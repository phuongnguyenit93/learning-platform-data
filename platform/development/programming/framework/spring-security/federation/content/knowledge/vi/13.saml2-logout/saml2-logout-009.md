# Xử lý CSRF cho thao tác đăng xuất do người dùng khởi tạo trong SAML 2.0

> **Chủ đề:** Spring Security – federation · **Nhóm:** Đăng xuất SAML2. Bài học tập trung vào **logout do người dùng bấm tại Service Provider (SP)** và cách giữ bảo vệ CSRF, đồng thời giải thích vì sao **SAML Single Logout (SLO) callback từ Identity Provider (IdP)** dùng xác minh chữ ký/giao thức thay cho token HTML form của SP. Ví dụ Spring Security dành cho Servlet stack Spring Boot 3.x / Spring Security 6.x, còn ví dụ Java độc lập cần JDK 17+.

## 1. Vì sao đăng xuất cũng phải chống CSRF?

Người dùng đã xác thực bằng SAML SSO tại `https://portal.example.org`. Nếu ứng dụng triển khai `GET /logout` để ngay lập tức xóa phiên, một website khác có thể nhúng link, hình ảnh, iframe hoặc redirect tới địa chỉ đó. Trình duyệt có thể đính kèm cookie phiên của người dùng tùy bối cảnh, làm họ bị logout dù không hề bấm nút trong ứng dụng.

Ví dụ **mẫu tấn công** để hiểu nguyên nhân, không phải code ứng dụng được khuyến nghị:

```html
<img src="https://portal.example.org/logout" alt="">
```

Với ứng dụng bật RP-initiated SAML SLO, thao tác bị giả mạo có thể còn khởi động luồng logout tại IdP hoặc các ứng dụng liên thông. Điều này gây gián đoạn, vòng lặp đăng nhập và có thể ảnh hưởng các tác vụ nghiệp vụ đang mở.

**Nguyên tắc cốt lõi:** Logout do chính user khởi tạo là hành động thay đổi trạng thái, cần **HTTP POST + CSRF token hợp lệ**. Không dùng GET để hủy phiên; cũng không coi POST hoặc SameSite cookie là đủ nếu thiếu token.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **local logout**, **RP-initiated SAML SLO**, **AP/IdP-initiated SLO** và SLO response callback.
2. Giải thích vì sao `POST /logout` cần CSRF token, còn `POST /logout/saml2/slo` từ IdP dùng **chữ ký SAML và kiểm tra giao thức**.
3. Cấu hình Spring Security `saml2Logout()` mà **không tắt CSRF toàn bộ ứng dụng**.
4. Tạo form POST có CSRF token trong Thymeleaf/MVC và hiểu vấn đề JavaScript SPA.
5. Giới hạn ngoại lệ CSRF đúng callback; không miễn `/logout/**` hoặc user logout endpoint.
6. Kiểm thử thiếu/sai token, callback không ký, session timeout, SameSite, multi-node và logout một phần.

## 2. Phân biệt các luồng logout

| Hành vi | Bên khởi tạo | Endpoint SP phổ biến | Điều kiện tin cậy |
| --- | --- | --- | --- |
| **Local logout** | User nhấn logout trong SP | `POST /logout` | CSRF token của SP, session/cookie đúng |
| **RP-initiated SAML SLO** | User nhấn logout ở SP, sau đó SP tạo LogoutRequest | `POST /logout` nếu SLO mặc định, có thể đổi sang `POST /saml2/logout` | CSRF token tại request browser→SP; tiếp theo chữ ký SAML |
| **IdP/AP-initiated SLO** | IdP phát SAML LogoutRequest | `POST /logout/saml2/slo` với `SAMLRequest` | SAML signature, issuer, destination, identity/session |
| **SLO response callback** | IdP đáp lại LogoutRequest do SP gửi | `POST /logout/saml2/slo` với `SAMLResponse` | SAML signature, issuer, status, `InResponseTo`, request state |

**Không nhầm** `POST /logout` với `POST /logout/saml2/slo`. URL thứ nhất là lệnh từ trang web của người dùng; URL thứ hai là cổng nhận bản tin SAML giao thức từ IdP thông qua browser.

### 2.1. RP-initiated SLO từ nút Đăng xuất

```text
User browser                Spring Security SP                  SAML IdP
     |                              |                              |
     | POST /logout + _csrf       |                              |
     |---------------------------->|                              |
     |       CsrfFilter kiểm tra token                              |
     |       LogoutFilter / LogoutHandlers                          |
     |       kết thúc phiên SP, clear SecurityContext               |
     |       Saml2RelyingPartyInitiatedLogoutSuccessHandler         |
     |       tạo/ký SAML LogoutRequest, lưu state                    |
     |<----------------------------| redirect/POST sang IdP SLO     |
     |------------------------------------------------------------>|
     |                              |         IdP xử lý logout    |
     |<------------------------------------------------------------|
     | POST /logout/saml2/slo (SAMLResponse)                       |
     |---------------------------->|                              |
     |       Saml2LogoutResponseFilter                              |
     |       validate signature, status, InResponseTo              |
     |<----------------------------| success/error UX               |
```

Theo tài liệu Spring Security, SP có thể kết thúc phiên local **trước khi** nhận LogoutResponse. IdP không bảo đảm lúc nào cũng trả về, và SLO có thể thất bại một phần. Không hiển thị “đã đăng xuất mọi nơi” chỉ dựa trên việc SP phát một LogoutRequest.

### 2.2. IdP-initiated SLO

```text
IdP -> Browser -> POST /logout/saml2/slo
                 form field SAMLRequest
                         |
                         v
                Saml2LogoutRequestFilter
                + SAML LogoutRequest validator
                         |
                 IdP signature hợp lệ?
                 Issuer/Destination đúng?
                 NameID/SessionIndex/session đúng?
                         |
           Hợp lệ -> local session cleanup -> ký LogoutResponse
           Sai     -> reject, không logout tùy tiện
```

SAML callback không mang token `_csrf` do SP render vì IdP không sở hữu token đó. Điều này **không** cho phép bất kỳ POST nào tới callback hủy phiên: bản tin phải qua SAML validation. Một `SAMLRequest` thiếu chữ ký hoặc ký bằng key lạ không được tin.

## 3. Cơ chế CSRF ở browser

CSRF (Cross-Site Request Forgery) xảy ra khi website không đáng tin thúc đẩy browser nạn nhân gửi request thay đổi trạng thái đến ứng dụng đang có session authentication. Browser có thể gửi cookie tự động, nên attacker không cần đọc cookie.

**POST một mình không đủ:** cross-site HTML form cũng có thể POST:

```html
<!-- Minh họa mối đe dọa, không triển khai -->
<form method="post" action="https://portal.example.org/logout">
  <button type="submit">Click</button>
</form>
```

SP cần một token chỉ cấp/kiểm tra trong ngữ cảnh phiên đúng. Attacker thông thường không truy xuất được token từ trang SP do browser same-origin policy.

### 3.1. Bất biến cần bảo đảm

- `GET /logout` không hủy session, kể cả khi do user click hoặc browser prefetch.
- `POST /logout` hoặc RP user logout URL tùy biến phải mang CSRF token hợp lệ.
- Token thiếu, sai, hết hạn hoặc thuộc session khác bị từ chối **trước khi logout handlers chạy**.
- Chỉ khi CSRF hợp lệ, SP mới được hủy local session và phát signed SAML LogoutRequest nếu cấu hình SLO.
- SLO callback không dùng token form làm chứng cứ IdP hợp lệ; nó cần **signature/trust/issuer/destination/correlation**.
- Không log token, session cookie, RelayState bí mật hoặc raw SAML messages.

### 3.2. Những khái niệm không thể thay thế nhau

| Dữ liệu | Mục đích | Có thay token CSRF logout của user không? |
| --- | --- | --- |
| `_csrf` hoặc `X-CSRF-TOKEN` | Chứng minh POST được thực hiện trong browser/session context được phép | **Là token được dùng** |
| `JSESSIONID` hoặc `SESSION` | Xác định phiên browser | Không; cookie có thể tự gửi |
| `RelayState` | State liên kết luồng SAML | Không |
| `InResponseTo` | Correlate LogoutResponse với LogoutRequest | Không |
| `SigAlg`/`Signature` hoặc XML `ds:Signature` | Verify bản tin SAML của signer tin cậy | Không bảo vệ user click ban đầu |
| `SameSite` | Hạn chế ngữ cảnh gửi cookie | Defense-in-depth, không thay token |
| `Origin`/`Referer` | Kiểm tra nguồn bổ sung | Không thay token mặc định |
| CORS | Điều khiển quyền đọc response và một số cross-origin requests | Không chặn mọi cross-site form POST |

## 4. Spring Security xử lý logout và CSRF mặc định

Ở Spring Security Servlet, CSRF protection được bật theo mặc định trong cấu hình thông thường. `CsrfFilter` kiểm tra các HTTP methods không an toàn, trong đó có POST. Với logout:

- `GET /logout` có thể hiển thị **trang xác nhận** kèm CSRF token, không thực hiện logout ngay.
- `POST /logout` có token đúng mới được `LogoutFilter` xử lý.
- `POST /logout` thiếu/sai token thông thường trả `403 Forbidden`; status cụ thể tùy `AccessDeniedHandler`.
- Logout handlers có thể invalidate session, clear `SecurityContext` và xóa CSRF token cũ.

Đây là hành vi đúng theo tài liệu Spring Security, không phải lỗi do SAML.

### 4.1. Cấu hình phải tránh

```java
// ANTI-PATTERN: không tắt CSRF toàn ứng dụng dùng cookie/session.
http.csrf(csrf -> csrf.disable());
```

Tắt CSRF có thể cho phép GET logout làm thay đổi state theo default/custom logout behavior, và làm các endpoint POST/PUT/PATCH/DELETE khác mất phòng vệ. Callback SAML không có token không phải lý do tắt CSRF toàn cục.

`permitAll()` là kiểm tra **authorization**; nó không mặc nhiên tắt CSRF. Đừng nhầm giữa authorization, CSRF và SAML signature validation.

## 5. Spring Security 6.x: bật SAML Single Logout và giữ CSRF

Tạo `SamlLogoutSecurityConfig.java` trong một ứng dụng Spring Boot có SAML2 Service Provider dependencies:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **class cấu hình Spring**, không có `main` chạy độc lập bằng `javac`. Để hoạt động cần bean `RelyingPartyRegistrationRepository`, metadata IdP tin cậy, signing key/certificate và IdP hỗ trợ Single Logout. `csrf(Customizer.withDefaults())` thể hiện yêu cầu CSRF bảo vệ lệnh user-initiated logout.

`saml2Logout()` kích hoạt luồng SLO của Spring Security. Nếu login bằng SAML và registration có SLO capability, POST logout hợp lệ có thể được Spring xử lý thành RP-initiated SLO.

### 5.1. Ví dụ application.yml cho registration

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "https://login.example.org/metadata/saml"
```

Đây là **cấu hình minh họa**, chưa chạy nếu thiếu key/cert/file thực tế. IdP metadata cần công bố `SingleLogoutService` và verification certificates, SP phải có signing credential đúng vai trò. `singlelogout.url` là **callback SLO của SP**, không phải `POST /logout` do user gửi.

`{baseUrl}` và `{registrationId}` là URI placeholders của Spring Security, đòi public HTTPS host/port đúng qua reverse proxy. Không dùng internal HTTP host làm SLO destination trên production.

### 5.2. Không tạo controller GET /logout để hủy session

```java
// SAI: GET dễ bị browser khác kích hoạt.
// @GetMapping("/logout")
// public String logout(HttpSession session) {
//     session.invalidate();
//     return "redirect:/login";
// }
```

Custom controller này bỏ CSRF, bỏ các handlers chuẩn của Spring Security và có thể không tạo SAML LogoutRequest đúng cách.

## 6. Form đăng xuất an toàn

### 6.1. Thymeleaf

Trong trang Thymeleaf tích hợp Spring Security/Spring MVC:

```html
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất</button>
</form>
```

Khi `RequestDataValueProcessor`/CSRF support được tích hợp đúng, Thymeleaf có thể tự thêm hidden CSRF input cho POST. Hãy xác nhận bằng HTML đã render trong DevTools thay vì mặc định tin rằng token luôn có mặt.

HTML sau render có thể trông như:

```html
<form action="/logout" method="post">
  <input type="hidden" name="_csrf" value="SERVER_GENERATED_TOKEN"/>
  <button type="submit">Đăng xuất</button>
</form>
```

`SERVER_GENERATED_TOKEN` chỉ là chuỗi minh họa, không phải secret thực. Không hardcode token vào template. Nếu dùng view engine không tự inject token, lấy `CsrfToken` do Spring Security expose trong request attribute `_csrf` rồi render hidden input với `parameterName` và `token` đúng phiên bản.

**Không đưa token vào query URL**, vì có thể lộ qua access logs, browser history, referrer, monitoring hoặc ảnh chụp màn hình.

### 6.2. Không dùng GET link làm thao tác hủy phiên

```html
<!-- Link có thể mở trang confirmation, nhưng không được hủy session -->
<a href="/logout">Đăng xuất</a>
```

Với CSRF enabled, GET thường chỉ hiển thị confirmation để người dùng submit form POST. Nếu muốn một nút duy nhất, dùng form POST. Nếu muốn link style, JavaScript có thể submit form POST có token và phương án không dùng JS dẫn tới trang confirmation.

### 6.3. Token cũ, session hết hạn

Token có thể bị xóa/rotate sau login/logout; một form ở tab cũ có thể gặp 403. Xử lý bằng cách cập nhật token hoặc thông báo reload/login lại, không bằng bỏ CSRF. Token CSRF không nhất thiết dùng một lần trong mọi repository; chính sách sinh/lưu/rotate thuộc Spring Security version và `CsrfTokenRepository`.

## 7. Local logout và RP-initiated SLO tách endpoints

Có thể cung cấp hai lựa chọn:

- “Đăng xuất khỏi ứng dụng” → chỉ xóa session SP.
- “Đăng xuất SSO” → SP phát LogoutRequest sang IdP nếu được hỗ trợ.

Spring Security cho phép tách URL:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SeparateLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout.logoutUrl("/logout"))
            .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));

        return http.build();
    }
}
```

Đây là class cấu hình **thay thế** class ở mục 5, không khai báo cả hai chain cùng match toàn bộ URL.

| URL | Mục đích | CSRF |
| --- | --- | --- |
| `POST /logout` | Local logout | **Bắt buộc token** |
| `POST /saml2/logout` | RP-initiated SAML SLO | **Bắt buộc token** |
| `POST /logout/saml2/slo` | IdP SAML callback | SAML signature/protocol validation, không dùng form token |

Hai form có thể cùng lấy CSRF token trong session:

```html
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất cục bộ</button>
</form>

<form th:action="@{/saml2/logout}" method="post">
  <button type="submit">Đăng xuất SSO</button>
</form>
```

**Cả hai endpoint user-facing phải giữ CSRF**, kể cả path có tên SAML.

### 7.1. Không xóa session sớm bằng controller tùy biến

RP-initiated logout cần thông tin principal/registration/`NameID`/`SessionIndex` khi áp dụng để tạo LogoutRequest. Nếu controller tự invalidate session trước khi framework thực thi `Saml2RelyingPartyInitiatedLogoutSuccessHandler`, ngữ cảnh có thể mất.

Để Spring Security điều phối `LogoutHandler` và SAML logout success handler, tránh custom filter xóa state hoặc chặn request trước thời điểm cần.

## 8. CSRF và SAML callback: hai ranh giới khác nhau

`POST /logout/saml2/slo` nhận `SAMLRequest` hoặc `SAMLResponse` từ IdP qua browser. IdP không thể biết CSRF token của trang SP. Vì vậy SAML callback có thể cần ngoại lệ CSRF **chỉ cho endpoint giao thức**, còn các validator phải kiểm tra:

- Đúng `SingleLogoutService` endpoint và HTTP binding.
- SAML XML/Redirect signature và certificate gắn với IdP registration đã tin.
- `Issuer`/`Destination`, message structure, NameID/SessionIndex/session matching khi áp dụng.
- Với LogoutResponse: `InResponseTo`/RelayState, pending `Saml2LogoutRequestRepository`, SAML Status, time/replay policy.
- Chỉ thực hiện local logout đối tượng phù hợp sau khi request đáng tin; không chấp nhận unsigned/fake LogoutRequest.
- Không tải metadata/key từ browser input, không tin XML `KeyInfo` tùy ý.

**Ngoại lệ CSRF không cho quyền đăng xuất user**: nó chỉ cho bản tin đến **SAML validation boundary**.

### 8.1. Ngoại lệ chỉ dành cho đúng callback

Spring Security `saml2Logout()` thường cấu hình protocol filters/matchers tương ứng. Trong môi trường có custom chains/endpoints, cần kiểm tra runtime behavior: callback có bị CSRF chặn trước validation không? Nếu cần tự bổ sung exception, phải giới hạn đúng method/path và test lại.

Fragment dùng trong Spring Security 6.x khi thực sự cần:

```java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

// Fragment cho HttpSecurity. Chỉ dùng khi callback được xử lý
// hoàn toàn bởi SAML LogoutRequest/LogoutResponse validators.
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AntPathRequestMatcher("/logout/saml2/slo", "POST")
));
```

Đây không phải class chạy độc lập. Tùy phiên bản major, `AntPathRequestMatcher` có thể deprecated/thay API. Nếu DSL đã cấu hình exception, không cần thêm một rule trùng. Quan trọng nhất: không cho một controller khác cùng path xử lý request không phải SAML.

### 8.2. Anti-pattern phải từ chối

```java
// SAI: wildcard có thể bao trùm user logout endpoint.
http.csrf(csrf -> csrf.ignoringRequestMatchers("/logout/**"));

// SAI: tắt CSRF toàn bộ web app vì SAML callback không có _csrf.
http.csrf(csrf -> csrf.disable());
```

Nếu callback URL đổi, phải đồng bộ IdP metadata, SAML request/response filter matchers, reverse proxy routes và ngoại lệ CSRF hẹp nếu có. Đừng dùng `permitAll()` để suy luận callback đã an toàn: authorization không thay signature validation.

## 9. LogoutRequest và LogoutResponse phải còn tương quan

Spring Security có `Saml2RelyingPartyInitiatedLogoutSuccessHandler` tạo, ký và gửi LogoutRequest khi user logout hợp lệ. Request có ID/RelayState và được lưu trong `Saml2LogoutRequestRepository` theo cấu hình để verify LogoutResponse trả về.

Điều kiện nhận callback không chỉ là “đến từ IdP”:

1. Chữ ký và issuer thuộc IdP đang trust.
2. `Destination`/SP SLO endpoint đúng.
3. `InResponseTo` khớp request đã phát, trạng thái/RelayState hợp lệ theo repository.
4. `Status` phản ánh kết quả SLO, không giả định mọi response đều thành công.
5. Chống replay, duplicate IDs và tenant/session confusion theo profile.

Phải phân biệt `Saml2LogoutRequestRepository` với `CsrfTokenRepository` và `Saml2AuthenticationRequestRepository` dùng cho đăng nhập. Chúng lưu ba loại state khác nhau và không thay thế được.

### 9.1. IdP-initiated logout không được logout ngẫu nhiên

Khi IdP gửi LogoutRequest, Spring Security `Saml2LogoutRequestFilter`/validator phải xác định issuer/trust và principal hoặc session context đúng. Không dựa vào raw `NameID` chưa được verify để tra bất cứ session nào trong toàn hệ thống rồi invalidate. Không để `POST /logout/saml2/slo` với form rỗng trở thành một “logout all” endpoint.

### 9.2. SLO có thể hoàn tất một phần

IdP có thể không hỗ trợ SLO, browser đóng giữa luồng, LogoutResponse trả lỗi hoặc một SP khác không xử lý yêu cầu. UI cần phân biệt **local session đã hủy** và **federation SLO đã được xác nhận**. Không hứa “đăng xuất tất cả thiết bị” khi SAML SLO chỉ nhắm session theo IdP profile.

## 10. SameSite cookie, CSRF và cross-site POST

`POST /logout` từ trang SP thường same-origin nên browser gửi cookie SP. `POST /logout/saml2/slo` từ IdP thường là cross-site POST; cookie `SameSite=Lax` hoặc `Strict` có thể không đi theo. Nếu SLO callback cần session/request state, kết quả có thể là không tìm được pending LogoutRequest.

Cách điều tra:

1. Trên browser test, kiểm tra `Set-Cookie` ở SP và Cookie header tại callback (không sao chép giá trị cookie vào log/ticket).
2. Xác nhận `SameSite`, `Secure`, `HttpOnly`, `Domain` và `Path`.
3. Xác minh public HTTPS host qua trusted proxy headers, không để internal HTTP URL vào SAML metadata.
4. Với flow cần cookie cross-site POST, có thể cân nhắc `SameSite=None; Secure` theo threat model, cùng CSRF token cho mọi user-initiated actions.
5. Nếu dùng shared session/Redis/multi-node, đảm bảo callback pod khác vẫn tìm được state và không fail-open.
6. Không bỏ `InResponseTo`/signature validation hoặc CSRF của `POST /logout` để sửa cookie issue.

**SameSite là lớp phụ**: `SameSite=None` có thể làm cookie đi cross-site dễ hơn, càng cần CSRF token ở browser logout. CORS không thay CSRF vì cross-origin HTML form không cần đọc response để gây tác động.

## 11. SPA và JavaScript logout

Một ứng dụng SPA dùng Spring Security cookie/session có thể gửi CSRF token qua header:

```javascript
// Fragment: headerName và csrfToken do backend cấp theo cơ chế
// Spring Security tương ứng; không hardcode token.
async function localLogout(headerName, csrfToken) {
  const response = await fetch("/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { [headerName]: csrfToken }
  });
  if (!response.ok) {
    throw new Error("Logout failed");
  }
}
```

**Chú ý:** Fetch không tự tạo top-level navigation sang IdP. Nếu `POST /logout` bắt đầu RP-initiated SAML SLO, Spring Security có thể trả redirect hoặc HTML form tới IdP, nhưng xử lý nó trong fetch không đảm bảo browser hoàn tất SLO. Với SAML Web SSO, **form POST từ main document** thường phù hợp hơn. SPA cần thiết kế flow điều hướng riêng nếu muốn SLO, không coi fetch 200/302 là mọi SP/IdP đã logout.

Nếu SPA lấy CSRF token qua cookie (`CookieCsrfTokenRepository`) hoặc endpoint riêng, cần xem deferred tokens và BREACH/XOR token handling theo Spring Security version. Đừng tự lấy raw token rồi dùng sai request handler. XSS vẫn có thể phá CSRF nếu kẻ xấu chạy script same-origin, nên cần CSP/output encoding.

## 12. Java 17 thuần: kiểm tra ý nghĩa của CSRF trên user logout

Chương trình sau mô phỏng browser gửi method/path/sessionId/token. Đây là **mô hình giáo dục**, không phải `CsrfFilter` của Spring và **không có SAML XML/signature verification**. Các strings minh họa không phải session IDs/tokens đủ entropy cho production.

Lưu `UserLogoutCsrfDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

public class UserLogoutCsrfDemo {

    record Request(String method, String path,
                   String sessionId, String token) {}

    static boolean allowUserLogout(
            Request request, Map<String, String> tokens) {

        if (!"POST".equals(request.method())) {
            return false;
        }
        if (!"/logout".equals(request.path())
                && !"/saml2/logout".equals(request.path())) {
            return false;
        }

        String expected = tokens.get(request.sessionId());
        if (expected == null || request.token() == null) {
            return false;
        }
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8),
                request.token().getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) {
        Map<String, String> sessions = Map.of(
                "session-A", "token-A",
                "session-B", "token-B");

        System.out.println("GET logout: " + allowUserLogout(
                new Request("GET", "/logout", "session-A", "token-A"),
                sessions));
        System.out.println("POST missing token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", null),
                sessions));
        System.out.println("POST wrong token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", "wrong"),
                sessions));
        System.out.println("POST valid token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", "token-A"),
                sessions));
        System.out.println("Cross-session token: " + allowUserLogout(
                new Request("POST", "/logout", "session-A", "token-B"),
                sessions));
        System.out.println("SAML callback as user logout: " + allowUserLogout(
                new Request("POST", "/logout/saml2/slo",
                            "session-A", "token-A"),
                sessions));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac UserLogoutCsrfDemo.java
java UserLogoutCsrfDemo
```

Stdout **chính xác**:

```text
GET logout: false
POST missing token: false
POST wrong token: false
POST valid token: true
Cross-session token: false
SAML callback as user logout: false
```

Giải thích: GET không đổi state; POST thiếu/sai/cross-session token bị từ chối; chỉ POST tới endpoint user logout với token khớp mới được phép bắt đầu. Callback `/logout/saml2/slo` không được coi là user logout; nó phải đi qua SAML validators riêng.

**Giới hạn:** `MessageDigest.isEqual` chỉ minh họa so sánh bytes; dữ liệu session/token giả không có bảo vệ mật mã, và kết quả `true` không chứng minh user đã authenticated. Đừng dùng đoạn code này thay Spring Security `CsrfTokenRepository` hoặc SAML signature/issuer/NameID/SessionIndex/`InResponseTo` validation.

## 13. Kiểm thử với Spring Security MockMvc

Khi có `spring-security-test` và một biến `MockMvc mvc` được cấu hình security filters, có thể kiểm tra thiếu/sai token bị chặn. Fragment:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mvc.perform(post("/logout").with(user("alice")))
        .andExpect(status().isForbidden());

mvc.perform(post("/logout")
        .with(user("alice"))
        .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
```

Fragment trên **không phải class JDK runnable độc lập**; cần Spring Test/MockMvc. Khi custom `AccessDeniedHandler` trả redirect hoặc custom status, assert “không logout” qua session/handler side effects, không chỉ hardcode 403.

Đối với token đúng và RP-initiated SLO, mock principal thông thường `user("alice")` **không phải Saml2AuthenticatedPrincipal**. Cần SAML authentication context, registration/IdP test và signed LogoutRequest/Response fixtures để xác minh SLO thật.

### 13.1. Test matrix cần có

| Tình huống | Kỳ vọng |
| --- | --- |
| `GET /logout` khi CSRF enabled | Không invalidate session |
| External image/link GET logout | Không forced logout |
| `POST /logout` không token | Reject trước logout handlers |
| `POST /logout` sai token | Reject |
| `POST /logout` token session khác | Reject |
| `POST /logout` token đúng với SAML principal | Bắt đầu logout theo SLO config |
| `POST /saml2/logout` không token trong cấu hình tách URL | Reject |
| `POST /saml2/logout` token đúng | RP-initiated SLO |
| `POST /logout` trong cấu hình tách URL | Local logout, không gửi LogoutRequest |
| IdP gửi signed SAMLRequest tới protocol callback | SAML validator tiếp nhận không cần form token |
| IdP gửi unsigned/bad signature SAMLRequest | Reject; không logout ngẫu nhiên |
| Callback SAMLResponse sai `InResponseTo` | Reject |
| SAMLResponse replay hoặc issuer khác IdP đăng ký | Reject |
| POST callback không có SAML field hợp lệ | Không gọi local logout |
| Cookie SameSite chặn callback | Không bypass correlation, xử lý cookie/state |
| LogoutRequest tạo pod A, response về pod B | Có shared state hoặc fail closed |
| Session hết hạn/token stale | Reject an toàn, UI yêu cầu tải lại |
| Logout URL nằm trong wildcard exempt CSRF | Security test phải fail; sửa matcher |
| SLO chỉ local mà UI nói logout mọi nơi | UX test fail; hiển thị scope thật |
| Logs chứa CSRF token/cookies/SAMLResponse | Security QA fail |

### 13.2. Test browser end-to-end

1. Login bằng IdP test có SLO và user giả.
2. Xem form logout render token (không chia sẻ giá trị).
3. GET /logout xác nhận phiên vẫn còn.
4. POST thiếu/sai token xác nhận reject và **không** gửi LogoutRequest.
5. POST token đúng xác nhận local logout và signed LogoutRequest, nếu SLO enabled.
6. IdP trả LogoutResponse; SP verify `InResponseTo` và status.
7. IdP gửi LogoutRequest hợp lệ và giả/unsigned; SP chỉ xử lý request hợp lệ.
8. Test callback cross-site POST, SameSite cookie, các pods khác nhau.
9. Kiểm tra không có token/session/raw SAML trong logs/APM/WAF.
10. Kiểm tra thông báo UI phân biệt local logout và federation SLO completion.

## 14. Chẩn đoán sự cố

| Triệu chứng | Khả năng chính | Cách xử lý |
| --- | --- | --- |
| Bấm logout nhận 403 | Token thiếu/sai/stale, session timeout | Render token đúng, refresh/reload; không tắt CSRF |
| GET logout chỉ hiện confirmation | Hành vi an toàn | Submit form POST |
| GET logout làm xóa phiên ngay | Custom GET logout hoặc CSRF disabled | Khôi phục POST+CSRF |
| POST token đúng nhưng không có SLO | Chưa bật `saml2Logout()`, IdP thiếu SLO metadata, không phải SAML principal | Kiểm tra registration/SLO/handler |
| Callback IdP bị CSRF 403 | Custom matcher/chain chưa cho protocol POST | Giới hạn ngoại lệ đúng callback, không wildcard |
| Callback unsigned vẫn logout user | Không đi qua SAML validator | Khôi phục filters/trust/signature/identity checks |
| SLO Response `InResponseTo` sai | State mất/session/tenant/routing | Rà LogoutRequest repository và cookie |
| SP logout xong, login lại không hỏi password | IdP session vẫn sống | Phân biệt local vs SLO |
| SPA fetch không điều hướng IdP | Fetch không thay top-level navigation | Form POST/flow navigation phù hợp |
| SLO partial failure | IdP/ứng dụng khác không hoàn tất | Báo trạng thái thật, không hứa global logout |
| CSRF token nằm trong URL/log | UI hoặc tracing sai | Chuyển hidden field/header, scrub logs |
| Nhiều filter chains khiến user logout không có CSRF | Matcher/priority sai | Test chính xác chain và endpoints |

**Đừng suy lỗi chỉ từ status:** 403 có thể do CSRF hoặc authorization, 400 từ SAML validator, 302 có thể là IdP redirect hoặc login page. Điều tra theo thứ tự: browser logout POST → CSRF → logout handlers → SAML request → IdP → SAML response callback. Dùng event/reason code thay vì raw SAML payload.

## 15. Checklist production

- [ ] User logout dùng POST; GET không mutate session.
- [ ] Token CSRF của Spring Security được render, gửi và verify.
- [ ] Cả local logout lẫn RP-initiated logout URL tùy biến đều cần token.
- [ ] Không `csrf.disable()` và không wildcard ignore `/logout/**`.
- [ ] `saml2Logout()` và IdP `SingleLogoutService`/SP credentials cấu hình đúng.
- [ ] Callback `/logout/saml2/slo` chỉ cho SAML validation xử lý, không có custom logout controller mở.
- [ ] Nếu cần exception CSRF, chỉ đúng method/path callback và test POST giả bị từ chối.
- [ ] Signed LogoutRequest/LogoutResponse được verify trust/issuer/destination/NameID/`InResponseTo`/status/replay.
- [ ] `RelayState` không dùng làm CSRF token hay open redirect.
- [ ] SameSite/cookie/session/HTTPS/proxy được test với cross-site POST.
- [ ] Multi-node LogoutRequest state không mất hoặc fail closed.
- [ ] CSRF token stale/session timeout xử lý không cần bypass.
- [ ] SPA dùng browser navigation thích hợp cho SAML SLO.
- [ ] Local logout và SLO completion được thể hiện đúng trong UI.
- [ ] Logs, metrics, APM và WAF không chứa CSRF/session tokens, raw SAML messages hoặc private key.
- [ ] Đã test GET, token missing/wrong/cross-session, unsigned SLO, wrong issuer, bad InResponseTo, replay và lost cookie.

## 16. Câu hỏi ôn tập

**1. Vì sao logout phải chống CSRF?**  
Browser có thể tự mang session cookie trong request do trang khác khởi phát; attacker không cần đọc cookie.

**2. Chỉ yêu cầu POST đã đủ chưa?**  
Chưa. HTML form cross-site có thể POST. Cần CSRF token hợp lệ.

**3. IdP callback `POST /logout/saml2/slo` có cần token form `_csrf` không?**  
Không. Đây là SAML protocol callback; phải verify chữ ký/trust và các điều kiện SAML, không dựa vào token form SP.

**4. Có thể exempt `/logout/**` để giải lỗi IdP callback không?**  
Không. Wildcard có thể bỏ CSRF ở chính user logout endpoint; chỉ exempt callback chính xác nếu thực sự cần.

**5. `GET /logout` hiện confirmation có phải bug?**  
Không. Đây là cách tránh GET tự hủy phiên, dùng form POST có token.

**6. Chữ ký SAML LogoutRequest có thay CSRF token cho `POST /logout` không?**  
Không. SP chỉ tạo bản tin ký **sau** khi nhận lệnh browser; lệnh ban đầu vẫn cần CSRF.

**7. SameSite=Lax bảo đảm IdP callback nhận session cookie không?**  
Không, cross-site POST có thể không gửi cookie. Cần test browser và policy cookie/state.

**8. SLO phát request thành công có đồng nghĩa logout tất cả SP khác không?**  
Không. Phụ thuộc IdP response, profile và khả năng từng ứng dụng.

**9. SPA gọi fetch POST /logout có tự điều hướng tab đến IdP không?**  
Không chắc. SAML SLO là browser flow, thường nên dùng top-level form POST.

**10. LogoutResponse ký hợp lệ nhưng `InResponseTo` sai có được chấp nhận không?**  
Không. Phải correlate đúng LogoutRequest đã lưu và các điều kiện giao thức.

## 17. Tài liệu tham khảo

- [Spring Security 6.5 — Performing Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html): RP/AP SLO, endpoints, LogoutRequest/Response và tách local/SLO.
- [Spring Security — CSRF protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): logout CSRF, form, session timeout, SPA.
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET confirmation và POST logout/handlers.
- [Spring Security — Testing CSRF with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` và invalid token.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): LogoutRequest/Response, InResponseTo và Status.
- [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Single Logout Profile.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-POST/Redirect và RelayState.
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF token và defense in depth.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session/cookie/logout.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): SAML signature/trust và validation.

**Ghi nhớ:** **Người dùng bấm Đăng xuất tại SP → POST có CSRF token**. **IdP gửi SAML LogoutRequest/LogoutResponse → callback SLO xác minh chữ ký và giao thức**. Hai cơ chế bổ sung cho nhau, không thay thế nhau. Không tắt CSRF toàn cục, không exempt wildcard user logout và không tuyên bố đã logout toàn federation khi chưa biết kết quả SLO.