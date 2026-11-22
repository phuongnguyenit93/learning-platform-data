# Bảo toàn correlation ID qua các lớp gửi mail

Một email trong ứng dụng Spring Framework Mail có thể đi qua nhiều lớp trước khi được gửi: HTTP controller, business service, domain event, template renderer, hàng đợi, worker, `JavaMailSender`, máy chủ SMTP và cuối cùng là webhook báo trạng thái từ nhà cung cấp. Nếu mỗi lớp chỉ ghi log riêng mà không có định danh liên kết, khi một email bị trễ hoặc thất bại rất khó trả lời những câu hỏi tưởng chừng đơn giản:

- Request hoặc sự kiện nghiệp vụ nào đã tạo yêu cầu gửi email?
- Email được tạo một lần hay đã bị submit nhiều lần?
- Tác vụ dừng ở lớp template, queue, worker, kết nối SMTP hay hệ thống tiếp nhận?
- Log từ một worker chạy vài phút sau request ban đầu có thuộc cùng quá trình không?
- Sự kiện delivery/bounce trả về từ provider có liên quan tới email nào?
- Một lỗi `MailAuthenticationException` hoặc `MailSendException` ảnh hưởng tới yêu cầu nào?

**Correlation ID** là mã dùng để nối các log và bản ghi liên quan tới cùng một luồng công việc. Để giữ được mã đó qua quá trình gửi mail, cần truyền nó **như dữ liệu rõ ràng** qua ranh giới lớp, thread, process và message broker; sau đó đưa vào logging context như MDC để quan sát thuận tiện. Chỉ dựa vào một biến thread-local sẽ không đủ khi hệ thống gửi bất đồng bộ.

Bài học này hướng dẫn cách thiết kế định danh, tạo và xác thực correlation ID, truyền qua Spring MVC và `@Async`, lưu trong queue/outbox, gắn với kết quả SMTP và webhook, đồng thời tránh rò rỉ dữ liệu hay nhầm correlation ID với `Message-ID` của email.

## 1. Correlation ID là gì và giải quyết vấn đề nào?

Giả sử người dùng xác nhận đơn hàng và ứng dụng gửi email thông báo. Trong môi trường nhiều instance, log có thể phân tán như sau:

```text
HTTP service:       Order confirmed
Notification layer: Mail request created
Queue consumer:     Processing mail job
Template renderer:  Rendered order-confirmation/v3
SMTP adapter:       SMTP submission failed
```

Nếu không có khóa liên kết, rất khó biết năm log này có cùng nói về một email hay không.

Khi có correlation ID:

```text
correlationId=corr-63de orderId=ORD-401
    HTTP: Order confirmed

correlationId=corr-63de notificationId=notif-918
    Notification: Mail request created

correlationId=corr-63de notificationId=notif-918
    Worker: Processing mail job

correlationId=corr-63de notificationId=notif-918
    Renderer: Template rendered

correlationId=corr-63de notificationId=notif-918 attemptId=try-2
    SMTP: Authentication failed
```

Một truy vấn log theo `correlationId=corr-63de` có thể dựng lại luồng xử lý. Truy vấn theo `notificationId=notif-918` thu hẹp tới một thông báo cụ thể; theo `attemptId=try-2` thu hẹp tới một lần thử gửi.

**Correlation ID giúp chẩn đoán; nó không phải một cơ chế xác thực, chống gửi trùng hay bảo đảm phân phát.** Nếu cần những tính chất đó, ứng dụng phải có idempotency, lưu trạng thái bền vững và quy tắc truy cập riêng.

## 2. Phân biệt các loại ID trong hệ thống gửi mail

Nhiều loại định danh cùng xuất hiện trong một chuỗi gửi email nhưng có ý nghĩa khác nhau.

| Định danh | Phạm vi | Mục đích |
|---|---|---|
| `correlationId` | Một luồng nghiệp vụ/yêu cầu liên quan | Liên kết log và các bước xử lý qua lớp/thread/process. |
| `requestId` | Một HTTP request cụ thể | Chẩn đoán một lần gọi API. |
| `traceId` | Một distributed trace | Theo dõi span và độ trễ giữa các thành phần khi có tracing. |
| `eventId` | Một domain event | Nhận diện một sự kiện nghiệp vụ đã phát ra. |
| `notificationId` | Một thông báo logic | Nhận diện email được yêu cầu gửi cho một recipient. |
| `attemptId` | Một lần thử gửi | Phân biệt retry thứ nhất, thứ hai, thứ ba. |
| `idempotencyKey` | Một thao tác cần chống submit trùng | Giúp tránh tạo nhiều notification logic cho cùng yêu cầu. |
| `Message-ID` | Header RFC 5322 của email | Định danh Internet message; có thể được dùng để threading/chẩn đoán. |
| `providerMessageId` | Hệ thống nhà cung cấp email | Tra cứu submission/delivery/bounce phía provider. |

Một đơn hàng có thể tạo email cho khách hàng, người bán và bộ phận vận hành. Chúng có thể **chia sẻ correlation ID** nhưng phải có **notification ID riêng**.

Ví dụ:

```text
correlationId = corr-order-401
eventId       = event-401-confirmed

    +-- notificationId = notif-customer-401
    |       recipient = customer
    |       attemptId = try-customer-1
    |
    +-- notificationId = notif-seller-401
    |       recipient = seller
    |       attemptId = try-seller-1
    |
    +-- notificationId = notif-ops-401
            recipient = operations
            attemptId = try-ops-1
```

Nếu chỉ có một correlation ID mà không có notification ID, không thể phân biệt rõ ba email. Ngược lại, nếu mỗi layer tạo correlation ID mới mà không giữ mã gốc, log bị đứt đoạn.

### Correlation ID khác Message-ID như thế nào?

`Message-ID` có dạng header MIME, ví dụ:

```text
Message-ID: <c4b7e13d.20261112@mailer.example.org>
```

Nó thuộc email thực tế. SMTP server hoặc email provider có thể tạo, giữ nguyên hoặc thay đổi những identifier khác khi xử lý. `Message-ID` không phải ID của HTTP request và không đảm bảo được trả lại trong mọi webhook.

**Không thay thế correlation ID bằng Message-ID.** Hãy giữ ánh xạ giữa correlation ID, notification ID, attempt ID, Message-ID nếu có và provider message ID trong bản ghi gửi mail.

## 3. Chọn phạm vi và thời điểm tạo correlation ID

Một chính sách dễ vận hành:

1. Khi HTTP request đi vào ứng dụng, tạo hoặc nhận một correlation ID đã được kiểm tra.
2. Nếu xử lý bắt đầu từ scheduler, broker, CLI hoặc domain event không có HTTP request, tạo correlation ID ở điểm vào đó.
3. Dùng cùng correlation ID xuyên suốt luồng nghiệp vụ liên quan.
4. Tạo notification ID riêng cho từng email logic.
5. Tạo attempt ID mới cho mỗi lần gọi SMTP, nhưng giữ nguyên notification ID và correlation ID trong các lần retry.

Ví dụ:

```text
HTTP request corr-A
  └── Order created
      └── Mail request notif-X
          ├── Attempt 1 try-X1: SMTP timeout
          └── Attempt 2 try-X2: SMTP accepted
```

Log của cả hai attempt cần cùng `corr-A` và `notif-X`, không tự động thay correlation ID ở lần retry thứ hai.

### Dùng UUID hoặc ULID?

Có thể dùng UUID ngẫu nhiên:

```java
String correlationId = UUID.randomUUID().toString();
```

ULID hoặc các ID tương đương cũng có thể phù hợp nếu hệ thống đã chọn chuẩn đó. Điều quan trọng hơn kiểu mã là:

- Đủ khó trùng trong phạm vi hệ thống.
- Không chứa mật khẩu, email, số điện thoại hoặc dữ liệu cá nhân.
- Có độ dài giới hạn.
- Có thể validate trước khi dùng.
- Được tạo một lần ở entry point rồi truyền tiếp.

Không nên tạo correlation ID bằng cách nối trực tiếp địa chỉ email và timestamp. Cách này rò rỉ dữ liệu và có thể không đảm bảo uniqueness.

## 4. Nhận correlation ID từ HTTP request một cách an toàn

Một số hệ thống nhận mã từ header `X-Correlation-ID` hoặc gateway. Header từ client có thể bị giả mạo, quá dài hoặc chứa ký tự xuống dòng, vì vậy cần chính sách tin cậy rõ ràng.

Có hai cách chính:

- **Tự sinh ID nội bộ:** bỏ qua ID do client gửi; an toàn và đơn giản.
- **Chấp nhận ID từ gateway tin cậy:** gateway xác thực/chuẩn hóa header; ứng dụng vẫn validate cấu trúc và giới hạn độ dài.

Không nên nhận bất kỳ chuỗi nào từ Internet rồi đưa thẳng vào log hoặc MIME header.

Ví dụ filter Spring MVC:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String incoming = request.getHeader(HEADER);

        String id = incoming != null
                && SAFE_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        String previous = MDC.get("correlationId");

        try {
            request.setAttribute(ATTRIBUTE, id);
            response.setHeader(HEADER, id);
            MDC.put("correlationId", id);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    }
}
```

Các điểm đáng chú ý:

- `OncePerRequestFilter` phù hợp với xử lý servlet request.
- Regex và độ dài giới hạn tránh nhận header tùy ý.
- `request.setAttribute(...)` đưa ID vào request context.
- Response header giúp client báo lỗi kèm ID khi liên hệ hỗ trợ.
- `MDC.put(...)` giúp log trong cùng thread có ID.
- Khối `finally` khôi phục MDC khi thread được trả về pool.

Ví dụ này không biến header thành nguồn đáng tin cậy. Nếu hệ thống có ranh giới bảo mật rõ, có thể **luôn tạo internal correlation ID** và lưu external request ID trong một trường khác, sau đó chỉ nối chúng ở hệ thống có quyền phù hợp.

### Với async dispatch của Servlet

Các cơ chế async dispatch có thể sử dụng thread khác hoặc làm filter chạy ở những dispatch khác nhau. Không nên giả định MDC từ servlet thread luôn có sẵn ở thread bất đồng bộ. Dữ liệu correlation ID cần được chuyển rõ vào command/event, hoặc được instrument bởi thư viện tracing tương ứng.

## 5. MDC là gì và vì sao không đủ để bảo toàn ID?

**MDC** (*Mapped Diagnostic Context*) là cơ chế của logging framework như SLF4J/Logback cho phép gắn các cặp key-value vào context của thread hiện tại.

Ví dụ:

```java
MDC.put("correlationId", id);

logger.info("Preparing notification");
```

Logback có thể in correlation ID trong pattern:

```xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>
        %d{ISO8601} %-5level [%thread]
        correlationId=%X{correlationId:-missing}
        %logger - %msg%n
      </pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

MDC rất hữu ích cho log nhưng thường dựa trên **thread-local state**. Khi chuyển sang `@Async`, thread pool, Kafka/RabbitMQ consumer hoặc một process khác, MDC hiện tại **không tự động trở thành dữ liệu của job**.

Có hai nguy cơ:

1. **Mất ID:** worker thread không có MDC nên log `correlationId=missing`.
2. **Dính ID cũ:** thread pool tái sử dụng thread có MDC chưa được dọn, khiến log của job B mang ID từ job A.

Vì vậy, nguyên tắc là: **correlation ID sống trong dữ liệu của yêu cầu gửi; MDC chỉ là biểu diễn tạm thời phục vụ logging.**

## 6. Truyền correlation ID qua service và message builder

Thay vì cho mọi lớp phụ thuộc `MDC.get("correlationId")`, hãy định nghĩa một command có ID rõ ràng.

Ví dụ Java record:

```java
import java.util.Locale;

public record MailRequest(
        String correlationId,
        String notificationId,
        String eventId,
        String recipient,
        String templateKey,
        String templateVersion,
        Locale locale,
        String orderNumber
) {
}
```

Khi tạo request:

```java
MailRequest mailRequest = new MailRequest(
        correlationId,
        UUID.randomUUID().toString(),
        orderEvent.id(),
        customer.email(),
        "order-confirmation",
        "v3",
        customer.mailLocale(),
        order.number()
);
```

Service truyền cùng object hoặc các trường ID cần thiết:

```java
public void submit(MailRequest request) {
    log.info(
            "Mail request accepted, notificationId={}, template={}",
            request.notificationId(),
            request.templateKey()
    );

    mailQueue.publish(request);
}
```

Log có thể sử dụng MDC, nhưng bản thân `MailRequest` giữ ID để chuyển tới nơi khác.

### Tách dữ liệu nghiệp vụ khỏi logging metadata

`correlationId` và `notificationId` là metadata vận hành, còn `recipient`, `templateKey`, `locale` và payload là dữ liệu dùng để render email. Không dùng correlation ID làm mã đơn hàng, mã xác minh, ID người dùng hay khóa xác thực.

Với hệ thống nhiều lớp, có thể tạo một kiểu riêng:

```java
public record MailDiagnostics(
        String correlationId,
        String notificationId,
        String eventId
) {
}
```

Sau đó đưa `MailDiagnostics` vào envelope của command. Cách này làm rõ metadata được truyền xuyên suốt nhưng không bắt mọi domain entity phải chứa các trường của mail transport.

## 7. Bảo toàn MDC qua @Async bằng TaskDecorator

Khi dùng Spring `@Async("mailExecutor")`, lời gọi được chuyển sang thread của `ThreadPoolTaskExecutor`. Một cách phổ biến để sao chép logging context là `TaskDecorator`.

Ví dụ:

```java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submittingThreadContext =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousWorkerContext =
                    MDC.getCopyOfContextMap();

            try {
                if (submittingThreadContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittingThreadContext);
                }

                task.run();
            } finally {
                if (previousWorkerContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousWorkerContext);
                }
            }
        };
    }
}
```

Cấu hình executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setTaskDecorator(new MdcTaskDecorator());

        return executor;
    }
}
```

Nếu request thread có `MDC["correlationId"]` khi submit, decorator chụp bản sao map đó. Khi job chạy, worker thread có context tương ứng và khôi phục context trước đó trong `finally`.

### Hai điều cần nhớ

**Thứ nhất:** decorator chỉ hỗ trợ những task đi qua executor đã cấu hình. Nếu một component dùng `new Thread(...)`, `CompletableFuture.supplyAsync(...)` không chỉ định executor, hoặc một executor khác, MDC có thể không được truyền.

**Thứ hai:** decorator chỉ giữ **logging context tại thời điểm submit**. Nó không lưu công việc bền vững, không tự truyền context qua broker/network, và không có tác dụng nếu job được phát sinh từ process khác.

Do đó, vẫn phải giữ correlation ID trong `MailRequest` hoặc bản ghi outbox.

### Khi @Async thất bại

`@Async` được xử lý qua Spring proxy; gọi nội bộ một phương thức async từ cùng instance thường không chuyển thread như kỳ vọng. Exception từ phương thức async trả `void` cũng không tự quay lại caller. Những vấn đề này ảnh hưởng khả năng chẩn đoán; cần cơ chế xử lý kết quả/exception rõ ràng.

## 8. Thiết lập logging context ngay tại ranh giới worker

Ngay cả khi đã có `TaskDecorator`, worker nhận job từ broker hoặc database vẫn nên dùng ID **trong payload/record** để thiết lập MDC.

Một helper có thể khôi phục đúng trạng thái trước đó:

```java
import java.util.Map;
import org.slf4j.MDC;

public final class MailLogContext implements AutoCloseable {

    private final Map<String, String> previous;

    private MailLogContext(MailRequest request) {
        previous = MDC.getCopyOfContextMap();

        MDC.put("correlationId", request.correlationId());
        MDC.put("notificationId", request.notificationId());
    }

    public static MailLogContext from(MailRequest request) {
        return new MailLogContext(request);
    }

    @Override
    public void close() {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}
```

Sử dụng:

```java
public void handle(MailRequest request) {
    try (MailLogContext ignored = MailLogContext.from(request)) {
        log.info("Processing mail request");

        String html = templateRenderer.render(request);
        log.info("Mail template rendered");

        mailGateway.submit(request, html);
        log.info("SMTP submit step completed");
    }
}
```

Khối `try-with-resources` dọn MDC ngay cả khi template renderer hoặc SMTP gateway ném exception.

Một cải tiến có thể là truyền một record `MailDiagnostics` thay vì toàn bộ `MailRequest` vào helper, để không liên quan đến payload nhạy cảm.

### Tại sao phải khôi phục MDC, không chỉ remove một key?

Nếu worker được gọi từ context đã có `traceId`, `spanId` hoặc metadata hợp lệ khác, chỉ xóa một key hoặc gọi `MDC.clear()` bừa bãi có thể phá vỡ context của lớp cha. Việc lưu map trước đó và khôi phục trong `finally` giúp đoạn code có thể lồng nhau an toàn hơn.

Ngược lại, nếu một worker thiết lập MDC cho nhiều job liên tiếp mà không dọn, job sau có thể kế thừa nhầm ID cũ.

## 9. Outbox: lưu correlation ID như dữ liệu bền vững

Với email quan trọng, một thiết kế phổ biến là lưu yêu cầu gửi vào **transactional outbox** cùng transaction nghiệp vụ.

```text
HTTP request
  correlationId=corr-401
        |
        v
Business transaction
  ├── Save order
  └── Insert mail_outbox
        correlationId=corr-401
        notificationId=notif-401
        status=PENDING
        |
        v
Commit
        |
        v
Outbox worker (possibly another instance)
        |
        v
SMTP attempt
```

Một bảng tối thiểu có thể có:

```sql
CREATE TABLE mail_outbox (
    id                VARCHAR(64) PRIMARY KEY,
    correlation_id    VARCHAR(64) NOT NULL,
    event_id          VARCHAR(64),
    notification_type VARCHAR(100) NOT NULL,
    recipient_ref     VARCHAR(128) NOT NULL,
    template_key      VARCHAR(128) NOT NULL,
    payload_json      TEXT NOT NULL,
    status            VARCHAR(40) NOT NULL,
    attempt_count     INT NOT NULL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL
);
```

Đây là cấu trúc minh họa. Đối với dữ liệu nhạy cảm, cân nhắc mã hóa payload, giới hạn quyền, retention và phân tách recipient reference với địa chỉ email thật.

Khi worker bắt đầu, nó đọc lại `correlation_id` từ bản ghi. Không có gì bảo đảm MDC của request ban đầu còn tồn tại, vì worker có thể chạy sau nhiều giờ hoặc trên một máy khác.

### Lưu correlation ID trong cùng transaction

Nếu event đã được commit nhưng metadata correlation ID chỉ nằm trong RAM, bạn có thể mất khả năng nối log khi process dừng. Với outbox, nên lưu ID và yêu cầu gửi **trong cùng transaction** với trạng thái nghiệp vụ làm phát sinh email.

Đối với mỗi notification logic, dùng `notificationId` làm khóa theo dõi chính. Correlation ID có thể được chia sẻ giữa nhiều notification nên không phù hợp làm khóa duy nhất của bản ghi outbox.

## 10. Truyền ID qua message broker

Với RabbitMQ, Kafka hoặc một broker khác, correlation ID có thể đi trong **message headers** hoặc trong body envelope. Một phương án bền vững thường lưu trong body hoặc một schema có version; header giúp middleware/logging dễ lấy metadata hơn.

Ví dụ envelope dạng JSON:

```json
{
  "eventType": "MAIL_REQUESTED",
  "schemaVersion": 1,
  "correlationId": "corr-63de",
  "notificationId": "notif-918",
  "eventId": "order-event-401",
  "templateKey": "order-confirmation",
  "templateVersion": "v3",
  "recipientRef": "customer-401"
}
```

Consumer:

```java
@RabbitListener(queues = "mail.notification")
public void onMessage(MailEnvelope envelope) {
    try (MailLogContext ignored =
            MailLogContext.from(envelope.toMailRequest())) {

        mailDeliveryService.process(envelope);
    }
}
```

Các kiểu `MailEnvelope` và `toMailRequest()` là ví dụ về model và mapping của ứng dụng, không phải API có sẵn của Spring AMQP.

Một ứng dụng thực tế cần xác nhận schema, ID, giới hạn kích thước và quyền của producer. Không nên tin một header correlation ID từ một producer chưa được xác thực rồi ghi thẳng vào log.

### Header và body có thể lệch nhau

Nếu broker header có `correlationId=A` nhưng body có `correlationId=B`, cần quy định nguồn dữ liệu chuẩn. Một chính sách thông dụng là coi envelope đã được validate là nguồn gốc, còn header chỉ là bản sao để log/transport. Ghi nhận mismatch rồi từ chối hoặc cách ly message nếu cần; đừng âm thầm chọn một giá trị tùy tiện.

### Retry và dead-letter queue

Khi retry qua queue hoặc DLQ, giữ cùng `correlationId` và `notificationId`. Tạo `attemptId` mới cho mỗi SMTP attempt để có thể phân biệt:

```text
corr-63de / notif-918
    ├── attempt-1 -> temporary SMTP error
    ├── attempt-2 -> connection timeout
    └── attempt-3 -> SMTP accepted
```

Nếu requeue tạo correlation ID mới, người vận hành khó thấy ba lần thử thuộc cùng một notification.

## 11. Trace ID và correlation ID trong hệ thống distributed tracing

Nếu ứng dụng dùng Micrometer Tracing, OpenTelemetry hoặc một hệ thống tracing khác, log có thể chứa `traceId` và `spanId`. Hai khái niệm này có thể bổ sung cho correlation ID.

```text
Correlation ID: corr-63de
    |
    +-- HTTP trace A
    |     ├── controller span
    |     └── outbox insert span
    |
    +-- Worker trace B
    |     ├── template render span
    |     └── SMTP submit span
    |
    +-- Webhook trace C
          └── provider event handling span
```

Đối với một workflow kéo dài, correlation ID có thể giữ nguyên trong khi các lần xử lý có trace khác nhau, đặc biệt khi context tracing không được tiếp tục qua queue/outbox.

### Truyền W3C trace context

Một số hệ thống truyền distributed tracing qua HTTP hoặc message headers dùng chuẩn như `traceparent` và `tracestate`. Nếu thư viện instrumentation hỗ trợ, span context có thể được trích xuất và tiếp tục ở consumer.

Không nên tự viết parser/serializer `traceparent` khi đã có propagation library phù hợp. Việc propagation cần đúng ngữ nghĩa trace/span, sampling và trust boundary.

**Trace context không thay thế notification ID.** Khi truy xuất một email nhiều ngày sau từ provider webhook, trace gốc có thể đã hết retention; bản ghi notification ID và correlation ID bền vững vẫn cần thiết.

### Baggage và dữ liệu nhạy cảm

OpenTelemetry/Micrometer baggage có thể truyền metadata qua nhiều hệ thống. Không đặt email, access token, mật khẩu hoặc PII vào baggage chỉ để tiện logging; một số metadata có thể xuất hiện trong header hoặc telemetry backend.

Nếu dùng baggage cho correlation ID, vẫn cần lưu ID vào outbox khi nghiệp vụ yêu cầu truy xuất lâu dài.

## 12. Từ renderer đến JavaMailSender: giữ ID qua lớp gửi

Một quy trình rõ ràng nên truyền metadata tới gateway SMTP:

```java
public record MailSubmission(
        String correlationId,
        String notificationId,
        String attemptId,
        String recipient,
        String subject,
        String plainText,
        String html
) {
}
```

Gateway:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class SmtpMailGateway {

    private final JavaMailSender mailSender;

    public SmtpMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(MailSubmission request)
            throws MessagingException {

        try (var ignored = MailLogScope.open(
                request.correlationId(),
                request.notificationId(),
                request.attemptId())) {

            MimeMessage mime = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, true, "UTF-8");

            helper.setFrom("notifications@example.org");
            helper.setTo(request.recipient());
            helper.setSubject(request.subject());
            helper.setText(
                    request.plainText(),
                    request.html()
            );

            log.info("SMTP submit started");

            try {
                mailSender.send(mime);
                log.info("SMTP transport accepted message");
            } catch (MailException exception) {
                log.error(
                        "SMTP submit failed, errorType={}",
                        exception.getClass().getSimpleName()
                );
                throw exception;
            }
        }
    }
}
```

`MailLogScope.open(...)` là tiện ích logging context do ứng dụng định nghĩa, tương tự `MailLogContext` ở phần trước. `log` là logger của lớp. Đoạn code minh họa luồng truyền metadata; code production cần xử lý riêng `MessagingException` phát sinh khi dựng MIME và lưu kết quả attempt trong storage.

Điểm cốt lõi là gateway **nhận ID qua `MailSubmission`**, không phải cố đoán correlation ID từ địa chỉ email, subject hoặc `Message-ID` sau khi gửi.

### Đặt log theo giai đoạn

Những event hữu ích:

```text
MAIL_REQUEST_ACCEPTED
MAIL_TEMPLATE_RENDERED
MAIL_ATTEMPT_STARTED
MAIL_SMTP_ACCEPTED
MAIL_ATTEMPT_FAILED
MAIL_RETRY_SCHEDULED
MAIL_PROVIDER_DELIVERED
MAIL_PROVIDER_BOUNCED
```

Mỗi log nên mang correlation ID, notification ID và attempt ID khi có. Khi xử lý provider event, có thể cần cả provider message ID.

## 13. Có nên thêm correlation ID vào email header?

Jakarta Mail cho phép thêm custom header:

```java
mimeMessage.setHeader(
        "X-Application-Correlation-ID",
        correlationId
);
```

Điều này đôi khi hữu ích khi điều tra raw email hoặc khi một SMTP provider giữ lại header và cho phép tra cứu. Tuy nhiên, cần hiểu các giới hạn:

- **Header có thể được người nhận đọc được**, không phải metadata bí mật.
- Một số provider hoặc mail gateway có thể xóa, thay đổi hoặc không trả header trong webhook.
- Header không bảo đảm được bên nhận/nhà cung cấp dùng để deduplicate.
- Giá trị phải được validate và không chứa CR/LF hoặc dữ liệu cá nhân.
- Chỉ nên thêm khi có mục đích chẩn đoán được chấp thuận.

Trong nhiều ứng dụng, giữ correlation ID **ở database và log** đã đủ; không cần đưa nó vào email thực tế.

### Correlation ID không phải Message-ID

Không dùng custom header làm thay thế `Message-ID`, `In-Reply-To` hoặc `References`. Những header đó có quy tắc và mục đích riêng trong thư điện tử.

Nếu ứng dụng cần quản lý `Message-ID` để phục vụ chẩn đoán, hãy ghi nhận giá trị thực tế của message sau khi chuẩn bị/gửi, với hiểu biết rằng provider có thể có thêm ID nội bộ. Không dựa vào việc mọi provider giữ nguyên ID theo một cách đồng nhất.

## 14. Ghi nhận SMTP attempt và kết quả không chắc chắn

Mỗi lần gọi `JavaMailSender.send(...)` cần có attempt ID để phân biệt retry.

Ví dụ record:

```json
{
  "correlationId": "corr-63de",
  "notificationId": "notif-918",
  "attemptId": "attempt-918-02",
  "smtpRoute": "primary",
  "status": "SMTP_SUBMISSION_FAILED",
  "errorClass": "MailSendException",
  "smtpReplyCode": null
}
```

Nếu `send` trả về bình thường, có thể ghi `SMTP_ACCEPTED` hoặc `ACCEPTED_BY_SMTP` theo contract của hệ thống. **Không ghi `DELIVERED`** trừ khi có bằng chứng delivery ở tầng provider/recipient phù hợp.

### Timeout có thể là kết quả không xác định

Một tình huống:

1. Worker gửi toàn bộ nội dung email.
2. SMTP server chấp nhận message.
3. Kết nối bị ngắt trước khi client nhận phản hồi cuối.
4. `JavaMailSender` báo exception hoặc timeout.
5. Worker không biết chắc server đã nhận message hay chưa.

Lúc này, nên phân biệt `UNKNOWN` với thất bại chắc chắn. Khi retry, một email trùng có thể được gửi. Correlation ID giúp nối các attempt và điều tra; **nó không tự mang lại exactly-once**.

### Đừng thay correlation ID khi retry

Giữ:

```text
correlationId = corr-63de
notificationId = notif-918
```

Và thay:

```text
attemptId = attempt-918-01
attemptId = attempt-918-02
attemptId = attempt-918-03
```

Nếu retry từ một operator action riêng, có thể ghi thêm `retryTriggeredBy` hoặc `recoveryOperationId` để biết nguồn kích hoạt; không cần bỏ mất correlation ID của workflow gốc.

## 15. Gắn correlation với provider message ID và webhook

Sau khi SMTP chấp nhận email, một provider có thể tạo ID riêng. Các sự kiện sau đó như delivery, bounce, deferred hoặc complaint có thể đến qua webhook, API hoặc event stream.

```text
Application mail request
  correlationId=corr-63de
  notificationId=notif-918
        |
        v
SMTP/API submission
        |
        v
providerMessageId=provider-7af1
        |
        v
Provider webhook (later)
  providerMessageId=provider-7af1
  event=DELIVERED
        |
        v
Lookup notificationId
        |
        v
Update delivery state
  correlationId=corr-63de
```

Một bảng ánh xạ tối thiểu:

| Trường | Công dụng |
|---|---|
| `notification_id` | Khóa nội bộ của thông báo logic. |
| `correlation_id` | Liên kết với nghiệp vụ và log gốc. |
| `attempt_id` | Lần submit đã tạo provider ID. |
| `provider_message_id` | Khóa tra cứu sự kiện từ nhà cung cấp. |
| `mime_message_id` | Header Message-ID nếu có và cần lưu. |
| `provider_event_id` | Giúp deduplicate webhook khi provider cung cấp. |
| `delivery_status` | Trạng thái sau submission. |

### Không phải webhook nào cũng trả custom header

Một số provider hỗ trợ truyền metadata tùy chỉnh khi gửi bằng API; một số khác chỉ trả provider message ID hoặc event ID. Khi gửi qua SMTP, có thể không có cơ chế gắn metadata đáng tin cậy tương tự API.

Vì vậy, hãy xây việc correlate webhook dựa trên **khả năng thực tế của provider**. Có thể cần dùng provider message ID, email message ID, custom metadata được hỗ trợ hoặc một bảng ánh xạ khi gửi. Không giả định chỉ cần đặt `X-Correlation-ID` là mọi webhook sẽ trả lại giá trị đó.

### Webhook cần xác thực và chống replay

Correlation ID không xác thực nguồn sự kiện. Webhook phải được kiểm tra chữ ký, token hoặc cơ chế authentication mà provider công bố. Sự kiện có thể được gửi lặp; cần dùng provider event ID hoặc một khóa deduplication phù hợp.

Không cho phép webhook chỉ dựa vào correlation ID để cập nhật trạng thái của bất kỳ notification nào, vì một correlation ID có thể liên quan tới nhiều email.

## 16. Truy vấn log từ một lỗi MailException

Một quy trình chẩn đoán có thể bắt đầu bằng log:

```text
timestamp=2026-11-12T09:20:11Z
event=MAIL_ATTEMPT_FAILED
correlationId=corr-63de
notificationId=notif-918
attemptId=attempt-918-02
errorType=MailAuthenticationException
smtpRoute=primary
```

Có thể tra cứu theo thứ tự:

1. **Attempt ID**: xác định lần thử gửi và thông tin lỗi cụ thể.
2. **Notification ID**: xem các attempt trước đó, trạng thái outbox và quyết định retry.
3. **Correlation ID**: tìm sự kiện nghiệp vụ tạo email, request/event liên quan và các log từ renderer/queue.
4. **Provider message ID**, nếu tồn tại: đối chiếu dashboard provider và delivery webhook.

Các câu hỏi cần trả lời:

- Job được tạo khi nào?
- Ai/điều gì phát sinh event?
- Template/version/locale nào được dùng?
- Attempt nào xảy ra đầu tiên?
- Lỗi xảy ra trước hay sau khi SMTP có thể chấp nhận message?
- Có job khác cùng correlation ID không?
- Lần retry có bị trùng hay không?
- Có webhook delivery/bounce nào đến sau đó không?

Với một lỗi SMTP authentication kéo dài, nhiều correlation ID có thể cùng gặp lỗi trên một mail route. Khi đó cần thêm **route/provider ID** để thấy sự cố hệ thống, thay vì chỉ điều tra từng email.

## 17. Structured logging và quy ước tên trường

Nên thống nhất tên trường giữa các service:

```text
correlationId
requestId
traceId
spanId
eventId
notificationId
attemptId
providerMessageId
smtpRoute
notificationType
templateKey
templateVersion
status
errorType
```

Nếu mỗi service dùng một tên khác nhau như `corr_id`, `requestCorrelation` và `mailFlowId`, dashboard và truy vấn log sẽ phức tạp hơn. Có thể chuẩn hóa sang snake_case ở tầng log ingestion, nhưng schema cần được công bố và giữ ổn định.

### Một log có cấu trúc minh họa

```json
{
  "event": "MAIL_SMTP_ACCEPTED",
  "correlationId": "corr-63de",
  "notificationId": "notif-918",
  "attemptId": "attempt-918-03",
  "smtpRoute": "primary",
  "durationMs": 842,
  "templateKey": "order-confirmation",
  "templateVersion": "v3"
}
```

Không cần log subject đầy đủ hoặc recipient thật để tương quan sự kiện. Có thể lưu recipient reference/alias nội bộ hoặc domain đã được kiểm soát theo chính sách riêng tư.

### Đừng dùng correlation ID làm nhãn metric

Correlation ID có cardinality rất cao vì gần như mỗi yêu cầu có giá trị khác nhau. Không đặt nó vào label/tag của Prometheus/Micrometer timer hoặc counter:

```text
# Không phù hợp vì cardinality rất cao:
mail_send_total{correlationId="corr-63de"}

# Phù hợp hơn:
mail_send_total{smtpRoute="primary",result="accepted"}
```

Correlation ID nên nằm trong **log, trace hoặc bản ghi truy vấn**, không phải nhãn metric. Metric dùng các chiều thấp-cardinality như route, kết quả, loại thông báo hoặc loại lỗi đã phân nhóm.

## 18. Bảo mật và quyền riêng tư của correlation ID

Correlation ID có vẻ chỉ là một chuỗi kỹ thuật, nhưng có thể dùng để truy vấn log hoặc truy ra hoạt động người dùng. Do đó:

- Không tạo ID chứa email, số điện thoại, access token hoặc dữ liệu cá nhân.
- Không chấp nhận giá trị tùy ý dài hoặc có control character.
- Không dùng correlation ID để cấp quyền truy cập một mail record.
- Không đặt nó trong liên kết reset password như token bí mật.
- Giới hạn quyền truy vấn log và dashboard.
- Có chính sách retention cho log và delivery record.
- Che thông tin recipient, body, attachment và token khi log lỗi.
- Nếu đưa vào response/header email, xem nó là metadata có thể bị tiết lộ.

Ví dụ không nên:

```text
correlationId = "user-email@example.org-2026-11-12"
```

Ví dụ hợp lý hơn:

```text
correlationId = "e241cb19-8cfa-4bb0-b254-b94fefefc719"
```

Nếu cần liên kết ID với user, lưu mapping trong cơ sở dữ liệu được kiểm soát quyền thay vì mã hóa PII trực tiếp vào ID.

## 19. Các lỗi phổ biến làm mất correlation ID

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Controller có ID, `@Async` không có | MDC dựa trên thread-local | Truyền ID trong command và dùng TaskDecorator nếu cần. |
| Worker log ID của email trước | Không clear/restore MDC trong thread pool | Dùng `try/finally` hoặc scope `AutoCloseable`. |
| Queue consumer có `correlationId=missing` | Publisher không serialize metadata | Thêm correlation ID vào envelope/header có schema rõ. |
| Retry xuất hiện như email mới | Tạo notification ID/correlation ID mới ở mỗi attempt | Giữ logical ID, tạo attempt ID mới. |
| Nhiều email cùng correlation ID khó phân biệt | Chỉ dùng correlation ID, không có notification ID | Tạo notification ID riêng cho mỗi thư logic. |
| Webhook không thể nối về email | Không lưu provider ID hoặc không có mapping | Ghi ánh xạ providerMessageId → notificationId. |
| SMTP log có Message-ID nhưng request log không có | Nhầm Message-ID với correlation ID | Lưu cả hai và liên kết qua notification record. |
| Log của job có ID nhưng trace mất | Trace context không được propagate | Cấu hình instrumentation/propagation phù hợp. |
| Log chứa giá trị correlation ID rất dài | Tin header không kiểm tra | Validate format và độ dài ở ingress. |
| Metric backend có quá nhiều series | Dùng correlation ID làm tag metric | Chuyển ID sang log/trace. |
| Webhook có ID đúng nhưng cập nhật sai thư | Dùng correlation ID để xác định một notification | Dùng notification/provider ID cụ thể và xác thực webhook. |
| Mất ID sau restart | ID chỉ nằm trong RAM/MDC | Lưu vào outbox hoặc queue envelope bền vững. |

## 20. Kiểm thử propagation từ đầu tới cuối

Cần kiểm thử việc **bảo toàn ID**, không chỉ việc một dòng log nào đó có ID.

### 20.1. Test HTTP filter

Các tình huống:

- Request có ID hợp lệ được giữ lại theo chính sách.
- Request không có ID được sinh UUID.
- ID có newline, khoảng trắng hoặc quá dài bị từ chối và thay bằng ID nội bộ.
- Response header và request attribute có cùng ID.
- Sau request, MDC được khôi phục để tránh nhiễm thread.

Ví dụ ý tưởng với MockMvc:

```java
mockMvc.perform(
        get("/orders/ORD-401")
            .header("X-Correlation-ID", "corr-test-401")
    )
    .andExpect(
        header().string("X-Correlation-ID", "corr-test-401")
    );
```

Ví dụ giả định endpoint và security/filter chain phù hợp đã tồn tại trong ứng dụng. Cần kiểm tra thêm command được tạo từ request mang đúng correlation ID.

### 20.2. Test @Async và TaskDecorator

Một test có thể:

1. Đặt `MDC["correlationId"] = "corr-A"` trong thread submit.
2. Submit task qua `mailExecutor` và chờ `CompletableFuture` hoàn tất.
3. Trong task, xác nhận MDC là `corr-A`.
4. Submit task khác với `corr-B`.
5. Xác nhận task thứ hai không thấy `corr-A`.
6. Xác nhận MDC ở thread submit và worker được dọn sau khi kết thúc.

Sử dụng `CountDownLatch` hoặc `CompletableFuture` giúp test xác nhận đồng bộ hóa, không phụ thuộc vào `Thread.sleep(...)` tùy ý.

### 20.3. Test outbox và queue serialization

Tạo `MailRequest` với:

```text
correlationId = corr-order-401
notificationId = notif-order-401
```

Serialize, persist/publish, rồi deserialize/read ở worker. Kiểm tra hai ID giữ nguyên. Đây là kiểm thử quan trọng vì MDC của thread tạo request sẽ không tồn tại tại worker.

### 20.4. Test SMTP failure và retry

Dùng mock `JavaMailSender` hoặc SMTP test server có thể gây lỗi:

- Attempt 1 thất bại: record có correlation ID và attempt ID thứ nhất.
- Attempt 2 thành công: correlation ID và notification ID không đổi; attempt ID khác.
- Log lỗi không chứa credential hoặc raw MIME.
- Job không biến mất chỉ vì worker ném `MailException`.

### 20.5. Test provider webhook

Dùng webhook payload mô phỏng đã được xác thực theo cơ chế provider:

1. Tạo mapping giữa provider message ID và notification ID.
2. Nhận sự kiện delivery/bounce.
3. Tra đúng notification record.
4. Ghi nhận trạng thái với correlation ID gốc.
5. Gửi lại cùng webhook event để kiểm tra deduplication.

Đây là kiểm thử của lớp mapping và delivery, không phải cam kết mọi provider đều có cùng schema webhook.

## 21. Chiến lược rollout trong hệ thống đã hoạt động

Nếu ứng dụng cũ chưa có correlation ID đầy đủ, không nhất thiết phải thay tất cả service cùng lúc.

Một cách triển khai từng bước:

1. **Ingress:** thống nhất tên `correlationId`, tạo và validate ID ở HTTP/event entry point.
2. **Mail command:** thêm ID vào envelope của yêu cầu gửi, cùng notification ID.
3. **Outbox schema:** lưu ID và bảo đảm backward compatibility với job cũ.
4. **Worker:** đặt MDC từ metadata trong payload/record.
5. **SMTP adapter:** log start/success/error với correlation ID và attempt ID.
6. **Provider integration:** lưu provider message ID và map webhook về notification.
7. **Dashboard/log query:** cập nhật truy vấn, alert và tài liệu vận hành.
8. **Dọn tương thích:** khi job cũ đã hết, siết invariant correlation ID không được trống.

### Xử lý job cũ không có correlation ID

Nếu outbox cũ có nhiều record thiếu ID, có thể tạo **legacy correlation ID** cho từng job/nhóm sự kiện khi đọc, đồng thời ghi nhận rằng đó là ID được bổ sung sau, không phải correlation ID của request ban đầu.

Không được tự khẳng định đã nối được tới HTTP request gốc nếu dữ liệu đó không tồn tại. Có thể dùng event ID hoặc order ID để tìm lại quan hệ khi đủ bằng chứng, nhưng không nên suy luận tùy tiện.

## 22. Checklist thiết kế và vận hành

| Câu hỏi | Kỳ vọng |
|---|---|
| Có chính sách tạo/nhận correlation ID ở entry point? | Có. |
| Header từ ngoài có được validate hoặc thay bằng ID nội bộ? | Có. |
| Cùng một workflow có giữ correlation ID khi chuyển service/thread? | Có. |
| Mỗi email logic có notification ID riêng? | Có. |
| Mỗi retry có attempt ID riêng nhưng giữ logical ID? | Có. |
| `@Async` có cơ chế propagate/dọn MDC? | Có, nếu log dựa vào MDC. |
| Broker/outbox có lưu ID như dữ liệu bền vững? | Có, với mail async quan trọng. |
| SMTP adapter có ghi status đúng `SMTP_ACCEPTED`/failure? | Có. |
| Có mapping provider ID với notification ID? | Có, nếu cần correlate delivery events. |
| Webhook có xác thực và deduplication? | Có. |
| Không dùng correlation ID làm secret hoặc authorization? | Có. |
| Correlation ID không được dùng làm high-cardinality metric label? | Có. |
| Có test request → queue → worker → SMTP → webhook? | Có. |
| Log có thể truy vấn theo correlationId/notificationId/attemptId? | Có. |

## 23. Ghi nhớ

- **Correlation ID** liên kết những bước thuộc cùng luồng nghiệp vụ; **notification ID** xác định một email logic; **attempt ID** phân biệt các lần gửi.
- Correlation ID không phải HTTP request ID, distributed trace ID, SMTP `Message-ID` hay provider message ID.
- Tạo hoặc validate ID ở entry point và **truyền như dữ liệu tường minh** qua service, event, queue và outbox.
- MDC chỉ là logging context theo thread; đừng phụ thuộc MDC như nguồn dữ liệu duy nhất cho email bất đồng bộ.
- Với `@Async`, có thể dùng `TaskDecorator` để sao chép và khôi phục MDC, nhưng vẫn cần ID trong mail command.
- Consumer/worker nên thiết lập MDC từ record nhận được và dọn trong `finally` hoặc `AutoCloseable`.
- Queue/outbox phải giữ correlation ID khi process restart và khi job được retry.
- Ghi log đúng giai đoạn: render, submit, SMTP accepted, failure, retry và provider delivery/bounce; không đánh đồng SMTP accepted với delivered.
- Correlate webhook qua provider message ID hoặc metadata mà provider thực sự hỗ trợ; không giả định custom mail header sẽ quay lại trong webhook.
- Không dùng correlation ID làm secret, idempotency key duy nhất hoặc nhãn metric có cardinality cao.
- Kiểm thử cả propagation, cleanup, retry và mapping provider event, không chỉ kiểm tra một dòng log.

Giữ được correlation ID xuyên suốt email pipeline giúp hệ thống trả lời chính xác **thư nào, được tạo từ đâu, đã trải qua những lần thử nào và đang dừng ở giai đoạn nào**. Nền tảng của thiết kế không phải một logging trick, mà là **metadata ổn định được lưu và truyền qua mọi ranh giới**, kết hợp MDC/tracing để chẩn đoán và delivery record để đối chiếu kết quả thực tế.
