# Xác thực nhiều yếu tố và theo dõi mức xác thực đã đạt được trong Spring Security Servlet

## 1. Bài toán: đăng nhập thành công chưa chắc đủ để thực hiện mọi thao tác

Một ứng dụng web dùng **Spring Security Servlet** có thể có nhiều mức rủi ro. Người dùng đã đăng nhập bằng mật khẩu và được phép xem trang cá nhân, nhưng khi chuyển tiền, thay đổi email khôi phục hoặc thêm khóa API, ứng dụng cần **xác thực bổ sung (step-up authentication)**. Sau khi người dùng chứng minh yếu tố thứ hai, hệ thống phải biết **đã xác thực những yếu tố nào, vào lúc nào, cho danh tính nào, trong phiên nào**, để chỉ cấp quyền phù hợp trong một khoảng thời gian hữu hạn.

**Multi-factor authentication (MFA)** là việc chứng minh danh tính bằng **từ hai yếu tố thuộc các nhóm độc lập**. Những nhóm thường gặp:

| Nhóm yếu tố | Ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| Something you know — điều bạn biết | Mật khẩu, PIN độc lập | Hai mật khẩu không tự trở thành hai nhóm yếu tố |
| Something you have — điều bạn sở hữu | Security key FIDO2, thiết bị lưu passkey, ứng dụng tạo TOTP | TOTP thường gắn với một secret trên thiết bị; email OTP có đặc tính và rủi ro khác |
| Something you are — đặc tính sinh trắc | Vân tay, khuôn mặt khi được dùng trong cơ chế xác thực phù hợp | Sinh trắc cục bộ của passkey thường xác minh người dùng trước khi thiết bị ký challenge; server không nhất thiết nhận dữ liệu sinh trắc |

**MFA khác với chỉ thêm một màn hình.** Nếu bước hai chỉ hỏi một câu bí mật đã lưu cùng mật khẩu, hoặc OTP có thể nhận bằng chính tài khoản email vừa bị chiếm, mức độc lập có thể thấp. Cũng không nên đồng nhất “OTP” với “chống phishing”: **TOTP và SMS OTP dễ bị lừa nhập vào website giả; WebAuthn/FIDO2 với origin binding thường chống phishing tốt hơn** khi cấu hình đúng.

**Xác thực (authentication)** trả lời “ai/điều gì đã được chứng minh?”. **Ủy quyền (authorization)** trả lời “được làm gì?”. MFA tăng mức tin cậy của authentication, nhưng không thay thế quyền theo vai trò, theo tài nguyên, kiểm tra chủ sở hữu, chống CSRF, phòng XSS hay giám sát bất thường.

Ví dụ về policy có thể thiết kế:

- `GET /profile`: cần một phiên đăng nhập thông thường.
- `POST /payments`: cần phiên đã đăng nhập **và** chứng cứ MFA được xác nhận gần đây, đồng thời người dùng có quyền thanh toán.
- `POST /security/disable-mfa`: cần phương thức xác thực mạnh và quy trình khôi phục riêng; tuyệt đối không tự tắt MFA chỉ vì có cookie phiên.
- `GET /admin/audit`: ngoài MFA có thể đòi vai trò admin, device compliance và chính sách thời gian.

Đích của bài này là hiểu cơ chế **theo dõi mức xác thực đã đạt được (authentication assurance)** trong ngữ cảnh Spring Security Servlet và cách dùng trạng thái đó cho step-up đúng ranh giới tin cậy.

## 2. Phân biệt “đã đăng nhập”, “đã có MFA” và “MFA còn đủ mới”

Một phiên có thể trải qua nhiều trạng thái:

~~~text
Chưa xác thực
    │
    └─ Mật khẩu/passkey/SSO thành công
              ▼
     Đã xác thực bước đầu
     (chỉ vào được tài nguyên rủi ro thấp)
              │
              ├─ Người dùng chọn thao tác nhạy cảm
              ▼
     Yêu cầu xác thực bổ sung
              │
              ├─ Chứng minh yếu tố hợp lệ → ghi nhận bằng chứng
              ▼
      Đã đạt yêu cầu step-up
      (được phép tiếp tục nếu còn đủ quyền)
              │
              ├─ Hết thời hạn step-up
              ├─ Đổi tài khoản / đăng nhập mới
              ├─ Thu hồi yếu tố / nghi ngờ bị xâm nhập
              └─ Logout hoặc hủy session
              ▼
     Trở về mức chưa đạt step-up
~~~

Hai mốc thời gian phải tách biệt:

1. **Tuổi của session**: phiên có thể tồn tại 8 giờ để người dùng xem thông tin thông thường.
2. **Độ mới của bằng chứng MFA**: policy chuyển tiền có thể chỉ chấp nhận yếu tố thứ hai được xác minh trong **10 phút gần nhất**. Con số là ví dụ chính sách, không phải mặc định bắt buộc của Spring Security.

Nếu bước hai đã thành công lúc 09:00 và người dùng chuyển tiền lúc 09:05, có thể đủ mới; tới 10:00 thì phải step-up lại dù session vẫn đăng nhập. Mức độ này gọi là **reauthentication freshness**. Đôi khi rủi ro cao yêu cầu xác thực lại toàn bộ hoặc phê duyệt theo chính transaction, không chỉ “MFA gần đây”.

Một access token có claim `amr`/`acr` hay một `Authentication` có authority cho yếu tố nào đó **không tự động** bảo đảm tất cả policy trên; phải biết ai phát hành, khi nào xác thực, token còn giá trị hay không và policy đích mong đợi điều gì.

## 3. Mô hình hóa bằng chứng xác thực (authentication assurance evidence)

Một bản ghi server-side có thể chứa:

| Trường | Mục đích |
| --- | --- |
| `subjectId` | Định danh ổn định của tài khoản đã xác thực (không tin vào username do request gửi) |
| `loginEventId` | ID ngẫu nhiên của lần đăng nhập chính; giúp chống tái dùng MFA của lần login trước |
| `factorId` / `factorType` | Yếu tố đã xác minh, ví dụ TOTP hoặc WebAuthn; không lưu mã OTP |
| `verifiedAt` | Thời điểm server xác minh thành công yếu tố |
| `expiresAt` hoặc TTL theo policy | Khi nào chứng cứ không còn đủ mới |
| `context` (nếu cần) | Phạm vi thao tác, transaction, mức rủi ro hoặc phương thức đã dùng |
| `assurancePolicyVersion` (nếu cần) | Cho phép thu hồi/đánh giá lại khi chính sách thay đổi |

**Nguồn sự thật phải do server thiết lập**, không lấy từ body, query parameter, header tùy ý, localStorage, cookie có thể sửa hoặc claim JWT chưa được xác minh. Ví dụ client gửi `mfa=true` chỉ là dữ liệu không đáng tin.

Cần phân biệt:

- **Factor đã đăng ký (enrolled)**: tài khoản có TOTP secret hoặc passkey.
- **Factor đã xác minh trong lần đăng nhập này**: người dùng thực sự hoàn thành bước thách thức.
- **Factor đã xác minh gần đây**: bằng chứng còn trong cửa sổ thời gian của hành động.
- **Mức bảo đảm đạt được**: policy kết hợp loại yếu tố, số lượng, độ độc lập, độ mới, nguồn xác thực, risk context, khả năng chống phishing.

Không suy ra “đã đạt MFA” chỉ vì user có trường `mfaEnabled=true` trong database, cũng không dựa vào việc một endpoint `/mfa/verify` từng trả HTTP 200 cho một browser khác.

### Những ranh giới dễ mắc lỗi

- **Cùng user nhưng lần login khác**: token/session mới không được kế thừa dấu MFA từ phiên cũ chỉ nhờ cùng username.
- **Đổi tài khoản trong cùng browser**: dấu MFA của Alice không hợp lệ cho Bob.
- **Đăng nhập bằng remember-me**: cookie remember-me có thể không cung cấp mức bằng chứng tương đương mật khẩu vừa nhập; nhiều thao tác cần `fullyAuthenticated` hoặc xác thực lại.
- **Đổi mật khẩu, reset MFA, thay recovery factor**: cân nhắc thu hồi các session/step-up evidence cũ.
- **Cluster nhiều node**: nếu server lưu session phân tán, bằng chứng phải được xử lý nhất quán, có TTL và thu hồi; không dựa vào biến static của một JVM.

## 4. Spring Security Servlet nhìn mức xác thực ở đâu?

Trong Spring Security, request đi qua filter chain, tải `SecurityContext` từ nơi lưu phù hợp và đưa `Authentication` vào `SecurityContextHolder`. `Authentication` có principal, authorities và thông tin phương thức xác thực mà provider cấp. **Đã có `Authentication.isAuthenticated() == true` không đồng nghĩa đã đạt mọi yếu tố MFA**.

Các cách thể hiện assurance có thể khác nhau giữa phiên bản và kiến trúc:

1. **Factor authorities / cơ chế MFA tích hợp của phiên bản Spring Security đang dùng**: phiên bản có hỗ trợ có thể đánh dấu những yếu tố đã được chứng minh và áp quy tắc đòi nhiều yếu tố bằng authorization. Chỉ gán authority của một yếu tố **sau khi verifier phía server thành công**, không cho client tự thêm. Hãy kiểm tra tài liệu và API chính xác của phiên bản triển khai.
2. **Server-side session evidence + AuthorizationManager**: ứng dụng Servlet tự lưu bằng chứng có ràng buộc phiên/login, rồi yêu cầu chứng cứ khi route nhạy cảm được truy cập. Ví dụ học tập bên dưới minh họa lựa chọn này với các API Spring Security 6.x.
3. **OIDC/OAuth2 ngoại vi**: IdP có thể truyền `acr` (authentication context class reference), `amr` (authentication methods references) và `auth_time` trong token phù hợp. Resource server/client chỉ dùng các claim này khi **đã xác minh token, issuer, audience, freshness, trust contract và ý nghĩa claim của IdP**. Không tin claim tự tạo ở frontend.

**Quan trọng:** nếu chỉ có form login chuẩn, Spring Security có thể xác thực và coi request là authenticated sau mật khẩu. Khi ứng dụng yêu cầu MFA ở route nhạy cảm, phải thêm **authorization rule riêng** để chặn trước khi bước hai hoàn tất. Trạng thái “chưa đạt MFA” không phải lý do để bỏ qua kiểm tra quyền hoặc cho phép bypass các route API trực tiếp.

### Đặt step-up ở đâu?

Với URL, dùng `authorizeHttpRequests(...)` và một `AuthorizationManager<RequestAuthorizationContext>` hoặc biểu thức access phù hợp. Với business operation, bổ sung method-level authorization (ví dụ `@PreAuthorize` hoặc service check) nếu cùng hành động có nhiều đường vào như controller, message consumer và scheduled job.

**Không chỉ bảo vệ nút bấm trên frontend.** Client có thể gọi API trực tiếp. **Không chỉ kiểm tra trong controller rồi quên service** nếu có RPC/job khác gọi cùng chức năng. Policy phải được áp tại boundary đúng với kiến trúc.

## 5. Mẫu triển khai step-up có quản lý session trong Spring Boot 3 / Security 6

Mẫu sau dành cho **Java 17+, Spring Boot 3.x, Spring Security Servlet (Spring MVC + session/form login)**. Nó minh họa dấu xác thực **phía server** và truy cập theo độ mới của MFA, **không tự triển khai thuật toán TOTP hay FIDO2**. Để sản xuất thực tế, phải tích hợp bộ xác minh yếu tố thứ hai đạt yêu cầu an toàn, rate limit và lưu trữ credential an toàn.

Dependency Gradle tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 5.1. Bằng chứng server-side gắn với lần login

File `MfaAssuranceService.java`, package `com.example.demo.security`. Ứng dụng lưu cả **sự kiện xác thực chính** và **sự kiện xác minh MFA** vào session. Đây là cơ chế mẫu cho ứng dụng dùng session; không dùng trong stateless API mà không thay đổi kiến trúc.

~~~java
package com.example.demo.security;

import java.io.Serializable;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class MfaAssuranceService {

    private static final String PRIMARY_KEY =
        MfaAssuranceService.class.getName() + ".PRIMARY";
    private static final String MFA_KEY =
        MfaAssuranceService.class.getName() + ".MFA";
    private static final Duration MAX_AGE = Duration.ofMinutes(10);

    public record PrimaryEvent(String subject, String loginId)
            implements Serializable {}

    public record MfaEvidence(String subject, String loginId,
                              String factor, Instant verifiedAt)
            implements Serializable {}

    private static boolean hasStrongPrimary(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !(auth instanceof AnonymousAuthenticationToken)
            && !(auth instanceof RememberMeAuthenticationToken);
    }

    // Chỉ gọi sau khi xác thực bước đầu thành công ở server.
    public void onPrimarySuccess(HttpServletRequest request,
                                 Authentication auth) {
        if (!hasStrongPrimary(auth)) {
            throw new IllegalStateException("Primary auth required");
        }
        HttpSession session = request.getSession(true);
        session.removeAttribute(MFA_KEY);
        session.setAttribute(PRIMARY_KEY,
            new PrimaryEvent(auth.getName(),
                             UUID.randomUUID().toString()));
    }

    // Chỉ gọi sau khi verifier thứ hai thực sự thành công.
    public void recordFactor(HttpServletRequest request,
                             Authentication auth, String factor) {
        if (!hasStrongPrimary(auth)
            || !Set.of("totp", "webauthn").contains(factor)) {
            throw new IllegalStateException("Invalid MFA context");
        }

        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new IllegalStateException("No login session");
        }
        Object primary = session.getAttribute(PRIMARY_KEY);
        if (!(primary instanceof PrimaryEvent login)
            || !login.subject().equals(auth.getName())) {
            throw new IllegalStateException("Login event mismatch");
        }

        session.setAttribute(MFA_KEY,
            new MfaEvidence(login.subject(), login.loginId(),
                            factor, Instant.now()));
    }

    public boolean hasRecentMfa(HttpServletRequest request,
                                Authentication auth) {
        if (!hasStrongPrimary(auth)) {
            return false;
        }
        HttpSession session = request.getSession(false);
        if (session == null) {
            return false;
        }
        Object primary = session.getAttribute(PRIMARY_KEY);
        Object mfa = session.getAttribute(MFA_KEY);
        if (!(primary instanceof PrimaryEvent login)
            || !(mfa instanceof MfaEvidence proof)) {
            return false;
        }

        Instant now = Instant.now();
        Duration age = Duration.between(proof.verifiedAt(), now);
        return login.subject().equals(auth.getName())
            && proof.subject().equals(login.subject())
            && proof.loginId().equals(login.loginId())
            && !age.isNegative()
            && age.compareTo(MAX_AGE) < 0;
    }
}
~~~

**Những tính chất được minh họa:**

- `onPrimarySuccess(...)` xóa evidence MFA cũ **mỗi khi mật khẩu được xác thực thành công** và sinh `loginId` mới; không cho cùng user tái sử dụng MFA của login trước chỉ vì session còn thuộc tính cũ.
- `recordFactor(...)` không nhận identity từ body. Nó dùng `Authentication` của server và yêu cầu có primary event cùng user trong session. `factor` không lấy tùy ý từ request; caller nội bộ chỉ truyền tên yếu tố mà verifier vừa kiểm thành công.
- `hasRecentMfa(...)` yêu cầu **cùng subject, cùng loginId, còn trong 10 phút**, không ở tương lai, và primary authentication không phải anonymous/remember-me.
- Bản ghi chỉ chứa **loại yếu tố và timestamp**, không lưu TOTP code, TOTP secret, WebAuthn private key hoặc access token.

**Giới hạn cần bổ sung ở production:** dùng **user ID bất biến** thay vì `auth.getName()` nếu tên đăng nhập có thể đổi; lưu proof với policy version và ngữ cảnh thao tác khi cần; đánh dấu thu hồi khi reset/disable MFA; test cả các luồng OAuth2 Login, SSO, password change hoặc custom authentication vì handler ví dụ ở mục sau chỉ xử lý `formLogin`. Session không tự chứng minh thiết bị an toàn hoặc chống XSS/cookie theft.

### 5.2. SecurityFilterChain yêu cầu MFA cho URL nhạy cảm

File `SecurityConfig.java` trong cùng package:

~~~java
package com.example.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, MfaAssuranceService assurance)
            throws Exception {

        SavedRequestAwareAuthenticationSuccessHandler next =
            new SavedRequestAwareAuthenticationSuccessHandler();

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error", "/login").permitAll()
                .requestMatchers("/mfa/**").fullyAuthenticated()
                .requestMatchers("/sensitive/**").access(
                    (authentication, context) ->
                        new AuthorizationDecision(
                            assurance.hasRecentMfa(
                                context.getRequest(),
                                authentication.get())))
                .anyRequest().authenticated())
            .formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    assurance.onPrimarySuccess(request, authentication);
                    next.onAuthenticationSuccess(
                        request, response, authentication);
                }))
            .logout(logout -> logout.invalidateHttpSession(true));

        return http.build();
    }
}
~~~

Đây là class trong dự án Spring, **không phải chương trình JDK độc lập**. Các URI là ví dụ: `/sensitive/**` phải được điều chỉnh theo API nhạy cảm thật.

Luồng kiểm soát:

1. Sau form login, Spring Security xác thực mật khẩu và tạo SecurityContext. Success handler xóa MFA cũ, gán primary login event rồi chuyển tiếp qua handler thông thường của form login.
2. `/mfa/**` chỉ dành cho user xác thực đầy đủ, **không tính remember-me**; nếu chưa có session xác thực, hệ thống yêu cầu đăng nhập trước. Nếu dùng ứng dụng khác hoặc cơ chế khác, cấu hình access tương đương.
3. Mọi request vào `/sensitive/**` chỉ qua khi server xác minh gần đây có đúng chứng cứ MFA; route khác vẫn cần đăng nhập.
4. `AuthorizationDecision(false)` ở URL nhạy cảm thường trở thành **403** cho user đã đăng nhập. Frontend có thể hướng tới màn hình step-up theo hợp đồng ứng dụng, thay vì coi đây là lỗi hệ thống. Không nên tạo vòng lặp redirect MFA.
5. Chính sách business như `hasAuthority("PAYMENT_WRITE")` vẫn cần được kết hợp với MFA, ví dụ dùng method-level authorization hoặc manager kết hợp; **chỉ có MFA không chứng minh user được phép thực hiện hành động**.
6. Đây là mẫu **form login**; nếu hệ thống hỗ trợ OAuth2 Login, SAML hoặc custom AuthenticationProvider, phải gắn hook làm mới primary event cho **mọi** lần đăng nhập và thay đổi principal. Nếu không, dấu MFA có thể cũ hoặc request hợp lệ bị chặn.

**CSRF vẫn bật mặc định.** Đừng gọi `csrf().disable()` chỉ vì thêm bước MFA: browser dùng session cookie sẽ tự gửi cookie tới server trong nhiều bối cảnh, nên endpoint POST cập nhật trạng thái cũng cần CSRF protection.

### 5.3. Xác minh yếu tố thứ hai rồi ghi nhận mức mới

Ví dụ contract phía server cho TOTP:

~~~java
package com.example.demo.security;

public interface TotpVerifier {
    // Trả true chỉ sau khi kiểm tra mã hợp lệ và chưa được dùng lại.
    // Implementation thật cần lưu secret an toàn, rate limit và
    // chống replay theo bước thời gian.
    boolean verifyAndConsume(String subject, String code);
}
~~~

Đây là interface cho **implementation xác minh TOTP thực tế**, không phải một verifier có thể chạy độc lập. Ứng dụng phải cung cấp bean triển khai an toàn; không “demo” bằng cách trả `true` cho mọi mã, hardcode `123456` hoặc kiểm tra giá trị từ client mà không có secret phía server.

Controller nhận POST và gọi verifier; chỉ sau khi xác minh thành công mới nâng trạng thái:

~~~java
package com.example.demo.security;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class MfaController {

    private final TotpVerifier verifier;
    private final MfaAssuranceService assurance;

    public MfaController(TotpVerifier verifier,
                         MfaAssuranceService assurance) {
        this.verifier = verifier;
        this.assurance = assurance;
    }

    @PostMapping("/mfa/verify")
    public ResponseEntity<Void> verify(
            @RequestParam("code") String code,
            Authentication authentication,
            HttpServletRequest request) {

        if (code == null || !code.matches("[0-9]{6,8}")
            || !verifier.verifyAndConsume(
                authentication.getName(), code)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Verification failed");
        }

        // Sau khi MFA thành công, đổi session ID nếu đã có session.
        // Đây là lớp phòng vệ bổ sung; vẫn cần bảo vệ session cookie.
        request.changeSessionId();
        assurance.recordFactor(request, authentication, "totp");
        return ResponseEntity.noContent().build();
    }
}
~~~

Ở hệ thống thật, `TotpVerifier` phải có giới hạn số lần thử, chống dùng lại cùng mã trong cùng cửa sổ thời gian, đồng hồ được đồng bộ và secret được bảo vệ. Code có thể hợp lệ theo ± một bước đồng hồ nhưng verifier phải **không chấp nhận lặp** nếu policy không cho phép; áp rate limit theo user, IP/risk signal và từng thiết bị phù hợp. Mã lỗi công khai nên chung chung; log không chứa code.

Vì request sử dụng form body, request hợp lệ có thể có header `Content-Type: application/x-www-form-urlencoded` và CSRF token theo cơ chế Spring Security. **Client không được gán trực tiếp cờ MFA** bằng request tới một endpoint “markSuccess”. Chỉ controller tin cậy mới gọi `recordFactor(...)` sau khi verifier thành công.

Trong mô hình có nhiều loại yếu tố, WebAuthn verifier phải xác minh **challenge, origin, RP ID, chữ ký, credential public key, user verification khi policy yêu cầu và cơ chế chống replay** trước khi đánh dấu `"webauthn"`. Không gán nhãn WebAuthn chỉ vì trình duyệt gửi chuỗi `factor=webauthn`.

### 5.4. Tại sao không chỉ thêm ROLE_MFA vào UserDetails?

`ROLE_MFA` nằm cố định trong database account có thể phản ánh **đã đăng ký MFA**, nhưng không chứng minh **lần login hiện tại** đã qua yếu tố thứ hai. Nếu role được gắn sẵn ngay sau mật khẩu, user có thể được vào route nhạy cảm mà không làm step-up.

Nếu chọn mô hình factor authorities trong Spring Security, chỉ ghi authority sau **chứng cứ thật**, bảo đảm authority bị xóa/đánh giá lại khi hết hạn, logout, đổi principal, thu hồi credential và áp đúng policy. Nếu dùng session evidence như ví dụ, authority không cần bị sửa sau mỗi lần step-up; `AuthorizationManager` kiểm tra evidence tại request time.

## 6. Một ví dụ Java 17 thuần về độ mới và các yếu tố độc lập

Ví dụ này **chạy được với JDK 17+ mà không cần Spring** để học quy tắc: *đã có hai loại yếu tố không đồng nghĩa luôn đủ mới*. Nó **không thực hiện xác thực** và không thể thay verifier trên server.

File `AssuranceDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.EnumSet;
import java.util.Set;

public class AssuranceDemo {
    enum Factor { PASSWORD, TOTP, WEBAUTHN }

    record Evidence(String user, Set<Factor> factors,
                    Instant lastStepUp) {
        boolean meetsPolicy(String currentUser, Instant now) {
            Duration age = Duration.between(lastStepUp, now);
            return user.equals(currentUser)
                && factors.contains(Factor.PASSWORD)
                && (factors.contains(Factor.TOTP)
                    || factors.contains(Factor.WEBAUTHN))
                && !age.isNegative()
                && age.compareTo(Duration.ofMinutes(10)) < 0;
        }
    }

    public static void main(String[] args) {
        Instant t = Instant.parse("2026-01-01T12:00:00Z");

        Evidence onlyPassword = new Evidence(
            "alice", EnumSet.of(Factor.PASSWORD), t);
        Evidence twoFactors = new Evidence(
            "alice",
            EnumSet.of(Factor.PASSWORD, Factor.TOTP), t);

        System.out.println(
            onlyPassword.meetsPolicy("alice", t.plusSeconds(30)));
        System.out.println(
            twoFactors.meetsPolicy("alice", t.plusSeconds(30)));
        System.out.println(
            twoFactors.meetsPolicy("alice", t.plusSeconds(601)));
        System.out.println(
            twoFactors.meetsPolicy("bob", t.plusSeconds(30)));
    }
}
~~~

Chạy:

~~~bash
javac AssuranceDemo.java
java AssuranceDemo
~~~

Stdout **chính xác**:

~~~text
false
true
false
false
~~~

Dòng thứ nhất thiếu yếu tố độc lập; dòng thứ hai có mật khẩu + TOTP và còn mới; dòng thứ ba quá 10 phút; dòng thứ tư không cùng người dùng. Trong production còn cần bind bằng chứng với **login event, session, issuer/trust context, policy và việc factor thực sự đã được xác minh**, như cấu hình mẫu ở mục 5.

## 7. Những yếu tố MFA thường dùng và cách xử lý an toàn

### 7.1. TOTP

TOTP (Time-based One-Time Password) thường tạo mã ngắn từ secret và bước thời gian. Một implementation đúng cần:

- Secret ngẫu nhiên riêng cho mỗi user/thiết bị, cấp qua quy trình enrollment có xác thực mạnh và xác nhận thành công trước khi bật.
- Secret được bảo vệ ở server (mã hóa, giới hạn quyền), không log QR provisioning URI hoặc secret.
- Thuật toán TOTP chuẩn và đồng hồ đồng bộ; chỉ chấp nhận cửa sổ lệch thời gian nhỏ khi policy cho phép.
- **Chống brute force và replay**: số lần thử hữu hạn, chống việc dùng lại mã đã tiêu thụ; kiểm soát cạnh tranh khi hai request gửi cùng mã.
- Quy trình reset/khôi phục an toàn, thu hồi enrollment khi đổi thiết bị, cảnh báo khi thay factor.
- Không để attacker đăng ký yếu tố của họ sau khi chỉ chiếm session mức thấp.

TOTP là thêm yếu tố sở hữu secret nhưng **không chống phishing hoàn toàn**. Một website giả có thể lấy mã trong thời gian còn hiệu lực và dùng ngay; vì vậy giao dịch có rủi ro cao có thể cần WebAuthn hoặc phê duyệt ràng buộc giao dịch.

### 7.2. WebAuthn/FIDO2 và passkey

WebAuthn sử dụng cơ chế khóa công khai, thử thách và ràng buộc với **relying party ID/origin**. Khi phù hợp và cấu hình đúng, yếu tố này giảm rủi ro phishing so với mã OTP nhập tay. Một phương thức passkey có thể đáp ứng xác thực mạnh với user verification; không tự suy ra “hai yếu tố” chỉ từ việc hiện hộp thoại sinh trắc.

Cần kiểm tra registration/assertion, challenge một lần, origin, RP ID, chữ ký, credential ID, trạng thái credential, user verification theo policy và bảo vệ dữ liệu người dùng. **Không tự chấp nhận “webauthn_success=true” từ frontend.** Tình trạng đồng bộ passkey, dùng chung thiết bị, recovery và threat model ảnh hưởng mức assurance thực tế.

Nếu xác thực chính đã dùng một passkey mạnh với user verification, policy có thể coi là đủ mức cho một số hành động mà **không** cần mật khẩu + TOTP; đó là lựa chọn assurance theo chuẩn và risk assessment, không phải công thức cứng “hai màn hình = MFA”.

### 7.3. SMS, email OTP và recovery codes

SMS OTP chịu rủi ro SIM swap, chuyển số, intercept và phishing; email OTP phụ thuộc bảo mật mailbox và có thể không độc lập với primary login. Không gắn nhãn mọi phương thức OTP là đạt cùng mức tin cậy.

**Recovery codes** cần được tạo bằng bộ sinh ngẫu nhiên an toàn, cho tải/lưu một lần, lưu hash/biện pháp bảo vệ phù hợp và tiêu thụ một lần; chúng là **cơ chế khôi phục** có thể yếu hơn phương thức MFA thông thường. Sau khi dùng recovery, có thể áp quy trình xác minh bổ sung, cảnh báo và yêu cầu đăng ký lại yếu tố.

Không biến “lost MFA device” thành câu hỏi bí mật dễ đoán hoặc link email không kiểm soát. Đổi/đặt lại MFA cần chống account takeover; có thể yêu cầu waiting period, cảnh báo đa kênh, hỗ trợ xác minh danh tính và thu hồi sessions theo rủi ro.

## 8. Xác thực nhiều yếu tố trong OIDC và bên ngoài ứng dụng

Trong hệ thống có **Identity Provider** chịu trách nhiệm MFA (OIDC, SAML...), ứng dụng Servlet có thể không tự triển khai TOTP/WebAuthn. Thay vào đó cần đọc kết quả từ provider **đáng tin**, theo hợp đồng xác thực.

OIDC có các claim thường thấy:

- `amr`: danh sách phương thức xác thực được sử dụng, theo quy ước của provider.
- `acr`: lớp/ngữ cảnh đảm bảo mà provider đã xác nhận; **không phải thang điểm số phổ quát** có cùng nghĩa ở mọi IdP.
- `auth_time`: thời điểm authentication của end user theo token/context phù hợp; khác với `iat` (thời điểm token được phát hành).

**Không tin** vào JWT chưa kiểm chữ ký hoặc header do browser tự tạo như `X-AMR: mfa`. Khi nhận token, phải kiểm issuer, audience, expiry, nonce khi phù hợp, signature và hợp đồng `acr/amr/auth_time`. Nếu provider hỗ trợ step-up, client có thể gửi yêu cầu xác thực lại (ví dụ theo `max_age` hoặc `acr_values` theo hợp đồng IdP), nhưng **không tự giả định** mọi IdP sẽ bắt MFA hoặc trả cùng claim.

Một token được phát hành mới **không có nghĩa người dùng vừa thực hiện MFA**; `iat` mới có thể chỉ là refresh token exchange, trong khi `auth_time` cũ. Với resource server, cần phân biệt authentication context claim đã được kiểm tra và quyền nghiệp vụ cho endpoint.

Có thể tham chiếu các khái niệm **Authentication Assurance Level (AAL)** như AAL1/AAL2/AAL3 từ bộ tiêu chuẩn NIST khi tổ chức có yêu cầu compliance, nhưng **không ánh xạ máy móc** `password+OTP = AAL2` hoặc `passkey = AAL3`. Cần đáp ứng đầy đủ đặc tính authenticator, phishing resistance, verifier, lifecycle và yêu cầu của chuẩn đang áp dụng.

## 9. Khi nào yêu cầu step-up và phạm vi của bằng chứng

**Step-up theo route:** mọi request tới `/sensitive/**` đòi MFA còn mới. Đơn giản và dễ test nhưng có thể gây yêu cầu lại liên tục nếu TTL quá ngắn.

**Step-up theo hành động:** ví dụ thay tài khoản nhận tiền, xuất dữ liệu cá nhân, tắt bảo vệ tài khoản. Có thể yêu cầu MFA ngay trước action (transaction authorization), không cho một proof được tái sử dụng cho hàng loạt thao tác rủi ro cao.

**Step-up theo risk signal:** thiết bị lạ, IP bất thường, hành vi tốc độ cao, quyền admin, tài khoản có sự kiện khôi phục gần đây. Tuy nhiên không dựa hoàn toàn vào fingerprint/IP vì có thể thay đổi và bị giả mạo; policy cần chống gây phiền nhiễu và bảo vệ riêng tư.

**Action-bound approval** yêu cầu người dùng thấy đúng số tiền/người nhận/tác vụ và xác nhận dựa trên challenge gắn với transaction; một mã TOTP dùng chung không tự buộc vào nội dung giao dịch. Với hệ thống tài chính/nhạy cảm, cân nhắc phê duyệt mật mã gắn giao dịch, giới hạn số lần thử và cơ chế chống replay.

Việc đánh dấu MFA chỉ nên xảy ra **sau khi verifier trả thành công**, không phải ngay khi hiển thị QR code, người dùng nhấn “đã xác minh” hay gửi request chứa mã không hợp lệ.

## 10. Phòng các lỗi trạng thái MFA trong session

| Lỗi thiết kế | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lưu `mfa=true` trong localStorage hoặc cookie không ký | Client tự sửa để qua bước hai | Lưu evidence phía server hoặc token ký/kiểm chặt với ràng buộc phù hợp |
| Chỉ kiểm `mfaEnabled` trong DB | User mới nhập mật khẩu vẫn vào endpoint nhạy cảm | Phân biệt enrolled và verified trong phiên hiện hành |
| Bằng chứng MFA không có loginEventId | Có thể tái sử dụng dấu MFA sau đăng nhập khác trong cùng session | Reset sau mọi primary login, bind với login event |
| Giữ bằng chứng vô hạn theo thời lượng cookie | Step-up cũ vẫn cho phép hành động nhạy cảm | TTL/last verified, yêu cầu xác thực lại theo policy |
| Bỏ yêu cầu MFA khi request đến trực tiếp API | Bypass frontend/UX | Bảo vệ phía server bằng AuthorizationManager hoặc service |
| Đánh dấu MFA trước khi verifier hoàn tất | Cho phép sai yếu tố hoặc race condition | Chỉ ghi sau xác minh và consume challenge thành công |
| Không chống replay mã TOTP | Một mã bị lấy cắp dùng được nhiều lần trong cửa sổ thời gian | Theo dõi mã/timestep đã dùng, xử lý cạnh tranh và rate limiting |
| Tự coi remember-me là primary mới | Bỏ qua yêu cầu mật khẩu hiện thời | Yêu cầu fullyAuthenticated/reauthentication theo chính sách |
| MFA proof không gắn subject | Dấu MFA của Alice được dùng cho Bob | Bind subject + login + session |
| Dùng MFA thay cho `hasAuthority` | User thường có MFA vẫn thực hiện admin action | Kết hợp MFA với role/ACL/tenant checks |
| Chỉ đổi session ID khi primary login, không bảo vệ cookie | Session theft hoặc XSS vẫn có thể chiếm phiên | HTTPS, Secure/HttpOnly/SameSite, CSP và chống XSS/CSRF |
| Reset MFA qua email bị chiếm | Attacker bypass phương thức mạnh | Quy trình recovery nghiêm ngặt, thông báo và thu hồi phiên |
| Giấu policy nhưng trả lỗi quá chi tiết | Lộ tài khoản, yếu tố đã đăng ký, thời gian MFA | Thông báo đủ dùng, không lộ secret hay enumeration |

### Khi session bị mất hoặc bị thu hồi

Từ góc nhìn server, khi `HttpSession` không tồn tại, `PRIMARY_KEY` hoặc `MFA_KEY` không được phục hồi đáng tin, hoặc evidence khác user/login, mặc định **fail closed**: coi chưa đạt step-up. Ứng dụng có thể mời user xác thực lại; không tự tạo bằng chứng từ trạng thái cũ của frontend.

Nếu dùng `Spring Session` với Redis/JDBC, cần đảm bảo serialization/versioning, TTL, xóa session khi logout và đồng bộ quy tắc trong cluster. Tùy chỉnh reauthentication cho password reset, administrator revocation và factor reset cần đi qua mọi node chứ không chỉ cache cục bộ.

## 11. Kiểm thử và chẩn đoán

### 11.1. Ma trận acceptance test

| Điều kiện đầu vào | Đường đi | Kết quả mong đợi |
| --- | --- | --- |
| Chưa đăng nhập | `GET /sensitive/summary` | Bị yêu cầu xác thực, không trả dữ liệu |
| Đã nhập mật khẩu, chưa MFA | `GET /sensitive/summary` | Bị chặn/đòi step-up |
| Đã nhập mật khẩu, nhập TOTP sai | `POST /mfa/verify` | Lỗi chung, không ghi bằng chứng MFA |
| Đã nhập mật khẩu, mã TOTP đúng và chưa dùng | `POST /mfa/verify` | Xác minh thành công, lưu proof gắn login hiện tại |
| MFA vừa hoàn thành, user có quyền thao tác | `GET /sensitive/summary` | Được đi tiếp đến controller/service |
| MFA đã hết TTL | `GET /sensitive/summary` | Yêu cầu step-up lại |
| Login người dùng khác trong cùng browser | `GET /sensitive/summary` | Evidence cũ không hợp lệ |
| Logout hoặc session hết hạn | `GET /sensitive/summary` | Không dùng lại evidence cũ |
| Authentication qua remember-me | `GET /mfa/verify` hoặc sensitive route | Bị yêu cầu xác thực mạnh hơn theo policy |
| User không có quyền nghiệp vụ dù MFA thành công | `POST /sensitive/payment` | Vẫn bị từ chối theo business authorization |
| Gửi POST MFA không CSRF token khi dùng cookie | `POST /mfa/verify` | Bị CSRF protection chặn |
| Hai request dùng cùng OTP đồng thời | `POST /mfa/verify` | Verifier chỉ chấp nhận theo policy chống replay |

Không chỉ test HTTP 200/403. Kiểm tra **session evidence có thực sự được tạo/xóa**, TTL, quyền của tài nguyên, trạng thái session sau login và việc dấu MFA không vượt ranh giới user.

### 11.2. Unit test mô hình session và clock

Với mẫu `MfaAssuranceService`, unit test nên bao phủ:

1. `onPrimarySuccess` tạo `loginId` mới và xóa proof của login trước.
2. `recordFactor` từ chối khi không có primary event hoặc principal không khớp.
3. `hasRecentMfa` trả false khi session null, remember-me, subject khác, `loginId` khác, timestamp tương lai hoặc đã quá 10 phút.
4. Record factor chỉ được gọi sau mã TOTP/WebAuthn được verifier chấp nhận.
5. Khi có nhiều request đồng thời, verifier bảo đảm mã một lần không bị tiêu thụ hai lần.

Để test biên TTL ổn định, trong production nên inject `java.time.Clock` vào service và dùng `Clock.fixed(...)` trong test, thay vì phụ thuộc thời gian thực. Code mục 5 dùng `Instant.now()` cho dễ học; với ứng dụng phức tạp hãy tách đồng hồ và policy thành dependency.

### 11.3. MockMvc và integration test

Với Spring Security Test, có thể dùng `MockMvc` để kiểm tra route và CSRF. Ví dụ minh họa **đoạn trong test class đã thiết lập MockMvc, giả lập principal**:

~~~java
mvc.perform(post("/mfa/verify")
        .with(user("alice"))
        .param("code", "123456"))
    .andExpect(status().isForbidden()); // Không có CSRF token
~~~

Để dùng đoạn này trong test phải có static imports `MockMvcRequestBuilders.post`, `SecurityMockMvcRequestPostProcessors.user` và `MockMvcResultMatchers.status`, cùng `mvc` đã inject. Nếu ứng dụng dùng `@WebMvcTest` hoặc `@SpringBootTest @AutoConfigureMockMvc`, cần kiểm tra SecurityFilterChain thực sự được kích hoạt. `user("alice")` là helper tạo principal **giả trong test**, không chứng minh password hoặc MFA đã chạy. Mã `123456` chỉ là dữ liệu giả; không tạo xác thực thành công nếu verifier thật chưa chấp nhận.

Sau đó bổ sung test với `.with(csrf())`, mô phỏng verifier chấp nhận/từ chối, session giữ nguyên giữa các request, kiểm tra 403 trước step-up và kết quả phù hợp sau step-up. Với ứng dụng thật cần integration test qua trình duyệt, proxy, HTTPS, CSRF cookie/session và MFA provider thực tế.

### 11.4. Ghi log và thông báo lỗi

Log nên thể hiện **sự kiện** (bắt đầu step-up, thành công/thất bại, hết hạn, reset factor, revoke session) với subject ID đã bảo vệ, loại yếu tố, correlation ID, timestamp và policy ID. Không log TOTP code, QR secret, WebAuthn private key (không bao giờ ở server), recovery code, cookie phiên hay access token.

Với user cuối, thông báo hợp lý là “Cần xác thực bổ sung” hoặc “Không thể xác minh mã” mà không tiết lộ yếu tố đã đăng ký, mã đúng bao nhiêu chữ số nếu không cần hoặc trạng thái account nhạy cảm. Rate limiting, khóa tạm thời và hỗ trợ recovery cần tránh tạo kênh dò tài khoản.

## 12. Checklist thiết kế production

- [ ] Phân biệt clearly **đã đăng ký** yếu tố và **đã chứng minh** yếu tố trong lần login hiện tại.
- [ ] Chọn loại yếu tố đủ độc lập và đủ mạnh với nguy cơ của thao tác; ưu tiên phishing-resistant MFA khi phù hợp.
- [ ] Chỉ đánh dấu MFA sau khi backend verifier kiểm tra chính xác và chống replay.
- [ ] Evidence có **subject, loginEventId, loại yếu tố, thời điểm, TTL** và được kiểm tra server-side.
- [ ] Khi primary login mới, đổi account, logout, reset factor hoặc sự kiện thu hồi, evidence cũ không còn được chấp nhận.
- [ ] URL, service và thao tác nhạy cảm đều được bảo vệ tại server; MFA kết hợp với role/ACL/tenant authorization.
- [ ] Không cho remember-me hoặc session cũ tự động thỏa điều kiện reauthentication cao.
- [ ] Session cookie dùng HTTPS, Secure, HttpOnly, SameSite phù hợp; vẫn có CSRF protection và phòng XSS.
- [ ] TOTP/OTP có rate limiting, chống brute force/replay; WebAuthn kiểm tra origin/RP ID/challenge/signature.
- [ ] OIDC `acr/amr/auth_time` chỉ được tin sau xác minh và hợp đồng issuer; không nhầm token `iat` với MFA mới.
- [ ] Enrollment/recovery/reset/disable MFA có chính sách bảo mật riêng và cảnh báo người dùng.
- [ ] Test cả đường thành công, fail closed, expired evidence, session rotation, account switch, CSRF và proxy/cluster.
- [ ] Không log secret, recovery code, OTP, JWT/cookie hoặc bằng chứng nhạy cảm; dùng metrics/audit có giới hạn quyền.

**Kết luận:** “Đã xác thực” không phải một trạng thái nhị phân duy nhất cho mọi hành động. Spring Security Servlet có thể dùng authentication/factor authorities hoặc **bằng chứng MFA phía server gắn với sự kiện đăng nhập** để biết người dùng đã đạt mức xác thực nào và còn đủ mới hay không. Chỉ khi chứng cứ hợp lệ **và** quyền nghiệp vụ phù hợp, API nhạy cảm mới được phép chạy; chính sách phải fail closed khi bằng chứng thiếu, cũ hoặc bị thu hồi.
