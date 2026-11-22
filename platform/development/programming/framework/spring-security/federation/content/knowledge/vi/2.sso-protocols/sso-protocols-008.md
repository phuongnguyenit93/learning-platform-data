# Giới hạn dùng assertion hoặc ticket đăng nhập để gọi API

**Kết luận cần nắm:** assertion hoặc ticket trong Single Sign-On (SSO) thường chứng minh rằng một người dùng đã được xác thực **cho một dịch vụ và một luồng đăng nhập xác định**. Chúng **không tự động cấp quyền truy cập API khác**. Đưa nguyên SAML assertion, CAS service ticket, Kerberos ticket hay OIDC ID token vào `Authorization: Bearer` không biến chúng thành OAuth 2.0 access token.

Khi tích hợp Spring Security, cần phân tách rõ: **đăng nhập vào ứng dụng (authentication)**, **ủy quyền để gọi API (authorization)** và **phiên của ứng dụng (session)**. Việc một người đã đăng nhập tại IdP/SSO mới chỉ là một phần của chuỗi kiểm tra bảo mật.

## 1. Assertion, ticket và access token khác nhau ở đâu?

Trong hệ thống liên kết danh tính, các bên thường gồm:

- **Identity Provider (IdP) / hệ thống SSO:** xác thực người dùng và phát hành bằng chứng theo giao thức.
- **Relying Party (RP) / Service Provider (SP):** ứng dụng nhận và kiểm chứng bằng chứng để đăng nhập người dùng, sau đó có thể tạo session riêng.
- **Client gọi API:** thành phần gửi HTTP request đến API; có thể là trình duyệt, ứng dụng mobile hoặc backend.
- **Resource Server / API:** nơi kiểm tra credential được chấp nhận và phân quyền truy cập tài nguyên.
- **Authorization Server:** bên cấp OAuth 2.0 access token theo grant/policy, có thể tích hợp với IdP nhưng không nhất thiết trùng vai trò.

Trước khi chuyển một credential sang API, phải hỏi:

1. **Bằng chứng này được phát hành cho ai?** Ví dụ SAML `AudienceRestriction`, CAS `service`, Kerberos service principal, JWT `aud`.
2. **Bằng chứng được sử dụng để làm gì?** Đăng nhập web, chứng minh danh tính client, xin token ở token endpoint, hay truy cập tài nguyên?
3. **Có thể sử dụng bao nhiêu lần, trong bao lâu?** CAS ST một lần thử validation; SAML assertion có điều kiện thời gian và chống replay; access token có thời hạn riêng.
4. **API biết kiểm chứng bằng cách nào?** Chữ ký và metadata SAML, CAS validation, Kerberos/SPNEGO, JWT signature/claims hoặc OAuth introspection.
5. **Quyền truy cập cụ thể là gì?** Cần scope/permission, tenant, quyền sở hữu đối tượng và chính sách nghiệp vụ; việc xác thực danh tính thành công chưa đủ.

### Bảng phân loại

| Credential | Dùng đúng mục đích | Tại sao không thể tùy tiện gọi API khác? |
| --- | --- | --- |
| **SAML 2.0 assertion / SAMLResponse Web Browser SSO** | SP xác minh sự kiện đăng nhập từ IdP | Có audience/recipient và các điều kiện của SP, ACS, request; không mặc nhiên thể hiện API scope |
| **CAS Service Ticket (ST)** | Một service nhận ticket và gọi CAS kiểm tra một lần | Giới hạn đúng `service`; CAS quy định một lần thử validation dù thành công hay thất bại |
| **CAS TGT / TGC** | Duy trì phiên SSO với CAS | Đây là thông tin phiên tại CAS, không phải bearer credential để chia cho API |
| **CAS Proxy Ticket (PT)** | Proxy truy cập một `targetService` qua luồng CAS proxy đã thiết kế | Chỉ dành cho target service, không phải token dùng mọi nơi |
| **Kerberos service ticket** | Xác thực với service principal cụ thể qua giao thức Kerberos | API phải là dịch vụ đích và chấp nhận Kerberos/SPNEGO theo đúng protocol |
| **OIDC ID token** | RP/client xác minh người dùng đã được IdP xác thực | Audience thường là client ID, không phải resource server; không thay access token |
| **OAuth 2.0 access token** | API chấp nhận ủy quyền truy cập tài nguyên theo audience/resource và scope | Cũng có giới hạn issuer, audience, expiry, scope và token profile |
| **Session cookie của web app** | Trình duyệt duy trì phiên với chính web app | API độc lập không tự xác nhận được phiên; cookie có thêm rủi ro CSRF |

**Chú ý thuật ngữ:** CAS và Kerberos đều nói đến “ticket” nhưng khác giao thức. CAS Ticket-Granting Ticket (TGT) liên quan SSO của CAS; Kerberos Ticket-Granting Ticket cũng viết TGT nhưng phục vụ việc xin Kerberos service tickets. Không suy ra các ticket dùng thay nhau được.

## 2. Bốn giới hạn quan trọng khi đem credential đăng nhập đi gọi API

### 2.1. Ràng buộc bên nhận (audience / recipient / service)

Một SAML assertion được IdP phát hành cho SP `urn:corp:portal` không tự có hiệu lực đối với `orders-api`. CAS ST phát hành cho `service=https://portal.example.test/callback` không phải vé cho `https://api.example.test/orders`. Kerberos ticket cho dịch vụ HTTP của Portal cũng không đương nhiên dùng được với API có service principal khác.

Nếu API bỏ qua ràng buộc này, token/ticket của dịch vụ A có thể bị chuyển sang B, gây **token substitution** hoặc **confused deputy**. Cùng một tổ chức, cùng IdP hay cùng `sub`/email vẫn không thay thế được kiểm tra đúng audience.

### 2.2. Phạm vi và ngữ nghĩa ủy quyền (scope)

Assertion đăng nhập có thể chứa NameID, email, nhóm, thời điểm MFA. Các dữ liệu này không tự có nghĩa người dùng được gọi `POST /api/payments/approve`. Cần xác định ai cấp quyền, quyền áp dụng tới API nào, đã hết hiệu lực chưa, và có cho phép đối với bản ghi/tenant cụ thể không.

OAuth access token thường thể hiện phạm vi bằng `scope` hoặc quyền theo quy ước của authorization server. Dù scope hợp lệ, API vẫn phải kiểm tra **object-level authorization**: ví dụ người dùng chỉ được đọc đơn hàng thuộc tenant của mình.

### 2.3. Giới hạn thời gian và chống phát lại

- **SAML Web SSO:** assertion/response chịu các điều kiện `NotBefore`, `NotOnOrAfter`, `Recipient`, `InResponseTo` khi áp dụng, cùng kiểm tra chữ ký, request binding và replay.
- **CAS ST:** theo đặc tả chỉ hợp lệ cho **một lần thử validation**; lần xác thực thành công không có nghĩa có thể dùng lại ST để gọi hàng trăm API request.
- **Kerberos:** dịch vụ phải kiểm chứng ticket và authenticator theo giao thức, bao gồm cơ chế chống replay; không coi vé Kerberos là chuỗi bearer dùng lặp tùy ý.
- **OAuth access token:** thường được dùng cho nhiều request trong thời gian hiệu lực, nhưng cũng cần bảo vệ vì người giữ bearer token có thể sử dụng nếu không có cơ chế ràng buộc người gửi khác.

Vì vậy không có quy tắc chung rằng “SSO ticket dùng được tới lúc hết hạn”; ngữ nghĩa **sử dụng một lần**, **gắn với service** và **có thể tái dùng** khác nhau tùy loại.

### 2.4. Cách kiểm chứng và định dạng

Một API Spring Security dùng **JWT Resource Server** kiểm tra bearer token theo cấu hình JWT. SAMLResponse là thông điệp SAML/XML, CAS ST thường là chuỗi opaque, Kerberos thực hiện trao đổi ticket/authenticator. Chúng không thành JWT access token chỉ vì xuất hiện sau header `Authorization: Bearer`.

OIDC ID token có thể có cấu trúc JWT hợp lệ, nhưng tính hợp lệ cú pháp và chữ ký **không chứng minh** đây là *access token dành cho API*. API phải kiểm tra token purpose/profile, issuer, audience, hiệu lực và quyền theo hợp đồng bảo mật của mình.

## 3. SAML Web Browser SSO: assertion dùng tại SP, không phải access token chung

Mô hình SAML 2.0 Web Browser SSO điển hình:

~~~text
Người dùng -> IdP xác thực
                |
                v
       Trình duyệt nhận SAMLResponse
                |
                v
       SP / Assertion Consumer Service (ACS)
                |
         Kiểm chứng SAML hợp lệ
                |
                v
            Phiên web SP
                |
                v
          SP cần gọi Orders API
~~~

Ở bước ACS, SP phải kiểm tra các thành phần liên quan theo profile và binding đang sử dụng:

| Thuộc tính/kiểm tra | Ý nghĩa |
| --- | --- |
| `Issuer` và khóa/chứng thư đáng tin | Bằng chứng phát hành từ IdP được cấu hình |
| Chữ ký của response/assertion theo profile | Bảo đảm tính toàn vẹn và nguồn phát hành |
| `AudienceRestriction` | Assertion gửi cho RP/SP dự kiến |
| `SubjectConfirmationData.Recipient` | Bên nhận phù hợp, thường là ACS endpoint |
| `InResponseTo` | Gắn kết với yêu cầu đăng nhập khi có yêu cầu tương ứng |
| `NotBefore`, `NotOnOrAfter` | Hiệu lực trong khoảng thời gian cho phép |
| Đối chiếu request ID, replay, session | Không chấp nhận thông điệp cũ hoặc không tương ứng luồng hiện hành |

Sau khi xác thực, SP có thể tạo web session. Nhưng Orders API **không tự trở thành ACS hoặc audience hợp lệ** của assertion đó. Gửi nguyên `SAMLResponse` sang `/api/orders` có thể bị từ chối; nếu cố buộc API chấp nhận mà không có thiết kế nhận riêng sẽ tạo khoảng trống bảo mật.

### SAML assertion có thể làm đầu vào để xin OAuth access token

Cần phân biệt **token exchange tại authorization server** với **dùng assertion để gọi resource server**:

- **RFC 7522** định nghĩa SAML 2.0 bearer assertion trong OAuth 2.0 như một authorization grant và/hoặc cơ chế client authentication ở **token endpoint**. Authorization server kiểm chứng assertion rồi quyết định có cấp access token hay không.
- **RFC 8693** định nghĩa OAuth 2.0 Token Exchange: client có thể trình `subject_token`, thông tin loại token, audience/resource và scope mong muốn; authorization server áp dụng chính sách để cấp security token phù hợp với dịch vụ đích.

Hai flow này **chỉ hoạt động khi authorization server có hỗ trợ và đã thiết lập trust/policy**. Spring Security `saml2Login` không tự tạo OAuth access token từ mọi SAML assertion. Access token được cấp mới mới là thứ API có thể nhận theo cơ chế Resource Server tương ứng.

**Câu chốt:** SAML assertion là bằng chứng đăng nhập có thể được *chuyển đổi qua luồng có kiểm soát*, không phải credential API phổ quát.

## 4. CAS: service ticket chỉ dành cho service và một lần kiểm chứng

Trong CAS SSO:

1. Người dùng được xác thực tại CAS, có thể có CAS SSO session.
2. CAS chuyển trình duyệt trở về ứng dụng cùng **Service Ticket (ST)** dành riêng cho `service`.
3. Ứng dụng gửi ST và `service` cho CAS validation endpoint.
4. CAS phản hồi kết quả; ứng dụng có thể tạo session của riêng mình.

**Giới hạn theo đặc tả CAS:** ST chỉ hợp lệ cho đúng service identifier đã dùng khi cấp vé và **chỉ một lần thử ticket validation**, kể cả lần thử trả kết quả thất bại. Vì thế không thể coi ST đã dùng trong bước 3 là credential nhiều lần cho một API khác. TGT/TGC phục vụ SSO của CAS, càng không nên chuyển cho downstream API vì làm lộ phiên đăng nhập.

### Khi cần CAS proxy authentication

CAS có cơ chế riêng:

~~~text
Portal đã xác thực CAS ST
     |
     +-- được CAS cấp proxy-granting ticket (PGT) khi đủ điều kiện
                  |
                  +-- xin Proxy Ticket (PT) cho targetService = Inventory API
                               |
                               +-- Inventory API xác minh PT với CAS
~~~

PT ràng buộc với **target service**, được xác minh qua endpoint/proxy flow phù hợp và tuân thủ chính sách CAS. Điều này không đồng nghĩa mọi ứng dụng đều hỗ trợ proxy ticket; nó cần cấu hình và quan hệ tin cậy rõ ràng.

Nếu nhiều API hiện đại cần scopes/audience và kiểm soát delegation, một hệ thống có thể chọn mô hình **CAS cho login + OAuth cho API** thay vì chuyển ST giữa dịch vụ.

## 5. Kerberos/SPNEGO: API có thể dùng Kerberos nếu chính API hỗ trợ

Kerberos hoạt động qua service principal và cơ chế xác thực mạng. Với HTTP, client có thể dùng **Negotiate/SPNEGO** để chứng minh quyền truy cập dịch vụ có cấu hình Kerberos. Khác với OAuth bearer token, Kerberos liên quan ticket, authenticator, khóa dịch vụ và chống replay.

- **Trường hợp hợp lệ:** Orders API được cấu hình là Kerberos acceptor phù hợp với service principal của mình; client xin ticket cho chính dịch vụ đó và thực hiện trao đổi SPNEGO đúng chuẩn. API có thể xác thực bằng Kerberos và tự quyết định quyền.
- **Trường hợp không hợp lệ:** Lấy Kerberos service ticket phát cho Portal rồi dán làm `Authorization: Bearer` tại Orders API. Vé được ràng buộc vào service principal và không phải OAuth access token.
- **Delegation/constrained delegation:** Nếu backend cần nhân danh người dùng sang backend khác, phải có quyền và luồng ủy quyền Kerberos đúng chính sách để xin ticket cho **dịch vụ đích**, không sao chép vé Portal.

Đặc tả Kerberos V5 còn yêu cầu server có biện pháp chống replay phù hợp, thường là replay cache trừ khi giao thức ứng dụng có cách bảo vệ tương đương. Vì vậy không thể coi mọi Kerberos ticket là credential độc lập chỉ cần kiểm tra ngày hết hạn.

## 6. OIDC ID token và OAuth access token: cùng có thể là JWT nhưng khác mục đích

Đây là lỗi rất phổ biến trong API dùng Spring Security: vì OIDC ID token thường là JWT, đội phát triển nghĩ chỉ cần API giải mã được JWT là đủ.

| Loại | Người nhận và mục đích | Có gửi cho resource server làm bearer token không? |
| --- | --- | --- |
| **OIDC ID token** | RP/client biết người dùng đã xác thực, `aud` thường gắn với `client_id` | **Không dùng thay access token** |
| **OAuth access token** | API/resource server được chỉ định; scope hoặc policy biểu thị quyền | **Có**, khi đúng loại, issuer, audience và quyền |
| **OAuth refresh token** | Client dùng tại token endpoint theo quy tắc refresh grant | **Không** |
| **Cookie phiên web** | Web app phát hành và kiểm soát session | Không tự dùng ở API khác; nếu API cùng dùng cookie phải thiết kế CSRF/phiên |

Ví dụ minh họa:

~~~text
ID token:
    aud = portal-web-client
    sub = user-123
    purpose = RP xác nhận người dùng đã đăng nhập

Access token:
    aud = orders-api
    sub = user-123
    scope = orders.read
    purpose = truy cập Orders API theo quyền được cấp
~~~

Cùng một `sub` không làm hai token hoán đổi được. Nếu Orders API chỉ kiểm tra chữ ký, bỏ `aud` và loại token, ID token dành cho portal có thể bị chấp nhận nhầm ở API: đây là lỗi **token confusion**.

Access token không nhất thiết là JWT: nó cũng có thể là opaque token, khi đó resource server thường dùng **introspection** theo giao thức đã thống nhất. Hệ thống dùng JWT access token cần xác minh chữ ký và những claim bắt buộc; nơi áp dụng JWT Profile for OAuth 2.0 Access Tokens (RFC 9068) cần kiểm tra profile/token type phù hợp.

## 7. Các kiến trúc phù hợp để gọi API sau SSO

### 7.1. Browser/mobile client nhận OAuth access token cho API

~~~text
Người dùng --SSO tại IdP--> Authorization Server
                                   |
                         OAuth Authorization Code + PKCE
                                   |
                                   v
                          Client nhận access token
                                   |
                 Authorization: Bearer (token dành cho Orders API)
                                   |
                                   v
                           Orders Resource Server
                         kiểm tra aud, scope, quyền dữ liệu
~~~

Client yêu cầu tài nguyên/scope phù hợp; authorization server quyết định cấp quyền theo grant, consent và policy. ID token (nếu có) phục vụ đăng nhập vào OIDC client. API chỉ chấp nhận **access token dành cho mình**.

### 7.2. Server-side web app dùng SAML SSO, backend cần gọi API

~~~text
Browser --SAML SSO--> Portal (SP)
                          |
                     Session của Portal
                          |
             Backend Portal cần gọi Orders API
                          |
             Xin access token bằng flow được hỗ trợ
             (delegation/token exchange/bridge...)
                          |
                          v
                      Orders API
~~~

Portal không chuyển nguyên `SAMLResponse` hoặc cookie SSO của IdP cho Orders API. Nếu API cần thực hiện hành động **thay mặt người dùng**, hệ thống cần cơ chế được phép chuyển danh tính/quyền (ví dụ SAML bearer grant hoặc OAuth token exchange khi các bên hỗ trợ). Nếu API chỉ thực hiện công việc **nhân danh backend**, OAuth client credentials có thể phù hợp, nhưng credential này **không tự mang quyền hay danh tính người dùng cuối**.

Mô hình BFF (Backend for Frontend) có thể giữ session cookie trong giao tiếp browser–BFF, và BFF sử dụng access token khi gọi API downstream. BFF vẫn cần CSRF protection ở những endpoint xác thực bằng cookie.

### 7.3. CAS proxy hoặc Kerberos

Nếu hệ thống đã thống nhất CAS proxy ticket hoặc Kerberos/SPNEGO cho đúng backend, áp dụng giao thức đó với target service/SPN được khai báo rõ. Đây là ngoại lệ kiến trúc có điều kiện; không biến ST hoặc service ticket của web thành bearer token dùng mọi nơi.

### 7.4. Service-to-service không có người dùng

Backend chạy job đồng bộ gọi API có thể sử dụng client credentials hoặc workload identity. Quyền của ứng dụng cần được tách khỏi quyền của người dùng. Khi nghiệp vụ đòi hỏi kiểm toán “ai yêu cầu thay đổi?”, client-credentials token đơn lẻ không thay thế được danh tính và ủy quyền người dùng.

## 8. Spring Security: cấu hình Resource Server nhận đúng access token

Ví dụ một **Spring Boot 3.x servlet API** trên Java 17+ bảo vệ `/api/orders`. Dự án cần dependencies Spring Web, Spring Security và `spring-boot-starter-oauth2-resource-server`; authorization server phải cấp JWT access token có audience `orders-api` và các scope tương ứng.

Tạo `src/main/java/com/example/security/ApiSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/oauth
          audiences:
            - orders-api
~~~

**Giải thích:**

1. `oauth2ResourceServer(...jwt(...))` bảo vệ API theo cơ chế **JWT bearer access token**. Không có bước tự coi SAML assertion hoặc CAS ST là JWT.
2. `issuer-uri` chỉ định issuer đáng tin cậy để tìm cấu hình/khóa xác minh và kiểm tra issuer; `audiences` buộc JWT có audience của **Orders API**. Chỉ cấu hình issuer **không thay thế** kiểm tra audience.
3. Spring Security mặc định thường ánh xạ scope trong claim `scope` hoặc `scp` thành authority mang tiền tố `SCOPE_`; hai rule thể hiện quyền đọc và ghi. API vẫn phải kiểm tra quyền nghiệp vụ với từng đơn hàng.
4. `STATELESS` và việc tắt CSRF trong ví dụ **chỉ phù hợp với một API thuần bearer token, không xác thực request bằng browser cookie**. Nếu cùng ứng dụng có `saml2Login`/`oauth2Login`, form hoặc session cookie, cần phân tách SecurityFilterChain theo đường dẫn và bảo vệ CSRF ở endpoint dùng cookie.
5. URL `example.test` trong minh họa không phải issuer đang hoạt động. Khi triển khai phải dùng issuer và audience thực sự của tổ chức, đồng thời có controller API, authorization server và khóa hợp lệ.

Đây là **class cấu hình của một dự án Spring Boot**, không phải chương trình Java độc lập có thể chạy trực tiếp với `javac` và `java`; nó không in stdout cố định. Mã được trình bày theo Spring Security 6.x và Java 17+, cần dự án đã khai báo dependencies phù hợp. Nếu authorization server cấp **opaque token**, phải cấu hình Resource Server introspection thay cho JWT decoder.

Ví dụ client gọi API **sau khi đã xin được access token hợp lệ** và đặt vào biến môi trường `ACCESS_TOKEN`:

~~~bash
curl --fail-with-body --header "Authorization: Bearer $ACCESS_TOKEN" "https://api.example.test/api/orders"
~~~

Lệnh trên không tự đăng nhập và không tự cấp token. Biến `ACCESS_TOKEN` phải mang **OAuth access token hợp lệ cho Orders API**. Không thay bằng OIDC ID token, SAMLResponse, CAS ticket, Kerberos service ticket hay refresh token.

### Phân biệt ba nhóm tính năng Spring Security

- **`saml2Login`:** SP/RP xử lý SAML Web Browser SSO, xác thực người dùng rồi tạo ngữ cảnh đăng nhập ứng dụng.
- **`oauth2Login`:** client/RP xử lý luồng đăng nhập OAuth2/OIDC; với OIDC kiểm chứng ID token theo quy tắc OIDC.
- **`oauth2ResourceServer`:** API nhận và kiểm chứng bearer access token (JWT hoặc opaque theo cấu hình) để bảo vệ tài nguyên.

Một ứng dụng có thể sử dụng nhiều nhóm, nhưng mỗi luồng có trách nhiệm và yêu cầu bảo mật khác nhau. **Không dùng cấu hình login để giả định API tự có token hoặc tự được phân quyền.**

## 9. Khi API cố ý chấp nhận assertion hoặc ticket: điều kiện bắt buộc

Không có quy tắc tuyệt đối rằng API *không bao giờ* được xác thực bằng SAML, CAS hay Kerberos. Một API có thể chấp nhận credential theo profile riêng nếu **nó đã được thiết kế là bên nhận hợp lệ**. Trước khi triển khai, phải có:

1. **Hợp đồng giao thức:** nêu rõ endpoint, credential type, profile/binding, cách chuyển, cách xác minh; không đoán loại credential theo việc chuỗi có vẻ giống JWT.
2. **Trust đúng nguồn:** chỉ tin issuer, chứng thư, khóa, CAS server hoặc Kerberos realm/service đã được cấu hình và kiểm chứng.
3. **Bên nhận chính xác:** audience, recipient, service identifier hoặc SPN phải là dịch vụ đích; không chấp nhận vé cấp cho ứng dụng khác.
4. **Hiệu lực và chống replay:** thời hạn, request/response binding, one-time ticket validation, nonce/authenticator khi giao thức yêu cầu.
5. **Authorization tách biệt:** kiểm tra role/permission/scope, tenant, ownership và quy tắc nghiệp vụ; tránh nhầm thành công đăng nhập với quyền quản trị API.
6. **Bảo vệ credential:** TLS, cookie flags, không ghi token/assertion vào log hoặc URL ngoài trường hợp bắt buộc của giao thức; quản lý key rotation và lỗi xác minh.
7. **Vòng đời:** thiết kế expiration, revocation, logout, deprovisioning và phản ứng khi IdP/CAS/authorization server gặp sự cố.
8. **Hỗ trợ thật sự:** nếu dùng RFC 7522, RFC 8693, CAS proxy hoặc Kerberos delegation, cả client, server và hệ thống cấp token phải hỗ trợ chính xác, có policy cấp quyền phù hợp.

Với API công khai hoặc microservices hỗ trợ OAuth, việc **phát hành access token có audience/scope phù hợp** thường dễ vận hành và phân quyền hơn việc dạy từng API chấp nhận mọi loại chứng cứ đăng nhập.

## 10. Lỗi thường gặp khi tích hợp

| Dấu hiệu | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| SAMLResponse được gửi trong Bearer header, API trả `401` | API không hỗ trợ SAML assertion, JWT decoder không xử lý SAML | Thiết kế flow cấp access token/bridge hoặc SAML API profile hợp lệ |
| CAS ST dùng để đăng nhập xong, validation lần nữa thất bại | ST chỉ một lần validation, ràng buộc đúng service | Không tái sử dụng ST; xem CAS PT dành cho target service |
| API không nhận Kerberos ticket | Sai service principal, key, SPNEGO cấu hình, thời gian hoặc replay | Xác minh SPN, acceptor, keytab và policy delegation |
| API nhận JWT nhưng báo `401` | Sai `iss`, `aud`, hết hạn, chữ ký hoặc token type | Kiểm tra bằng chứng và cấu hình đúng API |
| Đưa OIDC ID token vào API bị từ chối | Token dùng cho RP/client, không phải access token của API | Xin đúng OAuth access token cho audience/resource |
| API trả `403` sau khi token hợp lệ | Thiếu scope hoặc quyền nghiệp vụ | Kiểm tra `SCOPE_` mapping, object/tenant authorization |
| Người dùng logout Portal nhưng API token còn hợp lệ | Phiên web và token API có vòng đời độc lập | Chính sách TTL, revocation/introspection và logout phù hợp |

**Về mã trạng thái:** `401 Unauthorized` thường biểu thị thiếu hoặc credential không được xác thực; `403 Forbidden` thường biểu thị đã xác thực nhưng không đủ quyền. Cách trả lỗi thực tế còn phụ thuộc cấu hình Spring Security và endpoint.

### Các câu hỏi tự kiểm tra

**Câu 1:** IdP phát SAML assertion cho Portal. Assertion có email và nhóm “admin”. API Orders có nên chấp nhận nguyên assertion để duyệt đơn hàng không?  
**Trả lời:** Không mặc nhiên. Phải xác minh assertion dành cho đúng API, được API hỗ trợ theo profile hợp lệ, còn hiệu lực/chống replay và có quyền nghiệp vụ. Thường cần một access token riêng.

**Câu 2:** CAS ST đã được Portal kiểm chứng thành công. Có dùng lại ST để gọi Inventory API không?  
**Trả lời:** Không. ST đã bị tiêu thụ bởi lần validation; còn ràng buộc service ban đầu. CAS proxy cần một PT phù hợp target service.

**Câu 3:** JWT có chữ ký hợp lệ và `sub=user-123`, nhưng `aud=portal-client`; Orders API yêu cầu `aud=orders-api`. Có chấp nhận không?  
**Trả lời:** Không. Chữ ký và subject đúng không bù được audience sai.

**Câu 4:** API có thể xác thực bằng Kerberos không?  
**Trả lời:** Có, nếu API là service đích được cấu hình Kerberos/SPNEGO và xác minh ticket/authenticator đúng chuẩn. Không được tái sử dụng ticket của một dịch vụ khác như bearer chung.

**Câu 5:** Backend có access token từ client-credentials grant. API có thể coi token đó là bằng chứng “nhân viên A đã đồng ý” không?  
**Trả lời:** Không tự động. Client credentials là quyền ứng dụng; cần luồng delegation/on-behalf-of nếu muốn thay mặt người dùng.

## 11. Checklist thiết kế và kiểm thử

- [ ] Xác định loại credential ở mỗi hop: SAML assertion, CAS ST/PT, Kerberos, ID token, OAuth access token hay session cookie.
- [ ] Mỗi credential đều có mục đích, issuer và **service/audience** hợp lệ được phía nhận kiểm chứng.
- [ ] Phân tách authentication khỏi authorization theo scope, role, tenant và đối tượng nghiệp vụ.
- [ ] Với OAuth API, client xin token cho đúng resource; API xác minh chữ ký/introspection, issuer, audience và thời hạn.
- [ ] Không dùng lại CAS ST; không chuyển SAML assertion hoặc Kerberos ticket của service A sang B.
- [ ] Nếu cần bridging/delegation, kiểm tra cả các bên thực sự hỗ trợ RFC 7522, RFC 8693, CAS proxy hoặc Kerberos delegation.
- [ ] Bảo vệ token, assertion, ticket, cookie khỏi rò rỉ trong log, URL và lưu trữ client.
- [ ] Có chính sách CSRF cho phần sử dụng cookie; bảo vệ API bearer token phù hợp.
- [ ] Xử lý đúng lỗi `401`/`403`, hết hạn, logout và thu hồi quyền.

## 12. Ghi nhớ

**Một chứng cứ đăng nhập hợp lệ chưa đủ chứng minh quyền gọi API.** Hãy xác nhận nó được cấp **cho bên nhận nào**, nhằm **mục đích nào**, có thể **sử dụng bao lâu/bao nhiêu lần**, được **kiểm chứng ra sao** và cấp **quyền gì**.

Trong ứng dụng Spring Security, phần đăng nhập SAML/OIDC/CAS/Kerberos và phần API OAuth Resource Server nên có ranh giới rõ. Muốn gọi API sau SSO, hãy xin hoặc trao đổi để nhận đúng access token, hoặc triển khai một giao thức xác thực API đặc thù đã thỏa thuận đầy đủ. Không chuyển nguyên login assertion/ticket một cách tùy tiện.

### Tài liệu chính thức

- Spring Security 6.5 – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security – SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/
- Spring Boot – OAuth2 Resource Server configuration: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- RFC 7522 – SAML 2.0 Assertion Profile for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc7522
- RFC 8693 – OAuth 2.0 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
- RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- Apereo CAS – CAS Protocol Specification: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- RFC 4120 – Kerberos Network Authentication Service (V5): https://www.rfc-editor.org/rfc/rfc4120
