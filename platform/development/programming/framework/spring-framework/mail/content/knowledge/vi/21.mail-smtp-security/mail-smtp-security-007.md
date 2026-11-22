# Bảo vệ secret trong cấu hình

## 1. Vì sao cấu hình SMTP là dữ liệu nhạy cảm?

Trong **Spring Framework Mail**, ứng dụng thường dùng `JavaMailSender` để gửi email qua một SMTP server. Bên cạnh host, port và chế độ TLS, client có thể cần thông tin xác thực như username/password, app password hoặc access token OAuth 2.0. Những giá trị này là **secret** vì chúng cho phép một tiến trình hoặc người khác sử dụng quyền gửi mail của tài khoản hay tổ chức.

Ví dụ một cấu hình Spring Boot đơn giản:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: notifications@example.net
    password: some-password
~~~

Nếu `some-password` là credential thật, đặt trực tiếp trong `application.yml` rồi commit lên Git là một rủi ro lớn: bất cứ ai đọc được repository, bản build, artifact hoặc bản sao lưu đều có thể tiếp cận secret. Không chỉ source code, secret còn có thể xuất hiện trong command line, log debug, CI/CD output, container image, môi trường runtime hoặc dashboard quản trị.

Một secret bị lộ có thể dẫn tới:

- Gửi spam/phishing bằng tài khoản hợp lệ của tổ chức.
- Vượt quota SMTP hoặc khiến tài khoản bị khóa, ảnh hưởng email giao dịch.
- Truy cập mailbox hoặc dịch vụ khác nếu credential được tái sử dụng.
- Rò rỉ danh sách người nhận, nội dung thông báo và thông tin vận hành.
- Khó điều tra vì hoạt động của kẻ tấn công trông giống kết nối ứng dụng.

Mục tiêu của bài học là cấu hình `JavaMailSender` sao cho **ứng dụng có thể sử dụng secret khi cần nhưng không lưu, phát tán hoặc hiển thị nó ở nơi không được phép**.

> **Nguyên tắc cốt lõi:** Code và artifact nên chứa **tên cấu hình**, không chứa **giá trị bí mật**. Secret được cấp phát ở runtime qua một kênh được kiểm soát; chỉ thành phần cần gửi mail được quyền đọc.

## 2. Phân biệt thông tin cấu hình và secret

Không phải mọi thuộc tính SMTP đều cần bảo vệ ở mức giống nhau:

| Thuộc tính | Ví dụ | Có phải secret? | Khuyến nghị |
| --- | --- | --- | --- |
| SMTP host | `smtp.example.net` | Thường không | Có thể đặt trong cấu hình theo môi trường |
| Port | `587` hoặc `465` | Không | Khai báo tường minh |
| STARTTLS/SSL | `true` | Không | Bắt buộc theo policy an toàn |
| SMTP username | `mailer@example.net` | Thường là dữ liệu vận hành nhạy cảm | Hạn chế hiển thị; có thể cấp cùng secret |
| SMTP password/app password | Chuỗi do provider cấp | **Có** | Không commit, không log, cấp ở runtime |
| OAuth access token | Bearer token ngắn hạn | **Có** | Quản lý vòng đời, scope và thời hạn |
| OAuth refresh token/client secret | Credential để lấy token mới | **Có** | Secret manager/identity provider |
| TLS private key (nếu dùng mTLS) | Private key | **Có** | Keystore/secret store, quyền truy cập chặt |
| CA certificate/public certificate | Public cert | Thường không | Có thể phân phối như cấu hình tin cậy |

Một username SMTP đôi khi không đủ để đăng nhập, nhưng vẫn nên xem là thông tin vận hành cần kiểm soát vì nó có thể hé lộ tài khoản gửi hoặc hạ tầng nội bộ. Không in cả object cấu hình chỉ vì nghĩ rằng username không phải password.

### 2.1. App password không phải password tài khoản chính

Nếu nhà cung cấp hỗ trợ **app password**, hãy dùng credential riêng cho ứng dụng với phạm vi phù hợp, thay vì tài khoản cá nhân hoặc mật khẩu đăng nhập chung. Khi cần thu hồi, tổ chức có thể vô hiệu hóa app password mà không buộc thay mật khẩu của tất cả người dùng.

Tuy nhiên, app password vẫn là một **secret toàn quyền theo phạm vi cấp cho nó**. Không được để nó xuất hiện trong Git, Docker image hoặc log chỉ vì tên có chữ “app”.

### 2.2. OAuth2 không làm token trở thành dữ liệu công khai

Một số SMTP provider hỗ trợ xác thực dựa trên OAuth2/XOAUTH2. Khi đó password tĩnh có thể được thay bằng access token có thời hạn và phạm vi quyền. Token vẫn là một credential: không được log, commit hay gửi qua kênh không an toàn. Nếu dùng refresh token hoặc client secret để lấy token mới, những giá trị đó cũng phải được bảo vệ.

Cách bật cơ chế xác thực và lấy token phụ thuộc provider/Jakarta Mail implementation. Không được giả định chỉ đổi `spring.mail.password` sang chuỗi token là mọi provider tự hoạt động với OAuth2.

## 3. Những vị trí dễ làm lộ secret

Secret có thể bị lộ từ nhiều đường đi, không chỉ từ `application.yml`:

| Nơi lộ | Ví dụ sai | Vấn đề |
| --- | --- | --- |
| Source control | Commit `spring.mail.password` thật | Secret lưu trong lịch sử Git và các bản clone |
| File cấu hình đóng gói | Tạo `application-prod.yml` chứa password khi build | Secret đi vào JAR/image/artifact |
| Command line | `--spring.mail.password=...` | Có thể hiện trong danh sách tiến trình, job log |
| Docker build | `ARG SMTP_PASSWORD` rồi ghi vào layer | Có thể lộ trong build history/layer/cache |
| CI pipeline | In biến hoặc bật shell tracing | Secret xuất hiện ở log/artifact |
| Log ứng dụng | `log.info("{}", mailProperties)` | In toàn bộ object gồm password |
| SMTP debug | Bật xác thực debug tùy tiện | Provider/debug output có thể tiết lộ thông tin nhạy cảm |
| Actuator | Expose `/env`, `/configprops` quá rộng | Người không có quyền có thể nhìn thấy cấu hình |
| Runtime environment | Công cụ inspect/process diagnostics | Biến môi trường có thể được người có quyền host/container đọc |
| Backup, support bundle | Sao chép file secret cùng log | Secret bị nhân bản ngoài kênh quản lý |
| Chat/ticket | Dán credential thật để nhờ hỗ trợ | Mở rộng phạm vi người có thể đọc |

Chống rò rỉ phải xem xét cả **quá trình phát triển, build, deploy, chạy ứng dụng và xử lý sự cố**.

## 4. Cách không nên làm: hard-code credential

Ví dụ cần tránh:

~~~java
@Configuration
class MailConfiguration {

    @Bean
    JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.net");
        sender.setPort(587);
        sender.setUsername("notifications@example.net");
        sender.setPassword("a-real-secret-here"); // KHÔNG NÊN
        return sender;
    }
}
~~~

Credential trong source có thể bị:

- Commit lên Git hoặc đẩy lên remote.
- Sao chép sang nhánh feature, fork, mirror, backup.
- Đưa vào source JAR, bytecode hoặc các artifact phân phối.
- Hiển thị khi review code hoặc chụp màn hình.

Đổi thành một chuỗi Base64 hoặc mã hóa bằng khóa cũng viết ngay trong repository **không giải quyết được vấn đề**. Base64 chỉ là encoding, không phải encryption; nếu chương trình có đủ khóa giải mã hard-code trong cùng artifact thì người đọc artifact cũng có thể tìm cách giải mã.

Đặt một giá trị mẫu rõ ràng để minh họa là chấp nhận được trong tài liệu, nhưng **không dùng credential thật trong snippet, fixture hay commit test**.

## 5. Cấu hình Spring Boot bằng biến môi trường

Cách cơ bản để tách secret khỏi source là dùng placeholder trong `application.yml`:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Trong ví dụ này:

- `SMTP_USERNAME` và `SMTP_PASSWORD` là **tên** biến môi trường, không phải giá trị.
- Spring resolve placeholder khi tạo cấu hình ứng dụng.
- `spring.mail.username` và `spring.mail.password` được dùng bởi cấu hình mail sender khi Spring Boot mail auto-configuration hoạt động.
- Chỉ host/port và chính sách TLS/timeout được lưu trực tiếp trong YAML.

Ví dụ khởi chạy local từ một shell đã được cấp biến môi trường qua kênh an toàn:

~~~text
SMTP_USERNAME = <giá trị được cấp ngoài repository>
SMTP_PASSWORD = <giá trị được cấp ngoài repository>
~~~

Không đưa giá trị thật vào script commit, file README hoặc câu lệnh terminal được copy vào issue. Tên biến có thể công khai; giá trị secret phải được cấp ở thời điểm chạy.

### 5.1. Không đặt mật khẩu mặc định trong placeholder

Tránh:

~~~yaml
spring:
  mail:
    password: ${SMTP_PASSWORD:hardcoded-fallback-secret}
~~~

Cú pháp `${NAME:default}` khiến ứng dụng âm thầm dùng giá trị mặc định nếu môi trường thiếu biến. Nếu default là credential thật thì secret lại nằm trong Git; nếu default là một password sai, cấu hình production có thể khởi chạy nhưng thất bại ở runtime theo cách khó chẩn đoán.

Với cấu hình cần xác thực, nên **fail fast** khi thiếu secret, thay vì mặc định một password cố định. Nếu môi trường phát triển không gửi mail ra ngoài, hãy dùng profile riêng với SMTP sink hoặc fake sender thay vì dùng một secret thật làm fallback.

### 5.2. Relaxed binding và tên biến Spring Boot

Spring Boot có thể bind các biến môi trường thông qua quy tắc relaxed binding. Ví dụ ở một số cấu hình triển khai:

~~~text
SPRING_MAIL_HOST
SPRING_MAIL_PORT
SPRING_MAIL_USERNAME
SPRING_MAIL_PASSWORD
~~~

có thể được ánh xạ tới các thuộc tính `spring.mail.*` tương ứng. Đây là lựa chọn khác với placeholder `${SMTP_PASSWORD}` trong YAML.

Hãy chọn một quy ước rõ ràng cho môi trường deploy, tránh khai báo đồng thời nhiều nguồn password với precedence khó hiểu. Không dựa vào việc secret được inject đúng chỉ vì biến tồn tại; cần có bước kiểm tra cấu hình và quyền truy cập ở runtime.

### 5.3. Biến môi trường có giới hạn bảo mật

Biến môi trường tốt hơn hard-code, nhưng **không phải secret vault**:

- Người có quyền quản trị host/container có thể đọc process environment.
- Một số công cụ inspect, crash dump hoặc support diagnostic có thể thu thập biến môi trường.
- Lỗi cấu hình CI/CD có thể in biến ra log.
- Biến môi trường thường không tự thay đổi trong một process đang chạy khi secret được rotate.

Với production cần bảo vệ cao, cân nhắc **file secret được mount read-only hoặc secret manager** thay vì chỉ đặt tất cả credential vào biến môi trường.

## 6. Bảo vệ credential khi truyền qua SMTP

Tách secret khỏi Git mới bảo vệ credential **lúc lưu trữ**. Khi ứng dụng gửi tới SMTP server, cần bảo vệ credential **trên đường truyền**.

Hai mô hình kết nối thường gặp:

| Cơ chế | Port ví dụ | Cách thiết lập |
| --- | ---: | --- |
| Submission với STARTTLS | 587 | Bắt đầu kết nối, nâng cấp lên TLS trước khi xác thực |
| Implicit TLS/SMTPS | 465 | TLS bắt đầu ngay khi mở kết nối |

Ví dụ STARTTLS trên cổng 587:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

`mail.smtp.starttls.enable=true` cho phép nâng cấp STARTTLS khi server hỗ trợ. **`mail.smtp.starttls.required=true`** yêu cầu STARTTLS thành công thay vì tiếp tục theo một đường không mã hóa khi server không hỗ trợ. `mail.smtp.ssl.checkserveridentity=true` yêu cầu kiểm tra định danh server theo hostname trong TLS, giúp chống kết nối nhầm endpoint giả mạo.

Ví dụ implicit TLS trên cổng 465:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.ssl.enable: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Không bật cả hai chế độ chỉ vì muốn “càng nhiều TLS càng tốt”; chọn cấu hình đúng với loại endpoint provider cung cấp. Port là quy ước phổ biến, không phải bằng chứng bảo mật: cần xác nhận server thật sự hỗ trợ cơ chế được yêu cầu.

### 6.1. Tránh các cấu hình vô hiệu hóa xác thực TLS

Không dùng:

~~~yaml
spring:
  mail:
    properties:
      mail.smtp.ssl.trust: "*"
~~~

Đặt trust quá rộng có thể khiến ứng dụng tin các certificate không mong muốn, làm suy yếu xác thực server. Nếu certificate của SMTP server không hợp lệ, cần sửa chuỗi tin cậy hoặc cấu hình truststore đúng, không tắt xác thực để “cho gửi được”.

Không bỏ `starttls.required` để né lỗi TLS rồi vẫn đăng nhập bằng credential thật trên một kết nối không được bảo vệ. Bảo mật secret tại runtime và TLS là hai lớp phòng thủ bổ sung nhau.

## 7. Dùng file secret và config tree của Spring Boot

Trong container hoặc môi trường production, một cách cấp secret là **mount file read-only từ secret store**. Ứng dụng đọc secret khi startup mà không cần đưa giá trị đó vào repository, command line hoặc Docker image.

Spring Boot hỗ trợ **config tree**: mỗi file trong một thư mục trở thành một property, với tên file là property key và nội dung file là value. Ví dụ thư mục được cấp tại runtime:

~~~text
/run/secrets/smtp/
├── spring.mail.username
└── spring.mail.password
~~~

Ví dụ file cấu hình không chứa secret:

~~~yaml
# application-prod.yml
spring:
  config:
    import: "configtree:/run/secrets/smtp/"
  mail:
    host: smtp.example.net
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Nội dung của hai file bí mật do hệ thống deploy cấp, không được ghi vào repository hoặc đóng gói trong JAR. Khi Spring Boot đọc config tree, các tên `spring.mail.username` và `spring.mail.password` được cung cấp cho mail auto-configuration.

Ở ví dụ production, không đặt tiền tố `optional:` trước `configtree:`: nếu mount secret bị thiếu, startup sẽ thất bại rõ ràng thay vì âm thầm bỏ qua một nguồn cấu hình bắt buộc. Nếu có môi trường **không sử dụng SMTP thật**, hãy cấu hình profile riêng, không dùng secret production làm fallback.

### 7.1. Vì sao mount file có thể tốt hơn environment variable?

File secret cho phép hệ thống triển khai áp dụng:

- Quyền đọc filesystem theo user/group của tiến trình.
- Volume mount chỉ đọc, hạn chế sửa nhầm.
- Phân quyền secret theo workload/service account.
- Tách cơ chế cấp secret khỏi build và image.
- Audit hoạt động truy cập qua secret manager hoặc nền tảng vận hành.

Tuy vậy, mount file **không làm secret an toàn tuyệt đối**. Người có quyền đọc filesystem trong container hoặc host vẫn có thể lấy nội dung; process khi đọc vẫn giữ secret trong memory. Vì vậy cần kết hợp quyền tối thiểu, network policy, log hygiene và kiểm soát truy cập vào môi trường chạy.

### 7.2. Đừng gắn file secret vào thư mục web/static

Không mount secret ở những thư mục như:

~~~text
src/main/resources/static/
public/
wwwroot/
~~~

hoặc một thư mục có thể bị HTTP server phục vụ như file công khai. File secret phải nằm ngoài đường phục vụ static resource và ngoài vùng người dùng có thể tải xuống.

**Lưu ý về ký hiệu:** đường dẫn `/run/secrets/smtp/` là ví dụ Linux/container, không phải yêu cầu của mọi nền tảng. Đối với Windows service hoặc môi trường khác, dùng vị trí và cơ chế cấp secret tương đương, với ACL phù hợp.

## 8. Ví dụ triển khai trên Kubernetes

Kubernetes có đối tượng `Secret` và có thể mount key dưới dạng file trong Pod. Một phần cấu hình `Deployment` minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mail-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mail-api
  template:
    metadata:
      labels:
        app: mail-api
    spec:
      containers:
        - name: app
          image: registry.example.net/mail-api:release-tag
          volumeMounts:
            - name: smtp-secret-files
              mountPath: /run/secrets/smtp
              readOnly: true
      volumes:
        - name: smtp-secret-files
          secret:
            secretName: smtp-credentials
            items:
              - key: username
                path: spring.mail.username
              - key: password
                path: spring.mail.password
~~~

Ví dụ này **không chứa giá trị bí mật**; Secret tên `smtp-credentials` đã được tạo/cấp bởi quy trình quản lý bí mật có kiểm soát. File mount sẽ khớp các property của config tree trong phần trước.

Trong môi trường thực tế:

- Chỉ cấp quyền đọc Secret cho service account/workload cần gửi mail.
- Thiết lập RBAC và chính sách hạn chế ai được `get/list/watch` Secret.
- Bật encryption at rest cho dữ liệu Secret theo khả năng của cluster.
- Giới hạn quyền truy cập Pod, node và cơ chế `exec`/debug.
- Đặt permission phù hợp để ứng dụng chạy non-root vẫn đọc được file mà không mở quyền cho mọi process.
- Không commit một manifest `Secret` có `data` hay `stringData` chứa credential thật lên Git công khai hoặc repository không được phép.

**Kubernetes Secret không tự bảo đảm bí mật tuyệt đối.** Giá trị trong field `data` được biểu diễn bằng Base64; Base64 **không phải mã hóa bảo mật**. Secret có thể bị đọc nếu quyền RBAC, quyền node hoặc quy trình backup bị cấu hình sai.

### 8.1. Cấp secret từ hệ thống bên ngoài

Trong nhiều tổ chức, Secret của Kubernetes có thể được đồng bộ từ một secret manager qua bộ điều khiển hoặc CSI driver. Khi đó:

~~~text
Secret manager / vault
          |
          v
Controlled workload identity
          |
          v
Secret sync / CSI mount
          |
          v
Read-only runtime file
          |
          v
Spring Boot config tree
          |
          v
JavaMailSender
~~~

Quy trình cụ thể phụ thuộc nhà cung cấp và hạ tầng, nhưng các nguyên tắc giữ nguyên: secret không đi vào image, quyền đọc ở mức workload, có rotation và có audit.

### 8.2. Rotation của file mount không đồng nghĩa ứng dụng đã đổi credential

Ngay cả khi nền tảng cập nhật nội dung file secret, `JavaMailSender` hoặc đối tượng cấu hình của Spring Boot có thể đã đọc giá trị lúc khởi động. Việc thay file không tự bảo đảm bean SMTP sẽ nhận password mới trong mọi cấu hình.

Phải xác định rõ chiến lược **reload hoặc rolling restart** khi rotate secret. Nếu dùng cơ chế refresh động, cần kiểm tra thread-safety, connection pool, thời điểm áp dụng và cách xử lý các lượt gửi đang chạy.

## 9. Secret manager và workload identity

Với production, tổ chức có thể lưu credential tại một hệ thống quản lý secret chuyên dụng:

- HashiCorp Vault hoặc nền tảng tương đương.
- Secret manager của nhà cung cấp cloud.
- Hệ thống quản lý khóa/credential nội bộ.
- Dịch vụ identity cấp token ngắn hạn thay cho password lâu dài.

Điểm khác biệt quan trọng so với việc lưu password trong source là **secret chỉ được cấp cho workload đúng quyền tại runtime**, thường dựa trên machine/workload identity hoặc service account.

Luồng tổng quát:

~~~text
Developer commits code (không có secret)
          |
          v
CI builds immutable artifact (không có secret)
          |
          v
Runtime authenticates using workload identity
          |
          v
Secret manager authorizes secret read
          |
          v
Process obtains credential
          |
          v
JavaMailSender authenticates over TLS
~~~

Một ứng dụng dùng secret manager vẫn cần bảo vệ **identity dùng để lấy secret**. Nếu phải hard-code một “master password của Vault” vào ứng dụng để lấy SMTP password, hệ thống chỉ chuyển vấn đề sang một secret khác.

### 9.1. Quyền tối thiểu (least privilege)

Workload gửi email nên chỉ được đọc:

- Credential của SMTP account mà nó thực sự sử dụng.
- Phiên bản secret tương ứng với môi trường (`dev`, `staging`, `production`).
- Các key liên quan tới luồng gửi mail được cấp quyền.

Không cấp quyền đọc tất cả secret của tổ chức chỉ để một mail service hoạt động. Tách credential production với staging, tách sender theo hệ thống nếu provider hỗ trợ, và giới hạn chức năng account ở mức cần thiết.

### 9.2. Tách environment và tenant

Không dùng chung một SMTP password cho:

- Local development, staging và production.
- Nhiều ứng dụng không liên quan.
- Nhiều tenant nếu yêu cầu isolation có mức rủi ro riêng.

Khi dùng credential theo tenant, hãy chọn secret dựa trên tenant đã được **xác thực và ủy quyền**, không lấy trực tiếp secret path từ request rồi đọc tùy ý. Không log tên secret có thông tin cá nhân nếu namespace secret chứa PII.

## 10. Không đưa SMTP secret vào Docker image

Trong CI/CD, credential SMTP thường chỉ cần ở **runtime**, không cần để compile, test unit hoặc đóng gói JAR.

Tránh:

~~~dockerfile
# KHÔNG NÊN
ARG SMTP_PASSWORD
ENV SMTP_PASSWORD=$SMTP_PASSWORD
COPY application-prod-with-password.yml /app/application.yml
~~~

Vấn đề:

- Build argument hoặc `ENV` có thể xuất hiện trong image metadata, lịch sử hoặc build log.
- File được `COPY` vào image tồn tại trong các layer/artifact đã phát hành.
- Rebuild image cho mỗi lần đổi secret khiến việc rotate chậm và phân tán credential.

Dockerfile nên độc lập với secret SMTP:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Runtime cung cấp environment hoặc secret volume theo cơ chế deploy. Không vì muốn “ẩn trong Docker image” mà mã hóa password bằng một khóa cũng được COPY vào image.

### 10.1. Docker Compose dùng biến runtime vẫn cần bảo vệ

Ví dụ ở mức cấu hình:

~~~yaml
services:
  mail-api:
    image: registry.example.net/mail-api:release-tag
    environment:
      SMTP_USERNAME: ${SMTP_USERNAME:?required}
      SMTP_PASSWORD: ${SMTP_PASSWORD:?required}
~~~

Compose ở đây dùng interpolation để lấy giá trị từ môi trường của công cụ deploy. `:?required` yêu cầu biến có giá trị theo cú pháp Compose, tránh deploy với biến trống.

Tuy nhiên, các giá trị được đặt trong **environment của container** có thể bị lộ bởi công cụ inspect hoặc người có quyền quản trị daemon/container. Với môi trường có yêu cầu bảo mật cao, ưu tiên cơ chế runtime secret file/secret service hỗ trợ. File `.env` nếu được sử dụng để cung cấp biến phải được kiểm soát quyền và **không commit lên Git**; chỉ thêm vào `.gitignore` chưa đủ nếu file đã từng được commit.

## 11. Bảo vệ SMTP secret trong CI/CD

Pipeline build và deploy là một nguồn rò rỉ credential phổ biến. Một quy trình an toàn nên tách hai giai đoạn:

~~~text
Build stage
   - checkout source
   - compile/test
   - package artifact / container image
   - không đọc SMTP password production
          |
          v
Deploy stage
   - deploy artifact đã build
   - workload được cấp secret lúc chạy
   - ứng dụng khởi động và xác thực SMTP qua TLS
~~~

Điều này giúp artifact có thể được promoted từ staging sang production mà không cần nhúng credential của bất kỳ môi trường nào.

### 11.1. Nguyên tắc cho pipeline

- Lưu credential trong **secret store của CI/CD hoặc hệ thống runtime**, không trong file YAML pipeline.
- Giới hạn môi trường/branch/job được phép sử dụng secret production.
- Chỉ cấp quyền cho deploy job thật sự cần; job pull request từ nguồn không tin cậy không nên đọc credential.
- Không dùng `echo`, `printenv`, `set -x` hoặc ghi toàn bộ environment khi có secret.
- Bật masking ở pipeline nếu nền tảng hỗ trợ, nhưng **masking không thay thế việc tránh log secret**.
- Không lưu secret vào build cache, test report, artifact, support bundle hay terminal transcript.
- Không truyền password bằng command-line argument có thể lộ trong process listing.
- Quản lý quyền sửa pipeline vì người có quyền sửa bước chạy có thể thay code để đọc secret.
- Audit truy cập secret, thay đổi permission và các lần deploy có sử dụng quyền production.

Nếu pipeline cần chạy integration test với SMTP, dùng SMTP sink hoặc tài khoản **test riêng** có quota và phạm vi giới hạn. Không dùng credential production trong unit test hay test tự động từ nhánh chưa được bảo vệ.

### 11.2. Secret scanning và Git history

Có thể thêm secret scanning ở pre-commit hoặc CI để phát hiện credential bị đưa vào source, file cấu hình hoặc commit. Tuy nhiên, scanner có thể không nhận diện được mọi loại token và không thay thế code review/quản lý secret.

Nếu một secret từng được commit, thêm tên file vào `.gitignore` chỉ ngăn một số lần add mới; **nó không xóa nội dung khỏi commit lịch sử, clone hoặc backup**. Khi phát hiện lộ secret, ưu tiên rotate/revoke ngay, rồi xử lý lịch sử và bản sao theo quy trình incident response.

## 12. Không để secret lọt qua logging và SMTP debug

Một lỗi thường gặp khi chẩn đoán SMTP là bật log giao thức hoặc in object cấu hình:

~~~java
// KHÔNG NÊN:
log.info("SMTP config: {}", mailProperties);
log.error("SMTP failed, password={}", password);
~~~

Đối tượng mail properties có thể chứa password; phương thức `toString()` tự sinh của record/Lombok có thể vô tình in toàn bộ field.

Ví dụ log an toàn hơn:

~~~java
log.info(
        "Mail sender configured host={} port={} tlsRequired={}",
        configuredHost,
        configuredPort,
        true);
~~~

Đối với lỗi gửi:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    log.warn(
            "Mail send failed deliveryId={} errorType={}",
            deliveryId,
            ex.getClass().getSimpleName());
    throw ex;
}
~~~

Đừng in `ex.getMessage()` hoặc nguyên stack trace vào kênh log công khai nếu chưa xác định được các thành phần có thể chứa recipient, địa chỉ server, token hay dữ liệu MIME. Khi cần chẩn đoán sâu, dùng log có bảo vệ quyền truy cập và quy trình lọc dữ liệu nhạy cảm.

### 12.1. Tắt SMTP debug có khả năng lộ dữ liệu

Trong môi trường production, không bật debug authentication/protocol một cách tùy tiện:

~~~yaml
spring:
  mail:
    properties:
      mail.debug: false
      mail.debug.auth: false
~~~

Khi bật Jakarta Mail debug hoặc bật `Session.setDebug(true)`, log giao thức có thể tiết lộ metadata về email, SMTP command hoặc thông tin nhạy cảm tùy phiên bản và cấu hình. Đặc biệt, các tùy chọn liên quan đến debug auth không nên được bật trong production.

Nếu bắt buộc bật logging để điều tra:

1. Chỉ thực hiện trong thời gian ngắn, có người phê duyệt.
2. Dùng tài khoản thử nghiệm khi có thể.
3. Kiểm soát nơi log được lưu và ai có quyền đọc.
4. Không log credential, token hoặc body email thực.
5. Tắt lại sau điều tra và kiểm tra retention của dữ liệu đã thu thập.

### 12.2. Exception chain cũng có thể mang secret

`MailSendException` có thể chứa nested cause của Jakarta Mail/SMTP transport. Ngay cả khi top-level message chung chung, phần cause bên trong có thể chứa địa chỉ người nhận, hostname hoặc chi tiết phản hồi server.

Khi cần lưu lỗi vào outbox, nên dùng một bộ phân loại:

~~~java
public record SafeMailError(
        String errorCode,
        String errorType,
        String safeSummary) {
}

SafeMailError error = new SafeMailError(
        "SMTP_AUTH_FAILED",
        exception.getClass().getSimpleName(),
        "SMTP authentication was rejected");
~~~

Không lưu nguyên object `Throwable` hoặc serialize `MailException` trực tiếp vào JSON. Đối với metric, chỉ dùng `errorCode` đã chuẩn hóa, không dùng exception message hoặc password làm label.

## 13. Bảo vệ Actuator, diagnostic endpoint và config dump

Spring Boot Actuator có thể cung cấp thông tin chẩn đoán cấu hình qua các endpoint như `/actuator/env` và `/actuator/configprops` khi được bật. Đây là những endpoint hữu ích trong vận hành nhưng có thể làm lộ tên property và, nếu cấu hình sai, giá trị nhạy cảm.

Một cấu hình thận trọng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Trong các phiên bản Spring Boot hỗ trợ thuộc tính `show-values`, `never` yêu cầu không hiển thị giá trị property ở các endpoint đó. Cấu hình `exposure.include` ở đây không expose `env` hoặc `configprops` qua web.

Không xem sanitization là lớp bảo vệ duy nhất. Vẫn cần:

- Chỉ bật endpoint quản trị cần thiết.
- Bảo vệ endpoint bằng authentication/authorization và network restriction.
- Không công khai `/env`, `/configprops` hoặc endpoint debug tùy ý.
- Không tạo API “show current mail config” trả về object có password.
- Hạn chế access tới thread dump, heap dump, process diagnostic và file support bundle.

Các giá trị cụ thể và khả năng mặc định của Actuator có thể khác giữa các phiên bản Spring Boot; hãy áp dụng một cấu hình quản trị theo chính sách môi trường thay vì phụ thuộc vào việc secret chắc chắn sẽ được che trong mọi công cụ.

### 13.1. Không tự expose @ConfigurationProperties chứa password

Nếu ứng dụng tạo class cấu hình riêng:

~~~java
@ConfigurationProperties(prefix = "app.smtp")
public class SmtpSettings {
    private String username;
    private String password;

    // Getters/setters omitted.
}
~~~

Không đưa object này vào response API, metric hoặc log. Nếu dùng Lombok `@Data` hoặc Java record, lưu ý phương thức `toString()` có thể in cả password. Có thể thiết kế object cấu hình không sinh `toString` chứa secret, hoặc chủ động redact field khi cần chẩn đoán.

Trong ứng dụng Spring Boot thông thường, không cần định nghĩa một bản sao credential khác nếu `spring.mail.username` và `spring.mail.password` đã được auto-configuration sử dụng. Giảm số nơi lưu/copy secret giúp giảm bề mặt rò rỉ.

## 14. Kiểm tra thiếu credential và fail fast

Một ứng dụng yêu cầu gửi SMTP có xác thực không nên chạy production với username hoặc password rỗng rồi chỉ phát hiện lúc gửi email đầu tiên.

Với cấu hình environment placeholder hoặc config tree bắt buộc, lỗi thiếu nguồn cấu hình có thể được phát hiện khi startup. Nếu cần áp dụng chính sách rõ ràng hơn, có thể thêm guard riêng cho profile production:

~~~java
package com.example.mail;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration
@Profile("prod")
public class MailCredentialGuardConfig {

    @Bean
    ApplicationRunner validateSmtpCredentials(
            Environment environment) {

        return args -> {
            String username =
                    environment.getProperty("spring.mail.username");
            String password =
                    environment.getProperty("spring.mail.password");

            if (username == null || username.isBlank()
                    || password == null || password.isBlank()) {
                // Không đưa giá trị secret vào exception message.
                throw new IllegalStateException(
                        "Required SMTP authentication is not configured");
            }
        };
    }
}
~~~

Ở đây guard chỉ kiểm tra sự hiện diện; **không log credential** và không chứng minh credential đúng hay server kết nối được. Guard giả định profile `prod` yêu cầu username/password SMTP. Nếu dùng OAuth2 hoặc cơ chế khác, cần thay kiểm tra bằng chính sách credential tương ứng.

Nếu cần kiểm tra kết nối SMTP trong startup/health check, phải hiểu rằng một kết nối tới provider cũng có thể làm quá trình deploy phụ thuộc vào mạng hoặc quota. Không thực hiện gửi email thật chỉ để kiểm tra cấu hình ở mọi lần khởi động. Thiết kế readiness/health theo yêu cầu SLA và khả năng provider, không để lộ thông tin xác thực trong response.

### 14.1. Password rỗng khác password sai

Nên phân biệt:

| Tình huống | Cách nhận diện | Hành động |
| --- | --- | --- |
| Không có secret source | Config import/placeholder không resolve | Fail startup hoặc cảnh báo triển khai |
| Password rỗng | Validation của ứng dụng | Fail fast, không cố SMTP |
| Username/password không khớp | SMTP trả lỗi auth | Báo lỗi cấu hình; kiểm tra secret version |
| Secret bị thu hồi | SMTP auth đột ngột thất bại sau khi từng chạy tốt | Kiểm tra rotation/revocation |
| TLS thất bại | Không xác thực được TLS endpoint | Kiểm tra cert/CA/hostname, không tắt validation |
| SMTP provider tạm ngừng | Kết nối timeout hoặc phản hồi tạm thời | Retry/backoff tùy policy |

Không gộp tất cả vào thông báo `invalid password`: lỗi TLS, DNS, network hoặc provider outage không phải lúc nào cũng liên quan tới credential.

## 15. Xoay vòng (rotate) SMTP credential

Không có secret nào nên được giả định là sẽ tồn tại mãi mãi. Credential có thể cần thay vì chính sách bảo mật, nhân sự thay đổi, nghi ngờ lộ thông tin hoặc yêu cầu của nhà cung cấp.

**Rotation** là quy trình thay credential cũ bằng credential mới trong khi giảm tối đa gián đoạn gửi email.

### 15.1. Quy trình rotation có chuẩn bị

Nếu provider cho phép tồn tại đồng thời hai credential:

1. Tạo credential mới bằng tài khoản/quyền được cấp phù hợp.
2. Lưu bản mới trong secret manager hoặc secret store của môi trường.
3. Cập nhật tham chiếu version/key được deploy; không in giá trị ra terminal/log.
4. Cho workload reload hoặc rolling restart để `JavaMailSender` nhận credential mới.
5. Kiểm tra xác thực và gửi **email thử tới SMTP sink hoặc người nhận kiểm thử được phép**.
6. Theo dõi tỷ lệ lỗi auth, trạng thái queue/outbox và số attempt lỗi.
7. Thu hồi credential cũ sau khi xác nhận workload đã chuyển sang bản mới.
8. Ghi audit: ai thực hiện, thời điểm, version được chuyển, xác nhận revoke.

Nếu provider chỉ hỗ trợ một credential tại một thời điểm, cần kế hoạch cutover và chấp nhận khả năng gián đoạn ngắn. Lưu backoff/retry cho các email tạm thời gửi lỗi thay vì bỏ thư.

### 15.2. Rotation không có nghĩa thay file là đủ

Một ứng dụng Java có thể giữ password trong đối tượng cấu hình hoặc mail sender suốt vòng đời process. Vì vậy:

~~~text
Secret manager rotates credential
              |
              v
Runtime mount / environment updated
              |
              v
Does JavaMailSender use new value?
              |
       +------+------+
       |             |
       v             v
     Yes          No / unknown
       |             |
       v             v
 Validate         Reload bean /
 SMTP auth        rolling restart
~~~

Không giả định secret đã được cập nhật chỉ vì file mount thay đổi. Nếu dùng environment variable, giá trị process thường được chụp ở lúc khởi chạy và cần restart/redeploy. Nếu dùng secret file và framework có cơ chế refresh, phải kiểm tra cụ thể bean SMTP và các kết nối đã mở có thực sự nhận credential mới hay chưa.

### 15.3. Rotation của OAuth token

OAuth access token có thời hạn ngắn; việc làm mới token phải diễn ra trước khi hết hạn và theo đúng flow/provider. Nếu refresh token hoặc client secret dùng để lấy access token bị lộ, phải thu hồi credential đó và xem xét phạm vi token đã phát.

Không cache access token vô thời hạn trong một `static final String` hoặc ghi token vào log để debug. Nếu dùng OAuth2 với SMTP, cần cấu hình cơ chế SASL/XOAUTH2 và quyền phù hợp theo provider; không coi access token như một password vĩnh viễn.

### 15.4. Không retry liên tục khi lỗi do rotation

Nếu credential cũ bị thu hồi nhưng ứng dụng chưa reload, SMTP có thể trả lỗi xác thực cho hàng loạt email. Retry ngay lập tức bằng cùng credential không có ích và có thể kích hoạt biện pháp chống lạm dụng của provider.

Hệ thống nên:

- Phân loại `MailAuthenticationException` thành sự cố cấu hình/cấp quyền.
- Cảnh báo người vận hành.
- Tạm dừng hoặc đặt backoff hợp lý cho các attempt cùng nguyên nhân.
- Không đánh dấu `SENT` cho message bị từ chối.
- Khi credential đã được cập nhật, redrive các delivery còn hợp lệ theo chính sách.

## 16. Xử lý khi SMTP secret bị lộ

Giả sử một password SMTP thật bị commit vào repository hoặc xuất hiện trong log build. Không chỉ “xóa dòng secret” rồi coi sự cố kết thúc: credential có thể đã được sao chép.

Một quy trình incident response điển hình:

| Giai đoạn | Hành động |
| --- | --- |
| **Contain** | Thu hồi/vô hiệu hóa credential bị lộ càng sớm càng phù hợp với chính sách vận hành; phát credential mới qua kênh an toàn |
| **Assess** | Xác định phạm vi repository, log, artifact, image, CI runner và những người có quyền truy cập |
| **Recover** | Cập nhật runtime secret, restart/reload ứng dụng và xác nhận gửi mail hoạt động |
| **Investigate** | Kiểm tra SMTP/provider audit, số lượng email bất thường, thay đổi quota và dấu hiệu lạm dụng |
| **Clean up** | Loại secret khỏi source/artifact/log còn trong phạm vi kiểm soát; xử lý history/backup theo quy trình được duyệt |
| **Prevent** | Bổ sung secret scanning, tách quyền, kiểm soát debug và cải thiện quy trình cấp credential |

Trong trường hợp đã nghi ngờ bị lộ, **rotate/revoke phải được ưu tiên hơn việc chỉ viết lại lịch sử Git**. Rewrite history không thu hồi credential cũ khỏi những bản clone, cache hoặc log đã được tạo.

### 16.1. Khi credential bị phát tán qua log

Ngoài revoke:

- Xác định thời gian log nhạy cảm được thu thập.
- Kiểm tra người/role có thể đọc log.
- Hạn chế hoặc xóa các bản log bị ảnh hưởng theo chính sách retention và điều tra.
- Xác minh không có pipeline, collector hoặc dashboard nào tiếp tục xuất trường nhạy cảm.
- Không copy lại credential bị lộ vào ticket/chat để “lưu bằng chứng”; dùng mã sự cố và vị trí bằng chứng được bảo vệ.

Đôi khi log còn chứa tên người nhận và nội dung thư; phạm vi xử lý sự cố phải xét cả dữ liệu cá nhân, không chỉ password.

### 16.2. Secret bị lộ trong Docker image

Nếu image đã chứa file password, việc sửa Dockerfile chỉ ảnh hưởng build tương lai. Cần:

1. Revoke credential cũ.
2. Build/publish image sạch.
3. Thay workload đang chạy bằng image sạch.
4. Kiểm soát quyền và retention của registry/cache/artifact chứa image cũ.
5. Kiểm tra các bản deploy cũ có còn chạy hoặc đang được backup không.

Không trông đợi rằng thay `ENV` lúc deploy sẽ làm secret biến mất khỏi layer cũ.

## 17. Môi trường local và thử nghiệm không cần secret production

Phần lớn thao tác phát triển template và MIME không cần gửi thư thật. Có thể dùng SMTP sink cục bộ như Mailpit hoặc MailHog để ứng dụng gửi email vào một hộp thư thử nghiệm thay vì provider production.

Ví dụ `application-local.yml`:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
~~~

Đây là ví dụ cho **SMTP sink local chỉ bind ở loopback và không yêu cầu xác thực**. Không được đem cấu hình `auth: false`, không TLS vào production SMTP qua mạng công cộng. Nếu sink ở container khác, tên host/port cần thay theo network và chính sách cô lập của môi trường thử nghiệm.

Mục tiêu:

- Render email HTML/plain text và kiểm tra MIME mà không tiêu hao quota mail thật.
- Không cần phát SMTP password thật cho mọi developer.
- Dễ chạy test với recipient giả.
- Không vô tình gửi thông báo thử nghiệm tới khách hàng.

### 17.1. Secret local nên lưu ở đâu?

Nếu vẫn phải kiểm thử với SMTP thật trong một môi trường được phép:

- Dùng credential riêng cho developer/test, với quota và phạm vi giới hạn.
- Lưu bằng phương tiện được tổ chức chấp thuận: password manager, keychain hoặc secret store cho local development.
- Không commit `.env`, `application-local.yml` chứa giá trị thật hoặc shell script thiết lập password.
- Không đưa credential vào command history nếu có kênh cấu hình an toàn hơn.
- Xóa hoặc thu hồi test credential khi không còn cần.

**Spring Boot không mặc định biến mọi file `.env` thành nguồn cấu hình chỉ vì file có tên `.env`.** Một công cụ như Docker Compose hoặc shell có thể nạp nó, nhưng cách load vào process phải được cấu hình tường minh theo môi trường.

### 17.2. Một cấu hình giả cho unit test

Với unit test service gọi `JavaMailSender`, có thể dùng mock/fake:

~~~java
@Test
void sendNoticeBuildsExpectedMessage() {
    JavaMailSender mailSender = mock(JavaMailSender.class);
    MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));

    when(mailSender.createMimeMessage()).thenReturn(message);

    NotificationMailer service = new NotificationMailer(mailSender);
    service.send("recipient@example.invalid", "Thông báo thử");

    verify(mailSender).send(any(MimeMessage.class));
}
~~~

Ví dụ dùng JUnit 5/Mockito và giả định `NotificationMailer` có API tương ứng. Test này không yêu cầu SMTP password thật và không mở kết nối mạng. Nếu cần xác nhận email thực sự được tạo đúng MIME, có thể xem message được xây dựng bằng Jakarta Mail hoặc gửi tới SMTP sink trong integration test.

Tên miền `example.invalid` trong ví dụ là địa chỉ giả; không dùng email khách hàng thật trong test nếu không cần.

## 18. Kiểm tra tính an toàn của việc cấp secret

Kiểm thử cấu hình nên tập trung vào những hành vi quan sát được:

### 18.1. Test không có secret production

Với profile `prod`, bỏ nguồn password được mount hoặc biến môi trường giả định:

1. Ứng dụng phải từ chối khởi động nếu credential bắt buộc không có.
2. Thông báo lỗi không được in giá trị password.
3. Không tự động fallback sang secret hard-code.
4. Không bật một SMTP mode không xác thực/TLS chỉ để vượt qua lỗi.

Không cần gửi thư thật để kiểm tra ứng dụng phản ứng đúng khi thiếu cấu hình.

### 18.2. Test nguồn secret được resolve

Trong môi trường test được cô lập, cấp một chuỗi dummy không có quyền gửi thật từ file hoặc environment và xác nhận cấu hình mail sender đọc đúng property. Không log chuỗi dummy theo cùng code path mà production sẽ dùng secret thật.

Khi kiểm tra object cấu hình trong test, chỉ so sánh giá trị trong memory theo phạm vi test và không đưa nó vào test report/serialized snapshot công khai.

### 18.3. Test log không xuất secret

Một phép thử hữu ích là sử dụng **sentinel credential giả** rồi kích hoạt nhánh lỗi (ví dụ mail authentication failure) và kiểm tra hệ thống log đã cấu hình không chứa sentinel. Kiểm tra này hỗ trợ phát hiện việc vô tình log password nhưng không chứng minh toàn bộ hệ thống không có đường rò rỉ khác.

Không chạy test bảo mật với secret thật chỉ để kiểm tra nó có bị log hay không.

### 18.4. Test TLS failure là fail-closed

Với endpoint thử nghiệm có certificate không đáng tin hoặc không hỗ trợ STARTTLS, xác nhận client thất bại theo chính sách, thay vì âm thầm gửi credential qua kết nối không được bảo vệ. Không tắt hostname verification/truststore để làm test “xanh”.

### 18.5. Test sau rotation

Trong môi trường được kiểm soát:

- Secret mới được cấp cho workload.
- Ứng dụng reload/restart theo thiết kế.
- SMTP authentication với credential mới hoạt động.
- Credential cũ bị revoke không còn dùng được.
- Delivery đang chờ không bị đánh dấu `SENT` khi authentication thất bại.
- Các job có thể retry lại với credential mới mà không mất trạng thái.

Nếu có nhiều instance, thử rolling restart để phát hiện instance còn sử dụng credential cũ.

## 19. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Production không resolve `SMTP_PASSWORD` | Chưa inject biến hoặc tên biến sai | Kiểm tra secret injection, tên key và môi trường, không in giá trị |
| File config tree không được đọc | Mount sai path, thiếu file, process không có quyền | Xác nhận đường dẫn, ACL, read-only mount và tên file |
| Password đúng trong secret manager nhưng SMTP auth vẫn lỗi | Bean đọc version cũ hoặc env override giá trị mới | Kiểm tra precedence và reload/restart |
| Sau rotation một vài Pod vẫn auth thất bại | Rolling deploy chưa hoàn tất hoặc instance còn credential cũ | Xác định Pod/version, hoàn tất rollout, thu hồi credential cũ theo kế hoạch |
| SMTP gửi được ở local nhưng không chạy production | Sai host/port/TLS policy, mạng hoặc tài khoản không được phép | Kiểm tra mạng, TLS handshake, quota và auth theo từng môi trường |
| JavaMailSender không xác thực | Thiếu `mail.smtp.auth=true` hoặc credential không được bind | Kiểm tra policy SMTP và nguồn cấu hình |
| TLS báo certificate/hostname error | Certificate chain/CA hoặc hostname không khớp | Sửa truststore/cert/hostname; không dùng trust wildcard |
| Secret xuất hiện trong build log | Script in environment hoặc bật command tracing | Tắt luồng log nhạy cảm, revoke/rotate và rà phạm vi log |
| Secret xuất hiện trong image | Dùng `ARG/ENV` hoặc `COPY` file secret khi build | Revoke/rotate, rebuild image sạch, xử lý artifact cũ |
| `/actuator/env` có thể truy cập công khai | Expose endpoint và bảo vệ kém | Giới hạn exposure, authz, network và show-values |
| Email thất bại sau khi đổi credential | SMTP account bị revoke, chưa reload, provider giới hạn | Kiểm tra version, error category và áp dụng backoff |
| Secret local vô tình lên Git | File chưa ignore hoặc được force-add | Revoke, làm sạch repository/history theo quy trình |
| Log SMTP quá chi tiết | Debug protocol/auth bật trên production | Tắt debug, bảo vệ và xử lý các log đã thu thập |
| Nhầm Base64 là bảo vệ secret | Dùng encoding thay encryption/secret store | Chuyển sang secret management và quyền tối thiểu |

### 19.1. Cẩn thận với thứ tự ưu tiên property source

Spring Boot hỗ trợ nhiều nguồn cấu hình: file application theo profile, biến môi trường, command line, config import và các nguồn tích hợp khác. Một property có thể được khai báo ở nhiều nơi, và nguồn có mức ưu tiên cao hơn có thể **override** giá trị từ secret store.

Ví dụ:

~~~text
Mounted config tree provides spring.mail.password
          |
          v
An old environment variable SPRING_MAIL_PASSWORD also exists
          |
          v
Actual value depends on property-source precedence
~~~

Khi rotate secret nhưng SMTP vẫn xác thực bằng bản cũ, nên kiểm tra **đường đi của cấu hình**, tên property và các nguồn override. Không in giá trị resolved password ra log để xác định nguồn nào thắng. Có thể tạm cung cấp diagnostic chỉ ghi **tên nguồn/property** theo phương án kiểm soát quyền, không ghi nội dung secret.

Chọn một nguồn secret chính thức cho production và hạn chế override tùy tiện bằng command-line argument. Việc giữ quy ước rõ ràng quan trọng hơn cố gắng “ẩn” password bằng nhiều lớp placeholder chồng nhau.

### 19.2. Rò rỉ secret qua toString, exception hoặc serialization

Ngoài việc in trực tiếp password, còn có các lối rò rỉ gián tiếp:

~~~java
record MailSettings(String username, String password) {
}

MailSettings settings =
        new MailSettings("mailer@example.net", "dummy-value");

// Không làm thế này với settings thật:
log.debug("settings={}", settings);
~~~

Java record tự sinh `toString()` với cả các thành phần, nên ví dụ trên có thể in password. Tương tự, Lombok `@Data` thường tạo `toString()`. Nếu bắt buộc dùng các cấu trúc này, phải chủ động loại secret khỏi output hoặc không log object.

Tránh đưa secret vào response DTO, cache key, exception message hoặc serialized debugging event. Một property được đọc từ vault **vẫn là secret** sau khi nằm trong Java object.

## 20. Câu hỏi thường gặp

**“Đặt password trong application.properties và thêm file vào .gitignore đã đủ chưa?”**  
Chưa. Nếu file từng được commit, nó vẫn nằm trong Git history và các bản sao. Nếu file được đóng gói vào JAR, password vẫn theo artifact. Tốt hơn là cấu hình bằng environment, runtime mount hoặc secret manager.

**“Có thể hard-code password rồi mã hóa Base64 không?”**  
Không. Base64 chỉ biến đổi biểu diễn, có thể giải mã dễ dàng. Mã hóa bằng khóa hard-code ngay trong ứng dụng cũng không giải quyết được việc phải giữ bí mật khóa.

**“Biến môi trường có được xem là tuyệt đối an toàn không?”**  
Không. Nó giúp tránh commit vào source nhưng có thể bị người có quyền trên host/container, công cụ diagnostics hoặc log pipeline truy cập. Cần phân quyền và kiểm soát môi trường.

**“Tại sao nên dùng config tree nếu đã có environment?”**  
Config tree cho phép phân phối secret qua file được mount, áp dụng quyền filesystem và tách nội dung khỏi image/environment khi nền tảng hỗ trợ. Không phải ứng dụng nào cũng bắt buộc dùng, nhưng đây là lựa chọn hữu ích cho container production.

**“Kubernetes Secret đã được mã hóa chưa?”**  
Field `data` dùng Base64, không phải encryption. Bảo vệ thực tế còn phụ thuộc encryption at rest của cluster, RBAC, quyền node, backup và quy trình cấp secret.

**“Có nên lưu username SMTP trong Git không?”**  
Username không phải lúc nào cũng cấp quyền độc lập, nhưng có thể tiết lộ tài khoản gửi/hạ tầng. Thường nên cấu hình ngoài source nếu chính sách tổ chức coi đó là dữ liệu vận hành nhạy cảm.

**“Có nên dùng app password thay mật khẩu chính?”**  
Nếu provider hỗ trợ, app password riêng có thể giúp giảm phạm vi ảnh hưởng và dễ revoke. Nhưng nó vẫn phải được quản lý như secret thật.

**“OAuth2 có loại bỏ nhu cầu quản lý secret không?”**  
Không. Access token là secret; refresh token, client secret hoặc identity dùng để lấy token cũng cần bảo vệ. OAuth2 có thể hỗ trợ token ngắn hạn và scope, nhưng không tự bảo đảm log và storage an toàn.

**“Port 587 có phải luôn an toàn vì có STARTTLS không?”**  
Không. Cần yêu cầu STARTTLS, xác thực chứng chỉ/hostname và bảo đảm provider hỗ trợ. Chỉ chọn port 587 không đủ.

**“Port 465 và 587 có khác nhau ở cách dùng secret không?”**  
Cả hai đều cần bảo vệ credential. Port 465 thường dùng TLS từ đầu kết nối; port 587 thường dùng STARTTLS để nâng cấp. Cấu hình phải phù hợp endpoint.

**“Có thể đặt mail.smtp.ssl.trust=* để sửa nhanh lỗi TLS không?”**  
Không nên. Trust rộng làm suy yếu xác thực server. Hãy sửa certificate chain/truststore và hostname theo cấu hình đúng.

**“Có nên bật mail.debug khi production lỗi?”**  
Chỉ trong điều kiện chẩn đoán được kiểm soát, có thời hạn và chính sách bảo vệ log rõ ràng. Không bật auth debugging hay in credential. Ưu tiên log phân loại lỗi và correlation ID.

**“Nếu đã tắt debug, secret có chắc không xuất hiện trong log?”**  
Không thể kết luận như vậy. Code ứng dụng, framework, exception chain và pipeline có thể vẫn ghi nhầm secret. Cần bảo vệ nhiều lớp và kiểm thử đường log nhạy cảm.

**“Có thể expose /actuator/env để xác nhận password đã được load?”**  
Không nên dùng giá trị password trong endpoint chẩn đoán. Giới hạn endpoint, yêu cầu quyền phù hợp và kiểm tra trạng thái cấu hình bằng tín hiệu không tiết lộ secret.

**“Khi rotation, file secret mới có làm JavaMailSender tự dùng mật khẩu mới không?”**  
Không được bảo đảm. Bean có thể đã nhận giá trị lúc startup. Cần reload/restart theo thiết kế và xác nhận xác thực với credential mới.

**“Thiếu SMTP_PASSWORD thì cho ứng dụng dùng mặc định được không?”**  
Không dùng mật khẩu mặc định hard-code cho production. Nếu cấu hình bắt buộc thiếu, fail fast; nếu môi trường local không cần gửi thật, dùng profile SMTP sink riêng.

**“Có nên gửi một email thật mỗi lần app khởi động để test secret không?”**  
Không cần thiết trong nhiều ứng dụng, và có thể gây spam/quota hoặc làm startup phụ thuộc provider. Hãy dùng validation cấu hình, health policy phù hợp và integration test tách biệt.

**“Sau khi phát hiện secret bị commit, chỉ cần xóa commit là đủ?”**  
Không. Secret có thể đã nằm trong clone, cache, CI log hoặc image. Revoke/rotate là bước quan trọng đầu tiên; sau đó xử lý dữ liệu và bản sao theo incident response.

## 21. Checklist triển khai bảo vệ SMTP secret

Khi đưa Spring Framework Mail lên production, có thể kiểm tra các nhóm sau:

### Nguồn cấu hình

1. Password/app password/token không nằm trong source code, file cấu hình được commit hoặc test fixture.
2. Secret được cấp qua nguồn runtime có kiểm soát: environment, mount file hoặc secret manager.
3. Không có fallback secret hard-code trong `${NAME:default}`.
4. Phân quyền nguồn secret theo môi trường và workload.
5. Không dùng chung credential production với local/staging.
6. Không có property source cũ vô tình override secret mới.

### Mạng và SMTP

7. Chọn đúng TLS mode cho endpoint: STARTTLS bắt buộc hoặc implicit TLS.
8. Xác thực certificate/hostname; không dùng trust wildcard không kiểm soát.
9. Credential chỉ được truyền qua kết nối đáp ứng chính sách TLS.
10. SMTP timeout và error handling được cấu hình để tránh thread treo vô hạn.

### Build, deploy và vận hành

11. Docker/JAR artifact không chứa SMTP password.
12. CI/CD không in giá trị secret hoặc truyền qua command line dễ quan sát.
13. Actuator/diagnostic endpoint chỉ được expose theo quyền tối thiểu.
14. SMTP debug/auth debug không bật tùy tiện trên production.
15. Log và metric không chứa recipient/token/password hoặc object cấu hình nguyên vẹn.
16. Có phương án reload/restart khi rotate credential.
17. Có audit người/role truy cập secret và các lần thay đổi version.
18. Có quy trình revoke/rotate khi phát hiện credential bị lộ.

### Ứng dụng và kiểm thử

19. Cấu hình SMTP bắt buộc thiếu thì fail fast, không im lặng dùng password mặc định.
20. Local/unit test dùng SMTP sink, fake sender hoặc credential test riêng.
21. Lỗi auth sau rotation không bị retry dồn dập bằng password cũ.
22. Các email chưa gửi giữ trạng thái thích hợp để retry sau khi cấu hình được sửa.
23. Không in secret trong exception, support ticket hoặc nội dung báo lỗi công khai.
24. Có test chứng minh ứng dụng không dùng nguồn secret production trong profile local.

## 22. Mẫu kiến trúc an toàn

~~~text
                       Source repository
                              |
                              | no SMTP secret
                              v
                          CI / build
                              |
                              | immutable JAR / image
                              v
                      Runtime deployment
                              |
          +-------------------+------------------+
          |                                      |
          v                                      v
   Workload identity                       Mail properties
          |                               - host / port
          v                               - TLS / timeout
   Secret manager                          - no password
          |
          v
   Protected secret delivery
     (file mount / controlled environment)
          |
          v
   Spring Boot configuration binding
          |
          v
   JavaMailSender + TLS verification
          |
          v
   SMTP server / provider
          |
          v
   Success or classified error
          |
          v
   Outbox status / retry / safe metrics
~~~

Trong mô hình này, credential không đi vào source, build output hay dashboard. Runtime được phép đọc đúng secret cần dùng, Spring Mail gửi qua kênh TLS phù hợp và hệ thống giám sát chỉ nhận mã lỗi/trạng thái đã chuẩn hóa.

## Kết luận

**Bảo vệ secret trong cấu hình SMTP** không chỉ là chuyển `spring.mail.password` sang một biến môi trường. Một giải pháp đầy đủ phải bao phủ toàn bộ vòng đời credential: cấp phát, phân phối runtime, sử dụng qua TLS, hạn chế quyền đọc, tránh lộ qua log/Actuator/CI/image, xoay vòng và xử lý sự cố.

Với Spring Framework Mail, cách triển khai thường phù hợp là: **giữ host/port/TLS policy trong cấu hình không bí mật; cấp username/password hoặc token qua nguồn runtime được quản lý; bắt buộc TLS và xác thực server; không in secret ở bất kỳ đường logging nào; và có quy trình rotation/revoke rõ ràng**. Những nguyên tắc đó vừa giảm nguy cơ lộ credential, vừa giúp dịch vụ gửi email duy trì khả năng vận hành khi credential hết hạn, bị thay thế hoặc cần thu hồi khẩn cấp.
