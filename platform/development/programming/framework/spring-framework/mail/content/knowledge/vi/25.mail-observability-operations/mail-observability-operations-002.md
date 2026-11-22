# Đo thời gian tạo message và thời gian chờ SMTP

Trong ứng dụng Spring Framework Mail, yêu cầu gửi email có thể chậm vì nhiều lý do: template HTML được render lâu, file PDF chưa được tạo xong, attachment được đọc từ storage chậm, worker đợi trong queue, kết nối TCP/TLS phải thiết lập lại, SMTP AUTH mất nhiều round-trip hoặc mail server trả lời chậm. Nếu chỉ đặt một đồng hồ bao quanh toàn bộ nghiệp vụ, người vận hành khó biết nên tối ưu đoạn nào.

**Đo thời gian tạo message và thời gian chờ SMTP** là việc chia luồng gửi thành những khoảng đo có ranh giới rõ ràng, gắn kết quả thành công/thất bại và quan sát chúng qua logs, metrics hoặc traces.

Hai phép đo nền tảng:

1. **Message preparation/build duration:** từ khi ứng dụng bắt đầu dựng nội dung email cho đến khi hoàn tất phần chuẩn bị đã được quy định, chẳng hạn render template, xác định recipient, tạo MimeMessage và cấu hình MIME parts.
2. **SMTP submit-call duration:** từ ngay trước lúc gọi **JavaMailSender.send(...)** đến khi lời gọi đồng bộ đó trả về hoặc ném exception.

**Không đồng nhất submit-call duration với thời gian server SMTP xử lý.** Lời gọi send có thể bao gồm việc đọc attachment trễ, MIME serialization, DNS, TCP connect, TLS, AUTH, truyền DATA và chờ phản hồi. JavaMailSender không tự trả về một breakdown chuẩn cho từng giai đoạn.

Khi hệ thống dùng **@Async**, **@TransactionalEventListener(AFTER_COMMIT)** hoặc **transactional outbox**, còn phải đo thời gian tác vụ nằm chờ trong queue và khoảng thời gian từ khi nghiệp vụ commit tới khi SMTP relay chấp nhận message. Đây là những khoảng hoàn toàn khác với thời gian trong một lời gọi send.

## 1. Phân tách toàn bộ luồng gửi email

Một luồng ứng dụng điển hình:

~~~text
Business transaction
        |
        v
COMMIT + create outbox event
        |
        |---- Queue waiting ----|
        v                       |
Worker claims event            |
        |
        +-- Load snapshot and template
        +-- Render subject/plain text/HTML
        +-- Validate data and resolve resources
        +-- Build MimeMessage
        |
        |---- Build duration ---|
        v                       |
JavaMailSender.send(...)
        |
        +-- Deferred resource reading / MIME serialization
        +-- DNS / TCP connect when required
        +-- STARTTLS or implicit TLS handshake
        +-- SMTP AUTH
        +-- MAIL FROM / RCPT TO
        +-- DATA transfer / final response
        |
        |---- Send-call duration ----|
        v                            |
Success returned or exception        |
        |
        +-- Later delivery / bounce / mailbox processing
~~~

Không phải mọi hệ thống đều có outbox. Khi gửi đồng bộ trong HTTP request, phần queue có thể không tồn tại. Nhưng sự khác biệt giữa **build**, **send call**, **SMTP acceptance** và **delivery** vẫn quan trọng.

### 1.1. Bảng ranh giới metric

| Metric gợi ý | Bắt đầu | Kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| **mail.template.render.duration** | Bắt đầu render template | Renderer tạo xong text/HTML | Chi phí render |
| **mail.message.build.duration** | Bắt đầu chuẩn bị message | Build object xong theo contract | Chi phí chuẩn bị tầng ứng dụng |
| **mail.smtp.submit.call.duration** | Trước send(...) | send(...) trả về/ném lỗi | Latency đồng bộ caller quan sát |
| **mail.outbox.queue.delay** | Enqueue/commit event | Worker bắt đầu xử lý | Thời gian chờ được xử lý |
| **mail.attempt.processing.duration** | Worker bắt đầu một attempt | Attempt kết thúc | Tổng thời gian một lần xử lý |
| **mail.event.to.relay.acceptance** | Sự kiện nghiệp vụ đã lưu | Relay chấp nhận SMTP | Độ trễ end-to-end tới relay |
| **mail.outbox.pending.count** | Chụp trạng thái queue | — | Backlog |
| **mail.delivery.attempts** | Mỗi lần thử | Tăng 1 | Số attempt |

Tên metric chỉ là mẫu thiết kế; không phải tất cả đã có sẵn khi thêm Spring Boot Actuator.

### 1.2. Không nhầm với delivery latency

Một lời gọi JavaMailSender.send trả thành công thường có nghĩa transport đã hoàn thành theo mức phản hồi SMTP của relay. Nó **không chứng minh message đã vào inbox, không bị spam filter hoặc đã được người nhận đọc**.

Khi đo end-to-end, nên ghi rõ mốc là **relay acceptance**, không ghi chung chung là delivered nếu chưa có dữ liệu chuyển phát thực tế.

## 2. Dùng đồng hồ phù hợp với loại phép đo

Có hai loại thời gian:

- **Elapsed duration trong cùng process:** dùng **System.nanoTime()** hoặc clock đơn điệu của Micrometer Timer.
- **Timestamp để đối soát qua queue hoặc nhiều process:** dùng thời điểm lịch như **Instant** hoặc timestamp do database tạo, và tính đến sai lệch đồng hồ giữa các máy.

### 2.1. Vì sao System.nanoTime phù hợp?

Ví dụ:

~~~java
long started = System.nanoTime();

try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    long elapsedMillis =
            java.util.concurrent.TimeUnit.NANOSECONDS
                    .toMillis(elapsedNanos);

    log.info("operation.durationMs={}", elapsedMillis);
}
~~~

**System.nanoTime()** thích hợp đo khoảng trôi qua, không dùng để biểu diễn một ngày giờ theo lịch. Giá trị tuyệt đối của nó không nên lưu làm event timestamp để đối chiếu giữa hai máy.

### 2.2. Vì sao không dùng System.currentTimeMillis() cho timer?

Clock thời gian thực có thể được điều chỉnh bởi hệ điều hành hoặc đồng bộ NTP. Khi đó một phép trừ timestamp có thể sai so với thời gian trôi qua thật, thậm chí âm trong một số trường hợp. Độ phân giải millis cũng không tối ưu khi đo những giai đoạn ngắn.

Dùng nanoTime cho thời gian của method; dùng Instant cho createdAt, claimedAt, acceptedAt trong outbox.

### 2.3. Không trừ nanoTime từ hai process khác nhau

Một worker không thể lấy System.nanoTime được lưu từ service khác rồi trừ với System.nanoTime của nó. Hai giá trị không có mốc hệ quy chiếu chung. Queue delay phải dựa trên các timestamp có cùng chính sách clock và cần cân nhắc clock skew.

## 3. Tại sao phải đo cả thành công lẫn thất bại?

Mẫu code không đầy đủ:

~~~java
mailSender.send(message);
recordDuration(System.nanoTime() - started);
~~~

Nếu send ném MailException, câu lệnh recordDuration không chạy. Những lần timeout dài nhất có thể biến mất khỏi dashboard, khiến latency trông tốt hơn thực tế.

Cần đặt ghi thời gian trong **finally**:

~~~java
long started = System.nanoTime();
String outcome = "success";

try {
    mailSender.send(message);
} catch (RuntimeException ex) {
    outcome = "failure";
    throw ex;
} finally {
    long duration = System.nanoTime() - started;
    metrics.recordSubmit(duration, outcome);
}
~~~

Trong ví dụ, **metrics.recordSubmit(...)** là hàm ứng dụng tự thiết kế, không phải phương thức mặc định của JavaMailSender.

### 3.1. Ghi kết quả đúng ý nghĩa

- **success:** lời gọi send trả bình thường.
- **failure:** lời gọi send ném exception.
- **unknown outcome:** một trạng thái nghiệp vụ riêng khi không thể chắc chắn relay đã chấp nhận message hay chưa, ví dụ mất response sau DATA.

Một exception không tự chứng minh chắc chắn email chưa được gửi.

### 3.2. Không gọi catch Exception rồi retry ngay

Việc instrument phải giữ nguyên exception semantics. Lỗi AUTH, recipient, message preparation và timeout cần chính sách retry riêng. Timer chỉ quan sát, không quyết định biến mọi lỗi thành retryable.

## 4. Message build bao gồm những bước nào?

Trong hệ thống có email HTML, xây dựng message có thể gồm:

1. Đọc DTO snapshot cần thiết.
2. Chọn locale và template.
3. Render Subject, text/plain và text/html.
4. Format số tiền, ngày tháng.
5. Tạo MimeMessage bằng JavaMailSender.
6. Tạo MimeMessageHelper.
7. Thiết lập From, Reply-To, To, CC/BCC và Subject.
8. Thiết lập body.
9. Tạo multipart structure.
10. Thêm inline image/attachment references.
11. Hoàn tất chuẩn bị theo hợp đồng của service.

Không nhất thiết các bước này đều nằm trong một factory. Quan trọng là định nghĩa ranh giới đo phải nhất quán.

### 4.1. Nếu render template nằm ngoài timer

Giả sử:

~~~java
String html = templateRenderer.render(data);

long started = System.nanoTime();
MimeMessage message = buildMime(html);
long buildNanos = System.nanoTime() - started;
~~~

Timer chỉ đo phần buildMime, **không bao gồm render**. Nếu dashboard ghi “message preparation duration”, cần ghi chú rõ hoặc mở rộng timer bao cả render.

### 4.2. Dùng metric con khi cần tìm bottleneck

Có thể tạo:

~~~text
mail.template.render.duration
mail.attachment.generate.duration
mail.resource.load.duration
mail.message.build.duration
mail.smtp.submit.call.duration
~~~

Nhưng đừng tăng số metric vô hạn. Bắt đầu từ build và send; chỉ thêm bước con khi cần phân biệt những chi phí lớn.

### 4.3. Đừng giữ transaction database trong khi chờ SMTP

Nếu gọi send bên trong method **@Transactional**, duration SMTP có thể trở thành thời gian giữ connection/lock của database. Nên tách giao dịch dữ liệu khỏi việc gửi để tránh liên kết độ trễ mạng với hiệu năng transaction.

## 5. Ví dụ đo build và send bằng System.nanoTime

Một service minh họa:

~~~java
public void sendOrderMail(OrderMailData data) {
    long buildStarted = System.nanoTime();

    MimeMessage message;
    try {
        message = buildMessage(data);
    } finally {
        recordBuildNanos(
                System.nanoTime() - buildStarted
        );
    }

    long submitStarted = System.nanoTime();

    try {
        mailSender.send(message);
    } finally {
        recordSubmitNanos(
                System.nanoTime() - submitStarted
        );
    }
}
~~~

**buildMessage**, **recordBuildNanos** và **recordSubmitNanos** là hàm ví dụ của ứng dụng. Code này làm rõ vị trí bắt đầu/kết thúc timer.

Nếu build ném exception, đoạn submit sẽ không được thực hiện. Điều này đúng: lỗi chuẩn bị message không được tính thành một lần gửi SMTP.

### 5.1. Ví dụ kết quả

~~~text
mail.message.build.duration = 14 ms
mail.smtp.submit.call.duration = 780 ms
~~~

Có thể kết luận build object mất 14 ms và lời gọi send mất 780 ms.

**Không thể kết luận tất cả 780 ms là server processing.** Nó có thể bao gồm kết nối, handshake, auth, serialize MIME và network transfer.

## 6. Micrometer Timer là lựa chọn phù hợp cho metrics

**Micrometer Timer** ghi duration, count và những thông tin thống kê khác tùy registry/cấu hình. Nó có thể được xuất ra backend như Prometheus để phân tích phân phối latency.

Trong một ứng dụng Spring Boot, thường dùng Actuator/Micrometer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Nếu dùng Prometheus, ứng dụng còn cần registry/exporter tương ứng. Đoạn dependency chỉ minh họa, không yêu cầu một phiên bản cụ thể.

**Không giả định JavaMailSender mặc định đã xuất sẵn metric riêng cho build và send theo hai phạm vi của bài.** Cần instrument ứng dụng hoặc có một instrumentation khác được cấu hình phù hợp.

### 6.1. Timer.Sample

Một mẫu:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    performOperation();
} finally {
    sample.stop(
            registry.timer(
                    "mail.operation.duration",
                    "outcome",
                    "completed"
            )
    );
}
~~~

Đây là cơ chế đo đơn giản, nhưng trong ứng dụng thật cần thay tag outcome theo kết quả success/failure như ví dụ tiếp theo.

### 6.2. Tại sao ưu tiên Timer hơn một log cho mỗi millis?

Timer tổng hợp các lần chạy, hỗ trợ histogram/percentile và cảnh báo theo thời gian. Log theo từng message vẫn hữu ích khi điều tra event cụ thể nhưng không nên là nguồn duy nhất để xác định p95/p99.

## 7. Service Spring đo build và SMTP submit-call

DTO minh họa:

~~~java
public record OrderMailData(
        String recipient,
        String orderNumber,
        String messageText
) {}
~~~

Service:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class TimedOrderMailService {

    private final JavaMailSender sender;
    private final MeterRegistry registry;

    public TimedOrderMailService(
            JavaMailSender sender,
            MeterRegistry registry
    ) {
        this.sender = sender;
        this.registry = registry;
    }

    public void sendConfirmation(OrderMailData data) {
        MimeMessage message = buildTimed(data);
        submitTimed(message);
    }

    private MimeMessage buildTimed(OrderMailData data) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            MimeMessage message = sender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            false,
                            "UTF-8"
                    );

            helper.setFrom("orders@example.org");
            helper.setTo(data.recipient());
            helper.setSubject(
                    "Xác nhận đơn hàng " + data.orderNumber()
            );
            helper.setText(data.messageText(), false);

            return message;
        } catch (MessagingException ex) {
            outcome = "failure";
            throw new MailPreparationException(
                    "Cannot prepare confirmation",
                    ex
            );
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.message.build.duration",
                            "kind", "order_confirmation",
                            "outcome", outcome
                    )
            );
        }
    }

    private void submitTimed(MimeMessage message) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (MailException ex) {
            outcome = "failure";
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "kind", "order_confirmation",
                            "outcome", outcome
                    )
            );
        }
    }
}
~~~

### 7.1. Các ranh giới của đoạn code

- Build bắt đầu trước createMimeMessage và kết thúc khi các field đã được đặt.
- Nếu build thất bại, không gọi send.
- Send timer bắt đầu trước JavaMailSender.send và dừng khi nó trả về hoặc ném exception.
- Hai timer dùng tag **kind** và **outcome** với số giá trị hữu hạn.
- Không đưa recipient, subject, body hoặc password vào metric tag.

### 7.2. Không coi đây là toàn bộ pipeline

Ví dụ nhận DTO đã được chuẩn bị và không render template hay attachment. Nếu service thực tế truy vấn database, dựng PDF hoặc render HTML, quyết định có tính phần đó vào build metric hay đặt metric con.

### 7.3. Dữ liệu sai phải bị xử lý đúng

Code dùng recipient từ DTO. Trong ứng dụng thật, cần validation địa chỉ và quyền gửi theo hợp đồng. Instrumentation không thay thế validation hoặc chính sách bảo mật dữ liệu.

### 7.4. Chỉ dùng success/failure ở Timer không đủ để xử lý retry

Kết quả MailException cần được phân loại theo nguyên nhân để outbox quyết định RETRY_WAIT, INVALID_RECIPIENT, PAUSED_CONFIG hoặc UNKNOWN_OUTCOME. Metric chỉ cung cấp tín hiệu tổng hợp.

## 8. Attachment và lazy MIME serialization

Một điểm rất quan trọng: **thời gian tạo object MimeMessage không nhất thiết bao gồm thời gian đọc toàn bộ attachment**.

Ví dụ:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoiceFile),
        "application/pdf"
);
~~~

Tùy overload và cách Jakarta Mail dùng DataSource, lời gọi addAttachment có thể chỉ gắn tham chiếu Resource. Dữ liệu thật có thể được đọc khi message được serialize bên trong send.

Kết quả:

~~~text
Build object duration:  9 ms
Send call duration:   1800 ms
~~~

Send-call duration có thể cao do I/O đọc file hoặc encode MIME, chứ không hoàn toàn do SMTP server chậm.

### 8.1. Phân biệt object build và message materialization

- **Object build:** tạo MimeMessage/MimeMessageHelper và thiết lập MIME structure.
- **Materialization:** tạo các byte MIME sẽ được truyền đi; có thể cần mở stream, đọc file và encode attachment.

Nếu muốn đo materialization, cần instrumentation phù hợp với giai đoạn serialize. Không đặt tên timer object build là “thời gian đọc toàn bộ attachment” khi nó chưa đọc.

### 8.2. Đọc trước vào ByteArrayResource

Nếu ứng dụng đọc attachment trước:

~~~java
byte[] invoiceBytes =
        attachmentLoader.loadWithLimit(invoiceId);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoiceBytes),
        "application/pdf"
);
~~~

Thời gian đọc file nằm trong build/preparation nếu timer bao gồm loadWithLimit. Việc tạo byte[] từ file vẫn tiêu tốn thời gian và memory; nó không tự tối ưu tổng latency mà chỉ thay đổi giai đoạn chi phí xuất hiện.

### 8.3. Không serialize hai lần để có metric đẹp

Trong test, có thể gọi **message.writeTo(...)** để xác minh MIME. Nhưng trong production, serialize vào ByteArrayOutputStream trước rồi để JavaMailSender serialize lần nữa có thể nhân đôi CPU/I/O và tăng memory, đặc biệt với attachment lớn.

Cần tối ưu thực chất, không đổi hiệu năng ứng dụng chỉ để đo một metric.

### 8.4. Metric kích thước message

Nếu cần so sánh, có thể phân nhóm **size_class=small/medium/large** dựa trên kích thước hợp lý. Không biến mỗi số byte hoặc tên attachment thành một metric tag riêng.

## 9. Lời gọi JavaMailSender.send làm gì?

Ở mức khái niệm:

~~~text
JavaMailSender.send
      |
      +-- Prepare/serialize deferred MIME data
      +-- Resolve SMTP host / TCP connection
      +-- TLS: implicit TLS or STARTTLS
      +-- SMTP AUTH if required
      +-- MAIL FROM / RCPT TO
      +-- DATA serialization and transfer
      +-- Wait for SMTP response
      |
      v
Return normally or throw
~~~

Các bước có thể thay đổi theo implementation, cấu hình session, batch và transport. Nếu có connection reuse, chi phí kết nối/handshake của một message không giống lần gửi đầu tiên.

### 9.1. DNS và TCP connect

Thời gian send có thể tăng vì DNS lookup hoặc kết nối bị chặn. Server có thể chưa nhận bất kỳ SMTP command nào.

### 9.2. TLS handshake

STARTTLS hoặc implicit TLS cần thương lượng giao thức/cipher và xác minh certificate. Nếu certificate không hợp lệ, send có thể kết thúc với MessagingException/SSLHandshakeException.

### 9.3. SMTP AUTH

Provider có thể yêu cầu xác thực, làm tăng round-trips. AUTH thất bại phải phân biệt với server phản hồi chậm.

### 9.4. MAIL FROM và RCPT TO

Nhiều recipient có thể tăng thời gian trao đổi lệnh hoặc tạo partial recipient failure. Đừng coi kết quả toàn message là kết quả của từng recipient khi API trả exception.

### 9.5. DATA

Body và attachment được serialize, truyền qua mạng, sau đó client chờ phản hồi cuối từ server. Dữ liệu lớn và băng thông thấp có thể làm phần này chiếm nhiều thời gian.

### 9.6. Relay accept không đồng nghĩa delivered

JavaMailSender trả thành công thường cho biết transport hoàn thành theo phản hồi SMTP. Nó không chứng minh provider đã chuyển message tới mailbox hoặc người nhận đã mở.

## 10. Phân biệt thời gian client call với server processing

Có thể biểu diễn gần đúng:

~~~text
T_submit_call
  = T_client_overhead
  + T_connect_when_needed
  + T_tls_and_auth
  + T_smtp_commands
  + T_mime_serialization
  + T_network_transfer
  + T_response_wait
~~~

Đây là phân rã theo khái niệm. JavaMailSender không tự trả từng thành phần qua API send.

**Không thể dùng một phép đo bao ngoài send để suy ra chính xác SMTP server xử lý DATA trong bao nhiêu milliseconds.**

Muốn đo sâu hơn có thể cần:

- Telemetry do SMTP provider công bố.
- Instrumentation trong transport hoặc SMTP proxy có quyền kiểm soát.
- Tracing riêng của connection/TLS/network.
- SMTP test server tạo độ trễ theo từng phase.
- Phân tích log giao thức có kiểm soát, chỉ khi cần và đã đánh giá rủi ro PII/secrets.

### 10.1. Không bật SMTP debug mặc định chỉ để có timing

Protocol debug của Jakarta Mail có thể in địa chỉ, command và metadata. Nó không nhất thiết có timestamp/phase duration chuẩn cho việc tổng hợp metric. Hãy ưu tiên Timer/Observation cho production.

### 10.2. Tên metric phản ánh điều thực sự đo

Tên tốt:

~~~text
mail.smtp.submit.call.duration
~~~

Tên dễ gây hiểu nhầm:

~~~text
smtp.server.processing.duration
~~~

nếu chỉ đo bên ngoài JavaMailSender.send.

## 11. MimeMessagePreparator có một ranh giới đặc biệt

Spring cho phép:

~~~java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(
                    mimeMessage,
                    false,
                    "UTF-8"
            );

    helper.setFrom("news@example.org");
    helper.setTo("an@example.net");
    helper.setSubject("Thông báo");
    helper.setText("Nội dung", false);
});
~~~

Trong API **send(MimeMessagePreparator)**, callback dựng message được chạy bên trong lời gọi send. Nếu đo bên ngoài lời gọi này, timer sẽ bao gồm **cả callback chuẩn bị và transport**.

### 11.1. Đo callback bằng Timer riêng

~~~java
mailSender.send(mime -> {
    Timer.Sample buildSample = Timer.start(registry);
    String outcome = "success";

    try {
        MimeMessageHelper helper =
                new MimeMessageHelper(
                        mime,
                        false,
                        "UTF-8"
                );

        helper.setFrom("news@example.org");
        helper.setTo("an@example.net");
        helper.setSubject("Thông báo");
        helper.setText("Nội dung", false);
    } catch (MessagingException ex) {
        outcome = "failure";
        throw ex;
    } catch (RuntimeException ex) {
        outcome = "failure";
        throw ex;
    } finally {
        buildSample.stop(
                registry.timer(
                        "mail.message.build.duration",
                        "kind", "notification",
                        "outcome", outcome
                )
        );
    }
});
~~~

Nếu đồng thời đo bên ngoài send(preparator), **hai scope chồng lấn**. Không cộng hai duration đó như thể chúng độc lập.

### 11.2. Trừ callback duration khỏi total có được không?

Giá trị total - callback có thể giúp tham khảo, nhưng nó vẫn gồm nhiều overhead phía client và network. **Không đồng nghĩa server xử lý đúng bằng hiệu số này.**

### 11.3. Nếu muốn hai phạm vi rõ

Có thể dựng MimeMessage trước, đo build, sau đó gọi **send(MimeMessage)** và đo send. Vẫn cần ghi chú lazy resource serialization.

## 12. SimpleMailMessage có đặc điểm đo khác

Với thư plain text:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notifications@example.org");
message.setTo("an@example.net");
message.setSubject("Thông báo");
message.setText("Nội dung");

mailSender.send(message);
~~~

Phần xây dựng SimpleMailMessage là việc tạo object và lưu chuỗi; JavaMailSenderImpl có thể chuyển nó thành MimeMessage khi gửi, nên send-call duration có thể chứa thêm công việc nội bộ này.

Không so sánh trực tiếp build latency của **SimpleMailMessage nhỏ** với **MimeMessage có file PDF lớn** mà không phân loại message type hoặc size.

## 13. Đo queue delay trong transactional outbox

Một hệ thống gửi mail tin cậy có thể ghi outbox event cùng transaction nghiệp vụ rồi để worker xử lý sau.

Ví dụ timeline:

~~~text
10:00:00  Business transaction commits
10:00:45  Worker claims outbox event
10:00:46  Message preparation completed
10:00:48  SMTP relay accepted message
~~~

Các khoảng đo:

- Queue delay: gần 45 giây.
- Build/processing: từ lúc worker bắt đầu đến khi message xong.
- Send-call: giai đoạn JavaMailSender.send.
- Event-to-relay: khoảng 48 giây.

### 13.1. Queue delay và SMTP latency là hai chuyện khác nhau

Một message nằm chờ 5 phút trong outbox nhưng send hoàn tất trong 250 ms không phải là “SMTP chậm 5 phút”. Bottleneck có thể là worker scheduling, thread pool, lease, database query hoặc retry backoff.

### 13.2. Schema timestamp minh họa

~~~text
eventId
createdAt
firstClaimedAt
availableAt
attemptStartedAt
attemptFinishedAt
relayAcceptedAt
status
attempts
~~~

Đặt timestamp nhất quán giữa các worker và database, đồng thời theo dõi clock skew nếu nhiều host sử dụng nguồn thời gian khác nhau.

### 13.3. Tách retry backoff và scheduler lag

- **Initial queue delay:** từ tạo event đến claim đầu tiên.
- **Retry wait:** thời gian cố ý chờ đến nextAttemptAt.
- **Scheduler lag:** tác vụ đã đến thời điểm khả dụng nhưng worker chưa claim.
- **Attempt processing:** thời gian thực thi một lần thử.

Nếu gộp tất cả thành queue latency, đội vận hành có thể tăng số worker để xử lý một khoảng backoff vốn được thiết kế có chủ đích.

## 14. Đo end-to-end từ nghiệp vụ đến relay accept

Trong trải nghiệm người dùng, metric quan trọng có thể là:

~~~text
T_to_relay_accept
  = relayAcceptedAt - businessCommittedAt
~~~

Nó bao gồm queue, scheduling, render, build, send và các lần retry, tùy timeline thực tế.

### 14.1. Mốc commit cần rõ

Nếu outbox createdAt được ghi **trước commit** bên trong transaction, nó có thể hơi sớm hơn thời điểm commit thật. Cần chọn định nghĩa nhất quán và ghi chú khác biệt đó trong dashboard.

### 14.2. Không cộng duration chồng lấn

Nếu một Timer bao toàn bộ worker attempt đã gồm render/build/send, đừng cộng nó thêm vào các Timer render/build/send rồi gọi tổng đó là end-to-end. Chỉ cộng các đoạn không trùng lặp.

### 14.3. Không ép duration thành công cho event FAILED

Một tác vụ không bao giờ được relay chấp nhận không có relayAcceptedAt. Theo dõi **time-to-terminal-failure** và **count failed** riêng nếu cần SLA xử lý lỗi.

## 15. @Async: đo trong worker, không phải chỉ ở caller

Ví dụ:

~~~text
HTTP request
     |
     +-- Submit async task
     |       |
     |       v
     |    Return immediately
     |
     v
HTTP response

Executor worker later:
     |
     +-- Build message
     +-- JavaMailSender.send
     +-- Record actual send-call duration
~~~

Nếu đo quanh lời gọi @Async từ request, có thể chỉ đo thời gian submit task vào executor. Muốn đo SMTP, đặt timer **trong method chạy trên worker**.

### 15.1. Executor queue wait

Nếu task chờ trong executor queue, nó cũng cần metric riêng khi latency này ảnh hưởng SLO.

### 15.2. Async không tự làm task bền vững

@Async không tự lưu ý định gửi vào database hay durable queue. Khi process dừng, task trong memory có thể mất. Nếu thông báo quan trọng, dùng transactional outbox hoặc queue có retention phù hợp.

### 15.3. Exception không quay lại request

Với void async listener, lỗi gửi không nhất thiết quay về request đã kết thúc. Worker cần ghi metric failure, trạng thái outbox và retry riêng.

## 16. Đo batch send và từng message

JavaMailSender hỗ trợ một lời gọi gửi nhiều message:

~~~java
mailSender.send(messageA, messageB, messageC);
~~~

Một timer bao ngoài là **batch duration**, không phải ba message duration riêng.

Ví dụ:

~~~text
Batch size:        3
Batch send time:   3.6 s
~~~

**Không chia đều 3.6/3** rồi coi đó là latency của từng message. Connection có thể được dùng chung, mỗi message có kích thước và thời gian khác nhau, và một message có thể bị lỗi.

### 16.1. Nếu cần theo dõi per-message

Có thể gửi/đo từng message độc lập nếu trade-off chấp nhận được, hoặc instrument thêm ở adapter/provider. Khi batch có partial failures, cần theo dõi trạng thái từng event, không chỉ outcome tổng.

### 16.2. Count gửi ở tầng nào?

Một lời gọi send chứa ba MimeMessage có **1 invocation**, nhưng có thể **3 message attempts**. Đặt tên metric và mẫu đo khác nhau để tránh nhầm.

## 17. Timeout của SMTP không phải overall deadline

Cấu hình Spring Boot ví dụ:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: mail-service
    password: secret-from-secure-runtime
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

Tên account và password ở đây chỉ là placeholder; trong triển khai thật phải lấy secret từ cơ chế quản lý bí mật, không lưu credential thật trong source.

| Property | Nhóm chờ thường được kiểm soát |
| --- | --- |
| **mail.smtp.connectiontimeout** | Tạo kết nối |
| **mail.smtp.timeout** | Đọc phản hồi |
| **mail.smtp.writetimeout** | Ghi dữ liệu ra socket |

Giá trị thường tính bằng milliseconds trong Jakarta Mail SMTP provider tương ứng.

### 17.1. Read timeout 10 giây không có nghĩa send tối đa 10 giây

Một lời gọi có thể gồm nhiều lần đọc/ghi, handshake, authentication và transfer. Timeout của một thao tác I/O không đồng nghĩa overall deadline cho toàn bộ quy trình.

### 17.2. Metrics không thay thế timeout

Timer giúp biết duration, không tự hủy một operation quá lâu. Cần timeout network và cơ chế xử lý task phù hợp.

### 17.3. Timeout quá thấp có thể gây lỗi giả

Nếu gửi attachment lớn hoặc provider bình thường cần thời gian đáp ứng dài, timeout quá ngắn làm tăng số lỗi và retry, thậm chí tạo duplicate. Nên điều chỉnh dựa trên phân phối latency thực tế và SLA.

### 17.4. Timeout sau DATA

Nếu client đã gửi DATA nhưng không nhận được response cuối, relay có thể đã chấp nhận message. Metric failure phải được đọc cùng khả năng **UNKNOWN_OUTCOME**; retry có thể tạo email trùng.

## 18. Phân tích retry và backoff trong tổng độ trễ

Một event gửi email được thử ba lần:

~~~text
Attempt 1: 2 s -> temporary failure
Backoff:  30 s
Attempt 2: 5 s -> temporary failure
Backoff: 120 s
Attempt 3: 1 s -> accepted
~~~

Tổng thời gian lời gọi send là 8 giây, còn thời gian backoff là 150 giây. End-to-end có thể lớn hơn 158 giây do queue, build và scheduling.

**Không gắn nhãn 158 giây là “SMTP processing time”.**

### 18.1. Mỗi attempt nên có metric riêng

Số attempts, build duration, submit-call duration, error category và nextAttemptAt cần được theo dõi theo task.

### 18.2. Tách log event và metric tag

Event ID, attempt ordinal, recipient reference nên xuất hiện trong log/tracing được kiểm soát. Metric tag chỉ dùng tập giá trị hữu hạn như **attempt_group=first/retry** nếu thực sự cần.

### 18.3. Retry phải có deadline nghiệp vụ

Email reset password hoặc OTP có thể hết hạn. Khi email chỉ được chấp nhận sau khi link hết hạn, tối ưu submit-call latency không sửa được tính đúng đắn của trải nghiệm. Cần đo end-to-end và giới hạn retry phù hợp.

## 19. Phân phối latency: average, p50, p95, p99

Một average có thể che phần tail latency.

| Thống kê | Cách đọc |
| --- | --- |
| **Count** | Số lượt gọi hoặc số mẫu |
| **Mean/average** | Thời gian trung bình trong cửa sổ |
| **p50** | Mốc mà khoảng nửa mẫu không vượt quá |
| **p95** | Khoảng 95% mẫu không vượt quá |
| **p99** | Khoảng 99% mẫu không vượt quá |
| **Max** | Mẫu lớn nhất theo cửa sổ thống kê |
| **Histogram** | Phân phối mẫu theo khoảng ngưỡng |

Ví dụ:

~~~text
p50 send = 0.4 s
p95 send = 1.1 s
p99 send = 12 s
~~~

Hầu hết lời gọi nhanh nhưng một nhóm nhỏ có thể bị timeout hoặc có resource lớn.

### 19.1. Percentile ở lưu lượng thấp

Với 5 message mỗi giờ, percentile trong cửa sổ một phút có thể không có ý nghĩa ổn định. Dashboard nên hiển thị count cùng percentile và chọn cửa sổ phù hợp.

### 19.2. Không average các p95 giữa instance

Percentile không phải giá trị cộng tuyến tính. Nếu muốn p95 tổng hệ thống, dùng histogram buckets được tổng hợp đúng thay vì tính trung bình p95 từng process.

### 19.3. Outcome success và failure cần tách

Những lần failure timeout dài có thể làm p95 tổng tăng. Để hiểu tình hình, xem latency theo **outcome** cùng **error ratio**, không chỉ một percentile gộp.

## 20. Cấu hình Micrometer histogram

Ví dụ Timer:

~~~java
Timer submitTimer = Timer.builder(
        "mail.smtp.submit.call.duration"
    )
    .description("Synchronous JavaMailSender send duration")
    .tag("kind", "order_confirmation")
    .tag("outcome", "success")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
            java.time.Duration.ofMillis(250),
            java.time.Duration.ofSeconds(1),
            java.time.Duration.ofSeconds(3),
            java.time.Duration.ofSeconds(10)
    )
    .register(registry);
~~~

Sau đó có thể ghi:

~~~java
submitTimer.record(
        java.time.Duration.ofMillis(850)
);
~~~

Các ngưỡng là ví dụ. Trong ứng dụng thật, thống nhất cách cấu hình Timer giữa các instance và outcome, tránh các timer cùng tên/tag nhưng distribution settings khác nhau.

### 20.1. Histogram có chi phí

Nhiều bucket và nhiều combinations của tags có thể tạo rất nhiều time series. Chỉ bật histogram cho những Timer quan trọng và kiểm soát cardinality.

### 20.2. Không đưa raw size vào tag

Nếu muốn phân tích attachment:

~~~text
size_class=small
size_class=medium
size_class=large
~~~

Các bucket phải được định nghĩa ổn định. Không gắn mỗi số byte thành một tag value riêng.

## 21. Cách đọc Timer trong Prometheus

Metric Micrometer có tên:

~~~text
mail.smtp.submit.call.duration
~~~

có thể được Prometheus exporter chuyển thành các series tương tự:

~~~text
mail_smtp_submit_call_duration_seconds_count
mail_smtp_submit_call_duration_seconds_sum
mail_smtp_submit_call_duration_seconds_bucket
~~~

Series **bucket** phụ thuộc histogram/SLO configuration và exporter. Không giả định nó luôn tồn tại.

### 21.1. Throughput

~~~promql
sum(
  rate(mail_smtp_submit_call_duration_seconds_count[5m])
)
~~~

Đây là tốc độ **send invocation được timer ghi**, không phải số message đã tới inbox.

### 21.2. Average submit-call duration

~~~promql
sum(
  rate(mail_smtp_submit_call_duration_seconds_sum[5m])
)
/
sum(
  rate(mail_smtp_submit_call_duration_seconds_count[5m])
)
~~~

Kết quả thường tính bằng seconds. Khi không có traffic, denominator có thể bằng 0; dashboard cần xử lý trạng thái không có mẫu phù hợp.

### 21.3. p95 từ histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(
      mail_smtp_submit_call_duration_seconds_bucket{
        outcome="success"
      }[5m]
    )
  )
)
~~~

Có thể phân nhóm theo **kind** nếu muốn so sánh các loại email, ví dụ tổng hợp by (le, kind).

## 22. Tag metrics nên dùng giá trị ít biến động

| Tag nên cân nhắc | Giá trị ví dụ |
| --- | --- |
| **kind** | order_confirmation, password_reset |
| **outcome** | success, failure |
| **provider** | primary_smtp, backup_smtp |
| **error_category** | auth, timeout, tls, recipient, unknown |
| **size_class** | small, medium, large |
| **attempt_group** | first, retry |

Không đưa trực tiếp:

- Email người nhận.
- Subject/body.
- Password, OAuth token.
- Order ID, event ID, Message-ID.
- Filename tùy ý hoặc URL.
- Raw exception message.
- Tenant ID nếu có số lượng rất lớn và backend không được thiết kế cho nó.

Những giá trị riêng lẻ có thể thuộc **structured log/trace** được phân quyền, không phải metric labels đại trà.

### 22.1. Lỗi SMTP nên map thành category

Đừng dùng exception.getMessage() làm tag. Một diagnostic text có thể chứa địa chỉ, host hoặc nội dung do provider trả về và làm nổ số time series.

### 22.2. Low cardinality là yêu cầu vận hành

Mỗi tổ hợp tag có thể tạo series riêng. Khi lưu lượng email lớn, việc gắn userId hoặc recipient sẽ làm metrics backend tốn memory/storage và giảm khả năng query.

## 23. Structured log và tracing bổ sung cho metrics

Metric trả lời **bao lâu và bao nhiêu lần**. Log/trace giúp tìm **event nào, attempt nào, lỗi gì**.

Ví dụ log an toàn:

~~~text
eventId=mail-event-3024
kind=order_confirmation
attempt=2
buildDurationMs=13
submitDurationMs=10024
outcome=failure
errorCategory=read_timeout
~~~

Không cần log địa chỉ người nhận hoặc nội dung email.

### 23.1. Correlation ID

Khi có outbox, một ID ổn định giúp liên kết business transaction → outbox event → worker attempt → SMTP result.

### 23.2. Không bật Jakarta Mail protocol debug thường trực

Debug có thể lộ địa chỉ, AUTH metadata và thông tin nhạy cảm tùy provider. Để theo dõi performance production, ưu tiên metrics/traces và log đã giới hạn dữ liệu.

### 23.3. Tracing không thay thế stopwatch

Một trace span có thể biểu diễn operation duration và liên kết nhiều service. Nếu đã dùng Observation/Tracing để ghi cùng một metric, cần tránh instrument trùng một scope.

## 24. Dùng Micrometer Observation khi ứng dụng đã triển khai tracing

Ví dụ ý tưởng:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation.createNotStarted(
        "mail.smtp.submit",
        observationRegistry
    )
    .lowCardinalityKeyValue(
            "mail.kind",
            "order_confirmation"
    )
    .observe(() -> mailSender.send(message));
~~~

**observationRegistry** và **message** là dữ liệu được chuẩn bị bởi ứng dụng. Các handlers/exporters quyết định observation này tạo metrics hay traces như thế nào.

### 24.1. Tránh duplicate instrumentation

Nếu cả Timer thủ công và Observation đều đo send với cùng ý nghĩa, dashboard có thể có hai tên metric khác nhau cho một scope hoặc thậm chí đếm trùng. Chọn quy ước nhất quán.

### 24.2. Trace fields vẫn cần privacy review

Ngay cả high-cardinality trace fields cũng có thể được lưu trong backend. Không đưa token hoặc nội dung email vào attributes chỉ vì chúng không tạo metric series.

## 25. Unit test Timer không cần SMTP server

Để test instrumentation:

- Dùng **Mockito** mock JavaMailSender.
- Dùng MimeMessage thật trong bộ nhớ.
- Dùng **SimpleMeterRegistry**.
- Dùng **Micrometer MockClock** để điều khiển duration.
- Dùng JUnit 5 xác nhận count, outcome và số lời gọi send.

Không nên dùng **Thread.sleep(100)** rồi assert timer chính xác 100 ms; scheduler và tải CI có thể làm test flaky.

### 25.1. Ví dụ MockClock

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.time.Duration;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class TimedOrderMailServiceTest {

    @Test
    void measuresSubmitDurationWithoutNetwork() {
        MockClock clock = new MockClock();

        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(
                        SimpleConfig.DEFAULT,
                        clock
                );

        JavaMailSender sender = mock(JavaMailSender.class);

        MimeMessage mimeMessage = new MimeMessage(
                Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage())
                .thenReturn(mimeMessage);

        doAnswer(invocation -> {
            clock.add(Duration.ofMillis(250));
            return null;
        }).when(sender).send(any(MimeMessage.class));

        TimedOrderMailService service =
                new TimedOrderMailService(sender, registry);

        service.sendConfirmation(
                new OrderMailData(
                        "an@example.net",
                        "ORDER-001",
                        "Đơn hàng đã xác nhận."
                )
        );

        Timer sendTimer = registry
                .find("mail.smtp.submit.call.duration")
                .tag("kind", "order_confirmation")
                .tag("outcome", "success")
                .timer();

        assertNotNull(sendTimer);
        assertEquals(1, sendTimer.count());
        assertEquals(
                250.0,
                sendTimer.totalTime(TimeUnit.MILLISECONDS),
                0.01
        );

        Timer buildTimer = registry
                .find("mail.message.build.duration")
                .tag("outcome", "success")
                .timer();

        assertNotNull(buildTimer);
        assertEquals(1, buildTimer.count());

        verify(sender, times(1))
                .send(any(MimeMessage.class));
    }
}
~~~

Test điều khiển thời gian bằng MockClock thay vì chờ 250 ms thật. Nó kiểm tra **Timer đã ghi đúng duration của lời gọi gửi được giả lập**, không phải hiệu năng SMTP ngoài đời.

### 25.2. Vì sao build Timer không assert milliseconds cụ thể?

MockClock chỉ tiến thêm bên trong send mock. Phần build diễn ra theo code bình thường và có thể ghi duration bằng 0 trên clock giả. Mục tiêu test build ở đây là timer được tạo và count đúng; nếu cần test một duration build khác 0, hãy đưa clock hoặc giả lập renderer vào đúng scope.

## 26. Test timer khi gửi thất bại

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;

@Test
void recordsFailureDuration() {
    SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

    JavaMailSender sender = mock(JavaMailSender.class);

    when(sender.createMimeMessage()).thenReturn(
            new MimeMessage(
                    Session.getInstance(new Properties())
            )
    );

    doThrow(new MailSendException("simulated"))
            .when(sender).send(any(MimeMessage.class));

    TimedOrderMailService service =
            new TimedOrderMailService(sender, registry);

    assertThrows(
            MailSendException.class,
            () -> service.sendConfirmation(
                    new OrderMailData(
                            "an@example.net",
                            "ORDER-002",
                            "Đơn hàng đã xác nhận."
                    )
            )
    );

    Timer failure = registry
            .find("mail.smtp.submit.call.duration")
            .tag("outcome", "failure")
            .timer();

    assertNotNull(failure);
    assertEquals(1, failure.count());
}
~~~

### 26.1. Test nhánh build lỗi

Khi recipient/template gây lỗi lúc build:

- Build timer phải ghi outcome=failure.
- Send timer không có thêm mẫu cho event đó.
- JavaMailSender.send không được gọi.

Đây là cách ngăn lỗi đầu vào làm bẩn metrics SMTP.

### 26.2. Test instrument không phải benchmark

Một unit test với mock không đo độ trễ network, TLS hay provider. Nó xác nhận việc ghi metric hoạt động theo code.

## 27. Test tích hợp với SMTP server có kiểm soát

Nếu muốn quan sát hiệu năng gửi thực tế, dùng SMTP test server/fake transport có thể tạo delay tại phase mong muốn:

| Giai đoạn | Tình huống test |
| --- | --- |
| Greeting | Server gửi 220 trễ |
| STARTTLS | TLS handshake chậm hoặc certificate sai |
| AUTH | Response chậm hoặc trả lỗi |
| RCPT TO | Trì hoãn chấp nhận recipient |
| DATA | Throttle truyền dữ liệu |
| Final response | Trì hoãn phản hồi sau DATA |
| Network | Cắt kết nối, timeout |

Các test này có thể kiểm tra send-call duration tăng theo delay và timer failure vẫn được ghi.

### 27.1. Không assert chính xác từng millisecond qua socket

Độ trễ scheduler/JVM/network làm tổng thời gian dao động. Hãy dùng các ngưỡng có biên phù hợp hoặc so sánh tương đối trên môi trường test được kiểm soát.

### 27.2. Không load test SMTP production tùy tiện

Gửi hàng nghìn email qua provider thật có thể vượt rate limit, ảnh hưởng uy tín sender hoặc vô tình gửi thư cho người dùng. Chỉ load test trên môi trường/account được phép và dữ liệu giả.

### 27.3. Test attachment size

So sánh các message nhỏ/lớn để xem mức ảnh hưởng của đọc file và truyền byte. Không mặc định chênh lệch chỉ do SMTP server nếu resource được đọc muộn trong send.

## 28. Cách đọc các tình huống chậm

### 28.1. Build chậm, send nhanh

~~~text
build p95 = 2.7 s
send p95  = 0.4 s
~~~

Điều tra template, query, tạo PDF, load attachment, CPU/GC. Chưa có cơ sở thay SMTP provider.

### 28.2. Build nhanh, send chậm

~~~text
build p95 = 0.02 s
send p95  = 7.0 s
~~~

Điều tra connect, TLS, AUTH, provider throttling, DATA, kích thước MIME và lazy resource read. Chưa kết luận server chậm khi chưa loại trừ client-side work.

### 28.3. Queue delay cao, send nhanh

~~~text
queue p95 = 180 s
build p95 = 0.02 s
send p95  = 0.4 s
~~~

Điều tra worker capacity, scheduling, lease, backlog, retry backoff và database query outbox.

### 28.4. Failure duration gần timeout

~~~text
send failure ~= 10 s
errorCategory=read_timeout
~~~

Có thể liên quan mail.smtp.timeout khoảng 10 giây. Cần xem root cause và phase; tổng send không nhất thiết bằng đúng một lần read timeout.

### 28.5. p99 rất cao nhưng p95 tốt

~~~text
p50 = 0.3 s
p95 = 1.0 s
p99 = 20 s
~~~

Có thể có nhóm nhỏ message bị timeout hoặc attachment lớn. Phân loại theo kind/outcome/size_class thay vì thêm tag recipient.

### 28.6. Request nhanh hơn sau khi chuyển @Async

Có thể chỉ là thay đổi ranh giới: request giờ không đợi SMTP. Hãy đo thực sự trong worker và xem end-to-end to relay accept trước khi tuyên bố hệ thống gửi nhanh hơn.

## 29. Dashboard tối thiểu cho vận hành

Một dashboard nên hiển thị:

| Nhóm | Chỉ số |
| --- | --- |
| Message build | p50, p95, p99, count, errors |
| Template render | p95 và cache/error nếu cần |
| SMTP submit call | p50, p95, p99 theo outcome |
| Throughput | Send attempts/second |
| Failure | Error ratio và nhóm lỗi |
| Outbox | Pending, oldest pending, queue delay |
| Retry | Attempts, scheduled retries, terminal failure |
| End-to-end | Commit-to-relay acceptance |
| Capacity | Worker active count, executor saturation |
| Message class | Kind và size bucket |

### 29.1. Alert phải dẫn đến hành động

Ví dụ:

- Build p95 tăng sau khi đổi template → kiểm tra renderer.
- Send p95 tăng và TLS errors cao → kiểm tra TLS/provider.
- Queue oldest age vượt SLA → kiểm tra worker capacity/locks.
- Retry queue tăng → xem rate limit hoặc sự cố provider.
- AUTH failure tăng → kiểm tra credential/policy, không retry mù.
- UNKNOWN_OUTCOME tăng → đối soát trước khi retry để giảm duplicate.

### 29.2. Hiển thị sample count

Một percentile từ vài message khác về độ tin cậy với percentile từ hàng chục nghìn message. Đừng alert quá nhạy khi lượng mẫu rất nhỏ.

## 30. SLO ví dụ cho email

Có thể xây dựng mục tiêu minh họa:

~~~text
SLO-1:
  95% successful SMTP submit calls finish within 3 seconds.

SLO-2:
  99% order-confirmation events reach SMTP relay
  within 2 minutes of business commit.

SLO-3:
  No high-priority outbox event remains pending for
  more than 10 minutes without an observable state.
~~~

Đây không phải chuẩn chung cho Spring Mail. Cần hiệu chỉnh theo provider, loại message, SLA, lưu lượng và business criticality.

### 30.1. SLO vận hành không đồng nghĩa SLO người nhận mở thư

SMTP relay accept là một mốc kỹ thuật, không phải read receipt. Không dùng metric send-call để khẳng định người dùng đã đọc email.

### 30.2. Email bảo mật có deadline khác newsletter

Password reset có thể không còn ý nghĩa khi link hết hạn. Newsletter có thể chấp nhận thời gian queue dài hơn. Không áp cùng deadline cho mọi loại nếu không có yêu cầu nghiệp vụ.

## 31. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đo HTTP request tổng | Không biết queue/build/send chậm | Tách scope |
| Dùng currentTimeMillis cho elapsed | Dễ bị clock adjustment | nanoTime hoặc Timer |
| Ghi metric sau send mà không finally | Bỏ mất lỗi/timeout | Ghi cả success/failure |
| Gọi send-call là server processing | Sai ý nghĩa kỹ thuật | Đặt tên chính xác |
| Coi addAttachment đã đọc hết file | Lazy read có thể nằm trong send | Ghi rõ build contract |
| Serialize MIME hai lần để đo | Tăng CPU/I/O/memory | Instrument thao tác cần thiết |
| Đo @Async từ caller | Chỉ đo enqueue | Đo trong worker |
| Trộn queue delay vào SMTP latency | Chẩn đoán nhầm nghẽn | Metric riêng |
| Đặt recipient/Subject làm tag | Rò rỉ PII và high cardinality | Low-cardinality tags |
| Chỉ nhìn average | Bỏ qua tail latency | Histogram/p95/p99 |
| Average p95 giữa các instance | Không đúng thống kê | Tổng hợp histogram |
| Chia đều batch duration | Không đúng per-message | Đo batch và trạng thái riêng |
| Coi send success là delivered | SMTP accept khác inbox | State chính xác |
| Dùng Thread.sleep trong unit test | Flaky CI | MockClock |
| Bật protocol debug thường trực | Lộ dữ liệu, tăng overhead | Structured metrics |
| Timeout nghĩa là chắc chắn chưa gửi | Có thể sau DATA | UNKNOWN_OUTCOME |
| Timeout property là overall deadline | Thực tế chỉ giới hạn I/O tương ứng | Đo và kiểm soát toàn luồng |

## 32. Câu hỏi thường gặp

**1. Đo thời gian tạo message bằng cách nào?**

Đặt timer trước khối render/build MimeMessage và dừng khi khối đó hoàn tất. Ghi rõ thời gian có bao gồm template, resource loading và attachment generation hay không.

**2. Đo thời gian chờ SMTP bằng cách nào?**

Đặt timer quanh JavaMailSender.send(...) và ghi trong finally. Đây là **synchronous submit-call duration**, không phải chính xác server processing duration.

**3. Vì sao send mất lâu khi build nhanh?**

Do network, DNS, TLS, AUTH, SMTP round-trip, MIME serialization hoặc attachment được đọc muộn.

**4. Vì sao nên dùng System.nanoTime()?**

Nó phù hợp đo elapsed time bên trong process và không phụ thuộc vào việc chỉnh đồng hồ lịch.

**5. Có thể dùng Instant cho queue delay không?**

Có, khi dùng timestamp bền vững và xử lý clock skew. Không trừ các giá trị nanoTime từ các máy khác nhau.

**6. Timer có ghi lỗi không?**

Có nếu ứng dụng dừng sample trong finally ngay cả khi operation ném exception. Không nên chỉ ghi timer ở nhánh thành công.

**7. Spring Boot có tự sinh hai metric build/send không?**

Không nên mặc định như vậy. Chúng là metric với scope do ứng dụng định nghĩa và cần được instrument, exporter theo cấu hình.

**8. Có đo riêng STARTTLS handshake bằng JavaMailSender Timer không?**

Không bằng một timer bao ngoài send. Cần transport-level instrumentation hoặc telemetry phù hợp để đo từng phase.

**9. MimeMessagePreparator ảnh hưởng timer ra sao?**

Callback chuẩn bị message chạy bên trong send(preparator), nên timer bao ngoài có cả build và transport. Đo callback riêng nếu cần phân biệt.

**10. SimpleMailMessage có cần Timer build không?**

Có thể, nhưng build object thường ngắn; JavaMailSenderImpl có thể chuyển sang MIME trong send. Cần giải thích rõ scope.

**11. Vì sao PDF khiến send chậm hơn?**

File có thể được đọc và encode khi MIME serialize bên trong send, đồng thời nhiều byte hơn làm network transfer lâu hơn.

**12. Có nên gọi MimeMessage.writeTo trước send chỉ để đo?**

Không nên trong production nếu phải serialize hai lần hoặc tốn memory lớn. Có thể dùng ở test hoặc instrumentation đặc biệt.

**13. Queue delay có phải SMTP latency không?**

Không. Queue delay là thời gian tác vụ chưa bắt đầu send, còn send-call là thời gian lời gọi gửi đang chạy.

**14. @Async có tự làm SMTP nhanh hơn không?**

Không. Nó chuyển công việc sang thread khác, giúp request trả nhanh nhưng duration của worker vẫn cần được đo.

**15. p95 là gì?**

Mốc mà khoảng 95% mẫu trong một tập quan sát không vượt quá. Nó không phải max và không cho thấy toàn bộ tail.

**16. Có nên gắn eventId làm metric tag không?**

Không. Nó tạo high cardinality; nên dùng trong log/trace có kiểm soát.

**17. Test Timer mà không dùng Thread.sleep được không?**

Có. Micrometer MockClock kết hợp SimpleMeterRegistry cho phép điều khiển thời gian ở unit test.

**18. Batch send gồm ba message thì duration thuộc message nào?**

Thuộc toàn batch nếu timer bao ngoài một lời gọi send. Không tự chia đều; cần instrumentation khác để đo per-message.

**19. Read timeout 10 giây có phải send tối đa 10 giây không?**

Không nhất thiết. Send gồm nhiều bước I/O và có thể chờ nhiều lần.

**20. Nếu send ném timeout thì email chắc chắn chưa được chấp nhận?**

Không. Timeout sau DATA có thể xảy ra khi SMTP relay đã nhận message. Retry có nguy cơ tạo bản sao.

**21. Metric end-to-end quan trọng khi nào?**

Đặc biệt khi có outbox, queue, retry hoặc async. Nó phản ánh thời gian từ business commit tới SMTP relay acceptance.

**22. Có thể dùng JavaMailSenderImpl.testConnection để đo send latency không?**

Không. testConnection kiểm tra kết nối/đăng nhập ở mức nhất định, không dựng và truyền một message thực. Gọi nó cho mỗi email còn thêm kết nối và overhead, nên không thay thế Timer quanh send.

## 33. Ghi nhớ về đo thời gian tạo message và thời gian chờ SMTP

**Một phép đo tốt cần có ranh giới tốt.** Trong Spring Framework Mail, hãy tách thời gian render/build message khỏi thời gian lời gọi đồng bộ **JavaMailSender.send(...)**. Gọi đoạn thứ hai là **SMTP submit-call duration** vì nó có thể bao gồm MIME serialization, đọc attachment trễ, DNS/TCP, TLS, AUTH, DATA và chờ phản hồi — không phải chỉ thời gian SMTP server xử lý.

Dùng **System.nanoTime()** hoặc **Micrometer Timer** để đo elapsed time trong process. Ghi trong **finally** để không bỏ mất mẫu lỗi và timeout. Khi có **@Async** hoặc outbox, đặt Timer trong worker và đo thêm **queue delay**, **retry backoff** và **event-to-relay-acceptance**; không cộng các khoảng đo chồng lấn.

Theo dõi count, error ratio, histogram và p50/p95/p99; phân nhóm bằng các tag hữu hạn như kind, outcome và error_category. Không đưa recipient, Subject, token hoặc event ID vào metric tags. Kiểm thử instrumentation bằng **JUnit 5, Mockito và Micrometer MockClock**, rồi dùng SMTP test server có kiểm soát khi cần tìm hiểu transport thực tế.

Mục tiêu không chỉ là trả lời “gửi email mất bao lâu”, mà là biết **giai đoạn nào gây chậm, độ trễ đó ảnh hưởng người dùng thế nào và nên tối ưu template, attachment, queue hay SMTP** mà không làm mất tính chính xác và bảo mật của hệ thống.
