# Ánh xạ Service Ticket tới phiên ứng dụng để xử lý thông báo đăng xuất CAS

## 1. Vấn đề: CAS đã logout nhưng ứng dụng Spring vẫn còn phiên

Một nhân viên đăng nhập ứng dụng Spring Boot thông qua **CAS Protocol**. CAS Server phát **Service Ticket (ST)**, trình duyệt mang ticket về ứng dụng, ứng dụng xác minh ticket qua CAS Server rồi tạo `Authentication` và `HttpSession`.

Sau đó người dùng bấm **Đăng xuất khỏi CAS**. CAS Server có thể hủy phiên đăng nhập tập trung của người dùng và gửi **Single Logout (SLO) notification** tới các dịch vụ đã tham gia. Nhưng ứng dụng Spring đang có một hoặc nhiều `HttpSession` của riêng nó. Làm thế nào CAS client biết **chính xác phiên nào** phải hủy khi nhận thông báo logout?

Câu trả lời trong CAS Protocol Single Logout là: **giữ ánh xạ từ Service Ticket đã dùng khi xác thực tới phiên ứng dụng được tạo hoặc liên kết với lần xác thực đó**. CAS SLO gửi lại định danh ticket; ứng dụng dùng định danh để tìm và vô hiệu hóa phiên tương ứng. Nếu không có ánh xạ, CAS có thể đã logout thành công nhưng ứng dụng vẫn có session đăng nhập cũ.

Bài học thuộc **Spring Security - federation → Đăng xuất CAS** và tập trung đúng chủ đề **“Ánh xạ Service Ticket tới phiên ứng dụng để xử lý thông báo đăng xuất”**.

### Sau bài học, bạn có thể

1. Mô tả tách biệt **CAS TGT/TGC**, **Service Ticket**, **HttpSession/SecurityContext** và **SLO request**.
2. Vẽ luồng **đăng nhập, lưu ST → HttpSession, CAS back-channel logout và session invalidation**.
3. Giải thích vì sao `SessionIndex` trong CAS SLO message là **CAS Service Ticket ID**, không phải `JSESSIONID`, và không được nhầm với SAML Web Browser SSO session semantics.
4. Biết vai trò của **`org.apereo.cas.client.session.SingleSignOutFilter`**, **`SingleSignOutHttpSessionListener`**, **`SessionMappingStorage`** và Spring Security CAS integration.
5. Phân biệt CAS **back-channel POST** và **front-channel browser notification**, điều kiện browser/cookie và khả năng hỗ trợ của client.
6. Hiểu giới hạn của ánh xạ **in-memory** khi ứng dụng chạy nhiều pod/nodes và cách thiết kế ánh xạ session ID trên kho phân tán.
7. Xử lý mapping cleanup khi session hết hạn, local logout, user đăng nhập lại, nhiều tab và duplicate SLO notifications.
8. Phân tích bảo mật SLO callback: spoofing/logout CSRF/DoS, bảo vệ nguồn thông báo, XML parser, replay và log redaction.
9. Chạy ví dụ **Java 17 độc lập** mô phỏng ST→Session và hủy đúng phiên bằng ST mà không cần servlet container.
10. Xây test plan xác nhận SLO từ CAS Server thực đến ứng dụng Spring đã chạy.

**Ngữ cảnh kỹ thuật:** CAS Protocol của Apereo CAS, Java 17+, Spring Boot 3.x với Spring Security Servlet/MVC, CAS Java Client tương thích Jakarta Servlet. Các tên API và cách đăng ký Filter/Listener phải được đối chiếu theo phiên bản dependency. URL `cas.example.org` và `app.example.org` trong bài chỉ để minh họa.

---

## 2. Vì sao “CAS logout” không tự xóa HttpSession của ứng dụng?

Hệ thống có nhiều vòng đời độc lập:

| Thành phần | Chủ sở hữu | Giá trị điển hình | Có bị xóa tự động khi CAS logout? |
| --- | --- | --- | --- |
| **Ticket-Granting Ticket (TGT)** | CAS Server/ticket registry | Phiên SSO trung tâm | CAS Server có thể hủy theo chính sách |
| **Ticket-Granting Cookie (TGC)** | Browser tại CAS domain | Cookie tham chiếu TGT | CAS Server quản lý chính sách logout/cookie |
| **Service Ticket (ST)** | CAS Server phát cho một service | `ST-opaque-...` | ST đã được tiêu thụ khi xác minh, nhưng ID có thể dùng để liên hệ SLO |
| **HttpSession của SP/CAS client** | Ứng dụng Spring/Servlet container | Internal session ID như `JSESSIONID` | **Không tự bị CAS Server xóa** nếu client không xử lý SLO |
| **SecurityContext/Authentication** | Spring Security trong phiên ứng dụng | CAS principal + authorities | Cần session invalidation/security cleanup phù hợp |
| **Application tokens/WebSocket** | Những lớp riêng của ứng dụng | JWT, refresh token, socket connection | **Không mặc định** bị CAS SLO thu hồi |

CAS Server **không nắm trực tiếp một `HttpSession` Java object** nằm trong tiến trình ứng dụng. Nó không thể gọi `session.invalidate()` trên servlet container từ xa. CAS chỉ có thể **thông báo** tới client; chính ứng dụng có trách nhiệm tìm và hủy phiên của mình.

Apereo CAS mô tả SLO là một hoạt động **best-effort**: CAS gửi thông báo tới những service từng tham gia phiên tập trung; delivery có thể lỗi, browser có thể đóng hoặc client không hỗ trợ. Do đó **không hứa mọi thiết bị, mọi ứng dụng và token đều bị thu hồi** chỉ vì một CAS logout event đã được phát.

### Local logout khác CAS SLO

- **Local logout tại ứng dụng:** app hủy session hiện tại, nhưng **TGT/TGC tại CAS có thể còn**. Lần truy cập sau có thể nhận **ST mới** và đăng nhập không cần nhập lại password.
- **CAS logout:** CAS hủy phiên trung tâm; nếu có SLO notification, client cần xử lý và hủy local sessions đã được liên kết với phiên đó.
- **App-wide/global logout:** yêu cầu thu hồi những session/tokens khác; cần thiết kế thêm, không tự có chỉ vì ST mapping.

Mục tiêu của bài là xử lý đúng **phiên ứng dụng liên quan tới một CAS ST**, không xây một hệ thống xóa toàn bộ session của mọi account theo username do browser cung cấp.

## 3. Tại sao ánh xạ lại dùng ST, dù ticket đã được tiêu thụ?

CAS ST có hai chức năng tại hai thời điểm khác nhau:

1. **Lúc login:** ST là credential dùng **một lần** để CAS Server kiểm tra user và service. Nếu hợp lệ, ứng dụng tạo phiên.
2. **Lúc CAS SLO:** ID của ST từng cấp cho service đóng vai trò **correlation identifier**, cho CAS client xác định phiên ứng dụng cần kết thúc.

Điều này **không có nghĩa** ST cũ trở thành credential có thể dùng lại. CAS ST vẫn phải **one-time validation**. Mapping giữ ID ticket chỉ nhằm **định vị phiên để revoke**; **không** được dùng ID đó để khôi phục hoặc cấp Authentication mới.

Ví dụ:

~~~text
CAS Server cấp ST:        ST-opaque-A1
App xác minh ST:          SUCCESS, user-42
App HTTP session:         SESSION-SP-7F9
SLO mapping ở app:        ST-opaque-A1 -> SESSION-SP-7F9

Sau đó CAS logout:
  logoutRequest.SessionIndex = ST-opaque-A1

App lookup:
  ST-opaque-A1 -> SESSION-SP-7F9

App thực hiện:
  invalidate(HttpSession SESSION-SP-7F9)
  remove mapping ST-opaque-A1
~~~

**TGT ID** và **HttpSession ID** không nên xuất hiện thay thế cho `SessionIndex` của thông báo CAS Protocol SLO. Trong Apereo CAS, session identifier dùng để liên hệ SLO thường chính là **Service Ticket ID ban đầu** của service.

### Không lẫn CAS SLO với SAML 2.0 SLO

CAS Protocol SLO back-channel có thể dùng XML mang tên `<samlp:LogoutRequest>` và `<samlp:SessionIndex>`. **Hình thức XML giống SAML** không có nghĩa ứng dụng phải chuyển thông điệp này vào `Saml2LogoutRequestFilter` hoặc áp dụng nguyên trạng mọi quy tắc của **SAML 2.0 Single Logout Profile**. CAS SLO và SAML 2.0 SLO là hai **protocol integrations** khác nhau, ngay cả khi Apereo CAS Server hỗ trợ cả hai.

Trong **CAS SLO**, `SessionIndex` do CAS Server gửi được dùng để **tra ST→session**. Trong **SAML 2.0 Web Browser SSO/SLO**, `SessionIndex` thường liên quan `AuthnStatement` theo các profile SAML khác; không tự xem nó là CAS ST.

## 4. Toàn bộ luồng: login rồi SLO back-channel

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant APP as Spring Security CAS client
    participant INDEX as ST-to-HttpSession mapping
    participant CAS as CAS Server
    B->>APP: GET /private
    APP-->>B: Redirect CAS /login?service=...
    B->>CAS: GET CAS login, TGC/TGT hoặc xác thực mới
    CAS-->>B: Redirect /login/cas?ticket=ST-ABC
    B->>APP: GET /login/cas?ticket=ST-ABC
    APP->>INDEX: Gắn ST-ABC với session đang xử lý
    APP->>CAS: HTTPS /serviceValidate?ticket=ST-ABC&service=...
    CAS-->>APP: authenticationSuccess
    APP->>APP: Lưu Authentication trong HttpSession
    APP-->>B: Redirect tới resource không có ticket
    Note over CAS,APP: Lúc user logout CAS
    B->>CAS: CAS /logout
    CAS->>CAS: Hủy TGT, chọn dịch vụ từng tham gia
    CAS->>APP: POST logoutRequest với SessionIndex=ST-ABC
    APP->>INDEX: lookup ST-ABC
    INDEX-->>APP: HttpSession cần hủy
    APP->>APP: session.invalidate()
    APP->>INDEX: Dọn mapping
    APP-->>CAS: HTTP response phù hợp
    B->>APP: Request với cookie SP cũ
    APP->>APP: Không còn authenticated session tương ứng
~~~

**Lưu ý thứ tự của thư viện:** CAS Java Client `SingleSignOutFilter` thường ghi mapping khi nhìn thấy request chứa tham số ticket, **trước các filter xác thực phía sau**. Vì vậy trong code thực tế **không được coi sự tồn tại của mapping là bằng chứng ST đã validation thành công**. Chỉ kết quả CAS TicketValidator thành công mới cấp Authentication; phải dọn stale mappings sau các luồng thất bại/expiry theo policy. Một số ứng dụng tự xây mapping **sau validation success**; cần đảm bảo không làm mất khả năng nhận SLO và xử lý race.

## 5. Hình dạng thông báo CAS SLO: SessionIndex là ST

Theo Apereo CAS SLO documentation, một **back-channel logout** có thể gửi HTTP POST từ CAS Server tới service đã tham gia. Phần nội dung chứa SAML-shaped LogoutRequest, ví dụ:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_cas-logout-001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z">
  <saml:NameID>opaque-principal-42</saml:NameID>
  <samlp:SessionIndex>ST-ABC</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Đây là **XML minh họa**, không phải credential thật và cũng không có chữ ký. Trong triển khai CAS client thông thường, message có thể được chuyển trong form parameter có tên `logoutRequest`; với front-channel tùy cấu hình có thể dùng encoding khác (ví dụ Base64 trong query). **Không giả định** mọi CAS phiên bản gửi raw XML body không bọc tham số hoặc mọi front-channel đều dùng cùng format.

### Những trường thường gây hiểu sai

| Thành phần | Ý nghĩa trong CAS SLO | Không được suy |
| --- | --- | --- |
| `LogoutRequest@ID` | Định danh thông điệp logout | Không phải HttpSession ID |
| `LogoutRequest@IssueInstant` | Thời điểm thông điệp | Không phải lúc phát ST |
| `NameID` | Thông tin principal theo thông báo | Không dùng đơn độc để xóa mọi session theo email |
| `SessionIndex` | **ST ID được CAS dùng để tương quan với phiên của service** | Không phải JSESSIONID, CAS TGT hoặc SAML login SessionIndex của mọi sản phẩm |
| `logoutRequest` | Tên form/query parameter trong CAS Java Client mặc định | Không phải `ticket` login param |
| `RelayState` nếu có | Tham số phụ tùy flow/client | Không phải key session mapping cốt lõi trong CAS SLO |

### Back-channel không có cookie trình duyệt của user

Với POST trực tiếp từ **CAS Server → application**, browser của người dùng **không tham gia request này**. Vì vậy thông báo thường **không mang `JSESSIONID` của người dùng**. Một controller/filter viết:

~~~java
HttpSession current = request.getSession(false);
if (current != null) {
    current.invalidate();
}
~~~

sẽ **không tìm được session của người dùng cần logout** nếu request back-channel không mang đúng cookie. Tệ hơn, dùng `getSession(true)` có thể tạo session mới cho request của CAS Server mà vẫn không hủy session cần thiết.

Giải pháp là **tìm session của người dùng qua `SessionIndex=ST</BT> đã được ánh xạ từ lúc login**, rồi hủy session được tìm thấy. Không dựa vào browser cookie của callback back-channel.

## 6. CAS Java Client cung cấp cơ chế nào?

Một số thành phần chính trong **Apereo Java CAS Client**:

| Thành phần | Vai trò |
| --- | --- |
| `org.apereo.cas.client.session.SingleSignOutFilter` | Chặn request có ST để lưu mapping; nhận SLO callback và hủy session liên quan |
| `SingleSignOutHandler` | Xử lý logic token registration/logout message trong thư viện |
| `SessionMappingStorage` | Hợp đồng lưu mapping ticket ↔ phiên; hỗ trợ lookup và removal |
| `HashMapBackedSessionMappingStorage` | Ví dụ/default in-memory mapping trong các phiên bản client |
| `SingleSignOutHttpSessionListener` | Dọn mapping khi `HttpSession</BT> bị destroy/expire |
| `artifactParameterName` | Tên tham số login ticket, mặc định `ticket` |
| `logoutParameterName` | Tên tham số CAS SLO, mặc định `logoutRequest` |
| `logoutCallbackPath` | Giới hạn đường callback SLO theo khả năng phiên bản; không phải service URL nói chung |
| `eagerlyCreateSessions` | Điều khiển hành vi tạo session khi thấy ticket theo CAS Java Client config |
| `org.springframework.security.cas.web.CasAuthenticationFilter` | Spring Security filter xác thực CAS ticket |
| `CasAuthenticationProvider` | Spring Security provider gọi TicketValidator để xác thực ticket |

**Hai filter có trách nhiệm khác nhau:**
- `SingleSignOutFilter`: **ghi/tra/hủy session mapping** phục vụ logout.
- `CasAuthenticationFilter`: **xác thực Service Ticket** thông qua CAS TicketValidator và tạo Authentication.

Không thay thế cái này bằng cái kia. Một ứng dụng **chỉ** có `CasAuthenticationFilter` có thể login bình thường mà **không** nhận/hủy session khi CAS gửi Single Logout.

### Vì sao SLO filter cần chạy trước CAS authentication filter?

Lúc browser trở về:

~~~text
GET /login/cas?ticket=ST-A
    |
    v
SingleSignOutFilter: record ST-A → HttpSession
    |
    v
Spring Security filter chain / CasAuthenticationFilter
    |
    v
TicketValidator /serviceValidate
    |
    + success → SecurityContext ở cùng HttpSession
~~~

Để ghi mapping đúng lúc và xử lý logout POST trước các filter khác chặn request, **SingleSignOutFilter thường cần đứng sớm** hơn CAS authentication và Spring security authorization/CSRF handlers. Nếu SLO POST bị CSRF 403 ở filter khác trước khi tới CAS SLO filter, phiên ứng dụng **không bị invalidated**.

Không “giải quyết” bằng `csrf().disable()</BT> cho toàn ứng dụng. Chỉ định tuyến/đăng ký SLO filter đúng vị trí, giới hạn callback và bảo vệ nguồn theo threat model. Những phiên bản CAS client dùng Servlet Filter bên ngoài Spring Security chain có thứ tự khác; phải kiểm tra filter order thực qua integration test.

## 7. Thiết lập CAS client SLO với Spring Boot Servlet

### 7.1 Các dependency liên quan

Với project Gradle đang dùng Boot plugin/BOM phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'

    // Chọn Java CAS Client artifact/version tương thích Spring Security
    // và jakarta.servlet trong Spring Boot 3, hoặc dependency do
    // spring-security-cas/ứng dụng đã quản lý.
}
~~~

Đây là **snippet** trong project có build configuration hoàn chỉnh, không phải build file chạy độc lập. Cần kiểm tra Spring Security CAS transitive dependencies và Java CAS Client phù hợp, không kéo vào một bản **`javax.servlet`** cũ trong ứng dụng **`jakarta.servlet`** mà mong Filter hoạt động.

### 7.2 Đăng ký SingleSignOutFilter và Session Listener

Mẫu **Spring Boot Servlet configuration**, với giả định dependency hiện tại thực sự cung cấp các class `org.apereo.cas.client.session.*` tương thích:

Tệp `src/main/java/com/example/cas/CasSingleLogoutConfig.java`:

~~~java
package com.example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSingleLogoutConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilterRegistration() {
        var bean = new FilterRegistrationBean<SingleSignOutFilter>();
        bean.setFilter(new SingleSignOutFilter());

        // Phải quan sát được request login mang ticket và callback SLO.
        bean.addUrlPatterns("/*");

        // Chạy trước Spring Security CAS authentication filter.
        // Kiểm tra thứ tự thực của encoding và security filters khi deploy.
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
        bean.setName("casSingleSignOutFilter");
        return bean;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSloSessionListener() {
        return new ServletListenerRegistrationBean<>(
                new SingleSignOutHttpSessionListener());
    }
}
~~~

**Điều kiện và giới hạn:**
- Đây là **mã Spring Configuration**, không phải Java standalone; cần Boot, CAS client, Jakarta Servlet và web application thực.
- Cấu hình filter mapping `/*` giúp nó nhìn thấy `GET /login/cas?ticket=...` và callback SLO có thể gửi tới URL service hoặc URL logout riêng.
- Thứ tự `Ordered.HIGHEST_PRECEDENCE + 50` chỉ là ví dụ; phải kiểm tra `CharacterEncodingFilter` (UTF-8), Spring Security DelegatingFilterProxy và các servlet filters khác trong hệ thống thực.
- Khi cần giới hạn đường nhận logout, CAS client có `logoutCallbackPath` tùy version. Cần **giữ khả năng record login ticket** dù logout callback chỉ xử lý tại path riêng.
- Nếu ứng dụng đã đăng ký `SingleSignOutFilter` qua `web.xml`, `@EnableCasClient` hoặc auto-config, **không đăng ký trùng**.
- Spring Boot 3 dùng `jakarta.servlet.*`; CAS client version cũ có thể chỉ hỗ trợ `javax.servlet.*`. Phải dùng bản tương thích.
- Filter có thể tạo session khi thấy ticket theo `eagerlyCreateSessions` policy; thử login và kiểm tra `HttpSession` sau CAS validation thành công.
- Listener giúp dọn mapping khi session hết hạn/invalidate. Không bỏ listener vì “logout đã hoạt động” trong test ngắn hạn.
- Không đưa CasAuthenticationFilter vào Servlet Filter auto-registration **hai lần** nếu nó cũng được gắn vào Spring SecurityFilterChain.

### 7.3 Spring Security CAS phải được cấu hình riêng

`SingleSignOutFilter` **không thay** CAS authentication. Ứng dụng vẫn phải có:

1. `ServiceProperties.service` là **public callback URL**, ví dụ `https://app.example.org/login/cas`.
2. `CasAuthenticationEntryPoint` dẫn browser sang CAS login.
3. `CasAuthenticationFilter` nhận ST tại callback.
4. `CasAuthenticationProvider` dùng `TicketValidator` gọi CAS Server.
5. `AuthenticationUserDetailsService` hoặc principal mapping/authorities theo policy.
6. Spring SecurityFilterChain bảo vệ business endpoints.
7. Session persistence phù hợp khi xác thực thành công.

Một bean nhỏ minh họa `ServiceProperties` (không phải app hoàn chỉnh):

~~~java
@Bean
ServiceProperties serviceProperties() {
    var properties = new ServiceProperties();
    properties.setService("https://app.example.org/login/cas");
    properties.setSendRenew(false);
    return properties;
}
~~~

**Không copy snippet mà thiếu import/bao class**: `ServiceProperties` thuộc `org.springframework.security.cas.ServiceProperties`, `@Bean` thuộc Spring Context. Phải cấu hình chính xác CAS Server `/login`, service registry và ticket validation endpoint. Trong CAS, `service` cũng là URL CAS có thể dùng làm SLO callback nếu chưa cấu hình `logoutUrl` riêng.

## 8. Config CAS Server: gửi notification tới service nào?

Theo Apereo CAS, SLO có thể được cấu hình **per registered service**:
- `logoutType = BACK_CHANNEL` thường là lựa chọn default trong mô tả CAS.
- `logoutType = FRONT_CHANNEL` đưa notification qua browser; phụ thuộc khả năng client và browser.
- `logoutType = NONE` / disable tương ứng cho service nếu policy/phiên bản hỗ trợ.
- `logoutUrl` có thể xác định **endpoint nhận SLO riêng**, khác URL `service` dùng lúc login.

Ví dụ đoạn **CAS registered service JSON** minh họa hình thức, không phải file hoàn chỉnh vì service registry và class names phụ thuộc CAS version:

~~~json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "^https://app\\.example\\.org/.*",
  "name": "Portal CAS Service",
  "id": 102,
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://app.example.org/login/cas"
}
~~~

Lưu ý:
- `serviceId` thường là regex registration được CAS quản trị. Ví dụ chỉ minh họa; production phải **thu hẹp pattern** theo đường callback/host có quyền, không dùng wildcard quá rộng.
- CAS SLO có thể gửi tới **service URL gốc** hoặc `logoutUrl` riêng khi được cấu hình; app SLO filter cần thấy đúng path.
- `logoutUrl` chỉ là endpoint nhận notification, **không phải URL để browser bắt đầu logout**.
- Service registry CAS cần được cập nhật theo workflow vận hành, không lấy JSON tùy ý từ browser.
- CAS Server có thể gửi SLO không đồng bộ; lỗi gửi tới app chưa chắc làm CAS logout thất bại.
- Thông điệp SLO dùng Service Ticket ID liên hệ với service đăng nhập; nếu cấu hình thay đổi URL, mapping vẫn cần cùng ticket/account session.

### Kiểm tra endpoint qua trace

Trong CAS Server logs (được redacted), kiểm tra:
1. TGT bị hủy theo logout flow.
2. Các service tham gia được CAS chọn để nhận notification.
3. Đối với ứng dụng này: `logoutType`, SLO endpoint và HTTP response.
4. `SessionIndex</BT> mà CAS dùng liên hệ với ST ban đầu.
5. HTTP POST thật sự tới app (hoặc front-channel theo cấu hình).
6. App đã tra mapping, invalidate session và dọn mapping.
7. Request mới từ browser với cookie cũ không còn authenticated.

Không suy “SLO hoàn tất” chỉ từ trang logout CAS hiển thị HTTP 200.

## 9. Back-channel và front-channel: khác điểm tựa cho session mapping

| Khía cạnh | Back-channel SLO | Front-channel SLO |
| --- | --- | --- |
| Người gửi request | CAS Server trực tiếp gọi SP | Browser chuyển/call tới SP theo yêu cầu CAS |
| Phương thức thường gặp | HTTP POST | HTTP GET/JSONP/AJAX hoặc iframe, tùy CAS version |
| Browser user cookie | **Không mặc nhiên có** | Có thể có hoặc bị SameSite/third-party policies chặn |
| Payload | LogoutRequest/SessionIndex thường qua `logoutRequest` | Payload/encoding có thể khác, ví dụ base64 query |
| Dữ liệu để tìm phiên | **ST → HttpSession mapping** | Có thể vẫn cần ST mapping; không lệ thuộc cookie |
| Điểm dễ thất bại | Firewall/network, callback URL sai, node mapping khác | Browser đóng, cookie bị chặn, JS/iframe hạn chế |
| Phía app cần | Endpoint/filter nhận back-channel, session store | CAS client version có hỗ trợ front-channel và browser policy phù hợp |
| Bảo đảm “mọi session” | Best-effort, phụ thuộc service/session reachability | Best-effort, phụ thuộc browser workflow |

**Quan trọng:** Đừng tự thiết kế front-channel logout bằng `GET /logout?username=alice` rồi xóa session theo user input. CAS đã có giao thức notification và mapping ticket; các request từ browser không tự là lời yêu cầu được tin. Nếu một client **không hỗ trợ front-channel**, cấu hình CAS gửi front-channel sẽ dẫn đến local session vẫn sống dù CAS logout xảy ra.

## 10. SessionMappingStorage quản lý gì?

Trong Apereo Java CAS Client, **SessionMappingStorage** biểu diễn kho ánh xạ giữa một định danh CAS authentication token (thường là ST) và `HttpSession` của ứng dụng. Các thao tác phổ biến ở những bản Java CAS Client gồm:

- Thêm mapping: logic tương tự `addSessionById(ticket, session)`.
- Tìm và xóa theo mapping ID khi có logout: logic tương tự `removeSessionByMappingId(ticket)`.
- Xóa mapping khi session bị destroy/expire: logic tương tự `removeBySessionById(sessionId)`.
- Làm sạch mapping cũ, tránh giữ tham chiếu tới phiên đã hết hạn.

**Mô hình nhận thức:**

~~~text
Lúc login:
  CAS Service Ticket ST-ABC
          |
          v
  SessionMappingStorage
          |
          v
  HttpSession session-A
          |
          v
  SecurityContext + CAS principal

Lúc CAS SLO:
  logoutRequest.SessionIndex = ST-ABC
          |
          v
  SessionMappingStorage.removeSessionByMappingId("ST-ABC")
          |
          v
  session-A.invalidate()
~~~

Đây là mô hình tác dụng của client library, **không phải tên public API Spring Security cho phép gọi trực tiếp mọi lúc**. Với version khác nhau, một số class/method có khác tên/khả năng; không tự triển khai mapping nếu thư viện chính thức đã cung cấp đầy đủ.

### Mapping phải được tạo vào đúng thời điểm

Một anti-pattern:

~~~text
CAS ticket validation SUCCESS
    -> Spring tạo HttpSession B
    -> Mapping filter trước đó đã record ST vào HttpSession A
    -> SLO tìm A và invalidate A
    -> B vẫn authenticated
~~~

Nếu app có **session fixation protection** hoặc tạo session mới trong quá trình login, cần kiểm tra mapping trỏ tới **phiên cuối cùng đang giữ SecurityContext**. Servlet session ID có thể thay đổi vì `changeSessionId()` hoặc session migration. Đừng cho rằng `request.getSession().getId()` trước login luôn trùng với session ID sau authentication.

Trong triển khai dùng CAS client chính thức, nên kiểm thử thực tế:
1. SLO filter thấy ticket và session vào lúc nào.
2. CAS AuthenticationFilter/SessionAuthenticationStrategy có thay session không.
3. Session listener có dọn mapping khi session cũ bị hủy không.
4. SLO notification có invalidate được session đang authenticated sau login không.
5. Nếu không, chọn cấu hình session fixation strategy/extension point tương thích hoặc update mapping **sau login success** một cách an toàn.

**Không tắt session fixation protection** chỉ để giữ nguyên ID khi mapping. Phải làm cho mapping và session lifecycle tương thích.

## 11. Phân biệt mapping được ghi với xác thực thành công

Ở nhiều bản CAS Java Client, `SingleSignOutFilter` ghi mapping khi **nhìn thấy tham số `ticket`** ở request. Lúc đó CAS ST **chưa chắc được validate**. Nếu ticket invalid:
- Mapping có thể tồn tại tạm thời với session chưa authenticated;
- Không có quyền cấp access chỉ vì mapping tồn tại;
- Mapping cần được dọn khi session hết hạn, bị hủy hoặc login fail theo policy;
- Không dùng mapping như một cache xác thực.

Trong ứng dụng tự viết store, có thể chọn record mapping **chỉ sau** khi CAS validator trả success; nhưng cần xử lý **race** giữa authentication success, session persistence và một SLO notification đến gần như đồng thời. CAS có thể phát SLO ngay khi user logout ở nơi khác. Do đó phải bảo đảm:
- Chỉ lưu mapping cho verified ST;
- Mapping chỉ đến đúng phiên authenticated;
- SLO arriving before mapping không biến thành “mất logout” dẫn đến phiên mới bị tạo sau CAS logout;
- Có kiểm tra state/version/recording lifecycle và, nếu cần, cơ chế pending revocation/tombstone với TTL được thiết kế an toàn;
- Không mở quyền để giải quyết race.

Một SLO handler chỉ nhận XML rồi gọi `request.getSession(true).invalidate()</BT> sẽ **không đúng** đối với back-channel.

## 12. Dọn mapping khi session kết thúc

Có ít nhất bốn trường hợp dọn:

| Sự kiện | Hành động cần |
| --- | --- |
| CAS SLO tới với ST đã ánh xạ | Remove ST mapping, invalidate HttpSession, cleanup reverse index |
| Local logout tại ứng dụng | Invalidate HttpSession và remove mọi mapping liên quan |
| Idle/absolute session expiry | Listener cleanup mapping tránh stale memory |
| Session fixation rotation hoặc session migration | Update mapping đúng session mới; cleanup old association |
| New CAS login cho user/session đã có | Quyết định replace/merge theo policy, tránh mapping nhiều ST đến một session không nhất quán |
| Application redeploy | In-memory mapping mất; không tuyên bố SLO sẽ hoạt động cho sessions tồn tại ở kho khác nếu map không được khôi phục |
| Session already invalidated, duplicate SLO | Idempotent no-op, không xóa session khác |
| Session store/Redis outage | Đánh dấu uncertain/retry/alert, không nói logout chắc chắn thành công |

**SingleSignOutHttpSessionListener** giúp dọn mapping khi phiên bị destroy hoặc expire, tránh tích lũy các ticket IDs và tham chiếu tới HttpSession objects trong JVM. Nhưng listener cũng phải được đăng ký đúng Servlet container (Spring Boot ServletListenerRegistrationBean/web.xml) và phiên bản tương thích.

### Một session có thể gắn nhiều ST không?

Có thể xảy ra khi user login lại trong cùng browser, nhiều tab, forced reauthentication hoặc flow tùy chỉnh. Một số implementation của CAS Java Client **xóa mapping cũ theo session ID khi đăng ký ST mới**, nên về bản chất giữ mapping hiện hành cho session đó. Nếu ứng dụng tự xây multi-ticket mapping:
- Phải dọn **tất cả ticket keys** khi session bị invalidated;
- Phải xác định semantics nếu ticket cũ vẫn còn liên hệ đến TGT đã bị hủy;
- Không cho cùng ticket key trỏ đồng thời hai sessions;
- Không dùng một username chung làm mapping key;
- Đánh giá login cũ/new principal và session fixation.

Không mặc định một ST luôn bằng một session ID hoặc một user có đúng một session.

## 13. Session fixation và thay đổi HttpSession ID sau login

Spring Security có **session fixation protection**, trong Servlet stack thường có thể thay session ID khi user đăng nhập. Nếu CAS SLO filter lưu mapping vào đối tượng session trước khi login, cần kiểm tra:
- Nếu `changeSessionId()` giữ **cùng HttpSession logical object** với ID mới, mapping tham chiếu session object có thể còn hủy đúng session; reverse index theo ID phải cập nhật nhất quán.
- Nếu strategy migration/new session làm session object thay đổi, mapping cũ có thể trỏ tới session đã invalidated.
- Listener sessionDestroyed có thể dọn mapping cũ, nhưng **không tự tạo mapping mới** nếu thiếu hook.
- Với distributed session ID mapping, ID cũ và ID mới cần được update atomically theo policy.

Một bước test bắt buộc:

~~~text
1. GET /private -> redirect CAS
2. CAS callback có ticket ST-A
3. SingleSignOutFilter record mapping
4. CAS AuthenticationProvider validation SUCCESS
5. Spring session fixation strategy chạy
6. Bắt lại session ID đang chứa SecurityContext
7. CAS logout gửi SessionIndex=ST-A
8. SLO filter phải invalidate được session ở bước 6
~~~

**Không giải quyết bằng cách tắt CSRF/session fixation toàn ứng dụng.** Cấu hình session handling phải phù hợp bảo mật, đồng thời mapping phải được xử lý đúng với lifecycle.

## 14. Đăng nhập nhiều trình duyệt/thiết bị

Ví dụ user đăng nhập cùng một tài khoản qua ba browser:

| Browser | CAS ST đã dùng | HttpSession tại app |
| --- | --- | --- |
| Laptop Chrome | `ST-A` | `session-A` |
| Laptop Firefox | `ST-B` | `session-B` |
| Điện thoại | `ST-C` | `session-C` |

Các phiên này có thể thuộc những **TGT khác nhau** hoặc cùng/khác CAS SSO session tùy browser/cookie. CAS Server chỉ gửi SLO cho các authentication records nó liên hệ với TGT bị hủy.

Nếu thông báo có:
- `SessionIndex=ST-A`: ứng dụng tìm **session-A** và hủy đúng phiên đó.
- `SessionIndex=ST-B`: ứng dụng hủy **session-B** nếu record đó thuộc CAS event phù hợp.
- Không có mapping `ST-C`: không tự suy “user X” rồi hủy mọi thiết bị.

**Không cho SLO từ ST-A tự động xóa mọi session của user theo email** trừ khi có yêu cầu nghiệp vụ và cơ chế revocation khác được thiết kế/ủy quyền riêng. CAS SLO ticket mapping nhắm tới **phiên đã xác thực bằng ticket liên quan**, không phải một API admin global logout.

## 15. Ứng dụng nhiều pod: vì sao in-memory mapping có thể thất bại?

Ví dụ deployment có hai ứng dụng:

~~~text
Browser CAS callback ST-A ---> app-pod-1
                               Mapping(ST-A) = HttpSession object on pod-1

CAS back-channel SLO -------> app-pod-2
                               In-memory mapping on pod-2: UNKNOWN
                               app-pod-1 session vẫn active
~~~

Tài liệu Spring Security minh họa Java CAS Client `SingleSignOutFilter` sử dụng một map tĩnh để tìm HttpSession. Một **static map chỉ nằm trong JVM đó**, không tự đồng bộ với các pod khác. Spring Session chia sẻ session store **chưa đủ** nếu SLO mapping ticket→session vẫn chỉ local.

### Các chiến lược

| Phương án | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Single-node hoặc sticky routing toàn bộ login/SLO | Đơn giản cho lab/small deployment | CAS SLO không mang user cookie, nên sticky LB theo browser cookie **không bảo đảm** đúng node |
| Distributed ticket→sessionId index | Tra đúng session từ mọi pod | Cần custom storage/integration và TTL/revocation consistency |
| Session store phân tán (Spring Session Redis/JDBC) | Mọi pod đọc/invalidate session theo ID | Vẫn cần **map ST→sessionId**, bảo vệ nguồn thông báo |
| Broker/event bridge được kiểm chứng | Có thể tổ chức toàn bộ các SP và session revocation | Không phải CAS Java Client default; phải xác minh contract |
| Short session TTL + live authorization | Giới hạn cửa sổ khi notification thất bại | Không thay immediate SLO nếu policy yêu cầu |

**Kết luận:** Nếu SLO có thể rơi vào pod khác, cần cơ chế mà pod đó dùng ST để **tìm session thật**, không chỉ tin sticky routing.

### Kiến trúc Redis minh họa

~~~text
Login callback trên pod A:
  ticket: ST-X
  finalSessionId: SESSION-9
  -> CAS_SLO:<hash(ST-X)> = SESSION-9   (TTL gắn app session)
  -> optional reverse index SESSION-9 -> {ticket-hashes}
  -> session trong Spring Session Redis

SLO callback trên pod B:
  nhận SessionIndex=ST-X
  -> tính key hash có bảo vệ phù hợp
  -> lookup và atomic consume mapping
  -> sessionRepository.deleteById("SESSION-9")
  -> remove reverse mappings
  -> audit kết quả
~~~

Đây là **mô hình tự thiết kế**, không phải mặc định CAS Java Client hay schema Redis chính thức. Nếu app quản lý Spring Session Redis:
- ST là secret ngắn hạn; tránh dùng raw ST làm Redis key/log hiển thị rộng. Có thể dùng **HMAC-SHA256(ticket, server secret)** làm index key để giảm lộ token qua store/log (cần key management).
- Session ID là credential nhạy cảm; store có ACL, TLS, encryption/retention phù hợp.
- Dùng atomic consume (Lua/transaction/compare-and-delete) chống duplicate callback và mapping races.
- TTL mapping phải **theo session lifecycle**, không theo ST validation TTL (vì ST đã tiêu thụ nhưng session app có thể sống lâu).
- Khi session ID đổi do fixation protection, **update mapping**.
- Khi session hết hạn/logout local, dọn mapping/reverse index.
- Nếu CAS SLO event đến trước mapping được commit, cần xử lý pending revocation/ordering một cách an toàn.
- Nếu Redis outage, **không** tuyên bố SLO hoàn tất khi session chưa bị xóa.

### Không chỉ dùng username làm khóa

`ST-X → session-X` là phép ánh xạ theo **giao dịch xác thực**, còn `username → sessions` là phép tra rộng hơn. Một user có thể có nhiều phiên/tenant/IdP. Nếu buộc dùng user index, cần định danh có phạm vi issuer/tenant/immutable ID và authorization chặt chẽ, tránh logout nhầm. **CAS SessionIndex không yêu cầu app suy username từ XML rồi xóa mọi phiên**.

## 16. Vấn đề bảo mật: CAS SLO callback có phải request đáng tin sẵn không?

**Không.** Dù logout notification là tín hiệu CAS Server phát, ứng dụng vẫn phải phòng trường hợp endpoint nhận một POST giả mạo. CAS Protocol SLO **có thể dùng SAML-shaped XML nhưng không nên mặc định thông điệp đó được ký bằng SAML XML Signature theo full SAML 2.0 SLO Profile**. Đặc biệt, một số CAS Java Client triển khai xử lý ST trong `SessionIndex` mà không có cơ chế xác minh chữ ký thông điệp giống Spring Security SAML provider.

### Threat model điển hình

Kẻ tấn công có thể:
- Gửi `POST logoutRequest=...` tới endpoint public, cố chọn `SessionIndex` của người khác.
- Lợi dụng ticket bị rò trong URL/log để kích hoạt logout session liên quan (**logout DoS**).
- Replay notification nhiều lần để gây load/noise nếu app không idempotent.
- Tấn công XML parser bằng DTD/XXE hoặc payload rất lớn nếu parser không an toàn.
- Đổi request path/Host header để vượt route policy.
- Lợi dụng filter đứng trước CSRF để gửi callback giả tới tất cả session.
- Tận dụng multi-node mapping race để khiến một phiên không bị hủy.

### Biện pháp bảo vệ phù hợp

1. **Giới hạn nguồn SLO back-channel:** chỉ cho CAS Server/cổng proxy đáng tin được gửi tới callback qua network/firewall/mTLS hoặc cơ chế xác thực thông điệp được triển khai hỗ trợ. Chỉ allow IP đơn thuần không phải bảo đảm duy nhất trong mọi mạng/proxy.
2. **Giới hạn endpoint/path:** CAS logout callback phải nằm trên URL được đăng ký và nhận đúng method/format/size; đừng cho browser chọn arbitrary user/session.
3. **Không tin Host/Forwarded headers** ngoài reverse proxy đã cấu hình.
4. **Parse XML an toàn**: không cho XXE/entity expansion, giới hạn kích thước/body và độ sâu.
5. **Lookup theo ST mapping**, không theo NameID/email từ XML.
6. **Atomic consume và idempotency:** notification lặp không hủy nhầm session khác hoặc cấp lại Authentication.
7. **TLS cho CAS Server ↔ app** và kiểm tra hostname/client cert theo kiến trúc.
8. **Audit/metrics không chứa raw ST** hay HttpSession IDs, giữ event correlation/trace được bảo vệ.
9. **Phân quyền callback và CSRF:** back-channel không có browser CSRF token; nếu miễn CSRF thì chỉ đúng endpoint/flow được bảo vệ bằng cơ chế khác, không tắt CSRF toàn ứng dụng.
10. **Fail safely:** khi không xác thực được nguồn thông báo, không hủy phiên theo input tùy ý; khi không tìm được mapping, không xóa theo user text.
11. **Rate limit** không phá delivery CAS nhưng giảm SLO spam.
12. **Không coi front-channel JavaScript/JSONP thành bằng chứng server authentication**, đánh giá CORS/Origin/CSRF và framework support độc lập.

**Quan trọng:** một SLO handler chỉ hủy session nên rủi ro thường là **denial of service/logout CSRF**, nhưng tác động vẫn quan trọng trong giao dịch/ứng dụng nhiều session. Không hạ validation để có “logout luôn hoạt động”.

## 17. Mối quan hệ giữa ST expiry và mapping retention

Một nhầm lẫn phổ biến là: “ST hết hạn sau vài phút, vậy xóa ST→session mapping sau vài phút là đúng”.

Không đúng. **ST credential** chỉ cần sống đủ lâu để được CAS validation **một lần**. Nhưng **ST ID làm correlation key cho SLO** có thể cần được giữ **đến khi phiên ứng dụng liên quan bị hủy**.

Ví dụ:
- 09:00: ST-A cấp và validate thành công, sau đó ST-A không còn hợp lệ để đăng nhập.
- 09:01: `HttpSession-A` còn authenticated.
- 12:00: User logout tại CAS; CAS gửi `SessionIndex=ST-A`.
- 12:00: Nếu app đã xóa mapping vì “ST validation TTL chỉ vài phút”, không thể tìm `HttpSession-A`.

Do đó:
- Mapping retention thường gắn với **HttpSession lifespan** và dọn qua session listener.
- Không cần giữ ST raw làm credential, chỉ index/correlation an toàn.
- Có TTL/quota/cleanup để tránh memory leak nếu session events mất.
- Khi session invalidated/logout local, dọn mapping ngay.
- Đối với session phân tán, lưu mapping thời hạn phù hợp session TTL, không tự đặt bằng TTL ST.

Trong thiết kế nhiều node cần cân bằng chính xác giữa khả năng nhận SLO trễ, session lifetime, cache retention và chính sách dữ liệu nhạy cảm.

## 18. Duplicate SLO, local logout và idempotency

Một phiên đã bị hủy có thể tiếp tục nhận SLO notification do CAS Server retry/proxy. Xử lý đúng:

~~~text
Receive SLO with SessionIndex=ST-A
  -> lookup ST-A
  -> if known: atomically remove mapping, invalidate mapped session
  -> if not found: no-op, record unknown/duplicate without leaking ST
  -> respond according to client protocol and monitoring policy
~~~

Hành vi **idempotent**:
- Một ST→session mapping bị consume chỉ một lần.
- Notification trùng không tạo session mới.
- `HttpSession.invalidate()` có thể ném `IllegalStateException` nếu đã invalidated; handler/libraries cần xử lý như “already invalid” phù hợp.
- Không xóa tất cả session có cùng username vì không tìm thấy ST.
- Nếu service logout local trước khi CAS SLO đến, mapping có thể đã được listener dọn; việc lookup trả empty là bình thường.
- Không để một SLO cũ vô hiệu hóa **phiên mới của người dùng** chỉ vì user đăng nhập lại bằng ST khác.

### Tình huống re-login

~~~text
09:00 ST-OLD -> session-1
09:30 Local logout session-1; mapping ST-OLD removed
09:31 CAS TGC còn, cấp ST-NEW
09:31 ST-NEW -> session-2

CAS SLO message muộn cho ST-OLD:
  Không được hủy session-2 chỉ vì cùng user name.
~~~

Nếu app chỉ giữ một bảng `username→currentSession` và dùng NameID, thông báo muộn cho login cũ có thể logout nhầm phiên mới. Vì vậy **key theo ST** là cốt lõi.

## 19. Java 17 độc lập: mô phỏng ST → phiên và hủy đúng phiên

Chương trình dưới đây **không dùng Spring/CAS Server**, chỉ dùng Java 17 Standard Library. Nó mô phỏng:
- Ghi ánh xạ **ST → phiên ứng dụng**.
- Một phiên có thể được liên kết với nhiều ticket trong trường hợp demo, kèm reverse index.
- Khi SLO mang một ST đã biết, **hủy phiên chính xác** và dọn toàn bộ ticket keys của phiên đó.
- Duplicate/stale SLO chỉ no-op, không ảnh hưởng phiên khác.
- Local logout dọn mapping.
- Không in ticket hoặc session secrets trong một ứng dụng thật; mã demo in ID giả để dễ theo dõi.

Tệp `CasSloSessionMappingDemo.java`:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Set;

public final class CasSloSessionMappingDemo {

    static final class Session {
        final String label;
        boolean active = true;

        Session(String label) {
            this.label = label;
        }

        void invalidate() {
            active = false;
        }
    }

    static final class TicketSessionIndex {
        private final Map<String, Session> byTicket = new HashMap<>();
        private final Map<Session, Set<String>> bySession =
                new IdentityHashMap<>();

        synchronized void record(String ticket, Session session) {
            if (ticket == null || ticket.isBlank() || session == null
                    || !session.active) {
                throw new IllegalArgumentException(
                        "Ticket and active session required");
            }
            Session previous = byTicket.put(ticket, session);
            if (previous != null && previous != session) {
                Set<String> previousTickets = bySession.get(previous);
                if (previousTickets != null) {
                    previousTickets.remove(ticket);
                    if (previousTickets.isEmpty()) {
                        bySession.remove(previous);
                    }
                }
            }
            bySession.computeIfAbsent(session, ignored -> new HashSet<>())
                    .add(ticket);
        }

        synchronized String onCasLogout(String ticket) {
            Session session = byTicket.get(ticket);
            if (session == null) {
                return "NO_MAPPING";
            }
            removeAllMappings(session);
            if (!session.active) {
                return "ALREADY_INACTIVE";
            }
            session.invalidate();
            return "INVALIDATED:" + session.label;
        }

        synchronized void onLocalSessionDestroyed(Session session) {
            removeAllMappings(session);
            session.invalidate();
        }

        private void removeAllMappings(Session session) {
            Set<String> ticketKeys = bySession.remove(session);
            if (ticketKeys != null) {
                for (String key : ticketKeys) {
                    byTicket.remove(key);
                }
            }
        }

        synchronized int mappingCount() {
            return byTicket.size();
        }
    }

    public static void main(String[] args) {
        TicketSessionIndex index = new TicketSessionIndex();
        Session a = new Session("session-A");
        Session b = new Session("session-B");
        Session c = new Session("session-C");

        index.record("ST-A1", a);
        index.record("ST-A2", a);
        index.record("ST-B1", b);
        index.record("ST-C1", c);

        System.out.println("Before: " + index.mappingCount());
        System.out.println("CAS ST-A1: "
                + index.onCasLogout("ST-A1"));
        System.out.println("CAS ST-A2 later: "
                + index.onCasLogout("ST-A2"));
        System.out.println("A active: " + a.active);
        System.out.println("B active: " + b.active);
        System.out.println("Mappings now: " + index.mappingCount());

        index.onLocalSessionDestroyed(c);
        System.out.println("Local logout C active: " + c.active);
        System.out.println("CAS ST-C1 later: "
                + index.onCasLogout("ST-C1"));

        System.out.println("CAS ST-B1: "
                + index.onCasLogout("ST-B1"));
        System.out.println("Mappings final: " + index.mappingCount());
    }
}
~~~

Biên dịch/chạy trên Java 17+:

~~~bash
javac CasSloSessionMappingDemo.java
java CasSloSessionMappingDemo
~~~

Stdout **chính xác**:

~~~text
Before: 4
CAS ST-A1: INVALIDATED:session-A
CAS ST-A2 later: NO_MAPPING
A active: false
B active: true
Mappings now: 2
Local logout C active: false
CAS ST-C1 later: NO_MAPPING
CAS ST-B1: INVALIDATED:session-B
Mappings final: 0
~~~

### Giải thích kết quả

1. Bốn ticket keys được ánh xạ đến ba phiên.
2. CAS SLO cho `ST-A1` tìm session A, invalidates A và dọn cả ST-A1/ST-A2.
3. SLO trễ cho ST-A2 không tìm mapping; session B không bị ảnh hưởng.
4. Local logout C invalidates session C và dọn ST-C1; SLO tới sau là no-op.
5. CAS SLO ST-B1 hủy đúng session B.
6. Sau cùng không còn mapping.

**Đây không phải CAS Client production:**
- ST IDs trong demo dễ đoán; CAS thật cần ticket có entropy cao.
- `HashMap/IdentityHashMap` chỉ có hiệu lực trong một JVM, không xử lý cluster.
- `Session` là object mô phỏng, không phải `jakarta.servlet.http.HttpSession`.
- Không có HTTPS, SLO callback authentication, XML parser hoặc ticket validation.
- Việc cho một session gắn nhiều ST là **policy demo**. Java CAS Client mặc định trong nhiều phiên bản có thể thay mapping khi cùng session nhận ticket mới; phải kiểm tra semantics thực tế trước khi áp logic này.
- Không dùng đầu vào tự khai từ browser để gọi `onCasLogout(ticket)` trong server thật.
- Trong production cần validate nguồn notification, bảo vệ index, atomicity giữa SLO/mapping/session store, cleanup và audit.

## 20. Kiểm thử đúng thời điểm: sau CAS login chứ không chỉ trước login

Một test chỉ kiểm tra `ticket→session ID` có record lúc callback **chưa đủ**. Bắt buộc chứng minh **session đang giữ Spring Security Authentication** là session bị hủy.

### Test A — login rồi CAS SLO

1. Đăng nhập CAS bằng tài khoản test, bắt ST ban đầu trong trace đã redact.
2. CAS validation trả success, Spring tạo authenticated session.
3. Kiểm tra route bảo vệ cho phép request với browser cookie.
4. Tại CAS Server test, gọi logout, phát notification cho service.
5. Kiểm tra app xử lý CAS SLO và invalidate đúng session đã tạo.
6. Gửi request tiếp theo với cookie cũ: không còn Authentication, thường bị redirect lại CAS login theo entry point.
7. Không khẳng định cả ba devices/ứng dụng đều logout nếu CAS chưa xác nhận delivery.

### Test B — CAS back-channel không cookie

1. CAS Server test gửi POST `logoutRequest` **không mang browser JSESSIONID**.
2. App phải tìm session từ ST mapping.
3. Không dùng `request.getSession(true)` của callback làm session cần hủy.
4. Sau xử lý, session browser cũ không còn authenticated.

### Test C — SessionIndex không phải HttpSession ID

1. Nhận SLO với `SessionIndex=ST-A`.
2. App lookup ST-A trong mapping và tìm session S.
3. Xác nhận **không** tìm servlet session bằng chuỗi `ST-A` trực tiếp.
4. Không dùng `NameID` làm đường tắt thay mapping khi đã mất ST.

### Test D — local logout trước CAS SLO

1. Đăng nhập, ghi mapping.
2. App local logout invalidates HttpSession.
3. Listener/remove mapping thực hiện cleanup.
4. CAS Server sau đó gửi logout cho ST cũ.
5. App xử lý no-op an toàn, không tạo session mới và không hủy phiên khác.

### Test E — duplicate SLO

1. CAS Server/test harness gửi cùng notification hai lần có kiểm soát.
2. Lần đầu invalidates đúng session.
3. Lần hai no-op, không ném lỗi 500 hoặc hủy session mới không liên quan.
4. Metrics phân biệt already processed và genuine failure nếu có bằng chứng.

### Test F — app nhiều node

1. CAS login callback đi **pod A**.
2. SLO callback đi **pod B**.
3. Nếu mapping in-memory, test có thể bộc lộ miss; không kết luận SLO đúng từ CAS 200.
4. Với distributed mapping + Spring Session, pod B tra ST→sessionId và delete đúng session.
5. Cookie cũ không còn truy cập được trên cả A/B.
6. Test khi pod A restart giữa login/SLO.

### Test G — session fixation

1. Ghi session ID trước CAS authentication.
2. Login thành công qua Spring Security.
3. Ghi session ID **sau** session fixation protection (không log raw ngoài test).
4. Gửi CAS SLO chứa original ST.
5. Phải hủy **phiên sau login** chứa Authentication.
6. Không sửa bằng cách tắt session fixation protection.

### Test H — một phiên có nhiều ticket/reauthentication

1. Cho user reauthenticate hoặc login lại trong browser same session nếu flow hỗ trợ.
2. Kiểm tra client thay mapping cũ hay duy trì nhiều ticket keys.
3. SLO cho ticket phù hợp phải hủy session theo contract.
4. Mapping cũ không được hủy nhầm một phiên mới khác principal.
5. Test chính sách khi CAS TGT cũ bị logout sau khi app có ST mới.

## 21. Kiểm thử bảo mật callback

| Test | Kỳ vọng |
| --- | --- |
| POST logoutRequest từ nguồn không tin | Bị hạn chế/từ chối theo architecture, không xóa session tùy ý |
| SessionIndex là ticket chưa biết | No-op + metrics, không tạo session mới |
| SessionIndex là raw JSESSIONID giả | Không lookup session trực tiếp bằng đó |
| NameID trùng username khác tenant | Không hủy tất cả sessions theo NameID |
| Message XML có DTD/XXE | Không parse external entity, từ chối payload |
| XML quá lớn/deep nesting | Có kích thước/thời gian xử lý giới hạn |
| SLO notification gửi hai lần | Idempotent no-op ở lần sau |
| SLO message đến sau local logout | Không làm thay đổi authenticated session mới |
| Ticket bị lộ trong proxy logs | Redact + investigate, không xem ST là không nhạy cảm |
| CAS SLO qua HTTP không bảo vệ | Không cho phép trong production trust design |
| SLO POST không có CSRF token | Chỉ callback chuyên biệt được bảo vệ bằng nguồn/transport thích hợp |
| User POST logoutRequest qua browser | Không được tùy tiện vô hiệu hóa session người khác |
| Session mapping Redis bị sửa | Bảo vệ ACL/integrity, không tin mapping từ client |
| Session fixation ID thay đổi | Mapping phải trỏ tới phiên authenticated hiện tại |
| App session còn nhưng CAS TGT hết | CAS SLO phải hoạt động nếu yêu cầu; live authorization vẫn độc lập |
| Unauthorized/403 từ business endpoint | Không tự coi là CAS SLO validation failure |

Các negative tests chỉ chạy trong **lab/CAS test service** được phép, không gửi logout forged messages tới người dùng thật.

## 22. Phân biệt lỗi giao thức với lỗi session lookup

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| CAS SSO logout xong nhưng app vẫn authenticated | SLO notification delivery, filter mapping, lookup/session invalidation |
| Không thấy POST logoutRequest tại app | CAS registered service `logoutType/logoutUrl`, network/firewall |
| CAS trả HTTP 200 mà session không bị hủy | Filter có thực sự parse request/tìm đúng ST mapping không? |
| Filter thấy message nhưng mapping missing | Mapping đã expire, ở pod khác, session ID thay đổi, login callback bị bỏ sót |
| Có ticket trong query login nhưng không có mapping | SLO filter order, artifactParameterName, filter path, session creation |
| Mapping trỏ tới old session | Session fixation strategy, migration, duplicate session |
| Local logout rồi SLO gây lỗi 500 | Duplicate handling, listener cleanup, already invalidated session |
| Nhiều pod khác nhau có hành vi khác | In-memory map, redis/session store, replica configuration |
| SLO POST bị 403 CSRF | SLO filter order/callback endpoint; không tắt CSRF toàn site |
| Front-channel hoạt động trong browser A nhưng không B | Client support, SameSite/cookie/iframe/JS restrictions |
| Người dùng logout app rồi tự SSO trở lại | CAS TGT/TGC vẫn còn; local logout ≠ CAS logout |
| Một ứng dụng khác vẫn đăng nhập | SLO delivery best-effort, service chưa hỗ trợ, session scope khác |
| Không biết ST còn dùng được không | ST đã consume khi login, mapping ID dùng cho logout, không retry validation |
| JWT/API token còn hiệu lực sau CAS SLO | Token lifecycle riêng; cần revocation nếu yêu cầu |
| CAS XML giống SAML LogoutRequest nhưng Spring SAML filter từ chối | Đang nhầm CAS Protocol SLO với SAML 2.0 SLO |

### Vấn đề phân biệt SessionIndex

Trong CAS SLO:
- `SessionIndex` là một **service-ticket based correlation key**.
- `HttpSession</BT> là đối tượng local application.
- `CAS TGT</BT> là global SSO session server-side.
- `Cookie TGC</BT> tồn tại trên domain CAS.
- `JSESSIONID</BT> là cookie ứng dụng, không đi theo CAS back-channel POST.

Một bảng ánh xạ được quản lý đúng nối **ST** với **session ứng dụng**, không tự đồng nhất năm thứ trên.

## 23. Spring Security CAS client và logout chủ động tại ứng dụng

Một ứng dụng thường có hai thao tác:

**A. Local logout**:
- Spring Security `LogoutFilter/SecurityContextLogoutHandler` xóa local SecurityContext/session.
- Listener cleanup ST mapping.
- CAS TGT/TGC có thể vẫn còn.
- Khi user truy cập lại, CAS có thể cấp ST mới, SSO tiếp.

**B. Global CAS logout flow**:
- Ứng dụng có thể local logout trước, rồi redirect browser sang CAS `/logout`.
- CAS hủy phiên tập trung và gửi SLO notifications tới các CAS services liên quan nếu đã bật.
- Mỗi ứng dụng nhận SLO phải dùng ST mapping của mình để invalidate local sessions phù hợp.
- App khác có thể không nhận/không xử lý SLO; không có bảo đảm mọi node/device/token bị thu hồi.

Spring Security CAS reference đề cập việc logout local trước khi phát yêu cầu CAS global logout; lý do là client local session phải được dọn rõ ràng chứ không phụ thuộc toàn bộ propagation bên ngoài.

**Đừng lẫn CAS `/logout` với SAML2 `/logout/saml2/slo`** trong Spring Security. SAML2 provider dùng `LogoutRequest/Response` theo giao thức riêng, keys và trust metadata; CAS SLO trong bài dùng CAS Java client/session mapping.

## 24. Tài liệu vận hành: kiểm tra một end-to-end CAS SLO

Một báo cáo runbook có thể có:

~~~text
CAS SLO test — portal
Protocol: CAS (not direct SAML2)
Service alias: portal-public-callback
Login ticket: [REDACTED]
CAS notification SessionIndex: [REDACTED]
CAS logoutType: BACK_CHANNEL
CAS logout target: configured registered-service SLO URL
Client SLO filter: registered and ordered before auth/CSRF flow
Mapping storage: in-memory / distributed (explicit)
Original authenticated session: found
Session invalidation result: completed
Mapping cleanup result: completed
Subsequent browser request: unauthenticated
Other apps: unknown unless separately verified
~~~

Không lưu raw CAS ST, session cookie, principal email hoặc full LogoutRequest trong ticket hỗ trợ. Chỉ ghi **ticket hash/correlation ID đã bảo vệ**, service alias, node và outcome. Nếu không tìm được mapping, ghi **MAPPING_MISS**, không tự nói “CAS thất bại”.

Các metrics tham khảo:
- `cas_slo_notification_received_total`
- `cas_slo_session_mapping_hit_total`
- `cas_slo_session_mapping_miss_total`
- `cas_slo_session_invalidated_total`
- `cas_slo_session_already_expired_total`
- `cas_slo_delivery_failure_total` ở phía CAS Server nếu có
- Latency CAS logout → app invalidation

Metrics labels chỉ nên dùng `serviceAlias, result, node, channel` với cardinality có kiểm soát, **không** dùng raw ST/sessionId/username.

## 25. Những sai lầm phổ biến

1. **“CAS hủy TGT nghĩa là app session tự biến mất.”** Sai, app cần nhận notification và invalidates local session.
2. **“Back-channel POST có cookie của user.”** Không mặc định, vì request do CAS Server phát.
3. **“SessionIndex trong CAS SLO là JSESSIONID.”** Sai, trong CAS Protocol nó được dùng như service ticket ID.
4. **“Map ST sau khi validate là vô ích vì ST đã dùng.”** Sai, ST ID vẫn dùng để tương quan logout.
5. **“ST mapping chứng minh người dùng authenticated.”** Sai, mapping có thể được ghi trước validation.
6. **“SAML-shaped LogoutRequest đồng nghĩa full SAML2 SLO.”** Sai, CAS Protocol SLO có contract riêng.
7. **“Chỉ cần CasAuthenticationFilter thì có SLO.”** Sai, cần SLO filter/client integration.
8. **“SingleSignOutFilter ở pod A tự biết session ở pod B.”** Sai với in-memory mapping.
9. **“Sticky routing theo browser cookie luôn giải quyết CAS back-channel.”** Sai, back-channel có thể không có browser cookie.
10. **“HttpSessionListener không cần.”** Có thể gây stale mapping và leak khi session expire/logout.
11. **“Chỉ nhìn một HTTP 200 từ CAS/app đủ biết logout xong.”** Sai, phải kiểm tra session invalidation thực.
12. **“Nếu mapping miss thì xóa mọi session cùng username.”** Rủi ro logout nhầm và DoS.
13. **“SLO callback là public POST nên có thể tin mọi XML gửi tới.”** Sai, cần bảo vệ source/transport và parse an toàn.
14. **“SLO callback không có CSRF token thì tắt CSRF cả site.”** Không đúng; hạn chế ngoại lệ và bảo vệ bằng cơ chế khác.
15. **“TTL mapping bằng ST validation TTL.”** Sai, mapping phải tồn tại theo session cần nhận logout.
16. **“Một ST có thể giữ làm bearer credential để app tái đăng nhập.”** Sai, ST là one-time credential.
17. **“Local logout rồi ST cũ còn mapping không sao.”** Sai, stale mapping có thể gây memory leak hoặc hủy nhầm session mới.
18. **“Chỉ một JSESSIONID trên tất cả thiết bị.”** Sai, mỗi browser/device có thể có session riêng.
19. **“Spring Session Redis tự đồng bộ CAS mapping in-memory.”** Không, cần map ST→session ID phân tán riêng nếu SLO nhận ở pod khác.
20. **“Mọi SLO success đồng nghĩa đã thu hồi JWT/refresh token/WebSocket.”** Không mặc định.
21. **“Đổi session ID sau login thì mapping vẫn luôn đúng.”** Phụ thuộc fixation strategy/client map, phải kiểm thử.
22. **“Notification gửi trễ theo ST cũ được phép hủy session đăng nhập mới cùng user.”** Không đúng nếu session mới không còn thuộc ST cũ.

## 26. Bài tập và đáp án

**Bài 1.** CAS gửi `SessionIndex=ST-ABC` đến app, không có cookie JSESSIONID. Làm sao tìm session?

**Đáp án:** lookup trong `SessionMappingStorage` theo **ST-ABC**, nhận HttpSession/sessionId đã ghi lúc login, rồi invalidate session đó.

**Bài 2.** `SingleSignOutFilter` đứng sau Spring Security CSRF filter và SLO POST bị 403. Kết quả?

**Đáp án:** SLO handler có thể không chạy, session vẫn active. Điều chỉnh filter order và SLO callback security scope đúng, không tắt CSRF cho mọi route.

**Bài 3.** Ticket ST đã được CAS serviceValidate consume. Vì sao vẫn giữ mapping đến lúc session hết hạn?

**Đáp án:** ST ID trở thành correlation key cho CAS SLO; **không phải credential có thể đăng nhập lại**.

**Bài 4.** Khi CAS logout cho ST-A mà lookup không thấy mapping, app có nên xóa mọi session của `NameID=alice` không?

**Đáp án:** không. Mapping miss có thể do session đã hết, pod khác, cleanup hoặc lỗi. Xóa theo username không có phạm vi tin cậy rõ sẽ làm logout nhầm.

**Bài 5.** CAS SLO POST đi app-pod-2 nhưng ticket mapping chỉ nằm RAM app-pod-1. Có bảo đảm SLO không?

**Đáp án:** không. Cần phân tán mapping ST→sessionId và dùng session store có thể revoke từ node nhận callback, hoặc một kiến trúc propagation có kiểm chứng.

**Bài 6.** Spring Session Redis đã chia sẻ HttpSession, vậy có tự làm CAS ST mapping phân tán không?

**Đáp án:** không. Nếu mapping do Java CAS Client `HashMapBackedSessionMappingStorage` quản lý trong JVM, nó vẫn local.

**Bài 7.** Tại sao `SingleSignOutHttpSessionListener` quan trọng?

**Đáp án:** dọn mapping khi session destroyed/expired, tránh stale ST mapping và memory leak.

**Bài 8.** SLO notification đến hai lần, lần đầu đã invalidate session. Lần thứ hai nên làm gì?

**Đáp án:** idempotent no-op khi mapping không còn; không tạo session mới, không xóa session user khác.

**Bài 9.** SLO message dùng tag `samlp:LogoutRequest`. Có thể chuyển nó thẳng sang `Saml2LogoutRequestFilter` của Spring không?

**Đáp án:** không. CAS Protocol SLO có mapping ST riêng và không đồng nghĩa full SAML 2.0 SLO profile.

**Bài 10.** Browser logout ở app nhưng CAS TGC vẫn còn. User vào app lại và có ST mới. Đây là lỗi?

**Đáp án:** có thể bình thường với **local logout**; CAS SSO session chưa bị hủy. Muốn global logout cần CAS /logout và SLO policy phù hợp.

**Bài 11.** `SingleSignOutFilter` ghi mapping ngay khi thấy ticket query. Mapping tồn tại có chứng minh CAS validation success không?

**Đáp án:** không. Filter có thể record trước CasAuthenticationProvider/TicketValidator. Chỉ kết quả CAS validation thành công được phép tạo Authentication.

**Bài 12.** Khi session fixation strategy thay HttpSession ID sau login, phải test gì?

**Đáp án:** đảm bảo SLO theo ST hủy được session **sau login** đang giữ SecurityContext; không tắt fixation protection để né lỗi.

**Bài 13.** Vì sao cần bảo vệ endpoint back-channel SLO khỏi request giả?

**Đáp án:** kẻ xấu có thể gửi forged logoutRequest để ép hủy phiên nếu biết/đoán được ST; có rủi ro logout CSRF/DoS. Dùng transport/source validation và kiểm soát callback.

**Bài 14.** Nếu ticket ST-A được cấp cho session A, sau local logout user có session B từ ST-B, CAS gửi notification cũ cho ST-A. Có nên hủy B?

**Đáp án:** không. Mapping ST-A phải được cleanup khi A kết thúc; notification cũ không được hủy session B khác ST.

**Bài 15.** CAS logout trả HTTP 200 và CAS gửi notification, nhưng browser với cookie SP cũ vẫn được truy cập. Kiểm tra gì?

**Đáp án:** SLO delivery tới app, endpoint/filter order, mapping hit, session fixation, session store/multi-node và thực tế session invalidation.

**Bài 16.** Với SLO back-channel, tại sao `request.getSession(true).invalidate()` không đủ?

**Đáp án:** request từ CAS Server không mang browser cookie user, nên nó có thể tạo/hủy session của request callback, **không phải user session** cần logout.

**Bài 17.** Mapping ticket→session cần TTL bao lâu?

**Đáp án:** thường gắn với vòng đời **ứng dụng HttpSession** và cleanup; không chỉ theo ST validation TTL vài phút. Cần chính sách retention và session expiry đồng bộ.

**Bài 18.** Front-channel CAS SLO phụ thuộc yếu tố gì ngoài mapping?

**Đáp án:** Java CAS client có hỗ trợ front-channel không, browser GET/JSONP/iframe flow, SameSite/cookie/third-party restrictions và delivery; không có bảo đảm browser hoàn tất.

## 27. Checklist triển khai và QA

- [ ] Đã xác định đây là **CAS Protocol SLO**, không nhầm SAML2 Single Logout.
- [ ] CAS Server service registry bật SLO phù hợp, `logoutType` và `logoutUrl` được xác minh.
- [ ] CAS login callback có ST đã được CAS Server validate với đúng service URL.
- [ ] `SingleSignOutFilter` quan sát request login mang ST và nhận notification CAS logout.
- [ ] SLO filter xử lý đúng request **trước** các filter có thể chặn callback.
- [ ] Không đăng ký filter trùng trong Servlet và Spring Security chain.
- [ ] `SingleSignOutHttpSessionListener` được đăng ký để dọn session mapping.
- [ ] ST→session mapping gắn với **phiên authenticated cuối cùng**, kể cả sau session fixation.
- [ ] `SessionIndex` trong CAS SLO được lookup theo **ST**, không theo JSESSIONID/NameID.
- [ ] CAS SLO back-channel hoạt động **không cần browser cookie**.
- [ ] Nếu nhiều node, ticket mapping và session deletion truy cập được qua các node.
- [ ] Local logout/session expire dọn mapping; duplicate SLO idempotent.
- [ ] Mapping retention phù hợp session lifetime, không cắt sau ST validation TTL.
- [ ] Endpoint SLO được bảo vệ nguồn/transport, hạn chế method/size/format, XML parser an toàn.
- [ ] Không có public API lookup ticket/SessionIndex tiết lộ session tồn tại.
- [ ] Không log raw ST, CAS TGT/TGC, JSESSIONID, cookie, full LogoutRequest hoặc principal nhạy cảm.
- [ ] App authorization và API tokens/WebSocket có revocation riêng khi nghiệp vụ yêu cầu.
- [ ] Test login→SLO, local logout trước SLO, duplicate, session fixation, many tabs, many nodes.
- [ ] Test back-channel POST, front-channel nếu dùng, CAS Server outage và mapping miss.
- [ ] Đã có metrics/trace cho notification nhận, mapping hit/miss, session invalidation, retry/outage.
- [ ] Không tuyên bố “đã logout mọi thiết bị/ứng dụng” khi chỉ mới hủy một phiên SP.

## 28. Ghi nhớ

**CAS Server quản lý phiên đăng nhập tập trung; ứng dụng Spring quản lý HttpSession của mình.** Khi CAS muốn Single Logout một phiên ứng dụng, nó gửi **Service Ticket ID** tương ứng trong `SessionIndex` của notification. CAS client cần **ánh xạ ST → HttpSession**, tra mapping khi nhận logout, invalidate **đúng phiên**, rồi dọn mapping.

Công thức ngắn:

~~~text
ĐĂNG NHẬP:
  CAS cấp ST
  -> ứng dụng nhận ST và CAS TicketValidator xác minh
  -> ST được liên hệ với HttpSession đã xác thực

CAS SINGLE LOGOUT:
  CAS hủy SSO session
  -> gửi logoutRequest (SessionIndex=ST)
  -> CAS client tra ST→HttpSession
  -> HttpSession.invalidate()
  -> xóa mapping và từ chối dùng phiên cũ

ĐIỀU KIỆN:
  CAS SLO notification phải được tiếp nhận an toàn;
  mapping phải tồn tại ở node xử lý;
  phiên được hủy phải là phiên đang chứa Authentication.
~~~

**Không đồng nhất ST với JSESSIONID, không dựa vào NameID để xóa mọi phiên, không coi ST mapping là authentication và không bỏ bảo vệ nguồn SLO notification.**

### Tài liệu chính thức

1. Apereo CAS 8.x — *Logout & Single Logout*, back-channel, front-channel, SessionIndex là Service Ticket, `logoutType/logoutUrl`: https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html
2. Apereo CAS — *CAS Protocol 2.0 Specification*, Single Logout section và logout XML Appendix C: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
3. Apereo Java CAS Client — *README: Configuring Single Sign Out*, filter, listener, artifactParameterName, logoutRequest: https://github.com/apereo/java-cas-client/blob/master/README.md
4. Spring Security — *CAS Authentication: Single Logout*, SingleSignOutFilter, local logout vs CAS logout, session mapping: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
5. Spring Session — *API/SessionRepository*, distributed session management: https://docs.spring.io/spring-session/reference/api.html
6. Spring Security — *Session Management*, session fixation and HttpSession security: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
7. Apereo CAS 7.3.x — *Logout & Single Logout*, per-service SLO config: https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html
8. Spring Boot — *FilterRegistrationBean / ServletListenerRegistrationBean* API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
