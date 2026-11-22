# Kiến thức đầu vào và trình tự học: từ mô hình tin cậy đến tích hợp SSO

> **Bối cảnh:** Spring Security – federation / Tổng quan liên kết. Bài này dành cho người đã biết phát triển ứng dụng Java và muốn hiểu vì sao một ứng dụng có thể tin danh tính do hệ thống khác xác thực, rồi triển khai đăng nhập một lần (Single Sign-On – SSO) đúng cách. Ví dụ thực hành dùng ứng dụng **Spring MVC/Servlet**, Java 17 và Spring Boot 3.5.x (Spring Security 6.x).

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

1. Vẽ được **ranh giới tin cậy** giữa người dùng, trình duyệt, ứng dụng, nhà cung cấp danh tính (IdP) và API.
2. Phân biệt **federation, SSO, OAuth 2.0, OpenID Connect (OIDC) và SAML 2.0**; chọn đúng giao thức cho mục tiêu đăng nhập hay truy cập API.
3. Giải thích được ứng dụng tin vào thông điệp danh tính dựa trên **issuer, audience, chữ ký, khóa xác minh, hiệu lực, trạng thái phiên và cấu hình đã đăng ký**, thay vì tin một tham số do trình duyệt gửi.
4. Theo dõi được luồng OIDC Authorization Code và SAML Web Browser SSO; nhận biết yêu cầu chống giả mạo và phát lại.
5. Thiết lập một ứng dụng Spring Security làm **OIDC Relying Party (OAuth2 Client)**, thử đăng nhập qua IdP và biết vị trí cấu hình SAML 2.0 hoặc Resource Server khi mở rộng.
6. Lập kế hoạch kiểm thử, xử lý sự cố và tăng cứng tích hợp SSO trước khi đưa vào sản xuất.

## 2. Kiến thức nền cần có trước khi học federation

| Nhóm | Cần nắm | Vì sao cần |
| --- | --- | --- |
| Java/Spring | Java 17+, Maven/Gradle, Spring Boot, cấu hình YAML, Bean, Spring MVC | Đọc và chạy được cấu hình `SecurityFilterChain` và endpoint thử nghiệm |
| Spring Security | `Authentication`, `SecurityContext`, `GrantedAuthority`, `SecurityFilterChain`, quy tắc `authenticated()`/`hasAuthority()` | Tách **đã xác thực** với **được phép truy cập** |
| HTTP và trình duyệt | HTTPS, 302 Redirect, GET/POST, cookie, `SameSite`, phiên server, URL callback | Hiểu vì sao đăng nhập có nhiều lượt chuyển hướng giữa ứng dụng và IdP |
| An toàn web | CSRF, XSS, session fixation, bảo vệ secret, reverse proxy | Tránh bỏ qua lớp phòng vệ chỉ vì đã dùng SSO |
| Mật mã cơ bản | Khóa công khai/riêng, chữ ký số, chứng thư X.509, JWT, JWKS, thời gian hết hạn | Phân biệt **xác minh nguồn phát** với **giải mã**, biết khi nào token/assertion đáng tin |
| Kiến trúc hệ thống | Domain, DNS, tenant, môi trường dev/test/prod, quản lý người dùng | Thiết kế đúng đối tượng tin cậy và đường dẫn callback của từng môi trường |

**Tự kiểm tra:** Nếu nhận `GET /orders` khi chưa đăng nhập, hãy giải thích vì sao Spring Security chặn request, chuyển người dùng đi xác thực, rồi tạo `Authentication` sau callback. Nếu chưa giải thích được, nên ôn Spring Security filter chain, session và CSRF trước khi cấu hình IdP.

## 3. Mô hình tin cậy: bắt đầu từ câu hỏi “ai tin ai?”

**Identity federation** là thỏa thuận kỹ thuật và quản trị để một hệ thống sử dụng kết quả xác thực danh tính từ hệ thống khác. **SSO** là trải nghiệm người dùng có thể truy cập nhiều ứng dụng mà thường không phải đăng nhập lại khi phiên tại IdP còn hợp lệ. Federation là cơ chế thiết lập niềm tin; SSO là một khả năng thường được xây trên cơ chế đó. Một lần đăng nhập tại IdP không đồng nghĩa mọi ứng dụng tự động có quyền xem mọi tài nguyên.

Các tác nhân:

- **End user / User Agent:** người dùng và trình duyệt đi qua các redirect. Trình duyệt là phương tiện truyền dữ liệu, **không phải bên cấp chứng nhận danh tính**.
- **Identity Provider (IdP):** nơi kiểm tra thông tin đăng nhập, chính sách MFA, điều kiện truy cập và phát hành thông tin xác thực. Trong OIDC thường gọi là **OpenID Provider (OP)**; trong SAML gọi là **Asserting Party/IdP**.
- **Ứng dụng nhận đăng nhập:** **Relying Party (RP)** trong OIDC, hoặc **Service Provider (SP)** trong SAML. Spring Security đóng vai trò này khi bật `oauth2Login()` hoặc `saml2Login()`.
- **Authorization Server (AS):** phát hành OAuth 2.0 access token. Thường cùng sản phẩm với IdP nhưng về mặt vai trò không bắt buộc là một thành phần.
- **Resource Server (RS):** API chấp nhận access token và áp dụng quyền truy cập cho tài nguyên; thường cấu hình `oauth2ResourceServer()`.

**Đường tin cậy tối thiểu:**

```text
Người dùng ──trình duyệt/redirect──> Ứng dụng RP/SP
     │                                  │
     └──đăng nhập/MFA tại IdP/OP<───────┘
                                        │
                            RP kiểm chứng kết quả do IdP phát hành
                                        │
                               Tạo phiên ứng dụng
                                        │
                             Áp dụng quyền cho tài nguyên

API Resource Server <── access token từ client ──> API caller
        │
        └── tự kiểm chứng access token phù hợp API
```

Ứng dụng và IdP phải có **cấu hình quan hệ tin cậy từ trước**: địa chỉ issuer/entity ID chính xác, client/SP registration, redirect/ACS được đăng ký, khóa hoặc metadata đáng tin, và quy tắc mapping người dùng. HTTPS bảo vệ đường truyền nhưng **HTTPS một mình không xác nhận một token được cấp cho đúng ứng dụng**.

### Đăng nhập, ủy quyền và tài nguyên là ba vấn đề khác nhau

| Công nghệ | Vai trò chính | Dữ liệu trọng tâm | Không nên suy diễn |
| --- | --- | --- | --- |
| OAuth 2.0 | Cấp quyền truy cập tài nguyên giữa client và authorization server | Authorization code, access token, scope | OAuth 2.0 tự nó **không phải** giao thức xác thực danh tính người dùng |
| OIDC (xây trên OAuth 2.0) | Đăng nhập danh tính có chuẩn | **ID Token**, `iss`, `sub`, `aud`, có thể có UserInfo | ID Token **không phải** access token để gọi API |
| SAML 2.0 Web Browser SSO | Đăng nhập liên kết phổ biến trong doanh nghiệp | SAML `AuthnRequest`, `Response`, `Assertion`, XML signature | Assertion không phải JWT; cách kiểm chứng và endpoint khác OIDC |
| Spring Security session | Ghi nhận trạng thái đăng nhập **tại ứng dụng** | `SecurityContext`, session cookie | Có phiên tại ứng dụng không tự bảo đảm phiên IdP còn tồn tại |
| OAuth2 Resource Server | Bảo vệ API bằng access token | JWT hoặc opaque token | API không nên chấp nhận ID Token chỉ vì nó có chữ ký hợp lệ |

**Ví dụ:** Công ty dùng một IdP cho cổng nhân viên và hệ thống báo cáo. Cả hai RP đã đăng ký với cùng IdP. Người dùng xác thực tại IdP khi vào cổng; khi mở báo cáo, trình duyệt được chuyển đến IdP và có thể nhận kết quả đăng nhập nhanh do phiên IdP còn hiệu lực. Dù vậy, báo cáo vẫn phải tự áp dụng chính sách vai trò riêng; một nhân viên chưa chắc được xem báo cáo tài chính.

## 4. Những điều kiện khiến “tin cậy” trở thành kiểm chứng được

1. **Nguồn phát hợp lệ:** OIDC/JWT kiểm tra `iss` đúng issuer đã cấu hình; SAML kiểm tra IdP entity ID. Không dùng issuer do chính token gợi ý để tự động thêm nhà cung cấp mới vào danh sách tin cậy.
2. **Đúng người nhận:** OIDC ID Token có `aud` chứa `client_id` của RP; access token cho API cần đúng audience của API; SAML Assertion có audience/recipient phù hợp SP.
3. **Toàn vẹn và nguồn ký:** kiểm tra chữ ký bằng khóa đáng tin của issuer tương ứng (OIDC dùng JWKS/metadata; SAML dùng certificate trong metadata). Không chấp nhận token thiếu chữ ký, thuật toán không được phép hoặc khóa lấy tùy tiện từ nội dung chưa tin.
4. **Đúng ngữ cảnh và thời gian:** kiểm tra `exp`, `nbf` khi áp dụng, độ lệch đồng hồ hợp lý; OIDC Authorization Code dùng `state`, `nonce` khi phù hợp, PKCE; SAML xác nhận `InResponseTo`, `Destination`, `SubjectConfirmationData`, điều kiện thời gian và chống phát lại phù hợp với profile/luồng.
5. **Chính xác địa chỉ trả về:** redirect URI của OIDC phải khớp cấu hình tại OP; ACS/entity ID của SAML phải khớp metadata tại IdP. Không xây redirect từ tham số `returnUrl` chưa kiểm soát.
6. **Định danh và ánh xạ người dùng:** với OIDC, khóa định danh bền vững thường là cặp **(`iss`, `sub`)**; không mặc nhiên dùng email làm khóa chính vì email có thể đổi hoặc được tái cấp. Với SAML, chọn NameID/attribute theo hợp đồng dữ liệu đã thống nhất.
7. **Quyền ứng dụng:** mapping group/role phải có nguồn đáng tin, mặc định quyền tối thiểu và kiểm soát tenant. **Đăng nhập thành công không tự cấp quyền ADMIN.**

Có hai ranh giới riêng cần vẽ: (a) **IdP → RP:** RP xác minh danh tính và lập phiên; (b) **AS → Resource Server:** API xác minh access token dành cho nó. Chúng có thể dùng chung issuer nhưng **khác mục tiêu kiểm chứng**.

## 5. Học luồng OIDC trước: Authorization Code và đăng nhập ứng dụng

Với ứng dụng web có server và đăng nhập tương tác:

1. **Đăng ký:** RP có `client_id`, cách xác thực client (chẳng hạn secret được lưu an toàn), tập redirect URI, `issuer-uri` và scope gồm `openid`. OP xuất bản discovery metadata và JWKS.
2. **Khởi tạo:** người dùng mở trang cần bảo vệ. RP chuyển trình duyệt đến authorization endpoint kèm `response_type=code`, `client_id`, `redirect_uri`, scope, `state` và tùy cấu hình `nonce`/PKCE.
3. **IdP xác thực:** OP thực hiện login, MFA, consent hoặc tái sử dụng phiên SSO. RP **không nhận mật khẩu** từ màn hình đăng nhập của OP.
4. **Callback:** OP trả trình duyệt về URI đã đăng ký cùng authorization code và state. RP đối chiếu state với giao dịch đang chờ, loại bỏ callback không gắn với yêu cầu hợp lệ.
5. **Token exchange:** backend RP gửi code đến token endpoint bằng kênh bảo vệ; với PKCE gửi `code_verifier`, và xác thực client theo registration. RP nhận ID Token, thường kèm access token.
6. **Validation và session:** RP xác minh ID Token (issuer, audience, signature, expiration, nonce khi áp dụng), nhận `sub`, ánh xạ tài khoản/quyền, rồi tạo `Authentication` và phiên đăng nhập của ứng dụng.
7. **Truy cập API:** nếu ứng dụng gọi API, nó dùng **access token thích hợp với API**, theo scope/audience và ủy quyền đã cấp. API có chính sách xác thực token và kiểm tra quyền độc lập.

```text
Browser            RP (Spring Security)         OIDC Provider
  | GET /me                |                         |
  |----------------------->|                         |
  |<--- 302 authorize -----|                         |
  |------------ authorization request ------------->|
  |<----------- login / MFA / code -----------------|
  | GET callback?code=...  |                         |
  |----------------------->|--- POST token(code) --->|
  |                        |<-- ID/access tokens ----|
  |                        |-- validate ID token    |
  |<-- session cookie -----|                         |
  | GET /me + cookie       |                         |
  |----------------------->|                         |
  |<-- ứng dụng trả dữ liệu |                         |
```

**Nhìn trong DevTools:** quan sát các URL `/oauth2/authorization/{registrationId}`, authorization endpoint của OP và `/login/oauth2/code/{registrationId}`; xem trạng thái HTTP và cookie. Không ghi lại hoặc chia sẻ code, access token, ID Token, session cookie hay client secret. `state` giúp liên kết request/response và chống login CSRF; PKCE ràng buộc code với bên khởi tạo. Public client phải dùng PKCE; confidential client cũng nên dùng khi nhà cung cấp hỗ trợ.

## 6. Đặt cạnh SAML 2.0 để thấy điểm chung và khác biệt

Trong **SP-initiated SAML Web Browser SSO**:

1. SP và IdP trao đổi metadata chứa **entity ID**, endpoint SSO, **Assertion Consumer Service (ACS)** và chứng thư/khóa xác minh; hai bên cấu hình quan hệ tin cậy.
2. Khi người dùng vào tài nguyên được bảo vệ, SP sinh `AuthnRequest` và chuyển trình duyệt đến IdP.
3. IdP xác thực và gửi **SAML Response/Assertion** qua trình duyệt, thường dùng HTTP POST đến ACS của SP.
4. SP xác minh chữ ký hợp lệ của Response hoặc Assertion theo yêu cầu cấu hình, issuer, audience, recipient/destination, `InResponseTo` nếu có yêu cầu trước đó, điều kiện thời gian và chống replay.
5. SP ánh xạ NameID/attributes thành tài khoản và `Authentication`, sau đó lập phiên ứng dụng.

Trong Spring Security, **RP/SP được cấu hình qua `RelyingPartyRegistration`**, dùng `saml2Login()`. Luồng mặc định thường bắt đầu ở `/saml2/authenticate/{registrationId}`; ACS xử lý `POST /login/saml2/sso/{registrationId}`. `saml2Metadata()` có thể công bố metadata để đăng ký SP tại IdP. Với SAML, cần đặc biệt hiểu **chữ ký XML, certificate rotation, request correlation, Assertion conditions và trường hợp IdP-initiated**, vốn khó đối chiếu giao dịch hơn luồng SP-initiated.

**So sánh thực dụng:** OIDC thường thuận lợi cho ứng dụng web/mobile hiện đại và hệ sinh thái OAuth API; SAML phổ biến ở tích hợp doanh nghiệp cũ. Cả hai đều hỗ trợ SSO, nhưng cấu trúc thông điệp, cơ chế callback, khóa xác minh và vận hành logout khác nhau. Chọn theo yêu cầu IdP và tổ chức, không chọn chỉ vì tên giao thức quen thuộc.

## 7. Trình tự học có thứ tự và tiêu chí hoàn thành

| Chặng | Học và thực hành | Bằng chứng đã hiểu |
| --- | --- | --- |
| 1. Nền tảng | Bảo vệ `/me` bằng Spring Security, phân biệt 302/401/403, session, CSRF và authority | Mô tả được chuỗi request → filter → `Authentication` → phân quyền |
| 2. Ranh giới tin cậy | Vẽ sơ đồ User–Browser–RP–OP–API; liệt kê issuer, audience, redirect, khóa, tenant | Chỉ ra bên nào ký, bên nào xác minh và token nào dành cho ai |
| 3. Giao thức | Đọc OAuth2 Authorization Code, OIDC ID Token/JWKS; so sánh SAML Request/Response/Assertion | Không nhầm ID Token với access token hoặc SAML Assertion |
| 4. Thiết lập IdP | Tạo tenant/realm thử nghiệm, OIDC client, callback, test user và cấu hình MFA nếu có | Có issuer URL chính xác, client registration và user thử |
| 5. Spring OIDC Login | Thêm `spring-boot-starter-oauth2-client`, `oauth2Login()`, cấu hình issuer/secret qua môi trường | Vào `/me` phải login, sau callback nhận đúng `iss` và `sub` |
| 6. Identity & role | Ánh xạ (`iss`, `sub`) vào user nội bộ, policy tenant, authority ở backend | User không có vai trò vẫn bị 403 ở endpoint yêu cầu quyền |
| 7. Bảo vệ API | Thêm Resource Server ở **dịch vụ API**; xác minh access token, `iss`, `aud`, expiration, scope | Access token đúng API được phép; ID Token hoặc token cho API khác bị từ chối |
| 8. SAML đối chiếu | Thử SP registration, metadata, ACS, chữ ký và mapping attributes nếu IdP hỗ trợ SAML | Vẽ được flow SAML và nêu khác biệt với OIDC |
| 9. Đưa vào vận hành | Kiểm thử lỗi và bảo mật, xoay khóa/secret, xử lý logout, TLS/proxy, audit | Có ma trận test âm, runbook thay khóa và rollback |

**Thứ tự khuyến nghị:** hoàn thành chặng 1–5 trước khi mở rộng nhiều IdP hoặc SAML; chặng 6–7 là bắt buộc nếu ứng dụng cần phân quyền thực tế và gọi API. Người học đã có kinh nghiệm OIDC có thể thực hiện chặng 8 sớm hơn, nhưng không bỏ qua kiểm chứng tin cậy.

## 8. Thực hành OIDC Login tối thiểu với Java 17

Đây là một ứng dụng **Spring MVC (Servlet)** dùng Spring Boot **3.5.0** để minh họa. Ví dụ biên dịch được khi có Java 17, Maven và **một OIDC Provider thật** với issuer, client ID/secret, redirect URI hợp lệ. Nó không tự chạy đăng nhập nếu chưa thiết lập IdP; các biến môi trường là bắt buộc.

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>sso-practice</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email
        provider:
          corporate:
            issuer-uri: ${OIDC_ISSUER_URI}
```

**Tệp `src/main/java/demo/sso/SsoApplication.java`:**

```java
package demo.sso;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SsoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoEndpoints {
    @GetMapping("/")
    String index() {
        return "Mo /me de dang nhap bang OIDC";
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "issuer", user.getIdToken().getIssuer().toString(),
                "subject", user.getIdToken().getSubject());
    }
}
```

**Chuẩn bị tại IdP:** tạo OIDC **confidential web client**, đăng ký chính xác callback `http://localhost:8080/login/oauth2/code/corporate`, cấp `openid` (cùng `profile`, `email` nếu chính sách cho phép), lấy `client_id`, secret và issuer URL. Với Keycloak, issuer có dạng `http(s)://<host>/realms/<realm>`; dùng đường dẫn/host thực tế do IdP công bố và bảo đảm khớp tuyệt đối `iss`. Trên môi trường thực, dùng HTTPS cho callback.

**Ví dụ chạy trên terminal Unix/macOS** (thay giá trị bằng credential thử nghiệm, không commit secret):

```bash
export OIDC_ISSUER_URI='https://idp.example.org/realms/demo'
export OIDC_CLIENT_ID='my-web-client'
export OIDC_CLIENT_SECRET='replace-with-real-secret'
mvn spring-boot:run
```

Trên PowerShell, đặt `$env:OIDC_ISSUER_URI`, `$env:OIDC_CLIENT_ID`, `$env:OIDC_CLIENT_SECRET` tương ứng trước khi chạy Maven. **Các tên miền/secret trên chỉ để minh họa**: dùng issuer và client thực mới đăng nhập được.

Mở `http://localhost:8080/` để kiểm tra endpoint công khai; mở `http://localhost:8080/me` hoặc `http://localhost:8080/oauth2/authorization/corporate` để bắt đầu đăng nhập. Sau khi xác thực thành công, `/me` trả JSON với **issuer** và **subject** của ID Token đã xác minh, ví dụ hình dạng `{"issuer":"https://...","subject":"..."}`. Giá trị cụ thể do IdP cấp nên không có stdout cố định. Nếu chưa có session, trình duyệt có thể thấy trang chọn đăng nhập trước khi chuyển sang OP. Mẫu này **chưa triển khai nghiệp vụ phân quyền, tài khoản nội bộ hay logout liên kết**.

**Giải thích code:** `spring-boot-starter-oauth2-client` cung cấp OIDC/OAuth2 client; `issuer-uri` cho phép khám phá endpoint và khóa từ metadata; `oauth2Login()` tích hợp luồng đăng nhập và thiết lập `Authentication`; `SecurityFilterChain` chỉ công khai `/`, `/error`, còn `/me` phải xác thực. `OidcUser` thể hiện principal sau login; ID Token trong ví dụ chỉ dùng để đọc danh tính tại RP, **không gửi làm bearer token cho API**.

**Khi thêm API riêng:** API cần `spring-boot-starter-oauth2-resource-server`, cấu hình JWT với issuer và audience của **API**, ví dụ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
          audiences: api://orders
```

Đoạn YAML này mô tả **cấu hình của một dịch vụ API Resource Server**, không thêm trực tiếp vào mẫu Login bên trên rồi mặc định coi mọi endpoint đã được bảo vệ bằng Bearer Token. API cần filter chain phù hợp, `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` hoặc cấu hình mặc định tương thích, và rule phân quyền theo scope/role của mình. Với access token opaque, dùng introspection thay vì giải mã JWT.

## 9. Nếu bắt buộc tích hợp SAML thay cho OIDC

Tư duy từ mục 3–4 vẫn giữ nguyên, nhưng chuyển sang cấu hình **SP/Relying Party** trong Spring Security:

1. Bổ sung dependency `spring-security-saml2-service-provider` và cấu hình `RelyingPartyRegistration`/IdP metadata.
2. Tại IdP khai báo **SP entity ID**, **ACS URL** và chứng thư ký SP nếu chính sách yêu cầu.
3. Trong `SecurityFilterChain` sử dụng `saml2Login(Customizer.withDefaults())` (cùng rule truy cập phù hợp).
4. Kiểm tra luồng `AuthnRequest` → `SAMLResponse` → ACS; bảo đảm chữ ký và điều kiện Assertion được xác minh trước khi lập session.
5. Mapping SAML NameID/attributes vào identity nội bộ theo hợp đồng; kiểm thử cả certificate rotation và IdP downtime.

**Không sao chép thông số OIDC sang SAML:** OIDC có `client_id`, redirect URI, JWKS/ID Token; SAML có SP/IdP entity ID, ACS, metadata XML và X.509 signature. Nếu IdP yêu cầu request ký hoặc Assertion mã hóa, phải cung cấp credential ký/giải mã tương ứng. Với SAML nên ưu tiên cấu hình thông qua metadata được quản lý và kiểm soát thay đổi, thay vì dán certificate thủ công ở nhiều nơi.

## 10. Ma trận kiểm thử trước khi gọi là “SSO hoạt động”

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Người dùng chưa đăng nhập truy cập trang bảo vệ | Chuyển tới luồng login; sau khi thành công mới có session |
| Login hợp lệ tại OP/IdP | ID Token/Assertion hợp lệ, identity đúng, lập phiên ứng dụng |
| Issuer/entity ID không nằm trong danh sách tin cậy | Từ chối xác thực |
| Chữ ký sai, dùng khóa không đáng tin, token/assertion hết hạn | Từ chối xác thực |
| ID Token sai `aud`, access token của API khác, thiếu scope | Từ chối tại bên nhận tương ứng |
| Callback OIDC sai `state`, code dùng lại, PKCE sai | Không hoàn thành login |
| SAML Response/Assertion bị replay, sai audience/recipient hoặc correlation | Không lập phiên |
| Người dùng đã login nhưng thiếu quyền nghiệp vụ | Trả 403 tại tài nguyên cần quyền; không tự tăng quyền |
| Một user dùng nhiều IdP/tenant | Danh tính không bị nhập nhằng; kiểm tra (`iss`, `sub`) và tenant |
| Khóa/certificate được xoay | Chỉ chấp nhận khóa hợp lệ theo lịch xoay; có phương án cập nhật metadata và rollback |
| OP/IdP tạm ngừng hoặc callback lỗi | Lỗi rõ ràng, không bỏ qua xác minh, không tạo phiên sai |
| Logout ứng dụng / logout IdP | Nêu rõ phiên nào bị xóa và khả năng SLO/front-channel/back-channel tùy giao thức, IdP |

**Cách kiểm chứng thủ công:** xem network trace đã che bí mật, log debug có chọn lọc của Spring Security, cấu hình registration tại OP và trạng thái phiên sau callback; đối chiếu issuer/audience với metadata. Kiểm thử âm bằng môi trường thử nghiệm; không tự sửa chữ ký token hoặc gửi payload thử nghiệm vào dịch vụ sản xuất.

## 11. Lỗi phổ biến và cách suy luận

- **`redirect_uri_mismatch`:** callback thực tế khác URI đăng ký (scheme/host/port/path hoặc reverse proxy). So sánh giá trị thực từ authorization request với IdP client registration; cấu hình trusted forwarded headers đúng và không tin `X-Forwarded-*` từ client bên ngoài.
- **`invalid_client` hoặc lỗi token endpoint:** sai client ID/secret, phương thức xác thực client, hoặc secret đã xoay; kiểm tra trong kho bí mật, không in secret ra log.
- **`invalid_issuer`, audience mismatch hoặc signature invalid:** nhầm realm/tenant, sai `issuer-uri`, JWKS không tương ứng, clock skew hay khóa vừa xoay. Không “sửa nhanh” bằng cách tắt xác minh.
- **Đăng nhập xong nhưng 403:** xác thực thành công nhưng ứng dụng chưa ánh xạ role/authority hoặc token thiếu scope; sửa rule và nguồn ánh xạ có kiểm soát thay vì cấp quyền rộng.
- **Vòng lặp login:** session cookie không được trả lại, `SameSite`/`Secure` không phù hợp, proxy sai scheme, nhiều instance không chia sẻ session hoặc callback không khôi phục được yêu cầu; kiểm tra cookie và chuỗi redirect.
- **Dùng ID Token gọi API:** Resource Server nhận nhầm loại token hoặc audience; gửi access token được cấp cho API và kiểm tra `aud`/scope ở API.
- **Nhầm logout cục bộ và Single Logout:** xóa session RP không nhất thiết kết thúc phiên IdP; thiết kế OIDC RP-Initiated Logout/SAML SLO nếu business thực sự yêu cầu và IdP hỗ trợ.
- **SAML invalid response:** sai ACS, entity ID, certificate, thời gian Assertion, recipient, signature hoặc `InResponseTo`; đối chiếu metadata hai phía và log đã loại thông tin nhạy cảm.

## 12. Bài tập kết thúc và tiêu chí đạt

**Bài tập A – thiết kế:** Cho hai ứng dụng `portal.example.org` và `reports.example.org` dùng chung IdP, hãy vẽ flow đăng nhập cho cả hai; ghi rõ chỗ có thể tái dùng phiên IdP và chỗ mỗi RP phải xác minh message, lập session và tự phân quyền. Giải thích vì sao SSO không chứng minh quyền xem báo cáo.

**Bài tập B – tích hợp:** Chạy ứng dụng tại mục 8 với một OIDC Provider thử nghiệm. Ghi lại issuer, `client_id`, callback và các bước redirect (không lưu token hoặc secret). Truy cập `/me` ở trình duyệt mới, chứng minh chỉ khi login xong mới thấy `iss`/`sub`.

**Bài tập C – kiểm thử bảo mật:** Thử một đăng ký callback sai và một issuer không trùng cấu hình; quan sát việc đăng nhập thất bại. Thêm endpoint yêu cầu một authority mà user chưa có và xác minh nhận 403 sau login. Giải thích vì sao cần kiểm tra `aud` ở API dù ID Token có chữ ký hợp lệ.

**Đạt bài** khi giải thích được đủ **ai phát hành → ai kiểm chứng → chứng cứ tin cậy → ai tạo phiên → ai kiểm tra quyền** cho cả OIDC và SAML; chạy được OIDC login thật trong môi trường thử nghiệm; và trình bày được ít nhất năm tình huống từ chối xác thực hoặc phân quyền. Đây là nền tảng để tiếp tục các chủ đề federation nâng cao: nhiều IdP, tenant routing, provisioning/SCIM, step-up MFA, liên kết tài khoản và vòng đời phiên.

## Nguồn đối chiếu chính thức

- Spring Security – OAuth2 Login Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Client Authorization Grants/PKCE: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OpenID Connect Core 1.0 – ID Token Validation: https://openid.net/specs/openid-connect-core-1_0.html
