# Kiểm tra đồng hồ, DNS, TLS, proxy và cấu hình môi trường khi có sự cố

## 1. Vì sao sự cố Resource Server thường nằm ngoài đoạn code xác thực?

Một API Spring Security OAuth 2.0 Resource Server có thể trả 401, không tải được JWKS, không introspect được opaque token hoặc chỉ lỗi ở một môi trường dù code và token không thay đổi. Nguyên nhân có thể nằm ở đồng hồ hệ thống, DNS, chứng chỉ TLS, proxy hoặc cấu hình được nạp khi ứng dụng khởi động.

Một request Bearer token có hai hướng kết nối cần phân biệt:

~~~text
API client
   |
   | HTTPS + Authorization: Bearer ...
   v
Load balancer / reverse proxy / ingress
   |
   | HTTPS hoặc HTTP nội bộ
   v
Spring Security Resource Server
   |
   | outbound HTTPS: discovery / JWKS / introspection
   v
Authorization Server / OpenID Provider
~~~

- **Inbound path:** client kết nối API qua gateway, load balancer, reverse proxy và ứng dụng. Sự cố ở đây thường liên quan listener, route, forwarded headers, TLS termination, path rewrite hoặc header bị loại bỏ.
- **Outbound identity path:** Resource Server kết nối issuer metadata, JWKS endpoint hoặc introspection endpoint. Sự cố thường liên quan DNS, egress proxy, TLS trust, proxy authentication, timeout hoặc provider availability.
- **Local validation path:** ứng dụng kiểm tra JWT claims bằng clock và cấu hình đã nạp. Sự cố thường liên quan thời gian lệch, issuer/audience sai, profile sai hoặc cấu hình môi trường không nhất quán.

Điều đầu tiên khi xử lý sự cố là xác định request đang thất bại ở hop nào. Không nên bắt đầu bằng việc tăng clock skew, tắt certificate validation hoặc thay đổi issuer URL khi chưa có bằng chứng.

## 2. Phân loại triệu chứng trước khi thay đổi cấu hình

| Triệu chứng | Nhóm cần kiểm tra đầu tiên |
|---|---|
| JWT hợp lệ ở máy developer nhưng bị reject trên server | Clock, issuer/audience, key/config profile |
| Lỗi chỉ xuất hiện sau khi deploy hoặc restart | Environment variables, secret mount, config precedence |
| Không tải được OpenID discovery document | DNS, egress proxy, TLS, issuer URI |
| Không tải được JWKS hoặc key rotation không có hiệu lực | DNS, proxy, TLS, JWKS cache, key ID |
| Opaque token trả 401 hàng loạt | Introspection endpoint, client credentials, TLS, proxy |
| Lỗi TLS handshake hoặc PKIX path building failed | Truststore, certificate chain, hostname, SNI |
| API hoạt động trực tiếp nhưng lỗi qua gateway | Forwarded headers, route, host/path rewrite, Authorization header |
| Redirect/callback hoặc issuer URL dùng HTTP/internal host | TLS termination và forwarded headers |
| Chỉ một node trong cluster lỗi | Node clock, DNS cache, truststore, environment/config drift |
| Lỗi chập chờn theo thời điểm | DNS resolver, connection pool, proxy, IdP, NTP, network timeout |
| Token mới không được chấp nhận sau key rotation | JWKS refresh/cache, DNS, issuer metadata và key selection |

Hãy ghi nhận thời điểm, node/pod, endpoint, issuer alias, error category, request ID và thay đổi triển khai gần nhất. Không ghi access token, refresh token, private key, client secret hoặc toàn bộ Authorization header vào ticket/log.

## 3. Đồng hồ hệ thống và JWT timestamps

### 3.1. Vì sao thời gian lệch làm JWT bị từ chối?

JWT thường có các NumericDate claims:

- `exp` — thời điểm token hết hạn.
- `nbf` — thời điểm token bắt đầu có hiệu lực.
- `iat` — thời điểm token được phát hành.

Resource Server so sánh các claims này với clock hiện tại. Nếu clock của Authorization Server và Resource Server lệch nhau, token có thể bị đánh giá là hết hạn hoặc chưa có hiệu lực dù client vừa nhận token.

Ví dụ:

~~~text
Authorization Server clock: 10:00:00
Resource Server clock:      10:02:30
JWT exp:                    10:01:00

AS vừa phát hành token còn hiệu lực trong 60 giây,
nhưng Resource Server đã nghĩ token hết hạn.
~~~

Lệch theo chiều ngược lại cũng có thể khiến token có `nbf` ở tương lai bị từ chối. Clock drift trên một node duy nhất tạo lỗi chỉ xảy ra khi load balancer route request đến node đó.

### 3.2. Kiểm tra UTC, timezone và đồng bộ NTP

JWT NumericDate được tính theo thời gian Unix, không phụ thuộc timezone hiển thị. Tuy vậy, timezone cấu hình sai làm log khó đối chiếu và có thể khiến người vận hành hiểu sai thời điểm sự cố.

Trên Linux:

~~~bash
date -u
timedatectl status
timedatectl timesync-status
chronyc tracking
chronyc sources -v
~~~

Trên Windows:

~~~powershell
Get-Date
Get-Date -AsUTC
w32tm /query /status
w32tm /query /source
~~~

Kiểm tra UTC hiện tại, NTP service, nguồn thời gian, offset, last successful synchronization và độ nhất quán giữa các nodes. Xác định host/pod có clock riêng hay dùng clock của node.

Nếu cần đồng bộ lại, dùng quy trình vận hành của hệ điều hành và hạ tầng. Ví dụ Windows có thể dùng `w32tm /resync` khi tài khoản và policy cho phép. Không tự sửa giờ thủ công trên production node đang chạy workload vì có thể ảnh hưởng database, scheduler, TLS validity, distributed locks và audit chronology.

### 3.3. Đọc JWT timestamps an toàn

Khi chẩn đoán, có thể decode payload trong môi trường kiểm thử để xem `iat`, `nbf` và `exp`. Việc decode payload không xác minh chữ ký; không dùng nội dung decode làm bằng chứng token đáng tin.

Đối chiếu:

- Token được phát hành lúc nào theo UTC?
- Resource Server ghi nhận request lúc nào?
- Claim `exp` có nằm trong quá khứ so với clock của node không?
- Claim `nbf` có nằm trong tương lai không?
- Clock skew có được cấu hình giống nhau trên các instances không?
- Issuer có phát token với thời gian bất thường không?

Không gửi token production vào website decoder công cộng. Nếu cần xem claims, dùng công cụ nội bộ hoặc fixture synthetic đã loại bỏ dữ liệu nhạy cảm.

### 3.4. Clock skew trong Spring Security

Spring Security dùng timestamp validator khi xác minh JWT. Có thể cấu hình khoảng clock skew để chấp nhận sai số nhỏ giữa các máy:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(JWK_SET_URI).build();

    JwtTimestampValidator timestamps =
        new JwtTimestampValidator(Duration.ofSeconds(60));

    OAuth2TokenValidator<Jwt> issuer =
        new JwtIssuerValidator(TRUSTED_ISSUER);

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuer,
            timestamps
        )
    );

    return decoder;
}
~~~

Đây là ví dụ minh họa; hãy giữ các validators khác của ứng dụng, đặc biệt audience và token profile. Clock skew phải nhỏ và dựa trên đo đạc thực tế. Tăng skew quá lớn có thể kéo dài thời gian chấp nhận token sau `exp` hoặc chấp nhận token trước `nbf`.

**Clock skew không thay thế NTP.** Nếu các node lệch vài phút hoặc vài giờ, sửa đồng bộ thời gian trước. Cấu hình skew chỉ hấp thụ sai số vận hành nhỏ và có chủ đích.

### 3.5. Kiểm tra thời gian trong test

Unit tests của code do ứng dụng kiểm soát nên dùng Clock có thể thay thế để không phụ thuộc đồng hồ thật:

~~~java
@Bean
@Primary
Clock applicationClock() {
    return Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
    );
}
~~~

Đây là ví dụ cho service sử dụng `Clock`. Không giả định bean Clock tự động điều khiển clock nội bộ của mọi decoder; nếu test validator/decoder, cấu hình clock/skew qua API mà version Spring Security đang dùng hỗ trợ hoặc tạo token fixture với timestamps xác định.

## 4. DNS và khả năng tìm thấy Authorization Server

### 4.1. DNS nằm ở outbound identity path

Khi cấu hình Resource Server bằng issuer URI, framework có thể cần truy cập metadata discovery để tìm JWKS URI. Khi JWT đến, decoder cần kết nối JWKS endpoint để lấy public keys. Với opaque token, introspector cần resolve host của introspection endpoint.

Một lỗi DNS có thể xuất hiện dưới các dạng:

- UnknownHostException.
- Name or service not known.
- Temporary failure in name resolution.
- Connection timeout sau khi resolve ra IP cũ.
- Một pod resolve được hostname nhưng pod khác không resolve được.
- Private DNS zone không được liên kết với subnet/cluster.
- Search domain hoặc split-horizon DNS trả kết quả khác giữa môi trường.

### 4.2. Kiểm tra DNS từ đúng runtime

Kiểm tra từ laptop không đủ nếu ứng dụng chạy trong Kubernetes, container, VM hoặc private subnet. Hãy thực hiện trong cùng network namespace hoặc một diagnostic pod có cùng DNS/network policy.

Linux:

~~~bash
getent hosts id.example.test
nslookup id.example.test
dig id.example.test A
dig id.example.test AAAA
cat /etc/resolv.conf
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName id.example.test
nslookup id.example.test
ipconfig /all
~~~

Nếu ứng dụng chạy trong Kubernetes, có thể dùng một pod chẩn đoán trong namespace và network policy tương ứng. Không cài thêm package vào production image chỉ để kiểm tra tạm thời nếu quy trình vận hành đã có ephemeral debug container.

Kiểm tra cả A và AAAA record. Một môi trường có IPv6 record nhưng route IPv6 không hoạt động có thể gặp timeout dù IPv4 vẫn dùng được. Xác minh DNS trả về đúng địa chỉ private/public theo thiết kế.

### 4.3. DNS cache và TTL

DNS resolver, JVM và HTTP client có thể cache kết quả theo TTL hoặc policy riêng. Vì vậy, sửa DNS record chưa chắc làm tất cả JVM dùng IP mới ngay lập tức.

Khi kiểm tra:

- Ghi lại DNS answer và TTL.
- So sánh answer giữa các nodes.
- Xác định JVM DNS cache policy.
- Xác định HTTP connection pool có giữ kết nối tới IP cũ không.
- Kiểm tra proxy có tự resolve hostname ở phía proxy hay không.
- Sau khi thay đổi DNS, theo dõi thời gian hội tụ theo TTL/cache policy.

Không flush cache hoặc restart đồng loạt cluster như bước đầu tiên. Làm rõ cache nào đang giữ giá trị cũ và dùng rolling restart nếu cần theo quy trình triển khai.

### 4.4. Phân biệt DNS lỗi và TCP/egress lỗi

Nếu hostname resolve được nhưng kết nối không thành công, kiểm tra route, firewall, security group, network policy, proxy và port.

Linux:

~~~bash
nc -vz id.example.test 443
curl -v --connect-timeout 5 https://id.example.test/
~~~

Windows:

~~~powershell
Test-NetConnection id.example.test -Port 443
curl.exe -v --connect-timeout 5 https://id.example.test/
~~~

Lệnh curl tới root path chỉ chứng minh một kết nối HTTP/TLS đã được thiết lập hoặc cho thấy lỗi ở một tầng. Nó không chứng minh discovery/JWKS/introspection endpoint đúng. Tiếp tục kiểm tra URL cụ thể mà Resource Server đang sử dụng.

### 4.5. Discovery, JWKS và issuer URI

Với cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Resource Server có thể cần lấy metadata discovery từ issuer để xác định JWKS URI và xác minh issuer. Hãy kiểm tra:

- Issuer URL có đúng scheme, host, path và realm/tenant không?
- Metadata endpoint trả HTTP 200 không?
- Trường `issuer` trong metadata có khớp issuer cấu hình không?
- `jwks_uri` có hostname mà runtime resolve được không?
- JWKS endpoint trả JSON hợp lệ và có key phù hợp với token header `kid` không?
- Proxy có chặn hoặc rewrite path discovery không?

Không lấy URL từ một log cũ rồi giả định đó vẫn là cấu hình hiện tại. Xem effective configuration đã nạp và metadata thực tế từ đúng môi trường.

### 4.6. JWKS cache và key rotation

Resource Server thường cache public keys để tránh tải JWKS cho mỗi request. Khi issuer rotate signing key:

- Token cũ có thể vẫn dùng key cũ trong thời gian overlap.
- Token mới có thể có `kid` mới.
- Resource Server phải tải được JWKS mới hoặc refresh theo behavior của decoder.
- Proxy/DNS/cache có thể tiếp tục đưa request đến endpoint cũ.
- Một node có thể đã refresh trong khi node khác chưa refresh.

Kiểm tra key ID trong JWT header và key IDs trong JWKS. Header `kid` chỉ là hint để chọn key, không phải bằng chứng tin cậy. Không xóa toàn bộ cache trên mọi node nếu chưa hiểu refresh behavior và ảnh hưởng đến provider.

## 5. TLS, certificate chain, hostname và truststore

### 5.1. Hai kết nối TLS khác nhau

Trong kiến trúc Resource Server có thể có ít nhất hai TLS sessions:

1. Client → API gateway/ingress/Resource Server (inbound).
2. Resource Server → Authorization Server/JWKS/introspection (outbound).

Chứng chỉ inbound do gateway hoặc ứng dụng trình bày cho client. Chứng chỉ outbound do issuer trình bày cho Resource Server. Truststore của JVM phía Resource Server thường ảnh hưởng kết nối outbound; certificate configuration của ingress ảnh hưởng inbound.

Một lỗi inbound TLS không nhất thiết là lỗi JWKS TLS. Phải xác định TLS handshake nào thất bại.

### 5.2. Những lỗi TLS thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể |
|---|---|
| PKIX path building failed | JVM không tin CA hoặc thiếu intermediate certificate |
| unable to find valid certification path | Truststore không có CA cần thiết |
| No subject alternative DNS name matching | Hostname không khớp SAN của certificate |
| Certificate expired / not yet valid | Certificate hết hạn hoặc clock sai |
| handshake_failure | TLS version, cipher, mTLS hoặc server policy không tương thích |
| Received fatal alert: certificate_unknown | Peer không tin certificate hoặc chain |
| Connection reset during handshake | Proxy/firewall/TLS inspection hoặc peer đóng kết nối |
| Works with curl, fails in JVM | curl và JVM dùng truststore/provider/TLS config khác |

### 5.3. Kiểm tra certificate chain và SNI

Dùng OpenSSL từ đúng runtime/network path nếu có:

~~~bash
openssl s_client -connect id.example.test:443 -servername id.example.test -showcerts -verify_return_error
~~~

`-servername` chỉ định SNI. Nếu bỏ SNI, server hosting nhiều virtual hosts có thể trả certificate mặc định không khớp hostname.

Kiểm tra:

- Certificate leaf có SAN chứa hostname đang gọi không?
- Certificate có còn hiệu lực theo UTC không?
- Intermediate chain có đầy đủ không?
- Root CA có nằm trong truststore được dùng không?
- Certificate có được thay gần thời điểm deploy không?
- TLS inspection proxy có thay certificate bằng CA nội bộ không?
- JVM có dùng truststore khác với công cụ curl/OpenSSL không?

Không chỉ nhìn subject CN; hostname verification hiện đại dựa vào Subject Alternative Name.

### 5.4. Kiểm tra truststore của JVM

Xem Java runtime:

~~~bash
java -version
~~~

Trong môi trường có thể đọc process arguments, kiểm tra các property liên quan như `javax.net.ssl.trustStore` và `javax.net.ssl.trustStoreType`. Không dump toàn bộ environment hoặc process command line ra ticket nếu có thể chứa secret.

Có thể xem nội dung truststore:

~~~bash
keytool -list -v -keystore /path/to/truststore.p12 -storetype PKCS12
~~~

Lệnh có thể yêu cầu password; nhập qua prompt hoặc secret manager theo quy trình, không ghi password trực tiếp trong shell history hoặc log.

Một ứng dụng có thể dùng truststore mặc định của JDK, truststore riêng, container CA bundle hoặc SSL bundle của Spring Boot. Hãy xác định đúng cơ chế đang hoạt động thay vì import CA vào một file mà JVM không đọc.

### 5.5. Thay đổi CA an toàn

Khi CA nội bộ được yêu cầu:

1. Xác minh fingerprint/certificate chain từ nguồn hạ tầng đáng tin.
2. Xác định truststore/bundle mà process thực sự sử dụng.
3. Thêm CA cần thiết theo quy trình change management.
4. Giữ hostname verification bật.
5. Restart/refresh đúng workload theo cơ chế reload.
6. Kiểm tra TLS handshake và gọi endpoint discovery/JWKS/introspection thật.
7. Theo dõi certificate expiry và rotation.

Không tắt trust validation, hostname verification hoặc dùng trust-all manager để “sửa nhanh”. Cách đó làm mất bảo vệ chống giả mạo Authorization Server.

### 5.6. Mutual TLS (mTLS)

Nếu IdP hoặc gateway yêu cầu client certificate, cần kiểm tra cả hai phía:

- Client certificate còn hạn và có clientAuth EKU phù hợp.
- Private key khớp certificate.
- Certificate chain được server tin.
- JVM/application đang nạp đúng keystore.
- Proxy có chuyển tiếp hoặc terminate mTLS theo contract không.
- Certificate identity được map đúng client/service.

TLS client certificate cho outbound connection khác với certificate-bound access token. Việc kết nối mTLS thành công không tự chứng minh token được ràng buộc certificate hoặc request được authorize.

## 6. Proxy, reverse proxy và forwarded headers

### 6.1. Xác định proxy đang nằm ở chiều nào

Có thể có:

- Outbound forward proxy cho Resource Server gọi issuer/JWKS/introspection.
- Inbound reverse proxy/load balancer trước API.
- Service mesh sidecar intercept outbound/inbound traffic.
- TLS-terminating ingress.
- API gateway xác thực sơ bộ hoặc rewrite route.

Không gộp chúng thành một “proxy issue”. Mỗi proxy có route, trust boundary và log riêng.

### 6.2. Outbound proxy

Nếu JVM phải đi qua corporate proxy để gọi issuer, cấu hình proxy có thể ảnh hưởng đến discovery và JWKS. Tùy HTTP client/transport, proxy có thể được cấu hình qua JVM system properties hoặc client-specific settings.

Các thuộc tính JVM thường gặp:

~~~text
https.proxyHost
https.proxyPort
http.proxyHost
http.proxyPort
http.nonProxyHosts
~~~

Không giả định mọi Spring Security decoder, WebClient hoặc HTTP client đều tự dùng cùng proxy settings. Kiểm tra transport thực tế mà application cấu hình cho decoder/introspector. Nếu proxy yêu cầu authentication, dùng cơ chế secret an toàn; không nhúng proxy password vào YAML hoặc command line.

Kiểm tra:

- Host/port proxy có đúng ở pod/node không?
- Host issuer có nằm trong `nonProxyHosts` ngoài ý muốn không?
- Proxy có cho phép CONNECT tới port 443 không?
- Proxy có yêu cầu authentication không?
- TLS inspection có thay certificate không?
- DNS được resolve ở client hay ở proxy?
- Proxy timeout/connection limit có bị chạm không?

### 6.3. Inbound reverse proxy và TLS termination

Một client có thể gọi:

~~~text
https://api.example.test/api/orders
~~~

Trong khi backend nhận kết nối nội bộ:

~~~text
http://orders-service:8080/api/orders
~~~

Nếu ứng dụng tạo absolute URL, redirect, issuer metadata hoặc kiểm tra origin từ request, nó cần biết external scheme/host đúng. Spring Boot có thể xử lý forwarded headers qua cấu hình server forward headers strategy phù hợp.

Ví dụ:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Giá trị cụ thể phụ thuộc Spring Boot version và hạ tầng. Có thể dùng native container support hoặc framework strategy theo hướng dẫn version-matched. Đừng bật trust forwarded headers trên đường truy cập trực tiếp từ client không tin cậy.

### 6.4. Forwarded headers là dữ liệu có trust boundary

Các header thường gặp:

~~~http
Forwarded: proto=https;host=api.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /gateway
~~~

Nếu backend tin mọi giá trị do client gửi, attacker có thể giả mạo scheme/host/prefix. Proxy tin cậy phải strip header forwarded do client cung cấp rồi ghi giá trị của chính proxy. Backend chỉ nên nhận forwarded metadata từ proxy/network path đã được xác định.

Kiểm tra:

- Ingress có xóa các header client tự gửi không?
- Ingress thêm đúng proto, host, port và prefix không?
- Backend có thể truy cập trực tiếp từ Internet hoặc mạng không tin cậy không?
- Có nhiều proxy hop và thứ tự forwarded chain có được hiểu đúng không?
- Path prefix có bị thêm/bỏ hai lần không?
- Spring application có tạo URL external đúng không?

### 6.5. Proxy làm mất Authorization header

Một số gateway route hoặc filter có thể strip/overwrite `Authorization`. Triệu chứng là API nhận request nhưng authentication context anonymous hoặc trả 401.

Đối chiếu request tại client, gateway access log (chỉ log sự hiện diện, không log giá trị token), và backend. Kiểm tra route policy, header allowlist, token relay và gateway authentication mode.

Không yêu cầu log toàn bộ bearer token để debug. Có thể ghi boolean `authorization_header_present`, scheme name, request ID và gateway route ID.

### 6.6. Path rewrite và security matchers

Proxy có thể chuyển:

~~~text
Public:  /gateway/orders/42
Backend: /api/orders/42
~~~

Nếu security matcher hoặc forwarded prefix không thống nhất, request có thể rơi vào chain khác hoặc endpoint matcher không như mong đợi.

Ghi nhận URI public, URI backend, context path, servlet path/path within application và chain matcher. Test qua đúng ingress/gateway configuration nếu lỗi chỉ xuất hiện ở production.

## 7. Cấu hình môi trường và configuration drift

### 7.1. Một codebase có thể nhận cấu hình khác nhau

Spring Boot nạp cấu hình từ nhiều nguồn: packaged config files, profile-specific files, environment variables, command-line arguments, external config và secret mounts. Giá trị cuối cùng có thể khác nhau giữa local, test, staging và production.

Những thuộc tính Resource Server quan trọng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Tên property hỗ trợ audience và behavior có thể phụ thuộc Spring Boot/Spring Security version hoặc custom configuration. Nếu version dự án không hỗ trợ property đó, audience validator phải được cấu hình trong code. Đừng sao chép YAML từ version khác mà không xác nhận effective configuration.

### 7.2. Kiểm tra profile và effective configuration

Kiểm tra:

- Active Spring profiles.
- Issuer URI và JWKS URI sau khi resolve.
- Audience allowlist.
- Introspection URI và client ID (không in secret).
- Proxy host/port/non-proxy rules.
- SSL bundle/truststore reference.
- Clock skew và token validators.
- Timeout, connection pool và cache settings.
- Ingress host/path và forwarded-header strategy.
- Secret version/mount timestamp.

Spring Boot Actuator có thể cung cấp thông tin health và environment tùy cấu hình. Không public endpoint `env` hoặc `configprops` nếu chưa được bảo vệ và sanitize; chúng có thể tiết lộ cấu hình nhạy cảm.

### 7.3. Environment variables và tên property

Environment có thể override YAML. Spring Boot relaxed binding chuyển đổi tên property sang dạng uppercase/underscore theo quy tắc của Boot. Khi debug, xác định biến thực tế trong container deployment manifest/secret references, không chỉ xem file YAML trong repository.

Không in toàn bộ environment variables. Chỉ inspect allowlist các key không bí mật hoặc redacted values. Với secret, xác minh presence, version và mount path mà không hiển thị giá trị.

### 7.4. Secret rotation và config reload

Client secret của introspection endpoint, truststore password hoặc private key có thể được rotate ở secret manager nhưng application process vẫn giữ giá trị cũ.

Kiểm tra:

- Secret version được mount vào workload.
- File/volume có được cập nhật không?
- Application có hỗ trợ reload hay chỉ đọc lúc startup?
- Pod rollout có thực sự thay thế tất cả instances?
- Old/new secret có overlap theo contract của IdP không?
- Một node cũ còn nhận traffic không?

Không chia sẻ secret qua ticket/chat hoặc copy vào log. Dùng secret reference và version identifier.

### 7.5. Nhiều cấu hình SecurityFilterChain

Một ứng dụng có thể có nhiều `SecurityFilterChain` với `@Order` và `securityMatcher` khác nhau. Một request có thể đi qua chain không chứa Resource Server config mà người vận hành đang kiểm tra.

Kiểm tra matcher nào khớp URI public/backend, chain nào có `oauth2ResourceServer()`, có chain catch-all đứng trước chain API không, gateway có rewrite path làm matcher thay đổi không, và test profile có thay security configuration không.

Log debug Spring Security chỉ bật tạm trong môi trường được kiểm soát; tránh để verbose authentication logs kéo dài trên production.

## 8. Cấu hình outbound HTTP và timeout

Discovery/JWKS/introspection là outbound HTTP dependencies. Timeout quá ngắn gây lỗi chập chờn; timeout quá dài có thể giữ request threads hoặc reactive resources quá lâu.

Phân biệt:

- DNS lookup timeout.
- TCP connect timeout.
- TLS handshake timeout.
- HTTP response timeout.
- Connection pool acquisition timeout.
- Retry/backoff.
- Circuit breaker/open state.
- JWKS cache refresh timeout.

Không chỉ tăng mọi timeout. Đo latency từng hop và chọn timeout theo service-level objective. Với reactive stack, dùng non-blocking HTTP client và tránh gọi blocking APIs trên event loop.

Đối với opaque token, introspection thường nằm trên request path nên availability/latency của IdP ảnh hưởng trực tiếp API. Với JWT, key có thể đã được cache nên API vẫn xác minh token khi IdP tạm thời không truy cập được, nhưng key rotation hoặc cache miss có thể làm request thất bại.

## 9. Quy trình chẩn đoán theo thứ tự

Một runbook hữu ích có thể đi theo các bước:

~~~text
1. Capture request ID, timestamp UTC, node/pod, route and status.
2. Confirm Authorization header reached the application (presence only).
3. Confirm which SecurityFilterChain handled the request.
4. If JWT: inspect issuer/audience/time/key ID validation category.
5. If remote key/introspection lookup failed:
     a. resolve hostname from the application runtime
     b. test TCP route and proxy path
     c. inspect TLS chain, SNI and truststore
     d. call the exact discovery/JWKS/introspection URL
6. Compare effective non-secret configuration across healthy and failing nodes.
7. Check NTP offset and DNS/cache differences between nodes.
8. Reproduce with a synthetic token and controlled environment.
9. Apply the smallest verified correction and roll out safely.
10. Confirm recovery across all nodes and monitor error rate.
~~~

### 9.1. Bắt đầu từ một request cụ thể

Ghi lại:

- UTC timestamp.
- Request/correlation ID.
- API route và HTTP method.
- Backend node/pod.
- HTTP status.
- Error category, exception class và sanitized cause.
- Token type (JWT/opaque/DPoP) và issuer alias.
- Thời điểm deploy/config/secret rotation gần nhất.

Không ghi raw token, claims nhạy cảm, PII hoặc client secret.

### 9.2. Xác định token đã đến ứng dụng chưa

Nếu gateway nhận request nhưng backend không thấy Authorization header, xử lý gateway route/header policy. Nếu backend nhận header nhưng không có Authentication, xem filter chain, scheme, token extraction và decoder/introspector errors.

### 9.3. Xác định local hay remote validation failure

JWT signature/claims validation có thể thất bại mà không cần network call nếu key đã cache. Nếu error là UnknownHost/SSLHandshake/timeout, xác định outbound URL thực tế là issuer discovery, JWKS hay introspection.

### 9.4. So sánh node tốt và node lỗi

Đối chiếu hai node cùng nhận request:

- Clock offset.
- DNS answer.
- JVM version và truststore.
- Active profiles/effective issuer.
- Secret version.
- Proxy settings.
- Pod image digest.
- Security chain/config revision.

Nếu chỉ một node lỗi, không thay policy toàn cluster trước khi kiểm tra node drift.

## 10. Lệnh chẩn đoán thực tế

### 10.1. Linux/container

~~~bash
date -u
timedatectl status
getent hosts id.example.test
cat /etc/resolv.conf
curl -v --connect-timeout 5 https://id.example.test/realms/shop/.well-known/openid-configuration
openssl s_client -connect id.example.test:443 -servername id.example.test -showcerts
~~~

### 10.2. Windows PowerShell

~~~powershell
Get-Date -AsUTC
w32tm /query /status
Resolve-DnsName id.example.test
Test-NetConnection id.example.test -Port 443
curl.exe -v --connect-timeout 5 https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

### 10.3. Kiểm tra metadata và JWKS

Sau khi discovery endpoint trả về, xác nhận:

- Issuer trong metadata khớp cấu hình.
- JWKS URI có thể resolve và kết nối từ application runtime.
- JWKS response là JSON hợp lệ.
- Key có `kid` phù hợp với token mới.
- Key type/algorithm tương thích với token.
- Certificate/hostname của cả discovery và JWKS endpoint hợp lệ.

Không giả định discovery và JWKS cùng hostname. Provider có thể đặt JWKS trên một domain khác, do đó phải kiểm tra DNS, proxy và TLS cho từng hostname.

### 10.4. Kiểm tra TLS bằng JVM

Nếu OpenSSL/curl thành công nhưng JVM thất bại, so sánh CA bundle, truststore, TLS provider, proxy và Java runtime. Có thể bật SSL debug có giới hạn trong một môi trường test/staging:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

Log này rất dài và có thể chứa thông tin môi trường. Chỉ bật tạm thời, giới hạn thời gian/traffic, lưu trữ an toàn và tắt ngay sau khi thu thập đủ bằng chứng.

## 11. Log, metrics và health checks

### 11.1. Log theo error category

Nên phân loại lỗi để biết failure domain:

| Category | Ví dụ |
|---|---|
| `jwt_expired` | Token hết hạn theo clock validator |
| `jwt_not_yet_valid` | `nbf` nằm ngoài clock skew |
| `jwt_issuer_invalid` | Issuer mismatch |
| `jwt_audience_invalid` | Audience không phù hợp |
| `jwks_dns_failure` | Không resolve được JWKS host |
| `jwks_tls_failure` | TLS trust/hostname failure |
| `jwks_http_failure` | HTTP status/timeout từ JWKS |
| `introspection_unavailable` | Introspection dependency lỗi |
| `proxy_connect_failure` | Không kết nối được outbound proxy |
| `forwarded_header_mismatch` | External host/scheme/path sai |
| `configuration_mismatch` | Node dùng issuer/profile/secret version khác |

Log nên có request ID, node ID, issuer alias, dependency hostname alias, error category và elapsed time. Không log Authorization header, JWT compact string, refresh token, private JWK, client secret hoặc truststore password.

### 11.2. Metrics

Các metrics hữu ích:

- Authentication success/failure theo error category.
- JWT validation failure theo issuer alias và reason.
- JWKS fetch latency/error count/cache refresh.
- Introspection latency/error/timeout.
- DNS/TCP/TLS connection failures nếu transport cung cấp.
- Clock offset/NTP synchronization health từ node monitoring.
- Request 401/403 rate theo route.
- Proxy connection pool saturation.
- Number of nodes/pods running each config revision.

Không dùng raw subject, tenant ID, token ID hoặc URL có ID người dùng làm metric labels cardinality cao.

### 11.3. Readiness và liveness

Liveness nên phản ánh process còn hoạt động; không nhất thiết restart ứng dụng chỉ vì IdP tạm thời unavailable.

Readiness có thể phản ánh dependency quan trọng theo service policy, nhưng cần tránh tạo restart storm hoặc loại toàn bộ instances khỏi load balancer khi issuer có sự cố toàn cục. JWT Resource Server với cached JWKS có thể tiếp tục xử lý token đã biết trong một số trường hợp; opaque introspection thường phụ thuộc IdP trực tiếp hơn.

Không public Actuator health/details cho anonymous Internet. Bảo vệ endpoint và sanitize dependency metadata.

## 12. Sự cố theo từng thành phần

### 12.1. Clock lệch trên một node

**Dấu hiệu:** cùng token, cùng request nhưng chỉ một pod trả 401; error liên quan expired/not-before.

**Kiểm tra:** NTP source, UTC offset, node time, container runtime và timestamp log.

**Xử lý:** sửa time synchronization theo platform runbook, xác nhận offset hội tụ, sau đó replay request bằng token mới. Không tăng clock skew toàn hệ thống để che một node drift.

### 12.2. DNS chỉ lỗi trong cluster

**Dấu hiệu:** laptop gọi issuer được nhưng pod không resolve; lỗi UnknownHost hoặc timeout.

**Kiểm tra:** resolver config trong pod, CoreDNS, private DNS zone, network policy, A/AAAA records và DNS answer theo node.

**Xử lý:** sửa zone/forwarder/network policy, chờ TTL/cache theo kế hoạch và kiểm tra từng pod. Không hard-code IP của IdP vào ứng dụng nếu hostname/SNI/certificate contract yêu cầu domain.

### 12.3. TLS trust lỗi sau khi certificate rotate

**Dấu hiệu:** trước deploy hoạt động, sau khi IdP/ingress thay certificate thì JVM báo PKIX failure.

**Kiểm tra:** certificate chain mới, issuer CA, intermediate, truststore thực tế, certificate validity và SNI.

**Xử lý:** cập nhật CA bundle/truststore được quản lý, kiểm thử outbound TLS, rollout có kiểm soát. Giữ hostname verification bật.

### 12.4. Proxy không cho phép JWKS endpoint

**Dấu hiệu:** discovery host truy cập được nhưng `jwks_uri` timeout hoặc 403; chỉ production egress bị lỗi.

**Kiểm tra:** hostname JWKS có nằm trong proxy allowlist, CONNECT policy, non-proxy rules, proxy authentication và TLS inspection.

**Xử lý:** cập nhật egress policy cho đúng endpoint; kiểm tra lại từ application runtime. Không bỏ qua TLS validation để vượt proxy inspection.

### 12.5. Issuer URI khác giữa staging và production

**Dấu hiệu:** token được ký đúng nhưng issuer validator reject; metadata issuer không trùng cấu hình.

**Kiểm tra:** effective issuer property, trailing slash/path/realm, profile, config map/secret revision và issuer claim trong token.

**Xử lý:** thống nhất issuer canonical URI theo provider contract, cập nhật config và rollout. Không sửa claim issuer trong token hoặc bỏ issuer validator để làm request pass.

### 12.6. Reverse proxy báo HTTP trong backend

**Dấu hiệu:** ứng dụng tạo redirect hoặc absolute URL dùng http/internal host dù client gọi https/public host.

**Kiểm tra:** TLS termination, Forwarded/X-Forwarded headers, proxy strip/rewrite và Spring forward headers strategy.

**Xử lý:** cấu hình trusted proxy, strip untrusted forwarded headers, gửi đúng external metadata và giới hạn backend access.

### 12.7. Một node vẫn dùng secret/truststore cũ

**Dấu hiệu:** một số requests tới cùng endpoint thành công, một số thất bại; lỗi theo pod.

**Kiểm tra:** image/config revision, mounted secret version, truststore checksum, startup timestamp và rollout status.

**Xử lý:** hoàn tất rolling deployment, loại instance cũ theo quy trình, xác nhận từng pod dùng cùng revision. Không copy secret vào log để so sánh; so sánh version/checksum được phép.

## 13. An toàn khi bật debug và thu thập bằng chứng

Spring Security có thể bật DEBUG/TRACE để quan sát filter chain và authentication flow. Dùng tạm thời ở môi trường có kiểm soát, giới hạn logger/package và thời gian.

Trước khi gửi log ra ngoài, redaction:

- Authorization/Bearer headers.
- JWT compact strings và refresh tokens.
- Client secrets và introspection credentials.
- Private keys, keystore/truststore passwords.
- PII trong claims, tenant/user identifiers.
- Internal hostnames/IPs nếu được phân loại nhạy cảm.
- Certificate private material.

Có thể log issuer alias, `kid`, thumbprint prefix, host alias, status code, request ID và error category nếu policy cho phép. Không cần log token để xác định một node có đang dùng key ID mới hay không.

## 14. Runbook xử lý sự cố mẫu

### Tình huống A — Tất cả requests JWT trả 401 sau deploy

1. Xác nhận timestamp UTC và deploy revision.
2. Kiểm tra issuer/audience effective config.
3. Kiểm tra clock/NTP trên tất cả nodes.
4. Lấy một token synthetic đã ký bằng test key và xác minh local decoder.
5. Nếu lỗi key retrieval, kiểm tra DNS → proxy → TLS → JWKS URL.
6. So sánh truststore/secret/profile trước và sau deploy.
7. Khôi phục config đã biết tốt nếu thay đổi gần nhất gây lỗi và rollback được phê duyệt.

### Tình huống B — Chỉ token mới lỗi sau key rotation

1. Đọc `kid` của token mới từ fixture/log đã sanitize.
2. Kiểm tra JWKS response có public key tương ứng không.
3. Kiểm tra Resource Server có truy cập được JWKS host mới không.
4. Kiểm tra DNS, proxy, TLS và cache refresh behavior.
5. Xác nhận issuer giữ overlap giữa key cũ và mới theo rotation plan.
6. Kiểm tra từng node đã refresh key set chưa.

### Tình huống C — Opaque token lỗi chập chờn

1. Xác định introspection endpoint và outbound client thực tế.
2. Đo DNS, connect, TLS, HTTP response và pool acquisition latency.
3. Kiểm tra client authentication/secret version.
4. Kiểm tra proxy timeout, rate limit và IdP availability.
5. Phân biệt invalid/inactive token với dependency unavailable.
6. Theo dõi 401/5xx và latency sau khi khôi phục.

### Tình huống D — Chỉ lỗi qua gateway

1. So sánh request public và backend path.
2. Xác nhận Authorization header được chuyển tiếp.
3. Xác nhận host/proto/port/prefix forwarded headers.
4. Xác nhận ingress strip client-supplied forwarded headers.
5. Kiểm tra security chain matcher và context path.
6. Chạy integration test qua ingress hoặc staging route tương đương.

## 15. Cấu hình môi trường nên được kiểm soát thế nào?

Một configuration baseline nên ghi nhận các giá trị không bí mật và nguồn sở hữu:

| Nhóm | Cấu hình cần quản lý | Nguồn có thẩm quyền |
|---|---|---|
| Identity | Issuer URI, audience, JWKS/introspection URI | Identity platform |
| Trust | CA bundle, truststore reference, certificate policy | Platform/security team |
| Network | DNS zone, egress proxy, allowlist, route | Network/platform team |
| Time | NTP source, max offset policy | Infrastructure |
| Application | Spring profile, filter chains, validators, timeouts | Application team |
| Secrets | Client secret/cert reference và version | Secret manager |
| Edge | Public host, TLS termination, forwarded header policy | Gateway/ingress owner |
| Observability | Request ID, error categories, metrics | Operations team |

Không nhất thiết mọi giá trị đều giống nhau giữa môi trường; chúng cần khác nhau có chủ đích và được kiểm soát. Ví dụ issuer staging khác production là bình thường nếu token issuer và trust configuration cùng khớp.

Nên có startup validation cho các thuộc tính bắt buộc: issuer URI hợp lệ, audience không rỗng, timeout dương, truststore tồn tại, proxy configuration hợp lệ. Không log giá trị secret khi validation thất bại.

## 16. Checklist kiểm tra trước khi kết luận lỗi ở code

- [ ] Đã xác định inbound hay outbound hop đang thất bại.
- [ ] Đã ghi request ID, node/pod và timestamp UTC.
- [ ] Đồng hồ node được đồng bộ NTP và offset nằm trong policy.
- [ ] `exp`, `nbf` và `iat` được đối chiếu với clock thực tế.
- [ ] Clock skew nhỏ, có chủ đích và nhất quán.
- [ ] DNS được kiểm tra từ đúng runtime/network namespace.
- [ ] A/AAAA records, TTL và DNS cache được kiểm tra.
- [ ] TCP route, firewall và egress policy được xác nhận.
- [ ] Discovery, JWKS hoặc introspection URL thực tế được kiểm tra riêng.
- [ ] TLS chain, SAN, expiry, SNI và truststore đúng.
- [ ] mTLS keystore/certificate được kiểm tra nếu provider yêu cầu.
- [ ] Outbound proxy, CONNECT, authentication và non-proxy rules đúng.
- [ ] Inbound reverse proxy chuyển tiếp Authorization header.
- [ ] Forwarded headers chỉ được tin từ proxy đáng tin.
- [ ] Public host/scheme/path khớp cấu hình ứng dụng.
- [ ] Active profiles và effective issuer/audience được xác nhận.
- [ ] Secret/truststore version giống nhau trên các nodes mong đợi.
- [ ] SecurityFilterChain đúng đang xử lý endpoint.
- [ ] Logs/metrics phân loại lỗi mà không chứa credential.
- [ ] Readiness/liveness không tạo restart storm khi IdP tạm thời lỗi.
- [ ] Sau thay đổi, xác nhận recovery trên tất cả nodes và theo dõi error rate.

## 17. Kết luận

Sự cố OAuth 2.0/OIDC Resource Server không phải lúc nào cũng xuất phát từ token hoặc security code. Clock drift có thể làm JWT hết hạn theo góc nhìn của một node; DNS có thể ngăn tải discovery/JWKS; TLS trust có thể chặn kết nối tới issuer; proxy có thể làm mất Authorization header hoặc thay đổi public URI; configuration drift có thể khiến các pods dùng issuer, secret hoặc truststore khác nhau.

Chẩn đoán hiệu quả cần theo đúng đường đi của request:

1. **Clock:** kiểm tra UTC, NTP và các JWT time claims.
2. **DNS/network:** resolve từ runtime thật, kiểm tra route và đúng endpoint.
3. **TLS:** xác minh chain, SAN, SNI, truststore và mTLS.
4. **Proxy:** tách outbound proxy khỏi inbound reverse proxy; kiểm tra header và URI forwarding.
5. **Environment:** so sánh effective configuration, profiles, secret versions và node revisions.
6. **Observability:** dùng request ID, error category và metrics để xác định hop lỗi mà không log credential.

Chỉ thay đổi cấu hình sau khi xác định được failure domain, sau đó kiểm tra lại từ đúng runtime và trên toàn bộ instances. Không tắt TLS validation, bỏ issuer validation hoặc nới clock skew lớn để che một lỗi hạ tầng.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Multi-tenancy for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot Reference — HTTP Forwarded Headers](https://docs.spring.io/spring-boot/reference/howto/webserver.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)







