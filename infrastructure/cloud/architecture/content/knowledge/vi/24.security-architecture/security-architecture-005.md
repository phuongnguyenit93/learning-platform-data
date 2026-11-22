# Phân đoạn mạng và kiểm soát giao tiếp giữa dịch vụ

## 1. Vì sao cần phân đoạn mạng trong kiến trúc cloud?

Một ứng dụng cloud thường gồm nhiều thành phần: public frontend, API gateway, backend service, database, queue, cache, hệ thống quản trị và tích hợp với bên thứ ba. Nếu tất cả thành phần nằm trong một mạng phẳng và có thể kết nối tự do, một workload bị xâm nhập có thể dò tìm và tiếp cận nhiều tài nguyên khác. Phân đoạn mạng giảm phạm vi giao tiếp, giới hạn đường đi của traffic và làm nhỏ blast radius khi xảy ra sự cố.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc được thiết kế từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai; sau đó đánh giá theo độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Phân đoạn mạng là một phần của trust boundary: mỗi kết nối cần có nguồn, đích, protocol, purpose, identity và policy được xác định.

**Network segmentation** chia hạ tầng thành các vùng hoặc miền giao tiếp có mức tin cậy và quyền kết nối khác nhau. **Service-to-service communication control** quyết định workload nào được gọi workload nào, dùng giao thức gì, xác thực ra sao và operation nào được phép thực hiện.

Sau bài này, bạn có thể:

- Xác định trust boundary, ingress/egress và đường đi traffic giữa các thành phần.
- Thiết kế VPC/VNet, subnet, route table, security group, firewall và private endpoint.
- Phân biệt network reachability với authentication và application authorization.
- Áp dụng microsegmentation, service identity và mutual TLS (mTLS).
- Kiểm soát traffic north-south, east-west và egress ra Internet/bên thứ ba.
- Thiết kế DNS/service discovery, Kubernetes NetworkPolicy và service mesh.
- Kiểm thử policy theo nguyên tắc deny-by-default và least privilege.
- Quan sát flow, phát hiện kết nối bất thường và vận hành thay đổi policy an toàn.

## 2. Trust boundary và luồng traffic

### 2.1. North-south và east-west traffic

- **North-south traffic** đi giữa hệ thống và bên ngoài: Internet, người dùng, đối tác, corporate network hoặc on-premises.
- **East-west traffic** đi giữa các workload bên trong môi trường: API gateway tới service, service tới database, worker tới queue và service-to-service.

Một kiến trúc có thể bảo vệ north-south tốt bằng WAF/API gateway nhưng vẫn có rủi ro east-west nếu mọi backend đều được phép gọi nhau và dùng chung credential.

### 2.2. Ví dụ BookingCloud

BookingCloud có:

- Web/mobile clients truy cập API qua CDN, WAF và API gateway.
- Booking service xử lý đơn.
- Inventory service giữ slot thiết bị.
- Payment service kết nối payment provider.
- Notification worker gửi email qua provider.
- Database, cache và message broker nằm trong vùng private.
- Platform operators truy cập quản trị qua identity-aware access hoặc bastion được kiểm soát.

~~~mermaid
flowchart TB
    INTERNET["Internet / clients"] --> EDGE["CDN + WAF"]
    EDGE --> GW["Public API gateway"]
    subgraph PRIVATE["Private application network"]
      GW --> BOOK["Booking service"]
      BOOK --> INV["Inventory service"]
      BOOK --> PAY["Payment service"]
      WORKER["Notification worker"]
      BOOK --> DB[("Booking DB")]
      INV --> CACHE[("Cache")]
      BOOK --> MQ[("Message broker")]
      WORKER --> MQ
    end
    PAY --> EXT["Payment provider"]
    WORKER --> EMAIL["Email provider"]
    OPS["Admin access path"] --> PRIVATE
~~~

Sơ đồ thể hiện các vùng logic. Khi triển khai, cần xác định mỗi mũi tên có phải kết nối trực tiếp hay đi qua proxy/gateway; network route và policy nào cho phép; identity nào được xác thực; protocol nào được dùng; và log nào chứng minh kết nối.

### 2.3. Bốn câu hỏi cho mỗi kết nối

Với từng đường giao tiếp, ghi rõ:

1. **Who:** workload hoặc principal nguồn là ai?
2. **Where:** nguồn và đích thuộc network, subnet, namespace, account/project hay region nào?
3. **What:** protocol, port, API operation hoặc resource nào được phép?
4. **Why:** mục đích nghiệp vụ và owner của kết nối là gì?

Một rule kiểu “allow all traffic from application subnet to database subnet” thường quá rộng. Cần đi sâu đến workload, protocol, port, identity và operation phù hợp.

## 3. Mô hình phân đoạn mạng cơ bản

### 3.1. VPC/VNet và subnet

VPC (Virtual Private Cloud) hoặc VNet là mạng logic riêng trong cloud account/subscription/project. Subnet chia dải địa chỉ và thường gắn với route table, network ACL hoặc security policy.

Một cách tổ chức phổ biến:

| Zone | Thành phần | Đặc điểm truy cập |
|---|---|---|
| Edge/public | Load balancer, NAT gateway, public ingress | Nhận traffic được công bố, hạn chế inbound |
| Application/private | Backend services, workers | Không nhận kết nối trực tiếp từ Internet |
| Data/private | Database, cache, broker | Chỉ nhận kết nối từ workload cần thiết |
| Management | Bastion, management agent, monitoring | Chỉ dành cho đường quản trị được phê duyệt |

Tên public/private không tự quyết định bảo mật. Subnet có public route nhưng instance không có public IP có thể không trực tiếp reachable; ngược lại, private subnet vẫn có thể gửi egress Internet qua NAT. Phải kiểm tra route table, address assignment, firewall và policy thực tế.

### 3.2. Availability Zone và failure domain

Subnet thường gắn với một Availability Zone hoặc failure domain trong một region. Phân tán application và data plane qua nhiều zone có thể tăng resilience, nhưng cần giữ policy nhất quán:

- Mỗi zone phải có route và security policy tương đương.
- Health check/load balancer chỉ đưa traffic đến target khỏe.
- Cross-zone traffic, replication và failover vẫn dùng kết nối được kiểm soát.
- Không mở rộng quá rộng chỉ để đơn giản hóa failover.
- Kiểm tra dependency DNS/private endpoint khi một zone mất.

### 3.3. Route table và đường đi

Route table quyết định traffic tới CIDR/prefix nào đi qua target nào: local route, internet gateway, NAT gateway, transit gateway, VPN, peering hoặc private endpoint. Firewall/security policy sau đó quyết định traffic được phép hay không.

Hãy vẽ cả forward và return path. Stateful firewall có thể tự theo dõi connection; stateless ACL cần rule cho cả hai chiều và ephemeral ports. Một route tồn tại không đồng nghĩa connection được cho phép; một rule allow cũng không tạo được route nếu routing không có.

~~~mermaid
flowchart LR
    USER["Client"] --> IGW["Internet gateway"]
    IGW --> LB["Public load balancer"]
    LB --> APP["Private application subnet"]
    APP --> DB["Private data subnet"]
    APP --> NAT["NAT / controlled egress"]
    NAT --> EXT["Approved external APIs"]
    OPS["Admin network"] --> VPN["VPN / identity-aware gateway"]
    VPN --> MGMT["Management subnet"]
~~~

## 4. Ingress: kiểm soát traffic đi vào

Ingress là traffic từ bên ngoài một workload hoặc network boundary đi vào. Các lớp thường gặp:

- DNS và CDN: định tuyến đến edge phù hợp, giảm origin exposure.
- DDoS protection: hấp thụ hoặc lọc traffic độc hại ở lớp phù hợp.
- WAF: kiểm tra HTTP request theo rule, signature và application context.
- Load balancer/API gateway: TLS termination, routing, authentication, rate limit và request validation.
- Network firewall/security group: giới hạn source, destination, protocol và port.
- Application authorization: kiểm tra user/client được gọi resource/operation nào.

Không nên phơi database, cache, broker hoặc management port ra Internet. Public entry point nên là thành phần được thiết kế để nhận traffic ngoài và chỉ forward đến backend cụ thể.

### 4.1. TLS termination và hop kế tiếp

Nếu TLS kết thúc tại CDN hoặc load balancer, payload được giải mã ở đó. Chặng từ load balancer tới backend cần được bảo vệ theo threat model, thường bằng TLS nội bộ hoặc mTLS. Cũng phải xác thực backend identity nếu proxy là trust boundary.

### 4.2. Header và client identity

Không tin các header như X-Forwarded-For, X-User hoặc X-Tenant-ID từ client gốc. Chỉ tin metadata do proxy tin cậy ghi đè/chuẩn hóa, và application vẫn xác thực principal qua token/session. Header có thể hỗ trợ routing/observability nhưng không thay authentication hay authorization.

## 5. Egress: kiểm soát traffic đi ra

Egress thường bị bỏ quên vì ứng dụng “cần Internet để hoạt động”. Nhưng một workload bị xâm nhập có thể dùng outbound access để tải payload, exfiltrate dữ liệu hoặc kết nối command-and-control.

### 5.1. Egress control

Các biện pháp:

- Không cho outbound unrestricted từ mọi workload.
- Chỉ cho phép destination/service cần thiết theo hostname, IP range, port hoặc identity-aware proxy khi phù hợp.
- Dùng NAT gateway hoặc egress proxy để tập trung logging, filtering và quota.
- Chặn kết nối trực tiếp tới Internet nếu workload chỉ cần private endpoint.
- Dùng DNS filtering, domain allowlist và monitoring domain mới/bất thường.
- Kiểm soát metadata service và cloud control-plane endpoint; workload chỉ được truy cập theo nhu cầu.
- Giới hạn upload/data transfer tới public storage hoặc dịch vụ ngoài.

### 5.2. Allowlist IP và hostname

IP allowlist có thể khó duy trì khi provider thay đổi address, dùng CDN hoặc anycast. Hostname allowlist cần proxy/DNS-aware enforcement; một firewall L3/L4 thông thường có thể chỉ nhìn IP. Tránh tự resolve hostname một lần rồi lưu IP vô thời hạn.

Với các API bên thứ ba, nên dùng endpoint chính thức, TLS validation, credential scope, quota và audit. Egress allowlist không thay việc xác thực server certificate.

### 5.3. Private endpoint

Private endpoint/private link cho phép workload truy cập một dịch vụ cloud qua network path riêng hoặc private address, tùy provider. Lợi ích là giảm public exposure và kiểm soát đường truy cập. Tuy vậy:

- Cần DNS private zone/record đúng.
- Route, endpoint policy và resource policy phải tương thích.
- Private network reachability vẫn cần IAM/service authentication.
- Cross-account/project access vẫn cần authorization.
- Chi phí endpoint, data processing và cross-zone/region traffic cần được tính.

## 6. Security group, network ACL và firewall

Các cloud provider có tên và semantics riêng. Một số khái niệm tổng quát:

| Thành phần | Phạm vi thường gặp | Đặc tính |
|---|---|---|
| Security group | Network interface/instance/workload | Thường stateful; rule allow theo source/destination, protocol, port |
| Network ACL | Subnet | Có thể stateless; cần rule inbound/outbound và thứ tự |
| Network firewall | VPC/VNet hoặc transit path | Có thể lọc L3/L4/L7, domain, intrusion signal tùy sản phẩm |
| Host firewall | OS/container node | Bảo vệ traffic tới process/host cụ thể |
| Kubernetes NetworkPolicy | Pod/namespace selector | Giới hạn ingress/egress ở mức pod, cần CNI hỗ trợ |
| Service mesh policy | Workload identity/HTTP/gRPC | Có thể kiểm soát identity, service và operation ở L7 |

Không nên nhân bản cùng một rule ở nhiều tầng mà không có owner. Cần xác định lớp nào là enforcement chính, lớp nào là defense-in-depth và ai chịu trách nhiệm đồng bộ.

### 6.1. Mẫu ma trận rule

| Source | Destination | Protocol/port | Action | Lý do |
|---|---|---|---|---|
| Public edge LB | API gateway | TCP 443 | Allow | Client API ingress |
| API gateway | Booking service | TCP 8443 | Allow | Route API nội bộ |
| Booking service | Inventory service | TCP 8443 | Allow | Hold/release slot |
| Booking service | Booking DB | TCP 5432 | Allow | Database access |
| Inventory service | Cache | TCP 6379/TLS theo cấu hình | Allow | Cache operation |
| Application subnets | Database admin port | Any | Deny | Không mở truy cập quản trị chung |
| Backend workloads | Internet | Any | Deny by default | Chỉ egress qua approved path |

Port trong bảng chỉ là ví dụ. Phải đối chiếu listener thực tế, TLS mode, database version và service configuration.

### 6.2. Stateful vs stateless

Stateful rule theo dõi connection và thường cho phép return traffic của kết nối đã được cho phép. Stateless ACL xét từng packet/chiều riêng, nên phải mở đúng ephemeral return ports nếu cần. Một lỗi phổ biến là rule outbound đúng nhưng response không đi được vì stateless ACL thiếu rule chiều về.

### 6.3. Thứ tự rule và implicit behavior

Một số firewall áp dụng first-match, một số áp dụng priority hoặc default deny. Cần biết:

- Có rule nào rộng hơn rule dự kiến không?
- Default là allow hay deny?
- IPv4 và IPv6 có policy đồng nhất không?
- Có rule kế thừa từ organization/account không?
- Có đường bypass qua peering, VPN hoặc public IP không?
- Rule có tự hết hạn hoặc review theo thời gian không?

## 7. Microsegmentation

Phân đoạn truyền thống chia subnet theo tầng. **Microsegmentation** thu hẹp policy tới workload, service, process hoặc identity cụ thể, nhằm giảm lateral movement nếu một thành phần bị chiếm.

Ví dụ thay vì “mọi pod trong app subnet gọi được mọi pod khác”, policy quy định:

- Booking service chỉ gọi Inventory API và Booking DB.
- Notification worker chỉ consume notification queue và gọi email provider qua egress proxy.
- Payment service chỉ nhận command từ Booking service và gọi payment provider.
- Analyst workload chỉ truy cập read-only reporting endpoint.

Microsegmentation có thể thực hiện bằng host firewall, security group theo workload, Kubernetes NetworkPolicy, service mesh hoặc distributed firewall.

### 7.1. Ưu điểm và đánh đổi

| Lợi ích | Đánh đổi |
|---|---|
| Giảm lateral movement và blast radius | Nhiều policy hơn, cần catalog/automation |
| Làm rõ service dependency | Có thể chặn nhầm traffic khi dependency thay đổi |
| Hỗ trợ least privilege | Debug phức tạp hơn nếu policy phân tán |
| Dễ chứng minh luồng được phép | Cần inventory chính xác và policy lifecycle |

Không tạo policy quá chi tiết thủ công đến mức không thể bảo trì. Dùng identity/label/selector có governance, template và review tự động.

## 8. Service identity và mutual TLS

Network location chỉ cho biết workload có thể tiếp cận endpoint. Nó không chứng minh workload là ai. Khi các service chạy trong cùng cluster/VPC, một attacker có thể từ workload đã xâm nhập thử gọi endpoint nội bộ khác.

### 8.1. Service identity

Mỗi workload nên có identity riêng, ví dụ service account/workload identity/certificate subject. Identity có thể được cấp qua platform control plane và có vòng đời:

- Provision identity khi deploy workload.
- Bind identity với service, environment, namespace hoặc workload attribute.
- Cấp credential/certificate ngắn hạn.
- Rotate tự động.
- Revoke khi workload bị xóa hoặc nghi bị xâm nhập.
- Audit việc cấp, dùng và thay đổi identity.

Tránh dùng chung một API key tĩnh cho nhiều microservice. Khi bị lộ, không thể xác định nguồn gọi và phạm vi thu hồi quá lớn.

### 8.2. TLS và mTLS

- TLS xác thực server với client và mã hóa kênh; tùy cấu hình client có thể xác thực bằng token/application credential.
- mTLS yêu cầu cả client và server trình bày certificate/identity, cho phép hai phía xác thực workload identity ở tầng transport.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Booking service
    participant B as Inventory service
    A->>B: TLS handshake + client certificate
    B->>B: Validate client cert and trust chain
    B-->>A: Server certificate
    A->>A: Validate server cert and identity
    A->>B: Encrypted HTTP request
    B->>B: Authenticate workload identity
    B->>B: Authorize requested operation
    B-->>A: Protected response
~~~

mTLS bảo vệ danh tính và kênh giao tiếp, nhưng không tự quyết định client được gọi mọi API. Application vẫn cần authorization theo service identity, API operation, tenant/resource scope và business policy.

### 8.3. Certificate lifecycle

- Dùng CA/trust bundle được quản trị, xác minh chain và SAN/identity.
- Cấp certificate ngắn hạn hoặc rotation tự động.
- Có quy trình revoke/rotate khi workload hoặc CA bị compromise.
- Giám sát certificate sắp hết hạn và lỗi handshake.
- Tránh tắt certificate validation để “sửa nhanh” sự cố.
- Định kỳ kiểm tra trust bundle khi nhiều CA hoặc nhiều cluster giao tiếp.

## 9. Lớp mạng không thay authorization ở L7

L3/L4 policy thường trả lời: IP nào được kết nối tới IP/port nào? L7 policy trả lời: identity nào được gọi method/path/operation nào?

Ví dụ Booking service có thể được phép mở kết nối TCP tới Inventory service trên port 8443. Nhưng quyền đó không đồng nghĩa Booking service được gọi mọi route như admin, export hoặc delete. Có thể giới hạn bằng:

- OAuth 2.0 client credentials hoặc workload identity token.
- Audience/scope riêng cho API.
- mTLS identity kết hợp authorization policy.
- API gateway/service mesh authorization policy.
- Application-level RBAC/ABAC theo business resource.

### 9.1. Ví dụ policy logic

~~~yaml
service: booking-service
identity: spiffe://bookingcloud/prod/booking
allowedDestinations:
  - service: inventory-service
    protocol: https
    port: 8443
    allowedOperations:
      - POST /internal/holds
      - DELETE /internal/holds/{holdId}
  - service: booking-db
    protocol: tcp
    port: 5432
denied:
  - service: payment-admin
  - destination: public-internet
conditions:
  requireMutualTLS: true
  requireWorkloadToken: true
  tokenAudience: inventory-api
  environment: production
~~~

Đây là pseudoconfiguration, không phải policy syntax chạy trực tiếp ở một cloud provider hoặc service mesh. Khi triển khai phải ánh xạ đúng identity, selector, port, path, method, trust domain và enforcement point; đồng thời test rằng mọi đường bypass đều bị chặn.

## 10. DNS và service discovery

Trong kiến trúc dynamic, pod, task hoặc VM có thể thay đổi IP sau deploy, scale hoặc failover. Service discovery cung cấp cách tìm service qua tên ổn định thay vì hard-code IP.

Các thành phần có thể gồm:

- DNS private zone/service name.
- Kubernetes Service và cluster DNS.
- Service registry/control plane.
- Load balancer hoặc service mesh endpoint discovery.
- Health check và endpoint readiness.

### 10.1. DNS không phải authorization

Không phân giải được tên có thể chặn một đường kết nối, nhưng biết DNS name không đồng nghĩa được phép truy cập. Private DNS chỉ giảm exposure; identity, network policy và application authorization vẫn phải có.

### 10.2. DNS và failover

TTL, caching, negative DNS response và resolver behavior ảnh hưởng thời gian chuyển endpoint. Một client có thể giữ IP cũ sau khi record thay đổi. Cần phối hợp DNS TTL với connection pool, retry, health check và deadline.

Không giả định giảm DNS TTL xuống rất thấp sẽ luôn làm failover nhanh hơn; resolver, application cache và connection reuse có thể giữ endpoint cũ.

## 11. Kubernetes NetworkPolicy

Kubernetes NetworkPolicy cho phép xác định ingress và egress của Pod dựa trên namespace/pod selectors, IP blocks và ports, tùy CNI plugin. Cần kiểm tra CNI có enforce NetworkPolicy hay không; chỉ tạo resource không có nghĩa policy đang hoạt động.

### 11.1. Ví dụ default deny

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: booking
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Policy này chọn tất cả pod trong namespace booking và mặc định chặn ingress/egress không được policy khác cho phép, theo semantics của CNI hỗ trợ NetworkPolicy.

### 11.2. Chỉ cho Booking gọi Inventory

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: booking-to-inventory
  namespace: booking
spec:
  podSelector:
    matchLabels:
      app: booking-service
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: inventory
          podSelector:
            matchLabels:
              app: inventory-service
      ports:
        - protocol: TCP
          port: 8443
~~~

Ví dụ này minh họa selector và port; nhãn namespace phải thực sự được cấu hình, và DNS egress có thể cần rule riêng tới kube-dns/NodeLocal DNS tùy môi trường. Kết nối tới database, telemetry, metadata service và external endpoint cũng cần policy có chủ đích.

### 11.3. Các giới hạn cần hiểu

- NetworkPolicy chuẩn thường tập trung vào L3/L4; không tự kiểm tra HTTP path/method.
- Policy thường additive: nhiều policy có thể cộng các quyền cho phép; cần đọc semantics CNI và tránh rule rộng.
- HostNetwork, node traffic, ingress controller và traffic từ/đến node có thể có hành vi đặc thù.
- Egress tới DNS, metadata endpoint, control plane và service ngoài cần kiểm tra riêng.
- Label selector sai hoặc label có thể bị workload tự gán sẽ làm ranh giới yếu.
- NetworkPolicy không thay RBAC Kubernetes, Pod Security, secret management hoặc service identity.

## 12. Service mesh

Service mesh triển khai proxy/data plane giữa các workload và control plane cấp cấu hình/identity/policy. Tùy sản phẩm, mesh có thể hỗ trợ mTLS, service discovery, traffic routing, retries, timeout, circuit breaker, telemetry và authorization L7.

### 12.1. Khi nào mesh hữu ích?

- Nhiều service cần mTLS và certificate rotation nhất quán.
- Cần policy service-to-service theo identity.
- Cần observability/traffic management thống nhất.
- Cần canary, retries có kiểm soát hoặc fault injection giữa các service.

### 12.2. Đánh đổi

- Sidecar/ambient data plane thêm hop và latency.
- Control plane, proxy và certificate authority trở thành dependency cần vận hành.
- Policy có thể bị phân tán giữa mesh, gateway, application và network firewall.
- Debug lỗi handshake/routing/authz cần năng lực chuyên môn.
- Resource usage và chi phí telemetry tăng.

Mesh không tự bảo vệ traffic nếu service có thể bypass proxy hoặc workload không được inject/attach đúng. Cần enforce strict mTLS/authorization và kiểm tra đường trực tiếp.

## 13. Kiểm soát kết nối tới database và data plane

Database, cache và broker thường chứa dữ liệu hoặc state quan trọng; không nên dựa vào subnet private như kiểm soát duy nhất.

### 13.1. Database

- Chỉ nhận từ security group/identity của service cần truy cập.
- TLS và server certificate validation.
- DB account riêng theo service, quyền table/schema tối thiểu.
- Không cho client Internet kết nối trực tiếp.
- Tách connection quản trị và application traffic.
- Audit connection, privilege change và query nhạy cảm theo khả năng database.
- Dùng private endpoint/route phù hợp; tránh public endpoint nếu không cần.

### 13.2. Cache

- Chỉ workload cần thiết được mở kết nối.
- Authentication/ACL theo user/service và command scope nếu dịch vụ hỗ trợ.
- TLS, secret rotation và memory/data retention policy.
- Không dùng chung credential admin cho mọi service.

### 13.3. Message broker

- Tách producer và consumer permissions theo topic/queue.
- Không cấp quyền đọc tất cả topic chỉ vì service cần một queue.
- Bảo vệ broker protocol bằng TLS và workload identity/credential riêng.
- Kiểm soát DLQ, replay, schema registry và management console.
- Phân vùng network và quota để tenant/service noisy neighbor không ảnh hưởng toàn cụm.

## 14. Egress tới bên thứ ba và data exfiltration

BookingCloud có Payment service và Notification worker gọi ra ngoài. Đây là đường có thể mang dữ liệu nhạy cảm qua trust boundary.

### 14.1. Thiết kế egress rõ ràng

| Workload | Destination | Data được phép gửi | Kiểm soát |
|---|---|---|---|
| Payment service | Payment provider API | Payment token/reference và amount cần thiết | TLS, endpoint validation, secret scope, egress allowlist |
| Notification worker | Email provider | Recipient và nội dung đã lọc | TLS, rate/quota, PII minimization, audit |
| Backend service | KMS/private cloud APIs | Key operation metadata | Private endpoint, workload identity, policy |
| Monitoring agent | Telemetry collector | Metrics/traces đã redacted | TLS, destination allowlist, write-only identity |

Không gửi toàn bộ customer record hoặc request context tới provider nếu chỉ cần một số trường.

### 14.2. Phòng data exfiltration

- Kiểm soát DNS và outbound destination.
- Dùng proxy có logging, classification hoặc DLP khi phù hợp.
- Hạn chế upload lớn, protocol không cần thiết và direct egress.
- Phát hiện traffic volume, domain hoặc region bất thường.
- Giới hạn quyền read/export ở application/storage layer.
- Tách role và approval cho bulk export.
- Kiểm tra cloud storage public access và cross-account policy.

Network firewall không thể hiểu đầy đủ nội dung đã mã hóa TLS nếu không có inspection phù hợp. Đừng dựa duy nhất vào deep packet inspection; cần identity, application audit, DLP ở endpoint được phép và data minimization.

## 15. Chính sách deny-by-default và lifecycle của rule

Một rule firewall hoặc NetworkPolicy không nên là cấu hình một lần rồi bỏ quên.

### 15.1. Quy trình quản trị rule

1. Ghi nhận owner, source, destination, protocol, port, purpose và data classification.
2. Xác định thời hạn hoặc điều kiện review.
3. Tạo rule dưới dạng infrastructure as code nếu có thể.
4. Peer review và policy validation tự động.
5. Deploy theo môi trường hoặc staged rollout.
6. Kiểm thử allow path và deny path.
7. Quan sát flow log và application telemetry.
8. Loại bỏ rule unused/deprecated; cập nhật dependency map.

### 15.2. Tránh rule rộng tạm thời trở thành vĩnh viễn

Nếu sự cố yêu cầu mở tạm một port, rule phải có owner, ticket, scope tối thiểu và expiry. Alert khi rule tạm còn tồn tại sau ngày dự kiến. Không giải quyết deployment lỗi bằng cách mở toàn bộ CIDR hoặc all ports trong production.

### 15.3. Policy as code

Có thể dùng static validation để phát hiện:

- 0.0.0.0/0 hoặc ::/0 mở vào management/database port.
- Egress unrestricted từ namespace/data tier.
- Security group dùng wildcard port.
- Rule trùng hoặc shadow nhau.
- Workload không có identity hoặc không có policy.
- Route/peering tạo đường bypass.

Các cảnh báo cần đối chiếu ngữ cảnh; public HTTPS listener có thể là chủ đích, trong khi SSH/RDP/database public thường cần xem xét nghiêm ngặt.

## 16. Quan sát và điều tra luồng mạng

### 16.1. Nguồn telemetry

- VPC/VNet flow logs hoặc network flow telemetry.
- Firewall/WAF/load balancer logs.
- DNS query logs.
- Kubernetes CNI/NetworkPolicy events.
- Service mesh access logs, metrics và distributed traces.
- Certificate issuance/rotation/handshake logs.
- Cloud audit logs cho route, security group, firewall và endpoint changes.

### 16.2. Metrics quan trọng

| Metric | Ý nghĩa | Điều cần phát hiện |
|---|---|---|
| Allowed/denied connection count | Mức traffic và policy deny | Kết nối bất thường hoặc rule sai |
| East-west service traffic | Service nào gọi service nào | Dependency mới hoặc lateral movement |
| Egress bytes/destination | Lưu lượng đi ra ngoài | Data exfiltration hoặc destination lạ |
| TLS/mTLS handshake failures | Sức khỏe trust/certificate | Certificate hết hạn hoặc identity mismatch |
| DNS NXDOMAIN/new domains | Hoạt động phân giải tên | Domain lạ, typosquatting hoặc misconfiguration |
| Policy changes | Thay đổi network access | Mở rộng quyền ngoài change window |
| Connection latency/retransmits | Chất lượng đường mạng | Congestion, routing issue |

Flow logs có thể bị thiếu packet-level detail hoặc có độ trễ tùy dịch vụ. Không dùng chúng thay packet capture/trace khi điều tra cần độ sâu hơn.

### 16.3. Correlation

Liên kết network flow với workload identity, deployment version, namespace, request trace ID và change record nếu hệ thống hỗ trợ. Tránh đưa user token hoặc payload nhạy cảm vào network log.

## 17. Kiểm thử phân đoạn và service communication

### 17.1. Kiểm thử positive và negative

| Test | Kỳ vọng |
|---|---|
| Booking → Inventory 8443 | Allow + mTLS/authz pass |
| Booking → Booking DB port được chỉ định | Allow |
| Booking → Payment admin endpoint | Deny |
| Notification worker → Database | Deny nếu không có dependency |
| Internet → Database | Deny |
| Pod trong namespace khác → Booking pod | Deny nếu chưa được cấp policy |
| Workload không có client certificate hợp lệ → internal API | TLS/authentication reject |
| Booking identity gọi Inventory admin operation | Network có thể reachable nhưng L7 authorization deny |
| Backend → unapproved Internet destination | Egress deny hoặc proxy reject |
| DNS/route failover | Chỉ endpoint khỏe và được policy cho phép nhận traffic |

### 17.2. Connectivity test không đủ

Lệnh curl thành công chỉ chứng minh một đường kết nối và một request hoạt động tại thời điểm test. Cần test:

- Identity đúng/sai.
- Certificate hết hạn/không đúng SAN.
- Token audience/scope sai.
- HTTP method/path không được cấp.
- Egress tới domain chưa approve.
- Policy sau rolling deployment.
- Pod restart và IP thay đổi.
- Failover zone/region.

### 17.3. Chaos/fault injection

Diễn tập revoke certificate, mất DNS resolver, firewall rule update sai, endpoint private không resolve, service mesh proxy restart hoặc zone mất kết nối. Kiểm tra hệ thống fail-closed ở ranh giới nhạy cảm, phục hồi trong SLO và không tạo bypass tạm thời không được kiểm soát.

## 18. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai sở hữu network rule, service identity và egress policy? Thay đổi có thể truy vết/rollback? | Network inventory, IaC, change review, flow logs và runbook |
| **Security** | Có default deny, microsegmentation, mTLS và authorization L7? | Threat model, policy tests, certificate lifecycle, deny events |
| **Reliability** | Firewall/DNS/mesh/endpoint failure có làm mất đường quan trọng hoặc tạo bypass? | Multi-zone design, health check, failure drills, rollback |
| **Performance Efficiency** | Proxy, inspection, mesh và cross-zone traffic ảnh hưởng latency/throughput? | p95/p99, handshake, flow volume, load test |
| **Cost Optimization** | Firewall/endpoint/egress/mesh logging có chi phí nào tăng theo traffic? | Egress bill, endpoint hourly/data cost, proxy resource usage |
| **Sustainability** | Có traffic vòng, route thừa, refresh/telemetry không cần thiết? | Flow inventory, utilization, rule cleanup và traffic optimization |

Một thiết kế tốt phải vừa chặn được traffic không cần thiết vừa giữ được các luồng nghiệp vụ và failover cần thiết. Network rule quá rộng làm yếu bảo mật; rule quá hẹp nhưng không có dependency map làm tăng outage và thời gian vận hành.

## 19. Bài thực hành: phân đoạn mạng cho BookingCloud

Hiện trạng:

- Tất cả service chạy trong một VPC và một subnet.
- Mỗi backend có thể gọi mọi backend trên mọi port.
- Database có private IP nhưng chấp nhận traffic từ cả subnet.
- Backend có egress Internet trực tiếp qua NAT.
- Kubernetes chưa có default-deny NetworkPolicy.
- Các service dùng chung một API key nội bộ.
- Admin truy cập node qua SSH từ VPN dải rộng.

Hãy thực hiện:

**Bài 1 — Threat model:** xác định ít nhất sáu đường lateral movement hoặc exfiltration nếu một pod bị chiếm.

**Bài 2 — Network zones:** vẽ edge, application, data, management và egress zones. Nêu subnet, route và private endpoint cần có.

**Bài 3 — Allow matrix:** lập bảng source/destination/protocol/port/purpose cho gateway, Booking, Inventory, Payment, worker, DB, cache, broker và KMS.

**Bài 4 — Identity:** thay shared API key bằng workload identity/certificate; thiết kế mTLS và authorization L7 cho từng API.

**Bài 5 — Kubernetes:** tạo default-deny ingress/egress và policy chỉ cho Booking gọi Inventory; xử lý DNS và telemetry.

**Bài 6 — Egress:** thiết kế NAT/egress proxy, destination allowlist và kiểm soát dữ liệu đi tới payment/email provider.

**Bài 7 — Admin:** thay SSH từ VPN rộng bằng identity-aware/bastion/short-lived access; giới hạn management subnet.

**Bài 8 — Test/observability:** viết positive/negative test, flow logs/metrics và diễn tập khi policy chặn nhầm hoặc zone bị mất.

### Khung kết quả tự kiểm tra

| Hiện trạng | Rủi ro | Hướng cải tiến |
|---|---|---|
| Một subnet phẳng | Lateral movement dễ | Tách edge/app/data/management và microsegment |
| Backend gọi mọi backend | Blast radius lớn | Allow matrix theo dependency |
| DB nhận cả subnet | Workload không liên quan cũng có thể thử kết nối | Chỉ allow service identity/SG cần thiết |
| Egress trực tiếp | Exfiltration/C2 khó kiểm soát | Egress proxy/allowlist/private endpoint |
| Không có NetworkPolicy | Pod giao tiếp rộng | Default deny và policy theo label/workload |
| Shared API key | Không phân biệt service, khó revoke | Workload identity và mTLS |
| VPN dải rộng + SSH | Management exposure lớn | JIT, MFA, bastion/identity-aware access và audit |

Đáp án phải nêu được luồng hợp lệ, luồng bị chặn, identity được xác thực và cách xác minh policy thực sự được enforce.

## 20. Checklist trước khi đưa network segmentation vào production

- [ ] Có network/data-flow map với owner và trust boundary.
- [ ] North-south và east-west traffic được nhận diện riêng.
- [ ] Edge, application, data và management zone có route/policy phù hợp.
- [ ] Ingress chỉ đi qua entry point được duyệt.
- [ ] Egress deny-by-default hoặc có destination policy được quản trị.
- [ ] Private endpoint/DNS/route được kiểm tra cùng resource/IAM policy.
- [ ] Security group/NACL/firewall có rule hẹp, owner, purpose và review date.
- [ ] Có microsegmentation cho workload nhạy cảm.
- [ ] Service identity riêng; credential/certificate có lifecycle và rotation.
- [ ] mTLS/TLS validation được bật trên chặng cần bảo vệ.
- [ ] L7 authorization giới hạn operation; network reachability không được coi là permission.
- [ ] Kubernetes CNI thực sự enforce NetworkPolicy; default-deny và DNS/telemetry rules đã test.
- [ ] Database/cache/broker không public và chỉ nhận workload cần thiết.
- [ ] Admin access có MFA, just-in-time, audit và blast radius hẹp.
- [ ] Flow logs, DNS/firewall/mesh telemetry có retention và alert.
- [ ] Có positive/negative tests, fault injection và rollback cho policy change.

Phân đoạn mạng tạo ra các vùng giao tiếp có giới hạn; service identity xác định workload nào đang gọi; TLS/mTLS bảo vệ kênh và xác thực đầu bên kia; authorization L7 giới hạn operation và resource. Kết hợp các lớp này với egress control, DNS/service discovery, policy as code và observability giúp giảm lateral movement, bảo vệ dữ liệu và giữ cho các đường giao tiếp cần thiết hoạt động ổn định khi hệ thống thay đổi.
