# Service mesh giải quyết vấn đề gì?

Một hệ thống thương mại điện tử ban đầu chỉ có một ứng dụng. Khi tách thành nhiều dịch vụ như `web`, `orders`, `payments`, `inventory` và `notifications`, mỗi request của người dùng có thể tạo thêm nhiều kết nối nội bộ. Nhóm phát triển gặp các vấn đề: service nào được gọi service nào, có cần mã hóa mọi kết nối không, danh tính giữa các service được kiểm tra thế nào, khi backend chậm thì timeout/retry ra sao, và một request thất bại đã đi qua những service nào?

Nếu từng nhóm tự triển khai TLS, client libraries, retries, metrics, tracing và chính sách truy cập, mỗi service có thể hành xử khác nhau. Một số kết nối dùng HTTPS, một số dùng HTTP; nơi retry vô hạn, nơi không timeout; một số API tin địa chỉ IP/hostname thay cho danh tính workload. **Service mesh** ra đời để đưa một phần các năng lực giao tiếp liên dịch vụ này vào một **lớp hạ tầng chung**, được điều khiển bằng chính sách.

**Service mesh giải quyết bài toán quản trị lưu lượng và bảo mật giao tiếp service-to-service ở quy mô nhiều workload**, bằng cách tách **data plane** xử lý kết nối khỏi **control plane** phân phối cấu hình, danh tính và chính sách. Service mesh thường gắn với **mTLS**, nhưng **mTLS chỉ là một phần**: quản lý tuyến, timeout, retry, cân bằng tải, telemetry và authorization cũng có vai trò quan trọng.

Bài thuộc chương **Service mesh và mTLS** của module **SECURITY_NETWORK_SECURITY**. Kiến thức kết nối với phân đoạn mạng, firewall, VPN, IDS/IPS, kiểm soát kết nối, TLS/PKI, Kubernetes NetworkPolicy và mạng cloud. Nội dung tập trung vào **vấn đề, cơ chế, phạm vi, đánh đổi và cách kiểm chứng**, không giả định mọi hệ thống đều phải cài mesh.

> **Thông điệp chính:** service mesh giúp **chuẩn hóa và quan sát giao tiếp giữa các dịch vụ**; nó **không tự sửa lỗ hổng nghiệp vụ, không tự cấp quyền user đúng, không bảo vệ mọi đường mạng và không bảo đảm ứng dụng luôn khả dụng**.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Nhận diện các vấn đề của kiến trúc microservices khiến service mesh trở nên hữu ích.
2. Phân biệt **service mesh**, **API gateway**, **reverse proxy**, **Kubernetes Service/Ingress**, **NetworkPolicy** và **service discovery**.
3. Giải thích vai trò **data plane**, **control plane**, proxy và mô hình **sidecar** hoặc **ambient/node-level**.
4. Mô tả cách **workload identity, PKI và mTLS** phối hợp để xác thực/mã hóa traffic giữa các workload.
5. Hiểu **traffic management** như canary, load balancing, timeout, retry, circuit breaking/outlier detection và giới hạn của chúng.
6. Phân biệt **service-to-service authorization** với **user-to-resource authorization**.
7. Nắm cách dùng logs, metrics, traces và topology để chẩn đoán lưu lượng liên dịch vụ.
8. Đánh giá các đánh đổi về performance, vận hành, kiểm soát control plane, chứng chỉ, compatibility và migration.
9. Thiết kế một thử nghiệm nhỏ có **positive/negative tests**, quan sát được hành vi thực và khôi phục được khi thay đổi chính sách.

## 2. Khi chưa có service mesh, hệ thống gặp những vấn đề gì?

Giả sử một yêu cầu đặt hàng có đường đi:

~~~mermaid
flowchart LR
    U["User / browser"] --> G["Ingress / API gateway"]
    G --> O["Orders service"]
    O --> P["Payment service"]
    O --> I["Inventory service"]
    O --> N["Notification service"]
    P --> DB[("Payment database")]
    I --> ST[("Inventory database")]
~~~

Khi chỉ có vài service, cấu hình có thể được quản lý bằng các thư viện client và vài reverse proxy. Nhưng khi số service và nhóm phát triển tăng, số **quan hệ gọi nhau** tăng nhanh và dễ phát sinh cấu hình không nhất quán.

| Vấn đề | Triệu chứng thực tế | Hệ quả có thể có |
|---|---|---|
| **Không biết chính xác ai gọi ai** | Chỉ thấy IP/Pod, thiếu identity rõ | Khó giới hạn đường east–west và điều tra lateral movement |
| **TLS/mTLS triển khai không đồng đều** | Service A bật TLS, service B dùng plaintext | Ranh giới dữ liệu và xác thực không nhất quán |
| **Quản lý certificate phân tán** | Mỗi nhóm tự cấp, lưu, rotate chứng chỉ | Cert hết hạn, khóa bị lộ, outage khi rotate |
| **Timeout/retry khác nhau** | Một service timeout 2 giây, service khác chờ vô hạn | Latency cao, retry storm và cascading failure |
| **Deployment canary khó kiểm soát** | Muốn chuyển 5% traffic nhưng phải sửa ứng dụng | Khó rollback, khác biệt giữa client versions |
| **Thiếu telemetry chung** | Log request bị đứt giữa các service | Chậm phát hiện hop gây lỗi |
| **Mạng quá rộng** | Pod nào cũng gọi được service nhạy cảm | Tăng blast radius khi workload bị xâm nhập |
| **Thay đổi hạ tầng khó khăn** | Đổi backend endpoint cần sửa client | Kết hợp chặt code ứng dụng và topology |

Service mesh tập trung vào **những tính năng lặp lại của đường truyền liên dịch vụ**. Điều này giúp đội platform cung cấp một lớp điều khiển thống nhất để các nhóm sản phẩm không phải tự viết lại cùng một logic mạng.

### 2.1. Không phải ứng dụng nào cũng gặp đủ các vấn đề trên

Một ứng dụng đơn khối (monolith) hoặc hệ thống chỉ vài service có thể dùng **TLS library chuẩn + API gateway + NetworkPolicy + observability** mà không cần mesh. Thêm service mesh tạo một hệ thống phức tạp mới; chỉ có ý nghĩa khi các vấn đề cụ thể đủ lớn để bù chi phí của nó.

**Câu hỏi đầu tiên không phải "Chọn Istio hay Linkerd?" mà là "Bài toán nào đang không kiểm soát được bằng những công cụ hiện có?"**

## 3. Service mesh là gì, và không phải là gì?

Service mesh là lớp hạ tầng hỗ trợ quản lý **communication giữa các service/workload**. Một kiến trúc thường có:

- **Data plane:** các proxy hoặc thành phần networking thực thi routing, mTLS, policy và thu telemetry trên traffic.
- **Control plane:** cung cấp cấu hình, service discovery/endpoint information, certificate/trust và chính sách cho data plane theo quyền được kiểm soát.
- **Identity plane / CA integration:** cấp và quản lý danh tính workload/certificates, đôi khi tích hợp vào control plane hoặc dịch vụ riêng.
- **Policy & observability integration:** công cụ định nghĩa quyền giao tiếp và ghi lại flow/metrics/traces.

Các triển khai có thể dùng proxy **sidecar gắn với từng Pod**, **node-level proxy**, **ambient data plane** hoặc biến thể khác. Vì vậy không định nghĩa service mesh là "mỗi Pod nhất thiết phải có Envoy sidecar".

### 3.1. Service mesh và những công nghệ dễ nhầm

| Công nghệ | Trả lời câu hỏi chính | Phạm vi thường gặp | Không tự thay thế |
|---|---|---|---|
| **Service mesh** | Workload A giao tiếp workload B theo identity, route và policy nào? | East–west / đôi khi qua mesh gateways | App AuthZ, network firewall và logic nghiệp vụ |
| **API gateway** | Client/API consumer được gọi API nào, rate limit/auth như thế nào? | North–south/API edge | Mesh identity/mTLS mọi service-to-service hop |
| **Ingress Controller / Gateway API** | HTTP(S) hostname/path/header đi vào backend nào? | Ingress L7 | Toàn bộ mTLS/telemetry nội bộ nếu không tích hợp |
| **Kubernetes Service** | Service name ánh xạ tới tập Pod endpoints thế nào? | Discovery/L4 load distribution | Peer authentication và app authorization |
| **NetworkPolicy** | Pod nào được mở kết nối L3/L4 tới Pod/IP/port nào? | Pod network policy do CNI enforce | TLS identity, HTTP method/path, retry/tracing |
| **Cloud security group / firewall** | Vùng nguồn/đích nào được phép ở lớp mạng? | VPC/VNet, VM, network interface | Workload identity và policy L7 |
| **VPN/IPsec** | Đường mạng giữa hai điểm/vùng được bảo vệ thế nào? | Tunnel/site/user | Quyền giữa từng service ở phía trong |
| **TLS library trong ứng dụng** | Ứng dụng mã hóa/xác thực một peer thế nào? | Một connection/session cụ thể | Fleet-wide configuration/discovery/telemetry nếu không tự xây |

Các lớp **bổ sung** cho nhau. Một request HTTP từ Internet có thể đi qua CDN/WAF, ingress gateway, mesh workload proxies, CNI NetworkPolicy và ứng dụng kiểm tra JWT/tenant. Không có lớp nào tự mang toàn bộ trách nhiệm.

### 3.2. North–south và east–west

- **North–south:** traffic từ ngoài vào hệ thống hoặc hệ thống ra ngoài, ví dụ browser → ingress gateway.
- **East–west:** traffic giữa các workloads bên trong hệ thống, ví dụ orders → inventory.

Đây là **mô hình định hướng**, không phải phân loại quyền tuyệt đối. Service mesh có thể hỗ trợ ingress/egress gateways, nhưng **bài toán chính thường là chuẩn hóa giao tiếp east–west**.

## 4. Kiến trúc data plane và control plane

~~~mermaid
flowchart TB
    subgraph CP["Control plane / trust & policy"]
      DISC["Discovery / endpoints / routing rules"]
      PKI["Workload identity & certificate issuance"]
      AUTH["Security / authorization policy"]
    end
    subgraph DP["Data plane"]
      A["Orders application"]
      PA["Proxy / L4 tunnel for Orders"]
      PB["Proxy / L4 tunnel for Inventory"]
      B["Inventory application"]
    end
    A --> PA
    PA -->|"mTLS + traffic management"| PB
    PB --> B
    DISC -.->|"Distribute config"| PA
    DISC -.->|"Distribute config"| PB
    PKI -.->|"Identity / trust material"| PA
    PKI -.->|"Identity / trust material"| PB
    AUTH -.->|"Effective rules"| PA
    AUTH -.->|"Effective rules"| PB
    PA -.-> TELE["Metrics / traces / access logs"]
    PB -.-> TELE
~~~

**Phân biệt quan trọng:**

- **Data plane xử lý request thật.** Phần mềm trong data plane có thể terminate/originate TLS, chọn upstream, enforce một số policy và ghi metrics.
- **Control plane phân phối desired configuration.** Nó không nhất thiết nhận mọi packet hay mọi HTTP request.
- **Certificate và policy** cần có vòng đời cấp phát, kiểm tra identity, rotate và thu hồi; control plane **cũng là security-critical asset**.

Trong kiến trúc proxy truyền thống, data plane thường dùng các proxy chuyên dụng như Envoy, nhưng tên proxy và cơ chế phân phối khác nhau theo mesh. Không lấy sơ đồ chung này làm mô tả duy nhất của Istio, Linkerd hay Consul.

### 4.1. Ví dụ thay đổi cấu hình mà không sửa business code

Giả sử API payment có 3 replicas, và đội vận hành muốn:

1. Chỉ service orders có quyền gọi API payment.
2. Client orders phải dùng mTLS để nói với payment.
3. Timeout tối đa cho một lần gọi là một mức đã được phê duyệt.
4. Canaries nhận một phần lưu lượng trong giới hạn SLO.
5. Telemetry cho thấy upstream nào gây 503 hoặc latency cao.

Một service mesh hỗ trợ những tính năng tương ứng có thể thực thi **một phần hoặc nhiều phần** qua chính sách data plane. **Ứng dụng vẫn chịu trách nhiệm** kiểm tra user, tenant, order state và logic tài chính.

## 5. Sidecar proxy và mô hình không sidecar

### 5.1. Sidecar model

Trong một mô hình phổ biến trên Kubernetes, mỗi Pod tham gia mesh chứa **application container** và **proxy sidecar**. Traffic phù hợp được chuyển qua proxy bằng cơ chế redirect/datapath thích hợp.

~~~mermaid
flowchart LR
    subgraph PODA["Orders Pod"]
      APPA["orders app"]
      PROXYA["sidecar proxy"]
      APPA --> PROXYA
    end
    subgraph PODB["Payments Pod"]
      PROXYB["sidecar proxy"]
      APPB["payments app"]
      PROXYB --> APPB
    end
    PROXYA -->|"mTLS over network"| PROXYB
~~~

**Lợi ích:** proxy gần application, có thể thực thi các tính năng L4/L7 hỗ trợ; app thường không cần tự triển khai cơ chế mesh tương ứng.

**Đánh đổi:** thêm container/process, tài nguyên CPU/RAM, bootstrap/upgrade sidecar, port capture, exceptions cho probes và lỗi do proxy/datapath. Khi app kết nối localhost/sidecar, lưu lượng **giữa app và proxy trong cùng Pod thường không được mTLS mã hóa** theo cách "wire mTLS" giữa proxies; cần xác định threat boundary của Pod/node.

### 5.2. Ambient hoặc node-level dataplane

Một số kiến trúc chia chức năng:

- **L4 secure tunnel/node proxy:** thực hiện kết nối/identity protection và telemetry cơ bản.
- **Optional L7 proxy/waypoint:** xử lý routing và authorization mức HTTP khi cần.
- **Control plane:** quản lý nhận dạng, certificates và phân phối policy.

Trong triển khai **Istio ambient**, một ví dụ khái niệm là `ztunnel` cho L4 và `waypoint proxy` cho L7 khi được cấu hình và các điều kiện enrollment/coverage thỏa. **Không tự suy rằng ambient đã có mọi tính năng L7 mà không cần waypoint**, hoặc rằng sidecar và ambient có hành vi policy hoàn toàn giống nhau.

### 5.3. So sánh theo yêu cầu

| Tiêu chí | Sidecar proxy | Ambient/node-level hoặc proxy dùng chung |
|---|---|---|
| Đặt data plane | Thường theo Pod | Node-level và/hoặc proxy L7 dùng chung |
| Chi phí theo số Pod | Có proxy mỗi Pod nên có overhead riêng | Có thể giảm một số chi phí per-Pod nhưng tạo thành phần chia sẻ |
| L7 routing/authorization | Có thể làm ngay tại sidecar nếu tính năng hỗ trợ | Có thể cần waypoint/L7 component riêng |
| Mức cô lập sự cố | Sự cố một sidecar thường gần Pod đó | Component chung có thể có blast radius lớn hơn |
| Onboarding/upgrade | Thường liên quan injection/restart Pods | Có thể ít can thiệp app Pod nhưng cần xử lý datapath/waypoint |
| Bảo mật | Phụ thuộc mTLS enrollment, bypass controls, identity | Phụ thuộc L4 tunnels, route capture và policy coverage |

**Không chọn architecture chỉ vì từ "sidecarless" hoặc "mTLS automatic"**. Kiểm chứng kết nối thật, khả năng quan sát, policy coverage, performance, HA và đường rollback.

## 6. Vấn đề thứ nhất: mã hóa và xác thực giữa các workload

### 6.1. Tại sao HTTPS ở ingress chưa đủ?

~~~text
Browser --HTTPS--> Ingress gateway --HTTP?--> Orders --HTTP?--> Payment

Chứng chỉ browser ↔ gateway chỉ bảo vệ hop đầu.
Các hop phía sau cần một chính sách riêng:
  - TLS/mTLS giữa service peers?
  - Workload identity có được xác minh?
  - Bên nào có quyền gọi service?
~~~

Nếu TLS kết thúc tại ingress rồi backend dùng HTTP, plaintext có thể đi qua mạng nội bộ. Mạng private giúp giảm exposure nhưng **không thay xác thực identity và mã hóa** khi threat model đòi hỏi.

### 6.2. mTLS có gì khác TLS một chiều?

Trong TLS server authentication thông thường, client kiểm tra **chứng chỉ/danh tính của server**. Với **mutual TLS (mTLS)**, mỗi phía còn chứng minh danh tính của mình qua credentials/certificates theo cấu hình. Trong service mesh, các proxy hoặc workload endpoints dùng mTLS để xác nhận **workload peers**.

~~~mermaid
sequenceDiagram
    participant O as Orders proxy
    participant P as Payments proxy
    participant I as Mesh identity / CA
    O->>I: Nhận certificate/trust material cho orders
    P->>I: Nhận certificate/trust material cho payments
    O->>P: TLS handshake + danh tính workload
    P-->>O: Xác minh và chứng minh danh tính peer
    Note over O,P: Hai chiều xác thực và thiết lập traffic keys
    O->>P: Request được bảo vệ bằng mTLS
    P-->>O: Response được bảo vệ bằng mTLS
~~~

Sơ đồ rút gọn: chu kỳ cấp chứng chỉ có thể sử dụng token/identity attestation và các giao thức phân phối riêng. Trong TLS hiện đại, **(EC)DHE giúp thỏa thuận khóa phiên**, **certificate/chữ ký xác thực**, và **AEAD đối xứng bảo vệ records**. Không diễn giải mTLS là hai lần mã hóa độc lập cho toàn bộ payload.

### 6.3. Workload identity: không chỉ là Pod IP

Một workload identity có thể ràng buộc vào Kubernetes ServiceAccount, namespace hoặc attestation mechanism theo mesh. Một dạng URI định danh thường thấy trong hệ sinh thái SPIFFE:

~~~text
spiffe://cluster.local/ns/orders/sa/orders-api
spiffe://cluster.local/ns/payments/sa/payments-api
~~~

Đây là **ví dụ theo quy ước danh tính**, không phải giá trị mặc định của mọi cluster. `cluster.local` ở đây là minh họa trust domain; trong thực tế có thể dùng trust domain khác. SPIFFE ID thường biểu diễn trong **URI SAN** của SVID certificate; **SPIRE** là một hệ thống có thể cấp workload identities/credentials theo mô hình SPIFFE, nhưng **không phải mọi mesh đều cần SPIRE**.

**Tại sao identity hữu ích hơn IP đơn thuần?**

- Pod IP có thể thay đổi khi reschedule và một IP có thể được tái sử dụng.
- Một Service có thể có nhiều replicas.
- Policies theo workload/service account gần với ý nghĩa **ai đang giao tiếp** hơn một địa chỉ động.
- Logs theo identity thuận tiện hơn khi điều tra sự cố xuyên namespace/node.

Tuy nhiên, **ServiceAccount hoặc label do người quản trị cấp không tự miễn nhiễm giả mạo**: nếu attacker có quyền tạo Pod dùng một ServiceAccount có quyền hoặc lấy credentials của nó, mesh identity có thể bị lạm dụng. RBAC, admission, node security và issuer attestation vẫn quan trọng.

### 6.4. Certificate lifecycle là trách nhiệm phải vận hành

Mesh có thể giúp tự động cấp/rotate workload certificates theo cấu hình, nhưng cần kiểm chứng:

1. **Issuer/CA** được bảo vệ bằng chính sách quản trị, khóa ký được bảo vệ đúng mức.
2. Certificate **ngắn hạn hoặc đủ ngắn** so với threat model và có cơ chế rotate tin cậy.
3. **Trust bundle/roots** được phân phối, thay thế và xử lý các giai đoạn CA rotation.
4. Workload bị thu hồi quyền hoặc bị xóa không được tiếp tục dùng credentials ngoài thời gian/chính sách cho phép.
5. **Clock skew, CA outage, control-plane disconnect** có hành vi được dự báo và giám sát.
6. Có quy trình khôi phục **khi mesh CA/private key hoặc workload credentials bị compromise**.

Không nói "mesh tự rotate certificate nên không thể có certificate outage". Mức độ ảnh hưởng phụ thuộc cách cache secret, TTL, SVID issuer, proxy reload và HA.

## 7. Vấn đề thứ hai: định nghĩa ai được gọi ai

mTLS **xác thực peer**, nhưng **xác thực không tự cho phép mọi hành động**. Mesh cần **authorization policy** để quyết định danh tính workload nào được gọi service, trên cổng/phương thức/path nào khi engine hỗ trợ.

### 7.1. Ba tầng cần tách biệt

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **NetworkPolicy / firewall** | Pod/network nào có thể gửi TCP tới destination? | Web → Orders:8080, không vào database |
| **Mesh peer identity / AuthZ** | Service nào với identity xác thực được phép gọi Orders? | `orders-api` chỉ nhận principal của `web` |
| **Application authorization** | User/tenant có được đọc/sửa đơn hàng này không? | User A không được xem order của User B |

Một service có thể được mesh cho phép kết nối mà ứng dụng vẫn phải trả `403` vì user không đủ quyền. Ngược lại, một request có JWT hợp lệ không tự được thông qua mesh nếu nguồn workload không nằm trong danh sách được phép.

### 7.2. Minh họa phân tách trust boundary

~~~mermaid
flowchart LR
    C["Frontend app"] --> NP["L3/L4 CNI NetworkPolicy"]
    NP --> M["Mesh mTLS + service AuthZ"]
    M --> API["Orders API AuthN/AuthZ"]
    API --> DB[("Orders DB permissions")]
    USER["JWT / session của user"] -.-> API
    WORK["Workload identity"] -.-> M
~~~

Một hệ thống an toàn thường cần **cả network reachability, service identity, user identity và data authorization**. Không dùng `source.namespace == "orders"` như bằng chứng user được phép đọc mọi đơn hàng.

### 7.3. L7 authorization không có ở mọi dataplane

Nếu proxy chỉ hỗ trợ **L4** cho một flow, có thể kiểm soát identity/port nhưng không nhìn được HTTP method/path. Muốn cho phép riêng `GET /health` và chặn `POST /admin` cần engine/hop có khả năng **phân tích L7** và policy phù hợp.

Trong ambient mesh, một flow chỉ đi qua L4 secure tunnel **không tự nhận policy L7**. Trong sidecar mesh, traffic không phải HTTP hoặc không được intercept đúng cũng có thể không chịu L7 controls theo ý định.

**Backend application vẫn cần authorization** dù mesh có policy L7; tránh phụ thuộc hoàn toàn vào proxy hoặc header do client gửi.

## 8. Vấn đề thứ ba: điều khiển traffic và triển khai an toàn

Service mesh có thể giúp áp chính sách lưu lượng nhất quán mà không yêu cầu mỗi service viết lại logic kết nối.

| Tính năng | Mục tiêu | Giới hạn/rủi ro |
|---|---|---|
| **Service discovery** | Tìm backend instances theo tên/service | Không tự xác minh peer nếu không có identity/TLS |
| **Load balancing** | Chọn instance khỏe/phù hợp | Cần readiness/health thực, request cost khác nhau |
| **Timeouts** | Không chờ backend vô hạn | Timeout sai có thể cắt request hợp lệ |
| **Retries** | Vượt qua lỗi tạm thời | Có thể làm trùng thao tác và gây retry storm |
| **Circuit breaking** | Hạn chế tài nguyên/kết nối khi backend quá tải | Thiết lập sai có thể tăng rejection khi traffic bình thường |
| **Outlier detection** | Loại tạm thời instance lỗi theo tín hiệu | Có thể loại nhầm nodes và dồn tải nơi khác |
| **Canary/weighted routing** | Đưa một phần traffic sang phiên bản mới | Trọng số không luôn đồng nghĩa tỷ lệ user; kiểm tra statistical sample |
| **Traffic mirroring** | Gửi bản sao request để quan sát/thử nghiệm | Có thể nhân đôi side effects hoặc dữ liệu nhạy cảm nếu không có kiểm soát |
| **Fault injection** | Diễn tập timeout/lỗi trong lab | Cần giới hạn nguồn, thời gian, approval, tránh production impact |

### 8.1. Ví dụ canary không sửa ứng dụng

~~~text
Orders gọi payment.internal:
  Route ổn định -> payment-v1
  Canary subset -> payment-v2

Mục tiêu (minh họa):
  payment-v1: 95% trọng số
  payment-v2:  5% trọng số

Ghi nhận:
  tỉ lệ 5% traffic thực có thể phụ thuộc load, retries,
  connection reuse, sticky policy và số request.
~~~

Tập Pod backend, version labels và route config phải thống nhất với service discovery. Khi backend canary có database schema khác, **đổi route không tự rollback được data schema**. Cần chiến lược backward compatibility, monitoring và rollback cấp ứng dụng.

### 8.2. Retry không thay ứng dụng thiết kế idempotency

Giả sử `POST /payments/charge` đã thực thi giao dịch nhưng response mất trên đường về. Một proxy tự retry request có thể tạo giao dịch thứ hai nếu application không có idempotency. Vì vậy:

- Retry chủ yếu áp cho những hành vi **idempotent/retry-safe** và các lỗi được phân loại rõ.
- Các thao tác thanh toán, chuyển tiền, gửi thông báo hoặc ghi dữ liệu có side effects cần **idempotency key** và deduplication đúng.
- Dùng **retry budget, timeout budget, concurrency limits**, hiểu giới hạn tài nguyên và số lần thử.
- Không cộng quá nhiều tầng retries (client library + mesh + API gateway) nếu không kiểm soát tổng số lần gọi.

### 8.3. Timeout budget của request nhiều hop

Giả sử người dùng có SLO 1 giây cho đường `gateway → orders → inventory`. Nếu mỗi hop được phép timeout 5 giây và retry ba lần, tổng latency có thể vượt SLO dù mỗi service “theo cấu hình”.

Thiết kế tốt thường bắt đầu từ **overall deadline của request**, rồi phân bổ thời gian cho các hop và retries. Mesh có thể thực thi một số deadline/timeout, nhưng application vẫn cần xử lý cancellation, transaction state và partial failure.

## 9. Vấn đề thứ tư: quan sát được đường đi của một request

Một yêu cầu `checkout` có thể gọi các service khác nhau. Nếu chỉ thu CPU/memory và HTTP status của ingress, bạn không biết hop nào gây chậm hoặc timeout.

Service mesh có thể cung cấp telemetry nhất quán:

- **Metrics:** request rate, error rate, latency distribution, connection/handshake failures, policy denials, retries.
- **Access logs:** nguồn/đích, route, response code, upstream instance hoặc danh tính workload theo cấu hình.
- **Distributed traces:** theo dõi các spans của request xuyên service khi ứng dụng/trace context hỗ trợ.
- **Topology/service graph:** hiển thị tập service đang giao tiếp và sự thay đổi luồng theo thời gian.

### 9.1. Ba tín hiệu thường dùng

| Tín hiệu | Câu hỏi | Hạn chế |
|---|---|---|
| **Request rate** | Traffic đang tăng/giảm ở service nào? | Không nói riêng lý do tăng |
| **Error rate** | Tỷ lệ 5xx/timeout/TLS failures là bao nhiêu? | Status code có thể khác giữa proxy và app |
| **Duration/latency** | Hop nào làm tăng p95/p99? | Cần đo theo đường đi và kiểm tra sample size |

Trace tốt có thể cho thấy:

~~~text
Trace checkout-abc (minh họa, không phải dữ liệu thật)
  gateway            320 ms
    orders           290 ms
      inventory       40 ms
      payments       230 ms
        card-provider 200 ms
~~~

**Giới hạn:** proxy có thể tự sinh spans ở một số hop, nhưng distributed tracing thường cần ứng dụng **propagate trace context** để nối spans xuyên request/service. Mesh không tự biết ý nghĩa nghiệp vụ `orderId` hoặc khôi phục ngữ cảnh không được truyền.

### 9.2. Telemetry là dữ liệu cần bảo vệ

Traces/logs có thể chứa service names, namespace, IP, headers, user identifiers và URI. Tránh ghi:

- Authorization bearer tokens, cookies, API keys, client private keys.
- Request/response bodies chứa thông tin thanh toán hoặc dữ liệu cá nhân.
- Secrets hoặc certificate private material từ proxy/control plane.

Thiết kế sampling, retention, phân quyền người xem, masking và encryption. Một mesh quan sát tốt **không có nghĩa nên log mọi payload**.

## 10. Vấn đề thứ năm: áp chính sách nhất quán trên nhiều nhóm phát triển

Đội platform có thể cung cấp policy templates cho mTLS, trusted principals, timeouts, route ownership và logging thay vì để từng nhóm tự tạo thư viện bảo mật.

### 10.1. Ví dụ chính sách mục tiêu

~~~text
Namespace payments:
  - Workloads phải giao tiếp theo mTLS khi mesh hỗ trợ đường đó.
  - Chỉ Orders workload identity được gọi Payment API.
  - Không truy cập payments admin API từ public namespace.
  - Có metrics và audit policy denials.
  - Khi certificate hết hạn hoặc control plane lỗi:
      phải có hành vi đã được kiểm thử, không tự fallback plaintext.
~~~

Một chính sách mesh có thể tập trung, nhưng nếu áp quá rộng mà không hiểu exceptions có thể **cắt traffic hợp lệ**. Ví dụ một workload chưa gia nhập mesh hoặc một probe ngoài mesh có thể không hoàn thành mTLS theo `STRICT` policy.

### 10.2. Policy-as-code đi kèm ownership

Phải có:

1. **GitOps/IaC repo** quản lý policy theo owner/namespace với code review.
2. Quyền **RBAC** hạn chế người tạo/sửa mesh-wide authorization hoặc trust rules.
3. **Admission/validation** để phát hiện selectors trống, allow-all, sai service account, gateway ngoại lệ.
4. **Canary và positive/negative tests** từ source thật để xác minh effective policy.
5. **Drift detection** giữa trạng thái thực và cấu hình đã phê duyệt.
6. Audit cho thay đổi control plane, certificates và quyền truy cập.

Không coi việc một YAML được Kubernetes API chấp nhận là bằng chứng chính sách đã được data plane áp dụng.

## 11. Những ranh giới bảo mật service mesh không tự giải quyết

| Boundary | Mesh giúp được gì? | Vẫn phải làm gì bên ngoài mesh? |
|---|---|---|
| Pod ↔ Pod trên đường được mesh quản lý | mTLS và policy theo workload identity | Kubernetes NetworkPolicy/CNI, host security, admission |
| Service ↔ database bên ngoài mesh | Có thể áp TLS/egress policy theo hỗ trợ | DB TLS/roles, credentials, firewall/private endpoints |
| User ↔ API | Một số mesh gateways có L7 policies | User login, JWT/session, MFA, object/tenant AuthZ |
| Application ↔ localhost/sidecar | Proxy quản lý đường sau khi capture | Container/Pod isolation, process security, secrets |
| HostNetwork/kernel/node | Chỉ theo khả năng datapath cụ thể | Host firewall, kubelet/CRI protection, OS patches |
| Mesh CA/control plane | Cấp identities và cấu hình | CA key protection, IAM/RBAC, audit/HA/backup |
| Cloud VPC/subnets | Có thể thêm identity trong mạng | SG/NSG, private endpoints, DNS, VPN, routing |
| HTTP business logic | Có thể giới hạn method/path khi hỗ trợ | Validate input, AuthZ, idempotency, rate/fraud logic |

### 11.1. Đừng hiểu mTLS giữa proxies là mã hóa đầu-cuối tuyệt đối

Với sidecar model, ứng dụng thường gửi plaintext tới local proxy; proxy gửi mTLS trên đường mạng; proxy đích giải mã rồi chuyển dữ liệu cho ứng dụng đích. **mTLS bảo vệ đoạn giữa các TLS endpoints**, không tự mã hóa dữ liệu đang nằm trong bộ nhớ ứng dụng, logs, volumes hoặc đường app ↔ local proxy.

Nếu proxy chỉ xử lý traffic qua một interface và một luồng có thể **bypass proxy** (direct node/host network, excluded ports, sidecar injection off, workload chưa enrollment), luồng đó có thể không nhận được mTLS/policy của mesh. Cần kiểm thử đường bypass thực tế và đặt **network policy/host firewall** độc lập.

### 11.2. Chính sách authorization có thể không bao phủ toàn bộ traffic

Ví dụ ứng dụng kết nối một database bằng giao thức không phải HTTP. Mesh engine có thể nhận dạng service identity và cổng ở L4 nhưng không hiểu quyền `SELECT` trên bảng nào. Database vẫn cần account, RBAC/roles, TLS và audit.

Một dịch vụ nhận gRPC/HTTP có thể dùng L7 authorization, nhưng quyền ở mesh là quyền **gọi API từ workload**, không thay kiểm tra **user sở hữu resource** trong ứng dụng.

## 12. Service mesh, NetworkPolicy và Zero Trust

**Zero Trust** không chỉ là "bật mTLS". Mục tiêu là **xác minh rõ identity, quyền tối thiểu và hạn chế tin cậy ngầm** trong từng yêu cầu truy cập.

Trong một cluster:

1. **NetworkPolicy** hạn chế Pod nào có thể mở kết nối tới đích nào.
2. **Mesh mTLS** xác thực workload peers và bảo vệ traffic trên những hop nằm trong phạm vi.
3. **Mesh authorization** hạn chế service identities được phép gọi các cổng/API có thể kiểm soát.
4. **Application authorization** kiểm tra user/tenant/resource và business action.
5. **Host/control-plane/IAM** ngăn attacker tự tạo workloads, lấy token hoặc sửa mesh policy.
6. **Telemetry/response** phát hiện bất thường và xử lý compromise/credentials.

### 12.1. Tại sao mTLS alone không đủ?

Giả sử cả `web` và `debug-tool` đều có certificate hợp lệ. Mesh xác minh được cả hai là workload thuộc trust domain. Nếu Payment API chỉ yêu cầu "client có certificate từ mesh CA" mà không kiểm tra **source identity cụ thể**, `debug-tool` cũng có thể kết nối.

**Authenticated ≠ authorized.** Một default-deny ở mesh authorization và allowlist principals phù hợp có thể giảm rủi ro này, nhưng chỉ khi policy đúng đối tượng và không có đường bypass.

### 12.2. Khi workload identity bị chiếm quyền

Nếu attacker chiếm Pod orders, họ có thể sử dụng identity/credentials của orders để gọi payment trong phạm vi được cấp. Mesh không tự nhận biết request đang bị thực hiện trái mục đích bởi một process hợp lệ đã bị compromise.

Vì vậy cần least privilege ở payment API, rate limits, transaction validation, anomaly detection, secret protection, audit và khả năng cô lập/thu hồi workload identity nhanh chóng.

## 13. So sánh: khi nào nên triển khai mesh?

### 13.1. Những điều kiện tăng giá trị

- Hàng chục/hàng trăm service với **quan hệ gọi nhau phức tạp**, nhiều ngôn ngữ và đội sở hữu.
- Có yêu cầu **mTLS/workload identity và authorization nhất quán** giữa nhiều services.
- Cần điều khiển traffic **canary, retries, timeouts** hoặc policy failover ở hạ tầng.
- Thiếu khả năng quan sát **east–west request/flow**, khó phân tích latency hoặc error cascade.
- Có platform team đủ năng lực vận hành **control plane, certificates, data plane versions, HA và observability**.
- Mục tiêu compliance yêu cầu chứng minh **traffic policy và certificate lifecycle** có thể kiểm toán.

### 13.2. Những trường hợp không nên vội vàng

- Chỉ có vài service, ít traffic và các thư viện TLS/observability hiện tại đáp ứng tốt.
- Chưa có căn bản về **Kubernetes RBAC, NetworkPolicy, application AuthZ, CI/CD và monitoring**.
- Không có đội trực/owner, certificate rotation runbook hoặc rollback cho mesh.
- Workloads có phần lớn traffic **không hỗ trợ capture/policy**, host networking hoặc protocol rất đặc biệt.
- Latency/CPU/memory budget quá chặt nhưng chưa đo overhead trong workload thực.
- Nhu cầu chỉ là **public API routing**: API gateway/Ingress có thể phù hợp hơn.

Không có một **ngưỡng số service tuyệt đối** buộc phải dùng mesh. Hãy xây business case bằng vấn đề đã quan sát, độ phức tạp hiện tại, chi phí chấp nhận được và bằng chứng từ pilot.

## 14. Ví dụ thiết kế: orders gọi payments qua service mesh

Giả sử ta có các namespace và ServiceAccounts sau trong một cluster **lab**:

| Workload | Namespace | Kubernetes ServiceAccount | Cổng dịch vụ |
|---|---|---|---|
| Frontend | `edge` | `web` | Gọi Orders |
| Orders API | `orders` | `orders-api` | Nhận 8080 |
| Payments API | `payments` | `payments-api` | Nhận 8080 |
| Debug tool | `sandbox` | `debug-client` | Không được gọi Payments |

Mục tiêu:

1. Frontend được gọi Orders; Orders được gọi Payments.
2. Payments chỉ nhận requests đến từ **identity của Orders**, qua kênh mTLS được mesh kiểm soát.
3. Debug tool, workload không thuộc mesh và client không có identity được phép **không được gọi** Payments qua đường có kiểm soát.
4. Payments vẫn kiểm tra **token, đơn hàng, số tiền, idempotency và quyền user**.
5. TLS ở ingress không che lấp **điểm kết thúc TLS** và mTLS giữa các workloads.

### 14.1. Đường truyền mục tiêu

~~~mermaid
flowchart LR
    USER["Browser"] -->|"HTTPS"| GW["Ingress gateway"]
    GW -->|"Policy cho ingress được xác minh"| O["Orders workload"]
    O -->|"Mesh mTLS + Orders identity"| P["Payments workload"]
    P --> D[("Payments database")]
    DBG["Debug workload"] -.->|"DENY mesh / network policy"| P
    O -.->|"mTLS peer ID + app JWT"| AUT["Service and user authorization"]
~~~

Sơ đồ không khẳng định app → proxy trong cùng Pod được mã hóa; mTLS được đánh giá trên **những hop giữa các mesh endpoints**, phụ thuộc mô hình sidecar/ambient và ứng dụng thật.

### 14.2. Istio `PeerAuthentication`: yêu cầu mTLS cho workload được chọn

Ví dụ cấu hình **Istio** minh họa khái niệm (không phải policy Kubernetes NetworkPolicy chuẩn):

~~~yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: payments-mtls-strict
  namespace: payments
spec:
  selector:
    matchLabels:
      app: payments-api
  mtls:
    mode: STRICT
~~~

Trong môi trường Istio/phiên bản hỗ trợ tài nguyên này, cấu hình yêu cầu mTLS cho inbound traffic tới **workloads được chọn** theo semantics của Istio.

**Điều cần kiểm chứng:**

- `app=payments-api` thực sự chọn đúng workload Pods/route.
- Workload đã tham gia đúng mô hình dataplane và certificates được cung cấp.
- Traffic từ legacy client **không có mesh mTLS** có thể bị chặn, tạo outage nếu chưa có lộ trình migration.
- Port exemptions, gateways, sidecar/ambient mode và native TLS trong ứng dụng cần review.
- `STRICT` là điều kiện về **transport peer authentication**, không có nghĩa mọi mesh identity được phép gọi Payment API.
- Thêm policy vào cluster **không đủ** để chứng minh toàn bộ đường mạng không có direct bypass.

Trong ví dụ, không hướng dẫn triển khai trên production khi chưa có canary, ownership và policy coverage.

### 14.3. Istio `AuthorizationPolicy`: cho phép đúng service identity

Ví dụ **lựa chọn một nhóm workload** payments và cho phép principal Orders trên cổng 8080:

~~~yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: payments-from-orders
  namespace: payments
spec:
  selector:
    matchLabels:
      app: payments-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/orders/sa/orders-api
      to:
        - operation:
            ports:
              - "8080"
~~~

Điểm cần đọc đúng:

- `selector` nhắm tới workload nhận traffic, **không** tự chọn source Pods.
- `source.principals` trong ví dụ kỳ vọng **identity đã xác thực qua mTLS**, không phải HTTP header do client tự gửi.
- `cluster.local` là trust domain **giả định**. Trong môi trường thực phải thay bằng identity/principal thực tế và xác minh trust domain, SAN/SPIFFE cùng namespace/ServiceAccount.
- `action: ALLOW` thể hiện allow policy cho scope tương ứng; **effective authorization** còn phụ thuộc các chính sách khác (ví dụ Istio DENY, CUSTOM, ALLOW policies), version, proxy mode và evaluation order của sản phẩm.
- `ports: ["8080"]` không xác định HTTP business endpoint nào được phép; Payments API **vẫn phải xác minh quyền nghiệp vụ**.
- Nếu ServiceAccount Orders bị chiếm quyền, attacker có thể sở hữu identity đã được phép; phải có app AuthZ, controls và audit bổ sung.

**Đặc biệt:** các công cụ service mesh có API, CRDs và precedence khác nhau. **Không** sao chép YAML Istio rồi mong Linkerd, Consul hoặc một CNI NetworkPolicy hiểu cùng fields.

### 14.4. NetworkPolicy bổ sung, không thay policy Istio

Một ví dụ Kubernetes `NetworkPolicy` cho Payments có thể giới hạn **network reachability** từ Pod Orders ở namespace `orders` tới Pod Payments trên port 8080:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-ingress-from-orders
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: payments-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 8080
~~~

**Cảnh báo quan trọng:** đây là một **mô hình logic dành cho Pod-to-Pod datapath tương ứng**, không phải policy khẳng định tương thích nguyên trạng với tất cả mesh modes. Khi mesh dùng **sidecar interception, port remapping, ambient ztunnel/HBONE, waypoint hoặc gateway**, địa chỉ nguồn/đích, port và nơi enforcement có thể khác. **Kiểm tra hướng dẫn CNI/mesh và test đường thực** trước khi áp. Policy này cũng không tự cấp egress từ Orders nếu Orders đã bị Egress-isolated.

Một chính sách `NetworkPolicy` dựa label **không phải danh tính mật mã**; người có quyền tạo Pod và gắn nhãn tin cậy cần được kiểm soát qua RBAC/admission.

### 14.5. Bài học từ ví dụ

| Kiểm soát | Điều bảo vệ | Phần không bảo vệ |
|---|---|---|
| NetworkPolicy Ingress | Hạn chế nguồn/cổng ở mạng Pod theo datapath được hỗ trợ | Không xác minh cert/user/token |
| Istio PeerAuthentication | Yêu cầu mTLS inbound theo scope | Không chỉ định service nào được phép về mặt nghiệp vụ |
| Istio AuthorizationPolicy | Hạn chế workload identity/operation theo policy engine | Không kiểm tra business order ownership |
| Payments API AuthZ | Kiểm tra user/tenant/order/idempotency | Không tự chặn mọi port/host route vào cluster |
| Firewall/IAM/PSA | Kiểm soát host, quyền tạo workload và trust boundaries khác | Không thay TLS application-level |

## 15. Ví dụ khái niệm: định tuyến traffic canary

Giả sử Service `orders-api.orders.svc.cluster.local` có hai subset ứng dụng `version=v1` và `version=v2`. Với một **Istio dataplane có L7 routing**, cách khai báo **minh họa** có thể gồm `DestinationRule` để định nghĩa subsets và `VirtualService` để chuyển trọng số:

~~~yaml
# Chỉ dùng cho bài học/lab có Istio CRDs và workloads phù hợp.
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: orders-subsets
  namespace: orders
spec:
  host: orders-api.orders.svc.cluster.local
  subsets:
    - name: stable
      labels:
        version: v1
    - name: canary
      labels:
        version: v2
---
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: orders-canary
  namespace: orders
spec:
  hosts:
    - orders-api.orders.svc.cluster.local
  http:
    - route:
        - destination:
            host: orders-api.orders.svc.cluster.local
            subset: stable
          weight: 95
        - destination:
            host: orders-api.orders.svc.cluster.local
            subset: canary
          weight: 5
~~~

Đọc đúng điều kiện:

1. `DestinationRule` chọn tập endpoints dựa trên label `version`; Service và Pod labels phải tồn tại.
2. `VirtualService` chọn route destinations cho HTTP traffic được mesh xử lý; **không có tác dụng nếu traffic không qua L7 data plane tương ứng**.
3. Trọng số là mục tiêu phân phối trong chính sách, **không bảo đảm đúng 5% người dùng** trong mọi cửa sổ, đặc biệt khi sample nhỏ hoặc có connection affinity/retries.
4. Canary cần **cùng chính sách AuthN/AuthZ, quản lý Secret và phân tách tenant** như stable.
5. Mẫu không thể áp trực tiếp vào một **ambient L4-only path** rồi kỳ vọng tự có phân phối HTTP L7.
6. Cấu hình production còn phải kiểm soát rollout, health, retries, timeouts, dữ liệu và quyền sửa routing.

### 15.1. Mẫu Canary không nên dùng để chuyển quyền

Không route mọi request có header `X-Canary: true` sang một backend có debug endpoint, quyền DB rộng hoặc configuration thiếu authorization; client có thể tự gửi header. Nếu cần canary theo cohort, nguồn đánh dấu phải được **xác thực hoặc tạo tại trusted gateway** và backend vẫn phải kiểm tra quyền.

### 15.2. Thế nào là rollback thành công?

Rollback traffic weight từ v2 về v1 chỉ là **network-level traffic rollback**. Để thật sự khôi phục sản phẩm cần:

- Phiên bản ứng dụng cũ vẫn tương thích database schema.
- Không có data migration không thể đảo ngược.
- Không giữ các sessions/long-lived connections sai phiên bản ngoài chủ đích.
- Lỗi latency, 5xx, auth denials và traffic distribution trở về mức chấp nhận được.

## 16. Các đánh đổi kỹ thuật phải tính trước

### 16.1. Performance và tài nguyên

Service mesh có thể thêm:

- **CPU/RAM** của sidecar hoặc proxy chia sẻ, đặc biệt khi traffic lớn.
- **Độ trễ xử lý**, TLS handshakes, routing lookups, retries/tracing.
- **Network hops** hoặc đường tunnel khác so với Pod-to-Pod trực tiếp.
- **Metrics/logs/traces** với chi phí cardinality/storage đáng kể.
- **Capacity của control plane/CA** để phân phối config và certificates.

Không mặc định mesh luôn làm chậm hơn một tỷ lệ cố định: ảnh hưởng phụ thuộc kiến trúc sidecar/ambient, proxy version, workload CPU, connection reuse, TLS hardware, request size và telemetry sampling.

Các chỉ số nên đo trong pilot:

| Chỉ số | Khi đo | Lý do |
|---|---|---|
| p50/p95/p99 latency | Trước/sau mesh và trong peak | Phát hiện overhead hoặc tail latency |
| CPU/RSS memory per Pod/node | Idle, load bình thường, tải cao | Capacity planning và OOM |
| TCP/TLS connection churn | Cold start, rollout, reconnect | Tác động handshake/certificate |
| Request success/5xx/reset | Stable/canary/error scenarios | Mức độ ổn định |
| Retry rate/budget | Backend lỗi và tải bình thường | Nguy cơ khuếch đại lưu lượng |
| Config propagation/convergence | Khi thay policy/cert | Độ trễ áp dụng và drift |
| Proxy/control-plane availability | Node failure, upgrade, CA outage | Blast radius và HA |
| Telemetry storage/cost | Trong 7–30 ngày mẫu | Chi phí và retention |

Không cần đưa một benchmark giả định thành **số liệu cam kết sản phẩm**. Hãy đo trên cluster/workload cụ thể.

### 16.2. Tính tương thích ứng dụng

Những trường hợp cần thử kỹ:

- gRPC, WebSockets, streaming, long-lived connections, database protocols và raw TCP.
- Port dùng để startup probes, readiness probes hoặc health checks.
- Ứng dụng tự terminate TLS hoặc yêu cầu client certificate riêng.
- Traffic tới localhost, loopback, hostNetwork, Unix sockets và named ports.
- Multi-network interfaces, Pod-to-VM, on-premises, external SaaS, DNS đặc biệt.
- HTTP/2, HTTP/3/QUIC khi mesh/gateway hỗ trợ; không suy TCP proxy tự bắt mọi UDP traffic.
- Startup/shutdown sequencing và graceful drain khi Pod bị terminate.
- Chu kỳ upgrade, sidecar injection failure, ambient enrollment failure và rollbacks.

Một mesh có thể giúp nhiều HTTP services nhưng không nhất thiết phù hợp cho mọi giao thức/routing path.

### 16.3. Blast radius của control plane và policy

Control plane có thể phân phối policy ảnh hưởng **hàng trăm workloads**. Một cấu hình sai như yêu cầu `STRICT` mTLS trên các service legacy chưa vào mesh, hoặc thay CA/trust bundle không đồng bộ, có thể làm nhiều kết nối cùng lúc thất bại.

Do đó cần HA, phân quyền, canary, review, progressive delivery, audit, cơ chế rollback và một **break-glass process** có giới hạn, không mở mesh-wide allow-all khi gặp sự cố.

## 17. Threat modeling: 20 tình huống dễ mắc

| ID | Rủi ro | Kịch bản | Cách giảm thiểu |
|---|---|---|---|
| M01 | **mTLS chưa bao phủ mọi workload** | Một số Pod không được mesh capture vẫn dùng HTTP | Inventory enrollment, mesh config, negative traffic tests |
| M02 | **Nhầm TLS ở ingress với nội bộ** | Gateway HTTPS nhưng backend plaintext | Hop-by-hop diagram, kiểm tra mTLS thực |
| M03 | **Chỉ bật mTLS mà không authorization** | Mọi service có cert đều gọi Payment API | Default-deny identity policies, allowlist principals |
| M04 | **Quyền app/tenant thiếu** | Workload được phép đọc đơn hàng của user khác | App AuthZ, object-level checks, DB roles |
| M05 | **Workload identity bị lộ** | Token/ServiceAccount credentials bị lạm dụng | RBAC, node isolation, credential rotation, anomaly detection |
| M06 | **CA/issuer compromise** | Khóa CA cấp identity sai hoặc CA bị chiếm | HSM/KMS khi phù hợp, root protection, incident rotation |
| M07 | **Certificate hết hạn/rotation lỗi** | Nhiều services đồng thời mất mTLS | Alerts, CA HA, expiry/rotation tests |
| M08 | **Control plane config bị thay** | Attacker đổi route/authorization | RBAC, GitOps approval, audit, admin endpoint protection |
| M09 | **L7 policy đặt ở L4-only path** | Nghĩ cấm HTTP `/admin` nhưng không waypoint | Coverage validation, appropriate L7 enforcement |
| M10 | **Direct proxy bypass** | HostNetwork/port exemption không qua mesh | CNI NetworkPolicy, host firewall, admission |
| M11 | **Retry storm** | Client, gateway và mesh cùng retry | Budget, overall deadline, idempotency, load tests |
| M12 | **Duplicate side effects** | Retry `POST /payments` tạo hai giao dịch | App idempotency key, retry-safe policy |
| M13 | **Circuit breaking quá chặt** | Proxy từ chối request hợp lệ lúc peak | Canary thresholds, adaptive capacity, SLO |
| M14 | **Canary thiếu AuthZ** | Traffic thử vào backend quyền rộng | Policy parity, staged release checks |
| M15 | **Gateway/mesh identity confusion** | Backend tin client-supplied headers là identity | Trusted proxy identity, overwrite headers, user AuthZ |
| M16 | **Cross-namespace policy nhầm** | Selector rộng ảnh hưởng nhầm nhiều services | Ownership, selector lint, negative tests |
| M17 | **Mesh egress không kiểm soát** | Workload vẫn gọi public SaaS trực tiếp | Egress gateway/firewall policy và runtime path tests |
| M18 | **Telemetry lộ dữ liệu nhạy cảm** | Trace/log ghi token hoặc PII | Redaction, role access, sampling, retention |
| M19 | **CNI/service mesh policy mâu thuẫn** | NetworkPolicy chặn proxy port/HBONE/DNS | Joint design, CNI-aware tests, flow verdict |
| M20 | **Upgrade/HA control plane chưa kiểm thử** | Proxy mất config/cert khi node hoặc CA lỗi | Upgrade canary, failover, backup, recovery exercises |

### 17.1. Một chuỗi lỗi không cần attacker

~~~mermaid
flowchart TD
    A["Bật mesh mTLS STRICT cho Payments"] --> B["Một client cũ không tham gia mesh"]
    B --> C["Client không có mTLS peer identity hợp lệ"]
    C --> D["Kết nối tới Payments bị từ chối"]
    D --> E["Orders hoặc job phụ trợ báo 503 / timeout"]
    E --> F["Client/gateway retry"]
    F --> G["Tăng tải và kéo dài thời gian phục hồi"]
~~~

Bài học là **chính sách bảo mật đúng nhưng triển khai thiếu kiểm kê vẫn có thể gây sự cố availability**. Trước khi chuyển sang `STRICT`, phải biết clients nào chưa có identity hoặc chưa tham gia mesh; quản trị giai đoạn chuyển đổi và điểm chấp nhận rủi ro.

### 17.2. Lúc bị compromise, service mesh giúp đến đâu?

Nếu một frontend Pod bị xâm nhập, service mesh có thể giảm những nơi mà identity của frontend được phép gọi. Nhưng:

- Attacker vẫn có thể gọi **API được allow** với lượng request bất thường.
- Nếu frontend dùng token của người dùng, app cần phân quyền và chống gian lận.
- Nếu control plane hoặc CA bị compromise, attacker có thể tác động tới nhiều services.
- Mesh không xóa được dữ liệu đã bị lộ hoặc thay secrets đã bị đánh cắp.

**Containment cần cả mesh authorization, NetworkPolicy/firewall, IAM, secrets rotation và application safeguards**.

## 18. Ma trận kiểm thử positive/negative

Các phép thử dưới đây dùng cho **cluster lab hoặc môi trường được cấp phép**, với workloads có thật và policy đã được review. Không dùng lỗi kết nối đơn độc làm bằng chứng; đối chiếu trạng thái backend, CNI flow, mesh proxy/identity logs và API authorization.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | Orders hợp lệ → Payments với mTLS | Thành công qua đúng mesh path | Proxy peer identity, handshake, request logs |
| N01 | Debug client không được phép → Payments | Bị chặn bởi mesh AuthZ/network policy | AuthZ deny, source principal |
| N02 | Workload ngoài mesh → Payments khi mTLS STRICT | Bị từ chối đúng policy | TLS peer/auth failure |
| P02 | Frontend được phép → Orders | Thành công, đúng route/auth | CNI + mesh + app trace |
| N03 | Frontend trực tiếp → Payments | Không được phép | Identity/network deny evidence |
| P03 | Payments trả 403 với user không có quyền | Transport có thể thành công, **app AuthZ deny** | App logs/tenant decision |
| N04 | Source tự gửi header "trusted-service" | Không nâng được workload identity | mTLS principal khác header |
| P04 | Certificate được rotate bình thường | Kết nối mới duy trì trong SLO | Cert age/trust/handshake metrics |
| N05 | Certificate/CA không tin cậy trong lab | TLS peer validation từ chối | Proxy TLS/cert errors |
| N06 | Payment workload chưa được mesh capture | Phát hiện thiếu coverage trước rollout | Enrollment/config/path inspection |
| N07 | Mesh policy selector chọn nhầm Pod | Test/alerts phát hiện before production | Labels, effective config và probe |
| P05 | Canary 95/5 dưới tải mẫu đủ lớn | Phân phối gần mục tiêu theo điều kiện đã định | Route metrics/backend traces |
| N08 | Canary v2 lỗi vượt ngưỡng | Rollback theo tiêu chí an toàn | SLO, config version và rollback logs |
| N09 | Retry non-idempotent POST | Không tạo giao dịch trùng | App idempotency/dedup logs |
| P06 | Backend tạm lỗi trên retry-safe GET | Retry theo budget, không storm | Retry counts, latency, limits |
| N10 | Timeout chain vượt global deadline | Fail có kiểm soát, không retry vô hạn | Distributed trace/deadline |
| P07 | Workload từ namespace được phép | Policy và identity đúng | mTLS principal, policy verdict |
| N11 | ServiceAccount/namespace khác gọi cùng API | Bị từ chối theo intended scope | AuthZ deny và RBAC |
| N12 | Traffic bypass sidecar/ztunnel có thể có | Bị chặn/ghi nhận bởi lớp độc lập | CNI/host firewall và flow tests |
| P08 | Service mesh telemetry enabled | Có request rate, errors, duration | Metrics/traces theo service |
| N13 | Trace chứa token hoặc PII | Logging/redaction policy loại bỏ dữ liệu | Sanitized sample và privacy audit |
| N14 | Control plane tạm mất kết nối | Data-plane behavior đúng runbook và cache/TTL | Fault-injection lab, proxy status |
| N15 | CNI default-deny áp dụng cùng mesh | Không chặn nhầm kênh/proxy hợp lệ | Flow verdict + app success |
| P09 | Sidecar/ambient upgrade canary | Không mất mTLS, không vượt latency budget | Proxy version, error rate, SLO |
| N16 | Public direct backend bypass | Không đi vòng qua mesh AuthZ | Firewall/private ingress tests |
| N17 | Node/host API/CRI accessible ngoài policy | Bị chặn bởi host/control-plane defenses | Host ACL/audit |

**Không phải mọi test được kỳ vọng cùng một cách từ chối.** Một kết nối bị cắt bởi NetworkPolicy khác với `403` do application AuthZ; một TLS alert vì certificate sai khác với `503` do upstream unavailable. Logs cần nêu **điểm quyết định thật**.

## 19. Quan sát chỉ đọc và troubleshooting

### 19.1. Kiểm tra Kubernetes và mesh enrollment

Ví dụ sau **chỉ đọc** và cần kubeconfig/permission phù hợp:

~~~bash
# Xác nhận context trước khi quan sát.
kubectl config current-context

# Xem Pod và labels ở những namespace giả định.
kubectl get pods -n orders --show-labels
kubectl get pods -n payments --show-labels
kubectl get pods -n payments -o wide

# Xem ServiceAccount liên quan; không in tokens/Secret values.
kubectl get serviceaccounts -n orders
kubectl get serviceaccounts -n payments

# Nếu cluster sử dụng Istio và các CRD đã cài:
kubectl get peerauthentication -A
kubectl get authorizationpolicy -A
kubectl get virtualservice -A
kubectl get destinationrule -A

# NetworkPolicy là lớp độc lập.
kubectl get networkpolicy -n payments
~~~

**Các lệnh trên không xác nhận mTLS đang chạy.** Chúng hiển thị metadata/policies được API server lưu, có thể chỉ một phần do RBAC. Cần xem **effective proxy config, peer identity và traffic tests** trong phạm vi công cụ/platform được cấp phép.

### 19.2. Kiểm tra traffic thật bằng ba góc nhìn

Đối với request `orders → payments`, đối chiếu:

1. **Application:** Orders gọi endpoint/port nào, trace/request ID và lỗi nghiệp vụ là gì?
2. **Mesh data plane:** route nào được chọn, peer identities có được xác minh, TLS/authorization verdict, retry/timeout bao nhiêu?
3. **Network & service:** DNS/Service endpoints, CNI flow verdict, Pod health, ingress/egress gateways và cloud firewall.

**Nếu chỉ nhìn `kubectl get peerauthentication`, bạn chưa biết request đang qua proxy hay có bypass.** Nếu chỉ nhìn `HTTP 200`, bạn cũng chưa chứng minh request được bảo vệ bằng mTLS.

### 19.3. Bảng chẩn đoán nhanh

| Triệu chứng | Khả năng cần kiểm tra | Cách phân biệt |
|---|---|---|
| Sau khi bật `STRICT` mTLS, một client lỗi | Client chưa trong mesh, TLS identity mismatch | Mesh enrollment, peer cert/handshake logs |
| mTLS thành công nhưng request `403` | Mesh AuthorizationPolicy hoặc app AuthZ | Decision point, principal, HTTP error source |
| Lỗi `503` nhiều hơn sau canary | Backend v2 không healthy, config route/subset sai | Service endpoints, proxy route, workload health |
| Service vừa chuyển Pod IP và không kết nối | Discovery lag, stale endpoints, CNI, DNS | EndpointSlice/service and proxy config |
| DNS fail sau default-deny | NetworkPolicy chưa cho DNS/NodeLocal | Resolver path, CNI flow |
| Canary chỉ nhận traffic một vùng | Gateway/mesh config drift, traffic distribution | Region, proxy version, route metrics |
| p99 latency tăng nhưng CPU app ổn | Proxy overhead, retry/connection queue | Tracing, proxy metrics, CPU/memory |
| Một long-lived connection không đổi route | Connection reuse hoặc policy convergence | New vs existing sessions |
| Chỉ Pod `hostNetwork` không được mTLS | Traffic chưa vào dataplane hoặc unsupported path | Host/CNI path, mesh capture |
| Traces bị đứt giữa hai service | Context propagation hoặc tracing sampling | Trace headers, SDK/proxy spans |
| Sidecar thiếu certificate khi CA không healthy | Certificate rotation/control-plane issue | CA logs, cert expiry, proxy status |
| App tự có HTTPS và mesh cũng TLS | Double TLS/nested TLS hoặc port capture mismatch | TLS endpoint diagram, client config |
| HTTP/3/UDP kết nối không áp policy | Data plane/gateway không capture protocol đó | Protocol/transport-specific tests |

### 19.4. Không xử lý outage bằng những lối tắt nguy hiểm

Không:

- Đổi toàn cluster sang `PERMISSIVE` rồi quên bật lại strict mTLS.
- Xóa toàn bộ AuthorizationPolicy hoặc tạo mesh-wide allow-all để vượt `403`.
- Bỏ TLS certificate verification để vượt lỗi CA/SAN.
- Đặt NetworkPolicy `egress: - {}` để vượt lỗi DNS/proxy mà không hiểu blast radius.
- Ghi token/private key vào log để "debug mTLS".

Hãy sửa **đúng ranh giới lỗi**, dùng một exception có scope/time owner nếu thực sự cần, rồi kiểm thử hồi quy sau sửa.

## 20. Quy trình triển khai service mesh theo từng giai đoạn

### Bước 1 — Xác định vấn đề cần giải quyết và đo baseline

Ghi các tuyến service-to-service, tỷ lệ plaintext, tỷ lệ timeout/retry, latency p95/p99, số lần incident liên quan cert, khả năng điều tra logs/traces, số nhóm cần phối hợp và yêu cầu compliance. Nếu giải pháp khác rẻ hơn/đủ tốt, ghi nhận thay vì cài mesh theo phong trào.

### Bước 2 — Inventory dependencies và trust boundaries

Vẽ ingress gateway, services, databases, DNS, public/private cloud APIs, SaaS, on-prem, VPN, hostNetwork, egress gateways, CI/control plane và các đường kết nối ngoài mesh. Đánh dấu **điểm TLS termination**, CA trust domains, ServiceAccounts, namespace ownership và ai có thể sửa labels/policies.

### Bước 3 — Pilot trên một nhóm workload nhỏ

Chọn hai hoặc ba service có traffic đại diện và rõ owner. Bật enrollment/capture, xác thực peer identity, TLS behavior, timeout/telemetry và kiểm thử performance. Chưa bật mTLS STRICT trên toàn namespace có clients legacy chưa được kiểm kê.

### Bước 4 — Kiểm soát certificates và identity

Thiết lập CA/trust bundle, issuer permissions, short-lived identities, RBAC/ServiceAccount ownership, TLS validation, rotation/CA outage handling và audit. Kiểm thử cả valid identity và unknown identity từ nguồn đã được phê duyệt trong lab.

### Bước 5 — Áp authorization theo least privilege

Với mỗi service nhạy cảm, ghi `source identity → destination service → allowed operation/port`. Bật mesh AuthZ trong scope kiểm soát, test negative từ sai namespace/SA. Giữ app-level JWT/tenant AuthZ và NetworkPolicy/firewall.

### Bước 6 — Điều khiển traffic có SLO

Chọn timeouts/retries sau khi hiểu idempotency và overall deadline. Canary thay đổi từng phần, theo dõi latency, errors, retry rate, resource overhead và backend health. Dùng circuit breaking/fault injection trong lab với scope rõ.

### Bước 7 — Rollout theo từng namespace/service

Version hóa configs, có approval/canary, theo dõi CNI và mesh dataplane coverage, rollback per-service thay vì mesh-wide bypass. Kiểm tra workloads chưa migrate, egress ngoài cluster và sự tương thích của giao thức.

### Bước 8 — Vận hành lâu dài

Theo dõi trust root/cert expiry, control plane/proxy versions, policy changes, mTLS failures, workload identity drift, trace completeness, retries và costs. Có runbook khi CA/key compromise, loss of control plane, dataplane upgrade, mesh gateway failure và tenant isolation issue.

## 21. Bài tập tình huống: hệ thống có mTLS nhưng vẫn không an toàn

**Bối cảnh giả định:** một cluster Kubernetes có `orders`, `payments` và `analytics`. Đội platform triển khai một mesh, cấp certificates tự động và bật mTLS giữa phần lớn workloads. Sau đó xảy ra hai sự cố:

1. `analytics` có certificate workload hợp lệ trong cùng trust domain và vẫn gọi được API thanh toán, dù không có lý do nghiệp vụ.
2. Khi Payment API chậm, client orders và sidecar đều retry `POST /charge`; một số giao dịch bị tạo hai lần.

Đội quản lý kết luận "mTLS đã bật nên vấn đề chắc do mesh không an toàn". Hãy phân tích:

| Câu hỏi | Điểm cần xem |
|---|---|
| mTLS đã làm đúng công việc gì? | Bảo vệ transport và xác minh peer trong phạm vi |
| Vì sao analytics có thể gọi payment? | Authenticated nhưng thiếu/misconfigured authorization |
| NetworkPolicy có ích gì? | Chặn đường network không cần thiết theo CNI |
| Vì sao hai giao dịch được tạo? | Retry layers, thiếu idempotency/transaction semantics |
| Mesh có thể nhìn thấy user nào đang thanh toán không? | Tùy tích hợp JWT/L7, nhưng backend vẫn cần app AuthZ |
| Nếu bật STRICT ngay toàn cluster thì sao? | Legacy/non-enrolled clients có thể mất kết nối |
| Nếu CA/mesh control plane lỗi? | Cert rotation, cached config, HA và recovery behavior |
| Nếu có một Pod không qua proxy? | Inventory enrollment/bypass, NetworkPolicy/host firewall |

### 21.1. Lời giải tham khảo

- mTLS **không thất bại** chỉ vì một principal không đúng nghiệp vụ vẫn có certificate hợp lệ. Cần định nghĩa **ALLOW theo workload identity** cho Orders và deny analytics theo effective policy.
- Không nên dùng `source.namespace=orders` như quyền xử lý mọi payment record; backend phải kiểm tra user/tenant/order/amount và role.
- CNI NetworkPolicy nên giảm network reachability tới Payment API, nhưng không thay mesh AuthZ vì labels có thể bị sửa bởi principal đủ quyền và không tạo identity cryptographic.
- Retry `POST /charge` phải bị chặn hoặc được kiểm soát bởi idempotency key, deduplication và rõ ràng chính sách retry ở client/gateway/mesh.
- Rollout cần đo mTLS coverage thực tế, cert/trust lifecycle, overhead và kiểm thử đường lỗi/ngoài mesh.

**Bài học kiến trúc:** **mTLS trả lời "ai đang giao tiếp qua kênh được bảo vệ?"**; mesh authorization trả lời "workload đó có được gọi service này không?"; application authorization trả lời "người dùng/nghiệp vụ này có quyền thực hiện thao tác trên tài nguyên này không?".

## 22. Checklist: trước khi quyết định hoặc triển khai service mesh

- [ ] Có bài toán cụ thể về east–west security, routing, resilience hoặc telemetry chưa được giải quyết hiệu quả.
- [ ] Phân biệt service mesh với API gateway, Ingress/HTTPRoute, Service discovery và NetworkPolicy.
- [ ] Vẽ data flow với **TLS endpoints** và các đường ngoài mesh.
- [ ] Biết data plane nào xử lý traffic thật và control plane nào phân phối policy/certificate.
- [ ] Đã so sánh sidecar với ambient/node-level theo tính năng L4/L7, overhead và blast radius.
- [ ] Workload enrollment/mTLS coverage được xác minh từ traffic thực, không chỉ nhìn YAML.
- [ ] Xác định trust domain, CA issuer, SVID/certificate lifecycle, rotation và recovery.
- [ ] Phân biệt TLS/mTLS peer authentication, mesh AuthZ và application AuthZ.
- [ ] Workload identities/ServiceAccounts có least privilege và quyền tạo Pod/sửa labels được kiểm soát.
- [ ] Các service nhạy cảm có allowlist principals cụ thể; không chỉ trust toàn mesh CA.
- [ ] Có NetworkPolicy/CNI và cloud/host firewall bổ sung, không dựa hoàn toàn vào mesh.
- [ ] Đánh giá traffic hostNetwork, DNS, databases, external SaaS, service mesh gateways và bypass paths.
- [ ] L7 policies chỉ được kỳ vọng khi dataplane hỗ trợ và traffic thực sự đi qua L7 enforcement.
- [ ] Retry/timeout budgets dựa vào overall deadline và nghiệp vụ idempotent.
- [ ] Không dùng canary/route để nới quyền hoặc đưa client vào backend debug.
- [ ] Có metrics, traces, logs theo source/destination identity, route, errors và policy verdict.
- [ ] Telemetry không lộ tokens, request bodies nhạy cảm, private keys hoặc thông tin tenant ngoài quyền.
- [ ] Đã đo CPU/memory, latency p95/p99, connection churn, retry rate và chi phí telemetry.
- [ ] Đã thử long-lived connections, streaming, gRPC, probes, mesh upgrades và non-HTTP protocols.
- [ ] Có positive/negative tests cho trusted/untrusted identities, TLS invalid, mTLS strict và app AuthZ.
- [ ] Có kế hoạch rollout dần, rollback riêng từng service và không mở mesh-wide allow-all.
- [ ] Kiểm soát mesh control plane/CA bằng RBAC, audit, backups và incident response.
- [ ] Đã thử tình huống CA/control-plane unavailable, certificate rotation và policy convergence.
- [ ] Có owner, runbook, change review và quy trình rà soát policy khi thêm service/namespace.
- [ ] Chỉ quyết định triển khai mesh khi lợi ích đo được xứng với độ phức tạp và chi phí vận hành.

**Ghi nhớ:** **Service mesh giải quyết bài toán quản lý giao tiếp giữa nhiều workload theo chính sách thống nhất**: xác thực/mã hóa bằng mTLS, service-to-service authorization, traffic routing/resilience và observability. Nhưng nó **không tự bảo vệ các luồng ngoài phạm vi dataplane, không thay CNI/firewall/Kubernetes RBAC, và không thay application authentication/authorization hoặc idempotency**. Triển khai hiệu quả phải bắt đầu từ **threat model, ownership, kiểm chứng đường đi thật, cấu hình ít quyền, đo overhead và rollout có khả năng khôi phục**.
