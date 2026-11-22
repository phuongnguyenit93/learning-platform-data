# Cấu hình TLS và secret theo profile

## 1. Bài toán thực hành: một ứng dụng Spring Boot, nhiều môi trường SMTP

Trong dự án **Spring Framework Mail**, một ứng dụng thường phải gửi email trên nhiều môi trường:

- **Local/development:** developer muốn quan sát email trong một SMTP sink như Mailpit mà không gửi email ra Internet.
- **Test/CI:** test cần tái lập được, không dùng tài khoản SMTP production, không phụ thuộc mạng bên ngoài.
- **Staging:** kết nối SMTP thật hoặc môi trường kiểm thử riêng của provider để xác minh TLS, authentication, sender identity và giới hạn.
- **Production:** bảo vệ credential, bắt buộc TLS đúng cách, kiểm soát quyền truy cập và có khả năng vận hành/rotation.

Một cách làm nguy hiểm là lưu cấu hình duy nhất:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: my-production-account
    password: actual-production-password
~~~

trong repository, rồi dùng cho tất cả môi trường. Điều này có thể làm lộ secret, vô tình gửi email thật khi chạy test, và không chứng minh kết nối đã mã hóa. Cũng nguy hiểm nếu development tắt TLS để kết nối SMTP sink, sau đó cấu hình ấy bị mang lên production.

Giải pháp là **phân tách cấu hình theo Spring profile**, giữ **giá trị không bí mật** trong file được version control, còn **secret** được cung cấp lúc chạy qua cơ chế quản lý bí mật phù hợp. Môi trường có yêu cầu bảo mật phải áp dụng TLS **fail closed**, nghĩa là không âm thầm hạ cấp sang plaintext khi không thể thương lượng TLS.

Mục tiêu của bài thực hành:

1. Cấu hình `spring-boot-starter-mail` và `JavaMailSender` dùng các profile `local`, `staging`, `prod`.
2. Local gửi tới SMTP sink, không dùng password hay gửi tới tài khoản thật.
3. Staging/production dùng STARTTLS trên cổng submission 587 với TLS **bắt buộc**, xác minh hostname/certificate.
4. Biết khi nào dùng implicit TLS/SMTPS cổng 465 và tránh trộn cấu hình 465/587.
5. Truyền SMTP username/password bằng environment variables hoặc secret mount/secret manager, không hardcode trong Git.
6. Viết service gửi email mẫu, thử nghiệm và kiểm tra cấu hình đang có hiệu lực.
7. Biết cách xử lý lỗi handshake, authentication, profile precedence, rotation và secret leakage.

> **Phạm vi:** Đây là bài thực hành cấu hình mail client gửi qua SMTP. Nó không tự thiết lập SPF, DKIM, DMARC, không cấu hình mail server, không bảo đảm thư tới inbox và không thay thế cơ chế xử lý bounce/retry của hệ thống production.

## 2. Hiểu đúng các lớp bảo mật trước khi cấu hình

Luồng gửi email có thể gồm:

~~~text
Spring Boot application
      |
      | JavaMailSender / Jakarta Mail
      v
SMTP submission endpoint
      |
      | provider's relay network
      v
Recipient mail server
      |
      v
Recipient mailbox/client
~~~

TLS trong cấu hình `JavaMailSender` bảo vệ **kết nối giữa ứng dụng và SMTP submission endpoint**. Nó không phải cam kết end-to-end encryption xuyên qua mọi relay tới máy người nhận.

### 2.1. SMTP STARTTLS và SMTPS khác nhau

| Cách kết nối | Cổng thường gặp | Bắt đầu kết nối | Thiết lập TLS | Jakarta Mail property |
| --- | --- | --- | --- | --- |
| SMTP + STARTTLS | 587 | Kết nối SMTP plaintext để thương lượng | Lệnh `STARTTLS` nâng cấp sang TLS trước auth/data | `mail.smtp.starttls.enable=true` và `mail.smtp.starttls.required=true` |
| SMTP implicit TLS / SMTPS | 465 | TLS handshake ngay từ lúc kết nối | TLS trước khi trao đổi SMTP | `mail.smtp.ssl.enable=true` với protocol `smtp` |
| SMTP plaintext cho sink local | 1025, tùy tool | SMTP plaintext trong môi trường cô lập | Không có TLS | Tắt auth/STARTTLS chỉ tại profile local |
| SMTP cổng 25 | 25 | Thường dùng trao đổi mail server-to-server | Phụ thuộc mục đích và cấu hình | Không mặc định dùng làm client submission |

Các cổng trên là **quy ước phổ biến**, không thay thế tài liệu của SMTP provider. Có hệ thống dùng cổng khác. Điều quan trọng là chọn đúng **cơ chế TLS** mà server cung cấp.

### 2.2. STARTTLS phải được yêu cầu, không chỉ được cho phép

Với Jakarta Mail:

~~~properties
mail.smtp.starttls.enable=true
~~~

cho phép sử dụng STARTTLS nếu server hỗ trợ. Tuy nhiên, chỉ bật flag này **chưa bảo đảm** kết nối sẽ thất bại khi server không quảng bá STARTTLS. Ở môi trường yêu cầu mã hóa, phải bổ sung:

~~~properties
mail.smtp.starttls.required=true
~~~

để không âm thầm chuyển sang gửi qua SMTP plaintext nếu không thương lượng được TLS.

### 2.3. Kiểm tra tên máy chủ trên chứng chỉ

Thêm:

~~~properties
mail.smtp.ssl.checkserveridentity=true
~~~

để yêu cầu xác minh server identity phù hợp hostname trong TLS certificate. Không chỉ cần certificate có chain đáng tin cậy; còn phải xác nhận kết nối đến **đúng** máy chủ được yêu cầu.

Không dùng các “cách chữa nhanh” sau trên production:

~~~properties
mail.smtp.ssl.trust=*
mail.smtp.ssl.checkserveridentity=false
~~~

Trust-all hoặc bỏ hostname verification có thể vô hiệu hóa phần quan trọng của xác thực TLS, làm tăng rủi ro man-in-the-middle. Khi certificate/hostname sai, hãy sửa endpoint, DNS, chain hoặc truststore được quản lý thay vì bỏ kiểm tra.

### 2.4. SMTP AUTH không thay thế TLS

`mail.smtp.auth=true` yêu cầu SMTP authentication, nhưng **AUTH không đồng nghĩa đường truyền được mã hóa**. Một server có thể hỗ trợ AUTH qua connection không được bảo vệ nếu cấu hình sai. Cần kiểm soát cả:

~~~text
Correct host
    +
TLS required
    +
Certificate and hostname verification
    +
Authentication if provider requires it
    +
Authorized sender identity
~~~

Username/password là secret để xác thực với relay, không phải giải pháp mã hóa nội dung trên các chặng tiếp theo. Với provider hỗ trợ OAuth2, secret có thể là token hoặc credential để lấy token thay cho mật khẩu; nguyên tắc bảo vệ vẫn như nhau.

## 3. Cấu trúc dự án Spring Boot mẫu

Ví dụ sử dụng Java 17+, Spring Boot 3.x và Jakarta Mail qua Spring Boot Mail starter:

~~~text
mail-profile-lab/
├── pom.xml
├── compose.yaml
├── src/
│   ├── main/
│   │   ├── java/com/example/mail/
│   │   │   ├── MailProfileLabApplication.java
│   │   │   ├── MailDemoService.java
│   │   │   ├── MailIdentityProperties.java
│   │   │   └── MailTlsConfigurationGuard.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       ├── application-staging.yml
│   │       └── application-prod.yml
│   └── test/
│       └── java/com/example/mail/
│           └── MailProfileConfigurationTest.java
└── .gitignore
~~~

Tên tệp và package chỉ mang tính minh họa. Với Gradle, dùng các dependency tương đương thay vì Maven.

### 3.1. Dependencies

Trong Maven `pom.xml` (giả sử project đã dùng Spring Boot parent/BOM để quản lý version):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-mail` đưa vào auto-configuration cho `JavaMailSender` và các thư viện Jakarta Mail cần thiết khi cấu hình phù hợp. Không cần tự tạo `JavaMailSenderImpl` nếu chỉ có một SMTP sender theo active profile.

Nếu dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đoạn Gradle trên giả định project đã cấu hình Spring Boot plugin/dependency management. Không đặt password hoặc token vào `pom.xml`, `build.gradle` hay command line build.

### 3.2. Main application

~~~java
package com.example.mail;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MailProfileLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailProfileLabApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` sẽ đăng ký các configuration properties record/class trong package thích hợp của project.

## 4. Chiến lược Spring profiles

Một quy ước đơn giản:

| Profile | Kết nối mail | Secret | Bảo vệ |
| --- | --- | --- | --- |
| `local` | Mailpit/MailHog/GreenMail trên localhost hoặc mạng Docker riêng | Không cần mật khẩu cho SMTP sink local | Không được dùng để gửi ra Internet |
| `staging` | Staging SMTP account hoặc SMTP test account của provider | Secret staging riêng, giới hạn quyền | STARTTLS required + hostname verification |
| `prod` | SMTP production account đã phê duyệt | Secret prod từ runtime/secret manager | TLS fail-closed, quyền tối thiểu, rotate/audit |

**Không tự suy rằng tất cả profile ngoài `prod` có thể dùng plaintext.** Staging thường chứa dữ liệu/sender giống production hoặc kết nối tới hạ tầng ngoài, nên phải bảo vệ tương ứng.

### 4.1. Cách Spring Boot nạp cấu hình

Giả sử có:

~~~text
application.yml
application-local.yml
application-staging.yml
application-prod.yml
~~~

`application.yml` chứa thuộc tính chung. Khi active `local`, Spring Boot kết hợp cấu hình chung với `application-local.yml`; các giá trị cùng key có thể được override bởi nguồn cấu hình có thứ tự ưu tiên cao hơn.

Không đặt credential prod vào `application.yml` rồi “ghi đè” bằng local vì một profile thiếu/override sai có thể vô tình dùng production secret.

### 4.2. Kích hoạt profile

Ví dụ chạy:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
~~~

Hoặc đặt environment variable:

~~~bash
export SPRING_PROFILES_ACTIVE=local
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
.\mvnw.cmd spring-boot:run
~~~

Đây là lệnh phục vụ phát triển. Trong production, hệ thống triển khai (container orchestrator, runtime service manager) nên chịu trách nhiệm thiết lập profile. Không commit một `application.yml` có `spring.profiles.active: prod` rồi hy vọng mọi môi trường override đúng.

### 4.3. Không kích hoạt đồng thời các profile mâu thuẫn

Tránh cấu hình vận hành:

~~~text
SPRING_PROFILES_ACTIVE=local,prod
~~~

Hai profile có thể cùng định nghĩa `spring.mail.host`, `port` và TLS flags; kết quả phụ thuộc thứ tự nạp và property precedence, làm tăng rủi ro gửi sai endpoint hoặc dùng plaintext. Chọn **một profile môi trường** cho mail transport, hoặc thiết kế rõ profile groups/feature profiles không xung đột.

### 4.4. Không dùng default profile như đường gửi production

Nên coi **không có active environment profile** là một cấu hình chưa hoàn chỉnh, hoặc chỉ cho phép dùng local sandbox trong môi trường phát triển được kiểm soát. Một production deployment thiếu `SPRING_PROFILES_ACTIVE=prod` phải bị phát hiện, thay vì tự gửi qua SMTP endpoint không xác định.

## 5. Cấu hình chung: application.yml

Đưa các tham số không bí mật và có thể dùng chung vào `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: mail-profile-lab

  mail:
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"

app:
  mail:
    from: ""
~~~

Giải thích:

- `spring.mail.protocol=smtp` chọn protocol SMTP. Đây là cách phổ biến khi sử dụng `mail.smtp.*` properties.
- `default-encoding=UTF-8` hỗ trợ tiếng Việt trong body/subject; khi tạo MIME vẫn nên sử dụng encoding rõ ràng ở builder nếu cần.
- `connectiontimeout` đặt giới hạn chờ thiết lập kết nối.
- `timeout` giới hạn thời gian chờ đọc phản hồi từ SMTP.
- `writetimeout` giới hạn thời gian gửi dữ liệu trên socket.
- `app.mail.from` là configuration property do ứng dụng định nghĩa; nó **không phải property built-in** của `JavaMailSender`.

Giá trị timeout ở đây **chỉ minh họa** (millisecond), cần được điều chỉnh theo provider, kích thước message, SLA và throughput. Nếu không cấu hình, một số thao tác network có thể chờ không mong muốn, làm worker bị giữ lâu.

### 5.1. Vì sao dùng tên key trong ngoặc vuông?

`spring.mail.properties` là map chuyển tiếp tới Jakarta Mail. Trong YAML, cách viết:

~~~yaml
properties:
  "[mail.smtp.starttls.enable]": "true"
~~~

giữ nguyên key `mail.smtp.starttls.enable` khi binding vào `Properties`. Dấu ngoặc vuông nằm trong cấu hình map YAML; **key thực mà Jakarta Mail nhận** không chứa ngoặc vuông.

Trong file `.properties`, cách tương đương là:

~~~properties
spring.mail.properties.mail.smtp.starttls.enable=true
~~~

Việc dùng key bracketed trong YAML giúp tránh nhầm cấu trúc map có dấu chấm, nhất là khi nhiều properties được chuyển nguyên văn cho thư viện bên dưới.

### 5.2. Đặt timeout chung không phải bỏ qua profile

Có thể giữ timeout chung như trên, rồi mỗi profile override khi provider yêu cầu. Tuy nhiên, **TLS mode, endpoint và secret** nên khai báo minh bạch theo environment profile; không để một profile vô tình thừa hưởng giá trị bảo mật không đúng mục đích.

## 6. Profile local: SMTP sink không có secret

Tạo `src/main/resources/application-local.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_LOCAL_HOST:127.0.0.1}
    port: ${SMTP_LOCAL_PORT:1025}
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.starttls.required]": "false"
      "[mail.smtp.ssl.enable]": "false"

app:
  mail:
    from: "no-reply@local.test"
    send-demo-on-startup: false
~~~

Trong profile `local`:

- SMTP sink chỉ phục vụ quan sát email, không giao ra Internet.
- Không cần user/password.
- Plaintext ở đây chỉ chấp nhận trong **môi trường phát triển cô lập**.
- `send-demo-on-startup` là property của ứng dụng mẫu, mặc định tắt để khởi động ứng dụng không tự gửi thư.

Nếu SMTP sink thực sự dùng STARTTLS thì phải cấu hình theo endpoint đó, không cố áp dụng ví dụ plaintext. Tuyệt đối không dùng profile `local` cho production relay.

### 6.1. Chạy Mailpit qua Docker Compose

Tạo `compose.yaml` phục vụ local:

~~~yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:1025:1025"
      - "127.0.0.1:8025:8025"
~~~

~~~bash
docker compose up -d mailpit
~~~

Giải thích:

- `127.0.0.1:1025`: SMTP sink để JavaMailSender gửi message.
- `http://127.0.0.1:8025`: giao diện web xem các email đã nhận.
- Binding host `127.0.0.1` giúp tránh vô tình expose SMTP sink/UI ra mọi interface. Vẫn cần kiểm tra firewall và chính sách máy phát triển.
- Image `latest` chỉ tiện trong ví dụ local; CI hoặc môi trường cần tái lập nên **pin một image tag/digest đã kiểm soát**.

Không dùng Mailpit như SMTP relay production. Việc sink trả kết quả nhận thành công không chứng minh deliverability ở Gmail/Outlook hoặc TLS/authentication của SMTP provider thật.

### 6.2. Ứng dụng ở trong container khác thì localhost thay đổi

Nếu Spring Boot chạy trên máy host, `127.0.0.1:1025` có thể truy cập cổng đã publish. Nếu ứng dụng chạy trong **container khác của cùng Compose network**, `127.0.0.1` trỏ về chính container Spring Boot, không phải Mailpit.

Khi đó cấu hình container app có thể dùng:

~~~text
SPRING_PROFILES_ACTIVE=local
SMTP_LOCAL_HOST=mailpit
SMTP_LOCAL_PORT=1025
~~~

`mailpit` là tên service được DNS nội bộ Compose phân giải. Không hardcode `mailpit` vào production profile hoặc giả định endpoint này tồn tại ở ngoài Docker network.

### 6.3. Local có thể dùng GreenMail hoặc fake SMTP khác

Nếu cần giả lập phản hồi lỗi SMTP cụ thể, ví dụ `421`, `550`, disconnect sau DATA, một SMTP fake có programmable responses phù hợp hơn sink chỉ thu thư. Local profile vẫn phải giữ credential production ngoài môi trường test.

## 7. Profile staging: SMTP thật với STARTTLS bắt buộc

Tạo `src/main/resources/application-staging.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_STAGING_HOST}
    port: ${SMTP_STAGING_PORT:587}
    username: ${SMTP_STAGING_USERNAME}
    password: ${SMTP_STAGING_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.enable]": "false"
      "[mail.smtp.ssl.checkserveridentity]": "true"

app:
  mail:
    from: ${SMTP_STAGING_FROM}
    send-demo-on-startup: false
~~~

Các placeholder **không có giá trị mặc định** đối với host, username, password và sender identity. Nếu môi trường chưa cung cấp chúng, deployment nên không được coi là cấu hình hợp lệ.

Ví dụ các tên môi trường:

~~~text
SPRING_PROFILES_ACTIVE=staging
SMTP_STAGING_HOST=[staging SMTP host do provider cấp]
SMTP_STAGING_PORT=587
SMTP_STAGING_USERNAME=[staging user]
SMTP_STAGING_PASSWORD=[secret, injected securely]
SMTP_STAGING_FROM=[verified staging From address]
~~~

Đây là **tên biến minh họa**, không phải thông tin xác thực thực tế. Không điền password thật vào tài liệu, source code, screenshot hoặc issue.

### 7.1. Vì sao không dùng chung tài khoản staging/prod?

Tài khoản riêng giúp:

- Giảm phạm vi ảnh hưởng nếu credential staging bị lộ.
- Tránh test/CI làm cạn quota production.
- Kiểm soát From identity và recipient restrictions riêng.
- Dễ rotate/revoke một environment mà không làm gián đoạn environment khác.
- Phân biệt audit/log của hoạt động thử nghiệm với mail thật.

Staging nên sử dụng test recipients/allowlist hoặc sandbox mode của provider khi có. Đừng thử bằng cách gửi hàng loạt tới khách hàng thật.

### 7.2. TLS phải fail closed tại staging

Hai thuộc tính:

~~~yaml
"[mail.smtp.starttls.enable]": "true"
"[mail.smtp.starttls.required]": "true"
~~~

phải được hiểu là một cặp. Nếu server không quảng bá STARTTLS hoặc STARTTLS negotiation thất bại, ứng dụng **không được âm thầm tiếp tục truyền thông điệp qua plaintext**. Điều này là đặc biệt quan trọng trước khi thử SMTP AUTH.

Thêm `checkserveridentity=true` để xác minh hostname phù hợp certificate. Nếu staging dùng server riêng với CA nội bộ, hãy cài trust chain hợp lệ trong JVM/container, không đặt `mail.smtp.ssl.trust=*`.

## 8. Profile production: secret bắt buộc và TLS fail-closed

Tạo `src/main/resources/application-prod.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_PROD_HOST}
    port: ${SMTP_PROD_PORT:587}
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.enable]": "false"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "15000"
      "[mail.smtp.writetimeout]": "20000"

app:
  mail:
    from: ${SMTP_PROD_FROM}
    send-demo-on-startup: false
~~~

Trong production:

- Không có password mặc định; không dùng `:changeme`, `:password` hoặc giá trị dummy làm fallback.
- SMTP host, username, password, sender identity được cung cấp qua kênh runtime được bảo vệ.
- STARTTLS không được “optional” khi kết nối SMTP submission ngoài môi trường cô lập.
- Hostname verification bật.
- Timeout có giới hạn để giảm worker bị giữ vô hạn.
- Tắt tự động gửi demo và không có endpoint công khai cho phép gửi đến địa chỉ tùy ý.

Các timeout chỉ là ví dụ, không phải giá trị chuẩn bắt buộc. Với attachment lớn, throughput cao hoặc provider phản hồi chậm, cần đo thực tế và chọn timeout/backoff phù hợp.

### 8.1. Không hardcode secret trong YAML

Không nên:

~~~yaml
spring:
  mail:
    username: "prod-account"
    password: "very-secret-password"
~~~

Cũng không nên:

~~~yaml
spring:
  mail:
    password: "cHJvZC1wYXNzd29yZA=="
~~~

Base64 chỉ là encoding có thể đảo ngược, **không phải encryption hay secret manager**. Git history, artifact image, CI logs và quyền đọc file vẫn có thể làm lộ credential.

### 8.2. Không dùng production SMTP để chạy local test

Tránh:

~~~text
SPRING_PROFILES_ACTIVE=local
SPRING_MAIL_HOST=real-production-smtp.example.net
SPRING_MAIL_PASSWORD=production-secret
~~~

Environmental overrides có thể thay đổi giá trị từ file profile theo thứ tự ưu tiên của Spring Boot. Profile `local` **không đủ để chứng minh** endpoint cuối cùng là Mailpit nếu runtime được inject các biến `SPRING_MAIL_*` không mong muốn.

Phải có validation, môi trường CI riêng, network policy và bài test kiểm tra **effective sender configuration**, không chỉ đọc file YAML bằng mắt.

### 8.3. Secret rỗng hoặc thiếu phải làm deployment thất bại

Phương án tốt:

~~~text
SMTP_PROD_PASSWORD missing
    |
    v
Configuration validation fails
    |
    v
No SMTP submission attempt
~~~

Không nên tự gửi mà không xác thực, chuyển endpoint hoặc dùng fallback credential cũ chỉ để service khởi động được. Với các job quan trọng, lỗi cấu hình nên được phân biệt rõ với lỗi nhà cung cấp SMTP tạm thời.

## 9. Cổng 465: cấu hình implicit TLS/SMTPS đúng cách

Một số provider yêu cầu TLS handshake **ngay từ đầu** trên cổng 465. Khi đó STARTTLS 587 và implicit TLS 465 là hai cấu hình loại trừ nhau.

Ví dụ **thay thế** riêng cho production khi provider cấp endpoint cổng 465:

~~~yaml
spring:
  mail:
    protocol: smtp
    host: ${SMTP_PROD_HOST}
    port: 465
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.starttls.required]": "false"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "15000"
      "[mail.smtp.writetimeout]": "20000"

app:
  mail:
    from: ${SMTP_PROD_FROM}
~~~

**Không thêm đoạn này bên cạnh config STARTTLS 587 rồi hy vọng cả hai cùng có hiệu lực.** Chỉ dùng một mode phù hợp endpoint. Có thể tạo profile riêng `prod-465` hoặc config deployment-specific với validation, nhưng không kích hoạt đồng thời `prod` và `prod-465` nếu chúng đều override cùng properties.

### 9.1. Bảng kiểm tra nhanh

| Cổng | `starttls.enable` | `starttls.required` | `ssl.enable` | Ý nghĩa |
| ---: | --- | --- | --- | --- |
| 587 | true | true | false | STARTTLS bắt buộc |
| 465 | false | false | true | Implicit TLS từ lúc connect |
| 1025 (local sink) | false | false | false | Plaintext local cô lập |
| 587 | true | false | false | **Có nguy cơ downgrade** nếu server không hỗ trợ STARTTLS |
| 465 | true | true | false | Sai mode điển hình: chờ SMTP greeting thay vì bắt đầu TLS |
| 587 | false | false | true | Sai mode điển hình: TLS handshake ngay với endpoint chờ SMTP greeting |

`mail.smtp.ssl.checkserveridentity=true` nên bật với cả STARTTLS và implicit TLS ở môi trường bảo vệ. Không suy cơ chế chỉ từ số port nếu provider hướng dẫn khác; xác minh bằng documentation/provider test.

### 9.2. TLS protocols và JVM truststore

Với Java 17+, JVM có TLS stack và truststore riêng. Khi compliance yêu cầu giới hạn TLS protocol versions, có thể cân nhắc:

~~~properties
mail.smtp.ssl.protocols=TLSv1.2 TLSv1.3
~~~

nhưng chỉ đặt nếu provider và JVM thực sự hỗ trợ, và có đánh giá chính sách. Ép sai protocol có thể gây handshake failure. Không dùng `SSLv3`/TLS cũ hoặc bỏ xác thực certificate để “khắc phục”.

Nếu SMTP server dùng CA private của tổ chức, quản lý CA trong JVM truststore/image/runtime một cách hợp lệ. Tránh truyền truststore password nhạy cảm trên command line dễ bị ghi lại trong process inventory/log; lựa chọn cơ chế quản lý runtime phù hợp với môi trường.

## 10. Vì sao file cấu hình có placeholder vẫn chưa đủ bảo mật?

Ví dụ:

~~~yaml
password: ${SMTP_PROD_PASSWORD}
~~~

giúp **không commit mật khẩu** vào repository, nhưng secret vẫn phải tồn tại khi process chạy. Nếu tổ chức đưa secret tới ứng dụng qua pipeline không an toàn, việc dùng placeholder không tự sửa được toàn bộ vấn đề.

Nguồn lộ secret thường gặp:

| Vị trí | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Git/source repository | Password vào commit và lịch sử Git | Không lưu secret; secret scanning |
| File `.env` | Bị commit, sync hoặc đọc trái quyền | Gitignore, file local protected |
| CI pipeline variables | Bị in trong log/debug | Masking, scoped permissions, không echo |
| Dockerfile `ARG`/`ENV` | Có thể lộ trong image/history/build logs | Không bake runtime secret vào image |
| Container environment | Process/container inspector có thể thấy | Restrict access, ưu tiên secret mount khi hợp lý |
| Kubernetes Secret | API access và etcd/manifest controls | RBAC, encryption at rest, external secrets |
| Actuator `/env`, `/configprops` | Exposure nhầm giá trị cấu hình | Lock down management endpoints, sanitize |
| Jakarta Mail debug | Có thể lộ protocol/account/metadata | Tắt debug ở production |
| Exceptions/logs | Connection URL, username, nội dung email | Sanitized logging, safe error codes |

**Secret manager không thay TLS.** Một mật khẩu được lấy an toàn nhưng gửi qua SMTP plaintext vẫn có thể lộ trên đường truyền. Và TLS không thay secret manager: connection được mã hóa nhưng mật khẩu commit trong Git vẫn là lỗ hổng.

## 11. Cấp secret qua environment variables

Ở local, không cần password. Ở staging/prod, một lựa chọn triển khai phổ biến là runtime inject secret vào biến môi trường mà file YAML tham chiếu:

~~~yaml
spring:
  mail:
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
~~~

Một deployment phải thiết lập:

~~~text
SPRING_PROFILES_ACTIVE=prod
SMTP_PROD_HOST=<approved SMTP endpoint>
SMTP_PROD_PORT=587
SMTP_PROD_USERNAME=<secret or protected account identifier>
SMTP_PROD_PASSWORD=<injected from secret store>
SMTP_PROD_FROM=<verified sender address>
~~~

Các giá trị trong dấu `<...>` là ký hiệu minh họa, **không được copy nguyên thành credential**. Không paste password thật vào command/documentation hoặc echo ra log để kiểm tra.

### 11.1. Env vars có an toàn tuyệt đối không?

Không. Chúng giảm nguy cơ **commit secret vào repository**, nhưng quyền quản trị máy/container, process inspection, crash diagnostics, CI logging hoặc các công cụ observability cấu hình sai vẫn có thể làm lộ environment.

Với mức bảo mật cao:

- Chỉ inject secret ở runtime, không ở build step.
- Giới hạn quyền xem container/Pod spec và process environment.
- Dùng secret manager/workload identity để lấy secret khi cần.
- Không cho mọi service cùng xem SMTP production credential.
- Hạn chế shell history, diagnostics và logging environment.
- Lên lịch rotate/revoke, kiểm soát audit truy cập secret.

### 11.2. Đặt tên biến có chủ đích

Hai cách:

~~~text
Option A:
  SMTP_PROD_PASSWORD
  application-prod.yml -> ${SMTP_PROD_PASSWORD}

Option B:
  SPRING_MAIL_PASSWORD
  Spring Boot relaxed binding trực tiếp
~~~

Cả hai đều có thể dùng, nhưng nên chọn **một convention rõ ràng**. Khi kết hợp A và B, environment variable `SPRING_MAIL_PASSWORD` có thể override thuộc tính đã được bind từ placeholder trong profile, gây khó xác định effective value.

Khi debug, hãy kiểm tra **nguồn cấu hình** mà không in giá trị secret. Có thể log tên active profiles và một boolean “secret configured” đã sanitize, không log password.

### 11.3. Không dựa vào file .env bị commit

Một file local `.env` phục vụ thử nghiệm có thể tồn tại trên máy developer, nhưng:

- Không commit vào Git.
- Không đưa secret thật vào file mẫu `.env.example`.
- Không copy nó vào Docker image.
- Không cho phép đọc rộng rãi trên máy chia sẻ.
- Không đặt SMTP prod secret vào máy cá nhân nếu không cần.

Ví dụ `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
config/secrets/
*.keystore.local
~~~

Gitignore chỉ ngăn commit mới; **nó không xoá secret từng xuất hiện trong lịch sử Git**. Nếu đã commit credential, phải revoke/rotate ngay và xử lý lịch sử theo chính sách.

## 12. Secret file mount và Spring Boot config tree

Một lựa chọn khác là mount secret thành các **file chỉ đọc** trong container. Spring Boot hỗ trợ `configtree:` để biến tên file thành configuration property.

Giả sử runtime mount:

~~~text
/run/secrets/smtp/
  SMTP_PROD_USERNAME
  SMTP_PROD_PASSWORD
~~~

Trong `application-prod.yml`, có thể thêm:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/smtp/"
~~~

đồng thời giữ:

~~~yaml
spring:
  mail:
    username: ${SMTP_PROD_USERNAME}
    password: ${SMTP_PROD_PASSWORD}
~~~

Đây là các **đoạn cấu hình cần được gộp vào cùng YAML file hợp lệ**, không tạo hai root `spring:` trùng nhau trong cùng một document. Nếu mount có đúng tên file, `configtree:` cung cấp property source để placeholder đọc giá trị.

### 12.1. Vì sao dùng optional:configtree?

`optional:` cho phép không có **directory mount** khi deployment dùng environment variables thay thế. Tuy nhiên, `SMTP_PROD_PASSWORD` **không được có default**: nếu cả env lẫn configtree đều không cung cấp credential, binding/validation vẫn phải báo lỗi trước khi hệ thống gửi mail.

Nếu production **bắt buộc** phải sử dụng secret mount theo policy, bỏ `optional:` và fail startup khi thư mục không có. Điều này tránh chạy với nguồn secret không đúng chuẩn.

### 12.2. Configtree khác đọc nội dung file như một đường dẫn

Với:

~~~text
/run/secrets/smtp/SMTP_PROD_PASSWORD
~~~

`configtree:` đọc nội dung file và cung cấp property `SMTP_PROD_PASSWORD`. Còn nếu tự đặt:

~~~text
SMTP_PROD_PASSWORD=/run/secrets/smtp/password
~~~

thì placeholder chỉ nhận **chuỗi đường dẫn file**, không tự động đọc secret bytes. Hai cách khác nhau:

- **Config tree:** property được bind từ nội dung file.
- **Custom secret loader:** code hoặc framework tích hợp phải mở file/secret manager, xử lý encoding và lifecycle.

Không nhầm đường dẫn secret với giá trị password khi cấu hình `JavaMailSender`.

### 12.3. Quyền file và rotation

Secret mount nên có quyền đọc giới hạn cho account chạy JVM, không cho mọi container/user đọc. Một số secret mounts có khả năng cập nhật nội dung file, nhưng **Spring Boot/Jakarta Mail không mặc định tự reload password đã bind vào JavaMailSenderImpl ở mọi trường hợp**.

Khi rotate:

1. Tạo credential mới trong provider/secret manager.
2. Phân phối phiên bản mới cho workload theo cơ chế đã được phê duyệt.
3. Restart/refresh hoặc thay bean/sender instance một cách an toàn.
4. Thử kết nối/gửi bằng credential mới.
5. Thu hồi credential cũ sau khi xác nhận không còn workload dùng nó.

Không giả định “file trong mount đã đổi” nghĩa mọi SMTP connection đang hoạt động sẽ tự cập nhật authentication.

## 13. Kubernetes: dùng Secret có sẵn và giới hạn quyền

Để minh họa cách inject secret vào Spring Boot Pod, giả sử người quản trị **đã tạo** Kubernetes Secret `smtp-prod-auth` bằng một quy trình quản lý secret an toàn. Trong Deployment có thể khai báo:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-worker
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mail-worker
  template:
    metadata:
      labels:
        app: mail-worker
    spec:
      containers:
        - name: mail-worker
          image: registry.example.com/mail-worker:<pinned-version>
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: SMTP_PROD_HOST
              valueFrom:
                configMapKeyRef:
                  name: mail-prod-endpoint
                  key: host
            - name: SMTP_PROD_PORT
              value: "587"
            - name: SMTP_PROD_FROM
              valueFrom:
                configMapKeyRef:
                  name: mail-prod-endpoint
                  key: from
            - name: SMTP_PROD_USERNAME
              valueFrom:
                secretKeyRef:
                  name: smtp-prod-auth
                  key: username
            - name: SMTP_PROD_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: smtp-prod-auth
                  key: password
~~~

Đây là **đoạn Deployment minh họa**, cần thay image, namespace, resource limits, service account, network policy, pod security và các thành phần còn lại theo cluster thực tế. Không có credential thật trong manifest.

### 13.1. Những điều Kubernetes Secret không tự bảo đảm

- Giá trị Secret thường được biểu diễn Base64 trong YAML/API; Base64 **không phải encryption**.
- Phải cấu hình quyền RBAC để chỉ workload/operator được phép đọc.
- Nên bật cơ chế mã hóa Secret **at rest** trong control plane theo quản trị cluster.
- Phải kiểm soát quyền xem Pod/environment, audit và CI/CD credentials.
- Secret trong environment của process không tự được cập nhật khi giá trị ở Kubernetes Secret thay đổi; thường cần rollout/restart.
- Hạn chế quyền của service account, không mount token/quyền ngoài nhu cầu.

Với hệ thống có secret manager tập trung, có thể dùng CSI driver hoặc external-secret integration để mount/đồng bộ secret theo policy. Tên sản phẩm và cách đồng bộ phụ thuộc nền tảng; vẫn phải xác định cách ứng dụng **nhận phiên bản mới** sau rotate.

### 13.2. Mount secret như file thay vì environment

Một phương án cho container:

~~~yaml
volumeMounts:
  - name: smtp-auth
    mountPath: /run/secrets/smtp
    readOnly: true

volumes:
  - name: smtp-auth
    secret:
      secretName: smtp-prod-auth
      items:
        - key: username
          path: SMTP_PROD_USERNAME
        - key: password
          path: SMTP_PROD_PASSWORD
~~~

Đoạn này nằm đúng các vị trí `containers[].volumeMounts` và `pod.spec.volumes` trong Deployment hoàn chỉnh. Kết hợp với `configtree:/run/secrets/smtp/`, file names được bind thành properties. Nếu dùng file mount, loại bỏ việc inject cùng secret qua environment để tránh không rõ precedence.

### 13.3. Network policy

Một Pod gửi SMTP thường chỉ cần egress tới:

~~~text
Approved SMTP endpoint
Approved port (587 or 465)
DNS resolver
Any required secret-management endpoints
~~~

Không mở egress ra mọi IP/port nếu chính sách tổ chức yêu cầu giới hạn. Tuy nhiên, cần cân nhắc IP động/provider DNS và proxy service thực tế; không hardcode địa chỉ có thể thay đổi mà không có cơ chế cập nhật.

## 14. Docker Compose ứng dụng + secret: không bake password vào image

Trong Docker Compose, tránh:

~~~dockerfile
ARG SMTP_PASSWORD
ENV SMTP_PASSWORD=$SMTP_PASSWORD
~~~

Password có thể rò qua build layer/history/metadata hoặc build logs. **Build artifact phải độc lập với credential của môi trường triển khai**.

Ý tưởng triển khai:

~~~text
Build once:
  mail-worker.jar / container image (no secrets)
            |
            v
Deploy staging:
  application-staging.yml + staging secret
            |
            v
Deploy production:
  same image + application-prod.yml + prod secret
~~~

Một image có thể dùng cho nhiều environment nhờ property sources và secret injection khác nhau; không cần rebuild artifact với production password.

### 14.1. Docker secrets cần được đọc đúng cách

Trong một số môi trường Docker Compose/Swarm, secret được mount dưới `/run/secrets/<name>`, **không tự chuyển thành biến môi trường**. Có thể dùng configtree hoặc một secret loader. Nếu ứng dụng dùng `${SMTP_PROD_PASSWORD}`, cần đảm bảo property source thực sự cung cấp giá trị đó; chỉ mount file tên `smtp_password` mà không cấu hình mapping sẽ chưa đủ.

### 14.2. Không log toàn bộ environment để debug

Tránh:

~~~java
System.getenv().forEach((key, value) ->
        log.info("{}={}", key, value));
~~~

Cách này có thể in mật khẩu, API key, token, endpoint riêng hoặc thông tin nhạy cảm khác. Khi cần xác nhận profile, chỉ log **tên profile** và những metadata đã được duyệt, không in nguồn secret.

## 15. CI/CD: tách build, test và deployment credentials

Một pipeline tốt không cần production SMTP password để compile hoặc unit test Java code.

~~~text
Source repository
    |
    v
CI build + unit tests
    |  no production SMTP credentials
    |
    v
Immutable artifact/image
    |
    v
Staging deployment
    |  staging secrets only
    |  approved test recipients
    v
Staging smoke tests
    |
    v
Production approval/deploy
       production workload identity/secret
~~~

### 15.1. Những kiểm soát nên có

- Secret scanning trên commit và pull request.
- Không in `env`, shell command chứa secret hoặc full `application-prod.yml` đã resolve.
- CI test chỉ truy cập SMTP fake/sink nếu có thể.
- Staging secret có scope và lifecycle riêng.
- Prod deployment job dùng short-lived identity/secret access được cấp quyền tối thiểu.
- Khi workflow cần đọc secret, giới hạn quyền theo branch/environment/approval.
- Không đưa credential vào test reports, crash dumps, artifacts hoặc container build args.

### 15.2. Kiểm tra trong CI không cần gửi mail thật

Phần lớn test nên kiểm tra:

1. Profile local bind host/port/auth đúng.
2. Profile staging/prod bind required TLS flags đúng.
3. Cấu hình thiếu secret bị từ chối/validation fail.
4. Mail composer tạo MIME message đúng.
5. Không có SMTP production calls từ unit/integration tests.

Chỉ một số test staging được ủy quyền mới cần kết nối SMTP thật để xác nhận certificate, AUTH, identity và provider constraints.

## 16. Viết service gửi mail đơn giản để thử các profile

Bài thực hành nên có một service nhỏ giúp kiểm tra việc inject `JavaMailSender` và sender identity. Service này **không tự chọn profile**; Spring Boot đã quyết định cấu hình effective ở bước khởi tạo.

### 16.1. Properties của ứng dụng

Tạo `MailIdentityProperties.java`:

~~~java
package com.example.mail;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailIdentityProperties(
        @NotBlank String from) {
}
~~~

`@Validated` kết hợp `spring-boot-starter-validation` giúp fail startup khi `app.mail.from` rỗng. Đây là validation cơ bản; một production service còn phải kiểm tra sender domain thuộc danh sách identity đã được xác minh tại SMTP provider.

### 16.2. Service dùng SimpleMailMessage

Tạo `MailDemoService.java`:

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public final class MailDemoService {

    private final JavaMailSender mailSender;
    private final MailIdentityProperties identity;

    public MailDemoService(
            JavaMailSender mailSender,
            MailIdentityProperties identity) {
        this.mailSender = mailSender;
        this.identity = identity;
    }

    public void sendTestMessage(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(identity.from());
        message.setTo(recipient);
        message.setSubject("Spring Mail profile test");
        message.setText(
                "Xin chào! Đây là email kiểm tra cấu hình.");

        mailSender.send(message);
    }
}
~~~

`SimpleMailMessage` phù hợp với plain text. Khi cần HTML, ảnh CID hoặc attachment, dùng `MimeMessage`/`MimeMessageHelper` (phần sau), nhưng TLS và secret config ở tầng `JavaMailSender` vẫn được áp dụng như nhau.

**Không mở một public HTTP endpoint nhận `recipient` tùy ý chỉ để test** nếu endpoint có thể bị lạm dụng gửi thư, tiêu thụ quota hoặc phát tán spam.

### 16.3. Runner chỉ được bật có chủ đích trong local

Tạo một class cấu hình:

~~~java
package com.example.mail;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
public class LocalMailDemoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.mail",
            name = "send-demo-on-startup",
            havingValue = "true")
    ApplicationRunner sendLocalDemo(MailDemoService service) {
        return args ->
                service.sendTestMessage("demo@local.test");
    }
}
~~~

Code chỉ gửi khi **cả hai** điều kiện đúng:

1. Active profile `local`.
2. `app.mail.send-demo-on-startup=true`.

Trong `staging`/`prod`, bean không được tạo. Không dùng một `CommandLineRunner` mặc định gửi email ngay khi production deployment khởi động.

### 16.4. Chạy smoke test local

Khi Mailpit đã chạy:

~~~bash
SPRING_PROFILES_ACTIVE=local \
APP_MAIL_SEND_DEMO_ON_STARTUP=true \
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_MAIL_SEND_DEMO_ON_STARTUP = "true"
.\mvnw.cmd spring-boot:run
~~~

Mở `http://127.0.0.1:8025` và kiểm tra một email `Spring Mail profile test`. Sau khi thử, xóa biến `APP_MAIL_SEND_DEMO_ON_STARTUP` hoặc tắt chức năng để các lần chạy tiếp theo không tự tạo thư.

Nếu Spring chạy trong Compose network, nhớ đổi `SMTP_LOCAL_HOST=mailpit`. Không chuyển runner local thành một cron job hay REST endpoint ở production.

## 17. Gửi HTML và attachment không làm thay đổi cách cấu hình TLS

TLS/authentication thuộc SMTP transport, trong khi `MimeMessageHelper` chịu trách nhiệm tạo message body và attachments. Không cần tạo một sender “kém bảo mật” riêng cho HTML.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class HtmlWelcomeComposer {

    private final JavaMailSender sender;

    public HtmlWelcomeComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(
            String from,
            String recipient) throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject("Chào mừng!");

        helper.setText(
                "Chào mừng bạn đến với dịch vụ.",
                "<html><body>"
                    + "<h1>Chào mừng!</h1>"
                    + "<img src=\"cid:brandLogo\" alt=\"Company\">"
                    + "</body></html>");

        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        sender.send(message);
    }
}
~~~

Ví dụ cần asset `src/main/resources/mail/images/logo.png` tồn tại trong artifact. `ClassPathResource` đọc được từ JAR; không nhúng `C:\...`, `/opt/app/...` hoặc `file:///...` vào HTML của người nhận.

### 17.1. Không nhầm TLS của SMTP với HTTPS của ảnh

Một email gửi qua STARTTLS có thể chứa:

~~~html
<img src="https://cdn.example.com/email/logo.png">
~~~

Khi mở thư, mail client có thể tải ảnh theo một kết nối HTTPS riêng; đó là **một giao dịch khác** với SMTP STARTTLS giữa Spring và relay. Tài nguyên HTTP không được mã hóa chỉ vì message đã dùng SMTP TLS.

### 17.2. Attachment có thể bị lộ ngay cả khi SMTP dùng TLS

TLS bảo vệ SMTP transport tới relay, nhưng sau khi provider accepted, email/MIME có thể được xử lý ở nhiều hệ thống. Nếu gửi tài liệu nhạy cảm:

- Kiểm tra recipient đúng và được authorize.
- Bảo vệ attachment source và object storage.
- Có content/size/malware controls phù hợp.
- Không log MIME bytes hoặc file path nhạy cảm.
- Cân nhắc portal link có authentication khi cần revoke/access control.

## 18. Tạo guard kiểm tra chính sách TLS lúc khởi động

YAML bảo mật rất hữu ích, nhưng có nguy cơ **property override ngoài ý muốn** qua environment, profile activation, deployment flags hoặc secret source. Một ứng dụng có yêu cầu cao có thể kiểm tra **effective JavaMailSender configuration** và từ chối khởi động nếu cấu hình trái chính sách.

### 18.1. Ví dụ MailTlsConfigurationGuard

~~~java
package com.example.mail;

import java.util.Arrays;
import java.util.List;
import java.util.Properties;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component
public final class MailTlsConfigurationGuard
        implements ApplicationRunner {

    private final Environment environment;
    private final JavaMailSender mailSender;

    public MailTlsConfigurationGuard(
            Environment environment,
            JavaMailSender mailSender) {
        this.environment = environment;
        this.mailSender = mailSender;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> active = Arrays.asList(
                environment.getActiveProfiles());

        int environmentProfiles = 0;
        if (active.contains("local")) {
            environmentProfiles++;
        }
        if (active.contains("staging")) {
            environmentProfiles++;
        }
        if (active.contains("prod")) {
            environmentProfiles++;
        }

        if (environmentProfiles != 1) {
            throw new IllegalStateException(
                    "Exactly one mail environment profile is required");
        }

        if (active.contains("local")) {
            return;
        }

        if (!(mailSender instanceof JavaMailSenderImpl sender)) {
            throw new IllegalStateException(
                    "Mail transport requires an approved TLS validator");
        }

        Properties p = sender.getJavaMailProperties();

        boolean starttlsEnabled = flag(
                p, "mail.smtp.starttls.enable");
        boolean starttlsRequired = flag(
                p, "mail.smtp.starttls.required");
        boolean implicitTls = flag(
                p, "mail.smtp.ssl.enable");
        boolean hostVerified = flag(
                p, "mail.smtp.ssl.checkserveridentity");

        boolean starttlsMode =
                starttlsEnabled && starttlsRequired && !implicitTls;
        boolean implicitTlsMode =
                implicitTls && !starttlsEnabled;

        if (!(starttlsMode || implicitTlsMode)) {
            throw new IllegalStateException(
                    "Approved TLS mode is required for SMTP");
        }
        if (!hostVerified) {
            throw new IllegalStateException(
                    "SMTP hostname verification must be enabled");
        }
        if ("*".equals(p.getProperty("mail.smtp.ssl.trust"))) {
            throw new IllegalStateException(
                    "Trust-all SMTP TLS configuration is forbidden");
        }

        if (blank(sender.getHost())
                || blank(sender.getUsername())
                || blank(sender.getPassword())) {
            throw new IllegalStateException(
                    "SMTP endpoint or credentials are missing");
        }
    }

    private static boolean flag(
            Properties p, String key) {
        return Boolean.parseBoolean(
                p.getProperty(key, "false"));
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

**Giới hạn của ví dụ:**

- Guard giả định chỉ có một `JavaMailSenderImpl` do Spring Boot Mail auto-configuration cung cấp. Nếu project bọc sender bằng proxy, dùng JNDI session, nhiều provider adapters hoặc custom SSL socket factory, phải viết validator theo abstraction thực tế.
- Guard kiểm tra mode TLS/host verification/credential **trong cấu hình**, không chứng minh certificate/endpoint thật hợp lệ trước khi kết nối.
- Guard không in secret hoặc hostname ra exception.
- Guard không tự test SMTP network; một provider outage có thể xảy ra sau startup.
- Nếu thêm environment profile khác, cập nhật policy; không bỏ qua nó một cách âm thầm.

### 18.2. Ngăn nhiều profile môi trường cùng được kích hoạt

Code trên kiểm tra chính xác một trong `local`, `staging`, `prod`. Đây là policy của **bài thực hành**, không phải yêu cầu chung của Spring. Một hệ thống có profile features bổ sung (`metrics`, `cloud`) vẫn có thể kích hoạt chúng, miễn không kích hoạt hai **environment mail profiles** cùng lúc.

### 18.3. Không dựa vào guard để chống mọi kiểu override

Nếu một attacker có quyền thay environment/secret/ứng dụng, họ có thể phá những lớp bảo vệ khác. Guard là **defense in depth** để bắt cấu hình sai, không thay RBAC, network policy, secret manager và kiểm thử deployment.

### 18.4. Startup validation và health check khác nhau

Có thể chọn `spring.mail.test-connection=true` để Spring Boot kiểm tra kết nối SMTP khi khởi động trong một số cấu hình. Điều này có thể khiến service không khởi động khi provider tạm lỗi. Đây là một lựa chọn về availability/readiness, không nhất thiết phù hợp với worker dùng durable outbox.

Phân biệt:

- **Configuration validation:** host/credential/TLS flags hợp lệ.
- **Transport connectivity check:** có mở kết nối, thương lượng TLS và authenticate được không.
- **Application readiness:** worker có thể phục vụ luồng mail theo SLO không.
- **Business delivery:** provider đã accepted/delivered message hay chưa.

Không nên đặt logic “gửi thử một email thật” trong mọi startup health check; nó có thể gây gửi trùng, tốn quota và ảnh hưởng reputation.

## 19. Kiểm thử cấu hình profile mà không gọi SMTP thật

Mục tiêu đầu tiên là kiểm tra Spring Boot có bind đúng thuộc tính cho `JavaMailSenderImpl` và không vô tình tắt TLS trong staging/prod. Việc này **không cần kết nối mạng**.

### 19.1. Unit/integration test effective properties ở prod

Ví dụ với JUnit 5 và Spring Boot Test:

~~~java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
    "SMTP_PROD_HOST=smtp.test.invalid",
    "SMTP_PROD_PORT=587",
    "SMTP_PROD_USERNAME=non-secret-test-user",
    "SMTP_PROD_PASSWORD=non-secret-test-value",
    "SMTP_PROD_FROM=test-sender@example.test",
    "spring.mail.test-connection=false"
})
@ActiveProfiles("prod")
class MailProdConfigurationTest {

    @Autowired
    private JavaMailSender mailSender;

    @Test
    void prodRequiresStarttlsAndHostnameVerification() {
        assertThat(mailSender)
                .isInstanceOf(JavaMailSenderImpl.class);

        JavaMailSenderImpl sender =
                (JavaMailSenderImpl) mailSender;

        assertThat(sender.getHost())
                .isEqualTo("smtp.test.invalid");
        assertThat(sender.getPort()).isEqualTo(587);

        assertThat(sender.getJavaMailProperties())
                .containsEntry(
                        "mail.smtp.auth", "true")
                .containsEntry(
                        "mail.smtp.starttls.enable", "true")
                .containsEntry(
                        "mail.smtp.starttls.required", "true")
                .containsEntry(
                        "mail.smtp.ssl.enable", "false")
                .containsEntry(
                        "mail.smtp.ssl.checkserveridentity", "true");
    }
}
~~~

`smtp.test.invalid` và các credentials ở đây chỉ là **giá trị giả cố ý không dùng được**, và test không gọi `send(...)`. Nó kiểm tra config binding, không kiểm tra SMTP TLS handshake thật. Không đặt provider thật vào test tự động chỉ để xác nhận properties.

Đối với cấu hình implicit TLS 465, viết test tương ứng khẳng định `ssl.enable=true` và `starttls.enable=false`, thay vì áp bài test STARTTLS trên môi trường 465.

### 19.2. Test local không có authentication

~~~java
@SpringBootTest(properties = {
    "spring.mail.test-connection=false",
    "app.mail.send-demo-on-startup=false"
})
@ActiveProfiles("local")
class MailLocalConfigurationTest {

    @Autowired
    JavaMailSenderImpl sender;

    @Test
    void localTargetsIsolatedSmtpSink() {
        assertThat(sender.getPort()).isEqualTo(1025);
        assertThat(sender.getJavaMailProperties())
                .containsEntry("mail.smtp.auth", "false")
                .containsEntry(
                        "mail.smtp.starttls.required", "false")
                .containsEntry(
                        "mail.smtp.ssl.enable", "false");
    }
}
~~~

Test giả định local config mặc định dùng 1025 và không có `SMTP_LOCAL_PORT` override. Nếu CI set biến override, test nên cố định host/port trong test properties hoặc cách ly environment để kết quả tái lập được.

### 19.3. Test cấu hình thiếu secret

Một test negative cần kiểm tra:

~~~text
active profile = prod
SMTP_PROD_HOST present
SMTP_PROD_USERNAME present
SMTP_PROD_PASSWORD absent/blank

Expected:
  application configuration fails safely,
  no SMTP connection is attempted.
~~~

Nếu dùng `ApplicationContextRunner` hoặc `SpringApplicationBuilder` để tạo isolated context, phải đảm bảo context test **không kế thừa secret production từ máy CI**. Một test “thiếu password” chạy trong môi trường đã inject password có thể cho kết quả sai.

Đừng đưa kết quả test vào tài liệu như `PASS` nếu chưa thật sự chạy. Bài này trình bày mẫu kiểm thử, còn mỗi dự án cần áp dụng với cấu hình dependency/version thực tế của mình.

### 19.4. Test bảo vệ chống override sai

Các trường hợp hữu ích:

| Profile | Thuộc tính bị thay sai | Kỳ vọng |
| --- | --- | --- |
| `prod` | `mail.smtp.starttls.required=false` | Guard từ chối |
| `prod` | `mail.smtp.ssl.checkserveridentity=false` | Guard từ chối |
| `staging` | `spring.mail.password` rỗng | Guard từ chối |
| `prod` | `mail.smtp.ssl.trust=*` | Guard từ chối |
| `local,prod` | Hai environment profiles cùng active | Guard từ chối |
| `local` | Không bật demo runner | Không gửi tự động |
| `prod` | Bật `app.mail.send-demo-on-startup=true` | Không tạo local runner |
| `prod` | Missing sender identity | Property validation thất bại |
| `prod-465` (nếu có) | SSL off/STARTTLS on | Mode policy thất bại |

Một guard chỉ bảo vệ một phần policy. Để chắc local không trỏ vào SMTP production, cần thêm **test/network allowlist cho local endpoint** và quản lý nguồn config cao ưu tiên, không chỉ dùng chính sách TLS của prod.

## 20. Kiểm tra STARTTLS và certificate bằng công cụ chẩn đoán

Trong môi trường staging được ủy quyền, có thể kiểm tra endpoint từ một máy có đường mạng tương tự ứng dụng.

### 20.1. Kiểm tra STARTTLS trên 587

Ví dụ với OpenSSL:

~~~bash
openssl s_client \
  -starttls smtp \
  -connect smtp.staging.example.net:587 \
  -servername smtp.staging.example.net \
  -verify_return_error
~~~

Thay hostname bằng endpoint staging thực. Lệnh này không cần username/password để kiểm tra **TLS handshake/certificate** ở mức giao thức. Trạng thái verify phụ thuộc CA truststore của máy chạy OpenSSL; JVM có truststore riêng và có thể cho kết quả khác.

Cần quan sát:

- Server có quảng bá STARTTLS đúng không?
- TLS handshake thành công không?
- Certificate còn hạn và chain trusted không?
- SAN/hostname có khớp endpoint không?
- Có proxy/corporate TLS inspection gây thay certificate không?
- Protocol/cipher được thương lượng có phù hợp chính sách không?

### 20.2. Kiểm tra implicit TLS trên 465

~~~bash
openssl s_client \
  -connect smtp.staging.example.net:465 \
  -servername smtp.staging.example.net \
  -verify_return_error
~~~

Với implicit TLS, không thêm `-starttls smtp` vì client phải làm TLS handshake ngay lúc connect. Nếu dùng sai mode, có thể thấy timeout, `wrong version number` hoặc lỗi nhận SMTP greeting.

### 20.3. OpenSSL thành công chưa chứng minh JavaMailSender thành công

Kết nối thử TLS chỉ kiểm tra một phần:

~~~text
Network reachability
      |
      v
TLS handshake
      |
      v
SMTP AUTH
      |
      v
MAIL FROM / RCPT TO
      |
      v
DATA / provider accepts
~~~

OpenSSL thường chưa thử AUTH, sender identity, quota hoặc nội dung MIME. JavaMailSender có thể dùng JVM truststore, TLS protocols và proxy configuration khác. Một smoke test staging được ủy quyền vẫn cần khi triển khai thực tế.

### 20.4. Không paste mật khẩu vào terminal test

Đừng nhập command có username/password thật trong shell history hoặc issue. Nếu một công cụ yêu cầu auth, dùng quy trình credential injection được phê duyệt và tránh in transcript có secret. Không bật debug toàn bộ giao thức trong production chỉ để “xem SMTP có kết nối được”.

## 21. Phân loại lỗi cấu hình theo triệu chứng

Các lỗi TLS, authentication, profile và SMTP connection có thể tạo exception tương tự nhau ở tầng Spring. Cần **phân biệt giai đoạn** trước khi sửa.

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra/hướng xử lý |
| --- | --- | --- |
| `Could not connect to SMTP host` | Host/port/DNS/firewall sai, service không mở | Xác nhận effective host/port và network egress |
| `Connection refused` | Không có listener hoặc port bị chặn | Kiểm tra SMTP endpoint/Mailpit/local vs container network |
| `Connection timed out` | Firewall, DNS/routing, endpoint không phản hồi | Traceroute/egress policy ở môi trường cho phép |
| `STARTTLS is required but host does not support STARTTLS` | Server không quảng bá STARTTLS | Xác minh endpoint/port đúng; **không tắt required trong prod** |
| `Could not convert socket to TLS` | Handshake, protocol/cipher, certificate hoặc proxy | Xem nested cause, CA/truststore, endpoint mode |
| `PKIX path building failed` | Java không trust chain certificate | Cài CA đúng/hoàn chỉnh certificate chain |
| `No subject alternative DNS name matching` | Hostname không khớp cert | Sửa hostname/SAN, không disable verification |
| `SSLHandshakeException` | Nhiều nguyên nhân TLS | Kiểm tra root cause và endpoint 587/465 |
| `Unsupported or unrecognized SSL message` | Trộn implicit TLS với plaintext/STARTTLS | Sửa `ssl.enable`/port |
| `AuthenticationFailedException` | Credential sai/hết hạn, account disabled, AUTH policy | Xác minh secret version, provider account/auth mechanism |
| `535 Authentication credentials invalid` | SMTP AUTH bị từ chối | Rotate/cấp lại account, không retry mật khẩu sai liên tục |
| `530 Must issue STARTTLS first` | AUTH hoặc MAIL command trước TLS | Bật STARTTLS required và đúng port |
| `550 Sender address rejected` | From/envelope/domain không được phép | Kiểm tra verified sender identity và provider policy |
| `421 Service not available` | Provider temporarily unavailable | Backoff/rate limit/alert theo policy |
| `454 TLS not available temporarily` | Server TLS capability lỗi tạm | Không downgrade; retry có giới hạn |
| `spring.mail.username` null | Missing profile/secret config | Kiểm tra active profile/property source không in value |
| Placeholder `${SMTP_PROD_PASSWORD}` unresolved | Secret chưa inject | Kiểm tra secret mount/env key và startup validation |
| Chạy local nhưng gửi mail thật | Property override/profile sai | Xem effective host và `SPRING_MAIL_*` sources |
| CI test thất bại do production SMTP unreachable | Test vô tình dùng provider thật | Chuyển sang local fake SMTP, không dùng prod creds |
| Mail accepted nhưng không tới inbox | Provider/recipient delivery, spam/bounce | SPF/DKIM/DMARC, feedback, provider logs; không chỉ TLS |

Không sửa bằng cách đổi tất cả `MailException` thành retry vô hạn. Một số lỗi cấu hình như sai credential hoặc hostname sẽ không tự phục hồi nếu không thay config.

### 21.1. Bắt nguyên nhân gốc

`JavaMailSender` có thể ném `MailAuthenticationException`, `MailSendException` hoặc `MailPreparationException`; bên trong còn có Jakarta Mail/TLS exception. Xem cause chain và giai đoạn:

~~~text
MailSendException
  -> MessagingException
     -> SSLHandshakeException
        -> ValidatorException / certificate cause
~~~

Điều này giúp phân biệt:

- Lỗi certificate trust.
- Sai host/SAN.
- TLS protocol mismatch.
- SMTP AUTH reject.
- Không thể đọc attachment trước gửi.
- SMTP transport đã bắt đầu nhưng kết quả submission không chắc chắn.

Không log nguyên stack trace tới một đích thiếu quyền truy cập nếu exception chứa metadata hoặc user data nhạy cảm. Dùng safe error code và correlation ID cho monitoring.

### 21.2. SMTP exception không luôn chứng minh thư chưa được gửi

Nếu lỗi xảy ra sau khi đã truyền toàn bộ DATA và client mất response, provider có thể đã accepted message. Khi retry, **có nguy cơ gửi trùng**. TLS timeout hay socket reset chỉ là dấu hiệu transport; hệ thống cần trạng thái `UNKNOWN`/reconciliation theo business policy thay vì gửi lại ngay.

## 22. Xác nhận effective configuration theo hướng không lộ secret

Khi cần debug một deployment, thông tin an toàn nên có:

~~~text
environmentProfile = prod
smtpMode = STARTTLS_REQUIRED
smtpPort = 587
hostnameVerification = true
smtpAuthEnabled = true
smtpSecretPresent = true
smtpSecretVersion = [approved non-secret version identifier]
~~~

Không nhất thiết log hostname nếu đây là thông tin hạ tầng nhạy cảm. Tránh log:

~~~text
smtpPassword = ...
smtpAuthToken = ...
JavaMail properties dump (possibly includes sensitive data)
MimeMessage content / recipients / attachment bytes
~~~

### 22.1. Actuator cần giới hạn

Spring Boot Actuator có thể giúp kiểm tra trạng thái ứng dụng nhưng endpoint như `/env` hoặc `/configprops` có thể tiết lộ cấu hình hoặc ít nhất metadata cấu hình nếu expose sai. Chỉ cho phép endpoint cần thiết với authentication/authorization, không bật `show-values=always` ở public production.

Các thuộc tính mang tên password thường được masking trong những cấu hình framework, nhưng **không dựa tuyệt đối vào masking** để bảo vệ secrets; một custom property hoặc log tự viết vẫn có thể lộ thông tin.

### 22.2. Header/debug của Jakarta Mail

Không bật `mail.debug=true` ở production khi không có quy trình kiểm soát, vì protocol transcript, địa chỉ email, capability, AUTH mechanism và các thông tin khác có thể xuất hiện trong log. Dù một thư viện có cơ chế che bớt nội dung AUTH, không coi đây là bảo đảm để log mọi thứ.

Nếu cần debug trong staging, bật ngắn hạn, dùng test account/recipient và lưu log theo retention hạn chế.

## 23. Rotation secret và bảo đảm availability

Mật khẩu ứng dụng, SMTP password hay OAuth credential có thể bị rotate vì lịch định kỳ, rò rỉ hoặc thay đổi chính sách provider.

### 23.1. Quy trình rotation có kiểm soát

~~~text
Create new provider credential
           |
           v
Store new version in secret manager
           |
           v
Deploy/refresh limited canary workload
           |
           v
Confirm TLS + auth + approved sender identity
           |
           v
Roll out remaining instances
           |
           v
Monitor auth failures, queue age, send outcomes
           |
           v
Revoke old credential
           |
           v
Audit and close rotation
~~~

Nếu provider hỗ trợ **song song hai credential** trong khoảng chuyển đổi, việc rotate ít gián đoạn hơn. Nếu chỉ có một password, cần kế hoạch rolling restart/stop dispatch phù hợp và thông báo cho người vận hành.

### 23.2. Không cập nhật password trên singleton tùy tiện

Trong hệ thống multi-thread, không nên cho nhiều request thay `JavaMailSenderImpl.setPassword(...)` đồng thời với việc gửi thư mà không có cơ chế đồng bộ/phiên bản:

~~~text
Worker A starts SMTP AUTH with credential v1
Secret reload overwrites shared sender to v2
Worker B starts send with changed configuration
~~~

Cơ chế refresh phải bảo đảm sender/connection configuration nhất quán cho từng attempt. Với Spring Boot auto-config một SMTP account, **rolling restart với phiên bản secret mới** thường dễ kiểm soát hơn mutate bean in-place mà không có protocol.

### 23.3. Khi rotation bị lỗi

Nếu credential mới không authenticate:

1. Kiểm tra version/permission và account status, không log mật khẩu.
2. Ngừng tăng tốc retry cùng credential sai; lỗi AUTH có thể gây lockout.
3. Giữ mail intents trong durable queue nếu workflow hỗ trợ.
4. Roll back sang phiên bản còn hợp lệ **chỉ khi chính sách cho phép và chưa revoke**.
5. Khắc phục secret distribution/config, rồi thử với test delivery.
6. Đánh dấu incident và cập nhật runbook nếu phát hiện giả thiết sai.

Đừng coi AUTH failure giống một lỗi mạng tạm thời rồi retry hàng trăm lần mỗi phút.

## 24. Nếu nhà cung cấp dùng OAuth2 thay cho SMTP password

Một số provider yêu cầu hoặc khuyến khích token-based authentication thay vì password truyền thống. Trong trường hợp này, ý tưởng profile separation vẫn đúng, nhưng secret có thể là:

- Client credential để lấy access token.
- Refresh token được phép theo chính sách.
- Workload identity liên kết tới hệ cấp token.
- Token ngắn hạn để SMTP AUTH XOAUTH2.

Không nên cố đưa một OAuth2 access token vĩnh viễn vào `application-prod.yml` vì token có thể hết hạn và cần refresh theo lifecycle.

### 24.1. Những câu hỏi kiến trúc cần giải quyết

1. Workload được cấp token bằng cơ chế nào?
2. Token audience/scope có giới hạn đủ cho mail submission không?
3. Token hết hạn khi nào và refresh thế nào?
4. Token được đưa vào Jakarta Mail AUTH bằng mechanism nào?
5. Connection hiện tại có bị ảnh hưởng khi token rotate không?
6. Có thể tạm dừng gửi khi identity provider unavailable không?
7. Làm sao log lỗi auth mà không log access/refresh token?

Các chi tiết XOAUTH2/Jakarta Mail provider-specific phải dựa vào tài liệu của SMTP provider và phiên bản thư viện đang dùng. Đừng chỉ đổi `spring.mail.password` từ password sang token rồi mặc định mọi server tự hỗ trợ mechanism phù hợp.

### 24.2. OAuth2 không làm biến mất yêu cầu TLS

Dù AUTH dùng password hay OAuth2, vẫn phải:

~~~text
TLS required and host verified
    +
Authorized SMTP endpoint
    +
Token/credential scoped to sender account
    +
Safe logging and rotation
~~~

Access token là một secret có giá trị trong thời hạn tồn tại; việc gửi token qua plaintext là rủi ro bảo mật.

## 25. TLS và secret trong hệ thống có nhiều SMTP providers

Bài thực hành dùng một `JavaMailSender` theo profile, nhưng một hệ thống lớn có thể dùng nhiều SMTP relays hoặc kết hợp HTTP email API. Khi ấy, không nên đổi `host`, `username` và `password` trên **một sender singleton** theo từng email.

~~~text
Business mail service
       |
       v
Provider selector (tenant, region, category)
       |
       +--> SMTP Provider A
       |      senderA with its own TLS/auth/secret
       |
       +--> SMTP Provider B
       |      senderB with its own TLS/auth/secret
       |
       +--> HTTP API Provider C
              clientC with its own HTTPS auth
~~~

Với mỗi SMTP adapter, cần có:

- Endpoint host/port đúng.
- TLS mode bắt buộc theo provider và yêu cầu bảo mật.
- Hostname/certificate verification.
- Secret riêng theo account/identity.
- Timeout, quota và retry policy rõ.
- Provider-specific feedback/bounce correlation.

**Fallback không được vượt policy**: nếu provider A TLS handshake thất bại, không chuyển sang B ở region không được phép hoặc dùng account không verify From domain. Và nếu SMTP DATA trên A đã gửi nhưng response không rõ, **không blind fallback** chỉ vì A gặp timeout.

### 25.1. Không dùng cấu hình “nới lỏng để fallback”

Sai:

~~~text
Primary A:
  STARTTLS required = true

Fallback B:
  STARTTLS required = false
  hostname check = false
~~~

Một provider dự phòng phải đáp ứng **các yêu cầu bảo mật tối thiểu tương đương**, không phải đường tắt giảm TLS chỉ để bảo đảm email luôn được submit.

### 25.2. Secrets theo provider/identity

Một cơ chế naming có thể là:

~~~text
SMTP_PROVIDER_A_SECRET_REF
SMTP_PROVIDER_B_SECRET_REF
~~~

và ứng dụng resolve từ một secret provider đáng tin khi tạo adapter. Không truyền secret reference hoặc credential của provider qua public HTTP request. Tên biến trên là metadata ví dụ, không phải đường dẫn thực đến secret.

## 26. Observability cho TLS và secrets mà không lộ thông tin

Một triển khai production cần phân biệt **sự cố cấu hình**, **sự cố transport** và **kết quả gửi**. Metric không nên chứa raw recipient/secret.

### 26.1. Các nhóm metric hữu ích

| Metric logic | Mục đích |
| --- | --- |
| `mail_smtp_connection_failures_total` | Phát hiện DNS/connect/timeout |
| `mail_smtp_tls_handshake_failures_total` | Theo dõi vấn đề TLS |
| `mail_smtp_auth_failures_total` | Theo dõi credential/account failure |
| `mail_smtp_submission_outcomes_total` | Accepted, rejected, unknown |
| `mail_smtp_send_duration_seconds` | Giám sát độ trễ submission |
| `mail_outbox_oldest_due_age_seconds` | Đo backlog thời gian thực |
| `mail_secret_refresh_failures_total` | Phát hiện rotate/refresh lỗi |
| `mail_provider_circuit_open` | Provider bị tạm ngừng gọi |

Các metric này là **đề xuất do ứng dụng tự instrument**, không phải bảo đảm có sẵn trong Spring Boot Mail.

### 26.2. Labels nên có cardinality thấp

Ví dụ:

~~~text
profile = staging | prod
provider = primary | secondary
stage = connect | tls | auth | data | unknown
outcome = accepted | rejected | unknown
error_code = tls_handshake | invalid_credentials | timeout
~~~

Không gắn raw email recipient, password, token, subject hoặc UUID của mỗi message vào metric label. Những trường đó có thể làm lộ dữ liệu và tạo số series quá lớn.

### 26.3. Structured logs an toàn

~~~json
{
  "event": "smtp.connection.failure",
  "profile": "prod",
  "providerGroup": "transactional-primary",
  "stage": "TLS_HANDSHAKE",
  "safeErrorCode": "SMTP_TLS_HOSTNAME_MISMATCH",
  "deliveryId": "opaque-id",
  "attemptId": "opaque-id"
}
~~~

Với sự cố startup chưa có delivery ID, chỉ ghi startup incident/correlation ID. Đừng tự tạo “mail failed” record khi chưa có ý định gửi cụ thể.

### 26.4. Alert có thể hành động

| Alert | Điều tra ưu tiên |
| --- | --- |
| TLS handshake failures tăng sau deploy | CA truststore, endpoint hostname, TLS mode |
| SMTP AUTH failure 100% | Secret version, account disabled, mechanism |
| Provider timeout tăng | Network, quota, socket timeout, provider outage |
| Starttls capability biến mất | Endpoint/proxy, server config; không downgrade |
| Mail backlog tăng | Worker concurrency, provider quota, retry storm |
| Unknown outcomes tăng | Timeout sau DATA, state commit failure, reconciliation |
| Secret rotation failures | Secret mount/identity/RBAC, canary rollout |

Một lỗi TLS handshake lặp lại ở toàn bộ gửi production có thể cần alert khẩn cấp vì không thể gửi email, nhưng **không nên tự động tắt TLS để khôi phục lưu lượng**.

## 27. Runbook: production không gửi được vì TLS

### 27.1. Bước 1 — Xác định phạm vi

Hỏi:

- Có bao nhiêu worker/Pod bị ảnh hưởng?
- Chỉ một SMTP provider hay tất cả?
- Lỗi bắt đầu sau deploy, đổi certificate, DNS hay rotation?
- Đang dùng STARTTLS 587 hay implicit TLS 465?
- Có job nào đã bắt đầu SMTP DATA và outcome UNKNOWN không?
- Outbox có đang giữ intents bền vững hay request bị fail trực tiếp?

### 27.2. Bước 2 — Kiểm tra effective transport mode

~~~text
If port 587:
  mail.smtp.starttls.enable  = true
  mail.smtp.starttls.required = true
  mail.smtp.ssl.enable        = false
  mail.smtp.ssl.checkserveridentity = true

If port 465:
  mail.smtp.ssl.enable        = true
  mail.smtp.starttls.enable   = false
  mail.smtp.ssl.checkserveridentity = true
~~~

Nếu cấu hình đang dùng cổng 465 với chế độ STARTTLS, sửa mode/port đúng hướng dẫn provider; đừng giảm xác thực certificate.

### 27.3. Bước 3 — Xác minh certificate/truststore

Kiểm tra:

- Cert chain, thời hạn, SAN và hostname.
- DNS/SMTP relay IP và proxy TLS.
- Truststore của JVM đang chạy, không chỉ CA trên máy developer.
- TLS versions/ciphers có được cả client và server hỗ trợ.
- Nếu có CA nội bộ, nó đã được phân phối đúng image/version chưa.

Nếu cần sửa truststore, thực hiện bằng deployment artifact/trust store policy có kiểm soát. Không inject trust-all socket factory vào runtime để tránh sửa cấu hình chính xác.

### 27.4. Bước 4 — Sửa và canary

1. Sửa đúng nguồn cấu hình/certificate/endpoint.
2. Kiểm tra với một canary Pod hoặc staging tương đương.
3. Xác nhận TLS handshake, authentication và sender identity.
4. Quan sát error rate và queue age.
5. Rollout tới các instance còn lại.
6. Đối soát attempts `UNKNOWN` trước khi gửi lại.

### 27.5. Bước 5 — Ghi lại incident

Không chỉ ghi “đã bật lại SMTP”. Nên lưu:

~~~text
Incident:
  Time window
  Active profile
  Intended TLS mode
  Error stage and safe code
  Certificate/config root cause
  Number of pending/accepted/unknown deliveries
  Resolution deployment version
  Prevention test/alert added
~~~

Không chèn password hoặc raw MIME vào incident report.

## 28. Runbook: bí mật SMTP bị lộ hoặc nghi ngờ bị lộ

Khi một password hoặc token gửi SMTP có thể đã bị đưa vào Git, logs hay build artifact, **chỉ xóa dòng chứa password là chưa đủ**.

Các bước hợp lý theo chính sách incident response:

1. Xác định và hạn chế nơi secret đang bị lộ; không sao chép secret vào thêm nhiều hệ thống khi điều tra.
2. Revoke/rotate credential ở provider theo mức độ khẩn cấp.
3. Cập nhật secret store và rollout phiên bản mới tới workload có quyền.
4. Kiểm tra hoạt động bất thường của SMTP account, quota, gửi không được ủy quyền.
5. Xem log/CI artifacts/Git history có bản sao secret ở đâu và xử lý theo chính sách.
6. Thay thế credential ở các môi trường khác **nếu dùng chung**; không chỉ sửa một profile.
7. Xác minh TLS/authenticated submission với credential mới.
8. Cập nhật cảnh báo, secret scanning, quyền truy cập và bài học incident.

**Không in credential mới ra chat hoặc terminal** để “xác nhận nó đã đổi”. Chỉ kiểm tra phiên bản, trạng thái kết nối và kết quả test đã được phê duyệt.

### 28.1. Hậu quả của việc dùng chung secret giữa profiles

Nếu local/staging/prod dùng cùng tài khoản SMTP, việc lộ secret ở máy developer có thể ảnh hưởng production. Vì vậy mỗi profile cần account/permission riêng theo môi trường; các secret quan trọng nên có blast radius tối thiểu và khả năng revoke độc lập.

## 29. Bài tập thực hành theo từng bước

### Bài 1 — Gửi vào Mailpit ở local

**Chuẩn bị:** Java/Maven/Docker có sẵn, dự án gồm các file được minh họa ở trên.

1. Bật Mailpit qua Docker Compose.
2. Chạy Spring với `SPRING_PROFILES_ACTIVE=local`.
3. Bật riêng `APP_MAIL_SEND_DEMO_ON_STARTUP=true` cho một lần smoke test.
4. Mở web UI Mailpit và xác nhận subject, From, To, nội dung UTF-8.
5. Tắt demo runner và chạy lại để xác nhận ứng dụng không tự gửi thư.

**Kết quả mong đợi:** email nằm trong local sink; không cần credential staging/prod và không đi ra SMTP provider thật.

### Bài 2 — Bảo đảm prod luôn yêu cầu TLS

**Chuẩn bị:** Dùng giá trị test giả, không gọi SMTP thực.

1. Chạy test `MailProdConfigurationTest`.
2. Xác nhận hiệu lực của `starttls.enable/required` và hostname verification.
3. Thử override `mail.smtp.starttls.required=false` trong môi trường test.
4. Xác nhận `MailTlsConfigurationGuard` từ chối cấu hình.
5. Khôi phục cấu hình đúng.

**Kết quả mong đợi:** local cho phép sink plaintext có chủ đích; staging/prod **không thể** sử dụng transport yếu hơn policy mà vẫn vượt qua guard.

### Bài 3 — Thử cấu hình implicit TLS

**Chuẩn bị:** Một endpoint staging/sandbox cho phép implicit TLS 465, hoặc một SMTP fake được cấu hình TLS tương ứng.

1. Tạo cấu hình thay thế dựa trên `ssl.enable=true`.
2. Bỏ STARTTLS mode trong cùng endpoint.
3. Bật hostname verification.
4. Kiểm tra TLS handshake và certificate với môi trường được phép.
5. Ghi lại sự khác biệt khi cố dùng STARTTLS 587 properties với endpoint 465.

**Kết quả mong đợi:** phân biệt được handshake từ đầu và STARTTLS upgrade, không sửa lỗi bằng cách disable TLS verification.

### Bài 4 — Secret bị thiếu

**Chuẩn bị:** Một context test không kế thừa credential bên ngoài.

1. Chọn profile `prod`.
2. Cung cấp host/username/from giả nhưng không cấp password.
3. Khởi tạo context.
4. Xác nhận startup/config validation thất bại, không có submission.
5. Cấp lại một **test secret giả** và xác nhận binding pass mà không kết nối provider thật.

**Kết quả mong đợi:** không có mật khẩu mặc định cho production và không có phương án âm thầm bỏ AUTH.

### Bài 5 — Secret rotation

**Chuẩn bị:** Staging account có quyền rotate hoặc môi trường mô phỏng.

1. Ghi credential version đang được staging sử dụng (không ghi raw value).
2. Tạo version mới trong secret store.
3. Rollout canary/restart ứng dụng theo cơ chế triển khai.
4. Kiểm tra TLS/authentication bằng staging smoke test.
5. Thu hồi version cũ khi đủ điều kiện.
6. Thử tình huống canary thất bại và xác nhận rollback/halt policy.

**Kết quả mong đợi:** secret rotation không đòi sửa source code, không lộ credential và có thể phân biệt lỗi auth với lỗi network/TLS.

### Bài 6 — Test chống nhầm profile

1. Active `local,prod` đồng thời.
2. Xác nhận guard từ chối.
3. Chạy local với một `SPRING_MAIL_HOST` override sai trong test cô lập.
4. Xác nhận test/điều kiện deployment phát hiện endpoint không mong muốn.
5. Thêm kiểm soát profile/allowed host theo chính sách dự án.

**Kết quả mong đợi:** thứ tự ưu tiên property sources không trở thành con đường để test gửi email qua production relay.

### Bài 7 — Chẩn đoán certificate lỗi

1. Trong staging/fake TLS, dùng certificate không được JVM tin cậy hoặc hostname không khớp (không dùng production để cố gây lỗi).
2. Xác nhận TLS handshake thất bại khi verification bật.
3. Ghi safe error code và nested cause đã sanitize.
4. Sửa trustchain/hostname theo phương án đúng.
5. Test lại với `checkserveridentity=true`.

**Kết quả mong đợi:** sửa root cause certificate, không phải đặt `ssl.trust=*` hoặc tắt hostname verification.

## 30. Ma trận tiêu chí hoàn thành dự án thực hành

Một bài lab chỉ có kết quả tốt khi phân biệt được **đã cấu hình**, **đã thử**, **đã xác minh** và **đã triển khai**. Bảng sau là tiêu chí để người học tự thực hiện; nó không khẳng định dự án hiện tại đã vượt qua các bài test.

| Hạng mục | Cách kiểm tra | Kết quả cần đạt |
| --- | --- | --- |
| Local isolation | Mailpit nhận email trong profile local | Không cần credential hoặc Internet SMTP |
| Profile selection | Chạy local/staging/prod độc lập | Mỗi môi trường có endpoint/identity riêng |
| Configuration source | Xem config đã sanitize | Không có password trong repository |
| STARTTLS | Test effective properties prod | `enable=true`, `required=true` |
| Certificate verification | Test effective properties | `ssl.checkserveridentity=true` |
| Implicit TLS | Chạy test riêng profile 465 | `ssl.enable=true`, STARTTLS không bị bật nhầm |
| No silent downgrade | Fake SMTP không hỗ trợ STARTTLS | Kết nối lỗi thay vì gửi plaintext |
| No trust-all | Override `ssl.trust=*` | Bị policy từ chối |
| Missing secret | Context test không cấp password | Startup fail, không gửi |
| Conflicting profiles | `local,prod` active | Guard từ chối |
| Local auto-send | Runner chỉ active khi flag bật | Không gửi khi flag false/prod |
| Fake SMTP | Gửi test và xem MIME | Body/subject/encoding đúng |
| TLS handshake | Staging smoke test được phép | Cert/host/CA/protocol hợp lệ |
| SMTP auth | Staging credential riêng | AUTH thành công với quyền đã duyệt |
| Sender identity | Gửi từ address đã verified | Provider không reject From |
| Secret rotation | Test canary/rollout | Credential cũ được thu hồi có kiểm soát |
| Outage handling | Fake provider unreachable | Retry/backoff/incident hợp lý, không tự giảm TLS |
| Logging | Soát logs ở lab | Không có raw password/token/body |
| CI isolation | Unit/integration test | Không cần production SMTP secret |
| Deployment | Review Pod/Compose | Không bake secret vào container image |

### 30.1. Dữ liệu đầu vào của lab cần được cô lập

Chỉ dùng:

- Test recipients không phải địa chỉ khách hàng thật.
- SMTP sink hoặc account staging/sandbox được phép.
- Secrets giả trong unit tests.
- Template/body không chứa PII hoặc token thật.
- Credential production chỉ có mặt trong deployment được ủy quyền.

Không tự tạo một tác vụ “gửi thử” hàng loạt vào production để đo deliverability nếu chưa có quyền, quota và kế hoạch rõ.

### 30.2. Phân loại kết quả kiểm chứng

~~~text
CONFIG_ONLY
  The expected properties have been bound.

TLS_HANDSHAKE_VERIFIED
  Transport handshake and certificate checks succeeded.

SMTP_AUTH_VERIFIED
  Provider accepted authentication.

SMTP_SUBMISSION_ACCEPTED
  Provider accepted the test submission.

RECIPIENT_DELIVERY_OBSERVED
  Test mailbox/provider feedback observed delivery.
~~~

Các trạng thái này **không đồng nghĩa** với nhau. Ví dụ unit test property binding pass không có nghĩa network TLS handshake đã thành công; SMTP accepted cũng chưa phải inbox delivery.

## 31. Những lỗi thiết kế cần tránh

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Hardcode SMTP password trong YAML | Lộ qua Git/artifacts | Inject runtime từ secret store |
| Password Base64 trong Git | Base64 đảo ngược dễ dàng | Không commit bất kỳ biểu diễn secret nào |
| Dùng một SMTP account cho mọi profile | Tăng blast radius/nhầm quota | Account riêng theo environment |
| Local dùng endpoint production | Gửi mail thật khi test | SMTP sink cô lập/allowlist |
| Chỉ bật `starttls.enable` | Có thể không fail khi thiếu STARTTLS | `starttls.required=true` |
| Tắt hostname verification | Không xác minh đúng server | Bật `ssl.checkserveridentity=true` |
| `ssl.trust=*` | Trust mọi certificate | Cài CA/truststore đúng |
| Port 465 với STARTTLS 587 properties | Giao thức khởi tạo khác nhau | Dùng implicit TLS mode |
| Port 587 với `ssl.enable=true` | TLS handshake sai thời điểm | Dùng STARTTLS |
| Dùng SMTP AUTH nhưng không yêu cầu TLS | Credential có thể lộ | TLS fail closed trước AUTH |
| Tin mọi certificate trong staging | Staging không phản ánh prod/security | Sửa trust chain, test đúng |
| Commit `.env` thật | Secret lộ qua source control | Gitignore + secret scanning + rotate nếu lộ |
| Dùng Docker `ARG` cho production password | Secret có thể lọt vào build artifact/history | Runtime injection |
| Coi Kubernetes Secret Base64 là encryption | Chưa đảm bảo bảo mật at rest | RBAC, encryption at rest, secret manager |
| Secret mount nhưng không có configtree/loader | Ứng dụng nhận đường dẫn chứ không nhận password | Bind nội dung file qua property source |
| Nghĩ secret file đổi thì JavaMailSender tự refresh | Bean/config có thể giữ giá trị cũ | Restart/refresh có kiểm soát |
| Dump toàn bộ Spring properties để debug | Có thể lộ password/metadata | Structured sanitized diagnostics |
| Bật `mail.debug` ở prod | Protocol/recipient/auth metadata bị ghi log | Chỉ debug hạn chế khi được phép |
| Test chỉ kiểm tra `application-prod.yml` trên disk | Không thấy runtime overrides | Kiểm tra effective config/guard |
| Chạy `local,prod` cùng lúc | Precedence có thể tạo kết hợp sai | Một environment profile duy nhất |
| Tự gửi email trong ApplicationRunner prod | Restart tạo email thừa | Local-only opt-in demo |
| Gửi email test tới người dùng thật | Spam, quota, PII concerns | Staging/test recipients |
| Tăng retry vô hạn khi AUTH 535 | Có thể khóa tài khoản/đốt quota | Khắc phục credential/permission |
| Fallback sang plaintext để “cứu mail” | Làm yếu security policy | Hold/alert và sửa TLS |
| Retry sau mọi timeout SMTP | Có thể gửi trùng | Xem stage, UNKNOWN/reconciliation |
| Coi STARTTLS là end-to-end email encryption | SMTP chỉ bảo vệ từng kết nối | Threat model theo các relay |
| Coi SMTP accepted là inbox delivered | Đo sai mức thành công | Feedback/bounce tracking riêng |

## 32. Câu hỏi thường gặp

**“Profile nào nên là mặc định khi phát triển?”**  
Có thể dùng `local` do người phát triển bật rõ ràng. Với một dự án chú trọng bảo mật, không có environment profile thì nên fail config validation thay vì tự chọn SMTP production hoặc một relay mặc định không rõ.

**“Có nên đặt spring.profiles.active trong application.yml?”**  
Thường nên để runtime/deployment quyết định environment. Đặt active profile cố định trong file chung dễ làm local/CI/prod khác nhau theo cách khó kiểm soát.

**“Spring Boot có tự tìm application-prod.yml không?”**  
Có khi profile `prod` được kích hoạt theo cơ chế config data của Spring Boot. Các giá trị còn có thể bị override bởi command-line/env và property sources ưu tiên cao hơn.

**“Có thể bật local và prod cùng lúc không?”**  
Spring cho phép nhiều profiles, nhưng với bài này hai profile môi trường đều cấu hình SMTP endpoint/TLS/identity. Không nên kết hợp; guard từ chối để tránh precedence mơ hồ.

**“Khi dùng placeholder có cần ghi password mặc định không?”**  
Không với staging/prod. `${SMTP_PROD_PASSWORD:password}` có thể khiến ứng dụng dùng một mật khẩu yếu khi deployment thiếu secret. Hãy fail startup và sửa secret source.

**“Spring Boot có sẵn JavaMailSender không?”**  
`spring-boot-starter-mail` kết hợp auto-configuration có thể tạo `JavaMailSenderImpl` khi các điều kiện cấu hình phù hợp. Nếu project tự tạo bean khác thì cần kiểm tra cách các thuộc tính được áp dụng.

**“STARTTLS trên 587 đã mã hóa ngay từ byte đầu tiên chưa?”**  
Không. SMTP session bắt đầu bằng giao tiếp để thương lượng STARTTLS, rồi TLS handshake nâng cấp kết nối. `starttls.required=true` giúp fail nếu không nâng cấp được; implicit TLS 465 bắt đầu bằng handshake TLS.

**“Tại sao cần cả starttls.enable và starttls.required?”**  
`enable` cho phép client dùng STARTTLS; `required` buộc nó không tiếp tục khi STARTTLS không có/không thành công. Trong môi trường bảo mật, chỉ enable là chưa đủ.

**“mail.smtp.ssl.enable có cần true cho STARTTLS 587 không?”**  
Không. Với cấu hình phổ biến, `ssl.enable=false` cho 587 STARTTLS; `ssl.enable=true` cho 465 implicit TLS. Chọn theo provider endpoint.

**“Có thể dùng 587 với ssl.enable=true không?”**  
Nếu endpoint 587 chờ SMTP greeting/STARTTLS, client implicit TLS sẽ cố handshake ngay và thường lỗi. Chỉ dùng khi provider thực sự có contract khác.

**“checkserveridentity bảo vệ điều gì?”**  
Nó kiểm tra hostname của SMTP endpoint tương thích TLS certificate; cùng với CA chain validation giúp xác minh ứng dụng nói chuyện với đúng server, không chỉ một server có chứng chỉ bất kỳ.

**“Vì sao không dùng ssl.trust=* để test nhanh?”**  
Vì đó là trust-all, có thể che lỗi certificate/MITM. Dùng CA/truststore phù hợp và giữ hostname verification để test gần với production.

**“STARTTLS bảo đảm thư được mã hóa tới mailbox người nhận không?”**  
Không. Nó bảo vệ kết nối từ Spring client đến SMTP relay của bạn. Các relay tiếp theo có cơ chế riêng; nội dung email cũng có thể được lưu ở provider.

**“Có cần SMTP AUTH khi đã dùng TLS?”**  
Tùy provider. TLS bảo vệ connection; AUTH xác thực account. Nhiều SMTP submission providers cần cả hai, nhưng một relay nội bộ đã xác thực bằng cơ chế khác có thể có contract riêng.

**“SMTP password có phải đặt trong Dockerfile không?”**  
Không. Image nên build độc lập môi trường; runtime inject secret theo deployment.

**“Kubernetes Secret đã an toàn vì dùng base64 chưa?”**  
Chưa. Base64 không mã hóa. Cần RBAC, encryption at rest, hạn chế đọc API/process env và có thể tích hợp secret manager ngoài cluster.

**“Configtree đọc tên file hay nội dung file?”**  
Nó dùng tên file làm key cấu hình và nội dung file làm value, khi được import đúng. Nếu chỉ truyền một đường dẫn file vào biến env, Spring không tự đọc nội dung trừ khi có cơ chế tương ứng.

**“Tại sao sau khi rotate Kubernetes Secret, app vẫn dùng password cũ?”**  
Secret được inject vào environment thường không tự cập nhật cho process; còn mounted file thay đổi không đồng nghĩa bean JavaMailSender tự reload. Cần rollout/restart hoặc refresh mechanism có thiết kế.

**“Có thể dùng OAuth2 thay mật khẩu SMTP không?”**  
Có nếu provider hỗ trợ và client được cấu hình đúng AUTH mechanism/token lifecycle. Token vẫn là secret và vẫn cần TLS.

**“Test profile prod có cần secret thật không?”**  
Không để kiểm tra binding/policy. Dùng test placeholder giả, không gọi SMTP; chỉ staging smoke test được phê duyệt mới cần credential staging thực tế.

**“Muốn biết app có đang dùng đúng secret thì log giá trị được không?”**  
Không. Có thể đối chiếu version/identifier của secret, successful authentication ở môi trường được phép, và metadata sanitized.

**“Connection refused khác PKIX path building failed thế nào?”**  
Connection refused thường ở tầng kết nối/port; PKIX là vấn đề trust chain khi TLS handshake. Chúng cần hướng sửa khác nhau.

**“AuthenticationFailedException có thể do TLS sai không?”**  
Có thể một số provider từ chối AUTH khi TLS chưa bật, nhưng cũng có thể do sai password, account policy hoặc AUTH mechanism. Phải xem stage/cause và server response được sanitize.

**“Sửa 535 bằng cách thử password liên tục được không?”**  
Không nên. Có thể gây khóa tài khoản, tiêu hao quota và tạo alert. Kiểm tra credential version/account policy rồi thử có giới hạn.

**“Có nên gọi testConnection khi app khởi động?”**  
Tùy yêu cầu availability. Nếu provider outage, fail startup có thể không phù hợp với worker có durable outbox. Configuration validation, readiness và SMTP connectivity cần được định nghĩa riêng.

**“Gửi email qua TLS rồi bị spam có phải TLS sai?”**  
Không nhất thiết. Deliverability còn phụ thuộc SPF/DKIM/DMARC, reputation, nội dung, complaint/bounce, chính sách người nhận và provider.

**“Có thể dùng Spring Mail để gửi HTML/attachment trên cùng TLS config không?”**  
Có. TLS/auth ở transport; `MimeMessageHelper` tạo MIME. Dùng đúng multipart, encoding và nguồn attachment.

**“SMTP exception có nghĩa chắc chắn thư chưa gửi?”**  
Không. Sau DATA, client có thể mất phản hồi dù relay đã accepted. Cần mô hình `UNKNOWN` và reconciliation để tránh duplicate khi retry.

**“Cần đổi profile mỗi lần gửi một email không?”**  
Không. Profile thường là cấu hình deployment/environment. Nếu có nhiều SMTP providers trong một app, dùng adapter/registry với configuration riêng thay vì mutate active profile hoặc singleton sender theo request.

**“Thế nào là bài lab hoàn thành?”**  
Khi đã kiểm tra local sink, cấu hình staging/prod không có secret trong repo, TLS fail-closed, certificate validation, negative tests, rotation plan và đúng phạm vi kiểm chứng. Một unit test pass không đồng nghĩa provider thật đã delivered email.

## 33. Checklist trước khi đưa cấu hình SMTP lên production

### Cấu hình và profile

1. Chỉ một profile môi trường mail `prod` được chọn ở deployment production.
2. Không có `local` hoặc profile test đang active cùng `prod`.
3. Host/port được lấy từ approved provider configuration.
4. SMTP mode đúng endpoint: STARTTLS 587 hoặc implicit TLS 465.
5. STARTTLS dùng cả `enable=true` và `required=true`.
6. Implicit TLS dùng `ssl.enable=true` và không bật STARTTLS sai ngữ cảnh.
7. Hostname verification bật.
8. Không có `ssl.trust=*`, custom trust-all socket factory hoặc config vô hiệu hóa certificate validation.
9. Timeout kết nối, đọc và ghi có giới hạn được cân nhắc theo workload.
10. Các property overrides được kiểm tra sau khi Spring Boot bind, không chỉ nhìn YAML.

### Secret và identity

11. Không có password/token trong source code, YAML, Dockerfile hoặc build artifacts.
12. Secret được cấp từ runtime/secret manager với quyền tối thiểu.
13. Local, staging và prod có credential/account scope riêng.
14. Password/token không có fallback giá trị yếu khi thiếu config.
15. Secret mount/env mapping có tên đúng và được Spring đọc thành giá trị, không phải file path.
16. Có quy trình rotation/revoke và xác minh version.
17. Pod/service account chỉ được đọc secret cần thiết.
18. Logs/metrics/Actuator không tiết lộ credentials hay raw MIME.
19. From/envelope identity đã được provider cho phép; SPF/DKIM/DMARC được cấu hình và kiểm tra theo yêu cầu.
20. Nếu dùng OAuth2, token refresh và AUTH mechanism được thiết kế rõ.

### Cô lập và khả năng vận hành

21. Local/CI dùng SMTP sink hoặc fake server, không gọi production provider.
22. Staging có test recipients và credential riêng.
23. Không có runner/endpoint công khai gửi email test trên production.
24. Network egress tới SMTP endpoint được kiểm soát phù hợp.
25. Có metrics lỗi connect/TLS/AUTH, submission outcome và queue age nếu dùng worker.
26. Có alert cho lỗi cấu hình sau deploy hoặc rotation.
27. Có runbook certificate mismatch, credential revoke, provider outage.
28. Có chính sách fail-closed khi TLS negotiation thất bại.
29. Lỗi sau SMTP DATA không bị retry/fallback mù như chắc chắn chưa gửi.
30. Có giới hạn retry/backoff, xử lý business deadline và reconciliation theo kiến trúc gửi mail.

### Kiểm chứng

31. Test property binding của `application-prod.yml` và `application-staging.yml`.
32. Test negative: thiếu secret, TLS bị tắt, hostname verification bị tắt, hai profile cùng active.
33. Test implicit TLS riêng nếu hỗ trợ cổng 465.
34. Smoke test staging xác minh certificate, AUTH và sender identity.
35. Test MIME UTF-8/HTML/attachment qua fake SMTP khi ứng dụng dùng.
36. Test secret rotation canary và kiểm tra không còn credential cũ trong workload sau revoke.
37. Test Docker/Kubernetes environment/secret mount thực tế, không chỉ unit test trên laptop.
38. Ghi lại phạm vi đã xác minh: config, TLS, AUTH, SMTP accepted hoặc feedback; không đánh đồng chúng.

## 34. Sơ đồ kiến trúc và ranh giới tin cậy

~~~text
                  Source repository
                         |
                         v
                   Versioned config
                  application.yml
                   profile YAMLs
                  (NO credentials)
                         |
                         v
                  Immutable build
                         |
                         v
                  Runtime environment
                         |
          +--------------+-----------------+
          |              |                 |
          v              v                 v
      Local profile   Staging profile   Prod profile
          |              |                 |
          v              v                 v
     Mailpit sink    Staging secrets     Prod secrets
     no SMTP AUTH     secret manager      secret manager
     plaintext only      |                   |
     in isolation        |                   |
          |              v                   v
          |         STARTTLS required   STARTTLS required
          |         or implicit TLS     or implicit TLS
          |              |                   |
          +--------------+-------------------+
                         |
                         v
                   Spring Boot Mail
               JavaMailSenderImpl + config
                         |
                         v
                 TLS policy validation
                         |
                         v
                MailDemoService / worker
                         |
                         v
                SMTP network submission
                         |
              +----------+-----------+
              |                      |
              v                      v
         ACCEPTED               ERROR/UNKNOWN
              |                      |
              v                      v
      Delivery feedback       Error classification,
      processed separately    retry/reconciliation
~~~

### 34.1. Điều gì được bảo đảm ở mỗi lớp?

| Lớp | Điều được kiểm soát | Điều chưa được bảo đảm |
| --- | --- | --- |
| Spring profiles | Tập cấu hình dự kiến theo môi trường | Không tự ngăn mọi runtime override |
| Secrets/runtime injection | Không hardcode credential vào source | Không loại bỏ mọi quyền xem runtime environment |
| STARTTLS required | Không downgrade về plaintext khi không nâng cấp được | Không mã hóa end-to-end qua mọi relay |
| Hostname/certificate verification | Xác minh endpoint theo TLS trust model | Không xác minh sender domain hoặc mail delivery |
| SMTP AUTH | Kiểm tra account được phép truy cập relay | Không xác minh người nhận thực sự mở mail |
| JavaMailSender accepted | Quan sát được provider đã nhận submission | Không bảo đảm inbox placement hoặc read receipt |
| Outbox (nếu có) | Giữ ý định gửi bền vững cùng nghiệp vụ | Không biến SMTP thành exactly-once |
| Feedback processing | Nhận bounce/delivery events theo provider | Không luôn biết chính xác inbox placement |

### 34.2. Nguyên tắc triển khai cần nhớ

- **Profile** quyết định cấu hình mong muốn; **runtime secret source** cung cấp credential.
- **TLS mode** phải khớp endpoint: 587 STARTTLS với `required=true`, hoặc 465 implicit TLS.
- **Hostname verification** và trust chain phải đúng; đừng dùng trust-all.
- **Local SMTP sink** là ngoại lệ có chủ đích trong môi trường cô lập, không phải tiêu chuẩn staging/prod.
- **Production không có password mặc định** và không dựa vào masked logs như một lớp bảo vệ duy nhất.
- **CI test cấu hình** không cần production credential hoặc network submission.
- **Secret rotation** là một thay đổi runtime có lifecycle rõ, không chỉ cập nhật một file.
- **SMTP accepted** là kết quả submission chứ chưa phải inbox delivery.

## 35. Kết luận

**Cấu hình TLS và secret theo profile** là một bài thực hành nền tảng để biến chức năng Spring Framework Mail từ ví dụ chạy trên máy cá nhân thành một thành phần có thể triển khai an toàn. Cách tiếp cận nên bắt đầu từ việc chia `local`, `staging`, `prod` rõ ràng; cấu hình SMTP sink chỉ cho local; dùng secret runtime riêng cho từng environment; và bắt buộc STARTTLS/implicit TLS cùng certificate/hostname verification ở các kết nối SMTP thật.

Với Spring Boot, các file `application-<profile>.yml` giúp biểu diễn chính sách theo môi trường, `spring.mail.properties` truyền các thuộc tính TLS tới Jakarta Mail, còn `JavaMailSender` cho phép code gửi thư không phải biết password hoặc hostname cụ thể. Tuy vậy, **cấu hình đúng trên disk chưa đủ**: cần kiểm tra effective properties, quản lý nguồn secret, tránh property override sai, có kế hoạch rotation và thử nghiệm lỗi TLS/AUTH trước khi triển khai.

Đích đến của bài lab không phải chỉ là “một email đã gửi thành công”, mà là một cơ chế gửi có thể giải thích và kiểm chứng: **môi trường phát triển không đụng tài khoản production, môi trường thật không downgrade TLS, không có secret trong repository, lỗi thiếu secret bị chặn, và sự cố kết nối được chẩn đoán mà không phải giảm bảo mật**.
