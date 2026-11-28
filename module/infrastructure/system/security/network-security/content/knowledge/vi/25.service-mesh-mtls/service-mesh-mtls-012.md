# Rủi ro khi bypass sidecar proxy trong Service Mesh và mTLS

**Sidecar proxy** là thành phần trung gian được triển khai bên cạnh ứng dụng, thường trong cùng Pod Kubernetes, để xử lý một phần hoặc toàn bộ lưu lượng mạng của workload. Trong các service mesh dùng mô hình sidecar, proxy có thể thực hiện **mTLS, xác thực danh tính workload, kiểm soát truy cập, routing, retry, telemetry và quản lý kết nối** theo cấu hình được đẩy từ control plane. Nhưng một ranh giới chỉ bảo vệ được những luồng **thực sự đi qua** nó.

**Bypass sidecar proxy** là tình huống một luồng đáng lẽ phải chịu kiểm soát tại proxy lại đi theo một đường khác, hoặc đến ứng dụng mà không được lớp proxy mong đợi xác minh. Điều này có thể xuất phát từ cấu hình injection, traffic interception, network path, vòng đời Pod, host networking, exception port/interface, topology gateway, hoặc một thay đổi hạ tầng không đồng bộ. **Không phải mọi bypass đều là khai thác thành công**: proxy có thể không nhìn thấy một luồng nhưng NetworkPolicy hoặc ứng dụng vẫn chặn; và khi một đường bắt buộc đi qua proxy bị lỗi, kết quả an toàn có thể là **fail closed**, tức request bị từ chối.

Bài thuộc chương **Service mesh và mTLS** trong module **SECURITY_NETWORK_SECURITY**. Nó kết nối kiến thức về **phân đoạn mạng, firewall/NetworkPolicy, VPN/cloud networking, DNS, IDS/IPS, TLS/mTLS, quan sát east–west traffic và mô hình hóa mối đe dọa** để trả lời câu hỏi: *khi mesh sidecar không ở trên đường truyền, kiểm soát nào biến mất, kiểm soát nào còn hiệu lực và bằng chứng nào xác nhận an toàn?*

> **Ràng buộc thực hành:** tất cả hostnames, IPs, labels, policies và log records là ví dụ đào tạo. Chỉ kiểm tra trong sandbox Kubernetes do bạn quản lý hoặc được cấp quyền. Không thử bỏ qua chính sách bảo mật production, sửa injection webhook hay tắt proxy của workload khác. Các manifest minh họa về mục tiêu kiểm soát phải được điều chỉnh theo mesh/CNI/version thật và được review trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Vẽ đường đi **application → sidecar → network → sidecar → application**, chỉ rõ chỗ mã hóa, xác thực và áp chính sách.
2. Giải thích các khái niệm **sidecar injection, traffic capture/interception, control plane, data plane, workload identity, mTLS và authorization policy**.
3. Phân biệt **bypass thực sự**, **mesh không bắt luồng do thiết kế**, **traffic bị chặn fail-closed** và **telemetry bị thiếu nhưng data plane vẫn có kiểm soát**.
4. Nhận diện rủi ro từ **thiếu sidecar, Pod cũ chưa được reinject, port/interface exclusion, loopback cùng Pod, hostNetwork, secondary CNI, probe/health ports và đường direct-to-service**.
5. Phân tích trường hợp **mTLS STRICT/PERMISSIVE**, danh tính certificate, giao thức plaintext và authorization khi luồng không qua sidecar.
6. Đánh giá tác động lên **L7 policy, egress control, rate limiting, retry/timeouts, tracing, audit và khả năng phát hiện sự cố**.
7. Thiết kế phòng vệ nhiều lớp với **Kubernetes NetworkPolicy, admission/RBAC, Pod Security, identity-aware gateway, application authentication và cloud firewall**.
8. Thực hiện các **kiểm thử dương/âm** an toàn; biết khi nào cần kiểm tra ở nguồn, đích, proxy, CNI và ứng dụng.
9. Dùng threat modeling, telemetry và runbook để **giảm blast radius**, xử lý cấu hình drift và điều tra nghi bypass.
10. Giải thích vì sao **ambient/sidecarless mesh** là kiến trúc data plane khác, không tự động đồng nghĩa có lỗ hổng bypass.

## 2. Sidecar proxy nằm ở đâu trong Kubernetes?

### 2.1. Cùng Pod nhưng không phải ứng dụng

Trong Pod có thể có:

~~~text
Pod orders-api
  Pod IP: 10.244.2.21
  Network namespace:
    lo, eth0, routes, TCP/UDP ports

  Container: orders application
    Listen: TCP/8080

  Container: mesh-proxy (ví dụ Envoy)
    Inbound/outbound listeners
    mTLS credentials and policy received from mesh control plane

  Traffic capture:
    iptables/nftables/eBPF/CNI redirect theo implementation
~~~

Hai containers trong cùng Pod **chia sẻ network namespace**, nên sidecar thường có khả năng đứng giữa network và ứng dụng bằng các rules hoặc dataplane hooks thích hợp. Tuy nhiên, **việc hai container cùng Pod không tự ép mọi socket qua sidecar**. Traffic capture phải được thiết lập và có **phạm vi cụ thể** theo protocol, destination, interface, port và chế độ chạy.

Sidecar không mặc định đọc được tất cả secrets, filesystems hoặc Linux namespaces của ứng dụng. Nguy cơ ở đây chủ yếu đến từ **đường mạng chung**, quyền/volumes được chia sẻ nếu có, và các ports giao tiếp nội bộ—không nên đồng nhất “chung netns” với “chung mọi quyền”.

### 2.2. Control plane và data plane

| Thành phần | Nhiệm vụ thường gặp | Điều kiện bảo mật |
| --- | --- | --- |
| **Mesh control plane** | Tạo/phân phối cấu hình routes, policies và workload certificates theo sản phẩm | IAM/RBAC, cấu hình an toàn, CA/identity trust và audit |
| **Sidecar data plane** | Xử lý các kết nối được redirect qua proxy | Lắng nghe đúng port, route/policy mới nhất, availability |
| **Traffic capture layer** | Chuyển connections từ app/netns qua proxy | Đúng scope, không có exclusion/bypass ngoài dự kiến |
| **Kubernetes CNI/dataplane** | Pod IP/routing/NetworkPolicy; có thể hỗ trợ mesh redirect | Không nhầm khả năng routing với khả năng mTLS/L7 |
| **Application** | Xử lý nghiệp vụ, xác thực và phân quyền tài nguyên | Không phụ thuộc duy nhất vào việc mesh chặn mọi request |
| **Ingress/Egress gateways** | Điểm proxy tại biên theo topology | Route thực phải đi qua gateway và policy còn hiệu lực |
| **CA/workload identity provider** | Phát/luân chuyển certificates/identity theo mesh | Chống cấp sai identity và credentials bị lạm dụng |

**Control plane không tự đứng trên mọi packet data path**. Khi policy được cập nhật, dữ liệu thực tế vẫn đi qua proxy hoặc thành phần data plane khác đang nhận cấu hình. Kiểm tra policy được API chấp nhận **chưa đủ chứng minh** sidecar của từng Pod đang chạy config đó.

### 2.3. Đường đi chuẩn khi cả hai Pod có sidecar

~~~mermaid
sequenceDiagram
  participant A as App A
  participant PA as Sidecar A
  participant NET as CNI/Network
  participant PB as Sidecar B
  participant B as App B
  A->>PA: Local application connection (captured)
  PA->>PA: Resolve route, outbound policy
  PA->>PB: mTLS across network via NET
  PB->>PB: Verify peer identity, inbound authorization
  PB->>B: Forward to local service listener
  B-->>PB: Application response
  PB-->>PA: Protected return traffic
  PA-->>A: Response
~~~

Đây là **mô hình minh họa cho một sidecar mesh có capture inbound/outbound và mTLS proxy-to-proxy**. Đường thực tế có thể qua gateway, các hops bổ sung, hoặc TLS pass-through; không có gì bảo đảm mọi mesh triển khai đúng thứ tự trên. Nếu **ứng dụng dùng TLS riêng**, giữa app và sidecar còn có thể có lớp TLS khác hoặc proxy chỉ xử lý TCP; không suy rằng sidecar luôn đọc HTTP plaintext.

### 2.4. Phân biệt ba loại “mã hóa giữa dịch vụ”

| Trường hợp | TLS peer identity do ai xác minh? | Ai có thể thấy plaintext? |
| --- | --- | --- |
| **Mesh mTLS giữa sidecars** | Sidecar A và B xác minh danh tính được mesh cấp | Ứng dụng và các proxies tại điểm kết thúc/khởi tạo TLS |
| **Application TLS end-to-end** | Ứng dụng client/server tự xác minh chứng chỉ | Chủ yếu hai ứng dụng; proxy TCP passthrough thường không đọc HTTP |
| **Application TLS kết hợp mesh mTLS** | Hai lớp TLS với hai trust/policy domains có thể khác nhau | Tùy thứ tự TLS và proxy mode; không mặc định mesh thấy L7 |

Điểm quan trọng: **Mesh mTLS không đồng nghĩa ứng dụng có authorization đúng**. Certificate có thể xác minh service identity nhưng không tự quyết định principal đó được quyền đọc khách hàng nào hoặc gọi gRPC method nào.

### 2.5. Sidecar không tự xuất hiện trong mọi Pod

Sidecar injection có thể được thực hiện bởi **mutating admission webhook**, cơ chế quản lý Pod template hoặc deployment tooling tùy mesh. Injection có thể phụ thuộc:

- Labels/annotations của namespace hoặc Pod.
- Mesh revision/canary version và target workload.
- Injection webhook availability/matching/failure behavior.
- Kiểu Pod và platform (Linux/Windows, hostNetwork, privileged/system Pods).
- Pod được tạo **trước** khi bật injection.
- Cơ chế native sidecar/sidecar injection khác nhau theo cluster/version.

Do đó **namespace có nhãn injection** không chứng minh tất cả Pods đang chạy bên trong đều có proxy. Kiểm tra **Pod spec thực tế, container readiness, mesh membership và configuration state** mới cho kết luận đáng tin cậy.

## 3. Bypass là gì, và lúc nào chỉ là thiếu đường?

### 3.1. Định nghĩa điều kiện

Một **sidecar bypass có ý nghĩa bảo mật** khi đồng thời có:

1. Có một **policy/đảm bảo dự kiến** phụ thuộc traffic đi qua proxy, như inbound mTLS/authorization hoặc outbound egress routing.
2. Một luồng **đến được tài sản mục tiêu mà không chịu kiểm soát tương ứng tại proxy**.
3. Những lớp kiểm soát còn lại **không chặn hoặc không cung cấp bảo đảm tương đương**.

Nếu client thử một đường direct nhưng backend NetworkPolicy deny từ đầu, đó là **nỗ lực hoặc khả năng thử bypass bị chặn**, không phải xác nhận bypass thành công. Nếu proxy không tiếp nhận packet vì cấu hình fail-closed rồi connection timeout, có **availability problem**, nhưng chưa chứng minh confidentiality/authorization bị bỏ qua.

### 3.2. Các trạng thái khác nhau

| Trạng thái | Ví dụ | Kết luận đúng |
| --- | --- | --- |
| **Proxy-in-path** | Luồng qua sidecar nguồn và đích; mTLS/AuthZ kiểm tra | Mesh policy có khả năng được thực thi; vẫn cần xác minh log/behavior |
| **Bypass nguồn, có proxy đích** | App nguồn đi trực tiếp nhưng sidecar đích vẫn bắt inbound và yêu cầu mTLS | Có thể bị chặn nếu không có đúng mesh identity; kiểm tra thực tế |
| **Qua proxy nguồn, bypass đích** | Outbound mTLS thiết lập nhưng đích không có listener/sidecar bắt tương ứng | Handshake fail hoặc thay đổi transport/policy tùy mode |
| **Bypass cả hai** | Direct TCP tới app listener ngoài phạm vi capture | Nguy cơ mất mesh mTLS, authorization và telemetry |
| **Proxy thiếu nhưng traffic bị chặn** | NetworkPolicy chặn direct flow | Không có request thành công; defense-in-depth có tác dụng |
| **Chỉ thiếu telemetry** | Luồng vẫn được CNI/mTLS kiểm soát nhưng exporter không ghi | Chưa chứng minh bypass; đánh dấu coverage gap |
| **Bypass có chủ đích** | Probe/local IPC được miễn một số mesh controls theo thiết kế | Phải ghi scope/risk và controls thay thế |
| **Sidecarless mesh** | Traffic qua node-level proxy/tunnel được quản lý | Không gọi là bypass chỉ vì không có container sidecar |

### 3.3. Mục tiêu kiểm thử là các bất biến

Thay câu hỏi “sidecar có chạy không?” bằng những **bất biến bảo mật**:

- **I1:** Mọi kết nối từ trust tier không được duyệt tới service nhạy cảm bị chặn.
- **I2:** Mọi lời gọi được phép tới service nhạy cảm có **peer identity đã được xác minh**.
- **I3:** Yêu cầu L7 nhạy cảm được kiểm tra đúng principal/action, không dựa riêng vào source IP.
- **I4:** Không có **alternate route** đi vào backend bỏ qua điểm kiểm soát bắt buộc.
- **I5:** Những luồng hợp lệ và bị chặn có telemetry đầy đủ hoặc được đánh dấu visibility gap.
- **I6:** Khi proxy/control plane gặp lỗi, hệ thống có **fallback/fail-closed behavior đã định nghĩa**, không ngầm chuyển từ mTLS sang plaintext.

Nếu chỉ chứng minh sidecar container Running mà chưa thử I1–I6, kết luận “mesh đã bảo vệ mọi traffic” vẫn còn thiếu bằng chứng.

### 3.4. Các điểm bypass có thể nằm ở đầu nào?

~~~mermaid
flowchart LR
    S["Source application"] --> O{"Outbound capture?"}
    O -- "Có" --> P1["Source sidecar"]
    O -- "Không" --> DIRECT["Alternative network path"]
    P1 --> NET["Pod / node / cloud network"]
    DIRECT --> NET
    NET --> I{"Inbound capture?"}
    I -- "Có" --> P2["Destination sidecar\nmTLS/AuthZ"]
    I -- "Không" --> APP["Destination application"]
    P2 --> APP
    C["NetworkPolicy / firewall"] -. "Có thể chặn ở data path" .-> NET
~~~

**Source bypass không mặc định kéo theo destination bypass.** Một destination sidecar cấu hình inbound STRICT và network controls đúng có thể từ chối client direct không có mTLS identity. Muốn biết request thực sự bypass được phải **quan sát ở cả nguồn, đích và ứng dụng**.

## 4. Bypass do injection không đồng đều

### 4.1. Nhãn namespace không làm thay đổi Pod đã chạy

Ví dụ một nhóm bật injection cho namespace chứa dịch vụ đang hoạt động. Mutating admission thông thường áp khi **Pod mới được tạo**, không tự sửa spec của những Pod đã tồn tại.

~~~text
Trước khi bật injection:
  Pod orders-v1  → containers: [app]

Sau khi bật injection:
  Pod orders-v1  → vẫn là [app], nếu chưa tái tạo
  Pod orders-v2  → containers: [app, mesh-proxy] theo cấu hình

Hậu quả:
  Cùng một Kubernetes Service có thể trỏ tới
  cả Pod được mesh quản lý và Pod chưa có proxy.
~~~

Nếu authorization/mTLS phụ thuộc proxy tại **destination Pod**, rollout hỗn hợp có thể khiến chính sách chỉ áp trên một phần replicas. Nói **“Service đã bật STRICT mTLS”** mà không kiểm tra từng endpoint là không đủ.

### 4.2. Injection opt-in/opt-out và nhầm lẫn revision

Một số mesh cho phép injection theo **namespace label, Pod annotation hoặc revision selector**. Rủi ro:

- Namespace được gắn label không đúng revision đang vận hành.
- Workload có annotation opt-out được giữ lại từ một deployment cũ.
- Webhook selector không match Pod mới.
- Một template Helm/Kustomize/GitOps khác ghi đè Pod annotations.
- Tạo Pods trực tiếp với service account/labels không qua pipeline chuẩn.
- Job/CronJob ngắn hạn chạy trước khi lớp kiểm soát quan sát được.
- Cluster có nhiều mesh control planes; workload gắn nhầm trust domain/revision.

**Không coi tên annotation hay thứ tự ưu tiên giữa nhãn Pod/namespace là phổ quát**: đó là chi tiết sản phẩm và version. Kiểm tra **admission result, Pod spec cuối cùng và actual proxy readiness**.

### 4.3. Admission webhook lỗi: fail-open hay fail-closed?

Trong Kubernetes, mutating admission webhooks có một số thiết lập như **failurePolicy** và timeout/matching rules. Nếu đường injection bắt buộc không sẵn sàng, hậu quả có thể khác nhau theo cấu hình:

- **Fail-closed admission:** từ chối tạo Pod không đạt điều kiện injection; bảo vệ tính nhất quán nhưng có thể gây deployment outage.
- **Fail-open admission:** Pod có thể được tạo mà không có mutation như kỳ vọng; giảm rủi ro chặn deploy nhưng phải chặn việc workload chạy không có kiểm soát bằng lớp khác.
- **Không match webhook:** Pod được tạo theo spec gốc, có thể không bị coi là lỗi webhook.
- **Mutation thành công nhưng proxy không Ready:** Pod có sidecar về mặt spec nhưng đường dữ liệu chưa sẵn sàng.

Không suy **failurePolicy=Fail** là toàn bộ service mesh an toàn tuyệt đối: vẫn phải kiểm tra đường bypass host/interface, app binding và network segmentation. Trong môi trường có yêu cầu mTLS bắt buộc, việc kiểm soát admission nên kết hợp **policy validation + runtime checks + NetworkPolicy/authorization**.

### 4.4. Workload không tham gia mesh có thể vẫn ở cùng cluster

Một cluster có thể có:

- Namespaces hệ thống không inject sidecar.
- Batch/maintenance Jobs tạo Pod không injection.
- Third-party operators hoặc controllers đặt Pod spec đặc biệt.
- Multi-tenant namespaces với quyền tạo labels/annotations khác nhau.
- Các workloads đã migrate sang **ambient** hoặc mesh mode khác.

Chính sách cần nêu **workload nào nằm trong phạm vi mesh** và những mạng/services nào một Pod ngoài mesh được phép kết nối. Nếu một client ngoài mesh có đường tới backend ngoài mesh, **mTLS mesh không tự bảo vệ flow đó**, dù cả hai Pod chạy trong cluster có control plane mesh.

### 4.5. “Pod có container tên proxy” không đủ

Một proxy container có thể có mặt nhưng:

1. Chưa có **workload certificate** hợp lệ.
2. Chưa kết nối được tới control plane để nhận cấu hình.
3. Sidecar readiness chưa đạt.
4. Traffic redirect rules chưa được cài hoặc đã bị thay.
5. Chạy revision khác với expectation.
6. Không được route đúng traffic vì port/interface exclusions.
7. App có đường **direct network socket** không được capture.

Đánh giá phải gắn cả **control-plane intent, Pod actual state, dataplane rules và traffic outcome**. Một phương án tốt là duy trì inventory các Pod có/không có sidecar theo namespace, owner, revision và expectation, thay vì chỉ đếm tổng sidecar containers.

## 5. Bypass do phạm vi traffic interception

### 5.1. Tại sao sidecar cần capture?

Trong mô hình transparent sidecar, ứng dụng có thể mở socket như bình thường. Các rules trong Pod/host/CNI có thể chuyển kết nối tới proxy mà không cần app đổi code. Với một triển khai dựa trên Linux packet filtering, thường có:

- **Outbound capture** từ app đến service hoặc IP khác, chuyển tới outbound listener của sidecar.
- **Inbound capture** từ network đến Pod app port, chuyển tới inbound listener.
- **Exclusions** cho traffic của chính proxy, control plane, loopback hay các destination/ports được phép bỏ capture.
- Xử lý **kết nối response** bằng conntrack/socket metadata theo dataplane implementation.

Với eBPF/CNI hoặc ambient mode, cơ chế khác đi. **Không kết luận bằng cách chỉ xem iptables** nếu CNI đang dùng eBPF hoặc một redirect hook khác.

### 5.2. Port exclusion và listener ngoại lệ

Một số service mesh có cấu hình **include/exclude inbound/outbound ports**, application ports hoặc UID/identity exclusions để tránh vòng lặp và xử lý traffic đặc biệt. Nếu một service nhạy cảm được bind trên port mà rule **không bắt inbound**, traffic tới listener đó có thể không được proxy xử lý, tùy đường mạng.

Tình huống minh họa:

~~~text
Expected:
  client → destination-sidecar → app TCP/8443
  sidecar verifies mTLS identity and authorization

Configuration drift:
  app listener changed to another port
  traffic capture policy excludes that port

Possible outcome:
  client direct flow reaches app listener
  without expected destination-sidecar authorization
  (only if routes, NetworkPolicy, app policy allow)
~~~

Không đủ nhìn thấy port bị excluded rồi kết luận có lỗ hổng. Phải đánh giá **đường tới listener, firewall/NetworkPolicy, TLS của chính ứng dụng và API authorization**. Cũng không được tự ý xóa tất cả exceptions: một số port dành cho liveness/readiness, điều khiển proxy hoặc outbound exclusions hợp lệ.

### 5.3. Exclusion theo IP range, interface hoặc traffic class

Một mesh có thể cho phép **bỏ capture** với destinations nội bộ, external CIDRs, proxy UIDs, hoặc interfaces. Rủi ro khi policy quá rộng:

- Outbound tới một dải private IP không qua mesh egress gateway.
- Traffic qua secondary interface không chịu mTLS/telemetry ở proxy.
- Pod gọi trực tiếp một endpoint IP thay vì Service FQDN, đi vào phạm vi capture khác.
- Một destination chuyển IP sau migration và rơi ngoài include ranges.
- Traffic IPv6 được điều hướng khác IPv4 trong cấu hình chưa đồng bộ.

Nguyên tắc phòng vệ là **inventory tất cả bypass exceptions cùng owner, mục đích, CIDR/port/protocol, thời hạn và ranh giới tin cậy**, sau đó test hiệu lực theo từng đường. Không mở dải 0.0.0.0/0 hoặc ::/0 cho mục tiêu bypass trừ khi đó là thiết kế đã được security review, và cần controls thay thế.

### 5.4. Localhost và giao tiếp cùng Pod

Các containers trong cùng Kubernetes Pod **chia sẻ network namespace**, nên một container có thể gọi cổng khác qua **127.0.0.1** hoặc **::1**. Tùy mesh/capture mode, một phần **loopback traffic có thể không đi qua outbound/inbound proxy**. Đây thường là quyết định kỹ thuật để sidecar giao tiếp với application, nhưng gây ra hậu quả:

- Admin/metrics/debug ports chỉ bind localhost vẫn có thể được **container khác cùng Pod** truy cập.
- Một sidecar độc lập không tự bảo vệ **một service khác cùng Pod** bằng NetworkPolicy L3/L4.
- Local IPC/Unix-domain sockets có thể có security model khác network-based mTLS.
- Một trust boundary giữa app và helper/sidecar không nên dựa duy nhất vào port “chỉ localhost”.

**Tuyệt đối không coi localhost là đường có mesh mTLS chắc chắn** nếu không xác minh bằng proxy dataplane/traffic. Nếu endpoint localhost nhạy cảm, dùng **application auth, Unix socket permissions, Pod isolation và RBAC/admission** phù hợp.

### 5.5. hostNetwork và privileged workloads

Pod sử dụng **hostNetwork: true** thường chia sẻ network namespace của node, không có địa chỉ Pod tách biệt theo mô hình bình thường. Traffic có thể không chịu same Pod sidecar redirection, hoặc mesh không hỗ trợ injection cho loại workload này, tùy implementation.

Khuyến nghị:

- Chỉ dùng hostNetwork cho hệ thống cần thiết và được phê duyệt.
- Giới hạn **Pod Security Admission**, RBAC, privileged/capabilities và node firewall.
- Không cho một service thường tự đổi sang hostNetwork để “sửa DNS/sidecar timeout”.
- Đánh giá node ports, metadata service, kubelet endpoints và cloud IAM riêng.
- Thiết kế cách enforce identity/authorization nếu host-level agent đi vào services nhạy cảm.

**Không thể dùng một NetworkPolicy chuẩn cho namespace ứng dụng để khẳng định mọi hostNetwork traffic đã bị cô lập**, vì CNI host-policy support khác nhau.

### 5.6. Nhiều network interfaces / SR-IOV / secondary CNI

Pod có thể có **eth0** do CNI chính và **net1** do secondary network. Nếu sidecar chỉ capture traffic trên default route/interface mà ứng dụng chủ động bind route qua net1, flow có thể không chịu mesh mTLS/policy như dự tính.

~~~text
Pod:
  eth0 (default Pod network): app ↔ mesh sidecar ↔ services
  net1 (secondary network):  app ↔ special network appliance

Question:
  Is net1 traffic captured, denied by CNI/host firewall,
  or intentionally outside mesh with its own TLS/auth?
~~~

Kiểm soát gồm **per-interface ACL/firewall, CNI attachment admission, route-policy review, app TLS/mTLS và logging**. Không mặc định **secondary CNI** được bảo vệ bởi chính sách trên eth0.

### 5.7. UDP/QUIC và các giao thức không được proxy hỗ trợ

Một số sidecar proxies ưu tiên TCP/HTTP/gRPC; khả năng intercept hoặc bảo vệ **UDP/QUIC, ICMP, SCTP, raw sockets và custom transports** khác theo mesh, proxy/dataplane và version. Do đó:

- Không tuyên bố “mesh mTLS mã hóa tất cả lưu lượng của Pod” nếu còn UDP flows không đi qua sidecar.
- Với **HTTP/3/QUIC**, xem gateway/sidecar có thực sự làm QUIC/TLS endpoint hoặc passthrough không.
- Với DNS UDP/53, nhiều mesh có cơ chế DNS capture/proxy riêng, nhưng **không phải mọi triển khai mặc định bắt DNS**.
- Với custom UDP, cần CNI/host/cloud firewall, protocol-level authentication hoặc tunnel encryption độc lập.

**Sự vắng mặt của HTTP telemetry cho một giao thức không phải HTTP** chưa phải bypass; cần xác định mesh policy nào được kỳ vọng áp trên transport đó.

### 5.8. IP tables/eBPF redirection không thay authorization

Ngay cả khi một gói đi qua sidecar, proxy có thể chỉ thực hiện **TCP forwarding** mà chưa xác minh HTTP request-level authorization. Một proxy được cấu hình **PERMISSIVE mTLS**, hoặc không có authorization rule cho workload đích, có thể nhận traffic theo policy hiện tại.

Do đó: **in-path ≠ authorized and encrypted**. Cần xác minh **effective transport security, peer identity, destination policy, application response và audit decision** từng lớp.

## 6. Vòng đời Pod và race condition của sidecar

### 6.1. Sidecar chưa Ready khi ứng dụng bắt đầu nhận/gửi traffic

Một Pod có thể khởi chạy application container trước khi proxy **sẵn sàng nhận cấu hình, certificate hoặc lắng nghe các cổng cần thiết**, tùy kỹ thuật injection, startup ordering và readiness gates. Nếu capture rules chưa ổn định, hành vi có thể là:

- **Fail closed:** lưu lượng không thể đi; requests timeout hoặc bị từ chối.
- **Traffic đi ra mà chưa được capture:** chỉ khi dataplane/fallback thực sự cho phép đường này.
- **Proxy nhận traffic nhưng chưa có cấu hình/mTLS certificate:** handshake hoặc route thất bại.
- **Pod Ready sớm hơn kỳ vọng:** Service bắt đầu chọn endpoint nhưng path thực chưa sẵn sàng.

Không dùng một biểu hiện TCP timeout để kết luận proxy đã bị bypass. Ngược lại, HTTP 200 từ ứng dụng khi proxy chưa Ready là **tín hiệu cần kiểm tra** liệu luồng đã qua đúng policy hay có một path khác.

### 6.2. Biện pháp startup an toàn

1. Cấu hình **startup/readiness gates hoặc cơ chế giữ app chờ proxy** được mesh/platform hỗ trợ.
2. Kiểm soát **injection** ở admission, không chỉ bằng convention của developer.
3. Xác minh CNI/iptables/eBPF redirect **được cài trước khi endpoint nhận workload traffic**.
4. Đặt **NetworkPolicy default-deny và allow hẹp** cho traffic chưa có identity/authorization.
5. Kiểm thử khi **restarting proxy, renewing certificate và rolling out sidecar revisions**.
6. Đảm bảo application readiness kiểm tra dependency thiết yếu thay vì chỉ process alive.

Khi mesh cung cấp **native sidecar container startup semantics** hoặc một cơ chế agent riêng, dùng chức năng được hỗ trợ theo version. Không gán một annotation hoặc thứ tự startup cụ thể cho mọi mesh.

### 6.3. Shutdown và kết nối tồn tại lâu

Khi Kubernetes chấm dứt Pod, một proxy có thể dừng trước khi **long-lived gRPC/WebSocket requests** hoàn tất nếu drain/termination ordering không đúng. Hệ quả:

- HTTP 503/reset hoặc timeout dù auth policy không thay.
- Client retry có thể tạo hiệu ứng nghiệp vụ nếu operation không idempotent.
- Telemetry cuối phiên không được flush đầy đủ.
- App hoặc proxy có thể rơi vào trạng thái dừng **không đồng bộ**.

Không tự coi điều này là bypass. Mục tiêu là **drain policy, graceful shutdown, preStop/termination grace, retry idempotency và tracing** đúng. Khi cố gỡ proxy để “cứu kết nối”, nguy cơ thay đổi security guarantees phải được review.

### 6.4. Sidecar crash và proxy restart

Một sidecar bị crash không tự động có nghĩa Pod ứng dụng sẽ **fail open**. Tùy CNI capture rules, app có thể không kết nối được vì traffic vẫn redirected tới listener chết. Nhưng nếu có exception, fallback path hoặc ứng dụng đã có socket không qua proxy, hệ quả khác.

Kế hoạch kiểm thử hợp lệ trong sandbox nên quan sát:

| Tình huống | Câu hỏi | Evidence |
| --- | --- | --- |
| Proxy not ready | App có bị đưa vào Service endpoint sớm không? | Pod readiness/EndpointSlice |
| Proxy restart | Outbound/inbound traffic có fail closed? | CNI drop/proxy logs, app result |
| Control plane unavailable | Data plane dùng cached config/cert được bao lâu? | xDS/cert expiry, proxy status |
| Cert rotation | Có sai trust root/identity gây handshake failures? | TLS verification logs |
| Pod terminating | Long-lived streams drain đúng không? | Proxy/app connection metrics |
| Network CNI race | Capture được khởi tạo trước traffic không? | CNI setup logs + traffic tests |

**Không làm gián đoạn proxy của production chỉ để test**; dùng mô phỏng, canary hoặc môi trường kiểm thử có phê duyệt.

## 7. Rủi ro về mTLS khi bypass sidecar

### 7.1. mTLS của mesh xác thực điều gì?

Trong mô hình mesh dùng mTLS giữa các data-plane endpoints, proxy thường trình **workload identity certificate** do mesh trust domain/CA phát, ví dụ một **SPIFFE-like identity**:

~~~text
spiffe://corp.example/ns/app/sa/orders-api
~~~

Đây là ví dụ cú pháp identity, không phải secret. Tên **service account/namespace/trust domain** cần được xác minh trong cơ chế cấp chứng chỉ thực tế; một string giống SPIFFE URI không tự chứng minh peer đang giữ certificate hợp lệ.

mTLS có hai mục đích:

- **Mã hóa lưu lượng trên đoạn do hai TLS endpoints bảo vệ**.
- **Xác thực hai endpoints**, theo CA/trust bundle, SAN/identity và policy.

Authorization có thể sử dụng peer identity đã xác minh, nhưng **certificate hợp lệ không đồng nghĩa được phép thực hiện mọi hành động**.

### 7.2. STRICT, PERMISSIVE và DISABLE: cách hiểu đúng

Trong một số mesh như các mô hình cấu hình của Istio, destination có thể chọn hành vi mTLS khái quát:

| Chế độ | Ý nghĩa thường gặp ở điểm enforcement | Rủi ro/chú ý |
| --- | --- | --- |
| **STRICT** | Proxy tiếp nhận inbound đã được capture và yêu cầu mesh mTLS | Bảo vệ intercepted path; **không bảo đảm direct path ngoài capture bị chặn** |
| **PERMISSIVE** | Proxy có thể nhận cả mTLS mesh và plaintext/non-mesh theo hỗ trợ | Thuận migration, nhưng plaintext path có thể tồn tại |
| **DISABLE** | Không yêu cầu mesh mTLS tại endpoint này theo cấu hình | Cần application TLS/controls khác nếu dữ liệu nhạy cảm |
| **UNSET/inherit** | Kế thừa policy effective từ namespace/mesh | Phải kiểm tra cấu hình thực tế, không đoán default |

Tên/mức áp dụng là **ví dụ mang tính sản phẩm**, không phải một Kubernetes NetworkPolicy API. Các phiên bản mesh và cách xét precedence có thể khác; phải đối chiếu **effective configuration và traffic results**.

**Một policy STRICT chỉ giúp nếu inbound flow thực sự tới endpoint/proxy áp STRICT.** Nếu một Pod thiếu proxy hoặc app listener có đường ngoài phạm vi capture, policy có thể không tồn tại ở đúng điểm thực thi.

### 7.3. Bypass có thể gây ba loại kết quả

Giả sử client không có mesh identity nhưng cố truy cập Orders API:

~~~text
Scenario A:
  Client → destination sidecar STRICT → app
  Expected: deny / failed mTLS; application not reached.

Scenario B:
  Client → app directly via unintended path
  App itself requires valid TLS + authorization.
  Expected: app denies unauthenticated request.

Scenario C:
  Client → app directly via unintended path
  App accepts plaintext or weak identity.
  Possible: missing mesh controls; high risk.
~~~

**Chỉ Scenario C mới minh họa tình huống bypass dẫn tới truy cập trái ý định**, nếu kết nối và quyền ứng dụng thật sự có hiệu lực. A/B là những lớp phòng vệ có thể chặn request. Không gom tất cả trường hợp “không có sidecar trace” thành C.

### 7.4. Nguy cơ downgrade từ encrypted sang plaintext

Nếu mesh mTLS là lớp mã hóa duy nhất giữa hai services, bypass có thể khiến TCP/HTTP đi **plaintext** nếu ứng dụng và đường mạng chấp nhận. Các bối cảnh nhạy cảm:

- Cross-node/zone traffic không có encryption được xác minh.
- Cloud peering hoặc transit traffic đi qua nhiều trust domains.
- Partner/on-prem connections.
- Node/Pod capture hoặc network monitoring có quyền truy cập payload.
- Lưu lượng mang tokens, PII hoặc DB credentials.

Phòng vệ:

- **Require mTLS** tại endpoint có kiểm soát và kiểm tra fail-closed.
- Cân nhắc **application-layer TLS/mTLS** với backend quan trọng nếu muốn bảo vệ độc lập với mesh.
- Dùng NetworkPolicy/firewall giới hạn đường direct.
- Kiểm tra certificate validation/trust roots và **plaintext negative tests** trong sandbox.
- Quan sát encrypted/unencrypted flow coverage bằng telemetry đúng điểm, không dựa trên một HTTP status đơn lẻ.

Không kết luận **“VPC private network đã mã hóa”** chỉ từ việc IP là private. Quy tắc mã hóa khác nhau theo hạ tầng, và identity/authorization vẫn cần được kiểm chứng riêng.

### 7.5. mTLS danh tính ở chặng proxy, không tự là danh tính người dùng

Trong hệ thống microservices:

~~~text
User Alice -> Frontend -> API Gateway -> Sidecar -> Orders API
~~~

Mesh mTLS có thể chứng minh **Gateway/Frontend workload identity**, không tự chứng minh **Alice được phép xem order của Bob**. Nếu một luồng bypass mesh, ứng dụng vẫn phải thực thi:

- JWT/OIDC token validation với issuer/audience/expiry.
- Resource/tenant authorization (object-level access checks).
- Input validation, SQL permissions và audit actions.
- Không tin X-Forwarded-User hoặc X-Authenticated-Principal do client tự gửi.

**Zero Trust** yêu cầu nhiều lớp: network route, transport peer identity, service identity và business authorization.

### 7.6. Mesh migration và mixed-mode traffic

Trong quá trình migration từ plaintext sang mTLS, PERMISSIVE có thể giúp ứng dụng ngoài mesh tiếp tục hoạt động. Nhưng nếu giữ PERMISSIVE lâu mà không theo dõi source identity, một luồng trực tiếp có thể **không chịu bảo đảm mTLS**.

Quy trình migration:

1. Inventory **mọi callers và receivers**, kể cả batch jobs và external gateways.
2. Kiểm tra tỷ lệ traffic có **mTLS peer identity** tại đích, không chỉ proxy count.
3. Cập nhật injection và policy cho các workloads cần tham gia.
4. Test fail behavior với **client không có mesh identity**.
5. Chuyển điểm nhận sang STRICT khi các dependencies đã sẵn sàng.
6. Giữ **NetworkPolicy/ingress restrictions** như ranh giới độc lập.
7. Duy trì detection khi plaintext traffic xuất hiện trở lại.

**Không chuyển STRICT trên production mà không kiểm tra cross-cluster/external clients**; điều đó có thể gây outage lớn. Cũng không duy trì PERMISSIVE vô thời hạn chỉ vì ngại sửa một client chưa onboard.

## 8. Authorization bypass và nhầm lẫn chính sách L4/L7

### 8.1. AuthorizationPolicy phụ thuộc điểm áp

Một service mesh có thể có **authorization policies** dựa trên source workload identity, namespace/service account, operation path, HTTP method hoặc các attributes khác theo triển khai. Nếu proxy không nằm trong đường truyền, nó **không thể kiểm tra** một request tới ứng dụng. Đây là sự khác biệt giữa:

- **Policy intent:** tài liệu/API mong muốn chặn một principal hoặc path.
- **Policy delivery:** control plane đã gửi cấu hình tới đúng proxy/gateway.
- **Policy enforcement:** traffic đi qua proxy và được kiểm tra thật.
- **Application authorization:** ứng dụng tự kiểm tra quyền nghiệp vụ, kể cả khi mesh cho phép.

Một chính sách ở mesh control plane không tự biến mọi port trong cluster thành một điểm kiểm soát truy cập.

### 8.2. Mục tiêu policy theo identity thay vì IP

Giả sử Orders API yêu cầu:

~~~text
Allow:
  frontend workload identity -> GET /orders/summary
  reporting workload identity -> GET /reports/orders

Deny:
  untrusted-dev -> Orders API
  any caller -> /admin if not dedicated admin identity
  any unauthenticated caller -> sensitive data operations
~~~

Nếu request tới ứng dụng **qua destination sidecar** và L7 policy được triển khai chính xác, proxy có thể chặn một số requests trước khi ứng dụng xử lý. Nếu một đường **direct app port** tránh điểm kiểm soát này, **backend ứng dụng cần tự thực thi authorization**; nếu không, quyền nghiệp vụ có thể bị vượt qua.

### 8.3. Ví dụ policy mang tính ý định

~~~yaml
# PSEUDO-YAML: không phải manifest Istio/Linkerd có thể apply nguyên xi.
security_intent:
  workload: orders-api
  permitted_sources:
    - service_identity: frontend
      methods: [GET]
      paths: [/orders/summary]
    - service_identity: reporting
      methods: [GET]
      paths: [/reports/orders]
  default_action: deny
  transport:
    require_authenticated_mtls: true
  paths_to_protect:
    - pod_ip_direct
    - service_cluster_ip
    - gateway
    - cross_namespace
    - cross_cluster
  controls:
    network_policy: allow_only_approved_peers
    mesh_destination_proxy: enforce_and_log
    application: validate_user_and_resource_permissions
~~~

**Pseudocode không tự cấu hình gì**. Để chuyển sang mesh thật, cần hiểu policy-specific inheritance, selectors, workload ports, action precedence và inbound capture. Ví dụ trong một số sản phẩm, tạo **ALLOW rule** làm thay đổi default behavior chỉ cho những workloads nó chọn; nếu không policy nào áp lên workload, truy cập có thể mặc định được cho phép. Không suy rằng “namespace đã có một policy tên deny-all” là mọi service bị deny.

### 8.4. Bypass HTTP policy khi traffic không được nhận diện HTTP

Ngay cả khi proxy được đặt trong đường đi, một HTTP authorization rule chỉ có hiệu lực nếu proxy:

- Nhận diện và xử lý traffic như **HTTP/gRPC** theo port/protocol config.
- Có quyền kiểm tra **method, path, headers** theo TLS termination/transport mode.
- Nhận được đúng cấu hình policy cho inbound listener.
- Không chuyển request qua đường TCP passthrough ngoài rule L7 dự định.

Nếu ứng dụng chạy HTTPS end-to-end và proxy chỉ nhìn **opaque TLS ciphertext**, proxy có thể thực thi một số **L4 identity policy** nhưng không đọc HTTP path; không nên kỳ vọng rule L7 nhìn thấy URL. Khi giao thức được khai báo sai hoặc proxy chuyển sang TCP forwarding, việc kiểm tra path/header có thể không tồn tại dù mTLS mesh giữa proxies vẫn hoạt động.

### 8.5. Service-to-service allow không thay user authorization

Ví dụ một frontend service được mesh cho phép gọi Orders API. Nếu backend tin rằng *mọi request từ frontend đều hợp lệ*, một lỗi frontend hoặc request giả qua frontend có thể đọc tài nguyên sai chủ sở hữu.

Phân quyền đúng phải chia:

1. **Mesh:** Frontend được gọi Orders API trên transport/port nào?
2. **Gateway/API:** JWT/identity/session có hợp lệ không?
3. **Backend application:** User/tenant có quyền đọc order cụ thể không?
4. **Database:** Query/row-level permissions và auditing theo thiết kế.

Bypass sidecar làm mất lớp (1) khi đường bị tránh; **không được để cả (2)–(4) vắng mặt chỉ vì tin lớp (1)**.

### 8.6. Kiểm tra policy theo từng hướng

Với traffic A→B:

| Vị trí | Có thể áp gì? | Kiểm tra cần có |
| --- | --- | --- |
| **Sidecar nguồn A** | Outbound route/timeout, traffic policy, mTLS origination, some egress restrictions | Source proxy thật sự nhận flow? |
| **Kubernetes CNI** | Egress/ingress NetworkPolicy peers/ports | Enforced vào đúng Pods/interfaces chưa? |
| **Gateway/Firewall** | Cross-zone policy, L7 nếu terminate phù hợp | Effective route có qua gateway không? |
| **Sidecar đích B** | Peer mTLS, inbound workload authorization, L7 checks khi thấy HTTP | Request thật sự vào listener đúng không? |
| **Ứng dụng B** | User/resource authorization, input checks, audit | Có deny khi mesh bypass không? |

**Không dựa chỉ vào outbound sidecar** để bảo đảm server đã xác thực/cấp quyền nếu client có thể bỏ outbound capture. Trong kiến trúc zero trust, **destination-side enforcement + application authorization + independent network segmentation** giảm hậu quả khi một nguồn không được bảo vệ.

## 9. Rủi ro telemetry, detection và forensic

### 9.1. Sidecar mất visibility như thế nào?

Sidecar thường cung cấp telemetry cho những kết nối mà nó xử lý: byte/requests, response code, TLS peer identity, retries, latency, tracing context và auth decision. Khi một luồng không qua proxy:

- **Request count/latency** tại proxy có thể giảm trong khi ứng dụng vẫn nhận traffic.
- **mTLS peer identity** có thể không có, không chứng minh client anonymous nếu một lớp TLS khác được ứng dụng kiểm.
- **Authorization deny logs** không xuất hiện dù có kết nối bị chặn ở NetworkPolicy.
- **Trace spans** của mesh thiếu hop, còn application spans có thể vẫn đầy đủ.
- **Retry/circuit-breaker metrics** không thấy traffic direct.
- Một dashboard service graph có thể **mất cạnh traffic**, dẫn tới nhận định sai về dependency.

**Không có sidecar logs không đủ để khẳng định bypass**: có thể collector/metrics exporter hỏng, sampling thay đổi, traffic dùng non-HTTP, hoặc data plane đã chuyển sang ambient/waypoint.

### 9.2. Ma trận nguồn telemetry

| Nguồn | Bằng chứng cung cấp | Hạn chế |
| --- | --- | --- |
| Pod spec/injection audit | Có proxy container, revision và annotations nào | Không chứng minh traffic được capture |
| Proxy config/status (xDS, routes, listeners, certs) | Cấu hình hiện tại trên proxy | Chưa chứng minh request thực đã đi qua |
| Proxy access/mTLS/AuthZ logs | Những luồng proxy xử lý và decision | Không bao phủ đường ngoài proxy |
| CNI/NetworkPolicy flow logs | Pod/IP/ports, allow/deny ở enforcement point | Không có user/resource authorization |
| Node/host firewall logs | Network paths ở host/node | Có thể chỉ thấy outer tunnel/NAT addresses |
| Ingress/Egress gateway logs | Những requests đi qua gateway | Direct path bypass có thể không xuất hiện |
| Application logs | Requests thực sự app nhận, identity/action nếu log đúng | Không tự chỉ ra mTLS bên ngoài proxy |
| DNS/Service/EndpointSlice | Name resolution và backend selection | DNS success không chứng minh request success |
| Kubernetes audit | Ai đổi Pod, labels, webhook, mesh policy | Không chứng minh data-plane traffic |
| Cloud VPC flow logs | Source/destination trên VPC node/Pod path tùy CNI | Có thể mất inner Pod IP vì encapsulation/NAT |
| SIEM/collector health | Exporter sống, ingestion lag, coverage | Không xác nhận request có/không nếu thiếu data sources |

### 9.3. Detect bằng chênh lệch app và proxy

Giả sử cùng một workload/route:

~~~text
10:00–10:05Z
  orders-app HTTP requests received:  4,800
  destination-sidecar requests seen:   4,600
  known health/local/internal probes:    200

Interpretation:
  Chênh lệch đã có giải thích sơ bộ.
  Chưa kết luận bypass.
~~~

Nếu khác:

~~~text
10:05–10:10Z
  orders-app HTTP requests received:  5,200
  destination-sidecar requests seen:   4,200
  expected exempt probes:                200
  unexplained gap:                       800
~~~

Đây là **tín hiệu điều tra**, nhưng chưa phải bằng chứng bypass. Cần xét **metric semantics** (requests vs connections), time window/clock skew, sampling, retries, readiness probes, sidecar caches, telemetry exporter drops và các entrypoints hợp lệ khác.

Nếu sau đối chiếu vẫn thấy app nhận requests từ nguồn không được phép, không có proxy/mesh verdict tương ứng, đồng thời **CNI/host flow logs xác nhận đường vào listener ngoài capture**, thì bằng chứng bypass mạnh hơn.

### 9.4. Sự thiếu vắng mTLS principal

Một HTTP access log có source IP nhưng không có **mesh peer identity** có thể do:

- Request không đi qua proxy mTLS.
- Service đang ở PERMISSIVE và nhận plaintext traffic.
- TLS terminate ở gateway, chỉ truyền header thay identity.
- Logger không ghi hoặc telemetry bị lấy mẫu.
- Traffic đến từ cùng Pod/localhost hoặc probe được exempt.
- App có TLS riêng và identity được ghi ở log khác.

Không mặc định một request thiếu principal là malicious, cũng không tự cấp quyền vì IP “nội bộ”. Đặt **định nghĩa nguồn đáng tin** và cách ghi nhận **unknown/missing evidence** trong audit.

### 9.5. Tương quan theo Pod UID và thời gian

Pod IP là địa chỉ có thể tái sử dụng. Để phân tích “flow 10.244.2.21 khi nào không có sidecar”, cần:

- Pod **UID**, namespace, serviceAccountName, owner reference, labels và create/delete time.
- Pod IP(s) và Node IP theo thời gian.
- Sidecar container/revision identity và readiness timeline.
- CNI/IPAM allocation/release logs.
- Proxy config/version và certificate serial/expiry theo thời gian nếu sản phẩm hỗ trợ.
- NetworkPolicy/mesh policy version, change ticket và commit ID.
- Event time từ app, proxy, CNI, API audit; kiểm tra clock skew và ingestion delay.

**Không join một flow log cũ với danh sách Pods hiện tại rồi khẳng định Pod đang mang IP đó đã gây flow cũ.** Khi bằng chứng thiếu, nêu rõ giới hạn quy nguồn.

### 9.6. Log nội dung nhạy cảm an toàn

Không ghi **private keys, mTLS SDS secrets, session tickets, API bearer tokens, cookies, unredacted customer payloads** vào SIEM chung. Ngay cả mesh access logs có thể chứa path/query với PII; cần **field-level redaction, retention và RBAC**, đặc biệt khi có nhiều tenants.

Telemetry phục vụ chứng minh control **không cần lưu plaintext secrets**. Ưu tiên workload identity, verified peer, selected route, policy decision, request ID, timing, bytes và status đã giảm thiểu thông tin cá nhân.

## 10. Egress bypass và các đường direct-to-destination

### 10.1. Vì sao egress là trường hợp dễ nhầm?

Một mesh có thể định nghĩa **egress gateway** để kiểm soát outbound traffic tới Internet, SaaS hoặc on-prem. Nhưng gateway chỉ bảo vệ đường mà traffic thật sự được route qua nó. Nếu Pod có alternate direct route đến Internet/cloud private service, request có thể **không chịu gateway policy**.

~~~mermaid
flowchart LR
    APP["Application Pod"] --> CAP{"Outbound captured?"}
    CAP -- "Có" --> SP["Source sidecar"]
    SP --> GW["Egress gateway\npolicy, telemetry"]
    GW --> EXT["External API"]
    CAP -- "Không" --> ALT["Node NAT / VPC route\nalternate path"]
    ALT --> EXT
    NP["NetworkPolicy / Cloud firewall"] -. "Có thể deny alternate path" .-> ALT
~~~

### 10.2. Những nguyên nhân cấu hình

- Namespace/Pod không được inject sidecar.
- Outbound IP/port exclusion rộng hơn nhu cầu.
- App route qua secondary interface hoặc hostNetwork.
- Egress gateway policy không match host/port/protocol.
- DNS trả IP mới, ServiceEntry/route policy hoặc destination selector chưa cập nhật.
- Đường Node NAT/VPC peering/private endpoint khác không đi qua gateway.
- Sidecar gửi traffic TCP opaque, trong khi policy chỉ được cấu hình cho HTTP.
- Một service mesh chỉ quan sát traffic nội bộ, không tuyên bố enforce mọi egress.

### 10.3. “ServiceEntry” hoặc external service registry không phải firewall

Một số meshes có objects khai báo external services/hosts và routing intentions. Việc thêm resource này có thể giúp proxy định tuyến, nhưng **không tự buộc một Pod không có sidecar phải dùng proxy**, và không tự ngăn direct connect qua Node/VPC route. Nếu mục tiêu **deny all external except approved**, cần:

1. Egress **NetworkPolicy** hoặc CNI extensions được thực thi.
2. Cloud firewall/SG/NAT policies hạn chế destinations theo yêu cầu.
3. Sidecar/egress gateway routing được kiểm chứng.
4. DNS egress/gateway policy không có đường bypass khác.
5. Application/IAM/resource permission controls ở dịch vụ đích.

Khi hệ thống chỉ bật mesh registry mà không có lớp chặn direct path, hãy coi đó là **routing/discovery policy**, chưa đủ để chứng minh network egress isolation.

### 10.4. Data exfil qua private network

Không chỉ Internet egress. Một Pod có thể truy cập **VPC peer, private endpoint, on-premises VPN, object storage API hoặc cluster khác** nếu network routes/IAM cho phép. Nếu SIEM chỉ theo dõi egress gateway public Internet, dữ liệu có thể đi qua **private path không quan sát**.

Kiểm soát:

- Network segmentation/NetworkPolicy cho east–west và egress cloud.
- VPC/Transit firewall, route isolation, private endpoint resource policies.
- mTLS/API authorization và DLP theo data classification.
- Flow logs ở CNI/node/VPC và ứng dụng đích, không chỉ egress proxy.
- Negative tests với unapproved destinations ở cả IPv4/IPv6.

**Private connectivity không phải bằng chứng một luồng chia sẻ dữ liệu đã được phê duyệt**, và mesh sidecar không tự thay IAM/resource-level access control.

### 10.5. Direct Pod IP và Service/Gateway bypass

Một backend được exposed qua Service/Gateway/WAF có thể còn **Pod IP listener** hoặc NodePort/LoadBalancer khác. Client có route nội bộ tới Pod IP có thể không qua gateway, tùy network topology và policy.

- **Bypass Gateway** không mặc định là **bypass destination sidecar**; inbound sidecar vẫn có thể bắt.
- **Bypass destination sidecar** có thể xảy ra nếu app port không capture, workload không inject, hostNetwork hoặc đường khác ngoài scope.
- Nếu Gateway thực hiện L7 authentication/WAF nhưng backend chỉ kiểm tra network source, **direct access có thể mất một lớp quan trọng**.

Do đó cần vừa **chặn direct origin paths** vừa giữ **backend application authorization**, không chỉ trông vào tên DNS/Ingress của ứng dụng.

## 11. Ambient/sidecarless mesh: không có sidecar chưa chắc là bypass

### 11.1. Mô hình sidecar không phải mô hình duy nhất

Một số triển khai service mesh sử dụng **node-level tunnel/proxy**, **ambient data plane**, **waypoint proxy**, eBPF hoặc kết hợp gateway thay cho việc inject một sidecar container vào mỗi Pod. Ở những hệ thống này, **không có container proxy cạnh ứng dụng là hành vi thiết kế**, không tự đồng nghĩa workload đã bị bỏ bảo vệ.

Hỏi đúng:

1. Workload được **đăng ký/onboard** vào mesh mode nào?
2. Data plane nào thực thi **L4 mTLS/identity**?
3. L7 HTTP authorization có được thiết kế qua **waypoint/gateway** hay không?
4. Những paths như **hostNetwork, secondary interface, direct Pod IP** có thuộc capture scope của mode đó không?
5. Có thể xác minh policy **trên chính đường traffic** bằng positive/negative tests không?

### 11.2. L4 và L7 không tự tương đương

Trong những kiến trúc ambient nhiều tầng, một thành phần node-level có thể xử lý **secure transport L4**, còn L7 routing/authorization lại phụ thuộc **một waypoint hoặc proxy bổ sung**. Do đó:

- Có L4 mTLS không đồng nghĩa HTTP path/JWT policy đã được áp.
- Workload được đưa vào ambient network không chứng minh L7 waypoint được đặt đúng.
- Waypoint chỉ thực thi trên traffic được route/enrolled qua nó theo sản phẩm.
- DNS/service routing, cross-namespace và direct IP cases phải được kiểm thử riêng.
- Sidecar và ambient có thể cùng tồn tại trong giai đoạn chuyển đổi, khiến policy coverage không đồng đều.

**Không dùng checklist “mọi Pod phải có sidecar container” làm kiểm soát duy nhất** cho các cluster đã áp một mesh data plane khác. Inventory cần có **mesh mode, effective enforcement point và test evidence**.

### 11.3. Phân loại sidecarless hợp lệ và bypass

| Quan sát | Bản chất có thể | Bằng chứng cần |
| --- | --- | --- |
| Pod không có sidecar, đã enroll ambient | Thiết kế bình thường | Node-level tunnel/waypoint status, policy tests |
| Pod không có sidecar, không thuộc mesh | Chưa được mesh bảo vệ | Admission/inventory, route/network controls |
| Pod có sidecar nhưng traffic không qua nó | Bypass hoặc exception | Proxy config, CNI path, app/network logs |
| L4 mTLS có, L7 policy không chạy | Missing waypoint/L7 path | Proxy participation, HTTP deny tests |
| Mesh proxy bị lỗi, direct traffic vẫn tới app | Cần điều tra fail-open/bypass | Trace timeline, effective path, backend auth |
| Sidecar telemetry mất, CNI mTLS logs còn | Có thể telemetry gap hoặc mode khác | Collector health và dataplane evidence |

### 11.4. Migration không nên tạo hai “vùng xám”

Khi chuyển giữa sidecar và ambient:

- Xác định **Pod nào thuộc mode nào** bằng selectors/labels và versioned inventory.
- So sánh **mTLS peer identity semantics**, trust domains và cert rotation giữa modes.
- Làm rõ nơi áp **L7 authorization, ingress/egress control và logging**.
- Chặn các direct paths ngoài hai modes bằng network/app controls.
- Test cả **cross-mode A→B, B→A** và external clients.
- Theo dõi thay đổi ALPN/protocol classification, gRPC/HTTP2, gateways và performance.
- Chỉ decommission sidecar policies khi enforcement tương đương đã được chứng minh.

**Một system đã có connectivity không có nghĩa security posture tương đương**. Migration cần so các **security invariants** chứ không chỉ latency/HTTP 200.

## 12. Defense in depth: chặn bypass khi proxy không ở trên đường

### 12.1. Phân tầng bảo vệ

~~~mermaid
flowchart TD
  SRC["Caller Pod / External client"] --> FW1["Source NetworkPolicy + cloud egress"]
  FW1 --> NET["CNI / VPC / transit network"]
  NET --> FW2["Destination NetworkPolicy / firewall"]
  FW2 --> MESH["Mesh data plane if enrolled\nmTLS and workload authorization"]
  MESH --> APP["Application authn / authz\nresource-level checks"]
  APP --> DB["Data service + IAM/DB permissions"]
  ADM["Admission, RBAC and Pod Security"] -. "Prevent unauthorized mesh opt-out" .-> SRC
  ADM -. "Enforce target workload posture" .-> MESH
  OBS["Audit, flow logs, proxy/app telemetry"] -. "Observe decisions" .-> NET
  OBS -. "Correlate identity and action" .-> APP
~~~

**Đường đi vật lý có thể khác sơ đồ**; một NetworkPolicy không mặc định tạo proxy hop, một gateway có thể đứng trước destination CNI, và các kiểm soát có thể xuất hiện nhiều lần. Mục tiêu là **không có một thành phần đơn lẻ nào quyết định toàn bộ trust**.

### 12.2. Kubernetes NetworkPolicy phải thực sự được CNI thực thi

Trong Kubernetes NetworkPolicy chuẩn:

- Policy chọn Pods trong một namespace bằng **podSelector**.
- Ingress/Egress isolation độc lập theo policyTypes.
- Các allow rules từ nhiều policies **cộng gộp**; thêm allow rộng có thể mở đường không mong muốn.
- Traffic Pod A→Pod B cần **source egress + destination ingress** cho phép nếu các hướng đã được cô lập.
- Kubernetes object tồn tại **không có nghĩa CNI đã enforce**.
- HostNetwork/secondary interfaces/NAT/service translation có thể có semantics khác theo CNI.

Mẫu **default deny ingress** cho namespace lab:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: baseline-deny-ingress
  namespace: mesh-lab
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Mẫu này chỉ là **baseline isolation trong namespace mesh-lab** khi CNI hỗ trợ. Những allowed flows cần một policy bổ sung; **không áp thẳng lên kube-system hoặc production** nếu chưa có dependency map và recovery plan. Không cho phép tạo NetworkPolicy sai rule hoặc mở hết traffic để “chữa lỗi mesh” khi chưa biết root cause.

### 12.3. Dùng source/destination selectors và port hẹp

Giả sử mesh-lab có frontend Pods nhãn app=frontend và orders Pods nhãn app=orders. Một allow rule ingress tại Orders:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-orders
  namespace: mesh-lab
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
~~~

Policy giới hạn **network reachability theo Pod labels**, không chứng minh frontend có mTLS identity hoặc token hợp lệ. Cần **admission/RBAC** để người không đáng tin không gắn nhãn app=frontend vào Pod tùy ý; và **mTLS/application auth** để chặn principal giả.

**Lưu ý về interception:** sidecar có thể dùng port đặc biệt để tiếp nhận inbound rồi chuyển tới app port. NetworkPolicy thường chọn **application destination/port** theo CNI semantics, nhưng NAT/order/host and gateway traffic khác nhau; phải test đúng đường khi apply. Không suy mọi mesh cần allow sidecar port từ bất kỳ nguồn nào.

### 12.4. Hạn chế direct-to-Pod bypass

Nếu gateway/sidecar phải là điểm áp policy:

1. Chỉ allow ingress tới backend Pods từ **các workloads/gateway peers** đúng nhu cầu.
2. Không expose application admin/debug ports trong Service/NodePort/LoadBalancer ngoài dự kiến.
3. Chặn direct origin access từ VPC peers/Internet qua **cloud SG/NACL/firewall**.
4. Giới hạn **egress từ untrusted namespaces** tới sensitive Pod subnets/ports.
5. Dùng application TLS/mTLS và authorization nếu cần bảo đảm độc lập với sidecar.
6. Kiểm tra các **alternate paths**: Pod IP, Service VIP, Node IP, hostNetwork, IPv6, secondary interface, cross-cluster private routes.

Không dùng DNS hiding hoặc Service name conventions làm cách duy nhất ngăn direct access. Một client biết Pod IP vẫn có thể thử kết nối nếu network route tồn tại.

### 12.5. Ngăn opt-out trái phép bằng admission và RBAC

Một developer/workload principal không nên tùy ý:

- Tạo Pod với nhãn/annotation **opt-out** khỏi mesh nếu policy yêu cầu tham gia.
- Đổi namespace injection/revision labels cho toàn tenant.
- Tạo Pod **hostNetwork/privileged/NET_ADMIN** ngoài nhu cầu đã duyệt.
- Thay CNI/sidecar traffic redirection rules.
- Sửa mesh mTLS/AuthZ policies hoặc xóa proxy/gateway config.
- Tự gắn **privileged Pod labels** để qua NetworkPolicy.
- Tạo Service/NodePort/LoadBalancer mở đường khác vào backend.

Kiểm soát:

- Kubernetes **RBAC least privilege** cho Pods/Deployments/namespaces/policies.
- **Validating admission/Gatekeeper/Kyverno/Kubernetes native policy** khi thích hợp với môi trường, kiểm tra opt-out/revision/hostNetwork/privileges.
- Namespace/project ownership và approval cho exceptions.
- **GitOps/policy-as-code** để phát hiện drift.
- Audit actor và changed fields với thời gian.

Admission không loại bỏ nhu cầu runtime testing; nó bảo vệ **đường đưa cấu hình vào cluster**, còn data plane quyết định hiệu lực thực tế.

### 12.6. Phòng vệ khi proxy bị compromise

Nếu sidecar hoặc mesh identity infrastructure bị xâm nhập, NetworkPolicy và application authorization giúp giảm phạm vi rủi ro nhưng không xóa toàn bộ. Kiểm soát gồm:

- Tách mesh trust domains và certificate issuance scopes khi cần.
- Mã hóa/tách quyền truy cập SDS/secret mounts/identity token.
- Harden sidecar image, resource limits, seccomp/capabilities theo khuyến nghị sản phẩm.
- Không expose proxy admin ports ra các network interfaces ngoài phạm vi quản trị.
- TLS cert rotation/revocation strategy và monitoring.
- Giữ **backend resource-level permissions** để một workload identity có cert hợp lệ cũng không truy cập dữ liệu vượt quyền.

Một mesh identity certificate cho biết peer thuộc workload/trust domain theo CA, **không phải một thẻ truy cập mọi database**.

### 12.7. Biện pháp khi application phải có port exempt

Một vài cổng như health probes, metrics hoặc bootstrap có thể được cố ý miễn redirect. Khi exception bắt buộc:

1. Ghi lý do nghiệp vụ/vận hành.
2. Giới hạn **bind address/port và nguồn truy cập**, không dùng default allow-all.
3. Đặt **NetworkPolicy/host firewall** hẹp và admission guardrails.
4. Không chứa administrative actions/credentials nhạy cảm trong một **probe endpoint không auth**.
5. Nếu cần identity, bổ sung TLS/authentication ở app hoặc proxy khác.
6. Tách metrics endpoint với application API quan trọng khi có thể.
7. Ghi exceptions vào inventory; test negative access định kỳ.

**Một cổng liveness miễn mesh capture không nên trở thành đường vòng truy cập admin API.**

## 13. Cách xác minh một luồng có thật sự đi qua sidecar

### 13.1. Kiểm tra từ đầu đến cuối thay vì chỉ một dashboard

Quy trình phòng vệ nên tìm **ba loại bằng chứng liên kết**:

**(A) Config intent:** Kubernetes/mesh policy muốn bảo vệ workload nào, hướng/port/identity nào?

**(B) Runtime state:** Pod thực tế có được enroll đúng mode, sidecar/capture/waypoint Ready, routes/certs/policy đã được nạp không?

**(C) Traffic evidence:** luồng thử nghiệm từ source được phép hoặc bị cấm có kết quả đúng và được ghi tại **đúng enforcement point** không?

| Cấp kiểm tra | Dương tính cần chứng minh | Âm tính cần chứng minh |
| --- | --- | --- |
| Admission | Workload bắt buộc có mesh mode đã chọn | Workload không thể tự opt-out trái quyền |
| Runtime | Sidecar/ztunnel/waypoint nhận config/cert hợp lệ | Pod không được phép chạy thiếu lớp bảo vệ |
| Traffic capture | Request hợp lệ tới backend đi qua điểm bảo vệ | Alternative path không làm mất kiểm soát |
| mTLS | Peer identity được xác minh | Peer chưa xác thực không được vào endpoint nhạy cảm |
| Authorization | Principal đúng action được allow | Wrong principal/scope/action bị deny |
| NetworkPolicy | Approved peer/port reachable | Unapproved namespace/port bị chặn |
| Logging | Proxy/CNI/app events liên kết đúng flow | Missing logs tạo alert, không bị coi là không có traffic |

### 13.2. Lệnh Kubernetes read-only cho người có quyền

Chỉ thực hiện trên **namespace lab hoặc workload thuộc quyền quản trị**:

~~~bash
# Liệt kê Pod và trạng thái các containers thực sự đang chạy.
kubectl get pods -n mesh-lab -o wide

# Kiểm tra spec, annotations, service account, container names/status.
kubectl get pod orders-api -n mesh-lab -o yaml

# Namespace labels, bao gồm labels mesh mode/revision nếu có.
kubectl get namespace mesh-lab --show-labels

# NetworkPolicy và Service/EndpointSlice trong namespace.
kubectl get networkpolicy -n mesh-lab -o yaml
kubectl get svc -n mesh-lab
kubectl get endpointslice -n mesh-lab

# Events để tìm scheduling, sandbox, admission và readiness issues.
kubectl describe pod orders-api -n mesh-lab
~~~

**Lưu ý:** việc xem Pod YAML hoặc logs có thể lộ environment variables/metadata nhạy cảm nếu hệ thống cấu hình kém; không đưa nguyên bản vào ticket công khai. Nếu ứng dụng chỉ cấp quyền đọc namespace, không tự tìm cách liệt kê tài nguyên toàn cluster.

### 13.3. Kiểm tra sidecar và proxy membership

Đối với mesh dùng Istio/Envoy sidecar, có thể tham khảo các nhóm công cụ như:

~~~bash
# Chỉ dùng nếu istioctl được cài, version phù hợp và người học có quyền.
# Xem trạng thái đồng bộ proxy với control plane.
istioctl proxy-status

# Xem proxy config ở phạm vi một Pod được quản lý.
# Lệnh/cú pháp cụ thể cần kiểm tra bằng trợ giúp của bản đã cài.
istioctl proxy-config listeners orders-api.mesh-lab
istioctl proxy-config clusters orders-api.mesh-lab
~~~

Các lệnh trên **mang tính minh họa về điều cần quan sát**, không phải một runbook bắt buộc cho mọi version/revision. Các meshes khác như Linkerd hay ambient mode sử dụng công cụ riêng và có thể **không có sidecar container cần inspect**. Một số lệnh proxy-config có thể trả dữ liệu lớn hoặc nhạy cảm; lọc fields cần thiết và bảo vệ kết quả.

Trong một deployment proxy thông thường, các dấu hiệu cần tìm:

- Sidecar/container hoặc node-level data-plane proxy có mặt theo mode đã duyệt.
- **Listener inbound/outbound** cho cổng dự kiến.
- **Route/cluster endpoint** đúng service và port.
- **mTLS policy/cert identity** và trust bundle đã load đúng.
- **Authorization filter/rules** nằm trên listener xử lý traffic cần bảo vệ.
- Proxy readiness và sync status, không có config reject/expired cert.
- Traffic counters/logs tăng khi gửi request lab tương ứng.

**Proxy config đúng mà client vẫn đi đường khác chưa chứng minh bảo vệ.** Cần phối hợp test trực tiếp từ nguồn đến đích cùng CNI/app telemetry.

### 13.4. Tạo bảng evidence từng flow

~~~text
Flow ID: F-ORD-001
Source: frontend Pod UID=...
Source SA/identity: frontend
Destination: orders Pod UID=...
Method/path: GET /orders/summary
Network path: Service DNS -> backend Pod
Capture expected: source outbound + destination inbound
Transport required: mesh mTLS, verified peer identity
NetworkPolicy: allow frontend -> orders TCP/8080
Application authorization: orders:read-summary
Expected: 200 + proxy/CNI/app event correlation
Observed: ...
Deviation: ...
~~~

Một negative flow:

~~~text
Flow ID: F-ORD-002
Source: untrusted Pod UID=...
Destination: orders API
Path: direct Pod IP or approved test Service URL
Expected: connection denied by NetworkPolicy
          OR mesh/app authentication/authorization denied
          according to explicit policy
Observed: ...
Expected blocker location: ...
Evidence: ...
~~~

**Không đặt kỳ vọng mọi denial đều trả HTTP 403**. NetworkPolicy có thể làm timeout/drop; TLS verification thường fail handshake; authorization ở proxy/app có thể trả HTTP response. **Quan trọng là request không được xử lý trái quyền**, không phải code trả về giống nhau.

### 13.5. Phân biệt xác thực mTLS và ứng dụng

Một kết quả kiểm thử nên tách:

~~~text
Network layer:
  TCP connection allowed?  yes/no
Mesh transport:
  Authenticated mTLS peer identity?  yes/no/unknown
L7 proxy policy:
  Accepted HTTP method/path?  yes/no/not-applicable
Application layer:
  Authenticated user/service?  yes/no
Authorization:
  Principal allowed action/resource?  yes/no
Telemetry:
  Source proxy, destination proxy, CNI, app logs?  complete/missing
~~~

Một HTTP 200 từ API **không tự chứng minh mesh mTLS được bật**, vì API cũng có thể trả 200 qua đường plaintext được phép. Một TLS handshake thành công **không tự chứng minh người dùng có quyền** trên tài nguyên.

### 13.6. Phát hiện Pod chưa có sidecar trong fleet

Không nên chỉ dựa vào đếm containers. Tối thiểu một inventory cần:

| Trường | Ý nghĩa |
| --- | --- |
| Cluster/namespace/Pod UID/owner | Ai chịu trách nhiệm workload |
| Mesh mode expected | sidecar, ambient, out-of-scope đã duyệt |
| Injection status/revision | Workload thực tế được inject đúng không |
| Sidecar/ztunnel/waypoint readiness | Data plane có hoạt động không |
| Capture scope | ports/interfaces/protocols bị loại trừ |
| Effective mTLS/AuthZ | Chế độ và policy thực tại endpoint |
| NetworkPolicy coverage | Có independent deny/allow enforcement không |
| Exemption owner/reason/expiry | Quyết định bypass có chủ đích |
| Last positive/negative test | Bằng chứng gần nhất |
| Telemetry/exporter health | Có nhìn thấy traffic thật không |

Nếu phát hiện unmeshed Pod ở **namespace ứng dụng nhạy cảm**, phải xác minh nó có **reachable từ peer không**, không lập tức gắn nhãn “compromised”. Có thể là workload system/test, một migration mode mới hoặc cấu hình lỗi; xác minh trước khi xử lý.

## 14. Lab có kiểm soát: chứng minh bảo vệ và phát hiện bypass

### 14.1. Mục tiêu và điều kiện

Lab này **không yêu cầu cố ý vô hiệu hóa mTLS hoặc tạo đường vòng vào production**. Mục tiêu là quan sát **proxy-in-path**, thử negative access từ Pod không được cấp quyền, so sánh logs và xác minh Pod readiness/mesh membership.

Điều kiện:

- Một Kubernetes **sandbox** có mesh được cài theo quy trình nhóm vận hành.
- Namespace có thể tạo workloads theo quyền đã cấp.
- CNI thực thi NetworkPolicy, nếu kiểm thử layer này.
- Workload image và tools được security/platform team phê duyệt.
- Người học có thể đọc Pod/proxy logs và proxy status theo RBAC.
- Không có secrets/production data trong lab.

**Nếu sandbox không có mesh**, vẫn có thể làm phần inventory/NetworkPolicy/mTLS threat model nhưng **không được ghi là đã kiểm chứng mesh enforcement thực tế**.

### 14.2. Topology lab

~~~mermaid
flowchart LR
  subgraph CL["Kubernetes training cluster"]
    F["frontend Pod\nmesh-enrolled"]
    U["untrusted Pod\nuntrusted identity"]
    SP["source proxy\nnếu sidecar mode"]
    DP["destination proxy\nnếu sidecar mode"]
    A["orders-api Pod\nTCP/8080"]
    F --> SP
    SP --> DP
    DP --> A
    U -. "negative test" .-> NP["NetworkPolicy\nor mesh AuthZ deny"]
    NP -. "deny" .-> A
  end
  C["Mesh control plane"] -. "config/certs" .-> SP
  C -. "config/certs" .-> DP
~~~

Sơ đồ là một **sidecar mode lab**; với ambient thay SP/DP bằng các data-plane enforcement points thực. Đừng thêm untrusted Pod vào đường production hoặc cấp cho nó Kubernetes RBAC/IAM không cần.

### 14.3. Minimal workload manifest để mô phỏng app

Ví dụ tạo namespace và Pod test **chỉ cho sandbox**:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mesh-lab
  labels:
    owner: security-training
---
apiVersion: v1
kind: Pod
metadata:
  name: orders-api
  namespace: mesh-lab
  labels:
    app: orders
spec:
  automountServiceAccountToken: false
  containers:
    - name: orders
      image: python:3.12-alpine
      command:
        - python
        - -u
        - -m
        - http.server
        - "8080"
        - --bind
        - 0.0.0.0
      ports:
        - containerPort: 8080
          name: http
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Service
metadata:
  name: orders-api
  namespace: mesh-lab
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

**Đây không phải production manifest**, vì chưa có probes, resource limits, image digest, TLS/app auth, high availability hoặc real business code. Mesh injection **không được tự suy ra** từ label **owner**; platform team cần enroll namespace/Pod theo mesh mode đã được duyệt **trước khi tạo Pod**. Nếu cần init container/proxy đặc quyền, phải theo cách CNI/mesh được tổ chức hỗ trợ; không tắt Pod Security Admission để chạy lab.

### 14.4. Hai clients với roles khác nhau

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: frontend
  namespace: mesh-lab
  labels:
    app: frontend
spec:
  automountServiceAccountToken: false
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
---
apiVersion: v1
kind: Pod
metadata:
  name: untrusted-client
  namespace: mesh-lab
  labels:
    app: untrusted
spec:
  automountServiceAccountToken: false
  containers:
    - name: test
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
        seccompProfile:
          type: RuntimeDefault
~~~

**Tách frontend và untrusted bằng label chỉ minh họa NetworkPolicy selectors**, không thay service identity certificate. Để test **mTLS source principal**, cần cấu hình service accounts và identity issuance do mesh/platform quản lý; không thể giả lập bằng cách chỉ đổi labels.

### 14.5. Baseline network deny/allow

Khi CNI hỗ trợ NetworkPolicy, có thể áp **baseline deny ingress** và allow frontend TCP/8080 trong namespace mesh-lab theo mục 12:

- **Allow:** frontend → Orders TCP/8080.
- **Deny:** untrusted-client → Orders TCP/8080.
- **Allow dependencies:** DNS và mesh/control-plane communication chỉ theo nhu cầu thật, không nới tất cả egress.

Nếu mục tiêu kiểm chứng **mTLS/AuthZ** độc lập với NetworkPolicy, một luồng bị NetworkPolicy chặn từ trước sẽ **không tới destination proxy**, do đó không chứng minh mesh đã deny. Muốn test mesh AuthZ cần một **test path được network layer cho đến proxy** nhưng có principal/action bị mesh từ chối; tiến hành trong sandbox có policy rõ và không mở service production.

### 14.6. Positive test: request qua Service

Khi Pod Ready và policies/enrollment đã đúng:

~~~bash
# Đọc Pod, containers và service endpoints.
kubectl get pod -n mesh-lab -o wide
kubectl get pod orders-api -n mesh-lab -o yaml
kubectl get service -n mesh-lab
kubectl get endpointslice -n mesh-lab

# Gọi bằng Service DNS từ Pod frontend trong sandbox.
kubectl exec -n mesh-lab frontend -- \
  wget -T 5 -qO- http://orders-api:80/
~~~

Kết quả kỳ vọng:

1. Request thành công khi gateway/mesh app policies cho phép.
2. Tương ứng có **request/connection evidence tại sidecar nguồn và đích** nếu đó là paths được capture.
3. Destination sidecar có **verified peer identity** nếu mTLS đang yêu cầu/thực thi.
4. Orders app có request log; **NetworkPolicy** cho phép source đúng.
5. Nếu không có proxy logs, điều tra exporter/config/mesh mode trước khi suy bypass.

**Một HTTP 200 từ máy chủ Python chỉ xác nhận HTTP app hoạt động**, không chứng minh mTLS hoặc policy identity—phải xem proxy certificates/transport evidence.

### 14.7. Negative test: nguồn không được cấp quyền

~~~bash
# Lệnh lab chỉ kiểm tra endpoint do nhóm sở hữu.
kubectl exec -n mesh-lab untrusted-client -- \
  wget -T 3 -qO- http://orders-api:80/
~~~

Kết quả kỳ vọng khi NetworkPolicy deny: untrusted-client **không tới được app**. Có thể là timeout hoặc lỗi kết nối tùy dataplane. Nếu NetworkPolicy không áp nhưng mesh authorization deny: response/error phụ thuộc proxy và protocol. **Không tự cấp quyền untrusted để “có kết quả đẹp”.**

Kiểm tra song song:

- NetworkPolicy selects đúng Orders/frontend/untrusted Pods?
- Pod source egress có đang bị policy khác chặn không?
- Request có được **destination sidecar** ghi nhận hay bị drop trước đó?
- App có nhận request không?
- Nếu app nhận request trái policy, có **NetworkPolicy/mesh capture gap hay authz issue**?

### 14.8. So direct Pod IP và Service path trong sandbox

Có thể kiểm chứng thêm **một endpoint do nhóm quản lý** bằng Pod IP lấy từ Kubernetes API. Đây **không phải hướng dẫn bỏ qua bảo vệ production**; mục đích là bảo đảm **direct Pod IP path không bỏ policy**.

~~~bash
# Xem Pod IP của orders-api trong lab.
kubectl get pod orders-api -n mesh-lab \
  -o jsonpath='{.status.podIP}'

# So kết quả tại Service và Pod IP bằng client lab.
# Thay TEST_POD_IP bằng IP đã đọc, không dùng IP của workload khác.
kubectl exec -n mesh-lab untrusted-client -- \
  wget -T 3 -qO- http://TEST_POD_IP:8080/
~~~

**Kỳ vọng:** không được có trường hợp untrusted request bị deny qua Service nhưng **được xử lý trái phép khi gọi Pod IP trực tiếp** nếu thiết kế yêu cầu cùng một authorization policy. Nếu khác nhau, xác định nơi chặn: Service/gateway, CNI, sidecar, app. Không vội kết luận lỗi của sidecar; Service-based path có thể qua một Gateway mà direct path không qua.

### 14.9. Test missing-sidecar scenario bằng đánh giá cấu hình

Để đánh giá rủi ro **Pod không injection** mà không phá sandbox:

1. Lấy inventory các **Pod spec/Pod template** và so với mesh mode expected.
2. Xác định Pod chưa enroll có đang **serve Service endpoints** không.
3. Kiểm tra NetworkPolicy/host/cloud firewall có cho untrusted source reach app port không.
4. Xem app có **TLS/authentication** độc lập không.
5. Nếu cần negative test trực tiếp, chỉ dùng **sandbox workload test riêng**, có approval và đường khôi phục rõ.
6. Đối chiếu hiệu quả admission: Pod ngoài mesh có bị chặn bởi guardrail khi thuộc nhóm bắt buộc mTLS không?

Không cần xóa sidecar, thay iptables hoặc cấu hình một lỗ hổng mới vào production để học bài.

### 14.10. Ma trận kiểm thử bảo mật và availability

| ID | Kiểm thử trong sandbox hoặc mô phỏng | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- |
| M01 | Pod app có sidecar theo mode yêu cầu | Injection/enrollment đúng | Pod spec + proxy status |
| M02 | Namespace bật injection nhưng Pod đã có từ trước | Nhận biết Pod cũ chưa reinject | Pod UID/creation time và containers |
| M03 | Approved frontend→Orders Service | Allow theo NetworkPolicy/mTLS/AuthZ | CNI + proxy + app logs |
| M04 | Untrusted→Orders Service | Deny theo policy đã định | Negative test, không có app operation |
| M05 | Untrusted→Orders Pod IP trực tiếp | Vẫn deny, không bypass gateway/mesh | Endpoint tests, CNI/proxy/app evidence |
| M06 | Frontend→Orders với wrong method/scope | L7/app deny | AuthZ decision và app audit |
| M07 | Client không có mTLS identity khi destination STRICT | Từ chối nếu tới enforced listener | TLS verification log |
| M08 | Request qua destination PERMISSIVE | Xác định plaintext path và chính sách khác | Peer identity/transport labels |
| M09 | Pod proxy not Ready | Không xử lý traffic trái policy; app readiness an toàn | Pod events/EndpointSlice |
| M10 | Proxy restarted (mô phỏng) | Fail behavior được ghi rõ | Flow/connection and readiness records |
| M11 | Probe/liveness port có exemption | Không truy cập admin actions | Port inventory, auth response |
| M12 | Containers cùng Pod gọi localhost | Ghi nhận đường local theo thiết kế | App logs, local test |
| M13 | hostNetwork Pod (mô phỏng) | Không giả định same policy coverage | Spec, host firewall/CNI capabilities |
| M14 | Secondary interface traffic (mô phỏng) | Có kiểm soát riêng hoặc documented exception | CNI attachment route/policy |
| M15 | UDP/QUIC traffic trong cluster | Chứng minh transport có/không mesh coverage | CNI/protocol logs |
| M16 | Outbound không qua approved egress gateway | Bị chặn bởi network/cloud controls | Egress policy + flow logs |
| M17 | DNS trả IP của private endpoint | Identity và route vẫn được xác minh | DNS, TLS, VPC flow |
| M18 | Sidecar/ambient mixed-mode cross traffic | Bảo đảm policy parity | Enrollment + mTLS/AuthZ tests |
| M19 | TLS certificate rotation | Full handshake mới xác minh đúng peer | TLS/cert lifecycle metrics |
| M20 | Wrong mesh principal tới allowed TCP/port | L7/mesh hoặc app deny | Identity in proxy/app logs |
| M21 | Gateway route bị tránh bằng direct Pod IP | Không bỏ WAF/AuthZ bắt buộc | Network deny hoặc backend auth |
| M22 | IP address reused sau Pod restart | Attribution dùng Pod UID + event-time | IPAM/Pod/audit timeline |
| M23 | Collector/exporter down | Có visibility alert, không báo không traffic | Exporter health |
| M24 | Egress qua VPC peering/VPN | Chỉ approved services, có flow/app audit | CNI + cloud logs |
| M25 | CNI không hỗ trợ NetworkPolicy (mô phỏng) | Không được tuyên bố deny enforcement | CNI capabilities/tests |
| M26 | Direct HTTP request có app auth hợp lệ nhưng thiếu mesh peer | Policy đã duyệt mới cho phép; nếu không phải deny | App logs + mesh identity |
| M27 | mTLS handshake OK nhưng user sai quyền | Application deny | API resource-level audit |
| M28 | App HTTP 200 nhưng proxy telemetry thiếu | Điều tra coverage, không tự coi bảo vệ đạt | Correlation and exporter health |
| M29 | Port exclusion được phê duyệt | Không expose sensitive data/management | Exception register + negative tests |
| M30 | Rollout từ PERMISSIVE sang STRICT | Approved traffic không outage, untrusted deny | Canary SLO + AuthZ/TLS metrics |

**M09–M10, M13–M15, M18–M19, M23–M25 và M29–M30** chỉ mô phỏng hoặc thực hiện trên sandbox chuyên dụng nếu có đủ quyền. Không được ngắt proxy, đổi mesh trust configuration, tạo route bypass hay làm gián đoạn CNI của cluster phục vụ người dùng.

### 14.11. Bảng log tổng hợp giả lập

~~~json
[
  {
    "event_id": "LB01",
    "event_time": "2026-11-28T06:00:00Z",
    "source": "kubernetes-audit-synthetic",
    "action": "PodCreated",
    "pod": "orders-api",
    "pod_uid": "orders-v2-uid",
    "mesh_mode": "sidecar",
    "proxy_ready": true
  },
  {
    "event_id": "LB02",
    "event_time": "2026-11-28T06:01:00Z",
    "source": "destination-proxy-synthetic",
    "request_id": "req-001",
    "verified_peer": "spiffe://corp.example/ns/mesh-lab/sa/frontend",
    "policy_decision": "allow",
    "http_status": 200
  },
  {
    "event_id": "LB03",
    "event_time": "2026-11-28T06:01:05Z",
    "source": "cni-flow-synthetic",
    "src": "untrusted-client",
    "dst": "orders-api",
    "dst_port": 8080,
    "decision": "deny"
  },
  {
    "event_id": "LB04",
    "event_time": "2026-11-28T06:02:00Z",
    "source": "application-synthetic",
    "request_id": "req-004",
    "remote_ip": "10.244.1.25",
    "http_status": 200,
    "proxy_request_id": null
  },
  {
    "event_id": "LB05",
    "event_time": "2026-11-28T06:02:01Z",
    "source": "collector-health-synthetic",
    "collector": "destination-proxy-logs",
    "healthy": false
  }
]
~~~

**Phân tích đúng:**

- **LB01** cho biết Pod được tạo với mesh mode sidecar và proxy Ready theo nguồn ghi; vẫn cần data-plane verification.
- **LB02** cho biết một request có mTLS peer identity ở destination proxy và được allow; còn authorization của business resource cần application audit.
- **LB03** cho thấy một negative flow bị CNI deny; chưa chắc proxy có nhận request này.
- **LB04** là app nhận request không có proxy request ID; **LB05** báo collector lỗi. Chưa đủ kết luận bypass; phải đối chiếu time window, exporter coverage, other log sources, flow path và application identity.

Đừng tự lấp giá trị **proxy_request_id=null** thành một identity hoặc gắn nhãn malicious khi nguồn telemetry bị thiếu.

### 14.12. Yêu cầu bài thu hoạch

Người học nộp:

1. Sơ đồ mọi **TLS endpoints, sidecar/ambient enforcement points** cho Frontend→Orders.
2. Bảng kiểm **Pod runtime state**, mesh mode/revision và capture exceptions.
3. **Ít nhất 10 positive/negative tests** từ M01–M30, có source/dest, expected decision và evidence.
4. Phân tích LB01–LB05, nêu **bằng chứng còn thiếu** để khẳng định bypass.
5. NetworkPolicy **default-deny + allow frontend** và lý do không tự giải quyết L7 authorization.
6. Một policy hành vi về **chặn opt-out injection** qua admission/RBAC.
7. Xác minh **direct Pod IP vs Service/Gateway** trong phạm vi lab.
8. Runbook **khi sidecar thiếu hoặc proxy not Ready**, phân biệt security incident với availability issue.
9. Kế hoạch **migrate PERMISSIVE → STRICT** có canary/rollback và review external dependencies.
10. Giải thích trường hợp **ambient không sidecar** nhưng vẫn có L4 mTLS và L7 waypoint theo kiến trúc.

**Tiêu chí đạt:** không dùng HTTP 200 hoặc proxy count như bằng chứng đủ; nêu rõ nơi thực thi và chính sách bị bỏ qua, có negative tests, có logs từ ít nhất hai lớp và giữ dữ liệu/cluster lab an toàn.

## 15. Threat modeling: rủi ro khi giả định sidecar luôn có mặt

### 15.1. Tài sản và ranh giới tin cậy

Trước khi đánh giá bypass, phải biết **thứ gì đang được proxy bảo vệ**:

- **Bí mật dữ liệu:** PII, tokens, payment/medical records, database traffic.
- **Workload identity:** service accounts, SPIFFE IDs, mTLS certificates và trust bundles.
- **Authorization policies:** source principals, namespaces, HTTP paths, RBAC scopes.
- **Ingress/egress boundaries:** WAF/API gateway, egress gateway, firewall, VPC/Transit routes.
- **Control-plane permissions:** quyền tạo Pod, patch labels, sửa mesh policy, traffic capture options và CNI config.
- **Observability:** proxy access logs, CNI flows, application audit, collector coverage.
- **Availability:** sidecar readiness, control plane, IPAM/CNI, certificate lifecycle, graceful drain.

**Threat model phải gắn với data flow cụ thể**, không chỉ đếm tổng sidecar pods. Một service đọc dữ liệu nhạy cảm bị direct-to-app bypass có impact cao hơn một synthetic health endpoint được miễn mesh capture có chủ đích.

### 15.2. Ma trận nguy cơ

| ID | Rủi ro | Điều kiện cần | Hậu quả tiềm năng | Phòng vệ/kiểm chứng |
| --- | --- | --- | --- | --- |
| SM-01 | Replica thiếu proxy do injection drift | Pod cũ/webhook không match | Một phần backend không chịu mesh policy | Inventory per Pod UID, enforced admission |
| SM-02 | Sidecar có nhưng listener/capture thiếu | Redirect rules/port scope sai | Direct app listener không chịu AuthZ/mTLS | Proxy config + CNI/app traffic test |
| SM-03 | mTLS ở PERMISSIVE quá lâu | Plaintext callers vẫn accepted | Transport identity thiếu, nguy cơ downgrade | Migrate STRICT theo canary và negative tests |
| SM-04 | STRICT được hiểu là kiểm soát toàn Pod | App port ngoài capture | Policy không nằm trên alternate path | Independent NetworkPolicy/app TLS |
| SM-05 | Opt-out annotation trái quyền | RBAC/admission cho sửa Pod template | Workload mới chạy ngoài mesh | Admission deny, namespace ownership/audit |
| SM-06 | Mixed proxy revisions | Rollout dở dang, policy semantics lệch | Intermittent deny/bypass, gaps | Revision inventory, compatibility tests |
| SM-07 | Startup race | App Ready trước proxy/capture | Mất availability hoặc traffic ngoài policy | Readiness gates, network deny |
| SM-08 | Proxy restart/failover path không rõ | Traffic capture/fallback khác dự kiến | Fail-open hoặc unexpected outage | Controlled failure-mode tests |
| SM-09 | Localhost admin API | Same-Pod containers share netns | Helper/compromised container truy cập admin | App auth, Pod isolation, loopback review |
| SM-10 | HostNetwork Pod | Host ns không chịu same capture | Tiếp cận node/other services | Pod Security, node firewall, identity controls |
| SM-11 | Secondary CNI interface | net1 route không qua sidecar | Missing mTLS/AuthZ/telemetry | Interface-specific policy/tests |
| SM-12 | UDP/QUIC traffic ngoài proxy scope | Mesh chỉ bảo vệ TCP path | Unobserved/unprotected transport | Protocol inventory, CNI/cloud policy |
| SM-13 | Source-only enforcement | Caller bỏ outbound capture | Egress/route restrictions bị tránh | Destination authz, egress NetworkPolicy |
| SM-14 | Destination-only enforcement absent | Unmeshed backend app listener | Wrong caller tới app | Enforce mesh enrollment/app authorization |
| SM-15 | Gateway/WAF bypass bằng direct Pod path | Direct routing, backend auth yếu | HTTP request không chịu gateway policy | Block origin paths, application auth |
| SM-16 | Egress bypass qua NAT/VPC peering | Alternate route không qua gateway | Data exfil/egress policy evasion | CNI/VPC firewall, route and NAT logs |
| SM-17 | L7 policy trên opaque TCP TLS | Proxy không đọc HTTP method/path | HTTP authorization không áp | Protocol/TLS termination design tests |
| SM-18 | Trusted header spoofing | Backend tin X-Authenticated-* từ client | Giả user/workload identity | Strip/overwrite, authenticate proxy peer |
| SM-19 | Sidecar admin/debug port exposed | Bind/ACL quá rộng | Info leak hoặc cấu hình/diagnostics misuse | Listen locally, RBAC/host firewall |
| SM-20 | mTLS credential issuance sai | Trust domain/SA RBAC bị lạm dụng | Peer identity không đáng tin | CA lifecycle, workload identity controls |
| SM-21 | Certificate rotation lỗi | Cert expired/CA lệch | Outage hoặc temptation disable mTLS | Monitor expiry, staged trust-rollout |
| SM-22 | NetworkPolicy không enforce | CNI thiếu support/agent down | Bypass path không bị chặn lớp dự phòng | Test actual deny, agent health |
| SM-23 | Selector label spoofing | Developer tạo Pods với labels privileged | Reachability mở ngoài policy | Label admission/RBAC, service mTLS |
| SM-24 | Sidecar logs biến mất | Exporter failed/sampling | Không thấy flow trái policy | Coverage heartbeats, app/CNI correlation |
| SM-25 | Sidecarless mode bị coi là unmeshed | Audit thiếu ambient knowledge | False positive, điều tra sai | Inventory mesh modes/enforcement |
| SM-26 | Ambient waypoint thiếu | L4 secure nhưng L7 AuthZ không áp | L7 policy bypass theo topology | Waypoint enrollment, method/path tests |
| SM-27 | Pod IP reused | SIEM nối IP với Pod hiện tại | Sai attribution incident | Pod UID/IPAM event-time joins |
| SM-28 | Unknown external workload | Interop migration thiếu identity | Unauthorized service access/outage | Strict vs permissive migration plan |
| SM-29 | Cross-cluster identity trust nhầm | Trust domains/gateways federation yếu | Cross-tenant privilege expansion | Explicit trust mappings and auth |
| SM-30 | Retry/timeouts không qua sidecar | Direct path bypass resiliency | Duplicate side effects/poor SLO | Idempotency, app timeouts, route governance |

**Một control-plane hoặc configuration weakness không tự có nghĩa dữ liệu đã bị đọc trái quyền.** Khi phát hiện SM-01/SM-02, cần chứng minh **reachable path + policy gap + application behavior** trước khi phân loại mức ảnh hưởng, đồng thời có thể áp containment chủ động với high-value assets.

### 15.3. STRIDE theo từng boundary

| STRIDE | Ví dụ | Evidence | Bảo vệ |
| --- | --- | --- | --- |
| **Spoofing** | Gắn labels/service headers giả, gọi app không có mTLS identity | Source Pod UID, peer cert, app principal | mTLS, admissions, per-request auth |
| **Tampering** | Đổi injection annotations, exclusions, Service routes | Kubernetes audit, GitOps drift | RBAC, approvals, immutable/controlled configs |
| **Repudiation** | Luồng app không có proxy trace, logs mất | App/CNI/collector timeline | Distributed tracing, audit retention |
| **Information disclosure** | Plaintext direct path hoặc exfil qua egress khác | Network flow, TLS evidence, data audit | TLS/app encryption, segmentation, DLP |
| **Denial of Service** | Proxy readiness/cert failure, startup race | Pod events, handshake failures, SLO | Graceful startup/drain, HA, safe rollback |
| **Elevation of privilege** | Untrusted client trực tiếp tới backend admin port | Mesh/NP/App allow/deny mismatch | Origin restrictions, app RBAC, least privilege |

### 15.4. Attack tree theo hướng kiểm soát

~~~mermaid
flowchart TD
  ROOT["Rủi ro: request đi tới service\nmà thiếu kiểm soát mesh dự kiến"] --> T{"Điều kiện phát sinh"}
  T --> INJ["Workload chưa enroll / injection gap"]
  T --> PATH["Bypass capture: port, IP,\ninterface hoặc loopback"]
  T --> POL["Policy không ở đúng listener\nhoặc không hiểu HTTP"]
  T --> ALT["Alternate route/gateway/egress"]
  T --> MON["Telemetry/visibility gap"]
  INJ --> DEF["Admission + Pod inventory\nand runtime verification"]
  PATH --> DEF2["CNI NetworkPolicy, host firewall,\napp TLS and port restrictions"]
  POL --> DEF3["Effective mTLS/AuthZ validation\nplus app authorization"]
  ALT --> DEF4["Route/egress controls\nand direct-path negative tests"]
  MON --> DEF5["CNI/app/proxy correlation,\ncollector health"]
  DEF --> RESP["Audit, alert, contain, retest"]
  DEF2 --> RESP
  DEF3 --> RESP
  DEF4 --> RESP
  DEF5 --> RESP
~~~

Đây là sơ đồ **phòng vệ**, không cung cấp quy trình xâm nhập. Các nhánh không loại trừ nhau; một incident có thể vừa có injection gap, vừa có L7 policy thiếu và log collector lỗi.

### 15.5. Blast radius theo trust tier

Ví dụ một Pod không inject nằm trong namespace Development:

- Nếu **CNI deny Development→Production** và destination app tự yêu cầu mTLS/authorization, nguy cơ bị giới hạn.
- Nếu **Development có route tới Production Pods**, SG mở rộng và backend phụ thuộc mesh-only authorization, blast radius cao hơn.
- Nếu Pod mang **cloud IAM permission** có thể đọc dữ liệu nhạy cảm và egress gateway bypass, rủi ro có thể liên quan cả data exfiltration.
- Nếu chỉ có **liveness endpoint** exempt không trả secrets và bị giới hạn Node-local source, tác động thấp hơn.

Không xếp mọi bypass cùng một mức. Cần hỏi **tài sản nào, peer nào, action nào, data classification nào, đường nào thực sự reachable** và có chứng cứ traffic hay không.

### 15.6. Chủ động giảm blast radius

Ưu tiên:

1. **Phân tách môi trường/trust tiers** bằng namespaces/NetworkPolicy, node pools hoặc clusters khi yêu cầu.
2. Mỗi service chỉ mở ports cần và không dùng direct admin endpoints trong Pod.
3. **Destination-side mTLS và application authorization** là điểm phòng thủ quan trọng.
4. Admission/RBAC không cho developer tự opt-out mesh hoặc thay policy/labels privileged.
5. Egress được hạn chế theo approved destinations, kể cả private VPC paths.
6. Control plane/CA/sidecar credentials được quản trị và rotate an toàn.
7. Telemetry có **coverage checks và response runbook** thay vì chỉ một dashboard proxy.

## 16. Troubleshooting: phân biệt bypass, mất mTLS và lỗi mạng

### 16.1. Bắt đầu từ triệu chứng thật

Một số biểu hiện:

- HTTP 200 từ nguồn đáng lẽ bị chặn.
- HTTP 401/403 nhưng đội phát triển gọi là “mesh chặn sai”.
- TLS handshake fail sau thay đổi STRICT.
- Pod không Ready hoặc proxy container restart.
- Một phần replicas trả response, phần còn lại timeout.
- Tracing thiếu destination sidecar hop.
- Gateway không ghi nhận traffic nhưng backend request count tăng.
- Egress gateway logs giảm sau cloud route change.

**Không phải mọi triệu chứng đều là bypass**. Phân loại:

1. **Control-plane:** policy/injection/certificate config gì đang được mong đợi?
2. **Runtime:** workload thuộc mesh mode nào, proxies/waypoints đã nhận cấu hình chưa?
3. **Network path:** routes và capture/NetworkPolicy đi qua đâu?
4. **Transport:** mTLS peer identity và TLS certificate verification thế nào?
5. **Application:** authn/authz và business outcome gì?
6. **Observability:** log sources có đầy đủ và đồng bộ event time không?

### 16.2. Quy trình quyết định

~~~mermaid
flowchart TD
  A["Nghi sidecar bypass hoặc request lỗi"] --> B{"Request có thật tới application?"}
  B -- "Không" --> B1["Xem NetworkPolicy, route,\nTLS rejection và proxy errors"]
  B -- "Có" --> C{"Workload thuộc mesh mode nào?"}
  C -- "Sidecar" --> D{"Proxy present, ready,\nconfig/capture đúng?"}
  C -- "Ambient" --> DA["Check node-level/waypoint\nL4 và L7 enrollment"]
  C -- "Out-of-scope" --> DB["Check approved exemption\nand independent controls"]
  D -- "Không" --> D1["Injection/redirect/race issue\ncheck alternate path"]
  D -- "Có" --> E{"Proxy đã xử lý cùng request?"}
  E -- "Có" --> E1["Check effective mTLS, AuthZ,\nprotocol and app permissions"]
  E -- "Không rõ" --> F["Correlate CNI/app logs,\ncollector health, request IDs"]
  DA --> F
  DB --> F
  D1 --> F
  F --> G{"Có evidence bypass và\npolicy không được áp?"}
  G -- "Có" --> H["Contain path + fix control,\nvalidate without disabling auth"]
  G -- "Chưa" --> I["Record uncertainty,\ncollect missing evidence"]
~~~

Sơ đồ không gán lỗi chắc chắn chỉ từ HTTP code hoặc log thiếu. **Khác biệt giữa request tới app và proxy xử lý request** là tín hiệu quan trọng nhưng phải xác minh metric/trace coverage.

### 16.3. Triệu chứng và lớp kiểm tra ưu tiên

| Triệu chứng | Giả thuyết | Bước xác minh |
| --- | --- | --- |
| Pod namespace có injection label nhưng thiếu proxy | Pod cũ, webhook selector/opt-out, ambient mode | Pod UID/spec, revision, mesh mode |
| Pod có sidecar nhưng app vẫn nhận traffic outside proxy logs | Collector loss, excluded port, direct path | Proxy config + CNI/app logs + exporter health |
| Sidecar not Ready, app nhận request | Readiness/capture race hoặc path khác | Endpoints, Pod startup, CNI redirect |
| Sidecar crash làm app timeout | Traffic vẫn redirect tới dead listener | Pod/CNI/proxy events, fail behavior |
| App nhận plaintext trái yêu cầu | Destination proxy bypass hoặc PERMISSIVE | TLS transport evidence + effective policy |
| STRICT làm một số clients lỗi | Clients thiếu mesh identity, trust bundle mismatch | Source identity, cert chain, migration inventory |
| HTTP 403 từ proxy | Mesh/L7 deny đúng hoặc policy lỗi | Proxy AuthZ decision, principal, route |
| HTTP 403 từ ứng dụng | App user/resource authorization | App/gateway request IDs |
| Direct Pod IP thành công nhưng Gateway route bị deny | Backend alternate path hoặc destination proxy not enforcing | Network reachability, app auth |
| HTTP policy không match | Opaque TCP, TLS passthrough, wrong listener | Protocol classification, TLS endpoint |
| Untrusted Pod có label được allow | Selector labels giả/misowned | Pod/Namespace audit, RBAC/admission |
| Sidecar probe/metrics port có request lạ | Port exemption quá rộng | Bind source/port, app capabilities, CNI |
| Egress gateway không thấy data | Direct NAT/peering path hoặc logging gap | CNI/VPC flow, route, collector |
| Secondary interface flow không có mesh identity | net1 traffic not captured | CNI attachment, interface routes |
| IPv4 policy đúng nhưng IPv6 khác | Capture/firewall chưa review IPv6 | IPv6 PodIPs/routes/policies |
| Mesh migration gây double proxy/loop | Mixed modes/incorrect enrollment | Effective path, revisions, listener config |
| mTLS cert expired | CA/rotation/sync issue | Certificate expiry, sidecar status |
| Client IP sai sau Gateway | NAT, trusted header processing | Socket peer, XFF trust, logs |
| gRPC streams reset khi rollout | Drain/timeout/protocol config | Proxy connection metrics, app errors |
| Một replica trả 200, replica khác deny | Mixed injection/config versions | Per-Pod proxy config/policy and endpoints |

### 16.4. Khi HTTP 200 xuất hiện ngoài policy

Đây là tình huống cần xem xét cẩn thận, nhưng **HTTP 200 có thể trả từ proxy/cache/health endpoint** và chưa chắc là một business action đã được thực hiện:

1. Xác định **hostname, IP/port, method/path, source Pod/identity và thời điểm**.
2. Xác minh response thực sự từ **backend application** hay một gateway.
3. Kiểm tra Proxy AuthZ/mTLS verdict tương ứng (nếu request được capture).
4. Kiểm tra NetworkPolicy/route và effective security controls trên direct path.
5. Xem application audit để xác định **resource/action** đã được xử lý hay chưa.
6. Thu thập cấu hình injection, sidecar/capture/waypoint của Pod UID tại thời điểm đó.
7. Nếu có lỗ hổng reachability, containment bằng **deny source/port, route correction hoặc app authorization** theo quy trình.

**Không vội tắt proxy hoặc mở firewall rộng hơn để tái hiện** trên production. Dùng sandbox/canary và bảo toàn evidence.

### 16.5. Khi mTLS handshake lỗi nhưng ứng dụng có vẻ khỏe

Một Pod app có thể mở port và liveness pass, còn proxy fail mTLS vì:

- Destination proxy STRICT yêu cầu peer có certificate/identity nhưng client không có.
- Workload certificate hết hạn, sai trust domain hoặc CA rollout không đồng bộ.
- Hostname/service identity binding hoặc authorization principal không khớp.
- Sidecar source chưa nhận config, mất control plane connectivity.
- Một path cross-cluster/gateway cần identity federation chưa được thiết kế.

**Cách khắc phục là làm đúng trust/cert/enrollment hoặc giảm traffic tới backend lỗi**, không tự chuyển STRICT sang PERMISSIVE hoặc bỏ TLS verification để làm cho HTTP 200.

### 16.6. Khi không có proxy trace nhưng CNI ghi flow

Một CNI flow cho source→destination TCP/8080 **được allow** không tự chứng minh bypass:

- Có thể là **captured flow** mà proxy exporter mất.
- Có thể là **same-Pod local call** được ghi không đầy đủ.
- Có thể là TCP traffic qua một L4 proxy không tạo HTTP spans.
- Có thể là connection giữ lâu, không ghi mỗi request.
- Có thể là service mesh đang dùng ambient mode.

Để phân biệt, kiểm tra **event time, proxy listener/counters, CNI policy verdict, app request ID, mesh mode và collector heartbeat**. Chỉ gắn nhãn confirmed bypass nếu chứng cứ kết nối thực sự tránh điểm enforcement mong đợi.

## 17. Incident response: containment, khôi phục và hậu kiểm

### 17.1. Định nghĩa ba cấp phát hiện

| Cấp phát hiện | Ví dụ | Hành động ban đầu |
| --- | --- | --- |
| **Posture drift** | Pod bắt buộc injection nhưng không có sidecar | Kiểm tra owner/mesh mode, hạn chế rollout, xác minh reachability |
| **Suspected bypass** | App requests vượt proxy metrics sau khi trừ probes nhưng thiếu CNI logs | Bảo toàn logs, kiểm tra exporter/capture/network path |
| **Confirmed unauthorized access path** | Untrusted source tới app, mTLS/AuthZ của proxy bị bỏ qua và app thực thi action trái quyền | Containment theo phạm vi, IR escalation, điều tra dữ liệu |

**Posture drift chưa đồng nghĩa compromise**. Nhưng với service giữ secrets/PII, một gap có thể cần containment trước khi có đủ bằng chứng data access—quyết định theo rủi ro, blast radius và yêu cầu tuân thủ.

### 17.2. Thu thập bằng chứng trước khi thay đổi

Thu thập trong phạm vi được phép:

1. Thời điểm, source/destination **Pod UID, namespace, service account, Pod IP, Node ID**.
2. Mesh mode/revision, Pod creation time, sidecar readiness và effective proxy config.
3. Mesh mTLS/authorization policies và certificate trust version.
4. NetworkPolicy/SG/firewall/route effective state, CNI version/capture exceptions.
5. Gateway/east–west routes và Service/EndpointSlice selection.
6. Proxy, CNI, DNS, Node/VPC flow, application/authorization logs.
7. Cloud/Kubernetes audit của mọi changes liên quan.
8. Telemetry ingestion delay/coverage, clock synchronization và missing records.

**Không dán raw tokens, private keys hoặc toàn bộ Envoy config chứa secret vào ticket mở rộng.** Lưu trong evidence store có quyền truy cập/retention phù hợp.

### 17.3. Containment theo mức ảnh hưởng

Các lựa chọn (phải có phê duyệt/IR authority):

- **Thu hẹp NetworkPolicy** ingress/egress của source/destination Pods.
- Sửa **cloud SG/firewall/route** nếu direct path nằm ngoài cluster.
- Chặn một **sensitive app port** ở đúng boundary khi dịch vụ không cần expose.
- Thay **authz policy của backend** để deny principal trái quyền, không phụ thuộc mesh sidecar.
- Tạm cô lập **Pod/Deployment đã xác định**, sau khi đánh giá availability và load balancing.
- Cấm/kiểm soát tạo Pod không injection qua admission nếu đó là policy bắt buộc.
- Bảo vệ egress gateway và chặn alternate Internet/private routes.
- Với compromise identity thật sự, cân nhắc thu hồi/rotate credentials theo quy trình.

**Không mặc định xóa mọi Pod/mesh control plane hoặc cắt toàn bộ mạng cluster** khi một port exemption sai. Chọn containment chính xác, có rollback và kiểm tra dependencies (DNS, metrics, node agents, service discovery).

### 17.4. Sửa root cause

| Root cause | Cách sửa bền vững |
| --- | --- |
| Injection missing | Sửa label/revision/webhook matching, redeploy theo controlled rollout |
| Port/interface exclusion không hợp lệ | Thu hẹp exception hoặc bảo vệ port/interface bằng controls khác |
| CNI redirection/config drift | Đưa về config hỗ trợ, kiểm tra per-node/Pod dataplane |
| mTLS PERMISSIVE không cần thiết | Lập migration và chuyển STRICT với negative tests |
| Mesh L7 policy không ở đúng listener | Sửa protocol classification, waypoint/gateway/route selection |
| Direct Pod/Service path bypass Gateway | Ingress restrictions và backend app authorization |
| HostNetwork/privileged workload | Phân vùng/chính sách Pod Security/host firewall, xem xét loại bỏ hostNetwork |
| Collector mất logs | Khôi phục exporter, bổ sung heartbeat/coverage alerts |
| Identity headers không đáng tin | Strip/overwrite, xác thực peer giữa proxies, app không tin header client |
| Mixed sidecar/ambient migration | Định nghĩa mode, route, L4/L7 enforcement và test matrix |

Đừng “chữa” bằng **DISABLE mTLS, verify none, allow-all NetworkPolicy hoặc bỏ AuthorizationPolicy** chỉ để các requests đang lỗi được chấp nhận. Nếu tổ chức phải cấp ngoại lệ khẩn cấp, cần **risk acceptance có thời hạn, compensating controls và owner**.

### 17.5. Verification sau containment và sau fix

Sau khi sửa:

1. **Positive test:** approved caller có request thành công, mTLS/authorization được xác minh.
2. **Negative test:** untrusted caller qua Service/Pod IP/gateway bị chặn đúng layer.
3. **Runtime test:** Pod spec/sidecar/ambient enforcement đang Ready, cấu hình effective.
4. **Capture test:** proxy/cni/app events tương quan cho đường đã sửa.
5. **Network test:** hostNetwork, secondary interface, cross-node/IPv6 và private routes theo phạm vi yêu cầu.
6. **Availability:** p95/p99, 5xx, gRPC streams, rollout/cert rotation không hỏng.
7. **Audit:** actor/change ticket/commit ID và thời gian rollback được ghi đầy đủ.

Không kết thúc incident chỉ vì **một curl trả 200**. Điều bắt buộc là những kết nối **phải bị deny vẫn không được xử lý trái quyền**.

### 17.6. Khôi phục mà không bỏ lớp bảo mật

Khi mesh proxy/config rollout gây outage:

- Tách **proxy dataplane failure** khỏi **app availability failure** bằng logs/health.
- Roll back tới **phiên bản proxy/policy đã được phê duyệt** còn giữ mTLS/AuthZ.
- Giữ CNI/NetworkPolicy deny với untrusted paths.
- Nếu một backend không còn xác minh được certificate, sửa CA/identity thay vì bỏ verification.
- Khi service cần failover qua region/cluster, kiểm tra **identity federation và gateway route** ở vùng mới.
- Không mở direct app port ngoài policy để “tạm bypass sidecar” nếu không có kế hoạch ngoại lệ chặt và compensating controls.

### 17.7. Post-incident review

Hậu kiểm nên trả lời:

- Tại sao policy intent không được thực thi trên đường cụ thể?
- Nguyên nhân là injection, capture, routing, mTLS, L7 policy hay telemetry?
- RBAC/admission/IaC đã cho phép thay đổi nào trái ý định?
- Có paths khác cùng rủi ro trong các namespaces/regions không?
- Những dữ liệu/tài nguyên nào **thật sự** được truy cập, dựa trên evidence gì?
- Negative tests đã thiếu trường hợp nào?
- Alert nào đã im lặng do collector gap?
- Ai sở hữu fix, test regression, exception expiry và timeline review?

**Ghi cả những điều chưa biết**, thay vì tự suy từ thiếu logs hoặc một IP NAT thành identity cụ thể.

## 18. Những tình huống thực tế cần nhận diện

### Tình huống A — Một replica không inject sidecar sau rollout

Orders API có 6 replicas. Năm Pods mới được inject proxy, một Pod cũ không có sidecar vì đã tồn tại trước khi bật namespace injection. Service load balance vẫn đưa một phần requests vào Pod cũ.

**Phân tích:** policy coverage có thể khác theo replica. Cần kiểm tra **Pod UID, creation time, spec, EndpointSlice và traffic** của từng replica. Nếu backend app thiếu auth, Pod cũ có nguy cơ truy cập ngoài mesh policy. Sửa bằng **controlled recreate/redeploy và admission guardrail**, duy trì NetworkPolicy/app authorization trong quá trình rollout.

### Tình huống B — mTLS STRICT nhưng một cổng admin vẫn nhận TCP

Security team đặt mTLS STRICT cho Orders workload, nhưng metrics/admin listener ở một cổng được miễn inbound capture lại nhận request từ Pod cùng namespace.

**Phân tích:** STRICT có thể chỉ áp tại **destination sidecar listener**; exempt port không tự chịu policy đó. Cần kiểm tra exception hợp lệ không, ràng buộc **NetworkPolicy/host binding/app authentication**, tách admin actions khỏi health endpoint. Không mở rộng danh sách exceptions chỉ để tiện troubleshooting.

### Tình huống C — App có sidecar nhưng TCP traffic đi qua net1

Một workload dùng secondary interface SR-IOV phục vụ traffic tốc độ cao. Sidecar bắt traffic eth0, trong khi app gọi database qua net1 và không có mTLS.

**Phân tích:** proxy present ≠ toàn bộ interface coverage. Đánh giá **routes/ip rules, CNI secondary attachment, cloud firewall và application TLS/mTLS**. Nếu net1 là ngoại lệ được duyệt, phải bảo vệ bằng các controls tương đương và telemetry riêng.

### Tình huống D — PERMISSIVE migration bị bỏ dở

Ban đầu cho phép cả plaintext và mesh mTLS để các batch jobs cũ hoạt động. Sáu tháng sau, tất cả workloads mới có sidecar nhưng vẫn còn một legacy client không có identity.

**Phân tích:** quá trình migration chưa đóng. Đo **mTLS/unauthenticated traffic coverage**, onboard client cũ, đặt timeline chuyển STRICT và test fail-closed. Không dùng việc proxy count tăng như bằng chứng mọi traffic đã được mã hóa.

### Tình huống E — API gateway deny nhưng direct Pod IP trả dữ liệu

Tại Ingress/Gateway, HTTP path /admin bị deny. Nhưng một Pod trong cùng cluster biết Pod IP backend, kết nối trực tiếp và ứng dụng không kiểm tra scope.

**Phân tích:** gateway policy **không nằm trên direct Pod IP route**; destination sidecar có/không có AuthZ cần được xác minh riêng. Chặn direct path bằng **NetworkPolicy**, bảo đảm app resource authorization, không dựa vào URL/path của Gateway như hàng rào duy nhất.

### Tình huống F — Egress gateway báo không có traffic SaaS mới

App team tích hợp một SaaS API, egress gateway dashboard vẫn hiển thị 0 request, nhưng SaaS báo đã nhận connections từ public NAT IP của cluster.

**Phân tích:** có khả năng **direct egress ngoài gateway**, hoặc telemetry gateway không đầy đủ. Kiểm tra CNI/VPC NAT flows, Pod IP→NAT mapping, proxy capture, gateway logs và cloud routing. Nếu policy yêu cầu đi qua gateway, chặn alternate path, không chỉ chỉnh dashboard.

### Tình huống G — Mesh proxy crash làm requests fail, không phải bypass

Sidecar của một Pod crash; traffic capture rules vẫn redirect vào local listener. Client requests timeout thay vì vào app trực tiếp.

**Phân tích:** đây có thể là **fail-closed availability incident**, không chứng minh bypass. Sửa proxy crash/readiness/certificate theo runbook; không bật bypass để ứng dụng “tạm chạy” khi policy yêu cầu mTLS.

### Tình huống H — Sidecar log thiếu nhưng CNI ghi rõ drop

Untrusted Pod thử gọi Orders API. CNI NetworkPolicy deny flow trước khi nó tới sidecar, nên proxy không có access log.

**Phân tích:** absence of proxy logs là hành vi **đúng với enforcement ở lớp trước**. Cần đọc CNI verdict và không gắn nhãn logging/bypass issue nếu flow thật sự bị chặn.

### Tình huống I — Pod label bị thay làm một source được allow

Backend NetworkPolicy chọn Pod nguồn app=frontend. Một user có RBAC rộng trong namespace có thể tạo Pod mới với label này, khiến network layer cho kết nối.

**Phân tích:** labels không phải cryptographic identity. Giới hạn create/patch labels qua **RBAC/admission**, đặt mTLS/source principal và app authorization theo service account. NetworkPolicy hữu ích nhưng không đủ cho workload trust.

### Tình huống J — Sidecarless ambient bị kiểm toán sai

Một namespace đã chuyển sang ambient mesh, không còn container Envoy sidecar. Dashboard kiểm toán cũ báo 100% Pods “unprotected”.

**Phân tích:** đây có thể là **false positive của inventory không hiểu mesh mode**. Xác minh node-level proxy/ztunnel và waypoint routes, L4 mTLS và L7 auth tests, không bắt mọi Pod phải có sidecar khi architecture chủ ý sidecarless.

### Tình huống K — Ambient có mTLS nhưng thiếu L7 waypoint

Pods đã được enrolled vào L4 secure transport, nhưng một HTTP method phải deny vẫn được app xử lý; team tưởng ambient tự enforce HTTP authorization.

**Phân tích:** L4 identity không tự thay L7 enforcement. Kiểm tra **waypoint selection/route**, L7 policy effective và app authorization. Tùy kiến trúc, phải đưa traffic qua đúng waypoint hoặc đặt authorization tại app/gateway.

### Tình huống L — HTTP traffic opaque nên path policy không chạy

Client app tự dùng TLS, sidecar chỉ xử lý opaque TCP vì cấu hình protocol. Security team áp L7 rule deny /admin nhưng proxy không có HTTP visibility.

**Phân tích:** cần đánh giá **TLS termination và protocol classification**. L7 rule chỉ có thể đọc path khi proxy được phép thấy HTTP; nếu yêu cầu application TLS end-to-end, nên đặt authorization tại app hoặc một endpoint/gateway có quyền termination được duyệt.

### Tình huống M — Startup race trong Pod

App vừa mở listener và readiness trả 200, nhưng sidecar chưa nhận identity certificate. Một số clients thấy reset, một số probes thấy app healthy.

**Phân tích:** phân biệt **app process health** với **secure endpoint readiness**. Dùng proxy readiness/Pod service readiness coordination, CNI deny for unauthorized direct flows; test during rollout/cert rotation. Không mặc định mọi proxy-not-ready đều fail-open.

### Tình huống N — Same-Pod helper truy cập local admin API

App có local admin port chỉ bind 127.0.0.1, team cho rằng sidecar mTLS bảo vệ port đó. Một helper container trong Pod cùng network namespace có thể kết nối.

**Phân tích:** same-Pod localhost không phải ranh giới auth giữa containers. Tách workloads khác trust level, đặt app auth/Unix socket permissions hoặc bỏ admin API không cần; không dựa vào NetworkPolicy cho local loopback.

### Tình huống O — IPv6 policy chưa được kiểm tra

Một cluster dual-stack có app IPv6 listener, nhưng sidecar exclusions/NetworkPolicy/firewall tests chỉ chạy IPv4. Một client có AAAA record dùng IPv6 path khác kỳ vọng.

**Phân tích:** cần kiểm tra IPv6 capture, route, mTLS, authorization, network policy và telemetry; không suy policy IPv4 đã áp toàn bộ các address families.

### Tình huống P — Cloud VPC peering tạo alternate path

Cluster có VPC-native Pod IPs, một VPC đối tác mới được peered và firewall mở tới Pod subnet. Dịch vụ backend không có network policy hạn chế nguồn mới.

**Phân tích:** đây là **thay đổi reachability ở hạ tầng**, có thể tạo direct path ngoài Gateway. Cần review VPC routes/SG, CNI NetworkPolicy, workload identity và backend authorization; không cho rằng “internal Kubernetes Service” chỉ reachable từ cluster.

### Tình huống Q — Gán nhầm Pod do IP tái sử dụng

Một flow lúc 10:00 phát từ Pod IP 10.244.2.21, nhưng Pod đó đã bị xóa và IP được cấp cho Pod khác lúc 10:10. Dashboard hiện tại gắn flow cũ vào workload mới.

**Phân tích:** cần join flow theo **event time + Pod UID/IPAM mapping**. Sai attribution có thể làm đội ứng cứu chặn nhầm workload hợp lệ và bỏ lỡ nguồn thật.

### Tình huống R — Sidecar rollback vô tình hạ cấp mTLS

Một rollout proxy mới gây lỗi handshake, team rollback bằng cách vô hiệu authorization filter hoặc chuyển PERMISSIVE. Requests trả 200 nhưng source identity không còn được xác minh như yêu cầu.

**Phân tích:** rollback phải giữ **security invariants**; dùng phiên bản proxy/cert đã được phê duyệt, sửa CA/trust domain và cô lập backend lỗi. Nếu có ngoại lệ khẩn cấp, áp compensating controls và time-bound risk acceptance.

## 19. Chính sách mesh minh họa và giới hạn enforcement

### 19.1. Ví dụ Istio PeerAuthentication ở đích

Trong một sandbox **Istio sidecar mode** có workload Orders được mesh quản lý đúng, một policy mTLS có thể có dạng:

~~~yaml
# ISTIO EXAMPLE — chỉ tham khảo cho sandbox, yêu cầu xác minh version.
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: orders-strict-mtls
  namespace: mesh-lab
spec:
  selector:
    matchLabels:
      app: orders
  mtls:
    mode: STRICT
~~~

Ý định: đối với **những traffic đi vào endpoint mesh được chọn và xử lý theo policy**, yêu cầu mTLS. Nó **không thay**:

- Kubernetes NetworkPolicy từ untrusted Pods.
- App TLS/authorization nếu cần bảo vệ độc lập với sidecar.
- Admission bảo đảm Orders Pod thực sự được inject/enroll.
- Runtime validation rằng inbound traffic không bypass listener.
- Gateway/host/cloud firewall đối với các alternate paths.

Không copy nguyên policy này vào production khi chưa kiểm tra **effective policy precedence, namespace/workload labels, mesh mode, service accounts, inbound ports và compatibility**. Một bản mesh cũ/mode khác có thể dùng API version hoặc semantics khác.

### 19.2. Ví dụ AuthorizationPolicy giới hạn caller và HTTP action

~~~yaml
# ISTIO EXAMPLE — minh họa intent cho sandbox với HTTP app.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-allow-frontend-summary
  namespace: mesh-lab
spec:
  selector:
    matchLabels:
      app: orders
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "spiffe://corp.example/ns/mesh-lab/sa/frontend"
      to:
        - operation:
            methods:
              - GET
            paths:
              - /orders/summary
            ports:
              - "8080"
~~~

Trong ví dụ, service identity ở principal là **giả định**. Chỉ khi mesh trust domain thực tế là **corp.example**, source dùng đúng service account **frontend** và certificate identity hợp lệ, rule mới match như dự kiến. Container/Pod name **frontend không tự tạo service account mang cùng tên**. Nếu ứng dụng lab vẫn dùng default ServiceAccount, cần thiết kế đúng service accounts/mesh identities hoặc dùng một test policy hẹp khác; không thay principal bằng wildcard để che lỗi.

**Mấu chốt:**

- Policy **ALLOW** chỉ bảo vệ các requests được **đúng mesh authorization enforcement point** xử lý và protocol được nhận diện.
- Nếu một workload không có proxy, ứng dụng có alternate path, hoặc traffic không đến đúng listener/waypoint, không thể giả định policy được áp.
- Nếu **HTTP method/path không được proxy nhìn thấy**, L7 rule sẽ không có ý nghĩa như đã thiết kế.
- Một policy ALLOW ở destination không mặc định thay **Kubernetes NetworkPolicy, user authorization hay DB permissions**.
- API/mesh version, rule precedence và DENY/CUSTOM/ALLOW semantics cần đối chiếu sản phẩm; không coi ví dụ này là policy-as-code đã nghiệm thu.

### 19.3. Phân biệt mTLS policy và route policy

| Mục tiêu | Công cụ thường cần | Sai lầm thường gặp |
| --- | --- | --- |
| Chứng minh caller workload identity | Mesh mTLS + peer validation | Dùng Pod IP hoặc labels như identity |
| Chặn untrusted Pod network path | CNI NetworkPolicy/cloud firewall | Chỉ đặt AuthorizationPolicy trong Pod không có sidecar |
| Hạn chế HTTP path/method | L7 proxy/waypoint hoặc application authorization | Proxy chỉ thấy opaque TCP mà kỳ vọng đọc path |
| Chặn direct origin bypass Gateway | Backend NetworkPolicy/firewall + app auth | Chỉ cấu hình Ingress/Gateway |
| Hạn chế arbitrary outbound traffic | Egress NetworkPolicy/CNI+cloud egress | Chỉ tạo egress gateway route |
| Bảo vệ localhost admin API | Application auth/IPC permissions/Pod trust model | Chỉ đặt mesh STRICT |
| Bảo đảm injection | Admission + mesh enrollment/runtime inventory | Chỉ gắn một label rồi không kiểm tra Pod thực |

### 19.4. Hành vi fail-closed phải được mô tả như testable invariant

Ví dụ một nhóm đặt mục tiêu:

~~~text
When frontend proxy is down:
  frontend must not silently send plaintext requests to Orders.

When Orders destination proxy is down:
  unauthorized clients must not reach Orders via direct Pod IP.

When mesh control plane is temporarily unavailable:
  existing data plane policy must not silently downgrade mTLS;
  service availability / certificate lifetime behavior is documented.

When collector is down:
  the absence of a proxy log must be marked as a coverage gap.
~~~

Đây là **yêu cầu thiết kế**, không phải khẳng định hành vi mặc định của mọi mesh. Mỗi invariant cần được kiểm chứng trên version/mode/data path thật, với quy trình mô phỏng có kiểm soát.

### 19.5. Mesh policy không thay cloud security boundary

Trong cloud/hybrid:

~~~text
Kubernetes Pod -> Sidecar -> Cloud VPC routing
    -> VPC peering/Transit/VPN -> Database/API
~~~

Khi destination là **service ngoài mesh**, chỉ có proxy nguồn có thể xử lý traffic. Không có **destination sidecar** để xác minh peer mesh identity ở phía dịch vụ đó, trừ khi có gateway/proxy hoặc cơ chế federation phù hợp. Nếu mục tiêu yêu cầu TLS server authentication, phải dùng **TLS origination/peer verification đúng SAN/CA hoặc application TLS**, cùng IAM/resource authorization phía dịch vụ.

**Không suy rằng sidecar phía nguồn một mình tự mang lại mTLS end-to-end tới một database legacy**. Bảo đảm transport phải chỉ rõ **TLS endpoints thật** ở từng chặng.

## 20. Checklist thiết kế, kiểm toán và nghiệm thu

### 20.1. Inventory và onboarding

- [ ] Mỗi workload có **cluster/namespace/Pod UID/owner/service account/trust tier**.
- [ ] Đã phân loại **sidecar, ambient/waypoint hoặc out-of-scope** theo policy rõ ràng.
- [ ] Namespace và Pod templates có injection/enrollment **đúng mode và revision**.
- [ ] Không có Pod cũ chưa reinject đang serve traffic nhạy cảm ngoài ý định.
- [ ] Mutating admission webhook match/failure behavior được kiểm tra.
- [ ] Có **validating admission** hoặc guardrail tương đương chặn opt-out trái quyền.
- [ ] RBAC hạn chế chỉnh Pod/namespace labels, sidecar exclusion, hostNetwork và policy resources.
- [ ] Mọi exception có **owner, purpose, scope, expiry/review**.
- [ ] Không đánh đồng sidecarless ambient với thiếu bảo vệ khi data plane riêng đang thực thi.

### 20.2. Capture và path validation

- [ ] Biết traffic nào được capture: **inbound/outbound, TCP/UDP, IPv4/IPv6, ports, IP ranges, interfaces**.
- [ ] Proxy listeners/routes/filters và workload certificate/trust bundle được nạp đúng.
- [ ] Thử **Service DNS/ClusterIP**, direct Pod IP, Gateway và external/peering paths nếu có.
- [ ] Đã kiểm tra **localhost cùng Pod**, admin/debug/metrics/probe ports và exemptions.
- [ ] hostNetwork/hostPort/NodePort/secondary CNI có controls tương đương hoặc documented exception.
- [ ] Không có direct origin route bypass WAF/authorization bắt buộc.
- [ ] Egress gateway không bị bypass qua Node NAT, Internet, VPC peering hoặc private endpoint.
- [ ] CNI NetworkPolicy được thực thi, không chỉ tồn tại trong Kubernetes API.
- [ ] Kiểm tra **cross-node, cross-AZ, dual-stack và multi-cluster** theo phạm vi.
- [ ] Khi mesh proxy tạm mất, không có **silent plaintext fallback** ngoài policy.

### 20.3. mTLS và workload identity

- [ ] Mesh peer identities dựa trên **certificate/trust domain/service account**, không chỉ Pod IP/label.
- [ ] Destination mTLS mode **STRICT/PERMISSIVE** được biết tại từng workload/port.
- [ ] Mọi PERMISSIVE exception còn cần thiết đều có kế hoạch loại bỏ hoặc controls thay thế.
- [ ] Lỗi CA/SAN/trust domain/certificate expiry được monitor và có rotation plan.
- [ ] Application/legacy external TLS được kiểm tra **independent of mesh** khi cần.
- [ ] Source proxy và destination proxy roles không bị nhầm; không xem source-only enforcement là đủ.
- [ ] Gateway/sidecar/ambient mode hỗ trợ đúng transport, HTTP/2/gRPC, UDP/QUIC theo design.
- [ ] Không dùng disable TLS verification như một giải pháp vận hành mặc định.

### 20.4. Authorization, ingress và egress

- [ ] Mọi sensitive service có **application resource-level authorization** độc lập với mesh.
- [ ] Mesh L7 policy nằm trên listener/waypoint **thực sự thấy HTTP method/path**.
- [ ] Policy default/ALLOW/DENY precedence được kiểm tra theo mesh version.
- [ ] Mọi caller chưa được xác thực có **negative test** và không xử lý sensitive actions.
- [ ] Backend không tin **client-controlled identity headers** mà không có trusted proxy chain.
- [ ] Egress allowlist bao gồm DNS/telemetry/control dependencies **đúng phạm vi**, không allow all Internet.
- [ ] CNI ingress/egress segmentation theo workloads/ports, không chỉ namespace naming.
- [ ] Cloud SG/firewall/route hạn chế external/private origin access.
- [ ] User identity và service identity được phân biệt trong logs/policies.

### 20.5. Readiness, failure modes và resilience

- [ ] Pod không vào Service backend set trước khi **security data plane đủ Ready** theo thiết kế.
- [ ] Có cách quan sát proxy/cert/config sync failures theo revision.
- [ ] Có kế hoạch **graceful drain/termination** cho long-lived streams.
- [ ] Có failover/cert rotation/cross-cluster tests với security policy parity.
- [ ] Khi proxy chết/control plane unavailable, đã đo **fail-open/fail-closed behavior** trong sandbox.
- [ ] Rollback không yêu cầu tắt mTLS/AuthZ hoặc mở network unrestricted.
- [ ] Hệ thống có canary, recovery owner, change ticket và SLO thresholds.

### 20.6. Observability và điều tra

- [ ] Inventory Pod UID/IP mapping và mesh mode theo **event time**.
- [ ] Proxy access/mTLS/AuthZ logs được tương quan với CNI/network/app audit logs.
- [ ] Có health monitoring cho **metrics/log exporter và ingestion delay**.
- [ ] Có alert khi app request count và proxy count lệch đáng kể ngoài baseline hợp lệ.
- [ ] Có alert khi unmeshed Pod phục vụ sensitive Service endpoints.
- [ ] Có alert về injection/port exclusion/mesh policy/CNI changes ngoài GitOps.
- [ ] Phân biệt **no traffic, denied traffic, missing telemetry và confirmed bypass**.
- [ ] Không log secrets, tokens, private keys hoặc khách hàng PII thô không cần thiết.
- [ ] Incident playbook có containment/rollback và test deny từ đúng source.

### 20.7. Bảng nghiệm thu chứng cứ

| Hạng mục | Bằng chứng tối thiểu | PASS khi |
| --- | --- | --- |
| Mesh participation | Expected mode vs runtime spec/agent status | Enrolled đúng, exceptions có approval |
| Traffic capture | Proxy listeners/routes + flow tests | Protected paths đi qua đúng enforcement point |
| mTLS identity | Verified peer cert/identity log | Untrusted/anonymous peers không được vào sensitive backend |
| L7 authorization | Positive/negative method/path tests | Caller trái quyền bị deny khi đến endpoint L7 |
| NetworkPolicy | CNI enforcement + allowed/denied tests | Direct Pod IP và Service paths không vượt quyền |
| External paths | Gateway/NodePort/VPC/cloud firewall inventory | Không có public/private alternate origin path ngoài policy |
| Startup/rollout | Pod/sidecar readiness, EndpointSlice, cert status | Không nhận traffic trước lớp bảo vệ bắt buộc |
| Egress | Gateway/CNI/VPC flow correlation | Không có direct unauthorized NAT/peering path |
| Telemetry | Proxy/CNI/app events + exporter health | Có coverage, event time và request IDs phù hợp |
| Rollback/IR | Playbook + canary tests + change records | Không phải hạ cấp mTLS/AuthZ để phục hồi |

**Một đợt nghiệm thu không thể kết thúc với kết luận “sidecar đã được inject”.** Cần ít nhất một luồng hợp lệ **được xử lý đúng** và một luồng trái quyền **bị chặn tại lớp phù hợp**, cùng chứng cứ cấu hình/data plane/telemetry.

## 21. Bài tập thiết kế và câu hỏi ôn tập

### 21.1. Bài tập kiến trúc: không để mesh-only policy thành điểm yếu duy nhất

Giả sử một doanh nghiệp có:

~~~text
Cluster: enterprise-k8s

Namespaces:
  edge      -> ingress-gateway
  web       -> frontend
  app       -> orders-api, payments-api
  data      -> database-proxy
  platform  -> DNS, CNI, telemetry

Traffic:
  Internet -> gateway -> frontend -> orders-api
  reporting VPC (peering) -> reporting gateway -> orders-api
  orders-api -> payments-api
  orders-api -> on-prem ERP via VPN

Mesh deployment:
  Most workloads use sidecar mode.
  One namespace is migrating to ambient mode.
  Several legacy Jobs were created before injection enabled.
  Health/metrics ports have controlled exemptions.

Security requirements:
  Mesh mTLS required for east-west sensitive services.
  Orders API must validate user/tenant permissions.
  Only approved workloads may reach payments/database ports.
  External SaaS egress must use controlled gateway.
  No silent downgrade to plaintext on proxy failure.
~~~

Yêu cầu:

1. Vẽ **data-flow diagram** với mọi Pod/sidecar/ztunnel/waypoint/gateway và trust boundaries.
2. Tìm mọi **đường direct-to-app** có thể không đi qua ingress gateway, destination sidecar hoặc waypoint.
3. Xác định **Pod nào thiếu injection** và liệu nó đang được Service/EndpointSlice chọn làm backend.
4. Thiết kế **NetworkPolicy allowlist** edge→web→app→data, giữ DNS và telemetry dependencies.
5. Thiết kế mTLS identity policy và **wrong-principal negative tests**.
6. Thiết kế application authorization cho Orders API để chặn đọc dữ liệu sai tenant dù request qua Frontend.
7. Kiểm soát **hostNetwork, admin/debug/probe ports và secondary network exceptions**.
8. Xác minh **UDP/QUIC, IPv6 và multi-cluster** nằm ở mesh mode nào hoặc cần controls khác.
9. Thiết kế **egress gateway + cloud firewall/route** ngăn direct SaaS/peering bypass.
10. Lập **canary rollout** từ PERMISSIVE sang STRICT có failure-mode tests.
11. Xây **SIEM correlation** nối Pod UID, verified peer identity, CNI flow, proxy request và app audit.
12. Soạn **incident runbook** khi một unmeshed Pod ở namespace app xử lý request trái quyền.
13. Phân tích ambient L4 data plane và các trường hợp cần L7 waypoint.
14. Đưa ra ít nhất **10 negative tests** bảo đảm không mở đường tắt với direct Pod IP hoặc external routes.
15. Ghi **owner, approved exceptions, expiry và rollback** cho mỗi network/mesh policy.

**Tiêu chí đạt:** mỗi security invariant có một enforcement point thật, không chỉ một cấu hình trên control plane; destination và app không chấp nhận principal trái quyền; logs đủ để phân biệt bypass với collector failure; dữ liệu nhạy cảm được bảo vệ khi một proxy không sẵn sàng.

### 21.2. Câu hỏi tự kiểm tra

**Câu 1.** Bypass sidecar proxy là gì?

*Gợi ý:* Một luồng đáng lẽ được proxy kiểm soát đi đường khác và không chịu đúng kiểm soát đó; cần xác minh flow và các lớp chặn còn lại.

**Câu 2.** Sidecar container đang Running có chứng minh mọi application socket đã được capture?

*Gợi ý:* Không. Cần listeners, capture scope, routing và actual flow tests.

**Câu 3.** Namespace có injection label có chứng minh Pods đã tạo từ hôm trước đều có sidecar?

*Gợi ý:* Không. Admission thường chỉ mutate khi tạo Pod; cần kiểm tra/recreate theo quy trình.

**Câu 4.** Source proxy bị bypass có đồng nghĩa destination app chắc chắn nhận traffic?

*Gợi ý:* Không. Destination sidecar STRICT, NetworkPolicy hoặc application authentication có thể deny.

**Câu 5.** Vì sao HTTP 200 không tự chứng minh mTLS?

*Gợi ý:* App có thể trả 200 trên direct/plaintext path; cần verified peer identity và TLS evidence tại đúng endpoints.

**Câu 6.** Khác nhau giữa proxy bypass và proxy fail closed là gì?

*Gợi ý:* Bypass là tránh kiểm soát mà vẫn có đường xử lý; fail closed ngăn connection khi bảo vệ không hoạt động.

**Câu 7.** Một request không có proxy log có phải bypass?

*Gợi ý:* Không nhất thiết; collector, sampling, wrong time window, CNI deny hoặc ambient mode có thể giải thích.

**Câu 8.** Sidecar mTLS xác thực danh tính user Alice hay workload proxy?

*Gợi ý:* Chủ yếu xác thực TLS workload peer theo certificate/trust domain; user authorization là lớp khác.

**Câu 9.** STRICT mTLS trên sidecar đích có bảo vệ một port không bị traffic interception không?

*Gợi ý:* Không thể mặc định; cần test scope và app/network controls cho exempt port.

**Câu 10.** PERMISSIVE nguy hiểm ở đâu trong migration kéo dài?

*Gợi ý:* Một số plaintext/non-mesh callers có thể tiếp tục được nhận nếu chính sách còn cho phép.

**Câu 11.** Vì sao localhost giữa containers cùng Pod không phải security boundary mạnh?

*Gợi ý:* Các containers chia sẻ network namespace; network policy Pod-level không tách loopback giữa chúng.

**Câu 12.** hostNetwork có được bảo vệ như Pod CNI thông thường không?

*Gợi ý:* Không mặc định; Pod dùng host networking và cần controls riêng theo CNI/host security.

**Câu 13.** Secondary interface có thể ảnh hưởng sidecar thế nào?

*Gợi ý:* Traffic đi net1 có thể nằm ngoài phạm vi capture trên primary interface/route.

**Câu 14.** Một UDP/QUIC request có luôn được sidecar mesh mTLS bảo vệ không?

*Gợi ý:* Tùy hỗ trợ protocol/dataplane; phải kiểm tra, không suy từ HTTP/TCP policy.

**Câu 15.** Vì sao Gateway WAF không bảo vệ mọi direct Pod IP flow?

*Gợi ý:* Chỉ những requests thật sự đi qua Gateway mới chịu chính sách WAF ở Gateway; backend cần network/app controls.

**Câu 16.** Nếu Orders API có AuthorizationPolicy, còn cần API-level authorization không?

*Gợi ý:* Có. Mesh service identity không tự xác định quyền user/tenant/object.

**Câu 17.** Proxy đi qua opaque TLS TCP có kiểm tra được HTTP path không?

*Gợi ý:* Không nếu không giải mã/nhận diện được HTTP; phải đặt L7 policy ở endpoint có HTTP visibility.

**Câu 18.** Khi frontend sidecar không Ready, làm gì để ngăn silent plaintext fallback?

*Gợi ý:* Readiness/capture coordination, CNI deny, destination mTLS/app auth và fail-closed tests.

**Câu 19.** Mesh control plane down có bắt buộc mọi data plane requests đều fail ngay không?

*Gợi ý:* Không. Proxy có thể dùng cached config/certs theo sản phẩm và thời hạn; cần kiểm chứng.

**Câu 20.** Một Policy ALLOW tại destination có bắt buộc mọi Pod khác trong cluster cũng dùng policy đó?

*Gợi ý:* Không. Nó áp với những workloads/enforcement points được chọn và traffic thật đi qua.

**Câu 21.** Vì sao CNI NetworkPolicy là defense-in-depth cho mesh?

*Gợi ý:* Nó có thể deny untrusted network path trước app/proxy, kể cả khi mesh capture gap—nếu CNI thực thi đúng.

**Câu 22.** Labels trong NetworkPolicy có phải cryptographic workload identity không?

*Gợi ý:* Không. Giới hạn quyền sửa labels qua admission/RBAC và dùng mTLS/service identity.

**Câu 23.** Egress gateway không có log nhưng SaaS nhận traffic: hai giả thuyết nào quan trọng?

*Gợi ý:* Direct NAT/alternate route bypass hoặc exporter/telemetry gap.

**Câu 24.** Có thể suy IP NAT là danh tính một Pod đơn lẻ không?

*Gợi ý:* Không. Nhiều Pods có thể dùng cùng IP; cần NAT/session mapping, Pod UID và event time.

**Câu 25.** Ambient mode không có sidecar có tự động là một finding nghiêm trọng?

*Gợi ý:* Không nếu workload được enroll vào node-level secure transport và policy được thực thi theo thiết kế.

**Câu 26.** Trong ambient, L4 mTLS có tự áp HTTP method/path policy không?

*Gợi ý:* Không; L7 authorization có thể cần waypoint/gateway hoặc app enforcement.

**Câu 27.** Tại sao không dùng một default-deny policy trên production rồi sửa lỗi sau?

*Gợi ý:* Nó có thể chặn DNS, app dependencies, telemetry/control plane; cần allowlist/canary/rollback.

**Câu 28.** Khi sidecar crash mà requests timeout, có được kết luận bypass thành công không?

*Gợi ý:* Không. Đó có thể là fail closed; cần xác minh actual path và app requests.

**Câu 29.** Cách nào chứng minh direct Pod IP path không vượt Gateway authorization?

*Gợi ý:* Negative test trong sandbox từ nguồn không được phép, so CNI/proxy/app evidence và backend authorization.

**Câu 30.** Một health port được exempt khỏi mesh capture có nhất thiết là vulnerability không?

*Gợi ý:* Không nếu phạm vi/nguồn/response an toàn và có controls thay thế; phải có exception inventory.

**Câu 31.** Pod IP tái sử dụng làm điều tra bypass sai thế nào?

*Gợi ý:* Flow cũ bị gán nhầm Pod mới; cần UID/IPAM allocation windows và timestamp.

**Câu 32.** Khi mTLS handshake lỗi do CA rotation, có nên chuyển sang PERMISSIVE ngay không?

*Gợi ý:* Không mặc định. Sửa trust/cert/rollout; nếu ngoại lệ khẩn, cần approval, bù kiểm soát và thời hạn.

**Câu 33.** Khi app trả HTTP 403 nhưng proxy mTLS hợp lệ, lỗi thuộc layer nào?

*Gợi ý:* Có thể application authorization đúng design, không phải network/TLS failure.

**Câu 34.** Vì sao cần quan sát cả source lẫn destination proxy?

*Gợi ý:* Bypass nguồn không tự kéo theo bypass đích; mỗi endpoint thực thi các kiểm soát khác nhau.

**Câu 35.** Khi sidecar log metrics giảm, app metrics tăng, cần điều tra gì?

*Gợi ý:* Metric semantics/time windows, health probes, collector, policy mode, alternate routes và CNI flow.

**Câu 36.** NetworkPolicy có tự mã hóa Pod-to-Pod traffic không?

*Gợi ý:* Không. Nó giới hạn reachability; TLS/mTLS hoặc data-plane encryption bảo vệ nội dung.

**Câu 37.** mTLS certificate có cho phép một backend tự bỏ kiểm tra tenant/user không?

*Gợi ý:* Không. Chứng chỉ workload không thay business authorization.

**Câu 38.** Vì sao cần audit annotation exclusions?

*Gợi ý:* Một exemption có thể thay đổi interception scope và tạo direct path không được mesh kiểm soát.

**Câu 39.** Khi rollout từ sidecar sang ambient, cần so sánh những gì ngoài HTTP 200/latency?

*Gợi ý:* L4 mTLS identity, L7 waypoint, policy coverage, direct paths, gateway/egress và telemetry.

**Câu 40.** Điều kiện tối thiểu nào giúp đóng một finding confirmed bypass?

*Gợi ý:* Root cause đã sửa, negative test chặn nguồn trái quyền, traffic đi đúng enforcement point, application auth đúng, telemetry và owner/change record đầy đủ.

### 21.3. Bài tập phân tích log

Tình huống giả lập:

~~~text
09:00Z: Kubernetes audit: orders-v1 Pod created WITHOUT sidecar
09:05Z: Namespace injection enabled; existing orders-v1 unchanged
09:10Z: orders-v2 Pod created WITH sidecar; proxy Ready
09:15Z: Service endpoints: orders-v1 + orders-v2
09:20Z: CNI: untrusted -> orders-v1 TCP/8080, verdict ALLOW
09:20Z: App orders-v1: GET /admin HTTP 200, authn field empty
09:20Z: Destination proxy: no corresponding request on orders-v1
09:21Z: CNI: untrusted -> orders-v2 TCP/8080, verdict DENY
09:22Z: Proxy log exporter orders-v2: healthy
~~~

**Câu hỏi:**

1. Thông tin nào chứng minh **mixed injection rollout**?
2. Có thể nói chắc untrusted request vào orders-v1 đã bỏ mesh enforcement mong đợi không? Cần thêm gì?
3. Vì sao HTTP 200 với authn field empty là dấu hiệu quan trọng nhưng chưa đủ chứng minh data breach?
4. Negative test orders-v2 bị CNI deny có nói gì về effective mesh mTLS tại orders-v2?
5. Những controls nào phải thêm để không phụ thuộc chỉ vào sidecar?
6. Tại sao bật namespace injection lúc 09:05 không tự sửa orders-v1?
7. Làm sao sửa bằng controlled rollout mà không phá service SLO?
8. Làm thế nào xác minh sau remediation rằng cả Service và direct Pod IP path đều deny untrusted?

**Đáp án định hướng:**

- Hai Pods có cấu hình injection khác nhau, cùng được Service chọn; orders-v1 có khả năng không được mesh bảo vệ như orders-v2.
- CNI ALLOW + app HTTP 200 + không có proxy tại orders-v1 là **evidence mạnh về missing destination-side mesh enforcement**, nhưng cần xác minh chính xác source, request correlation, app endpoint và auth policy expected, đặc biệt nếu exporter có gaps.
- HTTP 200 ở /admin không tự chứng minh dữ liệu nhạy cảm đã bị lộ; cần **application action/audit, response classification và data owner review**.
- CNI DENY tại orders-v2 chứng minh **network-layer deny**, không chứng minh destination proxy STRICT/AuthZ vì request có thể chưa tới proxy.
- Remediate bằng **inventory/redeploy correct mesh mode, admission deny unmeshed workloads, NetworkPolicy, app authorization và negative tests**; giữ healthy backend capacity/canary và rollback trong security baseline.

## 22. Tổng kết

- **Sidecar proxy chỉ bảo vệ lưu lượng thực sự đi qua nó**. Có proxy container, mesh policy trên control plane hoặc một Service DNS không tự chứng minh **mTLS/authorization đã được áp**.
- **Bypass thực sự khác fail-closed và telemetry gap**. Phải chứng minh đường nào tránh điểm enforcement, request có tới app không và controls còn lại có chặn hay không.
- **Injection không đồng đều, port/IP/interface exclusions, localhost, hostNetwork, secondary CNI, UDP/QUIC và startup/shutdown races** có thể tạo các phạm vi không được proxy xử lý hoặc gây sự cố availability.
- **mTLS STRICT** bảo vệ đúng endpoint/capture scope của nó, không phải một network firewall toàn cluster. **PERMISSIVE** hữu ích cho migration nhưng cần kiểm tra plaintext traffic và thu hẹp ngoại lệ.
- **Mesh workload identity khác user/resource authorization**. Backend phải kiểm tra principal, tenant, action và dữ liệu ngay cả khi mTLS đã xác minh frontend service.
- **L7 policy yêu cầu HTTP visibility** ở proxy/waypoint/app; opaque TCP/TLS forwarding không mặc nhiên kiểm tra HTTP path hoặc JWT.
- **NetworkPolicy, cloud firewall, Pod Security, validating admission/RBAC và application TLS/authorization** cung cấp defense-in-depth khi proxy thiếu hoặc traffic đi đường khác.
- **Egress gateway không tự buộc mọi outbound path qua nó**. Phải kiểm tra direct NAT, VPC peering, private endpoints, IPv6 và cross-cluster traffic, đặc biệt khi dữ liệu nhạy cảm có thể di chuyển qua các đường private.
- **Ambient/sidecarless là một kiến trúc khác**, không phải finding chỉ vì không có sidecar; cần xác minh L4 mTLS và L7 waypoint/authorization riêng.
- **Telemetry phải tương quan nhiều lớp**: Pod UID/injection state, proxy/CNI/VPC flow, application audit, DNS và collector health theo event time. Không dùng sự vắng mặt của proxy log làm chứng cứ duy nhất.
- **Đánh giá an toàn bằng security invariants và negative tests**: authorized flow thành công với peer identity đúng; unauthorized caller không tới được sensitive action qua Service, Pod IP hoặc alternate path.
- Khi gặp nghi bypass, quy trình đúng là **kiểm kê phạm vi, bảo toàn evidence, containment chính xác, sửa root cause, kiểm thử lại và rollout/rollback không hạ cấp mTLS/AuthZ**.
