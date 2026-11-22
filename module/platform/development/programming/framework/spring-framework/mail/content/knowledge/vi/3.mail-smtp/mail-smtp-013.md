# Timeout kết nối, timeout đọc và timeout ghi trong Spring Framework Mail

Gửi email qua SMTP là một tác vụ mạng. Dù trong ứng dụng Spring chỉ có một lệnh `mailSender.send(...)`, phía sau có nhiều bước: phân giải tên máy chủ, thiết lập TCP, nhận lời chào SMTP, thương lượng TLS, xác thực, truyền nội dung thư và chờ phản hồi. Khi một bước bị chặn, thread gửi mail có thể chờ rất lâu nếu không có giới hạn phù hợp.

Spring Framework Mail sử dụng `JavaMailSender` và thường dựa vào Jakarta Mail để làm việc với SMTP. Ba timeout quan trọng nhất là:

- **Connection timeout** — `mail.smtp.connectiontimeout`: giới hạn thời gian chờ thiết lập **kết nối socket** tới SMTP server.
- **Read timeout** — `mail.smtp.timeout`: giới hạn thời gian chờ một thao tác **đọc dữ liệu từ socket**.
- **Write timeout** — `mail.smtp.writetimeout`: giới hạn thời gian một thao tác **ghi dữ liệu lên socket** có thể bị chặn.

Cả ba thuộc tính dùng đơn vị **mili giây (ms)** và cần cấu hình riêng. Chúng không phải một “timeout tổng” bao trùm toàn bộ quá trình gửi email.

## 1. Nhìn ba timeout trên dòng thời gian SMTP

Một phiên SMTP có STARTTLS thường diễn ra theo các bước khái quát:

```text
Ứng dụng Java                               SMTP server
     |                                           |
     | -- DNS: smtp.example.com ---------------- |
     |                                           |
     | -- TCP connect -------------------------> |
     |      [connectiontimeout]                  |
     | <---------------------------- 220 ------- |
     |      [timeout: read]                      |
     | -- EHLO --------------------------------> |
     |      [writetimeout: write]                 |
     | <----------------------------- 250 ------ |
     |      [timeout: read]                      |
     | -- STARTTLS ----------------------------> |
     | <----------------------------- 220 ------ |
     | -- TLS handshake -----------------------> |
     | -- EHLO / AUTH -------------------------> |
     | <----------------------------- 235 ------ |
     | -- MAIL FROM / RCPT TO -----------------> |
     | <----------------------------- 250 ------ |
     | -- DATA --------------------------------> |
     | <----------------------------- 354 ------ |
     | -- headers, body, attachments ----------> |
     |      [writetimeout: write]                 |
     | -- "." kết thúc DATA -------------------> |
     | <----------------------------- 250 ------ |
     |      [timeout: read]                      |
     | -- QUIT --------------------------------> |
```

Đây là sơ đồ đơn giản hóa; phiên SMTP cụ thể có thể có nhiều lệnh/response hơn, nhiều người nhận và cơ chế TLS khác. Một lần gửi gồm **nhiều thao tác đọc và ghi luân phiên**. Có trường hợp mở TCP rất nhanh nhưng chờ phản hồi `250` sau `DATA` rất lâu; cũng có trường hợp máy chủ trả lời nhanh nhưng truyền tệp đính kèm qua mạng bị nghẽn.

| Thuộc tính Jakarta Mail | Được áp dụng khi | Ví dụ sự cố | Không đại diện cho |
| --- | --- | --- | --- |
| `mail.smtp.connectiontimeout` | Đang chờ mở kết nối TCP | Firewall bỏ gói hoặc máy chủ không phản hồi kết nối | Toàn bộ lần gửi sau khi kết nối thành công |
| `mail.smtp.timeout` | Đang chờ dữ liệu đọc từ socket | Chờ banner `220`, `250`, `354`, `235` | Thời gian ghi dữ liệu lên mạng |
| `mail.smtp.writetimeout` | Đang ghi dữ liệu lên socket | Gửi body hoặc attachment khi server ngừng nhận dữ liệu | Thời gian chờ phản hồi sau khi đã ghi |

## 2. Connection timeout — giới hạn lúc mở kết nối

`mail.smtp.connectiontimeout` là thời gian tối đa cho thao tác **thiết lập kết nối socket** tới SMTP endpoint. Ví dụ:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
```

Giá trị `5000` tương ứng **5 giây**. Khi ứng dụng kết nối tới `smtp.example.com:587`, hệ điều hành phải hoàn thành bắt tay TCP. Nếu đường mạng hoặc firewall im lặng bỏ gói tin, thao tác kết nối có thể bị chặn; connection timeout giúp thoát khỏi trạng thái đó.

Những tình huống thường liên quan đến connection timeout:

- SMTP server không thể tiếp cận từ môi trường chạy ứng dụng.
- Firewall hoặc network policy chặn outbound TCP và không gửi lỗi từ chối rõ ràng.
- Đường truyền có vấn đề khiến bắt tay TCP không hoàn thành trong thời gian cho phép.
- Endpoint SMTP quá tải đến mức không thể thiết lập kết nối đúng hạn.

Tuy nhiên, **connect timeout không bao gồm mọi bước trước khi nhận email**:

- DNS lookup có thể xảy ra trước thao tác kết nối. Một DNS resolver phản hồi rất chậm không nhất thiết bị giới hạn bởi `connectiontimeout`.
- Server đã chấp nhận TCP nhưng không gửi lời chào `220`: client đang **đọc**, nên `mail.smtp.timeout` mới liên quan.
- Server phản hồi chậm sau `AUTH` hoặc `DATA`: kết nối vốn đã tồn tại, không còn ở giai đoạn connect.
- Gửi file đính kèm bị nghẽn: đây là vấn đề ghi dữ liệu, thường không giải quyết bằng connect timeout.

Nếu hostname sai, có thể xuất hiện `UnknownHostException`; nếu cổng bị từ chối rõ ràng, có thể xuất hiện `ConnectException: Connection refused`. Hai lỗi này không nhất thiết tiêu tốn hết số mili giây connect timeout: máy khách có thể nhận thất bại ngay.

**Tình huống minh họa:** TCP connect hoàn tất trong 100 ms, nhưng SMTP server không gửi banner suốt 30 giây. Mặc dù `connectiontimeout=3000`, việc chờ banner vẫn có thể kéo dài nếu `mail.smtp.timeout` không được đặt. Cấu hình connect timeout không tự động giới hạn tất cả những gì diễn ra sau khi mở TCP.

## 3. Read timeout — giới hạn chờ phản hồi

`mail.smtp.timeout` là **socket read timeout** của Jakarta Mail, thường áp dụng thông qua tùy chọn `SO_TIMEOUT`. Ví dụ:

```properties
spring.mail.properties.mail.smtp.timeout=10000
```

Giá trị `10000` nghĩa là **10 giây** cho một thao tác đọc bị chặn khi chưa nhận được dữ liệu.

SMTP là giao thức theo nhịp lệnh–phản hồi: client gửi lệnh rồi thường đợi server xác nhận. Nếu server đã kết nối nhưng quá tải hoặc không trả lời, một thao tác đọc có thể đứng lâu.

| Giai đoạn | Dữ liệu được chờ | Ví dụ vấn đề |
| --- | --- | --- |
| Sau TCP connect | Banner `220` | Máy chủ giữ kết nối nhưng không gửi lời chào |
| Sau `EHLO` | `250` và thông tin capability | SMTP relay phản hồi chậm |
| Sau `STARTTLS` | Phản hồi và dữ liệu trao đổi TLS | Quá trình nâng cấp TLS bị kẹt |
| Sau `AUTH` | Kết quả xác thực | Backend xác thực SMTP chậm |
| Sau `RCPT TO` | Xác nhận người nhận | Server kiểm tra chính sách mất thời gian |
| Sau dấu `.` kết thúc `DATA` | Phản hồi chấp nhận thông điệp | Server xử lý/xếp hàng nội dung lâu |

Tại bước cuối, read timeout có ý nghĩa đặc biệt. Client có thể đã truyền toàn bộ nội dung và chỉ đang chờ phản hồi `250`. Nếu phản hồi không đến kịp, **không thể tự suy ra thư chưa được server tiếp nhận**. Server có thể đã nhận thông điệp, nhưng phản hồi bị mất hoặc đến trễ.

### Read timeout không phải deadline cho toàn bộ lần gửi

Một timeout đọc thường giới hạn thời gian chờ **một thao tác đọc** khi không có dữ liệu. Nếu phiên SMTP trải qua nhiều lần đọc, tổng thời gian có thể vượt đáng kể ngưỡng.

```text
mail.smtp.timeout = 10000 ms

Đợi banner:         8 giây   → đọc thành công
Đợi EHLO:           7 giây   → đọc thành công
Đợi sau AUTH:       9 giây   → đọc thành công
--------------------------------------------
Tổng thời gian đọc: 24 giây
```

Dù mọi bước đều dưới 10 giây, tổng cộng đã 24 giây. Một phản hồi được nhận dần thành nhiều phần cũng có thể khiến tổng thời gian kéo dài hơn giới hạn chờ đơn lẻ. Vì vậy `mail.smtp.timeout` không đồng nghĩa “toàn bộ `send()` phải xong trong 10 giây”.

## 4. Write timeout — giới hạn khi truyền dữ liệu

`mail.smtp.writetimeout` giới hạn thời gian một thao tác ghi vào socket SMTP bị chặn:

```properties
spring.mail.properties.mail.smtp.writetimeout=10000
```

Khi gửi email có HTML hoặc PDF đính kèm, thư viện cần truyền dữ liệu MIME qua kết nối. Nếu server ngừng đọc hoặc tốc độ mạng thấp đến mức bộ đệm socket không còn chỗ, thao tác ghi có thể bị chặn.

```text
Client                                         SMTP server
  |                                                |
  | -- DATA -------------------------------------> |
  | <--------------------------------- 354 ------- |
  | -- body chunk 1 ----------------------------> |
  | -- body chunk 2 ----------------------------> |
  | -- body chunk 3 ------- [bị chặn] ----------> |
  |                                                |
  |       writetimeout có thể kích hoạt             |
```

Trong trường hợp này, tăng `mail.smtp.timeout` không giải quyết đúng thao tác đang chậm. Thư viện đang chờ **ghi**, không phải chờ **đọc**.

Với Jakarta Mail/Angus Mail ở các phiên bản phổ biến, write timeout được triển khai bằng cơ chế lập lịch đóng socket nếu thao tác ghi kéo dài quá thời gian. Một số triển khai sử dụng thêm tài nguyên lập lịch/thread theo kết nối, nên ở hệ thống gửi số lượng lớn cần quan tâm số kết nối đồng thời.

Write timeout cũng **không phải** tổng thời gian tối đa để upload toàn bộ thư: body có thể được ghi thành nhiều lần; hệ điều hành còn có socket buffer. Những lần ghi nhỏ thành công liên tục có thể khiến tổng thời gian upload lớn hơn `writetimeout`.

### Khi nào write timeout dễ xuất hiện?

- Gửi file lớn qua SMTP relay ở khu vực mạng xa.
- Máy chủ SMTP đã kết nối nhưng đọc dữ liệu rất chậm.
- Đường truyền hoặc TCP flow control khiến socket không thể nhận thêm dữ liệu để gửi.
- Tải tăng cao, nhiều email đồng thời cạnh tranh băng thông.

Nếu SMTP server chủ động trả lỗi vì thư vượt kích thước cho phép, đó là lỗi giao thức/chính sách của server; tăng write timeout không làm file lớn trở nên hợp lệ.

## 5. Cấu hình Spring Boot cho cả ba timeout

Nếu ứng dụng dùng `spring-boot-starter-mail` và để Spring Boot tự tạo `JavaMailSender`, có thể thêm cấu hình vào `src/main/resources/application.properties`:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

# Đơn vị: milliseconds
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Bảng diễn giải:

| Thuộc tính | Giá trị ví dụ | Ý nghĩa |
| --- | ---: | --- |
| `mail.smtp.connectiontimeout` | 5000 ms | Chờ tối đa khoảng 5 giây cho thao tác TCP connect |
| `mail.smtp.timeout` | 10000 ms | Chờ tối đa khoảng 10 giây cho thao tác đọc socket |
| `mail.smtp.writetimeout` | 10000 ms | Giới hạn thao tác ghi socket bị chặn khoảng 10 giây |

Các giá trị này **chỉ là ví dụ ban đầu**, không phải cấu hình chuẩn cho mọi dịch vụ. Cần điều chỉnh theo độ trễ mạng, provider SMTP, kích thước thư và yêu cầu nghiệp vụ.

Đặc biệt, Spring Boot truyền các khóa `spring.mail.properties.*` vào JavaMail Session. Cần dùng đúng tên `mail.smtp.connectiontimeout`, `mail.smtp.timeout` và `mail.smtp.writetimeout`; không có một thuộc tính tiêu chuẩn `spring.mail.timeout` để thay thế cả ba.

### Tương đương trong application.yml

Để giữ nguyên tên thuộc tính Jakarta Mail có dấu chấm trong map, có thể dùng khóa dạng bracket:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Cấu hình port `587` với STARTTLS là một trường hợp thông dụng. Nếu provider dùng **implicit TLS** trên port `465`, cấu hình cần thay đổi phù hợp:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=465
spring.mail.properties.mail.smtp.ssl.enable=true
spring.mail.properties.mail.smtp.auth=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Không chọn port hoặc TLS mode theo suy đoán; tuân thủ hướng dẫn của SMTP provider. TLS handshake có thể phát sinh thao tác đọc/ghi socket, nhưng ba thuộc tính này không được hiểu là deadline tuyệt đối cho toàn bộ quá trình TLS trong mọi thư viện/JDK.

### Nếu ứng dụng dùng giao thức smtps

Tên thuộc tính được Jakarta Mail đặt theo **protocol prefix**. Với cấu hình sử dụng transport `smtp` thông thường (kể cả SSL/TLS enable trên `smtp`), dùng `mail.smtp.*` như trên. Nếu ứng dụng **chủ động cấu hình protocol `smtps`**, các thuộc tính tương ứng có prefix `mail.smtps.*`, ví dụ `mail.smtps.timeout`. Cần đối chiếu protocol thực tế của `JavaMailSenderImpl` để tránh đặt đúng giá trị nhưng sai prefix.

## 6. Cấu hình JavaMailSenderImpl không dùng Spring Boot

Trong ứng dụng chỉ dùng Spring Framework hoặc muốn cấu hình JavaMailSender theo cách thủ công:

```java
package example.mail;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(properties);
        return sender;
    }
}
```

Các cấu hình trên thuộc Jakarta Mail, được truyền qua `Properties`. Nếu đang dùng Spring Boot auto-configuration, thông thường nên cấu hình `spring.mail.*` thay vì tạo bean thủ công; việc tạo bean riêng có thể thay đổi cơ chế Boot tự động cấu hình.

Các khóa timeout thường có **giá trị mặc định vô hạn** ở Jakarta Mail nếu không được cấu hình, dù OS/JDK và các lớp mạng vẫn có những giới hạn riêng. Vì vậy không nên kỳ vọng hệ thống tự có ba giới hạn hợp lý khi bỏ trống chúng.

## 7. Timeout trong ngữ cảnh gửi mail từ service Spring

Ví dụ một dịch vụ gửi email:

```java
package example.mail;

import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotification(String recipient, String content) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Thông báo");
        message.setText(content);

        try {
            mailSender.send(message);
            // SMTP submission thành công ở ranh giới được cấu hình.
        } catch (MailException ex) {
            // Ghi nhận attempt và phân loại lỗi ở tầng vận hành.
            throw ex;
        }
    }
}
```

Nếu timeout phát sinh, `JavaMailSender` có thể ném một ngoại lệ Spring Mail như `MailSendException`; nguyên nhân sâu hơn có thể đến từ Jakarta Mail, TCP socket hoặc TLS. Không nên giả định mọi timeout đều được bọc trong cùng một loại ngoại lệ hoặc cùng một nội dung message giữa các phiên bản.

| Biểu hiện/cause | Giai đoạn nghi ngờ | Cách diễn giải |
| --- | --- | --- |
| `SocketTimeoutException: connect timed out` | Connect | Không thiết lập kết nối TCP đúng hạn |
| `SocketTimeoutException: Read timed out` | Read | Đang chờ dữ liệu/phản hồi qua socket |
| Socket bị đóng hoặc lỗi khi ghi | Write | Có thể nghẽn khi gửi dữ liệu, kết quả phía server chưa rõ |
| `ConnectException: Connection refused` | Connect | Endpoint từ chối nhanh, không nhất thiết hết connect timeout |
| `UnknownHostException` | DNS | Không phân giải được hostname |
| `SSLHandshakeException` | TLS | Sai certificate/protocol, trust hoặc sự cố TLS |
| SMTP response `4xx` hoặc `5xx` | Giao thức SMTP | Server phản hồi lỗi; không nhất thiết là timeout |

**Lưu ý:** Một lần `mailSender.send(message)` trả về bình thường chỉ cho biết quá trình giao thư tại chặng SMTP mà ứng dụng gửi tới đã thành công theo phạm vi đó. Nó không chứng minh email đã tới inbox hay đã được đọc.

## 8. Vì sao timeout đọc sau DATA là trường hợp đặc biệt?

Xét tình huống:

```text
Ứng dụng                               SMTP relay
   |                                       |
   | -- DATA, toàn bộ nội dung, "." -----> |
   |                                       | nhận và lưu thư?
   | <----- phản hồi 250 bị trễ/mất ------ |
   |                                       |
   | -- read timeout ------------------X  |
```

Ứng dụng biết mình không nhận được phản hồi xác nhận kịp thời, nhưng không nhất thiết biết server đã chấp nhận mail hay chưa. Nếu backend retry ngay mà không đối soát, người nhận có thể nhận trùng.

Trường hợp write timeout ở cuối quá trình truyền cũng có thể gây **kết quả không chắc chắn**. Việc socket gửi báo lỗi không đủ chứng minh chính xác server đã nhận bao nhiêu dữ liệu, đặc biệt khi có buffer, proxy hoặc kết nối đã chuyển được phần dữ liệu trước đó.

Vì vậy, nên phân biệt:

- `failed_before_submission`: có căn cứ cho thấy chưa gửi nội dung thư.
- `outcome_unknown`: thông tin không đủ để biết SMTP server đã nhận trọn vẹn hay chưa.
- `submitted_to_relay`: ứng dụng nhận được xác nhận thành công ở chặng SMTP.
- `delivered`: nếu ESP cung cấp sự kiện giao nhận đến hệ thống phía nhận, đây là một mốc **khác** `submitted_to_relay`.

SMTP thông thường không mang lại bảo đảm exactly-once end-to-end trong mọi tình huống mạng. Nếu ESP hỗ trợ **idempotency key**, webhook và tra cứu provider message ID, có thể kết hợp để hạn chế tình huống retry trùng. Với SMTP thuần, hãy sử dụng correlation ID, lịch sử attempt, chính sách retry và đối soát phù hợp với nghiệp vụ.

## 9. Giới hạn riêng lẻ khác với timeout tổng của send()

Giả sử cấu hình:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Một lần gửi có thể có thời gian như sau:

```text
TCP connect                       2 giây
Đọc lời chào 220                  3 giây
Đọc kết quả EHLO                  4 giây
TLS / AUTH                        6 giây
Ghi nội dung MIME                 7 giây
Đọc kết quả sau DATA              8 giây
----------------------------------------
Tổng thời gian gửi               30 giây
```

Các thao tác riêng lẻ đều có thể không vượt ngưỡng tương ứng, nhưng tổng là 30 giây. **Không được cộng đơn giản `5 + 10 + 10 = 25 giây` rồi xem là SLA tối đa** cho `send()`.

Ngoài các thao tác mạng, tổng thời gian job còn có thể bao gồm:

- DNS resolution, TLS handshake và các lớp proxy.
- Render HTML template, tạo phần thân MIME, đọc attachment từ disk/object storage.
- Chờ được executor hoặc hàng đợi cấp thread để bắt đầu gửi.
- Thử gửi lại, chờ backoff và xử lý sự cố của ESP.

Nếu có yêu cầu “toàn bộ tác vụ không quá 20 giây”, ứng dụng cần **deadline/budget tổng ở tầng công việc** cùng với ba socket timeout. Chỉ gọi `CompletableFuture#orTimeout(...)` hoặc `Future#get(timeout)` là chưa đủ để bảo đảm socket đã dừng: thao tác I/O bên dưới có thể tiếp tục chạy nếu cancellation/interruption không cắt được nó. Cần quản lý cả thread, socket, giới hạn đồng thời và cơ chế hủy thực tế.

## 10. Cách chọn giá trị phù hợp

Không có một bộ timeout cố định dùng tốt cho mọi hệ thống. SMTP relay nội bộ trên LAN, dịch vụ email qua Internet, hệ thống gửi OTP và hệ thống gửi báo cáo PDF có yêu cầu rất khác nhau.

| Tình huống ví dụ | Connection | Read | Write | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| Relay ổn định gần ứng dụng | 3–5 giây | 5–10 giây | 5–10 giây | Quan sát tốc độ phản hồi thực |
| ESP qua Internet | 5–10 giây | 10–20 giây | 10–30 giây | Có độ trễ và chính sách provider |
| Thư có attachment lớn | 5–10 giây | 10–30 giây | 20–60 giây | Cần giới hạn dung lượng riêng |

Các khoảng này **chỉ minh họa hướng lựa chọn ban đầu**, không phải SLA hoặc khuyến nghị bắt buộc. Timeout quá thấp gây lỗi giả trong điều kiện mạng chậm nhất thời; timeout quá cao làm thread bận lâu, ảnh hưởng throughput.

Cách điều chỉnh thực tế:

1. Đo latency gửi thực tế theo provider, loại thư và kích thước email; xem p50, p95, p99.
2. Đặt connect timeout vừa đủ để phát hiện endpoint không thể truy cập mà không chờ mặc định quá lâu.
3. Đặt read timeout theo thời gian server trả lời thực tế, kể cả sau bước `DATA` khi có quét và xếp hàng.
4. Đặt write timeout tính đến tốc độ mạng và kích thước **thư MIME đã encode**, thường lớn hơn file attachment gốc.
5. Theo dõi tỷ lệ lỗi mỗi loại và điều chỉnh sau khi có dữ liệu vận hành.
6. Đặt giới hạn đồng thời, số lần retry và thời hạn gửi theo mức độ khẩn cấp của nội dung.

Ví dụ, attachment PDF có kích thước 8 MB sẽ tạo MIME message lớn hơn file gốc khi mã hóa base64 cùng các header. Do đó, write timeout cho email có attachment có thể cần khác email OTP một dòng. Tuy nhiên, phải ưu tiên kiểm tra giới hạn kích thước được ESP công bố và tránh gửi file quá lớn qua email.

## 11. Retry khi gặp timeout

Không phải mọi lỗi gửi mail đều cần retry theo cùng cách. Timeout kết nối lúc chưa truyền thông điệp và timeout đọc sau khi truyền xong `DATA` có mức độ chắc chắn rất khác nhau.

| Sự cố | Cách xử lý thường hợp lý |
| --- | --- |
| Connect timeout trước khi truyền | Có thể retry có giới hạn; kiểm tra network, firewall, host, port |
| Read timeout trước `DATA` | Cân nhắc retry theo giai đoạn; xử lý các lỗi cấu hình riêng |
| Read timeout sau khi gửi hết `DATA` | Trạng thái không chắc chắn; tránh retry tự động mù quáng |
| Write timeout khi đang gửi body | Có thể có dữ liệu đã chuyển; lưu attempt, cân nhắc khả năng gửi trùng |
| SMTP `4xx` | Thường tạm thời; retry theo mã lỗi và chính sách provider |
| SMTP `5xx` | Thường là lỗi vĩnh viễn; không retry nguyên trạng nếu cần sửa địa chỉ/chính sách |
| Sai username/password | Sửa secret/cấu hình; retry liên tục sẽ không khắc phục |

Một chính sách retry tốt thường có **exponential backoff với jitter**, số lần thử tối đa, thời hạn giao hợp lý và ID liên kết các attempt. Ví dụ với OTP hết hạn sau vài phút, hệ thống không nên retry hàng giờ; với email báo cáo hàng ngày, có thể chấp nhận trễ hơn.

```text
notification_id = n-101
delivery_id     = d-202
attempt 1       = timeout_after_data
attempt 2       = pending_policy_or_reconciliation
delivery_result = outcome_unknown
```

Với email giao dịch quan trọng, có thể sử dụng outbox và ESP có event tracking để tránh đánh mất yêu cầu gửi hoặc tạo các attempt vô hạn. Nếu server đã nhận mail nhưng app không nhận `250`, email trùng vẫn có thể xảy ra; chính sách retry cần chấp nhận thực tế này.

## 12. Kết hợp timeout với kiến trúc gửi mail bất đồng bộ

Nếu người dùng gửi request HTTP tạo đơn hàng và backend gọi SMTP đồng bộ, request có thể bị giữ cho tới khi server email trả lời hoặc timeout. Nhiều request cùng gặp sự cố sẽ chiếm thread HTTP, làm giảm khả năng đáp ứng của hệ thống.

```text
HTTP Request
    |
    v
Order Service
    | Ghi đơn hàng + bản ghi yêu cầu email (outbox)
    v
HTTP Response
    |
    +------------------------------+
                                   |
                                   v
                           Outbox / Queue
                                   |
                                   v
                             Email Worker
                            /    |      \
                     timeout  retry   concurrency limit
                                   |
                                   v
                               SMTP / ESP
                                   |
                                   v
                      Delivery/Bounce Webhook (nếu có)
```

Đưa việc gửi email vào worker giúp tách độ trễ SMTP khỏi request HTTP. Tuy nhiên worker vẫn cần ba timeout mạng:

- Giới hạn worker/concurrency để tránh mở quá nhiều kết nối SMTP, đặc biệt khi write timeout có chi phí thread/lập lịch theo kết nối.
- Giữ backlog có giới hạn và theo dõi tuổi của job đang chờ.
- Lưu `delivery_id`, `attempt_id` và kết quả từng lần gửi để đối soát.
- Retry có kiểm soát khi lỗi tạm thời; đánh dấu `outcome_unknown` nếu không chắc server nhận chưa.
- Theo dõi `delivered` hoặc `bounced` riêng nếu provider có webhook.

Tác vụ gửi bất đồng bộ không tự xử lý mọi vấn đề. Nếu SMTP luôn timeout, queue sẽ tăng nhanh nếu không có circuit breaker, backoff, hạn mức retry và cảnh báo vận hành.

## 13. Xác định loại timeout khi có sự cố

### Tình huống A — Không thể kết nối tới SMTP

**Triệu chứng:** Đợi khoảng bằng connection timeout, sau đó báo `connect timed out`.

**Nguyên nhân có thể:** Sai route, firewall chặn port 587, network policy Kubernetes, SMTP endpoint không reachable.

**Cách xử lý:** Kiểm tra host/port, DNS, outbound firewall và khả năng kết nối từ đúng môi trường chạy ứng dụng. Tăng read timeout không giúp thiết lập TCP.

### Tình huống B — Kết nối thành công nhưng không có banner

**Triệu chứng:** TCP connect hoàn tất nhưng ứng dụng không nhận được `220`.

**Nguyên nhân có thể:** Server quá tải, proxy SMTP bị kẹt, sử dụng sai port/TLS mode.

**Cách xử lý:** Kiểm tra read timeout và giao thức SMTP/TLS thực tế; phân biệt lỗi kết nối với lỗi phản hồi.

### Tình huống C — Thư ngắn gửi được, attachment lớn bị treo

**Triệu chứng:** Gửi vài dòng text ổn nhưng file PDF lớn thường gây write timeout.

**Nguyên nhân có thể:** Đường truyền chậm, server ngừng đọc hoặc giới hạn kích thước mail.

**Cách xử lý:** Đo MIME size, băng thông, giới hạn nhà cung cấp và write timeout. Nếu server trả mã SMTP từ chối vì vượt kích thước, đừng tăng write timeout như một cách “sửa”.

### Tình huống D — Timeout sau khi kết thúc DATA

**Triệu chứng:** Client truyền xong email nhưng không nhận `250` kịp.

**Nguyên nhân có thể:** Server đang xử lý/xếp hàng, response trễ hoặc đứt kết nối.

**Cách xử lý:** Kiểm tra read timeout, SMTP logs và dữ liệu đối soát từ ESP. Xử lý như kết quả **không chắc chắn** thay vì mặc định email chưa được gửi.

### Tình huống E — Không có exception nhưng send() rất chậm

**Triệu chứng:** Mọi thao tác dưới timeout riêng, nhưng tổng latency 30–60 giây.

**Nguyên nhân có thể:** Nhiều lần đọc/ghi tích lũy, DNS/TLS chậm, thời gian chuẩn bị attachment hoặc chờ thread.

**Cách xử lý:** Đo tổng attempt và từng giai đoạn có thể quan sát. Khi cần SLA tổng, xây deadline và cơ chế quản lý job, không chỉ chỉnh một timeout.

## 14. Logging, metrics và giới hạn thông tin

Để vận hành có cơ sở, nên ghi nhận ở mức một **lần thử gửi**:

| Trường | Mục đích |
| --- | --- |
| `delivery_id`, `attempt_id` | Liên kết sự kiện và các lần thử |
| `smtp_host`, `smtp_port`, `provider` | Xác định endpoint gặp sự cố |
| `started_at`, `elapsed_ms` | Đo thời gian tổng |
| `error_category` | Phân loại connect/read/write/TLS/auth/SMTP |
| `message_size_bytes` | Phát hiện liên hệ giữa kích thước và write timeout |
| `retry_count`, `next_retry_at` | Theo dõi backlog retry |
| `submission_outcome` | Phân biệt success, failed và unknown |

Có thể theo dõi `mail_send_duration` (p50/p95/p99), `mail_send_timeout_total` theo loại lỗi, số worker gửi mail đang bận, queue depth và số event delivered/bounced từ ESP nếu có.

Không ghi username/password SMTP, OTP, token, nguyên body của thư hoặc thông tin cá nhân nhạy cảm vào log. SMTP debug có thể hỗ trợ chẩn đoán nhưng cần bật trong phạm vi hẹp, kiểm soát quyền truy cập và thời gian lưu log vì dữ liệu xác thực hoặc nội dung có thể bị lộ tùy cấu hình.

Những sai lầm cần tránh:

- Tăng `connectiontimeout` khi server đã connect nhưng chậm trả lời sau `AUTH`.
- Tăng `mail.smtp.timeout` khi thực tế socket bị chặn lúc truyền attachment.
- Đặt timeout thấp hơn độ trễ bình thường, khiến retry liên tục và tăng tải.
- Cho rằng `timeout=10000` có nghĩa toàn bộ `send()` chỉ kéo dài 10 giây.
- Retry mọi lỗi ngay lập tức mà không tính khả năng server đã nhận thư sau `DATA`.
- Xem một lần `JavaMailSender.send()` thành công là bằng chứng email đã đến inbox.

## 15. Tổng hợp qua ba câu hỏi chẩn đoán

**Ứng dụng chưa mở được đường TCP tới SMTP?** Xem `mail.smtp.connectiontimeout`, cấu hình host/port và đường mạng.

**Đã kết nối nhưng không nhận phản hồi của SMTP server?** Xem `mail.smtp.timeout`, giai đoạn lệnh SMTP đang đợi và phản hồi từ server.

**Đang truyền nội dung mà socket không ghi tiếp được?** Xem `mail.smtp.writetimeout`, kích thước MIME, tốc độ đường truyền và trạng thái server.

Một điểm khởi đầu trong Spring Boot có thể là:

```properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Sau đó điều chỉnh bằng số liệu thực tế. **Connection timeout** bảo vệ bước mở TCP; **read timeout** bảo vệ thao tác chờ dữ liệu; **write timeout** bảo vệ thao tác truyền dữ liệu. Cả ba giảm nguy cơ I/O bị treo, nhưng để hệ thống email hoạt động ổn định vẫn cần giới hạn tổng thời gian công việc, retry có kiểm soát, quản lý tài nguyên và đối soát kết quả gửi.
