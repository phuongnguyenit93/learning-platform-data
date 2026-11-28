# Cloud load balancer và lớp bảo vệ đi kèm: Thiết kế điểm vào an toàn cho ứng dụng cloud

## 1. Bối cảnh và mục tiêu học tập

**Cloud load balancer** là dịch vụ hoặc thành phần cân bằng tải chạy trong môi trường cloud, nhận kết nối/yêu cầu từ client rồi phân phối đến các **backend** như virtual machine, container, Kubernetes service, serverless endpoint hoặc dịch vụ khác. Ngoài phân phối tải, tùy loại load balancer (LB), nó có thể thực hiện **TLS termination**, định tuyến theo hostname/path, health check, kiểm soát kết nối và tích hợp với CDN, WAF, cơ chế chống DDoS hoặc dịch vụ quan sát.

Trong chương **Bảo mật mạng cloud** của học phần **SECURITY_NETWORK_SECURITY**, mục tiêu không chỉ là giúp hệ thống chịu nhiều truy cập. LB thường nằm tại **ranh giới tin cậy giữa Internet, mạng riêng cloud, cụm ứng dụng và các dịch vụ nội bộ**. Một sai lệch ở đây có thể khiến hệ thống bị truy cập trái phép, mất khả năng phục vụ, lộ địa chỉ backend hoặc bỏ qua WAF. Bảo vệ LB cần phối hợp nhiều lớp: **phân đoạn mạng, firewall/security group, quản lý TLS/chứng thư, xác thực kết nối, WAF, bảo vệ DNS, chống DDoS, IDS/IPS và giám sát lưu lượng**.

**Tình huống mở đầu:** một công ty đặt API trên hai availability zones (AZs), phía trước có public HTTP load balancer gắn WAF. Nếu các backend vẫn có public IP cho phép kết nối trực tiếp từ Internet, kẻ tấn công có thể bỏ qua chính sách WAF bằng đường **direct-to-origin**. Việc LB có WAF không chứng minh ứng dụng được bảo vệ nếu còn một đường vào khác.

Sau bài này, bạn có thể:

1. Phân biệt cloud LB lớp 4 và lớp 7, public/internet-facing và internal/private, proxying và passthrough.
2. Xác định ranh giới bảo mật tại **CDN/edge, LB listener, gateway, backend và control plane**.
3. Thiết kế bảo vệ nhiều lớp bằng **WAF, chống DDoS upstream, security groups/NSG, network firewall, TLS/mTLS, xác thực và phân quyền**.
4. Phân tích đúng các vấn đề **IP nguồn, X-Forwarded-For/Forwarded, PROXY protocol, Host/SNI, health checks và origin bypass**.
5. Triển khai an toàn theo cách tiếp cận đa vùng, autoscaling, IPv4/IPv6, Kubernetes và các môi trường hybrid.
6. Chọn chỉ số giám sát, xây kịch bản kiểm thử an toàn, chẩn đoán lỗi 4xx/5xx và xác minh chính sách bằng bằng chứng thực tế.

## 2. Load balancer làm gì, và không làm gì?

Một LB nhận traffic ở một hoặc nhiều **frontends/listeners**, quyết định **backend pool/target group** rồi chuyển tiếp dựa trên thuật toán và trạng thái sức khỏe. Những thuật toán thường gặp gồm round robin, weighted distribution, least connections hoặc hash-based routing, nhưng khả năng thực tế khác theo sản phẩm.

~~~mermaid
flowchart LR
    C["Client / Internet"] --> FE["Frontend listener<br/>IP + port + protocol"]
    FE --> R["Routing / policy / TLS nếu hỗ trợ"]
    R --> T["Backend pool / target group"]
    T --> A["Backend A - AZ 1"]
    T --> B["Backend B - AZ 2"]
    T --> D["Backend C - AZ 2"]
    H["Health checks"] -.-> A
    H -.-> B
    H -.-> D
~~~

Các chức năng cần phân biệt:

| Thành phần | Chức năng chính | Không nên mặc định |
| --- | --- | --- |
| **DNS** | Phân giải hostname thành endpoint LB/CDN | DNS là lớp xác thực hay chống DDoS toàn diện |
| **CDN/edge** | Phục vụ cache, hấp thụ traffic và có thể chặn ở biên | Mọi request đều bị WAF kiểm tra nếu chưa gắn policy |
| **Cloud LB** | Phân phối và quản lý kết nối/request theo loại | Luôn có WAF, xác thực người dùng hoặc kiểm tra nội dung |
| **WAF** | Kiểm tra HTTP(S) theo rule được cấu hình | Thay firewall L3/L4 hoặc kiểm tra mọi payload vô hạn |
| **DDoS protection** | Giảm tác động các dạng flood theo khả năng nhà cung cấp | Bảo vệ khỏi mọi request hợp lệ nhưng tốn CPU/DB |
| **Security group/NSG** | Cho phép/chặn luồng mạng theo điểm gắn và quy tắc | Kiểm tra được JSON body, URL và vai trò tài khoản |
| **Network firewall** | Phân đoạn, lọc và có thể inspection theo tính năng | Nhìn thấy nội dung TLS nếu không ở điểm phù hợp |
| **Application** | Xác thực, phân quyền, validation và nghiệp vụ | Có thể bỏ qua authentication chỉ vì nằm sau LB |
| **Observability** | Đo lường, log, phát hiện bất thường | Có log nghĩa là đã ngăn được cuộc tấn công |

**LB không phải lá chắn tuyệt đối.** Một API ở sau LB vẫn có thể có lỗ hổng BOLA/IDOR, SQL injection, credential stuffing hoặc một operation đọc dữ liệu lớn gây cạn cơ sở dữ liệu. LB là điểm thích hợp để triển khai một số kiểm soát, nhưng backend vẫn cần **authorization, input validation, resource limits và audit**.

## 3. Phân loại cloud load balancer

### 3.1. Network Load Balancer (L4)

**L4 LB** xử lý luồng dựa trên thông tin mạng/transport như IP, TCP hoặc UDP và trạng thái kết nối. Tùy nền tảng, nó có thể hỗ trợ TLS listener/offload, client IP preservation và health checks; nhưng **không nên mặc định** rằng một L4 listener hiểu URL path, JSON body hoặc HTTP headers.

Phù hợp cho:

- TCP/UDP services hoặc giao thức không phải HTTP.
- Hệ thống cần giữ đặc điểm kết nối, latency và traffic throughput.
- Một số kiến trúc TLS passthrough hoặc truyền mã hóa đến backend.
- Frontend cho dịch vụ mạng cần cân bằng kết nối theo layer 4.

**Ranh giới an ninh:** nếu TLS đi xuyên LB tới backend (passthrough), WAF HTTP ở chính LB không thể kiểm tra nội dung ứng dụng mà nó không giải mã/parse. Thay vì “bật WAF” chỉ bằng tên sản phẩm, phải kiểm tra có điểm **L7 HTTP inspection** trong data path hay không.

### 3.2. Application Load Balancer (L7)

**L7 LB** hiểu HTTP(S) và có thể dùng host/path/method/header theo khả năng sản phẩm để định tuyến. Nó thường có cơ chế TLS termination, HTTP/2 hoặc HTTP/3 tùy nền tảng, rewrite/redirect, health checks và tích hợp với WAF/identity.

Phù hợp cho:

- Website, REST/GraphQL APIs và một số gRPC/web application workloads.
- Định tuyến nhiều host hoặc nhiều dịch vụ qua cùng một endpoint.
- Áp một số rule HTTP tại điểm chung trước backend.
- Gắn WAF hoặc dịch vụ bảo vệ ứng dụng theo tích hợp được hỗ trợ.

**Không được suy ra L7 LB luôn có khả năng kiểm tra tất cả request body**, hoặc hỗ trợ cùng các tính năng HTTP/3, WebSocket, gRPC trên mọi sản phẩm. Một số tính năng phải bật trên profile/listener cụ thể hoặc nằm ở gateway/WAF khác.

### 3.3. Public/internet-facing so với internal/private

| Loại | Khả năng tiếp cận | Mục đích thường gặp | Kiểm soát ưu tiên |
| --- | --- | --- | --- |
| **Public / internet-facing** | Endpoint có thể truy cập từ Internet theo route, listener và policy | Web/app/API công khai | DDoS upstream, WAF, TLS, ingress rules, auth, logging |
| **Internal / private** | Endpoint định tuyến trong VPC/VNet/mạng liên kết được phép | API nội bộ, microservices, backend tầng 2 | Segmentation, mTLS, IAM, route restrictions, không mở nhầm peering/VPN |
| **Hybrid-facing** | Frontend/targets liên quan VPN, private link, on-prem hoặc liên mạng | Truy cập ứng dụng xuyên cloud/on-prem | Kiểm tra trust boundary, routing, identity và DNS |

**Private không tự đồng nghĩa an toàn.** Một internal LB có thể truy cập được từ tài khoản cloud khác, mạng kết nối qua peering/VPN, workstation nhiễm mã độc hoặc workload cùng VPC nếu cấu hình cho phép. Chính sách phải dựa trên **nguồn và danh tính được phép**, không chỉ nhãn internal.

### 3.4. Ví dụ các họ dịch vụ cloud

| Hệ sinh thái | Ví dụ loại dịch vụ | Ý nghĩa khi thiết kế |
| --- | --- | --- |
| **AWS** | Application Load Balancer, Network Load Balancer, Gateway Load Balancer | Cần phân biệt L7 HTTP, L4 TCP/UDP và lớp chèn network appliances |
| **Microsoft Azure** | Azure Load Balancer, Application Gateway, Azure Front Door | Phân biệt LB L4, web application delivery/WAF và global edge |
| **Google Cloud** | Application Load Balancers và Network Load Balancers với các mode triển khai | Khả năng global/regional, proxy/passthrough và WAF/DDoS attachment khác nhau |
| **Kubernetes trên cloud** | Service type LoadBalancer, Ingress, Gateway API controller | API Kubernetes không đồng nghĩa một loại LB vật lý/chức năng cố định |

Đây là **bản đồ khái niệm**, không phải ma trận tính năng hoặc tên sản phẩm bất biến. Khả năng WAF, IPv6, client IP preservation, mTLS, private endpoint, gRPC, HTTP/3, timeout, quota và chi phí cần xác minh theo **region, tier, phiên bản controller và tài liệu nhà cung cấp** khi triển khai.

## 4. Data plane, control plane và shared responsibility

Trong cloud, LB có hai mặt bảo mật:

1. **Data plane:** tiếp nhận, xử lý, định tuyến traffic của client tới backend theo cấu hình.
2. **Control plane:** API/console/IaC nơi người được cấp quyền tạo listeners, thay TLS certificate, đổi WAF attachment, cập nhật backend pool hoặc firewall rules.

Một data plane được bảo vệ tốt vẫn có thể bị tổn hại nếu control plane IAM bị chiếm quyền. Ví dụ attacker có quyền thay listener có thể tạo route mới bỏ qua WAF hoặc gắn backend không được phép.

### 4.1. Ranh giới trách nhiệm chia sẻ

Cloud provider thường chịu trách nhiệm vận hành hạ tầng managed service theo phạm vi dịch vụ. **Khách hàng vẫn chịu trách nhiệm cấu hình** endpoint, routing, TLS policy, access control, firewall, backend exposure, WAF policies, secret/cert lifecycle, logs và kiểm soát IAM.

Đặc biệt:

- **Dịch vụ được quản lý** không có nghĩa policies mặc định phù hợp threat model.
- **Auto-scaling** không đồng nghĩa chống được unlimited cost hoặc các attack làm kiệt DB.
- **Cloud-native DDoS baseline** không chắc chặn được từng loại business-logic abuse.
- **Có encryption in transit** không mặc định đã kiểm tra đúng hostname hoặc trust anchor ở kết nối tới backend.

### 4.2. Bảo vệ control plane

Cần giới hạn quyền IAM theo role và nhiệm vụ:

| Quyền thay đổi | Hậu quả nếu bị lạm dụng | Bảo vệ nên có |
| --- | --- | --- |
| Thay listener/routing rule | Chuyển traffic vào ứng dụng sai | Least privilege, approval, IaC review và audit |
| Gỡ hoặc thay WAF policy | Bỏ lớp bảo vệ HTTP | Guardrails/policy-as-code, thay đổi có phê duyệt |
| Gắn backend target mới | Chuyển dữ liệu tới hệ thống chưa được tin | Tag/role restrictions, inventory và review |
| Tải/đổi TLS certificate | Downtime, định danh sai hoặc lộ khóa | PKI lifecycle, quyền đọc secret tối thiểu |
| Thay security group/NSG | Mở public backend hoặc admin port | Route/network policy review, cảnh báo config drift |
| Xóa log/metric hoặc thay retention | Mất khả năng điều tra | Audit bất biến/tập trung, tách quyền vận hành |

Không trao quyền **quản trị cloud toàn bộ** chỉ vì một nhóm cần sửa health check của một LB. Mọi thay đổi quan trọng phải có **owner, lý do, đánh giá blast radius và khả năng rollback**.

## 5. Kiến trúc tham chiếu public web/API an toàn

~~~mermaid
flowchart LR
    U["Internet users"] --> DNS["DNS + edge routing"]
    DNS --> EDGE["CDN / DDoS mitigation<br/>WAF tại điểm hỗ trợ"]
    EDGE --> PUB["Public HTTPS L7 LB"]
    PUB --> FW["Backend ingress policies<br/>Security group / NSG"]
    FW --> APPS["Private application targets<br/>AZ A và AZ B"]
    APPS --> DATA["Private DB / cache"]
    PUB -. "Metrics + access logs" .-> SOC["SIEM / monitoring"]
    EDGE -. "WAF + edge telemetry" .-> SOC
    FW -. "Flow / deny logs" .-> SOC
    APPS -. "App auth/audit" .-> SOC
    BAD["Internet direct-to-origin"] -. "Deny" .-> FW
~~~

**Mục tiêu thiết kế:** Internet chỉ vào những **frontends được phê duyệt**. Backend **không có đường truy cập công cộng không kiểm soát**, được đặt tại các subnet/segment phù hợp, security group/NSG chỉ cho phép nguồn thực sự cần, và service xác thực/ủy quyền trong ứng dụng.

### 5.1. Chia vùng ví dụ

| Vùng | Tài nguyên | Luồng được phép |
| --- | --- | --- |
| **EDGE** | CDN/WAF/DDoS service | Internet → edge; edge → frontend chính thức |
| **PUBLIC-INGRESS** | Public LB frontends | Chỉ các listener công khai cần thiết |
| **APP-PRIVATE** | VM/containers hoặc serverless connectors | LB/gateway → app port và health checks |
| **DATA-PRIVATE** | Database/cache/queue | Đúng application identities và ports |
| **MGMT** | Administration, CI/CD, observability | IdP/IAM, bastion/private access theo policy |
| **EGRESS** | NAT/egress gateway/proxy/firewall | Chỉ đường outbound được phép |

**Không cần mọi topology đều dùng subnet public cho managed LB**: cách provider gắn frontend vào mạng và route khác nhau. Bản chất cần kiểm chứng là **điểm truy cập, đường đi, chính sách và danh tính**, không phải giả định tất cả cloud triển khai giống một loại VPC.

### 5.2. Ma trận truy cập tối thiểu

| Nguồn → Đích | Dịch vụ | Quyết định mẫu |
| --- | --- | --- |
| Internet → Public HTTPS LB | 443/TCP hoặc giao thức client đã phê duyệt | **Allow** |
| Internet → App private IP | Mọi kết nối không qua LB | **Deny / không có route** |
| LB → App targets | Cổng ứng dụng cụ thể | **Allow** theo policy |
| Health checker → health endpoint | Cổng/path cần thiết | **Allow** đúng nguồn/hạ tầng |
| App → Database | Cổng và identity riêng | **Allow** theo phân quyền |
| Public LB → DB | Kết nối DB trực tiếp | **Deny** nếu không có nhu cầu |
| Internet → Management endpoints | SSH/RDP/admin/API không công khai | **Deny** |
| App → Internet outbound | Theo danh sách dịch vụ cần thiết | **Allow có kiểm soát** |
| Peering/VPN → Internal LB | Chỉ workloads được cấp quyền | **Allow theo chính sách riêng** |

Đây là **ma trận yêu cầu**, không phải firewall rules có thể copy vào mọi cloud. Security groups/NSGs, routing tables, network ACLs và provider-managed frontend addresses có semantics khác nhau. Một số giải pháp health check cần các nguồn được nhà cung cấp xác định; không tự chặn bằng một danh sách IP tự đoán.

## 6. TLS termination, end-to-end TLS và mTLS

### 6.1. Ba mô hình mã hóa phổ biến

| Mô hình | Đường đi | Ưu điểm | Điểm cần bảo vệ |
| --- | --- | --- | --- |
| **TLS termination tại LB** | Client → HTTPS LB → HTTP backend | LB có thể hiểu HTTP, dễ route và gắn WAF tại L7 | Backend hop không mã hóa; cần đánh giá trust boundary |
| **TLS re-encryption** | Client → HTTPS LB → HTTPS backend | Mã hóa cả hai cạnh, cho phép L7 processing tại LB | Cấu hình **xác minh chứng thư backend** thật sự |
| **TLS passthrough** | Client → L4 LB → TLS backend | Backend trực tiếp nắm TLS session/keys | LB không tự đọc HTTP body/header để WAF L7 |

Không gọi mô hình đầu tiên là **end-to-end encrypted** nếu chặng LB → backend truyền HTTP plaintext. Ngược lại, re-encryption không tự bảo đảm backend authentication nếu LB chỉ mở TLS tới bất kỳ chứng thư nào mà không xác minh đúng danh tính.

~~~mermaid
flowchart LR
    C["Browser / API client"] -->|"TLS #1: verify public hostname"| LB["L7 Load Balancer<br/>Terminate client TLS"]
    LB -->|"TLS #2: verify backend identity"| A["Private app service"]
    A -->|"TLS #3 + DB authentication"| DB["Database"]
    CA["PKI / certificate lifecycle"] -. "Cert / trust policy" .-> LB
    CA -. "Cert / trust policy" .-> A
~~~

### 6.2. Chứng thư tại frontend

Cloud LB/edge listener cần:

- Chứng thư **phù hợp hostname** mà client truy cập; dùng SAN/DNS names và chain đầy đủ.
- Quản lý vòng đời cấp phát, tự động gia hạn khi có, deploy và kiểm tra mọi listener/region.
- TLS versions và cipher policies phù hợp yêu cầu tổ chức, tránh giao thức cũ không an toàn.
- Cơ chế bảo vệ private key, IAM trên certificate/secret manager và audit thao tác thay.
- Kiểm tra **SNI**, HTTP **Host** và route mapping: cùng một IP frontend có thể phục vụ nhiều tên miền.
- Theo dõi lỗi handshake, certificate expiry, chain và những client đặc thù.

Nếu LB chỉ thực hiện TCP/TLS passthrough, chứng thư có thể nằm tại **backend**, không phải frontend LB. Xác định chính xác **điểm kết thúc TLS** trước khi sửa chứng thư hoặc phân tích lỗi.

### 6.3. Bảo vệ chặng LB → backend

Chính sách backend encryption cần trả lời:

1. LB có thực sự kết nối **TLS tới backend**, hay chỉ TCP/HTTP?
2. LB có kiểm tra **issuer chain**, hostname/SAN hoặc danh tính backend theo cơ chế sản phẩm hỗ trợ không?
3. Backends có sử dụng một chứng thư dùng chung hoặc identity riêng, và quy trình rotation thế nào?
4. Chứng thư có được cập nhật khi VM/pod được autoscale không?
5. Nếu backend identity sai hoặc trust store thiếu, hệ thống **từ chối** hay âm thầm kết nối tiếp?

Một số managed LB hỗ trợ TLS backend nhưng có **khả năng kiểm chứng backend certificate hạn chế hoặc semantics riêng**. Phải xác minh với tài liệu và phép thử tiêu cực của đúng sản phẩm; nếu thiếu chức năng cần thiết, cân nhắc mTLS proxy/service mesh hoặc lớp kết nối bổ sung.

### 6.4. mTLS và workload identity

**Mutual TLS (mTLS)** cho phép cả hai phía xác thực bằng chứng thư khi được cấu hình đúng. Một kiến trúc có thể yêu cầu **client → LB mTLS** hoặc **LB/proxy → backend mTLS**, phụ thuộc khả năng sản phẩm.

**Phân biệt:**

- CA trust của client để xác thực **LB/server certificate**.
- CA trust của LB/server để xác thực **client certificate**.
- Identity/authorization map từ certificate tới user, device, service hoặc tenant.

Một client certificate hợp lệ **không thay thế quyền** đối với một API cụ thể; backend vẫn cần authorization theo operation, resource và tenant. Không mặc định mọi cloud LB đều hỗ trợ mTLS ở cả hai hướng, cùng semantics về CRL/OCSP và tất cả protocol listeners.

### 6.5. TLS 1.3, HTTP/2, HTTP/3 và request replay

Tùy nền tảng, frontend có thể hỗ trợ **TLS 1.3, HTTP/2, HTTP/3 qua QUIC**. Khi đánh giá:

- Xác định chính xác listener/protocol/port được bật và tương tác với WAF.
- Kiểm tra giới hạn headers, body, concurrent streams và timeout riêng.
- Không đồng nhất HTTP/3 (QUIC/UDP) với TCP 443 về cách firewall/L4 listener hoạt động.
- Nếu tính năng **TLS 1.3 early data (0-RTT)** được hỗ trợ, cần đánh giá rủi ro **replay** cho các operation không idempotent; có thể từ chối hoặc hạn chế 0-RTT theo policy.

Chỉ thay chứng thư hoặc bật phiên bản TLS mới không tự bảo đảm mọi client/edge/proxy/backend đều dùng cùng protocol và có hành vi an ninh tương đương.

## 7. WAF gắn với cloud load balancer

### 7.1. WAF là gì trong đường đi HTTP?

**Web Application Firewall (WAF)** áp quy tắc trên HTTP(S) sau khi dữ liệu được giải mã và parse ở một điểm phù hợp. WAF có thể có:

- **Managed rules** cho một số mẫu tấn công phổ biến.
- Rules theo URI, method, header, cookie hoặc body theo khả năng.
- **IP/geo/reputation** rules với giới hạn độ chính xác.
- Rate-based rules và bot mitigation theo nền tảng/tier.
- Custom allow/deny/challenge và ngoại lệ theo route/nhóm client.
- Logging/metrics, rule version và chế độ count/log-only để rollout an toàn.

**WAF không phải antivirus của mọi file upload** và không thay application input validation, authentication hoặc authorization. Nếu WAF chỉ kiểm tra một phần body do giới hạn inspection, phần body còn lại có thể vẫn được chuyển tiếp tùy chế độ xử lý.

### 7.2. Kiến trúc attachment phải được xác minh

Một policy “đã tạo trong console” chưa chắc đã **được gắn vào đúng frontend/hostname/route**. Kiểm tra:

1. WAF nằm ở **CDN edge, regional L7 LB, gateway** hay một ứng dụng lọc độc lập?
2. Đúng **resource ID, listener, endpoint, scope, account/project/subscription và region** chưa?
3. Mọi đường public route vào dịch vụ đều qua policy chưa?
4. Có route **bypass** như origin hostname, legacy LB, IPv6, alternate port hoặc service endpoint khác không?
5. Những request có HTTP/2/3, gRPC, streaming hoặc body lớn được inspect/enforce thế nào?
6. Policy được bật **block**, **count**, **challenge** hay một chế độ khác?

### 7.3. WAF false positive và khả năng rollback

Một WAF rule có thể chặn request hợp lệ khi API có JSON đặc biệt, query tham số phức tạp hoặc payload được encode. Quy trình thay đổi nên:

- Bật **count/log-only** trong khoảng đại diện khi nền tảng hỗ trợ.
- Dùng **rule ID, URI, action, trace/request ID** để tìm tác động.
- Tạo **exception hẹp** theo path/parameter, method hoặc nguồn đáng tin đã xác thực thay vì disable cả rule group.
- Có owner, hạn sử dụng ngoại lệ, canary và rollback.
- Duy trì **app authorization, body limits, rate/concurrency limits** kể cả khi có WAF exception.

**Không nên lập allowlist toàn bộ IP NAT của một khách hàng** nếu như vậy bỏ qua mọi rule ứng dụng; nhiều người và ứng dụng có thể dùng cùng public IP.

### 7.4. WAF inspection limit khác hard body limit

| Khái niệm | Ý nghĩa | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| **WAF body inspection cap** | Số byte nội dung WAF cố gắng phân tích | Phần ngoài cap có thể không được kiểm tra nhưng vẫn đi qua |
| **LB/proxy request-body hard cap** | Kích thước tối đa body được nhận/chuyển | Không tự kiểm tra dữ liệu sau giải nén hoặc cấu trúc JSON |
| **Application parsed/decoded limit** | Giới hạn nội dung sau parse/giải nén, độ sâu, số fields | Phải có để ngăn payload nhỏ nhưng tốn CPU |
| **Upload object limit** | File/object size và storage quota | Không đồng nghĩa tổng multipart body cap |

Khi WAF không thể kiểm tra hết request, phải biết hành động chính xác: **block, pass-through, inspect partial, truncate hoặc log-only**. Đừng ghi “đã chặn upload lớn” chỉ vì một tham số WAF chứa chữ *limit*.

## 8. DDoS protection đi kèm LB và edge

### 8.1. Các tầng tấn công

| Tầng | Kịch bản | Điểm bảo vệ hợp lý |
| --- | --- | --- |
| **Network volumetric** | Băng thông flood vào public endpoint | Upstream/cloud edge/ISP và dịch vụ DDoS network |
| **Transport/state exhaustion** | Nhiều connections/flows chiếm state | DDoS/L4 protections, connection caps, timeouts |
| **HTTP L7 flood** | Nhiều HTTP requests vào endpoints phổ biến | CDN/WAF/rate limit, auth, cache |
| **Expensive application requests** | Ít request nhưng query hoặc export rất nặng | App cost/concurrency/queue/quota và DB controls |
| **Slow clients/slow uploads** | Kết nối giữ lâu nhưng RPS thấp | Header/body read timeouts, concurrency, resource limits |

**Một LB có autoscaling vẫn có giới hạn:** quotas, số backend connections, health probes, chi phí, database pool, region capacity và đường upstream. DDoS protection của cloud có thể giúp hấp thụ nhiều kiểu flood, nhưng không loại trừ yêu cầu **capacity planning và application-level controls**.

### 8.2. Global edge so với regional origin

CDN/edge network có thể phân phối điểm tiếp nhận rộng hơn, cache content và giảm lưu lượng tới origin. Điều này hữu ích cho các tài nguyên tĩnh và một số APIs phù hợp cache. Tuy nhiên:

- Request không cache được vẫn có thể đến origin.
- Cache key sai có thể gây **lộ dữ liệu xuyên user/tenant**.
- Dynamic/private responses cần policy **Cache-Control**, cookie, Authorization và cache partition đúng.
- Ứng dụng quản trị, login, checkout, ghi dữ liệu hoặc API cá nhân hóa thường yêu cầu xử lý cache thận trọng.
- Một attacker có thể cố truy cập origin trực tiếp nếu origin chưa khóa.

Không bật cache toàn bộ route chỉ để giảm tải nếu chưa kiểm tra privacy và tính đúng đắn nghiệp vụ.

### 8.3. Rate limiting nhiều cấp

Một API công khai có thể dùng các ngân sách độc lập:

~~~text
Edge:
  coarse source/IP burst guard
  network-level abuse signals

Regional L7 gateway:
  route-based request rate, header/body limits

After authentication:
  verified user/API key/tenant budget

Backend:
  weighted cost, concurrency, queue, DB query timeout
~~~

**IP nguồn không phải danh tính người dùng**: NAT/CGNAT có thể gộp hàng trăm người vào một IP, trong khi một attacker có thể dùng nhiều IP/IPv6 addresses. Do đó, sau xác thực, quota theo **verified identity/tenant** thường hợp lý hơn việc chỉ dựa vào per-IP.

### 8.4. Đừng xử lý volumetric DDoS bằng cách tăng backend

Khi đường mạng trước LB bị bão hòa, thêm VM vào target group có thể không giải quyết được vấn đề. Cần phân biệt **network saturation**, **LB connection-state exhaustion**, **WAF rule bottleneck** và **backend resource exhaustion** qua metric ở từng tầng; chọn cơ chế mitigation theo vị trí nghẽn.

## 9. Phân đoạn mạng quanh LB: Security Group, NSG và firewall

### 9.1. Cấu trúc inbound tối thiểu

Với public web application:

1. Frontend chỉ mở **listener ports** cần thiết (ví dụ HTTPS).
2. Backend chỉ nhận từ **LB/connector/health checker** theo loại nguồn mà provider hỗ trợ.
3. Database và cache chỉ nhận từ đúng **application tier**; không public.
4. Management plane dùng **private administrative access**, IAM và log theo policy.
5. Egress chỉ cho những dịch vụ mà ứng dụng thật sự cần.

Tùy cloud, có thể reference **security group identity**, **network tags**, **service tags**, địa chỉ subnet/connector hay nguồn health probes được công bố. Tránh hard-code một IP LB khi dịch vụ có thể thay đổi địa chỉ.

### 9.2. SG/NSG và network ACL không giống WAF

**Security group/NSG** thường lọc theo địa chỉ, protocol, port và một số nguồn nhận dạng do nền tảng hỗ trợ. Tính **stateful** hoặc **stateless**, thứ tự priority, áp dụng ở NIC/subnet và xử lý traffic trở về khác giữa các dịch vụ. **Network ACL** có thể bổ sung phạm vi subnet nhưng không thay thế identity/API authorization.

Ví dụ không an toàn:

~~~text
Backend private service port 8080:
  ALLOW 0.0.0.0/0 (mọi IPv4 nguồn)

Chỉ vì backend được cho là nằm trong private subnet
không có nghĩa rule này phù hợp trong mọi topology.
~~~

Thay bằng **nguồn LB/security boundary thực sự**; kiểm tra **IPv6 ::/0**, peering, VPN, internal routes và các public endpoints khác. Không chỉ xem security group mà quên routing/public IP/interface gắn vào backend.

### 9.3. Tường lửa không thể áp khi không thấy traffic

Nếu các pods trong cùng node/VPC/overlay có thể nói chuyện trực tiếp mà không đi qua firewall tập trung, một rule chặn trên thiết bị trung tâm có thể **không bao giờ thấy luồng đó**. Cần placement đúng: SG/NSG, VPC firewall rules, Kubernetes NetworkPolicy được CNI thực thi, microsegmentation hoặc service mesh authorization.

**Bảo vệ external ingress** là một chiều; **east–west traffic** giữa services và **egress** tới Internet/cloud APIs cũng phải được threat model riêng.

## 10. Chống origin bypass: LB có WAF nhưng backend vẫn hở

### 10.1. Các đường bypass phổ biến

| Đường đi | Cách xuất hiện | Cách kiểm tra |
| --- | --- | --- |
| **Public IP của VM/backend** | App node có public interface và mở port | Inventory public endpoints, SG/NSG, route |
| **Legacy LB cũ** | DNS cũ đã quên hoặc một listener chưa gỡ | Asset inventory, DNS, routing và policy |
| **Direct origin hostname** | Hostname nội bộ bị lộ và public DNS vẫn trỏ | DNS/cert logs, allowlists và origin firewall |
| **IPv6 alternate path** | IPv4 bị chặn nhưng IPv6 public mở | Dual-stack ingress tests |
| **Admin/debug port** | Port 8080/8443 hoặc quản trị mở ngoài intended LB | Port inventory và ingress rules |
| **Kubernetes NodePort/public Service** | Workload có entrypoint khác Ingress/WAF | Service/controller inventory và cluster policies |
| **VPN/peering/private endpoints** | Tập nguồn nội bộ quá rộng | Route table, firewall và workload identity |
| **Cross-account/shared network** | Peering/TGW/private connectivity gắn sai | Account/network boundary review |

Một bằng chứng tốt gồm **kiểm thử từ nguồn lab không được phép** và **log deny tại đúng enforcement point**, không chỉ nhìn UI thấy WAF đã bật.

### 10.2. Origin lock-down

Tùy kiến trúc có thể kết hợp:

- Backend **không có public IP** hoặc không có route inbound công cộng.
- SG/NSG chỉ cho **LB hoặc edge connector** theo kiểu source được nhà cung cấp hỗ trợ.
- Chặn truy cập direct-to-origin ngay cả khi caller biết địa chỉ và gửi HTTP Host hợp lệ.
- Kết nối riêng từ CDN/edge đến origin hoặc các cơ chế xác thực origin được provider hỗ trợ.
- **mTLS hoặc application-layer origin authentication** khi kiến trúc cần danh tính của hop phía trước.
- Audit cả IPv4/IPv6 và các listeners/legacy resources.

Nếu CDN dùng IP ranges thay đổi, phải cập nhật nguồn được phép qua quy trình đáng tin; **không nên giữ allowlist thủ công hết hạn** khiến edge traffic hợp lệ bị chặn hoặc vô tình mở quá rộng.

### 10.3. Chỉ kiểm tra header “bí mật” từ CDN là chưa đủ

Một custom header được edge thêm vào có thể là tín hiệu bổ sung để nhận diện request hợp lệ; nhưng nếu header có thể bị lộ hoặc client có thể gọi thẳng origin và tự đặt nó, đó không phải ranh giới bảo mật mạnh.

Ưu tiên **network restriction + authenticated origin connection + least-privilege IAM** theo khả năng. Nếu dùng shared-secret header, cần bảo vệ/rotation/giới hạn quyền, không log giá trị và không coi nó tương đương mTLS.

## 11. Client IP và các headers qua chuỗi cloud proxy

### 11.1. Remote peer không luôn là IP người dùng

Trong kiến trúc **client → CDN → LB → API gateway → backend**, backend có thể thấy IP của gateway/LB là remote peer. Nếu backend giới hạn theo địa chỉ này, tất cả người dùng có thể bị gộp chung một rate-limit bucket; nếu ghi access log sai nguồn, điều tra sự cố trở nên khó khăn.

Ngược lại, **tin trực tiếp header X-Forwarded-For do Internet client tự gửi** có thể khiến client giả IP, né rate limit hoặc tạo bằng chứng sai.

~~~mermaid
flowchart LR
    C["Client thật"] --> EDGE["Trusted edge / CDN"]
    EDGE --> LB["Cloud LB / proxy"]
    LB --> APP["Application"]
    FAKE["Untrusted X-Forwarded-For<br/>do client tự khai"] -. "Không được tự tin" .-> APP
    EDGE -. "Nguồn đã xác minh<br/>theo policy" .-> APP
~~~

### 11.2. Những cơ chế mang thông tin nguồn

| Cơ chế | Dùng ở đâu | Cảnh báo |
| --- | --- | --- |
| **Remote source address** | Peer mà socket/backend thấy | Có thể là proxy hoặc NAT, không phải người dùng |
| **X-Forwarded-For (XFF)** | HTTP chain qua proxies | Chuỗi nhiều IP, có thể chứa phần do client tự khai |
| **Forwarded** | HTTP header theo RFC 7239 | Chỉ đáng tin khi ingress xử lý theo trust policy |
| **X-Forwarded-Proto** | Ghi nhận scheme phía ngoài | Không dùng để quyết định HTTPS chỉ bằng input tự khai |
| **X-Forwarded-Host** | Ghi nhận host phía ngoài | Cần allowlist/validation tránh host-header poisoning |
| **PROXY protocol** | Metadata nguồn ở lớp kết nối giữa những hop hỗ trợ | Không phải HTTP; chỉ bật khi cả hai phía được cấu hình và bảo vệ |
| **Client IP preservation** | Tính năng LB hoặc mode phù hợp | Phụ thuộc loại LB/target mode/NAT/routing |

**PROXY protocol** truyền metadata của kết nối; nó không mặc nhiên xác thực chủ thể gửi metadata. Backend phải chỉ nhận PROXY protocol từ **trusted peers**, nếu không client có thể gửi metadata giả hoặc làm parser backend lỗi.

### 11.3. Quy tắc tin cậy qua proxy chain

1. Xác định **ingress nào thật sự đáng tin** và được phép kết nối backend.
2. Edge **xóa hoặc chuẩn hóa** các headers do client tự cung cấp có thể ảnh hưởng source identity.
3. Mỗi hop xác định remote peer có thuộc danh sách proxy tin cậy không trước khi sử dụng header phía trước.
4. App nhận **verified_client_ip** từ thành phần được kiểm soát; log riêng **remote_peer_ip** và chain metadata khi cần.
5. Áp rate limiting pre-auth theo nguồn đáng tin, post-auth theo **verified user/API client/tenant**.
6. Kiểm tra IPv4, IPv6, multiple XFF entries, định dạng không hợp lệ và những request đi vào qua ingress phụ.

Không có quy tắc “chọn IP đầu tiên trong XFF là client thật” áp dụng cho tất cả kiến trúc. Thứ tự parsing phải dựa trên **cách từng proxy thực tế ghi đè/thêm header** và số hop tin cậy.

### 11.4. Host và SNI không phải người dùng có quyền

**TLS SNI** giúp chọn chứng thư/virtual host trong handshake; **HTTP Host** hoặc **:authority** giúp xác định đích ứng dụng. Một client có thể tự yêu cầu hostname tùy ý trong những trường được giao thức cho phép.

Vì vậy:

- Có danh sách hostnames được phép/được phục vụ đúng tại LB/router.
- Không dùng giá trị Host chưa được kiểm tra làm căn cứ tạo URL reset mật khẩu, xác định tenant hoặc phân quyền.
- Kiểm tra sự khác biệt giữa **SNI, HTTP Host/:authority, TLS backend name và routing policy**.
- Đối với nhiều virtual hosts, cấu hình hành vi mặc định cho hostname không khớp, không vô tình route tới ứng dụng quản trị.

### 11.5. HTTP framing và request smuggling

Khi có nhiều HTTP proxies, sự không nhất quán trong xử lý **Content-Length, Transfer-Encoding, header normalization hoặc chuyển đổi HTTP/2 → HTTP/1.1** có thể gây **HTTP desynchronization/request smuggling**.

Rate limit và WAF thường đặt ở hop ngoài. Nếu hai hop hiểu ranh giới request khác nhau, kiểm soát ở hop ngoài có thể không khớp hành vi ở backend. Để giảm rủi ro:

- Sử dụng các stack/proxy được cập nhật và xử lý framing theo chuẩn.
- Không chuyển tiếp request có framing mơ hồ hoặc headers mâu thuẫn.
- Đồng nhất quy tắc normalization và loại bỏ hop-by-hop headers không hợp lệ.
- Kiểm thử tích hợp **có quyền và trong lab cô lập**, không thử smuggling trên dịch vụ Internet ngoài phạm vi.

**WAF không thay parser protocol chuẩn.** Một rule theo path/body không đủ nếu ranh giới thông điệp giữa các hop có thể bị diễn giải khác nhau.

## 12. Health checks, readiness và tránh đưa traffic vào backend hỏng

### 12.1. Health check phục vụ cả availability và security

Load balancer thường gửi **active health probes** hoặc dùng thông tin passive health theo tính năng để xác định backend đủ điều kiện nhận traffic. Một cấu hình health check sai có thể:

- Đưa client vào backend chưa sẵn sàng xác thực/kiểm tra quyền.
- Loại toàn bộ backends vì chặn sai health checker.
- Duy trì backend lỗi nhưng luôn trả 200 cho một endpoint quá nông.
- Tạo vòng lặp autoscaling/restart khi dependency tạm lỗi.
- Lộ endpoint debug/metrics nếu mở health path công khai.

### 12.2. Liveness, readiness và deep dependency checks

| Kiểm tra | Mục tiêu | Sai lầm thường gặp |
| --- | --- | --- |
| **Transport/connectivity** | Cổng/connection có thể mở | Kết nối TCP thành công không bảo đảm API xử lý đúng |
| **Liveness** | Process còn hoạt động, có nên restart? | Gắn vào DB transient lỗi gây restart hàng loạt |
| **Readiness** | Instance sẵn sàng nhận request mới? | Trả ready trước khi secrets/routes/dependencies quan trọng sẵn sàng |
| **Deep dependency health** | Database/cache/downstream có đủ điều kiện nghiệp vụ? | Probing sâu quá thường xuyên gây quá tải hoặc tạo phụ thuộc vòng |
| **End-to-end synthetic** | Client hợp lệ có đi xuyên các lớp thành công? | Chỉ test health route mà bỏ qua auth/TLS/WAF |

Health check endpoint nên **nhẹ, ổn định, không tiết lộ secrets**, chỉ trả thông tin tối thiểu. Health monitoring cho người vận hành có thể tách khỏi health endpoint mà LB dùng.

### 12.3. Allowlist đúng nguồn health checker

Trong một số cloud, health probes có thể bắt nguồn từ địa chỉ/service ranges khác với traffic ứng dụng. Nếu security group/firewall chỉ cho app traffic nhưng chặn probes, LB đánh dấu target **unhealthy** và ngừng gửi request.

Đừng mở toàn Internet vào backend chỉ để health checks hoạt động. Hãy dùng **nguồn health probes được provider công bố hoặc nguồn service identity được hỗ trợ**, và kiểm tra luật IPv4/IPv6 theo chính sách.

### 12.4. Connection draining và graceful shutdown

Khi deploy hoặc scale down:

1. Đánh dấu backend không nhận **request mới**.
2. Cho phép các request đang chạy hoàn tất trong thời gian drain phù hợp.
3. Kết thúc các long-lived connections/WebSocket/gRPC streams theo policy.
4. Đảm bảo server không dừng trước khi LB đã ngừng route tới nó.
5. Xử lý retry/idempotency để tránh request bị thực thi trùng khi response bị mất.

**Connection draining không bảo đảm mọi request thành công** khi node chết đột ngột. Ứng dụng cần timeout, idempotency keys và quản lý partial operations đúng.

## 13. Cân bằng tải, sticky sessions và tính cô lập

### 13.1. Thuật toán routing và backend utilization

Một thuật toán tốt giúp phân phối traffic, nhưng security posture còn phụ thuộc:

- Backend có **resource limits**, quotas và autoscaling thresholds phù hợp không?
- Có endpoint tải nặng hơn nhiều dù số request ngang nhau không?
- Routing theo client IP/hash có khiến nhiều user NAT dồn lên một instance không?
- Một backend bị **unhealthy** có nhanh chóng bị loại không?
- Policy WAF/SG/cert có giống nhau trên mọi backend node không?

**Round robin không đồng nghĩa công bằng tài nguyên** nếu một request export tốn CPU 30 giây còn một request health tốn vài mili giây.

### 13.2. Session affinity / stickiness

Một số LB hỗ trợ **session affinity** bằng cookie, IP hash hoặc cơ chế tương tự. Sticky sessions có thể giúp ứng dụng cũ giữ state, nhưng cũng tạo rủi ro:

- Một backend nóng hơn các backend khác.
- Khi backend chết, session state bị mất nếu ứng dụng chỉ lưu local memory.
- Cookie của LB có thể bị xử lý sai về domain, path, SameSite, Secure hoặc lifetime.
- Routing theo IP có thể khiến hàng trăm người dùng sau NAT bị gom vào một target.

**LB stickiness cookie không tự là authentication cookie.** Nó thường phục vụ định tuyến; ứng dụng vẫn phải xác thực session/token và bảo vệ CSRF hoặc session fixation theo đặc tính sản phẩm.

Giải pháp bền vững hơn trong nhiều ứng dụng cloud là **stateless app nodes** với shared state/store có bảo mật phù hợp, nhưng phải cân nhắc latency, consistency và mục tiêu vận hành.

### 13.3. Backend pool và blast radius

Không nên trộn backends có mức nhạy cảm khác nhau trong một target group chỉ vì cùng port 443. Phân tách theo **mục đích ứng dụng, tenant boundary, môi trường production/lab, quyền IAM và network zone**.

Một lỗi routing rule theo hostname có thể chuyển request chứa token của khách A tới ứng dụng B. Cần kiểm tra:

- Default action của listener.
- Host/path priority và wildcard matching.
- Redirect/rewrite và tính nhất quán với authorization.
- Rate limits tại gateway và backend.
- Chỉ số 4xx/5xx theo **target group/service**, không chỉ toàn LB.

## 14. High availability, multi-AZ và cross-region

### 14.1. Multi-AZ không phải bảo đảm ứng dụng toàn vẹn

Cloud LB có thể được triển khai qua nhiều availability zones, nhưng ứng dụng vẫn có **single points of failure** như một database, credential store, shared rate limiter hoặc egress NAT gateway.

~~~mermaid
flowchart TD
    U["Internet client"] --> L["Cloud LB / Public endpoint"]
    L --> A["App targets - AZ A"]
    L --> B["App targets - AZ B"]
    A --> D["Shared data / dependency"]
    B --> D
    M["Observability + health policies"] -.-> L
    M -.-> A
    M -.-> B
    M -.-> D
~~~

**HA ở LB** không có nghĩa **HA end-to-end** khi cả hai app AZ cùng phụ thuộc một cache/DB lỗi hoặc Identity Provider không sẵn sàng.

### 14.2. Cross-zone/cross-region traffic

Đánh giá:

- LB có thể route giữa các zones/regions không, và những giới hạn nào áp dụng?
- Network firewall/SG/NSG, service tags và routes có nhất quán ở mỗi vùng không?
- Lưu lượng liên vùng có tạo chi phí, độ trễ hoặc thay đổi residency requirements không?
- Health status/circuit breaker có loại đúng vùng không khỏe?
- DNS/global traffic manager có caching/TTL ảnh hưởng failover không?
- Mọi region có cùng WAF policy, TLS/cert, access log, secrets và IAM guardrails không?

Một DR region được triển khai nhưng **quên WAF hoặc origin access restriction** có thể trở thành đường truy cập yếu hơn production chính.

### 14.3. Failover và failback

Một kế hoạch tốt cần chỉ rõ **trigger, quyết định, quyền thao tác, điểm kiểm chứng và rollback**.

Ví dụ:

~~~text
Normal:
  Region A phục vụ phần lớn traffic.
  Region B sẵn sàng hoặc dự phòng theo thiết kế.

Incident:
  Health checks + synthetic tests xác nhận A suy giảm.
  Cơ chế điều phối chuyển traffic theo policy.
  Kiểm tra WAF, TLS, IAM, origin rules tại B.

Recovery:
  Dữ liệu và dependencies đạt điều kiện failback.
  Chuyển traffic từng bước và theo dõi errors/latency.
~~~

Không diễn giải **DNS TTL** là cam kết mọi client chuyển vùng ngay khi hết TTL. Recursive resolvers, client caches, kết nối đã mở và global LB semantics ảnh hưởng kết quả thực tế.

## 15. DNS, IPv4/IPv6 và hybrid connectivity

### 15.1. DNS tên miền của LB

Một public LB thường được tiếp cận qua hostname. DNS có thể dùng A/AAAA, CNAME/alias hoặc các cơ chế của provider. Cần giám sát:

- Domain ownership và quyền sửa DNS.
- TTL và sự thay đổi endpoint khi failover.
- Certificate SAN/SNI tương ứng hostname.
- Đường CDN/WAF chính thức so với origin hostname.
- Cấu hình DNSSEC nếu vùng/domain sử dụng, cùng chính sách resolver phù hợp.

**DNSSEC xác thực dữ liệu DNS theo chuỗi tin cậy** khi được dùng đúng, nhưng **không bảo đảm ứng dụng HTTPS có chứng thư hợp lệ** và không thay origin firewall/WAF.

### 15.2. Dual-stack

Với một endpoint hỗ trợ cả IPv4 và IPv6, cần kiểm tra **mọi lớp**:

| Lớp | IPv4 | IPv6 |
| --- | --- | --- |
| DNS | A record | AAAA record |
| Edge/WAF | IPv4 ingress policy | IPv6 ingress policy |
| LB listener/frontends | IPv4 endpoint | IPv6 endpoint theo khả năng |
| SG/NSG/firewall | IPv4 source/destination | IPv6 source/destination |
| Rate limit | IPv4 source/identity | IPv6 address/prefix/identity |
| Backend | Có thể IPv4-only | Có thể IPv6 hoặc LB thực hiện proxy translation |

Không suy ra **backend phải dual-stack** chỉ vì frontend hỗ trợ IPv6: một số L7 proxies có thể nhận IPv6 ở edge rồi dùng IPv4 đến target. Tuy nhiên bảo vệ inbound v6 vẫn phải tương đương yêu cầu v4; một cấu hình chỉ chặn **0.0.0.0/0** không tự bao phủ **::/0**.

### 15.3. Internal LB qua peering, VPN và private connectivity

Internal LB có thể phục vụ workloads từ:

- Cùng VPC/VNet hoặc các subnet được định tuyến tới.
- Peering/hub-spoke, transit gateway/virtual WAN.
- VPN site-to-site, remote-access hoặc dedicated private circuit.
- Cross-account/project private endpoint khi nhà cung cấp hỗ trợ.
- Hybrid on-prem workloads.

**Private route là quyền tới mạng, không phải quyền vào ứng dụng.** Cần xem source network, service identity, mTLS/auth, firewall và policy từ từng trust domain. Tránh tạo một “internal LB allow-all” rồi để mọi mạng được peering có thể gọi API quản trị.

### 15.4. Egress cũng cần kiểm soát

Backend sau LB có thể cần kết nối tới database, object storage, third-party APIs hoặc identity services. Nếu backend có outbound Internet quá rộng, một workload bị chiếm có thể chuyển dữ liệu ra ngoài dù đường vào được bảo vệ tốt.

Kiểm soát **egress firewall/NAT gateway/private endpoints, DNS policies, workload identity và logs**, đồng thời đảm bảo health/renewal/telemetry không bị chặn nhầm.

## 16. Cloud load balancer trong Kubernetes

### 16.1. Service type LoadBalancer, Ingress và Gateway API

Trên Kubernetes, các API khác nhau mô tả ý định định tuyến:

| Kubernetes resource | Mục đích | Ranh giới cần kiểm tra |
| --- | --- | --- |
| **Service type LoadBalancer** | Yêu cầu môi trường cấp endpoint LB cho một Service | Có thể tạo public hoặc internal LB tùy controller/annotations/config |
| **Ingress** | Khai báo host/path routing cho HTTP(S) qua ingress controller | Tính năng TLS/WAF và LB phụ thuộc controller đang chạy |
| **Gateway API** | Tách vai trò quản lý gateway/listener/routes và attachment policies theo implementation | Không tự bảo đảm backend isolation hoặc WAF nếu chưa cấu hình |
| **NetworkPolicy** | Kiểm soát lưu lượng pod ở phạm vi CNI hỗ trợ | Không phải mọi CNI/cluster đều áp giống nhau; không thay external SG |
| **Pod readiness probe** | Quyết định pod sẵn sàng nhận traffic | Không tự chứng minh đã có authz hoặc app behavior đúng |

**Tên resource không quyết định phạm vi public/private.** Một Service type LoadBalancer có thể vô tình tạo public address nếu cluster/controller default như vậy. Cần có policy-as-code, admission/guardrails và review annotations/parameters cho đúng cloud.

### 16.2. Ba lớp dễ bị bỏ quên

1. **Cloud LB / security group / node ingress:** client có thể tới những địa chỉ và cổng nào?
2. **Kubernetes ingress/gateway/controller:** TLS, hostname/path, rewrites, headers, WAF, rate limit được gắn chỗ nào?
3. **Service/pod network:** NetworkPolicy và service authorization có ngăn đường direct pod-to-pod không?

Một ingress đã gắn WAF không bảo vệ pod nếu **NodePort, LoadBalancer Service thứ hai hoặc internal network path** vẫn cho truy cập trực tiếp ứng dụng.

### 16.3. Ví dụ Kubernetes NetworkPolicy về ý định, không phải public LB config

Giả sử namespace **app-lab** có pods gắn nhãn **app: web** và ingress controller chạy trong namespace **ingress-lab**, gắn nhãn **app: ingress-gateway**. Một chính sách có thể giới hạn ingress tới web pods từ đúng controller:

~~~yaml
# Chỉ là ví dụ lab có CNI hỗ trợ NetworkPolicy đúng cách.
# Cần xác minh namespace/pod labels và plugin thực thi trước khi áp.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: only-ingress-to-web
  namespace: app-lab
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-lab
          podSelector:
            matchLabels:
              app: ingress-gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

**Giới hạn quan trọng:** NetworkPolicy áp theo semantics của CNI và phạm vi pods/namespace, **không phải** rule cho cloud LB frontend, SG hoặc WAF. Trong một số cơ chế forwarding/NAT, source pod/IP mà NetworkPolicy nhìn thấy có thể khác dự kiến. Cần **kiểm thử từ đúng ingress controller**, không chỉ tin manifest đã apply thành công.

Với ingress-nginx, gateway controller, service mesh hay cloud-native controller khác, có thể cần thêm policy tại cloud và controller. Một app được phép nhận từ ingress vẫn cần **TLS backend nếu policy yêu cầu, auth/authz và resource limits**.

### 16.4. Certificate management và automation

Kubernetes workloads có thể sử dụng controller quản lý TLS certificates hoặc service mesh workload CA. Cần kiểm soát:

- Quyền đọc/cập nhật Secrets và external secret stores.
- Certificate issuance permissions, SAN/hostname allowlists và thời gian hết hạn.
- TLS termination location: edge LB, ingress gateway, mesh proxy hoặc app.
- Rotation/reload và đồng bộ trên nhiều pods/controllers.
- Không log private keys, JWTs hoặc nguyên nội dung Secret trong CI/CD.
- Khả năng đẩy trust updates tới workloads và ảnh hưởng tới connections đang mở.

### 16.5. Tránh hai tầng “cùng chịu trách nhiệm” nhưng không tầng nào thực thi

Một cloud LB có thể cho phép tất cả HTTP requests, ingress controller cho rằng WAF nằm tại cloud edge, còn app cho rằng ingress đã xác thực user. Nếu không định rõ trách nhiệm, **authentication, WAF và size limits** có thể bị bỏ trống.

Lập một bảng phân công **control → enforcement point → owner → test evidence**. Chỉ ghi “dùng cloud LB + Kubernetes Ingress” không đủ để mô tả bảo mật.

## 17. Cloud-native quan sát và giám sát LB

### 17.1. Cần log gì ở từng lớp?

| Nguồn | Dữ liệu có thể có | Giá trị |
| --- | --- | --- |
| **CDN/edge** | Edge response, cache status, WAF actions, source context | Phân biệt chặn ở edge với request tới origin |
| **LB access logs** | Listener, frontend/backend info, request/connection, status, latency, target | Truy vết load balancing và tầng tạo lỗi |
| **WAF logs** | Matched rule, action, bot/rate signals, request metadata | Xác định rule chặn và false positive |
| **Cloud flow logs** | IP/port/protocol, allow/deny theo khả năng | Tìm đường direct access và vấn đề L3/L4 |
| **Health/target metrics** | Healthy/unhealthy target count, response time | Tìm backend bị loại hoặc failover |
| **Application logs** | Authenticated principal, route ID, app status, business action | Xác minh authorization và nguyên nhân lỗi |
| **Control-plane audit** | Ai tạo/sửa/xóa LB, listener, WAF, SG, DNS | Phát hiện config drift và thay đổi trái phép |
| **PKI/cert monitoring** | Certificate expiry, TLS handshake failures | Ngăn mất khả năng truy cập do cert |

**Không mặc định** cloud LB access log ghi nội dung đầy đủ của mọi HTTP request, TCP packet hoặc dữ liệu đã mã hóa. Semantics của từng field phụ thuộc loại LB và nhà cung cấp. Tránh sử dụng log vượt phạm vi quyền riêng tư hoặc thu thập raw Authorization/cookie/token.

### 17.2. Một sự kiện giả lập

~~~json
{
  "time_utc": "2026-11-28T08:00:00Z",
  "request_id": "req-cloud-lab-0042",
  "component": "public-l7-lb-lab",
  "listener": "https-443",
  "host": "app.lab.example",
  "route_id": "GET:/api/items",
  "client_ip_verified": "198.51.100.42",
  "target_pool": "app-private-a",
  "lb_status": 502,
  "target_status": null,
  "waf_action": "allow",
  "target_connect_ms": 5000,
  "policy_version": "lab-policy-v3"
}
~~~

Đây là **JSON minh họa**, không phải schema của một provider. Địa chỉ **198.51.100.42** nằm trong dải dành cho tài liệu theo RFC 5737; thời gian và tên dịch vụ là giả định. Trường **target_status: null** có thể giúp đặt giả thuyết chưa nhận được HTTP response từ backend, nhưng **không đủ** để kết luận lý do 502 khi chưa có network/health/app logs.

### 17.3. Dashboard và metric quan trọng

| Metric | Câu hỏi trả lời | Giới hạn diễn giải |
| --- | --- | --- |
| **Frontend requests / connections** | Traffic đến LB tăng ở đâu? | Số kết nối không đồng nghĩa số user hoặc request |
| **Requests/response codes theo listener/path** | Route nào có 4xx/5xx? | Cần phân biệt LB-generated và target-generated |
| **Healthy target count** | Backends có đủ điều kiện nhận traffic? | Health endpoint có thể không đại diện app |
| **Target response latency** | Upstream chậm hay proxy chậm? | Cache, queue, retries và tracing ảnh hưởng |
| **TLS handshake errors** | Lỗi cipher, cert, SNI, protocol? | Không phải mọi lỗi đều do attack |
| **WAF blocks/challenges/counts** | Rule nào đang tác động traffic? | Block không tự chứng minh request độc hại |
| **DDoS signals/mitigation events** | Có chiến dịch mạng hoặc L7? | Tùy coverage, không phải ground truth tuyệt đối |
| **Active connections/streams** | Có nguy cơ cạn state? | HTTP/2 multiplexing làm khác request count |
| **Byte throughput / packets** | Băng thông đến/đi đang dùng bao nhiêu? | Không đủ phân biệt attack và traffic hợp lệ |
| **Backend CPU/memory/DB pool** | Có thực sự giảm tải backend không? | LB khỏe chưa chắc DB khỏe |
| **Autoscaling/capacity/quota** | Có chạm giới hạn vùng/cloud? | Autoscaling có độ trễ và trần |
| **Cost / egress / WAF charges** | Có chi phí bất thường hay denial of wallet? | Billing có thể có độ trễ |
| **Config change / drift** | Ai thay policy và khi nào? | Cần audit log đáng tin |

### 17.4. Correlation ID xuyên các hop

Một request có thể có ID do CDN, LB, gateway hoặc application tạo. Cần thiết kế **tracing/request correlation**:

1. Edge tạo hoặc chuẩn hóa request ID, không tin ID tự khai làm bằng chứng danh tính.
2. Các hop có thể ghi local request ID và liên kết với trace context được phép.
3. Ghi **source of 4xx/5xx**, target identity, latency và WAF action nếu hỗ trợ.
4. Backend log **authenticated principal/tenant** đã xác minh, không tin raw client header.
5. Bảo vệ nội dung log; tránh để trace baggage/headers làm lộ secrets.

**Không có một request ID thống nhất** không có nghĩa không thể điều tra, nhưng sẽ khó phân biệt lỗi phát sinh tại edge, LB, ingress hay backend. Có thể dùng timestamp, hostname, path, client verified IP, trace ID và target logs để đối chiếu trong thời gian phù hợp.

### 17.5. Phát hiện hành vi đáng ngờ

Các tín hiệu cần xem theo bối cảnh:

- Tăng mạnh WAF blocks sau một lần thay rule.
- Nhiều request 401/403 tới API login hoặc admin routes.
- Một nguồn gửi nhiều connections đến listener không cần thiết.
- Healthy targets giảm đột ngột trong khi traffic tăng.
- Nhiều TLS handshake errors từ tập client/ASN bất thường.
- Lưu lượng direct-to-origin bị network policy từ chối.
- Một backend có status/latency lệch các backend khác.
- Xóa logging hoặc WAF attachment ngay trước khi traffic tăng.

Tín hiệu đơn lẻ chưa đủ kết luận xâm nhập. Cần đối chiếu **change records, deploys, application logs, baseline, threat intelligence phù hợp và incident triage**.

## 18. Những rủi ro thiết kế đặc thù cần threat model

### 18.1. Bảng kịch bản

| Nguy cơ | Tác động | Lớp giảm thiểu |
| --- | --- | --- |
| **Direct origin bypass** | Tránh WAF/rate limit ở edge | Private backends, origin ACL, mTLS và ingress inventory |
| **L7 flood tới endpoint nặng** | CPU/DB cạn dù LB còn hoạt động | WAF/rate limit, cost/concurrency/timeout, queue |
| **Client IP spoofing qua proxy header** | Né limiter, sai audit, policy bypass | Trusted chain, header normalization, network restriction |
| **TLS backend không xác minh server** | Có mã hóa nhưng thiếu đảm bảo danh tính đích | Backend trust policy, cert validation, mTLS |
| **WAF count-only nhầm là block** | Request nguy hiểm vẫn được chuyển | Verify action/mode và test deny |
| **Body inspection truncation** | Payload ngoài phần inspect có thể qua | Hard body/decoded limits và app validation |
| **Health checker bị chặn** | Targets unhealthy, gây downtime | Probe source allow rules đúng provider |
| **Health endpoint trả 200 dù app lỗi** | LB tiếp tục gửi traffic tới instance không hoạt động đúng | Readiness và synthetic checks |
| **Listener default route sai** | Lộ admin hoặc tenant khác | Host allowlist, rule priority, backend authorization |
| **SNI/Host confusion** | Request route tới backend ngoài ý định | Validation, route consistency và TLS test |
| **Misconfigured cache** | Lộ response riêng tư giữa users | Cache key partition, Cache-Control, auth-aware caching |
| **Session affinity sai** | Phân bố tải lệch, session mất khi node down | Stateless design hoặc shared session store |
| **Multi-region policy drift** | DR region ít bảo vệ hơn primary | IaC/guardrails, parity tests, canary |
| **Control plane IAM compromise** | Gỡ WAF, thay route hoặc backend | Least privilege, MFA/approval, audit và drift detection |
| **Expensive autoscale reaction** | Chi phí cloud tăng bất thường | Budgets, rate limits, autoscale caps và monitoring |
| **Log/telemetry gap** | Không phát hiện outage hay bypass | Pipeline health, retention, multi-source correlation |

### 18.2. Defense in depth không đồng nghĩa bật mọi tính năng

Nhiều lớp chỉ có giá trị nếu **mỗi lớp có phạm vi và trách nhiệm rõ**. Ví dụ:

- CDN giảm traffic vào origin, nhưng không quyết định user có được xem đơn hàng của người khác.
- WAF lọc một số payload HTTP, nhưng không đảm bảo query DB có chi phí thấp.
- SG/NSG giới hạn cổng và nguồn, nhưng không kiểm tra OAuth token.
- mTLS xác thực workload, nhưng không tự cấp quyền cho mọi API action.
- API rate limit giảm request floods, nhưng không chống bão hòa đường mạng trước edge.
- IDS/IPS/NDR ở một điểm mạng không nhìn thấy payload TLS nếu không được thiết kế cho điều đó.

Mục tiêu là **khép kín đường đi có khả năng bị khai thác**, không phải tăng số biểu tượng bảo mật trên sơ đồ.

## 19. Thiết kế triển khai và thay đổi an toàn

### Bước 1 — Xác định mục đích dịch vụ và ranh giới tin cậy

Trước tiên ghi rõ:

- Dịch vụ **public, internal hoặc hybrid**?
- Giao thức: HTTP(S), TCP, UDP, gRPC, WebSocket, HTTP/3 hay hỗn hợp?
- Client là khách công cộng, nhân viên VPN, partner API, workload khác hay IoT?
- Những vùng/tenant/tài nguyên nào **không được** truy cập?
- Các tiêu chí availability, RTO/RPO, latency, data residency và chi phí?

Không nên chọn **L4 hoặc L7** chỉ vì đội vận hành quen dùng sản phẩm. Loại LB phải phù hợp protocol, bảo mật cần thực thi và đường đi thật.

### Bước 2 — Lập bản đồ ingress và backend inventory

Liệt kê theo phạm vi được phép quản trị:

- DNS names, frontend IP, listeners và public/private classification.
- CDN/edge, WAF policies, L4/L7 LBs, gateways/ingress controllers.
- Target groups, backends, subnet/zone, security group/NSG và route.
- TLS termination points, certificates, truststore và backend encryption.
- Health checks, autoscaling groups, Kubernetes Services/Ingress/Gateways.
- Đường phụ: IPv6, origin IP, legacy LB, private endpoint, VPN/peering.

Vì hệ thống cloud có thể đổi IP theo thời gian, nên sử dụng **resource IDs, tags, policy attachments và inventory từ control plane**, không chỉ một bảng địa chỉ IP tĩnh.

### Bước 3 — Định nghĩa security controls theo hop

Ví dụ bảng phân công:

| Hop | Owner | Control | Cách kiểm chứng |
| --- | --- | --- | --- |
| Internet → CDN | Edge/security | DDoS protections, WAF, request policy | Edge logs, blocked request lab |
| CDN → Public LB | Platform/network | Origin restriction, TLS, allowed sources | Direct-to-origin denied |
| LB → App | Network/platform | SG/NSG, TLS backend, health checks | Allow/deny và TLS identity test |
| App → Data | App/data/network | DB auth, network isolation, encryption | Unauthorized app path denied |
| Control plane | Cloud platform | Least-privilege IAM, approvals, audit | Change audit và drift alert |
| All hops | Observability/SOC | Request correlation, telemetry | End-to-end synthetic + logs |

**Điều kiện kiểm chứng phải là hành vi thực**, không chỉ “WAF policy đã tồn tại” hoặc “security group đã khai báo”.

### Bước 4 — Chọn giới hạn tài nguyên

Quyết định **body/header size caps, rate/concurrency limits, timeouts, maximum connections, queuing, retries và circuit breakers**. Cần phân biệt:

- Global edge limits và post-auth per-user/tenant budgets.
- Health-check request với user requests.
- Một HTTP request có thể cần nhiều CPU/DB operations.
- Request timeouts so với connection idle timeouts và drain timeout.
- Streaming/gRPC/WebSocket connections so với request/stream concurrency.

Chọn giá trị theo **tải hợp lệ và năng lực dịch vụ**, không áp một con số từ ví dụ cho mọi ứng dụng.

### Bước 5 — Infrastructure as Code và guardrails

Khuyến nghị quản lý LB, listeners, backend pools, firewall, WAF attachments và logging thông qua **IaC có review** nếu tổ chức đã áp dụng quy trình này. Với policy-as-code:

- Không chấp nhận public backend có ingress trái chuẩn.
- Kiểm tra public LB phải có TLS policy/chứng thư hợp lệ.
- Kiểm tra WAF attachment ở các ứng dụng bắt buộc.
- Không cho secrets/private keys xuất hiện trong repository/state không được bảo vệ.
- Gắn owner, environment, data classification và change ticket.
- Theo dõi drift giữa hạ tầng thực tế và source-of-truth.

**IaC apply thành công không đồng nghĩa kiểm soát đã hoạt động.** Cần thử end-to-end và phản hồi từ target thực sau deploy.

### Bước 6 — Triển khai theo giai đoạn

1. Tạo backend private, kiểm tra health/readiness và quyền truy cập nội bộ.
2. Tạo internal/pubic listeners theo thiết kế, gắn đúng chứng thư và routing.
3. Áp SG/NSG/firewall và khóa origin đường vào phụ.
4. Gắn WAF/DDoS/edge policies, chạy quan sát/count trước khi block khi phù hợp.
5. Thiết lập access/audit logs, metrics, alerts, request IDs và log retention.
6. Kiểm thử từ client lab, từng AZ/region, IPv4/IPv6 và các quyền khác nhau.
7. Thực hiện canary/traffic shift, giám sát 4xx/5xx, health và business outcomes.
8. Xác minh failover, scale, certificate renewal và rollback trước khi mở rộng.

### Bước 7 — Rollback và incident readiness

Một rollback có thể là **phục hồi WAF rule cũ**, chuyển traffic về backend pool ổn định hoặc hoàn nguyên listener/SG change. Không nên “rollback” bằng cách **mở toàn bộ backend ra Internet** nếu rủi ro có thể tránh bằng phương án hẹp hơn.

Runbook cần có **người phê duyệt, trạng thái trước/sau, nơi lấy log, ngưỡng báo động, lệnh/tiến trình khôi phục theo provider và cách kiểm tra sau khi thay đổi**.

## 20. Kiểm thử trong môi trường cloud/lab được phép

**Quy tắc an toàn:** chỉ kiểm thử endpoints thuộc tài khoản hoặc phòng lab bạn được phép quản trị. Không tạo traffic flood, quét rộng Internet, thử nghiệm DDoS thật hay gửi payload khai thác vào dịch vụ không được ủy quyền. Với managed cloud services, phải tuân thủ chính sách thử nghiệm của nhà cung cấp và tổ chức.

### 20.1. Topology lab minh họa

~~~text
Public hostname:   app.lab.example
Public HTTPS LB:   listener TCP/443
WAF:               gắn đúng public frontend
App backend:       private subnet, service port 8080
Health route:      GET /health
Admin endpoint:    không public
DB:                private, không nhận trực tiếp từ LB
Sources:
  Client A:        authorized test client
  Client B:        test client không thuộc allowlist private

Address examples (chỉ để minh họa):
  Client A:        198.51.100.10
  Client B:        203.0.113.20
  Backend:         192.0.2.50
~~~

Các dải IPv4 **192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24** dành cho tài liệu theo RFC 5737, không thể tự dùng như địa chỉ cloud thực. Các hostname là placeholder cần thay bằng địa chỉ lab thuộc quyền quản trị.

### 20.2. Ma trận allow/deny và resilience

| Test | Nguồn → đích | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- |
| HTTPS hợp lệ | Client A → public LB | TLS đúng tên, ứng dụng phản hồi đúng | TLS verify, access/app logs |
| Hostname sai | Client A → frontend với host không được phục vụ | Từ chối/route mặc định an toàn | Listener routing và logs |
| Backend trực tiếp | Client B → backend public/alternate path | Không thể truy cập service | Route/SG deny và inventory |
| Backend từ LB | LB → app port | Được phép theo rule cụ thể | Health/target logs |
| App → DB | App được cấp quyền → DB | Được phép đúng identity | DB auth và network logs |
| LB → DB | LB → DB | Không có quyền/đường | Firewall/service policies |
| Health check | Nguồn probe phù hợp → /health | Đúng target health state | Health metrics |
| WAF deny sample | Client lab → route/rule đã phê duyệt | Block ở đúng WAF hop | WAF rule ID/action log |
| WAF count mode | Client lab → rule count | Không bị block bởi count-only | WAF action logs |
| Authentication | Anonymous → protected API | Bị deny, không bypass qua LB | App auth logs |
| Headers nguồn giả | Client gửi XFF tự khai | Verified IP không bị thay sai | Gateway/app logs |
| IPv6 | Client IPv6 → hostname AAAA nếu hỗ trợ | Chính sách tương đương IPv4 | DNS, listener và firewall logs |
| Multi-AZ | Disable test target có kiểm soát | Traffic chỉ tới healthy targets | Health và target logs |
| Certificate error | SNI/tên không phù hợp ở test endpoint | Client TLS verify thất bại | Client diagnostics |
| WAF/SG drift | Mô phỏng thay đổi trên staging | Cảnh báo và kiểm tra chặn phù hợp | IaC policy, audit |
| Backend load | Nhóm request hợp lệ tải nhỏ | Không quá timeouts/queues | p95 latency, backend metrics |

**Không chỉ kiểm tra cho phép.** Một hệ thống có thể “chạy tốt” về chức năng nhưng vẫn cho client đi thẳng vào backend. Nghiệm thu bảo mật phải có cả **positive tests và negative tests**.

### 20.3. Lệnh quan sát HTTP/TLS an toàn

Các lệnh dưới chỉ gửi một request tới hostname lab được phê duyệt:

~~~bash
# Xem status và response headers từ frontend lab.
curl --head --max-time 10 https://app.lab.example/health

# Xem TLS certificate và chain public do server trình.
# Chỉ dùng với hostname lab có DNS và endpoint thật.
openssl s_client \
  -connect app.lab.example:443 \
  -servername app.lab.example \
  -verify_hostname app.lab.example \
  -verify_return_error \
  < /dev/null
~~~

**Không dùng tùy chọn bỏ xác minh TLS** để làm phép thử “thành công”. Nếu gặp lỗi chứng thư, kiểm tra hostname/SNI, chain, truststore và clock. Một phép thử tới hostname đúng chưa chứng minh toàn bộ backends/regions đều cấu hình đúng.

### 20.4. Kiểm tra DNS đúng phạm vi

~~~bash
# Lệnh đọc DNS, không gửi traffic ứng dụng.
nslookup app.lab.example

# Nếu môi trường có dig:
dig app.lab.example A
dig app.lab.example AAAA
~~~

Khi frontend có cả A/AAAA records, cần đánh giá **ngữ nghĩa routing và security policies của hai họ địa chỉ**. Nếu không có AAAA, chưa thể kết luận toàn bộ dịch vụ “không hỗ trợ IPv6”; có thể endpoint IPv6 nằm ở một hostname khác hoặc yêu cầu bật riêng.

### 20.5. Không tự tin HTTP status đơn lẻ

| Kết quả | Giả thuyết ban đầu | Cần xác minh thêm |
| --- | --- | --- |
| **200/2xx** | Endpoint phản hồi thành công | Có đúng backend/identity/route và policy không? |
| **301/302/308** | Redirect | Có open redirect hoặc chuyển sang HTTP không? |
| **400** | Request/headers không hợp lệ | Tầng nào tạo lỗi; Host/SNI/framing |
| **401/403** | Authentication/authorization hoặc WAF deny | App auth logs hay WAF action? |
| **404** | Route không có hoặc mặc định | Có route sai đưa tới service khác không? |
| **413** | Body vượt limit ở một hop | Edge, LB, gateway hay app tạo lỗi? |
| **429** | Rate limiting | Policy/key nào, Retry-After có không? |
| **502** | Bad Gateway | LB không nhận phản hồi upstream hợp lệ, TLS/backend connect? |
| **503** | Service unavailable | Backend unhealthy, dependency lỗi, quota hoặc policy? |
| **504** | Gateway timeout | Upstream không phản hồi kịp, timeout nào? |

Một ứng dụng có thể tự trả những mã trên; không thể quy mọi 403 cho WAF hoặc mọi 502 cho backend chỉ dựa vào **status**. Phải đối chiếu **log theo hop** và trace/request ID.

### 20.6. Negative test TLS/backend identity

Trong lab, có thể cấu hình một **backend test certificate có SAN không khớp** và quan sát LB có từ chối kết nối backend khi policy yêu cầu hostname validation hay không. Điều này cần môi trường staging cô lập; không dùng man-in-the-middle hoặc sửa certificate production để kiểm chứng.

Mục tiêu là xác định **khả năng xác minh backend identity thực sự** của sản phẩm đang dùng, không chỉ xem một checkbox “Use HTTPS backend”.

## 21. Chẩn đoán sự cố Cloud LB và các lớp bảo vệ

~~~mermaid
flowchart TD
    A["Ứng dụng sau Cloud LB gặp lỗi"] --> B{"DNS/Frontend và TLS hoạt động?"}
    B -->|Không| C["DNS, public/private LB, listener, cert, SNI"]
    B -->|Có| D{"WAF/edge có chặn request?"}
    D -->|Có| E["Xem rule ID, mode, scope, false positive"]
    D -->|Không| F{"Có backend healthy?"}
    F -->|Không| G["Probe source, readiness, route, SG/NSG"]
    F -->|Có| H{"LB kết nối và nhận phản hồi backend?"}
    H -->|Không| I["Target port, TLS backend, timeout, connection"]
    H -->|Có| J["Authn/authz/app/DB/cost/limits"]
    C --> K["Kiểm thử lại qua đúng hostname/region"]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

### 21.1. Không thể kết nối frontend

Kiểm tra hostname DNS, public/private LB, listener đã bật, cloud routing, SG/NSG inbound, HTTP vs HTTPS, certificate/chain và trạng thái deployment. Nếu client đang ở Internet mà LB là **internal**, lỗi truy cập có thể đúng theo chính sách thay vì là downtime.

### 21.2. LB có listener nhưng backend unhealthy

Kiểm tra:

- Backend process lắng nghe đúng address/port/protocol.
- Health path/status hoặc matcher có phù hợp thực tế?
- SG/NSG/firewall cho phép **health checker source** không?
- Endpoint có yêu cầu đăng nhập/Host header khiến probe thất bại?
- Backend dependencies hoặc readiness có lỗi?
- Có một AZ/region bị thiếu route, DNS hoặc secret không?

**Không mở toàn bộ backend cho Internet** chỉ để health check thành công.

### 21.3. Lỗi TLS ở frontend hoặc backend

Frontend: sai certificate/SAN/SNI, expired cert, thiếu intermediate hoặc TLS policy không tương thích. Backend: LB không tin CA, hostname mismatch, client cert sai, target không hỗ trợ giao thức hoặc policy security không cho kết nối. Hai lỗi có thể xuất hiện cùng lúc nhưng thuộc **hai TLS edges khác nhau**.

### 21.4. Nhiều HTTP 403 sau khi bật WAF

Đọc WAF action/rule IDs; phân biệt **block/challenge/count**, payload, route, source identity và thời điểm thay policy. Nếu request hợp lệ bị chặn, điều chỉnh rule **hẹp và có kiểm thử**, tránh tắt toàn bộ WAF hoặc allow mọi traffic từ IP NAT của khách.

### 21.5. HTTP 502/503/504 tăng đột ngột

Theo dõi **target healthy count, target connection error, upstream latency, backend logs, autoscaling và deployment timeline**. Một 502 có thể đến từ protocol/TLS mismatch hoặc target đóng kết nối; 503 có thể do pool không có healthy targets hoặc quá tải; 504 thường liên quan upstream timeout. **Nghĩa chính xác phụ thuộc proxy/provider**, nên cần log cụ thể.

### 21.6. Ứng dụng còn hoạt động nhưng backend bị truy cập trực tiếp

Ưu tiên đánh giá như **sự cố phân đoạn**. Kiểm tra public IP, secondary listener, IPv6, legacy DNS, Kubernetes Service/NodePort, SG/NSG, peering/VPN và routing. Khóa đường không được phép theo quy trình để tránh ảnh hưởng production hợp lệ; xác minh lại WAF attachment trên luồng chính.

### 21.7. Latency tăng khi WAF/DDoS/rate limits đang hoạt động

Đo **edge latency, LB processing time, backend target time, queue/concurrency và database latency**. WAF không tự là nguyên nhân; cache miss, backend autoscale delay hoặc ứng dụng truy vấn DB chậm có thể tạo cùng biểu hiện. Đối chiếu thời điểm deploy và raw metric theo từng hop trước khi thay cấu hình.

### 21.8. Chỉ một AZ hoặc một node gặp lỗi

Kiểm tra target registration, route/security policy, TLS cert, container version, health endpoint và deployment status theo AZ. Nếu một AZ thiếu WAF không phải do WAF thường gắn ở frontend chung, nhưng **đường ingress phụ hoặc stack dự phòng** có thể chưa có policy tương đương. Cần biết nơi chính sách thực sự được gắn, không suy đoán từ vị trí backend.

### 21.9. Không có WAF log nhưng client vẫn truy cập được

Khả năng gồm: WAF chưa attach, mode không ghi log, log pipeline lỗi, request đi đường bypass hoặc một route không được inspect. Kiểm tra **data path thực**, attachment/action, metrics và log delivery health. Không kết luận “không có attack” từ việc WAF logs rỗng.

## 22. Tình huống tổng hợp: Public API đa vùng với LB, WAF và backend riêng

### 22.1. Bối cảnh

Một tổ chức vận hành **Orders API** trên cloud. Khách hàng sử dụng website và ứng dụng di động. Hạ tầng có:

- Public DNS hostname **orders.lab.example**.
- CDN/WAF ở edge.
- Regional HTTPS L7 load balancer ở **Region A**.
- Hai nhóm backend application tại **AZ A** và **AZ B**.
- Database riêng, worker xử lý báo cáo và một API nội bộ.
- Dịch vụ định danh dùng OAuth/OIDC, API keys cho đối tác.
- Một cụm dự phòng ở **Region B**.

Chính sách ban đầu:

~~~text
Internet -> CDN/WAF -> Public HTTPS LB -> App targets -> DB
                         |
                         +--> /api/orders
                         +--> /api/reports
                         +--> /admin   (đáng lẽ private)

Observed issues:
  1. App VM ở AZ B còn public IP và mở cổng 8080.
  2. WAF tại edge bật Count, đội vận hành nghĩ là Block.
  3. LB -> App dùng HTTPS nhưng chưa biết có xác minh SAN backend hay không.
  4. API rate limit chỉ theo remote IP ở App, thường là IP của LB.
  5. Health checker bị chặn sau khi siết SG.
  6. Region B chưa có policy parity và audit logs đầy đủ.
~~~

### 22.2. Phân tích từng sai lệch

| Vấn đề | Nguy cơ | Điều chỉnh kiến trúc |
| --- | --- | --- |
| VM AZ B có public IP/port 8080 | Client có thể bỏ qua WAF và LB | Gỡ đường public không cần thiết, dùng private targets và source-restricted ingress |
| WAF Count bị hiểu là Block | Payload phù hợp rule vẫn được cho qua | Xác minh WAF mode, canary rồi chuyển rule cần thiết sang Block |
| HTTPS backend nhưng không rõ validation | Mã hóa không chắc xác thực đúng backend | Kiểm tra backend certificate trust/hostname; thêm mTLS/proxy nếu yêu cầu |
| Limiter chỉ thấy IP LB | Users chung bucket, chặn oan hoặc mất công bằng | Định nghĩa trusted proxy chain và post-auth verified identity budgets |
| Chặn nhầm health probes | Backend bị loại khỏi pool | Cho đúng nguồn health checks theo provider; giữ backend không public |
| Region B thiếu WAF/audit | Failover sang region yếu hơn | IaC parity tests, audit, cert và WAF attachment trước DR exercise |
| /admin đi qua public listener | Bề mặt quản trị công khai | Tách internal LB/identity-aware administrative access, kiểm tra authz |

### 22.3. Sơ đồ sau cải tiến

~~~mermaid
flowchart LR
    C["Clients"] --> EDGE["CDN + WAF block policy<br/>DDoS mitigation"]
    EDGE --> LB["HTTPS Public L7 LB"]
    LB --> APP["Private app targets<br/>AZ A + AZ B"]
    APP --> DB["Private DB"]
    ADMIN["Admins + IdP / VPN<br/>được phê duyệt"] --> ILB["Internal LB"]
    ILB --> MGMT["Admin service"]
    AUDIT["Audit / SIEM"] -. "Edge + LB + App + IAM logs" .-> LB
    AUDIT -. "Policy/config monitoring" .-> ILB
    B["Region B DR"] -. "Equivalent ingress/security policy" .-> EDGE
~~~

Sơ đồ là đề xuất kiến trúc tổng quát, không cam kết một giải pháp DR cụ thể hay chế độ global routing. Tùy provider, DR edge routing, private endpoints và health monitors có các thành phần riêng.

### 22.4. Ma trận kiểm chứng trước đưa vào production

1. **Client hợp lệ** truy cập Orders API qua public hostname, TLS verify và app authorization đúng.
2. **Client không có quyền** không đọc/ghi đơn hàng của tenant khác dù qua WAF thành công.
3. **Client Internet thử đường direct backend** bị chặn, bao gồm IPv4, IPv6 và alternate ports.
4. **WAF test request đã được phê duyệt** khớp rule và bị chặn ở chế độ Block đúng scope.
5. **XFF giả từ Internet** không thay verified client identity của gateway/app.
6. **Probe source** có thể kiểm tra health; một app target hỏng được loại khỏi pool.
7. **Backend certificate SAN sai** trong lab bị từ chối nếu chính sách yêu cầu backend identity verification.
8. **/admin** không truy cập công khai; qua internal route vẫn đòi identity/authorization.
9. **Region B** có cùng security baselines và telemetry khi thực hiện DR test.
10. **Gỡ một instance có kiểm soát** không khiến những request không idempotent bị thực thi trùng không phát hiện.
11. **Request lớn/đắt tiền** được bảo vệ bằng body/cost/concurrency caps.
12. **Log** liên kết được edge request, WAF action, LB status và application trace.

## 23. Câu hỏi tự kiểm tra

### 23.1. Câu hỏi

1. Điểm khác nhau quan trọng nhất giữa **L4 LB** và **L7 HTTP LB** khi gắn WAF là gì?
2. Một **internal LB** có mặc nhiên an toàn nếu VPC kết nối nhiều chi nhánh qua VPN không?
3. Tại sao CDN có WAF vẫn có thể không bảo vệ được app nếu origin public?
4. Với TLS termination ở LB và HTTP backend, “end-to-end encryption” đã đúng chưa?
5. Backend dùng HTTPS có tự chứng minh LB kiểm tra đúng chứng thư backend không?
6. Vì sao Host và SNI phải được xem xét riêng trong multi-tenant virtual hosts?
7. WAF đang **Count** có chặn các request khớp rule không?
8. Tại sao **WAF inspection cap** khác **hard body cap**?
9. Nếu app nhận remote peer là IP LB, điều gì xảy ra với limiter theo IP ở app?
10. Vì sao không chọn địa chỉ đầu tiên trong X-Forwarded-For một cách mù quáng?
11. Khi health checker bị firewall chặn, LB có thể có hành vi gì?
12. Vì sao readiness của app không nên được xác minh chỉ bằng TCP connect?
13. Một LB chạy nhiều AZ có bảo đảm DB và IdP luôn sẵn sàng không?
14. Nếu thêm CDN caching, điều gì phải kiểm soát để tránh lộ response giữa tenants?
15. Kubernetes Service type LoadBalancer có tự gắn WAF và NetworkPolicy không?
16. Một rule SG/NSG cho LB → app có thay authorization theo user không?
17. Tại sao cần kiểm tra cả **IPv6 alternate path** dù IPv4 đã khóa origin?
18. Nếu client nhận HTTP 503, có thể kết luận ngay WAF đã block không?
19. Vì sao route /admin nên được đánh giá riêng thay vì đặt chung public listener?
20. Một cuộc volumetric DDoS làm nghẽn đường upstream có được giải quyết đơn giản bằng cách thêm VM không?
21. Khi Region B là disaster recovery, vì sao cần kiểm thử **WAF và IAM parity** chứ không chỉ failover DNS?
22. Trong một incident origin bypass, hai loại bằng chứng quan trọng nhất bạn nên tìm là gì?

### 23.2. Gợi ý trả lời

**(1)** L4 thường quyết định dựa trên kết nối/transport và không tự parse HTTP; WAF cần điểm L7 nhìn được HTTP sau giải mã. **(2)** Không: internal LB có thể truy cập từ các nguồn qua routing/peering/VPN được phép. **(3)** Client đi trực tiếp origin bỏ qua điểm WAF. **(4)** Chưa, vì chặng LB→backend truyền HTTP plaintext. **(5)** Không; cần kiểm tra semantics của backend trust/hostname validation ở đúng dịch vụ.

**(6)** SNI chọn TLS identity còn HTTP Host/:authority dùng cho HTTP routing; sai khác có thể dẫn đến route/certificate khác. **(7)** Thông thường Count chỉ ghi nhận, không chặn bởi rule đó. **(8)** Inspection cap giới hạn phần được phân tích; hard cap giới hạn toàn body được chấp nhận. **(9)** Các users có thể bị gộp một bucket và bị chặn oan hoặc policy trở nên không đúng. **(10)** Header có thể chứa giá trị do client tự khai; phải xác định trusted proxy chain.

**(11)** Targets bị đánh dấu unhealthy, traffic ngừng hoặc lỗi. **(12)** Process có thể mở TCP port nhưng auth, routes hoặc dependencies chưa sẵn sàng. **(13)** Không; các dependencies có thể là single points of failure. **(14)** Cache key theo user/tenant, response Cache-Control, Authorization và cookie behavior. **(15)** Không; controller, cloud integration và policies phải được cấu hình riêng. **(16)** Không; SG/NSG bảo vệ luồng mạng, ứng dụng vẫn phải xác thực và phân quyền.

**(17)** Một rule IPv4 không tự chặn IPv6. **(18)** Không; 503 có thể do unhealthy pool, outage, capacity hoặc ứng dụng. **(19)** Quản trị có yêu cầu trust/identity cao hơn và thường không cần public entrypoint. **(20)** Không; cần mitigation upstream/edge trước đường nghẽn. **(21)** Region B có thể có ingress route, chứng thư, WAF, secret hoặc audit khác primary. **(22)** Bằng chứng đường direct traffic có thể vào backend và bản ghi SG/NSG/route/target cho thấy điểm thực thi thiếu deny.

## 24. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có cloud LB là tự được chống mọi DDoS.” | Phụ thuộc loại attack, provider coverage và ứng dụng phía sau. |
| “L4 LB có thể WAF mọi HTTP body như L7.” | Passthrough không tự cung cấp HTTP inspection. |
| “Internal LB không cần xác thực.” | Internal routes vẫn có thể nối nhiều trust domains và workload đã bị chiếm. |
| “Cloud managed service tự cấu hình WAF, IAM và TLS an toàn.” | Khách hàng chịu trách nhiệm về cấu hình phù hợp theo shared responsibility. |
| “Gắn WAF vào một LB bảo vệ mọi hostname/ingress.” | Phải kiểm tra attachment, listener, region, resource và mọi đường phụ. |
| “WAF Count mode đã chặn request.” | Count chỉ ghi nhận theo semantics chế độ; cần Block/enforcement. |
| “WAF đọc 16 KiB body nghĩa là body lớn hơn 16 KiB bị chặn.” | Inspection cap khác hard reject cap; tùy cấu hình xử lý vượt hạn. |
| “Public backend có WAF phía trước vẫn an toàn.” | Direct origin có thể bypass nếu không chặn đường đó. |
| “HTTPS LB → HTTPS backend nghĩa là backend đã được xác thực.” | Cần xác minh chain, SAN/identity và chính sách backend TLS. |
| “Client IP luôn là TCP remote peer backend thấy.” | Có thể là edge, LB, proxy hoặc NAT. |
| “X-Forwarded-For là dữ liệu client ID đáng tin.” | Header cần trust chain; IP không phải identity của user. |
| “HTTP Host tự chứng minh client được truy cập tenant đó.” | Host là phần request phải được validate và kết hợp authorization. |
| “Healthy TCP port là ứng dụng xử lý đúng.” | Readiness và end-to-end synthetic cần ngữ cảnh ứng dụng. |
| “Sticky LB cookie chính là login session.” | Affinity cookie thường phục vụ routing, không thay auth session. |
| “Multi-AZ LB tự tạo HA cho mọi dependencies.” | Database, secrets, IdP, cache và quota store vẫn có thể lỗi. |
| “DNS TTL đảm bảo chuyển vùng ngay lập tức.” | Resolvers, client caches và open connections ảnh hưởng failover. |
| “Service type LoadBalancer của Kubernetes luôn private.” | Public/internal phụ thuộc controller và cấu hình cloud. |
| “NetworkPolicy Kubernetes thay SG/NSG và WAF.” | Mỗi cơ chế thực thi tại một lớp khác nhau. |
| “Không có WAF log là không có tấn công.” | Có thể thiếu attachment, pipeline hoặc request đi bypass. |
| “HTTP 403 luôn do WAF, 502 luôn do app.” | Status có thể được tạo ở nhiều hop; cần trace/log. |
| “Đã khóa origin qua IPv4 thì IPv6 tự an toàn.” | IPv6 có routing/firewall/listeners riêng. |
| “Mở mọi nguồn backend sẽ chữa lỗi health check an toàn.” | Phải xác định đúng nguồn probe và giới hạn ingress. |
| “Auto-scaling vô hạn có thể thay DDoS protection.” | Vẫn có uplink, service quotas, cost và downstream bottlenecks. |

## 25. Checklist nghiệm thu Cloud LB và các lớp bảo vệ

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| Public/private scope | LB nào được phép Internet-facing và vì sao? | Inventory frontend/listener và approval |
| Loại LB | L4/L7 có phù hợp protocol và WAF requirements? | Kiến trúc traffic path và test |
| TLS frontend | Client kiểm tra đúng hostname, chain và policy TLS? | TLS validation tests và certificate inventory |
| TLS backend | Chặng backend được mã hóa và xác thực theo yêu cầu? | Backend negative identity test |
| WAF attachment | Chính sách gắn đúng resource/region và action=Block khi cần? | Rule ID, test event và WAF logs |
| DDoS defense | Có upstream mitigation và escalation runbook? | Provider/config documentation và tabletop |
| Origin restriction | Không có đường direct-to-origin công cộng? | Negative tests IPv4/IPv6, SG/NSG/route |
| Source IP chain | Verified client IP không bị XFF spoofing? | Ingress config và log comparison |
| Host/SNI | Hostname không hợp lệ không route tới admin/tenant khác? | Listener/default-route tests |
| Backend segmentation | Chỉ LB/gateway/probes được phép vào app? | SG/NSG/NetworkPolicy và deny evidence |
| Data isolation | LB không thể trực tiếp truy cập DB không cần thiết? | Network/DB authorization tests |
| Health checks | Probe nguồn đúng, path nhẹ và readiness phản ánh target? | Health logs và controlled outage test |
| HA | Lỗi một target/AZ được xử lý phù hợp? | Draining/failover test và metrics |
| DR region | WAF, TLS, IAM, origin ACL và logging parity? | Region B parity tests |
| Kubernetes ingress | Không có NodePort/Service/alternate ingress bypass? | Controller inventory, policy tests |
| Rate/resource limits | RPS, cost, body, concurrency và timeout phù hợp? | Boundary tests, backend utilization |
| Logs | Phân biệt edge, LB, target, WAF và app errors? | Correlation request ID và SIEM dashboards |
| IAM/control plane | Quyền sửa LB/WAF/SG tối thiểu, có audit? | Role review, change logs |
| Privacy | Không log credentials/tokens/payload nhạy cảm? | Data handling review, retention policy |
| Rollback | Có versioned policy, owner và điều kiện khôi phục? | Approved runbook và canary results |

**Nguyên tắc nghiệm thu:** không đánh dấu PASS chỉ vì một tính năng được bật trong control plane. Hãy chứng minh **request hợp lệ đi được theo tuyến mong muốn** và **request không được phép bị chặn ở đúng ranh giới**, rồi đối chiếu log, metrics và trạng thái backend.

## 26. Tổng kết

**Cloud load balancer** tạo điểm vào và cơ chế phân phối traffic cho dịch vụ cloud, nhưng chỉ là **một thành phần của kiến trúc bảo vệ mạng**. Muốn một ứng dụng vừa sẵn sàng vừa an toàn, cần xác định rõ nó dùng **L4 hay L7, public hay private, TLS termination ở đâu, request đi qua WAF/DDoS ở đâu, backend nào được phép nhận traffic và chính sách nào bảo vệ control plane**.

Các điểm quan trọng:

- **CDN/WAF và DDoS protection** giúp bảo vệ edge; chúng không thay API authorization hay backend resource limits.
- **Origin isolation** là yêu cầu cốt lõi: backends không được lộ đường phụ bỏ qua WAF, kể cả public IP, IPv6, legacy listener hoặc Kubernetes Service khác.
- **TLS ở hai chặng** phải được kiểm chứng độc lập; mã hóa backend chưa đủ nếu không kiểm tra đúng server identity.
- **Client IP/Host/XFF** không tự là danh tính tin cậy; cần chuẩn hóa qua trusted proxy chain và kiểm tra quyền theo identity.
- **Security group/NSG/firewall, NetworkPolicy và IAM** hoạt động tại các lớp khác nhau và bổ sung cho nhau.
- **Health checks, draining, multi-AZ/DR, logging và capacity limits** là phần của an toàn vận hành chứ không chỉ hiệu năng.
- Chính sách phải được thử qua **allow/deny, negative tests, failure scenarios và log correlation** sau mọi thay đổi đáng kể.

Trong **SECURITY_NETWORK_SECURITY**, bài học này nối kiến thức về **phân đoạn, firewall, VPN, IDS/IPS, DNS, mạng không dây, xác thực kết nối và phòng vệ cloud** thành một kiến trúc **defense in depth**. Mục tiêu không phải xếp chồng càng nhiều sản phẩm càng tốt, mà là **đúng điểm thực thi, đúng ranh giới tin cậy, chính sách tối thiểu và bằng chứng vận hành có thể kiểm tra**.

### Tài liệu tham khảo và đọc thêm

- **AWS Elastic Load Balancing Documentation:** Application Load Balancer, Network Load Balancer, Gateway Load Balancer, listeners, target groups, health checks và bảo mật.
- **AWS WAF và AWS Shield Documentation:** WAF policy association, rate-based rules, DDoS protection và phạm vi hỗ trợ.
- **Microsoft Azure Load Balancer, Application Gateway và Azure Front Door Documentation:** L4/L7, WAF, network security, health probes và cấu hình edge.
- **Google Cloud Load Balancing và Cloud Armor Documentation:** loại application/network LB, health checks, edge security policies và deployment modes.
- **Kubernetes Documentation — Service, Ingress, Gateway API và NetworkPolicy:** phạm vi các API và những cơ chế network/access controls.
- **RFC 9110 — HTTP Semantics:** Host/authority, các mã trạng thái HTTP và ngữ nghĩa request/response.
- **RFC 9112 / RFC 9113 / RFC 9114:** HTTP/1.1, HTTP/2 và HTTP/3 framing/protocol semantics.
- **RFC 7239 — Forwarded HTTP Extension:** metadata chuyển tiếp qua HTTP proxies; không tự bảo đảm tính đáng tin.
- **RFC 8446 — TLS 1.3:** bảo mật kênh truyền, TLS handshake và các đặc tính như early data.
- **RFC 5280 — PKIX X.509 Certificate and CRL Profile:** chuỗi chứng thư và xác minh trust.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** địa chỉ dùng trong ví dụ và bài lab.
- **NIST SP 800-207 — Zero Trust Architecture:** xác thực/ủy quyền theo tài nguyên và ranh giới.
- **OWASP API Security Top 10 (2023):** rủi ro authorization, bảo vệ tài nguyên và cấu hình API.
- **OWASP HTTP Request Smuggling / File Upload / Denial of Service Cheat Sheets:** kiểm soát HTTP framing, upload và tài nguyên ứng dụng.
- **Tài liệu nhà cung cấp/cloud controller đang vận hành:** xác minh chính xác khả năng WAF attachment, backend TLS, IPv6, rate limits, quotas, log fields và chi phí theo region/version.
