# Luồng CAS thông báo kết thúc phiên đến các dịch vụ

> **Module:** Spring Security – federation · **Nhóm:** Đăng xuất CAS. Bài học trình bày CAS **Single Logout (SLO)** khi một phiên đăng nhập tập trung bị kết thúc: CAS Server biết những service nào đã nhận Service Ticket, phát thông báo đến từng service và **CAS client** phải xóa đúng local session. Nội dung áp dụng **native CAS protocol** chứ không trộn lẫn với SAML 2.0 SLO hay OpenID Connect logout. Đoạn Java thuần yêu cầu JDK 17+; các đoạn Spring Security/CAS Java Client cần dependencies và kiểm tra tương thích Spring Boot/Security/Servlet API theo phiên bản thực tế.

## 1. Tại sao CAS logout cần thông báo đến từng ứng dụng?

Giả sử cùng một người dùng sử dụng ba ứng dụng nội bộ:

| Hệ thống | Cơ chế đăng nhập | Trạng thái phiên |
| --- | --- | --- |
| CAS Server `https://sso.example.org/cas` | Xác thực user/MFA, cấp ticket | TGT trong CAS ticket registry, TGC cookie tại CAS domain |
| Portal A | Validate ST riêng do CAS phát | Local HttpSession/SecurityContext A |
| Reports B | Validate ST khác nhờ CAS SSO | Local HttpSession/SecurityContext B |
| Workflow C | Validate ST thứ ba | Local HttpSession/SecurityContext C |

**CAS Server là nơi xác thực tập trung, không phải quản lý HttpSession của A/B/C.** TGT có thể còn hoạt động khi A logout local; ngược lại, CAS xóa TGT không tự động vô hiệu hóa ba sessions nằm ở ba ứng dụng khác nhau.

**CAS Single Logout (SLO)** bổ sung khả năng thông báo: khi một CAS SSO session kết thúc, CAS tìm các **services đã được sử dụng trong session** và gửi các logout messages. Mỗi service **phải xử lý** notification, tìm đúng local session từng được đăng nhập bằng Service Ticket do CAS phát và invalidate nó.

Điều cần nhớ: **CAS phát notification, client mới thực sự terminate application session**. Việc CAS logout thành công không phải bảo đảm mọi application session đã bị hủy; CAS SLO theo tài liệu là một quá trình **best effort**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt application local logout, CAS logout và Single Logout.
2. Giải thích CAS dùng quan hệ **TGT → các Service Tickets → service URLs** để lựa chọn nơi gửi notification.
3. Hiểu `SessionIndex` trong CAS SLO thường chứa **Service Ticket ID**, không phải TGT hay session cookie.
4. Đọc `logoutRequest` XML, hiểu **back-channel POST** và **front-channel** AJAX/JSONP/iframe.
5. Giải thích session mapping **ST ID → HttpSession** của CAS Java Client.
6. Tích hợp `SingleSignOutFilter` và `SingleSignOutHttpSessionListener` với Spring Security CAS.
7. Bảo vệ SLO callback: nguồn gửi, XML parsing, scope, replay và CSRF boundary.
8. Thiết kế multiple pods với distributed session repository và session mapping.
9. Hiểu giới hạn best-effort, timeout, logout event đến muộn và partial success.
10. Chạy Java 17 demo mô phỏng nhiều sessions, gửi notification, idempotency và isolation.

## 2. Phân biệt ba mức logout

| Thao tác | Ai khởi tạo? | Phiên được kết thúc | Điều không tự xảy ra |
| --- | --- | --- | --- |
| **Local logout A** | User bấm đăng xuất trong Portal A | HttpSession và Spring SecurityContext **A** | TGT/TGC CAS và sessions B/C không tự mất |
| **CAS logout** | Browser/user hoặc CAS policy kết thúc SSO | TGT trong CAS Server và CAS browser SSO cookie | Local HttpSession A/B/C không bị CAS trực tiếp xóa |
| **CAS SLO** | CAS phát notifications sau CAS logout/expiration theo chính sách | **Các CAS clients** tự invalidate sessions tương ứng | Không bảo đảm 100% delivery/success, không mặc định xóa mọi phiên của cùng user trên mọi thiết bị |

### 2.1. Vì sao local logout có thể dẫn đến login lại ngay?

User logout Portal A, nhưng TGC CAS vẫn tồn tại. Khi browser vào lại Portal, A redirect CAS login; CAS thấy TGC/TGT hợp lệ nên có thể phát **ST mới** mà không hỏi password. Từ góc nhìn user, thao tác logout A “không giữ được”. Đó là khác biệt giữa logout local và logout SSO, không phải ST bị reuse.

### 2.2. Vì sao CAS logout có thể để Reports còn authenticated?

CAS chỉ kiểm soát TGT/TGC ở CAS Server. Reports B đã validate `ST-B` và lập local HttpSession B; request `GET /reports` sau này sử dụng session cookie Reports, không liên hệ CAS trên từng request. Nếu B không cài SLO client hoặc notification không đến, Reports vẫn có thể phục vụ request authenticated cho đến local expiry/logout.

### 2.3. SLO không đồng nghĩa “đăng xuất tất cả thiết bị”

CAS SLO thông thường tác động **một CAS SSO session** và những services được ghi nhận trong TGT đó. Cùng user trên laptop B có thể có TGT riêng và các application sessions khác. Nếu yêu cầu “logout all devices”, cần chính sách revocation phiên rộng hơn, không suy ra chỉ từ SLO notification cho TGT hiện tại.

## 3. Các ticket và cookie tham gia SLO

| Ký hiệu | Ai giữ? | Vai trò |
| --- | --- | --- |
| **TGT — Ticket-Granting Ticket** | CAS Server | Phiên SSO; biết services đã xác thực |
| **TGC — Ticket-Granting Cookie** | Browser, scoped CAS domain | Để CAS nhận lại SSO session khi /login được truy cập |
| **ST — Service Ticket** | CAS Server phát; browser đưa cho service; service validate | Một lần cho một service; ST ID còn dùng để correlate CAS SLO |
| **HttpSession ID** | Service A/B/C và browser cookie | Xác định local application session, CAS Server không biết trực tiếp |
| **CAS SLO SessionIndex** | Trong logoutRequest CAS gửi | **ST ID** trước đó dành cho service cần logout |
| **CAS client session mapping** | Từng CAS service | `ST ID → local HttpSession` để invalidate |

**Không dùng TGT làm CAS client session key.** CAS client không cần biết CAS TGT secret. Nó chỉ nhận ST của mình và biết session nào được thiết lập sau ST validation.

### 3.1. CAS biết service nào qua ST records

```text
CAS TGT-USER-001
  |
  +-- issued ST-PORTAL-001 -> Portal A
  +-- issued ST-REPORTS-002 -> Reports B
  +-- issued ST-WORKFLOW-003 -> Workflow C

Portal local mapping:  ST-PORTAL-001 -> HttpSession P-123
Reports local mapping: ST-REPORTS-002 -> HttpSession R-456
Workflow mapping:      ST-WORKFLOW-003 -> HttpSession W-789
```

Khi CAS kết thúc TGT, nó có thể gửi đến Portal message có SessionIndex=`ST-PORTAL-001`; Reports nhận SessionIndex=`ST-REPORTS-002`; Workflow nhận `ST-WORKFLOW-003`. Mỗi app tìm đúng session riêng.

### 3.2. ST hết hiệu lực login nhưng ID vẫn có ích

Service Ticket đã được CAS validate thì **không dùng lại để login**. Tuy nhiên ID của ST vẫn có thể được CAS client lưu dưới dạng **correlation key** cho logout. Đây không phải cho phép replay ST. Mapping này phải được xóa khi application session hết hạn, local logout hoặc SLO đã xử lý.

**Không log raw ST**, vì ST có thể lộ khi chưa consume và ST ID sau đó còn có thể tham gia targeted forced-logout nếu SLO endpoint thiếu xác thực caller.

### 3.3. Hai browser sessions của cùng user

```text
Browser 1: TGT-1 -> ST-A-1 -> AppSession-A-1
Browser 2: TGT-2 -> ST-A-2 -> AppSession-A-2
```

CAS logout TGT-1 chỉ nên invalidate AppSession-A-1. **Không** đọc `NameID=alice` rồi xóa mọi session của `alice`, vì như vậy có thể gây ảnh hưởng sai phạm vi hoặc cross-tenant.

## 4. Trình tự đăng nhập trước khi SLO

### 4.1. Portal và Reports cùng dùng CAS SSO

```text
Browser               Portal A                CAS Server               Reports B
  |                      |                         |                        |
  | GET /dashboard       |                         |                        |
  |--------------------->|                         |                        |
  |<---------------------| redirect /cas/login?service=Portal             |
  |------------------------------------------------>|                        |
  |                  CAS login/TGT/TGC              |                        |
  |<------------------------------------------------| redirect ST-PORTAL-1   |
  | GET Portal callback?ticket=ST-PORTAL-1         |                        |
  |--------------------->|                         |                        |
  |                      | CAS /serviceValidate    |                        |
  |                      |------------------------>|                        |
  |                      |<------------------------| cas:user=alice         |
  |                      | map ST -> P-session     |                        |
  |                      |                         |                        |
  | GET Reports /finance -----------------------------------------------> |
  |<---------------------------------------------- redirect CAS /login   |
  |------------------------------------------------>|                        |
  |                   CAS TGC still valid            |                        |
  |<------------------------------------------------| ST-REPORTS-1 redirect |
  |--------------------------------------------------------------------> |
  |                                    Reports validates, maps ST -> R-session |
```

CAS TGT hiện ghi nhận hai services. Portal A và Reports B **không dùng cùng HttpSession** dù user chỉ nhập mật khẩu một lần.

### 4.2. Mỗi service bắt đầu lưu ST→session khi nào?

Sau khi CAS `/serviceValidate` xác nhận ST đúng service và Spring Security tạo authenticated context, CAS client SLO handler cần biết **ST ID của login này liên hệ HttpSession nào**. Có thư viện CAS client tự ghi mapping qua filter/handler trong quá trình login; khi tùy biến filter hoặc session fixation policy phải kiểm tra mapping được tạo **đúng phiên đã authenticated**.

**Không** lưu mapping chỉ vì browser gửi `ticket=ST-...` mà chưa validate ST: attacker có thể gửi ticket giả, làm nhiễu mapping hoặc session. Tích hợp CAS client chuẩn và xác minh behavior bằng integration test.

## 5. Khi CAS TGT bị kết thúc: CAS phát các thông báo

### 5.1. Sự kiện bắt đầu

Thông thường user logout CAS qua `/cas/logout` hoặc TGT hết hạn theo chính sách CAS. CAS server xóa/expire SSO state; nếu bật Single Logout cho các registered services, CAS lựa chọn những services/tickets cần thông báo.

CAS Protocol và Apereo CAS mô tả SLO khi **TGT được chấm dứt có chủ đích**; việc phát khi idle timeout có thể phụ thuộc cấu hình/phiên bản. Không tự khẳng định mọi cleanup job/TTL eviction sẽ phát callback như nhau.

### 5.2. Sequence tổng thể

```text
Browser           CAS Server                    Portal A              Reports B
   |                  |                             |                     |
   | CAS /logout      |                             |                     |
   |----------------->|                             |                     |
   |                  | expire TGT / clear TGC      |                     |
   |                  | lookup ST/service records   |                     |
   |                  |                             |                     |
   |                  | POST SLO for ST-PORTAL-1    |                     |
   |                  |---------------------------->|                     |
   |                  |                             | find mapping        |
   |                  |                             | session.invalidate |
   |                  |<----------------------------| HTTP response       |
   |                  |                                                   |
   |                  | POST SLO for ST-REPORTS-1 ----------------------->|
   |                  |                                                   | invalidate
   |                  |<--------------------------------------------------| HTTP response
   |<-----------------| CAS logout UI/redirect     |                     |
```

Sơ đồ minh họa luồng hợp lý, **không cam kết thứ tự**: Apereo CAS có cơ chế back-channel bất đồng bộ và có thể không chờ toàn bộ apps trả kết quả. CAS logout không bị rollback nếu một service lỗi.

### 5.3. CAS logout không trực tiếp xóa cookie applications

Cookie TGC tại `sso.example.org` khác cookie `JSESSIONID` tại `portal.example.org`. CAS Server không thể gọi Java `session.invalidate()` ở Portal A từ xa. Nó **gửi notification**, rồi CAS client A tra mapping ST→HttpSession và thực hiện invalidation nội bộ.

Browser có thể **vẫn giữ JSESSIONID cũ** dù session server đã bị hủy. QA cần gửi lại cookie cũ tới protected route và xác nhận bị coi anonymous/redirect login; không dựa vào việc browser cookie còn hiển thị.

## 6. Back-channel: CAS Server gửi HTTP POST trực tiếp

Apereo CAS định nghĩa kiểu `BACK_CHANNEL` thường dùng nhất cho CAS client server-side.

### 6.1. Thông báo và đường đi

```text
CAS Server
  POST https://portal.example.org/login/cas
    Content-Type: application/x-www-form-urlencoded
    logoutRequest=(CAS SLO XML đã được form-encode)
        |
        v
Reverse proxy -> CAS client SLO handler/filter
        |
        v
Parse SessionIndex = ST-PORTAL-1
        |
        v
Lookup ST-PORTAL-1 -> HttpSession P-123
        |
        v
P-123.invalidate()
        |
        v
Remove ST→session mapping / return HTTP result
```

Đây là **server-to-server request**, không phải browser gửi session cookie của Portal. CAS có thể POST đến **original service URL** đã dùng để cấp ST, hoặc `logoutUrl` riêng đã khai báo trong registered service configuration.

### 6.2. Ví dụ LogoutRequest

Apereo CAS SLO dùng XML có dạng:

```xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_sample-event-001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z">
  <saml:NameID>alice</saml:NameID>
  <samlp:SessionIndex>ST-PORTAL-1</samlp:SessionIndex>
</samlp:LogoutRequest>
```

Đây là **fixture minh họa**, không phải thông báo signed thật. Ý nghĩa quan trọng:

- `SessionIndex`: **CAS Service Ticket ID** để client tìm session, không phải HttpSession ID.
- `NameID`: có thể mô tả principal, **không dùng đơn độc để xóa mọi session cùng username**.
- `ID`/`IssueInstant`: có thể hỗ trợ replay/freshness checks tùy implementation.
- XML namespace có chữ SAML2 **không chứng minh request có chữ ký số** hoặc tuân full SAML2 SLO profile.

Trong CAS SLO truyền thống, **message có thể không chứa chữ ký XML**. Nếu endpoint public chấp nhận POST với chỉ `SessionIndex` rồi invalidate bất kỳ session nào, attacker biết ST ID có thể gây forced logout. Bảo vệ caller/network và correlation là bắt buộc theo threat model.

### 6.3. Một HTTP request minh họa

```http
POST /login/cas HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=URL_ENCODED_CAS_SLO_XML
```

`URL_ENCODED_CAS_SLO_XML` là ký hiệu mô tả. Trong thực tế CAS Java Client parse parameter theo API; không tự viết XML string parser bằng regex. Không log raw form body, query, NameID hay ST.

### 6.4. CAS mặc định gửi SLO tới URL nào?

Tài liệu Apereo mô tả mặc định CAS gửi logout request đến **service identifier** được dùng lúc authentication. Registered service có thể cấu hình `logoutUrl` riêng, ví dụ:

```json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "name": "Portal CAS Client",
  "id": 2101,
  "serviceId": "https://portal[.]example[.]org/login/cas",
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://portal.example.org/cas/slo"
}
```

JSON trên là **schema minh họa**; cách serialize/validate configuration và service ID matching strategy phụ thuộc version Apereo CAS. Không tự dùng ở production nếu chưa kiểm chứng CAS release/service registry đang chạy.

Nếu đã đặt `logoutUrl=/cas/slo`, ingress, application routing và SLO handler phải tiếp nhận POST ở đúng URL. Một custom Spring controller chỉ cho phép GET có thể trả 405 trước khi SLO filter xử lý.

## 7. Front-channel: CAS yêu cầu browser thông báo logout

Một số CAS versions hỗ trợ `FRONT_CHANNEL`: CAS dùng browser gửi yêu cầu đến applications, thường thông qua AJAX/JSONP GET hoặc iframe.

```text
CAS logout page in browser
     |
     +--> GET Portal SLO URL?
          logoutRequest=BASE64_MESSAGE&callback=...
     |
     +--> GET Reports SLO URL?
          logoutRequest=BASE64_MESSAGE&callback=...
     |
     +--> Client code/filter xử lý khi hỗ trợ
```

Apereo CAS documentation **cảnh báo không phải mọi CAS clients hỗ trợ front-channel**. Các yếu tố rủi ro:

- Browser/tab đóng trước khi AJAX/iframe hoàn tất.
- Third-party cookie restrictions, `SameSite`/CSP/CORS, popup/tracking blockers.
- App client không nhận JSONP GET variant hoặc method/path khác cấu hình.
- JS lỗi, slow network, service bị down.
- GET mang logout data có nguy cơ bị gọi giả/cached/logged nếu handler tùy biến không xác thực context.
- Không thể kết luận mọi service đã invalidated chỉ vì CAS logout page load xong.

**Cân nhắc lựa chọn:** Ứng dụng Spring MVC dùng server-side session thường phù hợp với BACK_CHANNEL có xác thực CAS callback origin, nếu CAS Server gọi được service URL. FRONT_CHANNEL cần kiểm thử browser/client hỗ trợ cụ thể, không bật bằng suy đoán.

## 8. Registered service cấu hình loại thông báo

Trong Apereo CAS service management, `logoutType` có các ý nghĩa:

| logoutType | Hành vi |
| --- | --- |
| `BACK_CHANNEL` | CAS Server gửi POST trực tiếp theo CAS SLO protocol |
| `FRONT_CHANNEL` | CAS Server dùng browser để phát các logout notifications |
| `NONE` | Không gửi SLO notification tới service này |

Theo Apereo CAS docs, BACK_CHANNEL là default được nêu với registered services ở những phiên bản tương ứng. Cần kiểm tra release hiện deploy và registry actual vì system default có thể thay đổi do policy.

### 8.1. SLO không tự cài client handler

Bật SLO ở CAS Server **chỉ có nghĩa CAS gửi notifications**. Nếu service không có CAS client SLO handler, POST có thể bị log là request lạ, trả 404/405/403 hoặc 200 từ wrong handler, trong khi session vẫn sống. Chỉ kiểm tra server-side `logoutType=BACK_CHANNEL` chưa đủ.

### 8.2. Service-specific logoutUrl khác /login callback

Service CAS login có thể dùng `https://portal.example.org/login/cas` còn logout notifications đi `https://portal.example.org/cas/slo`. Vì vậy phải:

1. Đăng ký `logoutUrl` trong CAS service registry với origin/path đã duyệt.
2. Mở đường mạng CAS Server → service callback bằng HTTPS.
3. Configure CAS client filter/handler nhận POST ở đúng path.
4. Bảo vệ nguồn thông báo, không cho arbitrary browser POST hủy sessions.
5. Test actual session invalidation, không chỉ thông báo đã đến ingress.

Không lấy `logoutUrl` từ query browser, không dùng wildcard host/port/path không rõ owner.

## 9. CAS Java Client và Spring Security: session mapping

### 9.1. Các thành phần trong ứng dụng

| Thành phần | Vai trò |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirect browser đến CAS login khi cần authentication |
| `CasAuthenticationFilter` | Nhận ST từ CAS callback để tạo authentication request |
| `CasAuthenticationProvider` | Validate ST qua CAS Server/TicketValidator, tạo principal trong Spring Security |
| `ServiceProperties` | Public service URL dùng để issue/validate ticket |
| **`SingleSignOutFilter`** | CAS Java Client filter nhận SLO requests và duy trì/xử lý ticket-session mapping theo version |
| **`SingleSignOutHttpSessionListener`** | Dọn mapping khi HttpSession hết hạn hoặc bị invalidate |
| `SessionMappingStorage` | Contract lưu/tra ST→HttpSession trong CAS client |
| `SecurityContext`/`HttpSession` | Trạng thái authenticated cục bộ service cần được hủy |

**Chú ý:** `SingleSignOutFilter` và listener thuộc **Apereo CAS Java Client**, không phải `Saml2LogoutRequestFilter` của Spring Security SAML2.

### 9.2. Vì sao listener quan trọng?

Service đã lưu `ST-A-1 → HttpSession A-1`. Khi user local logout A hoặc session idle timeout, mapping cũ phải bị xóa. Nếu không, map có thể tích tụ stale references, tăng memory và nguy cơ một SLO message cũ gây ảnh hưởng sai session sau authentication mới.

`SingleSignOutHttpSessionListener` giúp cleanup map khi session lifecycle kết thúc; trong multi-pod cần xác minh mapping thực tế thuộc đúng distributed implementation và các nodes.

### 9.3. Thứ tự filter thực sự quan trọng

`SingleSignOutFilter` phải nhận requests và được đặt phù hợp **trước CAS auth filter** để xử lý POST notification mà không bị chuyển qua login redirect, CSRF handler hoặc @Controller sai.

CAS Java Client có thể đồng thời dùng filter này để ghi nhận association ticket→session trên incoming login requests. Vì vậy phải test:

- Có mapping sau successful CAS ticket validation.
- Mapping trỏ tới session thật sau Spring Security session-fixation rotation.
- CAS SLO POST tìm được mapping và invalidate đúng session.
- Duplicate notification không làm hủy session mới.
- Local logout/session expiry xóa mapping.

## 10. Ví dụ cấu hình Spring Boot Servlet

Đây là ví dụ **class cấu hình Spring**, cần CAS Java Client tương thích với Jakarta Servlet trên Spring Boot 3.x. Các bản client đời cũ dùng `javax.servlet` có thể không chạy trực tiếp trên Boot 3 (Jakarta); hãy kiểm tra dependencies/Javadoc đúng version.

```java
import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloServletConfiguration {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSingleSignOutFilter() {
        FilterRegistrationBean<SingleSignOutFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new SingleSignOutFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloHttpSessionListener() {
        return new ServletListenerRegistrationBean<>(
                new SingleSignOutHttpSessionListener());
    }
}
```

**Đây là fragment tích hợp** chứ không phải project Spring Boot hoàn chỉnh. Còn cần CAS login entry point/filter/provider, Spring Security filter chain, CAS Server registry, session store và network security. `Ordered.HIGHEST_PRECEDENCE + 10` chỉ là ví dụ order; xác minh order trong application thật và không đăng ký trùng filter/listener nếu web.xml hoặc auto-config đã đăng ký.

Tại sao dùng `/*` mapping? CAS Java Client tài liệu thường cho filter quan sát các requests liên quan login ticket lẫn logoutRequest. Dùng dedicated path chỉ khi version/architecture bảo đảm mapping vẫn được ghi khi login, nếu không sẽ không có ticket→session mapping.

### 10.1. Spring Security giữ CSRF cho nút logout user

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CasLocalLogoutSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/logged-out"));

        // Đăng ký CAS entry point, filter và authentication provider
        // riêng theo Spring Security CAS integration.
        return http.build();
    }
}
```

`POST /logout` với CSRF token là **user-initiated local logout**. Back-channel SLO POST từ CAS Server không có form CSRF token của browser, nên cần route/filter xử lý protocol phù hợp và **nguồn gửi đáng tin**. Nếu `SingleSignOutFilter` chạy trước Spring Security chain và đã intercept notification, có thể không cần tự thêm ngoại lệ CSRF. **Không** gọi `http.csrf(csrf -> csrf.disable())` để làm callback hoạt động.

### 10.2. CAS SLO XML không phải SAML2 SLO filter

Một dòng `<samlp:LogoutRequest>` có namespace SAML2 không đồng nghĩa CAS native SLO được Spring `saml2Logout()` xử lý. Spring Security SAML2 SP có protocol signing, issuer, SAMLResponse và request repositories khác. Khi đang dùng `spring-security-cas`, hãy sử dụng **CAS Java Client SLO handler** đúng protocol/version và không trộn URLs.

### 10.3. Cấu hình web.xml truyền thống

CAS Java Client README cũng mô tả Servlet filter/listener:

```xml
<filter>
  <filter-name>CAS Single Sign Out Filter</filter-name>
  <filter-class>org.apereo.cas.client.session.SingleSignOutFilter</filter-class>
</filter>
<filter-mapping>
  <filter-name>CAS Single Sign Out Filter</filter-name>
  <url-pattern>/*</url-pattern>
</filter-mapping>
<listener>
  <listener-class>
    org.apereo.cas.client.session.SingleSignOutHttpSessionListener
  </listener-class>
</listener>
```

Không cài đồng thời web.xml + Spring Boot FilterRegistrationBean nếu nó khiến filter chạy hai lần. Với Jakarta Servlet, cấu hình deployment descriptors/schema/packages phải tương thích phiên bản container.

## 11. Global logout do user khởi tạo

### 11.1. Bắt đầu bằng thao tác có CSRF

Ứng dụng có thể đưa ra hai lựa chọn “Đăng xuất khỏi ứng dụng này” và “Đăng xuất SSO”. Form server-rendered:

```html
<!-- Thymeleaf form; cần xác nhận CSRF token đã được inject đúng. -->
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất khỏi ứng dụng</button>
</form>

<!-- /logout-sso là endpoint do app tự xây, không phải Spring default. -->
<form th:action="@{/logout-sso}" method="post">
  <button type="submit">Đăng xuất đăng nhập tập trung</button>
</form>
```

Endpoint `/logout-sso` nên kiểm tra CSRF, hủy local session theo Spring Security handlers, rồi điều hướng browser tới CAS `https://sso.example.org/cas/logout` theo URL cố định. Không nhận tùy tiện `?casLogoutUrl=...` để redirect, không dùng controller GET hủy session. Cần đảm bảo CAS logout flow/cookie theo CAS Server version.

### 11.2. Tại sao nên local logout trước CAS logout?

CAS SLO là best effort. Nếu CAS Server không gọi lại app do mạng lỗi, app khởi tạo vẫn phải kết thúc phiên local của mình. Spring Security CAS tài liệu gợi ý local logout trước rồi người dùng có thể chọn CAS global logout.

### 11.3. Đừng hứa “logout mọi ứng dụng đã thành công”

Khi CAS Server xóa TGT/TGC, app có thể báo CAS session đã kết thúc. Nhưng nếu Reports B thiếu SLO filter, hoặc callback đang lỗi, Reports vẫn có local session hợp lệ. Giao diện và báo cáo vận hành phải phân biệt:

- SSO session terminated at CAS.
- Notification attempted/delivered to service.
- Session actually invalidated by service.
- Protected resource no longer authenticated với cookie cũ.

## 12. Bảo vệ SLO endpoint khỏi forced logout

### 12.1. Thông báo XML có thể bị giả

CAS SLO back-channel truyền thống có thể không mang XML digital signature. Nếu endpoint public nhận:

```http
POST /login/cas HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=FAKE_SLO_XML
```

và handler chỉ lấy `SessionIndex` rồi invalidate session, người ngoài biết ST ID có thể cố forced logout. **Không coi HTTPS của service callback tự chứng minh caller là CAS**: HTTPS/TLS server certificate xác thực **service endpoint** cho caller, không xác thực caller nếu không có mTLS hoặc lớp source authentication khác.

### 12.2. Các lớp phòng vệ

- Giới hạn CAS back-channel qua **mTLS**, internal network routing, IP/CIDR allowlist được duy trì hoặc identity-aware ingress/gateway.
- CAS Server URL và service callback path/method phải cố định và được quản trị; không nhận từ query.
- Kiểm tra body size, XML parser hardened: cấm DTD/XXE, entity expansion, external resource access.
- Nếu deployment có signature/message authentication thật, phải verify bằng **trust anchor ngoài request**, không dùng certificate trong request chưa được trust.
- SLO session mapping scope theo trusted CAS server, service, tenant và ST ID khi multi-tenant.
- Không invalidate session theo raw `NameID` hoặc `sessionId` do request gửi.
- Chặn duplicate/late notification làm logout session mới.
- Rate-limit và log reason codes, không log raw ticket/NameID/logoutRequest XML.
- Test mTLS/ingress, route ordering và session invalidation thực.

### 12.3. CSRF exception nếu cần phải hẹp

CAS Server-to-service POST không mang form `_csrf` của browser. Nếu SLO servlet filter được đăng ký trước Spring Security `CsrfFilter` và nhận notification, không nhất thiết cần CSRF exception.

Nếu có dedicated POST `/cas/slo` trong Spring Security chain, chỉ cân nhắc ngoại lệ **đúng method/path** sau khi có source authentication. Fragment minh họa Spring Security 6.x:

```java
// CHỈ dùng khi /cas/slo là CAS back-channel endpoint thật,
// đã được bảo vệ bằng mTLS/ingress trust và SLO validation.
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new org.springframework.security.web.util.matcher
        .AntPathRequestMatcher("/cas/slo", "POST")
));
```

`AntPathRequestMatcher` có thể bị deprecated ở phiên bản mới; dùng matcher được hỗ trợ tương ứng. Không exempt `/logout/**` hay tắt CSRF toàn app. **Ngoại lệ CSRF không thay caller authentication**.

### 12.4. Front-channel GET cần threat model riêng

Với front-channel CAS SLO, browser có thể phát GET mang `logoutRequest`. Đừng viết một endpoint GET chỉ cần `?sessionId=...` là invalidate session. Nếu client không hỗ trợ validation/compatibility, dùng back-channel đã bảo vệ hoặc giải pháp revocation khác. Một GET không được tin chỉ vì nó “đến từ trang CAS” — request headers/Referer có thể thiếu và không phải chứng cứ đủ.

## 13. Multi-pod, Spring Session và ticket-session mapping

### 13.1. Static map trong CAS client không đủ cho cluster

Spring Security CAS docs minh họa `SingleSignOutFilter` dùng static session mapping. Nếu Portal có 2 pods:

```text
CAS ticket ST-PORTAL-1 được xử lý trên pod A
  -> pod A lưu ST-PORTAL-1 -> HttpSession A

CAS logout POST đi qua load balancer đến pod B
  -> pod B không có in-memory mapping
  -> không tìm được HttpSession A

Browser request tiếp theo đến pod A hoặc Spring Session store
  -> local authenticated session có thể vẫn hợp lệ
```

Có thể Spring Session Redis đã chia sẻ HttpSession data, nhưng CAS client SLO mapping vẫn local. Hai loại state khác nhau cần đồng bộ đúng.

### 13.2. Mô hình distributed mapping

```text
After validated CAS login:
  mappingKey = HMAC(trusted CAS server + service ID + ST ID)
  mappingValue = local session ID
  expiry = local session expiry upper-bound

On authenticated CAS SLO:
  parse SessionIndex = ST ID
  lookup mapping within correct CAS/service namespace
  check mapping current / not previously consumed
  invalidate server-side session in shared repository
  delete mapping atomically
  publish invalidation to other nodes if needed
```

Một `SessionMappingStorage` tùy biến/distributed hoặc integration tương ứng có thể đáp ứng, tùy CAS Java Client version. Đừng tự gán `SessionIndex` trực tiếp làm Redis HttpSession key: CAS gửi **ST ID**, không phải session ID.

### 13.3. Race và session fixation

- Khi Spring Security rotate session ID sau login, mapping phải trỏ tới phiên mới có `SecurityContext`.
- Khi local logout, xóa mapping ST cũ. Một SLO notification muộn cho ST cũ không được invalidate session mới.
- Nếu request đã bắt đầu trước SLO, nó có thể giữ Authentication trong request context cho đến khi hoàn thành; những operations nhạy cảm có thể cần revocation check gần thời điểm commit.
- SLO duplicate nên idempotent: mapping đã xóa thì không làm thêm và không chạm session khác.
- Nếu Redis/session repository lỗi, không trả lời “đã logout thành công” trước khi thực sự invalidated theo policy.

### 13.4. CAS Server cluster

CAS Server nhiều nodes cần shared ticket registry và service records nhất quán: node logout phải biết services đã cấp ticket trong TGT. Việc back-channel bất đồng bộ và failover cần health/timeout metrics. Không tự xem CAS đã gửi POST là đã thu hồi mọi ứng dụng.

## 14. Java 17: mô phỏng CAS SLO đa ứng dụng và cô lập phiên

Demo sau chạy bằng JDK 17 thuần, mô phỏng CAS Server giữ mối liên hệ TGT→tickets/services; Portal và Reports giữ ST→session mapping. Nó cho thấy **local logout không xóa CAS SSO**, CAS global logout gửi nhiều notifications, một ST cũ đã local logout không ảnh hưởng session mới, notification giả bị từ chối theo cờ trust mô phỏng và session user khác không bị xóa.

**Không phải code production:** Không có TLS, browser, CAS XML parsing, digital signature, Java Servlet session, Spring SecurityContext hoặc HttpSession store. `trustedFromCas` chỉ là boolean để dạy cách tách trust boundary; production cần caller authentication thật. Không dùng String ticket giả làm credential.

Lưu file `CasSloFlowDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CasSloFlowDemo {

    record Notification(Service service, String ticket) {}

    static final class Service {
        private final Map<String, String> sessionsByTicket = new HashMap<>();
        private final Set<String> liveSessions = new HashSet<>();

        void loginAfterValidation(String ticket, String sessionId) {
            sessionsByTicket.put(ticket, sessionId);
            liveSessions.add(sessionId);
        }

        boolean active(String sessionId) {
            return liveSessions.contains(sessionId);
        }

        void localLogout(String sessionId) {
            liveSessions.remove(sessionId);
            sessionsByTicket.entrySet()
                    .removeIf(e -> e.getValue().equals(sessionId));
        }

        boolean receiveSlo(String ticket, boolean trustedFromCas) {
            if (!trustedFromCas) {
                return false;
            }
            String sessionId = sessionsByTicket.remove(ticket);
            return sessionId != null && liveSessions.remove(sessionId);
        }
    }

    static final class CasServer {
        private final Set<String> activeTgts = new HashSet<>();
        private final Map<String, List<Notification>> ticketsByTgt =
                new HashMap<>();

        void login(String tgt) {
            activeTgts.add(tgt);
            ticketsByTgt.put(tgt, new ArrayList<>());
        }

        void recordIssued(String tgt, Service service, String ticket) {
            if (!activeTgts.contains(tgt)) {
                throw new IllegalStateException("Expired CAS session");
            }
            ticketsByTgt.get(tgt).add(new Notification(service, ticket));
        }

        boolean active(String tgt) {
            return activeTgts.contains(tgt);
        }

        List<Notification> endSso(String tgt) {
            if (!activeTgts.remove(tgt)) {
                return List.of();
            }
            return List.copyOf(ticketsByTgt.remove(tgt));
        }
    }

    public static void main(String[] args) {
        CasServer cas = new CasServer();
        Service portal = new Service();
        Service reports = new Service();
        String tgt = "TGT-DEMO";

        cas.login(tgt);
        portal.loginAfterValidation("ST-PORTAL-OLD", "session-P-old");
        cas.recordIssued(tgt, portal, "ST-PORTAL-OLD");
        reports.loginAfterValidation("ST-REPORTS", "session-R");
        cas.recordIssued(tgt, reports, "ST-REPORTS");

        // User khác có session riêng tại Reports.
        reports.loginAfterValidation("ST-OTHER", "session-other");

        System.out.println("Initially portal: "
                + portal.active("session-P-old"));
        System.out.println("Initially reports: "
                + reports.active("session-R"));

        portal.localLogout("session-P-old");
        System.out.println("Local logout keeps reports: "
                + reports.active("session-R"));

        portal.loginAfterValidation("ST-PORTAL-NEW", "session-P-new");
        cas.recordIssued(tgt, portal, "ST-PORTAL-NEW");
        System.out.println("CAS SSO still active: " + cas.active(tgt));

        boolean forged = portal.receiveSlo("ST-PORTAL-NEW", false);
        System.out.println("Untrusted notification rejected: "
                + (!forged && portal.active("session-P-new")));

        List<Notification> notifications = cas.endSso(tgt);
        int invalidated = 0;
        for (Notification notification : notifications) {
            if (notification.service().receiveSlo(
                    notification.ticket(), true)) {
                invalidated++;
            }
        }

        System.out.println("CAS SSO terminated: " + !cas.active(tgt));
        System.out.println("SLO notices sent: " + notifications.size());
        System.out.println("Sessions invalidated: " + invalidated);
        System.out.println("Portal after SLO: "
                + portal.active("session-P-new"));
        System.out.println("Reports after SLO: "
                + reports.active("session-R"));
        System.out.println("Replay changes nothing: "
                + !portal.receiveSlo("ST-PORTAL-NEW", true));
        System.out.println("Unrelated reports session: "
                + reports.active("session-other"));
    }
}
```

Biên dịch/chạy:

```bash
javac CasSloFlowDemo.java
java CasSloFlowDemo
```

Stdout **chính xác**:

```text
Initially portal: true
Initially reports: true
Local logout keeps reports: true
CAS SSO still active: true
Untrusted notification rejected: true
CAS SSO terminated: true
SLO notices sent: 3
Sessions invalidated: 2
Portal after SLO: false
Reports after SLO: false
Replay changes nothing: true
Unrelated reports session: true
```

### 14.1. Tại sao gửi 3 notifications nhưng chỉ hủy 2 sessions?

CAS đã cấp `ST-PORTAL-OLD`, `ST-REPORTS` và `ST-PORTAL-NEW` dưới cùng TGT. Portal đã local logout session gắn `ST-PORTAL-OLD`, nên notification cũ không tìm thấy mapping. Hai notifications còn lại mới hủy hai active sessions.

Đây là minh họa cho **idempotency** và lý do không xóa theo username: ST cũ không được hủy session mới chỉ vì cùng user.

### 14.2. Giới hạn chi tiết

- `HashMap`/`HashSet` chưa thread-safe/distributed; nhiều CAS nodes/Portal pods cần ticket registry và session mapping phù hợp.
- Các ticket strings dễ đoán và `loginAfterValidation` giả lập kết quả CAS validation; production phải kiểm tra ST qua CAS Server thật.
- `trustedFromCas` là tham số demo, không chứng minh HTTP POST đến từ CAS; production dùng mTLS/ingress identity hoặc message authentication được hỗ trợ.
- Không có XML parser, logoutRequest structure validation, IssueInstant, replay detection hoặc error handling network.
- Demo dispatch đồng bộ; CAS real có thể gửi best effort/asynchronously.
- Không có Spring HttpSession invalidation thực hoặc JWT revocation.

## 15. Thông báo lỗi/không đến và best effort

### 15.1. Partial logout là trạng thái có thể xảy ra

```text
CAS:
  TGT destroyed and TGC cleared

Portal:
  notification delivered -> session invalidated

Reports:
  POST failed (503) -> session still authenticated

Workflow:
  HTTP 200 but ST mapping missing -> session status unknown
```

Theo CAS protocol, server có thể bỏ qua errors của SLO requests để giữ availability: **CAS logout không rollback** nếu Reports fail. Nếu cần đảm bảo session revocation cao hơn, phải thêm controls như central revocation indicator, shorter session TTL, session introspection on sensitive actions hoặc out-of-band logout event delivery theo architecture riêng.

### 15.2. Không nhầm HTTP status với kết quả revoke

- HTTP 200 chỉ chứng minh handler/ingress đã trả response, chưa chứng minh session không còn.
- HTTP 302 có thể là redirect login do filter order; SLO request chưa được xử lý.
- HTTP 403 có thể do CSRF, auth/proxy ACL, mTLS hoặc WAF.
- HTTP 404/405 thường là callback URL/method sai.
- HTTP 500/503 có thể do session repository/network error.
- CAS /logout trả trang thành công không phải acknowledgment của tất cả services.

QA nên gửi lại request protected với **cookie cũ** và xác nhận session của service không còn authenticated. Browser không thấy CAS→service back-channel trong DevTools, cần kiểm tra server telemetry đã redacted.

### 15.3. Thông báo đến chậm và request đang chạy

Khi CAS logout xảy ra, một request vào Portal có thể đã đọc authenticated context trước khi session bị invalidate. Server không thể dừng toàn bộ threads chỉ vì CAS SLO. Operations nhạy cảm có thể cần revocation check ngay trước commit, nhất là khi tài sản quan trọng và race window không chấp nhận được.

### 15.4. Retry/duplicates

CAS SLO thường best effort; custom gateway/queue có thể thêm retries. Client phải idempotent: sau lần xử lý đầu ST mapping đã xóa, callback trùng chỉ trả kết quả phù hợp mà không đụng session khác. Không tự giả định CAS mặc định retry cho tới khi mọi service hoàn tất.

## 16. Session lifecycle và các vấn đề dễ nhầm

### 16.1. Session fixation protection

Spring Security có thể rotate HttpSession ID sau successful login. Mapping ticket→session cần trỏ tới authenticated session **sau rotation**. Nếu map ST lưu session cũ đã không còn, SLO không invalidate được phiên hiện tại. Test thật cả login, rotation, SLO và browser re-use cookie.

### 16.2. Username không đủ làm scope

User `alice` có thể đăng nhập nhiều browser hoặc tenants. Một SLO notification `NameID=alice` không cho phép hủy mọi sessions `alice` trên tất cả tenants. Ưu tiên ST mapping scoped tới trusted CAS authority/service/tenant; session deletion chỉ tác động phiên tương ứng.

### 16.3. CAS SLO và API/JWT tokens

Nếu ứng dụng ngoài HttpSession còn phát JWT/access tokens, CAS Java Client SLO có thể chỉ invalidate HttpSession. Tokens đã phát không tự bị thu hồi nếu không có revocation mechanism riêng. Cần đánh giá TTL, token introspection, back-end caches, delegated credentials theo security requirements.

### 16.4. CAS Proxy credentials

Nếu ứng dụng giữ Proxy Granting Ticket (PGT) để gọi backend theo CAS Proxy, local session logout/SLO có thể yêu cầu hủy quyền dùng PGT trong application vault. CAS TGT/logout cũng tác động PGT server-side theo CAS policy. Nhưng việc invalidate HttpSession không luôn tự xóa mọi credential store bên ngoài; cần cleanup theo lifecycle và kiểm tra CAS /proxy rejection.

## 17. Ma trận kiểm thử an toàn

| Kịch bản | Kỳ vọng |
| --- | --- |
| CAS user logout, A/B đều BACK_CHANNEL | A/B nhận SLO và invalidate sessions tương ứng |
| Local logout A không logout CAS | B và CAS SSO vẫn hoạt động |
| CAS registered service `logoutType=NONE` | Service không được CAS gửi SLO, local session có thể còn |
| CAS gửi POST đến wrong logoutUrl | 404/405 hoặc fail; alert, không tuyên bố complete |
| CAS gửi valid SLO cho ST A | Chỉ session map ST A bị invalidate |
| B nhận ST index thuộc A | B không có mapping; không invalidate |
| User có 2 browser sessions cùng username | Chỉ session thuộc TGT được logout bị hủy |
| Invalid/malformed/oversized logoutRequest | Reject, không parse nguy hiểm |
| XXE/DOCTYPE/entity expansion trong XML | Reject/harden parser |
| Back-channel POST từ untrusted caller | Reject ở mTLS/ingress/handler policy |
| XML chứa NameID nhưng không có ST mapping | Không xóa theo NameID |
| Duplicate notification | Idempotent; không hủy thêm sessions |
| Notification ST cũ đến sau login ST mới | Session mới không bị hủy sai |
| Session đã idle timeout trước CAS SLO | Mapping được cleanup, không leak |
| CAS POST tới pod khác login pod | Shared mapping/session invalidation hoặc fail closed |
| Spring Session Redis active nhưng SLO map local | Test phát hiện mismatch |
| CAS callback HTTP 200 nhưng session còn authenticated | QA FAIL, sửa handler/mapping |
| Reports backend đang down | CAS logout vẫn có thể hoàn thành, Reports partial SLO alert |
| SLO front-channel trên browser chặn iframe/third-party cookies | Không được tuyên bố complete nếu app không xử lý |
| CAS XML namespace SAML2 nhưng message không signed | Không suy ra signature verified |
| POST /logout browser thiếu CSRF | Reject; không logout |
| Exempt `/logout/**` hoặc `csrf.disable()` | Security QA FAIL |
| JWT vẫn hoạt động sau CAS SLO | Chỉ chấp nhận nếu token policy cho phép; đánh giá revocation |
| Raw ticket/logoutRequest trong nginx/APM logs | Security QA FAIL |
| CAS TGT expires by idle timeout | Verify version/policy event SLO behavior |
| Service mapping cleanup trên HttpSession destroy | Không còn stale entries/memory leak |
| Request in-flight trong lúc SLO | Behavior theo revocation policy và authorization checks |

### 17.1. E2E runbook

1. Khởi chạy CAS test Server có registered services A/B hỗ trợ SLO.
2. Browser sạch login Portal, CAS cấp ST A; service tạo local HttpSession A.
3. Truy cập Reports, CAS dùng TGC đã có để cấp ST B; service tạo local HttpSession B.
4. Xác nhận hai protected routes authenticated.
5. Thực hiện user-triggered CAS logout qua flow có CSRF bảo vệ ở service.
6. Kiểm tra CAS Server đã xóa/expire TGT và gửi notifications (logs redacted).
7. Kiểm tra A/B nhận `logoutRequest` và mapping `SessionIndex`, sau đó invalidate.
8. Gửi lại cookies cũ tới protected routes A/B; phải bị coi anonymous.
9. Test negative: wrong ST, duplicate, unknown mapping, untrusted caller và XML hỏng.
10. Test failure: service B down hoặc SLO POST đến pod khác, CAS logout vẫn có thể thành công nhưng app B local session còn; đánh dấu partial.
11. Kiểm tra logs/proxy/APM không lưu raw ticket/NameID/TGT/HttpSession IDs.
12. Test user khác/tenant khác không bị logout bởi notification này.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| CAS logout xong Portal vẫn login | SLO filter chưa chạy, mapping thiếu, callback không tới | Kiểm tra service registry, filter order, ST→session map |
| CAS SLO POST trả 403 | CSRF/proxy ACL/mTLS/security chain | Tìm tầng chặn; giữ source authentication, chỉ ngoại lệ hẹp nếu cần |
| CAS POST trả 404 hoặc 405 | `logoutUrl`/HTTP method/router sai | Kiểm tra original service URL, dedicated logoutUrl và ingress |
| CAS SLO có XML nhưng không tìm thấy session | Session mapping chỉ trong pod khác hoặc bị xóa | Shared SessionMappingStorage và session repository |
| Một pod xử lý được, pod khác không | Static map local, load balancer không sticky | Distributed mapping và invalidation |
| User local logout rồi login lại không hỏi password | TGC/TGT CAS còn | Phân biệt local vs CAS logout |
| Reports session còn khi CAS TGT xóa | Notification missed hoặc app không SLO enabled | Alert partial logout; add SLO handler/TTL |
| SLO chỉ hỏng trên browser mới | FRONT_CHANNEL/third-party cookie/CSP/JS | Test client/browser support, cân nhắc BACK_CHANNEL |
| 200 từ SLO callback nhưng session vẫn sống | Wrong handler ack, session repository không invalidate | Test protected route sau callback |
| Logout event ST cũ xóa session mới | Mapping stale sau local logout/session rotate | Listener cleanup và correct session binding |
| CAS callback XML bị SAML2 filter reject | Nhầm native CAS protocol và SAML 2.0 SLO | CAS Java Client SingleSignOutFilter |
| CAS Server không gửi SLO trên timeout | Version/cấu hình idle-expiry policy | Test điều kiện CAS TGT expiration thực |
| Access logs có `ticket`/`logoutRequest` | Request/query/body tracing chưa redact | Sanitize ingress, CAS HTTP client, APM, support tooling |

## 19. Monitoring và audit không làm lộ ticket

Một pipeline logs có thể ghi các **event codes**:

```text
CAS:
  cas_tgt_terminated
  cas_slo_service_selected
  cas_slo_notification_attempted
  cas_slo_notification_result

APPLICATION:
  cas_slo_notification_received
  cas_slo_caller_verified
  cas_slo_ticket_mapping_found
  cas_slo_local_session_invalidated
  cas_slo_mapping_removed
  cas_slo_processing_error
```

Metric gợi ý: `cas_slo_notifications_sent_total`, `cas_slo_callbacks_received_total`, `cas_slo_mapping_miss_total`, `cas_slo_sessions_invalidated_total`, `cas_slo_failures_total` và `cas_slo_processing_latency_seconds`, label bằng allowlisted service identifiers. Không gắn raw ST, TGT, session cookie, NameID/email hoặc arbitrary URL vào labels/logs.

**Redact ở nhiều tầng:** CAS HTTP client, reverse proxy/Ingress, WAF, servlet access log, distributed trace, APM và error handler. Tránh log raw XML/`logoutRequest` hoặc browser ticket query. Khi debug dùng ID sự kiện nội bộ và thông tin service đã duyệt.

## 20. Checklist production

- [ ] Phân biệt local logout, CAS logout và CAS SLO notification.
- [ ] CAS Server/registered services bật đúng `logoutType` và `logoutUrl`.
- [ ] BACK_CHANNEL POST có thể tới đúng SLO endpoint qua TLS.
- [ ] `SingleSignOutFilter`/`SingleSignOutHttpSessionListener` tương thích CAS client release và Servlet API.
- [ ] Filter order đúng so với CAS authentication và Spring Security chain; không đăng ký trùng.
- [ ] CAS client lưu ST→HttpSession mapping sau validated login.
- [ ] Session destroy/local logout dọn stale mappings.
- [ ] User POST local/global logout được bảo vệ CSRF.
- [ ] CAS SLO back-channel xác thực nguồn; XML parser chống XXE/oversize.
- [ ] Không xem CAS XML namespace SAML2 là chữ ký đã được verify.
- [ ] SessionIndex được hiểu là Service Ticket ID, không phải TGT hoặc HttpSession ID.
- [ ] Không logout theo raw NameID/browser query session ID.
- [ ] Duplicate/delayed events không invalidate phiên mới khác.
- [ ] Multi-pod sessions và SLO mappings được đồng bộ/invalidated đúng.
- [ ] CAS SLO best effort được monitoring và có kế hoạch partial failure.
- [ ] Browser/front-channel chỉ dùng nếu CAS client hỗ trợ và đã test SameSite/CSP.
- [ ] UI không tuyên bố logout mọi nơi chỉ vì CAS /logout thành công.
- [ ] SLO không tự revoke JWT/PGT hoặc credentials ngoài HttpSession nếu app còn quản lý.
- [ ] QA bằng gửi lại cookie cũ sau SLO, xác minh protected route không authenticated.
- [ ] Không log ST/TGT/TGC/logoutRequest/NameID/cookies trong ingress/APM.
- [ ] Có negative tests cho untrusted caller, XML, cross-tenant, session mismatch, replay và service outage.

## 21. Câu hỏi ôn tập

**1. Vì sao logout CAS Server không trực tiếp xóa HttpSession Portal?**  
CAS quản lý TGT/TGC của mình, không sở hữu session store Portal. CAS phải thông báo; Portal client mới tìm và invalidate local session.

**2. CAS SLO SessionIndex mang giá trị gì?**  
Trong native CAS SLO, là **Service Ticket ID** từng gửi tới CAS service, giúp ánh xạ đến phiên local.

**3. Có nên lấy NameID=alice rồi xóa mọi phiên alice?**  
Không. Một user có nhiều sessions/tenants; chỉ session phù hợp ST mapping phải bị hủy.

**4. BACK_CHANNEL và FRONT_CHANNEL khác nhau?**  
BACK_CHANNEL: CAS Server POST trực tiếp. FRONT_CHANNEL: browser AJAX/JSONP/iframe theo version và client support.

**5. CAS SLO XML dùng namespace SAML2 có nghĩa message được ký?**  
Không. Cần xác thực nguồn bằng trust boundary triển khai và signature nếu thực sự có/được verify; không mặc định signed.

**6. Vì sao cần SingleSignOutHttpSessionListener?**  
Để dọn ST→HttpSession mapping khi local HttpSession bị hủy/hết hạn.

**7. CAS Server gửi 200 từ callback có chắc phiên hết?**  
Không. Phải kiểm tra session repository và protected resource sau SLO.

**8. Multi-node Spring Session Redis có tự chia sẻ CAS client SLO mapping không?**  
Không nhất thiết. Session store và ST→session mapping có thể tách; cần thiết kế distributed mapping riêng.

**9. Logout notification của ST cũ đến sau login ST mới thì sao?**  
Không được hủy session mới nếu không thuộc mapping cũ; cleanup và idempotency.

**10. CAS logout xóa TGT nhưng Reports không nhận POST; trạng thái thế nào?**  
CAS SSO đã kết thúc, Reports local session có thể còn — đó là partial SLO best effort.

**11. Có nên disable CSRF toàn app để nhận SLO POST?**  
Không. User logout POST vẫn cần CSRF; callback CAS phải bảo vệ nguồn và cấu hình matcher/filter riêng.

**12. FRONT_CHANNEL phụ thuộc browser những gì?**  
JavaScript/iframe/CSP/third-party cookies/SameSite/network và CAS client support; không luôn đáng tin.

**13. Nếu service sử dụng API JWT, CAS SLO có tự revoke JWT không?**  
Không. Cần token revocation/TTL policy độc lập.

**14. Có thể dùng SAML2 LogoutRequestFilter xử lý native CAS SLO không?**  
Không. Dù XML dùng SAML namespace, các giao thức và CAS client handlers khác nhau.

## 22. Tài liệu chuẩn và tham khảo

- [Apereo CAS 8.0.x — Logout & Single Logout](https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html): scope CAS/local/SLO, BACK_CHANNEL/FRONT_CHANNEL, SessionIndex=ST, logoutType/logoutUrl và tính best effort.
- [Apereo CAS 7.3.x — Logout & Single Logout](https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html): đối chiếu hành vi theo release 7.x.
- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): CAS /logout và SLO POST semantics, client/server error handling.
- [Apereo CAS 8.x — Service Management](https://apereo.github.io/cas/8.0.x/services/Service-Management.html): registered service logoutType policy.
- [Spring Security — CAS Authentication and Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): SingleSignOutFilter/SingleSignOutHttpSessionListener integration, local vs CAS logout.
- [Apereo Java CAS Client README](https://github.com/apereo/java-cas-client/blob/master/README.md): Servlet filter/listener registration; kiểm tra bản jakarta/javax tương thích.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF cho user logout/state-changing requests.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session lifecycle và session fixation.
- [OWASP XML External Entity Prevention](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): XML parser hardening.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation/cookies/logout.

**Ghi nhớ:** CAS logout hủy SSO TGT/TGC, nhưng **CAS Server chỉ gửi notification** — thường **BACK_CHANNEL POST `logoutRequest`** đến những services đã nhận ticket. Mỗi client phải ánh xạ `SessionIndex=Service Ticket ID` tới **HttpSession của chính service**, invalidate session và dọn mapping. BACK_CHANNEL/FRONT_CHANNEL đều có thể lỗi; **CAS SLO là best effort**, phải kiểm tra local session đã thực sự bị hủy, xác thực nguồn callback, không tắt CSRF bừa bãi và không xem namespace SAML2 của XML là bằng chứng chữ ký.