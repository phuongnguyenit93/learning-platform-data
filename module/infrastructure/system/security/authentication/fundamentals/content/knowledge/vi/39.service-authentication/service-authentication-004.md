# mTLS giữa service (Mutual TLS giữa các dịch vụ)

> **Chương:** Service authentication  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Sử dụng chứng chỉ số và TLS để hai workload xác minh danh tính của nhau khi thiết lập kênh service-to-service; quản lý PKI, trust bundle, private key và vòng đời chứng chỉ; ánh xạ danh tính workload sang chính sách authorization; triển khai và vận hành mTLS an toàn trong Java, API gateway và service mesh.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mutual TLS (mTLS) và phân biệt nó với TLS thông thường, API key, bearer token và xác thực người dùng.
2. Mô tả TLS handshake có client certificate và cách hai bên xác minh certificate chain.
3. Thiết kế workload identity dựa trên SAN, EKU, trust domain và issuer; tránh dựa vào Common Name hoặc chuỗi subject không được kiểm soát.
4. Phân biệt xác thực kênh TLS với authorization cho service, API, method, resource và tenant.
5. Quản lý CA, trust store, private key, cấp phát, rotation, expiry và revocation của certificate.
6. Phân tích ranh giới tin cậy khi TLS kết thúc tại gateway, ingress hoặc sidecar proxy.
7. Triển khai mTLS cho service-to-service trong Java và service mesh; kiểm tra các cấu hình client-auth bắt buộc.
8. Nhận diện rủi ro từ certificate giả, private key bị lộ, trust bundle quá rộng, proxy header giả và kết nối tái sử dụng.
9. Kiểm thử negative cases, certificate rotation, revocation, authorization và khả năng quan sát trong môi trường phân tán.

## 1. mTLS giữa service là gì?

**Mutual TLS (mTLS)** là cách thiết lập kênh TLS trong đó cả hai đầu kết nối đều xác thực danh tính của phía bên kia bằng chứng chỉ số. Trong HTTPS thông thường, client thường xác minh server certificate để biết mình đang kết nối với server nào. Với mTLS, server cũng yêu cầu client cung cấp certificate và chứng minh quyền kiểm soát private key tương ứng.

Trong kiến trúc service-to-service, client và server thường là hai workload:

- Order Service gọi Payment Service.
- Learning API gọi Enrollment Service.
- Notification Worker gọi Email Gateway.
- API Gateway gọi các backend nội bộ.
- Một workload trong Kubernetes gọi service ở namespace khác.

mTLS giúp Payment Service xác minh request đến từ workload có danh tính được CA tin cậy cấp certificate. Đồng thời, Order Service xác minh server mà nó đang kết nối là Payment Service thuộc trust domain mong đợi.

### Vì sao cần xác thực hai chiều?

Nếu chỉ xác thực server, client biết nó đang gọi đúng endpoint nhưng server có thể chưa biết client là ai. Nếu chỉ dựa vào IP hoặc mạng nội bộ, một workload bị xâm nhập có thể giả mạo request từ vùng mạng được tin cậy.

mTLS bổ sung danh tính mật mã cho cả hai phía của kết nối. Nó giúp giảm phụ thuộc vào vị trí mạng và tạo cơ sở cho policy theo workload identity.

### Ví dụ

Order Service cần gọi endpoint xử lý thanh toán. Payment Service chỉ chấp nhận kết nối từ certificate có danh tính workload tương ứng với Order Service trong môi trường production. Một pod khác trong cùng cluster, dù truy cập được network route, không thể hoàn tất client authentication nếu không có certificate và private key hợp lệ.

Điều này chỉ xác thực danh tính workload theo PKI và policy đã cấu hình. Payment Service vẫn phải kiểm tra Order Service có được phép gọi thao tác capture payment cho đơn hàng cụ thể hay không.

## 2. Phân biệt TLS, mTLS và các cơ chế xác thực khác

| Cơ chế | Bên được xác thực | Bằng chứng chính | Phạm vi |
| --- | --- | --- | --- |
| TLS server authentication | Client xác minh server. | Server certificate và proof of private key. | Bảo vệ kết nối tới server. |
| **mTLS** | Client và server xác minh lẫn nhau. | Certificate chain và proof of private key ở cả hai phía. | Danh tính hai workload trên một kênh TLS. |
| API key | Server xác minh secret do client gửi. | Shared secret/token. | Thường gắn với client hoặc integration. |
| Bearer access token | Resource server xác minh token. | Token được issuer phát hành. | Quyền truy cập API theo audience/scope/claim. |
| OAuth client authentication | Authorization server xác minh OAuth client. | Client secret, private_key_jwt hoặc mTLS tùy phương thức. | Xác thực client tại token endpoint. |
| User authentication | Ứng dụng/IdP xác minh người dùng. | Password, passkey, MFA, certificate hoặc phương thức khác. | Danh tính con người. |

mTLS không thay thế mọi cơ chế trên. Một API có thể dùng mTLS để xác thực workload và access token để biểu diễn quyền được cấp. Ví dụ, service chứng minh nó là Order Service bằng client certificate, đồng thời trình access token có audience Payment API và scope phù hợp.

### mTLS không tự tạo quyền nghiệp vụ

Certificate hợp lệ chỉ cho biết peer chứng minh được private key tương ứng với certificate do trust chain được chấp nhận cấp. Nó không tự cho biết service được phép đọc mọi dữ liệu, gọi mọi endpoint hoặc thao tác trên mọi tenant.

Luôn tách:

1. **Transport authentication:** peer nào đang thiết lập kết nối?
2. **Application authentication/context:** request hoặc token đại diện cho actor nào?
3. **Authorization:** actor đó được làm gì trên resource nào, trong tenant nào?

## 3. Certificate và PKI trong mTLS

mTLS dựa trên Public Key Infrastructure (PKI). Một certificate liên kết public key với một danh tính hoặc tập thuộc tính được CA xác nhận.

### Thành phần cơ bản

- **Private key:** bí mật được workload dùng để ký bằng chứng trong TLS handshake.
- **Public key:** phần công khai tương ứng, được nhúng trong certificate.
- **Leaf certificate:** certificate cấp cho workload/client hoặc server.
- **Intermediate CA:** CA trung gian ký certificate leaf hoặc CA cấp thấp hơn.
- **Root CA / trust anchor:** điểm tin cậy gốc được cấu hình trong trust store.
- **Certificate chain:** chuỗi chữ ký dẫn từ leaf certificate về trust anchor được chấp nhận.
- **Trust store:** tập CA hoặc trust bundle mà workload dùng để xác minh certificate peer.
- **Key store:** nơi giữ private key và certificate identity của chính workload.

### Chuỗi tin cậy

~~~mermaid
flowchart TD
    R["Root CA / Trust Anchor"] --> I["Intermediate CA"]
    I --> C["Workload Leaf Certificate"]
    C --> W["Service chứng minh quyền giữ private key"]
    T["Trust Store của peer"] --> V["Xác minh chain, thời hạn và policy"]
    W --> V
    V --> A{"Danh tính được chấp nhận?"}
    A -->|"Có"| K["Hoàn tất xác thực TLS"]
    A -->|"Không"| X["Từ chối handshake"]
~~~

Certificate không đáng tin chỉ vì nó tự khai một SAN đẹp hoặc có chữ ký bất kỳ. Peer phải xác minh chain tới trust anchor đúng, thời hạn, key usage, extended key usage, thuật toán và các ràng buộc khác theo policy.

### Certificate cần thể hiện đúng mục đích

Certificate dùng cho client authentication thường cần Extended Key Usage phù hợp, ví dụ TLS Web Client Authentication. Server certificate cần mục đích server authentication. Cần kiểm tra Key Usage, Basic Constraints, Name Constraints và các extension liên quan theo profile PKI.

Không dùng một certificate bất kỳ có chain hợp lệ cho mọi vai trò. Trust anchor có thể cấp nhiều loại certificate; policy phải kiểm tra certificate được phát hành cho đúng mục đích.

## 4. Workload identity: SAN, URI và trust domain

Trong service-to-service, điều quan trọng là ánh xạ certificate sang danh tính workload ổn định.

Các định danh có thể xuất hiện trong Subject Alternative Name (SAN):

- DNS SAN: tên service hoặc endpoint theo naming policy.
- URI SAN: định danh workload theo một namespace, ví dụ SPIFFE ID.
- IP SAN: địa chỉ IP nếu profile yêu cầu; thường không nên dùng IP động làm identity duy nhất.
- OtherName hoặc SAN type riêng theo profile PKI được thống nhất.

### Ưu tiên SAN theo policy

Common Name (CN) từng được dùng trong một số mô hình cũ, nhưng không nên dựa vào CN như danh tính chính. Với workload identity, nên định nghĩa SAN rõ ràng và kiểm tra chính xác theo trust policy.

Ví dụ URI SAN theo phong cách SPIFFE:

~~~text
spiffe://example.edu/ns/production/sa/order-service
~~~

Định danh này có thể biểu diễn trust domain, namespace và service account. Cấu trúc cụ thể cần theo profile đã chọn; không tự parse chuỗi theo giả định tùy tiện.

### Mapping danh tính

| Certificate identity | Principal nội bộ | Mục đích |
| --- | --- | --- |
| URI SAN thuộc trust domain production và service order | workload:order-service | Gọi API nội bộ đã được cấp quyền. |
| URI SAN thuộc namespace monitoring | workload:metrics-agent | Thu thập metrics được allowlist. |
| DNS SAN của gateway đã đăng ký | workload:api-gateway | Gọi backend qua ingress được quản lý. |

Không dùng substring matching kiểu “SAN có chứa order” hoặc wildcard rộng cho production. Cần so sánh theo identity format đã chuẩn hóa, issuer/trust domain, tenant và environment.

### Danh tính workload khác danh tính người dùng

mTLS certificate thường xác thực process, pod, VM hoặc service account. Nó không chứng minh người dùng cuối đã đăng nhập. Nếu Order Service thay mặt học viên gọi Payment API, hệ thống cần mô hình hóa cả workload caller và user/actor delegation nếu nghiệp vụ yêu cầu.

## 5. TLS 1.3 handshake với client certificate

mTLS bổ sung bước server yêu cầu client certificate trong TLS handshake. Ở mức khái niệm, TLS 1.3 full handshake diễn ra như sau:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client workload
    participant S as Server workload
    C->>S: ClientHello
    S-->>C: ServerHello
    S-->>C: EncryptedExtensions
    S-->>C: CertificateRequest
    S-->>C: Server Certificate
    S-->>C: CertificateVerify
    S-->>C: Finished
    C->>S: Client Certificate
    C->>S: CertificateVerify
    C->>S: Finished
    Note over C,S: Hai bên xác minh chain và proof of private key
    C->>S: Application data được mã hóa
~~~

Trình tự chi tiết còn phụ thuộc handshake options, cipher suite, certificate selection và việc client certificate có được yêu cầu hay không. Với TLS 1.3, client authentication trong handshake được khởi tạo bằng CertificateRequest; client gửi Certificate và CertificateVerify nếu có certificate phù hợp.

### Server kiểm tra client certificate

Server thường cần xác minh:

1. Certificate chain dẫn tới trust anchor được cấu hình.
2. Certificate còn trong thời hạn hiệu lực.
3. SAN khớp với workload identity được chấp nhận.
4. EKU/Key Usage phù hợp với client authentication.
5. Signature algorithm và key size đáp ứng policy.
6. Certificate không bị revoke hoặc trạng thái còn được chấp nhận theo mô hình PKI.
7. Identity được phép kết nối tới service này.
8. Proof of private key trong handshake hợp lệ.

### Client kiểm tra server certificate

Client cũng phải xác minh server certificate:

- Chain tới CA server được tin cậy.
- Hostname/SAN khớp endpoint dự kiến.
- Certificate còn hiệu lực và đúng purpose.
- Server chứng minh quyền giữ private key.
- Trust policy không cho phép CA hoặc hostname ngoài phạm vi.

Không tắt hostname verification chỉ để làm cho mTLS “hoạt động”. mTLS yêu cầu xác minh cả hai phía.

## 6. Xác thực kết nối không đồng nghĩa xác thực từng request

TLS xác thực peer khi thiết lập kết nối. Nhiều request HTTP/2 hoặc gRPC có thể chạy trên cùng một kết nối TLS. Vì vậy, danh tính certificate thường gắn với connection/peer, không tự động đại diện cho mọi user hoặc actor ở tầng ứng dụng.

Cần phân biệt:

- **Connection identity:** certificate peer đã xác minh trên TLS connection.
- **Request identity:** principal mà ứng dụng gán cho request sau khi kiểm tra context.
- **Delegated identity:** người dùng hoặc service khác mà caller đang đại diện.
- **Resource authorization:** quyết định cho endpoint, action, record và tenant.

Nếu gateway tái sử dụng connection hoặc multiplex nhiều request, không được gắn một user identity từ request trước vào request sau. Request-scoped identity phải được xây dựng và xóa đúng vòng đời.

### Connection pooling

HTTP client có thể tái sử dụng connection. Nếu pool được chia sẻ giữa các workload identity hoặc certificate khác nhau, có nguy cơ request đi qua connection đã xác thực bằng identity không đúng dự kiến.

- Tách pool theo TLS identity, trust profile và endpoint khi cần.
- Không đổi certificate của một client đang hoạt động mà không quản lý connection cũ.
- Đóng hoặc drain connection sau rotation/revocation theo policy.
- Kiểm tra connection reuse trong test và telemetry.

## 7. Trust boundary khi TLS kết thúc tại gateway hoặc proxy

Trong kiến trúc thực tế, TLS có thể kết thúc tại load balancer, ingress, API gateway hoặc sidecar proxy. Khi đó, backend không nhất thiết nhìn thấy client certificate handshake ban đầu.

~~~mermaid
flowchart LR
    A["Order Service"] -->|"mTLS"| G["API Gateway / Ingress"]
    G -->|"mTLS riêng"| P["Payment Service"]
    G --> I["Identity mapping / policy"]
    I --> P
    X["Workload không tin cậy"] -. "Không được tự khai identity header" .-> P
~~~

### Hai đoạn TLS khác nhau

Nếu Order Service mTLS tới Gateway, rồi Gateway mTLS tới Payment Service, Payment Service trực tiếp xác thực Gateway ở hop thứ hai. Nó không tự động xác thực Order Service ở hop đầu.

Gateway có thể chuyển tiếp identity đã xác minh qua header hoặc metadata, nhưng backend chỉ được tin thông tin đó nếu:

- Gateway là proxy được tin cậy và được xác thực ở hop backend.
- Header do gateway ghi đè, không giữ giá trị do client gửi.
- Kênh gateway-backend được bảo vệ.
- Có quy ước rõ về issuer, identity, audience và request context.
- Backend không thể truy cập trực tiếp từ nguồn bỏ qua gateway nếu policy yêu cầu gateway mediation.
- Identity propagation có integrity protection hoặc cơ chế token/assertion phù hợp nếu ranh giới yêu cầu.

Không tin header như X-Client-Cert hoặc X-Forwarded-Client-Cert từ mọi request. Proxy phải xóa header đầu vào cùng tên và ghi lại giá trị đã xác minh. Nếu backend có thể bị gọi trực tiếp, attacker có thể giả header để mạo danh workload.

## 8. Authentication và authorization cho service

Sau khi TLS handshake thành công, ứng dụng cần ánh xạ certificate identity sang principal và kiểm tra quyền.

Ví dụ:

- workload:order-service được gọi Payment API.
- Payment API chỉ cho phép principal này gọi endpoint tạo authorization intent.
- Endpoint capture chỉ cho phép principal đã có scope hoặc policy bổ sung.
- Request phải gắn đúng order ID và tenant.
- Nếu service thay mặt user, token delegation phải xác định actor và subject rõ ràng.

### Ma trận policy minh họa

| Principal | API/action | Quyền |
| --- | --- | --- |
| workload:order-service | POST /payment-intents | Allow nếu tenant/order hợp lệ. |
| workload:order-service | POST /refunds | Deny nếu chưa được cấp policy riêng. |
| workload:metrics-agent | GET /metrics | Allow trong network/policy monitoring. |
| workload:reporting-service | GET /reports | Allow theo scope và tenant đã cấp. |
| workload:unknown | Bất kỳ API nội bộ | Deny. |

### Nguyên tắc authorization

- Deny by default.
- Quyền tối thiểu theo service, action, resource và tenant.
- Tránh cấp role “internal” quá rộng.
- Kiểm tra trạng thái workload identity và certificate.
- Không suy ra quyền chỉ từ việc certificate được CA ký.
- Audit quyết định allow/deny mà không ghi private key hoặc secret.
- Có thể kết hợp mTLS với OAuth access token hoặc policy engine.

## 9. Cấp phát certificate và quản lý CA

Certificate lifecycle bắt đầu trước khi service chạy. Một quy trình tốt phải biết ai được yêu cầu certificate, identity nào được cấp và khóa được tạo/bảo vệ ở đâu.

### Quy trình cấp phát

1. Workload hoặc agent được xác thực với provisioning authority.
2. Hệ thống xác định workload identity từ scheduler/orchestrator hoặc inventory tin cậy.
3. Private key được tạo trong workload, secure agent, HSM hoặc secret provider phù hợp.
4. CSR được tạo và gửi tới CA.
5. CA kiểm tra requester, identity, namespace, environment và policy.
6. CA phát leaf certificate với SAN, EKU, validity và algorithm phù hợp.
7. Certificate được phân phối tới workload cùng trust bundle cần thiết.
8. Workload nạp certificate và thực hiện mTLS.
9. Hệ thống theo dõi expiry, rotation và revoke.

### Root CA và intermediate CA

- Root CA nên được bảo vệ nghiêm ngặt, thường offline hoặc trong HSM.
- Intermediate CA giới hạn phạm vi phát hành theo environment, tenant hoặc loại workload.
- Không dùng cùng một CA quá rộng cho mọi môi trường nếu điều đó làm tăng blast radius.
- Trust bundle phải được phân phối có xác thực và có version.
- Thay CA cần có giai đoạn overlap để chuyển trust an toàn.

### Private key

- Không commit private key vào source control hoặc image.
- Không dùng cùng một private key cho nhiều workload độc lập.
- Hạn chế quyền đọc file/key và tránh log secret.
- Ưu tiên key generation tại nơi sử dụng và key protection phù hợp.
- Có quy trình rotate/revoke khi pod, VM, node hoặc secret store bị compromise.
- Tránh chia sẻ key dài hạn giữa các môi trường dev/test/prod.

## 10. Rotation, expiry và revocation

Certificate có thời hạn. Nếu certificate hết hạn, peer có thể từ chối handshake. Nếu certificate bị lộ, attacker có thể dùng nó tới khi bị revoke hoặc hết hạn, tùy cơ chế kiểm tra.

### Rotation

Một quy trình rotation thường gồm:

1. Cấp certificate mới và private key mới.
2. Cập nhật workload hoặc agent để nạp certificate mới.
3. Xác minh handshake bằng identity mới.
4. Chuyển traffic và drain connection cũ.
5. Thu hồi hoặc để certificate cũ hết hạn theo policy.
6. Xác minh mọi replica đã hoàn tất rotation.

Không thay file certificate mà bỏ qua connection pool hoặc TLS context đã cache. Một số runtime chỉ nạp certificate lúc khởi tạo SSLContext; cần reload hoặc restart/drain có kiểm soát.

### Short-lived certificate

Certificate ngắn hạn giảm thời gian tồn tại của credential bị lộ và giảm phụ thuộc vào CRL/OCSP trong một số kiến trúc. Tuy nhiên, short-lived certificate đòi hỏi CA và workload agent sẵn sàng, đồng hồ chính xác và cơ chế rotation đáng tin cậy.

### Revocation

Các cơ chế có thể gồm:

- CRL.
- OCSP hoặc cơ chế kiểm tra trạng thái tương đương.
- Trust bundle update hoặc denylist theo serial/fingerprint.
- Thu hồi identity trong workload identity provider.
- Xóa/revoke credential tại service mesh control plane.

Không phải mọi TLS stack đều kiểm tra revocation mặc định hoặc đồng nhất. Cần kiểm tra runtime thực tế, cache và hành vi khi OCSP/CRL không khả dụng. Với certificate ngắn hạn, expiry nhanh có thể là một phần của chiến lược containment, nhưng không thay thế khả năng revoke khẩn cấp khi cần.

## 11. SPIFFE/SPIRE và workload identity

Trong hệ thống cloud-native, SPIFFE cung cấp định dạng định danh workload và SPIRE là một triển khai phổ biến để cấp phát, xác minh workload identity.

Một SPIFFE ID có dạng URI, ví dụ:

~~~text
spiffe://prod.example.edu/ns/payments/sa/order-service
~~~

SPIRE Agent có thể xác minh workload dựa trên node attestation và workload attestation theo cấu hình, sau đó cấp SVID (SPIFFE Verifiable Identity Document). X.509-SVID là certificate có SPIFFE ID trong URI SAN; workload dùng nó cho mTLS.

### Lợi ích

- Danh tính workload không phụ thuộc IP động hoặc tên pod tạm thời.
- Certificate có thể ngắn hạn và được tự động rotate.
- Trust domain và bundle giúp xác minh workload giữa các service.
- Có thể áp policy theo namespace, service account và môi trường.
- Giảm việc phân phối shared secret thủ công.

### Điều cần kiểm soát

- Attestation source phải đáng tin và được bảo vệ.
- Trust domain không được chấp nhận tùy tiện.
- Workload selector phải chính xác, tránh selector quá rộng.
- SVID phải có TTL và rotation phù hợp.
- Bundle federation phải được xác minh và quản lý version.
- Không coi mọi workload trong cùng trust domain đều có cùng quyền.
- Có kế hoạch khi SPIRE server/agent hoặc control plane không khả dụng.

SPIFFE/SPIRE là một cách quản lý workload identity, không phải điều kiện bắt buộc để triển khai mTLS. Có thể dùng PKI nội bộ khác nếu identity lifecycle và trust policy được thiết kế rõ.

## 12. mTLS trong service mesh

Service mesh thường tự động hóa cấp phát certificate, thiết lập mTLS giữa sidecar/ambient proxy và áp policy giữa workload.

Một kiến trúc điển hình:

- Control plane cấp identity và trust bundle.
- Data plane proxy thực hiện TLS handshake.
- Proxy xác minh certificate peer.
- Policy engine hoặc mesh authorization policy quyết định workload nào được gọi service nào.
- Telemetry ghi nhận identity và kết quả kết nối.

### Ưu điểm

- Giảm việc mỗi ứng dụng tự viết TLS plumbing.
- Tự động rotation certificate.
- Policy thống nhất cho nhiều service.
- Có telemetry về workload identity và connection.
- Có thể bật strict mTLS theo namespace/service.

### Giới hạn

- Nếu có plaintext port hoặc bypass path, mTLS không bao phủ toàn bộ traffic.
- Proxy bị compromise có thể làm lộ hoặc giả mạo identity trong phạm vi nó kiểm soát.
- Policy quá rộng vẫn cho phép lateral movement.
- Control plane/trust bundle là thành phần có quyền lớn.
- Ứng dụng cần hiểu identity propagation khi TLS terminate ở sidecar.
- Debugging certificate, trust bundle và authorization policy có thể phức tạp.

Không coi việc bật “mesh mTLS” là hoàn tất zero trust. Cần xác minh mọi đường traffic, policy authorization, ingress/egress, service account và cách bypass được ngăn chặn.

## 13. Triển khai mTLS trong Java

Java JSSE hỗ trợ TLS và client certificate qua KeyStore, TrustStore và SSLContext. Cấu hình server và client cần tách rõ identity của chính mình với CA dùng để xác minh peer.

### 13.1 Server yêu cầu client certificate

Ví dụ cấu hình Spring Boot dạng minh họa:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:tls/server-identity.p12
    key-store-type: PKCS12
    key-store-password: SERVER_KEYSTORE_PASSWORD
    trust-store: classpath:tls/client-ca-trust.p12
    trust-store-type: PKCS12
    trust-store-password: CLIENT_TRUSTSTORE_PASSWORD
    client-auth: need
~~~

Ý nghĩa:

- Key store chứa server certificate và private key mà ứng dụng dùng để chứng minh danh tính server.
- Trust store chứa CA/trust anchor được chấp nhận để xác minh client certificate.
- client-auth: need yêu cầu client cung cấp certificate hợp lệ; cấu hình want có thể cho phép client không có certificate tùy container/runtime, không phù hợp nếu endpoint bắt buộc mTLS.
- Mật khẩu store phải đến từ secret manager/environment injection và không commit vào repository.

Tên property và khả năng reload có thể khác theo phiên bản framework/container. Cần kiểm tra cấu hình của runtime đang dùng.

### 13.2 Java HttpClient với SSLContext

Ví dụ khái niệm nạp client identity và trust store:

~~~java
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.net.http.HttpClient;
import java.security.KeyStore;
import java.time.Duration;

public final class MtlsClientFactory {

    private MtlsClientFactory() {
    }

    public static HttpClient create(
            KeyStore clientKeyStore,
            char[] keyPassword,
            KeyStore trustStore
    ) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
        );
        kmf.init(clientKeyStore, keyPassword);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);

        return HttpClient.newBuilder()
                .sslContext(sslContext)
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }
}
~~~

Đây là khung minh họa. Production cần quản lý secret, chọn certificate đúng alias khi có nhiều identity, hostname verification mặc định, timeout, connection pool, rotation/reload và xử lý lỗi TLS. Không cài TrustManager chấp nhận mọi certificate và không tắt endpoint identification.

### 13.3 Lấy principal từ TLS peer

Ở server, framework/container có thể đưa certificate peer vào request context. Ứng dụng cần:

- Xác minh TLS client authentication đã thành công.
- Lấy certificate chain từ TLS session/request attribute do container bảo vệ.
- Kiểm tra SAN và ánh xạ sang principal nội bộ.
- Không đọc certificate identity từ header tùy ý.
- Tách principal của workload khỏi user principal và delegated actor.
- Áp authorization theo endpoint/action/resource.

Nếu TLS kết thúc tại reverse proxy, backend chỉ được dùng forwarded certificate identity khi proxy được xác thực, header bị ghi đè và đường bypass đã bị chặn.

## 14. Kết hợp mTLS với OAuth access token

mTLS và OAuth có thể bổ sung nhau:

- mTLS xác thực workload đang kết nối.
- OAuth access token mô tả quyền được cấp cho client hoặc actor.
- Resource server kiểm tra cả hai theo policy.

### Certificate-bound access token

OAuth Mutual-TLS Client Authentication and Certificate-Bound Access Tokens (RFC 8705) định nghĩa cách client xác thực bằng certificate tại authorization server và ràng buộc access token với certificate đó.

Token có thể chứa confirmation claim tham chiếu certificate thumbprint, thường là x5t#S256 trong cnf. Resource server so sánh certificate của TLS connection với thumbprint được ràng buộc trong token.

Điều này làm token bị đánh cắp khó sử dụng từ một client không có private key tương ứng. Tuy nhiên:

- Token và private key bị lộ cùng lúc vẫn nguy hiểm.
- TLS termination cần chuyển certificate binding một cách tin cậy.
- Resource server phải thực sự kiểm tra binding.
- Token vẫn cần issuer, audience, expiry, scope và authorization validation.
- Rotation certificate cần phối hợp token lifecycle.

### Không nhầm client authentication với user delegation

Nếu service gọi API thay mặt người dùng, cần token/delegation model thể hiện actor và subject. Client certificate chỉ chứng minh workload client, không tự chứng minh người dùng đã cho phép hành động.

## 15. Cross-trust-domain và nhiều tổ chức

Một workload có thể gọi service thuộc tổ chức khác. Khi đó, hai bên cần thống nhất cách tin cậy certificate và ánh xạ identity.

Các lựa chọn:

- Cùng trust anchor hoặc PKI federation đã được phê duyệt.
- Trust bundle federation theo trust domain.
- Gateway/API partner có danh tính và certificate riêng.
- OAuth client registration kết hợp mTLS và audience/scope.
- Policy mapping rõ ràng giữa external principal và internal role.

### Nguyên tắc

- Không tin mọi certificate từ một public CA cho mọi API nội bộ.
- Trust bundle phải giới hạn theo mục đích và môi trường.
- External SAN/URI không tự mang ý nghĩa quyền nội bộ.
- Mapping partner identity cần explicit allowlist và owner.
- Có quy trình thu hồi trust khi partner bị compromise hoặc hợp đồng kết thúc.
- Theo dõi certificate expiry và thay đổi CA trước khi ảnh hưởng production.

## 16. Các lỗi cấu hình và mối đe dọa thường gặp

| Rủi ro | Cách xảy ra | Biện pháp |
| --- | --- | --- |
| **Client authentication optional** | Server cho phép client không gửi certificate dù endpoint cần mTLS. | Dùng chế độ bắt buộc và test handshake thiếu certificate. |
| **Trust-all certificate** | Client chấp nhận mọi server certificate. | Dùng trust store đúng và hostname verification. |
| **CA quá rộng** | Mọi certificate từ CA lớn được coi là workload nội bộ. | Trust anchor chuyên biệt, SAN policy và issuer scoping. |
| **CN/string matching** | Principal được gán bằng substring hoặc CN dễ giả định. | Dùng SAN có cấu trúc, exact mapping và trust domain. |
| **Private key leakage** | Key nằm trong image, source control hoặc log. | Secret manager/HSM, quyền tối thiểu, rotate/revoke. |
| **Long-lived certificate** | Credential bị lộ có thể dùng lâu. | Short-lived cert, rotation và revoke workflow. |
| **Stale trust bundle** | CA cũ vẫn được chấp nhận sau khi bị loại bỏ. | Versioned bundle, rollout và kiểm tra propagation. |
| **Proxy header spoofing** | Backend tin X-Client-Cert do caller gửi. | Proxy ghi đè header, xác thực hop và chặn bypass. |
| **TLS termination gap** | Gateway xác thực client nhưng backend tưởng đã xác thực trực tiếp client. | Mô hình hóa từng hop, identity propagation có integrity. |
| **No authorization** | Bất kỳ workload có cert hợp lệ gọi mọi API. | Deny by default, service/action/resource policy. |
| **Connection pool identity mix** | Request dùng connection được xác thực bằng certificate khác. | Pool isolation và test connection reuse. |
| **Revocation not enforced** | Runtime không kiểm tra CRL/OCSP hoặc cache quá lâu. | Kiểm chứng runtime, short-lived cert và emergency denylist. |
| **Session resumption assumption** | Hệ thống giả định certificate được kiểm tra mới ở mọi lần kết nối resumed. | Kiểm tra semantics TLS/session ticket và giới hạn lifetime. |
| **mTLS bypass path** | Plaintext port hoặc network route bỏ qua proxy/mesh. | Inventory traffic path, network policy và strict mode. |
| **Overbroad service identity** | Một service account dùng chung cho nhiều workload. | Identity riêng theo workload/environment và least privilege. |

## 17. Giám sát và vận hành mTLS

mTLS cần được vận hành như một hệ thống identity lifecycle, không chỉ là bật TLS một lần.

### Telemetry nên có

- TLS handshake success/failure và alert reason đã chuẩn hóa.
- Certificate issuer, SAN principal, serial hoặc fingerprint theo chính sách dữ liệu.
- Thời điểm hết hạn và số ngày còn lại.
- Trust bundle version.
- Client-auth mode và TLS protocol/cipher được thương lượng.
- Workload/service identity ở mỗi hop.
- Authorization decision và policy version.
- Rotation/revocation event và propagation lag.

Không ghi private key, keystore password hoặc secret. Certificate public data vẫn có thể tiết lộ topology và service naming, nên giới hạn quyền truy cập log/metrics.

### Alert hữu ích

- Certificate sắp hết hạn nhưng chưa được rotate.
- Certificate bất ngờ xuất hiện từ workload/namespace không phù hợp.
- Nhiều handshake fail do unknown CA, expired cert hoặc SAN mismatch.
- Trust bundle thay đổi ngoài lịch.
- Một identity gọi endpoint ngoài baseline.
- Tăng đột biến kết nối từ certificate bị nghi compromise.
- mTLS bị downgrade hoặc có traffic đi qua plaintext path.

### Runbook sự cố private key bị lộ

1. Xác định certificate, workload, trust domain và phạm vi ảnh hưởng.
2. Chặn hoặc revoke identity/key theo cơ chế CA/control plane.
3. Phát hành key và certificate mới từ nguồn tin cậy.
4. Cập nhật trust/revocation state và đảm bảo propagation tới peer.
5. Drain connection và session resumption state theo khả năng.
6. Kiểm tra request đã thực hiện trong khoảng thời gian nghi compromise.
7. Rotate token/secret liên quan nếu có khả năng bị lộ cùng.
8. Ghi audit, thông báo service owner và theo dõi handshake sau containment.

Không chỉ xóa file certificate trên pod rồi coi sự cố đã xử lý; private key có thể đã bị sao chép và dùng ở nơi khác.

## 18. Ví dụ thực tế: Learning Platform

Learning Platform có các workload Order API, Enrollment Service, Payment Service và Notification Worker chạy trong cluster.

### Kết nối bình thường

1. Order API nhận request từ người dùng đã được xác thực.
2. Order API gọi Enrollment Service qua mTLS.
3. Enrollment Service xác minh certificate chain, URI SAN và workload identity của Order API.
4. Authorization policy cho phép Order API kiểm tra enrollment.
5. Order API gọi Payment Service qua một kết nối mTLS riêng.
6. Payment Service xác minh identity của Order API và kiểm tra access token/audience/scope nếu API yêu cầu.
7. Notification Worker chỉ được gọi endpoint gửi thông báo; không được gọi payment capture.

### Certificate hết hạn

Một replica của Order API không rotate certificate đúng hạn. Handshake tới Enrollment Service thất bại do certificate hết hạn. Hệ thống phát alert, loại replica khỏi traffic, cấp certificate mới và xác minh lại kết nối. Không được tắt certificate validation để khôi phục dịch vụ tạm thời.

### Workload bị compromise

Nếu private key của Notification Worker bị lộ, security team thu hồi identity đó, revoke certificate, ngăn workload tiếp tục kết nối và cấp identity mới sau khi tái tạo môi trường sạch. Các service khác vẫn chỉ cho phép principal đã được allowlist, nên certificate của Notification Worker không tự cấp quyền gọi Payment API.

### Gateway termination

Nếu API Gateway kết thúc mTLS từ client rồi mở mTLS mới tới Order API, Order API trực tiếp xác thực Gateway. Nếu cần biết client gốc, Gateway phải truyền identity đã xác minh bằng cơ chế tin cậy; Order API không được tin header từ Internet hoặc từ caller không xác thực.

## 19. Kiểm thử mTLS giữa service

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Client certificate hợp lệ | Kết nối bằng certificate đúng CA, SAN và EKU. | Handshake thành công. |
| Thiếu client certificate | Kết nối tới endpoint bắt buộc mTLS mà không gửi certificate. | Handshake bị từ chối. |
| Certificate từ CA lạ | Dùng certificate không thuộc trust bundle. | Handshake bị từ chối. |
| Certificate hết hạn | Dùng leaf certificate quá hạn. | Handshake bị từ chối. |
| SAN không khớp | Dùng certificate hợp lệ nhưng identity không được phép. | Authentication hoặc authorization từ chối theo policy. |
| EKU sai | Dùng certificate chỉ dành cho server auth làm client. | Bị từ chối theo certificate purpose validation. |
| Hostname server sai | Client gọi endpoint có SAN không khớp. | Client từ chối server certificate. |
| Private key không khớp | Ghép certificate với key khác. | Không chứng minh được possession; handshake thất bại. |
| Certificate chain thiếu intermediate | Bỏ intermediate cần thiết. | Kết quả theo chain-building policy; không âm thầm trust leaf. |
| Certificate rotation | Cấp cert mới và chuyển traffic. | Kết nối mới dùng identity mới; cert cũ được retire an toàn. |
| Revoked certificate | Đánh dấu serial/fingerprint bị revoke theo cơ chế hỗ trợ. | Peer từ chối theo revocation policy và SLA. |
| Trust bundle rotation | Thêm CA mới, overlap rồi loại CA cũ. | Không gián đoạn ngoài kế hoạch; CA cũ bị ngừng tin đúng lúc. |
| CN spoofing | Dùng CN quen thuộc nhưng SAN không đúng. | Không cấp principal dựa vào CN. |
| Proxy header spoofing | Gửi X-Client-Cert/X-Forwarded-Client-Cert giả. | Proxy ghi đè; backend không tin giá trị do client cung cấp. |
| Direct backend bypass | Gọi backend bỏ qua gateway/mesh. | Network/policy chặn nếu kiến trúc yêu cầu đi qua proxy. |
| Authorization mismatch | Cert hợp lệ nhưng gọi action không được cấp quyền. | TLS có thể thành công; API trả deny. |
| Cross-tenant identity | Dùng workload identity tenant A gọi tài nguyên tenant B. | Authorization từ chối. |
| Connection pooling | Dùng pool trong nhiều identity context. | Không có connection identity leakage. |
| Session resumption | Thử TLS resumption sau khi certificate bị revoke hoặc trust thay đổi. | Hành vi đúng theo policy ticket lifetime/invalidation. |
| Service mesh strict mode | Gọi service từ workload không có mTLS. | Traffic bị từ chối. |
| Plaintext bypass | Thử port hoặc route phụ không qua mTLS. | Không có đường bypass ngoài policy. |
| Private key compromise drill | Thu hồi key test và cấp key mới. | Kết nối cũ bị chặn trong SLA; key mới hoạt động. |
| Control plane outage | Làm CA/identity agent unavailable trong lab. | Workload xử lý theo policy availability; không tự hạ xuống plaintext. |

## 20. Checklist triển khai

- [ ] Đã xác định workload identity riêng cho service, environment và tenant cần thiết.
- [ ] Certificate có SAN theo profile rõ; không dựa vào CN hoặc substring matching.
- [ ] EKU/Key Usage phù hợp client/server authentication.
- [ ] Client và server đều xác minh chain, validity, purpose và peer identity.
- [ ] Hostname verification của server được bật.
- [ ] Server yêu cầu client certificate bắt buộc ở endpoint cần mTLS.
- [ ] Trust bundle giới hạn theo trust domain, CA và environment.
- [ ] Private key được bảo vệ, không commit vào source/image/log và không chia sẻ không cần thiết.
- [ ] Có CA issuance workflow, short-lived certificate và rotation tự động.
- [ ] Có revocation/emergency containment và hiểu giới hạn CRL/OCSP của runtime.
- [ ] Connection pool, TLS context và session resumption được xử lý khi rotate/revoke.
- [ ] Authorization tách khỏi certificate authentication và áp dụng least privilege.
- [ ] Gateway/sidecar termination được mô hình hóa theo từng hop.
- [ ] Forwarded identity chỉ được tin từ proxy đã xác thực và header bị ghi đè.
- [ ] Không có plaintext hoặc bypass path ngoài policy.
- [ ] OAuth/token delegation được dùng khi cần biểu diễn quyền hoặc user actor.
- [ ] Có telemetry về handshake, identity, expiry, trust bundle và authorization.
- [ ] Có runbook khi CA, private key, certificate hoặc trust bundle bị compromise.
- [ ] Có test certificate thiếu/sai/hết hạn, SAN/EKU, rotation, revocation, proxy và multi-region.

## 21. Tự kiểm tra

**Câu 1.** mTLS khác TLS thông thường ở điểm nào?

**Đáp án:** TLS thông thường thường xác thực server với client; mTLS yêu cầu cả client và server chứng minh danh tính bằng certificate và private key tương ứng.

**Câu 2.** Certificate hợp lệ có tự cấp quyền gọi mọi API nội bộ không?

**Đáp án:** Không. Certificate xác thực peer theo PKI. Authorization vẫn phải kiểm tra principal, endpoint, action, resource, tenant và policy.

**Câu 3.** Vì sao nên dùng SAN thay vì dựa vào CN?

**Đáp án:** SAN cung cấp định danh có kiểu và được dùng cho service identity/hostname theo profile. CN không nên là nguồn identity chính và có thể dẫn tới mapping mơ hồ.

**Câu 4.** Trust store và key store khác nhau thế nào?

**Đáp án:** Key store giữ private key/certificate identity của chính workload; trust store chứa CA/trust anchor dùng để xác minh peer.

**Câu 5.** Nếu TLS kết thúc tại gateway, backend đã xác thực client gốc chưa?

**Đáp án:** Không nhất thiết. Backend trực tiếp xác thực gateway trên hop thứ hai. Client gốc chỉ được tin nếu gateway truyền identity đã xác minh qua một cơ chế integrity-protected và backend chặn đường bypass.

**Câu 6.** Vì sao mTLS không thay thế OAuth access token trong mọi trường hợp?

**Đáp án:** mTLS chứng minh workload trên kết nối; access token có thể biểu diễn audience, scope, delegation và quyền được cấp. Hai cơ chế giải quyết các lớp khác nhau.

**Câu 7.** Short-lived certificate giúp giảm rủi ro gì?

**Đáp án:** Giảm khoảng thời gian certificate bị lộ có thể được dùng và giảm phụ thuộc vào revocation propagation. Nó vẫn cần issuance/rotation ổn định và containment khẩn cấp.

**Câu 8.** Có nên chấp nhận mọi certificate do public CA ký cho API nội bộ không?

**Đáp án:** Không. Trust anchor phải giới hạn theo mục đích, environment và identity policy; certificate cần đúng SAN/EKU và được ánh xạ rõ ràng.

**Câu 9.** Service mesh bật mTLS có đồng nghĩa đã hoàn thành zero trust không?

**Đáp án:** Không. Cần authorization theo workload/action/resource, bảo vệ control plane, kiểm tra mọi traffic path, ngăn bypass và quản lý identity lifecycle.

**Câu 10.** Khi private key của workload bị lộ, chỉ xóa pod có đủ không?

**Đáp án:** Không. Key có thể đã bị sao chép. Cần revoke identity/certificate, phát hành key mới, drain connection, kiểm tra token/session và điều tra hoạt động trong thời gian bị ảnh hưởng.

## Ghi nhớ

**mTLS giữa service** xác thực hai chiều bằng certificate và proof of private key trên kênh TLS. Nó cung cấp workload identity có thể kiểm chứng qua trust chain, SAN, EKU và trust domain. Nhưng mTLS chỉ xác thực peer của kết nối; quyền gọi API vẫn cần authorization riêng theo service, action, resource và tenant.

Một triển khai an toàn cần PKI và private-key lifecycle rõ ràng, certificate ngắn hạn/rotation, revocation, trust bundle có giới hạn, hostname verification, xử lý đúng khi TLS kết thúc tại gateway/sidecar và bảo vệ identity propagation. Trong Java hoặc service mesh, phải kiểm tra client-auth bắt buộc, connection pooling, session resumption và mọi đường bypass. **Danh tính workload chỉ đáng tin khi nguồn cấp, certificate, private key, trust policy và quyền nghiệp vụ đều được kiểm soát xuyên suốt vòng đời.**
