# Gửi email qua hàng đợi với theo dõi kết quả và chống gửi trùng

## 1. Bài toán thực hành và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter Spring Integration. Trọng tâm của module là quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát các luồng tích hợp thực tế. Bài thực hành thuộc chương **Thực hành tổng hợp**, với đề bài **gửi email qua hàng đợi, theo dõi kết quả và chống gửi trùng**.

Tình huống: sau khi đơn hàng được xác nhận, hệ thống phải gửi email thông báo. API phải trả nhanh, còn SMTP/provider đôi khi chậm, quá tải hoặc không khả dụng. Client có thể gửi lại request sau timeout; RabbitMQ có thể giao lại message khi worker crash; hai worker có thể nhận hai bản sao công việc. Đồng thời vận hành cần biết yêu cầu nào đã được tiếp nhận, đang thử gửi, được SMTP chấp nhận, thất bại hay cần đối soát.

**Mục tiêu:** xây dựng flow tham chiếu bằng **Spring Boot + PostgreSQL/JDBC + RabbitMQ/Spring AMQP + JavaMailSender**, với các năng lực:

1. Nhận yêu cầu theo **idempotency key** ổn định, trả cùng delivery ID cho request lặp.
2. Dùng **transactional outbox** để tránh khoảng trống giữa commit database và publish broker.
3. Worker nhận công việc, **atomic claim** trong database, chỉ một attempt có quyền gửi tại một thời điểm.
4. Gửi qua SMTP có timeout, phân loại lỗi, ghi trạng thái, retries và lịch sử.
5. Tra cứu kết quả qua REST API và quan sát bằng metric/log/trace.
6. Xử lý message lặp, crash sau SMTP send, mất broker ACK, lỗi dữ liệu và DLQ.
7. Có bộ kiểm thử chứng minh transaction, idempotency và trạng thái sau lỗi.

**Giới hạn bảo đảm:** Không thể cam kết **exactly-once email delivery** chỉ bằng SMTP. Provider có thể đã nhận lệnh nhưng client timeout trước khi thấy phản hồi. Vì vậy, chống yêu cầu trùng và chống worker gửi cùng lúc **khác** với chứng minh người nhận chỉ nhận đúng một thư. Bài học đưa ra chính sách bảo thủ: khi kết quả gửi không chắc chắn, ghi **UNKNOWN** và đối soát trước khi tự động gửi lại.

## 2. Hiểu đúng “gửi thành công” và state machine

| Mốc | Trạng thái/tín hiệu | Điều đã được chứng minh | Chưa được chứng minh |
| --- | --- | --- | --- |
| API commit database | **PENDING** | Delivery và outbox đã được lưu bền vững | RabbitMQ/SMTP đã nhận |
| Relay nhận publisher confirm | Outbox **published_at** | Broker xác nhận publish; đã kiểm tra unroutable return | Worker đã xử lý |
| Worker nhận quyền gửi | **SENDING** | Claim DB thành công | Provider đã chấp nhận |
| JavaMailSender trả thành công | **ACCEPTED_BY_SMTP** | SMTP/provider đã chấp nhận lệnh theo hợp đồng | Inbox đã nhận, không bounce |
| Có feedback provider xác thực | **DELIVERED/BOUNCED** nếu hỗ trợ | Feedback đến từ provider theo ngữ nghĩa sự kiện | Người dùng đã đọc |
| Provider từ chối tạm thời, biết chắc chưa nhận | **RETRY_WAIT** | Có thể lên lịch thử lại theo policy | Không phải mọi SMTP exception đều an toàn để retry |
| Sai recipient/policy không thể gửi | **FAILED_PERMANENT** | Không tiếp tục tự động ở trạng thái này | Không thể sửa dữ liệu rồi thực hiện lại |
| Timeout/crash mà kết quả SMTP chưa rõ | **UNKNOWN** | Không đủ bằng chứng về kết quả gửi | Gửi lại chắc chắn không trùng |

**ACCEPTED_BY_SMTP không có nghĩa DELIVERED.** Một thư có thể bị bounce, chặn bởi spam filter hoặc gặp vấn đề ở mail server phía sau. Muốn biết giao thành công, phải có webhook hoặc hệ thống xử lý bounce đáng tin; một SMTP response thông thường không cung cấp điều đó.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: HTTP transaction tạo delivery + outbox
    PENDING --> SENDING: Worker atomic claim
    SENDING --> ACCEPTED_BY_SMTP: SMTP chấp nhận và DB commit
    SENDING --> RETRY_WAIT: Từ chối tạm thời xác định
    RETRY_WAIT --> PENDING: Scheduler tạo outbox dispatch mới
    SENDING --> FAILED_PERMANENT: Lỗi dữ liệu hoặc từ chối vĩnh viễn
    SENDING --> UNKNOWN: Kết quả không chắc / lease hết
    ACCEPTED_BY_SMTP --> DELIVERED: Provider feedback xác thực
    ACCEPTED_BY_SMTP --> BOUNCED: Provider bounce xác thực
    UNKNOWN --> ACCEPTED_BY_SMTP: Đối soát thấy đã chấp nhận
    UNKNOWN --> RETRY_WAIT: Operator cho phép retry có ghi nhận rủi ro
    UNKNOWN --> FAILED_PERMANENT: Quyết định dừng sau điều tra
~~~

Không tự động đưa **UNKNOWN** về PENDING chỉ vì lease hết hạn: worker có thể đã gửi thư nhưng chưa ghi được trạng thái. Một chính sách ưu tiên *không gửi trùng* sẽ đối soát hoặc cần operator quyết định trước khi thử lại. Chính sách ưu tiên *giao thư bằng mọi giá* có thể chấp nhận nguy cơ duplicate, nhưng phải ghi rõ trong hợp đồng.

## 3. Kiến trúc: HTTP → DB outbox → RabbitMQ → SMTP

~~~mermaid
flowchart TD
    A["Order service / HTTP caller"] -->|"POST + Idempotency-Key"| B["Email Request API"]
    B --> C["PostgreSQL transaction"]
    C --> D["email_delivery PENDING"]
    C --> E["email_outbox EmailSendRequested"]
    B -->|"202 + deliveryId"| F["GET status API"]
    D --> F
    E --> G["Outbox relay"]
    G -->|"Publisher confirm + routing"| H["RabbitMQ durable queue"]
    H --> I["Mail worker"]
    I -->|"Atomic claim / attempt token"| D
    I --> J["Template renderer"]
    J --> K["JavaMailSender / SMTP"]
    K -->|"Success/failure/unknown"| D
    I -->|"ACK sau durable outcome"| H
    D --> L["Retry scheduler / reconciler"]
    L -->|"Due RETRY_WAIT"| E
    L -->|"Expired SENDING → UNKNOWN"| D
    H -->|"Malformed message"| M["Dead-letter/quarantine"]
~~~

**Database giữ trạng thái nguồn sự thật**; RabbitMQ vận chuyển công việc, không quản lý tính duy nhất của email. HTTP không chờ SMTP, chỉ phản hồi sau DB commit. Relay có thể publish lặp nếu broker nhận nhưng database chưa đánh dấu published; đó là lý do worker luôn kiểm tra trạng thái và claim thay vì tin mọi message đều mới.

Một work message tối thiểu:

~~~json
{
  "eventId": "8fd73fc8-c870-4ef9-aa22-2b85c3190b36",
  "deliveryId": "73de4c12-7a47-4566-b810-d92b18cab27f",
  "schemaVersion": 1
}
~~~

Worker lấy recipient, template, variables từ DB; không cần đưa toàn bộ HTML, địa chỉ email hoặc dữ liệu cá nhân vào queue. **eventId** định danh một lần dispatch qua broker, còn **deliveryId** định danh một yêu cầu gửi nghiệp vụ. Cả hai không tự đảm bảo SMTP idempotency.

## 4. Dependencies và cấu hình kết nối

Ví dụ Maven với Spring Boot parent/BOM quản lý phiên bản, Java 17+:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đoạn code dùng API kiểu Spring Boot 3.x (`jakarta.mail`, `jakarta.validation`, `@RabbitListener`); với Spring Boot 4.x phải kiểm tra lại starter/module và package theo phiên bản đang dùng. Cần migration tool như Flyway/Liquibase nếu dự án đã chuẩn hóa schema migration.

### 4.1. application.yml không chứa secret thật

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
  rabbitmq:
    addresses: ${RABBITMQ_ADDRESSES}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        prefetch: 5
        concurrency: 2
        max-concurrency: 6
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  email:
    from-address: ${EMAIL_FROM_ADDRESS}
    work-queue: email.send.work
    work-exchange: email.work.exchange
    work-routing-key: email.send
    max-attempts: 5
    sending-lease: 2m
~~~

SMTP timeout do JavaMail/Jakarta Mail quy định theo **millisecond**. Nếu không đặt, một số timeout có thể vô hạn và giữ worker lâu. Cấu hình STARTTLS, TLS certificate/hostname, port 465/587, sender domain, quyền và provider rate limits phải được kiểm chứng; không tắt TLS verification để “chạy thử” trên production. URL và credential lấy từ runtime/secret manager, không commit vào source hoặc in log.

### 4.2. RabbitMQ topology

~~~text
Direct exchange: email.work.exchange (durable)
    routing key: email.send
        → durable queue: email.send.work
             → workers

Dead-letter exchange: email.work.dlx
    → durable quarantine queue: email.send.dlq
~~~

Broker phải có exchange, binding, durable queue và policy DLX tương ứng. Publisher gửi **persistent message**, dùng **publisher confirms + returns/mandatory** để phân biệt broker đã xác nhận publish với unroutable. Confirm `ack=true` một mình không đủ để biết routing key đã đưa message vào queue nếu không kiểm tra return. DLQ dành cho message lỗi không xử lý được; **lỗi SMTP của một delivery hợp lệ chủ yếu theo dõi ở DB**, không thể chỉ nhìn DLQ.

## 5. Thiết kế schema PostgreSQL

~~~sql
CREATE TABLE email_delivery (
    id                   UUID PRIMARY KEY,
    tenant_id            VARCHAR(80) NOT NULL,
    idempotency_key      VARCHAR(180) NOT NULL,
    request_fingerprint  CHAR(64) NOT NULL,
    recipient_address    TEXT NOT NULL,
    template_key         VARCHAR(100) NOT NULL,
    template_version     INTEGER NOT NULL,
    variables_json       JSONB NOT NULL,
    status               VARCHAR(32) NOT NULL,
    attempt_count        INTEGER NOT NULL DEFAULT 0,
    attempt_token        UUID,
    lease_until          TIMESTAMPTZ,
    next_attempt_at      TIMESTAMPTZ,
    last_error_kind      VARCHAR(60),
    smtp_accepted_at     TIMESTAMPTZ,
    provider_message_id  TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_email_idempotency
        UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT ck_email_status CHECK (status IN (
        'PENDING', 'SENDING', 'RETRY_WAIT',
        'ACCEPTED_BY_SMTP', 'FAILED_PERMANENT',
        'UNKNOWN', 'DELIVERED', 'BOUNCED'
    )),
    CONSTRAINT ck_email_attempt_count CHECK (attempt_count >= 0)
);

CREATE INDEX ix_email_retry_due
    ON email_delivery (status, next_attempt_at);
CREATE INDEX ix_email_sending_lease
    ON email_delivery (status, lease_until);

CREATE TABLE email_outbox (
    id                UUID PRIMARY KEY,
    delivery_id       UUID NOT NULL REFERENCES email_delivery(id),
    dispatch_no       INTEGER NOT NULL,
    event_type        VARCHAR(50) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    claim_token       UUID,
    claim_until       TIMESTAMPTZ,
    publish_attempts  INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_email_dispatch UNIQUE (delivery_id, dispatch_no)
);

CREATE INDEX ix_email_outbox_pending
    ON email_outbox (published_at, claim_until, created_at);

CREATE TABLE email_delivery_history (
    id             BIGSERIAL PRIMARY KEY,
    delivery_id    UUID NOT NULL REFERENCES email_delivery(id),
    from_status    VARCHAR(32),
    to_status      VARCHAR(32) NOT NULL,
    error_kind     VARCHAR(60),
    actor          VARCHAR(40) NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Giải thích:

- `email_delivery` giữ **trạng thái gửi hiện tại**, payload đã được validate và khóa chống yêu cầu trùng.
- `request_fingerprint` phát hiện dùng cùng idempotency key nhưng request khác; tính từ dữ liệu chuẩn hóa, không từ `Map.toString()`.
- `email_outbox` là **ý định publish** được commit cùng delivery; `dispatch_no=0` cho lần đầu, `1...` cho các lần requeue có chủ đích.
- `email_delivery_history` ghi các chuyển trạng thái (không chứa raw body hoặc password) phục vụ audit.
- `attempt_token` gắn quyền cập nhật kết quả với một lần claim; `lease_until` giúp phát hiện worker chết. **Lease hết hạn không chứng minh thư chưa gửi**.

Cần có migration kiểm tra schema, index và quyền; không tạo bảng theo từng message. Đối với dữ liệu cá nhân, áp dụng mã hóa, quyền truy cập, retention, backup và xóa theo chính sách phù hợp. Không ghi raw recipient/body/token vào metric hoặc log.

### 5.1. Idempotency key đúng phạm vi

Một key nên định danh **một email có chủ đích**: tenant + business event + purpose/template + người nhận logic + version nếu version tạo thư khác.

~~~text
tenant = shop-east
event = order-confirmed:O-204:v3
recipientRole = primary-customer
purpose = order-confirmation
templateVersion = 2

Idempotency-Key =
order-confirmed:O-204:v3:primary-customer:order-confirmation:v2
~~~

Không dùng RabbitMQ deliveryTag/JMSMessageID, UUID mới mỗi HTTP retry hoặc timestamp hiện tại làm **business idempotency key**. Nếu cùng một event gửi cho hai recipient, phải xác định là **hai delivery khác nhau**. Tránh đưa địa chỉ email thô vào key/log; cũng không tự xóa dấu chấm, `+tag` hoặc lowercase local-part theo quy tắc riêng của một nhà cung cấp rồi áp dụng toàn cầu.

### 5.2. Fingerprint của request

Fingerprint cần tính từ **recipient, templateKey, templateVersion, variables** sau khi serialize JSON có thứ tự thuộc tính ổn định, cùng quy tắc normalize được công bố. Cùng key + cùng fingerprint → trả delivery cũ. Cùng key + fingerprint khác → **409 Conflict**, tuyệt đối không sửa request đang gửi.

Nếu fingerprint có thể bộc lộ thông tin cá nhân thông qua brute-force, có thể dùng HMAC với secret riêng được quản lý. Không ghi fingerprint thô cùng mọi biến email vào logs.

## 6. HTTP API tiếp nhận yêu cầu

### 6.1. REST contract

~~~http
POST /api/email-deliveries
Idempotency-Key: order-confirmed:O-204:v3:primary-customer:v2
Content-Type: application/json

{
  "recipient": "customer@example.invalid",
  "templateKey": "order-confirmation",
  "templateVersion": 2,
  "variables": {
    "orderCode": "O-204",
    "customerDisplayName": "Customer"
  }
}
~~~

API chỉ trả sau khi lưu DB thành công:

~~~http
HTTP/1.1 202 Accepted
Location: /api/email-deliveries/73de4c12-7a47-4566-b810-d92b18cab27f
Content-Type: application/json

{
  "deliveryId": "73de4c12-7a47-4566-b810-d92b18cab27f",
  "status": "PENDING",
  "statusUrl": "/api/email-deliveries/73de4c12-7a47-4566-b810-d92b18cab27f"
}
~~~

**202 Accepted không có nghĩa đã gửi email.** HTTP caller phải dùng GET status hoặc callback có xác thực để theo dõi. Cần xác thực tenant, giới hạn rate, validate template cho phép và địa chỉ nhận để tránh API trở thành **open mail relay**.

### 6.2. Request DTO

~~~java
public record SendEmailRequest(
        @NotBlank String recipient,
        @NotBlank String templateKey,
        @Min(1) int templateVersion,
        @NotNull Map<String, String> variables) {
}

public record EmailAccepted(
        UUID deliveryId, String status, URI statusUrl) {
}
~~~

Các annotation Bean Validation không thay thế việc validate sender/recipient domain, kích thước JSON, quyền chọn template, dữ liệu HTML hoặc tập biến bắt buộc. Idempotency key cần độ dài/format hạn chế và phải được giữ nguyên qua các HTTP retries của caller.

### 6.3. Tạo delivery và outbox trong cùng transaction

~~~java
@Service
public class EmailRequestService {
    private final JdbcTemplate jdbc;
    private final EmailRequestFingerprint fingerprintService;

    public EmailRequestService(
            JdbcTemplate jdbc,
            EmailRequestFingerprint fingerprintService) {
        this.jdbc = jdbc;
        this.fingerprintService = fingerprintService;
    }

    @Transactional
    public UUID accept(
            String authenticatedTenant,
            String key,
            SendEmailRequest request) {

        validateCommand(authenticatedTenant, key, request);
        String fingerprint =
                fingerprintService.sha256Canonical(request);
        UUID newId = UUID.randomUUID();

        int inserted = jdbc.update("""
            INSERT INTO email_delivery (
                id, tenant_id, idempotency_key,
                request_fingerprint, recipient_address,
                template_key, template_version,
                variables_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, 'PENDING')
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """,
            newId, authenticatedTenant, key,
            fingerprint, request.recipient(),
            request.templateKey(), request.templateVersion(),
            fingerprintService.toCanonicalJson(request.variables()));

        if (inserted == 1) {
            jdbc.update("""
                INSERT INTO email_outbox (
                    id, delivery_id, dispatch_no, event_type)
                VALUES (?, ?, 0, 'EmailSendRequested')
                """, UUID.randomUUID(), newId);
            return newId;
        }

        ExistingRequest previous = jdbc.queryForObject("""
            SELECT id, request_fingerprint
            FROM email_delivery
            WHERE tenant_id = ? AND idempotency_key = ?
            """,
            (rs, index) -> new ExistingRequest(
                    rs.getObject("id", UUID.class),
                    rs.getString("request_fingerprint")),
            authenticatedTenant, key);

        if (previous == null
                || !previous.fingerprint().equals(fingerprint)) {
            throw new IdempotencyConflictException(
                    "Key already used for different email contents");
        }
        return previous.id();
    }

    private record ExistingRequest(UUID id, String fingerprint) {}

    private void validateCommand(
            String tenant, String key, SendEmailRequest request) {
        // Validate tenant authorization, key length and format,
        // approved template, recipient syntax and payload size.
    }
}
~~~

**EmailRequestFingerprint** và **IdempotencyConflictException** là interface/class do ứng dụng phải triển khai; phần validate trong code là điểm mở rộng bắt buộc trước khi production. PostgreSQL unique `(tenant_id,idempotency_key)` là cơ chế chặn cạnh tranh thật: hai request song song cùng key không thể cùng tạo bản ghi. Với READ COMMITTED, transaction thứ hai có thể đợi transaction thứ nhất; sau đó đọc request đã commit để kiểm tra fingerprint.

Nếu insert outbox lỗi, transaction rollback cả delivery. Nếu HTTP response mất sau commit, caller gửi lại cùng key sẽ nhận lại ID cũ. Khi fingerprint không khớp, map exception thành **HTTP 409 Conflict**, không silently thay recipient/template của một delivery đang xử lý.

### 6.4. Controller và tenant boundary

~~~java
@RestController
@RequestMapping("/api/email-deliveries")
public class EmailDeliveryController {
    private final EmailRequestService requests;
    private final EmailDeliveryQuery queries;

    public EmailDeliveryController(
            EmailRequestService requests,
            EmailDeliveryQuery queries) {
        this.requests = requests;
        this.queries = queries;
    }

    @PostMapping
    ResponseEntity<EmailAccepted> accept(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody SendEmailRequest command,
            Authentication authentication) {
        String tenant = authenticatedTenant(authentication);
        UUID id = requests.accept(tenant, key, command);
        URI location = URI.create("/api/email-deliveries/" + id);
        return ResponseEntity.accepted()
                .location(location)
                .body(new EmailAccepted(
                        id, queries.status(tenant, id), location));
    }
}
~~~

**EmailDeliveryQuery** và hàm **authenticatedTenant(Authentication)** là abstraction minh họa do ứng dụng hiện thực. Tenant phải lấy từ identity đã xác thực, không tin `X-Tenant-Id` do người gọi tự cung cấp. Có thể trả ngay `PENDING` từ service để giảm một query; đoạn này minh họa contract REST. Không gửi RabbitMQ hoặc SMTP trong cùng HTTP controller trước DB commit.

## 7. Outbox relay: publish RabbitMQ có xác nhận

Outbox relay đọc `email_outbox` chưa được đánh dấu publish, gửi `EmailWorkMessage` tới RabbitMQ, rồi cập nhật trạng thái khi có bằng chứng publish phù hợp.

~~~text
HTTP DB transaction
  └── INSERT email_delivery + email_outbox
       └── COMMIT
            └── Outbox relay claim các hàng pending
                 └── RabbitTemplate publish persistent message
                      └── Publisher confirm + mandatory return check
                           └── Mark email_outbox.published_at
~~~

### 7.1. Claim hàng outbox ngắn, không giữ transaction khi đợi broker

Với nhiều relay instances, có thể claim theo batch bằng PostgreSQL:

~~~sql
WITH due AS (
    SELECT id
    FROM email_outbox
    WHERE published_at IS NULL
      AND (claim_until IS NULL OR claim_until < now())
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE email_outbox o
SET claim_token = :relay_token,
    claim_until = now() + interval '30 seconds',
    publish_attempts = publish_attempts + 1
FROM due
WHERE o.id = due.id
RETURNING o.id, o.delivery_id, o.dispatch_no, o.claim_token;
~~~

Đây là SQL PostgreSQL tham chiếu, với named parameters do repository bind. Transaction chỉ bao bước **claim và commit ngay**; sau đó gọi broker ngoài DB transaction. Khi publish thành công và còn token hợp lệ:

~~~sql
UPDATE email_outbox
SET published_at = now(),
    claim_token = NULL,
    claim_until = NULL
WHERE id = :event_id
  AND claim_token = :relay_token
  AND published_at IS NULL;
~~~

Nếu relay chết **sau khi RabbitMQ nhận nhưng trước khi DB ghi published_at**, hàng outbox sẽ được phát lại. Không thể loại hết khoảng trống commit giữa hai hệ thống bằng một transaction DB thông thường. **Worker phải idempotent theo deliveryId và trạng thái DB**, không trông chờ message ID broker tự loại trùng.

### 7.2. Publisher confirms và unroutable returns

Spring AMQP `RabbitTemplate` dùng `CorrelationData` để quan sát confirms/returns. Ví dụ cho Spring AMQP 3.x:

~~~java
public record EmailWorkMessage(
        UUID eventId, UUID deliveryId, int schemaVersion) {
}

@Component
public class ConfirmingWorkPublisher {
    private final RabbitTemplate rabbit;
    private final ObjectMapper mapper;

    public ConfirmingWorkPublisher(
            RabbitTemplate rabbit, ObjectMapper mapper) {
        this.rabbit = rabbit;
        this.mapper = mapper;
    }

    public void publish(UUID eventId, UUID deliveryId) {
        try {
            String json = mapper.writeValueAsString(
                    new EmailWorkMessage(eventId, deliveryId, 1));
            CorrelationData correlation =
                    new CorrelationData(eventId.toString());

            rabbit.convertAndSend(
                    "email.work.exchange", "email.send", json,
                    message -> {
                        message.getMessageProperties()
                                .setMessageId(eventId.toString());
                        message.getMessageProperties()
                                .setDeliveryMode(
                                        MessageDeliveryMode.PERSISTENT);
                        return message;
                    },
                    correlation);

            CorrelationData.Confirm confirmed =
                    correlation.getFuture().get(5, TimeUnit.SECONDS);
            if (!confirmed.isAck()
                    || correlation.getReturn() != null) {
                throw new IllegalStateException(
                        "Broker did not confirm routable work");
            }
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Invalid email work payload", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted waiting for broker confirm", ex);
        } catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException(
                    "Publisher outcome uncertain; keep outbox", ex);
        }
    }
}
~~~

Import chính gồm `RabbitTemplate`, `CorrelationData`, `MessageDeliveryMode`, `ObjectMapper`, `JsonProcessingException`, `TimeUnit`, `ExecutionException` và `TimeoutException`. Hàm có thao tác chờ confirm **blocking**, nên chạy ở outbox relay worker, không chạy trên Reactor event loop. Cần kiểm tra các API theo Spring AMQP version và bảo đảm publisher confirms + returns đã thực sự được bật.

**Confirm ACK không phải email sent.** Nó chỉ là bằng chứng broker xác nhận publish theo giao thức; message có thể unroutable nếu không kiểm tra return. Timeout chờ confirm có thể là **kết quả publish chưa xác định**: giữ outbox để retry, chấp nhận khả năng publish trùng.

## 8. Atomic claim: rào chắn trước nhiều worker và redelivery

Một RabbitMQ queue có thể redeliver sau mất ACK, hoặc nhận event trùng do relay publish lại. Lock Java trong một process không đủ cho nhiều application instances. Mỗi lần chuẩn bị gửi phải có **atomic compare-and-set** trong PostgreSQL:

~~~sql
UPDATE email_delivery
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    attempt_token = :new_attempt_token,
    lease_until = now() + interval '2 minutes',
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'PENDING'
RETURNING
    id, tenant_id, recipient_address,
    template_key, template_version,
    variables_json, attempt_count, attempt_token;
~~~

Nếu worker A claim thành công, worker B update **0 hàng** và **không được gọi SMTP**. Nếu message đến khi delivery đang SENDING, RETRY_WAIT, UNKNOWN hoặc đã có kết quả cuối, worker bỏ qua theo state machine.

### 8.1. Ba ranh giới thực sự

~~~text
Transaction DB #1: claim → SENDING + attemptToken → COMMIT
       ↓
SMTP network operation (không nằm trong DB transaction)
       ↓
Transaction DB #2: ghi outcome theo attemptToken → COMMIT
       ↓
RabbitMQ ACK của delivery
~~~

Không giữ DB transaction mở trong lúc chờ SMTP: không có cách nào để rollback một email đã được mail server chấp nhận chỉ nhờ rollback PostgreSQL. Giữ transaction qua network còn tạo lock lâu, giữ connection và làm tăng độ trễ.

### 8.2. Ghi kết quả với fencing token

Sau khi SMTP trả thành công:

~~~sql
UPDATE email_delivery
SET status = 'ACCEPTED_BY_SMTP',
    smtp_accepted_at = now(),
    attempt_token = NULL,
    lease_until = NULL,
    last_error_kind = NULL,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'SENDING'
  AND attempt_token = :attempt_token;
~~~

**Bắt buộc kiểm tra số hàng update = 1** và ghi lịch sử trạng thái trong cùng transaction. Nếu không khớp token, không được ghi đè trạng thái hoặc tự báo “sent”; có thể lease đã hết và reconciler chuyển UNKNOWN. `attempt_token` là fencing token để bản cập nhật muộn không phủ kết quả mới.

### 8.3. Lease hết hạn không chứng minh chưa gửi thư

~~~sql
UPDATE email_delivery
SET status = 'UNKNOWN',
    last_error_kind = 'worker_lease_expired',
    updated_at = now()
WHERE status = 'SENDING'
  AND lease_until < now()
RETURNING id, attempt_token;
~~~

Transaction reconciler phải ghi history/audit và alert cho những hàng chuyển UNKNOWN. **Không tự động trả về PENDING để gửi lại.** Worker có thể chết trước SMTP send, nhưng cũng có thể đã gửi thành công rồi crash trước khi ghi DB. Chỉ có đối soát với provider hoặc một chính sách chấp nhận nguy cơ gửi trùng mới quyết định có thử lại.

Lease phải lớn hơn thời gian SMTP timeout tổng thể + render + DB update margin; trong môi trường latency bất thường nên có heartbeat/giám sát worker, nhưng heartbeat cũng không thể bảo đảm biết kết quả SMTP sau crash.

### 8.4. Ma trận xử lý message lặp

| Trạng thái DB khi worker nhận | Gọi SMTP? | Quyết định |
| --- | --- | --- |
| PENDING và claim thắng | **Có** | Bắt đầu attempt mới |
| PENDING nhưng claim thua | **Không** | ACK duplicate sau khi xác minh trạng thái |
| SENDING | **Không** | ACK bản sao; reconciler theo dõi lease |
| RETRY_WAIT | **Không** | ACK message đến sớm; scheduler phụ trách |
| ACCEPTED_BY_SMTP, DELIVERED, BOUNCED | **Không** | ACK duplicate |
| FAILED_PERMANENT | **Không** | ACK duplicate, lưu trạng thái lỗi |
| UNKNOWN | **Không** | ACK duplicate, chờ đối soát |
| Không tồn tại delivery/schema không hợp lệ | **Không** | Quarantine/DLQ có kiểm soát |

## 9. JavaMailSender: template, transport và dữ liệu gửi

Không nhận HTML/subject tùy ý hoặc `From` bất kỳ từ caller. Dùng template được cấp phép, có phiên bản và escaping:

~~~java
public record RenderedEmail(
        String subject, String html, String plainText) {
}

public interface EmailTemplateRenderer {
    RenderedEmail render(
            String templateKey,
            int templateVersion,
            Map<String, String> variables);
}
~~~

Một implementation có thể dùng Thymeleaf hoặc engine tương đương, với template key từ allowlist, variable validation, HTML escaping, giới hạn body và quy tắc không chèn CRLF nguy hiểm vào header. **Template version phải ổn định qua retry**; không âm thầm đổi nội dung của delivery đã chấp nhận.

~~~java
@Component
public class SmtpEmailTransport {
    private final JavaMailSender mailSender;
    private final EmailTemplateRenderer renderer;
    private final String from;

    public SmtpEmailTransport(
            JavaMailSender mailSender,
            EmailTemplateRenderer renderer,
            @Value("${app.email.from-address}") String from) {
        this.mailSender = mailSender;
        this.renderer = renderer;
        this.from = from;
    }

    public void send(ClaimedDelivery claim)
            throws MessagingException {
        RenderedEmail content = renderer.render(
                claim.templateKey(), claim.templateVersion(),
                claim.variables());

        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime, true, StandardCharsets.UTF_8.name());
        helper.setFrom(from);
        helper.setTo(claim.recipient());
        helper.setSubject(content.subject());
        helper.setText(
                content.plainText(), content.html());

        // Header phục vụ correlation, KHÔNG chống trùng tại SMTP.
        mime.setHeader(
                "X-Email-Delivery-Id", claim.id().toString());
        mailSender.send(mime);
    }
}
~~~

`ClaimedDelivery` là DTO do repository dựng từ hàng đã claim; các import chính là `JavaMailSender`, `MimeMessageHelper`, `jakarta.mail.internet.MimeMessage`, `jakarta.mail.MessagingException`, `StandardCharsets` và `@Value`. `setText(plain,html)` tạo thông điệp nhiều phiên bản nội dung để mail client chọn cách hiển thị.

### 9.1. SMTP trả thành công chưa chứng minh thư đến inbox

- JavaMailSender trả bình thường chỉ chứng minh **SMTP handoff** thành công theo phản hồi provider tại thời điểm đó.
- Header `Message-ID` hoặc custom header **không** bắt buộc SMTP provider thực hiện idempotency.
- Một thư có thể bị bounce hoặc lọc spam sau khi server chấp nhận.
- Nếu dùng provider API có idempotency key được công bố, cần kiểm tra chính xác thời hạn giữ key và ngữ nghĩa từng endpoint; **không tự suy diễn từ header Message-ID**.
- Gửi **một recipient trên một delivery** giúp theo dõi partial failure và chống trùng rõ hơn một email nhiều recipients.

### 9.2. Phân loại lỗi SMTP bảo thủ

| Lỗi | Chứng cứ | Quyết định đề xuất |
| --- | --- | --- |
| Template sai, địa chỉ invalid trước gửi | Request không hợp lệ | FAILED_PERMANENT |
| Server trả mã từ chối rõ và chắc chắn chưa chấp nhận message | Có response xác định theo phase | RETRY_WAIT với 4xx có thể retry, permanent với 5xx phù hợp |
| Auth sai/permission bị chặn | Vấn đề cấu hình hoặc quyền | Alert, không retry nóng |
| Socket timeout, mất kết nối quanh DATA/ACK | Không chắc server đã nhận | **UNKNOWN**, đối soát trước retry |
| JavaMailSender.send trả bình thường | SMTP handoff đã thành công | ACCEPTED_BY_SMTP |
| Ghi DB thất bại sau SMTP send | Thư có thể đã được chấp nhận | Không ACK sai; reconciler xử lý UNKNOWN |

Phân loại **MailException** chỉ theo class thường không đủ: nhiều lỗi đã được Spring Mail wrapper, và một IOException có thể xảy ra **sau** khi SMTP đã chấp nhận DATA. Mặc định **UNKNOWN** khi không chứng minh được server đã từ chối. Nếu một lỗi được xác định tạm thời nhưng hết ngân sách retry, dừng tự động hoặc chuyển xử lý vận hành theo chính sách, không retry vô hạn.

## 10. RabbitMQ listener: ACK sau khi lưu outcome bền vững

Trong Spring AMQP, có thể dùng `@RabbitListener(ackMode="MANUAL")` và `Channel.basicAck` để ACK **sau khi** worker hoàn tất thao tác cập nhật trạng thái vào PostgreSQL:

~~~java
@Component
public class EmailWorkListener {
    private final ObjectMapper mapper;
    private final EmailDeliveryProcessor processor;

    public EmailWorkListener(
            ObjectMapper mapper,
            EmailDeliveryProcessor processor) {
        this.mapper = mapper;
        this.processor = processor;
    }

    @RabbitListener(
            queues = "${app.email.work-queue}",
            ackMode = "MANUAL")
    public void consume(
            String raw,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long tag)
            throws IOException {

        final EmailWorkMessage work;
        try {
            work = mapper.readValue(raw, EmailWorkMessage.class);
            if (work.eventId() == null
                    || work.deliveryId() == null
                    || work.schemaVersion() != 1) {
                throw new IllegalArgumentException(
                        "Unsupported work message");
            }
        } catch (JsonProcessingException | IllegalArgumentException ex) {
            // Chỉ khi DLX/quarantine queue được cấu hình và kiểm thử.
            channel.basicReject(tag, false);
            return;
        }

        try {
            processor.process(work);
            channel.basicAck(tag, false);
        } catch (UnknownDeliveryException invalidReference) {
            channel.basicReject(tag, false);
        } catch (DataAccessException databaseUnavailable) {
            // Phải có backoff/delayed-requeue/pause policy ở broker.
            channel.basicNack(tag, false, true);
        }
    }
}
~~~

Các import gồm Spring AMQP `@RabbitListener` và `AmqpHeaders`, RabbitMQ `com.rabbitmq.client.Channel`, Spring Messaging `@Header`, Jackson `ObjectMapper`, Spring DAO `DataAccessException` và Java `IOException`. Các exception nghiệp vụ trong ví dụ được ứng dụng định nghĩa.

**Chú ý:** `basicNack(...,requeue=true)` có thể gây **hot requeue loop** khi database mất kết nối; trong production phải có broker-delayed retry, consumer pause/backoff, quorum delivery limit hoặc một chiến lược dừng consumer và cảnh báo. Nếu không thể lưu trạng thái bền vững thì **không ACK như thành công**.

`basicReject(requeue=false)` **không tự xác nhận** message đã tới DLQ nếu DLX/routing sai hoặc broker có giới hạn riêng. Kiểm tra DLQ ingress, queue depth và đường phục hồi; không dùng `nullChannel` hay log-only recovery như một kho bền vững.

### 10.1. Processor: claim, send, ghi outcome

Một abstraction repository:

~~~java
public interface EmailDeliveryRepository {
    ClaimDecision claim(UUID id, UUID newAttemptToken);
    void markAccepted(UUID id, UUID attemptToken);
    void markPermanent(
            UUID id, UUID attemptToken, String errorKind);
    void markRetryWait(
            UUID id, UUID attemptToken,
            String errorKind, Instant nextAttempt);
    void markUnknown(
            UUID id, UUID attemptToken, String errorKind);
}

public sealed interface ClaimDecision
        permits ClaimDecision.Acquired,
                ClaimDecision.Skip, ClaimDecision.Missing {

    record Acquired(ClaimedDelivery delivery)
            implements ClaimDecision {}
    record Skip(String reason) implements ClaimDecision {}
    record Missing() implements ClaimDecision {}
}

public enum SmtpFailureKind {
    KNOWN_TEMPORARY,
    KNOWN_PERMANENT,
    UNCERTAIN
}

public interface SmtpErrorClassifier {
    SmtpFailureKind classify(Throwable error);
}
~~~

`ClaimedDelivery` là DTO trả từ SQL claim (ID, recipient, template, variables, attemptCount, attemptToken). Repository phải triển khai bằng **transaction ngắn** và **fencing update** `WHERE status='SENDING' AND attempt_token=?`. Tất cả state changes và history phải commit trong cùng DB transaction. Nếu update 0 hàng, không được trả success.

Orchestration:

~~~java
@Service
public class EmailDeliveryProcessor {
    private static final int MAX_ATTEMPTS = 5;

    private final EmailDeliveryRepository repository;
    private final SmtpEmailTransport smtp;
    private final SmtpErrorClassifier classifier;

    public EmailDeliveryProcessor(
            EmailDeliveryRepository repository,
            SmtpEmailTransport smtp,
            SmtpErrorClassifier classifier) {
        this.repository = repository;
        this.smtp = smtp;
        this.classifier = classifier;
    }

    public void process(EmailWorkMessage work) {
        UUID token = UUID.randomUUID();
        ClaimDecision decision =
                repository.claim(work.deliveryId(), token);

        if (decision instanceof ClaimDecision.Missing) {
            throw new UnknownDeliveryException(work.deliveryId());
        }
        if (decision instanceof ClaimDecision.Skip) {
            return;  // Không gọi SMTP nếu terminal/in-flight/not-due.
        }

        ClaimedDelivery claim =
                ((ClaimDecision.Acquired) decision).delivery();

        try {
            smtp.send(claim);
        } catch (InvalidEmailInputException | EmailTemplateContractException ex) {
            repository.markPermanent(
                    claim.id(), token, "invalid_email_or_template");
            return;
        } catch (MailException | MessagingException ex) {
            SmtpFailureKind kind = classifier.classify(ex);
            if (kind == SmtpFailureKind.KNOWN_PERMANENT) {
                repository.markPermanent(
                        claim.id(), token, "smtp_permanent_rejection");
            } else if (kind == SmtpFailureKind.KNOWN_TEMPORARY
                    && claim.attemptCount() < MAX_ATTEMPTS) {
                repository.markRetryWait(
                        claim.id(), token, "smtp_temporary_rejection",
                        nextAttemptAt(claim.attemptCount()));
            } else if (kind == SmtpFailureKind.KNOWN_TEMPORARY) {
                repository.markPermanent(
                        claim.id(), token, "retry_budget_exhausted");
            } else {
                repository.markUnknown(
                        claim.id(), token, "uncertain_smtp_result");
            }
            return;
        }

        repository.markAccepted(claim.id(), token);
        // Chỉ return khi outcome DB đã commit thành công.
    }

    private Instant nextAttemptAt(int attemptNumber) {
        long base = Math.min(900L,
                30L << Math.min(attemptNumber - 1, 5));
        long jitter =
                ThreadLocalRandom.current().nextLong(0L, 15L);
        return Instant.now().plusSeconds(base + jitter);
    }
}
~~~

**InvalidEmailInputException, EmailTemplateContractException, UnknownDeliveryException, ClaimedDelivery** và các repository implementations là code của ứng dụng, không phải Spring APIs. `MAX_ATTEMPTS=5` và backoff là ví dụ: production nên bind vào `@ConfigurationProperties`, validate dương và xét provider rate limit/Retry-After. Code phải xử lý **lỗi render template** theo taxonomy: template không tồn tại/biến sai phải thành lỗi permanent và được ghi trạng thái; không để nó ném RuntimeException rồi mặc định requeue vô hạn.

`MailException | MessagingException` chỉ bắt các lỗi gửi đã dự kiến. Một lỗi lập trình, bean bị cấu hình sai hoặc database mất kết nối **không** được nuốt dưới nhánh “retry SMTP”; lỗi ngoài dự kiến phải đi tới error policy/alert đúng tầng.

### 10.2. Crash và ACK theo thứ tự

| Điểm crash | State DB | RabbitMQ | Hậu quả và cách xử lý |
| --- | --- | --- | --- |
| Trước claim | PENDING | Redeliver nếu chưa ACK | Worker sau có thể claim |
| Sau claim, trước SMTP | SENDING | Có thể redeliver | Không gửi lặp; lease hết → UNKNOWN, cần xác minh |
| Sau SMTP accepted, trước DB mark | SENDING | Có thể redeliver | **UNKNOWN** sau lease, không tự resend |
| Sau DB mark ACCEPTED_BY_SMTP, trước ACK | ACCEPTED_BY_SMTP | Có thể redeliver | Worker thấy terminal và ACK, không SMTP send lại |
| ACK đã gửi nhưng kết nối broker mất | State bền vững | Broker có thể giao lại | Deduplicate theo deliveryId/status |
| Đang RETRY_WAIT mà message cũ đến | RETRY_WAIT | Redelivery | ACK message cũ; scheduler phát công việc khi đến hạn |

**Đây là at-least-once message processing với hạn chế gửi trùng best-effort**, không phải exactly-once SMTP. Trường hợp crash trước SMTP mà bị UNKNOWN có thể khiến một email không được gửi nếu không có đối soát; đây là trade-off rõ của chính sách tránh gửi trùng.

## 11. Retry có lịch và xử lý các công việc UNKNOWN

### 11.1. Không dùng requeue nóng cho lỗi SMTP tạm thời

Khi provider **chắc chắn từ chối tạm thời** và còn attempts, worker ghi:

~~~sql
UPDATE email_delivery
SET status = 'RETRY_WAIT',
    next_attempt_at = :scheduled_at,
    last_error_kind = :error_kind,
    attempt_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'SENDING'
  AND attempt_token = :attempt_token;
~~~

Sau khi ghi **RETRY_WAIT** và history vào DB thành công, ACK work message cũ. Một scheduler lấy các hàng đến hạn:

~~~sql
SELECT id, attempt_count
FROM email_delivery
WHERE status = 'RETRY_WAIT'
  AND next_attempt_at <= now()
ORDER BY next_attempt_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Trong **cùng một transaction scheduler**, với từng hàng đã lock: chuyển về `PENDING`, xóa `next_attempt_at`, insert outbox event mới với `dispatch_no = attempt_count` và UUID event mới; ràng buộc `UNIQUE (delivery_id,dispatch_no)` ngăn tạo trùng. **Không commit trạng thái PENDING trước khi insert outbox.**

~~~text
RETRY_WAIT + next_attempt_at đến hạn
     → DB transaction:
          UPDATE delivery SET status=PENDING
          INSERT outbox(dispatch_no=attempt_count)
       COMMIT
     → Outbox relay publish
     → Worker claim lần tiếp theo
~~~

Với các lần attempt 1,2,..., `dispatch_no=1,2,...` là đủ nếu mỗi attempt tạo nhiều nhất một lịch retry. Nếu cần operator retry hoặc re-drive nhiều lần không gắn với attempt count, hãy thêm **dispatch sequence** riêng và transaction increment để không đụng unique.

### 11.2. Budget và phân loại lỗi

Retry policy cần:

- **Maximum attempts** giới hạn, không nhân vô hạn với retry ở SMTP client, RabbitMQ và HTTP caller.
- **Exponential backoff + jitter** và tôn trọng Retry-After/quota của provider khi có.
- Phân loại permanent error (recipient invalid, template missing) khác transient (SMTP 4xx được xác minh).
- **Unknown không tự retry** trừ khi provider hỗ trợ lookup/idempotency hoặc operator ghi nhận chấp nhận nguy cơ duplicate.
- Giới hạn concurrent send/prefetch để không gây cạn connection, rate limit hoặc làm email bị đánh dấu spam.

### 11.3. Reconciliation của UNKNOWN

Một reconciler định kỳ tìm delivery có trạng thái UNKNOWN, giữ đầy đủ **attempt token, correlation, Message-ID/provider ID và mốc thời gian** trong audit an toàn. Quy trình:

1. Nếu provider có API truy vấn giao dịch theo key/message ID, kiểm tra tình trạng thật bằng credential có quyền tối thiểu.
2. Nếu xác minh đã chấp nhận, chuyển sang `ACCEPTED_BY_SMTP` (không tự nhận DELIVERED).
3. Nếu chứng minh **chưa** chấp nhận và business policy cho phép, chuyển `RETRY_WAIT` bằng một transition có audit và dispatch mới.
4. Nếu provider không hỗ trợ xác minh, giữ UNKNOWN, báo vận hành hoặc đưa ra quyết định **chấp nhận gửi trùng** có ghi nhận.
5. Không để UNKNOWN mất khỏi dashboard hoặc bị xóa bởi retention quá ngắn.

**SMTP thuần không cung cấp một API đối soát universal**. Header Message-ID có thể giúp tìm kiếm log nhưng không bắt buộc nhà cung cấp trả kết quả. Trong trường hợp đó, “không gửi lại tự động khi UNKNOWN” là bảo đảm *giảm nguy cơ trùng*, không phải bảo đảm mọi yêu cầu sẽ được giao.

## 12. Theo dõi kết quả qua API, không qua queue depth

REST endpoint đọc trạng thái có phân quyền:

~~~http
GET /api/email-deliveries/73de4c12-7a47-4566-b810-d92b18cab27f
Authorization: Bearer ...
~~~

Ví dụ response:

~~~json
{
  "deliveryId": "73de4c12-7a47-4566-b810-d92b18cab27f",
  "status": "RETRY_WAIT",
  "attemptCount": 2,
  "nextAttemptAt": "2026-11-21T10:10:00Z",
  "smtpAcceptedAt": null,
  "lastErrorKind": "smtp_temporary_rejection",
  "updatedAt": "2026-11-21T10:08:00Z"
}
~~~

API chỉ trả dữ liệu thuộc tenant mà principal có quyền. Query phải có cả `delivery_id` **và** `tenant_id`, ví dụ:

~~~sql
SELECT id, status, attempt_count,
       next_attempt_at, smtp_accepted_at,
       last_error_kind, updated_at
FROM email_delivery
WHERE id = :delivery_id
  AND tenant_id = :authenticated_tenant;
~~~

Nếu không tìm thấy, trả 404 hoặc thông điệp thống nhất theo chính sách chống enumeration. Không hiển thị recipient/body, SMTP credential, stack trace hoặc provider raw response cho caller thông thường. Có thể cung cấp endpoint admin kiểm tra history với phân quyền riêng và audit truy cập.

### 12.1. Đừng đặt tên “delivered” cho SMTP success

Nếu chỉ dùng JavaMailSender + SMTP, client nên thấy **ACCEPTED_BY_SMTP**. Khi có provider webhook/bounce:

- Xác minh signature, timestamp/replay protection và quyền gửi webhook.
- Xác định **provider event ID** duy nhất và lưu để bỏ các webhook lặp.
- Match provider_message_id/correlation với delivery ID, không tin event ID chưa xác thực từ request.
- Chấp nhận event đến trễ hoặc đảo thứ tự; không để event trạng thái cũ ghi đè trạng thái mới trái policy.
- `BOUNCED`, `COMPLAINED`, `DELIVERED` là những tín hiệu khác nhau; không suy diễn người nhận đã đọc từ delivered.

Có thể có dashboard theo dõi **SMTP accepted** riêng và **provider delivered** riêng, cùng tỷ lệ bounce và thời gian từ request tới xác nhận.

### 12.2. Trạng thái outbox khác trạng thái email

`published_at` có nghĩa **công việc đã được broker xác nhận**; không phải SMTP success. Một outbox event có thể được publish nhiều lần mà delivery vẫn chỉ có một lần claim; ngược lại một delivery có thể có nhiều outbox events do retry. **Queue depth** là gauge số message đang chờ, không phải tổng số email đã gửi.

## 13. Các trạng thái lỗi và quy trình phục hồi

Một hệ thống email đáng tin cậy cần **error taxonomy** thống nhất giữa request API, outbox relay, RabbitMQ consumer, renderer, SMTP và callback:

| Vị trí lỗi | Ví dụ | Nơi giữ trách nhiệm | Cách phục hồi |
| --- | --- | --- | --- |
| HTTP request validation | Thiếu recipient/template | HTTP caller | 400; không tạo delivery |
| Dùng lại idempotency key sai payload | Cùng key, khác recipient | HTTP caller | 409; không sửa delivery cũ |
| PostgreSQL không commit được lúc accept | DB outage | HTTP caller | 503/5xx; retry cùng idempotency key |
| Outbox relay gặp broker outage | Không có publisher confirm | Outbox bền vững | Retry publish với backoff; có thể duplicate queue |
| Message không route được | Unroutable return | Outbox relay | Sửa exchange/binding, không mark published |
| Work payload/schema sai | Invalid JSON/unsupported schemaVersion | Quarantine queue | Cách ly + alert, không gọi SMTP |
| Delivery ID không tồn tại | Lỗi dữ liệu/outbox inconsistency | Quarantine và điều tra | Không tạo delivery mới từ broker payload |
| Worker không truy cập DB | DB timeout trước/giữa claim | Broker work vẫn chưa ACK | Backoff/pause/requeue có giới hạn |
| SMTP từ chối tạm thời rõ ràng | Provider 4xx có chứng cứ | email_delivery RETRY_WAIT | Scheduler phát outbox lần sau |
| SMTP từ chối vĩnh viễn | Recipient invalid, 5xx phù hợp | FAILED_PERMANENT | Sửa dữ liệu/nhân viên xử lý, không retry vô hạn |
| SMTP timeout sau khi bắt đầu gửi | Kết quả không rõ | UNKNOWN | Tra cứu/đối soát, không tự resend |
| SMTP success, DB result update lỗi | Có thể mail đã đi | SENDING → UNKNOWN | Reconcile, ngăn gửi lặp |
| Rabbit ACK thất bại | DB đã có terminal status | Broker có thể redeliver | Worker skip SMTP và ACK bản sao |
| Provider trả bounce | Hộp thư không nhận được | Feedback history | Cập nhật bounce policy/stop send theo quy tắc |

**DLQ không thay thế bảng trạng thái gửi.** Một email `FAILED_PERMANENT` có thể là kết quả nghiệp vụ cần hiển thị trong API, trong khi một message JSON sai schema là sự cố hạ tầng nên đưa sang quarantine. Nếu gửi mọi thất bại SMTP sang DLQ mà không cập nhật email_delivery, người dùng sẽ chỉ thấy PENDING mãi mãi.

### 13.1. Cảnh báo khi có thể mất trách nhiệm xử lý

Đặc biệt cần báo động nếu:

- Delivery PENDING đã commit lâu nhưng **không có outbox** tương ứng: vi phạm invariant transaction.
- Outbox `published_at IS NULL` tồn tại lâu, relay không gửi được hoặc bị kẹt lease.
- PENDING đã được publish nhưng queue không có consumer và tuổi yêu cầu tăng.
- SENDING vượt lease, UNKNOWN tăng; không âm thầm phát lại.
- RETRY_WAIT đã quá next_attempt_at lâu nhưng scheduler không tạo dispatch mới.
- DLQ ingress tăng, đặc biệt lỗi schemaVersion hoặc delivery ID không tồn tại.
- ACCEPTED_BY_SMTP tăng nhưng bounce/complaint rate cũng tăng, cần kiểm tra chất lượng địa chỉ/template.

## 14. Observability: metric, log, trace và SLO

Thiết kế metric theo **đơn vị đo và thời điểm tăng**, tránh gọi chung mọi sự cố là `email_errors`:

| Metric đề xuất (Micrometer name) | Type | Khi nào ghi |
| --- | --- | --- |
| `app.email.request.accepted` | Counter | Transaction accept email + outbox commit |
| `app.email.request.idempotency_reused` | Counter | Cùng key/fingerprint trả lại ID cũ |
| `app.email.request.idempotency_conflict` | Counter | Cùng key khác fingerprint bị 409 |
| `app.email.outbox.publish_attempts` | Counter | Relay thực sự bắt đầu một publish |
| `app.email.outbox.publish_confirmed` | Counter | Confirm ACK và không có unroutable return |
| `app.email.outbox.pending` | Gauge | Số outbox chưa published |
| `app.email.outbox.oldest_age` | Gauge | Tuổi outbox chưa publish lâu nhất |
| `app.email.work.received` | Counter | Một delivery RabbitMQ vào worker, gồm redelivery |
| `app.email.work.claimed` | Counter | Claim DB trả 1 hàng, attempt thực sự bắt đầu |
| `app.email.work.duplicate_skipped` | Counter | Work message không cần gửi vì state hiện tại |
| `app.email.send.attempt.duration` | Timer | Thời gian render + SMTP của một attempt |
| `app.email.smtp.accepted` | Counter | JavaMailSender trả thành công và DB đã ghi kết quả |
| `app.email.retry.scheduled` | Counter | Trạng thái RETRY_WAIT đã được commit |
| `app.email.unknown` | Counter | Một transition vào UNKNOWN |
| `app.email.delivery.status` | Gauge | Số delivery đang ở mỗi status |
| `app.email.feedback.bounced` | Counter | Bounce event xác thực, không đếm webhook retry trùng |
| `app.email.quarantine.received` | Counter | Message đi vào DLQ/quarantine được quan sát |

Tên này là **quy ước ứng dụng đề xuất**, không phải toàn bộ metric có sẵn của Spring Boot/Spring AMQP. Counter process có thể reset khi restart. Với Prometheus, sử dụng `rate()`/`increase()` phù hợp; gauge là giá trị tức thời, không cộng queue depth như tổng event lịch sử.

### 14.1. Tag và cardinality

Tag nên là tập hữu hạn như:

~~~text
template=order-confirmation | shipment-update
provider=primary-smtp | backup-smtp
error_kind=timeout | temporary_reject | invalid_recipient | unknown
status=PENDING | SENDING | RETRY_WAIT | ACCEPTED_BY_SMTP | UNKNOWN
result=success | failure
~~~

**Không** dùng `deliveryId`, idempotency key, email address, raw tenantId, subject, message body hoặc provider token làm metric label. Chúng có cardinality rất cao, có thể lộ PII hoặc credential. Các ID nghiệp vụ dùng cho correlation có thể xuất hiện ở **log/trace có quyền truy cập và retention phù hợp**, sau khi áp dụng chính sách dữ liệu.

### 14.2. Trace qua ba hệ thống

~~~text
HTTP POST (requestId)
  → DB transaction accept:
       deliveryId = 73de...
       outboxEventId = 8fd...
  → outbox relay:
       Rabbit publish / confirm
  → Rabbit worker:
       deliveryId = 73de...
       attemptToken = ...
       DB claim
       SMTP send
       DB outcome
       Rabbit ACK
  → GET status / feedback event
~~~

Trace context đi qua HTTP, outbox và RabbitMQ phải được truyền có chủ đích; broker hoặc worker không tự nối span đúng chỉ vì header có UUID. Không log SMTP password hoặc header Authorization. Nếu raw email body có PII, không ghi vào trace baggage.

### 14.3. SLO và dashboard

Một dashboard vận hành nên có:

- **Acceptance latency**: thời gian từ POST tới DB commit/202.
- **Queue-to-start latency**: từ `created_at` tới claim đầu tiên.
- **Time-to-SMTP-accept**: thời gian từ yêu cầu tới `smtp_accepted_at`, chỉ với trạng thái có xác nhận.
- **Retry rate**, **UNKNOWN rate**, **permanent failure rate** và số đang RETRY_WAIT.
- **Outbox oldest age**, queue ready/unacked, consumer concurrency, DB pool saturation.
- **Provider rejection/timeout**, **bounce/complaint** và feedback latency nếu có.

Không tạo SLO “100% delivered” khi chỉ có SMTP acceptance. Nên tách **“SMTP accepted within 5 minutes”** và **“confirmed delivered”** nếu provider có dữ liệu cần thiết, đồng thời tính riêng UNKNOWN/PENDING quá hạn.

## 15. Bảo mật, quyền gửi và dữ liệu cá nhân

Một API gửi email rất dễ bị lạm dụng thành **open relay** nếu không kiểm soát. Những kiểm soát cần có:

1. **Authentication và authorization**: caller chỉ được gửi đúng purpose/template/recipient policy của tenant, không tự chọn `From` tùy ý.
2. **Template allowlist/versioning**: tránh nội dung tùy tiện và template injection; HTML-escape variables, chặn control characters/header injection.
3. **Rate limit/quota**: giới hạn số request trên tenant/purpose/domain và concurrent SMTP sends; tôn trọng provider limits.
4. **Email validation**: kiểm tra cú pháp, dữ liệu đã xác minh, suppression list/bounces/unsubscribe; không tự sửa địa chỉ quá mức theo quy tắc một nhà cung cấp.
5. **Legal/compliance**: phân biệt email giao dịch và marketing, có chính sách consent/unsubscribe, retention và data minimization phù hợp.
6. **Transport security**: SMTP TLS/STARTTLS, validate certificates; bảo vệ password/OAuth token qua secret manager và rotation.
7. **Domain reputation**: cấu hình SPF, DKIM, DMARC theo domain gửi và phản hồi bounce/complaint; không gán provider acceptance bằng chứng thư đã tới inbox.
8. **Privacy**: mã hóa/bảo vệ email address, variables, logs, backups; API GET có tenant authorization và không để lộ body cho caller không có quyền.
9. **Replay/abuse protection**: idempotency key có scope, TTL/retention được thiết kế theo nghiệp vụ, hạn chế số lượng key ngẫu nhiên trên một actor.
10. **Template changes**: triển khai version mới có kiểm soát; tránh render lại một delivery cũ bằng template khác sau retry.

Không có chiến lược chống trùng nào bảo vệ được hệ thống khi caller chủ ý tạo **idempotency key mới cho cùng sự kiện**. Nguồn phát sự kiện nghiệp vụ phải có contract rõ về key và việc phát lại.

## 16. Kiểm thử integration: chứng minh cả những điểm crash

Test unit cho service/mapper chỉ xác minh logic Java. Bài toán queue + transaction + SMTP cần test tích hợp sử dụng **PostgreSQL thật, RabbitMQ thật và SMTP test server** (chẳng hạn GreenMail, MailHog hoặc một SMTP stub kiểm soát được phản hồi).

### 16.1. Testcontainers PostgreSQL và RabbitMQ

Ví dụ skeleton JUnit 5:

~~~java
@Testcontainers
@SpringBootTest
class EmailDeliveryIntegrationIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @Container
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4-management");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry props) {
        props.add("spring.datasource.url",
                postgres::getJdbcUrl);
        props.add("spring.datasource.username",
                postgres::getUsername);
        props.add("spring.datasource.password",
                postgres::getPassword);
        props.add("spring.rabbitmq.host", rabbit::getHost);
        props.add("spring.rabbitmq.port", rabbit::getAmqpPort);
    }

    // Cấu hình SMTP fake host/port bằng test properties,
    // chạy migration, khởi động relay/worker và assert DB,
    // RabbitMQ queue/DLQ, SMTP messages.
}
~~~

Khai báo dependency Testcontainers `postgresql`, `rabbitmq`, JUnit 5 module và JDBC driver phù hợp, cùng SMTP stub test. Image versions chỉ để minh họa, cần pin và cập nhật theo CI. Nếu test cần auth RabbitMQ riêng, khai báo credentials test trong cấu hình riêng; không dùng production secrets.

### 16.2. Ma trận test phải có

| Kịch bản | Kết quả bắt buộc |
| --- | --- |
| Một POST hợp lệ | Một email_delivery + một email_outbox, HTTP 202 |
| POST lặp cùng key/payload | Cùng deliveryId, không thêm outbox |
| POST cùng key nhưng khác recipient/template | HTTP 409, request cũ không đổi |
| Hai POST đồng thời cùng key | Unique constraint bảo vệ, chỉ một delivery |
| DB commit thất bại khi insert outbox | Rollback cả delivery, không có orphan request |
| Relay chết trước publish | Outbox còn pending, restart có thể publish |
| Relay publish thành công rồi crash trước mark | Có thể có hai queue messages; worker chỉ một claim |
| Broker publisher confirm NACK/unroutable | Không mark published, retry đúng policy |
| Hai workers cùng nhận duplicate message | Chỉ một atomic claim thắng; không send song song |
| SMTP trả accepted, DB mark thành công, broker ACK mất | Redelivery skip SMTP, giữ ACCEPTED_BY_SMTP |
| SMTP accepted rồi worker crash trước DB mark | SENDING hết lease → UNKNOWN, **không auto resend** |
| SMTP 4xx chắc chắn chưa accept | RETRY_WAIT với nextAttemptAt, scheduler tạo dispatch mới |
| Retry đạt max attempts | FAILED_PERMANENT hoặc manual review theo policy, không loop |
| SMTP kết quả bất định | UNKNOWN và reconciliation, không tự retry |
| Invalid template/recipient | FAILED_PERMANENT, không gửi |
| Work message JSON sai/schemaVersion lạ | Quarantine/DLQ; không tạo email delivery |
| DB outage ở listener | Không ACK như success; requeue/backoff/pause có giới hạn |
| DeliveryId của tenant khác | API GET không lộ trạng thái hoặc dữ liệu |
| Provider gửi webhook bounce hai lần | Một transition/logical event được ghi, không nhân đôi metric |
| Quá nhiều requests | Rate limit, queue/pool saturation có ngưỡng và cảnh báo |

### 16.3. Fault injection quan trọng nhất

Để kiểm chứng “SMTP accepted nhưng DB không kịp ghi”, một fake SMTP server có thể **ghi nhận đã nhận DATA**, rồi test tắt worker hoặc inject lỗi ở bước `markAccepted`. Sau đó:

~~~text
1. Worker claim → SENDING, attempt_count=1.
2. Fake SMTP ghi nhận một message.
3. Inject crash/lỗi DB trước markAccepted.
4. Broker redeliver (hoặc relay gửi duplicate).
5. Worker mới thấy SENDING nên không send thêm.
6. Lease hết, reconciler chuyển UNKNOWN.
7. Assert SMTP fake vẫn chỉ có một message.
8. Operator/reconciler xử lý UNKNOWN theo policy rõ ràng.
~~~

Test này chứng minh chính sách **không tự gửi lại khi kết quả chưa rõ**, không chứng minh email đã thực sự được giao tới inbox. Test thêm tình huống crash **trước SMTP call**: state cũng có thể UNKNOWN, cho thấy trade-off giữa gửi trùng và bỏ sót khi chưa đối soát.

### 16.4. Test transaction và assertion đúng đơn vị

Không chỉ assert “listener được gọi một lần”: RabbitMQ có thể giao hai lần nhưng hệ thống vẫn đúng nếu **một claim thắng và không có side effect trùng**. Cần assert:

- Số hàng `email_delivery` và `email_outbox` theo business key.
- Số attempts và trạng thái đúng sau từng lỗi.
- Số email mà SMTP fake **thực sự nhận**.
- Khi relay/worker restart, dữ liệu vẫn giữ nguyên và scheduler phục hồi.
- Không có terminal success giả khi SMTP không rõ kết quả.

Không dùng `Thread.sleep` dài cố định nếu có thể dùng Awaitility/polling với deadline và condition rõ. Đảm bảo cleanup test data, queue, SMTP stub và isolation giữa tests; tránh các tests chạy song song vô tình cạnh tranh cùng queue.

## 17. Runbook vận hành và đối soát

~~~mermaid
flowchart TD
    A["Cảnh báo email backlog/unknown tăng"] --> B{"Vị trí nghẽn?"}
    B -->|"Outbox chưa publish"| C["Kiểm tra RabbitMQ confirms, returns, bindings"]
    B -->|"Queue tích tụ"| D["Kiểm tra worker, DB pool, prefetch, rate limit"]
    B -->|"SMTP reject/timeout"| E["Kiểm tra provider health, quota, TLS và auth"]
    B -->|"UNKNOWN"| F["Đối soát provider, không auto resend"]
    C --> G["Khôi phục và đo outbox oldest age"]
    D --> G
    E --> G
    F --> H["Ghi quyết định accepted/retry/manual review"]
    G --> I["Kiểm tra API statuses + audit + recipient suppression"]
    H --> I
~~~

Trình tự xử lý:

1. Xác định mất kết nối ở **DB, broker, worker hay SMTP** qua metric và trace, không xem mọi lỗi là SMTP fail.
2. Nếu outbox pending tăng, kiểm tra confirms/unroutable returns, DLX/queue configuration và relay lease.
3. Nếu queue ready/unacked tăng, kiểm tra worker concurrency, SMTP timeout, provider quota, DB pool và xử lý hot redelivery.
4. Nếu RETRY_WAIT quá hạn tăng, kiểm tra scheduler; không gửi lại bằng script thủ công bỏ qua idempotency.
5. Nếu UNKNOWN tăng, xuất danh sách kiểm soát, đối soát qua provider/log có phân quyền; ghi rõ từng quyết định retry.
6. Với BOUNCED/COMPLAINED, cập nhật suppression và thông báo cho nghiệp vụ; không tiếp tục gửi vô hạn tới địa chỉ bị từ chối.
7. Khi khôi phục, đối chiếu request accepted, outbox published, attempts, SMTP accepted, unknown và feedback; tránh kết luận từ một metric đơn lẻ.

**Operator re-drive** phải là một lệnh nghiệp vụ có auth, audit, expected-state check và idempotency riêng; không đơn thuần “copy message từ DLQ qua work queue” nếu DB đang ở ACCEPTED_BY_SMTP hoặc UNKNOWN.

### 17.1. Nếu tổ chức dùng Spring Integration DSL

Kiến trúc này cũng có thể dùng **Spring Integration AMQP inbound/outbound adapters**, `IntegrationFlow`, channel và service activator thay cho một số lớp `@RabbitListener`/relay trong ví dụ. Khi đó cần giữ nguyên những ranh giới quan trọng:

- API ghi **email_delivery + outbox** trong DB transaction; không gửi trực tiếp mail từ HTTP thread.
- AMQP inbound flow phải gọi service **atomic claim → SMTP → durable outcome**, thay vì gửi thẳng payload tới mail outbound adapter rồi mặc định đã có exactly-once.
- `errorChannel`, `RequestHandlerRetryAdvice` hoặc `ErrorMessageSendingRecoverer` chỉ là cơ chế điều phối lỗi; **không chứng minh** bản tin đã được lưu bền vững hoặc email đã được gửi.
- Bảo vệ `ACK/NACK` của message nguồn theo loại inbound adapter, listener container, transaction và recoverer thực tế. Một error flow log xong rồi return có thể vô tình làm source ACK.
- Đặt correlation ID, deliveryId và eventId qua adapter một cách có kiểm soát; không phát tán địa chỉ email/SMTP token thành headers không cần thiết.

Nếu dùng **MailSendingMessageHandler** của Spring Integration để thực hiện SMTP, vẫn phải bao quanh nó bằng chính sách status/attempt token và xử lý `UNKNOWN`. Đổi tên adapter không làm biến mất khoảng không nguyên tử giữa SMTP acceptance và DB commit.

## 18. Những nhầm lẫn cần tránh

**“Đã gửi message vào RabbitMQ là đã gửi email.”** Chưa: mới chỉ xếp công việc, worker và SMTP còn chưa xử lý.

**“Publisher confirm ACK nghĩa là người nhận đã có thư.”** Sai: confirm thuộc broker publish, không phải SMTP hoặc inbox.

**“JavaMailSender.send trả về nghĩa là thư chắc chắn delivered.”** Nó chỉ chứng minh SMTP/provider chấp nhận theo operation, chưa tính bounce/spam.

**“Message-ID chống gửi trùng.”** Đây là header correlation, không phải giao thức exactly-once SMTP.

**“Đặt @Transactional quanh SMTP send là đủ rollback.”** Transaction DB không thể thu hồi email đã được server nhận.

**“Cứ gặp MailException thì retry ngay.”** Timeout gần SMTP DATA/ACK có thể là kết quả bất định; resend có thể tạo thư trùng.

**“RabbitMQ sẽ tự lọc bản tin có cùng eventId.”** Không phải mặc định; phải dựa trên DB state/claim/unique key.

**“Dùng Redis setNX hoặc lock trong RAM là đủ.”** Một lock tạm thời không thay thế unique constraint, durable outcome và cơ chế xử lý crash.

**“ACK trước khi commit outcome giúp hệ thống chạy nhanh.”** Có thể mất khả năng phục hồi nếu process crash trước khi lưu kết quả.

**“Một số lỗi SMTP có thể nuốt và trả thành công để tránh redelivery.”** Điều này che lỗi và làm API theo dõi sai; chỉ ACK khi transition hoặc quyết định recovery đã được lưu bền vững.

**“Lease hết chứng minh chưa gửi.”** Không; worker có thể đã gửi thành công rồi chết trước DB update.

**“Chỉ cần DLQ để xem tất cả email thất bại.”** DLQ theo dõi message poison/transport; bảng delivery mới giữ trạng thái nghiệp vụ như RETRY_WAIT, UNKNOWN, SMTP accepted và bounced.

**“Một idempotency key dùng cho mọi người nhận.”** Cần xác định đúng một đơn vị gửi và recipient/purpose; nếu không sẽ bỏ sót email hợp lệ.

**“Dùng lại cùng key với request khác thì cứ lấy request mới.”** Phải trả 409; không mutate delivery đã chấp nhận.

## 19. Checklist trước khi triển khai production

1. Chốt hợp đồng `202 Accepted`, endpoint GET status và ý nghĩa của `ACCEPTED_BY_SMTP` so với `DELIVERED`.
2. Định nghĩa idempotency key theo tenant, event, purpose/template và recipient; cùng key khác payload phải 409.
3. Commit email_delivery + outbox trong **một PostgreSQL transaction**.
4. Outbox relay dùng lease/claim, publisher confirms, mandatory returns và xử lý publish outcome không chắc chắn.
5. Queue durable, message persistent, DLX/quarantine được kiểm thử; không dùng queue depth như số mail đã gửi.
6. Worker dùng atomic DB claim/fencing token; không gửi khi status đã terminal, SENDING hoặc UNKNOWN.
7. SMTP send có timeout, STARTTLS/TLS, sender allowlist, template escaping và provider rate limit.
8. ACK broker chỉ sau khi DB state/decision bền vững; mất DB phải có requeue/backoff/pause an toàn.
9. Chỉ retry lỗi **được chứng minh chưa accept**, có max attempts và backoff/jitter; timeout bất định → UNKNOWN.
10. Scheduler retry qua outbox trong transaction; expired SENDING → UNKNOWN, không tự động resend.
11. Reconciliation và operator re-drive được xác thực, ghi audit và tránh gửi duplicate.
12. Bảo vệ recipient/variables, suppression list, consent, retention, SPF/DKIM/DMARC và credentials.
13. Metrics/tracing phân biệt accepted request, published work, claim, SMTP acceptance, unknown và feedback.
14. Test với PostgreSQL + RabbitMQ + SMTP giả, đặc biệt duplicate concurrent, crash sau SMTP success, mất ACK và DLQ.
15. Có runbook khi outbox backlog, retry_due quá hạn, UNKNOWN tăng và provider bounce.

**Kết luận:** gửi email qua hàng đợi không phải “đưa `JavaMailSender.send()` vào một listener”. Thiết kế đáng tin cậy phải có **DB outbox để không mất ý định gửi, unique idempotency key để chống nhận trùng, atomic claim để chống nhiều worker, state machine để theo dõi kết quả, và cách xử lý UNKNOWN trung thực**. Hệ thống có thể đảm bảo việc **tiếp nhận và điều phối công việc bền vững** trong phạm vi đã thiết kế, nhưng không nên hứa exactly-once delivery trên SMTP thuần.

## Tài liệu tham khảo

- [Spring Boot Reference — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html): JavaMailSender, mail starter, cấu hình SMTP và các timeout.
- [Spring Framework — Email](https://docs.spring.io/spring-framework/reference/integration/email.html): MimeMessageHelper, nội dung HTML/plain và giao diện mail sender.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): @RabbitListener, ackMode MANUAL và listener container.
- [Spring AMQP — RabbitTemplate/Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): CorrelationData, publisher confirms, mandatory returns.
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): acknowledge modes, concurrency, prefetch và container settings.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ranh giới ACK của consumer và confirm của producer.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject/nack, routing và dead-letter.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): ranh giới @Transactional và commit/rollback.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): unique constraint và idempotent insert.
- [PostgreSQL — SELECT / SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html): cạnh tranh worker và claim outbox.
- [Testcontainers — Modules](https://java.testcontainers.org/modules/): PostgreSQL, RabbitMQ và môi trường integration test.
