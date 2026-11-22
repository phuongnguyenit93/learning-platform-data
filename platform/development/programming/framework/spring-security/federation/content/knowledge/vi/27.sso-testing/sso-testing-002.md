# Kiểm thử nhiều ứng dụng dùng chung IdP và phiên đăng nhập

> **Module:** Spring Security – federation · **Chủ đề cha:** Kiểm thử SSO. Bài Knowledge này trình bày cách kiểm thử **Single Sign-On (SSO) liên ứng dụng** khi ứng dụng A và ứng dụng B cùng sử dụng một Identity Provider (IdP), nhưng vẫn có **phiên HTTP cục bộ, client registration, token audience và quyền nghiệp vụ riêng**. Nội dung tập trung vào Spring Security OIDC Authorization Code, browser E2E, session isolation, các kịch bản logout và đối chiếu với SAML2/CAS. Kiểm thử SSO không thể chỉ là hai request `MockMvc.with(oidcLogin())` thành công.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Vẽ đúng quan hệ **IdP session**, **local session A**, **local session B**, cookie/browser context, authorization code và ID Token audience.
2. Giải thích tại sao dùng chung IdP **không có nghĩa** hai ứng dụng dùng chung `JSESSIONID`, `SecurityContext`, access token, refresh token hay local authorities.
3. Cấu hình hai OIDC clients `client-A` và `client-B` với cùng trusted issuer nhưng client IDs, secrets, redirect URIs và session cookies tách biệt.
4. Dựng hai instances Spring Boot từ một codebase, chạy sau HTTPS proxy với hai hostnames để loại bỏ false positive do cookie `localhost`.
5. Thiết kế browser test trong **một browser context duy nhất** để kiểm chứng A login tương tác, B reuse phiên tại IdP mà không có ceremony nhập credential mới.
6. Phân biệt số **authorization requests**, số **authorization code token exchanges** và số **interactive IdP authentication ceremonies**.
7. Kiểm tra identity/tenant/roles độc lập, chú ý OIDC `sub` có thể **pairwise** theo client/sector, không mặc định `sub_A == sub_B`.
8. Dùng `prompt=none`, `prompt=login`, `max_age`, `auth_time` và `acr`/`amr` đúng contract; hiểu khi nào IdP phải hỏi lại consent/MFA/reauthentication.
9. Phân biệt logout local A, OP session expiration, RP-Initiated Logout và front-/back-channel Single Logout có hoặc không có delivery.
10. Biết ý nghĩa các trường `iss`, `aud`, `sid`/`sub`, `jti` và `events` của OIDC Back-Channel Logout Token, không nhầm nó với ID Token hay Servlet session ID.
11. Dùng Spring Security Test `oidcLogin()` cho controller/authorization một app, nhưng không coi là chứng cứ SSO hai apps.
12. Chạy chương trình Java 17 offline có stdout xác định để phân biệt hai local sessions, IdP session, logout và browser profile isolation.
13. Thiết kế signed fixture tests/IdP test E2E, negative tests và chaos tests cho SAML2, CAS, cookie SameSite, IdP outage, key rotation và mạng.
14. Ghi nhận log/metrics an toàn, lập ma trận acceptance và runbook chẩn đoán SSO thất bại.

**Nền tảng:** Java 17, Spring Boot 3.3.x/Spring Security 6.3.x dùng làm ví dụ học tập; trước production phải chọn phiên bản còn nhận security patches. URLs `a.example.test`, `b.example.test`, `idp.example.test` là minh họa, không có DNS/HTTPS hoặc IdP chạy sẵn. Các snippets có ghi *mảnh kiểm thử* cần test infrastructure; chỉ ví dụ Java 17 độc lập có thể chạy ngay mà không cần dịch vụ ngoài.

## 2. Mô hình: một IdP, ba phiên độc lập

~~~text
                      +--------------------------+
                      |  OP / IdP                 |
                      |  idp.example.test         |
                      |  central SSO session      |
                      |  cookie IDP_SESSION       |
                      +-------------+------------+
                                    |
                           browser redirects
                         +----------+----------+
                         |                     |
          +--------------v------------+  +-----v-------------------+
          | App A: a.example.test     |  | App B: b.example.test  |
          | client_id=client-A        |  | client_id=client-B     |
          | cookie APP_A_SESSION      |  | cookie APP_B_SESSION   |
          | local app session A       |  | local app session B    |
          | APP_ORDER_READ            |  | APP_REPORT_READ        |
          +---------------------------+  +-------------------------+
~~~

Alice mở A:
1. Browser chưa có phiên A → A bắt đầu OAuth2/OIDC authorization request với `client_id=client-A`.
2. Browser đến IdP, user đăng nhập/MFA theo policy. IdP tạo **SSO session** của chính IdP trên browser.
3. IdP chuyển một **authorization code dành cho A** về callback A. A đổi code qua token endpoint, xác minh ID Token và tạo **HTTP session riêng ở A**.
4. Alice mở B trong **cùng browser context**. Browser chưa có phiên B → B bắt đầu **authorization request mới**, lần này `client_id=client-B`.
5. Browser được chuyển đến IdP. Nếu IdP session vẫn hợp lệ, consent/assurance của B đủ và chính sách không bắt reauthentication, IdP cấp code cho B **không yêu cầu nhập lại mật khẩu**.
6. B xác minh ID Token dành cho **audience B**, tạo local session riêng.
7. A/B có thể xử lý request tiếp theo bằng local sessions mà không liên tục gọi IdP.

### 2.1. Bảng trạng thái sau SSO

| Thành phần | Cơ quan sở hữu | Trạng thái sau login A+B | Phạm vi |
| --- | --- | --- | --- |
| OP/IdP session | IdP | ACTIVE | Thường browser/IdP-specific. |
| A HttpSession | A/container/session store A | ACTIVE | Chỉ A. |
| B HttpSession | B/container/session store B | ACTIVE | Chỉ B. |
| ID Token A | IdP cấp, A kiểm chứng | `aud=client-A` | Không dùng làm ID Token B. |
| ID Token B | IdP cấp, B kiểm chứng | `aud=client-B` | Không dùng làm ID Token A. |
| Authorization Code A | OP cấp cho client A | Đã tiêu thụ một lần | Không được chuyển sang B. |
| Authorization Code B | OP cấp cho client B | Đã tiêu thụ một lần | Không được chuyển sang A. |
| Local role A | A/local authorization store | `APP_ORDER_READ` | Không tự chuyển sang B. |
| Local role B | B/local authorization store | `APP_REPORT_READ` | Không tự chuyển sang A. |

**Một lần đăng nhập** thường nghĩa **một ceremony tương tác tại IdP**, **không phải** chỉ có một authorization request. Dù người dùng không thấy form login ở B, OP vẫn có thể nhận request authorize cho B rồi cấp code/token mới.

### 2.2. Cookie jar của browser

~~~text
idp.example.test -> IDP_SESSION=op-1
a.example.test   -> APP_A_SESSION=a-71
b.example.test   -> APP_B_SESSION=b-29
~~~

Cookie host-only của A không tự được gửi cho B, và cookie host-only của IdP cũng không được copy thành cookie A/B. **Port không nằm trong cookie origin scope**: thử hai apps ở `localhost:8081`/`localhost:8082` với cùng `JSESSIONID` có thể gây collision. Test E2E đáng tin nên dùng **hai hostnames** qua TLS proxy, không tạo SSO bằng cách đặt `Domain=.example.test` cho app session cookie.

### 2.3. Phân biệt SSO với shared application session

Sai lầm:
- Copy cookie `JSESSIONID` A vào B rồi test B trả 200.
- Config Spring Session Redis A/B dùng cùng namespace và vô tình share SecurityContext.
- Cho B tin ID Token hoặc access token `aud=client-A`.
- Tạo sẵn session B trước khi mở B, rồi kết luận IdP reuse session.
- Đặt tất cả endpoints `permitAll`, nhìn HTTP 200 và báo PASS.

Đúng: B phải có **một authentication flow của client B** được protocol verifier xử lý rồi mới tạo B session, trong khi **IdP session từ A** giúp không hỏi lại credential nếu policy phù hợp.

## 3. Môi trường kiểm thử E2E chuẩn

| Nơi | URL giả lập | Khóa kiểm tra |
| --- | --- | --- |
| IdP sandbox | `https://idp.example.test/realms/workforce` | OIDC Discovery, JWKS, test user và cookie session thật. |
| Ứng dụng A | `https://a.example.test` | Registered client-A, callback A, cookie A. |
| Ứng dụng B | `https://b.example.test` | Registered client-B, callback B, cookie B. |
| Callback A | `https://a.example.test/login/oauth2/code/central` | Chính xác trong allowed redirect URIs của A. |
| Callback B | `https://b.example.test/login/oauth2/code/central` | Chính xác trong allowed redirect URIs của B. |
| OIDC test user | `alice-test` | Active, assurance policy định nghĩa rõ. |
| Browser mới | Cookie storage trống | Không thừa hưởng IdP/A/B session từ lần test trước. |
| Browser thứ hai | Separate profile/context | Không dùng để chứng minh cookie sharing, chỉ test isolation. |

Có thể dùng Keycloak test realm hoặc IdP sandbox khác với:
- Hai client registrations độc lập, hai redirect URIs và logout URLs tách biệt.
- SSO session thật, chính sách consent/remember-me/MFA được ghi rõ.
- Audit event phân biệt **interactive authentication** và authorization request dùng existing session.
- Signing keys/certificates test và HTTPS trust, không dùng secrets production.
- Khả năng reset sessions giữa các test, quản lý test data và test user disable/revoke.
- Nếu định kiểm tra Back-Channel Logout, OP và cả hai RPs phải hỗ trợ/đăng ký endpoints, signature validation và session mapping.

### 3.1. Không dùng “test IdP” chỉ trả JSON đã mock

Một mock `GET /authorize` giả lập HTTP 302 và token endpoint trả ID Token cố định có thể test một client flow, nhưng **không tự chứng minh shared IdP browser cookie/SSO**. Test nhiều ứng dụng phải có user-agent và IdP có thực thi session reuse/consent/reauthentication policies.

### 3.2. Thực thi trong CI

- Mỗi CI run có namespace users/clients/ports hoặc sandbox isolated.
- Tạo user test, inject credential qua secret manager; không hard-code password/MFA seed vào Git.
- Không giữ Selenium/Playwright persisted profile giữa các test nếu không cố ý test persistence.
- Dùng HTTPS với cert/trust đúng cho browser; không tắt TLS verification trong production.
- Pin browser/driver/IdP versions tương thích, lưu audit event IDs đã ẩn danh, không lưu cookies/tokens.
- Thiết lập cơ chế chờ trạng thái thay vì `Thread.sleep(...)` quá rộng; những đổi hướng OIDC có latency.
- Cleanup local sessions, IdP sessions và test users sau mỗi scenario, không chỉ đóng tab.

## 4. Kịch bản happy path: A login, B dùng lại IdP session

### 4.1. Trình tự

~~~text
Browser context FRESH
    |
    | GET https://a.example.test/me
    v
App A -> IdP authorize (client-A, state_A, nonce_A, PKCE_A)
    |
    | IdP login user Alice (interactive)
    | IdP browser session OP-1 established
    v
IdP -> A callback with code_A/state_A
    |
    | A validates state/nonce/iss/aud/signature/time
    | A creates local session A-71
    v
GET /me at A -> 200, app=A, authenticated=true

SAME browser context:
    |
    | GET https://b.example.test/me
    v
App B -> IdP authorize (client-B, state_B, nonce_B, PKCE_B)
    |
    | Browser sends OP-1 IdP cookie
    | OP policy allows reuse: no new credential prompt
    v
IdP -> B callback with code_B/state_B
    |
    | B verifies token audience client-B, local identity
    | B creates local session B-29
    v
GET /me at B -> 200, app=B, authenticated=true
~~~

### 4.2. Điều kiện QA PASS

1. Trước A, không có app A session, B session hay OP browser cookie.
2. A bắt đầu đúng `client-A` flow, đã hoàn tất một **interactive IdP authentication ceremony**.
3. A ID Token `aud` đúng A, local session A được tạo sau validation.
4. Trước B, B **chưa có** local session.
5. B bắt đầu **authorization request B**, có `state_B`, `nonce_B`, PKCE/code exchange B riêng.
6. B dùng lại OP browser session và **không có credential ceremony thứ hai** trong policy không yêu cầu step-up/consent.
7. B ID Token `aud` đúng B, B session được tạo, B authorization độc lập.
8. Reload A/B không tự đi qua flow mới khi local session còn hiệu lực.
9. Cookie A và B là host-only và không bị ghi đè, OP cookie thuộc IdP.
10. IdP audit xác nhận một interactive sign-in, dù có **hai authorization requests**.

**Không chỉ kiểm tra** A và B đều HTTP 200; local session leak hay controller permitAll cũng có thể tạo false positive.

### 4.3. Tự động hóa bằng Selenium (mảnh minh họa)

Đoạn này cần Selenium 4, JUnit 5, ChromeDriver, reverse proxy/IdP test thật và test fixture để hoàn tất login. **Không phải tệp Java chạy độc lập**, khác `MultiAppSsoSessionDemo` ở mục 11.

~~~java
// MẢNH kiểm thử E2E trong JUnit + Selenium:
WebDriver browser = new ChromeDriver();
try {
    browser.get("https://a.example.test/me");

    // Helper phụ thuộc IdP test; không hard-code password thật.
    completeInteractiveLoginAtTestIdp(
        browser, testCredentialsFromVault
    );

    WebDriverWait wait = new WebDriverWait(
        browser, Duration.ofSeconds(20)
    );
    wait.until(ExpectedConditions.urlContains("a.example.test"));

    // Parse response JSON/đọc test instrumentation để assert
    // app A authenticated. Đừng chỉ dựa URL hoặc source text.
    assertEquals("A", readAppIdFromCurrentResponse(browser));

    // REUSE cùng WebDriver/cookie jar cho B.
    browser.get("https://b.example.test/me");
    wait.until(ExpectedConditions.urlContains("b.example.test"));
    assertEquals("B", readAppIdFromCurrentResponse(browser));

    // Instrumented test IdP: có 2 authorization requests
    // nhưng chỉ 1 interactive credential ceremony.
    assertEquals(2, testIdpAudit.authorizationRequests());
    assertEquals(1, testIdpAudit.interactiveLogins());
} finally {
    browser.quit();
}
~~~

Các hàm `completeInteractiveLoginAtTestIdp`, `readAppIdFromCurrentResponse`, `testIdpAudit` là **test harness phụ thuộc sandbox**, phải được implement thật; không coi snippet trên là executable standalone. Selenium/Playwright chạy với browser thật nhưng các kết quả vẫn cần kiểm tra server-side audit, không lấy screenshot thay authentication proof.

### 4.4. Hai browser profiles riêng

Để test isolation, mở profile mới `browser-private` **không có OP cookie**:
- Vào B: phải bắt đầu login/identity selection theo policy, không tự thừa hưởng Alice từ profile work.
- Nếu thiết bị có IWA/Kerberos/passkey auto authentication, IdP có thể đăng nhập lại nhanh **nhưng đã dùng một phương thức khác**, cần tách khỏi phép thử cookie SSO.
- Không dùng browser profile khác cho bước B trong **happy path SSO** vì nó chủ động phá điều kiện browser cookie sharing.
- Browser tabs trong **cùng profile** thường share cookie jar; không nhất thiết share in-memory JS state/localStorage nếu origin khác.

## 5. Kiểm tra IdP thực sự đã tái sử dụng phiên

**Trình duyệt không hiện form đăng nhập** là tín hiệu chưa đủ: password manager/passkey/Windows IWA có thể tự xác thực lại, hoặc browser còn local session B từ test khác.

Ưu tiên:
- Audit IdP có event authentication thành công **interactive** riêng event authorize/token issuance.
- IdP OP session ID/ref nội bộ cho cùng browser được ghi nhận theo privacy policy.
- A/B audit callback riêng `client_id` và generation của local session.
- `auth_time` từ validated ID Tokens làm tín hiệu hỗ trợ, không bắt buộc bằng nhau trong mọi profile/IdP policy và không thay log interactive flow.
- B đang có local session hay chưa trước request.
- Các cookies được scoped đúng host, không lộ cookie raw value.

### 5.1. Những số đếm không đồng nhất

~~~text
authorization_requests  = 2   (A và B)
authorization_codes     = 2   (code_A, code_B)
token_exchanges         = 2   (mỗi client đổi code của mình)
interactive_logins      = 1   (nếu OP session reuse được)
local_sessions_created  = 2   (A và B)
~~~

Nếu `interactive_logins=2`, cần xem B yêu cầu reauthentication/consent/step-up có chủ đích hay OP cookie không được gửi. Nếu `authorization_requests=1` nhưng B login thành công “ngay” khi B chưa có local session, phải xem có bypass/accidental session sharing.

### 5.2. Không bắt buộc sub của A và B bằng nhau

OIDC hỗ trợ **pairwise subject identifier**: cùng người có thể được IdP cấp `sub_A` và `sub_B` khác nhau theo sector/client. Identity linking tới local accounts phải dựa **issuer + subject đã được xác minh và approved mapping**, hoặc authoritative directory crosswalk, không so raw `sub` giữa clients như một khẳng định SSO.

Email trùng hay `email_verified=true` cũng không chứng minh A/B là cùng local user; khi test hai clients nên xác nhận đúng user bằng IdP test audit và trusted provisioning IDs, không bằng email duy nhất.

## 6. OIDC prompt=none, prompt=login, max_age và auth_time

### 6.1. `prompt=none`

Khi RP gửi authorize request với `prompt=none`, OP **không được tương tác UI**. Nếu không thể đáp ứng, OP trả error thích hợp như `login_required`, `interaction_required`, `consent_required` hoặc `account_selection_required`.

| Điều kiện OP | Kỳ vọng |
| --- | --- |
| Session còn và B không cần consent/step-up | Có thể hoàn tất silent authorization. |
| Session IdP đã hết hạn/chưa có | `login_required`, không cấp local B session. |
| Consent của client B chưa được cấp | `consent_required` hoặc error tương đương. |
| B yêu cầu MFA mới | `interaction_required` khi prompt none, cần interactive flow. |
| Nhiều IdP accounts, phải chọn | `account_selection_required` khi cần. |
| Iframe silent auth bị chặn third-party cookie | Có thể fail dù top-level redirect SSO bình thường. |

Không dùng `prompt=none` để bypass password/MFA. Đây chỉ là yêu cầu IdP tận dụng **phiên xác thực hợp lệ đang có**, hoặc **từ chối** khi thiếu bằng chứng.

### 6.2. `prompt=login` và `max_age`

`prompt=login` yêu cầu OP xác thực lại. `max_age` quy định độ cũ tối đa của authentication; khi yêu cầu, client cần kiểm tra `auth_time` được trả theo OIDC. `max_age=0` thường yêu cầu authentication mới theo profile; không tự đảm bảo MFA nếu IdP chỉ hỏi password.

**Bài test:** A có OP session từ trước, B yêu cầu `max_age=300` hoặc ACR mạnh hơn. B có thể hiển thị step-up/password/MFA. Đó **không nhất thiết là SSO FAIL**: test cần đối chiếu B policy và đảm bảo không hạ chuẩn chỉ để đạt “no second prompt”.

### 6.3. `iat` không phải `auth_time`

Một ID Token cấp mới cho B có thể có `iat` hiện tại trong khi `auth_time` phản ánh lần xác thực trước ở A. Không dùng thời điểm B session được tạo hoặc ID Token issued time làm bằng chứng user vừa thực hiện MFA.

### 6.4. Third-party cookies và iframe

Top-level redirect tới IdP khác cơ chế hidden iframe silent authentication. Browser có thể chặn third-party cookies trong iframe, khiến `prompt=none` thất bại, trong khi redirect tới IdP như trang chính vẫn SSO được. Test phải ghi loại user-agent/browser settings, không kết luận chính sách IdP sai chỉ vì iframe fail.

## 7. Spring Boot: hai ứng dụng từ cùng một codebase

Dự án sau minh họa **hai OIDC Relying Parties** có thể chạy từ cùng source với env vars khác nhau. Từng app có client ID và cookie riêng. IdP test và HTTPS proxy vẫn phải được dựng; **không tuyên bố đây là demo end-to-end chạy được khi chưa có OP**.

### 7.1. Cấu trúc

~~~text
multi-rp-oidc-test/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/multirp/
    │   ├── MultiRpApplication.java
    │   ├── WebSecurityConfig.java
    │   └── SessionInfoController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-rp-oidc-test'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. `application.yml`

~~~yaml
server:
  port: ${APP_PORT:8081}
  servlet:
    session:
      timeout: 20m
      cookie:
        name: ${APP_COOKIE_NAME:RP_SESSION}
        http-only: true
        secure: true
        same-site: lax

app:
  name: ${APP_NAME:A}

spring:
  security:
    oauth2:
      client:
        registration:
          central:
            provider: central
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          central:
            issuer-uri: ${OIDC_ISSUER}
~~~

IdP phải đăng ký **hai clients**:

~~~text
Application A:
  APP_NAME=A
  APP_PORT=8081
  APP_COOKIE_NAME=APP_A_SESSION
  OIDC_CLIENT_ID=client-A
  OIDC_CLIENT_SECRET=<secret-A-from-vault>
  OIDC_ISSUER=https://idp.example.test/realms/workforce

Application B:
  APP_NAME=B
  APP_PORT=8082
  APP_COOKIE_NAME=APP_B_SESSION
  OIDC_CLIENT_ID=client-B
  OIDC_CLIENT_SECRET=<secret-B-from-vault>
  OIDC_ISSUER=https://idp.example.test/realms/workforce
~~~

`client_id` phải **khác nhau** nếu hai apps là hai RPs độc lập. Trong source, registration ID nội bộ `central` có thể giống vì mỗi instance có config context riêng. Redirect URI A/B là URLs độc lập:

~~~text
https://a.example.test/login/oauth2/code/central
https://b.example.test/login/oauth2/code/central
~~~

Backend A:8081 và B:8082 được công khai qua proxy HTTPS trên **hai hostnames khác nhau**; dùng trusted forwarded headers/public URL configuration để `{baseUrl}` khớp callback của từng client. Không tin Host/X-Forwarded-Host do Internet client tùy ý gửi. Không dùng cùng hostname localhost với hai ports rồi giả định session cookies cách ly theo port. Nếu phát triển HTTP trực tiếp, `Secure` cookie có thể không được browser gửi; E2E nên dùng TLS thay vì tắt bảo vệ trong production.

### 7.3. `MultiRpApplication.java`

~~~java
package com.example.multirp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiRpApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiRpApplication.class, args);
    }
}
~~~

### 7.4. `WebSecurityConfig.java`

~~~java
package com.example.multirp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                // A/B phải tự cấp APP_ADMIN theo local policy.
                .requestMatchers("/admin/**").hasAuthority("APP_ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                // Chỉ local logout; không tự logout IdP hoặc B.
                .logoutUrl("/logout")
                .logoutSuccessUrl("/")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            .build();
    }
}
~~~

Ứng dụng tạo local `SecurityContext` sau OIDC callback đã được framework validate. `/admin/**` mặc định bị chặn nếu không có local `APP_ADMIN`; không tự nhận role từ SSO cookie. Production cần nạp enabled/tenant/roles theo trusted identity link `(iss,sub)` và local authorization store, kiểm tra MFA/ACR/freshness nếu endpoint yêu cầu.

### 7.5. `SessionInfoController.java`

~~~java
package com.example.multirp;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionInfoController {

    private final String appName;

    public SessionInfoController(
            @Value("${app.name}") String appName) {
        this.appName = appName;
    }

    @GetMapping("/")
    public Map<String, String> index() {
        return Map.of(
            "app", appName,
            "login", "/oauth2/authorization/central");
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "app", appName,
            "authenticated", authentication.isAuthenticated(),
            "authType",
                authentication.getClass().getSimpleName());
    }

    @GetMapping("/admin/check")
    public Map<String, String> admin() {
        return Map.of("app", appName, "status", "allowed");
    }
}
~~~

Controller cố ý **không** trả raw ID Token, access token, email, `sub` hay session ID qua API công khai. Để xác nhận cùng test subject ở A/B, đối chiếu IdP test audit và approved local identity mapping, không chỉ nội dung `/me`.

### 7.6. Chạy

~~~bash
./gradlew bootRun
~~~

Với cùng JAR có thể chạy hai process/containers độc lập, inject env vars riêng, mỗi app có session store/cookie riêng. Cần IdP test đã cấu hình issuer, client secrets và đăng ký callback URLs; nếu thiếu, application có thể không khởi động hoặc login fail. Không đưa client credentials vào command line được ghi vào shell history của CI.

Nếu cả hai dùng Redis/Spring Session, chọn **namespace riêng cho A/B** để không trộn session keys/SecurityContext. Shared Redis không đồng nghĩa shared RP session; đó là một dependency hạ tầng cần cách ly.

## 8. Những test HTTP/protocol bắt buộc ngoài browser behavior

### 8.1. Client và callback binding

- Authorization request từ A có `client_id=client-A`, redirect URI A, `state_A`, `nonce_A`, PKCE challenge A.
- B có `client_id=client-B`, redirect URI B, `state_B`, `nonce_B`, PKCE challenge B.
- Code A chỉ dùng một lần ở A; đem code A tới B phải bị token endpoint từ chối.
- B không chấp nhận ID Token `aud=client-A`, dù signature của IdP hợp lệ.
- B không chấp nhận `state_A`/`nonce_A` hoặc redirect URI khác registration.
- Không cho browser chọn issuer không nằm allowlist bằng `?issuer=https://evil.example`.
- Kiểm tra ID Token `iss`, `aud`, `exp`, signature/JWKS, `nonce` theo framework; don't decode without verify.
- Session ID rotation sau login, cookie Secure/HttpOnly/SameSite và CSRF trên business POST.

### 8.2. Authorization và account mapping

| User/permission | App A | App B |
| --- | --- | --- |
| Alice có `APP_ORDER_APPROVE` ở A, `APP_REPORT_READ` ở B | Approve theo order ownership | Chỉ xem reports theo quyền B |
| Alice bị disabled ở B | Không tự ảnh hưởng quyền A | Deny B |
| Alice thuộc tenant-A ở A, tenant-B ở B | Kiểm tra resource-A tenant | Kiểm tra resource-B tenant |
| External email trùng, issuer/sub khác | Không auto-link | Không auto-link |
| `sub_A != sub_B` do pairwise | Lookup approved A identity | Lookup approved B identity |
| B yêu cầu phishing-resistant recent MFA | A policy không tự thay thế | B phải check ACR/AMR/auth_time đã verify |

**Shared IdP session chỉ hỗ trợ authentication UX, không truyền role hay tenant entitlement giữa hai apps.** Nếu B chấp nhận group name tự khai từ token của client A để cấp admin, đó là lỗi trust boundary.

## 9. Local logout không phải global logout

### 9.1. Local logout ở A

~~~text
Before:
  IdP session ACTIVE
  A session ACTIVE
  B session ACTIVE

POST https://a.example.test/logout
  -> Spring LogoutFilter invalidates A HttpSession

After:
  IdP session ACTIVE
  A session ENDED
  B session ACTIVE
~~~

**Đây là kết quả bình thường** với `.logout(...)` trong ví dụ Spring Boot. Khi user quay lại A ngay lập tức, A sẽ đưa user đến IdP; IdP session còn nên **có thể cấp code mới mà không hỏi lại credential**, và A lại tạo local session mới. Không kết luận local logout thất bại chỉ vì user vào A lại nhanh.

Test đúng phải xác nhận **A old session ID đã invalidated**, không chỉ giao diện hiển thị thông báo logout, và B session không bị ảnh hưởng.

### 9.2. IdP/OP session hết hạn

Nếu OP session đã hết nhưng A và B vẫn có local HttpSessions:

~~~text
IdP session=EXPIRED
A local session=ACTIVE
B local session=ACTIVE
~~~

A/B có thể vẫn trả 200 cho request dựa trên local sessions cho đến khi app timeout hoặc có SLO/revocation. **Xóa cookie IdP không tự xóa HttpSession của A/B**. Vì vậy phải định nghĩa rõ *user experience logout* và *global session revocation* là hai yêu cầu khác nhau.

### 9.3. RP-Initiated Logout trong OIDC

OIDC RP-Initiated Logout 1.0 cho phép RP đưa browser đến OP `end_session_endpoint` với `id_token_hint` (recommended), `post_logout_redirect_uri` đã đăng ký và `state` khi dùng. Spring Security có `OidcClientInitiatedLogoutSuccessHandler`:

~~~java
// MẢNH cấu hình thay thế local logout handler ở mục 7.
// Cần imports/bean ClientRegistrationRepository đúng version.
OidcClientInitiatedLogoutSuccessHandler opLogout =
    new OidcClientInitiatedLogoutSuccessHandler(
        clientRegistrationRepository
    );
opLogout.setPostLogoutRedirectUri("{baseUrl}");

http.logout(logout -> logout
    .logoutSuccessHandler(opLogout)
    .invalidateHttpSession(true)
    .clearAuthentication(true));
~~~

Đây là **mảnh wiring**, không chèn nguyên đoạn này vào code đã gọi `http.build()`. Import:
`org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler` và `org.springframework.security.oauth2.client.registration.ClientRegistrationRepository`.

Chức năng khởi tạo OP logout cần provider hỗ trợ Discovery/`end_session_endpoint` và registered post-logout URI. **Không có bảo đảm B tự logout ngay** nếu chưa có cơ chế front-/back-channel notification hoặc phiên B tự hết hạn. Redirect hoàn tất đến trang "logged out" không là distributed transaction có xác nhận mọi RP.

## 10. Back-Channel Logout và Front-Channel Logout

### 10.1. OIDC Back-Channel Logout Token

IdP có thể gửi **signed Logout Token JWT** tới mỗi RP đã đăng ký. Token phải có trust validation theo OIDC Back-Channel Logout 1.0, gồm:
- `iss`: issuer đã duyệt;
- `aud`: client ID của RP nhận notification, A và B phải đúng audience riêng;
- `iat`, `exp`, `jti`: thời gian/event ID phục vụ validation và replay controls;
- `events` chứa khóa `http://schemas.openid.net/event/backchannel-logout`;
- `sid` hoặc `sub` (hoặc cả hai) theo supported profile;
- **không được** chứa `nonce`;
- signature/algorithm tin cậy; không chấp nhận unsigned/`alg=none`.

`sid` trong Logout Token là opaque session identifier của OP profile, **không phải** Servlet `JSESSIONID`. RP phải lưu binding `issuer+subject/sid→local session(s)` đúng scope để invalidate. Nếu Logout Token chỉ có `sub`, intent có thể là thu hồi các RP sessions của subject đó theo profile. Không dùng email, không hủy tất cả users có cùng display name.

### 10.2. Idempotency, replay và đến muộn

- OP có thể gửi trùng khi retry hoặc proxy retransmit; receiver phải idempotent.
- Session đã timeout/local logout trước notification → no-op, không tạo session mới.
- Session A cũ đã kết thúc, user login lại tạo A session generation mới → notification cũ không được hủy nhầm generation mới khi event binding là session-specific.
- Nếu notification không có `sid` mà là subject-wide, xử lý đúng **phạm vi được đặc tả**; không tự hẹp hoặc rộng hơn ý định của token đã kiểm chứng.
- `jti` replay cache và TTL cần policy; không log raw token.
- HTTP timeout/502 từ B không chứng minh B chưa invalidate hay đã invalidate; đối chiếu server-side state.
- Không tin Browser gửi `?sid=...` hoặc `?sub=...` để gọi session revoke API.

### 10.3. Front-Channel Logout

Một OP có thể dùng browser iframe/redirect để gọi logout endpoints của RPs. Delivery phụ thuộc browser/tab/third-party cookies/SameSite/CSP và network. Không dùng một iframe load xong làm bằng chứng rằng B local session đã bị invalidate; phải gửi request mới tới B/kiểm tra session store/audit.

### 10.4. Ma trận kết quả

| Sự kiện | IdP session | Local A | Local B |
| --- | --- | --- | --- |
| Local logout A | Còn | Ended | Còn |
| Revisit A khi OP còn | Còn | Tạo session A mới | Còn |
| OP expires, không có notifications | Ended | Có thể còn | Có thể còn |
| RP-Initiated OP logout từ A, không propagation | Ended nếu OP xử lý | Ended | Có thể còn |
| Signed back-channel notifications xử lý thành công tại A+B | Ended | Ended | Ended |
| B callback bị mạng chặn | Ended | Theo delivery ở A | Có thể còn |
| B session đã timeout trước notification | Tùy | Tùy | Ended từ trước |

**Thực thi toàn federation logout phải dựa trên bằng chứng từ từng RP**, không chỉ OP logout response.

## 11. Java 17 độc lập: mô phỏng hai RP và một OP

Ví dụ này **chạy được chỉ với JDK 17**. Nó minh họa sự tách biệt của ba phiên và hai browser contexts; không xử lý signed OIDC tokens, không dùng Servlet/Redis, không bảo đảm delivery. Dùng nó để kiểm tra logic kỳ vọng trước khi viết browser E2E tests.

### 11.1. `MultiAppSsoSessionDemo.java`

~~~java
import java.util.HashMap;
import java.util.Map;

public final class MultiAppSsoSessionDemo {

    static final class Idp {
        private final Map<String, String> sessions = new HashMap<>();
        private int interactiveLogins = 0;

        void login(String browser, String user) {
            sessions.put(browser, user);
            interactiveLogins++;
        }

        String sessionUser(String browser) {
            return sessions.get(browser);
        }

        boolean active(String browser) {
            return sessions.containsKey(browser);
        }

        void logout(String browser) {
            sessions.remove(browser);
        }

        int loginCount() {
            return interactiveLogins;
        }
    }

    static final class App {
        private final Map<String, String> localSessions =
            new HashMap<>();

        String visit(String browser, Idp idp) {
            if (localSessions.containsKey(browser)) {
                return "LOCAL_SESSION";
            }
            String subject = idp.sessionUser(browser);
            if (subject == null) {
                return "LOGIN_REQUIRED";
            }
            // Mô phỏng một authorization code flow mới cho RP này.
            localSessions.put(browser, subject);
            return "SSO_NO_PROMPT";
        }

        void logout(String browser) {
            localSessions.remove(browser);
        }

        boolean active(String browser) {
            return localSessions.containsKey(browser);
        }
    }

    public static void main(String[] args) {
        Idp idp = new Idp();
        App a = new App();
        App b = new App();
        String work = "work-browser";
        String privateBrowser = "private-browser";

        System.out.println("initialA=" + a.visit(work, idp));
        idp.login(work, "alice");

        System.out.println("firstA=" + a.visit(work, idp));
        System.out.println("firstB=" + b.visit(work, idp));
        System.out.println("interactiveLogins=" + idp.loginCount());

        a.logout(work);
        System.out.println("afterLocalLogoutA=" + a.active(work));
        System.out.println("afterLocalLogoutB=" + b.active(work));
        System.out.println("idpStillActive=" + idp.active(work));

        System.out.println("reenterA=" + a.visit(work, idp));
        System.out.println("loginCountAfterReenter=" +
            idp.loginCount());

        // IdP ends session, but RP sessions can stay active
        // without notification.
        idp.logout(work);
        System.out.println("opEndedButAActive=" + a.active(work));
        System.out.println("opEndedButBActive=" + b.active(work));

        a.logout(work);
        b.logout(work);
        System.out.println("visitBWithoutOp=" + b.visit(work, idp));

        idp.login(privateBrowser, "bob");
        System.out.println("privateB=" +
            b.visit(privateBrowser, idp));
        System.out.println("workBAfterLogout=" + b.active(work));

        // New IdP session for Alice and fresh local RP sessions.
        idp.login(work, "alice");
        a.visit(work, idp);
        b.visit(work, idp);
        System.out.println("beforeFederatedA=" + a.active(work));
        System.out.println("beforeFederatedB=" + b.active(work));

        // Only models successful notifications to A and B.
        idp.logout(work);
        a.logout(work);
        b.logout(work);
        System.out.println("afterFederatedA=" + a.active(work));
        System.out.println("afterFederatedB=" + b.active(work));
        System.out.println("bobStillActive=" +
            b.active(privateBrowser));
        System.out.println("totalInteractiveLogins=" +
            idp.loginCount());
    }
}
~~~

### 11.2. Lệnh chạy và stdout

~~~bash
javac --release 17 MultiAppSsoSessionDemo.java
java MultiAppSsoSessionDemo
~~~

**Stdout chính xác:**

~~~text
initialA=LOGIN_REQUIRED
firstA=SSO_NO_PROMPT
firstB=SSO_NO_PROMPT
interactiveLogins=1
afterLocalLogoutA=false
afterLocalLogoutB=true
idpStillActive=true
reenterA=SSO_NO_PROMPT
loginCountAfterReenter=1
opEndedButAActive=true
opEndedButBActive=true
visitBWithoutOp=LOGIN_REQUIRED
privateB=SSO_NO_PROMPT
workBAfterLogout=false
beforeFederatedA=true
beforeFederatedB=true
afterFederatedA=false
afterFederatedB=false
bobStillActive=true
totalInteractiveLogins=3
~~~

**Diễn giải:**
- Một IdP login cho Alice đủ để A và B nhận hai local sessions khi policy cho phép.
- Local logout A không đổi B hay IdP session.
- Revisit A khi OP session active dẫn tới **SSO session mới ở A** mà không tăng số credential ceremonies.
- OP logout một mình **không** xóa local A/B sessions.
- Khi cả OP và local B session hết, B phải login lại.
- Browser-private cho Bob có OP session riêng; không thừa hưởng Alice, và logout Alice không xóa phiên Bob.
- Chỉ nhánh cuối mô phỏng cả hai notification đến và được xử lý nên A/B cùng ended.
- Chương trình không validate JWT, cookies, SAMLResponse, CAS ticket, network hay session store. Không dùng Map/boolean browser ID làm cơ chế production.

## 12. MockMvc, Spring Security Test và giới hạn phạm vi

`spring-security-test` cung cấp `SecurityMockMvcRequestPostProcessors.oidcLogin()`:

~~~java
// Test one already-authenticated request; NOT cross-app SSO:
mvc.perform(get("/me").with(oidcLogin()))
    .andExpect(status().isOk());
~~~

Đây là test một `OidcUser` giả được đưa vào SecurityContext; nó không:
- tạo browser IdP cookie;
- thực hiện authorization redirect A→IdP/B→IdP;
- đổi authorization code/token thật;
- kiểm chứng `state`, `nonce`, PKCE và chữ ký ID Token trong flow đã bị mock;
- tạo hai local sessions trên hai hostnames;
- chứng minh B reuse OP session không cần hỏi mật khẩu;
- thử logout notification giữa hai apps.

Dùng MockMvc để kiểm tra:
- authorization manager/method security của **một app**;
- local principal mapping, enabled, roles, tenant;
- CSRF khi POST;
- controller JSON/HTTP status và error handling.

Dùng **browser E2E + IdP test có browser session thật** để khẳng định SSO liên ứng dụng. Nếu cần test OIDC callback/Logout Token signature, dùng protocol integration với provider/crypto validation thật, không chỉ `oidcLogin()`.

## 13. SAML2: hai Service Providers cùng Identity Provider

Nếu A/B dùng SAML2:
1. SP A gửi `AuthnRequest A` tới IdP; IdP tạo SSO session rồi trả **SAML Response dành riêng ACS-A**.
2. SP B gửi `AuthnRequest B`; IdP có thể dùng phiên IdP còn hiệu lực và trả **SAML Response riêng ACS-B** mà không hỏi password.
3. A/B verify chữ ký/assertion, Issuer, AudienceRestriction, Recipient/Destination, InResponseTo/Conditions và đăng ký RP riêng.
4. A/B tạo `HttpSession` riêng, kiểm tra NameID/immutable identity mapping và local roles.

Các test đặc thù:
- **Audience A không được chấp nhận ở B**, dù assertion signed bởi cùng IdP.
- SP A/B `entityId`, ACS, trust certificates, signing policies phải tách đúng.
- SAML `persistent NameID` có thể được phát pairwise theo SP; không yêu cầu raw NameID A=B.
- SAML SLO có `SessionIndex`/LogoutRequest/LogoutResponse, ký/verify theo hợp đồng, không là Servlet session ID.
- Local logout A không tự logout B; muốn federated SLO phải bật `saml2Logout`, cấu hình IdP và test callback delivery/ack/timeout.
- `MockMvc.with(authentication(new Saml2Authentication(...)))` chỉ test authorization sau authentication, **không** chứng minh IdP cookie sharing hoặc SAML signature verification.

Với SAML cross-site POST vào ACS, xem SameSite cookie/session correlation; đừng tắt validation/CSRF toàn app chỉ để test hết 403.

## 14. CAS: cùng TGT/TGC, hai Service Tickets riêng

Nếu A/B là CAS services:
- Browser có CAS **TGC cookie**, CAS server giữ **TGT** — đây là SSO session chung.
- Lần đầu vào A, CAS cấp **ST-A** theo service URL A, A validate ST-A một lần và tạo HttpSession A.
- Lần đầu vào B, CAS có thể cấp **ST-B** mới bằng TGT còn sống, user không nhập lại password; B validate ST-B theo service URL B, tạo HttpSession B.
- Không thể đem ST-A sang B; service-ticket binding và one-time validation phải được enforced.
- CAS Single Sign Out dùng ticket/session mapping tại mỗi service, callbacks theo profile và delivery có thể best-effort; test duplicate, timeout, missing callback và multi-node routing.
- Local logout A không tự hủy CAS TGT trừ khi ứng dụng chủ động gọi CAS logout theo thiết kế.

**Không dùng lẫn thuật ngữ:** OIDC ID Token/Logout Token, SAML Response/SessionIndex và CAS ST/TGT/TGC là các loại chứng cứ khác nhau. Một identity broker có thể hỗ trợ nhiều protocol, nhưng không suy rằng mọi giao thức đều share OP cookie/session khi thực tế có nhiều IdPs/realms trung gian.

## 15. Cookie, SameSite, HTTPS, session fixation

### 15.1. Hai apps trên localhost: hai ports không bảo đảm cookie isolation

Cookie thường được scoped theo domain/path/name, không theo TCP port. Nếu A `localhost:8081` và B `localhost:8082` cùng set `JSESSIONID` với path "/", cookie có thể bị ghi đè. Test dễ có 302 login loop hoặc false pass.

**Khuyến nghị test:** A/B hostnames khác nhau; host-only local cookies, tên riêng, HTTPS, explicit proxy routes. Không đặt `Domain=.example.test` cho tất cả app cookies chỉ để “có SSO”.

### 15.2. SameSite và các redirect methods

- OIDC Authorization Code callback thường là top-level GET, `SameSite=Lax` có thể phù hợp trong nhiều browser/config.
- SAML2 ACS thường là cross-site POST; nếu session/state cookie bị chặn bởi SameSite, correlation có thể thất bại.
- `SameSite=None` trong browser hiện đại thường yêu cầu `Secure`, nhưng không thay thế CSRF.
- Hidden iframe silent auth và OIDC front-channel logout có thể bị third-party cookie restrictions chặn dù top-level browser redirect hoạt động.
- Dùng các browser versions/contexts đã pin và test từng profile, không tự bật `SameSite=None` toàn hệ thống mà không đánh giá CSRF/third-party cookies.
- Forwarded Host/Proto chỉ được tin từ proxy đã xóa spoofed inbound headers. Sai public baseUrl làm redirect URI và ID Token audience flow lỗi.

### 15.3. SecurityContext/session store

- A/B có thể dùng Spring Session chung một Redis cluster, nhưng **namespace và session store policies cần tách** để tránh SecurityContext/role leakage.
- Multi-node A1/A2: OIDC state/nonce authorization request repository phải tìm đúng session khi callback từ IdP đến node khác.
- Rotate session ID khi authentication thành công để chống session fixation.
- Local session idle timeout và OP session max lifetime có thể khác nhau; không yêu cầu chúng kết thúc cùng thời điểm nếu không có SLO contract.
- Browser logout UI không là bằng chứng server đã invalidated session; thử request mới với cookie cũ và kiểm tra 401/redirect đúng.
- Tất cả business POST cần CSRF/session/authorization theo policy; OIDC callback được framework xử lý theo protocol, không mở tùy tiện.

## 16. Kiểm thử sự cố, expiry và quyền cao

### 16.1. A local session expired, OP còn active

~~~text
OP=ACTIVE, A=EXPIRED, B=ACTIVE
GET A /me -> A starts new authorize flow -> OP reuses SSO
A creates a NEW local session
B unchanged
~~~

Test cần phân biệt session generation mới với session cũ, kiểm tra account enabled/roles một lần nữa. Không tái sử dụng stale SecurityContext.

### 16.2. OP session expired, A/B local còn

~~~text
OP=EXPIRED, A=ACTIVE, B=ACTIVE
GET A /me -> may return 200 using A local session
GET B /me -> may return 200 using B local session
~~~

Nếu business yêu cầu thu hồi đồng bộ, phải bật back-channel/SLO hoặc có session revalidation/revocation riêng. Không coi OP session expiry tự động thu hồi local sessions.

### 16.3. IdP outage

- Existing local sessions có thể hoạt động theo app policy dù IdP offline.
- B chưa có local session có thể không hoàn tất OIDC login mới.
- Không “fallback” thành user mặc định khi IdP unreachable.
- Kiểm tra DNS/TLS/JWKS cache, metadata endpoint, key rotation, token validation failure và timeout.
- Nếu dùng IdP khác làm fallback, phải có policy/identity linking riêng; không tự merge bằng email.
- Không thử chaos trên IdP production.

### 16.4. Step-up ở B

Một người có thể vào A với assurance BASIC nhưng B cần MFA/phishing-resistant authentication vừa thực hiện:
- B đưa `acr_values`, `max_age` hoặc policy-specific challenge tới IdP theo hợp đồng.
- IdP có thể yêu cầu tương tác lại, dù session SSO đang sống.
- Sau callback, B kiểm tra validated `acr`/`amr`/`auth_time`, cùng local identity và role.
- Đừng hạ B policy để bắt “SSO một lần” trong test.
- Một ID Token `iat` mới không chứng minh user vừa MFA.

## 17. Ma trận kiểm thử liên ứng dụng

| ID | Tình huống | Kết quả |
| --- | --- | --- |
| T01 | Fresh browser GET A. | Chưa có local auth; redirect IdP approved. |
| T02 | Login IdP lần đầu với client-A. | One interactive auth; session A tạo hợp lệ. |
| T03 | Cùng browser vào B lần đầu. | B có authorize flow riêng nhưng reuse OP session nếu policy đủ. |
| T04 | B đã có session từ test trước. | Test phải reset để không tạo false pass. |
| T05 | A/B khác client IDs. | Mỗi ID Token đúng audience riêng. |
| T06 | Callback A/B redirect URIs bị đổi chéo. | Reject. |
| T07 | ID Token aud=A gửi cho B. | Reject, không tạo session B. |
| T08 | Authorization code A thử dùng tại B. | Reject client/redirect/code binding. |
| T09 | State A bị gửi cho callback B. | Reject. |
| T10 | Nonce A bị dùng lại cho B. | Reject. |
| T11 | Two apps cùng issuer nhưng khác client secrets. | Không share tokens/secrets. |
| T12 | A/B cùng cookie name trên localhost ports khác. | Test phát hiện collision risk, không kết luận origin isolation. |
| T13 | Host-only APP_A_SESSION và APP_B_SESSION. | Cookies tách đúng origin. |
| T14 | Browser context thứ hai chưa có OP session. | Không thừa hưởng Alice, login mới theo policy. |
| T15 | Two tabs cùng browser profile. | Có thể reuse OP cookie/session. |
| T16 | Browser third-party iframe cookie blocked. | Silent iframe có thể fail; top-level redirect test riêng. |
| T17 | Prompt none, OP session active, consent đủ. | Silent authorization có thể thành công. |
| T18 | Prompt none, OP session absent. | `login_required` hoặc tương đương, không local login. |
| T19 | Prompt none, B cần step-up. | `interaction_required`, không bypass MFA. |
| T20 | B require consent chưa có. | Consent prompt/error theo policy, không auto grant. |
| T21 | B require phishing-resistant method. | Đúng method/ACR/auth_time, không hạ policy. |
| T22 | `max_age=0` khi OP session cũ. | Reauth, kiểm tra auth_time theo spec. |
| T23 | ID Token iat mới, auth_time cũ. | Không coi fresh MFA. |
| T24 | Pairwise sub A != sub B cho cùng user. | Identity mapping đúng, không fail giả. |
| T25 | Email giống, issuers/subjects khác. | Không auto-link account. |
| T26 | User disabled ở B nhưng active ở A. | B deny theo local state. |
| T27 | A có APP_ORDER_APPROVE, B chỉ APP_REPORT_READ. | Không cross-app privilege escalation. |
| T28 | Tenant A không được vào resource tenant B. | Deny dù SSO thành công. |
| T29 | Reload A/B local sessions active. | Không redirect IdP bất thường. |
| T30 | Local logout A. | A ended, B và OP still active. |
| T31 | Reenter A ngay sau local logout, OP active. | A new local session qua IdP SSO; không reuse old session. |
| T32 | OP logout/expiry, chưa có notification. | A/B local sessions có thể còn; không false global success. |
| T33 | RP-Initiated Logout A tới end_session_endpoint. | OP logout theo contract, B checked separately. |
| T34 | B chưa hỗ trợ back-channel logout. | B có thể còn active; ghi đúng giới hạn. |
| T35 | Back-channel Logout Token aud=B, signed/valid. | B revoke đúng local session(s). |
| T36 | Back-channel token sai signature/issuer/audience. | Reject. |
| T37 | Logout Token không có events/nonce xuất hiện. | Reject theo spec. |
| T38 | Duplicate jti, expired/late event. | Idempotent, không hủy nhầm session generation mới. |
| T39 | OP notification bị mất ở proxy. | B có thể active; alert/reconcile. |
| T40 | Bob trong browser-private, logout Alice work browser. | Bob sessions không bị xóa. |
| T41 | Local session A timeout, OP còn. | A authorize lại và tạo session mới. |
| T42 | OP session timeout, A/B local còn. | Không tự đồng bộ nếu thiếu SLO. |
| T43 | IdP offline, A/B local sessions còn. | Theo app policy, không phát auth mới giả. |
| T44 | IdP offline khi B chưa có session. | B login fail closed. |
| T45 | Key rotation/JWKS changes. | Signed valid token pass, untrusted signer reject. |
| T46 | Spring Session Redis namespaces trùng. | Test phát hiện cross-app leak. |
| T47 | Callback đến replica khác node. | State/nonce/session repository nhất quán. |
| T48 | SAML Assertion issued cho SP A đến SP B. | Reject audience/recipient/InResponseTo. |
| T49 | SAML2 NameID pairwise khác. | Không tự coi khác người. |
| T50 | SAML local logout A. | B session vẫn còn trừ khi SLO. |
| T51 | CAS ST-A đem validate ở service B. | Reject service binding/replay. |
| T52 | CAS TGT logout, one SLO callback mất. | Local session service ấy có thể còn. |
| T53 | MockMvc oidcLogin() pass ở A/B. | Chỉ unit/authorization pass, không chứng minh SSO. |
| T54 | Browser password manager tự điền credential lần B. | IdP audit phân biệt reauth thật với reuse session. |
| T55 | OP session có nhiều accounts, cần chọn account. | Account selection theo IdP, không auto wrong user. |
| T56 | User switch identity trong cùng browser khi A session cũ còn. | Không lẫn local principal/permissions. |
| T57 | B local OAuth refresh token còn sau OP logout. | Test revocation/lifetime riêng. |
| T58 | CI log ID Token/cookies/session IDs. | QA fail, redact và rotate khi cần. |
| T59 | SLO completed nhưng browser tab hiển thị DOM cũ. | Request server mới xác nhận authorization. |
| T60 | Nâng IdP/browser/Spring Security version. | Chạy lại regression SSO/CSRF/cookies/logout. |

### 17.1. Acceptance criteria

Một scenario **SSO nhiều app** đạt PASS khi:
1. Hai RPs dùng distinct approved client registrations/redirect URIs.
2. Trong một browser context mới, A login tương tác hợp lệ.
3. B thực hiện authorize flow của chính B và reuse OP session không credential prompt thứ hai **khi chính sách cho phép**.
4. IdP instrumentation xác minh số interactive auth ceremonies, không suy từ 200/ảnh màn hình.
5. Local A/B sessions riêng, cookies không đè nhau, đúng audience/state/nonce.
6. Không lẫn local identities/tenant/roles; pairwise IDs được xử lý theo contract.
7. Local logout khác OP/global logout; nếu test SLO thì có bằng chứng từng RP session đã thực sự bị hủy.
8. Có coverage cho sessions hết hạn, IdP outage, cookies bị chặn và negative tokens.

## 18. Troubleshooting

### 18.1. B yêu cầu login lại dù A đã login

Kiểm tra:
- Cùng browser context hay test runner tạo profile mới?
- B có redirect tới **cùng trusted IdP issuer** và cùng cookie session domain/profile không?
- IdP session còn, cookie chưa bị block/expired?
- B có `prompt=login`/`max_age`/step-up/consent khác A?
- Browser third-party cookie policies hoặc iframe silent auth?
- Đồng hồ, proxy Host/X-Forwarded-Proto, issuer metadata, TLS/callback config?
- App B đã có local session stale dẫn tới redirect loops?
- IdP authentication logs có bao nhiêu interactive events?

Không khắc phục bằng shared JSESSIONID, tắt signature/MFA hoặc dùng token A tại B.

### 18.2. B trả HTTP 200 ngay, không qua IdP

Có thể:
- B session đã tồn tại từ test trước;
- route B `permitAll`;
- cookie A/B bị share sai Domain/path/namespace;
- test dùng MockMvc `oidcLogin()`;
- reverse proxy routing cả hai hostnames vào cùng app.

Reset browser/IdP sessions, assert client-B authorize flow và local B session creation.

### 18.3. Logout A xong lại vào A được ngay

A local session đã kết thúc nhưng OP session còn, nên re-login SSO tạo session A mới. Đây có thể là expected behavior. Nếu yêu cầu global logout, cấu hình OP logout + back-/front-channel propagation được duyệt và test từng RP.

### 18.4. IdP logout rồi B vẫn truy cập được

Kiểm tra:
- B local session còn đang active không?
- OP có phát signed notification cho B không?
- B có receiver đúng và mapping `sid/sub` tới session store không?
- B callback bị firewall/TLS/CSRF/routing/authorization block?
- Có event đến muộn/duplicate và multi-node store issue không?
- B sử dụng refresh token/API credentials có lifecycle khác không?

Không ghi global logout success nếu B còn session hoặc không có bằng chứng B đã revoked.

### 18.5. Browser-only test flaky

Pin version browser; dùng explicit waits, không dùng thời gian cố định; test SameSite/third-party cookie/SSO iframe riêng; reset IDP sessions và avoid popup extension/password manager; không dùng production credentials.

### 18.6. App A/B lẫn user/role

Đây là lỗi bảo mật: đánh giá cookie Domain, session namespace, wrong audience, account mapping bằng email, pairwise subject assumptions, tenant scoping, trusted proxy identity headers, session fixation. Revoke sessions/tokens ảnh hưởng và điều tra.

## 19. Monitoring và test evidence

Metrics gợi ý (không tự có trong Spring):
 
~~~text
sso_authorize_started_total{app,client}
sso_callback_success_total{app,client}
sso_callback_error_total{app,reason_class}
sso_interactive_auth_total{idp,scenario}
sso_existing_op_session_reuse_total{app}
sso_local_session_created_total{app}
sso_local_logout_total{app}
sso_op_logout_total{app,result}
sso_backchannel_logout_received_total{app,result}
sso_backchannel_session_revoked_total{app}
sso_stepup_total{app,result}
sso_authorization_denied_total{app,reason_class}
~~~

Không dùng email, `sub`, `sid`, token, session ID hoặc raw IP như metric labels. Tracing nên dùng test run ID ngẫu nhiên/opaque, bản ghi có retention và kiểm soát quyền đọc.

### 19.1. Mẫu kết quả SSO

~~~text
scenario=T03
browser_context=opaque-ci-context
idp=approved-test-idp
appA_client=client-A
appB_client=client-B
idp_authorization_requests=2
idp_interactive_login_events=1
appA_session=ACTIVE_CONFIRMED
appB_session=ACTIVE_CONFIRMED
audience_validation_A=PASS
audience_validation_B=PASS
app_permissions=ISOLATED
result=PASS
~~~

### 19.2. Mẫu logout toàn hệ thống

~~~text
scenario=T35
op_session=ENDED_CONFIRMED
appA_logout_notification=VERIFIED
appA_session=REVOKED_CONFIRMED
appB_logout_notification=VERIFIED
appB_session=REVOKED_CONFIRMED
result=PASS
~~~

Nếu B callback mất, ghi đúng `appB_session=UNKNOWN_OR_ACTIVE` và đánh **FAIL** cho yêu cầu global revocation; không suy thành công từ OP logout page.

## 20. Tự đánh giá

**1. Dùng chung IdP có làm A/B dùng chung HttpSession không?**  
Không. Mỗi RP tạo local session riêng sau authorization flow của client đó.

**2. Tại sao B vẫn redirect tới IdP nhưng không hỏi mật khẩu?**  
B cần một authorization code dành riêng cho client-B; IdP dùng browser session đã có để cấp code.

**3. Một lần SSO có thể có hai OAuth2 authorization requests không?**  
Có, một cho mỗi app. Số credential ceremonies có thể chỉ là một.

**4. Dùng hai Selenium browser profiles để test SSO có đúng không?**  
Không cho happy path shared cookie: cần **một** browser context. Dùng profile khác để test isolation.

**5. B có được dùng ID Token aud=A không?**  
Không, audience/client binding phải được xác minh.

**6. Nếu `sub_A != sub_B`, chắc chắn là hai người?**  
Không. Pairwise subject có thể khác theo client/sector; cần trusted mapping.

**7. `prompt=none` có bỏ qua authentication không?**  
Không. Nó yêu cầu IdP chỉ dùng chứng cứ có sẵn, nếu không đủ phải trả error.

**8. `auth_time` có phải thời điểm tạo local B session?**  
Không. Đó là thời gian IdP xác thực end-user.

**9. Local logout A có logout B không?**  
Không mặc định. B session và IdP session có thể còn.

**10. OP session expired có tự hủy A/B không?**  
Không nếu không có SLO/revocation propagation.

**11. OIDC signed Logout Token có giống ID Token không?**  
Không. Logout Token có `events` dành cho back-channel logout và `sid/sub` theo spec, không có `nonce`.

**12. MockMvc `oidcLogin()` ở A và B có chứng minh SSO không?**  
Không. Nó chỉ giả principal cho request của từng app.

**13. Hai apps khác ports trên localhost có cookie cách ly tuyệt đối không?**  
Không. Cookie không scoped theo port; nên dùng hostnames khác nhau trong E2E.

**14. Nếu B cần MFA mạnh hơn A, lần vào B có thể yêu cầu MFA không?**  
Có. Đó có thể là đúng security policy, không phải lỗi SSO.

**15. SAML/CAS có dùng chung loại ID Token/Logout Token của OIDC không?**  
Không. Phải kiểm thử từng protocol/binding riêng dù cùng danh mục federation.

## 21. Checklist go-live

- [ ] Có IdP sandbox, app A/B thật, HTTPS và hostnames phân biệt.
- [ ] Hai RPs có distinct client IDs, secrets, callback/logout URLs đúng trust configuration.
- [ ] Browser context mới được reset, không có sessions tồn đọng từ test trước.
- [ ] A interactive login qua IdP được theo dõi bằng audit/instrumentation.
- [ ] B chạy authorize flow riêng, reuse OP session trong **cùng browser context** khi policy cho phép.
- [ ] Có xác nhận chỉ một interactive ceremony dù hai authorization/token flows.
- [ ] OIDC state/nonce/PKCE/code binding/issuer/audience/expiry/signature được xác minh.
- [ ] OP session và local sessions A/B được phân biệt rõ trong logs và test oracle.
- [ ] Cookie A/B host-only, Secure, HttpOnly, không share bằng Domain chung.
- [ ] Không coi localhost ports là cookie isolation; test SameSite/third-party cookies đúng browser.
- [ ] Account linking dùng trusted IDs, không auto-match email; pairwise sub xử lý theo contract.
- [ ] Local authorities, account enabled, tenant và resource ownership độc lập theo app.
- [ ] Có negative tests cho wrong audience, wrong issuer, swapped callback, stale state/nonce.
- [ ] Có test `prompt=none` active/absent/consent/step-up, `max_age`/`auth_time` theo policy.
- [ ] Logout local A được xác minh riêng, không gắn nhãn global logout.
- [ ] Nếu RP-Initiated OP logout được bật, `end_session_endpoint`/return URI registered và tested.
- [ ] Nếu có OIDC Back-Channel Logout, kiểm tra signed JWT, events, sid/sub/jti, audience và idempotent revoke.
- [ ] Nếu có SAML2/CAS, test đúng assertions/tickets, SLO callbacks, signature, service binding và late/missing event.
- [ ] Test local/OP session expiry, IdP outage, key rotation, multi-node session store và restart.
- [ ] MockMvc dùng cho local controller/authorization, browser E2E cho shared IdP session.
- [ ] Không lưu tokens/cookies/PII trong CI logs/screenshots; secrets được quản lý an toàn.
- [ ] Có test T01–T60 hoặc coverage tương đương, regression sau nâng version.

## Ghi nhớ

> **Một IdP session có thể giúp đăng nhập vào nhiều ứng dụng mà không nhập lại mật khẩu, nhưng mỗi ứng dụng phải có authorization flow, session, token audience và quyền riêng.** Kiểm thử SSO đúng cách phải đi qua A và B bằng **cùng browser context**, xác nhận **IdP session reuse và số interactive authentication ceremonies**, không chỉ hai HTTP 200 hoặc hai MockMvc mock users. **Local logout không tự thành global logout**; muốn khẳng định logout toàn federation phải chứng minh từng RP local session đã được thu hồi qua cơ chế SLO thực sự.

### Tài liệu tham khảo chính thức

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authorization Code flow, prompt none/login, max_age, auth_time, ID Token iss/aud/nonce.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): end_session_endpoint, id_token_hint và post_logout_redirect_uri.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): signed Logout Token, events, sid/sub/jti, delivery và revoke.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout qua user agent/browser.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, authorization endpoint và code callback.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): OidcClientInitiatedLogoutSuccessHandler.
- [Spring Security — MockMvc OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): oidcLogin() test fixture và giới hạn.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext, session fixation, lifecycle.
- [Spring Security — SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/IdP, AuthnRequest, ACS.
- [Spring Security — SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP initiated SLO, LogoutRequest/LogoutResponse.
- [Apereo CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): TGT/TGC, ST per service và SLO.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie/session security.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): MFA, reauthentication and recovery controls.
