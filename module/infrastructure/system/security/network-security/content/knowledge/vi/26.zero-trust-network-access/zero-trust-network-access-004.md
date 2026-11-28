# Application-level access thay cho network-level access: Thiết kế Zero Trust Network Access theo từng ứng dụng

## 1. Đặt vấn đề: Truy cập một ứng dụng có cần truy cập cả mạng?

Trong mô hình truy cập từ xa truyền thống, một nhân viên có thể kết nối **VPN** để thiết bị nhận route tới các dải IP nội bộ. Sau khi thiết lập tunnel, các firewall và ACL quyết định thiết bị có thể kết nối tới **những địa chỉ và cổng** nào. Cách làm này rất hữu ích cho nhiều giao thức và hệ thống cũ, nhưng việc **có đường đi mạng** không đồng nghĩa người dùng cần toàn bộ những đích có thể đi tới.

Ví dụ: nhân viên kế toán chỉ cần sử dụng một website quản lý chi phí. Nếu VPN cấp quyền đến subnet chứa website, máy chủ file, cơ sở dữ liệu thử nghiệm và cổng quản trị, máy tính bị nhiễm mã độc có thể có **bề mặt dò tìm hoặc tấn công mạng rộng hơn nhu cầu nghiệp vụ**, trừ khi các biện pháp phân đoạn, host firewall và authorization đã siết chặt các đường đi.

**Application-level access** đặt câu hỏi ở phạm vi hẹp hơn:

> Chủ thể nào, từ thiết bị và bối cảnh nào, được phép truy cập **ứng dụng hoặc tài nguyên cụ thể nào**, thông qua phiên kết nối được kiểm soát nào?

Trong **Zero Trust Network Access (ZTNA)**, một bộ phận trung gian thực thi chính sách (broker, gateway hoặc proxy theo triển khai) có thể xác thực chủ thể, đánh giá ngữ cảnh và chỉ thiết lập luồng tới **ứng dụng được cấp quyền**, thay vì trao cho thiết bị một route chung tới toàn bộ mạng riêng. Điều này dịch trọng tâm từ **network location** sang **identity, resource, context và policy enforcement**.

Thuộc chương **Zero Trust Network Access** của học phần **SECURITY_NETWORK_SECURITY**, bài này nối các kiến thức **phân đoạn, firewall, VPN, xác thực kết nối, DNS, IDS/IPS, giám sát xâm nhập và bảo vệ mạng cloud** thành một thiết kế truy cập **theo ứng dụng**. ZTNA không có nghĩa bỏ mọi firewall hoặc coi VPN luôn không an toàn; nó là **một cách tổ chức quyền truy cập hẹp, xác minh trước khi cấp và giám sát trong quá trình sử dụng**, phù hợp với mô hình Zero Trust Architecture.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **network reachability**, **application reachability**, **authentication**, **authorization** và **session access**.
2. So sánh VPN L3/L4, reverse proxy/identity-aware proxy và ZTNA application broker mà không đơn giản hóa thành “VPN xấu, ZTNA tốt”.
3. Mô tả **Policy Engine (PE), Policy Administrator (PA), Policy Enforcement Point (PEP)** và các nguồn tín hiệu chính sách theo tư duy NIST SP 800-207.
4. Thiết kế truy cập dựa trên **user/workload identity, MFA, device posture, application identity, thời điểm, mức rủi ro và phạm vi tác vụ**.
5. Giải thích các đường đi ZTNA **clientless browser**, **endpoint agent**, **outbound connector**, **reverse-proxy gateway** và các khác biệt khi xử lý HTTP, SSH, RDP, TCP.
6. Bảo vệ **đường truy cập trực tiếp tới origin**, không tin proxy headers, session cookies hay token chưa xác minh; hiểu rủi ro session hijacking và policy bypass.
7. Tổ chức di chuyển theo từng ứng dụng từ truy cập mạng rộng sang least privilege, cùng rollback, logging, kiểm thử allow/deny và tình huống mất IdP/connector.

## 2. Năm lớp khái niệm phải tách biệt

| Khái niệm | Câu hỏi | Ví dụ | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Network reachability** | Gói tin có route và vượt qua firewall tới IP/cổng không? | Laptop mở TCP tới 10.40.8.20:443 | Người dùng có quyền truy cập dữ liệu |
| **Application reachability** | Client có được chuyển tới dịch vụ cụ thể không? | Proxy chỉ chuyển tới app expense | Quyền thực hiện mọi thao tác trong app |
| **Authentication** | Chủ thể đang trình danh tính gì, được xác minh thế nào? | SSO + phishing-resistant MFA | Chủ thể có quyền ở mọi tenant |
| **Authorization** | Chủ thể được thao tác nào trên resource nào? | User được xem hóa đơn của nhóm mình | Request không vượt quota hoặc app không có lỗi |
| **Session enforcement** | Quyền truy cập đang được duy trì/thu hồi theo chính sách nào? | Gateway chặn phiên khi bị khóa tài khoản | Mọi kết nối cũ tự hủy ngay nếu gateway không kiểm tra lại |

Một firewall rule **ALLOW TCP/443** không thể diễn giải nghiệp vụ **“được xem chi phí của phòng ban A, nhưng không được phê duyệt thanh toán phòng ban B”**. Ngược lại, một ứng dụng có authorization hoàn chỉnh vẫn cần lớp network segmentation để giảm khả năng truy cập các port khác hoặc các dịch vụ không liên quan.

**Phạm vi cấp quyền có thể khác nhau:** một sản phẩm ZTNA chỉ hỗ trợ **allow tới host:port** sau xác thực, sản phẩm khác có thể gắn **HTTP path/method**, thiết bị và quyền tải xuống. Không được gọi mọi policy “application-level” là **fine-grained object authorization**. Quyền trên từng bản ghi, tenant hoặc thao tác nghiệp vụ thường vẫn phải được thực thi trong **ứng dụng/API**.

### 2.1. Hai sai lầm kiến trúc đối xứng

- **Nhầm A:** “Đã kết nối VPN, vậy người dùng đã được tin.” Sai vì VPN tunnel xác thực/kết nối vào mạng không mặc nhiên cấp quyền trên ứng dụng và dữ liệu.
- **Nhầm B:** “Đã có ZTNA proxy, vậy không cần network firewall và app authorization.” Sai vì có thể còn direct-to-origin, east–west traffic, application vulnerabilities hoặc proxy routes cấu hình sai.

Giải pháp là bảo đảm **network policy, application access policy và business authorization** bổ trợ nhau, với vị trí thực thi và kiểm thử được ghi rõ.

## 3. Network-level access truyền thống

### 3.1. Mô hình truy cập ở cấp mạng

~~~mermaid
flowchart LR
    USER["Nhân viên / thiết bị"] --> VPN["VPN concentrator<br/>Xác thực tunnel"]
    VPN --> ROUTE["Đường đi tới subnet nội bộ"]
    ROUTE --> FW["Firewall / ACL"]
    FW --> APP["Ứng dụng chi phí :443"]
    FW --> FILE["File server :445"]
    FW --> ADMIN["Admin endpoint :22"]
    FW --> DB["Database :5432"]
~~~

**Sơ đồ chỉ minh họa khả năng kết nối**, không khẳng định VPN mặc định cho phép tất cả các cổng trên. Một triển khai VPN đúng có thể dùng **per-user ACL, microsegmentation, posture checks, MFA và host firewalls** để hạn chế gần tương đương phạm vi ứng dụng.

Điểm cần xem là **sau khi xác thực tunnel, thiết bị được phép định tuyến tới những đối tượng nào**, và việc authorization ở **mỗi ứng dụng** diễn ra ở đâu.

### 3.2. Những hạn chế có thể xuất hiện

1. **Network location thành tín hiệu tin cậy quá mạnh:** sau khi vào một mạng riêng, client có thể có nhiều đường đi hơn thực sự cần.
2. **Flat hoặc coarse-grained segmentation:** quyền tới một CIDR/subnet không phản ánh từng ứng dụng, từng vai trò.
3. **Phát hiện dịch vụ:** thiết bị nhiễm mã độc có thể thử kết nối tới các máy/cổng còn reachable.
4. **Kết nối dài và quyền thay đổi:** identity hoặc trạng thái thiết bị đổi khi VPN tunnel còn mở; phụ thuộc cách tunnel và gateway đánh giá lại.
5. **Third-party access:** mở rộng VPN cho đối tác có thể dẫn đến cấp route/ACL phức tạp và khó quan sát.
6. **Tài sản không nằm trong cùng mạng:** môi trường multi-cloud/SaaS/hybrid khiến quản lý route, split tunneling và dải IP ngày càng khó.

**Nhưng không được quy mọi rủi ro cho VPN.** Truy cập rộng thường bắt nguồn từ policy và topology. Với các ứng dụng không thể đi qua proxy, các kết nối cấp mạng được **siết theo host/cổng/identity** vẫn là lựa chọn hợp lý.

### 3.3. VPN vẫn có vị trí

VPN có thể cần cho:

- Giao thức đặc thù không tương thích với gateway/proxy ZTNA được chọn.
- Quản trị cơ sở hạ tầng qua network management protocols với kiểm soát bổ sung.
- Kết nối **site-to-site** hoặc giữa mạng cloud/on-prem ở cấp hạ tầng.
- Workload legacy phụ thuộc discovery/broadcast/complex port ranges, khi chưa thể tách ứng dụng.
- Một số nhu cầu khôi phục khẩn cấp hoặc quản lý hạ tầng trong môi trường hạn chế.

Một chiến lược Zero Trust có thể **giữ VPN cho nhóm nhu cầu cụ thể**, đồng thời chuyển các ứng dụng phù hợp sang application-level access. Mục tiêu là **least privilege và giám sát**, không nhất thiết là thay mọi tunnel bằng một sản phẩm duy nhất.

## 4. Application-level access thực sự thay đổi điều gì?

### 4.1. Mô hình chỉ cho ứng dụng được phép

~~~mermaid
flowchart LR
    U["User + thiết bị"] --> PEP["ZTNA enforcement gateway<br/>Đánh giá phiên/kết nối"]
    IDP["Identity provider + MFA"] -. "Identity assurance" .-> PDP["Policy decision"]
    DEV["Device posture / MDM / EDR"] -. "Tín hiệu thiết bị" .-> PDP
    CTX["Ứng dụng, quyền, bối cảnh, rủi ro"] -. "Policy inputs" .-> PDP
    PDP -. "Permit / deny / conditions" .-> PEP
    PEP -->|"Chỉ phiên được cấp quyền"| A["Private expense application"]
    PEP -. "Không có route được cấp"| B["Other private workloads"]
    PEP -. "Access telemetry" .-> LOG["Audit / SOC"]
~~~

Người dùng yêu cầu truy cập **expense.app.example**. Broker/gateway xác minh phiên/danh tính và policy; nếu được phép, nó chỉ tạo đường tới **ứng dụng expense**, trong khi thiết bị không cần nhận route tới file server, DB hoặc toàn subnet chứa ứng dụng.

**Không phải mọi ZTNA đều proxy từng HTTP request.** Một số sản phẩm tạo phiên TCP ứng dụng được ủy quyền, một số chạy ở endpoint/network layer để thực hiện per-destination access, một số tích hợp reverse proxy trong ingress. Điều kiện tối thiểu là **giảm quyền truy cập mạng rộng thành các tài nguyên được phép** và thực thi quyết định dựa trên danh tính/ngữ cảnh thay vì chỉ “đang ở mạng nội bộ”.

### 4.2. Access theo ứng dụng có nhiều mức hạt

| Mức cấp quyền | Điều được phép | Ví dụ | Biện pháp vẫn cần |
| --- | --- | --- | --- |
| **App/host** | Truy cập một hostname/service | expense.app.example | Authorization từng user/resource trong app |
| **App + port/protocol** | Chỉ TCP/443 hoặc RDP tới một server | RDP tới jump host được duyệt | Strong auth, session logging |
| **App + HTTP route/method** | GET /reports nhưng không POST /admin | Identity-aware L7 proxy | Không thay kiểm tra object/tenant trong app |
| **App + identity posture** | Chỉ user nhóm Finance từ managed device | SSO/MFA + MDM attestation | Chống session/token theft và thiết bị bị chiếm |
| **App + session conditions** | Access chỉ trong thời gian công việc | Time-bound privileged access | Revocation và kiểm tra quyền bên backend |
| **Object/business authorization** | Chỉ hóa đơn của tenant A | App RBAC/ABAC/BOLA prevention | Cần thực thi ở backend/data layer |

**ZTNA thường kiểm soát điều kiện đến ứng dụng**, còn ứng dụng/API quyết định quyền chi tiết sau khi đã vào. Một PEP có L7 policy tốt có thể giảm rủi ro, nhưng **chỉ đặt route policy ở proxy không chứng minh backend tránh BOLA/IDOR**.

### 4.3. Có phải “ẩn” ứng dụng là đã an toàn?

Một private application không công bố public listener trực tiếp sẽ giảm attack surface. Nhưng **không public DNS** hoặc dùng địa chỉ khó đoán không phải authentication; người dùng có thể tìm ra IP/hostname bằng nhiều nguồn hoặc do cấu hình rò rỉ.

Giá trị bảo mật đến từ **không có đường kết nối không được phép** tới origin, **xác thực danh tính** và **thực thi policy trước khi tạo phiên**. “Dark application” chỉ là hiệu ứng giảm khả năng phát hiện khi thực sự có boundary, không thay authorization.

## 5. Zero Trust theo NIST SP 800-207

### 5.1. Các nguyên tắc gốc

Zero Trust Architecture hướng tới **bảo vệ tài nguyên** và giảm việc suy ra độ tin cậy chỉ từ vị trí mạng. Những nguyên tắc thường dùng:

- **Mọi nguồn dữ liệu và dịch vụ được xem là tài nguyên** cần bảo vệ.
- **Mọi communication được bảo mật** phù hợp yêu cầu, bất kể trong/ngoài mạng.
- **Truy cập từng tài nguyên được cấp theo từng phiên/điều kiện** với least privilege.
- Quyết định dựa trên **chính sách động** từ identity, trạng thái chủ thể/tài sản, tài nguyên và bối cảnh.
- Theo dõi trạng thái tài sản, tích lũy **telemetry**, đánh giá và cải thiện chính sách liên tục.
- Authentication và authorization được thực hiện trước khi quyền truy cập tài nguyên được cấp.

Zero Trust **không có nghĩa mặc định không tin một cách cảm tính** hoặc “bắt MFA ở mỗi HTTP request”. Nó yêu cầu một cơ chế quyết định có bằng chứng, phạm vi hẹp và khả năng đánh giá lại theo chính sách.

### 5.2. Vai trò PE, PA và PEP

~~~mermaid
flowchart TB
    SUBJECT["Subject<br/>User / device / workload"] --> PEP["Policy Enforcement Point<br/>Gateway / proxy / agent"]
    PEP <--> RESOURCE["Enterprise resource<br/>Ứng dụng được bảo vệ"]
    PEP -. "Access request + context" .-> PE["Policy Engine<br/>Đưa ra decision"]
    PE --> PA["Policy Administrator<br/>Tạo/đóng control path"]
    PA -. "Session instructions" .-> PEP
    IDP["Identity + MFA"] -.-> PE
    CDM["Device security + inventory"] -.-> PE
    THREAT["Threat / activity / policy inputs"] -.-> PE
    PEP -. "Access logs" .-> AUDIT["Audit / SIEM"]
~~~

Theo mô hình khái niệm NIST:

- **Policy Engine (PE):** đánh giá yêu cầu và dữ liệu liên quan để đưa ra **grant/deny/revoke** theo policy.
- **Policy Administrator (PA):** thực hiện hành động tạo, cấu hình hoặc kết thúc control path/phiên dựa trên quyết định của PE.
- **Policy Enforcement Point (PEP):** thành phần cho phép, giám sát hoặc chấm dứt kết nối từ subject đến enterprise resource.

Đây là **vai trò logic**, không bắt buộc là ba máy chủ riêng. Một sản phẩm có thể kết hợp PE/PA trong cloud control plane và triển khai PEP trên endpoint, tại edge, ở ingress hoặc trên connector. Hãy phân biệt **control plane** ra quyết định với **data plane** thực thi traffic.

### 5.3. PEP đặt ở đâu?

| Vị trí | Ưu điểm | Cần kiểm chứng |
| --- | --- | --- |
| **Cloud-edge identity-aware proxy** | Không cần mở route từ laptop vào subnet | Backend không bị gọi thẳng; TLS, headers, sessions |
| **Endpoint agent + access fabric** | Có thể hỗ trợ private TCP applications | Agent integrity, route scope, split tunnels, bypass |
| **Application ingress/gateway** | Gắn quyền theo host/path/service | Direct-to-origin và L7 parsing/HTTP bypass |
| **Service-side connector** | Kết nối outbound từ private network | Connector identity, segmentation, quyền đến các upstream |
| **Service mesh/workload PEP** | Workload-to-workload mTLS và authorization | Pods/paths không đi qua mesh; application authz |
| **Host/process-level gateway** | Hạn chế một tiến trình hoặc endpoint | Coverage khi agent chết/đổi process, quyền OS |

**Đặc tính hỗ trợ khác nhau giữa sản phẩm/phiên bản.** Không chọn vị trí PEP theo marketing slogan; chọn theo **protocol, threat model, khả năng bảo vệ origin và bằng chứng test deny**.

## 6. Các mô hình triển khai application-level ZTNA

### 6.1. Reverse proxy cho web application

Với website nội bộ, một mô hình là **HTTPS client → identity-aware proxy → private web application**. Gateway nhận request, xác thực user qua IdP/SSO, đánh giá policy rồi tạo kết nối tới backend.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant G as ZTNA web gateway / PEP
    participant I as IdP + MFA
    participant D as Policy decision
    participant A as Private app
    U->>G: GET https://expense.app.example/
    G->>I: Redirect / authorization flow
    I-->>U: Login + MFA (nếu cần)
    U->>G: Redirect/callback theo giao thức
    G->>I: Xác minh phiên / token phù hợp
    G->>D: User + device + app + context
    D-->>G: Permit session / conditions
    G->>A: Proxy request qua kết nối được bảo vệ
    A-->>G: App response
    G-->>U: Response và session controls
~~~

Sơ đồ là **luồng logic đơn giản**, không thay tài liệu triển khai OpenID Connect/OAuth/SAML cụ thể. Trong hệ thống thật, authorization code, PKCE, state, nonce, redirect URI, cookie và token validation phải được xử lý đúng profile. Browser thường **không tự gửi ID token tới mọi backend**; kiến trúc gateway/backend quyết định cách trao identity đã xác minh.

**Ưu điểm:** người dùng có thể truy cập web qua browser mà không nhận route nội bộ. **Giới hạn:** WebSockets, HTTP/2, streaming, file upload, download, SPA/API calls, CORS, redirect/cookie domain, HTTP/3 và long-lived sessions phải được kiểm thử với đúng gateway.

### 6.2. Outbound connector từ mạng riêng

Một kiểu khác đặt **connector** trong VPC/VNet/on-prem network. Connector tự thiết lập **kết nối outbound đã xác thực** tới access fabric. Gateway chuyển các phiên đã được phê duyệt qua connector tới đúng app.

~~~mermaid
flowchart LR
    USER["User + client"] --> EDGE["ZTNA cloud access edge"]
    PE["Policy decision + IdP/device context"] -. "Authorize" .-> EDGE
    EDGE <-->|"Control / data path theo thiết kế"| CONN["Private connector<br/>Outbound authenticated connection"]
    CONN -->|"Allow only app target"| APP["Expense app 10.20.1.15:443"]
    CONN -. "Không cấp route chung"| OTHER["DB / file server / admin hosts"]
    FW["Private network policy"] -. "Restrict source/ports" .-> CONN
~~~

**Không mở inbound từ Internet đến origin** là lợi ích tiềm năng của outbound connector, nhưng phải kiểm chứng firewall thực tế, khả năng connector bị lợi dụng, authentication giữa connector–edge và tuyến kết nối nội bộ.

Nếu connector có đường tới cả subnet 10.20.0.0/16 mà policy chỉ nêu app, cần xác minh **broker thực sự không cho người dùng chọn tùy ý địa chỉ đích/port**. Defense in depth nên giới hạn **connector egress tới đúng backend**; một connector bị chiếm không nên mặc nhiên có khả năng quét toàn VPC.

### 6.3. Agent-based access cho TCP/SSH/RDP

Một **endpoint agent** có thể phối hợp với broker để chỉ mở kết nối tới **một destination application hoặc host:port**. Ví dụ kỹ sư được quyền SSH tới máy bảo trì trong 30 phút, nhưng không được truy cập các hosts hoặc ports khác trong cùng subnet.

Các cách triển khai khác nhau:

- Client tạo một **tunnel scoped theo ứng dụng hoặc destination** qua access fabric.
- Một gateway cung cấp **SSH/RDP proxy hoặc bastion** với session controls.
- Thiết bị định tuyến những **FQDN/IP/ports được cấp quyền** qua agent, không cấp route toàn mạng.
- Một số hệ thống cung cấp browser-based remote desktop/terminal qua proxy.

**Lưu ý:** Agent-based sản phẩm có thể vẫn gắn route ở OS hoặc sử dụng tunnel layer 3 cho một tập địa chỉ hẹp. Không được gọi nó là **HTTP-level authorization** nếu công cụ chỉ giới hạn **host:port TCP**.

### 6.4. Identity-aware application ingress

Trong cloud/Kubernetes, một L7 ingress/API gateway có thể xác thực user/token và áp policy trước khi route tới **một service**. Phù hợp cho internal applications, B2B APIs hoặc admin UIs. Tuy nhiên:

- Phải chặn **truy cập trực tiếp Service/Pod/NodePort/alternate LB** bỏ qua ingress.
- Identity headers phải được tạo từ nguồn đã xác minh.
- Backend vẫn áp **authorization theo user, tenant và resource**.
- NetworkPolicy/SG/firewall phải chặn traffic từ các sources ngoài gateway.

### 6.5. Clientless không đồng nghĩa mọi giao thức

**Clientless web ZTNA** thường thuận tiện cho browser-native applications. Với SSH, RDP, databases, thick-client apps, UDP hoặc discovery protocols, một số sản phẩm cần **native client agent, gateway chuyên dụng hoặc các connector hỗ trợ giao thức**. Không lựa chọn platform chỉ từ câu “mọi ứng dụng không cần VPN” khi chưa kiểm tra **danh sách protocol và luồng phụ thực tế**.

## 7. Phân biệt identity-aware proxy, ZTNA và API gateway

| Giải pháp | Thường thực hiện | Không tự có |
| --- | --- | --- |
| **Identity-aware reverse proxy** | SSO, chính sách truy cập website trước origin | Quyền tới từng record, hỗ trợ mọi TCP/UDP |
| **ZTNA access broker** | Kết nối user/device tới private app theo policy | Mọi chức năng PAM, EDR, DLP hoặc app authorization |
| **API gateway** | Token verification, routing, rate limiting, API policies | Bảo vệ đường trực tiếp vào origin nếu mạng mở |
| **PAM / privileged session gateway** | Cấp quyền quản trị thời hạn ngắn, session recording/approval theo sản phẩm | Tự phủ mọi ứng dụng web |
| **Service mesh** | mTLS/authorization giữa workloads có enroll | End-user SSO và traffic ngoài mesh |
| **VPN** | Tạo tunnel/route mạng riêng có kiểm soát | Per-application business authorization |
| **SASE/SSE platform** | Có thể kết hợp ZTNA, SWG, CASB, DLP theo dịch vụ | Chắc chắn có mọi chức năng trong mọi gói/tier |

**Các thuật ngữ chồng lấn:** một nền tảng có thể là identity-aware proxy và đồng thời là PEP của ZTNA; API gateway có thể đóng vai trò application PEP. Thiết kế nên ghi rõ **control cụ thể, vị trí thực thi và test case**, không chỉ nhãn sản phẩm.

## 8. Danh tính người dùng và xác thực mạnh

### 8.1. User identity nên đến từ đâu?

Với workforce ZTNA, nguồn danh tính thường là **Identity Provider (IdP)** được tổ chức quản lý qua OIDC/OAuth/SAML hoặc cơ chế tương đương. PEP phải dựa trên **kết quả xác thực đã được xác minh**, không tin HTTP header do client tự gửi.

Những dữ liệu có thể tham gia quyết định:

- User identifier ổn định và trạng thái account (active/disabled).
- Nhóm/role/department hoặc entitlement từ nguồn đã được quản trị.
- Authentication method/assurance, MFA hoàn tất hay chưa.
- Session age, sign-in risk và threat signals theo chính sách.
- Quan hệ với ứng dụng, project, tenant và thời hạn quyền.

**Email, display name và địa chỉ IP không phải định danh đủ mạnh.** Email có thể đổi, IP có thể được chia sẻ NAT, còn nhóm/role phải được kiểm tra nguồn và cập nhật theo lifecycle.

### 8.2. MFA và chống phishing

MFA giảm rủi ro khi mật khẩu bị lộ, nhưng mức bảo đảm khác nhau. **Phishing-resistant MFA** như WebAuthn/FIDO2 khi được cấu hình đúng giúp ràng buộc authentication với nguồn/phạm vi thích hợp, giảm rủi ro phishing so với OTP nhập tay.

Đối với ứng dụng nhạy cảm, có thể yêu cầu:

1. User thuộc nhóm được cấp quyền.
2. Authentication đạt mức bảo đảm được xác định.
3. Phiên đăng nhập còn hiệu lực và không có tín hiệu compromised.
4. Thiết bị đáp ứng chính sách tối thiểu.
5. Quyền truy cập chỉ dành cho app và thời gian cần thiết.

**MFA không thay authorization.** Một tài khoản vượt MFA có thể vẫn không được phép vào payroll, hoặc chỉ được đọc chứ không được phê duyệt thanh toán.

### 8.3. Tránh tin nhầm token

Đối với JWT dùng làm **access token**, hệ thống phải kiểm tra chữ ký và thuật toán được chấp nhận, issuer, audience, thời gian hiệu lực, loại token, các claim/binding liên quan và trạng thái thu hồi theo thiết kế. Việc **base64-decode payload để đọc sub** không phải xác minh.

**ID token** trong OpenID Connect phục vụ mục đích xác nhận sự kiện xác thực với **client dự kiến**, không mặc nhiên là access token để API chấp nhận ở mọi resource server. Không dùng một token chỉ vì nó có chứa user ID và chữ ký hợp lệ nhưng sai audience/purpose.

### 8.4. Token forwarding và trust boundary

Một gateway có thể **ủy quyền app access** rồi gửi identity context tới backend bằng:

- Token có audience dành riêng cho backend, được kiểm tra đầy đủ.
- Header nội bộ được **gateway ghi đè**, bảo vệ bằng mTLS/private network và không nhận từ Internet.
- Một assertion được ký hoặc cơ chế identity propagation theo profile.
- Backend session riêng được tạo theo các điều kiện đã xác minh.

Phải tránh **confused deputy**: backend không nên tin một header **X-Authenticated-User: admin** khi bất kỳ client nào có thể gọi thẳng backend và tự đặt nó. Ingress phải **strip/overwrite**, backend chỉ tin nguồn đã xác thực, và **direct-to-origin bị chặn**.

## 9. Device posture: Tín hiệu hỗ trợ, không phải niềm tin tuyệt đối

### 9.1. Posture có thể gồm những gì?

| Tín hiệu | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Device enrollment** | Có trong MDM/UEM | Thiết bị quản lý vẫn có thể bị compromise |
| **OS / patch level** | Version cập nhật theo baseline | Patch không chứng minh không có malware |
| **EDR/AV health** | Agent đang báo healthy | Telemetry có thể trễ hoặc bị can thiệp |
| **Disk encryption** | Full-disk encryption enabled | Không tự bảo vệ session đang mở |
| **Device certificate / key binding** | Chứng minh một khóa đã được đăng ký | Bảo vệ key và vòng đời thiết bị vẫn quan trọng |
| **Firewall/screen lock status** | Cấu hình endpoint theo chính sách | Không bảo đảm app không có lỗ hổng |
| **Device risk score** | Tín hiệu tổng hợp từ security platform | Phụ thuộc độ tin cậy, khả năng giải thích và thời điểm |
| **Endpoint agent health** | Agent hoạt động và báo cáo đúng | Agent thiếu quyền hoặc mất kết nối tạo điểm mù |

**Dữ liệu posture cần đến từ nguồn được kiểm soát**, có xác minh phù hợp. Không xem một chuỗi User-Agent, client-side JavaScript tự khai hoặc header **X-Device-Compliant: true** là bằng chứng thiết bị đã đạt compliance.

### 9.2. Posture “tại thời điểm” khác “liên tục”

Giả sử user được phép lúc 09:00 khi EDR healthy, nhưng đến 09:15 EDR phát hiện malware. Nếu PEP chỉ đánh giá posture **một lần khi đăng nhập** và cho phiên kéo dài 8 giờ, thay đổi này có thể không làm session bị cắt ngay.

Thiết kế cần nêu:

- Tần suất lấy lại posture và **độ trễ chấp nhận được**.
- Trigger risk events để **reauthorize/revoke**.
- Hành vi khi mất tín hiệu device compliance.
- Những kết nối đang mở được **ngắt, chờ hết phiên hay chỉ chặn kết nối mới**.
- Quy tắc ngoại lệ cho BYOD, contractors, thiết bị hạn chế.

**“Continuous verification” là mục tiêu kiến trúc**, không phải cam kết mọi packet được kiểm tra lại theo thời gian thực. Cần thử nghiệm **revocation latency** trên giao thức và gateway thực tế.

### 9.3. Managed, BYOD và unmanaged devices

| Thiết bị | Policy có thể phù hợp | Lưu ý |
| --- | --- | --- |
| **Managed employee laptop** | SSO/MFA + enrollment + patch/EDR posture | Không đồng nghĩa full trust |
| **BYOD** | Chỉ web app ít nhạy cảm, session ngắn, upload/download control khi hỗ trợ | Tránh thu thập telemetry cá nhân quá mức |
| **Vendor workstation** | Quyền một app, hợp đồng/thời hạn, strong MFA | Đối tác không nên nhận route cả subnet |
| **Privileged admin device** | Device trust mạnh hơn, JIT approval, PAM | Kiểm soát session/commands và out-of-band recovery |
| **Headless workload** | Workload identity/cert/token ngắn hạn thay user MFA | Lifecycle, identity binding và mTLS |

**Không áp chung một policy cho mọi người, mọi thiết bị.** Một thiết bị không quản lý có thể bị hạn chế hoặc từ chối những dữ liệu nhạy cảm, trong khi vẫn được phép dùng cổng hỗ trợ công khai nếu nghiệp vụ yêu cầu.

## 10. Chính sách ứng dụng: Identity × resource × context

### 10.1. Policy tuple

Một quyết định truy cập ứng dụng có thể mô hình hóa:

~~~text
Subject:
  authenticated_user_id
  groups, role, entitlements

Device:
  device_id, management_state, posture_timestamp

Resource:
  application_id, hostname, protocol, port, sensitivity

Context:
  time, session_age, risk, network signals

Action:
  connect / read route / start privileged session

Decision:
  PERMIT / DENY / REQUIRE_STEP_UP / REVOKE
~~~

Các field là **mô hình sư phạm**, không phải schema chuẩn của NIST hay một nhà cung cấp. Chọn đúng tín hiệu là quan trọng: **network location** có thể là *một input rủi ro* nhưng **không nên tự là bằng chứng người dùng được phép**.

### 10.2. RBAC, ABAC và relationship-based control

- **RBAC:** cấp quyền theo role, như FinanceReader → expense-app.
- **ABAC:** đánh giá thuộc tính user/device/resource/context; ví dụ managed device + user còn hợp đồng + app sensitivity.
- **Relationship-based policy:** chủ thể được quyền khi có quan hệ owner/project/tenant phù hợp (nhiều trường hợp cần application-level object authorization).
- **Time-bound/JIT entitlements:** quyền đặc biệt có thời hạn và cần approval nếu policy yêu cầu.

Có thể kết hợp các cách này. Một user trong role FinanceReader vẫn có thể bị từ chối khi thiết bị không đạt posture; một admin có thể phải yêu cầu **step-up MFA** trước khi mở privileged session.

### 10.3. Chính sách mẫu cho ba ứng dụng

| App | Ai được vào? | Điều kiện | Phạm vi thật sự |
| --- | --- | --- | --- |
| **expense-web** | Nhân viên Finance có trạng thái active | SSO + MFA, thiết bị phù hợp | HTTPS app, backend vẫn kiểm tra quyền dữ liệu |
| **support-portal** | Contractor được sponsor cấp trong 30 ngày | MFA, session age, nhóm support-vendor | Chỉ portal, không có route tới DB |
| **admin-ssh** | Admin thuộc nhóm operations, được phê duyệt | Managed device + phishing-resistant MFA + JIT | SSH tới một hostname/server theo phiên |

Mọi ngưỡng như **30 ngày** chỉ là ví dụ. Production policy cần chủ sở hữu, thời hạn entitlement, cách thu hồi, ngoại lệ và các ca kiểm thử.

### 10.4. Policy-as-code dạng ý định

Ví dụ **giả lập, không phải cấu hình chạy trực tiếp của một ZTNA vendor**:

~~~yaml
policy_id: expense-web-access-v1
resource:
  app_id: expense-web
  hostname: expense.app.example
  protocol: HTTPS
  port: 443
subjects:
  must_be_authenticated: true
  group_any_of:
    - finance-readers
    - finance-admins
device:
  require_managed: true
  require_compliant: true
authentication:
  require_mfa: true
session:
  max_age_minutes: 60
  reevaluate_on_risk_event: true
decision_on_unknown_device_state: DENY
default_action: DENY
~~~

Một hệ thống thực có thể biểu diễn các quy tắc này bằng UI, JSON, CEL, Rego, YAML hoặc API riêng. **Policy trên chỉ có ý nghĩa nếu PEP thực sự nhận và thực thi đúng các điều kiện.** Chỉ ghi cấu hình vào Git hoặc console không chứng minh máy khách không thể đi vòng tới origin.

### 10.5. Deny by default phải ở cấp nào?

**Deny by default** có nhiều tầng:

1. **Chưa xác thực:** không tạo phiên đến private application.
2. **Đã xác thực nhưng thiếu entitlement:** từ chối ứng dụng không được cấp.
3. **Đã được cấp ứng dụng:** chỉ những route/port/protocol tương ứng, không mở toàn subnet.
4. **Đã tới backend:** ứng dụng tiếp tục kiểm tra role, tenant, object, CSRF và business rules.
5. **Network:** backend không nhận từ nguồn không phải PEP/gateway hoặc các workloads đã được phép.

Nếu một hệ thống chỉ deny ở tầng 1, nhưng backend có một listener công khai khác, thì **ràng buộc truy cập thất bại** dù dashboard hiển thị ZTNA policy là DENY.

## 11. Bảo vệ origin: Điều kiện bắt buộc để ZTNA có ý nghĩa

### 11.1. Mô hình bypass

~~~mermaid
flowchart LR
    U["Internet client"] --> PEP["ZTNA access gateway"]
    PEP --> APP["Private application / origin"]
    U -. "Direct public IP / alternate DNS / IPv6" .-> APP
    FW["Origin network segmentation"] -. "Block bypass path" .-> APP
    AUTH["App authn/authz"] -. "Verify authorized identity" .-> APP
~~~

Một ứng dụng có thể được công bố qua ZTNA hostname nhưng **origin vẫn reachable** tại public IP, DNS cũ, legacy load balancer, Kubernetes NodePort hoặc management port. Khi đó request có thể tránh broker, MFA/device checks hoặc audit ở PEP.

**Một kiểm thử deny thành công qua gateway không chứng minh origin đã an toàn.** Cần kiểm kê **mọi đường ingress** và kiểm thử âm tính từ nguồn không được phép.

### 11.2. Những biện pháp khóa origin

| Biện pháp | Mục tiêu | Giới hạn/cần lưu ý |
| --- | --- | --- |
| **Private IP/no public route** | Không thể truy cập trực tiếp từ Internet | Peering/VPN/hybrid routes vẫn có thể có |
| **Security group/NSG/firewall** | Chỉ cho PEP/connector hoặc workload được phép tới app port | Cần source identity/ranges đúng, IPv4/IPv6 đầy đủ |
| **Connector outbound only** | Không cần listener inbound từ public edge vào VPC | Connector có thể trở thành bước nhảy nội bộ nếu quá quyền |
| **Mutual TLS tới origin** | Origin xác minh danh tính gateway/connector | Cert trust/rotation/revocation phải đúng |
| **Signed identity assertion / trusted header** | Truyền user context đã được kiểm chứng | Không tin client-supplied header; bảo vệ kênh và audience |
| **Ingress allowlist & host validation** | Chỉ route hợp lệ được nhận | Một mình Host header không đủ để chứng minh nguồn |
| **Kubernetes NetworkPolicy / workload segmentation** | Hạn chế đường pod-to-service ngoài gateway | Cần CNI hỗ trợ, lưu ý hostNetwork/alternate paths |

Với CDN/ZTNA edge cung cấp IP ranges thay đổi, **không hard-code nguồn cũ rồi quên cập nhật**. Một giải pháp có thể sử dụng private connectivity, service identity hoặc API quản lý allowlist có kiểm soát; chọn theo sản phẩm và threat model.

### 11.3. Kẻ tấn công có thể tự đặt proxy identity headers

Ví dụ request **không đáng tin** nếu gửi trực tiếp tới backend:

~~~http
GET /admin HTTP/1.1
Host: expense.app.example
X-Authenticated-User: finance-admin
X-Device-Trusted: true
X-Forwarded-For: 198.51.100.21
~~~

**Các headers trên không chứng minh identity hay posture.** Một client có thể tự tạo giá trị. Backend chỉ được tin các context do **gateway/IdP được xác minh** tạo ra, với đường kết nối và cơ chế bảo vệ phù hợp; ingress cần xóa/ghi đè headers do client tự khai.

**X-Forwarded-For** có thể phục vụ ghi client IP khi trust proxy chain được thiết kế đúng, nhưng **IP không phải user identity**. Không chọn “IP đầu tiên trong XFF” theo một quy tắc mù quáng rồi coi là client thật.

### 11.4. DNS không phải security boundary

Một kiến trúc có thể dùng **split-horizon DNS**, private DNS zones và ZTNA-specific FQDNs để điều hướng client. DNS có ích cho discovery và định tuyến, nhưng:

- Không công bố A/AAAA record **không tự chặn kết nối** nếu địa chỉ và route vẫn tồn tại.
- DNS query có thể đi qua resolver khác hoặc cache.
- Một app có thể có hostname khác, public IP và IPv6 path chưa khóa.
- Service-to-service traffic có thể đi thẳng Pod IP/private IP thay vì hostname.

Phải có **origin network enforcement** và application authorization. **DNSSEC** có thể hỗ trợ xác thực phản hồi DNS theo chain trust thích hợp, nhưng không thay PEP hoặc TLS hostname validation.

### 11.5. Thực thi ở nhiều hop

Khi đường đi là **client → ZTNA edge → cloud LB → ingress controller → app**, phải ghi rõ:

- Hop nào xác thực user/device?
- Hop nào kiểm tra entitlements và thời gian phiên?
- Hop nào kiểm tra HTTP host/path/method?
- Hop nào tạo identity header/assertion?
- Hop nào chặn IP/direct request bypass?
- Hop nào làm TLS termination và backend certificate validation?
- Hop nào ghi 401/403/429/502, hoặc logs bị thiếu?

**Một đường đi có nhiều proxy không đồng nghĩa nhiều tầng xác thực.** Nếu các proxies đều tin header đầu vào từ Internet, chúng có thể lặp lại cùng một sai lầm.

## 12. Bảo mật phiên, cookies và thu hồi quyền

### 12.1. Quyền truy cập có vòng đời

Một application access session thường gồm:

~~~mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> Authenticating: Request protected app
    Authenticating --> Denied: Auth / policy fails
    Authenticating --> Authorized: Verify identity and policy
    Authorized --> Active: Establish scoped connection
    Active --> Reevaluate: Posture/risk/time/role change
    Reevaluate --> Active: Still permitted
    Reevaluate --> Revoked: Policy denies or revokes
    Active --> Expired: Session timeout
    Active --> Ended: Sign out / disconnect
    Denied --> [*]
    Revoked --> [*]
    Expired --> [*]
    Ended --> [*]
~~~

Đây là **mô hình logical state**, không phải mọi sản phẩm đều có đầy đủ các trạng thái và khả năng event-driven revoke. Điều cần đo là **thời gian từ khi policy/user risk đổi đến khi phiên mới và phiên đang mở bị từ chối**.

### 12.2. Session token khác access token

- **Gateway session cookie:** có thể đại diện phiên SSO/authentication tại ZTNA proxy.
- **OAuth access token:** token được client gửi tới resource server theo audience/scope.
- **OIDC ID token:** xác nhận thông tin authentication cho client dự kiến.
- **Application session cookie:** phiên riêng do backend tạo.
- **Device certificate:** ràng buộc thiết bị hoặc workload ở một cơ chế mTLS.

Không tráo đổi những dữ liệu này vì cùng “chứng minh đăng nhập”. Chúng có **audience, thời hạn, issuer, revocation semantics và mục đích khác nhau**.

### 12.3. Cookie và redirect security

Nếu PEP sử dụng cookie trong browser:

- Dùng **Secure, HttpOnly, SameSite** thích hợp với ứng dụng/SSO flow.
- Giới hạn **Domain/Path** để cookie không lan sang subdomain không được tin.
- Chống **CSRF**, session fixation, open redirect và login CSRF theo flow.
- Xác minh state/nonce/PKCE/redirect URI theo giao thức đăng nhập.
- Không đặt token bí mật vào URL query string hoặc log mặc định.
- Kiểm tra session expiry/logout, đặc biệt ở iframe, SPA và nhiều domains.

**SameSite không thay CSRF protection** trong mọi trường hợp. Một ZTNA session cookie mạnh vẫn có thể bị lạm dụng nếu ứng dụng có XSS, lộ cookie hoặc cross-origin flow bị cấu hình sai.

### 12.4. Mất thiết bị và khóa tài khoản

Kịch bản: laptop bị đánh cắp khi có một phiên ZTNA đang mở. Runbook phải trả lời:

1. Khóa hoặc vô hiệu hóa user/device identity ở đâu?
2. Có thu hồi gateway session ngay không, hay chờ hết TTL?
3. Các **TCP/SSH/RDP sessions đang mở** có bị ngắt không?
4. App backend có còn session/token riêng chưa được revoke không?
5. Có thiết bị thứ hai cùng user đang hợp lệ cần giữ hoạt động không?
6. Có đủ log để xác định các app đã được truy cập trước khi revoke?

**Đăng xuất IdP không chắc ngắt ngay mọi session phía application.** Phải hiểu session propagation, back-channel logout nếu hỗ trợ và khả năng revoke của từng PEP/app.

### 12.5. Idle timeout, absolute lifetime và step-up

| Cơ chế | Mục tiêu | Lưu ý |
| --- | --- | --- |
| **Idle timeout** | Giới hạn phiên không hoạt động | WebSocket/gRPC keepalives có thể tác động định nghĩa idle |
| **Absolute session lifetime** | Giới hạn tuổi phiên dù có hoạt động | Không thay risk-triggered revoke |
| **Step-up MFA** | Tăng assurance trước thao tác nhạy cảm | Phải ràng buộc với hành động/phiên đúng |
| **JIT access** | Chỉ cấp quyền khi có nhu cầu, hết hạn tự động | Cần approval/expiration đồng bộ |
| **Risk-based revoke** | Chấm dứt khi account/device có tín hiệu nguy hiểm | Signal delay, false positives, open connections |

Con số timeout cần dựa vào dữ liệu hợp lệ và rủi ro ứng dụng. **Một phiên admin 8 giờ** và **phiên đọc thông tin công khai 8 giờ** không có cùng hệ quả.

## 13. TLS, mTLS và xác thực đầu cuối

### 13.1. Hai chặng mã hóa khi dùng proxy

~~~mermaid
flowchart LR
    C["Browser / agent"] -->|"TLS #1<br/>verify app hostname"| G["ZTNA gateway"]
    G -->|"TLS #2<br/>verify origin identity"| A["Private application"]
    CA["PKI/Trust policy"] -. "Trust + rotation" .-> G
    CA -. "Trust + rotation" .-> A
~~~

Nếu ZTNA proxy terminate TLS từ browser rồi chuyển **HTTP plaintext** tới backend, không được mô tả rằng dữ liệu được mã hóa **trong cả hai chặng**. Nếu gateway kết nối HTTPS backend nhưng **không xác minh SAN/hostname/trust chain**, kênh có thể được mã hóa mà **backend identity không được đảm bảo theo yêu cầu**.

### 13.2. mTLS cho connector/backend

Một kết nối **mTLS** giữa connector/gateway và origin có thể chứng minh danh tính của hai đầu kết nối khi PKI và certificate validation đúng. Cần quản lý:

- CA trust, certificate issuing policies và SAN/identity mapping.
- Private key storage, rotation, expiry và revocation semantics.
- Phân quyền **connector nào được kết nối app nào**, không chỉ tin mọi cert do một CA cấp.
- Fail-closed behavior khi certificate sai.
- Monitoring handshake failures và certificate expiry.

**mTLS xác thực workload/connector**, không tự chứng minh người dùng cuối được phép xem một bản ghi cụ thể. End-user identity propagation và backend authorization vẫn phải được thiết kế.

### 13.3. TLS passthrough hay terminate?

| Kiểu | Lợi ích | Đánh đổi |
| --- | --- | --- |
| **TLS terminated tại gateway** | Có thể áp SSO/L7 policy, route HTTP, log status | Gateway nhìn payload; phải bảo vệ logs/secrets và backend hop |
| **TLS re-encrypted tới app** | Bảo vệ cả hai đường truyền, vẫn có L7 ở gateway | Cần backend certificate validation |
| **TLS passthrough** | Backend giữ keys/giải mã | Gateway không tự hiểu HTTP path/body; enforcement hẹp hơn |

Không giả định gateway có thể làm **full HTTP request inspection** khi dữ liệu đi passthrough. Cần chọn vị trí PEP phù hợp với **mức policy hạt** mong muốn.

## 14. Truy cập ứng dụng không phải HTTP: SSH, RDP, database

### 14.1. SSH theo host, principal và thời gian

Một mô hình truy cập SSH có thể yêu cầu:

~~~text
Subject:
  admin-user-17, active, privileged entitlement
Device:
  managed + compliant
Target:
  jump-host-01.internal.example TCP/22
Conditions:
  JIT approval, MFA, 30-minute window
Decision:
  Allow SSH session through approved gateway
Denied:
  Other hosts, DB ports, arbitrary subnet routes
~~~

Phạm vi mạng được thu hẹp tới một target:22, nhưng SSH server vẫn phải kiểm tra **host identity, user public-key/certificate, OS account permissions, sudo authorization** và log admin actions theo policy. ZTNA là **một lớp trước SSH**, không thay SSH host key validation.

### 14.2. RDP và remote desktop

Remote desktop có thể cần gateway chuyên biệt để hỗ trợ **RDP TCP/UDP, clipboard, file redirection, audio/video và session controls**. Một web-only ZTNA proxy không mặc nhiên hỗ trợ đầy đủ.

Một chính sách có thể cấp quyền tới **một máy desktop được quản lý**, không cấp quyền tới subnet Windows. Nhưng bên trong desktop, OS authentication, local privilege, disk redirection và khả năng truy cập các systems khác vẫn cần kiểm soát để tránh **pivoting**.

### 14.3. Database clients

Database client có thể dùng TCP tới một endpoint riêng. ZTNA có thể hạn chế **ai được mở kết nối tới DB proxy/host**, nhưng:

- DB vẫn cần **DB authentication và RBAC** trên schema/table/row.
- TLS DB server certificate nên được kiểm tra.
- Query timeout, connection pool, quotas và audit vẫn cần.
- Việc cho TCP/5432 chưa đồng nghĩa user được đọc mọi bảng.
- Shared service accounts có thể làm mất khả năng quy kết user nếu không có identity propagation.

### 14.4. Legacy applications nhiều port hoặc discovery

Ứng dụng cũ có thể dùng dynamic port ranges, broadcast/multicast, callbacks hoặc peer-to-peer connections. Nếu product không hỗ trợ đầy đủ, đừng cấu hình “application = toàn CIDR” rồi nói vẫn là least privilege.

Hãy phân tích dependency map, lựa chọn **protocol-aware proxy** hoặc segmented VPN/VLAN với ACL hẹp nếu chưa thể tách, kèm kế hoạch giảm phạm vi về lâu dài.

### 14.5. Long-lived sessions và stream

WebSocket, HTTP/2 streams, gRPC, SSH và RDP có thể giữ kết nối kéo dài sau lúc được cấp. Các câu hỏi cần test:

- Khi user bị revoke, **kết nối cũ** có bị đóng không?
- Khi device posture đổi, PEP có chặn **new streams** trong cùng connection không?
- Khi connector mất mạng, session được fail closed hay reconnect?
- Có timeout/keepalive và drain behavior rõ ràng không?
- App có thể tự mở kết nối phụ bypass gateway không?

Một test chỉ kiểm tra **login mới bị deny** chưa đủ để khẳng định toàn bộ phiên đang hoạt động đã bị thu hồi.

## 15. Workload-to-workload: Application access không chỉ dành cho nhân viên

### 15.1. Danh tính dịch vụ thay cho địa chỉ mạng

Trong microservices/Kubernetes/multi-cloud, hai dịch vụ có thể nằm cùng VPC nhưng không nên vì thế mà mặc nhiên tin nhau. Một policy có thể nêu:

~~~text
Principal:
  service identity = orders-api in production

Destination:
  inventory-api, operation read-stock

Conditions:
  valid workload certificate
  authorized identity and environment

Denied:
  write-stock, admin operations, unrelated services
~~~

Điều này cụ thể hơn **allow subnet 10.40.0.0/16 → TCP/443**. Workload identity có thể được gắn bằng **mTLS, SPIFFE/SPIRE theo triển khai, cloud workload identity hoặc service account tokens đã được kiểm chứng**. Không mặc định tất cả Kubernetes service accounts tự có SPIFFE identity hoặc mesh authorization.

### 15.2. Mesh policy và application API authorization

Một service mesh có thể kiểm tra peer workload identity và cho phép kết nối **orders → inventory**, nhưng nếu mọi request GET/POST tới inventory đều được phép, một lỗi application authorization vẫn có thể làm lộ dữ liệu tenant.

Các lớp:

1. **CNI NetworkPolicy:** workload nào có thể mở kết nối tới IP/cổng.
2. **mTLS/workload PEP:** peer identity nào có quyền sử dụng service.
3. **L7 gateway/mesh:** method/path/route được phép nếu hỗ trợ.
4. **Application authorization:** order/customer/tenant được phép truy cập dữ liệu nào.

Không đếm bốn tầng là bốn lần xác thực user nếu tất cả chỉ kiểm tra cùng một điều kiện; mỗi tầng phải có **trách nhiệm và bằng chứng** riêng.

### 15.3. Workload identity cần có vòng đời

Khi Pod được tái tạo, certificate/key/token phải được cấp lại hoặc xoay vòng đúng. Không nhúng API keys dài hạn vào image hoặc giữ một tài khoản DB dùng chung cho mọi deployment không có audit.

Các yêu cầu thường gồm:

- Identity issuance chỉ từ control plane được tin và workload đúng namespace/service account.
- Certificate/JWT **audience, issuer, TTL và scope** theo dịch vụ.
- Hạn chế đọc keys/secrets, bảo vệ node/container runtime.
- Revocation/rotation và deny khi identity không còn hợp lệ.
- Quan sát kết nối theo **workload identity + thời điểm + môi trường**, không chỉ Pod IP.

### 15.4. Third-party B2B/API access

Một đối tác có thể truy cập một API cụ thể bằng **OAuth client credentials, mTLS-bound client identity hoặc API credential** theo hợp đồng. Quyết định access phải bao gồm:

- Partner/client identity đã xác thực.
- API product, scope, tenant và các operation được phép.
- Thời hạn hợp đồng hoặc entitlement.
- Rate limit/quota/cost budget và hành vi khi vượt (ví dụ HTTP 429).
- Logs và cơ chế revoke khi đối tác chấm dứt hợp đồng.

ZTNA có thể bảo vệ network entrypoint, nhưng **API authorization, token audience và tenant isolation** vẫn phải kiểm tra trong gateway và backend. Không tự tin client_id tự khai hoặc tenant header do đối tác gửi.

## 16. Threat modeling: Các đường vượt ranh giới ứng dụng

### 16.1. Tài sản và tác nhân

**Tài sản cần bảo vệ:** ứng dụng nội bộ, backend APIs, admin endpoints, databases, connector credentials, user sessions, gateway policies, IdP, device posture signals và audit logs.

**Tác nhân/rủi ro có thể gặp:** tài khoản bị phishing, browser/session token bị đánh cắp, endpoint bị compromise, contractor giữ quyền quá hạn, connector bị chiếm, nhân viên có quyền vượt nhu cầu, ứng dụng có lỗi authorization, policy IAM bị sửa ngoài quy trình hoặc direct-origin bypass.

### 16.2. Ma trận kịch bản

| Kịch bản | Vì sao vẫn xảy ra khi có ZTNA? | Biện pháp phòng vệ |
| --- | --- | --- |
| **Direct-origin bypass** | Public IP/NodePort/legacy hostname còn mở | Private origin, SG/NSG/NetworkPolicy, gateway-only mTLS |
| **Header spoofing** | Backend tin X-User-ID/X-Device-Trusted tự khai | Strip/overwrite, signed context, mTLS, app validation |
| **Stolen session cookie** | User đã xác thực trước khi token/cookie bị lộ | Cookie hardening, session binding nếu hỗ trợ, short TTL, anomaly/revoke |
| **Compromised managed device** | Posture healthy không chứng minh OS sạch | EDR response, least privilege, session controls, behavior monitoring |
| **Over-broad app policy** | Group/role chọn quá rộng hoặc wildcard route | Least privilege, policy-as-code, negative testing |
| **Stale entitlement** | Contractor nghỉ việc nhưng group/quyền chưa thu hồi | JML lifecycle, expiry, periodic access review |
| **IdP misconfiguration** | Token sai audience/issuer vẫn được tin | Validate protocol/token, issuer pinning, secure redirect |
| **Connector pivot** | Connector có quyền tới cả subnet private | Egress allowlist, connector isolation, workload IAM |
| **PEP bypass qua alternate ingress** | App có hai LB/ingress paths | Inventory, consistent enforcement, network deny |
| **Role/group escalation** | Identity store group tự đổi hoặc provisioning sai | Entitlement governance, privileged change audit |
| **Long-lived session after revoke** | PEP chỉ kiểm tra ở login | Session re-evaluation, forced disconnect tests |
| **BOLA/IDOR trong ứng dụng** | Gateway cho user vào app nhưng backend không kiểm tra object | Application authorization, resource ownership tests |
| **Browser download/exfil** | User được vào app và lấy dữ liệu hợp lệ/quá rộng | App data authorization, DLP nếu phù hợp, logging |
| **HTTP request smuggling/confusion** | Các proxies parse HTTP khác nhau | Protocol validation, patching, reject ambiguous framing |
| **DDoS vào public PEP** | Edge vẫn là Internet-facing | Upstream DDoS/WAF/rate limits/capacity |
| **Outage của IdP/broker** | Truy cập có thể không cấp mới được | HA, dependency runbook, policy fallbacks và emergency access |

**Không có biện pháp đơn lẻ loại bỏ mọi rủi ro.** ZTNA giảm bề mặt kết nối và cải thiện quyết định truy cập, nhưng phải kết hợp endpoint hardening, application security, network segmentation, identity governance và giám sát.

### 16.3. Control plane có thể là mục tiêu đặc biệt

Kẻ có quyền sửa **application definitions, connector targets, access policy, groups hoặc certificate trust** có thể chuyển traffic sang origin khác, nới allow, thêm admin hoặc tạo đường egress không phù hợp.

Kiểm soát:

- Least-privilege IAM và role tách biệt tạo ứng dụng, duyệt chính sách, quản trị connectors.
- MFA mạnh cho control plane và JIT/PAM khi cần.
- Change approvals, policy versioning, signed/reviewed IaC, drift alerts.
- Audit hành động sửa/xóa policy hoặc connector, lưu trong hệ thống không cùng quyền với editor.
- Kiểm tra cấu hình multi-region/multi-tenant đồng nhất; đặc biệt đường khôi phục.

**Một public web gateway đã khóa origin không đủ nếu người không có quyền vẫn có thể đổi target app trong console.**

### 16.4. Gateway là nơi tập trung dữ liệu nhạy cảm

Identity-aware proxy có thể thấy URL/path, login context, HTTP headers hoặc response metadata. Nếu terminate TLS, proxy có thể có khả năng đọc plaintext của request/response; rủi ro về **secret, cookie, PII và compliance** cần được xem xét.

- Không ghi **Authorization headers, cookies, access tokens, passwords, request bodies** vào log mặc định.
- Bảo vệ credentials/key material và quyền sửa log pipeline.
- Phân vùng dữ liệu giữa tenant/customer nếu gateway phục vụ multi-tenant.
- Giới hạn retention, encrypt logs, RBAC và audit đọc.
- Đánh giá vendor/shared responsibility và vị trí dữ liệu theo hợp đồng.

## 17. Access graph: Thiết kế quyền từ nhu cầu nghiệp vụ

### 17.1. Xây inventory ứng dụng trước khi đổi VPN

Không thể cấp “theo ứng dụng” nếu chưa biết **ứng dụng gồm những service, hostname, ports, callback và dependencies nào**. Một inventory phù hợp có thể gồm:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| App ID/owner | expense-web / Finance IT | Trách nhiệm nghiệp vụ |
| Frontend hostname | expense.app.example | Identity/certificate/routing |
| Origin address | private expense service | Bảo vệ direct access |
| Protocol | HTTPS/443 | Chọn PEP compatible |
| User groups/roles | finance-reader/admin | Chính sách entitlement |
| Device requirements | managed + compliant | Posture |
| App sensitivity | internal/confidential | Rủi ro/assurance |
| Dependencies | SSO, API, DB, file upload | Thiết kế traffic và không mở thừa |
| Access pattern | Browser + SPA + WebSocket | Kiểm thử giao thức |
| Allowed egress | Auth/API/telemetry endpoints | Network segmentation |
| Logging/audit | Request ID, user ID, target | Điều tra |
| Break-glass path | Privileged emergency runbook | Availability và audit |

**Một DNS hostname không luôn bằng một ứng dụng.** Ứng dụng có thể phụ thuộc API calls sang nhiều origins, third-party IdP hoặc WebSocket endpoint. Một policy chỉ mở landing page có thể khiến trang đăng nhập thành công nhưng chức năng nghiệp vụ lỗi.

### 17.2. Từ ACL mạng sang bảng quyền ứng dụng

**Mô hình cũ:** user group Finance có route qua VPN tới **10.20.0.0/16** rồi ACL cho TCP/443.

**Mô hình mục tiêu** (giả lập):

| Principal/nhóm | Ứng dụng | Giao thức | Điều kiện | Quyền |
| --- | --- | --- | --- | --- |
| Finance employee | expense-web | HTTPS/443 | SSO/MFA + compliant device | Access app |
| Finance manager | expense-approval | HTTPS/443 | Step-up MFA/JIT cho bước duyệt | Access app, app quyết định approve rights |
| Vendor support | ticket-portal | HTTPS/443 | Sponsor + MFA + expiry | Support portal only |
| Operations admin | jump-host-01 | SSH/22 | Managed workstation + PAM approval | Time-bound admin session |
| Unknown/disabled user | Any private app | Any | Không hợp lệ | Deny |

Hệ thống mới không tự cấp IP route đến tất cả backend. Network firewall tiếp tục hạn chế connector/PEP chỉ tới **đích cần thiết**, và từng ứng dụng duy trì authorization riêng.

### 17.3. Nghĩ theo người truy cập tài nguyên, không theo subnet

Một ma trận quyền theo ứng dụng nên trả lời:

1. Ai là **chủ thể có quyền** và nguồn entitlement?
2. Ứng dụng nào thực sự cần, ở environment nào?
3. Session/method nào được phép, có cần JIT không?
4. Điều kiện device/risk/MFA?
5. Những resources nào **không được** truy cập, dù cùng subnet/cluster?
6. Ứng dụng nào phải truy cập thông qua một proxy/connector riêng?
7. Cách kiểm chứng quyền bị thu hồi khi đổi group, nghỉ việc hoặc mất thiết bị?

**Một policy tốt phải có cả yêu cầu allow và deny rõ ràng.** Chỉ liệt kê app được vào chưa đủ để kiểm chứng việc user không có route tới các apps khác.

## 18. So sánh khi chuyển từ VPN tới ZTNA

### 18.1. So sánh theo tiêu chí kỹ thuật

| Tiêu chí | VPN truy cập mạng | ZTNA theo ứng dụng |
| --- | --- | --- |
| **Đơn vị cấp quyền phổ biến** | Tunnel/route, subnet, host:port ACL | App/resource/session, đôi khi host:port hoặc HTTP route |
| **Tín hiệu identity** | VPN user/cert/IdP theo thiết kế | User/device/workload/app context tại PEP |
| **Lộ topology** | Phụ thuộc routes/segmentation được cấp | Có thể giảm thông tin về mạng riêng nếu origin bị khóa |
| **Giao thức** | Linh hoạt cho IP traffic theo VPN type | Tùy proxy/agent/protocol support |
| **Third-party access** | Cần VPN client/tunnel + ACL | Có thể chỉ cấp một app/browser session |
| **Network enforcement** | Firewall, ACL, segmentation | Vẫn cần firewall/connector isolation |
| **Application authorization** | Backend tự thực hiện | Backend vẫn tự thực hiện |
| **Session revocation** | Ngắt tunnel/ACL cập nhật theo khả năng | Ngắt app session/PEP theo khả năng; phải test |
| **Observability** | Flows/tunnels, VPN account, network logs | App/identity/session logs; vẫn cần flows |
| **Legacy support** | Thường thuận tiện cho non-HTTP và nhiều ports | Có thể cần agent/proxy chuyên dụng |
| **Operational dependence** | VPN concentrator, routing, IdP | PEP/connector, identity, posture, control plane |
| **User experience** | Đăng nhập tunnel và truy cập route | Có thể browser SSO hoặc agent-based |

**Không dùng bảng này để tuyên bố ZTNA mặc định bảo mật hơn mọi VPN.** Kết quả phụ thuộc **network access scope, policy quality, client/connector hardening, origin lockdown, app authorization, HA và monitoring**.

### 18.2. Khi ZTNA có lợi ích rõ

Điển hình:

- Contractor chỉ cần **một internal web portal**.
- Đội hỗ trợ remote cần truy cập một **quản trị app theo thời hạn**.
- Nhân viên làm việc từ nhiều mạng, không cần route tới các subnet nội bộ.
- Doanh nghiệp muốn giảm **lateral reachability** của endpoint sau khi credential bị lộ.
- Nhiều apps cloud/on-prem nhưng người dùng chỉ nên thấy danh mục apps đã cấp quyền.

### 18.3. Khi không nên vội thay

Một ứng dụng legacy dùng hàng chục dynamic ports, UDP discovery và callbacks có thể cần **network-level connectivity**. Nếu platform chỉ hỗ trợ HTTPS proxy, chuyển sang ZTNA bằng cách mở một **CIDR rộng qua agent** có thể không cải thiện nhiều so với VPN segmented.

Cần tính **độ phức tạp tích hợp, chi phí, latency, availability, lỗi DNS/tunnel, nhu cầu offline và khả năng hỗ trợ** trước khi chọn đường đi.

### 18.4. Phương án kết hợp

Một kiến trúc thực tế có thể dùng:

- ZTNA browser gateway cho **web applications**.
- Agent-based scoped access cho **SSH/RDP/internal TCP services**.
- Segmented VPN cho **legacy operations** còn cần network reachability.
- Site-to-site VPN/private links cho **cloud/hybrid infrastructure**.
- Service mesh/mTLS cho **workload-to-workload**.
- Firewall/NetworkPolicy ở origin và app authorization ở backend.

Đây là **phân chia theo use case**, không yêu cầu một sản phẩm duy nhất phải làm tất cả.

## 19. Quy trình chuyển một ứng dụng từ network-level sang application-level

### Bước 1 — Chọn ứng dụng thí điểm

Ưu tiên một **web application rõ owner**, giao thức tiêu chuẩn, quy mô người dùng vừa phải và có khả năng rollback. Tránh chọn ngay hệ thống quản trị tối quan trọng hoặc app legacy phức tạp nhiều ports nếu chưa có dependency map.

Xác định **baseline**: user groups, số phiên đồng thời, p95/p99 latency, error rates, tính năng upload/download/WebSocket, SSO integrations, dependency inventory và nơi lưu log.

### Bước 2 — Vẽ topology trước/sau

~~~mermaid
flowchart TB
    subgraph OLD["Trước: network-level"]
      U1["User laptop"] --> VPN["VPN"]
      VPN --> SUBNET["Internal subnet reachability"]
      SUBNET --> APP1["Expense app"]
      SUBNET -. "Có thể reachable tùy ACL" .-> OTHER1["Other private services"]
    end
    subgraph NEW["Sau: app-level"]
      U2["User/device"] --> PEPP["ZTNA PEP + policy"]
      PEPP --> CONN["Scoped connector"]
      CONN --> APP2["Expense app"]
      NET["SG / firewall"] -. "Origin only from connector" .-> APP2
      PEPP -. "No shared network route" .-> OTHER2["Other private services"]
    end
~~~

Trong sơ đồ, “sau” phải được xác minh bằng **network deny paths**. Nếu thiết bị vẫn có VPN route đến origin hoặc backend còn public, chỉ thêm PEP vào luồng mới **chưa hẳn thay thế quyền cấp mạng rộng**.

### Bước 3 — Thiết kế policy và entitlement

Ghi:

- Application ID, hostname, protocol/port và backend target.
- User/partner/workload group được quyền.
- Device compliance/MFA/risk conditions.
- Session duration, step-up và revoke.
- Access logs cần có và retention.
- Owner, reviewer, change window và rollback criterion.

Định nghĩa **negative test cases**: user ngoài nhóm, device unmanaged, user disabled, app khác cùng subnet, wrong Host header, direct origin IP, token không hợp lệ, session hết hạn.

### Bước 4 — Chuẩn bị origin và connector

Đặt origin trong vùng phù hợp, chỉ cho **connector/gateway → app:port**, đóng public path và các alternate listeners không cần thiết. Chưa cắt VPN cũ cho đến khi test chức năng, người dùng và break-glass theo kế hoạch.

Nếu dùng outbound connector, hạn chế **egress từ connector tới app cụ thể**, bảo vệ connector identity/updates và có HA nếu ứng dụng yêu cầu. **Đừng đặt một connector với quyền toàn VPC** chỉ vì cấu hình dễ.

### Bước 5 — Tích hợp SSO/MFA và xác minh identity

Kiểm tra **IdP app registration, redirect URIs, token issuer/audience, signing keys, group membership, SCIM/JML provisioning, session/logout** theo profile. Không dùng ID token như access token sai audience; không tin user headers từ Internet.

### Bước 6 — Chạy pilot song song

Cho một nhóm nhỏ dùng app qua ZTNA, vẫn giữ đường cũ cho **người được phép** theo change plan. Tránh tạo chính sách làm cả hai đường tự do cùng mở: phải biết **ai đang dùng ZTNA, ai đang dùng VPN**, và có log tương ứng.

Test chức năng theo **real workflow**, không chỉ login:

- Login/logout, deep links và bookmarks.
- SPA/API calls, CORS, authentication callbacks.
- File upload/download và giới hạn kích thước.
- WebSocket/gRPC/streaming nếu có.
- Background requests, refresh token/session expiry.
- Mobile/BYOD và contractors nếu scope có.
- Failure/rollback khi IdP, connector hoặc app không sẵn sàng.

### Bước 7 — Đóng quyền VPN rộng

Sau khi pilot đạt yêu cầu, giảm dần ACL/routes cũ cho nhóm dùng ZTNA; có thể giữ VPN cho service legacy khác. Kiểm tra **không còn kết nối thẳng tới origin** từ endpoint đã chuyển, kể cả IPv6, VPN route cache, peering và DNS cũ.

**Không đồng nhất “user không biết IP” với “user không thể kết nối IP”.** Phải có bằng chứng deny tại đúng firewall/network enforcement point.

### Bước 8 — Vận hành và access review

Thiết lập:

- Periodic entitlement reviews, contractor expiry và JML.
- Logs/alerts khi group/app policy/connector thay đổi.
- Posture signal health, authentication failures, step-up events.
- Session revocation drill và connector HA drills.
- Regression tests sau cập nhật gateway/IdP/app/cert/DNS.
- SLO, capacity, cost và privacy review.

### Bước 9 — Nghiệm thu dựa trên điều kiện đo được

Một migration **chưa hoàn thành** nếu chỉ có màn hình login mới. Phải chứng minh **đúng identity được vào đúng app, sai identity bị chặn, không còn đường mạng rộng, backend authorization không bị bypass, và dịch vụ có thể phục hồi khi control plane/connector lỗi**.

## 20. Availability và các tình huống phụ thuộc hạ tầng

### 20.1. ZTNA tạo thêm dependency

Luồng truy cập app có thể phụ thuộc:

~~~text
Client DNS / local agent
  -> Public edge / PEP
  -> IdP / MFA service
  -> Policy decision / posture source
  -> ZTNA data plane
  -> Private connector / tunnel
  -> Origin TLS / authentication
  -> Application / database
~~~

Sự cố ở một khâu có thể làm người dùng mất quyền truy cập dù ứng dụng vẫn khỏe. Cần theo dõi riêng **authentication errors, policy decision latency, connector health, TLS errors, backend connection rate và app status**.

### 20.2. Fail-closed và fail-open không đơn giản

| Khi mất dependency | Lựa chọn an toàn khả dụng | Đánh đổi |
| --- | --- | --- |
| **IdP unavailable** | Không cấp phiên mới, có thể giữ phiên đã xác minh trong giới hạn | Availability giảm; cần kiểm tra tuổi phiên |
| **Policy engine unavailable** | Từ chối quyền mới hoặc dùng cached signed decision có TTL nếu policy cho phép | Cached policy có thể stale |
| **Posture source unavailable** | Deny privileged apps; app ít nhạy cảm có thể có fallback đã định | Cần phân biệt unknown với compliant |
| **Connector unavailable** | Reroute sang connector HA được phép | Mất HA có thể khiến app không truy cập |
| **Control plane unreachable** | Data plane có thể giữ các phiên đã cấp theo semantics product | Thu hồi quyền có thể chậm |
| **Origin unavailable** | Trả lỗi backend đúng, không mở đường bypass | Không “tạm mở public origin” thiếu kiểm soát |

**Fail-open** trên application access có thể cho phép một user không được phép vào ứng dụng; đó là quyết định rủi ro nghiêm trọng. Nếu cần emergency access, ưu tiên **đường break-glass riêng, có authentication mạnh, giới hạn thời gian, phê duyệt và audit**, không biến policy default thành allow all.

### 20.3. Connector HA và vùng triển khai

Một private connector có thể là **single point of failure**. Khi cần HA:

- Dùng nhiều connector instances theo khả năng nền tảng.
- Kiểm tra selection/failover, trạng thái phiên, cùng target policies.
- Xác minh không có connector mới với SG quá rộng.
- Kiểm soát certificates/secret rotation và network egress.
- Kiểm thử **rolling restart, node/AZ outage, provider reconnect**.
- Có metrics cho queue, active connections, target errors và connector memory/CPU.

**Hai connector đặt trong cùng một máy/zone không tự là HA đa vùng**. Phải phân tích blast radius của compute, network, DNS, identity và backend.

### 20.4. Latency và trải nghiệm người dùng

Chuyển traffic qua proxy có thể tăng round trips hoặc đường đi xa hơn. Đánh giá:

| Chỉ số | Cần đo |
| --- | --- |
| **Time to first authorized app response** | DNS, IdP redirect, policy check, connector |
| **SSO/MFA completion time** | Người dùng có gặp quá nhiều prompts? |
| **PEP processing latency** | Policy/auth middleware và reverse proxy overhead |
| **Backend latency** | Origin thực xử lý chậm hay gateway? |
| **Streaming/long-lived health** | WebSocket/gRPC disconnects, keepalive, idle timeout |
| **Upload/download throughput** | Body limits, proxy buffers, DLP inspection |
| **Availability/SLO** | App reachable theo nhóm, device và region |
| **Client resource use** | Agent CPU, network battery, roaming effects |

Không kết luận ZTNA “chậm hơn VPN” chỉ từ một phép thử trên một mạng. So sánh **cùng app, cùng region, cùng workflow và mô hình bảo mật tương đương**, đo distribution thay vì một lần ping.

### 20.5. Break-glass

Một phương án emergency cho **IdP outage hoặc admin access recovery** phải:

1. Có owner và phạm vi ứng dụng/host cụ thể.
2. Có authentication mạnh bằng đường độc lập đủ an toàn.
3. Giới hạn entitlement, thời gian, logging và người phê duyệt.
4. Không công bố quyền truy cập rộng toàn subnet ngoài thiết kế.
5. Được luyện tập định kỳ trong lab, có kiểm chứng revoke sau sự cố.

**Break-glass là phương án khôi phục được kiểm soát**, không phải một tài khoản super-admin vĩnh viễn bỏ MFA.

## 21. Observability: Đo chính sách, phiên và đường đi

### 21.1. Những tầng log cần tương quan

~~~mermaid
flowchart TD
    IDP["IdP / MFA login events"] --> JOIN["Correlation + identity mapping"]
    POSTURE["Device posture / MDM / EDR"] --> JOIN
    POLICY["Policy decision + entitlement changes"] --> JOIN
    PEP["Gateway / connector session logs"] --> JOIN
    FW["Origin network deny / allow flows"] --> JOIN
    APP["App authentication / authorization logs"] --> JOIN
    JOIN --> SIEM["SIEM / investigation / alerts"]
    JOIN --> METRIC["Availability + policy metrics"]
~~~

Một sự kiện “access permit” ở PEP không tự chứng minh backend phục vụ thành công; một application HTTP 403 có thể cho thấy app authorization đã chặn request **sau khi** gateway cấp phiên. Cần correlation theo request/session IDs, timestamp và trusted identity.

### 21.2. Event fields nên có

| Trường | Dùng để | Lưu ý bảo mật |
| --- | --- | --- |
| **event_time_utc / ingest_time** | Dựng timeline và đo trễ log | Đồng bộ time |
| **application_id / resource_id** | Định danh app, đích và policy | Không công bố mapping nhạy cảm cho client |
| **subject_ref / principal_type** | Liên hệ user/partner/workload | Có thể dùng pseudonymized ID |
| **device_ref / posture_state** | Kiểm tra điều kiện device | Không log toàn bộ dữ liệu endpoint |
| **policy_id / revision** | Truy vết chính sách đang áp | Cần audit mọi lần sửa |
| **decision / reason** | PERMIT, DENY, STEP_UP, REVOKE | Phân biệt auth fail với policy deny |
| **session_id / request_id** | Liên kết các hops | Không dùng session secret làm log ID |
| **PEP_id / connector_id / region** | Khoanh vùng lỗi HA | Không làm lộ nội bộ ra response |
| **backend_target / protocol/port** | Xác minh đúng app target | Dữ liệu nhạy cảm nội bộ |
| **session_start/end/revocation cause** | Đo thời hạn/thu hồi | Không log raw tokens |
| **latency / bytes / status** | Performance và lỗi | Không coi bytes là chứng minh exfil |
| **sensor_health / logging_failure** | Kiểm tra coverage | Missing data phải thể hiện rõ |

### 21.3. Log giả lập

~~~json
{
  "event_time_utc": "2026-11-28T07:30:00Z",
  "app_id": "expense-web-lab",
  "session_ref": "session-anonymized-1042",
  "subject_ref": "user-anonymized-17",
  "device_ref": "device-anonymized-08",
  "posture": "compliant",
  "auth_assurance": "mfa",
  "policy_id": "expense-web-access-v1",
  "policy_revision": "rev-17",
  "decision": "PERMIT",
  "gateway_ref": "ztna-edge-lab-a",
  "connector_ref": "connector-lab-01",
  "target_ref": "expense-origin-01",
  "protocol": "HTTPS",
  "backend_result": 200
}
~~~

Đây là **schema giả định cho mục đích học tập**, không phải định dạng chuẩn của một vendor. User/device refs đã ẩn danh; không lưu access token, cookies hoặc API secrets.

### 21.4. Metrics có ích

| Metric | Ý nghĩa | Cách tránh suy diễn sai |
| --- | --- | --- |
| **Permits/denials theo app/policy** | Policy tác động tới user/apps nào | Deny không tự là tấn công |
| **SSO/MFA error rate** | IdP hoặc UX đang lỗi? | User deny và IdP outage khác nhau |
| **Posture failure rate** | Devices không đạt điều kiện | Agent outage có thể gây false positives |
| **Active/revoked session count** | Policy lifecycle | Session revoked ở PEP khác app session |
| **Revocation propagation latency** | Quyền được thu hồi nhanh tới đâu | Đo cả long-lived connections |
| **Connector health/queue/errors** | Điểm nghẽn private access | Một connector healthy chưa chắc app reachable |
| **Origin direct access deny events** | Kiểm tra đường bypass | Cần phân biệt authorized admin paths |
| **Backend 4xx/5xx và p95 latency** | App có hoạt động sau PEP? | 403 app không nhất thiết lỗi ZTNA |
| **Policy changes/drift** | Có ai nới scope/group/target? | Phân biệt approved vs out-of-band |
| **Access reviews và expired entitlements** | Quyền cũ đã được thu hồi? | Phải xác nhận backend session/credentials |

**Không gắn mỗi user/device ID thành metric label không giới hạn** ở hệ thống time-series. Dùng thống kê theo app/policy/team, logs có RBAC để điều tra chi tiết và retention theo nhu cầu.

### 21.5. Các cảnh báo an ninh đáng xem

- Một user truy cập **nhiều private apps nhạy cảm mới** ngoài entitlement baseline.
- Nhiều lần deny/step-up fail hoặc dấu hiệu đăng nhập bất thường.
- Device trở thành noncompliant nhưng session vẫn được sử dụng quá giới hạn cho phép.
- Application policy hoặc connector target bị thay **ngoài approved change**.
- Một app origin nhận direct connection từ nguồn không phải PEP.
- Session của tài khoản đã disabled vẫn hoạt động sau thời hạn revoke kỳ vọng.
- Connector đột nhiên thiết lập connections đến đích ngoài danh sách.
- Logging pipeline mất dữ liệu đúng lúc gateway/IdP có lỗi hoặc thay policy.

**Tín hiệu đơn lẻ không là bằng chứng compromise.** Ví dụ user truy cập app mới có thể do onboarding được phê duyệt; cần đối chiếu identity governance, ticket, device context và sự kiện ứng dụng.

## 22. Lab: Kiểm chứng quyền theo ứng dụng bằng mô phỏng policy

**Phạm vi:** lab chỉ sử dụng người dùng thử, ứng dụng thử và hạ tầng được phép. Không gửi credential guessing, không tạo flood, không dò cổng trên mạng tổ chức ngoài phạm vi, không thử sửa headers/token để bypass một dịch vụ không được ủy quyền.

### 22.1. Topology giả lập

~~~text
Application domain:
  expense.app.example

PEP:
  ztna-gateway-lab

Private origin:
  expense-origin-01, private HTTPS/443

Other private destinations:
  finance-db-01, TCP/5432
  admin-jump-01, TCP/22

Users and devices:
  alice: finance-reader, managed-compliant device
  bob: general-employee, managed-compliant device
  guest: unauthenticated
  alice-byod: finance-reader, unmanaged device

Policy:
  expense-web: permit finance-reader + MFA + compliant device
  finance-db: no end-user direct connection
  admin-jump: separate privileged entitlement/JIT
~~~

**Các tên miền dùng .example là placeholder dành cho tài liệu**, không phải DNS triển khai thực. Các IP nội bộ/hostnames phải được thay bằng endpoint lab thuộc quyền quản trị nếu cần test kết nối.

### 22.2. Expected decision table

| Scenario | Identity | Device | App target | Expected |
| --- | --- | --- | --- | --- |
| 1 | alice, MFA đạt | Compliant | expense-web | **PERMIT** |
| 2 | bob, MFA đạt | Compliant | expense-web | **DENY** — thiếu entitlement |
| 3 | guest | Bất kỳ | expense-web | **Redirect/auth required hoặc DENY** |
| 4 | alice, MFA đạt | Unmanaged | expense-web | **DENY hoặc step-up theo policy; ví dụ này DENY** |
| 5 | alice đã bị disabled | Compliant | expense-web | **DENY** với phiên mới |
| 6 | alice, MFA đạt | Compliant | finance-db TCP/5432 | **DENY** — không có app grant |
| 7 | alice, MFA đạt | Compliant | admin-jump TCP/22 | **DENY** — thiếu JIT/admin entitlement |
| 8 | ops-admin + approval | Managed/healthy | admin-jump TCP/22 | **PERMIT** theo session limit |
| 9 | alice từng được phép | Device chuyển noncompliant | expense-web session cũ | **REVOKE/close** trong SLA quy định |
| 10 | alice từng được phép | Compliant | expense origin direct path | **DENY bằng network/origin policy** |

**Trường hợp (9) cần thử riêng**: một product có thể chỉ ngăn sessions mới mà không đóng ngay WebSocket/SSH session cũ. Bài nghiệm thu phải ghi rõ **revocation propagation time** được chấp nhận.

### 22.3. Policy evaluator giả lập

Một bộ ra quyết định đơn giản để học:

~~~text
function evaluate_access(request):
    app = lookup_registered_app(request.target_app_id)
    if app is unknown:
        return DENY("unknown_app")

    principal = verify_identity(request.identity_evidence)
    if principal is invalid or disabled:
        return DENY("identity_invalid")

    if not principal.has_entitlement(app):
        return DENY("not_entitled")

    if not verify_authentication_assurance(principal, app.min_assurance):
        return REQUIRE_STEP_UP("mfa_required")

    posture = fetch_verified_device_posture(request.device_id)
    if posture is stale or posture does not meet app.policy:
        return DENY("device_posture")

    if context_risk(request) exceeds app.max_risk:
        return DENY("risk_policy")

    return PERMIT(
        resource=app.id,
        allowed_destination=app.origin,
        allowed_protocol=app.protocol,
        max_session_lifetime=app.session_limit
    )
~~~

Đây là **pseudocode**, không chạy trực tiếp. Nó cố tình bỏ qua các vấn đề kỹ thuật như **OIDC flow, signed decision/transport, state management, anti-replay, rate limiting, continuous evaluation, MFA enrollment và multiple device identities**. Trong production, không gọi một hàm tự khai **request.device_id** là bằng chứng thiết bị; cần identity binding/tín hiệu được xác minh.

### 22.4. Kiểm chứng application access ở layer HTTP

Trong một môi trường đã có **lab hostname thật** và client được phép:

~~~bash
# Quan sát status và response headers, một request nhỏ.
curl --head --max-time 10 https://expense.app.example/

# Kiểm tra TLS/hostname thay vì bỏ qua xác minh.
openssl s_client \
  -connect expense.app.example:443 \
  -servername expense.app.example \
  -verify_hostname expense.app.example \
  -verify_return_error \
  < /dev/null
~~~

**Lưu ý:** những lệnh này dùng hostname placeholder .example; **chỉ chạy sau khi thay bằng hostname lab được cấp phép**. Response **302 chuyển đến IdP** hoặc **401/403** ở trạng thái chưa xác thực có thể là hành vi hợp lệ theo thiết kế; một request curl không đi hết SSO browser flow.

Không thêm **-k/--insecure** để coi TLS test thành công, không dán session cookie hoặc OAuth token thật vào terminal history.

### 22.5. Kiểm chứng không còn đường tới subnet nội bộ

Một migration đạt mục tiêu cần có **negative network test** từ endpoint đã chuyển: chỉ host ứng dụng được cấp đường đi thông qua PEP; các địa chỉ riêng khác không reachable bằng đường VPN hoặc public route.

Tuy nhiên:

- Đừng tự quét cả subnet để chứng minh. Chỉ thử những **đích lab cụ thể** đã được owner chấp thuận.
- Cần đích có listener/trace để phân biệt “không lắng nghe” với “network deny”.
- Kiểm tra **IPv4/IPv6, alternate ports, DNS cũ và đường VPN còn sót**.
- Kết quả nên ghi **firewall/PEP deny log** tại enforcement point tương ứng.

### 22.6. Kiểm thử headers do client tự khai

Trong **lab cô lập**, có thể gửi một request với **X-Authenticated-User** do client tự đặt tới gateway và xác minh PEP **không coi header ấy là danh tính**. Phải tránh chạy bài test này trên Internet service ngoài phạm vi.

Kỳ vọng:

1. PEP xóa/ghi đè headers identity không đáng tin.
2. Backend chỉ thấy **authenticated principal** từ nguồn được xác minh hoặc session/token hợp lệ.
3. Khi chưa đăng nhập, request vẫn bị yêu cầu auth/deny.
4. Direct-to-origin không thể dùng header tương tự để bypass.

**Chứng minh DENY ở gateway chưa đủ** nếu origin có đường kết nối trực tiếp; hai đường phải được thử riêng theo phương án được cấp quyền.

### 22.7. Kiểm chứng thay đổi entitlement

Trong lab, admin thay **nhóm được cấp quyền** hoặc disabled test account theo change plan:

~~~text
T0: alice thuộc Finance, có phiên expense-web hợp lệ.
T1: admin thu hồi entitlement của alice.
T2: lần mở phiên mới không được phép.
T3: session hiện hữu bị revoke/expire theo SLA đã định.
T4: application session và token riêng, nếu có, cũng được xử lý.
~~~

Đo **T2−T1** và **T3−T1**. Nếu sản phẩm không hỗ trợ revoke tức thời cho một giao thức, tài liệu chính sách phải nói rõ **giới hạn của thực thi** và bù bằng TTL/connection timeout thích hợp.

### 22.8. Kiểm thử lỗi dependency

Chỉ trong lab/staging có thể cô lập, thử **mất IdP**, **connector restart**, **PEP failover**, **backend TLS cert mismatch** và **policy engine outage** với traffic nhỏ. Kỳ vọng không có tình huống lỗi khiến gateway **tự chuyển sang cho phép tất cả users** hoặc mở origin public.

## 23. Lab thiết kế chính sách ứng dụng: Bài toán theo nhóm

### 23.1. Yêu cầu nghiệp vụ

Công ty có ba ứng dụng:

1. **Expense Portal:** nhân viên Finance đọc dữ liệu, manager phê duyệt.
2. **Vendor Tickets:** đối tác chỉ dùng helpdesk trong thời hạn hợp đồng.
3. **Production Jump Host:** chỉ Operations quản trị theo JIT.

Hạ tầng dùng **cloud edge + private connector + origin firewall**, IdP cấp thông tin user/groups. Thiết bị có thể là managed laptop hoặc BYOD.

### 23.2. Bảng policy đề xuất

| Ứng dụng | Nhóm được phép | Điều kiện | Không được phép |
| --- | --- | --- | --- |
| Expense Portal | FinanceReader, FinanceManager | MFA + compliant device | Người ngoài Finance, direct DB access |
| Expense approval | FinanceManager | Step-up + application approval permission | FinanceReader không được phê duyệt |
| Vendor Tickets | SponsoredVendor | MFA, entitlement chưa hết hạn, scope ticket theo app | Lối vào HR/Expense |
| Production Jump Host | OperationsAdmin | Managed device, JIT approval, session audit | Contractor, user không có privilege |

Mỗi dòng cần **ID tài nguyên**, port/protocol, session lifetime và nguồn identity đáng tin. Nếu vendor dùng BYOD, phải xác định điều kiện posture được hỗ trợ thay vì tự yêu cầu EDR trên máy không thuộc quyền quản lý.

### 23.3. Bài tập phát hiện rủi ro

Giả sử một admin tạo rule:

~~~text
Subject: AllAuthenticatedUsers
Resource: *.internal.example
Protocol: TCP
Ports: any
Device: any
Session: 24 hours
Decision: PERMIT
~~~

**Phân tích:** Đây có thể gần với **network-level access quá rộng**, dù rule nằm trong console ZTNA. Nó cho mọi user đã đăng nhập quyền tới nhiều dịch vụ, nhiều ports và thiết bị chưa đánh giá, không phù hợp least privilege trong kịch bản.

**Đề xuất:** Thay bằng **per-application resources, scoped host/port/protocol, groups/entitlements cụ thể, posture, shorter sessions, explicit exceptions**, và bảo đảm connector không có đường egress rộng hơn quyền cần thiết.

### 23.4. Tiêu chí chấm bài

Người học cần chứng minh:

- Một ứng dụng có **owner và boundary** xác định.
- Allow rules đủ cho luồng nghiệp vụ nhưng không mở subnet.
- Có ít nhất **ba negative cases**: wrong user, wrong device và wrong resource/port.
- Có một test **direct origin deny** với nguồn trong lab.
- Có cách kiểm tra **app authorization** sau khi ZTNA cho phép.
- Có chỉ số/log chứng minh **policy và session revocation** hoạt động.
- Có kế hoạch **fallback có kiểm soát** khi IdP/connector lỗi.

**Không đánh giá bài chỉ qua số lượng dòng policy.** Một policy ngắn nhưng chính xác, có test deny và owner rõ ràng thường tốt hơn tập rule dài nhưng không thể xác minh.

## 24. Chẩn đoán sự cố application-level access

~~~mermaid
flowchart TD
    A["Người dùng không vào được app qua ZTNA"] --> B{"DNS / client / edge reachable?"}
    B -->|Không| C["Client DNS/agent, public edge, routing"]
    B -->|Có| D{"Identity/SSO xác thực được?"}
    D -->|Không| E["IdP, redirect, MFA, clock, token validation"]
    D -->|Có| F{"Policy PERMIT?"}
    F -->|Không| G["Entitlement, device posture, context, policy version"]
    F -->|Có| H{"Connector và origin reachable?"}
    H -->|Không| I["Connector health, SG/NSG, TLS backend, target"]
    H -->|Có| J{"App response hợp lệ?"}
    J -->|Không| K["App authz, cookies, headers, DB, 4xx/5xx"]
    J -->|Có| L["Measure performance and session lifecycle"]
    C --> M["Verify lại theo đúng app/user/device"]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

### 24.1. User thấy đăng nhập lặp vô hạn

**Giả thuyết:** IdP redirect URI/cookie domain/SameSite sai, browser chặn third-party cookies, clock lệch, callback route bị proxy rewrite sai, stale session hoặc state/nonce thất bại.

**Kiểm tra:** Gateway authentication logs, IdP sign-in events, correlation ID, HTTPS/Host headers, cookie attributes và callback hostname. Không sửa bằng cách **tắt xác minh state/nonce, bỏ HTTPS hay chấp nhận mọi redirect URI**.

### 24.2. Đăng nhập thành công nhưng nhận 403

**Hai vị trí có thể tạo 403:** PEP từ chối do group/posture/entitlement hoặc backend từ chối do app authorization. Xác định **điểm trả status** từ gateway/app logs, policy ID và request ID trước khi sửa rule.

Nếu backend chặn do tenant/resource ownership, **không thêm toàn bộ user vào group admin** chỉ để hết lỗi. Phải sửa app entitlement hoặc business authorization theo owner.

### 24.3. Chỉ một vài users chung mạng bị chặn

**Giả thuyết:** thiết bị/compliance khác, role chưa được đồng bộ, session age, authentication assurance, IdP conditional access hoặc rate limit theo public NAT IP gây chặn oan.

**Kiểm tra:** user and device identities đã xác minh, policy version, thời điểm cập nhật nhóm, source IP trust, gateway/IdP logs. **Không dùng IP NAT chung làm bằng chứng users có cùng quyền**.

### 24.4. App HTML tải được, API requests lỗi

**Giả thuyết:** SPA gọi API hostname khác không qua đúng PEP, cross-origin/CORS, cookies không được gửi, expired token, WebSocket upgrade không hỗ trợ, backend route rewrite sai, request-body limit hoặc origin firewall chặn.

**Kiểm tra:** browser developer network log trong phạm vi được phép, gateway app mapping, API request IDs, status codes, destination, TLS/cert và app logs. Không mở wildcard proxy tới mọi domain chỉ để SPA chạy.

### 24.5. SSH/RDP thất bại dù web portal có quyền

**Giả thuyết:** product chỉ cấp web access, agent chưa hoạt động, sai protocol/port, OS client tự mở kết nối phụ, SSH host key không khớp, PAM approval thiếu hoặc RDP security negotiation không tương thích.

**Kiểm tra:** entitlement cho **đúng target host:port**, agent routing/connector, protocol support, target firewall, server logs và session lifecycle.

### 24.6. Connector báo healthy nhưng app bị 502/504

**Connector connected** chỉ chứng minh đường về access fabric đã mở; nó chưa chứng minh connector có quyền/route/TLS đúng tới backend. Kiểm tra:

- Backend target IP/hostname/port và DNS trong private network.
- Security group/firewall từ connector tới app.
- HTTPS backend certificate trust, SAN/SNI, timeout.
- Backend readiness, connections/queue và app dependency health.
- Có bị proxy hop/HTTP framing mismatch không.

**Không mở firewall toàn VPC** để xử lý một target không reachable; xác định chính xác hop lỗi.

### 24.7. Session vẫn chạy sau khi user bị khóa

**Giả thuyết:** gateway chỉ kiểm tra ở session start, cached decision TTL cao, long-lived TCP không bị ngắt, app session riêng tồn tại hoặc event revocation chưa tới data plane.

**Kiểm tra:** IdP disable timestamp, PE/PA/PEP event timeline, session age, connector state, application session invalidation. Nếu không thể revoke ngay do product limitation, cần đưa vào **risk acceptance, timeout policies và kế hoạch cải tiến**.

### 24.8. Truy cập bằng IP origin vẫn thành công

Đây là **dấu hiệu nghi ngờ bypass**. Kiểm tra public IP, public DNS/AAAA, legacy load balancer, NodePort, alternate listener, VPN routes và peering. Đối chiếu SG/NSG/firewall, proxy identity checks và app authentication.

**Ứng phó:** khóa đường không được phép một cách có kiểm soát, tránh gián đoạn những integration có quyền thực nhưng chưa được kiểm kê. Không chỉ đổi DNS hoặc Host header.

### 24.9. Sau migration, p95 latency tăng

Đo riêng **client→edge**, **policy/SSO**, **edge→connector**, **connector→origin**, **app/DB time**. Những yếu tố như region chọn sai, proxy queuing, TLS handshakes, upload buffering hoặc IdP redirect loops cần phân biệt.

**Không so số ping tới VPN concentrator với p95 ứng dụng qua ZTNA**: đó là hai phép đo khác bản chất.

### 24.10. ZTNA control plane lỗi nhưng sessions vẫn dùng được

Có thể là **thiết kế cho phép session đã cấp tiếp tục** trong thời gian control plane mất kết nối. Cần hiểu cache/TTL/revocation behavior và đảm bảo **không cấp quyền mới vô điều kiện**. Khi control plane phục hồi, kiểm tra policy drift và các sessions có entitlement đã hết hạn.

### 24.11. Bảng phân biệt các mã lỗi

| Quan sát | Có thể có nguyên nhân | Đừng vội kết luận |
| --- | --- | --- |
| **HTTP 302** | Redirect login/SSO | Gateway hỏng |
| **HTTP 401** | Thiếu/không hợp lệ authentication | Network firewall drop |
| **HTTP 403** | PEP policy deny hoặc app authorization deny | User cần VPN subnet |
| **HTTP 404** | Unknown app/route, app-level response | App không tồn tại trong mạng |
| **HTTP 413** | Body limit ở edge/proxy/app | User không có quyền |
| **HTTP 429** | Rate quota ở edge/gateway/app | Mã lỗi chứng minh attacker |
| **HTTP 502** | Proxy/upstream protocol/connection problem | MFA sai |
| **HTTP 503** | Unavailable gateway/connector/app targets | WAF đang chặn |
| **HTTP 504** | Upstream timeout, connection/processing delay | Chắc chắn backend CPU cao |
| **TCP timeout** | Route, firewall, connect/auth gateway, target down | Chắc chắn network-level policy chặn |
| **TLS certificate error** | Wrong SAN/CA/expiry/SNI | Có thể bỏ verify để dùng tiếp |

Cần phân biệt status **do PEP tạo** với status **do app trả qua PEP**; chỉ nhìn HTTP status tại browser là chưa đủ.

## 25. Case study: Đối tác chỉ cần xem hệ thống hỗ trợ, không cần vào mạng văn phòng

### 25.1. Trạng thái ban đầu

Một nhà cung cấp bên ngoài được cấp VPN với user/password/MFA để truy cập ứng dụng **support-portal**. Do tích hợp cũ, VPN ACL cấp quyền tới subnet **10.60.5.0/24**. Subnet còn có các dịch vụ nội bộ khác:

~~~text
Remote contractor laptop
  -> VPN
  -> 10.60.5.0/24
      10.60.5.10:443   support-portal
      10.60.5.20:443   internal-hr-ui
      10.60.5.30:22    maintenance host
      10.60.5.40:5432  reporting database
~~~

Đây là topology **giả định**; các địa chỉ private chỉ mang tính minh họa, không đại diện mạng thật. Có thể firewall bổ sung đã chặn một số đích; việc cấp route không tự đảm bảo kết nối thành công. Tuy nhiên, **mục tiêu kinh doanh của đối tác chỉ là support-portal**, nên cần giảm bề mặt ngay từ lớp network access.

### 25.2. Chính sách đích

| Thành phần | Policy mới |
| --- | --- |
| **Identity** | Partner user do sponsor cấp, có expiry và MFA |
| **Device** | BYOD hoặc managed theo mức dữ liệu; quy định rõ điều kiện |
| **App** | support.app.example qua HTTPS/443 |
| **Resource mapping** | PEP chỉ nối tới support-portal origin, không đến subnet khác |
| **Origin networking** | Chỉ connector/gateway được vào support origin |
| **Backend authz** | Chỉ thấy ticket thuộc phạm vi partner |
| **Session** | TTL, idle timeout, logout/revoke và log theo yêu cầu |
| **No access** | HR, SSH maintenance, DB và các apps không được cấp |

### 25.3. Thiết kế đường đi mới

~~~mermaid
flowchart LR
    PARTNER["Contractor browser"] --> EDGE["ZTNA access edge"]
    IDP["Partner identity + MFA"] -. "Verify user / entitlement" .-> EDGE
    PE["Policy / expiry / device signals"] -. "Access decision" .-> EDGE
    EDGE <--> CONN["Private outbound connector"]
    CONN -->|"Only support:443"| PORTAL["Private support portal"]
    CONN -. "Denied by network policy" .-> HR["Internal HR"]
    CONN -. "Denied by network policy" .-> DB["Reporting DB"]
    APP["Support backend authorization"] -. "Ticket/tenant access" .-> PORTAL
~~~

Điểm kiểm chứng chính là **contractor không được cấp route toàn subnet**, connector chỉ tới portal, và mọi truy cập trực tiếp/bỏ qua PEP đều bị network controls từ chối.

### 25.4. Những lỗi thường xuất hiện khi migration

1. Portal dùng **attachment download** trên một hostname khác, chưa được route qua PEP.
2. Ứng dụng chuyển hướng sau đăng nhập đến **internal FQDN** không thể phân giải trên client.
3. Backend dùng **X-User-ID** không được chuẩn hóa ở gateway.
4. Contract expiry được áp tại ZTNA nhưng **application session dài hạn** vẫn tồn tại.
5. VPN ACL cũ chưa bị gỡ và partner vẫn có network path tới HR.
6. Gateway hỗ trợ HTTP nhưng một phần portal dùng **WebSocket** không tương thích.
7. Connector mặc định có egress tới **mọi máy trong 10.60.5.0/24**.

**Bài học:** Một sơ đồ ZTNA “đúng” nhưng thiếu negative testing, app dependency map và session revocation vẫn chưa chứng minh giảm quyền.

### 25.5. Kết quả nghiệm thu

| Test | Kỳ vọng |
| --- | --- |
| Partner hợp lệ mở portal với MFA | Cho vào qua PEP |
| Partner không có entitlement | Deny |
| Partner đã hết hạn hợp đồng | Deny login mới, revoke/expire sessions theo SLA |
| Partner cố truy cập HR/DB qua gateway | Unknown/unauthorized resource bị deny |
| Partner thử direct origin từ client lab | Network deny |
| Connector thử kết nối HR/DB từ host lab tương ứng | Egress policy deny, có log |
| Partner đọc ticket của tenant khác | Backend application authorization deny |
| Portal upload/download/WebSocket được phép | Hoạt động với limits và audit |
| IdP/connector mất tạm thời trong lab | Không chuyển thành unrestricted access |
| VPN route cũ | Đã thu hẹp/gỡ với nhóm đã migration |

### 25.6. Nếu partner thiết bị bị chiếm sau khi truy cập?

ZTNA có thể hạn chế **những ứng dụng khác** mà thiết bị tiếp cận, nhưng nếu token/session đang hợp lệ, kẻ chiếm có thể cố lạm dụng chính **support portal**. Cần **phishing-resistant MFA khi phù hợp, session security, app authorization, rate limits, DLP nếu có, monitoring và khả năng revoke nhanh**.

**Giảm lateral network reachability không đồng nghĩa ngăn mọi hành vi lạm dụng bên trong ứng dụng được cấp.**

## 26. Checklist nghiệm thu một hệ thống application-level access

### 26.1. Kiến trúc và inventory

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Application inventory** | Có owner, FQDN, protocol, target, sensitivity cho từng app? | App catalog và dependency map |
| **Resource granularity** | Mỗi grant tương ứng một app/host/port thay vì cả subnet? | Access policy và access graph |
| **Network routes** | Endpoint có còn route rộng tới private network không? | Routing/agent/VPN config và negative tests |
| **Origin private** | Backend có thể bị gọi trực tiếp bằng IP, IPv6, legacy hostname không? | Network deny evidence, SG/NSG/NetworkPolicy |
| **Connector scope** | Connector chỉ tới targets được phép? | Egress policy, target inventory và test deny |
| **Ingress paths** | Mọi public/internal entrypoints đều có PEP hoặc chặn theo policy? | LB/ingress/NodePort inventory |
| **Cloud/multi-region** | Policy, certificates và origin protection nhất quán? | Per-region verification |
| **Legacy access** | Có các apps vẫn dùng VPN và ACL hẹp theo kế hoạch? | Exception register, owner, review dates |

### 26.2. Identity, posture và authorization

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Authentication** | IdP/token/SSO được xác minh đúng audience và flow? | IdP and gateway validation tests |
| **MFA** | Nhóm app nhạy cảm có đủ authentication assurance? | MFA success/failure, step-up tests |
| **Entitlement** | Chỉ group/role hợp lệ được vào app? | Allow + wrong-role deny |
| **Device posture** | Có nguồn tín hiệu đáng tin, TTL và policy unknown? | Managed/unmanaged tests |
| **User lifecycle** | Nghỉ việc/chấm dứt hợp đồng làm mất quyền kịp thời? | JML/revocation audit |
| **Session lifecycle** | Login, idle/absolute timeout, logout, revoke hoạt động? | Session timeline và old connection test |
| **Header integrity** | Backend không tin X-User-ID từ client? | Strip/overwrite, signed assertion/mTLS test |
| **App authorization** | User đã vào app vẫn bị giới hạn theo tenant/object? | BOLA/IDOR negative tests và app audit |
| **Service identity** | Workload-to-workload peer được xác thực theo policy? | mTLS/identity and authz evidence |

### 26.3. Giao thức, an toàn mạng và availability

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Protocol support** | HTTP/2/3, WebSocket, gRPC, SSH/RDP, TCP theo nhu cầu? | Real workflow tests |
| **TLS frontend/backend** | Hostname/trust validated trên mọi TLS hop? | Positive và certificate mismatch tests |
| **Rate/resource limits** | Request size, RPS, quota, concurrency và timeout đủ? | Boundary/load-small tests |
| **DDoS/WAF** | Public PEP được bảo vệ upstream phù hợp? | WAF/edge policy và monitoring |
| **Connector HA** | Mất một connector có lối dự phòng an toàn? | Controlled failover |
| **IdP/control-plane outage** | Phân biệt session cũ và cấp quyền mới khi lỗi? | Dependency failure drill |
| **Performance** | p95/p99 và error rate đạt SLO? | End-to-end metrics |
| **Break-glass** | Có đường khôi phục hẹp, được duyệt, log và expiry? | Runbook và exercise |
| **Rollback** | Có cách thu hẹp/khôi phục policy không mở origin rộng? | Versioned change và post-tests |

### 26.4. Quan sát và quản trị

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Policy-as-code** | Access rules/targets có review và version? | PR/change logs |
| **Least-privilege IAM** | Quyền sửa gateway/connector/IdP giới hạn? | Role and access review |
| **Audit telemetry** | Ai, app nào, policy nào, decision và timestamp nào? | Correlated PEP/IdP/app logs |
| **Direct bypass alerts** | Có phát hiện traffic origin không qua PEP? | Firewall/flow deny alerts |
| **Pipeline health** | Mất logs/collector làm phát cảnh báo? | Heartbeat/ingest lag tests |
| **Privacy** | Không log passwords/tokens/cookies và PII quá mức? | Data handling review |
| **Entitlement reviews** | Có owner duyệt quyền theo kỳ và khi chuyển vai trò? | Review outcomes |
| **Exception control** | Những bypass/legacy grants có owner/expiry? | Exception inventory |

**Một checklist chỉ đạt PASS khi có bằng chứng hành vi**, không phải khi console báo “Enabled”. Trọng tâm là **user hợp lệ được vào đúng app, user sai bị deny, direct origin không mở, quyền hết hạn được thu hồi và ứng dụng hoạt động ổn định**.

## 27. Câu hỏi tự kiểm tra và đáp án gợi ý

**1. Vì sao network-level reachability không đủ để thể hiện quyền dùng một app?**

Vì một IP/subnet/port chỉ mô tả đường đi mạng, không chứng minh người dùng có quyền trên ứng dụng, tenant hay dữ liệu. Application-level policy ràng buộc quyền với **resource cụ thể và identity/context**.

**2. VPN có tự là mô hình vi phạm Zero Trust không?**

Không. Một VPN có MFA, posture, least-privilege per-user ACL và phân đoạn chặt có thể hỗ trợ các nguyên tắc Zero Trust; vấn đề là **quyền mạng được cấp rộng đến đâu** và có xác minh theo resource hay không.

**3. ZTNA có bắt buộc thay mọi VPN trong doanh nghiệp không?**

Không. Site-to-site, protocols legacy hoặc workloads có yêu cầu network-level vẫn có thể dùng VPN được phân đoạn và giám sát.

**4. Application-level access luôn hiểu HTTP path và object authorization?**

Không. Có triển khai chỉ hạn chế **app/host:port/TCP session**. Backend thường vẫn thực hiện authorization cho từng object/tenant.

**5. Theo NIST, PE, PA, PEP khác nhau thế nào?**

PE quyết định policy, PA thiết lập/đóng control path theo quyết định và PEP cho phép/giám sát/chấm dứt traffic giữa subject với resource.

**6. “Clientless ZTNA” có nghĩa mọi SSH/RDP/UDP app đều chạy trong browser?**

Không. Phải kiểm tra khả năng protocol; có thể cần agent, bastion, session gateway hoặc scoped VPN riêng.

**7. Vì sao chặn direct-to-origin quan trọng hơn việc ẩn DNS?**

Vì nếu origin vẫn reachable trực tiếp, người dùng có thể bypass gateway, MFA/device policy hoặc WAF dù hostname không được công bố.

**8. Một gateway nhận X-Authenticated-User: admin từ client có nên tin không?**

Không. Identity phải do PEP/IdP xác minh, gateway strip/overwrite client headers và backend chỉ tin đường truyền/assertion được bảo vệ.

**9. User thuộc group Finance có luôn được phê duyệt tất cả hóa đơn không?**

Không. ZTNA có thể cấp quyền vào Finance app, nhưng backend phải kiểm tra role, tenant, quyền phê duyệt và object ownership.

**10. JWT có trường sub và chữ ký hợp lệ là đủ cho mọi API?**

Không. Cần kiểm tra issuer, audience, algorithm/keys, thời gian, token type, scope/binding và revocation profile. ID token không tự là API access token.

**11. Phishing-resistant MFA mang lại gì cho ZTNA?**

Giảm nguy cơ credential phishing và tăng assurance khi cấu hình đúng; không thay app authorization, session protection hoặc endpoint security.

**12. Tại sao MDM “compliant” không chứng minh thiết bị chắc chắn sạch?**

Vì posture có thể trễ, bị can thiệp hoặc không thấy mọi compromise. Nó là một tín hiệu trong quyết định, không phải bằng chứng tuyệt đối.

**13. Re-evaluate access có nghĩa kiểm tra mọi packet?**

Không nhất thiết. Tần suất evaluation/revocation phụ thuộc session, giao thức, PEP và product. Cần đo thời gian thu hồi.

**14. Logout IdP có chắc hủy ngay WebSocket đang mở không?**

Không. PEP/app có thể giữ session riêng; phải kiểm tra session revocation propagation và long-lived connections.

**15. Mã hóa TLS từ gateway tới backend có đủ xác thực backend không?**

Không nếu gateway không xác minh đúng chain/SAN/identity; mã hóa và xác thực đích là hai điều kiện cần kiểm chứng.

**16. mTLS giữa connector và origin đã thay MFA của nhân viên chưa?**

Không. mTLS này xác thực các workload/connection endpoints; end-user identity/entitlement là lớp khác.

**17. Connector dùng outbound tunnel có tự an toàn nếu nó được mở egress toàn VPC?**

Không. Nếu connector hoặc control plane bị chiếm, phạm vi tới internal targets có thể quá rộng. Cần egress allowlist/segmentation.

**18. Vì sao multi-cloud không có nghĩa chỉ cần một ZTNA hostname là đủ?**

Vì còn app identity, origin isolation, backend network paths, DNS, regional policy parity và logging mỗi môi trường.

**19. Một principal có thể được cho vào app nhưng vẫn nhận HTTP 403?**

Có. App có thể từ chối thao tác do thiếu business authorization; cần xác định nguồn 403.

**20. Khi mất IdP, có nên cho mọi user vào app để giảm downtime?**

Không. Nên có fail policy, cached decisions có giới hạn nếu được phê duyệt, HA và break-glass riêng; không biến deny thành allow all.

**21. Tại sao browser SPA dễ gặp lỗi sau khi chuyển qua proxy?**

Vì API origins, cookies, CORS, deep links, redirect URIs và WebSocket/streaming có thể khác đường đi cũ.

**22. Để chứng minh giảm lateral reachability cần test gì?**

Ngoài login thành công, phải có **negative network tests** tới những app/hosts/ports không được cấp và direct origin, cùng log chặn ở enforcement point.

**23. Vì sao một lần login test không đủ nghiệm thu?**

Vì nó chưa xác minh app workflow, authorization, long-lived sessions, expiry, revocation, failover, origin bypass hoặc hậu quả khi policy đổi.

**24. Khi một partner bị khóa tài khoản, điều gì có thể còn tồn tại?**

Gateway session, app session, cached authorization decisions hoặc TCP connections đang mở; phải đo thời hạn chấm dứt và tác động tới từng hop.

**25. Nếu edge access log PERMIT nhưng backend báo 502, có phải policy sai không?**

Không nhất thiết. Policy có thể cấp đúng, nhưng connector, backend TLS, route, app readiness hoặc dependencies bị lỗi.

**26. Một policy allow *.internal.example TCP any có đạt least privilege ứng dụng không?**

Trong đa số threat models không: nó rất rộng, gần quyền cấp mạng. Nên tách cụ thể host/protocol/port/identity và quản lý exceptions.

**27. ZTNA giúp ngăn mọi exfiltration từ app được cấp không?**

Không. User có quyền vào app có thể đọc/tải dữ liệu được app cho phép; cần application authorization, audit, data policy và DLP phù hợp nếu yêu cầu.

**28. Vì sao phải giám sát PEP và application logs cùng lúc?**

PEP biết permit/deny session, app biết thao tác/tài nguyên. Cần cả hai để phân biệt lỗi access, backend authorization và hành vi nghiệp vụ.

**29. Khi bắt đầu migration, ứng dụng nào thường nên chọn làm pilot?**

Một web application có owner rõ, protocol hỗ trợ, dependency map và rollback đơn giản; chọn dựa trên risk và khả năng kiểm chứng.

**30. Thước đo quan trọng nhất để chứng minh ZTNA chuyển đổi thành công là gì?**

Một bộ bằng chứng: **đúng chủ thể/thiết bị được vào đúng app**, các đường network không được phép **bị chặn**, ứng dụng **hoạt động đúng**, session **thu hồi đúng SLA** và control/telemetry **có thể vận hành, điều tra, khôi phục**.

## 28. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “ZTNA chỉ là VPN đổi tên.” | Tư duy ZTNA nhấn mạnh resource-specific access, identity/context và enforcement; triển khai cụ thể có thể dùng tunnel scoped nhưng không nên cấp quyền subnet rộng. |
| “Dùng VPN là chắc chắn không Zero Trust.” | VPN được phân đoạn, MFA và policy hẹp có thể là một phần của kiến trúc Zero Trust. |
| “Có ZTNA thì không cần firewall.” | Firewall/SG/NSG/NetworkPolicy vẫn cần để khóa origin, egress connector và các đường khác. |
| “App-level access luôn kiểm tra từng HTTP object.” | Có sản phẩm chỉ kiểm soát app hoặc host:port; business authorization vẫn thuộc backend. |
| “User ở mạng nội bộ là đủ đáng tin.” | Network location là tín hiệu ngữ cảnh, không là authorization. |
| “User có quyền vào app thì có quyền vào toàn subnet.” | Policy nên chỉ mở application resource được cấp; hạn chế lateral routes. |
| “ZTNA app không có DNS public nghĩa là không ai tìm thấy origin.” | DNS hiding không thay network access control. |
| “Có identity-aware proxy là origin không bị bypass.” | Phải kiểm tra public IP, alternate ingress, IPv6, legacy LB/NodePort và VPN routes. |
| “X-Authenticated-User do client gửi là bằng chứng user.” | Header chỉ tin khi được gateway xác minh/tạo và bảo vệ đường truyền. |
| “Client IP trong X-Forwarded-For luôn là IP thật.” | Phụ thuộc trusted proxy chain, NAT và xử lý header đúng. |
| “Header Host và TLS SNI tự cấp quyền truy cập.” | Chúng tham gia routing/certificate selection, không chứng minh user entitlement. |
| “JWT decode được sub là đủ để tin token.” | Cần verify signature/keys, issuer, audience, thời hạn, scope/token purpose và chính sách liên quan. |
| “OIDC ID token dùng được như bearer access token cho mọi API.” | Mục đích và audience khác; backend phải chấp nhận đúng loại token. |
| “Bật MFA là ngăn toàn bộ session hijacking.” | Session cookies/tokens vẫn có thể bị lộ; cần session controls và monitoring. |
| “Thiết bị managed không thể bị xâm nhập.” | Device posture là tín hiệu có thể trễ hoặc không đầy đủ. |
| “Continuous verification nghĩa kiểm tra lại từng packet.” | Phụ thuộc cơ chế re-evaluation/revocation; cần đo thời gian thực tế. |
| “Disabled user đồng nghĩa mọi session đã ngắt tức thì.” | Gateway/app sessions và long-lived connections có thể còn tồn tại. |
| “TLS connector→origin có nghĩa origin identity luôn được xác minh.” | Cần CA/SAN/peer identity verification đúng, không chỉ bật encryption. |
| “mTLS connector xác thực luôn end-user.” | Nó thường xác thực endpoints/workloads; end-user identity là lớp khác. |
| “Outbond connector tự an toàn vì không mở inbound Internet.” | Connector vẫn có privileges và đường tới private apps; phải segment và bảo vệ keys. |
| “Tất cả ứng dụng chỉ cần trình duyệt, không cần agent.” | SSH/RDP/TCP/UDP/legacy clients có thể cần gateway/agent khác. |
| “Một lần HTTP 200 chứng minh app migration thành công.” | Cần negative tests, real workflows, app authorization, revocation và HA. |
| “HTTP 403 là chắc do ZTNA.” | Có thể là app, API gateway hoặc WAF; xác định hop phát sinh. |
| “Quyền ZTNA cấp mọi tài nguyên trong app.” | App vẫn kiểm tra tenant/record/action, tránh BOLA/IDOR. |
| “Có access policy đã đủ chống DDoS.” | Public edge vẫn cần capacity, WAF/rate limits và upstream protection. |
| “Không thấy policy deny nghĩa là người dùng được phép.” | Có thể log mất, PEP bypass hoặc connector không giám sát đúng. |
| “Break-glass nên cho phép truy cập không cần kiểm soát.” | Emergency path phải hẹp, MFA/authorization phù hợp, log, expiry và audit. |
| “Policy cho *.internal.example TCP any vẫn là least privilege vì ở ZTNA.” | Quyền tới wildcard + mọi ports có thể quá rộng, cần phân rã app/host:port. |
| “Mọi đường đi Internet→private app đều qua một proxy.” | Có thể tồn tại peering, VPN, NodePort, legacy LB, private link và đường nội bộ khác. |
| “Càng lưu nhiều HTTP body càng an toàn.” | Log có thể lộ credentials/PII, gây chi phí và rủi ro tuân thủ. |
| “ZTNA cần loại bỏ mọi segmentation ở east–west network.” | Workload-to-workload traffic và backend zones vẫn cần được bảo vệ. |
| “Không thể dùng Zero Trust khi app chưa hiện đại hóa.” | Có thể triển khai theo từng ứng dụng/host và giữ segmented legacy paths có quản lý. |

## 29. Tổng kết

**Application-level access thay cho network-level access** là sự thay đổi về **đơn vị cấp quyền**, không đơn thuần thay đổi client VPN hoặc mua một dịch vụ proxy. Trong mô hình truy cập mạng, người dùng/thiết bị có thể được cấp **route hoặc khả năng kết nối** tới nhiều địa chỉ trong subnet. Trong cách tiếp cận **ZTNA theo ứng dụng**, chủ thể chỉ được cấp **phiên tới ứng dụng/tài nguyên cụ thể** khi danh tính, quyền, thiết bị và ngữ cảnh thỏa policy. Đường tới các ứng dụng khác không được mở chỉ vì user đã đăng nhập.

Những nguyên tắc cốt lõi:

1. **Resource-centric:** định danh từng ứng dụng, host/protocol/port hoặc operation phù hợp, không cấp cả subnet nếu không cần.
2. **Identity and context-aware:** dùng user/workload identity đã xác minh, MFA, device posture và entitlements; không dựa vào network location đơn thuần.
3. **Policy decision và enforcement rõ:** phân biệt PE/PA/PEP, biết vị trí control plane/data plane và đo được hành vi grant/deny/revoke.
4. **Origin isolation:** khóa các đường direct-to-origin, kể cả alternate DNS/IP, VPN, IPv6, cloud LB và Kubernetes ingress khác.
5. **Defense in depth:** firewall/NetworkPolicy bảo vệ đường đi; app authorization bảo vệ tài nguyên nghiệp vụ; TLS/mTLS bảo vệ kênh và danh tính endpoints.
6. **Session lifecycle:** có TTL, logout, step-up và cơ chế thu hồi được kiểm chứng, đặc biệt với SSH/RDP/WebSocket/streams dài.
7. **Protocol-aware deployment:** web proxy, endpoint agent, private connector, PAM và service mesh phục vụ những nhu cầu khác nhau.
8. **Measurable migration:** pilot, allow/deny tests, dependency mapping, performance, HA, break-glass và rollback có kiểm soát.
9. **Observability and governance:** log policy decisions, actor/changes, app access và origin network denies; giám sát mất telemetry và review entitlement.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, ZTNA kết nối nội dung của **VPN, phân đoạn mạng, firewall, xác thực, PKI, DNS, IDS/IPS, proxy và cloud network security**. Một triển khai thành công phải chứng minh **bề mặt kết nối được thu hẹp**, không chỉ có giao diện đăng nhập mới. Định hướng là **đúng chủ thể, đúng ứng dụng, đúng điều kiện, đúng thời hạn và không có đường vòng**, đồng thời giữ cho dịch vụ khả dụng và khả năng điều tra sự cố đáng tin cậy.

### Tài liệu tham khảo và hướng đọc thêm

- **NIST SP 800-207 — Zero Trust Architecture:** nguyên tắc Zero Trust, policy engine, policy administrator, policy enforcement point và resource-focused access.
- **NIST SP 800-207A — A Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Cloud Environments:** định hướng policy/identity-aware access trong cloud-native và multi-cloud.
- **NIST SP 800-63 Digital Identity Guidelines:** xác thực danh tính và authentication assurance; dùng phiên bản hiện hành trong thiết kế cụ thể.
- **CISA Zero Trust Maturity Model:** các trụ cột identity, devices, networks, applications/workloads và data.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** vai trò client, authorization server và access token theo OAuth 2.0.
- **OpenID Connect Core:** authentication flows, ID token, issuer/audience và session-related design.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** cơ chế bảo vệ authorization code flow.
- **RFC 7519 — JSON Web Token (JWT)** và **RFC 8725 — JWT Best Current Practices:** token format, validation và các lỗi sử dụng phổ biến.
- **RFC 8446 — TLS 1.3:** handshake, encryption và yêu cầu bảo vệ kết nối TLS.
- **RFC 9110 — HTTP Semantics:** ngữ nghĩa HTTP, status codes, headers và caching.
- **RFC 2606 — Reserved Top Level DNS Names:** .example và các tên dùng cho tài liệu/thử nghiệm.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** dải IP minh họa, không sử dụng như endpoint production.
- **W3C Web Authentication (WebAuthn) và FIDO Alliance specifications:** xác thực chống phishing và ràng buộc xác thực.
- **OWASP Authorization Cheat Sheet, Authentication Cheat Sheet và Session Management Cheat Sheet:** authorization theo resource, quản lý phiên, MFA và lỗi triển khai.
- **OWASP API Security Top 10 (2023):** rủi ro BOLA, broken authentication, resource consumption và misconfiguration.
- **Kubernetes Documentation — NetworkPolicy, Ingress và Service:** phân đoạn workloads và điểm truy cập origin trong môi trường container.
- **Tài liệu chính thức của ZTNA gateway/connector, IdP, MDM/EDR, PAM và cloud provider đang triển khai:** xác minh protocol support, session revocation, connector permissions, backend TLS, logging, HA, region/tier và giới hạn sản phẩm cụ thể.
