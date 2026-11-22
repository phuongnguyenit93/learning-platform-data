# Tạo endpoint yêu cầu gửi email xác nhận

Khi người dùng đăng ký tài khoản, thay đổi địa chỉ email hoặc cần xác nhận một thao tác, ứng dụng thường cung cấp một HTTP endpoint để **yêu cầu gửi email xác nhận**. Trong Spring Framework Mail, phần gửi thư có thể thực hiện bằng `JavaMailSender` và `MimeMessageHelper`, nhưng một API có thể dùng trong thực tế còn cần xác thực dữ liệu, giới hạn lạm dụng, quản lý token, thời hạn hiệu lực, xử lý lỗi SMTP và trạng thái gửi.

Bài thực hành này xây dựng một flow **xác minh quyền kiểm soát địa chỉ email**: người dùng yêu cầu gửi thư tới địa chỉ đang chờ xác minh, mở liên kết chứa token dùng một lần rồi xác nhận. Đây là một ví dụ cụ thể của “email xác nhận”; với email xác nhận đơn hàng, thanh toán hoặc đặt lịch, bạn vẫn áp dụng các nguyên tắc REST, MIME, bảo mật và độ tin cậy tương tự, nhưng **không cần lấy email verification token để thay cho trạng thái nghiệp vụ**.

Chúng ta bắt đầu với mô hình dễ hiểu trong Spring Boot, sau đó nâng cấp lên cách tổ chức production với **durable command/outbox**, response `202 Accepted`, chống account enumeration, idempotency, retry và kiểm thử bằng SMTP sandbox. Mỗi bước phân biệt rõ **yêu cầu gửi**, **đã chấp nhận để xử lý**, **đã submit qua SMTP** và **đã xác minh địa chỉ**.

**Mục tiêu cuối cùng:** có một endpoint HTTP có contract rõ ràng, tạo email xác nhận đúng recipient, không làm lộ tài khoản/token, có thể thử nghiệm và quan sát được, đồng thời biết giới hạn của các giải pháp đồng bộ đơn giản.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế endpoint `POST /api/email-confirmations/requests` với body, validation và HTTP response phù hợp.
2. Giải thích vì sao yêu cầu gửi và xác nhận token là **hai hành động khác nhau**.
3. Tạo token ngẫu nhiên đủ mạnh, URL-safe, có TTL và chỉ lưu digest thay vì lưu token plaintext trong bảng xác minh.
4. Dựng một email text/plain và HTML an toàn bằng `MimeMessageHelper`.
5. Không gửi email trực tiếp trong controller hoặc trong transaction database kéo dài.
6. Tránh tiết lộ tài khoản có tồn tại qua response, body, timing và lỗi khác nhau.
7. Giới hạn tần suất yêu cầu theo user, IP, device hoặc địa chỉ có chính sách phù hợp.
8. Giải thích ranh giới transaction khi lưu token và gọi SMTP.
9. Xây hướng mở rộng sang transactional outbox và retry an toàn.
10. Tổ chức unit, web, persistence và SMTP integration tests.

## 2. Xác định quy trình nghiệp vụ

Giả sử một tài khoản đã được tạo với trạng thái **email chưa xác minh**. Người dùng nhấn “Gửi email xác nhận”. Hệ thống cần:

```text
Web / Mobile client
        |
        v
POST /api/email-confirmations/requests
        |
        v
Validate + authorize/rate limit
        |
        v
Find eligible unverified account
        |
        v
Create single-use token with expiry
        |
        v
Persist token digest + request metadata
        |
        v
Compose and submit email
        |
        v
User opens confirmation link
        |
        v
POST /api/email-confirmations/confirm
        |
        v
Validate token, consume once, mark email verified
```

**Không được coi việc gửi thư là đã xác minh email.** Account chỉ được đánh dấu `verified` sau khi một confirmation token hợp lệ được sử dụng theo quy trình xác minh được thiết kế.

### Hai endpoints khác nhau

| Endpoint | Mục đích | Có đổi trạng thái verified? |
| --- | --- | --- |
| `POST /api/email-confirmations/requests` | Yêu cầu gửi thư chứa liên kết/mã xác minh | Không |
| `POST /api/email-confirmations/confirm` | Kiểm tra token và xác nhận địa chỉ | Có, khi token hợp lệ |

Với sản phẩm dùng magic-link để đăng nhập hoặc thay đổi địa chỉ, chính sách token và quyền khác nhau; **không tái sử dụng token verification cho mọi hành động** nếu chúng có mức độ nhạy cảm khác.

## 3. Contract của endpoint yêu cầu

### Request minh họa

```http
POST /api/email-confirmations/requests HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "email": "student@example.net"
}
```

### Response đề xuất

```http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Length: 0
```

**`202 Accepted` nghĩa là ứng dụng đã chấp nhận yêu cầu theo contract tiếp nhận**, không có nghĩa SMTP đã submit hay email đã delivered. Nếu một API dùng hàng đợi bền vững, nên chỉ trả `202` sau khi durable request record đã được ghi thành công.

Đối với endpoint public có khả năng lộ sự tồn tại tài khoản, trả cùng một response dạng generic dù email không tồn tại, đã verified hoặc đang được cooldown, miễn là yêu cầu đã được xử lý theo chính sách tương ứng. Không trả `404 Account not found` hoặc `409 Email already verified` chỉ cho nhóm email cụ thể nếu điều đó cho phép người lạ dò tài khoản.

### Nếu endpoint yêu cầu authenticated session

Một thiết kế an toàn hơn cho nhiều sản phẩm:

```http
POST /api/me/email-confirmations/requests HTTP/1.1
Authorization: Bearer <session-token>
```

Backend lấy địa chỉ từ **account đã đăng nhập**, không tin một email do client truyền. Phù hợp khi yêu cầu xác nhận email của tài khoản hiện tại. Với luồng đăng ký chưa đăng nhập, cần một cơ chế public request được bảo vệ chống lạm dụng như phần sau.

## 4. Những HTTP status thường gặp

| Trạng thái | Ý nghĩa ở API | Lưu ý |
| --- | --- | --- |
| `202 Accepted` | Yêu cầu đủ điều kiện đã được tiếp nhận theo contract | Không nói “đã delivered” |
| `204 No Content` | Một số API chọn cho thao tác idempotent đã xử lý xong | Không có nội dung trả về |
| `400 Bad Request` | JSON sai hoặc giá trị không thể parse theo contract | Không lộ account lookup |
| `401 Unauthorized` | Thiếu hoặc sai authentication ở endpoint yêu cầu đăng nhập | Không áp dụng máy móc với endpoint public |
| `403 Forbidden` | Chủ thể không được phép thao tác | Cần tránh leakage nếu request public |
| `429 Too Many Requests` | Vượt rate limit | Trả Retry-After khi phù hợp, không tiết lộ account |
| `503 Service Unavailable` | Không thể tiếp nhận bền vững do phụ thuộc hệ thống | Cho client biết có thể thử lại theo policy |

Trong môi trường public, việc trả `429` riêng dựa theo tình trạng cụ thể của địa chỉ cũng có thể tiết lộ thông tin. Hãy thiết kế rate limits và response policy nhất quán, đồng thời vẫn chặn lạm dụng.

## 5. Những gì endpoint không nên làm

Không trả về raw token:

```json
{
  "verificationToken": "secret-token",
  "emailExists": true,
  "smtpStatus": "DELIVERED"
}
```

Những dữ liệu này vừa có thể lộ bí mật vừa mô tả sai kết quả SMTP.

Không nhận toàn bộ MIME content do người dùng public chỉ định:

```json
{
  "to": "victim@example.net",
  "from": "admin@example.org",
  "subject": "Tùy ý",
  "html": "<a href='https://malicious.example'>...</a>"
}
```

Nếu endpoint chỉ có mục đích xác minh email, backend phải **sở hữu template, sender domain, nội dung, TTL và đích link**. Không biến nó thành một open mail relay để attacker gửi thư tùy ý.

## 6. Kiến trúc Spring Boot cho bài thực hành

```text
EmailConfirmationController
         |
         v
ConfirmationRequestService
         |
         +--> Validation / RateLimit / Eligibility
         |
         +--> ConfirmationIssuer (transaction)
         |       |
         |       +--> AccountRepository
         |       +--> VerificationTokenRepository
         |       +--> SecureTokenService
         |
         +--> ConfirmationMailSender
                 |
                 +--> Template renderer
                 +--> JavaMailSender
                 +--> SMTP sandbox/provider

EmailConfirmationController.confirm
         |
         v
ConfirmationVerifier (transaction)
         |
         +--> TokenRepository
         +--> AccountRepository
```

Trong phiên bản học tập đầu tiên, service phát token trong một transaction rồi gửi mail **sau khi transaction hoàn tất**. Phiên bản này dễ hiểu nhưng **chưa bảo đảm không mất yêu cầu gửi khi process crash hoặc SMTP lỗi**; mục nâng cấp production sẽ dùng outbox và xử lý bất đồng bộ bền vững.

## 7. Dependency và nền tảng

Ví dụ dùng:

- Java 17+.
- Spring Boot 3.x với `jakarta.mail`/`jakarta.validation`.
- Spring Web cho REST.
- Spring Validation cho input.
- Spring Data JPA và một SQL database.
- Spring Boot Mail cho `JavaMailSender`.
- JUnit/Spring Boot Test và SMTP sandbox cho kiểm thử.

Dependencies Gradle trong một project đã cấu hình Spring Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Không trộn các phiên bản `javax.mail` cũ với `jakarta.mail` trong cùng ví dụ Spring Boot 3.x. Với database production, sử dụng migrations thay vì cho Hibernate tự drop/recreate các bảng quan trọng khi restart.

## 8. Package structure gợi ý

```text
com.example.mailconfirm
├── MailConfirmationApplication.java
├── api/
│   ├── EmailConfirmationController.java
│   ├── RequestConfirmationBody.java
│   ├── ConfirmEmailBody.java
│   └── ApiExceptionHandler.java
├── domain/
│   ├── UserAccount.java
│   ├── EmailVerificationToken.java
│   └── ConfirmationPolicy.java
├── repository/
│   ├── AccountRepository.java
│   └── EmailVerificationTokenRepository.java
├── service/
│   ├── SecureTokenService.java
│   ├── ConfirmationIssuer.java
│   ├── ConfirmationRequestService.java
│   └── ConfirmationVerifier.java
└── mail/
    └── ConfirmationMailSender.java
```

Với production, có thể thêm `outbox/`, `worker/`, `metrics/`, `security/`. Những tên package chỉ là minh họa, không phải cấu trúc Spring Boot bắt buộc.

## 9. Cấu hình SMTP riêng cho development

Không gửi mail thử từ local environment đến người dùng thật. Sử dụng Mailpit, GreenMail hoặc một SMTP sandbox đã được phê duyệt:

```yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000

app:
  confirmation:
    base-url: http://localhost:8080
    token-ttl: PT15M
    sender-address: no-reply@example.org
```

Ví dụ giả định một SMTP test server đang nghe ở `127.0.0.1:1025` và không yêu cầu TLS/auth. **Không sao chép cấu hình `auth=false`/`STARTTLS=false` sang production**. SMTP provider thật có thể yêu cầu STARTTLS, implicit TLS hoặc auth phù hợp.

### Production dùng secrets và TLS đúng contract

```yaml
spring:
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
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000

app:
  confirmation:
    base-url: https://account.example.org
    sender-address: verify@example.org
```

`${...}` được hiểu là **Spring property placeholders** sau khi hiển thị; secret values phải lấy từ secret management hoặc environment phù hợp. Không đưa SMTP password vào repository, HTTP responses hay exception logs.

## 10. Cấu hình database cho bài học

Ví dụ PostgreSQL local:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://127.0.0.1:5432/mailconfirm
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

`ddl-auto: validate` giả định tables đã được tạo bằng migration. Trong demo ngắn, có thể dùng database in-memory với schema dành riêng cho test. Không cho production dùng `create-drop` trên database chứa tài khoản và verification token.

## 11. Mẫu database logic

Hai bảng cốt lõi:

```sql
CREATE TABLE user_account (
    id UUID PRIMARY KEY,
    email_canonical VARCHAR(320) NOT NULL UNIQUE,
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE email_verification_token (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES user_account(id),
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);

CREATE INDEX ix_verification_account_expiry
    ON email_verification_token(account_id, expires_at);
```

`token_hash` chứa digest của token có entropy cao, không chứa raw token. `expires_at` và `used_at` cho phép xác định token còn hợp lệ. Thêm unique constraint giúp lookup và tránh trùng digest trong phạm vi bảng; với token ngẫu nhiên 256-bit, collision cực kỳ khó, nhưng database vẫn nên có constraint đúng.

Nếu ứng dụng hỗ trợ thay địa chỉ email, cần gắn token với **email đang chờ xác minh hoặc email version**. Không xác minh một địa chỉ mới bằng token đã phát hành cho địa chỉ cũ.

## 12. Định nghĩa REST request body với Bean Validation

```java
package com.example.mailconfirm.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RequestConfirmationBody(
        @NotBlank
        @Email
        @Size(max = 320)
        String email
) {}
```

Một DTO khác cho bước xác nhận:

```java
package com.example.mailconfirm.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ConfirmEmailBody(
        @NotBlank
        @Size(max = 512)
        String token
) {}
```

Validation HTTP chỉ là lớp đầu tiên. `@Email` không chứng minh mailbox tồn tại, người gọi sở hữu mailbox, hoặc địa chỉ đã được chuẩn hóa phù hợp. Token verification mới chứng minh quyền truy cập vào đường nhận thư theo quy trình.

## 13. Controller nhận yêu cầu và trả 202

```java
package com.example.mailconfirm.api;

import com.example.mailconfirm.service.ConfirmationRequestService;
import com.example.mailconfirm.service.ConfirmationVerifier;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/email-confirmations")
public class EmailConfirmationController {

    private final ConfirmationRequestService requests;
    private final ConfirmationVerifier verifier;

    public EmailConfirmationController(
            ConfirmationRequestService requests,
            ConfirmationVerifier verifier
    ) {
        this.requests = requests;
        this.verifier = verifier;
    }

    @PostMapping("/requests")
    public ResponseEntity<Void> request(
            @Valid @RequestBody RequestConfirmationBody body
    ) {
        requests.request(body.email());
        return ResponseEntity.accepted()
                .cacheControl(CacheControl.noStore())
                .build();
    }

    @PostMapping("/confirm")
    public ResponseEntity<Void> confirm(
            @Valid @RequestBody ConfirmEmailBody body
    ) {
        verifier.confirm(body.token());
        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
```

Controller không dựng MIME, không tạo token, không truy vấn trực tiếp database và không chứa SMTP configuration. Nó chỉ chuyển request đến application service và áp contract HTTP.

**Lưu ý:** đây là khung controller; để có API production, cần thêm authentication/authorization, anti-abuse controls, exception mapping và durable acceptance theo chính sách. Việc trả `202` không tự tạo khả năng background processing.

## 14. Phân biệt public request và authenticated request

Với endpoint public nhận email:

- Bất kỳ ai có thể yêu cầu gửi tới một địa chỉ bất kỳ nếu không có rào chắn.
- Kẻ xấu có thể spam một người hoặc dùng API để dò tài khoản.
- Thời gian phản hồi khác nhau giữa account có/không có có thể tạo side channel.

Với endpoint `/api/me/...`:

- Backend lấy account ID từ session/token đã xác thực.
- Chỉ gửi tới địa chỉ đang chờ xác minh thuộc tài khoản ấy.
- Thường không cần nhận trường `email` trong request body.
- Vẫn cần rate limit/cooldown và kiểm tra trạng thái.

Trong bài, controller public được giữ để minh họa contract dễ thử. **Không đưa nguyên controller này ra Internet nếu chưa triển khai những biện pháp chống lạm dụng và xử lý timing leakage** ở các phần sau.

## 15. Entity tài khoản chờ xác minh

Ta giả định ứng dụng đã có cơ chế tạo tài khoản. Bài học không triển khai registration/password management để tập trung vào email confirmation.

```java
package com.example.mailconfirm.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "user_account")
public class UserAccount {

    @Id
    private UUID id;

    @Column(
            name = "email_canonical",
            nullable = false,
            unique = true,
            length = 320
    )
    private String emailCanonical;

    @Column(name = "email_verified_at")
    private Instant emailVerifiedAt;

    protected UserAccount() {}

    public UserAccount(UUID id, String emailCanonical) {
        this.id = id;
        this.emailCanonical = emailCanonical;
    }

    public UUID getId() {
        return id;
    }

    public String getEmailCanonical() {
        return emailCanonical;
    }

    public boolean isEmailVerified() {
        return emailVerifiedAt != null;
    }

    public void markEmailVerified(Instant when) {
        if (emailVerifiedAt == null) {
            emailVerifiedAt = when;
        }
    }
}
```

Nếu hệ thống cho phép đổi địa chỉ, model production nên có `pendingEmail` hoặc một email version riêng. Token phải gắn với **địa chỉ đang được xác minh** chứ không xác nhận nhầm một địa chỉ đã được đổi sau khi token được phát.

## 16. Entity verification token

```java
package com.example.mailconfirm.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "email_verification_token")
public class EmailVerificationToken {

    @Id
    private UUID id;

    @Column(name = "account_id", nullable = false)
    private UUID accountId;

    @Column(
            name = "token_hash",
            nullable = false,
            unique = true,
            length = 64
    )
    private String tokenHash;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "used_at")
    private Instant usedAt;

    protected EmailVerificationToken() {}

    public EmailVerificationToken(
            UUID id,
            UUID accountId,
            String tokenHash,
            Instant createdAt,
            Instant expiresAt
    ) {
        this.id = id;
        this.accountId = accountId;
        this.tokenHash = tokenHash;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    public UUID getAccountId() {
        return accountId;
    }

    public boolean isUsableAt(Instant now) {
        return usedAt == null && expiresAt.isAfter(now);
    }

    public void consumeAt(Instant now) {
        if (usedAt != null) {
            throw new IllegalStateException(
                    "Token already consumed"
            );
        }
        usedAt = now;
    }
}
```

Token được coi là đã hết hạn khi `expiresAt <= now`. Dùng `Instant` với clock được inject sẽ giảm nhầm lẫn giữa múi giờ và thuận tiện cho test.

### Không lưu raw token vào entity

Nếu database bị lộ trong lúc token còn hiệu lực, một cột `raw_token` cho phép attacker xác minh email thay người nhận. Với token ngẫu nhiên đủ entropy, lưu digest SHA-256 giúp người có database dump không thể dễ dàng lấy lại token.

**Lưu ý:** digest không thay thế mã hóa nếu bản raw token còn nằm trong hàng đợi/outbox. Ở phần production, token cần gửi phải được bảo vệ khi lưu hoặc được phát hành ở worker.

## 17. Repository cho account và token

```java
package com.example.mailconfirm.repository;

import com.example.mailconfirm.domain.UserAccount;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface AccountRepository
        extends JpaRepository<UserAccount, UUID> {

    Optional<UserAccount> findByEmailCanonical(
            String emailCanonical
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from UserAccount a where a.id = :id")
    Optional<UserAccount> findLockedById(
            @Param("id") UUID id
    );
}
```

Và:

```java
package com.example.mailconfirm.repository;

import com.example.mailconfirm.domain.EmailVerificationToken;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface EmailVerificationTokenRepository
        extends JpaRepository<EmailVerificationToken, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
           select t from EmailVerificationToken t
           where t.tokenHash = :hash
           """)
    Optional<EmailVerificationToken> findLockedByHash(
            @Param("hash") String hash
    );
}
```

Pessimistic locking trên token giúp giảm nguy cơ hai request đồng thời cùng consume một token. Lock account khi chuyển trạng thái giúp tránh race giữa các tokens khác nhau của cùng account.

Khi production có lưu lượng lớn, cũng có thể dùng atomic conditional UPDATE/optimistic locking với contract phù hợp. Đừng chỉ làm `findByHash`, check `usedAt` rồi save không có concurrency control.

## 18. Service tạo token ngẫu nhiên và digest

Một token cần **khó đoán** và dùng được trong URL. Tránh token tăng dần hoặc dựa vào timestamp/account ID.

```java
package com.example.mailconfirm.service;

import org.springframework.stereotype.Component;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

@Component
public class SecureTokenService {

    private final SecureRandom secureRandom =
            new SecureRandom();

    public String newToken() {
        byte[] bytes = new byte[32]; // 256 random bits
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public String hash(String rawToken) {
        try {
            MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(
                    rawToken.getBytes(StandardCharsets.US_ASCII)
            );
            return HexFormat.of().formatHex(hashed);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable", ex
            );
        }
    }
}
```

### Vì sao 32 bytes random?

32 bytes từ `SecureRandom` cho token có 256 bit ngẫu nhiên về mặt thiết kế; khi encode bằng Base64 URL-safe không padding, token thường có độ dài 43 ký tự. Token có entropy cao có thể dùng SHA-256 digest để lookup, không giống mật khẩu người dùng có entropy thấp cần thuật toán password hashing chậm như Argon2/bcrypt/scrypt.

Không tự dùng `UUID.randomUUID()` cộng timestamp làm token thay cho một yêu cầu ngẫu nhiên mạnh nếu đặc tả sản phẩm đã định 256-bit secret. Và không dùng `Random` (không phải `SecureRandom`) để phát hành token xác minh.

### Token hashing không phải token encryption

Hash là một chiều: bảng token dùng để **kiểm chứng token do người dùng cung cấp**. Để gửi email, ứng dụng cần raw token ở thời điểm compose; nếu cần lưu raw token để retry, phải mã hóa bảo mật hoặc có cơ chế tái phát hành trong worker.

## 19. Clock injection giúp test expiry chính xác

```java
package com.example.mailconfirm;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Clock;

@Configuration
public class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Trong unit test có thể thay:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-12T03:00:00Z"),
        ZoneOffset.UTC
);
```

Giờ hết hạn nên so sánh bằng `Instant`; không lấy giờ local của máy chủ cộng chuỗi “15 phút” theo timezone không xác định.

## 20. Chính sách chuẩn hóa email address

Ví dụ đơn giản trong một hệ thống đã chọn **email case-insensitive theo chính sách account**:

```java
package com.example.mailconfirm.service;

import java.util.Locale;

public final class EmailCanonicalizer {

    private EmailCanonicalizer() {}

    public static String canonicalize(String raw) {
        return raw.trim().toLowerCase(Locale.ROOT);
    }
}
```

**Đây là chính sách đơn giản hóa cho project**, không phải quy tắc kỹ thuật an toàn cho mọi mailbox: local part có thể có semantics case-sensitive, internationalized addresses cần chuẩn hóa riêng, còn provider-specific alias/dot/plus rules không được áp dụng tùy tiện. Với production, phải thống nhất canonicalization ngay từ registration/account lookup và test địa chỉ Unicode/IDN nếu hệ thống hỗ trợ.

Đừng “bỏ dấu chấm trong Gmail” hoặc “bỏ phần sau dấu +” cho tất cả email domains. Việc đó có thể hợp nhất hai địa chỉ khác nhau ở provider khác.

## 21. Dữ liệu trao giữa issuer và mail sender

```java
package com.example.mailconfirm.service;

import java.time.Instant;
import java.util.UUID;

public record IssuedConfirmation(
        UUID accountId,
        String recipient,
        String rawToken,
        Instant expiresAt
) {}
```

Record này có **raw token chỉ tồn tại trong memory giữa phát hành và gửi** ở phiên bản demo. Không log record bằng `toString()`, không serialize thành HTTP response và không đặt vào queue không mã hóa.

Một worker/outbox thực tế cần hợp đồng khác để bảo vệ dữ liệu khi chưa gửi, xem phần nâng cấp.

## 22. Service phát token trong transaction riêng

```java
package com.example.mailconfirm.service;

import com.example.mailconfirm.domain.EmailVerificationToken;
import com.example.mailconfirm.domain.UserAccount;
import com.example.mailconfirm.repository.AccountRepository;
import com.example.mailconfirm.repository.EmailVerificationTokenRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Service
public class ConfirmationIssuer {

    private final AccountRepository accounts;
    private final EmailVerificationTokenRepository tokens;
    private final SecureTokenService secureTokens;
    private final Clock clock;

    public ConfirmationIssuer(
            AccountRepository accounts,
            EmailVerificationTokenRepository tokens,
            SecureTokenService secureTokens,
            Clock clock
    ) {
        this.accounts = accounts;
        this.tokens = tokens;
        this.secureTokens = secureTokens;
        this.clock = clock;
    }

    @Transactional
    public Optional<IssuedConfirmation> issueIfEligible(
            String rawEmail
    ) {
        String canonical =
                EmailCanonicalizer.canonicalize(rawEmail);

        Optional<UserAccount> found =
                accounts.findByEmailCanonical(canonical);

        if (found.isEmpty() || found.get().isEmailVerified()) {
            return Optional.empty();
        }

        UserAccount account = found.get();
        Instant now = clock.instant();
        Instant expiresAt = now.plus(Duration.ofMinutes(15));

        String rawToken = secureTokens.newToken();
        String hash = secureTokens.hash(rawToken);

        tokens.save(new EmailVerificationToken(
                UUID.randomUUID(),
                account.getId(),
                hash,
                now,
                expiresAt
        ));

        return Optional.of(new IssuedConfirmation(
                account.getId(),
                account.getEmailCanonical(),
                rawToken,
                expiresAt
        ));
    }
}
```

Trong bài này TTL được đặt là 15 phút để dễ minh họa; production nên đọc từ `@ConfigurationProperties`, có validation và giới hạn phù hợp cho loại email. Không coi 15 phút là thời hạn đúng cho mọi sản phẩm.

### Tách transaction là điều cần thiết

`@Transactional` trên `ConfirmationIssuer` chỉ bao phần lookup và insert token. Khi facade gọi **qua một Spring bean khác**, transaction commit trước khi facade thực hiện SMTP. Nhờ đó không giữ database transaction mở khi network I/O bị chậm.

Tuy nhiên, vẫn có cửa sổ mất công việc:

```text
Commit token -> process crashes -> SMTP never called
```

Điểm này là giới hạn có chủ đích của bản demo; outbox giúp xử lý.

## 23. Không thu hồi toàn bộ token cũ một cách mù quáng

Người dùng nhấn “Gửi lại email” ba lần:

```text
Token A issued at 10:00
Token B issued at 10:01
Token C issued at 10:02
```

Hai chính sách thường gặp:

**Một token còn hiệu lực tại một thời điểm:**

- Phát token B và thu hồi A.
- Đơn giản trạng thái, nhưng email A có thể đến muộn và link không còn hợp lệ.

**Cho phép một số tokens còn hạn cùng tồn tại:**

- A/B/C đều có thể xác minh trong TTL.
- Cần rate limits và bảo đảm account chỉ được chuyển verified một lần.
- Sau khi verified, các tokens còn lại không được dùng để thực hiện tác vụ khác.

Code minh họa theo cách thứ hai: có thể tạo nhiều token, nhưng verifier kiểm tra account đã verified hay chưa. Production cần quy tắc resend, cooldown và max active tokens rõ ràng; không tạo vô hạn records khi attacker spam endpoint.

## 24. Tạo trang xác nhận và đường link

Email chứa đường dẫn đến trang frontend:

```text
https://account.example.org/confirm-email?token=<opaque-token>
```

Frontend hiển thị nội dung xác nhận, sau đó gọi `POST /api/email-confirmations/confirm` với token. Không nhất thiết phải tự xác minh ngay khi HTTP GET mở link.

### Vì sao không tự xác nhận bằng GET?

Email security gateways và link scanners có thể tự mở URL trước người dùng. Nếu GET có side effect “consume token và mark account verified”, một hệ thống scanner có thể vô tình kích hoạt hành động. Với các tác vụ quan trọng, nên dùng một trang giải thích và một hành động xác nhận được bảo vệ thích hợp.

Nếu lựa chọn xác minh bằng một lần click không cần bước xác nhận bổ sung, cần đánh giá scanner/prefetch behavior, replay và rủi ro của sản phẩm, không đơn giản coi URL GET luôn là một ý định người dùng.

## 25. Quản lý base URL của email

Không lấy `Host` header do client cung cấp để xây link:

```java
// Anti-pattern: attacker có thể điều khiển Host
String link = request.getHeader("Host") + "/confirm-email";
```

Thay bằng origin do ứng dụng quản lý:

```yaml
app:
  confirmation:
    base-url: https://account.example.org
```

Trong môi trường staging:

```yaml
app:
  confirmation:
    base-url: https://staging-account.example.org
```

Tránh dùng URL production trong email test, và chỉ cho phép HTTPS origin đã được phê duyệt khi phục vụ người dùng thật. Điều này giảm rủi ro host-header poisoning và link dẫn sang domain giả.

## 26. Cấu hình xác nhận dưới dạng type-safe properties

```java
package com.example.mailconfirm;

import org.springframework.boot.context.properties.ConfigurationProperties;
import java.net.URI;
import java.time.Duration;

@ConfigurationProperties(prefix = "app.confirmation")
public record ConfirmationProperties(
        URI baseUrl,
        String senderAddress,
        Duration tokenTtl
) {}
```

Kích hoạt:

```java
package com.example.mailconfirm;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ConfirmationProperties.class)
public class MailConfirmationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                MailConfirmationApplication.class, args
        );
    }
}
```

Trong production, thêm validation properties: sender address hợp lệ, `baseUrl` thuộc allowlisted HTTPS origins, `tokenTtl` dương và trong khoảng policy. Đừng cho client của endpoint tự chọn baseUrl hoặc SMTP sender.

## 27. Service dựng và gửi MIME email

```java
package com.example.mailconfirm.mail;

import com.example.mailconfirm.ConfirmationProperties;
import com.example.mailconfirm.service.IssuedConfirmation;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;
import org.springframework.web.util.HtmlUtils;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

@Component
public class ConfirmationMailSender {

    private final JavaMailSender sender;
    private final ConfirmationProperties properties;

    public ConfirmationMailSender(
            JavaMailSender sender,
            ConfirmationProperties properties
    ) {
        this.sender = sender;
        this.properties = properties;
    }

    public void send(IssuedConfirmation issued)
            throws MessagingException {

        String encoded = URLEncoder.encode(
                issued.rawToken(),
                StandardCharsets.UTF_8
        );
        String url = properties.baseUrl()
                .resolve("/confirm-email?token=" + encoded)
                .toASCIIString();

        String safeUrl = HtmlUtils.htmlEscape(url);
        String plain = """
                Vui lòng xác minh địa chỉ email của bạn.

                Mở đường dẫn:
                """ + url + """

                Nếu bạn không yêu cầu, có thể bỏ qua thư này.
                """;

        String html = """
                <html>
                  <body>
                    <h1>Xác minh địa chỉ email</h1>
                    <p>Vui lòng xác nhận địa chỉ bằng liên kết:</p>
                    <p><a href="%s">Xác minh email</a></p>
                    <p>Nếu bạn không yêu cầu,
                       có thể bỏ qua thư này.</p>
                  </body>
                </html>
                """.formatted(safeUrl);

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom(properties.senderAddress());
        helper.setTo(issued.recipient());
        helper.setSubject("Xác minh địa chỉ email");
        helper.setText(plain, html);

        sender.send(mime);
    }
}
```

**Lưu ý về khối code:** Java text block có quy tắc nối chuỗi và dấu xuống dòng riêng; ví dụ tập trung vào việc truyền một `plain` và một `html` tương đương. Trong dự án thực tế, một template engine có HTML escaping rõ và một plain-text renderer thường dễ quản lý hơn. Khi code được dùng trong project, nên viết helper format link rõ ràng thay vì lạm dụng chuỗi ghép trong template.

### Vì sao dùng MimeMessageHelper?

- Tạo `text/plain` và `text/html` cùng nội dung.
- Hỗ trợ charset UTF-8 cho tiếng Việt.
- Có thể mở rộng inline logo hoặc attachment khi thực sự cần.
- Tách business service khỏi API MIME/Jakarta Mail.

Không đặt email verification token trong `Subject` hoặc custom headers. Subject và headers có thể được hiển thị/lưu/ghi log rộng hơn body, còn raw token đã nằm trong link nên cần giảm thêm các bản sao.

## 28. Chú ý link token và privacy

Link dạng query parameter có thể bị lưu trong:

- Browser history.
- Proxy/server access logs nếu request đi tới URL.
- Client diagnostics hoặc support screenshots.
- Referrer khi trang có third-party resources nếu cấu hình sai.
- Email security scanning/logging.

Vì vậy trang confirmation nên:

- Có HTTPS và policy Referrer-Policy hạn chế.
- Không tải analytics/third-party scripts mang theo full URL có token.
- Không in token trong application logs.
- Sau khi đọc token, xóa nó khỏi URL đang hiển thị khi phù hợp với thiết kế frontend.
- Chỉ gửi token tới endpoint xác minh được bảo vệ, không gắn token vào nhiều redirects.
- Dùng token short-lived, one-time và ràng buộc đúng account/action.

Có thể cân nhắc fragment-based link hoặc phương thức khác để giảm server-side URL logging, nhưng phải đánh giá client compatibility, link scanner và UX; không có một mẫu URL bảo đảm an toàn tuyệt đối.

## 29. Facade điều phối request trong bản học tập

`ConfirmationIssuer` lưu token trong transaction. `ConfirmationMailSender` thực hiện SMTP I/O **sau đó**, bên ngoài transaction này.

```java
package com.example.mailconfirm.service;

import com.example.mailconfirm.mail.ConfirmationMailSender;
import jakarta.mail.MessagingException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;

@Service
public class ConfirmationRequestService {

    private static final Logger log =
            LoggerFactory.getLogger(
                    ConfirmationRequestService.class
            );

    private final ConfirmationIssuer issuer;
    private final ConfirmationMailSender mailSender;

    public ConfirmationRequestService(
            ConfirmationIssuer issuer,
            ConfirmationMailSender mailSender
    ) {
        this.issuer = issuer;
        this.mailSender = mailSender;
    }

    public void request(String rawEmail) {
        issuer.issueIfEligible(rawEmail).ifPresent(issued -> {
            try {
                mailSender.send(issued);
            } catch (MailException | MessagingException ex) {
                // Demo: không lộ account/SMTP reason ra HTTP.
                // Production: persist failure + retry via outbox.
                log.warn(
                        "Confirmation SMTP submit failed; accountId={}",
                        issued.accountId()
                );
            }
        });
    }
}
```

Code này có một số ưu điểm học tập:

- Controller không phụ thuộc trực tiếp SMTP.
- Token hash được persist trước khi gọi `send(...)`.
- Không giữ transaction mở khi SMTP có network latency.
- HTTP response không lộ nội dung SMTP exception.

**Nhưng nó chưa phải giải pháp public-production**:

1. Nếu process chết sau commit token nhưng trước send, không có durable mail work item.
2. Nếu SMTP lỗi, chỉ log mà chưa có retry.
3. Nếu email account không tồn tại, code bỏ qua SMTP nhanh hơn; nếu tồn tại, chờ SMTP. **Response time có thể tiết lộ account existence.**
4. Nếu client retry HTTP, có thể sinh nhiều tokens/emails.
5. Chưa giới hạn tốc độ hoặc abuse.
6. `202` trong demo chỉ phản ánh endpoint đã xử lý lời gọi, không phản ánh một hàng đợi bền vững.

Phần production phía sau giải quyết bằng durable command và outbox, không chỉ thêm `@Async` vào `mailSender.send(...)`.

## 30. Trạng thái token và account không phụ thuộc SMTP

Mô hình trạng thái token:

```text
ISSUED
  |
  +-- user confirms before expiry -> CONSUMED
  |
  +-- time reaches expiry -------> EXPIRED
  |
  +-- account verified by other token -> NO LONGER ELIGIBLE
```

Không cần biến every token thành một JPA state enum nếu `expiresAt` và `usedAt` đủ biểu diễn theo business, nhưng cần nhớ trạng thái này khác **trạng thái gửi email**.

Một token có thể đang hợp lệ dù email chưa được gửi do lỗi transport; đây là lý do nên theo dõi mail notification riêng với token.

## 31. Kiểm tra token bằng transaction

Ta dùng digest của raw token để lookup, khóa token row khi consume, rồi khóa account để bảo đảm trạng thái xác minh nhất quán.

```java
package com.example.mailconfirm.service;

import com.example.mailconfirm.domain.EmailVerificationToken;
import com.example.mailconfirm.domain.UserAccount;
import com.example.mailconfirm.repository.AccountRepository;
import com.example.mailconfirm.repository.EmailVerificationTokenRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;

@Service
public class ConfirmationVerifier {

    private final EmailVerificationTokenRepository tokens;
    private final AccountRepository accounts;
    private final SecureTokenService secureTokens;
    private final Clock clock;

    public ConfirmationVerifier(
            EmailVerificationTokenRepository tokens,
            AccountRepository accounts,
            SecureTokenService secureTokens,
            Clock clock
    ) {
        this.tokens = tokens;
        this.accounts = accounts;
        this.secureTokens = secureTokens;
        this.clock = clock;
    }

    @Transactional
    public void confirm(String rawToken) {
        String hash = secureTokens.hash(rawToken);
        EmailVerificationToken token = tokens
                .findLockedByHash(hash)
                .orElseThrow(InvalidConfirmationToken::new);

        Instant now = clock.instant();
        if (!token.isUsableAt(now)) {
            throw new InvalidConfirmationToken();
        }

        UserAccount account = accounts
                .findLockedById(token.getAccountId())
                .orElseThrow(InvalidConfirmationToken::new);

        if (account.isEmailVerified()) {
            throw new InvalidConfirmationToken();
        }

        // Với đổi email: kiểm tra địa chỉ/version hiện tại
        // vẫn khớp dữ liệu đã được xác minh.
        account.markEmailVerified(now);
        token.consumeAt(now);
    }
}
```

Định nghĩa exception riêng:

```java
package com.example.mailconfirm.service;

public class InvalidConfirmationToken
        extends RuntimeException {
}
```

Entity managed bởi JPA sẽ được dirty-check và lưu khi transaction commit. Nếu database schema có nhiều active tokens/account, sau account verified, token còn lại không được xác minh thêm do account check. Có thể cleanup/invalidate chúng theo policy.

### Cẩn thận khi đổi email

Trong dự án thật, phải kiểm tra token xác nhận **đúng email/version đang chờ**. Ví dụ user yêu cầu xác minh A, sau đó đổi sang B; token A không được phép đánh dấu B là verified. Bài dùng một trường email cố định để tập trung vào endpoint; một luồng đổi email cần schema bổ sung như `pending_email`/`target_email_hash`/`email_version`.

## 32. Error mapping cho confirm endpoint

`InvalidConfirmationToken` có thể trả một thông báo generic:

```java
package com.example.mailconfirm.api;

import com.example.mailconfirm.service.InvalidConfirmationToken;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidConfirmationToken.class)
    public ResponseEntity<Void> invalidToken() {
        return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
```

Không cần trả:

```json
{
  "tokenExists": true,
  "accountEmail": "somebody@example.net",
  "expiredAt": "..."
}
```

cho một caller không có quyền. Có thể có UX hướng dẫn “Liên kết không hợp lệ hoặc đã hết hạn; hãy yêu cầu thư mới”, nhưng nội dung và API diagnostics không được giúp đoán token hoặc account.

## 33. Token có phải dùng một lần không?

Có. Khi một token đã được consume:

```text
First confirmation POST -> success / 204
Second POST with same token -> invalid / generic rejection
```

Trong một hệ thống có UX idempotent, có thể cho user đã đăng nhập thấy trạng thái “Email đã xác minh” qua endpoint account riêng. Không cần làm cho mọi raw token cũ còn hợp lệ chỉ để thứ hai trả `204`.

### Tại sao phải locking?

Không có kiểm soát concurrency:

```text
Thread A: find token used_at = null
Thread B: find token used_at = null
Thread A: set used_at = now
Thread B: set used_at = now
```

Nếu cùng token dùng để cấp thêm quyền, điều này nghiêm trọng. JPA pessimistic lock hoặc atomic UPDATE có predicate `used_at IS NULL AND expires_at > now()` giúp thiết kế use-once chắc hơn.

## 34. Rate limit là một yêu cầu bắt buộc

Một endpoint public có thể bị dùng để spam email. Các giới hạn gợi ý:

- Tối đa N requests/IP trong một cửa sổ.
- Tối đa N requests/email/account trong một cửa sổ.
- Cooldown giữa hai thư gửi tới cùng account.
- Giới hạn số active tokens.
- Giới hạn tổng traffic theo tenant/project.
- CAPTCHA hoặc challenge khi có hành vi đáng ngờ.
- Tăng kiểm soát khi IP/proxy có hành vi bất thường.
- Theo dõi bounce/complaint/suppression từ provider.

Các giá trị N phải dựa vào usage/abuse profile, không có một ngưỡng chuẩn cho mọi ứng dụng. Với nhiều application instances, counter/rate limiter phải có **shared backing store hoặc enforcement ở gateway**; dùng biến static trong JVM chỉ bảo vệ một node.

### Chống spam mà không làm lộ account

Nếu endpoint trả `429` chỉ khi email tồn tại, kẻ tấn công có thể phân biệt accounts theo response. Có thể dùng rate limits kết hợp trên IP, identity và giá trị được chuẩn hóa/băm phù hợp, đồng thời giữ generic response khi bỏ qua yêu cầu không đủ điều kiện. Không log địa chỉ raw trong metric labels.

## 35. Account enumeration qua thời gian phản hồi

Một lỗi nguy hiểm:

```java
if (accountNotFound) {
    return 202;          // 2ms
}
mailSender.send(email);   // 700ms
return 202;
```

Body và status đều giống nhau nhưng timing khác biệt. Khi lặp nhiều lần, attacker có thể suy ra email đã đăng ký.

**Cách tốt hơn:** tách HTTP acceptance khỏi lookup/account-specific SMTP I/O. Endpoint ghi một **durable request command** theo contract, trả generic `202`; một worker khác quyết định có account nào đủ điều kiện và có nên gửi không.

Không kỳ vọng random sleep hay thêm delay cố định là biện pháp hoàn chỉnh; các side effects, status/headers, rate limit và độ trễ phân phối vẫn phải được thiết kế phù hợp.

## 36. Tạo request từ phiên đăng nhập giảm bề mặt lạm dụng

Nếu chỉ có authenticated user yêu cầu xác minh email của mình, endpoint có thể như:

```java
@PostMapping("/me/email-verification-request")
public ResponseEntity<Void> requestForCurrentUser(
        Authentication authentication
) {
    UUID accountId = currentAccountId(authentication);
    confirmationCommands.enqueueForAccount(accountId);
    return ResponseEntity.accepted().build();
}
```

`currentAccountId(...)` và `confirmationCommands` là abstractions do ứng dụng định nghĩa; example giả định security filter đã xác thực session/principal.

Không chấp nhận account ID lấy từ request body nếu endpoint chỉ cho user hiện tại, trừ khi đã có authorization check tường minh. Với backend-for-frontend có session cookie, cần thiết kế CSRF protection cho POST tương ứng.

## 37. CORS không phải authorization

Nếu frontend khác origin, ứng dụng có thể cần cấu hình CORS để trình duyệt gửi request. Nhưng:

- CORS là cơ chế browser, không ngăn client HTTP khác gửi request.
- CORS không chứng minh người gọi có quyền gửi thư tới mailbox.
- Wildcard origin cùng credentials thường không phù hợp cho authenticated endpoint.
- CSRF và authentication là các bài toán riêng.

Không bật `@CrossOrigin("*")` một cách tùy tiện để chữa một lỗi frontend rồi bỏ qua rate limit/permission.

## 38. Idempotency khi người dùng bấm nút nhiều lần

Một user có thể:

- Double-click “Gửi”.
- Refresh page.
- Mất phản hồi HTTP rồi retry.
- Dùng mobile app có retry interceptor.
- Mở hai tab và gửi cùng lúc.

Nếu mỗi request tạo một token và gửi một email:

```text
request-1 -> token A -> email A
request-2 -> token B -> email B
request-3 -> token C -> email C
```

Điều này làm mailbox bị flood và tăng khả năng nhầm link.

Một API có thể nhận `Idempotency-Key` do client tạo và scope theo actor/action, nhưng phải lưu key bền vững, có TTL và không để key của một user ảnh hưởng user khác. Ngoài ra cần **cooldown** để ngăn nhiều yêu cầu có idempotency keys khác nhau.

Đừng coi `Idempotency-Key` là bí mật xác thực; nó chỉ là khóa chống thực hiện trùng một request logic.

## 39. Response body generic cho UX

Một sản phẩm có thể chọn response:

```json
{
  "message": "Nếu địa chỉ đủ điều kiện, thư xác nhận sẽ được gửi."
}
```

Với public endpoint, câu này không xác nhận account có tồn tại. Để người dùng không bị kẹt, frontend có thể hiển thị:

> Nếu chưa thấy thư, hãy kiểm tra thư rác hoặc thử lại sau ít phút.

Tuy nhiên, **đừng nói “Email đã gửi thành công” ngay khi API chỉ ghi yêu cầu vào queue**. Câu chữ phải phù hợp mức độ mà backend đã thực sự xác nhận.

## 40. Những thứ không nên đưa vào logs

Không log:

```text
rawToken
confirmationLink with query token
email body
SMTP password
full MimeMessage
authorization header
unmasked recipient email (nếu không cần)
```

Ví dụ log an toàn hơn:

```text
event=email_confirmation_requested
requestId=opaque-request-id
flow=signup-email-verification
result=accepted
```

Đối với worker:

```text
event=email_confirmation_smtp_attempt
notificationId=opaque-notification-id
attemptId=opaque-attempt-id
providerRoute=transactional
status=SUBMITTED
```

Không ghi raw token vào exception hoặc vào JSON response khi xảy ra lỗi template/SMTP.

## 41. Config cho email nội dung: From, Reply-To, Subject

Một email xác nhận nên có:

- `From` domain được hệ thống cấp quyền.
- `Subject` rõ, không chứa token.
- `Reply-To` nếu có kênh hỗ trợ.
- Plain text và HTML tương đương.
- Nội dung “nếu không yêu cầu thì bỏ qua”.
- Thông tin hết hạn theo chính sách thực tế.
- Link về domain chính thức (HTTPS).

Không cho public request chọn `From` hoặc tùy ý cung cấp HTML để tránh biến endpoint thành mail relay.

### SMTP authentication và domain reputation

Khi đi production, kiểm tra SPF, DKIM, DMARC và chính sách From của provider để giảm spoofing/delivery problems. Một `JavaMailSender.send(...)` thành công không bảo đảm email được đưa vào Inbox hoặc người dùng mở được link.

## 42. Vì sao bản demo chưa đủ độ tin cậy cho production?

Xét luồng:

```text
HTTP request
   |
   v
INSERT token_hash  -- database COMMIT
   |
   X  process crashes
   |
   v
JavaMailSender.send(...) never happens
```

Tài khoản có token hợp lệ trong database nhưng người dùng không nhận được email. Tương tự, khi SMTP server từ chối tạm thời hoặc hết quota, bản demo không có retry job.

Một giải pháp khác thường được đề xuất là `@Async` hoặc `CompletableFuture.runAsync(...)`. Chúng có thể giảm latency, nhưng không tự tạo durability: process restart trước khi thread thực thi vẫn mất công việc. Muốn phục hồi, **ý định gửi phải được lưu bền vững**.

## 43. Kiến trúc production: nhận request bền vững trước

Một public endpoint nên tách acceptance khỏi account lookup và SMTP:

```text
Client
  |
  v
POST /api/email-confirmations/requests
  |
  v
Input validation + rate limit
  |
  v
Persist durable confirmation request command
  |
  v
Commit
  |
  v
HTTP 202 Accepted
                |
                v
        Command worker
          - decrypt/resolve recipient
          - check eligibility/cooldown
          - create token + digest
          - create encrypted mail outbox work
                |
                v
          Mail worker
            - claim notification
            - decrypt token just-in-time
            - render MIME
            - SMTP submit
            - record attempt outcome
```

Với endpoint authenticated, command có thể chỉ cần `accountId` và action type. Với endpoint public nhận `email`, payload email cần được bảo vệ vì nó là PII; tránh đưa raw email vào queue logs hoặc metrics.

**Không trả `202` trước khi ghi thành công durable command**, nếu API contract nói đã tiếp nhận. Nếu database/queue không sẵn sàng, trả lỗi service phù hợp thay vì báo thành công rồi âm thầm mất request.

## 44. Database schema minh họa cho durable command

```sql
CREATE TABLE email_confirmation_request (
    request_id UUID PRIMARY KEY,
    recipient_ciphertext BYTEA,
    recipient_cipher_metadata JSONB,
    actor_account_id UUID,
    action_type VARCHAR(40) NOT NULL,
    state VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    retry_after TIMESTAMPTZ,
    processed_at TIMESTAMPTZ
);

CREATE INDEX ix_confirmation_command_pending
    ON email_confirmation_request(created_at, request_id)
    WHERE state = 'PENDING';
```

Đây là **schema minh họa**, chưa có đủ key management/tenancy/retention constraints. `recipient_ciphertext` là dữ liệu được mã hóa bằng hệ thống ứng dụng quản lý; không tự mã hóa bằng Base64. `actor_account_id` chỉ nên chứa ID đã được xác thực/ủy quyền nếu có.

Một vài hệ thống có thể lưu command trong durable broker thay vì database. Khi ấy cần hiểu publish acknowledgment, persistence và retry semantics của broker.

### Tránh lưu cả SMTP email trong request command

Request command nên biểu diễn một ý định:

```text
action=SEND_EMAIL_VERIFICATION
subject=account
accountId or protected address reference
requestId
createdAt
```

Template, sender address, token, HTML và routing nên được backend quyết định sau khi kiểm tra eligibility. Điều này giảm cơ hội biến endpoint thành relay tùy ý.

## 45. Nạp công việc bằng transaction ngắn

Với authenticated account:

```java
@Transactional
public UUID enqueueVerificationForCurrentAccount(
        UUID authenticatedAccountId
) {
    UUID requestId = UUID.randomUUID();

    confirmationCommands.insertPending(
            requestId,
            authenticatedAccountId,
            "VERIFY_OWN_EMAIL"
    );

    return requestId;
}
```

`confirmationCommands` là repository do ứng dụng tự xây. Đối với public email input, cần encrypted recipient reference/canonicalization policy; không lưu raw email vào command để tiện debug.

Hàm chỉ ghi DB; nó không thực hiện SMTP trong transaction. Một worker nhận command sau commit. Không cần trả `requestId` cho public client nếu ID đó vô tình cho phép truy vấn thông tin account.

## 46. Token và mail outbox phải được tạo cùng transaction

Command worker có thể:

```text
Claim request command
      |
      v
Find eligible account
      |
      v
Generate random raw token
      |
      v
SHA-256 digest -> verification_token
      |
      v
Encrypt raw token -> mail_outbox_payload
      |
      v
INSERT notification PENDING
      |
      v
Mark command MATERIALIZED
      |
      v
COMMIT
```

**Quan trọng:** nếu insert token digest thành công nhưng tạo outbox thất bại, transaction phải rollback cùng nhau. Nếu outbox có mail cần gửi nhưng token hash không tồn tại, người dùng sẽ nhận link không bao giờ xác minh được.

Ví dụ khung service:

```java
@Transactional
public void materializeRequest(UUID requestId) {
    ConfirmationRequest command =
            commands.lockPending(requestId);

    if (!eligible(command)) {
        commands.markSuppressed(requestId);
        return;
    }

    String rawToken = secureTokens.newToken();
    String tokenHash = secureTokens.hash(rawToken);
    Instant expiresAt = clock.instant().plus(tokenTtl);

    tokenRepository.insert(
            command.accountId(),
            tokenHash,
            expiresAt
    );

    EncryptedPayload payload = encryption.encrypt(
            command.accountId(),
            rawToken
    );

    outbox.insertIfAbsent(
            command.logicalRequestKey(),
            payload,
            expiresAt
    );

    commands.markMaterialized(requestId);
}
```

Đoạn code này **giả định** các abstractions do ứng dụng xây: `ConfirmationRequest`, `EncryptedPayload`, repositories, policy, crypto, và constraint chống duplicate. Nó minh họa transaction boundary; không phải code copy vào project chưa định nghĩa classes.

### Quy tắc quan trọng với mật khẩu/token

Raw token chỉ nên xuất hiện trong memory khi phát hành và khi worker dựng email; lúc cần lưu qua restart, nó phải được mã hóa và có TTL. Không dùng token digest từ database để render link: digest là một chiều, không khôi phục raw token được.

## 47. Outbox record và trạng thái gửi

Một schema tham khảo:

```sql
CREATE TABLE mail_outbox (
    notification_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    account_id UUID NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    encrypted_token_payload_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    next_attempt_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    submitted_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ
);

CREATE TABLE mail_submission_attempt (
    attempt_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_outbox(notification_id),
    provider_key VARCHAR(60) NOT NULL,
    status VARCHAR(30) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox(next_attempt_at, notification_id)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
```

`UNIQUE(request_id)` minh họa một command tạo tối đa một notification. Nếu sản phẩm cho phép một request gửi cho nhiều recipients hoặc nhiều templates, cần thiết kế business key khác.

Đừng đưa raw token vào `mail_submission_attempt` hoặc logs. State của mail và state của verification token là các vòng đời riêng.

## 48. Claim công việc với nhiều worker

Nếu có nhiều application instances:

```text
Worker A ----+
             +-- shared mail_outbox database
Worker B ----+
             |
             +-- only one valid claim per notification
```

Một pattern PostgreSQL:

```sql
SELECT notification_id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
ORDER BY created_at, notification_id
FOR UPDATE SKIP LOCKED
LIMIT 50;
```

**Query này chưa đủ nếu chỉ SELECT rồi COMMIT**. Phải ghi `PROCESSING`/owner/lease trong cùng transaction trước commit; sau đó mới thực hiện SMTP ngoài transaction.

Nếu worker crash, lease hết hạn và reconciler quyết định cách xử lý tiếp. Không tự coi lease hết hạn đồng nghĩa SMTP chưa submit, đặc biệt khi process chết sau khi gửi DATA.

## 49. Vì sao retry SMTP phải có phân loại

```text
Attempt A
  |
  +-- Connection could not open before DATA
  |       -> known not submitted, retry may be safe
  |
  +-- Temporary 4xx before acceptance
  |       -> retry per provider policy
  |
  +-- Permanent invalid recipient
  |       -> do not retry blindly
  |
  +-- Timeout after SMTP DATA
          -> UNKNOWN: may already be accepted
```

Một lỗi `MailSendException` không chứng minh mọi recipient đều chưa được submit. Có thể có partial acceptance hoặc timeout sau DATA. Retry tự động có thể tạo hai thư chứa hai tokens, gây nhầm lẫn.

### Chính sách đơn giản cho confirmation

- Lỗi chắc chắn trước submission: có thể retry có giới hạn.
- Lỗi vĩnh viễn: ghi `FAILED`, không spam provider.
- Outcome `UNKNOWN`: hạn chế retry mù; reconciliation nếu có bằng chứng provider.
- Token đã hết hạn: không gửi link cũ; cần luồng yêu cầu mới/tái phát hành token theo policy.
- Account đã verified: không gửi lại confirmation vô ích.
- Token hoặc account bị hủy: dừng pending work.

## 50. Khi nào nên cleanup encrypted token?

Không giữ raw token mã hóa vô thời hạn:

```text
PENDING / RETRY_WAIT (valid token)
          |
          +-- still eligible --> retain encrypted payload briefly
          |
          +-- token expired --> cancel pending send

SUBMITTED / FAILED / CANCELED / EXPIRED
          |
          v
Retention decision
          |
          v
Purge encrypted token payload
          |
          v
Keep minimal status/attempt metadata
```

Sau khi SMTP submission hoàn tất, có thể xóa encrypted raw-token payload theo retention policy, còn digest token tồn tại tới khi consume/expire và được dọn theo chính sách. Không xóa token digest khi người dùng còn cần xác minh chỉ vì mail đã được submit; làm vậy link sẽ không hoạt động.

## 51. Tách “đã gửi” khỏi “đã xác minh”

Một số trạng thái cần được quan sát riêng:

| Khái niệm | Trạng thái ví dụ | Ý nghĩa |
| --- | --- | --- |
| Request command | ACCEPTED, MATERIALIZED, SUPPRESSED | Yêu cầu được xử lý thế nào |
| Outbox notification | PENDING, PROCESSING, SUBMITTED, FAILED, UNKNOWN | Thư đã được submit hay chưa |
| Verification token | ISSUED, CONSUMED, EXPIRED | Token còn được sử dụng không |
| Account email | UNVERIFIED, VERIFIED | Quyền kiểm soát email đã được xác nhận chưa |
| Provider feedback | DELIVERED_REMOTE, BOUNCED, DEFERRED | Bằng chứng vận chuyển tới bên nhận |

Một notification `SUBMITTED` nhưng account vẫn `UNVERIFIED` là bình thường. Một email có event `DELIVERED_REMOTE` cũng không chứng minh người nhận đã nhấn xác minh.

## 52. Không lưu trạng thái gửi bằng một boolean

```java
boolean sent;
```

không phân biệt:

- Đã enqueue nhưng chưa worker chạy.
- SMTP submit thành công.
- SMTP timeout với kết quả mơ hồ.
- Provider deferred.
- Email bị bounce.
- User đã xác minh.

Nên có state/attempt ledger và timestamps rõ. API chỉ cần hiển thị mức độ phù hợp cho user; không nhất thiết công khai mọi internal transport detail.

## 53. Nhiều emails xác nhận trong cùng một thời gian

Người dùng bấm gửi lại trong lúc thư trước chưa đến:

```text
Email A sent 10:00 (token A)
Email B sent 10:01 (token B)
Inbox receives B first, then A
```

Cần chính sách rõ ràng:

- Cho phép hai tokens còn hạn và account verify bằng token nào cũng được.
- Hoặc chỉ cho token mới nhất hợp lệ, nhưng UX phải chấp nhận email A đến muộn sẽ báo link expired/invalid.
- Có cooldown để giảm số mail gửi.
- Có thể hiển thị “Chúng tôi vừa gửi gần đây” mà không tiết lộ account public.

Không để hai requests đồng thời tạo một loại trạng thái không nhất quán; sử dụng database constraints/locks và policy kiểm chứng.

## 54. Gửi link theo account đang pending, không theo email user tùy ý

Một endpoint có thể nhận `email` nhưng mail sender không nên chỉ dùng `body.email` để gửi mà chưa tìm account/eligibility:

```text
Input email
   |
   v
Canonicalize according to account policy
   |
   v
Resolve eligible account
   |
   v
Use verified ownership of target/pendingEmail
   |
   v
Create token scoped to account + address
   |
   v
Send to approved target address
```

Trong thực tế, thay đổi email có thể cần xác minh cả địa chỉ cũ/mới hoặc re-authentication tùy mức độ nhạy cảm. Đừng cho client chỉ định `accountId` của người khác và `recipient` bất kỳ để backend gửi một link xác minh cho account không thuộc quyền.

## 55. Sau khi xác minh: trạng thái và quyền

Trong verifier:

```text
Validate token hash + expiry + unused
      |
      v
Check account and pending email scope
      |
      v
Mark email verified
      |
      v
Consume token
      |
      v
Commit transaction
```

Nếu ứng dụng cần kích hoạt các tính năng sau khi verified, có thể phát domain event/outbox **sau khi trạng thái verified được ghi bền vững**. Không cấp quyền dựa trên việc người dùng đã yêu cầu gửi email, và không mở quyền trước khi transaction xác minh commit.

## 56. SMTP errors không nên rò ra public API

Ví dụ không nên:

```json
{
  "error": "Account exists but SMTP provider rejected
            student@example.net due to mailbox policy"
}
```

Một public endpoint chỉ nên trả lỗi hạ tầng generic khi acceptance không thực hiện được. Logs vận hành có thể ghi error category và opaque request/attempt ID.

Với authenticated endpoint, có thể cung cấp UI “Không thể tiếp nhận yêu cầu lúc này, thử lại sau” mà không công khai nội dung provider SMTP response.

### Không im lặng trước việc mất công việc

Ẩn lỗi SMTP khỏi user không có nghĩa được bỏ qua chúng. Production phải lưu outcome, metrics, alerts và có quy trình retry/manual intervention để người dùng thực sự có cơ hội nhận email.

## 57. Các bước chạy bài thực hành ở môi trường local

Một trình tự an toàn:

1. Tạo một dự án Spring Boot theo dependencies ở phần trước.
2. Chạy PostgreSQL test database hoặc database test tương thích.
3. Tạo schema bằng migration (hoặc test schema riêng).
4. Chạy SMTP capture server trên localhost port 1025.
5. Tạo một **account giả chưa verified** trong bảng `user_account`.
6. Cấu hình `app.confirmation.base-url` trỏ tới trang xác nhận local/staging.
7. Start Spring Boot application.
8. Gửi POST request vào endpoint.
9. Mở giao diện SMTP capture server để xem email.
10. Lấy link test và xác nhận bằng `POST /confirm`.
11. Kiểm tra account verified state và token consumed.

### Tạo account giả

Ví dụ dữ liệu synthetic:

```sql
INSERT INTO user_account (
    id, email_canonical, email_verified_at
)
VALUES (
    '5b3a0fd5-a196-4cc0-b9a7-165829479de4',
    'student@example.net',
    NULL
);
```

**Không dùng địa chỉ của người thật khi SMTP client có thể gửi ra Internet**. Nếu dùng SMTP capture local, message sẽ bị giữ trong test server; không khuyến khích phát thử tới hộp thư không thuộc quyền dự án.

## 58. Gửi HTTP request bằng curl

Ví dụ trên terminal hỗ trợ curl:

```bash
curl -i -X POST \
  'http://localhost:8080/api/email-confirmations/requests' \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.net"}'
```

Phản hồi của demo:

```http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Length: 0
```

Nếu dùng PowerShell 5.1, `curl` có thể là alias của `Invoke-WebRequest`; dùng `curl.exe` hoặc `Invoke-RestMethod` với body JSON phù hợp.

### Chú ý kết quả

`202` không bảo đảm:

- Hộp thư đã nhận email.
- Token còn hiệu lực khi user mở.
- Provider đã delivered.
- Người dùng đã xác minh.

Trong bản demo đồng bộ, service đã *thử* gọi mail sender khi account đủ điều kiện; nhưng API contract không công khai chi tiết và vẫn thiếu durability.

## 59. Đọc thư trên SMTP sandbox

Trong một giao diện SMTP capture:

- Tìm Subject “Xác minh địa chỉ email”.
- Kiểm tra recipient là tài khoản giả.
- Kiểm tra `From` đúng sender test.
- Xem text/plain và text/html.
- Xác nhận link thuộc local/staging origin.
- Không có token trong Subject.
- Không có user-supplied HTML độc hại.

Một SMTP capture server có thể cho xem raw MIME và HTML preview, nhưng preview không thay thế kiểm thử thực tế trên Gmail, Outlook hoặc Apple Mail nếu sản phẩm có yêu cầu tương thích client.

## 60. Gọi endpoint xác nhận

Sau khi lấy raw token từ link test trong SMTP sandbox, gọi:

```bash
curl -i -X POST \
  'http://localhost:8080/api/email-confirmations/confirm' \
  -H 'Content-Type: application/json' \
  -d '{"token":"PASTE_SYNTHETIC_TEST_TOKEN_HERE"}'
```

Nếu token hợp lệ và chưa hết hạn:

```http
HTTP/1.1 204 No Content
Cache-Control: no-store
```

Nếu token không hợp lệ, đã dùng hoặc hết hạn, ví dụ:

```http
HTTP/1.1 400 Bad Request
Cache-Control: no-store
```

Không paste token thật vào issue tracker, screen recording hoặc command history ở môi trường production. Trong thực hành local, chỉ dùng synthetic test account.

## 61. Những gì cần xem trong database sau khi xác nhận

Trước khi confirm:

```text
user_account.email_verified_at = NULL
email_verification_token.used_at = NULL
email_verification_token.expires_at > now
```

Sau khi confirm:

```text
user_account.email_verified_at = timestamp
email_verification_token.used_at = timestamp
```

Nếu gọi cùng token lần thứ hai, trạng thái không được thay đổi thêm và verifier phải từ chối theo contract. Với nhiều active tokens/account, những token còn lại cũng phải bị chặn bởi `account.isEmailVerified()`.

## 62. Unit test: token ngẫu nhiên và hash nhất quán

```java
import org.junit.jupiter.api.Test;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import static org.junit.jupiter.api.Assertions.*;

class SecureTokenServiceTest {

    private final SecureTokenService service =
            new SecureTokenService();

    @Test
    void generatesUrlSafeTokensAndStableHashes() {
        String a = service.newToken();
        String b = service.newToken();

        assertNotEquals(a, b);
        assertTrue(a.matches("[A-Za-z0-9_-]+"));
        assertEquals(64, service.hash(a).length());
        assertEquals(service.hash(a), service.hash(a));
        assertNotEquals(service.hash(a), service.hash(b));
    }

    @Test
    void doesNotRepeatInSmallTestSample() {
        Set<String> tokens = IntStream.range(0, 1000)
                .mapToObj(i -> service.newToken())
                .collect(Collectors.toSet());

        assertEquals(1000, tokens.size());
    }
}
```

Test 1.000 tokens chỉ giúp bắt lỗi implementation hiển nhiên, **không chứng minh độ an toàn mật mã**. Bảo mật dựa trên `SecureRandom`/entropy và policy quản lý secret, không dựa trên một bài test random sample.

## 63. Unit test: expiry boundary

Ví dụ kiểm tra logic entity với clock cố định:

```java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class VerificationTokenExpiryTest {

    @Test
    void expiresExactlyAtDeadline() {
        Instant issuedAt =
                Instant.parse("2026-11-12T03:00:00Z");
        Instant expiresAt = issuedAt.plusSeconds(900);

        var token = new EmailVerificationToken(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "a".repeat(64),
                issuedAt,
                expiresAt
        );

        assertTrue(
                token.isUsableAt(expiresAt.minusNanos(1))
        );
        assertFalse(token.isUsableAt(expiresAt));
        assertFalse(token.isUsableAt(expiresAt.plusSeconds(1)));
    }
}
```

Không dùng `Thread.sleep(900_000)` để test TTL. Với `Clock.fixed` và explicit `Instant`, tests nhanh và deterministic hơn.

## 64. Web test: controller trả 202 và gọi service

Có thể dùng `MockMvc` ở mức standalone:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EmailConfirmationControllerTest {

    @Test
    void requestReturnsAcceptedWithoutToken() throws Exception {
        ConfirmationRequestService requests =
                mock(ConfirmationRequestService.class);
        ConfirmationVerifier verifier =
                mock(ConfirmationVerifier.class);

        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new EmailConfirmationController(
                        requests, verifier
                )
        ).build();

        mvc.perform(post("/api/email-confirmations/requests")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"student@example.net"}
                                """))
                .andExpect(status().isAccepted())
                .andExpect(content().string(""));

        verify(requests).request("student@example.net");
        verifyNoInteractions(verifier);
    }
}
```

Test này kiểm tra controller routing và response shape, **không kiểm tra Spring Security filter/rate limiting** nếu các filter chưa được thêm vào standalone setup. Với authentication/CSRF cần integration/web security tests phù hợp.

## 65. Web test: validation

Các trường hợp:

| Input | Kỳ vọng |
| --- | --- |
| JSON rỗng hoặc thiếu email | 400 do validation |
| `email=""` hoặc chỉ whitespace | 400 |
| Giá trị không có dạng email theo validator | 400 |
| Vượt giới hạn kích thước | 400 |
| JSON sai cú pháp | 400 |
| Email hợp lệ nhưng account không tồn tại | Generic 202 cho public API |
| Email đã verified | Generic 202 cho public API |
| Quá rate limit | Theo rate-limit policy, không lộ account |

Để test `@Valid` thực sự hoạt động, dùng `@WebMvcTest` với validator được cấu hình hoặc cung cấp `LocalValidatorFactoryBean` cho standalone `MockMvc`. Một test chỉ gọi thẳng controller method **không thực hiện** validation annotations.

## 66. Unit test: verifier dùng token một lần

Các tình huống cần có:

1. Token hash tìm được, chưa dùng, chưa hết hạn, account chưa verified → đánh dấu verified và consume.
2. Token không tồn tại → generic error.
3. Token đã used → generic error.
4. Token hết hạn đúng boundary → generic error.
5. Account đã verified → không tăng quyền/hành động lần nữa.
6. Token gắn với account đã bị xóa → generic error.
7. Account email/version đã thay → không xác minh địa chỉ mới bằng token cũ.
8. Hai threads cùng sử dụng token → chỉ một transaction thành công.

Test cuối cần một DB integration test có locking/atomic UPDATE thực tế; chỉ mock repository tuần tự không chứng minh concurrency correctness.

## 67. Database integration test: uniqueness và lock

Với PostgreSQL test database:

- Insert account chưa verified.
- Issue token và xác nhận digest được lưu, raw token không xuất hiện trong row.
- Hai confirm requests đồng thời với cùng token.
- Kiểm tra một request chuyển account verified và token consumed; request còn lại generic fail.
- Kiểm tra transaction rollback nếu cập nhật token hoặc account thất bại.
- Kiểm tra index/unique constraints bảo đảm lookup hiệu quả.

Sử dụng transaction barriers/latches có timeout hữu hạn; không dựa vào `Thread.sleep(...)` để tạo race.

Khi chuyển email cho account trong một transaction khác, cần test rằng verifier không xác minh nhầm địa chỉ mới.

## 68. SMTP integration test với GreenMail

Một SMTP test server có thể nhận mail do `JavaMailSender` gửi mà không ra Internet:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import java.time.Instant;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class ConfirmationMailSenderIntegrationTest {

    @Test
    void sendsConfirmationToLocalSmtp() throws Exception {
        GreenMail smtp = new GreenMail(
                new ServerSetup(0, "127.0.0.1", "smtp")
        );
        smtp.start();

        try {
            JavaMailSenderImpl javaMailSender =
                    new JavaMailSenderImpl();
            javaMailSender.setHost("127.0.0.1");
            javaMailSender.setPort(smtp.getSmtp().getPort());

            var props = new ConfirmationProperties(
                    java.net.URI.create(
                            "https://staging-account.example.org"
                    ),
                    "mail-test@example.org",
                    java.time.Duration.ofMinutes(15)
            );
            ConfirmationMailSender mail =
                    new ConfirmationMailSender(
                            javaMailSender, props
                    );

            mail.send(new IssuedConfirmation(
                    UUID.randomUUID(),
                    "student@example.net",
                    "SYNTHETIC_TEST_TOKEN",
                    Instant.now().plusSeconds(900)
            ));

            assertTrue(smtp.waitForIncomingEmail(5000, 1));

            MimeMessage received =
                    smtp.getReceivedMessages()[0];
            assertEquals(
                    "Xác minh địa chỉ email",
                    received.getSubject()
            );
            assertTrue(
                    received.isMimeType("multipart/*")
            );
        } finally {
            smtp.stop();
        }
    }
}
```

Test cần dependency GreenMail phù hợp namespace Jakarta Mail của project. Test này xác nhận SMTP local nhận message và Subject/MIME ở mức cơ bản; **không chứng minh Gmail/Outlook render đúng** hoặc user đã click.

### Không dùng production credentials khi test

`JavaMailSenderImpl` ở test phải trỏ đến localhost/sandbox; không lấy host/password từ profile production. Không đưa raw test token vào test logs nếu suite lưu dữ liệu ngoài môi trường.

## 69. Kiểm tra MIME parts và links bằng parser

Trong test nâng cao:

1. Traverse `MimeMessage` và nested `Multipart`.
2. Xác nhận có phần `text/plain` và `text/html`.
3. Đọc decoded UTF-8 content.
4. Kiểm tra cả hai có lời nhắc xác minh và link chứa test token tương ứng.
5. Kiểm tra Subject và From.
6. Kiểm tra MIME không có attachment bất ngờ.
7. Kiểm tra raw token không nằm trong Subject/custom headers.
8. Mở trong ít nhất một mail client test thực tế để xác nhận CTA có thể sử dụng.

Không so raw MIME bytes đơn thuần vì Content-Transfer-Encoding có thể khác và MIME boundary ngẫu nhiên.

## 70. Test account enumeration

Với public request, kiểm tra:

```text
Account exists, unverified -> generic 202
Account exists, verified   -> generic 202
Account not found         -> generic 202
Account in cooldown       -> generic policy response
```

Ngoài status/body/headers, đánh giá **timing distribution** và side effects có thể quan sát bên ngoài. Một test đơn lẻ so latency không đủ chứng minh chống timing attack; nên thiết kế architecture async/durable trước, sau đó dùng load/security testing theo khả năng.

Không trả một `Location` URL cho phép query trạng thái account bằng public request ID mà không có authorization.

## 71. Test rate limiting và idempotency

Các case:

- Double-click một lần, cùng idempotency key.
- Retry sau HTTP timeout, cùng key.
- Hai keys khác nhau trong cooldown window.
- Cùng IP nhiều địa chỉ.
- Cùng email từ nhiều IP khác nhau.
- Hai application instances cùng nhận request.
- Restart rate limiter backing store.
- Provider 4xx/5xx hoặc quota exceeded.

Mục tiêu không phải “không bao giờ gửi mail thứ hai”, mà là **không bị spam, không tạo request trùng ngoài policy và vẫn có con đường resend hợp lệ**.

## 72. Test SMTP failure và recovery

Một ma trận:

| Kịch bản | Kết quả dự kiến |
| --- | --- |
| SMTP connection refused trước submission | Attempt fail, policy có thể retry |
| SMTP auth sai | Alert/config failure, không retry liên tục |
| SMTP temporary rejection | Retry/backoff theo giới hạn |
| SMTP permanent invalid recipient | Không retry vô hạn |
| Timeout sau DATA | `UNKNOWN`, không tự gửi lại mù |
| Process crash sau token commit trước send (demo) | Nhận biết lỗ hổng; production outbox phải phục hồi |
| Process crash sau outbox commit trước worker | Work item còn tồn tại để xử lý |
| Process crash sau SMTP accepted trước status update | Tránh duplicate bằng attempt/reconciliation policy |
| Token hết hạn trước khi retry | Cancel hoặc issue new request theo policy |
| Account đã verified trước worker send | Suppress pending confirmation nếu policy phù hợp |

Một vài SMTP providers cung cấp API để tra cứu message ID/status, nhưng không phải mọi SMTP relay đều có; thiết kế `UNKNOWN` phải trung thực khi không có bằng chứng.

## 73. Test logging và privacy

Fixture dùng:

```text
TEST-SYNTHETIC-CONFIRMATION-TOKEN
```

Trong unit/integration tests, chụp application logs khi:

- Issue token.
- MailSender gửi thành công.
- SMTP ném exception.
- Token không hợp lệ.
- Rate limit bị kích hoạt.
- Cleanup token/outbox.

Kiểm tra token không xuất hiện trong logs hoặc exception serialization; request body chứa raw token của `/confirm` cũng không được ghi lại bởi middleware/tracing.

**Không dùng marker test làm bằng chứng an ninh tuyệt đối**: cần review HTTP access logs, reverse proxy, APM, exception reporting và email provider logs.

## 74. Test cleanup token đã hết hạn

Token table sẽ tăng theo số requests:

```text
ISSUED -> CONSUMED
ISSUED -> EXPIRED
```

Một cleanup job định kỳ có thể xóa token records đã dùng/hết hạn sau retention phù hợp. Nếu cần audit, lưu metadata tối thiểu khác, không giữ token hash/raw link vô hạn.

Với encrypted raw token ở outbox production, cleanup phải tách:

- Dữ liệu cần cho retry trước expiry.
- Dữ liệu đã submit.
- Dữ liệu hết hạn/hủy.
- Attempts có outcome `UNKNOWN` cần policy reconciliation.

Không xóa dữ liệu đang được worker sử dụng mà không kiểm tra lease/retention.

## 75. Test trên mail client thật

Một email verification phải hoạt động trên mobile:

- Subject tiếng Việt có dấu đúng.
- Link/CTA vẫn thấy khi ảnh bị tắt.
- Text/plain có link đầy đủ.
- Dark mode không làm chữ chìm vào background.
- Cỡ chữ đủ lớn để đọc.
- CTA mở trang xác nhận ở đúng domain.
- Trang xác nhận không bị tự kích hoạt bởi link preview.
- Token không bị cắt hoặc sửa khi copy/paste.
- Không có dữ liệu cá nhân nhạy cảm trong preheader.

GreenMail/Mailpit giúp test MIME nhưng không thay thế việc mở email bằng Gmail, Outlook, Apple Mail hoặc những clients đại diện cho sản phẩm.

## 76. Observability: metric cho HTTP acceptance

Không đặt tên metric `emails_sent_total` tại controller, vì lúc đó email chưa chắc đã được submit.

Một số metric gợi ý:

```text
confirmation.http.requests.total
confirmation.http.accepted.total
confirmation.http.rejected.total
confirmation.requests.rate_limited.total
confirmation.command.pending
confirmation.command.processing.lag
confirmation.token.issued.total
confirmation.token.consumed.total
confirmation.token.expired.total
confirmation.mail.outbox.pending
confirmation.mail.smtp.attempted.total
confirmation.mail.smtp.submitted.total
confirmation.mail.smtp.unknown.total
confirmation.mail.smtp.failed.total
```

Đây là tên metric do ứng dụng có thể tự định nghĩa, không phải tên mặc định của Spring Mail. Có thể dùng Micrometer/Actuator theo stack dự án.

**Không đưa email address, raw token, full URL hoặc account ID có cardinality cao vào metric labels.** Các thông tin cụ thể dành cho log/audit có quyền riêng.

## 77. Những mốc thời gian cần theo dõi

```text
requestedAt
acceptedAt
materializedAt
firstAttemptAt
submittedAt
tokenExpiresAt
confirmedAt
```

Có thể đo:

```text
Acceptance latency = acceptedAt - requestedAt
Dispatch lag       = firstAttemptAt - acceptedAt
SMTP latency       = smtp result time - firstAttemptAt
Time to verify     = confirmedAt - submittedAt
```

Khi chưa có `submittedAt` (ví dụ SMTP vẫn pending), không nên gán latency bằng 0. Với public API không tiết lộ account existence, metric nội bộ có thể chi tiết theo trạng thái nhưng phải được bảo vệ.

### Mục tiêu SLO minh họa

> 99% các request đủ điều kiện được ghi bền vững trong vòng một khoảng ngắn; đa số notification đủ điều kiện được thử SMTP trong một cửa sổ có giới hạn, trừ khi provider throttling.

Không gán con số SLA mà chưa đo latency, quota SMTP, mailbox feedback và khả năng scale của hệ thống.

## 78. Audit cần phân biệt yêu cầu, phát token, gửi và xác minh

Một record audit có thể có:

```text
event = EMAIL_CONFIRMATION_REQUEST_ACCEPTED
requestId = opaque ID
timestamp = ...

event = VERIFICATION_TOKEN_ISSUED
notificationId = opaque ID
timestamp = ...

event = MAIL_SMTP_SUBMITTED
attemptId = opaque ID
timestamp = ...

event = EMAIL_VERIFIED
accountId = opaque ID
timestamp = ...
```

Không có event `EMAIL_VERIFIED` chỉ vì `MAIL_SMTP_SUBMITTED` đã được ghi. Tương tự, một provider delivered event không tự chứng minh user đã click link.

Không lưu toàn bộ raw SMTP transcript hoặc token trong audit log. Nếu cần forensic evidence, có retention và quyền phù hợp cho từng loại dữ liệu.

## 79. Runbook: POST trả 202 nhưng không có email

Các bước:

1. Xác định `requestId`/test actor và thời điểm gọi (không cần raw token).
2. Kiểm tra request command đã persist chưa.
3. Kiểm tra worker có claim command không.
4. Kiểm tra eligibility: account pending, verified hay cooldown.
5. Xem outbox notification có được materialize không.
6. Xem SMTP attempt log đã gọi mail sender chưa.
7. Kiểm tra provider acceptance/rejection, network, TLS, auth.
8. Kiểm tra mailbox test và Spam/Junk/Quarantine.
9. Kiểm tra token có hết hạn trước khi thư tới không.
10. Không tự resend cùng raw token nếu trạng thái/TTL không còn hợp lệ.

Với public endpoint, người dùng chỉ thấy generic response. Việc điều tra nội bộ nên có correlation IDs nhưng không được mở API truy vấn account existence cho người lạ.

## 80. Runbook: người dùng nhận nhiều email xác nhận

Những nguyên nhân cần xét:

- Double-click/retry HTTP.
- Thiếu cooldown.
- Worker claim trùng sau lease timeout.
- Duplicate queue delivery.
- Retry SMTP sau outcome `UNKNOWN`.
- Hai application instances cùng xử lý không có unique constraint.
- Một tài khoản có nhiều tokens chưa hết hạn.

Khắc phục:

1. Tìm logical request ID và các notification IDs.
2. Xem có phải một notification có nhiều SMTP attempts không.
3. Xác định attempts nào được provider chấp nhận.
4. Xem idempotency key và cooldown policy.
5. Kiểm tra worker concurrency/lease.
6. Cân nhắc giảm auto retry trong trường hợp unknown.

Không xóa lịch sử attempts để dashboard trông sạch; cần giữ bằng chứng vừa đủ để biết duplicate phát sinh ở tầng nào.

## 81. Runbook: user nhấn link nhưng token invalid

Kiểm tra:

- Token thực sự nằm trong database digest lookup không?
- Token đã hết hạn?
- Token đã used?
- Account đã verified bởi token khác?
- User có đổi email giữa lúc issue và confirm?
- Link bị client rewrite/encode sai?
- Frontend có gửi nguyên `token` hay đã cắt ở ký tự đặc biệt?
- Token có bị security scanner hoặc link preview sử dụng theo endpoint GET tự động không?

Với Base64URL không padding, token có ký tự an toàn trong URL; dù vậy vẫn phải encode đúng và giữ nguyên chuỗi. Không trả về thông tin nhạy cảm về lý do token invalid cho caller không được xác thực.

### UX khi liên kết hết hạn

Hiển thị một thông báo rõ:

> Liên kết xác minh không còn hợp lệ. Bạn có thể yêu cầu gửi lại thư.

Nếu người dùng ở phiên đã đăng nhập, có thể điều hướng đến authenticated resend flow để giảm account enumeration và spam. Không tự tạo token mới chỉ vì bất kỳ ai gọi một endpoint confirm với token random.

## 82. Runbook: SMTP authentication lỗi

Triệu chứng:

```text
MailAuthenticationException
SMTP AUTH rejected
```

Điều tra:

- Host/port/TLS mode đúng provider?
- Credential đã rotation hoặc hết hạn?
- Account có quyền gửi From domain không?
- Secret injected đúng môi trường?
- Provider có giới hạn IP/region/permission?
- Application có đang retry liên tục gây account lockout?

Không in password hoặc raw AUTH exchange ra log. Nếu lỗi configuration toàn cục, tạm ngừng retry ồ ạt và cảnh báo vận hành.

## 83. Runbook: SMTP chấp nhận nhưng không thấy trong Inbox

`JavaMailSender.send(...)` không lỗi, nhưng user nói chưa nhận.

Các khả năng:

- Provider deferred.
- Mailbox provider bounce/reject sau submission.
- Spam/Junk/Quarantine.
- Suppression list hoặc sender reputation.
- SPF/DKIM/DMARC alignment issues.
- Recipient mailbox rules.
- Link hoặc email bị security gateway xử lý.

Không coi lỗi này chứng minh controller chưa chạy. Kiểm tra provider feedback khi có và hướng dẫn user kiểm tra mailbox phù hợp.

## 84. Runbook: token link bị lộ trong logs

Nếu raw token được ghi trong HTTP access log hoặc exception:

1. Ngăn việc ghi thêm.
2. Xác định nguồn và phạm vi lưu (application/reverse proxy/APM/SIEM).
3. Thu hồi token còn hiệu lực theo incident policy.
4. Xóa/redact bản ghi ở các nơi có khả năng xử lý.
5. Kiểm tra token bị lộ đã được sử dụng chưa, nếu có evidence.
6. Không copy raw token sang ticket/chat khi điều tra.
7. Sửa logging filters, URL handling, frontend referrer policy và tests.

Đừng nghĩ hash token trong database đủ bảo vệ nếu raw token đang nằm trong access log.

## 85. Runbook: token hết hạn trước khi email được gửi

Với backlog SMTP:

```text
Token issued at 10:00, expires 10:15
SMTP worker executes at 10:20
```

Nếu vẫn gửi token, người dùng nhận email vô dụng.

Giải pháp:

- Worker kiểm tra `tokenExpiresAt` trước send.
- Nếu token hết hạn, hủy notification pending và purge encrypted token payload theo policy.
- Nếu cần gửi lại, issue một token mới gắn với một logical request mới, có cooldown/eligibility.
- Không tự kéo dài expiry của token đã phát mà không đánh giá security.
- Theo dõi outbox lag so với TTL.

Một SLA dispatch 20 phút không hợp lý nếu token chỉ sống 15 phút; thiết kế TTL và capacity phải tương thích.

## 86. Runbook: database token hash bị trùng hoặc sai schema

Token 256-bit với SecureRandom rất khó trùng tự nhiên. Nếu unique constraint `token_hash` báo conflict, điều tra:

- Service có đang dùng token generator deterministic/test implementation ở production?
- Token có bị reuse do cache/global state?
- Có bug trong hashing/encoding?
- Database schema có cắt chuỗi hash?
- Có test profile hoặc seed dữ liệu sai?

Không tự bắt conflict rồi bỏ qua mà vẫn gửi email. Nếu hash không được persist, link gửi ra sẽ không xác minh được. Một retry phát token mới có thể hợp lý sau khi phân loại và xử lý transaction.

## 87. Checklist API request

- [ ] Endpoint dùng POST, không làm thay đổi dữ liệu qua GET tùy tiện.
- [ ] DTO có validation và độ dài tối đa.
- [ ] Không cho user tự cung cấp SMTP From/HTML/Subject.
- [ ] Account ownership/eligibility được xác định rõ.
- [ ] Public response không xác nhận account existence.
- [ ] Timing/channel side effects không dễ làm lộ account.
- [ ] Có rate limit, cooldown, abuse monitoring.
- [ ] Có idempotency policy cho double-click/retry.
- [ ] Chỉ trả `202` sau durable acceptance nếu đó là contract.
- [ ] Response không chứa raw token hoặc provider details.
- [ ] Có request ID/log metadata an toàn.
- [ ] Không cache response/token nhạy cảm ngoài policy.

## 88. Checklist token và database

- [ ] Token tạo từ `SecureRandom`, entropy đủ mạnh.
- [ ] Token URL-safe và không chứa dữ liệu đoán được.
- [ ] Chỉ lưu hash/digest trong verification-token table.
- [ ] TTL được validate, dùng `Clock`/`Instant`.
- [ ] Token gắn đúng account và email/version cần xác minh.
- [ ] Consume một lần với locking/atomic update.
- [ ] Từ chối token expired/used/unknown bằng response generic.
- [ ] Không phát hành token vô hạn khi resend liên tục.
- [ ] Token raw nếu nằm trong durable outbox phải được mã hóa.
- [ ] Có cleanup sau expiry/retention.
- [ ] Không log raw token, confirmation URL hoặc template model nhạy cảm.

## 89. Checklist Spring Mail

- [ ] `spring-boot-starter-mail` và Jakarta Mail namespace phù hợp.
- [ ] SMTP host/port/TLS/auth/timeouts đúng provider.
- [ ] From domain được phép gửi.
- [ ] MIME có text/plain và text/html tương đương.
- [ ] Charset UTF-8 cho nội dung tiếng Việt.
- [ ] Link chứa đúng domain cấu hình, không lấy Host header.
- [ ] HTML link được escape/encode đúng.
- [ ] Email vẫn đọc được khi images disabled/dark mode.
- [ ] Không chứa OTP/token trong Subject, filename hoặc headers.
- [ ] SMTP test server và test mailbox được dùng trước production.
- [ ] Không giữ database transaction dài trong lúc SMTP send.

## 90. Checklist outbox/reliability

- [ ] Request được persist trước khi trả `202`.
- [ ] Command worker có claim/lease và xử lý duplicate.
- [ ] Token digest và encrypted outbox được ghi atomically.
- [ ] Mail worker có attempt ID và state.
- [ ] Có retry/backoff cho lỗi tạm thời đã phân loại.
- [ ] Không resend mù attempt có outcome `UNKNOWN`.
- [ ] Account verified/token expired thì pending work bị suppress theo policy.
- [ ] Có retention/purge cho encrypted raw token.
- [ ] Có metrics về queue lag, SMTP failures và token expires.
- [ ] Worker restart/failover không làm mất notification.
- [ ] Không khẳng định exactly-once email delivery khi không có contract.

## 91. Checklist kiểm thử

- [ ] Unit tests cho token generation/hash.
- [ ] Expiry boundary test với fixed clock.
- [ ] Web MVC tests cho `202` và validation.
- [ ] Generic behavior cho unknown/verified email.
- [ ] Concurrency tests cho consume token một lần.
- [ ] SMTP sandbox integration test.
- [ ] MIME plain/HTML/Subject/From tests.
- [ ] Failure tests cho SMTP 4xx/5xx/timeout.
- [ ] Process crash/restart tests cho outbox.
- [ ] Rate limit/idempotency tests đa instance.
- [ ] Privacy/logging tests với synthetic token.
- [ ] Real-client test với Gmail/Outlook/mobile đại diện.
- [ ] Test hủy/resend/expiry và account email change.

## 92. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gửi SMTP trực tiếp trong controller | Request chậm, khó retry | Service + durable outbox |
| Gửi trong transaction DB | Lock dài, rollback không thu hồi email | Transaction ngắn, send sau commit |
| Trả `200: Email delivered` sau `send(...)` | Cam kết sai | 202 accepted + telemetry đúng tầng |
| Trả 404 cho email không tồn tại | Dò tài khoản | Generic public response |
| Response giống nhau nhưng latency khác lớn | Timing enumeration | Async durable acceptance |
| Không rate limit | Spam victim và provider quota | Throttle/cooldown/abuse controls |
| Dùng `Random`/timestamp làm token | Dễ dự đoán | SecureRandom entropy cao |
| Lưu token plaintext trong DB | Lộ DB có thể chiếm token | Hash; encrypt raw token nếu phải giữ |
| Không có expiresAt/usedAt | Link dùng lại vô hạn | TTL và one-time consume |
| Chỉ check token rồi save không lock | Race consume | Pessimistic lock/atomic update |
| Token xác nhận email cũ cho email mới | Verify sai địa chỉ | Bind email/version với token |
| Dùng `@Async` coi như durable | Mất task khi restart | Outbox/durable broker |
| Retry mọi SMTP exception | Email trùng, link gây nhầm | Outcome/attempt classification |
| Token expired vẫn gửi | Link vô dụng | Worker pre-send eligibility |
| Gửi HTML bằng `SimpleMailMessage` | Thấy raw HTML | MimeMessageHelper |
| Lấy base URL từ Host header | Link giả/phishing | Config allowlisted origin |
| GET link tự confirm | Security scanner có thể kích hoạt | Confirmation page + POST/user action |
| Ghi token vào Subject/access log | Lộ bí mật | Redact/avoid sensitive metadata |
| Test bằng SMTP production và email thật | Gửi nhầm/lộ dữ liệu | Sandbox/allowlisted seed mailbox |

## 93. Bài tập 1 — Tạo endpoint theo contract

**Yêu cầu:** triển khai `POST /api/email-confirmations/requests` với JSON chứa email, trả `202` và không trả raw token.

Tiêu chí:

- JSON không hợp lệ trả 400.
- Email không tồn tại và đã verified có response generic như policy public.
- Controller không gọi trực tiếp `JavaMailSender`.
- Có một service chịu trách nhiệm accept request và quyết định bước tiếp theo.
- Không log raw email/token trong HTTP response.

**Gợi ý:** bắt đầu bằng controller và một service giả trong unit/web test, rồi mới kết nối database.

## 94. Bài tập 2 — Sinh token có TTL

**Yêu cầu:** dùng `SecureRandom` sinh token URL-safe; lưu SHA-256 digest, createdAt và expiresAt.

Tiêu chí:

- Hai lần phát hành có tokens khác nhau.
- Digest ổn định cho cùng raw token.
- Raw token không xuất hiện trong bảng `email_verification_token`.
- Hết hạn đúng khi `now >= expiresAt`.
- Test không cần `Thread.sleep`.

**Gợi ý:** tạo `Clock` injectable và fixture cố định.

## 95. Bài tập 3 — Xác minh một lần

**Yêu cầu:** `POST /api/email-confirmations/confirm` đánh dấu verified và consume token atomically.

Tiêu chí:

- Token mới/hợp lệ xác minh thành công.
- Token expired/used bị từ chối generic.
- Gọi token lần hai không phát sinh side effect.
- Hai requests đồng thời không cùng consume thành công.
- Token cho email A không thể xác minh email B sau khi tài khoản đổi địa chỉ.

**Gợi ý:** optimistic/pessimistic locking hoặc conditional update có predicate rõ.

## 96. Bài tập 4 — Gửi plain text và HTML

**Yêu cầu:** tạo `MimeMessage` với Subject tiếng Việt, text/plain và text/html chứa link.

Tiêu chí:

- SMTP sandbox nhận đúng một thư tới test mailbox.
- Subject và From đúng.
- Hai formats cùng link và mô tả nghiệp vụ.
- Raw token không xuất hiện trong Subject.
- Mở email ở một mobile mail client có thể bấm CTA.

**Gợi ý:** dùng `MimeMessageHelper.setText(plain, html)`, UTF-8 và nội dung chỉ chứa synthetic token.

## 97. Bài tập 5 — Chống account enumeration

**Yêu cầu:** biến request API thành public-safe hơn khi một email không tồn tại hoặc đã verified.

Tiêu chí:

- Cùng response shape theo policy.
- Timing không phụ thuộc trực tiếp SMTP submission.
- SMTP chỉ được gọi trong worker cho eligible account.
- Không có status endpoint public cho phép dò account.
- Rate limit không vô tình lộ account existence.

**Gợi ý:** endpoint chỉ persist durable request command; account lookup nằm sau async boundary.

## 98. Bài tập 6 — Durable outbox

**Yêu cầu:** sau khi HTTP trả 202, restart app vẫn xử lý được yêu cầu gửi chưa hoàn thành.

Tiêu chí:

- Durable command được commit trước response.
- Worker claim an toàn khi chạy hai instances.
- Token hash và encrypted outbox payload được lưu atomically.
- SMTP send nằm ngoài database transaction.
- Mỗi attempt có ID và status.
- Lỗi temporary được retry với backoff, có max attempts.
- Không retry mù outcome `UNKNOWN`.

**Gợi ý:** test process crash ở các ranh giới: trước command commit, sau commit, sau outbox commit, trước SMTP, sau SMTP accepted.

## 99. Bài tập 7 — Cooldown và resend

**Yêu cầu:** tránh gửi ba thư khi user double-click và vẫn cho resend hợp lệ sau một khoảng thời gian.

Tiêu chí:

- Có idempotency key hoặc logical request dedupe phù hợp.
- Có cooldown được thực thi qua nhiều instances.
- Có max active tokens hoặc policy quản lý tokens cũ.
- Response public không tiết lộ account existence.
- Có metric đếm rate-limited/suppressed requests.

**Gợi ý:** một biến static trong JVM không đủ; dùng shared store hoặc API gateway phối hợp.

## 100. Bài tập 8 — Token đã hết hạn trước khi worker gửi

**Kịch bản:**

```text
Token expires at 10:15
Outbox worker gets task at 10:20
```

**Yêu cầu:** không gửi một email với link đã hết hạn.

**Gợi ý:** kiểm tra token TTL ngay trước SMTP. Đánh dấu notification `EXPIRED/CANCELED` và giải phóng encrypted token theo policy. Nếu user còn muốn xác minh, phải có flow tạo yêu cầu mới hợp lệ.

## 101. Bài tập 9 — Không gửi nhầm tài khoản

**Kịch bản:** user yêu cầu xác minh `old@example.net`, rồi đổi email pending thành `new@example.net` trước khi nhấn link.

**Yêu cầu:** token cũ không thể tự xác nhận email mới.

**Gợi ý:** token cần ràng buộc `accountId + targetEmail/emailVersion`. Verifier kiểm tra context còn khớp trong transaction trước khi cập nhật verifiedAt.

## 102. Bài tập 10 — An toàn SMTP test

**Yêu cầu:** tạo một test harness gửi tới mailbox giả, đọc Subject/HTML/plain text và chứng minh không cần Internet production.

Tiêu chí:

- `JavaMailSenderImpl` chỉ kết nối `127.0.0.1` và cổng sandbox.
- Không sử dụng production secrets.
- Dữ liệu test là synthetic.
- Có MIME parser test cho alternatives.
- Test failure path không log token.
- Sau test dừng SMTP server và cleanup fixtures.

**Gợi ý:** GreenMail hoặc một SMTP capture server phù hợp phiên bản Jakarta Mail.

## 103. Bài tập 11 — SMTP timeout sau DATA

**Kịch bản:** worker đã gửi đủ DATA, nhưng kết nối mất trước khi nhận final reply.

**Yêu cầu:** phân biệt `UNKNOWN` với `FAILED` chắc chắn.

**Gợi ý:** attempt ledger, provider lookup nếu có, chính sách resend dựa trên khả năng duplicate và TTL. Không sử dụng `catch (MailException) { resend(); }` cho mọi trường hợp.

## 104. Bài tập 12 — Trang xác nhận và link scanner

**Yêu cầu:** link GET hiển thị trang xác nhận nhưng không tự consume token.

Tiêu chí:

- GET trang không thay đổi verified state.
- POST xác nhận theo user action và policy bảo mật.
- Token không xuất hiện trong logs/analytics.
- UI hỗ trợ link hết hạn hoặc đã dùng.
- Test với mailbox/gateway có link prefetch nếu sản phẩm dùng.

**Gợi ý:** thiết kế confirmation page với referrer policy chặt và không tải third-party scripts không cần thiết.

## 105. Tiêu chí nghiệm thu bài thực hành

Một ứng dụng hoàn chỉnh cho use case này có thể được nghiệm thu theo các lớp:

| Lớp | Câu hỏi cần trả lời | Bằng chứng |
| --- | --- | --- |
| API | POST request đúng contract, response generic? | MockMvc/web tests |
| Validation | Reject malformed input và giới hạn kích thước? | Validation tests |
| Security | Không lộ token/account existence? | Review + negative tests |
| Token | Random, TTL, hash, one-time? | Unit + DB integration |
| Data ownership | Token gắn đúng account/email version? | Domain tests |
| Persistence | Commit token/outbox atomically? | Transaction tests |
| SMTP | Message được submit với headers đúng? | SMTP sandbox |
| MIME | Có plain/HTML và UTF-8 đúng? | Jakarta Mail parser |
| Retry | Temporary/unknown outcomes đúng policy? | Failure injection |
| Abuse | Rate limits và cooldown đa instance? | Load/security tests |
| UX | Link hoạt động trên clients đại diện? | Seed mailbox tests |
| Operations | Tracing/metrics/audit không lộ bí mật? | Runtime review |

Không coi tất cả câu hỏi đều pass chỉ vì hai endpoints trả 202/204 trong Postman.

## 106. Những lựa chọn có thể thay đổi theo dự án

**A. Gửi xác minh sau đăng ký**

- Email được lấy từ registration pending account.
- Public request cần chống enumeration/rate limits.
- Account chưa được cấp các quyền yêu cầu verified email.

**B. Xác minh địa chỉ email mới của user đã đăng nhập**

- Backend lấy account từ authenticated principal.
- Token phải gắn `pendingEmail` và version.
- Có thể yêu cầu re-authentication hoặc thông báo tới email cũ.

**C. Gửi lại email xác nhận đơn hàng**

- Không cần token xác minh quyền sở hữu email nếu chỉ thông báo.
- Cần authorization và idempotency theo `orderId`.
- Không gửi lại vô hạn khi HTTP client retry.
- Dùng order snapshot/template version khi nghiệp vụ yêu cầu.

**D. Xác nhận một giao dịch nhạy cảm**

- Email link chỉ là một yếu tố của quy trình xác nhận.
- Có thể cần step-up authentication, session binding và replay protection.
- Không cho một GET link prefetch tự thực hiện side effect có giá trị lớn.

Cùng một tên “email xác nhận” có thể chỉ những mục tiêu khác nhau. Trong bài này, **email verification của địa chỉ tài khoản** là trường hợp xuyên suốt để mọi endpoint, token và test có một ngữ nghĩa thống nhất.

## 107. Tài liệu tham khảo

- Spring Framework — Email Integration: https://docs.spring.io/spring-framework/reference/integration/email.html
- Spring Boot — Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Security — Servlet Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

Các liên kết giúp đối chiếu API và nguyên tắc thiết kế theo phiên bản đang dùng. Mô hình Spring Boot/JPA trong bài là khung minh họa, với các service/repository production nâng cao được nêu rõ là abstractions cần tự xây, không phải tính năng tự có của `JavaMailSender`.

## 108. Kết luận

Để **tạo endpoint yêu cầu gửi email xác nhận** trong Spring Framework Mail, bắt đầu bằng một REST contract tường minh: `POST /api/email-confirmations/requests` nhận dữ liệu đã validation và trả một phản hồi **generic**, trong khi `POST /api/email-confirmations/confirm` xác minh **token ngẫu nhiên, có thời hạn và dùng một lần** rồi cập nhật account trong database transaction.

`JavaMailSender` và `MimeMessageHelper` giúp xây và submit email có text/plain, HTML và UTF-8 đúng, nhưng **không thay thế authentication, authorization, chống spam, quản lý token, database consistency hay bảo đảm gửi**. Phần dễ viết nhất là gọi `send(...)`; những phần quyết định chất lượng production là biết **ai được phép yêu cầu**, **địa chỉ nào được xác minh**, **token nào còn hợp lệ**, **SMTP outcome có chắc chắn không**, và **làm sao phục hồi công việc khi crash**.

Với một demo local, có thể tách token issuer transaction khỏi SMTP sender và gửi qua sandbox. Với endpoint public-production, nên tiến thêm đến **durable request command + idempotent token/outbox materialization + mail worker** để HTTP không phụ thuộc SMTP và không làm lộ account qua timing. Ghi nhận trạng thái request, notification, attempt, token và account riêng; retry có kiểm soát, không gửi token hết hạn, không lưu raw token ở nơi không bảo vệ và không coi SMTP submitted là email verified.

Khi hoàn thành bộ unit/API/DB/SMTP/security tests và thử link trên mail client đại diện, bạn sẽ có một nền tảng email confirmation **dễ hiểu, có thể mở rộng và có khả năng vận hành** trong ứng dụng Spring Boot, thay vì chỉ một endpoint “gọi mailSender và hy vọng email đến nơi”.
