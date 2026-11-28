# Egress control cho container: giới hạn lưu lượng đi ra theo nguyên tắc tối thiểu quyền

**Egress control** là tập hợp biện pháp xác định **container, Pod hoặc workload được phép tạo kết nối đi đâu, bằng giao thức nào, trong điều kiện danh tính nào và qua điểm kiểm soát nào**. Nếu ingress trả lời câu hỏi “ai được vào dịch vụ?”, egress trả lời “dịch vụ này được đi ra đâu?”. Trong thực tế, một Pod xử lý REST API có thể cần gọi database, DNS, dịch vụ thanh toán hoặc hệ thống quan sát, nhưng không có lý do để truy cập mọi subnet nội bộ, toàn bộ Internet hoặc endpoint quản trị của cloud.

Trong chương **Bảo mật mạng container** thuộc học phần **SECURITY_NETWORK_SECURITY**, egress control kết hợp **phân đoạn mạng, firewall, Zero Trust, TLS/mTLS, VPN, DNS, IDS/IPS, bảo mật API và bảo mật mạng cloud**. Mục tiêu không chỉ giảm nguy cơ data exfiltration, SSRF hoặc lateral movement. Egress control còn giúp **phân định quyền giữa production và development, khống chế tác động của container bị chiếm, quản lý kết nối đối tác và tạo bằng chứng kiểm toán**.

Bài học sử dụng Kubernetes làm ví dụ chính vì đây là môi trường phổ biến cho nhiều container có vòng đời động. Đồng thời, bài giải thích các giới hạn trong Docker/Podman, cloud VPC, proxy, CNI và service mesh. **Kubernetes NetworkPolicy chuẩn chủ yếu kiểm soát theo Pod, IP, port và protocol; nó không tự hiểu DNS name, HTTP path, JWT, TLS identity hay mục đích nghiệp vụ.** Để áp chính sách theo tên miền, workload identity hoặc payload, cần thành phần có khả năng phù hợp.

Tất cả hostname có đuôi **.example** và địa chỉ thuộc dải tài liệu dùng làm ví dụ giả định; không phải endpoint sản xuất. Các lệnh chỉ thực hiện trên lab hoặc hạ tầng được cấp phép. Những YAML gắn nhãn *pseudopolicy* không phải cấu hình có thể apply trực tiếp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **egress, ingress, east–west, north–south**, source workload và điểm thực thi chính sách.
2. Xây dựng **allowlist đích theo nhu cầu nghiệp vụ**, thay vì mặc định cho mọi Pod truy cập toàn mạng.
3. Hiểu đúng **Kubernetes NetworkPolicy egress isolation, policyTypes, podSelector, namespaceSelector, ipBlock, ports** và hợp nhất nhiều chính sách.
4. Cấu hình mẫu **default-deny egress** và mở ngoại lệ tối thiểu cho DNS, dịch vụ nội bộ hoặc đích IP cố định.
5. Giải thích vì sao egress theo **FQDN, URL, HTTP method và workload identity** cần cơ chế ngoài NetworkPolicy chuẩn.
6. Phân tích **egress gateway, forward proxy, NAT/SNAT, security group, VPC route và cloud firewall**.
7. Nhận diện rủi ro **SSRF, cloud instance metadata, DNS tunneling, DoH, IPv6, hostNetwork và privileged workload**.
8. Kiểm tra cả **đường đi và đường về**, log chặn/cho phép, tính thực thi của CNI và alternate bypass paths.
9. Thiết kế rollout không làm đứt DNS, container image pulls, service mesh, monitoring và luồng ứng dụng hợp lệ.
10. Lập ma trận kiểm thử, điều tra sự cố và vận hành chính sách egress có owner, expiry, audit và rollback.

## 2. Egress là gì và giới hạn của khái niệm

Ở mức mạng, **egress** là traffic rời khỏi một endpoint hoặc một miền bảo vệ. Cần xác định **điểm nhìn**: cùng một request có thể là egress của Pod A nhưng là ingress của Pod B.

~~~mermaid
flowchart LR
    A[Pod Orders API] -->|Egress của Orders| B[Pod Catalog]
    A -->|Egress ra bên ngoài cluster| G[Egress gateway / firewall]
    G -->|Kết nối đã được duyệt| P[Partner HTTPS API]
    B -.Ingress của Catalog.-> A
    G -.Flow logs / quyết định.-> S[Security monitoring]
~~~

### 2.1. Các loại luồng

| Loại | Ví dụ | Ý nghĩa kiểm soát |
|---|---|---|
| **Pod → Pod cùng namespace** | Orders gọi Catalog | Egress của Orders, ingress của Catalog |
| **Pod → Pod khác namespace** | App gọi Payment | Cross-namespace segmentation, identity và cả hai đầu |
| **Pod → database nội bộ** | App gọi PostgreSQL | Port/IP hoặc service identity, DB authentication |
| **Pod → DNS resolver** | Tra cứu tên dịch vụ/đối tác | Cho phép resolver đúng, xem DNS policy và cache |
| **Pod → Internet** | Gọi API nhà cung cấp | Egress allowlist, TLS verify, proxy và quota |
| **Pod → cloud API/metadata** | Lấy token hoặc thao tác điều khiển | IAM/service identity, chặn endpoint nhạy cảm |
| **Node → container registry** | Kubelet/container runtime pull image | Thường là **egress của node/runtime**, không phải egress của Pod ứng dụng |
| **Control plane → node/Pod** | Kubernetes probe hoặc quản trị | Đường khác, không được coi là Pod egress thường |

**Không đánh đồng container với Pod:** nhiều containers trong cùng một Kubernetes Pod thường **chia sẻ network namespace, Pod IP và port space**. Core NetworkPolicy chọn **Pod**, không thiết lập allowlist khác nhau cho hai container cùng Pod.

### 2.2. Egress control không thay authorization

Một Pod được phép TCP/443 tới API đối tác không tự có quyền đọc dữ liệu của tenant khác. Cần **TLS server identity, token đúng audience, scope, business authorization, logging và key rotation**. Một nguồn IP “nội bộ” cũng không chứng minh người gọi đáng tin.

## 3. Vì sao outbound mặc định rộng là nguy hiểm?

Một container bị xâm nhập có thể cố:
- Gửi dữ liệu ra Internet qua HTTPS hoặc giao thức khác.
- Liên lạc với hạ tầng điều khiển từ xa khi có đường mạng.
- Truy cập database, Redis, message broker hoặc API của namespace khác.
- Gọi metadata/control-plane endpoints để lấy credentials nếu cấu hình cloud cho phép.
- Thăm dò cổng quản trị nội bộ, dù cổng đó không public.
- Lạm dụng chức năng tải URL/webhook của ứng dụng gây **SSRF**.
- Sử dụng resolver không được phê duyệt hoặc tunnel dữ liệu qua DNS.
- Gọi registry/repository ngoài supply-chain policy.
- Gây tải outbound làm cạn NAT ports, connection tracking hoặc quota cloud.

**Egress deny không chữa được việc container bị compromise**. Nó giảm số đích attacker có thể tiếp cận và tạo thêm tín hiệu phát hiện. Nếu đích được phép là một dịch vụ có thể chuyển tiếp dữ liệu không kiểm soát, attacker vẫn có thể lợi dụng đích đó; phải xem cả **đường đi qua proxy trung gian**.

### 3.1. Mô hình Zero Trust cho outbound

Thay vì “Pod trong cluster được gọi mọi thứ”, xác định:

\[
\text{Allowed Flow} =
\text{Source Workload} \land
\text{Destination} \land
\text{Protocol/Port} \land
\text{Identity/Authorization} \land
\text{Context/Policy}
\]

Đây là **khung tư duy**, không phải công thức mà Kubernetes NetworkPolicy tự thực hiện toàn bộ. Core NetworkPolicy có thể kiểm soát một phần ở mức Pod/CIDR/port; yếu tố danh tính, hostname, phương thức HTTP hay thuộc tính tài nguyên cần thực thi ở những lớp khác.

## 4. Bản đồ trust boundaries trong container platform

Một hệ thống container hiện đại có nhiều đường egress.

~~~mermaid
flowchart TB
    POD[App Pod] --> DNS[Cluster DNS / NodeLocal DNS]
    POD --> INT[Internal API / DB]
    POD --> GW[Proxy hoặc Egress Gateway]
    GW --> FW[Cloud Firewall / NAT]
    FW --> PARTNER[External Partner]
    NODE[Worker Node / Kubelet] --> REG[Container Registry]
    POD -.Chặn theo policy.-> META[Cloud Metadata]
    POD -.Chặn theo policy.-> MGMT[Management Networks]
    CTRL[Network policy + IAM + GitOps] -.Quản trị.-> POD
    CTRL -.Quản trị.-> GW
    FW -.Traffic logs.-> SIEM[SIEM]
    POD -.CNI/flow logs.-> SIEM
~~~

Bốn ranh giới quan trọng:

1. **Container/Pod → cluster network:** ai được truy cập DNS, API nội bộ, DB, service mesh?
2. **Cluster → cloud VPC / on-premises:** route, SG, firewall và VPN nào cho phép lưu lượng?
3. **Cloud network → Internet:** có proxy, NAT, gateway, egress inspection hoặc allowlist?
4. **Workload → identity/control plane:** IAM, cloud metadata, Kubernetes API và secrets có được giới hạn?

Một luồng có thể không đi qua gateway theo đường dự kiến, ví dụ **PrivateLink/private endpoint, VPC peering, hostNetwork, NodePort, direct Internet route hoặc DNS-over-HTTPS ngoài policy**. Vì vậy inventory **mọi đường** quan trọng không kém cấu hình một rule.

## 5. Defense in depth cho egress

| Lớp | Điều kiểm soát được | Điều không tự giải quyết |
|---|---|---|
| **Core Kubernetes NetworkPolicy** | Chọn Pods và cho phép ingress/egress theo Pod/namespace/CIDR/port | FQDN/HTTP path/URL/JWT; phụ thuộc CNI thực thi |
| **CNI-specific policy** | Có thể bổ sung FQDN, DNS proxy, L7 hoặc cluster-wide policy | Semantics không portable, phải kiểm tra sản phẩm |
| **Cloud SG/NACL/firewall** | Địa chỉ, subnet, protocol, stateful/stateless rules theo cloud | Pod identity và authorization có thể không hiện |
| **Routing/Transit hub** | Network reachability, next hop, inspection path | Không phải application authorization |
| **Egress gateway / forward proxy** | Egress choke point, identity, hostname/URL policy tùy năng lực | Không tự buộc mọi Pod đi qua nếu vẫn có alternate path |
| **DNS resolver/filter** | DNS queries, policy tên miền, logging | Hardcoded IP, cached DNS, DoH/DoT tự chọn |
| **Service mesh** | Service identity/mTLS, policy/telemetry ở luồng đi qua proxy | Không tự chặn bypass ngoài proxy nếu enforcement thiếu |
| **IAM + application** | Quyền cloud API, token scope và business rules | Không tự giới hạn TCP/UDP ra Internet |
| **Runtime hardening** | Ngăn container đổi mạng, capabilities, secrets | Không tự thay route/egress allowlist |
| **Monitoring/response** | Phát hiện anomalous flows, route/policy drift | Không bảo đảm chặn kịp mọi luồng |

**Không tồn tại một YAML đơn lẻ bảo vệ mọi luồng outbound của Kubernetes, nodes, hostNetwork và cloud APIs.** Quy trình phải chọn đúng enforcement points và kiểm thử từng đường.

## 6. Core Kubernetes NetworkPolicy hoạt động thế nào?

Kubernetes **NetworkPolicy** là API khai báo điều kiện cho phép lưu lượng vào/ra **Pods được chọn**, trên nền CNI/network plugin có hỗ trợ. Nó không phải firewall process gắn trực tiếp vào YAML; controller/data plane thực thi policy tùy môi trường.

### 6.1. Những trường quan trọng

- **metadata.namespace:** namespace sở hữu đối tượng NetworkPolicy.
- **spec.podSelector:** chọn các Pod **trong namespace của NetworkPolicy**. Selector rỗng **{}** chọn mọi Pod trong namespace.
- **spec.policyTypes:** gồm **Ingress**, **Egress** hoặc cả hai.
- **spec.ingress/egress:** danh sách các **rule cho phép**; core API không cung cấp explicit deny rule chung có thứ tự.
- **egress[].to:** những destination Pods/namespaces hoặc CIDR phù hợp.
- **egress[].ports:** protocol và port đích theo rule.
- **ipBlock:** CIDR được chỉ định, có thể có các exceptions theo API.

**Một Pod chỉ bị cô lập egress khi có ít nhất một NetworkPolicy chọn Pod đó và đặt nó vào phạm vi Egress isolation**, trực tiếp hoặc theo defaulting semantics. Khi Pod đã bị cô lập, các kết nối outbound được phép là **hợp của các rule allow** trong mọi policy phù hợp. Chính sách bổ sung chỉ **mở thêm** quyền; không thể viết một policy chuẩn để “deny override” một allow quá rộng ở policy khác.

### 6.2. Cơ chế hợp nhất nhiều policies

Giả định:
- Policy A cho Orders Pod gọi DNS.
- Policy B cho Orders Pod gọi Catalog.
- Policy C được tạo sau nhưng không có egress rules.

Nếu cả ba chọn cùng Pod và đều áp Egress isolation, các quyền A và B vẫn hợp lại; **Policy C không thu hồi allow của A hoặc B**. Để giảm quyền phải sửa/xóa policy tạo allow hoặc dùng một cơ chế enforcement khác có semantics được xác minh.

### 6.3. Một chiều hay hai chiều?

Đối với Pod A gọi Pod B:
- A cần được cho **egress** nếu A đang bị cô lập outbound.
- B cần được cho **ingress** nếu B đang bị cô lập inbound.
- Phản hồi của một kết nối được phép thường được xử lý theo connection tracking trong mô hình NetworkPolicy; không cần mở rộng outbound reply bằng một policy allow-all độc lập chỉ để hồi đáp.

Tuy nhiên, behavior cụ thể của **state tracking, NAT, Service translation và host networking** phụ thuộc network plugin. NetworkPolicy không thay kiểm tra tầng ứng dụng.

### 6.4. Những giới hạn cần nhớ

1. Core NetworkPolicy không định nghĩa rule theo **DNS name/FQDN**.
2. Core NetworkPolicy không định nghĩa **HTTP method/path, Kafka topic, database table**.
3. Chọn Pod theo labels không bảo đảm caller không thể sửa labels nếu quyền Kubernetes RBAC sai.
4. Phạm vi enforcement với **hostNetwork, node-originated traffic, traffic tới Pod từ host** phụ thuộc implementation; không suy từ Pod-to-Pod denial ra toàn bộ node isolation.
5. Không có guaranteed ordering hay deny precedence giữa các Core NetworkPolicies.
6. **L4 port cho phép** không có nghĩa server certificate đã được xác minh.
7. Service IP/Pod IP và NAT khiến phạm vi **ipBlock** có khác biệt giữa implementations.
8. Nếu CNI không hỗ trợ NetworkPolicy, việc tạo object thành công **không đồng nghĩa có hiệu lực chặn**.

## 7. Tạo mặc định từ chối egress cho một namespace

Một baseline hữu ích là chọn tất cả Pods trong một namespace và không cung cấp egress allow rules.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: orders-prod
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Ý nghĩa:
- Chọn tất cả Pods trong namespace **orders-prod**.
- Cô lập chúng về **egress**.
- Không bổ sung egress allowances trong policy này.
- **Không thay đổi ingress isolation** chỉ bởi policy này.
- **Không phủ nhận** quyền egress đã được policy khác cho phép với các Pods đó.

### 7.1. Tại sao default deny thường làm ứng dụng lỗi?

Nếu app cần DNS, database, IdP, metrics, time synchronization hoặc gọi HTTPS ra ngoài mà chưa có exception, các luồng ấy có thể bị chặn. Đây là hệ quả có chủ đích của default deny, nhưng **triển khai ồ ạt không kiểm kê dependencies dễ gây outage**.

### 7.2. Một baseline chưa đủ là chính sách hoàn chỉnh

Một namespace có thể chứa nhiều loại Pods:
- Orders API.
- Worker xử lý queue.
- Migrator/maintenance job.
- Metrics exporter.
- Sidecar/service mesh proxy.
- Init container.
- Deployment cron job.

Mỗi workload có thể cần quyền egress khác nhau; **policy chọn đúng workload** thường giảm blast radius hơn việc mở chung toàn namespace sau khi default deny.

## 8. Cho phép egress DNS có kiểm soát

DNS là dependency đầu tiên thường bị bỏ sót khi bật default-deny. Một cách phổ biến ở các cluster dùng CoreDNS là cho đúng **Pods DNS** nhận UDP/TCP 53 từ workload được chọn.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-cluster-dns
  namespace: orders-prod
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Lưu ý chính xác:** trong một phần tử **to**, đặt **namespaceSelector và podSelector cùng cấp** nghĩa là chọn **Pods phù hợp trong các namespaces phù hợp**; không phải “tất cả Pods của namespace đó” cộng với “Pods có label trên namespace hiện tại”.

Ví dụ chỉ hoạt động nếu:
- Namespace kube-system có label **kubernetes.io/metadata.name=kube-system**.
- DNS Pods thực sự có label **k8s-app=kube-dns**; tên label có thể khác theo distribution.
- CNI thực thi selectors đúng và luồng DNS đi qua những Pods được chọn.
- CoreDNS hoặc DNS implementation có đường đi/return path phù hợp.
- Không có **NodeLocal DNSCache**, DNS proxy hoặc DNS service IP translation yêu cầu lựa chọn khác.

### 8.1. NodeLocal DNSCache và DNS IP đặc biệt

Nếu workload gửi DNS tới **link-local address** của NodeLocal DNSCache, chính sách DNS theo CoreDNS Pods có thể không bao phủ đường đi được quan sát bởi CNI. Tùy CNI, cần policy riêng cho địa chỉ/cache/process của node hoặc DNS proxy được vendor hỗ trợ.

**Không thêm 0.0.0.0/0:53 để “sửa” DNS khi chưa hiểu cơ chế**, vì điều đó cho phép gửi DNS tới các resolver ngoài chính sách và mở thêm đường exfiltration.

### 8.2. DNS over TCP không phải ngoại lệ hiếm

DNS dùng UDP 53 phổ biến, nhưng **TCP 53 vẫn cần** trong nhiều tình huống như response lớn, fallback hoặc quy trình riêng. Do đó policy DNS thường phải xét cả UDP và TCP 53 theo resolver thực tế. DoT qua TCP/853 và DoH qua HTTPS/443 là các luồng khác, không tự được “quản lý DNS” chỉ vì đã cho DNS 53.

### 8.3. DNS request và DNS response

Một packet query được phép đi tới resolver không chứng minh hostname được giải quyết thành IP được phép. Với destination có tên động, cần **FQDN policy hoặc egress proxy** phù hợp thay vì mở toàn bộ IP chỉ vì DNS trả về địa chỉ đó.

## 9. Cho phép gọi một service nội bộ

Ví dụ **Orders API** được phép gọi **Catalog API** ở namespace **catalog-prod**, port 8443.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-catalog
  namespace: orders-prod
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: catalog-prod
          podSelector:
            matchLabels:
              app: catalog-api
      ports:
        - protocol: TCP
          port: 8443
~~~

Để cuộc gọi hoạt động:
1. Catalog Pods phải được gắn label đúng.
2. Kubernetes Service có thể chuyển tiếp tới Catalog Pods trên **targetPort** phù hợp; port trong NetworkPolicy cần phản ánh traffic tại điểm enforcement (pre-/post-NAT tùy CNI).
3. Nếu Catalog Pods bị ingress isolated, **ingress policy phía Catalog** cũng phải cho Orders vào.
4. Ứng dụng phải kiểm tra server identity qua TLS/mTLS và quyền API.
5. Nếu có service mesh sidecar, cần kiểm tra chính sách traffic đi qua sidecar và các cổng thực sự sử dụng.

**NetworkPolicy không tự giải quyết quyền với từng Catalog item**. Sau khi kết nối L4 được phép, Catalog vẫn phải thực thi business authorization.

### 9.1. Nguy cơ chọn nhầm namespace/Pod labels

Một policy dùng:

~~~yaml
# Minh họa cú pháp sai về ý định khi muốn chọn Pod trong namespace khác.
to:
  - namespaceSelector:
      matchLabels:
        team: catalog
  - podSelector:
      matchLabels:
        app: catalog-api
~~~

Ở đây là **hai phần tử riêng**, nên semantics là **OR**: bất kỳ destination Pods thuộc namespace có label **team=catalog**, **hoặc** bất kỳ Catalog Pod có label **app=catalog-api trong chính namespace của policy**. Điều này khác với chọn đúng Catalog Pods trong một namespace xác định.

**Không chỉ lint YAML syntax; phải review semantics của selectors và kiểm thử reachability thực tế.**

## 10. Cho phép tới một địa chỉ IP bên ngoài

Khi destination có địa chỉ **cố định và quản lý được**, Core NetworkPolicy có thể dùng **ipBlock**.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-external-partner-ip
  namespace: orders-prod
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 198.51.100.10/32
      ports:
        - protocol: TCP
          port: 443
~~~

**198.51.100.10 thuộc dải địa chỉ tài liệu**, không phải IP của đối tác thật; ví dụ có tính chất minh họa.

### 10.1. Khi nào ipBlock phù hợp?

- Hệ thống đích có **địa chỉ cố định** hoặc dải CIDR có owner và contract rõ.
- Có thể quản trị thay đổi địa chỉ/allowlist an toàn.
- Không phải các workloads cùng cluster mà bạn có thể chọn bằng Pod/namespace labels.
- Routing/NAT behavior của CNI xác định được địa chỉ nào được dùng khi thực thi policy.

### 10.2. Khi nào không nên dựa vào ipBlock?

- SaaS dùng CDN hoặc IP pool thay đổi thường xuyên.
- FQDN có nhiều A/AAAA records tùy region.
- Cần lọc theo **HTTP Host, URI/path hoặc server identity**.
- Traffic đi qua NAT/proxy làm destination tại Pod khác destination thực tế.
- Đích là Pod/Service IP nhưng NAT semantics của CNI chưa được kiểm chứng.
- CIDR dùng chung nhiều tenant/dịch vụ, làm allowlist quá rộng.

**NetworkPolicy ipBlock là điều kiện địa chỉ, không phải bảo đảm caller thật sự nói chuyện với đúng tên miền hay đối tác.** Khi IP thay đổi, cần pipeline cập nhật policy có kiểm chứng hoặc egress proxy có tên miền/identity controls.

## 11. So sánh destination selectors và ipBlock

| Cách chọn | Dùng tốt cho | Rủi ro/chú ý |
|---|---|---|
| **podSelector** | Pod trong namespace của policy | Phụ thuộc đúng label và RBAC |
| **namespaceSelector** | Một hoặc nhiều namespaces | Có thể quá rộng nếu chỉ chọn namespace |
| **namespaceSelector + podSelector trong cùng phần tử** | Workloads cụ thể ở namespaces khác | Phải kiểm tra cả hai selectors |
| **ipBlock CIDR** | External/static IP destinations | Không kiểm tra DNS/TLS identity, NAT và overlap |
| **Service name (DNS)** | Không có trường native trong core NetworkPolicy | Cần CNI FQDN policy hoặc proxy nếu muốn L7/domain allowlist |
| **Workload identity/SPIFFE** | Dịch vụ nội bộ có mTLS/mesh | Không thuộc core NetworkPolicy, cần engine riêng |
| **HTTP Host/path** | API calls qua proxy | Phải dùng L7 gateway/proxy và chặn đường bypass |

### 11.1. Vì sao một địa chỉ Service IP có thể gây hiểu nhầm?

Kubernetes Service có thể dùng **virtual IP**, rồi kube-proxy, eBPF load balancing hoặc data-plane component chuyển đổi destination tới Pod IP. **Thời điểm xử lý NAT so với policy enforcement** có thể khác theo CNI và datapath, ảnh hưởng việc một **ipBlock trỏ ClusterIP** có hiệu lực hay không.

Đối với service nội bộ, ưu tiên selectors khi phù hợp và kiểm thử; không coi một allowlist ClusterIP là portable giữa mọi distributions.

## 12. FQDN egress: tên miền không phải địa chỉ cố định

Một yêu cầu thường gặp: “Pod chỉ được gọi **api.partner.example** qua HTTPS”. Core NetworkPolicy **không có thuộc tính toFQDNs** trong API chuẩn. Một số CNI/vendor đưa ra **FQDN policies** hoặc DNS proxies; cũng có thể dùng **HTTP CONNECT forward proxy/egress gateway** với allowlist tên miền.

### 12.1. FQDN control cần những điều kiện nào?

- Client phải sử dụng resolver/đường egress được giám sát.
- Policy engine phải ánh xạ DNS name sang IP theo semantics rõ.
- DNS records có **TTL, nhiều IPs, CDN, failover và cache**.
- Phải xét **A và AAAA**, CNAME chain và dynamic address pools.
- Giải quyết chuyện **hardcoded IP, DoH/DoT riêng, host file, DNS cache hoặc proxy bypass**.
- Nếu policy dựa vào HTTP Host/SNI, phải hiểu **TLS encryption, proxy modes, QUIC/HTTP/3 và ECH** theo khả năng sản phẩm.

### 12.2. DNS-based policy không phải xác thực server

Ngay cả khi resolver trả IP cho api.partner.example, ứng dụng vẫn cần:
- TLS certificate/hostname verification.
- Pinning hoặc trust restrictions khi có căn cứ và kế hoạch rotation.
- Token đúng issuer/audience và authorization hợp lệ.
- Chống redirect sang host ngoài danh sách được phép.
- Kiểm tra response/endpoint identity ở các lớp phù hợp.

**Một tên miền được allow không chứng minh mọi URL/path trên tên miền ấy an toàn.** Shared hosting và CDN có thể phục vụ nhiều nội dung.

### 12.3. Wildcard policy cần thận trọng

Allow **\*.example** có thể mở cả staging, subdomain của đối tác, endpoint bị takeover hoặc tên mới trong tương lai. Nên giới hạn đúng hostname và owner khi có thể. Những biểu thức wildcard có semantics khác nhau theo CNI/proxy, phải kiểm tra chúng khớp subdomain nào và có bao gồm apex domain không.

## 13. DNS tunneling và resolver không được phép

Khi chặn HTTP/HTTPS outbound nhưng vẫn cho UDP/53 tới mọi Internet IP, một workload có thể có kênh giao tiếp ngoài policy qua DNS nếu resolver và dữ liệu truy vấn bị lạm dụng.

### 13.1. Kiểm soát DNS

1. Cho phép Pod truy cập **resolver được phê duyệt**, không mở port 53 tới mọi địa chỉ.
2. Kiểm tra NodeLocal DNSCache/cluster DNS path và thực thi phù hợp.
3. Dùng **DNS filtering/logging** với data retention, privacy và quyền truy cập rõ.
4. Giới hạn DNS queries bất thường, query lengths, request rates và domain entropy theo monitoring phù hợp.
5. Quản trị ứng dụng tự sử dụng **DoH/DoT** qua những đường không phù hợp policy.
6. Đối chiếu DNS query logs với outbound flows, không coi DNS log là bằng chứng request ứng dụng đã thành công.
7. Với private zones, tránh resolver forwarding sai làm lộ tên nội bộ.

### 13.2. DoH/DoT không “biến mất” khỏi egress

DoH thường chạy trên **HTTPS/443**, DoT thường qua **TLS/853**. Một NetworkPolicy chỉ chặn UDP/53 ngoài cluster không tự chặn DoH qua một HTTPS destination đã allow quá rộng. Để giới hạn, cần kết hợp **network allowlists, proxy/domain policies và application configuration**.

**Không xem mã hóa DNS là hành vi độc hại mặc định**; chính sách doanh nghiệp có thể cho phép DNS mã hóa tới resolver được duyệt. Vấn đề là **đường phân giải ngoài quyền, thiếu logging hoặc nguy cơ data leakage**.

## 14. Egress gateway và forward proxy

Một **egress gateway** là điểm tập trung outbound traffic trước khi nó đi tới đích. Một **forward proxy** xử lý request thay mặt client, thường có khả năng áp chính sách theo destination host, URL hoặc identity tùy mode và sản phẩm.

~~~mermaid
flowchart LR
    POD[App Pod] -->|Theo policy| EG[Egress Gateway / Proxy]
    EG -->|Chỉ đích được duyệt| FW[Firewall / NAT]
    FW --> EXT[External API]
    POD -.Bị chặn.-> EXT
    EG -.Auth + routing decisions.-> SOC[SIEM]
    FW -.Flow/NAT logs.-> SOC
~~~

### 14.1. Chế độ proxy

| Kiểu | Cách hoạt động | Điểm cần lưu ý |
|---|---|---|
| **Explicit forward proxy** | Ứng dụng biết HTTP(S)_PROXY hoặc proxy endpoint | Ứng dụng có thể bypass proxy nếu còn direct egress; phải cưỡng chế ở mạng |
| **HTTP CONNECT proxy** | Client yêu cầu tunnel TCP đến host/port | Kiểm tra destination, identity, TLS và policy CONNECT |
| **Transparent proxy** | Traffic được redirect tại mạng/sidecar | DNS/NAT/MTU, state và protocol handling phức tạp |
| **Service mesh egress gateway** | Mesh chuyển traffic ra khỏi mesh qua gateway | Không bảo đảm mọi traffic qua gateway nếu có đường direct bypass |
| **Cloud managed firewall/egress** | Network route/NAT/firewall tại cloud | Có thể không hiểu Pod/user identity hoặc HTTP URL |
| **Application-level broker** | Service gọi broker nội bộ, broker gọi đối tác | Giúp kiểm soát nghiệp vụ nhưng broker thành tài sản nhạy cảm |

### 14.2. Không mặc định proxy giải mã TLS

Một forward proxy hỗ trợ **HTTP CONNECT** có thể chỉ chuyển tiếp bytes của TLS tunnel mà không giải mã payload. Nếu cần kiểm tra URL/path/body, có thể phải dùng **application gateway** ở điểm có quyền giải mã hoặc TLS interception được đánh giá. **TLS interception** tạo rủi ro privacy, private key, truststore, mTLS và hiệu năng; không áp mặc định.

### 14.3. Bắt buộc traffic qua gateway

Phải đảm bảo:
1. Pod chỉ có đường outbound tới gateway/đích nội bộ được phép.
2. Direct route ra Internet không cho bypass.
3. Gateway có danh tính, quyền và allowlist theo consumer.
4. Firewall/cloud networking chỉ chấp nhận traffic ra từ gateway/egress subnet phù hợp.
5. Mọi kết nối dự phòng/failover vẫn qua enforcement point tương đương.
6. Không có alternate protocol IPv6/UDP/QUIC đi đường khác.
7. Logs có thể quy gán traffic về workload, tenant hoặc service identity.

**Chỉ đặt biến môi trường HTTPS_PROXY không phải policy chống bypass** nếu container vẫn có thể tạo kết nối TCP trực tiếp.

## 15. NAT, SNAT và danh tính nguồn sau egress

Trong nhiều cloud/Kubernetes setups, traffic từ Pods đi ra ngoài có thể được **SNAT** thành node IP, gateway IP, NAT public IP hoặc proxy IP. Đích ngoài có thể chỉ thấy **một IP chung**, không biết Pod nào đã gửi.

### 15.1. Các hệ quả

- Đối tác allowlist **NAT egress IP**, không phải Pod IP.
- Logs tại đối tác chỉ thấy gateway, cần correlation nội bộ.
- Rate limiting theo IP có thể áp chung nhiều workloads.
- Nếu có multi-region hoặc failover, egress IP có thể đổi.
- NAT port exhaustion hoặc connection tracking có thể làm timeout.
- Firewall policy theo source IP cần hiểu **IP tại đúng enforcement point**.
- Nếu firewall nhìn node IP, nó không tự có namespace/service identity.

~~~text
Pod A: 10.244.1.10:54001 ----+
                             |
Pod B: 10.244.2.20:55002 ----+--> SNAT / Egress IP 203.0.113.25 --> Partner
                             |
Pod C: 10.244.3.30:56003 ----+

Đối tác thấy 203.0.113.25; hệ thống nội bộ cần NAT mappings
và thời điểm để quy về Pod/workload.
~~~

**203.0.113.25 là địa chỉ tài liệu**, không phải NAT endpoint thật.

### 15.2. Egress IP per namespace/workload

Một số CNI/cloud platforms hỗ trợ **egress IP assignment** theo workload, namespace hoặc node pool. Tính năng này thuận tiện cho partner allowlist và attribution, nhưng:
- Không tự thay danh tính workload hoặc TLS.
- Có thể chuyển IP khi failover; cần xem support/capacity/HA.
- Nếu nhiều Pods dùng một IP, vẫn cần audit chi tiết.
- Không có semantics portable trong core Kubernetes NetworkPolicy.
- Phải hạn chế ai được đổi assignment/labels/route.

## 16. Cloud instance metadata và SSRF

Một Pod hoặc container có khả năng gọi địa chỉ metadata/identity endpoint của hạ tầng có thể nhận được thông tin hoặc credentials tùy cloud, cấu hình workload identity và quyền liên quan. **SSRF** làm rủi ro tăng nếu một ứng dụng chấp nhận URL do caller kiểm soát rồi tự tải nội dung từ mạng nội bộ.

### 16.1. Mô hình rủi ro

~~~mermaid
flowchart TD
    USER[Caller API] --> FETCH[Ứng dụng có chức năng fetch URL]
    FETCH -->|Request nội bộ không được giới hạn| META[Cloud metadata / node credentials]
    FETCH -->|Request hợp lệ| PARTNER[Đối tác được duyệt]
    META -.Credential exposure risk.-> INCIDENT[Security incident]
    POLICY[Egress allowlist + app URL validation + IAM] -.Cần bảo vệ.-> FETCH
    POLICY -.Chặn đường ngoài quyền.-> META
~~~

Trong môi trường thực, **metadata endpoint, hop limits, authentication mechanism và protections** thay đổi theo cloud/provider. Ví dụ, IMDSv2 của AWS dùng session-token mechanism và cấu hình hop limit; nó có thể giảm một số kiểu SSRF, nhưng **không thay thế phân quyền IAM, workload isolation hoặc egress controls**.

### 16.2. Biện pháp phối hợp

- **Workload identity** được cấp theo service/namespace với quyền tối thiểu, tránh node-wide secrets.
- Không dùng credentials có scope quá rộng trong môi trường container.
- Chặn truy cập metadata/control-plane endpoints từ workloads không cần chúng, theo cloud/CNI capabilities.
- App chỉ cho URL đích từ danh sách được quản trị; xử lý redirect và DNS rebinding.
- Kiểm tra destination sau DNS resolution/redirect ở lớp phù hợp, không chỉ dùng regex.
- Tách network management và service data path.
- Giới hạn quyền Kubernetes API và token mounts cho Pods không cần.
- Ghi log bất thường với data minimization, không công khai secrets.
- Test luồng từ workload đại diện trong lab; không dựa vào một biến môi trường đơn độc.

### 16.3. Không chặn metadata một cách mù quáng

Một số hệ thống **cần** trao đổi với provider metadata/identity endpoint để lấy identity hoặc bootstrap. Nếu chặn thiếu hiểu biết có thể làm hỏng AWS/GCP/Azure workload identity hoặc managed agents. Thiết kế cần xác định **Pod nào thực sự cần**, đường đã được provider bảo vệ và phương án identity tốt hơn.

## 17. Container runtime, Docker, Podman và host networking

Kubernetes là môi trường điều phối; Docker/Podman/containerd và Linux networking có những cơ chế cấp thấp khác.

### 17.1. Docker bridge và outbound mặc định

Trong một số Docker bridge networks, container có thể tạo outbound connection thông qua host NAT/firewall khi host có route. **Đặt container vào private bridge không tự có nghĩa “không Internet”**. Mức reachability thực tế phụ thuộc host routing, firewall, network driver và runtime settings.

### 17.2. Docker network=none

Một container chạy với **network disabled** hoặc network namespace không có uplink có thể bị giới hạn outbound mạnh, phù hợp một số batch jobs hoàn toàn offline. Nhưng điều này cũng chặn DNS, service access và telemetry thông thường.

~~~text
Container xử lý file offline
  - Không cần DNS/HTTPS/API/DB
  - network=none (khi runtime cho phép)
  - Input/output qua volume hoặc cơ chế đã quản trị
~~~

Đây là ví dụ kiến trúc, **không phải biện pháp mặc định cho mọi microservice**.

### 17.3. Host networking và đặc quyền mạng

Các workloads dùng **hostNetwork**, privileged mode hoặc capability mạng mạnh như **NET_ADMIN** có thể tương tác với network stack của node theo cách khác Pod bình thường. Core NetworkPolicy **không nên được coi là rào chắn đáng tin cho mọi trường hợp đặc quyền này**, vì hỗ trợ và enforcement tùy CNI.

Cần:
- Giới hạn **privileged/hostNetwork/hostPID/hostPath** theo policy admission.
- Loại bỏ capabilities không cần thiết.
- Sử dụng Pod Security Admission/Policy engine với chuẩn phù hợp.
- Kiểm soát Kubernetes RBAC và quyền tạo/sửa workload.
- Tách node pools cho workloads có đặc quyền nếu cần.
- Bảo vệ host firewall, node IAM và runtime sockets.
- Có audit changes và negative tests khi workload thay labels/host networking.

### 17.4. Một Pod nhiều container

Sidecar proxy, init container và app container có thể dùng chung **Pod network namespace**. Core NetworkPolicy không phân biệt “chỉ app được gọi API, sidecar không được” chỉ bằng việc cả hai nằm cùng Pod. Muốn phân quyền khác nhau có thể phải **tách workload/Pod**, dùng identities ở lớp ứng dụng/proxy hoặc sandbox phù hợp.

### 17.5. Kubelet image pulls không phải app Pod egress

**Image pulls** thường do kubelet/container runtime ở node thực hiện **trước khi Pod chạy**, nên NetworkPolicy egress của Pod **không nhất thiết kiểm soát việc node kéo image**. Cần kiểm soát riêng:
- Node egress tới registries và artifact mirrors.
- Registry authentication và image pull credentials.
- Image signing/verification/admission khi áp dụng.
- Supply-chain policy và SBOM/vulnerability management.
- Node firewall, DNS, caching và control plane networking.

Ngược lại, nếu một **container đang chạy** tự tải binary/package qua Internet, đó là outbound từ workload và cần được quản lý qua egress policy/allowlist tương ứng.

## 18. IPv4, IPv6 và dual-stack egress

Một cluster dual-stack có thể có cả **IPv4 và IPv6 Pod addresses**, Service addresses và egress paths. Nếu tổ chức chỉ kiểm soát **0.0.0.0/0** hoặc IPv4 NAT, workloads có thể tiếp cận đích ngoài bằng **IPv6** nếu route/allow policy tồn tại.

### 18.1. Điều cần kiểm tra

| Vấn đề | IPv4 | IPv6 |
|---|---|---|
| Destination address | A record, IPv4 literals | AAAA record, IPv6 literals |
| Default route | 0.0.0.0/0 | ::/0 |
| NetworkPolicy ipBlock | CIDR IPv4 | CIDR IPv6, cần CNI hỗ trợ đúng |
| Egress translation | SNAT/NAT gateway hoặc proxy | Direct routing, NAT66/NAT64/egress-only gateway tùy nền tảng |
| Firewall | Security group/iptables/eBPF rules | Cần rules/attachment tương ứng cho IPv6 |
| DNS | IPv4 resolver hoặc dual-stack | Resolver và AAAA handling phù hợp |
| Metadata/link-local | Một số địa chỉ riêng | Có những địa chỉ và cơ chế IPv6 theo provider |
| Observability | IPv4 flow logs | Phải kiểm tra IPv6 cũng được thu |

### 18.2. Thiết kế cho dual-stack

1. Inventory các IPv4/IPv6 ranges của Pod, Service, node và external destinations.
2. Xác định CNI và cloud firewall **có thực thi IPv6 NetworkPolicy đúng kỳ vọng không**.
3. Không dùng policy IPv4 allowlist rồi mặc định IPv6 cũng được kiểm soát.
4. Áp route/SG/firewall/proxy egress cho **cả hai address families**.
5. Kiểm tra DNS A/AAAA và cơ chế client chọn address.
6. Test nguồn và destination IPv4/IPv6 riêng.
7. Kiểm tra Service, NodeLocal DNS và NAT64 nếu hệ thống sử dụng.
8. Kiểm tra logging, SIEM pipeline, route changes và failover với IPv6.

**NAT IPv4 không tự chặn IPv6**. Nếu policy egress chỉ quan sát NAT public IPv4, cần bổ sung giám sát ở Pod/CNI hoặc IPv6 egress gateway để không có điểm mù.

## 19. Kubernetes API và workload identity

Pod đôi khi cần gọi **Kubernetes API server** để đọc ConfigMap, metadata hoặc quản lý tài nguyên theo quyền được cấp. Không nên để toàn bộ Pods tự do nói chuyện với API server chỉ vì chúng nằm trong cluster.

### 19.1. Hai lớp quyền cần phối hợp

- **Network reachability:** workload nào có đường TCP/TLS tới Kubernetes API endpoint?
- **Kubernetes RBAC:** service account nào được thực hiện thao tác nào trên tài nguyên nào?

Một Pod có route tới API server nhưng không có permission cần thiết vẫn phải bị API từ chối. Ngược lại, service account có quyền rộng nhưng Pod không cần gọi API có thể được hạn chế egress để giảm rủi ro khi bị chiếm.

### 19.2. Service account token

Một Pod không cần quyền Kubernetes API có thể:
- Sử dụng service account quyền tối thiểu.
- Xem xét **automountServiceAccountToken: false** khi tương thích với workload.
- Giới hạn quyền tạo/đọc secrets, Pods, NetworkPolicy và namespaces qua RBAC.
- Sử dụng workload identity/cloud IAM được quản lý cho những cloud APIs cần thiết.
- Giữ private keys và cloud credentials ra khỏi image/ConfigMap.

**Chặn egress không làm một token bị đánh cắp vô hiệu** nếu attacker có đường khác tới API server. Phải đồng thời quản lý credential scope, thời hạn và access logs.

### 19.3. Cluster service IP và API endpoint

Kubernetes API có thể được truy cập qua một **Service IP**, DNS name hoặc endpoint riêng theo cluster provider. Khi đặt NetworkPolicy, cần kiểm tra **CNI handling của Service VIP và endpoint translation**, không tự sao chép một ipBlock cho cluster khác.

Không mở **0.0.0.0/0:443** chỉ vì một component cần Kubernetes API; điều đó còn cho phép HTTPS tới nhiều destination khác.

## 20. Service mesh và egress theo workload identity

Service mesh có thể cung cấp **mTLS, service identity, traffic routing, authorization và telemetry** giữa workloads hoặc tới một egress gateway. Tuy nhiên, mesh không mặc định thay thế egress network policy.

### 20.1. Kiến trúc hai lớp

~~~mermaid
flowchart LR
    APP[App Pod + Sidecar / Ambient] --> MESH[Mesh Egress Gateway]
    MESH -->|Destination identity/policy| EX[Partner Service]
    NET[CNI NetworkPolicy] -.Chỉ cho đi gateway và đích được duyệt.-> APP
    AUTH[Identity & mTLS policy] -.Xác thực service.-> MESH
    FW[Cloud Firewall / NAT] -.Chặn direct bypass.-> EX
    MESH -.Audit flows.-> SOC[SIEM]
~~~

### 20.2. Hai đường bypass cần kiểm tra

1. **Direct network bypass:** app hoặc Pod có thể tạo kết nối thẳng tới external IP, bỏ gateway.
2. **Proxy configuration bypass:** workload có thể gọi TCP/UDP/protocol hoặc port không được proxy chặn/intercept; hoặc một container có đặc quyền sửa redirect rules tùy mô hình.

Phải có **CNI/network enforcement và permissions** phù hợp. Policy mesh dựa vào sidecar egress gateway chỉ hiệu quả với traffic thật sự qua gateway.

### 20.3. Identity không thay tên miền

Mesh có thể xác thực service identity (ví dụ URI identity trong mTLS) cho internal services. Với public SaaS, gateway có thể chỉ thấy **FQDN/CONNECT/SNI** hoặc cần app-provided metadata. **Một service identity của Pod nguồn** không tự xác thực server đích; client vẫn cần TLS hostname verification và đúng CA trust.

### 20.4. Mô hình rủi ro gateway tập trung

Gateway trở thành:
- Điểm tập trung lưu lượng/chi phí.
- Nơi có thể thấy destination và request metadata.
- Đối tượng cần patch và HA.
- Mục tiêu cho credential abuse hoặc traffic laundering.
- Nguồn log cần redaction/retention và IAM.

Cần capacity budget, autoscaling, token/cert rotation, least privilege và **fail-closed hoặc fail-open theo yêu cầu rõ ràng**. Không để failover tự mở direct Internet route mà không có approval.

## 21. Egress tới cloud, on-premises và các mạng quản trị

Trong môi trường đa VPC/VNet hoặc hybrid, “không Internet” **không có nghĩa an toàn**. Một Pod có thể có route tới data center, control-plane endpoint, VPC peering hoặc shared-services hub.

### 21.1. Phân vùng đích

| Nhóm đích | Ví dụ | Mục tiêu |
|---|---|---|
| Public SaaS được phép | API đối tác | HTTPS identity, domain/IP allowlist, quota |
| Cloud provider APIs | Object storage, queue, KMS | Private endpoint/IAM và endpoint policy theo khả năng |
| Internal application | Catalog/Payments service | Selectors + mTLS + app authorization |
| Database/cache | PostgreSQL/Redis | Chỉ đúng workload, port và DB credentials |
| Control/management | K8s API, bastion, metrics admin | Tối thiểu quyền, không tự mở toàn node subnet |
| On-premises | Directory, ERP, legacy API | Transit/VPN/BGP route và firewall allowlist |
| Update/telemetry | Artifact mirror, metrics collector | Thống nhất package source và retention |
| Untrusted networks | Internet ngoài danh sách | Mặc định không cho |

### 21.2. Private endpoint không tự an toàn

Dùng private endpoint giúp traffic tránh một số đường Internet, nhưng:
- Endpoint vẫn có service access policy và IAM.
- DNS phải phân giải tới đúng private endpoint.
- Consumer/workload identity phải được kiểm tra.
- Route đến private endpoint có thể là alternate bypass của centralized egress.
- Endpoint policy có thể khác giữa regions/accounts.
- Network logs có thể hiển thị private IP thay vì hostname.
- Quyền truy cập đối tượng cloud vẫn do IAM/resource policy quyết định.

### 21.3. Hub-and-spoke và egress tập trung

Khi workload Pod ở spoke VPC đi qua transit hub tới firewall/NAT:
1. NetworkPolicy/CNI tại nguồn kiểm soát Pod egress.
2. VPC subnet routes đưa traffic tới transit/egress attachment.
3. Hub route table chọn next hop phù hợp.
4. Firewall kiểm tra source/destination/port và connection state.
5. NAT/proxy có thể đổi source/destination identity.
6. Return path phải đi qua cùng security context theo thiết kế.
7. Cloud IAM/service identity bảo vệ API đích.

**VPC route có thể tồn tại nhưng NetworkPolicy deny**; ngược lại NetworkPolicy allow mà VPC firewall deny vẫn không kết nối được. Điều này phản ánh defense in depth, không phải mâu thuẫn cấu hình.

## 22. TLS, mTLS, egress identity và kiểm soát dữ liệu

### 22.1. Vì sao chỉ cho TCP/443 chưa đủ?

Một firewall cho **TCP/443 tới toàn bộ Internet** không biết caller đang gọi API được phép hay đưa dữ liệu tới một HTTPS server không được kiểm soát.

Cần xem:
- Đích cụ thể (IP/FQDN) và đúng hostname/TLS certificate.
- Access token có đúng API audience, scope và issuer không.
- Ứng dụng có redirect sang domain khác không.
- Proxy có giới hạn CONNECT destination không.
- Có egress log và audit theo workload/tenant không.
- Dữ liệu gửi đi có thuộc danh mục được phép không.
- Có route proxy/service đích gián tiếp chuyển tới mạng bị cấm không.

### 22.2. TLS interception không phải giải pháp mặc định

Nếu doanh nghiệp muốn phân tích payload outbound HTTPS bằng proxy TLS interception, cần đánh giá:
- Ai có quyền giải mã và xem dữ liệu.
- Root CA dùng cho proxy được cài vào clients nào.
- Private key của proxy CA được bảo vệ ra sao.
- Ảnh hưởng tới mTLS, certificate pinning và compliance.
- Có logging lộ secrets/tokens hoặc nội dung nhạy cảm không.
- Khi proxy lỗi thì fail-open/fail-closed theo tài sản nào.

Có thể chỉ cần **domain allowlist + TLS verification ở ứng dụng + workload identity + audit** nếu payload inspection không phù hợp hoặc vi phạm privacy requirements.

### 22.3. DLP và data classification

Egress control giảm số đường có thể thoát dữ liệu, nhưng **không tự biết nội dung file có nhạy cảm hay không**. Với dữ liệu quan trọng:
- Phân quyền truy cập dữ liệu tại nguồn.
- Không đưa dữ liệu ngoài nhu cầu vào memory/log.
- Quản lý endpoints nhận dữ liệu và contracts.
- Data Loss Prevention (DLP) ở điểm có đủ visibility và quyền phù hợp.
- Audit export/bulk API theo user/tenant.
- Alert unusual volumes, destinations hoặc time patterns.

## 23. Quan sát egress: cần log ở đâu?

Có thể kết hợp:
- **CNI/eBPF flow telemetry** gắn với Pod, namespace, node và policy.
- **NetworkPolicy verdict** allow/deny nếu CNI hỗ trợ logging.
- **Node firewall/conntrack metrics**, theo năng lực môi trường.
- **Cloud VPC flow logs/Firewall logs**.
- **Egress proxy/gateway access and decision logs**.
- **DNS query/response logs**.
- **TLS/service mesh identity và upstream logs**.
- **Application audit** cho từng API call/tenant/action.
- **Cloud audit logs** cho thay đổi NetworkPolicy, SG, IAM, routes và endpoints.

### 23.1. Chuỗi dữ liệu lý tưởng cho một outbound request

~~~mermaid
sequenceDiagram
    participant A as Orders Pod
    participant D as Cluster DNS
    participant C as CNI Policy
    participant G as Egress Gateway
    participant P as Partner API
    A->>D: Resolve api.partner.example
    D-->>A: Allowed destination IP
    A->>C: TCP/TLS outbound request
    C-->>A: Policy decision cho Pod/port/destination
    A->>G: Traffic qua đường được duyệt
    G->>P: TLS tới đúng partner
    P-->>G: Response
    G-->>A: Response đã xác minh theo policy
    Note over A,P: Logs gắn workload, destination, TLS identity, time và decision
~~~

Sơ đồ là luồng logic, không phải thiết kế datapath cụ thể của mọi CNI/gateway. Trên CNI thật, việc kiểm tra NetworkPolicy thường diễn ra **trên đường dữ liệu**, không phải một request/response ứng dụng “hỏi CNI” qua API như hình.

### 23.2. Các trường log nên có

| Trường | Giá trị | Ghi chú |
|---|---|---|
| Timestamp UTC và ingest time | Timeline, log delay | Đồng bộ clocks |
| Pod UID/namespace/workload owner | Định danh nguồn | Pod IP có thể tái sử dụng |
| Node, cluster, environment | Khoanh vùng policy | Một workload có thể chạy nhiều regions |
| Destination IP/port/protocol | Phân tích L3/L4 | Có thể là IP sau NAT/Service translation |
| DNS query name nếu có | Gắn với hostname | Không suy từ DNS là đã kết nối |
| TLS server identity/proxy route | Xác minh external service | Phụ thuộc visibility và privacy |
| Policy ID/version/action | Chứng minh allow/deny | Thay đổi policy có thể làm thay kết quả |
| Egress gateway/NAT mapping | Quy về workload sau SNAT | Có retention và quyền truy cập |
| Connection bytes/duration | Phát hiện exfil/abuse | Kiểm soát false positive |
| IAM/API identity | Phân biệt cloud operation | Không log credential/token |
| Request/correlation ID | Ghép app với gateway | ID do client tự đưa không là identity đáng tin |

### 23.3. Tránh ghi secret vào logs

Không lưu:
- Authorization bearer tokens, API keys, client secrets.
- Full query strings chứa password/signed URLs.
- Nội dung private response/body khi không cần.
- TLS session secrets và private keys.
- Cloud metadata credentials.
- Data fields của user/tenant ngoài nhu cầu điều tra.

**Làm sạch log trong app mà để forward proxy ghi nguyên HTTP headers cũng có thể rò secret.** Cần review mọi điểm giải mã/ghi log.

### 23.4. Không kết luận “không có egress” chỉ từ một hệ thống log

Flow logs có thể sampling, bị trễ, chỉ phản ánh subnet/node IP hoặc không ghi một số loại traffic. Một DNS query không nhất thiết tạo TCP connection; một firewall deny có thể không xuất hiện trong application logs.

Phải kết hợp **policy inventory + data-plane tests + các nguồn telemetry có vị trí phù hợp** trước khi kết luận luồng bị chặn.

## 24. Policy governance: labels, namespaces và RBAC

Khi bảo mật phụ thuộc vào labels, quyền **tạo/sửa Pod, namespaces và policy** trở thành một phần của mạng.

### 24.1. Lỗi nhãn và đặc quyền

Giả sử policy cho phép mọi Pod có label **egress-tier=trusted**. Nếu một developer không thuộc nhóm được phép có thể tự đặt label này cho Pod, họ có thể mở quyền egress ngoài dự kiến.

Cần:
1. Quy định **ai sở hữu nhãn bảo mật** và cách áp chúng.
2. Dùng admission policies để giới hạn hoặc xác minh label trên workload/namespace khi phù hợp.
3. Tách quyền tạo Pods với quyền sửa NetworkPolicy/namespace labels.
4. Kiểm soát privileged, hostNetwork và bypass-capable workloads.
5. Audit policy changes và K8s events liên quan.
6. Kiểm thử thay nhãn không thể tự leo quyền theo mô hình quản trị.

### 24.2. Namespace không tự là security boundary hoàn chỉnh

Namespace giúp tổ chức tài nguyên và hỗ trợ RBAC/NetworkPolicy selectors, nhưng:
- Cluster có thể chia sẻ nodes/kernel.
- Host/network privileged workloads có đường khác.
- Kubernetes API RBAC có thể cho cross-namespace actions.
- ServiceAccounts/Secrets có thể bị cấp quyền sai.
- Ingress/egress đi qua shared gateways.
- Pod-to-Pod communication không tự bị chặn chỉ vì khác namespace.

Cần **NetworkPolicy + IAM/RBAC + admission + runtime controls + node isolation** theo độ nhạy.

### 24.3. Core NetworkPolicy không có explicit deny priority

Một số CNI có chính sách **clusterwide deny hoặc priority ordering** mở rộng. Đây là tính năng vendor-specific; muốn dùng phải:
- Đọc semantics và giới hạn sản phẩm.
- Phân biệt core Kubernetes API với custom resources.
- Kiểm tra xung đột giữa core NetworkPolicy và CNI policy.
- Test kết quả thay vì suy từ thứ tự YAML.

**Không giải thích một NetworkPolicy standard có rule deny:true**, vì core Kubernetes spec không định nghĩa trường đó.

## 25. Triển khai egress control theo giai đoạn

Một lần bật default-deny cho toàn bộ cluster có thể làm hỏng DNS, telemetry, token refresh, image-related runtime operations và các kết nối không được inventory. Thay đổi nên diễn ra có kiểm soát.

### Giai đoạn 1 — Discovery

1. Lập inventory **namespace/workload/service owner**.
2. Thu outbound destinations từ app traces, DNS, proxy và CNI/cloud flow logs.
3. Phân loại đích **must-have, optional, deprecated, unknown**.
4. Xác định traffic **Pod vs Node**, Pod-to-Pod vs Internet/hybrid.
5. Ghi IP/FQDN, port/protocol, identity, tần suất, TLS và dữ liệu di chuyển.
6. Phân biệt flows chỉ xuất hiện lúc startup, nightly jobs, failover hoặc certificate renewal.
7. Xem IPv6, direct IP, DoH, NodeLocal DNS, PrivateLink và service mesh path.
8. Lập baseline security/availability trước khi thay đổi.

### Giai đoạn 2 — Policy design

1. Chọn phạm vi pilot một workload/namespace ít rủi ro.
2. Định nghĩa **default deny + minimum explicit allow**.
3. Viết DNS exceptions đúng CNI/topology.
4. Cho internal services theo **pod/namespace selectors** và ingress counterpart.
5. Cho external SaaS qua **proxy/FQDN policy** khi IP động.
6. Giữ cloud metadata/control-plane access chỉ cho workload cần.
7. Định nghĩa metrics, logs, certificates và secret rotation paths.
8. Review RBAC/admission và ai có quyền sửa labels/policies.
9. Có owner, ticket, risk acceptance và rollback.

### Giai đoạn 3 — Test/staging

1. Chạy **positive tests** cho mọi flows cần.
2. Chạy **negative tests** cho destination không được cấp quyền.
3. Kiểm tra both IPv4/IPv6.
4. Kiểm tra DNS with/without cache, TCP/UDP.
5. Kiểm tra startup jobs, scheduled tasks, token renew, certificate rotation.
6. Kiểm tra egress gateway HA và multi-node/multi-AZ.
7. Đo app SLO, latency, timeout/error rates và NAT/proxy capacity.
8. Thu evidence từ CNI/firewall/proxy/app; điều chỉnh policy nhỏ nhất cần thiết.

### Giai đoạn 4 — Rollout production

1. Deploy canary/nhóm nhỏ và xác minh **policy thật được CNI thực thi**.
2. Theo dõi request success, 4xx/5xx, latency, DNS failures, network denies.
3. Không mở allow-all khi có một lỗi chưa xác định.
4. Cập nhật exceptions hẹp có hạn dùng nếu nhu cầu khẩn cấp được phê duyệt.
5. Dùng safe rollback về profile đã được duyệt khi cần khôi phục.
6. Tách incident availability khỏi incident security để không đánh đổi vô ý.
7. Kiểm tra policy parity giữa regions/node pools và DR clusters.

### Giai đoạn 5 — Vận hành

- Review unknown destinations và exceptions hàng tháng/quý theo risk.
- Giám sát policy drift, egress volume/destination anomalies.
- Theo dõi CNI upgrades, Kubernetes versions, DNS changes và node AMI/image.
- Kiểm tra workload mới được thừa hưởng default-deny.
- Tái kiểm thử các **deny flows**, không chỉ app happy path.
- Có alert cho **missing telemetry** và config changes không phê duyệt.

## 26. Kịch bản thiết kế mẫu: Orders API chỉ được gọi ba đích

Giả định:
- Namespace **orders-prod** chạy Pods có label **app=orders-api**.
- API cần truy vấn **DNS của cluster**.
- API gọi Catalog Pods ở **catalog-prod**, port TCP/8443.
- API gọi một partner HTTPS cố định trong lab tại **198.51.100.10:443**.
- Không cần kết nối trực tiếp Dev, database của nhóm khác hoặc toàn Internet.

### 26.1. Mục tiêu

~~~text
ALLOW: orders-api -> cluster DNS UDP/TCP 53
ALLOW: orders-api -> catalog-prod/catalog-api TCP/8443
ALLOW: orders-api -> documented partner IP TCP/443
DENY:  orders-api -> other outbound destinations
REQUIRE: Catalog ingress policy + TLS/mTLS + authZ riêng
OBSERVE: DNS, network verdict, gateway/app traces
~~~

### 26.2. Tập chính sách cần thiết

1. **default-deny-egress** chọn tất cả Pods trong orders-prod.
2. **orders-allow-cluster-dns** chỉ chọn Orders Pods và đúng DNS targets.
3. **orders-allow-catalog** chọn đúng Catalog Pods ở namespace khác.
4. **orders-allow-external-partner-ip** cho đúng IP/port lab.
5. Chính sách **ingress tại Catalog**, nếu Catalog bị ingress isolated.
6. Firewall/VPC routes và TLS/authorization thực tế.

Các policy ở mục 7–10 **cùng tồn tại** để hợp nhất quyền. Tuy nhiên, nếu có một policy cũ cho **egress to 0.0.0.0/0** và cũng chọn Orders Pods, tập quyền sẽ rộng hơn dự kiến. Phải **inventory tất cả policies** và kiểm chứng tại runtime.

### 26.3. Ma trận quyết định

| Source | Destination | Expected network | Expected application |
|---|---|---|---|
| orders-api | Cluster DNS | Allow 53 UDP/TCP | Resolver trả dữ liệu theo policy |
| orders-api | catalog-api:8443 | Allow | mTLS/token + quyền nghiệp vụ hợp lệ |
| orders-api | 198.51.100.10:443 lab | Allow | TLS hostname verify và partner authorization |
| orders-api | dev-api | Deny | Không chạy đến bước app khi network chặn |
| orders-api | DB của tenant khác | Deny | Nếu có alternate route, DB auth vẫn deny |
| orders-api | Internet ngoài danh sách | Deny | Không có connection được phép |
| random Pod orders-prod | Partner | Deny trừ khi có policy cho Pod đó | Không tự dùng credential Orders |
| orders-api | Node metadata endpoint ngoài quyền | Deny theo thiết kế cloud/CNI | Workload IAM cũng không cấp quyền thừa |

### 26.4. Điều cần kiểm tra trong môi trường thật

- DNS Pods có đúng labels và traffic path?
- CNI hỗ trợ core NetworkPolicy egress chưa?
- NetworkPolicy có áp với node-local DNS hoặc proxy redirect không?
- Catalog namespace có label đúng và inbound policy?
- HTTPS traffic tới partner IP có dùng đúng hostname/certificate?
- Backend worker/init container có startup dependencies khác không?
- Node egress/image pulls có bị tác động bởi firewall cloud không?
- Có IPv6 hoặc alternate egress gateway bypass không?
- Có app-level HTTP redirect sang đích khác không?

**Không biến ví dụ thành “policy production hoàn chỉnh” nếu chưa kiểm thử những điểm trên.**

## 27. Các lệnh kiểm tra an toàn trong Kubernetes lab

Các lệnh sau là **read-only**, trừ khi người học cố ý chạy phép thử kết nối từ Pod hiện có. Chúng chỉ dùng trong cluster đã được cấp quyền. Thay **orders-prod**, tên Pod và labels cho đúng lab; không dùng kết quả chứa topology/secrets để đăng công khai.

### 27.1. Inventory NetworkPolicies

~~~bash
# Xem các policy trong namespace lab được phép
kubectl get networkpolicies -n orders-prod

# Xem chi tiết rules và selectors
kubectl describe networkpolicy default-deny-egress -n orders-prod

# Xem namespaces cùng labels để đối chiếu policy
kubectl get namespaces --show-labels
~~~

### 27.2. Đối chiếu Pod labels và policy selectors

~~~bash
# Chỉ đọc Pod selectors; tên label là giả định ở ví dụ
kubectl get pods -n orders-prod -l app=orders-api --show-labels
kubectl get pods -n catalog-prod -l app=catalog-api --show-labels

# Xem endpoint thực của Catalog Service
kubectl get services,endpointslices -n catalog-prod
~~~

Labels trên Service/Pod có thể thay đổi sau rollout. **Một NetworkPolicy không tự chọn Pod theo Service name**; cần biết Pod thực tế được chọn và CNI đang enforcing.

### 27.3. Kiểm tra RBAC của người thao tác

~~~bash
# Kiểm tra quyền đang dùng; không làm thay đổi cluster
kubectl auth can-i get networkpolicies -n orders-prod
kubectl auth can-i create networkpolicies -n orders-prod
kubectl auth can-i patch networkpolicies -n orders-prod
~~~

Câu trả lời thể hiện quyền theo cơ chế RBAC/admission ở ngữ cảnh đang kiểm tra; **không chứng minh người dùng không có quyền thông qua role/credential khác**.

### 27.4. Kiểm tra DNS từ Pod hiện có và được phép

~~~bash
# Ví dụ: Pod có sẵn nslookup; thay tên Pod bằng Pod thật trong lab
kubectl exec -n orders-prod orders-api-lab-0 -- \
  nslookup catalog-api.catalog-prod.svc.cluster.local
~~~

Một container tối giản có thể **không có nslookup**. Không cần cài tooling vào production image chỉ để test. Có thể dùng dedicated test workload trong lab với chính sách và quyền rõ, nhưng **Pod test phải thực sự khớp selectors của workload được kiểm tra**, nếu không kết quả không đại diện.

### 27.5. Một request HTTPS nhỏ tới endpoint được phép

~~~bash
# Lab-only: endpoint minh họa chưa tồn tại
kubectl exec -n orders-prod orders-api-lab-0 -- \
  curl --silent --show-error --connect-timeout 2 --max-time 5 \
  -I https://api.partner.example/
~~~

Đường kiểm chứng này phụ thuộc container có curl và DNS/routing thực tế. **Không dùng -k/--insecure để bỏ TLS certificate verification** nhằm ép test thành công. Với chính sách allow theo IP, hostname giả định có thể không phân giải tới IP đó; cần lab server/certificate và DNS hợp lệ để thực sự kết luận.

### 27.6. Xác định nguyên nhân mà không sửa mò

Nếu test lỗi, lần lượt kiểm tra:
1. Application DNS và cấu hình resolv.conf phù hợp environment.
2. Pod labels, namespace labels, policyTypes và tất cả matching policies.
3. CNI plugin có enforce egress không, NodeLocal DNS path.
4. Destination Pod labels, targetPort và **ingress policy**.
5. VPC route/SG/firewall/egress gateway/NAT.
6. TLS/HTTP response và application authorization.
7. IPv6, service mesh, proxy/redirect, hostNetwork.
8. CNI/firewall/app logs trong cùng timestamp.

**Không xoá toàn bộ NetworkPolicies để chẩn đoán** trên môi trường production; việc này mở rộng reachability không kiểm soát.

## 28. Ma trận kiểm thử egress control

Mỗi phép thử cần **test owner, environment, namespace, workload/Pod UID, CNI/provider version, source/destination, policy version, timestamp và evidence**. Chỉ test trên lab/staging hoặc production theo change window được duyệt.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| E01 | Pod mới trong namespace default deny | Egress bị cô lập nếu không có allow khác | Policy matching + CNI verdict |
| E02 | Orders Pod → DNS UDP 53 | Allowed tới resolver đúng | DNS + CNI flow log |
| E03 | Orders Pod → DNS TCP 53 | Allowed đúng resolver | DNS/TCP test + log |
| E04 | Orders Pod → resolver ngoài policy | Denied | Network verdict |
| E05 | Orders Pod → Catalog 8443 | Allowed trên network | CNI + app request |
| E06 | Catalog ingress policy thiếu | Connection bị từ chối dù Orders egress allow | Ingress/egress policy diff |
| E07 | Orders Pod → Dev Pod | Denied | CNI deny + label evidence |
| E08 | Orders Pod → partner fixed IP:443 | Allowed trong lab theo IP+TLS policy | Flow + TLS verify |
| E09 | Orders Pod → partner khác:443 | Denied | Network verdict |
| E10 | Một Pod không chọn bởi allow rule → partner | Denied | Pod selector + flow |
| E11 | Một allow-all policy cũ chọn cùng Pod | Phát hiện unintended union | NetworkPolicy inventory |
| E12 | namespaceSelector + podSelector cùng một to | Chỉ chọn Pod đúng namespace | Label + connectivity test |
| E13 | Hai to elements riêng (OR) | Review thấy quyền rộng hơn ý định | Policy semantic test |
| E14 | DNS đi qua NodeLocal DNSCache | Quyết định đúng trên CNI/provider | DNS path + policy |
| E15 | Pod dùng IPv6 đến external endpoint | Bị deny/allow đúng policy IPv6 | IPv6 flow + logs |
| E16 | Hardcoded IP bypass DNS | Vẫn bị network policy kiểm soát | Direct-IP negative test trong lab |
| E17 | DoH/DoT ngoài danh sách | Bị chặn hoặc qua resolver được duyệt | Egress/proxy logs |
| E18 | External FQDN đổi A/AAAA | Policy/Proxy không mở quá rộng, vẫn hoạt động theo contract | DNS TTL + gateway decision |
| E19 | Pod tìm kết nối direct bỏ forward proxy | Direct path bị chặn | CNI + gateway logs |
| E20 | Egress gateway failover | Luồng hợp lệ phục hồi, denied vẫn deny | HA test, app SLO |
| E21 | External HTTPS certificate sai | Client từ chối dù TCP/443 được phép | TLS validation logs |
| E22 | mTLS service identity sai | Service đích từ chối theo policy | Mesh auth logs |
| E23 | Cloud metadata từ workload không được phép | Bị cô lập bằng policy theo thiết kế | Policy evidence trong lab, không đọc credentials |
| E24 | IAM/cloud API permission vượt scope | Bị resource/IAM policy từ chối | Cloud audit |
| E25 | Node image pull từ registry được duyệt | Node egress hoạt động ngoài phạm vi Pod policy | Node registry logs |
| E26 | App tải package trực tiếp trong Pod | Chỉ đến repository đã duyệt hoặc denied | CNI/proxy logs |
| E27 | Privileged/hostNetwork Pod không được tạo trái phép | Admission/RBAC từ chối | Admission audit |
| E28 | Pod-to-Pod traffic cùng node | Core policy được CNI thực thi như kỳ vọng | CNI verdict + app |
| E29 | Namespace label bị sửa trái quyền | Admission/RBAC phát hiện/chặn | K8s audit |
| E30 | Cloud NAT đổi source IP | Có mapping và attribution đúng | NAT + proxy + Pod metadata |
| E31 | Partner rate limit sau NAT shared IP | Quota/identity không gây ảnh hưởng ngoài policy | Partner logs + counters |
| E32 | Private service endpoint bypass Internet gateway | Được inventory và kiểm soát riêng | Routes + endpoint policy |
| E33 | Traffic on-prem qua transit hub | Firewall/identity đúng ở từng hop | Route + VPN/flow logs |
| E34 | DNS cache/TTL thay đổi sau rollout | Không tạo false deny kéo dài | DNS/cache/gateway telemetry |
| E35 | NetworkPolicy object tạo nhưng CNI không enforce | Phát hiện được kiểm thử âm tính | Runtime flow evidence |
| E36 | SIEM/CNI logging bị ngắt | Có alert telemetry loss | Collector/pipeline health |
| E37 | Autoscaling thêm Pods/nodes | Pod mới có cùng egress restrictions | Rollout/canary test |
| E38 | Multi-AZ/region failover | Security parity cho allowed/denied flows | Failover matrix |
| E39 | Egress proxy/NAT quá tải trong POC hợp lệ | Resource/SLO trong budget, không fail-open ngoài policy | CPU/conntrack/latency |
| E40 | Thêm policy chỉ deny rỗng khi vẫn có allow khác | Quyền allow cũ vẫn còn theo union semantics | Matching policies + test |

**Đừng ghi PASSED nếu chưa chạy và thu bằng chứng.** Nếu thiếu CNI flow logs, cần kết hợp policy inventory, route/firewall telemetry và test ở đúng source Pod. Các ca liên quan metadata hoặc tài nguyên nhạy cảm chỉ dùng **đích giả định/được quản lý** và xác minh quyết định chặn, **không lấy credential**.

## 29. Phân tích lỗi: tại sao Pod mất outbound?

### 29.1. DNS timeout sau default deny

**Khả năng:** không có DNS allow rule; CoreDNS label khác; NodeLocal DNSCache dùng địa chỉ/đường khác; UDP/TCP 53 chưa mở đúng; CNI áp policy sau NAT khác kỳ vọng.

**Kiểm tra:** Pod resolv.conf, label của DNS Pods/namespace, DNS service/endpoints, NodeLocal DNS behavior và CNI verdict. Không bật cho phép DNS 0.0.0.0/0:53 chỉ để xử lý nhanh.

### 29.2. DNS thành công nhưng HTTPS timeout

**Khả năng:** IP đích không nằm trong ipBlock allowlist, FQDN đổi IP, IPv6 được chọn mà policy thiếu, route/SNAT/firewall lỗi hoặc proxy chưa chạy.

**Kiểm tra:** A/AAAA answers, destination IP/port thực tế, policy matching, egress gateway, cloud route/SG và TLS handshake. DNS success **không tự chứng minh** TCP connectivity.

### 29.3. Pod A gọi Pod B bị deny dù A có allow egress

**Khả năng:** B bị ingress isolated; selector tại nguồn/destination không khớp; Service targetPort khác policy; traffic qua mesh/port rewrite; CNI không thực thi như giả định.

**Kiểm tra:** hai phía NetworkPolicy, namespace/Pod labels, Service endpoint selection, targetPort, mesh redirects và flow logs.

### 29.4. Một Pod bị chặn, Pod khác cùng namespace vẫn được phép

**Khả năng:** Pod labels khác, không được chọn bởi allow policy, sidecar/inits khác, RBAC/admission thay labels hoặc node/CNI datapath khác.

**Kiểm tra:** Pod UID, labels, deployment revision, matched policies và node placement. Đừng dựa chỉ vào tên namespace.

### 29.5. Policy default deny đã tạo nhưng Internet vẫn thông

**Khả năng:**
- CNI chưa hỗ trợ/enforce NetworkPolicy.
- Có allow-all egress policy khác chọn Pod.
- Pod test không thuộc namespace/selector đã cấu hình.
- Traffic xuất phát từ **node/hostNetwork** chứ không phải Pod thường.
- Có đường proxy/service trung gian vẫn được allow.
- Plugin có semantics đặc thù với source/destination NAT.

**Kiểm tra:** matching policies, CNI feature support, Pod network namespace, logs và một negative test an toàn. **Kubernetes API chấp nhận NetworkPolicy không chứng minh đã chặn.**

### 29.6. App chạy trên một node nhưng lỗi node khác

**Khả năng:** CNI agent/deployment lỗi ở một node, MTU/route/iptables/eBPF state khác, node firewall/SG khác hoặc NodeLocal DNS không chạy trên node đó.

**Kiểm tra:** node identity, CNI status/metrics, per-node DNS/proxy, interface routes, cluster events và policy parity.

### 29.7. Egress proxy trả 403 cho partner hợp lệ

**Khả năng:** domain không khớp allowlist, proxy yêu cầu client identity, CONNECT port không được duyệt, DNS/SNI/Host bất đồng hoặc certificate policy.

**Kiểm tra:** proxy logs đã redacted, authenticated caller, hostname, URI/port, TLS verification và contract. Không tắt toàn proxy authorization vì một tenant lỗi.

### 29.8. Tăng 5xx/latency sau egress centralization

**Khả năng:** traffic hairpin cross-AZ, egress gateway quá tải, NAT port exhaustion, connection tracking, TLS handshakes lặp, DNS latency hoặc retries không giới hạn.

**Kiểm tra:** p95/p99 app, connection reuse, conntrack/NAT capacity, proxy CPU, route placement và timeout budgets. Tối ưu theo đo lường; không mở direct Internet không phê duyệt.

### 29.9. Logs không hiển thị Pod IP

**Khả năng:** SNAT tại node/gateway, proxy connection hoặc CNI overlay khiến source ở điểm quan sát khác Pod IP.

**Kiểm tra:** node/Pod mapping theo thời điểm, NAT tables/flow logs, proxy identity và application correlation. Không quy một public egress IP cho một user duy nhất.

### 29.10. Từ chối được IPv4 nhưng vẫn kết nối qua IPv6

**Khả năng:** IPv6 routes và policies chưa bật/enforce, AAAA record được client ưu tiên, firewall chỉ cấu hình IPv4.

**Kiểm tra:** IPv6 Pod IP/destination, ::/0, CNI support, IPv6 SG/firewall và egress gateway. Không coi IPv4-only negative test là đủ.

## 30. Runbook khi phát hiện outbound trái phép

### Giai đoạn A — Phát hiện và xác minh

1. Xác định **source workload/Pod UID, namespace, node, cluster và owner**.
2. Ghi destination IP/FQDN/port, timestamp, bytes, protocol và egress path.
3. Xác định policy ID/version, CNI verdict, proxy route, NAT mapping và DNS evidence.
4. Phân loại: traffic hợp lệ chưa inventory, config drift, lỗi app, SSRF, credential misuse hay nghi ngờ container compromise.
5. Kiểm tra cloud control plane/SG/route, Kubernetes policy/admission và service mesh.
6. Xác định có truy cập dữ liệu nhạy cảm, cloud metadata, partner API hoặc network management không.
7. Bảo toàn chứng cứ, tránh xuất token/private key trong log hoặc báo cáo.

### Giai đoạn B — Khoanh vùng và giảm tác động

- **Traffic ngoài quyền:** điều chỉnh allowlist hoặc cô lập workload theo incident policy; không xóa toàn egress policies.
- **Compromised Pod:** phối hợp incident response, phân tích ảnh hưởng và thay Pod/image/credentials theo quy trình; bảo vệ evidence trước khi terminate khi phù hợp.
- **SSRF:** thu hẹp URL allowlist, DNS/redirect handling, egress gateway và IAM.
- **Metadata credential exposure:** đánh giá/rotate/revoke credentials, thu hẹp IAM/metadata access theo provider.
- **Route/NetworkPolicy drift:** rollback về policy an toàn, chặn privileged/hostNetwork bypass.
- **NAT/proxy abuse:** giới hạn consumer, bổ sung identity/quotas và tăng telemetry.
- **False-positive deny:** mở exception hẹp, owner/timebound, rollout canary và review.

### Giai đoạn C — Khôi phục

1. Xác nhận workload hợp lệ có thể gọi **đúng DNS và destinations được duyệt**.
2. Xác nhận trực tiếp tới denied destinations vẫn bị từ chối.
3. Kiểm tra app/authN/authZ, TLS certificate verification và CNI enforcement.
4. Kiểm tra egress gateway/HA, NAT, proxy logs và data-plane health.
5. Chạy negative tests ở Pod/namespace/node khác nhau và IPv4/IPv6.
6. Theo dõi error rate, p95/p99, retries và outbound bytes.
7. Xác minh policy không mở rộng đường tới metadata, management hoặc Dev/Prod ngoài scope.

### Giai đoạn D — Hậu kiểm

Ghi:
- Root cause và trust boundaries bị ảnh hưởng.
- Vì sao egress destination không có owner hoặc policy drift.
- Có CNI/NetworkPolicy enforcement blind spot hay không.
- Thời gian phát hiện/khắc phục, dữ liệu và workloads bị ảnh hưởng.
- Control nào thiếu: app URL validation, IAM, admission, proxy, DNS monitoring.
- Test hồi quy và người chịu trách nhiệm hoàn tất.
- Bản cập nhật policy-as-code, runbook, inventory và monitoring.

**Một cảnh báo bị tắt hoặc một outbound IP bị chặn không đủ để tuyên bố đóng sự cố**, nếu alternate route/credentials vẫn cho phép hành vi cũ.

## 31. Tình huống phân tích và đáp án gợi ý

### Tình huống A — Tạo default-deny nhưng không chặn được Internet

Một namespace đã có default-deny-egress; Pods vẫn kết nối HTTPS ra Internet.

**Đáp án:** kiểm tra có NetworkPolicy khác allow 0.0.0.0/0 chọn cùng Pod không, CNI có enforce egress không, Pod đang test có thuộc namespace không và có phải hostNetwork không. Core policies có **union allow semantics**, không có thứ tự deny override.

### Tình huống B — Orders API không phân giải được DNS

Orders Pods vừa bật default deny, cấu hình resolver trỏ DNS Service IP nhưng không resolve hostname.

**Đáp án:** cho phép egress tới đúng DNS path, xét CoreDNS labels, TCP/UDP 53, ClusterIP NAT và NodeLocal DNSCache. Không mở DNS ra mọi resolver công khai.

### Tình huống C — Policy chọn hai điều kiện nhưng mở rộng hơn mong muốn

Một người viết hai mục to riêng: một namespaceSelector cho namespace production, một podSelector cho app=payments.

**Đáp án:** hai entries là OR; không phải AND. Để chọn Payment Pods **trong** namespace production, đặt namespaceSelector và podSelector **trong cùng phần tử to**.

### Tình huống D — App gọi Catalog được trên Service name nhưng fail ở Pod IP

NetworkPolicy cho ipBlock ClusterIP, còn CNI thực thi sau DNAT và thấy Pod IP.

**Đáp án:** service translation và IP semantics khác kỳ vọng. Dùng destination selectors nếu phù hợp, kiểm tra CNI enforcement và test đường thật; không mặc định ipBlock ClusterIP portable.

### Tình huống E — DNS allow nhưng egress qua DoH

Workload bị chặn UDP/53 ra Internet nhưng có allow-all TCP/443; ứng dụng chọn resolver DoH riêng.

**Đáp án:** Core NetworkPolicy không hiểu đây là DNS traffic ở HTTPS/443. Cần egress allowlist/proxy/FQDN policy và quản trị resolver/DoH của ứng dụng, không chỉ port 53.

### Tình huống F — Partner thay IP thường xuyên

API đối tác dùng CDN nên các IP thay đổi, trong khi policy ipBlock chỉ có một IP.

**Đáp án:** dùng egress gateway/proxy hoặc FQDN policy có xử lý DNS TTL, CNAME, A/AAAA và TLS identity. Không mở 0.0.0.0/0:443 nếu không có rủi ro/approval rõ ràng.

### Tình huống G — Worker A bị leak token nhưng không có outbound Internet

Một attacker có quyền trong Pod vốn chỉ gọi Shared API; Shared API lại cho phép upload/log ra Internet thay mặt client.

**Đáp án:** egress isolation trực tiếp có hiệu lực nhưng **trusted intermediate** trở thành proxy dữ liệu. Cần authorization tại Shared API, giới hạn phương thức/đích, identity, quotas và audit.

### Tình huống H — Proxy dùng HTTPS_PROXY nhưng app vẫn gọi Internet trực tiếp

NetworkPolicy cho direct outbound rộng; chỉ yêu cầu developer đặt biến môi trường proxy.

**Đáp án:** proxy config không cưỡng chế security. Chặn direct egress tại CNI/SG/firewall và chỉ cho Pod đi gateway/allowed destinations; kiểm thử direct bypass.

### Tình huống I — CNI flow logs chỉ hiện node IP

Pods dùng SNAT trước khi traffic rời node, SOC không xác định được nguồn gây outbound bất thường.

**Đáp án:** kết hợp CNI Pod identity telemetry, NAT mapping, node/Pod UID/time và gateway logs. Không chỉ dùng public source IP để xác định một workload.

### Tình huống J — Docker bridge container được cho là private

Một container trên bridge network có thể curl Internet nhờ host NAT; đội vận hành tưởng bridge mặc định offline.

**Đáp án:** bridge là mô hình kết nối, không là egress deny. Cần host firewall/runtime network policy, isolated network hoặc proxy restrictions theo use case.

### Tình huống K — App chạy được nhưng Pod mới pull image thất bại

Node firewall bị khóa outbound registry, khiến kubelet không kéo image; NetworkPolicy của Pod không thay đổi.

**Đáp án:** image pull do **node/runtime** thực hiện. Kiểm soát/cho phép registry ở node egress riêng, kiểm tra mirror/auth; không nới Pod NetworkPolicy vô ích.

### Tình huống L — SSRF tới cloud metadata

Ứng dụng có chức năng tải URL do user nhập; một request không được kiểm soát có thể tới metadata endpoint theo route cloud.

**Đáp án:** validate allowlist URL/redirect/DNS, hạn chế metadata reachability ở mạng, dùng workload IAM scope nhỏ và provider protections. Test denial an toàn, **không truy xuất credentials**.

### Tình huống M — Client IPv6 bypass proxy IPv4

Pod dual-stack nhận AAAA record và kết nối trực tiếp IPv6; policy chỉ cho/giới hạn 0.0.0.0/0.

**Đáp án:** cần IPv6 NetworkPolicy/CNI support, ::/0 route enforcement và cloud firewall tương đương, cũng như gateway hỗ trợ IPv6 hoặc chặn đúng cơ chế.

### Tình huống N — Label được dùng làm quyền ưu tiên

Namespace policy cho Pod label **egress-tier=trusted** ra ngoài, nhưng developer tự gắn label đó cho Deployment của mình.

**Đáp án:** labels là dữ liệu có thể bị người có quyền create/patch Pod thay đổi. Cần RBAC/admission guardrails, bảo vệ ownership và policy approval; không coi label là credential tự xác thực.

### Tình huống O — Egress gateway lỗi khiến toàn API mất traffic

Một gateway duy nhất xử lý outbound payment; khi nó lỗi, mọi service timeout. Team muốn tạm mở direct Internet cho tất cả Pods.

**Đáp án:** cần HA/multi-AZ, timeout, failover và risk-defined fail-closed/fail-open. Không mở direct egress diện rộng thiếu phê duyệt; ưu tiên khôi phục gateway hoặc safe fallback được thiết kế.

### Tình huống P — NetworkPolicy chặn Dev→Prod nhưng Cloud Private Endpoint mở

Dev không có đường TCP trực tiếp tới Prod Pod, nhưng có thể gọi Prod API qua private endpoint đã chia sẻ.

**Đáp án:** đây là alternate application/network path ngoài Pod-to-Pod route. Kiểm soát endpoint/IAM/API authZ, inventory private connectivity và test access từ Dev.

### Tình huống Q — Pod được egress TCP/443 nhưng TLS báo lỗi

Kết nối TCP đi được qua firewall, nhưng client nhận chứng chỉ không khớp hostname.

**Đáp án:** NetworkPolicy đang làm đúng chức năng L3/L4. Cần sửa DNS/SNI/certificate/trust hoặc route đến đúng endpoint, **không tắt TLS verification**.

### Tình huống R — Default deny khiến Prometheus mất metrics

Scraper hoặc Pod metrics endpoint cần outbound telemetry/remote-write nhưng policy chưa có exception.

**Đáp án:** inventory đúng chiều traffic: scraper → endpoint là ingress của endpoint, còn remote write từ agent là egress. Mở đúng nguồn/đích/port và identity, không cho toàn namespace Internet chỉ để thu metrics.

## 32. Các sai lầm thường gặp

1. **Coi NetworkPolicy là firewall chạy trong container.** Nó là API khai báo, CNI phải thực thi.
2. **Có object NetworkPolicy nghĩa chắc chắn đã chặn traffic.** Cần runtime enforcement test.
3. **Nhầm container với Pod.** Các container cùng Pod thường chia sẻ network namespace.
4. **Quên policyTypes: Egress.** Không đạt isolation mong muốn trong một số cấu hình.
5. **Chỉ tạo default deny rồi cho rằng mọi external traffic bị deny tuyệt đối.** Có thể còn allow policies khác.
6. **Coi Core NetworkPolicy có deny priority.** Core API hợp nhất allow rules.
7. **Đặt namespaceSelector và podSelector ở hai to entries nhưng muốn AND.** Thực tế là OR.
8. **Chọn namespace rộng khi chỉ cần một service.** Tăng lateral reachability.
9. **Tin labels bất biến.** Người có RBAC sửa Pod/namespace có thể thay selectors.
10. **Chỉ kiểm tra egress của source mà quên ingress của destination.** Luồng vẫn fail.
11. **Dùng ipBlock ClusterIP mà không kiểm tra NAT/CNI semantics.** Kết quả không portable.
12. **Cho DNS ra toàn Internet để xử lý một lỗi.** Mở thêm resolver/exfil path.
13. **Quên TCP/53 hoặc NodeLocal DNSCache.** DNS hoạt động không ổn định.
14. **Coi DNS allow là FQDN policy.** Core NetworkPolicy không kiểm soát domain.
15. **Dùng FQDN allowlist nhưng bỏ TLS hostname verification.** Không xác thực đúng endpoint.
16. **Chỉ cho HTTPS 443 tới 0.0.0.0/0 rồi gọi là least privilege.** Destination scope quá rộng.
17. **Bỏ qua DoH/DoT và hardcoded IP.** DNS policy có thể bị bypass.
18. **Tin HTTP_PROXY/HTTPS_PROXY tự cưỡng chế outbound.** Container có thể direct-connect nếu mạng cho phép.
19. **Coi egress gateway tự chặn mọi đường khác.** Phải kiểm tra direct route và alternate paths.
20. **Coi NAT là hệ thống kiểm tra identity.** SNAT chỉ chuyển địa chỉ/port.
21. **Không theo dõi NAT port exhaustion.** Có thể gây timeout dù policy đúng.
22. **Gộp Pod IP với external source identity.** Proxy/SNAT có thể che nguồn.
23. **Quên node egress cho image pulls.** Pod NetworkPolicy không kiểm soát toàn node.
24. **Dùng hostNetwork/privileged nhưng dựa hoàn toàn vào Pod policy.** Có bypass hoặc semantics đặc biệt.
25. **Cho workload NET_ADMIN không cần thiết.** Làm tăng khả năng sửa mạng.
26. **Coi namespace tự là security boundary hoàn chỉnh.** Cần RBAC, admission, isolation và identity.
27. **Cho Pod tới Kubernetes API mà bỏ RBAC.** Network allow không thay permissions.
28. **Không kiểm tra cloud metadata và workload identity.** SSRF/credential risk.
29. **Chặn metadata bừa bãi mà không hiểu cloud identity flows.** Làm hỏng app/bootstrap.
30. **Tin PrivateLink/private endpoint tự bảo vệ dữ liệu.** Vẫn cần IAM/authorization.
31. **Chỉ bảo vệ IPv4.** IPv6 có thể tạo đường egress khác.
32. **Chỉ xem DNS logs để kết luận không exfil.** App có thể dùng direct IP/cache/DoH.
33. **Chỉ xem cloud flow logs ở NAT IP.** Khó quy về Pod.
34. **Không có policy owner và expiry cho ngoại lệ.** Allowlist phình to theo thời gian.
35. **Không thử startup/scheduled jobs khi rollout.** App có thể lỗi sau nhiều giờ/ngày.
36. **Coi 403 HTTP là lỗi network.** Có thể là app authorization đúng.
37. **Coi ping lỗi là network policy đã chặn mọi TCP/UDP.** ICMP có semantics khác và test chưa đủ.
38. **Không thử multi-node, multi-AZ, failover.** Policy/route có thể drift.
39. **Chỉ chạy positive connectivity tests.** Không biết denied destinations có đang mở.
40. **Tắt toàn bộ policies để khôi phục một ứng dụng.** Mở blast radius không kiểm soát.

## 33. Checklist triển khai egress control cho container

- [ ] Xác định **workload/Pod/namespace owners, data classification và destinations**.
- [ ] Tách Pod egress với node/runtime egress, image pulls và control plane flows.
- [ ] Có inventory IPv4/IPv6, Pod CIDRs, Service IPs, cloud routes và alternate paths.
- [ ] Đã xác minh CNI thực thi **Kubernetes NetworkPolicy egress** đúng tính năng mong muốn.
- [ ] Áp **default-deny egress** ở namespace/workload theo rollout được phê duyệt.
- [ ] Đã inventory mọi policy khác chọn cùng Pod và union allow semantics.
- [ ] Cho DNS chỉ tới resolver được duyệt; xét UDP/TCP 53 và NodeLocal DNSCache.
- [ ] Đã xác minh namespace labels, Pod labels, selectors và RBAC/admission.
- [ ] Dùng selector chung namespace/cross-namespace đúng semantics AND/OR.
- [ ] Với destination Pod bị ingress isolated, đã cho phép inbound tương ứng.
- [ ] Kiểm tra Service VIP, targetPort, DNS và NAT ở điểm CNI enforcement.
- [ ] Cho external fixed IP/CIDR có owner, port/protocol tối thiểu.
- [ ] Với SaaS IP động, dùng FQDN policy/proxy phù hợp và kiểm tra TTL/A/AAAA/CNAME.
- [ ] Không cho **0.0.0.0/0:443** vì tiện lợi trừ khi có policy/risk acceptance rõ.
- [ ] Không tin proxy config đơn độc; direct outbound bypass bị chặn.
- [ ] Egress gateway/forward proxy có caller identity, policy, HA và logs được bảo vệ.
- [ ] NAT/egress IP có mapping, capacity, rotation và attribution theo thời gian.
- [ ] TLS hostname verification, mTLS/service identity và app authZ vẫn được thực thi.
- [ ] Đã đánh giá cloud metadata, IAM/Workload Identity và SSRF defense.
- [ ] Đã hạn chế privileged/hostNetwork/NET_ADMIN và quyền thay labels/policies.
- [ ] Kubernetes API được cấp đường mạng và RBAC chỉ cho workload cần.
- [ ] Pod có sidecar/service mesh được kiểm tra proxy path và bypass risk.
- [ ] Cloud SG/firewall/transit/PrivateLink routes phù hợp với Pod egress intent.
- [ ] IPv6/dual-stack egress và ::/0 được kiểm soát, có telemetry.
- [ ] Đã kiểm kê dependency startup, token/certificate renewal, logging và scheduled jobs.
- [ ] Có positive tests cho đúng DNS, internal API, external partner và telemetry.
- [ ] Có negative tests cho Dev→Prod, metadata ngoài quyền và external destinations.
- [ ] Test giữa nhiều nodes/AZ, production/staging và DR theo phạm vi.
- [ ] Có logs CNI, proxy, DNS, NAT, cloud flow và application correlation.
- [ ] Logs không chứa token, API keys, credentials hoặc dữ liệu nhạy cảm ngoài policy.
- [ ] Có alert egress anomaly, policy drift, drops, NAT saturation và telemetry loss.
- [ ] Mỗi allow exception có owner, lý do, expiry và phương án review.
- [ ] Policy-as-code được review, có CI semantic tests và đường rollback.
- [ ] Khi CNI/provider/mesh/DNS được upgrade, chạy lại egress regression tests.
- [ ] Runbook phân biệt DNS, network, TLS, app authorization, proxy và cloud IAM failures.
- [ ] Không coi một policy YAML hoặc một phép curl thành công là chứng minh đầy đủ bảo mật.

## 34. Tổng kết

**Egress control cho container** biến outbound traffic từ “mặc định có đường đi” thành **những quyền cụ thể theo workload, destination, protocol và chính sách bảo mật**. Trong Kubernetes, bắt đầu bằng **NetworkPolicy default-deny**, sau đó thêm allow rules nhỏ nhất cho DNS, dịch vụ nội bộ và external endpoints. Phải hiểu đúng **podSelector, namespaceSelector, ipBlock, policyTypes và cơ chế hợp nhất các allow policies**, cũng như thực tế CNI, NAT, Service translation và hostNetwork.

Để bảo vệ trước **SSRF, data exfiltration, lateral movement, cloud metadata abuse và proxy bypass**, cần kết hợp **egress gateway/forward proxy, FQDN/DNS controls, firewall/SG, IPv4/IPv6 policy, workload IAM, TLS/mTLS, RBAC/admission và logging đa lớp**. Việc triển khai tốt không phải là chặn mọi thứ bất chấp availability, mà là **chứng minh các kết nối cần thiết vẫn hoạt động, các kết nối không được phép thực sự bị từ chối, và chính sách tiếp tục đúng khi Pod scale, route thay đổi hoặc hệ thống failover**. Đây là năng lực phòng vệ cốt lõi của học phần **SECURITY_NETWORK_SECURITY**.
