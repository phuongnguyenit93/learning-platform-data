# Mail receiver trong Spring Integration

Khi nhắc tới email trong Spring Framework, lập trình viên thường nghĩ ngay đến `JavaMailSender` và `MimeMessageHelper` để **gửi thư ra ngoài**. Tuy nhiên, nhiều hệ thống còn có nhu cầu **nhận thư từ một hộp thư**: đọc phản hồi khách hàng, tiếp nhận báo cáo từ đối tác, xử lý email chứa tệp đính kèm hoặc nhập yêu cầu hỗ trợ từ một địa chỉ chung.

**Spring Integration Mail** cung cấp các thành phần tích hợp với JavaMail/Jakarta Mail để biến email nhận qua **IMAP hoặc POP3** thành message trong một **Spring Integration message flow**. Thay vì tự viết vòng lặp kết nối mailbox, tìm thư chưa đọc và chuyển nội dung cho nghiệp vụ, ứng dụng có thể dùng mail receiver, inbound endpoint, channel và message handler.

Ví dụ kiến trúc:

~~~text
Hộp thư support@example.com
          |
          | IMAP / IMAPS
          v
Spring Integration Mail receiver
          |
          | Spring Message<?> chứa dữ liệu email
          v
Message channel / integration flow
          |
          +-- xác định loại thư
          +-- đọc subject, From, MIME, attachment
          +-- kiểm tra bảo mật
          +-- lưu inbound job bền vững
          |
          v
Ứng dụng tạo ticket hoặc cập nhật nghiệp vụ
~~~

Đây là **nhận thư từ một mailbox đã tồn tại**, không phải viết một SMTP server để trực tiếp nhận email từ Internet. Spring Integration Mail thường là **email client** kết nối tới dịch vụ hộp thư của nhà cung cấp.

Bài học trình bày vai trò của mail receiver, cách cấu hình polling và IMAP IDLE, ví dụ Spring Java DSL, xử lý MIME an toàn, trạng thái thư, idempotency, đồng thời, vận hành và kiểm thử tích hợp.

## 1. Phân biệt gửi thư và nhận thư trong Spring

| Khía cạnh | Gửi email | Nhận email |
| --- | --- | --- |
| Thành phần quen thuộc | `JavaMailSender`, `MimeMessageHelper` | Spring Integration Mail receiver / inbound adapter |
| Giao thức thường dùng | SMTP submission | IMAP, IMAPS, POP3, POP3S |
| Hành động chính | Nộp email cho mail server | Đọc email đã có trong mailbox |
| Trạng thái cần quản lý | Outbox, retry, submitted, bounced | Thư mới/đã đọc, UID, đã xử lý, duplicate |
| Đầu vào nghiệp vụ | Event nội bộ, job gửi thư | Dữ liệu bên ngoài do người gửi cung cấp |
| Rủi ro đặc thù | Quota, SMTP reject, gửi trùng | MIME độc hại, xử lý lặp, bỏ sót thư |

Một email có thể được **gửi bằng SMTP** tới `support@example.com`. Sau đó ứng dụng **đọc qua IMAP**, nhưng hai giao thức phục vụ hai giai đoạn khác nhau:

~~~text
External sender --SMTP--> Mail server / mailbox
                                   |
                                   | IMAP/POP3
                                   v
                            Spring Integration
                                   |
                                   v
                            Business processing
~~~

### 1.1. Khi nào dùng mail receiver?

Các use case phù hợp:

- Đọc email đến `support@...` để tạo ticket.
- Nhận hóa đơn/báo cáo từ đối tác và trích xuất attachment.
- Đọc mailbox dùng cho quy trình phê duyệt hoặc nhập dữ liệu.
- Tiếp nhận email trả lời một thông báo đã gửi, ghép theo correlation ID.
- Tạo workflow khi nhận email từ một nhóm địa chỉ được kiểm soát.

### 1.2. Khi nào nên dùng webhook hoặc email inbound API?

Nếu email service provider cung cấp **inbound parse webhook**, ứng dụng có thể nhận HTTP event thay vì tự polling IMAP. Webhook có thể giảm việc quản lý mailbox connection, nhưng cần xử lý chữ ký webhook, retry, idempotency, định dạng payload và giới hạn provider.

Nếu chỉ cần biết email gửi ra có bị bounce hay complaint, **provider event webhook** thường thích hợp hơn việc suy diễn từ một mailbox trả lời. Mail receiver hữu ích khi yêu cầu nghiệp vụ thực sự là **đọc email nội dung đến một hộp thư**.

## 2. Tổng quan IMAP, POP3 và IMAP IDLE

### 2.1. IMAP

IMAP phù hợp khi ứng dụng cần:

- đọc mailbox mà vẫn giữ email trên server;
- sử dụng folder như `INBOX`;
- tìm message theo cờ `SEEN`, `DELETED` hoặc search criteria;
- quản lý UID của message trong folder;
- phối hợp với các client khác hoặc một quy trình lưu trữ email.

Ví dụ:

~~~text
imaps://mail-reader:<credential>@mail.example.test:993/INBOX
~~~

Chuỗi này chỉ minh họa cấu trúc URL; **không dùng credential thật trong tài liệu, log hoặc repository**. Tên protocol, host, port, folder và cách escape ký tự đặc biệt phải phù hợp với phiên bản thư viện/provider.

IMAPS thường dùng TLS ngay từ đầu trên cổng **993**. IMAP với STARTTLS thường dùng cổng **143**, nếu provider cho phép. Chỉ chọn mode được nhà cung cấp công bố.

### 2.2. POP3

POP3 thường đơn giản hơn, tập trung vào tải message trong mailbox, với khả năng quản lý folder/flags hạn chế hơn IMAP.

~~~text
pop3s://mail-reader:<credential>@mail.example.test:995/INBOX
~~~

POP3S thường dùng implicit TLS ở cổng 995. Với hệ thống cần tìm kiếm folder, đọc/đánh dấu thư theo trạng thái và xử lý nhiều client, **IMAP thường phù hợp hơn**.

### 2.3. IMAP IDLE

IMAP IDLE cho phép client duy trì một kết nối IMAP để server thông báo khi mailbox thay đổi, từ đó xử lý thư mới với độ trễ thấp hơn polling định kỳ.

~~~text
Polling:
  cứ mỗi 15 giây -> kết nối/tìm thư -> xử lý

IMAP IDLE:
  giữ một phiên IMAP IDLE
  -> server báo thay đổi
  -> receiver tìm/nhận message
  -> chuyển tới integration channel
~~~

**IDLE không phải hàng đợi có bảo đảm delivery tuyệt đối.** Server có thể ngắt kết nối, mạng gián đoạn hoặc notification bị bỏ lỡ. Ứng dụng production vẫn cần chiến lược reconnect và đồng bộ lại mailbox, không chỉ phụ thuộc vào một kết nối IDLE đang sống.

### 2.4. So sánh nhanh

| Tiêu chí | IMAP polling | IMAP IDLE | POP3 polling |
| --- | --- | --- | --- |
| Cách phát hiện | Theo lịch | Server báo thay đổi qua kết nối IDLE | Theo lịch |
| Folder | Có | Có | Hạn chế |
| Flags/read state | Có | Có | Hạn chế |
| UID per folder | IMAP UID/UIDVALIDITY | IMAP UID/UIDVALIDITY | UIDL nếu server hỗ trợ |
| Độ trễ | Phụ thuộc poll interval | Thường thấp hơn khi IDLE ổn định | Phụ thuộc poll interval |
| Kết nối lâu dài | Không nhất thiết | Có | Không nhất thiết |
| Phù hợp | Batch, đối soát, tải vừa | Phản ứng gần thời gian thực | Mailbox đơn giản |

## 3. Các khối xây dựng của Spring Integration Mail

Spring Integration phân tách phần **lấy message** với phần **xử lý message**:

| Thành phần | Vai trò |
| --- | --- |
| `ImapMailReceiver` | Truy cập email từ IMAP mailbox |
| `Pop3MailReceiver` | Truy cập email từ POP3 mailbox |
| `MailReceivingMessageSource` | Đưa message nhận được thành nguồn cho polling endpoint |
| `SourcePollingChannelAdapter` | Endpoint định kỳ gọi message source |
| `ImapIdleChannelAdapter` | Inbound endpoint dùng IMAP IDLE thay vì polling thường |
| `MessageChannel` | Truyền Spring Integration message giữa các bước |
| `IntegrationFlow` | Mô tả pipeline bằng Java DSL |
| `MessageHandler` / `@ServiceActivator` | Xử lý message trong flow |
| `jakarta.mail.Message` / `MimeMessage` | Đối tượng email và MIME thực tế |

**Cần phân biệt hai lớp `Message`:**

- `org.springframework.messaging.Message<?>` là message của Spring Messaging, gồm payload và headers của integration flow.
- `jakarta.mail.Message` là message của mail protocol; `MimeMessage` là implementation thông dụng cho nội dung MIME.

Trong một inbound flow, **payload** của Spring message có thể là đối tượng Jakarta Mail, hoặc nội dung đã được receiver/transformer xử lý, tùy cấu hình. Không nên mặc định mọi handler luôn nhận `String`.

### 3.1. Mail receiver không phải mail sender

`JavaMailSender` không có API để poll inbox. Thêm dependency `spring-boot-starter-mail` để gửi thư **không tự động tạo một inbox receiver**. Phần inbound cần các thành phần **Spring Integration Mail** và flow cấu hình rõ ràng.

### 3.2. Pollable message source và message-driven adapter

Với polling:

~~~text
Poller
  -> MailReceivingMessageSource.receive()
      -> ImapMailReceiver
          -> Spring Message payload
              -> channel/handler
~~~

Với IDLE:

~~~text
ImapIdleChannelAdapter
  -> ImapMailReceiver / IDLE connection
      -> channel
          -> handler
~~~

Hai hướng khác nhau ở **cách kích hoạt nhận**, nhưng phần xử lý nghiệp vụ sau channel có thể tái sử dụng.

## 4. Dependency và phiên bản

Với Spring Boot/Spring Integration theo hệ Jakarta Mail:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

Nếu dùng Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mail</artifactId>
</dependency>
~~~

Thông thường dùng **Spring Boot dependency management** để thống nhất phiên bản Spring Integration, Spring Framework và Jakarta Mail/Angus Mail. Với dự án không dùng Boot, cần khai báo dependency management và mail implementation tương thích.

**Phân biệt namespace:**

- Spring Framework 6 / Spring Boot 3 và các phiên bản Spring Integration tương ứng sử dụng `jakarta.mail.*`.
- Dự án Spring/JavaMail thế hệ trước có thể dùng `javax.mail.*`.

Không trộn `javax.mail` và `jakarta.mail` tùy tiện trong cùng ứng dụng; điều đó có thể gây lỗi class/method và dependency không tương thích.

**Lưu ý phiên bản:** Tên builder hoặc method trong Java DSL có thể thay đổi theo thế hệ Spring Integration. Khi áp dụng code bên dưới, dùng API của đúng phiên bản thư viện và kiểm tra tài liệu tham chiếu tương ứng.

## 5. Ví dụ IMAPS polling trong Spring Boot

Ví dụ sau chọn **IMAPS polling**, một mô hình dễ hiểu để xây dựng receiver đầu tiên.

### 5.1. Cấu hình ứng dụng

~~~yaml
app:
  mail:
    inbound:
      imap-url: ${INBOUND_IMAP_URL}
      poll-delay-ms: 15000
~~~

Biến môi trường `INBOUND_IMAP_URL` chứa endpoint mailbox thử nghiệm phù hợp với Spring Integration Mail URL format. Nếu URL chứa user/password, nó là **secret** và phải được quản lý như secret; không in trong log hoặc commit vào repository. Với mật khẩu có ký tự `@`, `/`, `:`, `%`, cần encode đúng định dạng URL mà thư viện yêu cầu; không nối chuỗi URL một cách ngây thơ.

Ví dụ minh họa đã ẩn credential:

~~~text
imaps://reader:<redacted>@mail.example.test:993/INBOX
~~~

Đây không phải địa chỉ kết nối thật.

### 5.2. Tạo receiver và flow

~~~java
package com.example.mail.inbound;

import java.time.Duration;
import java.util.Properties;

import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
@EnableIntegration
public class ImapInboundConfiguration {

    @Bean
    ImapMailReceiver imapMailReceiver(
            @Value("${app.mail.inbound.imap-url}") String imapUrl) {

        ImapMailReceiver receiver = new ImapMailReceiver(imapUrl);

        Properties properties = new Properties();
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "15000");
        properties.put("mail.imaps.ssl.checkserveridentity", "true");

        receiver.setJavaMailProperties(properties);

        // Cấu hình minh họa: thư đọc xong sẽ được đánh dấu SEEN.
        // Production phải xác định trước chiến lược durable ingest.
        receiver.setShouldMarkMessagesAsRead(true);
        receiver.setShouldDeleteMessages(false);

        return receiver;
    }

    @Bean
    IntegrationFlow imapInboundFlow(
            ImapMailReceiver receiver,
            InboundMailInspector inspector,
            @Value("${app.mail.inbound.poll-delay-ms:15000}")
                    long pollDelayMs) {

        MailReceivingMessageSource source =
                new MailReceivingMessageSource(receiver);

        return IntegrationFlow
                .from(source, endpoint -> endpoint.poller(
                        Pollers.fixedDelay(
                                Duration.ofMillis(pollDelayMs))
                                .maxMessagesPerPoll(10)))
                .handle((payload, headers) -> {
                    inspector.inspect((MimeMessage) payload);
                    return null; // Terminal handler: không tạo output mới.
                })
                .get();
    }
}
~~~

### 5.3. Handler chỉ đọc metadata an toàn

~~~java
package com.example.mail.inbound;

import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.stereotype.Component;

@Component
public class InboundMailInspector {

    public void inspect(MimeMessage mimeMessage) {
        try {
            String subject = mimeMessage.getSubject();
            Address[] from = mimeMessage.getFrom();
            String messageId = mimeMessage.getMessageID();

            // Thực tế: tạo inbound job và lưu metadata tối thiểu.
            // Ví dụ chỉ minh họa thao tác đọc; tránh log body/PII.
            String safeType = subject == null
                    ? "no-subject" : "has-subject";

            System.out.println(
                    "Received mail: type=" + safeType
                    + ", hasFrom=" + (from != null && from.length > 0)
                    + ", hasMessageId=" + (messageId != null));

        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot inspect inbound mail", ex);
        }
    }
}
~~~

**Đây là ví dụ khởi đầu, không phải pipeline production có bảo đảm exactly-once.** Ví dụ đánh dấu thư đã đọc để tránh polling lặp liên tục; nếu handler lỗi sau khi thư đã bị đánh dấu `SEEN`, thư có thể không còn xuất hiện trong lần tìm unread tiếp theo. Trong production cần chiến lược **lưu bền vững trước khi thừa nhận đã tiếp nhận** và cơ chế quét/khôi phục phù hợp.

### 5.4. Giải thích từng phần

1. `ImapMailReceiver` quản lý truy cập mailbox.
2. `setJavaMailProperties` đặt timeout và kiểm tra danh tính server TLS.
3. `MailReceivingMessageSource` là nguồn để poller gọi lấy message.
4. `Pollers.fixedDelay(...)` quyết định khoảng cách giữa các lần polling.
5. `maxMessagesPerPoll(10)` giới hạn số message được polled trong một nhịp theo semantics endpoint; không thay thế giới hạn tổng mailbox hay attachment size.
6. Handler nhận payload là `MimeMessage` trong cấu hình minh họa.
7. `return null` biểu diễn bước xử lý kết thúc, không phát output message tiếp theo.

Không dùng một poll interval cực ngắn khi không cần thiết: mailbox provider có giới hạn connection/rate, và quá nhiều lần poll có thể làm tăng tải.

### 5.5. Điểm cần xác minh với phiên bản và provider

- Mail URL có thể chứa credential; Spring Integration có các lựa chọn authenticator/connection configuration tùy API/version. Khi dùng credential xoay vòng hoặc OAuth, ưu tiên cách cấu hình không làm lộ URL.
- MIME payload có thể được đọc lười từ folder. Nếu handler cần duyệt nội dung/attachment, phải đảm bảo **folder vẫn mở khi đọc**, hoặc vật hóa nội dung vào DTO/byte storage trong giai đoạn nhận.
- Các cài đặt `shouldMarkMessagesAsRead`, `shouldDeleteMessages` quyết định side effects của receiver; không coi chúng là cơ chế transaction commit nghiệp vụ.
- Khi có nhiều receiver bean, dùng `@Qualifier` hoặc đặt tên bean để tránh inject nhầm.

## 6. Polling interval, batch size và backpressure

Polling cần cân bằng giữa độ trễ và tải:

~~~text
Polling mỗi 1 giây:
  + phản ứng nhanh
  - nhiều request, socket và CPU

Polling mỗi 60 giây:
  + giảm tần suất kết nối
  - mail có thể đợi lâu
~~~

### 6.1. Các tham số vận hành

| Tham số | Tác động |
| --- | --- |
| `fixedDelay` / `fixedRate` | Khi nào poll tiếp |
| `maxMessagesPerPoll` | Số lượt nhận trong mỗi poll cycle |
| Worker concurrency | Số message xử lý song song |
| IMAP connection/read timeout | Giới hạn thời gian chờ network |
| Search criteria | Số message cần duyệt |
| Attachment limits | Giới hạn RAM, disk, I/O |
| Queue capacity | Giới hạn lượng công việc đang chờ |
| Retry policy | Cách thử lại khi lỗi tạm thời |

**Không nhầm `maxMessagesPerPoll` với giới hạn dung lượng.** Một message có attachment hàng trăm MB vẫn có thể vượt khả năng xử lý dù chỉ lấy một message mỗi lần.

### 6.2. Nên tách nhận thư khỏi xử lý tốn thời gian

Không nên để một IMAP poller đồng bộ chờ OCR, gọi API chậm hoặc xử lý PDF lớn trước khi tiếp nhận mail tiếp theo.

Kiến trúc thường tốt hơn:

~~~text
IMAP receiver
  |
  v
Validate + extract metadata/content within limits
  |
  v
Durable inbox store / queue
  |
  +-- công bố inbound job đã tiếp nhận
  |
  v
Background business workers
  |
  v
Ticket / invoice / workflow
~~~

Receiver tập trung vào **ingest an toàn và bền vững**, còn business workers xử lý bất đồng bộ. Nếu queue/storage quá tải, áp dụng backpressure hoặc giảm polling để không làm cạn memory/disk.

## 7. IMAP IDLE với inbound channel adapter

Khi mailbox server hỗ trợ IDLE và cần xử lý gần thời gian thực, Spring Integration cung cấp `ImapIdleChannelAdapter`.

Mô hình:

~~~text
IMAP server
   |
   | IDLE notification
   v
ImapIdleChannelAdapter
   |
   v
MessageChannel
   |
   v
@ServiceActivator / message handler
~~~

### 7.1. Cấu hình bằng Java

Một cách tổ chức theo component API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.ImapIdleChannelAdapter;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ImapIdleConfiguration {

    @Bean
    MessageChannel inboundMailChannel() {
        return new DirectChannel();
    }

    @Bean
    ImapIdleChannelAdapter imapIdleAdapter(
            ImapMailReceiver receiver,
            MessageChannel inboundMailChannel) {
        ImapIdleChannelAdapter adapter =
                new ImapIdleChannelAdapter(receiver);
        adapter.setOutputChannel(inboundMailChannel);
        return adapter;
    }
}
~~~

Handler:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import jakarta.mail.internet.MimeMessage;

@Component
public class IdleInboundHandler {

    private final InboundMailInspector inspector;

    public IdleInboundHandler(InboundMailInspector inspector) {
        this.inspector = inspector;
    }

    @ServiceActivator(inputChannel = "inboundMailChannel")
    public void handle(Message<?> springMessage) {
        inspector.inspect((MimeMessage) springMessage.getPayload());
    }
}
~~~

Đây là **một lựa chọn cấu hình thay cho polling flow**, không phải cấu hình để chạy song song với poller trên cùng `ImapMailReceiver`. Nếu ứng dụng chọn IDLE, hãy chỉ kích hoạt endpoint IDLE phù hợp, tránh hai consumer cạnh tranh cùng trạng thái mailbox.

### 7.2. IDLE không thay thế rescan

Server có thể:

- ngắt IDLE khi hết thời gian cho phép;
- đóng connection khi bảo trì;
- gửi notification nhưng client rơi mạng;
- áp quota hoặc giới hạn số connections;
- thay đổi trạng thái folder ngoài kỳ vọng.

Ứng dụng cần khả năng reconnect và **periodic reconciliation**: quét lại từ checkpoint/UID hoặc khoảng trạng thái phù hợp để tìm mail có thể bị bỏ lỡ, đồng thời dựa vào idempotency để tránh tạo ticket trùng.

Không đặt kỳ vọng IDLE bảo đảm “đúng một lần, không mất mail”.

## 8. Cờ IMAP: SEEN, DELETED và việc xác nhận đã xử lý

IMAP quản lý flags trên từng message. Một số cờ thường gặp:

| Flag | Ý nghĩa phổ biến | Lưu ý |
| --- | --- | --- |
| `\Seen` | Thư đã được đọc/đánh dấu đã đọc | Không đồng nghĩa nghiệp vụ đã xử lý |
| `\Deleted` | Thư được đánh dấu để xóa | Có thể cần thao tác expunge theo cơ chế server |
| `\Flagged` | Thư được gắn cờ | Ý nghĩa phụ thuộc quy trình |
| User-defined flag | Server cho phép cờ tùy biến nếu hỗ trợ | Không phải mọi server đều hỗ trợ |

Các lựa chọn receiver như `shouldMarkMessagesAsRead` và `shouldDeleteMessages` tác động lên thư trong mailbox. **Không phải là transaction ack gắn với database ứng dụng.**

### 8.1. Bẫy “đánh dấu đã đọc = đã xử lý”

~~~text
T1 Receiver tải email M1
T2 Receiver đánh dấu M1 là SEEN
T3 Handler tạo ticket nhưng database lỗi
T4 Ứng dụng crash
T5 Poller lần sau chỉ tìm UNSEEN
T6 M1 không được xử lý lại
~~~

Nếu message chỉ được tìm bằng trạng thái chưa đọc, hệ thống có thể **bỏ sót** M1. Ngược lại, nếu không bao giờ đánh dấu SEEN, poller có thể tải lại M1 mỗi lần và tạo ticket trùng.

Không có một cấu hình flag duy nhất giải quyết mọi tình huống; cần kết hợp **durable inbox + idempotency + quy tắc flag/checkpoint**.

### 8.2. Chiến lược đáng tin cậy hơn

~~~text
1. Nhận email M1
2. Xác định khóa nhận dạng ổn định trong phạm vi mailbox
3. Ghi inbound record + nội dung cần thiết bền vững
4. Commit transaction inbound store
5. Cập nhật mailbox flag/checkpoint theo policy
6. Worker xử lý inbound record idempotent
7. Ghi status PROCESSED hoặc FAILED
~~~

Nếu crash xảy ra sau bước 4 nhưng trước bước 5, lần quét sau có thể nhận lại M1. **Unique constraint/upsert** trong inbound store ngăn tạo record trùng. Đây thường là hành vi mong muốn hơn là cố tin vào việc một cờ SEEN tương đương đã xử lý xong.

### 8.3. Xóa thư khỏi mailbox?

Không tự động bật `shouldDeleteMessages=true` cho email quan trọng nếu chưa có retention và recovery strategy. Với IMAP, `\Deleted` có thể cần expunge để xóa vật lý; hành vi cụ thể còn phụ thuộc receiver, folder mode và server. Với POP3, deletion semantics khác IMAP và thường được thực hiện theo phiên giao thức.

Phương án thường an toàn:

- giữ thư trên mailbox trong thời hạn retention;
- đánh dấu/di chuyển sau khi ingest thành công;
- dọn thư theo một tác vụ retention riêng có audit;
- không xóa trước khi dữ liệu/attachment thiết yếu đã lưu bền vững.

Nếu chính sách bắt buộc xóa sớm vì dữ liệu nhạy cảm, vẫn cần xác định điểm commit và cách phục hồi khi lỗi.

## 9. Idempotency và nhận dạng message

Email có thể được đọc nhiều lần vì:

- ứng dụng restart;
- IMAP connection bị ngắt rồi reconnect;
- cờ SEEN thay đổi bởi người dùng hoặc client khác;
- receiver chạy trên nhiều replica;
- tác vụ reconciliation quét lại;
- DB commit thành công nhưng update flag thất bại.

**Idempotency** là yêu cầu cốt lõi cho một inbox processor production.

### 9.1. Message-ID không phải khóa duy nhất tuyệt đối

Header `Message-ID` có dạng ví dụ:

~~~text
Message-ID: <opaque-id@sender.example>
~~~

Nó hữu ích cho correlation và threading, nhưng:

- có thư thiếu Message-ID;
- người gửi có thể tạo ID không đúng/không unique;
- cùng một message có thể xuất hiện ở nhiều mailbox;
- header có thể bị giả mạo;
- nội dung forward/import có thể giữ ID cũ.

Do đó, không nên chỉ dùng `Message-ID` làm unique key toàn hệ thống mà không hiểu phạm vi và các trường hợp ngoại lệ.

### 9.2. IMAP UID và UIDVALIDITY

IMAP cung cấp UID cho message trong folder. UID có ý nghĩa cùng với **UIDVALIDITY** của folder: nếu UIDVALIDITY thay đổi, một UID số cũ có thể không còn chỉ cùng một message.

Một khóa kỹ thuật thường gồm:

~~~text
mailbox_account_id
folder_identifier
uid_validity
message_uid
~~~

Khi sử dụng Jakarta Mail, folder IMAP có thể hỗ trợ `UIDFolder`:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public record ImapIdentity(
        long uidValidity,
        long uid) {
}

static ImapIdentity identityOf(Message message)
        throws Exception {
    Folder folder = message.getFolder();
    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Folder does not support IMAP UID");
    }

    return new ImapIdentity(
            uidFolder.getUIDValidity(),
            uidFolder.getUID(message));
}
~~~

**Quan trọng:** ví dụ cần được gọi **khi folder/connection vẫn mở và message còn hợp lệ**. Một `MimeMessage` đã được tách khỏi IMAP folder hoặc đã bị đóng có thể không cho truy vấn UID. Vì vậy, việc lấy UID nên nằm trong phần ingest/receiver có quyền truy cập folder, không đặt tùy ý trong async worker chạy nhiều phút sau.

UID có ý nghĩa **theo mailbox/folder**; khi di chuyển thư sang folder khác, cần hiểu UID mới. Trong production, sử dụng khóa ghép với account và folder, không chỉ một số nguyên UID.

### 9.3. POP3 UIDL

Một số POP3 server hỗ trợ UIDL để nhận dạng message giữa các phiên. Tính sẵn có và đặc tính ổn định phụ thuộc provider/implementation. Nếu không có UIDL đáng tin, cần lựa chọn khác như message metadata/hash có kiểm soát, đồng thời chấp nhận rằng dedupe có thể không hoàn hảo.

Không dùng **message sequence number** trong folder làm định danh bền vững qua lần poll và thay đổi mailbox.

### 9.4. Bảng inbound deduplication

Ví dụ thiết kế PostgreSQL:

~~~sql
CREATE TABLE inbound_mail (
    inbound_id        UUID PRIMARY KEY,
    mailbox_account   VARCHAR(120) NOT NULL,
    folder_id         VARCHAR(250) NOT NULL,
    uid_validity      BIGINT NOT NULL,
    message_uid       BIGINT NOT NULL,
    rfc_message_id    VARCHAR(1000),
    subject_summary   VARCHAR(300),
    state             VARCHAR(40) NOT NULL,
    received_at       TIMESTAMPTZ NOT NULL,
    ingested_at       TIMESTAMPTZ NOT NULL,
    processed_at      TIMESTAMPTZ,
    UNIQUE (
        mailbox_account,
        folder_id,
        uid_validity,
        message_uid
    )
);
~~~

Đây là mô hình **cho nguồn IMAP đã có UID hợp lệ**, không phải schema áp dụng nguyên xi cho POP3. Có thể bổ sung trường storage key của MIME/attachment và cấu hình retention. `subject_summary` là dữ liệu có thể chứa PII nên cần quyền truy cập và thời hạn lưu phù hợp.

Một cách ingest:

~~~sql
INSERT INTO inbound_mail (
    inbound_id,
    mailbox_account,
    folder_id,
    uid_validity,
    message_uid,
    state,
    received_at,
    ingested_at
)
VALUES (
    :id,
    :account,
    :folder,
    :uid_validity,
    :uid,
    'INGESTED',
    :received_at,
    CURRENT_TIMESTAMP
)
ON CONFLICT (
    mailbox_account,
    folder_id,
    uid_validity,
    message_uid
) DO NOTHING;
~~~

Nếu insert không tạo row mới, message đã từng được ingest trong cùng phạm vi UID. Không tạo ticket mới vô điều kiện. Việc phát business event nên gắn với transaction/outbox của inbound record để tránh tạo hai ticket.

### 9.5. Hai consumer cùng đọc một mailbox

Nếu nhiều replica polling một mailbox, cả hai có thể nhận cùng một email:

~~~text
Pod A: tìm thấy M1
Pod B: tìm thấy M1
Pod A: INSERT inbound record -> success
Pod B: INSERT same unique key -> conflict / no-op
~~~

Unique constraint giúp ngăn xử lý trùng ở lớp dữ liệu. Tuy vậy, hai pod vẫn gây thêm traffic và có thể tranh chấp IMAP flags/connection. Với một mailbox quan trọng, thường nên có **leader/lease hoặc một consumer chủ động** trong mỗi thời điểm, cộng với dedupe bền vững.

Không tin vào `@Scheduled` hoặc `@EnableIntegration` tự động tạo distributed lock giữa các instance.

## 10. Quản lý folder và vòng đời MimeMessage

Một `MimeMessage` được đọc từ IMAP có thể liên quan tới dữ liệu trên server. Một số thành phần content/attachment có thể được tải **lười** khi gọi `getContent()` hoặc `getInputStream()`.

Ví dụ:

~~~text
IMAP receiver đọc metadata
   |
   v
Đưa MimeMessage đến async worker
   |
   v
Receiver đóng IMAP Folder
   |
   v
Worker gọi getInputStream() trên attachment
   |
   v
FolderClosedException / lỗi I/O
~~~

### 10.1. Không chuyển raw MimeMessage qua queue bền vững

Một queue/database thường cần payload đã **vật hóa**:

~~~text
InboundMailRecord {
  mailboxId,
  sourceMessageKey,
  fromAddress,
  subject,
  receivedAt,
  textBodyStorageRef,
  attachmentStorageRefs,
  state
}
~~~

Trong phạm vi receiver còn có quyền truy cập folder:

1. Đọc MIME trong giới hạn kích thước.
2. Chuyển dữ liệu cần thiết thành DTO/bytes/storage object.
3. Đóng stream và lưu dữ liệu bền vững.
4. Commit inbound record.
5. Chỉ sau đó cho worker async sử dụng storage references.

Không giữ đối tượng `MimeMessage` gắn với một folder đã đóng trong một queue dài hạn.

### 10.2. Tùy chọn autoCloseFolder

Một số phiên bản Spring Integration Mail cung cấp cấu hình về việc tự đóng folder sau khi receiver nhận message. Có thể phải điều chỉnh vòng đời folder khi muốn đọc nội dung MIME sau adapter.

**Không chỉ tắt tự đóng folder để “chữa lỗi” rồi bỏ quên cleanup.** Giữ folder mở quá lâu có thể cạn kết nối hoặc gây lỗi khi server timeout. Hãy chọn thiết kế đọc/vật hóa nội dung tại đúng giai đoạn, và xác minh semantics của phiên bản Spring Integration đang dùng.

### 10.3. Đóng InputStream

Nếu đọc attachment:

~~~java
try (var input = bodyPart.getInputStream()) {
    // Stream bytes vào storage có giới hạn size.
}
~~~

Nên dùng streaming với giới hạn số bytes, không gọi `readAllBytes()` vô điều kiện trên thư từ Internet khi chưa biết kích thước.

## 11. Đọc cấu trúc MIME an toàn

Một email có thể gồm:

~~~text
MimeMessage
  |
  +-- multipart/mixed
        |
        +-- multipart/alternative
        |     +-- text/plain
        |     +-- text/html
        |
        +-- application/pdf; attachment
        +-- image/png; inline; Content-ID
~~~

Không giả định mọi email đều là một `String`. `MimeMessage.getContent()` có thể trả về `String`, `Multipart` hoặc đối tượng khác tùy MIME part và implementation.

### 11.1. Duyệt phần nội dung

Ví dụ utility minh họa:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeWalker {
    private MimeWalker() {}

    public static void walk(Part part, int depth)
            throws Exception {
        if (depth > 12) {
            throw new IllegalArgumentException(
                    "MIME nesting limit exceeded");
        }

        if (part.isMimeType("multipart/*")) {
            Multipart parts = (Multipart) part.getContent();
            if (parts.getCount() > 100) {
                throw new IllegalArgumentException(
                        "Too many MIME parts");
            }
            for (int i = 0; i < parts.getCount(); i++) {
                walk(parts.getBodyPart(i), depth + 1);
            }
            return;
        }

        if (part.isMimeType("text/plain")) {
            // Đọc text có giới hạn size và charset phù hợp.
            return;
        }
        if (part.isMimeType("text/html")) {
            // Không render HTML không tin cậy vào trang quản trị.
            return;
        }

        // Attachment/inline/other content: kiểm tra MIME type,
        // size, disposition, filename rồi stream vào storage.
    }
}
~~~

Utility này chỉ minh họa **kiểm soát độ sâu và số part**. Nó chưa thực hiện giới hạn tổng số bytes, decompression ratio, character decoding, nested `message/rfc822`, xử lý signed/encrypted email hay malware scanning. Với đầu vào không tin cậy, cần thêm các bảo vệ tương ứng.

### 11.2. HTML email không đáng tin cậy

Email HTML có thể chứa:

- script hoặc markup gây XSS nếu render trực tiếp;
- remote images/tracking URLs;
- link giả mạo;
- CSS/HTML đặc biệt;
- attachment có content type giả.

Nếu hiển thị nội dung nhận trong dashboard hỗ trợ, cần sanitize HTML, cô lập môi trường render, kiểm soát remote resources và chuẩn hóa link. Không giả định email từ hộp thư đáng tin đã được an toàn cho browser.

### 11.3. Filename và attachment path traversal

Không viết:

~~~java
Path target = uploadDir.resolve(part.getFileName());
Files.copy(part.getInputStream(), target);
~~~

mà không validate filename. Một attachment có thể khai báo:

~~~text
../../config/application.yml
C:\Windows\...
invoice.pdf/../secret.txt
~~~

Nên tạo **storage key do server sinh**, ví dụ UUID, và giữ filename gốc chỉ làm metadata đã được lọc:

~~~java
Path target = uploadDir.resolve(
        UUID.randomUUID().toString() + ".bin");
~~~

Sau đó xác minh path chuẩn hóa nằm trong thư mục được cấp, giới hạn kích thước, quyền file và xử lý symlink theo môi trường. Không dùng filename do người gửi cung cấp làm đường dẫn ghi trực tiếp.

### 11.4. Attachment có thể là mã độc

Khi nhận PDF, Office document, ZIP hoặc tệp khác:

- đặt giới hạn mỗi file và tổng message;
- giới hạn số attachment và độ sâu multipart;
- kiểm tra định dạng thực tế thay vì tin `Content-Type`;
- quét malware nếu ứng dụng lưu/phát tán file;
- tránh auto-execute, auto-extract không giới hạn;
- giới hạn giải nén để chống zip bomb;
- lưu file ở vùng không có quyền thực thi;
- không công khai file trước khi qua chính sách kiểm tra.

Receiver là **biên giới tin cậy**: mọi From, Subject, MIME headers và attachment đều là input từ bên ngoài.

## 12. Xác thực người gửi và phòng chống email giả mạo

Một người gửi có thể đặt:

~~~text
From: invoices@trusted-partner.example
~~~

nhưng giá trị From **không phải bằng chứng mật mã về danh tính**. Khi dùng email để kích hoạt nghiệp vụ nhạy cảm:

- kiểm tra kết quả SPF/DKIM/DMARC từ hệ thống mail nhận có độ tin cậy;
- hiểu rằng `Authentication-Results` có thể là header được chèn tại nhiều hop; chỉ tin header do hạ tầng nhận đáng tin tạo ra;
- so khớp allowlist sender/domain chỉ như một lớp kiểm tra, không phải bảo đảm duy nhất;
- dùng chữ ký tài liệu/S/MIME/PGP hoặc xác minh ngoài băng nếu workflow yêu cầu;
- tránh tự động duyệt thanh toán hay thay đổi quyền chỉ dựa vào địa chỉ From;
- xác minh business correlation ID một cách an toàn.

Ví dụ không an toàn:

~~~text
Email From: finance@partner.example
Subject: Approve payment
Body: Please transfer money to new account.
~~~

Nếu ứng dụng tự cập nhật thông tin thanh toán chỉ dựa vào From và subject, kẻ tấn công có thể giả mạo email. Cần phê duyệt/quy tắc xác minh độc lập cho thao tác rủi ro cao.

## 13. Authentication, TLS và OAuth2 cho IMAP

Receiver cần xác thực với mail server và bảo vệ nội dung trên đường truyền.

### 13.1. IMAPS/POP3S

Ví dụ thông số:

~~~text
IMAPS: protocol=imaps, TLS implicit, thường port 993
POP3S: protocol=pop3s, TLS implicit, thường port 995
IMAP STARTTLS: thường port 143, nếu provider hỗ trợ
~~~

Properties cho IMAPS có prefix `mail.imaps.`:

~~~properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=15000
mail.imaps.ssl.checkserveridentity=true
~~~

Với IMAP không implicit TLS mà dùng STARTTLS, thuộc tính thuộc protocol `imap` và phải đặt STARTTLS required/hostname verification theo tài liệu provider. Không sao chép nguyên `mail.imaps.*` sang một kết nối `imap` rồi mặc định được áp dụng.

### 13.2. Không vô hiệu hóa chứng chỉ

Không đặt trust-all socket factory để “làm cho test/production chạy được”. Cách đúng là:

- dùng đúng hostname và port;
- xác minh certificate chain;
- cấu hình truststore phù hợp;
- điều tra TLS inspection/proxy;
- cập nhật CA certificate nếu cần.

Email nhận và credential mailbox có thể chứa thông tin nhạy cảm; TLS không hợp lệ có thể cho phép server giả mạo.

### 13.3. OAuth2/XOAUTH2

Nhiều nhà cung cấp hạn chế Basic Authentication đối với IMAP/POP3. Họ có thể yêu cầu OAuth 2.0 với SASL XOAUTH2 hoặc một cơ chế khác.

Quy trình mức khái niệm:

~~~text
Identity provider
   |
   | token theo scope/audience mailbox
   v
AccessTokenProvider
   |
   v
Jakarta Mail IMAP authentication (XOAUTH2)
   |
   v
Spring Integration IMAP receiver
~~~

Phải kiểm tra:

- provider thực sự hỗ trợ IMAP OAuth cho loại tài khoản/tenant;
- scope, token audience và mailbox identity;
- delegated hay app-only flow được phép;
- token expiry, refresh và revocation;
- khả năng thay đổi credential khi kết nối reconnect;
- cơ chế SASL/auth mà phiên bản mail provider đang dùng hỗ trợ.

**Không dùng token của một API khác như mật khẩu IMAP** nếu audience/scope không đúng. Không đưa access token vào log, exception text hoặc mail header. Nếu provider chỉ hỗ trợ HTTP API với permission phù hợp, cân nhắc dùng API thay IMAP.

### 13.4. Secret không nằm trong source code

Không hard-code:

~~~java
new ImapMailReceiver(
    "imaps://real-user:real-password@mail.example.com:993/INBOX");
~~~

Đây là ví dụ **cách không nên làm**. Với production dùng secret manager, managed identity nếu provider hỗ trợ, hoặc cơ chế cung cấp credential của framework. Nếu URL được build từ secret, tránh log full URL và chú ý ký tự đặc biệt/encoding.

## 14. Phân loại lỗi và chiến lược retry

Không phải mọi lỗi khi nhận email đều nên xử lý giống nhau.

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Authentication | Credential hết hạn, OAuth permission bị thu hồi | Cảnh báo, refresh/rotate hợp lệ; không retry liên tục |
| TLS/certificate | Hostname mismatch, chain không tin cậy | Dừng kết nối, sửa trust/config |
| Network | Timeout, connection reset | Retry với backoff và jitter |
| Folder unavailable | INBOX/folder bị đổi hoặc thiếu quyền | Kiểm tra cấu hình/quyền |
| MIME parse error | Multipart hỏng, charset không hợp lệ | Quarantine hoặc đánh dấu xử lý thất bại |
| Attachment limit | Tệp quá lớn, số parts vượt mức | Quarantine/reject theo policy |
| Business validation | Không đủ dữ liệu tạo ticket | Đưa vào dead-letter/manual review |
| Database failure | Không ghi được inbound record | Retry ingest, không ack xóa mail |
| Duplicate message | UID đã có record | No-op hoặc kiểm tra trạng thái record |

### 14.1. Lỗi ở receiver khác lỗi ở handler

~~~text
Receiver connect/search/read failure
  -> không nhận được message
  -> reconnect/backoff, alert mailbox health

Handler parsing/business failure
  -> message đã xuất hiện trong flow
  -> cần record lỗi + quarantine/retry
~~~

Nếu nhận thư đã bị đánh dấu SEEN trước khi handler lỗi, việc retry chỉ bằng cách đợi IMAP unread polling tiếp theo có thể không hoạt động.

### 14.2. Retry có giới hạn

Không retry vô hạn một MIME message hỏng, attachment độc hại hoặc yêu cầu nghiệp vụ không hợp lệ. Có thể dùng:

~~~text
INGESTED -> PROCESSING
           |
           +-- PROCESSED
           +-- RETRY_WAIT -> PROCESSING
           +-- QUARANTINED / FAILED_FINAL
~~~

Lưu attempt count, next retry time, error class và correlation ID. Quarantine cần giữ dữ liệu tối thiểu đủ phục vụ điều tra nhưng tuân thủ quyền truy cập và retention.

### 14.3. Error channel trong Spring Integration

Spring Integration có cơ chế error messages/error channels cho một số endpoint và flow. Khi sử dụng, xác định:

- lỗi đồng bộ được ném về poller hay chuyển đến error channel?
- message gốc và exception có được lưu bền vững không?
- error handler có thực hiện retry hay chỉ log?
- một exception làm dừng toàn bộ flow hay chỉ một message?

**Error channel không tự tạo transaction giữa IMAP flags và database**. Nó là cơ chế xử lý lỗi ở messaging pipeline, vẫn cần thiết kế idempotency và durable state.

## 15. Cô lập tài khoản và tenant khi có nhiều mailbox

Một ứng dụng SaaS có thể đọc các mailbox:

~~~text
tenant-a -> support-a@...
tenant-b -> invoices-b@...
tenant-c -> claims-c@...
~~~

Mỗi mailbox có:

- provider/host/port;
- credential/token riêng;
- folder/search policy;
- cursor/UIDVALIDITY/checkpoint riêng;
- quota, rate limit và retention riêng.

Đừng lấy From của email làm tenant ID: người gửi có thể giả mạo. Tenant identity nên được xác định từ **mailbox account cấu hình sẵn** hoặc routing đã được xác thực.

### 15.1. Một receiver cho mỗi mailbox?

Có thể tạo receiver/flow riêng cho từng mailbox khi số lượng nhỏ. Với hàng nghìn tenant, mỗi mailbox giữ một IDLE connection có thể vượt giới hạn provider và tốn memory/thread/socket.

Các chiến lược khác:

- scheduler phân nhóm mailbox và polling có giới hạn concurrency;
- cân bằng mailbox theo worker shards;
- dynamic receiver lifecycle được quản lý;
- provider inbound webhook/API nếu phù hợp;
- một mailbox chung với routing dựa trên địa chỉ đích đã xác minh, khi mô hình nghiệp vụ cho phép.

### 15.2. Không chia sẻ session/credential sai tenant

Phải cô lập:

- credential và OAuth token;
- mailbox UID/checkpoints;
- inbound deduplication key;
- attachment storage;
- event log;
- quyền xem nội dung.

Nếu receiver tenant A đưa message sang handler tenant B do cấu hình nhầm, hậu quả có thể là rò rỉ dữ liệu. Test mapping mailbox-to-tenant là một phần quan trọng của integration test.

## 16. Cách tránh vòng lặp auto-reply và email storm

Một receiver có thể tạo ticket rồi tự trả lời:

~~~text
Customer email -> inbound receiver
   -> ticket created -> automatic reply
   -> customer auto-responder
   -> inbound receiver
   -> new reply ...
~~~

Để giảm nguy cơ:

- phát hiện thông báo tự động qua header `Auto-Submitted`, `Precedence` và đặc điểm provider, nhưng không coi một header đơn lẻ là tín hiệu hoàn hảo;
- dùng correlation IDs / threading như `In-Reply-To` và `References`;
- không trả lời mọi bounce hoặc delivery status notification bằng một email mới;
- giới hạn số auto-reply theo conversation/recipient/thời gian;
- nhận diện địa chỉ hệ thống của chính mình;
- dùng sender policy và rate limit;
- có kill switch cho inbound-triggered outgoing mail.

Không dùng subject chứa “Re:” làm bằng chứng duy nhất rằng email thuộc ticket cũ; header threading có thể thiếu hoặc giả mạo.

## 17. Quan sát và vận hành receiver

Các chỉ số có ích:

| Metric/Signal | Ý nghĩa |
| --- | --- |
| `inbound_mail_poll_total` | Số lần polling |
| `inbound_mail_poll_error_total` | Polling/connection errors |
| `inbound_mail_received_total` | Số message receiver đọc được |
| `inbound_mail_ingested_total` | Message đã lưu inbound record |
| `inbound_mail_duplicate_total` | Message bị deduplicate |
| `inbound_mail_processing_failed_total` | Business processing failures |
| `inbound_mail_quarantined_total` | Message bị quarantine |
| `inbound_mail_processing_duration_seconds` | Thời gian xử lý |
| `inbound_mail_oldest_pending_age_seconds` | Tuổi inbound job pending lâu nhất |
| `inbound_mail_attachment_bytes` | Dung lượng nhận, dùng histogram/summary phù hợp |
| `inbound_mail_last_success_timestamp_seconds` | Thời điểm nhận/ingest thành công gần nhất |

Tên ở đây là **tên đề xuất do ứng dụng tự instrument**, không phải tất cả metric Spring Integration tự động cung cấp sẵn.

### 17.1. Bounded metric tags

Nên dùng:

~~~text
mailbox_profile=support_primary
protocol=imaps
stage=poll|ingest|process
result=ok|error|duplicate
error_class=auth|tls|network|mime|storage|unknown
~~~

Không dùng raw From, Subject, Message-ID, recipient email, UID hoặc từng tenant ID động làm mọi metric label. Những dữ liệu chi tiết nên nằm trong log/DB có phân quyền.

### 17.2. Dashboard health

~~~text
Mailbox receiver health
------------------------------------------------
Receiver connected: YES
Last successful poll: 15 seconds ago
Last successful ingest: 40 seconds ago
Inbox messages observed: 320
New inbound jobs: 12 in last 5 minutes
Processing retry backlog: 8
Quarantined: 2 today
Connection errors: 0 in last 1 hour
------------------------------------------------
~~~

Số liệu chỉ minh họa. Với mailbox ít traffic, “không nhận được email mới trong một giờ” **không tự là sự cố**. Cần kết hợp polling health, connection status và kỳ vọng traffic.

### 17.3. Cảnh báo

- Receiver bị authentication failure liên tục.
- IMAP IDLE không reconnect được hoặc polling dừng lâu.
- Mailbox gần đầy/quota tăng, nếu provider expose.
- Inbound job pending lâu bất thường.
- Lỗi MIME parse/quarantine tăng đột ngột.
- Lỗi lưu attachment/storage.
- Một tenant/mailbox nhận lưu lượng bất thường.
- Worker xử lý tắc, gây backpressure lên ingest.

Không xuất raw email, attachment, token hay thông tin cá nhân vào alert.

## 18. Kiểm thử tích hợp với SMTP + IMAP server giả lập

Unit test của handler có thể tạo `MimeMessage` trong bộ nhớ. Nhưng để kiểm tra **receiver thực sự kết nối IMAP và đọc hộp thư**, nên dùng integration test với một mail server thử nghiệm hỗ trợ IMAP, ví dụ GreenMail.

Mô hình:

~~~text
JUnit test
   |
   +-- start GreenMail SMTP + IMAP
   |
   +-- send fixture email vào SMTP test server
   |
   +-- Spring Integration ImapMailReceiver poll inbox
   |
   +-- handler ghi inbound record/test sink
   |
   +-- assert metadata, MIME, state, dedupe
   |
   +-- stop flow/server + cleanup DB/files
~~~

### 18.1. Các tầng test

| Loại test | Mục tiêu |
| --- | --- |
| Unit test MIME parser | `String`/`Multipart`, attachment, charset, lỗi MIME |
| Unit test classification | From, subject, correlation, validation rule |
| Unit test deduplication | Unique key/UIDVALIDITY, duplicate no-op |
| Integration test IMAP | Connect, poll, flags, folder lifecycle |
| Integration test IDLE | Notification/reconnect và rescan behavior |
| Integration test DB/outbox | Commit, retry, crash giữa ingest/ack |
| Provider sandbox test | TLS/auth/OAuth, quota, folder behavior thực tế |

### 18.2. Test cases quan trọng

1. Hộp thư rỗng: receiver không tạo inbound job.
2. Có một email mới: nhận đúng From, Subject và nội dung.
3. Email có HTML và plain text: parser nhận đúng hai loại.
4. Email có nhiều attachment: xử lý theo giới hạn và lưu đúng.
5. Email thiếu Message-ID: không crash vô hạn.
6. Email có ký tự Unicode/charset khác nhau: decode phù hợp.
7. Mailbox chứa message đã đọc: hành vi search/flags đúng policy.
8. Database lỗi sau khi nhận: không đánh mất email.
9. Cùng email đọc hai lần: không tạo ticket trùng.
10. Hai receiver chạy đồng thời: dedupe/lease hoạt động.
11. IMAP folder bị đóng trước khi đọc attachment: phát hiện và xử lý lifecycle.
12. IDLE connection bị ngắt: reconnect và reconciliation.
13. Credential/token hết hạn: lỗi auth được phân loại, không retry dồn dập.
14. Attachment filename độc hại hoặc file quá lớn: quarantine, không path traversal.
15. Email giả From: không tự kích hoạt thao tác nhạy cảm.

### 18.3. Test bằng điều kiện thay vì sleep cố định

Không nên:

~~~java
Thread.sleep(3000);
assertEquals(1, inboundRepository.count());
~~~

Timing phụ thuộc máy và CI. Nếu dùng Awaitility trong test:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals(
            1,
            inboundRepository.countByMailboxProfile(
                    "support_primary")));
~~~

`await()` là ví dụ API của Awaitility khi dự án có dependency tương ứng. Điều kiện nên kiểm tra record của **test hiện tại**, không đếm toàn bộ mailbox/DB nếu fixture dùng chung.

### 18.4. Cleanup

Integration test phải giải phóng:

- IMAP/SMTP test server hoặc container theo đúng owner;
- mailbox messages và flags;
- inbound DB records / queue jobs;
- background schedulers/async workers;
- attachment/temp files/streams;
- Spring context gắn port động nếu context được cache.

Không purge toàn bộ mailbox trong `@AfterEach` nếu các test khác dùng cùng server và chạy song song. Ưu tiên per-test fixture, account/recipient riêng hoặc test correlation ID.

## 19. Những lỗi thường gặp khi triển khai

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `JavaMailSender` để đọc inbox | Không đúng API/giao thức | Dùng Spring Integration Mail receiver |
| Chỉ thêm mail starter rồi chờ auto-receive | Không có inbound flow | Cấu hình receiver và endpoint |
| Nhầm `org.springframework.messaging.Message` với Jakarta `Message` | Cast/type lỗi | Phân biệt wrapper và payload |
| Đánh dấu `SEEN` trước durable ingest rồi coi là ack | Có thể mất xử lý khi crash | Durable inbox + reconciliation |
| Không đánh dấu hoặc checkpoint gì | Poll lại gây ticket trùng | Idempotency và read/flag policy |
| Dùng sequence number IMAP làm ID vĩnh viễn | Sai sau thay đổi folder | UID + UIDVALIDITY + folder + account |
| Chỉ dùng Message-ID làm unique key | Thiếu/trùng/giả mạo | Khóa dựa trên mailbox và UID |
| Chuyển `MimeMessage` gắn folder đã đóng sang async worker | `FolderClosedException` | Materialize content trong giai đoạn nhận |
| Dùng IDLE và mặc định không mất notification | Có thể bỏ sót mail | Reconnect và periodic rescan |
| Nhiều pod cùng poll mà không có dedupe | Duplicate processing | Lease/leader + unique constraint |
| Nhận tất cả attachment vào RAM | OutOfMemory | Streaming + size limits |
| Dùng filename gốc làm filesystem path | Path traversal/overwrite | Storage key an toàn |
| Hiển thị HTML email trực tiếp | XSS/tracking | Sanitize và cô lập render |
| Tin vào header From cho phê duyệt | Email spoofing | Xác minh thêm danh tính nghiệp vụ |
| Tắt TLS hostname verification để sửa lỗi | Credential/data có thể bị lộ | Sửa CA/truststore/endpoint |
| Poll quá nhanh và không backpressure | Quota, tải cao | Rate limit, queue capacity |
| Retry email lỗi MIME vô hạn | Poison message kẹt flow | Quarantine/FAILED_FINAL |
| Không đóng server/folder/stream trong test | Leak/socket conflict | Quản lý lifecycle theo owner |
| Ghi raw email và token vào log | Lộ dữ liệu nhạy cảm | Metadata tối thiểu, phân quyền |

## 20. Tình huống tổng hợp: hộp thư support tạo ticket

Giả sử một ứng dụng có hộp thư `support@example.com`. Mỗi email từ khách hàng sẽ được xử lý thành yêu cầu hỗ trợ.

### 20.1. Kiến trúc

~~~mermaid
flowchart TD
    A["Customer sends email"] --> B["Support mailbox"]
    B --> C["IMAP receiver"]
    C --> D["Extract UID + bounded MIME"]
    D --> E{"Already ingested?"}
    E -->|Yes| F["No-op / reconcile state"]
    E -->|No| G["Durable inbound_mail + content storage"]
    G --> H["Ticket processing queue"]
    H --> I{"Validation / processing"}
    I -->|Success| J["Ticket created"]
    I -->|Transient error| K["Retry wait"]
    I -->|Invalid/unsafe| L["Quarantine"]
    K --> H
~~~

### 20.2. Một email bình thường

~~~text
Mailbox: support-primary
Folder: INBOX
UIDVALIDITY: 1008
UID: 5521
Message-ID: <opaque-id@customer.example>
From: customer@example.net
Subject: Tôi không đăng nhập được
Attachment: screenshot.png
~~~

Receiver:

1. Kết nối IMAPS qua TLS, xác thực bằng credential được phép.
2. Tìm message mới theo search policy.
3. Trong khi folder còn mở, lấy mailbox/folder/UIDVALIDITY/UID.
4. Đọc và kiểm tra MIME trong giới hạn; lưu attachment bằng storage key riêng.
5. Insert record `inbound_mail` với unique key tương ứng.
6. Commit record và phát job tạo ticket.
7. Cập nhật cờ mailbox/checkpoint theo policy.
8. Worker tạo ticket, liên kết ticket với inbound ID.

Nếu receiver crash sau bước 6 nhưng trước bước 7, lần scan sau có thể đọc lại thư. Unique key giúp không tạo ticket thứ hai.

### 20.3. Một email không hợp lệ

Email có:

~~~text
From: unknown@example.net
Attachment: ../../app-config.yml
Size: vượt giới hạn cho phép
~~~

Ứng dụng không lưu filename gốc ra đường dẫn tự do, không cố đọc hết vào RAM và không tạo ticket chứa file nguy hiểm. Nó ghi metadata/quarantine event có kiểm soát, đồng thời tránh loop xử lý cùng poison message vô hạn.

### 20.4. Lỗi provider IMAP

Khi server đóng kết nối:

1. Receiver phân loại lỗi network/folder.
2. Có backoff và reconnect thay vì quay vòng tức thì.
3. Sau khi phục hồi, reconciliation quét mailbox theo checkpoint.
4. Dedupe ngăn tạo ticket trùng với thư từng ingest.
5. Dashboard báo thời gian poll thành công gần nhất, số lỗi và backlog.

## 21. Checklist trước production

### Giao thức và kết nối

- [ ] Chọn IMAP polling, IMAP IDLE hoặc POP3 theo yêu cầu.
- [ ] Host, port, folder và URL được xác minh với provider.
- [ ] TLS/hostname verification được bật theo đúng protocol.
- [ ] Credential/token nằm trong secret store; hỗ trợ rotate/refresh.
- [ ] Có connection/read timeout và reconnect/backoff.

### Ingest và trạng thái

- [ ] Hiểu rõ `SEEN`, `DELETED` và cơ chế tìm thư của receiver.
- [ ] Không coi flag đã đọc là bằng chứng nghiệp vụ hoàn thành.
- [ ] Có durable inbound store trước khi ack/checkpoint.
- [ ] Khóa deduplication có mailbox/folder/UIDVALIDITY/UID với IMAP.
- [ ] Có chiến lược reconciliation khi crash/IDLE disconnect.
- [ ] Đảm bảo không có hai consumer làm sai cùng mailbox.

### MIME và bảo mật

- [ ] Đọc nội dung khi folder còn mở hoặc vật hóa vào storage.
- [ ] Có giới hạn message bytes, số MIME parts và nesting depth.
- [ ] Attachment dùng tên storage do server sinh, không dùng path người gửi.
- [ ] Có malware scanning/quarantine theo nhu cầu.
- [ ] HTML từ email không được render trực tiếp không sanitize.
- [ ] Không tin header From/Subject để thực hiện hành động nhạy cảm.
- [ ] Không log nội dung thư, token hoặc thông tin cá nhân không cần thiết.

### Xử lý nghiệp vụ

- [ ] Có state machine INGESTED/PROCESSING/PROCESSED/RETRY/QUARANTINED.
- [ ] Retry có giới hạn và phân biệt lỗi tạm thời/vĩnh viễn.
- [ ] Business worker idempotent, tránh ticket/invoice trùng.
- [ ] Có backpressure nếu mailbox hoặc attachment tăng đột ngột.
- [ ] Có cơ chế tránh auto-reply loop.
- [ ] Tenant identity được suy ra từ mailbox/routing đã xác minh.

### Quan sát và kiểm thử

- [ ] Đo poll errors, ingest success, duplicates và pending age.
- [ ] Cảnh báo khi receiver ngừng hoạt động hoặc auth thất bại.
- [ ] Integration test IMAP flags, UID, crash/retry và IDLE reconnect.
- [ ] Test MIME độc hại, Unicode, file quá lớn và duplicate.
- [ ] Test fixture dọn mailbox, DB, queue và attachment files.

## 22. Những điều cần nhớ

- **Spring Integration Mail** cung cấp thành phần **nhận email** qua IMAP/POP3, khác với `JavaMailSender` dùng để gửi qua SMTP.
- Với polling, `MailReceivingMessageSource` và `ImapMailReceiver` kết hợp với poller để đưa email vào integration flow.
- Với IMAP IDLE, `ImapIdleChannelAdapter` nhận tín hiệu thay đổi từ server nhưng vẫn cần reconnect và reconciliation.
- Trong Spring Integration, `Message<?>` bao bọc payload; payload có thể là Jakarta `MimeMessage` hoặc dạng đã được chuyển đổi tùy cấu hình.
- `\Seen` và `\Deleted` là trạng thái mailbox, **không phải transaction ack của business processing**.
- Production cần **durable inbox, idempotency và checkpoint**; IMAP UID phải gắn với UIDVALIDITY, folder và account.
- Không giữ `MimeMessage` phụ thuộc folder đã đóng trong async job; hãy vật hóa dữ liệu cần thiết trong giai đoạn nhận.
- Nội dung email là input không tin cậy: giới hạn size, sanitize HTML, kiểm tra attachment và không tin header From cho thao tác rủi ro.
- TLS, credential management và OAuth configuration là một phần của bảo mật receiver.
- Cần phân biệt lỗi kết nối/nhận thư, lỗi MIME parse và lỗi nghiệp vụ để retry đúng.

Một mail receiver có thể bắt đầu đơn giản bằng vài bean Spring Integration, nhưng một hệ thống nhận email đáng tin cậy cần xác định rõ **khi nào thư đã được lưu, cách chống xử lý trùng, khi nào cập nhật trạng thái mailbox và phải làm gì khi kết nối hoặc handler thất bại**. Khi thiết kế được các ranh giới này, email đến có thể trở thành đầu vào ổn định cho ticket, hóa đơn và nhiều workflow khác của ứng dụng Spring.

### Tài liệu tham khảo

- **Spring Integration Reference — Mail Support:** inbound channel adapters, polling, IMAP IDLE, mail receivers và search strategy.
- **Spring Integration API:** `ImapMailReceiver`, `Pop3MailReceiver`, `MailReceivingMessageSource`, `ImapIdleChannelAdapter`.
- **Spring Integration Reference — Java DSL / Polling Consumers:** `IntegrationFlow`, `Pollers`, message channels và error handling.
- **Spring Framework Reference — Integration / Messaging:** `Message<?>`, message headers và channel semantics.
- **Jakarta Mail API:** `Message`, `MimeMessage`, `Folder`, `UIDFolder`, `Multipart`, `Part`.
- **RFC 3501 — Internet Message Access Protocol Version 4rev1:** IMAP folders, flags, UIDs và UIDVALIDITY (đối chiếu các cập nhật giao thức phù hợp provider).
- **RFC 9051 — Internet Message Access Protocol Version 4rev2:** IMAP4rev2.
- **RFC 2177 — IMAP4 IDLE command:** thông báo mailbox qua IDLE.
- **RFC 1939 — Post Office Protocol Version 3:** POP3 và UIDL.
- **RFC 5322 — Internet Message Format:** From, Subject, Message-ID, References và các header.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** MIME multipart, content type, charset và attachment.
- **Tài liệu IMAP/OAuth của nhà cung cấp mailbox đang dùng:** permissions, rate limits, connection policies, TLS và token lifecycle.
