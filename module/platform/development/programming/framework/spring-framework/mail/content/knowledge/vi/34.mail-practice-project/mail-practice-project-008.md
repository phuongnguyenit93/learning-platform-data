# Tạo outbox cho email sau khi transaction commit

Trong một dự án Spring Framework Mail, yêu cầu tưởng chừng đơn giản là: **khi một đơn hàng được xác nhận, gửi email thông báo cho khách hàng**. Nhưng nếu gửi bằng `JavaMailSender` trực tiếp trong phương thức có `@Transactional`, chúng ta sẽ gặp vấn đề **dual-write** giữa database và SMTP server.

Bài thực hành này xây dựng một **transactional outbox** nhỏ với **Spring Boot, Spring JDBC, PostgreSQL, Spring Mail và Mailpit**. Khi ứng dụng tạo đơn hàng, nó lưu **đơn hàng và ý định gửi email trong cùng transaction**. Chỉ sau khi transaction commit, một worker mới nhìn thấy outbox job, nhận quyền xử lý, gửi qua SMTP và ghi lại kết quả. Khi SMTP lỗi, job được lên lịch retry; khi worker chết, lease hết hạn để job có cơ hội được xử lý tiếp.

Điểm cần hiểu thật rõ ngay từ đầu:

> **Outbox row phải được INSERT trong business transaction, không phải INSERT sau commit. Việc GỬI email mới diễn ra sau khi transaction commit.**

Nếu đợi database commit xong mới INSERT outbox, ứng dụng có thể crash giữa hai bước và mất hoàn toàn ý định gửi. Nếu gửi SMTP trước khi commit, email có thể được relay chấp nhận rồi business transaction rollback. Transactional outbox nhằm loại bỏ **khoảng trống giữa business write và mail intent**, không tạo giao dịch phân tán với SMTP.

~~~mermaid
flowchart TD
    A["POST /api/orders"] --> B["BEGIN database transaction"]
    B --> C["INSERT app_order"]
    B --> D["INSERT mail_outbox PENDING"]
    C --> E["COMMIT atomically"]
    D --> E
    E --> F["Worker poll committed jobs"]
    F --> G["Claim job + lease"]
    G --> H["COMMIT claim"]
    H --> I["Compose MIME + JavaMailSender.send"]
    I --> J{"SMTP submission"}
    J -->|"Accepted"| K["Mark SENT"]
    J -->|"Temporary error"| L["RETRY + next_attempt_at"]
    J -->|"Permanent error"| M["DEAD / manual action"]
    L --> F
~~~

Sau bài thực hành, bạn sẽ có một API tạo đơn hàng, bảng outbox bền vững, một dispatcher có claim/lease, xử lý retry cơ bản, cấu hình SMTP test và bộ tình huống để kiểm tra commit/rollback/restart/duplicate. Đây là **nền tảng thực hành**, không phải hệ thống email production đã đầy đủ mọi yêu cầu về domain, consent, DKIM, quota hay delivery feedback.

## 1. Kết quả cần đạt

Luồng thành công:

~~~text
Client POST /api/orders
  -> OrderApplicationService
       BEGIN
       INSERT app_order
       INSERT mail_outbox(status=PENDING)
       COMMIT
  <- HTTP 201 Created + orderId

Outbox worker
  -> SELECT committed job
  -> claim: PENDING -> SENDING
  -> JavaMailSender.send(...)
  -> local Mailpit SMTP accepts
  -> update status=SENT

Mailpit UI
  -> hiển thị email xác nhận
~~~

Luồng rollback:

~~~text
OrderApplicationService
  BEGIN
  INSERT app_order
  INSERT mail_outbox
  throw RuntimeException
  ROLLBACK

Result:
  Không có order mới.
  Không có mail_outbox job.
  Worker không có gì để gửi.
~~~

Luồng tạm lỗi:

~~~text
SMTP đang ngừng hoạt động
  -> worker gửi thất bại
  -> status RETRY
  -> next_attempt_at = tương lai

SMTP hoạt động lại
  -> worker claim khi đến hạn
  -> gửi lại
  -> status SENT
~~~

Và giới hạn cần chấp nhận:

~~~text
SMTP đã chấp nhận thư
worker crash trước khi ghi SENT
lease hết hạn
worker mới có thể gửi lại
=> Có nguy cơ email trùng.
~~~

Mục tiêu là **không mất yêu cầu gửi sau khi commit**, có thể phục hồi sau lỗi và biết chính xác ranh giới bảo đảm của hệ thống.

## 2. Kiến trúc dự án nhỏ

Các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `OrderController` | Nhận HTTP request, trả order ID |
| `OrderApplicationService` | Mở business transaction |
| `OrderRepository` | Ghi và đọc đơn hàng |
| `MailOutboxWriter` | INSERT ý định gửi với unique idempotency key |
| `MailOutboxClaimer` | Claim job tới hạn trong transaction ngắn |
| `OutboxPollingWorker` | Poll và điều phối xử lý |
| `OutboxEmailProcessor` | Đọc payload, tạo MIME, gửi SMTP |
| `MailOutboxResultWriter` | Ghi SENT, RETRY hoặc DEAD theo lease token |
| PostgreSQL | Nguồn sự thật của order và outbox |
| Mailpit | SMTP server/UI thử nghiệm, không gửi Internet |
| `JavaMailSender` | API Spring gửi MIME qua SMTP |

Cấu trúc tham khảo:

~~~text
src/main/java/com/example/mailoutbox/
  MailOutboxApplication.java
  order/
    CreateOrderRequest.java
    CreateOrderResponse.java
    OrderRow.java
    OrderRepository.java
    OrderApplicationService.java
    OrderController.java
  mail/
    OrderMailPayload.java
    MailOutboxWriter.java
    ClaimedMailJob.java
    MailOutboxClaimer.java
    MailOutboxResultWriter.java
    OutboxEmailProcessor.java
    OutboxPollingWorker.java
src/main/resources/
  application.yml
  db/migration/V1__create_orders_and_mail_outbox.sql
compose.yml
~~~

Tên package/lớp mang tính gợi ý. Để dễ thấy ranh giới giao dịch, ví dụ dùng **Spring JDBC** với SQL trực tiếp; có thể thay bằng Spring Data JPA nếu giữ nguyên semantics.

## 3. Công nghệ và điều kiện chạy

Môi trường ví dụ:

- Java 17 trở lên.
- Spring Boot 3.x với Jakarta Mail.
- Spring Web và Validation cho HTTP API.
- Spring JDBC và PostgreSQL.
- Flyway cho migration.
- Spring Boot Mail/`JavaMailSender`.
- Docker Compose để chạy PostgreSQL và Mailpit.
- Spring Test cùng database/SMTP test phù hợp khi viết integration test.

Các dependency Gradle dạng minh họa:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.postgresql:postgresql'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cấu hình Flyway modules có thể khác tùy phiên bản Spring Boot/Flyway được quản lý; ví dụ giả định dùng một phiên bản hỗ trợ PostgreSQL module tương ứng. Không ghi version tùy tiện trùng hoặc xung đột với dependency management của dự án.

Ở bài này, **không cần `@EnableAsync`**: worker sẽ chạy bằng `@Scheduled`, còn dữ liệu công việc nằm trong PostgreSQL chứ không nằm trong queue RAM.

## 4. Chạy PostgreSQL và Mailpit ở local

Tệp `compose.yml` tham khảo:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: mail_demo
      POSTGRES_USER: mail_demo
      POSTGRES_PASSWORD: mail_demo
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mail_demo -d mail_demo"]
      interval: 5s
      timeout: 3s
      retries: 10

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"
      - "8025:8025"

volumes:
  postgres_data:
~~~

Chạy trong môi trường thực hành:

~~~bash
docker compose up -d
~~~

Mailpit lắng nghe SMTP tại `localhost:1025` và giao diện web tại `http://localhost:8025` khi ứng dụng chạy trên máy host. Dữ liệu và credentials trong ví dụ chỉ để **local development**, không dùng nguyên cấu hình này cho production.

### Vì sao dùng Mailpit?

Mailpit tiếp nhận các SMTP submissions để người học quan sát thư trong UI mà không gửi thật ra Internet. Trạng thái SENT trong database nên được hiểu là **SMTP test relay đã chấp nhận submission**, không phải bằng chứng email đã delivered tới inbox thật.

## 5. Cấu hình Spring Boot

Tệp `application.yml` tham khảo:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mail_demo
    username: mail_demo
    password: mail_demo

  flyway:
    enabled: true

  mail:
    host: localhost
    port: 1025
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000

app:
  mail:
    from: no-reply@example.test
    outbox:
      poll-ms: 1000
~~~

`app.mail.*` là cấu hình do ứng dụng tự đặt, không phải property tự động hiểu bởi Spring Mail. Local Mailpit thường không cần SMTP AUTH/TLS; **production phải dùng chính sách TLS/auth đúng theo provider**, không sao chép `auth: false` hoặc tắt STARTTLS cho một server công cộng.

Các timeouts quan trọng vì worker không được treo mãi trong một lời gọi SMTP. Nếu một attempt có thể kéo dài lâu hơn lease, job có nguy cơ bị worker khác reclaim và gửi trùng.

## 6. Bật scheduling

~~~java
package com.example.mailoutbox;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class MailOutboxApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailOutboxApplication.class,
                args
        );
    }
}
~~~

`@EnableScheduling` cho phép các method `@Scheduled` được gọi định kỳ. **Scheduling không thay transaction**: poller phải đọc từ database sau commit và mỗi lần claim cần một atomic database operation.

## 7. Migration: tạo bảng đơn hàng

Trong `V1__create_orders_and_mail_outbox.sql`, tạo bảng:

~~~sql
CREATE TABLE app_order (
    id UUID PRIMARY KEY,
    request_key VARCHAR(160) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_order_request_key
        UNIQUE (request_key),

    CONSTRAINT chk_order_positive_amount
        CHECK (total_amount > 0),

    CONSTRAINT chk_order_status
        CHECK (status IN ('CONFIRMED'))
);
~~~

Ở bản demo, một request tạo ngay một đơn hàng `CONFIRMED`; dự án thật có thể tách `DRAFT`, `PAID`, `CANCELED` và quy trình thanh toán riêng.

`request_key` là idempotency key ở tầng **HTTP tạo đơn hàng**. Nếu cùng request được gửi lại, không nên tạo đơn hàng mới. Nó khác với `idempotency_key` của email, dù hai khóa có liên hệ với nhau.

Không lưu thông tin thẻ ngân hàng, access token hoặc dữ liệu không cần thiết vào bảng này.

## 8. Migration: bảng mail_outbox

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES app_order(id),
    event_type VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(320) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    payload_json JSONB NOT NULL,

    status VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    claim_owner VARCHAR(160),
    claim_token UUID,
    claim_until TIMESTAMPTZ,

    last_error_code VARCHAR(80),
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_mail_outbox_idempotency
        UNIQUE (idempotency_key),

    CONSTRAINT chk_mail_outbox_status
        CHECK (status IN (
            'PENDING', 'SENDING', 'RETRY', 'SENT', 'DEAD'
        )),

    CONSTRAINT chk_mail_outbox_attempts
        CHECK (
            attempt_count >= 0
            AND max_attempts > 0
        )
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (
        status,
        next_attempt_at,
        created_at
    );

CREATE INDEX idx_mail_outbox_expired_claim
    ON mail_outbox (
        claim_until
    )
    WHERE status = 'SENDING';
~~~

Đây là PostgreSQL SQL. Trong production, có thể thêm tenant, priority, purpose, sender profile, template version, retention và partitioning, nhưng bài thực hành giữ scope gọn.

### Ý nghĩa các trường

| Cột | Mục đích |
| --- | --- |
| `id` | ID job duy nhất |
| `order_id` | Liên kết nghiệp vụ |
| `event_type` | Loại mail/event cần gửi |
| `idempotency_key` | Không enqueue hai lần cùng mail intent |
| `recipient_email` | Recipient snapshot của demo |
| `payload_json` | Dữ liệu cần dựng email |
| `status` | Trạng thái xử lý |
| `attempt_count` | Số lần claim để thử gửi |
| `max_attempts` | Ngưỡng dừng auto-retry |
| `next_attempt_at` | Thời điểm retry tiếp theo |
| `claim_owner` | Worker instance đã claim |
| `claim_token` | Fencing token cho lần claim |
| `claim_until` | Hạn lease để phục hồi crash |
| `last_error_code` | Category lỗi an toàn cho log/DB |
| `submitted_at` | Thời điểm SMTP relay báo accept |
| `created_at`, `updated_at` | Audit/scheduling |

**`SENT` trong demo được định nghĩa là submitted/accepted bởi SMTP transport**, không phải delivered. Có thể đổi tên thành `SUBMITTED` trong hệ thống production để tránh nhập nhằng.

## 9. Trạng thái và quy tắc chuyển trạng thái

~~~mermaid
flowchart TD
    A["PENDING"] --> B["SENDING"]
    B -->|"send() success"| C["SENT"]
    B -->|"retryable error"| D["RETRY"]
    B -->|"permanent error"| E["DEAD"]
    D --> B
    B -->|"lease expired"| F["Reclaim"]
    F --> B
    F -->|"attempts exhausted"| E
~~~

Quy tắc:

- `PENDING`: record đã được commit nhưng chưa claim.
- `SENDING`: worker đang giữ lease, có thể có SMTP attempt đang diễn ra.
- `RETRY`: thất bại, chờ `next_attempt_at`.
- `SENT`: `JavaMailSender.send` trả thành công và worker lưu kết quả.
- `DEAD`: không tiếp tục auto-retry; cần review/repair/replay theo quyền.
- Lease hết hạn không tự chứng minh job chưa được SMTP accept.
- Không có transaction ACID chung giữa `SENT` update và SMTP relay.

Bản demo dùng `DEAD` cho cả lỗi cấu hình và exhausted attempts; khi vận hành thật nên phân loại rõ **permanent failure**, **unknown outcome** và **manual intervention**.

## 10. Model request và snapshot cho email

Một request API:

~~~java
package com.example.mailoutbox.order;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

public record CreateOrderRequest(
        @NotBlank String requestKey,
        @Email @NotBlank String recipientEmail,
        @NotNull @DecimalMin("0.01")
        BigDecimal totalAmount,
        @NotBlank String currency
) {
}
~~~

Response:

~~~java
package com.example.mailoutbox.order;

import java.util.UUID;

public record CreateOrderResponse(
        UUID orderId,
        String emailStatus
) {
}
~~~

Snapshot mail:

~~~java
package com.example.mailoutbox.mail;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderMailPayload(
        UUID orderId,
        String recipientEmail,
        BigDecimal totalAmount,
        String currency
) {
}
~~~

`payload_json` giữ thông tin cần thiết để render một email xác nhận đơn hàng, tránh phụ thuộc hoàn toàn vào bản ghi domain có thể thay đổi sau commit. Trong production, cần giới hạn dữ liệu nhạy cảm, pin template version nếu có template engine và kiểm tra recipient/consent theo purpose.

### Vì sao phải có requestKey?

Một HTTP client có thể timeout sau khi server đã commit rồi gửi lại request. Nếu mỗi lần tạo UUID order mới mà không kiểm tra key, hệ thống có thể tạo **hai đơn hàng và hai mail intents**. Unique `request_key` chống trùng ở tầng đơn hàng; unique `mail_outbox.idempotency_key` chống trùng ở tầng mail.

Khi cùng key được gửi với payload khác, phải coi là **conflict**, không âm thầm trả đơn hàng cũ với dữ liệu không khớp.


## 11. Repository đơn hàng: insert idempotent

Model để đọc database:

~~~java
package com.example.mailoutbox.order;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderRow(
        UUID id,
        String requestKey,
        String recipientEmail,
        BigDecimal totalAmount,
        String currency,
        String status
) {
}
~~~

Repository dùng `JdbcTemplate`:

~~~java
package com.example.mailoutbox.order;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public class OrderRepository {

    private final JdbcTemplate jdbc;

    public OrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public OrderRow insertOrRead(
            CreateOrderRequest request) {

        UUID proposedId = UUID.randomUUID();

        jdbc.update(
            """
            INSERT INTO app_order (
                id, request_key, recipient_email,
                total_amount, currency, status
            )
            VALUES (?, ?, ?, ?, ?, 'CONFIRMED')
            ON CONFLICT (request_key) DO NOTHING
            """,
            proposedId,
            request.requestKey(),
            request.recipientEmail(),
            request.totalAmount(),
            request.currency()
        );

        return jdbc.query(
            """
            SELECT id, request_key, recipient_email,
                   total_amount, currency, status
            FROM app_order
            WHERE request_key = ?
            """,
            (rs, rowNum) -> new OrderRow(
                    rs.getObject("id", UUID.class),
                    rs.getString("request_key"),
                    rs.getString("recipient_email"),
                    rs.getBigDecimal("total_amount"),
                    rs.getString("currency"),
                    rs.getString("status")
            ),
            request.requestKey()
        ).stream().findFirst().orElseThrow();
    }
}
~~~

Trong PostgreSQL với transaction isolation thông thường `READ COMMITTED`:

- Lần đầu insert theo `request_key` sẽ tạo order mới.
- Lần sau cùng key, `ON CONFLICT DO NOTHING` không tạo thêm row.
- Phương thức đọc lại order theo key để trả cùng order ID.
- Nếu hai request cạnh tranh cùng key, unique constraint là lớp bảo vệ cuối cùng.

Ở isolation level khác hoặc khi có serialization failure, ứng dụng có thể cần retry transaction theo chính sách. Không biến câu `SELECT exists` rồi `INSERT` thành cơ chế chống race nếu thiếu unique constraint.

### Cùng requestKey nhưng payload khác

Phải kiểm tra dữ liệu đã có khớp request:

~~~java
private void requireSameRequest(
        OrderRow order,
        CreateOrderRequest request) {

    boolean same =
            order.recipientEmail()
                    .equals(request.recipientEmail())
            && order.totalAmount()
                    .compareTo(request.totalAmount()) == 0
            && order.currency()
                    .equals(request.currency());

    if (!same) {
        throw new IllegalArgumentException(
                "requestKey was reused with different data"
        );
    }
}
~~~

Phương thức này được đặt tại application service bên dưới. Trong production, cần chuẩn hóa inputs, tenant scope, authentication, anti-abuse và trả HTTP `409 Conflict` khi key bị tái sử dụng với payload khác.

## 12. Outbox writer: ghi mail intent cùng transaction

~~~java
package com.example.mailoutbox.mail;

import com.example.mailoutbox.order.OrderRow;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public class MailOutboxWriter {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public MailOutboxWriter(
            JdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public void enqueueOrderConfirmation(
            OrderRow order) {

        OrderMailPayload payload =
                new OrderMailPayload(
                        order.id(),
                        order.recipientEmail(),
                        order.totalAmount(),
                        order.currency()
                );

        String json;

        try {
            json = objectMapper.writeValueAsString(
                    payload
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize order mail intent",
                    ex
            );
        }

        String idempotencyKey =
                "order-confirmation:" + order.id();

        jdbc.update(
            """
            INSERT INTO mail_outbox (
                id, order_id, event_type,
                idempotency_key,
                recipient_email,
                payload_json, status,
                next_attempt_at
            )
            VALUES (
                ?, ?, 'ORDER_CONFIRMED',
                ?, ?,
                CAST(? AS jsonb),
                'PENDING', now()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            UUID.randomUUID(),
            order.id(),
            idempotencyKey,
            order.recipientEmail(),
            json
        );
    }
}
~~~

`ON CONFLICT DO NOTHING` làm thao tác enqueue idempotent theo event/recipient intent. Đây không phải cách ngăn mọi email trùng ở ranh giới SMTP; nó chỉ ngăn tạo **nhiều job logic** cho cùng order confirmation.

### Điểm quan trọng nhất

Trong repository này **không** có `@Async`, `mailSender.send(...)` hoặc gọi API bên ngoài. Đây là thao tác database bình thường để application service có thể kết hợp vào một transaction duy nhất.

Nếu JSON serialization thất bại, exception được ném ra ngoài; transaction của application service sẽ rollback theo cấu hình mặc định cho runtime exception.

## 13. Application service: commit cả order và outbox

~~~java
package com.example.mailoutbox.order;

import com.example.mailoutbox.mail.MailOutboxWriter;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxWriter outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxWriter outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID placeOrder(
            CreateOrderRequest request) {

        OrderRow order =
                orders.insertOrRead(request);

        requireSameRequest(order, request);

        outbox.enqueueOrderConfirmation(order);

        return order.id();
    }

    private void requireSameRequest(
            OrderRow order,
            CreateOrderRequest request) {

        boolean same =
                order.recipientEmail()
                        .equals(request.recipientEmail())
                && order.totalAmount()
                        .compareTo(
                                request.totalAmount()
                        ) == 0
                && order.currency()
                        .equals(request.currency());

        if (!same) {
            throw new IllegalArgumentException(
                    "requestKey was reused with different data"
            );
        }
    }
}
~~~

Khi `placeOrder` chạy qua Spring transaction proxy, cả `orders.insertOrRead(...)` và `outbox.enqueueOrderConfirmation(...)` sử dụng **cùng datasource và transaction manager**. Một lỗi trước commit khiến cả hai thao tác rollback.

Đây là **phần đảm bảo nguyên tử**:

~~~text
BEGIN

INSERT app_order
INSERT mail_outbox (PENDING)

COMMIT
~~~

Nếu chỉ thêm outbox trong callback `AFTER_COMMIT`, ta tạo lại khoảng crash window:

~~~text
COMMIT app_order
JVM crash trước INSERT mail_outbox
=> đơn hàng có, yêu cầu gửi biến mất
~~~

Nếu dùng `@TransactionalEventListener(AFTER_COMMIT)`, hãy dùng nó **chỉ để đánh thức poller** khi outbox row đã được ghi trong transaction, không thay thế việc ghi row.

## 14. HTTP controller: trả trạng thái đúng

~~~java
package com.example.mailoutbox.order;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderApplicationService service;

    public OrderController(
            OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CreateOrderResponse> create(
            @Valid @RequestBody
            CreateOrderRequest request) {

        UUID id = service.placeOrder(request);

        return ResponseEntity.ok(
                new CreateOrderResponse(
                        id,
                        "MAIL_INTENT_RECORDED"
                )
        );
    }
}
~~~

Trong ví dụ, response `200 OK` thuận tiện cho cả request đầu và retry cùng idempotency key; nếu API cần phân biệt resource vừa tạo với replay, có thể trả `201 Created` cho lần đầu, `200 OK` cho lần lặp. Endpoint production cũng cần authentication, tenant scope và mapping `409` cho request-key conflict.

**`MAIL_INTENT_RECORDED` không có nghĩa SMTP đã gửi.** Nó chỉ nói transaction đã hoàn tất với outbox intent được ghi nhận.

### Thử gọi API

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "checkout-req-001",
    "recipientEmail": "buyer@example.test",
    "totalAmount": 250000.00,
    "currency": "VND"
  }'
~~~

Phản hồi minh họa:

~~~json
{
  "orderId": "5c5b0d1d-b4e7-4ee6-a8ce-7cc398a92011",
  "emailStatus": "MAIL_INTENT_RECORDED"
}
~~~

UUID là dữ liệu minh họa. Nếu gọi lại **cùng requestKey và cùng payload**, service trả cùng order ID và không tạo thêm mail intent nhờ hai unique constraints.

## 15. Quan sát transaction commit trong PostgreSQL

Sau khi gọi API, query:

~~~sql
SELECT id, request_key, recipient_email, status
FROM app_order
ORDER BY created_at DESC
LIMIT 5;
~~~

Và:

~~~sql
SELECT id, order_id, event_type,
       status, attempt_count,
       next_attempt_at, submitted_at
FROM mail_outbox
ORDER BY created_at DESC
LIMIT 5;
~~~

Nếu worker đang chạy nhanh, status có thể đã là `SENT` thay vì `PENDING` khi bạn xem. Để quan sát trạng thái ban đầu, có thể tạm tắt worker trong **môi trường demo** hoặc cấu hình poll interval lớn hơn trước khi gọi API.

Không dùng trạng thái mail outbox để chứng minh email đã delivered; tại đây chỉ có local Mailpit SMTP submission.

## 16. Vì sao row PENDING chỉ được worker thấy sau commit?

Với PostgreSQL ở isolation level `READ COMMITTED` thông thường, transaction khác chỉ nhìn thấy các row đã commit.

~~~text
HTTP transaction:
  BEGIN
  INSERT app_order
  INSERT mail_outbox PENDING
  ... chưa commit

Worker transaction:
  SELECT ... WHERE status='PENDING'
  => chưa thấy row chưa commit

HTTP transaction:
  COMMIT

Worker transaction:
  SELECT ...
  => thấy row và có thể claim
~~~

Đây là lý do **không cần gửi SMTP ngay trong HTTP transaction**. Poller có thể chạy sẵn, nhưng nó chỉ lấy những outbox rows đã durable.

Lưu ý: nếu cố gửi local event để worker chạy quá sớm, worker có thể chưa thấy row trong transaction chưa commit. Đừng biến timing event thành điều kiện đúng/sai của hệ thống; database outbox mới là nguồn sự thật.

## 17. Ranh giới chống lỗi khi transaction rollback

Giả sử một business validation lỗi sau khi cả hai INSERT được gọi:

~~~java
@Transactional
public UUID placeOrderAndFail(
        CreateOrderRequest request) {

    OrderRow order =
            orders.insertOrRead(request);

    outbox.enqueueOrderConfirmation(order);

    throw new IllegalStateException(
            "Simulated failure"
    );
}
~~~

Đây là **một test seam minh họa** đặt trong bean được gọi từ bên ngoài qua Spring proxy; không phải method cần đưa vào API production. Vì runtime exception thoát ra khỏi transaction:

~~~text
ROLLBACK:
  app_order INSERT bị rollback
  mail_outbox INSERT bị rollback
  worker không thấy job
~~~

Nếu bạn viết một phương thức `@Transactional` rồi tự gọi qua `this.placeOrderAndFail(...)` trong cùng class, proxy-based transaction có thể không được áp như mong đợi. Hãy kiểm thử ranh giới bằng bean/service thực hoặc `TransactionTemplate`.

### Vì sao không dùng REQUIRES_NEW cho outbox?

Nếu outbox writer dùng `REQUIRES_NEW`:

~~~text
Outer business transaction chưa commit
  -> inner outbox transaction commit
  -> outer business transaction rollback
~~~

thì worker có thể nhận mail intent cho một đơn hàng không tồn tại. **Outbox phải ở cùng transaction**, không được vô tình commit độc lập với business state.


## 18. Model job mà worker nhận

Worker không nên cần nhận một `ResultSet` hoặc entity mutable đang mở transaction khi gửi mail. Hãy map những trường cần thiết sang một record bất biến:

~~~java
package com.example.mailoutbox.mail;

import java.util.UUID;

public record ClaimedMailJob(
        UUID id,
        UUID orderId,
        String recipientEmail,
        String payloadJson,
        UUID claimToken,
        int attemptCount,
        int maxAttempts
) {
}
~~~

Job này có `claimToken` gắn riêng với **lần claim hiện tại**. Nó khác `idempotencyKey`:

- `idempotencyKey` không thay đổi giữa các request/retries của cùng intent.
- `claimToken` phải thay đổi mỗi lần worker mới claim hoặc reclaim.
- `attemptCount` được tăng khi bắt đầu một claim/attempt theo contract demo.
- `maxAttempts` giới hạn auto-retry; không chứng minh thư đã gửi hay chưa.

Không đặt toàn bộ MIME bytes/attachment vào đối tượng queued in-memory để tránh làm worker phình heap.

## 19. Claim job an toàn khi có nhiều worker

Nếu chỉ viết:

~~~java
List<Job> jobs =
        repository.findByStatus("PENDING");

for (Job job : jobs) {
    mailSender.send(...);
}
~~~

hai JVM có thể đọc cùng một row và cùng gửi. Cần **atomic claim** bằng transaction/lock/conditional update.

Với PostgreSQL, `FOR UPDATE SKIP LOCKED` cho phép một worker lấy job không bị worker khác khóa:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        (
            status IN ('PENDING', 'RETRY')
            AND next_attempt_at <= now()
        )
        OR (
            status = 'SENDING'
            AND claim_until < now()
        )
    )
      AND attempt_count < max_attempts
    ORDER BY next_attempt_at, created_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE mail_outbox AS o
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    claim_owner = :worker_id,
    claim_token = :token,
    claim_until = now() + interval '2 minutes',
    updated_at = now()
FROM picked
WHERE o.id = picked.id
RETURNING
    o.id, o.order_id, o.recipient_email,
    o.payload_json::text AS payload_json,
    o.claim_token, o.attempt_count, o.max_attempts;
~~~

**Ý nghĩa:**

1. Chọn một job đã đến hạn hoặc một job `SENDING` có lease hết hạn.
2. Bỏ qua row đang bị transaction khác lock.
3. Tăng attempt count và cấp owner/token/lease mới.
4. Trả thông tin của job vừa claim.
5. Commit claim trước khi SMTP send.

`SKIP LOCKED` là khả năng đặc thù SQL/database, không mặc định portable cho mọi DB. Khi dùng MySQL, SQL Server hoặc nền tảng khác, cần điều chỉnh cơ chế claim phù hợp.

### Vì sao cần lease?

Nếu worker chết sau claim nhưng trước khi ghi kết quả:

~~~text
Worker A claim job, status=SENDING
Worker A crash
Không có lease:
  job kẹt SENDING mãi

Có lease:
  sau claim_until, Worker B có thể reclaim
~~~

Tuy nhiên, lease không loại bỏ hoàn toàn double send: worker cũ có thể bị pause rồi thức dậy sau khi lease đã hết hạn; nếu nó đã submit SMTP, external effect có thể xảy ra dù DB fencing ngăn nó update row.

## 20. Repository claim trong một transaction ngắn

~~~java
package com.example.mailoutbox.mail;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Repository
public class MailOutboxClaimer {

    private final NamedParameterJdbcTemplate jdbc;

    public MailOutboxClaimer(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<ClaimedMailJob> claimOne(
            String workerId) {

        UUID token = UUID.randomUUID();

        String sql = """
            WITH picked AS (
                SELECT id
                FROM mail_outbox
                WHERE (
                    (
                        status IN ('PENDING', 'RETRY')
                        AND next_attempt_at <= now()
                    )
                    OR (
                        status = 'SENDING'
                        AND claim_until < now()
                    )
                )
                  AND attempt_count < max_attempts
                ORDER BY next_attempt_at, created_at, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE mail_outbox AS o
            SET status = 'SENDING',
                attempt_count = attempt_count + 1,
                claim_owner = :workerId,
                claim_token = :token,
                claim_until =
                    now() + interval '2 minutes',
                updated_at = now()
            FROM picked
            WHERE o.id = picked.id
            RETURNING
                o.id, o.order_id, o.recipient_email,
                o.payload_json::text AS payload_json,
                o.claim_token, o.attempt_count,
                o.max_attempts
            """;

        List<ClaimedMailJob> rows =
                jdbc.query(
                    sql,
                    Map.of(
                        "workerId", workerId,
                        "token", token
                    ),
                    (rs, index) ->
                        new ClaimedMailJob(
                            rs.getObject(
                                "id", UUID.class
                            ),
                            rs.getObject(
                                "order_id", UUID.class
                            ),
                            rs.getString(
                                "recipient_email"
                            ),
                            rs.getString(
                                "payload_json"
                            ),
                            rs.getObject(
                                "claim_token", UUID.class
                            ),
                            rs.getInt(
                                "attempt_count"
                            ),
                            rs.getInt(
                                "max_attempts"
                            )
                        )
                );

        return rows.stream().findFirst();
    }
}
~~~

### Transaction boundary cần chính xác

`claimOne` chạy qua Spring bean/proxy với `@Transactional`. SQL update và row lock nằm trong một DB transaction ngắn. Sau khi method trả và transaction được commit, worker mới bắt đầu network I/O.

**Không** viết:

~~~java
@Transactional
public void claimAndSend() {
    Job job = claimOne();
    mailSender.send(...);
    markSent(...);
}
~~~

Điều đó giữ transaction/locks xuyên SMTP request và không biến SMTP thành resource rollback được. Nếu network treo, database có thể bị contention và timeout.

### Vì sao claim một job mỗi lần?

Bản demo claim từng job để `claim_until` bắt đầu gần thời điểm gửi, tránh claim một batch lớn rồi các job chờ trong RAM hết lease trước khi được xử lý. Khi mở rộng, có thể claim batch tương ứng với available worker capacity, không claim vô hạn.

## 21. Fencing token khi ghi kết quả

Khi worker gửi xong, không được update status chỉ bằng `id`:

~~~sql
UPDATE mail_outbox
SET status = 'SENT'
WHERE id = :job_id;
~~~

Vì worker A có thể đã mất lease và worker B vừa reclaim cùng job. A thức dậy muộn sẽ ghi đè trạng thái của B.

Cần match **job ID + current claim token + status SENDING**:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    submitted_at = now(),
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now(),
    last_error_code = NULL
WHERE id = :job_id
  AND claim_token = :token
  AND status = 'SENDING';
~~~

Nếu số row updated bằng 0, worker không còn sở hữu current claim hoặc trạng thái đã đổi.

**Fencing chỉ ngăn stale DB updates**, không thể “thu hồi” email mà worker A đã gửi qua SMTP. Đây là giới hạn cố hữu giữa database và external side effect.

## 22. Result writer: SENT, RETRY và DEAD

~~~java
package com.example.mailoutbox.mail;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;
import java.util.UUID;

@Service
public class MailOutboxResultWriter {

    private final JdbcTemplate jdbc;

    public MailOutboxResultWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean markSent(ClaimedMailJob job) {

        int updated = jdbc.update(
            """
            UPDATE mail_outbox
            SET status = 'SENT',
                submitted_at = now(),
                claim_owner = NULL,
                claim_token = NULL,
                claim_until = NULL,
                last_error_code = NULL,
                updated_at = now()
            WHERE id = ?
              AND claim_token = ?
              AND status = 'SENDING'
            """,
            job.id(),
            job.claimToken()
        );

        return updated == 1;
    }

    @Transactional
    public boolean markFailed(
            ClaimedMailJob job,
            String safeErrorCode,
            boolean permanent) {

        boolean exhausted =
                job.attemptCount()
                        >= job.maxAttempts();

        String nextStatus =
                permanent || exhausted
                        ? "DEAD"
                        : "RETRY";

        Instant nextAttempt =
                Instant.now()
                        .plusSeconds(
                                backoffSeconds(
                                    job.attemptCount()
                                )
                        );

        int updated = jdbc.update(
            """
            UPDATE mail_outbox
            SET status = ?,
                next_attempt_at = ?,
                last_error_code = ?,
                claim_owner = NULL,
                claim_token = NULL,
                claim_until = NULL,
                updated_at = now()
            WHERE id = ?
              AND claim_token = ?
              AND status = 'SENDING'
            """,
            nextStatus,
            Timestamp.from(nextAttempt),
            safeErrorCode,
            job.id(),
            job.claimToken()
        );

        return updated == 1;
    }

    private long backoffSeconds(
            int attemptCount) {

        int exponent =
                Math.min(
                    Math.max(attemptCount - 1, 0),
                    6
                );

        long base =
                Math.min(
                    30L * (1L << exponent),
                    1800L
                );

        long jitter =
                ThreadLocalRandom.current()
                        .nextLong(0L, 16L);

        return base + jitter;
    }
}
~~~

Trong bản demo, `markFailed` tự chọn `RETRY` hoặc `DEAD` theo `permanent` và số attempts. `next_attempt_at` của DEAD không còn được dùng; production có thể để null hoặc tách column theo state contract.

`safeErrorCode` phải là category có kiểm soát, ví dụ `SMTP_TEMPORARY`, `SMTP_AUTH`, `INVALID_PAYLOAD`. Không đưa toàn bộ exception message, email body hoặc credential vào DB để tránh lộ dữ liệu nhạy cảm.

### Failure của result writer

Nếu SMTP đã accept nhưng `markSent` không commit vì DB outage:

~~~text
SMTP accepted
DB unavailable khi markSent
lease expires
worker retries
=> Có thể gửi trùng
~~~

Điều đó không thể sửa bằng cách đơn giản “gọi markSent trước khi send”, vì đảo thứ tự lại có nguy cơ mất email. Outbox đưa ra khả năng phục hồi tốt hơn, chứ không tạo exactly-once SMTP.

## 23. Worker cần phân loại lỗi chứ không retry mọi thứ

Với Spring Mail:

| Lỗi | Xử lý thực hành | Lưu ý production |
| --- | --- | --- |
| SMTP temporary failure | RETRY + backoff | Xem SMTP reply/enhanced status |
| `MailAuthenticationException` | DEAD/hold và alert | Không retry nóng password sai |
| `MailSendException` | Có thể retry, ghi diagnostics | Outcome đôi khi không chắc sau DATA |
| MIME preparation failure | DEAD/repair payload | Có thể chưa gọi SMTP |
| JSON payload không parse được | DEAD/manual repair | Không gửi content sai |
| Attachment tạm unavailable | RETRY nếu còn TTL | Tránh mất file trước retry |
| Invalid recipient vĩnh viễn | DEAD/suppression | Phân loại theo provider |
| SMTP accepted, result DB update lỗi | Lease/retry; có thể trùng | Audit unknown outcome |

`MailSendException#getFailedMessages()` có thể chứa map message → exception, nhưng không phải chứng cứ delivery; map rỗng cũng không đồng nghĩa không có lỗi. Một exception timeout sau khi gửi xong SMTP `DATA` có thể là **unknown outcome**, không chắc relay chưa nhận thư.

Bản demo dưới đây xử lý phần lớn `MailException` như retryable để nhìn thấy cơ chế phục hồi, nhưng khi triển khai production phải xây classifier theo lỗi/per-recipient/provider contract, thay vì đồng nhất mọi exception với một trạng thái.

## 24. Processor: dựng MIME và gửi ngoài transaction claim

~~~java
package com.example.mailoutbox.mail;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OutboxEmailProcessor {

    private static final Logger log =
            LoggerFactory.getLogger(
                    OutboxEmailProcessor.class
            );

    private final ObjectMapper mapper;
    private final JavaMailSender sender;
    private final MailOutboxResultWriter results;
    private final String fromAddress;

    public OutboxEmailProcessor(
            ObjectMapper mapper,
            JavaMailSender sender,
            MailOutboxResultWriter results,
            @Value("${app.mail.from}")
            String fromAddress) {

        this.mapper = mapper;
        this.sender = sender;
        this.results = results;
        this.fromAddress = fromAddress;
    }

    public void process(ClaimedMailJob job) {

        OrderMailPayload payload;

        try {
            payload = mapper.readValue(
                    job.payloadJson(),
                    OrderMailPayload.class
            );
        } catch (JsonProcessingException ex) {
            results.markFailed(
                    job,
                    "INVALID_PAYLOAD",
                    true
            );
            return;
        }

        try {
            MimeMessage message =
                    composeMessage(job, payload);

            sender.send(message);

        } catch (MailAuthenticationException ex) {
            results.markFailed(
                    job,
                    "SMTP_AUTH",
                    true
            );
            return;

        } catch (MailSendException ex) {
            log.warn(
                    "Mail job {} submission failed; " +
                    "failedMessages={}",
                    job.id(),
                    ex.getFailedMessages().size()
            );

            results.markFailed(
                    job,
                    "SMTP_SEND_OR_UNKNOWN",
                    false
            );
            return;

        } catch (MailException ex) {
            results.markFailed(
                    job,
                    "SMTP_TRANSPORT",
                    false
            );
            return;

        } catch (MessagingException ex) {
            results.markFailed(
                    job,
                    "MIME_PREPARATION",
                    true
            );
            return;
        }

        boolean saved = results.markSent(job);

        if (!saved) {
            log.warn(
                    "SMTP accepted but claim no longer " +
                    "matches; jobId={}",
                    job.id()
            );
        }
    }

    private MimeMessage composeMessage(
            ClaimedMailJob job,
            OrderMailPayload payload)
            throws MessagingException {

        MimeMessage mime =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        mime,
                        false,
                        "UTF-8"
                );

        helper.setFrom(fromAddress);
        helper.setTo(payload.recipientEmail());

        helper.setSubject(
                "Xác nhận đơn hàng "
                + payload.orderId()
        );

        helper.setText(
                "Đơn hàng " + payload.orderId()
                + " đã được xác nhận. Tổng tiền: "
                + payload.totalAmount()
                + " " + payload.currency(),
                false
        );

        mime.setHeader(
                "X-Mail-Job-Id",
                job.id().toString()
        );

        return mime;
    }
}
~~~

Đây là **sample implementation có giới hạn**. Trong production cần validate payload và recipient một cách đầy đủ trước `sender.send`, tách error classifier, áp per-tenant sender policy, kiểm soát size/MIME, không dùng HTML chưa escape và xử lý rõ `UNKNOWN_OUTCOME`.

### Vì sao không bọc process() bằng @Transactional?

`process` có network I/O. Nếu bọc toàn bộ bằng `@Transactional`, transaction có thể giữ lâu trong lúc SMTP chậm. Các transaction cần ngắn và nằm tại **claim** và **ghi kết quả**.

`MailOutboxResultWriter` là bean riêng để `@Transactional` có thể áp qua Spring proxy. Không tự gọi method transactional bằng `this.method()` rồi nghĩ transaction luôn được tạo trong proxy-based setup.

## 25. Scheduled worker: poll từng job đã commit

~~~java
package com.example.mailoutbox.mail;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.UUID;

@Component
public class OutboxPollingWorker {

    private final MailOutboxClaimer claimer;
    private final OutboxEmailProcessor processor;
    private final MailOutboxResultWriter results;

    private final String workerId =
            UUID.randomUUID().toString();

    public OutboxPollingWorker(
            MailOutboxClaimer claimer,
            OutboxEmailProcessor processor,
            MailOutboxResultWriter results) {

        this.claimer = claimer;
        this.processor = processor;
        this.results = results;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.outbox.poll-ms:1000}"
    )
    public void poll() {

        results.reapExhaustedClaims();

        for (int index = 0; index < 10; index++) {

            Optional<ClaimedMailJob> next =
                    claimer.claimOne(workerId);

            if (next.isEmpty()) {
                return;
            }

            processor.process(next.get());
        }
    }
}
~~~

`workerId` là identity của process instance trong demo. Trong production nên có instance ID có thể truy vết qua deployment/pod, không chia một owner ID cho nhiều JVM không liên quan.

Vòng lặp claim **mỗi lần một job** rồi xử lý ngay, tránh giữ lease của quá nhiều job đang xếp hàng. Không có memory queue lớn; DB vẫn giữ các công việc chưa claim.

`reapExhaustedClaims()` được bổ sung ở bước tiếp theo để xử lý trường hợp worker crash đúng ở attempt cuối.


## 26. Reaper: xử lý lease hết hạn ở attempt cuối

Trong claim SQL có điều kiện `attempt_count < max_attempts`. Giả sử worker claim attempt thứ năm trong số năm attempts rồi crash trước khi ghi kết quả. Sau khi lease hết hạn:

~~~text
status = SENDING
attempt_count = 5
max_attempts = 5
claim_until < now()
~~~

Job không còn đủ điều kiện claim và có thể kẹt vĩnh viễn nếu không có reaper. Bổ sung phương thức dưới đây vào `MailOutboxResultWriter`:

~~~java
@Transactional
public int reapExhaustedClaims() {

    return jdbc.update(
        """
        UPDATE mail_outbox
        SET status = 'DEAD',
            last_error_code =
                'LEASE_EXPIRED_AT_MAX_ATTEMPTS',
            claim_owner = NULL,
            claim_token = NULL,
            claim_until = NULL,
            updated_at = now()
        WHERE status = 'SENDING'
          AND claim_until < now()
          AND attempt_count >= max_attempts
        """
    );
}
~~~

**Cực kỳ quan trọng:** `DEAD` ở đây có nghĩa **đã hết chính sách auto-retry**, chứ không chứng minh email chắc chắn chưa được gửi. Worker có thể đã gửi tới SMTP relay rồi crash trước khi cập nhật DB. Tình huống này nên được đưa vào hàng đợi/manual dashboard để đối soát; một hệ thống production có thể dùng status riêng `UNKNOWN_OUTCOME`.

Nếu reaper được gọi mỗi giây trong nhiều replicas, hãy giới hạn batch/rate và giám sát lock contention khi volume lớn. Bản demo dùng một câu update đơn giản để thể hiện semantics.

## 27. Trình tự chạy thực hành

Với các file đã tạo ở trên:

1. Khởi động PostgreSQL và Mailpit bằng Docker Compose.
2. Khởi động ứng dụng Spring Boot để Flyway chạy migration và worker bắt đầu polling.
3. Gửi POST tạo đơn hàng.
4. Đọc kết quả trong PostgreSQL.
5. Quan sát email trong Mailpit UI.
6. Gửi lại cùng request key.
7. Thử mô phỏng SMTP offline và retry.
8. Thử rollback bằng một test seam.
9. Quan sát lease khi worker bị dừng.
10. Kiểm tra không có mail intent cho transaction rollback.

Lệnh khởi động môi trường local:

~~~bash
docker compose up -d
~~~

Khởi động Spring Boot bằng cách phù hợp build tool của dự án, ví dụ từ IDE hoặc task run của dự án. Việc này là **hướng dẫn người học**, không phải một bước phụ thuộc vào môi trường bài viết.

### Gọi API

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "order-demo-476",
    "recipientEmail": "learner@example.test",
    "totalAmount": 125000,
    "currency": "VND"
  }'
~~~

Nếu ứng dụng và Mailpit đều hoạt động, một message xác nhận đơn hàng sẽ xuất hiện trong UI Mailpit ở `http://localhost:8025`.

### Query database

~~~sql
SELECT
    o.id AS order_id,
    o.request_key,
    o.status AS order_status,
    m.id AS mail_job_id,
    m.status AS mail_status,
    m.attempt_count,
    m.last_error_code,
    m.submitted_at
FROM app_order AS o
JOIN mail_outbox AS m
    ON m.order_id = o.id
WHERE o.request_key = 'order-demo-476';
~~~

Kỳ vọng sau khi Mailpit accept và result writer commit:

~~~text
order_status: CONFIRMED
mail_status: SENT
attempt_count: 1
last_error_code: null
submitted_at: timestamp
~~~

Nếu worker chưa chạy, status ban đầu có thể là `PENDING`. Nếu SMTP đang offline, status có thể là `RETRY`. Đây là những trạng thái hợp lệ theo thời điểm quan sát.

## 28. Thử lại cùng requestKey

Gửi lại chính request:

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "order-demo-476",
    "recipientEmail": "learner@example.test",
    "totalAmount": 125000,
    "currency": "VND"
  }'
~~~

Kết quả mong muốn:

- Không sinh order mới.
- Trả cùng order ID.
- Không tạo outbox job mới.
- Không có “một email mới chỉ vì HTTP client retry”, trừ khi job cũ còn đang chạy/retry theo chính sách.

Kiểm tra:

~~~sql
SELECT COUNT(*)
FROM app_order
WHERE request_key = 'order-demo-476';
~~~

Kỳ vọng là `1`.

~~~sql
SELECT COUNT(*)
FROM mail_outbox
WHERE order_id = (
    SELECT id
    FROM app_order
    WHERE request_key = 'order-demo-476'
);
~~~

Kỳ vọng cũng là `1`.

### Cùng key nhưng payload khác

Gửi lại `order-demo-476` với `totalAmount` hoặc `recipientEmail` khác nên bị từ chối. Trong code ví dụ, service ném `IllegalArgumentException`. Với API production, nên dùng một exception riêng `IdempotencyKeyConflictException` và map sang HTTP `409 Conflict`, không trả order cũ im lặng.

Một key phải được scoped theo actor/tenant khi ứng dụng có nhiều khách hàng; không để tenant khác có thể đoán requestKey và truy cập order của tenant A.

## 29. Thử SMTP offline: outbox vẫn bền vững

Trong local demo, dừng Mailpit:

~~~bash
docker compose stop mailpit
~~~

Gửi một request **mới với requestKey mới**:

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "order-smtp-offline",
    "recipientEmail": "offline@example.test",
    "totalAmount": 90000,
    "currency": "VND"
  }'
~~~

Ngay cả khi SMTP test server không chạy, transaction order/outbox vẫn có thể commit:

~~~sql
SELECT
    o.request_key,
    m.status,
    m.attempt_count,
    m.next_attempt_at,
    m.last_error_code
FROM app_order AS o
JOIN mail_outbox AS m
    ON m.order_id = o.id
WHERE o.request_key = 'order-smtp-offline';
~~~

Sau worker thử gửi thất bại, có thể thấy:

~~~text
request_key       = order-smtp-offline
status            = RETRY
attempt_count     = 1
next_attempt_at   = thời điểm tương lai
last_error_code   = SMTP_SEND_OR_UNKNOWN
                 hoặc SMTP_TRANSPORT
~~~

HTTP service không phụ thuộc việc SMTP đang sẵn sàng để lưu business state. Đây là lợi ích quan trọng của outbox so với gọi `send(...)` trực tiếp trong request.

Khởi động lại Mailpit:

~~~bash
docker compose start mailpit
~~~

Khi `next_attempt_at` đến hạn, worker sẽ claim lại và thử gửi. Nếu được relay accept, status chuyển `SENT`.

**Lưu ý:** Không dừng SMTP quá lâu đến mức job vượt `max_attempts` rồi trở thành `DEAD`. Khi đó bài tập cần thao tác replay có kiểm soát thay vì chờ auto-retry.

## 30. Thử rollback: không có mail intent

Thêm một test seam hoặc cấu hình fault injection trong môi trường test để ném runtime exception **trước commit**, sau khi cả order và outbox đã được insert trong transaction.

Sau đó kiểm tra:

~~~sql
SELECT COUNT(*)
FROM app_order
WHERE request_key = 'order-force-rollback';
~~~

Kỳ vọng `0`.

~~~sql
SELECT COUNT(*)
FROM mail_outbox
WHERE idempotency_key LIKE 'order-confirmation:%';
~~~

Không nên dùng tổng count của toàn bảng để kết luận rollback nếu trước đó đã có nhiều mail jobs. Cần truy vết job/request test một cách riêng biệt, ví dụ transaction fixture biết chính xác order ID dự kiến hoặc test tạo database sạch.

### Vì sao test rollback quan trọng hơn việc kiểm tra response 500?

Một HTTP 500 chỉ cho biết request thất bại ở phía ứng dụng. Nó không tự chứng minh:

- Database đã rollback.
- Outbox row cũng rollback.
- Worker chưa kịp gửi mail.
- Không có mail intent đã commit ở transaction khác.

Integration test phải đọc **cả business state và outbox state** từ database thật sau khi transaction kết thúc.

## 31. Thử worker crash sau claim

Một tình huống thực hành:

~~~text
1. Mail job ở PENDING.
2. Worker claim -> SENDING.
3. Worker bị dừng đột ngột trước khi gửi hoặc ghi kết quả.
4. Database vẫn có status SENDING.
5. claim_until đi qua.
6. Worker khác khởi động và claim lại job.
~~~

Quan sát:

~~~sql
SELECT
    id,
    status,
    attempt_count,
    claim_owner,
    claim_token,
    claim_until
FROM mail_outbox
ORDER BY created_at DESC
LIMIT 10;
~~~

Nếu worker bị kill ngay sau khi SMTP relay accept nhưng trước `markSent`, job có thể bị gửi lại sau lease expiry. Đây là **expected limitation** cần chấp nhận và theo dõi.

Không thử crash/kill trên dữ liệu người dùng thật. Dùng test SMTP và database cô lập để tránh gửi trùng mail production.

## 32. Tại sao worker không giữ DB transaction khi SMTP gửi?

Giả sử một SMTP request mất 20 giây. Nếu toàn bộ gửi nằm trong transaction:

~~~text
BEGIN
SELECT/UPDATE outbox row
mailSender.send(...) mất 20 giây
UPDATE outbox result
COMMIT
~~~

thì transaction có thể giữ row lock/connection quá lâu. Trong lúc đó các worker khác khó claim batch và ứng dụng có thể gây contention.

Thiết kế đúng hơn:

~~~text
Transaction A:
  claim row + token
  COMMIT

Outside DB transaction:
  compose/send via SMTP

Transaction B:
  update result WHERE id AND claim_token
  COMMIT
~~~

Ranh giới này làm rõ failure: crash giữa A và B tạo một lease có thể phục hồi. Không có transaction phân tán với SMTP; vì thế worker phải chấp nhận retries và duplicate window.

## 33. Outbox idempotency khác SMTP exactly-once

Hãy tách ba loại định danh:

| ID | Mục đích |
| --- | --- |
| `request_key` | Không tạo nhiều đơn hàng từ HTTP retry |
| `mail_outbox.idempotency_key` | Không tạo nhiều job mail cùng một ý định |
| `claim_token` | Chặn worker cũ ghi đè DB state |
| `mail_outbox.id` | Tracing mail job |
| `Message-ID`/correlation header | Tìm message trong logs/provider |
| Provider message ID | Đối soát submission/delivery feedback |

Unique constraint giải quyết duplicate **enqueue**. Lease token giải quyết stale **DB updates**. Không cơ chế nào trong hai cơ chế đó buộc SMTP relay phải reject duplicate messages.

Crash window:

~~~text
JavaMailSender.send returns success
  -> SMTP has accepted
  -> JVM crashes
  -> SENT update not persisted
  -> worker reclaims
  -> SMTP receives another submission
~~~

Đảo thứ tự mark SENT trước gửi sẽ tạo nguy cơ **mất email** nếu crash sau mark nhưng trước submission.

Vì vậy, cam kết phù hợp là **durable intent + at-least-once submission attempts khi retry được phép**, không phải “email chắc chắn tới inbox đúng một lần”. Người nhận có thể nhận trùng, email có thể bị provider deferred/bounced và delivery phải được theo dõi riêng.

## 34. Unknown outcome sau SMTP DATA

SMTP có thể nhận trọn message và phản hồi thành công, nhưng response không tới được client:

~~~text
Client sends DATA
Relay accepts message
Network disconnects
Client observes timeout
~~~

Không có đủ bằng chứng để khẳng định relay chưa nhận. Nếu retry, có khả năng gửi trùng. Nếu bỏ qua retry, có khả năng bỏ sót mail chưa được nhận.

Production nên có trạng thái hoặc failure category `UNKNOWN_OUTCOME` và đối soát qua provider API/message ID nếu khả dụng, đồng thời có chính sách theo purpose:

- OTP: không gửi token hết hạn.
- Biên nhận: có thể cho retry và hỗ trợ “resend” có audit.
- Marketing: kiểm tra consent/suppression trước retry.
- Cảnh báo bảo mật: có thể cần kênh thay thế/escalation.
- Thông báo nội bộ: có thể chấp nhận duplicate nếu nội dung idempotent.

Trong demo, mã `SMTP_SEND_OR_UNKNOWN` cố ý thừa nhận không chắc kết quả; khi mở rộng cần classifier tốt hơn, không gộp mọi `MailSendException` thành transient.

## 35. Tại sao cần retry có backoff?

Nếu provider đang offline mà 5.000 workers retry liên tục, hệ thống có thể:

- Tạo network connection storm.
- Làm đầy logs và DB writes.
- Vượt SMTP provider quota.
- Khi provider quay lại, gửi burst quá lớn.
- Khiến account bị throttled hoặc lock.
- Đẩy chậm các jobs khác.

`MailOutboxResultWriter` dùng exponential backoff + jitter. Một ví dụ lịch:

~~~text
attempt 1 -> retry khoảng 30-45 giây
attempt 2 -> retry khoảng 60-75 giây
attempt 3 -> retry khoảng 120-135 giây
attempt 4 -> retry khoảng 240-255 giây
...
~~~

Jitter phân tán thời điểm retry giữa các job. Trong production, áp:

- Rate limit theo SMTP account/provider.
- Retry-After khi provider có contract hỗ trợ.
- Hard cutoff theo attempts hoặc tuổi job.
- TTL nội dung/token.
- Error categories permanent/temporary/unknown.
- Fair scheduling theo tenant/purpose.
- Circuit breaker hoặc hold account khi lỗi AUTH hàng loạt.

Không dùng một vòng `while(true)` gọi `mailSender.send` ngay sau mọi exception.

## 36. Vì sao cần tách per-recipient job?

Demo tạo **một order → một outbox job → một recipient**. Đây là lựa chọn có chủ đích.

Nếu một `MimeMessage` gửi tới A, B và C, SMTP có thể accept một phần recipients rồi reject phần khác. Retry toàn bộ có thể gây duplicate cho người đã accept.

Một job/recipient giúp:

- Idempotency key rõ theo order/event/recipient.
- Theo dõi attempts riêng.
- Không lộ địa chỉ của người nhận khác qua To/Cc.
- Áp unsubscribe/suppression riêng.
- Tách quota và retry.
- Đối soát provider delivery feedback.

Với email nhiều người nhận, phải thiết kế recipient-level outcome và SMTP partial-send semantics. Không xem một `MailSendException#getFailedMessages()` như danh sách xác nhận delivery cho từng recipient.

## 37. Nhiều replica chạy cùng lúc

Khi tăng từ một process thành ba replicas:

~~~text
Worker A  -> database
Worker B  -> database
Worker C  -> database
~~~

Tất cả có thể poll cùng bảng, nhưng atomic claim + `SKIP LOCKED` giúp mỗi row có một current DB owner/lease trong lúc claim.

Cần chú ý:

- Worker ID phải phân biệt instances.
- Claim batch không vượt available executor capacity.
- Lease timeout dài hơn thời gian xử lý dự kiến, có heartbeat cho job dài.
- Completion luôn kiểm tra token.
- Expired lease được reclaim.
- Reaper xử lý job không còn attempts.
- Multi-tenant quotas phải được giới hạn **toàn cluster**, không chỉ mỗi JVM.
- Worker chết giữa SMTP và DB update vẫn có nguy cơ double send.

Nếu cần throughput rất lớn, có thể dùng outbox CDC/broker relay; nhưng **business state và outbox intent vẫn phải được ghi atomically**.

## 38. Khi nào dùng AFTER_COMMIT event listener?

Một event listener sau commit có thể giúp worker thức dậy ngay:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onOrderCommitted(
        OrderCommittedEvent event) {

    localDispatcherSignal.wakeUp();
}
~~~

Đây là minh họa API và signal do ứng dụng cung cấp. Điều kiện bắt buộc: **mail_outbox row đã được INSERT trong transaction trước đó**.

Nếu process crash sau commit trước listener, polling định kỳ vẫn nhìn thấy job. Listener chỉ giảm latency; không phải nguồn sự thật.

Không viết:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void sendMailAfterCommit(...) {
    mailSender.send(...);
}
~~~

rồi coi đó là transactional outbox. Nếu không có durable mail intent, crash giữa commit và listener sẽ làm mất email.

## 39. Không gửi tới provider production từ bài tập

Dùng Mailpit để kiểm tra email format/SMTP submission. Trước khi dùng provider thật, cần bổ sung:

- Domain và From identity verification.
- SMTP AUTH và TLS trust/hostname verification.
- Secret manager và credential rotation.
- Throttling/quota theo account.
- MIME/HTML escaping và size limits.
- SPF/DKIM/DMARC theo domain sending.
- Bounce/complaint handling và provider feedback.
- Suppression/consent policy khi cần.
- Logging không lộ recipient/token.
- Monitoring oldest pending age và deliverability.
- Multi-tenant sender routing.
- Alert khi job DEAD/unknown outcome.
- Graceful shutdown và lease tuning.

Mailpit accept email không chứng minh email sẽ vượt qua policy của Gmail, Outlook hoặc một SMTP relay production. Đừng sao chép local cấu hình không auth/TLS sang mạng công cộng.


## 40. Kiểm thử transaction commit thật

Một test nên chứng minh rằng **order và outbox intent cùng commit**, không chỉ kiểm tra `OrderApplicationService` đã gọi hai repository methods.

Ví dụ với Spring Boot test sử dụng PostgreSQL test database được khởi tạo riêng:

~~~java
@SpringBootTest
class OrderOutboxIntegrationTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void createsOrderAndMailIntentTogether() {

        String key =
                "integration-" + UUID.randomUUID();

        CreateOrderRequest request =
                new CreateOrderRequest(
                        key,
                        "buyer@example.test",
                        new BigDecimal("125000.00"),
                        "VND"
                );

        UUID orderId =
                service.placeOrder(request);

        Integer orderCount =
                jdbc.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM app_order
                    WHERE id = ?
                    """,
                    Integer.class,
                    orderId
                );

        Integer mailCount =
                jdbc.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM mail_outbox
                    WHERE order_id = ?
                    """,
                    Integer.class,
                    orderId
                );

        assertEquals(1, orderCount);
        assertEquals(1, mailCount);
    }
}
~~~

Các import test tương ứng gồm JUnit 5, `@SpringBootTest`, Spring `@Autowired`, `JdbcTemplate` và Java `UUID`/`BigDecimal`. Ví dụ tập trung vào invariant của business transaction; trong test thật cần cô lập dữ liệu và cấu hình worker để không có test khác làm thay đổi trạng thái/đếm.

Nếu test method có `@Transactional` bao ngoài, nó có thể rollback ở cuối test; khi cần xác minh một **commit thực sự mà worker ở thread khác nhìn thấy**, hãy cấu hình ranh giới test transaction thích hợp thay vì để toàn bộ fixture chưa commit.

### Test không nên chỉ mock repository

Một mock có thể xác nhận:

~~~text
verify(orderRepository).insert(...)
verify(outboxRepository).enqueue(...)
~~~

nhưng không chứng minh hai thao tác dùng chung datasource, chung transaction manager, commit/rollback nguyên tử. Cần ít nhất một integration test với transaction database phù hợp.

## 41. Kiểm thử rollback trong database

Dùng `TransactionTemplate` để tạo một transaction chủ động thất bại sau cả hai thao tác:

~~~java
@Test
void rollbackRemovesBothWrites() {

    String key =
            "rollback-" + UUID.randomUUID();

    CreateOrderRequest request =
            new CreateOrderRequest(
                    key,
                    "rollback@example.test",
                    new BigDecimal("99000.00"),
                    "VND"
            );

    assertThrows(
            IllegalStateException.class,
            () -> transactionTemplate
                    .executeWithoutResult(status -> {

                        OrderRow order =
                                orders.insertOrRead(
                                        request
                                );

                        outbox.enqueueOrderConfirmation(
                                order
                        );

                        throw new IllegalStateException(
                                "Simulated rollback"
                        );
                    })
    );

    Integer ordersAfter =
            jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM app_order
                WHERE request_key = ?
                """,
                Integer.class,
                key
            );

    assertEquals(0, ordersAfter);
}
~~~

Trong test fixture, `transactionTemplate`, `orders`, `outbox` và `jdbc` là các bean được inject. Để kiểm tra cả hai phía, có thể giữ ID đã tạo trong fixture hoặc query outbox theo event/reference test; test phải đảm bảo worker không đang xử lý dữ liệu chưa commit, và tốt nhất cô lập theo requestKey.

Một rollback test phải kiểm tra **không còn outbox row tương ứng** chứ không chỉ order count. Khi unique constraint hoặc serialization lỗi, transaction cũng phải rollback nhất quán.

## 42. Kiểm thử idempotency từ HTTP retry

~~~java
@Test
void sameRequestKeyCreatesOneOrderAndJob() {

    String key =
            "duplicate-" + UUID.randomUUID();

    CreateOrderRequest request =
            new CreateOrderRequest(
                    key,
                    "same@example.test",
                    new BigDecimal("75000.00"),
                    "VND"
            );

    UUID first =
            service.placeOrder(request);

    UUID second =
            service.placeOrder(request);

    assertEquals(first, second);

    Integer count =
            jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM mail_outbox
                WHERE order_id = ?
                """,
                Integer.class,
                first
            );

    assertEquals(1, count);
}
~~~

Cần thêm test **cùng key nhưng payload khác** để xác nhận conflict, và test concurrency nhiều requests cùng key. Không chỉ test tuần tự vì race giữa hai HTTP threads có thể phát hiện vấn đề mà unit test không thấy.

Trong production, nên scope requestKey theo tenant, lưu request fingerprint hoặc các trường cần so khớp và dùng HTTP response semantics rõ ràng.

## 43. Kiểm thử claim concurrency

Một test concurrency cần **database thật với locking semantics của production**. Có thể tổ chức:

~~~text
Given:
  20 outbox jobs PENDING đã commit

Run concurrently:
  Worker A claimOne(...)
  Worker B claimOne(...)

Assert:
  Không có job ID được claim bởi cả A và B
  claimToken của từng claim không rỗng
  status chuyển SENDING đúng số rows
  attemptCount tăng một lần mỗi claim
~~~

Sau đó:

~~~text
Expire một lease trong test DB.
Worker C reclaim.
Token mới khác token cũ.

Old worker:
  markSent(jobId, oldToken)
  => updated row count = 0

New worker:
  markSent(jobId, newToken)
  => updated row count = 1
~~~

Đây là cách xác nhận **DB fencing**. Nó không chứng minh SMTP provider không nhận duplicate nếu worker cũ đã thực hiện send trước khi mất lease.

Không cần dùng thời gian thật cho mọi test: có thể cập nhật `claim_until` trong database thử nghiệm hoặc thiết kế một time abstraction phù hợp. Test concurrency với mock `JdbcTemplate` không chứng minh `SKIP LOCKED` đúng dưới contention thật.

## 44. Kiểm thử SMTP success bằng Mailpit

Một integration test hoặc thực hành có thể chạy:

~~~text
1. Insert committed mail_outbox PENDING.
2. Worker claim.
3. Build MimeMessage.
4. JavaMailSender.send tới Mailpit.
5. Assert Mailpit đã accept/capture message.
6. Assert job status SENT.
7. Poll tiếp: job SENT không được claim.
~~~

Nên assert bằng `X-Mail-Job-Id` hoặc correlation ID, không chỉ lấy “email mới nhất” từ một mailbox có thể được nhiều tests sử dụng.

Với GreenMail hoặc SMTP test server khác, có thể kiểm tra recipients/subject/body mà không gửi mail ra Internet.

Nếu test dùng async polling, đợi theo điều kiện có deadline thay vì `Thread.sleep` cố định:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {

        assertEquals(
                "SENT",
                readOutboxStatus(mailJobId)
        );
    });
~~~

`await()` là API kiểu Awaitility nếu dự án dùng dependency test này; `readOutboxStatus` là test helper. Không khẳng định code trên có thể chạy độc lập khi chưa cấu hình test SMTP/database.

## 45. Kiểm thử SMTP failure và retry

Tạo job mới khi Mailpit đang dừng hoặc dùng fake sender ném một `MailException` phù hợp.

Kỳ vọng:

~~~text
PENDING
 -> SENDING (attempt_count = 1)
 -> RETRY (next_attempt_at > now())

Sau delay:
 -> SENDING (attempt_count = 2)
 -> SENT nếu SMTP accept
~~~

Các assertion:

- Order vẫn `CONFIRMED` dù SMTP lỗi.
- Mail intent không biến mất.
- Retry không diễn ra trước deadline.
- `last_error_code` là category an toàn.
- Một job không bị gửi cùng lúc bởi hai current claims.
- Trên attempt cuối thất bại, status chuyển DEAD.
- Worker chết trên attempt cuối thì reaper giải phóng claim về trạng thái cần review.
- Không log payload chứa dữ liệu nhạy cảm.

Không chỉ kiểm tra số lần exception được ném; phải xác minh database state sau mỗi transaction.

## 46. Kiểm thử crash sau SMTP acceptance

Đây là tình huống quyết định để hiểu giới hạn của outbox:

~~~text
Fake SMTP sender:
  record accepted submission
  return success

Result writer:
  mô phỏng database failure
  không lưu SENT

Lease:
  expires

Worker tiếp:
  claim lại job
  submit lần nữa
~~~

Kết quả có thể là **hai submissions cho cùng outbox job**.

Một test nên xác nhận:

- Job vẫn có thể được phục hồi.
- Không tuyên bố exactly-once SMTP.
- Attempt/correlation ID được ghi để điều tra.
- Nếu old token bị stale, result update của worker cũ không ghi đè DB.
- Retry policy hiểu unknown outcome.
- Nội dung có thể được render lại nhất quán, nhưng business side effects ngoài SMTP phải idempotent.

Nếu provider có documented idempotency API/token, có thể dùng theo contract riêng; SMTP thuần không có khóa idempotency toàn mạng.

## 47. Monitoring cơ bản cho dự án

Khi thử nghiệm chuyển sang production, nên đo:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_outbox_pending_count` | Job chưa gửi |
| `mail_outbox_retry_count` | Job chờ retry |
| `mail_outbox_oldest_pending_age_seconds` | Độ trễ backlog |
| `mail_outbox_sending_count` | Current leases |
| `mail_outbox_expired_lease_total` | Worker crash/timeouts |
| `mail_outbox_send_attempt_total` | Submission attempts |
| `mail_outbox_send_duration_seconds` | Thời gian SMTP |
| `mail_outbox_failed_total` | Lỗi theo category |
| `mail_outbox_dead_count` | Job cần manual action |
| `mail_outbox_unknown_outcome_total` | Có nguy cơ ambiguous submission |
| `mail_outbox_duplicate_intent_total` | Enqueue duplicate bị chặn |
| `mail_outbox_reaper_total` | Expired final-claim cleanup |

Log theo `mailJobId`, `orderId`, attempt và provider route. Không đưa recipient address, body, token hay error text chứa PII vào metric label.

### Khi nào cần cảnh báo?

- Job PENDING già hơn SLA.
- SMTP AUTH hoặc TLS failures liên tục.
- DEAD tăng.
- Retry backlog tăng không giảm.
- Lease expiration tăng sau deployment.
- Worker không poll/claim thành công.
- Unknown outcome tăng khi mạng/provider lỗi.
- Job security/OTP chờ lâu đến mức nội dung hết hiệu lực.

Trong production, nếu một job bị đánh dấu DEAD, cần quy trình xem xét và khả năng replay có kiểm soát, không xóa thẳng row khiến mất audit.

## 48. Các giới hạn của demo trước khi mở rộng

Bài thực hành cố tình chưa triển khai đầy đủ:

- Multi-tenant authorization và sender registry.
- Phân loại SMTP reply code 4xx/5xx chi tiết.
- Per-recipient partial-send handling cho MIME nhiều recipients.
- Template engine, HTML escaping và attachments.
- Retry khác nhau theo purpose/tenant.
- Distributed quota/rate limiting.
- Priority/fair scheduling.
- Heartbeat renew lease cho long-running jobs.
- Provider delivery/webhook feedback.
- Claim batch với concurrency pool/available capacity.
- Payload schema version và immutable attachment storage.
- Reconciliation unknown outcomes.
- Data retention, legal hold và GDPR/PII policy.
- Alerting/metrics có phân quyền.
- Cách quản lý dead-letter/manual replay trong UI.

Những phần đó là nhu cầu production tùy quy mô. Mục tiêu Row 476 là **nắm đúng transaction boundary và tự xây được một mail outbox durable để gửi sau commit**.

## 49. Những lỗi triển khai thường gặp

### 49.1. INSERT outbox sau khi transaction commit

Đây **không phải** transactional outbox atomic. Crash giữa commit order và INSERT outbox có thể làm mất ý định gửi.

### 49.2. Gửi SMTP trong `@Transactional`

SMTP không rollback theo DB. Nếu DB rollback sau relay acceptance, khách hàng vẫn có thể nhận thư.

### 49.3. Chỉ gửi trong `AFTER_COMMIT` listener

Nếu không có outbox row đã commit, listener có thể bị mất khi process crash.

### 49.4. Bọc `mailSender.send` bằng `@Async` là xong

Executor queue in-memory không bền vững qua restart, không thay DB job store.

### 49.5. Outbox dùng `REQUIRES_NEW` riêng

Intent có thể commit dù business transaction rollback.

### 49.6. Không có unique idempotency key

HTTP retry và duplicate webhook tạo nhiều mail jobs.

### 49.7. Dùng UUID mới làm request key mỗi lần retry

Không có duplicate detection theo business intent.

### 49.8. SELECT rồi SEND mà không claim

Hai worker có thể đọc cùng job và gửi trùng.

### 49.9. Giữ DB transaction mở suốt SMTP

Lock contention và network timeout làm transaction chậm.

### 49.10. Không có lease

Crash ở trạng thái SENDING làm job kẹt mãi.

### 49.11. Không có fencing token

Worker cũ có thể ghi đè DB status sau khi bị reclaim.

### 49.12. Lease ngắn hơn SMTP timeout

Hai workers có thể cùng gửi một job.

### 49.13. Không xử lý expired lease ở final attempt

Job SENDING hết max attempts có thể kẹt vĩnh viễn.

### 49.14. Coi `SENT` là delivered

SMTP accepted chưa chứng minh mail vào inbox hoặc được đọc.

### 49.15. Coi outbox là exactly-once SMTP

Crash sau relay accepted trước DB update vẫn có thể gửi trùng.

### 49.16. Retry mọi exception ngay lập tức

Gây retry storm; hard errors hoặc AUTH failure cần policy khác.

### 49.17. Không kiểm tra token/consent tại send time

Job có thể gửi nội dung hết hạn hoặc tới recipient không còn được phép.

### 49.18. Lưu attachment lớn trong JSONB outbox

Làm database/heap phình lớn; nên dùng immutable object storage references khi có file lớn.

### 49.19. Claim quá nhiều job trước khi có executor capacity

Lease của task chờ có thể hết trước khi chúng được xử lý.

### 49.20. Không có oldest pending alert

Outbox có thể backlog nhiều giờ mà API vẫn trả thành công.

### 49.21. Không kiểm thử rollback và concurrency bằng DB thật

Mock tests không chứng minh ACID atomicity hay lock semantics của `SKIP LOCKED`.

### 49.22. Dùng SMTP production để làm bài tập

Có thể gây thư rác, phát dữ liệu thử và ảnh hưởng provider reputation. Dùng Mailpit/test server cô lập.

## 50. Câu hỏi tình huống

**Câu 1.** Outbox row được tạo trước hay sau transaction commit?

Phải **INSERT trong cùng business transaction**. Worker chỉ xử lý row sau commit.

**Câu 2.** Nếu business transaction rollback, worker có gửi email không?

Không có outbox row durable từ transaction đó, nên worker không có job tương ứng để gửi.

**Câu 3.** SMTP đang offline, đơn hàng có nên tạo được không?

Có thể vẫn commit đơn hàng và outbox; worker retry gửi theo policy. Điều này phụ thuộc use case, nhưng không nên buộc business DB transaction chờ SMTP.

**Câu 4.** Vì sao không dùng `@TransactionalEventListener(AFTER_COMMIT)` để gọi SMTP trực tiếp?

Crash sau commit trước listener có thể làm mất ý định gửi nếu không có durable outbox.

**Câu 5.** Vì sao cần `requestKey` và `idempotencyKey` riêng?

Chúng bảo vệ hai tầng: duplicate HTTP order creation và duplicate mail intent enqueue.

**Câu 6.** Tại sao claim phải nằm trong transaction ngắn?

Để nhiều workers phối hợp an toàn và tránh giữ DB locks trong lúc SMTP I/O.

**Câu 7.** `SKIP LOCKED` có bảo đảm không bao giờ gửi trùng không?

Không. Nó chỉ phối hợp claim/row locking, không loại bỏ duplicate sau lease expiry/crash.

**Câu 8.** `claimToken` có thay thế idempotency key không?

Không. Token thay đổi theo attempt; idempotency key ổn định theo intent.

**Câu 9.** Nếu worker crash sau SMTP acceptance nhưng trước `markSent`, điều gì xảy ra?

Job có thể được retry và email bị gửi trùng; không có exactly-once SMTP.

**Câu 10.** Vì sao cần reaper ở attempt cuối?

Nếu worker chết khi `attempt_count=max_attempts`, claim query sẽ không chọn lại job; reaper chuyển nó sang trạng thái cần manual action thay vì để kẹt SENDING.

**Câu 11.** `SENT` có nghĩa người dùng đã thấy thư trong Gmail chưa?

Không. Trong demo là SMTP relay đã chấp nhận submission, không chứng minh delivered.

**Câu 12.** Vì sao cần backoff và jitter?

Để không tạo retry storm khi provider tạm lỗi, đồng thời phân tán traffic sau outage.

**Câu 13.** Một exception timeout sau SMTP DATA có chắc thư chưa được gửi?

Không. Relay có thể đã accept nhưng client mất response, nên outcome chưa chắc chắn.

**Câu 14.** Hai HTTP requests cùng requestKey nhưng email nhận khác nhau thì sao?

Phải báo conflict và không tạo một intent khác âm thầm; unique key phải có policy rõ.

**Câu 15.** Tại sao nên gửi một recipient mỗi job trong demo?

Dễ idempotency, retry, privacy và result tracking, tránh partial-recipient complexity.

**Câu 16.** Một mail job giữ attachment trong local `/tmp`, worker restart ở pod khác thì sao?

Có thể mất file; production phải dùng nguồn nội dung bền vững và giữ đủ lâu qua retry.

**Câu 17.** Khi nào nên trả `202 Accepted`?

Khi API chỉ tiếp nhận xử lý bất đồng bộ; cần nói rõ mail intent đã được persist, không khẳng định delivered.

**Câu 18.** Làm sao chứng minh transaction đúng?

Integration test commit/rollback với DB thật, kiểm tra cả business row và outbox row; không chỉ mock các method calls.

## 51. Mô hình ghi nhớ

~~~mermaid
flowchart TD
    A["Create order HTTP request"] --> B["Validate requestKey + tenant"]
    B --> C["BEGIN database transaction"]
    C --> D["Insert/find order"]
    C --> E["INSERT outbox PENDING unique intent"]
    D --> F["COMMIT"]
    E --> F
    F --> G["Scheduled worker"]
    G --> H["Claim due row with SKIP LOCKED"]
    H --> I["COMMIT claim + lease token"]
    I --> J["Compose MIME"]
    J --> K["JavaMailSender.send"]
    K --> L{"Outcome"}
    L -->|"Accepted"| M["Mark SENT with token"]
    L -->|"Temporary"| N["RETRY + backoff"]
    L -->|"Permanent"| O["DEAD / review"]
    L -->|"Unknown"| P["Reconcile / retry policy"]
    N --> G
    P --> G
    M --> Q["Provider feedback nếu có"]
~~~

Ghi nhớ các nguyên tắc:

1. **Ghi outbox trong cùng business transaction**, không INSERT sau commit.
2. **Worker gửi mail sau commit**, vì chỉ đọc những row đã durable.
3. **SMTP không nằm trong ACID transaction của database**; đừng gửi trong `@Transactional` rồi chờ rollback mail.
4. **`@Async`/`AFTER_COMMIT` không thay durable outbox**; chúng chỉ có thể bổ trợ scheduling/wake-up.
5. **Unique request key và unique mail idempotency key bảo vệ hai tầng duplicate**.
6. **Claim dùng transaction ngắn và row locking/conditional update**, không giữ DB locks xuyên network I/O.
7. **Lease có expiry và fencing token**, đồng thời phải có cách xử lý expired final attempt.
8. **SENT chỉ nghĩa submitted cho relay**; delivered/bounced thuộc workflow khác.
9. **Unknown SMTP outcome có thể tạo duplicate khi retry**; outbox không hứa exactly-once.
10. **Retry có backoff/jitter và failure classification**, không retry vô hạn mọi exception.
11. **Một job/recipient giảm partial-send complexity** và giúp quản lý quota/consent riêng.
12. **Payload phải đủ ổn định để dựng mail sau restart**, có template/snapshot/attachment versions khi cần.
13. **Production cần bảo mật sender, recipient, token và attachment**, cùng quota/monitoring/retention.
14. **Đo backlog age, dead jobs, lease expiry và unknown outcomes** để phát hiện sự cố.
15. **Kiểm thử commit, rollback, concurrency, SMTP failures và crash windows** bằng database/SMTP test server cô lập.

Trong dự án Spring Framework Mail này, bước quyết định không phải là thêm `@Scheduled` hay một vòng lặp retry, mà là **giữ ranh giới giao dịch đúng**: cập nhật nghiệp vụ và ý định gửi được commit nguyên tử, còn SMTP submission diễn ra sau commit qua một worker có job bền vững. Với schema, idempotency, claim/lease, retry và các bài kiểm thử thực hành, ứng dụng có khả năng phục hồi tốt hơn trước lỗi SMTP và restart, đồng thời không che giấu nguy cơ email trùng tại ranh giới external transport.





