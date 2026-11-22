# Kiểm thử timeout và server từ chối trong Spring Framework Mail

Một ứng dụng gửi email qua **Spring Framework Mail** có thể hoạt động tốt khi SMTP server phản hồi nhanh, nhưng dễ gặp lỗi khó tái hiện khi kết nối bị chậm, mail server từ chối địa chỉ nhận, tài khoản gửi hết quyền, hoặc kết nối bị ngắt giữa lúc gửi nội dung. Trong các trường hợp này, việc mock `JavaMailSender` để ném một exception không đủ chứng minh hệ thống thật phản ứng đúng: nhiều lỗi chỉ xuất hiện khi **Jakarta Mail thực sự giao tiếp qua socket SMTP** và nhận phản hồi ở từng bước của giao thức.

Bài học này hướng dẫn thiết kế **kiểm thử tích hợp (integration testing)** cho hai nhóm tình huống:

1. **Timeout:** kết nối không được thiết lập kịp, không đọc được phản hồi SMTP đúng hạn hoặc gửi dữ liệu quá lâu.
2. **Server từ chối:** SMTP server phản hồi mã 4xx/5xx ở một lệnh cụ thể, ví dụ từ chối recipient, dữ liệu email, địa chỉ gửi hoặc authentication.

Mục tiêu là kiểm tra không chỉ exception của Spring Mail, mà còn trạng thái nghiệp vụ, retry, giới hạn thời gian chờ, khả năng tránh duplicate, an toàn transaction, log và năng lực hồi phục khi SMTP hoạt động trở lại.

> Nguyên tắc cốt lõi: kiểm thử theo **đúng giai đoạn SMTP gặp lỗi**. “SMTP failed” không đủ để quyết định email có thể retry, recipient có cần suppression hay hệ thống có nguy cơ gửi trùng.

## 1. Vì sao phải kiểm thử tích hợp với SMTP thật hoặc giả lập?

Ví dụ một unit test:

~~~java
doThrow(new MailSendException("SMTP unavailable"))
        .when(mailSender).send(any(SimpleMailMessage.class));
~~~

Test này hữu ích để kiểm tra cách business service xử lý exception. Nhưng nó không chứng minh:

- Host/port và các thuộc tính timeout đã thực sự được Jakarta Mail áp dụng.
- Kết nối SMTP có bị timeout như dự kiến hay không.
- Server từ chối ở bước RCPT TO khác từ chối ở DATA như thế nào.
- Spring Mail bọc exception do transport tạo ra ra sao.
- Mail sender có chờ vô hạn khi server không phản hồi không.
- Thông điệp có thể đã được relay nhận trước khi ứng dụng nhận lỗi không.
- Một message có nhiều recipient sẽ được xử lý thế nào khi chỉ một địa chỉ bị từ chối.

**Integration test** phải cho thành phần được kiểm tra đi qua một ranh giới thực, chẳng hạn `JavaMailSenderImpl` → Jakarta Mail → TCP socket → SMTP test server. Server này cần có khả năng điều khiển phản hồi, tạm ngưng trả lời, ngắt kết nối và ghi nhận các lệnh đã nhận.

### Các cấp kiểm thử nên phối hợp

| Cấp | Thành phần thực | Mục tiêu |
| --- | --- | --- |
| Unit test | Business service, mock sender | Bắt lỗi, phản hồi nghiệp vụ, trạng thái mong đợi |
| Integration test SMTP | JavaMailSenderImpl + Jakarta Mail + SMTP test server | Kiểm tra giao thức, timeout, phản hồi 4xx/5xx |
| Integration test persistence | Worker + database/outbox + SMTP fake | Retry schedule, transaction, lease, chống mất message |
| Multi-instance test | Nhiều worker + broker/limiter + SMTP fake | Đảm bảo không gửi trùng vì claim, không bão retry |
| Provider staging test | Provider/account thử nghiệm được phép | Xác minh TLS, AUTH, quota, permission đặc thù |

Không dùng SMTP production hoặc hộp thư của khách hàng để chủ động tạo hàng nghìn timeout/refusal. Bài thử lỗi phải chạy trên hạ tầng test được phép, có giới hạn tài nguyên và địa chỉ nhận kiểm thử.

## 2. Hiểu các giai đoạn trong phiên SMTP

Một phiên SMTP submission có thể diễn ra như sau (sơ đồ đã rút gọn):

~~~text
Application / Jakarta Mail                 SMTP relay
            |                                  |
            |--------- TCP connect ---------->|
            |<-------- 220 greeting ----------|
            |--------- EHLO ----------------->|
            |<-------- 250 capabilities ------|
            |--------- STARTTLS ------------->|  nếu yêu cầu
            |<-------- 220 ready -------------|
            |======= TLS handshake ===========|
            |--------- EHLO ----------------->|
            |<-------- 250 capabilities ------|
            |--------- AUTH ----------------->|  nếu có
            |<-------- 235 / 535 ------------|
            |--------- MAIL FROM ------------>|
            |<-------- 250 / 5xx ------------|
            |--------- RCPT TO -------------->|
            |<-------- 250 / 4xx / 5xx -------|
            |--------- DATA ----------------->|
            |<-------- 354 / 4xx / 5xx -------|
            |--------- headers + body ------->|
            |--------- <CRLF>.<CRLF> -------->|
            |<-------- 250 / 4xx / 5xx -------|
            |--------- QUIT ----------------->|
            |<-------- 221 -------------------|
~~~

Các mã trên chỉ là ví dụ phổ biến, không đại diện mọi SMTP extension hoặc provider. Không phải phiên nào cũng dùng STARTTLS hoặc AUTH, nhưng ứng dụng production phải tuân theo yêu cầu bảo mật do provider quy định.

### Vì sao vị trí lỗi quan trọng?

| Giai đoạn | Điều có thể xảy ra | Hệ quả |
| --- | --- | --- |
| TCP connect | Connection timeout hoặc refused | Chưa thiết lập phiên SMTP |
| Greeting/EHLO | Server không trả lời; session stall | Chưa bắt đầu gửi envelope/body |
| STARTTLS | Server không hỗ trợ hoặc TLS handshake lỗi | Không được âm thầm hạ cấp bảo mật |
| AUTH | Credential sai, hết quyền hoặc server xác thực bị lỗi | Lỗi theo SMTP account, không phải recipient |
| MAIL FROM | Địa chỉ gửi không được phép, policy từ chối | Chưa có message được chấp nhận |
| RCPT TO | Recipient không hợp lệ/tạm unavailable | Có thể chỉ ảnh hưởng một recipient |
| DATA trước nội dung | Server từ chối nhận dữ liệu | Chưa chuyển body |
| Sau khi gửi dấu kết thúc DATA | Server chấp nhận hoặc từ chối; phản hồi có thể bị mất | Có thể phát sinh kết quả **không xác định** |
| Sau thông điệp đã accepted | Provider/remote MX tiếp tục xử lý | Bounce/deferred không đồng nghĩa lỗi submit ban đầu |

Một test trả 550 ngay sau EHLO không thể dùng thay cho tình huống recipient bị từ chối ở RCPT TO. **Phải giả lập đúng lệnh và thời điểm** để test phân loại lỗi đáng tin cậy.

## 3. Ba kiểu timeout chính trong Jakarta Mail SMTP

Các thuộc tính SMTP thường dùng:

| Property | Ý nghĩa khái quát | Giới hạn điều gì? |
| --- | --- | --- |
| `mail.smtp.connectiontimeout` | Connection timeout | Thời gian chờ thiết lập kết nối TCP |
| `mail.smtp.timeout` | Socket read timeout | Thời gian chờ dữ liệu phản hồi từ SMTP server |
| `mail.smtp.writetimeout` | Socket write timeout | Thời gian ghi dữ liệu tới SMTP socket |

Giá trị cấu hình thường là số mili giây theo cách triển khai Jakarta Mail SMTP phổ biến. Khi không cấu hình, một số môi trường/provider có thể cho phép chờ rất lâu hoặc không giới hạn ở một giai đoạn; không nên dựa vào mặc định cho ứng dụng có SLA.

### 3.1. Connection timeout

Xảy ra khi client không thiết lập được TCP connection tới đích trong khoảng cấu hình.

Ví dụ:

- Đường mạng tới SMTP server bị blackhole/drop packet.
- Firewall không trả phản hồi.
- Route/network gặp sự cố.

**Phân biệt:** nếu kết nối bị từ chối ngay bằng TCP RST, thường là **connection refused**, không phải timeout. Cả hai làm gửi thất bại nhưng là hai failure modes khác nhau. Test kết nối tới một port chắc chắn không lắng nghe thường kiểm tra connection refused, **không phải connection timeout**.

### 3.2. Read timeout

Ứng dụng đã kết nối, nhưng server không trả lời lệnh SMTP trong thời gian cho phép:

~~~text
Client                           Fake SMTP server
  |---------- connect ---------->|
  |<--------- 220 greeting ------|
  |---------- EHLO ------------->|
  |                              | (không gửi reply)
  |   chờ đến read timeout       |
  |---- exception -------------->|
~~~

Đây là tình huống dễ tái hiện bằng một SMTP server test có khả năng **im lặng sau EHLO**. Nó không đòi hỏi mạng bên ngoài phải thật sự chậm.

### 3.3. Write timeout

Xảy ra khi dữ liệu gửi tới socket không thể được ghi kịp thời, ví dụ server ngừng đọc body và buffer phía TCP đầy.

Khó mô phỏng ổn định hơn read timeout vì bộ đệm của kernel/network có thể nhận một lượng dữ liệu lớn ngay cả khi phía server chưa thực sự đọc. Một test chỉ gửi chuỗi nhỏ rồi ngủ vài trăm mili giây **chưa chắc tạo được write timeout**.

Để kiểm thử đáng tin cậy hơn, có thể:

- Dùng network fault injector có điều khiển đường truyền.
- Cho server dừng đọc trong lúc gửi MIME body đủ lớn theo giới hạn test.
- Kiểm soát socket buffer nếu test harness hỗ trợ.
- Dùng timeout tổng của test và dừng tài nguyên khi không tái hiện được.

Không nên coi mọi IOException xảy ra trong khi gửi body là write timeout. Phải phân biệt reset connection, broken pipe và socket timeout qua nguyên nhân thật.

### 3.4. Timeout của cả thao tác gửi

Ba thuộc tính trên không nhất thiết tạo ra **một deadline tổng cho toàn bộ `send()`**. Một phiên có nhiều lần đọc/ghi và handshake, mỗi bước có thể tiêu tốn thời gian. Nếu cần giới hạn tổng thời gian xử lý một job, hãy thiết kế SLA/deadline ở tầng worker và xem cách hủy/lấy lại tài nguyên.

Không tự cho rằng `CompletableFuture.orTimeout(...)` sẽ lập tức ngắt một socket SMTP đang blocking. Timeout của future có thể chỉ đánh dấu kết quả trong khi worker thực tế vẫn chạy. Đặt timeout ở transport, giới hạn concurrency và kiểm tra hành vi cancel/thread là cần thiết.

## 4. Cấu hình timeout trong Spring Boot

Ví dụ cấu hình SMTP submission qua STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: mail-service
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"
~~~

Các giá trị trên chỉ là ví dụ. Host, port, cách cấp credential, TLS mode, timeout phải dựa trên provider và SLA thực tế. Không commit secret production vào repository; dùng cơ chế secret manager hoặc cấu hình bảo mật của môi trường.

Nếu sử dụng implicit TLS trên cổng 465, cấu hình TLS phải phù hợp; không sao chép mọi thuộc tính STARTTLS của cổng 587 rồi kết luận là đủ.

### Chú ý cú pháp YAML

Cú pháp `"[mail.smtp.timeout]"` là một cách biểu diễn khóa Jakarta Mail dưới `spring.mail.properties` trong Spring Boot configuration binding. Tránh nhầm với một property thuộc trực tiếp `spring.mail.timeout` nếu phiên bản đang dùng không định nghĩa property đó.

### Không tự gắn timeout vào từng email

`JavaMailSenderImpl` thường là một bean dùng chung, cấu hình transport áp dụng cho nhiều message. Nếu một loại thông điệp cần SLA đặc biệt, cân nhắc:

- Tách SMTP sender/route theo loại email.
- Tách worker lane/queue và chính sách retry.
- Dùng timeout đã được chấp thuận cho từng sender.
- Đảm bảo không sửa `JavaMailSenderImpl` đang dùng chung giữa các thread trong lúc gửi.

Chỉ đổi một property trong bean dùng chung ngay giữa nhiều cuộc gọi không phải một cơ chế cấu hình nguyên tử đáng tin cậy.

## 5. SMTP từ chối: lỗi tạm thời và lỗi vĩnh viễn

SMTP reply code thường được phân nhóm:

- **4xx:** lỗi tạm thời cho yêu cầu hiện tại, thường có thể thử lại sau.
- **5xx:** lỗi vĩnh viễn đối với yêu cầu hiện tại, thường không nên retry mù.

Đây là quy tắc ban đầu, **không phải một chính sách retry hoàn chỉnh**. Mã giống nhau có thể mang nguyên nhân khác nhau tùy lệnh và provider, đặc biệt với enhanced status codes.

| Ví dụ mã | Tình huống thường gặp | Chiến lược ứng dụng |
| --- | --- | --- |
| 421 | SMTP service tạm không sẵn sàng | Backoff, có thể tạm giảm tốc/đóng route |
| 450 | Mailbox tạm unavailable | Retry có giới hạn theo recipient/message |
| 451 | Local processing error | Retry tạm thời, quan sát |
| 452 | Không đủ tài nguyên | Tránh dồn tải, retry có backoff |
| 535 | Authentication credentials không hợp lệ ở một số provider | Điều tra credential/quyền; không retry tất cả email liên tục |
| 550 | Mailbox không tồn tại hoặc policy từ chối, tùy ngữ cảnh | Không retry mù; phân loại recipient/policy |
| 553 | Địa chỉ/identity bị từ chối theo cú pháp hoặc policy | Sửa địa chỉ/cấu hình |
| 554 | Transaction/message bị từ chối, tùy giai đoạn | Điều tra content/policy/server |

Ví dụ mã SMTP không cam kết mọi server sẽ phản hồi giống nhau. Enhanced status code như `5.1.1`, `4.7.1`, `5.7.1` giúp bổ sung ngữ cảnh, nhưng ứng dụng phải theo thông số của provider và thư viện transport thực tế.

### Authentication failure khác recipient refusal

Nếu SMTP trả lỗi khi AUTH, đó thường là vấn đề credential, quyền relay hoặc cơ chế xác thực. Không suppress địa chỉ người nhận chỉ vì SMTP password sai.

Nếu server trả lỗi permanent khi RCPT TO cho một địa chỉ, kết quả có thể áp dụng cho recipient đó. Không tự coi sender credential bị lộ hoặc bắt buộc rotate secret.

### Server từ chối trước DATA và sau DATA

- **RCPT TO 550:** server không nhận recipient đó; chưa có body được chuyển trong transaction này.
- **DATA 554 trước 354:** server không cho bắt đầu chuyển nội dung.
- **Sau dấu kết thúc DATA, server phản hồi 554:** server đã đọc message nhưng báo từ chối theo giao thức; cần xử lý như lỗi của lần submit.
- **Sau dấu kết thúc DATA, kết nối mất trước final reply:** client không biết chắc server đã chấp nhận hay chưa; phải cân nhắc **SUBMISSION_UNKNOWN** và khả năng duplicate.

Phân biệt hai trường hợp cuối rất quan trọng. Không thử lại ngay mọi exception phát sinh sau khi đã gửi body.

## 6. Spring Mail exception và nguyên nhân bên dưới

Ở tầng Spring, `JavaMailSender.send(...)` thường biểu diễn lỗi bằng các loại `MailException`, tùy giai đoạn và cấu trúc message:

| Lớp lỗi Spring | Ý nghĩa khái quát |
| --- | --- |
| `MailSendException` | Không gửi được một hoặc nhiều message |
| `MailAuthenticationException` | Authentication tới mail server thất bại |
| `MailParseException` | Không tạo/parse message hợp lệ |
| `MailPreparationException` | Lỗi khi chuẩn bị message với callback/preparator |
| `MailException` | Base class mà business boundary có thể bắt |

Các exception từ Jakarta Mail, SMTP provider implementation, `IOException`, `SocketTimeoutException` và các lỗi networking có thể nằm trong cause chain hoặc map failed messages. Cách bọc lỗi có thể khác tùy Spring/Jakarta Mail provider/version và vị trí lỗi. **Không viết test integration chỉ chấp nhận một subclass/cause duy nhất nếu hành vi contract của ứng dụng chỉ yêu cầu phân loại một cách an toàn.**

### Những việc cần làm khi bắt lỗi

1. Lưu internal notification ID và attempt ID.
2. Phân loại lỗi ở transport adapter.
3. Phân biệt lỗi recipient/permanent, service temporary, AUTH, content và outcome unknown.
4. Giữ exception cause cho chẩn đoán có kiểm soát.
5. Quyết định retry, suppress, dead-letter hoặc báo cần can thiệp.
6. Không log SMTP credential, OTP, reset token hoặc body có dữ liệu nhạy cảm.

### Một adapter phân loại lỗi

~~~java
public enum TransportFailureKind {
    CONNECTION_FAILED,
    READ_TIMEOUT,
    WRITE_TIMEOUT,
    TEMPORARY_SMTP,
    PERMANENT_RECIPIENT,
    AUTHENTICATION_FAILED,
    CONTENT_REJECTED,
    SUBMISSION_UNKNOWN,
    OTHER
}

public record TransportFailure(
        TransportFailureKind kind,
        String normalizedCode,
        boolean retryable,
        boolean recipientScoped
) {
}
~~~

Đây là model **do ứng dụng định nghĩa**, không phải API của Spring Mail. Mapping phải dựa trên bằng chứng từ SMTP phase, code và exception. Không suy ra `SUBMISSION_UNKNOWN` chỉ từ exception class nói chung; cần biết kết nối đứt tại bước nào hoặc dùng một gateway cho phép ghi nhận phase.

## 7. Phân biệt timeout do kết nối với server chủ động từ chối

Một server từ chối bằng reply `550` là một **protocol-level refusal**: ứng dụng đã trao đổi qua SMTP và nhận phản hồi. Một `SocketTimeoutException` khi chờ reply là **transport-level timeout**: ứng dụng chưa có phản hồi ở bước đó.

| Dấu hiệu | Connection timeout | Read timeout | SMTP 550 |
| --- | --- | --- | --- |
| TCP connection đã thiết lập? | Thường chưa | Đã | Đã |
| Server gửi mã SMTP từ chối? | Không | Không ở bước đang chờ | Có |
| Cần fault injection mạng? | Thường có | Fake server im lặng là đủ | Fake server trả 550 |
| Có thể retry? | Thường sau backoff, tùy ngữ cảnh | Tùy giai đoạn | Thường không retry mù |
| Có cần suppression recipient? | Không suy ra được | Không suy ra được | Có thể, sau phân loại |
| Kết quả submit không xác định? | Thường không vì chưa nối được | Phụ thuộc lệnh đang chờ | Nếu reply rõ thì biết bị từ chối |

Một test tốt phải nói rõ “timeout ở đâu” hoặc “server từ chối lệnh gì”. Không dùng một catch `MailException` rồi gắn mọi lỗi là SMTP timeout.

## 8. Lựa chọn SMTP test server

Có hai nhóm công cụ khác nhau:

### 8.1. SMTP capture server

Các công cụ như GreenMail, MailHog/Mailpit hoặc một SMTP server test nội bộ hữu ích để xác nhận:

- Client kết nối tới endpoint kiểm thử.
- Email được gửi và server chấp nhận.
- From, To, Subject, MIME và attachment được tạo đúng.
- Kết quả không đi ra mailbox thật.

Tuy nhiên, **không phải capture server nào cũng cho cấu hình trả 451 hoặc giữ im lặng đúng sau EHLO bằng API đơn giản**. Nếu cần fault injection có tính quyết định, dùng server scripted hoặc network proxy hỗ trợ các hành vi đó.

### 8.2. Scripted/fault-injection SMTP server

Một test server có thể được lập trình để:

- Gửi greeting 220 rồi không trả lời EHLO.
- Trả 450/550 ở RCPT TO.
- Trả 451/554 ở DATA.
- Chấp nhận body rồi đóng kết nối trước final 250.
- Đóng kết nối giữa các lệnh.
- Trì hoãn phản hồi 250 sau DATA.

Test này đi qua socket thật, nhưng không phụ thuộc SMTP provider công cộng. Nó kiểm tra chính xác tình huống đã mô phỏng và có thể chạy nhiều lần trong CI.

### 8.3. Network proxy/fault injector

Với connection timeout, packet loss, reset và write timeout, một network proxy hoặc môi trường Testcontainers có hỗ trợ điều khiển network có thể tái hiện chính xác hơn một fake SMTP server chỉ dùng ServerSocket. Ví dụ, có thể dùng một proxy có hỗ trợ latency/timeout toxic để mô phỏng một đường truyền không phản hồi.

Không giả định một port đóng sẽ gây connect timeout. Hệ điều hành có thể trả connection refused ngay, khiến test sai mục tiêu.

## 9. Cấu hình JavaMailSenderImpl trực tiếp cho integration test

Một integration test có thể tạo sender thật, trỏ đến SMTP server giả lập trên loopback interface:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class TestMailSenderFactory {

    public static JavaMailSenderImpl create(
            String host,
            int port,
            int connectTimeoutMs,
            int readTimeoutMs,
            int writeTimeoutMs) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "false");
        properties.put("mail.smtp.connectiontimeout",
                Integer.toString(connectTimeoutMs));
        properties.put("mail.smtp.timeout",
                Integer.toString(readTimeoutMs));
        properties.put("mail.smtp.writetimeout",
                Integer.toString(writeTimeoutMs));
        sender.setJavaMailProperties(properties);

        return sender;
    }
}
~~~

Với fake server chỉ hỗ trợ SMTP plaintext trên loopback, ví dụ này chủ động không dùng AUTH/STARTTLS. **Chỉ dùng cấu hình như vậy trong test cô lập.** Production phải giữ TLS và authentication theo provider, không tắt bảo mật chỉ để “sửa” một lỗi kết nối.

### Tạo message test không chứa dữ liệu thật

~~~java
import org.springframework.mail.SimpleMailMessage;

public static SimpleMailMessage sampleMessage() {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("sender@example.test");
    message.setTo("receiver@example.test");
    message.setSubject("SMTP integration test");
    message.setText("No production data");
    return message;
}
~~~

Miền `example.test` trong ví dụ là địa chỉ minh họa; test server local không chuyển thư ra Internet. Không dùng địa chỉ thật của khách hàng khi kiểm tra server từ chối.

## 10. Tạo scripted SMTP server tối giản bằng Java

Để tái hiện lỗi có tính quyết định, có thể viết một SMTP test server nhỏ dùng `ServerSocket` và một executor. Server này chỉ phục vụ test cơ bản: không hỗ trợ STARTTLS, SMTP AUTH, nhiều message trên một connection hoặc toàn bộ SMTP extension. Điểm quan trọng là nó **thực sự nói giao thức SMTP qua TCP**.

Ví dụ một file helper trong test sources:

~~~java
package com.example.mailtest;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ScriptedSmtpServer implements AutoCloseable {

    public enum Scenario {
        ACCEPT,
        SILENT_AFTER_EHLO,
        RCPT_TEMPORARY_451,
        RCPT_PERMANENT_550,
        DATA_PERMANENT_554,
        DROP_AFTER_BODY
    }

    private final ServerSocket listener;
    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();
    private final Scenario scenario;
    private final List<String> commands =
            new CopyOnWriteArrayList<>();
    private final AtomicBoolean bodyTerminated =
            new AtomicBoolean(false);
    private final Future<?> serverTask;

    public ScriptedSmtpServer(Scenario scenario) throws IOException {
        this.scenario = scenario;
        this.listener = new ServerSocket(
                0,
                1,
                InetAddress.getByName("127.0.0.1"));
        serverTask = executor.submit(this::serveOneConnection);
    }

    public int port() {
        return listener.getLocalPort();
    }

    public List<String> commands() {
        return List.copyOf(commands);
    }

    public boolean sawBodyTerminator() {
        return bodyTerminated.get();
    }

    private void serveOneConnection() {
        try (Socket client = listener.accept()) {
            client.setSoTimeout(5_000);

            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.US_ASCII));

            reply(out, "220 local.test ESMTP ready");

            String line;
            while ((line = in.readLine()) != null) {
                String upper = line.toUpperCase(Locale.ROOT);

                // Chỉ ghi command; tuyệt đối không log DATA body
                // hoặc nội dung AUTH của một test tương lai.
                commands.add(upper.startsWith("DATA")
                        ? "DATA" : line);

                if (upper.startsWith("EHLO ")
                        || upper.startsWith("HELO ")) {
                    if (scenario == Scenario.SILENT_AFTER_EHLO) {
                        // Client phải tự hết read timeout.
                        TimeUnit.SECONDS.sleep(3);
                        return;
                    }
                    reply(out, "250-local.test Hello",
                            "250 SIZE 10485760");
                } else if (upper.startsWith("MAIL FROM:")) {
                    reply(out, "250 2.1.0 Sender OK");
                } else if (upper.startsWith("RCPT TO:")) {
                    if (scenario == Scenario.RCPT_TEMPORARY_451) {
                        reply(out, "451 4.3.0 Try again later");
                    } else if (
                            scenario == Scenario.RCPT_PERMANENT_550) {
                        reply(out, "550 5.1.1 Unknown recipient");
                    } else {
                        reply(out, "250 2.1.5 Recipient OK");
                    }
                } else if (upper.equals("DATA")) {
                    if (scenario == Scenario.DATA_PERMANENT_554) {
                        reply(out,
                                "554 5.7.1 Message rejected");
                        continue;
                    }

                    reply(out, "354 End with <CRLF>.<CRLF>");
                    while ((line = in.readLine()) != null) {
                        if (line.equals(".")) {
                            bodyTerminated.set(true);
                            break;
                        }
                    }

                    if (scenario == Scenario.DROP_AFTER_BODY) {
                        // Mô phỏng mất final SMTP reply.
                        // Client không biết chắc outcome.
                        return;
                    }
                    reply(out, "250 2.0.0 Queued as test-123");
                } else if (upper.equals("RSET")) {
                    reply(out, "250 2.0.0 Reset OK");
                } else if (upper.equals("NOOP")) {
                    reply(out, "250 2.0.0 OK");
                } else if (upper.equals("QUIT")) {
                    reply(out, "221 2.0.0 Bye");
                    return;
                } else {
                    reply(out, "502 5.5.2 Command not supported");
                }
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (IOException ignored) {
            // Khi client timeout/close hoặc test shutdown:
            // đóng socket là hành vi mong đợi.
        }
    }

    private static void reply(
            BufferedWriter writer,
            String... lines) throws IOException {
        for (String line : lines) {
            writer.write(line);
            writer.write("\r\n");
        }
        writer.flush();
    }

    @Override
    public void close() throws IOException {
        listener.close();
        serverTask.cancel(true);
        executor.shutdownNow();
    }
}
~~~

### Phạm vi của helper

- Dùng cổng động `0` để hệ điều hành cấp port trống.
- Chỉ lắng nghe `127.0.0.1` và chỉ xử lý một kết nối.
- Có reply 220, 250, 354, 451, 550, 554 và 221 phù hợp với các kịch bản.
- Có kịch bản im lặng sau EHLO để thử read timeout.
- Có kịch bản đóng kết nối sau khi client gửi xong body nhưng trước final reply để mô phỏng kết quả không xác định.
- Không giữ hoặc in email body; chỉ đánh dấu đã nhận kết thúc DATA.
- Đóng listener/executor ở cuối mỗi test để tránh rò rỉ thread/port.

Đây là **fake SMTP tối giản cho mục đích học**. Nó không phải mail server RFC-compliant đầy đủ và không nên tiếp nhận lưu lượng thật. Nếu cần kiểm thử TLS handshake, SMTP AUTH, nhiều recipient hoặc policy provider-specific, hãy dùng test harness/relay có hỗ trợ tương ứng.

### Tại sao cần cleanup?

Nếu test để server thread chờ accept/read mãi, CI có thể treo hoặc bị tích lũy thread qua nhiều test. Với `try-with-resources`, `close()` được gọi ngay cả khi assertion thất bại. Test còn cần timeout tổng ở runner để bảo vệ khỏi lỗi mạng/harness bất thường.

## 11. Integration test: server chấp nhận thông điệp

Trước khi kiểm thử lỗi, cần một đường đi thành công làm baseline. Nếu test thành công cũng không chạy, các test lỗi có thể đang phát hiện cấu hình fake server sai chứ không phải hành vi cần kiểm tra.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SmtpSuccessIntegrationTest {

    @Test
    void submitsMessageWhenServerAcceptsData() throws Exception {
        try (ScriptedSmtpServer smtp =
                new ScriptedSmtpServer(
                        ScriptedSmtpServer.Scenario.ACCEPT)) {

            JavaMailSenderImpl sender =
                    TestMailSenderFactory.create(
                            "127.0.0.1",
                            smtp.port(),
                            500,
                            500,
                            500);

            assertDoesNotThrow(
                    () -> sender.send(sampleMessage()));

            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("MAIL FROM:")));
            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("RCPT TO:")));
            assertTrue(smtp.commands().contains("DATA"));
            assertTrue(smtp.sawBodyTerminator());
        }
    }
}
~~~

Các helper `sampleMessage()` và `TestMailSenderFactory` được định nghĩa ở các phần trước; có thể đưa vào một lớp test utility hoặc static import phù hợp với package trong dự án.

**Kết quả test:** JavaMailSenderImpl gửi message và nhận final success từ fake SMTP. Điều này chứng minh **submission thành công đến fake relay**, không chứng minh email đến mailbox người nhận.

## 12. Integration test: read timeout sau EHLO

Test quan trọng nhất vì có thể tái hiện ổn định mà không phụ thuộc đường mạng bên ngoài:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class SmtpReadTimeoutIntegrationTest {

    @Test
    void failsWhenServerStopsReplyingAfterEhlo() throws Exception {
        try (ScriptedSmtpServer smtp =
                new ScriptedSmtpServer(
                        ScriptedSmtpServer.Scenario.SILENT_AFTER_EHLO)) {

            JavaMailSenderImpl sender =
                    TestMailSenderFactory.create(
                            "127.0.0.1",
                            smtp.port(),
                            500,
                            250,
                            500);

            assertTimeoutPreemptively(
                    Duration.ofSeconds(5),
                    () -> assertThrows(
                            MailException.class,
                            () -> sender.send(sampleMessage())));

            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("EHLO ")
                            || cmd.startsWith("HELO ")));
            assertFalse(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("MAIL FROM:")));
        }
    }
}
~~~

Với `mail.smtp.timeout=250`, client chờ reply sau EHLO và sẽ nhận lỗi khi vượt read timeout. Giới hạn `assertTimeoutPreemptively(5s)` bảo vệ bài test khỏi kẹt quá lâu; tuy nhiên nếu phải hủy thread, nên quan sát khả năng giải phóng socket và thread trong môi trường test.

### Không assert thời gian chính xác 250 ms

Thời gian tổng chịu ảnh hưởng bởi việc khởi tạo JavaMailSender, socket, scheduling và overhead của CI. Không viết assertion kiểu “chính xác 250 ms” hoặc giới hạn quá sát. Thay vào đó kiểm tra:

1. Sender không thể gửi thành công.
2. Fake server đã nhận EHLO.
3. Chưa gửi envelope/body.
4. Test kết thúc trong một upper bound hợp lý.
5. Cause chain có bằng chứng socket read timeout khi muốn kiểm tra sâu.

Nếu test chỉ nhìn `MailException` mà không xác nhận server đã im lặng ở đúng bước, lỗi có thể xuất phát từ sai host/port chứ không phải read timeout.

## 13. Integration test: server từ chối recipient 550

Giả sử fake SMTP server chấp nhận MAIL FROM nhưng trả 550 5.1.1 cho RCPT TO:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailException;

class SmtpRecipientRefusalIntegrationTest {

    @Test
    void refusesInvalidRecipientBeforeData() throws Exception {
        try (ScriptedSmtpServer smtp =
                new ScriptedSmtpServer(
                        ScriptedSmtpServer.Scenario.RCPT_PERMANENT_550)) {

            var sender = TestMailSenderFactory.create(
                    "127.0.0.1",
                    smtp.port(),
                    500, 500, 500);

            assertThrows(MailException.class,
                    () -> sender.send(sampleMessage()));

            assertTrue(smtp.commands().stream()
                    .anyMatch(cmd -> cmd.startsWith("RCPT TO:")));
            assertFalse(smtp.commands().contains("DATA"));
            assertFalse(smtp.sawBodyTerminator());
        }
    }
}
~~~

Test xác nhận:

- Có phiên SMTP thực.
- Server đã nhận lệnh RCPT TO.
- Server từ chối recipient trước khi client gửi body.
- JavaMailSender phản hồi bằng exception.
- Ứng dụng có thể phân loại đây là lỗi recipient-scoped nếu có đủ bằng chứng mã/response.

Không tự khẳng định mọi SMTP 550 là “địa chỉ không tồn tại” nếu provider trả 550 vì chính sách, DNS hoặc sender identity. Test này dùng response **550 5.1.1 Unknown recipient** nên mô phỏng cụ thể lỗi recipient invalid.

## 14. Integration test: server tạm từ chối recipient 451

Một phản hồi 451 ở RCPT TO có thể biểu thị lỗi tạm thời. Lần gửi đó chưa được accepted cho recipient, nhưng business layer có thể quyết định retry với backoff.

~~~java
@Test
void temporaryRecipientRefusalDoesNotSubmitData() throws Exception {
    try (ScriptedSmtpServer smtp =
            new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.RCPT_TEMPORARY_451)) {

        var sender = TestMailSenderFactory.create(
                "127.0.0.1",
                smtp.port(),
                500, 500, 500);

        assertThrows(MailException.class,
                () -> sender.send(sampleMessage()));

        assertTrue(smtp.commands().stream()
                .anyMatch(cmd -> cmd.startsWith("RCPT TO:")));
        assertFalse(smtp.commands().contains("DATA"));
    }
}
~~~

Điều cần kiểm tra ở tầng ứng dụng:

- **Không** đánh dấu email SUBMITTED.
- Có thể chuyển outbox sang RETRY_PENDING nếu classifier xác định lỗi tạm thời.
- Tăng attempt count **một lần** cho lệnh submit đã thực hiện.
- Lưu mã 451/enhanced status nếu đọc được.
- Có `nextAttemptAt` trong tương lai, không retry tức thời trong vòng lặp nóng.
- Giới hạn số lần thử, tuổi thông điệp và tốc độ retry.

Không viết integration test yêu cầu hệ thống *luôn* retry 451 ở mọi trường hợp; policy có thể còn phụ thuộc recipient validity, SLA, provider, loại email và retry budget.

## 15. Integration test: DATA bị từ chối

Khi RCPT TO được chấp nhận nhưng server trả 554 ở lệnh DATA, message chưa được gửi dưới dạng body:

~~~java
@Test
void rejectsDataCommandAfterAcceptingRecipient() throws Exception {
    try (ScriptedSmtpServer smtp =
            new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.DATA_PERMANENT_554)) {

        var sender = TestMailSenderFactory.create(
                "127.0.0.1",
                smtp.port(),
                500, 500, 500);

        assertThrows(MailException.class,
                () -> sender.send(sampleMessage()));

        assertTrue(smtp.commands().contains("DATA"));
        assertFalse(smtp.sawBodyTerminator());
    }
}
~~~

Đây là lỗi **server từ chối ngay ở lệnh DATA**. Không nhầm với server đọc toàn bộ email rồi trả 554 **sau dấu kết thúc DATA**; hai tình huống khác nhau về dữ liệu đã chuyển, log và khả năng biết kết quả.

### Vì sao cần test hai vị trí?

Nếu adapter phân loại lỗi “thấy 554” rồi luôn coi là content-related permanent failure, đó có thể là chính sách nghiệp vụ phù hợp với provider cụ thể. Nhưng adapter vẫn nên ghi phase/recipient và không suy ra nội dung thực đã được server đọc nếu lỗi xuất hiện trước 354.

Một test bổ sung có thể cho fake server trả 354, đọc body tới dấu chấm, sau đó trả 554. Kết quả là **SMTP reply từ chối rõ ràng**, khác với mất reply hoàn toàn.

## 16. Integration test: ngắt kết nối sau DATA

Tình huống nguy hiểm nhất cho retry/idempotency:

~~~text
Client                              SMTP relay
  |--------- DATA ----------------->|
  |<-------- 354 -------------------|
  |--------- MIME body ------------>|
  |--------- "." ------------------>|
  |                                | Có thể đã xử lý message
  |          connection closed     X
  |                                |
  | Không nhận final 250 / 4xx / 5xx
~~~

Server test chỉ giả lập **mất final response**; nó không chứng minh một relay production đã chấp nhận message. Điều quan trọng là ứng dụng **không biết chắc outcome**.

~~~java
@Test
void treatsLostFinalResponseAsUncertainOutcome() throws Exception {
    try (ScriptedSmtpServer smtp =
            new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.DROP_AFTER_BODY)) {

        var sender = TestMailSenderFactory.create(
                "127.0.0.1",
                smtp.port(),
                500, 500, 500);

        assertThrows(MailException.class,
                () -> sender.send(sampleMessage()));

        assertTrue(smtp.commands().contains("DATA"));
        assertTrue(smtp.sawBodyTerminator());

        // Business assertion: khi transport adapter biết
        // rằng final reply bị mất sau DATA,
        // policy không retry mù ngay lập tức.
    }
}
~~~

Ở tầng dịch vụ, nên có trạng thái như `SUBMISSION_UNKNOWN`, lưu attempt ID và provider correlation, rồi đối soát hoặc xử lý theo chính sách duplicate. Không đánh dấu SUBMITTED chỉ vì server đã đọc body; không đánh dấu FAILED chắc chắn rồi lập tức gửi bản mới nếu có khả năng relay đã nhận.

**Giới hạn thực tiễn:** `JavaMailSenderImpl` không cung cấp API cấp cao luôn cho biết chính xác “đã gửi dấu kết thúc DATA rồi nhưng mất final reply”. Nếu cần phân loại tuyệt đối theo phase, hãy thiết kế transport gateway có instrumented protocol-level result hoặc dùng provider API có idempotency/status lookup. Test ở tầng policy có thể inject một `SUBMISSION_UNKNOWN` outcome đã được transport adapter phát hiện đáng tin, thay vì yêu cầu Spring Mail tự suy ra mọi trường hợp.

## 17. Kịch bản connection refused và connection timeout

### Connection refused

Trường hợp không có process nào lắng nghe tại đích, hệ điều hành có thể trả về lỗi từ chối kết nối rất nhanh:

~~~text
Client -> 127.0.0.1:port
        <- TCP RST / connection refused
~~~

Test có thể trỏ tới một port local được kiểm soát là không có listener, nhưng việc “tìm port trống rồi đóng socket” có khả năng race vì một process khác có thể chiếm port trước khi test dùng. Vì vậy, hãy coi đó là một integration test phù hợp trong môi trường cô lập, không phải bằng chứng timeout deterministic.

Ví dụ mục tiêu:

~~~java
@Test
void reportsConnectionFailureWhenNoSmtpListenerExists() {
    int isolatedUnusedPort = getPortFromControlledTestHarness();
    var sender = TestMailSenderFactory.create(
            "127.0.0.1",
            isolatedUnusedPort,
            200, 300, 300);

    assertThrows(MailException.class,
            () -> sender.send(sampleMessage()));
}
~~~

`getPortFromControlledTestHarness()` là helper do test infrastructure cung cấp, không có sẵn trong JUnit. Nó cần đảm bảo môi trường port ổn định hoặc được sandbox hóa. Trường hợp này có thể dẫn tới lỗi **connection refused**, không chứng minh `mail.smtp.connectiontimeout` đã hoạt động.

### Connection timeout

Muốn kiểm tra **connect timeout** thực sự, nên sử dụng một đường truyền mà kết nối bị drop/blackhole và không nhận phản hồi trong khoảng deadline. Điều này phụ thuộc OS và network; một địa chỉ IP “không tồn tại” có thể trả `Network unreachable` ngay thay vì timeout.

Quy trình đúng:

1. Tạo network test environment có fault injector.
2. Cấu hình proxy/route nhận traffic nhưng không hoàn tất kết nối theo cách có thể tái hiện.
3. Đặt `mail.smtp.connectiontimeout` đủ ngắn cho CI.
4. Xác nhận lỗi là connect timeout (không phải DNS failure/refused).
5. Đo upper bound tổng bằng timeout của test runner.
6. Cleanup proxy/network sau mỗi test.

**Không giả lập connect timeout bằng cách cho fake SMTP server chấp nhận TCP rồi im lặng sau EHLO**; đó là read timeout.

## 18. Test write timeout có tính kiểm soát

Write timeout khó tái hiện ổn định hơn read timeout vì dữ liệu ứng dụng ghi có thể được TCP buffer nhận ngay. Nếu server không đọc nữa nhưng dữ liệu còn vừa bộ đệm, thao tác write vẫn có thể thành công trong một thời gian.

### Cách xây dựng kịch bản

1. Fake SMTP chấp nhận kết nối, EHLO, MAIL FROM, RCPT TO và trả 354 cho DATA.
2. Sau 354, server **ngừng đọc socket**.
3. Client bắt đầu gửi nội dung MIME lớn có giới hạn hợp lý trong môi trường test.
4. `mail.smtp.writetimeout` được cấu hình đủ nhỏ.
5. Một transport/network fault injector có thể giới hạn buffer hoặc băng thông nếu cần.
6. Test ghi nhận exception/cause và bảo đảm worker giải phóng tài nguyên.

### Điều không nên làm

- Không gửi hàng gigabyte dữ liệu chỉ để ép socket timeout.
- Không cho test chạy vô hạn để chờ OS buffer đầy.
- Không yêu cầu thời điểm lỗi chính xác tới mili giây.
- Không nhầm lỗi `Broken pipe` do server chủ động đóng connection với write timeout.
- Không dùng SMTP provider công cộng cho thí nghiệm tắc nghẽn đường truyền.

Một test write timeout đạt yêu cầu cần có dấu hiệu fault đã được kích hoạt đúng và exception đến từ write operation. Nếu công cụ không cung cấp điểm quan sát đó, kết quả chỉ chứng minh “gửi thất bại dưới điều kiện network chậm”, chưa chứng minh timeout property.

### Giới hạn của implementation

Một số SMTP provider implementation có thể dùng thread/timer nội bộ cho write timeout. Vì vậy cần kiểm tra hành vi tài nguyên khi nhiều lần write timeout: thread có được dọn không, socket có đóng không, future/worker có chờ kéo dài không. Không giả định hủy một `Future` là đủ để đóng mọi kết nối đang block.

## 19. Kiểm thử server từ chối ở MAIL FROM

Lỗi ở MAIL FROM liên quan envelope sender, quyền relay hoặc policy. Nó không phải bằng chứng địa chỉ người nhận không hợp lệ.

Ví dụ SMTP script:

~~~text
220 local.test ESMTP ready
C: EHLO app.local
S: 250 local.test
C: MAIL FROM:<notifications@example.test>
S: 553 5.7.1 Sender not authorized
~~~

Một test cần xác nhận:

- Client đã gửi MAIL FROM.
- Server trả mã từ chối ở lệnh đó.
- Không chuyển sang DATA.
- Service phân loại sender/account policy error.
- Không suppress recipient.
- Có alert nếu lỗi ảnh hưởng mọi thông điệp cùng SMTP identity.

Để thêm kịch bản vào ScriptedSmtpServer, có thể mở rộng enum với `MAIL_FROM_REJECT_553` và trả reply tương ứng trong nhánh MAIL FROM. Nếu muốn kiểm tra lỗi “sender address invalid” và “sender not authorized” riêng, dùng enhanced status code và text được provider định nghĩa trong fixture.

## 20. Kiểm thử từ chối SMTP AUTH

Trong production, xác thực SMTP thường diễn ra sau khi thiết lập kết nối bảo mật theo cấu hình provider. Khi username/password sai hoặc account không có quyền, server có thể trả mã như `535`.

### Mục tiêu kiểm thử

- Bắt được authentication failure ở đúng bước AUTH.
- Phân loại lỗi ở **cấp SMTP account/provider**, không phải một recipient.
- Không tiếp tục gửi MAIL FROM, RCPT TO, DATA sau AUTH failure.
- Tạm dừng hoặc giới hạn retry của lane gửi nếu lỗi ảnh hưởng nhiều job.
- Không lộ password/token trong log và telemetry.
- Giữ email giao dịch trong outbox để xử lý sau khi credential phục hồi.
- Không downgrade từ STARTTLS sang plaintext để “thử lại”.

### Vì sao scripted server đơn giản chưa đủ?

Helper trước đó không triển khai STARTTLS hoặc SMTP AUTH. Nếu chỉ thêm reply 535 cho một câu lệnh bất kỳ, test không thực sự xác nhận quá trình AUTH chuẩn. Khi cần test đầy đủ, dùng SMTP test server hỗ trợ SASL AUTH/TLS, một fake server triển khai đúng phần giao thức cần thiết, hoặc môi trường staging được phép.

### Ví dụ cách tổ chức test service

~~~java
@Test
void authenticationFailureDoesNotSuppressRecipient() {
    // Transport adapter trả kết quả đã được
    // phân loại từ SMTP AUTH trong test tích hợp.
    when(transport.submit(any()))
            .thenThrow(new SmtpCredentialRejectedException(
                    "AUTH_REJECTED"));

    assertThrows(SmtpCredentialRejectedException.class,
            () -> dispatcher.dispatch(notification));

    verify(providerHealthService)
            .recordCredentialFailure("primary-smtp");
    verifyNoInteractions(recipientSuppressionRepository);
}
~~~

Đây là test service dùng mock adapter **bổ sung** cho test SMTP protocol, không thay thế test TLS/AUTH thật. Những tên lớp như SmtpCredentialRejectedException là do ứng dụng định nghĩa.

### Phân biệt AUTH 535 và từ chối recipient 550

Nếu toàn bộ notification cùng thất bại vì credential sai, retry từng email sẽ tạo bão xác thực mà không giúp phục hồi. Cần tạm dừng provider lane, alert, refresh/rotate credential theo chính sách và drain backlog sau khi xác minh AUTH thành công. Ngược lại, recipient 550 ở một địa chỉ không nên tự động làm dừng mọi email của provider.

## 21. Kiểm thử TLS và xác thực certificate

Các lỗi bảo mật có thể trông giống “không gửi được email”, nhưng không nên được xử lý bằng cách tắt TLS hoặc bật trust-all trong production.

Các kịch bản tích hợp:

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| SMTP server yêu cầu STARTTLS nhưng client không bật | Gửi bị từ chối/cấu hình bị phát hiện |
| Client yêu cầu STARTTLS nhưng server không advertise | Không âm thầm gửi plaintext |
| Certificate không hợp lệ | Kết nối bảo mật thất bại theo trust policy |
| Hostname không khớp certificate | Hostname verification chặn kết nối |
| Server chỉ hỗ trợ implicit TLS | Client dùng đúng TLS mode và port |
| TLS handshake bị treo | Transport timeout và resource cleanup phù hợp |
| Credential sai sau TLS | Lỗi AUTH được phân loại riêng |

Với Spring/Jakarta Mail, thường cấu hình `mail.smtp.starttls.enable`, `mail.smtp.starttls.required`, `mail.smtp.ssl.checkserveridentity` cho STARTTLS theo provider. Test không được “sửa” lỗi chứng chỉ bằng cách đặt `mail.smtp.ssl.trust=*` ở môi trường production.

**Test TLS thực sự cần một SMTP server có chứng chỉ và TLS handshake**. Fake server plaintext ở phần trước không có khả năng này. Dùng certificate test và trust store dành riêng cho test nếu cần, không vô hiệu hóa xác thực để biến bài kiểm tra bảo mật thành kiểm tra kết nối thường.

## 22. Kiểm thử nhiều người nhận và partial refusal

Một MIME message có thể chứa To/Cc/Bcc nhiều recipient. SMTP server có thể trả:

~~~text
C: RCPT TO:<a@example.test>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<b@example.test>
S: 550 5.1.1 Unknown recipient
~~~

Đây là tình huống **mixed acceptance**. Kết quả gửi phụ thuộc SMTP transport implementation, cấu hình và chính sách partial-send; không nên suy ra chỉ từ việc `send()` ném exception rằng mọi người nhận đều bị từ chối.

### Thuộc tính liên quan

Jakarta Mail SMTP có thuộc tính `mail.smtp.sendpartial`. Trong các triển khai phổ biến, cấu hình này ảnh hưởng việc có tiếp tục gửi tới những recipient được chấp nhận khi một phần recipient bị từ chối hay không.

Test nên chạy các biến thể cấu hình được sản phẩm hỗ trợ và quan sát:

- Server nhận bao nhiêu lệnh RCPT TO.
- Có tiếp tục DATA hay không.
- Message có được accepted cho các recipient hợp lệ không.
- Exception/failed address list được đưa ra như thế nào.
- Ứng dụng tạo trạng thái **theo recipient**, không chỉ một status chung cho message.

Không nên mặc định `sendpartial=true` cho tất cả ứng dụng mà không hiểu tác động riêng tư/duplicate và logic nhận kết quả. Với email giao dịch cá nhân hóa, gửi một message cho một recipient thường dễ theo dõi hơn.

### Một test matrix

| Tình huống | Kỳ vọng cần xác định |
| --- | --- |
| Tất cả RCPT accepted | DATA và final response thành công |
| Tất cả RCPT permanent refused | Không đánh dấu bất kỳ recipient nào submitted |
| Một RCPT accepted, một permanent refused | Theo dõi partial behavior đúng cấu hình |
| Một RCPT temporary refused | Chỉ retry recipient phù hợp, nếu transport cho phép |
| Server accept DATA nhưng kết nối mất | Không tự gửi lại mọi recipient khi outcome chưa chắc chắn |

Không dùng `MailSendException` như một boolean “all failed” nếu underlying transport đã gửi được một phần. Cần đọc kỹ exception/result metadata và thử nghiệm chính xác với implementation đang dùng.

## 23. Kiểm thử phản hồi sau DATA so với mất final reply

Hai kịch bản dễ nhầm:

**A. Server trả 554 sau body:**

~~~text
C: DATA
S: 354 Continue
C: [headers and body]
C: .
S: 554 5.7.1 Message rejected
~~~

Client đã nhận một **kết quả từ chối rõ ràng** cho transaction. Theo semantics SMTP, server không chấp nhận trách nhiệm giao message này; business service có thể xử lý như lỗi phản hồi.

**B. Server không trả final response:**

~~~text
C: DATA
S: 354 Continue
C: [headers and body]
C: .
X: Connection closes before final reply
~~~

Ứng dụng **không biết** relay đã nhận message hay chưa. Đây là cửa sổ không chắc chắn và có nguy cơ duplicate nếu retry.

### Test fixture cần khác nhau

Trong helper:

- Scenario DATA_PERMANENT_554 hiện tại từ chối **trước** khi gửi body.
- Scenario DROP_AFTER_BODY mô phỏng **sau** body nhưng không có reply.

Để kiểm thử A, cần thêm một scenario ví dụ `REJECT_AFTER_BODY_554`: sau khi đọc dấu chấm kết thúc DATA, trả `554 5.7.1 Message rejected` thay cho 250.

Không thay thế A bằng B rồi kết luận lỗi có cùng ý nghĩa. Cần lưu **SMTP phase** hoặc bằng chứng tương đương trong transport adapter.

## 24. Spring Boot integration test với ApplicationContext

Tạo `JavaMailSenderImpl` trực tiếp kiểm tra transport thật, nhưng chưa chứng minh Spring Boot auto-configuration, property binding và bean injection hoạt động đúng. Với dự án sử dụng Spring Boot, nên có thêm một integration test chạy `ApplicationContext` và trỏ bean được auto-config tới SMTP fake.

Ví dụ khung test:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
class BootMailConfigurationIntegrationTest {

    private static final ScriptedSmtpServer SMTP = startServer();

    @Autowired
    JavaMailSender sender;

    private static ScriptedSmtpServer startServer() {
        try {
            return new ScriptedSmtpServer(
                    ScriptedSmtpServer.Scenario.ACCEPT);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    @DynamicPropertySource
    static void configureMail(DynamicPropertyRegistry properties) {
        properties.add("spring.mail.host",
                () -> "127.0.0.1");
        properties.add("spring.mail.port", SMTP::port);
        properties.add("spring.mail.properties[mail.smtp.auth]",
                () -> "false");
        properties.add("spring.mail.properties[mail.smtp.timeout]",
                () -> "500");
        properties.add("spring.mail.properties[mail.smtp.connectiontimeout]",
                () -> "500");
        properties.add("spring.mail.properties[mail.smtp.writetimeout]",
                () -> "500");
    }

    @Test
    void autoConfiguredSenderSubmitsToLocalSmtp() {
        sender.send(sampleMessage());
    }

    @AfterAll
    static void closeServer() throws IOException {
        SMTP.close();
    }
}
~~~

Code minh họa ý tưởng, giả định dự án đã có Spring Boot Mail starter và JUnit/Spring Boot test dependencies phù hợp. Cần điều chỉnh package/import của helper và xác minh phiên bản Boot đang dùng bind các key `spring.mail.properties[...]` đúng như cấu hình. Vì fake server chỉ nhận một connection, class ví dụ chỉ có một test; nếu có nhiều test, cần hỗ trợ nhiều connection hoặc tạo server mỗi lượt với context isolation.

### Tách các lớp test cho dễ điều tra

- **Transport-focused test:** khởi tạo JavaMailSenderImpl trực tiếp, mỗi test một fake server riêng.
- **Boot configuration test:** khởi động ApplicationContext để kiểm tra `spring.mail.*` và wiring.
- **Business integration test:** thêm database/outbox và mail dispatcher để kiểm tra retry/transaction.

Không bắt ApplicationContext restart hàng trăm lần chỉ để mô phỏng nhiều SMTP code nếu bài test cấp transport đã đủ. Giữ số lượng context tests cần thiết cho cấu hình và component wiring thực sự.

## 25. Kiểm thử timeout trong transaction nghiệp vụ

Một lỗi thiết kế phổ biến:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailSender.send(buildConfirmation(order));
    return order;
}
~~~

Nếu SMTP read timeout kéo dài vài giây, transaction database bị giữ mở. Nếu relay đã accepted email nhưng transaction rollback sau đó, người nhận có thể nhận xác nhận cho một đơn hàng không tồn tại.

### Mô hình bền vững hơn

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    outboxRepository.save(EmailOutboxMessage.pending(
            "ORDER_CONFIRMED",
            order.getId(),
            order.getCustomerId()));
    return order;
}
~~~

Sau khi commit, worker đọc outbox và submit qua JavaMailSender. Một test database + fake SMTP cần xác nhận:

1. Transaction tạo đơn hàng và outbox commit cùng nhau.
2. Khi SMTP timeout, đơn hàng vẫn tồn tại.
3. Outbox record không bị xóa.
4. Worker ghi trạng thái RETRY_PENDING hoặc trạng thái phù hợp.
5. `nextAttemptAt` được lưu để retry sau, không block HTTP request.
6. Sau khi SMTP phục hồi, worker submit theo limiter.
7. Nếu submission unknown, không retry mù.

Đây là nội dung integration test **về cách ứng dụng phản ứng với transport**, bổ sung cho test JavaMailSenderImpl ở các phần trước.

## 26. Phân loại lỗi vào retry, failed và unknown

Một ứng dụng có thể dùng policy:

~~~java
public enum MailDeliveryAction {
    RETRY_LATER,
    FAIL_PERMANENT,
    HOLD_FOR_CREDENTIAL_FIX,
    RECONCILE_UNKNOWN,
    SUPPRESS_RECIPIENT,
    IGNORE_OR_DEFER
}
~~~

Ví dụ mapping:

| Bằng chứng | Hành động gợi ý |
| --- | --- |
| Connection timeout trước kết nối | Retry có backoff, nếu còn hạn |
| Read timeout sau EHLO | Retry tạm thời; chưa gửi body |
| Temporary RCPT 451 | Retry theo recipient/message policy |
| Permanent RCPT 550 5.1.1 | Có thể suppress recipient, không retry mù |
| AUTH 535 với credential chung | Hold provider lane, sửa credential |
| MAIL FROM policy rejected | Hold/config fix, không suppress recipient |
| DATA 554 rõ ràng | Điều tra content/policy; có thể permanent |
| Mất final reply sau DATA | RECONCILE_UNKNOWN |
| Email hết hạn | Không gửi, EXPIRED |
| Marketing bị unsubscribe | SUPPRESSED, không gọi SMTP |
| Thiếu rate limit permit | Defer, không tính SMTP attempt |

Chính sách cụ thể cần dựa trên domain nghiệp vụ, provider semantics và kết quả transport. Không dùng `instanceof MailSendException` đơn thuần để quyết định retry hay suppress, vì cùng subclass có thể bao nhiều nguyên nhân.

### Không biến lỗi hạ tầng thành lỗi địa chỉ

Nếu SMTP không phản hồi do network, không được cập nhật `recipient.valid=false`. Nếu credential sai, không được suppress mọi recipient. Nếu 550 do sender policy, không được ghi nhận là mailbox không tồn tại. **Phân loại sai có thể làm mất email hợp lệ lâu dài**.

## 27. Exponential backoff và giới hạn retry sau timeout

Một timeout thường có khả năng phục hồi, nhưng retry không nên lặp ngay:

\[
\text{delay}_n = \min(\text{maximum},\,\text{initial} \times 2^{n-1}) + \text{jitter}
\]

Ví dụ chính sách thử nghiệm:

| Lần thử | Mốc chờ minh họa |
| --- | --- |
| 1 | Gửi ngay khi job được claim |
| 2 | Sau khoảng 30–45 giây |
| 3 | Sau khoảng 1–2 phút |
| 4 | Sau khoảng 3–5 phút |
| Hết maxAttempts | DEAD_LETTER hoặc xử lý theo policy |

Giá trị chỉ minh họa. Hạn mức provider, TTL OTP/reset link và SLA của giao dịch quyết định thời gian thực tế. Jitter nên có nguồn ngẫu nhiên kiểm soát được trong test; không assert một timestamp chính xác khi production dùng random.

### Những bất biến nên được kiểm thử

- Một lần timeout không tạo nhiều lệnh gửi tức thời.
- `nextAttemptAt` nằm trong tương lai theo backoff policy.
- Không vượt maxAttempts.
- Không retry khi hết hạn.
- Retry cũng phải qua rate limiter và concurrency gate.
- Worker crash/restart không reset lịch và attempts.
- SMTP unknown không tự động vào cùng nhánh “retry safe” với lỗi trước MAIL FROM.

### Tránh retry lồng nhiều lớp

Nếu Spring Retry thử 3 lần trong adapter và outbox retry 5 lần, có thể tạo 15 lần gọi SMTP cho một message. Phải định nghĩa rõ số lần gọi transport thực và đặt ngân sách tổng. Test nên đếm **physical SMTP attempts**, không chỉ outbox attempt counter.

## 28. Ma trận kiểm thử timeout và server từ chối

Khi thêm hoặc thay SMTP provider, hãy giữ một bộ kịch bản tối thiểu. Các tình huống không nên chỉ được mô phỏng bằng một exception chung.

| ID | Fault được đưa vào | Giai đoạn | Kỳ vọng chính |
| --- | --- | --- | --- |
| T01 | Server trả final 250 | Sau DATA | JavaMailSender submit thành công |
| T02 | TCP connection refused | Connect | Ghi lỗi kết nối, không coi là SMTP response |
| T03 | TCP packet bị drop | Connect | Connection timeout trong ngưỡng |
| T04 | Server không gửi 220 greeting | Greeting | Read timeout |
| T05 | Server im lặng sau EHLO | EHLO | Read timeout; chưa gửi body |
| T06 | Server im lặng sau MAIL FROM | Envelope | Read timeout; không suy ra recipient invalid |
| T07 | Server ngừng đọc body | DATA write | Write timeout/resource cleanup theo khả năng harness |
| T08 | Server trả 421 | Greeting/command | Lỗi dịch vụ tạm thời, backoff |
| T09 | Server trả 451 | RCPT TO | Temporary recipient refusal, retry policy |
| T10 | Server trả 550 5.1.1 | RCPT TO | Permanent recipient failure, không retry mù |
| T11 | Server trả 553 | MAIL FROM | Sender/policy error, không suppress recipient |
| T12 | Server trả 554 | DATA trước 354 | Refusal trước khi chuyển body |
| T13 | Server trả 554 | Sau dấu kết thúc DATA | Explicit rejection sau body |
| T14 | Server đóng connection | Sau dấu kết thúc DATA, trước reply | Outcome unknown, không tự resend |
| T15 | Credential không hợp lệ | AUTH | Lỗi cấp provider/account, tạm dừng retry hàng loạt |
| T16 | STARTTLS bị từ chối/không hỗ trợ | TLS negotiation | Không downgrade khi TLS required |
| T17 | Certificate sai hostname | TLS handshake | Kết nối bị chặn theo chính sách |
| T18 | Một RCPT accepted, một bị 550 | Nhiều recipient | Partial-send behavior được đo đúng |
| T19 | Timeout rồi process restart | Outbox | Retry schedule/attempts không mất |
| T20 | Nhiều worker cùng xử lý timeout | Worker/outbox | Không vượt concurrency/quota, claim có lease |
| T21 | Hết token rate limit trước send | Dispatch gate | Defer mà không tạo SMTP attempt |
| T22 | SMTP lỗi 4xx rồi phục hồi | Retry | Backoff/jitter, không burst hàng nghìn jobs |
| T23 | Có email đã SUBMITTED và job được replay | Replay | Không gửi lại tùy tiện |
| T24 | Complaint/unsubscribe khi chờ retry | Business policy | Không gửi marketing bị suppress |
| T25 | Monitoring/logging bật khi lỗi | Observability | Có error code/correlation, không lộ secret/body |
| T26 | Server rất chậm nhưng chưa timeout | Performance | Không giữ transaction nghiệp vụ quá lâu |

Những kịch bản thuộc TLS, AUTH, network blackhole và multi-recipient cần fixture/server hỗ trợ đúng fault. Không cố ép fake server tối giản làm mọi thứ rồi coi kết quả tương đương production provider.

### Test nào cần chạy ở đâu?

**Mỗi commit/CI nhanh:**

- Đường gửi thành công.
- Read timeout sau EHLO.
- RCPT 451/550.
- DATA 554 và mất final reply.
- Unit test retry/suppression/classifier.

**Integration suite sâu hơn:**

- TLS/AUTH bằng SMTP test server phù hợp.
- Database/outbox transaction, lease và restart.
- Nhiều recipient/partial acceptance.
- Network proxy cho connect/write timeout.

**Staging có kiểm soát:**

- Kết nối provider thật đã được cấp phép.
- SMTP credentials, STARTTLS/certificate, From authorization.
- Quota/rate-limit theo hợp đồng thử nghiệm.
- Provider-specific enhanced codes và bounce events.

Không bắt đầu load test bằng cách gửi tới mailbox thật hoặc dùng credential production.

## 29. Quan sát trạng thái SMTP trong bài test

Một test tốt cần bằng chứng ở nhiều tầng:

| Tầng | Bằng chứng nên quan sát |
| --- | --- |
| Fake SMTP server | Đã nhận connect, EHLO, MAIL FROM, RCPT TO, DATA chưa |
| Transport | Method send trả bình thường hay ném lỗi |
| Classifier | Failure kind/code/recipient scope |
| Worker | Attempts, nextAttemptAt, lease owner, trạng thái cuối |
| Database | Domain transaction có commit, outbox còn record |
| Monitoring | Error count, timeout latency, SMTP in-flight |
| Business | Response hiển thị cho user và khả năng thử lại/kênh thay thế |

Ví dụ, một test read timeout chỉ assert lỗi SMTP nhưng không kiểm tra server đã nhận EHLO có thể thực tế đang thất bại vì port sai. Một test permanent RCPT refusal chỉ assert exception nhưng không kiểm tra recipient suppression có thể bỏ sót chính sách vận hành.

### Nên đo và ghi log điều gì?

Một log cấu trúc có thể chứa:

~~~json
{
  "event": "mail_submission_failed",
  "notificationId": "notif-184",
  "attemptId": "attempt-3",
  "providerKey": "smtp-primary",
  "stage": "RCPT_TO",
  "failureKind": "PERMANENT_RECIPIENT",
  "smtpReplyCode": "550",
  "enhancedStatusCode": "5.1.1",
  "retryable": false
}
~~~

Đây là JSON minh họa do ứng dụng tự định nghĩa. Không ghi SMTP password, access token, OTP, reset link, nội dung MIME hoặc nguyên văn phản hồi server chứa dữ liệu cá nhân không cần thiết.

### Cause chain không phải contract hoàn toàn ổn định

Một integration test có thể cần xem underlying `SocketTimeoutException`, nhưng vị trí cause có thể khác theo phiên bản Jakarta Mail và pha giao thức. Trong production adapter nên chuẩn hóa thành mã lỗi nội bộ ổn định, sau đó kiểm tra:

- Test transport xác nhận có timeout thực ở fake server.
- Adapter test xác nhận cause tương ứng được mapping.
- Business test chỉ assert policy ổn định như RETRY_PENDING hoặc SUBMISSION_UNKNOWN.

Tách các lớp này giúp nâng phiên bản framework/SMTP provider mà không làm toàn bộ test nghiệp vụ phụ thuộc class cụ thể trong một thư viện.

## 30. Thiết kế timeout phù hợp với SLA

Các timeout quá dài làm tăng thời gian chờ và số thread bị giữ; quá ngắn có thể tạo nhiều lỗi giả khi server bình thường nhưng hơi chậm.

Ví dụ giả định:

- Connection timeout: 3 giây.
- Read timeout: 5 giây.
- Write timeout: 5 giây.
- Worker concurrency: 4.
- HTTP request không chờ email giao dịch sau commit; worker xử lý nền.

Các con số chỉ là ví dụ. Khi chọn cấu hình thật, cần xem:

- SLO của email OTP hoặc reset link.
- Thời gian phản hồi quan sát được từ provider.
- Kích thước email/attachment.
- Khả năng latency cao ở môi trường network.
- Retry budget và quota SMTP.
- Số lượng worker, số connection tối đa.
- Tổng deadline nghiệp vụ và expiry của thông điệp.

### Timeout không phải deadline toàn cục

Giả sử mỗi lệnh đọc timeout sau 5 giây, nhưng SMTP transaction có nhiều lệnh đọc. Tổng thời gian thực thi có thể lớn hơn 5 giây. Một job có deadline tổng cần ghi lại lúc bắt đầu và có cơ chế dừng/đánh dấu trạng thái phù hợp nếu hết thời gian.

Nếu toàn bộ quá trình sending được đưa vào `@Async`, HTTP request có thể kết thúc nhanh, nhưng không có nghĩa mail worker được phép kẹt vô hạn. Timeout vận chuyển, bounded executor và queue vẫn rất quan trọng.

### Retry không được vượt expiry

OTP có thể có thời hạn ngắn. Nếu lần gửi đầu timeout và backoff đẩy lần retry đến sau khi token hết hạn, gửi email chứa token cũ gây trải nghiệm sai. Worker cần kiểm tra `expiresAt` ngay trước mỗi attempt.

Email giao dịch có thể được phép retry lâu hơn, nhưng cần cảnh báo khi vượt SLA. Email marketing có thể bị hủy khi chiến dịch kết thúc. Không dùng cùng retry policy cho mọi loại.

## 31. Kiểm thử khả năng phục hồi của worker sau timeout

Một lỗi timeout có thể tạo ra hai vấn đề:

1. Thông điệp không được gửi.
2. Thread/connection/lease không được giải phóng, khiến các message tiếp theo bị kẹt.

Integration test nên xác nhận **hệ thống còn xử lý message khác sau khi một gửi bị timeout**.

### Kịch bản phục hồi

1. Job A gặp read timeout.
2. Worker ghi retry state cho A.
3. Concurrency slot được release.
4. Job B được claim và gửi thành công qua một fake SMTP session khác.
5. Worker tiếp tục hoạt động; không có thread/connection leak rõ ràng.
6. Khi đến hạn, A được retry theo policy.

Nếu server test chỉ hỗ trợ một connection, dùng hai instance server hoặc mở rộng fake harness nhận nhiều connection và có script theo phiên. Không dùng cùng một fake server đã đóng nếu nó chỉ accept một lần.

### Đừng quên finally

Ví dụ dispatch có concurrency gate:

~~~java
if (!smtpSemaphore.tryAcquire()) {
    outbox.defer(notificationId);
    return;
}

try {
    mailSender.send(message);
    outbox.markSubmitted(notificationId);
} catch (MailException exception) {
    outbox.recordTransportFailure(
            notificationId, exception);
} finally {
    smtpSemaphore.release();
}
~~~

Đoạn này minh họa việc trả permit trong finally. Trong hệ thống thật, cần tách transaction cập nhật outbox khỏi SMTP network call và tránh tự gọi transactional method qua self-invocation trong cùng bean.

### Test rò rỉ thread

Không chỉ đếm tổng thread ở mức JVM vì framework, GC và test runner cũng tạo thread. Nên đo:

- Số worker thread của mail executor.
- Active/in-flight tasks.
- Task queue length.
- Số socket connection tới fake SMTP.
- Số record PROCESSING bị giữ quá lease.
- Tỷ lệ throughput sau một loạt timeout.

Một phép thử gây lỗi lặp vài trăm lần trong môi trường cô lập có thể giúp phát hiện resource leak, nhưng số lần và thời gian phải được giới hạn để CI ổn định.

## 32. Chống duplicate khi kết quả SMTP không xác định

Khi client không nhận final reply sau DATA, việc retry có thể gửi trùng. Bảo vệ ở các tầng:

- Dùng internal notification ID cho sự kiện nghiệp vụ.
- Đặt unique constraint trên idempotency key để không enqueue trùng.
- Ghi từng delivery attempt có trạng thái và thời điểm.
- Claim outbox bằng lease/locking.
- Nếu transport có kết quả không rõ, giữ trạng thái SUBMISSION_UNKNOWN.
- Đối soát provider message ID, relay log hoặc event API nếu có.
- Nếu yêu cầu resend thực sự, tạo một request mới có audit, không âm thầm reset record cũ.

### Vì sao Message-ID không phải bảo đảm idempotency?

SMTP và mailbox không có một quy tắc bắt buộc tất cả hệ thống phải loại bỏ email trùng dựa trên header Message-ID. Một Message-ID ổn định có thể giúp trace/reconciliation, nhưng không thay thế trạng thái ứng dụng hoặc provider idempotency API nếu có.

### Kiểm thử double-claim

Với database hỗ trợ locking, chạy hai worker cố claim một notification đến hạn. Một worker được quyền xử lý, worker còn lại phải bỏ qua hoặc chờ. Mock repository không đủ để chứng minh locking thực; cần integration test database/transaction.

Ngay cả khi claim được bảo vệ, duplicate vẫn có thể xảy ra khi worker cũ đã gửi thành công nhưng dừng trước khi cập nhật trạng thái. Đây là giới hạn của SMTP transaction boundary, không phải lỗi riêng của semaphore.

## 33. Kiểm thử server từ chối và suppression list

Một SMTP recipient rejection có thể dẫn đến suppression, nhưng phải đúng phạm vi.

### Permanent recipient refusal

Nếu test server trả 550 5.1.1 đối với recipient A:

- Lưu reason đã chuẩn hóa cho A.
- Không gửi lại liên tục A.
- Có thể suppress A theo policy.
- Không suppress B nếu B không có lỗi.
- Không chặn toàn bộ sender khi chỉ một recipient không tồn tại.

### Temporary recipient refusal

Nếu server trả 451:

- Giữ email ở trạng thái retryable nếu còn đủ điều kiện.
- Không suppress vĩnh viễn chỉ sau một temporary failure.
- Dùng backoff và giới hạn attempts.
- Theo dõi nếu cùng recipient liên tục thất bại.

### Policy rejection

Nếu server trả 550/554 vì sender reputation hoặc content policy, **đổi recipient không phải giải pháp**. Có thể cần xem SPF/DKIM/DMARC, nội dung, quota, tần suất và chính sách provider. Test nên phân biệt mã và tình huống provider mô phỏng; không dùng tất cả 5xx để gắn reason INVALID_ADDRESS.

### Nguy cơ suppression sai

Một logic kiểu:

~~~java
catch (MailException error) {
    recipientRepository.setEmailInvalid(recipientId);
}
~~~

là sai: MailException có thể do timeout, credential hoặc network. Tầng xử lý recipient chỉ nên suppress khi có bằng chứng phù hợp từ transport/provider và chính sách rõ ràng.

## 34. Bảo mật và giới hạn khi chạy kiểm thử lỗi SMTP

Để tránh ảnh hưởng dữ liệu thật:

- Bind fake SMTP vào loopback/container network của test.
- Không dùng SMTP production host hoặc credential thật.
- Đặt timeout nhỏ nhưng có giới hạn.
- Không cho fake relay chuyển tiếp thư ra Internet.
- Không đưa email cá nhân vào fixture.
- Không bật protocol debug log chứa thông tin AUTH và MIME body trong CI shared logs.
- Dọn socket, thread, container, queue sau test.
- Tách database/outbox test khỏi production.
- Giới hạn email count và attachment size.
- Không tắt TLS verification trong production chỉ vì test TLS lỗi.
- Không suy ra một test với SMTP fake chứng minh provider thật tuân theo cùng message quota, timeout hoặc enhanced codes.

### Debug protocol nên dùng khi nào?

Trong môi trường cô lập, protocol trace có thể giúp xác nhận lệnh nào đã được gửi và server trả lời gì. Nhưng trace có thể chứa recipient address, subject, body hoặc AUTH material tùy thư viện/cấu hình. Không nên bật `mail.debug=true` kéo dài trong production. Với test, ưu tiên fake server ghi lại **tên lệnh và phase** thay vì toàn bộ nội dung.

### Không cần Internet để kiểm tra timeout

Read timeout, RCPT refusal, DATA rejection và mất final reply có thể tái hiện với SMTP scripted server local. Network connect timeout có thể cần fault injector, nhưng vẫn nên đặt trong môi trường mạng test được kiểm soát. Điều này làm test nhanh, lặp lại được và không phụ thuộc trạng thái provider công cộng.

## 35. Những lỗi thường gặp khi viết integration test

### 35.1. Mock MailSender nhưng gọi đó là SMTP integration test

Mock không đi qua socket SMTP/Jakarta Mail. Dùng fake SMTP server để kiểm tra transport thực; mock vẫn hữu ích ở unit test policy.

### 35.2. Tắt STARTTLS để “cho test qua” rồi dùng cấu hình đó cho production

Fake plaintext trên localhost chỉ phục vụ test cô lập. Production cần cấu hình TLS theo provider.

### 35.3. Test connect timeout bằng port không có listener

Port đóng thường gây connection refused. Muốn connect timeout phải mô phỏng kết nối bị drop/blackhole.

### 35.4. Test write timeout bằng email quá nhỏ

TCP buffer có thể nhận toàn bộ body và không tạo write timeout. Dùng network injector/buffer control nếu cần kết quả quyết định.

### 35.5. Assert exception class/cause quá cứng

Transport/provider version có thể bọc exception khác nhau. Test phân loại ổn định ở tầng adapter và kiểm tra hành vi socket ở test transport.

### 35.6. Dùng Thread.sleep và assertion thời gian sát

CI chậm, scheduling và network stack tạo jitter. Dùng fake clock cho retry, upper bound hợp lý và event/latch cho concurrency.

### 35.7. Không kiểm tra fake server đã nhận lệnh nào

Test “read timeout” có thể thực tế lỗi sai port. Đo command progression: EHLO, MAIL FROM, RCPT TO, DATA.

### 35.8. Chỉ trả một mã 550 cho mọi giai đoạn

RCPT rejection và MAIL FROM rejection khác phạm vi lỗi. Fake server phải script đúng vị trí.

### 35.9. Coi send() lỗi là chắc chắn chưa gửi

Nếu mất final reply sau DATA, client không biết relay đã accepted hay chưa. Retry mù có thể duplicate.

### 35.10. Coi send() thành công là delivered

Final 250 của relay là submission acceptance ở chặng đó, không phải inbox delivery. Bounce có thể xuất hiện sau.

### 35.11. Không làm sạch state giữa các test

Outbox records, fake server connection, executor hoặc Redis limiter từ test trước có thể ảnh hưởng test sau. Dùng isolation và cleanup.

### 35.12. Test nhiều worker nhưng limiter chỉ nằm trong từng JVM

Tổng tốc độ có thể vượt quota. Test concurrency toàn cụm phải dùng chung limiter/DB claim.

### 35.13. Để SMTP AUTH failure gây retry storm

Một credential sai không tự sửa khi retry nhiều email. Cần tạm dừng lane, sửa secret rồi tiếp tục backlog.

### 35.14. Retry 4xx ngay lập tức

Server đang quá tải có thể càng khó hồi phục. Áp dụng exponential backoff, jitter và rate limit.

### 35.15. Giữ transaction DB mở trong lúc SMTP timeout

Làm tăng lock contention và không đảm bảo đồng bộ giữa SMTP và database. Ghi outbox cùng nghiệp vụ, send sau commit.

### 35.16. Không test khi worker tiếp tục sau một timeout

Một message lỗi có thể giữ slot khiến các message sau bị kẹt. Kiểm tra cleanup, release và throughput phục hồi.

### 35.17. Dùng provider thật cho bài test từ chối hàng loạt

Có thể vi phạm quota, ảnh hưởng uy tín gửi hoặc tác động người nhận. Dùng fake/staging đã được cho phép.

### 35.18. Không đo partial acceptance nhiều recipient

Khi một địa chỉ bị từ chối, không được tự cho rằng mọi recipient đều thất bại hoặc mọi recipient đều được giao.

### 35.19. Tính thiếu permit như một SMTP failure

Nếu worker chưa gọi send vì limiter hết token, không được tăng SMTP attempt hoặc suppress recipient.

### 35.20. Đánh dấu email đã đến inbox chỉ vì không nhận bounce

Thiếu bounce không chứng minh delivery thành công. Phải phân biệt kết quả submit với provider delivery event.

## 36. Runbook khi SMTP timeout trong production

Khi tỷ lệ timeout tăng bất thường, thứ tự xử lý nên tập trung vào xác định điểm lỗi và giảm tác động trước khi tăng retry:

1. **Xác định loại timeout:** TCP connect, read after EHLO, TLS handshake, AUTH reply, RCPT reply, DATA write hay final reply sau body.
2. **Phân nhóm phạm vi:** một pod, toàn bộ worker, một SMTP account, một provider, một recipient domain hay một chiến dịch.
3. **Kiểm tra mạng:** DNS, firewall, port, proxy, routing, packet loss và thay đổi network policy.
4. **Kiểm tra provider:** tình trạng dịch vụ, rate limit, quota, thời gian phản hồi và SMTP reply code.
5. **Xem worker:** in-flight sends, connection count, executor queue, outbox oldest age và timeout rate.
6. **Giảm tải nếu cần:** tạm dừng chiến dịch không thiết yếu, giảm concurrency/rate; không mở rộng thread vô hạn.
7. **Bảo vệ email bắt buộc:** giữ outbox bền vững; không rollback giao dịch đã commit chỉ vì SMTP lỗi.
8. **Phân loại unknown:** đối với mất final reply sau DATA, không retry mù.
9. **Khôi phục có điều tiết:** sau khi SMTP phục hồi, xả backlog qua limiter và backoff, tránh retry storm.
10. **Đối soát:** so sánh accepted, bounced, deferred và provider events nếu có; không suy ra đã giao thư từ kết quả submit.
11. **Hậu kiểm:** xác định nguyên nhân gốc, sửa timeout/cấu hình/quota phù hợp và bổ sung test tái hiện.

### Không tăng timeout một cách mù quáng

Tăng read timeout từ 5 giây lên 60 giây có thể che giấu sự cố trong khi giữ worker/connection lâu hơn. Nếu provider đang quá tải, việc chờ lâu hơn không nhất thiết tăng throughput. Trước khi sửa cấu hình, cần hiểu giai đoạn bị chậm và ngân sách deadline của hệ thống.

### Khi cần failover sang provider khác

Nếu có provider dự phòng, chỉ route những message phù hợp, bảo đảm sender identity và credential được cấu hình đúng, dùng quota riêng, không tự retry các message có kết quả không xác định. Failover không làm mất rủi ro duplicate hoặc quyền riêng tư; cần trace theo provider/attempt.

## 37. Runbook khi SMTP server chủ động từ chối

Một spike lỗi 4xx hoặc 5xx cần xử lý khác nhau theo mã và giai đoạn:

### Nếu tăng 421/451/452

- Kiểm tra lỗi do provider, network hay recipient.
- Nếu là throttling, giảm tốc và dùng exponential backoff có jitter.
- Kiểm tra backlog, quota, connection concurrency.
- Không tạo hàng nghìn retries đồng thời.
- Theo dõi thời gian lỗi kéo dài và tỷ lệ phục hồi.

### Nếu tăng 550 5.1.1 ở RCPT TO

- Nhóm theo nguồn danh sách, recipient domain và thời điểm.
- Xem địa chỉ có được xác minh hay không.
- Suppress địa chỉ thực sự không hợp lệ theo chính sách.
- Không tiếp tục thử gửi vô hạn tới cùng địa chỉ.
- Không kết luận đây là lỗi SMTP password.

### Nếu tăng 535 ở AUTH

- Kiểm tra credential, quyền SMTP AUTH, account lock và thay đổi chính sách.
- Dừng các retries vô ích ở cấp provider lane.
- Cập nhật/rotate secret qua hệ thống quản lý an toàn.
- Xác minh TLS, AUTH và From permission trên canary.
- Mở lại mail dispatcher theo rate limiter.
- Không log hoặc gửi password trong ticket/chats.

### Nếu tăng 554 sau DATA

- Xem phản hồi provider về content, attachment size, spam/policy, sender identity.
- Phân biệt trả 554 rõ ràng với mất phản hồi.
- Không thay recipient hoặc resend mù khi lỗi do content/policy.
- Dùng test server để tái hiện đúng phase nếu có thể.
- Sau sửa, replay có kiểm soát và giữ attempt history.

## 38. Một ví dụ tích hợp end-to-end: đặt hàng và SMTP 451

Giả sử người dùng thanh toán thành công. Ứng dụng cần gửi email xác nhận nhưng SMTP trả 451 ở RCPT TO.

### Thiết kế mong đợi

~~~text
HTTP POST /orders
       |
       v
Business transaction:
  - Save order
  - Save ORDER_CONFIRMED outbox message
       |
       v
COMMIT
       |
       v
Mail worker claims outbox
       |
       v
JavaMailSender -> fake SMTP
       |
       v
RCPT TO -> 451 4.3.0 Try later
       |
       v
Classifier: TEMPORARY_SMTP
       |
       v
Outbox RETRY_PENDING + nextAttemptAt
       |
       v
Worker retries later through limiter
       |
       v
SMTP 250 accepted -> SUBMITTED
~~~

### Các assertion nghiệp vụ

- Đơn hàng vẫn tồn tại sau SMTP failure.
- Outbox có notification ID liên kết đúng đơn hàng.
- Attempt đầu tiên được ghi là lỗi tạm thời.
- Trạng thái không nhảy sang SUBMITTED hoặc DELIVERED khi SMTP trả 451.
- Không có lần gửi tiếp theo ngay khi chưa tới nextAttemptAt.
- Sau phục hồi, chỉ một worker claim record đúng lịch.
- Nếu fake SMTP nhận final 250, record có thể chuyển SUBMITTED.
- Không tự ghi DELIVERED nếu không có provider delivery event.

### Pseudocode test

~~~java
@Test
void orderSurvivesTemporarySmtpRefusal() {
    // Arrange: fake SMTP trả 451 ở RCPT TO
    // và repository/outbox dùng database test.
    Order order = orderService.placeOrder(command);

    // Domain transaction đã commit.
    assertTrue(orderRepository.existsById(order.getId()));

    // Mail worker xử lý outbox ở một transaction riêng.
    mailWorker.dispatchDue();

    EmailOutboxRecord record = outboxRepository
            .findByBusinessKey("ORDER_CONFIRMED", order.getId())
            .orElseThrow();

    assertEquals(OutboxStatus.RETRY_PENDING,
            record.getStatus());
    assertTrue(record.getNextAttemptAt().isAfter(clock.instant()));
    assertTrue(orderRepository.existsById(order.getId()));
}
~~~

Các lớp OrderService, MailWorker, EmailOutboxRecord, repository và Clock là thành phần do dự án định nghĩa; ví dụ minh họa những assertion cần có, **không phải một test chạy độc lập khi chưa tạo domain model**.

### Phần nào phải được integration-test?

Để tin kết quả, cần:

- Test SMTP transport thật qua fake server trả 451.
- Test policy classifier gắn 451 vào temporary failure.
- Test DB/outbox ghi trạng thái/nextAttemptAt bằng transaction thật.
- Có thể thêm test end-to-end điều phối toàn luồng bằng fake SMTP và database test nếu hệ thống cần độ tin cậy cao.

Việc mock tất cả ba phần rồi verify method được gọi không chứng minh transaction/SMTP boundary đã hoạt động thực sự.

## 39. Checklist triển khai và nghiệm thu

Trước khi đưa cấu hình timeout và SMTP refusal handling vào production, đội phát triển nên nắm rõ các điểm:

| Hạng mục | Cần xác định |
| --- | --- |
| Host, port và TLS mode | Có đúng provider và môi trường không? |
| Timeout | Có cấu hình connect/read/write phù hợp không? |
| Kết nối refused | Có phân biệt với connect timeout không? |
| Read timeout | Đã test server im lặng ở một lệnh cụ thể chưa? |
| Write timeout | Fault injection có thực sự làm socket write bị block không? |
| 4xx | Có retry có backoff, jitter và maxAttempts không? |
| 5xx | Có phân loại recipient/content/auth đúng phạm vi không? |
| AUTH failure | Có tránh retry storm và lộ secret không? |
| TLS failure | Có fail closed thay vì downgrade không? |
| DATA response loss | Có chính sách SUBMISSION_UNKNOWN/duplicate không? |
| Nhiều recipient | Có xác định partial acceptance không? |
| Outbox | Email bắt buộc có được lưu cùng transaction nghiệp vụ không? |
| Retry state | Có bền vững qua restart không? |
| Rate/concurrency | Retry và replay có qua cùng limiter không? |
| Expiry/suppression | Không gửi OTP hết hạn/marketing đã unsubscribe? |
| Metrics/log | Có phase, category, reason và correlation mà không lộ PII? |
| Test cleanup | Có đóng socket/thread/DB container/queue? |
| Provider event | Không nhầm submitted với delivered? |

Checklist trên là công cụ lập kế hoạch kiểm thử; từng dòng chỉ được coi là đạt khi có kết quả test/quan sát tương ứng. Với một dự án chưa cần nhiều recipient hay không có TLS AUTH trong fake server, có thể chia test suite thành các cấp phù hợp nhưng vẫn cần xác định giới hạn đã được kiểm chứng.

## 40. Câu hỏi tự kiểm tra

**1. Vì sao mock JavaMailSender không đủ để kiểm thử SMTP timeout?**

Vì mock không tạo TCP connection và không thực thi Jakarta Mail SMTP protocol. Nó chỉ kiểm tra business behavior khi exception được ném, không xác nhận cấu hình timeout hoặc phase giao thức.

**2. Sự khác nhau giữa connect timeout và connection refused là gì?**

Connect timeout là không hoàn tất kết nối trong thời hạn; connection refused thường có phản hồi từ chối kết nối nhanh từ hệ điều hành hoặc điểm mạng. Port không có listener thường tạo refused, không phải timeout.

**3. mail.smtp.timeout dùng để làm gì?**

Đó là socket read timeout trong các triển khai Jakarta Mail SMTP phổ biến, giới hạn thời gian chờ phản hồi đọc từ server.

**4. mail.smtp.writetimeout có dễ test bằng body ngắn không?**

Không. TCP buffer có thể nhận toàn bộ body ngay cả khi server không đọc. Cần network fault injector/kiểm soát buffer hoặc dữ liệu đủ lớn có giới hạn.

**5. Cấu hình ba timeout có tạo deadline tổng cho send() không?**

Không nhất thiết. Nhiều bước đọc/ghi có thể cộng dồn; cần giới hạn toàn bộ job ở tầng cao hơn khi có SLA tổng.

**6. SMTP 451 và SMTP 550 khác nhau thế nào?**

451 thường là lỗi tạm thời; 550 là từ chối vĩnh viễn cho yêu cầu hiện tại theo ngữ cảnh. Cần xem phase/enhanced status/provider trước khi quyết định retry hay suppression.

**7. Nếu 550 xuất hiện ở MAIL FROM, có nên đánh dấu recipient invalid không?**

Không. Lỗi ở MAIL FROM liên quan sender/envelope/policy, không chứng minh recipient có vấn đề.

**8. Vì sao phải kiểm thử từ chối trước và sau DATA?**

Vì khả năng biết message đã được chuyển tới đâu khác nhau. Lỗi trước DATA chưa gửi body; sau body cần phân biệt server từ chối rõ ràng với không có final reply.

**9. Mất final reply sau dấu chấm kết thúc DATA có thể gây gì?**

Ứng dụng không biết chắc relay đã nhận message hay chưa. Retry mù có thể gửi trùng. Có thể cần trạng thái SUBMISSION_UNKNOWN và đối soát.

**10. Header Message-ID có bảo đảm không gửi trùng không?**

Không. Nó hữu ích cho trace nhưng SMTP/mailbox không có yêu cầu phổ quát loại duplicate dựa trên Message-ID.

**11. Khi RCPT TO 550 một trong hai recipient, có thể coi cả hai đều lỗi không?**

Không nên suy đoán. Hành vi partial acceptance phụ thuộc transport configuration và server; cần test theo recipient và chính sách.

**12. Nếu SMTP AUTH thất bại, có nên retry tất cả email với password cũ?**

Không. Có nguy cơ bão xác thực. Cần sửa credential/quyền và giữ outbox, mở lại dispatch có kiểm soát.

**13. Vì sao không tắt TLS khi gặp lỗi certificate?**

Đó là hạ cấp bảo mật và có thể làm lộ credential/nội dung. Cần sửa trust/hostname/TLS configuration theo provider.

**14. Read timeout sau EHLO chứng minh điều gì?**

Client đã nối tới server, gửi EHLO và không nhận reply kịp thời. Nếu fake server chưa nhận MAIL FROM/DATA, có thể xác nhận body chưa được submit.

**15. Vì sao dùng cổng động trong test SMTP?**

Giảm xung đột giữa nhiều test hoặc process. Cần đóng listener để không rò rỉ port/thread.

**16. Có nên assert read timeout chính xác 250 ms?**

Không. Độ trễ chịu ảnh hưởng scheduling, startup và overhead. Kiểm tra failure mode cùng upper bound hợp lý, và dùng fault injection xác định.

**17. JavaMailSender.send() trả về bình thường có nghĩa delivered không?**

Không. Nó thường chứng minh submission được relay chấp nhận theo phản hồi; delivery xuống mailbox là giai đoạn khác.

**18. Vì sao cần transactional outbox khi gửi email sau đặt hàng?**

Để yêu cầu gửi email được lưu cùng transaction nghiệp vụ, còn SMTP được gọi sau commit; timeout không làm rollback đơn hàng đã hoàn tất và không làm mất yêu cầu gửi.

**19. Thiếu rate token có được tính là SMTP attempt không?**

Không nếu chưa gọi transport. Đó là defer do limiter; không đánh dấu một lần SMTP gửi thất bại.

**20. Vì sao cần giới hạn maxAttempts và thêm jitter?**

Để tránh retry vô hạn và tránh nhiều worker cùng thử lại vào một thời điểm, làm quá tải SMTP.

**21. Làm sao kiểm tra hệ thống còn khỏe sau khi một message timeout?**

Đo worker slots, socket/thread cleanup, outbox state và khả năng gửi thành công message tiếp theo. Một exception được bắt chưa đủ chứng minh tài nguyên được giải phóng.

**22. Vì sao không nên chạy fault-injection trên SMTP production?**

Nó có thể ảnh hưởng quota, uy tín gửi, người nhận hoặc dịch vụ thật. Dùng SMTP fake/test provider trong môi trường được cấp phép.

**23. Có thể dùng @Async để giải quyết toàn bộ timeout không?**

Không. @Async chuyển lời gọi sang executor; socket vẫn có thể block, queue có thể đầy và task trong memory có thể mất khi process chết. Vẫn cần transport timeout, bounded executor và outbox.

**24. Khi server trả mã 4xx nhưng provider đang tự retry message đã accepted, ứng dụng có nên gửi lại không?**

Không nên tự tạo một bản mới khi provider vẫn sở hữu message và đang retry downstream. Phải xác định liệu lỗi xảy ra trước submission hay là deferred sau accepted.

**25. Bước quan trọng nhất để tránh phân loại sai lỗi SMTP là gì?**

Ghi nhận bằng chứng về phase giao thức, reply/enhanced status và nguyên nhân transport; chuẩn hóa tại adapter rồi mới áp dụng chính sách retry/suppression.

## Kết luận

**Kiểm thử timeout và server từ chối trong Spring Framework Mail phải đi qua ranh giới SMTP thực và mô phỏng lỗi ở đúng giai đoạn của giao thức.** Hãy phân biệt connect, read và write timeout với server refusal theo mã 4xx/5xx; dùng `JavaMailSenderImpl` nối tới scripted SMTP server để kiểm tra EHLO, RCPT TO, DATA và final reply. Bổ sung test TLS/AUTH, multi-recipient, network fault injection và Spring Boot configuration theo nhu cầu. Ở tầng ứng dụng, kiểm tra transactional outbox, phân loại lỗi, retry có backoff/jitter, bảo vệ recipient khỏi suppression sai, chống retry storm và giữ trạng thái SUBMISSION_UNKNOWN khi relay có thể đã nhận message nhưng phản hồi bị mất. Cuối cùng, dùng metric, log có correlation, cleanup tài nguyên và kịch bản outage-recovery để chứng minh hệ thống không chỉ phát hiện lỗi, mà còn **phục hồi an toàn mà không làm mất email quan trọng hoặc tạo bản gửi trùng không kiểm soát**.
