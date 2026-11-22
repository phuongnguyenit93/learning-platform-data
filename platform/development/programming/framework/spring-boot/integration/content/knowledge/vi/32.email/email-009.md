# Thử lại có kiểm soát, chống gửi trùng và theo dõi kết quả

## 1. Bài toán gửi email trong hệ thống tích hợp

Một dịch vụ Spring Boot nhận kết quả thanh toán, ghi đơn hàng vào PostgreSQL rồi gửi email biên nhận qua SMTP hoặc API của nhà cung cấp email. Yêu cầu nghiệp vụ thường là: không mất thông báo quan trọng, không gửi nhiều email cho cùng một hành động, không làm chậm request thanh toán và biết email đã được **chấp nhận**, **phát tới hộp thư** hay **bị trả lại**.

Gọi `JavaMailSender.send(...)` và thêm retry đơn giản vẫn có ba cửa sổ lỗi:

1. **DB commit xong, ứng dụng crash trước khi gửi:** đơn đã thanh toán nhưng không có email.
2. **Nhà cung cấp nhận email, ứng dụng timeout hoặc crash trước khi lưu kết quả:** retry có thể tạo email trùng.
3. **SMTP trả thành công, thư bị bounce hoặc vào spam:** log “send success” không chứng minh người nhận đã nhận hoặc đọc thư.

Trong module `SPRING_BOOT_INTEGRATION`, email là một adapter đầu ra có tác dụng phụ giống HTTP client hoặc broker. Phải thiết kế hợp đồng dữ liệu, giao dịch, idempotency, xử lý lỗi, kiểm thử và quan sát. Ví dụ dùng **Spring Boot 3.x, Java 17+, Spring Mail và PostgreSQL**; các nguyên tắc cũng áp dụng cho email qua HTTP API. SMTP không cung cấp exactly-once xuyên các hệ thống.

Mục tiêu bài học: phân loại lỗi để retry phù hợp; lưu ý định gửi bằng transactional outbox; chống yêu cầu gửi trùng; quản lý kết quả từ `PENDING` đến `ACCEPTED`/`DELIVERED`/`BOUNCED`; và kiểm thử các tình huống crash, timeout, nhiều worker.

## 2. Các mốc của một email và sự khác nhau giữa chúng

~~~mermaid
sequenceDiagram
    participant A as Business API
    participant D as PostgreSQL
    participant W as Email worker
    participant P as SMTP/Email provider
    participant R as Recipient mailbox
    A->>D: Commit nghiệp vụ + email outbox
    W->>D: Claim một email PENDING
    D-->>W: Lease + payload
    W->>P: SMTP DATA hoặc HTTP request
    P-->>W: SMTP 250 hoặc HTTP accepted
    W->>D: Ghi trạng thái ACCEPTED
    P->>R: Thử phát tới hộp thư
    P-->>W: Webhook delivered/bounced nếu hỗ trợ
    W->>D: Lưu sự kiện phát
~~~

| Mốc | Có thể khẳng định | Chưa thể khẳng định |
| --- | --- | --- |
| `PENDING` | Ý định gửi đã được lưu bền vững | Email được gửi ra mạng |
| `SENDING` | Worker đã claim và bắt đầu xử lý | Provider đã nhận |
| `ACCEPTED` | SMTP relay/provider phản hồi nhận xử lý request | Thư đến inbox người nhận |
| `DELIVERED` | Provider báo phát thành công theo định nghĩa của họ | Người nhận đã mở/đọc, không vào spam |
| `BOUNCED` | Provider/hệ thống đích báo không thể phát | Mọi loại bounce đều nên retry |
| `COMPLAINED` | Provider báo người nhận đánh dấu spam/khiếu nại | Được phép tiếp tục gửi loại thư đó |
| `UNKNOWN` | Không rõ provider đã chấp nhận request hay chưa | Có thể gửi lại mà không tạo bản trùng |

**SMTP phản hồi `250 OK` sau `DATA`** nghĩa là SMTP relay chấp nhận trách nhiệm xử lý thư. Sau đó relay vẫn có thể gặp bounce. Khi `JavaMailSender.send(...)` trả về mà không exception, điều đó chủ yếu chứng minh lệnh gửi hoàn tất theo phản hồi SMTP, **không phải delivery cuối cùng**.

Với HTTP API, `202 Accepted` cũng có thể chỉ nghĩa là provider đã đưa request vào hàng đợi. Một số provider cung cấp provider message ID, webhook và idempotency key riêng; cần xác minh hợp đồng và thời hạn của từng tính năng. SMTP chuẩn không tự loại bỏ bản gửi lặp dựa trên một idempotency key của ứng dụng.

### Ba loại ID cần tách biệt

| ID | Tạo ở đâu | Công dụng |
| --- | --- | --- |
| **Business intent key** | Ứng dụng | Xác định đúng một ý định gửi; dùng unique constraint chống enqueue trùng |
| **Outbox ID** | Ứng dụng/database | Định danh bản ghi, worker, trace và audit |
| **Provider message ID / RFC 5322 Message-ID** | Provider hoặc message | Đối chiếu với SMTP, webhook, lịch sử provider |

Header `Message-ID` giúp tương quan nhưng **không phải** cơ chế chống gửi trùng phổ quát. Gửi hai bản với cùng `Message-ID` vẫn có thể khiến người nhận thấy hai thư. Nếu provider hỗ trợ API idempotency, dùng cùng khóa ổn định khi retry trong thời hạn provider quy định; phải xác minh bảo đảm đó có bao gồm bước tiếp nhận hay chỉ request API.

## 3. Phân loại lỗi trước khi thử lại

Một exception từ `JavaMailSender` hoặc một HTTP timeout không đủ để kết luận nhà cung cấp chưa nhận email. Retry phải dựa trên **kết quả chấp nhận của provider** và mức độ chắc chắn của phản hồi.

| Loại kết quả | Ví dụ | Quyết định |
| --- | --- | --- |
| **Tạm thời, biết chắc chưa nhận** | SMTP trả mã tạm thời trước khi nhận nội dung thư; provider trả 429 và bảo đảm request bị từ chối | Đưa lại vào hàng đợi sau backoff/`Retry-After` |
| **Vĩnh viễn, biết chắc chưa nhận** | Recipient sai cú pháp, địa chỉ bị từ chối vĩnh viễn, sender domain chưa xác minh | Đánh dấu `FAILED_FINAL`, không retry tự động |
| **Không xác định được đã nhận chưa** | Timeout/mất kết nối sau khi gửi SMTP `DATA`; HTTP request timeout khi provider có thể đã tạo email | `UNKNOWN`, đối soát theo provider ID/log trước khi gửi lại |
| **Đã nhận nhưng phát không thành công** | Provider báo delayed/deferred/bounced sau `ACCEPTED` | Cập nhật sự kiện phát; chỉ retry theo loại bounce và chính sách |
| **Sự cố cấu hình hoặc quyền** | Sai credential SMTP, TLS certificate, domain bị khóa, quota tổ chức bị dừng | Cảnh báo, tạm dừng worker và khắc phục nguyên nhân |

SMTP thường dùng mã `4xx` cho lỗi tạm thời và `5xx` cho lỗi vĩnh viễn, nhưng phải xét phản hồi xuất hiện **ở bước giao thức nào**. Gửi cho nhiều recipient có thể chỉ thành công với một phần danh sách, do đó không được retry toàn bộ nếu một địa chỉ bị từ chối. Với thông báo cần theo dõi, nên tạo **một outbox record cho mỗi recipient và mỗi ý định gửi**.

### Backoff, jitter và thời hạn

Ví dụ một chính sách để hiệu chỉnh bằng SLA thực tế:

1. Cho tối đa **5 lượt gửi**, kể cả lượt đầu; dừng khi hết thời hạn nghiệp vụ.
2. Backoff mũ, với độ trễ nền 30 giây, nhân đôi theo số lần lỗi, trần 15 phút. Thêm jitter ngẫu nhiên để các instance không retry đồng loạt.
3. Nếu nhà cung cấp trả `Retry-After` hợp lệ, tuân thủ trong giới hạn chính sách; dùng rate limiter chung cho domain/provider khi bị throttling.
4. Không retry lỗi cấu hình, địa chỉ không hợp lệ hoặc bounce vĩnh viễn chỉ bằng cách tăng số lần thử.
5. Nếu kết quả **không rõ**, không chuyển về `PENDING` một cách mù quáng. Cần đối soát hoặc quyết định chấp nhận rủi ro gửi lại có ghi audit.

Công thức tham khảo: `delay = min(30s × 2^(attempt - 1), 15m) + jitter`; `attempt` là số lượt gửi đã thực hiện, bắt đầu từ 1. Bản triển khai cần chú ý tràn số khi tính lũy thừa và giới hạn tổng thời gian chờ. Retry giúp phục hồi lỗi tạm thời nhưng **không tạo ra exactly-once**.

## 4. Transactional outbox: lưu bền vững ý định gửi

### Vì sao gửi trong transaction database không đủ?

Đoạn sau rất dễ gây hiểu nhầm:

~~~java
@Transactional
public void completePayment(...) {
    paymentRepository.markPaid(...);
    mailSender.send(...); // I/O SMTP nằm ngoài JDBC transaction
}
~~~

Email có thể đã được provider chấp nhận rồi DB rollback, khiến người nhận thấy biên nhận cho đơn chưa thành công. Hoặc DB commit xong rồi process crash trước khi gửi. `@Transactional` cho PostgreSQL **không gộp được SMTP vào cùng transaction**.

Thiết kế thông dụng:

~~~text
HTTP/Kafka PaymentCompleted
          |
          v
Spring service @Transactional
  UPDATE payment/order
  INSERT email_outbox (PENDING)
          |
          v
   COMMIT database
          |
          v
Email worker claim -> SMTP/API -> lưu kết quả
          |
          v
Provider webhook/DSN -> cập nhật phát/bounce
~~~

Vì cập nhật nghiệp vụ và tạo outbox ở **cùng một database transaction**, rollback sẽ bỏ cả hai; commit thành công để lại bản ghi `PENDING` cho worker sau restart. Tuy nhiên worker vẫn có thể gửi lại email sau crash trước khi ghi kết quả; cần thêm cơ chế theo dõi `UNKNOWN` và idempotency.

### 4.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE email_outbox (
    id                  UUID PRIMARY KEY,
    intent_key          VARCHAR(240) NOT NULL UNIQUE,
    recipient_email     VARCHAR(320) NOT NULL,
    template_code       VARCHAR(100) NOT NULL,
    template_data       JSONB NOT NULL,
    status              VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempt_count       INT NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token         UUID,
    lease_until         TIMESTAMPTZ,
    provider_message_id TEXT,
    accepted_at         TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,
    last_error_kind     TEXT,
    last_error_summary  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (attempt_count >= 0),
    CHECK (status IN (
        'PENDING','SENDING','ACCEPTED','DELIVERED',
        'BOUNCED','COMPLAINED','FAILED_FINAL','UNKNOWN'
    ))
);

CREATE INDEX idx_email_outbox_due
    ON email_outbox (next_attempt_at, created_at)
    WHERE status = 'PENDING';

CREATE TABLE email_delivery_event (
    provider_event_id TEXT PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES email_outbox(id),
    event_type VARCHAR(40) NOT NULL,
    provider_occurred_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Các cột lưu trace/lease và sự kiện phát trong ví dụ là khung thiết kế; production cần migration, chính sách retention, phân quyền đọc và bảo vệ PII. Không lưu mã OTP, password reset token hoặc toàn bộ dữ liệu nhạy cảm dạng plaintext lâu hơn mức cần thiết. Có thể lưu một tham chiếu bản mẫu và dựng nội dung khi worker gửi, nhưng phải giữ hợp đồng dữ liệu ổn định để replay không tạo nội dung sai.

`intent_key` biểu diễn một **ý định gửi thông báo nghiệp vụ**. Ví dụ `invoice-issued:invoice-123:recipient-user-42` là một hóa đơn đã phát hành gửi đến đúng một người nhận. Cùng sự kiện đi từ Kafka hai lần vẫn sinh cùng khóa. Không dùng timestamp hoặc UUID ngẫu nhiên làm `intent_key` mỗi lần retry.

Nếu cần gửi một email **đính chính** hoặc gửi lại có chủ đích, tạo intent mới được nghiệp vụ ủy quyền, chẳng hạn `invoice-correction:invoice-123:revision-2:recipient-user-42`. Không tự tạo intent mới chỉ vì template code được nâng cấp sau deployment.

### 4.2. Ghi ý định gửi trong cùng transaction nghiệp vụ

Giả sử có bảng `invoice(id, status)` và lời gọi đã kiểm tra hóa đơn hợp lệ:

~~~java
// InvoiceNotificationService.java — Spring JDBC + PostgreSQL
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceNotificationService {
    private final JdbcTemplate jdbc;

    public InvoiceNotificationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void issueInvoice(UUID invoiceId, String recipientUserId, String to) {
        // Ứng dụng thật phải xác thực và kiểm tra trạng thái hóa đơn.
        int updated = jdbc.update("""
            UPDATE invoice SET status = 'ISSUED'
            WHERE id = ? AND status = 'DRAFT'
            """, invoiceId);
        if (updated == 0) {
            String current = jdbc.queryForObject(
                    "SELECT status FROM invoice WHERE id = ?",
                    String.class, invoiceId);
            if (!"ISSUED".equals(current)) {
                throw new IllegalStateException("Invoice is not issuable");
            }
        }

        String intentKey = "invoice-issued:" + invoiceId
                + ":recipient:" + recipientUserId;
        String payload = "{\"invoiceId\":\"" + invoiceId + "\"}";

        jdbc.update("""
            INSERT INTO email_outbox
              (id, intent_key, recipient_email, template_code, template_data)
            VALUES (?, ?, ?, ?, ?::jsonb)
            ON CONFLICT (intent_key) DO NOTHING
            """, UUID.randomUUID(), intentKey, to, "invoice-issued", payload);
    }
}
~~~

Code nhằm giải thích **ranh giới JDBC transaction**. Để sử dụng thực tế, phải kiểm tra giá trị trả về từ `UPDATE`: nếu hóa đơn không tồn tại, không được phát hành hoặc đã ở trạng thái khác, cần xử lý theo state machine và quy định có enqueue hay không. Không tự coi mọi trường hợp `UPDATE = 0` là phát hành thành công. Đồng thời cần giải quyết tranh chấp cập nhật, quyền người nhận và thay đổi email address.

`ON CONFLICT (intent_key) DO NOTHING` dựa vào unique constraint để hai request/consumer cùng thao tác vẫn tạo tối đa một outbox record. Cách “SELECT xem có chưa, rồi INSERT” tách rời có race condition. Đảm bảo `@Transactional` chạy qua Spring proxy và dùng cùng transaction manager cho invoice và outbox; không áp dụng được nếu mỗi bảng nằm ở database không có transaction chung.

## 5. Worker claim công việc và quản lý lượt gửi

Nếu mỗi instance đều chạy tác vụ tìm `PENDING` rồi gửi ngay, hai instance có thể cùng thấy một record và gửi trùng. Cần **claim nguyên tử** trong database, ghi trạng thái xử lý trước khi mở kết nối SMTP và ràng buộc kết quả của worker với lượt claim.

### 5.1. Claim bằng FOR UPDATE SKIP LOCKED

PostgreSQL cho phép chọn bản ghi đến hạn và giữ khóa trong một transaction ngắn:

~~~sql
WITH picked AS (
    SELECT id
    FROM email_outbox
    WHERE status = 'PENDING'
      AND next_attempt_at <= now()
    ORDER BY next_attempt_at, created_at
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE email_outbox e
SET status = 'SENDING',
    lease_token = :claim_token,
    lease_until = now() + interval '2 minutes',
    attempt_count = e.attempt_count + 1,
    updated_at = now()
FROM picked
WHERE e.id = picked.id
RETURNING e.id, e.intent_key, e.recipient_email,
          e.template_code, e.template_data, e.attempt_count,
          e.lease_token;
~~~

`:claim_token` là UUID mới do worker tạo, và transaction claim **commit trước** khi gửi email. `SKIP LOCKED` giúp các worker tranh chấp không lấy cùng row đang bị khóa. Không giữ transaction/row lock xuyên suốt lời gọi SMTP chậm. Với hệ nhiều instance, có thể kết hợp giới hạn batch size, thread pool và provider rate limit.

Ví dụ repository Spring JDBC thực hiện đúng nguyên tắc:

~~~java
// EmailClaimRepository.java — PostgreSQL, Spring JDBC
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class EmailClaimRepository {
    private final JdbcTemplate jdbc;

    public EmailClaimRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedEmail> claim(int maxBatchSize) {
        UUID token = UUID.randomUUID();
        return jdbc.query("""
            WITH picked AS (
                SELECT id FROM email_outbox
                WHERE status = 'PENDING' AND next_attempt_at <= now()
                ORDER BY next_attempt_at, created_at
                LIMIT ?
                FOR UPDATE SKIP LOCKED
            )
            UPDATE email_outbox e
            SET status = 'SENDING',
                lease_token = ?,
                lease_until = now() + interval '2 minutes',
                attempt_count = e.attempt_count + 1,
                updated_at = now()
            FROM picked
            WHERE e.id = picked.id
            RETURNING e.id, e.intent_key, e.recipient_email,
                e.template_code,
                e.template_data::text AS template_json,
                e.attempt_count, e.lease_token
            """, (rs, rowNum) -> new ClaimedEmail(
                    rs.getObject("id", UUID.class),
                    rs.getString("intent_key"),
                    rs.getString("recipient_email"),
                    rs.getString("template_code"),
                    rs.getString("template_json"),
                    rs.getInt("attempt_count"),
                    rs.getObject("lease_token", UUID.class)),
                maxBatchSize, token);
    }
}

record ClaimedEmail(
        UUID id, String intentKey, String recipientEmail,
        String templateCode, String templateJson,
        int attemptCount, UUID leaseToken) {}
~~~

Mẫu `record` chỉ mô tả payload cần cho worker; phần render template, kiểm tra quyền người nhận và quản lý kết quả được xây riêng. Trên Spring, phương thức `@Transactional` phải được gọi **từ bean khác qua proxy** để transaction được áp dụng. Nếu một worker gọi claim rồi chỉ gửi sau khi transaction commit, các worker khác không claim lại những row `SENDING`.

### 5.2. Ghi kết quả bằng claim token

Sau khi nhận phản hồi chấp nhận từ provider, cập nhật có điều kiện:

~~~sql
UPDATE email_outbox
SET status = 'ACCEPTED',
    accepted_at = now(),
    provider_message_id = :provider_message_id,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :outbox_id
  AND status = 'SENDING'
  AND lease_token = :claim_token;
~~~

Phải kiểm tra **số row cập nhật bằng 1**; nếu bằng 0, record có thể đã bị người khác chuyển trạng thái hoặc claim không còn hợp lệ. Không được im lặng kết luận đã lưu kết quả. Nếu dùng SMTP mà không có provider message ID, trường này có thể để `NULL`; lưu header correlation ID riêng để điều tra.

Với lỗi được xác nhận là tạm thời **và chắc chắn provider chưa nhận**, worker ghi `PENDING` với `next_attempt_at` mới và xóa lease, hoặc `FAILED_FINAL` khi hết số lần/thời hạn. Cần cập nhật cũng theo `id + lease_token + status` như trên để tránh một worker cũ ghi đè trạng thái mới. Ghi lỗi đã phân loại dưới dạng `last_error_kind` và bản tóm tắt an toàn, không lưu credential hay toàn bộ email body.

### 5.3. Lease hết hạn không có nghĩa gửi thất bại

Khi worker crash và lease hết hạn, có ít nhất hai khả năng: (a) worker chết trước lời gọi SMTP; (b) SMTP đã nhận thư nhưng worker chết trước khi ghi `ACCEPTED`. Nếu tự động đổi `SENDING` về `PENDING` rồi retry, khả năng (b) tạo **email trùng**.

Chính sách thận trọng hơn:

~~~sql
UPDATE email_outbox
SET status = 'UNKNOWN',
    lease_token = NULL,
    lease_until = NULL,
    last_error_kind = 'LEASE_EXPIRED',
    updated_at = now()
WHERE status = 'SENDING'
  AND lease_until < now();
~~~

`UNKNOWN` cần được **đối soát** qua provider API/log/event nếu có. Với API có idempotency key được bảo đảm, có thể retry cùng khóa theo chính sách provider. Với SMTP thuần, một số nghiệp vụ chọn gửi lại dù có nguy cơ trùng; nghiệp vụ khác chọn xử lý thủ công vì email không được phép gửi hai lần. Phải ghi rõ sự đánh đổi **có thể mất thông báo** và **có thể gửi trùng** trong SLA.

Một worker quá chậm có thể vẫn gửi xong sau khi lease chuyển sang `UNKNOWN`. Claim token ngăn worker đó âm thầm ghi đè trạng thái DB, nhưng **không thể thu hồi email đã gửi ra ngoài**. Timeout gửi, lease duration, heartbeat khi cần và số instance phải được thiết kế cùng nhau; monitoring phát hiện số row cập nhật kết quả bằng 0 là thiết yếu.

### 5.4. Thuật toán worker, tách rõ transaction

~~~text
Mỗi lần scheduler chạy (không chồng lượt với chính nó):
  claimed = claim(PENDING đến hạn, giới hạn batch) [transaction ngắn]

  for each mail in claimed:
    1. Render và validate email, từ dữ liệu nghiệp vụ đã lưu
    2. Gọi SMTP hoặc provider API (ngoài transaction DB)
    3. Nếu provider chấp nhận: mark ACCEPTED bằng claim token
    4. Nếu chắc chắn lỗi tạm thời trước acceptance:
       đặt PENDING với next_attempt_at theo backoff
    5. Nếu chắc chắn lỗi vĩnh viễn: mark FAILED_FINAL
    6. Nếu không rõ provider đã nhận chưa: mark UNKNOWN

Reconciler riêng:
  SENDING quá lease -> UNKNOWN
  UNKNOWN -> đối soát provider / quyết định xử lý theo SLA
~~~

Với Spring Scheduling, có thể dùng `@EnableScheduling` cùng `@Scheduled(fixedDelay = 2000)` để gọi worker; nếu scale nhiều instance, claim ở database vẫn cần thiết. Việc chạy mỗi 2 giây chỉ là ví dụ, phải tính theo throughput, giới hạn SMTP, độ ưu tiên thông báo và quy mô backlog. Không đặt toàn bộ email vào một `@Async void` mất dấu vết trạng thái.

## 6. Kết nối SMTP bằng Spring Mail với timeout và TLS

### 6.1. Cấu hình cơ bản

~~~kotlin
// build.gradle.kts — Spring Boot 3.x
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-mail")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

~~~yaml
# application.yml — SMTP submission với STARTTLS trên port 587
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

Các giá trị `${SMTP_HOST}`, `${SMTP_USERNAME}` và `${SMTP_PASSWORD}` là placeholder lấy từ biến môi trường/secret tương ứng. Thời gian timeout của Jakarta Mail tính bằng **mili giây**. Với **implicit TLS trên port 465**, cần cấu hình `mail.smtp.ssl.enable=true` và điều chỉnh STARTTLS cho đúng endpoint; không trộn hai chế độ một cách máy móc.

`mail.smtp.starttls.required=true` tránh gửi dữ liệu trên kết nối không được nâng cấp TLS khi môi trường yêu cầu STARTTLS. `mail.smtp.ssl.checkserveridentity=true` yêu cầu kiểm tra tên máy chủ với certificate. Client phải tin cậy CA đúng và không dùng cơ chế “trust all certificates” để che lỗi cấu hình. Nếu provider dùng OAuth2, API key hoặc SMTP relay đặc thù, phương pháp xác thực và rotation sẽ khác; chỉ cấp credential qua secret manager và giới hạn quyền gửi.

### 6.2. Ví dụ adapter gửi một recipient

~~~java
// SmtpEmailSender.java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SmtpEmailSender {
    private final JavaMailSender mailSender;

    public SmtpEmailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(ClaimedEmail mail) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());
        helper.setFrom("notifications@example.test");
        helper.setTo(mail.recipientEmail());
        helper.setSubject("Hóa đơn của bạn đã được phát hành");
        helper.setText("Vui lòng đăng nhập để xem hóa đơn.", false);
        message.setHeader("X-Notification-Id", mail.id().toString());
        mailSender.send(message);
    }
}
~~~

Ví dụ tập trung vào ranh giới SMTP: một recipient, địa chỉ gửi được cấu hình/kiểm chứng, một header correlation ID không chứa thông tin nhạy cảm. Trong ứng dụng thực, `templateCode`/`templateJson` được dùng để render mẫu đã kiểm soát, escape dữ liệu người dùng khi tạo HTML, kiểm tra nội dung và không gửi token bí mật qua log. Email có nhiều loại nên tách phần render khỏi adapter gửi.

`mailSender.send(message)` có thể ném `MailException` (với nguyên nhân SMTP/Jakarta Mail nằm sâu bên trong). Phải phân loại phản hồi thực tế, kể cả trường hợp thư được nhận một phần, trước khi retry. Hàm `send` không trả delivery status; worker chỉ được mark `ACCEPTED` sau khi có xác nhận gửi phù hợp, và kết quả cuối cần theo dõi qua provider nếu có.

## 7. Theo dõi delivery, bounce, complaint và trạng thái không rõ

### 7.1. Nguồn sự kiện cuối cùng đến từ đâu?

| Cách gửi | Thông tin thường lấy được | Hạn chế |
| --- | --- | --- |
| **SMTP thông thường** | Kết quả server chấp nhận hoặc từ chối lời gọi gửi, lỗi SMTP | Không mặc nhiên biết email đã được phát tới mailbox; có thể cần DSN/log của hệ thống mail |
| **Email service qua API** | Request ID/provider message ID, API status | HTTP success có thể chỉ là `ACCEPTED` |
| **Webhook của provider** | `delivered`, `deferred`, `bounced`, `complained`, `unsubscribed`... tùy hợp đồng | Có thể trễ, mất thứ tự, được phát lại; phải xác thực nguồn |
| **Email open/click tracking** | Sự kiện pixel/link theo cơ chế của provider | Không xác minh chắc người đọc, vì proxy, chặn tracking và các yếu tố riêng tư |

**Không biến `ACCEPTED` thành `DELIVERED`** chỉ vì không thấy lỗi sau vài giây. Nếu provider không hỗ trợ delivery feedback, để trạng thái ở `ACCEPTED` với giới hạn quan sát được ghi rõ trong báo cáo. Với SMTP hỗ trợ Delivery Status Notification (DSN), việc yêu cầu DSN cũng **không bảo đảm** mọi hệ thống đích sẽ gửi thông báo đầy đủ hoặc đúng thời hạn.

### 7.2. Nhận webhook một cách idempotent

Để nhận sự kiện `delivered`/`bounced` từ provider:

1. Xác minh chữ ký/HMAC hoặc cơ chế authentication do nhà cung cấp quy định; kiểm tra timestamp và giới hạn replay khi có.
2. Xác định đúng outbox record từ **provider message ID + recipient/metadata tương quan** theo hợp đồng provider. Một ID có thể đại diện nhiều recipient tùy API; không tìm theo ID đơn lẻ khi mô hình cho phép nhiều người nhận.
3. Chuyển sự kiện vào transaction database: `INSERT email_delivery_event` với `provider_event_id` unique; nếu đã tồn tại thì coi là redelivery và phản hồi thành công.
4. Cập nhật trạng thái outbox theo **state machine** và thời gian sự kiện có ý nghĩa, không ghi đè mù quáng theo thứ tự HTTP request đến.
5. Chỉ phản hồi HTTP `2xx` sau khi xử lý bền vững; nếu database tạm thời lỗi, để provider retry theo hợp đồng. Tính idempotent là bắt buộc vì webhook cũng có thể giao ít nhất một lần.

Ví dụ câu SQL chống lặp sự kiện:

~~~sql
INSERT INTO email_delivery_event (
    provider_event_id, outbox_id, event_type, provider_occurred_at
)
VALUES (
    :event_id, :outbox_id, :event_type, :provider_occurred_at
)
ON CONFLICT (provider_event_id) DO NOTHING;
~~~

Nếu không INSERT được vì unique key đã tồn tại, không xử lý side effect của sự kiện đó lần thứ hai. Nếu vừa INSERT sự kiện vừa cập nhật `email_outbox`, nên đặt cả hai trong một transaction để tránh event log và trạng thái tổng hợp mâu thuẫn.

### 7.3. Mô hình chuyển trạng thái không đơn giản là thứ tự đến

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> SENDING: claim
    SENDING --> PENDING: lỗi tạm thời, chắc chắn chưa nhận
    SENDING --> FAILED_FINAL: lỗi vĩnh viễn / hết lượt
    SENDING --> UNKNOWN: timeout hoặc crash mơ hồ
    SENDING --> ACCEPTED: SMTP/API xác nhận tiếp nhận
    ACCEPTED --> DELIVERED: provider delivery event
    ACCEPTED --> BOUNCED: bounce event
    ACCEPTED --> COMPLAINED: complaint event
    DELIVERED --> COMPLAINED: complaint về sau
    UNKNOWN --> ACCEPTED: đối soát tìm thấy email
    UNKNOWN --> FAILED_FINAL: quyết định nghiệp vụ có audit
~~~

Sơ đồ là luồng phổ biến, không bao trùm mọi hành vi provider. Ví dụ một provider có thể báo `deferred` trước `delivered` hoặc báo bounce trễ sau một sự kiện khác. **Lưu nhật ký sự kiện bất biến** rồi tính trạng thái tổng hợp theo luật rõ ràng; không lấy “webhook mới đến sau” làm chân lý duy nhất. `COMPLAINED` và hard bounce thường dẫn tới **suppression**: không tiếp tục gửi tới địa chỉ hoặc loại thông báo tương ứng cho đến khi chính sách cho phép.

Phải phân biệt **hard bounce** (thường không nên tự động gửi lại) và **soft bounce/deferred** (có thể do mailbox đầy hoặc server đích tạm thời lỗi). Nếu provider tự retry việc phát, ứng dụng không nên tạo **một email API request mới** chỉ vì nhận event deferred. Chỉ kích hoạt retry bên ứng dụng sau khi hiểu đúng kết quả cuối và chính sách retry của provider.

### 7.4. Đối soát email `UNKNOWN`

Với provider có API truy vấn, tìm email qua provider message ID, idempotency key hoặc custom metadata đã đăng ký. Nếu tìm được một yêu cầu được chấp nhận, ghi `ACCEPTED` cùng thông tin đối soát. Nếu provider xác nhận **chắc chắn không có** request và còn trong thời hạn gửi, có thể khởi tạo lượt retry mới. Nếu không thể xác minh, cần quyết định có đánh đổi nguy cơ trùng lấy khả năng không bỏ sót thông báo.

Với SMTP thuần, thường không có API truy vấn chuẩn để biết liệu email đã được nhận ở vùng timeout. Cần phân loại `UNKNOWN`, xem mail server log khi có quyền, theo dõi cảnh báo và có quy trình xử lý thủ công hoặc retry được nghiệp vụ cho phép. Việc tự động đổi tất cả `UNKNOWN` thành `PENDING` sẽ làm mất ý nghĩa của trạng thái này.

## 8. Liên kết với HTTP, database, Kafka và broker

### Request HTTP

API phát hành hóa đơn có thể trả `202 Accepted` hoặc `200 OK` sau khi transaction nghiệp vụ và bản ghi outbox đã commit. Phản hồi phải nói rõ **“đã ghi nhận yêu cầu thông báo”** thay vì cam kết email đã đến inbox. Có thể trả về `notificationId`/`outboxId` cho endpoint đọc trạng thái (chỉ cho người dùng được phép).

Nếu client retry request HTTP do timeout, một **idempotency key ở tầng API** hoặc khóa nghiệp vụ ổn định sẽ giúp tránh phát hành lại hóa đơn và enqueue nhiều email. Idempotency key này có thể khác outbox key, nhưng phải có quy tắc ánh xạ rõ và duy trì cùng hành vi khi request được gửi lại.

### Kafka/RabbitMQ inbound event

Khi consumer nhận `InvoiceIssued`, hãy ghi inbox/projection cùng email outbox trong một DB transaction. Chỉ ack/commit offset của broker **sau khi DB commit**; nếu crash giữa commit DB và broker ack, message có thể được giao lại nhưng unique `intent_key` sẽ ngăn tạo thêm outbox. Ghi outbox không có nghĩa email đã gửi, nên đừng ack broker dựa trên SMTP send thành công trong request thread.

Với kiến trúc có hai database, một transaction DB thông thường không bao trùm cả hai. Cần xác định nguồn dữ liệu chân lý và dùng inbox/outbox hoặc cơ chế giao dịch tương thích với yêu cầu, thay vì đặt `@Transactional` lên phương thức rồi cho rằng mọi adapter tham gia cùng commit.

### Cache và các tác dụng phụ khác

Nếu hệ thống gửi email có link/token được cache trong Redis, phải kiểm soát TTL và thời điểm commit/expire. Không tạo email với đường dẫn chứa token chưa được persist hoặc đã hết hạn. Các callback webhook có thể kích hoạt cập nhật notification dashboard, audit hoặc suppression list; những tác dụng phụ này cũng cần idempotency theo `provider_event_id`.

### Ranh giới nghiệp vụ của “không gửi trùng”

Unique `intent_key` bảo đảm **tối đa một bản ghi outbox cho một ý định**, nhưng không bảo đảm chỉ một email được provider chấp nhận. Nếu nghiệp vụ yêu cầu một email duy nhất tuyệt đối, SMTP cùng database không có một commit chung để bảo đảm điều đó; phải chấp nhận đánh đổi hoặc chọn provider có giao thức idempotency đáng tin cậy trong phạm vi đã công bố.

Ví dụ, email biên nhận thường ưu tiên **không bỏ sót** và có thể chịu một bản trùng hiếm. Mã OTP hoặc reset password có thể ưu tiên một quy tắc khác: hủy hiệu lực token cũ, gửi intent mới với thời hạn rõ ràng, không replay token đã hết hạn. Quy tắc nghiệp vụ quyết định trạng thái nào được phép retry.

## 9. Quan sát, cảnh báo, bảo mật và vận hành

### Metric và log có giá trị

| Tín hiệu | Tại sao cần |
| --- | --- |
| `email_outbox_pending_total`, `email_outbox_oldest_pending_age` | Biết backlog và thời gian chờ của thông báo |
| `email_send_attempts_total{result,provider}` | Tách attempt thành công, từ chối chắc chắn, không rõ |
| `email_send_duration_seconds` | Phát hiện provider chậm, cần điều chỉnh timeout/pool |
| `email_retry_scheduled_total{reason}` | Biết retry có hiệu quả hay đang lặp |
| `email_unknown_total` và `email_unknown_oldest_age` | Ưu tiên đối soát các lượt gửi mơ hồ |
| `email_delivery_events_total{type}` | Theo dõi delivered, bounce, complaint, deferred |
| `email_intent_duplicate_suppressed_total` | Đo việc unique key chặn yêu cầu enqueue trùng |

Nên có dashboard theo provider, template, môi trường, domain nhận (nếu việc phân nhóm này tuân thủ chính sách dữ liệu), và cảnh báo khi email quan trọng vượt SLA chờ/phát, `UNKNOWN` tăng hoặc provider báo rate limit liên tục.

Log tối thiểu gồm `outboxId`, `intentKey` dạng đã làm sạch, `attemptCount`, `providerMessageId` khi có, thời điểm claim/send/accept, mã lỗi có thể phân loại và trace/correlation ID. **Không log SMTP password, API token, toàn bộ email body, header nhạy cảm hoặc địa chỉ email đầy đủ nếu không cần thiết**. Giới hạn quyền truy cập bảng outbox và event log, mã hóa dữ liệu cần bảo vệ, retention phù hợp yêu cầu pháp lý/nội bộ.

### Giữ uy tín domain và tuân thủ gửi email

Hệ thống cần SPF, DKIM và DMARC phù hợp với domain gửi, xác minh sender identity tại provider và xử lý bounce/complaint. Thông báo marketing cần thực hiện preference/opt-out theo chính sách và quy định áp dụng; email giao dịch vẫn phải đúng mục đích và tránh gửi lại do lỗi kỹ thuật. Đảm bảo danh sách suppression được kiểm tra trước khi tạo/gửi intent khi nghiệp vụ yêu cầu.

### Vận hành khi provider gặp sự cố

Nếu provider trả throttling liên tục, không mở số worker vô hạn. Dùng giới hạn concurrency, bulkhead cho SMTP pool, circuit breaker hoặc pause khi cần, retry theo backoff, cảnh báo và kế hoạch thay đổi provider có kiểm soát. Khi chuyển provider, giữ nguyên `intent_key` và outbox ID; phải giải quyết các bản `UNKNOWN` trước vì provider cũ có thể đã chấp nhận thư.

Khi nâng cấp Spring Boot, Jakarta Mail, driver SMTP hoặc provider SDK, kiểm tra lại timeout, TLS/STARTTLS, exception classification, handling partial recipient, header correlation, webhook schema và giới hạn idempotency. Một dependency upgrade không nên vô tình biến tất cả exception thành retryable.

## 10. Kiểm thử tích hợp và lỗi cưỡng bức

Với email, unit test chỉ xác nhận `send(...)` được gọi một lần là chưa đủ. Cần thử nghiệm trên PostgreSQL thật hoặc Testcontainers, SMTP server thử nghiệm (ví dụ GreenMail) hoặc fake provider HTTP có khả năng điều khiển phản hồi và thời điểm đứt kết nối.

| Kịch bản | Cách dựng lỗi | Kết quả cần xác nhận |
| --- | --- | --- |
| Nghiệp vụ rollback | Transaction invoice ném exception trước commit | Không có outbox được commit |
| Crash sau commit nghiệp vụ | Dừng process sau INSERT outbox, trước worker | Record `PENDING` còn và gửi được sau restart |
| Hai request trùng nghiệp vụ | Chạy đồng thời hai lần với cùng `intent_key` | Chỉ một outbox record; không tạo hai intent |
| Hai worker claim cạnh tranh | Hai instance đồng thời chạy claim | Mỗi `PENDING` chỉ được claim bởi một worker tại thời điểm đó |
| Provider trả lỗi tạm thời rõ ràng | Fake SMTP/API trả phản hồi biết chắc chưa accept | Backoff đúng, giữ intent và attempt count, không retry tức thì |
| Provider trả lỗi vĩnh viễn | Recipient không hợp lệ hoặc quyền gửi bị từ chối | `FAILED_FINAL` hoặc pause vận hành, không loop vô hạn |
| Đứt kết nối sau khi provider nhận | Fake provider lưu request rồi đóng socket trước response | `UNKNOWN`, không tự động retry không kiểm tra |
| DB lỗi khi ghi `ACCEPTED` | Provider đã nhận, UPDATE DB thất bại | Có cảnh báo, lease hết hạn thành `UNKNOWN` để đối soát |
| Worker xử lý lâu quá lease | Worker A chậm; reconciler đánh dấu `UNKNOWN` | Không tự tạo lượt gửi B; kết quả A ghi muộn không ghi đè vô điều kiện |
| Webhook trùng | Gửi cùng `provider_event_id` hai lần | Chỉ một event record và một hiệu ứng trạng thái |
| Webhook sai thứ tự | Nhận `delivered` rồi sự kiện `deferred` cũ hơn | Không ghi đè trạng thái hợp lệ bằng sự kiện cũ một cách mù quáng |
| Webhook giả mạo | Thiếu/sai chữ ký, timestamp quá hạn | Bị từ chối, không sửa dữ liệu |
| Bounce/complaint | Provider phát event cuối phù hợp | Tình trạng được ghi nhận; suppression theo chính sách |
| Hệ thống quá tải | Provider trả 429 liên tục hoặc SMTP chậm | Concurrency/rate limit được kiểm soát; backlog và tuổi queue được cảnh báo |
| Chuyển provider sau incident | Một số record `UNKNOWN` ở provider cũ | Đối soát hoặc quyết định nghiệp vụ trước khi gửi qua provider mới |

Đặc biệt, không thể mô phỏng vùng lỗi “provider đã nhận thư nhưng response bị mất” chỉ bằng mock luôn ném exception **trước** lời gọi gửi. Cần một fake server chủ động nhận request rồi làm mất response, hoặc kiểm thử qua môi trường provider phù hợp. Kết quả pass phải kiểm tra **bản ghi outbox, nhật ký sự kiện, số yêu cầu thực tế provider đã nhận và thời điểm retry**, không chỉ log Java.

Trong production, không thử gửi thư thật đến khách hàng hoặc cố tình ngắt dịch vụ chung để diễn tập. Dùng địa chỉ sandbox/test, dữ liệu giả và environment được kiểm soát. Nếu cần replay sau sự cố, xác định trước số lượng `UNKNOWN`, mức rủi ro gửi trùng và người phê duyệt thay đổi trạng thái.

## 11. Tình huống phân tích và câu hỏi tự kiểm tra

### Tình huống A: retry sau timeout làm khách hàng nhận hai email

Worker lấy hóa đơn `INV-814`, gửi qua SMTP. Server đã phản hồi chấp nhận nhưng kết nối bị đứt trước khi client nhận phản hồi. Worker coi tất cả `MailException` là lỗi tạm thời và gửi lại ngay. Khách hàng nhận hai bản.

Gốc lỗi là **kết quả lần gửi đầu không xác định**, không chứng minh server chưa nhận. Sửa bằng trạng thái `UNKNOWN`, đối soát khi có khả năng, timeout hợp lý, idempotency key nếu API provider hỗ trợ và quy tắc quyết định gửi lại theo độ quan trọng của thông báo.

### Tình huống B: không gửi trùng nhưng lại mất email

Ứng dụng ghi dấu `sent = true` trước khi gọi SMTP nhằm chống gửi trùng. Process crash ngay sau dấu này, trước khi tạo kết nối. Scheduler bỏ qua vì thấy `sent = true`. Đơn đã hoàn tất nhưng khách hàng không có thư.

Không được đánh đồng **đã đặt lịch** với **đã được chấp nhận**. Dùng outbox `PENDING`, claim `SENDING`, hoàn thành `ACCEPTED` sau phản hồi và phân loại `UNKNOWN` khi claim bị bỏ dở. Đưa business change và enqueue vào một DB transaction.

### Tình huống C: cùng email được enqueue hai lần bởi hai consumer

Kafka redelivery đưa `InvoiceIssued(invoiceId=INV-814)` tới hai lần. Hai consumer đều `SELECT` không thấy outbox rồi `INSERT`. Nếu không có unique constraint, có thể tạo hai bản. Sửa bằng một `intent_key` ổn định cho `invoiceId + recipient`, unique index và `INSERT ... ON CONFLICT DO NOTHING`; DB transaction bảo đảm chỉ có một intent.

### Câu hỏi tự kiểm tra

1. **SMTP `250 OK` có nghĩa thư đã nằm trong inbox người nhận?** Không. Relay mới chấp nhận xử lý; kết quả phát cuối tùy provider/mailbox.
2. **Dùng `@Retryable` quanh `mailSender.send` có đảm bảo không gửi trùng?** Không. Timeout sau acceptance có thể tạo thêm email, ngay cả khi retry đúng số lần.
3. **Unique `intent_key` giải quyết được gì?** Chặn tạo nhiều bản ghi outbox cho cùng một ý định nghiệp vụ; chưa loại trừ hai lần SMTP send khi phản hồi mơ hồ.
4. **Vì sao dùng `FOR UPDATE SKIP LOCKED`?** Để nhiều worker tranh chấp claim mà không cùng lấy một record đang bị khóa.
5. **Vì sao lease hết hạn không được tự động retry ngay?** Worker có thể đã gửi thành công nhưng chưa kịp lưu `ACCEPTED`; retry làm tăng nguy cơ trùng.
6. **Webhook delivered nhận lại hai lần thì xử lý thế nào?** Xác thực nguồn, dùng `provider_event_id` unique và cập nhật trạng thái idempotent trong transaction.
7. **Nếu provider không có delivery webhook thì báo trạng thái gì?** Có thể báo `ACCEPTED` theo phản hồi SMTP/API; không tuyên bố `DELIVERED` khi không có bằng chứng.
8. **Khi database commit xong nhưng email chưa được gửi, điều gì giúp phục hồi?** Outbox `PENDING` đã commit cùng nghiệp vụ và worker có thể lấy lại sau restart.
9. **Tại sao không nên gửi thông báo tài chính cho nhiều người nhận trong một lệnh SMTP duy nhất?** Phản hồi có thể chỉ chấp nhận một phần; theo dõi và retry từng recipient khó chính xác.
10. **Tại sao retry phải xét thời hạn nghiệp vụ?** Một email token hoặc đường dẫn đã hết hạn có thể vô dụng, gây nhiễu hoặc tạo rủi ro nếu được gửi quá muộn.

Để gửi email đáng tin cậy trong Spring Boot Integration, cần bảo vệ **ý định gửi** bằng transaction và unique key, bảo vệ **quá trình thực thi** bằng claim/backoff/timeout có kiểm soát, và bảo vệ **diễn giải kết quả** bằng các trạng thái phân biệt `ACCEPTED`, `DELIVERED`, `BOUNCED` và `UNKNOWN`. Chính sự phân biệt này giúp phát hiện ranh giới lỗi và đưa ra quyết định retry có bằng chứng thay vì dựa vào giả định “không có phản hồi tức là chưa gửi”.
