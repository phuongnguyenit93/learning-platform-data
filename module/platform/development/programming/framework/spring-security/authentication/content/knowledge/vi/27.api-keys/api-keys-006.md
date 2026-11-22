# Luân chuyển, hết hạn và thu hồi API key trong Spring Security

> **Phạm vi:** Cách quản lý vòng đời **API key dạng opaque** do ứng dụng cấp cho client khi gọi API: tạo mới, luân chuyển (rotation), hết hạn (expiration), thu hồi (revocation) và kiểm tra ngay trong Spring Security. Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x Servlet. API key là một *bearer secret*: ai có chuỗi secret đều có khả năng gửi request với quyền của nó. TLS, quyền tối thiểu, giới hạn tốc độ và thu hồi có hiệu lực là yêu cầu thiết yếu.

## 1. Kết quả học tập

Sau bài này, bạn sẽ có thể:

1. Phân biệt phát hành, kích hoạt, luân chuyển, hết hạn, thu hồi và xóa metadata của API key.
2. Tách **ID công khai** và **secret bí mật**, biết nên lưu digest/HMAC, owner, scopes, thời hạn và trạng thái như thế nào.
3. Thực hiện rotation có **overlap hữu hạn** để client chuyển từ khóa cũ K1 sang khóa mới K2, hoặc revoke ngay khi có nghi ngờ bị lộ.
4. Kiểm tra `activatedAt`, `expiresAt`, `revokedAt`, owner/audience và quyền trên **mọi request**, kể cả khi job dọn dữ liệu chưa chạy.
5. Đưa một identity đã xác minh thành `Authentication`/`GrantedAuthority` trong Spring Security và phân loại lỗi 401/403/429/5xx.
6. Kiểm thử đúng mốc thời gian, cache/replica nhiều instance, thao tác đồng thời, mất secret và các bước ứng cứu.

Bài tập trung vào **API key của ứng dụng**. Nó khác OAuth2 access token, JWT, khóa ký JWT, mật khẩu người dùng và private key TLS. Không tự áp dụng cơ chế thu hồi của API key lên token tự chứa mà không đánh giá thiết kế.

## 2. Những trạng thái phải tách biệt

| Trạng thái/hành động | Ý nghĩa | Hành vi |
| --- | --- | --- |
| `ISSUED` / `PENDING` | Đã sinh ID + secret nhưng chưa được chấp nhận | Từ chối nếu chưa tới `activatedAt` |
| `ACTIVE` | Khóa có thể dùng trong phạm vi đã cấp | Vẫn phải xác minh secret, expiry, owner và scope |
| `ROTATING` | Đang thay bằng khóa mới | Có thể tạm có hai khóa active |
| `EXPIRED` | Đã đến `expiresAt` | Không cho dùng dù digest đúng |
| `REVOKED` | Bị vô hiệu hóa chủ động trước hạn | Chặn mọi request sau thu hồi theo SLA |
| `PURGED` | Metadata cũ được xóa theo retention | Không phải cách thay thế revoke/audit |

~~~text
         ISSUE -> PENDING -> ACTIVE ------- expiry -------> EXPIRED
                                 |
                                 +-- rotate -> NEW KEY -> ACTIVE
                                 |               |
                                 +-- grace K1,K2 |
                                 |               |
                                 +-- cutoff ----> REVOKE K1
                                 |
                                 +-- compromise -> REVOKE NGAY
~~~

**Rotation không phải sửa secret trên cùng một record.** Cấp K2 với ID, digest và thời điểm riêng; K1 giữ trạng thái/expiry của mình trong thời gian overlap. Nếu ghi đè secret K1, client chưa chuyển sẽ đột ngột lỗi, không biết client nào còn dùng K1 và khó audit. Revocation nên là một chiều; nếu cần khôi phục truy cập, cấp **khóa mới**, không làm raw secret cũ sống lại.

`EXPIRED` có thể là **trạng thái tính toán** từ `expiresAt`; không cần phụ thuộc vào cron đặt cột status thành EXPIRED. Cron/scheduled cleanup chỉ phục vụ dữ liệu vận hành, không phải cổng thực thi bảo mật.

## 3. Định dạng API key và mô hình lưu trữ

Một dạng cấu trúc minh họa:

~~~text
ak_prod_v2_k123456.<32_byte_random_secret_base64url>
|----------------| |--------------------------------|
     key_id                phần secret bí mật
~~~

Đây là **ký hiệu**, không phải khóa thật. `key_id` được phép hiển thị để quản lý; `secret` không được lưu plaintext ở database hoặc log. Prefix môi trường như `prod` giúp nhận diện nhưng không tự chứng minh được phép dùng ở production: vẫn phải kiểm tra metadata ở server.

| Metadata | Mục đích |
| --- | --- |
| `key_id` (unique/indexed) | Tra cứu bản ghi, audit, revoke một khóa cụ thể |
| `secret_digest` / `secret_hmac` | So sánh secret, không lưu raw key |
| `owner_id`, `service_id`, `tenant_id` | Danh tính và trách nhiệm của ứng dụng gọi |
| `environment` / `audience` | Dịch vụ đích và môi trường được chấp nhận |
| `scopes` / `permissions` | Quyền như `orders:read`, `orders:write` |
| `issued_at` / `activated_at` | Thời điểm phát hành và bắt đầu hiệu lực |
| `expires_at` | Hạn tuyệt đối, không phụ thuộc cleanup job |
| `revoked_at`, `revoked_by`, `reason` | Dấu vết thu hồi |
| `rotated_from` / `rotation_group` | Quan hệ K1 -> K2 và lịch cutover |
| `last_used_at` / `version` | Theo dõi rollout và chống cập nhật đè từ snapshot cũ |

**Sinh khóa:** `SecureRandom` tạo ít nhất 32 byte (256 bit) làm secret, rồi biểu diễn Base64 URL-safe hoặc hex. Không dùng timestamp, username, `Random`, counter hay một UUID đơn lẻ thay 256-bit secret. ID có thể dùng UUID hoặc ID ngẫu nhiên unique; secret phải được sinh độc lập.

**Hash:** Với secret thực sự ngẫu nhiên 256 bit, SHA-256 digest phù hợp cho lookup và gần như không thể brute-force. HMAC-SHA-256 với **pepper ở secret manager tách khỏi DB** có thể tăng phòng thủ khi DB lộ; cần versioning và kế hoạch xoay pepper. Không dùng plain SHA-256 cho **mật khẩu người dùng** entropy thấp: password cần KDF như Argon2id/bcrypt/scrypt. Digest fixed-length có thể được so bằng `MessageDigest.isEqual`.

**Hiển thị:** Raw secret chỉ giao **một lần** khi create/rotate qua kênh an toàn. Các API liệt kê chỉ trả key ID, nhãn, owner, scope, expiry và trạng thái. Nếu quên secret, phải rotate; không thiết kế endpoint `GET /keys/{id}` để đọc lại raw secret.

## 4. Điều kiện chấp nhận tại mỗi request

~~~text
Client --HTTPS + X-API-Key--> Spring Security / API gateway
         |
         v
Parse key ID + secret (định dạng, length, charset)
         |
         v
Lookup key ID tại store được kiểm soát
         |
         v
Kiểm tra secret digest/HMAC
         |
         v
activatedAt <= now < expiresAt và revokedAt == null
         |
         v
Owner còn active + đúng tenant/environment/audience
         |
         v
Tạo Authentication với scopes server-side
         |
         v
hasAuthority(...) -> cho phép hoặc 403
~~~

Một phép kiểm tra logic đầy đủ:

~~~text
accepted = format_ok AND id_exists AND secret_matches
           AND activated_at <= now AND now < expires_at
           AND revoked_at IS NULL AND owner_active
           AND environment_matches AND audience_matches
           AND requested_operation_in_scopes
~~~

**Đúng thời điểm `expiresAt` đã hết hạn:** `now.isBefore(expiresAt)` phải là true mới được nhận. Dùng giờ server UTC dạng `Instant`; không cho client tự gửi thời gian mới, không dựa vào `LocalDate` bỏ mất giờ. Digest đúng nhưng owner disabled, scope thiếu hoặc key revoked vẫn **không** cấp quyền.

Nếu key store unavailable, auth chưa thể kết luận danh tính. Hệ thống phải **fail closed** và báo lỗi hạ tầng; không lấy kết quả `valid=true` cũ từ cache vô thời hạn để cho truy cập.

## 5. Luân chuyển có overlap hữu hạn

Ví dụ integration `billing-worker` đang dùng K1. Lịch rotation định kỳ:

1. **Inventory:** xác định owner, workload, môi trường, scopes, các job hiếm khi chạy, thời hạn K1 và giới hạn số khóa đồng thời.
2. **Phê duyệt:** kiểm tra actor có quyền rotate; K2 không được tự nhận scope lớn hơn K1.
3. **Cấp K2:** ID/secret mới, digest mới, `expiresAt` mới và `rotatedFrom=K1`. Dùng transaction, version và idempotency cho API quản trị.
4. **Phân phối K2:** cấp qua secret manager/kênh an toàn; client cài đặt K2 và rollout dần.
5. **Kiểm chứng:** dùng K2 gọi endpoint nhỏ nhất được cấp phép, xác minh 2xx hoặc mã nghiệp vụ thích hợp; theo dõi key ID mà không log raw secret.
6. **Overlap:** K1 và K2 tạm thời cùng hợp lệ để các instance client chuyển đổi; có cutoff rõ.
7. **Cutover:** thu hồi K1, phát invalidation/version update tới cache và chứng minh K1 bị từ chối ở mọi region/gateway.
8. **Đóng vòng:** cập nhật audit, inventory và alert khi tiếp tục thấy K1 bị sử dụng.

| Thời điểm | K1 | K2 | Điều cần theo dõi |
| --- | --- | --- | --- |
| Chưa rotate | ACTIVE | Chưa phát hành | K1 expiry và last used |
| Vừa cấp K2 | ACTIVE | PENDING/ACTIVE | K2 được client nhận an toàn |
| Đang chuyển | ACTIVE tới cutoff | ACTIVE | Request K1 giảm, K2 tăng |
| Sau cutoff | REVOKED/EXPIRED | ACTIVE | K1 bị từ chối nhất quán |
| Về sau | Không tái kích hoạt | ACTIVE đến expiry riêng | Cảnh báo trước expiry K2 |

Giới hạn có thể dùng `old_effective_expiry = min(old_original_expiry, rotation_cutoff)`. Nếu cutoff được thực thi bằng job đặt `revokedAt`, phải xử lý job lỗi/đến muộn; tốt hơn có thể kiểm tra mốc cutoff trực tiếp trong đường xác thực. Không kéo dài overlap vô hạn do một client quên cập nhật.

**Lộ khóa/compromise:** Khi K1 bị nghi ngờ lộ, phải **revoke K1 ngay**, không để grace cho attacker. Cấp K2 cho client còn hợp lệ qua kênh mới và điều tra các dấu vết sử dụng K1. Đây là quy trình khẩn khác rotation định kỳ.

## 6. Expiration, activation và thời gian thực tế

Phân biệt `issuedAt`, `activatedAt`, `expiresAt`, `rotationCutoff`, `idleTimeout` nếu có, và thời gian lưu metadata audit. Expiry tuyệt đối không được gia hạn bằng việc request tới API liên tục trừ khi hệ thống có **chính sách renewal mới được phê duyệt**; cách an toàn, dễ audit là cấp key mới.

Các lỗi hay gặp:

- So `LocalDate` thay vì `Instant` khiến khóa còn hợp lệ sang ngày sau.
- Dùng `now.isAfter(expiresAt)` để từ chối, khiến đúng thời điểm expiry vẫn được dùng. Dùng `now.isBefore(expiresAt)` làm điều kiện chấp nhận.
- Chỉ dùng cron xóa bản ghi quá hạn; cron lỗi thì key vẫn được nhận nếu auth không check `expiresAt`.
- Cho client sửa `expiresAt` trong request hoặc xem thời gian client là nguồn tin.
- Cache Authentication/metadata không giới hạn rồi bỏ qua thời điểm hết hạn.
- Không tính clock skew và replica lag trong kiến trúc phân tán.

Có thể gửi cảnh báo T-14/T-7/T-1 ngày nếu TTL dài; nhắc không tự gia hạn. Clock máy chủ phải được đồng bộ, timestamp dùng UTC, và test tại `expiresAt.minusNanos(1)`, `expiresAt`, `expiresAt.plusSeconds(1)`.

## 7. Thu hồi trước hạn

**Revocation** là thao tác chủ động từ phía server khi client bị mất, nhân viên/đối tác offboard, nghi lộ key, abuse, hoặc không còn nhu cầu. Nếu `revokedAt != null`, khóa không được chấp nhận **ngay cả khi mật mã và expiry còn hợp lệ**.

Thu hồi cần đáp ứng:

- **Idempotent:** gọi revoke nhiều lần giữ nguyên REVOKED, không tự mở khóa lại.
- **Terminal:** không cho bật lại cùng raw secret; cấp ID+secret khác để phục hồi.
- **Atomic:** transaction/compare-and-set/version tránh job rotate ghi đè trạng thái revoked.
- **Auditable:** actor, reason, key ID, owner, thời gian và correlation ID; log không chứa raw secret.
- **Propagated:** cache, gateway và các region nhận thu hồi theo SLA đã cam kết.
- **Scoped:** có thể revoke một key hoặc toàn bộ keys thuộc owner/tenant sau kiểm tra quyền.

SQL minh họa cập nhật một chiều, syntax tham số tùy repository:

~~~sql
UPDATE api_keys
SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
    revoked_by = COALESCE(revoked_by, :operator)
WHERE key_id = :key_id AND revoked_at IS NULL;
~~~

Các tham số phải đến từ ngữ cảnh quản trị đã được xác thực và kiểm tra ownership; đừng tin actor do client tự khai báo. Nếu hệ thống lưu `version`, cập nhật version cùng transaction để tránh lost update.

**Xóa key khỏi client ≠ revoke ở server.** Nếu ai đó đã copy secret trước khi xóa file, key vẫn có thể được dùng đến khi server xác nhận revoked hoặc expired. Việc xóa secret khỏi Git history, pod, ticket, CI variable và rotate deployment chưa thay thế revoke tại authoritative store.

## 8. Ví dụ Java 17 độc lập minh họa vòng đời

Chương trình dưới tạo key 256 bit, lưu SHA-256 digest (vì đây là secret ngẫu nhiên cao), so sánh digest bằng `MessageDigest.isEqual`, dùng `Instant` để kiểm thử mà không cần sleep. Chỉ dùng JDK; **không** in key thật. Đây là mô hình học tập trong một process, chưa có DB, quyền, key-ID collision handling hay kiểm tra concurrency phân tán.

Tệp `ApiKeyLifecycleDemo.java`:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class ApiKeyLifecycleDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    record Stored(String owner, byte[] digest,
                  Instant expiresAt, Instant revokedAt) {}

    static final class Registry {
        private final Map<String, Stored> keys = new ConcurrentHashMap<>();

        String issue(String owner, Instant issuedAt, Duration ttl) {
            if (ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("TTL must be positive");
            }
            byte[] secret = new byte[32];
            RANDOM.nextBytes(secret);
            try {
                String id = "ak_demo_" +
                        UUID.randomUUID().toString().replace("-", "");
                keys.put(id, new Stored(owner, sha256(secret),
                        issuedAt.plus(ttl), null));
                return id + "." + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(secret);
            } finally {
                Arrays.fill(secret, (byte) 0);
            }
        }

        boolean accepts(String presentedKey, Instant now) {
            if (presentedKey == null) {
                return false;
            }
            int dot = presentedKey.indexOf('.');
            if (dot < 0 || dot != presentedKey.lastIndexOf('.')) {
                return false;
            }
            Stored stored = keys.get(presentedKey.substring(0, dot));
            if (stored == null || stored.revokedAt() != null
                    || !now.isBefore(stored.expiresAt())) {
                return false;
            }

            byte[] supplied;
            try {
                supplied = Base64.getUrlDecoder()
                        .decode(presentedKey.substring(dot + 1));
            } catch (IllegalArgumentException badEncoding) {
                return false;
            }
            try {
                return supplied.length == 32
                        && MessageDigest.isEqual(
                                stored.digest(), sha256(supplied));
            } finally {
                Arrays.fill(supplied, (byte) 0);
            }
        }

        void revoke(String keyId, Instant at) {
            keys.computeIfPresent(keyId, (id, old) ->
                    new Stored(old.owner(), old.digest(),
                            old.expiresAt(),
                            old.revokedAt() == null ? at : old.revokedAt()));
        }

        private static byte[] sha256(byte[] bytes) {
            try {
                return MessageDigest.getInstance("SHA-256").digest(bytes);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        Instant t0 = Instant.parse("2026-11-06T00:00:00Z");

        String k1 = registry.issue("billing-worker", t0,
                Duration.ofDays(7));
        System.out.println("old before rotation: " +
                registry.accepts(k1, t0.plusSeconds(1)));

        Instant rotation = t0.plus(Duration.ofDays(1));
        String k2 = registry.issue("billing-worker", rotation,
                Duration.ofDays(7));
        Instant overlap = rotation.plusSeconds(10);
        System.out.println("old during overlap: " +
                registry.accepts(k1, overlap));
        System.out.println("new during overlap: " +
                registry.accepts(k2, overlap));

        String oldId = k1.substring(0, k1.indexOf('.'));
        registry.revoke(oldId, rotation.plusSeconds(20));
        Instant after = rotation.plusSeconds(21);
        System.out.println("old after revoke: " +
                registry.accepts(k1, after));
        System.out.println("new after revoke: " +
                registry.accepts(k2, after));
        System.out.println("new at expiry: " +
                registry.accepts(k2, rotation.plus(Duration.ofDays(7))));
    }
}
~~~

Biên dịch, chạy bằng JDK 17+:

~~~bash
javac ApiKeyLifecycleDemo.java
java ApiKeyLifecycleDemo
~~~

**Stdout kỳ vọng chính xác**, bất kể secret ngẫu nhiên:

~~~text
old before rotation: true
old during overlap: true
new during overlap: true
old after revoke: false
new after revoke: true
new at expiry: false
~~~

Đầu tiên K1 hợp lệ, sau khi sinh K2 cả hai hợp lệ, sau `revoke` chỉ K2 còn hợp lệ. Ở đúng mốc expiry của K2, điều kiện `now.isBefore(expiresAt)` là false. Trạng thái của K1 không được bật lại.

**Giới hạn:** Registry dùng `ConcurrentHashMap` nên mất dữ liệu khi process restart, không thực thi scopes/owner/tenant, thiếu transaction nhiều vùng, không có audit hoặc anti-abuse. `record Stored` giữ `byte[]` nội bộ cho ví dụ; production cần copy an toàn và bảo vệ memory. Đối với sản phẩm thật, dùng DB bền vững, secret manager và HMAC/digest versioning phù hợp. Đừng cho client tự quyết định `now`; ví dụ đưa `Instant` từ hàm test, code server cần `Clock` tin cậy.

## 9. Đưa khóa hợp lệ vào Spring Security

Trong Servlet stack, có thể dùng `OncePerRequestFilter` đọc header, gọi một `ApiKeyVerifier` lấy identity từ server rồi đặt `Authentication` vào `SecurityContext`. Tạo authorities từ **metadata server**, không tin scope user tự gửi.

Contract (phải tự cung cấp triển khai repository/DB thật):

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;

public interface ApiKeyVerifier {

    // empty chỉ khi credential invalid; lỗi store phải báo lỗi hệ thống.
    Optional<KeyIdentity> verify(String rawKey);

    record KeyIdentity(String serviceId, Set<String> authorities) {}
}
~~~

Bộ lọc `ApiKeyFilter.java`:

~~~java
package example.security;

import java.io.IOException;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {
    private final ApiKeyVerifier verifier;

    public ApiKeyFilter(ApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        List<String> headers = Collections.list(request.getHeaders("X-API-Key"));
        if (headers.isEmpty()) {
            chain.doFilter(request, response);
            return;
        }
        if (headers.size() != 1 || headers.get(0).isBlank()
                || headers.get(0).contains(",")) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        Optional<ApiKeyVerifier.KeyIdentity> identity =
                verifier.verify(headers.get(0));
        if (identity.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var authorities = identity.get().authorities().stream()
                .map(SimpleGrantedAuthority::new).toList();
        Authentication auth = new UsernamePasswordAuthenticationToken(
                identity.get().serviceId(), null, authorities);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Các yêu cầu chưa được viết trong filter mẫu phải nằm ở `verifier.verify`: kiểm tra định dạng/độ dài tối đa, ID, digest/HMAC, active, expiry, revoked, owner/tenant/environment/audience và scopes. Filter không phân biệt nguyên nhân key sai trong phản hồi công khai, chỉ trả 401; database outage không được chuyển thành `Optional.empty()`.

**Lưu ý:** Filter được tạo bằng `new ApiKeyFilter(verifier)` khi gắn vào `HttpSecurity`; nếu đánh dấu `@Component` lên filter hoặc khai báo một filter bean khác, Spring Boot có thể đăng ký nó thêm ở servlet container và gây hai lần chạy/sai thứ tự. Nếu phải dùng bean, tắt container auto-registration.

`ApiSecurityConfig.java`, cấu hình Spring Security 6 Servlet minh họa:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http,
            ApiKeyVerifier verifier) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((req, res, e) ->
                                res.sendError(401)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/status").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("orders:read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("orders:write")
                        .anyRequest().authenticated())
                .addFilterBefore(new ApiKeyFilter(verifier),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

**Đây là mảnh cấu hình Spring, không chạy bằng `javac` độc lập.** Cần Spring Boot application, repository/verifier thật, controllers và test. Cấu hình `csrf.disable` chỉ hợp lý cho API stateless sử dụng API key header, không dùng browser cookie làm ambient authentication; đừng tắt CSRF trên toàn website có form/OIDC. Nếu còn web UI, tạo các SecurityFilterChain khác với matcher/order hợp lệ.

Trong WebFlux phải dùng `SecurityWebFilterChain` và `WebFilter`/reactive verifier, không dùng `OncePerRequestFilter` của Servlet. Nếu verifier dựa vào blocking database client, cô lập I/O phù hợp; không block event loop. Key opaque custom không tự động là OAuth2 Bearer/JWT.

## 10. Cách xử lý lỗi cho client và vận hành

| Tình huống | Phản hồi thông thường | Lưu ý |
| --- | --- | --- |
| Thiếu key ở endpoint cần xác thực | 401 Unauthorized | Không tạo authenticated principal |
| Sai ID, secret, malformed, inactive | 401 Unauthorized | Không xác nhận key ID nào tồn tại |
| Expired/revoked | 401 Unauthorized | Public response chung, không lộ metadata |
| Key hợp lệ nhưng thiếu `orders:write` | 403 Forbidden | Authorization, không phải sai khóa |
| Vượt quota/rate limit | 429 Too Many Requests | Có thể dùng `Retry-After` theo policy |
| Key store unavailable/timeout | 503 hoặc 5xx phù hợp | Fail closed, không ngụy trang thành 401 |
| Owner/service bị offboard | Từ chối theo auth policy | Thu hồi mọi key tương ứng |
| Key của staging được gửi đến prod | 401 | Dù format hợp lệ cũng sai audience/environment |

Không phản hồi raw key, digest, `revokedAt`, `expiresAt` chính xác cho caller chưa được xác thực. API quản trị có quyền riêng có thể hiển thị metadata phù hợp. Một custom filter nằm trước Spring `ExceptionTranslationFilter` phải xử lý error boundary rõ ràng, không đoán rằng mọi exception sẽ được converter phía sau bắt.

## 11. Nhiều instance, cache và consistency

Thu hồi ghi thành công tại database **chưa chắc** toàn bộ API instance đã từ chối key. Ví dụ A cache kết quả `valid(K1)=true` 10 phút, B đã thấy `revokedAt`; request đến A vẫn có thể thành công. Độ trễ giữa source-of-truth, replica, gateway và cache **là một phần của SLA thu hồi**.

| Mô hình | Ưu điểm | Rủi ro cần giải quyết |
| --- | --- | --- |
| Đọc store authoritative mỗi request | Hiệu lực thu hồi nhanh, dễ lý giải | DB latency/tải và outage |
| Cache metadata TTL ngắn | Giảm tải | Staleness tối đa gần TTL + replica lag |
| Pub/sub invalidation + version | Đẩy cập nhật nhanh | Missed event, out-of-order, consumer offline |
| Gateway/introspection tập trung | Một nơi enforce | HA, không bypass gateway |
| Keys TTL ngắn | Thu hẹp cửa sổ bị lộ | Không thay thế revoke khẩn trước expiry |

Nếu yêu cầu thu hồi trong vài giây, cache TTL 10 phút không đáp ứng. Cần version/sequence, invalidation có acknowledgement hoặc read-through; đo thời gian đến khi **mọi region** thật sự từ chối.

Race nguy hiểm:

~~~text
T1: đọc K1=ACTIVE trước rotation
T2: phát hiện lộ -> REVOKE K1, commit
T1: ghi snapshot cũ K1=ACTIVE  <-- BUG, key sống lại
~~~

Sửa bằng transaction hoặc optimistic locking và chuyển trạng thái một chiều:

~~~sql
UPDATE api_keys
SET revoked_at = :now, version = version + 1
WHERE key_id = :id AND revoked_at IS NULL AND version = :expected_version;
~~~

Nếu cập nhật 0 hàng, đọc state mới rồi quyết định, không ép ghi ACTIVE. Rotation thêm record K2 và cập nhật cutoff K1 theo điều kiện. Cache invalidation nên có version để một event cũ không làm cache nhận lại trạng thái active.

Cần xác định chính sách đối với request đã bắt đầu trước thời điểm revoke transaction commit. Một lookup hợp lệ trước commit không nhất thiết chấm dứt ngay request đang chạy; nếu muốn cắt cả job/stream dài hạn thì cần authorization check lại hoặc đóng session/connection tại boundary phù hợp.

## 12. Triển khai client và cập nhật secret

Backend nhận K2 rồi nhưng caller vẫn có thể phát K1 nếu:

- Kubernetes pod hoặc service nạp secret khi khởi động chưa restart.
- CI/CD variable, Vault, cloud secret manager hoặc External Secrets cập nhật chậm.
- Batch cuối tháng, cron ít chạy, môi trường dự phòng hoặc script vận hành giữ bản cũ.
- SDK singleton/connection pool cache header credential nhiều giờ.
- Các service staging/prod dùng lẫn secret hoặc proxy không chuyển header đúng.

Trong overlap, theo dõi K1/K2 usage **qua key ID** trong audit, không log raw secret. Tới cutoff, xác minh mọi job dự kiến đã chuyển K2; sau đó revoke K1 và theo dõi số request còn gửi K1. Nếu một job hiếm khi chạy cần thêm thời gian, phải giải quyết trong change plan có phê duyệt trước cutoff, không tự mở grace vô hạn.

## 13. API quản trị vòng đời

Các endpoint sau là thiết kế **của ứng dụng**, Spring Security không tự tạo:

| Endpoint | Vai trò | Điều kiện |
| --- | --- | --- |
| `POST /admin/api-keys` | Tạo key, trả secret một lần | Xác thực admin/owner và authorize scopes |
| `GET /admin/api-keys` | Liệt kê metadata, không raw key | Quyền quản lý và audit |
| `POST /admin/api-keys/{id}/rotate` | Cấp K2, link K1 | Idempotency, không nâng quyền |
| `POST /admin/api-keys/{id}/revoke` | Thu hồi trước hạn | Atomic, idempotent, ghi audit |
| `POST /admin/owners/{id}/revoke-all` | Offboard owner và keys | Đặc quyền, hạn chế blast radius |

API quản trị nên dùng OIDC có MFA/RBAC, mTLS hoặc service identity mạnh, tách biệt với key thường. Không cho key đang quản lý tự tạo key khác có quyền cao. Chỉ chấp nhận owner và scopes sau khi kiểm tra quyền theo dữ liệu server.

**Retry/idempotency:** Nếu transaction cấp K2 thành công nhưng response mất, retry mù quáng có thể sinh K3. Dùng idempotency key/workflow giao key an toàn, và chính sách xử lý key cấp dở. Không lưu raw secret lâu dài chỉ để replay response: nếu raw key bị mất, revoke record đã cấp dở và cấp lại có audit.

## 14. Audit, cảnh báo và phản ứng sự cố

Ghi nhận sự kiện phát hành, rotate, revoke, expire, sử dụng lại revoked key, actor, reason, key ID, owner và correlation ID. Log cần giảm dữ liệu nhạy cảm, phân quyền truy cập, chống sửa trái phép và retention rõ ràng.

~~~text
event=key_rotated at=2026-11-06T09:00:00Z
owner=billing-worker old_id=ak_prod_****2f new_id=ak_prod_****83
event=key_revoked at=2026-11-06T09:15:00Z
owner=billing-worker id=ak_prod_****2f reason=cutover
~~~

Các ID đã che chỉ để minh họa; không chứa secret. Không đưa raw header, secret, digest đầy đủ, token, username nhạy cảm vào log/tracing/metrics hoặc URL. Metric label nên có nhóm cố định như `result=valid|invalid|expired|revoked|infra_error` và `environment`; tránh key ID làm nhãn cardinality cao.

Quan sát: số key sắp hết hạn, K1 được dùng sau cutoff, p95/p99 thời gian xác thực, 401/403 theo client, store 5xx, invalidation lag, vùng có kết quả auth không nhất quán và clock drift. Khi phát hiện lộ key, trình tự ưu tiên là **revoke, xác minh hiệu lực đa vùng, cấp mới an toàn, cập nhật client, điều tra audit/ảnh hưởng và sửa nguồn lộ**.

## 15. Kiểm thử

**Unit test với `Clock.fixed` hoặc `Instant` do server cung cấp:**

1. Sinh K1/K2 khác nhau; store không chứa raw secret; secret có entropy đủ.
2. Sai một ký tự secret, key ID không tồn tại, đầu vào quá dài/malformed đều bị từ chối.
3. `now=expiresAt.minusNanos(1)` còn hợp lệ; `now=expiresAt` và sau đó đều không hợp lệ.
4. Trước `activatedAt` bị từ chối; khóa revoked bị từ chối dù chưa expired.
5. K1/K2 chấp nhận đúng overlap, K1 bị chặn sau cutoff, K2 còn hạn hoạt động.
6. Revoke hai lần không hồi sinh khóa, rotate và revoke đồng thời không mất cập nhật.
7. Owner disabled, cross-environment, sai audience và thiếu scope bị chặn.
8. Store timeout không cho request đi tiếp, báo lỗi hạ tầng.
9. Cache invalidation mất sự kiện/đến muộn vẫn đáp ứng SLA thu hồi.
10. Request đa instance/region có quyết định đồng nhất sau revoke.

**Integration test Spring Security qua `MockMvc`:**

| Request | Kết quả bảo mật |
| --- | --- |
| `GET /api/orders/1` không có header | 401 |
| Key có `orders:read` đúng, request GET | Xác thực thành công, chính xác principal |
| Key chỉ `orders:read`, request POST cần `orders:write` | 403 |
| Key expired, revoked hoặc sai secret | 401, không tạo session |
| Hai header `X-API-Key` | 401 |
| Key store hỏng | 5xx/503 theo error policy, tuyệt đối không 200 |
| K1 sau cutoff / K2 còn hạn | K1: 401; K2: được xác thực |
| Vượt quota | 429 qua rate limiter |

Test trạng thái security tách với status nghiệp vụ (một controller hợp lệ vẫn có thể trả 404). Khi dùng WebFlux, dùng `WebTestClient` thay vì `MockMvc`. Trong staging, thực hiện rotation thật với 2 client versions, test client không restart, job hằng tháng, replica lag, clock skew và đo trễ revoke đến từng instance.

## 16. Lỗi thường gặp

| Cách làm sai | Nguy cơ | Cách sửa |
| --- | --- | --- |
| Overwrite secret trên cùng key ID lúc rotate | Client đứt kết nối, mất audit lineage | Mỗi phiên bản ID + record riêng |
| Cho overlap vô hạn | K1 vẫn truy cập được lâu sau khi có K2 | Cutoff hữu hạn và đo lường |
| Chỉ chạy cron xóa expired | Cron lỗi thì key còn hiệu lực | Check expiry ở mỗi request |
| Lộ key vẫn chờ hết grace | Kẻ có key tiếp tục dùng | Revoke khẩn |
| Lưu raw key vào DB/log | Database/log leak thành credential leak | Lưu digest/HMAC và chỉ hiển thị một lần |
| Cache `valid=true` quá lâu | Revoke trên giấy | Invalidation hoặc TTL phù hợp SLA |
| Cho phép viết ACTIVE sau revoke | Key cũ sống lại | State terminal, transaction/version |
| Bỏ kiểm tra owner/scopes | Vượt quyền | Authorities từ server metadata |
| Map mọi exception thành 401 | Che DB outage | 5xx/503 và fail closed |
| Đưa key vào URL query | Lộ trong log và browser history | HTTPS header, redaction |
| Tái dùng key prod ở staging | Mở rộng phạm vi lộ secret | Keys tách môi trường |

## 17. Checklist trước production

- [ ] Secret ngẫu nhiên tối thiểu 256 bit; ID công khai tách riêng; lưu digest/HMAC có quản lý version.
- [ ] Key có owner, scope, environment, activated/expired/revoked, rotation lineage, audit.
- [ ] Raw key chỉ giao một lần qua kênh bảo mật; không có plaintext trong DB, Git, log, URL, CI/CD.
- [ ] Auth kiểm tra thời gian UTC và trạng thái từng request, đúng mốc `now < expiresAt`.
- [ ] 401/403/429/5xx đúng ngữ nghĩa; không fail open khi key store unavailable.
- [ ] Rotation cấp K2 độc lập, overlap hữu hạn, client rollout, cutoff và test từ chối K1.
- [ ] Revoke idempotent/terminal, atomic, có audit; lan truyền đến mọi instance theo SLA.
- [ ] Có rate limit/quota, theo dõi bất thường, hạn chế thông tin lỗi.
- [ ] Admin API có cơ chế xác thực mạnh/RBAC riêng và cơ chế xử lý key thất lạc/offboarding.
- [ ] Có test thời gian biên, revoke race, cache mất event, multi-region và rotation client hiếm khi chạy.

**Điểm chính:** Luân chuyển là **phát hành khóa mới và cắt khóa cũ có kiểm soát**; hết hạn là điều kiện **thực thi ngay khi xác thực**, còn thu hồi vô hiệu hóa trước hạn và phải được phản ánh trên mọi API instance. Spring Security chỉ đưa client vào `SecurityContext` sau khi xác minh khóa, rồi dùng `GrantedAuthority` để quyết định quyền; thời gian, audit, secrets và consistency quyết định mức an toàn thực tế.

## Tài liệu tham khảo

- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Filter Chain Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
- [Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
