# Poller, queue channel và lịch gửi

Trong **Spring Framework Mail**, `JavaMailSender` xử lý việc tạo và gửi email ra SMTP server. Khi một ứng dụng cần nhận thư theo chu kỳ, đưa thư vào hàng đợi xử lý, giới hạn tốc độ gửi hoặc chỉ gửi thông báo vào một thời điểm cụ thể, ta cần thêm một lớp điều phối. **Spring Integration Mail** cung cấp các thành phần theo mô hình *Enterprise Integration Patterns* (EIP), gồm **inbound/outbound channel adapter**, **message channel**, **poller** và **service activator**, để nối các tác vụ mail thành một luồng rõ ràng.

Một thiết kế thường gặp là:

```text
IMAP mailbox                      Ứng dụng nghiệp vụ
    |                                     |
    v                                     v
Inbound Mail Adapter               Scheduled Mail Job
    |                                     |
 Poller A                              Due-job poller
    |                                     |
    v                                     v
Inbound QueueChannel               Outbound QueueChannel
    |                                     |
 Poller B                              Poller C
    |                                     |
    v                                     v
Mail processing handler             SMTP outbound adapter
                                          |
                                          v
                                     JavaMailSender
                                          |
                                          v
                                      SMTP relay
```

Ba khái niệm rất dễ bị nhầm:

- **Poller** là cơ chế đánh thức một endpoint định kỳ để đọc một nguồn hoặc lấy message khỏi một `PollableChannel`.
- **`QueueChannel`** là nơi đệm message giữa producer và consumer; mặc định đây là **hàng đợi trong bộ nhớ**, không phải hệ thống lưu lịch gửi bền vững.
- **Lịch gửi** là quy tắc nghiệp vụ quyết định **email nào được phép gửi tại thời điểm nào**, có thể theo một lần gửi trong tương lai hoặc lịch lặp lại. Lịch này thường phải được lưu trong database/outbox nếu cần sống qua restart.

Bài học triển khai từng lớp bằng Spring Boot, Spring Integration Java DSL và Spring Mail, đồng thời giải thích backpressure, timeout, lỗi SMTP, retry, transaction, đa instance và phương pháp kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt poller đọc mailbox, poller đọc queue và scheduler quyết định thời điểm gửi.
2. Hiểu `MessageSource`, `SourcePollingChannelAdapter`, `PollableChannel`, `QueueChannel`, `PollingConsumer` và `MailSendingMessageHandler`.
3. Cấu hình một luồng outbound đơn giản dùng `QueueChannel` và `@ServiceActivator` có poller.
4. Cấu hình IMAP inbound adapter polling theo Java DSL.
5. Chọn `fixedDelay`, `fixedRate` hoặc `cron` phù hợp.
6. Dùng `maxMessagesPerPoll` và `receiveTimeout` đúng ý nghĩa.
7. Đặt capacity cho queue để tạo backpressure, không để dùng bộ nhớ vô hạn.
8. Giải thích tại sao enqueue thành công khác với SMTP accepted và delivered.
9. Thiết kế lịch gửi có `sendAt`, timezone, cancellation, rescheduling và idempotency.
10. Kết hợp transactional outbox khi yêu cầu không mất lịch sau restart.
11. Xử lý transient/permanent/unknown outcomes, không retry mù sau SMTP timeout.
12. Kiểm tra flow bằng Mockito, in-memory queue và SMTP sandbox.

## 2. Các thành phần của Spring Integration Mail

Spring Integration sử dụng cấu trúc message-centric:

```text
Message<?> 
    = payload + headers
          |
          v
MessageChannel
          |
          v
MessageHandler
```

| Thành phần | Chức năng | Ví dụ ở bài toán mail |
|---|---|---|
| `Message<?>` | Bao bọc payload và metadata | Email command, `SimpleMailMessage`, mail nhận từ IMAP |
| `MessageChannel` | Nối các endpoint | Channel cho yêu cầu gửi |
| `DirectChannel` | Chuyển message đồng bộ tới subscriber | Kiểm tra/biến đổi ngay khi producer gửi |
| `QueueChannel` | Đệm message cho consumer chủ động lấy | Hàng đợi giữa app và SMTP sender |
| `MessageSource` | Cung cấp message khi được gọi | `MailReceivingMessageSource` |
| `SourcePollingChannelAdapter` | Poll nguồn rồi chuyển sang channel | Tìm thư mới qua IMAP |
| `PollingConsumer` | Poll một `PollableChannel` rồi xử lý | Lấy email chờ khỏi queue để gửi |
| `ServiceActivator` | Kích hoạt logic xử lý message | `MailSendingMessageHandler` hoặc worker |
| `MailSendingMessageHandler` | Delegates outbound mail đến Spring `MailSender` | Gửi `MailMessage` qua SMTP |
| `TaskScheduler`/trigger | Xác định thời điểm một poller chạy | fixed delay, fixed rate, cron |

**Thành phần nào làm việc gì?** Poller không tự gửi email, QueueChannel không tự gọi SMTP và JavaMailSender không tự tạo durable scheduling. Chúng phối hợp thông qua endpoint và configuration.

### 2.1. Spring Integration Mail là module bổ sung

Thêm `spring-integration-mail` để có các mail-specific adapters. `spring-boot-starter-mail` hỗ trợ Spring Mail/Jakarta Mail gửi; `spring-integration-core` cung cấp hạ tầng message flow.

Cùng một ứng dụng có thể sử dụng cả `JavaMailSender` trong code truyền thống và outbound adapter của Spring Integration. Không nhất thiết phải chuyển mọi service sang Integration Flow chỉ vì một luồng cần poller.

### 2.2. Hai nghĩa của từ “message”

Trong chương này:

- **Spring Integration Message:** `org.springframework.messaging.Message<?>`, gồm payload + headers của pipeline.
- **Email/MIME message:** `jakarta.mail.Message` hoặc `MimeMessage`, gồm headers/body theo chuẩn email.

Một Integration Message có thể mang payload là `SimpleMailMessage`, `MimeMessage` hoặc một DTO `MailJob`. Không được nhầm headers của Spring Integration với SMTP/MIME headers nếu chưa có mapping cụ thể.

## 3. Poller thực sự làm gì?

Một poller có một **trigger** định thời và một **receive action**.

```text
Trigger fires
     |
     v
Poller invokes receive()
     |
     +--> MessageSource (IMAP inbox, JDBC source, ...)
     |
     +--> PollableChannel (QueueChannel, ...)
     |
     v
Message received?
     |
     +--> No  -> end this poll cycle
     |
     +--> Yes -> invoke downstream handler/flow
     |
     v
Repeat up to maxMessagesPerPoll, then wait for next trigger
```

Điểm quan trọng: poller chạy theo lịch **đánh thức**, không tự hiểu business field `sendAt` hoặc `dueDate` nằm trong payload.

Ví dụ:
- Poller được gọi mỗi 5 giây.
- Queue có một message đặt lịch cho tuần sau.
- Nếu message đã được đẩy vào QueueChannel và consumer không có kiểm tra thời gian, message có thể bị gửi **ngay tại lần poll kế tiếp**, không phải tuần sau.

Vì vậy **lịch gửi theo nghiệp vụ phải được áp dụng trước lúc enqueue hoặc ngay trước submission**.

### 3.1. Source polling và channel polling là hai endpoint khác nhau

**Inbound adapter**:

```text
IMAP server
    |
    v
MailReceivingMessageSource.receive()
    ^
    | Poller mỗi 10 giây
    |
    +----> Spring Integration Message
                    |
                    v
               inboundChannel
```

**Outbound consumer**:

```text
outboundQueue
    |
    v
PollingConsumer.receive()
    ^
    | Poller mỗi 1 giây
    |
    +----> MailSendingMessageHandler
                    |
                    v
               JavaMailSender
```

Một hệ thống có thể cần cả hai poller, với cấu hình khác nhau.

## 4. QueueChannel có gì khác DirectChannel?

| Tiêu chí | DirectChannel | QueueChannel |
|---|---|---|
| Cách delivery | Đẩy trực tiếp tới subscriber, thường trên caller thread | Producer đưa vào queue, consumer lấy sau |
| Có đệm messages? | Không | Có |
| Có cần consumer poller? | Thường không | Có đối với service activator/handler theo polling |
| Producer đợi SMTP send? | Có thể, nếu handler gửi đồng bộ | Thường chỉ đợi enqueue |
| Dùng bộ nhớ | Không giữ hàng đợi mặc định | Giữ messages chờ, theo capacity |
| Tính bền vững | Không phải durable queue | Mặc định **in-memory**, vẫn không durable |
| Phù hợp | Xử lý đơn giản, cần phản hồi đồng bộ | Cần tách nhịp producer/consumer, backpressure |

### 4.1. Ví dụ DirectChannel

```text
HTTP request
   |
   v
DirectChannel
   |
   v
MailSendingMessageHandler
   |
   v
SMTP
   |
   v
HTTP response (có thể phải chờ SMTP)
```

Một SMTP timeout có thể giữ request thread lâu và khiến application khó xử lý lưu lượng lớn.

### 4.2. Ví dụ QueueChannel

```text
HTTP request
   |
   v
QueueChannel(capacity=100)
   |
   +--> producer nhận kết quả enqueue
   |
Poller
   |
   v
MailSendingMessageHandler
   |
   v
SMTP
```

Producer không nhất thiết chờ mail được gửi. Nhưng nếu application restart khi còn message trong queue in-memory, các message đó có thể biến mất.

**Enqueued vào QueueChannel không tương đương “đã được lưu lịch bền vững”.**

## 5. Dependency và phiên bản ví dụ

Với Spring Boot và Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.integration:spring-integration-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chọn bộ dependency có phiên bản tương thích qua BOM/dependency management của dự án. Ví dụ sử dụng:
- Java 17+;
- Spring Framework 6+/Spring Boot 3+;
- Spring Integration Java DSL;
- Jakarta Mail (`jakarta.mail`), không phải namespace `javax.mail` cũ.

API Java DSL có thể thay đổi giữa những nhánh Spring Integration. Khi dùng phiên bản khác, cần đối chiếu chữ ký builder/poller với reference của đúng phiên bản. Bài học mô tả các contract chung và ví dụ kiểu cấu hình thông dụng.

## 6. Cấu hình SMTP trước khi đưa vào Integration Flow

Một Spring Boot application có thể dùng `spring.mail.*` để cấu hình `JavaMailSender`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
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

Cấu hình trên minh họa SMTP STARTTLS cổng 587. Thông số phải thay bằng endpoint thật được provider cấp; không commit secret.

Tầng Spring Integration **không thay thế**:
- xác thực TLS certificate/hostname;
- SMTP AUTH;
- SPF/DKIM/DMARC và verified From;
- quota/provider rate limit;
- SMTP connect/read/write timeout.

Queue/poller điều phối **khi nào và bao nhiêu message được chuyển tới sender**. Chính `JavaMailSender` chịu trách nhiệm submit MIME qua SMTP.

## 7. Ví dụ outbound tối thiểu: QueueChannel + poller + JavaMailSender

Đây là một ví dụ hoàn chỉnh về **hàng đợi trong bộ nhớ** cho email text đơn giản. Nó phù hợp làm demo hoặc luồng không yêu cầu durability.

### 7.1. Khai báo queue và service activator

```java
package com.example.mailflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OutboundMailFlowConfig {

    @Bean("outboundMailQueue")
    public PollableChannel outboundMailQueue() {
        // Bộ đệm giới hạn 100 messages trong một JVM.
        return new QueueChannel(100);
    }

    @Bean
    @ServiceActivator(
        inputChannel = "outboundMailQueue",
        poller = @Poller(
            fixedDelay = "1000",
            maxMessagesPerPoll = "5"
        )
    )
    public MessageHandler outboundMailHandler(
            JavaMailSender javaMailSender) {

        return new MailSendingMessageHandler(
            javaMailSender
        );
    }
}
```

Ý nghĩa:

- `@EnableIntegration` bật hạ tầng Spring Integration cần thiết.
- Bean `outboundMailQueue` là `PollableChannel` với capacity 100.
- `MailSendingMessageHandler` dùng sender đã cấu hình.
- Poller kích hoạt mỗi khoảng cố định theo `fixedDelay`, cố gắng xử lý tối đa 5 messages trong một poll cycle.
- Nếu queue rỗng, consumer không có gì để gửi.
- Một lần poll không có nghĩa chỉ gửi một message; số message phụ thuộc `maxMessagesPerPoll` và thời gian xử lý.

Không đặt `maxMessagesPerPoll` quá lớn nếu SMTP send chậm, vì một poll cycle có thể kéo dài và giữ scheduler/worker resources.

### 7.2. Producer tạo SimpleMailMessage rồi enqueue

```java
package com.example.mailflow;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class SimpleMailQueuePublisher {

    private final MessageChannel outboundQueue;

    public SimpleMailQueuePublisher(
        @Qualifier("outboundMailQueue")
        MessageChannel outboundQueue) {

        this.outboundQueue = outboundQueue;
    }

    public void enqueue(String recipient, String subject,
                        String plainBody) {

        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("no-reply@example.com");
        mail.setTo(recipient);
        mail.setSubject(subject);
        mail.setText(plainBody);

        boolean queued = outboundQueue.send(
            MessageBuilder.withPayload(mail).build(),
            1000L
        );

        if (!queued) {
            throw new IllegalStateException(
                "Outbound mail queue is full"
            );
        }
    }
}
```

`SimpleMailMessage` là Spring Mail message abstraction; `MailSendingMessageHandler` có thể xử lý nó và chuyển tới `MailSender`. Với HTML/multipart/attachment, nên dựng `MimeMessage` qua sender hoặc một transformer/service chuyên biệt, thay vì cố nhét HTML raw vào `SimpleMailMessage`.

### 7.3. Điều gì thực sự được bảo đảm?

Nếu `enqueue()` trả về không lỗi:
- QueueChannel đã chấp nhận Spring Integration Message theo contract.
- SMTP **chưa chắc đã được gọi**.
- SMTP **chưa chắc đã accepted**.
- Email **chưa chắc đã được giao**.
- Job **không tự sống qua restart** nếu queue vẫn in-memory.

Vì vậy API có thể trả về “đã xếp hàng”, không nên trả “đã gửi thành công” hoặc “đã tới người nhận”.

### 7.4. Một singleton sender, nhiều mail messages

`JavaMailSender` thường được Spring quản lý như bean dùng chung. Mỗi email vẫn cần nội dung/recipient riêng; không giữ một `SimpleMailMessage` mutable rồi sửa để dùng song song ở nhiều request.

## 8. Ví dụ inbound: IMAP adapter với poller

Spring Integration Mail cung cấp `ImapMailReceiver` và `MailReceivingMessageSource`; Java DSL có builder `Mail.imapInboundAdapter(...)`.

Ví dụ cấu hình hướng tới một mailbox được phép và có TLS:

```java
package com.example.mailflow;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.dsl.Mail;
import org.springframework.messaging.PollableChannel;

@Configuration
public class InboundMailFlowConfig {

    @Bean("inboundMailQueue")
    public PollableChannel inboundMailQueue() {
        return new QueueChannel(200);
    }

    @Bean
    public IntegrationFlow inboxPollingFlow(
            MailboxEndpointProperties endpoint) {

        Properties javaMailProperties = new Properties();

        javaMailProperties.put(
            "mail.imaps.ssl.checkserveridentity", "true"
        );
        javaMailProperties.put(
            "mail.imaps.connectiontimeout", "5000"
        );
        javaMailProperties.put(
            "mail.imaps.timeout", "10000"
        );

        return IntegrationFlow
            .from(
                Mail.imapInboundAdapter(
                        endpoint.storeUri()
                    )
                    .javaMailProperties(javaMailProperties)
                    .shouldDeleteMessages(false)
                    .shouldMarkMessagesAsRead(false)
                    .maxFetchSize(10),
                e -> e.poller(
                    Pollers.fixedDelay(10000)
                        .maxMessagesPerPoll(10)
                )
            )
            .channel("inboundMailQueue")
            .get();
    }
}
```

`MailboxEndpointProperties` là lớp cấu hình do ứng dụng định nghĩa, trả về một IMAPS store URI được lấy từ nơi bảo mật, **không phải API của Spring**. Một URL minh họa về mặt cấu trúc là `imaps://user:credential@host:993/INBOX`; không hardcode credential thật vào URL trong source hoặc log nó.

Các method và tên builder cần đối chiếu phiên bản Spring Integration đang dùng. Không nên copy cấu hình với URL chứa password từ tài liệu minh họa vào repository thật.

### 8.1. Hai mức cấu hình không được nhầm

Trong ví dụ inbound:

- `maxFetchSize(10)` kiểm soát số thư mà receiver cố lấy trong phạm vi khả năng/cách thực hiện của receiver.
- `maxMessagesPerPoll(10)` kiểm soát số lần `MessageSource.receive()` được poller gọi trong **một chu kỳ**.

Hai tham số không phải một quota đồng nhất và **không tự đảm bảo chính xác chỉ có 10 email bytes được tải trong mỗi 10 giây**. Cần đọc semantics của receiver, payload và downstream flow thực tế.

### 8.2. Không xóa hoặc đánh dấu SEEN khi chưa xử lý

`shouldDeleteMessages(false)` và `shouldMarkMessagesAsRead(false)` là lựa chọn thận trọng cho ingestion. Việc đánh dấu SEEN, move folder hoặc xóa thư nên tuân theo chính sách riêng sau khi dữ liệu cần thiết đã được lưu an toàn.

Với IMAP, cần theo dõi UID/UIDVALIDITY và idempotency ở storage, không chỉ dựa vào unread flag. Nếu polling kéo về cùng message nhiều lần, downstream phải có cơ chế dedupe.

### 8.3. IMAP IDLE khác polling

Nếu server hỗ trợ IDLE, `ImapIdleChannelAdapter` có thể phát message khi có thông báo mới mà **không dùng poller theo cách của polling inbound adapter**. Dù vậy vẫn cần reconnect và resync bằng UID sau restart/mất kết nối.

Không triển khai đồng thời hai adapter vào cùng mailbox theo hai đường mà không có ownership/idempotency, vì có thể xử lý trùng một email.

## 9. Dùng QueueChannel giữa inbound và processor

Có thể đặt:

```text
IMAP polling adapter
      |
      v
inboundMailQueue(capacity=200)
      |
      v
Poller mỗi 500 ms
      |
      v
TicketIngestionHandler
      |
      v
Database / durable work
```

Ví dụ consumer:

```java
package com.example.mailflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class InboundMailConsumerConfig {

    @Bean
    @ServiceActivator(
        inputChannel = "inboundMailQueue",
        poller = @Poller(
            fixedDelay = "500",
            maxMessagesPerPoll = "10"
        )
    )
    public MessageHandler inboundMailHandler(
            TicketIngestionService ingestion) {

        return message -> ingestion.accept(
            message.getPayload()
        );
    }
}
```

`TicketIngestionService` là một service do ứng dụng định nghĩa. Payload inbound có thể là một Jakarta Mail message hoặc dạng nội dung đã chuyển đổi, tùy adapter và configuration; tầng ingestion nên có contract/type conversion rõ ràng.

### 9.1. Vì sao không xử lý database trực tiếp ngay trong poller nguồn?

Có thể, nếu xử lý rất ngắn. Nhưng một bước gọi API hoặc scan attachment lâu có thể làm poller nguồn bị chiếm. QueueChannel tách nhịp producer/consumer trong process, giúp áp dụng backpressure.

Tuy nhiên, queue mặc định in-memory: khi ứng dụng crash giữa lúc nhận mail và lưu database, message trong queue có thể bị mất. Nếu mailbox vẫn giữ thư và cursor/flag chưa xác nhận thì có thể quét lại; nhưng điều đó phải được thiết kế và kiểm thử, không phải mặc định chắc chắn.

### 9.2. Không coi “đã lấy khỏi queue” là “đã xử lý xong”

Một `PollingConsumer` thường lấy message khỏi queue trước khi gọi handler. Nếu handler ném exception:
- message đã được dequeue tại channel layer;
- việc message có được trả lại hay không phụ thuộc transaction/advice và message store;
- mặc định QueueChannel in-memory không phải một broker có visibility timeout, ack/nack và DLQ như RabbitMQ.

Muốn xử lý at-least-once bền vững, cần durable storage, idempotent consumer và error recovery phù hợp.

## 10. fixedDelay, fixedRate và cron

Poller hỗ trợ những cách định thời khác nhau.

| Chế độ | Ý nghĩa | Dùng khi |
|---|---|---|
| `fixedDelay` | Khoảng nghỉ sau khi poll cycle trước kết thúc | Muốn tránh kích hoạt dồn khi một cycle chậm |
| `fixedRate` | Lịch kích hoạt theo khoảng cố định tính từ mốc của scheduler | Muốn nhịp cố định, có kiểm soát concurrency |
| `cron` | Khớp những thời điểm lịch xác định | Muốn poll vào khung giờ/ngày nhất định |
| Trigger tùy biến | Quyết định lịch qua logic riêng | Có yêu cầu phức tạp |

### 10.1. fixedDelay

Ví dụ:

```java
e -> e.poller(
    Pollers.fixedDelay(5000)
        .maxMessagesPerPoll(5)
)
```

Mô hình trực giác:

```text
00:00 poll starts
00:03 poll ends
      wait 5 seconds
00:08 next poll starts
```

Phù hợp nếu muốn đảm bảo khoảng nghỉ sau một đợt xử lý, tránh liên tiếp đè lên mailbox/provider.

### 10.2. fixedRate

```java
e -> e.poller(
    Pollers.fixedRate(5000)
        .maxMessagesPerPoll(5)
)
```

Mô hình:

```text
00:00 planned
00:05 planned
00:10 planned
00:15 planned
```

Không nên hiểu fixedRate là framework chắc chắn chạy đồng thời vô hạn nếu xử lý chậm. Kết quả thực tế còn phụ thuộc `TaskScheduler`, executor, số threads và thời gian thực hiện. Nếu một poll cycle quá dài, lịch có thể bị trễ hoặc áp dụng xử lý trigger theo scheduler semantics.

### 10.3. Cron

Ví dụ ý tưởng: lấy dữ liệu từ một nguồn vào 9 giờ sáng trong các ngày làm việc. Spring-style cron thường dùng trường giây:

```text
0 0 9 * * MON-FRI
```

Cron hữu ích cho “khi nào đánh thức endpoint”. Nhưng một cron poller đọc QueueChannel **không kiểm tra deadline riêng cho từng message**. Nếu 100 emails có `sendAt` khác nhau, không dùng một cron chung rồi giả định chúng sẽ tự được gửi đúng thời điểm.

### 10.4. Timezone

Nếu dùng lịch “9 giờ sáng”, phải xác định nó là:
- giờ UTC;
- giờ trong data center;
- giờ của tenant;
- hay giờ địa phương của người nhận.

Các lịch có timezone phải được giải theo `ZoneId`/cron trigger phù hợp, tránh phụ thuộc JVM default timezone. Đối với khu vực có DST, 9 giờ có thể đổi UTC offset theo mùa; có những thời điểm địa phương không tồn tại hoặc xuất hiện hai lần.

## 11. maxMessagesPerPoll: giới hạn số lần đọc trong một chu kỳ

`maxMessagesPerPoll` là thông số quan trọng nhưng dễ gây ngộ nhận.

Giả sử QueueChannel có 100 messages và consumer:

```java
@Poller(
    fixedDelay = "1000",
    maxMessagesPerPoll = "10"
)
```

Một chu kỳ poll có thể đọc và xử lý tối đa 10 messages (hoặc ít hơn nếu queue rỗng/lỗi). Đến chu kỳ sau mới tiếp tục đọc những message còn lại theo scheduler.

Ví dụ nếu mỗi message xử lý trung bình 200 ms:
- xử lý 10 messages đã mất khoảng 2 giây;
- `fixedDelay=1s` nghĩa còn nghỉ thêm khoảng 1 giây sau đó;
- throughput thực tế thấp hơn 10 messages/giây.

Không tính throughput chỉ bằng `maxMessagesPerPoll / fixedDelay` khi handler có thời gian xử lý đáng kể.

### 11.1. Mặc định của source và consumer có thể khác

Trong Spring Integration, `SourcePollingChannelAdapter` và `PollingConsumer` có các giá trị mặc định riêng cho `maxMessagesPerPoll`. Vì thế **nên đặt tường minh**, thay vì giả định cả hai sẽ lấy cùng số messages mỗi chu kỳ.

### 11.2. Không dùng giá trị âm bừa bãi

Một số configuration cho phép poll cho tới khi nguồn trả `null` khi dùng giới hạn âm. Nếu `receive()` luôn có message hoặc block dài, chu kỳ có thể không kết thúc đúng dự kiến, ảnh hưởng lifecycle và khả năng dừng endpoint.

Không dùng “poll vô hạn” chỉ để tăng throughput khi queue có thể liên tục được producer bơm đầy.

### 11.3. Giá trị zero không phải “đợi message”

Trong một số phiên bản Spring Integration, `maxMessagesPerPoll=0` có semantics tạm dừng việc poll `MessageSource`. Không coi zero là “lấy không giới hạn”; xác nhận behavior theo phiên bản và loại endpoint đang dùng.

## 12. receiveTimeout: đợi queue hay tạo thêm độ trễ?

`receiveTimeout` ảnh hưởng thời gian consumer đợi khi gọi `receive()` trên nguồn có khả năng block.

Ví dụ:

```text
Poller every 5 seconds
receiveTimeout = 50 ms
```

Nếu message đến ngay sau lần poll vừa trả về rỗng, nó có thể phải đợi gần 5 giây để poll kế tiếp chạy.

Ngược lại:

```text
Poller frequently
receiveTimeout = 5 seconds
```

Một consumer có thể đợi lâu hơn cho message, giảm khoảng trống phát hiện nhưng chiếm một thread đang chờ. Đây là ý tưởng long polling.

### 12.1. receiveTimeout không phải SMTP timeout

Ba thông số riêng biệt:

| Thông số | Áp dụng cho | Điều khiển |
|---|---|---|
| Poller `receiveTimeout` | `PollableChannel.receive()` | Đợi message có sẵn |
| `mail.smtp.connectiontimeout` | SMTP transport | TCP connect |
| `mail.smtp.timeout` | SMTP transport | Socket read |
| `mail.smtp.writetimeout` | SMTP transport | Socket write |

Điều chỉnh `receiveTimeout` không sửa SMTP timeout. Nếu một SMTP submit bị treo, phải xem SMTP properties, worker deadline/lease và provider behavior.

### 12.2. Đừng để nhiều long-poll consumers dùng hết scheduler threads

Một số lượng lớn pollers có `receiveTimeout` dài có thể giữ các thread của scheduler/executor chờ queue. Khi thiết kế hệ thống nhiều consumers, cần xem task scheduler pool size và chính sách concurrency; không cho mọi endpoint chiếm một thread vô thời hạn.

## 13. QueueChannel capacity và backpressure

Ví dụ:

```java
@Bean
public PollableChannel outboundMailQueue() {
    return new QueueChannel(100);
}
```

Queue chứa tối đa 100 messages trong memory theo cấu hình này. Nếu đầy, producer có thể:
- block chờ chỗ trống trong thời gian timeout;
- thất bại enqueue khi hết timeout;
- chuyển sang retry/backpressure policy.

Ví dụ:

```java
boolean accepted = queue.send(
    MessageBuilder.withPayload(mail).build(),
    250L
);

if (!accepted) {
    // Không được coi là đã enqueue thành công.
    throw new IllegalStateException("MAIL_QUEUE_FULL");
}
```

### 13.1. Vì sao queue unbounded nguy hiểm?

Khi SMTP provider chậm hoặc outage:
- producer vẫn enqueue hàng nghìn messages;
- heap tăng theo số message và attachment;
- GC pauses tăng;
- OutOfMemoryError có thể làm ứng dụng sập;
- toàn bộ in-memory queue mất khi process crash.

Queue bounded giúp lộ vấn đề sớm, nhưng **không thay thế durable outbox**.

### 13.2. Backpressure ở tầng business API

Nếu một HTTP request chỉ cần yêu cầu gửi:
1. Validate và persist một outbox row bền vững.
2. Trả `202 Accepted` sau khi commit nếu đó là contract.
3. Queue/poller phía sau xử lý với tốc độ phù hợp.
4. Giới hạn enqueue khi downstream quá tải.

Nếu chỉ enqueue vào memory rồi trả `202`, contract phải nói rõ ràng về tính không bền vững hoặc cần thay đổi kiến trúc để đảm bảo job không bị mất.

### 13.3. Một QueueChannel không phải broker liên máy

QueueChannel in-memory thuộc một JVM. Nếu ứng dụng có ba replicas:
- mỗi replica có queue riêng;
- messages không tự chia sẻ;
- một pod crash có thể mất message chưa xử lý;
- không có distributed ack, replication hay durable consumer group.

Dùng JDBC-backed channel store/broker hoặc database outbox khi yêu cầu phục hồi và phân tải đa instance.

## 14. Persistent QueueChannel và giới hạn của message store

Spring Integration có thể dùng các persistent `MessageStore`/`MessageGroupStore` implementations để backing cho một QueueChannel; một ví dụ là `JdbcChannelMessageStore`.

```text
Producer
   |
   v
QueueChannel
   |
   v
JdbcChannelMessageStore
   |
   v
Database
   |
   v
Poller -> handler
```

Điều này giúp giảm rủi ro mất queued messages khi process restart, nhưng còn phụ thuộc:
- serialization/converter của payload;
- transaction boundaries khi enqueue/dequeue;
- concurrent consumers;
- schema/index và database availability;
- handling message bị dequeue nhưng SMTP submit chưa xong;
- idempotency của downstream business operation.

**Persistent queue không làm SMTP gửi “exactly once”.** SMTP submission không thể tự động rollback nếu database transaction rollback sau khi relay đã accepted.

### 14.1. Khi nào dùng QueueChannel persistent?

Hữu ích khi ứng dụng đã dùng Spring Integration message stores và muốn pipeline được khôi phục. Với email lịch gửi tương lai có nhiều trạng thái nghiệp vụ (cancel, reschedule, expire, retry, suppression), **transactional outbox với schema riêng** thường dễ query và audit hơn việc chỉ lưu serialized Spring Messages.

### 14.2. Đừng đưa MimeMessage mutable vào persistent store không kiểm soát

Một `MimeMessage` có thể chứa state/streams/attachments khó serialize bền vững, phụ thuộc lifecycle của session hoặc dữ liệu còn tồn tại.

Nên lưu:
- job ID;
- template ID/version hoặc nội dung snapshot có bảo vệ;
- recipient đã xác thực;
- sendAt;
- timezone/business metadata;
- status/attempt count;
- file/object references có lifecycle kiểm soát.

Khi consumer xử lý, nó mới dựng một `MimeMessage` riêng.

## 15. Lịch gửi là điều kiện nghiệp vụ, không phải polling interval

Có ba dạng yêu cầu khác nhau:

| Nhu cầu | Cách tiếp cận |
|---|---|
| Gửi email ngay sau business event | Persist/enqueue rồi xử lý sớm |
| Gửi một email vào `sendAt` trong tương lai | Lưu job có due time và chỉ claim khi đã đến hạn |
| Gửi báo cáo vào mỗi 9:00 thứ Hai | Lịch lặp tạo job mới theo business key |

Ví dụ:

```text
Notification A: sendAt = 2026-11-13T09:00+07:00
Notification B: sendAt = 2026-11-15T14:30+07:00
Notification C: sendAt = 2026-12-01T08:00+07:00
```

Một consumer poll QueueChannel mỗi giây **không biết** A/B/C cần gửi vào thời điểm nào nếu logic enqueue không giữ chúng ở storage đến lúc due.

### 15.1. Mô hình đúng cho future send

```text
Create scheduled mail
       |
       v
Database outbox:
   messageKey
   sendAt
   status=PENDING
       |
       v
Due-job scheduler/poller
   WHERE sendAt <= now
       |
       v
Claim job atomically
       |
       v
Mail worker / outbound adapter
       |
       v
SMTP relay
```

Scheduler kiểm tra thời gian, channel/worker thực hiện xử lý, SMTP adapter gửi ra ngoài.

### 15.2. “Lịch gửi” không phải đảm bảo đúng từng mili giây

Nếu cấu hình poller mỗi 10 giây, một job đến hạn ở giữa hai ticks có thể bị nhận trễ tối đa gần một chu kỳ ngay cả khi hệ thống khỏe. Trong thực tế còn:
- backlog;
- provider latency;
- rate limit;
- clock skew;
- retries;
- application restart;
- transaction contention.

Vì thế cần định nghĩa SLA: “gửi không trước thời điểm đã chọn, và thường trong X phút sau thời điểm đó” thay vì hứa đúng 09:00:00.

## 16. Schema outbox cho scheduled email

Ví dụ PostgreSQL:

```sql
CREATE TABLE scheduled_email (
    message_key UUID PRIMARY KEY,
    business_event_key VARCHAR(160) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    from_identity VARCHAR(320) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    template_version VARCHAR(60) NOT NULL,
    payload_ref VARCHAR(512),
    send_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_error_code VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT scheduled_email_attempt_nonnegative
        CHECK (attempt_count >= 0),
    CONSTRAINT scheduled_email_status_valid
        CHECK (status IN (
            'PENDING',
            'SENDING',
            'RETRY_WAIT',
            'SMTP_ACCEPTED',
            'CANCELLED',
            'EXPIRED',
            'UNKNOWN',
            'DEAD_LETTER'
        ))
);

CREATE INDEX idx_scheduled_email_due
    ON scheduled_email(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE UNIQUE INDEX uq_scheduled_email_business
    ON scheduled_email(business_event_key);
```

Một sản phẩm có thể cần khóa business event gồm tenant và notification type thay vì unique toàn bộ `business_event_key`. Chọn uniqueness theo nghiệp vụ thực tế.

### 16.1. Phân biệt sendAt và nextAttemptAt

- `send_at`: thời điểm **sớm nhất** email được phép gửi theo yêu cầu nghiệp vụ.
- `next_attempt_at`: thời điểm lần gửi tiếp theo được phép thử theo retry/backoff.
- Một job eligible khi cả hai điều kiện thời gian phù hợp và status cho phép.

Ví dụ:
- `send_at` = 09:00.
- Attempt đầu lúc 09:00 trả lỗi transient.
- `next_attempt_at` = 09:05.
- Lúc 09:03 không được retry, dù `send_at` đã qua.

### 16.2. Cancellation và rescheduling

Khi người dùng hủy:
- chỉ cho hủy nếu job chưa thực hiện submission hoặc theo policy;
- dùng conditional DB update để tránh race với worker claim;
- nếu đã `SMTP_ACCEPTED` không thể “thu hồi SMTP” bằng cách xóa outbox.

Khi đổi `sendAt`:
- cập nhật đúng version/row lock;
- ghi audit actor/time/reason;
- không tạo thêm message logic nếu chỉ thay lịch;
- nếu worker đã claim, quy tắc concurrency phải xác định có thể đổi hay không.

## 17. Claim job đến hạn atomically

Nếu có nhiều workers/pods, không dùng:

```text
SELECT due jobs
FOR each job:
   UPDATE status
   send
```

mà thiếu khóa/transaction, vì hai workers có thể chọn cùng một row và gửi trùng.

Một ví dụ PostgreSQL dùng `FOR UPDATE SKIP LOCKED`:

```sql
WITH due AS (
    SELECT message_key
    FROM scheduled_email
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at, send_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE scheduled_email e
SET status = 'SENDING',
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    attempt_count = e.attempt_count + 1,
    updated_at = :now
FROM due
WHERE e.message_key = due.message_key
RETURNING e.message_key, e.attempt_count,
          e.lease_token, e.recipient;
```

Đây là skeleton cho một claim transaction ngắn. Khi claim nhiều rows, dùng lease/attempt IDs riêng hoặc thiết kế token batch có ownership rõ ràng. Nên tạo lịch sử từng attempt trong cùng transaction claim.

### 17.1. Không giữ database lock khi gọi SMTP

Quy trình phù hợp:

```text
Transaction 1: claim due rows + commit
        |
        v
SMTP network call (outside DB transaction)
        |
        v
Transaction 2: persist outcome + release lease
```

SMTP có thể chậm hàng chục giây. Nếu giữ DB row locks suốt network call, contention tăng và các transactions nghiệp vụ khác bị ảnh hưởng.

### 17.2. Fencing khi ghi outcome

```sql
UPDATE scheduled_email
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

Nếu row count bằng 0, worker không còn sở hữu lease hợp lệ; đừng ghi đè trạng thái của worker khác.

Fencing bảo vệ **database state**, nhưng không thu hồi email mà SMTP relay đã nhận. Khi lease hết hạn trong lúc network call không rõ outcome, cần reconciliation.

## 18. Scheduler tạo job và scheduler dispatch job là hai việc khác nhau

**Scheduler tạo job lặp lại**:

```text
Every weekday 09:00
    |
    v
Create a new digest job
    |
    v
Persist messageKey + sendAt
```

**Dispatcher tìm job đến hạn**:

```text
Every 1 second
    |
    v
SELECT/CLAIM due jobs
    |
    v
Submit through mail worker
```

Không trộn hai khái niệm. Một tác vụ báo cáo hàng tuần tạo **một email logic mới mỗi kỳ**, còn dispatcher xử lý những job đã được tạo.

### 18.1. Cron tạo digest hằng ngày

```java
package com.example.mailflow;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MorningDigestSchedule {

    private final ScheduledMailService scheduledMailService;

    public MorningDigestSchedule(
            ScheduledMailService scheduledMailService) {
        this.scheduledMailService = scheduledMailService;
    }

    @Scheduled(
        cron = "0 0 9 * * MON-FRI",
        zone = "Asia/Ho_Chi_Minh"
    )
    public void createDailyDigestJobs() {
        scheduledMailService.createDigestForBusinessDate();
    }
}
```

`ScheduledMailService` là application service do dự án định nghĩa, phải:
- xác định business date/timezone;
- tạo idempotency key theo ngày và loại digest;
- persist email jobs trong DB;
- không gửi ngay trong một transaction dài nếu không có chủ đích;
- có cách catch-up khi scheduler bị tắt trong thời gian chạy theo lịch.

Cần bật scheduling với `@EnableScheduling` trong cấu hình tương ứng. Một cron method ở nhiều replicas có thể chạy **trên mỗi replica**, nên unique key/distributed lock vẫn cần thiết.

### 18.2. Catch-up và missed ticks

Khi ứng dụng downtime đúng 09:00:
- không nên cho rằng `@Scheduled` tự chạy bù tất cả các kỳ bị lỡ;
- phải có policy “tạo job cho những business dates chưa được tạo” nếu cần;
- dùng unique constraint để tránh tạo trùng;
- giới hạn số kỳ catch-up để tránh gửi hàng loạt email cũ, không còn giá trị.

### 18.3. Lịch của user ở timezone khác

Lưu:
- local date/time theo ý định người dùng;
- `ZoneId` của lịch;
- thời điểm resolved sang `Instant`/UTC cho lần gửi cụ thể;
- chính sách DST ambiguous/nonexistent time;
- audit khi đổi múi giờ hoặc reschedule.

Không tính “9 giờ sáng của người dùng” bằng cách cộng cố định 7 giờ cho tất cả tenant ở mọi khu vực.

## 19. Dispatcher định kỳ cho due jobs

Một thành phần định kỳ có thể gọi service dispatch:

```java
package com.example.mailflow;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueMailDispatcher {

    private final DueMailDispatchService dispatchService;

    public DueMailDispatcher(
            DueMailDispatchService dispatchService) {
        this.dispatchService = dispatchService;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.dispatch.fixed-delay-ms:1000}"
    )
    public void dispatch() {
        dispatchService.dispatchDueBatch();
    }
}
```

Đây là một cách dùng scheduler của Spring để **đánh thức một use case**. Nếu muốn bám hoàn toàn Spring Integration, có thể tạo `MessageSource` backed by a due-job repository rồi dùng `SourcePollingChannelAdapter` với poller. Cả hai cách đều cần đúng transaction/cursor/lease semantics.

### 19.1. Scheduler không thay thế durable queue

Nếu dispatcher:
1. Claim job thành `SENDING`.
2. Enqueue job reference vào một QueueChannel **in-memory**.
3. Process crash trước khi consumer gửi.

Job có thể bị kẹt ở `SENDING`. Recovery process cần kiểm tra lease, biết có hay chưa có side effect SMTP, và chỉ retry khi outcome đã được phân loại an toàn.

Nếu không cần đệm memory, dispatcher có thể claim một job rồi gọi worker gửi trực tiếp. Cách đơn giản hơn đôi khi dễ kiểm soát atomicity/duplicate hơn.

### 19.2. Kiến trúc recommended cho email quan trọng

```text
Database scheduled_email (source of truth)
               |
               v
Due-job poller + atomic claim
               |
               v
Bounded processing worker
               |
               v
JavaMailSender / SMTP
               |
               v
Persist attempt outcome
               |
               +--> ACCEPTED
               +--> RETRY_WAIT
               +--> DEAD_LETTER
               +--> UNKNOWN
```

QueueChannel có thể dùng làm **buffer/wakeup hint** khi cần, nhưng không nên là nơi duy nhất lưu job dự kiến gửi sau nhiều giờ/ngày.

## 20. Một luồng hoàn chỉnh: Producer → Queue → Poller → SMTP

Xét use case gửi thông báo theo lịch với một message reference:

```text
POST /notifications/schedule
      |
      v
Validate recipient + template + sendAt
      |
      v
DB transaction: insert scheduled_email(PENDING)
      |
      v
HTTP 202 + messageKey
      |
      |  đến thời điểm đủ điều kiện
      v
Due-job poller
      |
      v
Claim job (SENDING + lease)
      |
      v
QueueChannel (optional, bounded)
      |
      v
PollingConsumer
      |
      v
Mail renderer -> JavaMailSender
      |
      v
SMTP relay
      |
      v
Persist submission outcome
```

### 20.1. Những ranh giới quan trọng

- HTTP trả `202` sau **DB commit**, không phải sau `QueueChannel.send(...)` nếu hợp đồng yêu cầu durable.
- Queue chứa một job reference/command, không phải nơi duy nhất lưu toàn bộ trạng thái.
- Worker phải verify job chưa bị hủy/hết hạn và còn lease trước khi submission.
- SMTP accepted không đồng nghĩa delivered; provider có thể deferred/bounced.
- Lỗi SMTP không phải cứ catch là retry ngay.
- Những side effects và state transitions cần attempt IDs để hỗ trợ audit.

### 20.2. Dùng channel tách tuyến

Một hệ thống có thể có:

```text
scheduled_email
    |
    v
Router
    |
    +--> transactionalMailQueue -> provider A sender
    |
    +--> marketingMailQueue     -> provider B sender
    |
    +--> internalAlertQueue     -> internal relay
```

Cách tách queue giúp áp dụng:
- concurrency/rate limit riêng;
- retry/backoff theo policy;
- TLS/credential/verified sender identity đúng;
- monitoring theo business category;
- suppression cho marketing.

Không gửi toàn bộ tenant và category qua một queue/sender nếu điều đó làm mất isolation hoặc vi phạm provider quota.

## 21. Lỗi, retry và errorChannel

Spring Integration hỗ trợ error handling cho message flows, nhưng một error channel **không tự biến lỗi SMTP thành retry an toàn**.

Có các tình huống:

| Kết quả | Ví dụ | Quyết định phù hợp |
|---|---|---|
| Lỗi trước khi bắt đầu submit | Validation/template lỗi | Dừng hoặc dead letter theo policy |
| SMTP transient đã xác minh | Relay trả 421/451 trước accepted | Backoff rồi retry trong ngân sách |
| SMTP permanent rejection | Invalid recipient/permission | Không retry vô hạn |
| Timeout sau DATA, không thấy response | Relay có thể đã accepted | `UNKNOWN`, reconciliation |
| SMTP accepted, delivery deferred | Provider đang tự retry | Không tạo submission mới ngay |
| Message đã được queue nhưng processor crash | Memory queue có thể mất | Dùng outbox/recovery được thiết kế |

### 21.1. Error channel dùng làm gì?

Một integration endpoint có thể phát `ErrorMessage` vào error channel theo cách được Spring Integration cấu hình. Handler lỗi có thể:
- ghi log an toàn;
- chuyển loại lỗi về domain outcome;
- phát metric/alert;
- kích hoạt workflow retry/dead-letter;
- không làm scheduler dừng im lặng.

Không chỉ viết một error handler `log.error(...)` rồi coi email đã được retry hoặc không mất việc.

### 21.2. Retry advice

Có thể áp dụng `RequestHandlerRetryAdvice` hoặc retry policy tương ứng của Spring Integration cho handler. Nó phù hợp cho lỗi **được xác định an toàn để retry** và có số lần/budget rõ ràng.

Nhưng:
- retry advice in-memory có thể mất context khi process restart;
- lỗi không rõ outcome có thể tạo duplicate;
- retry mà không delay/backoff có thể gây SMTP storm;
- successful SMTP submission không rollback được;
- không nên retry một message có link/token đã hết hạn.

Với email quan trọng, dùng durable attempt history và state machine `RETRY_WAIT`/`UNKNOWN`/`DEAD_LETTER` ở outbox; advice chỉ là một tầng bổ sung đã được định nghĩa rõ.

## 22. Transaction của poller không thể rollback SMTP

Spring Integration có thể dùng transaction advice cho polling endpoints, giúp atomicity trong một số quy trình đọc/ghi message store/database.

Nhưng:

```text
BEGIN DB TRANSACTION
  dequeue job
  send SMTP -> relay accepted
  UPDATE DB -> error
ROLLBACK DB
```

Rollback DB **không rút lại email** đã được relay nhận. Nếu queue transaction rollback làm job xuất hiện lại, lần poll tiếp theo có thể gửi trùng.

### 22.1. Những đảm bảo có thể đạt được

- Atomic insert business record + outbox job trong cùng DB transaction.
- Atomic claim + tạo attempt record.
- Atomic persist outcome + cập nhật job state.
- Unique idempotency key tránh tạo hai email logic từ một business event.
- Fencing token tránh stale worker ghi đè kết quả.

Những đảm bảo này không đồng nghĩa **exactly-once SMTP delivery**.

### 22.2. Khi kết quả không rõ

Sau SMTP DATA, nếu network đứt trước response, ứng dụng không biết upstream đã nhận chưa. Một worker mới không được resend mù chỉ vì poller đã lấy message khỏi queue/lease hết hạn.

Cần:
- ghi `UNKNOWN`;
- đối soát provider logs/API/event nếu hỗ trợ;
- dùng idempotency phía provider nếu contract thật sự hỗ trợ;
- hoặc áp dụng quyết định chấp nhận rủi ro duplicate được ghi nhận.

## 23. Concurrency và giới hạn tốc độ

Một QueueChannel poller có thể đọc nhiều messages mỗi cycle, nhưng số SMTP connections đồng thời còn phụ thuộc:
- TaskScheduler/TaskExecutor;
- số service activators/consumers;
- số application instances;
- thời gian SMTP send;
- provider quota/rate limit.

**`maxMessagesPerPoll` không phải global concurrency limiter hay token bucket.**

### 23.1. Concurrent workers cần giới hạn riêng

Ví dụ:
- Provider cho phép 5 SMTP connections đồng thời.
- 3 application pods.
- Mỗi pod có executor 5 threads.

Tổng có thể tới 15 concurrent sends, vượt provider limit. Cần điều phối quota toàn account hoặc chia hạn mức trên các pods.

### 23.2. Rate limit khác concurrency

- **Concurrency:** tối đa N submissions đang xử lý cùng lúc.
- **Rate:** tối đa M submissions mỗi giây/phút.
- **Queue capacity:** tối đa K messages đệm.
- **Retry budget:** tối đa R attempts cho một email logic.

Không dùng một tham số poller duy nhất để thay cho cả bốn.

### 23.3. Backoff và jitter khi provider outage

Nếu có 10.000 email chờ và provider outage 5 phút:
- polling quá nhanh gây retries liên tục;
- queue memory tăng;
- SMTP 4xx tăng;
- khi provider hồi phục có thể có retry storm.

Cần:
- exponential backoff + jitter;
- circuit breaker khi cần;
- provider health/route policy;
- giới hạn throughput;
- dashboard backlog;
- dead letter cho lỗi permanent/hết ngân sách.

## 24. Mailbox polling: UID và idempotency

Nếu luồng dùng IMAP inbox polling, cần lưu ý `Message` nhận từ Jakarta Mail khác email outbound.

Một email trong IMAP folder có:
- message sequence number, có thể thay đổi khi thư bị expunge;
- UID ổn định hơn trong phạm vi `folder + UIDVALIDITY`;
- flags như `SEEN`, `DELETED`;
- headers và MIME parts có thể không tin cậy.

Không dùng `messageNumber` làm khóa đồng bộ lâu dài. Trong ingestion storage, một identity hữu ích là:

```text
(mailboxAccount, folder, uidValidity, uid)
```

### 24.1. Poller có thể nhận lại cùng một email

Dù IMAP adapter giới hạn `maxFetchSize` và không đánh dấu SEEN, việc polling lại sau restart/lỗi có thể phát cùng một mail. Đây là điều bình thường nếu thiết kế at-least-once.

Downstream nên:
1. Đọc UID/metadata có thể xác định được.
2. Kiểm tra unique key trong database.
3. Persist snapshot/processing event trong transaction.
4. Chỉ cập nhật cursor/flag theo policy sau khi commit.
5. Nếu gặp lại, skip idempotently.

### 24.2. Không chuyển Message lazy-loading qua queue dài hạn

Một Jakarta Mail `Message` có thể phụ thuộc Store/Folder connection khi truy xuất body. Nếu đẩy thẳng vào queue rồi đóng mailbox connection, worker nhận sau có thể lỗi.

Nên chuyển message thành:
- DTO có headers và dữ liệu body cần thiết đã được tải;
- durable mailbox message ID/UID reference và worker biết reconnect;
- attachment reference đã được lưu và scan.

Chọn cách phù hợp với retention, resource limits và privacy policy.

## 25. Lịch gửi lặp, catch-up và DST

Bài toán “mỗi thứ Hai lúc 9:00 theo giờ khách hàng” khác “sau 10 phút”:

| Yêu cầu | Cách biểu diễn |
|---|---|
| Sau 10 phút | `Instant.now().plus(Duration.ofMinutes(10))` |
| Đúng ngày cụ thể ở một timezone | `LocalDateTime` + `ZoneId` → `Instant` |
| Mỗi thứ Hai 9:00 | Recurrence rule/cron với timezone |
| Mỗi 24 giờ kể từ lần chạy trước | Interval/Duration theo scheduler policy |

### 25.1. Đừng dùng cron để tạo trùng khi chạy nhiều pods

Một `@Scheduled(cron=...)` chạy trên mỗi application instance nếu không có cơ chế điều phối. Với 4 pods, có thể tạo 4 email digest trùng.

Giải pháp:
- unique key như `tenantId + notificationType + businessDate`;
- claim/distributed lock;
- một scheduler có ownership rõ;
- idempotent job creation.

### 25.2. Không gửi lịch đã hết hiệu lực

Ví dụ email xác minh tài khoản có token hết hạn sau 15 phút. Nếu SMTP provider lỗi một giờ, job được retry sau khi token đã hết hạn sẽ không có ích.

Cần trường:
- `expiresAt` hoặc business deadline;
- suppression/cancel status;
- max attempts;
- policy chuyển `EXPIRED` khi không còn hợp lệ.

Khi dispatch, kiểm tra deadline ngay trước attempt, không chỉ khi enqueue.

### 25.3. Biến đổi giờ địa phương với DST

Một ngày có thể:
- không có 02:30 vì đồng hồ nhảy tới 03:00;
- có 01:30 hai lần khi đồng hồ lùi.

Hệ thống phải định nghĩa policy: chọn offset nào, bỏ qua, hoặc dịch thời điểm. Với lịch gửi toàn cầu, lưu timezone chuẩn như `Europe/Berlin` thay vì hardcode offset hiện tại.

## 26. Bảo mật ở poller, channel và outbound adapter

Message flows dễ trở thành đường gửi email không kiểm soát nếu mọi service có thể đẩy recipient tùy ý vào một channel chung.

### 26.1. Xác minh trước khi enqueue

- Người gọi có quyền gửi loại email này?
- Recipient có được phép theo nghiệp vụ?
- Marketing recipient đã opt-in và chưa unsubscribe?
- Sender domain đã verified?
- Email template và URL an toàn?
- Attachment có được phép truy cập và kích thước phù hợp?
- Tất cả message fields đã được validate/escaped đúng ngữ cảnh?

Không để một Integration Message header tùy ý ghi đè `From` hoặc `To` đã được kiểm soát.

### 26.2. Tách channel theo trust boundary

Inbound email là dữ liệu **không tin cậy**. Không nối trực tiếp:

```text
IMAP incoming payload -> outbound SMTP channel
```

mà thiếu validation/authorization, nếu không attacker có thể khiến ứng dụng trở thành mail forwarder hoặc spam relay.

Nên có một service chuyển đổi có xác minh:
- mailbox account/tenant;
- sender identity;
- business rule;
- approved recipient;
- content sanitation;
- rate limit.

### 26.3. Secret và TLS

- SMTP: STARTTLS required hoặc implicit TLS đúng cổng, hostname verification.
- IMAP: IMAPS/STARTTLS bắt buộc, CA và hostname validation.
- Credentials lấy từ secret store.
- Không log raw MIME hoặc OAuth token.
- Không dùng `ssl.trust=*` trong production.
- Network egress chỉ tới endpoints được phép.

### 26.4. Email headers không phải authorization

`X-Application-Message-Key` hoặc `correlationId` giúp truy nguyên, không chứng minh caller được quyền gửi. Mọi routing và tenant identity phải được xác định từ server-side context đã xác thực.

## 27. Quan sát vận hành

Không nên chỉ có log “mail sent”.

| Metric | Ý nghĩa |
|---|---|
| `mail_queue_depth` | Số Spring Messages đang chờ trong QueueChannel |
| `mail_queue_capacity` | Capacity hiện hành |
| `mail_enqueue_rejected_total` | Số lần queue đầy/timeout |
| `mail_poller_cycle_seconds` | Thời gian mỗi poll cycle |
| `mail_poller_received_total` | Số messages lấy được từ nguồn |
| `mail_outbox_due_count` | Số scheduled emails đã đến hạn |
| `mail_schedule_lag_seconds` | Trễ từ `sendAt` đến lúc claim/submission |
| `mail_active_submissions` | Số SMTP attempts đang hoạt động |
| `mail_smtp_submit_seconds` | Độ trễ submission |
| `mail_smtp_outcomes_total` | Accepted/transient/permanent/unknown |
| `mail_retry_wait_count` | Số job chờ retry |
| `mail_dead_letter_count` | Số job dừng tự động |
| `mail_imap_fetch_errors_total` | Lỗi đọc mailbox |
| `mail_provider_rate_limited_total` | Lỗi rate limit theo provider |

### 27.1. Structured logs

```json
{
  "event": "mail.submission_attempt",
  "messageKey": "msg-1001",
  "attemptId": "att-3",
  "provider": "transactional",
  "dueAt": "2026-11-13T02:00:00Z",
  "claimedAt": "2026-11-13T02:00:02Z",
  "outcome": "SMTP_ACCEPTED",
  "durationMs": 843
}
```

Không log password, token, full email body hoặc attachment bytes. `messageKey` và `attemptId` là những định danh server-generated phục vụ hỗ trợ/đối soát.

### 27.2. Theo dõi delay thực sự

Phân biệt:

```text
scheduledAt -> dueAt -> claimedAt -> smtpAcceptedAt
```

Nếu khoảng `dueAt → claimedAt` cao, điều tra scheduler/queue/backlog. Nếu `claimedAt → smtpAcceptedAt` cao, điều tra SMTP/network/render. Nếu `smtpAcceptedAt → deliveredAt` cao, xem provider/destination mail system.

Không coi một poller hoạt động đều là bằng chứng email được giao đúng giờ.

## 28. Unit test cho QueueChannel mà không gọi SMTP

Có thể kiểm tra producer enqueue một `SimpleMailMessage` mà không cần server.

```java
package com.example.mailflow;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.messaging.Message;

class MailQueuePublisherTest {

    @Test
    void enqueuesOneMailWithCorrectContent() {
        QueueChannel queue = new QueueChannel(10);
        SimpleMailQueuePublisher publisher =
            new SimpleMailQueuePublisher(queue);

        publisher.enqueue(
            "customer@example.net",
            "Xác nhận đơn hàng",
            "Xin chào Nguyễn Thị Ánh."
        );

        Message<?> pending = queue.receive(0);

        assertThat(pending).isNotNull();
        assertThat(pending.getPayload())
            .isInstanceOf(SimpleMailMessage.class);

        SimpleMailMessage mail =
            (SimpleMailMessage) pending.getPayload();

        assertThat(mail.getTo())
            .containsExactly("customer@example.net");

        assertThat(mail.getSubject())
            .isEqualTo("Xác nhận đơn hàng");

        assertThat(mail.getText())
            .contains("Nguyễn Thị Ánh");
    }
}
```

Test này xác nhận nội dung và enqueue, **không** kiểm tra poller scheduling hoặc SMTP delivery. `queue.receive(0)` lấy message trực tiếp trong test mà không chờ một endpoint tự động.

### 28.1. Test queue capacity

```java
@Test
void rejectsWhenBoundedQueueIsFull() {
    QueueChannel queue = new QueueChannel(1);

    SimpleMailMessage first = new SimpleMailMessage();
    first.setText("A");

    SimpleMailMessage second = new SimpleMailMessage();
    second.setText("B");

    assertThat(queue.send(
        MessageBuilder.withPayload(first).build(), 0
    )).isTrue();

    assertThat(queue.send(
        MessageBuilder.withPayload(second).build(), 0
    )).isFalse();
}
```

Cần import `org.springframework.messaging.support.MessageBuilder`. Test capacity có ích để bảo vệ logic producer không coi `send(false)` là thành công.

### 28.2. Test poller scheduling khác test QueueChannel

Muốn xác minh endpoint tự poll và gửi đúng số messages mỗi cycle, cần test Spring Integration context với test poller/scheduler. Một unit test đọc QueueChannel trực tiếp không chứng minh `@Poller` được kích hoạt.

## 29. Integration test với SMTP test server

Dùng SMTP sandbox như GreenMail/Mailpit hoặc test SMTP server phù hợp để kiểm tra Spring Integration outbound flow.

Các trường hợp:
1. Đẩy một `SimpleMailMessage` vào QueueChannel.
2. Poller chạy và `MailSendingMessageHandler` submit.
3. SMTP server test nhận đúng một email.
4. Kiểm tra recipients, subject và body.
5. Queue rỗng sau khi xử lý thành công.
6. Tạo lỗi SMTP trước DATA rồi kiểm tra error handling/retry.
7. Test rate limit và timeout bằng server có khả năng fault injection.
8. Test application restart cùng durable outbox, không chỉ queue memory.

### 29.1. Không dùng Thread.sleep tùy ý

Một test asynchronous cần:
- trigger/poller kiểm soát được nếu có thể;
- latch/barrier hoặc condition assertion có timeout giới hạn;
- test clock cho `sendAt` và `nextAttemptAt`;
- bounded waits thay vì nhiều `Thread.sleep`;
- isolation cho mỗi test và cleanup.

Một bài test “chờ 10 giây rồi hy vọng có mail” dễ flaky và làm CI chậm. Cần assert điều kiện có thật, không phụ thuộc may rủi của scheduler.

### 29.2. Test message deadline bằng Clock.fixed

Giả sử một job có `sendAt` ở T+10 phút:
- T: chưa eligible, dispatch trả 0.
- T+9m59s: vẫn chưa eligible.
- T+10m: claim được.
- SMTP accepted: status cập nhật.
- Chạy dispatch lại: không gửi trùng.

Unit test có thể kiểm tra due predicate thuần; integration test dùng PostgreSQL/Testcontainers để xác minh SQL comparison và atomic claim.

### 29.3. Test restart

Với outbox bền vững:
1. Persist job future-dated.
2. Restart application hoặc tạo worker context mới trên cùng DB.
3. Tiến test clock tới hạn.
4. Chạy due-job polling.
5. Verify job vẫn còn và được xử lý.

Nếu chỉ dùng QueueChannel in-memory, test sẽ cho thấy jobs có thể mất sau khi queue được tạo lại. Đây là lý do không dùng memory queue làm scheduling storage cho thông báo quan trọng.

## 30. Ma trận lỗi và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Gửi ngay dù đã đặt lịch tuần sau | Đẩy sẵn vào QueueChannel, consumer poll không kiểm tra due | Lưu `sendAt` trong durable outbox, chỉ claim khi đến hạn |
| Poller không chạy | Endpoint chưa startup, chưa bật integration/scheduling hoặc thiếu poller cho pollable channel | Kiểm tra endpoint lifecycle và wiring |
| Queue đầy, producer treo | Capacity thấp, send timeout cao, SMTP chậm | Backpressure, bounded wait, durable storage |
| Memory tăng liên tục | Queue không giới hạn, attachments lớn | Bounded queue, giới hạn bytes/attachments |
| Email mất sau restart | QueueChannel in-memory | Persistent store/outbox và recovery |
| Cùng email gửi hai lần ở nhiều pods | Không atomic claim/idempotency | Unique business key, lease, fencing |
| maxMessagesPerPoll=5 nhưng xử lý rất chậm | SMTP call chậm, poll cycle kéo dài | Đo duration, giới hạn work, rate/concurrency |
| Polling có nhưng không nhận thư mới | Sai IMAP credentials/folder/search policy | Kiểm tra IMAP adapter và auth/TLS |
| Mail từ IMAP bị xử lý trùng | Dựa vào SEEN/message number | UID + UIDVALIDITY, DB unique key |
| SMTP exception làm message biến mất | Message đã dequeue khỏi memory, không durable recovery | Persist job trước submission, error/retry |
| SMTP timeout rồi gửi lại ngay | Không phân biệt UNKNOWN outcome | Reconciliation, không retry mù |
| Cron chạy 3 lần | 3 application replicas đều trigger | Distributed ownership/idempotency |
| Báo cáo ngày hôm qua bị gửi sau 2 tuần | Không có expiration/catch-up policy | Deadline/expiry và missed-run rules |
| Lịch gửi sai giờ | Dùng timezone máy hoặc offset cố định | Lưu ZoneId và giải quyết DST |
| Provider báo accepted nhưng chưa có inbox | Nhầm SMTP submit với delivery | Theo dõi provider delivery events |
| Long poller khiến scheduler không chạy endpoint khác | receiveTimeout dài và pool quá ít threads | Pool sizing, bounded waits |
| Đọc mail từ QueueChannel nhưng handler không nhận | Sai tên channel/consumer chưa gắn poller | Khai báo bean và endpoint đúng |
| Integration Message chứa headers nguy hiểm | Tin untrusted headers để set recipient/From | Authorize/validate tại boundary |
| Error channel chỉ log mà không xử lý job | Thiếu durable failure state | Outbox retry/dead letter/reconciliation |
| Test pass nhưng production TLS fail | Test server không có TLS đúng mode | Thêm integration test cert/hostname |
| Job CANCELLED vẫn gửi | Race giữa cancel và worker claim | Conditional update, check before send |

## 31. Checklist triển khai

### 31.1. Poller

- [ ] Xác định poller đọc nguồn hay poller đọc QueueChannel.
- [ ] Chọn `fixedDelay`, `fixedRate` hoặc cron có lý do.
- [ ] Cấu hình `maxMessagesPerPoll` tường minh theo throughput.
- [ ] Cấu hình `receiveTimeout` phù hợp resource/thread budget.
- [ ] Đo poll cycle duration và error rate.
- [ ] Không tạo poll cycle không kết thúc vì unbounded receive.
- [ ] Kiểm soát startup/shutdown và error channel.
- [ ] Không để nhiều pods cùng xử lý một mailbox/job khi không có ownership.

### 31.2. QueueChannel

- [ ] Capacity hữu hạn nếu in-memory.
- [ ] Producer xử lý queue full/timeout.
- [ ] Không dùng queue memory làm nguồn duy nhất cho future mail.
- [ ] Không chia sẻ mutable MIME giữa threads.
- [ ] Nếu persistent channel store, test serialization/transaction/recovery.
- [ ] Theo dõi depth/backlog/oldest age.
- [ ] Phân biệt dequeue với business processing success.

### 31.3. Lịch gửi

- [ ] Lưu `sendAt` và timezone đúng.
- [ ] Thêm unique business/idempotency key.
- [ ] Claim job atomically theo due predicate.
- [ ] Có cancellation/reschedule/expiration rules.
- [ ] Có max attempts/backoff/jitter và dead letter.
- [ ] `UNKNOWN` được reconcile, không tự resend.
- [ ] Không hứa chính xác tới mili giây nếu polling/backlog/provider có độ trễ.
- [ ] Kiểm soát catch-up sau downtime.
- [ ] Cron nhiều replicas không tạo job trùng.

### 31.4. Mail security

- [ ] SMTP TLS/hostname verification và credential an toàn.
- [ ] IMAP TLS/permission theo provider nếu có inbound.
- [ ] From domain và recipient đã được cho phép.
- [ ] Marketing suppression được thực thi trước routing.
- [ ] Không để email inbound mở relay gửi email outbound tùy ý.
- [ ] Không log raw MIME/secrets.
- [ ] Attachment/MIME parser có giới hạn dữ liệu và xử lý không tin cậy.

### 31.5. Tests

- [ ] Unit test producer/queue capacity.
- [ ] Unit test due-time/recurrence/timezone.
- [ ] Integration test poller/handler với SMTP sandbox.
- [ ] Integration test outbox PostgreSQL claim/concurrency/restart.
- [ ] Test transient/permanent/UNKNOWN outcomes.
- [ ] Test queue full, cancellation race và missed schedule.
- [ ] Test IMAP UID/idempotency nếu dùng inbound.
- [ ] Test deployment nhiều replicas theo policy ownership.

## 32. Bài tập thực hành

### Bài 1 — Vẽ luồng

Phân biệt ba việc trong sơ đồ: IMAP source polling, QueueChannel polling consumer, scheduled email due-job dispatch. Chỉ ra nơi email được xem là `QUEUED` và nơi upstream SMTP accepted.

### Bài 2 — Outbound QueueChannel

Tạo `QueueChannel(20)` và `@ServiceActivator` dùng `MailSendingMessageHandler` với poller 1 giây, tối đa 5 messages/poll. Dùng SMTP sandbox, không gửi Internet.

### Bài 3 — Backpressure

Dùng `QueueChannel(1)`, producer gửi hai messages với timeout 0. Xác minh lần thứ hai trả false và API không báo enqueue thành công.

### Bài 4 — fixedDelay và fixedRate

Một handler mất 2 giây, poller interval 1 giây. Phân tích nhịp thực tế của fixedDelay và fixedRate, kể cả giới hạn TaskScheduler.

### Bài 5 — maxMessagesPerPoll

Queue có 25 messages. Consumer xử lý tối đa 5/poll, fixedDelay 2 giây. Xác định số poll cycles tối thiểu nếu không có lỗi và lý do tổng thời gian còn phụ thuộc handler latency.

### Bài 6 — receiveTimeout

So sánh poller 5 giây + receiveTimeout 50 ms với poller dày hơn + receiveTimeout dài. Phân tích latency khi một message đến ngay sau poll rỗng.

### Bài 7 — IMAP inbound adapter

Tạo flow `Mail.imapInboundAdapter(...)` với `shouldDeleteMessages(false)`, `shouldMarkMessagesAsRead(false)`. Đẩy vào QueueChannel và test bằng IMAP sandbox.

### Bài 8 — Không dùng SEEN làm ACK

Tạo hai lần poll cùng một IMAP message; dùng unique `(mailbox,folder,uidValidity,uid)` để chứng minh chỉ một ticket được tạo.

### Bài 9 — Gửi email vào tương lai

Nhận `sendAt` bằng một Instant. Persist `scheduled_email`, poll WHERE `sendAt<=now` và không enqueue trước hạn.

### Bài 10 — Timezone

User ở `Europe/Berlin` muốn nhận mail mỗi thứ Hai 09:00. Thiết kế cách lưu ZoneId và xử lý DST để lịch không bị lệch một giờ theo mùa.

### Bài 11 — Daily digest

Dùng cron tạo job mỗi ngày làm việc, unique `(tenant,date,notificationType)`. Chạy hai replicas rồi chứng minh không tạo email logic trùng.

### Bài 12 — Missed run

Ứng dụng ngừng 3 ngày, sau đó khởi động. Thiết kế catch-up policy: kỳ nào cần gửi bù, kỳ nào đã quá hạn và cần bỏ qua.

### Bài 13 — Atomic claim

Hai workers cùng tìm jobs tới hạn trong PostgreSQL. Dùng `FOR UPDATE SKIP LOCKED`, lease token và unique attempt để chỉ một worker claim một job.

### Bài 14 — Error channel

Cho outbound handler ném SMTP exception giả lập. Định nghĩa cách chuyển exception thành durable state thay vì chỉ ghi log.

### Bài 15 — Unknown outcome

Giả lập kết nối mất sau DATA. Test job `UNKNOWN` và không tự enqueue cùng message qua provider khác.

### Bài 16 — Retry backoff

Thiết kế maxAttempts=3, exponential backoff và deadline. Test với `Clock.fixed`/mutable clock, không dùng `Thread.sleep`.

### Bài 17 — Queue persistent

So sánh `QueueChannel` in-memory với JDBC-backed channel store và outbox schema chuyên dụng. Liệt kê những lỗi vẫn có thể xảy ra sau SMTP accepted.

### Bài 18 — Cancellation race

User hủy email đúng lúc worker claim. Thiết kế conditional transaction để xác định hủy có thành công không, không có trạng thái nói CANCELLED nhưng SMTP vẫn được submit không kiểm soát.

### Bài 19 — SMTP sandbox integration

Đẩy một email từ QueueChannel qua poller tới `MailSendingMessageHandler` và SMTP test server. Xác nhận recipient/subject/body; không coi điều này là bằng chứng email delivered ngoài Internet.

### Bài 20 — Monitoring

Thiết kế dashboard cho queue depth, poll duration, scheduling lag, SMTP submission latency, retries, dead letter và UNKNOWN. Đề xuất alert khi backlog vượt SLA.

## 33. Tài liệu tham khảo

Để đối chiếu cấu hình theo phiên bản đang triển khai, xem tài liệu chính thức của Spring:

- Spring Integration — Mail Support: https://docs.spring.io/spring-integration/reference/mail.html
- Spring Integration — Message Endpoints và poller: https://docs.spring.io/spring-integration/reference/endpoint.html
- Spring Integration — Message Channels: https://docs.spring.io/spring-integration/reference/channel/configuration.html
- Spring Integration — Java DSL Message Channels: https://docs.spring.io/spring-integration/reference/dsl/java-channels.html

Các mẫu trong bài là cấu hình tham khảo; khi áp dụng vào dự án thật phải dùng API và dependency versions tương thích, SMTP/IMAP endpoints được phê duyệt và cơ chế lưu trạng thái phù hợp yêu cầu nghiệp vụ.

## 34. Tổng kết

**Poller, QueueChannel và lịch gửi** giải quyết ba bài toán khác nhau trong Spring Integration Mail:

1. **Poller** định thời việc gọi `MessageSource.receive()` hoặc `PollableChannel.receive()`; nó không tự hiểu thời điểm gửi của một email nghiệp vụ.
2. **QueueChannel** tách producer khỏi consumer và tạo backpressure nhưng mặc định là hàng đợi **trong bộ nhớ**, không đảm bảo email sống qua restart.
3. **MailSendingMessageHandler** là outbound adapter sử dụng Spring `JavaMailSender`; enqueue vào channel không phải SMTP accepted, và SMTP accepted không phải delivered.
4. `fixedDelay`, `fixedRate`, cron, `maxMessagesPerPoll` và `receiveTimeout` kiểm soát nhịp và số lần receive, **không thay thế global rate limit hoặc concurrency control**.
5. Với **gửi email vào tương lai**, lưu `sendAt` cùng trạng thái trong database/outbox và chỉ atomic claim khi đến hạn; dùng polling như cơ chế đánh thức.
6. Với **lịch lặp**, scheduler tạo email jobs có business idempotency key; dispatcher riêng tìm và xử lý job đến hạn.
7. **Backpressure** cần queue capacity, worker concurrency/rate limits, retry/backoff và observability; không để SMTP outage khiến hàng đợi memory tăng vô hạn.
8. Với email quan trọng, lưu **outbox, attempt history, lease, retry, dead letter và trạng thái UNKNOWN** để xử lý restart, timeout, kết quả không rõ và nguy cơ gửi trùng.
9. Với **IMAP inbound**, kết hợp poller, UID/UIDVALIDITY và idempotency; không dùng `SEEN` hoặc queue dequeue làm ACK nghiệp vụ.
10. Unit tests kiểm tra queue/logic thời gian; integration tests kiểm tra poller với SMTP sandbox và durable persistence trong database thật.

Khi phân định rõ **lịch đánh thức, hàng đợi đệm và thời điểm email được phép gửi**, bạn có thể thiết kế luồng Spring Integration Mail dễ quan sát, an toàn khi quá tải, hạn chế email trùng và phục hồi được sau sự cố mà không nhầm việc xếp hàng với việc giao thư thành công.
