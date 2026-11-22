# TLS termination, mTLS và identity forwarding

## 1. Vai trò của TLS trong triển khai API

TLS bảo vệ kênh truyền giữa hai điểm kết nối. Khi được cấu hình đúng, TLS cung cấp:

- **Confidentiality:** bên thứ ba trên đường truyền khó đọc được dữ liệu.
- **Integrity:** phát hiện dữ liệu bị sửa đổi trên kênh.
- **Peer authentication:** client xác minh server; với mutual TLS (mTLS), server cũng xác minh client certificate.

Trong triển khai API, TLS có thể kết thúc ở CDN, load balancer, ingress controller, API gateway, service mesh sidecar hoặc ngay trong application. Điểm kết thúc TLS là một trust boundary: thành phần đó nhìn thấy plaintext sau khi giải mã và chịu trách nhiệm bảo vệ dữ liệu trước khi chuyển tiếp.

TLS không tự quyết định user được gọi function nào, object nào hoặc tenant nào. HTTPS server authentication, mTLS workload authentication, OAuth/OIDC authentication và authorization là các lớp khác nhau. Một kết nối mTLS thành công chỉ chứng minh peer sở hữu certificate được trust theo cấu hình; ứng dụng vẫn phải kiểm tra permission và business policy.

## 2. Phân biệt TLS termination, passthrough và re-encryption

Ba topology phổ biến:

| Mô hình | Luồng kết nối | Đặc điểm và trade-off |
|---|---|---|
| TLS termination tại edge | Client --TLS--> Gateway --HTTP--> Service | Gateway giải mã request; hop nội bộ là plaintext và trở thành trust boundary lớn |
| TLS termination rồi re-encrypt | Client --TLS--> Gateway --TLS/mTLS--> Service | Gateway đọc được request; hop tới service tiếp tục được mã hóa và có thể xác thực workload |
| TLS passthrough | Client --TLS xuyên qua L4 proxy--> Application | Application tự kết thúc TLS; proxy không đọc HTTP payload để áp dụng L7 policy |

Một số hệ thống có nhiều hop:

~~~text
Client
  |
  | TLS (server authentication, optional client mTLS)
  v
CDN / WAF
  |
  | TLS hoặc mTLS
  v
API Gateway / Ingress
  |
  | mTLS với workload identity
  v
Service mesh sidecar
  |
  | mTLS
  v
Application service
~~~

Service mesh có thể kết thúc một kết nối mTLS ở sidecar rồi thiết lập kết nối mTLS mới tới sidecar đích. Đây là hai TLS session riêng, không phải một TLS session end-to-end xuyên suốt mọi proxy.

### 2.1 TLS termination tại edge

Gateway giữ server certificate/private key, giải mã HTTP và áp dụng routing, WAF, authentication plugin, rate limit hoặc request validation. Nếu gateway gửi HTTP plaintext tới upstream, bất kỳ thành phần nào có thể quan sát network segment đó đều có thể đọc request và response.

Chỉ dùng plaintext trên hop nội bộ khi threat model, network isolation, host boundary và dữ liệu cho phép rõ ràng. “Private network” hoặc “cùng VPC” không tự động có nghĩa là đáng tin; workload bị xâm nhập, packet capture hoặc route sai vẫn có thể làm lộ dữ liệu.

### 2.2 Re-encryption tới upstream

Gateway kết thúc TLS bên ngoài rồi mở TLS mới tới upstream. Với mTLS, gateway xác minh server certificate của upstream và upstream xác minh client certificate của gateway.

Đây thường là lựa chọn phù hợp khi cần L7 inspection ở gateway nhưng vẫn muốn bảo vệ dữ liệu trên network nội bộ và xác thực workload ở mỗi hop.

### 2.3 TLS passthrough

L4 proxy chuyển tiếp luồng TLS mà không giải mã HTTP. Application hoặc ingress phía sau phải sở hữu certificate và thực hiện TLS policy.

Passthrough giữ TLS session giữa client và backend, nhưng gateway ở giữa không thể đọc HTTP path/body để thực thi L7 authorization, schema validation hoặc WAF rule. Một số proxy vẫn có thể định tuyến theo SNI, nhưng SNI không thay thế xác thực host và application authorization.

## 3. Chọn topology theo trust boundary

Trước khi cấu hình, trả lời:

- Thành phần nào được phép thấy plaintext?
- Private key của server certificate được lưu và truy cập ở đâu?
- Client certificate được xác minh ở edge hay tại application?
- Gateway có cần đọc HTTP để routing, WAF, rate limit hoặc validate schema không?
- Có bao nhiêu network hop từ edge tới application?
- Upstream có thể bị gọi trực tiếp ngoài gateway không?
- Service nào được phép gọi service nào?
- Khi gateway bị compromise, attacker có thể impersonate những workload nào?

Không có một topology đúng cho mọi hệ thống. Một API public thường cần TLS ở edge; các hop giữa gateway và service nên dùng TLS/mTLS khi network boundary hoặc dữ liệu yêu cầu. Một API cần giữ client certificate tới application có thể dùng passthrough hoặc xác minh ở edge rồi chuyển identity bằng assertion được bảo vệ.

## 4. TLS server configuration

Server certificate phải:

- Được cấp bởi CA mà client dự kiến trust.
- Có SAN phù hợp với hostname client sử dụng.
- Có key usage/extended key usage phù hợp cho TLS server.
- Còn hiệu lực và có chuỗi certificate hợp lệ.
- Dùng private key được bảo vệ, giới hạn người/process có quyền đọc.

Client cần xác minh certificate chain và hostname. Không tắt hostname verification hoặc trust mọi certificate để “sửa lỗi handshake”. Không dựa vào Common Name cũ khi SAN là nguồn định danh hostname theo chuẩn hiện đại.

Policy triển khai nên:

- Ưu tiên TLS 1.3; hỗ trợ TLS 1.2 khi compatibility yêu cầu và cấu hình cipher suite an toàn.
- Tắt SSLv3, TLS 1.0 và TLS 1.1.
- Dùng certificate/key algorithm và key size còn được khuyến nghị.
- Quản lý SNI, ALPN và HTTP/2 theo listener.
- Redirect HTTP sang HTTPS nếu listener HTTP cần tồn tại.
- Bật HSTS cho domain HTTPS phù hợp; chỉ dùng includeSubDomains/preload khi mọi subdomain đã sẵn sàng.
- Không để debug endpoint hoặc admin interface dùng policy yếu hơn.

TLS policy phải được kiểm tra ở CDN, load balancer, gateway và application; cấu hình ở một hop không bảo vệ các listener khác.

## 5. Certificate identity: xác minh đúng danh tính

Certificate có thể chứa nhiều thông tin, nhưng authorization nên dựa trên định danh ổn định và được quản lý:

- Server identity thường được xác minh qua DNS SAN.
- Workload identity có thể dùng URI SAN, ví dụ SPIFFE ID.
- Client certificate identity phải được ánh xạ tới principal/service account đã đăng ký.
- CA chain, EKU, key usage, validity period và policy của issuer đều cần được kiểm tra.

Không authorize bằng cách so sánh một chuỗi DN/CN tùy ý hoặc tìm substring như CN=admin. Subject DN có thể thay đổi format, thứ tự hoặc encoding; tên có thể không duy nhất. Dùng SAN theo profile đã định nghĩa, issuer được trust và mapping identity rõ ràng.

Ví dụ workload identity:

~~~text
spiffe://example.internal/ns/payments/sa/payment-api
~~~

Giá trị trên chỉ là ví dụ. Trust domain, namespace và service account phải khớp identity registry của hệ thống.

## 6. mTLS từ external client tới edge

Với client certificate authentication, TLS handshake gồm xác minh certificate của server và certificate của client:

1. Client kết nối tới hostname API.
2. Server trình certificate và chứng minh sở hữu private key.
3. Server yêu cầu client certificate nếu listener bật mTLS.
4. Client gửi certificate chain và chứng minh sở hữu private key.
5. Edge kiểm tra chain, issuer/trust anchor, validity, EKU, SAN và policy thu hồi.
6. Edge ánh xạ certificate identity sang client principal.
7. Sau handshake, application/gateway tiếp tục kiểm tra quyền trên operation và resource.

mTLS phù hợp với partner integration, machine-to-machine API, device identity hoặc môi trường có yêu cầu certificate-based client authentication.

### 6.1 Trust store và CA

Trust store cần chứa đúng CA/intermediate được phép cấp client certificate cho API. Tránh trust toàn bộ public CA nếu chỉ một nhóm partner được phép kết nối; certificate do một public CA hợp lệ cấp không có nghĩa holder được quyền gọi API nội bộ.

Có thể dùng private CA hoặc dedicated issuing CA cho client workload. Tách CA theo environment hoặc trust domain giúp giảm blast radius và làm rõ chính sách cấp phát.

### 6.2 Kiểm tra certificate client

Không chỉ kiểm tra certificate có chain hợp lệ. Cần kiểm tra:

- NotBefore/NotAfter.
- Certificate path và trust anchor.
- Extended Key Usage cho client authentication.
- Key usage phù hợp.
- SAN identity nằm trong registry/allowlist.
- Issuer/CA được phép cho API này.
- Revocation theo khả năng và policy của hệ thống.

Không dùng certificate đã hết hạn, sai SAN hoặc sai EKU chỉ vì handshake có thể được cấu hình permissive. Certificate hợp lệ về mật mã vẫn có thể thuộc client không được phép truy cập API cụ thể.

## 7. mTLS giữa workload/service

Trong service-to-service communication, mỗi workload nên có identity riêng. Ví dụ:

~~~text
order-service  --mTLS-->  payment-service
notification   --mTLS-->  order-service
admin-worker   --mTLS-->  audit-service
~~~

Service nhận xác minh certificate của caller và áp dụng service authorization:

- order-service được gọi payment authorize/capture theo policy.
- notification không được gọi payment refund.
- admin-worker chỉ được gửi audit event vào interface đã định.

Không cấp một certificate chung cho cả cluster nếu cần phân biệt workload. Không dùng “mọi certificate do cluster CA cấp đều được gọi mọi service”. Trust CA trả lời ai có thể được xác thực; authorization policy quyết định identity nào được gọi service/method nào.

Với service mesh, bật strict mTLS cho workload cần bảo vệ, khai báo service identity và authorization policy theo namespace/service account. Kiểm tra cả traffic đi qua mesh lẫn traffic có thể bypass sidecar.

## 8. Gateway re-encrypt và xác minh upstream

Khi gateway mở TLS mới tới upstream, gateway phải xác minh server certificate của upstream:

- Trust đúng CA hoặc trust bundle.
- Xác minh SAN/hostname theo tên service dự kiến.
- Gửi SNI phù hợp.
- Không tắt certificate verification.
- Không cho client điều khiển upstream hostname hoặc trust store.
- Xác thực gateway với upstream bằng client certificate nếu dùng mTLS.

Ví dụ:

~~~text
External client
    | TLS: api.example.com
    v
API Gateway
    | TLS + client certificate: gateway identity
    v
order-service.internal
    | verify gateway certificate and identity
    v
Application
~~~

Gateway không nên chỉ mã hóa hop nội bộ mà bỏ qua xác minh server certificate. TLS tới một server giả mạo vẫn là TLS nhưng không bảo vệ đúng đích.

## 9. TLS termination làm thay đổi client identity như thế nào?

Nếu TLS kết thúc tại gateway, TLS session ở upstream là session mới. Application nhìn thấy peer certificate của gateway, không nhìn thấy certificate gốc của external client.

Điều này quan trọng khi backend cần biết client certificate nào đã được xác minh ở edge. Có ba lựa chọn:

1. **TLS passthrough:** application tự xác minh certificate client gốc.
2. **Terminate mTLS tại edge và forward identity assertion:** gateway xác minh client certificate rồi gửi identity đã xác minh tới application qua kênh tin cậy.
3. **Terminate mTLS tại edge và token exchange:** gateway đổi external identity thành token nội bộ có audience/scope cho service nhận.

Không giả định upstream có thể đọc certificate gốc từ TLS session mới. Không chuyển raw certificate hoặc DN qua một header rồi để application tin mà không xác thực nguồn.

## 10. Identity forwarding an toàn

Identity forwarding chuyển thông tin principal qua trust boundary. Chỉ nên thực hiện sau khi gateway đã xác minh credential/certificate.

Một assertion nội bộ nên có tối thiểu:

- iss: gateway/identity issuer đã được service tin cậy.
- sub: client/workload principal đã được ánh xạ.
- aud: đúng service nhận.
- iat, exp: thời điểm phát hành và expiry ngắn.
- jti: định danh token nếu cần kiểm soát replay.
- Claim cần thiết cho authorization, không mang toàn bộ profile.
- cnf hoặc certificate binding nếu threat model yêu cầu ràng buộc token với key.

Gateway ký assertion bằng key được quản lý. Upstream xác minh signature, issuer, audience, thời hạn, thuật toán allowlist và key rotation. Token chỉ được dùng cho service/audience đã định; không dùng một assertion toàn quyền cho mọi upstream.

Nếu dùng token exchange, token nội bộ nên có scope tối thiểu và lifetime ngắn. Không forward access token bên ngoài tới service khác nếu audience không dành cho service đó.

## 11. Forward identity bằng header: chỉ khi trust boundary được khóa

Một số hệ thống dùng header nội bộ như:

~~~http
X-Authenticated-Client: partner-42
X-Client-Certificate-SAN: spiffe://partner.example/client/42
X-Principal-Type: service
~~~

Các header này chỉ an toàn khi tất cả điều kiện sau được đáp ứng:

1. Edge xóa mọi header cùng tên do client gửi.
2. Gateway tự tạo giá trị từ certificate/token đã xác minh.
3. Gateway-to-upstream được bảo vệ bằng mTLS hoặc cơ chế service identity tương đương.
4. Upstream chỉ nhận request từ gateway identity được phép.
5. Upstream từ chối header assertion khi request tới từ nguồn khác.
6. Header schema/length/character được chuẩn hóa và có version nếu cần.
7. Header không được dùng làm bằng chứng duy nhất cho object/tenant authorization.

Nếu các service có thể gọi trực tiếp nhau, cần quy định service nào được phép tạo assertion và cách xác minh. Không tin X-User-ID, X-Role, X-Tenant-ID hoặc X-Forwarded-Client-Cert chỉ vì request đến từ private network.

## 12. X-Forwarded-Client-Cert và proxy chain

Một số proxy hỗ trợ header như X-Forwarded-Client-Cert (XFCC) để chuyển certificate information đã quan sát ở hop trước. Đây là metadata forwarding, không phải chuẩn authentication độc lập.

Nếu sử dụng:

- Cấu hình proxy nào được phép append/forward/strip XFCC.
- Edge phải xóa XFCC do external client gửi.
- Chỉ tin XFCC từ proxy identity đã xác thực.
- Giới hạn field được forward; tránh chuyển toàn bộ certificate nếu application chỉ cần SAN identity.
- Parse theo grammar của proxy, không split chuỗi tùy tiện.
- Không dùng raw subject string để authorize.
- Kiểm tra behavior khi có nhiều proxy hop và nhiều certificate.

Nếu upstream chỉ cần principal ID, một signed assertion có audience/expiry rõ thường dễ xác minh hơn việc chuyển certificate text qua header.

## 13. Phân biệt network peer, client certificate và application principal

Một request sau proxy có thể có ba danh tính:

| Danh tính | Nguồn | Ý nghĩa |
|---|---|---|
| Network peer | Socket/TLS connection | Workload hoặc proxy đang kết nối trực tiếp |
| TLS client identity | Certificate trong TLS session hiện tại | Peer sở hữu certificate đã được verifier chấp nhận |
| Application principal | Token/session/assertion đã xác minh | User, partner client hoặc service principal được API xử lý |

Khi TLS kết thúc ở gateway và gateway re-encrypt tới service, socket peer và TLS client identity ở application thường là gateway. External client principal phải được forward riêng bằng assertion đáng tin cậy nếu service cần.

Không dùng X-Forwarded-For để thay identity. IP có thể hỗ trợ audit/abuse detection nhưng không chứng minh principal. Cũng không coi certificate identity là user identity nếu certificate đại diện cho partner application hoặc workload.

## 14. Kết hợp mTLS với OAuth2/OIDC

mTLS và bearer token giải quyết các lớp khác nhau:

- mTLS xác thực peer/channel và có thể ràng buộc credential với certificate.
- OAuth2 access token thể hiện principal/client, audience và scope.
- OIDC ID token mô tả authentication event cho client; không mặc định dùng ID token làm API access token.
- Application authorization quyết định principal được gọi operation và truy cập object nào.

Ví dụ partner API có thể yêu cầu cả mTLS certificate thuộc partner A và OAuth2 token có audience orders-api, scope orders:write. Gateway kiểm tra cả hai rồi mới route request. Nếu token có certificate confirmation claim, verifier cần xác minh token thực sự được ràng buộc với certificate/key tương ứng.

Không chỉ yêu cầu “có certificate” rồi bỏ qua token scope; cũng không coi bearer token hợp lệ là lý do bỏ qua mTLS khi policy yêu cầu workload identity.

## 15. Certificate issuance, rotation và revocation

Certificate có vòng đời cần được tự động hóa:

1. Workload/client được xác minh identity trước khi cấp.
2. Private key được tạo và lưu trong nơi kiểm soát; ưu tiên key không exportable nếu nền tảng hỗ trợ.
3. CA cấp certificate với SAN/EKU đúng profile.
4. Workload sử dụng certificate trước expiry.
5. Agent/sidecar hoặc deployment controller tự gia hạn.
6. Có overlap giữa certificate cũ và mới để tránh downtime.
7. Certificate cũ bị ngừng dùng và thu hồi khi cần.

Thiết kế rotation:

- Dùng certificate lifetime phù hợp khả năng tự động renew.
- Theo dõi expiry trước nhiều ngày/giờ tùy lifetime.
- Hỗ trợ CA bundle overlap khi đổi issuer.
- Không reload certificate bằng cách restart toàn bộ service nếu có hot reload an toàn.
- Xác minh mọi replica đã nhận certificate mới.
- Xóa private key/certificate cũ khỏi mount/cache khi không còn cần.

Revocation có thể dựa trên CRL, OCSP hoặc policy/short-lived certificate tùy hạ tầng. Không giả định mọi TLS stack đều kiểm tra revocation giống nhau. Cần test cache, stapling, network failure và thời gian propagation. Với workload certificate ngắn hạn, giảm lifetime và tự động cấp lại có thể là biện pháp thực tế, nhưng không thay thế quy trình revoke khi identity bị compromise.

## 16. Lưu trữ private key và triển khai certificate

Không commit private key, keystore password hoặc CA private key vào source repository, Docker image hay Helm values công khai.

Ưu tiên:

- Secret manager, KMS/HSM hoặc workload identity để cấp certificate/key.
- Mount file với permission tối thiểu cho process cần dùng.
- Tách server key, client key và CA signing key.
- Tách dev/staging/production trust domain.
- Không mount CA private key vào application runtime.
- Không truyền private key qua log, environment dump hoặc diagnostic endpoint.
- Hạn chế quyền đọc keystore và backup.

Nếu dùng PKCS#12/JKS, bảo vệ cả file và password. Password trong environment variable vẫn có thể lộ qua process inspection, crash dump hoặc diagnostics; dùng secret injection phù hợp runtime và hạn chế quyền.

## 17. Ví dụ cấu hình mTLS trong Java/Spring Boot

Ví dụ cấu hình server yêu cầu client certificate:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/api-server.p12
    key-store-type: PKCS12
    key-store-password: <injected-keystore-password>
    trust-store: file:/run/secrets/client-ca-trust.p12
    trust-store-type: PKCS12
    trust-store-password: <injected-truststore-password>
    client-auth: need
~~~

client-auth: need yêu cầu client certificate cho kết nối tới listener này; want yêu cầu tùy chọn nhưng có thể tiếp tục khi client không gửi certificate. Cú pháp/property phụ thuộc phiên bản Spring Boot và embedded server; kiểm tra tài liệu đúng phiên bản trước khi áp dụng.

Hai giá trị password trong ví dụ là placeholder. Runtime phải inject chúng từ secret manager hoặc secret mount/property source được bảo vệ; không commit password thật vào YAML, image hoặc repository.

Nếu chỉ một nhóm endpoint yêu cầu mTLS, không nên bật need cho listener dùng chung mà không xem xét các client khác. Có thể tách listener/host, dùng gateway policy hoặc cấu hình server phù hợp để tránh vô tình bắt mọi client phải có certificate.

### 17.1 Xác minh certificate không thay thế authorization

Sau khi TLS stack xác minh client certificate, ứng dụng vẫn cần map certificate identity sang principal và kiểm tra permission:

~~~java
String clientIdentity = extractVerifiedSan(request);

PartnerPrincipal principal = partnerRegistry
    .findActiveByCertificateIdentity(clientIdentity)
    .orElseThrow(AuthenticationException::new);

authorization.require(principal, "orders:write");
orderService.createOrder(principal, command);
~~~

Đây là pseudo-code. extractVerifiedSan chỉ được lấy certificate từ TLS session mà container đã xác minh, không lấy DN/SAN từ request header. Cách truy cập peer certificate phụ thuộc servlet container, reverse proxy và cách TLS termination được triển khai.

Nếu TLS kết thúc ở gateway, application không có certificate gốc trong request socket. Khi đó dùng signed assertion hoặc token exchange theo mục identity forwarding; không gọi getPeerCertificates() rồi giả định đó là external client.

## 18. Ví dụ gateway-to-upstream mTLS

Luồng cấu hình khái niệm:

~~~text
listener:
  public_host: api.example.com
  tls_certificate: edge-server-cert
  require_client_certificate: true
  client_trust_bundle: partner-client-ca

upstream:
  service: order-service.internal
  tls: true
  sni: order-service.internal
  verify_server_certificate: true
  trusted_server_ca: internal-workload-ca
  client_certificate: gateway-workload-cert
~~~

Đây là mô hình minh họa, không phải cú pháp của một gateway cụ thể. Cần kiểm tra:

- Listener dùng đúng server certificate.
- Client CA chỉ trust partner/workload được phép.
- Gateway xác minh SAN của upstream.
- Upstream xác minh certificate của gateway.
- Gateway strip identity header từ client trước khi tạo assertion.
- Upstream không có đường truy cập trực tiếp từ nguồn không tin cậy.

Không đặt insecureSkipVerify, verify=false hoặc trust-all certificate trong production để khắc phục lỗi CA/SAN. Sửa trust bundle, hostname/SNI hoặc certificate issuance.

## 19. Health check, admin endpoint và TLS policy

Health probe có thể đi qua listener khác hoặc dùng credential riêng. Không tạo một HTTP listener plaintext có thể truy cập từ mạng rộng chỉ để load balancer kiểm tra health.

Tách:

- Liveness: process còn hoạt động.
- Readiness: instance có thể nhận traffic.
- Startup: ứng dụng đã khởi động xong.
- Admin/management: endpoint vận hành có authentication/network restriction riêng.

Nếu probe không hỗ trợ mTLS, giới hạn network source, path và response; không trả version, environment, secret hoặc topology. Không dùng health endpoint như cách bypass TLS cho API business.

## 20. Quan sát và cảnh báo TLS/mTLS

Theo dõi:

- TLS handshake success/failure theo listener và client category.
- Certificate sắp hết hạn, renew thất bại và CA trust mismatch.
- Client certificate không hợp lệ, issuer/SAN/EKU không đúng.
- Upstream TLS verification failure và SNI/hostname mismatch.
- mTLS policy downgrade hoặc plaintext upstream traffic.
- Service identity mới xuất hiện hoặc caller gọi service ngoài allowlist.
- Identity assertion signature/audience/expiry failure.
- Authentication success nhưng authorization deny theo principal/operation.

Log nên ghi certificate fingerprint hoặc identity đã chuẩn hóa khi cần điều tra, issuer, validity state, listener, peer workload và request ID. Không log private key, PEM secret, token hoặc toàn bộ certificate nếu không cần; certificate có thể chứa thông tin định danh cá nhân/đối tác.

Metric label cần cardinality giới hạn. Không dùng raw certificate serial, user ID hoặc full SAN tùy ý làm label không giới hạn; lưu chi tiết trong audit record có quyền truy cập.

## 21. Kiểm thử TLS termination và mTLS

Kiểm thử qua đúng topology triển khai, không chỉ unit test TLS config:

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Server certificate | Client gọi đúng hostname | Chain và SAN được xác minh |
| Hostname mismatch | Certificate không khớp hostname | Client từ chối |
| Expired server cert | Server cert hết hạn | Handshake bị từ chối |
| Missing client cert | Listener yêu cầu mTLS nhưng client không gửi | Handshake bị từ chối |
| Untrusted client CA | Client cert do CA ngoài trust bundle cấp | Bị từ chối |
| Wrong SAN/EKU | Certificate không thuộc client profile | Bị từ chối |
| Expired client cert | Client cert hết hạn | Bị từ chối |
| Valid cert, wrong permission | Partner hợp lệ gọi function ngoài scope | TLS thành công, application trả deny |
| Gateway-to-service mTLS | Gateway gọi upstream | Upstream xác minh đúng gateway identity |
| Upstream impersonation | Certificate upstream sai SAN/CA | Gateway từ chối kết nối |
| TLS downgrade | Client ép protocol/cipher cũ | Listener từ chối theo policy |
| Plaintext bypass | Gọi upstream qua HTTP hoặc port ngoài dự kiến | Network/policy chặn |
| Identity header spoofing | Client tự gửi X-Authenticated-Client/XFCC | Edge strip và tạo assertion mới |
| Direct upstream | Caller ngoài gateway kết nối service | Bị network/service identity policy chặn |
| Assertion tampering | Sửa sub/aud/exp/signature | Upstream từ chối |
| Audience mismatch | Token dành cho service khác | Upstream từ chối |
| Certificate rotation | Đổi cert trong overlap window | Traffic tiếp tục và cert mới được dùng |
| Revocation | Thu hồi certificate bị compromise | Kết nối mới bị chặn theo thời gian policy |
| Proxy chain | Nhiều hop thêm identity metadata | Upstream chỉ tin đúng hop đã xác thực |
| Health/admin path | Gọi probe và management listener | Không mở đường bypass API security |

### 21.1 Kiểm tra dữ liệu plaintext

Trong môi trường test, xác minh network path giữa gateway và upstream không truyền HTTP plaintext nếu policy yêu cầu re-encryption. Dùng packet capture/test proxy trong phạm vi được phép hoặc kiểm tra listener/connection metadata. Không suy luận “đã bật TLS ở edge” đồng nghĩa mọi hop đều mã hóa.

### 21.2 Kiểm tra certificate rotation

Mô phỏng:

- Cert cũ và mới cùng được trust trong overlap window.
- Một replica chưa reload cert.
- CA bundle mới chưa được rollout tới tất cả service.
- Cert cũ bị revoke khi connection pool vẫn giữ connection.
- Renewal agent mất quyền truy cập secret manager.

Xác nhận alert xuất hiện trước khi certificate hết hạn và rollback/renewal không làm hạ TLS verification.

## 22. Runbook xử lý sự cố handshake và identity

Khi TLS/mTLS lỗi:

1. Xác định client, listener, route, hop và thời điểm lỗi.
2. Kiểm tra certificate chain, SAN, EKU, validity và issuer.
3. Xác định TLS session kết thúc ở CDN, gateway, mesh hay application.
4. Kiểm tra trust bundle và certificate rotation trên tất cả replica.
5. Kiểm tra SNI/hostname verification của upstream.
6. Xác minh client certificate identity được map tới đúng principal.
7. Kiểm tra signed assertion issuer/audience/expiry/key ID nếu identity được forward.
8. Xem xét clock skew, connection pool và cache certificate/revocation.
9. Khôi phục trust/certificate đúng; không tắt verification để làm traffic chạy lại.
10. Kiểm tra log/audit để xác định request bị từ chối hay đã tới application.

Nếu private key hoặc CA signing key bị lộ, xử lý như credential compromise: cô lập issuer/workload, cấp key/certificate mới, thu hồi certificate cũ, cập nhật trust bundle, rà soát access log và rotate assertion signing key nếu có liên quan.

## 23. Các lỗi thiết kế thường gặp

1. **TLS chỉ ở edge:** hop gateway-to-service truyền plaintext qua network không được kiểm soát.
2. **Re-encrypt nhưng không verify upstream:** kết nối mã hóa tới nhầm server.
3. **Trust mọi certificate từ một CA rộng:** workload không liên quan cũng có thể gọi service.
4. **Dùng DN/CN substring làm authorization:** identity mapping không ổn định và dễ trùng.
5. **Coi mTLS là business authorization:** certificate hợp lệ được phép gọi mọi function.
6. **Forward raw identity header:** client tự giả mạo principal hoặc tenant.
7. **Tin XFCC từ mọi proxy:** metadata do client gửi được coi là certificate đã xác minh.
8. **Quên direct upstream path:** attacker bypass gateway và identity stripping.
9. **Dùng shared client certificate:** audit không xác định được workload nguồn.
10. **Tắt hostname verification:** TLS không còn xác minh đúng đích.
11. **Certificate hết hạn bất ngờ:** không có renewal automation/alert.
12. **Không có overlap khi rotate CA:** deployment làm gián đoạn toàn bộ kết nối.
13. **Bật mTLS need cho listener dùng chung:** client không có cert hợp lệ bị ảnh hưởng ngoài dự kiến.
14. **Log private key/certificate/token:** telemetry trở thành nơi rò rỉ credential.
15. **Chỉ test handshake:** không test authorization, identity forwarding và side effect.

## 24. Quy trình thiết kế TLS và identity forwarding

Với mỗi API deployment:

1. Vẽ topology client, CDN/WAF, gateway, ingress, mesh và service.
2. Đánh dấu nơi TLS kết thúc và nơi plaintext có thể xuất hiện.
3. Chọn termination, passthrough hoặc re-encryption theo trust boundary.
4. Xác định server certificate, client CA, workload identity và owner.
5. Cấu hình TLS version, cipher, SAN, SNI, ALPN và hostname verification.
6. Bật mTLS ở các hop cần xác thực workload/client.
7. Map certificate SAN/issuer tới principal ổn định; không authorize bằng DN tùy tiện.
8. Nếu TLS kết thúc trước application, thiết kế signed identity assertion hoặc token exchange.
9. Strip client-supplied identity/forwarding headers; chỉ trust assertion từ gateway đã xác thực.
10. Giới hạn audience, scope và lifetime của identity assertion.
11. Chặn direct upstream path hoặc xác thực caller tại service.
12. Quản lý private key, certificate issuance, rotation và revocation.
13. Thiết lập health/admin listener và monitoring riêng.
14. Kiểm thử handshake, upstream verification, spoofing, authorization, rotation và bypass.
15. Review topology và trust bundle khi thêm proxy, service hoặc environment.

## 25. Checklist rà soát

- [ ] Có sơ đồ mọi TLS hop và điểm termination.
- [ ] Mọi plaintext segment đều nằm trong trust boundary được phê duyệt.
- [ ] Gateway-to-upstream dùng TLS/mTLS khi threat model yêu cầu.
- [ ] Client xác minh server chain và SAN/hostname.
- [ ] Gateway xác minh upstream chain, SAN và SNI; không trust-all.
- [ ] TLS 1.0/1.1 và protocol/cipher yếu đã bị tắt.
- [ ] Client mTLS và workload mTLS được phân biệt rõ.
- [ ] Trust store chỉ chứa CA cần thiết cho listener/service.
- [ ] Client certificate được kiểm tra chain, validity, EKU, SAN và revocation policy.
- [ ] Certificate identity được map tới principal registry; không dùng DN/CN substring.
- [ ] mTLS authentication không thay thế function/object/tenant authorization.
- [ ] Identity forwarding strip header do client gửi và tạo assertion từ identity đã xác minh.
- [ ] Signed assertion có issuer, audience, expiry, signature và key rotation.
- [ ] Upstream chỉ tin gateway/service identity đã xác thực; direct access được kiểm soát.
- [ ] XFCC/Forwarded metadata chỉ được tin từ proxy chain đã xác thực.
- [ ] Private key và trust bundle được lưu, mount và phân quyền an toàn.
- [ ] Certificate có automation cho issuance, renewal, overlap và revocation.
- [ ] Health/admin endpoint không tạo đường bypass TLS/authentication.
- [ ] Có metrics/alerts cho expiry, handshake, trust mismatch và identity drift.
- [ ] Có end-to-end tests cho TLS, mTLS, spoofing, audience, rotation và plaintext bypass.

TLS termination quyết định nơi dữ liệu được giải mã; mTLS xác thực peer trên từng kết nối; identity forwarding đưa principal đã xác minh qua các trust boundary. Khi ba phần được thiết kế nhất quán, service biết chính xác workload nào đang kết nối, external client nào đã được edge xác thực và quyền nghiệp vụ nào vẫn phải kiểm tra tại application.
