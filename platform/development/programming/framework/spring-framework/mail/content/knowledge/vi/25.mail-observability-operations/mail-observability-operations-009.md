# Dashboard theo sender, tenant và loại email

Trong một hệ thống sử dụng **Spring Framework Mail**, lệnh `JavaMailSender.send(...)` mới chỉ là một phần của vòng đời gửi thư. Ứng dụng có thể tạo mail job, đưa vào outbox, retry sau lỗi SMTP và nhận delivery/bounce event từ nhà cung cấp. Khi có nhiều tài khoản gửi, nhiều khách hàng tổ chức (*tenant*) và nhiều loại thông báo, một dashboard chỉ hiển thị “đã gửi bao nhiêu email” không đủ để vận hành.

Ví dụ nền tảng SaaS sử dụng ba sender:

~~~text
tx-primary        -> OTP, password reset, order confirmation, invoice
tx-backup         -> dự phòng cho thông báo giao dịch
marketing-primary -> newsletter và chương trình ưu đãi
~~~

Nếu OTP chậm, đội vận hành cần xác định **sender nào lỗi, tenant nào bị ảnh hưởng và loại email nào cần ưu tiên**. Dashboard nhiều chiều giúp tách một sự cố SMTP authentication khỏi tình huống tenant bị quota, worker bị backlog hay một chiến dịch marketing bị rate-limit.

Ba câu hỏi cốt lõi:

1. **Sender:** danh tính/hạ tầng gửi nào đang có vấn đề?
2. **Tenant:** khách hàng tổ chức nào chịu tác động và ở mức độ nào?
3. **Loại email:** use case nào đang bị ảnh hưởng: OTP, hóa đơn, xác nhận đơn hay newsletter?

**Nguyên tắc quan trọng:** phải phân biệt **logical job**, **SMTP/API attempt**, **submission được chấp nhận** và **delivery cuối cùng**. Chúng không phải một đơn vị đo và không được nhập chung vào một tỷ lệ “email thành công”.

## 1. Vì sao phải có dashboard nhiều chiều?

Giả sử toàn hệ thống có 4.200 attempts trong 5 phút, trong đó 200 lỗi:

~~~text
Tổng:
  Attempts:   4.200
  Exceptions:   200

Theo sender:
  tx-primary:         200 lỗi / 200 attempts
  marketing-primary:    0 lỗi / 4.000 attempts
~~~

Tỷ lệ exception toàn hệ thống khoảng 4,8%, nhưng **toàn bộ email từ sender giao dịch đã thất bại**. Một con số tổng có thể khiến sự cố quan trọng bị che bởi lưu lượng marketing.

Dashboard cần hỗ trợ cả ba kiểu nhìn:

| Góc nhìn | Câu hỏi | Hành động có thể hỗ trợ |
| --- | --- | --- |
| Theo sender | `tx-primary` có bị lỗi credentials không? | Kiểm tra auth, TLS, provider và failover |
| Theo tenant | Tenant A có phải tenant duy nhất bị chặn? | Kiểm tra quota, cấu hình riêng, quyền From |
| Theo loại email | OTP có bị chậm trong khi newsletter bình thường? | Ưu tiên worker, queue, SLO |

Một luồng điều tra:

~~~text
Overview
  -> Sender health: tx-primary
       -> Mail type: OTP
            -> Tenant impact: tenant-a
                 -> Job detail: job-752 / attempt-2
~~~

Trong thực tế, **không nên đưa cả ba chiều vào mọi time series mà không kiểm soát số giá trị**. Sender profile và mail type có thể là các tag ít giá trị; tenant ID thường có cardinality rất lớn và phù hợp hơn với database/analytics drill-down.

## 2. Định nghĩa chính xác sender

Từ “sender” có nhiều nghĩa trong Spring Mail:

| Danh tính | Ví dụ | Vai trò |
| --- | --- | --- |
| Header `From` | `orders@notify.example.com` | Địa chỉ người nhận nhìn thấy |
| Sender profile | `tx-primary` | Cấu hình gửi ổn định ở ứng dụng |
| SMTP auth identity | `smtp-transactional-account` | Credential/mailbox dùng xác thực |
| SMTP host | `smtp.vendor.example` | Server nhận kết nối |
| DKIM domain | `notify.example.com` | Domain ký email |
| Provider/stream | `provider-a/transactional` | Hạ tầng hoặc luồng gửi |

Nên chọn **`sender_profile`** làm chiều chính để vận hành:

~~~text
sender_profile = tx-primary
  From aliases:
    orders@notify.example.com
    security@notify.example.com
    billing@notify.example.com
  SMTP provider = provider-a
  Provider stream = transactional
~~~

Một lỗi SMTP credential có thể ảnh hưởng nhiều From aliases cùng sender profile. Nếu dashboard chỉ phân theo từng From address, người vận hành có thể bỏ lỡ nguyên nhân chung.

### 2.1. Sender profile phải ổn định

Đặt tên theo vai trò:

~~~text
tx-primary
tx-backup
marketing-primary
~~~

Không dùng hostname có số pod ngẫu nhiên, password, token, email cá nhân hoặc thời gian deploy làm sender profile. Khi đổi provider hoặc credentials, giữ identity cấp ứng dụng ổn định và ghi lại provider/version như metadata riêng.

### 2.2. Một job có thể thử qua nhiều provider

Ví dụ failover:

~~~text
job-752 / messageKey=invoice:INV-123

attempt-1: sender=tx-primary, provider=provider-a, timeout
attempt-2: sender=tx-backup,  provider=provider-b, accepted
~~~

Dashboard cần tách:

- **logical job:** một yêu cầu gửi;
- **sender profile của từng attempt:** xác định adapter/credential sử dụng;
- **provider của từng attempt:** xác định hệ thống ngoài nào gặp lỗi.

Đừng coi hai attempts là hai email nghiệp vụ mới. Và nếu attempt 1 timeout sau khi provider có thể đã nhận message, retry qua provider B vẫn có nguy cơ gửi trùng.

## 3. Tenant là chiều điều tra, không nhất thiết là metric label

Tenant đại diện cho một tổ chức/khách hàng trong ứng dụng multi-tenant:

~~~text
tenantId: company-4821
tenantTier: enterprise
region: ap-southeast
senderProfile: tx-primary
~~~

Với một SaaS có 10.000 tenant, nếu đưa `tenant_id` vào mọi Counter/Timer, số series có thể tăng rất lớn:

~~~text
sender × tenant × mail_type × result × provider × pod × histogram_bucket
~~~

Chẳng hạn, 4 sender × 10.000 tenant × 10 loại email × 5 status × 12 bucket tạo ra 24 triệu tổ hợp tiềm năng, chưa tính provider và pod. Không phải tất cả tổ hợp đều xuất hiện, nhưng đây là dấu hiệu rõ về nguy cơ chi phí cardinality.

### 3.1. Hai tầng dữ liệu

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Cảnh báo nhanh theo sender, stream, mail type | Prometheus/Micrometer metrics ít nhãn |
| Tỷ lệ lỗi theo gói tenant | Metric label `tenant_tier` giới hạn |
| Liệt kê Top N tenant bị ảnh hưởng | SQL/analytics/event store |
| Tìm job của một tenant cụ thể | Truy vấn DB theo `tenant_id` có phân quyền |
| Điều tra một message | Job timeline, attempt events, logs/traces |

Với ứng dụng ít tenant có danh sách cố định, có thể cân nhắc tenant label nếu đã kiểm tra cardinality. Nhưng với tenant động, hãy ưu tiên **metrics tổng hợp + drill-down từ dữ liệu job/event**.

### 3.2. Không dùng tên tenant hoặc địa chỉ nhận làm label

Tên khách hàng có thể thay đổi, trùng nhau và chứa thông tin nhạy cảm. Recipient email có cardinality rất cao, đồng thời là dữ liệu cá nhân. Không đưa các giá trị đó vào Prometheus labels hay dashboard public.

Lưu tenant ID bất biến trong event store; màn hình chi tiết có thể lấy tên hiển thị qua service có kiểm tra quyền.

## 4. Chuẩn hóa loại email

Không lấy subject làm `mail_type`:

~~~text
Mã OTP 483921
Mã OTP 729104
Hóa đơn INV-2026-000123
~~~

Subject thay đổi theo từng email và dễ chứa dữ liệu nhạy cảm. Nên dùng taxonomy có giới hạn:

| Mail type | Stream | Tính chất |
| --- | --- | --- |
| `otp` | Transactional | Thời hạn ngắn, latency quan trọng |
| `password_reset` | Transactional | Link/token có hạn |
| `order_confirmation` | Transactional | Gắn với event đơn hàng |
| `invoice` | Transactional | Có thể chứa PDF |
| `security_alert` | Transactional | Cảnh báo tài khoản |
| `newsletter` | Marketing | Gửi theo campaign |
| `promotion` | Marketing | Consent/opt-out quan trọng |
| `other` | Theo chính sách | Cần được phân loại lại khi đủ thông tin |

### 4.1. Mail type khác template và campaign

| Thuộc tính | Cardinality | Metrics label? |
| --- | --- | --- |
| `mail_type` | Hữu hạn, ổn định | Thường nên |
| `stream` | Giao dịch/marketing | Thường nên |
| `sender_profile` | Danh mục cấu hình | Thường nên |
| `tenant_tier` | Số gói nhỏ | Có thể |
| `template_version` | Thay đổi theo release | Thường không cần |
| `campaign_id` | Mỗi chiến dịch một giá trị | Event/analytics |
| `subject` | Gần như vô hạn | Không |
| `message_key` | Mỗi logical job riêng | Không |
| `recipient_address` | Gần như vô hạn, có PII | Không |

Một loại email có thể có template khác nhau theo tenant/ngôn ngữ nhưng vẫn cùng mail type. Nếu template version gây lỗi, dùng job log/event để drill-down thay vì phát series riêng cho mọi phiên bản.

## 5. Hiểu vòng đời trước khi định nghĩa metric

~~~mermaid
flowchart LR
    A["Business event"] --> B["Mail job created"]
    B --> C["Outbox/queue"]
    C --> D["Transport attempt"]
    D --> E{"SMTP/API response"}
    E -->|Accepted| F["SUBMITTED"]
    E -->|Error| G["Retry / Final / Unknown"]
    F --> H["Provider processing"]
    H --> I["DELIVERED"]
    H --> J["BOUNCED"]
    H --> K["COMPLAINT"]
    G --> D
~~~

| Trạng thái/sự kiện | Ý nghĩa |
| --- | --- |
| `CREATED` | Ứng dụng đã ghi yêu cầu gửi bền vững |
| `QUEUED` | Job đang chờ xử lý |
| `ATTEMPT_STARTED` | Worker bắt đầu một lần thử |
| `SUBMITTED` | SMTP/API báo nhận message theo contract |
| `SUBMISSION_EXCEPTION` | Transport ném lỗi; có thể chưa biết đã nộp một phần hay chưa |
| `RETRY_WAIT` | Có kế hoạch thử lại |
| `FAILED_FINAL` | Không còn retry theo chính sách |
| `DELIVERED` | Provider báo giao thư theo nghĩa của họ |
| `BOUNCED` | Provider báo delivery thất bại sau submission |
| `COMPLAINT` | Người nhận báo spam theo provider feedback |

**`SUBMITTED` không phải `DELIVERED`.** `JavaMailSender.send(...)` trả về bình thường thường chỉ cho biết bước SMTP submission hoàn tất. Email vẫn có thể bị bounce hoặc phân loại vào spam folder.

### 5.1. Một job có thể có nhiều attempts

~~~text
job-752
  attempt 1 -> SMTP 451
  attempt 2 -> SMTP timeout
  attempt 3 -> accepted
~~~

Kết quả:

- logical jobs = 1;
- transport attempts = 3;
- attempts báo lỗi = 2;
- cuối cùng job submitted = 1.

Tỷ lệ **attempt success** và **eventual job success** khác nhau. Nếu dùng attempts làm mẫu số của SLO giao dịch, dashboard sẽ báo sai mức độ ảnh hưởng.

### 5.2. Partial send và unknown

Khi gửi một `MimeMessage` có nhiều To/Cc/Bcc, Jakarta Mail có thể báo lỗi một phần: một số recipient đã được chấp nhận, một số bị từ chối. Một `MailSendException` không tự chứng minh mọi recipient đều chưa nhận submission.

Kết nối cũng có thể đứt sau `DATA` nhưng trước phản hồi cuối, khiến kết quả không chắc chắn. Khi đó nên lưu `UNKNOWN` hoặc trạng thái tương đương. Không tự động gắn `NOT_SENT` chỉ vì có exception.

Nếu sản phẩm cần dashboard theo recipient, dữ liệu job phải có **recipient-level outcome**; một boolean `sent` của message không đủ.

## 6. Catalog metrics cho Spring Mail

Ví dụ tên Micrometer và dạng xuất Prometheus thường gặp:

| Metric Micrometer | Tên Prometheus điển hình | Loại | Nội dung |
| --- | --- | --- | --- |
| `mail.jobs.created` | `mail_jobs_created_total` | Counter | Logical jobs đã được tạo |
| `mail.submission.attempts` | `mail_submission_attempts_total` | Counter | Lần thử transport |
| `mail.submission.duration` | `mail_submission_duration_seconds_*` | Timer | Thời lượng một lần gọi SMTP/API |
| `mail.retry.scheduled` | `mail_retry_scheduled_total` | Counter | Lần lên lịch retry |
| `mail.jobs.terminal` | `mail_jobs_terminal_total` | Counter | Job đạt trạng thái terminal |
| `mail.outbox.pending` | `mail_outbox_pending` | Gauge | Số jobs chưa terminal |
| `mail.outbox.oldest.pending.age` | `mail_outbox_oldest_pending_age_seconds` | Gauge | Tuổi job pending lâu nhất |
| `mail.delivery.events` | `mail_delivery_events_total` | Counter | Provider events được xử lý |
| `mail.suppressed` | `mail_suppressed_total` | Counter | Job bị policy chặn trước khi gửi |
| `mail.provider.throttled` | `mail_provider_throttled_total` | Counter | Rate-limit/deferral bởi provider |

Các tên Prometheus thực tế phụ thuộc registry và naming convention. Phải kiểm tra endpoint metrics của ứng dụng thay vì đoán chắc exporter sẽ dùng tên giống ví dụ.

### 6.1. Chọn nhãn có giới hạn

~~~text
sender_profile = tx_primary | tx_backup | marketing_primary
stream         = transactional | marketing
mail_type      = otp | invoice | order_confirmation | newsletter | other
tenant_tier    = free | standard | enterprise | internal
provider       = provider_a | provider_b
result         = submitted | exception
error_class    = auth | network | timeout | policy | recipient | unknown
~~~

Không phải metric nào cũng cần tất cả nhãn. Tăng số dimension không miễn phí, đặc biệt trên histogram có nhiều bucket.

**Không gắn:**

~~~text
tenant_id = customer-4821              // nhiều giá trị
message_key = order-confirmed:evt-123  // gần như unique
recipient = alice@example.net          // PII và nhiều giá trị
subject = "Mã đăng nhập 483921"        // PII/secret và nhiều giá trị
error_message = "550 bob@example.net" // không ổn định, có PII
~~~

### 6.2. Counter, Gauge và Timer

- Counter đo số lần xảy ra, chỉ tăng (attempts, retries, events).
- Gauge đo trạng thái hiện tại, có thể tăng/giảm (queue depth, worker claims).
- Timer đo duration và có thể xuất histogram phục vụ p95/p99.

Không dùng Counter để biểu diễn pending queue depth; cũng không dùng Gauge thay số email đã từng được gửi.

## 7. Kiến trúc thu thập số liệu

~~~mermaid
flowchart TD
    A["Business services"] --> B["Outbox / job store"]
    B --> C["Mail worker / JavaMailSender"]
    C --> D["SMTP/API provider"]
    D --> E["Provider webhook"]
    A --> F["Micrometer"]
    C --> F
    E --> F
    F --> G["Prometheus / metrics backend"]
    G --> H["Grafana dashboard + alerts"]
    B --> I["Job/attempt event store"]
    C --> I
    E --> I
    I --> J["Tenant drill-down / analytics"]
    J --> H
~~~

Có hai dòng dữ liệu chính:

1. **Metrics tổng hợp:** nhanh, nhãn hữu hạn, dùng cho health, alert, SLO xu hướng.
2. **Event/job store:** chi tiết tới tenant, message, attempt và thời điểm; phục vụ điều tra, báo cáo và audit có phân quyền.

Log/traces bổ sung thông tin correlation khi cần. Không dùng trace count để thay metric tổng số job vì hệ thống tracing có thể sampling.

### 7.1. Đặt instrumentation đúng chỗ

| Sự kiện | Điểm ghi nhận tốt | Điều cần tránh |
| --- | --- | --- |
| Job created | Sau khi outbox/job được commit | Đếm trước khi transaction rollback |
| Attempt started | Worker bắt đầu gửi | Đếm job chỉ nằm chờ |
| Submission result | SMTP/API adapter | Đổi tên thành delivered |
| Retry scheduled | Sau khi lịch retry được lưu | Tăng metric nhiều lần do transaction retry |
| Pending gauge | Trạng thái DB/queue hiện tại | Cộng cùng một snapshot ở mọi replica |
| Delivery event | Sau khi xác minh/dedup webhook | Đếm trùng webhook |
| Suppression | Tầng chính sách | Coi suppression là transport error |

Counter nằm trong bộ nhớ không rollback cùng database. Nếu cần **báo cáo chính xác unique job đã commit**, hãy lấy từ dữ liệu bền vững hoặc event đã deduplicate; metrics ở tiến trình phù hợp giám sát vận hành hơn là kế toán tuyệt đối.

## 8. Dùng Micrometer trong Spring Boot

Với Spring Boot có Actuator và Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: mail-platform
~~~

Endpoint `/actuator/prometheus` không nên mở cho Internet không kiểm soát. Cần giới hạn truy cập và dùng TLS/network policy/authorization theo hạ tầng.

### 8.1. Dùng enum để giới hạn cardinality

~~~java
public enum SenderProfile {
    TX_PRIMARY,
    TX_BACKUP,
    MARKETING_PRIMARY
}

public enum TenantTier {
    FREE, STANDARD, ENTERPRISE, INTERNAL
}

public enum MailType {
    OTP, PASSWORD_RESET, ORDER_CONFIRMATION,
    INVOICE, SECURITY_ALERT, NEWSLETTER, PROMOTION, OTHER
}
~~~

Một profile ID khác với địa chỉ sender thực tế. Những enum này do code quản lý; không tạo thêm label trực tiếp từ input người dùng.

### 8.2. Ghi metrics bằng Counter và Timer

~~~java
package com.example.mail.metrics;

import java.time.Duration;
import java.util.Locale;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class MailAttemptMetrics {
    private final MeterRegistry registry;

    public MailAttemptMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            SenderProfile sender,
            TenantTier tier,
            MailType type,
            boolean transportReturnedNormally,
            Duration elapsed) {

        Tags base = Tags.of(
                "sender_profile", tag(sender),
                "tenant_tier", tag(tier),
                "mail_type", tag(type));

        String result = transportReturnedNormally
                ? "submitted" : "exception";

        Counter.builder("mail.submission.attempts")
                .tags(base)
                .tag("result", result)
                .description("SMTP/API submission attempts")
                .register(registry)
                .increment();

        Timer.builder("mail.submission.duration")
                .tags(base)
                .description("Transport attempt duration")
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed);
    }

    private static String tag(Enum<?> value) {
        return value.name().toLowerCase(Locale.ROOT);
    }
}
~~~

Khi export Prometheus, `mail.submission.attempts` thường trở thành `mail_submission_attempts_total`. `publishPercentileHistogram()` có thể tạo `_bucket` phục vụ p95, đồng thời tăng số series; tránh bật histogram với tag không giới hạn.

### 8.3. Bọc JavaMailSender tại transport boundary

~~~java
import jakarta.mail.internet.MimeMessage;
import java.time.Duration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class InstrumentedSmtpAdapter {
    private final JavaMailSender sender;
    private final MailAttemptMetrics metrics;

    public InstrumentedSmtpAdapter(
            JavaMailSender sender,
            MailAttemptMetrics metrics) {
        this.sender = sender;
        this.metrics = metrics;
    }

    public void submit(
            MimeMessage message,
            SenderProfile profile,
            TenantTier tier,
            MailType type) {

        long started = System.nanoTime();
        boolean returnedNormally = false;
        try {
            sender.send(message);
            returnedNormally = true;
        } finally {
            long nanos = System.nanoTime() - started;
            metrics.record(
                    profile,
                    tier,
                    type,
                    returnedNormally,
                    Duration.ofNanos(Math.max(0L, nanos)));
        }
    }
}
~~~

Ý nghĩa:

- Mỗi lời gọi `submit(...)` là **một attempt**.
- `submitted` chỉ biểu diễn lời gọi transport trả bình thường.
- `exception` không tự khẳng định mọi recipient đều chưa được gửi; với partial/unknown cần phân tích sâu hơn.
- `finally` giúp ghi duration cả khi có lỗi; exception vẫn được truyền tới tầng điều phối retry.
- Đoạn code không ghi lại job state hoặc giải quyết outbox/idempotency; đây là trách nhiệm khác.

Nếu có nhiều `JavaMailSender` beans, cần inject đúng sender/adapter cho profile bằng `@Qualifier` hoặc router. Không cho client bên ngoài tự gán profile tùy ý để làm sai số liệu.

### 8.4. Không đếm jobs created trước commit

Giả sử service:

~~~text
BEGIN DB transaction
  UPDATE order
  INSERT mail_outbox
  Increment jobs_created_total
ROLLBACK
~~~

Counter đã tăng nhưng job không tồn tại. Vì vậy, nếu cần số logical job bền vững, nên dùng DB/event đã commit hoặc xuất sự kiện sau commit với contract rõ. Đừng xem metrics in-memory là bản ghi kế toán bảo đảm chính xác một lần.

## 9. Gauge backlog và nhiều replicas

Một dashboard vận hành thường cần:

~~~text
Pending: 720 jobs
Retry wait: 64 jobs
Oldest eligible pending: 82 seconds
Active worker claims: 24
~~~

Ví dụ query PostgreSQL từ bảng outbox:

~~~sql
SELECT
    sender_profile,
    mail_type,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
    ) AS pending_jobs,
    MIN(created_at) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
    ) AS oldest_created_at
FROM mail_outbox
GROUP BY sender_profile, mail_type;
~~~

Đây là ví dụ tổng hợp, không phải một phương thức có sẵn của Spring Mail. Nếu không có pending job, timestamp oldest là `NULL`. Khi xuất metric tuổi, có thể dùng:

~~~text
age_seconds = now - oldest_created_at
~~~

nhưng phải xử lý trường hợp không có job và xác định time zone thống nhất.

### 9.1. Không cộng ba lần cùng một database snapshot

Nếu ba pod cùng query một outbox chung:

~~~text
mail_outbox_pending{instance="pod-a"} 720
mail_outbox_pending{instance="pod-b"} 720
mail_outbox_pending{instance="pod-c"} 720
~~~

Truy vấn `sum(mail_outbox_pending)` ra 2.160, sai so với 720.

Giải pháp:

- chỉ một exporter chịu trách nhiệm đo tổng backlog;
- hoặc mỗi exporter đo một shard/partition **không trùng nhau**, rồi cộng;
- nếu các replica thực sự xuất cùng một snapshot toàn cục, có thể dùng `max` tạm thời nhưng phải xét độ trễ/stale data;
- tốt hơn, định nghĩa rõ một chủ sở hữu cho metric global.

### 9.2. “Oldest pending” khác “Overdue for retry”

Một job được tạo 2 giờ trước nhưng có `next_attempt_at` ở tương lai có thể **chưa quá hạn**. Cần phân biệt:

- tuổi từ `created_at`;
- tuổi từ khi `next_attempt_at` đã đến mà worker chưa claim;
- thời gian kẹt trong `PROCESSING` hoặc lease đã hết hạn.

Với alert “worker bị tắc”, **eligible-but-unclaimed age** thường phản ánh tốt hơn tuổi tất cả jobs đang chờ backoff.

## 10. Truy vấn Prometheus theo sender và loại email

Các ví dụ giả định metric/tag được xuất với tên như mục 6.

### 10.1. Throughput submitted theo sender

~~~promql
sum by (sender_profile) (
  rate(mail_submission_attempts_total{result="submitted"}[5m])
)
~~~

Kết quả là **attempts submitted/second**, không phải unique delivered emails/second.

### 10.2. Số attempts submitted trong một giờ theo loại email

~~~promql
sum by (mail_type) (
  increase(mail_submission_attempts_total{result="submitted"}[1h])
)
~~~

`rate` phù hợp đo tốc độ, `increase` phù hợp ước lượng số lần tăng trong window. Cả hai xử lý counter reset tốt hơn phép trừ raw counter tại hai timestamp tùy ý.

### 10.3. Exception rate theo sender

~~~promql
sum by (sender_profile) (
  rate(mail_submission_attempts_total{result="exception"}[10m])
)
/
clamp_min(
  sum by (sender_profile) (
    rate(mail_submission_attempts_total[10m])
  ),
  0.001
)
~~~

Đây là tỷ lệ exception **trên attempts**. Mẫu số 0 làm tỷ lệ không xác định; `clamp_min` tránh chia 0 nhưng không thay thế việc hiển thị **N/A** khi lượng mẫu quá ít. Alert cần thêm điều kiện số attempts tối thiểu.

### 10.4. Heatmap sender × mail type

~~~promql
sum by (sender_profile, mail_type) (
  rate(mail_submission_attempts_total{result="exception"}[10m])
)
/
clamp_min(
  sum by (sender_profile, mail_type) (
    rate(mail_submission_attempts_total[10m])
  ),
  0.001
)
~~~

Đây là nguồn cho heatmap hoặc bảng tỷ lệ lỗi theo từng cặp sender/type. Ô không có attempts nên thể hiện N/A; đừng mặc định 0% thành công.

### 10.5. p95 submission latency

Nếu Timer đã bật histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, sender_profile) (
    rate(mail_submission_duration_seconds_bucket[10m])
  )
)
~~~

Histogram percentile là ước lượng dựa trên bucket. Nếu exporter không có `_bucket`, query sẽ không ra kết quả; cần kiểm tra cấu hình registry/endpoint. p95 ở đây đo **SMTP/API attempt**, không bao gồm toàn bộ thời gian job nằm trong queue.

### 10.6. Không dùng rate cho backlog Gauge

~~~promql
mail_outbox_pending{stream="transactional"}
~~~

Metric dạng Gauge được đọc trực tiếp hoặc tổng hợp theo shard thật. `rate(...)` của Gauge không biểu diễn số job đang chờ.

## 11. Dashboard layout gợi ý

Một dashboard nên có nhiều cấp:

### 11.1. Executive/operations overview

~~~text
EMAIL OPERATIONS — Last 1 hour
---------------------------------------------------------
Logical jobs created | SMTP attempts | Exception rate
Oldest eligible job  | p95 submit    | Provider throttles
---------------------------------------------------------
Submission throughput by stream / sender
Outbox depth + queue age
Error classes by provider
Recent deploy / credential rotation markers
~~~

Các panel phải ghi rõ đơn vị, time window, timezone, metric source và mức độ trễ cập nhật.

### 11.2. Sender health table

| Sender | Stream | Attempts/5 phút | Exception rate | p95 submit | Pending |
| --- | --- | ---: | ---: | ---: | ---: |
| `tx-primary` | Transactional | 420 | 0,2% | 380 ms | 12 |
| `tx-backup` | Transactional | 0 | N/A | N/A | 0 |
| `marketing-primary` | Marketing | 2.900 | 3,1% | 1,4 s | 1.500 |

Các con số chỉ minh họa. Không hiển thị “0% lỗi” cho sender không có attempts; đó là **không có mẫu**, không phải bằng chứng khỏe.

### 11.3. Mail type view

| Mail type | Jobs created | Oldest eligible | Final failed | Chỉ số ưu tiên |
| --- | ---: | ---: | ---: | --- |
| `otp` | 1.200 | 6 s | 2 | Submission trước khi token hết hạn |
| `order_confirmation` | 900 | 10 s | 5 | Đồng bộ với trạng thái đơn hàng |
| `invoice` | 500 | 20 s | 4 | Chuẩn bị attachment và size limits |
| `newsletter` | 20.000 | 4 phút | 70 | Complaint, deferral, campaign pacing |

Giá trị chỉ minh họa. OTP và newsletter không nên chung SLO dù cùng dùng SMTP.

### 11.4. Tenant impact view

Trang có phân quyền:

~~~text
Tenant: company-4821
Period: 24 hours

Jobs by type:
  OTP                 80
  Order confirmation 150
  Invoice             10
  Newsletter         500

Health:
  Retry wait           12
  Failed final          3
  Hard bounced          4

Recent jobs:
  jobId | type | sender | status | attempts | createdAt
~~~

Các số ở đây là minh họa. Với nhiều tenant, dùng bảng Top N impacted hoặc tìm kiếm theo tenant ID trong analytics. Không phát metric riêng cho mỗi tenant chỉ để tạo trang này.

### 11.5. Job timeline

~~~text
job-752 / type=invoice / sender=tx-primary
10:00:00 CREATED
10:00:01 CLAIMED
10:00:02 ATTEMPT_STARTED #1
10:00:03 SMTP 451 / RETRY_WAIT
10:01:03 ATTEMPT_STARTED #2
10:01:04 SUBMITTED
10:01:08 DELIVERED (provider event)
~~~

Trang này có thể mở log/trace theo job ID và correlation ID, nhưng chỉ hiển thị metadata được phép. Không công khai OTP, nội dung mail hoặc toàn bộ recipient list.

## 12. Drill-down theo tenant qua SQL

Prometheus giúp thấy hệ thống gặp vấn đề; SQL/event store giúp biết tenant và job nào bị ảnh hưởng.

### 12.1. Schema tối giản

~~~sql
CREATE TABLE mail_job (
    job_id         VARCHAR(64) PRIMARY KEY,
    tenant_id      VARCHAR(64) NOT NULL,
    sender_profile VARCHAR(80) NOT NULL,
    mail_type      VARCHAR(80) NOT NULL,
    stream         VARCHAR(30) NOT NULL,
    status         VARCHAR(30) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    submitted_at   TIMESTAMP
);

CREATE TABLE mail_attempt (
    attempt_id   VARCHAR(64) PRIMARY KEY,
    job_id       VARCHAR(64) NOT NULL REFERENCES mail_job(job_id),
    provider     VARCHAR(80) NOT NULL,
    result       VARCHAR(30) NOT NULL,
    error_class  VARCHAR(50),
    started_at   TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

CREATE TABLE mail_delivery_event (
    id                VARCHAR(64) PRIMARY KEY,
    job_id            VARCHAR(64) NOT NULL REFERENCES mail_job(job_id),
    provider          VARCHAR(80) NOT NULL,
    provider_event_id VARCHAR(150),
    event_type        VARCHAR(40) NOT NULL,
    occurred_at       TIMESTAMP,
    received_at       TIMESTAMP NOT NULL
);
~~~

Schema nhằm giải thích mô hình, không phải migration production hoàn chỉnh. Trong ứng dụng thực tế cần indexes, timestamp UTC/timezone, retention, unique constraint cho provider event trong scope đúng, policy PII và recipient-level rows nếu một message nhiều người nhận.

### 12.2. Top tenant theo logical jobs

Ví dụ PostgreSQL:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS created_jobs
FROM mail_job
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY tenant_id
ORDER BY created_jobs DESC
LIMIT 20;
~~~

Đây là số logical job rows, không phải số attempts. Một logical job đại diện một message hay một recipient phải được định nghĩa ở mô hình ứng dụng.

### 12.3. Query chi tiết được phân quyền

~~~sql
SELECT
    job_id,
    sender_profile,
    mail_type,
    status,
    created_at,
    submitted_at
FROM mail_job
WHERE tenant_id = :authorized_tenant_id
  AND sender_profile = :sender_profile
  AND mail_type = :mail_type
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 100;
~~~

`authorized_tenant_id` phải được backend xác nhận theo người dùng/role, không được chỉ lấy từ dropdown. Query nên sử dụng prepared parameters để tránh SQL injection.

### 12.4. Snapshot trạng thái theo cohort

~~~sql
SELECT
    tenant_id,
    sender_profile,
    mail_type,
    COUNT(*) AS jobs_created,
    COUNT(*) FILTER (
        WHERE status = 'SUBMITTED'
    ) AS jobs_submitted,
    COUNT(*) FILTER (
        WHERE status = 'FAILED_FINAL'
    ) AS jobs_failed_final,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING','PROCESSING','RETRY_WAIT')
    ) AS jobs_nonterminal
FROM mail_job
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY tenant_id, sender_profile, mail_type;
~~~

Đây là **cohort theo thời điểm tạo** với trạng thái **tại thời điểm query**. Nó không phải “số email submitted trong giờ” vì một job tạo trước giờ này có thể submitted bây giờ. Muốn đếm submission theo thời điểm, truy vấn `submitted_at` hoặc attempt/event table với window tương ứng.

### 12.5. Backlog không được bỏ sót job cũ

Nếu backlog query lọc `created_at` chỉ trong 24 giờ gần nhất, job kẹt 3 ngày sẽ biến mất khỏi dashboard dù vẫn pending.

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS pending_count,
    MIN(created_at) AS oldest_created_at
FROM mail_job
WHERE status IN ('PENDING','PROCESSING','RETRY_WAIT')
GROUP BY tenant_id;
~~~

Tách backlog hiện tại khỏi báo cáo cohort lịch sử. Với số lượng tenant/job lớn, dùng materialized view hoặc analytics store thay vì query toàn bảng trên mỗi refresh dashboard.

## 13. Delivery, bounce và provider webhook

Một provider có thể gửi event sau khi SMTP/API đã nhận message:

~~~text
provider_message_id=provider-abc-123
event_type=DELIVERED
occurred_at=2026-11-12T09:00:15Z
~~~

Về sau còn có thể nhận `BOUNCED`, `DEFERRED`, `COMPLAINT`. Định nghĩa “delivered” tùy provider và thường không chứng minh người dùng đã đọc thư.

### 13.1. Webhook có thể trùng, trễ và sai thứ tự

~~~text
T1 Provider tạo DELIVERED event
T2 Provider tạo COMPLAINT event
T3 Webhook COMPLAINT đến trước
T4 Webhook DELIVERED đến sau
~~~

Do đó cần:

- xác thực webhook signature/authorization;
- liên kết provider message ID với local job/attempt;
- deduplicate event bằng provider event ID hoặc identity được provider quy định;
- phân biệt `occurred_at` và `received_at`;
- có state transitions rõ ràng;
- lưu event history khi cần audit;
- nhận biết khi provider webhook bị gián đoạn.

### 13.2. Đếm event khác unique delivery

Một message có thể có nhiều deferred events, hoặc webhook `DELIVERED` bị gửi lặp. `mail_delivery_events_total{event_type="delivered"}` là số event xử lý theo contract instrumentation, chưa chắc là số unique emails delivered nếu chưa deduplicate.

Khi tính bounce/complaint rate, phải xác định:

- mẫu số là unique submissions, unique recipient submissions hay jobs?
- kết quả được tính theo cohort gửi hay ngày nhận event?
- provider có hỗ trợ reporting đầy đủ không?
- có loại bỏ duplicate không?

Không so sánh provider A có webhook đầy đủ với provider B không có tracking rồi kết luận B có tỷ lệ delivery 0%.

### 13.3. Missing data cần hiển thị rõ

Nếu webhook chưa cấu hình:

~~~text
Delivery tracking: N/A
Reason: Provider events not configured
~~~

Không tự điền “0 delivered” và coi là lỗi gửi. Thiếu dữ liệu là vấn đề **observability coverage**, không phải bằng chứng message bị thất bại.

## 14. SLO theo loại email và sender

**SLI** là chỉ số đo chất lượng dịch vụ. **SLO** là mục tiêu đặt ra cho SLI đó trong một thời kỳ.

Ví dụ mục tiêu giả định:

| Đối tượng | SLI | SLO minh họa |
| --- | --- | --- |
| OTP | Tỷ lệ logical job submitted trong 30 giây kể từ khi tạo | ≥ 99% / 30 ngày |
| Xác nhận đơn | Job submitted trong 2 phút | ≥ 99,5% / 30 ngày |
| Invoice | Submitted trong thời hạn nghiệp vụ | Theo hợp đồng |
| Newsletter | Hoàn thành campaign trong lịch | Theo deadline |
| Transactional sender | SMTP exception rate trên attempts | Ngưỡng do đội vận hành đặt |

Những giá trị này không phải chuẩn bắt buộc. SLO phải định nghĩa:

- bắt đầu từ business event committed hay job created?
- kết thúc ở submitted hay provider delivered?
- retry nhiều lần tính một hay nhiều?
- suppression và job hủy hợp lệ xử lý thế nào?
- provider missing events ảnh hưởng mẫu số ra sao?

### 14.1. Tách các khoảng thời gian

~~~text
Business event committed
  | A. event -> job persisted
Mail job created
  | B. queue waiting time
Worker begins attempt
  | C. SMTP/API submission duration
SUBMITTED
  | D. delivery delay (nếu có provider events)
DELIVERED
~~~

Một SMTP adapter rất nhanh không thể che giấu queue bị tắc 10 phút. Với OTP, thường cần quan sát **job creation -> submission**, không chỉ transport duration.

### 14.2. Đừng dùng attempt success rate thay job SLO

Một OTP job có 3 attempts và submitted sau 8 giây có thể vẫn đạt SLO 30 giây. Attempt success rate chỉ 1/3 nhưng logical job hoàn thành trong hạn.

Nếu SLO đo **khả năng hoàn thành yêu cầu gửi**, phải lấy logical jobs và thời hạn làm đơn vị, không lấy số attempts.

## 15. Alerting có ngữ cảnh

### 15.1. Các loại alert

| Alert | Chẩn đoán sơ bộ | Hành động |
| --- | --- | --- |
| Authentication failures tăng | Credential/OAuth/SMTP policy | Kiểm tra auth và sender |
| Oldest eligible pending tăng | Worker/queue tắc | Kiểm tra claim, scheduler, backlog |
| OTP deadline misses | Thông báo thiết yếu bị chậm | Ưu tiên sự cố |
| Provider throttling 4xx | Quota/rate limit | Giảm tốc, xem account usage |
| Marketing complaint spike | Campaign/danh sách có vấn đề | Tạm dừng chiến dịch, điều tra |
| Provider event webhook ngừng | Mất visibility delivery | Kiểm tra webhook ingestion |
| Một tenant lỗi bất thường | Cấu hình/quota/sender policy riêng | Drill-down tenant |
| Failover liên tục | Primary sender/provider bất ổn | Điều tra nguyên nhân, chống duplicate |

### 15.2. Alert rule ví dụ

~~~yaml
groups:
  - name: mail-operations
    rules:
      - alert: TransactionalMailBacklogOld
        expr: mail_outbox_oldest_pending_age_seconds{stream="transactional"} > 120
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Transactional mail backlog is aging"
          description: "Check eligible jobs, workers, provider throttling."
~~~

Ngưỡng 120 giây/5 phút chỉ mang tính minh họa; OTP có thể cần mức thấp hơn. Hãy chắc metric thực sự phản ánh **eligible pending jobs**, không tính cả job đang chờ backoff hợp lệ rồi gây cảnh báo giả.

### 15.3. Tỷ lệ cần volume guard

Một sender có 1 attempt và 1 lỗi sẽ có error rate 100%. Điều đó chưa đủ chứng minh outage diện rộng.

Một chính sách alert có thể là:

~~~text
error rate > threshold
AND attempts within 10m >= minimum sample count
AND condition persists for N minutes
~~~

Ngược lại, nếu business events tiếp tục tạo job nhưng không có attempt nào, exception rate có thể bằng 0 hoặc không có dữ liệu. Cần alert **silent failure** dựa trên created jobs, pending depth và oldest eligible age.

### 15.4. Không đẩy PII vào alert

Alert nên chứa sender profile, stream, type, region, số job và dashboard link. Không nhúng OTP, message body, raw recipient list, SMTP password, bearer token hoặc full provider response có thông tin nhạy cảm.

## 16. Runbook điều tra theo sender, tenant và mail type

Giả sử `tx-primary` có SMTP exception rate tăng:

1. **Khoanh vùng sender:** chỉ `tx-primary` hay cả `tx-backup` và marketing?
2. **Khoanh vùng loại mail:** OTP/password reset hay mọi loại giao dịch?
3. **Khoanh vùng tenant:** một tenant, một tier hay toàn hệ thống?
4. **Đọc error class:** auth, TLS, timeout, provider policy, recipient reject, data size?
5. **Đối chiếu thay đổi gần đây:** deploy, credential rotation, OAuth scopes, DNS, queue configuration?
6. **Xem backlog:** pending/eligible age, active workers, retry lịch, quota.
7. **Đối chiếu provider:** health status, throttling, account suspension, webhook data.
8. **Giảm thiểu:** điều tiết marketing nếu quota chung, sửa cấu hình, failover theo runbook đã kiểm thử.
9. **Đảm bảo idempotency:** không retry mù khi submission outcome có thể đã thành công.
10. **Xác nhận phục hồi:** lỗi giảm, backlog được xử lý, logical jobs đáp ứng deadline.

### 16.1. Khi chỉ một tenant lỗi

Kiểm tra:

- tenant-specific SMTP identity hoặc `From`/Send As permission;
- quota tenant và provider quota;
- recipient list có hard bounce cao;
- template theo tenant lỗi render/attachment;
- suppression policy và consent;
- sai mapping sender profile/tenant.

Không kết luận tenant sai chỉ vì lỗi xuất hiện ở một tenant; cần đọc job/attempt evidence.

### 16.2. Khi chỉ marketing gặp lỗi

Kiểm tra campaign spike, list hygiene, complaint, rate limit, deferral, suppression, tracking domain và ESP marketing stream. Có thể tạm dừng campaign trong khi bảo vệ transactional capacity. Nhưng nếu hai luồng dùng chung provider account quota, tác động vẫn có thể lan sang OTP.

## 17. Các bẫy làm dashboard sai

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đếm retries thành mail jobs mới | Thổi phồng lượng mail | Tách job ID và attempt ID |
| Coi `send` trả về là Inbox delivered | Báo cáo quá lạc quan | Provider delivery event riêng |
| Coi mọi exception là chưa gửi ai | Sai với partial/unknown | Recipient-level outcome/UNKNOWN |
| Đếm duplicate webhook | Delivery bị nhân đôi | Idempotent event processing |
| Histogram có `tenant_id` hoặc `job_id` | Cardinality/chi phí rất cao | Bounded labels + drill-down store |
| Tính pending bằng sum trên mọi DB-querying pod | Queue depth bị nhân theo replica | Một exporter hoặc shard rõ |
| Không hiển thị timezone/time window | Đếm “hôm nay” sai | UTC storage, timezone UI rõ |
| Filter created_at trên backlog | Che giấu job quá cũ | Query mọi nonterminal jobs |
| So sánh provider có/không có webhook | Delivery rate không tương đương | Data coverage indicator |
| Đếm Counter trong DB transaction trước commit | Metric có job bị rollback | Đo sau commit hoặc query DB |
| Không phân biệt retry wait và overdue | Cảnh báo sai | Theo dõi eligible backlog |
| Error rate không có sample guard | Alert khi 1 lỗi nhỏ | Volume + duration guard |
| Chỉ có error rate, không có silent-failure alert | Không nhận ra worker ngừng gửi | Created-vs-attempted, oldest age |
| Tenant filter không kiểm tra backend authorization | Lộ dữ liệu tenant khác | Enforce quyền tại query/API |
| Gắn full exception text vào metric | PII + cardinality cao | Error-class enum, log kiểm soát |

### 17.1. Counter reset và scrape gap

Prometheus `rate`/`increase` hỗ trợ việc counter reset khi process restart. Tuy nhiên, nếu scrape bị gián đoạn kéo dài hoặc exporter mất dữ liệu, hệ thống vẫn có thể thiếu mẫu. Không dùng Counter in-memory làm nguồn billing/audit chính xác tuyệt đối.

### 17.2. Timezone và dữ liệu đến muộn

Job created lúc 23:59 UTC có thể thuộc ngày hôm sau theo timezone của tenant. Event delivered có thể đến nhiều phút/giờ sau. Dashboard cần công bố rõ:

- group theo `occurred_at` hay `received_at`;
- ngày theo UTC hay local tenant timezone;
- số liệu có thể thay đổi khi event trễ đến;
- query là cohort created hay observation window.

### 17.3. Traces bị sampling

Trace có thể chỉ lưu một phần requests. Dùng traces để tìm hành trình một mail job; không lấy số trace làm tổng số email đã gửi.

## 18. Bảo mật dashboard multi-tenant

Một dashboard có thể vô tình tiết lộ:

- tenant nào đang hoạt động;
- khối lượng đơn hàng/hóa đơn;
- email người nhận;
- lỗi gửi chứa thông tin cá nhân;
- thông tin provider và quyền tài khoản gửi.

Phân quyền minh họa:

| Nhóm | Quyền |
| --- | --- |
| On-call nội bộ | Xem sender/stream và drill-down theo vai trò |
| Support | Chỉ tenant được giao xử lý |
| Admin tenant | Chỉ dữ liệu tenant của mình |
| Marketing team | Campaign/marketing data, không xem OTP |
| Security team | Audit và sender authentication anomalies |

### 18.1. UI dropdown không phải authorization

Nếu API nhận `tenant_id` từ URL rồi query tự do, người dùng có thể sửa ID để xem tenant khác. Backend phải kiểm tra principal/role/tenant membership. Có thể dùng row-level security hoặc service layer để thực thi policy.

### 18.2. Privacy trong metrics và logs

Không đưa:

- SMTP password/API key/OAuth token;
- OTP hoặc reset token;
- message body/attachments;
- raw recipient addresses;
- subject tùy ý;
- tenant names không được phép công khai;

vào metric tags hoặc alert. Job ID/correlation ID có thể xuất hiện trong log có phân quyền; chỉ xem recipient thật trong màn hình có audit khi cần hỗ trợ.

### 18.3. Retention và chi phí

Metrics tổng hợp có thể lưu lâu để phân tích xu hướng. Event store chi tiết theo recipient phải có retention, quyền truy cập và cơ chế xóa thích hợp. Không lưu cả MIME raw hoặc PDF attachment chỉ để hỗ trợ một dashboard.

## 19. Kiểm thử instrumentation

### 19.1. Unit test với SimpleMeterRegistry

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MailAttemptMetricsTest {

    @Test
    void recordsAttemptWithBoundedTags() {
        try (SimpleMeterRegistry registry =
                new SimpleMeterRegistry()) {
            MailAttemptMetrics metrics =
                    new MailAttemptMetrics(registry);

            metrics.record(
                    SenderProfile.TX_PRIMARY,
                    TenantTier.ENTERPRISE,
                    MailType.ORDER_CONFIRMATION,
                    true,
                    Duration.ofMillis(250));

            double count =
                    registry.get("mail.submission.attempts")
                            .tags(
                                    "sender_profile", "tx_primary",
                                    "tenant_tier", "enterprise",
                                    "mail_type", "order_confirmation",
                                    "result", "submitted")
                            .counter()
                            .count();

            assertEquals(1.0, count);
        }
    }
}
~~~

Test này chỉ kiểm tra metrics trong bộ nhớ; không cần SMTP connection. Nên test thêm:

- exception từ `JavaMailSender.send(...)` vẫn tăng `result=exception`;
- exception vẫn được truyền lên caller, không bị nuốt;
- timer được ghi cả lúc lỗi;
- retry lần hai tăng attempts nhưng không tạo logical job mới;
- không có tag động ngoài danh mục cho phép.

### 19.2. Integration test

Dùng GreenMail/Mailpit hoặc SMTP server test để:

1. Gửi một message tới test server thật.
2. Xác minh attempt counter/timer.
3. Mô phỏng lỗi submission và error classification.
4. Xác minh outbox job state và retry.
5. Đảm bảo cùng event không bị đếm thành nhiều logical job.
6. Dọn mailbox/outbox để test sau không bị ảnh hưởng.

Mock sender không chứng minh provider delivery. Provider webhooks cần test riêng với event ID lặp, event đến trễ/sai thứ tự và signature validation.

### 19.3. Kiểm tra Prometheus/Grafana

- Endpoint `/actuator/prometheus` xuất đúng tên metrics, được bảo vệ truy cập.
- Histogram buckets thực sự tồn tại trước khi dùng `histogram_quantile`.
- Query `rate`/`increase` dùng trên Counter, backlog dùng Gauge.
- Multiple pods không làm tổng pending tăng giả.
- Sender có zero traffic được hiển thị N/A khi phù hợp.
- Alerts có volume guard, không page vì một mẫu duy nhất.
- Tenant drill-down enforce authorization.
- Dashboard ghi rõ timeframe, timezone, source và thời điểm cập nhật.

## 20. Tình huống tổng hợp: OTP lỗi sau đổi credential

Ứng dụng có:

~~~text
Sender profiles: tx-primary, tx-backup, marketing-primary
Mail types: otp, order_confirmation, invoice, newsletter
Tenants: company-a, company-b, ...
~~~

Vào một thời điểm vận hành giả định, dashboard cho thấy:

~~~text
Overall exception rate: 2.1%

By sender:
  tx-primary:         45% exception
  marketing-primary:  0.2% exception

By mail type:
  otp:                60% exception
  newsletter:          0.2% exception
~~~

Những số liệu này chỉ minh họa.

### 20.1. Điều tra

1. Lọc `sender=tx-primary`.
2. Thấy nhóm `error_class=auth` tăng.
3. Đối chiếu marker “SMTP credentials rotated” gần thời điểm lỗi.
4. Xem backlog OTP và các tenant có job pending quá hạn.
5. Kiểm tra token/credential, SMTP AUTH policy và `From`/Send As permission.
6. Nếu có backup sender đã kiểm thử và có đủ quyền, cân nhắc failover theo runbook.
7. Không tự gửi lại tất cả job ở trạng thái unknown vì có thể đã được server nhận.

### 20.2. Xác nhận phục hồi

Theo dõi:

- exception rate giảm về mức bình thường;
- oldest eligible pending giảm;
- OTP logical jobs đạt `SUBMITTED` trong thời hạn;
- final failed không tiếp tục tăng;
- attempts/job không tăng bất thường do retry;
- provider delivery event được theo dõi riêng.

**Nhờ dashboard theo sender, tenant và loại email, đội vận hành xác định đúng thành phần và nhóm người dùng bị ảnh hưởng**, thay vì suy đoán từ một tỷ lệ tổng.

## 21. Checklist triển khai

### Định danh

- [ ] `sender_profile` ổn định và không chứa credential.
- [ ] `mail_type` có danh mục hữu hạn.
- [ ] Tenant ID được lưu trong job/event store, không tạo metric cardinality vô hạn.
- [ ] Provider/stream/tenant tier được gắn ở vị trí phù hợp.

### Semantics

- [ ] Phân biệt logical jobs, attempts, submitted, delivery events.
- [ ] Có trạng thái unknown/partial khi kết quả SMTP không chắc chắn.
- [ ] Tách queue wait và SMTP submission duration.
- [ ] Gauge backlog không bị nhân đôi bởi nhiều replicas.
- [ ] Provider webhook được xác thực, xử lý idempotent.
- [ ] Các tỷ lệ có mẫu số và time window rõ.

### Dashboard và vận hành

- [ ] Overview, sender health, mail type và tenant drill-down đều có.
- [ ] Có job timeline tới attempt/event.
- [ ] Có SLO/alert ưu tiên cho OTP và transactional.
- [ ] Alert có volume guard và cảnh báo silent failure.
- [ ] Runbook auth, quota, throttle, backlog và failover được chuẩn bị.
- [ ] Panel thiếu dữ liệu hiển thị N/A thay vì 0% giả.

### Bảo mật và kiểm thử

- [ ] Metrics endpoint không public không kiểm soát.
- [ ] Không log OTP, raw body, secret hoặc PII không cần thiết.
- [ ] Backend kiểm tra quyền truy vấn tenant.
- [ ] Unit test metric names/tags và exception path.
- [ ] Integration test SMTP, outbox, webhook và cleanup.
- [ ] Retention metrics/events/logs phù hợp mục đích.

## 22. Những điều cần nhớ

- Dashboard Spring Framework Mail nên cho phép phân tích **sender**, **tenant** và **loại email** để khoanh vùng sự cố.
- Sender profile là danh tính cấu hình; đừng nhầm với From, SMTP host, credential hay DKIM domain.
- Mail type là một taxonomy nghiệp vụ hữu hạn, không lấy subject hoặc campaign ID động làm nhãn.
- Tenant ID quan trọng cho hỗ trợ nhưng có thể làm nổ metric cardinality: dùng metrics tổng hợp và DB/analytics drill-down có phân quyền.
- **Job, attempt, submission và delivery** có semantics khác nhau và cần đếm riêng.
- Micrometer Counter/Timer phù hợp cho attempt và latency; Gauge cho backlog; event store cho tenant/job details.
- PromQL phải hiểu reset, histogram, sample size và duplicate gauge ở nhiều replicas.
- Provider webhook có thể lặp, trễ và sai thứ tự; số event không tự bằng số message delivered duy nhất.
- OTP và newsletter có mức độ quan trọng khác nhau, nên SLO/cảnh báo không giống nhau.
- Dashboard phải gắn với runbook, kiểm thử và quyền truy cập, không chỉ là biểu đồ đẹp.

Một dashboard hiệu quả không chỉ trả lời “hôm nay gửi bao nhiêu email” mà còn trả lời được **sender nào đang lỗi, tenant nào bị tác động, loại email nào cần ưu tiên và bằng chứng xảy ra ở giai đoạn nào của quá trình gửi**. Khi kết hợp metrics có cardinality kiểm soát với dữ liệu job/event chi tiết, hệ thống Spring Framework Mail có thể được giám sát, cảnh báo và điều tra một cách chính xác hơn.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper` và transport errors.
- **Spring Boot Reference — Production-ready Features / Actuator:** Metrics và endpoint configuration.
- **Micrometer Documentation:** Counter, Timer, Gauge, tags/cardinality và histogram.
- **Prometheus Documentation:** Counter/Gauge, `rate`, `increase`, `histogram_quantile` và alerting rules.
- **Grafana Documentation:** dashboard variables, panel queries, permissions và alerting.
- **OpenTelemetry Documentation:** traces/metrics/log correlation.
- **Jakarta Mail SMTP provider documentation:** submission, exceptions và partial recipient send.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP transaction và acceptance.
- **Tài liệu email service provider đang sử dụng:** delivery/bounce/complaint events, rate limits và webhook contract.
