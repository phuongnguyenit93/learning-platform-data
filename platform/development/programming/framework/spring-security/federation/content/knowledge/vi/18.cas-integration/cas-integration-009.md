# Phân biệt phiên ứng dụng có trạng thái với chế độ xác thực ticket không lưu phiên

> **Module:** Spring Security – federation · **Chủ đề cha:** Tích hợp CAS. Bài học phân biệt **CAS web login có trạng thái (stateful application session)** với **CAS ticket authentication không dựa vào HttpSession (stateless client/service)**, đặc biệt cơ chế `CasAuthenticationFilter`, `CasAuthenticationProvider` và `StatelessTicketCache` của Spring Security. “Stateless” ở HTTP/Spring **không tự đồng nghĩa** toàn bộ hệ thống không lưu trạng thái, cũng **không** cho phép dùng lại một CAS ticket tại CAS server sau khi nó đã được xác minh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **CAS server SSO session**, **service ticket (ST)**, **proxy ticket (PT)**, **application HttpSession** và **SecurityContext** là những thứ khác nhau.
2. Mô tả cách một trình duyệt nhận ST, ứng dụng gọi CAS xác minh ST **một lần**, rồi lưu `Authentication` vào phiên ứng dụng cho những request tiếp theo.
3. Giải thích vì sao API/remoting client không có cookie phiên thường phải cung cấp credential **ở từng request** thay vì dựa vào `JSESSIONID`.
4. Phân biệt `CasServiceTicketAuthenticationToken.CAS_STATEFUL_IDENTIFIER` và `CAS_STATELESS_IDENTIFIER` theo API Spring Security CAS 6.x.
5. Hiểu vai trò của `ServiceProperties.authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource`, `Cas20ProxyTicketValidator` và `StatelessTicketCache`.
6. Giải thích nghịch lý tưởng như mâu thuẫn: **CAS ST/PT chỉ được validate một lần**, nhưng Spring có thể **tái sử dụng authentication đã được cache theo ticket** trong mô hình stateless.
7. So sánh `HttpSessionSecurityContextRepository`, `NullSecurityContextRepository` và `SessionCreationPolicy.STATELESS`, không nhầm Spring session policy với cấu hình CAS ticket processing.
8. Nhận diện rủi ro của **ticket cache như bearer credential**: lộ token, replay trong thời gian TTL, scope của service/tenant, stale roles, logout/revocation, multi-node và availability.
9. Thiết kế hai kiểu triển khai: web portal stateful và backend API stateless; chọn cách xác thực phù hợp thay vì cố sử dụng CAS ticket như JWT hoặc API key vĩnh viễn.
10. Chạy chương trình Java 17 độc lập, nhìn rõ thời điểm xác minh CAS, thời điểm đọc phiên local, cache hit và kết quả sau khi cache hết hạn.
11. Lập ma trận test về session fixation, TTL, service mismatch, PT/PGT trust, CAS outage, logout và dữ liệu quyền theo từng request.

**Phạm vi phiên bản:** Java 17, Spring Boot 3.3.x / Spring Security 6.3.x dùng giao thức **CAS**; các API và mẫu cấu hình Spring Security mới/cũ cần được kiểm tra theo dependency thực tế. Ví dụ Spring có điều kiện cần máy chủ CAS thật và service registration đúng; code Java độc lập không gọi CAS thật.

## 2. Câu hỏi quyết định: sau khi xác thực, request tiếp theo chứng minh người dùng bằng gì?

Một ứng dụng Orders Portal có browser và một API back-end báo cáo:

- Browser mở `/orders`, được redirect tới CAS. Sau khi CAS xác minh ST, Portal tạo phiên `JSESSIONID`. Browser tiếp tục request bằng **cookie phiên Portal**; Portal **không xác minh lại ST** mỗi lần.
- Một service-to-service client gọi `/api/reports` mà **không có HttpSession cookie**. Nếu dùng CAS proxy ticket theo cơ chế stateless của Spring, request phải mang **ticket tương ứng**, và API phải có cách xác thực request đó. Có thể gọi CAS validate **ticket mới** mỗi lần, hoặc áp một **StatelessTicketCache** để tái sử dụng kết quả xác minh trước đó trong cửa sổ được quản trị.

Nhìn ngoài, cả hai đều đã “đăng nhập nhờ CAS”; điểm khác là **nơi giữ bằng chứng đăng nhập giữa các request**.

| Tiêu chí | Stateful web portal | CAS stateless remoting/API |
| --- | --- | --- |
| Chủ thể phổ biến | Browser có cookie, UI nhiều request. | Backend/remote client không dùng cookie phiên Portal. |
| CAS ticket thường gặp | ST từ `/login?service=...`. | PT cấp qua PGT, dành riêng `targetService`. |
| Điểm nhận ticket | `CasAuthenticationFilter.filterProcessesUrl`, mặc định `/login/cas`. | URL khác callback login khi đã bật `authenticateAllArtifacts` và cung cấp service URL động. |
| Tín hiệu nội bộ | `CAS_STATEFUL_IDENTIFIER`. | `CAS_STATELESS_IDENTIFIER`. |
| Đơn vị nhận diện ở request sau | Session ID cookie `JSESSIONID` và `SecurityContext` lưu server-side. | Credential trên request, thông thường PT; có thể tra `StatelessTicketCache`. |
| CAS validate trực tiếp | Khi nhận ST lần đầu để login. | Khi PT lần đầu chưa có cached token, hoặc với ticket mới nếu không cache. |
| Nơi lưu auth | `HttpSession`/session store. | Không cần HttpSession, nhưng có thể có **ticket cache server-side**. |
| TTL/thu hồi chính | Session timeout, logout, session store, local account policy. | Ticket cache TTL/eviction, ticket exposure và quyền local; CAS ticket 1 lần không tự xóa cache. |
| Nếu mất trạng thái | User có thể phải SSO/login lại. | Nếu mất cache, cùng PT đã consume ở CAS có thể không validate lần nữa. |
| Rủi ro lớn | Session cookie bị chiếm, fixation/CSRF/session mismatch. | Token/PT bị lộ, dùng lại trong cache window, không tách đúng service/tenant. |

**Kết luận trung tâm:** Stateful và stateless mô tả **cách ứng dụng tiếp tục xác thực request**, không phải việc CAS server có giữ phiên SSO hay không. CAS luôn có hệ thống ticket/SSO lifecycle riêng.

## 3. Năm loại trạng thái phải tách biệt

### 3.1. CAS TGT/TGC: trạng thái SSO của nhà cung cấp danh tính

- CAS server cấp **Ticket-Granting Ticket (TGT)** khi xác thực người dùng, quản lý phiên SSO trong phạm vi CAS.
- Browser thường giữ **Ticket-Granting Cookie (TGC)** cho domain CAS; Portal **không** sở hữu cookie ấy.
- TGT/TGC có thể sống lâu hơn, ngắn hơn hoặc độc lập với phiên HTTP tại Portal.
- Cùng một CAS SSO session có thể được dùng để phát **nhiều ST** cho các ứng dụng khác nhau.
- Logout local của Portal **không bảo đảm** logout TGT/TGC tại CAS; cần CAS logout/Single Sign Out nếu triển khai.

### 3.2. Service Ticket (ST): credential chuyển giao cho một service

- CAS cấp ST cho **một service URL** sau khi browser được xác thực.
- Browser quay về `https://portal.example/login/cas?ticket=ST-...`.
- **Portal server** gọi CAS `/serviceValidate?service=...&ticket=...` qua HTTPS.
- CAS kiểm tra ST đúng service, chưa dùng, chưa hết hạn; validation làm ST **bị tiêu thụ** bất kể thành công hay thất bại theo CAS protocol.
- ST **không phải** local session ID, username hay quyền nghiệp vụ.

### 3.3. Proxy-Granting Ticket và Proxy Ticket

Một ứng dụng đã xác thực có thể cần gọi dịch vụ back-end **thay mặt user**:

- Nó dùng callback tin cậy `pgtUrl` trong CAS validation để nhận/correlate **Proxy-Granting Ticket (PGT)** với `PGTIOU`.
- Ứng dụng dùng PGT yêu cầu CAS cấp **Proxy Ticket (PT)** cho `targetService` cụ thể qua `/proxy`.
- Backend nhận PT và dùng `/proxyValidate`, không dùng `/serviceValidate` cho PT.
- PT cũng là credential **opaque, ràng buộc service và chỉ hợp lệ cho một validation attempt** tại CAS.
- Proxy chain `cas:proxies` có thể phản ánh dịch vụ đã trung gian; backend chỉ nhận các proxy đã được duyệt.

**Không dùng PGT như PT** và không chuyển PGT/TGT cho browser hoặc backend bên ngoài phạm vi tin cậy. PGT có giá trị lấy nhiều PT; rò PGT nghiêm trọng hơn rò một PT có scope hẹp.

### 3.4. Application HttpSession: trạng thái của Portal

`JSESSIONID` thường chỉ tham chiếu một `HttpSession` do Portal/server session store quản lý. Trong phiên có thể lưu `SPRING_SECURITY_CONTEXT` với `Authentication` đã được CAS xác thực.

~~~text
Browser cookie JSESSIONID=abc
       |
       v
Portal HttpSession abc
       |
       +-- SecurityContext
       |     Authentication principal=alice
       |     GrantedAuthorities=[APP_ORDER_READ]
       |
       +-- SavedRequest, CSRF token hoặc dữ liệu session khác
~~~

Browser không cần gửi ST lại sau login. Mỗi request qua Spring Security khôi phục `SecurityContext` từ repository/session (nếu session hợp lệ) rồi kiểm tra quyền nghiệp vụ.

### 3.5. StatelessTicketCache: trạng thái ngoài HttpSession

`StatelessTicketCache` của Spring Security **không phải** session store của browser; nó có thể ánh xạ **ticket → CasAuthenticationToken đã xác minh**.

~~~text
Client request PT-abc
    |
    v
API CAS filter / provider
    |
    +-- Cache MISS -> HTTPS CAS /proxyValidate
    |                 -> verified user + authorities
    |                 -> put CasAuthenticationToken in cache
    |
    +-- Cache HIT  -> reuse cached CasAuthenticationToken
    |
    v
Request SecurityContext (chỉ request này)
    |
    v
Authorization / business handler
~~~

Với một cache có TTL 2 phút, CAS có thể đã tiêu thụ PT ở lần đầu nhưng API vẫn chấp nhận **cùng chuỗi PT** trong hai phút do **cache nội bộ**, chứ không phải CAS đổi quy tắc “một lần”. Cơ chế này cần được coi như **chuyển một ticket thành bearer credential tạm thời tại ứng dụng** và quản trị rất chặt.

## 4. Stateful browser login: dòng thời gian đầy đủ

~~~text
Browser             Portal (Spring Security)             CAS Server
   |                         |                              |
   | GET /orders             |                              |
   |------------------------>| no local Authentication      |
   |<-- 302 CAS /login ------| service=Portal/login/cas     |
   |------------------------------------------------------->|
   |                         |                              | TGC/TGT hoặc credentials
   |<-- 302 Portal?ticket=ST-|------------------------------|
   | GET /login/cas?ticket=ST                              |
   |------------------------>| CasAuthenticationFilter      |
   |                         |-- CAS /serviceValidate ----->|
   |                         |<-- CAS XML Success ----------|
   |                         | load UserDetails/roles       |
   |                         | save SecurityContext in     |
   |                         | HttpSession, rotate ID       |
   |<-- redirect clean URL --|                              |
   | GET /orders + JSESSIONID                               |
   |------------------------>| restore SecurityContext      |
   |<-- 200 or 403 ----------| authorization check          |
~~~

### 4.1. Các bước cụ thể trong Spring

1. `ExceptionTranslationFilter` gọi `CasAuthenticationEntryPoint` khi request bảo vệ chưa xác thực.
2. `CasAuthenticationEntryPoint` dựng CAS login URL, dùng `ServiceProperties.service` là canonical callback URL.
3. CAS phát ST và chuyển browser về callback `/login/cas`.
4. `CasAuthenticationFilter` thấy ticket ở `filterProcessesUrl` và tạo `CasServiceTicketAuthenticationToken` với principal biểu thị **stateful**.
5. `AuthenticationManager` chuyển token đến `CasAuthenticationProvider`.
6. Provider dùng `Cas20ServiceTicketValidator` và `ServiceProperties`, gọi CAS `/serviceValidate` qua TLS.
7. CAS trả `cas:authenticationSuccess`, provider tải local authorities và tạo `CasAuthenticationToken`.
8. Authentication filter/`SecurityContextRepository` lưu kết quả vào session; Spring xử lý session fixation theo cấu hình.
9. Request sau dùng session cookie, **không dùng lại ticket**; backend authorization vẫn kiểm tra quyền/tenant/resource.

### 4.2. Tại sao không gọi CAS mỗi HTTP request?

Vì ST đã dùng một lần. Nếu browser gửi lại cùng `ST-...` khi truy cập trang tiếp theo, CAS có thể trả `INVALID_TICKET`. Stateful web cần dựa vào một credential **khác** sau login, thường là cookie session Portal.

**Đừng nhầm**:
- “ST chỉ dùng một lần” = quy tắc **CAS validation**.
- “Phiên Portal dùng nhiều request” = quy tắc **session management của Portal**.
- “CAS TGT còn sống” = lý do user có thể SSO lại khi session Portal hết hạn.

### 4.3. Session fixation và cookie

Sau CAS login, cần:
- Luân chuyển session ID khi authentication thành công; với Servlet hiện đại Spring thường dùng `changeSessionId()`, nhưng custom CAS filter/session strategy phải được cấu hình và thử nghiệm.
- Cookie `Secure`, `HttpOnly`, `SameSite` phù hợp với ứng dụng và cross-site flow.
- CSRF protection cho browser actions dựa cookie; login callback là GET và xử lý ticket riêng.
- Session idle timeout, absolute timeout nếu policy yêu cầu, logout invalidation, concurrent session restrictions, account revocation.
- Không đưa JSESSIONID vào URL, không sử dụng `HttpSession` do browser lựa chọn làm bằng chứng quyền nếu không qua Spring Security.
- Dùng shared session store hoặc session affinity có kiểm thử nếu Portal chạy nhiều instances.

### 4.4. Sau local logout

Local logout tại Portal hủy `HttpSession` và SecurityContext tương ứng. **TGC/TGT của CAS có thể vẫn còn**, nên mở lại trang được bảo vệ có thể redirect tới CAS rồi nhận **ST mới** mà không nhập lại mật khẩu. Đó là một vòng SSO mới, không phải reuse ST cũ.

## 5. Stateless CAS: xác thực từng request mà không dùng HttpSession

### 5.1. Khác từ điểm vào

Spring Security reference mô tả **stateful CAS client** là request có ticket gửi vào `CasAuthenticationFilter.filterProcessesUrl`. **Stateless CAS client** là request có ticket tới URL **khác** callback đó, khi filter được cấu hình nhận ticket ở các URL được phép.

Các điểm bật theo mẫu Spring Security CAS:

- `ServiceProperties.setAuthenticateAllArtifacts(true)`: cho phép xử lý CAS ticket trên các URL ngoài callback login (phải giới hạn bằng security filter chain/route trust).
- `ServiceAuthenticationDetailsSource`: cung cấp **service URL của request đang được bảo vệ** cho provider; không dùng `ServiceProperties.service` web callback cố định một cách mù quáng.
- `CasServiceTicketAuthenticationToken.CAS_STATELESS_IDENTIFIER`: provider nhận ra xác thực thuộc kiểu stateless, không dùng auth được lưu trong phiên trước đó.
- `Cas20ProxyTicketValidator`: xác minh **proxy ticket** qua CAS `/proxyValidate`; khác `Cas20ServiceTicketValidator` cho ST.
- `StatelessTicketCache`: tùy policy, có thể lưu `CasAuthenticationToken` đã xác minh và cho phép cache hit khi caller trình ticket cũ.
- `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository`: giúp **không lưu SecurityContext vào HttpSession** giữa các request.

**Không có một thuộc tính đơn lẻ nào tự hoàn thiện toàn bộ thiết kế này.** `SessionCreationPolicy.STATELESS` chỉ tác động đến Spring session/security context; nó không tự bật nhận CAS PT trên mọi API, không cấu hình ticket validator, không tự chọn target service hay proxy trust.

### 5.2. Luồng proxy ticket chuẩn

~~~text
User/browser -> Front-end App (đã CAS login)
                  |
                  | có PGT từ CAS qua callback đã xác minh
                  v
           CAS /proxy?pgt=PGT-...&targetService=API
                  |
                  +-> trả PT-xyz chỉ cho API
                  |
Front-end server -- HTTPS, PT-xyz --> Back-end API
                                      |
                                      | không có JSESSIONID
                                      | CasAuthenticationFilter
                                      | ticket cache lookup
                                      |
                          MISS ------+------ HIT
                           |                  |
                     CAS /proxyValidate      cached CasAuthenticationToken
                     service=API            (phải còn TTL/trust)
                     ticket=PT-xyz           |
                           |                  |
                      validated user -------+
                                      |
                                      v
                              SecurityContext chỉ request
                                      |
                                      v
                              local authorization
~~~

**Quan trọng:** nếu back-end API có PT đã được xác minh và token cache còn hợp lệ, request sau gửi cùng PT có thể được chấp nhận **bởi cache**, không phải do CAS chấp nhận validate lại PT. CAS protocol vẫn yêu cầu PT chỉ cho **một validation attempt** và chỉ cho `targetService` đã phát.

### 5.3. “Không lưu phiên” không có nghĩa “không lưu state”

Ngay cả khi `HttpSession` không được tạo, hệ thống vẫn có thể giữ:

- CAS server giữ TGT/TGC và trạng thái ticket.
- PGT storage tại front-end service (nếu proxying).
- StatelessTicketCache tại API (nếu được bật).
- Revocation blocklist/permission cache/identity link.
- Load balancer affinity, rate limiting, audit và request tracing.

Do đó “stateless” trong ứng dụng thường chỉ nghĩa **không dùng per-browser HttpSession làm authentication persistence**. Không có yêu cầu kiến trúc nào buộc CAS server phải không lưu trạng thái, hoặc cache phải biến mất.

### 5.4. Hệ quả khi không dùng ticket cache

Nếu mỗi request API phải mang một PT **mới**, API gọi CAS `/proxyValidate` cho PT ấy, CAS tiêu thụ nó và kết quả authentication chỉ sống trong request hiện tại.

Ưu điểm:
- Không duy trì cửa sổ **cached reusable ticket**.
- Revocation/ticket validity được CAS kiểm tra ở mỗi lần nhận **ticket mới**.
- Không cần chia sẻ ticket cache giữa API nodes.

Nhược điểm:
- Front-end cần xin PT mới qua PGT cho mỗi call.
- CAS và HTTPS round-trips tăng, dễ ảnh hưởng latency và availability.
- CAS outage khiến request mới không xác thực được nếu không có credential hợp lệ khác.
- Cần bảo vệ PGT storage, quản lý proxy chain và tránh retry PT đã tiêu thụ.

`NullStatelessTicketCache` là implementation không có backing cache trong API Spring; nó phù hợp để **không có cache hit**, nhưng **không biến một PT cũ thành credential có thể được CAS xác minh nhiều lần**.

## 6. CAS Ticket một lần và cache: hai quy tắc nhìn như mâu thuẫn

### 6.1. CAS protocol

Với ST/PT:

1. CAS cấp ticket cho một `service` cụ thể.
2. Ticket còn hạn trong một cửa sổ ngắn.
3. Lần gọi validation **đầu tiên**, CAS tiêu thụ ticket, kể cả sai service/validation fail.
4. Các validation attempts kế tiếp dùng cùng ticket bị CAS từ chối.

~~~text
CAS:
validate(PT-1, API) -> SUCCESS, mark PT-1 consumed
validate(PT-1, API) -> INVALID_TICKET
~~~

### 6.2. Spring CAS stateless ticket cache

Với `SpringCacheBasedTicketCache` đã cấu hình:

~~~text
API:
Request #1, PT-1 -> cache MISS -> CAS validates SUCCESS
                -> cache[PT-1]=CasAuthenticationToken(user=alice), TTL 2m

Request #2, PT-1 -> cache HIT  -> accepts cached authentication
                -> KHÔNG gọi CAS validate lần hai

Request #3, PT-1 sau TTL -> cache MISS
                -> CAS validate -> INVALID_TICKET vì PT-1 đã consumed
~~~

Không hề có mâu thuẫn: **CAS từ chối validate lại**, nhưng API **không gọi lại CAS** khi có cache hit.

### 6.3. Bảo mật: đây là một dạng bearer credential do API tạo ra

Nếu cùng chuỗi PT có thể dùng lại để lấy cached `CasAuthenticationToken`, ai có được chuỗi PT trong TTL **có thể tìm cách replay** vào API. Vì vậy cache không chỉ là tối ưu CPU; nó **thay đổi cách đối xử với ticket ở phía API**.

Những câu hỏi bắt buộc trước khi bật:

- PT đi qua TLS/mTLS nào? Có lọt vào URL query, browser history, Referer, access logs, telemetry không?
- Cache TTL là bao lâu? Có giới hạn kích thước và eviction khi user bị disable/logout không?
- Cache key có scope theo CAS realm, target service, tenant, route/method nếu policy cần không? Spring cache mặc định được mô tả là keyed by ticket ID; **không tự suy mọi ràng buộc nghiệp vụ được thực thi lại trên cache hit**.
- Cache có bị dùng chung cho nhiều security chains/tenants mà thiếu phân vùng không?
- Local roles và account status có được kiểm tra lại khi xử lý hành động nhạy cảm không?
- Khi CAS backend outage, cache có tiếp tục cho phép request? Nếu có, đó có phải chủ ý risk policy không?
- Sau cache eviction, hệ thống sẽ yêu cầu PT mới hay bất ngờ thử CAS với ticket cũ rồi thất bại?
- Có audit để chứng minh cache hit, miss, expiration và revoke?

**Mặc định an toàn cho API nhạy cảm:** ưu tiên PT mới/validation mới mỗi request hoặc một cơ chế access token thiết kế riêng với audience/scope/expiry/revocation rõ ràng. Chỉ bật cache khi đã duyệt threat model và hạn mức TTL, không chỉ vì giảm số lần gọi CAS.

## 7. State là gì trong Spring Security, và state nằm ở đâu?

### 7.1. SecurityContextHolder ≠ SecurityContextRepository

- `SecurityContextHolder` thường giữ `SecurityContext` trong phạm vi **thread/request** để các filter/service đọc Authentication.
- `SecurityContextRepository` quyết định có **lưu và khôi phục** context giữa các request hay không.
- `HttpSessionSecurityContextRepository` đọc/ghi security context vào `HttpSession`.
- `NullSecurityContextRepository` không persist context giữa requests.
- `SessionCreationPolicy.STATELESS` yêu cầu Spring Security không tạo/dùng HttpSession để lấy SecurityContext; đây là policy cho **Spring session**, không là proxy ticket policy.

Vì vậy API stateless vẫn có thể có `SecurityContextHolder.getContext().getAuthentication()` **trong lúc xử lý một request đã xác thực**. Khác biệt nằm ở việc **request tiếp theo không có cookie/session context để khôi phục**.

### 7.2. SessionCreationPolicy trong bối cảnh này

| Policy | Ý nghĩa gần đúng | Có phải CAS stateless auth không? |
| --- | --- | --- |
| `ALWAYS` | Spring tạo session. | Không; vẫn cần CAS flow riêng. |
| `IF_REQUIRED` | Tạo session khi framework cần. | Phù hợp nhiều web flows stateful. |
| `NEVER` | Spring không chủ động tạo mới nhưng có thể sử dụng session đã tồn tại. | Không bảo đảm không dùng session. |
| `STATELESS` | Không tạo/dùng HttpSession cho SecurityContext. | **Chưa đủ** để nhận/validate CAS tickets stateless. |

Một web portal CAS dạng redirect thường cần request cache/SavedRequest, CSRF token và callback session. Nếu ép `STATELESS` trên cùng filter chain mà không thiết kế lại các thành phần này, có thể gây redirect loop hoặc mất Authentication sau redirect.

### 7.3. Khi có nhiều SecurityFilterChain

Có thể tách:

~~~text
@Order(1) /api/**  -> CAS PT hoặc bearer API; STATELESS;
                      NullSecurityContextRepository; không web redirect

@Order(2) /**      -> CAS web ST callback, HttpSession session;
                      CasAuthenticationEntryPoint, CSRF, session fixation
~~~

Các chain phải có **requestMatcher chính xác**, tránh một `CasAuthenticationFilter` cấu hình `authenticateAllArtifacts=true` tình cờ xử lý tất cả ticket trên URL không dự định. Mỗi chain nên có trust config phù hợp, không chia sẻ cache nếu scope không tương thích.

## 8. So sánh lựa chọn kiến trúc

| Bối cảnh | Mô hình phù hợp | Vì sao |
| --- | --- | --- |
| Web MVC dùng browser, nhiều trang | CAS login stateful + local HttpSession. | CAS ticket chỉ validate một lần, session phù hợp browser. |
| SPA gọi backend cùng origin và có cookie | Có thể dùng web session + CSRF/session policy. | “SPA” không bắt buộc stateless. |
| Service-to-service gọi API theo user qua CAS proxy | CAS PT + stateless processing theo trusted target service. | Mỗi request có credential, không dùng browser cookie. |
| API traffic cao, muốn cache PT | Chỉ khi có threat model cache, TTL và revocation rõ. | Cache giảm CAS calls nhưng tạo cửa sổ replay. |
| Public API đa client không cần CAS delegation | Cân nhắc OAuth2/OIDC JWT/opaque access tokens theo thiết kế. | CAS PT không thay thế một hệ thống API token chuẩn. |
| Dịch vụ nhạy cảm, yêu cầu kiểm tra danh tính mỗi call | PT mới/validate mỗi request hoặc step-up thiết kế riêng. | Tránh cached authentication tồn tại quá lâu. |
| Web portal có logout nhiều ứng dụng | CAS SLO + local session invalidation theo hợp đồng. | TGT/TGC và Portal HttpSession là hai hệ thống phiên khác nhau. |
| Multi-tenant dùng CAS realms khác nhau | Scope realm/service/tenant và cache riêng. | Username/ticket ID không tự mang nghĩa toàn cục. |

**Không nên chọn stateless chỉ vì hiện đại hơn.** Chi phí vận hành và rủi ro bảo mật phụ thuộc người dùng, loại client, khả năng quản lý credential, latency và yêu cầu thu hồi quyền.

## 9. Java 17 chạy độc lập: phiên local so với cache PT

Ví dụ này **không có server CAS thật** và **không có HttpSession thật**. Nó chỉ mô phỏng các quy tắc: CAS ticket dùng một lần, Portal giữ local session sau web login, API cache kết quả xác minh PT trong TTL ngắn. Phần mô phỏng dùng map cố định và timestamp giả, nên stdout **không phụ thuộc thời gian thực**.

### 9.1. Tệp `CasSessionModesDemo.java`

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class CasSessionModesDemo {

    private static final String WEB =
        "https://portal.example/login/cas";
    private static final String API =
        "https://api.example/reports";
    private static final String OTHER =
        "https://other.example/reports";

    record Ticket(String service, String username) { }
    record CachedAuth(String username, long expiresAt) { }

    // Mô phỏng phần CAS: ST/PT tiêu thụ một lần.
    static final class CasServer {
        private final Map<String, Ticket> issued = new HashMap<>();
        private final Set<String> consumed = new HashSet<>();

        void issue(String ticketId, String service, String user) {
            issued.put(ticketId, new Ticket(service, user));
        }

        String validate(String ticketId, String service) {
            Ticket issuedTicket = issued.get(ticketId);
            if (issuedTicket == null || !consumed.add(ticketId)) {
                return "INVALID_TICKET";
            }
            if (!issuedTicket.service().equals(service)) {
                return "INVALID_SERVICE";
            }
            return "SUCCESS:" + issuedTicket.username();
        }
    }

    // Mô phỏng Portal web: nhớ username bằng session ID.
    static final class StatefulPortal {
        private final CasServer cas;
        private final Map<String, String> sessions = new HashMap<>();

        StatefulPortal(CasServer cas) {
            this.cas = cas;
        }

        String login(String ticket, String sessionId) {
            String result = cas.validate(ticket, WEB);
            if (!result.startsWith("SUCCESS:")) {
                return "DENY:" + result;
            }
            String username = result.substring("SUCCESS:".length());
            sessions.put(sessionId, username);
            return "AUTH:" + username;
        }

        String nextRequest(String sessionId) {
            String user = sessions.get(sessionId);
            return user == null ? "ANONYMOUS" : "AUTH:" + user;
        }

        void logout(String sessionId) {
            sessions.remove(sessionId);
        }
    }

    // Mô phỏng API không có HttpSession:
    // Nếu cache hit thì không gọi CAS lần nữa.
    static final class StatelessApi {
        private final CasServer cas;
        private final Map<String, CachedAuth> cache = new HashMap<>();
        private final long ttlSeconds;

        StatelessApi(CasServer cas, long ttlSeconds) {
            this.cas = cas;
            this.ttlSeconds = ttlSeconds;
        }

        String request(String ticket, String service, long now) {
            // Scope theo target service, khác với key ticket-only
            // trong một số cache có sẵn của Spring.
            String key = service + "#" + ticket;
            CachedAuth entry = cache.get(key);

            if (entry != null && now < entry.expiresAt()) {
                return "AUTH:" + entry.username() + " (CACHE)";
            }
            cache.remove(key);

            String result = cas.validate(ticket, service);
            if (!result.startsWith("SUCCESS:")) {
                return "DENY:" + result;
            }

            String username = result.substring("SUCCESS:".length());
            cache.put(key, new CachedAuth(username, now + ttlSeconds));
            return "AUTH:" + username + " (CAS)";
        }
    }

    public static void main(String[] args) {
        CasServer cas = new CasServer();
        StatefulPortal web = new StatefulPortal(cas);
        StatelessApi api = new StatelessApi(cas, 30);

        cas.issue("ST-WEB", WEB, "alice");
        System.out.println("webLogin=" +
            web.login("ST-WEB", "session-1"));
        System.out.println("webNext=" +
            web.nextRequest("session-1"));
        System.out.println("webReplay=" +
            web.login("ST-WEB", "session-2"));
        web.logout("session-1");
        System.out.println("webAfterLogout=" +
            web.nextRequest("session-1"));

        cas.issue("PT-API", API, "bob");
        System.out.println("apiFirst=" +
            api.request("PT-API", API, 100));
        System.out.println("apiCached=" +
            api.request("PT-API", API, 110));
        System.out.println("apiExpired=" +
            api.request("PT-API", API, 131));

        cas.issue("PT-WRONG", API, "charlie");
        System.out.println("apiWrongService=" +
            api.request("PT-WRONG", OTHER, 200));
        System.out.println("apiAfterWrongService=" +
            api.request("PT-WRONG", API, 201));
    }
}
~~~

### 9.2. Biên dịch và chạy

Dùng **JDK 17 hoặc cao hơn**:

~~~bash
javac --release 17 CasSessionModesDemo.java
java CasSessionModesDemo
~~~

**Stdout chính xác:**

~~~text
webLogin=AUTH:alice
webNext=AUTH:alice
webReplay=DENY:INVALID_TICKET
webAfterLogout=ANONYMOUS
apiFirst=AUTH:bob (CAS)
apiCached=AUTH:bob (CACHE)
apiExpired=DENY:INVALID_TICKET
apiWrongService=DENY:INVALID_SERVICE
apiAfterWrongService=DENY:INVALID_TICKET
~~~

**Đọc kết quả:**

- `webLogin` xác minh ST một lần rồi tạo map local session.
- `webNext` không gọi CAS nữa vì vẫn có phiên Portal.
- `webReplay` cho thấy ST cũ không dùng lại được.
- `webAfterLogout` mất session local nên quay về anonymous.
- `apiFirst` xác minh PT thành công rồi lưu cached authentication 30 giây.
- `apiCached` tái sử dụng kết quả local, không làm CAS cho phép validate PT lần hai.
- `apiExpired`: cache hết TTL; CAS đã tiêu thụ PT nên xác minh lại thất bại, cần **PT mới**.
- `apiWrongService` tiêu thụ PT khi validate sai service.
- `apiAfterWrongService`: sửa URL nhưng PT cũ vẫn đã dùng, phải lấy ticket khác.

**Giới hạn:** Code không có HTTP, TLS, proxy chain, cryptography, account authorization hay CAS implementation. Cache theo `service#ticket` để minh họa scope; cấu trúc cache thật trong Spring cần được kiểm tra theo Javadoc/version và thiết kế phân vùng bằng biện pháp đã được duyệt, không giả sử mặc định khớp ví dụ này.

## 10. Spring Boot 3.3: web CAS stateful cấu hình bằng Java

Dưới đây là project **mẫu tích hợp** cho web portal dùng CAS service ticket và `HttpSession`. Nó yêu cầu một CAS server thật; không thể xác minh đăng nhập chỉ bằng chạy code khi thiếu CAS metadata/service registry. Mục tiêu code là thể hiện **điểm lưu SecurityContext** và trách nhiệm của CAS provider, thay vì viết TicketValidator tự động chấp nhận mọi ticket.

### 10.1. Cấu trúc

~~~text
cas-stateful-web/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/casstate/
    │   ├── CasStatefulApplication.java
    │   ├── CasWebSecurityConfig.java
    │   └── MeController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cas-stateful-web'
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
    implementation 'org.springframework.security:spring-security-cas'
}
~~~

**Dùng `spring-security-cas`**, không dùng `spring-security-saml2-service-provider` cho CAS ST/PT. Các version cố định ở đây phục vụ bài học; khi production cần dùng Spring/CAS client version còn được cập nhật và vá bảo mật.

### 10.2. Application và cấu hình

`src/main/java/com/example/casstate/CasStatefulApplication.java`:

~~~java
package com.example.casstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasStatefulApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasStatefulApplication.class, args);
    }
}
~~~

`src/main/resources/application.yml`:

~~~yaml
app:
  cas:
    base-url: "${CAS_BASE_URL}"
    login-url: "${CAS_LOGIN_URL}"
    web-service: "${CAS_WEB_SERVICE}"

server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Ví dụ biến môi trường đã được admin thiết lập:

~~~text
CAS_BASE_URL=https://cas.partner.example/cas
CAS_LOGIN_URL=https://cas.partner.example/cas/login
CAS_WEB_SERVICE=https://portal.example/login/cas
~~~

**CAS_WEB_SERVICE phải trùng chính xác canonical service URL** mà CAS đã đăng ký và CAS filter đang nhận `ticket`. Nếu reverse proxy đưa ứng dụng vào một scheme/host/port khác, sửa cấu hình URL trước, không tắt xác minh service ở CAS.

### 10.3. CasWebSecurityConfig.java

~~~java
package com.example.casstate;

import java.util.List;
import java.util.Map;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class CasWebSecurityConfig {

    @Bean
    ServiceProperties casWebServiceProperties(
            @Value("${app.cas.web-service}") String serviceUrl) {
        if (!serviceUrl.startsWith("https://")
                || !serviceUrl.endsWith("/login/cas")) {
            throw new IllegalArgumentException(
                "Expected canonical HTTPS CAS callback /login/cas");
        }
        ServiceProperties result = new ServiceProperties();
        result.setService(serviceUrl);
        result.setAuthenticateAllArtifacts(false);
        return result;
    }

    @Bean
    UserDetailsService localUsers() {
        // Học tập: chỉ cho phép subject đã biết.
        UserDetails alice = User.withUsername("alice")
            .password("{noop}unused-for-CAS-auth")
            .authorities("APP_REPORT_READ")
            .build();
        Map<String, UserDetails> allowed = Map.of("alice", alice);
        return username -> {
            UserDetails account = allowed.get(username);
            if (account == null) {
                throw new UsernameNotFoundException(
                    "CAS user not linked to an enabled local account");
            }
            return account;
        };
    }

    @Bean
    CasAuthenticationProvider casWebProvider(
            ServiceProperties casWebServiceProperties,
            UserDetailsService localUsers,
            @Value("${app.cas.base-url}") String baseUrl) {

        if (!baseUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                "CAS validation server must be HTTPS");
        }

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(casWebServiceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(baseUrl));
        provider.setUserDetailsService(localUsers);
        provider.setKey("cas-stateful-portal");
        return provider;
    }

    @Bean
    CasAuthenticationEntryPoint casWebEntryPoint(
            ServiceProperties casWebServiceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {

        if (!loginUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                "CAS login server must be HTTPS");
        }

        CasAuthenticationEntryPoint point =
            new CasAuthenticationEntryPoint();
        point.setLoginUrl(loginUrl);
        point.setServiceProperties(casWebServiceProperties);
        return point;
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            CasAuthenticationProvider casWebProvider,
            CasAuthenticationEntryPoint casWebEntryPoint,
            ServiceProperties casWebServiceProperties) throws Exception {

        AuthenticationManager manager =
            new ProviderManager(List.of(casWebProvider));
        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();

        // Tạo filter bên trong chain, tránh Spring Boot tự đăng ký
        // một @Bean Filter lần thứ hai ở Servlet container.
        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setAuthenticationManager(manager);
        casFilter.setServiceProperties(casWebServiceProperties);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setSecurityContextRepository(repository);
        casFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(casWebEntryPoint)
            )
            .securityContext(ctx -> ctx
                .securityContextRepository(repository)
            )
            .addFilterAt(casFilter, CasAuthenticationFilter.class)
            .build();
    }
}
~~~

**Giải thích cấu hình:**

- `ServiceProperties.service` cố định URL callback, `authenticateAllArtifacts=false` để chỉ dùng flow ST tại callback, không xử lý ticket trên mọi URL.
- `CasAuthenticationEntryPoint` redirect browser tới CAS.
- `CasAuthenticationFilter` xử lý `/login/cas`; principal của request CAS là stateful identifier.
- `CasAuthenticationProvider` gọi `Cas20ServiceTicketValidator`: CAS server thực sự kiểm tra ST.
- `HttpSessionSecurityContextRepository` lưu và khôi phục Authentication giữa các request của Portal.
- `ChangeSessionIdAuthenticationStrategy` minh họa chống session fixation khi CAS authentication thành công; cần thử với Servlet container/session setup thực tế.
- `UserDetailsService` cung cấp local authorities cho người được liên kết. `{noop}` ở demo **không dùng để xác thực CAS** và không phải lựa chọn bảo mật cho password login production.
- **Không khai báo CasAuthenticationFilter dưới dạng @Bean** rồi đồng thời add vào chain, vì Spring Boot có thể tự đăng ký Filter bean ở Servlet container ngoài SecurityFilterChain.
- Không cấu hình `SessionCreationPolicy.STATELESS` trong web chain có cookie/session này.
- Local logout và CAS SLO không đồng nhất. Cấu hình bổ sung CAS Single Sign Out chỉ khi đối tác thực sự cung cấp và đã thử nghiệm.

### 10.4. Controller

`src/main/java/com/example/casstate/MeController.java`:

~~~java
package com.example.casstate;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/")
    public String home() {
        return "Open /me to sign in with CAS";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "user", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                .map(a -> a.getAuthority()).toList()
        );
    }
}
~~~

Với user `alice` từ CAS và local allowlist, response của `GET /me` có thể như sau:

~~~json
{
  "user": "alice",
  "authorities": ["APP_REPORT_READ"]
}
~~~

Nó **không** biểu thị rằng CAS đã cấp `APP_REPORT_READ`. Quyền này đến từ local `UserDetailsService`. Nếu CAS xác thực một subject chưa có local account, ứng dụng không tự tạo quyền.

### 10.5. Chạy và kiểm chứng

~~~bash
./gradlew bootRun
~~~

Chuẩn bị JDK 17/Gradle wrapper tương thích, HTTPS host public, CAS server thật, service registry và cấu hình certificate/CA phù hợp. Nếu thiếu URL/keys/service registration, có thể không khởi động hoặc login không hoàn tất; bài **không cung cấp IdP giả**.

Quy trình kiểm chứng:

1. Browser truy cập `/me` và nhận redirect tới CAS login.
2. CAS xác thực rồi phát ST trỏ về đúng `CAS_WEB_SERVICE`.
3. Portal server gọi `/serviceValidate` qua TLS; không làm điều này ở browser.
4. Spring lưu authenticated `SecurityContext` trong `HttpSession`.
5. Request thứ hai với cùng JSESSIONID trả về cùng principal **không gửi lại ST**.
6. Sau logout local, JSESSIONID không còn authentication; CAS TGC có thể cấp ST mới để SSO lại.
7. Replay ST cũ tới callback phải không được CAS chấp nhận như một authentication mới.
8. Kiểm tra session ID luân chuyển khi login, timeout, cookies và account disabled.

## 11. Spring CAS stateless: cấu hình các thành phần cốt lõi

**Đây là một recipe tích hợp cần nối vào SecurityFilterChain riêng cho API**, không phải project standalone tự chạy: nó cần CAS proxy protocol, PGT/PT issuer, backend service registry, proxy trust policy, role mapping và ticket cache implementation. Mục đích là chỉ ra thành phần bắt buộc và điểm cần kiểm tra, tránh bảo rằng thêm `sessionCreationPolicy(STATELESS)` là đủ.

### 11.1. Quyết định endpoint và target service trước

Giả sử backend API nhận ticket theo URL:

~~~text
https://api.example/internal/reports?ticket=PT-...
~~~

IdP đã cấp PT cho đúng `targetService` tương ứng, và Spring `ServiceAuthenticationDetailsSource` phải tạo cùng service URL để `/proxyValidate`. URL ví dụ **không nên mang ticket vào access log**, cần HTTPS và masking. Không cho client đổi hostname/tenant hoặc proxy trust bằng tham số `service`/`casServer`.

Nếu API dùng `/internal/reports?page=2` và `/internal/reports?page=3`, phải thống nhất với CAS cách xác định **service URL canonical**/query chính xác. Không đoán rằng một PT cho reports có thể validate ở mọi path/query tùy ý. Có thể dùng service ID cố định được CAS đăng ký nếu profile và client library hỗ trợ; phải thử nghiệm.

### 11.2. Bật authenticateAllArtifacts và ServiceAuthenticationDetailsSource

~~~java
// MẢNH BEAN / WIRING của API, không phải class độc lập.
ServiceProperties apiService = new ServiceProperties();
apiService.setService("https://api.example/internal/reports");
apiService.setAuthenticateAllArtifacts(true);

CasAuthenticationFilter apiFilter = new CasAuthenticationFilter();
apiFilter.setServiceProperties(apiService);
apiFilter.setAuthenticationDetailsSource(
    new org.springframework.security.cas.web.authentication
        .ServiceAuthenticationDetailsSource(apiService)
);
apiFilter.setAuthenticationManager(apiAuthManager);
apiFilter.setSecurityContextRepository(
    new org.springframework.security.web.context
        .NullSecurityContextRepository()
);
~~~

**Cần hoàn thiện:** `apiAuthManager` là manager chứa đúng CasAuthenticationProvider cho API; phải cấu hình filter chain match `/internal/**` và entry point phù hợp để API trả 401 thay vì redirect browser. Đây là **mảnh wiring**, không phải một lớp Java đã import tất cả API và có `main`.

**Ranh giới trust:** `ServiceAuthenticationDetailsSource` dựa vào request URL; nếu reverse proxy/Host headers không được kiểm soát, service URL tính ra có thể sai hoặc bị điều khiển. Phải sử dụng canonical public URL/allowlisted routes và cấu hình forwarded headers **chỉ từ reverse proxy tin cậy**.

### 11.3. Provider dùng proxy ticket validator

~~~java
// MẢNH BEAN: backend API xác minh PT qua /proxyValidate.
// Các biến sau đến từ cấu hình đáng tin cậy, không lấy từ request.
CasAuthenticationProvider apiProvider =
    new CasAuthenticationProvider();

apiProvider.setServiceProperties(apiService);
apiProvider.setTicketValidator(
    new org.apereo.cas.client.validation
        .Cas20ProxyTicketValidator("https://cas.example/cas")
);
apiProvider.setUserDetailsService(localUsers);
apiProvider.setKey("cas-stateless-api");
~~~

Trong production phải thiết lập **CasProxyDecider** hoặc proxy trust policy phù hợp để không chấp nhận một chuỗi trung gian không được phép. Các tài liệu CAS có ví dụ `acceptAnyProxy=true` để minh họa; **không mặc định bật trong môi trường nhạy cảm**. Nếu triển khai proxying, phải cấu hình PGT callback/PGTIOU và xác nhận source/target service policy tại CAS.

### 11.4. Lựa chọn ticket cache

**Không cache:**

~~~java
// Không tạo cửa sổ chấp nhận lại cùng PT trong local cache.
// Cần một PT MỚI cho request API tiếp theo.
apiProvider.setStatelessTicketCache(
    new org.springframework.security.cas.authentication
        .NullStatelessTicketCache()
);
~~~

**Có cache:** Spring Security cung cấp `SpringCacheBasedTicketCache` nhận một Spring `Cache`. Ví dụ dùng một cache có TTL và size cap (đoạn này cần dependencies Caffeine và spring-context-support tương ứng):

~~~java
// MẢNH CẤU HÌNH CACHE, không phải toàn bộ SecurityConfig.
org.springframework.cache.Cache localCache =
    new org.springframework.cache.caffeine.CaffeineCache(
        "cas-pt-auth",
        com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
            .maximumSize(5000)
            .expireAfterWrite(java.time.Duration.ofSeconds(60))
            .build()
    );

apiProvider.setStatelessTicketCache(
    new org.springframework.security.cas.authentication
        .SpringCacheBasedTicketCache(localCache)
);
~~~

Với cache 60 giây, `CasAuthenticationProvider` có thể dùng lại `CasAuthenticationToken` từ cache khi PT được trình lại. **60 giây không phải mặc định CAS/Spring**. Cần kiểm tra:
- Nó có bắt đúng realm/service/tenant scope không? Nếu cache key mặc định chỉ là ticket, phải tránh dùng chung cache giữa các trust contexts; cân nhắc wrapper có namespace hoặc route isolation.
- Eviction khi account bị khóa/revoke và khi logout theo policy.
- Cache có TTL, max size, metrics và fault handling. Tránh cache vĩnh viễn không giới hạn.
- Nếu deployment nhiều node, cache local Node A và Node B khác nhau; PT đã consume ở CAS trên A có thể fail tại B. Không dùng “cache distributed” mà bỏ qua yêu cầu về key scope/expiration/eviction.

**Không gọi một cache là “truly stateless”:** không có browser HttpSession nhưng vẫn có server-side cache state và rủi ro tương đương bearer token.

### 11.5. SecurityFilterChain cho API

~~~java
// MẢNH DSL: filter, manager và service properties đã khởi tạo.
// Không dùng cùng web chain có CAS browser login.
http
    .securityMatcher("/internal/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(
            org.springframework.security.config.http
                .SessionCreationPolicy.STATELESS
        )
    )
    .securityContext(context -> context
        .securityContextRepository(
            new org.springframework.security.web.context
                .NullSecurityContextRepository()
        )
    )
    .requestCache(cache -> cache.disable())
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .addFilterAt(apiFilter, CasAuthenticationFilter.class);
~~~

Ở một ứng dụng có **hai chains**, dùng `@Order` và matcher cụ thể; chỉ chain `/internal/**` sử dụng session policy này. API cần entry point trả **401 JSON** thay vì redirect CAS login khi một máy gọi không có PT; security/CSRF config phải phù hợp loại credential (không cookie) và HTTP methods, **không tắt CSRF toàn ứng dụng**. Cần xử lý trường hợp mã nguồn trong `/internal/**` có state mutation, CORS/mTLS/gateway, replay controls.

### 11.6. Sao không dùng cùng provider/web filter rồi bật true?

Vì `authenticateAllArtifacts=true` làm CAS filter có thể nhận ticket trên **mọi URL được chain match**. Nếu chain web bao gồm nhiều endpoints, một attacker có thể cố đưa ticket vào nơi không dự tính và khiến ứng dụng validate dưới service URL khác.

Tách security chains/bean config giúp:
- Browser callback dùng **stateful ST** với cố định `ServiceProperties.service`.
- API dùng **stateless PT** với target service được duyệt và proxy validation.
- Không trộn `HttpSessionSecurityContextRepository` và `NullSecurityContextRepository` một cách mơ hồ.
- Không dùng chung ticket cache giữa tenant/IdP với khác trust anchors.
- Có khả năng log/metric riêng và phản hồi HTTP khác nhau.

## 12. Cache hit có làm thay đổi authorization không?

Có thể. Khi cache chứa `CasAuthenticationToken` cùng `GrantedAuthority`, local user bị thay quyền **sau lúc lần đầu validate** mà cache chưa hết hạn, cache hit có thể trả lại một tập authority **cũ** nếu ứng dụng không tải/kiểm tra lại.

Ví dụ:

~~~text
T0  API validate PT-123 với CAS -> alice, APP_EXPORT_READ
T1  Cache store authentication cho PT-123, TTL 60s
T2  Admin tắt alice hoặc revoke APP_EXPORT_READ
T3  Client gửi lại PT-123 (trong TTL) -> cache hit
T4  Nếu code chỉ nhìn cached authority -> nguy cơ vẫn ALLOW
~~~

**Cách xử lý:**
- Với quyền nhạy cảm, thực hiện **resource-level authorization** dựa vào local user status và policy hiện hành tại thời điểm request.
- Thiết kế cache invalidation khi local account bị revoke, đổi tenant, bị tách khỏi CAS identity hoặc permission thay đổi.
- Dùng TTL nhỏ và giới hạn scope; không xem TTL là thay thế cho một cơ chế thu hồi có yêu cầu chặn gần thời gian thực.
- Đừng cache quyền quản trị không giới hạn; đánh giá step-up re-authentication cho tác vụ nhạy cảm.
- Nếu cache miss sau CAS outage, fail closed; không trả thông tin user cũ từ session của một request khác.

### 12.1. Ticket cache khác cache user profile

- `StatelessTicketCache` lưu **Authentication được tạo từ CAS ticket**.
- User profile cache lưu tên/email/department, có thể được refresh riêng.
- Permission cache lưu quyền nội bộ, cần invalidation/revalidation phù hợp.
- CAS ticket registry quản lý ST/PT đã phát/tiêu thụ tại CAS server.
- Không xóa một cache rồi giả định đã xóa mọi nguồn state liên quan.

### 12.2. Session local cũng có quyền cũ

Stateful portal cũng có thể giữ `Authentication`/authorities trong session. Khi admin revoke quyền, ứng dụng phải xác định có cần invalidate session/reload permissions/check backend mỗi request không. Không cho rằng stateful xấu còn stateless tốt: **cả hai đều cần chính sách thu hồi và authorization**, chỉ khác nơi lưu sự kiện xác thực.

## 13. CAS outage, cache và availability

| Tình huống | Stateful portal | Stateless PT không cache | Stateless PT có cache |
| --- | --- | --- | --- |
| CAS còn hoạt động, credential mới | Login ST thành công. | PT mới được validate. | Miss validate; hit dùng auth đã xác minh. |
| CAS tạm không phản hồi sau khi Portal đã login | Phiên Portal còn hợp lệ có thể tiếp tục theo policy. | Không xác thực PT mới. | Cache hit có thể tiếp tục cho đến TTL, nếu risk policy cho phép. |
| CAS outage trước lần xác thực đầu | Không tạo session mới. | Không xác thực. | Cache miss không xác thực. |
| Ticket đã consume tại CAS | Portal dùng session cookie; không gửi ST lại. | PT cũ bị từ chối. | Cache hit của PT cũ có thể vẫn được chấp nhận. |
| Node khác không có state | Session store cần shared/sticky hoặc re-login. | PT mới có thể validate; PT cũ fail. | Local cache miss có thể fail với PT đã consume ở node khác. |
| User vừa bị revoke | Session cần invalidation/authorization check. | PT mới/validation và quyền local cần check. | Cached authentication cần evict/revalidate quyền. |
| CAS SLO/logout xảy ra | Local session phải nhận logout/invalidation qua cơ chế phù hợp. | PGT/PT issuance/validation bị ảnh hưởng theo CAS policy. | Cached PT **không tự bị xóa** nếu không có integration eviction. |

**Không tuyên bố cache hit là bảo đảm an toàn trong CAS outage.** Nó chỉ là một trade-off đã được duyệt: API chấp nhận một token đã xác minh trước đó trong TTL, dù nguồn xác thực hiện thời không khả dụng. Hệ thống nhạy cảm có thể yêu cầu fail closed ngay.

## 14. Phạm vi service, realm, proxy chain và tenant

### 14.1. Ràng buộc service trong CAS

CAS phát ST/PT cho đúng `service`/`targetService`. Ở lần validation đầu, CAS kiểm tra service khớp. Với stateless API cache, **cache hit không gọi CAS lần nữa**, nên dịch vụ phải đảm bảo không sử dụng cached authentication ngoài service/route/tenant đã được chấp nhận.

Ví dụ cùng một PT bị copy sang `/admin/export`; nếu API chỉ key cache theo ticket và không áp resource authorization, có thể tạo đường vượt quyền. Biện pháp:
- API có service identifier/canonical route rõ và tách các ứng dụng nhạy cảm thành service scopes thích hợp.
- Kiểm tra local permissions, action, resource ownership và tenant **trên từng request**.
- Hạn chế dùng một ticket cache toàn cục nếu có nhiều target service/trust contexts.
- Không sử dụng URL do browser/client cung cấp để tự quyết định CAS endpoint hoặc service parameter.
- Xem xét mTLS/gateway identity cho service-to-service traffic và audience/scope token hiện đại nếu phù hợp.

### 14.2. Nhiều CAS realms

~~~text
CAS realm A -> service portal-A -> alice -> local-user-A
CAS realm B -> service portal-B -> alice -> local-user-B
~~~

Hai username giống nhau không tự là một tài khoản. Với stateless cache, cần có scope rõ ràng:

~~~text
IdentityKey = (trustedCasRealm, serviceScope, validatedUser)
CacheKey policy = (trustedCasRealm, serviceScope, ticketId)
~~~

Đây là **khuyến nghị thiết kế**, không khẳng định `SpringCacheBasedTicketCache` mặc định tạo composite key này. Nếu không thể custom theo version, triển khai **các cache instances/repositories riêng theo realm và service**, tránh nhập nhằng.

### 14.3. Quyền không đến từ một chuỗi ticket

Ticket/username/attributes từ CAS xác minh **identity**. Các quyền `APP_REPORT_READ`, `APP_ORDER_APPROVE` hay tenant ownership nên đến từ nguồn được SP quản trị hoặc trust-mapping contract đã phê duyệt. Không cho ticket prefix `PT-ADMIN` hoặc attribute `groups=admin` tự biến thành quyền quản trị Portal.

### 14.4. Proxy trust chain

Backend có thể nhận PT do một proxy trung gian hợp lệ sử dụng. Các CAS responses có thể kèm `cas:proxies`. Backend phải đặt policy chấp nhận proxy nào, số hop và service nào; không cho một trung gian ngoài trust boundary tự đứng vào chain. Xác minh CAS `/proxyValidate` và proxy chain là điều kiện riêng của xác thực, không nên bỏ chỉ để giảm latency.

## 15. Bảo vệ credential và giảm nguy cơ replay

### 15.1. Ticket thường đi qua URL

Trong các ví dụ CAS cổ điển, browser/client gửi `?ticket=ST-...` hoặc `?ticket=PT-...`. Nó có thể bị lộ qua:
- HTTP access logs/ingress và reverse proxy.
- Application Performance Monitoring, traces, dashboards.
- Browser history và Referer sang website khác.
- Screenshots/bug reports/chat chứa URL.
- Cache HTTP/analytics chưa loại query nhạy cảm.

**Biện pháp:**
- HTTPS ở CAS ↔ Portal và mTLS/TLS cho service-to-service khi hợp đồng yêu cầu.
- Mask ticket query trong logs, không dùng ticket làm metric label.
- `Referrer-Policy: no-referrer` hoặc strict policy ở callback, không tải third-party assets trước khi redirect sạch.
- Không lưu ST/PT trong localStorage hoặc query của redirect ra ngoài.
- Không chấp nhận ticket từ redirect user tự thiết kế mà thiếu service allowlist.
- Giới hạn độ dài input/size payload, rate limiting, bảo vệ CSRF ở browser actions dựa cookie.
- Nếu sử dụng ticket cache, cache phải có TTL nhỏ, eviction, phân quyền truy cập và không đưa raw ticket vào audit log.

### 15.2. Replay: phân biệt hai cửa sổ

**Cửa sổ CAS:** một PT chưa validate có thể bị đánh cắp và sử dụng trước bên dự kiến. CAS chỉ chấp nhận validation một lần, nên attacker có thể tiêu thụ PT trước nạn nhân.

**Cửa sổ local cache:** sau khi API đã validate PT và lưu cached token, kẻ cắp có cùng PT có thể cố dùng nó trong TTL để nhận authentication đã cache. Đây là rủi ro **khác**, không được giải quyết chỉ bằng quy tắc one-time CAS.

### 15.3. Những điều không nên làm

- Bật `acceptAnyProxy=true` mặc định cho backend nhạy cảm.
- Tắt TLS hostname/certificate verification để “giảm độ trễ”.
- Dùng một cache không TTL/max size và không eviction khi logout.
- Dùng raw ticket làm audit identifier trong hệ thống quan sát chung.
- Dùng `SessionCreationPolicy.STATELESS` để vô tình bỏ CSRF cho web cookie chain.
- Cho client truyền `casServer=...` hoặc `service=...` tùy ý để validation, gây SSRF/trust confusion.
- Nhận HTTP 200 từ CAS mà không kiểm tra `cas:authenticationSuccess` vs `cas:authenticationFailure`.
- Tự parse `PT-...` thành username/quyền.
- Dùng ST/PT của một tenant làm session cho tenant khác.
- Dùng cache hit để bỏ hết local authorization.
- Coi PT cache như OAuth access token có scope/revocation chuẩn mà chưa thiết kế.

## 16. Logout, session expiry và thu hồi quyền

### 16.1. Stateful Portal

~~~text
Browser -- POST /logout --> Portal invalidate HttpSession
                                 |
                                 +-- clear local SecurityContext
                                 +-- remove local session cookie
                                 +-- optional CAS Single Sign Out
~~~

Nếu không triển khai CAS Single Sign Out, TGT/TGC tại CAS có thể vẫn còn, nên user sẽ SSO lại bằng ST mới khi quay về trang bảo vệ.

### 16.2. Stateless API

Không có HttpSession để hủy. Phải:
1. Chặn/evict cache entry theo ticket/identity/tenant nếu được yêu cầu.
2. Không tiếp tục chấp nhận PT đã bị báo compromise hoặc user đã revoke, dù cache TTL chưa hết, nếu policy đòi thu hồi ngay.
3. Xác định PGT/PT issuance/delegation ở front-end; khi CAS logout, phải hiểu cơ chế có tự invalidate cached PT ở backend **hay không**.
4. Kiểm tra session và quyền trên từng resource/request; không dựa vào SLO notification chưa xác nhận như cơ chế duy nhất.
5. Không trả `200 logout success` cho mọi API node nếu cache local ở một node khác vẫn còn chứa ticket.

### 16.3. Absolute session lifetime và cache lifetime

- `HttpSession` có idle timeout, có thể thêm absolute max age/forced re-auth theo chính sách.
- `StatelessTicketCache` có TTL, max size và invalidation semantics riêng.
- CAS TGT/TGC có lifetime riêng.
- CAS ST/PT tồn tại ngắn trước khi validate và được tiêu thụ sau validation.
- Không lấy một TTL (ví dụ 20 phút session) áp làm TTL cho tất cả thứ trên.

## 17. Monitoring và phân tích lỗi

| Triệu chứng | Có thể do | Hướng điều tra |
| --- | --- | --- |
| Web login thành công rồi request sau anonymous | SecurityContext không được persist, session cookie mất, STATELESS cấu hình nhầm. | Kiểm tra SecurityContextRepository, CAS filter success path, cookies/SessionCreationPolicy. |
| Browser bị redirect CAS liên tục | Service URL sai, filter callback mismatch, session không lưu hoặc CAS error. | So khớp canonical callback, access logs đã mask, authentication traces. |
| API PT đầu tiên thành công, lần hai thất bại | Đúng CAS one-time, không cache hoặc cache ở node khác/đã hết TTL. | Kiểm tra policy cần PT mới hay cache và routing. |
| API PT cũ được dùng tiếp trong 1 phút | Có stateless authentication cache. | Đánh giá bearer/replay risk và TTL có đúng policy. |
| Một node cho phép, node khác từ chối | Cache local không nhất quán, shared store không có. | Shared cache với secure scope hoặc PT mới mỗi call. |
| CAS 200 nhưng đăng nhập thất bại | XML `authenticationFailure` hoặc user không linked. | Kiểm tra loại failure, local UserDetails và service. |
| API chấp nhận PT dành cho service khác | Sai dynamic service URL hoặc cache scope. | Kiểm tra `ServiceAuthenticationDetailsSource` và targetService binding. |
| Admin revoke nhưng API còn chấp nhận | Cached authorities chưa bị evict/reload. | Policy invalidation/revalidate local permissions. |
| API báo 302 HTML cho machine client | Dùng web CAS entry point sai chain. | API nên 401/403 theo protocol, tách entry point. |
| Login web lưu session dù đã set STATELESS ở API | Hai security chains riêng, hành vi đúng. | Kiểm tra matcher/order thực tế. |
| API tạo JSESSIONID khi nghĩ stateless | Filter khác/request cache/CSRF/session config gây state. | Kiểm tra toàn chain, không chỉ một annotation. |
| CAS server timeout làm web/API hang | CAS validation client chưa có timeout/circuit breaker. | Đặt connect/read timeout, fail closed, metric latency. |

### 17.1. Metric đề xuất

~~~text
cas_web_login_total{result,realm}
cas_web_session_created_total{realm}
cas_web_session_invalidated_total{reason}
cas_stateless_ticket_validation_total{result,realm}
cas_stateless_cache_hit_total{service}
cas_stateless_cache_miss_total{service}
cas_stateless_cache_eviction_total{reason}
cas_proxy_ticket_failure_total{reason}
cas_user_revocation_enforcement_total{mode}
cas_api_auth_latency_seconds{route_group}
~~~

Đây là **metric đề xuất**, không mặc nhiên tồn tại trong Spring Security. Không đưa ST/PT, user ID, email, TGT/PGT hoặc session cookie vào labels. Nếu cần audit bằng correlation ID, sinh ID nội bộ ngẫu nhiên và không log credential thô.

### 17.2. Những điều log nên nêu

- CAS realm/service registration **đã duyệt**, không phải URL do client nhập.
- Authentication mode: stateful web, stateless cache hit hoặc stateless CAS validation.
- CAS validation result code ở mức tổng quát; không ghi raw CAS XML/ticket.
- Local account status/permission decision **đã ẩn danh hoặc mã hóa** theo audit policy.
- Cache age/TTL bucket và session store health.
- HTTP error class (401 unauthenticated / 403 authenticated thiếu quyền / 5xx dependency error) được mapping nhất quán.
- Retry behavior và log ticket reuse failure (chỉ count, không ghi ticket).

## 18. Ma trận kiểm thử tích hợp

| ID | Test | Kỳ vọng |
| --- | --- | --- |
| T01 | Browser GET protected page chưa login. | Redirect CAS login với canonical service URL. |
| T02 | CAS phát ST đúng service. | Callback nhận ticket và gọi `/serviceValidate` một lần. |
| T03 | CAS validation success, local user active. | Portal tạo Authentication và session. |
| T04 | Request web kế tiếp có JSESSIONID hợp lệ. | Khôi phục Authentication; không gửi ST tới CAS lại. |
| T05 | Replay ST cũ tại callback. | CAS từ chối, không tạo session mới. |
| T06 | Session web hết hạn. | Request không còn local auth; có thể SSO lấy ST mới. |
| T07 | Logout Portal local, TGC tại CAS còn. | Local session bị hủy; không tự tuyên bố CAS logout. |
| T08 | Web session ID trước/sau CAS login. | Có session fixation protection thích hợp. |
| T09 | Cookie Secure/HttpOnly/SameSite không phù hợp. | Test phát hiện và cấu hình phù hợp. |
| T10 | Stateless PT mới đúng target service. | API CAS validation thành công, SecurityContext chỉ request. |
| T11 | Stateless PT không cache được dùng lại. | CAS trả INVALID_TICKET cho lần sau. |
| T12 | Stateless PT có cache TTL còn hạn. | Cache hit; không gọi CAS validate lần hai. |
| T13 | Cache entry hết TTL. | PT cũ không còn auth; yêu cầu ticket mới. |
| T14 | PT bị dùng ở service URL khác lúc validation đầu. | CAS reject service mismatch. |
| T15 | PT đã cached rồi đưa sang endpoint/tenant khác. | Backend phải enforce scope/permission; không chấp nhận cross-tenant. |
| T16 | PT bị lộ trong URL/log. | Có redaction, incident response, cache eviction. |
| T17 | CAS outage trước ticket validation. | Fail closed, không authenticate. |
| T18 | CAS outage sau API cache hit. | Hành vi theo documented cache policy và TTL. |
| T19 | API node B không có cache Node A. | PT cũ fail/require fresh PT; không false success. |
| T20 | API có distributed cache. | TTL, namespace, atomic eviction và tenant isolation đúng. |
| T21 | User bị disable khi session web vẫn sống. | Session invalidation hoặc current policy deny. |
| T22 | User bị revoke khi stateless cache còn hạn. | Eviction/revalidation chặn quyền nhạy cảm. |
| T23 | Proxy chain có proxy chưa được phép. | Backend từ chối, không bật acceptAnyProxy. |
| T24 | Client gửi `casServer=attacker`. | Bỏ input, chỉ gọi CAS host trusted. |
| T25 | Client gửi `service` khác contract. | Không cho thay trusted service URL. |
| T26 | API chain bị cấu hình web CAS redirect entry point. | Test phát hiện 302 và sửa thành 401. |
| T27 | API chain `STATELESS` nhưng filter khác tạo session. | Audit kết quả theo từng chain và tắt session-based features. |
| T28 | Web chain bị cấu hình `STATELESS`. | Test phát hiện mất persistence/login loop. |
| T29 | CAS trả HTTP 200 kèm authenticationFailure. | Không authenticate. |
| T30 | Proxy Ticket gửi tới `/serviceValidate`. | Không được chấp nhận như ST. |
| T31 | Service Ticket gửi vào API có PT-only policy. | Reject ticket sai loại. |
| T32 | CAS proxy ticket hết hạn trước validation. | CAS reject, API không bypass. |
| T33 | CAS validation response network timeout. | Không tự cấp local Authentication; dùng PT mới nếu retry. |
| T34 | Multi-realm cùng username alice. | Không map chéo local users/tenant. |
| T35 | API dùng cache TTL không giới hạn. | Chính sách QA fail, buộc cấu hình max TTL/size. |
| T36 | Web local session và API ticket cache cùng user. | Thu hồi phân biệt cả hai stores, không assume logout một phía xóa phía kia. |

### 18.1. Gợi ý bài lab

**Lab A — Web có trạng thái:**
1. Chạy CAS test và Portal Servlet có `HttpSessionSecurityContextRepository`.
2. Đăng nhập, kiểm tra callback có ST mới và CAS validation một lần.
3. Nhiều lần gọi `GET /me` với cookie, xác nhận không gọi CAS lại.
4. Logout local, kiểm tra `JSESSIONID` mất hiệu lực; thử mở trang bảo vệ để quan sát SSO lại bằng ST mới.
5. Tắt/ngắt session store, mô tả ảnh hưởng tới các node.

**Lab B — API không có HttpSession:**
1. Cấu hình CAS proxy PGT/PT trong môi trường thử nghiệm được phép.
2. Mở backend service đã đăng ký `targetService` và sử dụng `Cas20ProxyTicketValidator`.
3. Tắt cache: PT mới thành công, PT cũ từ chối.
4. Bật cache TTL nhỏ: PT mới validation một lần, request lặp trong TTL dùng cache.
5. Chạy qua hai API instances, kiểm tra kết quả cache consistency/replay.
6. Revoke user hoặc role; kiểm tra thực sự có thể deny dù cache hit.
7. Chụp metrics có redaction, không chụp/log nguyên văn ticket.

**Lab C — Threat model:**
1. Mô phỏng đưa PT vào URL khác, service khác, tenant khác và CAS realm khác.
2. Phân tích nơi xảy ra binding check (CAS lần đầu) và nơi phải tự enforce (API khi cache hit).
3. Tắt CAS, đo hành vi web session, PT fresh/miss và PT cached/hit.
4. Chọn policy TTL, eviction và cần hay không một API access token khác thay thế.

## 19. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “CAS ticket chỉ dùng một lần thì web request sau phải validate lại.” | Replay bị CAS từ chối. | Stateful web lưu session local, không dùng ST lại. |
| “STATeless nghĩa là server không giữ bất kỳ trạng thái nào.” | Bỏ sót cache CAS/PGT/identity và revocation. | Tách state của CAS, Portal session và ticket cache. |
| “Set STATELESS là tự hỗ trợ PT.” | API không validate CAS ticket hoặc lỗi authorization. | Bật CAS artifact processing, details source, proxy validator và chain đúng. |
| “Cache hit chứng minh CAS vừa xác minh ticket.” | Hiểu nhầm tính mới và revocation. | Log/cache TTL, hiểu cached authentication. |
| “Cache PT không có rủi ro vì PT vốn one-time.” | Token bị replay trong cache TTL. | Treat as bearer, TTL ngắn, TLS và eviction. |
| “Một cache dùng chung mọi tenant vì ticket có thể là unique.” | Cross-realm/trust scope mix-up. | Namespaced/trust-separated cache và authorization. |
| “Đổi URL service tùy request rồi validate.” | Service confusion/SSRF/mismatch. | Trusted service config, route allowlist và canonical host. |
| “Dùng /serviceValidate cho proxy tickets.” | CAS từ chối hoặc behavior sai profile. | Dùng proxy validator và proxy trust policy. |
| “Bật acceptAnyProxy để khỏi lỗi.” | Chấp nhận chain trung gian không tin. | Named/trusted proxy policy. |
| “Có authenticated user thì quyền luôn còn hiệu lực.” | Cache/session giữ role cũ sau revoke. | Per-request policy/revocation và invalidation. |
| “API không có JSESSIONID thì không có CSRF/rủi ro browser.” | API có thể bị gọi từ browser/credential rò URL. | Thiết kế threat model theo thực tế credential/cookies. |
| “Tắt HTTPS check vì CAS nội bộ.” | Credential/token bị lộ hoặc server giả. | TLS truststore/mTLS đúng. |
| “Không nhận response CAS, cứ tạm cấp role.” | Bypass authentication. | Fail closed, retry bằng ticket mới. |
| “Logout Portal đã xóa cache API.” | Cached PT còn sống. | Revoke cả session và cache theo phạm vi. |
| “Khởi tạo CasAuthenticationFilter như @Bean và addFilterAt luôn.” | Có thể filter được đăng ký hai lần. | Chỉ đăng ký vào SecurityFilterChain hoặc disable servlet auto-registration. |

## 20. Checklist trước production

- [ ] Đã phân loại client browser vs backend remoting và chọn stateful/stateless theo nhu cầu.
- [ ] Web ST callback và CAS validation URL được allowlist/HTTPS/canonical chính xác.
- [ ] Web filter dùng `CAS_STATEFUL_IDENTIFIER` ở callback và SecurityContext được lưu trong session.
- [ ] Stateful session có rotation, TTL, cookie attributes, CSRF, logout và shared store policy.
- [ ] API chỉ nhận CAS PT trên routes và targetService đã được duyệt.
- [ ] `authenticateAllArtifacts` và `ServiceAuthenticationDetailsSource` được cấu hình/chặn phạm vi phù hợp.
- [ ] API proxy validator dùng `/proxyValidate` và kiểm tra proxy chain được phép.
- [ ] `SessionCreationPolicy.STATELESS` / `NullSecurityContextRepository` áp đúng API filter chain.
- [ ] Không nhầm `NullStatelessTicketCache` với cho phép revalidate ticket đã consumed.
- [ ] Nếu bật `SpringCacheBasedTicketCache`, TTL/max size/eviction/multi-node/realm scope được chứng minh.
- [ ] Cache hit được đối xử là sử dụng credential đã cached, không như CAS xác minh mới.
- [ ] Có kiểm soát ticket leakage ở URL/log/Referer/analytics/tracing.
- [ ] Không lấy CAS validation URL, service URL hoặc tenant từ request parameter không tin.
- [ ] Local account/permissions/tenant resource authorization được kiểm tra theo policy trên từng request.
- [ ] Session hoặc ticket cache có kế hoạch revoke khi local account disabled hoặc CAS SLO/incident.
- [ ] CAS outage behavior có tài liệu: web session, cache hit, cache miss, ticket fresh.
- [ ] Hai chains web/API có matcher/order/entry point tương ứng; API machine client nhận 401/403 đúng.
- [ ] Proxy PGT/PT được giữ trong secret management và không expose qua browser.
- [ ] Có test T01–T36 hoặc bộ kiểm thử tương đương chạy được trong staging.
- [ ] Mọi ví dụ Spring được rà soát với version thực tế và nâng dependencies theo security fixes.

## Ghi nhớ

> **Stateful CAS:** validate **ST một lần** → lưu `Authentication` vào **HttpSession Portal** → các request sau dùng session cookie. **Stateless CAS:** không khôi phục Authentication từ HttpSession, client trình **ticket/credential ở mỗi request**; Spring có thể dùng `StatelessTicketCache` để nhớ kết quả **xác minh PT lần đầu**. Cache này không làm CAS ticket trở thành reusable tại CAS, nhưng có thể làm PT trở thành **bearer credential có hiệu lực trong cache TTL của API**. Quyết định cache, scope, TTL, eviction và authorization vì vậy là một quyết định bảo mật, không chỉ hiệu năng.

### Tài liệu chính thức

- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): stateful service ticket, stateless proxy ticket, `authenticateAllArtifacts`, `ServiceAuthenticationDetailsSource` và `StatelessTicketCache`.
- [Spring Security 6.3.5 — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): stateful callback `/login/cas`, stateless ticket path, principal identifiers và filter semantics.
- [Spring Security 6.3.5 — CasAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): ticket validator, user details, cache và provider key.
- [Spring Security 6.3.x — StatelessTicketCache Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/cas/authentication/StatelessTicketCache.html): cache lưu `CasAuthenticationToken` theo ticket, phục vụ caller không có HttpSession.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextRepository`, `NullSecurityContextRepository`, `SessionCreationPolicy.STATELESS`, session fixation.
- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): ST/PT ràng buộc service và chỉ hợp lệ cho một validation attempt, PGT và `/proxyValidate`.
- [Apereo CAS — Protocol Overview](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html): TGT/TGC/ST và CAS protocol versions.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie/session fixation/revocation.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): credential handling, throttling và reauthentication.
