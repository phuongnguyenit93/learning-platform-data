# Lỗi LDAP, chứng thư, issuer hoặc JWK bị nhầm thành sai mật khẩu

## 1. Tình huống: người dùng báo “sai mật khẩu”, nguyên nhân lại nằm ở hệ thống xác thực

Một ứng dụng Spring Security có thể sử dụng nhiều cơ chế xác thực: form login với LDAP, xác thực client certificate qua TLS/X.509, đăng nhập OAuth2/OIDC từ Identity Provider (IdP), hoặc OAuth2 Resource Server xác minh JWT từ Authorization Server. Khi gặp lỗi, giao diện thường chỉ hiển thị “Đăng nhập không thành công” hoặc client nhận HTTP 401. Điều đó **không chứng minh mật khẩu đã sai**.

Những lỗi hoàn toàn khác nhau có thể dẫn tới cùng trải nghiệm người dùng:

- LDAP server không thể kết nối, hết connection, lỗi DNS, StartTLS hoặc chứng thư LDAPS hết hạn.
- Người dùng tồn tại nhưng DN mapping, group search, referral hoặc tài khoản bị khóa không phù hợp cấu hình.
- TLS mTLS từ chối client certificate **trước khi request tới Spring Security**; thậm chí ứng dụng không nhìn thấy HTTP request.
- Client certificate hợp lệ ở tầng TLS nhưng X.509 principal extraction không lấy được user đúng, hoặc app không tìm thấy mapping sang account.
- Access JWT hợp lệ về cấu trúc nhưng bị từ chối vì `iss`, `aud`, `exp`, `nbf`, `alg`, chữ ký hoặc khóa công khai chưa khớp.
- JWK Set endpoint sai URL, không truy cập được, có TLS/DNS lỗi, cache quá cũ hoặc IdP đang xoay khóa `kid`.
- Frontend dùng **ID token** cho API thay vì **access token**, hoặc token cấp bởi môi trường khác.
- Authentication thực ra thành công nhưng authorization thiếu role/scope, gây 403 mà giao diện vẫn hiển thị “mật khẩu sai”.

Bài thuộc nhóm **Chẩn đoán** của module **Spring Security - authentication**. Mục tiêu là phân biệt **credential thực sự không hợp lệ**, **lỗi danh tính/chính sách**, **lỗi hạ tầng/trust**, **lỗi xác minh token** và **lỗi quyền**, đồng thời không làm lộ thông tin nhạy cảm.

**Nguyên tắc xuyên suốt:** thông báo ra ngoài có thể được chuẩn hóa để chống username enumeration; nhưng log/metric/trace **bên trong, đã lọc dữ liệu** phải đủ phân loại lỗi. Không dùng mã HTTP hoặc một chuỗi `BadCredentialsException` duy nhất làm kết luận nguyên nhân gốc.

## 2. Một sơ đồ quyết định để tránh chẩn đoán nhầm

```text
Request xác thực thất bại
        │
        ├─ Có request đi vào ứng dụng không?
        │    ├─ KHÔNG → kiểm TLS handshake, mTLS, reverse proxy/WAF,
        │    │          certificate chain, SNI, routing, ingress logs
        │    └─ CÓ
        │
        ├─ Cơ chế nào đang xử lý request?
        │    ├─ Form / LDAP → user search, bind/compare, LDAPS,
        │    │                 DNS/connectivity, account policy, groups
        │    ├─ X.509      → chứng thư đã đến Servlet chưa?
        │    │                 subject regex, account mapping, authorities
        │    ├─ OAuth2/OIDC login → authorize/callback, state/nonce/PKCE,
        │    │                      TLS/issuer/IdP metadata, ID token
        │    └─ Bearer JWT API → token format, decoder, iss/aud/time,
        │                        signature, kid/alg/JWK cache/endpoint
        │
        ├─ Đã xác thực nhưng thiếu quyền?
        │    └─ CÓ → kiểm 403, role/scope/tenant, không đổ lỗi mật khẩu
        │
        └─ Chỉ sau khi loại trừ các lớp trên mới kết luận
           credential/password thực sự không hợp lệ
```

Bắt đầu bằng câu hỏi **“request đã đi đến tầng nào?”**, thay vì tự động reset mật khẩu user. Kết quả TLS handshake, thông tin kết nối LDAP, dấu vết `JwtDecoder` hoặc status từ gateway có thể giúp xác định tầng bị lỗi mà không cần nhìn raw password/token.

## 3. Ma trận chẩn đoán nhanh theo cơ chế

| Quan sát | Không nên kết luận | Kiểm tra đáng tin | Hành động đầu tiên |
| --- | --- | --- | --- |
| Form login luôn chuyển `/login?error` | User nhập sai password | LDAP bind/search, service exception, directory status | Correlation ID + log category |
| Chỉ lỗi khi LDAP certificate vừa thay | Password đồng loạt sai | LDAPS trust chain, hostname, expiry, JVM truststore | Thử TLS/DNS an toàn |
| LDAP trả `49 invalidCredentials` | Chắc chắn mật khẩu sai | DN, account lock/expiry, subcode phụ thuộc vendor | So khớp directory policy |
| Request mTLS không xuất hiện trong access log | Spring không nhận user/password | TLS handshake/proxy client-cert verification | Kiểm ingress/TLS logs |
| X.509 request có certificate nhưng app không đăng nhập | Certificate chắc chắn không hợp lệ | Subject extraction, principal mapping, UserDetailsService | Kiểm mapping sau TLS |
| JWT API trả 401 khi token có `iss` khác kỳ vọng | User đăng nhập sai | Issuer string và token origin | So issuer chính xác |
| Chỉ token ký bằng khóa mới bị 401 | User sai credential | JWK Set có `kid` mới chưa, cache/rotation | Kiểm JWKS trusted |
| 401 khi IdP/JWKS DNS timeout | Password hết hạn | Egress/DNS/TLS/JWKS availability | Kiểm dependency |
| Valid token nhưng API trả 403 | JWT/password bị từ chối | Authority/scope/tenant | Xác minh authorization |
| Trong test `jwt()` pass nhưng production 401 | Production “sai password” | Test bypass thật `JwtDecoder` | Kiểm chữ ký/issuer/aud ở integration |

**Chú ý:** HTTP 401 chỉ biểu thị yêu cầu cung cấp xác thực hợp lệ theo protocol; nó không định danh một lỗi password. Với mTLS, handshake fail có thể **không có HTTP status nào**; trạng thái lỗi và logging phụ thuộc proxy, TLS stack và client.

## 4. Spring Security chia xác thực và phân quyền thành các tầng

Một ứng dụng Servlet thường có `FilterChainProxy` chọn `SecurityFilterChain`, rồi các filter xác thực như `UsernamePasswordAuthenticationFilter`, `X509AuthenticationFilter` hoặc `BearerTokenAuthenticationFilter`.

```text
Client
  │
  ├─ TLS / mTLS ──> reverse proxy/ingress/Tomcat
  │                    │ handshake có thể thất bại ở đây
  │                    ▼
  └────────────── HTTP request
                       │
                       ▼
                FilterChainProxy
                       │
             matching SecurityFilterChain
                       │
            Authentication filter/provider
                       │
                AuthenticationManager
                       │
              UserDetails/LDAP or JwtDecoder
                       │
                authenticated principal
                       │
                AuthorizationFilter
                       │
             200 / 401 / 403 / redirect
```

Đừng nhầm:

- **Authentication failure:** không thiết lập được danh tính hoặc credential không hợp lệ. Một Bearer access token bị từ chối có thể dẫn đến `401 WWW-Authenticate: Bearer`.
- **Authentication service failure:** không liên hệ được LDAP/JWKS hoặc trust infrastructure; phản hồi có thể là 401, redirect, 5xx hoặc lỗi do handler custom. **Không có status mặc định thống nhất** cho mọi provider.
- **Authorization failure:** danh tính đã xác thực nhưng thiếu quyền, thường 403.
- **Transport failure:** TLS/mTLS handshake không thành công; app không nhất thiết nhận HTTP request và Spring Security có thể không phát event.

Nếu giao diện front-end gom mọi status thành “Sai mật khẩu”, người dùng sẽ chịu ảnh hưởng và đội vận hành mất dấu hạ tầng. Hãy giữ UX an toàn nhưng phân loại nội bộ theo nguồn thật.

## 5. LDAP: sai password khác lỗi kết nối, bind, search và quyền directory

Spring Security LDAP hỗ trợ nhiều chiến lược. Với **bind authentication**, ứng dụng dùng LDAP để xác thực credential qua bind theo DN; với **password comparison**, provider so sánh password qua attribute/LDAP compare theo cấu hình. Những bước phổ biến:

1. Chuẩn hóa/kiểm tính hợp lệ username (không biến đầu vào user thành LDAP filter thiếu escape).
2. Tìm DN thích hợp bằng pattern hoặc user search; DN mapping sai có thể làm user không tìm thấy.
3. Kết nối directory qua LDAP/LDAPS/StartTLS, thực hiện bind hoặc compare.
4. Load nhóm/quyền qua `LdapAuthoritiesPopulator` nếu cần.
5. Xây `Authentication` rồi lưu context/phiên qua Spring Security nếu đăng nhập web thành công.

**LDAP 49** là kết quả `invalidCredentials` của directory, nhưng **không nhất thiết chứng minh** mật khẩu do người dùng gõ sai. Nó có thể liên quan DN sai, account policy, service account bind sai hoặc cách directory vendor mã hóa chi tiết. Ví dụ Active Directory có các mã phụ trong message như `52e` (credential mismatch), `533` (disabled), `775` (locked), `701` (expired). **Những mã phụ là đặc thù AD, không phải chuẩn chung của mọi LDAP**, và không nên được phơi ra giao diện đăng nhập.

### 5.1. Bảng nhóm lỗi LDAP

| Nhóm | Dấu hiệu khả dĩ | Cần kiểm |
| --- | --- | --- |
| Credential/bind không hợp lệ | LDAP result `49`, `BadCredentialsException` | Password, DN pattern, user mapping, directory-specific policy |
| User không tìm thấy | Search trả 0 entry; `UsernameNotFoundException` có thể bị mask | Search base/filter, OU, UPN/uid, escaping |
| Directory không sẵn sàng | `CommunicationException`, timeout, `ServiceUnavailableException` hoặc wrapper | DNS, firewall, port, pool, server availability |
| LDAPS/StartTLS trust lỗi | `SSLHandshakeException`, `PKIX path building failed`, hostname mismatch | Truststore, certificate chain, SAN, CA, expiry |
| Service bind account lỗi | Search dùng bind DN/password không hợp lệ | Secret rotation, quyền search, account lock |
| LDAP referral sai hoặc vòng lặp | Referral exception, truy vấn qua domain khác | Referral policy, domain topology, URI an toàn |
| Group/authority lookup lỗi | Bind user thành công nhưng groups rỗng/lỗi | Group base, member filter, nested groups, access permission |
| Pool cạn/lỗi mạng gián đoạn | p99 login cao, timeout, max connections | Pool size, timeouts, load, retry/health checks |

**Không sửa LDAP outage bằng cách bỏ qua kiểm mật khẩu**, tắt LDAPS validation hoặc tự gán authenticated=true. Khi không xác minh được danh tính đáng tin, phải fail closed với thông báo chung hoặc trạng thái dịch vụ phù hợp contract.

### 5.2. Một chuỗi chẩn đoán LDAP cụ thể

Ví dụ trước đây Alice đăng nhập tốt, hôm nay mọi user đều gặp thông báo “Invalid username or password”:

1. Kiểm số lượng lỗi theo thời gian: tăng đồng loạt trên nhiều account hay chỉ một account?
2. So đối chiếu hostname/IP/port của directory, DNS resolution, có đổi chứng thư/CA hay service secret không.
3. Kiểm root cause ở server logs sau khi lọc PII: `javax.naming.CommunicationException`/`SSLHandshakeException` khác với LDAP 49.
4. Thử kết nối LDAPS từ **chính network namespace/pod của ứng dụng**, không chỉ từ laptop admin.
5. Nếu kết nối được, kiểm service account search permission, DN pattern/user base và bind flow.
6. Nếu password bind đúng nhưng role thiếu, kiểm group mapping và authorization; có thể HTTP 403 chứ không phải login sai.
7. Chỉ cho phép khôi phục đăng nhập sau khi upstream identity dependency được xác minh và policy an toàn.

Nếu chỉ có một tài khoản lỗi, cũng chưa mặc định password sai: user có thể chuyển OU, bị khóa, disabled, password expired, policy giờ đăng nhập hoặc referral riêng.

## 6. LDAP search/bind: ba chỗ thường nhầm với mật khẩu

### 6.1. DN pattern không khớp cây LDAP

Ví dụ hệ thống cấu hình `uid={0},ou=people` nhưng account thực tế chuyển sang `ou=employees`. User cung cấp password đúng nhưng bind tại DN không tồn tại vẫn thất bại.

**Cách chẩn đoán:** dùng một tài khoản lab được cấp quyền, tìm entry theo đúng base/filter qua công cụ LDAP an toàn; so DN tương đối với base DN do Spring `BaseLdapPathContextSource` cấu hình. Không in toàn bộ DN của khách hàng vào public logs.

### 6.2. Service account dùng cho search lỗi

Với search-before-bind, ứng dụng có thể cần một service DN có quyền đọc account metadata. Nếu password của service DN hết hạn hoặc bị rotate sai, **mọi user** sẽ lỗi dù họ nhập đúng password. Biện pháp sửa là quản lý secret/health của service account, **không** yêu cầu tất cả nhân viên reset password.

### 6.3. Group search hỏng sau bind

Người dùng xác thực danh tính thành công nhưng `LdapAuthoritiesPopulator` không tìm thấy nhóm, khiến họ thiếu `ROLE_EMPLOYEE` hoặc `ROLE_ADMIN`. Nếu ứng dụng trả 403 mà UI viết “Wrong password”, đó là lỗi phân loại giữa authentication và authorization.

**Kiểm tra:** liệu `Authentication.isAuthenticated()` đã true? `getAuthorities()` có đúng quyền? Cấu hình nested groups, member attribute, group DN base và mapping prefix phải nhất quán. Không tự cấp quyền mặc định ADMIN khi group lookup không thành công.

## 7. LDAPS/StartTLS: chứng thư máy chủ lỗi trước khi kiểm password

LDAP có thể dùng TLS theo hai cách:

- **LDAPS** thường bắt đầu TLS ngay trên kết nối, thường port 636.
- **LDAP + StartTLS** bắt đầu qua port LDAP (thường 389) rồi nâng kết nối lên TLS.

Trong cả hai, Java client phải tin certificate chain của directory và xác minh hostname theo cấu hình phù hợp. Khi CA được đổi, chứng thư hết hạn, SAN thiếu DNS tên dịch vụ hoặc truststore của JVM chưa cập nhật, LDAP bind chưa đến bước kiểm password đã có thể fail.

Dấu hiệu trong Java logs thường là `javax.net.ssl.SSLHandshakeException`, nguyên nhân sâu có thể liên quan `sun.security.provider.certpath.SunCertPathBuilderException`, `CertificateExpiredException` hoặc hostname verification. **Tên exception cụ thể phụ thuộc JDK, provider, driver và vị trí TLS termination**; tránh cứng nhắc chỉ tìm một chuỗi.

### 7.1. Quy trình kiểm tra an toàn

1. Lấy hostname LDAP đúng từ config đã được quản lý, so với SAN của server certificate.
2. Kiểm thời gian hệ thống/app pod/LDAP server; clock lệch có thể ảnh hưởng hiệu lực certificate.
3. Kiểm chain được server trình ra (root/intermediate), CA do JVM truststore tin cậy.
4. Kiểm quyền egress từ pod, DNS và firewall; lỗi timeout không phải chứng thư hết hạn.
5. Nếu chỉ lỗi một node, đối chiếu JDK version, truststore, container image và mounted CA bundle giữa các node.
6. Sửa CA/hostname/chain theo quy trình được phê duyệt, không đặt `trustAll`, tắt hostname verification hoặc chuyển sang LDAP plaintext để “chữa” login.

Công cụ kiểm certificate **của kết nối server** ở môi trường được phép:

```bash
openssl s_client \
  -connect ldap.example.test:636 \
  -servername ldap.example.test \
  -showcerts -verify_return_error
```

Đây là lệnh quan sát handshake; kết quả cần được đánh giá cùng truststore JVM của ứng dụng. OpenSSL thành công trên laptop không đảm bảo JVM container tin cùng CA. Không đưa private key hoặc password vào output/issue ticket.

### 7.2. JVM truststore là một thành phần deployment

Một số team sửa CA trên host Linux nhưng Java application dùng truststore riêng từ JDK/container. Kiểm `javax.net.ssl.trustStore`, truststore type, JDK CA bundle và file mount thực tế. Không lưu truststore password trong code, env dump hoặc logs. Luôn dùng public CA certificates do đội hạ tầng phê duyệt; không thêm một certificate tùy ý chỉ vì nó “làm bài test xanh”.

## 8. X.509/mTLS: lỗi chứng thư client không phải sai mật khẩu

Với **mutual TLS (mTLS)**, server/proxy yêu cầu **client certificate**, kiểm trust chain và các điều kiện liên quan trước khi (hoặc khi) chuyển HTTP request tới ứng dụng. Spring Security có `x509()`/`X509AuthenticationFilter` để lấy certificate đã được tầng TLS kiểm và ánh xạ sang principal/application user.

Có ít nhất hai nhánh hoàn toàn khác nhau:

### 8.1. Handshake fail ở ingress/proxy/container

Client gửi chứng thư hết hạn, không được CA tin, sai policy key usage, không có certificate khi server yêu cầu, hoặc kết nối TLS không đàm phán thành công. Application controller/filter có thể **không bao giờ nhìn thấy request**; Spring không có đủ dữ liệu để tạo `BadCredentialsException` cho một “password”.

```text
Client -- TLS ClientHello / Certificate -->
Ingress/Proxy -- verify client certificate -->
    FAILURE: TLS alert / connection aborted
    (không có HTTP response của app)
```

Nếu proxy cấu hình xác thực certificate là optional hoặc tự trả HTTP error, hành vi có thể khác. **Đừng khẳng định mọi lỗi mTLS đều phải là HTTP 401/403**, vì nhiều lỗi xảy ra trước HTTP.

### 8.2. Handshake thành công nhưng app không map được principal

TLS client certificate hợp lệ theo truststore chưa đồng nghĩa ứng dụng có account tương ứng. `X509AuthenticationFilter` thường trích xuất principal (ví dụ regex từ subject DN, mặc định có pattern lấy CN trong một số cấu hình) rồi dùng `UserDetailsService`/provider để load authorities. Lỗi mapping có thể khiến authentication không thành công dù không có password.

Kiểm:

- Chứng thư thật có tới servlet attribute `jakarta.servlet.request.X509Certificate` không? Ingress có forward certificate theo contract tin cậy không?
- Subject DN có chứa trường mong đợi hay không? `CN`, SAN/UPN/email và định danh ứng dụng có thực sự phù hợp?
- Regex trích xuất có match nhiều trường hoặc bị nhầm account không?
- Mapped user còn active/allowed và có authorities cần thiết không?
- Proxy có strip/spoof-prevention headers trước khi inject client certificate info không? **Không tin header certificate do Internet client tự đặt.**

Ví dụ cấu hình **Spring Security 6.x Servlet**, chỉ đặt trong một `SecurityFilterChain` dành cho endpoints mTLS:

```java
http
    .securityMatcher("/mtls/**")
    .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
    .x509(Customizer.withDefaults());
```

Đoạn này là **snippet DSL**, chưa có proxy/connector mTLS, user store và trust configuration. **Bật x509 filter không tự kích hoạt mTLS handshake**; server/ingress phải xác minh certificate trước. Nếu app backend nhận raw HTTP từ Internet, không được tự nhận X-Client-Cert từ header chưa bảo vệ.

## 9. Công cụ chẩn đoán mTLS mà không làm lộ khóa riêng

Ở môi trường lab có quyền thử nghiệm, xác minh client cert và handshake tại chính ingress mà người dùng đi qua:

```bash
openssl x509 -in client-lab.crt -noout \
  -subject -issuer -dates -ext extendedKeyUsage
```

Kiểm xem certificate có còn hạn, issuer đúng, subject/SAN nhận diện đúng và các đặc tính được policy chấp nhận. Lệnh có thể cho một số output tùy OpenSSL version; không chuyển toàn bộ certificate chain có thông tin cá nhân vào ticket nếu không cần.

Nếu cần thử handshake client authentication:

```bash
openssl s_client -connect api.example.test:443 \
  -servername api.example.test \
  -cert client-lab.crt -key client-lab.key \
  -verify_return_error
```

**Không in, upload hoặc commit file `client-lab.key`**. Sử dụng key test, quyền đọc tối thiểu, xóa theo policy. Kết quả handshake cần so với ingress log: nếu request chưa vào app, tìm ở TLS/proxy layer, không bật DEBUG cho toàn bộ Spring Security để tìm một event không tồn tại.

### 9.1. Sự khác nhau giữa server certificate và client certificate

- **Server certificate** chứng minh endpoint HTTPS/LDAPS đúng server, thường do client kiểm.
- **Client certificate** trong mTLS chứng minh client có private key tương ứng với certificate được server chấp nhận.

Đây là hai hướng trust khác nhau. Việc sửa server truststore không luôn giải quyết client certificate bị CA của server từ chối; ngược lại, import CA client vào server không sửa được client không tin server certificate. Chẩn đoán chính xác **điểm kiểm chứng** là điều bắt buộc.

## 10. OAuth2 Resource Server: bearer token lỗi không liên quan password

Với Spring Security Resource Server, request API thường gửi:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer eyJ...<redacted>
```

**Đoạn trên là ví dụ giao thức**, không dùng raw token thực trong logs hoặc tài liệu. `BearerTokenAuthenticationFilter` lấy token, `JwtAuthenticationProvider` gọi `JwtDecoder`, sau đó Spring xác minh signature, exp/nbf, issuer và các validators đã cấu hình. Token hợp lệ mới được ánh xạ thành `JwtAuthenticationToken` và scope/authorities.

Các nguyên nhân gây 401 có thể là:

- Không có token hoặc header `Authorization` không hợp lệ.
- Token không có cấu trúc JWT hợp lệ, base64url/JSON malformed hoặc chữ ký sai.
- Token hết hạn `exp`, chưa đến `nbf`, hoặc timestamp server lệch ngoài clock skew cho phép.
- `iss` không bằng issuer đã tin cậy, kể cả khác host/path/trailing slash.
- `aud` không chứa API audience kỳ vọng; token có thể dành cho một service khác.
- Signature algorithm `alg` không thuộc danh sách tin cậy; JWK không có key tương ứng.
- Token được ký bằng key mới có `kid` nhưng JWK Set/cache chưa cập nhật.
- JWK endpoint lỗi DNS/TLS/timeout, IdP metadata discovery không truy cập được.

Người dùng **có thể đã đăng nhập vào IdP bằng mật khẩu đúng**. Resource Server vẫn từ chối **access token** vì trust/claims/signature không hợp lệ. Reset password không sửa sai `iss` hoặc JWK cache.

### 10.1. 401 và 403 có ý nghĩa khác nhau

| Tình huống | Kỳ vọng thường gặp |
| --- | --- |
| Thiếu Bearer token vào protected API | `401` + `WWW-Authenticate: Bearer` |
| JWT sai chữ ký / sai issuer / hết hạn | `401`, Bearer challenge có thể có `invalid_token` |
| JWT đã được xác minh nhưng thiếu `SCOPE_reports.read` | `403`, có thể có `insufficient_scope` |
| JWT decoder không lấy được JWK/metadata | Kết quả phụ thuộc phiên bản, exception/handler; có thể 401 hoặc 5xx |
| TLS giữa Resource Server và IdP/JWKS lỗi | Lỗi outbound HTTP/TLS; cần internal dependency diagnostics |
| Access token từ client credentials thiếu quyền user | Không tự mang MFA/identity của human user |

**Không dựa vào 401 để xác định token sai password.** Access JWT thường do Authorization Server phát hành sau khi user/clients đã được xác thực ở một flow trước đó. Resource Server kiểm token, **không kiểm lại mật khẩu của user**.

## 11. Issuer: khác một ký tự cũng có thể thất bại

Trong JWT, `iss` biểu thị issuer. Spring Security khi cấu hình `issuer-uri` sẽ xác minh token đến từ issuer đã tin cậy. Chẳng hạn:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/finance
```

Token mang:

```json
{
  "iss": "https://idp.example.test/realms/sales",
  "sub": "user-123",
  "aud": ["finance-api"],
  "exp": 1893456000
}
```

Dù chữ ký hợp lệ với một key trong JWKS của IdP, token có `iss` là realm `sales` thay vì `finance` phải bị từ chối theo trust policy. **Không** thay `issuer-uri` thành một host gốc chung hoặc bỏ issuer validator chỉ để token qua.

Một số nguyên nhân sai issuer trong thực tế:

1. Frontend đăng nhập ở môi trường staging nhưng gọi API production.
2. Nhiều realms/tenants cùng IdP host; token chứa path của realm khác.
3. Reverse proxy biến URL public khác URL nội bộ, khiến IdP xuất `iss` không khớp config client.
4. Trailing slash, URL encoding, case hoặc scheme `http`/`https` khác nhau.
5. Resource Server đang dùng metadata endpoint/JWK URL của issuer khác.
6. Client nhầm **ID token** có audience là OAuth client ID với **access token** dùng cho API.

**Chẩn đoán:** so issuer kỳ vọng với cấu hình AS và **claims của token kiểm thử trong môi trường kiểm soát**. Không copy payload raw JWT của người dùng vào logs/ticket. Claims của JWT chỉ là dữ liệu **chưa được tin** trước khi verify signature; không dùng chúng để chọn một issuer/JWKS tùy ý.

## 12. JWK Set, kid, alg và việc xoay khóa

JWT ký bất đối xứng thường có header được issuer tạo, ví dụ:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-11"
}
```

**Các thuộc tính cần hiểu:**

- `alg`: thuật toán chữ ký. Resource Server phải giới hạn theo trusted algorithms; không tin header `alg` để tự thay chính sách.
- `kid`: key identifier **gợi ý** chọn public key trong JWK Set; nó không tự chứng minh key/issuer hợp lệ.
- `jwks_uri`: endpoint trong issuer metadata cung cấp public signing keys; URL có thể có path tùy IdP.
- JWK public fields như `kty`, `n`, `e` (RSA) hoặc `crv`/`x`/`y` (EC), `use` và `key_ops`: giúp chọn key phù hợp.
- `exp`/`nbf` và `iss` là **claims** của JWT payload; khác với fields của public key.
- Private signing key phải ở Authorization Server/HSM; Resource Server chỉ cần **public keys** và trust policy.

Khi AS rotate key:

```text
T0: JWKS = {kid: K1}             Token mới ký K1
T1: JWKS = {kid: K1, kid: K2}    Đăng K2 trước hoặc đúng lúc đổi
T2: AS phát token mới ký K2      Resource Server phải tìm thấy K2
T3: JWKS bỏ K1 sau khi token cũ hết hạn theo chính sách
```

Nếu AS xóa K1 quá sớm, token cũ còn thời hạn sẽ bị từ chối. Nếu AS bắt đầu ký K2 trước khi JWKS/CDN/cache có K2, token mới 401. Đây là **sự cố phối hợp key rotation**, không phải password sai. Khi `kid` không tìm được, decoder có thể fetch lại JWKS tùy cache/provider, nhưng không tự đảm bảo hệ thống cache/proxy lập tức đồng bộ.

### 12.1. Không “fix” bằng cách tắt kiểm chữ ký

Các cách sửa nguy hiểm cần tránh:

- Chấp nhận `alg=none` hoặc tự chọn secret theo một header JWT do client đặt.
- Chỉ base64-decode token rồi dùng `sub`/`role` chưa verify để cho truy cập.
- Tự tải JWKS từ URL chỉ định bên trong token/client request (SSRF/key substitution risk).
- Bỏ issuer/audience validator để token của mọi realm/service đều qua.
- Pin một public key vĩnh viễn nhưng không có kế hoạch key rotation.
- Log raw Bearer token để “xem cho dễ”.

Nguyên tắc là **sửa đúng issuer/JWK metadata, truststore, cache và AS rotation**, không nới lỏng tiêu chuẩn xác thực.

## 13. JWK endpoint lỗi mạng/TLS: một nhánh hạ tầng riêng

Resource Server phải tìm key để kiểm chữ ký. Khi JWK Set URL:

- Trả 404 do config sai path.
- Trả 5xx khi IdP lỗi.
- TLS certificate hết hạn hoặc CA chưa được JVM tin.
- DNS không resolve, egress firewall chặn, proxy outbound không được cấu hình.
- Response JSON không đúng JWK Set schema, thiếu key, `kid` sai, algorithm mismatch.
- Cache quá hạn hoặc CDN trả stale keys.
- Request timeout và connection pool cạn khi traffic tăng.

… thì không thể kiểm token theo policy và phải **không xác thực token chỉ vì không lấy được key**. Public response tùy filter/exception handling có thể giống `invalid_token` hoặc lỗi 5xx; cần internal diagnostics và monitoring để phân biệt.

### 13.1. Chẩn đoán theo lớp

1. Xác định API thực sự chọn Resource Server chain (không rơi vào form login chain).
2. Xác nhận issuer đã trust và JWK Set URI là cấu hình server-side đáng tin.
3. Từ node/pod của Resource Server, thử DNS, TCP, TLS tới IdP theo allowlist.
4. Kiểm HTTP status, content type, cache headers và JWK Set có public `kid` mong đợi.
5. Kiểm JWKS cache/rotation: token mới ký K2 nhưng cache trên một node vẫn chỉ K1?
6. Kiểm clock, exp/nbf/issuer/audience để không quy kết mọi JWT 401 cho JWK.
7. Quan sát p95/p99 decode latency và rate of cache refresh/timeout.
8. Không log token; nếu cần trace, chỉ log **token fingerprint không thể replay**, correlation ID, key ID theo allowlist, category và issuer alias đã cấu hình.

**Cẩn thận:** header `kid` của JWT chưa được verify; có thể do attacker tự chọn. Không đưa `kid` raw vào metric label/log không giới hạn. Validate size/charset và đưa vào sampling/allowlist khi phân tích.

## 14. issuer-uri, jwk-set-uri và thời điểm discovery

Trong Spring Boot 3.x/Spring Security 6.x, cấu hình Resource Server JWT thường là:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER}
          jwk-set-uri: ${JWT_JWK_SET_URI}
          audiences: ${JWT_AUDIENCE}
```

Đây là cách **khai báo rõ issuer và trusted JWK URL**; `issuer-uri` vẫn dùng để kiểm `iss`. Nếu dùng chỉ `issuer-uri`, framework có thể khám phá metadata/JWKS từ issuer. **Thời điểm discovery là chi tiết theo phiên bản và cách tạo decoder**: tài liệu Spring Security 6.5 mô tả default deferred discovery đến request JWT đầu tiên; một `JwtDecoder` custom do ứng dụng tự tạo có thể khởi tạo/khám phá theo cách khác. Đừng khẳng định mọi ứng dụng phải liên hệ IdP ngay khi startup hoặc mọi decoder đều lazy.

Cần kiểm:

- `JWT_ISSUER` phải khớp **chính xác** với `iss` của access token được tin cậy.
- `JWT_JWK_SET_URI` phải là endpoint **đáng tin**, cùng hợp đồng AS; không lấy từ user-supplied URL.
- `JWT_AUDIENCE` là audience của API, khác với client ID dùng cho OIDC ID token trong nhiều flow.
- DNS/TLS, hostname/CA và outbound egress phải hoạt động từ **tất cả pods**, không chỉ một node.
- Nếu tự khai báo `JwtDecoder @Bean`, có thể bạn đã thay auto-configuration validators. Đảm bảo issuer/audience/time/signature validation không mất.
- Không dùng một issuer/JWKS global cho nhiều tenants chưa đánh giá trust boundary; cần chiến lược trusted issuer resolution.

**Ví dụ:** nếu chỉ thêm `jwk-set-uri` mà bỏ `issuer-uri` hoặc cấu hình decoder chỉ kiểm chữ ký, ứng dụng có thể không áp dụng validator `iss` như yêu cầu. Signed token từ một issuer khác không được chấp nhận chỉ vì public key tìm thấy ở URL nào đó.

## 15. Spring Security AuthenticationEventPublisher: vì sao log “Bad Credentials” gây hiểu lầm?

Spring Security có `AuthenticationEventPublisher`; `DefaultAuthenticationEventPublisher` ánh xạ các `AuthenticationException` sang event types. Trong tài liệu **Spring Security 6.5**, mapping mặc định bao gồm:

| Exception | Event |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` |

**Chi tiết đáng nhớ:** `InvalidBearerTokenException` có thể được chuyển thành **AuthenticationFailureBadCredentialsEvent**, dù request **không hề có password**. Nếu một dashboard đếm toàn bộ `AuthenticationFailureBadCredentialsEvent` là “password sai”, số liệu sẽ bị sai. Tương tự `UsernameNotFoundException` thường được mask để chống account enumeration.

Event publisher sử dụng **exact exception class mapping** theo tài liệu Spring Security 6.5; subclass/custom exception có thể không được map tự động nếu chưa khai báo. Một số lỗi TLS xảy ra trước Spring và không phát event nào. Không coi “không thấy AuthenticationFailureEvent” là bằng chứng hệ thống không có authentication failures.

### 15.1. Cách thiết kế metric chính xác hơn

Không lấy event class làm nhãn nghiệp vụ duy nhất. Nên có thêm:

- **auth_mechanism** từ filter/chain được cấu hình: `LDAP_BIND`, `X509_MTLS`, `JWT_BEARER`, `OIDC_LOGIN`.
- **failure_category** từ một tập enum nội bộ đã review: `CREDENTIAL_REJECTED`, `DEPENDENCY_UNAVAILABLE`, `TLS_TRUST_ERROR`, `TOKEN_ISSUER_INVALID`, `TOKEN_KEY_UNAVAILABLE`, `TOKEN_SIGNATURE_INVALID`, `AUTHORIZATION_DENIED` hoặc `UNKNOWN`.
- **dependency_alias** theo config: `corporate-ldap`, `trusted-idp`; không raw URL/user input.
- **correlation_id** do server/gateway cấp, kiểm length và ký tự; không chứa PII.
- **status/outcome**: login redirect, 401, 403, TLS pre-HTTP error, 5xx.

Một `BadCredentialsException` không luôn phân loại được nguyên nhân gốc; cần đọc **trusted cause chain** hoặc thông tin provider đã lọc. Không cho client gửi header `X-Failure-Type: LDAP_OUTAGE` để thay đổi logic phân loại.

## 16. Ví dụ Spring Security 6.x: listener không lộ credential

Đoạn Java sau là class Spring component có thể biên dịch trong dự án **Spring Boot 3.x/Spring Security 6.x** có authentication event publisher. Nó không truy cập password/token, không log `Authentication.toString()` và chỉ ghi **loại sự kiện** đã allowlist.

**`SafeAuthEventDiagnostics.java`**

```java
package com.example.authdiagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationFailureServiceExceptionEvent;
import org.springframework.stereotype.Component;

@Component
public final class SafeAuthEventDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(SafeAuthEventDiagnostics.class);

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        String category;
        if (event instanceof AuthenticationFailureServiceExceptionEvent) {
            category = "SERVICE_EXCEPTION_NEEDS_ROOT_CAUSE";
        } else if (event instanceof AuthenticationFailureBadCredentialsEvent) {
            category = "CREDENTIAL_OR_TOKEN_REJECTED_NEEDS_CONTEXT";
        } else {
            category = "OTHER_AUTHENTICATION_FAILURE";
        }

        log.warn("auth_failure category={} eventClass={}",
                category, event.getClass().getSimpleName());
    }
}
```

Điểm quan trọng:

- `SERVICE_EXCEPTION_NEEDS_ROOT_CAUSE` chưa chắc là LDAP/network outage; cần kiểm trusted cause và dependency, tránh kết luận quá sớm.
- `CREDENTIAL_OR_TOKEN_REJECTED_NEEDS_CONTEXT` **không** có nghĩa password sai; có thể là invalid Bearer token, unknown username bị mask, hoặc credentials bị từ chối.
- Một số JWT decode errors bị ném qua filter chain/entry point khác, không có event listener trên một provider cụ thể; cần instrumentation của decoder/HTTP client ở nơi thích hợp.
- Nếu ứng dụng đã có logging theo cơ chế, không bắt tất cả exception rồi log stack trace/credential. Sampling và rate limit logs để tránh attacker tạo hàng triệu event.
- **Đây chỉ là event listener**, chưa thể xác định route/issuer/LDAP cause chỉ từ event type. Không mang nguyên `Authentication`, raw exception hay request vào asynchronous queue.

### 16.1. Cấu hình event publisher nếu cần

Đặt bean sau trong một class `@Configuration`, nếu chưa có publisher được framework/Boot cấu hình:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Imports:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
```

Đây là **snippet trong configuration class**, không phải source file độc lập. Khi dùng custom `ProviderManager`, kiểm nó thực sự sử dụng publisher được cấu hình. Tránh đăng ký lặp các publisher/event listeners khiến một request bị đếm nhiều lần.

## 17. Java 17 runnable: phân biệt tín hiệu với kết luận public

Chương trình này chạy **không cần Spring**, dùng enum tín hiệu do hệ thống chẩn đoán nội bộ đã xác minh. Nó cố tình **không** nhận raw password, JWT hoặc certificate bytes. Mục tiêu là chứng minh cùng một dòng “authentication failed” có nhiều nhánh xử lý.

**`AuthFailureClassifierDemo.java`**

```java
public class AuthFailureClassifierDemo {

    enum Signal {
        LDAP_BAD_SECRET,
        LDAP_UNREACHABLE,
        LDAPS_TRUST_FAILURE,
        MTLS_HANDSHAKE_REJECTED,
        JWT_ISSUER_MISMATCH,
        JWKS_FETCH_TIMEOUT,
        JWT_EXPIRED,
        MISSING_SCOPE
    }

    record Decision(String category, String publicOutcome) {}

    static Decision decide(Signal signal) {
        return switch (signal) {
            case LDAP_BAD_SECRET ->
                    new Decision("CREDENTIAL_REJECTED",
                                 "GENERIC_LOGIN_FAILURE");
            case LDAP_UNREACHABLE, JWKS_FETCH_TIMEOUT ->
                    new Decision("DEPENDENCY_UNAVAILABLE",
                                 "TEMPORARY_SERVICE_ERROR");
            case LDAPS_TRUST_FAILURE ->
                    new Decision("TLS_TRUST_ERROR",
                                 "TEMPORARY_SERVICE_ERROR");
            case MTLS_HANDSHAKE_REJECTED ->
                    new Decision("CLIENT_CERT_REJECTED",
                                 "TLS_ERROR_PRE_HTTP");
            case JWT_ISSUER_MISMATCH, JWT_EXPIRED ->
                    new Decision("TOKEN_INVALID",
                                 "HTTP_401_BEARER");
            case MISSING_SCOPE ->
                    new Decision("AUTHORIZATION_DENIED",
                                 "HTTP_403");
        };
    }

    public static void main(String[] args) {
        for (Signal signal : Signal.values()) {
            Decision decision = decide(signal);
            System.out.println(signal + " -> "
                    + decision.category() + " / "
                    + decision.publicOutcome());
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac AuthFailureClassifierDemo.java
java AuthFailureClassifierDemo
```

**Stdout chính xác:**

```text
LDAP_BAD_SECRET -> CREDENTIAL_REJECTED / GENERIC_LOGIN_FAILURE
LDAP_UNREACHABLE -> DEPENDENCY_UNAVAILABLE / TEMPORARY_SERVICE_ERROR
LDAPS_TRUST_FAILURE -> TLS_TRUST_ERROR / TEMPORARY_SERVICE_ERROR
MTLS_HANDSHAKE_REJECTED -> CLIENT_CERT_REJECTED / TLS_ERROR_PRE_HTTP
JWT_ISSUER_MISMATCH -> TOKEN_INVALID / HTTP_401_BEARER
JWKS_FETCH_TIMEOUT -> DEPENDENCY_UNAVAILABLE / TEMPORARY_SERVICE_ERROR
JWT_EXPIRED -> TOKEN_INVALID / HTTP_401_BEARER
MISSING_SCOPE -> AUTHORIZATION_DENIED / HTTP_403
```

**Đây là mô hình phân loại, không phải HTTP handler hoặc validator thực.** `TEMPORARY_SERVICE_ERROR` nghĩa ứng dụng nên đưa thông báo chung phù hợp policy; mã HTTP cụ thể có thể là 503 khi backend thiết kế rõ, nhưng Spring không mặc định trả đúng mã đó trong mọi nhánh. `TLS_ERROR_PRE_HTTP` có thể không có status HTTP nào. `MISSING_SCOPE` giả định token đã được verify; nếu token chưa hợp lệ thì phải từ chối xác thực trước.

Một lỗi riêng có thể **đồng thời** ảnh hưởng nhiều tầng, ví dụ IdP trả JWK qua HTTPS với certificate hết hạn: phân loại nguyên nhân kỹ thuật là trust failure, đồng thời báo dependency impacted.

## 18. Ví dụ Spring Boot 3.x: tách LDAP web login và JWT Resource Server

Bài toán thường xuất hiện khi một ứng dụng có cả trang web doanh nghiệp và REST API. Cấu hình tách chain giúp biết request đi vào provider nào. Ví dụ dưới đây dùng **Java 17+, Spring Boot 3.x/Spring Security 6.x** và dựa trên server LDAP/IdP được cung cấp ngoài dự án.

### 18.1. Dependencies

Một Gradle project có Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-ldap'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Thực tế phải chọn phiên bản khớp BOM Spring Boot. `spring-security-ldap` mang LDAP authentication support; JWT Resource Server cần JOSE support do starter quản lý. Không nhầm resource-server dependency với `spring-boot-starter-oauth2-client`, vốn dành cho client/OIDC login flow.

### 18.2. application.yml

```yaml
app:
  ldap:
    url: ${LDAP_URL:ldaps://ldap.example.test:636/dc=example,dc=test}

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${JWT_ISSUER}
          jwk-set-uri: ${JWT_JWK_SET_URI}
          audiences: ${JWT_AUDIENCE}
```

Lấy trusted URLs/secrets từ deployment configuration, không lấy từ client payload. URL `example.test` chỉ là ví dụ; app phải có directory và IdP/JWKS có thể truy cập để thật sự login.

### 18.3. Cấu hình hai SecurityFilterChain

**`DiagnosticSecurityConfig.java`** (package `com.example.authdiagnostics`):

```java
package com.example.authdiagnostics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.ldap.DefaultSpringSecurityContextSource;
import org.springframework.security.ldap.authentication.LdapBindAuthenticationManagerFactory;
import org.springframework.security.ldap.context.BaseLdapPathContextSource;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DiagnosticSecurityConfig {

    @Bean
    BaseLdapPathContextSource ldapContext(
            @Value("${app.ldap.url}") String url) {
        return new DefaultSpringSecurityContextSource(url);
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory =
                new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .anyRequest().hasAuthority("SCOPE_reports.read"))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(server -> server
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(
            HttpSecurity http,
            AuthenticationManager ldapAuthenticationManager)
            throws Exception {
        return http
                .authenticationManager(ldapAuthenticationManager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
```

**Giải thích:**

- Request `/api/**` vào chain `@Order(1)`, xác thực bearer JWT; không dùng form login, không hỏi LDAP password.
- Các request web khác đi vào chain `@Order(2)`, form login gọi LDAP bind manager. Khi login sai, form failure handler mặc định có thể redirect tới `/login?error`; điều đó không đủ để xác định LDAP outage.
- `securityMatcher` chọn chain, khác với `requestMatchers` chọn authorization rule bên trong chain. Nếu matcher sai, người dùng có thể nhìn thấy HTML redirect thay vì Bearer 401.
- `LDAPS` còn cần JVM truststore/CA đúng; bean constructor không tự chứng minh TLS/LDAP có thể kết nối. `JWT_ISSUER/JWT_JWK_SET_URI` phải phù hợp metadata/trusted AS.
- `SessionCreationPolicy.STATELESS` chỉ cho **API bearer header thuần**; web login giữ session và CSRF. Không tắt CSRF toàn hệ thống chỉ để test API.
- Demo LDAP bind dùng DN pattern `uid={0},ou=people`; nếu directory thực dùng user search, UPN hoặc nhiều OUs thì phải cấu hình cho đúng. User bind thành công không tự cấp các quyền nghiệp vụ; cần authorities mapping theo ứng dụng.
- Chưa có controller, LDAP server, JWKS server hoặc test credentials. **Đây là cấu hình tích hợp trong dự án có hạ tầng thật**, không phải chương trình Java độc lập; không tuyên bố code được chạy trong môi trường này.

### 18.4. Không dùng chung failure handler để kết luận mọi lỗi

Nếu frontend muốn trả trạng thái khác nhau khi LDAP dependency outage và password invalid, có thể định nghĩa policy:

```text
LDAP truly rejected credential / unknown username:
    web user sees generic "Cannot sign in"
    internal category: AUTH_CREDENTIAL_REJECTED

LDAP network/trust dependency unavailable:
    web user sees generic "Sign-in temporarily unavailable"
    internal category: LDAP_DEPENDENCY_UNAVAILABLE
    no password retry storm; alert ops

JWT invalid signature/issuer/audience/expired:
    API returns 401 Bearer challenge
    internal category: TOKEN_INVALID (safe subcategory)

JWKS endpoint outage:
    do not accept token without signature verification
    internal category: JWKS_DEPENDENCY_UNAVAILABLE
    response according to deliberate security/error contract

TLS/mTLS fails before application:
    client sees TLS error or ingress-defined response
    internal category: TLS_HANDSHAKE_FAILURE
```

Đây là **pseudocode chính sách**, không phải hành vi mặc định bảo đảm của tất cả Spring providers. Nếu phân biệt service unavailable trên UI, bảo đảm không biến nó thành **oracle dò account** (ví dụ cùng một lỗi kết nối chỉ xảy ra với username có thật); chỉ phân loại dựa trên tín hiệu hạ tầng đáng tin, không lộ policy tài khoản.

## 19. OAuth2 Login/OIDC và Resource Server là hai flow khác nhau

Một ứng dụng web dùng `oauth2Login()` thực hiện **Authorization Code flow** (thường với OIDC) qua redirect browser, state, nonce, PKCE theo kiến trúc và callback. Lỗi có thể là:

- `invalid_state`/state cookie hoặc session bị mất.
- Redirect URI không đúng whitelist ở IdP.
- Callback/reverse proxy scheme/host khác với URI cấu hình.
- Authorization Server token endpoint timeout, TLS certificate failure.
- ID token sai issuer, audience (client ID), signature, nonce hoặc key rotation.
- Mapping OIDC `sub`/`iss` sang local user thiếu hoặc role mapping thất bại.

Trong khi đó `oauth2ResourceServer().jwt()` nhận **access token** ở HTTP Authorization header. Nó không thực hiện browser login bằng password và không tự follow IdP login form.

| Khía cạnh | OIDC client login | Resource Server JWT |
| --- | --- | --- |
| Tài sản chính | Authorization response, ID token/authorized client | Access token dùng cho API |
| Token issuer trust | IdP của client registration | Issuer của protected API |
| Audience | Thường client ID trong ID token | Resource/API audience trong access token |
| HTTP UX | Redirect login/callback/error page | 401 Bearer hoặc 403 cho lack of scope |
| State | Web session, state, nonce, authorized client | Thường stateless decoder từng request |
| Sai lầm thường gặp | “User gõ sai password” khi state/redirect lỗi | “User gõ sai password” khi `iss`/`kid`/JWK lỗi |

**Không sử dụng ID token làm access token cho API.** JWT ID token có thể được ký hợp lệ nhưng audience/semantics là để chứng minh login với OAuth client, không để trao quyền cho Resource Server. Việc bỏ audience check để “chữa” 401 tạo nguy cơ token substitution.

## 20. Khác biệt giữa lỗi xác thực, service outage và 403 trong log

Một số lỗi được cố ý mask:

- `DaoAuthenticationProvider` và một số providers có thể biến `UsernameNotFoundException` thành `BadCredentialsException` để chống enumeration.
- LDAP server có thể không tiết lộ lý do account disabled/locked trong API public.
- JWT bearer filter có thể trả `InvalidBearerTokenException` và HTTP 401 mà không nói cụ thể chữ ký, issuer hay expiration trong body.
- Ingress/proxy có thể trả lỗi TLS mà ứng dụng không có log.
- `AccessDeniedException` sau authentication có thể dẫn đến 403; không phải password failure.

**Nên có hai lớp thông điệp:**

1. **Public response:** chung, an toàn, theo contract HTTP; không lộ DN, username có tồn tại, server names, private keys, token payload, truststore path, các validation subcode nhạy cảm.
2. **Internal evidence:** phân loại có giới hạn, timestamp UTC, correlation ID, app instance, chain name, dependency alias, error category, status, latency, certificate expiry **không chứa secrets**.

Không log raw `Authentication`, `Authentication.getCredentials()`, bearer token, `Authorization` header, session cookies, private keys, password request body hoặc full LDAP bind DN không cần thiết. Structured logs với allowlist cần áp dụng **ngay tại nguồn**.

## 21. Trình tự kiểm tra thực tế khi có incident

Giả sử 40% users báo “sai mật khẩu” sau khi deploy:

**Bước 1 — Phân nhóm request.** Có bao nhiêu lỗi ở form web, bao nhiêu ở API Bearer, bao nhiêu ở mTLS? Quan sát logs gateway/filter chain; đừng tính tất cả 401 vào password metrics.

**Bước 2 — Đối chiếu thời gian.** Lỗi tăng sau khi cập nhật CA, rotate JWK, migrate LDAP OU, đổi issuer/realm, deploy JDK/truststore, hay sau thay đổi clock? Gắn mã release/instance để biết có lỗi chỉ trên một node.

**Bước 3 — Kiểm request có tới app.** Nếu TLS mTLS handshake fail ở edge, Spring Security không thấy request. Kiểm ingress TLS logs và chain certificate; không tìm `BadCredentialsException` trong application logs.

**Bước 4 — Nếu là LDAP, phân biệt bind outcome với transport.** Với account lab, kiểm trusted LDAP connectivity, TLS, DN pattern, service account, user bind và group search. Không thử password của người dùng thật hoặc gửi chúng qua ticket.

**Bước 5 — Nếu là JWT, so trust boundary.** Kiểm token đến từ AS đúng, `iss`, `aud`, `exp/nbf`, `kid/alg` và JWK Set. Nếu token thực có chứa PII, dùng test token/synthetic token và chỉ ghi fingerprints đã được định nghĩa.

**Bước 6 — Nếu authn thành công nhưng 403, kiểm quyền.** Spring scope mapping prefix `SCOPE_`, roles `ROLE_`, tenant, resource ownership, group lookup và method security; đừng reset credentials.

**Bước 7 — Đánh giá scope blast radius.** Tất cả nodes lỗi hay chỉ một AZ/pod? Một node có JWK cache/truststore cũ? Redis/LDAP/IdP outage cục bộ? Có cơ chế retry tạo thác requests không?

**Bước 8 — Khắc phục đúng lớp.** Thay CA/hợp đồng trust có review; sửa issuer/JWKS config chính xác; đồng bộ key rotation; khôi phục LDAP service; sửa group mapping; rollback khi cần. Không tắt xác minh chữ ký, hostname, certificate hoặc authentication.

**Bước 9 — Regression và hậu kiểm.** Viết test cho tình huống đã gây lỗi (mTLS handshake, LDAP outage, JWKS rotation, issuer mismatch), thêm alert an toàn và bổ sung runbook.

## 22. Ma trận kiểm thử cho CI và staging

| Kịch bản | Mô phỏng/fixture | Kỳ vọng |
| --- | --- | --- |
| LDAP login đúng | Test LDAP server có user known-good | Authenticated, đúng principal/quyền |
| LDAP sai password | Tài khoản lab + password sai | Thất bại, public message generic |
| User không tồn tại | Login lab username không tồn tại | Thông báo/timing không trở thành enumeration oracle |
| LDAP server down | Dừng test container/chặn port | Không cho qua; phân loại dependency internally |
| LDAP TLS invalid CA | Test LDAPS server với CA không được trust | Không bind; trust error, không kết luận bad password |
| LDAP DN đổi OU | Test directory chuyển account path | Phát hiện search/lookup sai, không reset password |
| Group search hỏng | Directory trả user nhưng thiếu group | Không cấp role cao; kiểm 403 đúng policy |
| mTLS thiếu client cert | Test ingress yêu cầu certificate | TLS handshake hoặc edge error phù hợp config |
| mTLS cert hết hạn | Synthetic expired client certificate | Bị TLS/trust policy từ chối; Spring có thể không thấy request |
| mTLS cert hợp lệ nhưng principal unmapped | Test certificate đã được trust | App không map/không cấp quyền, phân loại khác TLS |
| JWT sai `iss` | Signed test JWT từ issuer khác | 401, không được chấp nhận |
| JWT sai `aud` | Signed test JWT không dành cho API | 401 khi audience validator được bật |
| JWT hết hạn hoặc `nbf` ở tương lai | Controlled clock fixture | 401, không phụ thuộc user password |
| JWT sai signature | Test key không được trust | 401; không bỏ signature verify |
| JWT key rotation K1→K2 | JWKS test endpoint thay public keys | Token mới hợp lệ sau trust/refresh; token cũ theo policy |
| JWKS down/DNS/TLS failure | Mock HTTP/JWKS server có timeout | Không chấp nhận token chưa verify, dependency alert |
| JWT hợp lệ thiếu scope | Correct signed JWT, wrong scope | 403, không biến thành login/password failure |
| OIDC state/nonce sai | Test IdP/callback | Login flow bị từ chối, không gán sai password |
| Two-node cache divergence | Hai pods khác cache/truststore | Phát hiện sự khác biệt theo instance |
| Excessive invalid tokens | Load test giới hạn và sampling | Không log raw token, không tạo DoS qua logging |

### 22.1. Spring Security Test có gì và không có gì?

`MockMvc` với `spring-security-test` rất hữu ích để kiểm matcher/authorization. Tuy nhiên:

- `.with(jwt())` **tạo giả JwtAuthenticationToken**, không gọi `JwtDecoder` thật để kiểm signature, issuer, audience hoặc JWKS.
- `.with(user("alice"))` **không gọi LDAP bind**. Nó không thể chứng minh directory reachable hay mật khẩu đúng.
- `.with(x509(...))` hoặc việc tự gắn certificate attribute trong mock request **không chứng minh TLS handshake/ingress client certificate verification**.
- MockMvc test thông thường có thể không chạy qua reverse proxy/TLS termination, nên cần HTTP/mTLS integration tests.

Để test đúng nguyên nhân gốc, dùng **LDAP test container/embedded LDAP** do team kiểm soát, **JWKS HTTP stub + JWT ký bằng khóa test**, **TLS test ingress** với test CA/expired cert và kiểm request flow end-to-end. Test phải tránh dùng private keys production hoặc token người dùng thật.

### 22.2. Những assertion cần thêm

Trong security integration tests nên assert cả:

- **HTTP response** đúng cho browser/API: 302 form login, 401 Bearer challenge, 403 thiếu quyền; 503 nếu handler dependency outage chủ đích.
- **Internal category** đúng mà không lộ root cause ở public response.
- **Không có bypass:** LDAP/JWKS/CA lỗi không thể xác thực như admin.
- **Không lộ dữ liệu:** log capture không chứa raw password, JWT, cookies hoặc private keys.
- **Không bị retry storm:** connection/JWKS retries có timeout, backoff, rate limit phù hợp.
- **Không ảnh hưởng unrelated flows:** API bearer failure không xóa web session, LDAP outage không tắt validation JWT.
- **Hoạt động sau recovery:** sau khôi phục directory/keys, valid login/token hoạt động lại mà không phải reset hàng loạt mật khẩu.

## 23. Dấu hiệu metrics/alerts nên có

| Tín hiệu | Ý nghĩa nếu tăng mạnh |
| --- | --- |
| `ldap_connect_timeout_total` | LDAP/DNS/firewall/pool issue |
| `ldap_tls_handshake_failure_total` | Certificate chain/CA/SAN/truststore/clock issue |
| `ldap_bind_rejected_total` | Credential/policy/DN issue, cần phân tích thêm |
| `ldap_group_lookup_failure_total` | Authorization mapping dependency |
| `mtls_handshake_rejection_total` tại ingress | Client certificate/trust/policy issue trước app |
| `x509_principal_mapping_failure_total` | TLS okay nhưng app không map được user |
| `jwt_invalid_issuer_total` | Token sai issuer/realm/environment |
| `jwt_invalid_audience_total` | Token không dành cho API |
| `jwks_fetch_failure_total` | Metadata/JWK availability/trust |
| `jwt_kid_not_found_total` | Rotation/cache/issuer mismatch/attacker input |
| `token_signature_rejected_total` | Key/algorithm/signature mismatch |
| `authz_denied_total` | Thiếu role/scope/tenant |
| `auth_provider_latency_seconds` | Dependency latency, có thể dẫn đến login timeout |

Đây là **tên metric minh họa do ứng dụng phải tự instrument**, **không** phải metrics tự động có sẵn của Spring Security. Không dùng username/email/IP/raw `kid`, `iss` từ unverified token làm metric labels có cardinality không giới hạn. Chỉ dùng các nhãn low-cardinality từ cấu hình được tin cậy như `mechanism`, `routeGroup`, `dependencyAlias`, `outcome`; user identifiers nếu phải lưu cho điều tra cần kho riêng, bảo mật và retention.

**Gợi ý alert:** không chỉ alert tổng số 401 mà so tỷ lệ theo cơ chế, node/version/AZ; sự kiện `jwks_fetch_failure` tăng sau key rotation quan trọng khác với một đợt credential stuffing. Quan sát p99 của LDAP bind/JWK request, thay vì nhìn riêng response status.

## 24. Lỗi sửa chữa nguy hiểm thường gặp

| Cách “sửa nhanh” | Rủi ro | Cách đúng |
| --- | --- | --- |
| “LDAP lỗi thì dùng admin password tĩnh” | Authentication bypass | Fail closed và phục hồi LDAP |
| Tắt hostname validation LDAPS | Có thể chấp nhận máy chủ giả mạo | Sửa SAN/hostname/CA chain |
| Đổi từ LDAPS sang LDAP plaintext | Lộ credential trên mạng | Sửa TLS, giữ mã hóa |
| Trust-all certificates hoặc bỏ chain validation | MITM, giả mạo IdP/LDAP | Truststore/CA được duyệt |
| Tắt yêu cầu client certificate của mTLS | Ai cũng có thể tới endpoint | Sửa cert policy và provisioning |
| Tin header `X-Client-Cert` từ Internet | Client tự giả certificate | Chỉ lấy từ trusted proxy đã verify |
| Bỏ kiểm `iss` vì token “đã ký đúng” | Token từ realm khác được dùng | Issuer validator chính xác |
| Bỏ kiểm `aud` vì JWT 401 | Cross-service token substitution | Validate API audience |
| Chấp nhận mọi `alg` từ JWT header | Algorithm confusion | Trusted algorithm allowlist |
| Tải JWKS từ URL do token khai | SSRF/rogue signing key | Server-side trusted JWKS configuration |
| Bỏ signature validation khi JWKS down | Forged token được chấp nhận | Fail closed + dependency alert |
| Dùng `jwt()` mock rồi kết luận JWKS ổn | Bỏ qua decoder/network/issuer | Integration signed-JWT tests |
| Log raw `Authentication` hoặc token | Credential/PII leakage | Redacted structured logs |
| Dùng một thông báo public “Sai password” cho mọi API 401 | Triage sai, người dùng bị ép reset | UX theo cơ chế; internal categories |
| Expose LDAP result/subcode ở login form | Username enumeration/account state leak | Generic response, internal-only evidence |
| Map mọi `AuthenticationFailureBadCredentialsEvent` thành password failure | Invalid Bearer token bị đếm sai | Tách mechanism/provider context |
| Trả 403 cho mọi token invalid | Sai HTTP semantics, SDK xử lý sai | 401 cho authn; 403 cho thiếu quyền |
| Không có timeouts/backoff với LDAP/JWKS | Thread exhaustion, cascading failure | Bounded timeouts, circuit breaker, retry policy |
| Reset password hàng loạt khi JWK rotate | Không giải quyết issue, gây gián đoạn | Kiểm key rotation/cache/issuer |

**Không dùng biện pháp vô hiệu hóa xác thực để chứng minh “lỗi đã được khắc phục”.** Mục tiêu của runbook là bảo toàn trust và xác định nguyên nhân, không làm endpoint trả 200 bằng mọi giá.

## 25. Bài tập thực hành

1. Một form login của công ty trả `/login?error` cho cả user đúng password khi directory đổi CA. Vẽ flow từ browser tới Spring Security/LDAP và xác định **tầng nào chưa tới bước check password**. Đề xuất ba bằng chứng nội bộ không chứa secrets.
2. Với LDAP code 49 và AD subcode `775`, giải thích vì sao không được kết luận user nhập sai password; public response nên như thế nào để chống enumeration?
3. Một mTLS request không xuất hiện trong ứng dụng. Nêu thứ tự kiểm tra TLS handshake, ingress logs, trusted CA, client EKU và principal mapping.
4. Client certificate handshake thành công nhưng Spring `x509()` không map user. Phân biệt “TLS trust fail” với “app principal mapping fail”.
5. API JWT có `iss=https://idp.example.test/realm-a` nhưng cấu hình trusted issuer là `realm-b`. Chữ ký vẫn verify; tại sao phải 401?
6. Token mới ký bằng `kid=K2`, JWKS cached trên node A chỉ có K1, node B đã có K2. Thiết kế một integration test chỉ ra cache/rotation discrepancy mà không log raw token.
7. JWKS endpoint trả TLS certificate expired. Có nên tạm disable signature validator? Vì sao không?
8. Cài listener Spring Security và tìm xem vì sao `InvalidBearerTokenException` có thể phát `AuthenticationFailureBadCredentialsEvent`. Chỉnh metrics để không gọi nhầm đó là password sai.
9. Viết MockMvc test authorization khi JWT giả lập đủ/thiếu scope, sau đó **bổ sung** integration test JWT ký thật với JWKS stub để kiểm issuer/audience/key.
10. Thiết kế dashboard theo cơ chế với 401/403, LDAP connect/TLS, JWKS fetch, cache miss, mTLS ingress errors và release version.
11. Đặt một service LDAP test không sẵn sàng; kiểm handler không cấp authentication và không lộ hostname/stacktrace trong public response.
12. Chọn thời điểm retry hợp lý sau IdP outage để không gây retry storm từ hàng nghìn pods hoặc clients.

## 26. Tổng kết và nguồn tham khảo

- **Không đồng nhất thông báo “đăng nhập thất bại” với password sai.** Xác định request đã tới TLS, directory/provider, JwtDecoder hay authorization layer nào.
- LDAP có thể lỗi bind/search/DN, network, service account, LDAPS truststore hoặc group mapping; `49 invalidCredentials` chưa đủ chứng minh sai password trong mọi directory.
- Với X.509/mTLS, TLS client certificate có thể bị từ chối **trước HTTP/Spring**; nếu handshake thành công nhưng principal mapping sai thì đó là nhóm lỗi khác.
- Resource Server xử lý access token, không kiểm password user; `iss`, `aud`, signature, `kid/alg`, JWKS cache/rotation và dependency outage là các nhánh cần chẩn đoán.
- Spring Security `AuthenticationFailureBadCredentialsEvent` có thể phát cho `InvalidBearerTokenException`; dashboard không được đếm toàn bộ event này như password failure.
- Public response cần an toàn, còn internal evidence phải đủ tách credential, service outage, trust error, token invalid và authorization denied; không log secrets.
- **Không bypass trust** để khắc phục: không tắt TLS validation, certificate requirement, issuer/audience/signature validation; fail closed khi không xác minh được.
- Test cả LDAP, mTLS, signed JWT/JWKS, issuer, role và failover; MockMvc mock user/JWT không thay integration test credential và crypto thật.

**Tài liệu chính thức:**

- [Spring Security 6.5 — LDAP Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/ldap.html)
- [Spring Security 6.5 — X.509 Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 — Authentication Events and Exception Mappings](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)