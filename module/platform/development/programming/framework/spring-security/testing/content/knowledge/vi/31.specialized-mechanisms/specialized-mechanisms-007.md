# Nhiều yếu tố xác thực khi phiên bản và cấu hình cung cấp khả năng tương ứng

## 1. Bối cảnh và mục tiêu

Một ứng dụng quản trị cho phép người dùng đăng nhập bằng mật khẩu, nhưng yêu cầu **xác thực thêm một yếu tố** trước khi tải báo cáo nhạy cảm hoặc thay đổi tài khoản thanh toán. Bài kiểm thử chỉ dùng `@WithMockUser(roles = "ADMIN")` có thể trả `200 OK` vì principal được đặt sẵn. Điều đó **không chứng minh người dùng đã vượt qua thử thách MFA**.

Trong module `SPRING_SECURITY_TESTING`, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên Servlet và Reactive: `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và các ca được phép hoặc bị từ chối. Chủ đề thuộc chương **Cơ chế chuyên biệt**, nhấn mạnh việc kiểm thử nhiều yếu tố xác thực (*multi-factor authentication*, MFA) **chỉ khi phiên bản Spring Security, cấu hình và các cơ chế đăng nhập liên quan thực sự cung cấp khả năng ấy**.

Sau bài này, bạn có thể:

1. Phân biệt hai yếu tố độc lập với hai thao tác kiểm tra cùng một yếu tố.
2. Kiểm tra dự án có MFA tích hợp sẵn hay phải sử dụng cơ chế step-up được thiết kế riêng.
3. Phân biệt `authentication` của lần đăng nhập đầu với bằng chứng yếu tố bổ sung đã được xác minh.
4. Viết test cho chuỗi **đăng nhập → bị yêu cầu yếu tố bổ sung → xác minh → được phép → hết hạn/thu hồi**.
5. Dùng `MockMvc` hoặc `WebTestClient` kiểm tra request chứa credentials thực, không chỉ cấp authorities giả.
6. Thiết kế các ca chống replay, hết hạn, đổi phiên, sai danh tính và vượt giới hạn thử.
7. Đánh giá đúng giới hạn của OTP, WebAuthn/passkey, JWT/OIDC `amr`/`acr` và các phiên bản framework.

> **Phạm vi quan trọng:** Không có một API MFA chung mặc định cho mọi phiên bản Spring Security. Tên annotation, cấu hình yếu tố, authentication success handling và hỗ trợ Servlet/Reactive phụ thuộc **đúng phiên bản** và cơ chế authentication đã được cài đặt. Các đoạn code mô tả quy tắc ứng dụng bên dưới dùng API Servlet ổn định để minh họa cách kiểm thử; chúng **không** giả định dự án tự động có một annotation MFA cụ thể.

## 2. MFA thực sự là gì?

Thông thường, yếu tố xác thực thuộc các nhóm:

| Nhóm | Ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| **Điều người dùng biết** | Password, PIN | Password/PIN được kiểm tra bằng provider tin cậy |
| **Điều người dùng sở hữu** | Khóa bảo mật FIDO2, ứng dụng authenticator, thiết bị có khóa riêng | Đã xác minh được bằng chứng sở hữu phù hợp |
| **Đặc điểm người dùng** | Sinh trắc học do thiết bị xác thực thực hiện | Cơ chế xác minh đạt đúng yêu cầu; máy chủ không tự suy luận chỉ từ một cờ do client gửi |

Nhập password hai lần **không** tự tạo thành hai yếu tố. Password cộng một câu hỏi bảo mật cũng thường vẫn cùng nhóm “điều người dùng biết”. Email OTP hay SMS OTP có thể là một bước xác minh bổ sung, nhưng mức bảo đảm phụ thuộc kênh phân phối và khả năng chống chiếm đoạt; SMS thường yếu hơn cơ chế chống phishing như WebAuthn.

MFA không đồng nghĩa **mọi hành động đều luôn cần xác thực lại**. Nhiều hệ thống áp dụng *step-up authentication*: sau khi người dùng đăng nhập, các thao tác nhạy cảm mới cần yếu tố bổ sung còn hiệu lực.

### 2.1. Bốn trạng thái phải phân biệt

| Trạng thái | Ý nghĩa | Có được thao tác nhạy cảm? |
| --- | --- | --- |
| Chưa đăng nhập | Không có principal đáng tin | Không |
| Đã qua yếu tố thứ nhất | Password hoặc cơ chế đầu tiên đã được xác minh | Chỉ các thao tác cho phép ở mức bảo đảm này |
| Đang chờ MFA | Có challenge đang hoạt động nhưng chưa có bằng chứng hợp lệ | Không |
| Đã qua MFA | Server đã xác minh yếu tố bổ sung, bằng chứng gắn với principal/phiên còn hiệu lực | Có, nếu **còn đủ quyền nghiệp vụ** |

Việc qua MFA **không cấp thêm role quản trị** một cách mặc định. Một người dùng `ROLE_USER` đã xác minh hai yếu tố vẫn không được trở thành `ROLE_ADMIN` nếu chính sách nghiệp vụ yêu cầu role đó.

## 3. Vì sao phải kiểm tra phiên bản và cấu hình trước?

Trong một số dòng Spring Security mới, framework có thể cung cấp các khả năng MFA/step-up hoặc cơ chế đăng nhập liên quan, chẳng hạn xác thực bằng one-time token và WebAuthn. Nhưng **khả năng của một bản phát hành không đồng nghĩa dự án đã bật và cấu hình nó**. Một ứng dụng Spring Boot cũng có thể quản lý phiên bản Spring Security thông qua dependency management; không nên suy luận tính năng chỉ từ phiên bản Java hoặc chỉ từ việc có `spring-security-test`.

Trước khi viết test MFA, nhóm phát triển nên xác định:

1. **Phiên bản thực tế:** Spring Boot, Spring Security và các modules authentication/client/resource-server/WebAuthn/OTT đang được sử dụng.
2. **Bề mặt hỗ trợ:** cơ chế ấy có được hỗ trợ trên Servlet, Reactive hay cả hai không? Có yêu cầu một dependency tùy chọn không?
3. **Cấu hình thực đã bật:** security chain nào đăng ký yếu tố thứ nhất, yếu tố thứ hai và quy tắc yêu cầu MFA?
4. **Cách thể hiện yếu tố đã qua:** authority do framework quản lý, thuộc tính authentication, session-bound proof, authentication details hoặc một abstraction đáng tin khác?
5. **Thời hạn và cách hủy:** yếu tố thứ hai tồn tại bao lâu, bị xóa khi logout/đổi tài khoản/đổi mật khẩu ra sao?
6. **Hành vi từ chối:** trả `401`, `403`, redirect `302` đến trang xác minh hay lỗi nghiệp vụ có cấu trúc?
7. **Công cụ test:** phiên bản `spring-security-test` có helper tương ứng không, hay test phải gửi request thực qua cơ chế đã cấu hình?

Đặc biệt, **không tự nhận** những tên như `MFA_VERIFIED`, `FACTOR_PASSWORD` hoặc `FACTOR_OTP` là authorities mà mọi phiên bản Spring Security sẽ tự tạo. Tên được dùng trong một số ví dụ minh họa có thể là **quy ước của ứng dụng**, không phải API mặc định. Nếu dự án dùng MFA tích hợp, phải sử dụng đúng contract và các constant/API **do phiên bản đó cung cấp**.

### 3.1. Chiến lược lựa chọn

| Tình huống dự án | Cách tiếp cận |
| --- | --- |
| Phiên bản hỗ trợ MFA tích hợp đúng cơ chế cần dùng | Dùng cấu hình chính thức, kiểm tra cách các factors được cấp và các authorization rules thực thi |
| Có one-time-token/WebAuthn nhưng không có orchestration MFA như mong muốn | Tích hợp cơ chế đã hỗ trợ vào chính sách step-up có kiểm soát |
| Phiên bản cũ không có MFA tích hợp | Thiết kế luồng xác thực bổ sung có state phía server, provider/verifier rõ ràng và test đủ ranh giới |
| Ứng dụng là OAuth2 Resource Server nhận bearer token | Có thể yêu cầu mức xác thực từ token đã được issuer ký/xác minh, thay vì tự mở một màn hình OTP cho mọi API |
| Ứng dụng dùng OIDC Login | Có thể kiểm tra `acr`/`amr` theo hợp đồng với IdP và yêu cầu step-up đúng giao thức |
| Tính năng chỉ hỗ trợ Servlet nhưng ứng dụng là WebFlux | Không sao chép thẳng class/filter của Servlet; tìm cơ chế Reactive hoặc tích hợp được thiết kế riêng |

**Nguyên tắc:** ưu tiên cơ chế chuẩn do framework/Identity Provider hỗ trợ khi đáp ứng yêu cầu bảo mật. Không tự viết TOTP, WebAuthn protocol hoặc xác minh token từ đầu chỉ vì test dễ tạo một mã `123456`.

## 4. Phân biệt test có authentication giả với MFA thực

Đoạn test sau **không chạy bất kỳ yếu tố xác thực nào**:

~~~java
@Test
@WithMockUser(username = "operator", roles = "ADMIN")
void mockAdminCanCallBusinessCode() {
    // Chỉ có principal giả; chưa login qua password hay yếu tố thứ hai.
}
~~~

Với Servlet, `SecurityMockMvcRequestPostProcessors.user()` và `@WithMockUser` tạo authentication cho test. Với Reactive, `WebTestClient.mutateWith(mockUser(...))` có vai trò tương tự. Chúng phù hợp để cô lập và kiểm thử authorization, nhưng không phải bằng chứng rằng password, OTP, WebAuthn challenge hay xác nhận từ IdP đã được thực thi.

Ngay cả test đưa thẳng một authority tự đặt:

~~~java
mockMvc.perform(get("/api/sensitive/export")
        .with(user("operator")
                .authorities(
                    new SimpleGrantedAuthority("ROLE_ADMIN"),
                    new SimpleGrantedAuthority("MFA_COMPLETE"))))
    .andExpect(status().isOk());
~~~

cũng chỉ kiểm tra **ứng dụng xử lý một authentication giả mang những authorities này**. Nếu policy của ứng dụng tin vào `MFA_COMPLETE`, test vẫn có thể xanh khi bước xác minh OTP ngoài đời bị bỏ qua hoàn toàn.

| Cách tạo danh tính | Có kiểm tra policy không? | Có kiểm tra yếu tố thứ nhất không? | Có kiểm tra yếu tố thứ hai không? |
| --- | --- | --- | --- |
| `@WithMockUser` / `with(user(...))` | Có thể có | Không | Không |
| `mockJwt()` / `jwt()` | Có thể có | Không chạy decoder | Không xác nhận MFA thực |
| `mockOidcLogin()` / `oidcLogin()` | Có thể có | Không chạy OIDC flow | Không xác minh `acr`/`amr` từ ID token thật |
| HTTP password login thật | Có | Có | Chưa chắc |
| HTTP password login + second-factor verify thật | Có | Có | Có, nếu verifier/flow thực sự chạy |
| Bearer JWT ký thật + decoder + kiểm tra mức bảo đảm | Có | Xác minh token theo issuer/validators | Tùy claim và mức độ tin cậy của IdP |

**Câu hỏi cốt lõi khi review test:** “Giá trị cho biết yếu tố thứ hai đã qua được **ai tạo**? Test tự gắn, client tự khai hay một verifier tin cậy của server/IdP xác nhận?”

## 5. Luồng step-up chuẩn cần quan sát

Một luồng MFA kiểu session có thể được mô hình hóa:

~~~mermaid
flowchart TD
    A["Chưa đăng nhập"] --> B["POST /login: username + password"]
    B --> C{"Password hợp lệ?"}
    C -- "Không" --> D["Đăng nhập thất bại"]
    C -- "Có" --> E["Session đã xác thực yếu tố đầu"]
    E --> F["GET /api/sensitive/export"]
    F --> G{"Có proof yếu tố hai còn hạn và khớp session?"}
    G -- "Không" --> H["403 hoặc redirect tới bước MFA"]
    H --> I["Server tạo challenge, gắn user + session + thời hạn"]
    I --> J["POST /mfa/verify: bằng chứng từ authenticator"]
    J --> K{"Verifier chấp nhận và consume challenge?"}
    K -- "Không" --> L["Từ chối, đếm lần sai / khóa tạm"]
    K -- "Có" --> M["Server ghi proof xác minh còn hạn"]
    M --> F
    G -- "Có" --> N["Kiểm tra role/permission nghiệp vụ"]
    N -- "Đủ quyền" --> O["200 OK"]
    N -- "Thiếu quyền" --> P["403 Forbidden"]
    M --> Q["Hết hạn / logout / đổi danh tính"]
    Q --> H
~~~

Luồng này cần các tính chất:

- **Challenge được tạo từ server**, đủ khó đoán, có hạn và gắn với principal/session/thiết bị phù hợp.
- **Xác minh độc lập:** OTP/TOTP/WebAuthn được verifier đáng tin kiểm tra, không dùng cờ `mfa=true` từ request.
- **Proof được phát hành sau xác minh**, lưu ở server/session hoặc trong token được ký và kiểm tra đúng cách.
- **Chống replay:** mã hoặc challenge đã dùng không được chấp nhận lại khi chính sách yêu cầu sử dụng một lần.
- **Thời hạn hiệu lực:** step-up có thời gian sống giới hạn; thao tác rủi ro cao có thể yêu cầu thời gian xác minh gần đây.
- **Buộc vào danh tính:** xác minh của user A không được dùng cho user B, phiên khác hoặc đăng nhập mới.
- **Ủy quyền vẫn hoạt động:** MFA không tự nâng `ROLE_USER` thành `ROLE_ADMIN`.

### 5.1. Authentication chưa hoàn tất và authentication đã hoàn tất

Tùy cơ chế, một tài khoản sau password login có thể được biểu diễn là:

1. Authentication đã qua bước thứ nhất, nhưng policy của endpoint yêu cầu thêm yếu tố thứ hai.
2. Một authentication đang chờ hoàn tất trước khi được coi là đủ mức bảo đảm để truy cập route khác.

Cả hai mô hình đều có thể xuất hiện tùy phiên bản và ứng dụng. **Không mặc định `isAuthenticated() == true` nghĩa là MFA đã xong.** Ngược lại, đừng tự gọi `setAuthenticated(true)` sau khi client gửi mã bất kỳ.

## 6. Cấu trúc một ví dụ Servlet theo kiểu step-up

Để tách bạch rule và cơ chế xác minh, ví dụ tiếp theo mô tả một application **đã có login form thật**, một dịch vụ `SecondFactorVerifier` và một vùng tài nguyên nhạy cảm:

| Endpoint | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| `GET /api/profile` | Dữ liệu thông thường | Đã đăng nhập yếu tố đầu |
| `GET /api/sensitive/export` | Dữ liệu nhạy cảm | Đã đăng nhập, có `ROLE_REPORTER` và proof MFA còn hạn |
| `POST /mfa/verify` | Xác minh yếu tố bổ sung | Đã đăng nhập, CSRF hợp lệ, challenge hợp lệ |
| `POST /logout` | Kết thúc phiên | Hủy principal/session và proof |

Đây là **mô hình minh họa cách kiểm thử**, không phải bản triển khai TOTP/WebAuthn production. Production phải có các biện pháp bảo vệ bổ sung về lưu trữ secret, chống replay, throttling, recovery và phương thức quản lý challenge.

### 6.1. Định nghĩa bằng chứng MFA ở phía server

Ví dụ lưu một proof ngắn hạn ở session Servlet **chỉ sau khi verifier xác nhận thành công**:

~~~java
import java.time.Instant;

record MfaProof(String subject, Instant verifiedAt) { }
~~~

`subject` trong ví dụ là `Authentication.getName()`. Hệ thống thực nên dùng **định danh tài khoản ổn định**, đồng thời liên kết proof với phiên đã xác thực và challenge tương ứng. Một proof ở session không được tạo từ cookie tự khai chứa plain text như `MFA_COMPLETE=true`.

Với session lưu trong Redis hoặc kho phân tán, representation của proof phải tương thích cơ chế serialization và TTL của kho ấy; không coi record Java minh họa trên là thiết kế persistence hoàn chỉnh.

### 6.2. Một `AuthorizationManager` kiểm tra proof

Ví dụ dưới dùng API Servlet `AuthorizationManager<RequestAuthorizationContext>` để kiểm tra **cả danh tính và thời hạn proof**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

import jakarta.servlet.http.HttpSession;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept
        .RequestAuthorizationContext;

final class MfaProofAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    static final String PROOF_ATTRIBUTE = "MFA_PROOF";
    private final Clock clock;

    MfaProofAuthorizationManager(Clock clock) {
        this.clock = clock;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        if (current == null
                || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        HttpSession session = context.getRequest().getSession(false);
        if (session == null) {
            return new AuthorizationDecision(false);
        }

        Object stored = session.getAttribute(PROOF_ATTRIBUTE);
        if (!(stored instanceof MfaProof proof)) {
            return new AuthorizationDecision(false);
        }

        Instant now = clock.instant();
        boolean valid = current.getName().equals(proof.subject())
                && !proof.verifiedAt().isAfter(now)
                && now.isBefore(
                    proof.verifiedAt().plus(Duration.ofMinutes(5)));

        return new AuthorizationDecision(valid);
    }
}
~~~

Đoạn code là **guard để minh họa chính sách step-up trong session**, chưa phải toàn bộ bảo mật production. Nó không tự xác minh yếu tố thứ hai; `MfaProof` chỉ đáng tin nếu **chỉ code server-side sau verifier thật** mới có quyền ghi vào session. Phải bảo đảm session bị hủy/luân chuyển đúng ở login, logout và thay đổi tài khoản.

Một số phiên bản Spring Security có thể khuyến nghị phương thức `authorize(...)` thay cho `check(...)` hoặc cung cấp API MFA cao hơn. Chọn chữ ký và cấu hình đúng theo API mà **bản Spring Security thực tế của ứng dụng** hỗ trợ, không giữ ví dụ bất chấp thay đổi version.

### 6.3. Ghép vào security chain mà không bỏ qua quyền nghiệp vụ

Đăng ký guard cùng một `Clock` do ứng dụng quản lý (các phương thức dưới đây nằm trong một lớp `@Configuration`):

~~~java
@Bean
Clock mfaClock() {
    return Clock.systemUTC();
}

@Bean
MfaProofAuthorizationManager mfaGuard(Clock mfaClock) {
    return new MfaProofAuthorizationManager(mfaClock);
}
~~~

Trong test thời gian hết hạn, có thể thay `Clock` bằng một clock cố định phù hợp test context. Ở các phiên bản Spring Security có `AuthorizationManagers.allOf(...)`, ta kết hợp **hai điều kiện bắt buộc**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain applicationSecurity(
        HttpSecurity http,
        MfaProofAuthorizationManager mfaGuard) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/mfa/**").authenticated()
                .requestMatchers("/api/sensitive/**")
                    .access(AuthorizationManagers.allOf(
                        AuthorityAuthorizationManager
                            .hasRole("REPORTER"),
                        mfaGuard))
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

`AuthorityAuthorizationManager.hasRole("REPORTER")` đòi `ROLE_REPORTER`, còn `mfaGuard` đòi proof MFA hợp lệ. Cả hai phải cùng cho phép. Nếu phiên bản dự án chưa có API tổ hợp `allOf(...)`, hãy viết một `AuthorizationManager<RequestAuthorizationContext>` riêng kết hợp **cả hai điều kiện** thay vì bỏ qua một điều kiện.

Đây vẫn là **authorization guard**, không phải verifier MFA. Việc ghi `MfaProof` vào session chỉ được thực hiện sau khi một cơ chế xác minh yếu tố thứ hai đáng tin chấp nhận bằng chứng. Một test chỉ gắn proof thủ công vào session sẽ không chứng minh verifier ấy đã chạy.

### 6.4. Endpoint xác minh yếu tố bổ sung

Tách verifier thành interface để phần test có thể quan sát và kiểm chứng:

~~~java
interface SecondFactorVerifier {

    // Chỉ trả true khi chứng cứ hợp lệ, challenge thuộc đúng subject
    // VÀ phiên đang xác thực, rồi được consume chống replay.
    boolean verifyAndConsume(
            String subject, String sessionId, String challengeResponse);
}
~~~

Một endpoint minh họa:

~~~java
import java.time.Clock;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class MfaVerificationController {

    private final SecondFactorVerifier verifier;
    private final Clock clock;

    MfaVerificationController(
            SecondFactorVerifier verifier, Clock clock) {
        this.verifier = verifier;
        this.clock = clock;
    }

    @PostMapping("/mfa/verify")
    String verify(@RequestParam String code,
                  Authentication authentication,
                  HttpServletRequest request) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        if (!verifier.verifyAndConsume(
                authentication.getName(), session.getId(), code)) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Second factor rejected");
        }

        session.setAttribute(
                MfaProofAuthorizationManager.PROOF_ATTRIBUTE,
                new MfaProof(authentication.getName(), clock.instant()));

        return "verified";
    }
}
~~~

**Không sao chép giao diện `verifyAndConsume(subject, code)` thành verifier production đơn giản chỉ so chuỗi mã tĩnh.** Ví dụ cố ý không cài đặt thuật toán OTP/WebAuthn. Trong sản phẩm, verifier cần xác nhận challenge ID, principal ổn định, session, TTL, số lần thử, thiết bị/credential, sự kiện sử dụng một lần và khả năng thu hồi. Việc **tạo challenge** và gửi đến authenticator cũng phải có các endpoint/service riêng theo giao thức được chọn.

Với một ứng dụng có built-in MFA, hãy dùng verifier, filter và factor state do framework cung cấp thay vì tự viết một hệ thống proof song song. Mục 6 minh họa cách diễn đạt **hợp đồng cần kiểm thử** khi không có hỗ trợ tích hợp phù hợp.

## 7. Phân biệt kiểm thử chính sách với kiểm thử quy trình MFA

Có ba lớp test khác nhau:

| Loại test | Cách thiết lập | Khẳng định được |
| --- | --- | --- |
| Unit test guard | Dựng `Authentication` và `MfaProof` thử nghiệm | Rule so khớp chủ thể, thời hạn, session và quyền hoạt động |
| MockMvc với `@WithMockUser` | Gắn sẵn user/authorities | Policy với principal giả đúng; **không** chứng minh password/OTP |
| Integration test login + challenge + verify | Gửi password/form, CSRF, proof thật tới verifier, giữ session | Các bước authentication, session, challenge và policy nối đúng |
| HTTP qua `RANDOM_PORT` | Gửi request thật qua socket, cookies và proof | Thêm embedded server, HTTP transport, session cookie behavior |
| Browser/E2E với WebAuthn/IdP | Authenticator/IdP test phù hợp | Giao thức trình duyệt, origin/challenge và redirect/callback ở môi trường kiểm soát |

Nếu chỉ tạo `MfaProof` thủ công trong session test rồi thấy endpoint trả `200`, bạn mới chứng minh **guard nhận proof hợp lệ**. Test đó không chứng minh `SecondFactorVerifier` đã nhận OTP, chống replay hay ghi proof sau khi xác minh thành công.

### 7.1. Ma trận trạng thái bắt buộc

| Tình huống | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- |
| Guest vào vùng nhạy cảm | `401` hoặc redirect `302` theo entry point | Yếu tố đầu chưa hoàn tất |
| Password sai | Login thất bại | Authentication yếu tố đầu từ chối |
| Password đúng, chưa có MFA | `403` hoặc redirect/challenge theo policy | Không được vào vùng nhạy cảm |
| Password đúng, OTP/challenge sai | Verify bị từ chối, không có proof | Không được tự nâng mức xác thực |
| Password đúng, OTP đúng, proof còn hạn, có role | `200` | Được vào vùng nhạy cảm |
| OTP đúng nhưng user thiếu role | `403` | MFA không thay quyền nghiệp vụ |
| Proof hết hạn | Từ chối/yêu cầu step-up lại | Thời hạn được thực thi |
| Dùng lại code/challenge đã consume | Bị từ chối | Chống replay |
| Proof của user A áp sang user B | Bị từ chối | Chống chuyển danh tính |
| Logout rồi gọi lại bằng session cũ | Bị từ chối/được yêu cầu đăng nhập | Xóa authentication và proof |
| Đăng nhập phiên mới trên thiết bị khác | Không thừa hưởng proof trái phép | Gắn proof với phiên |

Các giá trị HTTP cụ thể phải theo **entry point, success/failure handler và security chain thực**. Với form login, guest thường nhận redirect `302`; với API trả Bearer challenge, `401` thường phù hợp. Không viết assert một mã HTTP cho mọi phiên bản/cơ chế rồi gán tất cả thất bại là lỗi.

## 8. MockMvc: test điều hướng và trạng thái phiên sau login thật

Giả sử ứng dụng đã có:

- Login form tại `POST /login` với tài khoản fixture `operator` và password `correct-test-password`.
- Yếu tố thứ hai có mã/challenge được phát hành trong test bằng **verifier thực hoặc verifier hợp đồng đã kiểm soát**.
- `GET /api/sensitive/export` yêu cầu `ROLE_REPORTER` **và** bằng chứng MFA còn hạn.
- `POST /mfa/verify` như ví dụ, cần CSRF.

Một test tích hợp Servlet có thể kiểm tra hành vi theo các bước:

~~~java
import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletMfaFlowTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void sensitiveActionRequiresVerifiedSecondFactor()
            throws Exception {

        MvcResult login = mockMvc.perform(
                post("/login")
                    .with(csrf())
                    .param("username", "operator")
                    .param("password", "correct-test-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        // Giả định policy của ví dụ chọn 403 cho user đã qua password
        // nhưng chưa đủ MFA; nếu app redirect đến step-up thì sửa matcher.
        mockMvc.perform(get("/api/sensitive/export").session(session))
            .andExpect(status().isForbidden());

        mockMvc.perform(post("/mfa/verify")
                .session(session)
                .with(csrf())
                .param("code", "incorrect-code"))
            .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/sensitive/export").session(session))
            .andExpect(status().isForbidden());

        // Mã này chỉ là fixture do test factor-provider phát hành;
        // test phải biết chính xác challenge nào là hợp lệ.
        mockMvc.perform(post("/mfa/verify")
                .session(session)
                .with(csrf())
                .param("code", "fixture-valid-code"))
            .andExpect(status().isOk());

        mockMvc.perform(get("/api/sensitive/export").session(session))
            .andExpect(status().isOk());
    }
}
~~~

**Cách đọc ví dụ:** Đây là **khung integration test** cho một ứng dụng đã triển khai đầy đủ verifier, challenge issuance, security chain và session. Riêng `"fixture-valid-code"` là tên minh họa, **không thể có hiệu lực nếu test chưa cấp challenge và verifier test không biết giá trị này**. Đối với TOTP, hãy tạo mã theo thuật toán thật từ secret fixture và clock kiểm soát; đối với WebAuthn, dùng authenticator test tạo chữ ký hợp lệ, không hardcode chuỗi thay thế.

Trong production, challenge phải được phát hành và liên kết với subject/session trước khi verify. Test nên đi qua cả bước phát hành challenge, thay vì chỉ thực hiện `POST /mfa/verify` nếu yêu cầu là kiểm tra toàn bộ quy trình.

Nếu muốn kiểm tra riêng policy, có thể dùng `@WithMockUser` cho các rule đủ/thiếu role — nhưng **phải có test tích hợp không dùng `@WithMockUser` để xác minh MFA thực**.

### 8.1. Cần tách lỗi do CSRF

`POST /login` và `POST /mfa/verify` trong ví dụ dùng `with(csrf())` vì security chain bảo vệ CSRF cho state-changing requests. Nếu thiếu CSRF, request có thể bị `403` **trước khi password hoặc mã yếu tố hai được kiểm tra**.

Vì vậy cần ít nhất hai ca riêng:

~~~java
// Đã có phiên đăng nhập hợp lệ; không CSRF:
mockMvc.perform(post("/mfa/verify")
        .session(session)
        .param("code", "some-code"))
    .andExpect(status().isForbidden());

// Có CSRF, mã sai:
mockMvc.perform(post("/mfa/verify")
        .session(session)
        .with(csrf())
        .param("code", "incorrect-code"))
    .andExpect(status().isUnauthorized());
~~~

Test đầu kiểm tra CSRF, test sau mới kiểm tra nhánh verifier từ chối. `session` ở đây là session đã xác thực được tạo trong test ở mục 8.

### 8.2. Điều gì sẽ xảy ra nếu chỉ cấp quyền qua `@WithMockUser`?

Một test mô phỏng:

~~~java
@Test
@WithMockUser(username = "operator", roles = "REPORTER")
void mockUserDoesNotProvideSecondFactorProof() throws Exception {
    mockMvc.perform(get("/api/sensitive/export"))
           .andExpect(status().isForbidden());
}
~~~

Nếu policy sử dụng server-side `MfaProof` chứ không tự tin một cờ client gửi, principal giả `REPORTER` chưa có proof sẽ bị chặn. Đây là test có giá trị cho **policy**. Tuy nhiên, test vẫn không chứng minh bất kỳ yếu tố thứ hai nào đã được kiểm tra.

Ngược lại, nếu policy dựa trên một authority giả `MFA_COMPLETE` do test gắn, request có thể nhận `200`. Chỉ nên kết luận rằng **rule nhận authority ấy**; muốn kết luận proof thật, phải test đường verifier phát hành authority hoặc state đó.

## 9. Unit test thời hạn, danh tính và session

Những ràng buộc về thời gian dễ gây flaky test nếu chỉ dựa vào `Instant.now()` và `Thread.sleep()`. Nên inject `Clock` để mô phỏng thời điểm:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock firstTime = Clock.fixed(
    Instant.parse("2026-01-01T10:00:00Z"), ZoneOffset.UTC);
Clock afterExpiry = Clock.fixed(
    Instant.parse("2026-01-01T10:06:00Z"), ZoneOffset.UTC);
~~~

Với TTL 5 phút trong `MfaProofAuthorizationManager`, test có thể tạo proof tại `10:00`:

- Với `Clock` tại `10:04`, cùng principal/session → guard cho phép.
- Với `Clock` tại `10:06` → guard từ chối.
- Cùng thời điểm nhưng principal khác → từ chối.
- Không có session → từ chối.
- Có session nhưng không có proof → từ chối.
- Proof trong tương lai bất thường → từ chối.

**Không sử dụng sleep sáu phút để test TTL**: chậm, dễ ảnh hưởng CI, không kiểm soát chính xác ranh giới hết hạn.

Đối với việc giới hạn thời gian của challenge hoặc OTP, dùng cùng nguyên tắc test với clock kiểm soát, cộng các ca quanh ranh giới thời gian và chênh lệch đồng hồ cho phép theo giao thức thực.

### 9.1. Cần test chống replay riêng

Nếu ứng dụng sử dụng **one-time token** hoặc challenge một lần, test nên:

1. Phát hành một challenge thật cho user/phiên.
2. Gửi response hợp lệ lần thứ nhất → chấp nhận, challenge bị consume.
3. Gửi lại **chính response và challenge ID ấy** → bị từ chối.
4. Thử dùng challenge của user A trên user B → bị từ chối.
5. Thử response sau TTL → bị từ chối.

**Lưu ý TOTP:** mã TOTP có thể không mang challenge ID như WebAuthn. Chính sách chống replay có thể cần lưu thời điểm/timestep đã dùng cho từng credential, chặn tái sử dụng trong cùng cửa sổ thời gian và xử lý race khi hai request đến đồng thời. Không chỉ gọi `verifyTotp(code)` hai lần với cùng mã rồi mặc định thư viện sẽ tự ngăn replay.

## 10. HTTP thật: session cookie, CSRF và step-up

`MockMvc` đủ để kiểm tra Servlet filters và authentication provider trong mock request. Khi mục tiêu gồm cookie, redirect, cổng server và HTTP boundary, dùng:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpMfaTests {
    @LocalServerPort
    int port;

    @Test
    void anonymousCannotReadSensitiveResource() {
        WebTestClient http = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();

        http.get()
            .uri("/api/sensitive/export")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

Đoạn trên giả định ứng dụng dùng **form login** và redirect guest; nếu ứng dụng dùng HTTP Basic/Bearer challenge, thay bằng assert `401`. Test HTTP hoàn chỉnh cần lưu `Set-Cookie` và CSRF token từ response trước, gửi lại cookie/token qua các bước login và verify, và khẳng định **session mới** không được thừa hưởng proof cũ.

Không dùng `@WithMockUser` hay `mockUser()` để truyền principal từ test qua socket: security context của test **không tự đi theo HTTP request**. Trong HTTP test, credentials và chứng cứ yếu tố thứ hai phải được gửi bằng đúng giao thức mà ứng dụng hỗ trợ.

### 10.1. Session fixation và logout

Một hệ thống cần xác minh ít nhất:

- Session ID được xử lý đúng theo cấu hình chống fixation khi xác thực hoặc tăng mức bảo đảm.
- Proof yếu tố hai không sống lâu hơn TTL dù session vẫn còn.
- Logout hủy authentication và proof; cookie cũ không truy cập được nội dung nhạy cảm.
- Đổi tài khoản trong cùng trình duyệt không tái sử dụng proof của tài khoản trước.
- Đổi password, vô hiệu hóa credential MFA hoặc thu hồi session làm mất hiệu lực proof theo chính sách.

Không giả định mọi ứng dụng đều dùng cookie: với bearer token thuần stateless, bằng chứng MFA có thể nằm trong token được issuer đáng tin ký và có hiệu lực ngắn. Khi đó rủi ro và test khác với session-based MFA.

## 11. WebFlux: cùng mục tiêu, khác cơ chế mang ngữ cảnh

Spring WebFlux dùng `SecurityWebFilterChain`, `ReactiveAuthenticationManager`, `ReactiveSecurityContextHolder` và có thể `WebSession`. Không thể sao chép trực tiếp một `HttpSession`-based guard Servlet vào Reactive:

| Thành phần | Servlet | Reactive |
| --- | --- | --- |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP request/session | `HttpServletRequest` / `HttpSession` | `ServerWebExchange` / `WebSession` |
| Authentication | `AuthenticationManager`/provider | `ReactiveAuthenticationManager` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` trong Reactor Context |
| Test mock HTTP | `MockMvc` | `WebTestClient.bindToApplicationContext(...)` |
| Test socket thật | `RANDOM_PORT` + HTTP client | `RANDOM_PORT` + `WebTestClient.bindToServer()` |
| Mock principal | `user()` / `@WithMockUser` | `mockUser()` / `@WithMockUser` với Reactive test integration |

Một test Reactive chỉ kiểm tra policy có thể là:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("operator").roles("REPORTER"))
      .get()
      .uri("/api/sensitive/export")
      .exchange()
      .expectStatus().isForbidden();
~~~

Ví dụ giả định `client` đã được bind vào WebFlux application context và áp dụng `springSecurity()`, đồng thời **policy thực** đang kiểm tra session-bound proof MFA và trả `403` cho user đã đăng nhập nhưng chưa đủ MFA.

Để kiểm tra MFA thực tế, phải gửi:

1. Credentials cho yếu tố đầu đến authentication mechanism của WebFlux.
2. Request tạo challenge và bằng chứng xác minh yếu tố hai đến endpoint phù hợp.
3. Cookie/session hoặc token đã được server xác nhận qua đúng HTTP requests.
4. Request đến endpoint nhạy cảm, rồi thử lại với proof hết hạn, bị thu hồi và danh tính khác.

Nếu verifier Reactive liên hệ DB/Redis/IdP, dùng API non-blocking trong pipeline; đừng gọi `block()` hoặc tự `subscribe()` trong `WebFilter`/`ReactiveAuthenticationManager` để đọc trạng thái MFA. Test cần kiểm tra **Reactor Context không rò rỉ giữa các request**, đặc biệt với xử lý song song.

## 12. MFA từ OIDC/JWT: chỉ tin kết quả đã được xác minh

Khi ứng dụng dùng OIDC hoặc token từ Identity Provider, mức xác thực có thể được biểu diễn bằng các claim như:

- `amr` (*Authentication Methods References*): các phương thức được dùng trong quá trình xác thực.
- `acr` (*Authentication Context Class Reference*): ngữ cảnh/mức bảo đảm của quá trình xác thực theo chính sách IdP.
- `auth_time`: thời điểm người dùng được xác thực, nếu provider và yêu cầu hỗ trợ.

**Không diễn giải những claim này theo một ý nghĩa toàn cục cứng nhắc.** Giá trị `amr`/`acr` và chính sách mức bảo đảm phải được thỏa thuận với IdP; bản thân một giá trị không bảo đảm độc lập đã có hai yếu tố mạnh nếu IdP không có hợp đồng đó.

Một test không hợp lệ để kết luận OIDC đã có MFA:

~~~java
mockMvc.perform(get("/api/sensitive/export")
        .with(oidcLogin().idToken(token -> token
            .claim("acr", "high")
            .claim("amr", java.util.List.of("pwd", "otp")))))
    .andExpect(status().isOk());
~~~

`oidcLogin()` dựng principal giả và claims do test tự đặt; **không** xác minh chữ ký ID token, issuer, audience hay tính xác thực của `acr`/`amr`.

Để kiểm tra yêu cầu MFA qua token:

1. Dùng OIDC provider/authorization server thử nghiệm với chính sách MFA đã cấu hình, hoặc sinh **JWS ký thật** bằng khóa test được decoder chấp nhận.
2. Kiểm tra issuer, audience, chữ ký, `exp`, `nbf` và chính sách `auth_time` khi cần.
3. Chỉ sau validation mới ánh xạ claim mức bảo đảm thành quyết định authorization.
4. Thử token đúng chữ ký nhưng **không có** yêu cầu MFA → bị từ chối tại endpoint nhạy cảm.
5. Thử token sai chữ ký/hết hạn → authentication bị từ chối.
6. Thử token đủ MFA nhưng thiếu permission nghiệp vụ → vẫn bị từ chối.

Với OIDC step-up, client có thể yêu cầu ngữ cảnh xác thực cao hơn (chẳng hạn qua `acr_values` theo khả năng IdP). Nhưng **gửi yêu cầu `acr_values` chưa chứng minh IdP đã thực hiện MFA**; phải xác minh kết quả mà IdP trả về trong token/flow hợp lệ.

## 13. Chống bỏ qua MFA qua đường đi khác

Một hệ thống có thể bảo vệ `/ui/export` nhưng bỏ sót `/api/export`, job endpoint hoặc một phương thức service được gọi trực tiếp. Test nên bao quát:

| Đường truy cập | Câu hỏi |
| --- | --- |
| Trang web quản trị | Có bắt step-up trước khi hiển thị dữ liệu nhạy cảm? |
| REST API tương đương | Có áp dụng cùng policy hay chỉ dựa vào route UI? |
| GraphQL hoặc RPC | Policy có kiểm tra cùng mức bảo đảm? |
| Service/method được tái sử dụng | Có thể bị gọi ngoài HTTP filter mà không kiểm tra MFA? |
| Access token sau login | Token có mang mức bảo đảm phù hợp và còn hạn? |
| Phiên thứ hai/một thiết bị khác | Có tái sử dụng bằng chứng MFA từ phiên đầu không? |
| Người dùng bị hạ quyền | MFA proof còn nhưng quyền nghiệp vụ đã thay đổi thì có bị từ chối? |
| Endpoint chuyển đổi tài khoản hoặc impersonation | Có xóa proof cũ và yêu cầu kiểm tra lại đúng user? |

Nếu policy MFA chỉ nằm ở controller, service gọi từ worker nội bộ có thể bỏ qua nó. Với thao tác đặc biệt nhạy cảm, nên kiểm tra ranh giới nghiệp vụ hoặc authorization manager được dùng thống nhất, kết hợp cả kiểm thử ở HTTP và ở service.

## 14. Bảo vệ chính quy trình MFA

### 14.1. Mã sai và giới hạn số lần thử

Thêm test:

- Mã sai không làm thay đổi trạng thái MFA.
- Sau nhiều lần sai liên tiếp, hệ thống rate-limit/lock challenge theo policy, không cho brute force.
- Sau khi bị khóa tạm, một mã hợp lệ cũng không tự bỏ qua khóa nếu policy yêu cầu chờ.
- Có thể tạo challenge mới sau khi challenge cũ bị thu hồi/hết hạn theo chính sách.
- Các phản hồi không tiết lộ người dùng có secret hoặc authenticator nào.

### 14.2. Khôi phục và thay đổi yếu tố

MFA không chỉ có login và verify. Recovery codes, thêm/tháo authenticator, đổi số điện thoại hoặc đổi khóa bảo mật là những đường **thay đổi mức bảo đảm của tài khoản**. Test cần ngăn người dùng chỉ có password đơn lẻ tự xóa yếu tố hai khi chính sách yêu cầu xác minh bổ sung.

### 14.3. WebAuthn và passkey

Với WebAuthn, verifier cần kiểm tra những phần quan trọng của giao thức như:

- Challenge do server phát hành, còn hạn và chưa được dùng.
- Origin và RP ID được kiểm tra theo cấu hình.
- Chữ ký xác thực bằng public key của credential đã đăng ký.
- Credential gắn đúng user, và kiểm tra user presence/user verification theo chính sách.
- Counter và tín hiệu clone detection được xử lý phù hợp với loại authenticator.

**Passkey không tự động đồng nghĩa “password cộng yếu tố thứ hai”.** Tùy chính sách và loại authenticator, passkey có thể là một cơ chế xác thực mạnh hoặc một yếu tố độc lập. Hãy định nghĩa mức bảo đảm yêu cầu trước khi viết test “MFA hoàn tất”.

Để kiểm tra giao thức WebAuthn thật, cần authenticator giả lập có khả năng tạo assertion hợp lệ hoặc môi trường browser/device phù hợp. Một `@WithMockUser` mang `MFA_COMPLETE` không chứng minh các điều kiện chữ ký/origin/challenge trên.

## 15. Những lỗi kiểm thử thường gặp

| Dấu hiệu | Ngộ nhận hoặc lỗi | Cách kiểm tra đúng |
| --- | --- | --- |
| `@WithMockUser(roles = "ADMIN")` được `200` | Cho rằng MFA đã qua | Tách policy test và test login/verify thực |
| Tự gắn `MFA_COMPLETE` vào `SecurityContext` | Coi cờ test là proof của verifier | Kiểm tra code server-side phát hành state/authority |
| Chỉ test sai OTP | Verifier luôn từ chối cũng có thể làm test xanh | Có ca đúng OTP được phép |
| Chỉ test đúng OTP | Verifier luôn chấp nhận có thể làm test xanh | Có ca sai, hết hạn và replay |
| OTP sai nhưng POST thiếu CSRF | Thất bại có thể do CSRF trước verifier | Cấp CSRF hợp lệ để test OTP |
| Login form bằng `@WithMockUser` | Password manager không được chạy | Gửi form password thật qua request |
| Proof còn hạn ở user A dùng được cho user B | Proof không gắn subject/session | Kiểm tra binding và session lifecycle |
| Token OIDC mock có `acr=high` | Giả định IdP thực hiện MFA | Test ID token/JWS được ký và hợp đồng IdP |
| JWT có claim `mfa=true` do client tự viết | Đọc claim chưa xác minh chữ ký | Dùng decoder/issuer/audience validators thật |
| Dùng `Thread.sleep` để test hết hạn | Test chậm, flaky | Inject `Clock` |
| Vừa có role admin là được vào tài nguyên | Bỏ điều kiện step-up | Test cả role và MFA proof |
| Copy API MFA từ phiên bản khác | Không compile hoặc policy hoạt động khác | Kiểm tra tài liệu đúng version và integration test |
| Xóa session bằng logout nhưng proof vẫn còn ở cache | Sai cleanup lifecycle | Test request sau logout và thu hồi state |
| Test mock WebFlux dùng `HttpSession` của Servlet | Khác mô hình HTTP/session | Dùng `WebSession` và Reactor Context |

## 16. Bài tập áp dụng

### Bài 1: MFA chưa hoàn tất không được xuất dữ liệu

Viết hai ca MockMvc cho `GET /api/sensitive/export`: `ROLE_REPORTER` không có proof phải bị từ chối, và cùng role có proof do **verifier test** tạo phải được phép. Giải thích test nào chỉ kiểm tra policy và test nào thực sự đi qua verifier.

### Bài 2: kiểm chứng vòng đời challenge

Tạo challenge một lần cho `operator`, gửi response sai, sau đó response đúng, rồi gửi lại response đúng lần nữa. Kỳ vọng sai bị từ chối, đúng được chấp nhận một lần, lần replay bị từ chối. Kiểm tra verifier gắn challenge với đúng principal và session.

### Bài 3: kiểm tra role và MFA độc lập

Tạo bốn tổ hợp: role đúng/MFA đúng; role đúng/MFA thiếu; role sai/MFA đúng; role sai/MFA thiếu. Chỉ tổ hợp đầu tiên được vào endpoint nhạy cảm. Với người chưa đăng nhập, kiểm tra thêm behavior của entry point.

### Bài 4: giới hạn thời gian

Inject `Clock.fixed(...)` cho server-side proof. Tại thời điểm 4 phút sau verify, quyền còn hiệu lực; sau 6 phút, phải yêu cầu step-up lại. Không dùng `Thread.sleep()` để giả lập thời gian.

### Bài 5: OIDC mức bảo đảm

Một endpoint yêu cầu MFA qua IdP. Viết test principal giả để kiểm tra policy mapping của `acr`/`amr`, rồi thiết kế integration test với ID token **đã ký**: issuer/audience đúng nhưng mức bảo đảm thấp bị từ chối; mức cao phù hợp được chấp nhận; token sai chữ ký/hết hạn bị chặn tại decoder.

### Bài 6: Servlet và Reactive

Mô tả cách viết cùng một ma trận cho `MockMvc` và `WebTestClient`. Chỉ ra nơi dùng `HttpSession`/`SecurityFilterChain` và nơi dùng `WebSession`/`SecurityWebFilterChain`, cùng giới hạn của `@WithMockUser` trên HTTP server thật.

### Bài 7: kiểm tra phiên bản

Trong một môi trường thử nghiệm độc lập, kiểm tra tài liệu đúng phiên bản Spring Security mà dự án sử dụng. Xác định built-in MFA hoặc các cơ chế yếu tố sẵn có, nền tảng Servlet/Reactive hỗ trợ, cách cấp proof và API test. Viết một bảng quyết định “dùng tích hợp sẵn / dùng IdP / custom step-up”, không suy luận từ tên dependency đơn lẻ.

## 17. Checklist hoàn thành

- [ ] Đã xác minh **phiên bản và tính năng MFA** có thật, đã cấu hình đúng cho stack đang dùng.
- [ ] Có định nghĩa rõ yếu tố đầu, yếu tố hai và mức bảo đảm mong muốn.
- [ ] Có ca guest, password sai, password đúng nhưng chưa đủ MFA.
- [ ] Có ca MFA sai/đúng, challenge hết hạn và chống replay.
- [ ] Proof được tạo bởi verifier tin cậy, không chỉ do `@WithMockUser` hay client tự gắn.
- [ ] Proof được liên kết với principal, session hoặc token đúng thiết kế.
- [ ] Có TTL/step-up freshness và test bằng clock kiểm soát.
- [ ] Có xử lý logout, đổi danh tính, thu hồi credential, recovery và thiết bị khác.
- [ ] MFA không mặc nhiên cấp thêm role/permission nghiệp vụ.
- [ ] Có test cả route/method nhạy cảm và các đường đi tương đương.
- [ ] CSRF, cookies và HTTP redirects được kiểm tra theo cơ chế thực.
- [ ] Với OAuth2/OIDC/JWT, chỉ tin claims **sau khi** token/IdP được xác minh.
- [ ] Test mock principal được phân loại là **policy test**, không ghi nhầm thành E2E MFA.
- [ ] Chưa tuyên bố production MFA an toàn chỉ vì test server/IdP mock cho `200`.

## 18. Kết luận

MFA là một **chuỗi xác thực với bằng chứng đáng tin**, không phải một role hoặc thuộc tính do test tự đặt. `@WithMockUser`, `mockJwt()` và `oidcLogin()` giúp kiểm tra authorization sau khi đã có principal, nhưng không chứng minh password, OTP, WebAuthn hoặc Identity Provider đã thực sự xác minh yếu tố bổ sung.

Để kiểm chứng nhiều yếu tố, hãy xác định **khả năng hỗ trợ thực của phiên bản và cấu hình**, dùng các thành phần tích hợp phù hợp, rồi kiểm tra cả những request được chấp nhận và bị từ chối: chưa login, mới qua yếu tố đầu, challenge sai/hết hạn/replay, xác minh đúng, thiếu role, logout và phiên khác. Đặc biệt, test cần chứng minh **proof được phát hành bởi verifier đáng tin** và chỉ còn hiệu lực trong đúng ngữ cảnh được phép.

## 19. Tài liệu tham khảo

- [Spring Security Reference — Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html): các cơ chế đăng nhập và lựa chọn theo phiên bản.
- [Spring Security Reference — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` và các quyết định quyền.
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): helpers cho authentication, CSRF và HTTP assertions.
- [Spring Security Reference — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): lựa chọn cơ chế và ngữ cảnh Reactive.
- [Spring Security Reference — Reactive Web Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): `WebTestClient`, authentication giả và CSRF.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC/OAuth2 login và các thành phần xác thực.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, mock web và `RANDOM_PORT`.
- [W3C — Web Authentication](https://www.w3.org/TR/webauthn-3/): challenge, authenticator assertions và user verification.
- [RFC 6238 — Time-Based One-Time Password Algorithm](https://www.rfc-editor.org/rfc/rfc6238): TOTP và các cửa sổ thời gian.
