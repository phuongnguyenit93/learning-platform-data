# Kiểm thử header giả mạo và truy cập bỏ qua gateway xác thực

**Module:** Spring Security – federation  
**Chủ đề cha:** Kiểm thử SSO  
**Trọng tâm:** kiểm thử an toàn của hệ thống Single Sign-On (SSO) sử dụng authentication gateway/reverse proxy, đặc biệt là giả mạo identity headers và đường truy cập đến backend không đi qua gateway.  
**Công nghệ áp dụng:** HTTP/HTTPS, OIDC/SAML2 gateway, Nginx/ingress, Kubernetes/network policies, Spring Boot 3.x, Spring Security 6.x, Java 17+.

## 1. Bài toán: chỉ cần một header giả là có thể vượt SSO?

Trong một kiến trúc phổ biến, browser đăng nhập qua OIDC/SAML hoặc một cơ chế SSO khác ở **authentication gateway**. Gateway kiểm tra session và đưa thông tin identity đến backend qua một HTTP header nội bộ:

~~~text
Client / Browser
     |
     | Cookie SSO hoặc Authorization hợp lệ
     v
Public Edge / WAF
     |
     v
Authentication Gateway (xác minh OIDC/SAML/session)
     |
     | X-Verified-Subject: account-42
     | X-Verified-Issuer: https://idp.example.test
     v
Ingress / Reverse Proxy nội bộ
     |
     v
Spring Security Backend
     | Pre-authentication: lấy identity đã được gateway xác minh
     v
Local account / roles / resource authorization
~~~

Trong hệ thống này, Spring Security có thể dùng **RequestHeaderAuthenticationFilter** để lấy tên user từ header. Theo tài liệu Spring Security, filter này **chỉ trích username từ request header và không xác thực nguồn gốc header**. Nếu attacker gửi một request chứa **X-Verified-Subject: administrator** tới backend, hoặc gateway truyền header do client tự khai, Spring có thể hiểu sai đó là identity đã được xác thực.

Có **hai nhóm kiểm thử độc lập nhưng liên quan**:

1. **Header spoofing qua đường công khai:** attacker tự đặt X-Verified-Subject, X-Remote-User, SM_USER, X-Role, X-Forwarded-User... và mong gateway **bỏ/ghi đè** thay vì chuyển chúng đến backend.
2. **Gateway bypass:** attacker hoặc một workload khác đi **thẳng tới backend, NodePort, ingress phụ, service mesh endpoint hoặc đường quản trị** mà không qua authentication gateway, sau đó gửi các headers trông như do gateway tạo.

Một gateway có sanitization hoàn hảo **không đủ** nếu backend có đường đi vòng. Một backend chỉ nhận traffic từ ingress cũng **chưa chắc đủ**, nếu ingress truyền tiếp header từ nguồn không được auth gateway xác minh.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **ai được phép phát identity** và ai chỉ được phép chuyển HTTP bytes.
- Lập sơ đồ các trust boundaries từ browser đến backend và các **alternate paths**.
- Thiết kế test positive/negative dùng account thử nghiệm, không ảnh hưởng production.
- Phân biệt **identity headers** với **Forwarded/X-Forwarded-\*** dùng cho host, scheme, client IP và routing.
- Chứng minh header giả và request bypass **không thể tạo Spring Security Authentication** hoặc cấp quyền nghiệp vụ.
- Kiểm tra kết quả tại **gateway, backend, SecurityContext và endpoint bảo vệ**, không chỉ nhìn HTTP status.
- Viết ví dụ Java 17 mô phỏng nguyên tắc fail closed và hiểu giới hạn của MockMvc.

**An toàn thử nghiệm:** Chỉ thực hiện các test network trực tiếp trong **staging/lab được cấp phép**, với hostname/IP thử nghiệm và user giả; không dò quét IP/NodePort production hoặc thử giả làm người dùng thật.

## 2. Khái niệm quan trọng: pre-authentication không đồng nghĩa với self-verification

Spring Security hỗ trợ **pre-authentication** khi thành phần bên ngoài đã xác thực user. Các thành phần liên quan:

| Thành phần | Chức năng | Điều nó không tự bảo đảm |
| --- | --- | --- |
| Authentication gateway | Xác minh browser session, IdP token hoặc client certificate | Một downstream header không thể bị sửa nếu không có trust controls |
| RequestHeaderAuthenticationFilter | Lấy principal từ header như X-Verified-Subject | Không kiểm chữ ký, issuer, certificate gateway hoặc tính đúng của header |
| PreAuthenticatedAuthenticationToken | Mang principal từ nguồn pre-auth vào Spring | Không phải chứng cứ độc lập rằng IdP đã xác thực |
| PreAuthenticatedAuthenticationProvider | Nạp user details/authorities từ nguồn app | Không tái xác minh SAMLResponse/OIDC token của gateway |
| UserDetailsService | Ánh xạ user được phép, roles, enabled/locked | Không xác thực được một HTTP header nếu nguồn header giả |
| SecurityContext | Lưu Authentication của request/session tùy cấu hình | Không chứng minh nguồn Authentication từ đúng gateway |
| AuthorizationFilter/method security | Kiểm tra role/resource/tenant | Không sửa được principal bị mạo danh từ đầu |

Tài liệu Spring Security **Request-Header Authentication (Siteminder)** cảnh báo chính xác việc có thể **chọn username tùy ý khi header bị giả mạo**. Mặc định RequestHeaderAuthenticationFilter đọc **SM_USER**, nhưng ứng dụng có thể chọn header khác.

**Không nhầm HTTP headers:**

- **X-Verified-Subject, X-Authenticated-User, X-Remote-User, X-Forwarded-User, SM_USER**: identity claims *nếu* ứng dụng được cấu hình tin chúng.
- **X-Groups, X-Roles, X-Admin, X-Tenant, X-Email**: authorization/context claims; nguy hiểm nếu dùng để tự cấp quyền.
- **X-Forwarded-For, X-Real-IP, Forwarded: for=...**: thông tin IP/hop, **không phải xác thực user**.
- **Forwarded: proto=...;host=...**, **X-Forwarded-Host/Proto/Prefix/Port**: thông tin origin/routing; có thể ảnh hưởng callback SSO và redirects.
- **X-Forwarded-Client-Cert**: có thể là chuỗi chứng chỉ do một proxy đưa vào, **không tự tương đương một mTLS client certificate đã được backend xác minh**.
- **Authorization: Bearer ...**: chỉ đáng tin khi gateway/backend **thực sự xác minh** token theo issuer/audience/signature/expiry.
- **Cookie**: chứng minh session chỉ khi được server/gateway xác minh và ràng buộc với người dùng; chuỗi cookie do client tự khai không thể là “login”.

**Kết luận:** “Header có tên X-Verified-Subject” không có nghĩa nó đã được verified. Header names không có ý nghĩa mật mã.

## 3. Sơ đồ các ranh giới tin cậy và nguồn phát identity

Ví dụ hệ thống có bốn hops:

~~~text
B0 Browser/Internet
    |
    v
P0 CDN / WAF / public edge
    |
    v
P1 SSO authentication gateway  <-- IdP OIDC/SAML
    |
    v
P2 internal ingress / mesh proxy
    |
    v
A0 Spring Boot app :8080
~~~

Đánh dấu **vai trò tin cậy** khác nhau:

| Hop | Nguồn request | Có được xác thực user? | Có thể phát header identity? |
| --- | --- | --- | --- |
| B0 browser | Internet | Không theo lời tự khai | **Không** |
| P0 public edge | Internet | Thường chỉ làm transport/WAF | **Không**, trừ khi chính P0 làm auth được phê duyệt |
| P1 SSO gateway | Chỉ trusted P0 hoặc upstream policy | **Có**: validate session/OIDC/SAML | **Có**, sau khi xác minh |
| P2 ingress | Trusted P1 | Thường chỉ forward | **Không tạo user**, chỉ chuyển assertion đã được bảo vệ |
| A0 Spring app | Trusted P2 | Có thể tự verify signed assertion | Tiếp nhận identity có provenance, kiểm local user/rights |

Một **transport proxy** được phép chuyển request không đồng nghĩa là một **identity issuer** được phép nói “đây là alice”. Mối tin cậy cần có hai lớp:

1. **Peer/transport trust:** TCP/TLS peer thực sự là workload/gateway được phép; kiểm tra ở network ACL, ingress auth, mTLS service identity, mesh authorization.
2. **User identity provenance:** danh tính được tạo **bởi một thành phần đã xác thực user**, không chỉ được chuyển tiếp từ một caller chưa xác thực.

### Điểm kiểm tra quan trọng

- P1 có **xóa header identity từ client trước khi login** không?
- P1 có **ghi đè header đã tồn tại** sau xác thực không?
- P2 có nhận traffic từ những pods ngoài P1 không?
- Backend có thể được gọi trực tiếp qua public IP/NodePort/LoadBalancer, ingress phụ, DNS nội bộ, localhost hoặc một debugging route không?
- Có HTTP listener thứ hai hay management port riêng bỏ qua identity policy không?
- Các proxy có mTLS **xác thực peer identity** hay chỉ mã hóa TLS?
- Có đường bypass cho /api, /admin, /actuator, WebSocket, gRPC hoặc HTTP/2 không?
- Khi auth gateway lỗi, hệ thống **fail closed** hay cho vào bằng anonymous/user header cũ?
- Backend dùng HeaderUser/Email/Role để kiểm quyền hay lấy quyền từ DB/policy engine?
- Có session cũ giữ principal khác dù request mới đã đổi subject tại gateway?
- Hệ thống đa tenant có ràng buộc **issuer + subject + tenant** không?

## 4. Chuẩn bị bộ test: positive baseline và quan sát đúng tầng

Trước khi thử bypass, tạo một **test contract**. Ví dụ:

~~~text
Public URL:    https://portal.staging.example.test
Gateway P1:    auth-gateway.staging
App backend:   sso-app:8080 (không public)
Identity key:  X-Verified-Subject
Test subject:  reader-42
Other subject: admin-77 (không được dùng để impersonate người thật)
Protected URL: /api/me
Admin URL:     /admin/report
Identity source: IdP issuer+subject đã được gateway xác minh
Expected role: ROLE_READER (chỉ từ app DB/policy)
~~~

Tất cả hosts ở đây là **ví dụ, không phải mục tiêu thực**.

### Positive control P0: đăng nhập hợp lệ

Dùng account **reader-42** để đăng nhập qua public gateway. Kỳ vọng:

1. Gateway thực hiện OIDC/SAML/session validation, không chỉ thấy một username header.
2. Gateway tạo X-Verified-Subject **từ identity đã xác minh**, không từ request header của browser.
3. Backend nhận user reader-42 qua trusted path và ánh xạ local account/ROLE_READER.
4. GET /api/me báo đúng principal được phép.
5. GET /admin/report bị 403 hoặc deny theo role policy.
6. Sau logout/revoke, không thể dùng session cũ để tạo identity mới theo policy.

**Nếu positive baseline thất bại**, các negative tests trả 401/403 có thể là false positive do hệ thống SSO vốn chưa hoạt động. Không đánh dấu PASS an ninh trước khi baseline đúng.

### Các tín hiệu quan sát cần thu

- HTTP status/Location của **gateway** và của **backend** (ở mức telemetry nội bộ).
- Route và selected SecurityFilterChain, authentication method/session source.
- **Trusted gateway assertion issuance** event, subject ID sau mapping (không log raw token).
- Backend Authentication principal, authorities, tenant, decision trên tài nguyên.
- Network/mTLS denial tại điểm kết nối trực tiếp.
- Traces/correlation IDs đã sanitize theo mỗi hop; không tin request trace ID do attacker tự gửi nếu không reset.
- Không có user account mới/privilege mới được cấp do request giả.
- Tính nhất quán khi test phiên mới, session cũ và cửa sổ logout/revoke.

Một **HTTP 200** trên trang login/error công khai không chứng minh bypass thành công; một **HTTP 500** do app crash cũng không là kiểm thử an ninh PASS. Kết luận cần dựa trên **không có authenticated access trái quyền và đúng lý do bị chặn**.

## 5. Kiểm thử 1: giả mạo header identity qua public gateway

Client có thể tự thêm header trông như internal:

~~~http
GET /api/me HTTP/1.1
Host: portal.staging.example.test
X-Verified-Subject: admin-77
X-Authenticated-User: admin-77
X-Forwarded-User: admin-77
SM_USER: admin-77
X-Roles: ROLE_ADMIN
~~~

Nếu P0/P1 **chuyển nguyên header do client gửi** và backend dùng pre-auth, attacker có thể trở thành admin-77. Một số hệ thống nhận tên header khác nhau hoặc legacy aliases; cần kiểm tra **toàn bộ những headers thật sự có thể ảnh hưởng code**.

### Test với curl trên staging được cấp phép

~~~bash
curl -i \
  -H "X-Verified-Subject: admin-77" \
  -H "X-Roles: ROLE_ADMIN" \
  https://portal.staging.example.test/api/me
~~~

**Kỳ vọng khi không có session hợp lệ:** gateway trả login challenge/redirect hoặc 401/403; backend không có Authentication của admin-77. **Kỳ vọng khi có session reader-42 hợp lệ:** gateway có thể bỏ các forged headers rồi phát **reader-42**; /api/me phải phản ánh đúng reader-42, không phải admin-77.

Lưu ý: curl -i **không tự gửi một browser SSO session**; để test authenticated variant phải dùng cookie/tokens của **account test** được cấp theo quy trình staging. Không lấy cookie người khác.

### Kiểm tra kết quả chứ không chỉ đoán

| Biến thể | Kỳ vọng |
| --- | --- |
| Không login, forged X-Verified-Subject | Không tạo Authentication |
| Login reader-42, forged admin-77 | Nếu gateway cho request đi, backend thấy **reader-42** |
| Forged X-Roles=ROLE_ADMIN | Local roles không đổi |
| Forged X-Tenant=other-tenant | Không đổi tenant/không đọc cross-tenant |
| X-Authenticated-User hoặc SM_USER alias | Không được hệ thống dùng làm trusted alternative |
| Hai identity headers mâu thuẫn | Gateway reject hoặc tạo lại **một** canonical header duy nhất |

**Không thử với tài khoản admin production**. Sử dụng synthetic IDs và tài nguyên test có thể kiểm tra rõ ràng.

## 6. Kiểm thử 2: đường bypass tới backend

Đây là bài kiểm thử **khác** với header spoof qua gateway. Thậm chí P1 đã strip/overwrite hoàn hảo, nếu backend có alternate listener, một nguồn khác có thể gửi:

~~~text
Normal: Client -> P0 -> P1 (SSO) -> P2 -> backend

Bypass A: Authorized test host -------> backend:8080
Bypass B: Untrusted test pod ---------> ClusterIP service:8080
Bypass C: Alternate public ingress --> backend:8080
Bypass D: Exposed NodePort ----------> backend:8080
Bypass E: Management/debug port -----> protected business handler
~~~

Mục tiêu không phải tìm nhiều cổng để tấn công, mà là **xác minh toàn bộ đường tới backend đã được inventory và policy bao phủ**.

### Chuẩn bị

- Network/infra team cung cấp **danh sách endpoint staging được phép thử**: ingress public, internal service, NodePort (nếu tồn tại), pod/mesh listener và đường management có liên quan.
- Tạo một **untrusted test workload** với service identity/namespace không nằm trong allowlist.
- Tạo một **trusted gateway workload** để positive control.
- Đảm bảo SSO backend nhận chỉ đúng nguồn gateway/ingress theo ACL/NetworkPolicy/mTLS policy.
- Không mở network scanning tự động ra ngoài phạm vi staging đã phê duyệt.

### Test flow

1. Từ public URL, đăng nhập bằng reader-42 thành công và xác nhận /api/me.
2. Từ untrusted test host/pod, thử **một kết nối tới endpoint backend staging đã được cung cấp**. Không gửi secrets thật.
3. Kiểm tra phải gặp **network deny, mTLS peer rejection hoặc ingress authorization deny**. Kết nối không nên tới business handler.
4. Lặp lại với **X-Verified-Subject: reader-42** hoặc fake admin-77. Kết quả không được tốt hơn request không có header.
5. Thử các đường thay thế có trong architecture inventory: ingress khác hostname, port khác, sidecar vs application listener, HTTP/HTTPS và các routes nhạy cảm.
6. Kiểm tra telemetry: **request rejected upstream of business auth**; backend không phát security session hoặc response dữ liệu bảo vệ.
7. Nếu direct connection có thể đưa request tới pre-auth filter và filter tạo Authentication dựa trên forged header, đây là **gateway bypass nghiêm trọng**, phải khắc phục trước production.

**Đặc biệt lưu ý:** Có thể MockMvc mô phỏng request tới controller, nhưng MockMvc không thực hiện network routing, TLS handshake hoặc Kubernetes policy. Vì thế **MockMvc không thể tự chứng minh backend không truy cập trực tiếp được**. Bắt buộc có network-path/integration evidence.

### Tại sao “chỉ private IP” chưa đủ?

Mọi workload trong một VPC/cluster không nhất thiết có mức trust như nhau. NAT/sidecar/port-forward, một pod bị compromise, kết nối VPN nội bộ hoặc cấu hình NodePort sai có thể cho một peer không thuộc auth gateway gửi request trực tiếp. Không chấp nhận mọi IP 10.0.0.0/8 là “trusted identity issuer”.

## 7. Kiểm thử 3: proxy hop cuối đáng tin nhưng nguồn trước không đáng tin

Giả sử backend chỉ nhận từ ingress P2 và có mTLS:

~~~text
Untrusted pod U
    |
    | X-Verified-Subject: admin-77
    v
P2 internal ingress (mTLS được backend tin)
    |
    | Forward header nguyên trạng
    v
Backend
~~~

Nếu P2 không hạn chế **ai được phép gửi identity assertion**, backend vẫn có thể bị lừa qua một transport peer hoàn toàn hợp lệ.

**Kiểm thử:**

- Từ U gọi P2 qua đúng route/backend nhưng không có bằng chứng P1 authentication.
- Thử gửi fake identity header. P2 phải **reject hoặc loại header**, không chuyển thành principal.
- Từ P1 hợp lệ gửi request sau SSO thành công; P2 chấp nhận và forward đúng identity.
- Thử một P2 route/ingress class khác (nếu tồn tại) để phát hiện “auth optional” path.
- Thử gateway outage: P2 **không** tự đi tiếp bằng identity cũ hoặc bỏ bước auth.
- Kiểm mTLS **service identity** của nguồn P1, không chỉ TLS encrypted.

**Kết luận:** Trusted **last hop** không đủ chứng minh một claim **do đúng identity issuer phát ra**. Cần cả gateway authentication, message provenance và tuyến vận chuyển chỉ cho nguồn được phép.

## 8. Kiểm thử 4: role và tenant header spoofing

Ngay cả khi principal không thể bị giả, app có thể sai khi lấy quyền từ headers do client điền:

~~~http
X-Roles: ROLE_ADMIN
X-Admin: true
X-Groups: security-admins
X-Tenant: tenant-b
X-Email: ceo@example.test
~~~

**Negative cases:**

- Login reader-42 và thêm X-Roles=ROLE_ADMIN. GET /admin/report phải **deny**.
- Thêm X-Tenant=tenant-b; chỉ được đọc dữ liệu tenant-a vốn đã map từ local policy, không cross-tenant.
- Đổi X-Email thành email của user khác; stable issuer+subject vẫn phải là reader-42.
- Giữ một valid authenticated user nhưng request object ID không thuộc user; resource-level authorization phải deny.
- Local account disabled trong DB; gateway đã auth user cũng không được phép tiếp tục theo revocation SLA.

**Nguồn roles đáng tin:** local DB/LDAP/policy engine hoặc signed/verified authorization claims có issuer/audience/TTL phù hợp. Một X-Roles header trần được chấp nhận vì “đi từ network nội bộ” là lỗ hổng.

Không dùng email hoặc username local-part làm global identity key nếu hệ thống có nhiều issuers/tenants. Ưu tiên stable **issuer + subject (+ tenant theo contract)**.

## 9. Kiểm thử 5: X-Forwarded-For không phải chứng cứ user identity

X-Forwarded-For (XFF) thường chứa chuỗi IPs:

~~~http
X-Forwarded-For: 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

Ví dụ test:

~~~text
Client giả:      203.0.113.77 (điền vào header)
Client thật:     198.51.100.23 (địa chỉ P0 quan sát)
P0 trusted:      10.0.0.10
P1 trusted:      10.0.0.11
P2 TCP peer app: 10.0.0.12
~~~

Nếu edge chỉ append XFF mà không xóa client input, app có thể thấy:

~~~http
X-Forwarded-For: 203.0.113.77, 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

App chọn **phần tử đầu tiên bên trái** sẽ nhầm spoofed IP 203.0.113.77 thành IP client.

### Cách test đúng

- Tại public edge, gửi X-Forwarded-For chứa **IP synthetic** như 203.0.113.77.
- Edge nên **reset XFF theo peer thực nó quan sát**, hoặc proxy chain có cơ chế right-to-left chỉ chọn first untrusted hop dựa trên **danh sách trusted proxies chính xác**.
- Nếu immediate TCP peer không trusted, app nên bỏ qua XFF hoặc reject theo chính sách.
- IP allowlist, internal-only route, rate limit và audit attribution không được lấy raw XFF[0].
- Dùng mock request có repeated XFF headers, IPv6, whitespace và quoted IPv6 chỉ trong test parser/environment có hỗ trợ.
- Không suy ra identity từ IP nếu có NAT/office network dùng chung.

**Nhớ:** trusted IP/hop selection và SSO identity verification là hai việc khác nhau. Dù XFF đúng IP nguồn, nó **không** chứng minh user đã đăng nhập.

## 10. Kiểm thử 6: Forwarded, Host, Proto và Prefix poisoning

Các headers mô tả origin/routing có thể ảnh hưởng SSO redirects và cookies:

~~~http
Forwarded: for=198.51.100.23;proto=http;host=attacker.example.test
X-Forwarded-Host: attacker.example.test
X-Forwarded-Proto: http
X-Forwarded-Prefix: /admin
X-Forwarded-Port: 80
Host: portal.staging.example.test
~~~

RFC 7239 Forwarded là chuẩn cho for/by/host/proto, **nhưng client vẫn có thể tự gửi nó**. X-Forwarded-* là tập headers phổ biến khác; các proxies/framework có thể ưu tiên khác nhau. Bản thân cái tên “Forwarded chuẩn RFC” không chứng minh nguồn tin.

**Negative tests:**

1. Header **X-Forwarded-Host** không thể thay allowed public hostname dùng cho redirect URL.
2. Header **X-Forwarded-Proto=http** không làm app hạ HTTPS callback/security policy.
3. Header **X-Forwarded-Prefix** không chuyển /public thành /admin về mặt access-control.
4. **Forwarded và X-Forwarded-Host mâu thuẫn** phải được edge canonicalize hoặc reject theo contract.
5. **Host header bất thường** bị default virtual host/public gateway từ chối.
6. **OIDC redirect_uri/SAML ACS URL** không bị tạo từ untrusted Host/Proto/Prefix.
7. **Password reset links** không chứa hostname do client đưa vào.
8. **Secure cookie, SameSite, CSRF** không bị giảm bảo vệ do proxy metadata giả.
9. **X-Forwarded-Client-Cert** giả không được dùng thay một mTLS handshake/peer certificate đã kiểm chứng.

### Spring Boot forwarded-headers-strategy

Spring Boot 3.x hỗ trợ chiến lược:

~~~yaml
server:
  forward-headers-strategy: none
~~~

- **NONE:** không dùng forwarded headers để xây external request origin.
- **NATIVE:** servlet container như Tomcat dùng cơ chế native; phải kiểm tra danh sách trusted proxies và parser behavior.
- **FRAMEWORK:** Spring Framework ForwardedHeaderFilter xử lý Forwarded/X-Forwarded-* sau khi **trusted edge đã sanitize** chúng.

**ForwardedHeaderFilter không xác minh client hay proxy nào tạo header**. Chế độ **removeOnly=true** chỉ loại forwarded headers khỏi request mà không dùng giá trị. Nếu app không cần dynamic URL xây từ forwarded headers, ưu tiên canonical public base URL cấu hình server-side.

Không bật FRAMEWORK/NATIVE chỉ vì muốn “làm SSO chạy” trước khi kiểm tra trust boundary, Host allowlist, redirect policy và cả đường bypass trực tiếp.

## 11. Kiểm thử 7: duplicated header, aliases và HTTP parser differential

Các proxies có thể chuẩn hóa HTTP header không giống nhau. Một request thử nghiệm có thể chứa:

~~~http
X-Verified-Subject: reader-42
X-Verified-Subject: admin-77
~~~

Hoặc các biến thể:

~~~http
x-verified-subject: reader-42
X_Verified_Subject: admin-77
X-Authenticated-User: admin-77
SM_USER: admin-77
~~~

**Header names không phân biệt hoa/thường**, nhưng duplicate header values, underscores/hyphens, các aliases và normalization giữa proxy/container có thể làm từng hop đọc **giá trị khác nhau**.

Các test quan trọng:

- Gateway **xóa mọi inbound identity header** trước khi tạo claim đã xác minh; không phải chỉ check header có tồn tại.
- Sau login, gateway phát **chính xác một canonical identity header**.
- Duplicate identity headers bị reject hoặc canonicalized trước trust boundary, không để WAF kiểm value đầu mà app dùng value cuối.
- Header aliases không được vô tình map sang cùng variable/backend attribute tin cậy.
- Client không thể đưa **Connection: X-Verified-Subject** để khiến một hop bỏ security header quan trọng rồi hop sau diễn giải sai.
- Không có HTTP/1.1 vs HTTP/2 framing discrepancy làm ghép headers của request này sang request khác.
- Gateway và backend xử lý invalid header bytes/CRLF/ambiguous parsing nhất quán, fail closed.
- Không có route-specific normalization khiến /api hoặc /admin bỏ lớp sanitization.

**Về request smuggling:** Đây là một lớp kiểm thử parser/framing riêng, nên dùng bộ test/harness **đã được phép và có cô lập**, không thử payload phá đồng bộ hệ thống production. Mục tiêu ở đây là đảm bảo **identity của hai requests không bị trộn lẫn**.

## 12. Kiểm thử 8: session, logout, stale identity và SSO gateway outage

SSO browser thường dựa vào **gateway session cookie**; backend có thể dùng HttpSession hoặc stateless pre-auth. Cả hai thiết kế có các ca kiểm thử khác nhau.

### Stateful backend

Nếu Spring lưu SecurityContext vào HttpSession, identity có thể còn tồn tại khi header request sau biến mất hoặc thay đổi. Phải kiểm tra:

- Session backend có bị giữ sau khi gateway session đã hết hạn hoặc logout?
- Đổi user ở browser từ reader-42 sang một user khác có làm backend giữ principal cũ?
- Cookie session có session fixation protection, Secure, HttpOnly, SameSite phù hợp?
- Session timeout/revocation policy có phù hợp yêu cầu doanh nghiệp?
- Gateway và app có khác host/cookie domain khiến session “vượt” auth boundary không?
- Trong Spring Security pre-auth, **setCheckForPrincipalChanges(true)** và **setInvalidateSessionOnPrincipalChange(true)** có thể hữu ích khi dùng stateful session, nhưng **không thay việc xác minh nguồn header**.
- Nếu không có header, một session cũ đã authenticated vẫn có thể được dùng tùy filter/repository. Cần một policy rõ thay vì suy “header vắng mặt tự logout”.

### Stateless backend

Nếu gateway xác minh user mỗi request và phát trusted identity header, app có thể dùng **SessionCreationPolicy.STATELESS + NullSecurityContextRepository**. Test bảo đảm:

- Mỗi request phải có trusted identity assertion mới hoặc signed token còn hiệu lực.
- Không có session backend giữ principal từ request trước.
- Nếu header bị mất hoặc gateway outage, request được deny.
- Không có fallback Basic/form/anonymous role cho protected endpoints.
- Khi local account disabled, request tiếp theo bị deny theo policy.

**CSRF vẫn phải xem xét** nếu browser tự động gửi gateway session cookie trên cross-site requests. Một backend “stateless” không có nghĩa toàn bộ hệ thống browser SSO tự miễn nhiễm CSRF.

## 13. Tài liệu hóa test expectations theo từng điểm chặn

Mục tiêu không phải chỉ thấy status code mà phải chứng minh **đúng lớp đã từ chối**.

| Test | Điểm chặn mong muốn | Dấu hiệu thành công |
| --- | --- | --- |
| Client gửi forged principal | P0/P1 sanitization | Backend không thấy forged identity |
| Client gửi forged admin role | P1 hoặc backend role policy | No ROLE_ADMIN/403 với admin resource |
| Unauthenticated client gọi public URL | P1 auth | Redirect/login hoặc 401/403, không forward authenticated user |
| Untrusted pod gọi backend trực tiếp | NetworkPolicy/mTLS/ACL | Connection denied, không tới business handler |
| Untrusted caller gọi P2 thay P1 | P2 authorization | No accepted identity assertion |
| Wrong public Host/Proto | Public edge/request normalization | SSO redirect/ACS vẫn dùng trusted URL |
| XFF spoofed IP | Edge trusted-hop parser | Raw forged IP không được chọn cho allowlist |
| Session user changed | Gateway plus backend lifecycle | Principal/roles khớp user mới hoặc deny |
| Gateway outage | P1/P2 fail-closed | Không tạo anonymous-to-admin fallback |
| Valid SSO reader-42 | P1 + Spring + DB | /api/me đúng reader-42, /admin/report deny |

### Tại sao “deny” chưa đủ?

Một test có thể gặp 403 do **không có local account**, không phải do header stripping. Nếu mục đích là chứng minh gateway không truyền forged identity, cần quan sát sanitized gateway emission hoặc backend principal/trace an toàn. Tương tự, direct backend test trả 401 vì Spring thiếu header **không đủ** chứng minh network isolation nếu một request có forged header lại được nhận. Hãy thử cả có và không có header, rồi kết luận theo tầng.

## 14. Spring Boot 3/Spring Security 6: ví dụ pre-auth header được bảo vệ bên ngoài

**Cảnh báo bắt buộc:** Code sau **không tự ngăn người khác giả header**. Nó chỉ minh họa phần **ứng dụng** trong kiến trúc đã bảo đảm gateway authentication, header strip/overwrite và mạng backend không cho direct untrusted requests. **Không expose ứng dụng này ra Internet hoặc cluster không được tin nếu chưa có boundary/transport/signed assertion controls.**

### 14.1. Dependencies Maven

Trong pom.xml có Spring Boot parent/BOM tương thích Spring Security 6.x:

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
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

### 14.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  forward-headers-strategy: none

spring:
  application:
    name: proxy-sso-test
~~~

Giá trị none là lựa chọn cho demo khi không cần tự dựng absolute external URLs. Nếu ứng dụng production cần proxy metadata cho callback/redirect, phải đặt lại theo **trusted edge** và thử Host/Proto poisoning.

### 14.3. Java 17 main class

**src/main/java/com/example/ssogateway/SsoGatewayDemoApplication.java**

~~~java
package com.example.ssogateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SsoGatewayDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoGatewayDemoApplication.class, args);
    }
}
~~~

### 14.4. SecurityFilterChain dùng pre-auth

**src/main/java/com/example/ssogateway/GatewayPreauthSecurityConfig.java**

~~~java
package com.example.ssogateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class GatewayPreauthSecurityConfig {

    @Bean
    UserDetailsService localUsers() {
        // Demo: danh tính nội bộ từ trusted gateway.
        // Production: DB/LDAP/policy với issuer, subject, tenant.
        return username -> {
            if (!"reader-42".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("No approved account");
            }
            return User.withUsername(username)
                .password("{noop}not-used-for-proxy-sso")
                .roles("READER")
                .build();
        };
    }

    @Bean
    PreAuthenticatedAuthenticationProvider preauthProvider(
            UserDetailsService localUsers) {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            wrapper = new UserDetailsByNameServiceWrapper<>();
        wrapper.setUserDetailsService(localUsers);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(wrapper);
        return provider;
    }

    @Bean
    SecurityFilterChain protectedApi(
            HttpSecurity http,
            PreAuthenticatedAuthenticationProvider provider)
            throws Exception {

        NullSecurityContextRepository repo =
            new NullSecurityContextRepository();

        // Không @Bean cho filter này: tránh Boot tự
        // đăng ký một Servlet Filter ngoài security chain.
        RequestHeaderAuthenticationFilter headerFilter =
            new RequestHeaderAuthenticationFilter();
        headerFilter.setPrincipalRequestHeader("X-Verified-Subject");
        headerFilter.setExceptionIfHeaderMissing(false);
        headerFilter.setAuthenticationManager(
            new ProviderManager(provider));
        headerFilter.setSecurityContextRepository(repo);

        http
            .securityContext(sc -> sc
                .securityContextRepository(repo))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new Http403ForbiddenEntryPoint()))
            .addFilterBefore(
                headerFilter,
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Ý nghĩa:**

1. **RequestHeaderAuthenticationFilter** đọc đúng một header X-Verified-Subject, **không xác minh gateway hoặc chữ ký**.
2. **PreAuthenticatedAuthenticationProvider** kiểm local user qua UserDetailsByNameServiceWrapper.
3. **UserDetailsService** minh họa chỉ cho reader-42 với ROLE_READER, không tin X-Roles do client gửi.
4. **NullSecurityContextRepository + STATELESS** tránh backend session dùng identity cũ; gateway phải cung cấp validated header mỗi request.
5. **Http403ForbiddenEntryPoint** xử lý unauthenticated requests theo contract demo; status code có thể khác nếu app thay exception handling.
6. **Không cấu hình formLogin/BasicAuth fallback**; nếu thêm các cơ chế khác cần thử policy bypass riêng.
7. **Không cấu hình global csrf.disable()**; nếu browser dùng cookie/session ở gateway, cross-site unsafe requests vẫn cần CSRF controls phù hợp ở gateway/app.
8. **Không tạo filter như Spring Servlet Filter bean** rồi lại addFilterBefore; có thể dẫn tới chạy trùng ngoài chain.
9. **Không dùng request.getRemoteAddr() sau khi xử lý XFF làm chứng cứ user đã auth**. User identity cần provenance riêng.
10. **Quan trọng nhất:** Nếu một attacker gọi được backend trực tiếp và gửi X-Verified-Subject: reader-42, **code này có thể tạo Authentication reader-42**. Đó là minh họa chính xác vì sao network/identity trust boundary phải được kiểm thử, **không phải ví dụ bảo mật độc lập**.

### 14.5. Controller và endpoint

**src/main/java/com/example/ssogateway/CurrentUserController.java**

~~~java
package com.example.ssogateway;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {
    @GetMapping("/api/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("subject", principal.getName());
    }

    @GetMapping("/admin/report")
    public Map<String, String> admin(Principal principal) {
        return Map.of("admin", principal.getName());
    }
}
~~~

App **chỉ có ROLE_READER** trong demo; /admin/report bị deny ngay cả khi gửi X-Roles: ROLE_ADMIN. Điều này minh họa **authorization roles không lấy từ client header**. Nhưng khi gọi backend trực tiếp với X-Verified-Subject: reader-42, /api/me có thể trả 200; đó là lý do app chỉ được triển khai sau boundary được bảo vệ.

### 14.6. Test MockMvc cho policy cấp ứng dụng

**src/test/java/com/example/ssogateway/GatewayPreauthMvcTest.java**

~~~java
package com.example.ssogateway;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class GatewayPreauthMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void missingIdentityIsForbidden() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isForbidden());
    }

    @Test
    void approvedLocalSubjectIsMapped() throws Exception {
        // Chỉ xác minh application mapping, không chứng minh
        // gateway/network auth vì MockMvc gửi header trực tiếp.
        mvc.perform(get("/api/me")
                .header("X-Verified-Subject", "reader-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("reader-42"));
    }

    @Test
    void clientRoleHeaderDoesNotGrantAdmin() throws Exception {
        mvc.perform(get("/admin/report")
                .header("X-Verified-Subject", "reader-42")
                .header("X-Roles", "ROLE_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownLocalSubjectIsNotAccepted() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Verified-Subject", "admin-77"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Điều test này CHƯA chứng minh:** MockMvc chạy trong cùng application context, không đi qua CDN/WAF/gateway, không bắt Kubernetes NetworkPolicy hoặc mTLS. Nếu test “approvedLocalSubjectIsMapped” PASS, điều đó chỉ cho thấy application preauth dễ nhận **header do test gửi**; không thể gọi đó là header spoof prevention. Bước kiểm thử thật phải đi qua public gateway và thử direct-backend path ở staging.

**Giới hạn thực tế của mẫu:** Test unknownLocalSubjectIsNotAccepted có thể bị ảnh hưởng bởi cơ chế failure handling/security chain của project. Nếu chọn fail-fast preauth hoặc custom AuthenticationEntryPoint, status có thể khác; vẫn cần assert **không tạo authenticated identity**, không chỉ dựa vào đúng 403 của demo. Cần project hoàn chỉnh và dependencies mới chạy được, không có IdP/gateway giả định sẵn.

## 15. Java 17 độc lập: mô phỏng policy phát identity và chặn bypass

Chương trình **chạy độc lập bằng JDK 17**, không cần Spring, server, chứng chỉ hoặc network. Nó dạy cách quyết định theo **trusted ingress source**, trạng thái auth tại gateway, canonical identity và local permission. Các boolean/strings đại diện **bằng chứng do hạ tầng tin cậy cấp**, **không phải HTTP headers** attacker có thể tự gán trong production.

**Tệp: GatewaySpoofingPolicyDemo.java**

~~~java
import java.util.Set;

public final class GatewaySpoofingPolicyDemo {

    private static final String APPROVED_INGRESS = "mtls:auth-gateway";
    private static final Set<String> LOCAL_READERS =
        Set.of("reader-42");

    enum Result {
        BLOCKED_AT_NETWORK,
        LOGIN_REQUIRED,
        LOCAL_ACCOUNT_REJECTED,
        ADMIN_FORBIDDEN,
        VIEW_ALLOWED
    }

    record TestRequest(
        String authenticatedPeer,
        boolean ssoSessionVerifiedByGateway,
        String clientClaimedUser,
        String gatewayVerifiedUser,
        String clientClaimedRole,
        boolean adminResource) { }

    static Result evaluate(TestRequest request) {
        // authenticatedPeer là attestation mTLS/mesh thật
        // trong mô hình, KHÔNG phải HTTP X-Peer tự khai.
        if (!APPROVED_INGRESS.equals(request.authenticatedPeer())) {
            return Result.BLOCKED_AT_NETWORK;
        }

        if (!request.ssoSessionVerifiedByGateway()
                || request.gatewayVerifiedUser() == null) {
            return Result.LOGIN_REQUIRED;
        }

        // Không dùng clientClaimedUser hoặc clientClaimedRole.
        String subject = request.gatewayVerifiedUser();
        if (!LOCAL_READERS.contains(subject)) {
            return Result.LOCAL_ACCOUNT_REJECTED;
        }
        if (request.adminResource()) {
            return Result.ADMIN_FORBIDDEN;
        }
        return Result.VIEW_ALLOWED;
    }

    public static void main(String[] args) {
        TestRequest normal = new TestRequest(
            "mtls:auth-gateway", true,
            null, "reader-42", null, false);

        TestRequest forgedUser = new TestRequest(
            "mtls:auth-gateway", true,
            "admin-77", "reader-42", null, false);

        TestRequest direct = new TestRequest(
            "untrusted-pod", false,
            "reader-42", null, "ROLE_ADMIN", false);

        TestRequest withoutLogin = new TestRequest(
            "mtls:auth-gateway", false,
            "admin-77", null, null, false);

        TestRequest fakeAdminRole = new TestRequest(
            "mtls:auth-gateway", true,
            "admin-77", "reader-42", "ROLE_ADMIN", true);

        TestRequest unknownUser = new TestRequest(
            "mtls:auth-gateway", true,
            null, "unknown-55", null, false);

        System.out.println("normal=" + evaluate(normal));
        System.out.println("forgedUser=" + evaluate(forgedUser));
        System.out.println("directBackend=" + evaluate(direct));
        System.out.println("withoutLogin=" + evaluate(withoutLogin));
        System.out.println("fakeAdminRole=" + evaluate(fakeAdminRole));
        System.out.println("unknownLocalUser=" + evaluate(unknownUser));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac GatewaySpoofingPolicyDemo.java
java GatewaySpoofingPolicyDemo
~~~

**Stdout xác định từ logic của chương trình:**

~~~text
normal=VIEW_ALLOWED
forgedUser=VIEW_ALLOWED
directBackend=BLOCKED_AT_NETWORK
withoutLogin=LOGIN_REQUIRED
fakeAdminRole=ADMIN_FORBIDDEN
unknownLocalUser=LOCAL_ACCOUNT_REJECTED
~~~

**Giải thích từng dòng:**

- **normal:** trusted peer + SSO xác minh + local reader được phép đọc.
- **forgedUser:** client tự khai admin-77 nhưng gateway đã xác minh reader-42; bỏ claim giả, chỉ đọc như reader-42.
- **directBackend:** peer không nằm trong trusted ingress, bị chặn trước khi tin identity header.
- **withoutLogin:** dù có claim admin-77, gateway không có session đã xác minh nên phải yêu cầu login.
- **fakeAdminRole:** X-Roles do client khai không cấp quyền admin; ROLE_READER chỉ được xem tài nguyên thường.
- **unknownLocalUser:** một subject đã được gateway xác minh nhưng chưa có local account hợp lệ vẫn không được cấp business access.

**Đây là mô phỏng logic, không phải implementation của mTLS, OIDC, SAML hay servlet filter.** Production phải nhận peer identity từ TLS/mesh/network policy được kiểm chứng, nhận gateway verified user từ auth engine hoặc signed assertion, và đặt check **trước** khi tạo Authentication. Không dùng boolean do HTTP request body/header tự khai như một trusted proof.

## 16. Thiết kế E2E test với một gateway giả lập trong môi trường được phép

MockMvc chỉ kiểm app. Để chứng minh SSO boundary, cần integration setup:

~~~text
Test browser/client
    |
    v
Public staging edge
    |
    v
Authentication gateway test
    - Authenticates test session reader-42
    - Removes inbound X-Verified-Subject, SM_USER, X-Roles ...
    - Creates canonical X-Verified-Subject from verified user
    |
    v
Staging ingress with mTLS/service identity allowlist
    |
    v
Spring Boot app
    - Accepts only approved ingress
    - Maps reader-42 to local ROLE_READER
~~~

**Hai execution paths bắt buộc:**

1. **Gateway path:** client → public edge → authentication gateway → ingress → Spring.
2. **Direct-backend path:** untrusted test identity → approved backend test endpoint đã được infra cấp phép; **phải bị deny** dù client gửi header giả.

### Kịch bản E2E A: gateway sanitizes user header

1. Đăng nhập bằng reader-42.
2. Gửi request với X-Verified-Subject: admin-77.
3. Gateway kiểm session và overwrite X-Verified-Subject bằng reader-42.
4. Backend /api/me phản ánh reader-42; /admin/report deny.
5. Trong telemetry, xác nhận backend **không nhận giá trị admin-77 như trusted identity**.
6. Không log raw session token hoặc private user PII.

### Kịch bản E2E B: unauthenticated user cannot bypass gateway

1. Tạo request không có cookie/SSO session.
2. Gửi forged X-Verified-Subject: reader-42 vào public endpoint.
3. Gateway không tự biến request thành authenticated.
4. Response yêu cầu login/401/403 theo UX, không có backend Authentication.
5. Không được cấp Set-Cookie tạo session authenticated của backend.

### Kịch bản E2E C: direct-backend attempt

1. Infra cung cấp đúng backend staging endpoint và test identity được phép.
2. Từ untrusted test namespace/service identity gửi HTTP request không có header.
3. Kỳ vọng network deny/mTLS reject/ingress deny.
4. Thử thêm X-Verified-Subject: reader-42.
5. Kết quả **không thay đổi**: request vẫn không tạo Authentication hoặc trả business data.
6. Lặp lại qua những alternate routes đã được inventory.
7. Đảm bảo test không tác động hệ thống production.

### Kịch bản E2E D: gateway outage / fail closed

1. Trong lab, làm auth gateway từ chối mọi session hoặc mô phỏng IdP session validation outage.
2. Public request có header tự khai không thể đi tiếp thành authenticated.
3. P2 không tạo default identity hoặc tự bật auth optional.
4. Backend không phát hành session mới hoặc chấp nhận roles từ headers.
5. Kiểm alert và trạng thái phục hồi sau khi gateway hoạt động lại.

## 17. Ma trận kiểm thử âm toàn diện

| # | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| 1 | Login hợp lệ reader-42 qua P1 | /api/me đúng reader-42 |
| 2 | Reader truy cập /admin/report | Deny theo ROLE_READER |
| 3 | No session + X-Verified-Subject=admin-77 | Không Authentication |
| 4 | Valid reader session + forged admin subject | Vẫn reader-42, không admin |
| 5 | SM_USER=admin-77 | Không thay canonical user |
| 6 | X-Authenticated-User=admin-77 | Không thay canonical user |
| 7 | X-Forwarded-User=admin-77 | Không thay canonical user |
| 8 | X-Roles=ROLE_ADMIN | Không grant ROLE_ADMIN |
| 9 | X-Admin=true | Không nâng quyền |
| 10 | X-Tenant=tenant-b | Không cross-tenant access |
| 11 | X-Email của user khác | Không re-map local identity |
| 12 | X-Verified-Subject duplicate values | Reject/canonicalize an toàn |
| 13 | Identity header khác case | Sanitization không bypass |
| 14 | Header underscore/hyphen aliases | Không bị parser differential bypass |
| 15 | Connection chứa tên identity header | Không bỏ qua trust check |
| 16 | Raw XFF giả IP nội bộ | Không bypass IP-based controls |
| 17 | XFF nhiều hops với leftmost spoof | Trusted-hop policy đúng |
| 18 | Forwarded và X-Forwarded-For mâu thuẫn | Canonicalize/reject |
| 19 | X-Forwarded-Host attacker.example.test | Không thay public redirect host |
| 20 | X-Forwarded-Proto=http giả | Không hạ TLS/redirect/security controls |
| 21 | X-Forwarded-Prefix=/admin | Không bypass route auth |
| 22 | X-Forwarded-Client-Cert giả | Không được coi là mTLS authenticated |
| 23 | Không gửi Host đúng allowlist | Default virtual host deny |
| 24 | Untrusted test host gọi backend trực tiếp | Network/TLS/ingress deny |
| 25 | Untrusted pod gọi ClusterIP của app | NetworkPolicy/mTLS deny |
| 26 | Bypass qua NodePort/alternate listener | Không business access |
| 27 | Bypass qua secondary ingress/hostname | Không business access |
| 28 | Untrusted U gọi P2 với forged identity | P2 deny/header stripped |
| 29 | Gateway P1 fail-open scenario | Không authenticated access |
| 30 | Auth gateway outage | Fail closed, metrics/alert |
| 31 | Local user disabled | Không business access dù gateway authenticated |
| 32 | Gateway subject đổi trong session stateful | Không giữ principal cũ ngoài policy |
| 33 | Logout và browser cookie cũ | Deny theo revocation/lifetime policy |
| 34 | Direct preauth MockMvc với user header | Có thể map local user; **không được dùng làm bằng chứng network an toàn** |
| 35 | Wrong tenant object ID sau valid login | Resource-level deny |
| 36 | HTTP/2→HTTP/1 header normalization | Không trộn identity giữa requests |
| 37 | Repeated malformed headers trong lab | Parser fail safe; không smuggle identity |
| 38 | URI path case/trailing slash/encoded delimiter | Không đi nhầm security chain |
| 39 | OPTIONS, POST, WebSocket upgrade qua route khác | Gateway policy áp nhất quán |
| 40 | /actuator/admin metrics/debug path | Không bypass policy hoặc expose secrets |
| 41 | Unknown signed gateway JWT audience | Backend reject nếu dùng assertion token |
| 42 | Expired/revoked gateway token | Backend reject |
| 43 | Raw KeyInfo/JWT header tự khai issuer | Không nâng thành trusted identity |
| 44 | Session cookie cross-site unsafe request | CSRF protections theo design |
| 45 | Backend test có public endpoint cần thiết | PermitAll chỉ đúng route, không chứa business data |
| 46 | Trước/sau cập nhật ingress policy | Regression vẫn pass, không thêm bypass route |

**Phân biệt priority:** Các case 3–15 thuộc header spoofing, 24–29 thuộc **gateway bypass**, 16–23 thuộc proxy metadata, 31–35 thuộc SSO session/authorization, 36–46 thuộc parser/routing/config drift. Không kết luận cả hệ thống an toàn chỉ vì một bộ test thuộc một nhóm PASS.

## 18. Kết quả đánh giá và phân loại mức độ lỗi

### Critical / High

- **Direct backend có thể được gọi bằng forged X-Verified-Subject và tạo authenticated user**: authentication bypass nghiêm trọng, thường High/Critical theo scope/khả năng khai thác.
- Gateway forward untrusted X-Role/X-Admin khiến tăng quyền: privilege escalation.
- P2 nhận identity từ untrusted pod và backend tin: bypass qua trusted transport proxy.
- Một secondary ingress route bypass auth nhưng vẫn vào /admin.
- App chấp nhận public key/self-asserted identity token từ request như trusted gateway claim.

### Medium / cần triage theo threat model

- X-Forwarded-Host poisoning thay Location/reset links/SSO callback.
- X-Forwarded-For spoof làm sai audit/rate limits/IP policy, có thể thành High khi dùng để allow admin.
- Session lifecycle không phù hợp khi user đổi/truy cập tài nguyên còn quyền cũ.
- Header duplication/normalization bất nhất có thể tạo lỗ hổng có điều kiện.
- Gateway outage tự chuyển sang cơ chế yếu hơn nhưng chưa chứng minh được bypass.

### Đề xuất khắc phục tương ứng

| Phát hiện | Khắc phục |
| --- | --- |
| Client identity header được preserve | Edge/gateway strip và overwrite sau auth |
| Direct backend access | Default-deny NetworkPolicy/ACL, mTLS service identity, bỏ public NodePort/listener |
| Trusted P2 nhận từ U | P2 allowlist **authenticated gateway workload**, không chỉ CIDR private |
| Spring chỉ tin header, network khó khóa | Gateway-issued signed identity assertion, backend verify issuer/audience/signature/exp |
| Role/tenant từ raw header | DB/policy verified claims, local authorization |
| XFF spoof | Edge reset, right-to-left trusted proxies, không dùng XFF làm user identity |
| Host/Proto poisoning | Canonical URL/allowlist, sanitzed forwarded headers |
| Header duplicates/aliases | Reject duplicates, single canonical header, strict proxy parser policy |
| Session stale | Explicit session expiry/revocation/principal change checks |
| Gateway outage fail-open | Fail closed, alert và test recovery |
| Spring chain mismatch | Explicit securityMatcher/order, protected fallback chain, tests |
| Parser disagreement | Align HTTP versions/normalization, regression tests |

**Không khắc phục bằng cách “đổi tên X-Verified-Subject thành bí mật hơn”**. Header name không là credential và có thể được đoán/quan sát. Tương tự, private network không tự có trust identity.

## 19. Khi nào nên thay raw identity header bằng signed assertion?

Một kiến trúc chỉ tin header trần phù hợp khi **toàn bộ đường mạng** được kiểm soát chặt, upstream auth gateway bảo vệ và hệ thống có chứng cứ mTLS/ACL chống direct paths. Với nhiều teams, namespaces, proxies và service-to-service traffic, một **signed identity assertion** từ P1 đến A0 có thể dễ audit hơn.

Ví dụ gateway gửi JWT có:

- **iss**: trusted gateway issuer.
- **sub**: stable user identifier (không chỉ email).
- **aud**: đúng backend/service.
- **exp/nbf/iat**: thời hạn và freshness.
- **jti**: token ID nếu cần revoke/replay controls.
- **tenant/roles**: chỉ từ trusted policy, cần backend kiểm authorization.
- **signature**: ký bằng key nằm trong trustset đã onboarding, có rotation/alg allowlist.

Backend **phải tự verify JWT signature, issuer, audience, expiry, key selection** bằng Spring Security OAuth2 Resource Server/JwtDecoder hoặc thành phần tương đương. Không dùng JWK URL đến từ untrusted token header; không dùng ID Token OIDC như một API access token nếu chưa có contract bảo mật rõ.

**JWT không tự giải quyết mọi vấn đề:** Gateway signer bị compromise vẫn có thể phát claim sai; bearer token không tự chống replay nếu bị lộ; audience validation và short TTL vẫn cần. Network isolation, mTLS, resource authorization, monitoring và revocation policy nên tiếp tục duy trì.

### Một điểm về mTLS

Nếu backend chỉ nhận mTLS từ P2, ứng dụng biết peer là P2 nhưng **chưa chắc P2 đã xác thực user**. Chứng cứ end-to-end của P1 có thể là signed assertion; hoặc P2 phải bảo đảm chỉ P1 được phép cấp identity và không nhận nguồn bypass. Không dùng untrusted **X-Forwarded-Client-Cert** như một certificate đã được app trực tiếp xác minh qua TLS.

## 20. Checklist triển khai kiểm thử tại doanh nghiệp

- [ ] Có sơ đồ mọi hops và alternate backend paths, gồm CDN/WAF/SSO gateway/ingress/mesh/admin listener.
- [ ] Xác định duy nhất **identity issuer** được phép phát trusted user claim.
- [ ] Public edge bỏ các identity headers từ client, gồm aliases/duplicate/underscore variants.
- [ ] Gateway kiểm OIDC/SAML/session thực sự, overwrite canonical subject mỗi request.
- [ ] Ingress nội bộ chỉ nhận identity từ đúng authenticated gateway workload/service account.
- [ ] Backend không public và chỉ nhận traffic qua allowlisted ingress, có ACL/NetworkPolicy/mTLS thích hợp.
- [ ] Test **direct-to-backend** từ untrusted namespace/device được phép; thử cả có và không có forged header.
- [ ] Test **P2 bypass** từ một upstream không qua SSO, dù P2 có mTLS với backend.
- [ ] Positive control user reader-42 thật sự login thành công qua gateway.
- [ ] Forged user/role/tenant/email headers không đổi Authentication, authorities hoặc tenant.
- [ ] Không gán quyền từ raw X-Roles/X-Admin/X-Groups.
- [ ] Không coi XFF/Forwarded là proof user login; trusted-hop parsing và IP policy được test.
- [ ] Host/Proto/Prefix poisoning không đổi SSO redirect_uri/ACS/Location hoặc cookie security.
- [ ] Header duplication, case, aliases, Connection header, HTTP/1.1↔HTTP/2 được xử lý thống nhất.
- [ ] Spring SecurityFilterChain, /admin, /api, /actuator và alternate routes đều được audit.
- [ ] Pre-auth filter được đặt đúng chain; không auto-register trùng và không có fallback auth ngoài policy.
- [ ] Local UserDetailsService kiểm account enabled/tenant, không tự tạo administrator theo header.
- [ ] Nếu dùng stateful backend, session logout/expiry/principal-change được test; nếu stateless, request mới cần trusted identity mới.
- [ ] CSRF/Origin/Cookie SameSite/Secure/HttpOnly phù hợp browser SSO.
- [ ] Nếu dùng JWT assertion, verify signature/iss/aud/exp/alg/key rotation tại backend.
- [ ] Gateway outage phải **fail closed**, không đi tiếp bằng user mặc định hoặc cached header.
- [ ] Test không dùng real admin/prod secrets, không quét ngoài staging đã cấp phép.
- [ ] Observability có sanitized subject, route, source service identity, deny reason và trace; không log tokens/cookies.
- [ ] Kết quả test phân biệt deny tại network, gateway, Spring preauth, local authorization.
- [ ] CI/staging chạy regression suite sau thay proxy, ingress, service mesh, SSO gateway và Spring Security version.

**Kết luận:** Kiểm thử SSO qua gateway không dừng ở “đăng nhập thành công” hoặc “API trả 401 khi không có cookie”. Hệ thống phải chứng minh **client không thể tự chọn user bằng HTTP header** và **không có đường nào đưa header giả đến backend mà bỏ qua authentication gateway**. Khi thiết kế test, luôn tách: **ai xác thực user**, **ai được phép phát identity assertion**, **ai được phép chuyển tiếp**, **backend có tự verify assertion không**, và **ứng dụng đã kiểm quyền tài nguyên chưa**. Một RequestHeaderAuthenticationFilter được cấu hình đúng API vẫn có thể tạo lỗ hổng nếu các trust boundaries không được kiểm chứng.

## 21. Tài liệu tham khảo

- [Spring Security 6.5 – Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): RequestHeaderAuthenticationFilter, PreAuthenticatedAuthenticationProvider, yêu cầu bảo vệ header từ external authenticator.
- [Spring Security 6.5 – RequestHeaderAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): principalRequestHeader, exceptionIfHeaderMissing.
- [Spring Security 6.5 – AbstractPreAuthenticatedProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): context persistence, failure handling và principal-change checking.
- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContextRepository, session lifecycle.
- [Spring Framework 6.2 – ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): trust boundary, forwarded headers, removeOnly.
- [Spring Boot 3.5 – ForwardHeadersStrategy API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.ForwardHeadersStrategy.html): NONE/NATIVE/FRAMEWORK.
- [RFC 7239 – Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): for/by/host/proto và security considerations.
- [OWASP Web Security Testing Guide – Bypassing Authorization Schema](https://owasp.org/www-project-web-security-testing-guide/): test unauthorized/forced browsing và authorization boundaries.
- [OWASP WSTG – Other HTTP Security Header Misconfigurations](https://owasp.github.io/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management/14-Other_HTTP_Security_Header_Misconfigurations): header injection, hop-by-hop handling, header stripping concerns.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, authorization cho từng tài nguyên.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login/session trust boundaries.
- [MDN – X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): xử lý forwarded IP và nguy cơ spoofed values.
