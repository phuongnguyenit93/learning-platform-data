# Error channel và dead letter flow

## 1. Vì sao luồng nhận/gửi email cần một tuyến xử lý lỗi riêng?

Trong **Spring Integration Mail**, một ứng dụng có thể kết nối IMAP/POP3 để nhận thư, chuyển thư qua các channel, phân tích MIME, tạo ticket, nhập chứng từ, cập nhật trạng thái bounce hoặc gửi email qua SMTP. Tất cả các bước đó có thể lỗi ở những thời điểm khác nhau:

- IMAP server không kết nối được hoặc credential hết hạn.
- Email có MIME không hợp lệ, attachment quá lớn hay chứa nội dung bị cấm.
- Một handler lỗi khi ánh xạ dữ liệu thư thành đối tượng nghiệp vụ.
- Database tạm thời không ghi được kết quả.
- Dịch vụ tạo ticket phản hồi timeout dù có thể đã tạo ticket thành công.
- SMTP relay tạm từ chối gửi thư hoặc trả lỗi xác thực.
- Worker bị dừng sau khi đã gây side effect nhưng chưa kịp cập nhật trạng thái.

Nếu chỉ đặt `try/catch` quanh một handler và ghi log, hệ thống có thể **mất dấu vết của email**, xử lý lại mãi một message bị lỗi hoặc tạo tác vụ trùng khi retry.

**Error channel** trong Spring Integration là cơ chế đưa thông tin exception vào một luồng message để xử lý tập trung hoặc theo từng flow. **Dead letter flow** là quy trình kết thúc retry tự động bằng cách lưu một message/công việc lỗi vào nơi bền vững, có metadata để điều tra và redrive khi được phép.

~~~text
Mailbox / inbound gateway / mail task
                 |
                 v
          Integration flow
          parse -> validate
                 |
                 v
          business handler
                 |
         +-------+--------+
         |                |
         v                v
      SUCCESS          EXCEPTION
         |                |
         v                v
  Commit processing   ErrorMessage
  state / outcome          |
                          v
                     Error channel
                          |
                          v
                 Failure classification
                          |
           +--------------+---------------+
           |              |               |
           v              v               v
        RETRY          DEAD LETTER       UNKNOWN
       scheduled       / quarantine     / reconcile
           |              |               |
           v              v               v
      Next attempt     Operator review   Avoid blind retry
~~~

> **Quan trọng:** Spring Integration có cơ chế `errorChannel` và `ErrorMessage`, nhưng **không tự biến mọi lỗi thành bản ghi dead letter bền vững**. Nếu cần không mất thư sau restart, ứng dụng phải cấu hình queue/broker/database có lưu trữ phù hợp và quy trình xử lý trạng thái rõ ràng.

## 2. Error channel là gì?

Spring Integration xây dựng hệ thống theo mô hình **message → channel → endpoint/handler**. Khi một lỗi được chuyển thành thông điệp, payload thường là một `Throwable` (nhiều trường hợp là `MessagingException`), được bao trong một `ErrorMessage` thuộc Spring Messaging.

Một message thông thường:

~~~text
Message<?>:
  payload: MimeMessage / application command
  headers:
    id
    timestamp
    correlationId (if supplied)
    ...
~~~

Khi lỗi được publish:

~~~text
ErrorMessage:
  payload: Throwable
    possibly MessagingException
       cause: original failure
       failedMessage: Message<?> (if available)
  headers: error context
  originalMessage: optional
~~~

### 2.1. Những class cần biết

| Thành phần | Vai trò |
| --- | --- |
| `org.springframework.messaging.Message<?>` | Message ứng dụng truyền giữa các component |
| `org.springframework.messaging.support.ErrorMessage` | Message chứa exception dưới dạng payload |
| `org.springframework.messaging.MessagingException` | Exception có thể gắn `failedMessage`, dùng để liên kết lỗi với message |
| `org.springframework.messaging.MessageChannel` | Interface channel để gửi message |
| `org.springframework.integration.channel.DirectChannel` | Channel xử lý đồng bộ trong thread của sender |
| `org.springframework.integration.channel.ExecutorChannel` | Dispatch bất đồng bộ qua executor |
| `org.springframework.integration.channel.QueueChannel` | Pollable channel (mặc định là hàng đợi trong bộ nhớ nếu không có message store bền vững) |
| `org.springframework.integration.channel.PublishSubscribeChannel` | Phân phối cho nhiều subscriber |
| `org.springframework.integration.core.MessagingTemplate` | Gửi/nhận message và định tuyến lỗi theo ngữ cảnh |

Tên `errorChannel` là **tên channel tiêu chuẩn** được Spring Integration sử dụng trong các trường hợp thích hợp. Ứng dụng có thể tạo channel riêng, chẳng hạn `mailErrorChannel`, để tách lỗi của mail khỏi những integration flow khác.

### 2.2. ErrorMessage không phải bản sao của email gốc

Giả sử:

~~~java
throw new IllegalArgumentException(
        "Missing required order reference");
~~~

Error flow có thể nhận `ErrorMessage` chứa exception đã được bọc trong `MessagingException`. Dữ liệu của email gốc có thể nằm ở:

- `MessagingException.getFailedMessage()` nếu exception được gắn failed message.
- `ErrorMessage.getOriginalMessage()` nếu nguồn phát lỗi đã cung cấp.
- Header correlation/internal delivery ID đã truyền trước đó.
- Bản ghi inbox/outbox/database được liên kết với attempt.

**Không mặc định rằng mọi ErrorMessage đều có failedMessage hoặc originalMessage.** Lỗi kết nối IMAP trước khi fetch được thư là ví dụ: chưa có message ứng dụng nào để đính kèm.

### 2.3. Error channel khác business dead-letter store

~~~text
Error channel:
  “Có exception cần xử lý ngay trong integration runtime.”

Dead-letter store:
  “Một công việc chưa xử lý thành công đã được lưu
   vào trạng thái cuối, còn đủ metadata để điều tra.”
~~~

`DirectChannel` và `PublishSubscribeChannel` thông thường **không phải nơi lưu message bền vững**. `QueueChannel` mặc định cũng không tự bảo đảm phục hồi khi JVM restart. Muốn DLQ thực sự bền vững, nên dùng:

- Bảng `FAILED`/`DEAD_LETTER` trong database có transaction và audit.
- Broker queue với durability/publisher confirms/consumer ack được cấu hình đúng.
- Kafka dead-letter topic với retention, ACL và consumer policy tương ứng.
- Message store bền vững cho pollable channel nếu architecture sử dụng nó.

Những lựa chọn này có ngữ nghĩa khác nhau. Không gọi một `DirectChannel` tên `deadLetterChannel` là “dead letter đã được lưu an toàn” khi nó chỉ chuyển exception cho một handler đang chạy trong JVM.

## 3. Lỗi đồng bộ và lỗi bất đồng bộ đi đâu?

Hiểu ranh giới thread là điều quan trọng nhất khi thiết kế `errorChannel`.

### 3.1. Luồng đồng bộ với DirectChannel

~~~text
Caller
  |
  v
DirectChannel
  |
  v
Handler
  |
  +-- throws exception
  |
  v
Caller receives exception
~~~

Một handler trên `DirectChannel` thường chạy trong cùng thread gọi `send`. Khi nó ném exception, exception có thể lan về caller theo call stack. **Không phải mọi lỗi đồng bộ đều tự động được chuyển thành ErrorMessage trên global errorChannel**.

Nếu caller muốn xử lý tập trung, nó có thể catch và publish một ErrorMessage (hoặc sử dụng một thành phần Integration có error handling), nhưng phải giữ ranh giới retry/transaction rõ ràng.

### 3.2. Luồng bất đồng bộ với ExecutorChannel

~~~text
Caller --send--> ExecutorChannel
                      |
                      v
                 Worker thread
                      |
                      v
                    Handler
                      |
                      v
                   Exception
                      |
                      v
                ErrorMessage path
~~~

Khi endpoint chạy ở thread khác, exception **không thể ném trở lại caller cũ như một lời gọi đồng bộ**. Spring Integration có thể publish lỗi tới error channel khi messaging context và error handler được thiết lập.

Nơi nhận lỗi có thể đến từ header `errorChannel` trong message, từ cấu hình endpoint/poller hoặc channel mặc định theo khả năng của thành phần. **Không nên giả định một thiết kế dùng ExecutorChannel luôn có cùng hành vi với poller hoặc gateway**, bởi producer, handler và error infrastructure có hợp đồng riêng.

### 3.3. Poller là một ranh giới xử lý lỗi quan trọng

Một inbound mail adapter dùng polling thường thực hiện:

~~~text
Scheduler
   |
   v
Poller task
   |
   v
Read IMAP/POP3 message
   |
   v
Send to downstream flow
   |
   +--> exception
             |
             v
        Poller error handler
             |
             v
       Configured error channel
~~~

Đây là trường hợp thuận tiện để **chỉ định error channel riêng trên poller**. Nếu lỗi được xử lý và chỉ log, scheduler có thể tiếp tục poll ở chu kỳ sau. Nếu lỗi cứ tái diễn trên cùng một email, phải có trạng thái retry/quarantine/dead letter để tránh một vòng lặp lỗi vô hạn.

### 3.4. Bảng so sánh

| Nguồn lỗi | Lỗi có thể ném tới caller? | Khi nào error channel nhận? |
| --- | --- | --- |
| Handler qua `DirectChannel` | Thường có | Nếu caller/endpoint chủ động route hoặc error handling tương ứng |
| Handler qua `ExecutorChannel` | Không theo call stack caller ban đầu | Khi async error handler publish `ErrorMessage` |
| Mail polling inbound adapter | Không có HTTP caller chờ kết quả | Poller error handling có thể publish |
| Gateway đồng bộ có reply/timeout | Thường có thể trả exception cho caller | Theo reply/error channel/gateway configuration |
| Scheduled service gọi `JavaMailSender.send` trực tiếp | Có trong chính thread service | **Không tự vào Spring Integration errorChannel** chỉ vì app dùng Spring Integration |
| HTTP webhook controller | Exception có thể thành HTTP response | Chỉ vào error flow khi controller/service gửi message hoặc route lỗi có chủ đích |

Điều quyết định không chỉ là tên framework mà là **ranh giới nơi exception được bắt, chuyển thành message và gửi vào channel**.

## 4. Error channel toàn cục và error channel riêng cho mail

Trong Spring Integration, `errorChannel` là channel mặc định được runtime dùng trong các tình huống error publication. Với một ứng dụng có mail, file polling, Kafka, HTTP và các luồng khác, nên cân nhắc channel riêng cho từng domain để có retry policy và người vận hành đúng.

Ví dụ:

~~~text
Global errorChannel
   |
   +--> generic logging/alerting

mailErrorChannel
   |
   +--> mail-specific classifier
   +--> retry/dead-letter state transitions

fileErrorChannel
   |
   +--> file import recovery flow
~~~

### 4.1. Vì sao không đưa mọi thứ vào global errorChannel?

Một lỗi IMAP `FolderClosedException`, một lỗi CSV parser và một lỗi SMTP `MailAuthenticationException` có hành động khắc phục khác nhau. Nếu tất cả chảy vào một handler xử lý generic:

- Không có đủ source identity để biết message nào cần retry.
- Có thể retry lỗi permanent.
- Dead letter không phân biệt inbox và outbound delivery.
- Một lỗi parser hàng loạt có thể tràn log/alert.
- Admin khó tra cứu owner/tenant/region của công việc lỗi.

Global error channel có ích cho **fallback visibility**, nhưng không nên thay thế error policy của từng integration flow.

### 4.2. Tách lỗi theo ranh giới nghiệp vụ

Một ứng dụng có hai mail flow:

~~~text
Inbound:
  IMAP -> parse -> create support ticket
                 |
                 +--> inboundMailErrorChannel

Outbound:
  Outbox -> render -> SMTP send
                    |
                    +--> outboundMailErrorChannel
~~~

Ở chiều **inbound**, retry nghĩa là đọc/lấy lại và xử lý một email đã tiếp nhận. Ở chiều **outbound**, retry có thể gửi cùng email qua SMTP lần nữa và **có rủi ro duplicate khi outcome mơ hồ**. Dùng chung một lỗi `RETRY` không nói rõ loại side effect đang diễn ra.

## 5. Ví dụ cấu hình mailErrorChannel trong Spring Integration

Một kiến trúc đơn giản gồm ba thành phần:

1. Inbound message source đọc email từ IMAP.
2. `IntegrationFlow` điều phối email đến service xử lý.
3. `mailErrorChannel` nhận `ErrorMessage` do poller/endpoint publish.

Các đoạn code dưới đây dùng phong cách Spring Boot 3.x, Java 17+ và Spring Integration 6.x **để minh họa cấu trúc**, không phải một project có thể chạy ngay khi chỉ copy một class. Phiên bản dependency và overload API cần thống nhất với Spring Boot/Spring Integration đang dùng.

### 5.1. Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

`spring-integration-mail` cung cấp các mail adapter/receiver; `spring-boot-starter-jdbc` chỉ cần khi ví dụ dùng database để lưu state/DLQ. Nếu ứng dụng đã dùng Spring Data JPA thì không nhất thiết phải thêm starter JDBC riêng. Phiên bản dependency nên để Spring Boot BOM quản lý khi hỗ trợ.

### 5.2. Định nghĩa channel và error flow

~~~java
package com.example.mail.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
public class MailErrorIntegrationConfiguration {

    @Bean("mailErrorChannel")
    public MessageChannel mailErrorChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mailErrorFlow(
            MailFailureRouter failureRouter) {

        return IntegrationFlow.from("mailErrorChannel")
                .handle(message -> {
                    if (message instanceof ErrorMessage error) {
                        failureRouter.accept(error);
                    } else {
                        failureRouter.recordUnexpectedPayload(
                                message.getClass().getName());
                    }
                })
                .get();
    }
}
~~~

`MailFailureRouter` là **service do ứng dụng tự xây**, không phải Spring Integration class. Trong production nên validate types và ghi thông tin tối thiểu khi nhận message không mong đợi, không throw exception vô hạn ngay trong error handler.

Ở ví dụ, `DirectChannel` có **một subscriber nhận lỗi đồng bộ**, nên không lưu lỗi qua restart. Nhiệm vụ của `failureRouter.accept(...)` là phân loại và lưu trạng thái lỗi bền vững hoặc điều phối sang nơi lưu phù hợp. Nếu một error flow cũng throw, exception có thể lan trở lại poller/producer hoặc gây một chuỗi lỗi phụ; cần kế hoạch xử lý sự cố thứ cấp.

### 5.3. Kết nối poller với error channel

Giả sử ứng dụng đã khai báo một `MessageSource<?>` đọc IMAP thông qua mail adapter:

~~~java
package com.example.mail.integration;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
public class InboundMailFlowConfiguration {

    @Bean
    public IntegrationFlow inboundMailFlow(
            MessageSource<?> imapMailSource,
            InboundMailHandler handler) {

        return IntegrationFlow.from(
                        imapMailSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                                Duration.ofSeconds(10))
                                        .maxMessagesPerPoll(10)
                                        .errorChannel("mailErrorChannel")))
                .handle(message -> handler.accept(message))
                .get();
    }
}
~~~

`InboundMailHandler` là handler nghiệp vụ của ứng dụng. `imapMailSource` phải được cấu hình đúng với IMAP server, credential, TLS và chính sách giữ/đọc thư. Poller chỉ là **một** nơi phát sinh lỗi; handler có thể cần kênh lỗi riêng hoặc cách chuyển exception theo ngữ nghĩa giao dịch nếu pipeline có các nhánh bất đồng bộ khác.

Đặt `.errorChannel("mailErrorChannel")` trên poller có ý nghĩa: những exception được error handler của poller bắt trong tác vụ polling có thể được gửi tới channel này. **Không suy rằng nó tự động bắt tất cả exception của mọi thread downstream không thuộc poller context.**

### 5.4. Nguồn IMAP bằng MailReceivingMessageSource

Spring Integration Mail có `ImapMailReceiver` và `MailReceivingMessageSource`. Khung tạo nguồn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Bean("imapMailSource")
MessageSource<?> imapMailSource(
        ImapMailReceiver receiver) {
    return new MailReceivingMessageSource(receiver);
}
~~~

`ImapMailReceiver` được tạo từ cấu hình IMAP đã được kiểm tra, ví dụ cấu hình URL hoặc Jakarta Mail properties/Authenticator theo khả năng của phiên bản thư viện. Các account/secret cần được cấp từ **secret manager/runtime**, không commit trong source code. Cấu hình TLS, timeout, folder và `shouldDeleteMessages/shouldMarkMessagesAsRead` phải phù hợp với chiến lược xử lý lại của ứng dụng.

Điểm đặc biệt với inbound mail: nếu receiver đã đánh dấu thư là SEEN, move hoặc delete khi chưa commit kết quả nghiệp vụ, error flow có thể ghi `RETRY` nhưng **không còn tìm lại được thư gốc**. Hãy lưu identity/snapshot bền vững và tách thao tác IMAP flag/move khỏi commit business state.

### 5.5. Nếu endpoint không dùng poller

Một mail flow có thể dùng event-driven receiving adapter hoặc gateway theo cấu hình khác. Trong những trường hợp đó, thuộc tính error handling nằm ở endpoint/message headers/adapter tương ứng, **không có poller để đặt errorChannel**.

Hãy xác định rõ:

- Thread nào gọi business handler?
- Ai bắt exception?
- Lỗi có được chuyển thành `ErrorMessage` không?
- Error channel nào được chọn?
- Nếu không có subscriber hoặc handler lỗi, exception đi đâu?
- Khi error handler hoàn thành, source có coi message đã được nhận thành công không?

Phải trả lời được sáu câu hỏi này trong thiết kế, không chỉ thêm một bean `mailErrorChannel` và coi như toàn hệ thống được bảo vệ.

## 6. Đọc ErrorMessage một cách an toàn

Một error handler có thể nhận nhiều loại exception. Vì vậy, bước đầu tiên là chuẩn hóa thông tin mà không phụ thuộc vào một nested exception chain cố định.

### 6.1. Truy cập payload và failedMessage

~~~java
package com.example.mail.integration;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public final class ErrorMessageInspector {

    public static Message<?> failedMessageOf(
            ErrorMessage error) {

        Throwable failure = error.getPayload();
        if (failure instanceof MessagingException messaging) {
            Message<?> failed = messaging.getFailedMessage();
            if (failed != null) {
                return failed;
            }
        }
        return error.getOriginalMessage();
    }

    public static Throwable rootCauseOf(
            ErrorMessage error) {

        Throwable cause = error.getPayload();
        int depth = 0;
        while (cause.getCause() != null
                && cause.getCause() != cause
                && depth++ < 20) {
            cause = cause.getCause();
        }
        return cause;
    }
}
~~~

`getOriginalMessage()` có thể trả về `null`. Đoạn tìm root cause có giới hạn độ sâu nhằm tránh exception chain bất thường; ứng dụng nên **phân loại theo loại lỗi và giai đoạn thực tế**, không chỉ dựa vào chuỗi `getMessage()`.

### 6.2. Không giữ nguyên message payload trong DLQ theo mặc định

Với inbound MIME, `failedMessage.getPayload()` có thể là `MimeMessage` chứa:

- Địa chỉ email và header do người khác gửi.
- HTML body có thông tin nhạy cảm.
- Attachment lớn, malware hoặc dữ liệu bí mật.
- Stream/resource còn phụ thuộc kết nối IMAP đã đóng.

Không nên serialize nguyên `Message<?>`/`Throwable` vào database bằng Java serialization. Thay bằng:

~~~text
internalMessageId
sourceIdentity
attemptNumber
failureStage
safeErrorCode
payloadReference (if durable and authorized)
occurredAt
correlationId
~~~

Nếu chưa có bản sao MIME bền vững, một ErrorMessage trong JVM không thể được coi là **bằng chứng rằng email đã lưu an toàn để replay**.

### 6.3. Khi lỗi xảy ra trước khi có failedMessage

Ví dụ IMAP xác thực thất bại trong lúc `Store.connect`:

~~~text
ErrorMessage.payload:
  AuthenticationFailedException

failedMessage = null
originalMessage = null
~~~

Đây là **source/connection-level failure**, không phải lỗi của một email cụ thể. Hệ thống nên:

- Tăng chỉ số lỗi kết nối của mailbox.
- Log provider/mailbox ID nội bộ và safe error code.
- Cảnh báo owner về credential/provider.
- Retry **kết nối** theo backoff/circuit breaker.
- Không tự tạo một dead-letter record giả cho “email không rõ” khi chưa có thư nào được lấy.

Ngược lại, khi handler lỗi sau khi đã fetch email và có internal message ID, mới có cơ sở chuyển một delivery cụ thể sang `RETRY` hoặc `FAILED`.

## 7. Header errorChannel và correlation context

Spring Messaging cung cấp tên header `errorChannel` (hằng `MessageHeaders.ERROR_CHANNEL`). Các thành phần có hỗ trợ error routing có thể đọc header để xác định nơi gửi lỗi.

Ví dụ tạo message với error channel explicit:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<MailWorkItem> request = MessageBuilder
        .withPayload(workItem)
        .setHeader(
                MessageHeaders.ERROR_CHANNEL,
                mailErrorChannel)
        .setHeader(
                "mailInternalId",
                workItem.inboundId().toString())
        .build();
~~~

Header có thể là một `MessageChannel` hoặc channel name tùy contract của thành phần tham gia. Chỉ đặt header trên message **không bảo đảm mọi plain Java method call bên dưới tự động route exception**; error publication phải được hỗ trợ hoặc được triển khai rõ.

### 7.1. Giữ context qua bất đồng bộ

Khi email đi qua nhiều executor, channel, broker hoặc task scheduler, đừng dựa hoàn toàn vào `ThreadLocal`/MDC từ thread đọc IMAP. Hãy mang theo context tối thiểu bằng:

~~~text
inboundId / outboundDeliveryId
mailboxId / providerId
tenantId (with access controls)
attemptId
correlationId
workflowType
sourceIdentity
~~~

Các trường này cho phép nối ErrorMessage trở lại bản ghi state. Không đưa password, raw MIME body, recipient email hoặc attachment bytes vào header chỉ để có thêm thông tin debug.

### 7.2. Correlation ID không phải idempotency key mặc định

Một trace/correlation ID giúp tìm log, nhưng không nhất thiết ổn định qua mọi retry. Idempotency key phải xác định **cùng một business operation**, ví dụ:

~~~text
inboundId = D1
operation = CREATE_SUPPORT_TICKET
idempotencyKey = "ticket-from-inbound:D1"
~~~

Không tạo một idempotency key mới mỗi attempt nếu mục tiêu là tránh sinh ticket trùng. Cũng không dùng RFC `Message-ID` của sender làm khóa quyền hạn hoặc idempotency duy nhất vì nó có thể bị giả mạo/trùng.

## 8. Phân loại lỗi trước khi quyết định retry hay dead letter

Một `ErrorMessage` chỉ cho biết **có lỗi xảy ra**. Việc thử lại hay đưa vào dead letter phải dựa trên **loại lỗi, giai đoạn và trạng thái side effect**, không chỉ dựa vào class exception bên ngoài.

| Nhóm | Tình huống | Hành động thường phù hợp |
| --- | --- | --- |
| Source infrastructure | IMAP server unavailable, network timeout trước khi nhận thư | Retry kết nối với backoff, cảnh báo mailbox |
| Source authentication | IMAP OAuth token hết hạn hoặc credential sai | Tạm dừng retry dồn dập, xử lý secret/auth |
| Transient processing | DB deadlock, downstream tạm không sẵn | Retry message có kiểm soát |
| Permanent validation | Email thiếu dữ liệu bắt buộc, định dạng nghiệp vụ không hợp lệ | `FAILED`/quarantine, giữ reason |
| Malicious content | Attachment nguy hiểm, MIME abuse, virus | `QUARANTINED` và policy bảo mật |
| Data/snapshot missing | IMAP thư bị xóa/move, UIDVALIDITY đổi | Reconcile hoặc `SOURCE_UNAVAILABLE`; không fetch UID sai |
| Unknown external outcome | Timeout sau khi remote ticket API có thể đã tạo record | `UNKNOWN`/reconcile hoặc retry với idempotency key |
| SMTP temporary failure | Relay tạm unavailable hoặc throttle | Retry outbound với backoff nếu outcome rõ |
| SMTP permanent failure | Recipient bị từ chối chắc chắn, message vượt SIZE | `FAILED`, không retry vô hạn |
| Error flow infrastructure | Không ghi được row retry/DLQ, broker publish thất bại | Cảnh báo lỗi thứ cấp; tránh ack nguồn khi chưa lưu state |

### 8.1. Tách failure kind và failure stage

~~~java
public enum FailureKind {
    TRANSIENT,
    PERMANENT,
    SECURITY,
    UNKNOWN
}

public enum FailureStage {
    IMAP_CONNECT,
    IMAP_FETCH,
    MIME_PARSE,
    ATTACHMENT_SCAN,
    BUSINESS_VALIDATE,
    BUSINESS_DATABASE,
    EXTERNAL_SIDE_EFFECT,
    SMTP_SEND,
    STATE_PERSIST,
    ERROR_FLOW
}

public record FailureDecision(
        FailureKind kind,
        FailureStage stage,
        String safeErrorCode,
        boolean retryAllowed) {
}
~~~

Những enum/record này là **mô hình ứng dụng tự định nghĩa**, không phải built-in của Spring Integration. Trong Java, mỗi top-level `public` type cần đặt vào file riêng phù hợp.

`retryAllowed` không phải boolean do người dùng bên ngoài quyết định. Nó là kết quả của policy sau khi xem error kind, attempt count, deadline, suppression, khả năng đọc lại nguồn và trạng thái của side effect.

### 8.2. Classifier minh họa

~~~java
package com.example.mail.integration;

import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailSendException;

public final class MailFailureClassifier {

    public FailureDecision classify(
            Throwable rootCause,
            FailureStage stage) {

        if (stage == FailureStage.MIME_PARSE
                || stage == FailureStage.BUSINESS_VALIDATE) {
            return new FailureDecision(
                    FailureKind.PERMANENT,
                    stage,
                    "INVALID_INBOUND_CONTENT",
                    false);
        }

        if (rootCause instanceof MailAuthenticationException) {
            return new FailureDecision(
                    FailureKind.PERMANENT,
                    stage,
                    "SMTP_AUTH_CONFIGURATION",
                    false);
        }

        if (rootCause instanceof MailSendException) {
            return new FailureDecision(
                    FailureKind.UNKNOWN,
                    stage,
                    "SMTP_SEND_UNCLASSIFIED",
                    false);
        }

        return new FailureDecision(
                FailureKind.UNKNOWN,
                stage,
                "UNCLASSIFIED",
                false);
    }
}
~~~

Đây chỉ là **default fail-closed classifier**, không phải production retry policy đầy đủ. Trong thực tế, `MailSendException` thường chứa nested exception và chi tiết per-recipient; cần phân tích nguyên nhân SMTP, mã trả về và **đã qua giai đoạn DATA hay chưa**. Không xem mọi `MailSendException` là transient để retry ngay.

Tương tự, một lỗi `MessagingException` có thể gói `IOException`, lỗi conversion, database hoặc exception tự định nghĩa. Tên exception bọc bên ngoài **không đủ** để quyết định hành vi.

### 8.3. Không phải lỗi nào cũng gắn với một message

Mô hình có hai loại sự cố:

~~~text
SOURCE FAILURE
  mailboxId=MB1
  stage=IMAP_CONNECT
  no inboundMessageId
  action=BACKOFF_SOURCE

MESSAGE FAILURE
  inboundMessageId=D1
  stage=MIME_PARSE
  errorCode=INVALID_MULTIPART
  action=QUARANTINE
~~~

Đừng tạo hàng nghìn dead-letter rows từ một lần mailbox credential sai. Một lỗi source-level nên gắn với **mailbox/connect attempt**, còn message-level failure mới liên quan `inboundMessageId` và processing state.

## 9. Dead letter flow: từ ErrorMessage đến bản ghi bền vững

Một dead letter flow cần **một durable record hoặc broker message được xác nhận**, không chỉ gửi exception tới một consumer log.

~~~text
mailErrorChannel
      |
      v
Failure router
      |
      +-- No source message ID?
      |      |
      |      v
      |  Source incident / reconnect policy
      |
      +-- Has durable message ID
             |
             v
       Lookup current processing state
             |
             v
      Classify failure + attempt
             |
       +-----+-----------+--------------+
       |                 |              |
       v                 v              v
     RETRY             FAILED        QUARANTINED
       |                 |              |
       v                 v              v
   next_attempt_at    Dead-letter     Security queue
                      record/store     / restricted access
       |                 |              |
       +-----------------+--------------+
                         |
                         v
                  Audit + monitoring
~~~

### 9.1. Dead-letter schema minh họa

Với PostgreSQL, có thể dùng bảng trạng thái inbound và một bảng dead-letter event:

~~~sql
CREATE TABLE inbound_mail_work (
    id UUID PRIMARY KEY,
    mailbox_id UUID NOT NULL,
    source_key VARCHAR(450) NOT NULL,
    payload_ref VARCHAR(500),
    workflow_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    terminal_reason VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(mailbox_id, source_key, workflow_type)
);

CREATE INDEX ix_mail_work_due
    ON inbound_mail_work(status, next_attempt_at);

CREATE TABLE inbound_dead_letter (
    id UUID PRIMARY KEY,
    inbound_work_id UUID NOT NULL
        REFERENCES inbound_mail_work(id),
    attempt_no INT NOT NULL,
    failure_kind VARCHAR(30) NOT NULL,
    failure_stage VARCHAR(50) NOT NULL,
    error_code VARCHAR(100) NOT NULL,
    terminal_reason VARCHAR(100) NOT NULL,
    payload_ref VARCHAR(500),
    dead_lettered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution VARCHAR(100),
    UNIQUE(inbound_work_id, attempt_no)
);
~~~

`source_key` trong ví dụ là chuỗi đã được canonicalize và scope theo mailbox; nếu dùng IMAP, nên lưu **riêng** folder, UIDVALIDITY và UID với kiểu dữ liệu/unique constraint phù hợp. Đừng dùng RFC `Message-ID` trực tiếp như một khóa source tuyệt đối. Schema trên nhấn mạnh ranh giới **durable state + DLQ event**, không phải migration hoàn chỉnh.

### 9.2. Ghi FAILED và dead-letter record trong một transaction

~~~sql
-- Trong transaction sau khi đã kiểm tra claim ownership.
UPDATE inbound_mail_work
SET status = 'FAILED',
    last_error_code = :error_code,
    terminal_reason = :terminal_reason,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :work_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;

-- Chỉ INSERT khi UPDATE thực sự thay đổi đúng một row.
INSERT INTO inbound_dead_letter(
    id, inbound_work_id, attempt_no, failure_kind,
    failure_stage, error_code, terminal_reason, payload_ref
)
VALUES (
    :dlq_id, :work_id, :attempt_no, :failure_kind,
    :failure_stage, :error_code, :terminal_reason, :payload_ref
);
~~~

**Không chạy hai lệnh rời rạc với auto-commit** nếu nghiệp vụ yêu cầu tính nhất quán: có thể row đã `FAILED` nhưng chưa có DLQ record. Service nên bắt đầu transaction, kiểm tra số row update bằng 1, insert event và commit cùng nhau.

Nếu error flow nhận lại cùng lỗi, unique key trên `(inbound_work_id, attempt_no)` giúp tránh sinh nhiều terminal event cho một attempt. Nếu hỗ trợ nhiều trạng thái terminal/events cho cùng attempt, cần một mô hình event ID/transition ID khác phù hợp hơn.

### 9.3. Nếu dead letter nằm trên broker

Một kiến trúc RabbitMQ:

~~~text
inbound.work.queue
      |
      v
Consumer
      |
      +-- success -> ack after durable business result
      |
      +-- transient -> retry policy / delayed queue
      |
      +-- permanent -> reject/nack without requeue
                           |
                           v
                     Dead-letter exchange
                           |
                           v
                     inbound.mail.dlq
~~~

Broker phải có DLX/queue binding, durability và chính sách acknowledge/publish phù hợp. **Gửi tới một `MessageChannel` tên `mailDeadLetterChannel` không tự cấu hình RabbitMQ DLX.**

Với Kafka, dead letter thường là một **topic riêng** do error handling/retry policy publish sau khi xử lý thất bại; cần kiểm soát publish confirmation, consumer offsets, headers, ACL và retention. Các cơ chế này thuộc tầng broker adapter và không phải tính năng tự động của `spring-integration-mail`.

### 9.4. Khi chuyển ErrorMessage sang DLQ cần giữ điều gì?

Một dead-letter payload tối thiểu:

~~~json
{
  "deadLetterId": "dlq-opaque-id",
  "inboundWorkId": "work-opaque-id",
  "sourceType": "IMAP",
  "mailboxId": "mailbox-opaque-id",
  "workflowType": "CREATE_SUPPORT_TICKET",
  "attempt": 5,
  "failureStage": "MIME_PARSE",
  "failureKind": "PERMANENT",
  "safeErrorCode": "INVALID_MULTIPART",
  "terminalReason": "NON_RETRYABLE_FAILURE",
  "payloadReference": "restricted-storage-reference"
}
~~~

Không đặt credential, attachment bytes, raw HTML, toàn bộ MIME header hoặc stack trace có thể chứa thông tin người dùng vào DLQ theo mặc định. Nếu cần replay, `payloadReference` phải trỏ tới dữ liệu thực sự bền vững, được ủy quyền và còn trong thời hạn lưu.

### 9.5. Quarantine khác dead letter vận hành thông thường

Với email đáng ngờ:

- `FAILED`: handler không xử lý được, có thể điều tra và khắc phục.
- `QUARANTINED`: nội dung bị hạn chế vì security policy; không cho operator thường tự retry hoặc tải attachment.

Quarantine nên có quyền truy cập, retention, malware scanning và quy trình release riêng. Không tạo một nút “Retry all” áp dụng cho cả email có mã độc và email timeout database.

## 10. Retry trước khi chuyển vào DLQ

Không phải mọi lỗi đều phải dead letter ngay. Với database tạm unavailable hoặc IMAP server chập chờn, thử lại có giới hạn là hợp lý.

Một retry policy minh họa:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Nếu `d_0 = 30 giây`, `d_max = 15 phút`, `max_attempts = 5`:

| Attempt vừa lỗi | Delay cơ sở cho lần sau | State |
| --- | --- | --- |
| 1 | 30 giây | RETRY |
| 2 | 60 giây | RETRY |
| 3 | 120 giây | RETRY |
| 4 | 240 giây | RETRY |
| 5 | Không còn attempt tự động | FAILED/DLQ |

Jitter có thể rải thời điểm retry để tránh nhiều worker cùng gọi IMAP/SMTP/database vào một giây. Không có thời gian retry chuẩn chung cho mọi use case; cần xét SLA, hạn lưu nội dung nguồn và loại side effect.

### 10.1. Retry ở tầng nào?

Có nhiều tầng khác nhau:

~~~text
IMAP reconnect attempt
      |
      v
Inbound message fetch attempt
      |
      v
Message processing attempt
      |
      v
External API side-effect attempt
~~~

Một reconnect attempt không đồng nghĩa với một email đã được xử lý lại. Đừng tăng `inbound_message.attempt_count` khi chưa fetch/claim một inbound work item; dùng counter/metrics riêng cho lỗi mailbox connection.

### 10.2. Retry advice hay durable retry queue?

Spring Integration có cơ chế advice/interceptor để retry một handler khi lỗi; `RequestHandlerRetryAdvice` thường được dùng quanh endpoint handler và cấu hình policy/backoff/recovery theo phiên bản.

**In-process retry** phù hợp lỗi tạm thời ngắn, nhưng có giới hạn:

- Worker thread có thể bị giữ trong nhiều lượt thử.
- Retry state có thể mất khi JVM restart.
- Nếu handler đã gây side effect một phần, retry có thể gây trùng.
- Không tự ghi DLQ bền vững.

Với email cần bảo đảm xử lý qua crash hoặc worker restart, nên có **durable retry state** trên database/broker, với mỗi attempt độc lập. Có thể kết hợp *rất ít* retry nội bộ cho lỗi an toàn và retry bền vững cho các trường hợp kéo dài, nhưng phải định nghĩa rõ thế nào là attempt để không vượt `max_attempts`.

### 10.3. Không để retry advice che dấu lỗi nghiệp vụ

Nếu một handler bắt mọi exception rồi trả success:

~~~java
try {
    ticketService.createTicket(mail);
} catch (Exception ex) {
    log.warn("Cannot process inbound mail", ex);
    // returning normally
}
~~~

thì Spring Integration có thể coi endpoint đã xử lý thành công; retry advice/error channel sẽ không còn biết có lỗi. Thay vào đó:

- Catch chỉ những lỗi mà handler có thể xử lý hoàn toàn.
- Nếu cần retry, ném exception có taxonomy rõ hoặc persist trạng thái `RETRY` có kiểm soát.
- Khi đã chủ động ghi `FAILED`/DLQ, tránh để cùng exception tạo một DLQ event thứ hai không dedupe.

### 10.4. Không để lỗi DLQ làm mất lỗi gốc

Giả sử business handler lỗi, rồi service lưu DLQ cũng lỗi:

~~~text
Original error: INVALID_MULTIPART
                  |
                  v
Dead-letter database unavailable
                  |
                  v
Secondary error: DEAD_LETTER_PERSIST_FAILED
~~~

Nếu message nguồn đã bị ack/move/delete trước khi lưu lỗi bền vững, nó có thể bị mất. Chính sách cần:

- Không ack nguồn trước khi đạt điều kiện durable receipt theo hợp đồng.
- Giữ hoặc recover work record để retry ghi DLQ.
- Ghi metric/alert **lỗi error flow**.
- Có nơi lưu tối thiểu để điều tra nếu hệ thống chính không ghi được.
- Giữ thông tin lỗi gốc và lỗi thứ cấp; không chỉ log exception sau cùng.

## 11. Inbound IMAP: không để error channel làm mất email

Khi nhận thư qua IMAP, một vấn đề quan trọng là **các cờ của mailbox và trạng thái xử lý nghiệp vụ không nằm trong cùng transaction**.

Ví dụ luồng không an toàn:

~~~text
IMAP adapter reads message
         |
         v
Mail marked SEEN / moved
         |
         v
Ticket handler throws
         |
         v
ErrorMessage logged
         |
         v
Next poll reads UNSEEN only
         |
         v
Mail never processed again
~~~

Một log event hay ErrorMessage không đủ để bảo đảm thư được xử lý lại. Cần lưu **identity của message nhận được** và business status vào kho bền vững.

### 11.1. ID nguồn phù hợp cho IMAP

Các ID thường gặp:

| ID | Ý nghĩa |
| --- | --- |
| RFC `Message-ID` | Header do sender khai, có thể thiếu/trùng/giả mạo |
| IMAP UID | Server cấp, trong phạm vi một folder |
| IMAP UIDVALIDITY | Thế hệ UID của folder |
| IMAP message sequence number | Vị trí tạm thời, thay đổi khi expunge |
| Internal inbound ID | UUID do ứng dụng cấp |

Khóa source identity hợp lý:

~~~text
(mailbox_id, folder_key, uid_validity, imap_uid)
~~~

Không dùng RFC `Message-ID` hoặc `getMessageNumber()` làm khóa duy nhất cho toàn bộ inbound mail. Hai thư có thể có cùng RFC Message-ID; một UID có thể được tái sử dụng sau khi UIDVALIDITY thay đổi.

### 11.2. Schema trạng thái nhận thư

~~~sql
CREATE TABLE inbound_mail_message (
    id UUID PRIMARY KEY,
    mailbox_id UUID NOT NULL,
    folder_key VARCHAR(250) NOT NULL,
    uid_validity BIGINT NOT NULL,
    imap_uid BIGINT NOT NULL,
    rfc_message_id VARCHAR(512),
    payload_ref VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(mailbox_id, folder_key, uid_validity, imap_uid)
);
~~~

Đây là **một schema minh họa riêng** cho inbound identity. Khi triển khai, có thể kết hợp bảng này với `inbound_mail_work` ở phần trước thay vì tạo hai bảng cùng biểu diễn một workflow. Mục tiêu là có source identity rõ và trạng thái xử lý độc lập với IMAP flags.

### 11.3. Vòng đời email inbound

~~~text
IMAP UID discovered
        |
        v
Insert inbound row (idempotent)
        |
        v
Optional snapshot MIME to durable storage
        |
        v
Worker atomic claim (PROCESSING)
        |
        v
Business handler
        |
      /   \
     v     v
  Success  ErrorMessage
     |     |
     v     +--> RETRY / FAILED / QUARANTINED
  Commit
  PROCESSED
     |
     v
  Optional IMAP mark/move
~~~

Nếu ứng dụng chỉ giữ UID mà chưa snapshot MIME, một thư có thể bị người dùng xóa hoặc chuyển folder trước khi retry. Error handler cần có trạng thái `SOURCE_UNAVAILABLE`/reconciliation thay vì cố fetch cùng UID trong một folder hoặc UIDVALIDITY khác.

### 11.4. Checkpoint discovery phải độc lập với xử lý

Giả sử:

~~~text
UID 1001 -> PROCESSED
UID 1002 -> RETRY
UID 1003 -> PROCESSED
UID 1004 -> DISCOVERED
last_discovered_uid = 1004
~~~

Cursor cho biết poller đã phát hiện và lưu IDs đến UID1004, **không nói rằng email UID1002 đã được xử lý**. Cần một work record/status riêng cho từng UID. Nếu một batch insert có lỗi, không được nâng cursor trước khi toàn bộ source identities trong batch đã được lưu bền vững.

### 11.5. UIDVALIDITY thay đổi

Nếu server trả `UIDVALIDITY` khác với giá trị đã lưu, phải ngừng dùng cursor cũ, khởi tạo generation mới và đối soát các thư xuất hiện trở lại. Không tiếp tục từ `last_discovered_uid` của thế hệ cũ và không đồng nhất cùng số UID giữa hai thế hệ.

Một bản ghi `FAILED`/`RETRY` từ generation cũ chỉ được retry nếu còn snapshot hợp lệ hoặc có nguồn tương ứng được xác minh. Không tự fetch UID giống số ở generation mới rồi xử lý như email cũ.

### 11.6. Khi error flow đã nhận lỗi thì poller sẽ làm gì?

Nếu error handler nhận exception, ghi `RETRY` bền vững rồi kết thúc bình thường, poller có thể tiếp tục các lần scan sau. Điều này **không có nghĩa thư tự được retry**: phải có worker lấy record `RETRY` khi đến hạn.

Nếu error handler chỉ log rồi trả về, lỗi có thể biến mất về mặt flow. Vì vậy, hợp đồng cần rõ:

~~~text
ErrorMessage handled successfully
    == failure disposition has been recorded durably
    != business operation has succeeded
~~~

Không đánh dấu `PROCESSED` hoặc move thư chỉ vì error flow xử lý xong exception.

## 12. Outbound SMTP: error flow khác inbound retry

Một luồng gửi email có thể đi qua:

~~~text
Business transaction
      |
      v
Mail outbox PENDING
      |
      v
IntegrationFlow / mail worker
      |
      v
Render MIME + JavaMailSender.send
      |
      +--> success: SMTP_ACCEPTED
      |
      +--> error: ErrorMessage / retry state / failed state
~~~

Nếu Spring Integration mail **outbound adapter** hoặc service handler dùng `JavaMailSender` ném exception, việc route lỗi tùy channel, endpoint và error handler đã cấu hình. `JavaMailSender` tự nó không publish ErrorMessage chỉ vì ứng dụng có bean `errorChannel`.

### 12.1. Những kết quả gửi cần phân biệt

| Kết quả | Điều biết được | Nên làm |
| --- | --- | --- |
| MIME preparation failure | Chưa nộp email lên SMTP | Sửa dữ liệu/template, có thể FAILED |
| Connection failure trước submission | SMTP chưa nhận nội dung nếu chứng minh được | Retry có backoff |
| SMTP temporary rejection | Relay từ chối tạm theo giai đoạn xác định | Retry theo code, quota, deadline |
| SMTP permanent rejection | Message/recipient bị từ chối dứt khoát | FAILED hoặc suppression theo policy |
| `send(...)` thành công | Relay chấp nhận email theo quan sát ứng dụng | Ghi `SMTP_ACCEPTED`/`SENT` |
| Timeout sau DATA | Relay có thể đã chấp nhận dù caller không thấy response | UNKNOWN/reconciliation |
| DB `markSent` thất bại sau SMTP accepted | SMTP có thể đã nhận nhưng outbox chưa đổi trạng thái | Không retry mù; lưu nguy cơ duplicate |

**SMTP accepted không đồng nghĩa email đã tới inbox**. Provider có thể gửi bounce/DSN sau đó. Retry của provider khi đã accepted cũng khác retry của ứng dụng; không tự nộp một email mới chỉ vì feedback `DEFERRED`.

### 12.2. Một lỗi có thể dẫn tới gửi trùng

~~~text
Worker sends message
      |
      v
SMTP server accepts DATA
      |
      v
JavaMailSender.send returns successfully
      |
      v
Database markSENT fails
      |
      v
Outbox remains PROCESSING
      |
      v
Lease expires, new worker retries
      |
      v
Second email can be sent
~~~

Ngay cả transactional outbox cũng không tạo transaction nguyên tử giữa database và SMTP relay. Một integration error flow cần trạng thái/metrics cho `UNKNOWN` hoặc state-write failure, và chính sách reconciliation/duplicate tolerance.

### 12.3. Không retry dựa duy nhất trên MailSendException

`org.springframework.mail.MailSendException` có thể bao nhiều lỗi của JavaMail/Jakarta Mail, gồm chi tiết transport và recipient. Không được viết:

~~~java
catch (MailSendException ex) {
    // Sai: luôn gửi lại ngay.
    mailSender.send(message);
}
~~~

Một exception chưa đủ để biết provider đã accepted hay chưa. Trong error flow nên lưu:

~~~text
attemptId
outboundDeliveryId
failureStage
smtpCommandStage (if known)
safeSmtpCode
result = DEFINITE_FAILURE | UNKNOWN
~~~

Không suy đoán “không gửi được” chỉ từ một timeout, đặc biệt nếu lỗi xảy ra sau lúc truyền SMTP DATA.

### 12.4. Dùng Spring Integration với outbound work item

Một chiến lược minh họa:

~~~java
@Bean
public IntegrationFlow outboundMailFlow(
        OutboundMailSenderHandler senderHandler) {

    return IntegrationFlow.from("mailOutboundWorkChannel")
            .handle(message -> senderHandler.submit(message))
            .get();
}
~~~

`OutboundMailSenderHandler` là thành phần ứng dụng quản lý route, gửi bằng `JavaMailSender` và cập nhật trạng thái. Trong flow dùng channel đồng bộ, exception từ handler có thể lan về caller. Nếu muốn một error flow kiểu message, phải cấu hình/mở ranh giới catch/publish rõ ràng; chỉ tạo `outboundMailErrorChannel` không khiến exception đồng bộ tự đến đó.

## 13. Bridge lỗi từ service tới ErrorMessage khi cần

Có trường hợp business handler không được khởi chạy bởi một endpoint có error publication tự động, nhưng ứng dụng vẫn muốn đưa lỗi vào một error flow tập trung.

Ví dụ một service xử lý `Message<MailWorkItem>`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public final class MailWorkExecutor {

    private final MessageChannel mailErrorChannel;
    private final MailBusinessProcessor processor;

    public MailWorkExecutor(
            MessageChannel mailErrorChannel,
            MailBusinessProcessor processor) {
        this.mailErrorChannel = mailErrorChannel;
        this.processor = processor;
    }

    public void execute(Message<MailWorkItem> message) {
        try {
            processor.process(message.getPayload());
        } catch (Exception ex) {
            MessagingException failure =
                    new MessagingException(message, ex);
            boolean published = mailErrorChannel.send(
                    new ErrorMessage(failure));

            if (!published) {
                throw failure;
            }
        }
    }
}
~~~

`MailWorkItem` và `MailBusinessProcessor` là abstraction minh họa. Khi error channel được dùng như một **đường ghi durable failure disposition**, còn cần xử lý trường hợp `send(...)` ném exception thay vì trả `false`, và xác nhận handler thực sự commit trạng thái `RETRY`/`FAILED`. `send` trả `true` **không tự chứng minh** một DLQ đã persist nếu consumer chỉ log.

**Không publish lỗi hai lần.** Nếu cùng exception còn được ném ra ngoài cho poller error handler xử lý và service cũng publish một `ErrorMessage`, cùng attempt có thể tạo hai bản ghi retry/dead letter. Chọn một error ownership rõ và dùng unique transition/attempt ID để dedupe.

### 13.1. Tách exception của nghiệp vụ và exception của error flow

~~~text
Business handler throws E1
       |
       v
Error publishing succeeds?
       |
   +---+---+
   |       |
  Yes      No
   |       |
   v       v
Durable disposition?   E2 = Error flow failure
   |       |
   v       v
Ack according          Keep source unacked / retry
to source contract     or invoke fallback incident path
~~~

Nếu `failureRouter.accept(...)` ghi DB rồi commit, có thể coi error đã được disposition. Nếu nó chỉ tăng counter hoặc ghi log, không được ack và xóa nguồn thư chỉ vì xử lý lỗi “không ném exception”.

### 13.2. Lỗi thứ cấp có thể làm mất source context

Một ErrorMessage ném tiếp exception khi serialize payload sang DLQ có thể khiến root cause bị che mất. Giữ `safeErrorCode` và `attemptId` từ lỗi đầu tiên; lỗi `DLQ_PUBLISH_FAILED` là **một sự cố riêng**. Log và alert cả hai, nhưng không tạo chuỗi publish vô hạn từ cùng một error channel.

## 14. Chọn channel phù hợp cho error flow

Không phải mọi channel có tên “error” đều có hành vi giống nhau. Chọn loại channel ảnh hưởng đến đồng bộ, thứ tự, backpressure, lỗi thứ cấp và khả năng lưu dữ liệu.

| Channel | Cơ chế | Dùng khi nào? | Điểm cần chú ý |
| --- | --- | --- | --- |
| `DirectChannel` | Handler được gọi đồng bộ trên sender thread | Error handler ngắn, ghi state/audit cần hoàn tất trước khi caller tiếp tục | DB lỗi có thể lan trở lại publisher |
| `ExecutorChannel` | Dispatch sang executor | Muốn tách xử lý lỗi khỏi thread poller | Cần bounded queue; crash có thể mất công việc in-memory |
| `PublishSubscribeChannel` | Nhiều subscriber có thể nhận event | Fan-out logging, monitoring, state recorder | Một subscriber lỗi/async có thể làm semantics phức tạp; không thay durable commit |
| `QueueChannel` | Bên gửi đưa message vào queue, poller khác lấy ra | Bù tải/điều phối bước kế tiếp | Mặc định không durable; cấu hình capacity/message store |
| Broker-backed channel | Message đi qua broker | Durable retry/DLQ nếu cấu hình đầy đủ | Cần ack, publisher confirms và retention |

### 14.1. Vì sao một DirectChannel thường dễ hiểu để bắt đầu?

Với một inbound handler, ta có thể yêu cầu:

~~~text
Error published to mailErrorChannel
           |
           v
Failure handler commits RETRY/FAILED state
           |
           v
Error handler returns
           |
           v
Poller can proceed
~~~

Điều này dễ suy luận hơn fire-and-forget error processing. Nhưng nó cũng có nhược điểm: nếu database đang outage, error handler có thể block hoặc ném exception, làm poller chậm/dừng chu kỳ. Cần timeout và policy rõ ràng, không giữ thread vô hạn.

### 14.2. Tách quan sát và durable disposition

Một cấu trúc:

~~~text
             ErrorMessage
                  |
                  v
           Durable disposition
              RETRY/FAILED
                  |
               COMMIT
                  |
                  v
           Publish safe event
              |
        +-----+-----+
        |           |
        v           v
      Metrics      Logging/alert
~~~

Chọn **state persistence làm điều kiện thành công**, còn metrics/log có thể xuất sau commit. Nếu metrics service tạm lỗi, không nên tự tạo retry nghiệp vụ hoặc gửi email hai lần chỉ vì không ghi được metric.

### 14.3. Tránh “error of error” loop

Nếu ErrorMessage được gửi tới channel có handler cũng ném exception và lại được publish tới cùng error channel, ta có thể gặp vòng lặp:

~~~text
mailErrorChannel -> error handler fails
     ^                    |
     |                    |
     +---- republish -----+
~~~

Một chiến lược:

- Error handler ghi DLQ có giới hạn timeout.
- Nếu ghi thất bại, log một **sanitized secondary incident** và để lỗi lan tới caller/source error semantics.
- Hệ thống alert theo `ERROR_FLOW_PERSIST_FAILURE`.
- Không tự publish cùng error message vào cùng channel vô hạn.
- Có deduplication theo `attemptId + errorDispositionType` nếu publication lặp lại.

## 15. Redrive từ dead letter về luồng xử lý

Dead letter không chỉ là nơi chứa message thất bại. Khi lỗi đã được sửa, operator có thể muốn **redrive** (đưa công việc trở lại hàng xử lý).

Tuy nhiên, không phải mọi email đều còn phù hợp để xử lý:

- Email inbound chứa file độc hại không được tự thả ra khỏi quarantine.
- Ticket đã được tạo nhưng DB status chưa commit; redrive mù có thể tạo ticket trùng.
- Email password reset đã hết hạn; gửi lại bản cũ có thể gây nhầm lẫn.
- Một inbound source message đã bị xóa; không còn MIME snapshot để replay.
- Một outbound email đã SMTP accepted nhưng ở `UNKNOWN`; gửi lại có thể tạo duplicate.

### 15.1. Quy trình redrive

~~~text
Operator requests redrive
            |
            v
Authenticate + authorize
            |
            v
Inspect DLQ reason + attempt history
            |
            v
Check payload still exists / integrity
            |
            v
Check tenant, deadline, suppression, security policy
            |
            v
Check prior side effect / SMTP outcome
            |
            v
Reserve capacity and create audit record
            |
            v
Requeue existing work or create linked attempt
            |
            v
Observe new outcome
~~~

### 15.2. Hai mô hình redrive

**Tiếp tục cùng work item:**

~~~text
workId = W1
attempts = 1, 2, 3
status = FAILED

Operator approves retry cycle 2
workId = W1
attempts = 4, 5...
~~~

Ưu điểm: giữ lịch sử trên một record. Nhưng phải làm rõ `max_attempts` là giới hạn theo chu kỳ hay tổng các attempt, không reset âm thầm số lần xử lý.

**Tạo work item mới có liên kết:**

~~~text
oldWorkId = W1 (FAILED)
newWorkId = W2 (DISCOVERED/PENDING)
redriveOf = W1
redriveReason = "downstream ticket service restored"
~~~

Ưu điểm: giữ W1 bất biến để audit. Nhược điểm: cần kiểm soát business idempotency giữa W1/W2 để cùng thư không tạo side effect trùng khi đó không phải hành vi được phép.

### 15.3. SQL redrive một row minh họa

~~~sql
UPDATE inbound_mail_work
SET status = 'RETRY',
    next_attempt_at = now(),
    claim_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :work_id
  AND status = 'FAILED';
~~~

**Không copy nguyên SQL này thành API redrive công khai**. Service phải thực hiện authentication/authorization, check source/snapshot, duplicate side effects và policy retry cycle, ghi audit trong transaction và kiểm tra update count. Một hành động bulk “reset mọi FAILED thành RETRY” có thể lặp lại lỗi và làm quá tải hệ thống.

### 15.4. Redrive với broker DLQ

Nếu dùng RabbitMQ/Kafka:

1. Đọc DLQ item cùng source metadata.
2. Xác định internal work/delivery ID và trạng thái nghiệp vụ.
3. Validate redrive policy.
4. Gửi lại bằng cơ chế broker có xác nhận bền vững.
5. Chỉ ack/commit offset nguồn theo hợp đồng sau khi publish/redrive được xác nhận.
6. Ghi audit và quan sát attempt mới.

Trong một crash window, việc republish thành công nhưng chưa ack DLQ có thể khiến redrive lặp lại. Vì vậy consumer vẫn phải **idempotent**, không giả định thao tác “move DLQ → work” luôn nguyên tử trên mọi broker.

### 15.5. Audit cho thao tác redrive

~~~sql
CREATE TABLE inbound_redrive_audit (
    id UUID PRIMARY KEY,
    work_id UUID NOT NULL,
    actor_id VARCHAR(120) NOT NULL,
    reason VARCHAR(300) NOT NULL,
    action VARCHAR(40) NOT NULL,
    previous_status VARCHAR(30) NOT NULL,
    new_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Không ghi token, password, email body hoặc stack trace raw vào `reason`. Thường nên lưu ticket/incident ID và một danh mục reason thay vì paste nội dung thư.

## 16. Tích hợp Spring Retry/advice với errorChannel

Spring Integration có thể áp dụng **advice chain** cho message handler để retry hoặc recover. Điều cần hiểu là **retry nằm ở đâu trong flow** và exception còn được publish tới error channel hay đã được xử lý bởi recoverer.

~~~text
Inbound message
     |
     v
Handler with retry advice
     |
     +--> attempt 1 fails
     +--> attempt 2 fails
     +--> attempt 3 fails
     |
     v
Recovery callback (if configured)
     |
     +--> publish ErrorMessage?
     +--> record RETRY/FAILED?
     +--> throw?
~~~

### 16.1. ErrorMessageSendingRecoverer

Spring Integration có `ErrorMessageSendingRecoverer`, có thể được dùng làm recovery callback trong một số cấu hình retry advice. Vai trò là chuyển một failure thành error message được gửi tới channel định trước.

**Cần đặc biệt cẩn trọng với attempt count:** nếu retry advice thực hiện ba lần gọi handler trong một polling cycle rồi chỉ có một ErrorMessage cuối cùng, database `attempt_count` có thể đang đếm “một worker claim”, không phải ba **handler attempts**. Hãy định nghĩa rõ số lần thử bạn báo cáo và giới hạn tổng ở tất cả tầng.

### 16.2. Không dùng retry advice cho mọi side effect

Một handler tạo ticket rồi lỗi ở bước cập nhật trạng thái có thể đã tạo ticket trong attempt đầu. Retry advice gọi lại handler ngay trong cùng process có thể tạo ticket thứ hai.

Chỉ dùng local retry trực tiếp khi:

- Operation idempotent; **hoặc**
- Chắc chắn lỗi xảy ra trước side effect; **và**
- Retry count/timeout rõ ràng; **và**
- Không vượt SLA hoặc giữ worker thread quá lâu.

Nếu không bảo đảm các điều kiện đó, lưu durable state `UNKNOWN`/`RETRY` rồi xử lý bằng worker có idempotency key/reconciliation thường dễ kiểm soát hơn.

### 16.3. Recovery không đồng nghĩa xử lý thành công

Một recoverer chuyển exception tới error channel và kết thúc bình thường có thể khiến endpoint upstream coi lỗi đã được tiêu thụ. Vì vậy, error handler phải lưu một disposition bền vững. Không chỉ log một câu “retry exhausted” rồi để framework tiếp tục như thể message đã hoàn thành business workflow.

### 16.4. Không trộn retry source và retry message

Ví dụ một IMAP server connection bị lỗi khi poll:

~~~text
IMAP connection failure
  -> retry IMAP connection with bounded backoff
  -> no inboundMessageId yet
~~~

Trong khi một message đã được nhận có lỗi khi import:

~~~text
inboundMessageId=D1
  -> processing attempt fails
  -> record retry_count / next_attempt_at
~~~

Hai loại retry cần metric, SLO và dead letter policy khác nhau. Không tạo một bản ghi D1 “ảo” chỉ để có nơi lưu lỗi kết nối.

## 17. Quan sát error channel và DLQ với Micrometer/Actuator

Một error flow không thể vận hành tốt nếu chỉ ghi stack trace. Cần thấy **số lỗi, loại lỗi, độ tuổi backlog và tình trạng DLQ**.

### 17.1. Metrics cần phân biệt

| Metric logic | Kiểu | Câu hỏi |
| --- | --- | --- |
| `mail_error_messages_total` | Counter | Bao nhiêu ErrorMessage đã được router nhận? |
| `mail_error_disposition_total` | Counter | Bao nhiêu lỗi được quyết định RETRY/FAILED/QUARANTINED/UNKNOWN? |
| `mail_error_flow_failures_total` | Counter | Chính luồng ghi lỗi có thất bại không? |
| `mail_mailbox_connect_failures_total` | Counter | Mailbox nào gặp lỗi connect/auth theo nhóm? |
| `mail_inbound_processing_attempts_total` | Counter | Bao nhiêu lượt handler đã chạy? |
| `mail_inbound_completed_total` | Counter | Bao nhiêu work item đã hoàn tất? |
| `mail_inbound_retry_due` | Gauge | Bao nhiêu message tới hạn retry? |
| `mail_inbound_processing_inflight` | Gauge | Bao nhiêu message đang được claim? |
| `mail_dead_letter_current` | Gauge | Bao nhiêu message còn chờ triage? |
| `mail_dead_letter_arrivals_total` | Counter | Có bao nhiêu message mới chuyển vào DLQ? |
| `mail_dead_letter_oldest_age_seconds` | Gauge | Dead letter lâu nhất chưa được xử lý bao lâu? |
| `mail_redrive_attempts_total` | Counter | Bao nhiêu lần redrive được operator phê duyệt? |
| `mail_inbound_oldest_due_age_seconds` | Gauge | Work item đến hạn lâu nhất chưa xử lý? |
| `mail_source_last_successful_poll_age_seconds` | Gauge | Lần poll thành công gần nhất đã lâu chưa? |

Không phải ứng dụng nào cũng cần từng metric ngay đầu tiên. Nhưng **tổng số ErrorMessage** không đủ để biết email còn xử lý được không; phải kết hợp **ready/failed/oldest age/throughput**.

### 17.2. Chọn nhãn có cardinality thấp

Ví dụ nhãn được chuẩn hóa:

~~~text
workflow = inbound_ticket | inbound_bounce | outbound_transactional
source = imap | pop3 | webhook | smtp
stage = mime_parse | database | external_api | smtp_send
outcome = retry | failed | quarantined | unknown
error_code = imap_timeout | invalid_mime | db_unavailable | none
~~~

Không gắn raw recipient email, RFC Message-ID, subject, attachment filename, stack trace hoặc internal UUID trên mỗi metric series. Với nhiều tenant, dùng group/plan/region đã được duyệt nếu phạm vi nhãn hữu hạn và quyền xem phù hợp.

### 17.3. Ví dụ Micrometer counter

~~~java
package com.example.mail.ops;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public final class MailErrorMeters {

    private final MeterRegistry registry;

    public MailErrorMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    public void disposition(
            String workflow,
            String stage,
            String outcome,
            String errorCode) {

        Counter.builder("mail.error.disposition")
                .tag("workflow", workflow)
                .tag("stage", stage)
                .tag("outcome", outcome)
                .tag("error_code", errorCode)
                .register(registry)
                .increment();
    }
}
~~~

Trong production, hãy validate các nhãn bằng enum/allowlist thay vì truyền nguyên `Throwable.getMessage()` hoặc string từ dữ liệu inbound. Một attacker có thể tạo hàng nghìn error code/subject khác nhau nếu metrics lấy tag trực tiếp từ input.

**Lưu ý:** Counter là quan sát của process; nó có thể reset khi restart hoặc không kịp tăng sau DB commit. Database/outbox/DLQ là nguồn audit bền vững; Micrometer giúp cảnh báo và phân tích xu hướng, không thay thế lịch sử trạng thái.

### 17.4. Prometheus và Grafana

Với Spring Boot Actuator và registry Prometheus:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: when-authorized
~~~

Endpoint thường là `/actuator/prometheus` khi dependency và security config cho phép. Không expose các endpoint management ra Internet hoặc không có authorization. Tên metric xuất sang Prometheus tùy convention/registry; kiểm tra output thật trước khi viết PromQL.

PromQL minh họa nếu các series đã được xuất:

~~~promql
# Tốc độ lỗi được disposition theo nhóm trong 5 phút
sum by (workflow, outcome) (
  rate(mail_error_disposition_total[5m])
)

# Số job FAILED còn nằm ở DLQ, nếu gauge là global snapshot
max(mail_dead_letter_current)

# Thư đến hạn đang chờ lâu nhất
max(mail_inbound_oldest_due_age_seconds)
~~~

**Chú ý gauge global:** nếu mọi replica đều query cùng DB để xuất `mail_dead_letter_current`, `sum` sẽ đếm trùng. Chọn collector authoritative hoặc phép tổng hợp đúng scope; không tự cộng mọi instance.

### 17.5. Cảnh báo có thể hành động

| Cảnh báo | Tín hiệu | Hành động |
| --- | --- | --- |
| Mailbox không poll được | Last successful poll age vượt SLO | Kiểm tra IMAP credential/network/TLS |
| Dead letter tăng nhanh | DLQ arrivals tăng theo error code | Xem deploy, parser và dữ liệu nguồn |
| Error flow tự thất bại | `error_flow_failures_total` tăng | Kiểm tra DB/broker dùng ghi DLQ |
| Processing backlog quá lâu | Oldest due age tăng và completed rate thấp | Kiểm tra worker, capacity, downstream |
| Retry storm | Retry scheduled/started rate tăng đột biến | Backoff, jitter, provider outage |
| Quarantine spike | MIME/security errors tăng | Kiểm tra chiến dịch email độc hại hoặc parser |
| SMTP outcome UNKNOWN | Không rõ relay đã accepted | Đối soát trước khi gửi lại |
| Expired lease cao | Worker crash/hang | Kiểm tra timeout, heartbeat và concurrency |

Ngưỡng alert phải dựa trên SLO thực tế. Một message bị từ chối do file không hợp lệ không nhất thiết là incident; hàng trăm message authentication failed trong vài phút có thể ảnh hưởng nghiêm trọng.

### 17.6. Log/trace theo work ID

Một structured event:

~~~json
{
  "event": "mail.failure.disposition",
  "workId": "opaque-work-id",
  "attemptId": "opaque-attempt-id",
  "workflow": "INBOUND_TICKET",
  "source": "IMAP",
  "stage": "BUSINESS_DATABASE",
  "safeErrorCode": "DB_TIMEOUT",
  "decision": "RETRY",
  "nextAttemptAt": "2026-11-12T13:25:00Z"
}
~~~

Đừng log `MimeMessage.toString()`, nguyên exception chain có PII, raw headers, authentication details hoặc attachment bytes trong đường error handling. Nếu cần tra source identity, dùng internal work ID để tìm trong giao diện có phân quyền.

## 18. Kiểm thử ErrorMessage và dead-letter flow

Một bộ test nên bao phủ cả **error routing** và **durable state transition**, không chỉ xác nhận handler đã được gọi.

### 18.1. Unit test phân loại lỗi

Một ma trận:

| Input | Failure stage | Kỳ vọng |
| --- | --- | --- |
| Missing required field | BUSINESS_VALIDATE | Permanent/FAILED |
| IMAP temporary timeout | IMAP_CONNECT | Source reconnect/backoff |
| DB temporarily unavailable | BUSINESS_DATABASE | Retry nếu message đã có ID |
| Malware detected | ATTACHMENT_SCAN | QUARANTINED |
| External API timeout after request sent | EXTERNAL_SIDE_EFFECT | UNKNOWN/reconcile |
| SMTP accepted then DB commit fails | STATE_PERSIST | UNKNOWN risk, không blind resend |
| Invalid recipient | SMTP_SEND | Permanent failure theo mã SMTP đã xác minh |

Đừng mock một `MailSendException` rồi tự kết luận toàn bộ tình huống SMTP 4xx/5xx đã được test. Mock kiểm tra application policy, không kiểm tra transport thực sự tạo error code nào.

### 18.2. Test error channel nhận ErrorMessage

Một example sử dụng Spring `ErrorMessage`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class ErrorMessageContextTest {

    @Test
    void preservesFailedMessageContext() {
        Message<String> source = MessageBuilder
                .withPayload("test-work")
                .setHeader("workId", UUID.randomUUID().toString())
                .build();

        MessagingException failure = new MessagingException(
                source, new IllegalStateException("fake processing error"));
        ErrorMessage error = new ErrorMessage(failure);

        assertThat(error.getPayload())
                .isInstanceOf(MessagingException.class);
        assertThat(((MessagingException) error.getPayload())
                .getFailedMessage())
                .isSameAs(source);
    }
}
~~~

Test này xác nhận cách trích `failedMessage` khi error được tạo rõ ràng. Nó **không chứng minh** mọi lỗi của IMAP/SMTP tự động gắn failedMessage hoặc đi qua channel; cần integration test về thực tế source/endpoint.

### 18.3. Test poller error channel end-to-end

Một kịch bản:

~~~text
Mock/fake MessageSource returns a mail work message
              |
              v
IntegrationFlow poller invokes business handler
              |
              v
Handler throws controlled exception
              |
              v
mailErrorChannel receives ErrorMessage
              |
              v
failureRouter persists RETRY/FAILED
              |
              v
Assert database state + attempt history
~~~

Với endpoint polling, dùng thời gian chờ có timeout (ví dụ Awaitility) thay vì `Thread.sleep` cố định. Mỗi test cần unique work ID, database isolation và không xóa chung message queue nếu test chạy song song.

Đồng thời test **lỗi trước khi có Message<?>**, ví dụ fake IMAP source ném exception lúc connect. Kỳ vọng tạo source-level incident, không tự dựng một work item giả rồi đưa vào DLQ.

### 18.4. Test DLQ persistence bị lỗi

Đây là test rất quan trọng:

1. Business handler throw.
2. `mailErrorChannel` nhận ErrorMessage.
3. Repository ghi `FAILED`/DLQ được cấu hình ném lỗi.
4. Error flow **không báo durable success giả**.
5. Theo nguồn nhận, message không bị xóa/ack trước khi có đường khôi phục hợp lệ.
6. Có metric/alert `DLQ_PERSIST_FAILED`.
7. Khi DB phục hồi, thử lại/đối soát không tạo duplicate side effect.

Nếu test chỉ assert log có chữ “failed” rồi kết thúc, nó không phát hiện rủi ro mất email.

### 18.5. Test lỗi permanent không retry vô hạn

Một email có multipart hỏng được lưu `payload_ref`:

~~~text
Attempt 1: MIME_PARSE throws INVALID_MULTIPART
        |
        v
Failure classifier: PERMANENT
        |
        v
Status: FAILED / QUARANTINED
        |
        v
No automatic attempt 2, 3, 4...
~~~

Assert terminal reason/attempt history và không có work item đủ điều kiện được poll lại. Nếu người vận hành muốn redrive sau khi sửa parser, cần một quy trình có audit.

### 18.6. Test retry với bounded attempts

Với `max_attempts=3`:

~~~text
Claim #1 -> transient error -> RETRY after backoff
Claim #2 -> transient error -> RETRY after backoff
Claim #3 -> transient error -> FAILED/DLQ
~~~

Assert:

- `attempt_count=3`.
- Không có claim #4 tự động.
- Dead letter record được ghi đúng một lần.
- `last_error_code` giữ nguyên mã lỗi thực tế.
- `terminal_reason=MAX_ATTEMPTS_EXHAUSTED` được lưu riêng.
- Retry schedule không gọi handler trước `next_attempt_at`.

### 18.7. Test crash window và idempotency

Giả sử handler tạo ticket:

~~~text
Create ticket T1
       |
       v
Process crashes before marking PROCESSED
       |
       v
Retry same inbound work ID
       |
       v
Must not create ticket T2
~~~

Nếu ticket và state nằm cùng database, lưu chúng cùng transaction. Nếu ticket ở external service, dùng idempotency key ổn định và reconciliation. Test phải kiểm tra **kết quả nghiệp vụ**, không chỉ số ErrorMessage.

### 18.8. Test inbound thật bằng SMTP/IMAP test server

Có thể dùng **GreenMail** với cấu hình hỗ trợ IMAP để:

1. Tạo mailbox test và gửi một email mẫu vào đó.
2. Poll bằng Spring Integration Mail/Jakarta Mail.
3. Gây lỗi xử lý có kiểm soát.
4. Xác nhận error flow và status database.
5. Sửa lỗi/tới lịch retry, xác nhận chỉ một business side effect.
6. Chạy poll lần nữa, xác nhận source identity không tạo work item trùng.

Mailpit hoặc một SMTP sink chỉ có SMTP/API nhận message **không nhất thiết cung cấp IMAP mailbox**. Test nguồn IMAP phải chọn công cụ hỗ trợ đúng protocol.

### 18.9. Test outbound riêng với fake SMTP

Với SMTP integration:

- Success: relay test nhận message; outbox `SENT`.
- Permanent rejection: `FAILED`, không blind retry.
- Temporary rejection: `RETRY` theo backoff.
- Timeout sau DATA: outcome `UNKNOWN` nếu không có bằng chứng dứt khoát.
- SMTP accepted + DB update fail: không tự nộp lại ngay.

Một fake SMTP server có programmable responses sẽ phù hợp hơn SMTP sink mặc định khi cần mô phỏng lỗi protocol chi tiết.

## 19. Runbook: error channel nhận lỗi liên tục

Một error channel đang nhận nhiều message có thể phản ánh sự cố ở source, handler, downstream hoặc một thay đổi cấu hình. Không nên bắt đầu bằng “tăng retry count”.

### 19.1. Bước 1: xác định phạm vi

Kiểm tra:

- Lỗi đến từ `INBOUND_IMAP`, `INBOUND_WEBHOOK` hay `OUTBOUND_SMTP`?
- Có `inboundMessageId`/`outboundDeliveryId` không, hay lỗi ở tầng kết nối?
- `failureStage` và `safeErrorCode` là gì?
- Bắt đầu từ lúc nào, sau deploy/secret rotation hay provider outage?
- Bao nhiêu message thực sự bị ảnh hưởng, bao nhiêu mới vào DLQ?
- Queue ready age và last successful processing có tăng không?

Ví dụ:

~~~text
mailbox source MB1:
  errorCode = IMAP_AUTH_FAILURE
  failedMessage = null
  no inbound work ID

=> Resolve mailbox credential / provider access.
=> Do not create fake message DLQ items.
~~~

Một ví dụ khác:

~~~text
inbound work D1:
  errorCode = INVALID_MULTIPART
  attemptCount = 1
  payloadRef = stored safely

=> Mark FAILED / QUARANTINED.
=> Do not reconnect IMAP repeatedly to fix MIME bytes.
~~~

### 19.2. Bước 2: kiểm tra tính bền vững

Không chỉ tìm log lỗi. Hỏi:

1. Email gốc hoặc snapshot còn truy cập được không?
2. Bản ghi inbound/outbound đã được tạo trước khi error xảy ra chưa?
3. Error flow đã commit `RETRY`/`FAILED` hay chỉ publish vào một in-memory channel?
4. Với broker, message đã được ack, offset commit hoặc chuyển vào DLQ thành công chưa?
5. Có lỗi thứ cấp khi lưu DLQ không?

Nếu một message đã bị ack/move/delete mà không có durable record, cần kích hoạt quy trình phục hồi từ mailbox/provider logs/backup nếu được phép; không giả định error channel có thể tự khôi phục nó.

### 19.3. Bước 3: quyết định hành động đúng loại lỗi

| Tình huống | Hành động |
| --- | --- |
| IMAP authentication failed | Kiểm tra credential/OAuth/TLS, giảm reconnect storm |
| IMAP network unavailable | Backoff, health check và chờ hồi phục |
| Handler database timeout | Kiểm tra DB pool/lock/outage, retry có giới hạn |
| MIME invalid hàng loạt sau deploy | Kiểm tra parser regression và quarantine records |
| Attachment độc hại | Không redrive tự động; xử lý theo security workflow |
| External ticket API timeout | Reconcile/idempotency key trước khi gọi lại |
| SMTP rate limit | Giảm concurrency, backoff/jitter |
| SMTP auth fail | Sửa credential, không retry cùng secret sai liên tục |
| SMTP result unknown | Đối soát trước resend |
| Dead-letter DB/broker unavailable | Alert error flow, giữ nguồn chưa ack nếu policy cho phép |

### 19.4. Bước 4: xác nhận phục hồi

Theo dõi:

- Lỗi mới giảm và last successful poll/process cập nhật.
- Queue ready age giảm.
- Retry due jobs được xử lý, không tạo retry storm.
- DLQ arrivals về mức bình thường.
- Những item terminal cũ được triage hoặc redrive theo policy.
- Không có ticket/email gửi trùng sau recovery.
- Không có dữ liệu bị mất vì ack/mark SEEN sớm.

## 20. Runbook: dead letter tăng đột biến

DLQ tăng không tự nói được là lỗi của Spring Integration. Tìm **nhóm nguyên nhân** và **mốc thay đổi**.

~~~text
Alert: inbound_dead_letter_arrivals spikes
           |
           v
Group by safeErrorCode / workflow / source
           |
           v
Check release, schema, auth, upstream changes
           |
    +------+----------------+
    |                       |
    v                       v
Transient but exhausted    Permanent/unsafe
    |                       |
    v                       v
Fix service/backoff         Fix validation/security
    |                       |
    v                       v
Approved redrive           Quarantine/review
           |
           v
Audit + monitor success
~~~

### 20.1. Khi nào không nên “Retry all”?

- Message bị từ chối vì malware/invalid payload.
- Payload gốc đã hết retention hoặc checksum không khớp.
- Business operation đã hoàn tất nhưng app state chưa cập nhật.
- Một inbound reply đã được gắn ticket thủ công, không còn cần xử lý.
- Outbound email đã được SMTP accepted nhưng retry status do lỗi DB.
- Source identity thuộc mailbox/tenant không còn được phép xử lý.

Chức năng redrive cần có **dry-run, phạm vi giới hạn, quyền người thao tác, audit và rate limit**. Nếu không, thao tác xử lý sự cố có thể trở thành nguyên nhân làm tăng lỗi hoặc tạo dữ liệu trùng.

### 20.2. Không xóa DLQ để làm dashboard về 0

Một DLQ chứa 500 thư thất bại có thể là thông tin quan trọng phục vụ điều tra. Xóa record sẽ mất:

- Source identity và metadata về công việc bị lỗi.
- Attempt history.
- Nguyên nhân terminal.
- Khả năng liên kết với ticket hoặc outbound delivery.
- Audit về thời điểm lỗi xảy ra.

Cần retention/archive theo policy, không để dữ liệu vô hạn nhưng cũng không xóa dữ liệu chỉ vì dashboard cảnh báo.

## 21. Bảo mật riêng cho error channel và dead letter

Error flow có khả năng tiếp cận nhiều thông tin hơn handler bình thường vì nó chứa exception, headers và đôi khi cả payload lỗi. Điều đó làm nó trở thành một ranh giới bảo mật.

### 21.1. Nguy cơ rò rỉ dữ liệu qua exception

Exception message/stack trace có thể chứa:

- SMTP/IMAP host, user name.
- Recipient/sender email.
- MIME header hoặc subject.
- Raw body fragment do parser báo lỗi.
- URL nội bộ hoặc object storage key.
- External service response chứa token.

Không serialize nguyên `Throwable` vào bảng dead letter hoặc message broker mà không có nhu cầu và kiểm soát dữ liệu. Nên lưu **safeErrorCode**, stage, attemptId, correlation ID và source reference đã được kiểm soát. Log chi tiết cần có masking, giới hạn quyền đọc và retention.

### 21.2. Chống MIME/attachment abuse

Email đến từ bên ngoài có thể chứa:

- Multipart lồng sâu để gây quá tải parser.
- Header cực dài hoặc số lượng part bất thường.
- Attachment có content type giả.
- Archive bomb, file chứa malware.
- HTML có link hoặc nội dung gây lừa đảo.

Inbound flow phải giới hạn **message size, MIME depth, số part, attachment bytes, thời gian parse và concurrency**. Với nội dung đáng ngờ, chuyển `QUARANTINED` trước khi handler nghiệp vụ tạo ticket hiển thị hoặc import file.

### 21.3. Phân quyền DLQ và redrive

Không phải mọi người có quyền xem dashboard đều được:

- Tải raw MIME hoặc attachment.
- Thấy địa chỉ khách hàng.
- Thay trạng thái `FAILED` thành `RETRY`.
- Gửi lại email outbound.
- Xóa event audit.

Áp dụng RBAC/tenant scopes, audit actor/reason/time, mã hóa ở trạng thái lưu trữ khi cần và kiểm soát retention. Không đưa một DLQ chứa email nhạy cảm vào topic/bucket công khai chỉ để dễ debug.

### 21.4. Không dùng Message-ID để vượt quyền

RFC `Message-ID`, `In-Reply-To` và `References` do mail client/người gửi có thể tạo. Chúng hữu ích để tìm conversation ứng viên nhưng **không phải bằng chứng người gửi có quyền sửa ticket, account hoặc hồ sơ khác**.

Một ErrorMessage chứa original mail của attacker cũng là dữ liệu không tin cậy. Không cho giá trị header quyết định tùy ý bucket, file path, SQL query hoặc routing target.

### 21.5. Giới hạn tốc độ lỗi và log

Một email hỏng có thể bị poll và lỗi mỗi giây. Nếu mỗi lần lưu raw MIME/stack trace, attacker có thể tạo:

- Disk/log exhaustion.
- High-cardinality metrics.
- Alert fatigue.
- Nhiều attempts trong DB không hữu ích.

Dùng dedupe source identity, retry backoff, bounded DLQ, metric labels hữu hạn và rate-limited logs. Nhưng **không nuốt lỗi** nếu điều đó làm mất work item chưa được disposition.

## 22. Sơ đồ lựa chọn xử lý lỗi

~~~text
An error occurs in Spring Integration Mail
                    |
                    v
        Is error in an Integration endpoint?
               |                  |
              Yes                No
               |                  |
               v                  v
   Configure publisher /     Explicit try/catch,
   error channel/poller      publish error or persist state
               |                  |
               +--------+---------+
                        |
                        v
                 Have work/delivery ID?
                    |           |
                   No          Yes
                    |           |
                    v           v
             Source incident   Lookup durable state
             reconnect policy       |
                                      v
                              Classify error
                                      |
                          +-----------+-----------+
                          |           |           |
                          v           v           v
                       Transient    Permanent    Unknown
                          |           |           |
                          v           v           v
                    Retry schedule  Failed/DLQ   Reconcile
                          |           |           |
                          +-----------+-----------+
                                      |
                                      v
                              Commit durable outcome
                                      |
                                      v
                               Safe metrics/audit
                                      |
                                      v
                        Optional source ack/move/cleanup
~~~

### 22.1. Quy tắc “error handled” phải được định nghĩa

Tránh nhầm lẫn:

~~~text
ErrorMessage consumed != business success
ErrorMessage logged   != durable dead letter
SMTP send exception   != definitely not accepted
IMAP SEEN flag         != business PROCESSED
DLQ published          != safe to lose audit/source state
~~~

Để một flow đáng tin cậy, mỗi bước phải có trạng thái và ranh giới commit/ack được mô tả rõ. Nếu một lỗi không có source message ID, xử lý nó như sự cố hạ tầng thay vì bịa một email giả để đưa vào DLQ.

## 23. Các câu hỏi thường gặp

**“Error channel có phải là dead-letter queue không?”**  
Không. Error channel là một kênh nhận `ErrorMessage`. Nó có thể giúp route lỗi tới handler, nhưng không mặc định lưu message bền vững, không có tự động retry/audit/redrive. DLQ là nơi lưu lỗi terminal hoặc không thể tự phục hồi theo policy.

**“Thêm một bean tên errorChannel thì mọi Java exception đều vào đó?”**  
Không. Spring Integration chỉ publish lỗi qua error channel khi thành phần/endpoint được cấu hình hoặc hỗ trợ error publication. Một lời gọi service Java thông thường hoặc `JavaMailSender.send` trực tiếp không tự chuyển mọi exception sang channel.

**“Tại sao lỗi trên DirectChannel được ném về caller?”**  
`DirectChannel` thường invoke handler trong cùng thread gửi message. Vì vậy exception có thể lan theo stack call; nó không mặc định đi qua error channel nếu không có ranh giới bắt/publish tương ứng.

**“Tại sao lỗi ở ExecutorChannel không xuất hiện ở thread gọi send?”**  
Handler chạy ở executor thread khác. Exception không thể ném theo call stack đã trả về. Error handling phải được cấu hình phù hợp và cần một nơi lưu trạng thái để không mất thông tin khi worker chết.

**“Có nên tạo mailErrorChannel riêng thay vì dùng global errorChannel?”**  
Thường hữu ích khi mail flow cần taxonomy, retry, owner và DLQ riêng. Global channel vẫn có thể phục vụ lỗi chưa được phân loại/quan sát chung, nhưng không nên đánh đồng chính sách mail với mọi integration flow khác.

**“Poller errorChannel sẽ bắt mọi lỗi trong hệ thống?”**  
Không. Nó gắn với tác vụ poller và những lời gọi downstream nằm trong context xử lý tương ứng. Lỗi từ executor, gateway hoặc service không thuộc poller có thể cần cơ chế khác.

**“ErrorMessage payload là gì?”**  
Là một `Throwable`, thường được bọc thành `MessagingException` trong nhiều đường xử lý của Spring Messaging/Integration. Không phải payload email gốc.

**“Làm sao lấy email gốc từ ErrorMessage?”**  
Xem `MessagingException.getFailedMessage()` hoặc `ErrorMessage.getOriginalMessage()` khi có, và dùng internal work ID để truy xuất bản sao bền vững. Hai API có thể trả `null`, nhất là khi lỗi xảy ra trước khi fetch email.

**“Nếu failedMessage null thì có nên đưa vào DLQ?”**  
Không tự động tạo một inbound mail giả. Nếu lỗi thuộc IMAP connect/auth trước khi đọc được thư, xử lý như source-level incident với reconnect/backoff và alert. DLQ message-level cần một source identity/work ID thực sự.

**“Error handler nhận lỗi rồi return có nghĩa message đã xử lý thành công?”**  
Không. Nó chỉ có nghĩa exception đã được tiêu thụ ở tầng error flow. Trạng thái business phải được ghi `PROCESSED`/`RETRY`/`FAILED` rõ; không đánh dấu thành công chỉ vì error handler không throw.

**“QueueChannel có lưu dữ liệu sau khi JVM restart?”**  
Không mặc định. Cần message store bền vững hoặc broker được cấu hình durability/ack phù hợp. Tên channel hoặc việc dùng một queue trong memory không tạo cam kết durable delivery.

**“Có thể đặt tên channel là deadLetterChannel rồi coi là DLQ?”**  
Không. Nếu channel chỉ chuyển đến một handler chạy trong JVM, chưa có lưu trữ bền vững. Phải chứng minh message/metadata đã commit vào database, broker hoặc message store.

**“Có thể dùng RequestHandlerRetryAdvice thay cho database retry state?”**  
Có thể cho retry ngắn, an toàn và idempotent trong process. Nhưng advice không tự bảo đảm phục hồi sau JVM crash hoặc lưu đầy đủ attempt history. Với yêu cầu at-least-once bền vững, cần database/broker state.

**“ErrorMessageSendingRecoverer dùng để làm gì?”**  
Nó là một cơ chế recovery có thể chuyển exception sang error message/channel khi advice hết khả năng retry theo cấu hình. Không tự giải quyết durable DLQ, business idempotency hoặc ack semantics.

**“Nếu retry advice thử ba lần thì attempt_count là ba?”**  
Tùy quy ước của ứng dụng. Nếu attempt_count tăng khi worker claim một lần, ba lần retry nội bộ có thể vẫn thuộc một work claim. Cần tách `handler_attempts` và `durable_work_attempts` hoặc định nghĩa một hệ quy chiếu nhất quán.

**“Tại sao lỗi đọc MIME có thể xảy ra lại sau mỗi poll?”**  
Vì nguồn thư vẫn tồn tại, poller có thể lấy lại khi chưa có state terminal hoặc vẫn chỉ quét UNSEEN. Hãy lưu source identity, phân loại lỗi permanent, đánh dấu `FAILED`/`QUARANTINED` và tránh hot loop.

**“Chỉ mark IMAP SEEN sau khi đọc là đủ chứ?”**  
Không. Cờ SEEN không nằm trong transaction tạo ticket/nhập dữ liệu. Một mail client khác có thể thay đổi SEEN, và crash giữa flag update với business commit có thể khiến thư bị bỏ sót.

**“Nếu UIDVALIDITY đổi thì retry email cũ thế nào?”**  
Không fetch cùng số UID ở generation mới rồi giả định đó là cùng message. Dùng bản sao MIME bền vững nếu có, hoặc reconcile source với bằng chứng phù hợp; giữ lịch sử UIDVALIDITY cũ.

**“Có nên lưu nguyên MimeMessage vào DLQ?”**  
Không mặc định. Nó có thể chứa PII/attachment/malware, khó serialize an toàn và có thể phụ thuộc stream hoặc IMAP connection. Nên dùng payload reference tới snapshot bền vững có phân quyền, kèm metadata cần thiết.

**“Khi nào dùng QUARANTINED thay vì FAILED?”**  
Khi nội dung cần cô lập vì security policy, malware, MIME abuse hoặc chưa đạt yêu cầu kiểm tra an toàn. Redrive từ quarantine cần quyền/quy trình riêng, không giống sửa lỗi database.

**“SMTP MailSendException có nghĩa chắc chắn email chưa gửi?”**  
Không. Có trường hợp timeout sau DATA khiến client không biết relay đã chấp nhận hay chưa. Phải phân biệt definite failure và UNKNOWN; gửi lại có thể tạo bản trùng.

**“SMTP send thành công đã nghĩa người nhận có mail trong inbox?”**  
Chưa. Nó thường chỉ chứng minh relay SMTP đã nhận message theo quan sát của ứng dụng. Bounce/DSN và delivery feedback là giai đoạn khác.

**“Vì sao lỗi ghi DLQ cần được cảnh báo riêng?”**  
Vì nó xảy ra **ngay khi hệ thống đang cố lưu bằng chứng một lỗi khác**. Nếu tiếp tục ack nguồn dù chưa có durable disposition, message có thể mất vĩnh viễn. Cần alert và fallback rõ ràng.

**“Nếu error handler publish ErrorMessage rồi ném exception thì sao?”**  
Có nguy cơ cùng attempt được error handler khác xử lý lại, tạo retry/dead letter trùng. Chọn một đường sở hữu error và dùng unique transition/attempt ID để dedupe.

**“Có nên retry lỗi auth IMAP/SMTP liên tục không?”**  
Không. Sai credential hoặc chính sách provider sẽ không tự hết nhờ retry nhanh, thậm chí có thể khóa tài khoản. Cần sửa secret/provider config, backoff và cảnh báo.

**“Dead letter là trạng thái cuối vĩnh viễn?”**  
Nó là trạng thái dừng **tự retry**. Operator có thể redrive nếu nguyên nhân đã khắc phục và policy cho phép. Không nên tự reset trạng thái mà không audit.

**“Redrive có nên tạo một work ID mới?”**  
Tùy kiến trúc. Giữ cùng ID cho phép nối attempt history; tạo ID mới liên kết ID cũ giúp giữ record terminal bất biến. Dù chọn cách nào, business idempotency phải ngăn side effect trùng ngoài chủ đích.

**“Tại sao metrics DLQ và database đôi khi không khớp?”**  
Do thời điểm snapshot, metric counter reset, nhiều replica export gauge toàn cục hoặc lỗi collector. Xác định nguồn truth, metric freshness và aggregation đúng scope.

**“Có nên đính kèm subject/email address vào metric để dễ tìm?”**  
Không. Đây là PII và high-cardinality labels. Dùng enum lỗi/workflow/source type cho metrics; internal work ID trong log có quyền truy cập để điều tra từng record.

## 24. Checklist triển khai Error channel và dead letter flow

### Ranh giới error routing

1. Xác định mọi nguồn error: IMAP, POP3, inbound webhook, MIME parser, business handler, SMTP sender, database.
2. Biết mỗi handler đang chạy đồng bộ hay bất đồng bộ; ai bắt exception.
3. Cấu hình `mailErrorChannel` riêng khi cần mail-specific policy.
4. Gắn error channel đúng vào poller/endpoint hoặc chủ động publish khi service không thuộc integration error mechanism.
5. Không giả định exception đồng bộ tự động chuyển tới global `errorChannel`.
6. Khi có ErrorMessage, đọc `Throwable` và failed/original message **nếu có**, không mặc định non-null.
7. Giữ internal work ID/attempt ID qua mọi boundary.

### Retry và state

8. Phân biệt source-level error và message-level error.
9. Tạo source identity bền vững trước khi xử lý nghiệp vụ.
10. Với IMAP, dùng mailbox/folder/UIDVALIDITY/UID; không chỉ cờ SEEN hoặc RFC Message-ID.
11. Có `DISCOVERED`, `PROCESSING`, `RETRY`, `PROCESSED`, `FAILED` và `QUARANTINED` nếu cần.
12. Claim work item atomically với lease/fencing.
13. Lưu attempt history và mã lỗi đã chuẩn hóa.
14. Retry có backoff/jitter, deadline và max attempts.
15. Không retry permanent validation/malicious content vô hạn.
16. Với side effect bên ngoài, có idempotency key và reconciliation nếu outcome chưa rõ.

### Dead letter bền vững

17. Error flow phải lưu durable disposition, không chỉ ghi log.
18. Ghi `FAILED` và DLQ event cùng transaction nếu dùng database.
19. Với broker, cấu hình durability, routing, publish confirmation và ack/offset phù hợp.
20. Không ack/xóa source khi chưa đạt durable receipt theo hợp đồng.
21. Nếu chính DLQ storage lỗi, có secondary alert và cơ chế không mất work item.
22. Không serialize raw MIME/Throwable/password tùy tiện vào DLQ.
23. Có quyền truy cập/retention/quarantine phù hợp payload.
24. Không để ErrorMessage tự republish vào cùng channel vô hạn.

### Vận hành và redrive

25. Có metrics cho lỗi source, processing, retry, DLQ arrivals/current và tuổi backlog.
26. Có alert cho error flow persistence failures.
27. Dashboard phân biệt inbox processing, outbound SMTP và provider delivery feedback.
28. Có runbook cho auth failure, IMAP source missing, MIME invalid, SMTP UNKNOWN, DB outage.
29. Redrive cần authorization, validation payload, side-effect check, audit và rate limit.
30. Không dùng một nút `Retry all` cho cả malware/quarantine/SMTP UNKNOWN.

### Kiểm thử

31. Test ErrorMessage được route từ poller/endpoint phù hợp.
32. Test lỗi khi chưa có failedMessage thành source incident, không làm giả DLQ item.
33. Test lỗi permanent được FAILED/QUARANTINED đúng một lần.
34. Test retry đến max attempts và không có attempt vượt trần.
35. Test crash window giữa side effect và commit status.
36. Test lỗi secondary khi persist DLQ.
37. Test IMAP UIDVALIDITY, source identity duplicate và flag SEEN.
38. Test SMTP temporary/permanent/unknown bằng fake server phù hợp.
39. Test redrive giữ audit và idempotency.
40. Test metrics/log không chứa credential, MIME body, PII hoặc high-cardinality labels.

## 25. Tổng kết kiến trúc

~~~text
                  Spring Integration Mail
                            |
        +-------------------+----------------------+
        |                   |                      |
        v                   v                      v
   Inbound IMAP        Inbound webhook        Outbound mail job
        |                   |                      |
        v                   v                      v
    Discover UID       Verify event ID          Outbox claim
        |                   |                      |
        +-------------------+----------------------+
                            |
                            v
                   Durable work identity
                            |
                            v
                    Integration endpoint
                            |
                +-----------+-----------+
                |                       |
                v                       v
             SUCCESS                  EXCEPTION
                |                       |
                v                       v
         Business state commit      ErrorMessage
                |                       |
                |                       v
                |                 mailErrorChannel
                |                       |
                |                       v
                |                Error classifier
                |                       |
                |           +-----------+-----------+
                |           |           |           |
                |           v           v           v
                |         RETRY      FAILED/DLQ   UNKNOWN
                |           |           |           |
                |           v           v           v
                |        Due work    Redrive     Reconcile
                |           |           |           |
                +-----------+-----------+-----------+
                            |
                            v
                 Audit, metrics, runbooks
~~~

### Nguyên tắc cần ghi nhớ

- `errorChannel` là **tuyến truyền ErrorMessage**, không tự động là dead-letter store.
- Lỗi đồng bộ, bất đồng bộ và poller có **error publication semantics** khác nhau.
- `ErrorMessage` có payload Throwable; failed/original message **có thể vắng mặt**.
- **Lỗi kết nối mailbox** cần retry/cảnh báo ở source; **lỗi của email cụ thể** cần work ID và processing state.
- **Retry an toàn** phải xét khả năng side effect đã xảy ra và deadline của nghiệp vụ.
- **DLQ phải bền vững**, có dedupe và audit; ghi log rồi bỏ qua không phải dead letter.
- **Quarantine không tự động redrive** và phải có quyền/retention theo mức độ nhạy cảm.
- **SMTP UNKNOWN không được mù quáng gửi lại**, vì relay có thể đã nhận thư.
- **Nhận mail phải có source identity/cursor bền vững**, không phụ thuộc cờ SEEN để chứng minh đã xử lý.

## Kết luận

**Error channel và dead letter flow** trong Spring Integration Mail giúp tách đường xử lý exception khỏi luồng nghiệp vụ, nhưng chỉ đáng tin khi kết hợp với **trạng thái bền vững, phân loại lỗi, retry giới hạn, idempotency và cơ chế redrive có kiểm soát**. Một `ErrorMessage` xuất hiện trên channel là tín hiệu cần xử lý, không phải cam kết rằng email gốc đã được lưu hay nghiệp vụ đã thất bại dứt khoát.

Khi thiết kế cho môi trường sản xuất, hãy xác định rõ **ai bắt lỗi**, **message nào bị ảnh hưởng**, **lỗi xảy ra trước hay sau side effect**, **khi nào được ack nguồn**, và **điều kiện nào chứng minh trạng thái RETRY/FAILED đã commit**. Những ranh giới này biến một error handler đơn thuần thành hệ thống vận hành mail có thể quan sát, phục hồi sau crash và kiểm toán được mà không bỏ sót hoặc gửi/xử lý trùng email một cách không kiểm soát.
