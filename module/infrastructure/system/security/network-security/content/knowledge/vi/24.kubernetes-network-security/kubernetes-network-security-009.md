# Bảo vệ control plane endpoint trong Kubernetes: kiểm soát đường vào, danh tính và quyền quản trị

Trong chương **Bảo mật mạng Kubernetes** thuộc module **SECURITY_NETWORK_SECURITY**, **control plane endpoint** là một trong những ranh giới quan trọng nhất của cluster. Đây thường là địa chỉ mà người quản trị, hệ thống tự động, kubelet và những thành phần được ủy quyền dùng để liên lạc với **Kubernetes API server (kube-apiserver)**. Endpoint có thể được công bố qua DNS và load balancer, nằm trên mạng riêng hoặc có địa chỉ public nhưng yêu cầu TLS, xác thực và chính sách truy cập chặt chẽ.

Nếu kẻ tấn công có quyền gọi Kubernetes API với danh tính đủ mạnh, họ có thể đọc Secrets, tạo hoặc sửa workloads, thay NetworkPolicy, tạo ClusterRoleBinding, truy cập logs hoặc dùng các tính năng như **exec, attach, port-forward** để mở rộng phạm vi xâm nhập. Ngược lại, một cluster có API server hoàn toàn private vẫn có thể bị chiếm quyền nếu kubeconfig hoặc service account token bị lộ, RBAC quá rộng hay quyền quản trị cloud bị cấu hình sai.

Vì vậy, **bảo vệ control plane endpoint không đồng nghĩa chỉ đóng cổng 6443**. Cần bảo vệ đồng thời **network reachability, DNS/TLS trust, authentication, authorization, admission, workload/control-plane trust boundaries, audit, khả năng phục hồi và tài khoản của cloud provider**.

Sau bài học, bạn có thể:

- Vẽ đường kết nối tới **Kubernetes API server** và phân biệt endpoint với **etcd, kubelet, controller manager, scheduler**.
- Đánh giá các mô hình **public endpoint, public endpoint có allowlist, private endpoint và hybrid access**.
- Cấu hình tư duy bảo vệ **TLS certificate, CA trust, server name, kubeconfig, user/OIDC identity, service account credentials**.
- Sử dụng nguyên tắc **least privilege RBAC**, admission controls và phân tách quyền quản trị Kubernetes với quyền quản trị hạ tầng cloud.
- Hiểu giới hạn của **Security Group, NSG, VPC firewall, Kubernetes NetworkPolicy, private DNS, VPN, bastion và API gateway** đối với endpoint.
- Xây dựng **audit trail, metrics, rate/concurrency controls, HA và incident-response playbook** cho control plane.
- Kiểm chứng đường truy cập bằng **kubectl read-only, cloud networking evidence, positive/negative tests** mà không thử xâm nhập hệ thống không thuộc quyền.

## 1. Control plane endpoint thực sự là gì?

Trong Kubernetes, **API server** cung cấp điểm giao tiếp của Kubernetes API qua HTTPS. Những thao tác tạo Pod, xem Namespace, sửa Deployment, cấp quyền RBAC hoặc đọc tài nguyên cluster phần lớn được thực hiện qua API server. Các thành phần control plane khác cũng sử dụng API server để đọc và cập nhật trạng thái mong muốn của cluster.

~~~mermaid
flowchart TB
    H["Người quản trị / kubectl"] --> E["DNS + TLS endpoint / LB"]
    C["CI/CD + automation"] --> E
    W["Kubelet / agents được phép"] --> E
    E --> A["kube-apiserver"]
    A --> T["Authentication"]
    T --> Z["Authorization / RBAC / webhook"]
    Z --> M["Admission policies và validation"]
    M --> S["Kubernetes resources / etcd qua API server"]
    A -. "Audit events / metrics" .-> O["SOC / SRE"]
    S -. "Desired state" .-> R["Controllers / workloads"]
~~~

Đây là **luồng logic**: authentication, authorization và admission hoạt động theo các quy tắc của Kubernetes và loại request; không phải mọi request đều đi qua admission theo cùng cách. Đặc biệt, các thao tác đọc tài nguyên không giống create/update khi xét admission.

### 1.1. API server khác các thành phần còn lại

| Thành phần | Vai trò | Bảo mật mạng cần chú ý |
| --- | --- | --- |
| **kube-apiserver** | Cổng API của cluster; xử lý request, kiểm tra danh tính/quyền và tương tác với trạng thái cluster | Endpoint TLS, network ingress, authn/authz, audit, availability |
| **etcd** | Kho lưu trữ trạng thái cluster, có thể bao gồm dữ liệu Secrets | Không public; kiểm soát client/peer TLS, IAM, backup và encryption at rest |
| **kubelet** | Agent trên node quản lý các Pod/containers được giao | Kubelet API và xác thực/ủy quyền riêng; không mở tùy tiện cho nguồn lạ |
| **kube-controller-manager** | Vận hành các control loops | Quyền truy cập API, leader election, credential và cấu hình |
| **kube-scheduler** | Chọn node cho Pods dựa trên trạng thái và chính sách | Quyền truy cập API, scheduling integrity |
| **Cloud controller / CSI / CNI agents** | Kết nối API với hạ tầng cloud/network/storage | Service identity, RBAC, IAM, credential boundaries |
| **Admission webhooks** | Có thể kiểm tra hoặc biến đổi resource ở thời điểm admission | TLS, availability, policy scope, timeout, webhook fail mode |

Một cluster có API server bảo mật tốt nhưng **etcd hoặc kubelet endpoint lộ ra ngoài** vẫn có thể chịu rủi ro nghiêm trọng. Tuy nhiên, đây là các **bề mặt liên quan**, không nên nhầm rằng mọi cổng control plane đều là API server endpoint.

### 1.2. Địa chỉ và cổng của endpoint

- Trên cluster tự quản, Kubernetes API server thường phục vụ HTTPS trên **TCP 6443** theo nhiều cấu hình mặc định hoặc hướng dẫn phổ biến.
- Trên dịch vụ managed Kubernetes, client có thể kết nối tới **FQDN trên TCP 443** hoặc cổng do provider quy định; địa chỉ phía sau có thể là load balancer/hạ tầng do provider quản lý.
- **Không suy ra cổng từ tên thành phần**. Cần xem **kubeconfig server URL, provider cluster endpoint configuration và effective network policy**.
- Endpoint có thể được truy cập qua **IPv4, IPv6, private DNS, public DNS, VPN hoặc đường mạng riêng** tùy provider và kiến trúc.

Ví dụ một kubeconfig có thể khai báo:

~~~yaml
# Mẫu minh họa — tên miền giả, không phải kubeconfig đăng nhập thực.
apiVersion: v1
kind: Config
clusters:
  - name: learning-cluster
    cluster:
      server: https://k8s-api.example.test:6443
      certificate-authority-data: BASE64_CA_CERTIFICATE_PLACEHOLDER
contexts:
  - name: learning-context
    context:
      cluster: learning-cluster
      user: demo-identity
current-context: learning-context
users:
  - name: demo-identity
    user: {}
~~~

Đây **không phải credential hợp lệ**. Trong môi trường thật, user entry cần phương thức authentication được phê duyệt. Trường **server** chỉ cho biết nơi client sẽ gửi request; không tự xác nhận endpoint đó đáng tin hoặc user có quyền.

## 2. Threat model: điều gì xảy ra nếu API server bị lạm dụng?

### 2.1. Tài sản phải bảo vệ

1. **Kubernetes API access**: quyền đọc/ghi tài nguyên và các subresources.
2. **Kubeconfigs, tokens, client certificates và OIDC identities**: credential để vào API.
3. **RBAC objects**: Role, ClusterRole, RoleBinding, ClusterRoleBinding và quyền quản trị tương đương.
4. **Workload deployment integrity**: Pod/Deployment/DaemonSet/Job/Admission configuration không bị sửa trái phép.
5. **Secrets và service account tokens**: dữ liệu nhạy cảm, khả năng truy cập hệ thống phụ thuộc.
6. **Control plane availability**: cluster có thể tiếp tục điều phối workloads và khôi phục lỗi.
7. **Audit evidence**: bằng chứng ai đã thay gì, bằng danh tính nào, từ đâu và khi nào.
8. **Cloud/IAM boundary**: quyền tạo/sửa cluster endpoint, control plane network access, node roles và keys.

### 2.2. Một kẻ tấn công có thể bắt đầu từ đâu?

| Điểm vào | Rủi ro | Biện pháp trọng tâm |
| --- | --- | --- |
| **Internet-reachable endpoint** | Quét bề mặt TLS/HTTP, thử credential hoặc khai thác API/proxy nếu có lỗ hổng | Patch, network allowlist/private access, authn/authz và rate/DoS protection |
| **Kubeconfig bị lộ** | Dùng credential/token/cert hoặc context nhầm để gọi API | Bảo vệ file, short-lived auth, revoke/rotate và audit |
| **CI runner bị chiếm** | Lạm dụng service identity/cluster-admin ở pipeline | Workload identity, least privilege RBAC/IAM, scoped tokens |
| **Pod bị chiếm quyền** | Dùng mounted service account token hoặc đường network tới API server | Minimal RBAC, token projection, pod hardening, egress policy có hiệu lực |
| **Cloud IAM role quá rộng** | Thay endpoint access hoặc obtain cluster access qua tích hợp provider | Least privilege cloud IAM, MFA/JIT, approval và audit |
| **Bastion/VPN bị chiếm** | Có đường private tới API endpoint cùng credential quản trị | PAM/MFA, device posture, session logging, segmentation |
| **Admission webhook bị lạm dụng** | Cho phép tài nguyên ngoài policy hoặc gây lỗi tạo workload | Hạn chế quyền webhook, policy review, TLS và HA |
| **Aggregated API/extension** | Bề mặt API bổ sung và service trust boundary | Review APIService/webhook/backend identity và routing |

**Network allowlist không phải authentication.** Một IP được cho phép vẫn có thể thuộc NAT dùng chung, jump host bị chiếm hoặc CI runner đã mất kiểm soát. **RBAC không thay network controls** khi endpoint bị flood ở tầng thấp trước khi xử lý danh tính.

### 2.3. Ba trạng thái cần phân biệt

- **Reachable**: client có thể kết nối TCP/TLS tới endpoint.
- **Authenticated**: API server xác định được một identity theo một cơ chế được cấu hình.
- **Authorized**: identity được phép thực hiện verb trên resource/subresource trong phạm vi phù hợp.

Một kết nối HTTPS thành công **không chứng minh** có quyền liệt kê Secrets; một phản hồi **401** chứng minh request không được xác thực thành công theo ngữ cảnh nhưng endpoint vẫn có thể đang reachable; **403** thường cho biết request đã tới bước quyết định authorization, với những ngoại lệ ngữ nghĩa cần xem log.

## 3. Đường đi tới control plane endpoint

Trước khi thiết kế firewall, hãy xác định **source types, DNS, IP, ports, return path và những bên thực sự cần API**.

~~~mermaid
flowchart LR
    A["Admin device"] --> V["VPN / ZTNA / private access"]
    V --> D["Private DNS / network path"]
    D --> E["Kubernetes API endpoint"]
    C["CI runner"] -->|Authorized network + identity| E
    N["Node / kubelet"] -->|Managed/internal path| E
    P["Pod / service account"] -->|Cluster Service / endpoint path| E
    E --> S["API authentication + authorization"]
    E -. "Audit/telemetry" .-> O["SOC"]
~~~

**Một FQDN có thể phân giải khác nhau** từ laptop bên ngoài, bastion, VPN client và Pod trong cluster. Cần ghi lại đường thực tế cho từng nguồn.

### 3.1. Flow matrix nên có

| Nguồn | Nhu cầu kết nối | Điều kiện an toàn |
| --- | --- | --- |
| **Admin laptop** | kubectl đọc/đổi cấu hình theo nhiệm vụ | Managed device, MFA/IdP, private/ZTNA path nếu được chọn, least privilege |
| **Emergency/break-glass operator** | Khôi phục khi IAM/IdP/network lỗi | Credential được bảo vệ đặc biệt, JIT/procedure, audit và thử định kỳ |
| **CI/CD runner** | Deploy các resources đã được phê duyệt | Runner identity riêng, RBAC scope hẹp, token ngắn hạn, log |
| **Node/kubelet** | Đăng ký và đồng bộ workloads | Node certificate/credential, đường node-to-API đúng thiết kế, node authorizer |
| **System controllers/operators** | Theo dõi/thay trạng thái đã ủy quyền | ServiceAccount riêng, RBAC theo namespace/resource, không cluster-admin đại trà |
| **Application Pod** | Chỉ nếu thực sự sử dụng Kubernetes API | ServiceAccount tối thiểu, automount token khi cần, kiểm soát egress |
| **Partner/unmanaged host** | Thông thường không cần gọi control plane | Không nằm trong allowlist/network path, không có credential |

### 3.2. North–south và east–west với API server

Đối với một cluster, traffic từ quản trị viên tới API có thể đi từ bên ngoài vào control plane, còn kubelet/Pod tới API có thể đi trong mạng quản trị/nội bộ. Nhưng **không được suy một firewall rule đủ cho cả hai**.

Nếu giới hạn control plane endpoint theo một tập **admin public IP**, phải kiểm tra **node/CI/control-plane internal path** có độc lập không. Trên managed Kubernetes, một phần traffic nội bộ được provider xử lý qua endpoint hoặc cơ chế không trùng với public path. Thay đổi tùy chọn public/private có thể ảnh hưởng node registration, operators, webhook và DNS.

## 4. Public endpoint, private endpoint và hybrid access

### 4.1. Ba mô hình triển khai

| Mô hình | Đường truy cập | Lợi ích | Rủi ro/điều kiện |
| --- | --- | --- | --- |
| **Public endpoint có xác thực** | Internet có thể tới TLS endpoint theo network policy | Dễ quản trị từ nhiều mạng, ít phụ thuộc VPN | Bề mặt reachable rộng, cần patching, strong auth, rate/DoS controls |
| **Public endpoint + authorized source ranges** | Public IP/FQDN nhưng chỉ một số IP/CIDR được phép | Thu hẹp bề mặt network | NAT/shared IP, roaming admin, CI egress changes, provider-specific coverage |
| **Private endpoint** | Chỉ có đường private qua VPC/VNet, VPN, peering, transit, ZTNA hoặc bastion | Giảm Internet reachability, hỗ trợ segmentation | DNS/routing, private access, recovery path, CI runner location, HA phụ thuộc |
| **Hybrid/dual access** | Public và private path có policy riêng | Hỗ trợ migration/khả dụng theo use case | Dễ tạo đường bypass hoặc không nhất quán giữa IPs/policies |

**Private không đồng nghĩa zero trust**: một máy trong mạng private bị chiếm và có token đủ quyền vẫn có thể gọi API. Ngược lại, public endpoint không tự có nghĩa cluster bị chiếm nếu authentication/authorization thực thi tốt, dù bề mặt rủi ro mạng lớn hơn.

### 4.2. Public endpoint có allowlist

Đặt allowlist cần quan tâm:

1. **IP nguồn thực tại điểm enforcement**: người dùng đi qua VPN, NAT, CGNAT hoặc proxy doanh nghiệp có thể xuất hiện dưới egress IP khác dự kiến.
2. **CI/CD runners**: hosted runner có thể dùng dải IP thay đổi; không mở 0.0.0.0/0 chỉ để workflow chạy.
3. **IPv4/IPv6**: nếu endpoint hỗ trợ dual-stack, allowlist phải bao phủ cả address families theo thiết kế.
4. **Access từ node hoặc control-plane components**: kiểm tra nhà cung cấp xử lý các kết nối nội bộ thế nào trước khi thu hẹp rule.
5. **Failover**: thêm/bớt IP quản trị phải có change management, không tạo lỗ hổng vĩnh viễn.

Một IP allowlist nên coi là **lớp giảm bề mặt truy cập**, còn identity, MFA, RBAC và audit vẫn bắt buộc.

### 4.3. Private endpoint và DNS

Private endpoint cần **địa chỉ private reachable, DNS đúng, route đúng và firewall cho phép đúng luồng**:

~~~text
Admin laptop
   |
   | Managed VPN / private network / ZTNA
   v
Private DNS resolves k8s-api.example.test -> private endpoint address
   |
   | Route over approved private link
   v
Control plane TLS endpoint
   |
   +-- Authn / Authz / Audit
~~~

Các sự cố điển hình:

- **DNS giải ra public IP** trong khi public path đã tắt.
- Laptop được VPN nhưng **không có route** tới subnet/control plane CIDR.
- Firewall cho forward TCP 443 nhưng **return traffic** đi qua đường khác.
- Proxy doanh nghiệp cố **TLS interception** làm thay đổi trust chain và client từ chối endpoint.
- Private DNS được khai báo ở VPC/VNet nhưng **on-prem resolvers** không forward đúng.
- Network ACL/cloud endpoint policy có đường nguồn/đích khác nhau khi thay region/zone.

Không sửa lỗi TLS bằng cách **bỏ xác minh certificate**. Phải sửa DNS, CA trust, network route hoặc endpoint chính thống.

### 4.4. Bastion, VPN và ZTNA

Một bastion/management workstation có thể tạo điểm quản trị tập trung. Tuy nhiên, bastion cũng là tài sản có **giá trị tấn công cao** vì vừa có đường private vừa có thể chứa credential.

Controls hữu ích:

- **MFA/PAM/JIT access**, device health, hardening và đăng nhập bằng danh tính cá nhân.
- **Không dùng kubeconfig cluster-admin chia sẻ** trên tất cả bastion users.
- **Session audit** và chính sách hạn chế copy secrets.
- Phân đoạn rõ **bastion → Kubernetes API**, không cho bastion truy cập tất cả backend/databases khi không cần.
- Có **break-glass path** được thử trong tình huống VPN/IdP/DNS mất khả dụng.

## 5. TLS và danh tính server: endpoint phải được xác minh

Kubernetes API server thường được truy cập qua **HTTPS/TLS**. Client cần xác minh certificate chain của API server và **server identity** phù hợp với endpoint đang truy cập.

### 5.1. Vai trò của CA/SAN trong kubeconfig

Một kubeconfig thường chứa **server URL** cùng thông tin trust cho API server, ví dụ **certificate-authority-data** hoặc đường dẫn tới CA certificate được phê duyệt. Một số tích hợp có cách cung cấp trust tương đương.

**Một certificate hợp lệ về chữ ký nhưng không khớp FQDN/IP trong server URL** vẫn có thể bị từ chối. Nếu endpoint dùng load balancer hoặc private DNS mới, cần bảo đảm **SAN của serving certificate** phù hợp với hostname/IP mà client xác minh.

### 5.2. Vì sao không nên dùng insecure-skip-tls-verify

Tắt xác minh TLS:

- Khiến client không còn chứng minh chắc chắn đang nói chuyện với **API server được dự kiến**.
- Có thể làm lộ token/client authentication information tới bên giả mạo khi kết nối bị chuyển hướng.
- Che lỗi private DNS, cert chain, SAN hoặc CA rotation.
- Tạo một ngoại lệ khó phát hiện nếu kubeconfig được đưa vào CI.

**Giải pháp đúng** là sửa nguồn tin cậy, certificate, endpoint name hoặc đường đi; không ghi insecure-skip-tls-verify như một phương thức “khắc phục” lâu dài.

### 5.3. Client certificate và serving certificate là hai vai trò

| Chứng thư | Ai trình bày | Ai kiểm tra | Công dụng |
| --- | --- | --- | --- |
| **API serving certificate** | API server/load balancer TLS termination | kubectl, kubelet, automation client | Xác minh máy chủ đang được kết nối |
| **Client certificate** nếu được cấu hình | User/agent/kubelet client | API server và authn chain | Xác thực một identity client |
| **Etcd client/peer certificates** | Thành phần được ủy quyền gọi etcd | Etcd servers/peers | Bảo vệ kết nối lưu trữ trạng thái, không thay RBAC Kubernetes |
| **Webhook serving certificate** | Admission/authorization webhook server | API server | Bảo vệ điểm mở rộng webhook |

Không sử dụng certificate của API server để ký leaf certificates khác. **Private keys** phải được giữ ở nơi được kiểm soát; CA key cần có vòng đời và quyền chặt hơn workload key.

### 5.4. Certificate rotation

Đối với self-managed cluster, cần kiểm kê **API server serving cert, CA trust, client certs, kubelet-related PKI và endpoint aliases**. Managed control planes có thể do provider quản lý phần lớn việc cấp/gia hạn; nhưng đội vận hành vẫn chịu trách nhiệm về kubeconfig, identity, endpoint/network policy và các chứng thư do mình triển khai.

Quy trình an toàn:

1. Xác định issuer/CA, SAN, validity và những client trust anchors.
2. Cấp/rotate cert theo thiết kế; không làm mất quyền giữa các HA API server replicas.
3. Xác minh **kubeconfig clients, node registration, CI runners và monitoring**.
4. Đảm bảo có **overlap/rollout** phù hợp khi thay CA hoặc trust anchor.
5. Theo dõi certificate expiry và phản hồi TLS lỗi.

## 6. Authentication: ai đang gọi Kubernetes API?

Network reachability và TLS server validation mới chỉ đưa request tới **API server đúng**. Bước tiếp theo là **xác thực client** qua cơ chế được cluster hỗ trợ và bật đúng chính sách.

### 6.1. Các cơ chế thường gặp

| Cơ chế | Identity được xác định | Rủi ro điển hình | Control |
| --- | --- | --- | --- |
| **OIDC / external IdP** | Human user hoặc automation identity theo claims được tin | Session/token lộ, nhóm/quyền ánh xạ sai, offboarding chậm | MFA tại IdP, token TTL, claim policy, RBAC mapping |
| **Exec credential plugin** | kubectl chạy chương trình lấy token theo cấu hình | Kubeconfig độc hại thực thi chương trình tại máy người dùng | Chỉ tin kubeconfig/plugin được phê duyệt, file permissions, integrity |
| **X.509 client certificate** | Identity/nhóm trong cert theo CA/authn policy | Long-lived cert, private key lộ, thu hồi khó nếu không có chiến lược | Key custody, TTL/rotation, limited trust và RBAC |
| **ServiceAccount token** | Namespace/service-account identity | Token bị mount không cần thiết, RBAC quá rộng, Pod bị chiếm | Projected/short-lived tokens, audience/TTL, least privilege |
| **Webhook authentication** | Identity do external authenticator cung cấp | Authenticator thiếu HA, trust/bypass sai | TLS, audit, HA, strict identity mapping |
| **Cloud IAM-integrated authentication** | Cloud principal ánh xạ sang Kubernetes identity theo provider | Role cloud quá rộng, cluster access mapping sai | Least privilege IAM + Kubernetes RBAC, conditional access |

Không nên coi **user name trong kubeconfig** là identity được API server tin. Một kubeconfig context đặt tên tùy ý có thể dùng token/cert của một tài khoản khác; phải kiểm tra **credential thực và danh tính trả về từ cơ chế xác thực**.

### 6.2. MFA và short-lived credentials

Với human administrators, ưu tiên **central IdP/MFA và access lifecycle** khi hệ thống hỗ trợ:

- Người rời tổ chức hoặc đổi nhóm được **thu hồi quyền truy cập** kịp thời.
- Không phát tán **static admin tokens** qua chat, repository hoặc ticket.
- Dùng **short-lived access**; lưu refresh credentials theo chính sách bảo mật.
- Có **break-glass process** không phụ thuộc duy nhất vào một hệ thống IdP đã lỗi.
- Lưu **user attribution** theo từng thao tác; tránh dùng chung tài khoản “admin”.

Không thể chỉ bật MFA trên VPN rồi mặc định mọi yêu cầu API đều xác thực mạnh: một **CI token bị lộ** vẫn có thể gọi API qua đường được phép.

### 6.3. ServiceAccount tokens trong Pods

Pod có thể dùng Kubernetes API thông qua **ServiceAccount**. Trong nhiều cấu hình hiện đại, token có thể là **projected, bounded tokens** với audience và thời hạn thay vì một Secret token dài hạn được tự tạo theo kiểu legacy.

Hãy kiểm tra:

1. Pod có **thực sự cần Kubernetes API** hay không?
2. ServiceAccount được gắn có **RBAC tối thiểu** không?
3. Có cần tắt **automountServiceAccountToken** ở Pod hoặc ServiceAccount khi không dùng API không?
4. Token có **audience/expiration** phù hợp và được rotate theo nền tảng không?
5. Pod có quyền đọc token của workload khác qua volumes/host mounts không?
6. Khi Pod/namespace bị xóa hoặc workload bị compromise, đường **credential revoke và session response** là gì?

**Tắt automount** giúp giảm nguy cơ lộ token không cần thiết nhưng **không thay thế** kiểm soát quyền tạo Pod, đọc Secrets, mount volumes, exec hoặc dùng node credentials.

### 6.4. Anonymous authentication

Một API server có thể cho phép một số request được **gán anonymous identity** tùy cấu hình; authorization vẫn phải quyết định quyền của identity đó. Không nên để các role cho **system:anonymous/system:unauthenticated** có khả năng đọc dữ liệu nhạy cảm hoặc sửa tài nguyên.

Một số endpoint cần thiết cho health/discovery có thể có hành vi khác nhau theo phiên bản/config; **không tắt tùy tiện** nếu sẽ làm hỏng một thành phần cluster. Thay vào đó, kiểm tra **policy thực tế** và nguyên tắc không cấp quyền nhạy cảm cho anonymous identities.

## 7. RBAC: API reachable không có nghĩa request được phép

**Role-Based Access Control (RBAC)** là cơ chế authorization thường được dùng trong Kubernetes. Nó kiểm tra quyền dựa trên **verbs, apiGroups, resources/subresources, resourceNames và phạm vi namespace/cluster** theo rule hợp lệ.

### 7.1. Namespace Role và ClusterRole

| Đối tượng | Vai trò |
| --- | --- |
| **Role** | Tập quyền trong phạm vi namespace |
| **RoleBinding** | Gắn Role hoặc ClusterRole tới subject trong namespace |
| **ClusterRole** | Tập quyền đối với cluster-scoped resources, non-resource URLs hoặc có thể tái sử dụng trong namespace |
| **ClusterRoleBinding** | Gắn ClusterRole với subject ở phạm vi cluster |
| **Subject** | User, Group hoặc ServiceAccount được xác thực |

Một ClusterRoleBinding cấp **cluster-admin** cho ServiceAccount CI là phạm vi rất rộng. Dù CI runner chỉ reachable qua private endpoint, khi credential của runner bị chiếm, attacker vẫn có thể sử dụng quyền cluster-admin.

### 7.2. Ví dụ Role read-only theo namespace

~~~yaml
# Mẫu áp vào namespace demo-observe trong lab; không triển khai ngoài quyền.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployment-viewer
  namespace: demo-observe
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: bind-deployment-viewer
  namespace: demo-observe
subjects:
  - kind: ServiceAccount
    name: readonly-observer
    namespace: demo-observe
roleRef:
  kind: Role
  name: deployment-viewer
  apiGroup: rbac.authorization.k8s.io
~~~

Ví dụ trên **không tạo ServiceAccount**, không cấp quyền xem Secrets/Pods và không cho sửa Deployments. Đây là policy minh họa. Một pipeline thật có thể cần quyền riêng để rollout; không mở rộng bằng wildcard nếu có thể liệt kê chính xác các operations cần thiết.

### 7.3. Quyền nguy hiểm không chỉ là cluster-admin

Xem xét kỹ các quyền:

- **get/list/watch secrets**: có thể tiếp cận credentials trong namespace.
- **create/update pods, deployments, jobs, daemonsets**: có thể chạy workload và tác động service identities/mounts theo chính sách cluster.
- **pods/exec, pods/attach, pods/portforward**: mở rộng quyền tương tác với workload và đường kết nối.
- **create/update rolebindings/clusterrolebindings** hoặc quyền bind/escalate tương ứng: nguy cơ tăng quyền nếu policy cho phép.
- **impersonate** user/group/serviceaccount: có thể thực hiện request dưới identity khác trong phạm vi được ủy quyền.
- **nodes/proxy và các proxy/aggregation subresources**: cần xem tác động tới tài nguyên/node hoặc service phía sau.
- **create token via serviceaccounts/token**: có thể mint token cho một ServiceAccount được phép theo API và policy.
- **authorization webhook config, admission policies, CRDs/APIService**: thay đổi các tầng kiểm soát hoặc mở bề mặt mới.

Không phải mọi quyền này tự bảo đảm privilege escalation trong mọi cluster, nhưng chúng tạo **đường tác động mạnh** và phải được phân tích cùng Pod Security, admission, node permissions, IAM và trust boundaries.

### 7.4. Kubernetes NetworkPolicy không thay RBAC

NetworkPolicy có thể hạn chế **traffic tới/từ Pods** khi CNI hỗ trợ enforcement. Nó **không đồng nghĩa** một firewall tự động chặn public/private API server endpoint, và thường không kiểm soát đầy đủ **hostNetwork/control-plane endpoints** theo cách nhiều người hình dung.

Ngược lại, RBAC có thể chặn verb **delete secrets** nhưng không ngăn một client bị chiếm gửi nhiều kết nối làm nghẽn edge nếu chưa có network/load controls.

## 8. Admission: lớp kiểm soát sau authentication và authorization

**Admission controllers** giúp kiểm tra hoặc biến đổi resource requests tại API server theo rules của Kubernetes và loại operation. Chúng hữu ích để hạn chế các deployment làm mất an toàn, nhưng **không phải lớp thay cho RBAC**.

### 8.1. Các control thường quan tâm

| Control | Đối tượng | Điều cần hiểu |
| --- | --- | --- |
| **Pod Security Admission** | Pod security standards theo namespace labels/chính sách | Giảm privileged, host namespaces, unsafe capabilities tùy policy/mode |
| **ValidatingAdmissionPolicy** | Kiểm tra điều kiện resources theo khả năng phiên bản | Cần quản lý rule, parameter, matchConditions và failure behavior |
| **Validating/Mutating webhooks** | External services kiểm tra/biến đổi admission requests | TLS, authorization, network reachability, timeout, policy update/HA |
| **ResourceQuota / LimitRange** | Resource usage trong namespace | Hạn chế số lượng/cỡ workloads, không thay mọi anti-DoS API control |
| **Image/security supply-chain checks** | Admission extensions/engines khi được triển khai | Định nghĩa trusted registries, signatures và exception review |

### 8.2. Fail-open và fail-closed là quyết định nghiệp vụ

Nếu webhook **timeout**, tùy cấu hình failure policy, admission request có thể **được phép tiếp tục** hoặc **bị từ chối**. Mỗi lựa chọn có trade-off:

- **Fail-closed:** giữ enforcement khi webhook lỗi nhưng có thể làm deploy/scale/khôi phục dịch vụ thất bại.
- **Fail-open:** tăng khả năng tiếp tục deploy nhưng có thể nhận tài nguyên không được kiểm tra.

Policy nên phân loại **critical security checks**, webhook availability, namespace scope, cache/fallback và incident plan; không đặt ngẫu nhiên một chế độ cho tất cả.

### 8.3. Webhook network dependency

API server cần có đường tới webhook endpoint nếu webhook được cấu hình. Với private managed control plane, webhook chạy trong Pods hoặc dịch vụ bên ngoài có thể cần **route, DNS, TLS certificate, firewall/security group rules** chính xác.

Một endpoint API public khỏe **không chứng minh admission webhook healthy**. Kube-apiserver có thể xử lý request nhưng vẫn timeout khi gọi webhook, gây lỗi create/update. Vì vậy, có hai hướng kiểm chứng:

1. **Client/CI/node → Kubernetes API endpoint**.
2. **Kubernetes API server → admission/authentication/authorization webhook** và những dependencies tương ứng.

## 9. Những đường nhạy cảm bên trong Kubernetes API

Không phải mọi lời gọi API có rủi ro như nhau. Một lệnh list Deployments khác việc **exec vào Pod**, mở **port-forward**, thay **ClusterRoleBinding** hoặc deploy container privileged.

### 9.1. Exec, attach và port-forward

- **pods/exec** có thể cho phép chạy lệnh trong container với quyền process tương ứng.
- **pods/attach** có thể truy cập tiến trình tiêu chuẩn tương tác với container.
- **pods/portforward** tạo đường tới cổng trong Pod thông qua cơ chế Kubernetes API/kubelet path, không cần client có route trực tiếp tới Pod IP.
- **kubectl proxy** có thể cung cấp proxy HTTP tới API server tại máy vận hành; nếu bind ra địa chỉ ngoài ý định hoặc không có kiểm soát, nó có thể tạo đường API access không được mong muốn.

Những quyền này cần phân quyền/audit riêng. Đặc biệt, **port-forward có thể vượt qua kỳ vọng “không có network route trực tiếp từ laptop tới Pod”**, vì đường kết nối được trung gian qua Kubernetes API và các thành phần cluster.

### 9.2. API aggregation và CRDs

Kubernetes có thể mở rộng qua **CustomResourceDefinitions (CRDs)** và **API aggregation/APIService**. Các thành phần này tạo thêm kiểu tài nguyên hoặc backend APIs, với các yêu cầu riêng về authorization, TLS, availability và code security.

Không cấp quyền sửa APIService, cluster-wide admission/webhooks hoặc CRDs cho tất cả nhóm developer chỉ vì họ cần deploy ứng dụng trong một namespace.

### 9.3. Kubelet API khác Kubernetes API server

Kubelet trên node có các điểm giao tiếp riêng. Việc API server được bảo vệ tốt **không tự chặn trực tiếp kubelet endpoint** nếu node network/firewall đặt sai. Cần bảo vệ node management plane, kubelet authentication/authorization, chứng thư và cloud/host firewall độc lập.

### 9.4. Etcd và encryption at rest

**Etcd** có thể lưu dữ liệu nhạy cảm của Kubernetes, đặc biệt khi Secrets không được bảo vệ ở mức kỳ vọng. API server endpoint private vẫn không an toàn nếu etcd client/peer interfaces lộ cho người không có quyền.

Áp **etcd mTLS, private network isolation, backup encryption, RBAC/quyền host phù hợp và Kubernetes encryption at rest cho dữ liệu cần thiết**. Tính năng encryption at rest không tự thay bảo vệ network endpoint/credential.

## 10. NetworkPolicy, cloud firewall và segmentation

### 10.1. Control nào đang thực thi ở đâu?

| Lớp | Có thể kiểm soát | Không tự bảo đảm |
| --- | --- | --- |
| **Cloud firewall/SG/NSG** | Traffic theo IP/CIDR/port đến các network interfaces/endpoints trong phạm vi provider hỗ trợ | Kubernetes verbs, RBAC hoặc API server identity |
| **Private endpoint/VPC/VNet routing** | Ai có đường network tới API endpoint | User trong mạng private được quyền gì |
| **VPN/ZTNA/bastion** | Thiết bị/danh tính có đường quản trị | Token CI/Pod không bị lộ hoặc pod RBAC tối thiểu |
| **Kubernetes NetworkPolicy** | Pod ingress/egress theo labels/ipBlocks/ports nếu CNI enforce | Tất cả host-network/control-plane paths hoặc workload identity |
| **API server authn/authz** | User/group/service account nào được gọi verb/resource | L3/L4 packet flood/DoS hoàn toàn bị loại bỏ |
| **Admission/policy engine** | Resource creation/update có đáp ứng policy không | Người có quyền đọc không thể lộ thông tin qua các read APIs |
| **Firewall egress/policy for Pods** | Pod có thể mở kết nối tới endpoint nào theo enforcement | Service account token/mount hoặc DNS identity tự an toàn |

**NetworkPolicy behavior đối với traffic từ Pod tới API server** phụ thuộc CNI, endpoint path, kube-proxy/service routing, hostNetwork và phạm vi enforcement. Không nên khẳng định một rule NetworkPolicy sẽ chặn mọi cách truy cập control plane trên mọi cluster.

### 10.2. Pod-to-API egress

Một Pod có thể gọi Kubernetes API qua **kubernetes.default.svc** (Service IP) hoặc endpoint khác được cấu hình. Nếu workload không cần gọi API:

- Giới hạn **RBAC và token automount**.
- Xem xét **egress policy** tới Kubernetes API Service IP/endpoint theo CNI được triển khai.
- Kiểm tra Pod có thể tới **API endpoint public/private trực tiếp bằng IP/DNS khác** không.
- Không chặn nhầm **CoreDNS, CNI agents, monitoring, CSI/controller components** cần Kubernetes API để hoạt động.

**Pod NetworkPolicy không phải cơ chế duy nhất giảm rủi ro token theft**; nếu người tấn công lấy được token và gọi API từ một nơi khác reachable, cần danh tính/expiration/revocation phù hợp.

### 10.3. Egress từ API server

API server có thể cần gọi:

- Admission webhooks và aggregated API servers.
- Authn/authz webhooks hoặc external integrations.
- Etcd hoặc provider-managed dependencies qua network khác.
- Dịch vụ phục vụ metrics, tracing hoặc control-plane integrations tùy giải pháp.

Tùy platform, các đường này có **khả năng cấu hình khác nhau**. Một network rule quá chặt có thể bảo vệ ingress nhưng làm hỏng **control-plane-to-workload** traffic. Cần flow matrix hai chiều.

## 11. Managed Kubernetes: EKS, AKS và GKE

Các cloud providers quản lý nhiều thành phần control plane, nhưng **không thay trách nhiệm của người dùng** đối với IAM, endpoint exposure, private connectivity, workload access và logging. Chi tiết tính năng có thể thay đổi theo cluster mode, version, region và chính sách của provider; xác minh trạng thái thật trước khi sửa.

### 11.1. Amazon EKS

Trong những mô hình EKS thông dụng, endpoint access có thể được cấu hình theo **public, private hoặc cả hai**, với cách đặt public CIDR restrictions và đường kết nối nội bộ tùy cluster/network settings.

Cần xem:

- **Endpoint public/private access** đang bật thế nào và CIDR nào được ủy quyền.
- Admin/CI traffic sử dụng **DNS/route/public egress hay VPC private path**.
- **AWS IAM principals** có thể xác thực hoặc được gán quyền cluster thông qua cơ chế EKS access configuration nào.
- **Kubernetes RBAC** và quyền cloud IAM có tạo privilege escalation khi kết hợp không.
- **Control plane audit/API/authenticator logs** nào đã được bật/đưa tới hệ thống giám sát.
- Node groups, webhooks, DNS và private access có tiếp tục hoạt động sau change không.

**Không kết luận tắt public access luôn là thay đổi không gián đoạn**: runner hoặc admin ở bên ngoài VPC có thể mất đường nếu không có VPN/peering/transit/private DNS.

### 11.2. Azure Kubernetes Service (AKS)

AKS hỗ trợ các mô hình **API server public/private access** và những cơ chế kiểm soát network access theo tính năng/phiên bản; có thể có các lựa chọn **authorized IP ranges, private cluster, API server networking integration** trong các cấu hình phù hợp.

Cần kiểm tra:

- Cluster có public FQDN, private FQDN hay cả những tùy chọn khác trong môi trường cụ thể.
- **Private DNS zone, VNet linkage, VPN/ExpressRoute, UDR/NSG/Azure Firewall** liên quan đến API traffic.
- **Microsoft Entra ID/integrated authentication** và Kubernetes authorization model được áp.
- Runner/bastion và những người quản trị qua VPN có được **DNS + route + TLS + identity** đúng không.
- **Diagnostic settings/audit/metrics** được đẩy tới điểm giám sát nào.
- Control plane-to-webhook/network paths có bị chặn khi thay firewall không.

**Authorized IP ranges và private cluster** là những lựa chọn với phạm vi/hành vi riêng; không coi chúng luôn thay thế trực tiếp nhau mà không kiểm chứng.

### 11.3. Google Kubernetes Engine (GKE)

GKE có những cơ chế quản lý endpoint access/authorized networks/private control plane connectivity và **DNS-based endpoint access** tùy loại cluster và tính năng được bật.

Cần kiểm tra:

- Endpoint types nào đang khả dụng và thực sự bật.
- Private/public access, **authorized networks, IAM/OIDC/Google identity**, Kubernetes RBAC và các policy liên quan.
- Network path giữa nodes/Pods, admin/CI và control plane, bao gồm **private connectivity và DNS**.
- Kubernetes audit logs, cloud control-plane audit, metrics và retention.
- Những nguyên tắc về **VPC firewall rules, master/control-plane connectivity và webhooks** của cluster đang chạy.

Không áp cách tư duy **EKS subnet route table + AWS SG** cho GKE mà bỏ qua routing/firewall/endpoint model riêng của GCP.

### 11.4. So sánh trách nhiệm thay vì so tên menu

| Câu hỏi | EKS/AKS/GKE đều cần trả lời |
| --- | --- |
| Endpoint có public reachability không? | Bật/tắt public path, địa chỉ/DNS, source restrictions |
| Admin/CI đi tới endpoint bằng đường nào? | Public egress, private VPC/VNet, VPN/ZTNA/bastion |
| Ai có quyền xác thực? | IAM/IdP/credential integration được triển khai thực tế |
| Sau authentication có quyền gì? | Kubernetes RBAC và các cơ chế authorizer |
| Resource mutations được kiểm tra ra sao? | Admission webhooks/policies, Pod Security, governance |
| Control plane log lưu ở đâu? | Provider audit/log export, retention, SOC |
| Mất private DNS/VPN/provider API sẽ ra sao? | SLO, runbook, break-glass, HA |
| Node/webhook/operator traffic có an toàn không? | Control-plane-to-node/workload paths, TLS, firewall |

**Không đánh giá an toàn bằng một checkbox “Private cluster: true”.** Cần kiểm tra toàn bộ đường đi, privilege và telemetry.

## 12. Self-managed Kubernetes: bảo vệ listener và HA API servers

Trong self-managed clusters, đội vận hành chịu trách nhiệm trực tiếp với **kube-apiserver process, LB/listeners, serving certs, etcd connectivity, firewall, audit policy, patches và HA**.

### 12.1. Kiến trúc HA

~~~mermaid
flowchart LR
    A["Admin / kubelets / controllers"] --> V["Approved private endpoint + TLS LB"]
    V --> S1["kube-apiserver A"]
    V --> S2["kube-apiserver B"]
    V --> S3["kube-apiserver C"]
    S1 --> E["Etcd cluster / protected network"]
    S2 --> E
    S3 --> E
    V -. "Health/connection metrics" .-> M["SRE/SOC"]
    S1 -. "Audit/security metrics" .-> M
    S2 -. "Audit/security metrics" .-> M
    S3 -. "Audit/security metrics" .-> M
~~~

**Quorum và số lượng etcd members khác với số API server replicas**; không mặc định một sơ đồ ba API servers yêu cầu đúng ba etcd nodes trong mọi kiến trúc.

### 12.2. Các kiểm soát self-managed

1. **Bind/listen address** theo kiến trúc; không để listener quản trị ngoài mạng được phép.
2. **TLS server certificate** có SAN của endpoint DNS/IP và trusted CA đúng.
3. **Client authentication** không dựa trên anonymous access rộng hoặc token tĩnh chia sẻ.
4. **Authorization** theo RBAC/Node/webhook policy phù hợp, không để chế độ cho phép mọi request.
5. **Admission/security policies** cho resource mutations và tính toàn vẹn workload.
6. **Etcd endpoint isolation, mTLS, backup protection và encryption at rest**.
7. **Audit policy, log forwarding và metrics** có khả năng phục vụ điều tra.
8. **LB HA, health checks, rate/concurrency limits, endpoint failover**, theo tính năng được hỗ trợ.
9. **Patch/update strategy** cho API server, OS, runtime và các extensions.
10. **Backup/restore và break-glass**, thử trên staging, không chỉ lưu tài liệu.

### 12.3. Đừng tạo proxy không tương thích Kubernetes API

Kubernetes clients sử dụng **HTTP request/response, watch streams, long-running requests và cơ chế nâng cấp kết nối** cho một số API/subresources. Nếu đặt reverse proxy/L7 WAF phía trước:

- Phải hỗ trợ **HTTP streaming, connection upgrades, timeouts và request/body sizes** của Kubernetes API.
- Không làm hỏng **TLS identity, client certificate authentication** hoặc truyền identity sai khi terminate TLS.
- Không log raw Authorization headers, kubeconfigs, request bodies chứa Secrets.
- Không áp một policy WAF chung khiến watch/logs/exec/port-forward bị cắt hoặc chặn nhầm.
- Hiểu LB health check và mối quan hệ với API server readiness.

**Thêm WAF không phải thay thế** Kubernetes authn/authz; nếu terminate TLS tại proxy thì đây là thay đổi trust boundary phải được thiết kế chặt.

## 13. API endpoint availability và resource exhaustion

Control plane không chỉ cần giữ bí mật và quyền mà còn phải **sẵn sàng**. Flood các request API, watch/list lớn, expensive authorization/admission calls, webhook timeout hoặc lỗi etcd có thể làm API server chậm và ảnh hưởng cluster operations.

### 13.1. Những nguồn tải

| Nguồn | Hiệu ứng có thể xảy ra | Cách quản trị |
| --- | --- | --- |
| **Nhiều clients GET/LIST/WATCH** | CPU/memory, response encoding, watch cache pressure | Client throttling, API Priority and Fairness, quota theo policy |
| **Controllers lỗi retry** | Request storm khi API/etcd chậm | Exponential backoff, client QPS/burst hợp lý, fix controller |
| **Admission webhook chậm** | Create/update bị treo hoặc từ chối theo failure policy | Webhook HA, timeout, latency metrics, scoped matching |
| **Etcd latency/unhealthy** | API request/consistency operations chậm | Etcd HA, storage performance, backups, metrics |
| **Large API objects/requests** | Memory, parsing, admission và storage pressure | Resource limits, API validation, request size controls |
| **Unauthorized network flood** | TLS/connection/edge exhaustion trước RBAC | Network ACL, load/DoS controls, segmentation |
| **Node reconnect bursts** | Nhiều kubelet/client reconnect khi control plane phục hồi | HA/LB, network stability, restart/backoff policies |

### 13.2. API Priority and Fairness (APF)

Kubernetes hỗ trợ cơ chế **API Priority and Fairness** trong các phiên bản phù hợp nhằm phân bổ concurrency/queueing theo loại request và identity/classification; mục tiêu là hạn chế **một nhóm request chiếm toàn bộ năng lực phục vụ**.

Tuy nhiên:

- APF **không thay network ACL hoặc chống volumetric DDoS** trước khi request tới apiserver.
- Cần bảo vệ request quan trọng như **node/control-plane operations** và tránh starvation.
- Sai cấu hình flow schemas/priority levels có thể chặn nhầm workload quan trọng.
- Không tùy tiện chỉnh ngưỡng để “tăng throughput” khi bottleneck thực là etcd hoặc webhook.

### 13.3. Watch streams và long-running requests

Một số Kubernetes clients dùng **watch** để theo dõi tài nguyên và duy trì kết nối lâu dài. Nếu proxy đặt total timeout quá thấp, controllers có thể liên tục reconnect, tăng tải.

Mặt khác, nếu không có **connection/stream limits**, nhiều kết nối lâu có thể giữ FD/memory. Cần phân biệt **idle timeout, total deadline, HTTP/2 streams, watch timeout và application cancellation**; không áp một giá trị duy nhất cho mọi request.

### 13.4. Availability là một phần của security

Một outage API server có thể khiến:

- Không thể sửa Deployment hoặc rotate Secrets theo kế hoạch.
- Cluster operators không được phép phát hành thay đổi khắc phục.
- Node mới không đăng ký được, autoscaling/rolling updates gặp khó.
- Admission webhook hoặc controller loops bị ảnh hưởng gián tiếp.

**Workloads hiện có có thể tiếp tục chạy trong một số tình huống**, nhưng không nên khẳng định toàn cluster vẫn hoạt động bình thường khi API server không thể phục vụ. Cần runbook phục hồi có tính đến **quorum, backups, node operations và kubelet behavior**.

## 14. Audit logs: biết ai gọi API và kết quả gì

Kubernetes cung cấp cơ chế **audit** để ghi nhận hoạt động của API server theo audit policy và backend được cấu hình. Trên managed clusters, cách bật/export log phụ thuộc provider.

### 14.1. Sự kiện quan trọng

| Event | Vì sao đáng chú ý |
| --- | --- |
| **Tạo/sửa ClusterRoleBinding** | Thay quyền truy cập cluster, có thể cấp quyền quản trị |
| **Thay Role/RoleBinding** | Mở rộng quyền ở namespace |
| **Đọc/list Secrets bất thường** | Có thể cho thấy credential access hoặc tooling sai |
| **Pods/exec, pods/attach, pods/portforward** | Tương tác vào workload hoặc mở đường tới cổng trong Pod |
| **Tạo Pod privileged/hostNetwork** | Có thể làm tăng bề mặt host/network |
| **Thay admission policies/webhooks** | Bật/tắt hoặc thay lớp guardrails |
| **Cập nhật ConfigMaps/Secrets quản trị** | Có thể làm thay cấu hình nhạy cảm |
| **Request anonymous / 401 / 403 tăng đột biến** | Sai cấu hình client, scanning hoặc credential issue |
| **Thay access configuration cloud** | Endpoint public/private, authorized ranges/IAM access drift |
| **APIService/CRD bất thường** | Có thể tạo bề mặt API mới hoặc làm suy giảm API availability |

### 14.2. Audit policy và dữ liệu nhạy cảm

Kubernetes audit có các **levels** với độ chi tiết khác nhau theo rule; khi ghi request/response bodies, log có thể chứa **Secrets hoặc thông tin nhạy cảm**. Không bật ghi toàn bộ nội dung mọi request trên production mà không đánh giá **data minimization, storage quota, retention và RBAC cho log**.

Một hướng thiết kế:

- Metadata events cho các activity cần giám sát rộng.
- Chi tiết cao hơn cho các thay đổi quản trị có giá trị điều tra, nhưng **loại trừ dữ liệu nhạy cảm** phù hợp.
- Gửi log tới backend có **integrity/retention**, phân quyền theo vai trò.
- Ghi cả **cloud control-plane audit** cho các thay đổi nằm ngoài Kubernetes API.

### 14.3. Nên tương quan các lớp

~~~text
Client IP / VPN session / CI runner
  -> Cloud firewall / LB / private endpoint flow
  -> Kubernetes API audit (user, groups, verb, resource, response)
  -> Admission webhook / policy outcome (nếu áp dụng)
  -> Controller / node / workload logs

Mục tiêu: kết nối được actor -> request -> authorization -> effect.
~~~

Một log có user **system:serviceaccount:demo:deploy-bot** không tự cho biết ai trong tổ chức đã kích hoạt CI job. Cần correlate **CI pipeline ID, source commit, workflow approver và cloud IAM/session events**.

### 14.4. Mẫu normalized audit event

~~~json
{
  "caseId": "K8S-CP-009",
  "timestamp": "2026-11-28T06:30:00Z",
  "cluster": "demo-cluster",
  "sourceCategory": "ci-runner",
  "user": "system:serviceaccount:demo:deploy-bot",
  "verb": "create",
  "resource": "deployments",
  "namespace": "demo",
  "responseCode": 201,
  "networkPath": "approved-private-access",
  "policyOutcome": "authorized-and-admitted",
  "requestCorrelationId": "req-demo-009",
  "secretMaterialRecorded": false
}
~~~

Đây là **schema minh họa**, không phải dữ liệu gốc được Kubernetes tự tạo. Những trường **networkPath, policyOutcome, secretMaterialRecorded** yêu cầu hệ thống tổng hợp/đánh giá; không tự xuất hiện trong mọi audit backend.

## 15. Threat model: những sai cấu hình và đường tấn công điển hình

Một endpoint an toàn cần chống cả truy cập trái phép, lạm dụng quyền **sau khi xác thực**, suy giảm khả dụng và thay đổi đường kết nối không được phê duyệt.

| Threat / sai sót | Điểm tác động | Hậu quả có thể xảy ra | Controls và evidence |
| --- | --- | --- | --- |
| **Public API exposure ngoài chủ đích** | Endpoint access / LB / firewall | Tăng bề mặt scan, credential attempts hoặc resource exhaustion | Endpoint inventory, authorized ranges, cloud audit, external reachability test được phép |
| **Allowlist bị mở quá rộng** | CIDR 0.0.0.0/0, ::/0 hoặc NAT chung | Bất kỳ nguồn có route đều có thể tới TLS endpoint | Strict source policy, IPv4/IPv6 test, approvals, drift alert |
| **Kubeconfig/token lộ qua repository** | Developer laptop, CI artifact, backup | Kẻ có network path có thể gọi API dưới identity bị lộ | Secret scanning, short TTL, revoke/rotate, audit |
| **Kubeconfig exec plugin độc hại** | Máy của người quản trị | Có thể thực thi chương trình trên máy người mở kubeconfig | Trusted origin, file review, signing/integrity, endpoint/credential controls |
| **Cluster-admin cấp cho runner** | RBAC/IAM integration | CI compromise có thể điều khiển toàn cluster | Scoped Roles/Bindings, dedicated identities, pipeline approvals |
| **ServiceAccount token không cần thiết** | Pod filesystem/environment | Pod bị chiếm có thêm API credential | Disable automount khi không dùng, minimal RBAC, projected token |
| **RBAC role escalation** | RoleBinding/ClusterRoleBinding hoặc quyền bind/escalate | Mở rộng quyền ngoài intended role | Least privilege, approval, RBAC diff, audit alerts |
| **Anonymous identity có quyền rộng** | API authentication/authorization | Đọc/sửa tài nguyên không cần credential | Review anonymous authorization, negative tests |
| **TLS validation bị tắt** | kubectl/SDK/kubeconfig | Có thể chấp nhận API endpoint giả và lộ credential | CA/SAN verification, no insecure skip, PKI lifecycle |
| **DNS private endpoint sai** | Split DNS, VPN, resolvers | Kết nối tới nhầm public endpoint hoặc outage | DNS answers, route lookup, TLS identity, DNS change audit |
| **NetworkPolicy được hiểu sai** | Pod-to-API egress/host networking | Pod vẫn gọi API qua đường khác dù nghĩ đã chặn | CNI capability tests, enforce at correct network hop |
| **Admission webhook fail-open** | Resource create/update | Resource không đạt security policy vẫn được chấp nhận | Failure-policy review, HA, policy logs và tests |
| **Admission webhook fail-closed nhưng unavailable** | API write path | Không deploy/scale/khắc phục được | Webhook HA, timeouts, runbook, controlled failover |
| **API server flood/watch churn** | API Priority and Fairness/LB/etcd | API chậm, controllers reconnect, service recovery lỗi | APF metrics, rate/concurrency budgets, load tests có quyền |
| **API server certificate hết hạn** | TLS ingress hoặc LB | Nhiều client không xác minh được endpoint | Expiry monitoring, rotation canary và rollback |
| **Etcd/kubelet exposed** | Control-plane adjacent surfaces | Xâm phạm trạng thái cluster hoặc node ngoài API policy | Private network, TLS, host/cloud firewall, access inventory |
| **Cloud IAM endpoint tampering** | EKS/AKS/GKE control plane configuration | Đổi public/private access, vượt giới hạn admin path | IAM least privilege, configuration audit, IaC guardrails |
| **Port-forward/exec lạm dụng** | Kubernetes API subresources | Tiếp cận Pod/service ngoài route client trực tiếp | RBAC subresource restrictions, audit, alert |
| **Secret logging** | Audit policy, proxy, debugging | Token, client auth headers hoặc Secret bodies lộ | Metadata-level logs, redaction, RBAC/retention |
| **Break-glass không kiểm thử** | Recovery process | Mất quyền quản trị khi IdP/DNS/VPN outage | Secure emergency credential, test, monitoring, approvals |

### 15.1. Cần phân biệt ba hệ quả

- **Attack surface:** endpoint reachable hay các verbs nguy hiểm đã được cấp.
- **Policy violation:** principal được cấp quyền quá rộng, public range mở sai hoặc log nhạy cảm lộ ra.
- **Confirmed compromise:** có bằng chứng một actor đã xác thực/được ủy quyền và thực hiện hành động trái phép.

Không kết luận cluster đã bị chiếm chỉ vì public API trả một TLS handshake. Ngược lại, một token bị lộ dù chưa thấy audit event xấu vẫn cần **điều tra và xử lý theo mức độ rủi ro**.

## 16. Xây dựng baseline bảo mật theo các lớp

Một security baseline có thể chia thành các tầng trách nhiệm:

~~~mermaid
flowchart TD
    P["1. Cloud IAM + Kubernetes administrators"] --> N["2. Public/private endpoint + DNS/route/firewall"]
    N --> T["3. TLS server validation + credential hygiene"]
    T --> A["4. Kubernetes authentication + RBAC"]
    A --> V["5. Admission/security policies + workload controls"]
    V --> D["6. API audit, cloud audit, network flow, monitoring"]
    D --> R["7. Rotation/incident response/HA/break-glass"]
~~~

| Lớp | Yêu cầu tối thiểu | Chủ sở hữu điển hình |
| --- | --- | --- |
| **Cloud account/IAM** | Quyền thay endpoint, IAM access mapping, cluster configuration hạn chế | Cloud platform/IAM |
| **Network ingress** | Chỉ nguồn cần thiết tới API, private path nếu chọn, DNS/route/IPv6 rõ | Network platform/security |
| **TLS/PKI** | Server identity verification, CA trust, expiry monitoring | PKI/SRE |
| **Human/CI credentials** | MFA, short-lived access, JIT/conditional access, no shared admin tokens | IAM/DevOps |
| **Kubernetes RBAC** | Least privilege theo namespace/resource/verb; bảo vệ privileged subresources | Cluster security |
| **Admission/workload security** | Guardrails với elevated Pods, webhooks, image policies và security standards | Platform/AppSec |
| **Audit/monitoring** | API request metadata, RBAC changes, cloud endpoint drift, error/latency metrics | SOC/SRE |
| **Recovery** | HA, backup, break-glass, runbook và test outage | SRE/Incident response |

### 16.1. Nên quản trị bằng policy-as-code

Một tài liệu policy minh họa có thể trông như:

~~~yaml
# Mẫu kiểm soát nghiệp vụ, không phải schema của EKS/AKS/GKE hay Kubernetes.
control_id: K8S-CONTROL-PLANE-009
cluster: "demo-cluster"
environment: "production"
endpoint:
  exposure: "private"
  approved_admin_paths:
    - "managed VPN / ZTNA"
    - "isolated CI runners in approved network"
  public_endpoint_allowed: false
  ipv4_and_ipv6_review_required: true
  dns_and_tls_validation_required: true
identity:
  human_admin: "federated IdP + MFA + JIT when supported"
  automation: "dedicated workload identity, short-lived credential"
  shared_admin_credentials: "not permitted"
authorization:
  default: "least privilege"
  cluster_admin: "break-glass or explicitly approved roles only"
  protect_sensitive_verbs:
    - "get/list/watch secrets"
    - "create/update rolebindings"
    - "pods/exec and pods/portforward"
admission:
  webhook_failure_mode: "review per policy severity"
  require_pod_security_baseline: true
observability:
  api_audit: "enabled and exported with data minimization"
  cloud_endpoint_changes: "alert"
  anonymous_or_denied_access_spikes: "alert"
  certificate_expiry: "alert"
recovery:
  private_access_outage: "documented and tested"
  break_glass: "limited, protected, audited"
owner: "Kubernetes Platform + Security"
~~~

Không triển khai mẫu này như YAML Kubernetes resource. **Nó là checklist để chuyển thành policies thật** theo provider, phiên bản Kubernetes và công cụ IaC.

### 16.2. Kiểm soát thay đổi

Các thay đổi sau nên được đưa vào **security review/change process**:

- Từ private endpoint sang public hoặc thay danh sách authorized IP/CIDR.
- Thêm máy quản trị, CI runner, VPN route hoặc trust VPC/VNet mới.
- Thay **ClusterRole, ClusterRoleBinding** hoặc service account được cấp quyền mạnh.
- Thay OIDC issuer, group claims, cloud IAM cluster access entries/mappings.
- Thêm sửa **admission webhooks, APIService, authorization webhooks**.
- Rotate **API server CA/serving cert** hoặc thay endpoint DNS.
- Thay **control plane audit policy**, log destinations hoặc retention.
- Chỉnh API Priority and Fairness, proxy timeouts/limits hoặc HA LB.

**Terraform/Helm/apply success không chứng minh policy được thực thi đúng**. Cần test chính nguồn, danh tính và verb/endpoint đang bảo vệ.

## 17. Kiểm tra Kubernetes API mà không ghi đè cấu hình

Trong quy trình vận hành, nên bắt đầu từ **lệnh đọc trên cluster đã được cấp quyền**. Không cần tạo workload privileged, sửa firewall hay dùng kỹ thuật vượt xác thực để kiểm tra trạng thái endpoint.

### 17.1. Xem context và endpoint hiện tại

~~~bash
# Chỉ sử dụng kubeconfig/context được cấp quyền.
kubectl config current-context

# Xem server URL của context đang chọn.
kubectl config view --minify \
  -o jsonpath='{.clusters[0].cluster.server}'

# Xem kết quả xác thực/authorization theo quyền hiện tại.
kubectl auth can-i get deployments -n demo
kubectl auth can-i list secrets -n demo
kubectl auth can-i create clusterrolebindings

# Kiểm tra API server reachable và trạng thái phù hợp nếu được cấp quyền.
kubectl cluster-info
kubectl get --raw='/readyz'
~~~

**Không chạy kubectl config view --raw để dán output vào ticket/chats**: tùy kubeconfig, output thô có thể chứa **tokens, client keys hoặc dữ liệu chứng thực**. Các lệnh xem endpoint/permissions phía trên không phải cách chứng minh người khác không có quyền; chỉ kiểm tra **credential/context đang sử dụng**.

### 17.2. Kiểm tra RBAC trong phạm vi đọc được

~~~bash
# Read-only: cần quyền list tương ứng, không dùng trên cluster không sở hữu.
kubectl get clusterroles
kubectl get clusterrolebindings
kubectl get roles -n demo
kubectl get rolebindings -n demo

# Kiểm tra service account identity và policy trong namespace.
kubectl get serviceaccounts -n demo
kubectl get networkpolicies -n demo

# Xem các admission configurations nếu được phân quyền.
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
~~~

Sự hiện diện của một ClusterRoleBinding có tên “admin” **không tự cho biết ai đang được cấp quyền cụ thể** nếu chưa xem subjects và roleRef. Không nên chỉ đọc tên object.

### 17.3. Kiểm tra các dấu hiệu API extensions và resource pressure

~~~bash
# Chỉ đọc danh sách resource khi có quyền.
kubectl get apiservices
kubectl get customresourcedefinitions

# APF resources theo khả năng/phiên bản Kubernetes.
kubectl get flowschemas
kubectl get prioritylevelconfigurations

# Trạng thái nodes; không phải bằng chứng đầy đủ về API server HA.
kubectl get nodes -o wide
~~~

Các lệnh có thể trả **Forbidden** vì RBAC; đó là phản hồi hợp lệ theo thiết kế, không tự có nghĩa cluster lỗi. Một tài khoản ít quyền **không nên được nâng quyền chỉ để chạy checklist read-only**. Có thể nhờ operator có quyền xuất **metadata đã kiểm soát**.

### 17.4. Readiness không đồng nghĩa đầy đủ security

**/readyz** hoặc lệnh cluster-info cho thấy khả năng phục vụ theo điều kiện cụ thể, nhưng:

- Không chứng minh endpoint private hay có allowlist đúng.
- Không kiểm tra RBAC của mọi principal.
- Không khẳng định audit logging đang bật hoặc không lộ Secrets.
- Không xác minh routes của mọi nodes/CI/webhooks.
- Không kiểm thử failover, expiry, IdP outage.

Health checks là tín hiệu vận hành, cần kết hợp **control-plane config + network path + identity + audit**.

## 18. Kiểm tra TLS và network path theo cách được phép

### 18.1. Xác định FQDN/port rồi kiểm tra đúng hostname

Một phép kiểm thử trong mạng đã được ủy quyền có thể xác minh TLS endpoint:

~~~bash
# Ví dụ dùng FQDN và CA của lab, không áp dụng cho cluster khác.
# internal-k8s-ca.pem là file CA certificate đã được phê duyệt.
openssl s_client \
  -connect k8s-api.example.test:6443 \
  -servername k8s-api.example.test \
  -verify_hostname k8s-api.example.test \
  -verify_return_error \
  -CAfile internal-k8s-ca.pem
~~~

**-servername** gửi SNI; **-verify_hostname** kiểm tra server identity; **-CAfile** cung cấp trust anchor dự kiến. Nếu đường đi qua private DNS hoặc proxy, phải chạy test từ đúng network zone. Không dùng **-k/insecure** hoặc tắt server verification để “pass” kết quả.

### 18.2. Triệu chứng và lớp cần kiểm tra

| Triệu chứng | Những khả năng cần xét | Evidence |
| --- | --- | --- |
| **DNS NXDOMAIN/không resolve** | Private zone, resolver forwarding, DNS link, record lỗi | DNS answers tại admin/CI/node và DNS change log |
| **TCP connect timeout** | Route, SG/NSG/firewall, VPN, ACL, wrong endpoint address | Effective route, flow logs, approved source IP |
| **TLS unknown authority** | CA trust sai, kubeconfig khác cluster, TLS interception | Chain, issuer, fingerprint, kubeconfig CA metadata |
| **TLS hostname mismatch** | SAN/FQDN sai hoặc client vào endpoint khác | Server URL, SAN, DNS, LB listener |
| **HTTP 401** | Không có credential hoặc credential không hợp lệ | Authn logs, token expiry, IdP/session state |
| **HTTP 403** | Không được phép theo authorizer/policy | User/group/verb/resource, RBAC/webhook logs |
| **API timeout sau TCP/TLS thành công** | API server overloaded, etcd chậm, admission webhook lỗi | Apiserver metrics, etcd, admission latency, APF |
| **Chỉ kubectl từ laptop lỗi** | VPN/DNS/IdP/context/local kubeconfig | Laptop route, VPN egress, local credential |
| **Nodes không register** | Node-to-API private path, cert/bootstrap, cloud network ACL | Kubelet logs, node network path, API auth events |
| **CI không deploy sau private change** | Runner nằm ngoài private network, DNS không resolve, token sai | CI source network, route, endpoint flags, audit |

### 18.3. Đường network có thể khác giữa nguồn

Khi kiểm thử private endpoint, không chỉ chạy từ laptop của một admin đang VPN. Cần các góc nhìn:

1. **Managed admin device qua VPN/ZTNA**.
2. **Bastion/jump host ở management subnet**.
3. **CI runner thật**, không phải runner giả định cùng network.
4. **Node/kubelet** nếu nguồn đó phụ thuộc endpoint đã thay.
5. **Control plane → webhook/service backend**, khi provider hỗ trợ quan sát.
6. **Các vùng dự phòng/availability zones** và trường hợp failover.

Một nguồn kết nối được không chứng minh toàn bộ cluster vận hành tốt sau khi sửa mạng.

## 19. Case study 1: public endpoint mở rộng sau thay đổi CI

### 19.1. Bối cảnh giả định

Cluster production có public Kubernetes API endpoint nhưng chỉ cho **public IP egress của VPN và CI runners**. Sau khi chuyển CI sang managed runners có IP thay đổi, pipeline bị timeout. Một nhân viên sửa endpoint CIDR thành **0.0.0.0/0** để triển khai chạy lại rồi quên khôi phục.

### 19.2. Evidence

| Dấu hiệu | Quan sát | Điều cần xác định |
| --- | --- | --- |
| **Cloud audit** | Actor thay authorized ranges từ danh sách hẹp sang 0.0.0.0/0 | Có ticket/phê duyệt và thời điểm hiệu lực không? |
| **Endpoint config** | Public path reachable từ nhiều nguồn | Phạm vi public IPv4/IPv6 hiện tại là gì? |
| **CI logs** | Deploy thành công sau change | Không chứng minh change an toàn |
| **API audit** | Có thêm 401/403 từ nguồn không quen thuộc | Scan, misconfiguration hay attempt đáng ngờ? |
| **RBAC review** | CI identity có quyền rộng trong cluster | Khi CI token lộ, blast radius ra sao? |
| **Flow/edge logs** | Tăng request tới API endpoint | Cần tách traffic hợp lệ với abuse |

Không được suy rằng **0.0.0.0/0 tự làm cluster bị compromise**; có thể có RBAC/identity chặn mọi thay đổi. Nhưng đây là **mở rộng bề mặt network** và cần xử lý ngay theo policy.

### 19.3. Khôi phục và phòng ngừa

1. Ghi **change record, cloud principal, endpoint setting trước/sau, thời điểm**.
2. Đánh giá CI runner hiện dùng **egress IP nào**, liệu có thể dùng **private runners/VPC connectivity**.
3. Khôi phục **restricted CIDRs hoặc private endpoint** theo kiến trúc đã phê duyệt; không gây mất đường khẩn cấp quản trị.
4. Kiểm tra **MFA/IdP, CI credential TTL và Kubernetes RBAC**; thu hẹp quyền CI nếu quá rộng.
5. Phân tích API audit/flow logs từ thời điểm mở rộng để tìm **unknown principals, unusual verbs, Secrets access và RBAC changes**.
6. Bổ sung IaC/policy-as-code chặn **unapproved 0.0.0.0/0 và ::/0** ở public endpoint.
7. Chạy **positive test** từ runner/managed admin và **negative test** từ nguồn ngoài allowlist được ủy quyền.

**Bài học:** một thay đổi vì khả dụng CI có thể vô tình thay security boundary. Chọn **network access ổn định cho automation**, không giải quyết bằng public allow-all vĩnh viễn.

## 20. Case study 2: ServiceAccount token bị lộ trong Pod

### 20.1. Bối cảnh giả định

Một Pod xử lý dữ liệu web không cần Kubernetes API. Do mặc định cấu hình, Pod có service account token mount. ServiceAccount dùng chung cho nhiều Deployments và bị cấp quyền **list Secrets, create Pods** rộng trong namespace. Kẻ tấn công khai thác lỗi ứng dụng để đọc filesystem của container.

### 20.2. Tại sao private control plane không giải quyết đủ?

Từ bên trong cluster, Pod có thể có đường tới API service hoặc private endpoint theo cấu hình. Nếu token có quyền, **private endpoint có thể được gọi từ một nguồn không đáng tin dù Internet direct access bị chặn**.

~~~mermaid
flowchart LR
    X["Pod web bị xâm nhập"] --> T["Mounted ServiceAccount token"]
    T --> P["Kubernetes API reachable trong cluster"]
    P --> R["RBAC decisions"]
    R --> S["Resources trong phạm vi role được cấp"]
    T -. "Giảm rủi ro" .-> C["No token nếu không cần + minimal RBAC + Pod hardening"]
~~~

### 20.3. Điều tra và xử lý

| Giai đoạn | Hành động | Evidence |
| --- | --- | --- |
| **Identify** | Xác định Pod, ServiceAccount, namespace, role bindings và token exposure | Pod spec, SA metadata, RBAC diff |
| **Contain** | Cô lập workload bị chiếm theo IR; ngừng sử dụng credential có nguy cơ bị lộ | Network/Pod state, incident record |
| **Scope** | Tìm API audit events của ServiceAccount, đặc biệt Secrets reads, Pods create và RBAC changes | User identity, sourceIPs, verb/resource, timestamps |
| **Recover** | Thay workload/image, credential policy và thu hẹp RBAC; kiểm tra token rotation/revocation theo hệ thống | Deployment revision, role changes, validation |
| **Prevent** | Tắt token automount nơi không cần; cấp SA riêng từng workload và egress policy phù hợp | Admission/policy-as-code, positive/negative tests |

**Xóa Pod hoặc thay token không phải lúc nào cũng đủ** nếu attacker đã lấy những Secrets khác, tạo resources mới hoặc truy cập cloud IAM qua workload identity. Cần kiểm tra **persistence, lateral movement và downstream credentials** theo bằng chứng.

### 20.4. Bài học

**Network segmentation và Kubernetes RBAC phải kết hợp**: private endpoint làm giảm Internet attack surface, còn least privilege ngăn một Pod credential biến thành cluster admin khi Pod bị khai thác.

## 21. Case study 3: chuyển sang private endpoint khiến CI và node lỗi

### 21.1. Bối cảnh

Một cluster được chuyển từ public endpoint có allowlist sang **private-only API**. Đội quản trị đã kiểm tra kubectl từ bastion trong VPC thành công, nhưng pipeline ngoài cloud không còn deploy được. Ở một zone khác, một số worker nodes sau khi thay mới cũng không register được.

### 21.2. Chuỗi điều tra

~~~text
Expected:
  Admin bastion   -> private API endpoint: OK
  CI runner       -> approved private path: OK
  Worker nodes    -> provider-supported node/control plane path: OK

Observed:
  Bastion         -> OK
  CI runner       -> DNS resolves private address, no private route
  New nodes       -> bootstrap or network path fails in one subnet/zone
~~~

### 21.3. Các bước

1. Xác minh **endpoint configuration** và thời điểm thay đổi từ cloud audit.
2. So sánh **DNS answers** tại bastion, CI runner, các node subnets và on-prem.
3. Kiểm tra **effective routes, VPN/transit, SG/NSG/firewall và return path** cho từng nguồn.
4. Đối chiếu node **bootstrap credentials, TLS trust và kubelet logs** trước khi quy mọi lỗi về route.
5. Kiểm tra **webhook/control-plane-to-workload paths** không bị ảnh hưởng gián tiếp.
6. Chọn giải pháp đúng: **private CI runners hoặc dedicated private connectivity**, sửa DNS/route/firewall theo scope.
7. Nếu cần rollback public access tạm thời, phải có **hạn chế CIDR, approval, TTL, audit và kế hoạch đóng lại**, tránh mở all sources.
8. Kiểm tra failover/multi-zone, để việc một bastion kết nối được không che lỗi ở subnet khác.

### 21.4. Bài học

**Private control plane an toàn về hướng truy cập Internet không có nghĩa nó tự reachable đối với mọi client được phép.** Đường node, CI, bastion và webhook cần được thiết kế/vận hành cùng DNS và route.

## 22. Case study 4: admission webhook làm control plane chậm

### 22.1. Bối cảnh

Một cluster dùng **ValidatingAdmissionWebhook** để kiểm tra hình ảnh container và Pod Security policy. Sau khi thay webhook service/network, request create Deployment thường bị treo hoặc trả lỗi. API server vẫn nhận GET và một số read requests bình thường, khiến đội vận hành tưởng DNS/endpoint client đã hoàn toàn khỏe.

### 22.2. Phân biệt đường vào và đường ra

- **kubectl → API server:** TLS/connect/authentication vẫn hoạt động.
- **API server → webhook:** DNS/route/TLS/Service/endpoint có thể lỗi.
- **Webhook → backend/policy service:** có thể chậm hoặc không khả dụng.
- **API admission decision:** tùy failurePolicy và timeout, request bị reject hoặc đi tiếp.

### 22.3. Dữ liệu cần thu

| Evidence | Câu hỏi |
| --- | --- |
| **Admission webhook configuration** | Service/URL, match rules, timeoutSeconds, failurePolicy, caBundle đúng không? |
| **API server metrics/events** | Admission latency/error/throttle tăng từ khi nào? |
| **Webhook endpoint health** | Service endpoints/Pods có sẵn sàng và TLS đúng không? |
| **Network path** | Control plane có tới Pod/service webhook theo provider network constraints không? |
| **Change record** | Có đổi namespace, CA, DNS, CNI/firewall hay policies? |
| **Audited requests** | Request nào được admit/deny, resource nào bị ảnh hưởng? |

### 22.4. Biện pháp

1. Xử lý **dependency health và route/TLS** của webhook trước.
2. Cân nhắc **HA replicas, readiness, timeout và narrow match rules**.
3. Đánh giá **fail-open/fail-closed** cùng nhóm security và owner, không tự tắt security webhook cho toàn cluster.
4. Kiểm thử **resource hợp lệ được chấp nhận, resource vi phạm bị từ chối**, và failure behavior đúng.
5. Ghi recovery/fallback strategy để không bị khóa khả năng sửa một cluster đang gặp sự cố.

**Bài học:** bảo vệ endpoint còn gồm những **dependencies mà API server phải gọi**; firewall quá chặt có thể biến một security control thành nguyên nhân outage.

## 23. Case study 5: port-forward đi vòng đường client-to-Pod thông thường

### 23.1. Bối cảnh

Một data service không có public LoadBalancer và không cho laptop routing tới Pod CIDR. Đội bảo mật nghĩ rằng như vậy không ai bên ngoài data subnet có thể mở kết nối đến port quản trị của Pod. Tuy nhiên, một nhóm operator được cấp **pods/portforward** để debug.

**Port-forward thông qua Kubernetes API** có thể cung cấp đường kết nối được trung gian bởi control plane/node, không cần laptop có route trực tiếp tới Pod IP. Điều này không có nghĩa port-forward tự vượt RBAC; chính **quyền RBAC** là cổng kiểm soát.

### 23.2. Kiểm soát

- Cấp **pods/portforward** theo nhiệm vụ và namespace, không mặc định cho mọi developer.
- Bảo vệ **kubeconfig/IdP/MFA** và chỉ cho truy cập API từ nguồn đã phê duyệt.
- Ghi **audit events** của portforward và correlating logs trong phạm vi quan sát được.
- Yêu cầu ứng dụng/DB vẫn có **authentication/authorization**, không giả định “chỉ private Pod CIDR” là đủ.
- Nếu dữ liệu rất nhạy cảm, cân nhắc **JIT operator access** hoặc service-specific debug gateways có kiểm soát.

### 23.3. Giới hạn kết luận

Không thể suy rằng một Pod port reachable qua port-forward có nghĩa network policy bị bypass theo cùng ngữ nghĩa ở mọi CNI; cần xem **Kubernetes API tunnel/control-plane path và enforcement thực**. Quan trọng nhất là **threat model không được chỉ xét direct client-to-Pod routing**.

## 24. Runbook ứng phó khi control plane endpoint có dấu hiệu bị lạm dụng

### Giai đoạn 1 — Xác nhận và phân loại

Thu:

- **Cluster/account/project/subscription ID**, endpoint type, FQDN, thời gian UTC.
- **Observed source IP** và nơi thực thi allowlist/firewall (biết NAT/proxy có thể thay source).
- API audit **user/groups, verb, resource, namespace, response code**, request URI/subresource.
- Cloud audit **principal thay network/IAM/RBAC integration** hoặc endpoint.
- Các request bất thường: Secrets access, RBAC changes, create privileged Pods, exec/portforward, webhook changes.
- Health metrics: API 401/403/5xx, latency, APF, etcd, webhook, LB/firewall.

### Giai đoạn 2 — Containment dựa trên điểm kiểm soát đúng

| Tình huống | Ưu tiên containment | Điều cần tránh |
| --- | --- | --- |
| **Public endpoint mở ngoài ý định** | Thu hẹp CIDR hoặc chuyển private theo runbook, giữ admin/node/CI path | Cắt mọi đường quản trị khiến không thể khôi phục |
| **Token/CI identity bị lộ** | Ngừng sử dụng credential, revoke/rotate, giới hạn RBAC/IAM | Chỉ đóng IP nguồn mà bỏ qua token đã bị copy |
| **RBAC escalation** | Review/revert binding và actor, xác minh persistence | Xóa ngay audit/objects trước khi thu bằng chứng |
| **Pod/SA credential compromise** | Cô lập workload, thay token/SA policy, xem Secret access | Giả định xóa Pod là đã xóa mọi quyền |
| **API flood/DoS** | Edge/network safeguards, APF/client rate, sửa retry storm | Bật bypass auth/admission để giảm latency |
| **Webhook outage** | Khôi phục service/TLS/network, đánh giá fail behavior | Vô hiệu hóa mọi policies ngoài quy trình |
| **CA/certificate issue** | Kiểm tra trust/rotation, dùng approved recovery path | Bật insecure-skip-tls-verify trên tất cả clients |

### Giai đoạn 3 — Scope và điều tra

1. Xác định **attack window** từ sự kiện sớm nhất đáng tin; xem clock/timezone.
2. Liệt kê **actors/credentials** liên quan và các resource mutations/reads bất thường trong logs.
3. Kiểm tra **cloud IAM, network changes, service accounts và admission changes** có mở đường thứ hai không.
4. Với Secrets có khả năng đã bị đọc, lập kế hoạch **rotate downstream credentials** theo mức độ và dependencies.
5. Tìm **persistence** như workloads, RBAC bindings, webhooks, scheduled jobs, external identities mà actor đã tạo.
6. Khôi phục **approved configuration** bằng phiên bản IaC/kube manifests đã kiểm chứng; giữ bằng chứng theo chain of custody nội bộ.
7. Xác minh **positive/negative tests** và giám sát sau sự cố.

### Giai đoạn 4 — Khôi phục và hậu kiểm

Một sự cố được coi là được kiểm soát khi:

- Endpoint network policy và các DNS/route paths quay về **trạng thái phê duyệt**.
- Identity/credentials bị lộ không còn sử dụng được theo mục tiêu thu hồi.
- RBAC/admission/IAM drift đã được loại bỏ hoặc có exception được chấp thuận.
- API phục vụ ổn định cho **admin, CI, nodes, controllers và webhooks**.
- Audit/log retention đủ để xác minh action và phát hiện tái diễn.
- Có **owner, ticket, timeline, residual risks và deadline cải tiến**.

## 25. Ma trận kiểm thử bảo vệ endpoint

Chỉ kiểm thử trên **cluster, mạng và danh tính được cấp quyền**; dùng **staging/canary**, bounded attempts, không quét hoặc flood API của bên thứ ba. Kiểm thử public reachability nên dùng **một nguồn ngoài allowlist được sở hữu/được phép**, không dò tìm các cluster lạ.

| Test | Phạm vi | Kết quả mong đợi |
| --- | --- | --- |
| **P1 – Admin access** | Managed workstation + IdP/MFA + approved network path | kubectl gọi API, quyền đúng scope, có audit |
| **N1 – Unapproved source** | Test machine ngoài authorized CIDR/private connectivity | Không tới API theo network policy dự kiến |
| **P2 – CI access** | Real CI runner/identity đã được phê duyệt | Có route/DNS/TLS, chỉ được deploy đúng namespace |
| **N2 – CI overprivilege** | Test quyền create ClusterRoleBinding/list Secrets ngoài scope | RBAC từ chối, không tạo mutations |
| **P3 – Node bootstrap** | Node mới trong staging subnet/zone | Register thành công qua approved path |
| **N3 – Anonymous access** | Test unauthenticated request vô hại theo policy | Không được đọc/sửa dữ liệu nhạy cảm |
| **N4 – Expired/revoked credential** | Lab token/cert không còn hợp lệ | Authn từ chối, có evidence |
| **N5 – TLS trust mismatch** | Lab client dùng wrong CA/hostname | Client từ chối kết nối; không dùng insecure skip |
| **P4 – Private DNS** | VPN/bastion/CI/node từ các zones khác nhau | Đúng FQDN, private address, route và SAN |
| **N6 – IPv6 alternate path** | Nếu có dual-stack, test nguồn không được phép | Không bypass IPv4 network policy qua IPv6 |
| **P5 – ServiceAccount minimal role** | Pod được phép gọi get/list resource hẹp | 200/authorized với required verb, không hơn |
| **N7 – Pod without API role** | Pod không cần Kubernetes API/token | Không có usable credential và access ngoài policy |
| **P6 – Admission valid workload** | Lab Deployment hợp lệ | Admit đúng, webhook latency trong SLO |
| **N8 – Admission deny** | Fixture vi phạm Pod Security/admission policy | Bị từ chối theo policy và có log |
| **F1 – Webhook unavailable** | Staging outage được kiểm soát | Failure policy đúng và có recovery path |
| **F2 – API replica/LB failure** | HA staging failover | Client reconnect hợp lý, health/ready và controller behavior phù hợp |
| **O1 – RBAC alert** | Test binding thay đổi được phê duyệt trong lab | SOC nhận event có actor/verb/resource |
| **O2 – Cloud endpoint drift** | Test policy-as-code hoặc change preview | Public exposure change không có approval bị chặn/cảnh báo |
| **O3 – API overload telemetry** | Bounded test requests trong staging | Quan sát APF/concurrency/errors, không gây DoS |
| **N9 – Port-forward privilege** | Identity không có pods/portforward | Authorization từ chối với evidence |

### 25.1. Positive và negative tests phải cùng mục tiêu

Nếu một test **unapproved source không kết nối được**, có thể do DNS lỗi hoặc endpoint đang down, không nhất thiết do allowlist. Cần một **positive control** từ nguồn được phép, cùng thời điểm, để xác nhận API đang hoạt động.

Nếu kiểm tra RBAC bằng kubectl auth can-i, kết quả **no** rất hữu ích nhưng **không thay việc kiểm tra end-to-end** đối với token, admission, aggregated API hoặc subresources khi thiết kế yêu cầu. Không thực hiện những thao tác mutate nguy hiểm trên production chỉ để xác minh deny.

### 25.2. Chuỗi evidence tối thiểu

~~~text
Test ID / change ID:
Cluster + namespace/environment:
Client identity + source network:
Kubeconfig context + endpoint hostname (no secret output):
DNS answer + IPv4/IPv6 + route:
TLS certificate verification:
Authentication result:
RBAC/authorization result:
Admission outcome (nếu request thuộc phạm vi):
Network/firewall and API audit event IDs:
Business or cluster operation result:
Rollback/cleanup and residual risk:
~~~

## 26. Checklist thiết kế và vận hành thường xuyên

| Câu hỏi | Bằng chứng |
| --- | --- |
| Cluster endpoint có public/private access theo đúng thiết kế không? | Provider control-plane setting và approved network diagram |
| Public endpoint có authorized source ranges hẹp? | Effective IPv4/IPv6 allowlists, cloud audit |
| Private access có DNS, VPN/transit, routes và return path không? | DNS/route/flow tests từ admin/CI/nodes |
| Kubeconfig server URL và CA trust chính xác? | Sanitized context, TLS hostname/chain verification |
| Kubeconfigs, client keys, CI tokens có được bảo vệ? | Secure storage, token TTL, secret scanning, offboarding |
| Human operators có IdP/MFA và quyền theo nhiệm vụ? | IAM/IdP policy, access review, audit |
| ServiceAccounts có RBAC tối thiểu và token khi cần? | SA/Role/Binding review, automount checks |
| Cluster-admin, impersonate, bind/escalate permissions đã được review? | RBAC privilege inventory, approvals |
| Pods/exec, pods/portforward và Secrets reads có được giám sát? | Kubernetes API audit events, alerts |
| NetworkPolicy đang thực thi đúng phạm vi CNI? | Provider/CNI behavior tests, egress/hostNetwork review |
| Admission webhooks có TLS, HA, timeout và failure policy đúng? | Configuration + positive/negative/failure tests |
| Etcd/kubelet management ports có private/enforced network policy? | Host/cloud firewall, TLS/auth config, inventory |
| API server logs có đủ điều tra nhưng không lộ Secret bodies? | Audit policy, log export, redaction/retention |
| Cloud IAM thay endpoint access có least privilege? | Role assignments, approval, cloud API events |
| APF/rate limits/HA bảo vệ khỏi resource exhaustion? | Metrics, SLO, bounded tests và failover evidence |
| API serving cert/CA rotation có được theo dõi? | Expiry alerts, renewal and recovery runbook |
| Node/CI/webhook/backup-region paths đã kiểm tra sau change? | Flow matrix, test report, canary |
| Break-glass đã được diễn tập và lưu bảo mật? | JIT/PAM logs, test record, approval |

## 27. Các nhầm lẫn thường gặp

1. **“Control plane endpoint chính là etcd.”** Kubernetes API server cung cấp API; etcd là kho trạng thái có network/security controls riêng.
2. **“Cổng API Kubernetes luôn là 6443.”** Self-managed thường dùng 6443, managed endpoint có thể khác.
3. **“Chỉ cần public endpoint dùng HTTPS là an toàn.”** Còn network exposure, authn/authz, RBAC, admission, audit và availability.
4. **“Private endpoint đồng nghĩa người trong VPC/VNet được tin.”** Vẫn phải xác thực/ủy quyền từng identity và theo dõi nội bộ.
5. **“Authorized IP ranges thay thế MFA.”** IP/network location không chứng minh user identity.
6. **“Tắt public access chắc chắn không ảnh hưởng CI và nodes.”** Cần kiểm tra private DNS, route, firewall và source locations.
7. **“Một bastion kết nối được chứng minh mọi zones đều khỏe.”** CI, node subnets, webhook và failover path có thể khác.
8. **“Kubeconfig chỉ là file mô tả nên có thể chia sẻ.”** Nó có thể chứa token, client cert/key hoặc exec credential plugin.
9. **“Tên context trong kubeconfig là user được xác thực.”** Context label có thể tùy ý; credential thực xác định identity.
10. **“insecure-skip-tls-verify sửa an toàn lỗi certificate.”** Nó bỏ server identity validation.
11. **“RBAC chỉ cần chặn cluster-admin.”** Quyền Secrets, exec, portforward, bind/escalate và workload creation cũng cần review.
12. **“Một Pod trên private network không thể dùng API.”** Pod có thể truy cập Kubernetes API Service/private endpoint theo path cho phép.
13. **“ServiceAccount token mặc định luôn cần cho mọi Pod.”** Có thể tắt automount khi không sử dụng Kubernetes API.
14. **“NetworkPolicy luôn chặn control plane endpoint trên mọi CNI.”** Enforcement phụ thuộc CNI, network path, hostNetwork và endpoint semantics.
15. **“Không có direct route từ laptop tới Pod là không port-forward được.”** Port-forward sử dụng Kubernetes API-mediated path nếu được RBAC cho phép.
16. **“API server reachable nghĩa user có thể đọc Secrets.”** Reachability, authentication, authorization là những bước khác nhau.
17. **“HTTP 403 nghĩa firewall đã chặn.”** 403 thường đến từ authorization/application; firewall drop thường không tạo Kubernetes HTTP 403.
18. **“Webhook luôn fail-closed theo mặc định do là security component.”** Phải xem failurePolicy và behavior thực; không suy từ tên.
19. **“Webhook fail-open luôn tốt cho availability.”** Có thể nhận workload vi phạm security policies.
20. **“API server ready chứng minh cả cluster security khỏe.”** Readiness không kiểm tra IAM drift, endpoint exposure, RBAC toàn diện hoặc log hygiene.
21. **“Watch là một request ngắn nên proxy timeout nào cũng được.”** Watch có thể là long-running stream và cần policy đúng.
22. **“APF thay DDoS protection ở edge.”** APF kiểm soát concurrency/priority trong API server, không loại bỏ volumetric flood phía trước.
23. **“Bật audit full request body luôn là tốt.”** Có thể ghi dữ liệu Secrets và tạo rủi ro lưu trữ.
24. **“Cùng Kubernetes CLI command là hành vi giống trên EKS/AKS/GKE.”** Cloud IAM, endpoint, DNS, firewall, audit integrations khác nhau.
25. **“Private DNS giải được tên nghĩa đường private tới API hoạt động.”** Còn route, firewall, TLS, authn và return path.
26. **“Thay API server cert không ảnh hưởng kubelet/CI.”** Cần kiểm tra CA trust/SAN và các clients phụ thuộc.
27. **“Xóa Pod bị xâm nhập làm token và Secrets không còn nguy hiểm.”** Token/credential đã bị copy hoặc persistence có thể tồn tại.
28. **“Đã có IAM least privilege nghĩa Kubernetes RBAC tự đúng.”** Cloud IAM và RBAC là hai lớp phải kiểm tra cùng nhau.
29. **“Không thấy log firewall là không có API traffic.”** Có thể path khác, thiếu telemetry, sampling hoặc provider-managed boundary.
30. **“Chỉ cần giấu API server FQDN để an toàn.”** DNS name obscurity không thay authentication, authorization hay network controls.

## 28. Bài tập vận dụng và gợi ý

### Bài 1 — Public endpoint đã đủ an toàn?

Cluster có API endpoint public HTTPS, allowlist **0.0.0.0/0**, yêu cầu OIDC login và Kubernetes RBAC. Có thể kết luận không có rủi ro đáng kể vì attacker không có tài khoản không?

**Gợi ý:** không. Endpoint có bề mặt network rộng, có thể chịu quét, credential abuse hoặc resource exhaustion. Nên đánh giá authorized networks/private access, MFA, patching, API audit, APF và quyền sau khi authenticate.

### Bài 2 — TLS lỗi sau đổi private DNS

Sau khi chuyển cluster sang private endpoint, kubectl kết nối được TCP nhưng báo **certificate hostname mismatch**. Có nên bật insecure-skip-tls-verify?

**Gợi ý:** không. Kiểm tra kubeconfig server URL, DNS answer, serving certificate SAN, CA trust và load balancer/endpoint được phê duyệt. Sửa trust/danh tính và kiểm tra lại handshake.

### Bài 3 — CI runner bị mất route

Một Git-based CI runner ngoài VPC đã dùng public API qua allowlist. Từ khi chuyển sang private-only, kubectl timeout. Đội CI đề nghị bật public endpoint cho mọi IP. Hãy đưa phương án an toàn hơn.

**Gợi ý:** đặt runner trong approved private network hoặc cung cấp VPN/transit/private access, cấu hình private DNS và route/firewall đúng, giữ OIDC/workload identity scoped; nếu cần ngoại lệ tạm thời phải có CIDR hẹp, approval, TTL, log và rollback.

### Bài 4 — Pod lộ token

Pod web bị compromise, token mounted thuộc ServiceAccount có quyền **list Secrets** trong namespace. Endpoint đã private-only. Vì sao dữ liệu vẫn có nguy cơ bị truy cập?

**Gợi ý:** Pod có đường internal tới API và token mang RBAC quyền Secrets. Cần điều tra API audit, thu hồi/rotate credentials, giảm role, tắt automount nếu không dùng, kiểm tra downstream secrets/identity.

### Bài 5 — Port-forward và firewall

Database Pod không có public Service; laptop không route tới Pod CIDR. Một operator có quyền pods/portforward. Thiết kế có ngăn operator truy cập DB thông qua API không?

**Gợi ý:** không dựa riêng vào thiếu route. Port-forward tạo đường thông qua Kubernetes API khi đủ quyền; hạn chế RBAC subresource, quản trị kubeconfig và DB auth, ghi audit.

### Bài 6 — Webhook fail-closed

Security webhook đang fail-closed, service backend bị down khiến Deployment create/update lỗi. Đội app muốn tắt webhook cho toàn cluster. Hãy đưa quy trình phản hồi.

**Gợi ý:** kiểm tra webhook network/TLS/HA/timeout, xác định phạm vi ảnh hưởng, khôi phục service hoặc dùng exception scoped được security approval, kiểm thử mutation hợp lệ và vi phạm trước khi đóng incident.

### Bài 7 — Break-glass khi IdP lỗi

Cluster private-only, mọi admin phải dùng SSO qua VPN. IdP bị outage, đồng thời cần sửa cấu hình cluster khẩn cấp. Thiết kế recovery nên có gì?

**Gợi ý:** phương án truy cập dự phòng được bảo vệ, không chia sẻ thường ngày; PAM/dual approval khi phù hợp, audit độc lập, đường network riêng được thử định kỳ, credential expiry/revocation và post-event review.

### Bài 8 — Threat → control → evidence

Cho một hệ thống **managed Kubernetes production** với **application Pods, CI runners, admin VPN, private API endpoint và admission webhooks**. Xây dựng ma trận:

1. Những **nguồn IP/identity** nào cần kết nối API server?
2. Phải phân biệt **TLS server trust, client authentication, RBAC, admission** ra sao?
3. Những verbs/subresources nào không được cấp cho CI và developer thông thường?
4. **Pod-to-API access** và token automount được giới hạn ở đâu?
5. Webhook TLS/network/failurePolicy được test thế nào để vừa bảo mật vừa giữ availability?
6. Những **API audit, cloud audit, flow logs, SLO và alerts** nào chứng minh security controls hoạt động?
7. Khi private DNS/VPN hoặc CI path lỗi, có kế hoạch **rollback không mở public API toàn Internet** không?

**Gợi ý:** bắt đầu từ trust boundaries và flow matrix, ánh xạ từng thao tác tới **network enforcement → identity → authorization → admission → audit**, rồi thiết kế test không vượt phạm vi được ủy quyền.

## 29. Tổng kết

**Bảo vệ control plane endpoint** là bảo vệ **cửa ngõ thay đổi trạng thái Kubernetes** và những đường phụ thuộc vào cửa ngõ đó. Một hệ thống an toàn phải xác định rõ **public/private endpoint, DNS/routing, firewall/source policies, TLS server trust, kubeconfig credentials, OIDC/ServiceAccount authentication, RBAC, admission, API audit và khả năng phục hồi**. Trong kiến trúc managed Kubernetes, cloud IAM/endpoint settings là lớp riêng; trong self-managed Kubernetes, đội vận hành còn phải bảo vệ trực tiếp load balancer, serving certs, etcd và HA API servers.

Không có một control đơn lẻ bảo đảm an toàn: **private endpoint không thay RBAC**, **RBAC không thay network DoS protection**, **NetworkPolicy không mặc nhiên bảo vệ toàn bộ host/control-plane path**, và **admission webhooks không an toàn nếu không có TLS, availability và policy review**. Các API subresources như exec và port-forward cũng cần tính tới vì chúng có thể thay đổi cách tiếp cận workloads mà không cần client có direct route tới Pod.

Một control plane endpoint chỉ nên được coi là đã được bảo vệ khi **các danh tính được phép truy cập API qua đường tin cậy và thực hiện đúng quyền**, **nguồn và thao tác trái quyền bị từ chối ở đúng lớp**, **control plane vẫn phục vụ node/CI/webhook khi có sự cố**, và **có bằng chứng từ network flow, TLS verification, Kubernetes/cloud audit, positive/negative tests cùng runbook phục hồi để xác minh liên tục**.
