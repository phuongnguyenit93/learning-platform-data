# CasAuthenticationProvider và lựa chọn TicketValidator trong Spring Security CAS

**Central Authentication Service (CAS)** là giao thức đăng nhập một lần (SSO) trong đó **CAS Server** xác thực người dùng và cấp **service ticket (ST)** để một ứng dụng **service** kiểm tra trước khi cho đăng nhập. Với **Spring Security - federation**, thành phần kết nối giao thức CAS với hệ thống xác thực của ứng dụng là **`CasAuthenticationProvider`**. Tuy nhiên, provider không tự gọi mọi endpoint CAS theo cách tùy ý: nó cần một **`TicketValidator`** cụ thể của **Apereo Java CAS Client** để xác minh ticket với CAS Server.

Lựa chọn validator không đơn thuần là chọn tên class mới nhất. Phải trả lời: **service nhận ticket loại nào? Server hỗ trợ CAS 2.0 hay CAS 3.0 validation? Có cần user attributes? Có cho phép proxy ticket và ủy quyền qua proxy chain không?** Đồng thời cần cấu hình đúng **service URL, TLS, chính sách renew, local account/authorities, lifecycle phiên và kiểm thử replay**.

**Mục tiêu bài học:** hiểu pipeline `CasAuthenticationEntryPoint → CasAuthenticationFilter → AuthenticationManager → CasAuthenticationProvider → TicketValidator`, chọn đúng `Cas20ServiceTicketValidator`, `Cas30ServiceTicketValidator` hoặc proxy validator khi cần, áp dụng trong ứng dụng Spring Security, và nhận diện lỗi thường gặp mà không làm yếu ranh giới tin cậy của CAS.

> **Nguyên tắc trọng tâm:** với ứng dụng web chỉ cần CAS login và không chấp nhận proxy ticket, hãy chọn **service-ticket validator** tương thích giao thức CAS mà server công bố. **Không cấu hình `acceptAnyProxy=true` như giải pháp sửa lỗi đăng nhập**; nó thay đổi mức tin cậy và mở bề mặt xác thực ủy quyền.

## 1. Luồng CAS login và vị trí của provider

Một ứng dụng Spring Boot Servlet dùng CAS thường gồm bốn vai:

| Vai trò | Thành phần | Chức năng |
| --- | --- | --- |
| Người dùng | Browser | Điều hướng đến ứng dụng, CAS Server và quay lại bằng `ticket`. |
| CAS Server | Ví dụ `https://sso.example.org/cas` | Xác thực người dùng, phát ST/PT, xác minh một lần tại validation endpoint. |
| CAS Service / Spring application | Ví dụ `https://portal.example.org` | Nhận callback `/login/cas?ticket=ST-...`, tạo phiên ứng dụng sau khi xác minh. |
| Local security / authorization | `UserDetailsService`, `GrantedAuthority`, `SecurityContext` | Gắn danh tính được CAS xác thực với tài khoản, khóa, vai trò và quyền của chính ứng dụng. |

### 1.1. Sơ đồ chi tiết

~~~text
 Browser                Spring Security Portal                  CAS Server
   |                           |                                    |
   | GET /reports             |                                    |
   |-------------------------->|                                    |
   |              chưa có Authentication                           |
   |                           | CasAuthenticationEntryPoint       |
   |<--- 302 /cas/login?service=https://portal.../login/cas -------|
   |---------------------------------------------------------------->|
   |                           |                                login/MFA
   |<--- 302 https://portal.example.org/login/cas?ticket=ST-... ----|
   |                           |                                    |
   | GET /login/cas?ticket=ST-|                                    |
   |-------------------------->|                                    |
   |                           | CasAuthenticationFilter            |
   |                           | creates ticket Authentication      |
   |                           |       |                            |
   |                           | ProviderManager                    |
   |                           |       |                            |
   |                           | CasAuthenticationProvider          |
   |                           |       |                            |
   |                           | TicketValidator.validate(ST,service)|
   |                           |---------- HTTPS /p3/serviceValidate ->|
   |                           |<--------- Assertion / failure ------|
   |                           |                                    |
   |                           | Map CAS principal to local user    |
   |                           | Check local account status         |
   |                           | Create CasAuthenticationToken      |
   |                           | Save SecurityContext/session       |
   |<--------------------------|                                    |
   | 302 /reports              |                                    |
~~~

Hình minh họa một **CAS 3.0 service-ticket validation**; nếu chọn CAS 2.0, endpoint validation có thể là `/serviceValidate`. Tên endpoint/chứng thư thực phải khớp phiên bản và cấu hình CAS Server.

**Phân biệt hai đường HTTP:**

- **Browser → CAS**: `/login?service=...` để người dùng xác thực.
- **Spring backend → CAS**: `/serviceValidate?service=...&ticket=...` hoặc `/p3/serviceValidate?...` để xác minh ticket; đây là **kênh server-to-server qua HTTPS**, không dựa vào browser tự khẳng định đã đăng nhập.

`CasAuthenticationProvider` không thể cho phép một ST chưa xác minh chỉ vì nó bắt đầu bằng `ST-`. **Ticket là credential opaque**, không phải JWT mà service có thể tự decode ra danh tính.

## 2. Các kiểu ticket và identifier của CAS

| Đối tượng | Viết tắt | Vai trò | Cần tránh nhầm với |
| --- | --- | --- | --- |
| **Ticket Granting Ticket** | TGT | CAS Server lưu quyền SSO sau khi người dùng được xác thực; trình duyệt thường giữ cookie liên quan. | ST dùng một lần gửi cho ứng dụng; không lấy TGT làm ticket input tại SP. |
| **Service Ticket** | ST | Được phát riêng cho một giá trị `service`; service xác minh với CAS Server, thường **chỉ một lần**. | PT hoặc session ứng dụng. |
| **Proxy Granting Ticket** | PGT | Cho phép một service đã xác thực được cấp **proxy ticket** để gọi service khác thay mặt người dùng theo CAS protocol. | ST dùng để login ban đầu. |
| **Proxy Granting Ticket IOU** | PGTIOU | Giá trị tương quan giữa validation response và callback chứa PGT. | PGT bí mật thực tế. |
| **Proxy Ticket** | PT | Credential CAS dùng khi có ủy quyền qua một hoặc nhiều proxy service; cần xác minh proxy chain. | ST thường qua `serviceValidate`. |
| **Spring `HttpSession`** | `JSESSIONID` | Phiên ứng dụng sau xác thực, được duy trì theo policy Spring Security. | CAS ticket hoặc cookie SSO của CAS Server. |

### 2.1. ST được gắn với URL service

Khi CAS Server cấp:

~~~text
ticket = ST-abcdef...
service = https://portal.example.org/login/cas
~~~

service ở lần xác minh phải khớp quy tắc CAS Server áp dụng đối với URL đã được ghi nhận. Nếu validator gửi:

~~~text
service = http://portal.internal:8080/login/cas
~~~

thay vì public HTTPS URL dùng khi cấp ticket, validation có thể báo lỗi **INVALID_SERVICE**. Đây là nguyên nhân rất phổ biến khi chạy sau reverse proxy/load balancer.

**Đúng:** `ServiceProperties.service` phải là **URL callback chính xác và công khai** tương ứng `CasAuthenticationFilter`, CAS service registry và URL trong redirect login. **Không dùng hostname theo request header chưa được proxy tin cậy xác nhận để tự tạo service URL.**

### 2.2. ST một lần, không phải access token tái sử dụng

CAS protocol quy định service ticket chỉ hợp lệ cho **một lần validation attempt**; sau đó ticket bị vô hiệu, kể cả lần validation không thành công. Việc refresh URL `/login/cas?ticket=ST-old` hoặc gửi lại cùng ST tới endpoint có thể gây `INVALID_TICKET`, đó là hành vi chống replay bình thường.

Một số thiết kế CAS proxy/stateless có thể dùng **`StatelessTicketCache`** để tái sử dụng một **kết quả đã xác minh** cho các request theo policy riêng; không được nhầm cache này với việc CAS Server cho phép một ST mới đi qua validation nhiều lần. Khi mở rộng stateless cần review kỹ revocation, TTL, scope service và rủi ro replay.

## 3. CasAuthenticationProvider làm gì — và không làm gì?

**`org.springframework.security.cas.authentication.CasAuthenticationProvider`** là một `AuthenticationProvider` của Spring Security, được khai báo trong **`spring-security-cas`**. Nó phục vụ xác thực ticket CAS đã được filter đưa vào `AuthenticationManager`.

### 3.1. Các cộng tác viên chính

| Thành phần / thuộc tính | Vai trò |
| --- | --- |
| `ServiceProperties` | Chứa **service callback URL**, `sendRenew`, `authenticateAllArtifacts` và tên tham số ticket/service. |
| `TicketValidator` | Gửi ticket + service tới đúng CAS validation endpoint, xử lý phản hồi và trả `org.apereo.cas.client.validation.Assertion` hoặc lỗi. |
| `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` | Ánh xạ principal/attributes CAS đã xác minh thành user/authorities trong ứng dụng. |
| `UserDetailsService` (tùy phiên bản/API) | Cách đơn giản tra local user theo CAS principal; kiểm tra lifecycle và quyền nội bộ. |
| `UserDetailsChecker` | Cho phép kiểm tra trạng thái user khi được hỗ trợ; phải test LOCKED/DISABLED thực tế. |
| `GrantedAuthoritiesMapper` | Chuẩn hóa authorities sau khi người dùng được tra; không thay kiểm tra quyền tài nguyên. |
| `key` nội bộ của provider | Nhận diện provider tạo `CasAuthenticationToken` cho logic hỗ trợ token đã xác thực; **không phải CAS server signing key hay user password**. |
| `StatelessTicketCache` (nếu bật) | Cache kết quả ticket đã xác minh cho luồng stateless/proxy theo chính sách. |

Sau khi `TicketValidator` trả về **Assertion** hợp lệ, provider có thể gọi user-details service, kiểm tra account và tạo **`CasAuthenticationToken`** để Spring Security lưu trong **`SecurityContext`**.

**Quan trọng:** `CasAuthenticationProvider` **không tự quyết định** một user có quyền duyệt hóa đơn, thuộc tenant nào hoặc được vào một tài khoản local đã khóa. Logic đó nằm ở `UserDetailsService`/custom policy và tầng authorization. Nếu ST hợp lệ nhưng local account bị DISABLED, phải **từ chối admission**.

### 3.2. Luồng API nhìn từ Spring

~~~text
CasAuthenticationFilter
  -> AuthenticationManager.authenticate(ticketAuthentication)
     -> CasAuthenticationProvider.supports(authenticationType)
        -> TicketValidator.validate(ticket, service)
           -> CAS Server /serviceValidate hoặc /p3/serviceValidate
              -> Assertion (principal, attributes, proxy chain, ...)
        -> loadUserDetails / userDetailsChecker
        -> authorities mapping
        -> CasAuthenticationToken (authenticated)
  -> SecurityContextRepository / HttpSession
~~~

Một điểm về tài liệu phiên bản: nhiều đoạn reference CAS đã tồn tại lâu và mô tả `UsernamePasswordAuthenticationToken` có `CAS_STATEFUL_IDENTIFIER`; JavaDoc mới của `CasAuthenticationFilter` và provider còn đề cập **`CasServiceTicketAuthenticationToken`**. Hãy **kiểm tra phiên bản API cụ thể** (Spring Security 6.x/7.x) thay vì tự khởi tạo lớp token theo một hướng dẫn cũ rồi cho rằng tất cả release đều dùng y hệt. Dùng filter và manager của framework để tránh phải tạo token thủ công.

### 3.3. Provider key không phải một bí mật xác thực

`CasAuthenticationProvider#setKey(String)` cần một chuỗi ổn định phân biệt provider. Đừng nhầm nó với khóa ký của SAML/JWT, `client_secret` OIDC hay mật khẩu CAS. Nó không thể thay:

- Xác minh **service ticket** qua CAS Server và TLS.
- Chống replay của CAS Server.
- Bảo vệ session cookie/CSRF.
- Kiểm tra `UserDetails` và authorization.

Lúc dùng nhiều instance, cấu hình provider phải nhất quán; không thay đổi key tùy tiện giữa các request của cùng kiểu phiên. Không đưa key vào mã để “bảo vệ” tài khoản rồi bỏ xác minh ST.

## 4. TicketValidator: interface và nguồn gốc

Trong Apereo Java CAS Client, interface:

~~~java
org.apereo.cas.client.validation.TicketValidator
~~~

mô tả thao tác xác minh ticket. Mô hình cốt lõi ở mức khái niệm:

~~~java
Assertion assertion = ticketValidator.validate(ticket, serviceUrl);
~~~

Kết quả assertion chứa `Principal` CAS và có thể có attributes, authentication date/proxy chain và dữ liệu theo phiên bản/protocol. Khi CAS Server từ chối ST/PT hoặc response không hợp lệ, validator ném exception; Spring phải xử lý như **Authentication failure**, không tự tạo principal thay thế.

Các lớp triển khai thường gặp:

- `Cas20ServiceTicketValidator` — xác minh service ticket qua **CAS 2.0 `/serviceValidate`**.
- `Cas30ServiceTicketValidator` — dùng **CAS 3.0 `/p3/serviceValidate`**, phù hợp khi cần attributes mở rộng trong response.
- `Cas20ProxyTicketValidator` — xử lý **CAS 2.0 `/proxyValidate`**, có khả năng nhận **proxy tickets** và kiểm soát proxy chain.
- `Cas30ProxyTicketValidator` — dùng **CAS 3.0 `/p3/proxyValidate`**, hỗ trợ proxy tickets và attributes theo CAS 3.0.

**Các class validator này thuộc `org.apereo.cas.client.validation`**, không thuộc `org.springframework.security.cas.authentication`. Spring gọi chúng; Apereo CAS client thực hiện giao thức xác minh ticket.

### 4.1. Chọn theo giao thức và nhu cầu, không chọn theo số major Spring

| Bối cảnh ứng dụng | Validator phù hợp | Endpoint CAS dự kiến | Ghi chú |
| --- | --- | --- | --- |
| Web app nhận **ST** thông thường, server hỗ trợ CAS 2 validation. | `Cas20ServiceTicketValidator` | `/serviceValidate` | Lựa chọn bảo thủ khi chỉ cần principal, tương thích CAS 2. |
| Web app nhận ST, server hỗ trợ CAS 3 và ứng dụng cần **attributes**. | `Cas30ServiceTicketValidator` | `/p3/serviceValidate` | Thích hợp khi dùng user/organization attributes được CAS phát qua CAS 3. |
| Service phải xác minh **PT** qua CAS 2 proxy protocol. | `Cas20ProxyTicketValidator` | `/proxyValidate` | Phải có **proxy trust policy** tường minh. |
| Service phải xác minh PT qua CAS 3 proxy protocol và cần attributes. | `Cas30ProxyTicketValidator` | `/p3/proxyValidate` | Không chọn chỉ vì server là CAS 3; phải có use case proxy thật. |
| CAS Server hỗ trợ cả CAS 2 và CAS 3. | Chọn theo hợp đồng, attributes và loại ticket. | Theo validator. | **Server version không bằng protocol endpoint**; kiểm tra cấu hình release thực. |
| Dự án không chấp nhận proxy nhưng IdP/caller gửi PT. | **Reject PT** qua service-ticket validator. | `/serviceValidate` hoặc `/p3/serviceValidate` | Không tự “fallback sang proxy validator” để tránh lỗi. |

**Không chọn `Cas20ProxyTicketValidator` chỉ vì tên có CAS20 và bạn muốn “hỗ trợ tất cả”.** Proxy authentication là một trust relationship có quyền ủy quyền; mở rộng từ ST sang PT là thay đổi bảo mật quan trọng.

### 4.2. CAS 2.0 và 3.0 khác nhau ở đâu?

**CAS 2.0** thêm `/serviceValidate` và `/proxyValidate` với XML response cho việc xác thực service/proxy ticket. **CAS 3.0** mở rộng khả năng phát **authentication/user attributes**, thường qua `/p3/serviceValidate` và `/p3/proxyValidate`.

Ví dụ response CAS 2 (rút gọn):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>user-42</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Ví dụ response CAS 3 (rút gọn, minh họa):

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>user-42</cas:user>
    <cas:attributes>
      <cas:employeeId>emp-742</cas:employeeId>
      <cas:department>Finance</cas:department>
      <cas:affiliation>staff</cas:affiliation>
      <cas:affiliation>auditor</cas:affiliation>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Các XML trên là minh họa cấu trúc, không phải response có thể tự gửi đến Spring để xác thực**. CAS client phải nhận chúng qua kết nối xác minh ticket với CAS Server đáng tin. Dữ liệu `department` hoặc `affiliation` có thể xuất hiện nhiều giá trị; ứng dụng không được giả định mọi attribute là `String` đơn lẻ. Quan trọng hơn, **có attribute không có nghĩa ứng dụng phải tin nó để cấp vai trò admin**.

### 4.3. Không nhầm endpoint service validation với CAS login URL

CAS login thường:

~~~text
https://sso.example.org/cas/login?service=...
~~~

CAS2 validation:

~~~text
https://sso.example.org/cas/serviceValidate?service=...&ticket=...
~~~

CAS3 validation:

~~~text
https://sso.example.org/cas/p3/serviceValidate?service=...&ticket=...
~~~

Bạn thường truyền **CAS server base URL** `https://sso.example.org/cas` vào constructor `Cas20ServiceTicketValidator` hoặc `Cas30ServiceTicketValidator`; validator tự chọn endpoint protocol. **Không truyền URL `.../login` vào constructor** và không tự nối `/serviceValidate` hai lần.

Một CAS server mới có thể cung cấp CAS 2/3 cùng OIDC/SAML; **đừng dùng `TicketValidator` CAS để xác minh ID Token OIDC hay SAMLResponse**. Đó là các giao thức khác với validators khác.

## 5. ServiceProperties: ràng buộc ticket với đúng ứng dụng

`ServiceProperties` là hợp đồng giữa Spring CAS client và CAS Server về **service URL**.

~~~java
ServiceProperties properties = new ServiceProperties();
properties.setService("https://portal.example.org/login/cas");
properties.setSendRenew(false);
~~~

Đây là **mảnh Java trong dự án Spring Security**, cần import `org.springframework.security.cas.ServiceProperties`.

| Thuộc tính | Ý nghĩa | Rủi ro nếu sai |
| --- | --- | --- |
| `service` | Callback service URL được gửi khi redirect tới CAS và khi validate ticket. | `INVALID_SERVICE`/ticket không match, hoặc service identity confusion. |
| `sendRenew` | Nếu bật, gửi `renew` theo CAS để buộc xác thực rõ ràng thay vì chỉ tận dụng SSO session. | Nếu cấu hình không đồng bộ giữa login và validation, hành vi thất bại/không đạt freshness. |
| `authenticateAllArtifacts` | Cho xử lý ticket ở nhiều URL hơn; cần service URL được xác định động. | Mở rộng bề mặt nhận ticket, sai ranh giới service hoặc stateless cache. |
| `artifactParameter` | Tên tham số ticket, mặc định thường là `ticket`. | Filter không tìm thấy ticket nếu đổi lệch. |
| `serviceParameter` | Tên tham số service, mặc định `service`. | CAS login không nhận đúng callback. |

### 5.1. Lưu ý `sendRenew=true`

CAS protocol có tham số `renew`; nó yêu cầu CAS chỉ chấp nhận ticket được cấp sau việc **trình bày credentials chính thức** thay vì tự đăng nhập lại bằng phiên SSO hiện có. Đây là **chính sách reauthentication**, không mặc nhiên là **MFA** hoặc chống phishing. Nếu nghiệp vụ đòi MFA, cần một hợp đồng assurance/context riêng với CAS Server và xác minh kết quả, không chỉ dựa vào `renew=true`.

Khi không có nhu cầu xác thực lại ngay mỗi lần vào ứng dụng, `sendRenew=false` cho phép tận dụng CAS SSO. Trong ứng dụng nhạy cảm, cân nhắc bật renew có hiểu biết về UX và CAS Server policy, đồng thời thiết kế step-up cho thao tác nhạy cảm thay vì áp dụng bừa cho mọi trang.

### 5.2. Cấu hình sau reverse proxy

Nếu portal chạy container `http://portal-pod:8080` nhưng người dùng truy cập `https://portal.example.org`, **CAS service URL phải dùng HTTPS public URL** mà CAS Server nhận và đã đăng ký. Đừng tự tạo URL theo header `X-Forwarded-Host` không tin cậy, vì attacker có thể tạo service URL lạ.

Cần kiểm tra:

1. Reverse proxy cung cấp forwarded headers qua đường kết nối đáng tin, bảo vệ khỏi header do client trực tiếp chèn.
2. Spring Boot/Spring Security xác định đúng external scheme/host/path.
3. CAS Server **service registry** allowlist đúng `https://portal.example.org/login/cas`.
4. Browser redirect và backend validation dùng cùng URL dịch vụ đã được cấp ticket.
5. Không đưa `JSESSIONID`, query parameter nhạy cảm hoặc return URL tùy ý vào `service` nếu không được quản lý.

**Đừng tắt validation service matching** để sửa lỗi cấu hình proxy/HTTPS. Ràng buộc ticket với service là một trụ cột chống gửi ticket từ ứng dụng A sang ứng dụng B.

## 6. Chọn ServiceTicketValidator khi chỉ cần đăng nhập web

Trong kịch bản đa số ứng dụng Spring MVC:

~~~text
Browser -> CAS Server /login
        -> ST dành https://portal.example.org/login/cas
        -> Spring CasAuthenticationFilter
        -> CasAuthenticationProvider
        -> Cas20ServiceTicketValidator hoặc Cas30ServiceTicketValidator
        -> CAS Server xác minh ticket/service
        -> local admission và session
~~~

**Chọn service ticket validator** khi ứng dụng **không cần nhận ticket qua proxy service**. Nếu bạn cần user attributes để map hồ sơ, có thể chọn **Cas30ServiceTicketValidator** với CAS 3 validation endpoint có hỗ trợ.

Ví dụ Spring beans:

~~~java
@Bean
TicketValidator ticketValidator() {
    return new Cas30ServiceTicketValidator("https://sso.example.org/cas");
}
~~~

Cần import:

~~~java
import org.apereo.cas.client.validation.TicketValidator;
import org.apereo.cas.client.validation.Cas30ServiceTicketValidator;
~~~

Đây là bean trong Spring Configuration, không phải chương trình Java SE độc lập.

**Không dùng `Cas30ServiceTicketValidator` chỉ vì CAS Server có chữ “v7/v8”**; phải xác nhận server vẫn bật **CAS protocol v3 endpoints**, quyền release attributes và compatibility của Java CAS Client. Một CAS Server có nhiều phiên bản sản phẩm vẫn có thể cung cấp endpoint `/serviceValidate` của CAS2.

### 6.1. Kiểm soát attributes

Nếu CAS3 trả `attributes.roles=["analyst"]`, đừng làm:

~~~text
CAS attributes.roles -> ROLE_ADMIN hoặc ROLE_ + arbitraryString
~~~

mà không allowlist/tenant mapping. CAS Server chịu trách nhiệm **xác thực danh tính**; ứng dụng còn phải tra trạng thái local `LOCKED/DISABLED`, tenant/permission được phê duyệt, và 403 với thao tác không có quyền. Attribute để hiển thị và thuộc tính để cấp quyền có yêu cầu provenance khác nhau.

## 7. Chọn ProxyTicketValidator khi có ủy quyền thực sự

CAS proxy authentication cho phép Service A (đã xác thực người dùng) gọi Service B **thay mặt** người dùng. Có thể Service B nhận **proxy ticket PT**, không phải ST dành cho browser login.

~~~text
Browser --> Service A ------ ST validate ------> CAS
                |      pgtUrl / PGTIOU
                |<----- PGT callback / PGT ------- CAS
                |
                | request PT for Service B
                +-------------------------------> CAS /proxy
                |<------------------------------- PT-for-B
                |
                +------ HTTP request + PT ------> Service B
                                                  |
                                       Cas20/30ProxyTicketValidator
                                                  |
                              CAS /proxyValidate or /p3/proxyValidate
                                                  |
                                       checks service=Service-B, proxies
                                                  |
                                         authorize / deny
~~~

Đây là luồng CAS proxy, **không phải SAML `ProxyRestriction` hoặc OAuth Token Exchange**. CAS Server cấp PT theo một dịch vụ mục tiêu; Service B phải xác minh PT và **kiểm tra proxy chain** đúng bên đã được phép đại diện.

### 7.1. Proxy validator và danh sách proxy đáng tin

Proxy validator có cấu hình liên quan:

- `acceptAnyProxy`: nếu `true`, mọi proxy chain có thể được xem là được chấp nhận trong phạm vi validator, **không nên dùng mặc định trong production**.
- `allowedProxyChains`: mô tả các chuỗi proxy được phép nếu CAS client/server hỗ trợ và chính sách doanh nghiệp đã xác định.
- `proxyCallbackUrl`/`proxyGrantingTicketStorage`: phục vụ quá trình yêu cầu và nhận **PGT**, khi ứng dụng muốn **phát PT cho downstream**.
- `proxyReceptorUrl` của `CasAuthenticationFilter`: endpoint nhận PGT callback; phải tương ứng URL mà CAS Server gọi.

**Lựa chọn an toàn:** nếu Service B không có business case proxy, **không chuyển sang proxy validator**. Nếu cần PT, tạo một allowlist cụ thể dựa trên **proxy identity/URL** đã kiểm chứng; kiểm thử proxy chain chứa một hop lạ phải thất bại. Mở `acceptAnyProxy=true` nghĩa là nới rộng bên được đại diện danh tính.

### 7.2. Hai nghĩa khác nhau của proxy

1. **Ứng dụng đang proxy tới backend**: cần **PGT** để yêu cầu PT; cấu hình callback HTTPS, storage, `Cas20/30ProxyTicketValidator` thích hợp.
2. **Ứng dụng backend nhận PT**: cần proxy validator xác minh PT và danh sách proxy đã đi qua; không nhất thiết backend phải có PGT.

Không gộp hai trường hợp này rồi mặc định mọi ứng dụng phải đăng ký `pgtUrl`. Chỉ triển khai callback/PGT nếu thực sự phát proxy tickets.

### 7.3. PGT callback cần bảo vệ nghiêm

CAS Server gọi `pgtUrl` qua HTTPS, gửi `pgtId` và `pgtIou` để tương quan. Cần:

- Đảm bảo callback URL chính xác, certificate/TLS được kiểm tra, tránh chuyển hướng ra domain lạ.
- Lưu PGT bằng kho có kiểm soát quyền, không log URL/callback query thô chứa PGT.
- Ghép PGT với PGTIOU từ response validation **đúng giao dịch**.
- Dọn PGT/expired tickets, có TTL, hạn mức, revocation và quy trình rotation.
- Không dùng PGT một cách chung chung để xin PT cho bất kỳ backend không thuộc allowlist.

Bật proxy là **thay đổi trust boundary**; cần security review riêng ngoài cấu hình `CasAuthenticationProvider`.

## 8. Mẫu Spring Boot Servlet: provider + validator + filter + entry point

Ví dụ dưới đây hướng tới **Spring Security 6.x, Java 17+** và minh họa **service ticket CAS 3.0**, không dùng proxy. Cấu hình là phần của **ứng dụng Spring Boot** có CAS Server thực, Spring Security 6.x và Java CAS Client tương thích. Vì cấu hình CAS phụ thuộc phiên bản, hãy chạy kiểm thử biên dịch với BOM/dependencies đã khóa; **không coi mảnh code là dự án hoàn chỉnh khi chưa có CAS service registration/user repository**.

### 8.1. Dependencies ở mức module

~~~xml
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
  </dependency>
</dependencies>
~~~

**Đây là dependency fragment trong Maven `pom.xml`**, không phải POM hoàn chỉnh. Version phải được quản lý qua Spring Boot dependency management và/hoặc version Apereo CAS client tương thích; không sao chép một version bất kỳ. Một số tập hợp Spring Security/CAS Client mới có biến động API Java/Jakarta; kiểm tra Java 17+, `jakarta.servlet` và module chính xác khi nâng cấp.

### 8.2. Java Configuration

Tệp `src/main/java/example/cas/CasSecurityConfig.java`:

~~~java
package example.cas;

import org.apereo.cas.client.validation.Cas30ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
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

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService("https://portal.example.org/login/cas");
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    TicketValidator ticketValidator() {
        // CAS protocol 3.0; dùng CAS20ServiceTicketValidator
        // nếu server chỉ hỗ trợ CAS 2.0 service validation.
        return new Cas30ServiceTicketValidator(
                "https://sso.example.org/cas");
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties serviceProperties,
            TicketValidator ticketValidator,
            UserDetailsService userDetailsService) {

        CasAuthenticationProvider provider =
                new CasAuthenticationProvider();
        provider.setServiceProperties(serviceProperties);
        provider.setTicketValidator(ticketValidator);
        provider.setUserDetailsService(userDetailsService);
        provider.setKey("portal-cas-provider");
        return provider;
    }

    @Bean
    CasAuthenticationEntryPoint casEntryPoint(
            ServiceProperties serviceProperties) {

        CasAuthenticationEntryPoint entryPoint =
                new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl("https://sso.example.org/cas/login");
        entryPoint.setServiceProperties(serviceProperties);
        return entryPoint;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            CasAuthenticationProvider provider,
            CasAuthenticationEntryPoint entryPoint) throws Exception {

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setAuthenticationManager(new ProviderManager(provider));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                    entryPoint))
            .addFilterAt(filter, CasAuthenticationFilter.class);

        return http.build();
    }
}
~~~

Các setter ở cấu hình phản ánh **API CAS provider/entry point** đã có trong tài liệu Spring Security, nhưng phải xác minh rằng **`CasAuthenticationFilter` được đặt vào đúng filter chain** theo phiên bản đang chạy. Đây là ví dụ service-ticket flow, **chưa** có `UserDetailsService` bean, account DB, controller, CAS Server registration, TLS certificate hay integration tests; các thành phần đó phải do dự án thật cung cấp. Nếu `UserDetailsService` chưa có, ứng dụng sẽ không inject được bean và không khởi động thành công.

**Lưu ý bảo mật:** provider sử dụng `UserDetailsService` để tìm local account theo principal đã được CAS xác minh. Cần đảm bảo `UserDetails` tôn trọng `disabled/locked` và danh sách authorities thuộc tenant; kiểm tra bằng integration test. Mỗi hệ thống có thể cần `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` thay vì chỉ tra tên khi mapping ID/attributes phức tạp.

### 8.3. Khi cần CAS 2.0 thay CAS 3.0

Thay đúng bean validator:

~~~java
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;

@Bean
TicketValidator ticketValidator() {
    return new Cas20ServiceTicketValidator(
            "https://sso.example.org/cas");
}
~~~

Đây là **đoạn thay thế**, không được thêm hai bean cùng kiểu mà không phân biệt `@Qualifier`; khi sử dụng cấu hình ở trên, **chỉ có một validator** cho provider. CAS 2 service validation không đồng nghĩa API attributes CAS 3 của bạn sẽ được trả về như mong muốn; nếu cần attributes phải có endpoint và response profile phù hợp.

### 8.4. Khi cần ProxyTicketValidator

Nếu có yêu cầu thật nhận PT:

~~~java
import org.apereo.cas.client.validation.Cas30ProxyTicketValidator;

@Bean
TicketValidator ticketValidator() {
    Cas30ProxyTicketValidator validator =
            new Cas30ProxyTicketValidator("https://sso.example.org/cas");
    // Cấu hình allowlist proxy chains cụ thể theo
    // phiên bản Apereo Java CAS Client và hợp đồng proxy.
    // Không bật acceptAnyProxy trong production.
    return validator;
}
~~~

Đây là **mảnh cấu hình để minh họa lựa chọn class**, **chưa phải cấu hình proxy production hoàn chỉnh**. Cần cấu hình allowed proxy chains, PGT handling nếu có, session/stateless service details và kiểm thử end-to-end. Không “đổi validator” mà bỏ qua bảo vệ proxy chain, đúng service URL và authorities của backend.

### 8.5. URL filter và proxy có thể khác

`CasAuthenticationFilter` thường theo dõi `/login/cas` (có thể cấu hình `filterProcessesUrl`). Khi chỉ xử lý browser ST, **service URL** thường đúng endpoint này. Khi `ServiceProperties.authenticateAllArtifacts=true` để nhận ticket ở các URL khác, filter có thể cần **`ServiceAuthenticationDetailsSource`** lấy service URL động theo từng request. Bật flag mà không cấu hình chính xác details source/validator có thể khiến ticket không match hoặc vô tình chấp nhận ticket ở endpoint không dự tính.

Các chuỗi URL phải được đối chiếu với CAS **service registry** và bên tạo ticket. Đừng chấp nhận một `service` từ query string của browser để thay URL được server cấu hình.

## 9. TicketValidator và tùy biến chính sách HTTPS/trust

### 9.1. HTTPS phải thật sự xác minh CAS Server

`TicketValidator` gửi ticket là credential đến CAS Server; nếu ứng dụng bị MITM hoặc kết nối tới CAS Server giả, kẻ tấn công có thể đọc ST và trả danh tính giả. Vì thế:

- Chỉ cấu hình **HTTPS URL** thuộc CAS Server thật.
- Dùng Java truststore/PKIX với chứng thư hợp lệ, hostname verification đúng.
- Không cài `TrustAll`/`NoopHostnameVerifier` hoặc `SSLContext` bỏ certificate validation để “sửa lỗi SSL”.
- Giới hạn outbound egress và DNS theo kiến trúc, tránh CAS base URL được cấu hình từ dữ liệu user.
- Đặt connect/read timeouts phù hợp và **fail closed** khi timeout/5xx.
- Giữ secret/ticket khỏi logs, metrics, query traces và error pages.

Dù đường browser CAS login dùng HTTPS, **đường server-to-server validate** cũng phải được bảo vệ. Đừng lấy danh tính trực tiếp từ `ticket` hoặc browser header nếu HTTPS validation thất bại.

### 9.2. CAS service registry ở server và client phải đồng bộ

Một CAS Server thường có **service registry** chỉ cho phép những callback/service đã đăng ký. Đây là lớp bảo vệ chống cấp ticket cho dịch vụ lạ và open redirect. SP cần khớp:

~~~text
CAS Server /login service:
  https://portal.example.org/login/cas

CasAuthenticationEntryPoint:
  same ServiceProperties.service

CasAuthenticationProvider -> TicketValidator:
  same validated service URL

CAS Server service registry:
  permits exactly intended service identity
~~~

Có thể CAS registry dùng mẫu URL/regex để hỗ trợ nhiều môi trường; phải **càng cụ thể càng tốt** để tránh vô tình cho phép attacker-controlled subdomain hoặc redirect endpoint. Không chỉ thử đổi `service` trong URL cho đến khi login thành công; cần giải thích vì sao một service identifier đúng.

### 9.3. Không phát quyền mặc định từ TicketValidator

CAS validation result cho biết `principal` được CAS xác thực và các attributes CAS công bố. Trong Spring Security, **authorization** vẫn là việc của local authorities và method/resource policies.

Ví dụ một CAS principal `user-42` có attribute `roles=admin` từ external directory nhưng local app account bị khóa: **deny admission**, không tạo `ROLE_ADMIN` chỉ vì response XML chứa từ “admin”. Nếu không có local record và JIT provisioning không được phê duyệt, mặc định từ chối. Khi có nhiều tenants/IdP sources thông qua CAS, identity mapping cần namespace/issuer hoặc identity source contract, không nối bằng email đơn thuần.

## 10. UserDetailsService, Assertion và quyền cục bộ

### 10.1. Hai lựa chọn nạp người dùng

**Một:** `UserDetailsService` có thể tra `username` từ CAS `Assertion.getPrincipal().getName()` (hoặc wrapper/framework path), phù hợp khi CAS principal là khóa ổn định đã được thống nhất và local account DB có mapping một-một.

**Hai:** `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` cho phép xét chi tiết **CAS Assertion** và attributes đã được validator trả về. Phù hợp khi cần map subject từ CAS sang local account, tenant, multi-valued attributes hoặc admission policy phức tạp. Nhưng đừng tự dùng bất kỳ group nào để cấp admin; phải có allowlist và local entitlement.

Trong cả hai trường hợp:

- CAS principal là **kết quả sau ticket validation**; không lấy từ request parameter `username`.
- Nếu account `LOCKED`/`DISABLED`, reject authentication và không tạo `SecurityContext` thành công.
- Nếu local status DB outage, **fail closed** khi không thể đưa ra quyết định cấp quyền.
- Mọi `GrantedAuthority` có được map chỉ là đầu vào; backend vẫn phải kiểm tra **resource/tenant/ownership** cho từng API.

### 10.2. `CasAuthenticationToken` và Assertion

Sau authentication, Spring Security có thể đặt `CasAuthenticationToken` vào `SecurityContext`. Token này đại diện cho một **kết quả xác thực thành công** và có thể giữ `Assertion` từ CAS client.

Phân biệt:

| Spring/CAS object | Nguồn | Dùng cho |
| --- | --- | --- |
| `CasServiceTicketAuthenticationToken` hoặc CAS-specific request token theo version | Filter tạo từ CAS ticket callback. | Đầu vào của `AuthenticationManager`; **chưa chứng minh login thành công**. |
| `Assertion` (`org.apereo.cas.client.validation.Assertion`) | TicketValidator sau CAS server validation. | CAS principal, attributes/proxy details đã được CAS công bố. |
| `CasAuthenticationToken` | CasAuthenticationProvider sau user loading/checks. | `Authentication` đã xác thực; có principal và authorities. |
| `SecurityContext` | Spring Security duy trì. | Phiên danh tính/ủy quyền của request hiện tại. |
| Local account record | DB hoặc service được phê duyệt. | Status, tenant, role/entitlement, revocation. |

Đừng giữ raw CAS ticket như mật khẩu dài hạn trong ứng dụng; không serialize Assertion/PGT vào public JSON/log. Nếu trả `/me`, chỉ trả các trường tối thiểu (ví dụ local user ID và quyền phù hợp), không trả `ticket` hoặc URL validation.

## 11. Java 17 tự chạy: chọn validator theo policy

Chương trình độc lập dưới đây giúp kiểm tra **quy tắc lựa chọn validator**, phân biệt CAS2/CAS3, ST/PT, thuộc tính và proxy allowlist. Nó **không import Spring hoặc Apereo CAS**, không thực sự gửi ticket hay xác minh chữ ký; lớp `Choice` chỉ mô tả tên validator/endpoint nên có thể chạy với **JDK 17**.

Tệp `CasValidatorSelectionDemo.java`:

~~~java
import java.util.Set;

public class CasValidatorSelectionDemo {

    enum Protocol { CAS2, CAS3 }
    enum TicketKind { SERVICE, PROXY }

    record Requirement(
            Protocol protocol,
            TicketKind ticketKind,
            boolean requireUserAttributes,
            String proxyIdentity) {}

    record Choice(String validatorName, String endpoint,
                  boolean allowed) {}

    static Choice choose(Requirement req, Set<String> allowedProxies) {
        if (req.requireUserAttributes()
                && req.protocol() != Protocol.CAS3) {
            return new Choice("NONE", "NONE", false);
        }

        if (req.ticketKind() == TicketKind.SERVICE) {
            if (req.protocol() == Protocol.CAS3) {
                return new Choice("Cas30ServiceTicketValidator",
                                  "/p3/serviceValidate", true);
            }
            return new Choice("Cas20ServiceTicketValidator",
                              "/serviceValidate", true);
        }

        // PROXY: chỉ cho phép nếu có danh tính proxy rõ,
        // đã được xác minh và nằm trong allowlist.
        if (req.proxyIdentity() == null
                || !allowedProxies.contains(req.proxyIdentity())) {
            return new Choice("NONE", "NONE", false);
        }

        if (req.protocol() == Protocol.CAS3) {
            return new Choice("Cas30ProxyTicketValidator",
                              "/p3/proxyValidate", true);
        }
        return new Choice("Cas20ProxyTicketValidator",
                          "/proxyValidate", true);
    }

    public static void main(String[] args) {
        Set<String> trustedProxies =
                Set.of("https://gateway.example.org/pgt");

        Choice service2 = choose(new Requirement(
                Protocol.CAS2, TicketKind.SERVICE, false, null),
                trustedProxies);
        System.out.println(service2.validatorName()
                           + " " + service2.endpoint());

        Choice service3 = choose(new Requirement(
                Protocol.CAS3, TicketKind.SERVICE, true, null),
                trustedProxies);
        System.out.println(service3.validatorName()
                           + " " + service3.endpoint());

        Choice unsupported = choose(new Requirement(
                Protocol.CAS2, TicketKind.SERVICE, true, null),
                trustedProxies);
        System.out.println(unsupported.allowed());

        Choice proxy3 = choose(new Requirement(
                Protocol.CAS3, TicketKind.PROXY, true,
                "https://gateway.example.org/pgt"),
                trustedProxies);
        System.out.println(proxy3.validatorName()
                           + " " + proxy3.endpoint());

        Choice untrusted = choose(new Requirement(
                Protocol.CAS3, TicketKind.PROXY, true,
                "https://untrusted.example.org/pgt"),
                trustedProxies);
        System.out.println(untrusted.allowed());

        Choice proxy2 = choose(new Requirement(
                Protocol.CAS2, TicketKind.PROXY, false,
                "https://gateway.example.org/pgt"),
                trustedProxies);
        System.out.println(proxy2.validatorName()
                           + " " + proxy2.endpoint());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CasValidatorSelectionDemo.java
java CasValidatorSelectionDemo
~~~

**Stdout chính xác:**

~~~text
Cas20ServiceTicketValidator /serviceValidate
Cas30ServiceTicketValidator /p3/serviceValidate
false
Cas30ProxyTicketValidator /p3/proxyValidate
false
Cas20ProxyTicketValidator /proxyValidate
~~~

Giải thích:

1. Dịch vụ CAS2 nhận ST, không cần attributes → **Cas20ServiceTicketValidator**.
2. CAS3 nhận ST và cần attributes → **Cas30ServiceTicketValidator**.
3. CAS2 mà policy yêu cầu attributes theo CAS3 → **không coi là đáp ứng**; phải nâng hợp đồng endpoint hoặc thay cơ chế dữ liệu.
4. CAS3 nhận PT từ proxy được allowlist → có thể cân nhắc **Cas30ProxyTicketValidator**.
5. PT từ proxy lạ → deny, không “mở `acceptAnyProxy` để thử”.
6. CAS2 nhận PT từ proxy được phép → **Cas20ProxyTicketValidator**, phải cấu hình chain trust trong CAS client thật.

**Giới hạn quan trọng:** `proxyIdentity` trong demo là tham số giả định **đã được validator/server chứng thực**. Trong production không lấy proxy URL từ HTTP header do browser tự khai rồi cho vào allowlist; CAS Client phải trả và xác minh proxy chain ở CAS validation response. Demo không thực hiện Java networking, không tạo service ticket/PGT, không test TLS; nó chỉ minh họa lựa chọn triển khai.

## 12. Quy trình quyết định chọn validator: checklist thực dụng

~~~text
Ứng dụng nhận ticket CAS theo hợp đồng?
  |
  +-- Không: dùng validator của protocol thực tế (OIDC/SAML), không dùng CAS.
  |
  +-- Có:
         |
         +-- Chỉ nhận SERVICE ticket?
         |     |
         |     +-- CAS2 endpoint /serviceValidate
         |     |      => Cas20ServiceTicketValidator
         |     |
         |     +-- CAS3 endpoint /p3/serviceValidate
         |            => Cas30ServiceTicketValidator
         |
         +-- Cần nhận PROXY ticket thật?
               |
               +-- Không có hợp đồng proxy allowlist
               |      => từ chối PT / không dùng proxy validator
               |
               +-- Có policy proxy chain, target service và TLS
                      |
                      +-- CAS2 /proxyValidate
                      |      => Cas20ProxyTicketValidator
                      |
                      +-- CAS3 /p3/proxyValidate
                             => Cas30ProxyTicketValidator
~~~

Trước khi kết luận, ghi rõ CAS Server có bật endpoint nào, service ID được đăng ký ra sao, attributes nào cần dùng và có hay không yêu cầu ủy quyền proxy.

### 12.1. Các bước kiểm tra kết nối

1. Cấu hình **CAS base URL HTTPS** và xác minh chứng thư CA/hostname từ máy chạy Spring.
2. Kiểm tra service registry của CAS Server cho đúng **public callback `/login/cas`**.
3. Kiểm tra filter nhận đúng đường dẫn `/login/cas?ticket=...` và Spring auth manager có `CasAuthenticationProvider`.
4. Xác nhận CAS Server hỗ trợ `/serviceValidate` hoặc `/p3/serviceValidate` (nếu service validation).
5. Kiểm tra `UserDetailsService`/account mapping và role policy với principal thực tế từ CAS.
6. Nếu proxy, xác định service B, PGT callback, proxy chain allowlist, `/proxyValidate` phù hợp.
7. Chạy integration tests cho ST đầu tiên, replay, wrong service, invalid ticket, outage, attributes và local status.

**Không gửi ticket thật lên trình duyệt DevTools hoặc hệ thống logs chia sẻ** như bằng chứng xác minh. Với môi trường test, dùng danh tính/ticket riêng và che giá trị nhạy cảm khi ghi kết quả.

## 13. Lỗi tích hợp thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra an toàn |
| --- | --- | --- |
| Redirect CAS rồi quay về vòng lặp vô hạn. | Filter không bắt `/login/cas`, provider chưa được nối, service URL lệch hoặc session không lưu. | So `CasAuthenticationFilter`, `CasAuthenticationEntryPoint`, filter chain, callback và error handler. |
| CAS trả `INVALID_SERVICE`. | `ServiceProperties.service` khác `service` khi phát ticket hoặc registry không cho phép. | So URL public chính xác, forwarded headers, context path và proxy. |
| CAS trả `INVALID_TICKET`. | Ticket đã dùng, hết hạn, sai CAS server hoặc gửi nhiều request validate. | Ghi correlation và nguyên nhân; không retry cùng ST bằng fallback. |
| CAS 3 attributes bị thiếu. | Đang dùng CAS2 `/serviceValidate`, CAS Server không release attrs hoặc mapper không đọc. | Xem CAS3 endpoint, attribute release policy và Assertion attrs. |
| Backend gửi PT vào `serviceValidate` và thất bại. | Service validator không chấp nhận proxy tickets. | Nếu use case PT hợp lệ, chuyển proxy protocol với allowlist; không disable validation. |
| Lỗi `ClassNotFoundException: Cas30ServiceTicketValidator`. | Thiếu `cas-client-core` hoặc dependency version không tương thích. | Kiểm tra dependency tree/Jakarta tương thích; không chọn class bằng suy đoán. |
| `NoSuchMethodError` khi start. | Spring Security CAS module và Apereo CAS client sai version. | Dùng dependency management/BOM, cố định version đã được kiểm thử. |
| Java `SSLHandshakeException`. | CAS cert/hostname/truststore không hợp lệ. | Sửa PKIX/truststore, không bật trust-all. |
| CAS principal đúng nhưng app trả 403. | Local role/entitlement/tenant thiếu. | Xem `UserDetailsService`, granted authorities, resource policy. |
| Local account LOCKED vẫn login. | Chưa nối account checker/mapping đúng vào CAS provider. | Test path xác thực CAS với `UserDetailsChecker`/admission policy. |
| Proxy ticket từ service lạ vẫn được xác thực. | `acceptAnyProxy=true`, proxy chain không giới hạn. | Deny và định nghĩa allowedProxyChains đúng. |
| CAS endpoint trả XML/JSON nhưng validator parse lỗi. | Sai protocol validator, media type hoặc response profile. | Đối chiếu `/serviceValidate` vs `/p3/serviceValidate`, CAS Client version. |
| Callback ở node B không có session node A. | Session store cục bộ, thiếu sticky/failover protection. | Spring Session/shared store và test đa node. |
| Logout local xong browser vẫn SSO lại ngay. | CAS TGT/SSO cookie còn ở CAS Server. | Phân biệt logout ứng dụng với CAS single logout, cấu hình SLO riêng. |
| Validation timeout dẫn đến login vẫn thành công. | Hệ thống có fallback cho phép user khi CAS không sẵn sàng. | **Fail closed**; báo retry, không tạo phiên trên lỗi mạng. |
| Service URL dùng `http://pod:8080` sau reverse proxy. | Trust forwarded headers chưa chuẩn, hardcoded internal service. | Dùng external HTTPS service đăng ký ở CAS, kiểm tra proxy trust. |
| Một ST được validate thành công nhiều lần. | CAS server/custom validator vi phạm single-use, hoặc cache dùng sai. | Test atomic one-time ticket invalidation, xem cache/stateless path. |

### 13.1. Đọc lỗi `AuthenticationException` đúng cách

CAS validator có thể ném `TicketValidationException` của CAS client; Spring adapter/provider biến lỗi thành đường authentication failure theo API/version. Không đưa exception đầy đủ chứa ticket, URL nội bộ hoặc stack trace đến trình duyệt. Gợi ý phân loại nội bộ:

~~~text
CAS_TICKET_INVALID
CAS_SERVICE_MISMATCH
CAS_VALIDATOR_NETWORK_FAILURE
CAS_VALIDATOR_RESPONSE_FORMAT_ERROR
CAS_PROXY_NOT_ALLOWED
CAS_LOCAL_ACCOUNT_LOCKED
CAS_LOCAL_ACCOUNT_NOT_PROVISIONED
CAS_AUTHENTICATION_SUCCESS
~~~

Các tên là **reason codes gợi ý của ứng dụng**, không phải danh sách exception chính thức Spring Security. Hãy dùng metrics `cas_validation_latency`, `cas_ticket_replay_rejected`, `cas_provider_success_total` và audit có correlation ID, che ticket để phân tích.

## 14. Kiểm thử một provider và từng validator

| Test case | Kết quả mong đợi |
| --- | --- |
| ST mới, đúng CAS server + service URL, username local ACTIVE. | Validator thành công, provider tạo Authentication với authorities hợp lệ. |
| ST dùng lại sau validation thành công. | CAS Server từ chối `INVALID_TICKET`. |
| ST đã gửi validation nhưng lần trước failed. | CAS Server không chấp nhận lại ticket cũ theo single-use protocol. |
| ST dành service A được gửi tới service B. | Validation thất bại `INVALID_SERVICE`/tương đương. |
| ST hết hạn. | Reject, không tạo Spring session. |
| CAS Server không tin cậy/TLS invalid. | Fail closed; không trust-all. |
| CAS endpoint trả lỗi/timeout. | Không tạo Authentication thành công. |
| CAS2 service ticket với Cas20ServiceTicketValidator. | Nhận principal khi endpoint/hợp đồng hợp lệ. |
| CAS3 ST với Cas30ServiceTicketValidator. | Nhận principal và attributes đã được CAS Server phát. |
| CAS3 ST nhưng Cas20 validator. | Kiểm tra hỗ trợ và giới hạn attrs, không tự cho rằng có mọi CAS3 attributes. |
| PT được gửi tới `/serviceValidate`. | Bị từ chối bởi service-only validation. |
| PT từ proxy đã allowlist qua proxy validator. | Có thể xác thực sau khi đúng service và proxy chain policy. |
| PT từ proxy lạ. | Reject, không tự đổi `acceptAnyProxy` thành true. |
| Proxy chain chứa extra hop chưa được duyệt. | Reject. |
| PGT callback không khớp PGTIOU. | Không cấp/không dùng proxy ticket. |
| `ServiceProperties.sendRenew=true` nhưng user chỉ SSO cookie. | CAS yêu cầu/kiểm tra fresh explicit login theo chính sách renew. |
| CAS user tồn tại nhưng local account DISABLED. | Deny admission; không tạo session đã xác thực. |
| CAS user có group admin nhưng local không được duyệt. | Không tự cấp `ROLE_ADMIN`. |
| Multi-node callback và session store. | Không mất session hoặc tạo kết quả khác nhau vì node. |
| Reverse proxy external HTTPS vs internal HTTP. | Dùng đúng service URL public trong redirect và validation. |
| CAS server phát attributes multi-valued. | Mapper xử lý đúng loại và allowlist. |
| Logout local trong khi CAS TGT còn sống. | Không giả định CAS SSO đã bị xóa; kiểm tra SLO riêng. |

**Unit test Java** cho lựa chọn validator chỉ kiểm tra policy chọn class, không xác minh CAS login. Cần integration test với CAS Server test hoặc môi trường kiểm soát: phát ST thật, chạy callback, verify validation network call, user mapping, auth session và replay. Đặc biệt, phải test **wrong service** và **proxy chain**; hai nơi này liên quan trực tiếp đến lỗi xác thực liên kết.

## 15. CAS và SAML/OIDC: không dùng lẫn validators

Trong cùng hệ sinh thái federation, một CAS Server có thể đóng vai CAS protocol server, SAML IdP, OIDC OP hoặc broker. Tuy nhiên, các protocol không dùng cùng credential/validator:

| Giao thức ứng dụng dùng | Browser callback | Thành phần xác thực phù hợp |
| --- | --- | --- |
| **CAS** | `?ticket=ST-...` ở service callback. | `CasAuthenticationFilter` + `CasAuthenticationProvider` + **CAS `TicketValidator`**. |
| **SAML 2.0 Web SSO** | `SAMLResponse` (HTTP-POST/Artifact). | `Saml2WebSsoAuthenticationFilter` + OpenSAML provider/validators và RelyingPartyRegistration. |
| **OIDC** | `?code=...&state=...` rồi ID Token. | `oauth2Login()`, OIDC decoder/validation, ClientRegistration. |
| **OAuth Resource Server** | `Authorization: Bearer <access_token>`. | JWT decoder hoặc opaque-token introspector, audience/scope/permission policy. |

Nếu dự án đang cân nhắc chuyển từ CAS sang OIDC/SAML, không tự “tái dùng TicketValidator” để xác minh JWT/Assertion XML. Cần thiết kế migration về issuer/subject mapping, logout, session và entitlement; bảo vệ đúng protocol ở từng hop.

## 16. Những sai lầm nghiêm trọng cần tránh

1. **Chọn validator theo phiên bản Spring, không theo CAS validation endpoint.** Sai: phải biết CAS2/CAS3 protocol và loại ticket.
2. **Cho `TicketValidator` nhận bất kỳ URL CAS nào từ query browser.** Sai: tạo SSRF/trust confusion.
3. **Dùng `Cas20ProxyTicketValidator` cho mọi service.** Sai: có thể mở chấp nhận PT ngoài yêu cầu nghiệp vụ.
4. **Bật `acceptAnyProxy=true` để “login cho qua”.** Sai: bỏ kiểm tra chain tin cậy.
5. **Không so service URL với service được cấp ticket.** Sai: giảm bảo vệ chống chuyển ticket giữa ứng dụng.
6. **Dùng internal HTTP URL sau reverse proxy.** Sai: dễ INVALID_SERVICE và nguy cơ phát ticket sai.
7. **Retry cùng ST nhiều lần khi validation thất bại.** Sai: ST thường chỉ một validation attempt.
8. **Bỏ qua `SSLHandshakeException` bằng TrustAll.** Sai: credential và danh tính có thể bị giả mạo.
9. **Dùng `Assertion.getPrincipal().getAttributes()` để tự cấp mọi role.** Sai: cần local policy/allowlist.
10. **Cho local LOCKED login chỉ vì CAS xác thực đúng.** Sai: admission và authentication là hai điều kiện khác.
11. **Nhầm `sendRenew` với MFA.** Sai: reauth không tự chứng minh loại authenticator/mức assurance.
12. **Nhầm `provider.key` là secret ký ticket.** Sai: không thay validation/TLS.
13. **Nhầm `CasAuthenticationToken` với ticket request chưa xác minh.** Sai: cần phân biệt input token và authenticated result.
14. **Bật `authenticateAllArtifacts` vô điều kiện.** Sai: mở thêm URL nhận ticket và yêu cầu service details an toàn.
15. **Lưu ticket nguyên văn vào log/tracing.** Sai: lộ credential one-time và thông tin service.
16. **Nhầm PGTIOU với PGT thực tế.** Sai: PGTIOU chỉ dùng tương quan callback.
17. **Cho callback PGT kết nối HTTP/không kiểm chứng.** Sai: callback là đường nhạy cảm phải dùng TLS và trust.
18. **Dùng CAS TicketValidator để xử lý OIDC ID Token/SAMLResponse.** Sai: các protocol khác nhau.
19. **Local logout nghĩa là CAS Server và mọi service khác logout.** Sai: session/TGT/SLO cần chính sách riêng.
20. **Chỉ test login happy path.** Sai: wrong service, PT từ proxy lạ, replay, CAS outage và local lock quan trọng hơn.

## 17. Checklist quyết định khi triển khai production

1. Ứng dụng dùng **CAS protocol** thật hay OIDC/SAML do CAS Server cung cấp? Có xác định callback tương ứng chưa?
2. CAS Server base URL và login URL đã được cấu hình HTTPS, truststore/hostname và service registry đúng chưa?
3. Browser callback `/login/cas`, `ServiceProperties.service` và ticket validation `service` có cùng public URL không?
4. CAS Server hỗ trợ `/serviceValidate`, `/p3/serviceValidate`, `/proxyValidate`, `/p3/proxyValidate` nào?
5. Service có thực sự cần **user attributes** từ CAS3, hay chỉ cần principal?
6. Service chỉ nhận ST hay còn nhận PT? Nếu PT, có approved proxy chains và test proxy lạ không?
7. Nếu cần PGT, `pgtUrl`/proxy receptor/storage đã bảo vệ, tương quan PGTIOU và dọn TTL chưa?
8. Spring Security version và `spring-security-cas`/CAS client dependency đã được kiểm thử tương thích chưa?
9. `CasAuthenticationFilter` có trong đúng filter chain và `AuthenticationManager` đã nhận provider chưa?
10. `CasAuthenticationProvider` có `serviceProperties`, `ticketValidator`, `key` và user-details service đúng chưa?
11. Local account `LOCKED/DISABLED` và entitlement/tenant có chặn người dùng CAS đã xác thực khi cần không?
12. `sendRenew` có được dùng theo policy authentication freshness mà không bị nhầm với MFA không?
13. Ticket có được xác minh qua TLS, reject replay/wrong service, không log raw credentials không?
14. Đã test CAS Server failure và timeout fail-closed chưa?
15. Nếu deploy multi-node, session store và trust/service URL có nhất quán không?
16. Có chính sách local logout vs CAS Single Logout, session revocation và browser SSO cookie chưa?
17. Có observability theo correlation, reason code và latency, không lộ ticket/PGT/user data không?
18. Có integration test cho ST, CAS3 attributes, PT/proxy chain, local lock, failover và reverse proxy chưa?

## 18. Tự kiểm tra kiến thức

1. **`CasAuthenticationProvider` thuộc framework nào?** — Spring Security module CAS; nó đưa ticket validation vào `AuthenticationManager`.
2. **`TicketValidator` thuộc thư viện nào?** — Apereo Java CAS Client, package `org.apereo.cas.client.validation`.
3. **CAS service ticket được gửi tới đâu?** — Service callback `/login/cas?ticket=...`, sau đó Spring backend xác minh với CAS Server.
4. **Ticket đã được xác minh một lần có còn hợp lệ để validate lại không?** — Không theo quy tắc single-use ST của CAS protocol.
5. **`Cas20ServiceTicketValidator` gọi endpoint nào?** — CAS2 `/serviceValidate`.
6. **Muốn lấy CAS3 user attributes chọn gì?** — Dùng `Cas30ServiceTicketValidator` với CAS3 endpoint/attribute release được hỗ trợ.
7. **Khi nào cần `Cas30ProxyTicketValidator`?** — Khi service có business case nhận PT theo CAS3 và có proxy trust policy.
8. **`acceptAnyProxy=true` có phải cấu hình production an toàn?** — Không mặc định; nó mở trust chain không giới hạn.
9. **PGTIOU có là PGT không?** — Không; PGTIOU tương quan giữa validation response và PGT callback.
10. **`ServiceProperties.service` cần khớp gì?** — Callback URL public đã dùng khi CAS cấp ticket và URL service gửi khi validation.
11. **`sendRenew` có đảm bảo MFA không?** — Không; nó kiểm soát yêu cầu xác thực mới, không xác định mức phương thức.
12. **CAS validation thành công có cho quyền admin không?** — Không; local account/entitlements/tenant còn phải được kiểm tra.
13. **Mất kết nối CAS Server thì được login fallback không?** — Không khi validation là điều kiện bắt buộc; phải fail closed.
14. **Vì sao không thể dùng CAS validator cho SAMLResponse?** — Vì khác giao thức và bằng chứng xác thực.
15. **Sau khi local logout, người dùng có thể SSO lại ngay không?** — Có nếu phiên/TGT tại CAS Server vẫn còn; cần chính sách CAS SLO.
16. **Kiểm thử nào quan trọng ngoài happy path?** — Ticket replay, wrong-service, TLS, PT proxy lạ, account locked, outage và multi-node.

## Tài liệu tham khảo

- [Spring Security — CAS Authentication (reference, Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Spring Security API — CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html)
- [Spring Security API — CasAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html)
- [Spring Security API — CasAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationEntryPoint.html)
- [Spring Security API — ServiceProperties](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html)
- [Apereo CAS — CAS Protocol Specification: ST, serviceValidate, proxyValidate, CAS3 endpoints, PGT/PGTIOU](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Apereo CAS — CAS Protocol versions and service attributes](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html)
- [Apereo Java CAS Client — implementations and validation filters](https://github.com/apereo/java-cas-client/blob/master/README.md)
