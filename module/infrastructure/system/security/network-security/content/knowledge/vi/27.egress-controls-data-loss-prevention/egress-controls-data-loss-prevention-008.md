# Giới hạn upload từ workload: kiểm soát egress và chống thất thoát dữ liệu

## 1. Vì sao upload từ workload là một ranh giới bảo mật quan trọng?

Một workload trên Kubernetes, máy ảo, nền tảng serverless hay hệ thống CI/CD có thể gửi dữ liệu ra ngoài để hoàn tất công việc hợp lệ: tải artifact lên kho lưu trữ, đồng bộ bản sao lưu, gửi telemetry, cập nhật dữ liệu tới đối tác hoặc đẩy kết quả xử lý lên object storage. Nhưng cùng một khả năng **upload** cũng có thể bị lạm dụng: gửi thông tin khách hàng sang tài khoản cloud không thuộc tổ chức, làm rò secrets qua HTTP request, đưa database dump ra một dịch vụ chia sẻ file, hoặc chuyển dữ liệu sang đích ngoài phạm vi được phê duyệt.

**Giới hạn upload từ workload** không đơn thuần là đặt **giới hạn kích thước file**. Đây là một tập hợp chính sách xác định:

1. **Workload nào** được phép gửi dữ liệu ra ngoài?
2. **Loại dữ liệu nào** được xuất khỏi trust boundary?
3. **Đích nào** được phép nhận và ai sở hữu đích đó?
4. **Giao thức, đường truyền và thao tác nào** được phép thực hiện?
5. **Khối lượng/tốc độ/tần suất** upload nằm trong giới hạn nghiệp vụ nào?
6. **Ai phê duyệt ngoại lệ**, log gì, giám sát thế nào và có thể chặn/thu hồi khi phát hiện bất thường không?

Trong module **SECURITY_NETWORK_SECURITY**, chủ đề này kết nối **network segmentation, firewall, IDS/IPS, proxy, TLS/mTLS, DNS, Zero Trust Network Access, bảo mật mạng cloud, phân tích flow logs, threat modeling và data loss prevention (DLP)**. Các lớp mạng làm giảm đường thoát dữ liệu, còn **identity và policy ở mức ứng dụng/dữ liệu** quyết định liệu một upload có được phép hay không.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **egress allowlist, network byte quota, L7 upload policy, DLP content inspection, object-level IAM** và hạn mức nghiệp vụ.
- Mô hình hóa **workload identity → đích → dữ liệu → hành động upload** thay vì chỉ dựa trên source IP.
- Giải thích vì sao **HTTPS/TLS, proxy, NAT, DNS, multipart uploads, signed URLs, gRPC streams và QUIC** làm kiểm soát upload phức tạp.
- Thiết kế **network default deny, egress gateway, proxy authorization, DLP, object storage policy, audit và rate/volume controls** theo các ranh giới thực tế.
- Phân biệt những thứ **thấy được** ở VPC flow log, firewall, L7 proxy, application và data store; tránh kết luận exfiltration chỉ từ số byte.
- Thực hiện bài lab **Python offline** phân loại các upload được mô phỏng, xây ma trận kiểm thử **ALLOW/DENY**, runbook và cơ chế vận hành an toàn.

### 1.2. Những điều cần nhớ ngay từ đầu

**Chặn tất cả HTTP POST** không phải là chính sách DLP hoàn chỉnh: upload có thể dùng **PUT, PATCH, gRPC client stream, WebSocket, S3 multipart, chunked requests hoặc giao thức khác**. Ngược lại, một POST có thể là JSON nhỏ hợp lệ, không phải upload tệp.

**HTTPS không tự chống rò rỉ dữ liệu.** TLS bảo vệ bí mật trên đường truyền với peer được xác thực, nhưng nếu workload được phép kết nối và gửi nội dung cho một đích không nên nhận dữ liệu, TLS vẫn vận chuyển nội dung đó thành công.

**NetworkPolicy chỉ nhìn đường mạng theo khả năng CNI**, không tự biết một request gửi **số tài khoản ngân hàng, dữ liệu khách hàng hay code độc quyền**. Muốn phân tích nội dung cần một điểm có quyền nhìn plaintext hoặc metadata đáng tin ở application/data plane.

## 2. Upload hợp lệ khác dữ liệu bị thất thoát như thế nào?

Không nên gọi mọi egress upload là **data exfiltration**. Vấn đề nằm ở **nguồn dữ liệu, mục đích, quyền, người nhận, loại nội dung và ngữ cảnh**.

| Hoạt động | Có thể hợp lệ khi | Nguy cơ |
| --- | --- | --- |
| CI runner tải artifact lên registry | Registry thuộc tổ chức, image được phép, role chỉ được push vào repo cần thiết | Đưa source/sensitive build artifact sang registry cá nhân |
| Backup job tải snapshot lên object storage | Bucket/account/region được phê duyệt, mã hóa/retention đúng | Backup chứa PII bị ghi vào bucket public hoặc tài khoản khác |
| App gửi log/telemetry | Fields đã được lọc secrets/PII, destination được duyệt | Upload raw Authorization token, request body, database query |
| Service gửi report tới đối tác | Contract, data classification, recipient identity, approval còn hiệu lực | Gửi dữ liệu vượt phạm vi hợp đồng hoặc sai tenant |
| ML workload gửi training results | Dataset được phê duyệt, không có dữ liệu nhạy cảm không được phép | Export nguyên training corpus thay vì metrics |
| Security agent gửi mẫu điều tra | Có incident approval, legal/privacy review và kênh bảo mật | Gửi dump chứa credentials, PII ngoài khu vực lưu trữ kiểm soát |

Một workload có thể gửi dữ liệu **tới domain đúng nhưng object/bucket/account sai**. Ví dụ đích là object-storage API của cùng một cloud provider: **hostname chính thức** không bảo đảm **bucket thuộc công ty**. Vì vậy cần kết hợp **destination ownership, IAM resource policy, tenant/account ID và application-level authorization**, không chỉ cho phép domain lưu trữ chung.

### 2.1. Bốn nhóm dữ liệu

| Nhóm dữ liệu | Ví dụ | Hướng kiểm soát |
| --- | --- | --- |
| **Public** | Tài liệu đã công khai, mã nguồn đã được phép công bố | Cho phép theo mục đích và rate quota |
| **Internal** | Logs đã lọc, cấu hình không có secrets | Chỉ gửi tới approved services và có audit |
| **Confidential** | Dữ liệu khách hàng, báo cáo doanh nghiệp, source private | Destination/recipient allowlist, content policy, approval |
| **Restricted** | Private keys, access tokens, dữ liệu regulated, dump nhạy cảm | Deny mặc định ngoài các workflow được phê duyệt và giám sát chặt |

Phân loại là **ví dụ mô hình**, không thay cho taxonomy thực tế của tổ chức. Phải xem **data owner, legal/privacy requirements, residency và business need**. Cũng không được tin metadata tự khai như header **X-Data-Class: Public** nếu workload bị compromise có thể tự gán nhãn.

### 2.2. Egress control khác DLP

- **Egress control:** Kiểm soát nơi workload có thể kết nối, bằng protocol/port/destination/identity và đôi khi hạn mức.
- **DLP:** Phát hiện hoặc ngăn dữ liệu thuộc loại nhạy cảm rời ranh giới không được phép, dựa trên **nội dung, nhãn, fingerprint hoặc ngữ cảnh**, tùy điểm triển khai.
- **Application authorization:** Phân quyền workload được thực hiện **upload action, upload tới repository/bucket nào, với dữ liệu của tenant nào**.
- **Quota/rate limiting:** Giới hạn **mức sử dụng**, không tự kết luận dữ liệu là hợp lệ.
- **Auditing/detection:** Theo dõi và điều tra hoạt động gửi ra ngoài, có thể trễ hoặc chưa đủ bằng chứng.

**Một lớp đơn lẻ không bao phủ tất cả.** Firewall ALLOW TCP/443 không chứng minh payload được phép gửi. DLP kiểm tra “không có số thẻ” không chứng minh upload thuộc tenant đúng. Quota 100 MiB/ngày vẫn có thể cho phép một bí mật 1 KiB rò rỉ.

## 3. Mô hình đe dọa và các đường upload có thể tồn tại

~~~mermaid
flowchart LR
    A["App / Worker / Pod"] --> C["CNI, SG, cloud route"]
    C --> G["Egress proxy / service mesh gateway"]
    G --> F["Firewall / NAT / DNS policy"]
    F --> D["Approved partner / object storage"]
    C -. "Potential direct route" .-> U["Unapproved endpoint"]
    A --> L["Application logs / traces"]
    L --> T["Telemetry sink"]
    A --> M["Metadata or cloud identity service"]
    M -. "Scoped temporary credentials" .-> A
    G -. "Decision logs" .-> S["SIEM / DLP / data governance"]
    D -. "Object/action audit" .-> S
~~~

### 3.1. Những điểm attacker hoặc lỗi cấu hình có thể khai thác

| Bề mặt | Tình huống | Hậu quả |
| --- | --- | --- |
| **Ứng dụng bị RCE/SSRF** | Process bị điều khiển gửi request tới đích do attacker chọn | Exfil qua đường egress sẵn có |
| **Cloud workload identity quá quyền** | Pod có thể ghi mọi buckets/accounts, tạo pre-signed URL rộng | Data transfer ra tài nguyên không thuộc phạm vi |
| **Egress ANY/ANY** | Pod được gửi TCP/443 tới bất kỳ IP/host nào | Proxy bypass, upload qua dịch vụ lạ |
| **Shared CDN/cloud hostname** | Allowlist domain chung cho nhiều tenants | Gửi tới bucket hoặc SaaS workspace của attacker |
| **DNS/IPv6/alternate protocol** | Policy chỉ áp IPv4/TCP hoặc tin tên miền tự khai | Có đường upload không qua PEP dự kiến |
| **Logs và error telemetry** | App vô tình log body/token vào bên thứ ba | Rò dữ liệu qua kênh “hợp lệ” |
| **Multi-part/chunking** | Nhiều phần nhỏ vượt qua kiểm tra per-request | Tổng dữ liệu nhạy cảm được chuyển ra |
| **Compression/encryption trước upload** | DLP gateway chỉ thấy ciphertext/archive không hỗ trợ | Content inspection trở nên mù |
| **Signed URLs** | URL có quyền ghi vào bucket bên ngoài | Thao tác hợp lệ về mặt signature nhưng sai business policy |
| **NAT/shared IP** | Nhiều Pods dùng một public egress IP | Gán sai workload gây exfil |
| **Proxy misconfiguration** | Bypass port, tunnel CONNECT, wildcard domains | Chính sách egress không được thực thi |
| **Supply-chain/agent** | SDK hoặc telemetry library gửi nhiều dữ liệu hơn hợp đồng | Lộ dữ liệu do dependency hợp lệ về mạng |

### 3.2. Các ranh giới tin cậy

1. **Data boundary:** dữ liệu public/internal/confidential/restricted.
2. **Workload boundary:** identity của Pod/VM/function, namespace, cluster, tài khoản và môi trường Prod/Dev.
3. **Network boundary:** VPC/VNet, CNI, egress gateway, service-to-service tunnel, public Internet.
4. **Tenant/ownership boundary:** object storage bucket, SaaS workspace, cloud account/project bên nhận.
5. **Policy boundary:** ai có quyền thay allowlist, DLP rule, quota, proxy và exception?
6. **Observability boundary:** ai được xem payload/log, báo cáo, DLP matches hoặc dữ liệu bị quarantine?

**Tài sản nhạy cảm cần nhiều kiểm soát độc lập.** Đường từ một Pod Prod đến object store do cloud provider quản lý vẫn có thể vượt **ownership/trust boundary** nếu credentials và bucket policy cho phép ghi vào account ngoài.

## 4. Đơn vị quyết định: workload, dữ liệu, đích và hành động

Một policy có ích nên mô tả:

\[
\text{PermitUpload} =
\text{AuthenticatedWorkload}
\land \text{AuthorizedAction}
\land \text{ApprovedDestination}
\land \text{PermittedData}
\land \text{ContextWithinLimits}
\]

**Biểu thức là mô hình ý niệm**, không phải rule syntax hay điều kiện kiểm tra đủ cho mọi backend. Mỗi thành phần phải có **nguồn dữ liệu đáng tin, người thực thi và bằng chứng**.

| Chiều đánh giá | Ví dụ | Dữ liệu cần |
| --- | --- | --- |
| **Workload** | Namespace prod-analytics, ServiceAccount report-writer, signed image | K8s/workload identity, IAM principal, deployment owner |
| **Recipient** | Bucket report-exports trong company cloud account | Account/bucket ID, approved tenant/repository, network endpoint |
| **Operation** | PutObject cho prefix reports/daily/, không DeleteObject | IAM/object policy, API method/resource |
| **Data** | Report đã khử định danh, nhãn Internal | Data governance, DLP classification, file provenance |
| **Volume** | Tối đa 50 MiB/upload; budget theo giờ/ngày | Layer có request bytes và quota accounting đúng |
| **Time/context** | Batch window có phê duyệt; không ngoài lịch | Job identity, change ticket, UTC, entitlement/JIT |
| **Transport** | TLS verify đúng hostname; approved region | HTTPS/mTLS, egress proxy, provider endpoint |
| **Failure action** | DENY, step-up, quarantine hoặc alert-only theo policy | Policy owner, enforcement capabilities |

### 4.1. Một identity không nên đại diện cho mọi workload

**Static API key dùng chung 20 Pods** làm khó attribution và revocation. Với Kubernetes, có thể dùng **ServiceAccount identity**, cloud workload federation hoặc mTLS SPIFFE identity, kết hợp **short-lived cloud credentials**. Tuy nhiên **ServiceAccount hợp lệ không đủ** nếu IAM role rộng quyền sang buckets khác hoặc attacker có thể sử dụng identity của một process đã bị chiếm.

### 4.2. Không sử dụng “nguồn IP” làm quyền upload tuyệt đối

NAT gateway có thể gom nhiều workloads vào một IP public; Pod IP có thể tái sử dụng; load balancer/proxy có thể đổi source IP. Dùng **cryptographically verified workload identity** khi có thể, kèm resource authorization. IP/port/subnet chỉ là **một lớp phòng vệ mạng bổ sung**.

### 4.3. Đích phải xác định ở lớp phù hợp

**TCP destination IP/port** không cho biết bucket, account hay tenant đích; **TLS SNI** không luôn trùng HTTP Host và có thể bị che bởi ECH tùy trường hợp; **HTTP Host/path** chỉ có ở điểm xử lý L7. Với managed object store, chính **storage API/authorization** hoặc một broker ứng dụng có thể phân biệt **bucket/key/role** đáng tin hơn việc chỉ allowlist FQDN cloud provider.

## 5. Bản đồ lớp kiểm soát: từ Pod tới data store

~~~mermaid
flowchart LR
    W["Workload identity / app"] --> N["CNI NetworkPolicy / SG"]
    N --> P["Outbound L7 proxy / egress gateway"]
    P --> F["NAT / DNS resolver / cloud firewall"]
    F --> R["Remote API or object store"]
    I["IAM / resource policy"] -. "Authenticated authorization" .-> R
    D["DLP / classification"] -. "Inspect when plaintext available" .-> P
    D -. "Pre-upload scan / labels" .-> W
    O["Observability"] -. "Metrics / decisions" .-> W
    P -. "L7 logs" .-> O
    F -. "Network flows" .-> O
    R -. "Object audit" .-> O
~~~

| Điểm kiểm soát | Mạnh ở điều gì? | Không tự làm được |
| --- | --- | --- |
| **Kubernetes NetworkPolicy/CNI** | Pod/namespace ingress/egress theo IP/port/pod selectors nếu CNI hỗ trợ | Đọc nội dung file, quyết định bucket/object, FQDN theo NetworkPolicy chuẩn |
| **Cloud SG/NACL/firewall** | Network segments, routes, transport/protocol và một số identity/app rules tùy sản phẩm | Khẳng định từng upload thuộc loại dữ liệu cho phép nếu không có L7 inspect |
| **DNS filtering** | Chặn resolution tới tên miền cấm theo đường DNS được quản lý | Ngăn direct-IP/DoH/alternate resolver/tunnel khi không có enforcement khác |
| **L7 outbound proxy** | HTTP method/Host/path, bytes streaming và policy theo request khi nhìn plaintext | Đọc ciphertext của app TLS passthrough, kiểm tra mọi protocol không hỗ trợ |
| **DLP scanner** | Phân loại nội dung trước upload/in gateway theo khả năng | Chứng minh không có dữ liệu nhạy cảm khi nén/mã hóa/định dạng lạ |
| **Application upload broker** | Data owner, tenant, object type, destination account, workflow approval | Bảo vệ mọi đường mạng bypass nếu Pod còn direct egress |
| **Cloud IAM/resource policy** | PutObject/role/bucket/account/region/prefix theo hỗ trợ | Nhận biết nội dung nhạy cảm chỉ từ IAM action |
| **Storage service audit** | Object owner, operation, identity, bytes, timestamp theo log | Chứng minh các uploads bị chặn trước store, hay ứng dụng có side effect khác |
| **SIEM/flow logs** | Phát hiện volume/destination anomalies và ghép ngữ cảnh | Tự chặn real time hoặc thấy raw payload khi log là metadata |

### 5.1. Defense-in-depth không có nghĩa thêm proxy vô hạn

Mỗi hop bổ sung tạo **độ trễ, chi phí, blast radius và nơi lưu dữ liệu tạm**. Nên chọn những điểm **có thể thực thi chính sách chính xác nhất**: IAM/object policy cho resource access, app-side classification cho dữ liệu trước mã hóa, firewall/CNI cho chặn bypass, proxy cho HTTP metadata và DLP khi được phép inspect.

### 5.2. Bảng phân biệt ALLOW

Một **ALLOW** ở NetworkPolicy chỉ nói packet path đã được cho phép tại một điểm. Một **ALLOW** ở proxy có thể chỉ cho Host và POST. Một **ALLOW** ở object store chứng minh identity có quyền **PutObject vào bucket**. Để gọi upload hợp lệ theo business policy, cần xem **đúng dữ liệu, đúng recipient/account, đúng scope và approval**. Không dùng một dấu ALLOW làm kết luận cho mọi lớp.

## 6. Kubernetes egress: NetworkPolicy và lớp CNI

Một Pod có thể cần kết nối **DNS, identity broker, service nội bộ, approved object-storage gateway** và không cần direct Internet egress. **Default-deny egress** theo namespace/workload giúp giới hạn đường ra, nhưng chỉ hữu ích khi **CNI có thực thi NetworkPolicy** và rule phù hợp data path thực.

### 6.1. Ví dụ default deny cho namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-egress
  namespace: prod-reports
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Policy này **cô lập egress của những Pods được chọn** theo cơ chế NetworkPolicy được triển khai, **không phải tắt mọi egress của toàn cluster**. Không phải mọi CNI hỗ trợ hoàn toàn giống nhau; service mesh, hostNetwork traffic, NodeLocal DNSCache, cloud-managed services và những giao thức ngoài phạm vi cần test riêng.

### 6.2. Chỉ mở đường DNS và upload broker

Ví dụ minh họa chỉ cho Pods có label **app=report-writer** gửi TCP/443 tới Pod **upload-broker** ở namespace **platform-security**, cộng DNS tới Pods **kube-dns** trong namespace **kube-system**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: report-writer-approved-egress
  namespace: prod-reports
spec:
  podSelector:
    matchLabels:
      app: report-writer
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-security
          podSelector:
            matchLabels:
              app: upload-broker
      ports:
        - protocol: TCP
          port: 443
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

**Các nhãn, cổng và kiến trúc là giả định.** Trong cluster thực, DNS có thể dùng **NodeLocal DNSCache/hostNetwork**, upload broker là Service VIP qua kube-proxy/eBPF, hoặc ingress port khác do sidecar interception. Phải xác minh **packet destination thực tại điểm enforcement** và kết hợp ingress policy phía broker. Một policy cho phép DNS không đồng nghĩa browser/workload không thể sử dụng **DoH qua TCP/443 đã được mở** nếu có đường tới resolver thay thế.

### 6.3. Không đồng nhất CIDR với FQDN policy

Kubernetes NetworkPolicy chuẩn hỗ trợ **IP blocks, selectors và ports**, không có quy tắc FQDN được định nghĩa chuẩn. Một số CNI cung cấp **FQDN egress policy mở rộng** hoặc egress gateway, nhưng cần xem semantics **DNS caching, TTL, CDN/shared IPs, IPv6 và bypass direct-IP**. Khi đích là một **cloud object store dùng địa chỉ động/shared**, cân nhắc **private endpoint, resource policy, upload broker hoặc egress gateway** thay vì mở rộng CIDR public không kiểm soát.

### 6.4. Phạm vi không tự bao phủ tất cả

- Pods dùng **hostNetwork**, các agent/node processes và privileged workloads có thể chịu cơ chế khác.
- **Service mesh sidecar** có thể phát traffic từ cùng Pod network namespace nhưng tới cổng/interception path khác.
- **IPv6 và dual-stack** phải được kiểm thử tương đương IPv4.
- Không suy cả **DNS query lẫn TCP connection** đều đi qua một bộ rule chỉ vì có NetworkPolicy.
- Egress policy không tự thực thi **data classification, per-object permissions, quota hay API method restrictions**.

### 6.5. Kiểm tra ALLOW/DENY sau thay đổi

Trong lab/staging có quyền, xác nhận:

1. Report-writer gọi upload broker TCP/443 **ALLOW**, DNS hoạt động.
2. Report-writer gọi một **external arbitrary endpoint** **DENY**.
3. Workload khác trong namespace không được **giả danh report-writer chỉ bằng label** khi không có admission/RBAC bảo vệ Pod labels.
4. Broker chỉ chấp nhận **authenticated workload identity**, không tin một kết nối TCP được allow là đủ.
5. **Direct Pod IP, service VIP, IPv4/IPv6, DR region và node bypass** không tạo đường trái chính sách.

## 7. Egress proxy và gateway: kiểm soát HTTP upload

Một outbound HTTP proxy có thể xử lý requests trước khi đi ra external service. Nếu được đặt ở **đúng điểm** và có quyền quan sát HTTP payload/metadata, nó có thể áp chính sách theo **method, destination, URL path, request content type, identity, byte quota và DLP rule**.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload: report-writer
    participant P as Egress proxy / upload broker
    participant D as DLP/policy decision
    participant S as Approved storage API
    W->>P: Authorized upload request
    P->>D: Identity, recipient account, labels, declared size, policy
    D-->>P: ALLOW with limit and content obligations
    P->>P: Stream count, inspect if allowed, enforce limits
    P->>S: TLS validated and authorized write
    S-->>P: Storage response / object ID
    P-->>W: Result, sanitized error
    P-->>D: Decision metadata / completion
~~~

**Một số kiến trúc sẽ dùng separate upload broker thay vì generic forward proxy.** Broker có thể xác minh bucket, tenant, object namespace và data owner trước khi tạo hoặc thực thi upload; generic CONNECT proxy chỉ thấy tunnel và không mặc nhiên biết HTTP path hoặc recipient account bên trong TLS.

### 7.1. Ba cơ chế proxy khác nhau

| Cơ chế | Proxy nhìn được | Hạn chế |
| --- | --- | --- |
| **Forward proxy HTTP plaintext** | Method/Host/path/header/body ở chặng plaintext | Chỉ phù hợp nếu kênh giữa workload và proxy đã được bảo vệ theo rủi ro |
| **HTTP CONNECT TCP tunnel** | CONNECT target, proxy socket metadata; nội dung HTTPS thường vẫn mã hóa | Không thấy URL, HTTP PUT/POST body hoặc object key bên trong |
| **TLS termination/inspection do tổ chức kiểm soát** | L7 content và request metadata sau khi giải mã | Cần trust management, bảo vệ payload/keys/PII, chính sách pháp lý; E2E hoặc pinning có thể không tương thích |

**Không bật TLS decryption rộng khắp chỉ vì muốn kiểm tra upload.** Với dữ liệu cực nhạy, cách phù hợp có thể là **kiểm tra tại ứng dụng trước khi mã hóa**, proxy xử lý metadata, hoặc **resource-side object permissions**. TLS inspection chỉ dùng khi tổ chức có quyền, mục đích rõ ràng, phạm vi hẹp và bảo vệ bí mật trong proxy.

### 7.2. Ví dụ policy intent cho outbound HTTP

~~~yaml
# PSEUDOCODE minh họa, KHÔNG phải cấu hình hợp lệ của một vendor.
policy_id: prod-report-upload-v1
source_workload:
  namespace: prod-reports
  service_account: report-writer
destination:
  owner_account: company-production
  service: approved-upload-broker
  bucket: compliance-reports
  object_prefix: reports/daily/
operations:
  allowed: [PUT]
  max_single_upload_bytes: 52428800
data:
  allowed_classifications: [Internal]
  require_preupload_scan: true
transport:
  tls_peer_verified: true
  default_unknown_destination: DENY
accounting:
  max_uploaded_bytes_per_hour: 209715200
  max_concurrent_uploads: 2
on_dlp_unavailable: DENY
audit:
  log_decision_and_bytes_without_payload: true
~~~

**Các con số 50 MiB/request, 200 MiB/giờ, 2 uploads đồng thời chỉ là ví dụ**, không phải hạn mức chung. Upload hợp lệ có thể lớn hơn nhiều (backup, ML artifact), và một secret nhỏ hơn 1 KiB cũng đã là rò rỉ. Quota là **giới hạn tác động**, không chứng minh nội dung an toàn.

### 7.3. Cảnh giác với HTTP semantics

Một upload có thể dùng:

- **PUT** object trực tiếp, **POST** form, **PATCH** partial update.
- **HTTP chunked transfer** không có Content-Length.
- HTTP/2 **DATA frames** trên nhiều streams.
- **Content-Encoding gzip**, archive ZIP hoặc file được mã hóa trước.
- **multipart/form-data** hoặc **S3-style multipart upload** với nhiều requests.
- **gRPC client/bidirectional stream**, WebSocket binary frames.
- API-specific batch operations có thể chứa dữ liệu trong **JSON body**, không có file name.

Không chỉ kiểm tra **Content-Length** rồi coi đó là số byte thực sẽ được gửi. Nếu header thiếu/sai hoặc request stream kéo dài, phải có **streaming byte counters, total budgets, timeouts, max body/part limits và overflow/early-abort behavior** theo implementation.

## 8. Kiểm soát đích upload: host, cloud account, bucket và object

Khi workload được phép gọi **object-storage.example provider API**, câu hỏi khó hơn là **nó có được phép ghi vào tất cả buckets trên provider không?** Địa chỉ mạng, hostname và bucket owner là ba khái niệm khác nhau.

### 8.1. Phân biệt 5 kiểu định danh đích

| Thuộc tính đích | Ví dụ | Mức bảo đảm |
| --- | --- | --- |
| **Destination IP** | 198.51.100.15 | Địa chỉ mạng có thể shared, thay đổi qua CDN/NAT |
| **DNS hostname** | uploads.storage.example.org | Có thể shared giữa tenants, phụ thuộc resolution |
| **TLS peer identity** | Valid certificate cho hostname | Xác thực server, không xác thực bucket owner |
| **Cloud account / tenant ID** | company-production | Phân định bên quản lý tài nguyên, cần IAM/broker verify |
| **Bucket/object/container/key** | reports/daily/2026-11-28.json | Resource chính xác, kiểm tra quyền/nhãn/region |

Địa chỉ **198.51.100.0/24** là dải TEST-NET dành cho ví dụ tài liệu, không phải IP đích production.

### 8.2. Cloud IAM/resource policy

Đối với object storage, bảo vệ hiệu quả thường yêu cầu:

1. **Dedicated workload identity/role** chỉ có API write cần thiết.
2. Quyền **bucket/container cụ thể và object key prefix** theo khả năng provider.
3. Ràng buộc **resource/account/tenant owner**, không cho role ghi sang mọi buckets dù hostname giống nhau.
4. Chặn **public grants, insecure transport, unencrypted objects hoặc cross-region transfer** theo policy và hỗ trợ của service.
5. Có **audit log tại storage service** cho object create/complete, requester identity, bucket/key, timestamp và status.
6. Kiểm soát **ai có quyền sửa IAM/resource policy** hoặc tạo delegation/signed URLs.

Không tự đồng nhất syntax IAM của AWS S3, Azure Blob và Google Cloud Storage. Quyền action, resource scope, conditions, identity federation và object logging **khác nhau giữa providers và dịch vụ**.

### 8.3. So sánh ba kiểu egress ra storage

| Thiết kế | Ưu điểm | Rủi ro cần giải quyết |
| --- | --- | --- |
| Workload upload thẳng bằng cloud role hẹp | Hiệu năng tốt, sử dụng native cloud API | Role phải hạn chế bucket/account; content scan trước upload |
| Workload qua approved upload broker | Broker enforce business recipient/object/data labels | Broker thành điểm nhạy cảm, cần scaling và isolation |
| Workload qua egress TLS inspection proxy | Central L7 filtering theo khả năng | TLS compatibility, privacy, secrets tại proxy, bypass control |

### 8.4. Private endpoint không đồng nghĩa dữ liệu thuộc tổ chức

Private connectivity như cloud private endpoint có thể giữ traffic khỏi public Internet hoặc định tuyến qua mạng riêng. Nhưng **nó không tự chứng minh tài khoản/bucket/tenant đúng nếu endpoint/policy cho phép nhiều tài nguyên**. Cần kết hợp **resource ownership và identity-aware authorization**, đặc biệt khi dịch vụ cloud có **multi-tenant API**.

## 9. Signed URLs, delegated tokens và upload qua browser hoặc worker

Nhiều kiến trúc không đưa cloud credential đầy đủ cho workload mà cấp **pre-signed upload URL / SAS / delegated access token**. Điều này giúp giảm phạm vi quyền, nhưng đường upload vẫn cần được kiểm soát.

### 9.1. Những thuộc tính phải ràng buộc

- **Recipient resource:** bucket/container/account, object key hoặc prefix cụ thể.
- **Operation:** upload/write, không cho list/delete hoặc cấp lại delegation.
- **TTL:** thời gian đủ ngắn cho workflow, clock skew và file size dự kiến.
- **Content constraints:** content type, max bytes, checksums/tags nếu scheme hỗ trợ và có enforcement.
- **Ownership/tenant:** workflow này có được phép viết vào vùng dữ liệu/tenant ấy không?
- **Replay/multi-use:** URL có cho dùng lại, overwrite, hoặc nhiều parts không; cần kiểm soát khi nhạy cảm.
- **Audit:** ai cấp URL, cho object nào, workflow/approval nào và ai dùng.

**Không phải mọi loại signed URL hỗ trợ ràng buộc Content-Length, payload hash hoặc single-use theo cùng cách.** Không tự khẳng định chữ ký URL chứng minh người dùng sẽ chỉ gửi dữ liệu đã được DLP kiểm tra. Xác minh **provider-specific signature semantics** và kiểm tra tại upload broker/object-store khi cần.

### 9.2. Tình huống nguy hiểm

~~~text
Workload -> app broker: "Xin quyền upload báo cáo đã được duyệt"
App broker -> Workload: URL có quyền ghi quá rộng hoặc sang account khác
Workload -> Storage API: Gửi dữ liệu nội bộ vào account do kẻ khác sở hữu
~~~

Để giảm rủi ro, broker phải **tự xác định destination từ policy/server-side metadata**, không dùng account ID/bucket tùy ý do client gửi rồi ký. URL ký là một **bearer capability** trong thời hạn hiệu lực, cần được bảo vệ như credential. Không ghi **full signed query parameters** vào access logs, crash reports, tracing hay ticket.

### 9.3. Pre-upload scan và post-upload scan

| Cách làm | Khi phù hợp | Điểm yếu |
| --- | --- | --- |
| **Pre-upload scan** | Dữ liệu được kiểm tra trong app/broker trước khi rời boundary | Có race nếu file/payload thay sau scan; cần bind hash/object version |
| **Inline streaming inspection** | Proxy có quyền nhìn plaintext và có engine đủ khả năng | Streaming/buffering/latency, unknown length và unsupported formats |
| **Upload vào quarantine staging bucket** | Dịch vụ có thể nhận trước, quét rồi publish tới trusted consumer | Dữ liệu đã rời workload; quarantine ownership/ACL và retention rất quan trọng |
| **Post-upload asynchronous scan** | Phân loại và xử lý không cần block upload trước | Không ngăn rò rỉ tức thời nếu đích ngoài đã nhận dữ liệu |

**Post-upload scan không phải preventive DLP** khi dữ liệu đã được gửi tới một external uncontrolled recipient. Nếu dùng quarantine, nó phải nằm trong **trust boundary được phép**, không tự chuyển dữ liệu sang bên thứ ba trước khi kiểm tra.

### 9.4. Chứng minh file quét là file được upload

Nếu application scan file A nhưng có thể gửi file B ở request sau, policy bị vô hiệu. Thiết kế có thể ràng buộc **object identity, exact bytes/content hash, trusted upload broker, immutable staging object/version và manifest**. Cần xác định **canonicalization, compression/transform, encrypted container và hash algorithm**; hash trước khi biến đổi không tự khớp bytes thực trên wire.

## 10. Giới hạn kích thước, tốc độ và tổng dung lượng: không nhầm lẫn

**Giới hạn upload** gồm nhiều đơn vị và cửa sổ:

| Giới hạn | Chặn vấn đề | Không chặn được |
| --- | --- | --- |
| **Max single request bytes** | Một request quá lớn | Nhiều requests nhỏ, multipart |
| **Max object size** | Đối tượng lưu trữ quá kích thước | Nhiều objects hoặc nhiều phiên |
| **Max part size / part count** | Multipart abuse và resource exhaustion | Tổng volume nếu aggregate thiếu |
| **Per-workload bytes/hour/day** | Tổng dữ liệu upload trong cửa sổ | Dữ liệu nhạy cảm rất nhỏ |
| **Per-destination/tenant quota** | Đẩy dữ liệu sang đối tác quá mức | Bypass bằng đích khác nếu policy không bao phủ |
| **Concurrency limit** | Số phiên upload cùng lúc | Tốc độ/total bytes của từng phiên riêng |
| **Rate limit bytes/s** | Băng thông/egress burst | Tổng data over long duration |
| **Object write permission scope** | Chặn ghi sai account/bucket/prefix | Nội dung vượt classification nếu role vẫn được phép |

### 10.1. Phân biệt MiB và MB

\[
1\ \mathrm{MiB} = 2^{20}\ \mathrm{bytes} = 1{,}048{,}576\ \mathrm{bytes}
\]

\[
1\ \mathrm{MB} = 10^6\ \mathrm{bytes}
\]

Vì vậy **50 MiB = 52.428.800 bytes**; không nhầm với 50.000.000 bytes. Khi định nghĩa quota, phải viết rõ **raw payload bytes, compressed bytes, logical object bytes, network packets bytes hay billed bytes**.

### 10.2. Giới hạn per-request không đủ

Giả sử policy cho phép tối đa **10 MiB/upload**. Một workload có thể gửi **100 requests × 9 MiB = 900 MiB** mà không vượt per-request, nếu không có **aggregate quota**. Nhưng một secret nhỏ trong request đầu tiên vẫn có thể là incident; quota chỉ giảm quy mô/tốc độ.

### 10.3. Sliding window và token bucket

Một hệ thống có thể giới hạn **bytes mỗi phút** theo workload identity và recipient, kết hợp **token bucket** để chấp nhận burst có kiểm soát. Cần:

- Counters nhất quán **giữa proxies/replicas/regions**, tránh quota bị nhân lên khi scale.
- Khóa quota theo **identity + resource/tenant + policy**, không chỉ theo source IP/NAT.
- Giữ **atomic accounting**, reserve/release khi upload fail hoặc retry để không double count sai.
- Quy định **cách tính cancelled upload, retransmission, chunked body và parallel streams**.
- Không để retry của client làm **dùng hết quota hợp lệ** quá nhanh hoặc tránh quota do reset phiên.

### 10.4. Đọc Content-Length chưa chắc đúng

HTTP request có thể không khai Content-Length, hoặc dùng **chunked encoding / HTTP/2 DATA frames**. Với proxy L7, enforce nên dựa trên **actual streamed bytes**, có cách kết thúc stream an toàn khi vượt mức. Nếu cần DLP full-body, buffering phải có **memory/disk quota, timeout, max decompression ratio**, và không làm lộ dữ liệu vào buffer/storage không quản lý.

### 10.5. Logical bytes, compressed bytes và transfer bytes

Một file CSV 500 MiB có thể nén còn 50 MiB và được upload trong một request. Nếu quota áp **compressed transfer bytes**, nó không tương đương **logical data size** hoặc số records đã xuất. Muốn kiểm soát rò dữ liệu, có thể cần **data-classification/row-level approval** hoặc quota theo **logical records**, không chỉ lưu lượng trên wire.

## 11. DLP nội dung: phát hiện gì ở đâu?

Một hệ thống DLP có thể dùng **regex/format detection, data dictionaries, exact data matching, fingerprinting, labels, structured schema, ML classifier hoặc chính sách theo data owner**. Không một cách nào đảm bảo 100% phát hiện secrets/PII dưới mọi dạng.

### 11.1. Các điểm có thể quét

| Điểm | Dữ liệu thấy được | Lợi ích | Rủi ro/hạn chế |
| --- | --- | --- | --- |
| **Ứng dụng trước serialization/encryption** | Fields/rows/tenant/labels | Biết nghiệp vụ và classification | Nếu app bị compromise có thể bỏ qua check |
| **Endpoint/workload DLP agent** | Files/process/clipboard/network theo hỗ trợ | Bao phủ một số kênh ngoài app | Agent/OS permissions, resource overhead và privacy |
| **Upload broker** | Object/metadata/payload nếu nó nhận bytes | Enforcement tập trung theo recipient/owner | Đòi isolation, scaling, sensitive storage và identity |
| **Outbound TLS inspection** | HTTP content sau decryption nếu được phép | Có thể kiểm tra nhiều apps chung | Không xử lý mọi TLS/pinning/QUIC, rủi ro lưu plaintext |
| **Cloud storage staging** | Object sau upload | Scan nội dung trước khi publish nội bộ | Dữ liệu đã được gửi khỏi workload; owner/trust boundary phải phù hợp |
| **SaaS CASB/API** | Dữ liệu trong SaaS theo API quyền cấp | Discovery và kiểm soát governance | Asynchronous lag, API coverage, SaaS constraints |

### 11.2. Phân loại không phải xác thực quyền

Một file được gắn nhãn **Internal** không chứng minh người xuất có quyền gửi nó tới đối tác. DLP phải phối hợp với **tenant ownership, workflow approval và recipient authorization**. Một file không bị regex phát hiện PII vẫn có thể chứa **mã nguồn private, khóa dạng lạ hoặc bí mật nghiệp vụ**.

### 11.3. Khi dữ liệu đã bị mã hóa hoặc nén

Nếu app mã hóa archive trước khi gửi, proxy chỉ nhìn **ciphertext** trừ khi có quyền giải mã hợp pháp. Không thể khẳng định scan nội dung hoàn chỉnh chỉ bằng cách đọc TLS headers. Cách an toàn:

1. **Scan trước encryption** tại trusted application/broker.
2. Ràng buộc **digest, object ID và data classification** với bytes sẽ chuyển.
3. Chỉ cho upload tới **đích thuộc trust boundary được phê duyệt**.
4. Chặn **unsupported archive/encrypted payloads** theo policy hoặc yêu cầu review thủ công; ghi rõ false positives.
5. Theo dõi những egress flows **không qua đường có content visibility**.

### 11.4. False positives và false negatives

Quét nội dung dễ báo sai với **test fixtures chứa số giống định danh, dữ liệu đã khử nhận dạng hoặc code snippets**; cũng dễ bỏ sót **base64, screenshot, hình ảnh, nested archives hoặc bí mật ít entropy**. Cần **test corpus được phê duyệt, precision/recall evaluation, human review, feedback loop, rule versioning, multilingual content** và không huấn luyện classifier tùy ý từ dữ liệu bí mật chưa được phép.

### 11.5. Block, quarantine, redact hay alert-only?

**BLOCK** với dữ liệu restricted đi external unapproved destination; **QUARANTINE** khi cần review trong storage được kiểm soát; **REDACT/TRANSFORM** khi chỉ vài fields cần loại bỏ và application semantics cho phép; **ALERT-ONLY** khi đánh giá tác động của rule mới hoặc noncritical case, có owner/time limit. Không áp alert-only cho secret key lộ rõ vào đích ngoài rồi gọi đó là prevention.

## 12. Multipart, resumable và streaming uploads: quota phải theo toàn giao dịch

Một lỗi thiết kế phổ biến là kiểm tra **mỗi HTTP request** nhưng bỏ qua **workflow upload** gồm nhiều yêu cầu hoặc một stream kéo dài.

### 12.1. Multipart object upload

Một ứng dụng có thể:

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Report workload
    participant B as Upload broker / PEP
    participant S as Object store
    W->>B: Create upload session for approved object
    B-->>W: Upload ID / bounded capability
    loop Each part
        W->>B: Upload part N (bytes)
        B->>B: Validate identity, session, size and quota
        B->>S: Store authorized part
    end
    W->>B: Complete upload, part manifest
    B->>B: Check total object, DLP/provenance obligations
    B->>S: Finalize approved object
    S-->>B: Object version/status
    B-->>W: Result
~~~

Đây là **mô hình logic**, không phải chính xác giao thức multipart của mọi cloud storage. Nếu workload được phép upload mỗi part **8 MiB**, nó có thể hoàn tất object **800 MiB** qua 100 parts trừ khi policy tính tổng **upload ID, object key, recipient, workload và window**.

### 12.2. Các điểm accounting

| Sự kiện | Cần kiểm soát | Rủi ro |
| --- | --- | --- |
| Begin multipart upload | Workload identity, approved bucket/key, TTL/session | Tạo hàng nghìn phiên để né quota |
| Upload part | Actual byte count, part number, total reserved/committed budget | Mỗi part hợp lệ nhưng tổng vượt mức |
| Retry part | Idempotent replacement/dedup và accounting semantics | Double count hoặc bỏ tính khi retry |
| Complete upload | Parts manifest, object metadata, checksum, classification | Gắn các parts thành object lớn sai policy |
| Abort/timeout | Cleanup orphaned parts, quota reservation, lifecycle | Storage leak và quota state mâu thuẫn |
| Copy/compose server-side | Resource actions và source/destination object | Dữ liệu chuyển giữa buckets không đi qua app upload |

**Server-side CopyObject/compose/transfer** có thể di chuyển dữ liệu giữa buckets mà **không tạo outbound bytes tương ứng từ workload**. Bảo vệ phải nằm ở **IAM/resource policy/object audit** chứ không chỉ quota của egress gateway.

### 12.3. Resumable uploads

Với resumable upload, client có thể tiếp tục từ một offset và tái sử dụng URL/capability. Phải ràng buộc **upload session ID, object key, owner, expiry, allowed offset/range và tổng kích thước**. Nếu client gửi chồng range do retry, quota tính **bytes được nhận, bytes committed và storage object size** theo policy, tránh gian lận hoặc khóa nhầm.

### 12.4. gRPC client streaming và bidirectional streaming

Trong gRPC, một kết nối HTTP/2 có thể chứa **nhiều streams**, một RPC có nhiều messages. Proxy L4 chỉ thấy TCP bytes; nếu cần quota theo **RPC method và message**, phải có **L7 gRPC-aware enforcement** hoặc logic ở service. Đừng coi HTTP/2 connection limit là giới hạn **số objects/microservice operations**.

### 12.5. WebSocket và long-lived TCP

WebSocket handshake bắt đầu bằng HTTP nhưng sau **Upgrade**, nội dung binary frames có thể không còn là HTTP requests. Một proxy chỉ kiểm tra URL lúc handshake **không tự kiểm tra mỗi frame/data chunk**. Với raw TCP, MQTT, SFTP hay giao thức custom, policy cần **protocol-aware gateway** hoặc enforcement tại ứng dụng/server; rate cap IP/port chỉ giảm throughput, không nhận biết bí mật.

### 12.6. QUIC/HTTP/3 và UDP

HTTP/3 sử dụng QUIC trên UDP. Một egress proxy chỉ quản lý **HTTP/1.1/TCP 443** có thể không quan sát **UDP/443** nếu network policy còn cho phép. Có thể cần **egress UDP restrictions, compatible proxy support hoặc ứng dụng dùng một transport đã được phép**. Không mặc định chặn UDP/443 giải quyết mọi kiểu bypass, vì ứng dụng có thể đổi sang TCP hoặc đi qua tunnel khác nếu còn đường mở.

## 13. TLS, SNI, ECH và giới hạn quan sát payload

Một số kiến trúc cố dùng **network firewall hoặc flow log** để suy định upload dữ liệu nhạy cảm qua **TLS**. Đây là giới hạn quan trọng: encryption che nội dung trước các điểm không có khóa/không terminate TLS.

~~~text
Application payload / object data
  |
  |  TLS encryption tại app hoặc proxy
  v
TCP/QUIC traffic trên network
  |
  |  Flow log: source/destination, port, bytes, time, action
  |  Firewall L4: destination/rule; có thể không thấy HTTP path
  v
Remote TLS endpoint
~~~

### 13.1. Tầng nào thấy gì?

| Quan sát | Thường thấy được | Chưa thể kết luận |
| --- | --- | --- |
| VPC flow log | IP/port/protocol/time/byte counts theo source/sampling | HTTP method, bucket, field PII, user |
| Network firewall L4 | Destination, ports, route/rule metadata | Object key, JSON payload, content classification |
| TLS handshake metadata | Có thể thấy SNI/ALPN/cert metadata tùy TLS version/ECH/inspection | Mọi URL/path/Host, data bytes đúng nghĩa application |
| HTTP CONNECT proxy | CONNECT authority/destination và tunnel metadata | HTTPS request body bên trong tunnel nếu không decrypt |
| L7 proxy terminating TLS | HTTP method/path/headers/body nếu được phép xử lý | Original application intent và toàn bộ tenant auth nếu backend không cung cấp |
| Application pre-upload hook | Data labels, tenant, serialized body trước TLS | Bypass qua đường app không đi qua hook |
| Object storage audit | Authorized object write, bucket/key/bytes theo provider | Nội dung nhạy cảm nếu không có scan/classification |

### 13.2. ECH và SNI không phải identity/resource policy

**Encrypted ClientHello (ECH)** có thể che phần tên đích trong TLS ClientHello theo triển khai. Ngay cả khi firewall thấy SNI, **SNI không chứng minh URL path, account/bucket, tenant hoặc loại dữ liệu**. TLS SNI-based policy cần kết hợp **DNS/endpoint controls, object authorization, workload identity**, và kiểm thử khi clients dùng ECH hoặc direct IP.

### 13.3. TLS inspection và vấn đề quyền riêng tư

TLS inspection trên traffic ngoài vùng được phép hoặc không có căn cứ có thể phá kỳ vọng confidentiality và gây rủi ro dữ liệu:

- Proxy có thể nhìn **tokens, credentials, PII và business payload**; cần least privilege, encryption, access audit, retention.
- Certificate trust/PKI phải được quản lý; không vô hiệu hóa certificate validation của client.
- Một số ứng dụng dùng **certificate pinning, app mTLS hoặc end-to-end encryption** không phù hợp TLS interception.
- Nếu tổ chức không có quyền đọc nội dung, chọn **pre-upload data guard và resource-side restrictions** thay vì cố decrypt.
- Rà soát **phạm vi nhân sự, đối tác, quốc gia/region, contractual và regulatory obligations**.

**Làm nội dung có thể quan sát được không đồng nghĩa xử lý nội dung an toàn.** DLP quarantine và logs phải hạn chế việc tự tạo thêm bản sao dữ liệu nhạy cảm.

### 13.4. Không dựa vào một cổng để nhận diện upload

HTTPS có thể chạy cổng khác 443; HTTP có thể dùng 80 hoặc cổng ứng dụng tùy chỉnh; data export có thể đi qua DNS, SSH/SFTP, custom TCP/UDP, VPN tunnel hoặc SaaS SDK. **Chặn PUT/POST ở port 443** vừa không bao phủ tất cả đường ra vừa có thể làm hỏng API requests hợp lệ. Kiểm soát theo **intent và resource**, phối hợp network default deny.

## 14. DNS, CDN, SaaS và cloud provider shared endpoints

Một allowlist **api.example-saas.com** có thể đại diện cho dịch vụ phục vụ hàng nghìn khách hàng khác nhau. Nếu workload được phép upload tới domain đó, liệu nó có thể gửi vào **workspace cá nhân** bằng một API token khác?

### 14.1. Destination control theo cấp độ

1. **DNS domain/IP block**: giảm phạm vi kết nối nhưng không xác định tenant.
2. **TLS hostname verification**: chứng minh peer sở hữu/chịu trách nhiệm cho tên miền, không chứng minh tenant.
3. **SaaS tenant/workspace restriction**: yêu cầu ứng dụng/proxy hoặc SaaS API enforce đúng organization ID.
4. **User/workload authorization**: token được cấp cho role/resource của công ty, không dùng external tenant.
5. **Data-aware policy**: chỉ loại dữ liệu phù hợp được upload.
6. **Audit theo object/tenant**: xác nhận dữ liệu thực tới resource nào.

### 14.2. CDN/shared IP và SNI

Nhiều domains cùng dùng **một IP CDN**, nên IP reputation hoặc wildcard allowlist không đủ. HTTP CONNECT tunnel có thể chỉ biết **đích TLS** mà không phân biệt SaaS workspace. Nếu cần tenant-level restriction, sử dụng **provider-supported tenant controls, SaaS API, CASB/SSE đúng chức năng hoặc upload broker**; xác minh tool có nhìn đúng request/response chứ không chỉ tên miền.

### 14.3. DNS proxy không chặn mọi đường bypass

DNS filtering có thể bị đi vòng bởi **IP literal, cached DNS, alternate resolver, DoH/DoT, service mesh DNS capture differences** nếu egress còn mở. Giải pháp defense-in-depth là **chặn direct network paths, chỉ cho approved resolver/egress gateway, enforce identity tại resource** và test thực tế.

### 14.4. Redirect và Host header

HTTP client có thể theo **3xx redirect** tới host khác. Nếu client tiếp tục gửi **Authorization header, signed URL hoặc request body** sang domain không đáng tin, dữ liệu/secret có thể bị lộ. Client SDK và proxy nên:

- Verify **redirect destination** theo allowlist sau mỗi hop.
- Không gửi **credentials và bodies** sang origin khác ngoài policy.
- Kiểm tra **TLS certificate/hostname** sau redirect.
- Phân biệt **Host header/authority do client tự khai** với upstream connection mà proxy thực sự dùng.

Không được tin một domain chỉ vì URL ban đầu hợp lệ rồi bỏ kiểm soát toàn bộ redirect chain.

## 15. Cloud workloads: VM, Kubernetes, serverless và CI/CD

Từng môi trường có đường xuất dữ liệu riêng:

| Workload | Đường egress thường thấy | Cần bảo vệ |
| --- | --- | --- |
| **Kubernetes Pod** | Pod IP → CNI/sidecar → NAT/firewall/gateway | Pod/SA identity, NetworkPolicy, sidecar bypass, secret mount |
| **VM service** | NIC/SG/host firewall → NAT/proxy | Host/service identity, egress route, process attribution |
| **Serverless function** | Managed networking/NAT/VPC connector/direct service API | Function execution role, managed egress limitations, logging |
| **CI/CD runner** | Build tools → artifact registry/object store/external APIs | Short-lived credentials, dependency scripts, push permissions |
| **Batch/ETL worker** | Data warehouse/object storage → partner uploads | Dataset owner, volume, classification, export workflow approval |
| **Service mesh service** | App → sidecar → egress gateway → Internet | Workload mTLS identity, mesh policy, L7 visibility, CNI bypass |
| **Managed agent/collector** | Telemetry exporter → SaaS provider | Field redaction, vendor contract, network destination control |

### 15.1. Cloud object storage: AWS, Azure và Google Cloud

AWS S3, Azure Blob Storage và Google Cloud Storage có **IAM/resource-level access controls**, logging và private connectivity options theo dịch vụ. Dù vậy **syntax policies, access tokens, signed URL semantics, encryption, regional controls và logs** khác nhau. Thiết kế phải kiểm tra capability của **đúng provider/service/version** thay vì giả định một chính sách chung áp thẳng.

Ví dụ các quyết định cần ràng buộc:

- **AWS:** IAM role/session, bucket policy, account/bucket/key resources, object API action và network endpoint điều kiện hỗ trợ.
- **Azure:** Managed identity/role assignments, storage account/container, SAS/delegation scope, network/private endpoint restrictions theo hỗ trợ.
- **Google Cloud:** Workload Identity Federation/IAM principals, bucket object permissions, signed URL/delegation và network/egress controls theo hỗ trợ.

**Cloud credential có thể cho phép hành động không đi qua egress gateway**, ví dụ **server-side copy/replication**. Resource policy và audit của storage backend phải bao phủ những thao tác này.

### 15.2. Tách environments và tenants

Một CI runner Dev không nên có quyền **ghi tới Prod reporting bucket** hoặc truy cập tenant khác. Network rule Dev→Prod DENY giúp thu hẹp đường, nhưng API key/cloud role cũng phải **scope theo environment và resource** để ngăn exfil qua provider API hoặc path được phép.

### 15.3. Runtime identity khác image pull identity

**Image pull credential** thường do node/runtime dùng khi kéo image; application runtime không mặc nhiên cần credentials ấy. Không đưa registry admin key vào container env để publish artifact. Dùng **dedicated service account/short-lived token** cho upload, tách read/pull khỏi write/push.

### 15.4. Storage outbound ở cùng provider vẫn là egress

Một Pod ở trong VPC gửi dữ liệu tới object store qua **private endpoint** vẫn đang chuyển dữ liệu **ra khỏi trust boundary ứng dụng/namespace**, dù packet không ra public Internet. Đánh giá recipient ownership, classification và audit như các upload khác.

## 16. Thiết kế app-side upload broker: thực thi trước khi dữ liệu rời trust boundary

Một **upload broker** là ứng dụng trung gian có quyền nhận yêu cầu xuất dữ liệu, xác minh policy, thực hiện hoặc cấp capability write có giới hạn tới đúng đích. Mô hình này thích hợp khi việc phân quyền không thể diễn đạt chỉ bằng CIDR/port.

~~~mermaid
flowchart TB
    W["Workload: export request"] --> A["Authn workload identity"]
    A --> B["AuthZ: data owner + recipient + action"]
    B --> C["DLP/label: classify approved payload"]
    C --> D["Quota: logical and transfer bytes"]
    D --> E{"All checks satisfied?"}
    E -- "No" --> X["DENY / review / controlled quarantine"]
    E -- "Yes" --> F["Write via narrowly scoped identity"]
    F --> G["Approved object store/partner"]
    G --> H["Object audit, checksum, completion"]
~~~

### 16.1. Server-side decisions không dựa vào trường client tự khai

Một request:

~~~json
{
  "report_id": "report-2026-11-28",
  "destination_alias": "approved-partner-a",
  "purpose": "daily-compliance-report",
  "requested_format": "csv"
}
~~~

**Không để client tự đặt arbitrary bucket/account URLs hoặc data_classification='Public'** rồi broker chấp nhận. Broker cần resolve **destination_alias** từ cấu hình/registry được phê duyệt, xác minh report ownership/classification và principal đang gọi. Với multitenant app, **tenant ID** được lấy từ identity/context đáng tin, không chỉ từ JSON body.

### 16.2. Chặn TOCTOU giữa kiểm tra và upload

**Time-of-check-to-time-of-use (TOCTOU)** xảy ra khi dữ liệu được scan/approve rồi bị thay trước khi gửi. Giải pháp có thể dùng **immutable object version, manifest/checksum, broker-owned staging storage, content hash binding và explicit publish step**. Đừng ghi “DLP scan PASS” cho file A rồi cho phép bất kỳ file B cùng tên đi ra.

### 16.3. Định danh request và tính idempotent

Một upload đáng tin cần **workflow/request ID, object key, idempotency key, upload session ID, result code và audit event**. Khi client retry vì timeout, server phải phân biệt **đã commit** với **chưa commit**, tránh tạo duplicate objects hoặc tính quota không nhất quán. Không retry vô hạn một operation có side effect nếu chưa có idempotency guarantee.

### 16.4. Lựa chọn fail-closed khi classifier lỗi

Nếu DLP engine không trả lời:

- **Restricted/confidential external upload:** DENY hoặc giữ trong **quarantine nội bộ** theo policy.
- **Internal low-risk telemetry:** có thể áp chế độ **redaction tối thiểu và alert** nếu risk owner cho phép.
- **Critical backup:** có thể tiếp tục tới **trusted internal backup vault** khi đã thiết kế exception, vẫn không gửi ra recipient ngoài thiếu kiểm soát.

**Failure policy phải dựa trên mức độ dữ liệu và tác động**, có owner/time limit. Không đặt “DLP unavailable → allow all” rồi gọi đó là high availability.

## 17. Observability: đo upload nào, ở đâu và với bằng chứng gì?

Không có một log stream duy nhất trả lời đầy đủ **“workload đã rò dữ liệu hay chưa?”**. Cần kết hợp:

| Nguồn | Thấy được | Không mặc nhiên chứng minh |
| --- | --- | --- |
| CNI/VPC flow logs | IP/port/bytes/direction/time theo điểm thu | HTTP upload thành công, object/bucket nào, nội dung |
| Firewall/egress gateway | Rule/destination/action/volume, một số app metadata | Dữ liệu nhạy cảm nếu không inspect |
| L7 proxy access logs | Method/path/Host/status/bytes/identity nếu proxy nhìn HTTP | Object đã commit hoặc payload thuộc tenant hợp lệ |
| Workload/application logs | Export job ID, report owner, action, validation | Network path ngoài app đã bị chặn ở mọi nơi |
| Cloud IAM/STS audit | Role/session/token issuance và resource API access | Dữ liệu cụ thể đã upload nếu thiếu object logging |
| Object store audit | Bucket/object/key/version, requester, operation status | Content classification nếu chưa scan |
| DLP scanner | Rule/labels/match categories, confidence, decision | Toàn bộ content đã được quét khi format unsupported |
| DNS resolver logs | Domain queries và thời gian | TCP/HTTP đã tới đúng hostname hay bucket |
| EDR/runtime telemetry | Process/network/secret access, workload anomalies | Business approval/data ownership |

### 17.1. Một record chuẩn hóa minh họa

~~~json
{
  "event_time": "2026-11-28T06:20:00Z",
  "request_id": "upload-example-1001",
  "workload_id": "prod-reports/report-writer",
  "tenant_pseudonym": "tenant-42",
  "source_region": "region-a",
  "destination_owner": "company-production",
  "destination_service": "approved-report-broker",
  "resource_alias": "compliance-reports",
  "operation": "upload",
  "classification": "Internal",
  "declared_bytes": 10485760,
  "observed_bytes": 10485760,
  "committed_object_bytes": 10485760,
  "decision": "ALLOW",
  "dlp_status": "SCAN_PASS",
  "policy_revision": "upload-prod-v3",
  "upload_status": "COMMITTED",
  "audit_completeness": "CONFIRMED"
}
~~~

Đây là **schema giả lập**, không đại diện cho định dạng API thực tế. Tách **declared_bytes, observed_bytes và committed_object_bytes** vì chúng có thể khác nhau. **DLP PASS** cũng chỉ có giá trị trong phạm vi scan đã xác định; không là bằng chứng dữ liệu vô hại tuyệt đối.

### 17.2. Đếm bytes đúng ranh giới

Nếu source NIC thấy **50 MiB egress** và NAT gateway cũng thấy **50 MiB**, không cộng thành **100 MiB data sent** vì có thể **đếm hai lần cùng traffic**. Nếu proxy có **retry**, total upstream bytes có thể cao hơn logical object bytes. Cần chỉ rõ:

1. **Accounting point**: app logical payload, proxy forwarded, network transfer hay storage committed.
2. **Aggregation interval và sampling status**.
3. **Direction và NAT mapping**.
4. **Retry/multipart/parallel upload** semantics.
5. **Reconciliation với object audit** theo request/object IDs.

### 17.3. Logs phải an toàn

Không log **raw Authorization headers, signed URL query strings, private keys, access tokens, full report body, unredacted DLP matches hoặc PII sample text** vào telemetry chung. Có thể ghi **policy ID, classification label, count/category, object alias/version, pseudonymous workload/tenant ID và decision**. Nếu DLP forensic evidence cần payload, lưu trong **quarantine có IAM, encryption, retention và chain of custody** phù hợp.

### 17.4. Alert theo quality của logging

Nếu upload proxy metrics đột ngột về 0 nhưng NAT egress vẫn tăng, đừng kết luận “workload không còn upload”. Có thể **proxy bypass, collector failure, log delivery mất quyền hoặc policy scope thay đổi**. Cần theo dõi **log volume drift, collection errors, parser errors, ingestion lag, unmonitored paths và object audit reconciliation**.

## 18. Threat detection: upload bất thường không luôn là exfiltration

**Network DLP monitoring** giúp phát hiện mẫu đáng kiểm tra nhưng **không thể tự xác minh dữ liệu đã bị rò** nếu chỉ thấy IP/port/bytes. Trước khi gắn nhãn sự cố, cần biết **workload owner, business schedule, data type, recipient, approval, kết quả upload và chất lượng telemetry**.

| Detection hypothesis | Tín hiệu | Đối chiếu bắt buộc | False positive điển hình |
| --- | --- | --- | --- |
| **Upload tới destination mới** | Host/bucket/account chưa từng có trong baseline | Asset inventory, partner onboarding, resource owner | Partner hợp lệ vừa chuyển region |
| **Egress bytes tăng mạnh** | Outbound volume vượt baseline cùng workload | Backup/ETL job, object audit, compression, retries | Release hoặc migration dữ liệu |
| **Nhiều upload nhỏ** | Nhiều requests/parts nhỏ liên tục | Multipart workflow ID, DLP metadata, app intent | Telemetry batching, artifact chunks |
| **Upload ngoài change window** | Công việc gửi dữ liệu trái lịch | Job scheduler, incident approval, JIT grant | Job bị trễ vì queue |
| **Đích shared SaaS không đúng tenant** | HTTP API hợp lệ nhưng workspace khác | SaaS tenant audit, signed recipient, role/scopes | Tenant ID mới do chuyển hệ thống |
| **Đọc secrets rồi tạo upload** | Workload đọc secret store và egress tăng | Secret manager audit, process/action, destination | Credential rotation hoặc backup hợp lệ |
| **DLP rule match** | Payload được thấy có pattern nhạy cảm | Source classification, false-positive corpus, ownership | Test fixtures, synthetic strings |
| **Proxy logs biến mất nhưng NAT còn traffic** | Không còn proxy access logs, egress vẫn có | Collection health, bypass path, route/policy changes | Logging outage, traffic không thuộc proxy scope |
| **Cloud API server-side transfer** | Object copy tới bucket/account khác | Object audit, IAM/action, source and destination | Approved cross-account migration |
| **Data export sau đổi IAM** | New writer permission + object write | Cloud audit, change ticket, data owner | Incident remediation hợp lệ |
| **Unknown protocol egress** | TCP/UDP không nằm trong allowlist | Workload spec, CNI, approved services | New dependency, monitoring agent |
| **Unusual upload failures** | 4xx/5xx, quota DENY liên tiếp | Retry logic, auth expiry, policy drift | Client bug, expired signed URLs |

### 18.1. Baseline theo workload và dữ liệu

Một **backup worker** thường upload hàng trăm GiB trong khung giờ định trước; một **frontend API** lẽ ra hầu như không upload database dumps. Dùng cùng một ngưỡng **500 MiB/ngày** cho cả hai dễ tạo **false positive** và **false negative**. Baseline nên xét:

- Workload/service/tenant/environment và nguồn credentials.
- Loại operation: upload report, backup snapshot, publish artifact, telemetry.
- Đích thuộc company/partner nào; account/bucket/workspace/region.
- Data sensitivity và loại nội dung.
- Lịch batch, thay đổi deployment, seasonal usage.
- Quota theo logical bytes, transfer bytes, request counts, errors.
- Sampling/log gaps và các đường không có L7 visibility.

### 18.2. Đừng tự động block toàn bộ CIDR dựa trên một cảnh báo

Một public IP shared CDN hoặc cloud platform có thể phục vụ nhiều tenants hợp lệ. Chặn cả IP vì một flow đáng ngờ có thể gây **outage dịch vụ công ty**, trong khi attacker vẫn dùng endpoint khác. Ưu tiên hành động **phạm vi hẹp**: chặn **workload principal, recipient account, upload operation, object prefix, token hoặc session cụ thể**, kết hợp mạng khi cần.

### 18.3. Cảnh báo chất lượng DLP

Theo dõi:

| Metric | Cảnh báo khi |
| --- | --- |
| DLP inspected bytes / eligible bytes | Tỷ lệ inspection giảm hoặc unknown tăng |
| Unsupported content type/format | Workload gửi nhiều payload không quét được |
| Proxy bypass egress count | Network flows không có proxy decision tương ứng |
| Upload bytes by workload and destination owner | Vượt baseline đã tính theo scope |
| Multipart open/aborted sessions | Nhiều parts chưa hoàn tất hoặc quota reservation lỗi |
| Object owner/account mismatch | Có writes tới account không được duyệt |
| Policy DENY and override counts | Tăng bất thường hoặc có exception ngoài change |
| DLP engine latency and availability | Rules bị bỏ vì timeout hoặc fallback |
| Scan false-positive rate | Người dùng cần review quá nhiều hoặc tắt kiểm soát |
| Effective block verification | Workload trái quyền vẫn upload thành công |

### 18.4. Nguồn chứng cứ phải độc lập khi có thể

Kết hợp **flow logs + proxy decision + object audit + application/business job context + IAM/control-plane changes**. Nếu tất cả logs chỉ dựa vào một client-supplied field, chúng không độc lập. Cũng đừng lấy **trạng thái quota DENY** để kết luận chắc không có upload qua **alternate path**.

## 19. Case study A: workload Prod gửi báo cáo tới bucket ngoài công ty

**Bối cảnh giả định:** Service **report-writer** trong namespace **prod-reports** được phép gửi kết quả hàng ngày lên object storage thuộc account Production. Một thay đổi cấu hình cho phép client truyền **destination_bucket** tùy ý. Egress chỉ lọc domain API của cloud provider, không kiểm tra bucket owner.

### 19.1. Vì sao nhiều lớp có thể vẫn báo ALLOW?

| Lớp | Quan sát | Vấn đề |
| --- | --- | --- |
| Pod NetworkPolicy | TCP/443 tới provider API ALLOW | Không phân biệt bucket/account |
| DNS/TLS | Domain chính thức, cert hợp lệ | Peer là provider, không chứng minh tenant |
| Generic proxy | HTTP PUT/POST tới host được phép | Không xác thực bucket owner trong payload/path |
| Cloud role hoặc signed URL | Có quyền ghi vào bucket đích | Quyền kỹ thuật tồn tại không đồng nghĩa business-approved |
| DLP | Scan không phát hiện PII pattern | File có thể chứa bí mật nghiệp vụ hoặc policy cho phép sai recipient |
| Storage audit | Object tạo thành công ở external account | Bằng chứng dữ liệu rời trust boundary |

### 19.2. Threat/data flow

~~~mermaid
flowchart LR
    A["Prod report-writer"] --> P["Generic egress proxy: allowed host"]
    P --> API["Cloud storage shared API"]
    API --> C["Company bucket: expected"]
    API --> U["Other account bucket: observed"]
    I["Workload credentials / delegated URL"] -. "Object write authorization" .-> U
~~~

### 19.3. Phân tích và xử lý

1. Cố định timeline **UTC, workload identity, job ID, application config revision, destination bucket/account và object version**.
2. Kiểm tra **storage audit** ở nơi có quyền hợp pháp để xác định object đã được tạo và bytes đã commit, không chỉ dựa flow egress.
3. Xác định **data classification, data owner và partner approval**; không lấy hostname provider làm bằng chứng owner.
4. Thu hồi **delegated URL, temporary credential hoặc resource policy grant** có thể ghi sai đích; chỉ cho broker generate approved recipient.
5. Giới hạn IAM **bucket/account/prefix** và egress route; sửa **server-side destination resolution**.
6. Kiểm thử **company bucket ALLOW**, **external bucket DENY**, **direct API bypass DENY**, và **multipart/server-side copy**.
7. Nếu xác nhận có rò dữ liệu, phối hợp **incident commander, data/privacy/legal owner**; không copy file đã lộ vào ticket chung.

### 19.4. Bài học

**Cloud provider API là một điểm mạng, không phải một người nhận duy nhất.** Với dịch vụ multi-tenant, cần **recipient identity và resource-scoped permissions** tại tầng ứng dụng/IAM, bên cạnh network controls.

## 20. Case study B: upload multipart vượt hạn mức một request

**Bối cảnh giả định:** Một policy chặn file lớn hơn **10 MiB/request**. Batch worker được phép upload tới approved endpoint, nhưng SDK dùng multipart, mỗi part **9 MiB**. Một job tạo **120 parts**, đưa khoảng **1.080 MiB** dữ liệu qua gateway trong cùng giờ. Mọi request riêng lẻ đều được báo ALLOW.

### 20.1. Phân biệt volume và content

\[
120 \times 9\ \mathrm{MiB} = 1080\ \mathrm{MiB} \approx 1{,}055\ \mathrm{GiB}
\]

Đây là **kết quả kích thước nội dung giả định**, không phải chứng cứ exfil. Job có thể upload artifact hợp lệ, nhưng **policy tổng volume nếu có** đã không được thực thi.

### 20.2. Các sai sót thường gặp

- Proxy chỉ kiểm tra **Content-Length từng request**.
- **Multipart upload ID** không được gắn với user/workload/recipient.
- Mỗi Pod replica có quota riêng, scale lên N replicas làm **quota tổng bị nhân N**.
- Retry parts khiến accounting **bị double count** hoặc bị bỏ tính.
- DLP scan từng part riêng, không quét **logical reassembled object**.
- Upload đã dùng **HTTP/2 streaming** nên gateway L4 không nhận biết từng object.

### 20.3. Sửa bằng chính sách toàn workflow

1. Giới hạn **per-part, per-object, per-workload/hour và per-recipient** theo mục tiêu business.
2. Dùng **quota ledger nhất quán** hoặc cơ chế reservation/commit với concurrency đúng.
3. Gắn **upload session ID/object key/tenant** và loại bỏ/abort khi tổng vượt policy.
4. Kiểm tra **complete upload** chỉ sau khi payload/manifest được chấp thuận.
5. Với dữ liệu nhạy cảm, yêu cầu scan/classification **trên logical object hoặc trước partition** cùng integrity binding.
6. Test 9 MiB **ALLOW nếu quota còn**, 11 MiB per-request **DENY**, nhiều parts vượt tổng **DENY**, retry idempotent, cleanup sau abort.

### 20.4. Bài học

**Max request size không phải tổng mức upload**. Multipart/chunking, retry, nhiều replicas và streaming cần **accounting xuyên request**. Đồng thời một quota đúng vẫn không thay kiểm tra loại dữ liệu và người nhận.

## 21. Case study C: telemetry vô tình gửi token ra SaaS bên thứ ba

**Bối cảnh giả định:** Một service API có thư viện telemetry mới. Khi request tới backend trả lỗi, thư viện thu thập **entire HTTP headers và body** rồi gửi vào SaaS observability mà tổ chức đã cho phép outbound TCP/443. Không ai cố ý tải file, nhưng **bearer tokens và dữ liệu cá nhân** xuất hiện trong telemetry.

### 21.1. Tại sao egress allowlist không bắt được?

SaaS endpoint là **approved destination**, outbound TLS hoạt động bình thường. Flow logs chỉ biết IP/port/bytes; WAF ở ingress có thể không ghi nhận cách ứng dụng **sao chép headers vào export payload**. Chính sách phải có **data-minimization và logging/redaction** ở nơi phát telemetry hoặc trong broker có quyền kiểm soát nội dung.

### 21.2. Cần thu thập gì?

| Nguồn | Giá trị |
| --- | --- |
| App release/dependency audit | Phiên bản telemetry SDK, option capture headers/body |
| App logs/traces schemas | Có raw Authorization/Cookie/query params hay không |
| SaaS tenant audit | Workspace, upload event, retention, exports, access |
| SIEM/DLP | Synthetic token marker, classification match và alert |
| IAM/secret manager | Token nào có thể bị lộ, scope, expiry và revocation |
| Cloud/network flow | Thời gian và destination SaaS; không phải dữ liệu payload chính xác |

### 21.3. Ứng phó

1. Vô hiệu hóa **unsafe capture** hoặc đổi sang allowlist telemetry fields, có change record.
2. Hạn chế quyền đọc SaaS logs và làm theo policy **delete/restrict exposure**, có đánh giá chain of copies/backups.
3. Xác định **credential bị lộ** qua restricted forensic review, revoke/rotate đúng scope; không phát tán raw token trong ticket.
4. Kiểm tra identity/session misuse ở API, không suy “chưa bị khai thác” chỉ vì không có network anomaly.
5. Thêm **schema-level redaction test dùng fake token markers** trong staging trước mỗi SDK update.
6. Thiết kế **approved telemetry fields, retention, tenant controls và data residency**.

### 21.4. Bài học

**Data loss có thể xảy ra qua đường đã được phê duyệt và traffic rất nhỏ.** Network quota và domain allowlist không thay thế **kiểm soát dữ liệu trước serialization, log redaction và SaaS tenant governance**.

## 22. Case study D: policy proxy bị bỏ qua sau thay đổi sidecar/IPv6

**Bối cảnh giả định:** Đội nền tảng bắt buộc mọi upload đi qua egress gateway. Sau rollout dual-stack, một số Pods gọi trực tiếp một external IPv6 address; các requests này không xuất hiện trong proxy logs. NAT IPv4 dashboards vẫn bình thường, khiến SOC chưa nhận thấy sự thay đổi.

### 22.1. Những giả thuyết cần xác minh

| Dấu hiệu | Giả thuyết | Evidence |
| --- | --- | --- |
| IPv6 egress bytes tăng | CNI/route/policy thiếu rule IPv6 | VPC/CNI flow logs IPv6, effective routes |
| Egress proxy logs không có request | Direct bypass, capture exclusion hoặc log gap | Sidecar config, CNI rules, proxy health |
| DNS AAAA record mới | Client chọn IPv6 thay IPv4 | Resolver cache, application/client connection metadata |
| App hoạt động bình thường | External endpoint reachable ngoài gateway | TLS peer, destination identity, object audit |
| Sidecar injection không đồng nhất | Pods cũ chưa rollout hoặc webhook lỗi | Effective Pod spec, capture readiness |

### 22.2. Kiểm soát và kiểm chứng

1. Inventory **IPv4/IPv6 routes, egress gateway enforcement, DNS AAAA, network/firewall policies, hostNetwork/Node-level paths**.
2. Kiểm tra **thực tế traffic đã qua proxy chưa**, không chỉ xem annotation “mesh enabled”.
3. Bổ sung **default deny network** ở mọi IP family và network scope cần kiểm soát, chỉ mở gateway/broker hợp lệ.
4. Test **allowed upload through gateway**, **direct IPv4/IPv6 DENY**, **DoH/alternate resolver** nếu chúng tạo đường bypass theo threat model.
5. Reconcile **proxy logs, CNI/flow logs và destination object audit** trước/sau rollout.
6. Sửa vùng cấu hình hẹp, canary và rollback không tái mở upload trái quyền.

### 22.3. Bài học

**Gateway policy chỉ bảo vệ những luồng thực sự đi qua gateway**. Cần kiểm tra **data plane enforcement**, không chỉ control-plane route, và bao phủ **IPv4, IPv6, mesh exclusions, direct IP và cloud-managed egress**.

## 23. Runbook: phát hiện, chặn và điều tra upload không được phép

### 23.1. Phân biệt ba mục tiêu

1. **Prevention:** Chặn upload trái chính sách **trước khi bytes rời trust boundary**, nếu điểm thực thi có thể thấy và quyết định.
2. **Containment:** Khi phát hiện bất thường đã diễn ra, giảm khả năng tiếp tục upload bằng **identity/resource/network restrictions** có scope.
3. **Investigation and recovery:** Xác minh dữ liệu/đích bị ảnh hưởng, bảo toàn bằng chứng, phục hồi workflow hợp lệ và khắc phục đường bypass.

**Một lệnh chặn network sau sự kiện không thu hồi được dữ liệu đã tới bên nhận.** Nếu object đã commit tại external bucket, cần quy trình incident/data owner/legal/privacy thích hợp; không xóa dấu vết hoặc gửi thêm dữ liệu để “thử”.

### 23.2. Quy trình quyết định

~~~mermaid
flowchart TD
    A["Alert upload bất thường / DLP match"] --> B["Verify source, workload, data classification"]
    B --> C{"Recipient / operation trái policy?"}
    C -- "Chưa rõ" --> D["Correlate object audit, broker and app workflow"]
    D --> C
    C -- "Không" --> E["Approve/close with baseline, monitor"]
    C -- "Có hoặc verified leak" --> F["Contain: narrow identity/resource/network scope"]
    F --> G["Preserve logs, trace signed URL and object version"]
    G --> H["Classify exposure, owner and recipient"]
    H --> I["Revoke/rotate, close bypass, remediate"]
    I --> J["Test authorized ALLOW and unauthorized DENY"]
    J --> K["Restore workflow, postmortem and owners"]
~~~

### 23.3. Các bước vận hành chi tiết

**Bước 1 — Xác định đúng đối tượng.** Ghi **cloud account/project/subscription, cluster/namespace/Pod UID hoặc VM/function ID, ServiceAccount/IAM role, job ID, UTC event window, data owner và classification**. Tránh attribution chỉ theo public NAT IP hoặc Pod IP hiện tại.

**Bước 2 — Kiểm tra chất lượng quan sát.** Flow logs có sampling không? Proxy access logs có đủ không? Object store audit có bật cho đúng bucket? DLP thấy plaintext hay chỉ metadata? Logging có delay hay pipeline gap? Ghi nhãn **observed/estimated/unknown**.

**Bước 3 — Xác định destination thật.** Không dừng ở **Host/IP**. Xác định **SaaS tenant, cloud account, bucket/container, object key/version, region, signed URL issuer và resource policy** khi có bằng chứng.

**Bước 4 — Xác định data.** Ưu tiên **metadata/data owner/classification** từ nguồn đáng tin; nếu phải inspect payload thì theo phạm vi cho phép, hạn chế lộ PII/secrets và lưu evidence ở khu vực có quyền. So sánh **hash/object version** nếu kiểm tra pre-upload đã thực hiện.

**Bước 5 — Chặn có chọn lọc.** Thu hồi quyền **PutObject** sai bucket, revoke delegated URLs/token khi hỗ trợ, giảm quyền workload, chặn direct egress path, quarantine Pod/job/identity theo mức độ. Tránh chặn toàn bộ cloud provider IP hoặc đóng Internet cho các dịch vụ không liên quan khi có cách hẹp hơn.

**Bước 6 — Đối chiếu completion.** Phân biệt **attempt, accepted by gateway, bytes forwarded, upload completed, object created, object copied, data accessed by recipient**; không dùng HTTP 200 ở proxy thay cho object commit nếu workflow có bước Complete riêng.

**Bước 7 — Phục hồi workflow hợp lệ.** Phát hành credentials mới đúng scope, tạo route/exception đã duyệt, thử **ALLOW approved data/object** và **DENY unapproved data/destination**, đo latency/throughput và xác nhận logging.

**Bước 8 — Postmortem.** Ghi policy owner, IAM/capture/scan gaps, detection latency, recipients/data scope, false positives, thay đổi cần thực hiện, kỳ hạn và test regression.

### 23.4. Phân vai

| Vai trò | Trách nhiệm |
| --- | --- |
| **Incident commander / SOC** | Điều phối rủi ro, severity, evidence và phương án containment |
| **Data owner / privacy** | Data classification, approved recipient, nghĩa vụ thông báo |
| **Application owner** | Export workflow, job identity, business SLI, retry/idempotency |
| **Cloud/IAM team** | Cloud roles, bucket/account/resource policies, token/URL revocation |
| **Network/platform team** | CNI, firewall, egress gateway, routes, direct path, IPv4/IPv6 |
| **DLP/security engineering** | Scan scope, rule accuracy, quarantine và false positive triage |
| **Legal/compliance** | Pháp lý/hợp đồng/retention/thông báo theo chính sách tổ chức |

### 23.5. Mẫu incident record

~~~text
INCIDENT / CHANGE ID:
OWNER / APPROVAL / UTC WINDOW:
WORKLOAD ID / POD UID / SERVICEACCOUNT / CLOUD ROLE:
SOURCE ENV / CLUSTER / ACCOUNT / IP FAMILY:
RECIPIENT CLOUD ACCOUNT / SAAS TENANT / BUCKET / OBJECT:
DATA CLASSIFICATION / OWNER / APPROVED PURPOSE:
OBJECT HASH/VERSION OR SENSITIVE EVIDENCE REFERENCE (NO PAYLOAD):
TRANSPORT: HTTPS, CONNECT, gRPC, multipart, server-side copy:
NETWORK POINT: CNI, gateway, firewall/NAT, flow log:
POLICY: revision, IAM grants, upload quotas, DLP rule:
OBSERVATIONS: request, bytes forwarded, scan result, object commit:
CONFIDENCE / LOG COVERAGE / KNOWN GAPS:
CONTAINMENT: identity, recipient, gateway, routes, revocation:
ALLOW/DENY REGRESSION / BUSINESS SLI / SAFE ROLLBACK:
PENDING ACTIONS / RESPONSIBLE OWNERS:
~~~

### 23.6. Giới hạn thu hồi

Xóa một Pod hoặc tắt workload identity **không xóa các bản sao dữ liệu đã được tải lên**. Revoke token có thể có độ trễ vì **TTL/verifier cache/external STS sessions**. Object đã copy tới recipient có thể được sao chép thêm. Báo cáo phải phân biệt **đã chặn đường upload mới**, **credential cũ thực sự bị từ chối**, **dữ liệu ngoài kiểm soát** và **phạm vi chưa xác định**.

## 24. Lab Python offline: quyết định upload theo workload và recipient

Lab hoàn toàn **không mở socket, không quét IP, không gọi cloud API, không đọc tệp, không tải dữ liệu và không cần secrets thật**. Toàn bộ input là các object dữ liệu minh họa trong source code. Mục tiêu: kiểm tra **thứ tự policy**, phân biệt **DENY do quyền/dữ liệu/recipient/quota**, và không tin một upload chỉ vì không vượt hạn mức.

### 24.1. Đầu vào

Mỗi **UploadRequest** mang các thông tin đã được giả định là có thể kiểm chứng:

| Field | Vai trò | Giới hạn |
| --- | --- | --- |
| workload | Identity từ nguồn tin cậy giả định | Code không xác minh token chữ ký |
| destination_owner | Cloud account/SaaS tenant được phê duyệt | Code không tra provider ownership |
| object_prefix | Phạm vi object được phép ghi | Code không thực hiện IAM |
| data_class | Nhãn được gán đáng tin theo giả định | Code không chạy DLP thật |
| requested_bytes | Kích thước **logical upload** dự kiến | Code không stream/count actual bytes |
| used_bytes_this_hour | Tổng đã sử dụng trong kỳ kế toán giả định | Code không có distributed atomic ledger |
| dlp_status | PASS/BLOCK/UNKNOWN giả lập | Code không scan nội dung |
| tls_verified | Peer verification theo giả định | Code không thực hiện TLS handshake |
| authorized | Workload được cấp write permission | Không phải bằng chứng IAM ngoài lab |

### 24.2. Source code minh họa Python 3.10+

~~~python
from dataclasses import dataclass, replace
from enum import Enum


MIB = 1024 * 1024
MAX_REQUEST = 50 * MIB
MAX_HOURLY = 200 * MIB


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class UploadRequest:
    workload: str
    destination_owner: str
    object_prefix: str
    data_class: str
    requested_bytes: int
    used_bytes_this_hour: int
    dlp_status: str
    tls_verified: bool
    authorized: bool


APPROVED_WORKLOAD = "prod-reports/report-writer"
APPROVED_OWNER = "company-production"
APPROVED_PREFIX = "reports/daily/"
APPROVED_CLASSES = {"Public", "Internal"}


def evaluate(request: UploadRequest) -> tuple[Decision, str]:
    # Hard denials come first. A small file cannot bypass authorization.
    if not request.authorized:
        return (Decision.DENY, "NO_WORKLOAD_PERMISSION")

    if request.workload != APPROVED_WORKLOAD:
        return (Decision.DENY, "UNAPPROVED_WORKLOAD")

    if request.destination_owner != APPROVED_OWNER:
        return (Decision.DENY, "UNAPPROVED_RECIPIENT")

    if not request.object_prefix.startswith(APPROVED_PREFIX):
        return (Decision.DENY, "OBJECT_PREFIX_NOT_ALLOWED")

    if not request.tls_verified:
        return (Decision.DENY, "TLS_PEER_NOT_VERIFIED")

    if request.data_class not in APPROVED_CLASSES:
        return (Decision.DENY, "DATA_CLASS_NOT_ALLOWED")

    if request.requested_bytes < 0 or request.used_bytes_this_hour < 0:
        return (Decision.DENY, "INVALID_ACCOUNTING")

    if request.requested_bytes > MAX_REQUEST:
        return (Decision.DENY, "REQUEST_SIZE_EXCEEDED")

    if (
        request.used_bytes_this_hour + request.requested_bytes
        > MAX_HOURLY
    ):
        return (Decision.DENY, "HOURLY_BUDGET_EXCEEDED")

    if request.dlp_status == "BLOCK":
        return (Decision.DENY, "DLP_BLOCK")

    if request.dlp_status != "PASS":
        # Never silently equate unsupported/timeout with a clean scan.
        return (Decision.REVIEW, "DLP_NOT_VERIFIED")

    return (Decision.ALLOW, "POLICY_CHECKS_PASSED")


base = UploadRequest(
    workload="prod-reports/report-writer",
    destination_owner="company-production",
    object_prefix="reports/daily/2026-11-28.csv",
    data_class="Internal",
    requested_bytes=10 * MIB,
    used_bytes_this_hour=50 * MIB,
    dlp_status="PASS",
    tls_verified=True,
    authorized=True,
)

cases = {
    "approved": base,
    "wrong_owner": replace(base, destination_owner="external-account"),
    "wrong_workload": replace(base, workload="dev/debugger"),
    "secret_data": replace(base, data_class="Restricted"),
    "too_large": replace(base, requested_bytes=51 * MIB),
    "hourly_quota": replace(
        base,
        used_bytes_this_hour=195 * MIB,
    ),
    "dlp_unknown": replace(base, dlp_status="UNKNOWN"),
    "dlp_block": replace(base, dlp_status="BLOCK"),
    "no_permission": replace(base, authorized=False),
}

for label, item in cases.items():
    decision, reason = evaluate(item)
    print(label, decision.value, reason)

assert evaluate(cases["approved"])[0] == Decision.ALLOW
assert evaluate(cases["wrong_owner"])[1] == "UNAPPROVED_RECIPIENT"
assert evaluate(cases["wrong_workload"])[0] == Decision.DENY
assert evaluate(cases["secret_data"])[1] == "DATA_CLASS_NOT_ALLOWED"
assert evaluate(cases["too_large"])[1] == "REQUEST_SIZE_EXCEEDED"
assert evaluate(cases["hourly_quota"])[1] == "HOURLY_BUDGET_EXCEEDED"
assert evaluate(cases["dlp_unknown"])[0] == Decision.REVIEW
assert evaluate(cases["dlp_block"])[0] == Decision.DENY
assert evaluate(cases["no_permission"])[0] == Decision.DENY
~~~

Kết quả dự kiến:

~~~text
approved ALLOW POLICY_CHECKS_PASSED
wrong_owner DENY UNAPPROVED_RECIPIENT
wrong_workload DENY UNAPPROVED_WORKLOAD
secret_data DENY DATA_CLASS_NOT_ALLOWED
too_large DENY REQUEST_SIZE_EXCEEDED
hourly_quota DENY HOURLY_BUDGET_EXCEEDED
dlp_unknown REVIEW DLP_NOT_VERIFIED
dlp_block DENY DLP_BLOCK
no_permission DENY NO_WORKLOAD_PERMISSION
~~~

### 24.3. Đọc kết quả một cách chính xác

- **ALLOW** chỉ là kết luận của hàm policy giả lập; không chứng minh object đã upload thành công.
- **REVIEW** nghĩa là **chưa được phép xuất**, chỉ được chuyển sang luồng review/quarantine theo policy, **không coi là ALLOW ngầm**.
- **DENY wrong_owner** cho thấy hostname/cổng/TLS không đủ thay destination ownership.
- **DENY secret_data** xảy ra dù file chỉ **10 MiB**, vì kích thước không quyết định mức nhạy cảm.
- **DENY hourly_quota** dùng tổng 195 MiB đã tiêu thụ + 10 MiB mới = 205 MiB, vượt ngưỡng 200 MiB minh họa.

### 24.4. Giới hạn thiết yếu

1. **Không xác thực resource ownership thật**: nhãn destination_owner và authorized được tin trước khi gọi hàm.
2. **Không nhận biết multipart/chunked streaming**: số requested_bytes chỉ là dữ liệu khai báo.
3. **Không có concurrency/atomic accounting**: hai requests song song có thể cùng đọc used_bytes cũ và vượt quota trong hệ thật.
4. **Không quét plaintext**, xử lý archive/compression, URL redirect, TLS pinning, ECH hay gRPC.
5. **Không triển khai cloud IAM, K8s NetworkPolicy, EDR/SIEM, DLP scanner hoặc ZTNA**.
6. **Không tính quota theo tenant/recipient/account window** ngoài một field giả định.
7. Prefix string check trong lab **không phải canonical resource validation**: trong hệ thật phải xác định canonical bucket/key, encoding, path/resource semantics từ provider, chống ambiguity.
8. **Không có workflow approval/JIT, signed URLs, object commit/rollback, classification provenance hoặc versioning**.

### 24.5. Bài tập mở rộng

1. Thêm **logical bytes, transfer bytes, committed bytes** và giải thích khác nhau khi compression/retry.
2. Thêm **multipart session ID**, kiểm tra quota xuyên parts và object complete.
3. Thêm **tenant-specific budget**, với approved recipient và data owner riêng từng tenant.
4. Thêm **UTC event time**, token validity/TTL và policy revision theo incident timeline.
5. Thêm **DLP NOT_SUPPORTED/ERROR** và fail-closed khi dữ liệu restricted.
6. Thêm **server-side copy operation**, không có workload egress bytes nhưng vẫn phải kiểm tra account/object policy.
7. Thêm **idempotency key** và mô phỏng retry không double count.
8. Mô phỏng **IPv4/IPv6 direct egress bypass** với boolean effective_gateway_enforced, nhưng không tạo kết nối thật.
9. Thiết kế audit event chỉ có **decision reason/category**, không chứa payload/token.
10. Thêm **test suite ALLOW/DENY** cho mọi hard-deny rules và false-positive review path.

## 25. Ma trận kiểm thử egress/upload controls

Các ca này dành cho **lab, staging hoặc tài nguyên thuộc phạm vi được cấp quyền**. Dùng **dữ liệu tổng hợp và endpoints thử nghiệm do tổ chức sở hữu**; không đưa PII, private keys hoặc dữ liệu production vào công cụ/đích bên ngoài để “kiểm tra DLP”. Test liên quan **firewall, route, credential revoke, API upload, DR** phải có approval, scope, quota, business SLI, safe rollback.

| Test ID | Tình huống | Expected result/evidence |
| --- | --- | --- |
| EG-01 | Workload report-writer có identity đúng | ALLOW upload approved Internal report tới approved broker |
| EG-02 | Dev workload dùng cùng network egress | DENY do workload/resource authorization |
| EG-03 | ServiceAccount không có quyền object write | DENY tại IAM/resource API dù network reachable |
| EG-04 | Prod report-writer thử external account bucket | DENY theo owner/account, không dựa duy nhất Host |
| EG-05 | Workload gửi Restricted data dù chỉ 1 KiB | DENY theo data policy; quota nhỏ không thay DLP |
| EG-06 | DLP scanner trả UNKNOWN/timeout | REVIEW/quarantine hoặc DENY theo sensitivity; không auto ALLOW |
| EG-07 | DLP rule match fake synthetic secret | DENY có audit category, không ghi raw marker trong production log |
| EG-08 | Upload file Internal hợp lệ | ALLOW chỉ sau classification và recipient validation |
| EG-09 | Thiết bị/Pod thay IP nhưng identity không đổi | Policy theo identity vẫn đúng, có historical mapping |
| EG-10 | NAT public IP được dùng chung nhiều workloads | Không gán upload cho một Pod chỉ từ NAT IP |
| EG-11 | Kubernetes egress default deny | Direct outbound unknown IP/port DENY khi CNI hỗ trợ |
| EG-12 | Pod → approved upload broker TCP/443 | ALLOW, broker thực hiện authentication/authorization |
| EG-13 | DNS resolution qua approved resolver | ALLOW cần thiết; không mở mọi TCP/443 từ Pod |
| EG-14 | Direct DNS tới resolver khác | DENY theo egress policy phù hợp |
| EG-15 | DoH/DoT alternative resolver | Không tạo đường bypass nếu nằm ngoài approved egress |
| EG-16 | Upload direct Pod IP / external IP literal | DENY nếu không qua broker/gateway |
| EG-17 | IPv6 AAAA/destination | IPv6 egress áp policy tương đương IPv4 |
| EG-18 | HostNetwork workload | Có enforcement riêng, không mặc định Pod policy bao phủ |
| EG-19 | Sidecar/egress gateway route bị thiếu | Workload không fail-open direct Internet |
| EG-20 | Proxy HTTP CONNECT tới allowed provider | Không coi CONNECT ALLOW là nội dung upload sạch |
| EG-21 | Redirect HTTPS sang unapproved hostname | DENY redirect destination, không chuyển Authorization token |
| EG-22 | SNI đúng nhưng HTTP authority/recipient khác | Policy không tin mỗi SNI để định danh bucket |
| EG-23 | TLS peer verification thất bại | DENY, không sử dụng insecureSkipVerify để chữa lỗi |
| EG-24 | ECH/unknown SNI metadata | Áp approved destination/resource controls khác; không mặc định ALLOW |
| EG-25 | HTTP PUT trong approved workflow | ALLOW nếu identity, class, recipient, quota đạt |
| EG-26 | HTTP POST JSON chứa fake Restricted field | DLP/application policy DENY dù không có filename |
| EG-27 | PATCH, WebSocket, gRPC streaming | Chính sách phương thức/giao thức đúng; unknown không bypass |
| EG-28 | HTTP/2 multiple streams | Quota tính đúng theo request/stream, không chỉ TCP connection |
| EG-29 | HTTP chunked không có Content-Length | Actual streamed bytes được đo/limit nếu proxy hỗ trợ |
| EG-30 | Per-request 51 MiB với limit 50 MiB | DENY theo byte measurement đúng, không chỉ client claim |
| EG-31 | Multipart 100 parts hợp lệ riêng, tổng vượt budget | DENY/abort theo aggregate object/workload quota |
| EG-32 | Resume upload từ offset cũ | Không vượt object/session quota hoặc thay recipient |
| EG-33 | Retry part do network timeout | Idempotency/accounting đúng, không double count sai |
| EG-34 | Parallel replicas cùng upload | Atomic/shared quota không bị nhân lên theo số replicas |
| EG-35 | Abort multipart giữa chừng | Cleanup orphaned parts, update quota reservations, log status |
| EG-36 | Compression ratio cao | Logical data size/scan không suy từ compressed bytes duy nhất |
| EG-37 | Encrypted archive mà DLP không thể inspect | UNKNOWN/REVIEW hoặc DENY theo policy |
| EG-38 | Content đã scan rồi bị thay trước upload | Hash/object version binding phát hiện TOCTOU |
| EG-39 | Signed upload URL hết hạn | DENY đúng resource, không tự mở quyền vô hạn |
| EG-40 | Signed URL có bucket/account ngoài allowlist | Broker DENY trước khi cấp; tránh arbitrary client destination |
| EG-41 | URL/query chứa credential | Không xuất raw signed query params vào logs/traces |
| EG-42 | Server-side CopyObject/compose sang account khác | Resource policy DENY, object audit phát hiện dù Pod egress nhỏ |
| EG-43 | Cloud private endpoint tới external tenant | Không mặc định ALLOW chỉ vì private network path |
| EG-44 | SaaS domain đúng nhưng workspace sai | SaaS tenant restriction/resource auth DENY |
| EG-45 | Telemetry SDK export raw Authorization header | Redaction trước upload; scan với fake tokens được kiểm soát |
| EG-46 | Object store PUT accepted, Complete multipart chưa chạy | Không ghi committed object success sai |
| EG-47 | Proxy 200 nhưng object store trả lỗi | Audit phân biệt forwarded bytes, object commit, app outcome |
| EG-48 | VPC flow log có sampled/skip records | Điều tra ghi giới hạn, không kết luận không traffic |
| EG-49 | NAT có bytes nhưng proxy logs trống | Phát hiện bypass hoặc collector/logging error |
| EG-50 | Cloud role/bucket policy thay đổi ngoài change | Audit/alert và entitlement review theo owner |
| EG-51 | Policy failover sang DR region | Đồng bộ approved recipients, keys, egress routes, IPv6, logs |
| EG-52 | Quota/DLP engine outage | Approved failure policy không wildcard fail-open |
| EG-53 | DLP false positive trên synthetic non-sensitive file | Review/exception có thời hạn, không tắt scan toàn Prod |
| EG-54 | Credential hoặc signed URL bị revoke | New object writes bị DENY theo provider semantics |
| EG-55 | Batch hợp lệ vượt quota do growth | Có workflow request approval/tune limits, không sửa YAML tùy tiện |
| EG-56 | Direct production export sau policy deployment | ALLOW đúng workflow, DENY các đường bypass đã ghi trong threat model |
| EG-57 | Data owner đổi classification trong runtime | DLP/job policy re-evaluate, không dùng nhãn cache cũ vô hạn |
| EG-58 | Product proxy log schema đổi version | Parser phát hiện, decision quality không bị giả ALLOW |
| EG-59 | Proxy inspect từ account có dữ liệu privacy nhạy cảm | Policy/consent/retention, scope và log access bảo vệ |
| EG-60 | Incident khôi phục upload broker | Object audit reconciliation, ALLOW hợp lệ và DENY trái quyền cùng đạt |

### 25.1. Mẫu test record

~~~text
TEST / CHANGE ID / OWNER / APPROVER:
ENV / CLUSTER / NAMESPACE / POD UID / IAM PRINCIPAL:
WORKLOAD ID / DEPLOYMENT VERSION / DATA OWNER:
RECIPIENT SERVICE / ACCOUNT / TENANT / BUCKET / OBJECT:
DATA LABEL / CLASSIFICATION / APPROVED PURPOSE:
PROTOCOL: HTTP, gRPC, WS, TCP, QUIC, object API:
REQUEST/UPLOAD ID / PART / OBJECT VERSION:
EXPECTED MAX REQUEST, MAX OBJECT, HOURLY BUDGET:
NETWORK ENFORCEMENT: CNI / SG / EGRESS PROXY / IPv4/IPv6:
APPLICATION, DLP, IAM, RESOURCE POLICY REVISIONS:
EXPECTED ALLOW/DENY/REVIEW:
OBSERVED: request bytes, forwarded bytes, committed bytes:
OBJECT AUDIT / PROXY LOG / FLOW LOG / DLP DECISION:
LOGGING QUALITY AND TIMESTAMPS UTC:
ACTUAL RESULT / GAP / FALSE POSITIVE:
ROLLBACK, RETEST, REMEDIATION, BUSINESS SLI:
~~~

### 25.2. Những bài test không được thay thế nhau

- **ALLOW app→broker** không chứng minh **DENY app→Internet direct IP**.
- **DENY external hostname** không chứng minh **DENY external bucket cùng hostname provider**.
- **DLP PASS cho plaintext** không chứng minh ciphertext/archive sẽ được kiểm tra.
- **HTTP request nhỏ** không chứng minh một multipart workflow nằm trong quota.
- **Flow log ACCEPT** không chứng minh storage object đã được commit.
- **Proxy deny log** không chứng minh alternate IPv6/managed cloud API path cũng bị chặn.
- **Quyền IAM hẹp** không chứng minh ứng dụng đã khử danh tính dữ liệu trước upload.

## 26. Mô hình triển khai tham chiếu theo mức nhạy cảm

### 26.1. Ba cấu hình minh họa

| Khả năng | Telemetry Internal | CI artifact | Customer Confidential export |
| --- | --- | --- | --- |
| Workload identity | Dedicated telemetry role | Dedicated CI job identity | Dedicated approved export role |
| Destination | Approved observability tenant | Company registry/project | Partner/bucket/account cụ thể |
| Content policy | Schema allowlist, redact tokens | Artifact signing/scan provenance | Data owner approval + preupload DLP |
| Network policy | Collector-only egress | Registry/broker-only egress | Broker-only, direct egress DENY |
| Quota | Rate and volume by workload | Object size/repo and daily budget | Object/recipient/session and approval limit |
| Resource auth | SaaS tenant restriction | Repository push only | Restricted account/object/prefix write |
| TLS | Verified server peer | Verified registry + scoped credential | Verified endpoint and possibly mTLS |
| Audit | Fields/volume without payload | Artifact digest, builder, registry event | Object version, approval, classification, provenance |
| Failure response | Bounded queue/redact/drop per policy | Retry with idempotency | Quarantine/DENY if classification unavailable |

### 26.2. Thứ tự triển khai

1. **Discovery:** Inventory workloads, outgoing destinations, cloud accounts, APIs, telemetry collectors, backup services và egress paths.
2. **Data classification:** Xác định data owners, loại dữ liệu, approved exports và những đích được phép.
3. **Identity:** Cấp IAM/ServiceAccount/mesh identity riêng cho từng workload/environment.
4. **Observe-only phase có giới hạn:** Thu metadata, hiểu legitimate traffic và false positives; không gửi raw data nhạy cảm vào SIEM.
5. **Destination restriction:** Chặn unknown egress ở CNI/cloud firewall, cấp đường tới broker/gateway cần thiết.
6. **Resource policy:** Giới hạn object store/SaaS tenant và API actions theo chủ sở hữu.
7. **Content policy:** Scan ở app/broker có visibility đúng; chọn deny/quarantine/approval.
8. **Aggregate quota:** Thiết lập per-object/per-workload/per-recipient logical + transfer accounting.
9. **Canary enforcement:** Test chức năng hợp lệ lẫn đường trái phép, đo SLO và rollback.
10. **Production scale:** Mở rộng scope từng namespace/account/region với alert quality và config drift.
11. **Audit reconciliation:** So application decisions, proxy bytes, storage commits và IAM events.
12. **Operational review:** Quản lý ngoại lệ, revoke leaked credentials, update owners và test định kỳ.

### 26.3. Điều kiện phải xác minh trước khi gọi giải pháp “bảo vệ upload”

Một kiến trúc đạt mục tiêu khi:

- App hợp lệ vẫn **upload được đúng object vào đúng account/tenant**, với latency/throughput trong SLO.
- Workload sai identity/tenant, dữ liệu trái classification hoặc đích ngoài allowlist **bị từ chối**.
- **Direct network bypass/alternate protocol/IPv6** không vượt qua policy bắt buộc.
- **Actual streaming/multipart bytes và object commits** được accounting đúng.
- Policy **failures, unknown classification và telemetry gaps** không âm thầm chuyển thành ALLOW.
- SOC có **decision evidence không chứa secrets**, có cách xác định recipient/data owner và xử lý sự cố.

### 26.4. Ngoại lệ upload lớn cần chính sách riêng

Backup, data migration, machine-learning artifacts hoặc incident forensics có thể hợp lệ với dữ liệu rất lớn. Thay vì tắt mọi quota:

- Cấp **temporary exception** theo workload, source dataset, destination owner, size/time window và approver.
- Chỉ cho đúng **object namespace** và operation được cấp.
- Ghi **data classification, encryption/retention/region** và trách nhiệm bên nhận.
- Dùng **quota phù hợp riêng cho job** và rate scheduling để tránh overload.
- Kết thúc exception tự động, retire credentials/URLs và review object audit.

**Ngoại lệ phải giải quyết nhu cầu cụ thể, không tạo wildcard upload** cho toàn namespace hoặc cloud provider.

## 27. Những hiểu nhầm phổ biến khi giới hạn upload

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Upload nghĩa là chỉ HTTP POST file.” | PUT, PATCH, streaming, multipart, JSON, SFTP và nhiều protocol khác cũng truyền dữ liệu. |
| “HTTPS tự ngăn dữ liệu rò.” | TLS bảo mật đường truyền tới peer, không quyết định liệu recipient có được phép nhận hay không. |
| “Chặn port 443 là chặn mọi upload.” | Giao thức có thể dùng cổng khác; chặn 443 phá cả API hợp lệ mà vẫn còn đường khác. |
| “Cho phép provider domain nghĩa là cho phép company bucket.” | Cloud provider thường multi-tenant; phải xác minh bucket/account owner. |
| “Private endpoint đồng nghĩa data không rời trust boundary.” | Dữ liệu vẫn có thể sang account/tenant khác qua dịch vụ được chia sẻ. |
| “NetworkPolicy đọc được file/PII.” | NetworkPolicy chuẩn là network selectors/ports, không phải content DLP. |
| “FQDN policy có sẵn trong Kubernetes NetworkPolicy chuẩn.” | Cần implementation/CNI extension nếu muốn rule theo tên miền. |
| “Có sidecar là mọi egress đi qua sidecar.” | Capture, hostNetwork, exclusions, IPv6, protocols và CNI phải được kiểm chứng. |
| “Egress gateway tồn tại là không thể đi trực tiếp.” | Cần CNI/SG/route enforcement và test bypass. |
| “DNS filtering ngăn mọi upload tới domain cấm.” | Direct IP, cache, DoH/DoT, proxy khác và tunneling có thể bypass nếu route mở. |
| “Mọi HTTPS payload đều được proxy scan.” | CONNECT/TLS passthrough không cho proxy thấy body. |
| “Proxy thấy SNI nên biết bucket đích.” | SNI không chứng minh HTTP path, tenant hoặc resource owner. |
| “SNI luôn hiển thị trong TLS.” | Visibility phụ thuộc protocol/handshake/ECH/inspection và implementation. |
| “Đã DLP PASS thì dữ liệu chắc chắn an toàn.” | Coverage, classifier accuracy, supported formats và authorization vẫn giới hạn. |
| “File đã mã hóa vẫn được DLP kiểm tra nội dung như plaintext.” | Nếu không giải mã hợp pháp được, content scanner có thể mù. |
| “Base64/ZIP không đổi tính chất dữ liệu.” | Data vẫn nhạy cảm; detectors có thể bỏ sót hoặc cần decode với giới hạn an toàn. |
| “Content-Length nhỏ hơn limit là request sẽ luôn nhỏ.” | Chunked/HTTP2 stream hoặc header không đáng tin cần actual byte measurement. |
| “Một request dưới 10 MiB nghĩa là cả upload dưới 10 MiB.” | Multipart/resumable upload có nhiều requests/parts. |
| “Một TCP connection tương ứng một object upload.” | HTTP/2 multiplex nhiều streams, connection pool chứa nhiều requests. |
| “Quota một Pod chính là quota toàn service.” | Scale/regions tạo nhiều instances; accounting phải nhất quán. |
| “Upload thất bại thì không tính bytes nào.” | Dữ liệu có thể đã forwarded/received dù object chưa committed; định nghĩa metric rõ. |
| “Egress network bytes = object logical bytes.” | Compression, headers, retries, TLS và copy nội bộ làm hai số khác nhau. |
| “Dữ liệu nhỏ không thể là exfiltration.” | Một token/private key vài KB cũng rất nhạy cảm. |
| “Bytes cao chắc chắn là exfiltration.” | Backup, migration, artifact publishing có thể hợp lệ. |
| “Quét mỗi multipart part đủ cho logical object.” | Reassembly, cross-part content và total classification có thể khác. |
| “Scan file A đảm bảo file B cùng tên cũng sạch.” | Cần immutable version/hash binding để ngăn TOCTOU. |
| “Signed URL luôn giới hạn kích thước và chỉ dùng một lần.” | Phụ thuộc provider/scheme; xác minh expiry, scope và replay semantics. |
| “Có signed URL hợp lệ là recipient được business phê duyệt.” | URL có thể trỏ tới bucket/tenant không được phép. |
| “Chặn upload ở proxy cũng chặn cloud server-side copy.” | Resource-side API operations có thể truyền dữ liệu không đi qua workload. |
| “Source NAT public IP xác định một Pod duy nhất.” | Nhiều workloads dùng chung NAT; cần mapping và identity theo thời gian. |
| “Không có proxy logs nghĩa là không có upload.” | Có thể bypass, sampling, logging outage, alternate data path. |
| “Flow log ACCEPT nghĩa là upload thành công.” | Chỉ là quan sát network/policy tại điểm log, không chứng minh object committed. |
| “Storage HTTP 200 nghĩa là full multipart upload hoàn tất.” | Có thể mới upload part; cần completion/object audit. |
| “Cloud role có quyền PutObject là đã đủ về DLP.” | IAM quản lý resource actions, không tự phân loại nội dung. |
| “DLP phải đọc toàn bộ dữ liệu người dùng để hiệu quả.” | Cần data minimization và scanning đúng điểm/có quyền, cân bằng privacy. |
| “Nếu DLP outage, cứ allow toàn bộ để đảm bảo uptime.” | Failure policy theo sensitivity; restricted external upload cần fail closed. |
| “Một rule DLP báo sai thì nên tắt toàn bộ DLP.” | Có workflow review, test corpus, exception hẹp, expiry và owner. |
| “Chặn IP cloud provider nghi ngờ sẽ xử lý gọn.” | Shared endpoints có thể gây outage lớn; ưu tiên identity/resource/tenant scope. |
| “Log raw signed URL giúp điều tra hơn.” | URL có thể là bearer credential; cần redact và audit metadata. |
| “Public source IP trong log là xác thực danh tính.” | IP là network metadata, không phải cryptographic workload identity. |
| “Dev và Prod cùng bucket/role vẫn an toàn nếu dùng TLS.” | TLS không thay IAM, tenant/environment isolation. |
| “Đã cập nhật egress policy là mọi Pod/region áp ngay.” | Cần kiểm tra effective CNI/proxy/firewall config và propagation. |
| “Chỉ kiểm tra IPv4 là đủ.” | IPv6, managed services và multi-region có thể có đường riêng. |
| “Post-upload scan ngăn dữ liệu ra external recipient.” | Nếu bên ngoài đã nhận bytes, scan sau chỉ giúp phát hiện/phản ứng. |
| “Không thấy DLP alert chứng minh dữ liệu sạch.” | Pipeline có thể thiếu log, scan unsupported hoặc false negative. |

## 28. Câu hỏi ôn tập và bài tập thiết kế

1. **Giới hạn upload từ workload gồm những trục nào?** Identity, data class, recipient, operation, transport, size/rate/time và approval.
2. **Vì sao network egress allowlist không phải DLP hoàn chỉnh?** Nó không biết nội dung, tenant, object ownership hoặc resource authorization.
3. **Một IP của cloud object-storage provider có chứng minh bucket thuộc công ty không?** Không; đó có thể là shared multi-tenant service.
4. **Default deny egress trong Kubernetes cần gì để có hiệu lực?** CNI hỗ trợ enforcement, đúng selectors/ports, đường bypass được test.
5. **Kubernetes NetworkPolicy chuẩn có hỗ trợ FQDN rule không?** Không; phụ thuộc CNI extension hoặc gateway khác.
6. **HTTP CONNECT proxy có mặc nhiên thấy HTTPS PUT body không?** Không; nếu chỉ tunnel nó không giải mã payload.
7. **Tại sao TLS certificate hợp lệ chưa đủ?** Peer hostname đúng không bảo đảm tenant/account/bucket đúng hoặc dữ liệu được phép.
8. **Có thể chặn upload bằng cách chỉ DENY POST không?** Không; nhiều method/protocol khác có thể tải dữ liệu.
9. **Tại sao Content-Length không nên là giới hạn byte duy nhất?** Header thiếu/sai, chunked/HTTP2 streaming cần count actual bytes.
10. **10 MiB per-request có chặn 100 parts × 9 MiB không?** Không nếu thiếu aggregate quota.
11. **Logical bytes khác transferred bytes ra sao?** Compression, headers, TLS, retries và object semantics có thể làm khác.
12. **DLP scan PASS có đồng nghĩa business-approved export không?** Không; còn resource/recipient/tenant approval.
13. **Khi application nén/mã hóa file trước proxy, DLP cần điều chỉnh gì?** Scan tại điểm thấy plaintext hoặc deny/review unsupported formats.
14. **Vì sao chỉ allow hostname storage vẫn không ngăn external bucket?** Host chung cho nhiều accounts; phải enforce resource-level policy.
15. **Signed URL có thể bị rò qua đâu?** Logs/traces/tickets/redirects; nó có thể là bearer capability.
16. **Quy tắc quan trọng khi tạo signed URL là gì?** Server chọn đúng recipient/resource/action/TTL, không tin arbitrary client inputs.
17. **Upload broker giúp gì?** Kiểm tra source identity, data owner/classification, destination, quota trước khi transfer.
18. **Vì sao cần hash/immutable version sau pre-upload scan?** Chống TOCTOU giữa dữ liệu đã quét và payload được gửi.
19. **Quyền CopyObject/compose có thể bỏ qua quota egress không?** Có nếu chuyển dữ liệu server-side không đi qua workload.
20. **Vì sao flow log không đủ kết luận exfiltration?** Chỉ thấy metadata/bytes tại điểm log, không biết nội dung/recipient object/business context.
21. **Storage object audit giúp phân biệt gì?** Attempt so với actual commit/object version/requester theo khả năng service.
22. **Tại sao không cộng bytes ở source NIC và NAT?** Có thể đếm hai lần cùng traffic.
23. **Vì sao IPv6/QUIC phải nằm trong test matrix?** Chúng có đường/giao thức riêng có thể bypass policy chỉ thiết kế cho IPv4/TCP.
24. **Nếu scanner unavailable khi restricted upload, nên làm gì?** Chọn DENY hoặc trusted quarantine theo failure policy đã phê duyệt.
25. **Tại sao không tự block mọi IP của SaaS khi phát hiện upload lạ?** Shared IP khiến hợp lệ bị gián đoạn, không chặn recipient khác.
26. **Telemetry upload token có phải data loss dù endpoint được phép?** Có thể; phải redact/token governance, không chỉ network allowlist.
27. **Sự khác nhau giữa quota request và quota business job?** Quota request tính một transfer, job có nhiều parts/requests/objects.
28. **Những gì cần để chứng minh đường deny thực sự có hiệu lực?** CNI/proxy/IAM effective configuration, attempted upload test và resource audit.
29. **Vì sao “no DLP matches” không phải chắc an toàn?** Coverage gaps, unsupported format, false negatives, missing events.
30. **Khi khôi phục sau incident, ALLOW/DENY cần kiểm thử gì?** Legitimate recipient/data ALLOW, unknown owner/Restricted/direct bypass DENY.

### Bài tập kiến trúc cuối chương

Một công ty có Kubernetes trên cloud, service **report-writer** tạo báo cáo khách hàng, **CI runner** publish artifact, **backup worker** tải snapshot lên object storage và **telemetry agent** gửi metrics/logs tới SaaS. Hạ tầng gồm **service mesh sidecar, egress gateway, NAT, DNS resolver, CNI NetworkPolicy, IAM workload identity, cloud storage API và DLP broker**. Một số workloads chạy dual-stack IPv4/IPv6; đội ML cần upload large artifacts tới một partner.

Hãy xây bản thiết kế gồm:

1. **Sơ đồ data flow** từ từng workload tới destination, vẽ tất cả trust boundaries và các đường direct egress tiềm ẩn.
2. **Inventory nguồn/đích** theo workload ID, environment, partner account/tenant, bucket/object prefix, purpose và data owner.
3. **Data classification matrix**: Public, Internal, Confidential, Restricted; nêu loại nào được xuất và approval.
4. **NetworkPolicy/SG/egress gateway policy intent**: chỉ cho đúng brokers, DNS, object APIs; default-deny unknown và IPv6.
5. **Identity và cloud resource permissions**: Dedicated role/ServiceAccount, bucket/account/object actions, hạn chế server-side copy.
6. **TLS và L7 visibility**: Điểm terminate TLS, nơi DLP scan payload, xử lý CONNECT/passthrough/ECH/QUIC.
7. **Multipart/streaming quotas**: Per-request, per-object, per-workload/day, per-recipient và concurrency, cách reconcile retries.
8. **Pre-upload scan + integrity binding** cho báo cáo Confidential và workflow quarantine/approval khi scanner không hỗ trợ.
9. **Signed URL/broker lifecycle**: issuer, recipient, expiration, role scope, logging redaction và revoke.
10. **Telemetry an toàn**: App/proxy/cloud object audit, sampled flow logs, data minimization, detection rules.
11. **Bốn incident hypotheses**: Externally owned bucket, multipart quota bypass, telemetry token leakage, IPv6 bypass; chỉ rõ evidence cần để xác minh.
12. **Ma trận 20 ca ALLOW/DENY** và canary/rollback cho cả Prod/DR, logic bytes, multipart, quota engine/DLP outage.

**Tiêu chí đạt:** Kiến trúc phải chứng minh **upload hợp lệ vẫn hoàn tất đúng service/tenant**, còn **workload không đúng identity, dữ liệu trái classification, recipient sai, vượt quota hoặc bypass điểm thực thi** đều bị chặn theo policy và có bằng chứng audit phù hợp. Không tính “mở TCP/443 thành công” là upload business-approved.

## 29. Checklist triển khai và vận hành giới hạn upload

- [ ] Đã inventory **Pods/VMs/functions/CI runners/agents** nào có thể tạo upload?
- [ ] Mỗi workload có **owner, environment, business purpose, dedicated identity và entitlement**?
- [ ] Đã phân loại **data owner, classification, residency và recipient approvals**?
- [ ] Đã phân biệt **egress control, DLP, IAM/resource auth, quota và monitoring**?
- [ ] Có sơ đồ **workload → CNI/SG → proxy/gateway → NAT/firewall → recipient**, gồm alternate paths?
- [ ] Đã kiểm tra **IPv4/IPv6, hostNetwork, service mesh exclusions, managed endpoints và DR**?
- [ ] Default-deny network egress hoạt động **ở CNI/firewall thật**, không chỉ manifest?
- [ ] **DNS/DoH/direct IP/alternate resolver/redirect** không bypass egress policy bắt buộc?
- [ ] Service mesh/egress proxy nhận đúng traffic, không có **uncontrolled CONNECT/passthrough**?
- [ ] Proxy có quyền **TLS/L7 visibility** khi policy cần content inspection, không giả định đọc ciphertext?
- [ ] Các yêu cầu TLS inspection tuân thủ **privacy, PKI, authorization và data retention**?
- [ ] **TLS peer certificate/hostname verification** vẫn được thực thi, không bỏ qua để chữa lỗi?
- [ ] Đã xác minh **recipient cloud account/SaaS tenant/bucket/key/prefix**, không chỉ hostname?
- [ ] Cloud IAM/resource policy chỉ cấp **upload/write operations cần thiết**, không broad wildcard?
- [ ] **Server-side copy/replication/compose** được kiểm tra ở storage resource API?
- [ ] Signed/delegated upload capabilities có **recipient/action/TTL/owner/approval** phù hợp?
- [ ] Không log **full signed URL, Authorization, Cookie, private keys hoặc raw payload**?
- [ ] Content classification được tạo/kiểm tra bởi **nguồn đáng tin**, không tin header tự khai?
- [ ] DLP scanner có coverage cho **files, JSON, archives, image, compressed/encrypted formats** theo policy?
- [ ] Khi format không hỗ trợ hoặc DLP timeout, có **DENY/REVIEW/trusted quarantine** đúng sensitivity?
- [ ] **Pre-upload scan và actual upload** được ràng buộc qua object version/hash/immutable staging?
- [ ] Giới hạn **per-request, per-part, per-object, per-workload/tenant/day và per-recipient** được định nghĩa rõ?
- [ ] Quota chỉ rõ **logical, transfer, scanned, forwarded và committed bytes** khác nhau thế nào?
- [ ] Byte counting thực thi cả khi **Content-Length thiếu, HTTP/2 stream hoặc chunked upload**?
- [ ] Accounting được đồng bộ **giữa replicas, regions, retry/resume/multipart sessions**?
- [ ] Có hạn mức **concurrent uploads, rate, timeout và storage buffering/decompression**?
- [ ] Có **idempotency và cleanup** khi request thất bại/abort rồi retry?
- [ ] WebSocket/gRPC/QUIC/raw TCP/SFTP có **giải pháp protocol-aware hoặc deny** theo policy?
- [ ] Logs có **source identity, recipient owner, classification, policy revision, request/object ID và status**?
- [ ] Có đối soát **flow logs, proxy bytes, DLP decision, cloud IAM và object commits**, không double count?
- [ ] Logging pipeline có monitoring **skipped/unsupported/late records, schema drift và collector failures**?
- [ ] Detection rules có **workload baseline, false-positive handling và owner**?
- [ ] Phân biệt **potential exfiltration** với **confirmed exposure** bằng evidence thích hợp?
- [ ] Có quy trình **narrow containment, revoke delegated credentials và deny external recipient** khi incident?
- [ ] Có bảo vệ **forensic evidence, quarantine bucket, access audit và retention**?
- [ ] Có test **ALLOW approved upload và DENY wrong tenant, data, direct path, oversized, DLP unavailable**?
- [ ] Có **canary, business SLI, change approval, safe rollback** không khôi phục đường rò rỉ?
- [ ] Có review định kỳ **IAM permissions, destinations, cloud account ownership, policy exceptions, token TTL**?

**Kết luận:** **Giới hạn upload từ workload** đòi hỏi nhiều hơn một firewall rule hoặc số MiB tối đa. Một chính sách hiệu quả phải xác định **workload nào được phép, dữ liệu nào có thể rời ranh giới, account/tenant/bucket nào được nhận, giao thức nào có thể truyền, tổng dung lượng được tính ra sao và điểm nào thực thi quyết định**. Kết hợp **network egress default deny, workload identity, resource-scoped IAM, L7 upload broker, DLP đúng nơi có plaintext, quota xuyên multipart/streaming, log đối soát và quy trình revoke/incident** giúp vừa duy trì các workflow hợp lệ vừa giảm cơ hội thất thoát. Chỉ khi kiểm thử được cả **ALLOW đúng business need lẫn DENY đường trái quyền**, gồm cả IPv6, cloud API, signed URLs và đường bypass, tổ chức mới có bằng chứng thuyết phục rằng upload từ workload đang được kiểm soát.
