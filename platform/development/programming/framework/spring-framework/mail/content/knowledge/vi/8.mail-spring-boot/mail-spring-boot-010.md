# Tách cấu hình bằng application properties và YAML

Trong một ứng dụng Spring Boot sử dụng Spring Framework Mail, mã Java thường chỉ cần tạo nội dung email rồi gọi **JavaMailSender.send(...)**. Phần khó hơn nằm ở cấu hình kết nối: máy chủ SMTP là gì, sử dụng cổng nào, có cần xác thực không, dùng STARTTLS hay TLS ngay từ đầu, và các thao tác mạng được phép chờ bao lâu.

Nếu mọi thông số nằm trực tiếp trong class Java, việc chuyển từ môi trường phát triển sang production sẽ kéo theo sửa code và dễ làm lộ credential. Spring Boot hỗ trợ **externalized configuration** để tách thông số khỏi nghiệp vụ. Hai định dạng phổ biến nhất là **application.properties** và **application.yml** (hoặc **application.yaml**).

Bài này giải thích cách khai báo cấu hình gửi thư bằng cả hai định dạng, cách Spring Boot đưa giá trị vào **JavaMailSenderImpl**, cách phân chia theo profile và cách nạp thông tin nhạy cảm từ môi trường triển khai.

## 1. Mô hình: mã nghiệp vụ và cấu hình sender là hai trách nhiệm khác nhau

Ví dụ một service gửi thông báo trong Spring:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NoticeService {

    private final JavaMailSender mailSender;

    public NoticeService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotice(String recipient) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("noreply@example.org");
        mail.setTo(recipient);
        mail.setSubject("Thông báo");
        mail.setText("Bạn có một thông báo mới.");

        mailSender.send(mail);
    }
}
~~~

Service quyết định nội dung, địa chỉ gửi hiển thị và người nhận. Nó không cần biết hostname SMTP hoặc thông tin xác thực. Các thông số đó nên thuộc **cấu hình hạ tầng gửi email**.

~~~text
        Code nghiệp vụ Spring
                 |
       JavaMailSender.send(...)
                 |
                 v
         JavaMailSenderImpl
                 ^
                 |
       Spring Boot auto-config
                 ^
                 |
      application.properties
           hoặc
        application.yml
                 ^
                 |
      Profile / Environment
           / Secret store
~~~

**JavaMailSender** là giao diện gửi mail; **JavaMailSenderImpl** là một implementation dựa trên Jakarta Mail. Trong Spring Boot, khi có các dependency và điều kiện cấu hình phù hợp, cơ chế mail auto-configuration tạo bean cho ứng dụng.

Vì vậy, thay đổi từ SMTP sandbox sang SMTP production thường nên là thay đổi **cấu hình triển khai**, không phải thay đổi nội dung của **NoticeService**.

## 2. application.properties và application.yml khác nhau thế nào?

Cả hai định dạng cùng được Spring Boot nạp vào hệ thống cấu hình để tìm các key như **spring.mail.host**.

**Dạng properties** dùng các cặp key-value phẳng:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.protocol=smtp
~~~

**Dạng YAML** dùng cấu trúc lồng nhau:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    protocol: smtp
~~~

Về ý nghĩa cấu hình, hai ví dụ là tương đương.

| Đặc điểm | application.properties | application.yml |
| --- | --- | --- |
| Cấu trúc | Mỗi dòng chứa key đầy đủ | Các cấp được xác định bằng thụt lề |
| Tìm key | Dễ tìm nguyên chuỗi spring.mail.host | Cần hiểu cấu trúc cha/con |
| Lặp tiền tố | Có, ví dụ spring.mail.* lặp nhiều lần | Ít lặp hơn |
| Lỗi thường gặp | Viết sai tên key hoặc escape | Thụt lề sai, không quote ký tự đặc biệt |
| Profiles | Có hỗ trợ | Có hỗ trợ |
| Phù hợp với JavaMailSender | Có | Có |

Tập thuộc tính của Spring Boot là như nhau. **YAML không tạo ra loại JavaMailSender mới**, cũng không làm SMTP thay đổi giao thức.

Có thể dùng đuôi **.yml** hoặc **.yaml**. Nên duy trì một quy ước trong dự án để người bảo trì dễ tìm cấu hình.

## 3. Điều kiện tối thiểu để Spring Boot tạo sender

Với dự án Gradle, thường khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Đoạn này chỉ minh họa phần dependencies, giả định dự án đã cấu hình các plugin và repository cần thiết.

Spring Boot có thể tự cấu hình **JavaMailSenderImpl** khi classpath và thiết lập mail đáp ứng điều kiện auto-configuration, chẳng hạn có **spring.mail.host** hoặc cấu hình mail Session thích hợp. Khi đó service chỉ cần tiêm:

~~~java
private final JavaMailSender mailSender;
~~~

Không cần tự gọi **new JavaMailSenderImpl()** trong mỗi service.

Tuy nhiên, chỉ thêm dependency vẫn chưa đủ để gửi được thư. Ứng dụng còn cần endpoint SMTP thực, quyền gửi và thông tin xác thực theo yêu cầu của nhà cung cấp.

### Các thuộc tính Boot quan trọng

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **spring.mail.host** | Máy chủ SMTP |
| **spring.mail.port** | Cổng SMTP |
| **spring.mail.username** | Tài khoản dùng xác thực |
| **spring.mail.password** | Credential dùng xác thực |
| **spring.mail.protocol** | Transport protocol, thường là smtp |
| **spring.mail.default-encoding** | Charset mặc định khi tạo thông điệp |
| **spring.mail.properties[...]** | Map chứa các JavaMail Properties |
| **spring.mail.test-connection** | Yêu cầu kiểm tra kết nối khi khởi động trong cấu hình hỗ trợ |
| **spring.mail.jndi-name** | Tham chiếu mail Session từ JNDI, dùng trong một số hạ tầng |

Cần tách hai tầng: **spring.mail.host** là property Boot, còn **mail.smtp.auth** là property của SMTP transport do Jakarta Mail xử lý.

## 4. Ví dụ đầy đủ bằng application.properties

Giả sử nhà cung cấp SMTP yêu cầu AUTH và STARTTLS trên cổng 587. Tệp **src/main/resources/application.properties** có thể chứa:

~~~properties
# Đích kết nối
spring.mail.host=${SMTP_HOST}
spring.mail.port=${SMTP_PORT:587}
spring.mail.protocol=smtp

# Credential nhận từ môi trường chạy
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

# Mã hóa nội dung
spring.mail.default-encoding=UTF-8

# Thuộc tính dành cho Jakarta Mail SMTP
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true

# Timeout: mili giây
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

Giải thích:

- **host** và **port** xác định endpoint SMTP. Port 587 chỉ là ví dụ cho SMTP submission có STARTTLS.
- **username** và **password** lấy từ biến môi trường. Không viết mật khẩu thật trong source.
- **default-encoding=UTF-8** thích hợp cho thư tiếng Việt.
- **mail.smtp.auth=true** yêu cầu transport dùng xác thực SMTP theo cấu hình.
- **starttls.enable=true** cho phép client nâng cấp kết nối sang TLS nếu server hỗ trợ.
- **starttls.required=true** yêu cầu quá trình nâng cấp thành công; nếu không được thì phiên gửi thất bại.
- **ssl.checkserveridentity=true** bật kiểm tra danh tính hostname của SMTP server khi dùng TLS theo khả năng provider.
- Ba timeout giới hạn các bước kết nối, đọc và ghi dữ liệu trên mạng.

Con số **5000** biểu thị 5.000 mili giây, tức 5 giây. Đây là giá trị minh họa; ứng dụng thật phải chọn theo mạng, provider và kích thước email.

### 4.1. Placeholder lấy giá trị từ bên ngoài

Cú pháp:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=${SMTP_PORT:587}
~~~

có ý nghĩa:

- **${SMTP_HOST}**: yêu cầu Spring giải quyết giá trị tên SMTP_HOST từ Environment.
- **${SMTP_PORT:587}**: lấy SMTP_PORT nếu được cấp, nếu không thì dùng 587.
- Placeholder được Spring xử lý trong quá trình giải quyết cấu hình, không phải tính năng đặc biệt của SMTP.

Ví dụ môi trường chạy có:

~~~text
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=mailer@example.org
SMTP_PASSWORD=<secret supplied by deployment>
~~~

Đây là tên và giá trị minh họa. Trong thực tế, biến phải được cấp **cho process Java**, bằng cơ chế của shell, IDE, container, hệ thống triển khai hoặc secret manager.

Nếu một placeholder bắt buộc không có giá trị, ứng dụng có thể thất bại khi binding/khởi tạo sender. Đây là tín hiệu cấu hình thiếu dữ liệu, không nên khắc phục bằng cách hard-code password vào file.

### 4.2. Tránh fallback cho bí mật

Không nên viết:

~~~properties
spring.mail.password=${SMTP_PASSWORD:actual-production-password}
~~~

Vì giá trị fallback có thể được commit, đóng gói hoặc hiển thị trong file cấu hình. Với credential, yêu cầu hạ tầng cung cấp giá trị là lựa chọn dễ kiểm soát hơn.

## 5. Ví dụ tương đương bằng application.yml

Nếu dự án dùng YAML, cùng ý nghĩa có thể biểu diễn:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8

    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Về mặt cấu trúc:

~~~text
spring
└── mail
    ├── host
    ├── port
    ├── protocol
    ├── username
    ├── password
    ├── default-encoding
    └── properties
        ├── mail.smtp.auth
        ├── mail.smtp.starttls.enable
        ├── mail.smtp.starttls.required
        ├── mail.smtp.ssl.checkserveridentity
        └── timeout...
~~~

Ở đây, map **properties** truyền các JavaMail Properties cho implementation gửi thư.

**Tại sao các key trong properties có dấu ngoặc vuông và dấu nháy?**

Tên **mail.smtp.starttls.enable** phải được bảo toàn như một **key nguyên vẹn** của map. Cách viết **"[mail.smtp.starttls.enable]"** trong YAML sử dụng ký pháp bracket của Spring Boot Binder và quote để YAML hiểu đó là một tên key, tránh việc diễn giải dấu ngoặc theo cú pháp collection.

Trong application.properties, dạng tương ứng:

~~~properties
spring.mail.properties[mail.smtp.starttls.enable]=true
~~~

Một số ví dụ còn viết dạng phẳng **spring.mail.properties.mail.smtp.starttls.enable=true**; với map binding, dạng đó có thể hoạt động. Tuy nhiên, sử dụng bracket rõ ràng giúp thống nhất ý định giữ nguyên tên key mà transport cần.

### 5.1. Vì sao các giá trị trong map được quote?

YAML có kiểu dữ liệu như boolean và number. JavaMail Properties lại thường diễn giải các giá trị **true**, **false**, **5000** dưới dạng chuỗi.

Ví dụ sử dụng **"true"** và **"5000"** giúp người đọc hiểu đây là các giá trị truyền cho provider. Spring Boot có cơ chế chuyển đổi kiểu trong quá trình binding, nhưng cách viết này giảm nhầm lẫn khi sao chép sang cấu hình của Jakarta Mail.

### 5.2. Thụt lề đúng

Đúng:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
~~~

Sai với ý định đặt **spring.mail.port**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
  port: 587
~~~

Trong ví dụ sai, **port** là con của **spring**, không phải của **spring.mail**. Vì vậy không tạo key **spring.mail.port**.

Dùng khoảng trắng để thụt lề YAML, tránh tab. Hai khoảng trắng mỗi cấp là quy ước dễ đọc.

### 5.3. Khi nào cần quote giá trị YAML?

Với các giá trị có dấu hai chấm, dấu # hoặc ký hiệu YAML, quote để tránh parser hiểu nhầm:

~~~yaml
app:
  mail:
    display-name: "Bộ phận hỗ trợ: Việt Nam"
    subject-prefix: "[Support] "
~~~

Đây là ví dụ cấu hình ứng dụng tự định nghĩa, không phải key SMTP built-in. Một chuỗi trông đơn giản nhưng chứa ký tự cú pháp có thể cần dấu nháy để giữ nguyên giá trị.

## 6. Phân biệt thuộc tính Spring Boot và Jakarta Mail

Cần biết khi nào dùng **spring.mail.*** và khi nào dùng **mail.smtp.***.

~~~text
application.yml / application.properties
                 |
                 v
         Spring Boot MailProperties
                 |
          +------+------+
          |             |
          v             v
 host, port, user   properties Map
          |             |
          v             v
    JavaMailSenderImpl  Jakarta Mail properties
          |             |
          +------+------+
                 |
                 v
          SMTP transport
~~~

Bảng quy đổi:

| Mục đích | Spring Boot | Tầng Java/Jakarta Mail |
| --- | --- | --- |
| SMTP host | spring.mail.host | JavaMailSenderImpl.setHost |
| SMTP port | spring.mail.port | JavaMailSenderImpl.setPort |
| Username | spring.mail.username | JavaMailSenderImpl.setUsername |
| Password | spring.mail.password | JavaMailSenderImpl.setPassword |
| Protocol | spring.mail.protocol | JavaMailSenderImpl.setProtocol |
| Charset | spring.mail.default-encoding | JavaMailSenderImpl.setDefaultEncoding |
| SMTP AUTH | spring.mail.properties[mail.smtp.auth] | mail.smtp.auth |
| STARTTLS | spring.mail.properties[mail.smtp.starttls.enable] | mail.smtp.starttls.enable |
| Require TLS upgrade | spring.mail.properties[mail.smtp.starttls.required] | mail.smtp.starttls.required |
| Implicit TLS | spring.mail.properties[mail.smtp.ssl.enable] | mail.smtp.ssl.enable |
| Connection timeout | spring.mail.properties[mail.smtp.connectiontimeout] | mail.smtp.connectiontimeout |
| Read timeout | spring.mail.properties[mail.smtp.timeout] | mail.smtp.timeout |
| Write timeout | spring.mail.properties[mail.smtp.writetimeout] | mail.smtp.writetimeout |

Nếu viết Java cấu hình sender thủ công:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.org");
sender.setPort(587);
sender.getJavaMailProperties().put(
        "mail.smtp.starttls.enable", "true"
);
~~~

thì khi dùng Boot auto-configuration, cách biểu diễn tương đương là:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.properties[mail.smtp.starttls.enable]=true
~~~

Sai lầm phổ biến là tự tạo key **spring.mail.smtp.auth=true** rồi chờ Spring Boot hiểu thành thuộc tính SMTP. Với cấu hình chuẩn, cần dùng **spring.mail.properties[...]**.

## 7. Tách cấu hình chung và cấu hình riêng môi trường

Ứng dụng gửi thư có thể chạy trong ba môi trường:

| Môi trường | SMTP endpoint | Xác thực và bảo mật |
| --- | --- | --- |
| Local | SMTP capture server, ví dụ localhost:1025 | Có thể không AUTH/TLS trong sandbox nội bộ |
| Staging | SMTP sandbox hoặc tài khoản thử nghiệm | Theo chính sách của provider |
| Production | SMTP service chính thức | AUTH/TLS và secret được quản lý |

Cùng một service Java có thể chạy ở mọi môi trường nếu cấu hình được tách hợp lý. Spring Boot hỗ trợ **profiles** để đọc tệp theo môi trường.

Ví dụ cấu trúc:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-prod.yml
~~~

### 7.1. application.yml: giá trị dùng chung

~~~yaml
spring:
  mail:
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Các timeout và bảng mã dùng chung không cần lặp ở mọi profile khi chúng có cùng giá trị.

### 7.2. application-local.yml: dùng SMTP capture server

~~~yaml
spring:
  mail:
    host: localhost
    port: 1025
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
~~~

Cấu hình này **chỉ phù hợp khi** SMTP capture server nội bộ thực sự không yêu cầu AUTH/TLS. Không áp dụng tùy tiện cho SMTP server production.

Mục tiêu của môi trường local là quan sát những email mà ứng dụng tạo mà không vô tình gửi thư tới người dùng thật.

### 7.3. application-prod.yml: gửi qua SMTP server chính thức

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}

    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
~~~

Spring Boot kết hợp cấu hình chung với các giá trị riêng profile đang active theo thứ tự ưu tiên của Config Data. Các key giống nhau có thể được ghi đè theo nguồn có ưu tiên cao hơn.

### 7.4. Kích hoạt profile

Qua biến môi trường:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Hoặc tham số chạy ứng dụng:

~~~text
java -jar mail-demo.jar --spring.profiles.active=prod
~~~

Trong môi trường development, có thể chọn **local** thay cho **prod**.

Không nên tự đặt **spring.profiles.active** trong chính file **application-prod.yml** rồi mong nó tự kích hoạt. Profile phải được chọn từ nguồn cấu hình hợp lệ có hiệu lực trước khi tệp riêng profile được nạp.

### 7.5. Profile không phải nơi bảo quản password

Tệp **application-prod.yml** vẫn có thể được commit vào Git. Vì vậy, cấu hình production nên chứa **placeholder** chứ không chứa mật khẩu thật:

~~~yaml
spring:
  mail:
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Tên profile giúp chọn **nhóm cấu hình**, còn secret store hoặc environment của deployment quyết định **giá trị bí mật**.

## 8. Cấu hình profiles tương tự bằng application.properties

Không cần chuyển sang YAML chỉ để dùng profile. Một dự án cũng có thể có:

~~~text
src/main/resources/
├── application.properties
├── application-local.properties
└── application-prod.properties
~~~

Tệp chung **application.properties**:

~~~properties
spring.mail.protocol=smtp
spring.mail.default-encoding=UTF-8
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

Tệp **application-local.properties**:

~~~properties
spring.mail.host=localhost
spring.mail.port=1025
spring.mail.properties[mail.smtp.auth]=false
spring.mail.properties[mail.smtp.starttls.enable]=false
~~~

Tệp **application-prod.properties**:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=${SMTP_PORT:587}
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Hai bộ ví dụ YAML/properties đều thực hiện mục tiêu: chia **cấu hình chung**, **local** và **prod** mà không sửa lớp JavaMailSender ở service.

Một dự án có thể trộn định dạng, nhưng chọn cùng một định dạng cho các tệp cùng nhóm thường giảm nhầm lẫn khi vận hành.

## 9. Thứ tự ưu tiên khi nhiều nguồn có cùng một key

Spring Boot không chỉ đọc một file duy nhất. Ứng dụng có thể nhận cấu hình từ:

- Tệp application đóng gói trong JAR.
- Tệp application nằm ngoài JAR.
- Tệp dành cho profile đang active.
- Biến môi trường của hệ điều hành.
- Java system properties.
- Tham số dòng lệnh.
- Các nguồn được import hoặc cấu hình riêng.

Ví dụ:

~~~yaml
# application-prod.yml
spring:
  mail:
    host: smtp.primary.example.org
~~~

Nhưng môi trường chạy có:

~~~text
SPRING_MAIL_HOST=smtp.backup.example.org
~~~

Trong cơ chế property source thông dụng của Boot, biến môi trường **SPRING_MAIL_HOST** có thể ghi đè giá trị **spring.mail.host** từ file. Nếu người vận hành chỉ đọc YAML, họ có thể tưởng ứng dụng đang dùng primary endpoint.

### 9.1. Quy tắc định hướng

Trong cấu hình Spring Boot mặc định, thường có thể hiểu:

1. **Command-line arguments** kiểu **--spring.mail.host=...** có thể ghi đè biến môi trường và nhiều nguồn cấu hình.
2. **Biến môi trường** có thể ghi đè application files.
3. **Java system properties** cũng là nguồn có ưu tiên cao hơn nhiều cấu hình trong file.
4. **Cấu hình ngoài JAR** thường ưu tiên hơn cấu hình đóng gói bên trong, trong thứ tự Config Data mặc định.
5. **Tệp riêng cho profile active** ghi đè giá trị tương ứng từ cấu hình chung trong phạm vi quy tắc nạp Config Data.

Đây là quy tắc định hướng, không phải danh sách đầy đủ mọi thứ tự nguồn. Một ứng dụng có **spring.config.import**, custom PropertySource, test properties hoặc cấu hình launcher đặc biệt có thể cần xét quy tắc ưu tiên cụ thể của phiên bản Spring Boot đang dùng.

### 9.2. Có cả application.properties lẫn application.yml

Nếu hai tệp cùng tồn tại ở một location và chứa key trùng nhau, Spring Boot thường ưu tiên **.properties** hơn YAML tại location đó.

~~~text
src/main/resources/application.properties
src/main/resources/application.yml
~~~

Đừng dùng trùng lặp này làm cơ chế chuyển đổi production/local ngầm. Nên có một nguồn rõ ràng cho mỗi key và dùng profile hoặc override có chủ đích khi cần.

### 9.3. Khác biệt giữa giá trị trong file và giá trị cuối cùng

Đừng chỉ hỏi “application.yml ghi gì?”. Câu hỏi vận hành thực sự là:

> Bean JavaMailSender đang dùng cấu hình nào sau khi Spring Environment giải quyết profile và các property source?

Nếu người vận hành chỉnh một tệp mà ứng dụng vẫn kết nối tới server cũ, hãy kiểm tra nguồn ghi đè, thời điểm ứng dụng được deploy và việc sender có được tạo thủ công hay không.

## 10. Hai cách cấp cấu hình từ biến môi trường

### 10.1. Cách A: dùng placeholder có tên riêng

Trong **application.yml**:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Deployment cấp:

~~~text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
~~~

Đây là cách khai báo rõ những biến mà application cần.

### 10.2. Cách B: dùng tên biến môi trường trực tiếp của Spring Boot

Spring Boot hỗ trợ relaxed binding, ví dụ:

~~~text
SPRING_MAIL_HOST
SPRING_MAIL_PORT
SPRING_MAIL_USERNAME
SPRING_MAIL_PASSWORD
~~~

Các biến này có thể cung cấp trực tiếp giá trị tương ứng với **spring.mail.host**, **spring.mail.port** và các key khác mà không cần placeholder tùy chọn trong file.

Cả hai cách đều phù hợp. Điều quan trọng là thống nhất quy ước:

- Nếu file yêu cầu **${SMTP_PASSWORD}**, deployment phải cấp biến tương ứng.
- Nếu chỉ cấp **SPRING_MAIL_PASSWORD**, ứng dụng có thể dùng binding/override trực tiếp, nhưng không nên viết placeholder cho một tên khác rồi mặc nhiên cho rằng mọi tình huống đều hoạt động như nhau.
- Khi có nhiều nguồn, phải hiểu thứ tự ưu tiên và giá trị thực tế đang có hiệu lực.

### 10.3. Spring Boot không mặc định đọc mọi file .env

Một file **.env** đặt cạnh repository không tự động trở thành Environment của JVM trong mọi cách chạy Spring Boot.

Shell, IDE, Docker Compose hoặc công cụ deployment có thể nạp file đó rồi tạo biến môi trường. Nếu không có thành phần nào thực hiện bước này, các biến như **SMTP_HOST** vẫn có thể không tồn tại đối với process Java.

Do đó, khi dùng .env phải biết **công cụ nào nạp file**, ai có quyền đọc, file có bị commit hay không và biến có được chuyển vào container/process thực sự đang chạy.

## 11. STARTTLS và implicit TLS cần cấu hình khác nhau

Hai cấu hình SMTP phổ biến:

### 11.1. Submission cổng 587 với STARTTLS

Trong properties:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=587
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Tương đương YAML:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
~~~

Luồng khái niệm: thiết lập kết nối TCP, SMTP greeting/EHLO, nâng cấp STARTTLS, xác thực nếu server yêu cầu, rồi gửi thư.

**starttls.enable** cho phép dùng STARTTLS khi server hỗ trợ, còn **starttls.required** buộc phải nâng cấp thành công. Nếu ứng dụng yêu cầu bảo mật kênh gửi, hai ý nghĩa này cần được phân biệt.

### 11.2. Cổng 465 với TLS ngay từ đầu

Trong properties:

~~~properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=465
spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.ssl.enable]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true
~~~

Tương đương YAML:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
~~~

Khi dùng implicit TLS, kết nối bắt đầu bằng TLS handshake trước khi trao đổi SMTP. Chỉ thay port từ 587 sang 465 mà bỏ qua cơ chế TLS của endpoint có thể khiến client chờ sai giao thức và timeout.

Port 587/465 là quy ước thường gặp; phải đối chiếu yêu cầu thật của provider. Không tắt xác minh chứng chỉ hoặc tin mọi hostname chỉ để khắc phục lỗi TLS.

## 12. Timeout và giới hạn của cấu hình sender

Ba key thông dụng:

| Thuộc tính | Giới hạn thao tác | Đơn vị |
| --- | --- | --- |
| **mail.smtp.connectiontimeout** | Thiết lập socket | Mili giây |
| **mail.smtp.timeout** | Đọc phản hồi | Mili giây |
| **mail.smtp.writetimeout** | Ghi dữ liệu | Mili giây |

Ví dụ YAML:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Hoặc properties:

~~~properties
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

Timeout giúp tránh chờ quá lâu khi SMTP server hoặc đường truyền gặp sự cố. Tuy nhiên, ba timeout 5 giây **không chứng minh tổng thời gian của send() sẽ chỉ 5 giây**, vì phiên gửi gồm nhiều bước và có thể có retry ở tầng khác.

Với ứng dụng phục vụ HTTP request, nên cân nhắc hàng đợi gửi thư và chính sách retry thay vì để request người dùng chờ quá lâu trên SMTP transport.

## 13. Cấu hình riêng cho ứng dụng không thuộc spring.mail.*

Ngoài các thuộc tính sender, ứng dụng có thể cần tên hiển thị, email From và cờ bật thông báo. Các giá trị này thuộc **nghiệp vụ gửi thông báo**, không phải kết nối SMTP.

Ví dụ YAML:

~~~yaml
app:
  notifications:
    from-address: noreply@example.org
    display-name: "Hệ thống thông báo"
    welcome-enabled: true
~~~

Dạng properties:

~~~properties
app.notifications.from-address=noreply@example.org
app.notifications.display-name=Hệ thống thông báo
app.notifications.welcome-enabled=true
~~~

Đây là **những key do ứng dụng tự định nghĩa**. Spring Boot không tự đưa **app.notifications.from-address** vào JavaMailSenderImpl; service hoặc class **@ConfigurationProperties** của ứng dụng phải đọc chúng.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        String fromAddress,
        String displayName,
        boolean welcomeEnabled
) {}
~~~

Record này cần được đăng ký qua cơ chế như **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties(NotificationProperties.class)**.

Phân biệt:

- **spring.mail.***: kết nối và transport sender.
- **app.notifications.***: lựa chọn và hành vi nghiệp vụ do ứng dụng tự kiểm soát.

Không nên đặt thông tin nghiệp vụ vào các key transport tùy tiện hoặc tạo các key **spring.mail.custom-from** rồi cho rằng Boot sẽ tự sử dụng chúng.

## 14. Một ví dụ hoàn chỉnh: service không phụ thuộc định dạng cấu hình

Cấu hình có thể là properties hoặc YAML, nhưng Java service vẫn có thể giữ nguyên:

~~~java
package com.example.maildemo;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ConfirmationMailService {

    private final JavaMailSender sender;
    private final NotificationProperties options;

    public ConfirmationMailService(
            JavaMailSender sender,
            NotificationProperties options
    ) {
        this.sender = sender;
        this.options = options;
    }

    public void sendConfirmation(String recipient) {
        if (!options.welcomeEnabled()) {
            return;
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(options.fromAddress());
        message.setTo(recipient);
        message.setSubject("Xác nhận đăng ký");
        message.setText("Chúng tôi đã nhận được đăng ký của bạn.");

        sender.send(message);
    }
}
~~~

Ví dụ giả định **NotificationProperties** ở mục trước đã được đăng ký làm bean. Service nhận **JavaMailSender** từ Spring Boot và cấu hình nghiệp vụ từ **app.notifications.***.

Khi chuyển môi trường, không cần tạo lại sender trong service. Spring Boot sẽ giải quyết các property source khi khởi động và cấu hình bean phù hợp.

### Nếu dùng MimeMessageHelper

Khi cần HTML hoặc attachment, vẫn sử dụng cùng sender:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtmlNotice(String recipient)
        throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, false, "UTF-8"
    );

    helper.setFrom(options.fromAddress());
    helper.setTo(recipient);
    helper.setSubject("Thông báo");
    helper.setText("<p>Bạn có <strong>thông báo mới</strong>.</p>", true);

    sender.send(message);
}
~~~

Kiểu message có thể khác nhau, nhưng host, port, TLS, AUTH và timeout vẫn đến từ sender được cấu hình, không từ việc dùng SimpleMailMessage hay MimeMessage.

## 15. Khi Spring Boot không dùng cấu hình như mong đợi

### 15.1. Thiếu mail starter

Có application.yml chưa đủ để có JavaMailSender bean. Classpath cần thư viện phù hợp để Boot auto-config hoạt động.

### 15.2. Chưa khai báo host hoặc Session phù hợp

Nếu không có giá trị đầu vào mà auto-configuration yêu cầu, bean gửi mail có thể không được tạo. Khi đó cần xác định điều kiện kích hoạt sender, không chỉ quan sát lỗi thiếu bean trong service.

### 15.3. Có JavaMailSender bean thủ công

Nếu ứng dụng đã khai báo:

~~~java
@Bean
public JavaMailSender javaMailSender() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.manual.example.org");
    return sender;
}
~~~

auto-configuration của Boot thường sẽ nhường chỗ cho bean người dùng định nghĩa. Những khóa **spring.mail.host** trong YAML không nhất thiết được áp dụng vào bean tự tạo nếu code không chủ động đọc.

Vì vậy, nên chọn một cơ chế rõ ràng:

- Boot auto-config sử dụng **spring.mail.***.
- Bean tự tạo đọc cấu hình thông qua Environment/ConfigurationProperties có quy tắc xác định.

Tránh cấu hình bean thủ công và file application ở hai nơi rồi cho rằng Boot tự hợp nhất tất cả.

### 15.4. Mail Session từ JNDI

Một số application server quản lý sẵn **jakarta.mail.Session**. Spring Boot có thể được cấu hình để tham chiếu session đó qua **spring.mail.jndi-name** trong ngữ cảnh được hỗ trợ.

Đây là tình huống nâng cao. Với ứng dụng SMTP độc lập, cấu hình host/port/credential trực tiếp thường dễ hiểu hơn. Khi sử dụng Session do hạ tầng cấp, cần hiểu rõ nguồn thuộc tính và thứ tự ưu tiên.

## 16. Cách tìm giá trị cấu hình có hiệu lực

Khi một ứng dụng gửi thư không đúng SMTP endpoint, cần kiểm tra:

1. Profile thực tế đang active.
2. Tệp application nào được đóng gói và nạp.
3. Biến môi trường và command-line args có ghi đè hay không.
4. Có external config hoặc import nào thay đổi giá trị không.
5. Bean JavaMailSender có được tạo tự động hay thủ công.
6. Key **spring.mail.properties[...]** có được chuyển nguyên vẹn tới Jakarta Mail không.

Có thể đọc một số giá trị không nhạy cảm qua Environment:

~~~java
import org.springframework.core.env.Environment;

public String mailEndpoint(Environment env) {
    String host = env.getProperty(
            "spring.mail.host", "(not configured)"
    );
    String port = env.getProperty(
            "spring.mail.port", "(default)"
    );
    return host + ":" + port;
}
~~~

Đây là ví dụ về cách đọc property. Nếu bean sender được tạo thủ công hoặc dùng JNDI, Environment không nhất thiết phản ánh mọi thuộc tính cuối cùng của bean đó.

**Không log password, token, toàn bộ Environment hoặc JavaMail Session Properties mà chưa kiểm tra dữ liệu nhạy cảm.**

Trong ứng dụng có Spring Boot Actuator, các endpoint quan sát Environment/configuration có thể hỗ trợ chẩn đoán theo thiết lập bảo mật và cơ chế che giá trị nhạy cảm. Không nên mở endpoint cấu hình công khai chỉ để debug email.

### Các lỗi hay gặp

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Không tạo được JavaMailSender bean | Dependency, host, điều kiện auto-config |
| Host khác cấu hình trong YAML | Profile, biến môi trường, system properties, external config |
| AUTH thất bại | Credential, mail.smtp.auth, TLS, chính sách provider |
| STARTTLS không hoạt động | Cổng, mail.smtp.starttls.enable/required, capability server |
| TLS handshake thất bại | Sai chế độ implicit TLS/STARTTLS, hostname, certificate chain |
| Send chờ rất lâu | Connection/read/write timeout |
| Gửi được local nhưng không gửi được prod | Endpoint, firewall, secret, quyền account, provider policy |
| Gửi được nhưng không thấy inbox | Bounce, spam, quota, SPF/DKIM/DMARC, trạng thái chuyển phát |

Lỗi SMTP có thể xảy ra sau khi kết nối đã thành công, ví dụ người nhận bị từ chối hoặc thư quá lớn. **testConnection** không thay thế được việc gửi thử có kiểm soát.

## 17. spring.mail.test-connection có giải quyết toàn bộ vấn đề không?

Spring Boot hỗ trợ một tùy chọn kiểm tra kết nối mail trong những cấu hình phù hợp:

~~~properties
spring.mail.test-connection=true
~~~

Hoặc YAML:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Khi cơ chế kiểm tra được kích hoạt, Boot có thể thử kết nối SMTP trong quá trình startup. Điều này giúp phát hiện host/port hoặc thông tin xác thực sai sớm hơn.

Nhưng cần phân biệt:

| Mốc | Có thể xác nhận | Không thể khẳng định |
| --- | --- | --- |
| JavaMailSender bean tạo thành công | Có đối tượng sender | SMTP server thực sự truy cập được |
| Kiểm tra kết nối thành công | Thiết lập phiên tới server theo cấu hình hiện tại | Một recipient cụ thể được phép nhận |
| send() hoàn tất | Yêu cầu gửi hoàn tất ở lớp gửi theo phản hồi nhận được | Người nhận đã mở email |
| Provider báo delivery | Có tín hiệu chuyển phát theo định nghĩa provider | Người dùng đã đọc nội dung |

Bật kiểm tra kết nối khi startup cũng làm ứng dụng phụ thuộc khả năng truy cập SMTP ở thời điểm khởi động. Với một dịch vụ chỉ có chức năng gửi email, chính sách này có thể phù hợp; với ứng dụng nhiều chức năng, có thể muốn kiểm tra health riêng và xử lý gửi qua queue.

## 18. Tình huống: dùng environment variables khi triển khai production

Giả sử một nhóm dùng chung một bản build Spring Boot cho local và production.

**Trong repository:**

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-prod.yml
~~~

**Trong application.yml:** cấu hình protocol, encoding, timeout chung.

**Trong application-local.yml:** SMTP capture server của môi trường phát triển.

**Trong application-prod.yml:** host, port và cờ TLS của production, lấy credential từ placeholder.

**Trong deployment:** cấp những biến sau dưới cơ chế quản lý bí mật:

~~~text
SPRING_PROFILES_ACTIVE=prod
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=mailer@example.org
SMTP_PASSWORD=<protected runtime secret>
~~~

Đây là mô hình giúp **cùng một source Java** hoạt động trong nhiều môi trường. Khác biệt giữa local và prod được thể hiện ở property source, còn logic gửi email không cần tự nhận biết tên môi trường.

### Vì sao không đặt sẵn SPRING_PROFILES_ACTIVE=local trong bản build?

Nếu môi trường production quên ghi đè, ứng dụng có thể kết nối nhầm SMTP sandbox. Một quy trình triển khai tốt nên chủ động cấp profile và kiểm tra các giá trị bắt buộc cho từng môi trường.

### Có bắt buộc phải tách mọi file theo profile không?

Không. Nếu ứng dụng nhỏ và chỉ có một môi trường, một file cấu hình cùng các environment variables có thể đủ. Profile hữu ích khi có **các nhóm giá trị thực sự khác nhau**. Tách quá nhiều file chứa mỗi nơi một key cũng khiến việc truy vết khó hơn.

## 19. Những nguyên tắc bảo mật cần giữ khi tách cấu hình

### 19.1. Không commit thông tin xác thực

Không lưu mật khẩu SMTP hoặc token thật trong application.properties, application.yml, tệp mẫu được commit, log, ảnh chụp màn hình hay tài liệu. Biến môi trường hoặc secret manager phải được cấp với quyền truy cập thích hợp.

### 19.2. Tách cấu hình với quyền gửi thư

Địa chỉ recipient hoặc From hợp lệ về cú pháp vẫn có thể trái với quyền nghiệp vụ. Việc cấu hình JavaMailSender đúng không thay thế bước kiểm tra ai được phép nhận nội dung nào.

### 19.3. Không tắt TLS chỉ để gửi được

Nếu gặp lỗi TLS, hãy kiểm tra hostname, chứng chỉ, truststore của JDK, port và kiểu kết nối. Đừng dùng cấu hình tin mọi chứng chỉ hoặc bỏ xác minh máy chủ trong production.

### 19.4. Timeout phải hữu hạn và phù hợp

Cấu hình timeout giúp ứng dụng tránh bị treo vô hạn tại một số thao tác mạng, nhưng cũng cần giới hạn retry, hàng đợi, quản lý trạng thái gửi và cơ chế quan sát lỗi.

### 19.5. Tránh in cấu hình nhạy cảm khi chẩn đoán

Chỉ log dữ liệu cần thiết như môi trường, endpoint không bí mật, loại lỗi hoặc mã SMTP. Tránh ghi password, access token và nội dung thư nhạy cảm.

### 19.6. Phân biệt gửi và giao thư cuối cùng

JavaMailSender kết nối SMTP và chuyển message cho hệ thống gửi. Việc người nhận thực sự thấy thư trong inbox còn phụ thuộc hạ tầng chuyển phát, lọc spam, chính sách domain và trạng thái mailbox. Cấu hình sender đúng không tự bảo đảm tất cả các bước phía sau thành công.

## 20. Câu hỏi thực hành và củng cố

**Câu 1: Tôi đổi application.yml nhưng ứng dụng vẫn kết nối tới SMTP server cũ. Vì sao?**

Có thể có tệp properties trùng key, profile đang active khác, biến môi trường hoặc command-line args ghi đè, bean sender được tự tạo hoặc bản cấu hình mới chưa được deploy. Kiểm tra nguồn cấu hình có hiệu lực.

**Câu 2: Có cần dùng cả application.properties và application.yml không?**

Không. Chọn một định dạng chính thường đủ. Cả hai đều hỗ trợ spring.mail.* và Spring profiles.

**Câu 3: Nếu dùng application-prod.properties, tôi có cần viết lại mọi timeout từ application.properties không?**

Không, khi giá trị chung vẫn phù hợp và profile-specific file không ghi đè. Chỉ khai báo những key khác biệt theo môi trường.

**Câu 4: spring.mail.properties[mail.smtp.auth] là gì?**

Đó là một entry trong map JavaMail Properties mà Spring Boot chuyển cho SMTP transport. Nó khác với các thuộc tính trực tiếp như spring.mail.host.

**Câu 5: Có thể đặt SMTP_PASSWORD vào file .env không?**

Có thể dùng một hệ thống triển khai đọc .env rồi cấp thành biến môi trường, nhưng Spring Boot không tự động nạp mọi .env. Cần bảo vệ file và tránh commit secret.

**Câu 6: Có nên dùng port 465 với starttls.enable=true?**

Nếu endpoint 465 dùng implicit TLS theo cấu hình phổ biến, hãy dùng **mail.smtp.ssl.enable=true**. Port và cơ chế TLS phải tương thích với yêu cầu cụ thể của provider.

**Câu 7: Một biến SPRING_MAIL_HOST có thể ghi đè host trong YAML không?**

Trong cơ chế relaxed binding và ưu tiên property sources thông dụng của Spring Boot, có. Điều này hữu ích cho triển khai, nhưng cũng là nguyên nhân thường gặp khiến người đọc YAML hiểu sai giá trị có hiệu lực.

**Câu 8: Khi nào cần viết class @ConfigurationProperties riêng?**

Khi ứng dụng có nhóm cấu hình do mình sở hữu, như **app.notifications.from-address** hay **app.notifications.welcome-enabled**. Không cần tạo class riêng chỉ để đọc lại những spring.mail.* đã được Boot auto-config hỗ trợ.

**Câu 9: test-connection=true có gửi email thử không?**

Không. Nó phục vụ kiểm tra kết nối/phiên gửi theo cấu hình, không phải bằng chứng thư đã đến inbox.

**Câu 10: Có thể dùng chung code Java cho local và production không?**

Có. Service phụ thuộc JavaMailSender; profile và môi trường chạy quyết định sender kết nối đến endpoint nào. Đây là lợi ích chính của việc tách cấu hình.

## 21. Ghi nhớ về tách cấu hình Spring Boot Mail

**application.properties** và **application.yml** là hai cách biểu diễn cùng một hệ property source của Spring Boot. Với Spring Framework Mail, **spring.mail.host/port/username/password** khai báo thông số sender, còn **spring.mail.properties[...]** đưa những tùy chọn AUTH, TLS và timeout vào Jakarta Mail.

Hãy đặt **cấu hình dùng chung** trong application cơ sở, **khác biệt môi trường** trong profile hoặc external configuration, và **bí mật** trong nguồn được bảo vệ. Mã nghiệp vụ tiêm **JavaMailSender** để không phụ thuộc địa chỉ SMTP và cách quản lý credential.

Khi ứng dụng gửi thư không như mong đợi, cần truy tìm **giá trị cấu hình có hiệu lực** sau khi Spring Boot giải quyết toàn bộ property source, sau đó đối chiếu với endpoint và chính sách của SMTP server. Cách tổ chức này giúp cùng một ứng dụng triển khai nhất quán qua nhiều môi trường mà vẫn giữ được ranh giới rõ ràng giữa code, cấu hình và bí mật.
