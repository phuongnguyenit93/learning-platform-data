# Cảnh báo tỷ lệ lỗi, timeout và bounce tăng

## 1. Vì sao hệ thống gửi email cần cảnh báo chủ động?

Trong ứng dụng sử dụng **Spring Framework Mail**, việc gọi **JavaMailSender.send(...)** là một bước kỹ thuật trong chuỗi gửi thông báo. Đối với vận hành, câu hỏi quan trọng không chỉ là “hàm gửi có chạy không?” mà còn là:

- Bao nhiêu lần nộp email cho SMTP server thất bại?
- Lỗi đang tập trung ở nhà cung cấp, một loại thông báo hay một môi trường nào?
- **Connect timeout**, **read timeout** hoặc **write timeout** có tăng bất thường không?
- SMTP server đã nhận message, nhưng sau đó có nhiều người nhận báo **bounce** không?
- Hệ thống có đang retry liên tục mà không giải quyết nguyên nhân?
- Notification có đang tồn đọng trong outbox lâu hơn mức chấp nhận được?
- Việc cảnh báo có bị nhiễu khi lưu lượng thấp, do trễ webhook hoặc do cùng một email được thử nhiều lần không?

Một sự cố email có thể âm thầm kéo dài: web API vẫn trả thành công, transaction nghiệp vụ đã commit, nhưng thông báo không được gửi hoặc liên tục bị trả lại. Nếu chỉ tìm lỗi khi khách hàng phản ánh, hệ thống sẽ khó xác định phạm vi ảnh hưởng và thời điểm bắt đầu.

Bài này tập trung vào thiết kế **metric, dashboard, alert rule và quy trình phản ứng sự cố** cho ba tín hiệu:

1. **Tỷ lệ lỗi gửi tăng** — các lần SMTP submission thất bại hoặc kết quả chưa rõ tăng.
2. **Timeout tăng** — DNS/TCP/SMTP chậm, kết nối không phản hồi hoặc mất phản hồi sau DATA.
3. **Bounce tăng** — server/provider chấp nhận gửi ban đầu nhưng sau đó báo không chuyển phát được.

Các ví dụ đặt trong ngữ cảnh Spring Boot, JavaMailSender, **Micrometer**, **Prometheus**, **Alertmanager** và một hệ thống notification/outbox. Công cụ cụ thể có thể thay đổi, nhưng các nguyên tắc về định nghĩa tín hiệu và phân loại lỗi vẫn giữ nguyên.

## 2. Quan sát đúng hành trình email

Một notification thường đi qua nhiều giai đoạn:

~~~text
Business event
      |
      v
Notification / outbox record
      |
      v
Mail worker / renderer
      |
      v
JavaMailSender + Jakarta Mail
      |
      | DNS, TCP, TLS, SMTP AUTH, MAIL FROM, RCPT TO, DATA
      v
Submission SMTP server / ESP
      |
      | Phản hồi chấp nhận hoặc từ chối ban đầu
      v
Provider queue / relay
      |
      | Chuyển tới các mail server phía nhận
      v
Receiving system
      |
      +-- Delivered
      +-- Deferred
      +-- Bounced
      +-- Không có phản hồi rõ ràng
      |
      v
Webhook / DSN / provider event
      |
      v
Delivery-state processor
~~~

Hai điểm quan sát quan trọng:

**Submission:** ứng dụng có nộp message thành công cho SMTP server/ESP không? Một lời gọi **send(...)** trả về bình thường thường biểu thị server đã chấp nhận message ở chặng đầu, không bảo đảm đến Inbox.

**Delivery:** provider hoặc hệ thống nhận báo lại đã chuyển phát, bị hoãn hay bị trả lại như thế nào? Phần lớn thông tin này đến **bất đồng bộ** qua webhook, API hoặc **Delivery Status Notification (DSN)**.

Một biểu đồ “email success rate” mà chỉ đếm **send() không ném exception** thực ra đang đo **SMTP submission acceptance**, không phải tỷ lệ email người nhận đã thấy.

## 3. Định nghĩa trạng thái trước khi định nghĩa metric

Nếu không có trạng thái chuẩn, dashboard dễ đếm một message nhiều lần hoặc gộp các kết quả không liên quan.

### Trạng thái submission

| Trạng thái | Ý nghĩa |
|---|---|
| **PENDING** | Ý định gửi đã được lưu nhưng chưa thử SMTP |
| **PROCESSING** | Worker đang claim và xử lý |
| **ACCEPTED / SUBMITTED** | SMTP server/ESP đã chấp nhận message ở chặng submission |
| **RETRY_WAIT** | Lần thử không thành công và đã lên lịch retry |
| **FAILED** | Đã xác định không thể tiếp tục theo chính sách |
| **UNKNOWN** | Không xác định được server đã chấp nhận hay chưa |

### Trạng thái delivery

| Trạng thái | Ý nghĩa |
|---|---|
| **DELIVERED** | Provider/hệ thống nhận báo đã chuyển phát theo định nghĩa của họ |
| **DEFERRED** | Chuyển phát đang bị hoãn |
| **BOUNCED** | Có bằng chứng chuyển phát không thành công |
| **COMPLAINED** | Provider báo phản hồi phàn nàn/spam complaint |
| **UNKNOWN** | Chưa có thông tin cuối đáng tin cậy |

**SUBMITTED không đồng nghĩa DELIVERED**. **DEFERRED không đồng nghĩa BOUNCED**. Một message được retry có thể phát sinh nhiều lần submission attempt nhưng chỉ có **một notification nghiệp vụ**.

Đây là lý do hệ thống nên lưu định danh **notification ID**, **attempt ID**, **provider message ID** và **event ID** riêng nếu cần.

## 4. Phân loại lỗi trước khi tạo cảnh báo

Một **MailException** có thể bọc nhiều nguyên nhân. Nếu dashboard chỉ đặt tất cả vào nhãn “mail_error”, đội vận hành khó biết cần sửa cấu hình, mạng, dữ liệu recipient hay chính sách provider.

| Nhóm lỗi chuẩn hóa | Ví dụ | Khả năng phục hồi |
|---|---|---|
| **dns** | UnknownHostException, DNS resolver failure | Có thể tạm thời hoặc sai hostname |
| **connection_refused** | ConnectException trước SMTP session | Có thể service tắt/sai port |
| **connect_timeout** | TCP không kết nối trong thời hạn | Có thể do network, firewall, route |
| **read_timeout** | Chờ SMTP reply quá lâu | Phụ thuộc pha, có thể chưa rõ kết quả |
| **write_timeout** | Không ghi kịp dữ liệu lên socket | Phụ thuộc pha, có thể chưa rõ kết quả |
| **tls** | SSLHandshakeException, chứng chỉ sai | Thường cần kiểm tra endpoint/truststore |
| **auth** | MailAuthenticationException | Thường cần sửa credential/quyền |
| **smtp_4xx** | SMTP từ chối tạm thời | Retry có backoff theo chính sách |
| **smtp_5xx** | SMTP từ chối vĩnh viễn | Kiểm tra recipient, sender, policy |
| **mime_preparation** | MailParseException, lỗi template/MIME | Thường cần sửa dữ liệu/code |
| **provider_policy** | Rate limit, account quota, reputation | Phụ thuộc phản hồi và hợp đồng provider |
| **unknown** | Không đủ bằng chứng về nguyên nhân/pha | Cần điều tra hoặc đối soát |

Đây là **error category do ứng dụng định nghĩa**, không phải danh sách enum bắt buộc của Spring Mail. Mã SMTP và exception class thực tế phải được phân tích cùng ngữ cảnh.

Đặc biệt:

- Không mặc định **mọi SMTP 5xx là recipient không tồn tại**.
- Không mặc định **mọi SocketTimeoutException là retryable**.
- Không phân loại lỗi kết nối TCP là một phản hồi SMTP 4xx/5xx.
- Nếu một batch chứa kết quả một phần, phải tính riêng theo message/recipient hoặc nêu rõ mức độ không chắc chắn.

## 5. Ba phép đo quan trọng không có cùng mẫu số

Để tính tỷ lệ đúng, trước hết cần xác định **đơn vị được đếm**.

### Tỷ lệ lỗi submission theo attempt

~~~text
Submission failure rate =
  số SMTP submission attempts có kết quả thất bại
  -------------------------------------------------
  tổng SMTP submission attempts trong cùng khoảng
~~~

Ví dụ có 100 lần thử SMTP: 91 accepted, 7 failed, 2 unknown.

- Tỷ lệ **confirmed failure** = 7 / 100 = 7%.
- Tỷ lệ **unhealthy-or-unknown** = (7 + 2) / 100 = 9%.
- Tỷ lệ **confirmed acceptance** = 91 / 100 = 91%.

Nên hiển thị **UNKNOWN** riêng, không gộp nó vào confirmed failure để đánh mất ngữ nghĩa. Có thể có một alert “submission unhealthy” gộp FAILED + UNKNOWN, nhưng phải đặt tên rõ.

### Tỷ lệ timeout theo attempt

~~~text
Timeout attempt rate =
  số attempts bị timeout
  ------------------------
  tổng attempts cùng khoảng
~~~

Đây là **tỷ lệ theo attempt**, không phải tỷ lệ người nhận không được chuyển phát. Nếu một notification bị timeout ba lần, nó tạo ba timeout attempts.

### Tỷ lệ bounce theo notification đã submitted

~~~text
Bounce rate (theo notification) =
  số notification đã submitted và có bounce phù hợp
  --------------------------------------------------
  số notification đã submitted trong cùng cohort
~~~

Khác biệt quan trọng: bounce đến **sau submission**, có thể trễ từ vài giây tới nhiều giờ hoặc hơn. Vì vậy không phải lúc nào số bounce nhận trong 10 phút chia cho số thư gửi trong 10 phút cũng phản ánh đúng tỷ lệ bounce của lô email đó.

## 6. Đừng đếm notification và attempt lẫn nhau

Ví dụ một notification **N100**:

~~~text
N100
 |
 +-- Attempt 1 -> Connect timeout
 |
 +-- Attempt 2 -> SMTP 451
 |
 +-- Attempt 3 -> SMTP accepted
 |
 +-- Delivery event -> BOUNCED
~~~

Nếu đếm attempts:

- Tổng attempts: **3**.
- Failed attempts: **2**.
- Accepted attempts: **1**.

Nếu đếm notification:

- Notification nghiệp vụ: **1**.
- Có submission accepted: **1**.
- Bounced: **1**.

Với một cảnh báo lỗi transport, đếm attempt giúp nhận biết áp lực SMTP. Với báo cáo mức độ ảnh hưởng đến khách hàng, cần đếm **notification/recipient duy nhất**. Đừng nói “200 khách hàng bị lỗi” chỉ vì có 200 failed attempts; chúng có thể thuộc 20 notification được retry 10 lần.

Nếu một MimeMessage được gửi tới nhiều người nhận, kết quả có thể khác nhau theo recipient. Để đo bounce chính xác, nên có một **notification-recipient identity** hoặc record delivery riêng cho từng người, thay vì chỉ dùng Message-ID và giả định tất cả người nhận có trạng thái giống nhau.

## 7. Chọn cửa sổ thời gian và ngưỡng tối thiểu

Alert dựa vào tỷ lệ cần có cả **ngưỡng tỷ lệ** lẫn **điều kiện đủ mẫu**.

Ví dụ:

~~~text
Trong 10 phút:
  2 failures / 4 attempts = 50%

Trong 10 phút:
  200 failures / 4.000 attempts = 5%
~~~

Tỷ lệ 50% nghe nghiêm trọng nhưng có thể chỉ có 4 lần thử. Tỷ lệ 5% với 4.000 attempts ảnh hưởng tới nhiều notification hơn và đáng quan tâm.

Một chính sách minh họa:

| Signal | Cửa sổ ngắn | Cửa sổ dài | Điều kiện kích hoạt |
|---|---|---|---|
| Submission failures | 5–10 phút | 30–60 phút | Tỷ lệ vượt ngưỡng **và** đủ attempts |
| Timeout | 5–10 phút | 30 phút | Tỷ lệ tăng hoặc số tuyệt đối tăng |
| Bounce | 1–6 giờ | 24 giờ hoặc cohort trưởng thành | Bounce ratio tăng và đủ mẫu |
| Outbox backlog | 5–15 phút | 1 giờ | Pending age/queue depth vượt mục tiêu |
| Worker liveness | 2–5 phút | Theo lịch polling | Không có heartbeat/scrape như dự kiến |

Các con số chỉ minh họa, không phải ngưỡng chuẩn của Spring Mail. Cần hiệu chỉnh theo lưu lượng, lịch gửi chiến dịch, SLA và baseline thực tế.

### Vì sao bounce cần cửa sổ riêng?

Khi một chiến dịch gửi hàng nghìn email lúc 09:00, nhiều bounce có thể đến lúc 09:30. Nếu lấy bounce trong 09:30–09:40 chia cho submissions của đúng khoảng đó, mẫu số có thể gần bằng 0 và sinh một tỷ lệ vô nghĩa.

Với bounce, **cohort theo thời điểm submission** thường đáng tin hơn. Phần dưới sẽ trình bày cách dùng cả cảnh báo proxy theo thời gian nhận event và tỷ lệ cohort có độ trễ đủ lâu.

## 8. Kiến trúc giám sát khuyến nghị

Một cách tổ chức:

~~~text
Spring Mail application
    |
    +-- Mail submission metrics
    |       attempts, accepted, failed, unknown, duration
    |
    +-- Worker / outbox metrics
    |       pending, retry, oldest age, expired lease
    |
    v
Micrometer -> /actuator/prometheus
    |
    v
Prometheus ----> Alert rules ----> Alertmanager
    |                                  |
    v                                  v
Grafana dashboards              On-call / incident routing

ESP/SMTP provider
    |
    +-- Bounce / delivery / deferral webhooks
    |
    v
Verified webhook receiver
    |
    +-- Persist provider events idempotently
    +-- Update delivery state
    +-- Emit delivery metrics
    |
    v
Prometheus and/or cohort analytics
~~~

**Không nên tạo một counter duy nhất “email_failed_total” từ tất cả nguồn**, vì nó dễ đếm hai lần cùng một notification: một lần SMTP failure và một lần webhook bounce. Hãy duy trì tên metric và trạng thái riêng cho từng giai đoạn.

## 9. Bộ metric nền tảng

Một bộ tối thiểu có thể gồm:

| Metric logic | Loại | Ý nghĩa |
|---|---|---|
| **mail.submissions** | Counter | Số lần thử gửi SMTP; phân tách result/category |
| **mail.submission.duration** | Timer | Thời gian thực thi submission attempt |
| **mail.notification.submitted** | Counter | Số notification-recipient được xác nhận submitted lần đầu |
| **mail.delivery.events** | Counter | Số delivery event hợp lệ đã nhận, theo loại |
| **mail.notification.bounced** | Counter | Số notification-recipient được xác nhận bounced lần đầu |
| **mail.outbox.pending** | Gauge | Số notification chờ xử lý |
| **mail.outbox.oldest.due.age** | Gauge | Thời gian chờ của item đến hạn lâu nhất |
| **mail.outbox.retry** | Gauge | Số notification chờ retry |
| **mail.worker.last.poll** | Gauge | Unix timestamp của lần polling cuối |
| **mail.webhook.rejected** | Counter | Webhook bị từ chối do xác thực/schema |

Đây là tên logic theo phong cách **Micrometer dotted names**. Khi xuất qua Prometheus, tên được chuyển đổi theo naming convention; ví dụ **mail.submissions** có thể xuất dưới dạng **mail_submissions_total**, còn **mail.submission.duration** thành họ metric timer có đơn vị giây.

Không nên giả định rằng mọi library/registry/version đều tạo ra cùng hậu tố tên mà chưa quan sát metrics thực tế. Các ví dụ PromQL tiếp theo giả định exporter đã tạo đúng các tên minh họa.

## 10. Thiết kế label: đủ để tìm lỗi, không làm nổ cardinality

Một metric có thể được phân tách theo những dimension hữu ích:

| Label | Ví dụ | Mục đích |
|---|---|---|
| **provider** | primary-smtp, backup-smtp | Xác định ESP hoặc cấu hình gửi bị lỗi |
| **stream** | transactional, security, marketing | Phân biệt loại thông báo |
| **result** | accepted, failed, unknown | Tách kết quả submission |
| **category** | none, connect_timeout, smtp_4xx, auth | Tìm nhóm nguyên nhân |
| **environment** | production, staging | Phân biệt môi trường |
| **region** | region-a, region-b | Tìm sự cố theo vùng |

Các label phải thuộc **tập giá trị hữu hạn, được kiểm soát**. Không dùng:

- Địa chỉ email hoặc username của người nhận.
- Subject, Message-ID, notification ID, attempt ID.
- Toàn bộ nội dung exception hoặc SMTP reply text.
- URL chứa token hoặc thông tin cá nhân.
- File path/attachment name tùy ý từ request.
- ID tenant có hàng trăm nghìn giá trị mà không có kế hoạch giới hạn cardinality.

Nếu cần điều tra một notification cụ thể, dùng **structured logs, trace ID và database** có quyền truy cập phù hợp. Metrics dành cho tính toán tổng hợp.

### Vì sao cardinality quan trọng?

Mỗi tổ hợp label khác nhau tạo ra một time series:

~~~text
provider(3)
  x stream(4)
  x result(3)
  x category(12)
  x instance(20)
  = 8.640 series tiềm năng
~~~

Đây mới là một metric. Nếu thêm **recipient email** với hàng triệu giá trị, chi phí lưu trữ, query và vận hành Prometheus có thể tăng rất lớn.

Nên phân loại lỗi thành **mã chuẩn hóa**, ví dụ **smtp_4xx**, **read_timeout**, thay vì đặt exception.getMessage() làm label.

## 11. Bổ sung Micrometer và Spring Boot Actuator

Với ứng dụng Spring Boot, có thể thêm các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Phiên bản thư viện nên được quản lý tương thích với phiên bản Spring Boot đang sử dụng. Ví dụ cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: mail-notification-service
~~~

Nếu Actuator và Prometheus registry hoạt động, endpoint thường có dạng:

~~~text
GET /actuator/prometheus
~~~

Chỉ cho **Prometheus hoặc các hệ thống giám sát được ủy quyền** truy cập endpoint. Có thể dùng management port, network policy, authentication hoặc reverse proxy tùy hạ tầng. **Không công khai endpoint metrics chứa thông tin cấu trúc nội bộ cho Internet**.

### Tại sao cần xem dữ liệu exporter thực tế?

Prometheus naming convention có thể chuyển tên Micrometer từ dấu chấm sang dấu gạch dưới, thêm hậu tố **_total**, **_seconds** hoặc các series dành cho histogram. Trước khi đưa alert rule vào production, cần xác nhận:

- Tên metric và label thực sự được export.
- Counter có tăng khi test gửi email không.
- Timer có các series **_count**, **_sum** và **_bucket** khi histogram được bật không.
- Metrics có bị lọc bởi Spring profile/registry config không.
- Prometheus có scrape được endpoint tương ứng không.

Tránh copy một truy vấn PromQL chưa khớp tên exporter rồi suy ra “không có lỗi” vì dashboard luôn hiện 0.

## 12. Ghi metrics cho SMTP submission attempt

Một wrapper quanh **JavaMailSender** có thể ghi nhận **một outcome cho mỗi lần gửi một MimeMessage**.

Định nghĩa model phân loại do ứng dụng quản lý:

~~~java
public record MailFailure(
        String result,    // failed hoặc unknown
        String category   // dns, auth, read_timeout, ...
) {
}

public interface MailFailureClassifier {
    MailFailure classify(
            org.springframework.mail.MailException exception
    );
}
~~~

**MailFailureClassifier** không phải API mặc định của Spring. Đây là abstraction để tách quyết định retry/trạng thái khỏi code ghi metric.

Một lớp ghi metric:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class MailSubmissionMetrics {

    private final MeterRegistry registry;

    public MailSubmissionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String provider,
            String stream,
            String result,
            String category,
            long elapsedNanos
    ) {
        registry.counter(
                "mail.submissions",
                "provider", provider,
                "stream", stream,
                "result", result,
                "category", category
        ).increment();

        Timer.builder("mail.submission.duration")
                .tag("provider", provider)
                .tag("stream", stream)
                .tag("result", result)
                .register(registry)
                .record(Duration.ofNanos(elapsedNanos));
    }
}
~~~

Code giả định **provider**, **stream**, **result** và **category** đã được chuẩn hóa thành tập hữu hạn. Không truyền giá trị trực tiếp từ request hoặc exception message.

**Counter tăng một lần cho mỗi attempt**, còn Timer đo thời gian của attempt đó. Nếu một notification retry ba lần, counter tăng ba lần; đây là hành vi cố ý.

### Instrumented sender

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ObservedMailTransport {

    private final JavaMailSender sender;
    private final MailSubmissionMetrics metrics;
    private final MailFailureClassifier classifier;

    public ObservedMailTransport(
            JavaMailSender sender,
            MailSubmissionMetrics metrics,
            MailFailureClassifier classifier
    ) {
        this.sender = sender;
        this.metrics = metrics;
        this.classifier = classifier;
    }

    public void submit(
            MimeMessage message,
            String provider,
            String stream
    ) {
        long started = System.nanoTime();
        String result = "unknown";
        String category = "unclassified";

        try {
            sender.send(message);
            result = "accepted";
            category = "none";
        } catch (MailException exception) {
            MailFailure failure = classifier.classify(exception);
            result = failure.result();
            category = failure.category();
            throw exception;
        } finally {
            metrics.record(
                    provider,
                    stream,
                    result,
                    category,
                    System.nanoTime() - started
            );
        }
    }
}
~~~

Đoạn mã trên dành cho **một MimeMessage mỗi lần submit**. Nếu ứng dụng gọi API gửi mảng message hoặc một message có nhiều recipient và kết quả một phần, cần instrument theo từng message/recipient và thông tin lỗi thực tế; không lấy một exception của batch để khẳng định tất cả đã thất bại.

### Ngữ nghĩa result trong ví dụ

- **accepted:** send(...) trả về bình thường ở chặng SMTP submission.
- **failed:** classifier có bằng chứng server từ chối hoặc chưa gửi và operation thất bại rõ ràng.
- **unknown:** chưa có đủ bằng chứng xác định acceptance, ví dụ mất phản hồi ở pha cuối của SMTP DATA.

Ví dụ minh họa giả định classifier **không gọi mọi MailException là failed**. Nếu chưa nắm được pha/SMTP reply, nên giữ unknown. Hệ thống production cần bảo đảm wrapper không làm mất exception gốc nếu logic metrics gặp lỗi phụ và cần instrument thêm các lỗi phát sinh khi chuẩn bị nội dung nếu muốn đo đủ pipeline.

**Timer đo thời gian submission**, không phải thời gian email tới mailbox. Nếu yêu cầu độ trễ end-to-end, phải đo từ event nghiệp vụ đến delivery event bằng một metric khác có semantics rõ ràng.

## 13. Micrometer metrics và database không có transaction chung

Trong ứng dụng dùng outbox, một worker có thể:

1. Gửi email; SMTP chấp nhận.
2. Tăng counter accepted.
3. Mở transaction cập nhật outbox thành SUBMITTED.
4. Database update thất bại.

Metric accepted vẫn tăng, nhưng database chưa được cập nhật. Điều đó không nhất thiết là lỗi metric: nó phản ánh kết quả **SMTP attempt**, còn database phản ánh trạng thái xử lý nghiệp vụ có thể chưa lưu thành công.

**Counter Micrometer không tham gia transaction database**. Không nên giả định hai hệ thống cập nhật nguyên tử.

Vì vậy, nếu cần metric **mail.notification.submitted** đếm notification duy nhất:

- Dựa vào một transition có điều kiện/idempotent, ví dụ trạng thái trước chưa SUBMITTED và cập nhật thành công.
- Tách attempt counter và notification counter.
- Hiểu rằng metric exporter/counter có thể mất một increment khi process crash.
- Dùng truy vấn database hoặc dữ liệu provider làm nguồn đối soát bền vững khi yêu cầu tính chính xác cao.

Metrics là tín hiệu vận hành và cảnh báo; chúng **không thay thế audit log hoặc sổ cái notification**.

## 14. Bảng trạng thái cần phân biệt trong dashboard

Một dashboard hữu ích nên chia thành nhiều biểu đồ thay vì một ô “Email success”.

| Biểu đồ | Cách đọc |
|---|---|
| Submission attempts/s | Tải thực tế đẩy vào SMTP |
| Accepted/failed/unknown rate | Tình hình ngay tại chặng submission |
| Failure ratio theo provider/stream | Phạm vi lỗi |
| Timeout ratio và số timeout tuyệt đối | Chậm/hỏng ở mạng hoặc SMTP |
| Submission latency p50/p95/p99 | Dấu hiệu chậm trước khi lỗi bùng phát |
| Outbox pending/retry/oldest age | Sự cố đọng hàng |
| Bounce events/s | Lượng phản hồi bất đồng bộ |
| Mature-cohort bounce ratio | Tỷ lệ bounce của các notification đủ thời gian quan sát |
| Hard vs soft bounce | Chất lượng recipient hay gián đoạn tạm thời |
| Webhook lag và rejected events | Chất lượng pipeline nhận delivery |

Đặt đơn vị rõ ràng:

- **Attempts/s** không phải người dùng/s.
- **Timeout attempts** không phải notification bị mất.
- **Bounce events** không đồng nghĩa unique bounced notifications.
- **p95 seconds** là độ trễ của attempt, không phải độ trễ delivery.

## 15. PromQL: xem tỷ lệ submission thất bại

Giả sử metric:

~~~text
mail_submissions_total{
  provider="primary-smtp",
  stream="transactional",
  result="failed",
  category="smtp_4xx"
}
~~~

Tổng attempts trong 10 phút, theo provider/stream:

~~~promql
sum by (provider, stream) (
  increase(mail_submissions_total[10m])
)
~~~

Số attempts có kết quả FAILED:

~~~promql
sum by (provider, stream) (
  increase(mail_submissions_total{result="failed"}[10m])
)
~~~

Tỷ lệ FAILED hoặc UNKNOWN:

~~~promql
sum by (provider, stream) (
  increase(
    mail_submissions_total{result=~"failed|unknown"}[10m]
  )
)
/
clamp_min(
  sum by (provider, stream) (
    increase(mail_submissions_total[10m])
  ),
  1
)
~~~

Ví dụ truy vấn này không tự thay đổi ý nghĩa metrics:

- **FAILED + UNKNOWN** được dùng cho tỷ lệ “submission chưa khỏe”, không gọi là “confirmed failure rate”.
- Nếu muốn tỷ lệ lỗi đã xác nhận, chỉ lấy **result="failed"**.
- Nếu không có dữ liệu do ứng dụng ngừng hoạt động hoặc scrape bị mất, biểu thức có thể không có series chứ không tự động ra 0. Cần alert về liveness/scrape riêng.
- **increase()** có thể trả giá trị không nguyên do cách Prometheus ngoại suy các sample trong cửa sổ, dù counter thực tế chỉ tăng từng đơn vị.

### Chọn cửa sổ

**[5m]** phản ứng nhanh nhưng dễ nhiễu; **[30m]** ổn định hơn nhưng báo trễ. Có thể dùng cửa sổ ngắn cho cảnh báo mức độ cao và cửa sổ dài cho warning hoặc so sánh xu hướng.

## 16. Cảnh báo tỷ lệ lỗi tăng: cần chặn nhiễu lưu lượng thấp

Giả sử chính sách cảnh báo:

> Cảnh báo khi tỷ lệ FAILED + UNKNOWN cao hơn 5% trong 10 phút, có ít nhất 100 submission attempts và điều kiện kéo dài tối thiểu 5 phút.

Ví dụ Prometheus recording/alert rule:

~~~yaml
groups:
  - name: spring-mail-submission
    rules:
      - alert: MailSubmissionUnhealthyRateHigh
        expr: |
          (
            sum by (provider, stream) (
              increase(
                mail_submissions_total{result=~"failed|unknown"}[10m]
              )
            )
            /
            clamp_min(
              sum by (provider, stream) (
                increase(mail_submissions_total[10m])
              ),
              1
            )
          ) > 0.05
          and on (provider, stream)
          sum by (provider, stream) (
            increase(mail_submissions_total[10m])
          ) >= 100
        for: 5m
        labels:
          severity: warning
          service: spring-mail
        annotations:
          summary: "Tỷ lệ submission không khỏe tăng"
          description: "Provider và stream có tỷ lệ failed/unknown vượt 5%."
          runbook_url: "https://runbooks.example.com/mail/submission"
~~~

Trong ví dụ, **runbook_url** là URL tài liệu minh họa, không phải một trang đã triển khai.

### Điều kiện AND giải quyết vấn đề gì?

Nếu chỉ so sánh tỷ lệ với 5%, ba failures trong tổng bốn attempts đã đủ tạo alert. Điều kiện **ít nhất 100 attempts** giảm nhiễu của một sample quá nhỏ.

Tuy nhiên, nếu stream bảo mật chỉ gửi 20 email/ngày, ngưỡng 100 sẽ khiến nó không bao giờ được cảnh báo theo tỷ lệ. Với luồng ít lưu lượng nhưng quan trọng, nên có alert riêng theo:

- Số lỗi liên tiếp.
- Số notification không thể gửi sau nhiều lần retry.
- Độ tuổi outbox vượt SLA.
- Lỗi cấu hình nghiêm trọng như authentication failure.
- Không có worker poll khi đáng ra hệ thống đang chạy.

**Ngưỡng theo tỷ lệ phải đi cùng ngưỡng số lượng và mức độ quan trọng của luồng.**

### Vì sao cần for?

**for: 5m** yêu cầu biểu thức giữ trạng thái đúng liên tục qua nhiều lần đánh giá trước khi alert firing. Điều này giảm cảnh báo do biến động ngắn. Khi có các sự cố nghiêm trọng như mất hoàn toàn SMTP, có thể dùng alert nhanh hơn, nhưng cần kiểm tra tránh pagers bị spam khi flapping.

## 17. Cảnh báo timeout tăng theo tỷ lệ và số lượng

Timeout là một loại lỗi đáng theo dõi riêng vì nó có thể báo sự cố mạng hoặc SMTP provider đang chậm, trước khi tỷ lệ submission thất bại tăng rõ rệt.

### Timeout count

Giả sử category có ba giá trị:

- **connect_timeout**
- **read_timeout**
- **write_timeout**

Truy vấn số timeout attempts trong 10 phút:

~~~promql
sum by (provider, stream) (
  increase(
    mail_submissions_total{
      category=~"connect_timeout|read_timeout|write_timeout"
    }[10m]
  )
)
~~~

### Timeout ratio

~~~promql
sum by (provider, stream) (
  increase(
    mail_submissions_total{
      category=~"connect_timeout|read_timeout|write_timeout"
    }[10m]
  )
)
/
clamp_min(
  sum by (provider, stream) (
    increase(mail_submissions_total[10m])
  ),
  1
)
~~~

Một alert minh họa:

~~~yaml
- alert: MailSmtpTimeoutRateHigh
  expr: |
    (
      sum by (provider, stream) (
        increase(
          mail_submissions_total{
            category=~"connect_timeout|read_timeout|write_timeout"
          }[10m]
        )
      )
      /
      clamp_min(
        sum by (provider, stream) (
          increase(mail_submissions_total[10m])
        ),
        1
      )
    ) > 0.02
    and on (provider, stream)
    sum by (provider, stream) (
      increase(mail_submissions_total[10m])
    ) >= 100
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "SMTP timeout vượt ngưỡng"
~~~

Trong môi trường có vài attempts/phút, có thể bổ sung cảnh báo số tuyệt đối, ví dụ **ít nhất 10 timeout trong 10 phút**, hoặc một quy tắc riêng cho stream quan trọng.

### Không đồng nhất mọi timeout

**Connect timeout** cho biết nỗ lực mở TCP không hoàn thành trong hạn; thường chưa có message được gửi.

**Read timeout** có thể xảy ra khi chờ greeting, AUTH hoặc phản hồi cuối sau SMTP DATA. Trong trường hợp server đã nhận DATA nhưng phản hồi cuối bị mất, kết quả có thể là **UNKNOWN**, không phải chắc chắn FAILED.

**Write timeout** cũng có thể tạo kết quả chưa rõ nếu dữ liệu đã được truyền một phần/toàn bộ.

Nếu hạ tầng hoặc transport adapter có thể ghi nhận **pha lỗi** đáng tin cậy, có thể thêm label hữu hạn **phase=connect|greeting|auth|envelope|data|final_reply|unknown** cho một metric chuyên biệt. Không đoán phase chỉ dựa vào tên exception.

## 18. Cảnh báo độ trễ SMTP trước khi timeout bùng phát

Một SMTP provider có thể chậm dần trước khi thực sự timeout. **Timer** giúp nhìn thấy điều đó.

Với Micrometer Timer **mail.submission.duration**, một Prometheus registry có thể xuất:

~~~text
mail_submission_duration_seconds_count
mail_submission_duration_seconds_sum
mail_submission_duration_seconds_bucket
~~~

Series **_bucket** chỉ tồn tại khi cấu hình histogram thích hợp.

Ví dụ bật percentile histogram:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        mail.submission.duration: true
~~~

Sau khi xác nhận exporter có series bucket, có thể tính p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, stream) (
    rate(mail_submission_duration_seconds_bucket[10m])
  )
)
~~~

Hoặc tính độ trễ trung bình từ timer:

~~~promql
sum by (provider, stream) (
  rate(mail_submission_duration_seconds_sum[10m])
)
/
clamp_min(
  sum by (provider, stream) (
    rate(mail_submission_duration_seconds_count[10m])
  ),
  0.001
)
~~~

Đơn vị đo ở đây là **giây**. Không dùng p95 khi histogram chưa được cấu hình mà suy ra biểu đồ rỗng là “không có độ trễ”.

### Cảnh báo độ trễ có thể hữu ích khi nào?

- Submission vẫn accepted nhưng p95 tăng nhiều lần so với baseline.
- Chỉ một provider/region bị chậm, nhà cung cấp khác bình thường.
- Outbox age tăng vì mỗi lần gửi kéo dài.
- Connection pool, executor hoặc hàng đợi SMTP bị quá tải.

Ngưỡng như **p95 > 8 giây trong 15 phút** chỉ là ví dụ; nên dựa vào thời gian gửi bình thường của message/attachment và giới hạn timeout đã cấu hình.

Nếu email có attachment lớn, cần phân nhóm hợp lý hoặc đo size distribution để phân biệt chậm do dữ liệu và chậm do hạ tầng. Không thêm message size chính xác làm label có cardinality cao; có thể dùng bucket kích thước hữu hạn nếu cần.

## 19. Không có traffic không đồng nghĩa hệ thống khỏe

Một trường hợp dễ gây hiểu nhầm:

~~~text
09:00–09:10
  Số attempts: 0
  Tỷ lệ lỗi trên dashboard: không có dữ liệu
~~~

Nếu worker dừng hoàn toàn, tỷ lệ lỗi có thể biến mất thay vì tăng. Hệ thống cần các cảnh báo khác:

- **Prometheus scrape target down**.
- **Worker không polling theo lịch**.
- **Pending outbox tăng nhưng không có submission attempts**.
- **Oldest due notification age** vượt SLA.
- **Webhook receiver không nhận được delivery events** trong bối cảnh vẫn có lưu lượng dự kiến.

Ví dụ kiểm tra scrape:

~~~promql
up{job="mail-notification-service"} == 0
~~~

Nếu một target biến mất khỏi service discovery hoàn toàn, series **up** có thể trở nên stale và truy vấn trên không nhìn thấy target nữa. Do đó cần cấu hình service discovery, alert về missing targets hoặc các kiểm tra hạ tầng phù hợp, không dựa duy nhất vào so sánh up == 0.

### Heartbeat worker

Một worker có thể cập nhật thời điểm poll cuối:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class MailWorkerHeartbeat {

    private final AtomicLong lastPollSeconds =
            new AtomicLong(0L);

    public MailWorkerHeartbeat(MeterRegistry registry) {
        Gauge.builder(
                "mail.worker.last.poll",
                lastPollSeconds,
                value -> (double) value.get()
        ).register(registry);
    }

    public void polled() {
        lastPollSeconds.set(Instant.now().getEpochSecond());
    }
}
~~~

Gọi **polled()** ở mỗi vòng polling thực sự, không chỉ khi có mail gửi thành công. Ví dụ truy vấn:

~~~promql
time() - mail_worker_last_poll > 300
~~~

Cần xử lý giá trị khởi tạo 0, worker mới khởi động, instance được scale-to-zero và sự khác biệt đồng hồ giữa JVM/Prometheus. Đối với hệ thống chạy theo lịch thưa hoặc chỉ bật khi có công việc, ngưỡng 300 giây là không phù hợp; phải dựa vào cadence thực tế.

## 20. Quan sát outbox để phát hiện sự cố không tạo lỗi SMTP

Một notification có thể chưa bao giờ gọi được JavaMailSender, ví dụ:

- Worker ngừng chạy.
- Hàng đợi bị khóa bởi transaction lỗi.
- Scheduler không được kích hoạt.
- Record RETRY có next_attempt_at sai.
- Task bị thiếu executor thread.
- Lease PROCESSING không được thu hồi.

Khi đó **mail.submissions** không tăng và tỷ lệ lỗi SMTP không phản ánh vấn đề.

Metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| **mail_outbox_pending** | Số notification đang chờ |
| **mail_outbox_retry** | Số notification đang đợi retry |
| **mail_outbox_processing** | Số notification đã claim |
| **mail_outbox_expired_lease** | Số record PROCESSING có lease hết hạn |
| **mail_outbox_oldest_due_age_seconds** | Thời gian chờ kể từ lúc record đến hạn |
| **mail_worker_claimed_total** | Tổng record worker đã claim |
| **mail_worker_completed_total** | Tổng record hoàn tất theo chính sách |

**Oldest due age** thường hữu ích hơn chỉ nhìn pending count. Một queue có 10.000 record có thể bình thường trong chiến dịch lớn nếu throughput và tuổi chờ vẫn trong SLA. Ngược lại, chỉ một notification quan trọng chờ 30 phút có thể là sự cố nghiêm trọng.

Ví dụ alert:

~~~yaml
- alert: MailOutboxProcessingStalled
  expr: |
    mail_outbox_oldest_due_age_seconds > 900
    and on (provider, stream)
    mail_outbox_pending > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Outbox mail có item đến hạn chờ quá lâu"
~~~

Ví dụ giả định cả hai gauge có nhãn **provider** và **stream** giống nhau. Nếu chúng là metrics toàn dịch vụ hoặc có label khác, truy vấn phải điều chỉnh cho đúng. Không copy alert rule từ tài liệu mà bỏ qua schema metric triển khai.

### Pending và retry có nên cộng lại?

Tùy state machine. Nếu pending count chỉ đếm PENDING, retry count là nhóm riêng; một dashboard “backlog total” có thể cộng các trạng thái đến hạn. Nhưng nếu pending count đã bao gồm RETRY, cộng lại sẽ double count. Hãy ghi rõ phạm vi của từng gauge.

## 21. Alert severity, điều kiện kéo dài và chống cảnh báo trùng

Không phải mọi tín hiệu tăng đều cần đánh thức người trực ngay lập tức.

| Mức | Khi phù hợp | Cách xử lý |
|---|---|---|
| **Info** | Thay đổi lưu lượng hoặc xu hướng cần theo dõi | Dashboard, báo cáo |
| **Warning** | Failure/timeout/bounce vượt baseline nhưng hệ thống vẫn hoạt động | Ticket, điều tra trong giờ hỗ trợ |
| **Critical** | Lỗi diện rộng, queue quá SLA, ảnh hưởng thông báo quan trọng | Page on-call theo quy trình |

Ví dụ:

- **Warning:** failure + unknown rate trên 5% trong 10 phút, đủ 100 attempts, kéo dài 5 phút.
- **Critical:** gần như toàn bộ submission của transactional stream bị lỗi với lưu lượng đủ lớn trong 5 phút.
- **Warning:** bounce rate của cohort trưởng thành tăng hơn baseline.
- **Critical:** outbox của stream security ngừng xử lý và oldest age vượt SLA nghiêm trọng.

Các ngưỡng phải được hiệu chỉnh theo SLO tổ chức, không xem là mặc định sản phẩm.

### Giảm alert storm

Nếu SMTP provider bị down, các alert có thể cùng firing:

~~~text
Connection timeout high
Submission failure high
Outbox backlog high
Delivery event missing
~~~

Đây có thể là **một sự cố gốc**. Alertmanager có thể nhóm theo **service/provider/stream**, tạm ức chế các cảnh báo hậu quả khi alert gốc có độ tin cậy cao, và giới hạn repeated notifications.

Không ức chế tất cả cảnh báo bounce chỉ vì có lỗi SMTP: bounce cao có thể do dữ liệu recipient hoặc DMARC khác với lỗi kết nối.

## 22. Bounce là tín hiệu bất đồng bộ, không phải MailSendException

Giả sử một email được provider chấp nhận lúc 09:00:

~~~text
09:00  JavaMailSender.send(...) thành công
09:01  ESP bắt đầu relay tới domain nhận
09:03  Receiver tạm hoãn -> deferred
09:20  Receiver trả 550 -> permanent failure
09:21  ESP phát bounce webhook
09:21  Application cập nhật notification thành BOUNCED
~~~

Lời gọi **send(...)** lúc 09:00 không thể tự biết kết quả cuối tại 09:21.

Nếu chỉ bắt **MailSendException** thì hệ thống bỏ sót các bounce xảy ra sau khi SMTP đã chấp nhận. Ngược lại, không phải mọi MailSendException là bounce: lỗi DNS, TLS hoặc authentication trước submission không phải kết quả chuyển phát bất đồng bộ.

Các nguồn quan sát bounce có thể gồm:

- Webhook sự kiện **bounce**, **delivery**, **deferred** của ESP.
- API truy vấn trạng thái gửi và chuyển phát của nhà cung cấp.
- **DSN (Delivery Status Notification)** gửi tới địa chỉ envelope sender/bounce mailbox.
- Dashboard/exports của ESP được đưa vào pipeline dữ liệu.

Nếu hệ thống dùng nhiều nhà cung cấp, mỗi nguồn có schema và semantics riêng; cần chuẩn hóa trước khi đưa vào cùng dashboard.

## 23. Phân loại hard bounce và soft bounce trong cảnh báo

| Loại | Ví dụ | Diễn giải vận hành |
|---|---|---|
| **Hard bounce** | Địa chỉ không tồn tại được xác nhận | Có thể là chất lượng danh sách recipient kém |
| **Soft bounce** | Mailbox đầy, server nhận tạm thời bận | Có thể tự hồi phục, cần retry/defer |
| **Policy rejection** | Bị chặn do authentication, reputation hoặc anti-spam | Kiểm tra sender/domain/ESP |
| **Deferred** | Message chưa giao nhưng vẫn trong hàng chờ | Không tự coi là bounce cuối |
| **Spam complaint** | Người nhận đánh dấu thư không mong muốn | Tín hiệu riêng, không nên gộp vào bounce |

**Hard/soft** là thuật ngữ vận hành của nhiều provider, không phải một phép ánh xạ tuyệt đối từ SMTP reply code:

- Một lỗi SMTP 4xx có thể được provider retry nhiều lần rồi cuối cùng kết luận thất bại.
- Một 5xx có thể biểu thị chính sách sender, không chứng minh recipient không tồn tại.
- Một event **deferred** không có nghĩa là địa chỉ phải bị suppress vĩnh viễn.

Khi bounce tăng, phân biệt **chất lượng danh sách người nhận** với **vấn đề xác thực domain/reputation**. Nếu 90% bounce có cùng mã SPF/DMARC policy, xóa hàng loạt recipient là phản ứng sai.

### Hai cảnh báo bounce khác nhau

1. **Hard-bounce ratio high:** cảnh báo chất lượng dữ liệu hoặc danh sách recipient.
2. **Policy-rejection surge:** cảnh báo authentication, sender reputation hoặc chính sách provider/receiver.

Chúng có thể cùng tăng nhưng cần runbook và owner khác nhau.

## 24. Chuẩn hóa và xác thực webhook trước khi đếm bounce

Một event từ Internet không được tự động trở thành nguồn sự thật.

Pipeline đề xuất:

~~~text
ESP webhook request
        |
        v
Verify signature / authentication
        |
        v
Validate event schema and size
        |
        v
Check provider event ID (idempotency)
        |
        v
Persist event in database
        |
        v
Resolve provider message ID -> notification-recipient
        |
        v
Update delivery state with transition rules
        |
        v
Increment delivery metrics / update aggregates
~~~

Yêu cầu quan trọng:

- Xác minh chữ ký **trên raw body** nếu hợp đồng ESP yêu cầu.
- Kiểm tra timestamp/nonce hoặc cơ chế chống replay khi provider hỗ trợ.
- Không tin tên provider chỉ từ header người gọi tự đặt.
- Lưu event ID với unique constraint để xử lý các lần webhook retry.
- Đối chiếu provider message ID và recipient với notification đã gửi.
- Xử lý event có thể đến sai thứ tự.
- Không lấy dữ liệu chưa xác minh để thay đổi suppression list.

### Một bounce event có thể đến nhiều lần

~~~text
Provider event: E-7123
   |
   +-- Delivery #1 -> application ghi DB thành công
   |                     nhưng response bị timeout
   |
   +-- Delivery #2 -> provider gửi lại cùng E-7123
~~~

Nếu tăng **mail.notification.bounced** cả hai lần, tỷ lệ bounce bị thổi phồng. Cần phân biệt:

- **Webhook requests received:** có thể đếm mọi lần nhận, phục vụ vận hành endpoint.
- **Unique valid provider events:** chỉ đếm lần đầu được lưu thành công.
- **Unique bounced notifications:** chỉ đếm notification-recipient chuyển sang trạng thái bounce cuối theo semantics ứng dụng.

Khi provider không cung cấp event ID ổn định, phải có quy tắc dedup phù hợp với hợp đồng của họ; không coi hai event có cùng timestamp là đương nhiên trùng.

## 25. Độ trễ webhook và sai lệch giữa các cửa sổ thống kê

Một bẫy phân tích dữ liệu:

~~~text
09:00–09:10: 1.000 email được accepted
09:10–09:20: chỉ 20 email mới được accepted
09:10–09:20: nhận 100 bounce cho lô 09:00
~~~

Nếu tính:

~~~text
100 bounce / 20 submitted = 500%
~~~

tỷ lệ này **không phải bounce rate của một cohort**. Nó chỉ là tỷ số giữa hai luồng sự kiện xảy ra trong cùng cửa sổ đồng hồ nhưng đại diện cho những notification khác nhau.

Vì vậy có hai cách quan sát khác nhau:

**A. Bounce event arrival rate** — số bounce mới nhận mỗi phút. Phù hợp phát hiện đột biến tức thời ở webhook/delivery pipeline.

**B. Mature-cohort bounce ratio** — tỷ lệ những notification được gửi trong một khoảng thời gian xác định, sau khi cho chúng đủ thời gian nhận kết quả. Phù hợp đánh giá chất lượng deliverability và xu hướng dài hạn.

Không nên đặt nhãn **bounce rate** cho một biểu đồ chỉ là **bounce events/s** mà không giải thích.

## 26. Cảnh báo bounce tăng kiểu gần thời gian thực

Để phát hiện đột biến nhanh, có thể dùng số lượng **unique bounced notifications** nhận trong 1 giờ chia cho số notification mới submitted trong cùng khoảng, như một **proxy**:

~~~promql
sum by (provider, stream) (
  increase(mail_notification_bounced_total[1h])
)
/
clamp_min(
  sum by (provider, stream) (
    increase(mail_notification_submitted_total[1h])
  ),
  1
)
~~~

Đây là **operational proxy**, không phải cohort bounce rate chính xác. Tử số và mẫu số có thể thuộc hai thế hệ notification khác nhau; tỷ số có thể vượt 100% nếu webhook chậm hoặc lưu lượng gửi hiện tại giảm mạnh.

Một alert tạm thời chỉ nên dùng proxy nếu hiểu độ trễ provider và có điều kiện mẫu số:

~~~yaml
- alert: MailBounceArrivalRatioHigh
  expr: |
    (
      sum by (provider, stream) (
        increase(mail_notification_bounced_total[1h])
      )
      /
      clamp_min(
        sum by (provider, stream) (
          increase(mail_notification_submitted_total[1h])
        ),
        1
      )
    ) > 0.03
    and on (provider, stream)
    sum by (provider, stream) (
      increase(mail_notification_submitted_total[1h])
    ) >= 200
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Bounce events tăng bất thường, cần đối chiếu cohort"
~~~

Giả định counter **mail_notification_bounced_total** được tăng đúng một lần cho mỗi notification-recipient được xác nhận bounced, không theo số HTTP webhook retries. Metric **mail_notification_submitted_total** đếm notification-recipient có acceptance được xác nhận lần đầu.

**Không dùng ngưỡng proxy này để tự động khóa toàn bộ recipient hoặc kết luận chất lượng danh sách đang xấu**. Nó là tín hiệu điều tra và cần đối chiếu cohort, provider dashboard, policy errors và độ trễ sự kiện.

## 27. Tính bounce rate chính xác hơn bằng cohort

Một cohort có thể được xác định bằng **thời điểm submission**, ví dụ những notification đã accepted trong một khoảng 24 giờ và đã có ít nhất một giờ để quan sát feedback.

Truy vấn minh họa theo PostgreSQL:

~~~sql
WITH mature_submissions AS (
    SELECT
        notification_id,
        recipient_id,
        provider,
        stream,
        delivery_status
    FROM notification_delivery
    WHERE submitted_at >= CURRENT_TIMESTAMP - INTERVAL '25 hours'
      AND submitted_at <  CURRENT_TIMESTAMP - INTERVAL '1 hour'
      AND submission_status = 'SUBMITTED'
)
SELECT
    provider,
    stream,
    COUNT(*) AS submitted_recipients,
    COUNT(*) FILTER (
        WHERE delivery_status = 'BOUNCED'
    ) AS bounced_recipients,
    COUNT(*) FILTER (
        WHERE delivery_status = 'DELIVERED'
    ) AS delivered_recipients,
    COUNT(*) FILTER (
        WHERE delivery_status = 'UNKNOWN'
    ) AS unknown_recipients
FROM mature_submissions
GROUP BY provider, stream;
~~~

Schema **notification_delivery** là minh họa, không phải bảng mặc định của Spring Mail. Thiết kế thực tế phải bảo đảm một hàng biểu thị **một notification-recipient**, hoặc dùng **COUNT(DISTINCT notification_recipient_id)** nếu dữ liệu lưu nhiều event/attempt trên mỗi notification.

Từ kết quả:

~~~text
Mature-cohort bounce ratio =
  bounced_recipients / submitted_recipients
~~~

### Vì sao chờ một giờ?

Khoảng trễ **một giờ chỉ là ví dụ**. Một số provider báo bounce nhanh, nhưng một số lỗi deferred có thể chuyển thành bounce sau nhiều giờ hoặc nhiều ngày. Với mỗi stream, cần chọn **cohort maturity threshold** dựa trên độ trễ phản hồi và thời gian retry của provider.

Nếu chưa đủ thời gian trưởng thành:

- Bounce rate có thể bị đánh giá thấp vì chưa nhận hết bounce.
- Delivery status có thể vẫn PENDING/DEFERRED/UNKNOWN.
- Việc so sánh hôm nay với cohort cũ hơn có thể không công bằng.

Để phân tích sâu, nên giữ **submission cohort time**, **feedback observation time**, **delivery event time**, loại status và chính sách maturity.

## 28. Cảnh báo dựa trên tỷ lệ cohort đã trưởng thành

Có thể chạy một job tổng hợp theo chu kỳ, xuất các gauge:

~~~text
mail_bounce_cohort_ratio{
  provider="primary-smtp",
  stream="transactional",
  cohort_window="last_24h_matured"
} 0.042

mail_bounce_cohort_size{
  provider="primary-smtp",
  stream="transactional",
  cohort_window="last_24h_matured"
} 2500
~~~

Tên **cohort_window** phải thuộc tập cố định. Không thêm timestamp của từng cohort làm Prometheus label, vì dễ sinh rất nhiều time series. Lưu dữ liệu lịch sử chi tiết trong database hoặc hệ thống phân tích thay vì label.

Alert:

~~~promql
(
  mail_bounce_cohort_ratio{
    cohort_window="last_24h_matured"
  } > 0.03
)
and on (provider, stream, cohort_window)
(
  mail_bounce_cohort_size{
    cohort_window="last_24h_matured"
  } >= 200
)
~~~

Khi xuất gauge, cần ghi thêm **thời điểm lần tổng hợp cuối** và cảnh báo dữ liệu stale. Một ratio 0.001 đã đứng yên hai ngày do job bị chết không có nghĩa hệ thống khỏe.

### So sánh với baseline

Không phải mọi stream đều có baseline bounce giống nhau. Một chiến dịch gửi tới danh sách mới và một dòng OTP gửi tới tài khoản đã xác minh có hành vi khác nhau.

Nên so sánh:

- Cùng stream/provider trong những cohort trưởng thành gần đây.
- Cùng nhóm recipient/chiến dịch theo mức tổng hợp an toàn.
- Cùng loại hard/soft/policy bounce.
- Cùng tiêu chuẩn maturity và khoảng quan sát.

Nếu thay đổi cách tính denominator hoặc schema event, cần chú thích thay đổi trên dashboard để không nhầm sai lệch dữ liệu với thay đổi thực tế về deliverability.

## 29. Theo dõi độ trễ và lỗi của webhook delivery

Một hệ thống có thể gửi SMTP hoàn toàn bình thường nhưng dashboard bounce trống vì webhook receiver hỏng.

Ví dụ:

~~~text
SMTP submissions: bình thường
Provider dashboard: có bounce
Ứng dụng: 0 bounce events

Nguyên nhân có thể:
  webhook endpoint trả HTTP 500
  chữ ký xác thực bị cấu hình sai
  event parser không hiểu schema mới
  message ID không đối chiếu được
  event inbox/consumer bị kẹt
~~~

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| **mail_webhook_requests_total** | Số HTTP requests nhận được |
| **mail_webhook_rejected_total** | Số requests bị từ chối do chữ ký/schema/quyền |
| **mail_delivery_events_total** | Số event hợp lệ đã xử lý, phân theo loại |
| **mail_delivery_unmatched_total** | Số event không đối chiếu được notification |
| **mail_delivery_event_lag_seconds** | Thời gian từ event xảy ra ở provider tới khi ứng dụng ghi nhận |
| **mail_delivery_inbox_oldest_age_seconds** | Độ tuổi event còn tồn đọng trong inbox |
| **mail_delivery_inbox_pending** | Số event đang chờ xử lý |

### Cảnh báo không nhận được webhook

Không nên cảnh báo chỉ bằng điều kiện “không có bounce trong 15 phút” vì một hệ thống khỏe có thể không phát sinh bounce.

Cảnh báo tốt hơn:

- Tỷ lệ HTTP 5xx hoặc signature verification failures tăng.
- Event inbox tồn đọng và oldest age tăng.
- Provider báo vẫn phát delivery events nhưng application không nhận/không xử lý.
- Delivery-state UNKNOWN tồn đọng lâu hơn SLA.
- Có chênh lệch dài hạn giữa provider export và dữ liệu ứng dụng.

Nếu provider phát event theo batch hoặc một lịch không liên tục, liveness alert cần hiểu lịch đó. Không so sánh số webhook với submission theo cùng cửa sổ mà bỏ qua độ trễ.

## 30. Cảnh báo theo SLI/SLO thay vì một ngưỡng tùy ý

Khi email là tính năng quan trọng, có thể xác định **Service Level Indicator (SLI)** và **Service Level Objective (SLO)** cho từng lớp.

Ví dụ:

**SLI submission:**

~~~text
Tỷ lệ notification được SMTP provider xác nhận accepted
trong vòng T phút kể từ khi được tạo và đủ điều kiện gửi.
~~~

**SLI worker latency:**

~~~text
Tỷ lệ notification không vượt quá X phút trong trạng thái
PENDING/RETRY khi đã đến hạn xử lý.
~~~

**SLI delivery feedback:**

~~~text
Tỷ lệ delivery event được ingest và xử lý trong vòng Y phút
kể từ thời điểm provider phát event.
~~~

Không nhất thiết dùng **Inbox delivery** làm SLO nếu ứng dụng không có nguồn chứng minh cuối cùng. Hãy chọn chỉ số mà hệ thống thực sự đo và có thể chịu trách nhiệm.

### Error budget burn rate

Với một SLO submission, có thể dùng khái niệm **error budget**: tỷ lệ attempts/notifications không đạt mục tiêu. Cảnh báo bằng burn rate cao trên cả cửa sổ ngắn và dài giúp phát hiện sự cố nghiêm trọng mà vẫn giảm nhiễu.

Ví dụ khái niệm:

~~~text
SLO mục tiêu: 99.9% success
Allowed failure fraction: 0.1% = 0.001

Observed failure fraction: 2%

Burn rate = 0.02 / 0.001 = 20
~~~

Để dùng thật, cần xác định:

- Mẫu số là attempts hay notification duy nhất.
- UNKNOWN được tính như thế nào.
- Cửa sổ SLO là 7, 28 hay 30 ngày.
- Có loại bỏ notification bị từ chối do input không hợp lệ hoặc ngoài trách nhiệm hệ thống không.
- Thời gian chờ hợp lệ trước khi tính một notification là vi phạm.

Không đặt một SLO từ các counter chưa phân biệt retry và notification, vì có thể phản ánh hoạt động retry chứ không phản ánh tác động tới người dùng.

## 31. So sánh với baseline lịch sử và ảnh hưởng chiến dịch

Email traffic thường có chu kỳ theo giờ trong ngày, ngày trong tuần hoặc chiến dịch:

~~~text
07:00–09:00: ít thông báo
09:00–12:00: lưu lượng tăng
12:00–13:00: lưu lượng giảm
18:00: gửi chiến dịch dự kiến
~~~

Ngưỡng tuyệt đối “hơn 50 bounce trong 10 phút” có thể bình thường trong chiến dịch lớn nhưng bất thường trong luồng email bảo mật.

Nên phân đoạn theo:

- **stream**: transactional, security, marketing.
- **provider**: SMTP provider hoặc account gửi.
- **region** nếu sự cố mạng phân vùng.
- **environment** để không cộng test/staging vào production.
- **campaign category** có tập giá trị hữu hạn khi cần, nhưng tránh gắn ID chiến dịch mới cho mọi lần chạy lên mọi metric dài hạn.

### Cảnh báo dựa trên tăng tương đối

Có thể so sánh hiện tại với baseline đã tính từ những kỳ tương đồng. Nhưng cần tránh bẫy:

- Nếu baseline gần bằng 0, tăng 10 lần vẫn có thể chỉ là một vài email.
- Nếu có thay đổi về provider hoặc template, baseline cũ không còn tương đương.
- Một đợt gửi lớn làm thay đổi thành phần recipient, khiến bounce ratio tăng không nhất thiết vì hạ tầng bị lỗi.
- Dữ liệu delivery đến muộn khiến đường biểu đồ thay đổi sau khi thời gian submission đã qua.

Vì vậy, alert theo **baseline** vẫn nên kèm min sample, cửa sổ và ý nghĩa nghiệp vụ.

## 32. Runbook khi tỷ lệ lỗi submission tăng

Một cảnh báo failure/unknown rate cao nên dẫn tới một quy trình điều tra cụ thể, không chỉ một trang dashboard trống.

### Bước 1: Xác nhận phạm vi

- Provider nào bị ảnh hưởng?
- Stream nào: transactional, security hay marketing?
- Tất cả instance hay chỉ một region?
- Bắt đầu ngay sau deploy, thay secret hoặc thay network rule?
- Có ảnh hưởng tới email thật hay chỉ staging/test?

### Bước 2: Phân rã error category

| Category tăng | Hướng điều tra đầu tiên |
|---|---|
| **dns** | SMTP hostname, resolver, DNS cache, container DNS |
| **connection_refused** | Host/port, listener SMTP, firewall reject |
| **connect_timeout** | Routing, NAT, egress policy, provider availability |
| **read_timeout** | SMTP latency, pha chờ, server overload, đường mạng |
| **write_timeout** | Payload size, bandwidth, SMTP socket/network |
| **tls** | STARTTLS/SMTPS mode, certificate chain, truststore, JDK |
| **auth** | Credential, account permission, SMTP AUTH policy |
| **smtp_4xx** | Rate limiting, throttling, transient rejection |
| **smtp_5xx** | Sender/recipient policy, message size, reputation |
| **mime_preparation** | Template/recipient validation, content, attachment |

### Bước 3: Đối chiếu với log và provider

- Xem normalized error code và một số trace ID đại diện.
- Kiểm tra SMTP reply code và **pha gửi** nếu đã biết.
- Xem dashboard/trạng thái của provider.
- So sánh với sender/region khác.
- Kiểm tra timeout config và concurrency.

### Bước 4: Bảo vệ nghiệp vụ

- Đừng retry lỗi cấu hình sai credential hoặc template liên tục.
- Nếu provider down, cân nhắc backoff/circuit breaker hoặc chuyển provider theo chính sách.
- Nếu một message có kết quả UNKNOWN, không tự động retry mù.
- Nếu outbox đang dồn, kiểm tra lease, batch size và worker throughput.
- Nếu lỗi do deploy, thực hiện rollback hoặc sửa cấu hình có kiểm soát.

### Bước 5: Đánh giá mức ảnh hưởng

Đo:

- Unique notification-recipient chưa được submitted.
- Oldest pending age.
- Nhóm sự kiện nghiệp vụ bị ảnh hưởng.
- Độ trễ phục hồi sau khi sửa.
- Số notification cần replay hoặc đối soát.

Không chỉ báo “500 lỗi SMTP”, vì đó có thể là 500 attempts của một tập notification nhỏ được retry nhiều lần.

## 33. Runbook khi timeout tăng

Timeout thường có tương quan mạnh với hạ tầng mạng và thời gian phản hồi.

### Bước 1: Xác định loại timeout

~~~text
DNS lookup timed out?
     |
TCP connect timed out?
     |
Read timeout khi chờ greeting?
     |
Read timeout khi chờ SMTP AUTH?
     |
Read timeout khi chờ final DATA reply?
     |
Write timeout khi truyền nội dung?
~~~

Không phải mọi library cung cấp phase đầy đủ. Nếu thiếu bằng chứng, ghi nhận **unknown phase** và điều tra qua trace/provider log, không gán bừa.

### Bước 2: Kiểm tra hệ thống

- DNS tại chính VM/container/pod chạy ứng dụng.
- TCP connectivity tới đúng SMTP host:port.
- Firewall, cloud egress, NAT, proxy và service mesh.
- STARTTLS trên port 587 hoặc implicit TLS trên port 465 theo cấu hình.
- Thời gian phản hồi SMTP và quota provider.
- Attachment size, số kết nối đồng thời, thread/executor saturation.

### Bước 3: Đánh giá retry safety

**Connect timeout trước SMTP session** thường có thể retry nếu lỗi tạm thời.

**Timeout sau khi đã truyền DATA mà chưa nhận được final reply** có thể biểu thị server đã chấp nhận email nhưng phản hồi bị mất. Phải xem đây là kết quả **UNKNOWN** nếu không có chứng cứ từ chối rõ ràng.

Đối với UNKNOWN:

- Tìm provider message ID hoặc trace có thể tra cứu.
- Đối soát trước khi gửi lại nếu provider hỗ trợ.
- Ghi nhận nguy cơ duplicate nếu buộc phải replay.
- Dùng event ID/notification key ổn định để tránh tạo outbox record mới.

### Bước 4: Điều chỉnh cấu hình

Các property thường dùng:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=10000
mail.smtp.writetimeout=10000
~~~

Đơn vị là **mili giây**. Tăng timeout chỉ hợp lý khi đã chứng minh giới hạn hiện tại quá thấp so với độ trễ bình thường; nó không sửa DNS sai, port bị chặn hay certificate không hợp lệ.

### Bước 5: Xác nhận phục hồi

Theo dõi:

- Timeout ratio và số timeout tuyệt đối.
- p95 SMTP submission duration.
- Accepted/unknown rate.
- Outbox oldest age.
- Số duplicate/unknown cần đối soát.

Không coi sự cố đã hết chỉ vì timeout giảm nếu notification vẫn đang kẹt trong queue.

## 34. Runbook khi bounce tăng

Bounce tăng có thể là sự cố deliverability hoặc dữ liệu người nhận, không nhất thiết là lỗi JavaMailSender.

### Bước 1: Xác nhận nguồn

- Bounce event đến từ ESP/DSN đã xác minh chưa?
- Có webhook replay/duplicate tăng không?
- Đã deduplicate provider event và notification chưa?
- Có thay đổi cách tính bounce ratio hoặc cohort không?
- Có độ trễ webhook mới hoặc backlog trong event inbox không?

### Bước 2: Phân loại

- Hard bounce hay soft bounce?
- Tăng theo một recipient domain, provider hay stream?
- SMTP enhanced status code nào xuất hiện nhiều?
- Có liên quan đến sender reputation, SPF/DKIM/DMARC hay policy rejection không?
- Có một chiến dịch mới hoặc import danh sách chưa xác minh không?

### Bước 3: Kiểm tra xác thực domain

Các thay đổi sau có thể dẫn đến bounce/policy rejection:

- Header From đổi sang domain chưa xác minh.
- Envelope sender/Return-Path bị ESP viết lại.
- SPF record không còn cho phép IP/provider gửi.
- DKIM signature không hợp lệ hoặc signing domain không aligned.
- DMARC policy/alignment thay đổi.

**Không kết luận mọi bounce là sai địa chỉ người nhận** khi nguồn gốc là xác thực domain hoặc chính sách sender.

### Bước 4: Chọn biện pháp giảm tác động

- Hard bounce xác thực: suppress địa chỉ theo chính sách, yêu cầu xác minh khi cập nhật.
- Soft bounce: giảm tốc độ, backoff hoặc chờ provider retry.
- Lỗi sender reputation/authentication: sửa domain config hoặc nội dung gửi, không xóa toàn bộ recipient.
- Chiến dịch mới gây spike: tạm dừng chiến dịch theo quy trình nếu cần, kiểm tra consent và list quality.
- Webhook giả mạo: chặn/điều tra; không sửa suppression từ dữ liệu không tin cậy.

### Bước 5: Đo tác động

Tính tỷ lệ theo cohort đã đủ thời gian và xem:

- Số unique bounced notification-recipient.
- Tỷ lệ hard/soft/policy bounce.
- Lưu lượng gửi tương ứng.
- Những recipient bị suppress.
- Tác động tới notification giao dịch quan trọng.

Nếu provider chưa phát hết delivery feedback, báo cáo mức độ chắc chắn và khoảng trễ quan sát thay vì kết luận cuối cùng quá sớm.

## 35. Cảnh báo tổng hợp: nhìn một sự cố theo nhiều tín hiệu

Không nên điều tra từng biểu đồ tách biệt khi chúng có thể phản ánh cùng một nguyên nhân.

### Kịch bản A: SMTP provider tạm ngừng hoạt động

~~~text
09:00  SMTP connect timeout bắt đầu tăng
09:03  Submission failed/unknown ratio tăng
09:05  Worker retry với backoff
09:10  Outbox pending/retry tăng
09:15  Oldest due age tăng
~~~

Tín hiệu sớm là **timeout** và **submission ratio**. Backlog là hậu quả phát sinh muộn hơn. Nếu alert chỉ theo bounce, có thể không thấy gì vì email chưa được nộp cho ESP.

Hành động phù hợp:

- Kiểm tra khả dụng của SMTP host/port từ môi trường thực.
- Xác nhận status của provider.
- Điều tiết retry để tránh tạo storm.
- Theo dõi tuổi notification quan trọng.
- Khôi phục/đối soát khi provider ổn định.

### Kịch bản B: danh sách email khách hàng không hợp lệ

~~~text
SMTP submissions: accepted bình thường
SMTP latency: bình thường
Bounce events: tăng
Hard bounce ratio: tăng
Outbox: không bị backlog
~~~

Ở đây không nên tăng SMTP timeout hoặc mở rộng số worker. Cần xem nguồn recipient, import list, validation và suppression.

### Kịch bản C: xác thực domain bị sai sau deploy

~~~text
Submission: vẫn có thể được ESP chấp nhận
Delivery: receiver policy rejection tăng
Bounce: tăng ở nhiều domain nhận
SPF/DKIM/DMARC: bắt đầu fail
~~~

Cần kiểm tra thay đổi DNS, signing domain, header From, MAIL FROM và cấu hình ESP. Không kết luận khách hàng đồng loạt nhập sai email.

### Kịch bản D: webhook ngừng hoạt động

~~~text
SMTP submissions: bình thường
Provider dashboard: vẫn có delivery/bounce
Application delivery events: giảm về 0
Delivery inbox backlog / 5xx: tăng
~~~

Đây là lỗi pipeline quan sát/delivery ingestion, không chứng minh không có bounce. Nếu mất webhook, có thể phải đối soát qua provider API/export sau khi khôi phục.

## 36. Alertmanager: routing, grouping và runbook

Một alert chỉ hữu ích nếu được gửi tới đúng người xử lý với đủ dữ liệu ngữ cảnh.

Ví dụ ý tưởng routing:

~~~yaml
route:
  receiver: mail-platform-oncall
  group_by:
    - alertname
    - provider
    - stream
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: mail-critical-oncall

receivers:
  - name: mail-platform-oncall
  - name: mail-critical-oncall
~~~

Đây là **cấu trúc minh họa**; receiver phải được cấu hình kênh gửi thông báo thực tế như pager, email hoặc hệ thống sự cố. Đừng dùng alert email gửi qua **chính SMTP provider đang bị lỗi** làm đường cảnh báo duy nhất. Nếu mail platform sập, thông báo cảnh báo cũng có thể không tới nơi.

Một alert nên có:

- Tên service/stream/provider.
- Error category hoặc lý do chuẩn hóa.
- Cửa sổ và ngưỡng điều kiện.
- Số attempts/notifications liên quan.
- Link dashboard và runbook.
- Nhóm chịu trách nhiệm.
- Cách xác minh đã phục hồi.

Không đưa địa chỉ khách hàng, OTP, nội dung email hoặc credential vào annotations để tránh lộ dữ liệu qua hệ thống alert bên thứ ba.

### Grouping phải giữ thông tin quan trọng

Nếu group tất cả alert theo một label **service** duy nhất, sự cố chỉ xảy ra ở một provider có thể bị lẫn vào nhiều alert khác. Nếu group theo từng instance/container, người trực có thể nhận hàng chục alert cho cùng một lỗi. Nên ưu tiên **service + provider + stream + loại sự cố** khi phù hợp.

## 37. Kiểm thử instrumentation và quy tắc cảnh báo

Để phát hiện sai số trước production, có thể kiểm thử theo ba tầng.

### A. Unit test với MeterRegistry thử nghiệm

Với **SimpleMeterRegistry** của Micrometer, có thể kiểm tra:

- Một submission accepted tăng counter result=accepted đúng một lần.
- Một SMTP failure tăng result=failed và category được chuẩn hóa.
- Một kết quả không rõ tăng result=unknown, không đồng thời tăng accepted.
- Timer được ghi với duration dương.
- Không tạo label theo email, exception message hoặc notification ID.

Ví dụ:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MailSubmissionMetricsTest {

    @Test
    void recordsAcceptedAttempt() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MailSubmissionMetrics metrics =
                new MailSubmissionMetrics(registry);

        metrics.record(
                "primary-smtp",
                "transactional",
                "accepted",
                "none",
                1_000_000L
        );

        double total = registry.get("mail.submissions")
                .tag("provider", "primary-smtp")
                .tag("stream", "transactional")
                .tag("result", "accepted")
                .tag("category", "none")
                .counter()
                .count();

        assertEquals(1.0, total);
    }
}
~~~

Test kiểm tra một metric logic đã được ghi nhận. Nó không kiểm tra Prometheus registry exporter, nên cần kiểm tra format scrape ở tầng tích hợp nếu alert rule sử dụng tên metric đã được chuẩn hóa.

### B. Test lỗi SMTP và callback/webhook

- SMTP sandbox từ chối rõ bằng mã 4xx.
- SMTP sandbox từ chối bằng mã 5xx.
- Server không phản hồi khi kết nối hoặc khi chờ reply.
- Lỗi sau DATA dẫn đến **UNKNOWN** thay vì retry mù.
- Một webhook bounce hợp lệ chuyển đúng notification.
- Cùng provider event gửi lại hai lần nhưng chỉ tạo một event hợp lệ.
- Webhook giả mạo bị từ chối và không thay đổi suppression.
- Event delivered/deferred/bounced đến sai thứ tự nhưng state machine vẫn xử lý theo contract.

### C. Test alert rule

Prometheus có công cụ **promtool** hỗ trợ kiểm tra cú pháp và unit test quy tắc cảnh báo. Có thể dùng dữ liệu time series mô phỏng để kiểm tra:

- 2/4 attempts lỗi không gây alert khi chưa đủ mẫu.
- 10/100 attempts lỗi kéo dài vượt ngưỡng thì gây warning.
- 0 attempts không vô tình tạo tỷ lệ vô hạn.
- Counter reset do restart không tạo một đỉnh lỗi giả.
- Timeout tăng được alert riêng theo category.
- Bounce proxy không được diễn giải thành tỷ lệ cohort khi feedback đến muộn.
- Alert về worker down/backlog vẫn hoạt động khi không còn submission metrics.

Đây là những tình huống nên xây dựng trong test suite. Không dùng một vài truy vấn thủ công trên dashboard thay thế hoàn toàn rule tests trong pipeline triển khai.

## 38. Tính toán ví dụ một cửa sổ vận hành

Giả sử trong 10 phút một stream transactional có:

| Kết quả | Attempts |
|---|---:|
| Accepted | 940 |
| Failed do SMTP 4xx | 25 |
| Failed do auth | 5 |
| Failed do lỗi prepare được ghi trong pipeline riêng | 10 |
| Unknown do timeout sau DATA | 20 |

Tổng số dòng được ghi trong bảng là **1.000 attempts/pipeline operations**, nhưng cần lưu ý **10 lỗi prepare** xảy ra trước SMTP submission. Nếu metric **mail.submissions** chỉ đếm lời gọi JavaMailSender.send(...) như trong wrapper ở trên, mẫu số thực tế là **990 SMTP attempts**, không phải 1.000.

Với chính metric **mail.submissions**:

~~~text
accepted      = 940
failed SMTP   = 25 + 5 = 30
unknown       = 20
total SMTP    = 990

confirmed failure rate = 30 / 990 ≈ 3.03%
unhealthy rate         = 50 / 990 ≈ 5.05%
unknown rate           = 20 / 990 ≈ 2.02%
~~~

Nếu alert **unhealthy rate > 5%** và min sample 100, điều kiện có thể được đáp ứng, tùy series/time window và yêu cầu **for**. Lỗi prepare cần có **metric riêng cho pipeline preparation**, hoặc đổi định nghĩa tổng thể nếu muốn đo tất cả các operation từ lúc render.

Ví dụ cho thấy **định nghĩa denominator là một phần của độ chính xác vận hành**. Nếu cộng lỗi trước SMTP vào tử số nhưng không đưa chúng vào mẫu số một cách nhất quán, tỷ lệ sẽ bị sai.

### Bounce đến sau đó

Nếu có 28 notification-recipient từ lô gửi này được provider báo bounced sau 2 giờ, không cộng 28 vào failed attempts SMTP. Hãy ghi chúng ở **delivery status/cohort**, nơi chúng thuộc về.

## 39. Bảo mật dữ liệu và quyền truy cập dashboard

Thông tin vận hành email có thể vô tình trở thành nguồn lộ dữ liệu cá nhân:

- Header To/Cc/Bcc.
- Message-ID hoặc provider message ID có thể liên kết tới người nhận.
- Subject chứa mã đơn hoặc thông tin giao dịch.
- SMTP response chứa địa chỉ người nhận.
- Payload bounce/DSN có thể chứa một phần email gốc.
- Webhook event có thể chứa email, tên hoặc metadata riêng tư.

Các nguyên tắc nên áp dụng:

1. **Metrics labels:** chỉ dùng dimension hữu hạn như provider, stream, category.
2. **Structured logs:** dùng notification/trace ID được bảo vệ, tránh body/credential.
3. **Bảo vệ metrics endpoint:** giới hạn mạng và quyền truy cập.
4. **Bảo vệ dashboard:** chia quyền theo môi trường/tenant nếu cần.
5. **Không gửi dữ liệu nhạy cảm vào alert annotations**.
6. **Retention:** đặt thời hạn lưu delivery event và logs theo yêu cầu nghiệp vụ/pháp lý.
7. **Webhook:** xác minh chữ ký, chống replay và kiểm soát kích thước request.
8. **Suppression:** chỉ thay đổi theo event đã xác thực và quy tắc được phê duyệt.
9. **SMTP debug:** tránh bật protocol trace rộng trong production.
10. **Incident export:** chia sẻ số liệu tổng hợp, không mặc nhiên xuất raw EML/DSN.

### Điều gì cần log khi thất bại?

Ví dụ log có kiểm soát:

~~~text
notificationId=...
attemptId=...
provider=primary-smtp
stream=transactional
result=unknown
category=read_timeout
phase=final_reply
elapsedMs=12000
~~~

Không log nội dung thư, SMTP credential hoặc các thông tin nhận dạng không cần thiết.

## 40. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “send() thành công nghĩa là khách đã nhận mail” | Chỉ biết submission đã được chấp nhận ở chặng đang quan sát |
| “Không có MailException nghĩa là bounce rate bằng 0” | Bounce thường đến bất đồng bộ |
| “Mọi timeout đều retry được” | Sau DATA có thể đã accepted; cần UNKNOWN/đối soát |
| “Đếm attempts cũng là số khách hàng bị ảnh hưởng” | Retry tạo nhiều attempts cho cùng notification |
| “Cứ lỗi tăng là nên tăng timeout” | Lỗi có thể do DNS, TLS, auth hoặc provider policy |
| “Bounce chia submission cùng 10 phút luôn chính xác” | Feedback có độ trễ; cohort mới là phép đo phù hợp |
| “Một webhook bounce là một notification bounced mới” | Provider có thể retry/duplicate event |
| “Mọi 5xx đều do recipient không tồn tại” | Có thể do sender policy, size, authentication hoặc reputation |
| “0 events nghĩa là khỏe” | Worker/collector/webhook có thể đang down |
| “Error rate 50% luôn nghiêm trọng hơn 5%” | Cần xem mẫu số, SLO và số người bị ảnh hưởng |
| “Chỉ cần một metric email_failed_total” | Submission, preparation và delivery là các giai đoạn khác nhau |
| “Metrics counter là audit log chính xác tuyệt đối” | Counter có thể mất khi crash/restart và không transaction với DB |
| “Có bounce thì tự động suppress mọi email trong domain” | Cần phân loại nguyên nhân và phạm vi recipient |
| “Đưa exception message vào metric label giúp chẩn đoán” | Gây cardinality cao và có thể lộ dữ liệu |
| “Alert phải gửi qua email mới đúng bài toán” | Cần đường cảnh báo độc lập khi SMTP đang lỗi |

## 41. Bảng kiểm triển khai giám sát Spring Mail

Để hoàn thiện một hệ thống cảnh báo, có thể sử dụng thứ tự triển khai sau:

1. **Chọn đơn vị đếm:** SMTP attempt, notification-recipient, provider event hay unique bounce.
2. **Tách submission và delivery:** không gộp ACCEPTED với DELIVERED.
3. **Xác định result/category:** accepted, failed, unknown cùng nhóm nguyên nhân chuẩn hóa.
4. **Gắn provider/stream hữu hạn:** không dùng email/ID làm metrics label.
5. **Thêm Micrometer và Actuator:** instrument counter, timer, gauge.
6. **Xác nhận Prometheus scrape:** tên series và labels có thực.
7. **Định nghĩa windows/thresholds:** rate và min sample phù hợp lưu lượng.
8. **Cấu hình alert failure/timeout:** phân loại DNS, TCP, TLS, auth, SMTP và pha gửi.
9. **Đo outbox backlog:** oldest due age và trạng thái worker.
10. **Thu delivery events:** webhook/DSN được xác thực, lưu bền vững và idempotent.
11. **Đo bounce arrival và mature cohort riêng:** không dùng tỷ lệ cùng cửa sổ làm chân lý.
12. **Định nghĩa SLO:** submission latency, queue age hoặc delivery feedback theo trách nhiệm thực tế.
13. **Thiết kế Alertmanager:** group và route đúng owner, có runbook.
14. **Kiểm thử các quy tắc:** low volume, counter reset, mất scrape, delay và duplicate webhook.
15. **Bảo vệ dữ liệu:** không log body/credential hay đưa PII vào label.
16. **Thực tập xử lý sự cố:** provider down, read timeout, hard bounce surge, webhook outage.
17. **Theo dõi sau triển khai:** điều chỉnh threshold để giảm false positive nhưng không che sự cố thực.

## 42. Ghi nhớ

Giám sát email trong Spring Framework Mail cần nhìn **cả ba tín hiệu**: tỷ lệ lỗi ở chặng SMTP submission, timeout/kết quả gửi chưa rõ và bounce xảy ra sau khi email đã được server tiếp nhận. Mỗi tín hiệu cần **mẫu số, cửa sổ và nguồn dữ liệu** phù hợp.

Với **JavaMailSender**, có thể dùng **Micrometer** để ghi counter theo kết quả **accepted/failed/unknown**, đo độ trễ với Timer và quan sát retry/outbox bằng Gauge. Với Spring Boot Actuator và Prometheus, có thể xây alert dựa trên tỷ lệ tăng **kèm điều kiện đủ mẫu**, độ trễ p95, liveness và backlog.

Với bounce, cần tiếp nhận **DSN hoặc webhook từ provider** theo cơ chế bảo mật, chống xử lý trùng và cập nhật trạng thái theo từng notification-recipient. Số bounce đến trong một khoảng thời gian chỉ là tín hiệu đột biến; để đánh giá chất lượng deliverability, hãy tính **tỷ lệ theo cohort đã đủ thời gian phản hồi**.

Khi một cảnh báo kích hoạt, hãy phân loại lỗi trước khi xử lý: **DNS, TCP, TLS, AUTH, SMTP 4xx/5xx, timeout sau DATA, hard/soft bounce hoặc lỗi pipeline webhook**. Retry với backoff chỉ khi phù hợp; kết quả UNKNOWN cần đối soát để giảm nguy cơ gửi trùng.

**Một hệ thống cảnh báo tốt không chỉ nói rằng “email đang lỗi”, mà chỉ ra lỗi ở chặng nào, quy mô ảnh hưởng ra sao, bằng chứng có chắc chắn không và bước xử lý an toàn tiếp theo là gì.**





