# Trace luồng từ sự kiện nghiệp vụ đến mail server trong Spring Framework Mail

Khi người dùng xác nhận đơn hàng nhưng không nhận được email, câu hỏi đầu tiên thường là: hệ thống đã gửi thư hay chưa? Câu hỏi này khó hơn một lời gọi `JavaMailSender.send(...)`. Email có thể đi qua transaction nghiệp vụ, event, outbox, scheduler, worker bất đồng bộ, bước dựng `MimeMessage`, SMTP submission và cuối cùng là các sự kiện delivery/bounce do nhà cung cấp gửi về.

Một lời gọi gửi thư thành công chỉ cho biết SMTP transport đã hoàn tất thao tác submission theo hợp đồng thư viện. Nó không chứng minh người nhận đã thấy email trong Inbox. Ngược lại, một timeout sau SMTP DATA có thể xảy ra khi server đã nhận message nhưng client không nhận được phản hồi cuối. Chỉ thêm log “send started” và “send failed” không đủ để kết luận đúng.

**Tracing** giúp nhìn thấy các giai đoạn thực thi, thời gian và mối quan hệ nguyên nhân. Nhưng quan sát mail pipeline còn cần **correlation ID ổn định, structured logs, metrics, outbox states và provider event IDs**, bởi SMTP truyền thống không tự động mang distributed trace context giống HTTP/gRPC.

Bài này hướng dẫn cách lần theo một email từ business event tới mail server trong ứng dụng Spring, bao gồm Micrometer Observation/Tracing, MDC và async context, transactional outbox, SMTP result ambiguity, provider webhook, logging bảo mật, runbook và kiểm thử.

## 1. Luồng email từ nghiệp vụ tới SMTP

Ví dụ người dùng xác nhận đơn hàng:

~~~text
HTTP POST /orders/{id}/confirm
              |
              v
     OrderApplicationService
              |
              +--> validate + update order
              +--> insert mail_outbox
              |
              v
         DB COMMIT
              |
              v
      Outbox scheduler
              |
              v
        Claim mail job
              |
              v
        Mail worker
              |
              +--> load template/snapshot
              +--> render subject/plain/HTML
              +--> resolve attachments
              +--> build MimeMessage
              +--> acquire rate-limit slot
              |
              v
       JavaMailSender.send(...)
              |
              v
      SMTP connection + TLS + AUTH
              |
              +--> MAIL FROM
              +--> RCPT TO
              +--> DATA
              +--> final SMTP response
              |
              v
      Record SUBMITTED/RETRY_WAIT/FAILED
              |
              v
      Provider events if supported
              |
              +--> delivered
              +--> deferred
              +--> bounced
~~~

Một trace HTTP có thể bao gồm phần validate, update và outbox insert. Worker có thể chạy vài giây hoặc vài giờ sau trên instance khác. Provider webhook có thể đến còn muộn hơn. Vì thế không nên giả định mọi bước đều là child span của một HTTP trace duy nhất.

## 2. Những câu hỏi một trace tốt cần trả lời

1. Business event nào tạo ra ý định gửi email?
2. Transaction đã commit hay rollback?
3. Outbox record có được lưu bền vững không?
4. Scheduler có nhìn thấy job tới hạn không?
5. Worker nào đã claim job và lease có còn hiệu lực không?
6. Job chờ bao lâu trước khi được xử lý?
7. Có thất bại khi dựng template, HTML, ảnh hoặc attachment không?
8. SMTP client có được gọi không?
9. Thời gian gửi nằm ở connect, TLS, AUTH, DATA hay chờ phản hồi?
10. SMTP relay đã chấp nhận message chưa?
11. Đã retry bao nhiêu lần, vì lỗi gì?
12. Provider có báo delivered, bounced hoặc deferred không?

Không cần tạo span cho từng getter. Hãy quan sát các **ranh giới có ý nghĩa**: giao dịch, enqueue, claim, render, transport, trạng thái retry và event callback.

## 3. Trace, span, log, metric và durable state

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Trace | Liên kết chuỗi thực thi có quan hệ | HTTP confirm-order trace |
| Span | Một thao tác có thời lượng và thuộc tính | `mail.smtp.submit` |
| Structured log | Một sự kiện tại một thời điểm | Job N-2105 được claim |
| Metric | Xu hướng/số liệu tổng hợp | SMTP error rate hoặc queue age P95 |
| Business event | Một việc nghiệp vụ đã xảy ra | `OrderConfirmed` |
| Outbox row | Ý định gửi bền vững | Notification N-2105 ở RETRY_WAIT |
| Provider event | Kết quả downstream từ ESP/relay | Delivered hoặc bounced |
| Correlation ID | Nối dữ liệu giữa các traces và systems | `notificationId` |

Traces có sampling và retention nên không phải nguồn sự thật của notification status. Logs giúp tìm từng job; metrics phát hiện xu hướng; database outbox và provider event records lưu kết quả có giá trị nghiệp vụ.

## 4. Những loại ID cần phân biệt

| ID | Nguồn | Ổn định qua retry? | Mục đích |
| --- | --- | --- | --- |
| `orderId` | Business domain | Có | Tìm đơn hàng |
| `businessEventId` | Domain event | Có | Tìm event tạo email |
| `notificationId` | Mail application | **Có** | Định danh một yêu cầu gửi logic |
| `outboxId` | Durable outbox | Có | Tra record |
| `attemptId` | Worker mỗi lần gửi | Không | Phân biệt các lần thử |
| `traceId` | Tracing system | Trong một trace | Tìm spans liên quan |
| `spanId` | Tracing system | Không | Một đoạn thao tác |
| `providerMessageId` | ESP nếu có | Có thể đổi theo attempt | Tra provider events |
| `smtpQueueId` | SMTP relay nếu expose | Có thể đổi | Tra mail server queue |
| MIME `Message-ID` | Header email | Phụ thuộc implementation | Correlation ở MIME |

**Không dùng trace ID làm business idempotency key.** Một event có thể chạy ở nhiều traces; một trace có thể sinh nhiều notifications. `notificationId`/`outboxId` thường là khóa tốt nhất để tìm một email logic qua toàn bộ pipeline.

MIME `Message-ID` không phải provider queue ID, và SMTP không bảo đảm loại bỏ message trùng chỉ nhờ Message-ID.

## 5. Một timeline minh họa

~~~text
T+000 ms   HTTP request bắt đầu
T+011 ms   order.confirm start
T+025 ms   order updated
T+030 ms   mail_outbox row N-2105 inserted
T+042 ms   transaction COMMIT
T+180 ms   outbox poller claims N-2105
T+192 ms   mail.render start
T+214 ms   mail.render completed
T+220 ms   smtp.submit starts, attempt A1
T+415 ms   SMTP connection/TLS/AUTH completed
T+770 ms   final DATA 250 accepted
T+782 ms   outbox status SUBMITTED
T+6 sec    provider event DELIVERED
~~~

Thời gian trên chỉ minh họa. Nếu chỉ nhìn span `mail.smtp.submit` dài 550 ms, ta sẽ bỏ qua 180 ms queue wait hoặc transaction bottleneck. Nếu job chờ 10 phút trong outbox, SMTP có thể vẫn rất nhanh nhưng notification vẫn chậm.

## 6. Micrometer Observation và Tracing trong Spring

Spring Boot hiện đại hỗ trợ Micrometer Observation để quan sát các thao tác. Với Micrometer Tracing bridge/exporter phù hợp, observations có thể được biểu diễn thành spans, đồng thời có thể sinh metrics.

~~~text
Application code
       |
       v
Micrometer ObservationRegistry
       |
       +--> Observation handlers / timers
       |
       +--> Micrometer Tracing bridge
                     |
                     v
               Trace exporter
                     |
                     v
               Trace backend
~~~

Cần dependency của Spring Boot Actuator, Micrometer Tracing bridge và exporter tương thích với phiên bản Spring đang dùng. Chỉ inject `ObservationRegistry` không bảo đảm một trace backend sẽ nhận spans nếu chưa cấu hình bridge/exporter.

Ví dụ một phần cấu hình:

~~~yaml
spring:
  application:
    name: order-mail-service

management:
  tracing:
    sampling:
      probability: 0.1
~~~

`0.1` là ví dụ 10% sampling, không phải con số mặc định hay khuyến nghị chung. Exporter endpoint, security và logging integration phải theo backend/phiên bản sử dụng.

## 7. Tên span phải mô tả thao tác

Một hệ thống có thể đặt span names:

~~~text
order.confirm
mail.outbox.enqueue
mail.outbox.poll
mail.outbox.claim
mail.notification.process
mail.template.render
mail.attachment.load
mail.mime.prepare
mail.rate_limit.acquire
mail.smtp.submit
mail.outbox.mark_submitted
mail.provider.webhook.consume
~~~

Không nên tạo span name chứa recipient hoặc ID:

~~~text
mail.smtp.submit.customer@example.com
mail.smtp.submit.order.ORDER-123
~~~

Những giá trị đó khiến cardinality tăng, khó tổng hợp và có thể lộ dữ liệu cá nhân.

### Low-cardinality và high-cardinality

| Attribute | Cardinality | Cách dùng |
| --- | --- | --- |
| `mail.provider=primary` | Thấp | Metric tag và span |
| `mail.category=TRANSACTIONAL` | Thấp | Metric tag và span |
| `mail.outcome=SUBMITTED` | Thấp | Metric tag và span |
| `mail.failure_class=TRANSIENT` | Thấp | Metric tag và span |
| `notificationId=N-2105` | Cao | Structured log hoặc span attribute có kiểm soát |
| Recipient address | Cao, PII | Tránh metric tag; hạn chế logs/traces |
| Mail subject/body | Có thể nhạy cảm | Không đưa vào telemetry mặc định |

Trong spans, high-cardinality data chỉ nên được dùng khi lợi ích điều tra vượt rủi ro retention/access. Với metrics, không gắn các ID duy nhất vào tags.

## 8. Tracing nghiệp vụ và database transaction

Ví dụ use case:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orders.getRequired(orderId);

        order.confirm();
        orders.save(order);

        MailOutboxEntry mail =
            MailOutboxEntry.forConfirmedOrder(
                UUID.randomUUID(),
                orderId,
                order.customerId()
            );

        outbox.save(mail);
    }
}
~~~

Các domain/repository classes là mô hình minh họa, không phải class của Spring Mail. Khi update order và insert outbox cùng transaction, chúng commit/rollback cùng nhau.

Một span `order.confirm` trả về bình thường không tự chứng minh commit trong mọi proxy/call setup. Cần quan sát kết quả transaction hoặc đọc durable record. Không ghi “email enqueued durably” trước commit nếu transaction còn có thể rollback.

## 9. Event listener sau commit chưa phải durable dispatch

Ví dụ:

~~~java
@Component
public class ConfirmedOrderListener {

    private final MailDispatcher dispatcher;

    public ConfirmedOrderListener(
            MailDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onConfirmed(OrderConfirmedEvent event) {
        dispatcher.dispatch(event.notificationId());
    }
}
~~~

`AFTER_COMMIT` tránh chạy trước commit khi event được phát từ transaction, nhưng một process crash sau commit và trước khi listener hoàn tất vẫn có thể làm mất thao tác gửi nếu chỉ có event trong memory.

Với email quan trọng, outbox lưu yêu cầu cùng transaction. Listener có thể chỉ đánh thức poller để tăng tốc, còn durable outbox vẫn cho phép phục hồi sau restart.

Tracing nên tách:

- Event published.
- Transaction committed.
- Durable outbox inserted.
- Worker claimed.
- SMTP submission attempted.

Nếu chỉ instrument listener, một event mất trước listener sẽ không có worker trace để tìm.

## 10. Async làm mất trace context như thế nào?

Context tracing thường tồn tại trong scope/thread execution. Khi chuyển qua `@Async`, `TaskExecutor`, `@Scheduled` hoặc process khác, context không mặc nhiên đi theo:

~~~text
HTTP thread:
  traceId = A
  spanId  = B
        |
        +--> submit async task
                     |
                     v
mail-worker thread:
  current trace?
  MDC?
~~~

Khi không có propagation phù hợp, worker có thể tạo trace mới, log thiếu traceId hoặc còn MDC từ task trước.

Không sao chép toàn bộ HTTP request, security principal hoặc transaction context chỉ để lấy correlation ID. `notificationId` là dữ liệu nhỏ, ổn định và có ý nghĩa hơn cho durable mail workflow.

## 11. TaskDecorator và context propagation

Trong Spring Framework có phiên bản hỗ trợ `ContextPropagatingTaskDecorator`, có thể cấu hình một executor:

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailTaskExecutor")
    public ThreadPoolTaskExecutor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");

        executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator()
        );

        return executor;
    }
}
~~~

Class và dependency Micrometer context propagation phải tương thích phiên bản Spring; không giả định mọi dự án đều có class này. Với hệ thống không hỗ trợ, có thể dùng `TaskDecorator` tùy chỉnh, nhưng MDC-only propagation không tương đương full tracing context propagation.

Khi task chạy ngay sau request, parent-child trace có thể hợp lý. Với outbox job chạy vài giờ sau, thường tốt hơn khi tạo trace mới và liên kết bằng stable ID hoặc span link.

## 12. Outbox cần lưu gì để có thể nối traces?

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE mail_outbox (
    id                    UUID PRIMARY KEY,
    business_event_id     UUID NOT NULL,
    aggregate_id          UUID NOT NULL,
    category              VARCHAR(40) NOT NULL,
    status                VARCHAR(30) NOT NULL,
    attempts              INTEGER NOT NULL DEFAULT 0,
    next_attempt_at       TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    origin_trace_id       VARCHAR(32),
    origin_span_id        VARCHAR(16),
    origin_service        VARCHAR(100)
);
~~~

Không bắt buộc mọi job đều có `origin_trace_id`. Khi có active trace, application có thể lưu các ID hợp lệ để hỗ trợ điều tra, nhưng correlation chính vẫn là outbox/notification ID.

~~~text
Trace A: HTTP order confirmation
  |
  +--> order.confirm
  +--> mail.outbox.enqueue
          |
          +--> notificationId = N-2105

           time passes

Trace B: mail worker
  |
  +--> outbox.claim
  +--> mail.render
  +--> mail.smtp.submit
          |
          +--> notificationId = N-2105
          +--> originTraceId = A
~~~

Nếu backend hỗ trợ span links, một worker span có thể link tới context từ nguồn. Không tự thay traceId của worker chỉ để mọi logs trông cùng một trace.

## 13. Parent-child span, span link và correlation ID

| Quan hệ | Khi phù hợp | Điểm cần biết |
| --- | --- | --- |
| Parent-child | Hoạt động nằm trong execution trực tiếp của parent | Cần propagate context đúng |
| Span link | Job/message xử lý độc lập nhưng được gây ra bởi trace khác | Cần tracing API/backend hỗ trợ |
| Correlation ID | Liên kết qua DB, worker, provider và ngay cả khi trace bị sampling | Phải lưu và log nhất quán |

Nếu dùng OpenTelemetry `SpanBuilder.addLink(...)`, cần `SpanContext` hợp lệ và tin cậy. Không coi một chuỗi traceparent bất kỳ từ user input là context được phép gắn vào trace nội bộ.

Với Micrometer tracing bridges khác nhau, API tạo span link có thể không giống nhau. Có thể chỉ lưu `originTraceId` trong log nếu không muốn phụ thuộc API vendor cụ thể.

## 14. Tạo Observation quanh JavaMailSender.send

Một vị trí dễ instrument nhất là ranh giới gửi SMTP:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

@Service
public class ObservedMailDeliveryAdapter {

    private final JavaMailSender mailSender;
    private final ObservationRegistry observations;

    public ObservedMailDeliveryAdapter(
            JavaMailSender mailSender,
            ObservationRegistry observations) {
        this.mailSender = mailSender;
        this.observations = observations;
    }

    public void send(
            MimeMessage message,
            String provider,
            String category) {

        Observation.createNotStarted(
                "mail.smtp.submit", observations
            )
            .lowCardinalityKeyValue("mail.provider", provider)
            .lowCardinalityKeyValue("mail.category", category)
            .observe(() -> mailSender.send(message));
    }
}
~~~

Với ObservationRegistry được cấu hình các handler phù hợp, đoạn này có thể tạo metric timer và span. Không có handler/exporter thì một observation không bảo đảm trace xuất hiện trên dashboard.

`provider` và `category` phải được chuẩn hóa thành tập giá trị nhỏ. Không truyền recipient address hoặc subject vào `lowCardinalityKeyValue`.

## 15. Ghi lỗi trong observation

Để kiểm soát rõ span lifecycle:

~~~java
public void submit(
        MimeMessage message,
        String notificationId) {

    Observation observation =
        Observation.createNotStarted(
                "mail.smtp.submit", observations
            )
            .lowCardinalityKeyValue(
                "mail.transport", "smtp"
            );

    observation.start();

    try (Observation.Scope scope =
             observation.openScope()) {

        mailSender.send(message);

        log.info(
            "SMTP submission completed for notificationId={}",
            notificationId
        );

    } catch (MailException exception) {
        observation.error(exception);

        log.warn(
            "SMTP submission failed, notificationId={}, type={}",
            notificationId,
            exception.getClass().getSimpleName()
        );

        throw exception;
    } finally {
        observation.stop();
    }
}
~~~

Một production adapter thường phân loại lỗi thành `TRANSIENT`, `PERMANENT`, `CONFIGURATION` và `AMBIGUOUS`. Đừng tự gọi mọi exception là `NOT_SENT`. Timeout sau khi SMTP DATA đã được truyền có thể là trường hợp relay đã nhận nhưng phản hồi cuối bị mất.

Đoạn code cố ý không ghi subject/body, attachment, password hay raw SMTP transcript.

## 16. Không có distributed trace tự động xuyên SMTP server

SMTP truyền thống không tự truyền W3C Trace Context như các hệ thống HTTP/gRPC có instrumentation. Một client-side span quanh `JavaMailSender.send(...)` không khiến SMTP relay tự nhận traceparent và tạo child span.

~~~text
Application trace
   |
   +--> mail.smtp.submit span
              |
              v
           SMTP
              |
              v
        SMTP relay
              |
              +--> mail queue ID / server logs
              +--> provider events
~~~

Nếu sở hữu SMTP server, đội vận hành có thể bổ sung instrumentation riêng và liên kết với application qua IDs. Nếu dùng provider bên ngoài, thường cần đối soát bằng provider message ID, SMTP queue ID, recipient/account và timestamp.

Không tự đặt `traceparent` vào outgoing email headers rồi giả định server sẽ hiểu. Một custom header phục vụ correlation cũng cần xem xét privacy và khả năng provider giữ lại header. Thường sử dụng opaque notification ID an toàn hơn gửi internal trace metadata ra ngoài.

## 17. SMTP có nhiều mã 250 khác nhau

Một phiên giao tiếp rút gọn:

~~~text
C: EHLO app.example.com
S: 250 capabilities
C: MAIL FROM:<sender@example.com>
S: 250 OK
C: RCPT TO:<recipient@example.net>
S: 250 OK
C: DATA
S: 354 Continue
C: headers and body
C: .
S: 250 2.0.0 Queued as ABC123
~~~

`250` sau EHLO, MAIL FROM hoặc RCPT TO chưa chứng minh message được nhận hoàn chỉnh. **Final success reply sau dấu kết thúc DATA** mới là bằng chứng relay hiện tại đã chấp nhận submission.

`JavaMailSender.send(...)` không trả chuẩn một object chứa queue ID của server. Nếu cần `ABC123`, phải có nguồn provider logs/API/transport instrumentation phù hợp.

Ngay cả khi server chấp nhận DATA, không thể tự suy ra email đã vào Inbox. Provider còn có thể defer, filter, quarantine hoặc bounce ở downstream.

## 18. Structured logs giúp nối nhiều traces

Ví dụ log ở business service:

~~~json
{
  "timestamp": "2026-11-12T10:00:00Z",
  "service": "order-service",
  "event": "mail.outbox.enqueued",
  "traceId": "9d7436e89df6482898fe347812ae6c51",
  "orderId": "ORDER-123",
  "notificationId": "N-2105"
}
~~~

Worker có thể tạo một trace khác:

~~~json
{
  "timestamp": "2026-11-12T10:00:02Z",
  "service": "mail-worker",
  "event": "mail.smtp.submitted",
  "traceId": "be92f8366cc44836a7f18c3be8ffbe01",
  "notificationId": "N-2105",
  "attemptId": "N-2105-A1",
  "provider": "primary-smtp",
  "elapsedMs": 742,
  "status": "SUBMITTED"
}
~~~

`notificationId` liên kết hai giai đoạn ngay cả khi tracing backend lấy mẫu bỏ một trong hai traces. Đây là lý do cần stable correlation IDs ngoài tracing context.

## 19. MDC trong logging và vấn đề thread reuse

MDC (*Mapped Diagnostic Context*) hỗ trợ gắn các trường context vào log. Ví dụ:

~~~java
public void processMail(String notificationId) {
    try (MDC.MDCCloseable ignored =
             MDC.putCloseable(
                 "notificationId", notificationId
             )) {

        log.info("Mail processing started");
        mailDelivery.submit(notificationId);
        log.info("Mail processing completed");
    }
}
~~~

`mailDelivery` là abstraction ứng dụng. Cần import SLF4J `org.slf4j.MDC`.

Thread pool tái sử dụng thread. Nếu task A để lại MDC `notificationId=A`, task B có thể bị ghi log nhầm thành A. Dùng scoped context và `finally`/restore để tránh rò data giữa các tác vụ.

Nếu cần bảo toàn giá trị MDC cũ ở cùng key, có thể chụp map trước khi set, rồi restore đúng trạng thái sau task; không giả định mọi logging implementation có cùng behavior.

## 20. TaskDecorator chỉ sao chép MDC

Một decorator có thể capture MDC lúc submit:

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submitted =
            MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                MDC.getCopyOfContextMap();

            try {
                if (submitted == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submitted);
                }

                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Gắn vào `ThreadPoolTaskExecutor`:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

Đây là propagation **MDC**, không tự bảo đảm OpenTelemetry/Brave span context được truyền đầy đủ. Nếu cần parent-child spans chính xác, dùng propagation API phù hợp tracing stack.

Đừng trộn nhiều decorators sao chép cùng context nếu không rõ precedence. Kiểm thử task A/B chạy trên cùng thread để chắc chắn MDC không rò.

## 21. Poller @Scheduled nên có trace riêng

Một scheduler có thể tự chạy khi không có HTTP request:

~~~java
@Component
public class MailOutboxPoller {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxPoller(MailOutboxDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString =
        "${app.mail.poll-delay-ms:1000}")
    public void poll() {
        dispatcher.dispatchDue();
    }
}
~~~

Có thể tạo observation `mail.outbox.poll` cho một lượt poll, sau đó observation riêng `mail.notification.process` cho từng job.

Nếu poll lấy 100 records, không nên nhét tất cả high-cardinality IDs vào một span. Poller span đo throughput, còn job-level observations/structured logs nối với từng notification.

Với durable outbox, job trace mới và span link (nếu có) thường rõ ràng hơn việc ép tất cả jobs thành descendants của một cron span.

## 22. Đo queue wait khác với SMTP duration

Một job có các mốc:

~~~text
createdAt       10:00:00.000
nextAttemptAt   10:00:00.000
processingAt    10:00:04.000
submittedAt     10:00:04.800

Queue wait      4.000 s
Processing      0.800 s
End-to-end      4.800 s
~~~

Nếu khách hàng báo mail chậm, SMTP chỉ chiếm 800 ms. Bốn giây còn lại có thể do poll interval, lease contention, TaskExecutor saturation hoặc rate limiter.

Nên đo:

- `mail.outbox.wait`: từ lúc job đến hạn tới lúc processing bắt đầu.
- `mail.template.render`: thời gian render nội dung.
- `mail.mime.prepare`: thời gian tạo MIME.
- `mail.smtp.submit`: thời gian transport.
- `mail.outbox.status_update`: thời gian lưu kết quả.

Nếu job được chủ động lên lịch gửi muộn, không được coi thời gian chờ tới lịch là queue saturation. Có thể đo planned delay và unplanned due lag riêng.

## 23. Outbox state là nguồn sự thật

Một state machine:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +--> SMTP accepted ------> SUBMITTED
   |
   +--> temporary failure --> RETRY_WAIT
   |                              |
   |                              +--> PROCESSING
   |
   +--> permanent failure --> FAILED
   |
   +--> uncertain result ----> AMBIGUOUS
~~~

Lưu trạng thái cần bao gồm:

- `notificationId` và `attemptId`.
- Old/new status.
- Attempt count.
- Worker/lease ID khi cần.
- Failure class và mã SMTP nếu có.
- `nextAttemptAt`.
- Timestamp UTC.
- Provider ID khi được cung cấp.

Trace có thể bị sampling hoặc mất exporter; database outbox row không được phụ thuộc vào trace backend để quyết định retry, dead-letter hay status.

## 24. Một email logic có thể có nhiều attempt traces

~~~text
notificationId = N-2105
   |
   +--> attempt A1
   |       SMTP 421 temporary error
   |       retry after backoff
   |
   +--> attempt A2
   |       read timeout after DATA
   |       outcome AMBIGUOUS
   |
   +--> attempt A3
           SMTP accepted
           duplicate risk exists
~~~

`notificationId` giữ nguyên; `attemptId` thay đổi. Một hệ thống có thể đặt một span cho worker job và child spans theo từng attempt; hoặc mỗi attempt tạo trace riêng liên kết qua notification ID khi thực thi tách biệt.

Không reset attempts mỗi khi retry worker hoặc restart process. Cần quan sát số lần gọi SMTP thực tế, không chỉ số lần task được đưa vào executor.

## 25. Timeout sau DATA có thể là AMBIGUOUS

~~~text
Application                       SMTP relay
   |                                   |
   |------ MIME + DATA end ----------->|
   |                                   | accepted?
   |<------- response lost -----------X|
   |
   +--> read timeout
~~~

Trace `mail.smtp.submit` có thể báo error, nhưng không chứng minh message chưa được chấp nhận. Nếu relay đã nhận và queue trước khi phản hồi bị mất, retry có thể dẫn tới hai email.

Do đó cần trạng thái `AMBIGUOUS`, provider-side reconciliation khi có API và một policy rõ về idempotency/rủi ro duplicate. MIME Message-ID không tự bảo đảm SMTP dedup.

Khi log lỗi, ghi “submission outcome unknown after DATA” nếu có bằng chứng phase phù hợp. Không log chắc chắn `NOT_SENT` khi chỉ có timeout.

## 26. Provider message ID và queue ID

Nếu SMTP server trả:

~~~text
S: 250 2.0.0 Queued as ABC123
~~~

ID `ABC123` có thể giúp operator tra mail log/queue. Một email có thể có nhiều ID:

- Internal notification ID.
- Attempt ID.
- MIME Message-ID header.
- SMTP relay queue ID.
- ESP message ID.

Không gộp các ID thành một trường. `JavaMailSender.send(...)` không trả standardized queue ID; phải dùng provider log/event API hoặc instrumentation riêng nếu muốn lấy ID này.

Khi provider message ID được ghi nhận, thêm nó vào attempt record để nối sang event delivered/bounced. Nếu không lấy được, cần fallback bằng timestamp, account, message header hoặc correlation field do provider hỗ trợ.

## 27. Provider webhook là một trace độc lập

Provider có thể gửi event sau SMTP submission:

~~~text
HTTP POST /mail-events
       |
       v
Verify provider signature
       |
       v
Deduplicate event
       |
       v
Resolve providerMessageId
       |
       v
Find notificationId
       |
       v
Update delivery status
       |
       +--> DELIVERED
       +--> BOUNCED
       +--> DEFERRED
~~~

Webhook tạo HTTP request mới nên phù hợp với trace mới. Nối nó với notification qua provider message ID hoặc correlation ID, có thể dùng span link nếu stack hỗ trợ.

**Không giữ span mail.smtp.submit mở nhiều giờ** để chờ delivery event. Submission và delivery là hai vòng đời khác nhau. Một mail có thể SUBMITTED rồi BOUNCED, và hai trạng thái đó không mâu thuẫn.

Provider webhook cần xác thực nguồn, dedup event IDs và xử lý out-of-order delivery events. Đừng tin một payload từ Internet tự nhận là complaint/bounce rồi cập nhật trạng thái mà không verify.

## 28. JSON structured log cho một attempt

~~~json
{
  "event": "mail.attempt.finished",
  "notificationId": "N-2105",
  "attemptId": "A2",
  "businessEventId": "E-441",
  "provider": "primary-smtp",
  "category": "TRANSACTIONAL",
  "workerId": "worker-3",
  "outcome": "TEMPORARY_FAILURE",
  "failureClass": "TRANSIENT",
  "smtpCode": "421",
  "elapsedMs": 821,
  "retryAt": "2026-11-12T10:05:00Z",
  "traceId": "eb598f2f108c4d6b8fae95dd161b4692"
}
~~~

Các giá trị là minh họa. Không tạo giả `smtpCode` hoặc `providerMessageId` khi không có bằng chứng. Không log raw MIME, recipient, subject, password, OTP hoặc auth tokens chỉ để log trông đầy đủ.

Đặt fields có tập giá trị nhỏ thành metric tags, nhưng không dùng `notificationId` hoặc recipient email làm tag vì cardinality cao.

## 29. SMTP debug log và nguy cơ rò dữ liệu

Jakarta Mail có thể ghi protocol transcript:

~~~properties
spring.mail.properties.mail.debug=true
~~~

Trong test hoặc điều tra có kiểm soát, log này có thể giúp thấy EHLO, TLS, AUTH, MAIL FROM, RCPT TO, DATA và response. Nhưng tùy library/version, transcript có thể chứa địa chỉ người nhận, thông tin xác thực, MIME header hoặc body.

- Không bật protocol debug thường trực trên production.
- AUTH Base64 **không** phải encryption.
- Chỉ bật trong scope/thời gian ngắn.
- Redact credentials và PII.
- Giới hạn quyền đọc và retention.
- Không copy raw transcript vào ticket công khai.

Protocol debug không tự tạo distributed spans cho từng SMTP command. Với lỗi timeout, nếu không thấy final DATA response, cần chấp nhận rằng kết quả có thể không rõ.

## 30. Metrics phải bổ sung traces

Các metric names ví dụ:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_outbox_pending` | Số job chờ |
| `mail_outbox_oldest_due_age_seconds` | Tuổi job tới hạn lâu nhất |
| `mail_outbox_claim_total` | Số lần claim theo outcome |
| `mail_send_attempts_total` | Số lần gọi SMTP thực |
| `mail_submission_total` | Submitted/failed/ambiguous |
| `mail_smtp_duration_seconds` | Distribution SMTP duration |
| `mail_render_duration_seconds` | Thời gian dựng MIME |
| `mail_queue_wait_seconds` | Độ trễ queue |
| `mail_retry_scheduled_total` | Số lần lên lịch retry |
| `mail_retry_exhausted_total` | Số email hết retry policy |
| `mail_smtp_timeout_total` | Số transport timeout |
| `mail_provider_events_total` | Delivery/bounce/defer events |
| `mail_executor_rejected_total` | Executor saturation |

Đây là tên do ứng dụng tự thiết kế, không mặc định tồn tại chỉ vì thêm Spring Mail.

Ví dụ khi `mail_queue_wait_seconds` P95 tăng, trace giúp chỉ ra worker claim chậm, còn log theo notification ID cho biết một job cụ thể bị rate limit hay lỗi DB.

Sampling có thể khiến chỉ một phần traces được export. Không đếm tất cả email từ số spans backend; dùng metrics/database state.

## 31. Sampling, retention và chi phí

Một hệ thống gửi nhiều mail nếu tạo hàng chục spans cho từng recipient có thể tốn đáng kể chi phí telemetry.

Nên:

- Sampling hợp lý cho luồng khỏe mạnh.
- Giữ error logs và trạng thái bền vững riêng.
- Tail-based sampling lỗi/chậm nếu backend hỗ trợ.
- Giới hạn số spans/attributes/events.
- Tránh instrument từng byte MIME hoặc từng template variable.
- Đặt retention và quyền truy cập theo mức độ nhạy cảm.
- Không dùng trace backend như hệ thống audit bất biến.

Nếu trace nguồn không có trong backend vì sampling, worker vẫn có thể tra bằng notification ID. Outbox lưu origin trace ID chỉ là thông tin hỗ trợ.

## 32. Quy tắc bảo vệ dữ liệu trong mail tracing

Email có thể chứa dữ liệu nhạy cảm:

- From, To, Cc, Bcc.
- Subject, HTML body và attachment.
- OTP/reset token.
- SMTP username/password.
- OAuth access token/refresh token.
- Provider error payload chứa địa chỉ người nhận.
- Template variables chứa dữ liệu khách hàng.

Nguyên tắc:

1. Không log raw body/attachment mặc định.
2. Không gắn recipient vào span name/metric tag.
3. Không đưa credentials vào trace baggage.
4. Không propagate toàn bộ Authorization headers qua mail worker.
5. Dùng internal notification ID cho correlation.
6. Redact provider errors khi chứa PII.
7. Giới hạn quyền đọc telemetry và thời gian lưu.
8. Cẩn trọng nếu muốn thêm custom trace headers vào email gửi ra ngoài.
9. Không lưu raw SMTP transcript ở môi trường production nếu không có quy trình kiểm soát.
10. Chỉ thu thập những thông tin cần cho mục đích vận hành hợp lệ.

Một trace ID không phải mật khẩu nhưng có thể làm lộ mối liên hệ giữa các hoạt động nội bộ; không chia sẻ vô điều kiện ra bên ngoài.

## 33. Nhiều recipients và batch send

Một `MimeMessage` có thể gửi tới nhiều recipients, hoặc `JavaMailSender` gửi nhiều messages trong một batch. Khi có failure:

- Một recipient có thể bị từ chối.
- Một số recipients được chấp nhận nếu cấu hình partial send cho phép.
- `MailSendException.getFailedMessages()` có thể giúp tìm message lỗi trong batch.
- Nested Jakarta Mail `SendFailedException` có recipient-level information.
- Tracing span chung báo ERROR không đủ để đánh dấu mọi message trong batch là NOT_SENT.

Nếu nghiệp vụ cần đối soát theo từng người nhận, hãy lưu per-recipient submission outcomes hoặc tách messages theo người nhận. Không log Bcc recipient vào logs/trace ngoài policy cho phép.

Đừng suy ra outcome toàn batch chỉ từ một exception tổng quát.

## 34. Attachment và template rendering có thể là điểm nghẽn

Với HTML mail có ảnh và attachment:

~~~text
mail.notification.process
    |
    +--> mail.template.load
    +--> mail.template.render
    +--> mail.attachment.resolve
    +--> mail.mime.prepare
    +--> mail.smtp.submit
~~~

Nếu download file chậm, `mail.smtp.submit` có thể vẫn ngắn nhưng total processing dài. Quan sát thêm storage fetch, rendering và MIME preparation khi cần.

Các thuộc tính có thể an toàn hơn raw content:

- Template key/version.
- Attachment count.
- MIME size bucket.
- Render duration.
- Provider category.
- Status/outcome.

Không ghi template variable values hoặc filenames chứa thông tin cá nhân vào trace. Nếu đo attachment size bằng cách đọc stream, tránh consume non-repeatable input stream làm MIME message không còn dữ liệu khi gửi.

## 35. Khi mail đến trễ, tìm lỗi theo thứ tự nào?

Một runbook:

1. Tìm business aggregate/event ID.
2. Xác nhận nghiệp vụ đã commit.
3. Tìm notification/outbox row.
4. Xem thời điểm created và nextAttemptAt.
5. Kiểm tra có suppression/consent decision không.
6. Tính queue wait.
7. Tìm worker claim, lease và executor metrics.
8. Xem template render/attachment spans.
9. Xem mọi SMTP attempts và failure class.
10. Kiểm tra final response/ambiguous outcome.
11. Nếu SUBMITTED, tra provider ID và downstream events.
12. So sánh với metrics cùng thời gian để tìm outage/rate limit diện rộng.

Không bắt đầu điều tra ở SMTP khi outbox chưa tồn tại. Cũng không đổ lỗi cho SMTP nếu job bị rate limiter giữ 10 phút trước khi gọi sender.

## 36. Một số tình huống chẩn đoán cụ thể

### A. Có business event nhưng không có outbox

Kiểm tra transaction rollback, repository insert, dedup key, preference/suppression, event publication và DB error. Một log “event published” chưa phải bằng chứng intent đã được lưu bền vững.

### B. Outbox PENDING lâu

Xem poller scheduling, nextAttemptAt, DB lock/lease, worker saturation, executor rejection và provider cooldown. Traces ở claim/poll giúp hơn trace SMTP vì sender chưa được gọi.

### C. PROCESSING nhưng không thấy SMTP span

Có thể renderer lỗi, worker chết, sampling bỏ trace, instrumentation chưa bật hoặc task chưa chạy. **Không thấy span không chứng minh send chưa xảy ra**. Đối chiếu logs, outbox state và server/provider evidence.

### D. SMTP read timeout

Xác định phase: trước kết nối, AUTH, RCPT TO, hay sau DATA. Khi không nhận final response sau DATA, đặt AMBIGUOUS nếu không có bằng chứng rõ. Reconciliation tốt hơn retry mù.

### E. SUBMITTED nhưng người dùng chưa thấy email

Tra provider queue/message ID, event delivered/bounced/deferred, spam/quarantine và mailbox rules. Không gửi lại chỉ vì Inbox chưa có ngay.

### F. Trace ID mất sau @Async

Kiểm tra TaskDecorator/context propagation, MDC cleanup, sampling, worker trace policy và notification ID. Không truyền transaction context sang thread khác để sửa log.

## 37. Kiểm thử trace/correlation theo pipeline

Một integration test có thể dùng GreenMail:

1. Tạo order và gọi use case thực.
2. Để transaction commit.
3. Assert outbox record chứa notification ID.
4. Kích hoạt worker hoặc poller có kiểm soát.
5. Đợi GreenMail nhận message.
6. Assert message subject/recipient/correlation header nếu được cấu hình.
7. Kiểm tra outbox status SUBMITTED.
8. Kiểm tra structured logs của enqueue, claim và submit cùng notification ID.
9. Nếu dùng test tracing handler, xác nhận các span/observation names và tags chính.
10. Đảm bảo không log password, body hoặc thông tin cá nhân không cần thiết.

### Test @Async propagation

Chạy task qua executor thật để xác nhận:

- Correlation ID xuất hiện trong worker đúng giá trị.
- Context propagation hoặc trace mới diễn ra theo thiết kế.
- Task A không rò MDC sang task B.
- Failure được ghi nhận dù task chạy async.

### Test retry

~~~text
Notification N-2105
  |
  +--> Attempt A1: temporary failure
  |       |
  |       v
  |    RETRY_WAIT
  |
  +--> Attempt A2: SUBMITTED
~~~

Kỳ vọng notification ID giữ nguyên, attempt IDs khác nhau, outbox status và metric attempts phù hợp.

### Test provider events

- Event signature hợp lệ mới được xử lý.
- Duplicate webhook không nhân đôi metric/state.
- Provider message ID liên kết đúng notification.
- Webhook có thể là trace riêng.
- Delivery status và submission status không bị lẫn.

Không cần gửi email Internet thật chỉ để test tracing. SMTP capture server xác nhận transport test, còn provider integration có contract tests riêng.

## 38. Anti-pattern cần tránh

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng traceId làm notificationId | Mất ổn định khi retry/process khác | Stable business ID |
| Chỉ log “mail sent” | Không biết đã enqueue/submit/deliver | State transitions |
| Coi HTTP 200 là email delivered | Caller có thể chỉ enqueue | Phân biệt các mốc |
| Giữ span mở tới provider webhook | Span rất dài, sai lifecycle | Trace webhook riêng |
| Ép durable worker làm child của request cũ | Khó hiểu quan hệ | Span link/correlation |
| Nghĩ MDC TaskDecorator là full tracing propagation | Sai trace parent | Dùng API tracing phù hợp |
| Quên dọn MDC | Log bị gán nhầm job | Scope/finally restore |
| Truyền raw Authorization vào baggage | Lộ bí mật | Minimal context |
| Recipient là span name | PII/cardinality cao | Stable names |
| Notification ID làm metric label | Cardinality cao | ID trong logs |
| Đếm số trace như số email chính xác | Sampling làm thiếu | Metrics/database |
| Bật SMTP debug toàn production | Lộ SMTP AUTH và MIME | Debug có kiểm soát |
| Chỉ trace SMTP, bỏ queue wait | Không thấy delay trước send | Poll/claim/render metrics |
| Exception nghĩa là chắc chắn chưa gửi | Timeout sau DATA có thể accepted | AMBIGUOUS/reconcile |
| Message-ID là provider queue ID | Đối soát sai | Lưu ID riêng |
| Mark SUBMITTED trước send | Crash làm mất mail | Update theo outcome thật |
| Không verify webhook | Có thể giả mạo status | Signature/auth + dedup |

## 39. Lộ trình triển khai

1. Chọn một `notificationId` ổn định cho mỗi email logic.
2. Liên kết business event ID/aggregate ID với outbox.
3. Dùng durable outbox nếu nghiệp vụ cần retry/recovery.
4. Thêm structured logs ở enqueue, claim, render, submit và status update.
5. Cấu hình Micrometer Observation/Tracing và exporter tương thích Spring version.
6. Thêm spans có tên ổn định quanh ranh giới quan trọng.
7. Chọn context propagation khi chuyển sang `@Async`/TaskExecutor.
8. Với durable workers, cân nhắc trace mới + span link và stable correlation ID.
9. Đo queue wait, render time và SMTP duration riêng.
10. Phân loại submission outcome rõ ràng, gồm AMBIGUOUS.
11. Lưu provider queue/message ID khi có nguồn đáng tin.
12. Tích hợp delivery/bounce webhook, signature verification và dedup.
13. Tạo dashboard/alerts cho backlog, timeouts, retry exhausted và provider failure.
14. Kiểm soát sampling, cardinality, dữ liệu nhạy cảm và retention.
15. Kiểm thử pipeline với SMTP server test và tracing test handler khi thích hợp.

~~~text
HTTP trace A
    |
    v
Business service + database transaction
    |
    v
Outbox row (notificationId=N-2105)
    |
    v
Worker trace B
    |
    +--> claim
    +--> render
    +--> smtp.submit
    +--> status update
    |
    v
Provider webhook trace C
    |
    +--> verify
    +--> dedup
    +--> correlate provider ID to N-2105
    +--> delivery state update
~~~

Ba traces có thể độc lập nhưng được nối bằng notification ID, business event ID và provider IDs.

## 40. Ghi nhớ

- Mail pipeline gồm business transaction, outbox, worker, MIME preparation, SMTP và provider events.
- Trace/span giúp xem thời lượng và quan hệ; database state mới là nguồn sự thật bền vững.
- Notification ID giữ nguyên qua retry, attempt ID thay đổi và trace ID có thể khác ở HTTP/worker/webhook.
- SMTP truyền thống không tự động propagate W3C trace context tới relay.
- Quan sát `JavaMailSender.send(...)` phía client không chứng minh Inbox delivery.
- Final success reply sau DATA là bằng chứng SMTP hop chấp nhận submission; response trước DATA chưa đủ.
- Timeout sau DATA có thể AMBIGUOUS và retry có nguy cơ duplicate.
- `@Async` cần context propagation có chủ đích; MDC-only decorator không đủ cho mọi tracing stack.
- Worker outbox chạy sau nhiều giờ thường nên tạo trace mới và nối bằng ID/span link.
- Structured logs theo notification ID quan trọng khi trace bị sampling hoặc exporter gặp sự cố.
- Không giữ một span mở nhiều giờ để chờ delivery webhook.
- Queue wait, template render và SMTP duration cần đo riêng để tìm đúng bottleneck.
- Dùng low-cardinality metric tags; tránh recipient/subject/body trong telemetry.
- Không log SMTP password/token, MIME body hoặc raw AUTH transcript.
- Tracing không thay thế outbox, idempotency, retry policy và provider reconciliation.

**Nguyên tắc cốt lõi:** để trace từ business event đến mail server, đừng chỉ thêm một span quanh `JavaMailSender.send(...)`. Hãy duy trì một chuỗi correlation từ **business event → outbox → worker attempts → SMTP submission → provider event**, dùng span để thấy thao tác, log để tra ID, metric để thấy xu hướng và durable state để biết chính xác hệ thống đã làm gì.
