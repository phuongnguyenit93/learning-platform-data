# JavaMailSenderImpl và các thuộc tính cấu hình

Trong ứng dụng Spring cần gửi email, một đoạn mã có thể chỉ gọi **JavaMailSender.send(...)**. Nhưng để lời gọi đó thực sự làm việc, ứng dụng phải biết **gửi đến máy chủ SMTP nào, qua cổng nào, xác thực bằng cách nào, bảo vệ kết nối ra sao và chờ tối đa bao lâu**. Thành phần đứng giữa API gửi thư của Spring và thư viện Jakarta Mail trong cấu hình phổ biến là **JavaMailSenderImpl**.

JavaMailSenderImpl là một implementation cụ thể của giao diện **JavaMailSender**. Nó quản lý cấu hình kết nối, tạo đối tượng **MimeMessage**, chuẩn bị phiên **Jakarta Mail** và gửi thông điệp thông qua transport. Spring Boot thường tự tạo bean triển khai này khi dự án có dependency và thuộc tính mail tương ứng, nên lập trình viên ít khi cần tự khởi tạo.

Chủ đề này tập trung vào **cấu hình sender**: ý nghĩa từng nhóm thuộc tính, hai cách cấu hình trong Spring, lựa chọn TLS và timeout, cách xác định lỗi, cùng các giới hạn mà cấu hình gửi email có thể bảo đảm.

## 1. JavaMailSenderImpl nằm ở đâu trong quá trình gửi thư?

Có thể nhìn luồng gửi như sau:

~~~text
Ứng dụng Spring
    |
    | JavaMailSender.send(...)
    v
JavaMailSender (giao diện)
    |
    v
JavaMailSenderImpl (implementation)
    |
    | host, port, username, password, protocol
    | JavaMail Properties, Jakarta Mail Session
    v
Jakarta Mail SMTP transport
    |
    | Kết nối, TLS, AUTH, MAIL FROM, RCPT TO, DATA
    v
SMTP server / dịch vụ gửi thư
    |
    v
Hạ tầng email tiếp tục chuyển phát
~~~

Các tầng có trách nhiệm khác nhau:

- **Mã nghiệp vụ** quyết định vì sao gửi email, gửi cho ai, nội dung nào và thời điểm nào.
- **JavaMailSender** là API mà mã nghiệp vụ phụ thuộc vào.
- **JavaMailSenderImpl** là thành phần cấu hình và thực hiện thao tác gửi bằng Jakarta Mail.
- **Jakarta Mail** cung cấp Session, MimeMessage và cơ chế transport SMTP.
- **SMTP server** tiếp nhận hoặc từ chối yêu cầu; server có thể xếp hàng, chuyển tiếp hoặc thông báo lỗi phát thư về sau.

Điểm quan trọng: **JavaMailSenderImpl không phải SMTP server**. Nó là phía **client** gửi thư. Cấu hình đúng chỉ cho phép client làm việc với server, không thay thế việc vận hành hay quản lý một máy chủ mail.

### 1.1. Những lớp thường gặp

| Lớp / giao diện | Vai trò |
| --- | --- |
| **MailSender** | Giao diện Spring cho việc gửi các SimpleMailMessage đơn giản |
| **JavaMailSender** | Giao diện mở rộng hỗ trợ tạo và gửi MimeMessage |
| **JavaMailSenderImpl** | Triển khai thường dùng dựa trên Jakarta Mail, có thuộc tính máy chủ và phiên gửi |
| **SimpleMailMessage** | Thông điệp văn bản đơn giản do Spring cung cấp |
| **MimeMessage** | Thông điệp Jakarta Mail, có thể chứa HTML, nhiều MIME part, attachment |
| **MimeMessageHelper** | Tiện ích của Spring giúp dựng MimeMessage |
| **jakarta.mail.Session** | Ngữ cảnh cấu hình và provider Jakarta Mail |
| **jakarta.mail.Transport** | Thành phần thực hiện trao đổi với transport server |

Trong mã ứng dụng, nên **tiêm JavaMailSender** thay vì ép mọi service phụ thuộc JavaMailSenderImpl. Nhờ vậy, việc chọn cách cấu hình hay thay đổi implementation không ảnh hưởng đến logic tạo thông báo.

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Các phương thức tạo thông điệp và gửi thư nằm tại đây.
}
~~~

Nếu thực sự cần truy cập API riêng của JavaMailSenderImpl như **testConnection()**, nên đặt logic đó ở lớp cấu hình hoặc chẩn đoán hạ tầng, không trộn vào nghiệp vụ gửi thư thông thường.

## 2. Đưa Spring Mail vào dự án

Với Spring Boot, cách thường dùng là khai báo starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter cung cấp tích hợp mail phù hợp với Spring Boot và các dependency Jakarta Mail cần thiết cho việc gửi thư. Trong ứng dụng Boot được cấu hình SMTP hợp lệ, cơ chế auto-configuration có thể tạo bean **JavaMailSender** dựa trên **JavaMailSenderImpl**.

Điểm cần hiểu về auto-configuration:

1. Có thư viện và điều kiện classpath cần thiết.
2. Có cấu hình mail thích hợp, chẳng hạn **spring.mail.host**.
3. Không có bean sender do ứng dụng tự cung cấp khiến cơ chế auto-config nhường quyền.
4. Các giá trị được binding từ cấu hình Boot rồi đưa vào implementation và JavaMail Properties.

Không nên giả định chỉ thêm dependency là có thể gửi được thư. Nếu không có địa chỉ SMTP server, thông tin xác thực hoặc kênh kết nối hợp lệ, ứng dụng vẫn chưa thể hoàn tất tác vụ gửi.

### 2.1. Spring Framework không đồng nhất với Spring Boot

**Spring Framework** cung cấp giao diện JavaMailSender và class JavaMailSenderImpl để sử dụng trong mọi môi trường Spring phù hợp. **Spring Boot** bổ sung cơ chế đọc **spring.mail.*** và tự cấu hình bean.

Nếu ứng dụng là Spring Framework thuần, bạn có thể tự khai báo JavaMailSenderImpl trong **@Configuration**. Nếu sử dụng Boot, thường chỉ cần khai báo **application.yml** và tiêm JavaMailSender.

Vì vậy, khi đọc một đoạn tài liệu cấu hình, cần phân biệt:

- **setHost(...)**, **setPort(...)**, **setUsername(...)**: setter của JavaMailSenderImpl.
- **spring.mail.host**, **spring.mail.port**, **spring.mail.username**: thuộc tính cấu hình Spring Boot.
- **mail.smtp.auth**, **mail.smtp.starttls.enable**: thuộc tính của SMTP transport do Jakarta Mail sử dụng.

Ba cách viết này phục vụ các tầng khác nhau.

## 3. Những thuộc tính trực tiếp của JavaMailSenderImpl

JavaMailSenderImpl cho phép thiết lập một số giá trị cốt lõi bằng setter. Ví dụ:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();

sender.setHost("smtp.example.org");
sender.setPort(587);
sender.setProtocol("smtp");
sender.setUsername("mailer@example.org");
sender.setPassword("credential-from-secret-store");
sender.setDefaultEncoding("UTF-8");
~~~

Chuỗi credential trong ví dụ chỉ là ký hiệu minh họa; không được hard-code thông tin xác thực thực vào mã nguồn.

| Setter | Vai trò | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **setHost(String)** | Chỉ định hostname SMTP server | smtp.example.org | Phải là endpoint do nhà cung cấp xác nhận |
| **setPort(int)** | Chỉ định cổng kết nối transport | 587 | Cần phù hợp với TLS và yêu cầu server |
| **setProtocol(String)** | Chỉ định transport protocol | smtp | SMTP thường dùng để gửi thư |
| **setUsername(String)** | Cung cấp username khi server yêu cầu xác thực | mailer@example.org | Không đủ một mình để bảo đảm AUTH được bật |
| **setPassword(String)** | Cung cấp mật khẩu/credential phù hợp | Giá trị từ secret store | Không commit secret |
| **setDefaultEncoding(String)** | Đặt encoding mặc định để tạo MimeMessage | UTF-8 | Ảnh hưởng cách dựng nội dung, không quyết định TLS |
| **setJavaMailProperties(Properties)** | Truyền tập thuộc tính cho Jakarta Mail | mail.smtp.auth=true | Nơi cấu hình hành vi transport |
| **setSession(Session)** | Cung cấp Jakarta Mail Session đã được tạo sẵn | Session do hạ tầng quản lý | Trường hợp tích hợp nâng cao; cần hiểu thứ tự ưu tiên cấu hình |

Ngoài ra, JavaMailSenderImpl có thể thiết lập file type map mặc định nhằm hỗ trợ nhận diện kiểu MIME của tài nguyên; việc này khác với thiết lập SMTP host và TLS.

### 3.1. Giá trị mặc định không thay thế cấu hình thực tế

Các giá trị mặc định của implementation có thể khiến quá trình khởi tạo đối tượng không phát sinh lỗi, nhưng không có nghĩa đã kết nối thành công với một server gửi thư.

Ví dụ, giá trị port **-1** trong API có nghĩa sử dụng hành vi/cổng mặc định của provider khi kết nối, không có nghĩa port mạng -1 thực sự được sử dụng. Host và protocol cũng có giá trị mặc định tùy implementation. Với ứng dụng triển khai thực tế, nên chỉ rõ endpoint theo hướng dẫn của nhà cung cấp để tránh môi trường này gửi được còn môi trường khác lại kết nối nhầm.

### 3.2. Username và password có phải luôn bắt buộc?

Không phải mọi SMTP server đều cần cùng phương thức xác thực:

- Dịch vụ SMTP submission công khai hoặc dành cho ứng dụng thường yêu cầu AUTH.
- Một SMTP relay nội bộ có thể cho phép kết nối từ địa chỉ mạng đã được tin cậy, tùy chính sách.
- Nhà cung cấp hiện đại có thể yêu cầu credential ứng dụng hoặc token OAuth2, không phải mật khẩu đăng nhập thông thường.

Nếu máy chủ yêu cầu AUTH, cần cung cấp **username**, **credential đúng loại** và bật thuộc tính transport phù hợp, thường là **mail.smtp.auth=true**. Đừng đặt mật khẩu rồi giả định mọi server đều tự thực hiện xác thực đúng cách.

Đặc biệt, việc chấp nhận gửi từ một relay dựa trên IP là chính sách của server; không nên bỏ AUTH một cách tùy tiện chỉ để khắc phục lỗi xác thực.

## 4. JavaMail Properties: nhóm thuộc tính điều khiển SMTP transport

JavaMailSenderImpl có nhóm thuộc tính riêng nhưng rất nhiều hành vi kết nối do **Jakarta Mail** quyết định thông qua **Properties**.

Ví dụ Java:

~~~java
Properties properties = sender.getJavaMailProperties();

properties.put("mail.smtp.auth", "true");
properties.put("mail.smtp.starttls.enable", "true");
properties.put("mail.smtp.starttls.required", "true");
properties.put("mail.smtp.connectiontimeout", "5000");
properties.put("mail.smtp.timeout", "5000");
properties.put("mail.smtp.writetimeout", "5000");
~~~

Trong ví dụ, các giá trị được lưu dưới dạng chuỗi để provider đọc theo hợp đồng cấu hình. Các khóa **mail.smtp.*** là thuộc tính Jakarta Mail của SMTP transport, không phải setter độc lập của JavaMailSenderImpl.

### 4.1. Nhóm xác thực

| Thuộc tính | Mục đích |
| --- | --- |
| **mail.smtp.auth** | Yêu cầu SMTP transport sử dụng xác thực khi kết nối theo cấu hình |
| **mail.smtp.auth.mechanisms** | Chỉ định hoặc giới hạn cơ chế AUTH được thử, khi cần theo yêu cầu provider |
| **mail.smtp.from** | Gợi ý envelope sender cho SMTP transport, độc lập với header From |
| **mail.smtp.localhost** | Danh tính hostname mà client dùng trong lời chào SMTP khi cần chỉ định |

Thông thường, ứng dụng chỉ cần quan tâm trước hết đến **mail.smtp.auth**, username và password/credential. Các thuộc tính nâng cao phải được đặt theo tài liệu provider.

Không nên đặt **mail.smtp.from** bằng một địa chỉ tùy ý để né chính sách miền gửi. Nó ảnh hưởng đến envelope sender và xử lý bounce, cần phù hợp với tài khoản, quyền và chính sách xác thực mail.

### 4.2. Nhóm TLS

| Thuộc tính | Mục đích |
| --- | --- |
| **mail.smtp.starttls.enable** | Thử nâng cấp kết nối SMTP sang TLS bằng STARTTLS khi server hỗ trợ |
| **mail.smtp.starttls.required** | Yêu cầu STARTTLS; nếu không thực hiện được thì từ chối tiếp tục phiên |
| **mail.smtp.ssl.enable** | Sử dụng TLS ngay khi thiết lập kết nối SMTP, thường dùng ở endpoint cổng 465 |
| **mail.smtp.ssl.checkserveridentity** | Bật kiểm tra danh tính hostname của server theo cơ chế hỗ trợ |
| **mail.smtp.ssl.protocols** | Giới hạn các phiên bản TLS được dùng khi cần, tùy JDK/provider |

**starttls.enable=true** và **starttls.required=true** có ý nghĩa khác nhau. Enable cho phép client dùng STARTTLS khi server cung cấp capability; Required buộc TLS phải được thiết lập thành công trước khi giao tiếp tiếp tục. Với một dịch vụ gửi thư yêu cầu mã hóa, đặt **required** giúp tránh tình huống kết nối không được nâng cấp như mong đợi.

Không nên bật bừa **mail.smtp.ssl.trust="*"** hoặc tắt kiểm tra chứng chỉ để “sửa nhanh” lỗi TLS trong môi trường production. Làm như vậy có thể phá vỡ khả năng xác minh máy chủ đích. Thay vào đó, kiểm tra hostname, certificate chain, JDK truststore và cấu hình của provider.

### 4.3. Nhóm timeout

| Thuộc tính | Thao tác bị giới hạn thời gian | Đơn vị thường sử dụng |
| --- | --- | --- |
| **mail.smtp.connectiontimeout** | Thiết lập kết nối TCP tới SMTP server | Mili giây |
| **mail.smtp.timeout** | Chờ đọc dữ liệu hoặc phản hồi từ SMTP server | Mili giây |
| **mail.smtp.writetimeout** | Chờ khi ghi dữ liệu qua kết nối | Mili giây |

Ví dụ:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=5000
mail.smtp.writetimeout=5000
~~~

Ba loại timeout khác nhau vì một request gửi mail có thể bị treo ở nhiều giai đoạn: kết nối không thiết lập được, server chậm trả lời hoặc đường truyền bị nghẽn khi gửi một attachment lớn.

Giá trị **5000** là 5 giây, được dùng để minh họa, không phải ngưỡng tối ưu cho mọi hệ thống. Chọn timeout dựa vào mạng, provider, khối lượng file và chính sách retry. Nhiều cấu hình transport có timeout mặc định không giới hạn; vì vậy cấu hình giá trị hữu hạn có ý nghĩa thực tế trong ứng dụng phục vụ HTTP request hoặc worker.

Timeout không giải quyết toàn bộ thời gian gửi end-to-end. Một lần gửi có thể gồm nhiều lần đọc/ghi, xác thực, truyền nội dung và chờ phản hồi; tổng thời gian không nhất thiết đúng bằng một giá trị timeout riêng lẻ.

## 5. Cấu hình gửi SMTP trong Spring Boot qua application.yml

Cách thường dùng trong Spring Boot là cấu hình bean tự động qua **spring.mail.***.

Ví dụ cho một SMTP server hỗ trợ STARTTLS trên cổng 587:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    protocol: smtp
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

Các khóa trong **properties** được viết với cú pháp **"[...]"** để giữ nguyên tên khóa có dấu chấm trong map cấu hình. Jakarta Mail cần nhận đúng các tên như **mail.smtp.starttls.enable**; đây không phải một hierarchy Java bean của Spring.

Các thông tin nhạy cảm nên nằm trong biến môi trường hoặc secret manager:

~~~text
SPRING_MAIL_USERNAME=<SMTP account>
SPRING_MAIL_PASSWORD=<SMTP credential>
~~~

Không đặt credential thật vào repository hoặc ví dụ công khai. Đối với những dịch vụ cung cấp mật khẩu ứng dụng, token hoặc cơ chế AUTH riêng, cần tuân thủ tài liệu của nhà cung cấp thay vì dùng mật khẩu tài khoản cá nhân theo thói quen.

### 5.1. Các thuộc tính Boot tương ứng

| Cấu hình Spring Boot | Ý nghĩa | Liên hệ tới JavaMailSenderImpl |
| --- | --- | --- |
| **spring.mail.host** | SMTP hostname | setHost(...) |
| **spring.mail.port** | Port | setPort(...) |
| **spring.mail.username** | Tên đăng nhập | setUsername(...) |
| **spring.mail.password** | Credential | setPassword(...) |
| **spring.mail.protocol** | Transport protocol, thường smtp | setProtocol(...) |
| **spring.mail.default-encoding** | Encoding mặc định | setDefaultEncoding(...) |
| **spring.mail.properties[...]** | Các thuộc tính provider Jakarta Mail | JavaMail Properties |
| **spring.mail.test-connection** | Tùy chọn kiểm tra kết nối SMTP khi khởi động | Kiểm tra cấu hình kết nối, không gửi thư thật |
| **spring.mail.jndi-name** | Tham chiếu một mail Session từ JNDI khi hạ tầng hỗ trợ | Dùng Session cung cấp từ môi trường |

Những khóa này thuộc không gian cấu hình **Spring Boot**. Khi viết JavaMailSenderImpl thủ công trong ứng dụng Spring Framework không dùng Boot auto-config, chúng **không tự động có tác dụng** nếu không có code đọc và áp dụng.

### 5.2. Dạng application.properties tương đương

Nếu dự án dùng **application.properties**, cấu hình có thể viết:

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.protocol=smtp
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Trong **.properties**, chuỗi tên key được đưa về dạng phẳng trực tiếp; còn trong YAML cần chú ý cách biểu diễn map key chứa dấu chấm.

### 5.3. Các profile môi trường

Ứng dụng có thể có các endpoint SMTP khác nhau cho local, staging và production:

~~~text
local:
  SMTP sandbox / mail capture server

staging:
  SMTP sandbox hoặc tài khoản thử nghiệm

production:
  SMTP provider chính thức với secret và miền gửi đã cấu hình
~~~

Cơ chế Spring profiles giúp tách thông số môi trường. Tuy nhiên, **profile không phải kho lưu bí mật**: một tệp application-prod.yml được commit vào Git vẫn không phải chỗ thích hợp để chứa mật khẩu thật.

Với local, dùng một SMTP capture server giúp quan sát thư mà không phát đến địa chỉ người dùng. Với production, nên kiểm tra cấu hình DNS, quyền gửi, rate limit và chính sách delivery của nhà cung cấp.

## 6. Phân biệt STARTTLS cổng 587 và TLS ngay từ đầu cổng 465

Hai cách bảo vệ kết nối phổ biến là:

**SMTP submission + STARTTLS:** client kết nối tới server bằng giao thức SMTP, server công bố STARTTLS, sau đó hai bên nâng cấp kết nối sang TLS trước khi AUTH và gửi nội dung nhạy cảm.

**SMTP qua TLS ngay từ đầu (implicit TLS):** kết nối mạng bắt đầu bằng TLS handshake trước khi trao đổi SMTP.

### 6.1. Ví dụ cổng 587 với STARTTLS

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Luồng kết nối ở mức khái niệm:

~~~text
TCP connect đến host:587
    |
    v
SMTP greeting / EHLO
    |
    v
Server công bố STARTTLS
    |
    v
STARTTLS -> TLS handshake -> xác minh danh tính server
    |
    v
EHLO lại theo giao thức
    |
    v
AUTH -> MAIL FROM -> RCPT TO -> DATA
~~~

Nếu server không hỗ trợ STARTTLS mà client đặt **mail.smtp.starttls.required=true**, phiên gửi sẽ thất bại thay vì tiếp tục gửi trên kênh chưa được bảo vệ.

### 6.2. Ví dụ cổng 465 với implicit TLS

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 465
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Ở cấu hình này, TLS được thiết lập ngay từ đầu kết nối. Không nên lấy một mẫu 587 rồi chỉ đổi port thành 465 mà quên thay đổi thuộc tính tương ứng. Nếu client cố nói SMTP thuần đến endpoint đòi TLS ngay từ đầu, hoặc cố TLS handshake trực tiếp với endpoint đang chờ SMTP greeting, quá trình gửi có thể timeout hoặc lỗi giao thức.

**587 và 465 là quy ước triển khai thường gặp, không phải quy tắc bắt buộc cho mọi SMTP server.** Một tổ chức có thể dùng cổng riêng, và provider có thể có chính sách xác thực khác. Tài liệu của endpoint thực tế là nguồn cấu hình cuối cùng.

### 6.3. Có dùng protocol smtps không?

Jakarta Mail có cấu hình/protocol liên quan đến SMTP qua SSL/TLS trong một số provider. Tuy nhiên, với mô hình phổ biến sử dụng SMTP transport, cấu hình **protocol=smtp** kết hợp **mail.smtp.ssl.enable=true** thường rõ ràng cho implicit TLS.

Nếu thay đổi **setProtocol("smtps")**, một số tên thuộc tính của provider có thể chuyển sang tiền tố **mail.smtps.***. Không nên trộn tên property của protocol này với protocol khác mà không kiểm tra provider thực tế.

Khi triển khai, hãy chọn một mô hình kết nối được nhà cung cấp hỗ trợ và sử dụng nhất quán trong cấu hình.

## 7. Cấu hình JavaMailSenderImpl thủ công bằng @Configuration

Khi không dùng Spring Boot mail auto-configuration, hoặc cần quản lý cấu hình theo cách riêng, có thể khai báo bean rõ ràng.

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

    @Bean
    public JavaMailSender javaMailSender(Environment environment) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(
                environment.getRequiredProperty("SMTP_HOST")
        );
        sender.setPort(
                environment.getProperty(
                        "SMTP_PORT", Integer.class, 587
                )
        );
        sender.setProtocol("smtp");
        sender.setUsername(
                environment.getRequiredProperty("SMTP_USERNAME")
        );
        sender.setPassword(
                environment.getRequiredProperty("SMTP_PASSWORD")
        );
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

Ở đây **Environment** được dùng để đọc các biến cấu hình mà ứng dụng yêu cầu. Trong môi trường chạy, cần cung cấp đúng tên:

~~~text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
~~~

Ví dụ Java trên chỉ phục vụ mô hình SMTP submission 587 có STARTTLS. Nó không phải cấu hình mặc định chung cho mọi máy chủ. Nếu hạ tầng sử dụng cổng 465, phải điều chỉnh cổng và nhóm SSL properties tương ứng.

### 7.1. Tại sao khai báo kiểu trả về JavaMailSender?

Bean được đăng ký dưới kiểu giao diện:

~~~java
@Bean
public JavaMailSender javaMailSender(Environment environment) { ... }
~~~

Mã ứng dụng chỉ cần:

~~~java
private final JavaMailSender mailSender;
~~~

Điều này giúp service phụ thuộc API gửi chung, còn cấu hình hạ tầng được gom ở một nơi. Khi có yêu cầu chẩn đoán implementation, lớp quản trị hạ tầng có thể làm việc trực tiếp với JavaMailSenderImpl theo cách có kiểm soát.

### 7.2. Có nên vừa dùng Boot auto-config vừa khai báo bean thủ công?

Thường **không cần**. Nếu đã dùng Boot và cấu hình **spring.mail.*** đáp ứng nhu cầu, hãy để Boot tạo bean gửi thư.

Khi bạn tự định nghĩa bean sender, cơ chế auto-configuration thường nhường quyền cho bean đó theo điều kiện tương ứng. Điều này có thể khiến những thuộc tính **spring.mail.*** bạn viết không tự động được áp dụng vào bean thủ công, nếu mã cấu hình không đọc chúng.

Ví dụ: ứng dụng có **spring.mail.host=smtp-a.example.org**, nhưng bean thủ công lại gọi **setHost("smtp-b.example.org")**. Kết quả sẽ phụ thuộc bean thực sự được tiêm và cấu hình thực tế của nó; không thể giả định Boot tự hòa trộn hai nguồn một cách kỳ diệu.

Nên chọn một nguồn cấu hình rõ ràng, tránh có nhiều JavaMailSender cùng vai trò nhưng không biết service đang tiêm bean nào.

## 8. Jakarta Mail Session và thứ tự cấu hình

**Session** của Jakarta Mail mang Properties và thông tin môi trường mà mail provider sử dụng. JavaMailSenderImpl có thể tự tạo Session dựa trên JavaMail Properties hoặc nhận một Session do hạ tầng cấp.

Có hai cách dùng thường gặp:

### 8.1. Để JavaMailSenderImpl tạo Session

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();

sender.setHost("smtp.example.org");
sender.setPort(587);

Properties properties = new Properties();
properties.put("mail.smtp.auth", "true");
properties.put("mail.smtp.starttls.enable", "true");
properties.put("mail.smtp.starttls.required", "true");

sender.setJavaMailProperties(properties);
~~~

Đây là cách đơn giản cho đa số ứng dụng độc lập. Sender sở hữu cấu hình cần thiết để tạo Jakarta Mail Session.

### 8.2. Sử dụng một Session do môi trường cung cấp

Một application server có thể quản lý **jakarta.mail.Session** riêng, ví dụ qua JNDI. Trong trường hợp đó, ứng dụng có thể nhận Session đã được cấu hình và truyền vào JavaMailSenderImpl bằng **setSession(...)**.

Ưu điểm có thể là tập trung cấu hình hạ tầng, credential và chính sách kết nối bên ngoài mã ứng dụng. Đổi lại, cần hiểu rằng **Session cũng mang Properties riêng**, còn JavaMailSenderImpl có các setter host, port, username và password có thể được sử dụng khi kết nối.

Nếu dùng đồng thời Session do server quản lý và những setter/property khác, cần kiểm tra quy tắc ưu tiên và hành vi của implementation. Tránh đặt các giá trị mâu thuẫn ở nhiều nơi rồi dựa vào suy đoán về thứ tự ghi đè.

Trong Spring Boot có cấu hình **spring.mail.jndi-name** cho trường hợp phù hợp. Đây là một lựa chọn tích hợp hạ tầng, không phải thuộc tính cần dùng trong mọi ứng dụng.

### 8.3. Không sửa Properties liên tục khi đang gửi thư

Một bean JavaMailSenderImpl thường được dùng chung giữa nhiều request hoặc worker. Vì vậy, việc gọi **setHost**, **setPassword** hay sửa các Properties của Session trong khi nhiều luồng đang gửi thư dễ làm kết quả khó dự đoán.

Cách tổ chức thông thường:

1. Tạo và cấu hình sender khi ứng dụng khởi động.
2. Xác định rõ bean nào phục vụ endpoint SMTP nào.
3. Để các service sử dụng sender đã cấu hình.
4. Nếu cần nhiều tài khoản/nhà cung cấp, tạo các sender riêng có tên hoặc qualifier phù hợp, thay vì liên tục thay thông số của một sender dùng chung.

Khi cần đổi mật khẩu theo cơ chế rotation, phải có quy trình cập nhật cấu hình và vòng đời bean có kiểm soát; đừng thay đổi object dùng chung một cách tùy tiện.

## 9. Dùng sender đã cấu hình để gửi mail

Sau khi cấu hình, service có thể gửi văn bản đơn giản bằng **SimpleMailMessage**:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeEmailService {

    private final JavaMailSender mailSender;

    public WelcomeEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("noreply@example.org");
        message.setTo(recipient);
        message.setSubject("Chào mừng");
        message.setText(
                "Cảm ơn bạn đã đăng ký. "
                + "Chúc bạn có trải nghiệm tốt!"
        );

        mailSender.send(message);
    }
}
~~~

Trong ví dụ, **setFrom** tạo địa chỉ người gửi trong message. Đây không phải phương thức cấu hình host, port hay credential. **setTo** xác định địa chỉ người nhận, không phải chỉ định server để kết nối.

Khi gửi HTML hoặc attachment:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(String recipient) throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message, false, "UTF-8"
    );
    helper.setFrom("noreply@example.org");
    helper.setTo(recipient);
    helper.setSubject("Thông báo từ hệ thống");
    helper.setText(
            "<p>Thông báo đã được tạo thành công.</p>",
            true
    );

    mailSender.send(message);
}
~~~

Trong cả hai trường hợp, **cấu hình JavaMailSenderImpl vẫn được tái sử dụng**. Định dạng message có thể khác nhau nhưng endpoint và hành vi SMTP dùng cùng một sender.

### 9.1. Vì sao setFrom không thay thế setUsername?

**From** trong message là danh tính gửi mà người nhận có thể nhìn thấy. **Username** của JavaMailSenderImpl thường là danh tính dùng để SMTP AUTH.

Ví dụ:

~~~text
SMTP AUTH username: mailer-account@example.org
Header From:        notifications@example.org
~~~

Hai giá trị có thể khác nhau nếu nhà cung cấp cho phép và đã cấu hình danh tính gửi tương ứng. Nhưng một số provider chỉ cho phép địa chỉ From trùng tài khoản hoặc thuộc miền đã được xác minh.

Vì vậy, khi thấy lỗi “sender rejected” hoặc “not authorized to send as this address”, không nên chỉ thay password. Cần kiểm tra chính sách địa chỉ gửi và danh tính đã được xác thực.

### 9.2. Có cấu hình để lưu mail trong Sent không?

JavaMailSenderImpl thông thường **gửi qua SMTP**, không trực tiếp quản lý thư mục Sent hoặc inbox. Việc gửi thành công không mặc nhiên tạo một bản sao ở Sent của tài khoản. Nếu ứng dụng cần lưu bản sao, có thể phụ thuộc vào chính sách của dịch vụ gửi hoặc phải thực hiện một thao tác lưu thư riêng theo API của provider.

Đây là một ranh giới quan trọng khi đặt tên một service “mail sender”: nó chịu trách nhiệm gửi, không đại diện toàn bộ một email client có chức năng đọc và quản lý mailbox.

## 10. Kiểm tra kết nối bằng testConnection()

JavaMailSenderImpl cung cấp phương thức **testConnection()** để thử kết nối đến mail server với cấu hình hiện có.

Ví dụ trong thành phần chẩn đoán:

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class MailConnectionProbe {

    private MailConnectionProbe() {
    }

    public static void verify(JavaMailSenderImpl sender)
            throws MessagingException {
        sender.testConnection();
    }
}
~~~

Lời gọi này có thể phát hiện những lỗi như không kết nối được endpoint hoặc xác thực thất bại, tùy yêu cầu của server. Nó **không gửi một email thực sự đến inbox người nhận** và không bảo đảm một email với kích thước/recipient cụ thể sẽ được server chấp nhận.

### 10.1. Spring Boot test-connection

Trong Spring Boot có thể sử dụng thuộc tính:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Khi điều kiện auto-configuration và thành phần kiểm tra kết nối tương ứng được kích hoạt, Boot có thể kiểm tra kết nối lúc khởi động. Điều này giúp phát hiện lỗi cấu hình sớm, nhưng cũng tạo **phụ thuộc vận hành**: nếu SMTP server tạm thời không khả dụng, startup có thể thất bại dù các chức năng khác của ứng dụng không cần email ngay lúc đó.

Vì vậy, không nên bật tùy chọn này chỉ vì muốn “chắc chắn gửi được”. Hãy quyết định theo đặc tính dịch vụ:

- Dịch vụ chuyên gửi thư có thể coi việc không kết nối được SMTP là lỗi khởi động nghiêm trọng.
- Ứng dụng có nhiều tính năng khác có thể muốn khởi động được, ghi nhận health riêng của sender và retry qua hàng đợi.
- Với mail sandbox của môi trường test, có thể dùng test connection để phát hiện cấu hình sai khi xây dựng ứng dụng.

### 10.2. testConnection() không phải kiểm thử end-to-end

Kiểm tra kết nối và gửi thật là hai mốc khác nhau:

| Kiểm tra | Xác nhận được điều gì? | Chưa xác nhận được điều gì? |
| --- | --- | --- |
| Tạo bean JavaMailSenderImpl | Cấu hình có thể được đọc và đối tượng được tạo | Server có tồn tại hoặc truy cập được |
| **testConnection()** | Có thể mở phiên kết nối/auth theo cấu hình hiện tại | Người nhận cụ thể được chấp nhận, DATA và delivery thành công |
| Gửi mail thử đến hộp thư kiểm soát | Thử quá trình soạn, gửi và phản hồi SMTP | Mọi môi trường, mọi recipient đều sẽ thành công |
| Kiểm tra inbox/bounce/provider event | Có thêm bằng chứng về chuyển phát hoặc lỗi | Người dùng cuối chắc chắn đã mở/đọc thư |

Nếu cần chứng minh luồng thông báo nghiệp vụ hoạt động, testConnection() chỉ là một lớp chẩn đoán. Cần một bài kiểm tra gửi nhận phù hợp ở môi trường được kiểm soát.

## 11. Lỗi thường gặp và cách xác định cấu hình liên quan

Khi **mailSender.send(...)** lỗi, Spring có thể ném **MailException** như **MailAuthenticationException**, **MailSendException** hoặc lỗi liên quan; nguyên nhân gốc có thể nằm ở Jakarta Mail, socket hoặc TLS.

Bảng dưới gợi ý các nhóm lỗi, không thay cho việc đọc exception và phản hồi thực tế của server.

| Triệu chứng | Khả năng thường gặp | Nhóm cấu hình cần xem |
| --- | --- | --- |
| Không phân giải được hostname | Sai host hoặc vấn đề DNS/mạng | spring.mail.host, DNS |
| Connection refused | Sai port, server không lắng nghe, firewall | spring.mail.port, endpoint |
| Kết nối mãi chưa xong | Mạng không tới server hoặc endpoint chậm | connectiontimeout, route, firewall |
| Socket read timeout | Server không phản hồi kịp trong phiên | mail.smtp.timeout, TLS, server |
| SMTP AUTH thất bại (ví dụ 535) | Sai credential, cơ chế AUTH không phù hợp, quyền tài khoản | username/password, mail.smtp.auth, provider policy |
| Server yêu cầu xác thực (ví dụ 530 trong một số trường hợp) | AUTH chưa thành công hoặc chưa thực hiện | mail.smtp.auth, TLS, credentials |
| TLS handshake thất bại | Sai chế độ TLS, hostname/certificate chain, phiên bản TLS | 587 STARTTLS vs 465 SSL, truststore |
| STARTTLS required nhưng server không hỗ trợ | Server không công bố/không thiết lập STARTTLS | mail.smtp.starttls.required, endpoint |
| Sender bị từ chối | From/envelope sender không được phép | setFrom, mail.smtp.from, account/domain |
| Recipient bị từ chối | Địa chỉ hoặc chính sách người nhận | setTo/Cc/Bcc, server policy |
| Message quá lớn | MIME attachment hoặc encoded DATA vượt hạn mức | Kích thước file, provider SIZE |
| Gửi mail rất chậm | Đường truyền, server delay, thiếu timeout | connection/read/write timeouts |

### 11.1. Lỗi host và port

Ví dụ một ứng dụng cấu hình:

~~~text
host=smtp.example.org
port=465
starttls.enable=true
ssl.enable=false
~~~

Trong khi endpoint 465 yêu cầu implicit TLS. Client có thể không nhận được lời chào SMTP như mong đợi, vì đầu bên kia đang chờ TLS handshake. Cách xử lý là dùng đúng cấu hình mà provider yêu cầu, chẳng hạn **mail.smtp.ssl.enable=true** cho implicit TLS.

### 11.2. Lỗi username hoặc password

Nếu SMTP server trả lỗi xác thực, kiểm tra:

1. Tài khoản SMTP có được phép dùng từ ứng dụng?
2. Credential có đúng loại (mật khẩu ứng dụng, token hoặc cơ chế do provider chỉ định)?
3. AUTH có được bật, và việc sử dụng STARTTLS/TLS có đúng yêu cầu server?
4. Tài khoản có bị khóa, hạn chế IP hoặc yêu cầu cấu hình bổ sung?
5. Biến môi trường có được cung cấp đúng ở runtime?

Không nên in password ra log hoặc gửi credential cho bên thứ ba chỉ để đối chiếu. Có thể kiểm tra **sự hiện diện** của cấu hình và định danh môi trường mà không ghi nội dung secret.

### 11.3. Lỗi nhận recipient không đồng nhất với lỗi kết nối

Một kết nối và SMTP AUTH có thể thành công, nhưng server vẫn từ chối người nhận trong lệnh RCPT TO vì địa chỉ không tồn tại, policy không cho gửi tới miền đó hoặc vượt hạn mức.

**testConnection()** có thể thành công trong khi một lần gửi với recipient nhất định vẫn thất bại. Vì vậy, các lớp lỗi cần được phân biệt, tránh “sửa TLS” khi thực chất server đang từ chối người nhận.

### 11.4. Gửi thành công nhưng inbox không thấy thư

Nếu SMTP server đã chấp nhận DATA, hệ thống gửi có thể chỉ ghi nhận rằng thư đã được nhận để chuyển phát. Phía sau còn tồn tại:

- Hàng đợi chuyển phát.
- Bộ lọc spam, virus hoặc policy của miền nhận.
- Bounce hoặc trì hoãn.
- SPF, DKIM, DMARC và danh tiếng miền gửi.
- Hạn mức hoặc trạng thái hộp thư người nhận.

Đây thường là vấn đề **deliverability** hoặc trạng thái hậu xử lý. Việc JavaMailSenderImpl không ném lỗi không có nghĩa thư chắc chắn đã nằm trong inbox, càng không chứng minh người nhận đã đọc.

## 12. Debug SMTP mà không làm lộ dữ liệu

Jakarta Mail hỗ trợ chế độ debug giúp quan sát bước kết nối và trao đổi với transport.

Ví dụ cấu hình thường gặp:

~~~properties
spring.mail.properties.mail.debug=true
~~~

Nhưng **mail.debug** có thể tạo log nhạy cảm gồm tên server, địa chỉ email và thông tin giao thức. Tùy provider/cấu hình, log có thể chứa dữ liệu mà hệ thống không nên công khai.

Vì vậy:

- Chỉ bật debug tạm thời trong môi trường được kiểm soát.
- Kiểm tra chính sách che và lưu log.
- Không in password, access token hoặc nội dung email nhạy cảm.
- Tắt debug sau khi chẩn đoán.
- Với production, ưu tiên metrics, status code và lỗi đã được phân loại thay vì log toàn bộ SMTP conversation.

Không cấu hình tùy chọn cho phép in dữ liệu xác thực chỉ để giải quyết lỗi kết nối. Một log được chia sẻ để hỗ trợ kỹ thuật nên có địa chỉ và metadata phù hợp được che bớt.

## 13. Những thuộc tính không phải lúc nào cũng nên thay đổi

Tài liệu Jakarta Mail có nhiều thuộc tính nâng cao hơn những ví dụ phổ biến. Không nên sao chép một danh sách dài vào production mà không biết tác dụng của từng giá trị.

Một vài nhóm thường chỉ cần khi có yêu cầu cụ thể:

| Nhóm | Ví dụ | Khi nào cần cân nhắc? |
| --- | --- | --- |
| Giao thức kết nối | mail.transport.protocol, protocol của sender | Khi hạ tầng dùng provider/transport đặc biệt |
| Chế độ AUTH | mail.smtp.auth.mechanisms | Khi provider yêu cầu cơ chế xác thực cụ thể |
| Envelope sender | mail.smtp.from | Khi cần quy trình bounce hoặc địa chỉ envelope riêng |
| Debug transport | mail.debug | Khi điều tra lỗi ở môi trường được kiểm soát |
| Kiểm tra TLS | mail.smtp.ssl.checkserveridentity | Để kiểm soát xác minh hostname với SMTP TLS |
| Giới hạn kết nối/thời gian | mail.smtp.connectiontimeout, timeout, writetimeout | Gần như luôn có ích cho vận hành |
| Gửi từng phần | mail.smtp.sendpartial | Khi cần chính sách rõ ràng cho nhiều recipient, tùy provider |
| SSL/TLS nâng cao | mail.smtp.ssl.protocols | Khi cần thỏa mãn chính sách TLS có kiểm chứng |

Các key mail.smtp.* chỉ có tác dụng đúng nếu sender đang dùng SMTP transport tương ứng. Nếu đổi sang một provider khác hoặc một API gửi qua HTTP, tên thuộc tính, phương thức xác thực, timeout và cách theo dõi lỗi có thể khác hoàn toàn.

## 14. Trường hợp có nhiều SMTP account hoặc nhiều môi trường gửi

Một hệ thống có thể cần gửi:

- Email giao dịch từ **transactional@example.org**.
- Email hệ thống nội bộ từ **alerts@example.org**.
- Email bản tin từ tài khoản hoặc dịch vụ chuyên dụng.

Nếu cả ba dùng một sender mà sửa username/password trước mỗi lần gửi, các request đồng thời có thể sử dụng sai tài khoản hoặc sai endpoint.

Thiết kế rõ ràng hơn là tạo **các bean JavaMailSender độc lập**, mỗi bean cấu hình một tài khoản/provider, rồi tiêm qua qualifier.

Ví dụ minh họa ý tưởng:

~~~java
@Configuration
public class MultipleMailConfig {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender(
            TransactionalSmtpSettings settings
    ) {
        return buildSender(settings);
    }

    @Bean("alertsMailSender")
    public JavaMailSender alertsMailSender(
            AlertSmtpSettings settings
    ) {
        return buildSender(settings);
    }

    // Các kiểu Settings và buildSender ở đây đại diện cho
    // cấu hình nội bộ của ứng dụng, không phải class có sẵn
    // trong Spring Framework.
}
~~~

Và trong service:

~~~java
public TransactionalService(
        @Qualifier("transactionalMailSender")
        JavaMailSender mailSender
) {
    this.mailSender = mailSender;
}
~~~

Các đoạn mã này minh họa cách tách bean; chúng cần các class cấu hình cụ thể do dự án định nghĩa. Nếu không có nhu cầu nhiều sender, giữ một bean duy nhất sẽ đơn giản hơn.

Khi dùng nhiều sender, phải xác định cả sender được dùng cho lệnh gửi và danh tính **From** mà sender đó được phép sử dụng. Không nên tùy ý ghép sender của tài khoản A với From thuộc miền chưa xác thực của tài khoản B.

## 15. Cấu hình sender và an toàn vận hành

Một hệ thống gửi thư hoạt động ổn định cần nhiều hơn một host và password.

### 15.1. Bí mật và vòng đời credential

Mật khẩu hoặc token SMTP nên được cung cấp qua:

- Biến môi trường được quản lý có kiểm soát.
- Secret manager của nền tảng vận hành.
- Cơ chế cấp credential theo môi trường.
- Tài khoản SMTP riêng có quyền tối thiểu cần thiết.

Không đặt secret thật trong **application.yml** được commit, tài liệu Markdown, log khởi động hoặc request debug. Khi quay vòng credential, cần có quá trình cập nhật môi trường và sender đang sử dụng để tránh gián đoạn.

### 15.2. Xác minh TLS và hostname

Dùng TLS giúp bảo vệ nội dung trao đổi trên đường truyền, nhưng hiệu quả phụ thuộc việc xác minh đúng server. Không nên giải quyết lỗi truststore bằng cách tin mọi chứng chỉ.

Nếu thấy lỗi chứng chỉ, kiểm tra:

1. Hostname cấu hình có khớp với chứng chỉ server?
2. Chuỗi chứng chỉ có hợp lệ và được JDK truststore tin cậy?
3. Client đang dùng STARTTLS hay implicit TLS đúng cổng?
4. Đồng hồ hệ thống có đúng, JDK có hỗ trợ phiên bản TLS phù hợp?
5. Có thiết bị trung gian doanh nghiệp hợp lệ yêu cầu truststore được cấu hình rõ ràng?

Các câu hỏi trên hỗ trợ tìm nguyên nhân thay vì bỏ hẳn bước xác minh.

### 15.3. Timeout và retry

Nếu một lời gọi gửi thư diễn ra trong HTTP request, timeout quá dài có thể khiến người dùng phải chờ hoặc hết hạn ở gateway. Nếu đặt timeout quá ngắn, gửi thư có attachment hoặc qua mạng chậm có thể thất bại giả.

Nên cân nhắc gửi bất đồng bộ qua job/queue cho các nghiệp vụ cần độ tin cậy, với:

- Mã sự kiện nghiệp vụ.
- Trạng thái đã yêu cầu gửi/đã tiếp nhận/lỗi.
- Retry có giới hạn và backoff.
- Phân biệt lỗi tạm thời với lỗi vĩnh viễn.
- Quy tắc tránh gửi trùng nếu kết quả lần gửi trước chưa xác định.

SMTP không tự bảo đảm một lần xử lý nghiệp vụ tương ứng chính xác một email ở inbox. Ví dụ, mất kết nối sau khi server nhận DATA nhưng trước khi client nhận phản hồi có thể khiến ứng dụng không rõ thư đã được server tiếp nhận hay chưa.

### 15.4. Rate limit, quota và người nhận

Provider có thể giới hạn số email mỗi ngày, số recipient hoặc kích thước message. JavaMailSenderImpl không tự quyết định toàn bộ chính sách gửi hàng loạt. Tầng nghiệp vụ cần kiểm tra quyền gửi và giới hạn số người nhận; tầng vận hành cần xử lý quota, queue và sự kiện lỗi của provider.

### 15.5. Khả năng quan sát

Khi không gửi được thư, nên lưu những thông tin đủ để vận hành:

- Mã sự kiện hoặc job gửi.
- SMTP provider và môi trường liên quan.
- Thời điểm bắt đầu/kết thúc và thời gian gửi.
- Loại lỗi, mã phản hồi giao thức nếu có.
- Trạng thái retry.
- Người nhận đã được xử lý dưới dạng metadata theo chính sách bảo mật.

Không lưu credential hoặc toàn bộ nội dung email chỉ để có log chi tiết. Nếu cần theo dõi chuyển phát cuối cùng, có thể phải tích hợp callback/bounce/event API của dịch vụ gửi thay vì trông đợi hoàn toàn vào kết quả của **send()**.

## 16. Các ví dụ cấu hình theo tình huống

### Tình huống A: ứng dụng nội bộ dùng SMTP relay không yêu cầu AUTH

Giả sử tổ chức có relay chỉ chấp nhận kết nối trong mạng riêng và đã kiểm soát quyền theo IP hoặc cơ chế khác.

~~~yaml
spring:
  mail:
    host: mailrelay.internal.example
    port: 25
    properties:
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Ví dụ này chỉ có ý nghĩa nếu chính sách relay thực sự cho phép cách gửi đó. Không nên sao chép cấu hình thiếu AUTH/TLS cho một SMTP server Internet mà không kiểm tra chính sách và yêu cầu bảo mật.

### Tình huống B: gửi qua submission server yêu cầu AUTH và STARTTLS

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: mailer@example.org
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Đây là dạng mẫu thường dùng. **username** là giá trị minh họa, còn password nên được cấp từ secret runtime. Nếu dùng cấu hình YAML ở production, có thể bỏ username ra khỏi file để cấp cả username lẫn password thông qua biến môi trường.

### Tình huống C: gửi qua implicit TLS

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 465
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.ssl.enable]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Lưu ý không nhầm với STARTTLS cổng 587. Việc chọn cổng và cơ chế TLS phải dựa trên endpoint.

### Tình huống D: môi trường phát triển chỉ muốn xem thư được tạo

Có thể dùng SMTP sandbox trong mạng phát triển, cấu hình host/port theo sandbox, rồi tạo một thông điệp test. Cách này giúp kiểm tra được subject, HTML, MIME part và attachment mà không gửi thực sự đến người dùng.

Đối với unit test, có thể thay JavaMailSender bằng mock để kiểm tra phần quyết định thông điệp. Đối với integration test gửi thư, dùng SMTP capture server hoặc môi trường mail thử nghiệm đã kiểm soát.

Không nên kết luận **sender cấu hình chính xác cho production** chỉ từ một lần gửi thành công qua sandbox: môi trường production có thể dùng AUTH, TLS, quota và policy người gửi khác.

## 17. Câu hỏi thường gặp về JavaMailSenderImpl

**“JavaMailSender và JavaMailSenderImpl khác nhau thế nào?”**

JavaMailSender là giao diện. JavaMailSenderImpl là class triển khai thông thường dựa trên Jakarta Mail. Service nên phụ thuộc giao diện; cấu hình endpoint thuộc implementation.

**“Tôi đã gọi setUsername và setPassword, vì sao vẫn lỗi AUTH?”**

Có thể chưa bật mail.smtp.auth, endpoint dùng cơ chế xác thực khác, credential không hợp lệ hoặc server yêu cầu TLS trước AUTH. Cần đọc mã phản hồi và tài liệu provider.

**“Tại sao mail.smtp.auth không phải spring.mail.auth?”**

Vì đây là thuộc tính của SMTP provider trong Jakarta Mail. Trong Boot, nó được đặt dưới map **spring.mail.properties[...]** để đưa nguyên key cho Jakarta Mail. Spring Boot chỉ có những thuộc tính trực tiếp tương ứng như host, port, username, password, protocol và default-encoding.

**“Tôi muốn gửi trên cổng 465, có thể chỉ đổi spring.mail.port không?”**

Không nên. Nếu endpoint 465 dùng implicit TLS, cần cấu hình **mail.smtp.ssl.enable=true**. Đổi port mà vẫn dùng cơ chế STARTTLS không phù hợp có thể dẫn tới lỗi handshake hoặc timeout.

**“Cấu hình STARTTLS enable=true đã bảo đảm mã hóa chưa?”**

Chưa chắc, vì enable chỉ cho phép nâng cấp khi server hỗ trợ. Khi endpoint bắt buộc TLS, nên yêu cầu STARTTLS qua **mail.smtp.starttls.required=true** hoặc dùng cấu hình implicit TLS phù hợp.

**“Ba timeout có giống nhau không?”**

Không. Connection timeout giới hạn thiết lập TCP, read timeout giới hạn thời gian chờ dữ liệu phản hồi, write timeout giới hạn thao tác ghi. Một lần gửi có thể gồm nhiều bước và tổng thời gian dài hơn từng timeout.

**“testConnection() có gửi thử một email không?”**

Không. Nó kiểm tra khả năng kết nối/thiết lập phiên theo cấu hình, không kiểm chứng nội dung hay inbox đích.

**“Khi nào cần tự tạo JavaMailSenderImpl?”**

Khi không dùng Spring Boot mail auto-config, hoặc có nhu cầu cấu hình nâng cao/đa sender mà các thuộc tính Boot mặc định chưa đáp ứng. Nếu Boot đang tự tạo bean phù hợp, không cần định nghĩa thêm chỉ để gửi một email.

**“Có cần setDefaultEncoding('UTF-8') không?”**

Nên dùng encoding rõ ràng khi xử lý tiếng Việt. Trong Spring Boot, **spring.mail.default-encoding** thường có mặc định UTF-8 trong các phiên bản phổ biến, nhưng khai báo rõ cũng giúp người đọc hiểu kỳ vọng của hệ thống. Encoding của một MIME part có thể còn được thiết lập ở helper tùy ngữ cảnh.

**“Tôi cấu hình đúng nhưng nhà cung cấp vẫn đưa thư vào spam?”**

Cấu hình JavaMailSenderImpl chỉ xử lý kết nối và gửi thông điệp. Khả năng vào inbox còn phụ thuộc xác thực miền gửi, danh tiếng, nội dung, các chính sách của mail server và trạng thái người nhận.

## 18. Tổng hợp các thuộc tính cần nhớ

| Mục đích | Thuộc tính ở Spring Boot | Tương ứng ở Java/Jakarta Mail |
| --- | --- | --- |
| SMTP hostname | spring.mail.host | JavaMailSenderImpl.setHost |
| SMTP port | spring.mail.port | JavaMailSenderImpl.setPort |
| SMTP protocol | spring.mail.protocol | JavaMailSenderImpl.setProtocol |
| Tài khoản | spring.mail.username | JavaMailSenderImpl.setUsername |
| Credential | spring.mail.password | JavaMailSenderImpl.setPassword |
| Encoding mặc định | spring.mail.default-encoding | JavaMailSenderImpl.setDefaultEncoding |
| Bật AUTH | spring.mail.properties[mail.smtp.auth] | mail.smtp.auth |
| STARTTLS | spring.mail.properties[mail.smtp.starttls.enable] | mail.smtp.starttls.enable |
| Bắt buộc STARTTLS | spring.mail.properties[mail.smtp.starttls.required] | mail.smtp.starttls.required |
| Implicit TLS | spring.mail.properties[mail.smtp.ssl.enable] | mail.smtp.ssl.enable |
| Xác minh hostname TLS | spring.mail.properties[mail.smtp.ssl.checkserveridentity] | mail.smtp.ssl.checkserveridentity |
| Connection timeout | spring.mail.properties[mail.smtp.connectiontimeout] | mail.smtp.connectiontimeout |
| Read timeout | spring.mail.properties[mail.smtp.timeout] | mail.smtp.timeout |
| Write timeout | spring.mail.properties[mail.smtp.writetimeout] | mail.smtp.writetimeout |
| Kiểm tra kết nối khi khởi động | spring.mail.test-connection | testConnection() khi được cấu hình qua Boot |

Bảng chỉ mô tả những thuộc tính thường dùng. Trong file YAML hoặc properties, hãy dùng cách biểu diễn key đúng với định dạng cấu hình để Jakarta Mail nhận nguyên tên property.

## 19. Ghi nhớ khi cấu hình sender cho Spring Framework Mail

**JavaMailSenderImpl** là nơi Spring kết nối việc tạo **MimeMessage** với một phiên gửi thông qua **Jakarta Mail**. Những setter như **host, port, username, password, protocol** xác định đích và thông tin kết nối; **JavaMail Properties** điều khiển hành vi SMTP chi tiết như AUTH, STARTTLS, SSL và timeout.

Trong **Spring Boot**, đa số trường hợp nên bắt đầu với **spring-boot-starter-mail**, cấu hình **spring.mail.*** và tiêm **JavaMailSender** vào service. Khi cần tự xây dựng bean, cấu hình JavaMailSenderImpl trong một nơi riêng, ổn định từ lúc khởi động, và bảo đảm không có nhiều nguồn cấu hình mâu thuẫn.

Một sender được cấu hình tốt cần dùng đúng endpoint, đúng chế độ TLS, đúng quyền xác thực, timeout hữu hạn và credential được bảo vệ. Cuối cùng, hãy nhớ rằng **kết nối thành công**, **SMTP chấp nhận message** và **người nhận thực sự nhìn thấy email** là ba mốc khác nhau. Phân biệt được chúng sẽ giúp ứng dụng Spring gửi thư đáng tin cậy hơn và giúp việc điều tra lỗi đi đúng vào tầng cần sửa.
