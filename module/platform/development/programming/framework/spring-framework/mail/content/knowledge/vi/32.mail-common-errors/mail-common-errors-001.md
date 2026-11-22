# Cấu hình đúng host nhưng quên port hoặc protocol

Trong **Spring Framework Mail**, việc đặt đúng `spring.mail.host` là cần thiết nhưng **chưa đủ** để gửi email thành công. Một SMTP endpoint được xác định bởi **hostname, port, transport protocol, cách khởi tạo TLS và cơ chế xác thực**. Nếu chỉ nhập hostname mà bỏ qua các phần còn lại, ứng dụng có thể kết nối vào cổng mặc định không được provider hỗ trợ, chờ mãi một phản hồi không bao giờ tới, gặp lỗi TLS handshake hoặc bị từ chối xác thực.

Ví dụ, một nhà cung cấp có thể công bố cùng hostname `smtp.example.net` nhưng hai cách submission khác nhau:

- `smtp.example.net:587`: bắt đầu phiên SMTP thông thường, sau đó dùng **STARTTLS** để nâng cấp lên TLS trước khi xác thực.
- `smtp.example.net:465`: bắt đầu **TLS ngay khi TCP kết nối**, thường gọi là implicit TLS hoặc submissions.

Nếu ứng dụng kết nối đúng host nhưng dùng port 25 mặc định, hoặc kết nối port 465 mà không bật implicit TLS, DNS vẫn có thể phân giải bình thường, nhưng phiên gửi sẽ thất bại. Đây là một lỗi thường gặp vì thông báo lỗi xuất hiện ở tầng **TCP, TLS, SMTP hoặc AUTH**, trong khi nhà phát triển chỉ kiểm tra hostname.

Bài học này giải thích cách phân biệt các cổng và chế độ kết nối, cấu hình đúng trong Spring Boot và `JavaMailSenderImpl`, đọc thông báo lỗi, kiểm tra từ đúng môi trường chạy, viết test ngăn tái phát, cũng như xử lý sự cố trong hệ thống gửi email có queue/retry.

> **Phạm vi:** Bài tập trung vào **SMTP outbound submission** qua Spring Mail. Khi nhắc đến IMAP/POP3 hoặc HTTP email API, chúng ta sẽ làm rõ rằng đây là những giao thức **khác**, không thể thay thế `smtp` chỉ bằng một tên host giống nhau. Các hostname, tài khoản và domain trong ví dụ đều là giả định.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một hostname đúng không chứng minh kết nối SMTP đúng.
2. Phân biệt SMTP relay trên port 25, SMTP submission STARTTLS trên port 587 và implicit TLS trên port 465.
3. Phân biệt giá trị `spring.mail.protocol=smtp` với TLS mode `mail.smtp.starttls.*` và `mail.smtp.ssl.*`.
4. Hiểu các giá trị mặc định của `JavaMailSenderImpl` khi không chỉ định port.
5. Cấu hình `application.yml` đúng cho 587/STARTTLS và 465/implicit TLS.
6. Đặt các property TLS, hostname verification, SMTP AUTH và timeout một cách nhất quán.
7. Nhận biết tình huống sử dụng protocol `smtps` và yêu cầu đổi prefix JavaMail properties.
8. Tránh nhầm `server.port`, `spring.mail.port`, `mail.smtp.port` hoặc port của HTTP API.
9. Phân biệt lỗi DNS, TCP, TLS, EHLO/STARTTLS, AUTH, relay permission và message delivery.
10. Chẩn đoán kết nối bằng PowerShell, OpenSSL và log có kiểm soát.
11. Viết unit/integration tests xác minh đúng tổ hợp host/port/protocol/TLS.
12. Thiết kế timeout, retry và vận hành an toàn khi provider SMTP không khả dụng.

## 2. Một kết nối SMTP gồm những lựa chọn nào?

Hãy hình dung cấu hình outbound thành một bộ dữ liệu:

```text
SMTP connection profile
|
+-- Hostname: smtp.example.net
|
+-- TCP port: 587
|
+-- Transport protocol: smtp
|
+-- TLS mode: STARTTLS_REQUIRED
|
+-- Authentication: username/password or OAuth2
|
+-- Certificate/hostname verification: enabled
|
+-- Connect/read/write timeouts
|
+-- Sender identity / envelope sender / provider policy
```

Lớp nào sai đều có thể làm `JavaMailSender.send(...)` thất bại. Ví dụ:

| Thành phần | Giá trị đúng có thể là | Thiếu hoặc sai dẫn đến |
|---|---|---|
| Host | `smtp.example.net` | Không phân giải DNS, nhầm endpoint |
| Port | `587` | Có thể thử port 25 không mong muốn |
| Transport protocol | `smtp` | Không tìm đúng provider hoặc dùng wrong property namespace |
| TLS mode | STARTTLS required | Kết nối mã hóa không được thiết lập đúng |
| Authentication | Account được cấp quyền | SMTP `535`, `530` hoặc từ chối relay |
| Hostname verification | Bật, SAN khớp hostname | TLS không tin cậy hoặc nguy cơ MITM |
| Timeouts | Giới hạn phù hợp | Worker chờ quá lâu, backlog tăng |
| Sender/domain | Đã xác thực ở provider | Bị từ chối gửi hoặc fail SPF/DKIM/DMARC |

**Host, port và protocol phải được xem là một nhóm cấu hình không thể tách rời.** Không nên chỉ thay host rồi tái sử dụng mù quáng port/TLS mode của provider cũ.

## 3. Cổng SMTP phổ biến và mục đích

| Cổng | Mục đích phổ biến | Bắt đầu phiên | Gợi ý cho Spring Mail |
|---|---|---|---|
| **25** | SMTP server-to-server/relay, đôi khi relay nội bộ | SMTP plaintext ban đầu; có thể STARTTLS | Chỉ dùng khi provider/hạ tầng **cho phép rõ ràng** |
| **587** | **SMTP message submission** | SMTP greeting/EHLO rồi **STARTTLS** | `protocol=smtp`, `starttls.enable=true`, `starttls.required=true` |
| **465** | **Message submission over implicit TLS** | **TLS handshake ngay sau TCP connect** | `protocol=smtp` + `mail.smtp.ssl.enable=true`, hoặc `smtps` nếu cấu hình nhất quán |
| **2525** | Port thay thế ở một số dịch vụ | Tùy provider | Chỉ sử dụng theo tài liệu endpoint cụ thể |

Không có quy tắc rằng mọi hostname đều nghe trên tất cả các cổng. Cũng không nên coi port 2525 là một chuẩn bảo đảm STARTTLS hoặc implicit TLS; một số provider dùng nó vì chính sách mạng nhưng semantics phải kiểm tra riêng.

### 3.1. Port 25 không phải lựa chọn mặc định cho mọi ứng dụng

Port 25 thường liên quan truyền thư giữa các SMTP servers hoặc relay nội bộ. Nhiều môi trường cloud/network hạn chế outbound port 25. Dù SMTP endpoint của provider có hỗ trợ port 25, nó có thể không chấp nhận AUTH hoặc submission từ ứng dụng bằng cách bạn mong muốn.

Vì vậy **không dựa vào default port 25** cho email giao dịch gửi tới dịch vụ submission trừ khi có tài liệu cho phép.

### 3.2. Port 587: STARTTLS

Ứng dụng kết nối TCP, đọc greeting SMTP, trao đổi EHLO và yêu cầu nâng cấp TLS bằng `STARTTLS`. Sau khi TLS hợp lệ, client thực hiện SMTP AUTH nếu provider yêu cầu.

### 3.3. Port 465: implicit TLS

Ngay sau khi TCP kết nối, client phải khởi tạo TLS handshake. Nếu phía client chờ greeting SMTP plaintext, còn phía server chờ TLS ClientHello, hai phía có thể chờ nhau đến timeout.

### 3.4. Cổng không quyết định toàn bộ chính sách

Không nên viết code kiểu:

```java
if (port == 465) {
    // Tự suy đoán mọi capability hoặc credential.
}
```

Port là một thông số quan trọng, nhưng **hồ sơ cấu hình do provider công bố** vẫn là nguồn quyết định TLS mode, AUTH, hostname và quyền gửi.

## 4. Vì sao quên port thường dẫn đến port 25?

Trong cách dùng phổ biến với Spring `JavaMailSenderImpl`, nếu không cấu hình port tường minh, giá trị nội bộ có thể ở dạng `-1` để Jakarta Mail/provider sử dụng mặc định.

Đối với transport `smtp` thông thường, cổng mặc định thường là **25**. Do đó:

```yaml
spring:
  mail:
    host: smtp.example.net
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
```

**không có nghĩa** Spring Boot sẽ tự chọn port 587 chỉ vì đã khai báo username và password. Thư viện không thể tự biết nhà cung cấp đang yêu cầu 587 hay 465.

Đường đi có thể là:

```text
spring.mail.host = smtp.example.net
spring.mail.port = not configured
spring.mail.protocol = smtp (typical default)
                 |
                 v
JavaMailSenderImpl: no explicit port
                 |
                 v
SMTP provider default port: often 25
                 |
                 v
Cloud/network blocks port 25
or provider rejects submission
                 |
                 v
MailSendException / connection timeout / refused
```

### 4.1. Tại sao lỗi này dễ bị bỏ qua?

- Host đúng và DNS trả IP nên người phát triển tưởng cấu hình đã hoàn chỉnh.
- Máy local có thể cho phép port 25 nhưng cloud production lại chặn.
- Một số SMTP sandbox mặc định dùng port động hoặc 1025, khiến cấu hình test khác production.
- Email service mới có cùng hostname gần giống service cũ nhưng khác port/TLS.
- Username/password có sẵn làm người phát triển giả định thư viện tự chọn submission port.
- Log chỉ ghi “Could not connect to SMTP host” mà không được đọc đến phần `port: 25`.

### 4.2. Đọc port trong exception

Khi gặp lỗi kiểu:

```text
MailSendException: Mail server connection failed
...
Could not connect to SMTP host: smtp.example.net, port: 25
```

thông tin đáng chú ý là **port 25**, không chỉ hostname. Trước khi thay password, cần hỏi vì sao ứng dụng lại cố đi cổng đó.

### 4.3. Mặc định không thay thế cấu hình có chủ đích

Có nhiều versions Spring/Jakarta Mail và nhiều transport providers. Nếu dùng `smtps`, port mặc định có thể khác. Vì vậy hãy **đặt port tường minh trong hồ sơ production** và xác minh bằng integration test, thay vì phụ thuộc vào mặc định của thư viện.

## 5. Protocol của Jakarta Mail và TLS mode không phải một thứ

Trong Spring Boot có:

```yaml
spring:
  mail:
    protocol: smtp
```

Còn trong JavaMail properties có:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
mail.smtp.ssl.enable=false
```

Đây là hai lớp cấu hình khác nhau:

- **`spring.mail.protocol=smtp`:** chọn Jakarta Mail transport provider dùng SMTP.
- **`mail.smtp.starttls.enable=true`:** yêu cầu cơ chế nâng cấp TLS trong SMTP session.
- **`mail.smtp.ssl.enable=true`:** yêu cầu khởi tạo SSL/TLS ngay từ đầu cho `smtp` transport.

### 5.1. Dùng protocol smtp cho cả 587 và 465 được không?

**Có**, trong cách cấu hình thông dụng:

- Cổng 587: `protocol=smtp` + STARTTLS.
- Cổng 465: `protocol=smtp` + implicit TLS bật qua `mail.smtp.ssl.enable=true`.

Điều quan trọng là **chọn đúng TLS mode**, không nhất thiết phải chuyển `spring.mail.protocol` từ `smtp` sang `smtps` để dùng port 465.

### 5.2. Protocol smtps là gì?

Một số Jakarta Mail implementations cung cấp transport `smtps` như SMTP với SSL/TLS ngay khi kết nối. Khi chọn:

```yaml
spring:
  mail:
    protocol: smtps
```

cần đảm bảo provider/implementation hỗ trợ transport `smtps` và **các mail properties sử dụng đúng prefix `mail.smtps.*`**, thay vì giữ nhầm toàn bộ `mail.smtp.*`.

Ví dụ, `mail.smtp.auth=true` không nhất thiết điều khiển `smtps` transport vì provider có thể đọc `mail.smtps.auth`. Sự khác biệt về prefix có thể làm AUTH/timeouts/TLS checks không được áp dụng như dự định.

Với nhiều ứng dụng Spring Boot, cách đơn giản hơn là **giữ `protocol=smtp`** và bật implicit TLS bằng `mail.smtp.ssl.enable=true` trên port 465.

### 5.3. IMAP/POP3 không phải SMTP transport

- `imap`/`imaps`: đọc mailbox qua Jakarta Mail `Store`.
- `pop3`/`pop3s`: đọc mailbox qua Jakarta Mail `Store`.
- `smtp`/`smtps`: gửi thư qua Jakarta Mail `Transport`.

Không đặt `spring.mail.protocol=imaps` trong `JavaMailSenderImpl` với hy vọng gửi email bằng mailbox server. Spring Mail outbound cần một transport phù hợp cho việc gửi.

## 6. Cấu hình chuẩn: SMTP 587 với STARTTLS bắt buộc

Ví dụ Spring Boot:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
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
          timeout: 10000
          writetimeout: 10000
```

Giải thích:

| Property | Ý nghĩa |
|---|---|
| `spring.mail.host` | Host của SMTP submission endpoint |
| `spring.mail.port=587` | TCP port tường minh |
| `spring.mail.protocol=smtp` | Transport provider SMTP |
| `spring.mail.username/password` | Credential được cấp bởi SMTP provider |
| `mail.smtp.auth=true` | Bật SMTP AUTH khi provider yêu cầu |
| `mail.smtp.starttls.enable=true` | Cho phép yêu cầu STARTTLS |
| `mail.smtp.starttls.required=true` | Không tiếp tục nếu không thể nâng cấp STARTTLS |
| `mail.smtp.ssl.checkserveridentity=true` | Kiểm tra hostname với chứng chỉ TLS |
| `mail.smtp.connectiontimeout` | Timeout TCP connect tính bằng mili giây |
| `mail.smtp.timeout` | Timeout socket read tính bằng mili giây |
| `mail.smtp.writetimeout` | Timeout socket write tính bằng mili giây |

### 6.1. Vì sao phải có cả enable và required?

Nếu chỉ đặt:

```properties
mail.smtp.starttls.enable=true
```

một số hành vi mặc định có thể cho phép tiếp tục mà không STARTTLS khi server không quảng bá hoặc nâng cấp không khả dụng. Với endpoint mà chính sách yêu cầu TLS, đặt:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

để **fail closed** thay vì silently fallback sang plaintext.

### 6.2. Hostname verification vẫn là bắt buộc

TLS chỉ mã hóa phiên chưa đủ để bảo đảm kết nối đến đúng máy chủ. Cần kiểm tra certificate trust chain và tên host trong SAN của chứng chỉ.

Vì vậy:

```properties
mail.smtp.ssl.checkserveridentity=true
```

là một thành phần quan trọng khi gửi thông tin đăng nhập và nội dung qua mạng.

### 6.3. Đừng bật ssl.enable trên cổng chỉ chờ STARTTLS

Đây là lỗi:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    properties:
      mail:
        smtp:
          ssl:
            enable: true
```

Nếu server trên port 587 đang đợi SMTP greeting/EHLO/STARTTLS mà client bắt đầu TLS ngay lập tức, handshake sẽ không đi theo đúng protocol. Hậu quả có thể là `SSLException`, timeout hoặc connection reset.

**587 + STARTTLS** và **465 + implicit TLS** là hai mô hình khởi tạo khác nhau.

## 7. Cấu hình chuẩn: SMTP 465 với implicit TLS

Nếu provider công bố endpoint TLS ngay khi kết nối:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 465
    protocol: smtp
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

Luồng kết nối:

```text
JavaMailSenderImpl                     SMTP :465
         |                                  |
         +------- TCP connect ------------>|
         |                                  |
         +======= TLS handshake ===========|
         |         certificate verify      |
         |                                  |
         +------- SMTP EHLO -------------->|
         +------- AUTH ------------------->|
         +------- MAIL FROM/RCPT TO ------>|
         +------- DATA ------------------->|
         |<------ final acceptance --------|
```

Ở đây, không dùng STARTTLS như cách khởi tạo chính; TLS đã tồn tại trước khi ứng dụng trao đổi lệnh SMTP.

### 7.1. Lỗi phổ biến khi chỉ đổi port thành 465

Không đủ nếu chỉ sửa:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 465
```

mà vẫn để `mail.smtp.ssl.enable` ở mặc định false.

Client có thể chờ greeting SMTP plaintext, trong khi server trên 465 chờ TLS ClientHello. Cả hai đều có thể chờ đến khi hết timeout.

### 7.2. Có nên bật cả STARTTLS và implicit TLS?

Không nên bật cả hai như một mẹo “chắc chắn có TLS”. Chọn đúng mode theo endpoint:

- `smtp + 587 + starttls.enable/required`.
- `smtp + 465 + ssl.enable`.

Kết hợp các cờ vô tội vạ khiến vận hành khó giải thích và dễ vô tình dựa vào hành vi của provider version cụ thể.

### 7.3. Cấu hình hoàn chỉnh mới là một profile hợp lệ

Một profile nên lưu cùng nhau:
- host;
- port;
- transport protocol;
- TLS mode;
- username/credential mechanism;
- sender identity;
- socket timeouts;
- hostname verification policy.

Không thay mỗi port hoặc mỗi host rời rạc khi xoay vòng provider.

## 8. Trường hợp port 25: relay nội bộ hoặc mail server

Nếu tổ chức có relay nội bộ công bố port 25, có thể có cấu hình riêng:

```yaml
spring:
  mail:
    host: relay.internal.example
    port: 25
    protocol: smtp
    properties:
      mail:
        smtp:
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
```

Ví dụ này **giả định relay nội bộ hỗ trợ STARTTLS và được yêu cầu dùng TLS**. SMTP AUTH có thể do relay yêu cầu hoặc không; đó là chính sách mạng/tài khoản cụ thể, không thể suy ra từ port 25.

### 8.1. Không tự tắt TLS chỉ vì relay nằm trong VPC

Mạng nội bộ không tự động bảo đảm danh tính server hoặc chống nghe lén. Hãy theo yêu cầu bảo mật và khả năng thực tế của relay. Nếu relay không hỗ trợ STARTTLS, cần quyết định kiến trúc/hạ tầng phù hợp thay vì âm thầm bỏ `required=true` để “chữa lỗi”.

### 8.2. Môi trường cloud có thể hạn chế port 25

Một SMTP relay đang hoạt động trên máy phát triển không chứng minh ứng dụng sẽ kết nối thành công từ cloud provider, container cluster, mạng doanh nghiệp hoặc môi trường CI. Các môi trường có thể có egress policies khác nhau.

Hãy kiểm tra từ **nơi app thực sự chạy** và làm việc với network/provider theo cách được phê duyệt; không thay bừa port hoặc hướng email sang endpoint không được phép.

## 9. Sơ đồ handshake: nhận diện sai mode

### 9.1. STARTTLS đúng trên port 587

```text
Client                               Server :587
  |---- TCP connection ---------------->|
  |<--- 220 SMTP service ready ---------|
  |---- EHLO app.example -------------->|
  |<--- 250-STARTTLS -------------------|
  |---- STARTTLS ---------------------->|
  |<--- 220 Ready to start TLS ---------|
  |==== TLS handshake ==================|
  |---- EHLO again (inside TLS) ------->|
  |---- AUTH (inside TLS) ------------->|
  |---- MAIL FROM / RCPT TO / DATA ---->|
  |<--- final SMTP response -----------|
```

Đây là sơ đồ khái niệm; reply và EHLO capabilities thực tế phụ thuộc server. Điểm quan trọng là **TLS bắt đầu sau STARTTLS**.

### 9.2. Implicit TLS đúng trên port 465

```text
Client                               Server :465
  |---- TCP connection ---------------->|
  |==== TLS handshake ==================|
  |<--- SMTP greeting (inside TLS) -----|
  |---- EHLO (inside TLS) ------------->|
  |---- AUTH (inside TLS) ------------->|
  |---- MAIL FROM / RCPT TO / DATA ---->|
```

### 9.3. Sai: SMTP plaintext tới port 465

```text
Client                               Server :465
  |---- TCP connection ---------------->|
  |---- waits for SMTP greeting         |
  |                                     | waits for TLS ClientHello
  |............. timeout ...............|
```

### 9.4. Sai: TLS ngay lập tức tới port 587

```text
Client                               Server :587
  |---- TCP connection ---------------->|
  |==== sends TLS ClientHello ========>| expects SMTP exchange
  |<--- invalid response/reset ---------|
```

Thông điệp lỗi ở hai tình huống sai có thể khác nhau theo JVM, provider, proxy và thời điểm ngắt kết nối. **Không chỉ dựa vào một dòng exception; hãy đối chiếu port và TLS mode trước.**

## 10. Sai khác giữa server.port và spring.mail.port

Một lỗi nhìn qua đơn giản:

```yaml
server:
  port: 587

spring:
  mail:
    host: smtp.example.net
```

`server.port` là **cổng HTTP/HTTPS mà Spring Boot web server lắng nghe**. Nó không cấu hình cổng đích SMTP.

Nếu đặt `server.port=587`, ứng dụng web có thể cố bind port 587 trên máy chạy, trong khi sender vẫn không được cấu hình port SMTP đúng.

Cấu hình cần là:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
```

Giữ `server.port` cho HTTP API (ví dụ 8080) nếu ứng dụng có web server.

### 10.1. Đừng nhầm port phía client với port bên ngoài container

Các mục sau khác nhau:
- HTTP service port của app;
- cổng SMTP provider ở Internet;
- cổng relay nội bộ;
- cổng được Docker compose publish;
- cổng của một SMTP sandbox dùng trong test.

Một container chạy ứng dụng muốn gửi mail ra `smtp.example.net:587` cần **outbound network access** đến endpoint đó; không phải chỉ mapping `-p 587:587` trên container.

### 10.2. Không nhầm Spring Mail với HTTP email API

Nếu nhà cung cấp cho endpoint `https://api.provider.example/v1/send`, đó là **HTTP API**. Không điền hostname API vào `spring.mail.host` và để `JavaMailSender` cố kết nối qua SMTP port 587 hoặc 465.

Dùng SMTP endpoint do provider công bố, hoặc dùng HTTP client/SDK riêng nếu chọn API.

## 11. Sai khác giữa spring.mail.port và mail.smtp.port

Trong Spring Boot, cách rõ ràng và phổ biến là:

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
```

Bạn có thể thấy Jakarta Mail có các properties như `mail.smtp.port`. Nhưng khi dùng `JavaMailSenderImpl`, trường port được cấu hình tường minh trên sender có thể được truyền trực tiếp tới transport connect.

Vì vậy đừng cấu hình hai nguồn giá trị mâu thuẫn:

```yaml
spring:
  mail:
    port: 587
    properties:
      mail:
        smtp:
          port: 465
```

Người vận hành sẽ khó biết port nào thực sự được dùng. Tốt nhất:
1. Dùng `spring.mail.port` để cấu hình Spring Boot mail sender.
2. Dùng `spring.mail.properties.mail.smtp.*` cho TLS, AUTH và timeout phù hợp.
3. Không khai báo port thứ hai nếu không có yêu cầu cụ thể và hiểu rõ precedence của implementation.

### 11.1. Property transport.protocol cũng có thể gây nhầm

`spring.mail.protocol` là thuộc tính Boot dành cho `JavaMailSenderImpl`. Một property Jakarta Mail như `mail.transport.protocol` thuộc ngữ cảnh Session/Transport. Cấu hình song song hai nguồn có thể khiến người đọc không biết runtime đã chọn provider nào.

Hãy sử dụng một nơi cấu hình protocol, xác minh qua bean và test.

## 12. Lỗi thụt lề YAML và prefix sai

YAML nested properties được Spring Boot bind thành keys của Jakarta Mail. Ví dụ:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          starttls:
            enable: true
            required: true
```

tương ứng các keys:

```properties
mail.smtp.starttls.enable=true
mail.smtp.starttls.required=true
```

### 12.1. Sai: properties ngoài spring.mail

```yaml
spring:
  mail:
    host: smtp.example.net
    port: 587

mail:
  smtp:
    starttls:
      enable: true
```

Tùy cấu hình ứng dụng, phần `mail.smtp.*` ở top-level này **không tự động** nằm trong `spring.mail.properties` của sender. Kết quả: host/port đúng nhưng STARTTLS không được áp dụng.

### 12.2. Sai: viết nhầm starttls

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          startTLS:
            enabled: true
```

Jakarta Mail chờ các property keys như `mail.smtp.starttls.enable`, không phải một alias tùy ý `startTLS.enabled`. Tên property tùy thư viện; không suy ra từ cấu trúc YAML mà bỏ qua tên chuẩn.

### 12.3. Sai: port dưới nhánh properties không chủ đích

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          port: 587
```

Nếu dùng Spring Boot auto-config, thường nên đặt port ở `spring.mail.port` để tránh dựa vào tiền lệ của provider. Điều quan trọng là **đặt đúng thuộc tính mà sender instance thực sự dùng**.

### 12.4. Sai: property của smtp nhưng protocol smtps

```yaml
spring:
  mail:
    protocol: smtps
    port: 465
    properties:
      mail:
        smtp:
          auth: true
          timeout: 10000
```

`smtps` provider có thể đọc `mail.smtps.*`; các settings dưới `mail.smtp.*` không được áp dụng như mong muốn.

Nếu chọn `smtps` có chủ đích, phải cấu hình property namespace tương ứng và test. Nếu không có lý do khác, dùng `protocol=smtp` + `mail.smtp.ssl.enable=true` trên port 465 để giảm nhầm lẫn.

## 13. Ví dụ JavaMailSenderImpl cấu hình tường minh

Không dùng Spring Boot auto-config? Có thể khai báo sender bean:

```java
package com.example.mail;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class OutboundSmtpConfiguration {

    @Bean
    public JavaMailSender javaMailSender(
            SmtpEndpointProperties config) {

        JavaMailSenderImpl sender =
            new JavaMailSenderImpl();

        sender.setHost(config.host());
        sender.setPort(config.port());
        sender.setProtocol("smtp");
        sender.setUsername(config.username());
        sender.setPassword(config.password());
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();

        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        if (config.tlsMode() == TlsMode.IMPLICIT_TLS) {
            props.put("mail.smtp.ssl.enable", "true");
        } else if (config.tlsMode() == TlsMode.STARTTLS) {
            props.put("mail.smtp.starttls.enable", "true");
            props.put("mail.smtp.starttls.required", "true");
        } else {
            throw new IllegalArgumentException(
                "SMTP TLS mode is not approved"
            );
        }

        return sender;
    }
}
```

`SmtpEndpointProperties` và `TlsMode` trong ví dụ là **model do ứng dụng định nghĩa**, không phải những class có sẵn của Spring Framework.

### 13.1. Ví dụ model có validation

```java
package com.example.mail;

public enum TlsMode {
    STARTTLS,
    IMPLICIT_TLS
}

public record SmtpEndpointProperties(
    String host,
    int port,
    String username,
    String password,
    TlsMode tlsMode
) {
    public SmtpEndpointProperties {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("SMTP host required");
        }

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid SMTP port");
        }

        if (tlsMode == null) {
            throw new IllegalArgumentException("SMTP TLS mode required");
        }
    }
}
```

Với provider yêu cầu OAuth2 hoặc một relay nội bộ không AUTH, factory cần mở rộng contract. Không hardcode rằng mọi SMTP endpoint dùng username/password.

### 13.2. Vì sao validate port sớm?

Nếu port bỏ trống, một ứng dụng có thể rơi về default 25 mà không cảnh báo. Một model custom có thể **bắt buộc phải cung cấp port** ở startup và fail ngay, trước khi đến giờ gửi các email quan trọng.

Đừng dựa vào lỗi `MailSendException` đầu tiên xảy ra trong production để phát hiện cấu hình thiếu.

### 13.3. Cấu hình bất biến sau startup

Một `JavaMailSender` bean dùng chung nên được coi là ổn định về host, port, protocol, TLS và credential khi nhiều threads đang gửi. Không thay `sender.setPort(...)` trong một request khi request khác đã bắt đầu submit.

Nếu có nhiều SMTP profiles, dùng nhiều sender instances/registry được cấu hình riêng, không thay đổi cài đặt của một singleton theo từng email.

## 14. Spring Boot auto-configuration và custom bean

Khi có `spring-boot-starter-mail`, Spring Boot thường hỗ trợ tự cấu hình `JavaMailSender` dựa trên mail settings và điều kiện auto-config.

Nhưng nếu ứng dụng đã tự khai báo một bean `JavaMailSender` hoặc `JavaMailSenderImpl`, auto-config có thể **không tạo thêm sender mặc định**, tùy điều kiện của phiên bản Boot.

Hậu quả: chỉnh `spring.mail.port=587` trong `application.yml` nhưng custom bean vẫn dùng port 25 hoặc host hardcoded.

### 14.1. Tìm cấu hình đang thực sự được dùng

Các điểm cần xác minh theo dự án:
- Có custom `@Bean JavaMailSender` không?
- Có nhiều `JavaMailSender` beans/`@Qualifier` không?
- Có `MailSenderFactory` tự tạo sender theo tenant không?
- Có bean được tạo bằng `new JavaMailSenderImpl()` ngay trong business method không?
- Code có gọi `sender.setHost/setPort` sau khi bind config không?
- Có profile/test configuration override bean mặc định không?

Không chỉ đọc YAML rồi kết luận tất cả worker dùng sender đó.

### 14.2. Đọc endpoint đã cấu hình mà không lộ secret

Với một bean `JavaMailSenderImpl`, có thể quan sát host/port/protocol mà không log credential:

```java
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class MailConfigDiagnostics {

    public static String summary(
            JavaMailSenderImpl sender) {
        return "SMTP endpoint: host=" + sender.getHost()
            + ", port=" + sender.getPort()
            + ", protocol=" + sender.getProtocol();
    }
}
```

Mẫu này dùng để hỗ trợ diagnostics, **không phải cấp quyền expose config qua HTTP endpoint công khai**. Không gọi `getPassword()` hay in toàn bộ `Properties` vì có thể chứa thông tin nhạy cảm.

### 14.3. Port -1 là tín hiệu cần chú ý

Nếu log/snapshot cho thấy sender port `-1`, nghĩa là chưa có explicit port ở tầng sender. Transport provider có thể sử dụng default theo protocol.

Đây không nhất thiết là lỗi trong mọi môi trường nhưng là dấu hiệu nên xem lại khi dịch vụ submission yêu cầu port 587/465.

## 15. DNS đúng chưa đủ để chứng minh SMTP hoạt động

Giả sử:

```powershell
Resolve-DnsName smtp.example.net
```

trả địa chỉ IPv4/IPv6 hợp lệ.

Điều này chỉ chứng minh DNS resolution từ môi trường đang kiểm tra. Nó **không xác nhận**:
- port 587/465 có mở;
- firewall cho phép outbound;
- TLS mode đúng;
- certificate khớp hostname;
- SMTP AUTH hợp lệ;
- From domain được phép;
- provider đang nhận messages.

### 15.1. MX record không phải submission host

Một domain email `example.com` có thể có MX:

```text
example.com MX 10 inbound-mail.provider.example
```

Đó là nơi mail servers gửi thư **đến domain này**, không nhất thiết là endpoint ứng dụng phải dùng để **submit mail đi**.

Không tự lấy MX host rồi gán vào `spring.mail.host` khi provider đã công bố hostname submission riêng.

### 15.2. CNAME, proxy và hostname TLS

Một hostname có thể trỏ qua CNAME hoặc load balancer. Khi kiểm tra certificate, thường phải xác minh **hostname mà client sử dụng để kết nối**, ví dụ `smtp.example.net`, không tự thay bằng hostname backend chỉ vì DNS trả CNAME.

Nếu certificate không chứa SAN phù hợp, cần sửa certificate/endpoint hoặc cấu hình theo provider, không tắt hostname verification.

## 16. Kiểm tra port bằng PowerShell

Trên Windows (PowerShell) có thể thử:

```powershell
Test-NetConnection smtp.example.net -Port 587
```

Khi thành công:

```text
ComputerName     : smtp.example.net
RemotePort       : 587
TcpTestSucceeded : True
```

Điều đó chứng minh TCP connect tới IP/port đã kiểm tra tại thời điểm test. **Nó không chứng minh STARTTLS, AUTH hoặc SMTP submission sẽ thành công.**

So sánh cả cổng dự định và cổng ứng dụng thực sự đang thử:

```powershell
Test-NetConnection smtp.example.net -Port 25
Test-NetConnection smtp.example.net -Port 587
Test-NetConnection smtp.example.net -Port 465
```

Không nên quét bừa những địa chỉ không thuộc quyền quản trị; chỉ kiểm tra các endpoints mà tổ chức được phép kết nối.

### 16.1. Dùng chính môi trường production/test workload

Một lệnh trên laptop thành công không chứng minh pod Kubernetes cũng kết nối được. Các yếu tố khác nhau:
- source IP/egress NAT;
- VPC/subnet/firewall;
- corporate proxy;
- DNS resolver;
- IPv4/IPv6 route;
- allowlist của provider;
- container security policy.

Nếu được phép, hãy chẩn đoán từ cùng môi trường chạy app hoặc một diagnostic container có network policies tương đương.

### 16.2. Kết quả từ PowerShell cần diễn giải cẩn thận

| Kết quả | Ý nghĩa có thể |
|---|---|
| `TcpTestSucceeded=True` | TCP có thể mở đến endpoint |
| `False` | Port không reachable từ môi trường test hoặc bị từ chối |
| Timeout | Network/filter/route/server không phản hồi |
| Connection refused | Có phản hồi từ chối tại địa chỉ/port, thường không có service lắng nghe hoặc policy từ chối |

Không đủ dữ liệu để kết luận chính xác “firewall X đang chặn” nếu chỉ có một timeout.

## 17. Kiểm tra STARTTLS bằng OpenSSL

Với SMTP submission port 587:

```bash
openssl s_client \
  -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -verify_return_error
```

Các thành phần:
- `-starttls smtp`: thực hiện phần SMTP plaintext cần thiết rồi nâng cấp sang TLS.
- `-connect`: hostname/port thực tế.
- `-servername`: SNI server name khi có hỗ trợ.
- `-verify_hostname`: xác minh certificate hợp lệ cho hostname.
- `-verify_return_error`: không tiếp tục im lặng khi có lỗi xác minh chứng chỉ.

Kết quả thành công ở đây chứng minh TLS negotiation và kiểm tra chứng chỉ theo môi trường test; nó không tự chứng minh có thể xác thực SMTP AUTH hay gửi email với From domain đã chọn.

### 17.1. Test đúng hostname

Dùng đúng hostname và port mà `JavaMailSender` dùng. Đừng kiểm tra `smtp-a.example.net` trong terminal nhưng app lại đọc override thành `smtp-b.example.net`.

### 17.2. Đọc lỗi TLS

Một số dấu hiệu:
- `certificate verify failed`;
- hostname mismatch;
- `wrong version number`;
- handshake failure;
- unexpected EOF hoặc reset.

Lỗi phụ thuộc TLS mode, certificate, proxy và server; không nên gán tất cả về cùng nguyên nhân.

### 17.3. Khác biệt truststore

OpenSSL và JVM có thể dùng các trust anchors khác nhau. OpenSSL thành công **không bảo đảm Java runtime với truststore riêng cũng thành công**. Nếu Java báo `PKIX path building failed`, cần kiểm tra CA chain và JDK truststore cụ thể đang chạy.

## 18. Kiểm tra implicit TLS trên port 465

Với implicit TLS, **không thêm `-starttls smtp`**:

```bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net \
  -verify_hostname smtp.example.net \
  -verify_return_error
```

OpenSSL bắt đầu TLS ngay, tương ứng với cách server port 465 chờ client.

### 18.1. So sánh hai lệnh

**Đúng cho 587/STARTTLS:**

```bash
openssl s_client -starttls smtp \
  -connect smtp.example.net:587 \
  -servername smtp.example.net
```

**Đúng cho 465/implicit TLS:**

```bash
openssl s_client \
  -connect smtp.example.net:465 \
  -servername smtp.example.net
```

Nếu đổi hai lệnh cho nhau, lỗi có thể rất giống lỗi cấu hình trong Spring Mail. Đây là cách nhận biết phần nào server đang kỳ vọng, nhưng vẫn phải đối chiếu tài liệu provider.

### 18.2. Không đưa credential vào log chẩn đoán

Không gõ SMTP password/app password vào transcript được lưu chung hoặc chụp màn hình. Để kiểm tra AUTH thực sự, dùng ứng dụng test đã được bảo vệ hoặc công cụ chuyên dụng có redaction/secrets management thích hợp.

### 18.3. TLS test không có nghĩa đã gửi email

`openssl s_client` ở bước này mới kiểm tra network/protocol/TLS. Nó không chứng minh email accepted, delivered hoặc pass SPF/DKIM/DMARC.

## 19. Nhìn vào SMTP reply code đúng ngữ cảnh

Một số reply thường thấy:

| SMTP code | Ngữ cảnh thường gặp | Cần làm gì |
|---|---|---|
| `220` | Greeting hoặc sẵn sàng STARTTLS | Kiểm tra đang ở phase nào |
| `250` | EHLO capability, command success, final DATA acceptance | Phân biệt `250` của EHLO với `250` sau DATA |
| `334` | Tiếp tục một bước authentication challenge | Theo cơ chế AUTH thực tế |
| `421` | Service unavailable hoặc temporary shutdown | Backoff/health; không retry storm |
| `450`/`451` | Temporary failures | Xem phase và policy trước retry |
| `530` | Authentication hoặc TLS required | Kiểm tra AUTH/STARTTLS |
| `535` | Authentication rejected | Kiểm tra credential/scope/provider policy |
| `550`/`553`/`554` | Permanent rejection hoặc policy error | Xem full context; không retry mù |

SMTP reply code một mình có thể không đủ để chỉ ra sai port. Ví dụ `535` có thể xuất hiện vì password sai, token hết hạn, account bị khóa hoặc cơ chế AUTH không phù hợp. Việc đầu tiên là xác nhận app đã đến **đúng SMTP endpoint và TLS mode**.

### 19.1. 250 sau EHLO không phải accepted message

Nếu server trả:

```text
250-AUTH PLAIN LOGIN
250-STARTTLS
250 SIZE 20000000
```

đó là danh sách capabilities được quảng bá, không có nghĩa email đã được nhận vào queue. Một message chỉ có kết quả submission accepted khi server trả phản hồi phù hợp tại **giai đoạn hoàn tất DATA** hoặc cơ chế submission tương đương.

### 19.2. SMTP provider accepted không đồng nghĩa delivered

`JavaMailSender.send(message)` không ném exception thường cho biết submission đã hoàn tất theo transport API, **không** chứng minh recipient đã nhận trong Inbox. Provider có thể deferred, bounced hoặc bị spam-filter sau đó.

## 20. Ma trận triệu chứng → nguyên nhân có thể

| Triệu chứng/log | Điều cần kiểm tra trước | Sai cấu hình thường gặp |
|---|---|---|
| `Could not connect ... port: 25` | Port thực tế của sender | Thiếu `spring.mail.port` |
| `Connection refused` trên 587 | Endpoint/port, firewall | Provider chỉ dùng 465 hoặc host sai |
| Timeout trên 465 | TLS mode và network | Chưa bật `mail.smtp.ssl.enable` |
| `SSLException: wrong version number` | STARTTLS vs implicit TLS | Bật implicit TLS trên port 587 |
| `Unrecognized SSL message` | Server trả plaintext khi client đợi TLS | TLS mode không phù hợp |
| `Must issue a STARTTLS command first` | `starttls.enable/required` | Đang AUTH trước khi TLS |
| `STARTTLS is required but host does not support` | Đúng endpoint/capability | Kết nối sai port/server/proxy |
| `PKIX path building failed` | CA chain/truststore | Chứng chỉ server không được JDK tin |
| `No subject alternative names matching` | Hostname và certificate SAN | Host alias không khớp certificate |
| `AuthenticationFailedException` | AUTH/TLS/account policy | Credential hoặc cơ chế auth sai |
| `Could not convert socket to TLS` | Server STARTTLS và TLS context | TLS version/cert/proxy mismatch |
| `SendFailedException` | MAIL FROM/RCPT TO/DATA | Recipient/sender/relay policy |
| Local OK, production fail | Outbound firewall, DNS, IPv6, secrets | Environment differences |
| Chỉ fail sau rotation | Secret/config phiên bản mới, active sessions | Worker dùng mixed sender profiles |
| Không log được port | Custom sender config hoặc logging thiếu | Không chẩn đoán runtime |
| SMTP accepted nhưng không có Inbox | Delivery/bounce/suppression | Không phải lỗi port nhất thiết |

**Không dùng bảng như một bộ ánh xạ 1–1.** Một loại exception có nhiều nguyên nhân, đặc biệt khi giữa app và relay có proxy, firewall hoặc load balancer.

## 21. Quy trình chẩn đoán theo từng lớp

Để tránh đoán mò, hãy kiểm tra theo thứ tự:

```text
1. Xác nhận provider's documented endpoint
       |
       v
2. Xác định runtime host + port + protocol + TLS
       |
       v
3. Kiểm tra DNS resolution
       |
       v
4. Kiểm tra TCP connectivity từ workload
       |
       v
5. Kiểm tra SMTP greeting/STARTTLS hoặc implicit TLS
       |
       v
6. Kiểm tra CA + hostname verification
       |
       v
7. Kiểm tra SMTP AUTH
       |
       v
8. Kiểm tra MAIL FROM / RCPT TO policy
       |
       v
9. Kiểm tra DATA submission acceptance
       |
       v
10. Theo dõi delivery/bounce nếu cần
```

### 21.1. Bước 1: đọc tài liệu provider

Ghi lại:
- submission hostname;
- port 587/465 hay lựa chọn khác;
- STARTTLS hoặc implicit TLS;
- SMTP AUTH mechanism;
- credential format;
- verified sender;
- IP allowlist;
- quota và giới hạn kích thước.

Không tự lấy MX record làm submission hostname.

### 21.2. Bước 2: đối chiếu runtime

Đọc bean/settings thực tế, không chỉ source YAML. Tìm:
- environment override;
- Spring profiles;
- custom `JavaMailSender` bean;
- Secret/ConfigMap phiên bản cũ;
- Helm/Kubernetes values;
- deployment đang chạy bằng image khác;
- worker có profile riêng.

### 21.3. Bước 3: xác minh TCP

`Test-NetConnection` hoặc công cụ được phép trong environment cho biết port có reachable không. Không tự kết luận password sai khi TCP chưa kết nối được.

### 21.4. Bước 4: xác minh TLS

Dùng OpenSSL theo đúng mode của endpoint, rồi xác minh Java truststore/hostname. Không “chữa” bằng `ssl.trust=*`.

### 21.5. Bước 5: xác minh AUTH và sender

Nếu TLS thành công nhưng AUTH thất bại:
- xác định provider có yêu cầu app password/OAuth2 không;
- token có đúng scope không;
- account có bị disable không;
- login đã được cho phép từ source IP/region chưa;
- From domain có được phép hay không.

### 21.6. Bước 6: xác minh submission

Chỉ gửi email thử tới mailbox/sandbox được phép. Ghi nhận trạng thái SMTP accepted, provider ID nếu có, và kiểm tra bounce/delivery qua kênh thích hợp.

## 22. Connection timeout, read timeout và write timeout

Nếu quên port hoặc dùng sai TLS mode, ứng dụng có thể **treo cho tới timeout** thay vì báo lỗi ngay. Cần giới hạn phù hợp:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

Đơn vị của những SMTP socket timeouts này là **mili giây**.

| Property | Khống chế | Không khống chế |
|---|---|---|
| `connectiontimeout` | TCP connection establishment | Tổng thời gian cả email job |
| `timeout` | Socket read | Mọi đoạn xử lý ngoài network |
| `writetimeout` | Socket write | Tổng retry deadline |

### 22.1. Đừng đặt timeout bằng 0 để “không chờ”

Trong nhiều socket APIs, timeout 0 có thể mang nghĩa **không giới hạn** hơn là “fail ngay”. Phải kiểm tra semantics của thư viện; đặt số dương có chủ đích nếu muốn bounded wait.

### 22.2. Timeout quá ngắn có thể gây gửi trùng

Nếu server đã nhận đủ DATA nhưng client timeout trước khi nhận response, trạng thái có thể là `UNKNOWN`. Retry ngay có thể tạo email thứ hai.

Do đó:
- cấu hình timeout không quá thấp so với mạng/provider;
- phân loại lỗi theo phase khi có dữ liệu;
- không mặc định timeout = chắc chắn chưa gửi;
- có retry budget và reconciliation.

### 22.3. Tổng deadline là thứ khác

Nhiều SMTP commands được gửi nối tiếp, mỗi lần có network I/O riêng. Socket timeout không nhất thiết giới hạn toàn bộ thời gian render MIME + connect + AUTH + send + persist outcome.

Với job quan trọng cần SLA, đặt deadline ở tầng orchestration/worker, không chỉ ở socket properties.

## 23. AUTH failure không luôn là lỗi password

Giả sử port/TLS đã đúng nhưng nhận:

```text
535 5.7.8 Authentication credentials invalid
```

Có thể do:
- sai username/password;
- dùng mật khẩu đăng nhập thông thường khi provider yêu cầu app password;
- SMTP AUTH bị vô hiệu trên mailbox;
- token OAuth2 sai audience/scope/expired;
- provider giới hạn source IP;
- account bị khóa;
- gửi sai endpoint region;
- client chọn AUTH mechanism không được hỗ trợ;
- chính sách yêu cầu STARTTLS trước AUTH.

### 23.1. Đừng bỏ TLS để thử login

Đây là anti-pattern:

```yaml
spring:
  mail:
    properties:
      mail:
        smtp:
          starttls:
            enable: false
```

Nếu provider yêu cầu mã hóa, tắt STARTTLS có thể khiến AUTH bị từ chối hoặc làm lộ credential nếu server chấp nhận plaintext. Cần sửa endpoint/credentials/CA đúng cách.

### 23.2. Không lẫn username và From

`spring.mail.username` là tài khoản dùng cho SMTP AUTH; `helper.setFrom(...)` đặt header From của email. Chúng có thể khác nhau nếu provider cho phép verified aliases, nhưng không thể tự giả định mọi From domain đều được quyền gửi.

Một số provider từ chối relay nếu From hoặc envelope sender không phù hợp account/domain. Điều đó không thể giải quyết chỉ bằng đổi port.

### 23.3. SMTP AUTH không bảo đảm DMARC

Ngay cả khi server accepted message, receiving systems vẫn có thể kiểm tra SPF, DKIM và DMARC. Lỗi deliverability nên được xử lý bằng domain authentication và provider events, không gộp vào lỗi host/port.

## 24. SSL handshake và certificate errors

Nếu hostname đúng và port reachable nhưng TLS không hoạt động, cần xem hai nhóm lỗi:

**Nhóm A — Sai TLS mode:**
- 587 nhưng implicit TLS bật.
- 465 nhưng không bật implicit TLS.
- STARTTLS không được server quảng bá.
- Proxy phát plaintext hoặc chặn STARTTLS.

**Nhóm B — TLS validation:**
- Certificate hết hạn.
- Thiếu intermediate CA.
- JDK truststore không tin CA phù hợp.
- Hostname không có SAN khớp.
- TLS protocol/cipher không tương thích.
- SSL inspection thay chứng chỉ mà ứng dụng không tin cậy.

### 24.1. Hostname cần khớp certificate

Nếu client kết nối `smtp.example.net` nhưng certificate chỉ cấp cho `mail-backend.internal`, hostname verification sẽ fail dù cả hai cùng trỏ một máy.

Không lấy IP từ DNS rồi thay `spring.mail.host` thành IP nếu certificate không có IP SAN phù hợp.

### 24.2. Không bật trust-all

Tránh:

```properties
mail.smtp.ssl.trust=*
```

Cấu hình này có thể bỏ qua phần kiểm tra tin cậy theo cách implementation hỗ trợ, không phải biện pháp sửa certificate. Nó làm suy yếu bảo mật và che giấu lỗi endpoint.

### 24.3. Không tắt hostname verification

Nếu đã bật:

```properties
mail.smtp.ssl.checkserveridentity=true
```

và gặp mismatch, cách xử lý là dùng đúng hostname/certificate hoặc cập nhật phía server/CA, không thay thành false trong production để “được chạy”.

## 25. Spring Boot profile và environment override

Một nguồn lỗi khác là giá trị khai báo đã đúng trong file nhưng bị ghi đè lúc chạy.

Ví dụ:

```yaml
# application.yml
spring:
  mail:
    host: smtp.example.net
    port: 587
    protocol: smtp
```

Nhưng deployment đặt:

```text
SPRING_MAIL_PORT=25
```

và giá trị môi trường được áp dụng với độ ưu tiên cấu hình của Spring Boot. Kết quả sender có thể dùng port 25 dù developer thấy 587 trong repository.

### 25.1. Những nơi cần đối chiếu

- `application.yml`.
- `application-prod.yml` và active profiles.
- Environment variables.
- Command-line arguments.
- Config Server/externalized configuration.
- Kubernetes ConfigMap/Secret.
- Helm chart values.
- Custom `@ConfigurationProperties`.
- Custom bean factory hoặc sender registry.

### 25.2. Không dump toàn bộ environment

Environment chứa secrets. Khi kiểm tra:
- chỉ ghi các trường không nhạy cảm như host, port, protocol, TLS mode;
- không log password/token;
- không in full `Environment` hoặc mọi `spring.mail.properties` tùy tiện;
- hạn chế endpoint vận hành cần quyền truy cập.

### 25.3. Development sandbox có thể dùng port khác

Mailpit/GreenMail/mock SMTP server thường chạy port test do môi trường chọn. Đừng gán port test cho production hoặc để một giá trị mặc định 1025 lọt vào cấu hình thật.

Luôn có cấu hình tách rõ môi trường và test không được gửi tới mailbox Internet không mong muốn.

## 26. Vấn đề mạng: firewall, DNS, proxy và IPv6

Khi port đã cấu hình đúng nhưng không kết nối được, đừng lập tức thay TLS config.

Các nguyên nhân khác có thể là:

1. Provider chưa allowlist source IP.
2. Firewall/security group chặn outbound 587/465.
3. Cloud egress policy giới hạn SMTP traffic.
4. NetworkPolicy chặn pod.
5. DNS trả IPv6 nhưng route IPv6 bị lỗi.
6. Proxy/NAT thay đường đi.
7. Provider đang bảo trì hoặc rate-limit connections.
8. Endpoint private chỉ reachable từ network cụ thể.
9. DNS split-horizon trả IP khác theo môi trường.
10. Load balancer có backend sai TLS mode.

### 26.1. Kiểm tra TCP trước khi thay certificate

Nếu connection refused hoặc không reachable, chưa có TLS handshake để kiểm tra. Sửa route/port/firewall theo bằng chứng trước.

### 26.2. Kiểm tra đúng source environment

Có thể laptop thành công nhưng production Kubernetes thất bại do egress. Không phải vì Spring Boot có hai cách hiểu cùng một YAML, mà vì network path khác.

### 26.3. Khi IPv4 hoạt động nhưng IPv6 không

Đừng cố bật một cờ Java system property ngẫu nhiên ngay. Kiểm tra:
- DNS A/AAAA;
- route IPv6;
- network policy;
- provider IPv6 support;
- Java runtime options.

Nếu cần ưu tiên IPv4, đó là một thay đổi network/runtime có tác động hệ thống; phải đánh giá trước.

## 27. Dùng JavaMailSenderImpl.testConnection đúng mức

Spring cung cấp:

```java
JavaMailSenderImpl sender = ...;

sender.testConnection();
```

Phương thức này có thể kiểm tra kết nối tới mail server theo cấu hình sender và ném exception nếu không kết nối được.

Nó hữu ích để phát hiện:
- sai host/port;
- lỗi TCP;
- lỗi TLS khi connect;
- một số lỗi AUTH trong bước connect.

Nhưng **không chứng minh một email cụ thể sẽ được accepted**, vì chưa nhất thiết chạy MAIL FROM/RCPT TO/DATA với sender/recipient thật. Nó càng không chứng minh email delivered.

### 27.1. Test connection lúc startup

Spring Boot có cấu hình:

```yaml
spring:
  mail:
    test-connection: true
```

Khi được hỗ trợ bởi phiên bản và điều kiện auto-configuration, tùy chọn này giúp kiểm tra kết nối lúc ứng dụng khởi động.

Cân nhắc:
- Nếu SMTP outage, startup có thể fail.
- Với ứng dụng cần API còn chạy dù SMTP không khả dụng, fail startup có thể không phù hợp.
- Với một mail worker chỉ làm nhiệm vụ gửi, fail-fast có thể hữu ích.
- Nếu dùng multiple custom senders, cần kiểm tra từng profile bằng health logic riêng.
- Không nên gửi email thật để test connection.

### 27.2. Không thay thế health với readiness mù

Nếu readiness phụ thuộc SMTP availability, toàn bộ HTTP service có thể bị rút khỏi load balancer khi provider mail sự cố, dù các API khác còn hoạt động. Thiết kế health indicators theo critical dependencies và mục tiêu vận hành, không mặc định mail provider là dependency bắt buộc của mọi request.

## 28. Gửi thử bằng SimpleMailMessage

Sau khi host/port/protocol/TLS đã được xác minh, dùng một email thử có recipient được phép:

```java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailSmokeTestService {

    private final JavaMailSender sender;

    public MailSmokeTestService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendToApprovedMailbox(String approvedRecipient) {
        SimpleMailMessage message =
            new SimpleMailMessage();

        message.setFrom("no-reply@example.com");
        message.setTo(approvedRecipient);
        message.setSubject("SMTP connection smoke test");
        message.setText("This is a controlled test message.");

        sender.send(message);
    }
}
```

Ứng dụng thật phải kiểm tra `approvedRecipient` thuộc danh sách mailbox test được phép; không expose phương thức này như HTTP endpoint cho mọi người dùng nhập recipient tùy ý.

### 28.1. Phân biệt kết quả smoke test

- `testConnection()` thành công: kết nối/auth theo sender được kiểm tra.
- `sender.send(message)` thành công: transport báo submission thành công.
- Provider dashboard báo delivered: có thêm thông tin ở tầng delivery.
- Recipient mở thư: một sự kiện khác, không suy từ kết quả SMTP API.

### 28.2. Đừng gửi smoke test khi chưa xác minh route

Nếu cấu hình nhầm provider hoặc sandbox/production, smoke test có thể gửi ra Internet ngoài ý muốn. Kiểm tra host, port, profile và allowlist recipient trước khi gửi.

## 29. Testing: validation cho profile cấu hình

Có thể mô hình hóa endpoint và TLS mode thành một cấu hình cần xác nhận.

```java
package com.example.mail;

public enum SmtpTlsMode {
    STARTTLS_REQUIRED,
    IMPLICIT_TLS
}

public record MailServerProfile(
    String host,
    int port,
    SmtpTlsMode tlsMode
) {
    public MailServerProfile {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("Host required");
        }
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("Invalid port");
        }
        if (tlsMode == null) {
            throw new IllegalArgumentException("TLS mode required");
        }
    }
}
```

Nếu hệ thống chỉ hỗ trợ 587/465, có thể thêm allowlist và quy tắc pair. Tuy nhiên, **không hardcode rằng 587 luôn STARTTLS và 465 luôn implicit TLS cho mọi provider trong mọi môi trường** nếu hợp đồng cung cấp endpoint khác. Hãy validate theo **provider profile policy**, không chỉ theo con số.

### 29.1. Unit tests bắt lỗi port thiếu

```java
import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;

class MailServerProfileTest {

    @Test
    void rejectsMissingPort() {
        assertThatThrownBy(() ->
            new MailServerProfile(
                "smtp.example.net",
                0,
                SmtpTlsMode.STARTTLS_REQUIRED
            )
        ).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void acceptsExplicitSubmissionPort() {
        MailServerProfile profile =
            new MailServerProfile(
                "smtp.example.net",
                587,
                SmtpTlsMode.STARTTLS_REQUIRED
            );

        assertThat(profile.port()).isEqualTo(587);
    }
}
```

Unit test này không kết nối network; nó chỉ bảo vệ mô hình cấu hình khỏi “quên port”.

### 29.2. Test factory gắn đúng JavaMail properties

Nếu có `JavaMailSenderImpl` factory, hãy assert:
- `getHost()` đúng;
- `getPort()` đúng;
- `getProtocol()` đúng;
- `mail.smtp.starttls.enable/required` đúng ở 587;
- `mail.smtp.ssl.enable` đúng ở 465;
- `mail.smtp.ssl.checkserveridentity` được bật;
- timeouts dương;
- không có conflicting properties.

Không cần SMTP server để test mapping cấu hình này.

## 30. Integration tests: xác minh kết nối thực tế

Unit tests không đủ để chứng minh SMTP handshake.

Một kế hoạch integration test có thể dùng:
- GreenMail hoặc SMTP sandbox hỗ trợ protocol mong muốn;
- SMTP test server có TLS phù hợp;
- fault-injecting SMTP proxy/server cho các lỗi riêng;
- JavaMailSenderImpl cấu hình tới host/port test;
- assertions xác minh số messages accepted.

### 30.1. Happy-path STARTTLS

1. Khởi động SMTP test server có STARTTLS trên port động/cố định được phép.
2. Tạo hoặc inject chứng chỉ test CA đáng tin và SAN đúng hostname test.
3. Cấu hình `protocol=smtp`, port test, `starttls.enable/required=true`.
4. Gọi `testConnection()` hoặc gửi controlled test message.
5. Xác nhận test server nhận message.
6. Đóng resources đúng cách.

### 30.2. Happy-path implicit TLS

1. Khởi động SMTP TLS-from-connect test server.
2. Cấu hình `mail.smtp.ssl.enable=true` trên port test.
3. Xác minh handshake/TLS certificate.
4. Gửi một email thử và inspect MIME.
5. Không dùng `starttls smtp` khi test implicit TLS.

### 30.3. Negative test: sai TLS mode

Ví dụ:
- Client gửi TLS-from-connect tới server chỉ hỗ trợ STARTTLS.
- Client gửi plaintext SMTP tới server đợi implicit TLS.
- Client thiếu explicit port, cấu hình fallback không được chấp nhận theo policy.

Assertions nên xác minh exception/connection failure thuộc **nhóm** phù hợp và không có message được accepted. Không assert một chuỗi error message duy nhất vì JDK/provider versions có thể khác.

### 30.4. Negative test: hostname hoặc CA không hợp lệ

Cần có test certificate mismatch và untrusted CA. Không chứng minh “TLS hoạt động” bằng cách tắt hostname validation hoặc trust-all.

### 30.5. Tests không được phụ thuộc Internet production

Để CI ổn định:
- dùng SMTP sandbox cô lập;
- không dùng credential thật;
- không gửi recipient ngoài allowlist;
- chọn ports không xung đột;
- dừng server và cleanup;
- có bounded waits/timeouts;
- không để test gửi vào provider thật khi CI variables thiếu.

## 31. Kiểm thử môi trường với Testcontainers

Trong dự án dùng Testcontainers, có thể chạy một SMTP sandbox/container để test mail submission. Quan trọng nhất là **cổng ứng dụng kết nối phải là mapped host port thực tế**, không phải port cố định bên trong container nếu test chạy từ host process.

Ví dụ sơ đồ:

```text
JUnit process                  Docker container
     |
     | localhost:mappedPort
     +--------------------------> SMTP sandbox :1025
                                  (container port)
```

Nếu sandbox listen trên 1025 trong container, Testcontainers có thể map tới một port host khác. App phải dùng giá trị mapped port do test container cung cấp.

### 31.1. Đừng dùng 587 mặc định cho mọi integration test

Trong test environment, endpoint có thể dùng 1025, 3025 hoặc port ngẫu nhiên. Việc test với port khác production không có gì sai nếu mục tiêu là kiểm tra flow chung; tuy nhiên phải có test riêng cho **TLS mode và profile mapping**, nếu đó là lỗi cần phòng ngừa.

### 31.2. Property override trong @SpringBootTest

Một test có thể override:

```text
spring.mail.host=127.0.0.1
spring.mail.port=<mapped-smtp-test-port>
spring.mail.protocol=smtp
```

Cần dùng dynamic properties/test configuration tương ứng, không hardcode port nếu runtime tự map ngẫu nhiên.

### 31.3. Không nhầm testConnection với acceptance test

Một SMTP sandbox có thể cho `testConnection` pass, nhưng vẫn từ chối recipient hoặc MAIL FROM khi gửi thử. Test cả hai nếu use case đòi xác minh submission.

## 32. Đọc log không làm lộ credential

Jakarta Mail có các debug options, nhưng bật đầy đủ trong production có thể làm lộ metadata giao thức, địa chỉ email hoặc dữ liệu nhạy cảm.

Các thông tin thường đủ để chẩn đoán lỗi host/port/protocol:
- environment/service name;
- SMTP provider profile key;
- hostname được phép hiển thị;
- port;
- transport protocol;
- TLS mode;
- exception class;
- short safe error category;
- attempt ID/message key;
- duration;
- retry decision.

Ví dụ:

```json
{
  "event": "mail.smtp_connect_failed",
  "messageKey": "msg-2187",
  "attemptId": "attempt-3",
  "profile": "transactional",
  "host": "smtp.example.net",
  "port": 25,
  "protocol": "smtp",
  "tlsMode": "STARTTLS_REQUIRED",
  "errorCategory": "CONNECT_TIMEOUT",
  "durationMs": 5000
}
```

Đoạn log cho thấy rất rõ việc ứng dụng đang thử **port 25** dù profile mong đợi 587. Đây là thông tin có ích hơn ghi toàn bộ raw SMTP transcript.

### 32.1. Tránh các thông tin sau

- SMTP password hoặc app password.
- OAuth2 access/refresh token.
- AUTH challenge/response chứa secret.
- Toàn bộ MIME body.
- Attachment data/Base64.
- Link reset/verification token.
- Recipient addresses không cần thiết.

### 32.2. Bật debug có kiểm soát

Khi sự cố khó tái hiện, có thể bật debug ở môi trường test hoặc trong một cửa sổ chẩn đoán ngắn, với redaction và quyền truy cập log giới hạn. Không mặc định giữ mức debug protocol trong production lâu dài.

### 32.3. Metrics khác logs

Dùng metrics như:
- `mail_smtp_connect_failures_total{profile,category}`;
- `mail_smtp_send_duration_seconds{profile}`;
- `mail_smtp_auth_failures_total{profile}`;
- `mail_smtp_tls_failures_total{profile}`;
- `mail_outbox_retry_wait_count`;
- `mail_outbox_unknown_count`.

Không dùng message ID/recipient làm Prometheus label cardinality cao.

## 33. Retry và outbox: đừng biến lỗi cấu hình thành bão gửi

Nếu sai port, mọi lần retry sẽ tiếp tục kết nối tới endpoint sai, vừa lãng phí tài nguyên vừa tạo backlog.

Ví dụ:

```text
Mail job due
    |
    v
JavaMailSender tries smtp.example.net:25
    |
    v
Connect timeout
    |
    v
Retry immediately
    |
    +--> timeout again
    +--> timeout again
    +--> timeout again
```

Cách điều phối phù hợp:
- Khi phát hiện profile misconfiguration, mở circuit breaker/pause route nếu policy yêu cầu.
- Ghi alert về host/port/protocol/TLS mode sai.
- Đừng retry liên tục với cùng cấu hình.
- Dùng exponential backoff với jitter cho lỗi transient.
- Với lỗi cấu hình chắc chắn, cần sửa profile hoặc manual intervention.
- Giữ outbox jobs bền vững và retry budget.
- Khi config được sửa, resume/dispatch có kiểm soát để tránh bắn backlog hàng loạt.

### 33.1. Sai port trước kết nối thường không tạo SMTP submission

Nếu TCP connect chưa bao giờ thành công, việc chưa gửi DATA là rõ hơn so với timeout sau DATA. Tuy nhiên, **classifier phải dựa trên bằng chứng phase thật**; không suy luận mọi `MailSendException` đều là pre-submission.

### 33.2. UNKNOWN không được retry mù

Nếu lỗi xuất hiện sau khi client đã có thể gửi hết SMTP DATA nhưng chưa thấy final reply, provider có thể đã accepted. Retry mù có nguy cơ gửi trùng. Ghi `UNKNOWN` và đối soát theo provider logs/API/webhook nếu có.

### 33.3. Đừng thay `sendAt` khi sửa port

Một scheduled email đã đến hạn lúc 09:00 nhưng port sai đến 09:30. Sau khi sửa cấu hình:
- giữ `send_at=09:00` để audit;
- ghi actual submission time khi gửi;
- kiểm tra `expires_at`, consent và quota trước resend;
- không sửa mọi `send_at` thành hiện tại để che độ trễ.

## 34. Nhiều SMTP profiles và failover

Một ứng dụng có thể dùng:
- transactional provider trên port 587;
- marketing provider trên port 465;
- relay nội bộ trên port 25.

Nếu chỉ có một bộ `spring.mail.host/port` global và sửa động theo từng tenant, hệ thống có thể gửi sai route.

Thiết kế phù hợp:
- sender bean hoặc immutable profile cho từng provider;
- routing theo category/tenant được xác thực;
- validate host/port/TLS/auth từng profile;
- không mutate shared singleton giữa threads;
- metrics theo provider;
- quota/rate limits riêng.

### 34.1. Failover phải an toàn

Nếu provider A không kết nối được trước khi SMTP submission, có thể cân nhắc provider B khi policy cho phép. Nhưng B phải được chuẩn bị:
- domain From verified;
- SPF/DKIM/DMARC alignment;
- suppression/consent;
- credential/TLS;
- quota;
- data residency/tenant permission.

Không failover sang B chỉ vì A timeout **không rõ outcome**. Có thể A đã accepted email và B sẽ gửi thêm một bản.

### 34.2. Cấu hình cả host và port theo route

Hãy tránh:

```java
sender.setHost(provider.host());
sender.send(message);
```

mà quên cập nhật port/TLS. Khi chuyển provider, cần chuyển **toàn bộ endpoint profile**, không chỉ một thuộc tính.

## 35. Lỗi thường gặp khi nhận thư: IMAP và POP3 port/protocol

Dù bài này tập trung SMTP outbound, một hệ thống Spring Mail cũng có thể nhận email qua Jakarta Mail `Store`.

Cổng phổ biến:

| Giao thức nhận | Port phổ biến | TLS |
|---|---|---|
| IMAP | 143 | STARTTLS nếu server hỗ trợ |
| IMAPS | 993 | Implicit TLS |
| POP3 | 110 | STLS/STARTTLS nếu server hỗ trợ |
| POP3S | 995 | Implicit TLS |

### 35.1. Không dùng SMTP host để đọc INBOX

Một provider có thể công bố:
- `smtp.example.net` cho gửi;
- `imap.example.net` cho đọc.

Không dùng `spring.mail.host` như mặc định cho `Store.getFolder("INBOX")`. Spring Boot `spring.mail.*` auto-configuration chủ yếu dành cho outbound sender.

### 35.2. Session, Store và Transport khác nhau

`jakarta.mail.Session` là ngữ cảnh cấu hình. `Transport` dùng cho gửi qua SMTP, còn `Store` dùng cho đọc mailbox qua IMAP/POP3.

Nếu chọn `Session.getStore("imaps")`, phải dùng properties `mail.imaps.*`; còn `JavaMailSenderImpl` dùng protocol/transport `smtp` hoặc `smtps` và properties tương ứng.

### 35.3. Cùng vấn đề hostname đúng nhưng port sai

Nếu IMAP server đợi TLS ngay trên 993 mà client dùng `imap` plaintext, nó cũng có thể timeout hoặc handshake fail. Nguyên tắc chung vẫn là chọn đúng **protocol + port + TLS mode**.

## 36. Incident runbook: khi gửi mail đột ngột thất bại

### Bước 1 — Xác nhận mức ảnh hưởng

- Tất cả email hay chỉ một tenant/provider?
- Tất cả môi trường hay riêng production?
- Lỗi bắt đầu sau deployment/config rotation?
- SMTP requests đang timeout, AUTH fail hay bị reject?
- Backlog/retry tăng đến mức nào?

### Bước 2 — Tạm bảo vệ hệ thống

- Giới hạn concurrency/rate.
- Nếu phát hiện misconfiguration chắc chắn, pause route.
- Giữ job trong durable outbox, không drop.
- Không tự chuyển `UNKNOWN` về pending.
- Không dùng trust-all/plaintext fallback để “khôi phục ngay”.

### Bước 3 — Xác nhận runtime profile

Ghi lại non-secret:
- host;
- port;
- protocol;
- TLS mode;
- authentication mechanism;
- profile/environment;
- active application version.

So sánh với tài liệu provider, không chỉ với YAML trong git.

### Bước 4 — Kiểm tra DNS/TCP

Từ đúng môi trường deployment:
- resolve hostname;
- thử port được công bố;
- đối chiếu firewall/network;
- kiểm tra source IP allowlist nếu provider có.

### Bước 5 — Kiểm tra TLS

Dùng OpenSSL đúng mode, xác minh hostname và certificate chain, rồi kiểm tra JDK truststore nếu JVM vẫn fail.

### Bước 6 — Kiểm tra AUTH và sender policy

Sau khi kết nối/TLS đúng:
- xác nhận credential/scopes;
- xem provider logs;
- kiểm tra From/envelope sender;
- không in secret.

### Bước 7 — Controlled smoke test

Gửi một email đến mailbox test được phép, theo dõi kết quả submission.

### Bước 8 — Resume backlog có giới hạn

- Xử lý jobs hết hạn trước.
- Reconcile `UNKNOWN`.
- Giảm retry storm.
- Áp dụng quota/concurrency.
- Theo dõi acceptance, bounces và delivery nếu có.

### Bước 9 — Ghi lại nguyên nhân

Ví dụ:
> Tại deployment mới, biến `SPRING_MAIL_PORT` không được cấp, sender dùng port mặc định của `smtp`. Hạ tầng chặn outbound port 25. Khôi phục cấu hình port 587/STARTTLS và thêm startup validation + integration test.

Runbook nên giúp sửa **nguyên nhân gốc**, không chỉ thay timeout hoặc retry count.

## 37. Checklist cấu hình trước khi deploy

### 37.1. Endpoint

- [ ] Host SMTP submission đúng theo tài liệu provider.
- [ ] `spring.mail.port` được khai báo tường minh.
- [ ] `spring.mail.protocol` đúng transport.
- [ ] Không nhầm MX/IMAP/API endpoint với SMTP submission.
- [ ] Không nhầm `server.port` với `spring.mail.port`.
- [ ] Không có `mail.smtp.port` mâu thuẫn.
- [ ] Đã xác minh env/profile/ConfigMap overrides.

### 37.2. TLS và AUTH

- [ ] Port 587 dùng STARTTLS nếu provider công bố như vậy.
- [ ] Port 465 dùng implicit TLS nếu provider công bố như vậy.
- [ ] `starttls.required=true` khi endpoint yêu cầu STARTTLS.
- [ ] Hostname verification và CA chain hợp lệ.
- [ ] Không dùng `ssl.trust=*` trong production.
- [ ] SMTP AUTH mechanism/credential đúng.
- [ ] Credential lấy từ secret manager/env được bảo vệ.
- [ ] From domain/identity được verified.

### 37.3. Runtime

- [ ] Connect/read/write timeouts hợp lý.
- [ ] Workload có outbound access đến port.
- [ ] Provider quota/rate limits được biết.
- [ ] Startup/testConnection policy được cân nhắc.
- [ ] Có metrics/log non-secret cho host, port, protocol, TLS.
- [ ] Có retry/backoff/circuit breaker hoặc route pause thích hợp.
- [ ] Outbox không mất jobs khi provider outage.
- [ ] Không resend `UNKNOWN` mù.

### 37.4. Tests

- [ ] Unit test endpoint profile validation.
- [ ] Unit test mapping config vào `JavaMailSenderImpl`.
- [ ] Test 587/STARTTLS với server phù hợp.
- [ ] Test 465/implicit TLS với server phù hợp.
- [ ] Test wrong-port/wrong-mode failure.
- [ ] Test certificate mismatch bị từ chối.
- [ ] Test AUTH failure và sender policy.
- [ ] Test production-like network path nếu môi trường cho phép.
- [ ] Test không gửi thư thật ngoài ý muốn.

## 38. Bài tập thực hành

### Bài 1 — Thiếu port

Cho cấu hình:

```yaml
spring:
  mail:
    host: smtp.example.net
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
```

Provider yêu cầu 587/STARTTLS. Hãy bổ sung những properties còn thiếu và giải thích tại sao thiếu port có thể khiến client dùng cổng 25.

### Bài 2 — Nhầm server.port

Một ứng dụng đặt `server.port=587` nhưng email vẫn kết nối port 25. Hãy sửa và giải thích sự khác biệt giữa HTTP listen port và SMTP destination port.

### Bài 3 — STARTTLS so với implicit TLS

Vẽ handshake cho 587 và 465. Chỉ ra lệnh STARTTLS xuất hiện ở đâu và vì sao 465 không cần nâng cấp từ phiên SMTP plaintext.

### Bài 4 — Phân tích error “wrong version number”

Một client bật `mail.smtp.ssl.enable=true` trên port 587. Phân tích giả thuyết protocol mismatch và viết cấu hình đúng.

### Bài 5 — Port 465 timeout

Một client chỉ đổi `spring.mail.port` từ 587 sang 465 nhưng giữ STARTTLS config. Giải thích hiện tượng chờ greeting và đưa ra cấu hình implicit TLS đúng.

### Bài 6 — smtps property prefix

Một ứng dụng dùng `spring.mail.protocol=smtps` nhưng timeout đặt ở `mail.smtp.timeout`. Hãy xác định rủi ro prefix không được áp dụng và đề xuất cách cấu hình nhất quán.

### Bài 7 — YAML indentation

Cho một `application.yml` đặt `mail.smtp.starttls.enable` ngoài `spring.mail.properties`. Sửa nesting để sender nhận đúng property.

### Bài 8 — Runtime override

Repository dùng port 587 nhưng production log cho thấy port 25. Liệt kê các nguồn override cần kiểm tra và cách log non-secret runtime profile.

### Bài 9 — DNS vs TCP

`Resolve-DnsName` thành công nhưng `Test-NetConnection -Port 587` thất bại. Nêu những điều đã xác minh được và những nguyên nhân vẫn cần điều tra.

### Bài 10 — OpenSSL STARTTLS

Viết lệnh `openssl s_client -starttls smtp` cho 587, với SNI và hostname verification. Giải thích vì sao lệnh đó khác implicit TLS trên 465.

### Bài 11 — Certificate mismatch

SMTP certificate chỉ khớp `smtp-a.example.net` nhưng ứng dụng dùng `mail.example.net`. Thiết kế hướng sửa an toàn mà không tắt hostname verification.

### Bài 12 — TestConnection

Gọi `JavaMailSenderImpl.testConnection()`. Phân biệt điều test đó có thể chứng minh với các điều nó không thể chứng minh về recipient và delivery.

### Bài 13 — Unit test profile factory

Viết unit test xác minh factory cấu hình `smtp`, port 587, STARTTLS required hoặc port 465, implicit TLS. Test cũng phải reject port 0.

### Bài 14 — SMTP sandbox integration

Tạo hai test endpoints: một STARTTLS, một implicit TLS. Gửi test mail và xác minh server nhận thư đúng mode.

### Bài 15 — Mạng cloud chặn port 25

Local gửi được qua port 25 nhưng cloud timeout. Thiết kế quy trình kiểm tra egress, chọn submission endpoint được provider công bố và không tự thay sang port ngẫu nhiên.

### Bài 16 — AUTH sau TLS

Port và TLS đã đúng, nhưng server trả 535. Nêu các khả năng liên quan credential, OAuth2/app password, account policy và khác biệt giữa SMTP AUTH với From verification.

### Bài 17 — Timeout trong queue worker

Một worker gửi mail có connect timeout 60 giây và 100 jobs cùng đến hạn. Phân tích nguy cơ chiếm threads và đề xuất bounded concurrency/backoff.

### Bài 18 — Không gửi trùng sau UNKNOWN

Giả lập SMTP DATA đã gửi xong nhưng client mất final reply. Thiết kế outbox state `UNKNOWN` và reconciliation thay vì retry ngay.

### Bài 19 — Provider rotation

Một ứng dụng đổi từ provider A (587/STARTTLS) sang B (465/implicit TLS). Viết checklist những phần của profile phải đổi cùng lúc, bao gồm verified From và quota.

### Bài 20 — Chẩn đoán sự cố tổng hợp

Log:

```json
{
  "event": "mail.smtp_connect_failed",
  "host": "smtp.example.net",
  "port": 25,
  "protocol": "smtp",
  "durationMs": 5000,
  "errorCategory": "CONNECT_TIMEOUT"
}
```

Provider công bố port 587/STARTTLS. Hãy lập kế hoạch sửa, test trên sandbox, rollout và tránh retry storm cho backlog đã tồn tại.

## 39. Tổng kết

**Cấu hình đúng host nhưng quên port hoặc protocol** là lỗi phổ biến của Spring Framework Mail vì hostname chỉ giải quyết **địa chỉ máy chủ**, còn SMTP submission cần **đúng cổng, transport provider và TLS mode**.

Hãy nhớ những nguyên tắc:

1. **Khai báo port tường minh** trong `spring.mail.port`, không trông chờ Jakarta Mail tự suy ra 587 từ username/password.
2. **Port 587** thường dùng `smtp + STARTTLS`; bật cả `starttls.enable` và `starttls.required` khi nhà cung cấp yêu cầu mã hóa.
3. **Port 465** thường dùng implicit TLS; với `protocol=smtp`, bật `mail.smtp.ssl.enable=true` trước khi kết nối.
4. **Port 25** thường phục vụ relay/server-to-server; không mặc định dùng cho SMTP submission và có thể bị network/cloud chặn.
5. **`spring.mail.protocol` khác TLS mode**. `smtp` có thể hoạt động với cả 587/STARTTLS và 465/implicit TLS; nếu dùng `smtps` phải kiểm tra property prefix `mail.smtps.*`.
6. **`server.port` không phải `spring.mail.port`**. Đừng cấu hình cổng HTTP thay cho cổng SMTP.
7. **YAML nesting và runtime overrides** quan trọng; phải xem bean sender thực tế, không chỉ file nguồn.
8. Chẩn đoán theo tầng: **DNS → TCP → SMTP greeting/TLS → certificate → AUTH → MAIL FROM/RCPT TO/DATA → delivery**.
9. **Không sửa lỗi bằng cách tắt TLS/hostname verification** hoặc bật trust-all; phải sửa endpoint/certificate/credential theo policy.
10. **Giới hạn timeout và retry**, giữ outbox bền vững và không resend những attempts có outcome `UNKNOWN` một cách mù quáng.
11. **Kiểm thử cả mapping cấu hình và SMTP handshake thực** bằng unit tests, sandbox và network checks phù hợp môi trường.
12. **SMTP submission accepted không đồng nghĩa delivered**: delivery phụ thuộc provider và hệ thống nhận.

Khi cấu hình **host + port + protocol + TLS mode** như một profile thống nhất, bạn sẽ phát hiện lỗi sớm, chẩn đoán nhanh hơn và vận hành Spring Framework Mail đáng tin cậy mà không phải đánh đổi bảo mật hoặc tạo rủi ro gửi email trùng.
