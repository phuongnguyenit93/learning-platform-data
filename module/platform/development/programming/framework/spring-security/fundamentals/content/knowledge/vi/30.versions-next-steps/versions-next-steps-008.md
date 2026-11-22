# Học tiếp OAuth 2.0, OpenID Connect và liên kết danh tính khi có nhu cầu

> **Vị trí trong lộ trình:** Sau khi hiểu authentication, authorization, `SecurityFilterChain`, session và bảo vệ endpoint bằng Spring Security, hãy học OAuth 2.0, OpenID Connect (OIDC) hoặc federation khi hệ thống thực sự cần đăng nhập qua nhà cung cấp danh tính khác, gọi API bằng token hoặc dùng danh tính chung giữa nhiều ứng dụng.

## 1. Vì sao đây là bước học tiếp có điều kiện?

Kiến thức Spring Security nền tảng trả lời “request này được xác thực và được phép thực hiện việc gì?”. Những yêu cầu sau bổ sung câu hỏi “ai cấp danh tính?”, “quyền truy cập do ai cấp?” và “ứng dụng tin tưởng hệ thống nào?”:

- Người dùng đăng nhập bằng tài khoản doanh nghiệp, Google hoặc một Identity Provider (IdP).
- Nhiều ứng dụng cần **Single Sign-On (SSO)** để người dùng không phải nhập lại mật khẩu ở từng ứng dụng.
- Web app cần gọi một API khác **thay mặt người dùng** mà không biết mật khẩu API của họ.
- Một backend cần **nhận và kiểm tra access token** do Authorization Server phát hành.
- Hai dịch vụ trao đổi dữ liệu **không có người dùng tương tác**, dùng danh tính của chính ứng dụng.
- Ứng dụng cần tin cậy IdP thuộc tổ chức khác (federation).

Nếu dự án hiện tại chỉ cần đăng nhập cục bộ và vài quy tắc phân quyền, không phải triển khai OAuth2/OIDC ngay. Trước khi chọn công nghệ, xác định rõ luồng người dùng, client, API, tổ chức tin cậy và yêu cầu bảo mật.

## 2. Ba khái niệm rất dễ bị nhầm

| Khái niệm | Mục tiêu | Điều cần học |
| --- | --- | --- |
| **OAuth 2.0** | Ủy quyền để một `client` truy cập tài nguyên có giới hạn qua `access token` | Authorization Server, Resource Server, grants, scopes, token lifecycle |
| **OpenID Connect (OIDC)** | Xác thực người dùng theo chuẩn trên nền OAuth 2.0 | ID token, `openid` scope, issuer, subject, audience, nonce, UserInfo |
| **Identity federation** | Quan hệ tin cậy để hệ thống A chấp nhận danh tính do hệ thống B xác thực | IdP/Relying Party, trust, mapping tài khoản, chính sách, OIDC hoặc SAML |

**OAuth2 không tự nó là giao thức đăng nhập danh tính.** Access token thường thể hiện quyền cho một API, còn **ID token** trong OIDC truyền thông tin về sự kiện xác thực tới ứng dụng client. Một số OAuth2 provider có API thông tin người dùng và Spring Security hỗ trợ đăng nhập theo cách riêng, nhưng OIDC chuẩn hóa tốt hơn việc khẳng định danh tính.

**SSO không phải tên giao thức.** SSO là trải nghiệm đăng nhập có thể sử dụng qua nhiều ứng dụng; federation là mô hình tin cậy; OIDC và SAML 2.0 là các giao thức có thể dùng để hiện thực. SAML không phải “phiên bản cũ của OAuth2”; nhiều hệ thống doanh nghiệp vẫn sử dụng SAML federation.

### Các vai trò trong OAuth 2.0

1. **Resource Owner:** chủ thể sở hữu quyền truy cập tài nguyên, thường là người dùng trong luồng ủy quyền tương tác.
2. **Client:** ứng dụng yêu cầu quyền; có thể là web app, ứng dụng di động hoặc service.
3. **Authorization Server:** xác thực/đánh giá chính sách và cấp token.
4. **Resource Server:** API nhận access token và bảo vệ tài nguyên.
5. **OpenID Provider (OP):** IdP hỗ trợ OIDC. Ứng dụng dựa vào OP để xác thực được gọi là **Relying Party (RP)**.

Một ứng dụng có thể kiêm nhiều vai trò trong các luồng khác nhau. Chẳng hạn backend là OAuth2 Client khi gọi API bên ngoài, nhưng là Resource Server khi chính nó cung cấp API nhận bearer token.

## 3. Bảng chọn hướng học theo bài toán

| Nhu cầu thực tế | Học trước | Tính năng Spring Security |
| --- | --- | --- |
| “Đăng nhập bằng tài khoản công ty” cho ứng dụng web | OIDC Authorization Code, redirect, session, PKCE | `oauth2Login` và `ClientRegistration` |
| Web app gọi API thay mặt user | OAuth2 Client, scope, token refresh | `oauth2Client` và `OAuth2AuthorizedClientManager` |
| Backend bảo vệ REST API nhận Bearer token | OAuth2 Resource Server, JWT/opaque token, issuer, audience | `oauth2ResourceServer` |
| Service A gọi Service B mà không có user | Client Credentials, ứng dụng là principal | OAuth2 Client với `client_credentials` |
| Hai tổ chức cần đăng nhập liên kết | OIDC/SAML federation, trust, account linking | OIDC Login hoặc SAML2 tùy provider |
| Tự phát hành token và quản lý client/consent | Authorization Server, signing keys, token policy | Hệ thống Authorization Server/IdP chuyên dụng |

**Điểm quyết định:** đăng nhập người dùng, gọi API và phát hành token là ba trách nhiệm khác nhau. Chọn chức năng tương ứng, tránh tự viết bộ cấp token hoặc tự xử lý redirect khi chưa có nhu cầu.

## 4. Luồng OIDC Authorization Code + PKCE

Ví dụ ứng dụng Spring Boot Servlet muốn đăng nhập với IdP của công ty:

1. Người dùng vào trang yêu cầu đăng nhập. App chuẩn bị authorization request gồm `client_id`, `redirect_uri`, `scope=openid ...`, `state` và tham số liên quan.
2. Trình duyệt được chuyển đến Authorization Endpoint. Người dùng xác thực **tại IdP**; app không cần biết mật khẩu của họ.
3. IdP redirect về URI callback đã đăng ký, kèm authorization **code** và `state`.
4. Backend kiểm tra tính liên kết với request ban đầu; đổi code lấy token tại Token Endpoint. Nếu dùng PKCE, `code_verifier` phải khớp với `code_challenge` đã đăng ký.
5. Với OIDC, client xác minh ID token theo hợp đồng OIDC, gồm chữ ký, issuer (`iss`), audience (`aud`), thời hạn và `nonce` khi áp dụng.
6. Ứng dụng tạo phiên cục bộ hoặc cơ chế duy trì đăng nhập phù hợp; Spring Security tiếp tục chạy **authorization** cho request và tài nguyên của app.

```text
Trình duyệt          Spring Boot (RP / OAuth2 Client)             OIDC Provider
    |--- GET /private -------->|                                  |
    |<------- redirect --------|                                  |
    |---------------------- authorization request ---------------->|
    |<--------------------- login / consent -----------------------|
    |-------- callback + code ->|                                  |
    |                           |---- code + PKCE verifier ------->|
    |                           |<---------- tokens ---------------|
    |<------ app session -------|                                  |
    |--- GET /private --------->|-- app authorization rules ------>|
```

Đây là sơ đồ khái niệm, bỏ qua một số request và cookie. Không đưa client secret vào trình duyệt.

### Tại sao cần các cơ chế bảo vệ?

- **`state`:** liên kết callback với yêu cầu ban đầu, hạn chế CSRF/session mix-up trong luồng OAuth2.
- **`nonce`:** ràng buộc ID token với lần xác thực OIDC, hạn chế phát lại token trong các luồng có nonce.
- **PKCE:** gắn authorization code với client đã khởi tạo luồng bằng `code_verifier`. Đặc biệt cần với public client; nên cân nhắc với confidential client nếu IdP hỗ trợ.
- **Redirect URI:** phải đăng ký và đối chiếu chính xác; không nhận redirect đích tùy ý do người dùng nhập.

Các chi tiết như `state`, PKCE, ID token validation nên do thư viện OIDC/OAuth2 tin cậy đảm nhiệm. Việc chỉ đổi code rồi lưu token tùy tiện không hoàn tất một luồng đăng nhập an toàn.

## 5. Phân biệt access, ID và refresh token

| Token | Ai sử dụng? | Ý nghĩa |
| --- | --- | --- |
| **Access token** | API/Resource Server là đối tượng nhận theo audience | Quyền truy cập tài nguyên, thời hạn và scope; có thể là JWT hoặc opaque |
| **ID token** | OIDC Client/Relying Party | Kết quả xác thực danh tính người dùng; **không** dùng thay access token để gọi API |
| **Refresh token** | Client được phép lưu giữ | Xin access token mới; bảo vệ và xoay vòng/thu hồi theo chính sách |

**JWT là một định dạng token**, không phải tên khác của OAuth2 hoặc OIDC. JWT thường có claims như:

- `iss`: bên phát hành; phải thuộc issuer được tin cậy.
- `sub`: định danh subject trong ngữ cảnh issuer.
- `aud`: đối tượng dự kiến nhận token; API phải kiểm tra token dành cho chính mình.
- `exp`, `nbf`: giới hạn thời gian.
- `scope`/`scp`: các quyền được cấp, tên claim tùy IdP.
- `nonce`: ràng buộc yêu cầu OIDC khi dùng nonce.

**Giải mã Base64URL không tương đương xác minh token.** API cần kiểm tra chữ ký hoặc introspection, issuer, thời gian, audience và quyền theo chính sách. Tài khoản đã đăng nhập cũng không tự động có quyền nghiệp vụ: `Authentication` chỉ nói ai đã được xác thực, còn `Authorization` quyết định họ được làm gì.

## 6. Ví dụ A: OIDC Login cho ứng dụng Spring Boot Servlet

Ví dụ này là **cấu hình bên trong một ứng dụng Spring Boot có sẵn**, phù hợp để học với Java 17+. Nó phụ thuộc Spring Boot/Spring Security, không phải file Java độc lập biên dịch bằng `javac`; không có stdout cố định. Chọn phiên bản dependency phù hợp với dự án.

Với Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

`application.yml` cho IdP hỗ trợ OIDC Discovery:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope: openid, profile, email
        provider:
          corp:
            issuer-uri: "https://idp.example.org/realms/company"
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

- `registration.corp` là một client registration; `provider.corp.issuer-uri` để framework tìm metadata OIDC, endpoints và khóa công khai.
- `oauth2Login` dùng Authorization Code. Điểm khởi động mặc định thường là `/oauth2/authorization/corp`; callback thường là `/login/oauth2/code/corp`. Callback phải đăng ký đúng ở IdP.
- `authorizeHttpRequests` vẫn quyết định truy cập tài nguyên của **ứng dụng**, độc lập với việc IdP đã xác thực user.
- Giá trị `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` lấy từ môi trường hoặc secret manager; hostname ví dụ phải thay bằng issuer thực. Không commit secret.
- Với đăng nhập dùng session/cookie trên trình duyệt, giữ các biện pháp CSRF và cookie security phù hợp; không tắt chúng chỉ để làm demo.

Khi có IdP thử nghiệm hợp lệ, chạy ứng dụng Boot, mở route được bảo vệ rồi kiểm tra redirect → IdP → callback → phiên cục bộ. Đăng nhập thành công chưa đủ: thử một endpoint yêu cầu quyền mà user **không có** để kiểm tra phân quyền sau đăng nhập.

## 7. Ví dụ B: Resource Server cho API nhận JWT

Đây là **một ứng dụng API riêng** minh họa Resource Server. Thêm dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cho API tin issuer cung cấp metadata và khóa xác minh JWT:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.org/realms/company"
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Ý nghĩa:

- Resource Server xử lý header `Authorization: Bearer <access-token>`; xác minh JWT qua public keys/metadata của issuer và các ràng buộc bảo mật đã cấu hình.
- Scope `reports.read` được ánh xạ thành authority `SCOPE_reports.read` với cấu hình JWT scope converter mặc định thích hợp. Kiểm tra đúng claim mà IdP thực tế phát hành.
- Token thiếu, hết hạn hoặc không hợp lệ thường dẫn tới **HTTP 401**; token hợp lệ nhưng không có authority cần thiết thường dẫn tới **HTTP 403**.
- **Audience (`aud`) của API cần được kiểm tra/cấu hình theo yêu cầu**, không mặc định coi mọi JWT từ cùng issuer đều dành cho API này. Cân nhắc thêm validators cụ thể theo quy tắc dự án.
- Ví dụ chỉ nêu security; cần ứng dụng Boot, controller, issuer/token thật mới chạy được. Với API stateless chỉ dùng bearer token, đánh giá CSRF theo kiểu credential và threat model trước khi thay đổi cấu hình.

Nếu API nhận **opaque token**, học introspection thay cho xác minh JWT trực tiếp. Nếu ứng dụng cần **tự lấy token để gọi API khác**, đó là vai trò OAuth2 Client, không phải tính năng Resource Server.

## 8. OAuth2 Client, Client Credentials và gọi API

Khi backend cần gọi API trên danh nghĩa người dùng, học `authorization_code`, quản lý authorized client và refresh token. Spring Security cung cấp `OAuth2AuthorizedClientManager` và tích hợp với HTTP client như `RestClient`/`WebClient` tùy stack.

Ngược lại, với giao tiếp giữa hai service không có user, `client_credentials` cho token đại diện **ứng dụng**. Không dùng token service-to-service làm bằng chứng rằng một người dùng cụ thể đã cho phép thao tác. Quyền token nên tối thiểu và API cần phân biệt rõ principal ứng dụng với principal người dùng.

Một trình tự thực hành hợp lý: lấy token với grant đúng → gọi API thử nghiệm → yêu cầu scope bị từ chối → token hết hạn/refresh → thu hồi credential → xem log và cơ chế retry có lộ token hay không.

## 9. Khi nào cần identity federation?

Mô hình liên kết danh tính thường xuất hiện trong tổ chức có nhiều IdP, đối tác hoặc tenant:

```text
Người dùng
    |
Ứng dụng / Relying Party
    |
    | OIDC hoặc SAML qua trust đã cấu hình
    v
IdP / Identity Broker
    |-- Directory nhân viên
    |-- IdP của đối tác
    |-- IdP của tenant khác
```

Cần thiết kế **quan hệ tin cậy và tài khoản**, ngoài cấu hình callback:

1. **Nguồn danh tính:** tổ chức nào xác thực, đặt chính sách MFA và vô hiệu hóa nhân viên nghỉ việc?
2. **Khóa liên kết tài khoản:** với OIDC, dùng định danh ổn định như cặp `(iss, sub)`. Email có thể đổi, dùng lại hoặc chưa được xác minh, vì vậy không tự động ghép hai issuer chỉ bằng email.
3. **Phân quyền theo tenant:** claim nhóm/role từ IdP là dữ liệu đầu vào; ứng dụng phải xác định nhóm nào được tin và quyền nghiệp vụ nào áp dụng.
4. **Vòng đời tài khoản/phiên:** offboarding, revocation, logout, timeout và audit vẫn phải thiết kế riêng; SSO không tự động thu hồi mọi phiên trên tất cả ứng dụng ngay lập tức.
5. **Chia sẻ dữ liệu:** chỉ nhận claims cần thiết, hạn chế thời gian lưu và đối chiếu yêu cầu riêng tư.
6. **Provisioning:** đồng bộ vòng đời người dùng/directory (có thể qua SCIM) là bài toán khác với federation đăng nhập.

Nếu provider chỉ hỗ trợ SAML, dùng tích hợp SAML phù hợp hoặc identity broker đã được quản trị; đừng cố chuyển mọi federation thành cấu hình `oauth2Login`.

## 10. Lỗi phổ biến và cách tự kiểm chứng

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng access token như ID token | Nhầm ủy quyền API với xác thực user | Dùng OIDC và ID token cho danh tính |
| Gửi ID token đến REST API | Sai đối tượng nhận token | API nhận access token dành cho API |
| Chỉ decode JWT mà không verify | Tin token giả/hết hạn/sai issuer | Xác minh chữ ký, issuer, thời gian, audience và policy |
| Tin email/group trực tiếp là admin | Ghép nhầm user hoặc vượt quyền | Map identity và authorities theo issuer, tenant, chính sách |
| Bỏ state/nonce/PKCE, redirect URI quá rộng | Tăng nguy cơ replay và code interception | Dùng flow/framework chuẩn, URI chặt chẽ |
| Lưu secret/refresh token trong frontend, URL hoặc log | Lộ credential | Backend/secret store, giới hạn log, rotation |
| Dùng Client Credentials thay user delegation | Mất ngữ cảnh và consent của user | Dùng grant phù hợp |
| Cho rằng OIDC Login tự cấp mọi quyền | Thiếu kiểm soát nghiệp vụ | Kiểm tra authorization tại endpoint và domain |
| Tự vận hành Authorization Server khi chỉ cần SSO | Tăng rủi ro khóa ký, token, consent, vận hành | Dùng IdP/Authorization Server chuyên dụng nếu phù hợp |

**Bộ ca kiểm chứng tối thiểu:**

- **Web OIDC:** người chưa đăng nhập được chuyển đến IdP; callback hợp lệ thành công; callback có trạng thái sai bị từ chối; user đã đăng nhập nhưng thiếu quyền không được vào tài nguyên.
- **API:** không token → 401; token không hợp lệ/hết hạn/sai issuer → 401; token đúng nhưng thiếu scope → 403; token đúng audience + scope → cho phép. Để kiểm tra audience đúng, phải cấu hình validator audience cho API.
- **Federation:** user từ IdP không tin cậy bị từ chối; trùng email giữa hai issuer không tự động gộp tài khoản; tài khoản bị khóa không được cấp truy cập mới; policy theo tenant được áp dụng.

## 11. Lộ trình học tiếp đề xuất

1. **Ôn nền tảng:** `Authentication`, `SecurityContext`, `GrantedAuthority`, session, CSRF, bảo vệ API và HTTP 401/403.
2. **Chọn đúng vai trò:** vẽ Client → Authorization Server/OP → Resource Server và chỉ rõ token nào tới thành phần nào.
3. **Chỉ đào sâu nhánh phù hợp:** OIDC Login cho đăng nhập web; OAuth2 Client cho gọi API; Resource Server cho API nhận bearer token; federation khi cần trust liên tổ chức.
4. **Tự triển khai một môi trường thử:** IdP thử nghiệm, redirect URI hợp lệ, credentials đặt ngoài source code, một route công khai và một route yêu cầu authority.
5. **Thử cả ca lỗi:** expiry, issuer/audience sai, scope thiếu, logout và offboarding; xác thực thành công chưa chứng minh authorization đúng.
6. **Sau đó mới nâng cao:** custom claim mapping, multi-tenant issuer, refresh/revocation, account linking, token exchange, SAML hoặc tự vận hành Authorization Server nếu bài toán đòi hỏi.

**Tiêu chí nắm bài:** Giải thích được “OAuth2 cấp quyền, OIDC xác thực danh tính, federation thiết lập tin cậy”; chọn đúng `oauth2Login`/`oauth2Client`/`oauth2ResourceServer`; phân biệt access/ID/refresh token; và kiểm chứng được API từ chối token sai thay vì chỉ chạy qua happy path.

## 12. Tài liệu tham khảo chuẩn

Chọn tài liệu đúng **phiên bản Spring Boot/Spring Security** mà dự án dùng; API và mặc định có thể đổi qua các bản phát hành.

- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot — OAuth2](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [OpenID Foundation — How OpenID Connect Works](https://openid.net/developers/how-connect-works/)

**Định hướng:** học thêm các chuẩn này theo nhu cầu thật và vẫn giữ trách nhiệm kiểm soát truy cập trong ứng dụng. SSO hay token hợp lệ không thay thế kiểm tra quyền nghiệp vụ và bảo vệ dữ liệu.
