# Inbound mail adapter và message source

Trong một ứng dụng sử dụng **Spring Framework Mail**, việc gửi thư thường bắt đầu từ `JavaMailSender` và giao thức SMTP. Chiều ngược lại — **đọc email đã đến hộp thư và đưa vào quy trình xử lý của ứng dụng** — có thể được xây dựng bằng **Spring Integration Mail**.

Spring Integration cung cấp hai khái niệm quan trọng:

- **Mail message source:** thành phần chủ động lấy email từ một mailbox (ví dụ IMAP hoặc POP3) và trả về một `org.springframework.messaging.Message<?>`.
- **Inbound mail adapter:** endpoint nối nguồn email vào hệ thống Spring Integration, quyết định *khi nào* lấy thư và *đưa kết quả tới đâu*. Với polling, endpoint gọi message source theo một `Poller`; với IMAP IDLE, adapter có thể phản ứng với thông báo thay đổi từ server.

Nhờ đó, logic đọc hộp thư được tách khỏi logic nghiệp vụ như tạo ticket, nhập hóa đơn hoặc cập nhật một yêu cầu hỗ trợ.

~~~text
Internet sender
    |
    | SMTP
    v
Mailbox trên mail server (INBOX)
    |
    | IMAP/POP3
    v
Mail Receiver
    |
    v
MailReceivingMessageSource
    |
    | Poller kích hoạt việc lấy thư
    v
Polling Inbound Channel Adapter
    |
    v
Spring Integration MessageChannel
    |
    v
Validation / MIME parser / durable inbox / business handler
~~~

Sơ đồ này mô tả **polling adapter**. Trong cấu hình IMAP IDLE, `ImapIdleChannelAdapter` đảm nhiệm phần tiếp nhận theo sự kiện và không cần một poller gọi `MailReceivingMessageSource` theo lịch thông thường.

**Giới hạn cần nhớ:** đây là ứng dụng *kết nối tới mailbox*, **không phải một SMTP server tự nhận email trực tiếp từ Internet**. Mail server/provider vẫn chịu trách nhiệm nhận và lưu thư trước khi ứng dụng đọc.

## 1. Tại sao cần inbound mail adapter?

Giả sử một doanh nghiệp có hộp thư `support@example.com`. Khi khách hàng gửi email, hệ thống muốn tự tạo ticket:

~~~text
Customer sends email
       |
       v
support@example.com
       |
       v
IMAP receiver
       |
       v
Normalize + validate MIME
       |
       v
Inbound-mail record
       |
       v
Ticket-processing worker
       |
       v
Ticket created
~~~

Nếu tự viết một vòng lặp bằng Jakarta Mail, ứng dụng phải tự quản lý:

1. Kết nối và xác thực mailbox.
2. Tìm email phù hợp.
3. Giữ/đóng folder và network session.
4. Tải và giải mã email.
5. Chạy vòng polling hoặc IMAP IDLE.
6. Chuyển message sang handler.
7. Phân loại lỗi và thử lại.
8. Quản lý cờ `SEEN`, `DELETED` hoặc checkpoint.

Spring Integration Mail đóng gói phần tích hợp phổ biến và giúp nối vào **channel, message handler, filter, transformer, router** của Spring Integration. Tuy nhiên, framework không tự biết business transaction nào đã hoàn thành, vì vậy **idempotency, lưu bền vững và an toàn nội dung** vẫn do ứng dụng thiết kế.

### 1.1. Các trường hợp sử dụng

| Tình huống | Cách sử dụng inbound flow |
| --- | --- |
| Hộp thư hỗ trợ | Tạo ticket từ email khách hàng |
| Nhận báo giá hoặc hóa đơn | Trích xuất dữ liệu và attachment rồi đưa vào quy trình đối soát |
| Hộp thư phản hồi | Ghép thư trả lời với một cuộc hội thoại bằng thông tin tương quan |
| Nhận báo cáo định kỳ | Lưu tệp từ đối tác vào kho xử lý |
| Nhận xác nhận thủ công | Tạo bản ghi yêu cầu kiểm tra bởi nhân viên |
| Hộp thư chuyên dùng cho import | Đưa email vào workflow nhập dữ liệu có kiểm soát |

Không nên sử dụng chỉ một header `From` để tự động phê duyệt chuyển tiền, cấp quyền hoặc thực hiện tác vụ nguy hiểm; email là đầu vào không đáng tin cậy.

## 2. Kiến trúc ba lớp: receiver, message source, endpoint

Ba đối tượng có vai trò khác nhau:

### 2.1. Mail receiver: truy cập mailbox

Receiver chuyên về giao thức và trạng thái:

- `ImapMailReceiver` làm việc với IMAP/IMAPS.
- `Pop3MailReceiver` làm việc với POP3/POP3S.

Receiver cần thông tin host, account, folder, protocol, credential và các thuộc tính JavaMail/Jakarta Mail như timeout hoặc TLS. Nó còn có những chính sách liên quan cách tìm/đánh dấu/xóa message.

### 2.2. Message source: cung cấp Spring message

`MailReceivingMessageSource` là cầu nối giữa mail receiver và mô hình **pollable message source** của Spring Integration.

Về mặt khái niệm:

~~~java
Message<?> springMessage = mailMessageSource.receive();
~~~

`receive()` lấy một Spring Messaging message — hoặc `null` nếu không có message sẵn theo hợp đồng của source. **Đây là cách diễn giải API, không phải vòng lặp production nên tự gọi trong một business service.** Thông thường, polling endpoint sẽ gọi nó theo lịch đã cấu hình.

### 2.3. Inbound channel adapter: điểm khởi phát flow

Polling inbound adapter là một **message-producing endpoint**:

~~~text
Scheduler / Poller
       |
       v
MessageSource.receive()
       |
       v
Spring Message<?> 
       |
       v
Output MessageChannel
       |
       v
Handler / Flow
~~~

Endpoint chịu trách nhiệm nhận message từ source và phát vào channel. Nó không tự hiểu thư đã được nghiệp vụ xử lý xong hay đã lưu vào database.

### 2.4. Bảng phân biệt

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Receiver | *Đọc mailbox bằng giao thức nào và theo chính sách nào?* | `ImapMailReceiver` |
| Message source | *Lấy message tiếp theo bằng cách nào?* | `MailReceivingMessageSource` |
| Poller | *Bao lâu gọi source, mỗi lần lấy bao nhiêu?* | `Pollers.fixedDelay(...)` |
| Inbound endpoint | *Nối source vào channel như thế nào?* | `SourcePollingChannelAdapter` |
| Channel | *Message đi tới handler nào?* | `DirectChannel`, `QueueChannel` |
| Handler | *Thực hiện thao tác gì với email?* | MIME parser, durable ingest, ticket service |
| Error channel | *Đưa một số lỗi trong flow đến đâu?* | Error flow do ứng dụng cấu hình |

Không nên thay thế các khái niệm bằng một lớp `MailService` vừa connect IMAP vừa parse PDF, tạo ticket, commit DB và gửi auto-reply. Thiết kế phân lớp giúp dễ kiểm thử, mở rộng và xử lý lỗi riêng.

## 3. Polling inbound adapter khác IMAP IDLE adapter

Spring Integration Mail có hai kiểu kích hoạt thường gặp.

### 3.1. Polling

Poller hỏi mailbox theo lịch:

~~~text
00:00 -> poll IMAP -> 0 mail
00:15 -> poll IMAP -> 2 mails
00:30 -> poll IMAP -> 1 mail
00:45 -> poll IMAP -> 0 mail
~~~

Ưu điểm:

- Dễ hiểu, dễ đặt nhịp và giới hạn tải.
- Không cần duy trì một IMAP IDLE session kéo dài.
- Phù hợp xử lý theo lô hoặc mailbox có lưu lượng vừa phải.
- Có thể tích hợp checkpoint và quét đối soát định kỳ.

Hạn chế:

- Độ trễ nhận phụ thuộc poll interval.
- Poll quá nhanh có thể chạm quota kết nối/tìm kiếm của provider.
- Cần quản lý job trùng và trạng thái hộp thư.

### 3.2. IMAP IDLE

`ImapIdleChannelAdapter` tận dụng giao thức IMAP IDLE để nhận thông báo khi folder thay đổi:

~~~text
IMAP server -- notification --> IMAP IDLE adapter
                                      |
                                      v
                                MessageChannel
                                      |
                                      v
                                 Mail handler
~~~

Ưu điểm:

- Thường giảm độ trễ khi có email mới.
- Không cần cứ vài giây thực hiện một lần polling cố định để kiểm tra.

Hạn chế:

- Phụ thuộc server hỗ trợ IDLE và chính sách timeout.
- Phải xử lý reconnect, session bị cắt, thông báo đến trễ.
- Không phải cam kết “không mất thông báo” hoặc “chính xác một lần”.

### 3.3. So sánh

| Tiêu chí | Polling source + adapter | IMAP IDLE adapter |
| --- | --- | --- |
| Cơ chế | Poller gọi `receive()` | Adapter phản ứng qua IDLE connection |
| Giao thức phổ biến | IMAP hoặc POP3 | IMAP |
| Độ trễ | Theo poll interval | Thường gần thời gian thực |
| Quản lý kết nối | Theo cơ chế receiver/poller | Có kết nối IDLE dài |
| Rate limiting | Điều chỉnh nhịp poll và throughput | Điều chỉnh luồng xử lý/connection |
| Reconnect | Cần khi lỗi | Đặc biệt quan trọng |
| Khả năng bỏ sót/trùng | Vẫn có nếu thiếu checkpoint/dedupe | Vẫn có nếu thiếu reconciliation/dedupe |
| Phù hợp | Batch, import, polling có kiểm soát | Hộp thư cần phản ứng nhanh |

**Đừng chạy cả polling và IDLE trên cùng một receiver/folder chỉ vì muốn “nhanh và an toàn hơn”.** Hai consumer có thể tranh chấp cờ, folder và trạng thái. Nếu cần reconcile định kỳ khi dùng IDLE, hãy thiết kế quy trình riêng có khóa/cursor và idempotency.

## 4. IMAP và POP3 làm message source

### 4.1. IMAP

IMAP cho phép làm việc với folder, flags và UID trong một mailbox:

~~~text
Mail account: support@example.com
Folder: INBOX
Protocol: imaps
Port: thường 993
~~~

Nó phù hợp khi cần:

- đọc mailbox mà không xóa thư ngay;
- tìm thư mới/chưa được nhận;
- phân loại theo folder hoặc trạng thái;
- truy vết UID/UIDVALIDITY trong một folder;
- xử lý lỗi bằng cách quét lại các message đã nhận.

### 4.2. POP3

POP3 đơn giản hơn, thường dùng để tải message. Khả năng folder và flags hạn chế hơn IMAP.

~~~text
Mail account: import@example.com
Protocol: pop3s
Port: thường 995
~~~

POP3 phù hợp với vài quy trình mailbox đơn giản, nhưng khó quản lý trạng thái nhiều worker hoặc tác vụ reconciliation dựa trên folder flags. POP3 có khái niệm UIDL khi server hỗ trợ; không dùng sequence number làm ID bền vững.

### 4.3. URL mailbox chỉ là một phần cấu hình

Các URL minh họa:

~~~text
imaps://reader:<secret>@mail.example.test:993/INBOX
pop3s://reader:<secret>@mail.example.test:995/INBOX
~~~

**Không sao chép nguyên các URL này vào production.** Domain `example.test` là ví dụ; `<secret>` là placeholder. Cần dùng URL format đúng phiên bản Spring Integration, xử lý ký tự đặc biệt theo cú pháp URL và không để secret lộ trong source, log hoặc exception.

Nếu provider hỗ trợ OAuth2/XOAUTH2 hoặc bắt buộc dùng token, cần cấu hình authenticator/token provider tương thích; không giả định mọi mailbox vẫn hỗ trợ password thường.

## 5. Dependency cho Spring Boot

Một ứng dụng Spring Boot sử dụng Spring Integration Mail có thể cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

Maven:

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

Không có lý do bắt buộc dùng `JavaMailSender` nếu ứng dụng *chỉ nhận* thư. Nếu ứng dụng cũng gửi email, có thể bổ sung `spring-boot-starter-mail` và cấu hình SMTP phù hợp.

Khi dùng Spring Boot dependency management, các phiên bản Spring Integration, Spring Framework và Jakarta Mail cần tương thích. Dự án đời mới dùng namespace `jakarta.mail.*`; các dự án Spring 5/JavaMail đời cũ có thể dùng `javax.mail.*`. Không trộn namespace tùy ý.

## 6. Ví dụ: tạo IMAP message source và polling inbound flow

Xây dựng một flow nhỏ:

~~~text
ImapMailReceiver
  -> MailReceivingMessageSource
  -> Poller, tối đa 5 messages/poll
  -> InboundMailHandler
~~~

### 6.1. Cấu hình ứng dụng

~~~yaml
app:
  inbound-mail:
    url: ${INBOUND_MAIL_URL}
    poll-delay-ms: 15000
~~~

`app.inbound-mail.*` là namespace **do ứng dụng định nghĩa**, không phải thuộc tính Spring Boot tự nhận và cấu hình IMAP inbound tự động.

### 6.2. Tạo receiver, message source và IntegrationFlow

Ví dụ Spring Integration Java DSL trên hệ Jakarta Mail:

~~~java
package com.example.mail.inbound;

import java.time.Duration;
import java.util.Properties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
@EnableIntegration
public class InboundMailConfiguration {

    @Bean
    ImapMailReceiver supportMailReceiver(
            @Value("${app.inbound-mail.url}") String mailboxUrl) {

        ImapMailReceiver receiver =
                new ImapMailReceiver(mailboxUrl);

        Properties properties = new Properties();
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "15000");
        properties.put("mail.imaps.ssl.checkserveridentity", "true");
        receiver.setJavaMailProperties(properties);

        // Minh họa chính sách mailbox; chưa phải ACK nghiệp vụ.
        receiver.setShouldMarkMessagesAsRead(false);
        receiver.setShouldDeleteMessages(false);
        return receiver;
    }

    @Bean
    MailReceivingMessageSource supportMailSource(
            ImapMailReceiver supportMailReceiver) {
        return new MailReceivingMessageSource(supportMailReceiver);
    }

    @Bean
    IntegrationFlow supportMailFlow(
            MailReceivingMessageSource supportMailSource,
            InboundMailHandler inboundMailHandler,
            @Value("${app.inbound-mail.poll-delay-ms:15000}")
                    long pollDelayMs) {

        return IntegrationFlow
                .from(
                        supportMailSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                        Duration.ofMillis(pollDelayMs))
                                        .maxMessagesPerPoll(5)))
                .handle(message ->
                        inboundMailHandler.accept(
                                message.getPayload()))
                .get();
    }
}
~~~

Ở đây, **message source** là một bean riêng, còn DSL `IntegrationFlow.from(source, endpoint -> endpoint.poller(...))` tạo polling endpoint nối source vào flow.

Không cần tự viết `while(true)` hay `Thread.sleep(...)` để gọi `receive()`.

### 6.3. Handler nhận email

~~~java
package com.example.mail.inbound;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.stereotype.Component;

@Component
public class InboundMailHandler {

    private final InboundMailStore store;

    public InboundMailHandler(InboundMailStore store) {
        this.store = store;
    }

    public void accept(Object payload) {
        if (!(payload instanceof MimeMessage mail)) {
            throw new IllegalArgumentException(
                    "Expected a MimeMessage payload");
        }

        try {
            String subject = mail.getSubject();
            String messageId = mail.getMessageID();

            // Minh họa: lưu metadata/nội dung an toàn và idempotent.
            // Không coi Message-ID là khóa duy nhất đáng tin.
            store.ingest(mail, subject, messageId);
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot read inbound mail metadata", ex);
        }
    }
}
~~~

`InboundMailStore` là **interface/service do ứng dụng tự định nghĩa**, không phải class có sẵn trong Spring. Một implementation production sẽ cần:

1. Lấy định danh nguồn ở cấp mailbox/folder/UID.
2. Đọc MIME trong giới hạn kích thước.
3. Lưu metadata và attachment cần thiết vào storage.
4. Ghi inbound record bền vững và deduplicate.
5. Chỉ sau khi commit mới thay đổi trạng thái mailbox theo chính sách.

**Ví dụ flow này chưa giải quyết toàn bộ việc lưu bền vững hoặc ack.** Đặc biệt, nếu `setShouldMarkMessagesAsRead(false)`, ứng dụng cần chiến lược lọc/chuyển trạng thái để không đọc lại vô hạn cùng thư; nếu bật đánh dấu đã đọc quá sớm thì lại có rủi ro bỏ sót khi handler lỗi.

### 6.4. Chọn payload type đúng phiên bản

Trong cấu hình nhận thông thường, payload có thể là `jakarta.mail.internet.MimeMessage`. Nhưng Spring Integration Mail có các tùy chọn liên quan nội dung đơn giản và chuyển đổi nội dung; flow còn có thể có transformer trước handler.

Vì thế, business handler không nên giả định mọi flow luôn nhận `String` hoặc luôn nhận `MimeMessage`. Xác định **contract payload** ngay sau inbound adapter và kiểm tra trong integration test.

## 7. InboundChannelAdapter annotation và Java DSL

Spring Integration hỗ trợ nhiều cách cấu hình endpoint:

- **Java DSL** như `IntegrationFlow.from(source, spec -> spec.poller(...))`.
- Các annotation Spring Integration như `@InboundChannelAdapter` kết hợp `@Poller`.
- XML namespace configuration ở các dự án cũ.

Một ví dụ annotation, thay thế cho flow polling DSL ở mục trên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Bean
@InboundChannelAdapter(
        channel = "inboundRawMailChannel",
        poller = @Poller(fixedDelay = "15000"))
public MessageSource<?> inboundMailSource(
        ImapMailReceiver receiver) {
    return new MailReceivingMessageSource(receiver);
}
~~~

Trong cách tổ chức này, cần khai báo channel và handler phù hợp, ví dụ `@ServiceActivator(inputChannel = "inboundRawMailChannel")`.

**Chọn một cách tạo endpoint.** Nếu cùng một source được dùng đồng thời bởi annotation endpoint và DSL endpoint, hai poller có thể cạnh tranh nhận thư hoặc đụng trạng thái receiver.

### 7.1. Không nhầm adapter với transformer

Adapter đưa dữ liệu từ **bên ngoài** vào Spring message flow. Transformer thay đổi **biểu diễn message bên trong**:

~~~text
MailReceivingMessageSource
         |
         v
Inbound Adapter
         |
         v
Spring Message<MimeMessage>
         |
         v
MIME Transformer / Normalizer
         |
         v
Spring Message<InboundMailCommand>
         |
         v
Business Handler
~~~

Đây là một ranh giới tốt để chuyển dữ liệu từ Jakarta Mail object sang DTO đã được validate và lưu bền vững.

## 8. Channel và cách lựa chọn đồng bộ/bất đồng bộ

Sau inbound adapter, Spring Integration dùng `MessageChannel` để đưa message đến handler. Channel ảnh hưởng trực tiếp đến semantics xử lý.

### 8.1. DirectChannel: xử lý đồng bộ

~~~text
Poller thread
  -> receive MimeMessage
  -> DirectChannel
  -> Handler đọc MIME/lưu inbound record
  -> Handler trả về
  -> Poller tiếp tục
~~~

Ưu điểm:

- Handler chạy cùng luồng dispatch thông thường.
- Dễ xác định điểm kết thúc của lời gọi handler.
- Giảm nguy cơ truyền raw MIME qua ranh giới thread khi folder sắp đóng.

Nhược điểm:

- Handler chậm có thể khiến poller chậm.
- Nếu parser/attachment tốn thời gian, giảm throughput ingest.

**Mẫu hay dùng:** xử lý **ingest ngắn và bền vững** trên đường đồng bộ, sau đó worker riêng xử lý business task từ DB/queue.

### 8.2. ExecutorChannel / async handoff

Khi channel chuyển message sang thread khác:

~~~text
Poller receives MimeMessage
    -> executor queue
       -> worker đọc MIME trễ hơn
~~~

Có hai rủi ro:

1. Mail receiver có thể đã đóng IMAP folder trước khi worker gọi `getContent()` hoặc `getInputStream()`.
2. Một queue chỉ nằm trong memory không phải durable store. Crash có thể làm mất message đã lấy khỏi mailbox nhưng chưa được ghi bền vững.

Vì vậy, trước async boundary nên **vật hóa dữ liệu cần thiết và ghi inbound record**. Nếu cần xử lý lâu, gửi một `inboundId` hoặc `storageRef` đến worker thay vì đưa nguyên `MimeMessage` đang phụ thuộc kết nối IMAP.

### 8.3. QueueChannel có phải là durable queue?

Một `QueueChannel` dùng memory không tự biến thành hàng đợi bền vững chỉ vì có tên “queue”. Spring Integration có nhiều message store/queue adapter, nhưng mỗi lựa chọn có contract khác nhau.

Hãy phân biệt:

- memory queue;
- persistent message store/DB;
- external broker (RabbitMQ/Kafka/...);
- outbox hoặc inbox table do ứng dụng quản lý.

Chỉ tuyên bố “đã lưu thư” khi durable storage transaction thực sự thành công.

### 8.4. Cách tổ chức ít rủi ro

~~~mermaid
flowchart TD
    A["IMAP Receiver"] --> B["Polling Inbound Adapter"]
    B --> C["DirectChannel"]
    C --> D["Bounded MIME parsing"]
    D --> E["Durable inbound store"]
    E --> F["Inbound job queue"]
    F --> G["Business workers"]
    G --> H["Ticket / Invoice / Workflow"]
~~~

Nếu việc ingest có thể fail, đừng đánh dấu thư là đã xử lý hoàn toàn trước khi lưu thành công; retry và reconciliation phải xử lý khoảng trống giữa mailbox state và DB state.

## 9. Poller: nhịp, kích thước lô và giới hạn tài nguyên

Polling endpoint có thể được điều chỉnh:

~~~java
return IntegrationFlow
        .from(source, spec -> spec.poller(
                Pollers.fixedDelay(Duration.ofSeconds(20))
                        .maxMessagesPerPoll(10)))
        .handle(message -> inboundHandler.accept(
                message.getPayload()))
        .get();
~~~

### 9.1. Fixed delay và fixed rate

| Lịch | Ý nghĩa tổng quát | Khi dùng |
| --- | --- | --- |
| Fixed delay | Đợi một khoảng sau lần poll trước hoàn tất | Muốn tránh nhịp poll chồng chéo |
| Fixed rate | Cố gắng poll theo nhịp thời gian | Cần lịch đều, phải đánh giá thời gian xử lý |
| Cron | Poll theo lịch xác định | Nhận batch theo giờ hoặc thời điểm |

Không nên cấu hình polling quá dày khi mailbox provider giới hạn connection hoặc search request. Một poll mỗi vài giây không nhất thiết làm ứng dụng xử lý được nhiều mail hơn nếu parser/storage đang chậm.

### 9.2. maxMessagesPerPoll không phải giới hạn MIME size

`maxMessagesPerPoll(10)` hạn chế số lượt nhận message trong một poll cycle theo semantics endpoint. Nó **không** giới hạn:

- dung lượng một message;
- số MIME parts;
- tổng bytes của attachment;
- thời gian xử lý;
- tổng email tồn tại trong mailbox.

Cần áp size/timeout/part-count limits ở parser và hạ tầng riêng.

### 9.3. Cạnh tranh với scheduler

Khi dùng nhiều pollers, thread pools, hoặc nhiều application replicas:

- giới hạn concurrency theo mailbox/provider;
- tránh hai consumer tự ý thay đổi cùng flags;
- dùng lease/leader hoặc phân vùng mailbox nếu cần;
- lưu idempotency key bền vững;
- không giả định Spring scheduler trong từng JVM là distributed lock.

### 9.4. Backpressure

Nếu mỗi phút nhận 2.000 thư nhưng worker chỉ xử lý 300:

~~~text
Incoming rate: 2000/min
Processing rate: 300/min
Backlog growth: 1700/min
~~~

Giải pháp có thể gồm:

- giới hạn số message lấy mỗi poll;
- tạm dừng adapter khi storage vượt ngưỡng;
- scale worker xử lý job đã được lưu;
- tối ưu parser và hệ thống lưu tệp;
- đặt quota/rate theo mailbox/tenant;
- cảnh báo backlog age và disk usage.

**Dừng polling để bảo vệ hệ thống** thường tốt hơn lấy mọi attachment vào RAM rồi crash. Nhưng phải đánh giá retention/quota của mailbox: nếu không đọc lâu, mailbox có thể đầy và ngừng nhận thư mới.

## 10. IMAP IDLE adapter và message-driven flow

Khi chọn IMAP IDLE, cấu hình thường dùng `ImapIdleChannelAdapter`. Đây là **inbound channel adapter**, nhưng **không phải polling adapter cần `MailReceivingMessageSource`**.

Ví dụ với component API:

~~~java
package com.example.mail.inbound;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.ImapIdleChannelAdapter;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.messaging.MessageChannel;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
public class IdleMailConfiguration {

    @Bean("inboundIdleChannel")
    MessageChannel inboundIdleChannel() {
        return new DirectChannel();
    }

    @Bean
    ImapIdleChannelAdapter inboundIdleAdapter(
            ImapMailReceiver idleReceiver,
            @Qualifier("inboundIdleChannel")
                    MessageChannel outputChannel) {

        ImapIdleChannelAdapter adapter =
                new ImapIdleChannelAdapter(idleReceiver);
        adapter.setOutputChannel(outputChannel);
        return adapter;
    }
}
~~~

Handler có thể dùng:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class IdleMailHandler {

    private final InboundMailHandler inbound;

    public IdleMailHandler(InboundMailHandler inbound) {
        this.inbound = inbound;
    }

    @ServiceActivator(inputChannel = "inboundIdleChannel")
    public void onMessage(Message<?> message) {
        inbound.accept(message.getPayload());
    }
}
~~~

**Lưu ý:** ví dụ này là cấu hình IDLE riêng; không khởi tạo song song polling source và IDLE adapter cho cùng `ImapMailReceiver`. Cần tạo `idleReceiver` và URL/properties tương ứng, tương tự receiver polling ở phần trước.

### 10.1. Không nhầm IDLE với exactly-once

IDLE có thể ngắt kết nối, server timeout hoặc notification bị bỏ lỡ. Ứng dụng production cần:

- reconnect/backoff;
- kiểm tra connection/last-success timestamps;
- periodic reconciliation (quét lại theo checkpoint);
- idempotency nếu một email xuất hiện hai lần;
- xử lý trường hợp IMAP UIDVALIDITY thay đổi.

Không thiết kế rằng “IDLE event được nhận một lần thì email chỉ được xử lý một lần”.

## 11. Payload, header và sự khác nhau giữa Spring Message và email MIME

Đây là một nguồn nhầm lẫn lớn.

### 11.1. Spring Messaging message

~~~java
org.springframework.messaging.Message<?> integrationMessage;
Object payload = integrationMessage.getPayload();
var headers = integrationMessage.getHeaders();
~~~

Nó gồm:

- `payload`: đối tượng dữ liệu;
- `headers`: metadata của **Spring Integration flow**, không nhất thiết là các Internet mail headers.

### 11.2. Jakarta Mail message

~~~java
jakarta.mail.internet.MimeMessage mimeMessage;
String subject = mimeMessage.getSubject();
var from = mimeMessage.getFrom();
String[] values = mimeMessage.getHeader("Message-ID");
~~~

`MimeMessage` chứa nội dung và headers email chuẩn như From, To, Subject, Message-ID, Content-Type.

Không dùng:

~~~java
integrationMessage.getHeaders().get("Subject");
~~~

rồi mặc định đó là subject thật của email. Spring Integration có thể map một số metadata thành Spring headers, nhưng **contract không đồng nghĩa mọi email header luôn được copy sang Spring MessageHeaders**.

### 11.3. Xác định contract của flow

Một flow rõ ràng nên có hai ranh giới:

~~~text
Adapter output:
  Message<MimeMessage>          (ví dụ)

After normalization:
  Message<InboundMailCommand>
~~~

Trong `InboundMailCommand` có thể chứa:

~~~java
public record InboundMailCommand(
        String mailboxProfile,
        String sourceKey,
        String normalizedFrom,
        String subject,
        String plainBodyStorageRef,
        String htmlBodyStorageRef,
        java.util.List<String> attachmentStorageRefs) {
}
~~~

Đây là DTO ví dụ do ứng dụng định nghĩa, không phải class trong Spring Integration. Không đặt raw MimeMessage object gắn với folder vào queue dài hạn.

## 12. Trạng thái mailbox không phải business acknowledgment

IMAP hỗ trợ flags, thường gặp:

- `\Seen`: đã đọc;
- `\Deleted`: đánh dấu xóa, có thể cần expunge;
- `\Flagged`: đánh dấu;
- cờ tùy biến nếu provider cho phép.

Spring Integration Mail receiver có thể có các thiết lập như:

~~~java
receiver.setShouldMarkMessagesAsRead(false);
receiver.setShouldDeleteMessages(false);
~~~

**Cờ `SEEN` không có nghĩa ticket đã tạo thành công.**

### 12.1. Trường hợp bỏ sót

~~~text
T1 Poller lấy email M1
T2 Receiver đánh dấu SEEN
T3 Handler bắt đầu ghi DB
T4 DB bị lỗi, handler ném exception
T5 Lần poll sau tìm UNSEEN -> M1 không được chọn
~~~

Nếu ứng dụng coi SEEN là acknowledgment nghiệp vụ, M1 có thể bị bỏ sót.

### 12.2. Trường hợp xử lý trùng

~~~text
T1 Receiver đọc M1 nhưng chưa mark SEEN
T2 Handler tạo ticket
T3 Ứng dụng crash trước khi update mailbox
T4 Reconnect và đọc lại M1
T5 Handler tạo ticket thứ hai
~~~

Nếu chỉ dựa vào flags, ứng dụng có thể tạo dữ liệu trùng.

### 12.3. Chiến lược durable inbox

Một cách đáng tin cậy hơn:

~~~text
1. Receiver đọc M1
2. Xác định mailbox + folder + UIDVALIDITY + UID
3. Stream MIME cần thiết vào storage có giới hạn
4. INSERT inbound record với unique key
5. COMMIT database + durable content
6. Cập nhật cờ/checkpoint mailbox
7. Worker xử lý inbound record idempotent
8. Lưu PROCESSED / RETRY_WAIT / QUARANTINED
~~~

Nếu crash sau bước 5 nhưng trước bước 6, bước 4 ở lần quét sau gặp unique conflict và không tạo record nghiệp vụ thứ hai.

**Không có transaction phân tán tự động giữa IMAP server và database chỉ nhờ dùng Spring Integration.** Phải thiết kế at-least-once ingest, deduplication và reconciliation.

## 13. Tìm thư, lọc thư và đánh dấu đã đọc

Một receiver có thể có chiến lược tìm thư dựa trên cờ/điều kiện search. Chính sách mặc định và khả năng customization phụ thuộc protocol, phiên bản Spring Integration và mail server.

Các câu hỏi cần xác định:

1. Receiver chỉ lấy `UNSEEN`, `RECENT`, hoặc điều kiện khác?
2. Thư đã đọc bằng một client khác có cần được xử lý không?
3. Có cần bỏ qua email hệ thống/auto-responder không?
4. Khi lỗi parse, thư có được retry hay quarantine?
5. Khi server đổi UIDVALIDITY, checkpoint được xử lý ra sao?
6. Sau khi xử lý thành công, mail được giữ, đánh dấu hay chuyển folder?

### 13.1. Filter trong Spring Integration và search trên server khác nhau

**Mail search strategy** có thể giúp hạn chế những thư phải tải từ server:

~~~text
IMAP search criteria
  -> chỉ một tập message được fetch
~~~

**Message filter** phía Spring Integration hoạt động sau khi message đã được đưa vào flow:

~~~text
Inbound adapter
  -> filter message
  -> handler
~~~

Filter sau adapter không nhất thiết giảm network traffic. Ngược lại, nếu filter một thư sau khi nó đã được đánh dấu SEEN, thư có thể không xuất hiện lại trong các lần poll sau.

Với email bị loại vì không hợp lệ, cần quy định rõ nó sẽ được lưu audit, chuyển quarantine, giữ lại hay đánh dấu trạng thái nào.

### 13.2. Cờ và điều kiện là trạng thái chia sẻ

Hộp thư có thể được truy cập đồng thời bởi:

- người dùng qua email client;
- bot tự động khác;
- một ứng dụng chạy trên nhiều pod;
- hệ thống mail server có quy tắc tự động.

Một client khác có thể thay đổi flag, làm mất ý nghĩa của chiến lược chỉ đọc unread. Đừng coi inbox flags là nơi duy nhất lưu trạng thái nghiệp vụ của một workflow quan trọng.

## 14. Chống xử lý trùng: IMAP UID, UIDVALIDITY và Message-ID

### 14.1. Message-ID không đủ

Header email:

~~~text
Message-ID: <sample-123@sender.example>
~~~

Rất hữu ích cho correlation, nhưng có thể bị thiếu, trùng, giả mạo hoặc xuất hiện lại trong một message được chuyển tiếp.

Không dùng Message-ID đơn lẻ làm khóa duy nhất toàn hệ thống mà không xác định nguồn và phạm vi.

### 14.2. IMAP UID là định danh theo folder

Để nhận dạng một message trong IMAP:

~~~text
mailbox_account
folder_identifier
UIDVALIDITY
UID
~~~

UID thường chỉ duy nhất **trong một folder dưới một UIDVALIDITY cụ thể**. Khi UIDVALIDITY đổi, không giả định UID số cũ vẫn biểu diễn cùng message.

### 14.3. Ví dụ Jakarta Mail UIDFolder

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public record SourceIdentity(
        long uidValidity,
        long uid) {
}

public static SourceIdentity readSourceIdentity(
        Message sourceMessage) throws Exception {

    Folder folder = sourceMessage.getFolder();
    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "UID is unavailable for this folder");
    }

    return new SourceIdentity(
            uidFolder.getUIDValidity(),
            uidFolder.getUID(sourceMessage));
}
~~~

**Ví dụ cần chạy khi folder còn mở.** Nếu payload đã tách khỏi folder hoặc folder đóng trước khi handler gọi, việc lấy UID có thể không thực hiện được.

### 14.4. Unique constraint là điểm chặn duplicate

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE inbound_mail (
    inbound_id      UUID PRIMARY KEY,
    mailbox_profile VARCHAR(100) NOT NULL,
    folder_name     VARCHAR(250) NOT NULL,
    uid_validity    BIGINT NOT NULL,
    message_uid     BIGINT NOT NULL,
    rfc_message_id  VARCHAR(1000),
    storage_ref     VARCHAR(500),
    status          VARCHAR(40) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    processed_at    TIMESTAMPTZ,
    UNIQUE (
        mailbox_profile,
        folder_name,
        uid_validity,
        message_uid
    )
);
~~~

Một upsert:

~~~sql
INSERT INTO inbound_mail (
    inbound_id, mailbox_profile, folder_name,
    uid_validity, message_uid, status, created_at
)
VALUES (
    :id, :profile, :folder,
    :uid_validity, :uid, 'INGESTED', CURRENT_TIMESTAMP
)
ON CONFLICT (
    mailbox_profile, folder_name, uid_validity, message_uid
) DO NOTHING;
~~~

Đây là mô hình minh họa cho IMAP, không phải migration production hoàn chỉnh. Một hệ thống thực cần quản lý lưu content atomically hoặc xử lý orphan objects, tenant scope, index, retention, và những message không có UID sẵn trong handler.

### 14.5. Nhiều ứng dụng cùng đọc mailbox

Nếu hai pod cùng đọc M1:

~~~text
Pod A receives M1 -> INSERT -> success
Pod B receives M1 -> INSERT -> unique conflict
~~~

Unique constraint giúp tránh hai inbound records, nhưng không thay thế cơ chế tránh tranh chấp folder/flags. Với một mailbox quan trọng, nên cân nhắc **single active consumer/lease/leader** và dùng dedupe như lớp bảo vệ thứ hai.

## 15. MIME parsing và folder lifecycle

Email thực tế có thể là cấu trúc MIME lồng nhau:

~~~text
MimeMessage
  └── multipart/mixed
        ├── multipart/alternative
        │     ├── text/plain; charset=UTF-8
        │     └── text/html; charset=UTF-8
        ├── application/pdf; attachment
        └── image/png; inline; Content-ID
~~~

Đối tượng `MimeMessage` đọc từ IMAP có thể **lazy-load** một số nội dung. Nếu folder đóng trước khi code gọi `getContent()` hoặc `getInputStream()`, có thể phát sinh `FolderClosedException` hoặc lỗi I/O.

### 15.1. Vật hóa trước khi đổi thread

~~~text
Không nên:
  Receiver -> ExecutorChannel -> Queue<MimeMessage>
  -> receiver đóng folder -> worker đọc attachment

Nên:
  Receiver -> synchronous ingest
  -> parse + stream attachment -> durable storage
  -> inbound record committed
  -> Queue<InboundMailId> -> async business worker
~~~

Spring Integration Mail có các tùy chọn về folder-close behavior tùy version, nhưng chỉ giữ folder mở lâu hơn không giải quyết được durable ingestion và có thể làm cạn connection. Thiết kế nên giới hạn thời gian sống của đối tượng mail phụ thuộc server.

### 15.2. Duyệt MIME theo loại, không theo chỉ số cố định

Ví dụ utility:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static void visit(Part part, int depth)
        throws Exception {
    if (depth > 12) {
        throw new IllegalArgumentException(
                "MIME nesting is too deep");
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        if (multipart.getCount() > 100) {
            throw new IllegalArgumentException(
                    "Too many MIME parts");
        }
        for (int i = 0; i < multipart.getCount(); i++) {
            visit(multipart.getBodyPart(i), depth + 1);
        }
        return;
    }

    if (part.isMimeType("text/plain")) {
        // Đọc và giới hạn kích thước text.
    } else if (part.isMimeType("text/html")) {
        // Sanitize/normalize; không render trực tiếp.
    } else {
        // Attachment/inline/other: kiểm soát size và storage.
    }
}
~~~

Đoạn code này minh họa traversal; **chưa** có giới hạn tổng bytes, xử lý nested `message/rfc822`, header bất thường, malware, ZIP bombs hoặc encrypted content. Trong production, phải có policy chặt chẽ hơn.

### 15.3. Attachment không được tin tưởng

Một message có thể khai báo:

~~~text
Content-Disposition: attachment; filename="../../config.yml"
Content-Type: application/pdf
~~~

Không dùng tên file gốc làm path trực tiếp. Nên:

- phát sinh storage ID/filename do server kiểm soát;
- giữ tên gốc như metadata sau khi sanitize;
- giới hạn số attachment và tổng kích thước;
- stream bytes với quota (không `readAllBytes()` vô hạn);
- validate file signature khi phù hợp;
- quét malware trước khi phát tán;
- chống path traversal, zip bomb và symlink misuse.

Với `Part.getInputStream()`, đóng stream bằng `try-with-resources`. Không lưu file trong thư mục có quyền thực thi tự do.

### 15.4. HTML email không phải HTML đáng tin

Email HTML có thể chứa remote images, tracking links và markup không an toàn. Không đưa HTML từ message vào trang quản trị dưới dạng HTML không sanitize. Cần kiểm tra URL, chặn script/unsafe attributes và xem xét render isolation.

## 16. Spring Integration error handling

Lỗi có thể xảy ra tại các điểm khác nhau:

~~~text
Poller
  |
  +-- IMAP connect/auth error
  +-- mailbox folder/search error
  |
  v
Message source
  |
  +-- MIME read/parse error
  |
  v
Channel / handler
  |
  +-- validation/storage error
  +-- business processing error
~~~

### 16.1. Error channel và exception

Spring Integration có các cơ chế error channel để định tuyến một số lỗi từ endpoint/flow. Nhưng cần hiểu **lỗi được phát đồng bộ hay bất đồng bộ**, có phải `ErrorMessage` không, endpoint nào chịu trách nhiệm, và handler xử lý lỗi ra sao.

Không mặc định:

- mọi exception đều tự retry;
- mail bị lỗi luôn được giữ nguyên và đọc lại;
- nhận được `ErrorMessage` nghĩa là database đã rollback;
- error channel là dead-letter queue bền vững;
- IMAP flags sẽ được khôi phục nếu handler fail.

### 16.2. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Phản ứng phù hợp |
| --- | --- | --- |
| Authentication | Wrong credential, token hết hạn | Alert và refresh/rotate, tránh retry dồn dập |
| TLS | Certificate/hostname mismatch | Sửa trust/endpoint, không tắt bảo vệ |
| Network | Timeout, connection reset | Backoff + jitter + reconnect |
| Folder | Folder đổi tên, thiếu quyền | Điều tra cấu hình/permission |
| Message parse | MIME hỏng, charset lỗi | Quarantine/review, không poison loop |
| Size/security | Tệp quá lớn hoặc nguy hiểm | Reject/quarantine theo policy |
| Database | Không lưu được inbound record | Retry ingest, tránh ack sớm |
| Business | Không tạo ticket/hóa đơn được | Retry job đã lưu hoặc FAILED_FINAL |
| Duplicate | Đã tồn tại unique source identity | No-op hoặc reconcile status |

### 16.3. Poison message

Nếu receiver poll lại cùng một MIME hỏng nhiều lần:

~~~text
M1 -> parse error
M1 -> parse error
M1 -> parse error
...
~~~

Hệ thống có thể kẹt vĩnh viễn. Nên có attempt limit, quarantine record và thao tác mailbox rõ ràng (ví dụ chuyển folder lỗi hoặc giữ cờ/chốt trạng thái theo policy). Tránh **xóa email lỗi** khi chưa lưu đủ thông tin hỗ trợ điều tra hoặc chưa được quy định retention.

## 17. Bảo mật credential và kết nối

Inbound adapter cần quyền truy cập mailbox — một quyền nhạy cảm vì có thể đọc email và attachment.

### 17.1. TLS đúng protocol

Các cổng điển hình:

| Protocol | Cổng thường dùng | TLS |
| --- | --- | --- |
| IMAPS | 993 | Implicit TLS |
| IMAP | 143 | Có thể STARTTLS khi provider hỗ trợ |
| POP3S | 995 | Implicit TLS |
| POP3 | 110 | Có thể STARTTLS khi provider hỗ trợ |

Đặt properties theo đúng prefix:

~~~properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=15000
mail.imaps.ssl.checkserveridentity=true
~~~

Với IMAP STARTTLS, dùng property `mail.imap.*`, bật và yêu cầu STARTTLS phù hợp với provider. Không tự ghép `mail.imaps.*` rồi kỳ vọng nó áp dụng cho `imap`.

### 17.2. OAuth2/XOAUTH2

Một số provider không còn cho phép Basic Authentication với IMAP. Với OAuth2/XOAUTH2, ứng dụng có thể cần:

- token provider dùng đúng OAuth scope/audience cho IMAP;
- permission với mailbox tương ứng;
- refresh/re-acquire token khi hết hạn;
- kết nối lại khi thông tin xác thực thay đổi;
- cơ chế SASL auth hỗ trợ trong Jakarta Mail implementation;
- chính sách rate-limit và account access do provider quy định.

Không đặt access token hết hạn vào một URL IMAP tĩnh và mặc định nó sẽ tự refresh. Cần kiểm tra khả năng authenticator/token callback của phiên bản thư viện và provider đang dùng.

### 17.3. Không log secret

Tránh:

~~~java
logger.info("Mailbox URL: {}", mailboxUrl);
~~~

nếu URL chứa username/password/token. Thay bằng mailbox profile không nhạy cảm như `support_primary`, protocol và host đã lọc. Secret lấy từ secret manager hoặc environment, không commit trong source.

### 17.4. Đừng tắt kiểm tra certificate

TLS fail có thể do host không khớp, proxy, truststore hoặc certificate chain. Cách xử lý đúng là sửa cấu hình và niềm tin certificate, **không bật trust-all** để vượt lỗi trong production.

## 18. Multi-tenant và nhiều mailbox

Một nền tảng có thể nhận email cho:

~~~text
tenant-a -> support-a@example.com
tenant-b -> invoices-b@example.com
tenant-c -> claims-c@example.com
~~~

Thiết kế receiver có thể:

- một inbound flow cho mỗi mailbox khi số lượng nhỏ;
- scheduler điều phối nhiều mailbox với concurrency giới hạn;
- sharding mailbox theo worker;
- provider inbound webhook/API nếu có quy mô lớn;
- một mailbox chung với routing đã xác minh nếu business cho phép.

### 18.1. Ranh giới tenant được xác định từ mailbox

**Không lấy From của email làm tenant ID.** Người gửi có thể giả mạo:

~~~text
From: finance@tenant-a.example
~~~

Tenant identity nên gắn với **mailbox account/receiver profile được cấu hình trước** hoặc một rule routing được xác thực.

### 18.2. Nhiều IDLE connection có chi phí

Với hàng nghìn mailbox, một IDLE connection mỗi tenant có thể quá giới hạn provider hoặc tạo áp lực socket/thread/memory. Polling theo nhóm với concurrency kiểm soát hoặc inbound provider API có thể phù hợp hơn.

### 18.3. Dedupe key có mailbox scope

Ngay cả khi hai mailbox nhận cùng một email có cùng Message-ID, đó có thể là hai mục cần xử lý riêng. Khóa nhận dạng cần bao gồm mailbox/folder như thiết kế.

## 19. Quan sát inbound flow

Những chỉ số có ích:

| Chỉ số đề xuất | Mục đích |
| --- | --- |
| `inbound_mail_poll_total` | Số lần poll |
| `inbound_mail_poll_errors_total` | Lỗi kết nối/fetch |
| `inbound_mail_messages_received_total` | Số message source phát ra |
| `inbound_mail_ingested_total` | Số message đã lưu bền vững |
| `inbound_mail_duplicates_total` | Số lần duplicate bị chặn |
| `inbound_mail_processing_failed_total` | Lỗi nghiệp vụ |
| `inbound_mail_quarantined_total` | Số mail phải quarantine |
| `inbound_mail_ingest_duration_seconds` | Thời gian parse/lưu |
| `inbound_mail_pending_jobs` | Backlog downstream |
| `inbound_mail_oldest_pending_age_seconds` | Tuổi job chưa xử lý |
| `inbound_mail_last_success_timestamp_seconds` | Lần nhận/lưu thành công gần nhất |

Tên trên là **ví dụ instrumentation do ứng dụng định nghĩa**, không mặc định Spring Integration tự xuất tất cả metrics đó.

### 19.1. Đo từng giai đoạn

~~~text
mailbox checked
  -> message fetched
  -> message persisted
  -> business job processed
~~~

“Fetched” và “Ingested” khác nhau. Một email có thể tải thành công nhưng lưu DB thất bại; nếu chỉ đo `received_total`, dashboard có thể báo ứng dụng khỏe dù dữ liệu bị mất.

### 19.2. Metric labels an toàn

Nên dùng tập hữu hạn:

~~~text
mailbox_profile=support_primary
protocol=imaps
stage=receive|ingest|process
result=ok|error|duplicate
error_class=auth|tls|network|mime|storage|unknown
~~~

Tránh làm label từ raw email address, From, Subject, Message-ID, UID, filename, token hoặc mỗi tenant ID động. Chúng gây cardinality lớn và có thể rò rỉ PII.

### 19.3. Alert

- Polling dừng quá lâu.
- IMAP IDLE mất kết nối, không reconnect.
- Authentication/TLS lỗi lặp lại.
- Mailbox quota gần đầy.
- Số message fetched lớn nhưng ingested không tăng.
- Pending inbound jobs vượt ngưỡng.
- Tăng đột biến các thư quarantine hoặc attachment lỗi.

Không coi “không có thư mới trong 30 phút” là lỗi với mailbox ít traffic. Kết hợp last poll success, connection health và kỳ vọng lưu lượng.

## 20. Unit test và integration test

### 20.1. Unit test handler

Đọc email dưới dạng `MimeMessage` có thể test hoàn toàn trong bộ nhớ:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import static org.junit.jupiter.api.Assertions.*;

@Test
void parsesSubject() throws Exception {
    MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties()));
    mime.setFrom("customer@example.net");
    mime.setRecipients(
            jakarta.mail.Message.RecipientType.TO,
            "support@example.test");
    mime.setSubject("Yêu cầu hỗ trợ", "UTF-8");
    mime.setText("Tôi cần trợ giúp.", "UTF-8");
    mime.saveChanges();

    assertEquals("Yêu cầu hỗ trợ", mime.getSubject());
}
~~~

Test này kiểm tra Jakarta Mail object chứ **không** chứng minh receiver đã kết nối IMAP.

### 20.2. Integration test với mailbox server giả

Có thể dùng **GreenMail** hoặc mail test server hỗ trợ IMAP/SMTP:

~~~text
JUnit
  |
  +-- start GreenMail SMTP + IMAP
  |
  +-- gửi fixture email bằng SMTP cục bộ
  |
  +-- Spring Integration poller / IDLE adapter đọc IMAP
  |
  +-- handler lưu inbound record
  |
  +-- assert: subject, source identity, dedupe, status
  |
  +-- cleanup server, inbox, DB, queue, files
~~~

Với polling:

1. Start test server trên port động, tạo mailbox và login.
2. Trỏ IMAP receiver tới đúng host/port test.
3. Gửi một message fixture.
4. Chờ điều kiện inbound record xuất hiện với timeout hữu hạn.
5. Kiểm tra đúng một record và nội dung.
6. Cho receiver đọc lại/cố tình khởi động lại rồi xác nhận không tạo record trùng.
7. Stop inbound endpoint, server và dọn toàn bộ fixture.

### 20.3. Không dùng sleep cứng

Không nên:

~~~java
Thread.sleep(3000);
assertEquals(1, repository.count());
~~~

Nếu dùng Awaitility trong test:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals(
            1,
            repository.countByMailboxProfile(
                    "support_primary")));
~~~

`await()` là API Awaitility nếu test có dependency tương ứng; đây là ví dụ chờ theo điều kiện, không phải yêu cầu thêm thư viện cho mọi dự án.

### 20.4. Các test cases quan trọng

| Scenario | Kết quả cần xác minh |
| --- | --- |
| Inbox trống | Adapter không phát mail giả |
| Có một email | Nhận và tạo inbound record |
| HTML + plain | MIME parse đúng |
| Attachment PDF | Stream và lưu storage an toàn |
| Email Unicode | Subject/body giải mã đúng |
| Email không có Message-ID | Không crash hoặc tạo key sai |
| Đọc lại cùng email | Không tạo job/ticket trùng |
| Crash sau DB commit trước mark SEEN | Reconciliation/dedupe đúng |
| DB lỗi trước durable ingest | Không thừa nhận đã xử lý thành công |
| Folder đóng sớm | Không giữ raw MimeMessage vào worker trễ |
| UIDVALIDITY đổi | Không coi UID cũ là cùng message |
| IDLE disconnect | Reconnect và rescan |
| Hai pods đọc cùng mailbox | Unique constraint/lease bảo vệ |
| OAuth/token hết hạn | Phân loại auth error, refresh hợp lệ |
| Attachment filename nguy hiểm | Không path traversal |
| Message quá lớn | Quarantine/reject theo policy |
| Header From giả mạo | Không tự thực thi thao tác nhạy cảm |

### 20.5. Dọn trạng thái giữa các test

Để test không phụ thuộc thứ tự, cần dọn:

- SMTP/IMAP test server hoặc container;
- mailbox messages/flags;
- inbound DB rows;
- durable queue và delayed jobs;
- worker/executor đang chạy;
- attachment/temp files/streams;
- Spring context gắn dynamic port của test server.

Đừng purge mailbox dùng chung nếu các test chạy song song. Chọn per-test fixture hoặc correlation/namespace theo test.

## 21. Tình huống tổng hợp: support mailbox thành ticket

Một ứng dụng nhận email ở `support@example.com`, dùng IMAP polling:

~~~mermaid
flowchart TD
    A["Email đến support mailbox"] --> B["ImapMailReceiver"]
    B --> C["MailReceivingMessageSource"]
    C --> D["Polling inbound adapter"]
    D --> E["DirectChannel"]
    E --> F["MIME normalizer + limits"]
    F --> G{"Inbound key exists?"}
    G -->|Yes| H["Duplicate: no-op"]
    G -->|No| I["Durable inbound record"]
    I --> J["Business job"]
    J --> K["Ticket created"]
~~~

### 21.1. Thư hợp lệ

~~~text
Mailbox: support_primary
Folder: INBOX
UIDVALIDITY: 1008
UID: 5521
From: customer@example.net
Subject: Không đăng nhập được
Attachment: screenshot.png
~~~

Quy trình:

1. Poller gọi message source.
2. Receiver kết nối IMAP, tìm thư theo search strategy.
3. Adapter phát `Message<MimeMessage>` vào channel.
4. Handler lấy source identity khi folder còn mở.
5. Handler đọc MIME trong giới hạn, lưu attachment với storage key do server tạo.
6. Lưu inbound record với unique key và commit.
7. Sau khi dữ liệu an toàn, cập nhật mailbox flag/checkpoint theo chính sách.
8. Business worker lấy inbound ID và tạo ticket idempotent.

### 21.2. Đọc lại sau crash

Nếu ứng dụng crash sau bước 6 nhưng trước bước 7, thư có thể được receiver phát lại khi reconnect. Thay vì tạo ticket thứ hai, INSERT với unique constraint phát hiện đã ingest, sau đó reconcile trạng thái mailbox.

### 21.3. Thư nguy hiểm

Nếu attachment tự khai filename `../../application.yml` hoặc mail chứa HTML đáng ngờ, parser không dùng filename đó làm path và không render trực tiếp. Khi vượt giới hạn hoặc không thể kiểm chứng, message được đưa vào quarantine theo chính sách.

### 21.4. Mailbox provider gián đoạn

Khi IMAP connection lỗi:

1. Endpoint báo lỗi phù hợp.
2. Có reconnect/backoff chứ không retry liên tục.
3. Sau phục hồi, quét đối soát mailbox/checkpoint.
4. Dedupe tránh tạo ticket trùng.
5. Dashboard hiển thị poll errors, last successful ingest và backlog.

## 22. Những lỗi thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `JavaMailSender` để đọc inbox | Sai vai trò API | Dùng mail receiver trong Spring Integration |
| Chỉ thêm `spring-boot-starter-mail` | Không tự có inbound adapter | Thêm `spring-integration-mail` và cấu hình flow |
| Nhầm receiver với message source | Không hiểu ai poll/ai kết nối | Phân tách giao thức, source, endpoint |
| Để hai poller dùng cùng source | Cạnh tranh message/flags | Một endpoint sở hữu source hoặc thiết kế khóa |
| Chạy polling và IDLE cùng receiver | Cạnh tranh folder | Chọn một cơ chế, reconcile riêng |
| Poll quá nhanh | Tăng tải/quota | Điều chỉnh interval, backpressure |
| Coi `maxMessagesPerPoll` là size limit | OOM khi attachment lớn | Giới hạn bytes/MIME |
| Dùng raw `MimeMessage` trong async queue | FolderClosedException, dữ liệu chưa durable | Vật hóa/lưu rồi gửi inbound ID |
| Coi `\Seen` là business ACK | Có thể bỏ sót email khi DB lỗi | Durable inbox + reconciliation |
| Không dedupe | Tạo ticket trùng sau crash | UID/UIDVALIDITY + unique constraint |
| Chỉ dùng Message-ID làm unique key | Có thể thiếu hoặc trùng | Khóa có mailbox scope |
| Dùng sequence number làm cursor vĩnh viễn | Thay đổi khi xóa mail | Dùng IMAP UID đúng |
| Tự xóa email sau khi fetch | Mất dữ liệu khi handler lỗi | Retention/ack policy rõ |
| Không kiểm tra input MIME | Rủi ro XSS, path traversal, malware | Sanitization, size limits, scanning |
| Tin `From` để phê duyệt nhạy cảm | Dễ bị spoof | Xác minh danh tính ngoài băng khi cần |
| Hard-code credential trong URL/log | Lộ mailbox | Secret manager, log metadata |
| Tắt TLS hostname verification | Rủi ro MITM | Sửa certificate/trust |
| Retry poison message vô hạn | Kẹt flow | Quarantine và attempt limit |
| Không theo dõi fetched-vs-ingested | Khó phát hiện mất dữ liệu | Instrument từng giai đoạn |
| Chỉ test parser, không test IMAP flow | Không phát hiện lỗi connection/flags | Integration test với mail server giả |

## 23. Checklist triển khai

### Kiến trúc

- [ ] Chọn IMAP polling, IMAP IDLE hoặc POP3 theo yêu cầu.
- [ ] Phân biệt receiver, message source, poller, inbound endpoint và handler.
- [ ] Chỉ tạo một endpoint chính sở hữu receiver/mailbox ở một thời điểm, hoặc có concurrency strategy rõ.
- [ ] Payload contract giữa adapter và transformer được xác định.
- [ ] Không chuyển raw MimeMessage gắn folder sang async queue bền vững.

### Kết nối

- [ ] Host, port, folder và URL hợp lệ với provider.
- [ ] TLS/hostname verification đúng protocol.
- [ ] Secret/token được cấp và làm mới an toàn.
- [ ] Timeout và reconnect/backoff được cấu hình.
- [ ] Poll rate và connection quota được theo dõi.

### Dữ liệu và trạng thái

- [ ] Search criteria và chính sách SEEN/DELETED được xác định.
- [ ] Có durable inbound store trước khi coi đã ingest.
- [ ] Dedupe theo account/folder/UIDVALIDITY/UID nếu IMAP.
- [ ] Có reconciliation nếu crash hoặc IDLE disconnect.
- [ ] Không dùng Message-ID làm khóa duy nhất tuyệt đối.
- [ ] Business handler idempotent, có retry/quarantine.

### Bảo mật

- [ ] MIME size/depth/part count được giới hạn.
- [ ] Attachment dùng storage key an toàn, không path từ filename gốc.
- [ ] HTML không render trực tiếp không sanitize.
- [ ] Không tin header From để thực hiện thao tác nhạy cảm.
- [ ] Không đưa email body, secret, token hoặc PII vào metrics/log tùy tiện.
- [ ] Có retention/quarantine và access control.

### Vận hành và kiểm thử

- [ ] Có metrics poll, receive, ingest, duplicate, errors và backlog.
- [ ] Alert khi IMAP auth/TLS lỗi hoặc poll không hoạt động.
- [ ] Test với IMAP/SMTP test server và port/fixture cô lập.
- [ ] Test lặp, crash, UIDVALIDITY, IDLE reconnect và MIME bất thường.
- [ ] Cleanup mailbox, DB, queue, worker và attachment sau test.

## 24. Những điều cần nhớ

- **`ImapMailReceiver`/`Pop3MailReceiver`** phụ trách đọc hộp thư theo giao thức.
- **`MailReceivingMessageSource`** là nguồn message để polling endpoint lấy email.
- **Polling inbound adapter** kết hợp source với `Poller` và phát kết quả tới `MessageChannel`.
- **`ImapIdleChannelAdapter`** sử dụng cơ chế IDLE; không cần một polling message source thông thường để nhận notification.
- Spring `Message<?>` là wrapper; Jakarta `MimeMessage` là nội dung email trong payload khi cấu hình tương ứng.
- **SEEN/DELETED không phải ACK nghiệp vụ.** Để tránh bỏ sót và trùng, cần durable inbox, source identity và reconciliation.
- Đường đồng bộ ngắn để parse/lưu bền vững rồi đưa **inbound ID** sang worker thường an toàn hơn chuyển raw MIME qua async boundary.
- Mail nhận từ Internet là dữ liệu không tin cậy; phải kiểm soát HTML, attachment, kích thước, quyền và nguồn gửi.
- Polling interval, IDLE connection, quota, retries, logs và metrics cần được vận hành có chủ đích.
- Integration test cần kiểm tra mailbox thật trong môi trường test, không chỉ gọi handler với một MimeMessage trong memory.

**Inbound mail adapter và message source là ranh giới giữa hệ thống email bên ngoài với Spring Integration flow.** Hiểu rõ trách nhiệm của receiver, nguồn message, endpoint và channel giúp xây luồng nhận thư dễ kiểm thử, dễ vận hành và có thể phục hồi sau lỗi. Để sử dụng trong production, hãy kết hợp các thành phần này với **durable ingestion, idempotency, bảo mật MIME và chiến lược đồng bộ mailbox** thay vì coi mỗi lần lấy thư là một giao dịch nghiệp vụ đã hoàn tất.

### Tài liệu tham khảo

- **Spring Integration Reference — Mail Support:** inbound mail adapter, IMAP/POP3, IMAP IDLE, receiver/search strategy.
- **Spring Integration Reference — Java DSL và Polling Consumer:** `IntegrationFlow`, `Pollers`, polling endpoints, message channels.
- **Spring Integration API:** `MailReceivingMessageSource`, `ImapMailReceiver`, `Pop3MailReceiver`, `ImapIdleChannelAdapter`.
- **Spring Framework Reference — Messaging:** `Message<?>`, `MessageChannel`, `MessageHandler`.
- **Jakarta Mail API:** `Session`, `Message`, `MimeMessage`, `Folder`, `UIDFolder`, `Multipart` và `Part`.
- **RFC 3501 — Internet Message Access Protocol Version 4rev1:** folder, flags, UID/UIDVALIDITY; đối chiếu cập nhật trong IMAP4rev2.
- **RFC 9051 — Internet Message Access Protocol Version 4rev2:** cập nhật giao thức IMAP.
- **RFC 2177 — IMAP4 IDLE:** cơ chế notification qua kết nối IDLE.
- **RFC 1939 — Post Office Protocol Version 3:** POP3, message retrieval và UIDL.
- **RFC 5322 — Internet Message Format:** From, Subject, Message-ID và các header.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** multipart, charset, transfer encoding và attachment.
- **Tài liệu mailbox provider đang sử dụng:** IMAP/POP3 authorization, OAuth2/XOAUTH2, folder behavior, TLS, quota và connection limits.
