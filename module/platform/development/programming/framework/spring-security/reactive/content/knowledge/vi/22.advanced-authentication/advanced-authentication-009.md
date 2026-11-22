# Phân biệt mTLS tại proxy với danh tính đã được ứng dụng xác minh

## 1. Vấn đề: “Gateway đã kiểm mTLS” có nghĩa ứng dụng đã biết người gọi chưa?

Một hệ thống Spring WebFlux thường đứng sau API Gateway, Ingress Controller, Envoy, NGINX hoặc service mesh. Bên ngoài, client gửi request qua **mutual TLS (mTLS)**: cả server và client xuất trình chứng chỉ phù hợp trong quá trình TLS handshake. Gateway có thể xác minh certificate chain, chính sách CA và thông tin trong chứng chỉ, sau đó chuyển request vào backend WebFlux.

Điều rất dễ nhầm là:

> **Gateway xác thực một kết nối TLS không tự động đồng nghĩa Spring Security ở backend đã xác minh danh tính end-user/workload và cấp đúng quyền ứng dụng.**

Một kiến trúc phổ biến:

~~~text
        mTLS connection 1                 mTLS connection 2 (optional)
Client ----------------------> Proxy ------------------------------> WebFlux API
 cert C                     cert P                cert P           Server
   |                          |                        |               |
   | TLS handshake proves     | TLS to upstream        | Backend        |
   | possession of C private  | proves proxy P         | sees P as TLS   |
   | key to the proxy         | (not necessarily C)    | peer            |
~~~

Các quan sát phải được tách biệt:
- Proxy có thể xác thực client certificate C ở **hop 1**.
- Backend WebFlux kết nối tới proxy ở **hop 2**. Nếu hop 2 có mTLS, backend thường nhận diện **chính proxy P**, không phải C.
- Proxy có thể gửi HTTP header như `X-Forwarded-Client-Cert` (XFCC) hoặc `X-Authenticated-User` nhằm thông báo danh tính đã được nó kiểm tra; đó là **lời khẳng định do upstream gửi**, không phải bằng chứng TLS mà backend tự quan sát.
- Ứng dụng cần **một nguồn authentication đã được bảo vệ và xác minh**, kèm ánh xạ certificate identity → tài khoản/service principal → authorities/roles → quyền trên dữ liệu.
- Một người đã có certificate hợp lệ cũng không mặc nhiên được phép đọc mọi báo cáo hay trở thành ROLE_ADMIN.

Bài này thuộc nhóm **Xác thực mở rộng** của module Spring Security - reactive. Trọng tâm là trust boundary, lựa chọn kiến trúc an toàn và minh họa kiểm chứng thực tế trong Java 17 + Spring WebFlux.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **TLS peer identity**, **gateway assertion**, **Spring Security Authentication**, **business authorization**.
2. Giải thích điều gì được kiểm tra ở TLS handshake và điều gì không thể suy ra từ HTTP header.
3. Nhận biết khi nào `ServerHttpSecurity.x509(...)` có ý nghĩa; khi nào app chỉ thấy proxy certificate.
4. Xử lý đúng XFCC/X-Forwarded-* headers, tránh header spoofing và confused deputy.
5. Thiết kế hai phương án: **mTLS trực tiếp vào ứng dụng** hoặc **proxy mTLS + app kiểm chứng identity assertion**.
6. Dùng Reactive OAuth2 Resource Server xác minh một JWT assertion được gateway tin cậy ký, với `iss`, `aud`, `exp`, signature và scopes.
7. Viết WebTestClient tests: giả header không được xác thực, JWT ký hợp lệ thành công, sai chữ ký/issuer/audience/expiration bị từ chối, thiếu quyền trả 403.
8. Phân biệt local test có JWT ký thật với integration test cần TLS handshake/certificate/proxy thật.
9. Thiết kế audit, vận hành certificate rotation/revocation, network isolation và nhiều hop gateway.

## 2. Cơ chế mTLS thực sự xác minh điều gì?

TLS thông thường: client xác minh server certificate để biết endpoint đang giao tiếp với server có tên/khóa tin cậy. Với **mTLS**, phía server còn yêu cầu client đưa chứng chỉ và chứng minh possession của private key tương ứng trong TLS handshake.

Ở kết nối mà mTLS kết thúc, bên xác minh có thể:
- Xác minh chain của client certificate đến trust anchor/CA tin cậy.
- Kiểm tra certificate còn thời hạn, thuật toán/signature và constraints.
- Kiểm tra key usage và extended key usage như `clientAuth` khi chính sách yêu cầu.
- Kiểm chứng peer sở hữu private key tương ứng qua TLS handshake.
- Đọc Subject/SAN/URI SAN (ví dụ SPIFFE ID), fingerprint, issuer và serial number.
- Áp dụng chính sách trust domain, revocation hoặc workload allowlist theo nền tảng.

**Nhưng** TLS không tự biết “user này có quyền xem hóa đơn số 123” hoặc “workload này có ROLE_ADMIN”. Việc đó thuộc **identity mapping và authorization** của hệ thống.

### 2.1. Certificate subject ≠ tài khoản nội bộ ≠ quyền truy cập

Giả sử certificate có:

~~~text
Subject: CN=report-client,O=Example
URI SAN: spiffe://corp.example/ns/finance/sa/report-reader
Issuer:  CN=Example Workload CA
~~~

Có ba mức:

1. **Certificate identity:** một endpoint đã chứng minh possession của key và có certificate chain phù hợp tại một trust boundary.
2. **Application principal:** hệ thống tra/mapping `spiffe://corp.example/ns/finance/sa/report-reader` thành principal nội bộ như `workload-report-reader`. Có thể cần kiểm tra trạng thái tài khoản, tenant, expiry, risk/entitlements.
3. **Authorization:** principal có được phép gọi `GET /api/reports`, scope `reports.read` và xem bản ghi thuộc tenant của mình không?

Không thay thế bước 2 và 3 chỉ bằng việc certificate có Subject/issuer nhìn “giống công ty”.

### 2.2. CN so với SAN

Nhiều ví dụ X.509 cũ lấy Common Name (CN). Nhưng các hệ thống workload identity hiện đại thường dùng **Subject Alternative Name** loại DNS hoặc URI, ví dụ SPIFFE URI. Một CN có thể trùng, bị tái sử dụng hoặc không biểu thị định danh ứng dụng đủ mạnh.

Dùng SAN với policy tin cậy và identity mapping rõ. Nếu một framework mặc định extract CN, phải xem đó là **default kỹ thuật**, không mặc nhiên là policy tốt nhất cho workload/tenant của tổ chức.

### 2.3. Chứng chỉ hợp lệ không có nghĩa chưa bị thu hồi

Một certificate còn `notAfter` trong tương lai nhưng đã bị revoke hoặc service account đã bị vô hiệu vẫn có thể không còn được phép dùng. Nền tảng phải xét CA revocation policy (CRL/OCSP, short-lived certs, mesh rotation), cách mạng xử lý và authorization state hiện tại.

**TLS certificate validation, account status và quyền tài nguyên là ba kiểm soát khác nhau.**

## 3. Bốn vùng tin cậy cần vẽ trên sơ đồ

~~~text
Untrusted external network
           |
           | Client certificate C, mTLS handshake
           v
+--------------------+
| Trusted proxy/edge |
| - Verify client C  |
| - Map cert -> ID   |
| - Apply edge rules |
+--------------------+
           |
           | Protected hop (TLS/mTLS, network policy)
           | Optionally signed identity assertion
           v
+------------------------------+
| Spring WebFlux Resource API  |
| - Verify gateway assertion   |
| - Construct Authentication   |
| - Map authorities            |
| - Check object/tenant access |
+------------------------------+
           |
           v
         Database
~~~

Mỗi bước cần câu trả lời rõ:

| Câu hỏi | Bên chịu trách nhiệm | Bằng chứng phù hợp |
| --- | --- | --- |
| Client có possession của private key C? | TLS terminator của hop client→proxy | TLS handshake hợp lệ |
| Certificate C có chain/issuer/SAN hợp lệ? | Proxy hoặc policy engine mTLS | TLS verification + cert policy |
| Proxy chuyển đúng identity C hay nhận header giả? | Proxy ingress config | Strip + set trusted headers/assertions |
| Hop proxy→backend có được bảo vệ? | Proxy + backend + network | TLS/mTLS, ACL, network policy, allowlist |
| Backend có tin assertion là của gateway được phép? | WebFlux Security | Signature/JWKS hoặc kênh tin cậy ràng buộc |
| Assertion dành đúng ứng dụng, còn hạn không? | WebFlux decoder/validators | `iss`, `aud`, `exp`, `nbf`, `iat`, `jti` theo policy |
| Principal có quyền gọi route? | Spring Security | GrantedAuthority/permission |
| Principal được đọc bản ghi cụ thể? | Domain service | Ownership/tenant/ABAC/entitlement |

Nếu chỉ kiểm mTLS ở proxy nhưng bỏ các câu hỏi về backend, có thể sinh lỗi **header spoofing, confused deputy, bypass ingress hoặc cross-tenant access**.

## 4. Ba kiến trúc thường gặp và thứ Spring Security quan sát được

### 4.1. Phương án A — Client mTLS trực tiếp với WebFlux

~~~text
Client certificate C
       |
       | TLS handshake directly to Reactor Netty
       v
Spring WebFlux TLS endpoint
       |
       | ServerHttpSecurity.x509(...)
       v
X.509 principal extraction -> account lookup -> Authentication
       |
       v
authorizeExchange -> controller
~~~

Ở đây WebFlux nhận client certificate **trực tiếp từ TLS kết nối mà chính Netty terminates**. Spring Security Reactive có `ServerHttpSecurity.x509(...)`; khi bật, x509 authentication filter lấy certificate từ request TLS info, extract principal và gọi authentication manager.

Điều kiện: Netty TLS listener phải yêu cầu/kiểm client certificate; cần truststore/CA đúng; ứng dụng phải map identity và kiểm authorities. Chỉ bật DSL `x509` mà không cấu hình TLS client-auth **không làm TLS đột nhiên có client certificate hợp lệ**.

### 4.2. Phương án B — Client mTLS đến proxy, backend tin một identity assertion

~~~text
Client --mTLS (C verified)--> Proxy
                                 |
                                 | Mapping + signed JWT assertion:
                                 | iss=gateway, aud=webflux-api,
                                 | sub=client identity, exp≈now+60s
                                 v
                 WebFlux --ReactiveJwtDecoder--> Authentication
~~~

Backend xác minh một **assertion cryptographically signed** bởi gateway/identity service tin cậy. Nó không cần đọc raw client certificate từ HTTP header để tự “tái tạo” TLS proof. Nên bảo vệ thêm hop proxy→backend bằng network policy và TLS/mTLS, đồng thời không mở backend trực tiếp ra Internet.

Assertion được tạo **chỉ sau khi proxy kiểm mTLS C hợp lệ** và mapping thành identity được phê duyệt. Backend xác minh JWT signature, issuer, audience, lifetime và quyền, không nhận `sub` do client gửi tùy ý.

Đây là phương án minh họa bằng project Java17 bên dưới. **JWT gateway assertion không mặc nhiên là OIDC ID token hoặc OAuth access token của client gốc**; đó là một security contract riêng giữa gateway và backend. Spring Security Resource Server hỗ trợ JWT có chữ ký và có thể áp các validators theo contract.

### 4.3. Phương án C — Backend chỉ thấy mTLS của proxy

~~~text
Client --mTLS C--> Proxy --mTLS P--> WebFlux
                                  |
                                  v
                          TLS peer = proxy P
~~~

Backend có thể biết nó đang giao tiếp với proxy P qua mTLS. Điều đó bảo vệ **hop 2** nhưng không chứng minh ai là client C trên hop 1. Nếu dùng `.x509(...)` ở WebFlux trong phương án này, X.509 authentication thường đại diện cho **proxy P**, không phải tự động cho C.

**Không được gán CN/SAN của proxy thành identity của end-user.** Muốn ủy quyền theo client C, phải có thêm cơ chế truyền/kiểm chứng identity của C và mapping ở ứng dụng.

## 5. XFCC và các header danh tính: dữ liệu của HTTP, không phải TLS proof

Nhiều proxy có thể gửi:

~~~http
X-Forwarded-Client-Cert: By=spiffe://corp.example/gateway;Hash=...;Subject="CN=report-client"
X-Authenticated-User: report-reader
X-Forwarded-Proto: https
X-Forwarded-For: 203.0.113.25
~~~

Ý nghĩa:
- `X-Forwarded-Client-Cert` (XFCC) là header có cấu trúc thể hiện certificate information của một hay nhiều hops theo quy ước proxy.
- `X-Authenticated-User` là **header tùy biến**, không có cơ chế chữ ký/validation chung của HTTP.
- `X-Forwarded-For` và `Forwarded` là metadata về đường đi/protocol/client address, **không phải authenticated user identity**.
- `X-Forwarded-Proto=https` chỉ nói upstream cho rằng request gốc dùng HTTPS; **không chứng minh TLS client certificate đã được xác thực**.

Một attacker có thể gửi `curl -H 'X-Authenticated-User: admin'` tới bất kỳ HTTP endpoint nào mà họ chạm được. Nếu backend lấy header đó tạo `Authentication` mà không có trust boundary chặt, attacker có thể impersonate.

### 5.1. XFCC có nhiều thành phần, không parse bằng split ngây thơ

Theo tài liệu Envoy, XFCC ở dạng text có thể gồm nhiều elements ngăn bởi dấu phẩy, các key-value pairs ngăn bởi dấu chấm phẩy, giá trị có thể quoted/escaped; còn có format JSON tùy cấu hình. Nó có thể diễn tả **chuỗi proxy hops**, không chỉ certificate client gốc.

Không viết:

~~~java
// SAI: vừa thiếu trust check, vừa parse XFCC không đúng giao thức.
String user = request.getHeaders()
        .getFirst("X-Forwarded-Client-Cert")
        .split("Subject=")[1];
grantRoleAdmin(user);
~~~

Đây là **anti-pattern**, không phải chương trình hợp lệ để triển khai. Thậm chí parse chính xác format cũng **không khiến header trở thành bằng chứng TLS**.

### 5.2. Nguy cơ header spoofing qua bypass proxy

Nếu backend được expose trực tiếp (Service type LoadBalancer/NodePort, ingress thứ hai, debug port, port-forward, untrusted internal network), attacker có thể gửi header do mình chọn.

Ngay cả khi production ingress chính đã strip headers, một đường vào phụ có thể bypass chính sách. Do đó:
- Chặn direct ingress đến backend bằng network-level controls.
- Chỉ cho phép trusted proxy workload kết nối; dùng mTLS cho hop proxy→backend nếu phù hợp.
- Strip **mọi** identity headers do client mang vào trước khi proxy set bản mới.
- Không có đường không xác thực tới route nhạy cảm.
- Backend nên **tự verify signed assertion** hoặc chứng cứ danh tính tại security layer, không tự tin vì traffic ở mạng private.

### 5.3. Những tên header cần kiểm tra

Ít nhất rà soát:
- `X-Forwarded-Client-Cert` và các biến thể do gateway hỗ trợ.
- `X-Client-Cert`, `X-SSL-Client-Cert`, `SSL_CLIENT_CERT`.
- `X-Authenticated-User`, `X-User`, `X-User-Id`, `X-Remote-User`.
- `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`.
- `Authorization` nếu gateway tạo assertion và client cũng gửi Bearer.

Không chuẩn hóa tất cả trường này thành cùng một identity. **Chỉ một kênh xác thực do hệ thống chọn** mới được dùng để tạo Authentication. Những header còn lại dùng observability/routing sau khi trust đã được xác định, không thay authorization.

## 6. Envoy: SANITIZE, SANITIZE_SET và rủi ro FORWARD_ONLY

Envoy HttpConnectionManager có `forward_client_cert_details` để xử lý XFCC.

Các mode điển hình:
- **`SANITIZE`:** bỏ XFCC khi forward upstream; là lựa chọn mặc định trong tài liệu Envoy.
- **`SANITIZE_SET`:** bỏ XFCC hiện tại rồi đặt lại từ certificate hiện tại của mTLS downstream connection.
- **`FORWARD_ONLY`:** có thể forward XFCC hiện tại khi downstream là mTLS, **không tự thay nội dung bằng identity đã xác minh**.
- **`APPEND_FORWARD`:** append thông tin hiện tại vào chain, khiến việc xác định “hop nào là ai” cần parser/trust policy rõ.
- **`ALWAYS_FORWARD_ONLY`:** forward header kể cả request không có mTLS, đặc biệt nguy hiểm nếu backend tin header như authentication.

Một **mảnh cấu hình** Envoy HttpConnectionManager minh họa (không phải toàn bộ Envoy configuration runnable):

~~~yaml
# Chỉ đoạn field thuộc HttpConnectionManager:
forward_client_cert_details: SANITIZE_SET
set_current_client_cert_details:
  subject: true
  uri: true
~~~

Điều kiện quan trọng: listener **phải có downstream mTLS verification thực sự** nếu mong XFCC thể hiện client cert đã kiểm tra. Snippet trên **không tự cấu hình CA trust, listener, transport_socket, routing hoặc RBAC**.

**SANITIZE_SET giảm spoofing đầu vào nhưng vẫn chưa tự giải quyết app identity**. Spring WebFlux cần biết rằng header thực sự đến từ gateway trusted, không bị bypass, và phải map cert identity → app principal, phân quyền. Với yêu cầu assurance cao, signed assertion như phần 11 giúp backend cryptographically verify nguồn thông báo.

### 6.1. Mối nguy FORWARD_ONLY trong một thiết lập sai

Giả sử client gửi:

~~~http
X-Forwarded-Client-Cert: Subject="CN=admin"
~~~

Nếu proxy giữ nguyên header và backend coi `Subject=CN=admin` như authentication, client có thể giả mạo danh tính. Mặc dù TLS handshake của client có thể mTLS hợp lệ với **CN khác**, việc forward một header do client tự viết vẫn không chứng minh CN=admin.

Giải pháp: strip/sanitize untrusted header, dùng identity assertion chỉ sau certificate verification, và không cho phép direct backend access. Đừng đánh giá an toàn chỉ qua tên biến `X-Forwarded-Client-Cert`.

## 7. Spring Security Reactive X.509 khi ứng dụng trực tiếp kết thúc mTLS

Spring Security có hỗ trợ **Reactive X.509 Authentication**:

~~~java
@Bean
SecurityWebFilterChain directMtlsChain(ServerHttpSecurity http) {
    return http
            .x509(Customizer.withDefaults())
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .build();
}
~~~

Đây là snippet thuộc một cấu hình Spring WebFlux; cần imports `Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`. Nó phù hợp khi Reactor Netty nhận **client certificate từ TLS handshake thật**.

Theo tài liệu Spring Security, khi không cấu hình riêng:
- Default principal extractor trong các bản hiện hành là `SubjectX500PrincipalExtractor`, thường lấy CN từ subject X.500.
- Default authentication manager là `ReactivePreAuthenticatedAuthenticationManager`, kiểm tra user account ứng với tên được trích có tồn tại và không bị locked/disabled/expired.
- Có thể tùy biến `principalExtractor(...)` và `authenticationManager(...)` để áp mapping trust domain/SAN/entitlement chính xác hơn.

**Cấu hình X.509 principal extraction không thay cho truststore và TLS client certificate verification ở server.**

### 7.1. TLS cấu hình tại Reactor Netty / Spring Boot

Mẫu cấu hình (chỉ áp dụng khi bạn có keystore/truststore thật):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-type: PKCS12
    key-store-password: <secure-secret-from-secret-manager>
    trust-store: classpath:trusted-clients.p12
    trust-store-type: PKCS12
    trust-store-password: <secure-secret-from-secret-manager>
    client-auth: need
~~~

Đây là **template**, không thể chạy nguyên trạng vì không có các file PKCS12 và secret thật. Không commit keystore private key hoặc mật khẩu vào repository; dùng secret manager/SSL bundles có quản trị bảo mật.

- `client-auth: need` yêu cầu client certificate trong handshake.
- `client-auth: want` chỉ yêu cầu nếu client có thể gửi, có thể cho connection không certificate đi qua; không dùng `want` làm thay thế assurance bắt buộc.
- `trust-store` quyết định CA/certificates server chấp nhận khi xác minh client.
- TLS server certificate được client verify cho đúng hostname/trust chain.
- Chỉ sau handshake hợp lệ, Spring Security X.509 mới map principal ở request.

### 7.2. Reactive X.509 principal lookup

Ví dụ một tài khoản demo có CN `report-client`:

~~~java
@Bean
ReactiveUserDetailsService users() {
    UserDetails serviceClient = User.withUsername("report-client")
            .password("{noop}unused-for-x509")
            .roles("REPORT_READER")
            .build();
    return new MapReactiveUserDetailsService(serviceClient);
}
~~~

Đây là snippet bổ sung cho flow trực tiếp, không phải cấu hình production. Password `noop` chỉ để dựng UserDetails trong ví dụ; ứng dụng thực không nên bật Basic/password authentication với credential này. X.509 identity mapping trong hệ thống thật phải dựa trên chính sách CA/SAN/trust domain đã xét duyệt, không chỉ xem CN đẹp.

Để bảo vệ một API:

~~~java
.x509(Customizer.withDefaults())
.authorizeExchange(ex -> ex
        .pathMatchers("/api/report/**").hasRole("REPORT_READER")
        .anyExchange().denyAll())
~~~

Nếu certificate đã vượt TLS validation nhưng CN không map tài khoản phù hợp, authentication vẫn thất bại. Nếu account có role nhưng không sở hữu tài liệu cụ thể, domain authorization phải từ chối.

### 7.3. Vì sao không bật .x509 ở backend sau TLS-terminating proxy?

Nếu proxy kết thúc mTLS C rồi mở **kết nối TLS mới dùng certificate P** đến backend, backend chỉ có certificate P trong TLS peer info. Bật `x509` sẽ xác thực **P** (khi được trust/mapping), không “khôi phục” certificate C từ header.

Nếu proxy dùng HTTP không TLS tới backend, `x509` thường không thấy peer certificate nào. Chỉ cần gateway ghi `X-Forwarded-Client-Cert` **không tự điền** vào nguồn TLS peer certificate của Reactor Netty.

## 8. “Đã được ứng dụng xác minh” nghĩa là điều gì?

Trong một app Spring Security, chỉ nên coi danh tính là **authenticated principal** khi:
1. Credential/assertion đến qua một kênh được bảo vệ và có **quy tắc trust** rõ.
2. Bộ xác minh phù hợp đã chạy thành công (TLS client cert tại app, JWT signature/claims, hoặc backend pre-auth trust policy đủ mạnh).
3. Identity được map đến application principal đã biết/được phép.
4. `Authentication` được đặt vào security context của request theo cơ chế Reactive, không bằng cách tự sửa một HTTP header.
5. Controllers/services thực hiện authorization trên principal và dữ liệu.

Nguồn có thể là:
- `ServerHttpSecurity.x509` khi app **trực tiếp** nhận TLS client certificate.
- `oauth2ResourceServer(jwt)` khi app nhận **gateway-signed short-lived JWT assertion** hoặc OAuth access token thật và tự verify.
- Một custom `ReactiveAuthenticationManager`/pre-authentication filter nếu bắt buộc dùng trusted proxy header, nhưng cần network/mTLS/header sanitation, strict parsing, issuer binding, replay controls và quyền rõ; giải pháp này phức tạp, dễ sai hơn signed JWT.

**Đừng tự tạo `UsernamePasswordAuthenticationToken.authenticated("admin", null, ROLE_ADMIN)` chỉ vì một header có chuỗi `admin`.** Việc đó bỏ qua trust checks và có thể nâng quyền.

### 8.1. Identity proof khác authorization proof

Một gateway chứng minh certificate C thuộc workload `report-client` không đồng nghĩa scope `finance.approve` đã được cấp. Backend vẫn cần roles/authorities map từ entitlement đáng tin và object-level checks theo tenant.

Nếu gateway ký JWT với `scope=profile.read`, scope đó phải xuất phát từ một **permission decision đã được kiểm soát**, không phải từ header/parameter do client tự ghi.

## 9. Lựa chọn phương án xác minh: TLS trực tiếp, assertion được ký, hay proxy header?

| Phương án | App nhận được bằng chứng gì? | Yêu cầu tối thiểu | Đánh đổi |
| --- | --- | --- | --- |
| Direct app mTLS + X.509 | Peer certificate từ Netty TLS session | Server truststore, client-auth NEED, principal mapping | App quản lý PKI/trust cert |
| Proxy mTLS + hop2 mTLS, không assertion | Identity của proxy trên hop2 | Trust proxy cert, ACL | Chưa biết C ở hop1 |
| Proxy mTLS + raw XFCC header | Một chuỗi HTTP nói về C | Proxy strip/set, no bypass, hop2 protected, mapping | Dễ giả mạo nếu một đường trust sai |
| Proxy mTLS + JWT assertion do proxy ký | App kiểm signature/iss/aud/exp/sub của assertion | Gateway ký sau mTLS, trusted JWKS, network isolation | Thêm issuance/key rotation/replay policy |
| Client gửi OAuth access token trực tiếp tới backend qua proxy | App tự kiểm access token | Trusted issuer/JWKS, aud, scope | Không tự ràng buộc access token với mTLS cert nếu không có token binding |
| DPoP/mTLS-bound access token | App/API hoặc thành phần xác minh có thêm proof-of-possession | Protocol support, cnf binding và kiểm chứng request | Phức tạp hơn Bearer thuần |

Khuyến nghị tùy kiến trúc:
- Nếu app là TLS terminator: dùng **direct X.509** và mapping principal đúng.
- Nếu edge là mTLS terminator: để **gateway xác thực client certificate**, chuyển identity qua một contract đáng tin (thường **signed short-lived assertion**, hoặc identity service/gateway model được thiết kế cụ thể); app phải xác minh assertion và authorization.
- Với API OAuth2 đã có access token phù hợp: app có thể tự xác minh access token; nếu muốn ràng buộc với mTLS, cần token binding/confirmation claim và proof verification theo RFC 8705 hoặc tương đương, không chỉ kiểm hai thứ riêng rẽ.

## 10. Thiết kế gateway-signed assertion: không biến proxy thành “người ghi tên” vô hạn

Một gateway được phép gắn assertion sau khi đã:
1. Hoàn tất TLS client certificate validation và policy (CA, SAN, trust domain, EKU, revocation khi áp dụng).
2. Map certificate identity C đến **principal được phép**.
3. Xác định permissions cho backend **từ nguồn tin cậy**, không từ HTTP request header.
4. Tạo JWT có chữ ký theo key do gateway/issuer được kiểm soát.
5. Ràng buộc JWT vào backend bằng `aud`, thời hạn ngắn, issuer cố định và optional `jti`.
6. Chỉ forward tới đúng backend qua trust-protected channel.
7. Chặn tất cả direct/untrusted ingress và **strip headers do client gửi trùng tên assertion**.

Ví dụ payload JWT assertion (chỉ là JSON, không phải token đã ký):

~~~json
{
  "iss": "https://gateway.example.test/assertions",
  "aud": ["internal-profile-api"],
  "sub": "spiffe://corp.example/ns/finance/sa/report-reader",
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790000060,
  "jti": "one-time-or-unique-id",
  "scope": "profile.read",
  "authn_method": "client_certificate",
  "cert_sha256": "thumbprint-metadata-if-policy-requires"
}
~~~

**Mọi claims trên chỉ được tin sau khi application đã verify JWT.** Payload được Base64URL encode, không phải được mã hóa; không đặt private-key material hoặc dữ liệu nhạy cảm không cần thiết trong JWT. Thời hạn khoảng 60 giây là ví dụ thiết kế, **không** là mặc định chung.

### 10.1. Tại sao bắt buộc aud và issuer?

- `iss` giúp app chỉ nhận assertion từ gateway/identity issuer được ủy quyền.
- `aud` bảo đảm token cấp cho **chính backend** đang gọi, ngăn tái sử dụng assertion của service A tại service B.
- `exp`/`nbf` giới hạn thời gian, cùng clock skew nhỏ.
- `scope`/entitlements chỉ cho quyền đã được phê duyệt.
- `sub` biểu thị user/workload identity, không phải một role.

JWT có chữ ký hợp lệ nhưng issuer lạ, audience sai hoặc quá hạn phải bị từ chối. Đừng tắt audience validation để “fix 401”.

### 10.2. Chữ ký assertion không tự bảo đảm hop2 mTLS

Nếu backend cho phép bất kỳ client nào gửi token gateway-signed hợp lệ, đó vẫn là **Bearer token có thể replay** trong lifetime của nó. Phải bảo vệ hop2, lưu token ngắn, kiểm `jti`/replay policy khi cần, kết hợp mTLS/DPoP/token binding hoặc request-bound signature nếu threat model yêu cầu.

Signed assertion + hop2 mTLS thường là hai biện pháp **bổ sung**: một cái xác minh **asserted end-client identity**, cái kia xác minh **transport peer gateway**.

### 10.3. Mapping certificate thành sub phải có policy

Không dùng nguyên `CN` làm username duy nhất trong mọi issuer. Nên map từ:
- Trusted CA/trust domain.
- SAN URI hoặc DNS name thuộc namespace được quản trị.
- Certificate policy/EKU.
- Revocation/account status.
- Explicit allowlist/entitlement mapping.

Nếu một gateway nhận mTLS certificate hợp lệ của client X nhưng cho client tự chọn claim `sub=admin`, backend không thể sửa được nếu gateway đã ký thông tin sai. **Ký số chứng minh assertion do gateway phát**, không chứng minh mọi quyết định của gateway đều đúng. Vì thế security review bắt buộc bao gồm cả **mã mapping và quyền ký của gateway**.

## 11. Dự án Java 17+ runnable: WebFlux chỉ tin JWT assertion đã ký

Dự án dưới đây minh họa **phương án B**: backend không tin những headers `X-Authenticated-User` hoặc `X-Forwarded-Client-Cert` do HTTP request mang đến. Nó xác thực identity từ **JWT ký bởi một gateway giả lập trong test** bằng `ReactiveJwtDecoder` thật.

Quan trọng:
- **Không có proxy/mTLS thực trong project**. Test tạo một RSA keypair cục bộ để đóng vai gateway issuer và ký token; security app thực sự kiểm chữ ký RSA và claims.
- Các URL issuer/JWKS ở `application.yml` là hostname mô phỏng. App boot được và public route hoạt động; muốn xác thực request ở runtime ngoài test phải thay bằng gateway/issuer có JWKS thực.
- Không thể dùng các test này để kết luận TLS handshake, SAN policy, certificate revocation hay Envoy header sanitization đã đúng; các phần đó cần E2E tests khác.
- API minh họa chỉ nhận Bearer assertion được client đưa vào HTTP. Trong kiến trúc thật, **gateway** tạo/ghi đè token header sau mTLS; không expose backend trực tiếp.
- Nếu tổ chức sử dụng OAuth 2.0 access token của người dùng thay gateway assertion, có thể dùng Resource Server tương tự, nhưng trust issuer, claim semantics và certificate binding có thể khác.

### 11.1. Cấu trúc thư mục

~~~text
webflux-gateway-identity/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── IdentityController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        └── GatewayAssertionHttpTest.java
~~~

### 11.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-gateway-identity'
~~~

### 11.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng starter **Resource Server** vì app nhận JWT có chữ ký. Nó không cấp JWT, không thực hiện OAuth2 Login và không tự xác minh cert của người gọi ở hop client→proxy.

### 11.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-gateway-identity
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://gateway.example.test/assertions
          jwk-set-uri: https://gateway.example.test/assertions/jwks
          audiences:
            - internal-profile-api
~~~

- `issuer-uri`: cố định nguồn assertion được tin.
- `jwk-set-uri`: nơi tải public keys để kiểm chữ ký của gateway/identity issuer.
- `audiences`: ràng buộc assertion dành cho `internal-profile-api`.

**Đây không phải endpoint thật.** Test thay decoder qua TestConfiguration, nên không phụ thuộc JWKS network. Ứng dụng ở production phải kết nối issuer/JWKS hợp lệ qua HTTPS, triển khai key rotation và kiểm thêm các claim/token profiles phù hợp.

### 11.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Không dùng cookie login trong demo Bearer-only này.
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/identity")
                                .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/private")
                                .hasAuthority("SCOPE_profile.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Phân tích:
- Không có `headers("X-Authenticated-User")`, không đọc `X-Forwarded-Client-Cert` để tạo principal.
- Mỗi request API protected đòi một JWT mà `ReactiveJwtDecoder` xác minh.
- `JwtAuthenticationToken` đưa principal/authorities vào Reactive security context.
- `SCOPE_profile.read` đến từ claim `scope=profile.read` của JWT **đã xác minh**.
- `anyExchange().denyAll()` chặn route/method chưa khai báo.
- CSRF tắt **chỉ vì demo Bearer-only không có ambient browser cookie credentials**; nếu app dùng login session/cookie/Basic, phải thiết kế CSRF khác.
- `NoOpServerSecurityContextRepository` không lưu authentication giữa các requests, không có nghĩa mọi WebSession bị vô hiệu.
- Tại production vẫn cần restrict network path, backend mTLS, signed assertion TTL/replay policy; code này không tự kiểm tra địa chỉ proxy.

### 11.7. IdentityController.java

`src/main/java/demo/IdentityController.java`:

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/identity")
    public Mono<Map<String, Object>> identity(
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.just(Map.of(
                "principal", jwt.getSubject(),
                "issuer", jwt.getIssuer().toString(),
                "audience", jwt.getAudience()));
    }

    @GetMapping("/api/private")
    public Mono<Map<String, String>> privateData(
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.just(Map.of(
                "principal", jwt.getSubject(),
                "result", "AUTHORIZED"));
    }
}
~~~

Trường `principal` đến từ **verified JWT**, không phải một HTTP header có thể bị spoof. DTO cố tình không trả `jwt.getTokenValue()` hoặc toàn bộ claims. Ở production, subject/issuer cũng có thể là thông tin nhạy cảm; chỉ expose tối thiểu cần thiết và áp quyền object-level cho dữ liệu thật.

## 12. Test thật chữ ký RSA và JWT claim validation qua WebTestClient

Project sử dụng RSA keypair được sinh **trong bộ nhớ của test**, làm một gateway signer mô phỏng. `NimbusReactiveJwtDecoder` với RSA public key của test thực sự verify chữ ký rồi kiểm issuer/audience/timestamps. Điều này mạnh hơn test `mockJwt()`, vì có negative case ký bằng khóa không được tin.

**Nhưng nó vẫn không mô phỏng một TLS handshake của client với proxy.** Phần mTLS phải được kiểm ngoài bằng gateway/TLS/certificate fixtures.

### 12.1. GatewayAssertionHttpTest.java

`src/test/java/demo/GatewayAssertionHttpTest.java`:

~~~java
package demo;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(GatewayAssertionHttpTest.TestKeys.class)
class GatewayAssertionHttpTest {

    private static final String ISSUER =
            "https://gateway.example.test/assertions";
    private static final String AUDIENCE =
            "internal-profile-api";
    private static final String SUBJECT =
            "spiffe://corp.example/ns/finance/sa/report-reader";

    private static final KeyPair SIGNER = keyPair();
    private static final KeyPair ATTACKER = keyPair();

    @TestConfiguration(proxyBeanMethods = false)
    static class TestKeys {
        @Bean
        @Primary
        ReactiveJwtDecoder localSignedAssertionDecoder() {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder
                            .withPublicKey(
                                    (RSAPublicKey) SIGNER.getPublic())
                            .build();
            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            JwtValidators.createDefaultWithIssuer(ISSUER),
                            new JwtClaimValidator<List<String>>(
                                    "aud",
                                    aud -> aud != null
                                            && aud.contains(AUDIENCE))));
            return decoder;
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private static KeyPair keyPair() {
        try {
            KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static String signed(
            KeyPair key,
            String issuer,
            String audience,
            String scope,
            Instant expiresAt) throws JOSEException {

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject(SUBJECT)
                .audience(audience)
                .issueTime(Date.from(now.minusSeconds(10)))
                .notBeforeTime(Date.from(now.minusSeconds(10)))
                .expirationTime(Date.from(expiresAt))
                .claim("scope", scope)
                .build();

        SignedJWT jwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID("trusted-gateway-key")
                        .build(),
                claims);
        jwt.sign(new RSASSASigner(
                (RSAPrivateKey) key.getPrivate()));
        return jwt.serialize();
    }

    private String valid(String scope) throws JOSEException {
        return signed(SIGNER, ISSUER, AUDIENCE, scope,
                Instant.now().plusSeconds(120));
    }

    @Test
    void publicPingWithoutAuthenticationIs200() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousWithSpoofedUserHeaderIsStill401() {
        client.get().uri("/api/identity")
                .header("X-Authenticated-User", "admin")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void forgedXfccWithoutJwtIsStill401() {
        client.get().uri("/api/identity")
                .header("X-Forwarded-Client-Cert",
                        "Subject=\"CN=admin\"")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validSignedIdentityWinsOverSpoofedHeader()
            throws JOSEException {
        client.get().uri("/api/identity")
                .header("Authorization", "Bearer " + valid("profile.read"))
                .header("X-Authenticated-User", "admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principal").isEqualTo(SUBJECT)
                .jsonPath("$.issuer").isEqualTo(ISSUER)
                .jsonPath("$.audience[0]").isEqualTo(AUDIENCE);
    }

    @Test
    void correctScopeCanAccessPrivateEndpoint()
            throws JOSEException {
        client.get().uri("/api/private")
                .headers(h -> h.setBearerAuth(valid("profile.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.result").isEqualTo("AUTHORIZED");
    }

    @Test
    void missingScopeIs403EvenIfJwtIsValid()
            throws JOSEException {
        client.get().uri("/api/private")
                .headers(h -> h.setBearerAuth(valid("other.scope")))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongIssuerIs401() throws JOSEException {
        String jwt = signed(SIGNER,
                "https://attacker.example.test", AUDIENCE,
                "profile.read", Instant.now().plusSeconds(120));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() throws JOSEException {
        String jwt = signed(SIGNER,
                ISSUER, "another-backend",
                "profile.read", Instant.now().plusSeconds(120));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void expiredAssertionIs401() throws JOSEException {
        String jwt = signed(SIGNER,
                ISSUER, AUDIENCE,
                "profile.read", Instant.now().minusSeconds(3600));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void attackerSignedAssertionIs401() throws JOSEException {
        String jwt = signed(ATTACKER,
                ISSUER, AUDIENCE,
                "profile.read", Instant.now().plusSeconds(120));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void missingBearerTokenIs401() {
        client.get().uri("/api/identity")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void malformedBearerTokenIs401() {
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth("not-a-signed-jwt"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

### 12.2. Tại sao test này có ý nghĩa?

- Test `anonymousWithSpoofedUserHeaderIsStill401` chứng minh **HTTP header không tự tạo authentication** ở backend.
- Test `forgedXfccWithoutJwtIsStill401` chứng minh XFCC tự khai không được backend chấp nhận.
- Test `validSignedIdentityWinsOverSpoofedHeader` dùng assertion **được ký bằng private key test mà decoder tin public key tương ứng**; principal lấy từ JWT, không từ chuỗi `admin` trong header.
- Test sai issuer/audience chứng minh **chữ ký đúng vẫn không đủ**.
- Test sai chữ ký chứng minh **claims trông giống hợp lệ vẫn không đủ**.
- Test token hết hạn chứng minh giới hạn thời gian vẫn áp dụng.
- Test đúng chữ ký nhưng scope sai trả 403: identity verification khác authorization.
- Tests còn lại xác nhận no token/malformed token và public route.

**Tổng cộng 12 test methods** trong file, dự kiến PASS khi dependencies/API version đúng. Đây là **mã được thiết kế để người học tự biên dịch và chạy**, không phải bản ghi đã chạy Gradle thực tế.

### 12.3. Có kiểm thực JWT nhưng chưa kiểm mTLS thật

`NimbusReactiveJwtDecoder.withPublicKey(...)` ở TestConfiguration kiểm JWS bằng RSA public key. `@Import(TestKeys.class)` cung cấp decoder này cho Spring Security tại test context; Spring Boot decoder từ URL placeholder không được dùng trong các requests test.

Nhưng test **không chứng minh**:
- Proxy yêu cầu client certificate ở TLS handshake.
- Cert chain/issuer/KeyUsage/EKU/SAN được kiểm.
- `SANITIZE_SET` đã chạy trong gateway.
- Backend không thể bị truy cập trực tiếp từ một network không tin.
- Proxy certificate được backend verify ở hop 2.
- Assertion chỉ được gateway phát sau mTLS thành công.
- Certificate revocation hoạt động.
- Token binding chống replay đã được triển khai.

Cần TLS/Envoy/Kubernetes integration tests riêng cho các điều kiện này; không nói WebTestClient mocks là đủ.

## 13. Chạy ứng dụng và quan sát HTTP

Trong thư mục chứa `build.gradle`:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có Gradle Wrapper, sử dụng `./gradlew test` hoặc `gradlew.bat test` theo hệ điều hành. Dự kiến **12 phương thức @Test**; Gradle output thực tế còn tùy cấu hình và môi trường, nên không ghi stdout giả như thể đã chạy.

Ứng dụng trên `http://localhost:8080` chỉ phục vụ demo về security layer. Vì `application.yml` dùng issuer/JWKS giả, không có real gateway assertion để xác minh trong một app bootRun thông thường; muốn thử happy path hãy dùng tests RSA local hoặc thay config bằng issuer/gateway thật trên staging.

### 13.1. Public ping

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng **200 OK**, body:

~~~text
pong
~~~

### 13.2. Header giả không cấp quyền

~~~bash
curl -i http://localhost:8080/api/identity \
  -H 'X-Authenticated-User: admin'
~~~

Kỳ vọng **401 Unauthorized**. Đây là dấu hiệu app **không tin raw header** làm danh tính. Trường hợp thiếu JWT cũng 401, dù client có thể gửi XFCC được tạo bằng tay.

### 13.3. Chỉ token đúng từ gateway/issuer mới được tin

~~~bash
curl -i https://api-staging.example.test/api/identity \
  -H 'Authorization: Bearer <gateway-signed-assertion>'
~~~

Đây chỉ là template, không có token thật. Sau khi triển khai proxy→app trust model và issuer thật, backend phải kiểm JWT signature/iss/aud/exp. Token đúng → 200, token sai → 401.

**Không đưa raw JWT/token production vào shell history chung, logs, screenshot hay ticket.** JWT assertion là Bearer credential, có thể replay trong thời hạn nếu bị lấy cắp; chỉ chạy thử bằng dữ liệu kiểm thử.

### 13.4. Vì sao curl không chứng minh mTLS handshake?

`curl -H 'X-Forwarded-Client-Cert: ...'` chỉ gửi text header, không gửi TLS certificate. Để test mTLS ở proxy phải dùng client cert/private key hợp lệ:

~~~bash
# Lệnh minh họa, chỉ khi đã có cert/key do tổ chức cấp.
curl --cert client.pem --key client.key \
  --cacert trusted-gateway-ca.pem \
  https://gateway-staging.example.test/api/identity
~~~

Không có file cert/key thật trong bài. Proxy phải verify client certificate tại TLS, map identity và phát assertion. Nếu cần client key password, dùng secret handling an toàn; không commit client.pem/client.key hoặc đưa lên môi trường chung.

## 14. Đối chiếu HTTP lỗi 401/403 với TLS handshake failure

| Tình huống | Bên từ chối | Kết quả thường gặp |
| --- | --- | --- |
| Không gửi client certificate nhưng proxy yêu cầu mTLS NEED | TLS terminator | TLS handshake thất bại; **chưa chắc có HTTP status** |
| Client cert không có CA trusted/đã hết hạn | TLS terminator | TLS handshake/certificate validation failure |
| Client cert hợp lệ, mapping không được cấp quyền tại gateway | Gateway auth policy | Thường 403 hoặc gateway-specific failure |
| mTLS hop 1 hợp lệ, app không có signed assertion | Spring Security backend | 401 |
| Attacker gửi X-Authenticated-User/XFCC giả, không JWT | Spring Security backend | 401 |
| JWT signed assertion sai issuer/audience/expiry/signature | Spring Security backend | 401 |
| JWT đúng, thiếu `SCOPE_profile.read` | AuthorizationWebFilter/backend | 403 |
| JWT đúng scope, tenant/object không thuộc principal | Domain authorization | 403/404 theo policy |
| Backend chỉ thấy proxy P qua TLS hop 2 | Network/TLS/app | Peer TLS identity là P; chưa có end-client C |
| JWT đã verify nhưng backend bị bypass từ Internet | Hạ tầng sai | JWT vẫn bảo vệ auth, nhưng rủi ro replay/bypass khác còn |
| Certificate đã bị revoke nhưng gateway không kiểm policy | Gateway/PKI sai | App chỉ biết assertion gateway đã phát; cần sửa gateway |

**TLS handshake failure không đồng nghĩa 401.** Nếu client không thiết lập được TLS connection, HTTP handler chưa nhận request để trả 401/403.

## 15. Mẫu proxy pre-auth bằng raw header: chỉ khi trust boundary được chứng minh

Một số tổ chức có hạ tầng sẵn: edge xác thực mTLS, chỉ nội bộ được gửi vào backend, gateway luôn ghi đè `X-Authenticated-User` và app dùng custom filter để build principal. Đây là **mô hình pre-authentication**, không nhất thiết sai nếu được thiết kế nghiêm ngặt, nhưng nhiều giả định an toàn nằm ngoài mã Java.

Trước khi dùng:
1. Gateway bắt buộc client mTLS cho mọi route nhạy cảm.
2. Strip mọi identity headers client gửi, ghi đè header từ kết quả cert validation.
3. Backend chỉ reachable từ gateway workload, không có debug/direct ingress.
4. Hop proxy→backend được bảo vệ, có kiểm peer proxy khi thích hợp.
5. Header format, encoding, dấu phẩy, duplicates và multi-hop forwarding được định nghĩa rõ.
6. App chỉ tạo Authentication khi request chắc chắn đến từ trusted gateway, không dựa vào X-Forwarded-For do client đưa vào.
7. Identity map với tài khoản/tenant/role từ nguồn tin cậy; không tự cấp ADMIN theo header.
8. Cần xử lý header replay nếu attacker ở cùng mạng có thể ghi requests.
9. Các bypass/negative tests chạy từ những mạng/vùng khác nhau.
10. Mọi thay đổi ingress/gateway config cần security review vì có thể làm hỏng giả định của app.

**Không có một boolean `trust-all-proxy-headers=true` có thể thay thế toàn bộ các yêu cầu trên.** Với khả năng vận hành, signed JWT assertion có validation tại app thường cho ranh giới tin cậy rõ và dễ kiểm thử hơn.

### 15.1. Vì sao chỉ kiểm IP proxy là chưa đủ?

IP source có thể thay đổi vì NAT/load balancer, IP reuse, proxy chaining, pods và cloud networking. `X-Forwarded-For` có thể đến từ client nếu không được proxy sanitize. Chỉ dựa vào CIDR mà bỏ TLS peer validation không chứng minh mạnh một request thật sự do gateway mà bạn tin tạo ra.

IP allowlist/network policy nên là **lớp phòng thủ bổ sung**, không mặc nhiên là cơ chế duy nhất để grant ROLE_ADMIN.

## 16. Authenticated client certificate chưa tự ràng buộc Bearer access token

Có trường hợp gateway vừa thấy certificate C, vừa forward `Authorization: Bearer TOKEN`. Nếu backend chỉ verify token JWT một cách độc lập, app biết token hợp lệ; nhưng **không tự biết holder của token chính là chủ nhân certificate C**.

Nếu cần OAuth2 mTLS sender-constrained access token theo RFC 8705:
- Authorization Server phát token được ràng buộc với certificate, thường qua `cnf` thumbprint như `x5t#S256`.
- Resource Server hoặc trusted enforcement point phải kiểm certificate mà presenter thực sự dùng phù hợp confirmation claim đó.
- Với TLS termination ở proxy, cần giao thức truyền **cert identity đã được xác thực** đến backend đáng tin hoặc thực hiện confirmation tại gateway.
- Không được chỉ so `X-Forwarded-Client-Cert` với claim trong token nếu XFCC có thể bị giả.

Tương tự với DPoP (RFC 9449), cần proof JWT ràng buộc request/method/URI và các kiểm tra replay theo spec; không chỉ đọc `cnf` rồi coi như chống replay.

**mTLS tại proxy, OAuth access token và gateway-signed assertion là ba loại bằng chứng có vai trò khác nhau.** Hệ thống phải nêu rõ cái nào là authoritative identity và cái nào là thêm assurance.

## 17. Threat modeling theo các kịch bản tấn công

### 17.1. Kịch bản 1: header spoofing

Attacker gửi:

~~~http
GET /api/private HTTP/1.1
X-Authenticated-User: ceo
X-Forwarded-Client-Cert: Subject="CN=ceo"
~~~

Nếu backend cho phép trực tiếp truy cập và dùng headers tạo Authentication, attacker có thể impersonate. Biện pháp: network isolation, proxy header sanitization, signed assertion/verify ở app, negative tests. Trong project, request này thiếu JWT vẫn 401.

### 17.2. Kịch bản 2: “mTLS tới proxy nhưng backend tin nhầm proxy là user”

Proxy P dùng cert `CN=gateway` đến backend. Backend `x509` trích CN=gateway và một mapping sai cấp ADMIN. Bất kỳ caller nào được proxy forward có thể thừa hưởng role gateway. Biện pháp: không map gateway transport identity thành quyền user; dùng identity assertion của client C và authorization riêng.

### 17.3. Kịch bản 3: trusted proxy ký nhầm subject

Gateway xác minh certificate của report-reader nhưng cho client gửi `sub=admin` qua header rồi ký đúng bằng private gateway key. Backend verify JWT hợp lệ về crypto nhưng nhận identity sai. Biện pháp: gateway **phải tạo sub từ verified cert identity/entitlement**, tuyệt đối không từ client claims chưa tin cậy. Signature không chứng minh correctness của mapping.

### 17.4. Kịch bản 4: assertion bị replay

Attacker lấy một signed gateway assertion còn hạn, gửi lại trong 30–60 giây. Nếu backend là Bearer-only và có đường bypass, request có thể thành công. Biện pháp: hop2 mTLS/network isolation, TTL nhỏ, `jti` one-time/replay store nếu cần, sender-constrained tokens hoặc ký request-bound proof.

### 17.5. Kịch bản 5: giả mạo upstream metadata

Attacker đặt `X-Forwarded-Proto=https`, `X-Forwarded-For=127.0.0.1` để vượt kiểm soát HTTP scheme/IP. Biện pháp: chỉ trust forwarded headers của proxies được xác thực, strip inbound, không dùng forwarded metadata như authentication.

### 17.6. Kịch bản 6: certificate CA quá rộng

Gateway trust một CA có thể cấp cert cho nhiều workload không liên quan. Client sở hữu cert hợp lệ nhưng SAN không nằm trong namespace được phép vẫn có thể vượt certificate chain verification. Biện pháp: authorization theo SAN/trust domain/role, không “trust CA = trust mọi identity”.

### 17.7. Kịch bản 7: app có route ngầm permitAll

Authentication ở /api/private đúng nhưng một route phụ /internal/health/config được permitAll và làm lộ dữ liệu. Biện pháp: `anyExchange().denyAll()`, method-level security, route inventory, ingress policy và negative testing.

### 17.8. Kịch bản 8: nhiều proxy hops và chain confusion

Client→Edge A→Mesh B→Backend. Một hop có thể `APPEND_FORWARD`, hop khác `FORWARD_ONLY`, dẫn đến XFCC chứa nhiều elements và dữ liệu do caller tạo xen kẽ. Biện pháp: xác định authoritative hop, chọn sanitizer, định nghĩa signed assertion end-to-end, không parse “phần đầu hoặc cuối” tùy hứng.

## 18. Kiểm thử tích hợp thật với proxy/mTLS

Các bài test Java WebFlux xác minh crypto JWT và HTTP authorization, nhưng production cần bổ sung E2E:

| Test | Kết quả bắt buộc |
| --- | --- |
| Client không certificate → gateway mTLS-required route | TLS handshake bị từ chối |
| Client certificate hết hạn hoặc sai CA | Proxy từ chối theo policy |
| Client certificate hợp lệ nhưng SAN không allowlist | Không được cấp identity/route |
| Client certificate bị revoke | Theo revocation/short-lived cert policy đã phê duyệt |
| Client được xác thực qua proxy, app nhận signed assertion | Backend chỉ nhận đúng sub đã map |
| Client giả `X-Authenticated-User: admin` | Proxy strip; app không nhận admin |
| Client giả `X-Forwarded-Client-Cert` | Proxy sanitize; không ghi đè cert đã verify |
| Gọi backend trực tiếp bỏ proxy | Bị network policy/mTLS từ chối |
| Gọi qua một ingress thứ hai | Không bypass same security controls |
| Thay signed assertion của gateway bằng token attacker-signed | Backend 401 |
| Token issuer/audience/expiry sai | Backend 401 |
| Token hợp lệ nhưng thiếu role/scope | Backend 403 |
| Token đúng quyền route nhưng khác tenant/object | Domain deny |
| Proxy→backend certificate không phải trusted gateway | TLS peer validation failure |
| Gateway signing key rotation | Không cấp assertion bằng key chưa được verifier tin |
| Stolen signed assertion qua đường khác | Rejection/mitigation theo replay policy |
| WebSocket/gRPC/HTTP2 paths | Trust boundary và auth policy không bị bypass |
| Multi-region failover | Header/identity policy nhất quán tại mọi edge |

**Không cần dùng dữ liệu thật hoặc secrets thật** cho các tests; tạo CA/test certificates, test accounts và signed tokens trong môi trường cô lập.

### 18.1. Negative test từ cùng Pod/network nội bộ

Không chỉ test từ Internet. Một attacker có thể là pod bị chiếm trong cluster, container có network access hoặc service account có quyền rộng. Hãy kiểm:
- Bypass từ internal namespace không được phép.
- Gửi identity headers đến pod IP trực tiếp.
- Gửi tới debug/alternate ports.
- Gửi tới service port mà ingress policy không bảo vệ.
- Peer workload không có SAN/identity đúng có mở được mTLS hop không.

Mục tiêu là xác nhận **backend thật sự không coi network proximity như một role**.

## 19. Troubleshooting: mTLS báo thành công nhưng backend vẫn 401/403

### Backend 401 dù proxy đã verify mTLS

- Proxy có thật sự tạo signed assertion không?
- Assertion nằm trong header đúng tên, được forward qua đúng route?
- Backend dùng `oauth2ResourceServer(jwt)` hay đang đợi `.x509` từ TLS trực tiếp?
- Token có signature, issuer, audience và expiry hợp lệ?
- Gateway đã đổi signing key, JWKS backend cập nhật chưa?
- Đồng hồ proxy/backend có lệch nhiều không?
- Backend có nhận request qua security chain đúng không?
- Có route đi qua gateway thứ hai không có config assertion?

Không “sửa” 401 bằng cách lấy `X-Authenticated-User` làm principal trực tiếp.

### Backend 403 sau khi assertion hợp lệ

- Có `SCOPE_profile.read` hay role cần thiết không?
- `scope` được mapping bằng `JwtGrantedAuthoritiesConverter` đúng claim format?
- `hasAuthority` khác `hasRole` như thế nào?
- Account/tenant mapping còn hợp lệ không?
- Service đã kiểm object ownership và từ chối?
- Có CSRF từ một cookie-based route/chain khác không?
- Gateway đã ký scope sai từ client header? Nếu có, **sửa gateway**, không bỏ authorization.

### Backend chỉ thấy CN=proxy

Nếu backend kết thúc mTLS **hop proxy→backend**, đúng là peer certificate thuộc proxy. Điều này không có nghĩa Spring Security bị lỗi. Muốn biết client C, cần identity assertion từ upstream đã verify hoặc thiết kế passthrough TLS/direct mTLS phù hợp.

### Gửi XFCC nhưng WebFlux x509 principal null

`ServerHttpSecurity.x509` đọc thông tin peer TLS trên kết nối app trực tiếp nhận. XFCC là một chuỗi HTTP header; nó **không tự biến** thành `SslInfo.getPeerCertificates()`. Không tự tạo request wrapper giả SSL info từ XFCC mà bỏ trust checks.

### Có assertion hợp lệ nhưng subject sai

- Xác minh mapping cert SAN→principal ở gateway.
- Kiểm Gateway có tin claims header client không.
- Kiểm nhiều proxy hops/header sanitization.
- Kiểm tenant/workload delegation policy.
- Kiểm raw certificate subject đã được validate, không dùng CN suffix làm role.
- Kiểm signer identity, audit trail và key rotation.

## 20. Checklist triển khai an toàn

### TLS và proxy
- [ ] Proxy yêu cầu client mTLS trên các routes bắt buộc.
- [ ] CA/trust domain, SAN, EKU, expiry, revocation policy được định nghĩa rõ.
- [ ] TLS terminator biết client certificate C; backend biết hop nào thực sự có client cert.
- [ ] Proxy→backend có network isolation, TLS/mTLS và authenticated proxy peer khi phù hợp.
- [ ] Không có direct backend route/alternate ingress/port bypass.
- [ ] XFCC/X-Authenticated-User và mọi identity headers từ client bị sanitize/overwrite.
- [ ] Không dùng FORWARD_ONLY/ALWAYS_FORWARD_ONLY để tạo trusted principal.
- [ ] Forwarded/X-Forwarded-* chỉ được tin qua trusted proxies và cho đúng mục đích.
- [ ] Có audit thay đổi gateway routes, Envoy/Istio filters, network policy.

### Danh tính và signed assertion
- [ ] Gateway chỉ ký assertion sau khi certificate validation và mapping thành công.
- [ ] `sub` bắt nguồn từ trusted certificate identity/account mapping.
- [ ] `iss` cố định, `aud` ràng buộc chính backend.
- [ ] Kiểm JWS signature, allowed algorithms, `exp`/`nbf`/`iat`/`jti` theo policy.
- [ ] Signing private key được giữ tại issuer; backend chỉ có public verification keys.
- [ ] TTL assertion ngắn, anti-replay và sender binding được xét theo threat model.
- [ ] Headers/token values không được log ở edge và backend.
- [ ] Gateway không cấp scopes bằng cách copy tham số do client gửi.
- [ ] Principal được map vào role/tenant/entitlements từ nguồn tin cậy.
- [ ] App kiểm ownership ở service, không chỉ HTTP route.
- [ ] Mọi token khác issuer/audience hoặc unsigned/malformed bị từ chối.

### Spring Security Reactive
- [ ] `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder` đúng stack.
- [ ] `.x509` chỉ dùng khi backend trực tiếp nhận TLS client cert hoặc identity peer phù hợp.
- [ ] Nếu proxy kết thúc mTLS, backend **không** coi XFCC là TLS peer.
- [ ] `JwtAuthenticationToken` được sinh từ JWT đã verify, không từ raw header.
- [ ] Không dùng Servlet `HttpSecurity` hoặc tự lưu Authentication vào ThreadLocal.
- [ ] Không dùng `block()` trong Reactive auth filters.
- [ ] Bearer-only CSRF policy tách khỏi cookie/browser flows.
- [ ] HTTP 401 vs 403 giữ semantics đúng; TLS handshake failures khác HTTP auth failures.

### Kiểm thử và vận hành
- [ ] Test spoofed user/XFCC header không tạo authentication.
- [ ] Test token ký thật: đúng/sai issuer, audience, expiry, signature.
- [ ] Test scope/role negative và object/tenant access.
- [ ] Test direct backend bypass và alternate ingress.
- [ ] Test client certificate trust, SAN, expiry/revocation.
- [ ] Test proxy signing-key rotation và TLS cert rotation.
- [ ] Test multi-region/multi-proxy behavior.
- [ ] Có incident response khi private key/gateway bị compromise.
- [ ] Có metrics authentication failure, signer version, gateway decision, không lộ token.
- [ ] Không coi mockJwt() là chứng minh real certificate validation.

## 21. Câu hỏi tự kiểm tra

**1. Client đã được gateway xác thực mTLS, WebFlux có tự biết client SAN không?**

> Không. Nếu TLS kết thúc ở gateway, backend thấy kết nối mới từ gateway; cần identity truyền theo trust contract hoặc TLS passthrough/direct verification.

**2. Backend mTLS với proxy, peer cert là của ai?**

> Thường là certificate của chính proxy trên hop proxy→backend, không phải certificate client của hop trước.

**3. X-Forwarded-Client-Cert có phải TLS proof không?**

> Không. Nó là HTTP header về certificate do upstream khai báo; phải có trusted proxy sanitization và identity contract.

**4. `SANITIZE_SET` có hoàn tất authentication trong ứng dụng không?**

> Không. Nó làm sạch và set XFCC tại proxy trong điều kiện thích hợp, nhưng app vẫn cần trust channel, mapping principal và authorization.

**5. Đưa `X-Authenticated-User: admin` vào curl có đủ login không?**

> Không được đủ. App phải từ chối nếu không có credential/assertion mà nó tự verify.

**6. Khi nào sử dụng `ServerHttpSecurity.x509` hợp lý?**

> Khi Spring WebFlux trực tiếp kết thúc client mTLS, nhận peer certificate thật và có principal mapping phù hợp.

**7. Vì sao không cấp ROLE_ADMIN cho mọi cert của CA nội bộ?**

> Một CA có thể cấp cho nhiều identities; certificate trust khác role entitlement.

**8. Signed gateway assertion cần những claims nào?**

> Tối thiểu issuer/audience/subject/time theo protocol, và permissions theo business policy; thêm jti/replay/certificate binding khi cần.

**9. Chữ ký JWT hợp lệ có đủ để vào /api/private không?**

> Không. Còn issuer, audience, expiration, scope, tenant/ownership và các validators khác.

**10. Test mockJwt() có chứng minh RSA signature hoặc mTLS handshake không?**

> Không. MockJwt bypass JWT decoder; TLS handshake cần integration TLS test riêng.

**11. Nếu gateway ký sub sai từ client header, backend có phát hiện được không?**

> Backend có thể verify signer nhưng không tự biết mapping upstream sai. Phải sửa mapping/sanitization tại gateway và có audit/negative tests.

**12. mTLS có chống replay một gateway JWT assertion bị đánh cắp không?**

> Không tự động. Hop2 mTLS giúp giới hạn presenter, nhưng Bearer assertion vẫn cần lifetime, binding và anti-replay theo threat model.

**13. TLS clientAuth=want và need khác nhau?**

> want cho phép trường hợp không có client cert tùy server policy; need yêu cầu client cert tại handshake.

**14. Vì sao không dùng X-Forwarded-For để biết authenticated user?**

> Nó là metadata đường đi/IP và có thể bị spoof nếu untrusted; không phải xác thực danh tính.

**15. TLS handshake failure có phải 401 không?**

> Thường không. HTTP response có thể không tồn tại vì handshake thất bại trước khi request đến WebFlux.

**16. Access token được mTLS-bound cần thêm điều gì?**

> Confirmation claim/binding và proof-of-possession validation theo RFC 8705; chỉ một access token và một cert ở hai lớp độc lập chưa chắc đã ràng buộc nhau.

## 22. Tổng kết: không nhầm transport trust với application identity

**mTLS tại proxy** chứng minh certificate identity của client cho **proxy** tại TLS hop đó. **mTLS giữa proxy và WebFlux** chứng minh peer transport của hop sau, thường là proxy. **Danh tính đã được ứng dụng xác minh** chỉ hình thành sau khi app nhận và kiểm một bằng chứng đáng tin, map ra principal, rồi enforce authorization.

Hai cách thiết kế rõ ràng:
- **Direct mTLS tại WebFlux:** configure Reactor Netty client-auth/truststore + Spring Security Reactive `.x509(...)` + principal lookup + domain permissions.
- **mTLS ở proxy:** proxy verify cert và mapping, sanitize untrusted headers, phát short-lived signed assertion hoặc cơ chế trust có kiểm soát; backend verify chữ ký, issuer, audience, thời gian, scopes, đồng thời bảo vệ hop proxy→backend và chặn bypass.

**Không dùng header XFCC/X-Authenticated-User tự khai như bằng chứng tương đương TLS handshake.** Kể cả header được proxy set đúng, application phải hiểu trust boundary và kiểm authorization đối với tài nguyên cụ thể.

### Tài liệu tham khảo chính thức

- Spring Security — Reactive X.509 Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/x509.html
- Spring Security — ServerHttpSecurity Reactive API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — Testing Reactive JWT Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot — Common Application Properties (server.ssl.client-auth): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Security — Proxy headers and request trust: https://docs.spring.io/spring-security/reference/features/exploits/http.html
- Envoy — X-Forwarded-Client-Cert header semantics: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/headers.html
- Envoy — HttpConnectionManager forward_client_cert_details/SANITIZE_SET: https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto
- Istio — XFCC and network topology: https://istio.io/latest/docs/ops/configuration/traffic-management/network-topologies/
- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile: https://www.rfc-editor.org/rfc/rfc5280
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens: https://www.rfc-editor.org/rfc/rfc8705
- RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession: https://www.rfc-editor.org/rfc/rfc9449
- SPIFFE — Workload Identity Concepts: https://spiffe.io/docs/latest/spiffe-about/overview/