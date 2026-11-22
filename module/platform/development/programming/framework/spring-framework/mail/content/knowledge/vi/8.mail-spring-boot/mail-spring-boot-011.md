# Quản lý secret bằng biến môi trường hoặc secret store

Trong **Spring Boot**, cấu hình `JavaMailSender` thường gồm SMTP host, port, username và password. Host/cổng chỉ là tham số kết nối; còn SMTP password, API key của nhà cung cấp email và token xác thực là **secret** vì chúng cấp quyền sử dụng một tài khoản hoặc dịch vụ. Nếu bị lộ, các giá trị này có thể bị lạm dụng để gửi thư trái phép, làm cạn quota, ảnh hưởng uy tín tên miền và gây sự cố vận hành.

Quản lý secret đúng cách gồm cả vòng đời: **cấp phát → lưu trữ → phân phối → sử dụng → thay đổi/rotation → thu hồi**. Hai phương án quen thuộc với Spring Boot là **biến môi trường** và **secret store**. Chúng có thể được kết hợp: secret store quản lý giá trị và quyền, còn biến môi trường hoặc tệp mounted giúp Spring Boot nạp cấu hình.

Bài học này hướng dẫn cấu hình Spring Framework Mail theo cả hai phương án, giải thích cách Spring Boot nhận secret, phân quyền, bảo vệ log, thay credential và xử lý sự cố.

## 1. Xác định secret trong hệ thống gửi mail

| Giá trị | Mức độ nhạy cảm | Vai trò |
|---|---|---|
| `spring.mail.host`, `spring.mail.port` | Thường không phải secret | Tham số mạng kết nối SMTP. |
| `spring.mail.username` | Có thể nhạy cảm | Định danh tài khoản hoặc thông tin SMTP do provider cấp. |
| **`spring.mail.password`** | **Secret** | Mật khẩu, app password hoặc token/API key dùng cho SMTP AUTH. |
| API key của HTTP email provider | **Secret** | Cấp quyền gọi API gửi email hoặc chức năng khác. |
| OAuth access/refresh token | **Secret** | Quyền truy cập có thể có thời hạn và cần làm mới. |
| DKIM private key, nếu tự ký email | **Secret** | Khóa ký phải được quản lý như private key; nhiều provider ký giúp ứng dụng. |
| `From`, `Reply-To` | Thường không | Danh tính gửi hiển thị và địa chỉ trả lời. |
| `mail.smtp.starttls.required` | Không | Chính sách bảo vệ kết nối. |

Mục tiêu là **tách credential khỏi source code**, kiểm soát ai có thể đọc và thay đổi credential, đồng thời tránh lộ qua log, quá trình deploy hoặc công cụ chẩn đoán.

Không nên coi tất cả tài khoản mail là giống nhau. Có provider yêu cầu **app password**, có provider cấp một SMTP API key, có provider hỗ trợ OAuth hoặc cơ chế xác thực khác. Cần chọn cách được hệ thống gửi mail thực tế hỗ trợ.

## 2. Secret đi vào JavaMailSender bằng đường nào?

```text
Admin / bộ phận vận hành / automation
                |
                v
      Secret manager hoặc cấu hình
      có kiểm soát của nền tảng
                |
       +--------+---------+
       |                  |
       v                  v
  Environment var    Mounted secret file
       |                  |
       v                  v
 Spring Environment  Spring Config Data
       |             (configtree:)
       +--------+---------+
                |
                v
         MailProperties
                |
                v
        JavaMailSenderImpl
                |
                v
         Jakarta Mail
                |
                | SMTP AUTH qua TLS
                v
           SMTP relay
```

Các lớp giải quyết những công việc khác nhau:

- **Secret store** là nguồn quản lý secret: policy, audit, version, rotation và cơ chế phân phối.
- **Environment variable** truyền giá trị vào một process. Nó không tự mã hóa hoặc cấp quyền truy cập chi tiết.
- **Spring Environment** hợp nhất các nguồn property theo thứ tự ưu tiên của Spring Boot.
- **`JavaMailSenderImpl`** được cấu hình từ properties và sử dụng credential trong quá trình gửi SMTP.
- **Jakarta Mail Transport** tạo kết nối, thương lượng TLS và xác thực theo cấu hình.

Một service gửi biên nhận chỉ nên biết đến `JavaMailSender`; nó không cần đọc mật khẩu bằng `System.getenv(...)` trong từng lời gọi.

## 3. Cách 1: biến môi trường và application.yml

Spring Boot hỗ trợ **externalized configuration**: cùng JAR có thể chạy ở local, staging, production với secret khác nhau.

### 3.1. Cấu hình SMTP với placeholder

Dùng `spring-boot-starter-mail` trong Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Ví dụ `application.yml` dành cho SMTP submission trên cổng 587 với STARTTLS:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
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
          timeout: 5000
          writetimeout: 5000
```

Khi chạy, Spring Boot resolve `${SMTP_USERNAME}` và `${SMTP_PASSWORD}` theo các nguồn cấu hình đã đăng ký, chẳng hạn biến môi trường của process. Đoạn YAML không có mật khẩu thực, nên có thể được quản lý cùng source code.

| Property | Chức năng |
|---|---|
| `mail.smtp.auth=true` | Dùng cơ chế xác thực SMTP theo provider. |
| `mail.smtp.starttls.enable=true` | Cho phép nâng cấp kết nối sang TLS. |
| `mail.smtp.starttls.required=true` | Yêu cầu STARTTLS phải thành công; tránh tiếp tục trong chế độ không được bảo vệ khi chính sách đòi TLS. |
| `mail.smtp.ssl.checkserveridentity=true` | Kiểm tra danh tính host dựa trên chứng chỉ TLS trong provider. |
| `mail.smtp.connectiontimeout` | Thời gian tối đa kết nối, tính theo mili giây. |
| `mail.smtp.timeout` | Thời gian tối đa chờ đọc phản hồi socket. |
| `mail.smtp.writetimeout` | Thời gian tối đa chờ ghi socket. |

Không nên đặt mật khẩu fallback trong cấu hình, ví dụ `${SMTP_PASSWORD:changeme}`. Khi production thiếu secret bắt buộc, hệ thống nên phát hiện và báo lỗi thay vì âm thầm sử dụng credential mặc định hoặc gửi không xác thực.

Nếu SMTP provider yêu cầu cổng 465 với **implicit TLS**, cần cấu hình `mail.smtp.ssl.enable=true` và cổng tương ứng. Không trộn tùy tiện thiết lập 465 và 587.

### 3.2. Cấp biến môi trường

Trên shell Bash ở môi trường phát triển, có thể dùng:

```bash
export SMTP_USERNAME="smtp-test-account@example.com"

# Đọc mật khẩu từ terminal mà không in ký tự lên màn hình.
read -r -s -p "SMTP password: " SMTP_PASSWORD
printf '\n'
export SMTP_PASSWORD

java -jar app.jar
```

Đây là ví dụ chạy local. Trong triển khai thật, nền tảng container, CI/CD hoặc orchestrator nên cấp giá trị từ nguồn quản lý secret, tránh viết mật khẩu rõ vào script hay lịch sử shell.

Spring Boot còn có thể nhận trực tiếp các property qua biến môi trường:

```text
SPRING_MAIL_HOST=smtp.example.com
SPRING_MAIL_PORT=587
SPRING_MAIL_USERNAME=<smtp-username>
SPRING_MAIL_PASSWORD=<smtp-password>
```

Quy tắc **relaxed binding** cho phép `SPRING_MAIL_PASSWORD` ánh xạ tới `spring.mail.password`. Khi dùng cách này có thể bỏ trường `username` và `password` khỏi YAML.

**Chọn một quy ước rõ ràng**: sử dụng `SMTP_PASSWORD` thông qua placeholder hoặc cấp `SPRING_MAIL_PASSWORD` trực tiếp. Nếu đồng thời có nhiều nguồn cho cùng property, cần hiểu nguồn nào có mức ưu tiên cao hơn và tránh giá trị mâu thuẫn.

### 3.3. JavaMailSender không cần biết cách lưu secret

```java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ReceiptMailService {

    private final JavaMailSender mailSender;

    public ReceiptMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReceipt(String recipient, String orderCode) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("receipts@example.com");
        message.setTo(recipient);
        message.setSubject("Xác nhận đơn hàng " + orderCode);
        message.setText("Đơn hàng " + orderCode + " đã được ghi nhận.");

        mailSender.send(message);
    }
}
```

Spring Boot cấu hình sender bằng property source phù hợp; Jakarta Mail sử dụng credential khi kết nối SMTP. Lớp nghiệp vụ không cần truyền secret qua nhiều service.

**Lưu ý:** `mailSender.send(...)` không có exception thường có nghĩa SMTP server đã tiếp nhận yêu cầu gửi ở chặng đó, chưa phải bằng chứng email đã đến Inbox.

### 3.4. Điểm mạnh và giới hạn của biến môi trường

Biến môi trường dễ áp dụng, không yêu cầu thư viện tích hợp riêng và thuận tiện khi nền tảng triển khai đã hỗ trợ inject secret. Tuy nhiên:

- Env var **không phải vault**. Process, công cụ giám sát hoặc tài khoản có quyền phù hợp có thể đọc nó.
- Secret có thể bị lộ qua log deploy, shell history, process/debug metadata, crash dump hoặc công cụ quản trị.
- Env var không tự cấp audit, version hoặc rotation.
- Đổi biến môi trường trên hệ thống triển khai không tự cập nhật giá trị đã được bean tải vào bộ nhớ.
- Việc gửi SMTP vẫn cần TLS, hạn mức và quản lý quyền trên provider.

Với nhiều ứng dụng nhỏ, env var vẫn là lựa chọn hợp lý **nếu nó được cấp từ một nguồn an toàn và có quy trình rotation**.

## 4. Cách 2: secret store

**Secret store** là dịch vụ quản lý dữ liệu nhạy cảm. Các ví dụ thường gặp gồm HashiCorp Vault, AWS Secrets Manager, Google Cloud Secret Manager, Azure Key Vault và các cơ chế secret của nền tảng triển khai.

| Khả năng | Ý nghĩa khi gửi email |
|---|---|
| IAM/policy | Chỉ mail-service hoặc worker được phép mới đọc SMTP credential. |
| Version | Quản lý bản hiện tại và bản mới khi rotation. |
| Audit | Theo dõi truy cập, thay đổi hoặc cấp quyền. |
| Mã hóa dữ liệu | Bảo vệ secret lúc lưu và truyền theo chính sách/năng lực nhà cung cấp. |
| Workload identity | Dùng danh tính Pod/VM/service để đọc secret thay vì nhúng thêm master password. |
| Rotation | Tạo, phân phối và thu hồi phiên bản credential có kiểm soát. |
| Phân tách môi trường | Staging không có quyền đọc credential production. |

Ba kiểu tích hợp phổ biến:

1. **Secret store → env var:** nền tảng deployment lấy secret rồi inject vào process; Spring Boot dùng như mục 3.
2. **Secret store → mounted file:** secret agent/orchestrator cung cấp tệp; Spring Boot nạp bằng `configtree:` hoặc integration khác.
3. **Spring Boot → secret store:** ứng dụng dùng Config Data integration, Spring Cloud Vault hoặc SDK/provider-specific integration để đọc trực tiếp bằng service identity.

Không phải dùng đủ cả ba. Quan trọng là xác định **nguồn sự thật**, quyền truy cập, cách cấp tới ứng dụng và cách refresh giá trị đã nạp.

## 5. Mounted secret với Spring Boot configtree

Spring Boot hỗ trợ `spring.config.import` dạng **`configtree:`**. Trong một thư mục cấu hình kiểu này, tên file tương ứng tên property và nội dung file tương ứng giá trị.

Giả sử container có hai tệp:

```text
/run/secrets/
  spring.mail.username
  spring.mail.password
```

File `application.yml` chỉ cần khai báo:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
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
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Khi khởi động, Spring nạp `spring.mail.username` và `spring.mail.password` từ các tệp được mount, rồi cấu hình sender. Không có secret thật trong source hay JAR.

Hai dạng import có tác dụng khác nhau:

- `configtree:/run/secrets/`: nguồn cấu hình bắt buộc; nếu thư mục không tồn tại, lỗi sẽ được báo trong quá trình startup.
- `optional:configtree:/run/secrets/`: cho phép thư mục vắng mặt; hữu ích nếu local dùng env nhưng production dùng mounted secrets. Vẫn phải kiểm tra credential bắt buộc ở production.

Cần chú ý quyền đọc file, whitespace/newline trong giá trị, thứ tự ưu tiên nếu env var ghi đè cùng key, và việc refresh khi nguồn secret thay đổi. **File được cập nhật không có nghĩa `JavaMailSenderImpl` đang chạy tự nhận mật khẩu mới.**

### 5.1. Ví dụ Kubernetes Secret volume

Với Kubernetes, Secret có thể được mount thành file, qua một phần `Deployment` tương tự:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mail-service
  template:
    metadata:
      labels:
        app: mail-service
    spec:
      containers:
        - name: app
          image: example/mail-service:1.0.0
          volumeMounts:
            - name: smtp-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: smtp-secrets
          secret:
            secretName: mail-smtp-credentials
            items:
              - key: username
                path: spring.mail.username
              - key: password
                path: spring.mail.password
```

Ví dụ giả định `mail-smtp-credentials` đã tồn tại với key `username` và `password`, được tạo qua quy trình quản lý secret có kiểm soát. Không commit manifest chứa credential thật.

**Base64 trong trường `data` của Kubernetes Secret chỉ là cách biểu diễn dữ liệu, không phải mã hóa bảo mật.** Cần xem xét RBAC, quyền API, encryption at rest khi được hỗ trợ/cấu hình, quyền Pod và volume mount. Ngay cả khi nền tảng có thể cập nhật nội dung volume, ứng dụng thường cần rolling restart hoặc cơ chế reload để sender sử dụng giá trị mới.

### 5.2. Khi nào mounted file phù hợp hơn env var?

- Nền tảng đã có secret volume, CSI driver hoặc secret agent.
- Muốn giới hạn quyền truy cập theo user/container và tệp.
- Không muốn credential xuất hiện trong environment của process.
- Muốn dùng một cơ chế cấu hình Spring Boot thống nhất giữa nhiều runtime.

Tệp mounted cũng phải được bảo vệ: process có quyền đọc vẫn có thể truy cập, và người có quyền vào container/volume có thể xem nó.

## 6. Đọc secret store trực tiếp bằng integration

Một số dự án sử dụng **Spring Cloud Vault**, Config Data integration của cloud provider hoặc SDK để đọc secret trực tiếp. Luồng minh họa:

```text
Spring Boot workload
       |
       | Workload identity
       v
Secret store authentication
       |
       | Policy cho phép đọc đúng path
       v
SMTP credential
       |
       v
Spring Environment / cấu hình sender
       |
       v
JavaMailSenderImpl
```

Khi chọn phương án này, cần trả lời:

1. **Xác thực vào secret store bằng gì?** Ưu tiên danh tính workload được quản lý (Kubernetes auth, cloud identity, v.v.) khi hệ thống hỗ trợ. Không hard-code token quản trị.
2. **Được đọc path nào?** Chỉ quyền đọc secret SMTP của service, không cấp quyền wildcard toàn bộ kho.
3. **Kho không truy cập được lúc startup thì sao?** Với secret bắt buộc, thường cần fail fast hoặc báo ứng dụng không sẵn sàng; không dùng mật khẩu fallback.
4. **Giá trị được cache bao lâu?** Cần tính đến độ trễ và khả năng gián đoạn của secret store.
5. **Rotation ảnh hưởng bean thế nào?** Nạp cấu hình lúc startup không tự bảo đảm sender đang chạy sẽ được refresh.
6. **Integration có lộ secret qua log/tracing không?** Cần xác định cách redaction và quyền xem telemetry.

Cú pháp dependency, `spring.config.import`, auth method và path cụ thể thay đổi theo phiên bản Spring Boot/Spring Cloud/provider. Phải dùng integration tương thích với phiên bản ứng dụng và chính sách kho đang chạy.

Ví dụ một cách tổ chức key ở secret store:

```text
prod/mail-service/smtp
    username = [protected value]
    password = [protected value]

staging/mail-service/smtp
    username = [separate value]
    password = [separate value]
```

Tên path chỉ minh họa ý tưởng, không phải cú pháp bắt buộc của một provider.

## 7. Tổ chức secret giữa local, staging và production

Mỗi môi trường nên có **credential và quyền truy cập độc lập**:

| Môi trường | Nguồn cấu hình phù hợp | Nguyên tắc |
|---|---|---|
| Local development | Env var cấp tạm thời, secret tool dành cho developer hoặc SMTP sandbox | Không dùng tài khoản gửi email production để thử nghiệm. |
| Automated tests | Mail server giả lập, fake SMTP hoặc test fixture | Không gửi thư thật đến người dùng. |
| Staging | Secret store hoặc injection riêng của staging | Phân tách tài khoản và hạn chế tập người nhận. |
| Production | Secret store/nền tảng deploy có service identity, audit và rotation | Credential thật, TLS bắt buộc và giám sát hoạt động. |

Ví dụ có thể chạy local với một SMTP test server trên `localhost:1025`, không cần credential hoặc TLS nếu đó là server test được cô lập:

```yaml
# application-local.yml - chỉ dùng với SMTP sandbox nội bộ
spring:
  mail:
    host: localhost
    port: 1025
    username: ""
    password: ""
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
            required: false
```

Đây **không phải cấu hình hợp lệ cho SMTP production**. Trong production, không vô hiệu hóa TLS/AUTH chỉ để tránh lỗi secret hoặc kết nối.

### 7.1. File .env có phải cơ chế Spring Boot mặc định không?

Một số công cụ triển khai có thể đọc `.env`, nhưng **Spring Boot không mặc nhiên đọc mọi file `.env` theo cách Docker Compose hoặc thư viện dotenv làm**. File chỉ có tác dụng nếu IDE, shell, container runtime hoặc một integration đã thực sự nạp các key thành environment/property source.

Nếu dùng `.env` cho local:

- Tạo `.env.example` chỉ gồm tên biến và placeholder, không có secret thật.
- Đưa `.env` vào `.gitignore`; đặt quyền truy cập máy phù hợp.
- Không copy file vào Docker image hoặc artifact.
- Không cho rằng `.gitignore` xóa được bí mật đã commit trong lịch sử Git.
- Khi secret lộ qua commit/log, phải **thu hồi hoặc rotation**, không chỉ xóa khỏi phiên bản hiện tại.

### 7.2. Inject từ Kubernetes Secret qua environment

Nếu không dùng `configtree:`, cũng có thể để Kubernetes đưa các giá trị vào env của container:

```yaml
# Trích đoạn cấu hình container trong Pod/Deployment
env:
  - name: SPRING_MAIL_USERNAME
    valueFrom:
      secretKeyRef:
        name: mail-smtp-credentials
        key: username
  - name: SPRING_MAIL_PASSWORD
    valueFrom:
      secretKeyRef:
        name: mail-smtp-credentials
        key: password
```

Đây là đoạn trích; nó phải nằm đúng bên trong định nghĩa container của một Pod. Các secret key đã được tạo trước đó. Spring Boot bind trực tiếp từ `SPRING_MAIL_USERNAME` và `SPRING_MAIL_PASSWORD` khi khởi động.

Đổi giá trị của Kubernetes Secret không làm thay đổi biến môi trường của **process đang chạy**. Thông thường cần rolling restart hoặc tái tạo Pod để process mới nhận giá trị mới.

## 8. Phân quyền secret theo service và kênh gửi

Nguyên tắc **least privilege**: mỗi workload chỉ đọc những secret cần dùng.

Ví dụ hệ thống tách email giao dịch và email marketing:

```text
secret/prod/mail/transactional
    └── chỉ transaction-mail-worker được đọc

secret/prod/mail/marketing
    └── chỉ campaign-mail-worker được đọc

secret/staging/mail/test
    └── chỉ staging-mail-service được đọc
```

Vì sao nên phân tách?

- Thu hồi credential marketing không buộc phải thay credential giao dịch.
- Dễ theo dõi nguồn truy cập và giới hạn quota/permission.
- Một worker bị xâm nhập không nhất thiết đọc được tất cả SMTP credential production.
- Mỗi kênh có thể dùng tài khoản, sending domain hoặc provider khác nhau.

Tuy nhiên, **hai bean `JavaMailSender` trong cùng một JVM không tạo ranh giới bảo mật mạnh**. Nếu process có quyền đọc cả hai secret, code có quyền trong process có thể truy cập cả hai. Khi cần cách ly chặt, tách workload và service identity.

Ngoài quyền đọc từ secret store, tài khoản SMTP/API key cũng nên được cấp **quyền gửi tối thiểu** mà provider hỗ trợ. Nếu có scope riêng, không cấp quyền quản trị account khi ứng dụng chỉ cần gửi thư.

## 9. Rotation: thay SMTP credential an toàn

**Rotation** nghĩa là thay secret cũ bằng secret mới, rồi thu hồi secret cũ. Một ví dụ thuận lợi là provider cho phép tồn tại đồng thời hai credential trong giai đoạn chuyển đổi:

```text
T0  App instance A/B/C dùng credential v1
 |
 v
T1  Tạo credential v2 ở SMTP provider
 |
 v
T2  Lưu v2 vào secret store
 |
 v
T3  Rolling restart / refresh từng instance
 |   để sender sử dụng v2
 |
 v
T4  Kiểm tra AUTH, gửi test, quan sát lỗi
 |
 v
T5  Thu hồi credential v1
```

Các bước vận hành:

1. **Cấp credential mới** có quyền đúng phạm vi và cập nhật secret store theo phiên bản.
2. **Triển khai từng nhóm instance** để chúng nhận credential mới; tránh làm gián đoạn toàn bộ luồng gửi nếu có thể.
3. **Xác minh kết nối/xác thực và gửi thư thử** bằng các chỉ số phù hợp, không in credential ra log.
4. **Kiểm tra không còn workload dùng v1** và thu hồi v1.
5. **Theo dõi lỗi AUTH và queue gửi thư** sau chuyển đổi.
6. Ghi nhận metadata của rotation như thời điểm, người/hệ thống thực hiện và phiên bản; không lưu giá trị secret trong báo cáo.

Không phải SMTP provider nào cũng cho phép tạo hai credential hoạt động đồng thời. Nếu không hỗ trợ, cần thiết kế thời điểm chuyển đổi hoặc chuyển tài khoản theo giới hạn của provider. Khi credential đã lộ, ưu tiên thu hồi khẩn cấp theo mức độ rủi ro, thay vì chờ hết lịch rotation định kỳ.

### 9.1. Vì sao thay secret store chưa làm JavaMailSender dùng mật khẩu mới?

`JavaMailSenderImpl` thường nhận username/password khi bean được tạo hoặc cấu hình. Sau đó:

- Secret store có thể đã lưu **v2**.
- Secret file mounted có thể đã chứa **v2**.
- Bean và SMTP transport đang chạy vẫn có thể sử dụng **v1**.

**Cập nhật nguồn dữ liệu** và **làm mới cấu hình trong process** là hai hành động khác nhau. Có thể rolling restart, tái tạo sender bean hoặc dùng một cơ chế refresh động được thiết kế rõ. Nếu refresh trực tiếp, cần chú ý lời gọi gửi đang chạy, kết nối đã xác thực và tính nhất quán trong nhiều worker.

Đừng chỉ đưa `@RefreshScope` vào một bean rồi mặc định mọi nguồn secret đều có khả năng phát sự kiện refresh hoặc tất cả kết nối SMTP sẽ tự đổi credential.

### 9.2. Nếu credential hết hạn giữa lúc gửi?

Một job có thể đã được lấy khỏi queue và gặp lỗi `AUTH` vì secret cũ bị thu hồi. Nên:

- Phân loại lỗi xác thực riêng với lỗi địa chỉ người nhận.
- Không retry liên tục bằng credential đã bị server từ chối.
- Đưa job về trạng thái cần retry hoặc chờ khôi phục theo chính sách, đồng thời cảnh báo vận hành.
- Sau khi ứng dụng dùng secret mới, cho phép xử lý lại những job phù hợp.
- Nếu timeout xảy ra **sau khi SMTP server có thể đã nhận toàn bộ `DATA`**, kết quả gửi có thể chưa xác định; retry có thể gây thư trùng.

Quản lý secret không thay thế outbox, message queue hoặc chính sách gửi lại có kiểm soát.

## 10. Bảo vệ secret khi ứng dụng đang chạy

Ngay cả khi mật khẩu không còn nằm trong Git, nó vẫn có thể bị lộ trong runtime.

| Nơi dễ lộ | Ví dụ | Hướng giảm rủi ro |
|---|---|---|
| Process arguments | `--spring.mail.password=...` | Tránh truyền secret trực tiếp qua command-line argument. |
| Shell/script | `export SMTP_PASSWORD=mat-khau-that` trong script commit | Dùng injection từ nền tảng hoặc terminal input an toàn khi local. |
| Log startup và exception | In `MailProperties`, `Environment`, token hoặc payload | Chỉ log loại lỗi, mã sự kiện, hostname và trạng thái, không log secret. |
| Spring Boot Actuator | `/actuator/env`, `/actuator/configprops` | Giới hạn endpoint và quyền truy cập; không chỉ dựa vào masking mặc định. |
| CI/CD | Deploy log, build artifact, biến bị echo | Sử dụng secret masking, giới hạn quyền xem và thời gian lưu. |
| Container/JVM dump | Heap dump, process info, debug tool | Giới hạn người được truy cập, mã hóa/lưu trữ và retention phù hợp. |
| Git/Docker image | `application-prod.yml` chứa password | Không commit hoặc bake giá trị thật vào image. |
| Email header/body | Gắn API key vào `Message-ID` hoặc custom header | Không truyền secret trong nội dung email hoặc header. |

**Log đủ để chẩn đoán** có thể là:

```text
mail_channel=transactional
smtp_host=smtp.example.com
smtp_port=587
event_id=evt-1028
attempt=1
result=AUTH_FAILED
duration_ms=410
```

**Không log**:

```text
smtp_password=...
api_key=...
AUTH PLAIN <encoded-credentials>
secret_store_token=...
```

Một số phiên bản Spring Boot có cơ chế sanitize các thuộc tính nhạy cảm khi hiển thị, nhưng phải kiểm soát cả quyền truy cập Actuator và các log do ứng dụng, thư viện hoặc hạ tầng tự tạo. Debug Jakarta Mail có thể chứa metadata nhạy cảm; chỉ bật khi cần, trong môi trường kiểm soát, và không công bố transcript giao thức nguyên trạng.

## 11. SMTP TLS bảo vệ credential trên đường truyền

Secret store bảo vệ việc lưu và phân phối, nhưng **SMTP AUTH vẫn cần kết nối được bảo vệ**. Hai mô hình phổ biến:

**Cổng 587 với STARTTLS:**

```yaml
spring:
  mail:
    port: 587
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
```

**Cổng 465 với TLS ngay từ đầu:**

```yaml
spring:
  mail:
    port: 465
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
```

Không tự hạ xuống kết nối không mã hóa hoặc tắt kiểm tra chứng chỉ để “gửi được thư”. Cấu hình thực tế cần tương thích host/cổng/chứng chỉ do nhà cung cấp công bố.

Ngoài kết nối, cấu hình gửi thư cần xem xét quyền gửi của account, xác thực tên miền và SPF, DKIM, DMARC. **Bảo vệ mật khẩu** và **bảo đảm thư được hệ thống nhận tin cậy** là hai công việc có liên quan nhưng khác nhau.

## 12. Kiểm tra kết nối mà không in ra secret

Có thể kiểm tra kết nối SMTP bằng `JavaMailSenderImpl.testConnection()` trong môi trường phù hợp. Phương thức này giúp phát hiện một số lỗi host, TLS hoặc xác thực; nó không gửi một email test hoàn chỉnh và **không chứng minh thư đã vào Inbox**.

Ví dụ:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component
public class SmtpConnectionProbe {

    private final JavaMailSenderImpl sender;

    public SmtpConnectionProbe(JavaMailSenderImpl sender) {
        this.sender = sender;
    }

    public boolean canConnect() {
        try {
            sender.testConnection();
            return true;
        } catch (MessagingException ex) {
            // Có thể phát cảnh báo theo loại lỗi, không log mật khẩu.
            return false;
        }
    }
}
```

Đoạn này giả định ứng dụng có một bean `JavaMailSenderImpl` phù hợp. Nếu có nhiều sender, hãy chỉ định bean bằng `@Qualifier` hoặc tạo probe riêng theo channel. Tránh gọi liên tục để health check với tần suất cao, vì việc tạo kết nối/xác thực có chi phí và có thể chịu rate limit.

Khi có lỗi, cần phân biệt:

| Dấu hiệu | Nhóm nguyên nhân cần xem xét |
|---|---|
| Không resolve được SMTP host | DNS/cấu hình host hoặc mạng. |
| Connection refused/timeout | Port, firewall, relay, timeout. |
| TLS handshake lỗi | Cổng/cơ chế TLS, chứng chỉ, trust/hostname. |
| `535 Authentication failed` | Credential cũ, account bị khóa, policy AUTH, rotation chưa cập nhật bean. |
| `4xx` tạm thời | Quota, rate limit hoặc tình trạng SMTP server. |
| `5xx` ở người nhận | Chính sách gửi hoặc địa chỉ người nhận, không nhất thiết liên quan secret. |

Không bao giờ khắc phục lỗi bằng cách log toàn bộ password để “xem ứng dụng đang đọc đúng hay không”.

## 13. Chọn env var hay secret store?

| Tiêu chí | Biến môi trường | Secret store |
|---|---|---|
| Thiết lập | Đơn giản, Spring Boot hỗ trợ trực tiếp. | Cần hạ tầng/integration và service identity. |
| Lưu trữ có chính sách | Phụ thuộc nguồn đã inject biến. | Thường có policy, audit và version theo nền tảng. |
| Quyền truy cập | Chủ yếu theo process/host/deployment. | Có thể chi tiết theo workload và secret path. |
| Rotation | Cần thay nguồn cấp và làm mới process/bean. | Có thể quản lý version/rotation nhưng vẫn cần refresh ứng dụng. |
| Phát triển local | Thuận tiện. | Có thể cần thêm bước cấp quyền/xác thực. |
| Nhiều service, nhiều môi trường | Cần orchestrator quản lý phân phối. | Dễ quản trị tập trung khi policy được thiết kế tốt. |
| Rủi ro nếu cấu hình sai | Lộ qua command/log/metadata. | IAM quá rộng, token bootstrap bị lộ, refresh sai. |

**Gợi ý lựa chọn theo nhu cầu:**

- **Local và demo:** biến môi trường với SMTP sandbox, không chứa password thật trong repo.
- **Production trên nền tảng hỗ trợ secret injection:** dùng secret manager của nền tảng cấp env/file; Spring Boot bind bình thường.
- **Nhiều ứng dụng và credential quan trọng:** secret store có identity, audit và rotation rõ ràng.
- **Credential cần cập nhật liên tục:** thiết kế tích hợp và refresh thực sự, thay vì giả định Config Data tự cập nhật bean.

Có thể dùng **secret store làm nguồn dữ liệu gốc** và **env var/configtree làm phương thức phân phối**. Không cần chọn một rồi loại bỏ phương án còn lại.

## 14. Xử lý khi nghi ngờ lộ SMTP credential

Giả sử API key hoặc password xuất hiện trong commit Git, log CI/CD hay ticket hỗ trợ. Những bước cần thực hiện:

1. **Xác định phạm vi:** credential thuộc account/môi trường nào, có quyền gì và đã xuất hiện ở đâu.
2. **Thu hồi hoặc rotation:** tạo giá trị mới và vô hiệu hóa giá trị bị lộ theo mức độ khẩn cấp.
3. **Cập nhật nguồn secret an toàn:** đưa phiên bản mới vào secret store hoặc cơ chế injection.
4. **Triển khai lại ứng dụng:** restart/refresh để sender sử dụng credential mới; theo dõi lỗi AUTH và độ trễ queue.
5. **Rà soát lạm dụng:** kiểm tra hoạt động gửi bất thường, quota, log từ SMTP provider và các cảnh báo liên quan.
6. **Giới hạn bản sao:** xử lý secret có thể tồn tại trong lịch sử Git, artifact, log và dữ liệu hỗ trợ theo quy trình.
7. **Ngăn tái diễn:** bổ sung secret scanning, quản lý quyền, review cấu hình và giới hạn ai có thể xem log/CI.

**Xóa một dòng khỏi commit mới không làm credential đã lộ trở nên an toàn.** Thu hồi/rotation là hành động bắt buộc khi có nguy cơ bị sử dụng trái phép.

## 15. Những hiểu lầm thường gặp

**“Đưa password vào biến môi trường là đã mã hóa password.”** Sai. Env var là nơi process nhận giá trị; cần kiểm soát nơi lưu nguồn và quyền truy cập runtime.

**“Kubernetes Secret có Base64 là đã được mã hóa bảo mật.”** Sai. Base64 là mã hóa biểu diễn, có thể giải mã dễ dàng; bảo vệ at rest, RBAC và identity là các cấu hình riêng.

**“Đã dùng Vault thì không cần TLS SMTP.”** Sai. Vault bảo vệ việc lưu và phân phối, còn TLS bảo vệ thông tin xác thực trên kết nối SMTP.

**“Đổi secret ở store là mọi JavaMailSender dùng ngay giá trị mới.”** Sai. Nhiều sender được bind lúc startup và cần cơ chế refresh/restart.

**“Mật khẩu không nằm trong YAML nên log ra cũng không sao.”** Sai. Log/trace/artifact cũng có thể bị xem hoặc lưu lâu dài.

**“Có một SMTP account production cho tất cả service là cách tối ưu.”** Có thể tiện lúc đầu nhưng tăng phạm vi ảnh hưởng khi credential lộ và khó audit/thu hồi.

**“Nếu thiếu password thì cho phép gửi không AUTH để ứng dụng vẫn chạy.”** Không phù hợp khi SMTP provider yêu cầu xác thực. Nên phát hiện lỗi rõ, không âm thầm hạ tiêu chuẩn bảo mật.

**“Secret store tự giải quyết gửi email trùng hoặc bị mất.”** Sai. Độ bền yêu cầu gửi, retry và idempotency thuộc thiết kế worker/outbox, không phải chức năng của kho secret.

## 16. Bài tập thực hành

### Bài 1 — Cấp credential qua biến môi trường

Tạo cấu hình `spring.mail.*` dùng `${SMTP_USERNAME}` và `${SMTP_PASSWORD}`. Cấp hai biến qua shell hoặc IDE và gửi email đến SMTP sandbox.

Thử chạy khi thiếu `SMTP_PASSWORD` và quan sát lỗi cấu hình hoặc gửi. Giải thích vì sao không thêm mật khẩu mặc định vào code để tránh lỗi này.

### Bài 2 — Chuyển từ env sang configtree

Giả sử Pod có:

```text
/run/secrets/spring.mail.username
/run/secrets/spring.mail.password
```

Viết `spring.config.import` cần thiết. Giải thích khi nào dùng `configtree:` và khi nào dùng `optional:configtree:`. Nêu cách giới hạn quyền đọc file và quy trình làm mới sender nếu secret thay đổi.

### Bài 3 — Tách secret giữa transactional và marketing

Một hệ thống có hai worker gửi email với nhu cầu và quota khác nhau. Thiết kế hai secret path và hai service identity, chỉ ra điều kiện nào khiến việc tạo hai bean trong cùng process vẫn chưa tạo được ranh giới bảo mật mạnh.

### Bài 4 — Rotation trong nhiều instance

Ba instance Spring Boot đang dùng SMTP credential v1. Nhà cung cấp cho phép tạm thời dùng v1 và v2 song song. Hãy lập trình tự: tạo v2, cập nhật store, rolling restart, xác minh AUTH/gửi test, thu hồi v1, theo dõi lỗi sau chuyển đổi.

### Bài 5 — Chẩn đoán lỗi đúng tầng

Ứng dụng đã kết nối được nhưng SMTP báo `535 Authentication failed`. Liệt kê những việc cần kiểm tra mà không in ra mật khẩu: secret version đang được deployment cấp, thứ tự ưu tiên property, pod đã restart chưa, account/role còn hiệu lực không, provider có thay cơ chế AUTH hay không.

### Bài 6 — Phân loại dữ liệu

Cho các giá trị `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_API_KEY`, `From`, `DKIM_PRIVATE_KEY` và `mail.smtp.starttls.required`. Xác định giá trị nào phải quản lý như secret, giá trị nào thuộc cấu hình thông thường; giải thích từng lựa chọn.

## 17. Tổng kết

Trong Spring Boot Mail, **biến môi trường** giúp tách SMTP credential khỏi source code; **secret store** hỗ trợ quản lý quyền, audit, version và rotation. Spring có thể nhận giá trị từ biến môi trường, tệp `configtree:` hoặc integration với secret manager. Dù chọn cách nào, `JavaMailSender` vẫn chỉ cần được cấu hình và sử dụng qua API gửi email quen thuộc.

Cần bảo vệ toàn bộ vòng đời secret: cấp đúng quyền, không ghi mật khẩu vào Git/log, dùng TLS đúng với SMTP provider, giới hạn truy cập runtime, thiết kế rotation cùng restart/refresh bean và thu hồi credential bị lộ. **Giữ password ra khỏi `application.yml` là bước đầu; an toàn thực tế phụ thuộc cách ứng dụng và hạ tầng quản lý secret từ lúc cấp đến lúc thu hồi.**

