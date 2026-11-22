# Các thuộc tính spring.mail.host, port, username và password

Một ứng dụng Spring Boot muốn gửi email xác nhận đăng ký cần biết **kết nối đến máy chủ nào**, **qua cổng nào** và **dùng danh tính nào để được phép gửi thư**. Bốn thuộc tính cấu hình `spring.mail.host`, `spring.mail.port`, `spring.mail.username` và `spring.mail.password` là những thông tin nền tảng để Spring Boot chuẩn bị kết nối SMTP cho thành phần gửi email.

Ví dụ, hệ thống có thể cần nộp email vào dịch vụ SMTP của một nhà cung cấp. Mã nghiệp vụ chỉ gọi `JavaMailSender.send(...)`; Spring Boot cung cấp các giá trị kết nối để thư viện Jakarta Mail liên hệ với máy chủ. Cách tách này giúp thay đổi nhà cung cấp, tài khoản hoặc môi trường triển khai mà không phải sửa logic gửi thư.

Tuy nhiên, **bốn thuộc tính này chưa tự quyết định kết nối có được mã hóa bằng TLS hay không**, chưa tự tạo người gửi `From` và cũng không có nghĩa email chắc chắn được chuyển phát đến Inbox. Cần hiểu vai trò cụ thể của từng thuộc tính, các thiết lập SMTP bổ sung và cách quản lý bí mật an toàn.

## 1. Spring Boot đặt bốn thuộc tính này vào đâu?

Trong ứng dụng Spring Boot có phụ thuộc gửi mail phù hợp, cơ chế **Mail Auto-configuration** có thể tạo một bean `JavaMailSender`. Các giá trị `spring.mail.*` được ánh xạ vào đối tượng cấu hình và chuyển cho phần triển khai gửi thư, thường là `JavaMailSenderImpl`.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["application.yml / application.properties / biến môi trường"] --> B["Spring Boot cấu hình mail"]
    B --> C["JavaMailSender"]
    C --> D["Jakarta Mail SMTP transport"]
    D --> E["SMTP relay / submission server"]
    F["Dịch vụ nghiệp vụ"] -->|"send(message)"| C
    E --> G["Hạ tầng email chuyển tiếp"]
~~~

Ở đây, Spring Boot quản lý **cách tạo và cấu hình thành phần gửi thư**. Lớp nghiệp vụ tập trung vào người nhận, tiêu đề và nội dung.

Bốn thuộc tính cần học:

| Thuộc tính | Ý nghĩa chính | Ví dụ minh họa |
| --- | --- | --- |
| `spring.mail.host` | Tên máy chủ hoặc địa chỉ mà ứng dụng sẽ kết nối để nộp thư qua SMTP | `smtp.provider.example` |
| `spring.mail.port` | Cổng TCP trên máy chủ SMTP | `587` |
| `spring.mail.username` | Danh tính đăng nhập SMTP nếu máy chủ yêu cầu xác thực | `mailer@example.org` |
| `spring.mail.password` | Bí mật dùng với cơ chế xác thực SMTP tương ứng | Lấy từ biến môi trường hoặc kho bí mật |

Các giá trị trong bảng chỉ để minh họa. `smtp.provider.example` không phải địa chỉ của một máy chủ dịch vụ đang được cung cấp công khai. Người triển khai cần dùng thông số thực tế do nhà cung cấp SMTP cấp.

## 2. Chuẩn bị phụ thuộc để Spring Boot hỗ trợ gửi mail

Trong dự án Spring Boot dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter giúp đưa các thư viện tích hợp mail vào classpath. Với cấu hình phù hợp, Spring Boot có thể tự cấu hình `JavaMailSender` để ứng dụng tiêm phụ thuộc:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailNotificationService {

    private final JavaMailSender mailSender;

    public MailNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
~~~

Thêm starter **chưa đủ để gửi email thật**. Cần một SMTP server có thể kết nối và cấu hình đúng host, cổng, thông tin xác thực (nếu cần), TLS và các chính sách của nhà cung cấp.

Trong cách tự cấu hình thông dụng, `spring.mail.host` là thông tin quan trọng để Spring Boot thiết lập sender. Nếu không có host hay nguồn cấu hình Jakarta Mail Session phù hợp, ứng dụng có thể không có bean `JavaMailSender` được tự tạo. Ngoài ra, nếu dự án đã định nghĩa một bean sender riêng, auto-configuration sẽ không nhất thiết tạo thêm bean khác để thay thế.

## 3. spring.mail.host — máy chủ SMTP mà ứng dụng kết nối

`spring.mail.host` chỉ định **máy chủ SMTP đích của kết nối đi từ ứng dụng**. Ví dụ:

~~~properties
spring.mail.host=smtp.provider.example
~~~

Khi gửi thư qua một SMTP relay, thư viện Jakarta Mail dùng hostname này để mở kết nối mạng. Host có thể là:

- Tên DNS của dịch vụ SMTP do nhà cung cấp cấp, ví dụ `smtp.provider.example`.
- Tên máy chủ SMTP nội bộ trong mạng doanh nghiệp, ví dụ `mail-relay.internal.example`.
- `localhost` hoặc tên container trong môi trường phát triển khi có SMTP server kiểm thử hoặc relay cục bộ.
- Một địa chỉ IP trong những môi trường được quản lý riêng, dù hostname hợp lệ thường thuận tiện hơn cho việc kiểm tra chứng chỉ TLS.

### Host SMTP khác với miền của người nhận

Giả sử ứng dụng muốn gửi tới `an@example.net` nhưng cấu hình:

~~~properties
spring.mail.host=smtp.provider.example
~~~

Ứng dụng **không kết nối trực tiếp đến `example.net`** chỉ vì đó là miền trong địa chỉ người nhận. Nó kết nối đến `smtp.provider.example`, gửi thông điệp và các địa chỉ nhận cho relay. Khi cần chuyển tiếp thư ra Internet, relay hoặc hạ tầng phía sau mới xác định nơi tiếp nhận email của miền `example.net`, thường dựa trên DNS MX.

~~~mermaid
flowchart LR
    A["Spring Boot"] -->|"spring.mail.host"| B["smtp.provider.example"]
    B -->|"Tìm tuyến nhận, ví dụ DNS MX"| C["Máy chủ email của example.net"]
    C --> D["Hộp thư an@example.net"]
~~~

Vì vậy, nhập **địa chỉ website**, **miền nhận thư** hoặc **MX của người nhận** vào `spring.mail.host` thường không đúng với cách ứng dụng gửi thư qua nhà cung cấp SMTP submission.

### Host và danh tính TLS

Nếu bật TLS kèm kiểm tra hostname, tên tại `spring.mail.host` cần tương thích với tên được chứng chỉ TLS của SMTP server xác nhận. Dùng địa chỉ IP hoặc hostname tùy ý trong khi chứng chỉ chỉ cấp cho tên khác có thể dẫn đến lỗi xác thực TLS.

Khi nhà cung cấp cho nhiều hostname hoặc endpoint theo vùng, nên sử dụng hostname mà tài liệu của họ chỉ định, cùng cổng và kiểu TLS tương ứng.

### Khi host không truy cập được

Các tình huống phổ biến:

- DNS không phân giải được tên host.
- Máy chủ ngừng hoạt động.
- Firewall hoặc mạng chặn cổng SMTP cần dùng.
- Ứng dụng chạy trong container nhưng dùng `localhost` sai ngữ cảnh: `localhost` của container là chính container đó, không phải máy host hay một container SMTP khác.
- Dịch vụ SMTP chỉ cho phép kết nối từ các mạng/IP được cấp quyền.

Những tình huống này là vấn đề kết nối tới **host đã cấu hình**, không phải lỗi cú pháp của `SimpleMailMessage` hay `MimeMessage`.

## 4. spring.mail.port — cổng TCP của dịch vụ SMTP

`spring.mail.port` chỉ định cổng mạng để kết nối trên host:

~~~properties
spring.mail.port=587
~~~

Đây là một số nguyên, khác với địa chỉ email hoặc số thứ tự mailbox. Một host có thể vận hành nhiều dịch vụ trên các cổng khác nhau; port giúp hệ điều hành kết nối đến đúng dịch vụ SMTP.

Các cổng thường gặp:

| Cổng | Cách dùng thường gặp | Bảo mật kết nối |
| --- | --- | --- |
| **25** | Chuyển thư SMTP giữa các máy chủ (*mail transfer*) | Có thể thương lượng STARTTLS theo chính sách của hệ thống |
| **587** | Nộp thư từ ứng dụng/email client tới relay (*submission*) | Thường hỗ trợ STARTTLS; nhà cung cấp có thể bắt buộc xác thực và TLS |
| **465** | Submission với TLS ngay khi kết nối (*implicit TLS*) | TLS handshake bắt đầu trước khi gửi lệnh SMTP |
| Cổng tùy chỉnh | SMTP nội bộ hoặc dịch vụ kiểm thử | Phụ thuộc cấu hình của hệ thống |

Số cổng **không tự bật TLS**. Ví dụ đặt `port=587` mà không bật cấu hình STARTTLS không đồng nghĩa dữ liệu chắc chắn được mã hóa. Tương tự, kết nối cổng 465 yêu cầu client ở chế độ implicit TLS khi máy chủ cung cấp dịch vụ đó.

### Không khai báo port thì sao?

Thư viện SMTP thường có hành vi mặc định khi không chỉ định cổng (SMTP truyền thống thường dùng cổng 25). Tuy vậy, **không nên dựa vào cổng mặc định để triển khai ứng dụng** nếu nhà cung cấp yêu cầu 587 hoặc 465. Khai báo port tường minh giúp cấu hình rõ ràng và tránh kết nối nhầm dịch vụ.

Lưu ý không có quan hệ cố định kiểu “port 587 luôn phải dùng mọi ứng dụng” hoặc “port 25 không bao giờ dùng được”. Hãy ưu tiên **bộ thông số host, port, TLS và auth mà SMTP provider yêu cầu**.

### Ví dụ lỗi do ghép sai cổng và giao thức

Một server đang đợi **TLS handshake ngay từ đầu** ở cổng 465; client lại bắt đầu bằng lệnh SMTP plaintext để thương lượng STARTTLS. Hai bên chờ các byte khác nhau, gây timeout hoặc lỗi handshake.

Ngược lại, một server 587 đợi lời chào SMTP rồi lệnh `STARTTLS`; client lại khởi tạo implicit TLS ngay khi kết nối. Đó cũng là cấu hình sai dù hostname và username đều đúng.

## 5. spring.mail.username — danh tính xác thực SMTP

`spring.mail.username` là giá trị username mà client cung cấp cho quá trình xác thực SMTP khi dịch vụ sử dụng SMTP AUTH:

~~~properties
spring.mail.username=mailer@example.org
~~~

Nhà cung cấp có thể yêu cầu:

- Địa chỉ email đầy đủ như `mailer@example.org`.
- Tên đăng nhập do hệ thống cấp, không nhất thiết là địa chỉ email.
- Tên định danh cố định, trong khi phần bí mật là một API key hoặc token được provider hỗ trợ.
- Một cơ chế xác thực khác cần cấu hình hoặc thư viện bổ sung.

Vì vậy, **username không phải lúc nào cũng trùng với địa chỉ email gửi**.

### Username khác From và Reply-To

Ba giá trị dưới đây đảm nhiệm ba vai trò khác nhau:

| Giá trị | Vai trò |
| --- | --- |
| `spring.mail.username` | Danh tính đăng nhập với SMTP server, nếu có xác thực |
| `From` trên message | Địa chỉ người gửi hiển thị trong nội dung email |
| `Reply-To` trên message | Địa chỉ được gợi ý để người nhận trả lời |

Ví dụ ứng dụng có thể đăng nhập SMTP bằng `smtp-account-42` nhưng gửi với:

~~~text
From: Notifications <notice@example.org>
Reply-To: helpdesk@example.org
~~~

Điều này chỉ hoạt động nếu nhà cung cấp cho phép sử dụng danh tính người gửi đó. Họ có thể yêu cầu xác minh miền/địa chỉ, ghi đè `From` hoặc từ chối gửi nếu không khớp chính sách.

**Spring Boot không mặc nhiên lấy `spring.mail.username` để gán `From` cho mọi thông điệp.** Nếu sản phẩm cần một người gửi cố định, hãy khai báo cấu hình ứng dụng riêng, ví dụ `app.mail.from`, rồi dùng `setFrom(...)`.

### SMTP không xác thực có cần username?

Không phải mọi SMTP server đều yêu cầu đăng nhập. Một relay nội bộ được giới hạn bởi mạng/IP hoặc một SMTP server kiểm thử có thể cho phép gửi không cần SMTP AUTH. Trong trường hợp đó, `spring.mail.username` và `spring.mail.password` có thể được bỏ trống nếu đúng với chính sách server.

Tuy nhiên, việc server không yêu cầu xác thực **không có nghĩa nó được mở công khai để mọi người gửi**. Hạ tầng cần chính sách chống open relay và giới hạn nguồn kết nối phù hợp.

## 6. spring.mail.password — bí mật xác thực SMTP

`spring.mail.password` là dữ liệu bí mật dùng cùng cơ chế xác thực của nhà cung cấp SMTP:

~~~properties
spring.mail.password=${SMTP_PASSWORD}
~~~

Cấu hình trên yêu cầu Spring Boot lấy giá trị từ biến môi trường `SMTP_PASSWORD` khi ứng dụng khởi động. Đây là placeholder **thay thế cấu hình của Spring**, không phải chuỗi mật khẩu theo nghĩa đen và cũng không phải một cơ chế tự tạo bí mật.

Tên gọi `password` không có nghĩa phải dùng **mật khẩu đăng nhập web của tài khoản cá nhân**. Nhà cung cấp có thể yêu cầu mật khẩu ứng dụng, thông tin SMTP credential được cấp riêng hoặc khóa gửi thư có cơ chế dùng phù hợp. Cần làm theo tài liệu chính thức của nhà cung cấp.

### Vì sao không ghi mật khẩu trực tiếp?

Cấu hình kiểu sau không nên được đưa vào mã nguồn hoặc Git:

~~~properties
# Ví dụ cách cấu hình cần tránh:
spring.mail.password=your-real-password-here
~~~

Một mật khẩu lưu trực tiếp có thể đi vào lịch sử Git, bản sao repository, artifact xây dựng, ảnh chụp màn hình, log hoặc hệ thống CI. Sau khi đã lộ, xóa dòng ở commit mới **không chắc xóa được các bản sao cũ**; thường phải thu hồi/đổi khóa bị lộ.

Nên cấp bí mật qua môi trường chạy, kho bí mật của nền tảng hoặc cơ chế quản lý cấu hình có bảo vệ. Tài khoản dùng cho ứng dụng nên được cấp quyền phù hợp và có khả năng xoay vòng khi cần.

### Phân biệt biến môi trường và file .env

Spring Boot hỗ trợ lấy biến môi trường hệ điều hành và các nguồn cấu hình đã được nạp. Nhưng **một file `.env` đặt tùy ý trong thư mục dự án không mặc nhiên được Spring Boot nạp như biến môi trường**. Nếu sử dụng công cụ chạy container/IDE/script để nạp `.env`, chính công cụ đó phải đưa giá trị vào môi trường chạy hoặc nguồn cấu hình mà Spring đọc.

Đừng đặt mật khẩu thật trong ví dụ mã nguồn hoặc trong tham số lệnh khởi động nếu chúng có nguy cơ bị lưu vào shell history, danh sách tiến trình hoặc log của hệ thống triển khai.

## 7. Cấu hình cả bốn thuộc tính trong application.properties

Một cấu hình SMTP submission phổ biến dùng STARTTLS có thể viết như sau:

~~~properties
# Đích SMTP submission do nhà cung cấp cấp
spring.mail.host=smtp.provider.example
spring.mail.port=587

# Thông tin xác thực lấy từ môi trường
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

# Thuộc tính bổ sung cho Jakarta Mail SMTP transport
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

# Giới hạn thời gian chờ (mili giây)
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000

# Cấu hình riêng của ứng dụng, không thuộc spring.mail.*
app.mail.from=${APP_MAIL_FROM}
~~~

Cấu hình chia thành ba nhóm có ý nghĩa:

1. **`host` và `port`**: đích kết nối.
2. **`username` và `password`**: thông tin xác thực, khi server yêu cầu.
3. **`mail.smtp.*`**: thuộc tính bổ sung của Jakarta Mail, ví dụ SMTP AUTH, STARTTLS, xác thực hostname và timeout.

`app.mail.from` là khóa tùy chỉnh của **ứng dụng** để biểu diễn người gửi mặc định. Spring Boot không có quy ước rằng một khóa tùy chỉnh này sẽ tự điền `From`; mã gửi thư cần đọc và sử dụng giá trị đó.

### Vì sao cần thêm mail.smtp.auth?

Bốn thuộc tính `spring.mail.host`, `port`, `username`, `password` xác định đích và thông tin xác thực. Khi SMTP provider yêu cầu đăng nhập, cấu hình thường đi cùng:

~~~properties
spring.mail.properties.mail.smtp.auth=true
~~~

Thuộc tính này nói với Jakarta Mail SMTP transport rằng dịch vụ sử dụng SMTP AUTH. Cách xác thực cụ thể có thể phụ thuộc cơ chế mà server quảng bá và client hỗ trợ. Khi server yêu cầu OAuth2 hoặc một phương thức riêng, chỉ cung cấp username/password thông thường có thể chưa đủ.

Không nên nhầm `mail.smtp.auth=true` với TLS: **AUTH xác thực tài khoản**, còn **TLS bảo vệ kết nối mạng**. Chúng giải quyết hai yêu cầu khác nhau và thường được sử dụng cùng nhau.

### STARTTLS tùy chọn và STARTTLS bắt buộc

~~~properties
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
~~~

- `starttls.enable=true` cho phép client yêu cầu nâng cấp sang TLS khi server hỗ trợ.
- `starttls.required=true` yêu cầu STARTTLS khả dụng và thực hiện thành công; nếu không, thao tác gửi phải thất bại.

Khi dùng tài khoản SMTP trên một mạng không hoàn toàn tin cậy, cấu hình **yêu cầu TLS** và xác thực hostname phù hợp giúp tránh vô tình gửi thông tin qua kết nối plaintext.

### Timeout không phải chức năng tự gửi lại

Ba thuộc tính `connectiontimeout`, `timeout` và `writetimeout` giới hạn những loại thời gian chờ khi kết nối, đọc hoặc ghi. Chúng giúp tránh những kết nối kẹt quá lâu, nhưng **không tự tạo retry queue**, không tự loại bỏ người nhận trùng và không bảo đảm email được giao đến người nhận.

Một lỗi timeout vẫn cần xử lý theo ngữ cảnh, vì có trường hợp phía SMTP server đã chấp nhận thư nhưng phản hồi cuối không đến được ứng dụng. Gửi lại nguyên message có thể tạo thư trùng.

## 8. Cấu hình tương đương bằng application.yml

Nếu dự án sử dụng YAML, có thể diễn đạt cùng ý định:

~~~yaml
spring:
  mail:
    host: smtp.provider.example
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

app:
  mail:
    from: ${APP_MAIL_FROM}
~~~

Trong YAML, cấu trúc phân cấp biểu diễn `spring.mail.properties.mail.smtp.*`. Một lưu ý thực tế: các thuộc tính dưới `spring.mail.properties` được dùng làm **thuộc tính của Jakarta Mail**, không phải các tùy chọn Spring Boot tự đổi nghĩa. Nếu dùng YAML và cần một khóa phẳng có dấu chấm, có thể sử dụng cách biểu diễn phù hợp với cơ chế ánh xạ cấu hình; ví dụ cấu trúc lồng nhau ở trên làm rõ từng phân cấp.

Ví dụ trên không chứa credential thật; các biến môi trường phải được cấp trong môi trường chạy. Với YAML, cũng cần giữ đúng khoảng thụt lề và tránh vô ý viết key giống nhau nhiều lần rồi làm mất cấu hình mong muốn.

### Sử dụng các biến môi trường SPRING_MAIL_*

Spring Boot hỗ trợ ánh xạ tên thuộc tính sang biến môi trường. Ví dụ:

~~~text
SPRING_MAIL_HOST=smtp.provider.example
SPRING_MAIL_PORT=587
SPRING_MAIL_USERNAME=<giá trị được cấp>
SPRING_MAIL_PASSWORD=<bí mật được cấp>
~~~

Các dòng trên mô tả **tên biến**, không phải file cấu hình cần commit cùng ứng dụng và không phải lệnh shell nên sao chép nguyên văn. Cách cấp biến phụ thuộc Docker, IDE, hệ điều hành, CI/CD hoặc nền tảng triển khai.

Có thể sử dụng trực tiếp các biến môi trường theo quy tắc ánh xạ của Spring Boot, hoặc dùng placeholder `${SMTP_USERNAME}`/`${SMTP_PASSWORD}` như trong các ví dụ trước. Chọn cách nhất quán theo hạ tầng quản lý cấu hình của dự án.

## 9. Cấu hình implicit TLS khi SMTP server dùng cổng 465

Một số nhà cung cấp hỗ trợ SMTP submission qua **implicit TLS** trên cổng 465. Khi đó, TLS handshake bắt đầu ngay sau khi mở TCP connection; không thực hiện giai đoạn SMTP plaintext rồi nâng cấp bằng lệnh `STARTTLS`.

Ví dụ:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=465
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Trong trường hợp này, `mail.smtp.ssl.enable=true` yêu cầu kết nối SMTP được bảo vệ bằng TLS ngay từ đầu. Không cần yêu cầu `STARTTLS` trên một kết nối vốn đã bắt đầu trong TLS.

So sánh ngắn:

| Đặc điểm | Submission STARTTLS (thường 587) | Submission implicit TLS (thường 465) |
| --- | --- | --- |
| Kết nối ban đầu | SMTP thông thường | TLS handshake ngay lập tức |
| Cách bật TLS | Lệnh `STARTTLS` trên kết nối SMTP | Bật `mail.smtp.ssl.enable=true` |
| Thuộc tính chính | `mail.smtp.starttls.enable`, có thể `required` | `mail.smtp.ssl.enable` |
| Xác thực danh tính server | Nên bật kiểm tra hostname | Nên bật kiểm tra hostname |
| Thông tin đăng nhập | Theo yêu cầu SMTP provider | Theo yêu cầu SMTP provider |

Không nên chỉ đổi `port` rồi giữ nguyên mọi thuộc tính TLS từ một cấu hình khác. **Host, port, loại TLS và auth phải tạo thành một bộ thông số tương thích**.

## 10. Gửi thư thử bằng JavaMailSender

Sau khi cấu hình SMTP, một dịch vụ có thể nhận `JavaMailSender` qua constructor injection và gửi thư:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;
    private final String from;

    public WelcomeMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from) {

        this.mailSender = mailSender;
        this.from = from;
    }

    public void sendWelcome(String recipient) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Địa chỉ người nhận không được để trống"
            );
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject("Chào mừng bạn");
        message.setText(
                "Tài khoản của bạn đã được tạo thành công."
        );

        mailSender.send(message);
    }
}
~~~

Mối liên hệ giữa mã và cấu hình:

| Bước | Bên phụ trách |
| --- | --- |
| Chọn người nhận, tiêu đề và nội dung | `WelcomeMailService` |
| Lấy địa chỉ `From` riêng của ứng dụng | `app.mail.from` |
| Biết host, port, username, password | Cấu hình Spring Boot `spring.mail.*` |
| Xây dựng và chuyển thư qua SMTP | `JavaMailSender` và Jakarta Mail |
| Chấp nhận thư, chuyển tiếp, xử lý giới hạn và bounce | SMTP relay / hạ tầng email |

Để chạy thành công, cần host SMTP thật, cấu hình quyền gửi, tài khoản (nếu có xác thực) và một địa chỉ `From` mà nhà cung cấp chấp nhận. Thư sau khi được SMTP relay chấp nhận vẫn có thể bị trả lại hoặc rơi vào thư mục spam; việc `send(...)` trả về bình thường không chứng minh thư đã vào Inbox.

### Dùng MimeMessageHelper với HTML và Unicode

Khi cần HTML, tệp đính kèm hoặc cấu trúc MIME, có thể dùng cùng `JavaMailSender`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(String recipient) throws MessagingException {
    MimeMessage mime = mailSender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(mime, false, "UTF-8");

    helper.setFrom(from);
    helper.setTo(recipient);
    helper.setSubject("Xác nhận đăng ký ✅");
    helper.setText(
            "<p>Đăng ký của bạn <strong>đã hoàn tất</strong>.</p>",
            true
    );

    mailSender.send(mime);
}
~~~

Phương thức được minh họa như một thành viên **bổ sung của lớp dịch vụ đã có** trường `mailSender` và `from`. `MimeMessageHelper` xử lý phần nội dung/định dạng; nó không cần tự truy xuất host hoặc username. Cấu hình kết nối được sử dụng lại khi gọi `send(...)`.

## 11. Mỗi môi trường có thể sử dụng SMTP khác nhau

Một ứng dụng thường có nhiều môi trường:

- **Local development:** SMTP server thử nghiệm giữ lại email trong giao diện kiểm thử, không chuyển thư ra Internet.
- **Test/staging:** tài khoản SMTP được giới hạn quyền, quota thấp hoặc chỉ gửi tới nhóm kiểm thử.
- **Production:** SMTP relay chính thức, domain/sender đã xác minh, credential được quản lý an toàn.

Ví dụ cùng mã `WelcomeMailService` vẫn hoạt động với cấu hình khác:

| Môi trường | `host` | `port` | `username/password` |
| --- | --- | --- | --- |
| Local với SMTP test server | `localhost` hoặc hostname container nội bộ | Cổng của test server | Có thể không cần |
| Staging | SMTP sandbox của nhà cung cấp | Theo provider | Credential staging |
| Production | SMTP relay chính thức | Theo provider | Credential production |

Trong môi trường container, `localhost` trỏ về **container hiện tại**. Nếu SMTP test server chạy trong container khác, cần dùng tên mạng/container được phân giải trong cùng mạng thay vì mặc định `localhost`.

Có thể dùng các profile của Spring Boot như `application-local.yml` và `application-prod.yml` để khai báo host/port tương ứng. **Không nên commit credential production vào file profile**. Những bí mật này nên được cấp độc lập từ hạ tầng triển khai.

Một lưu ý: khi sử dụng placeholder không có giá trị môi trường tương ứng, quá trình tạo cấu hình hoặc sử dụng bean có thể thất bại. Với hệ thống cần gửi email, đây thường là tín hiệu cần sửa cấu hình, thay vì thay mật khẩu bằng chuỗi mặc định không an toàn.

## 12. Cấu hình spring.mail.* có tự kiểm tra server khi khởi động?

Thông thường, việc có bean `JavaMailSender` và bốn thuộc tính đã được bind **không đồng nghĩa** ứng dụng đã thiết lập kết nối SMTP hoặc xác thực thành công. Nhiều lỗi chỉ xuất hiện khi thực hiện gửi thực tế.

Spring Boot có tùy chọn:

~~~properties
spring.mail.test-connection=true
~~~

Khi được hỗ trợ và áp dụng, tùy chọn này yêu cầu thử kết nối với server khi khởi tạo cấu hình mail. Nó có thể giúp phát hiện sớm host/port/credential không phù hợp, nhưng cũng tạo **phụ thuộc khởi động ứng dụng vào khả năng truy cập SMTP tại thời điểm đó**.

Không nên coi `test-connection=true` là bằng chứng mọi email sau này sẽ gửi thành công:

- Kết nối có thể thành công lúc khởi động nhưng thất bại lúc gửi.
- Một tài khoản có thể xác thực được nhưng không có quyền dùng một địa chỉ `From` cụ thể.
- SMTP provider có thể giới hạn recipient, quota hoặc nội dung.
- Thư có thể được relay tiếp nhận nhưng chuyển phát thất bại sau đó.

Đối với ứng dụng cần tiếp tục phục vụ chức năng khác ngay cả khi SMTP tạm thời ngừng, cần cân nhắc cẩn thận việc buộc kiểm tra kết nối lúc khởi động. Với ứng dụng gửi thư chuyên biệt, việc phát hiện cấu hình lỗi từ đầu có thể hữu ích.

## 13. Thông số sai thường biểu hiện ra sao?

Các lỗi cấu hình có thể được nhận diện theo giai đoạn:

| Triệu chứng | Thuộc tính nên kiểm tra trước | Lý do thường gặp |
| --- | --- | --- |
| Không thể phân giải hoặc kết nối SMTP host | `spring.mail.host` | Sai hostname, DNS lỗi, hostname không truy cập được |
| Connection refused / timeout | `host` và `port` | Sai cổng, firewall chặn, server không chạy |
| TLS handshake thất bại | `port` và `spring.mail.properties.mail.smtp.*` | STARTTLS/implicit TLS không khớp server, chứng chỉ hoặc hostname không hợp lệ |
| SMTP báo xác thực thất bại | `username`, `password`, `mail.smtp.auth` | Sai credential, tài khoản bị khóa, sai cơ chế AUTH |
| Thư bị từ chối vì người gửi | `From` trên message và chính sách provider | Username hợp lệ nhưng địa chỉ `From` chưa được phép |
| Chờ quá lâu lúc gửi | Timeout của Jakarta Mail, network | Chưa giới hạn thời gian đọc/ghi hoặc hạ tầng phản hồi chậm |
| `JavaMailSender` không được tạo | Starter, `host`, cấu hình auto-configuration | Thiếu phụ thuộc, cấu hình host hoặc đã có bean tùy chỉnh |
| Gửi thành công nhưng người nhận không thấy thư | Không chỉ phụ thuộc bốn thuộc tính | Bounce, spam, địa chỉ sai, quota hoặc chính sách nhận |

### Lỗi xác thực: phân biệt username/password với TLS

Khi một SMTP relay trả lỗi `535 Authentication failed` hoặc thông báo tương tự, cần kiểm tra thông tin đăng nhập, cơ chế xác thực và trạng thái tài khoản. Nhưng lỗi xác thực cũng có thể xảy ra khi server chỉ cho phép AUTH sau STARTTLS mà client chưa nâng cấp thành công.

Ngược lại, nếu báo lỗi chứng chỉ TLS, thay đổi password không giúp khắc phục việc hostname hoặc chuỗi tin cậy bị sai. Cần đối chiếu **đúng giai đoạn kết nối → TLS → AUTH → nộp thư**.

### Lỗi sau khi SMTP chấp nhận

Nếu lệnh gửi được phản hồi thành công, điều đó thông thường chỉ xác nhận SMTP relay đã tiếp nhận thông điệp tại thời điểm nộp. Việc chuyển thư qua các máy chủ và đến hộp thư đích có thể diễn ra sau đó.

Khi sản phẩm cần biết trạng thái từng người nhận, nên tích hợp phản hồi bounce, webhook hoặc sự kiện chuyển phát từ nhà cung cấp email. `spring.mail.*` không tự cung cấp chức năng theo dõi Inbox.

## 14. Bí mật, log và quản trị vận hành

Bốn thuộc tính có mức độ nhạy cảm khác nhau:

- `spring.mail.host` và `port` thường là thông tin cấu hình dịch vụ; không phải mật khẩu nhưng cũng cần được quản trị theo môi trường.
- `spring.mail.username` có thể tiết lộ danh tính tài khoản dịch vụ, nên giới hạn xuất hiện trong log nếu không cần.
- `spring.mail.password` là bí mật, phải được bảo vệ và không được in ra console, log hoặc phản hồi API.

Một số nguyên tắc vận hành:

1. Dùng tài khoản SMTP riêng cho ứng dụng và chỉ cấp quyền cần thiết.
2. Lưu credential trong kho bí mật hoặc cấu hình môi trường được bảo vệ, không commit vào repository.
3. Có quy trình **xoay vòng/thu hồi credential** mà không phải sửa mã nghiệp vụ.
4. Bật TLS và xác thực hostname theo cách SMTP provider hỗ trợ.
5. Không ghi raw MIME hoặc nội dung email thật vào log để tránh lộ dữ liệu cá nhân.
6. Giới hạn timeout, tốc độ gửi và số lần thử lại theo yêu cầu sản phẩm.
7. Tách credential local, staging và production, tránh dùng một tài khoản cho mọi nơi.
8. Không bật debug Jakarta Mail tràn lan trên production vì log phiên giao thức có thể chứa địa chỉ email và metadata nhạy cảm.

Nếu một credential bị lộ, cần thu hồi hoặc thay đổi theo quy trình của nhà cung cấp. Việc xóa một dòng cấu hình khỏi file mới chưa chắc đã xóa bí mật khỏi lịch sử Git hoặc hệ thống log.

## 15. Những ngộ nhận thường gặp

### “Có username thì Spring tự dùng địa chỉ đó làm From”

Không. `spring.mail.username` là thông tin xác thực SMTP; `From` là trường của email do ứng dụng đặt. Nhà cung cấp có thể yêu cầu From tương thích với tài khoản nhưng đó là **chính sách của server**, không phải quy tắc tự động của bốn thuộc tính.

### “Port 587 đồng nghĩa email đã được mã hóa”

Không. Bản thân port chỉ xác định điểm kết nối TCP. STARTTLS cần được cấu hình và thương lượng thành công; nếu cần buộc TLS, phải có chính sách yêu cầu TLS và xác thực server.

### “Mọi SMTP server đều cần username/password”

Không. Relay nội bộ hoặc server kiểm thử có thể dùng cơ chế cho phép khác. Nhưng ứng dụng phải tuân thủ chính sách truy cập của server; không nên xây dựng open relay công khai.

### “Password là mật khẩu đăng nhập web thông thường”

Không nhất thiết. Nhiều nhà cung cấp yêu cầu **credential dành riêng cho SMTP**, app password, token hoặc cơ chế xác thực khác. Sử dụng đúng loại credential mà provider cấp.

### “Host phải là MX của người nhận”

Không. Với cấu hình thông dụng, host là **SMTP submission relay** của ứng dụng. Relay chịu trách nhiệm định tuyến và chuyển thư tới miền người nhận.

### “Chỉ cần bốn thuộc tính là gửi email an toàn”

Chưa đủ. Cần cấu hình TLS phù hợp, danh tính server, quyền gửi, địa chỉ From, quản lý bí mật và xử lý lỗi. Bốn thuộc tính chủ yếu mô tả **kết nối và xác thực**.

### “Có password trong application.properties nhưng không commit là an toàn”

Vẫn cần xét nơi lưu file, quyền truy cập, bản sao và cách triển khai. File có thể bị đồng bộ hoặc sao lưu không chủ đích. Kho bí mật và cơ chế cấp biến môi trường được quản lý thường thích hợp hơn cho credential production.

### “Đã kết nối SMTP thành công thì mọi email sẽ vào Inbox”

Không. SMTP có nhiều giai đoạn; nhà cung cấp và hệ thống nhận còn xử lý quyền gửi, địa chỉ đích, chính sách spam, quota và các phản hồi chuyển phát về sau.

## 16. Bài tập suy luận cấu hình

**Tình huống 1.** Nhà cung cấp yêu cầu `smtp.provider.example`, cổng 587, SMTP AUTH và STARTTLS bắt buộc. Bạn cần những nhóm thuộc tính nào?

Cần `spring.mail.host`, `spring.mail.port`, credential tương ứng, `mail.smtp.auth=true` và `mail.smtp.starttls.enable=true` cùng `required=true`, cộng kiểm tra danh tính server theo chính sách. Không chỉ đặt port 587 rồi coi đó là TLS.

**Tình huống 2.** Ứng dụng đăng nhập bằng `mailer@example.org` nhưng muốn gửi thư từ `support@example.org`. Chỉ đặt `spring.mail.username=mailer@example.org` là đủ chưa?

Chưa. Phải đặt `From` trên message thành `support@example.org` và đảm bảo SMTP provider cho phép danh tính đó. `username` không tự biến thành `From`.

**Tình huống 3.** Có cấu hình đầy đủ nhưng khi chạy trong Docker, `spring.mail.host=localhost` kết nối lỗi. Vì sao?

`localhost` trỏ về chính container ứng dụng. Nếu SMTP relay chạy ở máy host hoặc container khác, cần hostname hoặc cấu hình mạng tương ứng với nơi SMTP server thực sự chạy.

**Tình huống 4.** Ứng dụng dùng cổng 465 implicit TLS mà chỉ bật `starttls.enable=true`. Điều gì có thể xảy ra?

Client có thể bắt đầu sai kiểu kết nối so với server, gây timeout hoặc TLS handshake lỗi. Cần dùng `mail.smtp.ssl.enable=true` cho implicit TLS theo yêu cầu provider.

**Tình huống 5.** SMTP test server không yêu cầu xác thực. Có bắt buộc phải đặt username/password giả không?

Không. Chỉ cung cấp các thuộc tính mà môi trường thực sự yêu cầu. Đồng thời bảo đảm SMTP test server không bị truy cập trái phép ngoài môi trường kiểm thử.

**Tình huống 6.** Thư được nộp cho relay nhưng người nhận chưa thấy. Có thể chỉ đổi `spring.mail.password` để sửa không?

Không có căn cứ. Cần xem trạng thái chuyển phát, bounce, spam, địa chỉ nhận và chính sách của nhà cung cấp. Password đúng chỉ giải quyết một phần của quá trình xác thực để nộp thư.

## 17. Mô hình ghi nhớ

Khi đọc bốn thuộc tính mail của Spring Boot, có thể đặt bốn câu hỏi:

| Câu hỏi | Thuộc tính trả lời |
| --- | --- |
| **Kết nối tới máy chủ nào?** | `spring.mail.host` |
| **Kết nối qua cổng nào?** | `spring.mail.port` |
| **Đăng nhập bằng danh tính nào?** | `spring.mail.username` |
| **Dùng bí mật gì để xác thực?** | `spring.mail.password` |

Các câu hỏi tiếp theo nằm ở nơi khác: **TLS có bắt buộc không?** → `spring.mail.properties.mail.smtp.*`; **thư có From/To/Subject/body gì?** → mã tạo message; **thư đã chuyển phát chưa?** → SMTP relay và cơ chế theo dõi hạ tầng email.

Một cấu hình Spring Boot dễ bảo trì là cấu hình có **host/port rõ ràng**, **credential lấy từ nguồn bí mật phù hợp**, **TLS đúng với nhà cung cấp** và mã nghiệp vụ chỉ sử dụng `JavaMailSender`. Nắm vững ranh giới này giúp thay môi trường hoặc nhà cung cấp SMTP mà vẫn giữ được logic gửi thư rõ ràng, đồng thời giảm lỗi kết nối, xác thực và lộ thông tin bí mật.

