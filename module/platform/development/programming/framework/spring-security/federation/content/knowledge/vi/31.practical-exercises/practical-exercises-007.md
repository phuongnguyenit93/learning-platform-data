# Tích hợp CAS Login, xác minh Service Ticket và Single Sign-Out

## 1. Mục tiêu của bài thực hành tổng hợp

Trong **Spring Security - federation**, bài thực hành này kết hợp ba công việc cần được thiết kế như **một quy trình đăng nhập–phiên–đăng xuất hoàn chỉnh**:

1. **CAS Login**: chuyển người dùng từ ứng dụng Spring Security (gọi là *service* hoặc CAS client) sang máy chủ Central Authentication Service (CAS Server) để đăng nhập tập trung.
2. **Xác minh Service Ticket (ST)**: chỉ cấp `Authentication` và local `HttpSession` sau khi ứng dụng xác minh ticket với CAS Server qua back-channel HTTPS, cho **đúng service URL**, và áp dụng chính sách tài khoản/quyền nội bộ.
3. **Single Sign-Out (SLO)**: khi kết thúc phiên CAS SSO, ứng dụng tiếp nhận logout notification và vô hiệu hóa **đúng phiên local có liên hệ với service ticket**, không xóa mù mọi phiên theo username.

Đây là **CAS protocol**, không phải SAML 2.0 Web SSO dù thông báo CAS logout có thể sử dụng XML theo namespace SAML 2.0. Không được dùng `Saml2WebSsoAuthenticationFilter` để thay cho `CasAuthenticationFilter`, hay giả định OIDC `id_token`, CAS `ticket` và SAML `Assertion` có thể dùng thay cho nhau.

### 1.1. Những kết quả có thể kiểm chứng

Sau khi hoàn thành, một nhóm phát triển có thể chứng minh:

- User `alice` truy cập `/reports` khi chưa có phiên local sẽ được chuyển đến `https://sso.example.org/cas/login?...`.
- CAS Server đăng nhập người dùng và redirect đến **chính xác** `https://portal.example.org/login/cas?ticket=ST-...`.
- Spring Security gọi `https://sso.example.org/cas/serviceValidate`, đưa **đúng** `ticket` và `service`.
- Chỉ sau phản hồi validation thành công, ứng dụng mới tạo `Authentication` và session; tài khoản local disabled hoặc thiếu quyền bị từ chối.
- Cùng một ST hoặc ST dành cho một service khác **không** được sử dụng lại.
- POST `/logout` local kết thúc phiên ứng dụng nhưng **không mặc định kết thúc CAS TGT**.
- Đăng xuất toàn cục qua CAS `/logout`, khi CAS SLO được bật và delivery thành công, sẽ làm mất phiên tại những CAS clients có xử lý SLO.
- SLO callback giả không được dùng để buộc ứng dụng hủy phiên; callback đúng chỉ hủy session ánh xạ với ticket liên quan.
- Trong cluster, ticket/session mappings và local session storage có thiết kế nhất quán qua các nodes, hoặc giới hạn triển khai được ghi rõ.

**Nguyên tắc:** CAS xác thực tập trung; ứng dụng Spring Security vẫn chịu trách nhiệm session local, local account admission, phân quyền và xử lý SLO. Một HTTP redirect thành công hoặc một chuỗi bắt đầu bằng `ST-` không phải bằng chứng xác thực người dùng.

## 2. Từ vựng và ranh giới tin cậy

| Đối tượng | Nằm ở đâu / ai kiểm soát? | Vai trò | Giới hạn bảo mật |
| --- | --- | --- | --- |
| **CAS Server** | `https://sso.example.org/cas` | Login, lưu SSO session/TGT, phát và xác minh ST, gửi SLO notifications nếu được cấu hình. | Chỉ endpoint CAS Server đã được tin qua HTTPS/TLS; service registry giới hạn clients. |
| **CAS service / Portal** | `https://portal.example.org` | Spring app cần login tập trung, xác minh ST, tạo SecurityContext và HttpSession. | Không được coi user đã login chỉ vì browser mang ticket. |
| **TGT** (Ticket Granting Ticket) | CAS Server | Nền tảng phát ST cho một phiên CAS SSO. | Không chuyển raw TGT cho Spring app. |
| **TGC** (Ticket Granting Cookie) | Browser trên site CAS | Cookie đại diện phiên SSO để CAS nhận biết browser ở lần login tiếp. | **Khác** JSESSIONID của Spring app. |
| **ST** (Service Ticket) | Browser mang về service callback; CAS Server kiểm tính hợp lệ | Vé opaque, ngắn hạn, **một lần**, dành cho một service cụ thể. | ST là bearer credential, không log URL/ticket raw. |
| **CAS Assertion** | Kết quả **ticket validation** từ CAS Server | Chứa principal và tùy phiên bản CAS/protocol có attributes. | Phải đi từ trusted CAS ticket validator, không lấy từ client header. |
| **Spring Authentication** | `SecurityContext` của app | Principal/authorities sau CAS validation và local admission. | Không tự động có quyền business/admin. |
| **HttpSession / JSESSIONID** | Spring app và browser | Lưu SecurityContext/các dữ liệu local theo session strategy. | Không đồng nhất với CAS TGT/TGC; có TTL riêng. |
| **SLO SessionIndex** | LogoutRequest do CAS gửi theo CAS SLO format | Thường tham chiếu **service ticket ID** để tìm local session. | **Không phải HttpSession ID**, không dùng username để xóa mọi session. |

### 2.1. Hai loại kết nối không được trộn

```text
Browser-facing redirects:
  Browser ----> CAS /login?service=...
  Browser <---- CAS redirect
  Browser ----> Portal /login/cas?ticket=ST-...

Trusted server-to-server:
  Portal ---- HTTPS ----> CAS /serviceValidate?ticket=...&service=...

Single Logout:
  Browser/User ----> CAS /logout
  CAS Server ---- SLO notification ----> Portal service callback
  Portal maps ticket -> local session -> invalidates session
```

**CAS Server xác minh credentials của người dùng**; browser **không** tự xác minh ST, và ứng dụng không “giải mã ST” để biết user. Ticket validator phải hỏi CAS Server thật.

## 3. Môi trường lab và các địa chỉ ví dụ

Một kiến trúc luyện tập gồm:

| Thành phần | URL minh họa | Mục đích |
| --- | --- | --- |
| CAS Server | `https://sso.example.org/cas` | CAS login/validation/logout. |
| CAS Login | `https://sso.example.org/cas/login` | Trang xác thực CAS. |
| ST validation | `https://sso.example.org/cas/serviceValidate` | CAS 2.0 XML validation cho ST. |
| CAS 3 attributes | `https://sso.example.org/cas/p3/serviceValidate` | CAS 3 profile có attributes, khi client cấu hình đúng. |
| CAS logout | `https://sso.example.org/cas/logout` | Hủy CAS SSO session. |
| Spring app | `https://portal.example.org` | Service được bảo vệ. |
| Service callback | `https://portal.example.org/login/cas` | `CasAuthenticationFilter` nhận ST và CAS SLO thường gọi tới service URL này. |
| Protected page | `https://portal.example.org/reports` | Chỉ sau Authentication + authorization. |
| Local logout | `POST https://portal.example.org/logout` | Hủy local session. |
| Sign-out page | `https://portal.example.org/signed-out` | Giải thích local vs global logout. |

**Đây là tên miền minh họa, không phải môi trường có sẵn.** Khi triển khai, dùng HTTPS với certificate hợp lệ; CAS Server có **service registry** cho phép đúng service URL hoặc regex được kiểm duyệt chặt. Đừng đăng ký wildcard mọi URL, wildcard subdomain hoặc `http://` production.

### 3.1. Prerequisites của một thực hành thật

1. Java 17 hoặc mới hơn, Spring Boot/Spring Security Servlet stack đã được hỗ trợ trong tổ chức.
2. Một CAS Server sandbox, tài khoản thử nghiệm `alice` và `bob`, service registry có callback hợp lệ.
3. `spring-security-cas` + Apereo Java CAS Client tương thích với **đúng** Spring Security/Jakarta Servlet runtime; Spring Security 7 docs vẫn có CAS client integration.
4. HTTPS hai chiều ở mức browser→service và service→CAS; truststore đúng CA/hostname.
5. Một `UserDetailsService` hoặc local account directory với trạng thái `enabled/disabled`, tenant và quyền, không tin raw role input từ browser.
6. Có thể xem **redacted** logs của CAS, Spring Security, proxy, session store và delivery của SLO.
7. Có strategy local session, shared store/affinity nếu chạy nhiều nodes; script kiểm thử browser để theo dõi cookie và redirect.

**Version caution:** bài CAS của Spring Security reference có một số XML/description từ thời Spring Security 3.x, tuy đường dẫn tài liệu vẫn hiện diện ở 7.x. Phải kiểm **Javadoc đúng release**, đặc biệt API `CasAuthenticationProvider`, Jakarta Servlet và CAS Client major. Không copy một mẫu namespace cũ rồi khẳng định build được trên mọi Boot release.

## 4. CAS Login theo từng bước: từ `/reports` tới Authentication

### 4.1. Sequence hoàn chỉnh

```text
User Browser              Spring Portal                  CAS Server
    |                          |                              |
    | GET /reports             |                              |
    |------------------------->|                              |
    |                          | unauthenticated              |
    |                          | ExceptionTranslationFilter   |
    |<-------------------------| 302 to CAS login             |
    |                          |                              |
    | GET CAS /login?service=<encoded portal /login/cas>      |
    |-------------------------------------------------------->|
    |                          |                      check TGC |
    |                          |                      or MFA    |
    |<--------------------------------------------------------|
    | 302 Location: https://portal.../login/cas?ticket=ST-A    |
    |                          |                              |
    | GET /login/cas?ticket=ST-A                              |
    |------------------------->|                              |
    |                          | CasAuthenticationFilter      |
    |                          | CasAuthenticationProvider    |
    |                          | HTTPS /serviceValidate       |
    |                          | ticket=ST-A                  |
    |                          | service=exact callback       |
    |                          |----------------------------->|
    |                          |                              | verify
    |                          |                              | ST, service,
    |                          |                              | one-time
    |                          |<-----------------------------|
    |                          | CAS XML success/failure      |
    |                          |                              |
    |                          | load local user + authorities|
    |                          | create Authentication        |
    |                          | SecurityContext / session    |
    |<-------------------------| redirect to safe page        |
    | GET /reports with local JSESSIONID                     |
    |------------------------->|                              |
    |<-------------------------| 200 if authorized             |
```

**Điểm quyết định trust:** `CasAuthenticationProvider` chỉ cấp `Authentication` khi một `TicketValidator` xác minh ST với CAS Server, rồi kết hợp với local account details/authorities. **Local `UserDetailsService` không được xem là CAS password verifier**; nó có thể dùng để tra role/status sau khi danh tính đã xác minh.

### 4.2. CAS TGC khác local session cookie

- Browser có **CAS TGC** khi đã login CAS.
- Portal có **JSESSIONID** riêng sau khi login thành công tại Portal.
- Xóa Portal JSESSIONID nhưng giữ CAS TGC: truy cập Portal protected page có thể được **silent SSO** qua một ST mới, không cần gõ mật khẩu lại.
- Xóa CAS TGC/TGT nhưng không có SLO: Portal JSESSIONID vẫn có thể sống đến khi local session hết hạn hoặc bị logout.
- CAS SLO nỗ lực đóng khoảng cách giữa hai trạng thái, nhưng delivery là **best-effort**, không có bảo đảm tất cả services nhận được callback.

## 5. `Service Ticket`: định danh dịch vụ, một lần, thời gian ngắn

Theo CAS protocol:
- CAS Server cấp ST cho **đúng service** được yêu cầu qua `/login?service=...`.
- Browser quay về service URL với query `ticket=ST-opaque`.
- Service gọi `/serviceValidate` hoặc `/p3/serviceValidate` với ticket và **chính xác service URL tương ứng**.
- ST chỉ được validate **một lần**; kể cả khi validation thất bại vì `INVALID_SERVICE`, ticket bị tiêu thụ theo chuẩn CAS.
- ST có TTL ngắn, không tự chứa credentials để client phân tích.
- Một response `authenticationSuccess` chỉ đáng tin khi đến từ trusted CAS back-channel với TLS CA/hostname verification; không được đọc từ form field do browser đưa.

### 5.1. Điểm dễ làm sai: service URL

```text
CAS issues:
  service=https://portal.example.org/login/cas

Spring validates:
  service=https://portal.example.org/login/cas
  ticket=ST-A       -> SUCCESS

Wrong validation:
  service=http://portal-internal:8080/login/cas
  ticket=ST-A       -> INVALID_SERVICE

Also wrong:
  service=https://portal.example.org/admin
  ticket=ST-A       -> INVALID_SERVICE
```

`service` không phải “một domain có vẻ đúng”, mà là **service identifier** mà CAS Server gắn với ST. Tùy CAS server/service URL matching policy, khác scheme, host, port, path hoặc query có thể gây mismatch. **Thiết kế strict/exact public URL là mặc định an toàn**. Đừng đổi CAS registry sang `.*` chỉ để làm hết INVALID_SERVICE.

Nếu có load balancer/ingress:
- Public service là `https://portal.example.org/login/cas`, không phải `http://app-pod:8080/login/cas`.
- `ServiceProperties.service` phải khớp callback URL do filter xử lý.
- Proxy cần ghi đè `X-Forwarded-Proto/Host/Port` từ client và gửi giá trị đáng tin cho backend nếu cấu hình sử dụng.
- Không để attacker kiểm soát Host/forwarded headers để tạo redirect service URL.
- App/context path, trailing slash, query và URL encoding phải nhất quán.

### 5.2. CAS `/serviceValidate` mẫu

Chỉ dùng **vé giả ở môi trường test**, vì ST nằm trong URL có thể bị log:

```bash
curl --silent --show-error --fail-with-body \
  --get 'https://sso.example.org/cas/serviceValidate' \
  --data-urlencode 'service=https://portal.example.org/login/cas' \
  --data-urlencode 'ticket=ST-DEMO-NOT-REAL'
```

`curl --get --data-urlencode` chuyển tham số thành URL-encoded query đúng chuẩn. Một ST giả sẽ trả `INVALID_TICKET`, đó là **kết quả đúng**. Đừng copy ST thật từ DevTools vào shell history/logs.

**Phản hồi thành công minh họa** (chỉ CAS đã xác minh mới đáng tin):

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

**Phản hồi thất bại minh họa:**

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    The ticket was issued for a different service
  </cas:authenticationFailure>
</cas:serviceResponse>
```

Ngoài `INVALID_SERVICE`, cần xử lý `INVALID_TICKET`, `INVALID_REQUEST` và `INTERNAL_ERROR` theo version/profile. HTTP status có thể vẫn là 200 cho một CAS XML authenticationFailure, nên **không chỉ kiểm HTTP 200 để cấp login**; đọc kết quả validator theo CAS protocol.

### 5.3. Khác biệt CAS 2 và CAS 3

| Endpoint | Dùng khi nào? | Chú ý |
| --- | --- | --- |
| `/validate` CAS 1 | Legacy two-line `yes/no` | Không có cấu trúc attributes/CAS 2 XML; không dùng cho proxy tickets. |
| `/serviceValidate` CAS 2 | ST → XML `authenticationSuccess`/Failure | Phù hợp CAS service ticket verification cơ bản. |
| `/p3/serviceValidate` CAS 3 | ST validation kèm CAS attributes | Dùng validator CAS3 compatible như `Cas30ServiceTicketValidator` nếu ứng dụng cần attributes. |
| `/proxyValidate`, `/p3/proxyValidate` | ST/PT theo proxy profile | **Không dùng** nếu bài lab chỉ cần CAS Login trực tiếp; nếu nhận PT cần explicit proxy trust policy. |

**Không nhầm với SAML2 ACS endpoint**. CAS protocol 2.0 response có prefix `cas:` nhưng không phải SAML Assertion của IdP.

## 6. Sơ đồ component Spring Security

```text
HttpSecurity / Spring Security FilterChain
  |
  +-- ExceptionTranslationFilter
  |     +-- CasAuthenticationEntryPoint
  |           builds CAS /login?service=<ServiceProperties.service>
  |
  +-- CasAuthenticationFilter
        +-- watches /login/cas
        +-- extracts opaque ticket parameter
        +-- delegates to AuthenticationManager / ProviderManager
              +-- CasAuthenticationProvider
                    +-- CAS TicketValidator (server-to-server HTTPS)
                    +-- CAS Assertion: principal, attributes
                    +-- UserDetailsService / account admission
                    +-- CasProxyDecider (if accepting proxy tickets)
        +-- success: SecurityContextRepository / HttpSession
        +-- failure: deny, no local session

Before Spring Security filters (for CAS SLO):
  Apereo SingleSignOutFilter
       +-- map validated ticket request to HttpSession
       +-- handle CAS logoutRequest and invalidate mapped session
  SingleSignOutHttpSessionListener
       +-- remove mappings when sessions expire or are destroyed
```

### 6.1. Thành phần và chức năng

| Class | Vai trò |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirect browser tới CAS login. |
| `ServiceProperties` | Định nghĩa callback service URL và `sendRenew`. |
| `CasAuthenticationFilter` | Nhận `ticket` ở callback `/login/cas`. |
| `CasAuthenticationProvider` | Cầu nối Spring Authentication đến CAS TicketValidator. |
| `Cas20ServiceTicketValidator` | Xác minh ST với CAS 2 `/serviceValidate`. |
| `Cas30ServiceTicketValidator` | Xác minh ST/attributes qua CAS 3 profile khi được cấu hình đúng. |
| `ProviderManager` | Dẫn authentication request đến CAS provider. |
| `UserDetailsService` | Tra local user status và authorities sau CAS assertion. |
| `SecurityContextRepository` | Lưu/đọc Spring Authentication trong local session. |
| `SingleSignOutFilter` | CAS client filter theo dõi ticket/login và nhận SLO, hủy đúng session mapping. |
| `SingleSignOutHttpSessionListener` | Dọn ánh xạ khi `HttpSession` được destroy/expired. |

**Các tên và phương thức phải được đối chiếu với Spring Security/CAS Client version cụ thể.** `SingleSignOutFilter` không phải Spring `LogoutFilter`; hai cơ chế xử lý hai nguồn logout khác nhau.

## 7. Phụ thuộc Maven/Gradle và vấn đề tương thích

Trong một dự án Spring Boot đã dùng BOM/parent quản lý phiên bản Spring Security:

```xml
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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
  <dependency>
    <groupId>org.apereo.cas.client</groupId>
    <artifactId>cas-client-core</artifactId>
    <!-- Choose a Jakarta-compatible release approved by your BOM. -->
  </dependency>
</dependencies>
```

**Đây là dependency fragment**, không phải POM hoàn chỉnh. CAS Client may be pulled transitively by `spring-security-cas`; chỉ khai báo trực tiếp khi cần kiểm soát version. **Không tự đặt artifact version rỗng** nếu BOM của bạn không quản lý `cas-client-core`; khi đó phải ghim một phiên bản đã được duyệt cho dependency trực tiếp. Java CAS Client 4.x thuộc dòng Jakarta-compatible; ví dụ repository Maven Central có `cas-client-core` 4.1.1 năm 2026, nhưng cần kiểm thực tế tương thích Spring Security, Boot, Java, JAXB/Jakarta.

Lệnh kiểm dependency:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.apereo.cas.client
mvn dependency:tree -Dincludes=jakarta.servlet
mvn dependency:tree -Dverbose
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-cas --configuration runtimeClasspath
./gradlew dependencyInsight --dependency cas-client-core --configuration runtimeClasspath
```

**Lỗi thường gặp:** app Boot 3/4 dùng `jakarta.servlet.*` nhưng CAS client legacy bị ràng buộc `javax.servlet.*`, hoặc trộn các module CAS Client 3.x/4.x không đồng bộ dẫn tới NoClassDefFoundError. Không tự thay một JAR trên classpath để chữa tới khi chạy được; chọn bộ tương thích theo BOM và security advisories.

## 8. Cấu hình Spring Security bằng Java — ví dụ có phạm vi

Mẫu sau nhằm làm rõ wiring **Spring Security 7.1 API** và CAS client theo dependency set tương thích. Đây là **mảnh ứng dụng Spring Boot Servlet** cần Java, Servlet, Spring Security và CAS dependencies, `UserDetailsService` thực; **không phải file Java SE độc lập**. Tên host là mẫu, không có CAS Server thực tại các URL này.

```java
package example.cas;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class CasLoginSecurityConfig {

    private static final String CAS_BASE =
        "https://sso.example.org/cas";

    private static final String PORTAL_SERVICE =
        "https://portal.example.org/login/cas";

    @Bean
    SecurityFilterChain casChain(HttpSecurity http,
                                 UserDetailsService localUsers)
            throws Exception {

        ServiceProperties service = new ServiceProperties();
        service.setService(PORTAL_SERVICE);
        service.setSendRenew(false);

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(service);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(CAS_BASE));
        provider.setUserDetailsService(localUsers);
        provider.setKey("portal-cas-authentication-provider-v1");

        CasAuthenticationEntryPoint entry =
            new CasAuthenticationEntryPoint();
        entry.setLoginUrl(CAS_BASE + "/login");
        entry.setServiceProperties(service);

        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setServiceProperties(service);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());

        http.authenticationProvider(provider)
            .exceptionHandling(ex ->
                ex.authenticationEntryPoint(entry))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/signed-out").permitAll()
                .requestMatchers("/login/cas").permitAll()
                .requestMatchers("/reports").hasAuthority("reports:read")
                .anyRequest().authenticated())
            .addFilterBefore(casFilter,
                UsernamePasswordAuthenticationFilter.class)
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out"));

        return http.build();
    }
}
```

**Chú ý cần hoàn thiện trước production:**
1. Cung cấp `UserDetailsService` từ directory local, map CAS principal vào đúng tenant/account, chặn `disabled/locked/expired` và kiểm authorities.
2. Chạy integration tests để xác nhận `SecurityContext` được lưu đúng `HttpSession`, cookie và session fixation protection. Một custom filter/provider có thể cần cấu hình session strategy/context repository nhất quán với SecurityFilterChain.
3. Đoạn trên chỉ có **CAS Login và ST validation**, **chưa** có SLO filter, listener, gateway source checks, logout-all flow hoặc health monitoring.
4. `CasAuthenticationFilter` được tạo **bên trong chain**, không tạo đồng thời một `@Bean` Servlet Filter auto-registration gây chạy hai lần.
5. `/login/cas` phải được CAS Server đăng ký đúng service URL và `permitAll` vẫn chạy các CAS auth filters. **Không** `web.ignoring()` callback.
6. `http.logout` vẫn bật CSRF mặc định; với browser session, **POST `/logout` có CSRF token**. Không tắt CSRF toàn app vì CAS SLO dùng POST.
7. `UserDetailsService` phải giữ role/status theo policy local. Không dùng một test account với `ROLE_ADMIN` mặc định trong production.
8. `setKey` là identifier của provider dùng nội bộ Spring, **không phải CAS shared-secret** hay password CAS.
9. `setSendRenew(true)` ép CAS xác thực trực tiếp lại theo CAS protocol cho một service nhạy cảm; phải test UX/MFA và CAS registry, không coi nó là logout.
10. Nếu dùng `Cas30ServiceTicketValidator` cho attributes, thay class theo version và kiểm mapping/attribute trust; không chấp nhận raw header roles.

### 8.1. Các bước cần thêm ngoài code

- `UserDetailsService`: lấy `username` từ **verified CAS Assertion**, không từ query/header.
- `SecurityFilterChain` cho admin endpoints riêng nếu cần và giữ CSRF/tenant scoping.
- Ingress HTTPS/forwarded headers: public service/callback chính xác, không trust client-supplied Host.
- Session strategy/cookie: HttpOnly, Secure, SameSite phù hợp với GET CAS callback; CAS SLO back-channel không dùng browser cookies.
- CAS Server service registry: allowed service URL/pattern kiểm chặt; enable/allow SLO delivery đến service.
- Logging: redaction `ticket` và `logoutRequest` tại gateway, app, APM.
- Security review: inbound CAS SLO source trust; session mapping sống/expire chính xác qua nodes.

## 9. `CasAuthenticationProvider`: local admission không đồng nghĩa CAS login

Giả sử CAS Server xác minh thành công và trả principal `alice`. Ứng dụng có thể có local records:

| CAS principal | Local account | Quyền local | `/reports` |
| --- | --- | --- | --- |
| `alice` | ACTIVE | `reports:read` | 200. |
| `bob` | ACTIVE | không có `reports:read` | 403. |
| `carol` | DISABLED | có role cũ | Reject admission/login. |
| `david` | Chưa được cấp phát | none | Deny hoặc đi qua provisioning workflow được duyệt. |
| `alice@partnerB` | Thuộc tenant khác | chỉ partnerB | Không được vào tenantA dù username tương tự. |

**Cách làm:** sau CAS validation, `CasAuthenticationProvider` tra `UserDetailsService` và/hoặc converter được kiểm soát để kiểm local account status, dùng mapping tin cậy. `CasAuthenticationProvider#setUserDetailsChecker` có thể giúp check status theo Spring Security version. Nếu cần attributes từ CAS3, phân biệt `CAS` verified attribute với `HTTP header` tự tạo và **không cấp `ROLE_ADMIN` từ attribute không có trust policy**.

### 9.1. Đối với username duplicate/multi-tenant

Đừng dùng mỗi chuỗi `alice` cho mọi external identity sources nếu một CAS Server có nhiều realms/tenants. Xác định stable subject cùng CAS realm/issuer policy, mapping local unique key, trạng thái bị khóa và quyền. Không tự tạo local account với quyền cao cho bất kỳ CAS principal lạ nào.

### 9.2. Logout và quyền không tự cập nhật tức thì

Một khi Authentication và role được lưu trong local session, quyền có thể sống đến khi phiên hết hạn. Nếu `bob` bị thu hồi permission, CAS ticket validation trước đó không tự khiến Spring kiểm lại mỗi request. Cần TTL/revocation/authority refresh theo rủi ro và lập kế hoạch cho các phiên hiện hữu.

## 10. Single Sign-Out: local logout, CAS logout và đồng bộ session

### 10.1. Ba trường hợp khác nhau

| Action | CAS TGT/TGC | Local Portal session | Other CAS clients |
| --- | --- | --- | --- |
| `POST /logout` local | **Không tự kết thúc** | Spring logout clears Authentication, invalidates local session theo config. | Không bị ảnh hưởng. |
| Browser gọi CAS `/logout` | CAS hủy TGT/TGC | **Không tự hủy** nếu client không hỗ trợ/không nhận SLO. | Tương tự; phụ thuộc SLO. |
| CAS `/logout` + SLO hoạt động | CAS TGT bị hủy | CAS phát logout notification, client mapping ticket→session và invalidate. | Các clients nhận notification cũng đóng phiên tương ứng. |

CAS Server là **SSO session manager**, **không phải session manager toàn bộ ứng dụng**. CAS có thể gửi SLO đến nhiều services, nhưng theo CAS protocol lỗi delivery **không cản CAS logout**, do đó kết thúc TGT không chứng minh mọi local sessions chắc chắn đã hủy.

### 10.2. SLO message đi đâu?

Theo CAS SLO back-channel:
- CAS Server POST tới **service URL đã ghi nhận khi cấp ST**; trong ví dụ thường là `/login/cas`.
- Form parameter thường tên **`logoutRequest`**, chứa XML theo CAS SLO format.
- XML dùng `samlp:LogoutRequest`, `samlp:SessionIndex` thường **mang service ticket ID**, không phải username, TGT hay JSESSIONID.
- CAS client tìm mapping `ST -> HttpSession`, invalidate đúng session.
- `SingleSignOutHttpSessionListener` dọn record ánh xạ khi session đã hết hạn hoặc bị invalidate.

Ví dụ XML **giả**, không dùng để xác thực thật:

```xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-example"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:00Z">
  <saml:NameID>@NOT_USED@</saml:NameID>
  <samlp:SessionIndex>ST-opaque-original</samlp:SessionIndex>
</samlp:LogoutRequest>
```

**Không giả định đây là chữ ký SAML 2.0 Web SSO hoàn chỉnh**: CAS Single Logout có định dạng dùng SAML namespace, nhưng **CAS Client SLO policy và transport trust là riêng**. Với back-channel POST không có signature đáng tin, cần **bảo vệ nguồn nhận callback** bằng mTLS/trusted gateway/network ACL, exact route và bảo vệ khỏi forged logout (DoS phiên người khác).

### 10.3. Diễn tiến SLO chính xác

```text
User has local CAS sessions:
  Service Ticket ST-1 -> Portal Session SID-1 -> alice
  Service Ticket ST-2 -> Another Session SID-2 -> alice

User asks CAS /logout:
  CAS destroys SSO TGT/TGC
  CAS sends SLO POST for ST-1 to Portal service URL
  Portal SingleSignOutFilter:
     recognize trusted logoutRequest
     look up ST-1 -> SID-1
     invalidate SID-1
     remove mapping ST-1
  CAS sends logout for ST-2 if recorded/appropriate:
     invalidate SID-2
```

**Không dùng `NameID=alice` để hủy mọi session của alice**. Người dùng có thể có hai browser, hai thiết bị, hoặc một session local còn chưa được CAS ghi nhận. Hủy theo exact service-ticket mapping vừa đúng contract vừa tránh blast radius.

### 10.4. SLO có thể là fire-and-forget

CAS SLO delivery là best effort theo protocol:
- Client offline, network timeout hoặc WAF block POST => local session có thể vẫn tồn tại.
- ST→Session mapping mất sau node restart => callback không tìm được session.
- CAS TGT hết hạn tự nhiên mà không có SLO ở một mode/server policy => app session sống riêng.
- Browser/front-channel SLO có thể bị chặn bởi cookie/privacy policy hoặc tab đã đóng.
- SLO POST gửi trễ/duplicate, session đã expired => xử lý idempotent, không gây 500 vô hạn.
- Người dùng local logout nhưng CAS SSO vẫn sống => redirect protected resource có thể silent relogin.

Giải pháp nhiều lớp: session TTL hợp lý, local revocation, access-control checks, durable SLO storage phù hợp và monitoring/incident response; **không coi SLO là cơ chế thu hồi duy nhất** cho quyền đặc biệt.

## 11. Apereo Java CAS Client SingleSignOutFilter và listener

Theo Spring Security CAS docs và Apereo Java CAS Client:
- **`org.apereo.cas.client.session.SingleSignOutFilter`** nhận ticket ở login request để map với session, đồng thời nhận CAS logoutRequest và vô hiệu hóa session.
- **`org.apereo.cas.client.session.SingleSignOutHttpSessionListener`** dọn mappings khi session đã bị hủy.
- **Filter xử lý SLO cần chạy trước CAS Authentication Filter** và thường trước Spring Security FilterChain trong mô hình Servlet filters; phải thấy request ST ban đầu và SLO callback.
- Apereo Java CAS Client có tham số `logoutParameterName` (mặc định `logoutRequest`) và `logoutCallbackPath` để giới hạn endpoint cần parse POST.
- Encoding filter UTF-8 cần xử lý đúng thứ tự, đặc biệt nếu form/POST body đã được đọc trước CAS SLO filter.

### 11.1. Cấu hình Servlet listener/filter mẫu cho Spring Boot Jakarta

Đây là một **mảnh Spring Boot Servlet** với Apereo Java CAS Client phù hợp Jakarta; **không phải chương trình Java SE độc lập**:

```java
package example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloServletConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilter() {
        FilterRegistrationBean<SingleSignOutFilter> reg =
            new FilterRegistrationBean<>();
        reg.setFilter(new SingleSignOutFilter());
        reg.addUrlPatterns("/*");
        reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        reg.addInitParameter("logoutCallbackPath", "/login/cas");
        return reg;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
```

**Cần kiểm chứng khi ghép với filter chain thực:**
1. Với Boot/security filter ordering, `SingleSignOutFilter` phải chạy **trước** Spring Security CAS login filter và cả request handler có thể đọc body POST.
2. Phải kiểm `logoutCallbackPath` đúng service URL/path CAS Server POST tới; dùng source code/Javadoc chính CAS client release khi triển khai.
3. Mapping giữa ticket và session được đăng ký ở lần **GET `/login/cas?ticket=...`**, và session vẫn tồn tại sau CAS authentication; thử session fixation ID change.
4. Listener được đăng ký **một lần**, không cấu hình đồng thời `web.xml` và Java bean duplicates.
5. Filter đó **không tự xác minh SLO caller chính là CAS Server**; dùng mTLS/ingress policy, network identity/source restrictions và security review riêng.
6. Nếu Boot 3/4 dùng Jakarta servlet, CAS Client cần build Jakarta-compatible; không trộn class `javax.servlet.Filter` cũ.
7. Mapping mặc định trong Java CAS Client thường **in-memory/static** cho servlet context; **không phù hợp mặc định cho multi-node**, cần shared session mapping hoặc routing/cluster strategy do client version hỗ trợ.
8. `SessionIndex` phải map **ST của session này**, không phải JSESSIONID hay username. Test cả logout một user đang có nhiều sessions.
9. CAS SLO POST đi trước Spring CSRF filter khi được nhận/giải quyết ở Servlet filter riêng; **không tắt CSRF toàn app**. Nếu SLO đi qua Spring chain, chỉ ngoại lệ CSRF hẹp phù hợp source trust.
10. Có thể kiểm event của CAS SLO interceptor/registrations bằng JUnit integration và CAS sandbox, không dựa vào giả lập `HTTP 200`.

### 11.2. Quyền mạng và nguồn SLO

CAS SLO XML theo triển khai không phải lúc nào cũng có signed XML. **Một attacker biết ST (ví dụ bị lộ qua access logs) và có thể POST `logoutRequest` giả có thể ép session đó kết thúc** nếu endpoint không phân biệt nguồn. Đây là **logout DoS/session disruption**, không nhất thiết chiếm tài khoản, nhưng vẫn là vấn đề bảo mật.

Bảo vệ:
- SLO callback chỉ nhận từ CAS Server/approved gateway, dùng mTLS/service identity khi có thể.
- Network ACL là lớp phụ; không tin `X-Forwarded-For` do Internet client tự gửi.
- Không cho inbound SLO request từ host tùy ý đi thẳng pod, bypass ingress.
- Hạn chế `logoutCallbackPath`, method, body size, XML parser security, rate limits.
- Không log raw `logoutRequest`, ST, `JSESSIONID`; chỉ event refs.
- Trong cluster, mapping ST→session phải đáng tin và xóa idempotent.

**Không bật `permitAll` trên mọi endpoint chỉ để cho CAS SLO gọi được.** Callback có thể chưa có browser Authentication, nhưng phải đi đúng protocol filter và source trust.

## 12. Thiết kế hành động “Đăng xuất tại đây” và “Đăng xuất ở mọi ứng dụng”

Một UI nên tách hai lựa chọn rõ ràng:

- **Local logout**: POST `/logout` với CSRF token theo Spring Security, xóa local SecurityContext và HttpSession, hiển thị `/signed-out`.
- **Global logout**: POST một endpoint được bảo vệ CSRF để hủy phiên local, rồi **redirect browser đến URL CAS logout cố định từ cấu hình server**. CAS hủy TGT, gửi SLO đến các services có hỗ trợ, rồi có thể redirect tới **service/redirect URL đã được CAS đăng ký** theo policy.

**Không dùng GET link có side effect local logout mà không đánh giá CSRF**; không nhận `?returnUrl=https://attacker.example` rồi nhét vào CAS `service` hoặc local redirect. Nếu CAS Server cho redirect sau logout, URL phải thuộc service registry/allowlist chính xác; không lấy từ attacker input.

### 12.1. Mẫu pseudocode cho global logout

```text
POST /logout/all
  require current browser CSRF token
  clear local SecurityContext, invalidate local HttpSession
  expire local auth-related cookies via approved policy
  redirect browser to fixed:
    https://sso.example.org/cas/logout
  CAS invalidates its TGT/TGC
  CAS attempts SLO notifications to other CAS clients
  show safe public signed-out page according to CAS server config
```

Một ứng dụng có thể xử lý local logout qua `SecurityContextLogoutHandler`, logout success handler riêng và CSRF configuration. Mảnh trên là **pseudocode workflow**, không phải code drop-in cho mọi Spring version.

### 12.2. Tại sao local logout có thể lập tức login lại?

```text
Portal POST /logout
  -> JSESSIONID invalidated
Browser GET /reports
  -> Portal redirects CAS /login
  -> CAS TGC still active
  -> CAS issues NEW ST
  -> Portal verifies it and logs in again
```

Đây là **CAS SSO hoạt động như thiết kế**, không mặc định là bug. Nếu user muốn rời toàn bộ hệ thống, phải kết thúc CAS TGT/TGC; nếu cần thoát riêng ứng dụng, có thể cần UX tránh auto-redirect ngay vào protected URL.

## 13. Session, ticket mapping và concurrency

### 13.1. Session fixation protection

Spring Security có session fixation strategy: sau CAS login thành công, container có thể `changeSessionId()` hoặc migrate session. Đừng dùng **chuỗi JSESSIONID đã đọc trước login** làm giá trị ST→session bất biến. CAS client filter thường theo dõi `HttpSession` và listener để invalidate; **phải test thực tế qua session rotation**, không giả định mapping sẽ sống trên mọi implementation.

### 13.2. Cùng user, hai thiết bị

```text
Laptop browser:
   CAS ST-A -> Portal session SID-A
Phone browser:
   CAS ST-B -> Portal session SID-B

CAS SLO for ST-A:
  invalidate SID-A
  leave SID-B alone until the matching SLO event arrives
```

Không xóa bằng `username -> all sessions` khi thông báo định danh một ticket. Nếu policy muốn revoke **tất cả** sessions của user (offboarding, compromise), đó là **một workflow quản trị khác** cần explicit tenant/user identity và audit.

### 13.3. Multi-node failure

```text
Login request:
  LB -> Node A, ST-1 mapped to HttpSession SID-1 in A's memory

SLO callback:
  CAS -> LB -> Node B
  Node B has no mapping ST-1 -> SID-1
  returns 200/no-op or no match
  SID-1 on Node A remains active
```

**Sticky sessions không tự khắc phục CAS SLO back-channel**, vì SLO callback **không mang browser JSESSIONID** để load balancer route theo sticky cookie. Dùng một trong các phương án được thiết kế/kiểm thử:
- Shared mapping ST→session ID cộng shared Spring Session store, và revocation APIs có atomic semantics.
- Dedicated SLO coordinator service, bus/event tới node đang giữ session với durable delivery, TTL, replay/idempotency.
- Client/storage adapter hỗ trợ distributed mapping, nếu đúng version có capability này.
- Hạn chế architecture một node khi lab đơn giản, nhưng **không quảng cáo SLO multi-node** nếu chỉ có static map local.

Thử rolling restart, node failover, Redis outage, callback retry/delay và 2 browsers. **Không trả QA PASS chỉ vì một node nhận SLO 200**.

### 13.4. Idempotency và pending logout

- LogoutRequest lặp lại cho ST đã invalidate → no match/idempotent, không phá session mới.
- SLO tới trễ sau khi user đã login lại bằng ST mới → không invalidate **session mới** chỉ vì cùng username.
- CAS Server timeout -> app phải có session TTL hoặc revocation fallback; không “bỏ qua” cũ vô hạn.
- HTTP response 200 từ callback không chứng minh session thật bị xóa; phải verify access với **cookie cũ** đã bị reject.
- `HttpSessionListener` cleanup giảm stale ticket mapping; khi store hoặc listener lỗi cần telemetry và repair.
- Local session expiry độc lập với CAS TGT expiry; refresh permissions theo policy.

## 14. Cách kiểm thử trực tiếp với CAS sandbox

### 14.1. Chuẩn bị CAS Server registry

1. Cho phép service `https://portal.example.org/login/cas` trong CAS registry.
2. Bật CAS protocol endpoint `/serviceValidate` và TLS certificate đúng hostname.
3. Dùng test identity provider/user store, không dùng credentials production.
4. Cấu hình CAS logout/SLO delivery đến đúng service URL mà client filter xử lý.
5. Quy định login success role/tenant mapping cho `alice` và `bob`.
6. Nếu CAS Server hỗ trợ attributes, chỉ sử dụng qua CAS3 validator tương thích và trust policy.
7. Giữ logs ticket values **redacted** từ CAS, proxy và app.

### 14.2. Happy-path CAS login

- Browser GET `/reports` khi unauthenticated.
- Spring redirect tới CAS `/login?service=<encoded exact callback>`.
- CAS xác thực, redirect browser về callback có ST mới.
- Spring CAS filter gọi `/serviceValidate` đúng CAS host và `service`.
- CAS trả XML success; local `UserDetailsService` trả user enabled + role.
- Spring tạo SecurityContext/session, browser tới `/reports` và nhận 200.
- Sau đó browser reload `/reports` phải sử dụng local session, **không validate ST thêm lần nữa**.

### 14.3. ST one-time và wrong service

- Dùng ST đã validate gửi callback lần hai: CAS `INVALID_TICKET`, không tạo phiên mới.
- Lấy ST cấp cho `portal` nhưng validation khai `service` của app khác: CAS `INVALID_SERVICE`.
- **Ngay sau wrong-service validation**, thử lại ST với service đúng: vẫn `INVALID_TICKET` nếu CAS đã tiêu thụ ticket.
- Gửi ticket fake/expired/malformed: reject, không fallback chấp nhận username.
- Gọi CAS `/serviceValidate` qua network lỗi hoặc cert invalid: fail closed, không tạo Authentication.
- Không log `ticket` ở browser history/Referrer, ingress access logs hoặc APM.

### 14.4. CAS logout/SLO E2E

1. Đăng nhập CAS tại Portal, mở DevTools và ghi safe sessionRef.
2. Cũng login một CAS client thứ hai nếu muốn thấy global logout effect.
3. Kích hoạt global logout bằng browser vào CAS `/logout` (qua UX có chủ đích).
4. CAS hủy TGT và gửi SLO POST đến service URLs đã đăng ký; quan sát `logoutRequest` **presence flag**, không log raw XML.
5. CAS client `SingleSignOutFilter` tìm mapping ST→HttpSession và invalidate.
6. Dùng **cookie local cũ** gọi `/reports` lần nữa. Phải mất Authentication, redirect login/new session.
7. Kiểm client thứ hai tương tự; nếu không bị logout, đối chiếu delivery/mapping.
8. Lặp lại với logout local `/logout`: CAS TGT vẫn có thể sống và yêu cầu lại `/reports` có thể silent relogin.
9. Lặp lại SLO giả từ Internet/không mTLS: phải bị từ chối trước khi hủy local session.
10. Lặp lại SLO duplicate, session expired, node khác và CAS outage.

**Không đo SLO bằng cách nhìn trang “đã đăng xuất”**: trang đó có thể hiện dù HttpSession không bị invalidate. Kiểm authenticated API bằng **cookie cũ** và audit event.

## 15. Java 17 runnable: mô phỏng ST one-time, exact service và SLO mapping

Đây là một chương trình **Java SE 17 độc lập**, không cần Spring hay CAS Server thật. Nó mô phỏng CAS Server **phát ticket**, xác minh ST một lần cho đúng service, ứng dụng local admission và bảng ánh xạ ST→session dùng cho CAS SLO.

**Giới hạn bắt buộc:** `trustedCasSource` trong ví dụ là một boolean **tưởng tượng kết quả mTLS/ingress đã xác minh**. Không bao giờ lấy boolean đó từ HTTP query/header/JSON tự khai trong production. Chương trình không parse XML, kiểm TLS, quản lý TGT/TGC, thực thi CAS protocol hay distributed sessions; chỉ giúp hiểu logic phải kiểm thử khi ghép Spring Security/CAS.

Tạo file **`CasLoginAndSloDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

public final class CasLoginAndSloDemo {

    private static final String SERVICE =
        "https://portal.example.org/login/cas";

    record ServiceTicket(String id, String service, String principal) {}

    record Verified(boolean success, String code, String principal) {}

    static final class FakeCasServer {
        private final Map<String, ServiceTicket> tickets =
            new HashMap<>();

        void issue(String id, String service, String principal) {
            tickets.put(id, new ServiceTicket(id, service, principal));
        }

        Verified validate(String ticketId, String presentedService) {
            // Consume even on failed service match: CAS one-time semantics.
            ServiceTicket issued = tickets.remove(ticketId);
            if (issued == null) {
                return new Verified(false, "INVALID_TICKET", null);
            }
            if (!issued.service().equals(presentedService)) {
                return new Verified(false, "INVALID_SERVICE", null);
            }
            return new Verified(true, "SUCCESS", issued.principal());
        }
    }

    static final class PortalSessions {
        private final Map<String, String> sessions = new HashMap<>();
        private final Map<String, String> ticketToSession =
            new HashMap<>();

        String admit(String serviceTicket, Verified verified,
                     String sessionId, boolean localEnabled) {
            if (!verified.success()) {
                return "DENY_" + verified.code();
            }
            if (!localEnabled) {
                return "DENY_LOCAL_ACCOUNT";
            }
            sessions.put(sessionId, verified.principal());
            ticketToSession.put(serviceTicket, sessionId);
            return "AUTHENTICATED";
        }

        String receiveSlo(boolean trustedCasSource, String serviceTicket) {
            if (!trustedCasSource) {
                return "DENY_SLO_SOURCE";
            }
            if (serviceTicket == null || serviceTicket.isBlank()) {
                return "DENY_SLO_FIELDS";
            }
            String sessionId = ticketToSession.remove(serviceTicket);
            if (sessionId == null) {
                return "NO_MATCH";
            }
            sessions.remove(sessionId);
            return "INVALIDATED";
        }

        String status(String sessionId) {
            return sessions.containsKey(sessionId) ? "ACTIVE" : "ABSENT";
        }
    }

    public static void main(String[] args) {
        FakeCasServer cas = new FakeCasServer();
        PortalSessions portal = new PortalSessions();

        cas.issue("ST-A1", SERVICE, "alice");
        cas.issue("ST-A2", SERVICE, "alice");

        System.out.println("LOGIN_A1=" + portal.admit(
            "ST-A1", cas.validate("ST-A1", SERVICE), "SID-A1", true));
        System.out.println("LOGIN_A2=" + portal.admit(
            "ST-A2", cas.validate("ST-A2", SERVICE), "SID-A2", true));
        System.out.println("SESSION1_BEFORE=" + portal.status("SID-A1"));

        System.out.println("ST_REPLAY=" +
            cas.validate("ST-A1", SERVICE).code());

        cas.issue("ST-WRONG", SERVICE, "bob");
        System.out.println("WRONG_SERVICE=" +
            cas.validate("ST-WRONG",
                "https://portal.example.org/admin").code());
        System.out.println("WRONG_SERVICE_REPLAY=" +
            cas.validate("ST-WRONG", SERVICE).code());

        System.out.println("FORGED_SLO=" +
            portal.receiveSlo(false, "ST-A1"));
        System.out.println("SESSION1_AFTER_FORGERY=" +
            portal.status("SID-A1"));

        System.out.println("REAL_SLO_A1=" +
            portal.receiveSlo(true, "ST-A1"));
        System.out.println("SESSION1_AFTER_SLO=" +
            portal.status("SID-A1"));
        System.out.println("SESSION2_AFTER_SLO_A1=" +
            portal.status("SID-A2"));
        System.out.println("DUPLICATE_SLO_A1=" +
            portal.receiveSlo(true, "ST-A1"));

        cas.issue("ST-BOB", SERVICE, "bob");
        System.out.println("DISABLED_BOB=" + portal.admit(
            "ST-BOB", cas.validate("ST-BOB", SERVICE),
            "SID-BOB", false));
        System.out.println("BOB_SESSION=" + portal.status("SID-BOB"));

        System.out.println("EMPTY_SLO=" + portal.receiveSlo(true, ""));
        System.out.println("REAL_SLO_A2=" +
            portal.receiveSlo(true, "ST-A2"));
        System.out.println("SESSION2_AFTER_SLO=" +
            portal.status("SID-A2"));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac CasLoginAndSloDemo.java
java CasLoginAndSloDemo
```

**Stdout chính xác**:

```text
LOGIN_A1=AUTHENTICATED
LOGIN_A2=AUTHENTICATED
SESSION1_BEFORE=ACTIVE
ST_REPLAY=INVALID_TICKET
WRONG_SERVICE=INVALID_SERVICE
WRONG_SERVICE_REPLAY=INVALID_TICKET
FORGED_SLO=DENY_SLO_SOURCE
SESSION1_AFTER_FORGERY=ACTIVE
REAL_SLO_A1=INVALIDATED
SESSION1_AFTER_SLO=ABSENT
SESSION2_AFTER_SLO_A1=ACTIVE
DUPLICATE_SLO_A1=NO_MATCH
DISABLED_BOB=DENY_LOCAL_ACCOUNT
BOB_SESSION=ABSENT
EMPTY_SLO=DENY_SLO_FIELDS
REAL_SLO_A2=INVALIDATED
SESSION2_AFTER_SLO=ABSENT
```

### 15.1. Vì sao kết quả này hữu ích?

- `LOGIN_A1/A2`: cùng một principal có thể có **hai local sessions**, không nên map chỉ theo username.
- `ST_REPLAY`: ticket đã validate bị CAS tiêu thụ nên không thể dùng lại.
- `WRONG_SERVICE`: ST chỉ dành một service; sai service bị reject.
- `WRONG_SERVICE_REPLAY`: một lần validation thất bại cũng có thể tiêu thụ ST, nên sửa service URL rồi **lấy ST mới**, không retry ST cũ.
- `FORGED_SLO`: nhận SLO từ peer không đáng tin phải bị block trước khi chạm mapping.
- `REAL_SLO_A1`: ST-A1 chỉ hủy SID-A1, **SID-A2 vẫn active** cho đến khi nhận event ST-A2.
- `DUPLICATE_SLO`: cùng sự kiện SLO gửi lại phải idempotent.
- `DISABLED_BOB`: CAS credential valid nhưng local user status không cho vào.
- `EMPTY_SLO`: thiếu SessionIndex/ticket cần reject, không đoán username.
- `REAL_SLO_A2`: hoàn tất vô hiệu phiên thứ hai khi event phù hợp đến.

**Không đưa class demo vào Spring AuthenticationFilter production.** `HashMap` chỉ có tác dụng trong một JVM, không an toàn cho cluster; `trustedCasSource` phải là kết quả một lớp xác minh thật, và `Verified` không thể do caller tự điền. Trong production CAS ticket validator cần TLS, CAS XML parsing và đầy đủ account admission; SLO listener/filter cùng shared session store cần QA E2E.

## 16. Ma trận kiểm thử CAS Login và Service Ticket

| ID | Case | Kỳ vọng |
| --- | --- | --- |
| L01 | User chưa authenticated mở `/reports`. | Spring redirect CAS Login với exact service. |
| L02 | User có CAS TGC hợp lệ, không có local JSESSIONID. | CAS có thể cấp ST mới/silent SSO; app vẫn validate ST. |
| L03 | CAS trả ST đúng service, valid và unused. | `CasAuthenticationProvider` tạo Authentication sau local admission. |
| L04 | ST gửi lần thứ hai sau validation. | `INVALID_TICKET`; không có phiên mới. |
| L05 | ST đúng format nhưng giả. | CAS reject, không “decode” principal từ ST. |
| L06 | ST đã hết hạn. | CAS reject, app fail closed. |
| L07 | ST cho service A validate với service B. | `INVALID_SERVICE`; ticket bị consume. |
| L08 | Sau invalid-service attempt, retry đúng service với ST cũ. | Không thành công; dùng ST mới. |
| L09 | `service` dùng HTTP internal URL thay HTTPS public. | Reject; sửa ingress/serviceProperties. |
| L10 | CAS back-channel cert hết hạn/hostname sai. | Validation fail closed; không trust-all TLS. |
| L11 | CAS Server outage hoặc timeout. | Không tạo Authentication; hiển thị lỗi an toàn. |
| L12 | CAS trả XML `authenticationFailure` cùng HTTP 200. | Không cho login. |
| L13 | CAS assertion hợp lệ nhưng local account disabled. | Deny account admission. |
| L14 | CAS assertion hợp lệ nhưng role `reports:read` absent. | 403 resource authorization. |
| L15 | CAS username từ HTTP header tự khai. | Bị bỏ qua, không tạo principal. |
| L16 | CAS Server mới nhưng không thuộc approved endpoint. | Không tự trust issuer/URL. |
| L17 | CAS `renew=true` dành sensitive service. | Yêu cầu primary credentials theo CAS policy. |
| L18 | Multi-tenant username collision. | Stable identity mapping không gán sai local tenant. |
| L19 | Ticket lọt vào Nginx access log. | Security QA FAIL, redact/incident handling. |
| L20 | Successful validation nhưng local session không lưu SecurityContext. | Next request không authenticated; sửa repository/filter session wiring. |
| L21 | User logout local rồi `/reports` lại khi CAS TGC vẫn sống. | Có thể silent relogin — UX phù hợp. |
| L22 | Một CAS client dùng `Cas20ServiceTicketValidator` nhưng được gửi Proxy Ticket. | Reject vì không phải ST; proxy profile cần khác. |
| L23 | Spring filter callback URL lệch `/login/cas` đã đăng ký. | Detect login redirect loop/invalid service. |
| L24 | App vừa có servlet CAS auth filters vừa Spring CAS filter. | Detect double validation; ST một lần có thể bị consume sai. |

## 17. Ma trận kiểm thử Single Sign-Out

| ID | Case | Kỳ vọng |
| --- | --- | --- |
| S01 | CAS `/logout` hủy TGT, gửi SLO cho ST-1. | Portal invalidates session mapped ST-1. |
| S02 | POST logoutRequest đến từ nguồn chưa được tin. | Block trước session invalidation. |
| S03 | SLO `SessionIndex=ST-1`, user có SID-1 và SID-2. | Chỉ SID-1 bị hủy, không xóa theo username. |
| S04 | CAS SLO lặp lại cho ST-1. | Idempotent/no match; không làm hỏng session mới. |
| S05 | SLO cho ST-unknown. | No match an toàn, telemetry. |
| S06 | SLO thiếu SessionIndex hoặc XML malformed. | Reject/handled failure; không hủy ngẫu nhiên. |
| S07 | CAS gửi callback qua HTTP khi chỉ HTTPS được approved. | Block/redirect policy, sửa CAS service config. |
| S08 | Callback đi tới route khác `/login/cas`. | Detect missing SLO delivery, fix routing. |
| S09 | Filter SLO sau Spring auth filter, body đã bị đọc. | Test fail, sửa filter ordering. |
| S10 | Local session đã timeout trước CAS SLO. | No match/idempotent, không 500 vô hạn. |
| S11 | Listener không cleanup mapping sau session destroy. | Detect stale mapping/memory leak. |
| S12 | SLO vào node B trong khi ticket mapping ở node A. | Không được QA PASS nếu SID-A vẫn active. |
| S13 | Node A restart, mapping local mất. | Fail-safe report/alternative distributed strategy. |
| S14 | Shared store fail khi xử lý SLO. | Alert/retry/revocation, không silent success giả. |
| S15 | Browser/front-channel SLO bị third-party cookie block. | Không coi front-channel là bảo đảm tuyệt đối. |
| S16 | CAS Server offline lúc global logout. | Local session đã được hủy; CAS SSO có thể còn, báo rõ. |
| S17 | CAS `/logout` success nhưng client B callback timeout. | TGT kết thúc, B local session còn; đúng best-effort semantics. |
| S18 | Local `/logout` khi CAS TGC còn. | CAS SSO vẫn tồn tại, có thể tự đăng nhập lại. |
| S19 | CAS logout dùng redirect service URL do attacker khai. | Reject open redirect/allowlist. |
| S20 | CAS SLO POST bị Spring CSRF chặn trước filter. | Fix narrow routing/order; không disable CSRF toàn app. |
| S21 | Cas SLO XML nhầm với Spring SAML2 SingleLogoutFilter. | Không dùng sai protocol handler. |
| S22 | CAS SLO callback thử xóa mọi sessions của username. | Reject behavior; map exact ticket→session. |
| S23 | ST→HttpSession mapping bị sai sau session fixation rotation. | Detect, dùng proper listener/session mapping strategy. |
| S24 | User logout all trong 2 tabs/2 browsers trên nhiều nodes. | Mỗi session được hủy theo its recorded CAS ticket, test old cookies. |
| S25 | Authorization status disabled while CAS SSO still active. | Local checks/revocation deny access ngay theo policy. |
| S26 | SLO request body oversized / malicious XML entity. | XML parser/body limits, deny safely. |
| S27 | Một filter đăng ký hai lần (web.xml + Spring bean). | Detect duplicate SLO/session invalidation. |
| S28 | SLO 200 trả về nhưng session vẫn authenticated. | Test FAIL: callback acceptance không bằng session invalidation. |

## 18. Observability và debugging không lộ bí mật

### 18.1. Log theo sự kiện, không theo raw ticket

```text
event=CAS_LOGIN_REDIRECT
trace_ref=login-43
service_ref=portal-cas-login
registration_ref=corporate-cas
result=REDIRECT_TO_CAS

event=CAS_ST_VALIDATION
trace_ref=login-43
ticket_ref=hmac(ST-opaque)
service_ref=portal-cas-login
cas_response=SUCCESS
local_account_state=ACTIVE
authn_result=SUCCESS

event=CAS_SLO_RECEIVED
trace_ref=slo-91
cas_peer_trusted=true
service_ticket_ref=hmac(ST-opaque)
session_mapping=FOUND
session_invalidation=SUCCESS
```

Đây là **schema gợi ý**, không phải log mặc định. Chỉ dùng keyed HMAC references khi thật sự cần liên kết events; tránh raw ticket, session cookie, CAS TGC, SLO XML, PII và hashed values dễ đoán.

### 18.2. Metrics cần theo dõi

```text
cas_login_redirect_total{service}
cas_ticket_validation_total{service,result}
cas_invalid_service_total{service}
cas_ticket_replay_rejected_total{service}
cas_backchannel_tls_failure_total{service}
cas_local_admission_denied_total{reason}
cas_slo_received_total{service,source_trust}
cas_slo_session_mapping_total{service,result}
cas_slo_invalidation_total{service,result}
cas_slo_callback_latency_seconds{service}
cas_session_revoke_lag_seconds{service}
```

**Không dùng raw ticket/session/user identifiers làm metric labels**. Alert nếu wrong-service tăng sau ingress change, ST validation fail tăng sau CAS cert rotation, SLO callback đến nhưng session không invalidated, hoặc SLO peer không trusted tăng.

### 18.3. Log category theo Spring version

Tùy version, dùng có kiểm soát:
- `org.springframework.security.cas` cho CAS auth/provider behavior.
- `org.apereo.cas.client` cho CAS client validation/SLO.
- `org.springframework.security.web` cho filter chain, session persistence.
- CAS Server logs/service registry cho issuance/validation/SLO delivery.
- Ingress access logs **đã redact** query `ticket` và form `logoutRequest`.
- Spring Session Redis/JDBC metrics cho session TTL/revocation.

**Không bật DEBUG/TRACE trên production toàn web stack** nếu nó sẽ in raw URL headers/params. Một log `authenticationFailure` của CAS và Spring `AuthenticationException` có thể có message chứa input nhạy cảm; sanitize trước khi lưu.

## 19. Cây quyết định xử lý lỗi

```text
User cannot access protected Portal page
 |
 +-- Browser redirected to CAS /login?   NO
 |      -> Spring authorization/entry point/FilterChain
 |
 YES
 |
 +-- CAS redirected to correct /login/cas with ST?  NO
 |      -> CAS service registry, login, MFA, allowed service URL
 |
 YES
 |
 +-- CasAuthenticationFilter executed?  NO
 |      -> callback matcher, context path, filter order
 |
 YES
 |
 +-- HTTPS /serviceValidate succeeded?  NO
 |      -> CAS DNS/TLS/truststore/network timeout
 |
 YES
 |
 +-- CAS XML authenticationSuccess?  NO
 |      +-- INVALID_TICKET -> expired/reused/fake
 |      +-- INVALID_SERVICE -> service exact URL mismatch
 |      +-- other errors -> CAS config/logs
 |
 YES
 |
 +-- Local account ACTIVE and authorized?  NO
 |      -> UserDetailsService, account/tenant/roles
 |
 YES
 |
 +-- SecurityContext persists across next request?  NO
 |      -> Session/repository/cookie/CSRF/login filter
 |
 YES: CAS Login works
 |
 User signs out at CAS
 |
 +-- CAS SLO notification sent?  NO
 |      -> service SLO configuration, CAS TGT flow
 |
 YES
 |
 +-- Reaches trusted SLO filter before Spring?  NO
 |      -> ingress/mTLS/filter order/POST body/CSRF
 |
 YES
 |
 +-- ST SessionIndex maps local session?  NO
 |      -> ticket->session record, listener, cluster routing/store
 |
 YES
 |
 +-- Old session rejected afterward?  NO
        -> invalidation/storage propagation/security-context cache
```

**Một nguyên nhân, một lớp sửa:** login redirect loop không tự động do ticket; logout không đồng bộ không nhất thiết do CAS Server; XML success không chứng minh user có quyền business.

## 20. Lỗi thường gặp khi tích hợp

| Lỗi | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Redirect CAS liên tục. | `service` URL/callback matcher không nhất quán; SecurityContext không persist. | So browser URL, `ServiceProperties`, filter, cookie/session. |
| `INVALID_SERVICE`. | CAS issued ST cho public HTTPS, app validate nội bộ HTTP hoặc khác path/query. | Sửa exact public service identity/ingress, lấy ST mới. |
| `INVALID_TICKET`. | ST hết hạn, đã validate, bị double filter hoặc fake. | Điều tra one-time lifecycle, không retry ST cũ. |
| CAS trả XML failure nhưng app tạo session. | Custom integration chỉ kiểm HTTP 200. | Dùng CAS TicketValidator và failure branch đúng. |
| `CasAuthenticationFilter` không chạy. | Filter order/URL không match. | Map exact `/login/cas`, kiểm SecurityFilterChain. |
| SAML response filter xử lý CAS ST. | Trộn CAS với SAML2 SP. | Dùng CAS integration riêng. |
| GET login thành công nhưng trang khác 401. | SecurityContextRepository/session persistence/cookie lỗi. | Kiểm HttpSession, cookie Secure/Path, context save. |
| CAS login OK nhưng `ROLE_ADMIN` sai. | UserDetails/attribute mapping quá rộng. | Least privilege, local account status, tenant mapping. |
| Local logout xong login lại ngay. | CAS TGT/TGC còn. | UX local vs global logout rõ. |
| CAS global logout nhưng Portal vẫn vào được. | SLO filter chưa có/mapping mất/callback thất lạc. | Debug delivery, source trust, ST mapping, old cookie. |
| SLO POST bị 302 đến CAS login. | Request bị Spring auth entry point intercept. | SLO filter trước auth chain; dedicated callback route. |
| SLO POST bị 403. | CSRF/WAF/ingress block hoặc source trust deny. | Tách trust failure thật khỏi matcher lỗi; narrow policy. |
| SLO POST được 200 nhưng session còn. | Không tìm được mapping hoặc invalidate sai session. | Test ST→HttpSession, cluster, session store. |
| Mất SLO sau deploy nhiều nodes. | Static/in-memory map ở node A, callback vào B. | Shared mapping/revocation coordinator. |
| SLO hủy nhầm phiên mới. | Map theo username thay vì ST, stale session mapping. | Exact ticket→session, idempotency. |
| CAS callback có SAML namespace nên dùng `Saml2LogoutRequestFilter`. | Nhầm CAS SLO với SAML 2.0 SLO. | Đọc CAS client protocol và dùng đúng handler. |
| CAS TLS trust lỗi. | CA truststore/hostname/TLS versions sai. | Sửa CA/hostname/mTLS, không trust-all. |
| Client 4.x/Jakarta khởi động lỗi. | Trộn Java CAS Client legacy `javax.servlet` hoặc dependencies. | Pin bộ tương thích, kiểm dependency tree. |
| CAS `/p3/serviceValidate` attributes không xuất hiện. | Đang dùng CAS2 validator hoặc release policy không cấp attributes. | Dùng CAS3-compatible validator và CAS attribute release. |
| SLO XML parser/encoding fail. | Body bị đọc trước, wrong content type, filter order/charset. | Sửa order, UTF-8, request limits. |
| SLO client bị forged request DoS. | SLO endpoint public thiếu peer trust, ticket lộ. | mTLS/gateway allowlist, redaction, rate-limit. |

## 21. Những anti-pattern và vì sao sai

1. **“Có query `ticket=ST-...` là đã login.”** Chưa validate ở CAS Server.
2. **“ST là JWT nên có thể decode để lấy user.”** CAS ST là opaque credential.
3. **“ST sai service thì validate lại cùng ticket với URL đúng.”** ST một lần, failed validation cũng consume.
4. **“Spring local session bằng CAS TGT.”** Hai hệ thống session độc lập.
5. **“CAS logout chắc chắn xóa mọi HttpSession.”** SLO là best effort.
6. **“SingleSignOutFilter tự xác thực caller CAS qua HTTPS.”** HTTPS server cert không tự xác thực inbound caller.
7. **“SLO SessionIndex là JSESSIONID.”** Với CAS SLO, thường là ST ID để map phiên.
8. **“SLO có `samlp:LogoutRequest` nên là Spring SAML2 logout.”** Khác protocol/context.
9. **“Hủy tất cả sessions theo username khi nhận một logoutRequest.”** Sai scope, gây DoS.
10. **“Chỉ một node test SLO là đủ.”** Callback back-channel không mang sticky browser cookie.
11. **“HTTP 200 SLO chứng minh session đã bị revoke.”** Cần test old cookie.
12. **“Nếu CAS TGC còn thì local logout thất bại.”** Silent relogin có thể là hành vi SSO hợp lệ.
13. **“Cho mọi returnUrl từ query vào CAS /logout.”** Open redirect, phải allowlist.
14. **“Bỏ CSRF toàn app để CAS logout POST đi qua.”** Mở CSRF nghiệp vụ; sửa filter order/matcher.
15. **“Lấy authorities từ username/header không kiểm.”** Phải là local policy + verified assertion.
16. **“Dùng trust-all TLS để xử lý validation timeout.”** Bỏ trust server; không an toàn.
17. **“Map ST→Session trong static HashMap là cluster-ready.”** Không phân tán/đồng bộ.
18. **“Giữ mã legacy `javax.servlet` trong Boot Jakarta.”** Sai API compatibility.
19. **“Ticket raw trong URL log là bình thường vì một lần.”** Bearer secret vẫn có thể bị dùng trước validation.
20. **“SLO thay hẳn local session timeout và revocation.”** Callback có thể thất lạc.
21. **“CSRF callback SLO hợp lệ nếu IP từ X-Forwarded-For khai là CAS.”** Header attacker có thể spoof.
22. **“Dùng `Cas20ServiceTicketValidator` để nhận proxy ticket không cần policy.”** Proxy cần validator/trusted chain riêng.
23. **“Đăng xuất xong redirect tới `/reports` là đủ UX.”** Có thể auto-login lại qua CAS TGC.
24. **“Cứ thêm CAS client validation filter nữa cho chắc.”** Dễ double-validate ST một lần.
25. **“Update CAS Server/Java Client mà không chạy regression.”** Khác protocol/config có thể phá login/SLO.

## 22. Checklist nghiệm thu production

1. Có phiên bản Spring Security, CAS client, Servlet/Jakarta và Java được hỗ trợ/khóa trong SBOM.
2. CAS Server service registry chỉ chấp nhận exact approved HTTPS service URL.
3. Spring `CasAuthenticationEntryPoint` dùng CAS login host đã được tin.
4. `ServiceProperties.service` khớp `CasAuthenticationFilter` callback thật.
5. ST được validate bằng `Cas20ServiceTicketValidator`/validator phù hợp qua trusted HTTPS.
6. ST expired/fake/replayed/wrong service bị reject, kể cả XML failure HTTP 200.
7. Không dùng raw ST để tạo Principal/Authentication hoặc lấy role từ HTTP header.
8. Local account status/tenant/roles được kiểm độc lập với CAS login success.
9. SecurityContext persist trong HttpSession đúng lifecycle, cookie Secure/HttpOnly và policy SameSite.
10. Local login/logout có session fixation protection, CSRF cho browser actions.
11. Có lựa chọn local logout và global CAS logout với UX chính xác.
12. CAS `/logout` được triển khai với service redirect allowlist, không open redirect.
13. CAS SLO được bật/cho phép ở CAS Server, callback đúng service URL.
14. `SingleSignOutFilter` chạy đúng thứ tự trước CAS auth chain/body-reading filter.
15. `SingleSignOutHttpSessionListener` được đăng ký đúng một lần và cleanup mapping.
16. CAS SLO source trust được enforce bằng mTLS/gateway controls, không tin client headers.
17. `SessionIndex` map đúng service ticket ID, không dùng username/JSESSIONID để suy hủy.
18. SLO duplicate/unknown/late callbacks idempotent và có reason-code logs.
19. Sau SLO, old cookie/session không còn vào được protected endpoints.
20. Multi-node ST→Session mapping/revocation có thiết kế và failover tests thật.
21. CAS outage/callback loss có session TTL/revocation fallback, alert và runbook.
22. API/Session authorization không phụ thuộc duy nhất vào SLO delivery.
23. Query `ticket` và form `logoutRequest` bị redact ở CDN/ingress/APM/application logs.
24. Unit, component, integration và E2E CAS tests đều chạy với security negative paths.
25. CAS service credentials, cert/truststores và audit protected theo RBAC.
26. Không thay filter behavior/disable validation để đạt login happy path.

## 23. Câu hỏi ôn tập

1. **CAS TGT và ST khác gì nhau?** — TGT quản lý CAS SSO session, ST là vé một lần dành cho một service.
2. **TGC và JSESSIONID có phải một?** — Không; CAS SSO cookie khác local app session cookie.
3. **`CasAuthenticationEntryPoint` làm gì?** — Redirect browser tới CAS login với service URL.
4. **`CasAuthenticationFilter` làm gì?** — Nhận ST tại `/login/cas` và yêu cầu AuthenticationManager.
5. **`CasAuthenticationProvider` lấy identity từ đâu?** — Từ CAS TicketValidator đã xác minh ST và local user mapping.
6. **Tại sao ST không được validate hai lần?** — CAS tiêu thụ ST ở lần validation đầu theo giao thức.
7. **Sai `service` gây lỗi gì?** — `INVALID_SERVICE`, và ticket thường đã bị consume.
8. **CAS XML success có tự cấp `reports:read` không?** — Không; còn local account/authority policy.
9. **Local logout có hủy CAS TGT không?** — Không mặc định.
10. **CAS global logout có xóa mọi local session ngay lập tức không?** — Không đảm bảo; SLO delivery là best effort.
11. **`SingleSignOutFilter` phải chạy ở đâu?** — Trước CAS authentication processing để thấy ticket và logout callbacks.
12. **`SingleSignOutHttpSessionListener` dùng làm gì?** — Dọn ticket/session mappings khi session bị hủy.
13. **CAS SLO SessionIndex chứa gì?** — Thường là service ticket ID để tra đúng local session.
14. **Có được xóa mọi sessions theo NameID/username không?** — Không, trừ một workflow revoke-all riêng được ủy quyền.
15. **Vì sao SLO vào node khác có thể không hoạt động?** — Mapping ST→session local không có ở node đó.
16. **Làm sao chứng minh SLO thật sự hủy phiên?** — Sử dụng old cookie gọi protected API và xác minh không còn authenticated.
17. **Vì sao mTLS/ingress trust quan trọng cho SLO?** — CAS SLO XML có thể không cung cấp một chữ ký đáng tin, tránh forged logout.
18. **CAS `/serviceValidate` khác `/proxyValidate` thế nào?** — `/serviceValidate` chỉ ST, `/proxyValidate` dành profile nhận PT và proxy chain.
19. **Vì sao không log ST?** — ST là bearer credential dù chỉ dùng một lần.
20. **Kết quả QA tổng hợp cần gì?** — Đúng CAS Login/ST validation, local authorization/session, local/global logout, SLO ticket-to-session, security tests và multi-node behavior.

## Tài liệu tham khảo

- [Spring Security 7 — CAS Authentication, Service Ticket và Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Spring Security — Project Modules, spring-security-cas.jar](https://docs.spring.io/spring-security/reference/modules.html)
- [Apereo CAS — CAS Protocol Specification: login, /serviceValidate, ST one-time, SLO](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Apereo CAS — Logout and Single Sign-Out (best-effort, front/back channel)](https://apereo.github.io/cas/development/installation/Logout-Single-Signout.html)
- [Apereo Java CAS Client — README, SingleSignOutFilter và listener](https://github.com/apereo/java-cas-client/blob/master/README.md)
- [Maven Central — Apereo CAS Client Core versions](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client-core)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)