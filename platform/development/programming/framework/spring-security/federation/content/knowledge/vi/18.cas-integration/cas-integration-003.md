# CasAuthenticationFilter và tiếp nhận Service Ticket trong Spring Security CAS

## 1. Mục tiêu, bối cảnh và phạm vi

Trong hệ thống **Spring Security – federation**, một ứng dụng Java có thể sử dụng **Central Authentication Service (CAS)** để người dùng đăng nhập một lần rồi truy cập nhiều ứng dụng được đăng ký tại máy chủ CAS. Khi người dùng truy cập tài nguyên được bảo vệ, ứng dụng **không trực tiếp thu mật khẩu CAS**. Trình duyệt được điều hướng đến CAS Server, và sau khi người dùng được xác thực, CAS Server chuyển trình duyệt quay lại một **service URL** của ứng dụng kèm **Service Ticket (ST)**.

Thành phần nhận callback trong Spring Security là **CasAuthenticationFilter**. Nó tiếp nhận ticket, chuyển yêu cầu xác thực đến **AuthenticationManager → CasAuthenticationProvider**, và provider dùng **TicketValidator** liên hệ CAS Server để xác nhận ticket với service đã đăng ký. Chỉ sau khi CAS xác nhận và ứng dụng nạp/kiểm tra tài khoản nội bộ thì Spring Security mới tạo Authentication và phiên đăng nhập phù hợp.

Bài học thuộc nhóm **Tích hợp CAS**, với các mục tiêu:

1. Hiểu rõ **CAS Service Ticket** khác session cookie, Ticket-Granting Ticket (TGT), Proxy Ticket (PT) và OAuth/OIDC/SAML token như thế nào.
2. Theo dõi luồng **trình duyệt → CAS login → callback /login/cas?ticket=... → filter → provider → CAS serviceValidate → SecurityContext**.
3. Giải thích chính xác vai trò của **CasAuthenticationFilter, CasAuthenticationEntryPoint, ServiceProperties, CasAuthenticationProvider, TicketValidator, UserDetailsService**.
4. Cấu hình **service URL, filterProcessesUrl và CAS Server base URL** nhất quán, đặc biệt khi có reverse proxy/TLS termination.
5. Hiểu đặc tính **ST dùng một lần, TTL ngắn và ràng buộc với một service**; vì sao không thể tự tin chuỗi `ticket=ST-...` hoặc dùng lại ticket.
6. Phân biệt **stateful browser ticket login** với **CAS proxy ticket/stateless authentication**; không bật các khả năng proxy khi chưa có nhu cầu.
7. Đọc đúng sự khác nhau giữa tài liệu CAS cũ và API Spring Security hiện hành, tránh nhầm kiểu Authentication token khi nâng cấp.
8. Có ví dụ cấu hình Spring và một **chương trình Java 17 chạy độc lập**, kèm test bảo mật, troubleshooting và checklist triển khai.

**Nguyên tắc cốt lõi:** `CasAuthenticationFilter` **không tự công nhận chuỗi ticket trong URL là đã xác thực**. Nó chỉ khởi đầu yêu cầu xác thực; **CAS Server mới có thẩm quyền xác minh ticket, service và phát thông tin người dùng** qua kênh xác minh được bảo vệ.

## 2. Các khái niệm không được lẫn lộn

| Khái niệm | Nơi được tạo/quản lý | Công dụng | Vòng đời/độ tin cậy |
| --- | --- | --- | --- |
| **CAS Server** | Hệ thống danh tính trung tâm | Xác thực người dùng; cấp và xác minh ticket | Phải là endpoint CAS được cấu hình tin cậy |
| **Service** | Ứng dụng được CAS đăng ký | Đích nhận callback, ví dụ `https://portal.example.test/login/cas` | Service ID phải khớp chính sách CAS |
| **Service Ticket (ST)** | CAS Server | Chứng từ opaque để ứng dụng đổi lấy kết quả xác minh | Ràng buộc một service, TTL ngắn, **một lần validation** |
| **Ticket-Granting Ticket (TGT)** | CAS Server | Đại diện phiên SSO tại CAS, cho phép cấp nhiều ST | Không phải ST; không gửi vào `/login/cas` |
| **Ticket-Granting Cookie (TGC)** | Cookie thuộc domain CAS | Trình duyệt cho CAS nhận ra SSO session/TGT | Không phải cookie session của ứng dụng |
| **HttpSession/JSESSIONID** | Ứng dụng Spring | Phiên đăng nhập local sau khi ST đã được xác minh | Khác CAS SSO session; có vòng đời riêng |
| **Proxy Ticket (PT)** | CAS Server | Service trung gian gọi downstream service thay người dùng | Cần profile proxy/validator và chính sách tin cậy riêng |
| **Proxy-Granting Ticket (PGT)** | CAS Server | Cho phép service được cấp PT | Không phải ST; cần proxy callback/cơ chế giữ PGT |
| **CAS assertion** | Kết quả TicketValidator | Thông tin xác thực CAS và attributes được CAS xác nhận | Chỉ đáng tin sau khi validator chấp nhận |
| **Spring Authentication** | Spring Security | Principal + authorities + authenticated state trong ứng dụng | Phải đến từ provider đã kiểm ticket và local policy |

**Ticket không phải user ID.** Một chuỗi như `ST-opaque-abc` không nên được giải mã/parse để suy ra username, tenant hay quyền. Nó là **credential dùng một lần** phải được gửi đến CAS Server để validation.

**CAS Protocol khác OIDC/SAML**: ST không phải JWT access token hoặc OIDC ID Token, và `ticket` query parameter không phải `SAMLResponse`. Một CAS Server có thể cũng hỗ trợ OIDC/SAML, nhưng luồng trong bài là **CAS protocol service ticket**.

### 2.1. Ba trạng thái phiên tồn tại độc lập

~~~text
Trình duyệt
  |
  +-- cookie CAS TGC -> CAS Server giữ SSO session/TGT
  |
  +-- cookie JSESSIONID -> Spring app giữ local session
  |
  +-- callback ticket ST -> đổi đúng một lần tại CAS validation endpoint
~~~

Sau khi ST được xác minh, ứng dụng thường giữ Authentication trong local session. **Ứng dụng không nên giữ ST như một “mật khẩu đăng nhập” để tái xác minh mỗi request**. CAS Server có thể còn phiên TGT sau khi local session kết thúc, nên người dùng quay lại ứng dụng có thể được CAS cấp **ST mới** mà không nhập lại mật khẩu.

## 3. Luồng CAS Service Ticket end-to-end

Ví dụ hệ thống:

~~~text
CAS Server:  https://sso.example.test/cas
CAS login:   https://sso.example.test/cas/login
CAS validate:https://sso.example.test/cas/serviceValidate
SP service:  https://portal.example.test/login/cas
~~~

Sơ đồ:

~~~text
Browser                        Spring Security app                    CAS Server
   |                                  |                                   |
   | GET /private                     |                                   |
   |--------------------------------->|                                   |
   |                                  | ExceptionTranslationFilter        |
   |                                  |   -> CasAuthenticationEntryPoint  |
   |<---------------------------------| 302 CAS /login?service=<SP service>
   |---------------------------------------------------------------------->|
   |                                  |                                   | xác thực
   |                                  |                                   | bằng tài khoản
   |<----------------------------------------------------------------------|
   | 302 https://portal.example.test/login/cas?ticket=ST-opaque-abc        |
   |--------------------------------->|                                   |
   |                                  | CasAuthenticationFilter            |
   |                                  | lấy request parameter ticket        |
   |                                  | tạo authentication request          |
   |                                  | AuthenticationManager               |
   |                                  |    -> CasAuthenticationProvider     |
   |                                  |           -> TicketValidator        |
   |                                  |----------------------------------->|
   |                                  | GET /serviceValidate               |
   |                                  | ?service=<exact-SP-service>         |
   |                                  | &ticket=<opaque-ST>                 |
   |                                  |<-----------------------------------|
   |                                  | CAS serviceResponse XML             |
   |                                  |  SUCCESS: user + attributes         |
   |                                  |  FAILURE: reason                    |
   |                                  | nạp user + authorities local        |
   |                                  | tạo CasAuthenticationToken          |
   |                                  | lưu SecurityContext theo config     |
   |<---------------------------------| redirect tới trang trước đó        |
   | GET /private                     |                                   |
   |--------------------------------->| authorize user theo app policy     |
~~~

**Hai đường đi khác nhau:**

- **Browser redirect** đến CAS `/login` và trở về service URL mang `ticket`.
- **Server-to-server ticket validation** từ ứng dụng đến CAS `/serviceValidate` hoặc endpoint CAS profile tương thích, dùng HTTPS.

**Không tin callback chỉ vì browser được redirect từ CAS**. Browser có thể tự gọi `/login/cas?ticket=...`; việc xác minh server-to-server và ràng buộc service mới xác định giá trị ticket.

### 3.1. Khi chưa đăng nhập

Spring Security `ExceptionTranslationFilter` chuyển yêu cầu xác thực chưa đáp ứng tới **CasAuthenticationEntryPoint**. Entry point xây URL CAS Login dựa trên:

- URL đăng nhập CAS Server, ví dụ `https://sso.example.test/cas/login`.
- `ServiceProperties.service` xác định nơi CAS chuyển về, ví dụ `https://portal.example.test/login/cas`.
- Tùy cấu hình `renew` hoặc `gateway`, hành vi SSO/đòi nhập lại mật khẩu khác nhau.

Ví dụ redirect:

~~~text
HTTP/1.1 302 Found
Location: https://sso.example.test/cas/login?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
~~~

**service ở query trên phải được URL-encode**, nhưng giá trị sau khi decode phải đại diện đúng service đã đăng ký. Không tự ghép dấu `?`/`&` hoặc normalize host/path theo cảm tính.

### 3.2. Khi CAS xác thực thành công

CAS Server thiết lập/đọc SSO session của chính CAS, cấp một **ST chỉ dành cho service đã nêu** và redirect:

~~~text
HTTP/1.1 302 Found
Location: https://portal.example.test/login/cas?ticket=ST-opaque-abc
~~~

`ST-opaque-abc` là **giá trị minh họa, không phải ticket hợp lệ**. Ticket thực được CAS tạo ngẫu nhiên và không được đoán được.

### 3.3. Khi Spring nhận callback

`CasAuthenticationFilter` mặc định theo dõi **/login/cas**. Nó phát hiện request đến đường đó, đọc `ticket` và tạo **Authentication chưa được xác minh** để chuyển cho `AuthenticationManager`.

- `ticket` là credential tạm thời của yêu cầu xác thực.
- `principal` ban đầu là **dấu hiệu CAS-specific/stateful identifier** của filter/provider, **chưa phải user thực**.
- Chỉ sau khi CAS Server xác minh thành công, provider mới có kết quả user/attributes và nạp quyền trong ứng dụng.
- `AuthenticationManager` cần có **CasAuthenticationProvider** nhận biết loại authentication request.

Không viết controller `@GetMapping("/login/cas")` để lấy `ticket` và tự trả về tên user. Đó là việc của security filter chain/protocol client.

## 4. CasAuthenticationFilter làm gì và không làm gì?

**CasAuthenticationFilter** là một **`AbstractAuthenticationProcessingFilter`** của Spring Security. Với browser stateful CAS:

1. Chỉ xử lý request khớp **filterProcessesUrl** được cấu hình, mặc định **/login/cas**.
2. Lấy `ticket` từ request parameter.
3. Tạo authentication request đánh dấu CAS ticket.
4. Gọi `AuthenticationManager.authenticate(...)`.
5. Trên thành công, áp dụng session strategy/success handler và lưu **SecurityContext** qua `SecurityContextRepository` đã cấu hình phù hợp.
6. Trên thất bại, chuyển qua failure handler; không tạo phiên authenticated.
7. Nếu có request cache, có thể đưa người dùng trở lại tài nguyên ban đầu.

**Không phải trách nhiệm riêng của filter:**

- Xác minh ticket bằng việc so chuỗi ST hoặc đọc tiền tố `ST-`.
- Tự liên hệ CAS Server nếu không có provider/validator được nối đúng.
- Tin các tham số `username`, `roles`, `tenant` do browser gửi kèm callback.
- Xác minh proxy chain hay service ticket lifecycle mà không có CAS validator.
- Cấp quyền nghiệp vụ cho người dùng chỉ vì CAS trả username.
- Tự đăng xuất đồng thời CAS SSO/TGT hay các ứng dụng khác.

### 4.1. Khác biệt API theo phiên bản Spring Security

**Chú ý khi đối chiếu tài liệu:** một số đoạn trong trang hướng dẫn CAS Spring Security có nguồn gốc từ các phiên bản cũ và mô tả `UsernamePasswordAuthenticationToken` với principal đặc biệt **`CAS_STATEFUL_IDENTIFIER`**. Tuy nhiên Javadoc **Spring Security 7.x hiện hành** mô tả `CasAuthenticationFilter` tạo **`CasServiceTicketAuthenticationToken`** với `CasServiceTicketAuthenticationToken.CAS_STATEFUL_IDENTIFIER`, và `CasAuthenticationProvider` nhận loại token đó.

Bảng đối chiếu:

| Tài liệu / phiên bản | Mô tả request token | Điều cần làm |
| --- | --- | --- |
| Hướng dẫn CAS cũ / các phiên bản trước khi thay đổi API | `UsernamePasswordAuthenticationToken` dùng CAS-specific principal | Xem đúng Javadoc của phiên bản dự án |
| Javadoc Spring Security 7.x | `CasServiceTicketAuthenticationToken` dùng CAS-specific principal | Sử dụng filter/provider tương thích cùng bản |
| Kết quả xác thực thành công | `CasAuthenticationToken` chứa assertion và authorities | Không tự coi request token ban đầu là đã authenticated |

**Không hard-code một request token class từ tài liệu cũ rồi bắt provider mới phải nhận nó.** Sử dụng API/filter/provider từ **cùng bộ phiên bản Spring Security**, và kiểm tra integration tests sau nâng cấp.

Nguồn: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html và https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html .

## 5. ServiceProperties: hợp đồng URL quan trọng nhất

Một trong các lỗi triển khai thường gặp nhất là **service URL không khớp** giữa lúc CAS phát ST và lúc ứng dụng xác minh ST.

Ví dụ cấu hình đúng:

~~~text
ServiceProperties.service
  = https://portal.example.test/login/cas

CasAuthenticationFilter.filterProcessesUrl
  = /login/cas

CAS service registry
  cho phép https://portal.example.test/login/cas

CAS /login?service=...
  yêu cầu service này

CAS /serviceValidate?service=...
  dùng đúng service này
~~~

**CAS Protocol ràng buộc ST với service mà ticket được phát cho.** CAS Server phải kiểm tra ticket được gửi đến đúng service khi xác minh. Một ST phát cho `https://portal.example.test/login/cas` **không được** xác thực thành công với `https://reports.example.test/login/cas`.

### 5.1. Exact match và normalization

Các URL sau có thể **khác nhau** ở mức service identity:

~~~text
https://portal.example.test/login/cas
https://portal.example.test/login/cas/
http://portal.example.test/login/cas
https://portal.example.test:8443/login/cas
https://portal.internal:8080/login/cas
~~~

Cần đối chiếu với **CAS service matching policy**: đặc tả CAS mô tả service comparison rõ ràng, nhưng một số sản phẩm triển khai custom matching/normalization theo service registry. Để an toàn, **không dựa vào sự khoan dung không được cam kết**: cố định một URL HTTPS public và dùng xuyên suốt CAS login/validation/filter.

**Service URL dùng cho validation không bao gồm `ticket` query parameter mới nhận**, trừ khi profile/service identity đã thiết kế đặc biệt. Đừng sử dụng toàn bộ callback URL bao gồm `?ticket=ST-...` như một service mới, vì nó sẽ không khớp service lúc phát ticket.

### 5.2. Reverse proxy và SSL termination

Ứng dụng Java có thể chạy trên:

~~~text
Public: https://portal.example.test/login/cas
Ingress: https://edge.example.test -> http://app:8080
Internal servlet path: /login/cas
~~~

`ServiceProperties.service` cần là **public service URL đã được CAS đăng ký**, không phải `http://app:8080/login/cas`. Nếu app đặt dưới context path `/portal`, service phải phản ánh path thật, ví dụ `https://portal.example.test/portal/login/cas`.

- Cấu hình `X-Forwarded-Proto`, `X-Forwarded-Host` hoặc Forwarded Header chỉ từ **proxy đã tin cậy**.
- Không dùng một request `Host` do client tự điều khiển để quyết định `service` tùy ý.
- CAS service registry nên dùng allowlist chính xác hoặc pattern đủ chặt, **không cho phép mọi HTTPS URL chỉ để dễ test**.
- Test `service` URL của cả redirect login và request validation thực tế bằng instrumentation **đã che ticket**.

## 6. Ticket validation là bước quyết định tin cậy

`CasAuthenticationProvider` dùng **`TicketValidator`** của CAS Java client để gửi yêu cầu xác minh ticket đến CAS Server. Với CAS 2.0, ví dụ endpoint:

~~~text
GET https://sso.example.test/cas/serviceValidate
    ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
    &ticket=ST-opaque-abc
~~~

Với CAS 3.x cần user attributes, máy chủ có thể cung cấp **/p3/serviceValidate** và một validator tương thích (chẳng hạn **Cas30ServiceTicketValidator** trong Apereo CAS Java client). Không trộn validator 2.0, 3.0, JSON/XML hoặc proxy validator một cách tự phát; kiểm thử cùng server/version thực tế.

**Quan trọng:** việc gửi request validation đến CAS Server phải dùng **TLS được xác minh chuẩn** (certificate chain/hostname, không bỏ SSL verification). Nếu một kẻ tấn công điều khiển response của TicketValidator, ứng dụng có thể bị gán danh tính giả. Chỉ coi **kết quả thành công từ CAS endpoint tin cậy** là đầu vào để tạo Authentication.

### 6.1. Ví dụ serviceValidate thành công

CAS Protocol 2.0 trả XML như sau (giản lược):

~~~xml
<cas:serviceResponse
    xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-42</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Đây là **mẫu cấu trúc trả về**, không phải response từ server thật. Nếu triển khai CAS 3.0 có attributes, `/p3/serviceValidate` có thể trả thêm:

~~~xml
<cas:serviceResponse
    xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-42</cas:user>
    <cas:attributes>
      <cas:employeeNumber>E-0042</cas:employeeNumber>
      <cas:department>engineering</cas:department>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Attributes được release phụ thuộc **CAS server attribute repository + service registry attribute release policy**. Không mặc định mọi ứng dụng luôn nhận đủ group, email, department hoặc subject ổn định.

### 6.2. Ví dụ validation thất bại

~~~xml
<cas:serviceResponse
    xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    The service did not match the issued ticket.
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

Ngoài **INVALID_SERVICE**, có thể gặp:

| Mã/tình huống | Ý nghĩa chính | Xử lý |
| --- | --- | --- |
| **INVALID_TICKET** | Ticket không tồn tại, hết hạn, đã dùng hoặc không phù hợp | Từ chối, bắt đầu luồng login mới |
| **INVALID_SERVICE** | Service đã gửi đến validation không khớp service phát ticket | Từ chối; sửa service URL/registry |
| **INTERNAL_ERROR** | CAS Server gặp lỗi khi xác minh | Fail closed; monitoring/retry flow phù hợp |
| TLS/timeout | Ứng dụng không gọi được CAS Server tin cậy | Fail closed; không offline-trust ticket |
| XML/JSON parse error | CAS response không tương thích validator hoặc hỏng | Fail closed; sửa profile/version |
| User disabled/no local mapping | CAS xác minh identity nhưng ứng dụng không cho phép truy cập | Không tạo Authentication có quyền nghiệp vụ |

**Không đưa raw XML, ticket, cookie TGC hoặc SSO identifiers lên public logs** để debug; dùng correlation ID, service URL không có ticket, HTTP status và mã lỗi đã lọc.

### 6.3. CAS xác minh service chứ không phải Spring tự suy người dùng

Một response **authenticationSuccess** của CAS có thể cung cấp username, authentication date, attributes và proxy chain. `CasAuthenticationProvider` sau đó dùng **UserDetailsService/AuthenticationUserDetailsService** để lấy **GrantedAuthority** hoặc user record nội bộ theo policy. Nếu tài khoản local bị khóa hoặc không được phép dùng ứng dụng, login vẫn phải từ chối dù CAS đã xác minh ST hợp lệ.

**CAS xác thực “người này là ai theo CAS”; ứng dụng vẫn quyết định “được làm gì trong dịch vụ này”.** Không map arbitrary group thành admin authority nếu chưa có allowlist/authorization policy.

## 7. Một Service Ticket chỉ được xác minh một lần

Theo đặc tả CAS:

- ST được cấp **cho một service**.
- ST **phải chỉ có hiệu lực cho một lần validation attempt**, kể cả nếu validation không thành công.
- ST chưa sử dụng phải có TTL ngắn và hết hạn sau giới hạn do CAS Server quản lý.
- Ticket cần có entropy đủ cao, không thể đoán.

Ví dụ:

~~~text
CAS cấp ST-001 cho service A.

A validate(ticket=ST-001, service=A) -> SUCCESS, ticket bị tiêu thụ.
A validate(ticket=ST-001, service=A) lần nữa -> INVALID_TICKET.

CAS cấp ST-002 cho service A.
B validate(ticket=ST-002, service=B) -> INVALID_SERVICE, ticket bị tiêu thụ.
A cố dùng lại ST-002 -> INVALID_TICKET.

CAS cấp ST-003 cho service A.
Ticket hết hạn trước khi validate -> INVALID_TICKET.
~~~

**Không cache ST như một session credential phía ứng dụng.** Sau validation thành công, Spring nên giữ **SecurityContext/HttpSession**, không cần validation lại ticket cho từng request stateful. Không “retry 3 lần cùng ST” khi CAS trả INVALID_SERVICE; lỗi đầu tiên có thể đã tiêu thụ ST, cách đúng là sửa service URL và **khởi tạo login mới để lấy ticket mới**.

### 7.1. Ticket bị lộ ở query string có nguy hiểm không?

Có. ST là bearer-style credential trong cửa sổ thời gian ngắn **trước khi được validate**. Nếu ticket bị lộ qua browser history, referrer, proxy log hoặc analytics trước khi ứng dụng xác minh, attacker có thể thử sử dụng nó với **service mà ticket được phát cho**.

Biện pháp:

- Chỉ dùng HTTPS từ CAS đến browser và đến service.
- Thiết lập **Referrer-Policy: no-referrer** hoặc chính sách tương đương trên callback/vùng nhạy cảm; kiểm soát redirect.
- **Redact `ticket` từ access logs, reverse proxy, APM, traces, error reporting**.
- Giới hạn script/third-party assets trên trang callback.
- Không truyền ST vào JavaScript/frontend state hoặc lưu persistent storage.
- Sau login thành công, điều hướng đến URL sạch không có ticket khi phù hợp.
- Không dùng ST làm token API lâu dài.

Ticket dùng một lần giúp giảm thời gian tái sử dụng nhưng **không xóa mọi rủi ro race trước validation**.

## 8. Vai trò các Spring Security components

| Thành phần | Trách nhiệm | Sai lầm thường gặp |
| --- | --- | --- |
| **CasAuthenticationEntryPoint** | Bắt đầu CAS login redirect khi tài nguyên yêu cầu xác thực | Đặt CAS login URL sai hoặc chuyển đến /login/cas trực tiếp |
| **ServiceProperties** | Khai service identity và tùy chọn renew/authenticateAllArtifacts | Service khác với URL public/filter path |
| **CasAuthenticationFilter** | Nhận ticket callback và tạo authentication request | Tưởng ticket có trong URL là user đã đăng nhập |
| **AuthenticationManager** | Điều phối provider phù hợp | Quên khai provider xử lý CAS ticket token |
| **CasAuthenticationProvider** | Gọi TicketValidator, load UserDetails, tạo kết quả xác thực | Trộn CAS server/tenant hoặc trust thông tin browser |
| **TicketValidator** | Liên hệ CAS Server để xác minh ticket, service, trả assertion | Bỏ TLS validation, dùng sai endpoint CAS version |
| **UserDetailsService** | Ánh xạ CAS username sang local account và authorities | Tự cấp ROLE_ADMIN từ query/attribute chưa được duyệt |
| **SecurityContextRepository** | Giữ Authentication giữa các request stateful | Filter thành công nhưng không lưu session |
| **AuthenticationSuccessHandler** | Chuyển người dùng về requested resource/URL phù hợp | Open redirect hoặc để ST tiếp tục nằm trong URL |
| **AuthenticationFailureHandler** | Hiển thị lỗi và không tạo phiên authenticated | Tiết lộ raw ticket/validation details cho browser |

Tách rạch ròi **redirect, ticket validation, session persistence, local authorization** giúp debug chính xác: một HTTP 302 tới CAS chưa có nghĩa auth thành công; một XML CAS success chưa có nghĩa user được quyền vào mọi resource.

## 9. Spring Security 7.x: cấu hình Java minh họa đầy đủ các điểm nối

Spring Security cung cấp module **spring-security-cas**. Ví dụ cấu hình sau mô tả ứng dụng Servlet dùng **CAS Service Ticket stateful** với Spring Security 7.x và API Java hiện hành. Đây là **class trong một dự án Spring Boot có đầy đủ dependencies và UserDetailsService**; không phải file Java chạy bằng JDK thuần.

### 9.1. Dependency

Tệp `build.gradle` (Groovy DSL), giả sử dự án đã dùng Spring Boot dependency management tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Không tự chọn version CAS Client/Spring Security rời rạc.** CAS support/Apereo Java CAS Client thường được resolve theo dependency graph; với Spring Boot BOM, phải kiểm tra **version compatibility thực tế** và package classes trong dự án. Một số API thay đổi giữa Spring Security 5/6/7 như kiểu token và Jakarta Servlet package. Đoạn code dưới nhắm cách dùng API đã tài liệu hóa cho phiên bản 7.x; hãy chạy compile/integration test trên đúng version của tổ chức trước production.

### 9.2. Security configuration

Tệp `CasSecurityConfig.java`:

~~~java
package com.example.portal.security;

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
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class CasSecurityConfig {
    private static final String CAS_BASE =
        "https://sso.example.test/cas";
    private static final String SERVICE =
        "https://portal.example.test/login/cas";

    @Bean
    ServiceProperties casServiceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService(SERVICE);
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties casServiceProperties,
            UserDetailsService userDetailsService) {
        CasAuthenticationProvider provider = new CasAuthenticationProvider();
        provider.setKey("portal-cas-provider-v1");
        provider.setServiceProperties(casServiceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(CAS_BASE));
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain casSecurityFilterChain(
            HttpSecurity http,
            ServiceProperties casServiceProperties,
            CasAuthenticationProvider casAuthenticationProvider)
            throws Exception {
        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(CAS_BASE + "/login");
        entryPoint.setServiceProperties(casServiceProperties);

        CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setServiceProperties(casServiceProperties);
        casFilter.setAuthenticationManager(
            new ProviderManager(casAuthenticationProvider));
        casFilter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        casFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .authenticationProvider(casAuthenticationProvider)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .addFilterAt(casFilter, CasAuthenticationFilter.class);
        return http.build();
    }
}
~~~

### 9.3. Đọc code theo trách nhiệm

- **ServiceProperties.setService**: service public HTTPS cố định được CAS Server đăng ký và là URL callback được filter xử lý.
- **setSendRenew(false)**: ví dụ cho phép dùng CAS SSO session hiện có. Nếu hệ thống yêu cầu người dùng xác thực lại bằng thông tin đăng nhập chính, cần thiết kế `renew` đúng cả login và validation.
- **CasAuthenticationEntryPoint**: redirect đến `CAS_BASE + "/login"` kèm service.
- **Cas20ServiceTicketValidator**: thực thi CAS 2.0 ticket validation theo server base URL. Nếu cần CAS 3 attributes, phải dùng validator/profile tương thích; không chỉ thay tên endpoint bằng tay.
- **CasAuthenticationProvider.setKey**: định danh nội bộ của provider/token theo contract, **không phải cryptographic secret hoặc private key của CAS**.
- **setUserDetailsService**: loader tài khoản nội bộ. Ứng dụng phải cung cấp bean `UserDetailsService` thực và policy quyền; ví dụ không tự tạo username/password mẫu.
- **CasAuthenticationFilter.setFilterProcessesUrl**: đảm bảo callback là **/login/cas** và phù hợp với đường dẫn của service.
- **setAuthenticationManager(new ProviderManager(...))**: nối filter với provider xử lý CAS; không chỉ đăng ký provider bean rồi giả định filter tìm được.
- **setSecurityContextRepository**: lưu SecurityContext vào session khi xác thực thành công. Javadoc filter hiện hành lưu ý repository mặc định không nhất thiết lưu context; vì vậy cấu hình stateful nên rõ ràng.
- **setSessionAuthenticationStrategy**: dùng session ID rotation trên login để giảm session fixation; chọn theo cấu hình thực tế.
- **addFilterAt**: gắn filter vào Spring Security filter chain, không gọi `CasAuthenticationFilter` trực tiếp từ controller.

**Giới hạn của ví dụ:** đây là cấu hình tối giản để học đường đi ST, không bao gồm service registry phía CAS, logout/SLO, reverse proxy, deployment TLS, health endpoints, resource authorization, password management và testing. Kiểm tra **một số package/method có thay đổi theo Spring Security 6.x/7.x**, đặc biệt khi phiên bản mới yêu cầu cấu hình khác cho `SecurityContextRepository`. Tránh dùng code trên như sản phẩm hoàn chỉnh khi chưa chạy integration tests.

### 9.4. Lưu ý tránh filter chạy hai lần

Spring Boot có thể tự đăng ký một `jakarta.servlet.Filter` bean với Servlet container **ngoài** security filter chain nếu bạn khai nó như một bean Filter thông thường. Vì vậy ví dụ trên **tạo CasAuthenticationFilter bên trong method SecurityFilterChain**, không khai `@Bean CasAuthenticationFilter` riêng để vô tình tạo hai registration. Nếu ứng dụng thật cần Filter bean riêng, hãy kiểm soát Servlet `FilterRegistrationBean`/security chain order rõ ràng.

### 9.5. Nơi dành cho success/failure handlers

`CasAuthenticationFilter` kế thừa cấu hình success/failure từ `AbstractAuthenticationProcessingFilter`. Trong ứng dụng thật có thể:

- Dùng **SavedRequestAwareAuthenticationSuccessHandler** để trả người dùng về tài nguyên yêu cầu ban đầu.
- Dùng failure handler đưa đến trang lỗi tương thích CAS, không tiết lộ ticket.
- Ngăn open redirects, kiểm `defaultTargetUrl` và request cache.
- Đặt đúng security headers, cookie policy và logging filters để không làm lộ `ticket`.
- Kiểm nếu app dùng nhiều SecurityFilterChain thì filter có nằm trong chain nhận `/login/cas` hay không.

## 10. Cấu hình CAS Server: đăng ký service

CAS Server thường có **service registry** xác định dịch vụ nào được phép xác thực. Ví dụ thông tin hợp đồng cần thống nhất:

~~~text
CAS base:           https://sso.example.test/cas
CAS login:          https://sso.example.test/cas/login
CAS validation:     https://sso.example.test/cas/serviceValidate
Registered service: https://portal.example.test/login/cas
Service owner:      Portal Engineering
Allowed protocol:   CAS 2.0 Service Ticket
User attributes:    username; optional employeeNumber
Transport:          HTTPS only
~~~

Bên CAS Server có thể lưu registered service bằng JSON/YAML/database; **không có một file cấu hình chung áp dụng cho mọi bản CAS**. Không sửa service registry trên production chỉ theo một ví dụ, và không mở pattern kiểu `.*` vô điều kiện.

### 10.1. Vì sao CAS Server cần allowlist?

Nếu CAS cho phép bất kỳ service URL nào, attacker có thể dụ CAS redirect browser đến endpoint do attacker kiểm soát hoặc tận dụng service registry mở để lấy ticket trong bối cảnh lừa đảo. CAS Protocol khuyến nghị quản lý dịch vụ được phép và ưu tiên HTTPS.

Đăng ký service theo:

- Đúng public scheme `https`.
- Host/path nằm trong miền service chủ quản.
- Metadata owner, môi trường dev/UAT/prod và callback cụ thể.
- Attribute release policy theo từng service.
- Giới hạn các thuộc tính nhạy cảm, quyền audit và lịch sử thay đổi.
- Không để service regex chứa wildcard host/path quá rộng.

### 10.2. Không gửi mật khẩu và TGT đến ứng dụng

SP/service chỉ nhận **ST** rồi đổi lấy assertion. Browser có thể giữ **TGC** thuộc domain CAS; Spring app không nên đọc cookie TGC hoặc lưu TGT. Một lỗi kiến trúc là yêu cầu CAS Server “gửi mật khẩu user” về application để lập session. CAS federation nhằm giảm các dịch vụ phải trực tiếp quản lý mật khẩu.

## 11. UserDetails, CAS attributes và local authorization

Sau khi CAS xác minh ST, provider có thể lấy username và attributes:

~~~text
CAS response:
  user            = employee-42
  employeeNumber  = E-0042
  department      = engineering

Local application:
  externalIdentity = (CAS issuer/service, employee-42)
  userId           = 865bb18a...
  enabled          = true
  tenant           = business-a
  roles            = [ROLE_REPORT_READER]
~~~

`employee-42` chỉ là mẫu. Đừng mặc định `cas:user` toàn cầu độc nhất qua mọi CAS realm/tenant nếu hệ thống có nhiều CAS Server. Có thể cần scope theo **CAS provider / tenant / realm + subject** để tránh gộp người dùng có cùng chuỗi username.

**UserDetailsService không phải ticket validator.** Nó chạy **sau khi xác minh CAS**, phục vụ mapping tài khoản, trạng thái enabled/locked và authorities. Nếu ứng dụng chọn nạp user từ database:

- Từ chối tài khoản bị khóa/đã thôi quyền.
- Dùng stable external ID nếu CAS cung cấp; thỏa thuận xử lý rename/reuse username.
- Không tạo user/tenant role chỉ vì browser tự gửi `department=admin`.
- CAS attributes nếu được dùng để cấp quyền phải có allowlist, contract/issuer scope và audit.
- Kiểm quyền dữ liệu trong API local, không suy rằng người dùng đã được CAS xác thực sẽ được đọc mọi tài nguyên.

### 11.1. CAS 2.0 và CAS 3.0 attributes

CAS 2.0 `/serviceValidate` trả success XML với `user`. CAS 3 `/p3/serviceValidate` hỗ trợ trả attributes theo service policy. Nếu ứng dụng cần attributes mà không thấy:

1. Kiểm **validator** có dùng CAS 3 profile tương thích không (ví dụ Cas30ServiceTicketValidator).
2. Kiểm **CAS Server attribute repository** có chứa dữ liệu không.
3. Kiểm **registered service attribute release policy** có cho gửi thuộc tính đó không.
4. Kiểm `AuthenticationUserDetailsService`/custom mapping đã đọc assertion phù hợp chưa.
5. Không chuyển sang đọc user roles từ query `/login/cas?role=admin` để thay thế.

## 12. Stateful Service Ticket và Proxy Ticket là hai chế độ khác nhau

### 12.1. Browser stateful authentication

Trường hợp bài học:

~~~text
Browser GET /login/cas?ticket=ST-...
CasAuthenticationFilter
   -> stateful authentication request
   -> CAS Service Ticket Validator
   -> local SecurityContext/HttpSession
~~~

Sau khi đăng nhập, các HTTP requests tiếp theo dựa trên **local session**. Không gửi ST trên mỗi request. `ServiceProperties.authenticateAllArtifacts` thường **không cần bật** trong mô hình stateful callback một URL.

### 12.2. Stateless/proxy authentication

CAS cũng có cơ chế **Proxy Ticket** cho service A gọi service B thay mặt người dùng:

~~~text
User -> Service A (đã CAS-authenticated)
Service A -> CAS /proxy (dùng PGT hợp lệ)
CAS -> PT dành cho Service B
Service A -> Service B?ticket=PT-...
Service B -> CAS /proxyValidate?ticket=PT-...&service=B
~~~

Đây là phần nâng cao **không bắt buộc** cho Service Ticket login. Spring Security Javadoc nêu `CasAuthenticationFilter` có thể xử lý proxy tickets trên nhiều URL khi:

- `ServiceProperties.authenticateAllArtifacts = true`.
- Dùng `ServiceAuthenticationDetailsSource` để xây **service URL hiện tại** đúng cho validation.
- Provider dùng **proxy ticket validator**, ví dụ `Cas20ProxyTicketValidator`, và cấu hình proxy chain policy.
- Có `StatelessTicketCache` phù hợp khi giao thức không giữ HttpSession, với giới hạn bảo mật chặt.

**Không bật authenticateAllArtifacts=true theo thói quen.** Nó khiến filter có thể xem các artifact trên nhiều URL, tăng rủi ro xử lý ticket sai bối cảnh. Nếu chỉ là một ứng dụng web đăng nhập qua CAS, **stateful ST và /login/cas thường đủ**.

### 12.3. Proxy chain phải giới hạn nguồn

Trong các ví dụ cũ có thể thấy `acceptAnyProxy=true`. Điều đó có thể phù hợp lab nhưng **không an toàn như mặc định production**. Khi sử dụng proxy authentication:

- Chỉ cho phép **proxies thuộc danh sách đã duyệt**.
- Xác minh HTTPS proxy callback/PGT đúng quy trình.
- Giới hạn nơi PT có thể sử dụng và TTL.
- Kiểm soát `StatelessTicketCache` và key/cách hết hạn.
- Đừng nhầm PT với ST: một service chỉ muốn browser ST không nên tự chấp nhận PT.

## 13. renew, gateway và authenticateAllArtifacts

Ba tùy chọn này có mục đích khác nhau:

| Tùy chọn | Ý nghĩa | Cần cẩn trọng |
| --- | --- | --- |
| **renew=true** khi CAS login | Yêu cầu xác thực bằng primary credentials thay vì chỉ sử dụng SSO session sẵn có | Không đồng nghĩa MFA hoặc mọi bước reauth, phụ thuộc CAS policy |
| **gateway=true** | Không tương tác đăng nhập; nếu chưa có SSO, có thể quay lại không kèm ticket | Phải xử lý callback không có ticket; không đánh dấu authenticated |
| **authenticateAllArtifacts=true** phía Spring | Cho filter xử lý ticket/proxy artifacts ở URL khác filterProcessesUrl | Cần service URL details và proxy validator; không bật cho ST stateful đơn giản |

CAS Protocol quy định **renew và gateway không nên được kết hợp**; nếu sử dụng cần theo đúng tài liệu CAS Server. Nếu gateway không trả ticket, ứng dụng phải tiếp tục xử lý như **chưa xác thực**, không tin query `gateway` hoặc fallback vào anonymous user với quyền lớn hơn.

## 14. Java 17 độc lập: mô phỏng Service Ticket dùng một lần và ràng buộc service

Chương trình sau chạy với **JDK 17+**, không cần CAS Server/Spring dependency. Nó mô phỏng **phía CAS Server** với một ticket registry in-memory để minh họa:

- Ticket được cấp cho **một service cụ thể**.
- Đúng ticket + đúng service + chưa quá TTL → trả principal đã được registry xác nhận.
- Một validation attempt **consume** ticket; lần tiếp theo từ chối.
- Sai service, service URL khác dấu `/`, ticket hết hạn hoặc thiếu ticket → từ chối.
- Browser gửi một `user=admin` giả không thể quyết định username; chỉ kết quả từ registry/validator là input trusted.

**Giới hạn quan trọng:** `FakeCasServer` **không phải CAS Server**, không dùng cryptographic authentication, HTTPS, HTTP protocol, CAS XML, Spring Security hoặc CAS Java Client. `validate` trong bài giả lập **chỉ để học cơ chế one-time/service binding**, không thay thế một CAS TicketValidator production. Đừng cho browser tự gọi phương thức này với registry do browser cấp. Toàn bộ dữ liệu ticket là dữ liệu giả trong chương trình.

Tệp **CasServiceTicketLifecycleDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class CasServiceTicketLifecycleDemo {
    record Ticket(String value, String service, String username, Instant issuedAt) {}
    record Validation(boolean success, String username) {
        static Validation rejected() { return new Validation(false, ""); }
    }

    static final class FakeCasServer {
        private final Map<String, Ticket> issued = new ConcurrentHashMap<>();
        private final Set<String> allowedServices = Set.of(
            "https://portal.example.test/login/cas",
            "https://reports.example.test/login/cas");
        private final Duration ttl = Duration.ofSeconds(30);

        void issue(String ticket, String service, String username, Instant now) {
            if (!allowedServices.contains(service)) {
                throw new IllegalArgumentException("Unregistered service");
            }
            if (issued.putIfAbsent(ticket, new Ticket(
                    ticket, service, username, now)) != null) {
                throw new IllegalArgumentException("Duplicate ticket");
            }
        }

        Validation validate(String presentedTicket,
                            String requestedService, Instant now) {
            if (presentedTicket == null || presentedTicket.isBlank()) {
                return Validation.rejected();
            }
            // Simulates the CAS rule: ST is invalidated after validation attempt.
            Ticket original = issued.remove(presentedTicket);
            if (original == null) return Validation.rejected();
            if (!allowedServices.contains(requestedService)) {
                return Validation.rejected();
            }
            if (!original.service().equals(requestedService)) {
                return Validation.rejected();
            }
            if (now.isBefore(original.issuedAt())
                    || !now.isBefore(original.issuedAt().plus(ttl))) {
                return Validation.rejected();
            }
            return new Validation(true, original.username());
        }
    }

    public static void main(String[] args) {
        final String portal = "https://portal.example.test/login/cas";
        final String reports = "https://reports.example.test/login/cas";
        final Instant started = Instant.parse("2026-01-01T10:00:00Z");
        final FakeCasServer cas = new FakeCasServer();

        cas.issue("ST-opaque-1", portal, "employee-42", started);
        Validation accepted = cas.validate(
            "ST-opaque-1", portal, started.plusSeconds(2));
        System.out.println("serviceTicketAccepted=" + accepted.success());
        System.out.println("trustedUser=" + accepted.username());
        System.out.println("callbackUserIgnored="
            + !"admin-from-query".equals(accepted.username()));
        System.out.println("replayRejected=" + !cas.validate(
            "ST-opaque-1", portal, started.plusSeconds(3)).success());

        cas.issue("ST-opaque-2", portal, "employee-42", started);
        System.out.println("wrongServiceRejected=" + !cas.validate(
            "ST-opaque-2", reports, started.plusSeconds(2)).success());
        System.out.println("mismatchConsumesTicket=" + !cas.validate(
            "ST-opaque-2", portal, started.plusSeconds(3)).success());

        cas.issue("ST-opaque-3", portal, "employee-42", started);
        System.out.println("expiredTicketRejected=" + !cas.validate(
            "ST-opaque-3", portal, started.plusSeconds(31)).success());

        cas.issue("ST-opaque-4", portal, "employee-42", started);
        System.out.println("serviceUrlExact=" + !cas.validate(
            "ST-opaque-4", portal + "/", started.plusSeconds(2)).success());

        cas.issue("ST-opaque-5", reports, "analyst-7", started);
        System.out.println("otherServiceAccepted=" + cas.validate(
            "ST-opaque-5", reports, started.plusSeconds(2)).success());

        System.out.println("missingTicketRejected=" + !cas.validate(
            "", portal, started.plusSeconds(2)).success());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 CasServiceTicketLifecycleDemo.java
java CasServiceTicketLifecycleDemo
~~~

**Stdout chính xác**:

~~~text
serviceTicketAccepted=true
trustedUser=employee-42
callbackUserIgnored=true
replayRejected=true
wrongServiceRejected=true
mismatchConsumesTicket=true
expiredTicketRejected=true
serviceUrlExact=true
otherServiceAccepted=true
missingTicketRejected=true
~~~

**Diễn giải:**

- **serviceTicketAccepted=true**: ticket còn hiệu lực và service đúng.
- **trustedUser=employee-42**: username đến từ **validator/registry**, không phải query do browser tự chọn.
- **callbackUserIgnored=true**: input mạo danh ở callback không xác định principal.
- **replayRejected=true**: ST đã consume không thể tái dùng.
- **wrongServiceRejected=true**: ST của Portal không được chấp nhận cho Reports.
- **mismatchConsumesTicket=true**: một lần thử sai service cũng tiêu thụ ticket.
- **expiredTicketRejected=true**: ST hết TTL bị từ chối.
- **serviceUrlExact=true**: service có trailing slash khác có thể bị từ chối theo matching chính xác.
- **otherServiceAccepted=true**: Reports có thể dùng ST khác cấp riêng cho chính Reports.
- **missingTicketRejected=true**: không có ST thì không được xác thực.

**Không chạy chương trình này như endpoint auth thật.** Nó mô phỏng trạng thái trong memory và không chịu được phân tán, restart, browser redirects, đồng hồ CAS Server hoặc bảo mật TLS. Mục đích là hiểu vì sao **ServiceProperties.service phải đúng** và tại sao ST là **one-use**.

## 15. Tích hợp sản phẩm thật: kiểm thử theo lớp

Trước production, cần kiểm thử end-to-end với một CAS Server thử nghiệm và hai services được đăng ký.

### 15.1. Test kế hoạch thành công

1. Truy cập **https://portal.example.test/private** khi chưa có local session.
2. Xác nhận Spring redirect sang **CAS /login?service=...** với service URL đúng.
3. CAS xác thực và trả browser về **/login/cas?ticket=ST-...**.
4. Spring `CasAuthenticationFilter` nhận callback; `CasAuthenticationProvider` gọi validation endpoint CAS Server.
5. Validation gửi **ticket + đúng service**; CAS trả **authenticationSuccess** và username.
6. Provider nạp `UserDetails`, kiểm enabled/locked, cấp authorities theo policy.
7. Spring lưu **Authentication** và redirect về `/private`; request tiếp theo dựa local session.
8. Vào lại CAS Login ở app khác để kiểm TGT/TGC và tính năng SSO khi được phép.

Không cần xem ticket thật để chứng minh thành công: có thể ghi status và correlation IDs đã hash theo chính sách.

### 15.2. Ma trận negative tests

| Ca | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Callback không ticket | GET /login/cas | Không tạo Authentication |
| Ticket giả | `ticket=ST-fake` | CAS validation từ chối |
| Ticket bị tái sử dụng | ST đã validate xong | CAS trả INVALID_TICKET |
| Sai service URL | CAS cấp cho Portal, validate như Reports | CAS trả INVALID_SERVICE |
| Trailing slash khác | Service đăng ký không có / cuối, validation có / | Fail theo matching policy |
| HTTP thay HTTPS | `service=http://...` khác registered HTTPS | Từ chối, sửa proxy/config |
| Ticket quá hạn | ST hết TTL trước validate | Từ chối và khởi tạo login mới |
| CAS Server timeout | Không thể gọi /serviceValidate | Fail closed; không tạo user |
| TLS certificate CAS sai | Hostname/chain không tin cậy | Fail; không tắt TLS validation |
| CAS XML thiếu authenticationSuccess | Invalid/failure response | Fail, không cố parse username tùy ý |
| CAS response malformed | XML/JSON hỏng hoặc namespace sai | Fail; không bypass parser |
| Service không có trong CAS registry | CAS không chấp nhận service URL | Từ chối theo service registration |
| User local bị disabled | CAS success, app user disabled | Không tạo session authenticated |
| User local không tồn tại | CAS success, không map được user | Từ chối/JIT có chính sách, không tự cấp quyền |
| Callback có `username=admin` | Ticket thuộc employee | Username thật vẫn từ CAS validation |
| Callback có `roles=ADMIN` | CAS không phát role đó | Không cấp ROLE_ADMIN |
| CAS 2 validator nhưng cần CAS 3 attributes | Validator/profile không tương thích | Test phát hiện thiếu attrs, cấu hình đúng |
| Hai CAS realms | Ticket từ CAS A đưa app cấu hình CAS B | Không xác thực bởi CAS B |
| Hai services | ST của Portal đưa vào Reports | Từ chối |
| Proxy ticket đưa vào serviceValidate | PT thay ST | Không chấp nhận theo profile |
| Không bật proxy trust | PT bị dùng ở endpoint khác | Không xử lý như ST stateful |
| Stateless cache sai | Cache trả lại user không đúng scope | Test/chặn trong kiến trúc proxy riêng |
| Filter thiếu AuthenticationManager | Callback đến nhưng provider không chạy | Lỗi cấu hình được phát hiện trước production |
| Filter sai path | /callback thay vì /login/cas | Filter không bắt; sửa service/processing URL |
| Filter nằm sai SecurityFilterChain | /login/cas không thuộc chain CAS | Không xác thực; sửa security matcher/order |
| SecurityContext không lưu | Callback success nhưng request kế tiếp anonymous | Cấu hình stateful repository/session |
| Session fixation | Browser giữ session ID cũ sau login | Session authentication strategy phải đổi ID phù hợp |
| Logout local | App xóa session, CAS TGT vẫn còn | Có thể SSO lại bằng **ST mới**, không coi là dùng lại ST |
| Logout CAS | CAS TGT bị thu hồi | Không tự suy mọi app session đã bị xóa nếu SLO chưa hoạt động |
| Reverse proxy host spoof | Client giả X-Forwarded-Host | Không tạo service URL/callback do attacker quyết định |
| ST xuất hiện trong logs | Proxy log ghi full query | Redact; xử lý sự cố nếu lộ ticket |
| CAS service registry quá rộng | Wildcard cho domain tùy ý | Từ chối onboarding không hợp lệ |

### 15.3. Tách ba lớp lỗi

~~~text
A. Browser không quay về /login/cas:
   CAS login URL, service registry, DNS/TLS, redirect, path.

B. Callback đến nhưng CAS validation thất bại:
   Ticket bị dùng/hết hạn, wrong service, CAS SSL/trust,
   protocol CAS 2/3, validation endpoint/profile.

C. CAS validation success nhưng app vẫn 403/anonymous:
   UserDetails/authorities, SecurityContextRepository,
   session fixation/cookie, SecurityFilterChain/authorization.
~~~

**Đừng chữa lỗi của lớp B bằng cách bypass TicketValidator hoặc “tạo Authentication tạm”.** Cần tìm đúng service, certificate hoặc server compatibility.

## 16. Troubleshooting chi tiết

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra hữu ích |
| --- | --- | --- |
| Redirect loop CAS ↔ app | service URL mismatch khiến ST validation fail | CAS registry, ServiceProperties.service, URL public |
| Browser có ticket nhưng Spring không xác thực | /login/cas sai filterProcessesUrl hoặc filter không ở chain | Filter order, request matcher, path/context |
| INVALID_SERVICE | CAS service phát ST khác service gửi validate | URL scheme/host/port/path/query, proxy |
| INVALID_TICKET ngay lần đầu | ST quá hạn, bị pre-consume, CAS cluster ticket registry không đồng bộ | CAS logs; không tái dùng ST |
| INVALID_TICKET khi refresh | Browser refresh lại callback chứa ST đã dùng | Redirect sạch sau success, không coi refresh là login |
| CAS Server SSLHandshakeException | CA chain/hostname chưa tin | JVM truststore, CAS server cert |
| CAS Server 404 /serviceValidate | Base URL hoặc endpoint sai | CAS2/3 validation profile và context path |
| Java XML parser lỗi | CAS XML không tương thích, proxy/middleware trả HTML | HTTP status, Content-Type, parser, CAS logs |
| CAS success nhưng login fail | userDetailsService không tìm thấy/disabled | Principal mapping, local user state |
| 403 sau CAS success | Authenticated nhưng không có quyền local phù hợp | Authorities mapping/authorization policy |
| Spring Security 7 token mismatch | Code cũ kiểm UsernamePasswordAuthenticationToken | Javadoc v7 CasServiceTicketAuthenticationToken và provider |
| Session không tồn tại sau callback | Không persist SecurityContext, cookie/HttpSession policy | setSecurityContextRepository, session store |
| Only on multi-node | App session không chia sẻ hoặc CAS ticket store không đồng bộ | Spring Session, CAS ticket registry, load balancer |
| Only production | host công khai, context path, trusted headers khác UAT | URL public so với CAS registered service |
| Login yêu cầu mật khẩu mỗi lần | renew=true, CAS TGT hết hạn, browser không gửi TGC | CAS login policy, cookies |
| gateway không có ticket | User chưa có CAS SSO session | Xử lý anonymous đúng profile |
| Nhầm Proxy Ticket với ST | Dùng PT ở /serviceValidate | Proxy validator/config/chính sách proxy |
| CAS logout xong vẫn truy cập app | HttpSession local còn; chưa có Single Logout | Tích hợp CAS SLO/session invalidation riêng |
| Referrer/log chứa ST | Query callback bị ghi bởi web/proxy | Redaction + Referrer-Policy và clean redirect |

### 16.1. Mẫu log an toàn

~~~text
event=CAS_ST_VALIDATION_FAILED
registration=portal-cas-prod
service=https://portal.example.test/login/cas
casEndpoint=https://sso.example.test/cas/serviceValidate
status=INVALID_SERVICE
requestId=trace-7f4e
elapsedMs=132
~~~

**Không ghi `ticket` vào log**, không nhúng nó vào URL của exception hay trace. Username/attributes chỉ nên log khi chính sách và privacy cho phép; log hết `CAS Assertion` có thể làm lộ dữ liệu cá nhân.

### 16.2. Phân biệt CAS auth thành công và local authorization

Một user CAS đã được xác minh có thể vẫn gặp HTTP 403 do không có quyền đọc resource. Cần xem:

- `CasAuthenticationToken.isAuthenticated()` và authorities trong context theo logging được kiểm soát.
- `UserDetailsService` có ánh xạ đúng external subject đến user local không?
- Roles trong DB, tenant membership, application policy có cho truy cập không?
- Có một filter chain khác reset Authentication hay tạo anonymous context không?
- CSRF của POST nghiệp vụ có làm request bị từ chối sau khi login không?

Đừng gán mọi HTTP 403 là CAS service ticket lỗi.

## 17. Security checklist trước khi đi production

- [ ] Đã phân biệt CAS Server, SP/service, ST, TGT/TGC, PT/PGT và application HttpSession.
- [ ] Spring có module **spring-security-cas** tương thích các dependencies/cas-client.
- [ ] CasAuthenticationEntryPoint redirect đúng CAS login URL và gửi **service URL public**.
- [ ] `ServiceProperties.service` đúng **registered service URL** và khớp `filterProcessesUrl` callback.
- [ ] CAS service registry chỉ cho phép HTTPS service hợp lệ, không có wildcard tùy tiện.
- [ ] CasAuthenticationFilter thuộc đúng SecurityFilterChain và có AuthenticationManager phù hợp.
- [ ] CasAuthenticationProvider có TicketValidator gọi **CAS Server đáng tin**.
- [ ] TLS và hostname verification tới CAS validation endpoint **không bị tắt**.
- [ ] Không coi ST là JWT, username, lâu dài session token hoặc dữ liệu có thể đọc từ chuỗi.
- [ ] ST được validate **một lần**, không được cache làm credential, xử lý expiry/replay fail closed.
- [ ] App không tin username/group/tenant do browser gửi tới /login/cas.
- [ ] CAS success chỉ tạo user nếu UserDetails/local policy cho phép; account disabled bị từ chối.
- [ ] SecurityContext được persist bằng repository/session strategy đúng bản Spring.
- [ ] Session ID được đổi khi login thành công theo session fixation policy.
- [ ] Logging/proxy/APM/Referer redacts **ticket query parameter** và CAS Assertion nhạy cảm.
- [ ] Service URL không bị sửa bởi Host/X-Forwarded-Host không tin cậy.
- [ ] Nếu CAS 3 attributes cần thiết, validator/endpoint và attribute release policy đã được test.
- [ ] Không bật authenticateAllArtifacts, proxy validator hoặc acceptAnyProxy khi chỉ cần browser ST.
- [ ] Nếu có proxy ticket, giới hạn trusted proxy chain, PGT storage và cache scope.
- [ ] Đã kiểm phiên bản request token: Spring Security 7 **CasServiceTicketAuthenticationToken**, code tài liệu cũ có thể khác.
- [ ] Có integration tests với CAS Server thật hoặc test server tương thích, không chỉ unit mock ST.
- [ ] Có rollback/config audit khi CAS URL, service registry hoặc TLS certificate thay đổi.
- [ ] Local logout và CAS Single Logout là hai luồng riêng; không kết luận app session bị xóa khi CAS TGT hết hạn nếu không có SLO.
- [ ] Có monitoring các lỗi INVALID_SERVICE, INVALID_TICKET, TLS, user mapping và redirect loop.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao /login/cas?ticket=ST-... chưa đủ chứng minh người dùng đã xác thực?**

Vì ticket có thể do browser tự đưa vào. Filter phải chuyển ticket đến provider/validator để CAS Server xác minh nó được phát cho service đúng, còn hiệu lực và chưa sử dụng.

**2. CasAuthenticationFilter có trực tiếp gọi CAS /serviceValidate không?**

Thông thường filter chuyển authentication request đến **AuthenticationManager → CasAuthenticationProvider**; **TicketValidator** phía provider mới gửi yêu cầu validation tới CAS Server.

**3. ServiceProperties.service dùng cho mục đích gì?**

Đây là service identity/public callback URL, được gửi tới CAS login để phát ticket và dùng lại khi validation. Nó phải khớp service CAS đã đăng ký và URL filter xử lý.

**4. Vì sao thay HTTPS bằng HTTP hoặc thêm trailing slash có thể gây INVALID_SERVICE?**

Vì service identity có thể yêu cầu so khớp chính xác. Một ticket chỉ được phát cho service đã chỉ định, không phải mọi URL gần giống nó.

**5. CAS Service Ticket có thể được dùng lại sau validation thành công không?**

Không. Theo CAS protocol, ST chỉ có hiệu lực cho một lần validation attempt, kể cả khi lần đó thất bại. Sau login stateful, app giữ session riêng.

**6. CAS TGT có phải là ST trong callback không?**

Không. TGT đại diện phiên SSO tại CAS; ST được CAS cấp riêng cho một service và dùng một lần. Trình duyệt thường giữ TGC cho CAS, không cung cấp TGT cho /login/cas.

**7. CAS validation success có nghĩa được cấp ROLE_ADMIN trong app chưa?**

Chưa. Provider/UserDetailsService phải map tài khoản, kiểm enabled/locked và authorities theo chính sách local. CAS authentication khác application authorization.

**8. Vì sao response từ /serviceValidate phải qua TLS xác thực?**

Vì ứng dụng dựa vào kết quả CAS để quyết định người dùng là ai. Nếu attacker giả được CAS response hoặc thay đổi user, có thể tạo Authentication trái phép.

**9. Với Spring Security 7, request token của CasAuthenticationFilter là gì?**

Javadoc hiện hành mô tả **CasServiceTicketAuthenticationToken**; tài liệu CAS cũ có thể nhắc **UsernamePasswordAuthenticationToken**. Phải đối chiếu API của phiên bản đang dùng.

**10. CAS 2.0 Service Ticket và CAS 3.0 attributes khác gì?**

CAS 2.0 service validation trả kết quả user; CAS 3.0 có `/p3/serviceValidate` để trả attributes theo policy. Cần dùng validator/client tương thích và CAS Server phát attrs.

**11. Khi nào nên bật authenticateAllArtifacts?**

Khi triển khai xác thực proxy/stateless CAS artifact có thiết kế riêng, service URL details và proxy validator đúng. Không cần bật cho login browser ST trên /login/cas.

**12. Vì sao app logout xong vẫn được CAS SSO lại nhanh?**

Vì local session đã xóa nhưng CAS TGT/TGC có thể còn; CAS cấp **ST mới** không yêu cầu nhập lại mật khẩu. Đó không phải ST cũ bị reuse.

**13. Nếu browser refresh URL callback ST đã dùng và gặp INVALID_TICKET thì nên làm gì?**

Không validate lại ST đã consume. Điều hướng về URL sạch sau login và khởi tạo login mới khi cần, đồng thời kiểm success handler/callback caching.

**14. Một ST của Reports có dùng để đăng nhập Portal được không?**

Không. Ticket ràng buộc service nhận. CAS Server phải từ chối mismatch, ngay cả nếu hai app ở cùng tổ chức hay CAS realm.

**15. Có nên triển khai ticket validation chỉ bằng một bản đồ Map trong ứng dụng?**

Không. Map Java 17 trong bài chỉ là ví dụ **giả lập CAS Server** để học one-time/service binding. Production dùng TicketValidator kết nối CAS Server thật, với TLS, service registry và chính sách phiên phù hợp.

## 19. Tài liệu tham khảo chính thức

- Spring Security, **CAS Authentication**: luồng entry point, CasAuthenticationFilter, ServiceProperties, CasAuthenticationProvider, TicketValidator, stateful/proxy tickets: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security Javadoc, **CasAuthenticationFilter**, callback /login/cas, ServiceProperties, CasServiceTicketAuthenticationToken và SecurityContextRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
- Spring Security Javadoc, **CasAuthenticationProvider**, phương thức setServiceProperties, setTicketValidator, setUserDetailsService và CAS token handling: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Spring Security Javadoc, **ServiceProperties**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html
- Spring Security, **Servlet Authentication Architecture**, AuthenticationManager/ProviderManager và SecurityContext: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Apereo CAS, **CAS Protocol Specification 3.0**, /login, /serviceValidate, /p3/serviceValidate, Service Ticket one-time và INVALID_SERVICE: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS, **CAS Protocol Ticket Validation**, service matching strategy: https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html
- Apereo Java CAS Client, **README**, Cas20/Cas30 ServiceTicketValidators và proxy filter variants: https://github.com/apereo/java-cas-client/blob/master/README.md
- Apereo CAS, **Troubleshooting Guide**, invalid ticket/service và thiếu attributes: https://apereo.github.io/cas/development/installation/Troubleshooting-Guide.html

**Ghi nhớ:** `CasAuthenticationFilter` nhận **Service Ticket opaque** từ callback `/login/cas?ticket=...` và gửi authentication request đến **CasAuthenticationProvider**. Provider dùng **TicketValidator gọi CAS Server** để xác minh ticket cho **ServiceProperties.service** đúng, chưa hết hạn và chưa được sử dụng. Chỉ sau đó mới có username/attributes đáng tin cậy để Spring Security tạo **CasAuthenticationToken**, lưu local session và áp quyền nghiệp vụ. **Service URL phải nhất quán; ST dùng một lần; ticket không phải user, không phải TGT và không được tin khi chưa qua CAS validation.**