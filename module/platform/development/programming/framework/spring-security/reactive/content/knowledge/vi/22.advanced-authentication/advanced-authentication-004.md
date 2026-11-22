# Lưu API key dưới dạng bảo vệ, giới hạn quyền và luân chuyển khóa — Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Nhóm:** Xác thực mở rộng  
> **Mục tiêu:** Tạo API key đủ entropy, không lưu plaintext tại hệ thống xác minh, giới hạn scope/tenant/expiry, xây `AuthenticationWebFilter` + `ReactiveAuthenticationManager` cho WebFlux, phát hành/luân chuyển/thu hồi an toàn, kiểm thử lỗi và vận hành không rò secret.

## 1. Tình huống và ranh giới tin cậy

Một backend đối tác cần gọi `GET /partner/reports` của một ứng dụng Spring WebFlux. Nó không có browser login, không nên mượn password user và có thể gửi một API key trong HTTPS header:

~~~http
GET /partner/reports HTTP/1.1
Host: api.example.com
X-API-Key: ak_<key-id>.<secret>
Accept: application/json
~~~

Từ góc độ máy chủ, API key là **bearer credential**: ai cầm chuỗi secret hợp lệ có thể gọi API trong phạm vi được cấp. Nó không tự chứng minh client đang chạy trên đúng máy, không có MFA/consent, không tự ràng buộc với người dùng hoặc request cụ thể.

Một thiết kế phải đạt:
- Credential có ít nhất 256-bit entropy do CSPRNG tạo, không phải password khách tự đặt.
- Một khóa có **public ID** để tra metadata và **secret** được phân phối đúng một lần.
- Bảng database chỉ giữ HMAC fingerprint/hash của key, không giữ plaintext để có thể đọc lại.
- Mọi request phải kiểm tra key ID, fingerprint, thời gian hiệu lực, trạng thái revoke và scopes.
- Quyền kiểm tra ở cả tầng HTTP và domain/tenant/owner, không chỉ ở việc có key.
- Có quy trình rotation không gián đoạn và revoke tức thời khi nghi bị lộ.
- Có redaction ở proxy, application, APM, backup, error report và test logs.
- Nếu DB hoặc KMS không sẵn sàng, phải **fail closed**, không phục hồi Authentication từ dữ liệu không còn đáng tin.

## 2. Threat model và biện pháp

| Nguy cơ | Hậu quả | Phòng vệ |
| --- | --- | --- |
| Database lộ plaintext keys | Kẻ tấn công dùng toàn bộ keys | Không lưu plaintext; HMAC fingerprint một chiều |
| Log có `X-API-Key` | Log reader giả danh client | Header redaction + secret scanning |
| Key được nhúng vào SPA/mobile | User có thể trích xuất | BFF hoặc OAuth2; không cấp static key cho public client |
| Key yếu/dễ đoán | Brute force | `SecureRandom` và ≥32 bytes random |
| Key không hết hạn | Credential bị lộ tồn tại lâu | Expiry, rotation policy và revoke |
| Một key có mọi quyền | Truy cập vượt nhu cầu | Scope/tenant/owner tối thiểu |
| Cache trạng thái key quá lâu | Revoked key vẫn dùng được | Invalidation hoặc TTL ≤ revoke SLA |
| Database/KMS lỗi | Tạm bỏ kiểm tra | Fail closed, timeout, metrics |
| Public key ID bị đoán | Thử nhiều IDs | Key ID không phải secret; HMAC, rate limits, generic errors |
| Pepper bị rò | Giảm lớp phòng vệ DB | KMS, key versioning và reissue kế hoạch |
| Dùng key ở tenant khác | BOLA/IDOR | Query tenant từ verified principal, không từ input |
| Retry/gateway ghi secret | Lộ qua request dumps | Sanitize, controls tại mọi hop |

**API key không phải encryption key.** Khóa dùng để chứng minh quyền gọi API; thuật toán HMAC của server dùng một bí mật riêng gọi là **pepper**, không nên trộn hai vai trò hoặc lưu cả hai trong cùng DB.

## 3. Định dạng: public key ID và secret 256-bit

Định dạng minh họa:

~~~text
ak_<kid16>.<secret43>
kid16:     12 random bytes -> Base64URL không padding -> 16 ký tự
secret43:  32 random bytes -> Base64URL không padding -> 43 ký tự
~~~

Ví dụ dummy **chỉ dùng trong test**:

~~~text
ak_k7Xb2Pq9Wm4Ns8Ta.AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA
~~~

Chuỗi công khai trên **không phải secret production**. Với key thật, Java `SecureRandom` tạo 32 bytes bí mật mới; 32 bytes ngẫu nhiên tốt tương đương khoảng \(2^{256}\) khả năng. Không dùng timestamp, email, số thứ tự, `java.util.Random`, UUID ghép sai cách hoặc mật khẩu tự đặt làm phần secret.

**Public ID** giúp truy vấn record, revoke chính xác và phân biệt lần rotation trong audit. Nó không có quyền khi đứng một mình. Prefix chỉ là định dạng; không dùng prefix `ak_prod` để coi token đến từ production khi chưa verify.

Chấp nhận duy nhất một encoding canonical. Kiểm tra độ dài, Base64URL charset và đúng số byte giải mã; không trim whitespace một cách tùy tiện, không nhận nhiều cách biểu diễn cùng một key. Với secret được cấp một lần, mất key nghĩa là **cấp lại**, không xây API “xem lại secret”.

## 4. Lưu trữ một chiều bằng HMAC-SHA256

Sau khi phát full key, server tính:

~~~text
digest = HMAC_SHA256(
    server_pepper_v1,
    ASCII("api-key:v1:" + kid + ":" + secret)
)
~~~

Lưu **kid, digest 32 bytes, pepper_version, owner/tenant, scopes, validFrom, expiresAt, revokedAt**. Không lưu secret hoặc full key.

Khi nhận request: parse key → tra DB theo kid → lấy pepper phiên bản phù hợp từ secret manager → tính lại HMAC → dùng `MessageDigest.isEqual` trên hai digest kích cỡ cố định → xét status/time/scopes.

**Vì sao HMAC?** Với random 256-bit secret, SHA-256 thuần đã khó brute force; server-held pepper khác với DB bổ sung một lớp bảo vệ nếu chỉ DB bị đọc. Pepper không làm key yếu trở nên mạnh. Đừng dùng HMAC nhanh cho password người tự chọn; password cần KDF chậm như Argon2id/PBKDF2/bcrypt theo threat model và không nên chạy blocking CPU trên Netty event-loop.

**Vì sao không mã hóa đảo ngược?** Ứng dụng chỉ cần so khớp credential, không cần khôi phục plaintext. Encryption at rest/DB encryption vẫn hữu ích để bảo vệ metadata và backups, nhưng không thay cơ chế lưu fingerprint.

**Không cam kết constant-time toàn HTTP:** `MessageDigest.isEqual` tốt hơn byte-by-byte compare nhưng DB hit/miss và metadata paths có timing khác; kết hợp error chung, rate limits và giám sát. Không gọi `String.equals` trực tiếp trên plaintext key rồi log kết quả cùng chuỗi input.

## 5. Key lifecycle

~~~mermaid
flowchart TD
    A["Admin/owner đủ quyền yêu cầu"] --> B["Generate kid + secret bằng CSPRNG"]
    B --> C["HMAC fingerprint với pepper version"]
    C --> D["Insert digest/scopes/tenant/time/audit"]
    D --> E["Hiển thị full key một lần, kênh TLS an toàn"]
    E --> F["ACTIVE"]
    F --> G{"Rotate bình thường?"}
    G -->|"Có"| H["Issue key mới, overlap có deadline"]
    H --> I["Client deploy secret mới, xác minh usage"]
    I --> J["Revoke key cũ"]
    G -->|"Compromised"| K["Revoke ngay, không overlap"]
    F --> L["ExpiresAt hoặc revokedAt -> 401"]
    J --> M["Giữ metadata audit theo policy"]
    K --> M
    L --> M
~~~

Những trạng thái cần hỗ trợ: phát hành, kích hoạt `valid_from`, đang hoạt động, chuẩn bị thay, revoked, expired. Không “tắt mềm” bằng UI nhưng quên enforcement tại API. Không trả trạng thái chi tiết cho caller không có authentication vì có thể tiết lộ ID key tồn tại.

**Normal rotation:** phát key mới có ID và secret khác, cho client chuyển trong overlap giới hạn rồi revoke key cũ; cả hai keys được audit riêng. **Emergency rotation:** nếu key lộ, revoke ngay rồi issue key mới, không đợi client triển khai xong để tránh attacker tiếp tục dùng key bị lộ.

## 6. Cấu trúc database thực tế

Ví dụ PostgreSQL cho hệ thống dùng R2DBC:

~~~sql
CREATE TABLE api_keys (
    kid                 VARCHAR(32) PRIMARY KEY,
    owner_id            UUID NOT NULL,
    tenant_id           UUID NOT NULL,
    credential_digest   BYTEA NOT NULL,
    digest_version      SMALLINT NOT NULL,
    pepper_version      SMALLINT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from          TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    last_used_at        TIMESTAMPTZ,
    rotation_group_id   UUID NOT NULL,
    created_by          UUID NOT NULL,
    CONSTRAINT ck_digest_length CHECK (
        octet_length(credential_digest) = 32),
    CONSTRAINT ck_valid_interval CHECK (expires_at > valid_from)
);

CREATE TABLE api_key_scopes (
    kid                 VARCHAR(32) NOT NULL
        REFERENCES api_keys(kid) ON DELETE CASCADE,
    scope               VARCHAR(120) NOT NULL,
    PRIMARY KEY (kid, scope)
);

CREATE INDEX idx_key_owner
    ON api_keys(owner_id, tenant_id, revoked_at, expires_at);
~~~

Không có `raw_key`, `secret`, `plaintext_api_key`. Kid unique để xác định record; digest chỉ để verify, không phải khóa ngoại hay nội dung log. Có thể thêm `status`, label, `replaced_by`, policy version, quota, last-four masked indicator theo contract.

**Quyền database:** ứng dụng runtime chỉ cần đọc các trường xác thực; endpoint quản trị/revocation cần quyền tách biệt; backup/log được mã hóa và audit. Với R2DBC, `findByKid` trả `Mono<ApiKeyRecord>`, không dùng JDBC blocking trong Reactor event-loop. Query tenant trong domain layer phải là prepared/parameterized, không nối SQL từ path.

## 7. Giới hạn quyền trước và sau authentication

Một key có thể được cấp:

| Integration | Tenant | Scopes | Thời hạn |
| --- | --- | --- | --- |
| Reporting worker | tenant-A | `reports.read` | 30 ngày |
| Export worker | tenant-A | `reports.read`, `reports.export` | 7 ngày |
| Billing worker | tenant-B | `invoices.read` | 14 ngày |

Tầng HTTP chỉ cho `GET /partner/reports` nếu có authority `SCOPE_reports.read` và `POST /partner/reports` chỉ khi có `SCOPE_reports.write`. Tầng domain tiếp tục kiểm tra record thuộc `tenantId` trong **principal đã xác thực**. Không bao giờ tin tenant trong `X-Tenant-Id` hoặc `?tenant=...` để cấp quyền mà chưa đối chiếu.

Không có quyền chỉ vì key đã HMAC-match. Owner/tenant có thể bị đình chỉ, scopes thay đổi, resource bị xóa hoặc cần hai người phê duyệt. Đối với dữ liệu nhạy cảm, object-level authorization phải ở service gần persistence, không chỉ ở route matcher.

## 8. Thiết kế xác thực trong WebFlux

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as AuthenticationWebFilter
    participant M as ReactiveAuthenticationManager
    participant R as ApiKeyStore
    participant H as Handler
    C->>F: X-API-Key ak_kid.secret
    F->>F: ServerAuthenticationConverter parse header count/size
    F->>M: Unauthenticated credential
    M->>M: Canonical parse, HMAC-SHA256
    M->>R: findByKid(kid)
    R-->>M: digest, scopes, tenant, expiry, revoke
    M->>M: Digest compare + validFrom/expiry/revokedAt
    alt invalid
        M-->>F: BadCredentialsException
        F-->>C: 401 generic
    else valid
        M-->>F: Authenticated principal, SCOPE_...
        F->>H: Reactor SecurityContext
        H-->>C: Authorized response
    end
~~~

Spring Security Reactive dùng `AuthenticationWebFilter`, `ServerAuthenticationConverter`, `ReactiveAuthenticationManager` và `SecurityWebFilterChain`. Không dùng Servlet `OncePerRequestFilter` hay `SecurityContextHolder` ThreadLocal cho Reactor code rồi giả định authentication được truyền qua thread switches.

**Fail closed:** missing/malformed/wrong/revoked/expired key → 401; hợp lệ nhưng thiếu scope → 403; DB/KMS không khả dụng → không có Authentication thành công (HTTP 5xx theo error policy). Không xây `onErrorResume(ex -> Mono.just(previousPrincipal))` để giữ uptime.

## 9. Mô hình Java 17+ có thể xây bằng Maven

Bài lab minh họa một API header-only không có HTTP Basic/form login/session. Dùng Spring Boot `3.3.13` (Spring Security 6.x) để cố định API ví dụ; nhánh Boot 3.3 đã hết OSS support, vì vậy production mới phải chọn phiên bản còn được hỗ trợ và chạy lại tests.

~~~text
reactive-api-key/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/keys/
    │   │   ├── KeyApplication.java
    │   │   ├── KeyCrypto.java
    │   │   ├── KeyStore.java
    │   │   ├── KeyAuthManager.java
    │   │   ├── KeySecurityConfig.java
    │   │   ├── PartnerController.java
    │   │   └── KeyGenerator.java
    │   └── resources/application.yml
    └── test/java/demo/keys/KeyApiTest.java
~~~

Demo dùng ConcurrentHashMap in-memory **chỉ để test**: restart sẽ mất key, không hỗ trợ multi-node atomic revoke hay production transaction. Phần SQL ở mục 6 mô tả đích triển khai thực tế.

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>reactive-api-key</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

### 9.2. KeyApplication.java

~~~java
package demo.keys;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KeyApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeyApplication.class, args);
    }
}
~~~

### 9.3. application.yml

~~~yaml
server:
  port: 8080

lab:
  pepper-base64: "${API_KEY_PEPPER_B64:}"
  bootstrap-key: "${LAB_BOOTSTRAP_KEY:}"
~~~

Không có `API_KEY_PEPPER_B64` hợp lệ → **startup fail fast**. Không cấu hình pepper mặc định trong source. Nếu bootstrap key trống thì không có key được cấp ở môi trường lab. Production cần secret manager/KMS, encrypted data-at-rest và API quản trị issuance riêng.

## 10. KeyCrypto.java: parse canonical và HMAC fingerprint

File `src/main/java/demo/keys/KeyCrypto.java`:

~~~java
package demo.keys;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.authentication.BadCredentialsException;

record KeyParts(String kid, String secret) {
    // Không cho toString vô tình in raw key.
    @Override public String toString() {
        return "KeyParts[kid=" + kid + ",secret=<redacted>]";
    }
}

public final class KeyCrypto {
    private static final Pattern FORMAT = Pattern.compile(
        "^ak_([A-Za-z0-9_-]{16})\\.([A-Za-z0-9_-]{43})$");

    private final byte[] pepper;

    public KeyCrypto(String encodedPepper) {
        byte[] decoded;
        try {
            decoded = Base64.getDecoder().decode(encodedPepper);
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException(
                "HMAC pepper must be valid Base64", exception);
        }
        if (decoded.length != 32) {
            throw new IllegalStateException(
                "HMAC pepper must have exactly 32 bytes");
        }
        this.pepper = decoded.clone();
    }

    static KeyParts parse(String raw) {
        if (raw == null || raw.length() > 96) {
            throw invalid();
        }
        Matcher m = FORMAT.matcher(raw);
        if (!m.matches()) {
            throw invalid();
        }
        String secret = m.group(2);
        byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder().decode(secret);
        } catch (IllegalArgumentException ex) {
            throw invalid();
        }
        if (decoded.length != 32) {
            throw invalid();
        }
        String canonical = Base64.getUrlEncoder()
            .withoutPadding().encodeToString(decoded);
        if (!canonical.equals(secret)) {
            throw invalid();
        }
        return new KeyParts(m.group(1), secret);
    }

    byte[] fingerprint(KeyParts parts) {
        String message = "api-key:v1:" + parts.kid()
            + ":" + parts.secret();
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            return mac.doFinal(
                message.getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    static BadCredentialsException invalid() {
        return new BadCredentialsException("Invalid API key");
    }
}
~~~

**Giải thích:**
- 12-byte public ID → 16 chars, 32-byte secret → 43 chars Base64URL không padding.
- `parse` không auto-trim, kiểm tra độ dài và canonical encoding để tránh hai chuỗi khác nhau đại diện cùng entropy.
- `Mac` được tạo cho mỗi lần xác minh, không chia sẻ instance không thread-safe.
- HMAC message bao gồm domain separator + kid để không vô ý tái sử dụng cùng digest cho mục đích khác.
- Không log raw KeyParts, request headers hoặc pepper. Java String không thể reliably zeroize; giới hạn memory dumps/APM và scope của secrets.
- Trong production, pepper được lấy từ KMS theo `pepper_version` của record; lab chỉ có v1.

## 11. KeyStore.java: metadata in-memory, expiry và revoke

File `src/main/java/demo/keys/KeyStore.java`:

~~~java
package demo.keys;

import java.time.Instant;
import java.util.Arrays;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import reactor.core.publisher.Mono;

record KeyRecord(
        String kid,
        String ownerId,
        String tenantId,
        byte[] digest,
        Set<String> scopes,
        Instant validFrom,
        Instant expiresAt,
        Instant revokedAt) {

    KeyRecord {
        Objects.requireNonNull(kid);
        Objects.requireNonNull(ownerId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(digest);
        Objects.requireNonNull(scopes);
        Objects.requireNonNull(validFrom);
        Objects.requireNonNull(expiresAt);
        if (digest.length != 32 || !expiresAt.isAfter(validFrom)) {
            throw new IllegalArgumentException("Invalid key metadata");
        }
        digest = Arrays.copyOf(digest, digest.length);
        scopes = Set.copyOf(scopes);
    }

    @Override public byte[] digest() {
        return Arrays.copyOf(digest, digest.length);
    }

    KeyRecord revoked(Instant at) {
        return new KeyRecord(kid, ownerId, tenantId,
            digest, scopes, validFrom, expiresAt, at);
    }
}

public final class KeyStore {
    private final ConcurrentHashMap<String, KeyRecord> rows =
        new ConcurrentHashMap<>();

    public Mono<KeyRecord> findByKid(String kid) {
        return Mono.defer(() -> Mono.justOrEmpty(rows.get(kid)));
    }

    public void put(KeyRecord record) {
        rows.put(record.kid(), record);
    }

    public void revoke(String kid) {
        rows.computeIfPresent(kid,
            (id, prior) -> prior.revoked(Instant.now()));
    }

    public void clear() {
        rows.clear();
    }
}
~~~

`KeyRecord` clone digest để tránh sửa mảng từ bên ngoài và copy scopes thành immutable set. Trên production dùng DB/R2DBC, query theo kid, không lưu full key. `ConcurrentHashMap` không có persistence, cross-node coherence, audit hay atomic transaction giữa nhiều bảng — phải thay trước khi triển khai thật.

## 12. KeyAuthManager.java: kiểm tra digest, trạng thái và cấp scope

File `src/main/java/demo/keys/KeyAuthManager.java`:

~~~java
package demo.keys;

import java.security.MessageDigest;
import java.security.Principal;
import java.time.Instant;
import java.util.List;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.core.publisher.Mono;

record KeyPrincipal(String kid, String ownerId, String tenantId)
        implements Principal {
    @Override public String getName() {
        return ownerId;
    }
}

public final class KeyAuthManager implements ReactiveAuthenticationManager {

    private static final byte[] DUMMY_DIGEST = new byte[32];

    private final KeyStore store;
    private final KeyCrypto crypto;

    public KeyAuthManager(KeyStore store, KeyCrypto crypto) {
        this.store = store;
        this.crypto = crypto;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication input) {
        if (!(input.getCredentials() instanceof String raw)) {
            return Mono.error(KeyCrypto.invalid());
        }

        return Mono.defer(() -> {
            KeyParts parts = KeyCrypto.parse(raw);
            byte[] candidate = crypto.fingerprint(parts);

            return store.findByKid(parts.kid())
                .switchIfEmpty(Mono.defer(() -> {
                    // Không cam kết constant-time HTTP:
                    // DB hit/miss vẫn có thể có timing khác.
                    MessageDigest.isEqual(DUMMY_DIGEST, candidate);
                    return Mono.error(KeyCrypto.invalid());
                }))
                .flatMap(record -> {
                    boolean matched = MessageDigest.isEqual(
                        record.digest(), candidate);
                    Instant now = Instant.now();
                    if (!matched
                            || record.revokedAt() != null
                            || now.isBefore(record.validFrom())
                            || !now.isBefore(record.expiresAt())) {
                        return Mono.error(KeyCrypto.invalid());
                    }

                    List<GrantedAuthority> granted =
                        record.scopes().stream()
                            .map(scope -> (GrantedAuthority)
                                new SimpleGrantedAuthority(
                                    "SCOPE_" + scope))
                            .toList();

                    KeyPrincipal principal = new KeyPrincipal(
                        record.kid(),
                        record.ownerId(),
                        record.tenantId());

                    return Mono.just((Authentication)
                        UsernamePasswordAuthenticationToken.authenticated(
                            principal, null, granted));
                });
        });
    }
}
~~~

**Điểm an toàn:** HMAC/digest được kiểm tra trước khi cấp Authentication; invalid key và unknown kid đều dùng cùng BadCredentialsException. Chỉ cấp authorities từ metadata **server lưu**, không từ headers/body client. Authentication thành công không chứa raw secret ở credentials và principal chỉ gồm public key ID/owner/tenant.

Đây là operation nhanh ở lab. DB production phải non-blocking/đúng scheduler, không gọi `block()` và không tự `subscribe()`. Nếu DB/KMS lỗi thật, `Mono.error` làm request không authenticated; không dùng cached principal cũ làm fallback.

## 13. KeySecurityConfig.java: AuthenticationWebFilter trong WebFlux

File `src/main/java/demo/keys/KeySecurityConfig.java`:

~~~java
package demo.keys;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class KeySecurityConfig {

    @Bean
    KeyCrypto crypto(@Value("${lab.pepper-base64}") String pepper) {
        return new KeyCrypto(pepper);
    }

    @Bean
    KeyStore store(
            KeyCrypto crypto,
            @Value("${lab.bootstrap-key:}") String bootstrap) {
        KeyStore store = new KeyStore();
        if (!bootstrap.isBlank()) {
            KeyParts parts = KeyCrypto.parse(bootstrap);
            Instant now = Instant.now();
            store.put(new KeyRecord(
                parts.kid(), "demo-partner", "demo-tenant",
                crypto.fingerprint(parts), Set.of("reports.read"),
                now.minusSeconds(1), now.plusSeconds(86400), null));
        }
        return store;
    }

    @Bean
    KeyAuthManager manager(KeyStore store, KeyCrypto crypto) {
        return new KeyAuthManager(store, crypto);
    }

    @Bean
    SecurityWebFilterChain chain(
            ServerHttpSecurity http, KeyAuthManager manager) {

        var entry = new HttpStatusServerEntryPoint(
            HttpStatus.UNAUTHORIZED);

        var filter = new AuthenticationWebFilter(manager);
        filter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());
        filter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/partner/**"));
        filter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(entry));

        filter.setServerAuthenticationConverter(exchange -> {
            List<String> values =
                exchange.getRequest().getHeaders().get("X-API-Key");
            if (values == null || values.isEmpty()) {
                return Mono.empty();
            }
            if (values.size() != 1
                    || values.get(0) == null
                    || values.get(0).length() > 96) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }
            return Mono.just(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "api-key", values.get(0)));
        });

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/partner/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/partner/reports")
                    .hasAuthority("SCOPE_reports.write")
                .anyExchange().denyAll())
            .exceptionHandling(ex ->
                ex.authenticationEntryPoint(entry))
            .addFilterAt(filter, SecurityWebFiltersOrder.AUTHENTICATION)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
~~~

**Vì sao thế này?** `AuthenticationWebFilter` dùng converter cho chỉ `/partner/**`; một header X-API-Key mang token **chưa authenticated**, manager xác minh và trả authenticated principal. `authorizeExchange` xét quyền theo method và path. `HttpStatusServerEntryPoint` trả 401 chung cho request chưa xác thực hoặc key sai, không hỏi HTTP Basic credentials. `NoOpServerSecurityContextRepository` tránh lưu Authentication vào cookie/session.

**Không auto-trim key**, không lấy khóa từ URL/query hay cookie. Nếu application khác dùng nhiều authentication mechanisms, phải dùng `securityMatcher` và `@Order` để tách SecurityWebFilterChains đúng; đừng cho cookie session xác thực route đã tắt CSRF.

CSRF disable ở ví dụ vì **chỉ header-only server-to-server authentication**, browser không tự gửi API key như cookie. Nếu bạn cho phép API key trong cookie auto-sent, phải thiết kế CSRF protection. CORS không thay auth/CSRF; một SPA chứa key trong JavaScript là không bảo mật vì key dễ bị trích xuất.

## 14. PartnerController.java: xem identity đã xác minh

File `src/main/java/demo/keys/PartnerController.java`:

~~~java
package demo.keys;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PartnerController {

    @GetMapping("/public/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/partner/reports")
    public Mono<Map<String, String>> reports(
            @AuthenticationPrincipal KeyPrincipal key) {
        return Mono.just(Map.of(
            "owner", key.ownerId(),
            "tenant", key.tenantId(),
            "mode", "read"));
    }

    @PostMapping("/partner/reports")
    public Mono<Map<String, String>> create(
            @AuthenticationPrincipal KeyPrincipal key) {
        return Mono.just(Map.of(
            "owner", key.ownerId(), "mode", "write"));
    }
}
~~~

**Giới hạn demo:** Controller echo metadata, không ghi DB. API thật phải dùng `key.tenantId`/`key.ownerId` làm ràng buộc truy vấn, kiểm tra role/object ownership trên chính bản ghi dữ liệu, không dùng tenant parameter của caller để mở quyền.

## 15. KeyGenerator.java: CSPRNG và cấp key local một lần

File `src/main/java/demo/keys/KeyGenerator.java`:

~~~java
package demo.keys;

import java.security.SecureRandom;
import java.util.Base64;

public final class KeyGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    private static String url(byte[] value) {
        return Base64.getUrlEncoder()
            .withoutPadding().encodeToString(value);
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Choose --key or --pepper");
        }

        if ("--key".equals(args[0])) {
            byte[] id = new byte[12];
            byte[] secret = new byte[32];
            RANDOM.nextBytes(id);
            RANDOM.nextBytes(secret);
            System.out.println("ak_" + url(id) + "." + url(secret));
            return;
        }

        if ("--pepper".equals(args[0])) {
            byte[] pepper = new byte[32];
            RANDOM.nextBytes(pepper);
            System.out.println(
                Base64.getEncoder().encodeToString(pepper));
            return;
        }

        throw new IllegalArgumentException("Unknown option");
    }
}
~~~

CLI này cố ý **in key/pepper ra stdout** vì chỉ dùng để học trong terminal riêng. Production issuance phải đưa secret qua kênh admin được bảo vệ và chỉ hiển thị một lần, không print ra CI/build logs. Pepper production nên tạo/quản lý trong secret vault/KMS, không dùng API key cùng vai trò pepper.

## 16. KeyApiTest.java: positive/negative integration tests

Trong `src/test/java/demo/keys/KeyApiTest.java`, test dùng một dummy key công khai. Test property pepper dùng 32 bytes tuần tự, **không được dùng ngoài test**.

~~~java
package demo.keys;

import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(properties = {
    "lab.pepper-base64=AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=",
    "lab.bootstrap-key="
})
@AutoConfigureWebTestClient
class KeyApiTest {

    private static final String KEY =
        "ak_k7Xb2Pq9Wm4Ns8Ta.AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA";
    private static final String ID = "k7Xb2Pq9Wm4Ns8Ta";

    @Autowired WebTestClient web;
    @Autowired KeyStore store;
    @Autowired KeyCrypto crypto;

    @BeforeEach
    void seed() {
        store.clear();
        KeyParts parts = KeyCrypto.parse(KEY);
        Instant now = Instant.now();
        store.put(new KeyRecord(
            ID, "partner-42", "tenant-7",
            crypto.fingerprint(parts),
            Set.of("reports.read"),
            now.minusSeconds(60),
            now.plusSeconds(3600), null));
    }

    @Test
    void healthIsPublic() {
        web.get().uri("/public/health")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void noKeyGets401() {
        web.get().uri("/partner/reports")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validKeyReadsOnlyItsTenant() {
        web.get().uri("/partner/reports")
            .header("X-API-Key", KEY)
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("partner-42")
            .jsonPath("$.tenant").isEqualTo("tenant-7");
    }

    @Test
    void changedSecretGets401() {
        String wrong = KEY.substring(0, KEY.indexOf('.') + 1)
            + "BQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA";

        web.get().uri("/partner/reports")
            .header("X-API-Key", wrong)
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedKeyGets401() {
        web.get().uri("/partner/reports")
            .header("X-API-Key", "invalid-key")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void duplicateHeadersGet401() {
        web.get().uri("/partner/reports")
            .header("X-API-Key", KEY, KEY)
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void readOnlyKeyCannotPost() {
        web.post().uri("/partner/reports")
            .header("X-API-Key", KEY)
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void revokedKeyGets401() {
        store.revoke(ID);
        web.get().uri("/partner/reports")
            .header("X-API-Key", KEY)
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void expiredKeyGets401() {
        KeyParts parts = KeyCrypto.parse(KEY);
        Instant now = Instant.now();
        store.put(new KeyRecord(
            ID, "partner-42", "tenant-7",
            crypto.fingerprint(parts),
            Set.of("reports.read"),
            now.minusSeconds(7200),
            now.minusSeconds(3600), null));
        web.get().uri("/partner/reports")
            .header("X-API-Key", KEY)
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void notYetValidKeyGets401() {
        KeyParts parts = KeyCrypto.parse(KEY);
        Instant now = Instant.now();
        store.put(new KeyRecord(
            ID, "partner-42", "tenant-7",
            crypto.fingerprint(parts),
            Set.of("reports.read"),
            now.plusSeconds(3600),
            now.plusSeconds(7200), null));
        web.get().uri("/partner/reports")
            .header("X-API-Key", KEY)
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        // Chỉ /partner/** kích hoạt converter; unknown URL
        // không tự được coi là authenticated dù có header.
        web.get().uri("/unknown-route")
            .header("X-API-Key", KEY)
            .exchange().expectStatus().isUnauthorized();
    }
}
~~~

**11 test methods** được viết cho HTTP security; WebTestClient chạy filter/manager nên có kiểm tra HMAC thật trong lab. Test có dummy key **không** chứng minh KMS/database/Redis distributed revocation, HTTPS hoặc production secret rotation.

Với endpoint lạ `/unknown-route`, request không đi qua converter giới hạn `/partner/**` và bị `denyAll`. Ở cấu hình API này, anonymous denial đi qua entry point thường là **401**; ở các chain/security configurations khác có thể là 403. Cần xác minh status thực tế bằng Maven tests, không bỏ denyAll để sửa một assertion.

## 17. Lệnh chạy project

Tại thư mục Maven:

~~~bash
mvn clean test
mvn -q -DskipTests package
~~~

Để tạo key và pepper cho **lab local**:

~~~bash
java -cp target/classes demo.keys.KeyGenerator --key
java -cp target/classes demo.keys.KeyGenerator --pepper
~~~

Hai lệnh này in secrets ra terminal; **không** dùng trong CI logs, recording hoặc terminal chia sẻ. Với Bash có thể thu output vào biến của shell local:

~~~bash
export LAB_BOOTSTRAP_KEY="$(java -cp target/classes demo.keys.KeyGenerator --key)"
export API_KEY_PEPPER_B64="$(java -cp target/classes demo.keys.KeyGenerator --pepper)"
mvn spring-boot:run
~~~

Với Windows PowerShell:

~~~powershell
$env:LAB_BOOTSTRAP_KEY = java -cp target/classes demo.keys.KeyGenerator --key
$env:API_KEY_PEPPER_B64 = java -cp target/classes demo.keys.KeyGenerator --pepper
mvn spring-boot:run
~~~

Khi đã chạy, gọi health:

~~~bash
curl -i "http://localhost:8080/public/health"
~~~

JSON body dự kiến:

~~~json
{"status":"up"}
~~~

Gọi protected GET trong lab:

~~~bash
curl -i "http://localhost:8080/partner/reports" \
  -H "X-API-Key: $LAB_BOOTSTRAP_KEY"
~~~

Dự kiến JSON:

~~~json
{"owner":"demo-partner","tenant":"demo-tenant","mode":"read"}
~~~

Lệnh curl minh họa có thể đưa secret vào process arguments, shell history, debugging hoặc logs. Với production dùng HTTP library hoặc công cụ vault-aware/truyền header qua kênh an toàn; API ngoài localhost bắt buộc HTTPS.

**Mã mẫu chưa được chạy Maven trong cuộc hội thoại này.** Các mã status/behavior là mục tiêu assertions của ví dụ và cần thực thi/đối chiếu với phiên bản Spring Security thực tế trước khi dùng cho production.

## 18. Phát hành API key như một hành động quản trị

Lab không cung cấp endpoint phát khóa công khai vì dễ tạo lỗ hổng nếu copy. API quản trị production nên:
1. Yêu cầu admin/workload authentication mạnh, MFA/approval phù hợp risk.
2. Xác định owner/tenant theo principal quản trị, không tin trường request user tự khai.
3. Chỉ cho chọn scope nằm trong allowlist mà quản trị viên có thể cấp, có maximum TTL.
4. Sinh kid/secret CSPRNG ở server, HMAC bằng pepper từ KMS, lưu digest+metadata.
5. Ghi scopes và audit trong một transaction; xử lý unique kid collision và idempotency.
6. Trả full key **một lần** qua TLS, response `Cache-Control: no-store`, không đưa vào email/ticket/analytics.
7. Các lần xem sau chỉ cung cấp kid, masked suffix, scopes, created/expires, trạng thái, lastUsed.
8. Cho phép revoke theo kid, luôn kiểm quyền đúng owner/tenant và ghi audit người thực hiện.
9. Giới hạn số keys active trên một client/tenant và đánh giá default expiry theo risk.
10. Nếu client làm mất key trước khi lưu vào vault, không có “recover plaintext”; revoke và issue lại.

Ví dụ **chỉ minh họa cấu trúc** response lần đầu:

~~~json
{
  "keyId": "k7Xb2Pq9Wm4Ns8Ta",
  "apiKey": "<one-time-value-from-secure-issuance>",
  "scopes": ["reports.read"],
  "expiresAt": "2027-01-01T00:00:00Z"
}
~~~

Sau đó không trả `apiKey` nữa. Đối với key rotation, hai keys sẽ có kid khác nhau nhưng có thể cùng rotation group/owner để audit.

## 19. Quy trình rotation không gián đoạn

Ví dụ key A sẽ hết hạn vào ngày T:
- **T−7 ngày:** hệ thống nhắc owner, kiểm tra client hiện tại và scopes.
- **T−2 ngày:** issue key B mới, quyền tối thiểu, cùng tenant, expiry riêng; A và B tạm active.
- **T−1 ngày:** đối tác cập nhật B trong secret vault/deploy, xác nhận B dùng được.
- **Trước T:** quan sát usage theo public kid và error rate, đảm bảo B thực sự được dùng.
- **T:** revoke A, invalidate cache và thử A→401, B→200 ở môi trường được phép.
- **Sau T:** audit, xóa các copies plaintext trong deployment logs (nếu có) theo quy trình, giữ metadata theo retention.

Đây là quy trình có **overlap được giới hạn**, không phải yêu cầu giữ khóa cũ mãi. Không thay digest của A trong cùng record để biến nó thành B vì audit/caching có thể nhập hai lần sử dụng làm một.

**Emergency rotation:** khi nghi A bị lộ, revoke A **ngay** và phát B an toàn; không kéo dài overlap chỉ vì khách hàng cần thêm thời gian. Có thể chặn tạm endpoints hoặc dùng break-glass kế hoạch được phê duyệt. Sau đó truy vết theo kid/time/IP/traces (không xem raw token), kiểm tra dữ liệu đã truy cập và thông báo.

## 20. Pepper rotation và giới hạn không có plaintext

Nếu DB chỉ chứa:

~~~text
fingerprint_v1 = HMAC(pepper_v1, "api-key:v1:"+kid+":"+secret)
~~~

thì không thể tính trực tiếp:

~~~text
fingerprint_v2 = HMAC(pepper_v2, "api-key:v1:"+kid+":"+secret)
~~~

từ fingerprint_v1 mà **không biết secret**. Vì vậy pepper rotation cần thiết kế:
- Có `pepper_version` trong DB record.
- Key issuance mới luôn dùng phiên bản pepper hiện hành.
- Trong giai đoạn chuyển tiếp, server giữ pepper cũ **chỉ để verify các keys cũ** trong KMS với quyền chặt.
- Migrate bằng cách **issue keys mới** rồi retire keys cũ, hoặc có cơ chế re-fingerprint khi key hợp lệ được gửi và đã được đánh giá đầy đủ transaction/race/revoke risk.
- Khi không còn active records cần pepper cũ, retire old pepper theo policy.
- Nếu pepper bị lộ, đánh giá incident và reissue các keys chịu ảnh hưởng, không coi dual verification dài hạn là bảo vệ đủ.

Không dùng một pepper cho nhiều hệ thống hoặc mục đích cryptographic khác nhau. Versioning cần đi cùng audit, KMS ACL, disaster recovery và rollback.

## 21. Cache, revocation, nhiều instances

Với in-memory store, revoke ngay trong cùng process. Production có nhiều instances và có thể cache metadata; một key revoked vẫn có thể active trên instance khác nếu cache chưa invalidated.

| Cách | Hiệu năng | Revocation |
| --- | --- | --- |
| R2DBC DB read mỗi request | Tốn I/O | Nhìn thấy trạng thái DB sau commit theo consistency |
| Cache positive TTL ngắn | Nhanh | Stale tối đa theo TTL/bất thường của cache |
| Invalidation pub/sub + TTL backup | Nhanh | Phải test lost messages/restart/network partitions |
| Cache vô hạn | Rất nhanh | **Không phù hợp** với revoke SLA |
| DB down → dùng cached principal không thời hạn | Trông như resilient | **Fail open** trong trust model nghiêm ngặt |

Quy định **revocation SLA** trước khi chọn cache: API thanh toán có thể cần strict revocation, API đọc dữ liệu ít nhạy cảm có thể chấp nhận vài giây theo policy. Không kết luận chung “TTL 5 phút luôn an toàn”.

Một request đã vượt auth trước khi revoke có thể còn xử lý; khi việc thu hồi cần ngăn cả long-running job, domain service phải có checkpoint/revalidation/cancellation ở business boundary. Không có một lệnh UPDATE nào tự đảo ngược những side effects đã hoàn thành.

## 22. Bảo vệ bí mật trong logs, network và client

- HTTPS bắt buộc ngoài localhost; không tắt certificate validation.
- API key đi trong header, **không** trong URL query, redirect Location hoặc JSON error.
- Mask `X-API-Key` ở gateway, app logs, wiretap, APM, traces, screenshots và support bundles.
- Không đưa secrets vào frontend JavaScript, mobile bundle, Git, Dockerfile, commit message, Slack/email hoặc issue tracker.
- Cấp riêng key per environment/client/tenant, không chia sẻ prod key cho staging.
- Có rate limit per kid/owner/tenant cho keys hợp lệ; IP/WAF/concurrency limits cho unknown keys.
- Kiểm tra kích thước header trước parse; nhiều header values hoặc định dạng mơ hồ → reject.
- Nếu dùng IP allowlist sau proxy, chỉ tin forwarded IP từ trusted proxy.
- Secret scanning ở repo và CI, quy trình revoke/rotate tự động khi phát hiện rò.
- Cân nhắc mTLS hoặc request signing + nonce/timestamp cho use case chống replay; API key thông thường không chống replay khi plaintext lộ.

**CORS khác authentication:** nếu JavaScript SPA gửi `X-API-Key` cross-origin, browser có thể preflight, nhưng CORS allowlist **không ngăn** attacker trích xuất key đã nằm trong JS. Dùng OAuth2 Authorization Code + PKCE hoặc BFF server-side cho public/browser clients.

## 23. Matrix 401/403 và lỗi không được leak

| Trường hợp | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Missing header trên protected endpoint | 401 | Chưa authenticated |
| Malformed key / quá dài / nhiều header | 401 | Không có credential hợp lệ |
| Unknown kid | 401 | Không tìm thấy record xác thực |
| Wrong secret | 401 | HMAC mismatch |
| Revoked / expired / not-before | 401 | Credential không còn/chưa được phép |
| Key đúng, thiếu scope writes | 403 | Authentication đúng nhưng authorization thiếu |
| Key đúng, reports.read đúng tenant | 200 | Được vào controller |
| Key đúng, sai owner/tenant của object | 403/404 theo API policy | Domain authorization |
| Database/KMS không thể xác minh | Fail closed, thường 5xx | Không cấp authenticated principal |
| Key đã bị rotate/revoke nhưng cache stale | Có thể là lỗ hổng | Cần revocation SLA/invalidation |

Dùng **status/body generic** cho các lỗi credential 401, không trả “key ID này tồn tại nhưng bị revoke” cho caller chưa authenticated. Logging nội bộ có thể phân loại nguyên nhân bằng enum riêng nhưng tuyệt đối không in full key/digest/pepper.

## 24. Sự cố và cách chẩn đoán

| Triệu chứng | Khả năng | Hướng giải quyết |
| --- | --- | --- |
| Mọi request 401 sau deploy | Pepper sai/version, DB metadata mismatch | Kiểm tra KMS config/digest version |
| Key vừa phát đã bị 401 | Canonical format hoặc validFrom lệch | Kiểm tra Base64URL, clocks/NTP |
| Key đã revoke vẫn 200 | Cache stale hoặc replica lag | Invalidate, giảm TTL, verify DB read |
| Đối tác chỉ đọc nhưng POST thành công | Authz scope rule sai | hasAuthority và unit tests |
| Tenant-A xem được data tenant-B | Thiếu ownership check | Tenant filter tại service/DB |
| HMAC luôn sai | Code chuyển encoding/pepper khác | Versioning, US_ASCII/UTF-8, canonical format |
| Nhiều 401 trên một kid | Key lộ/đoán/secret đổi sai | Rate limit, owner notify, audit |
| Khóa mất nhưng admin muốn xem lại | Database chỉ có fingerprint | Revoke và issue key mới |
| API key hoạt động trên staging và prod | Secret reuse sai policy | Per-environment issuance |
| DB outage dẫn tới 200 | Cơ chế fail-open fallback | Xóa fallback, test lỗi repository |
| Client bị 403 sau rotation | New key thiếu đúng scope | Phê duyệt scope change/contract |
| API key lộ qua support logs | Masking chưa phủ mọi hop | Log scrub, revoke, incident response |

Debug theo thứ tự: header presence/length → canonical parsing → kid lookup → fingerprint version/HMAC → revoked/time → scopes → domain tenant → cache/invalidation → HTTP status. Đừng giải 401 bằng cách tắt toàn bộ xác thực hoặc cấp scope wildcard.

## 25. Bài tập tự thực hành

**A. High entropy:** Sinh 1000 keys bằng `KeyGenerator` ở lab, kiểm tra định dạng/độ dài/khả năng đụng ID (không coi không đụng trong mẫu nhỏ là chứng minh tuyệt đối). Không log secrets ở CI.

**B. Fingerprint only:** Chỉ lưu HMAC digest và metadata, xác minh không còn raw secret trong DB/test snapshots, không có endpoint “show key”.

**C. Invalid authentication:** Dùng WebTestClient test missing, wrong, malformed, duplicate key. Body/status không tiết lộ kid tồn tại hay không.

**D. Scope:** GET reports.read=200, POST reports.write thiếu=403; sau đó issue riêng key có reports.write trong test, kiểm tra POST thành công.

**E. Expiry/revocation:** Tạo revoked/expired/not-yet-valid records. Chứng minh không có Authentication thành công dù HMAC đúng.

**F. Rotation overlap:** Tạo A và B cùng owner/tenant, cả hai dùng được trong overlap, sau revoke A thì A→401 và B→200.

**G. Emergency revoke:** Giả lập key A lộ; không overlap, revoke và đánh giá logs/traces không có raw secret.

**H. Pepper rotation:** Thêm phiên bản pepper-v1/v2, migrate bằng key reissue; giải thích tại sao fingerprint cũ không rehash nếu không biết secret.

**I. Domain authorization:** Key tenant-A cố truy vấn report tenant-B; service phải chặn dù key có reports.read.

**J. Cache outage:** Thử DB timeout, cache stale, invalidation mất message, key vừa revoked; đo revoke SLA, đảm bảo không fail-open.

**K. Resource boundaries:** So sánh API key với OAuth2 Client Credentials, mTLS, BFF/OIDC để chọn phương án đúng với public hoặc confidential clients.

**L. Secret scanning:** Đặt dummy key test vào file lab, cấu hình detector, tự động thu hồi/đổi key theo runbook khi detect Git leak. Tuyệt đối không thử với credential thật.

## 26. Checklist hoàn thành

- [ ] Secret sinh bằng CSPRNG ≥256-bit và kid công khai riêng.
- [ ] Database chỉ lưu HMAC fingerprint, không giữ API key gốc.
- [ ] Pepper độc lập, KMS/secret manager, versioning và rotation plan.
- [ ] Một key chỉ hiện một lần; mất key → phát lại/revoke.
- [ ] Canonical Base64URL, length limit, một header duy nhất.
- [ ] So sánh digest bằng MessageDigest.isEqual, generic 401.
- [ ] Mỗi key có owner, tenant, scopes tối thiểu và expiry/revocation.
- [ ] HTTP authorization kết hợp domain object-level authorization.
- [ ] Rotation tạo ID/secret mới, overlap bounded, revoke có audit.
- [ ] Khi nghi lộ, revoke khẩn cấp và thông báo owner.
- [ ] Cache/DB consistency đáp ứng revocation SLA; dependency outage fail closed.
- [ ] Không log Authorization/X-API-Key, raw digest hoặc pepper.
- [ ] HTTPS, rate limit, secret scanning, client storage an toàn.
- [ ] API admin issuance có quyền mạnh, no-store và transaction/audit.
- [ ] API header-only tắt CSRF chỉ khi không có auto-sent credential khác.
- [ ] Có tests cho đúng key, sai key, scope, revoked, expired, validFrom.
- [ ] Test với R2DBC/real proxy/KMS trước khi production, không coi in-memory lab đủ.

## 27. Câu hỏi tự kiểm tra

1. API key là bearer credential khác OAuth2 access token ở điểm nào?
2. Vì sao dùng 32 random bytes thay vì timestamp/Random?
3. Kid có phải bí mật không? Vì sao cần key ID độc lập?
4. Tại sao có HMAC fingerprint lại không cần lưu plaintext API key?
5. Pepper làm gì và tại sao không nên nằm cùng DB?
6. Khi pepper đổi mà không có plaintext, có thể tự rehash mọi digest không?
7. Vì sao khóa hợp lệ reports.read không được POST reports.write?
8. Khi JWT/API key được browser gửi từ cookie, có cần CSRF không?
9. Cache có thể khiến revocation không ngay lập tức như thế nào?
10. Vì sao rủi ro lớn nhất vẫn tồn tại nếu client ghi full key vào log?
11. Vì sao đổi digest trong một row cũ có thể gây khó audit rotation?
12. Làm sao phân biệt authentication 401 và authorization 403?
13. Khi DB down, vì sao không cấp Authentication từ giá trị cũ?
14. Tại sao scope không đủ để bảo vệ tenant/object?
15. Khi nghi key đã bị lộ Git, xóa commit có đủ không?
16. Vì sao API key lưu trong public frontend bundle không được coi là secret?
17. Làm thế nào giới hạn tốc độ unknown key attempts khi chưa biết kid đáng tin?
18. Tại sao MessageDigest.isEqual không bảo đảm toàn HTTP request constant-time?

## 28. Tài liệu tham khảo

- [Spring Security — AuthenticationWebFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): reactive converter, authentication manager và failure handler.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): SecurityWebFilterChain, ServerHttpSecurity và matchers.
- [Spring Security — WebFlux Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): request rules và deny-by-default.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): issue, rotate, revoke, expire, vault, logging.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): secure randomness, key management.
- [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/): broken authentication, object-level authorization.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege và deny by default.
- [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key lifecycle.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): message authentication code.
- [Java 17 SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): random cryptographic.
- [Java 17 MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): digest comparison.

**Kết luận:** API key cần **secret ngẫu nhiên mạnh, không thể khôi phục từ database**, HMAC fingerprint kèm pepper, metadata về quyền/thời gian/thu hồi và chính sách tenant. Spring WebFlux dùng `AuthenticationWebFilter` + `ReactiveAuthenticationManager` để xác minh trước khi cấp Authentication; `SecurityWebFilterChain` giới hạn scopes, domain layer vẫn chặn BOLA/IDOR. Luân chuyển bình thường bằng cách phát khóa mới rồi chuyển client trước khi thu hồi khóa cũ; khi key lộ phải revoke ngay. Pepper rotation là vòng đời độc lập vì không thể rehash digest cũ khi không có plaintext. Kiểm tra thực thi, logs, cache/invalidation, DB/KMS outage và fail closed trước khi đưa vào production.