# Service discovery: tìm dịch vụ an toàn trong distributed system

> **Chương:** Authentication trong distributed system  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào service discovery: cách một service tìm endpoint của service khác trong môi trường động, cách giữ danh tính dịch vụ ổn định khi địa chỉ thay đổi, và cách ngăn discovery trở thành đường giả mạo, chuyển hướng hoặc vượt qua ranh giới tin cậy.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích service discovery và phân biệt logical service identity với network endpoint.
2. Mô tả các mô hình discovery qua DNS, registry, orchestrator và service mesh.
3. Xác định control plane, data plane, registry, resolver, workload và relying service trong trust model.
4. Thiết kế xác thực service-to-service độc lập với vị trí IP/hostname được discovery trả về.
5. Dùng TLS/mTLS, certificate identity, workload identity và token audience đúng cách.
6. Bảo vệ đăng ký, cập nhật, health check, cache và deregistration của service.
7. Nhận diện DNS spoofing, poisoning, rebinding, registry tampering, endpoint substitution và SSRF.
8. Thiết kế authorization sau khi xác thực service, gồm tenant, scope, action và resource.
9. Triển khai client/service discovery trong Java/Spring và xây dựng ma trận kiểm thử.

## 2. Service discovery là gì?

**Service discovery** là cơ chế giúp một thành phần tìm được địa chỉ mạng và thông tin kết nối của một dịch vụ khác trong hệ thống phân tán.

Trong môi trường hiện đại, instance có thể được tạo, thay thế, scale, di chuyển hoặc kết thúc liên tục. Client không nên phải biết trước IP của từng instance. Thay vào đó, client dùng một tên logic như:

- identity-service
- payment-api
- inventory-service
- orders.internal
- spiffe://example.org/prod/ns/payments/sa/payment-api

Discovery resolver ánh xạ tên logic hoặc service identifier sang endpoint có thể kết nối, ví dụ hostname, IP, port, protocol, zone và metadata.

Điểm quan trọng: discovery trả lời **kết nối tới đâu**. Nó không tự chứng minh **bên đang trả lời là ai**, và cũng không quyết định **bên đó được phép làm gì**.

Ví dụ, service orders tìm thấy một endpoint có IP 10.20.4.18 cho payment-api. Địa chỉ đó chỉ là thông tin định tuyến. Trước khi gửi dữ liệu nhạy cảm, orders vẫn phải xác minh endpoint có danh tính payment-api thuộc trust domain mong đợi, certificate hợp lệ, và request có được authorization cho operation cụ thể hay không.

## 3. Ba khái niệm cần tách biệt

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Service discovery** | Endpoint nào hiện có thể nhận kết nối? | payment-api -> 10.20.4.18:8443 |
| **Service authentication** | Peer đang kết nối có đúng là payment-api không? | mTLS certificate/SPIFFE ID hợp lệ |
| **Service authorization** | payment-api hoặc caller được phép thực hiện hành động nào? | orders-service được gọi payment:authorize cho tenant đã xác định |

Không được suy ra danh tính từ IP, hostname, DNS record hoặc việc endpoint xuất hiện trong registry. Không được suy ra quyền từ việc TLS handshake thành công. Mỗi lớp có mục tiêu và policy riêng.

~~~mermaid
flowchart TD
    A["Logical service name / identity"] --> B["Service discovery"]
    B --> C["Candidate endpoint: address + port"]
    C --> D["Secure channel: TLS / mTLS"]
    D --> E{"Peer identity valid?"}
    E -->|"No"| X["Reject connection"]
    E -->|"Yes"| F["Build authenticated workload principal"]
    F --> G["Authorization: action + resource + tenant + scope"]
    G --> H{"Policy allows?"}
    H -->|"No"| Y["Deny request"]
    H -->|"Yes"| I["Process request"]
~~~

## 4. Logical service identity và endpoint

Một dịch vụ có thể có nhiều instance và endpoint thay đổi theo thời gian. Danh tính logic cần ổn định hơn địa chỉ mạng.

Ví dụ:

~~~text
Logical identity:
  service = payment-api
  trust_domain = corp.example
  environment = production

Discovered endpoints:
  10.20.4.18:8443
  10.20.5.21:8443
  payment-7f8c.internal:8443
~~~

Các endpoint có thể thay đổi sau deploy hoặc autoscaling, nhưng danh tính workload mà client chấp nhận vẫn phải tuân theo policy. Client không nên đổi expected identity chỉ vì DNS trả về một IP mới.

Một identity tốt thường có namespace và authority rõ:

- Trust domain hoặc issuer.
- Environment/cluster.
- Namespace/team.
- Service account hoặc workload name.
- Mục đích hoặc audience nếu cần phân biệt.

Tên service chung chung như api hoặc worker có thể bị trùng giữa dev, staging và production. Namespace giúp tránh nhầm lẫn và giảm nguy cơ một service ở môi trường thấp giả mạo service production.

## 5. Các mô hình service discovery

### 5.1. DNS-based discovery

Client tra cứu tên DNS để lấy A/AAAA, SRV hoặc record phù hợp. DNS đơn giản, phổ biến và có thể tích hợp với load balancer, container platform hoặc service catalog.

Ưu điểm:

- Dựa trên hạ tầng tiêu chuẩn.
- Tương thích với nhiều runtime và client.
- Có cache và TTL để giảm tải resolver.
- Hỗ trợ tên logic thay cho IP cố định.

Giới hạn:

- DNS trả lời định tuyến, không tự xác minh service identity.
- Cache có thể giữ endpoint cũ sau khi instance bị thay thế.
- Resolver hoặc DNS zone bị compromise có thể chuyển client tới endpoint giả.
- Search suffix và hostname normalization có thể tạo nhầm tên.
- DNSSEC bảo vệ tính xác thực/toàn vẹn của dữ liệu DNS trong phạm vi chain of trust, nhưng không thay mTLS hoặc authorization ở application.

### 5.2. Service registry

Service instance đăng ký với registry; client hoặc load balancer truy vấn danh sách instance.

Thông tin có thể gồm:

- Service name và instance ID.
- Endpoint, port và protocol.
- Zone/region/cluster.
- Health/readiness status.
- Version hoặc deployment metadata.
- Workload identity reference.
- Thời gian lease/heartbeat.

Registry là một thành phần control plane nhạy cảm. Nếu attacker có thể đăng ký instance giả, sửa endpoint hoặc thay metadata, client có thể bị định tuyến tới dịch vụ độc hại.

### 5.3. Orchestrator-based discovery

Container orchestrator có thể cung cấp service name, virtual IP, internal DNS hoặc endpoint slices. Platform quản lý vòng đời instance và cập nhật endpoint khi pod/container thay đổi.

Không nên mặc định mọi workload trong cùng cluster đều đáng tin. Namespace, service account, network policy, admission policy và workload identity vẫn cần được cấu hình.

### 5.4. Service mesh

Service mesh có thể cung cấp control plane để phân phối identity/certificate và data plane proxy để thực hiện mTLS, routing, retries và telemetry.

Mesh giúp chuẩn hóa một số control, nhưng không tự bảo đảm application authorization đúng. Nếu policy mesh chỉ xác minh source/destination service mà bỏ qua tenant, user delegation hoặc business action, service vẫn có thể truy cập dữ liệu quá rộng.

### So sánh nhanh

| Mô hình | Nguồn endpoint | Thành phần cần bảo vệ |
|---|---|---|
| DNS | DNS records/resolver | DNS zone, resolver, cache, trust anchors |
| Registry | Service catalog | Registration API, registry database, ACL, lease |
| Orchestrator | Cluster control plane | API server, service account, namespace, endpoint controller |
| Service mesh | Mesh control plane/data plane | CA, workload identity, proxy config, policy distribution |

Một hệ thống có thể kết hợp nhiều mô hình, ví dụ DNS đưa tới gateway, gateway dùng registry để chọn instance, mesh proxy xác thực peer bằng mTLS.

## 6. Trust model: control plane và data plane

**Control plane** quản lý trạng thái mong muốn và metadata: service registration, endpoint, identity issuance, certificate distribution, route và policy.

**Data plane** xử lý kết nối và request thực tế: DNS resolution, load balancing, TLS handshake, token validation và API call.

~~~mermaid
flowchart LR
    subgraph CP["Control plane"]
        REG["Service registry"]
        ID["Workload identity / CA"]
        POL["Routing and authorization policy"]
    end
    subgraph DP["Data plane"]
        C["Caller workload"]
        R["Resolver / load balancer"]
        P["Peer workload"]
        M["mTLS / sidecar proxy"]
    end
    REG --> R
    ID --> M
    POL --> M
    C --> R
    R --> M
    M <--> P
~~~

Các nguyên tắc:

1. Chỉ workload hoặc controller được xác thực mới được đăng ký/cập nhật service record.
2. Quyền ghi registry phải tách theo namespace/service ownership.
3. CA chỉ cấp identity cho workload đã được xác minh.
4. Data plane xác minh peer identity dù endpoint đến từ registry đáng tin.
5. Policy được phân phối có integrity, version và rollback control.
6. Compromise control plane được xem là sự cố nghiêm trọng vì có thể ảnh hưởng nhiều workload.

Không dùng quyền quản trị cluster hoặc registry làm credential runtime cho mọi application.

## 7. Đăng ký và deregistration an toàn

Một flow registration nên kiểm tra:

- Workload requester có identity hợp lệ không?
- Workload có quyền đăng ký service name/namespace đó không?
- Endpoint có thuộc network/cluster/zone được phép không?
- Port và protocol có nằm trong profile cho phép không?
- Metadata có bị dùng để nâng quyền hoặc thay trust domain không?
- Registration có lease/expiry và heartbeat không?
- Khi workload kết thúc, record có được deregister hoặc tự hết hạn không?

Không cho requester tự đăng ký service identity của một workload khác. Ví dụ, service inventory không được tự đăng ký endpoint dưới tên payment-api.

### Lease và heartbeat

Registry có thể dùng lease có thời hạn. Instance phải gia hạn định kỳ; nếu heartbeat hết hạn, endpoint bị loại khỏi danh sách discovery.

Lease không thay health check. Một process có thể vẫn heartbeat nhưng application không sẵn sàng xử lý request. Cần phân biệt:

- Liveness: process còn sống.
- Readiness: instance có thể nhận traffic.
- Health: các dependency và chức năng cần thiết đang ở trạng thái chấp nhận được.

Không để health check không xác thực trở thành API quản trị có thể thay đổi state.

## 8. Service identity với TLS và mTLS

TLS cung cấp kênh được mã hóa và xác minh server identity theo certificate validation. Trong mTLS, client và server đều trình certificate và chứng minh possession của private key.

Đối với service-to-service:

- Client xác minh certificate chain tới trust anchor được cấu hình.
- Client kiểm tra SAN/identity mong đợi, không chỉ certificate có chữ ký CA.
- Server xác minh client certificate và ánh xạ sang workload principal.
- Hai bên kiểm tra validity, key usage/EKU và policy.
- Private key được bảo vệ trong keystore/HSM/secret provider phù hợp.
- Certificate được rotate trước expiry và revoke khi compromise.

### Hostname verification và workload identity

TLS hostname verification thường kiểm tra tên host mà client kết nối có khớp SAN của certificate không. Với workload identity, hệ thống có thể cần kiểm tra một URI SAN hoặc identity identifier theo profile, thay vì chỉ hostname.

Ví dụ:

~~~text
Expected peer identity:
  spiffe://corp.example/prod/ns/payments/sa/payment-api

Discovered endpoint:
  10.20.4.18:8443

Connection acceptance:
  trusted certificate chain
  AND expected workload identity matches SAN
  AND certificate is currently valid
  AND key usage permits client/server authentication
~~~

IP address hoặc DNS record chỉ giúp tìm endpoint. Identity được kiểm tra qua certificate và trust policy.

## 9. Workload identity và SPIFFE/SPIRE

Một workload identity framework có thể cấp identity cho service/process mà không cần hard-code long-lived secret trong application.

SPIFFE định nghĩa workload identity dưới dạng SPIFFE ID, thường biểu diễn bằng URI. SPIRE có thể attestation workload theo node/runtime attributes và cấp SVID, chẳng hạn X.509-SVID hoặc JWT-SVID.

Ví dụ identity:

~~~text
spiffe://corp.example/prod/ns/orders/sa/orders-api
spiffe://corp.example/prod/ns/payments/sa/payment-api
~~~

Một X.509-SVID có thể được dùng cho mTLS; verifier kiểm tra trust bundle và SPIFFE ID theo policy. JWT-SVID là token mang workload identity, cần kiểm tra issuer, audience, expiry và signature theo profile.

Lợi ích:

- Identity gắn với workload thay vì IP.
- Credential có lifetime giới hạn.
- Rotation có thể tự động.
- Trust domain và namespace hỗ trợ phân tách môi trường.
- Có thể cấp quyền theo workload identity cụ thể.

Giới hạn:

- Node/runtime attestation phải đáng tin.
- Workload bị compromise có thể sử dụng credential trong thời gian còn hiệu lực.
- Trust bundle và CA distribution là thành phần trọng yếu.
- SPIFFE ID hợp lệ không tự động cấp quyền nghiệp vụ trên mọi resource.

## 10. DNS security và endpoint substitution

Nếu client tin endpoint discovery mà không xác minh peer identity, attacker có thể tìm cách thay đổi câu trả lời hoặc đăng ký endpoint giả.

Các rủi ro:

- DNS spoofing hoặc cache poisoning.
- DNS zone/registrar compromise.
- Resolver bị cấu hình sai hoặc bị kiểm soát.
- Search suffix khiến short name được phân giải sang domain ngoài dự kiến.
- DNS rebinding làm hostname trỏ tới địa chỉ khác theo thời gian.
- Endpoint record cũ còn trong cache sau khi instance bị thu hồi.
- Service registry bị ghi bởi workload không có quyền.

Kiểm soát:

- Dùng DNS resolver/zone được quản lý và hạn chế quyền ghi.
- Dùng FQDN/namespace rõ thay vì short name mơ hồ.
- Cấu hình TTL và cache phù hợp với vòng đời instance.
- Kiểm tra peer certificate identity sau khi kết nối.
- Không tắt hostname verification khi dùng TLS.
- Không cho discovery metadata ghi đè trust anchor hoặc expected identity.
- Theo dõi thay đổi bất thường của record, owner và endpoint.
- Dùng DNSSEC khi phù hợp, nhưng vẫn giữ TLS/mTLS identity validation.

### DNS rebinding và SSRF

Service discovery có thể bị lợi dụng khi một API nhận hostname/URL do user cung cấp rồi tự phân giải và kết nối. Attacker có thể làm hostname trỏ tới IP nội bộ hoặc thay đổi câu trả lời giữa lúc kiểm tra và kết nối.

Biện pháp:

- Không cho user tùy ý chỉ định upstream service URL nếu không cần.
- Dùng allowlist logical service ID thay cho URL tự do.
- Chặn loopback, link-local, private metadata và địa chỉ nội bộ không được phép theo policy egress.
- Kiểm tra mọi địa chỉ sau resolution và sau redirect.
- Ghim expected service identity ở TLS layer.
- Giới hạn redirect, scheme, port và protocol.
- Thực hiện kiểm tra ở network egress policy như defense-in-depth.

Một lần resolve rồi kiểm tra IP chưa đủ nếu HTTP client resolve lại khi kết nối hoặc hostname có thể đổi giữa các bước. Kiểm soát cần gắn với endpoint thực tế được sử dụng và peer identity.

## 11. Registry poisoning và service impersonation

Registry poisoning xảy ra khi attacker thêm hoặc sửa service record để caller chọn endpoint do attacker kiểm soát.

Các con đường:

- Credential registry bị lộ.
- Workload có quyền đăng ký tên service tùy ý.
- API registration thiếu authorization theo namespace.
- Metadata hoặc health status có thể bị sửa bởi caller không tin cậy.
- Controller/agent có quyền quá rộng.
- Secret bootstrap của node bị compromise.

Kiểm soát:

- Xác thực workload trước khi registration.
- Authorize quyền register theo service identity và namespace.
- Dùng owner-bound registration và lease.
- Audit create/update/delete record.
- Tách quyền read/write/admin.
- Không cho registry metadata tự quyết định certificate identity hoặc trust anchor.
- Cảnh báo khi endpoint/service owner thay đổi ngoài deployment workflow.

Ngay cả khi registry bị poisoning, mTLS peer identity validation có thể chặn endpoint giả nếu attacker không có credential hợp lệ cho service đích. Đây là lý do discovery và authentication phải độc lập.

## 12. Service discovery và OAuth token audience

Một service client có thể lấy access token trước khi gọi service đích. Token cần được phát hành cho resource/audience đúng theo authorization server contract.

Không nên:

- Dùng một token audience chung cho toàn bộ microservices nếu mỗi service cần trust boundary riêng.
- Chấp nhận token chỉ vì chữ ký hợp lệ mà không kiểm tra issuer/audience.
- Lấy audience từ endpoint DNS tùy ý do discovery trả về.
- Forward user access token tới mọi downstream service không có lý do.

Thiết kế:

1. Client xác định logical target service đã được cấu hình.
2. Authorization server cấp token cho audience/resource tương ứng.
3. Discovery chọn endpoint instance thuộc logical target.
4. TLS/mTLS xác minh endpoint có identity tương ứng logical target.
5. Resource server xác minh token issuer, audience, expiry, scope và client/subject.
6. Authorization kiểm tra action, tenant và resource.

Endpoint có thể đổi nhưng audience/service identity vẫn giữ ổn định theo contract. Không lấy IP hoặc hostname động làm identity duy nhất của token.

## 13. Service mesh: ích lợi và giới hạn

Service mesh thường triển khai sidecar hoặc node proxy để xử lý:

- Service discovery/load balancing.
- mTLS và certificate rotation.
- Retry, timeout và circuit breaking.
- Telemetry và trace.
- Authorization policy ở mức service/workload.

Mesh có thể giảm việc mỗi ứng dụng tự triển khai TLS và credential rotation. Tuy nhiên:

- Application vẫn cần xác thực end-user token khi request đại diện user.
- Mesh identity thường xác định workload peer, không phải end-user.
- Policy mesh cần phối hợp với policy nghiệp vụ.
- Sidecar/proxy compromise có thể ảnh hưởng nhiều traffic.
- Traffic đi vòng ngoài mesh có thể bỏ qua policy nếu network không khóa.
- Egress traffic cần policy riêng, không mặc định được trust.

Không nhầm mTLS giữa hai sidecar với authorization của user cuối. Có thể cần cả workload identity và end-user identity trong cùng một request.

## 14. Identity propagation qua nhiều service

Trong microservices, một request có thể đi qua API gateway, orders, payment và ledger. Mỗi hop cần xác định danh tính nào đang được truyền.

Có hai loại identity thường gặp:

- **Workload identity:** service nào đang kết nối tới service tiếp theo.
- **End-user/delegated identity:** người dùng nào là chủ thể được đại diện và quyền nào được ủy quyền.

Không forward raw user token tới mọi downstream service một cách mặc định. Có thể dùng token exchange/on-behalf-of theo authorization server, với audience và scope giới hạn cho downstream.

Một context có thể bao gồm:

~~~text
transport_peer:
  workload_id = spiffe://corp.example/prod/ns/orders/sa/orders-api

delegated_subject:
  issuer = https://id.corp.example
  subject = user-104
  audience = payment-api
  scope = payment:authorize

request:
  tenant = tenant-9
  operation = authorize-payment
  correlation_id = internal-correlation-id
~~~

Service nhận phải xác minh từng phần theo nguồn phát hành. Không tin header X-User-Id hoặc X-Role từ kết nối không xác thực. Nếu gateway tạo header nội bộ, cần xóa header do client gửi trước đó và chỉ tin header qua channel/identity đã được bảo vệ.

## 15. Health check, readiness và trust

Health check giúp load balancer/registry biết instance có nên nhận traffic hay không. Nhưng health không phải identity proof.

Phân biệt:

- Liveness: process có còn chạy?
- Readiness: instance đã sẵn sàng nhận request?
- Dependency health: database, queue hoặc dependency có đáp ứng?
- Security posture: certificate còn hạn, workload identity hợp lệ, policy/configuration đúng?

Không nên để endpoint health công khai tiết lộ chi tiết version, dependency, topology hoặc secret. Health endpoint không nên có quyền thay đổi registration hoặc cấp credential.

Một instance healthy vẫn có thể là workload giả nếu registry bị thao túng. Một certificate hợp lệ cũng không có nghĩa instance đang healthy. Cần kết hợp discovery state, health và cryptographic identity.

## 16. Cache, TTL và stale endpoint

Discovery thường dùng cache để giảm latency và tải registry/DNS. Nhưng cache tạo khoảng thời gian endpoint cũ còn được sử dụng sau khi instance bị thu hồi.

Các câu hỏi:

- TTL bao lâu?
- Resolver có refresh khi connection fail không?
- Endpoint bị revoke có thể bị dùng thêm bao lâu?
- Client connection pool giữ connection tới instance đã deregister không?
- Certificate hết hạn hoặc identity bị revoke có được phát hiện trên connection đang mở không?
- Có cần đóng connection khi policy hoặc trust bundle thay đổi không?

Kiểm soát:

- TTL phù hợp với tốc độ thay đổi và SLA.
- Có bounded stale window.
- Evict cache khi có invalidation event.
- Connection pool có max lifetime và health validation.
- TLS session resumption/connection reuse phải phù hợp với certificate rotation và revocation policy.
- Không dùng stale endpoint nếu identity validation thất bại.
- Theo dõi thời gian từ revoke tới khi mọi caller ngừng sử dụng endpoint.

DNS TTL bằng 0 hoặc TTL rất ngắn không tự bảo đảm thu hồi tức thời; resolver, OS, runtime và connection pool có thể có cache riêng.

## 17. Load balancing và retry không được làm mất identity

Client có thể chọn một endpoint từ danh sách, hoặc dùng load balancer/gateway. Khi retry sang instance khác:

- Expected service identity vẫn phải là cùng logical service.
- mTLS phải xác minh từng peer.
- Token audience và scope vẫn phải đúng target service.
- Retry không được biến POST không idempotent thành side effect trùng.
- Không retry tự động khi lỗi chứng minh identity/certificate không hợp lệ.
- Không gửi credential tới endpoint ngoài allowlist.

Nếu một endpoint có certificate sai, client nên từ chối endpoint đó và tạo security telemetry. Không tự hạ TLS verification để retry endpoint khác.

## 18. Service discovery và authorization

Sau khi kết nối và xác thực peer thành công, service vẫn cần authorization:

- Caller workload có được gọi operation này không?
- Caller có quyền trên tenant nào?
- Token có đúng audience và scope không?
- Request có end-user delegation hợp lệ không?
- Resource có thuộc tenant/owner của subject không?
- Có yêu cầu step-up hoặc transaction approval không?

Ví dụ:

~~~text
Authenticated workload:
  orders-api

Delegated user:
  user-104

Requested action:
  payment:authorize

Resource:
  account-A104 / tenant-9

Policy:
  orders-api may call payment-api
  AND token audience is payment-api
  AND token scope includes payment:authorize
  AND user-104 may initiate payment for account-A104
  AND transaction limits and state are valid

Decision:
  ALLOW only when every required condition passes
~~~

mTLS chỉ chứng minh peer sở hữu private key tương ứng certificate identity. Nó không tự cấp quyền chuyển tiền, đọc dữ liệu khách hàng hoặc quản trị service.

## 19. Java/Spring: gọi service qua logical identity

Ví dụ dưới đây minh họa client gọi logical service name thay vì hard-code IP. Cấu hình TLS/mTLS và hostname/peer identity verification cần được thiết lập trong HTTP client/mesh theo trust policy của hệ thống.

~~~java
@Service
class PaymentClient {
    private final WebClient webClient;

    PaymentClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://payment-api.internal")
            .build();
    }

    Mono<PaymentResult> authorize(
            AuthorizePaymentRequest request,
            String accessToken) {
        return webClient.post()
            .uri("/v1/payments/authorize")
            .headers(headers -> {
                headers.setBearerAuth(accessToken);
            })
            .bodyValue(request)
            .retrieve()
            .bodyToMono(PaymentResult.class);
    }
}
~~~

Tên base URL là logical DNS/service name trong ví dụ. Production cần:

- Resolver chỉ sử dụng DNS/registry được phê duyệt.
- TLS certificate chain được xác minh.
- Hostname hoặc workload identity/SAN được kiểm tra đúng profile.
- Nếu dùng mTLS, client certificate được cấp cho đúng workload.
- Access token có audience payment-api và scope tối thiểu.
- Không log bearer token.
- Timeout/retry có giới hạn; POST chỉ retry với idempotency contract.

Không tắt certificate validation hoặc hostname verification để “sửa” lỗi service discovery.

### Ánh xạ peer identity sang principal

~~~java
record WorkloadPrincipal(
    String trustDomain,
    String serviceIdentity,
    String environment
) {}

WorkloadPrincipal authenticatePeer(PeerCertificate certificate) {
    certificate.verifyTrustedChain();
    certificate.verifyValidity();
    certificate.requireClientOrServerAuthUsage();

    String serviceId = certificate.requireExpectedUriSan();
    WorkloadIdentity identity = identityRegistry.requireActive(serviceId);

    return new WorkloadPrincipal(
        identity.trustDomain(),
        identity.serviceId(),
        identity.environment()
    );
}
~~~

Đây là pseudocode minh họa. PeerCertificate phải được tạo từ TLS stack đã xác minh chain và proof-of-possession; không parse SAN từ một header do caller tự gửi. Registry lookup cần authoritative source, trạng thái active và policy namespace.

## 20. Java/Spring: giới hạn outbound destination

Khi service cần gọi upstream động, ưu tiên chọn từ danh sách logical service đã cấu hình. Không nhận URL tùy ý từ user rồi gọi trực tiếp.

~~~java
enum InternalService {
    PAYMENT_API,
    INVENTORY_API
}

URI resolveAllowedService(InternalService service) {
    return switch (service) {
        case PAYMENT_API ->
            URI.create("https://payment-api.internal");
        case INVENTORY_API ->
            URI.create("https://inventory-api.internal");
    };
}
~~~

Đây chỉ là allowlist tối giản. Hệ thống thực tế có thể dùng registry/client-side load balancer, nhưng logical service ID phải được map qua resolver đáng tin và giữ expected peer identity cố định. Không cho input bên ngoài tạo tùy ý service enum, hostname, port hoặc scheme.

## 21. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi IP là service identity | Endpoint giả có thể được tin | Xác minh certificate/workload identity |
| Coi DNS record là bằng chứng danh tính | DNS tampering dẫn tới impersonation | TLS/mTLS và expected SAN validation |
| Tắt hostname verification | Kết nối tới peer sai identity | Sửa certificate/SAN/trust config |
| Mọi workload được đăng ký mọi service name | Registry poisoning | Owner-bound registration và namespace ACL |
| Registry metadata tự quyết định trust anchor | Attacker có thể đổi trust policy | Tách registry data khỏi CA/trust configuration |
| Dùng chung identity giữa dev và production | Lateral movement qua môi trường | Trust domain/namespace riêng |
| Chỉ mTLS mà không authorization | Service hợp lệ gọi action ngoài quyền | Policy theo workload, user, resource và action |
| Forward mọi user token downstream | Token exposure và audience confusion | Token exchange/audience-specific token |
| Tin header X-User-Id từ client | Impersonation | Chỉ tin context được xác thực qua trusted proxy |
| Health check được coi là identity proof | Instance giả có thể vượt kiểm tra | Tách health khỏi cryptographic authentication |
| Cache endpoint vô hạn | Tiếp tục dùng instance đã revoke | TTL, invalidation và connection lifetime |
| Retry mọi lỗi TLS | Gửi credential tới endpoint không tin cậy | Fail closed với identity validation error |
| URL do user nhập được resolver nội bộ gọi | SSRF tới internal metadata/service | Logical service allowlist và egress controls |
| Service mesh được coi là thay mọi authorization | Business-level access bị bỏ qua | Enforce AuthZ ở application/domain |
| Short DNS name không có namespace | Resolve nhầm service ở domain khác | FQDN và canonical service identity |

## 22. Ma trận kiểm thử service discovery và authentication

| Kiểm thử | Kết quả mong đợi |
|---|---|
| DNS trả endpoint đúng và certificate identity đúng | Kết nối được phép |
| DNS trả IP khác nhưng certificate đúng logical identity | Có thể chấp nhận nếu endpoint thuộc policy/discovery hợp lệ |
| DNS trả endpoint giả, certificate SAN sai | Từ chối kết nối |
| Certificate chain không trusted | Từ chối |
| Certificate hết hạn hoặc bị revoke theo policy | Từ chối |
| Certificate hợp lệ nhưng EKU không phù hợp | Từ chối cho mục đích đó |
| Workload đăng ký service name không thuộc namespace | Registry từ chối |
| Registration lease hết hạn | Endpoint bị loại khỏi discovery |
| Instance unhealthy/not-ready | Không nhận traffic theo policy |
| Registry record bị thay endpoint ngoài deployment workflow | Audit/alert; peer identity vẫn được xác minh |
| Service ở staging giả danh production service | Trust domain/identity check từ chối |
| Token audience không khớp target service | Resource server từ chối |
| mTLS thành công nhưng token thiếu scope | Authorization từ chối |
| mTLS thành công nhưng user không có quyền resource | Authorization từ chối |
| User gửi X-User-Id giả | Header bị bỏ qua/ghi đè bằng trusted context |
| DNS rebinding tới loopback/private metadata | Outbound policy chặn |
| Redirect trỏ tới hostname ngoài allowlist | Client từ chối |
| Resolver trả stale endpoint đã revoke | Identity/policy check chặn; cache được invalidated |
| Connection pool giữ connection quá lâu sau revoke | Rotation/revocation policy đóng hoặc giới hạn connection |
| Service registry unavailable | Hành vi fallback có giới hạn; không dùng endpoint không xác minh |
| Workload certificate rotation | Kết nối mới dùng cert mới; cert cũ hết hiệu lực theo overlap policy |
| Trust bundle thay đổi | Client nhận policy mới có integrity/version |
| Service mesh bypass path | Network policy chặn hoặc audit phát hiện |
| Discovery metadata chứa URL/port độc hại | Validation/allowlist từ chối |
| Caller retry POST sau endpoint failover | Cùng idempotency key; không tạo side effect trùng |

Kiểm thử cả positive và negative cases ở DNS/registry, TLS handshake, token validation, authorization và application side effect. Một kết nối thành công chưa chứng minh toàn bộ request được phép.

## 23. Tình huống phân tích

### Tình huống A: DNS trỏ tới endpoint giả

Orders tra cứu payment-api và nhận IP của một workload không thuộc payment team. Client gửi request chứa dữ liệu thanh toán vì chỉ kiểm tra DNS resolve thành công.

**Phân tích:** discovery chỉ trả endpoint. Client phải xác minh TLS chain và expected workload identity. Nếu SAN không khớp payment-api trong trust domain production, kết nối bị từ chối.

### Tình huống B: workload đăng ký nhầm service name

Một pod thuộc namespace thử nghiệm có quyền ghi registry toàn cluster và đăng ký dưới tên identity-service.

**Phân tích:** lỗi ở control plane authorization. Giới hạn registration theo workload identity, namespace và service ownership; audit mọi thay đổi record.

### Tình huống C: mTLS hợp lệ nhưng request không được phép

Orders-api có certificate hợp lệ và kết nối được payment-api. Tuy nhiên token không có scope payment:authorize.

**Phân tích:** mTLS xác thực workload peer, không cấp quyền nghiệp vụ. Payment-api phải kiểm tra token audience, scope, delegated user và transaction policy.

### Tình huống D: stale endpoint sau rollout

Instance cũ bị terminate nhưng một client vẫn giữ địa chỉ trong cache/connection pool. Instance mới đã được triển khai với certificate mới.

**Phân tích:** thiết kế TTL, lease, invalidation, max connection lifetime và certificate rotation. Client không được bỏ identity validation để kết nối lại.

### Tình huống E: URL do người dùng cung cấp

Một endpoint preview nhận URL từ user rồi dùng internal resolver để tải nội dung. Attacker gửi hostname có thể phân giải tới metadata service.

**Phân tích:** đây là SSRF kết hợp service discovery. Dùng logical destination allowlist, kiểm tra scheme/port/address sau resolution, chặn private/metadata ranges theo policy và xác minh peer identity.

## 24. Quy trình thiết kế và vận hành

Trước khi đưa service discovery vào production, hãy xác định:

1. Logical service identity và namespace/trust domain là gì?
2. Discovery source là DNS, registry, orchestrator hay mesh?
3. Ai có quyền register, update, deregister và đọc service record?
4. Registration có owner, lease, heartbeat và audit không?
5. Endpoint thay đổi thì expected peer identity được giữ ổn định ra sao?
6. TLS/mTLS certificate được cấp từ authority nào và SAN được kiểm tra thế nào?
7. Trust bundle, certificate rotation và revocation propagation hoạt động ra sao?
8. Workload identity có tách dev/staging/production không?
9. OAuth token có audience và scope đúng service không?
10. End-user/delegated identity được truyền qua downstream bằng cơ chế nào?
11. Authorization kiểm tra workload, subject, tenant, action và resource ở đâu?
12. DNS/registry cache, TTL, connection pool và stale endpoint được quản lý thế nào?
13. SSRF, DNS rebinding, endpoint substitution và registry poisoning được ngăn ra sao?
14. Health/readiness có tách khỏi identity và authorization không?
15. Khi registry, DNS, CA hoặc mesh control plane lỗi, fallback có an toàn không?
16. Có telemetry cho registration changes, TLS identity failures, stale endpoints và revoke delay không?
17. Có diễn tập control-plane compromise, cert rotation, endpoint failover và service impersonation không?

## 25. Ghi nhớ trọng tâm

- **Service discovery tìm endpoint, không xác minh danh tính.** IP, DNS record và registry entry không thay peer authentication.
- **Logical service identity ổn định hơn endpoint.** Instance có thể thay IP nhưng vẫn phải chứng minh cùng identity được mong đợi.
- **Control plane là tài sản trọng yếu.** Registry, orchestrator, CA và policy distribution cần authentication, authorization và audit riêng.
- **TLS/mTLS xác minh peer theo certificate và trust policy.** Kiểm tra chain, SAN/identity, validity và key usage; không tắt hostname verification.
- **Workload identity không tự cấp quyền nghiệp vụ.** Sau mTLS vẫn cần authorization theo scope, tenant, action và resource.
- **DNSSEC không thay mTLS.** Bảo vệ DNS data và xác minh peer là hai lớp khác nhau.
- **Service mesh không thay authorization ở application.** Mesh identity thường là workload identity, không phải end-user permission.
- **Discovery cache có thể giữ endpoint cũ.** Quản lý TTL, lease, invalidation và connection lifetime.
- **URL động tạo rủi ro SSRF và DNS rebinding.** Ưu tiên logical service allowlist và egress controls.
- **Identity propagation phải rõ actor và subject.** Không tin header do client tự khai hoặc forward token không đúng audience.

Service discovery an toàn kết hợp định tuyến động với danh tính workload ổn định. Resolver có thể tìm endpoint mới, nhưng caller vẫn xác minh peer bằng trust policy; sau đó resource server kiểm tra token, delegation và quyền trên action/resource. Khi control plane được bảo vệ và discovery không bị nhầm với authentication, hệ thống có thể scale và thay instance mà không mở rộng ranh giới tin cậy ngoài ý muốn.
