# Yêu cầu xác thực bổ sung cho thao tác nhạy cảm trong Spring Security (step-up MFA)

## 1. Đặt vấn đề: đăng nhập thành công không đủ cho mọi thao tác

Một người dùng đã đăng nhập có thể đọc danh sách đơn hàng, xem số dư hoặc chỉnh sửa một số thông tin ít rủi ro. Nhưng các hành động như **chuyển tiền**, **đổi email/mật khẩu**, **thêm thiết bị MFA**, **tắt MFA**, **phát hành API key quyền cao**, **thay đổi người thụ hưởng** hay **xóa dữ liệu hàng loạt** cần bằng chứng xác thực mạnh hơn hoặc mới hơn.

**Step-up authentication** là yêu cầu người dùng xác thực bổ sung khi đi tới một thao tác, tài nguyên hoặc ngữ cảnh rủi ro cao. Nó không nhất thiết phải buộc logout rồi login lại toàn bộ. Chính sách step-up có thể yêu cầu:

1. **Độ mạnh**: đã dùng các yếu tố/phương thức phù hợp, ví dụ password kết hợp WebAuthn.
2. **Độ mới (freshness)**: yếu tố cần thiết đã được chứng minh trong vòng vài phút, không phải từ phiên đăng nhập sáng hôm qua.
3. **Đúng chủ thể và phiên**: cùng account/session đang thực hiện thao tác.
4. **Đúng hành động hoặc giao dịch**: bước xác thực bổ sung được áp dụng cho *người thụ hưởng, số tiền, thiết bị hoặc thay đổi cụ thể*.
5. **Quyền nghiệp vụ hiện hành**: account vẫn có quyền thực hiện thay đổi, không chỉ có bằng chứng MFA.

Ví dụ: tài khoản `alice` đăng nhập từ 08:00 bằng password và đang có `ROLE_USER`. Lúc 17:00, Alice muốn thêm một tài khoản nhận tiền. Ứng dụng hiển thị thông tin người thụ hưởng, yêu cầu xác thực bằng WebAuthn hoặc một yếu tố theo policy, sau đó chỉ thực hiện hành động khi **bằng chứng mới, phù hợp, chưa bị sử dụng** và quyền của Alice vẫn còn hiệu lực.

Mục tiêu là chống lại các rủi ro như trình duyệt bị để quên, phiên bị chiếm đoạt, thao tác bị CSRF hoặc lạm dụng một phiên đăng nhập lâu dài. Step-up không thể tự chữa mọi lỗi XSS/CSRF hoặc thiết bị đã bị kiểm soát hoàn toàn, nhưng giúp tạo thêm ranh giới bảo vệ.

## 2. Hiểu đúng “yếu tố”, “xác thực lại” và “phân quyền”

| Khái niệm | Câu hỏi cần giải quyết | Ví dụ |
| --- | --- | --- |
| **Authentication** | Người đang giao tiếp có phải chủ thể đã khai không? | Password, passkey, chứng thư... |
| **Multi-Factor Authentication (MFA)** | Có đủ những yếu tố độc lập theo mức đảm bảo yêu cầu không? | Password + yếu tố sở hữu |
| **Re-authentication** | Người đang giữ phiên có vừa chứng minh lại quyền kiểm soát tài khoản không? | Nhập lại password, xác thực lại với IdP |
| **Step-up** | Yêu cầu đảm bảo mạnh hơn/mới hơn cho một tác vụ cụ thể | Passkey mới trước khi đổi email |
| **Authorization** | Sau khi đã xác thực, người dùng có quyền *làm gì và trên tài nguyên nào*? | Chỉ được chuyển từ ví chính mình |
| **Transaction authorization** | Người dùng có thật sự xác nhận chính giao dịch này không? | Xác nhận người nhận và số tiền đã hiển thị |

Hai lần nhập **cùng mật khẩu** không tạo ra hai yếu tố. Cookie đăng nhập, device fingerprint, IP, vị trí địa lý hoặc việc nhận diện một máy “đã tin cậy” **không tự trở thành yếu tố độc lập**; có thể dùng như tín hiệu đánh giá rủi ro.

Ví dụ lựa chọn xác thực:

- **Password + TOTP** có hai loại yếu tố theo mô hình phù hợp; cần bảo vệ TOTP secret, chống replay trong cửa sổ, rate limiting và recovery.
- **Password + WebAuthn/passkey** có thể cung cấp xác thực chống phishing với chính sách phù hợp; WebAuthn với user verification/passkey có thể là authenticator đa yếu tố trong một lần xác minh, tùy thiết bị, chính sách và mức đảm bảo.
- **Email OTP sau password** có thể nâng rào cản cho một số ứng dụng, nhưng email là kênh có thể bị chiếm cùng lúc hoặc bị forward; không mặc nhiên đạt yêu cầu assurance cao.
- **SMS OTP** có rủi ro SIM swap/phishing; nếu dùng phải áp dụng chính sách giảm thiểu và hiểu giới hạn.
- **Chỉ nhập lại password** là re-authentication, **không phải** tự động MFA.

Ưu tiên yếu tố **phishing-resistant** (như WebAuthn/FIDO2 khi phù hợp) cho hành động nhạy cảm cao. Lựa chọn cụ thể xuất phát từ threat model, yêu cầu tổ chức và hỗ trợ người dùng.

## 3. Ma trận chính sách cho từng nhóm thao tác

Chính sách nên được mô tả bằng hành động/tài nguyên, không chỉ theo tên URL hoặc role:

| Hành động | Yêu cầu cơ bản | Yêu cầu bổ sung ví dụ | Ràng buộc quan trọng |
| --- | --- | --- | --- |
| Xem hồ sơ cơ bản | Đăng nhập | Thường không cần step-up | Tenant và quyền đọc |
| Đổi tên hiển thị | Đăng nhập | Có thể không cần | Chống CSRF |
| Đổi mật khẩu | Đăng nhập/khôi phục hợp lệ | Xác thực lại gần đây hoặc MFA theo rủi ro | Thu hồi session/token cũ nếu policy |
| Thay email nhận thông báo bảo mật | Đăng nhập | Step-up + xác minh địa chỉ mới | Chặn chiếm account qua đổi email |
| Thêm/xóa passkey, TOTP, recovery methods | Đăng nhập | Xác thực mạnh và mới; bảo vệ recovery path | Không cho dùng factor mới chưa xác minh để tự phê duyệt nó |
| Phát hành API key quyền quản trị | Quyền quản trị | MFA mới và confirmation | Giới hạn scope, TTL, audit và không lộ key |
| Chuyển tiền/thay đổi người hưởng | Quyền sở hữu tài khoản nguồn | MFA mới; với rủi ro cao ràng buộc giao dịch | Account nguồn, người nhận, số tiền, idempotency |
| Xóa dữ liệu diện rộng | `ROLE_ADMIN` + quyền trên tập dữ liệu | Step-up và có thể approval thứ hai | Phạm vi bản ghi, audit, rollback khi áp dụng |
| Đổi cấu hình bảo mật toàn tổ chức | Quyền tương ứng | MFA mạnh, thời gian rất mới, có thể yêu cầu “four eyes” | Không tự phê duyệt quyền của chính mình |

**Ví dụ về thời gian 3–5 phút** trong bài chỉ là gợi ý chính sách bảo vệ thao tác rủi ro; không phải giá trị mặc định chung do Spring Security hay NIST quy định. Cần xác định theo mức độ nguy hiểm, trải nghiệm và tiêu chuẩn áp dụng.

Điều kiện cho phép cuối cùng thường có dạng:

```text
ALLOW nếu và chỉ nếu:
  authenticatedCurrentSession
  AND correctAccount
  AND allowedBusinessRole
  AND allowedResourceOwnership
  AND requiredFactorSuccessfullyVerified
  AND factorEvidenceStillFresh
  AND correctOperationBound
  AND proofNotConsumedBefore
  AND accountNotLockedOrRevoked
  AND requestPassesCSRF/anti-replay/idempotencyControls
```

“Đã có `ROLE_ADMIN`” và “đã qua MFA” là **hai điều kiện khác nhau**. Người dùng không có quyền quản trị không được trở thành admin chỉ vì vừa cung cấp một mã OTP.

## 4. Luồng step-up an toàn từ UI đến commit nghiệp vụ

```text
(1) Browser: POST /transfers/prepare với payload giao dịch
             |
             v
(2) Backend: authenticated? account/tenant/role/limit?
             |
             v
(3) Lưu pending action / challenge server-side:
    id, accountId, sessionId, actionFingerprint,
    requiredAssurance, createdAt, expiresAt
             |
             v
(4) UI hiển thị chính xác số tiền, đích nhận, loại thay đổi
             |
             v
(5) User xác thực bổ sung:
    WebAuthn assertion hoặc provider OTP đã xác minh
    (không coi một boolean client gửi là bằng chứng)
             |
             v
(6) Server ghi verifiedFactor + verifiedAt,
    liên kết account/session/challenge/action
             |
             v
(7) Browser: POST /transfers/confirm cùng challenge ID,
    gửi lại dữ liệu được ký/so khớp hoặc tham chiếu
    pending action bất biến server-side
             |
             v
(8) Backend: atomic claim proof
    + kiểm tra freshness/ownership/role/account
    + kiểm tra action fingerprint còn chính xác
             |
             v
(9) Commit transfer hoặc queue transactional outbox
    -> kết quả idempotent, audit, thông báo
```

Tách **chuẩn bị**, **xác minh yếu tố** và **thực hiện thay đổi** để người dùng biết mình đang phê duyệt điều gì. Khi người nhận hoặc số tiền đổi sau khi xác thực, bằng chứng cũ phải **không còn dùng được cho phiên bản giao dịch mới**.

Không lấy action ID, account ID, role hoặc trạng thái `mfaPassed` từ body/header do client tự khai rồi tin luôn. Browser có thể truyền ID tham chiếu, nhưng server phải truy vấn ngữ cảnh đáng tin đã được liên kết, xác minh và so khớp lại.

### Điểm cần phân biệt

- Một **factor đã được chứng minh gần đây** có thể đủ để truy cập trang cấu hình bảo mật. Điều này khác với **phê duyệt một chuyển khoản cụ thể**.
- Nếu policy cần *transaction binding*, chỉ gắn cờ `mfaVerified=true` trong toàn bộ phiên sẽ không đủ. Một xác thực của giao dịch A không được tự cấp phép cho giao dịch B.
- **Một lời xác nhận MFA chưa chắc một lần sử dụng:** ứng dụng có thể chọn “MFA hợp lệ 5 phút cho nhóm hành động” hoặc “mỗi giao dịch phải có bằng chứng dùng một lần”. Phải nói rõ loại nào được phép và test theo policy.

## 5. Freshness: bằng chứng MFA có thời điểm và hạn riêng

Cần phân biệt các thời điểm:

- `sessionCreatedAt`: lúc session ứng dụng bắt đầu.
- `primaryAuthenticatedAt`: lần gần nhất user chứng minh primary credential.
- `factorVerifiedAt`: lúc server/IdP kiểm chứng thành công yếu tố bổ sung.
- `proofExpiresAt`: hạn cuối proof được chấp nhận cho hành động/đường cần bảo vệ.
- `operationCreatedAt` / `operationVersion`: lúc dữ liệu giao dịch được xác lập.
- `accountRevokedAt` / `mfaFactorDisabledAt`: sự kiện có thể buộc hủy proof cũ.

Ví dụ:

```text
09:00  Login bằng password -> session A
12:40  Mở trang thường -> session A vẫn hợp lệ
12:41  Chuẩn bị thay đổi người nhận X -> challenge C1
12:42  Xác thực WebAuthn thành công cho C1
12:43  POST confirm C1, đúng người nhận X -> cho phép nếu đủ quyền
12:43  POST confirm C1 lần nữa -> từ chối replay
12:44  Đổi payload sang người nhận Y rồi dùng C1 -> từ chối
12:46  Dùng C1 lần đầu (nếu chưa tiêu thụ) -> hết hạn nếu TTL 3 phút
```

**So sánh thời gian chính xác** bằng Java `Instant`/UTC và `Clock` được inject để dễ test: `now.isBefore(expiresAt)`. Khi `now == expiresAt` là **hết hạn**; không tin giờ trên điện thoại/browser. Với nhiều node, cân nhắc đồng hồ DB hoặc cơ chế đồng bộ; không để cache snapshot vượt quá thời gian hiệu lực.

Đối với yếu tố đa lần, **factor evidence timestamp cần được phát hành bởi code xác thực tin cậy** (hoặc được lấy từ token IdP đã kiểm chứng); không để client tự gửi `verifiedAt` mới bằng cách sửa JSON. Khi logout, đổi account, disable factor hoặc reset password, phải xem có cần revoke proof/session hiện tại hay không theo chính sách.

## 6. Spring Security 7.x: FactorGrantedAuthority và yêu cầu MFA theo URL

**Giới hạn phiên bản rất quan trọng:** `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication` và `AuthorizationManagerFactories` là API được giới thiệu ở **Spring Security 7.0**. Không copy nguyên mẫu dưới đây vào ứng dụng Spring Security 6.x/Boot 3.x rồi kỳ vọng nó tồn tại.

Spring Security 7.x có thể gắn `FactorGrantedAuthority` khi các authentication mechanisms tương ứng thành công. Ví dụ:

- `FactorGrantedAuthority.PASSWORD_AUTHORITY` — `FACTOR_PASSWORD`.
- `FactorGrantedAuthority.OTT_AUTHORITY` — `FACTOR_OTT`.
- `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` — `FACTOR_WEBAUTHN`.

Factor authority chứa `issuedAt`, phục vụ chính sách độ mới. Điều kiện **“có hai factor”** trong authorization không tự tạo trang login/đăng ký yếu tố; bạn còn phải cấu hình các authentication mechanisms để thực sự thu nhận bằng chứng tương ứng. `OTT` trong ví dụ là one-time token login, **không đồng nghĩa với mọi loại TOTP/passkey**.

### 6.1. Chỉ yêu cầu MFA trên endpoint nhạy cảm (Servlet)

Ví dụ dưới đây theo API Spring Security **7.0**, sử dụng form login + one-time-token login và yêu cầu cả hai trên các đường nhạy cảm. Đặt trong dự án Spring Boot dùng Spring Security 7.x tương thích (thường là Boot 4.x; chọn dependency versions tương ứng).

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactories;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {})
public class SensitiveMfaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        var multiFactor = AuthorizationManagerFactories
                .<RequestAuthorizationContext>multiFactor()
                .requireFactors(
                        FactorGrantedAuthority.PASSWORD_AUTHORITY,
                        FactorGrantedAuthority.OTT_AUTHORITY)
                .build();

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/settings/security/**")
                            .access(multiFactor.authenticated())
                        .requestMatchers("/admin/keys/**")
                            .access(multiFactor.hasRole("ADMIN"))
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .oneTimeTokenLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Ý nghĩa:**

1. `@EnableMultiFactorAuthentication(authorities = {})` bật cơ sở hỗ trợ MFA nhưng **không áp đặt** cùng yêu cầu factor trên tất cả các authorization rules.
2. Factory `multiFactor` yêu cầu đủ `FACTOR_PASSWORD` và `FACTOR_OTT` cho các matcher được gọi `.access(multiFactor...)`.
3. `/admin/keys/**` đòi cả **ROLE_ADMIN** lẫn hai factor. Các đường còn lại chỉ cần authenticated.
4. Cần cung cấp `UserDetailsService` hoặc nguồn người dùng, cấu hình gửi one-time token qua kênh tin cậy, UI phù hợp và CSRF/session/cookie mặc định đúng. Đây là **lớp cấu hình**, không phải một chương trình Java độc lập có thể chạy bằng `javac`.
5. Cấu hình route-factor chỉ đảm bảo **yêu cầu yếu tố tại thời điểm truy cập**; chưa ràng buộc `actionFingerprint` cho một chuyển khoản cụ thể hoặc ngăn replay giao dịch. Phần nghiệp vụ cần bước tiếp theo.

Không áp dụng ví dụ này cho WebFlux `ServerHttpSecurity`: tài liệu API `@EnableMultiFactorAuthentication` 7.0 nêu hỗ trợ MFA cụ thể ở **Servlet**, và reactive hỗ trợ khác/không tương đương tại phiên bản đó. Xác minh phiên bản reactive thực tế trước khi triển khai.

### 6.2. Yêu cầu factor còn mới trong một khoảng thời gian

Spring Security 7.x có `RequiredFactor` với `validDuration`. Ví dụ code **thay thế** để yêu cầu một lần xác thực password trong 5 phút và one-time token trong 5 phút (theo policy minh họa):

```java
// Mảnh cấu hình Spring Security 7.x, bên trong method @Bean
// SecurityFilterChain đã có HttpSecurity và các import tương ứng.
var recentMfa = AuthorizationManagerFactories
        .<RequestAuthorizationContext>multiFactor()
        .requireFactor(factor -> factor
                .passwordAuthority()
                .validDuration(Duration.ofMinutes(5)))
        .requireFactor(factor -> factor
                .ottAuthority()
                .validDuration(Duration.ofMinutes(5)))
        .build();

// Trong authorizeHttpRequests:
// .requestMatchers("/settings/security/**")
//     .access(recentMfa.authenticated())
// .requestMatchers("/admin/keys/**")
//     .access(recentMfa.hasRole("ADMIN"))
```

Cần import `java.time.Duration`. Không được tự biến thời điểm đăng nhập cũ thành `issuedAt=now` chỉ để qua kiểm tra. `validDuration` kiểm tra **độ mới của factor**, **không** thay cho transaction binding, confirmation và one-time proof nếu business action có yêu cầu đó.

### 6.3. Chọn factor theo mức rủi ro

Spring Security 7.x còn có cơ chế yêu cầu nhiều combination factor và policy có điều kiện, ví dụ password + OTT hoặc passkey/WebAuthn theo cấu hình đã đăng ký. Đừng coi `@EnableMultiFactorAuthentication(authorities = {...})` với mọi rule là giải pháp mặc định: trang công khai, callback xác thực, recovery và những endpoint không cần step-up có thể trở nên khó truy cập nếu policy áp dụng tràn lan.

**Nguyên tắc:** chỉ định rõ endpoint/đối tượng phải đòi assurance nào; bảo đảm các flow để bổ sung factor có thể truy cập an toàn mà không tạo bypass cho protected resource.

## 7. Spring Security 6.x: thiết kế step-up ở tầng ứng dụng

Với Spring Security 6.x (Boot 3.x), có thể triển khai step-up bằng **policy ở ứng dụng** kết hợp với provider xác thực second factor đáng tin. Tránh nhầm với API 7.0 ở mục trước.

Kiến trúc gợi ý:

```text
SecurityFilterChain / oauth2Login / formLogin
        |
        v
Authentication + Session (đã login)
        |
        v
Controller/service chuẩn bị sensitive action
        |
        v
StepUpChallengeService
  - issue challenge server-side
  - verify TOTP/WebAuthn/re-auth IdP theo chuẩn
  - record factor evidence (trusted server only)
  - bind to account + session + action + TTL
        |
        v
POST confirm -> @PreAuthorize(role/permission)
  -> StepUpApprovalService.atomicConsumeAndExecute(...)
        |
        v
DB transaction / transactional outbox -> success
```

Các trách nhiệm cần tách:

- **Authentication Provider**: xác minh password, TOTP hoặc assertion WebAuthn. Đừng so khớp một chuỗi OTP từ browser với code đã lộ ở HTML/session mà không có policy bảo mật.
- **Challenge Service**: lưu challenge ID ngẫu nhiên, TTL, accountId, session binding, operation hash và trạng thái còn hiệu lực. Chống brute force/replay và giới hạn số lần thử.
- **Step-Up Proof Store**: chỉ ghi bằng chứng **sau khi yếu tố thực sự được xác minh**; hỗ trợ expire/revoke/consume atomically.
- **Authorization service**: kiểm tra role/ownership và trạng thái account hiện tại, không chỉ dựa vào thông tin từ lúc login.
- **Business Service**: commit hành động và update proof theo một transaction nếu cùng DB, hoặc dùng outbox/idempotency nếu đi qua hệ thống ngoài.

### Mẫu controller minh họa trong Spring MVC 6.x

```java
// Chỉ là mảnh mã, cần class @RestController, DTO, service
// và HTTP session/CsrfConfig được triển khai tương ứng.
@PreAuthorize("hasAuthority('TRANSFER_CREATE')")
@PostMapping("/api/transfers/{transferId}/confirm")
public ResponseEntity<Void> confirm(
        @PathVariable String transferId,
        @RequestBody ConfirmTransferRequest request,
        Authentication authentication,
        HttpSession session) {

    sensitiveTransferService.confirmAfterStepUp(
            authentication.getName(),
            session.getId(),
            transferId,
            request.approvalId());
    return ResponseEntity.noContent().build();
}
```

**Không được kết luận snippet này đủ để chuyển tiền an toàn**. Trong `confirmAfterStepUp` phải lấy giao dịch bất biến server-side từ `transferId`, kiểm tra account/tenant, role, beneficiary, amount, thời hạn, assurance, proof và atomic consume/trx trước khi thay đổi dữ liệu. Import/method body/DTO là của ứng dụng, nên snippet không phải một file chạy độc lập.

Spring Security method authorization cần bật `@EnableMethodSecurity` và bảo đảm đường service nhạy cảm cũng được bảo vệ, kể cả khi được gọi qua endpoint khác. Không chỉ để bước xác thực trên nút “Xác nhận” của frontend: mọi API/CLI/batch path phải tuân thủ cùng rule.

## 8. Ví dụ Java 17 chạy độc lập: chứng minh ràng buộc action, session, TTL và cạnh tranh

Ví dụ chạy **Java SE 17**, không cần Spring/IdP. Nó chỉ mô hình hóa **bằng chứng đã xác minh bởi server** chứ **không tự kiểm tra TOTP/WebAuthn**. Hãy tạo file **`StepUpDecisionDemo.java`** với mã sau:

```java
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class StepUpDecisionDemo {
    record Action(String kind, String destination, long amountCents) {
        Action {
            Objects.requireNonNull(kind);
            Objects.requireNonNull(destination);
            if (kind.isBlank() || destination.isBlank() || amountCents < 0) {
                throw new IllegalArgumentException("Invalid sensitive action");
            }
        }
    }

    record VerifiedPermit(
            String userId,
            String sessionId,
            Action action,
            String factor,
            Instant verifiedAt,
            Instant expiresAt) {}

    static final class AdjustableClock extends Clock {
        private volatile Instant current;
        AdjustableClock(Instant start) {
            current = Objects.requireNonNull(start);
        }
        @Override public Instant instant() { return current; }
        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(current, zone);
        }
        void advance(Duration d) { current = current.plus(d); }
    }

    static final class StepUpProofStore {
        private final Clock clock;
        private final ConcurrentHashMap<UUID, VerifiedPermit> permits =
                new ConcurrentHashMap<>();

        StepUpProofStore(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        // Chỉ server gọi SAU KHI authenticator thực sự xác minh thành công.
        // Không expose method này như endpoint tự khai "factorVerified=true".
        UUID recordVerifiedFactor(
                String userId, String sessionId, Action action,
                String factor, Duration ttl) {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(sessionId);
            Objects.requireNonNull(action);
            if (userId.isBlank() || sessionId.isBlank()
                    || !Set.of("WEBAUTHN", "TOTP").contains(factor)
                    || ttl == null || ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("Invalid verified proof");
            }

            Instant now = clock.instant();
            UUID permitId = UUID.randomUUID();
            permits.put(permitId, new VerifiedPermit(
                    userId, sessionId, action, factor,
                    now, now.plus(ttl)));
            return permitId;
        }

        boolean consume(
                UUID permitId, String userId,
                String sessionId, Action submitted) {
            if (permitId == null || userId == null
                    || sessionId == null || submitted == null) {
                return false;
            }

            AtomicBoolean accepted = new AtomicBoolean(false);
            permits.compute(permitId, (id, stored) -> {
                if (stored == null) return null;
                Instant now = clock.instant();
                if (!now.isBefore(stored.expiresAt())) return null;
                if (now.isBefore(stored.verifiedAt())) return stored;
                if (!stored.userId().equals(userId)
                        || !stored.sessionId().equals(sessionId)
                        || !stored.action().equals(submitted)) {
                    return stored;  // không cho tiêu thụ sai ngữ cảnh
                }
                accepted.set(true);
                return null;       // xóa trong cùng thao tác atomic
            });
            return accepted.get();
        }
    }

    public static void main(String[] args) throws Exception {
        var clock = new AdjustableClock(
                Instant.parse("2026-01-01T00:00:00Z"));
        var store = new StepUpProofStore(clock);
        var transfer = new Action("TRANSFER", "partner-9", 125_000);
        UUID proof = store.recordVerifiedFactor(
                "alice", "session-A", transfer,
                "WEBAUTHN", Duration.ofMinutes(3));

        System.out.println("wrongSessionAccepted="
                + store.consume(proof, "alice", "session-B", transfer));
        System.out.println("changedActionAccepted="
                + store.consume(proof, "alice", "session-A",
                        new Action("TRANSFER", "attacker-1", 125_000)));
        System.out.println("firstUseAccepted="
                + store.consume(proof, "alice", "session-A", transfer));
        System.out.println("replayAccepted="
                + store.consume(proof, "alice", "session-A", transfer));

        UUID concurrentProof = store.recordVerifiedFactor(
                "alice", "session-A", transfer,
                "TOTP", Duration.ofMinutes(3));
        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            CountDownLatch gate = new CountDownLatch(1);
            List<Future<Boolean>> attempts = new ArrayList<>();
            for (int i = 0; i < 12; i++) {
                attempts.add(pool.submit(() -> {
                    gate.await();
                    return store.consume(concurrentProof,
                            "alice", "session-A", transfer);
                }));
            }
            gate.countDown();
            int accepted = 0;
            for (Future<Boolean> attempt : attempts) {
                if (attempt.get()) accepted++;
            }
            System.out.println("concurrentAccepted=" + accepted);
        } finally {
            pool.shutdownNow();
        }

        UUID expiredProof = store.recordVerifiedFactor(
                "alice", "session-A", transfer,
                "WEBAUTHN", Duration.ofMinutes(3));
        clock.advance(Duration.ofMinutes(3));
        System.out.println("atExpiryAccepted="
                + store.consume(expiredProof, "alice", "session-A", transfer));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac StepUpDecisionDemo.java
java StepUpDecisionDemo
```

Stdout chính xác (không in UUID ngẫu nhiên):

```text
wrongSessionAccepted=false
changedActionAccepted=false
firstUseAccepted=true
replayAccepted=false
concurrentAccepted=1
atExpiryAccepted=false
```

### Giải thích tại sao kết quả đúng

- `VerifiedPermit` ràng buộc `userId`, `sessionId`, `Action` và `verifiedAt`, `expiresAt`. `Action` là record immutable; nếu `destination` hoặc `amountCents` đổi, `equals()` không còn khớp.
- `recordVerifiedFactor(...)` **chỉ được gọi từ đường server sau khi xác minh authenticator thành công**. Demo không có bộ kiểm tra WebAuthn/TOTP, vì vậy gọi phương thức từ `main` chỉ tạo một fixture tin cậy, không chứng minh tính bảo mật của authenticator.
- `consume(...)` dùng `ConcurrentHashMap.compute(...)` để kiểm tra và xóa **cùng một bước nguyên tử trên một key**. Không có `get` trước rồi `remove` sau.
- Đầu vào sai session/action bị từ chối **mà không xóa** permit hợp lệ; chủ thể có thể tiếp tục dùng permit đúng trước khi hết hạn.
- Request thắng lần đầu xóa permit; replay bị từ chối. 12 request cạnh tranh cùng permit chỉ có một request được `true`; không phụ thuộc thứ tự lên lịch thread.
- `now.isBefore(expiresAt)` khiến mốc `now == expiresAt` không còn hiệu lực.
- Chương trình **không thực hiện chuyển tiền, không tạo Spring Security Authentication, không lưu dữ liệu giữa các JVM**. `ConcurrentHashMap` chỉ chứng minh concurrency trong *một process*. Production phải dùng DB/shared store với nguyên tử cấp hệ thống, và kết hợp business transaction/idempotency.

**Quan trọng:** dữ liệu bằng chứng này là **cấp phép một hành động**, không phải một loại `GrantedAuthority` được thêm tùy tiện từ request. Nếu cần scope nhiều thao tác trong 5 phút thay vì một lần, thiết kế riêng giới hạn và hậu quả của việc tái sử dụng proof.

## 9. Đảm bảo one-time / transaction binding ở cơ sở dữ liệu

Một database schema ý tưởng (PostgreSQL) cho transaction-bound step-up:

```sql
CREATE TABLE step_up_approvals (
    approval_id UUID PRIMARY KEY,
    account_id VARCHAR(100) NOT NULL,
    session_binding VARCHAR(128) NOT NULL,
    action_hash VARCHAR(128) NOT NULL,
    factor_type VARCHAR(40) NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    CHECK (expires_at > verified_at)
);
```

- `approval_id` là ID ngẫu nhiên khó đoán; nó **không tự là yếu tố xác thực**, vì chỉ được phát sau khi factor đã được kiểm chứng và được ràng buộc với session.
- `session_binding` có thể là HMAC/ID phiên đã được bảo vệ, không lưu session secret thô trong log hoặc URL.
- `action_hash` phải được tính từ biểu diễn canonical **server-side** của hành động, gồm account nguồn/đích, số tiền/đơn vị tiền, đối tượng nhận, action type, version hoặc nonce. Không dùng `hashCode()` của Java làm fingerprint bảo mật.
- `factor_type`/`verified_at` phản ánh method đã xác minh và thời điểm đáng tin; không lấy một trường tự khai từ client.

Một cách “claim nguyên tử” bằng PostgreSQL:

```sql
UPDATE step_up_approvals
SET consumed_at = clock_timestamp()
WHERE approval_id = :approval_id
  AND account_id = :account_id
  AND session_binding = :session_binding
  AND action_hash = :action_hash
  AND factor_type = :required_factor
  AND consumed_at IS NULL
  AND revoked_at IS NULL
  AND verified_at <= clock_timestamp()
  AND expires_at > clock_timestamp()
RETURNING approval_id;
```

Nếu trả 1 row: request được quyền sử dụng proof một lần. Nếu 0 row: sai account/session/action/factor, hết hạn, bị revoke, đã dùng hoặc không tồn tại. Request **không được thực hiện action** nếu không claim được.

**Lưu ý về thời gian giao dịch:** `clock_timestamp()` ở PostgreSQL trả giờ thực tại thời điểm gọi, khác `CURRENT_TIMESTAMP` thường cố định từ đầu transaction. Trong truy vấn ở trên, các lần gọi có thể lệch vi mô; nếu yêu cầu thời điểm kiểm tra tuyệt đối nhất quán, chốt một mốc trong cùng bước atomic và áp dụng đúng predicate đó. Đừng dùng time do browser truyền hoặc một lần kiểm tra trước khi chờ lock rồi bỏ qua expiry sau khi chờ.

### Claim thành công chưa bảo đảm business effect exactly once

Mẫu giao dịch an toàn khi approval và business data nằm cùng database:

```text
BEGIN TRANSACTION
  - đọc dữ liệu chuyển tiền/tài khoản/tenant đáng tin
  - kiểm tra permission, ownership, giới hạn và trạng thái account
  - atomic claim approval (UPDATE ... RETURNING)
  - nếu không có row -> ROLLBACK, từ chối
  - tạo business operation với UNIQUE idempotency key
  - cập nhật số dư/chuyển trạng thái nhất quán
  - ghi audit/outbox event
COMMIT
```

Nếu thao tác gọi payment gateway hoặc service khác, transaction DB không thể phủ mạng ngoài. Khi request timeout sau commit, client có thể retry. Dùng **idempotency key cho business operation**, transactional outbox và consumer idempotent, không chỉ dựa vào `approval.used=true`.

**Nếu hệ thống nhiều instance:** không dùng `synchronized` hoặc `ConcurrentHashMap` làm ranh giới xác thực chung. Tùy DB/Redis, dùng atomic compare-and-set, row lock, unique constraint hoặc transaction. Test request đồng thời ở hai pod, không chỉ test trong một JVM.

## 10. SSO/OIDC: step-up qua Identity Provider là luồng khác

Nếu ứng dụng dùng `oauth2Login()`/OIDC, nó có thể yêu cầu **IdP xác thực lại hoặc nâng assurance** cho một tác vụ. Các tham số liên quan:

- `prompt=login`: yêu cầu IdP xác thực người dùng trở lại (theo hợp đồng IdP), nhưng **không tự đồng nghĩa MFA**.
- `max_age`: yêu cầu tuổi của authentication event không vượt một ngưỡng, và kiểm tra `auth_time` từ ID Token theo yêu cầu OIDC.
- `acr_values`: yêu cầu mức `Authentication Context Class Reference` cụ thể, tùy IdP có hỗ trợ và chấp nhận hay không.
- `acr`: assertion mức assurance IdP báo; chỉ có ý nghĩa theo **thỏa thuận/metadata IdP đã được kiểm chứng**.
- `amr`: các phương pháp xác thực được IdP thông báo; không coi bất kỳ mảng string tùy ý nào là bằng chứng đủ mạnh.

Luồng:

```text
RP app có session cũ
  -> xác định action cần assurance cao
  -> tạo challenge (account/session/action), state + nonce
  -> redirect đến IdP với max_age / acr_values theo policy
  -> IdP thu thập bằng chứng cần thiết và redirect callback
  -> Spring Security kiểm chứng OIDC: state, nonce, signature,
     iss, aud, exp cùng ràng buộc authorization code flow
  -> ứng dụng KIỂM CHỨNG acr/auth_time/amr theo hợp đồng IdP
  -> liên kết đúng (iss, sub) với account/session hiện hữu
  -> ghi proof + timestamp server-side
  -> atomic confirm sensitive action
```

**Không chấp nhận callback step-up như một thao tác “đăng nhập user khác” rồi chuyển chủ pending transaction**. Nếu `(iss, sub)` callback không khớp local account được liên kết với action ban đầu, phải từ chối/hủy challenge; không thay người phê duyệt bằng người vừa đăng nhập mà không có workflow được phép.

Dùng IdP SSO cookie còn hoạt động có thể khiến redirect hoàn tất ngay; đó **không chứng minh** người dùng đã thực sự thực hiện MFA mới. Phải kiểm tra policy assurance và thời gian event, không suy luận từ việc callback thành công.

Token ID/Access Token có thời gian hết hạn riêng với `HttpSession`; hết hạn ID Token **không mặc nhiên** xóa session ứng dụng. Một step-up proof cũng không nên được gia hạn chỉ vì cookie session chưa hết hạn.

## 11. Stateless API, JWT và WebFlux: không sao chép nguyên mẫu Servlet

Với API stateless dùng `Authorization: Bearer`:

- `Authentication` của resource server được tạo từ access token mỗi request; không có app browser session mặc định.
- Nếu token/claims đã ký chứa `acr`/`amr`/`auth_time`, application có thể kiểm tra chúng **chỉ khi issuer/audience/signature/claims đã được xác minh** và IdP xác định rõ ý nghĩa.
- Một token access mang scope `transfer:write` không tự chứng minh người giữ token **vừa** xác thực yếu tố bổ sung.
- Để step-up, có thể yêu cầu client thực hiện authorization flow mới xin **access token mới** với assurance cao và audience/scope đúng, rồi resource server xác minh. Hoặc dùng transaction approval service tách biệt và ràng buộc proof với operation.
- Nếu API sử dụng JWT có hạn dài, token cũ có thể tiếp tục được dùng cho tài nguyên thường; endpoint nhạy cảm phải từ chối token thiếu assurance/độ mới.
- Không tin header tự khai `X-MFA-Verified: true` do client gửi; nếu gateway chuyển thông tin xác thực, bảo vệ mTLS/signature và trust boundary.

Với **Spring WebFlux**, `SecurityWebFilterChain` và `ReactiveSecurityContextHolder` khác với `HttpSecurity`/`SecurityContextHolder` của Servlet. Không cắm nguyên `@EnableMultiFactorAuthentication` Servlet hoặc filter HTTP servlet vào pipeline reactive rồi kỳ vọng chạy. Chọn API được hỗ trợ của đúng Spring Security version; transaction-bound approval service vẫn phải được gọi và consume nguyên tử qua reactive database driver hoặc I/O cách ly đúng.

## 12. CSRF, session fixation, quyền và lỗi có thể bypass step-up

### 12.1. Tách bước MFA khỏi session hijacking không đúng cách

Nếu chỉ ghi `session.setAttribute("mfa", true)` ở một endpoint mà không kiểm tra ai được phép gọi và yếu tố gì đã xác minh, kẻ tấn công có thể “mở khóa” cả session. Một bằng chứng step-up an toàn cần có ít nhất:

```text
userId, sessionId, factorType,
verifiedAt, validUntil,
challengeId / approvalId,
intendedAction + immutable parameters,
state (issued / verified / consumed / revoked)
```

Nên xóa/revoke các bằng chứng liên quan khi logout, session rotation theo policy, thay chủ account, hủy factor hoặc phát hiện compromise. Nếu thiết kế cho phép cùng một session có nhiều tab, cần phân biệt challenge bằng ID, không để tab A phê duyệt nhầm hành động tab B.

### 12.2. CSRF và replay là hai rủi ro khác nhau

- **CSRF protection** chống browser bị website khác thúc ép gửi request khi cookie session có hiệu lực. Giữ `CsrfFilter`/tokens phù hợp cho các request đổi trạng thái, gồm enroll/remove factor, issue/verify challenge và confirm action.
- **Step-up MFA** yêu cầu chủ thể chứng minh yếu tố. Không loại bỏ CSRF chỉ vì có MFA; kẻ tấn công vẫn có thể tác động flow, redirect hoặc dữ liệu giao dịch trong một số bối cảnh.
- **Replay protection** ngăn cùng proof/transaction được dùng nhiều lần; cần atomic consume/idempotency.
- **Transaction binding** ngăn user xác nhận người nhận A nhưng payload cuối lại thực hiện người nhận B.
- **Session fixation protection** khi login/reauthenticating tùy cơ chế; không chấp nhận session ID do client chỉ định, và không gắn proof cũ sang session mới ngoài chủ đích.

### 12.3. Không nâng quyền khi chỉ vì đã MFA

Factor evidence phải được ghép với các phép kiểm tra:

```text
hasAuthority("TRANSFER_CREATE")
AND ownerOfSourceAccount(currentUser, transfer.sourceAccount)
AND amountWithinLimits(transfer)
AND recipientAllowed(transfer.recipient)
AND hasRecentAppropriateFactor(currentSession, transfer)
AND atomicApprovalConsumed(transfer)
```

Không tự biến `FACTOR_WEBAUTHN` thành `ROLE_ADMIN`, cũng không thay thế kiểm tra `tenantId`/ownership bằng “đã qua OTP”.

### 12.4. Lỗi HTTP và trải nghiệm

- **401 Unauthorized**: chưa có xác thực cần thiết hoặc token resource server không hợp lệ, tùy kiểu ứng dụng.
- **403 Forbidden**: đã xác thực nhưng không đủ quyền/assurance hoặc bị policy từ chối; với browser app có thể **redirect sang bước yêu cầu factor** nếu hệ thống hỗ trợ entry point tương ứng.
- **409 Conflict**: đôi khi phù hợp khi confirmation dùng bản giao dịch cũ/đã thay đổi; không nên trả chi tiết khiến thông tin nhạy cảm bị lộ.
- **429 Too Many Requests**: giới hạn thử code/đăng ký/recovery; không dùng 429 thay cho policy xác thực.
- Hết TTL: hướng dẫn yêu cầu xác thực bổ sung mới, không tăng timestamp của proof cũ một cách tự động.

Một UX tốt hiển thị lý do và **đúng thông tin giao dịch cần phê duyệt**, đồng thời hạn chế “MFA fatigue” từ prompt liên tục. Không cấp phép chỉ vì user nhấp “Approve” vào một thông báo push không có ngữ cảnh.

## 13. Sai lầm thường gặp

**Lỗi 1 — MFA chỉ kiểm tra khi đăng nhập.** Người dùng để session 12 giờ nhưng API chuyển tiền chỉ có `authenticated()`. Cần policy độ mới/assurance tại thao tác.

**Lỗi 2 — Chỉ kiểm tra role mà không kiểm tra factor.** `ROLE_ADMIN` không có nghĩa user hiện tại đang kiểm soát authenticator của tài khoản. Kết hợp hai điều kiện.

**Lỗi 3 — Chỉ kiểm tra factor mà không kiểm tra quyền.** User bất kỳ làm TOTP thành công rồi được gọi admin API. Step-up không phải role cấp quyền.

**Lỗi 4 — Cờ toàn cục `mfa=true` trên session.** Mọi thao tác tiếp theo được “mở khóa” vô hạn. Giới hạn TTL/scope; transaction binding và single-use nếu cần.

**Lỗi 5 — Coi OIDC `prompt=login` là bằng chứng MFA.** Prompt chỉ yêu cầu đăng nhập lại, không bảo đảm đúng phương pháp/mức assurance; kiểm chứng `acr`/`amr`/`auth_time` theo hợp đồng.

**Lỗi 6 — Tin timestamp/boolean client gửi.** Browser có thể sửa JSON. Chỉ nhận chứng cứ đã được authenticator/IdP xác minh và đặt timestamp phía server.

**Lỗi 7 — Thay đổi payload sau MFA.** User thấy số tiền/đích A nhưng API xử lý B. Lưu pending action server-side, so fingerprint/version chính xác khi commit.

**Lỗi 8 — Race giữa hai request confirm.** Hai request đều đọc `approval.used=false` và thực hiện action. Dùng atomic compare-and-set/DB transaction và idempotent business operation.

**Lỗi 9 — Dùng `synchronized` nhưng triển khai 5 pod.** Lock chỉ bảo vệ một process. Shared DB/Redis state và transaction phù hợp mới áp dụng cho toàn cluster.

**Lỗi 10 — Nhầm “có passkey” và “vừa dùng passkey”.** Enrollment record không phải proof xác thực; luôn có event đã được xác minh ở đúng thời điểm.

**Lỗi 11 — Cho phép tắt MFA bằng chính email recovery không được bảo vệ.** Kẻ tấn công chiếm email có thể bypass; recovery path phải có assurance, rate limit, audit và thông báo tương xứng.

**Lỗi 12 — Request thay đổi factor tự tạo factor proof.** Ví dụ endpoint thêm TOTP cũng tự set `mfaVerified=true` từ code người dùng chưa đăng ký. Tách bước enroll và verify, rồi yêu cầu factor hiện có/step-up trước khi disable.

**Lỗi 13 — Bỏ qua CSRF vì “đã có MFA”.** Session cookie vẫn có thể bị lợi dụng; bảo vệ mọi endpoint thay đổi trạng thái và login/linking flows.

**Lỗi 14 — Không thu hồi proof sau đổi password/logout.** Có thể giữ bằng chứng cũ dù tài khoản/phiên bị thay. Xây dựng event-driven invalidation theo policy.

**Lỗi 15 — Log mã OTP, WebAuthn assertion, cookies hoặc approval secrets.** Log chỉ metadata tối thiểu và kết quả, che user identifiers theo retention; không log raw credentials.

**Lỗi 16 — Chỉ test luồng thành công.** Không kiểm thử cross-account/cross-session, expired, concurrent, wrong operation, disabled account hoặc IdP assurance thấp. Cần test negative trước triển khai production.

## 14. Ma trận kiểm thử step-up

| Test case | Kỳ vọng |
| --- | --- |
| User đã login, truy cập trang thông thường | Theo quyền cơ bản, không ép step-up nếu không cần |
| User đã login nhưng chưa có factor bổ sung, vào endpoint nhạy cảm | Chuyển sang challenge hoặc từ chối theo kiểu API |
| Có password + factor hợp lệ theo route Spring Security 7 | Đạt điều kiện factor, vẫn phải đạt role/business permission |
| User thiếu `ROLE_ADMIN` nhưng đã làm MFA | Không thể truy cập admin API |
| Proof đã hết hạn đúng mốc `now == expiresAt` | Từ chối |
| Proof mới nhưng account hoặc session không khớp | Từ chối, không cấp quyền cho phiên khác |
| Proof cho chuyển khoản A dùng với chuyển khoản B | Từ chối transaction binding |
| Thay người nhận hoặc số tiền sau challenge | Từ chối hoặc yêu cầu challenge mới |
| Replay cùng proof sau thành công | Từ chối, không chạy lại business action |
| 12 request cùng approval trong một JVM | Tối đa một được claim |
| Request confirm từ nhiều node cùng DB | Tối đa một commit theo shared-store concurrency policy |
| Factor vừa bị disable hoặc account locked | Proof cũ bị revoke/từ chối theo policy |
| Login SSO đã qua 8 giờ, IdP có cookie còn hiệu lực | Không tự coi đó là step-up mới |
| OIDC callback thiếu assurance hoặc `auth_time` quá cũ | Từ chối theo IdP trust contract |
| Authorization code/state/nonce sai | Từ chối ở OIDC callback, không phát proof |
| CSRF vào endpoint xác nhận giao dịch | Từ chối theo CSRF policy |
| DB gặp lỗi khi claim proof | Fail closed; không thực hiện action |
| Commit thành công nhưng HTTP response mất | Retry không thực hiện thêm lần nữa nhờ idempotency |
| User cần recovery vì mất authenticator | Quy trình recovery riêng, không bypass quyền cao âm thầm |

### Nên kiểm thử ở đâu?

**Unit test:** policy tính độ mới, so khớp action, session, account, trạng thái, và logic concurrency thuần Java như `StepUpDecisionDemo`.

**Integration test:** Spring Security filter chain + form/OIDC/WebAuthn/OTT thật, csrf, session rotation, request matchers, authorization failure.

**Database concurrency test:** nhiều request/process cùng claim một approval, dùng chính PostgreSQL/Redis config production; kiểm tra số row/update/business effects.

**End-to-end test:** browser hiển thị đúng action, user xác thực đúng yếu tố, IdP bảo đảm `acr`/`amr`/`auth_time` theo hợp đồng, application ghi đúng giao dịch và audit; test cả nhiều tab, timeout, rollback.

## 15. Giám sát, audit và recovery

Vì step-up bảo vệ ranh giới nhạy cảm, cần theo dõi:

- Số yêu cầu step-up theo action/risk level, tỷ lệ thành công/thất bại/hủy.
- Phương pháp factor thực sự được xác minh, `verifiedAt`, thời gian từ challenge đến confirmation (không log credential).
- Tỷ lệ proof hết hạn, reuse/replay, wrong-action hoặc session mismatch.
- Thay đổi MFA methods, khôi phục tài khoản, disable factor, đổi email/mật khẩu.
- Số lần giao dịch business commit thành công, idempotency retry và outbox failure.
- Sự cố xác thực IdP, WebAuthn provider, DB hoặc rate limiting.

Audit phải gắn accountId, operationId, factorMethod, request correlationId, time và result. Giữ danh tính/PII trong mức tối thiểu, che raw token, mã OTP, cookie và secrets, đặt retention và quyền truy cập phù hợp.

**Recovery là đường tấn công quan trọng:** nếu người dùng mất passkey, phải có quy trình phục hồi an toàn, được kiểm toán, tránh cho phép recovery bằng một yếu tố yếu hơn mà bỏ qua mọi ràng buộc của hành động nhạy cảm. Recovery codes phải được bảo quản và tiêu thụ một lần theo policy.

## 16. Checklist cuối trước khi đưa vào hệ thống

1. Đã phân loại endpoint/action nào nhạy cảm và cần assurance nào chưa?
2. Có phân biệt **authentication**, **authorization**, **step-up** và **transaction approval** không?
3. Yếu tố mới được kiểm chứng bởi provider server-side, hay chỉ do client tự báo?
4. Nếu cần MFA thật sự, các yếu tố có độc lập và phù hợp threat model không?
5. Bằng chứng có `verifiedAt`, TTL, userId, sessionId, actionId/hash, trạng thái chưa sử dụng không?
6. Độ mới có được kiểm tra ở **mỗi quyết định nhạy cảm** bằng thời gian server/DB đáng tin không?
7. Role, account state, tenant, ownership và hạn mức nghiệp vụ có được kiểm tra lại không?
8. Có ngăn thay đổi số tiền/người nhận sau xác nhận không?
9. Có atomic consume + transaction/idempotency giữa các node không?
10. CSRF, state/nonce OIDC, session fixation, cookie attributes và HTTPS đã được test chưa?
11. Logout, đổi password, disable factor, revoke account có vô hiệu hóa proof cần thiết không?
12. Các phương án SSO, WebFlux, stateless API có dùng đúng giao thức/DSL theo phiên bản không?
13. Test có bao gồm wrong account/session/action, expiry boundary, 12 request đồng thời và lost response không?
14. User có được hiển thị rõ giao dịch mình đang phê duyệt và có recovery path an toàn không?

### Tài liệu tham khảo

- Spring Security 7.0 — Multi-Factor Authentication (`FactorGrantedAuthority`, selective MFA, `validDuration`): https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html
- Spring Security 7.0 API — `FactorGrantedAuthority`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html
- Spring Security 7.0 API — `EnableMultiFactorAuthentication`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html
- Spring Security — Authentication Persistence & Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — One-Time Token Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html
- OWASP — Authentication Cheat Sheet, re-authentication cho tính năng nhạy cảm: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Multifactor Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- NIST SP 800-63B-4 — Session Management và Reauthentication: https://pages.nist.gov/800-63-4/sp800-63b/session/

**Kết luận:** thao tác nhạy cảm phải chứng minh **đúng account, đúng quyền, đúng yếu tố, đủ mới, đúng phiên và đúng hành động**. Spring Security 7.x có thể kiểm tra factor authorities và valid duration ở mức authorization, nhưng transaction binding, one-time approval, quyền nghiệp vụ và idempotency vẫn cần được thiết kế rõ ở tầng ứng dụng và storage.
