# Kiểm thử danh tính ngoài, liên kết tài khoản và lỗi nhà cung cấp

Khi ứng dụng Java cho phép đăng nhập bằng **Google, Microsoft Entra ID, một OpenID Connect (OIDC) Provider hoặc một dịch vụ OAuth2 có UserInfo API**, công việc kiểm thử không dừng ở việc một request có `Authentication` và trả HTTP 200. Ứng dụng còn phải trả lời: danh tính ngoài này là ai theo **issuer/provider + subject bất biến**? Nó đã được liên kết với tài khoản nội bộ nào? Có được tự liên kết bằng email không? Khi nhà cung cấp từ chối đăng nhập, hết hạn phiên, trả thông tin lỗi hoặc bị gián đoạn, ứng dụng có vô tình tạo phiên hoặc gắn sai tài khoản không?

Bài học thuộc nhóm **Kiểm thử đăng nhập** của **Spring Security - authentication**. Phạm vi là **Spring Boot 3.5.x, Spring Security 6.5.x, Java 17+, Spring MVC/Servlet**, dùng `spring-security-test`, `MockMvc`, JUnit Jupiter và một kho liên kết tài khoản đơn giản. Nội dung phân biệt rõ **mock danh tính để test domain/authorization** với **test thực sự trao đổi authorization code và xác minh token với IdP**, đồng thời hướng dẫn negative tests, lỗi provider, bảo vệ state/nonce/issuer, chống account takeover qua auto-link và tính nhất quán trong database.

## 1. Từ bên ngoài đăng nhập đến tài khoản trong ứng dụng: ba lớp khác nhau

| Lớp | Đối tượng | Vai trò |
| --- | --- | --- |
| **Nhà cung cấp danh tính** (IdP / OpenID Provider / OAuth2 provider) | User tại nhà cung cấp, session tại IdP | Xác minh người dùng bên ngoài theo giao thức và policy của họ |
| **Spring Security OAuth2 Login Client** | `ClientRegistration`, authorization request, callback, ID token/UserInfo, `OAuth2AuthenticationToken` | Thực hiện OAuth2 Authorization Code/OIDC Login, thiết lập `Authentication` và phiên ứng dụng |
| **Tài khoản nội bộ (local account)** | `account_id`, quyền/tenant, trạng thái và các external identity bindings | Quyết định tài khoản nghiệp vụ nào được truy cập, cách liên kết/hủy liên kết và quyền cuối cùng |

Một provider có thể báo “alice đã đăng nhập với email alice@example.test”, nhưng ứng dụng vẫn phải xác định **local account ID**. Nếu ứng dụng tự gắn mọi email trùng nhau vào một tài khoản, việc đổi địa chỉ, alias, tenant, claim chưa được xác minh hoặc IdP cấu hình sai có thể dẫn đến **chiếm quyền tài khoản (account takeover)**.

**Hai loại thành công không tương đương:**

- **Provider authentication succeeded**: OIDC ID token/UserInfo hoặc OAuth2 identity đã được framework xác minh/nhận hợp lệ theo cấu hình.
- **Local account session ready**: ứng dụng đã resolve đúng account mapping, account không bị khóa, đủ policy/MFA, lưu session/context và trả kết quả sau login.

Kiểm thử cần quan sát cả hai, đặc biệt tình huống provider login thành công **nhưng liên kết bị từ chối**.

## 2. Khóa danh tính ổn định: OIDC dùng (iss, sub), không dùng email

### 2.1. OIDC — cặp issuer và subject

Theo mục 5.7 của **OpenID Connect Core 1.0**, khi Relying Party cần định danh ổn định một người dùng, cặp **`iss` + `sub`** từ ID token mới là khóa có bảo đảm thích hợp. `sub` chỉ cần duy nhất trong phạm vi một issuer; hai issuer khác nhau có thể cùng phát hành `sub=123` cho hai người khác nhau.

~~~text
IdP A: iss=https://issuer-a.example.test, sub=123   → Identity A
IdP B: iss=https://issuer-b.example.test, sub=123   → Identity B

Identity A ≠ Identity B

IdP A: iss=https://issuer-a.example.test, sub=456,
       email=shared@example.test                   → Identity C

Identity A ≠ Identity C, dù email có thể trùng.
~~~

**Không dùng email, preferred_username, name, displayName hay picture URL làm primary key cho liên kết tài khoản.** Chúng có thể đổi, bị tái sử dụng hoặc không được xác minh. `email_verified=true` là tín hiệu bổ sung về email theo ngữ nghĩa provider; **không phải** bằng chứng user đã kiểm soát local account hiện có và đồng ý liên kết.

Các điều kiện trước khi tin cặp `iss+sub`:

- Callback phải đi qua **đường OAuth2/OIDC thật đã xác minh**: authorization code, client binding, state, redirect URI, token endpoint và tính hợp lệ của ID token.
- Kiểm chữ ký theo keys tin cậy, issuer, audience/client ID, thời gian hiệu lực và nonce ở nơi giao thức yêu cầu; không dùng `decode Base64` làm validation.
- Không tin một JSON chứa `iss`/`sub` do client gửi lên để ra lệnh `linkAccount(...)`.
- Hạn chế issuer trong danh sách nhà cung cấp được cấu hình; không lấy metadata hoặc JWKS URL tùy ý từ untrusted claims dẫn đến SSRF/issuer confusion.
- Nhận diện mô hình `pairwise subject`: cùng một người tại IdP có thể nhận `sub` khác với các client/sector khác nhau. Không ép so sánh `sub` xuyên RP/sector mà không có hợp đồng từ IdP.

### 2.2. OAuth2 không có OIDC ID token

`oauth2Login()` còn hỗ trợ nhà cung cấp OAuth2 không OIDC. Khi đó user identity thường lấy từ UserInfo hoặc API của provider qua `OAuth2UserService`. Không phải mọi provider đều có claim `sub`; ví dụ provider có thể cung cấp một **numeric user ID** ổn định trong attribute `id`.

Lúc này khóa nên có dạng:

~~~text
(namespace/provider registration đã được kiểm soát, stable provider user id)

oauth2:lab-social + id=5021
~~~

Việc dùng registration ID trong namespace chỉ an toàn nếu ứng dụng **kiểm soát mapping registration → nhà cung cấp đúng**, và attribute `id` được lấy từ **endpoint/provider đáng tin đã cấu hình**. Không cho attacker tự gửi `registrationId`/`userId` từ frontend rồi xem như identity đã xác minh.

**Quan trọng:** OAuth2 thuần là cơ chế ủy quyền, không tự định nghĩa chuẩn identity toàn cục. Đừng nhầm access token của một service với OIDC ID token dành cho client login.

### 2.3. Mô hình dữ liệu đúng

~~~text
LOCAL_ACCOUNT
    account_id (PK, UUID hoặc ID nội bộ không tái sử dụng)
    email, status, tenant, roles, recovery policy
           │ 1
           ▼ N
EXTERNAL_ACCOUNT_LINK
    link_id (PK)
    account_id (FK → LOCAL_ACCOUNT.account_id)
    namespace (issuer OIDC hoặc provider key do app quản lý)
    subject (stable external user identifier)
    created_at, last_verified_at, revoked_at, ...
    UNIQUE(namespace, subject)
~~~

Một local account có thể gắn nhiều external identities, ví dụ corporate OIDC và social provider. Nhưng **mỗi external identity chỉ được liên kết với tối đa một local account tại một thời điểm**.

Các bất biến:

1. `UNIQUE(namespace, subject)` được database enforce, không chỉ kiểm tra trong code.
2. Không overwrite mapping của một external identity đã thuộc account khác.
3. Liên kết lại cùng account là **idempotent** hoặc trả kết quả xác định.
4. Xóa link không xóa account hoặc các link khác một cách vô ý.
5. Phải giữ lại ít nhất một phương thức đăng nhập/khôi phục hợp lệ theo policy.
6. Nếu account khóa/xóa, provider vẫn xác thực được không có nghĩa local account được mở lại.
7. Mọi thao tác link/unlink phải có audit và kiểm tra owner, recent authentication và CSRF/session binding theo threat model.

## 3. Các kịch bản linking và nguy cơ chiếm tài khoản

| Trường hợp | Hành vi mong muốn |
| --- | --- |
| IdP trả identity `(iss-A, sub-1)` đã liên kết `account-1` | Resolve chính xác `account-1` nếu status/policy hợp lệ |
| Identity mới, local account chưa có link | Chọn **đăng ký local account mới** hoặc quy trình liên kết có bằng chứng; không tự chiếm account có email trùng |
| User đang đăng nhập `account-1` muốn thêm IdP B | Yêu cầu **recent local authentication/step-up**, redirect tới IdP B, callback xác minh, confirm intent rồi ghi link atomically |
| Identity từ IdP B đã thuộc `account-2` | Trả conflict; **không gỡ/chuyển sang account-1** |
| Email claim trùng nhưng `sub` khác | Không tự coi là cùng người hoặc cùng account |
| Provider trả `email_verified=false` | Không dùng email như căn cứ khôi phục/link; tuân theo policy xác minh |
| Provider đổi display name/email | Giữ mapping theo stable provider ID; cập nhật profile riêng nếu cần |
| Một người có hai identities khác provider | Có thể cùng trỏ về local account sau khi cả hai đã được xác minh và owner xác nhận |
| Local account bị khóa dù provider token hợp lệ | Từ chối local login, không tự mở khóa |
| User muốn unlink method cuối | Chặn hoặc yêu cầu thiết lập recovery/method khác trước |
| Hai request link đồng thời cùng external identity | Tối đa một owner qua UNIQUE và transaction; không lấy “last writer wins” |
| User A gửi `accountId=B` trong HTTP body để liên kết | Phải bị từ chối IDOR; owner lấy từ local authenticated session, không tin body |

### 3.1. Quy trình link bảo mật: xác minh cả hai đầu

~~~text
Browser có local session của account-1
       │
       ▼
Bước 1: Re-auth/step-up cho local account-1
       │ accountId lấy từ SecurityContext/session
       ▼
Bước 2: Server tạo pending link intent
       │ random state, expiry, local account id, operation=LINK
       ▼
Bước 3: Redirect sang IdP để user xác thực external identity
       │ OAuth2 authorization_code, state, PKCE/nonce theo cấu hình
       ▼
Bước 4: Callback OIDC/OAuth2 đã được xác minh bởi server
       │ issuer/provider + stable subject
       ▼
Bước 5: Server kiểm pending intent, local owner & session binding
       │ không dùng email tự động, không nhận accountId client tùy ý
       ▼
Bước 6: INSERT UNIQUE(namespace, subject) → account-1
       │  ├─ đã thuộc account-1 → idempotent
       │  ├─ đã thuộc account-2 → conflict, không relink
       │  └─ chưa tồn tại       → tạo link mới
       ▼
Bước 7: Audit + confirmation; giữ recovery path
~~~

Một lỗi nghiêm trọng là coi **bất kỳ OAuth2 callback login nào** là yêu cầu liên kết tài khoản. Nếu không có `pending link intent` đã xác minh, callback chỉ nên tiếp tục **luồng login** theo identity đã tồn tại hoặc quy trình đăng ký an toàn.

**Không chứa client secret, ID token, authorization code, access/refresh token trong `pending link intent` hiển thị ra URL/log.** OAuth2 `state` là giá trị ngẫu nhiên để ràng buộc luồng và chống CSRF/response injection; không nên nhúng account ID hoặc credential dễ đoán trong state thuần.

### 3.2. Liên kết bằng email: vì sao “email trùng” là chưa đủ?

Một provider có thể trả `email=student@example.test` nhưng:

- Email chưa được xác minh, bị tái sử dụng hoặc được cấp cho nhân viên mới.
- Một local account dùng cùng email nhưng chủ thực sự khác.
- Người dùng có email alias hoặc tenant khác nhưng cùng address.
- Provider cung cấp email cho mục đích liên hệ, không phải stable subject.
- Có thể có thay đổi email sau khi lần đầu liên kết.

Nếu ứng dụng tự động làm:

~~~java
// SAI: chỉ thấy email trùng rồi nối thẳng tài khoản.
String localAccountId =
        localUsers.findByEmail(externalUser.getAttribute("email"));
links.save(localAccountId, externalUser.getAttribute("sub"));
~~~

thì attacker có thể chiếm local account qua claim không đủ đáng tin. Phương án đúng là dùng stable external identity để resolve; khi cần merge/link, yêu cầu cả local proof và external proof, kiểm tra owner, duy trì transaction và audit. Nếu enterprise federation cho phép auto-provision/auto-link, phải có **hợp đồng chính sách IdP/tenant rất cụ thể** và kiểm thử riêng, không áp rule email chung cho mọi provider.

## 4. Ba tầng kiểm thử bắt buộc

| Tầng | Công cụ | Chứng minh được | **Không chứng minh được** |
| --- | --- | --- | --- |
| **Unit/domain** | JUnit, Java service, fake repository | Unique external key, ownership/conflict, idempotency, account state/link logic | Token có chữ ký thật, HTTP callback và state |
| **Spring MVC security/controller** | `MockMvc` + `oidcLogin()`, `oauth2Login()` | Controller/authorization đọc đúng principal, mapping provider, response, ACL | Đã gọi IdP hoặc verify thực sự `iss/aud/nonce/signature` |
| **OAuth2/OIDC protocol integration** | Test IdP hoặc local stub issuer/token/JWKS/UserInfo, HTTP client và browser/session | Authorization request, callback, token exchange, validation, session/cookie, error/timeout | Production IdP không bao giờ thay đổi hay gặp outage |
| **E2E/contract với provider thật** | Staging IdP và dedicated test accounts | Tương thích metadata, redirect URI, MFA/consent, mTLS/proxy/session, failure modes thật | Không thay thế canary/negative/security tests và quan sát production |

**Bẫy rất thường gặp:** sử dụng `oidcLogin()` rồi kết luận “JWT signature, issuer và nonce đã được kiểm tra đúng”. Helper này **tạo SecurityContext giả** theo yêu cầu test, không gọi IdP và không cryptographically validate token. Nó rất tốt cho logic **sau xác thực**, nhưng cần tầng protocol integration riêng.

## 5. Spring Security hỗ trợ những API nào?

### 5.1. Cấu hình Servlet OAuth2 Login

Các thành phần tiêu biểu trong Spring Security 6.5:

- `HttpSecurity.oauth2Login(...)` cấu hình login OAuth2/OIDC authorization code.
- `ClientRegistration` định nghĩa `registrationId`, client ID/secret, authorization URI, token URI, redirect URI, scopes, issuer URI/JWK Set/UserInfo endpoint khi phù hợp.
- `ClientRegistrationRepository` cung cấp các registrations mà ứng dụng cho phép.
- `OAuth2AuthorizationRequestRedirectFilter` tạo authorization request và redirect qua `/oauth2/authorization/{registrationId}`.
- `OAuth2LoginAuthenticationFilter` xử lý callback mặc định `/login/oauth2/code/{registrationId}`.
- `OAuth2AuthorizedClientRepository` lưu thông tin authorized client theo cơ chế đã cấu hình; khác với bảng account links của ứng dụng.
- `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` điều khiển response của thành công/thất bại.
- `OAuth2UserService`/`OidcUserService` có thể được tùy biến để map claims thành local principal theo security policy.

**Không** có mặc định “OAuth2AuthorizedClient là link local account”. Nó mô tả quyền truy cập/resource access token của OAuth2 client, **khác** với mapping issuer+subject đến account nội bộ.

### 5.2. MockMvc helpers

`spring-security-test` cung cấp:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
~~~

Đây là ví dụ imports được xuống dòng sau package; trong file hoàn chỉnh bên dưới, imports được viết một dòng/statement cho dễ sao chép.

- `oidcLogin()` trả `OidcLoginRequestPostProcessor`; có `idToken(builder -> ...)`, `authorities(...)`, `oidcUser(...)`, `clientRegistration(registration)`.
- `oauth2Login()` trả `OAuth2LoginRequestPostProcessor`; có `attributes(attrs -> ...)`, `authorities(...)`, `oauth2User(...)`, `clientRegistration(registration)`.
- Cả hai tạo `OAuth2AuthenticationToken`/principal cho request, không kiểm chứng chữ ký token hay truy vấn UserInfo thật.
- `.with(oidcLogin())`/`.with(oauth2Login())` được đặt trên `get(...)`/`post(...)` bình thường.
- Nếu test quản lý link có HTTP POST và dùng cookie/session, nhớ `.with(csrf())` khi CSRF bật.

**Khác biệt:** `@WithMockUser` mô phỏng local principal thông thường, **không** tạo `OidcUser` với ID token hoặc `OAuth2AuthenticationToken`. Khi domain cần lấy issuer/sub, nên chọn đúng OAuth2/OIDC post-processor thay vì chỉ mock username.

## 6. Demo Java 17: danh tính ngoài có thể trùng subject nhưng khác issuer

Trước khi dùng Spring, một chương trình Java 17 độc lập minh họa rõ vì sao `(issuer, subject)` mới là khóa dữ liệu.

Tệp `ExternalIdentityKeys.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ExternalIdentityKeys {
    record ExternalId(String issuer, String subject) {
    }

    public static void main(String[] args) {
        var first = new ExternalId("https://issuer-a.test", "123");
        var second = new ExternalId("https://issuer-b.test", "123");

        Map<ExternalId, String> owners = new HashMap<>();
        owners.put(first, "account-one");
        owners.put(second, "account-two");

        System.out.println(first.equals(second));
        System.out.println(owners.get(first));
        System.out.println(owners.get(second));
        System.out.println(owners.size());
    }
}
~~~

Biên dịch/chạy (JDK 17+):

~~~bash
javac --release 17 ExternalIdentityKeys.java
java ExternalIdentityKeys
~~~

Stdout **chính xác**:

~~~text
false
account-one
account-two
2
~~~

`record` tạo `equals`/`hashCode` dựa trên **cả issuer lẫn subject**, nên hai người dùng ở hai issuers dù có cùng `sub` không bị gộp. Đoạn này chỉ mô phỏng **định danh và ánh xạ trong RAM**, chưa thực hiện OAuth2/OIDC, không có HTTP hay database.

## 7. Demo Spring Boot 3.5 + Spring Security 6.5: OIDC, OAuth2 và lỗi provider

Demo cấu hình **hai client registrations hoàn toàn giả lập** để test không cần Internet:

- `lab-oidc`: OIDC issuer `https://issuer.lab.invalid`, ID token có `iss`/`sub`.
- `lab-social`: OAuth2 non-OIDC, stable user ID ở attribute `id`.

Domain `.invalid` được dùng để tránh nhầm với IdP hoạt động thực. App có endpoint `GET /api/external/identity` đọc principal đã được Spring cung cấp và trả cặp định danh cho **lab**. Trong production, **không tự lộ raw external subject/issuer cho UI không có nhu cầu**; response nên dùng định danh ứng dụng và policy riêng tư.

**Giới hạn demo quan trọng:** registrations có URI provider giả; chạy ứng dụng không thể hoàn tất callback thật nếu chưa dựng test issuer/token/JWKS/UserInfo. Tuy vậy các test `oidcLogin()/oauth2Login()` bên dưới vẫn chạy không cần IdP vì chúng mô phỏng SecurityContext. Đừng xem nó là mẫu product-ready account linking endpoint.

### 7.1. Dependencies

`build.gradle` (chèn vào project Spring Boot 3.5/Groovy DSL có plugin/BOM và Java 17+):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-oauth2-client` là dependency cần cho `ClientRegistration`, `OAuth2LoginAuthenticationFilter` và các principal/authorized client OAuth2/OIDC. Nếu project đã dùng Spring Boot BOM, không cần hard-code phiên bản `spring-security-test` khác nhánh runtime.

### 7.2. Một file Spring Boot chứa các class demo

Tạo `src/main/java/example/externallogin/ExternalLoginApplication.java`:

~~~java
package example.externallogin;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ExternalLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalLoginApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ExternalSecurityConfig {

    @Bean
    ClientRegistrationRepository clientRegistrations() {
        ClientRegistration oidc = ClientRegistration
                .withRegistrationId("lab-oidc")
                .clientName("OIDC Lab")
                .clientId("oidc-lab-client")
                .clientSecret("not-a-real-secret")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .authorizationUri("https://issuer.lab.invalid/authorize")
                .tokenUri("https://issuer.lab.invalid/token")
                .jwkSetUri("https://issuer.lab.invalid/jwks")
                .issuerUri("https://issuer.lab.invalid")
                .userNameAttributeName("sub")
                .build();

        ClientRegistration social = ClientRegistration
                .withRegistrationId("lab-social")
                .clientName("Social Lab")
                .clientId("social-lab-client")
                .clientSecret("not-a-real-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("read:user")
                .authorizationUri("https://social.lab.invalid/authorize")
                .tokenUri("https://social.lab.invalid/token")
                .userInfoUri("https://social.lab.invalid/userinfo")
                .userNameAttributeName("id")
                .build();

        // Các URI .invalid chỉ dùng cho test; không thể login thật.
        return new InMemoryClientRegistrationRepository(oidc, social);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            SafeExternalFailureHandler failureHandler)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login",
                        "/oauth2/authorization/**",
                        "/login/oauth2/code/**")
                .permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(oauth -> oauth
                .failureHandler(failureHandler));

        // Giữ CSRF mặc định cho các request thay đổi trạng thái.
        // Link/unlink thật cần owner session, CSRF và step-up.
        return http.build();
    }
}

record ExternalIdentity(String namespace, String subject) {
    ExternalIdentity {
        if (namespace == null || namespace.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "External identity must have namespace and subject");
        }
    }
}

final class ExternalIdentityReader {
    private ExternalIdentityReader() {
    }

    static ExternalIdentity from(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        String registration = oauth.getAuthorizedClientRegistrationId();

        // Trong real login, OidcUser chỉ đáng tin SAU khi framework
        // đã verify ID token với provider đã cấu hình.
        if ("lab-oidc".equals(registration)
                && oauth.getPrincipal() instanceof OidcUser oidc) {
            var idToken = oidc.getIdToken();
            if (idToken.getIssuer() == null
                    || !("https://issuer.lab.invalid")
                        .equals(idToken.getIssuer().toString())
                    || idToken.getSubject() == null
                    || idToken.getSubject().isBlank()) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN);
            }
            return new ExternalIdentity(
                    idToken.getIssuer().toString(),
                    idToken.getSubject());
        }

        // Non-OIDC: app quyết định stable ID qua provider mapping.
        if ("lab-social".equals(registration)
                && !(oauth.getPrincipal() instanceof OidcUser)) {
            Object id = oauth.getPrincipal().getAttribute("id");
            if (!(id instanceof String || id instanceof Number)
                    || id.toString().isBlank()) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN);
            }
            return new ExternalIdentity("oauth2:lab-social",
                    id.toString());
        }

        throw new ResponseStatusException(HttpStatus.FORBIDDEN);
    }
}

@RestController
class ExternalIdentityController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/external/identity")
    Map<String, String> identity(Authentication authentication) {
        ExternalIdentity key = ExternalIdentityReader.from(authentication);
        // LAB ONLY: Không in raw external ID ở response sản phẩm thật.
        return Map.of("namespace", key.namespace(),
                "subject", key.subject());
    }
}

@Component
class SafeExternalFailureHandler implements AuthenticationFailureHandler {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeExternalFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        // Chỉ phân loại mã lỗi từ allowlist; KHÔNG log exception,
        // URL callback, authorization code, token hoặc raw error.
        String category = "PROVIDER_LOGIN_FAILED";
        if (exception instanceof OAuth2AuthenticationException oauthError
                && "access_denied".equals(
                        oauthError.getError().getErrorCode())) {
            category = "USER_DENIED_CONSENT";
        }

        LOG.warn("security_event={} category={}",
                "EXTERNAL_LOGIN_FAILURE", category);

        // Phản hồi chung, không lộ upstream error_description.
        response.sendRedirect(
                request.getContextPath() + "/login?external_error");
    }
}

// CHỈ mô phỏng unique ownership trong một process.
// KHÔNG wire phương thức link này trực tiếp vào HTTP endpoint!
final class AccountLinkRegistry {
    private final Map<ExternalIdentity, String> owners =
            new HashMap<>();

    synchronized LinkOutcome linkAfterBothProofs(
            String verifiedLocalAccountId,
            ExternalIdentity verifiedExternalIdentity) {
        if (verifiedLocalAccountId == null
                || verifiedLocalAccountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Verified local account required");
        }

        String current = owners.putIfAbsent(
                verifiedExternalIdentity, verifiedLocalAccountId);

        if (current == null) {
            return LinkOutcome.CREATED;
        }
        if (current.equals(verifiedLocalAccountId)) {
            return LinkOutcome.ALREADY_LINKED;
        }
        throw new AccountLinkConflictException();
    }

    synchronized String ownerOf(ExternalIdentity id) {
        return owners.get(id);
    }
}

enum LinkOutcome {
    CREATED, ALREADY_LINKED
}

class AccountLinkConflictException extends RuntimeException {
    AccountLinkConflictException() {
        super("External identity is already linked");
    }
}
~~~

**Đây là một file Java compile được khi project có dependencies đúng**, chỉ có một public top-level class `ExternalLoginApplication`. `AccountLinkRegistry` mô phỏng chỉ trong RAM, **không được gọi từ request có `verifiedLocalAccountId` do client khai báo**. Tên phương thức nhấn mạnh điều kiện tiên quyết, nhưng code demo **không tạo ra bằng chứng xác thực hai phía**. Trong production, một orchestrator đáng tin phải xác minh recent local login + fresh external callback/state trước khi gọi domain service; DB phải enforce unique constraint và transaction xuyên nhiều instance.

**Vì sao không làm một `POST /api/link?accountId=...` cho demo?** Endpoint như vậy rất dễ bị copy thành một lỗ hổng IDOR/account takeover. Domain link nên được test tách biệt; HTTP link thật cần cơ chế pending intent/session binding không thể mô phỏng an toàn chỉ bằng một tham số `accountId`.

### 7.3. Chạy demo

Với Gradle wrapper đã có:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

`GET http://localhost:8080/public` trả:

~~~text
public
~~~

`GET /oauth2/authorization/lab-oidc` tạo HTTP redirect hướng tới `https://issuer.lab.invalid/authorize` cùng các tham số `client_id`, `state`, `redirect_uri` v.v. Đây **chỉ là bắt đầu flow**; browser không thể hoàn thành thật vì issuer là domain giả. Trường hợp test `/api/external/identity` phải dùng Spring Security Test post-processors như phần 8, hoặc thay `.invalid` bằng môi trường IdP hợp lệ và có client secret do secret manager quản lý.

## 8. Tập kiểm thử JUnit + MockMvc: OIDC, OAuth2 và linking

Tạo `src/test/java/example/externallogin/ExternalLoginApplicationTest.java`:

~~~java
package example.externallogin;

import jakarta.servlet.http.HttpServletRequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ExternalLoginApplicationTest {

    @Autowired MockMvc mvc;
    @Autowired ClientRegistrationRepository registrations;

    private ClientRegistration oidc() {
        return registrations.findByRegistrationId("lab-oidc");
    }

    private ClientRegistration social() {
        return registrations.findByRegistrationId("lab-social");
    }

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void startsAuthorizationRedirectWithoutCallingProvider()
            throws Exception {
        mvc.perform(get("/oauth2/authorization/lab-oidc"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location",
                    containsString(
                            "https://issuer.lab.invalid/authorize")));
    }

    @Test
    void oidcPrincipalUsesIssuerAndSubject() throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oidcLogin()
                        .clientRegistration(oidc())
                        .idToken(token -> token
                                .issuer("https://issuer.lab.invalid")
                                .subject("subject-a")
                                .claim("email", "shared@example.test"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.namespace")
                    .value("https://issuer.lab.invalid"))
            .andExpect(jsonPath("$.subject").value("subject-a"));
    }

    @Test
    void sameEmailWithDifferentSubjectIsDifferentIdentity()
            throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oidcLogin()
                        .clientRegistration(oidc())
                        .idToken(token -> token
                                .issuer("https://issuer.lab.invalid")
                                .subject("subject-b")
                                .claim("email", "shared@example.test"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("subject-b"));
    }

    @Test
    void rejectsUnexpectedOidcIssuer() throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oidcLogin()
                        .clientRegistration(oidc())
                        .idToken(token -> token
                                .issuer("https://other.lab.invalid")
                                .subject("subject-a"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void nonOidcProviderUsesConfiguredStableId() throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oauth2Login()
                        .clientRegistration(social())
                        .attributes(attrs -> {
                            attrs.put("id", "social-5021");
                            attrs.put("email", "shared@example.test");
                        })))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.namespace")
                    .value("oauth2:lab-social"))
            .andExpect(jsonPath("$.subject").value("social-5021"));
    }

    @Test
    void localMockUserCannotImpersonateExternalIdentity()
            throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(user("local-user")))
            .andExpect(status().isForbidden());
    }

    @Test
    void sameExternalKeyCannotMoveToAnotherLocalAccount() {
        AccountLinkRegistry links = new AccountLinkRegistry();
        ExternalIdentity external =
                new ExternalIdentity("https://issuer.lab.invalid",
                        "subject-a");

        assertEquals(LinkOutcome.CREATED,
                links.linkAfterBothProofs("account-a", external));

        assertEquals(LinkOutcome.ALREADY_LINKED,
                links.linkAfterBothProofs("account-a", external));

        assertThrows(AccountLinkConflictException.class,
                () -> links.linkAfterBothProofs(
                        "account-b", external));

        assertEquals("account-a", links.ownerOf(external));
    }

    @Test
    void sameSubjectFromTwoIssuersIsNotSameLink() {
        AccountLinkRegistry links = new AccountLinkRegistry();
        ExternalIdentity a =
                new ExternalIdentity("https://issuer-a.test", "123");
        ExternalIdentity b =
                new ExternalIdentity("https://issuer-b.test", "123");

        assertEquals(LinkOutcome.CREATED,
                links.linkAfterBothProofs("account-a", a));
        assertEquals(LinkOutcome.CREATED,
                links.linkAfterBothProofs("account-b", b));
        assertEquals("account-a", links.ownerOf(a));
        assertEquals("account-b", links.ownerOf(b));
    }

    @Test
    void failedProviderLoginGetsGenericRedirect() throws Exception {
        SafeExternalFailureHandler handler =
                new SafeExternalFailureHandler();
        MockHttpServletRequest request =
                new MockHttpServletRequest();
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        // Error description cố ý chứa canary giả.
        OAuth2AuthenticationException failure =
                new OAuth2AuthenticationException(
                        new OAuth2Error(
                                "server_error",
                                "CANARY_NOT_TO_BE_SHOWN",
                                null));

        handler.onAuthenticationFailure(request, response, failure);

        assertEquals(302, response.getStatus());
        assertEquals("/login?external_error",
                response.getRedirectedUrl());
        assertFalse(response.getContentAsString()
                .contains("CANARY_NOT_TO_BE_SHOWN"));
    }
}
~~~

**Kỳ vọng:** 10 phương thức `@Test`, trong đó 7 ca qua MockMvc, 2 ca account-link domain, 1 ca custom provider failure handler. Toàn bộ đều chạy **offline** với registrations giả; chúng không khẳng định chương trình đã đăng nhập được vào IdP thực hay token chữ ký đã được xác minh.

Chạy bằng Gradle:

~~~bash
./gradlew test --tests example.externallogin.ExternalLoginApplicationTest
~~~

Kết quả kỳ vọng khi project có đúng dependencies và cấu hình là 10 test pass; mã ví dụ được soạn theo API Spring Security 6.5, nhưng không có kết quả build thực tế nào được tuyên bố ở đây. Nếu test fail, cần đọc root cause/test report thay vì vô hiệu hóa Security filter chain cho qua.

### 8.1. Tại sao dùng `oidcLogin().idToken(...)`?

Nó cho phép tạo những fixture có `iss`, `sub` và email do test kiểm soát:

~~~java
mvc.perform(get("/api/external/identity")
        .with(oidcLogin()
                .clientRegistration(oidc())
                .idToken(t -> t
                        .issuer("https://issuer.lab.invalid")
                        .subject("subject-a")
                        .claim("email", "student@example.test"))));
~~~

Đoạn này nằm trong method test có `MockMvc mvc` và method `oidc()` trả registration. Nó không thực hiện HTTP `/oauth2/authorization/...` hay callback `/login/oauth2/code/...`; Spring Test **chỉ cung cấp một principal** cho request hiện tại. Cơ chế mapping issuer/sub của controller được kiểm; còn verify JWS, issuer/audience và nonce cần tests ở tầng khác.

### 8.2. Vì sao có negative test issuer?

Ngay cả nếu app phụ thuộc vào framework OIDC validation, tầng mapping nên tránh chấp nhận nhầm một identity trong namespace ngoài allowlist. Test `rejectsUnexpectedOidcIssuer` sử dụng fixture giả có issuer không khớp để kiểm **defense-in-depth tại domain layer**.

**Nó không phải bài test chứng minh IdP thực đã phát một token chữ ký sai.** Vì `oidcLogin()` mock security principal, test đã bỏ qua hầu hết protocol validation; do đó negative test ở đây chỉ kiểm rule ở controller.

### 8.3. Vai trò của AccountLinkRegistry

Phương thức `linkAfterBothProofs(...)` mô phỏng invariant:

~~~text
external identity chưa có owner   → CREATED
external identity đã thuộc owner → ALREADY_LINKED
external identity thuộc user khác → CONFLICT
~~~

`synchronized` chỉ bảo đảm atomicity **trong một Java instance**. Một ứng dụng chạy nhiều server phải dùng DB transaction/unique index `(namespace, subject)` và xử lý xung đột insert; không dùng hai thao tác “SELECT rồi INSERT” không khóa làm nguồn duy nhất để chống race.

Test registry **không mô phỏng và không bảo đảm** bước xác minh local owner, session binding, OAuth2 state, recent-auth hoặc CSRF. Đây là **điều kiện đầu vào của service**; production chỉ gọi service khi một coordinator đáng tin đã kiểm tra đủ bằng chứng. Không thêm HTTP endpoint nhận thẳng `verifiedLocalAccountId` hoặc một boolean `isVerified` do client cung cấp.

### 8.4. Lỗi provider không đồng nghĩa lỗi mật khẩu

Trong OAuth2/OIDC, lỗi có thể do user từ chối consent, IdP downtime, token endpoint timeout, invalid client, state mismatch hoặc validation ID token thất bại. Không phải tất cả đều là “sai mật khẩu của người dùng”.

`SafeExternalFailureHandler` chỉ phân loại các lỗi đã biết, trả redirect chung. Không lấy raw `exception.getMessage()`, `OAuth2Error.getDescription()`, authorization code, access token hoặc callback URL để đưa vào response/log. Đừng ghi token và cả raw JWT claims khi debug.

**Điểm giới hạn:** unit test gọi handler trực tiếp nên chỉ chứng minh handler được gọi với exception thì trả response sạch. Nó **không** chứng minh mọi callback lỗi thật đều đến handler đó; cần integration test flow callback với IdP stub bên dưới.

## 9. Test provider thật bằng local IdP stub: cần kiểm tra những gì?

Một bài kiểm thử giao thức OAuth2/OIDC phải **khởi tạo request từ ứng dụng**, đi qua redirect và callback thực, có thể dùng một mock authorization server trong test environment với các endpoint:

~~~text
/.well-known/openid-configuration
/oauth2/authorize
/oauth2/token
/oauth2/jwks
/oauth2/userinfo
~~~

Địa chỉ thật và cấu trúc URL phụ thuộc framework giả IdP. Dùng `WireMock`, `MockWebServer`, một test OIDC provider container hoặc authorization server dành cho kiểm thử; **không** dùng URI `.invalid` từ demo rồi cho rằng token endpoint sẽ phản hồi.

Một test tối thiểu của **authorization code flow** phải xác minh:

1. `GET /oauth2/authorization/{registrationId}` trả redirect tới authorization endpoint đúng **nhà cung cấp đã tin cậy**.
2. Redirect có `client_id`, `redirect_uri`, `response_type=code`, `scope` và `state` ngẫu nhiên; PKCE challenge/nonce khi policy và chuẩn yêu cầu.
3. Server lưu authorization request/`state` trong repository phù hợp với session.
4. IdP test nhận code challenge, trả authorization code gắn đúng client/user/redirect/PKCE; không cho code reuse.
5. Callback `GET /login/oauth2/code/{registrationId}?code=...&state=...` được kiểm tra state, tương quan session, code được đổi tại token endpoint.
6. Token response chứa ID token hoặc access token đúng flow. Với OIDC, ID token có chữ ký hợp lệ, `iss`/`aud`/`exp`/`iat`/nonce phù hợp; JWK Set từ issuer tin cậy.
7. Với non-OIDC, userinfo API trả stable provider user ID; mapping namespace đúng.
8. Trước khi tạo local session/roles, ứng dụng áp account linking/status/policy; không auto-link chỉ dựa email.
9. Redirect sau login đưa browser tới trang an toàn; không open redirect.
10. Session context phục hồi được ở request tiếp theo, cookie flags phù hợp và local account đúng.

**Mọi API/OIDC mock principal test đã bỏ qua các bước 1–7**, nên phải đặt tên cho đúng: “controller mapping test”, không gọi “full OIDC security test”.

### 9.1. Negative protocol scenarios

| Mã | Sai hỏng mô phỏng tại provider/callback | Hành vi mong đợi |
| --- | --- | --- |
| R01 | Callback `state` thiếu | Từ chối, không tạo authenticated session |
| R02 | Callback `state` khác với request đã lưu | Từ chối, không accept callback |
| R03 | `state` của session A dùng với session B | Bị chặn, không liên kết nhầm user |
| R04 | Authorization code hết hạn hoặc đã đổi một lần | Token endpoint trả lỗi, không tạo session |
| R05 | Token endpoint HTTP 500/503 hoặc timeout | Generic failure, correlation ID; không ghi token/code |
| R06 | Token endpoint trả `invalid_client` | Không lộ client secret, không fallback sang client khác |
| R07 | Redirect URI sai hoặc client mismatch | Không cho callback/account binding tiếp tục |
| R08 | ID token chữ ký không hợp lệ hoặc `alg=none` ngoài policy | Reject, không lấy claims làm identity |
| R09 | ID token issuer khác configured issuer | Reject, không tự chọn JWK theo untrusted iss |
| R10 | ID token audience không chứa client ID hợp lệ | Reject |
| R11 | ID token `exp` đã quá hạn / `nbf` sai | Reject |
| R12 | OIDC nonce thiếu hoặc mismatch khi flow yêu cầu | Reject |
| R13 | JWKS endpoint timeout/rotation key | Xử lý cache/refresh theo chính sách; không “accept without verify” |
| R14 | UserInfo trả khác `sub` từ ID token (OIDC) | Reject theo OIDC consistency requirement |
| R15 | UserInfo chỉ có email không có stable ID | Không tự link/create privileged account |
| R16 | User từ chối consent: `error=access_denied` | Phản hồi chung; không tạo local login |
| R17 | IdP trả `error_description` chứa newline/secret | Không log/echo raw description |
| R18 | Provider trả cùng email cho hai `sub` khác nhau | Không gộp local account |
| R19 | Provider và tenant khác nhưng cùng `sub` | Không gộp external identities |
| R20 | Provider đổi email/name sau khi đã link | Binding vẫn theo stable ID, không bị relink |
| R21 | Two clients/sector identifiers, pairwise `sub` khác | Xử lý theo client/sector mapping đúng; không gán cưỡng ép |
| R22 | Provider login thành công nhưng local account disabled | Không tạo usable session |
| R23 | Lỗi DB khi ghi link sau callback | Transaction rollback, không login vào account sai |
| R24 | Hai request link đồng thời cùng identity | Unique constraint bảo đảm tối đa một owner |

### 9.2. Kiểm thử lỗi mạng không gây lộ bí mật

Với provider timeout hoặc HTTP 500:

- Chỉ log event code, endpoint category hoặc provider ID đã cấu hình, correlation ID; **không log** `authorization_code`, ID/access/refresh token, client secret, session ID, raw state.
- Không trả nguyên `OAuth2Error`/stack trace cho browser.
- Giới hạn retry; **không tự phát lại authorization code** sau khi token endpoint có kết quả không xác định, vì code là single-use.
- Khi issuer không truy cập được, không fallback sang xác minh “unsigned ID token” hoặc chấp nhận email theo body.
- Nếu muốn chuyển sang phương thức login khác, phải hiển thị lựa chọn an toàn; không tự động bypass MFA hoặc account-link verification.
- Có monitoring cho outage rate, provider latency và login failure category, nhưng không đưa user attributes/secret vào metric tags.

## 10. Kiểm thử liên kết nhiều provider và chống IDOR

### 10.1. Local identity và external identity là hai namespace

~~~text
local account #123
     │
     ├─ OIDC issuer A / sub xyz
     │
     └─ OAuth2 provider B / user id 5021

local account #456
     └─ OIDC issuer A / sub abc
~~~

Local account ID là định danh nghiệp vụ do ứng dụng tạo, **không lấy từ `sub`, email hay session ID của IdP**. Khi user đăng nhập lại qua một trong các link, app tìm mapping trong `EXTERNAL_ACCOUNT_LINK` rồi load local user/roles.

Nếu hệ thống có nhiều tenants, cần chặn cross-tenant linking ngay cả khi issuer/subject hợp lệ về mặt kỹ thuật; có thể namespace theo tenant khi đó là mô hình danh tính thực sự khác. Không tự đưa tenant client gửi vào SQL mapping mà không xác thực từ session/ủy quyền.

### 10.2. Link thêm provider cần *fresh external proof*

Một user đang logged-in vào account #123 không thể chỉ nhập “external user ID của tôi là xyz” rồi được link. Người đó phải đi qua **fresh provider authorization flow** (hoặc một bằng chứng phù hợp được thiết kế/verified server-side). Nếu attacker biết `sub` của nạn nhân từ log/URL, việc gửi `sub` tùy ý không thể tạo quyền điều khiển external identity.

### 10.3. Local proof và “confused deputy”

Nếu người dùng click “Link Microsoft” nhưng session local đã expired giữa chừng, callback có thể xảy ra sau khi người dùng khác đăng nhập vào cùng browser. **Không được gắn identity callback vào account hiện có lúc callback một cách mù quáng**. Phải lưu pending intent gắn đúng account, session và thời hạn ở lúc khởi tạo, so lại khi callback.

Tình huống cần test:

~~~text
session A, local owner=account-123 → begin link, state=S
session A expires
session B, local owner=account-456 → callback with state=S

Expected: reject, NOT link external user to account-456.
~~~

Khi vừa hỗ trợ “login by external identity” vừa hỗ trợ “link external identity vào account đã login”, cần phân biệt `operation=LOGIN` và `operation=LINK` trong trusted server state. Nếu không, một callback login bình thường có thể vô tình liên kết danh tính vào account người dùng khác.

### 10.4. Unlink và recovery

Unlink phải yêu cầu current local user owner và step-up khi cần; không cho user A gỡ link của B bằng cách gửi `linkId` của B. Sau unlink:

- External identity không còn truy cập local account qua mapping đó.
- Các local sessions/tokens đã cấp trước có thể vẫn còn hiệu lực; có chính sách thu hồi riêng.
- Có thể cần revoke OAuth2 authorized client của app; unlink một mapping local **không tự sign out mọi IdP session**.
- Phải đảm bảo ít nhất một phương thức đăng nhập/khôi phục còn hoạt động hoặc thực hiện recovery flow đáng tin.
- Audit hành động mà không lưu access token/client secret/authorization code.

## 11. HTTP errors, account conflicts và phản hồi UX

Phân loại đúng lỗi để người dùng và QA biết điều gì đã hỏng:

| Nhóm | Ví dụ | UX / HTTP gợi ý |
| --- | --- | --- |
| User từ chối consent | `access_denied` | “Bạn đã hủy đăng nhập bằng nhà cung cấp.”; vẫn không tạo session |
| IdP timeout/maintenance | `server_error`, HTTP 5xx, timeout | Thông báo tạm thời, cho phép thử lại flow mới, không reuse code |
| Callback hỏng state/nonce | CSRF/response injection | Không đăng nhập; thông báo chung và audit security event |
| Token không hợp lệ | Bad signature, issuer, audience, expiry | Từ chối; không giải mã rồi tin claims |
| UserInfo thiếu stable ID | Provider API thay đổi | Không liên kết; thông báo sự cố provider, không auto match email |
| External identity thuộc account khác | UNIQUE conflict | Không chuyển owner; yêu cầu hỗ trợ/owner verification |
| Local account disabled/locked | Local account policy | Không tạo local session dù IdP authenticated |
| Local user thiếu role/tenant | Authorization | Có thể 403 ở protected resource, không đồng nhất với OIDC invalid token |
| Session/link pending expired | Timeout link intent | Bắt đầu lại thao tác xác minh, không dùng lại state |
| Database outage trong linking | Transaction không hoàn tất | Không báo liên kết thành công; retry an toàn theo idempotency |
| Client registration sai redirectURI | Misconfiguration | Báo lỗi cấu hình tổng quát; xem audit nội bộ sanitized |

**Không lấy raw provider error description làm HTTP body hoặc log.** Một nhà cung cấp/trang callback có thể đưa chuỗi ngoài ý muốn chứa PII, token, newline hoặc markup. Hãy ánh xạ lỗi thành **mã nội bộ hữu hạn**, ví dụ `PROVIDER_UNAVAILABLE`, `EXTERNAL_LOGIN_FAILED`, `LINK_CONFLICT`, `LINK_INTENT_EXPIRED`, và trả correlation ID do server sinh.

### Login error không phải password error

Trong OAuth2 login, người dùng thường không nhập password của IdP vào ứng dụng RP. RP không nên trả “Sai mật khẩu Google/Microsoft” khi IdP từ chối request vì consent, state, client config, mạng, MFA hoặc token. Việc phân biệt nguyên nhân nội bộ cần dựa vào provider error category có trust boundary rõ, không phán đoán từ chuỗi message.

## 12. Tính nhất quán lưu trữ trong production

### 12.1. Database UNIQUE là điều kiện bắt buộc

Một DDL **minh họa logic** (cần điều chỉnh dialect và migrations thực tế):

~~~sql
CREATE TABLE external_account_link (
    link_id            VARCHAR(36) PRIMARY KEY,
    local_account_id   VARCHAR(36) NOT NULL,
    issuer_namespace   VARCHAR(255) NOT NULL,
    external_subject   VARCHAR(255) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    UNIQUE (issuer_namespace, external_subject)
);

CREATE INDEX idx_link_by_local_account
    ON external_account_link(local_account_id);
~~~

Cần thêm foreign key `local_account_id` tới bảng account thật, cột audit/soft deletion nếu có, handling length/collation và chính sách PII. Không dùng `ON CONFLICT DO UPDATE SET local_account_id = EXCLUDED.local_account_id` để “thắng race”: đó là cách chuyển ownership không có bằng chứng.

Nếu dùng soft-delete, phải thiết kế unique constraint cho active links phù hợp dialect, tránh tình huống hai hàng “active” cùng key hoặc tái liên kết khi identity đang bị tranh chấp.

### 12.2. Race và idempotency

Một cách làm **sai**:

~~~text
Request A: SELECT key -> absent
Request B: SELECT key -> absent
Request A: INSERT key → account-1
Request B: INSERT key → account-2
~~~

Nếu chỉ kiểm ở code, hai requests có thể cùng vượt qua. Unique constraint làm một insert thất bại; server phải chuyển thành **LINK_CONFLICT** hoặc idempotent result nếu cùng owner. Nếu dùng `SERIALIZABLE`/lock, vẫn cần xử lý retry và deadlock hợp lý. Ghi audit phải xảy ra sau trạng thái transaction thực sự được commit.

### 12.3. Thay đổi mapping/merge tài khoản

Khi người dùng merge hai local accounts, không tự động chuyển mọi external identity chỉ vì email giống. Quy trình có thể cần xác minh quyền cả hai local accounts, chống session confusion, kiểm active link conflicts, transaction/approval/audit và kế hoạch rollback. Với hệ B2B, một external identity có thể thuộc tenant khác dù email giống; phải có chính sách liên kết theo tenant.

## 13. Ma trận kiểm thử end-to-end

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| E01 | OIDC issuer/sub hợp lệ, đã link local A | Local account A |
| E02 | Cùng issuer, khác sub, email trùng local A | **Không tự link A** |
| E03 | Khác issuer, cùng sub | Hai external identities khác nhau |
| E04 | Non-OIDC provider stable ID hợp lệ | Resolve đúng provider namespace |
| E05 | Non-OIDC thiếu attribute stable ID | Reject, không fallback sang email |
| E06 | Unknown registrationId | Reject/không map ngầm |
| E07 | ID token issuer không match configured issuer | Reject |
| E08 | ID token audience/client ID sai | Reject |
| E09 | JWT chữ ký sai/JWK không tin cậy | Reject |
| E10 | ID token hết hạn/nonce sai | Reject |
| E11 | Callback thiếu/sai state | Reject, không tạo session |
| E12 | State của session A gửi tại session B | Reject |
| E13 | User từ chối consent | Generic failure, không tạo local session |
| E14 | IdP timeout hoặc 5xx | Không login, không leak token/client secret |
| E15 | Provider lỗi token exchange | Không reuse authorization code, audit category |
| E16 | Provider thay email nhưng giữ stable ID | Binding không đổi |
| E17 | Provider có `email_verified=false` | Không auto link email |
| E18 | Identity đã link A bị yêu cầu link vào B | Conflict, owner vẫn A |
| E19 | A link cùng identity lần hai | Idempotent |
| E20 | A đang link, session local hết hạn | Reject callback, không link vào user khác |
| E21 | Hai link cùng external ID đồng thời | Unique DB: tối đa một owner |
| E22 | User A cố unlink link thuộc B | Reject IDOR |
| E23 | User unlink login method cuối | Policy từ chối hoặc bắt buộc recovery |
| E24 | Local account locked, IdP auth success | Không tạo usable local login |
| E25 | MockMvc `oidcLogin()` pass nhưng integration ID token invalid | Hai test ở hai tầng phải được báo khác nhau |
| E26 | OAuth2 callback success handler throw | Không báo hoàn tất local session thiếu kiểm tra |
| E27 | Redirect URL không tin cậy | Không open redirect, không leak authorization code |
| E28 | Server lưu authorized client nhưng DB link chưa commit | Không tuyên bố local account linked |
| E29 | IdP liên tục timeout | Throttling/circuit breaker hợp lý, không fallback insecure |
| E30 | Thử lại sau provider outage | Tạo flow/state/code mới, kết quả idempotent |
| E31 | Pairwise subject khác giữa hai OIDC client | Không ép coi như cùng một account nếu chưa có quy tắc IdP |
| E32 | Token/provider claims xuất hiện trong log | Bị chặn bởi security canary/log redaction policy |

Những test này bao phủ cả unit, MockMvc, protocol integration, concurrency và E2E. Mỗi tầng có giá trị khác nhau; một test mock principal PASS **không thay thế** test issuer signature/nonce thật.

## 14. Lỗi thường gặp khi viết test OAuth2/OIDC linking

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Test bằng `@WithMockUser` nhưng controller yêu cầu `OidcUser` | Không mô phỏng đúng principal/OIDC claims | Dùng `oidcLogin()` và ID token fixture |
| Gọi `oauth2Login()` rồi khẳng định token signature valid | Bỏ qua cryptographic verification | Dùng local IdP/stub + callback thật |
| Dùng email làm key trong bảng link | Dễ gộp account không liên quan | OIDC: `iss+sub`; non-OIDC: trusted provider ID |
| Dùng `sub` một mình cho hai issuer | Collision cross-provider | Thêm issuer namespace |
| Cho client gửi `accountId` trong link request | IDOR/account takeover | Lấy owner từ verified local session |
| Đổi owner bằng UPDATE vô điều kiện | Chiếm account trong race | UNIQUE + conflict/approval |
| Không ràng pending state với local session | Callback gắn nhầm owner | Signed/server-side intent, state/session binding |
| Không kiểm expired intent | Replay/link sau khi người dùng bỏ dở | TTL và single-use intent |
| Gửi raw provider error về UI/log | Rò client secret/token/PII và log injection | Whitelist code, generic response |
| Mock userInfo/email mà không có stable id | Không biết ai là user thật | Require stable immutable provider ID |
| Tắt CSRF cho link/unlink cookie session | Cross-site action | Giữ CSRF, recent-auth/step-up |
| Tắt toàn bộ login khi IdP down | Không có recovery/backup auth policy | Thiết kế fallback an toàn, không bỏ qua verification |
| Dùng URI thật trong unit tests có mạng | Test chậm/flaky, secret leak | Local stub/`.invalid` fixture, test provider contract tách biệt |
| Đếm “oauth2Login mock passed” như full login E2E | Bỏ qua state/nonce/aud/iss và browser session | Báo rõ test tier, có integration |
| Dùng một in-memory HashMap trên 3 node | Link race và mất dữ liệu khi restart | Database transaction + UNIQUE |
| Lưu raw ID/access/refresh token vào account link table | Không cần thiết, tăng blast radius | Lưu minimal stable identity và authorized client riêng |
| Test bằng provider thật với email cá nhân | Dữ liệu nhạy cảm và không tái lập | Dedicated test accounts/fixtures, secrets manager |

## 15. Checklist nghiệm thu

- [ ] Xác định rõ issuer/provider namespace và stable subject; OIDC dùng `iss+sub`.
- [ ] Không auto-link chỉ vì email/username/displayName trùng.
- [ ] Có local account ID riêng và DB UNIQUE(namespace,subject), tránh cross-tenant confusion.
- [ ] Link yêu cầu recent local proof + fresh external proof, pending intent và state/session binding.
- [ ] Không nhận account ID, issuer, subject client gửi như chứng cứ đã verify.
- [ ] Mô phỏng provider/OIDC và non-OIDC riêng bằng `oidcLogin()`/`oauth2Login()`.
- [ ] Đảm bảo MockMvc có Spring Security filters; không đánh đồng `@WithMockUser` với OIDC.
- [ ] Có tests cross-issuer, same-email/different-sub, conflict, idempotency, missing ID.
- [ ] Có test lỗi nhà cung cấp qua handler (response/log không leak) và callback thật qua local IdP.
- [ ] Protocol integration xác minh state, code, PKCE/nonce, issuer, audience, signature, expiry, UserInfo stable ID.
- [ ] Có test IdP outage, timeout, invalid client, user denied consent, rotating keys.
- [ ] Local account status, MFA, roles và session được áp sau xác thực IdP; không cấp quyền chỉ vì OIDC success.
- [ ] Link/unlink có CSRF, step-up, audit và không tự khóa account khi method cuối bị gỡ.
- [ ] Race/concurrent linking được DB xử lý atomic, không chỉ synchronized Map.
- [ ] Secret/token/code/client secret không đi vào log, trace, metrics hay error response.
- [ ] Có kế hoạch recovery, provider migration, pairwise-sub, account merge và monitoring.

## 16. Tài liệu tham khảo

- [Spring Security 6.5 — Testing OAuth 2.0 / OIDC with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html)
- [Spring Security 6.5 — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html)
- [Spring Security 6.5 — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html)
- [Spring Security 6.5 — OAuth2 LoginConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/client/OAuth2LoginConfigurer.html)
- [Spring Security 6.5 — OidcUser API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security 6.5 — OAuth2AuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html)
- [Spring Security 6.5 — OIDC Test Request PostProcessor](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Security 6.5 — ClientRegistration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html)
- [OpenID Connect Core — Claim Stability and Uniqueness (`5.7)](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
