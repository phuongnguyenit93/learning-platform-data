# Profile phát triển, kiểm thử, staging và production

## 1. Vì sao cấu hình gửi mail phải khác nhau theo môi trường?

Ứng dụng sử dụng **Spring Framework Mail** thường kết nối đến SMTP server thông qua **JavaMailSender**. Khi phát triển trên máy cá nhân, chạy automated tests, triển khai staging và đưa lên production, ứng dụng có thể dùng **cùng một API gửi thư**, nhưng mục đích gửi, máy chủ SMTP, tài khoản, người nhận được phép và yêu cầu vận hành lại khác nhau.

Một lỗi cấu hình mail dễ gây tác động thực tế: developer thử chức năng gửi thông báo nhưng dùng nhầm SMTP production, khiến khách hàng thật nhận email thử nghiệm; hoặc một bộ kiểm thử tự động chạy hàng trăm lần và vô tình gửi hàng trăm email thật. Ở chiều ngược lại, nếu production vẫn dùng SMTP sink giả lập của môi trường local, khách hàng không nhận được thông báo mặc dù ứng dụng có thể ghi log “send thành công”.

Spring Boot hỗ trợ **profiles** để chọn các tập cấu hình khác nhau tùy môi trường. Với Spring Mail, mục tiêu là:

1. **Local/development**: nhìn thấy email được tạo ra mà không phát ra Internet.
2. **Test**: kiểm tra nội dung và tương tác gửi mail một cách lặp lại, độc lập mạng, không sử dụng credential thật.
3. **Staging**: kiểm thử luồng gửi gần với production nhưng phải hạn chế người nhận và tránh gửi nhầm ra ngoài.
4. **Production**: dùng SMTP provider thật, TLS, secret có quản lý, logging/monitoring, timeout và chính sách vận hành phù hợp.

Sơ đồ phân tách:

~~~mermaid
flowchart LR
    A[Spring application code] --> B[JavaMailSender / Mail service]
    B --> C{Active Spring profile}
    C -->|local| D[SMTP sink / inbox giả lập]
    C -->|test| E[Mock, fake hoặc SMTP test server]
    C -->|staging| F[SMTP sandbox + hạn chế recipient]
    C -->|prod| G[SMTP provider thật]
~~~

**Profile chọn cấu hình và wiring**, còn **quy tắc được phép gửi đến ai** phải được ứng dụng hoặc hạ tầng thực thi. Chỉ đặt tên profile là staging không tự động ngăn ứng dụng gửi email tới địa chỉ khách hàng thật.

## 2. Spring profile chọn và ghi đè cấu hình như thế nào?

Spring Boot thường đọc cấu hình cơ sở từ **application.yml**, sau đó kết hợp nguồn cấu hình theo profile đang được kích hoạt, ví dụ:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
└── application-prod.yml

src/test/resources/
└── application-test.yml
~~~

Đây là cách bố trí ví dụ, không phải bắt buộc. Tệp trong **src/test/resources** chỉ xuất hiện ở classpath test thông thường; cấu hình test có thể đặt nơi khác nếu quy trình build yêu cầu. Profile cũng có thể đến từ file .properties, tài nguyên ngoài ứng dụng, biến môi trường, command-line argument hoặc nền tảng triển khai.

Ví dụ:

~~~yaml
# application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

~~~yaml
# application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
~~~

Khi profile **local** được kích hoạt, ứng dụng nhận các thuộc tính chung (encoding, timeout) kết hợp với host/port của local. Các thuộc tính cùng khóa ở nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị trước đó. **Thứ tự ưu tiên configuration properties của Spring Boot phụ thuộc nguồn và hoàn cảnh nạp cấu hình**; không nên nghĩ đơn giản rằng mọi biến môi trường đều “luôn” có tác dụng giống mọi tệp YAML. Cần hiểu cơ chế externalized configuration, đặc biệt khi đồng thời dùng command line, biến môi trường, ConfigMap hoặc secret.

Kích hoạt profile khi chạy JAR:

~~~bash
java -jar application.jar --spring.profiles.active=local
~~~

Hoặc đặt biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=staging
~~~

Ở một dịch vụ triển khai, biến môi trường được truyền cho **tiến trình Java** trước khi khởi động. Không nên đặt mặc định **spring.profiles.active: prod** trong file cấu hình chung rồi hy vọng developer sẽ luôn nhớ ghi đè; việc lựa chọn môi trường nên được hệ thống chạy/triển khai quyết định rõ ràng.

### Nhiều profile cùng hoạt động

Spring có thể kích hoạt nhiều profile cùng lúc. Khi nhiều tài liệu cấu hình khai báo trùng một thuộc tính, thứ tự xử lý profile và độ ưu tiên nguồn có thể quyết định giá trị cuối. Ví dụ kết hợp **local,prod** có thể dẫn đến host một môi trường nhưng credential của môi trường khác nếu cấu hình không được kiểm soát.

Đối với cấu hình mail, nên coi **local**, **test**, **staging**, **prod** là **bốn môi trường triển khai loại trừ nhau** trong chính sách vận hành; nếu cần thêm profile tính năng khác, hãy xác định rõ thứ tự và ranh giới của chúng. Không dùng tên profile như lớp bảo mật duy nhất.

### Tên test, staging, prod chỉ là quy ước

Spring không tự hiểu rằng profile tên **test** phải vô hiệu hóa gửi mail, profile tên **staging** phải giới hạn người nhận hoặc profile tên **prod** phải bật TLS. Các hành vi đó chỉ xuất hiện khi ứng dụng **cấu hình bean, property và policy** tương ứng.

## 3. Ma trận mục tiêu cho bốn môi trường

| Khía cạnh | Local/development | Automated test | Staging | Production |
|---|---|---|---|---|
| SMTP endpoint | SMTP sink chạy local | Mock/fake hoặc test SMTP server | Sandbox hoặc relay riêng | SMTP provider/relay thật |
| Credential | Không cần nếu sink cho phép | Không có credential thật | Secret staging riêng | Secret production |
| Người nhận | Dữ liệu giả/lập | Địa chỉ fixture | Allowlist nội bộ hoặc domain sandbox | Người nhận hợp lệ theo nghiệp vụ |
| Hành vi gửi | Capture và hiển thị thư để debug | Verify, capture hoặc assert | End-to-end có rào chắn | Phát thư thật theo chính sách |
| TLS | Tùy sink local, thường không cần trên loopback | Không cần nếu mock | Bắt buộc khi giao tiếp với provider qua mạng | Bắt buộc khi hạ tầng yêu cầu, xác minh chứng chỉ |
| Khả năng quan sát | Web UI của sink, log đã làm sạch | Assertions và test reports | Metrics, log, event thử nghiệm | Metrics, queue, bounce/DSN/provider events |
| Thử gửi email thật | Không | Không | Chỉ tài khoản đích đã phê duyệt | Theo quy tắc ứng dụng |

Nên thiết kế **fail closed**: nếu ứng dụng không nhận ra môi trường hoặc không có cấu hình gửi hợp lệ, không tự chuyển sang SMTP production như “fallback” tiện lợi. Khi thiếu secret production, nên báo lỗi rõ ràng; khi test không có SMTP server, không được tự lén gọi host mail thật.

## 4. Cấu hình nền chung trong application.yml

Các thuộc tính **không nhạy cảm, dùng chung** có thể đặt trong file cơ sở:

~~~yaml
# src/main/resources/application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Ý nghĩa:

- **default-encoding**: charset mặc định cho nội dung email do JavaMailSender/MimeMessageHelper tạo khi dùng cấu hình này.
- **mail.smtp.connectiontimeout**: thời gian chờ thiết lập kết nối TCP đến SMTP server.
- **mail.smtp.timeout**: thời gian chờ đọc từ socket SMTP.
- **mail.smtp.writetimeout**: giới hạn thời gian chờ ghi dữ liệu vào socket theo Jakarta Mail transport.

Các thời gian tính bằng **mili giây**; con số chỉ là ví dụ. Nếu bỏ timeout hoặc đặt quá cao, luồng xử lý có thể bị giữ lâu khi mạng/SMTP server gặp sự cố. Timeout quá thấp lại tạo lỗi không cần thiết khi server hợp lệ phản hồi chậm.

**Cấu hình nền không đặt SMTP host/username/password thật.** Host và credential thuộc môi trường triển khai; phần này sẽ được định nghĩa trong từng profile hoặc được inject từ external configuration.

Spring Boot thường cung cấp **JavaMailSender auto-configuration** khi các thư viện cần thiết nằm trên classpath và cấu hình mail đáp ứng điều kiện. Nếu test profile không khai báo SMTP host mà ứng dụng lại tiêm JavaMailSender bắt buộc vào constructor, ứng dụng có thể không có bean phù hợp. Khi đó cần **cung cấp mock/fake bean trong test context** hoặc thiết kế một lớp gateway để chọn transport theo môi trường. Chỉ xóa thuộc tính SMTP host không tự biến send() thành noop.

## 5. Profile local: thu email vào SMTP sink

Khi phát triển local, dùng **SMTP sink** là cách thực tế để thử nội dung email mà không phát ra Internet. Các công cụ như **Mailpit**, **MailHog** hoặc một SMTP test server tương đương có thể nhận email qua SMTP và cho developer đọc nội dung qua giao diện web.

Ví dụ cấu hình local:

~~~yaml
# src/main/resources/application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false

app:
  mail:
    delivery-mode: CAPTURE
~~~

Trong ví dụ, SMTP sink được giả định đang lắng nghe **127.0.0.1:1025**; nếu chạy trong container, địa chỉ **127.0.0.1** trỏ về chính container ứng dụng, không phải host hay container SMTP sink. Khi dùng Docker Compose, ứng dụng có thể phải kết nối bằng **tên service** SMTP sink trong cùng network, ví dụ **mailpit:1025**. Port và hostname phải khớp cách triển khai thực tế.

Thuộc tính **app.mail.delivery-mode** là một **property do ứng dụng tự định nghĩa**, không phải cấu hình có sẵn của Spring Boot. Muốn dùng nó để kiểm soát logic thì phải xây dựng code đọc property và áp dụng chính sách, ví dụ ghi nhận CAPTURE, cấm gửi thật hoặc chọn adapter tương ứng. Chỉ thêm property vào YAML không tạo ra hành vi an toàn.

Luồng developer có thể kiểm tra:

~~~text
Local Spring Boot
    |
    | JavaMailSender.send()
    v
SMTP sink trên máy phát triển
    |
    v
Giao diện xem mail thu được
    |
    +-- Subject, To, From
    +-- Text/HTML
    +-- Attachment, MIME structure
~~~

SMTP sink có thể trả lời **250 accepted** khiến JavaMailSender.send() thành công; điều đó chỉ xác nhận **sink đã nhận và lưu để xem**, không chứng minh email được chuyển đến miền người nhận. Đây chính là hành vi mong muốn của môi trường local.

### Lưu ý khi demo và test thủ công

- Chỉ bind SMTP/web UI vào loopback hoặc network development phù hợp; không mặc định công khai giao diện chứa email thử nghiệm.
- Dùng dữ liệu giả hoặc dữ liệu đã khử nhạy cảm; sink thường giữ cả nội dung thư và tệp đính kèm.
- Với email HTML, kiểm tra cả text/plain, URL, hình ảnh inline và attachment; giao diện sink giúp quan sát MIME nhưng không thay thế kiểm thử ở email client thực tế.
- Khi thay đổi sender host, bảo đảm ứng dụng đã nạp đúng profile; không suy đoán dựa trên tên biến môi trường được đặt ở máy nhưng chưa truyền vào tiến trình.

## 6. Profile test: không phụ thuộc SMTP thật

Trong **unit test** và nhiều **integration test**, điều cần kiểm tra là: ứng dụng có yêu cầu gửi đúng người nhận, subject, body hoặc MIME part hay không. Thông thường không cần SMTP provider thật, vì mạng, tài khoản, hạn mức và việc phát thư làm test chậm, dễ flaky, hoặc vô tình gửi dữ liệu ra ngoài.

Một profile test an toàn có thể được khai báo như sau:

~~~yaml
# src/test/resources/application-test.yml
app:
  mail:
    delivery-mode: DISABLED
~~~

Một lần nữa, **app.mail.delivery-mode** chỉ hoạt động khi có code ứng dụng hiểu nó. Trong test chỉ mock JavaMailSender, cấu hình này có thể là metadata bổ sung cho chính sách môi trường; nó không tự thay thế mock.

### Kiểm tra tương tác JavaMailSender bằng mock

Với Spring Boot 3.3 và Spring Test/Mockito, có thể tạo test context có mock JavaMailSender rồi kiểm tra service đã tạo SimpleMailMessage đúng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class NotificationMailServiceTest {
    @Autowired
    private NotificationMailService service;

    @MockBean
    private JavaMailSender mailSender;

    @Test
    void shouldBuildWelcomeMessage() {
        service.sendWelcome("alice@example.test");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(mailSender).send(captor.capture());

        SimpleMailMessage message = captor.getValue();
        assertThat(message.getTo())
                .containsExactly("alice@example.test");
        assertThat(message.getSubject()).isEqualTo("Welcome");
    }
}
~~~

Ví dụ này giả định **NotificationMailService** đã tồn tại và phương thức **sendWelcome** tạo SimpleMailMessage rồi gọi JavaMailSender. Nó minh họa kiểu test, không phải lớp được Spring tự sinh. **@MockBean** phù hợp với Spring Boot 3.3; ở các phiên bản Spring/Boot mới hơn, cần kiểm tra cơ chế mock bean mà phiên bản dự án hỗ trợ.

Nếu ứng dụng dùng MimeMessage, test có thể dùng mock sender cho bước send nhưng vẫn cần một cơ chế tạo MimeMessage phục vụ kiểm tra. Một fake hoặc SMTP test server trong integration test sẽ tiện hơn nếu cần xác minh toàn bộ MIME, attachment và encoding. Không nên dùng một mock chỉ trả thành công để “kiểm chứng” STARTTLS hoặc SMTP AUTH, bởi mock không thực hiện giao thức SMTP.

### Integration test với SMTP test server

Khi cần thử **quá trình SMTP** (mã phản hồi, MIME, attachment, nhiều người nhận), có thể khởi động một SMTP test server trong quá trình test và trỏ **spring.mail.host/port** đến endpoint đó. Test cần tự quản lý vòng đời server, port và dữ liệu đã nhận; không được dùng credential production. Có thể chạy server trên một port động rồi truyền cấu hình vào Spring test context để tránh tranh chấp port giữa các job CI.

Phân biệt mục đích:

| Loại kiểm thử | Cách thay thế SMTP | Kiểm chứng được |
|---|---|---|
| Unit test | Mock JavaMailSender hoặc mock MailGateway | Lệnh gọi và dữ liệu request |
| Spring service test | MockBean/TestConfiguration | Wiring, validation, business rule |
| SMTP integration test | SMTP sink/test server cục bộ | Thực tế đóng gói MIME và giao thức submission |
| Staging end-to-end | SMTP sandbox/relay được quản lý | Cấu hình triển khai, kết nối mạng, TLS, credential, event |

Chọn một test phù hợp với điều muốn chứng minh. Test dùng mock không khẳng định khả năng phát thư thật; staging dùng provider thật không thay thế các unit test độc lập mạng.
## 7. Profile staging: gửi giống production nhưng có rào chắn

**Staging** là môi trường kiểm thử triển khai trước khi lên production. Đối với mail, staging thường cần xác minh nhiều hơn local: ứng dụng khởi động với biến môi trường, kết nối đến SMTP provider qua mạng, dùng TLS, xác thực tài khoản, phát sinh header/MIME đúng và xử lý phản hồi thực tế. Nhưng staging **không nên phát email cho tập người dùng production**.

Một cấu hình staging minh họa:

~~~yaml
# src/main/resources/application-staging.yml
spring:
  mail:
    host: ${STAGING_SMTP_HOST}
    port: 587
    username: ${STAGING_SMTP_USERNAME}
    password: ${STAGING_SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true

app:
  mail:
    delivery-mode: SANDBOX
    allowed-recipient-domains:
      - qa.example.org
~~~

Các tên biến **STAGING_SMTP_*** là ví dụ, không phải biến hệ thống được Spring tự cung cấp. Giá trị do hệ thống triển khai lấy từ secret store hoặc môi trường staging. Nếu thiếu giá trị bắt buộc, không nên âm thầm chuyển sang credential production.

**SANDBOX** và **allowed-recipient-domains** là cấu hình nghiệp vụ tự định nghĩa. Để chúng bảo vệ thật, ứng dụng phải có code kiểm tra người nhận, và provider có thể cung cấp cơ chế sandbox/test mode ở phía hạ tầng. Hai lớp bảo vệ nên được kết hợp:

- **Ở ứng dụng:** từ chối địa chỉ không thuộc allowlist, áp dụng cho cả **To, Cc, Bcc** và các luồng gửi khác.
- **Ở SMTP provider:** sử dụng tài khoản staging với quyền gửi hạn chế, domain đã dành riêng, chế độ sandbox hoặc chính sách không phát ra ngoài theo khả năng provider.

Không chỉ thay đổi header To hiển thị mà bỏ qua danh sách người nhận SMTP thực tế (envelope recipients). Quy tắc chặn phải áp dụng **trước bước gửi** đến tất cả đích có thể nhận thông điệp; nếu hệ thống có alias hoặc chuyển tiếp, cần kiểm soát ở hạ tầng đích nữa.

### Kiểm thử những gì ở staging?

1. **Kết nối:** host/port, DNS, firewall, TLS, chứng chỉ và cơ chế AUTH.
2. **Tạo nội dung:** subject, charset UTF-8, HTML/text alternative, inline resources, attachment và MIME boundary.
3. **Danh tính gửi:** địa chỉ From có được tài khoản SMTP cho phép; SPF/DKIM/DMARC của domain thử nghiệm được cấu hình nếu cần kiểm thử phát thư.
4. **Giới hạn:** kích thước MIME, số người nhận, rate limit, quota và phản hồi SMTP.
5. **Sự kiện bất đồng bộ:** submission accepted, deferred, bounced, provider webhook nếu provider hỗ trợ.
6. **An toàn dữ liệu:** dữ liệu thử được tạo riêng hoặc khử nhạy cảm; không sao chép nội dung thật của khách hàng vào mailbox staging thiếu bảo vệ.

Kết quả staging có thể cho thấy một email đã được **SMTP server chấp nhận**, nhưng không tự chứng minh đã đến Inbox của một người dùng cụ thể. Đừng dùng kết quả staging để khẳng định mọi domain bên ngoài đều phát thành công.

## 8. Profile production: bảo mật, độ tin cậy và quan sát

Production gửi thông điệp thật đến người nhận thật. Cấu hình cần tách biệt với staging về secret, quyền gửi và hạ tầng mạng. Một ví dụ trên **SMTP submission cổng 587 với STARTTLS**:

~~~yaml
# src/main/resources/application-prod.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000

app:
  mail:
    delivery-mode: LIVE
~~~

Trong YAML của Spring Boot, **${SMTP_HOST}** là placeholder được giải quyết từ configuration environment; **${SMTP_PORT:587}** có giá trị mặc định 587 khi không có biến phù hợp. Host, username, password không có fallback sang SMTP local hoặc staging. Nếu secret/provider không sẵn sàng, lỗi cấu hình phải được xử lý rõ ràng.

Các thuộc tính JavaMail:

| Thuộc tính | Tác dụng |
|---|---|
| **mail.smtp.auth=true** | Bật xác thực khi gửi qua SMTP |
| **mail.smtp.starttls.enable=true** | Cho phép nâng cấp kết nối bằng STARTTLS |
| **mail.smtp.starttls.required=true** | Yêu cầu STARTTLS thành công; không tiếp tục theo đường không TLS |
| **mail.smtp.ssl.checkserveridentity=true** | Kiểm tra danh tính hostname từ chứng chỉ trong SMTP TLS |
| **connectiontimeout** | Chặn thời gian chờ kết nối kéo dài |
| **timeout** | Giới hạn thời gian đọc socket |
| **writetimeout** | Giới hạn thời gian ghi socket theo transport |

**Cổng 465** thường dùng **implicit TLS** (bắt tay TLS ngay khi kết nối), nên cấu hình sẽ khác. Ví dụ khi provider yêu cầu cổng 465:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.ssl.enable: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Không dùng nhầm implicit TLS trên cổng server đang chờ banner SMTP rõ văn bản, hoặc ngược lại. Phải theo tài liệu của server thực tế; có thể bổ sung timeout chung như cấu hình trước.

### Khi production có nhiều pod/instance

Nếu ứng dụng chạy nhiều instance, **mỗi instance có JavaMailSender bean của riêng nó**. Bean singleton chỉ dùng lại trong cùng application context, không tạo một sender dùng chung toàn cluster. Toàn hệ thống cần kiểm soát:

- Hạn mức và số kết nối SMTP trên **tổng các instance**, không chỉ một pod.
- Retry khi gặp lỗi mạng hoặc SMTP 4xx, với backoff và giới hạn số lần.
- Trạng thái không chắc chắn khi timeout xảy ra lúc server có thể đã chấp nhận thư.
- Queue/outbox bền vững cho thông báo nghiệp vụ quan trọng.
- Metrics và log có request/message ID, không ghi password, access token hay nội dung nhạy cảm.

**JavaMailSender.send() thành công** trong mô hình SMTP submission cho biết bước gửi tới server đã được transport xử lý thành công; thông thường đây là server đã chấp nhận thư. Các trạng thái phát cuối cùng cần theo dõi qua log MTA, DSN/bounce hoặc event của nhà cung cấp, nếu có.

### Có nên kiểm tra kết nối khi ứng dụng khởi động?

Spring Boot có thuộc tính **spring.mail.test-connection** để thử kết nối sender tại startup trong điều kiện cấu hình tương ứng. Có thể bật ở môi trường mà việc kết nối mail là điều kiện bắt buộc để ứng dụng sẵn sàng, nhưng cần cân nhắc: SMTP provider tạm thời không sẵn sàng có thể khiến ứng dụng **không khởi động thành công**, dù các API nghiệp vụ khác vẫn sử dụng được.

Chọn chiến lược readiness theo yêu cầu nghiệp vụ. Có hệ thống xem mail là phụ trợ và chấp nhận xử lý bằng outbox khi SMTP ngắt; có hệ thống phải dừng tiếp nhận thao tác phụ thuộc mail nếu không có đường gửi. Startup test chỉ xác minh **kết nối ở thời điểm thử**, không xác nhận delivery dài hạn hoặc mọi quyền gửi.

## 9. Áp dụng rào chắn recipient ở mức ứng dụng

Profile và biến cấu hình không đủ để tạo chính sách an toàn nếu code luôn gọi **JavaMailSender.send()** mà không kiểm tra. Có thể đặt một lớp trung gian (**MailGateway** hoặc service gửi email) để quyết định được gửi thật, gửi vào sink hay từ chối theo cấu hình.

Ví dụ sử dụng custom configuration properties:

~~~java
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailPolicy(
        DeliveryMode deliveryMode,
        Set<String> allowedRecipientDomains) {

    public enum DeliveryMode {
        DISABLED, CAPTURE, SANDBOX, LIVE
    }
}
~~~

Đăng ký binding cho properties class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MailPolicy.class)
public class MailPolicyConfiguration {
}
~~~

**MailPolicy** và các tên enum là ví dụ do ứng dụng định nghĩa. Spring Boot không tự hiểu CAPTURE/SANDBOX; code gửi phải thực thi quy tắc, đồng thời cấu hình host SMTP phù hợp với mode.

Một phương thức kiểm tra chính sách đơn giản:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.util.Locale;

public final class RecipientPolicy {
    private RecipientPolicy() {
    }

    public static void requireAllowed(
            String email,
            MailPolicy policy) {
        if (policy.deliveryMode() == MailPolicy.DeliveryMode.DISABLED) {
            throw new IllegalStateException("Mail delivery is disabled");
        }

        if (policy.deliveryMode() == MailPolicy.DeliveryMode.LIVE) {
            return; // Các chính sách production khác vẫn phải áp dụng.
        }

        if (policy.deliveryMode() == MailPolicy.DeliveryMode.SANDBOX) {
            String domain = domainOf(email);
            boolean permitted = policy.allowedRecipientDomains() != null
                    && policy.allowedRecipientDomains().stream()
                        .map(d -> d.toLowerCase(Locale.ROOT))
                        .anyMatch(domain::equals);
            if (!permitted) {
                throw new IllegalArgumentException(
                        "Recipient not allowed in sandbox");
            }
        }

        // CAPTURE dùng SMTP sink đã cấu hình riêng,
        // tuyệt đối không trỏ nhầm CAPTURE đến production.
    }

    private static String domainOf(String email) {
        try {
            InternetAddress address = new InternetAddress(email, true);
            address.validate();
            String mailbox = address.getAddress();
            int at = mailbox.lastIndexOf('@');
            if (at < 1 || at == mailbox.length() - 1) {
                throw new IllegalArgumentException(
                        "Invalid recipient address");
            }
            return mailbox.substring(at + 1)
                    .toLowerCase(Locale.ROOT);
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid recipient address", ex);
        }
    }
}
~~~

Gọi **requireAllowed** trước khi tạo hoặc gửi thư cho **mọi người nhận** ở To, Cc và Bcc. Ví dụ code chỉ kiểm tra một mailbox tại một thời điểm; với một MIME message có nhiều recipient, lớp gửi phải trích xuất và kiểm tra toàn bộ recipient, kể cả những người nhận được thêm từ quy tắc nghiệp vụ. Ở production, việc LIVE cho phép đi qua check môi trường **không loại bỏ** validation, quyền gửi hay kiểm soát lạm dụng.

**Đây là lớp guard bổ sung, không phải bằng chứng cách ly hoàn chỉnh.** Nên dùng các SMTP credential có quyền hạn riêng, policy hạn chế tại nhà cung cấp và network egress rule khi có thể. Nếu kẻ lỗi cấu hình trỏ CAPTURE vào production, một check domain ở SANDBOX không đủ để phát hiện; cần kiểm tra cả host/port/account được phép theo môi trường hoặc áp dụng policy ở gateway/hạ tầng.

## 10. Bảo vệ secret và cấu hình từ hệ thống triển khai

Credential SMTP nên đến từ **secret manager, biến môi trường có kiểm soát hoặc cơ chế được tổ chức phê duyệt**, không commit password vào application.yml hoặc tài liệu ví dụ. Hệ thống triển khai có thể inject biến **SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD** cho profile production và bộ tên riêng cho staging.

Ví dụ tham số được truyền khi chạy:

~~~bash
java -jar application.jar --spring.profiles.active=prod
~~~

Nếu biến môi trường không được cấp hoặc tên placeholder không đúng, cấu hình cần báo lỗi rõ ràng. **Không lưu giá trị secret thật trong shell history, log khởi động hoặc lệnh CLI có tham số chứa password.** Trong nhiều nền tảng, secret có thể được mount thành file hoặc inject dưới dạng environment; cách chọn phụ thuộc threat model và hạ tầng.

### Tránh trùng tên hoặc ghi đè cấu hình không mong muốn

Ví dụ Spring Boot có thể đọc **SPRING_MAIL_HOST** như một property được bind đến **spring.mail.host**. Nếu hệ thống vừa có **${SMTP_HOST}** trong YAML vừa có **SPRING_MAIL_HOST** từ môi trường cũ, giá trị cấu hình thực tế có thể không như người viết YAML dự đoán do ưu tiên các property source.

Vì vậy:

- Dùng **một quy ước rõ ràng** về tên biến và nguồn secret cho mỗi môi trường.
- Không tái sử dụng secret production trong staging.
- Nếu cần kiểm tra cấu hình hiệu lực, log **profile, loại transport và tên host đã được cho phép công khai**, tránh in username/password hoặc token.
- Đặt chính sách có thể từ chối startup khi active profile, SMTP endpoint và delivery mode không tương thích.
- Kiểm soát quyền đọc secret của runtime; hạn chế quyền gửi của tài khoản SMTP đến mức cần thiết.

Việc SMTP server trả **235 Authentication successful** chỉ chứng minh đã xác thực client ở thời điểm đó. Người dùng vẫn có thể không nhận email nếu địa chỉ From không được phép, queue lỗi, hạn mức bị vượt hoặc server đích từ chối thư.
## 11. Tách MailGateway khỏi business logic khi cần đổi cách gửi

Ở ứng dụng nhỏ, service có thể inject trực tiếp **JavaMailSender** và dùng mock trong test. Khi hệ thống có nhiều cách xử lý email, nên cân nhắc một interface dành riêng cho nghiệp vụ, ví dụ **MailGateway**. Business service tạo yêu cầu gửi; gateway quyết định thực hiện bằng SMTP, capture hoặc fake theo môi trường.

~~~java
public record OutboundMail(
        String recipient,
        String subject,
        String body) {
}

public interface MailGateway {
    void send(OutboundMail mail);
}
~~~

Implementation SMTP:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
@Profile({"local", "staging", "prod"})
public class SmtpMailGateway implements MailGateway {
    private final JavaMailSender sender;
    private final MailPolicy policy;

    public SmtpMailGateway(JavaMailSender sender, MailPolicy policy) {
        this.sender = sender;
        this.policy = policy;
    }

    @Override
    public void send(OutboundMail mail) {
        RecipientPolicy.requireAllowed(mail.recipient(), policy);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(mail.recipient());
        message.setSubject(mail.subject());
        message.setText(mail.body());
        sender.send(message);
    }
}
~~~

**@Profile** là annotation do Spring cung cấp để quyết định bean được đăng ký trong application context khi profile tương ứng active. Ở đây SmtpMailGateway tồn tại khi local, staging hoặc prod được kích hoạt. Trong **local** gateway vẫn gọi SMTP nhưng endpoint trỏ đến sink. Ở **staging**, RecipientPolicy sẽ kiểm tra allowlist. Trong **prod**, mode LIVE cho phép đi tiếp theo các quy tắc gửi thật.

Ở **test**, có thể dùng một **recording fake** để lưu các yêu cầu gửi trong bộ nhớ và kiểm tra kết quả:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
public class RecordingMailGateway implements MailGateway {
    private final List<OutboundMail> captured = new ArrayList<>();

    @Override
    public synchronized void send(OutboundMail mail) {
        captured.add(mail);
    }

    public synchronized List<OutboundMail> snapshot() {
        return List.copyOf(captured);
    }

    public synchronized void clear() {
        captured.clear();
    }
}
~~~

Đây là **fake tối giản** để minh họa ý tưởng. Khi dùng trong test chạy song song hoặc một Spring context được tái sử dụng giữa test case, phải **reset dữ liệu test đúng thời điểm**, giới hạn scope của bean hoặc tạo fake riêng từng test. Không nên đưa một fake lưu dữ liệu của người dùng thật vào production. Chỉ áp dụng kiểu wiring này khi ứng dụng chủ động chọn MailGateway như ranh giới gửi thư; nó không phải khả năng tự động của JavaMailSender.

### Tránh profile chồng lấp tạo hai gateway

Nếu vô tình bật cùng lúc **test** và **prod**, cả RecordingMailGateway lẫn SmtpMailGateway có thể được đăng ký, gây lỗi bean không duy nhất hoặc dẫn đến chọn implementation sai nếu có @Primary hay @Qualifier. Vì vậy cần xác nhận profile môi trường là **độc quyền** và từ chối cấu hình không nhất quán ngay từ startup.

Không nên viết chính sách kiểu **@Profile("!prod")** cho mọi fake rồi mặc định rằng mọi hệ thống không phải prod luôn an toàn: khi profile chưa được khai báo hoặc có nhiều profile cùng kích hoạt, điều kiện phủ định có thể rộng hơn dự kiến.

## 12. Kiểm tra cấu hình môi trường trước khi phát thư

Một ứng dụng có thể khởi động được dù các thuộc tính SMTP đang trỏ nhầm môi trường. Vì vậy, cần thiết kế **kiểm tra tính nhất quán** trước khi chấp nhận request gửi mail:

| Điều kiện | Ví dụ kiểm tra | Hành vi phù hợp |
|---|---|---|
| Không có profile môi trường | Không kích hoạt local/test/staging/prod | Từ chối hoạt động gửi hoặc fail startup theo chính sách |
| Có nhiều profile môi trường | local + prod cùng active | Dừng startup để tránh cấu hình pha trộn |
| Local dùng host production | delivery-mode CAPTURE nhưng host SMTP thật | Từ chối gửi/khởi động, báo cấu hình không phù hợp |
| Test có đường gửi SMTP thật | Không có mock/gateway fake mà còn credential prod | Từ chối hoặc ngắt đường gửi mạng |
| Staging dùng secret prod | Endpoint, account hoặc secret không thuộc staging | Dừng triển khai/khởi động theo cơ chế kiểm soát |
| Staging nhận recipient ngoài allowlist | email khách hàng thật | Từ chối trước khi gọi JavaMailSender |
| Prod thiếu SMTP host/secret | Placeholder không được giải quyết hoặc credential rỗng | Báo lỗi cấu hình, không fallback sang staging |
| Prod không bật TLS theo policy | STARTTLS không bắt buộc với tài khoản/password | Dừng hoặc từ chối cấu hình không an toàn |

Để phát hiện sai profile ngay khi khởi động, có thể kiểm tra **Environment.getActiveProfiles()** cùng các thuộc tính của MailPolicy bằng một component khởi tạo. Ví dụ minh họa phần xác nhận chính sách:

~~~java
import jakarta.annotation.PostConstruct;
import java.util.Arrays;
import java.util.Set;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class MailEnvironmentGuard {
    private static final Set<String> ENVIRONMENTS =
            Set.of("local", "test", "staging", "prod");

    private final Environment environment;
    private final MailPolicy policy;

    public MailEnvironmentGuard(
            Environment environment,
            MailPolicy policy) {
        this.environment = environment;
        this.policy = policy;
    }

    @PostConstruct
    void verify() {
        long selected = Arrays.stream(environment.getActiveProfiles())
                .filter(ENVIRONMENTS::contains)
                .count();

        if (selected != 1) {
            throw new IllegalStateException(
                    "Exactly one mail environment profile is required");
        }

        boolean prod = Arrays.asList(environment.getActiveProfiles())
                .contains("prod");
        if (prod && policy.deliveryMode() != MailPolicy.DeliveryMode.LIVE) {
            throw new IllegalStateException(
                    "Production requires LIVE mail policy");
        }
    }
}
~~~

Ví dụ kiểm tra hai điều kiện cơ bản; một hệ thống thực tế cần xác minh thêm **mode chính xác theo từng profile, host được phép, TLS và các tham số bảo mật**. Nếu có nhiều profile nghiệp vụ khác thì không cần từ chối chúng; chỉ đếm bốn profile môi trường được định nghĩa là loại trừ nhau.

Việc kiểm tra này phụ thuộc vào **MailPolicy** được đăng ký qua @EnableConfigurationProperties như ví dụ trước. Nếu ứng dụng dùng profile mặc định **default** để phát triển, cần chỉnh lại chính sách về profile bắt buộc cho phù hợp. Không nên thêm guard quá nghiêm ngặt vào ứng dụng đang có nhiều môi trường mà chưa thiết kế cách chọn profile chính thức.

## 13. Quy trình chạy thử từ local đến production

Một đường đi thường dùng:

~~~text
LOCAL
  Build email nội dung đúng
  SMTP sink nhận được
  Developer xem HTML/attachment
       |
       v
TEST / CI
  Business rule và MailGateway được test bằng mock/fake
  SMTP integration test dùng test server riêng
  Không truy cập credential/provider thật
       |
       v
STAGING
  Cấu hình deployment và secret staging
  TLS/AUTH, MIME, giới hạn kích thước, provider events
  Chỉ gửi recipient được allowlist / sandbox
       |
       v
PRODUCTION
  Hệ thống triển khai chọn prod rõ ràng
  Secret production, TLS, monitoring và alert
  Gửi người nhận thật theo business policy
~~~

### Ở local

Khởi động SMTP sink, sau đó chạy ứng dụng với profile local. Tạo một yêu cầu gửi từ UI hoặc API và kiểm tra message xuất hiện trong giao diện sink. Nên thử cả plain text, HTML, Unicode, attachment và trường hợp người nhận không hợp lệ.

### Ở CI

Kích hoạt **test** bằng @ActiveProfiles hoặc cấu hình của test runner. Kiểm tra rằng mock/fake nhận đúng dữ liệu và không có đường gửi ra SMTP production. Nếu cần test giao thức, dùng SMTP server tạm thời với port độc lập và bộ dữ liệu nhỏ, được teardown sau test.

### Ở staging

Dùng **secret staging** và SMTP sandbox riêng. Thử qua đúng network path mà runtime sử dụng, kiểm tra khả năng đàm phán TLS, AUTH và các chính sách người nhận. Có thể thử một địa chỉ đích đã được cấp phép; không dùng danh sách khách hàng thật.

### Ở production

Áp dụng cấu hình production qua hệ thống deploy, kiểm tra secret đã được cấp đúng phạm vi và trạng thái SMTP provider. Khi cần smoke test, dùng tài khoản nhận thử đã được phê duyệt và một email có nội dung rõ là test vận hành. Theo dõi submission và event phát thư, tránh gửi tràn lan chỉ để kiểm tra “có hoạt động không”.

## 14. Xử lý lỗi khác nhau theo môi trường

| Tình huống | Local | Test | Staging | Production |
|---|---|---|---|---|
| Không kết nối SMTP | Kiểm tra sink/port/network | Nếu mock, không nên phụ thuộc SMTP; integration test xem server | Kiểm tra provider staging, TLS/firewall | Theo dõi incident, queue và retry có kiểm soát |
| Lỗi SMTP AUTH | Sink thường không cần AUTH | Không dùng credential thật | Kiểm tra secret staging/scope/quyền | Kiểm tra rotation, account policy, secret và alert |
| Nội dung/MIME sai | Xem mail trong sink | Assertion trên message/serialized MIME | Test end-to-end với sandbox | Sửa template theo quy trình phát hành |
| Gửi nhầm người nhận | Dữ liệu giả vẫn cần kiểm soát | Fixture phải độc lập và không có đường gửi thật | Guard/allowlist phải từ chối | Quy tắc nghiệp vụ và phân quyền người nhận |
| Provider tạm thời không sẵn sàng | Có thể restart sink | Test mock không phụ thuộc | Đối soát sự kiện và retry | Queue/outbox, timeout, backoff, alert |
| Không thấy thư trong Inbox | Kiểm tra sink, không có Inbox thật | Không phải mục tiêu unit test | Kiểm tra định nghĩa sandbox/provider event | Phân biệt SMTP accepted, relay, bounce, mailbox và bộ lọc |

Một số lỗi có thể **không xác định được chắc chắn đã gửi hay chưa**, chẳng hạn kết nối mất đúng lúc SMTP server đã tiếp nhận toàn bộ nội dung nhưng phản hồi thành công chưa đến client. Khi đó retry có thể tạo email trùng. Cần giữ trạng thái submission uncertain và có cơ chế đối soát theo khả năng của provider, đặc biệt với thông báo quan trọng.

### Log cần đủ thông tin nhưng không làm lộ dữ liệu

Có thể ghi:

~~~text
environment=staging
mailMode=SANDBOX
smtpEndpointClass=staging-provider
mailRequestId=mail-2048
recipientCount=1
event=SMTP_SUBMISSION_ACCEPTED
~~~

Không ghi:

~~~text
smtpPassword=...
oauthAccessToken=...
fullMimeBody=...
authorizationHeader=...
~~~

Tên provider, host hoặc username cũng có thể là thông tin nội bộ nhạy cảm tùy môi trường; chỉ log mức đủ dùng cho vận hành và tuân thủ chính sách của tổ chức.

## 15. Câu hỏi thường gặp

**Có cần bốn JavaMailSender bean trong cùng một ứng dụng không?** Thường không. Nếu mỗi lần chạy ứng dụng chỉ có **một profile môi trường**, một JavaMailSender bean dùng cấu hình của môi trường đó là đủ. Khi cần nhiều tài khoản SMTP cùng lúc trong một instance, có thể cấu hình nhiều bean với @Qualifier hoặc dùng một abstraction định tuyến.

**Đặt spring.mail.host trong application.yml rồi ghi đè ở từng profile có được không?** Về mặt kỹ thuật có, nhưng nếu host cơ sở là production thì thiếu hoặc quên chọn profile có thể dẫn đến gửi nhầm. Với cấu hình nhạy cảm, giữ base không có host thật hoặc đặt một phương án mặc định không phát thư thường an toàn hơn.

**application-test.yml có tự động khiến test không gửi mail không?** Không. File đó chỉ cung cấp thuộc tính khi profile test active. Phải mock/fake JavaMailSender, cấu hình SMTP test server hoặc chọn MailGateway tương ứng.

**@ActiveProfiles("test") có chặn network không?** Không. Nó chỉ kích hoạt profile test cho Spring test context; nếu code hoặc test vẫn trực tiếp mở network đến provider thật thì profile không ngăn được. Cần thiết kế đường gửi an toàn và test isolation.

**Tại sao local không bật STARTTLS nhưng staging/prod lại bật?** SMTP sink local chạy trên loopback có thể được thiết kế chỉ để capture và không hỗ trợ TLS/AUTH; staging/prod giao tiếp với provider qua network nên cần bảo vệ credential và dữ liệu. Khi môi trường local dùng SMTP remote, phải áp dụng TLS theo yêu cầu của remote server.

**Bật TLS và AUTH có chắc email được phát thành công không?** Không. TLS bảo vệ kết nối; AUTH chứng minh client được phép đăng nhập; sau đó SMTP server còn kiểm tra sender/recipient policy, quota, kích thước và các hop phát thư tiếp theo.

**Có nên dùng một tài khoản SMTP cho staging và production để đỡ cấu hình?** Không nên. Việc tách credential giúp giảm tác động khi staging bị lộ secret hoặc bị gửi nhầm, đồng thời cho phép cấp quyền và quota riêng.

**Có nên để test tự gửi email thật đến hộp thư của developer?** Chỉ với bài test tích hợp hoặc smoke test được thiết kế rõ, đã kiểm soát recipient và hạ tầng. Unit test và CI mặc định nên dùng fake/mock hoặc SMTP sink.

## 16. Nguyên tắc thiết kế cấu hình sender theo môi trường

Mỗi môi trường cần trả lời rõ ba câu hỏi: **JavaMailSender sẽ kết nối đến đâu? Ai được phép nhận thư? Khi gửi thất bại thì hệ thống biết và xử lý thế nào?**

| Profile | Đích gửi mong muốn | Rào chắn quan trọng |
|---|---|---|
| **local** | SMTP sink để developer xem thư | Không kết nối nhầm provider thật |
| **test** | Mock, recording fake hoặc SMTP test server | Không dùng secret/địa chỉ nhận thật; test lặp lại được |
| **staging** | SMTP sandbox/relay staging | Credential riêng, TLS, recipient allowlist và policy provider |
| **prod** | SMTP provider thật | Secret production, TLS, quyền gửi, retry/queue và monitoring |

Với **Spring Framework Mail**, cách triển khai thường là **cùng code nghiệp vụ và JavaMailSender API**, nhưng tách cấu hình bằng **application-{profile}.yml**, biến môi trường/secret và các bean hoặc policy phù hợp. Nên kiểm tra profile được chọn ở startup, cấm cấu hình pha trộn, xác minh đường gửi trong local/test/staging rồi mới sử dụng production. Khi đánh giá kết quả, luôn phân biệt **SMTP submission đã chấp nhận email** với **email được phát tới mailbox của người nhận**.
