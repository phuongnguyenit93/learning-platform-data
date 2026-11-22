# Chạy SMTP server kiểm thử và đọc lại MIME

Trong **Spring Framework Mail**, việc gọi **JavaMailSender.send(...)** mà không có exception chưa đủ để biết email được tạo ra đúng. Một email có thể bị lỗi font tiếng Việt, thiếu phần text/plain, HTML không đúng, attachment rỗng, Content-ID không khớp hoặc MIME multipart lồng sai. Dùng SMTP production để thử đi thử lại còn có nguy cơ gửi nhầm đến người dùng thật, tiêu tốn quota và làm bài kiểm thử phụ thuộc Internet.

Bài thực hành này xây dựng một **SMTP capture environment**: ứng dụng Spring Boot gửi email vào server SMTP kiểm thử, server giữ message lại, rồi chúng ta đọc **raw MIME** để kiểm tra cấu trúc và nội dung thực sự được gửi.

Bạn sẽ hoàn thành các bước:

1. Chạy **Mailpit** bằng Docker Compose, nhận SMTP trên port 1025 và mở giao diện kiểm thử trên port 8025.
2. Cấu hình Spring Boot **JavaMailSender** trỏ tới SMTP local, không dùng credentials thật.
3. Tạo **MimeMessage** có text/plain, text/html, UTF-8 tiếng Việt và attachment CSV.
4. Gửi thử qua một endpoint chỉ tồn tại trong local profile.
5. Mở UI Mailpit, xem MIME headers, tải file **.eml** và nhận diện multipart structure.
6. Viết code **Jakarta Mail** để parse .eml và duyệt các nested parts.
7. Viết **JUnit integration test với GreenMail**, gửi qua SMTP thật trong JVM rồi đọc lại MimeMessage mà không kết nối Internet.
8. Thử các lỗi phổ biến về host, port, TLS, charset, attachment, content-disposition và HTML.
9. Hiểu giới hạn: capture server nhận SMTP không có nghĩa email đã được chuyển phát tới inbox.

Đây là một bài thuộc chương **Dự án thực hành** của **Spring Framework Mail**. Tất cả địa chỉ email ví dụ dùng miền **example.invalid** để nhấn mạnh chúng chỉ phục vụ test, không phải người nhận thật.

---

## 1. Kiến trúc lab

~~~text
Terminal / Browser
       |
       | POST /__dev/mail/send
       v
Spring Boot application
       |
       v
JavaMailSender
       |
       | SMTP 127.0.0.1:1025
       v
Mailpit capture server
       |
       +--> Store message
       |
       +--> Web UI 127.0.0.1:8025
                    |
                    +--> HTML/plain preview
                    +--> MIME headers
                    +--> Attachment list
                    +--> Download .eml
                                |
                                v
                         Jakarta Mail reader
~~~

Ở đây có hai luồng độc lập:

- **Gửi:** JavaMailSender thực hiện SMTP submission vào Mailpit.
- **Đọc lại:** người học mở UI hoặc parse file .eml do Mailpit giữ lại.

SMTP là giao thức **gửi/submit** mail; không phải giao thức đọc hộp thư. Khi đọc lại nội dung Mailpit, ta sử dụng khả năng capture/UI/API của server test, không cần đăng nhập IMAP/POP3 của một tài khoản email thật.

### 1.1. Kết quả mong đợi

Một lần gọi endpoint tạo một email trong Mailpit với:

- From: demo-sender@example.invalid.
- To: student@example.invalid.
- Subject có dấu tiếng Việt.
- Plain-text body và HTML body.
- Attachment tên ket-qua.csv.
- MIME headers và boundaries được Jakarta Mail tạo.
- Có thể parse .eml và đọc lại nội dung decoded chính xác.

### 1.2. Điều lab không chứng minh

Mailpit không mặc định chuyển thư ra Internet. Bài này không kiểm tra Gmail inbox placement, Outlook rendering, production TLS/AUTH, SPF/DKIM/DMARC hoặc việc người nhận đã đọc thư.

## 2. SMTP capture server là gì?

Một SMTP capture server nhận các lệnh SMTP cơ bản và lưu message để developer kiểm tra:

~~~text
SMTP client                   Capture server
     |--- TCP connect ------------>|
     |<-- 220 greeting ------------|
     |--- EHLO ------------------->|
     |<-- 250 capabilities --------|
     |--- MAIL FROM ------------->|
     |<-- 250 ---------------------|
     |--- RCPT TO --------------->|
     |<-- 250 ---------------------|
     |--- DATA ------------------>|
     |<-- 354 ---------------------|
     |--- MIME body + final dot ->|
     |<-- 250 accepted -----------|
     |--- QUIT ------------------>|
~~~

Khi capture server trả **250 accepted**, ứng dụng biết test SMTP server đã nhận submission. Nó **không** nói email đã đến hộp thư người nhận ngoài Internet.

### 2.1. Vì sao tránh SMTP production?

- Tránh gửi nhầm email cá nhân hóa đến khách hàng.
- Không cần giữ credentials thật trong máy/CI.
- Không phụ thuộc rate limit và network provider.
- Dễ chạy lặp lại test.
- Đọc được MIME source và attachments.
- Không phụ thuộc spam filtering hoặc bounce delay.

### 2.2. Capture khác deliver

Một ứng dụng production có thể gửi email thành công tới relay rồi nhận bounce sau đó. Capture test chỉ kiểm tra phần **application → test SMTP server**.

## 3. Mailpit và GreenMail khác nhau thế nào?

| Công cụ | Vai trò | Thích hợp |
| --- | --- | --- |
| **Mailpit** | SMTP capture, web UI, API | Thao tác thủ công và xem raw MIME |
| **GreenMail** | Embedded mail servers bằng Java | JUnit SMTP integration tests |
| **smtp4dev** | Một lựa chọn SMTP capture có UI | Nhóm quen dùng công cụ này |
| **MailHog** | SMTP capture truyền thống | Dự án cũ đã dùng |
| **Provider sandbox** | Hành vi riêng của nhà cung cấp | AUTH/TLS/API/deliverability contract |

Trong bài này dùng Mailpit cho phần quan sát và GreenMail cho test tự động. Không cần chạy cả hai cùng lúc.

### 3.1. Phiên bản Jakarta Mail

Ví dụ hướng tới **Spring Boot 3 / Spring Framework 6**, nơi API mail thường dùng **jakarta.mail**. Các dự án Spring cũ dùng **javax.mail** cần chọn dependencies, imports và GreenMail artifact phù hợp; không trộn hai namespace trong cùng một test.

## 4. Yêu cầu môi trường

Cần có:

- Java 17 trở lên cho Spring Boot 3.
- Docker Engine và Docker Compose để chạy Mailpit.
- Gradle hoặc Maven.
- IDE, terminal và trình duyệt.
- Port 1025/8025 chưa bị chiếm.
- Một thư mục lưu file .eml giả lập.

Kiểm tra:

~~~bash
java -version
docker version
docker compose version
~~~

Nếu không có Docker, có thể thực hiện phần tự động với GreenMail embedded, nhưng UI Mailpit cần chạy server tương ứng.

## 5. Tạo compose.yaml cho Mailpit

Trong thư mục dự án lab, tạo:

~~~yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    container_name: mailpit-local
    restart: unless-stopped
    ports:
      - "127.0.0.1:1025:1025"
      - "127.0.0.1:8025:8025"
~~~

**latest** được dùng cho ví dụ học tập ngắn gọn. Trong CI hoặc dự án nhóm, nên pin một tag/digest đã kiểm chứng để kết quả tái lập tốt hơn.

### 5.1. Ý nghĩa của port

- **1025/TCP:** nơi JavaMailSender gửi SMTP.
- **8025/TCP:** nơi trình duyệt mở Mailpit UI và ứng dụng test có thể truy vấn HTTP API.

Không nhầm HTTP UI với SMTP listener.

### 5.2. Vì sao bind 127.0.0.1?

Cấu hình Docker chỉ expose ports trên loopback host, giảm nguy cơ máy khác truy cập được test server. Đây không phải hệ thống có authentication dành cho Internet.

### 5.3. Storage

Cấu hình tối giản chưa gắn persistent volume. Dữ liệu captured messages chỉ phục vụ lab và không được xem là durable business storage. Nếu nhóm cần giữ lịch sử test, phải thiết kế retention, access control và storage phù hợp.

## 6. Khởi động Mailpit

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 mailpit
~~~

Mở URL:

~~~text
http://127.0.0.1:8025
~~~

UI trống khi chưa gửi email là trạng thái bình thường.

### 6.1. Nếu port bị chiếm

Docker có thể báo lỗi khi host port 1025 hoặc 8025 đang được một process khác dùng. Có thể thay host port trong compose, nhưng phải thay Spring Mail port tương ứng.

### 6.2. Đóng môi trường sau thực hành

~~~bash
docker compose down
~~~

Không dùng lệnh dọn container/volume ngoài phạm vi lab.

## 7. Cấu trúc project Spring Boot

~~~text
mail-mime-lab/
  compose.yaml
  build.gradle
  src/
    main/
      java/
        com/example/maildemo/
          MailMimeLabApplication.java
          MailDemoSender.java
          LocalMailDemoController.java
          MimeReader.java
          MimeTreePrinter.java
      resources/
        application-local.yml
    test/
      java/
        com/example/maildemo/
          MimeRoundTripTest.java
          MimePartFinder.java
~~~

Đây là cấu trúc để **người học tự tạo khi thực hành**, không phải danh sách file worker hiện tại được phép viết trong STEP 4.

### 7.1. Dependency Gradle

Trong một project có Spring Boot plugin và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Mail starter đưa **JavaMailSender** và Jakarta Mail dependencies vào classpath theo phiên bản tương thích được Spring Boot quản lý.

### 7.2. Maven

Dùng các starter artifacts tương ứng trong pom.xml nếu dự án dùng Maven. Ví dụ nội dung Java không phụ thuộc vào build tool cụ thể.

## 8. Cấu hình SMTP local

Tạo **src/main/resources/application-local.yml**:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

### 8.1. Không cần SMTP username/password trong lab

Mailpit demo mặc định chấp nhận local SMTP không AUTH theo cấu hình này. Không chèn credentials thật vào application-local.yml.

### 8.2. Không bật STARTTLS bắt buộc khi server không hỗ trợ

Nếu bật **mail.smtp.starttls.required=true** nhưng test SMTP server không cung cấp STARTTLS, client sẽ thất bại khi gửi. Đó là sự không khớp cấu hình, không phải lỗi MIME.

### 8.3. Không copy sang production

Production SMTP cần TLS, xác minh certificate/hostname, AUTH và secret management đúng với nhà cung cấp. Plaintext SMTP ở đây chỉ dùng trên loopback hoặc mạng test cô lập.

### 8.4. Nếu Spring Boot chạy trong container

**127.0.0.1** bên trong app container là chính container đó. Khi app và Mailpit ở cùng Docker Compose network, có thể cấu hình **host: mailpit** và **port: 1025** thay vì loopback host.

## 9. Spring Boot application

~~~java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailMimeLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailMimeLabApplication.class,
                args
        );
    }
}
~~~

Ví dụ không gửi mail tự động khi startup vì hot reload, app restart hoặc test lifecycle có thể vô tình gửi nhiều thư. Ta sẽ tạo một local-only endpoint để kích hoạt đúng một lần theo yêu cầu.

## 10. Tạo MimeMessage có text, HTML và attachment

Tạo **MailDemoSender.java**:

~~~java
package com.example.maildemo;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailDemoSender {

    private final JavaMailSender mailSender;

    public MailDemoSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendSample() {
        MimeMessage message =
                mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                            StandardCharsets.UTF_8.name()
                    );

            helper.setFrom("demo-sender@example.invalid");
            helper.setTo("student@example.invalid");
            helper.setSubject(
                    "Bài thực hành MIME: tiếng Việt và tệp đính kèm"
            );

            String plain =
                    "Xin chào!\n"
                  + "Đây là nội dung text/plain.\n"
                  + "Mã ví dụ: LAB-475.\n";

            String html =
                    "<html><body>"
                  + "<h1>Xin chào!</h1>"
                  + "<p>Đây là phần <strong>text/html</strong>.</p>"
                  + "<p>Mã ví dụ: LAB-475.</p>"
                  + "</body></html>";

            helper.setText(plain, html);

            byte[] csv =
                    ("id,status\n"
                   + "LAB-475,READY\n")
                    .getBytes(StandardCharsets.UTF_8);

            helper.addAttachment(
                    "ket-qua.csv",
                    new ByteArrayResource(csv),
                    "text/csv"
            );

        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare demo MIME",
                    ex
            );
        }

        mailSender.send(message);
    }
}
~~~

### 10.1. MimeMessage khác SimpleMailMessage

**SimpleMailMessage** tiện cho email text thuần. **MimeMessage** hỗ trợ HTML, multipart/alternative, attachments, inline resources và MIME headers linh hoạt.

### 10.2. MULTIPART_MODE_MIXED_RELATED

Chế độ này cho phép sắp xếp các body parts cùng attachments/tài nguyên liên quan. Cấu trúc lồng nhau thực tế có thể chứa multipart/mixed, multipart/related và multipart/alternative; không giả định mọi part nằm ở root.

### 10.3. setText(plain, html)

Đây là hai **biểu diễn thay thế của cùng nội dung**, không phải hai emails. Một số mail clients chọn HTML, một số có thể dùng plain text.

### 10.4. Charset UTF-8

Ví dụ dùng tiếng Việt có dấu để kiểm tra MIME encoding/decoding. Trong raw source, tiếng Việt có thể được mã hóa quoted-printable hoặc base64; điều quan trọng là decoded content đúng.

### 10.5. Attachment bytes

CSV được tạo bằng ByteArrayResource. Với file nhỏ, nó dễ kiểm tra và có thể cung cấp stream mới khi MIME serializer cần. Với file lớn cần cách xử lý bounded/streaming, không gom mọi attachment vào RAM.

## 11. Endpoint chỉ dành cho local profile

Tạo **LocalMailDemoController.java**:

~~~java
package com.example.maildemo;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("local")
@RestController
@RequestMapping("/__dev/mail")
public class LocalMailDemoController {

    private final MailDemoSender sender;

    public LocalMailDemoController(MailDemoSender sender) {
        this.sender = sender;
    }

    @PostMapping("/send")
    public ResponseEntity<String> send() {
        sender.sendSample();

        return ResponseEntity.ok(
                "SMTP_SUBMITTED_TO_LOCAL_CAPTURE_SERVER"
        );
    }
}
~~~

### 11.1. Vì sao endpoint không nhận To tùy ý?

Bài lab không nhằm xây HTTP open relay. Sender/recipient đều cố định vào miền giả để không tạo tính năng phát thư tùy ý.

### 11.2. Vì sao có @Profile("local")?

Giảm nguy cơ route test xuất hiện ngoài môi trường local. Tuy vậy, profile chỉ là điều kiện bean activation, không thay thế authentication/firewall nếu máy dùng chung.

### 11.3. Response có nghĩa gì?

Đoạn **SMTP_SUBMITTED_TO_LOCAL_CAPTURE_SERVER** chỉ nói JavaMailSender gửi thành công tới test SMTP capture server theo kết quả phía caller; không có bằng chứng inbox delivery.

## 12. Khởi động app và gọi thử

Với Gradle wrapper trên macOS/Linux:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Với Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

Gửi một request:

~~~bash
curl -X POST http://127.0.0.1:8080/__dev/mail/send
~~~

Với PowerShell nên dùng **curl.exe** để tránh alias:

~~~powershell
curl.exe -X POST http://127.0.0.1:8080/__dev/mail/send
~~~

Kết quả mong đợi:

~~~text
SMTP_SUBMITTED_TO_LOCAL_CAPTURE_SERVER
~~~

### 12.1. Nếu nhận HTTP 404

Kiểm tra profile local có đang active không và controller có thuộc package được Spring component scan hay không.

### 12.2. Nếu nhận HTTP 5xx

Kiểm tra exception và Spring Mail config; không mặc định mọi lỗi là do MIME. Có thể Mailpit chưa chạy, sai port, AUTH hoặc STARTTLS bị bật nhầm.

### 12.3. Không gửi nhiều lần ngoài ý muốn

Mỗi POST tạo một mail message trong server test. Nếu kiểm tra count, chỉ gọi một lần hoặc reset/khởi tạo lại test server.

## 13. Xem email trong Mailpit UI

Mở:

~~~text
http://127.0.0.1:8025
~~~

Chọn email với Subject:

~~~text
Bài thực hành MIME: tiếng Việt và tệp đính kèm
~~~

Quan sát:

1. From/To.
2. Subject Unicode.
3. Thời điểm capture.
4. Preview plain text.
5. Preview HTML.
6. Attachment ket-qua.csv.
7. Message headers.
8. Raw/source hoặc mục download message.
9. Kiểu Content-Type và các MIME parts nếu UI cung cấp.
10. Các thông tin envelope nếu capture server hiện hỗ trợ.

Tên tab/nút có thể thay đổi giữa các phiên bản Mailpit. Nếu UI cho phép **Download / Source / Raw**, hãy tải bản email dạng **.eml** để kiểm tra độc lập.

### 13.1. UI render có thể che lỗi

HTML nhìn đúng trên trình duyệt test không bảo đảm plain-text alternative, charset và nested multipart đúng. Đọc .eml là bước cần thiết.

### 13.2. Test UI không phải email client production

Outlook, Gmail và các mail clients có chính sách render/ảnh/link khác nhau. Mailpit giúp kiểm tra MIME và preview, không chứng minh tương thích tuyệt đối với mọi client.

## 14. MIME là gì?

MIME (Multipurpose Internet Mail Extensions) là cách biểu diễn nội dung email với headers và body parts. Một message có thể chứa:

- Header From/To/Subject.
- Header MIME-Version.
- Content-Type.
- Charset.
- Content-Transfer-Encoding.
- Nhiều phần body dưới multipart.
- File attachment.
- Inline image với Content-ID.
- Message lồng nhau dạng message/rfc822.

Một email HTML không phải chỉ là chuỗi HTML; nó có cấu trúc thông điệp giúp receiving system hiểu các loại part.

## 15. Xem raw .eml

Ví dụ **định hướng cấu trúc**, không phải literal output được bảo đảm của Jakarta Mail:

~~~text
From: demo-sender@example.invalid
To: student@example.invalid
Subject: =?UTF-8?B?...?=
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/related; boundary="related"

--related
Content-Type: multipart/alternative; boundary="alternatives"

--alternatives
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

... encoded text ...

--alternatives
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

... encoded HTML ...

--alternatives--
--related--
--outer
Content-Type: text/csv; name="ket-qua.csv"
Content-Disposition: attachment; filename="ket-qua.csv"
Content-Transfer-Encoding: base64

... encoded attachment bytes ...

--outer--
~~~

### 15.1. Boundary

Boundary là delimiter của multipart. Jakarta Mail có thể tạo giá trị khác mỗi lần gửi; không hardcode boundary khi viết test.

### 15.2. Raw Subject

Với Unicode, Subject có thể là một hoặc nhiều encoded-words. Jakarta Mail **MimeMessage.getSubject()** decode để trả về String nội dung.

### 15.3. Content-Transfer-Encoding

Base64 và quoted-printable là **encoding**, không phải encryption. Không dùng chúng như cơ chế bảo vệ bí mật.

### 15.4. Cấu trúc không cố định tuyệt đối

Multipart nesting và headers có thể khác theo Jakarta Mail implementation và cấu hình. Test nên dựa trên **semantics và decoded contents**.

## 16. Các MIME headers cần kiểm tra

| Header | Ý nghĩa | Khi test |
| --- | --- | --- |
| **From** | Danh tính hiển thị người gửi | Đúng sender identity |
| **To** | Người nhận hiển thị | Đúng test recipient |
| **Cc/Bcc** | Visible/hidden recipients | Không suy envelope chỉ từ raw |
| **Subject** | Tiêu đề | Unicode decode đúng |
| **Date** | Mốc message creation/sending | Không hardcode exact value |
| **Message-ID** | ID của message | Không dùng như dedup guarantee |
| **MIME-Version** | MIME version | Thường 1.0 |
| **Content-Type** | Loại nội dung part | multipart, text, image, file |
| **Content-Transfer-Encoding** | Wire representation | Base64/quoted-printable/7bit |
| **Content-Disposition** | Attachment hoặc inline | Phân biệt body/file |
| **Content-ID** | ID của inline resource | Khớp cid reference |
| **filename/name** | Metadata tên file | Kiểm tra Unicode/bytes |

### 16.1. Envelope khác headers

SMTP **MAIL FROM/RCPT TO** xác định envelope; MIME **From/To** là headers. Một message có thể có Bcc envelope recipient mà không hiển thị Bcc header trong raw .eml.

### 16.2. Message-ID không chống gửi trùng

Gửi hai emails có cùng Message-ID vẫn có thể tạo hai lần SMTP submission. Không dùng Message-ID thay transactional outbox/idempotency policy.

### 16.3. Raw headers có line folding

Một header dài có thể xuống nhiều physical lines. Đừng assert raw Subject là đúng một dòng; dùng API MIME parse.

## 17. Ba subtype multipart cần hiểu

**multipart/alternative**:

~~~text
multipart/alternative
    +-- text/plain
    +-- text/html
~~~

Là các phiên bản thay thế của cùng nội dung.

**multipart/related**:

~~~text
multipart/related
    +-- text/html with src="cid:brand-logo"
    +-- image/png; Content-ID: <brand-logo>
~~~

Là nội dung chính và tài nguyên liên quan được tham chiếu.

**multipart/mixed**:

~~~text
multipart/mixed
    +-- multipart/alternative or related
    +-- text/csv; attachment
    +-- application/pdf; attachment
~~~

Thường dùng khi có file attachments.

### 17.1. Cây MIME có thể lồng nhiều tầng

Không nên parse bằng cách lấy duy nhất root.getContent() rồi cast String. Root có thể là Multipart, con của nó cũng là Multipart.

### 17.2. Content-Disposition có thể null

Text body thường không có disposition. Việc thiếu disposition không đồng nghĩa part bị lỗi.

### 17.3. Text attachment không phải plain body

Một tệp **notes.txt** có Content-Type text/plain, nhưng vẫn là attachment. Parser cần xét filename/disposition trước khi coi part là email body.

## 18. Charset khác Content-Transfer-Encoding

Hai headers liên quan nhưng không đồng nghĩa:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

- **charset=UTF-8:** cách bytes trở thành text.
- **quoted-printable/base64:** cách dữ liệu được biểu diễn trên MIME transport.

Một raw .eml có thể chứa các sequences kiểu **=C3=...** hoặc chuỗi base64 thay vì chữ tiếng Việt rõ ràng. Điều đó không phải lỗi nếu Jakarta Mail decode ra đúng nội dung.

### 18.1. Không grep raw để xác nhận UTF-8

Hãy gọi **Part.getContent()** cho text parts và so sánh decoded String.

### 18.2. Lỗi mojibake

Nếu ứng dụng đã đọc dữ liệu đầu vào sai charset trước khi dựng MimeMessage, thêm charset=UTF-8 ở MIME layer không tự sửa văn bản đã hỏng.

### 18.3. Filename Unicode là bài test độc lập

Subject decode đúng không chứng minh attachment filename cũng đúng. Hãy test **getFileName()** riêng nếu dùng tên file có dấu.

## 19. Tải file .eml

Trong message detail trên Mailpit, tìm mục **Raw / Source / Download** hoặc tên tương đương rồi lưu file:

~~~text
sample-message.eml
~~~

Một số phiên bản Mailpit cũng cung cấp HTTP API để liệt kê và lấy raw message; ví dụ routes thường gặp:

~~~text
GET /api/v1/messages
GET /api/v1/message/{ID}/raw
~~~

Khi tự động hóa API, cần kiểm tra đúng contract của **phiên bản đã pin**, vì response fields/routes có thể đổi. Workflow tải .eml từ UI đủ cho bài thực hành thủ công.

### 19.1. File .eml có thể chứa dữ liệu nhạy cảm

Body, OTP, reset URL và attachment tồn tại trong raw message dù được base64. Không commit captured production email vào repository.

### 19.2. Raw bytes khác reserialization

Đọc file .eml từ disk là đọc raw representation. Nếu tạo MimeMessage rồi gọi writeTo(), thư viện có thể serialize lại; không mặc định đó là byte-for-byte copy của file gốc.

## 20. Viết MimeReader đọc .eml bằng Jakarta Mail

Tạo **MimeReader.java**:

~~~java
package com.example.maildemo;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Properties;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

public final class MimeReader {

    public static void main(String[] args)
            throws Exception {

        if (args.length != 1) {
            System.err.println(
                    "Usage: MimeReader <path-to-message.eml>"
            );
            System.exit(2);
        }

        Path file = Path.of(args[0]);

        System.out.println(
                "Raw .eml bytes: " + Files.size(file)
        );

        Session session = Session.getInstance(
                new Properties()
        );

        try (InputStream in = Files.newInputStream(file)) {
            MimeMessage mail = new MimeMessage(
                    session,
                    in
            );

            System.out.println(
                    "From: " + Arrays.toString(
                            mail.getFrom()
                    )
            );

            System.out.println(
                    "To: " + Arrays.toString(
                            mail.getRecipients(
                                    Message.RecipientType.TO
                            )
                    )
            );

            System.out.println(
                    "Subject: " + mail.getSubject()
            );

            System.out.println(
                    "Message-ID: " + mail.getMessageID()
            );

            MimeTreePrinter.print(mail, 0);
        }
    }
}
~~~

### 20.1. Không cần IMAP

MimeMessage(Session, InputStream) parse file .eml được tải từ capture server; không cần mailbox credentials.

### 20.2. Decoded Subject

getSubject() trả một String có nội dung tiếng Việt đã được xử lý theo MIME header encoding.

### 20.3. InputStream lifecycle

try-with-resources giúp đóng file handle. Khi đọc attachment parts, cũng cần đóng decoded streams.

## 21. Duyệt cây MIME đệ quy

Tạo **MimeTreePrinter.java**:

~~~java
package com.example.maildemo;

import java.io.InputStream;
import java.util.Arrays;

import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeTreePrinter {

    private MimeTreePrinter() {}

    public static void print(Part part, int depth)
            throws Exception {

        String indent = "  ".repeat(depth);
        String disposition = part.getDisposition();
        String filename = part.getFileName();

        System.out.println(indent + "Part");
        System.out.println(
                indent + "  Type: " + part.getContentType()
        );
        System.out.println(
                indent + "  Disposition: " + disposition
        );
        System.out.println(
                indent + "  Filename: " + filename
        );
        System.out.println(
                indent + "  CID: " + Arrays.toString(
                        part.getHeader("Content-ID")
                )
        );

        Object content = part.getContent();

        if (content instanceof Multipart multi) {
            for (int i = 0; i < multi.getCount(); i++) {
                print(
                        multi.getBodyPart(i),
                        depth + 1
                );
            }
            return;
        }

        if (content instanceof Message nested) {
            print(nested, depth + 1);
            return;
        }

        boolean isAttachment =
                Part.ATTACHMENT.equalsIgnoreCase(
                        disposition
                ) || filename != null;

        if (!isAttachment
                && (part.isMimeType("text/plain")
                    || part.isMimeType("text/html"))
                && content instanceof String text) {

            String preview = text
                    .replace('\r', ' ')
                    .replace('\n', ' ');

            System.out.println(
                    indent + "  Characters: "
                    + text.length()
            );
            System.out.println(
                    indent + "  Preview: "
                    + preview.substring(
                            0,
                            Math.min(preview.length(), 120)
                    )
            );
            return;
        }

        try (InputStream decoded =
                     part.getInputStream()) {

            byte[] buffer = new byte[4096];
            long count = 0;
            int read;

            while ((read = decoded.read(buffer)) != -1) {
                count += read;
            }

            System.out.println(
                    indent + "  Decoded bytes: " + count
            );
        }
    }
}
~~~

### 21.1. Vì sao dùng instanceof Multipart?

Nested MIME parts là điều bình thường. Một parser chỉ duyệt root một cấp sẽ bỏ sót text body hoặc attachment.

### 21.2. Vì sao không cast mọi content thành String?

Part.getContent() có thể trả String, Multipart, Message hoặc một kiểu khác; cast String vô điều kiện có thể gây ClassCastException.

### 21.3. Vì sao kiểm tra filename/disposition?

Một attachment text/plain có thể không phải plain-text body. Bài demo xem file nào có filename là một dạng attachment, phù hợp với mục tiêu lab.

### 21.4. Giới hạn của parser demo

Với MIME từ nguồn không đáng tin cậy, cần giới hạn tổng parts, recursion depth, decoded bytes, stream time và kích thước. Code học tập chưa phải parser an toàn cho mọi email độc hại.

## 22. Chạy MimeReader

Trong IDE, chạy main class:

~~~text
com.example.maildemo.MimeReader
~~~

với program argument là đường dẫn file .eml.

Nếu dùng Gradle Groovy DSL, có thể thêm task:

~~~groovy
tasks.register('readMime', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.maildemo.MimeReader'

    args = [
        providers.gradleProperty('eml')
            .orElse('sample-message.eml')
            .get()
    ]
}
~~~

Chạy:

~~~bash
./gradlew readMime -Peml=sample-message.eml
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat readMime -Peml="C:\temp\sample-message.eml"
~~~

### 22.1. Kết quả cần quan sát

- Subject tiếng Việt được decode đúng.
- Có ít nhất text/plain và text/html.
- Có part attachment với filename ket-qua.csv.
- Tổng decoded bytes của CSV đúng với dữ liệu nhỏ tạo trong MailDemoSender.
- Root part có content type thuộc dạng multipart phù hợp.

### 22.2. Không assert cấu trúc cố định bằng vị trí

Tùy MIME implementation, body có thể ở một part nested khác; semantic content quan trọng hơn thứ tự part.

## 23. Tìm body và attachment bằng utility

Một utility cho kiểm thử tự động:

~~~java
package com.example.maildemo;

import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimePartFinder {

    private MimePartFinder() {}

    public static String findText(
            Part part,
            String mimeType
    ) throws Exception {

        if (part.isMimeType(mimeType)
                && !isAttachment(part)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                return text;
            }
        }

        Object content = part.getContent();

        if (content instanceof Multipart multi) {
            for (int i = 0; i < multi.getCount(); i++) {
                String text = findText(
                        multi.getBodyPart(i),
                        mimeType
                );

                if (text != null) {
                    return text;
                }
            }
        } else if (content instanceof Message nested) {
            return findText(nested, mimeType);
        }

        return null;
    }

    public static Part findAttachment(
            Part part,
            String filename
    ) throws Exception {

        if (filename.equals(part.getFileName())) {
            return part;
        }

        Object content = part.getContent();

        if (content instanceof Multipart multi) {
            for (int i = 0; i < multi.getCount(); i++) {
                Part found = findAttachment(
                        multi.getBodyPart(i),
                        filename
                );

                if (found != null) {
                    return found;
                }
            }
        } else if (content instanceof Message nested) {
            return findAttachment(nested, filename);
        }

        return null;
    }

    private static boolean isAttachment(
            Part part
    ) throws Exception {

        return Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition()
        ) || part.getFileName() != null;
    }
}
~~~

### 23.1. Không dùng root.getBodyPart(0) như một định luật

MimeMessageHelper có thể tạo multipart/mixed chứa related, rồi related chứa alternative. Helper tìm đệ quy sẽ bền vững hơn với nesting.

### 23.2. Utility này không kiểm tra magic bytes

Việc tìm được filename không chứng minh file được đính kèm an toàn hoặc đúng content type. Với attachment test, cần so sánh decoded bytes.

## 24. Kiểm tra attachment bytes sau khi decode

Khi đã tìm được Part với filename ket-qua.csv:

~~~java
Part attachment =
        MimePartFinder.findAttachment(
                message,
                "ket-qua.csv"
        );

if (attachment == null) {
    throw new IllegalStateException(
            "Missing CSV attachment"
    );
}

try (var in = attachment.getInputStream()) {
    String csv = new String(
            in.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8
    );

    System.out.println(csv);
}
~~~

Kỳ vọng:

~~~text
id,status
LAB-475,READY
~~~

### 24.1. Raw base64 không phải decoded file

Nếu MIME part dùng base64, getInputStream() thường trả decoded bytes. Đừng so sánh raw base64 string với nội dung CSV.

### 24.2. readAllBytes chỉ phù hợp lab nhỏ

Không đọc attachment hàng trăm MB vào RAM trong production. Stream dữ liệu với giới hạn và kiểm tra kích thước.

### 24.3. Filename từ email là dữ liệu không đáng tin

Nếu mở rộng parser để lưu attachments xuống disk, phải sanitize filename và chống path traversal. Bài lab chỉ đọc/so sánh bytes, không tự ghi file.

## 25. Đọc headers raw và decoded

MIME API:

~~~java
String subject = message.getSubject();
String type = message.getContentType();
String id = message.getMessageID();
~~~

Để in header lines:

~~~java
var headers = message.getAllHeaderLines();

while (headers.hasMoreElements()) {
    System.out.println(headers.nextElement());
}
~~~

### 25.1. Header line có thể folded

Một Subject dài có thể được biểu diễn trên nhiều lines. Test nên dùng getSubject() thay vì so sánh raw line.

### 25.2. Header order không bảo đảm bất biến

Không yêu cầu From phải đứng trước To hay Date luôn có cùng vị trí. Chỉ assert names/values có ý nghĩa.

### 25.3. Reserialization khác original source

Một MimeMessage được parse rồi writeTo() có thể sinh bytes khác file .eml đã tải; nếu cần xem source nguyên bản, dùng bytes của file gốc.

## 26. Thêm inline resource dùng Content-ID

Chuẩn bị một file PNG hợp lệ tại:

~~~text
src/main/resources/mail/logo.png
~~~

Trong MailDemoSender, có thể **thay phần HTML** bằng:

~~~java
String html =
        "<html><body>"
      + "<h1>Xin chào!</h1>"
      + "<img src=\"cid:brand-logo\" alt=\"Logo\">"
      + "</body></html>";

helper.setText(plain, html);

helper.addInline(
        "brand-logo",
        new org.springframework.core.io.ClassPathResource(
                "mail/logo.png"
        ),
        "image/png"
);
~~~

Đây là **đoạn mở rộng thay thế thao tác setText cũ**, không phải yêu cầu gọi setText hai lần để gửi hai body khác nhau.

### 26.1. HTML cid khớp Content-ID

Trong HTML là **cid:brand-logo**, còn raw MIME Content-ID có thể được hiển thị là **<brand-logo>**. Cần normalize dấu ngoặc khi kiểm tra.

### 26.2. Thứ tự và multipart/related

Nên setText trước addInline theo cách dùng MimeMessageHelper phù hợp. MIME layout có thể chứa nested related part, không phải chỉ attachment thường.

### 26.3. UI có thể khác mail client thật

Mailpit có thể render inline resource, nhưng một số email clients chặn hình ảnh hoặc sanitize HTML. MIME correctness không tự đảm bảo mọi client hiển thị giống nhau.

## 27. Bài kiểm thử tiếng Việt và filename có dấu

Mở rộng:

~~~java
helper.setSubject(
        "Thông báo xác nhận – kiểm thử UTF-8"
);

byte[] data = "tên,giá trị\nĐơn A,123\n"
        .getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "báo-cáo-tháng.csv",
        new ByteArrayResource(data),
        "text/csv"
);
~~~

Kiểm tra riêng:

- Subject decoded.
- Plain text.
- HTML text.
- Filename decoded.
- Nội dung bytes CSV.
- Content-Type và Content-Disposition.

### 27.1. Đừng kết luận chỉ từ raw source

Nếu raw Subject là encoded-word hoặc body là quoted-printable, đó không nhất thiết là lỗi. So sánh qua Jakarta Mail decoded API.

### 27.2. UTF-8 không sửa nguồn đã bị hỏng

Nếu Java String bị sai từ bước đọc database/resource, MimeMessageHelper không tự chữa mojibake. Kiểm tra từng bước của data pipeline.

## 28. GreenMail: server SMTP embedded cho JUnit

Thực hành thủ công với Mailpit giúp quan sát. Với CI, một test nên tự động:

~~~text
JUnit test
     |
     v
GreenMail.start()
     |
     v
JavaMailSenderImpl.send(...)
     |
     v
GreenMail.getReceivedMessages()
     |
     v
Assert MIME contents
     |
     v
GreenMail.stop()
~~~

### 28.1. Thêm dependency cho test

Ví dụ Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Ví dụ một release GreenMail dùng Jakarta Mail;
    // xác nhận artifact/version tương thích với project.
    testImplementation 'com.icegreen:greenmail:2.1.0'
}
~~~

Dòng GreenMail **2.1.x** hướng tới API Jakarta Mail. Không sử dụng artifact quá cũ dùng javax.mail khi production dependencies của test đang là jakarta.mail.

### 28.2. Không đưa GreenMail vào production runtime

Khai báo testImplementation và chỉ khởi động server trong test lifecycle.

### 28.3. Cổng test riêng

Ví dụ test dùng 3025 để tránh trùng Mailpit 1025. Khi chạy song song, nên dùng ephemeral port/isolated test resources nếu thư viện và runner hỗ trợ.

## 29. Viết SMTP/MIME round-trip integration test

~~~java
package com.example.maildemo;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;

import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class MimeRoundTripTest {

    @Test
    void canSendAndReadMime() throws Exception {

        GreenMail server = new GreenMail(
                new ServerSetup(
                        3025,
                        "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );

        server.start();

        try {
            JavaMailSenderImpl sender =
                    new JavaMailSenderImpl();

            sender.setHost("127.0.0.1");
            sender.setPort(3025);

            sender.getJavaMailProperties()
                    .put("mail.smtp.auth", "false");
            sender.getJavaMailProperties()
                    .put("mail.smtp.starttls.enable", "false");

            new MailDemoSender(sender).sendSample();

            MimeMessage[] received =
                    server.getReceivedMessages();

            assertEquals(1, received.length);

            MimeMessage mail = received[0];

            assertEquals(
                    "Bài thực hành MIME: tiếng Việt và tệp đính kèm",
                    mail.getSubject()
            );

            assertEquals(
                    "student@example.invalid",
                    mail.getRecipients(
                            Message.RecipientType.TO
                    )[0].toString()
            );

            assertTrue(
                    mail.getContent() instanceof Multipart
            );

            String plain = MimePartFinder.findText(
                    mail, "text/plain"
            );

            String html = MimePartFinder.findText(
                    mail, "text/html"
            );

            assertNotNull(plain);
            assertNotNull(html);
            assertTrue(
                    plain.contains("Đây là nội dung text/plain")
            );
            assertTrue(
                    html.contains("<strong>text/html</strong>")
            );

            Part csv = MimePartFinder.findAttachment(
                    mail, "ket-qua.csv"
            );

            assertNotNull(csv);

            byte[] actualBytes;

            try (var in = csv.getInputStream()) {
                actualBytes = in.readAllBytes();
            }

            assertEquals(
                    "id,status\nLAB-475,READY\n",
                    new String(
                            actualBytes,
                            StandardCharsets.UTF_8
                    )
            );
        } finally {
            server.stop();
        }
    }
}
~~~

### 29.1. Test này mạnh hơn mock.send()

Nó thực sự mở SMTP connection đến server kiểm thử và nhận message, không chỉ verify rằng service gọi sender.send() một lần.

### 29.2. Test không dùng SMTP production

Server và sender dùng loopback, không cần username/password thật, không gửi thư tới người nhận ngoài Internet.

### 29.3. Không assert boundary hoặc Message-ID cố định

Generated values có thể thay đổi. Assertions tập trung semantics: recipient, Subject, parsed body và attachment.

### 29.4. Port 3025 có thể xung đột trong CI

Không chạy các test cùng cổng 3025 đồng thời. Với test suite chạy song song, sử dụng một cơ chế cấp ephemeral ports và inject actual bound port vào sender.

## 30. GreenMail và Mailpit kiểm tra những tầng nào?

| Kiểm tra | Mailpit UI/.eml | GreenMail JUnit |
| --- | --- | --- |
| SMTP connection tới local test server | Có | Có |
| Capture một message | Có | Có |
| Đọc MIME headers | Có | Có |
| Parse multipart/alternative | Qua raw/reader | Qua MimeMessage |
| Assert decoded body | Có thể bằng reader | Có trực tiếp |
| Assert attachment bytes | Có thể bằng reader | Có trực tiếp |
| Tự chạy lại trong CI | Qua script/container | Thuận tiện embedded |
| Kiểm tra production AUTH/TLS | Không mặc định | Không mặc định |
| Kiểm tra Gmail/Outlook inbox | Không | Không |
| Xác nhận downstream delivered/read | Không | Không |

### 30.1. Chọn công cụ theo câu hỏi

Mailpit giúp developer **nhìn thấy** thư và tải MIME; GreenMail giúp test **lặp lại** với assertions tự động.

### 30.2. Mock JavaMailSender vẫn có vai trò

Unit test orchestrator, retry, routing và business decision thường chỉ cần Mockito. SMTP capture integration test dành cho MIME serialization/network handshake ở local.

## 31. Kiểm thử Bcc và SMTP envelope

Một message có:

~~~text
SMTP envelope:
  MAIL FROM: bounce@example.invalid
  RCPT TO: student@example.invalid
  RCPT TO: hidden@example.invalid

MIME headers:
  From: demo@example.invalid
  To: student@example.invalid
~~~

### 31.1. SMTP envelope không giống visible headers

Một Bcc recipient có thể nhận message theo envelope mà không được liệt kê trong raw MIME headers.

### 31.2. Test bằng capture server phù hợp

Nếu server test cung cấp envelope metadata, so sánh RCPT TO tại SMTP layer. Đừng suy toàn bộ envelope từ một .eml chỉ chứa message headers/body.

### 31.3. Return-Path/Received có thể khác production

Những headers do MTA tạo khi email đi qua nhiều hop sẽ không nhất thiết được Mailpit/GreenMail mô phỏng giống production.

## 32. Negative test: cấu hình sai port

Đổi Spring Mail port tạm thời:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 9999
~~~

Khi gửi có thể nhận lỗi connection refused hoặc timeout.

### 32.1. Đọc đúng nguyên nhân

Kiểm tra Docker Compose, host/port, firewall loopback và Spring profile. Đây là lỗi kết nối/config, không phải lỗi MIME.

### 32.2. Không retry vô hạn

Nếu port sai cố định, retry 5 giây một lần không làm server đổi cấu hình. Nên sửa configuration.

### 32.3. Nếu app chạy trong Docker

Nhắc lại: 127.0.0.1 bên trong container không trỏ tới Mailpit ở container khác. Dùng service DNS name và port nội bộ đúng.

## 33. Negative test: STARTTLS không khớp

Nếu server fake không hỗ trợ STARTTLS ở setup đang dùng, nhưng client bắt buộc:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
~~~

thì SMTP submission có thể thất bại.

### 33.1. Không tắt TLS của production để giải quyết test

SMTP local plaintext trên loopback là một cấu hình riêng cho lab. Production cần cấu hình STARTTLS/implicit TLS và hostname verification theo provider.

### 33.2. Phân biệt các port

- 1025: test port trong Docker Compose.
- 587: thường dùng SMTP submission với STARTTLS.
- 465: thường dùng implicit TLS.

Port không tự tạo bảo đảm bảo mật; phải kiểm tra các thuộc tính protocol.

## 34. Negative test: parse sai cấu trúc MIME

Một lỗi thường thấy:

~~~java
Object content = message.getContent();
String html = (String) content;
~~~

Nếu root là Multipart, cast này ném ClassCastException.

Một lỗi khác:

~~~java
Multipart multi = (Multipart) message.getContent();
String body = (String) multi.getBodyPart(0).getContent();
~~~

Part 0 có thể lại là Multipart, không phải String.

### 34.1. Dùng đệ quy và isMimeType

Kiểm tra content instanceof Multipart, rồi recurse tới text/plain/text/html parts. Luôn phân biệt attachment với body.

### 34.2. Không phụ thuộc số part cố định

Thêm một inline image hoặc attachment có thể làm MIME tree lồng sâu hơn. Assertions theo ý nghĩa bền vững hơn so với chỉ số position.

## 35. Negative test: attachment sai

Các lỗi:

- Filename đúng, bytes rỗng.
- Content-Type khai PDF nhưng bytes không phải PDF.
- InputStream đã được đọc hết.
- Resource không thể mở khi MIME serialize.
- Filename có Unicode bị decode sai.
- Attachment bị đặt inline ngoài ý muốn.
- Dữ liệu lớn vượt giới hạn provider.

### 35.1. Đọc decoded bytes thay vì nhìn icon

Một UI hiển thị attachment chỉ cho biết MIME metadata có thể được nhận diện. Test nên so sánh file bytes hoặc checksum.

### 35.2. Có thể đọc attachment muộn

MimeMessageHelper có thể giữ reference tới resource; lúc Jakarta Mail serialize để send mới đọc source. Nếu resource mất trước thời điểm đó, lỗi có thể xuất hiện khi gửi.

### 35.3. Không lưu filename trực tiếp từ email ngoài

Nếu viết parser để lưu attachment, sanitize filename/path và giới hạn bytes; metadata MIME không phải một filesystem path đáng tin.

## 36. Trường hợp Inline image

Đọc HTML:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Tìm MIME part có Content-ID **brand-logo**, Content-Type image/png và dữ liệu PNG hợp lệ.

### 36.1. Normalize CID

Raw header có thể là **<brand-logo>**, còn HTML dùng **cid:brand-logo**. Điều này thường hợp lệ.

### 36.2. MIME đúng không có nghĩa mọi client render giống nhau

Một số mail clients chặn remote/inline images hoặc sanitize HTML. Cần test rendering riêng nếu sản phẩm phụ thuộc vào bố cục.

## 37. Bảo mật môi trường SMTP capture

- Bind Docker ports vào loopback hoặc test network cô lập.
- Không expose UI/API ra public Internet.
- Không dùng SMTP production credentials.
- Không copy dữ liệu khách hàng vào demo fixtures.
- Không commit .eml từ email thật lên Git.
- Không log SMTP AUTH payload.
- Không dùng test endpoint public nhận recipient tùy ý.
- Không tự động gửi thật khi application startup.
- Dùng retention policy cho test data.
- Kiểm tra profile cấu hình trước khi chạy CI.
- Không dùng base64 như cơ chế che giấu nội dung nhạy cảm.

### 37.1. Local profile không thay security boundary

Một server chạy profile local trên máy chung vẫn có thể bị truy cập nếu bind/route sai. Cần cấu hình mạng và quyền truy cập phù hợp.

### 37.2. MIME attachments là untrusted input khi nhận từ bên ngoài

Bài lab đọc email tự tạo. Với incoming email thật, có thể gặp MIME phức tạp, malformed parts hoặc file nguy hiểm; cần sandbox/scan/size limits.

## 38. Giới hạn khi đánh giá delivery và tính đúng đắn gửi mail

| Câu hỏi | Capture server đủ trả lời? |
| --- | --- |
| Spring gửi đến local SMTP port đúng không? | Có |
| SMTP test server đã nhận message? | Có |
| MIME headers/UTF-8/HTML/attachment đúng? | Có, nếu assertions phù hợp |
| MIME có Content-ID và multipart nesting đúng? | Có |
| SMTP AUTH/TLS provider production đúng? | Không mặc định |
| Domain SPF/DKIM/DMARC đúng? | Không |
| Provider có rate limit khác không? | Không |
| Mail sẽ không vào spam? | Không |
| Message đã vào inbox của người nhận? | Không |
| Recipient đã đọc email? | Không |
| Retry sẽ không bao giờ gửi trùng? | Không |

### 38.1. SMTP submit vs downstream delivery

JavaMailSender.send hoàn tất và Mailpit capture message chỉ khẳng định **bước submission tới server thử nghiệm**. Nếu cần delivery status, hệ thống production cần downstream feedback như bounce/delivered webhooks được xác thực theo provider contract.

### 38.2. Không tuyên bố exactly-once SMTP

Database outbox và SMTP không có transaction chung. Nếu provider đã accept DATA nhưng app crash trước khi ghi SENT, retry có thể tạo duplicate. Capture test không loại bỏ khoảng bất định này.

## 39. CI và tổ chức test

Có thể chia kiểm thử theo tầng:

| Tầng | Công cụ | Câu hỏi |
| --- | --- | --- |
| Unit composer | JUnit/Jakarta Mail | MIME payload được chuẩn bị đúng? |
| Unit orchestration | Mockito JavaMailSender | Sender được gọi đúng? |
| Local SMTP integration | GreenMail/Mailpit | Submission và MIME serialization đúng? |
| Production-like contract | Provider sandbox | AUTH/TLS/quotas cụ thể đúng? |
| UI email client QA | Preview/manual | Rendering trên khách hàng mục tiêu ổn? |

### 39.1. CI nên cô lập SMTP server

Một shared Mailpit inbox chứa messages từ nhiều tests có thể làm assertion count flaky. Dùng instance riêng, reset hợp lý hoặc correlation test header.

### 39.2. Test lifecycle phải cleanup

Stop GreenMail trong finally hoặc extension lifecycle; dừng test container và không để port/test data tồn tại không kiểm soát.

### 39.3. Không phụ thuộc vào generated boundary

CI cần assertions trên decoded content và MIME semantics, không so sánh toàn bộ raw .eml với string literal có boundary ngẫu nhiên.

## 40. Runbook chẩn đoán ngắn

| Triệu chứng | Kiểm tra |
| --- | --- |
| UI 8025 không mở | docker compose ps, port bind, logs |
| Không có message | App profile local, SMTP host/port 1025 |
| Connection refused | Mailpit chạy chưa, app chạy host/container nào |
| HTTP demo 404 | Spring profile/component scan |
| AUTH error | Dev config có bật auth nhầm? |
| STARTTLS error | Fake server có hỗ trợ mode đang yêu cầu? |
| Subject lỗi dấu | Đầu vào Unicode/charset và getSubject |
| Chỉ có HTML | Dùng setText(plain, html) |
| Parser lỗi cast | Root Multipart, dùng recursive walk |
| Attachment rỗng | Source/resource bytes và decoded stream |
| Inline không hiện | CID, Content-ID, related parts |
| Test được >1 message | Endpoint gọi nhiều lần, server không reset |
| GreenMail port occupied | Test parallel conflict, dùng dynamic port |
| Mailpit thấy mail nhưng Gmail không thấy | Mailpit capture, không deliver |

### 40.1. Chẩn đoán theo thứ tự

Xác nhận server và port → Spring config → SMTP capture → MIME headers/tree → decoded text/files → behavior của mail client. Đừng sửa HTML khi nguyên nhân thật là ứng dụng đang gửi nhầm SMTP server.

## 41. Checklist hoàn thành

- [ ] Docker Compose khởi động Mailpit.
- [ ] Mở được UI tại 127.0.0.1:8025.
- [ ] Spring local profile trỏ SMTP 127.0.0.1:1025.
- [ ] Endpoint local gửi đúng một message khi gọi một lần.
- [ ] From/To/Subject hiển thị đúng.
- [ ] Có plain text và HTML.
- [ ] Subject/body tiếng Việt decode chính xác.
- [ ] Có attachment ket-qua.csv.
- [ ] Đã tải file .eml và đọc bằng Jakarta Mail.
- [ ] MIME tree parser duyệt nested Multipart.
- [ ] Attachment decoded bytes đúng.
- [ ] Không hardcode boundary/Message-ID trong test.
- [ ] GreenMail JUnit test nhận message và assert MIME.
- [ ] Không dùng SMTP credentials/recipient production.
- [ ] Hiểu rõ capture success khác inbox delivery.
- [ ] Đã cleanup test server khi xong.

## 42. Câu hỏi thường gặp

**1. Mailpit có gửi email ra Internet không?**

Với setup capture trong bài, nó lưu message để xem thay vì deliver tới mailbox ngoài. Đó là mục đích của SMTP server kiểm thử.

**2. Vì sao UI là port 8025 mà Spring gửi port 1025?**

8025 là HTTP web UI/API; 1025 là SMTP listener. Chúng khác giao thức và vai trò.

**3. Có cần IMAP/POP3 để đọc MIME không?**

Không. Bạn có thể tải .eml từ Mailpit hoặc lấy MimeMessage qua GreenMail API trong test. IMAP/POP3 phục vụ bài toán đọc mailbox khác.

**4. Có cần SMTP username/password không?**

Không trong lab local capture; production SMTP thường có yêu cầu xác thực/bảo mật riêng.

**5. Tại sao Subject raw bị encode?**

MIME hỗ trợ encoded-word cho Unicode headers. MimeMessage.getSubject() decode thành String dùng được.

**6. Base64 có bảo vệ nội dung email không?**

Không. Nó chỉ là encoding. Mọi người có bytes đều có thể decode.

**7. Vì sao MIME có nhiều tầng multipart?**

Plain/HTML alternatives, inline resources và attachments có cấu trúc khác nhau, nên MIME có thể chứa các nested Multipart.

**8. Vì sao getContent() không phải String?**

Part có thể là Multipart, nested Message, binary data hoặc String. Hãy kiểm tra type trước khi cast.

**9. Tại sao attachment text/plain không phải email body?**

Vì MIME metadata filename/disposition xác định nó là một file part, không phải phần nội dung chính.

**10. Có nên assert raw boundary không?**

Không. Boundary được tạo động; assert decoded content và MIME semantics.

**11. Có thể dùng JavaMailSender mock thay GreenMail không?**

Có để unit test orchestration, nhưng mock không kiểm tra SMTP exchange và MIME serialization thực. GreenMail phù hợp integration test.

**12. Cùng Message-ID có ngăn gửi trùng không?**

Không có bảo đảm SMTP relay tự loại trùng theo Message-ID.

**13. Bcc có xuất hiện trong .eml không?**

Không nên mặc định. Bcc thường được đưa vào envelope recipients mà không lộ trong headers gửi đi.

**14. Nếu sender.send trả bình thường thì recipient đã nhận chưa?**

Không. Đó là submit result phía SMTP client/server test, không chứng minh downstream inbox delivery.

**15. Vì sao GreenMail test dùng port 3025?**

Ví dụ chọn port test riêng, khác Mailpit 1025. Với CI chạy song song nên dùng port động/cô lập để tránh xung đột.

**16. Vì sao không gửi test mail vào tài khoản Gmail thật?**

Làm test phụ thuộc network/provider, dễ gửi nhầm, rate limit và khó đối chiếu raw MIME chính xác.

**17. Tôi có thể commit file .eml lên Git không?**

Chỉ khi đó là fixture giả, không chứa dữ liệu nhạy cảm và phù hợp chính sách repository.

**18. Vì sao raw MIME không có chữ tiếng Việt nguyên văn?**

Quoted-printable/base64 và encoded-word có thể biểu diễn bytes Unicode. Dùng Jakarta Mail decode.

**19. Làm sao phát hiện attachment bị lỗi?**

So sánh filename, content type và decoded bytes/checksum với dữ liệu mong đợi.

**20. SMTP test local có bảo đảm SPF/DKIM/DMARC production đúng không?**

Không. Cần cấu hình và kiểm thử domain/provider riêng.

**21. Vì sao message hiển thị đẹp trong Mailpit nhưng xấu trong Outlook?**

Mail clients có rendering engines và security policies khác nhau. MIME capture chỉ là một lớp kiểm tra.

**22. Có nên để endpoint test tồn tại trong production không?**

Không. Ví dụ giới hạn bằng local profile và không chấp nhận recipient tùy ý; production có quy trình và quyền riêng nếu cần diagnostic SMTP.

**23. Làm sao test attachment inline?**

Dùng cid trong HTML và Content-ID của MIME part image; kiểm tra decoded image bytes và cấu trúc multipart/related.

**24. Dùng Docker mà Spring không kết nối localhost được?**

Nếu Spring chạy trong container, localhost là app container. Dùng service hostname Mailpit cùng network.

**25. Có cần assert chính xác Content-Transfer-Encoding không?**

Thông thường không. Nếu nội dung decoded và Content-Type/charset đúng, quoted-printable hay base64 có thể thay đổi theo implementation.

## 43. Ghi nhớ về chạy SMTP server kiểm thử và đọc lại MIME

**Một bài kiểm thử Spring Framework Mail đáng tin cậy nên gửi email tới SMTP capture server, không gửi vào production.** Mailpit chạy qua Docker Compose có thể nhận SMTP trên **127.0.0.1:1025** và hiển thị message qua UI **127.0.0.1:8025**. Spring Boot dùng JavaMailSender/MimeMessageHelper để tạo mail có **text/plain, text/html, UTF-8 và attachment**, sau đó gửi đúng một lần vào server kiểm thử.

**Đọc lại MIME phải đi xa hơn HTML preview.** Hãy tải .eml, xem headers, Content-Type, charset, Content-Transfer-Encoding, Content-Disposition, Content-ID và các boundaries, rồi dùng Jakarta Mail để parse **MimeMessage** và duyệt **Multipart** đệ quy. Tìm đúng body parts, phân biệt text attachment với plain text body, so sánh decoded Subject và file bytes; không assert generated boundary hay Message-ID là chuỗi cố định.

Với kiểm thử tự động, **GreenMail** có thể khởi động SMTP server trong JVM, nhận message do JavaMailSenderImpl gửi và cung cấp MimeMessage cho JUnit assertions. Tách unit test composer, orchestration test và SMTP integration test; chỉ dùng dữ liệu giả, môi trường cô lập, không dùng secrets hoặc recipients thật.

Cuối cùng, **SMTP capture success chỉ xác nhận local submission, không chứng minh inbox delivery**. AUTH/TLS production, SPF/DKIM/DMARC, spam filtering, provider webhooks và duplicate handling là những trách nhiệm kiểm thử khác. Khi hiểu đúng giới hạn này, bạn có thể kiểm tra nội dung email một cách nhanh, an toàn, có thể lặp lại và dễ chẩn đoán.
