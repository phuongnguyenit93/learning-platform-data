# Bảo vệ Docker socket và control plane trong mạng container

Một doanh nghiệp chạy ứng dụng trong container và triển khai công cụ quan sát hạ tầng bằng cách mount `/var/run/docker.sock` vào container giám sát. Công cụ cần đọc danh sách container, nhưng ngay sau đó một lỗ hổng trong dashboard giám sát khiến người lạ có thể điều khiển tiến trình bên trong. Liệu kẻ đó có thể tác động tới các container khác, máy chủ Docker hay thậm chí hệ thống điều phối? Câu trả lời phụ thuộc **quyền mà socket thực sự trao cho tiến trình**, không phụ thuộc riêng việc container có chạy bằng user non-root hoặc mount được đánh dấu `:ro`.

Docker socket và các giao diện quản trị container là **mặt phẳng điều khiển (control plane)**. Chúng cho phép tạo, xóa, thay đổi, kiểm tra tài nguyên chạy container; vì thế tác động tiềm tàng lớn hơn một cổng HTTP của ứng dụng bình thường. Bảo vệ chúng đòi hỏi kết hợp **phân quyền host, giới hạn bề mặt kết nối, xác thực quản trị, kiểm soát workload, audit và ứng cứu sự cố**.

Bài thuộc chương **Bảo mật mạng container** của module **SECURITY_NETWORK_SECURITY**. Kiến thức liên quan tới phân đoạn mạng, firewall, TLS, VPN/ZTNA, NAC, mô hình hóa đe dọa, IDS/IPS, cloud IAM, DNS, kiểm soát luồng east–west và xây dựng kiến trúc mạng an toàn.

**Nguyên tắc trọng tâm:** ai có thể ra lệnh cho daemon/container orchestrator thường có thể gây ảnh hưởng sâu đến workload và host. **Không được coi Docker socket là “một file log để đọc”**, cũng không coi việc che API server khỏi Internet là đủ bảo vệ control plane.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Giải thích đường điều khiển từ **Docker CLI → Docker Engine API → daemon → container/runtime**, phân biệt nó với data plane ứng dụng.
2. Phân tích vì sao quyền truy cập `/var/run/docker.sock` hoặc nhóm `docker` trong cài đặt Docker Engine Linux rootful thường **tương đương một quyền quản trị host rất mạnh**.
3. Phân biệt **Unix socket, remote TCP API, TLS/mTLS, SSH context, rootless daemon và user namespace remapping**; hiểu giới hạn của từng biện pháp.
4. Nhận biết rủi ro khi mount Docker socket vào container, công cụ CI/CD, dashboard hoặc Docker socket proxy.
5. Giải thích các thành phần **Kubernetes API server, etcd, admission, RBAC, controller, scheduler, kubelet và CRI runtime socket**; không đánh đồng chúng với Docker socket.
6. Thiết kế ranh giới mạng và quyền cho Docker host/Kubernetes control plane, bảo vệ chứng chỉ, service accounts, secrets và logs.
7. Thực hiện kiểm tra cấu hình bằng lệnh **chỉ đọc**, lập ma trận kiểm thử phòng thủ và quy trình triển khai có rollback.

## 2. Phân biệt data plane và control plane

**Data plane** vận chuyển request/response của ứng dụng và traffic giữa các workload. **Control plane** nhận quyết định quản trị, lập lịch, cập nhật trạng thái, phân phối cấu hình và điều phối tài nguyên.

| Thành phần | Ví dụ nhiệm vụ | Nếu bị lạm dụng |
|---|---|---|
| Ứng dụng/container data plane | API, database client, message broker, traffic nội bộ | Lộ dữ liệu hoặc lạm dụng quyền ứng dụng |
| Docker Engine API / daemon | Tạo/chạy/dừng container, quản lý volumes, networks, images | Có thể ảnh hưởng tới nhiều container, dữ liệu và host |
| Container runtime / CRI | Quản lý vòng đời container/pod theo yêu cầu của orchestrator | Có thể thay đổi hoặc truy cập workload trên node |
| Kubernetes API server | Nhận/yêu cầu thay đổi API objects, xác thực và ủy quyền | Có thể đổi workloads, secrets, RBAC và toàn cluster tùy quyền |
| Controller manager / scheduler | Đối chiếu desired state, lập lịch workload | Sai quyết định điều phối và phân phối tài nguyên |
| Kubelet trên worker node | Quản lý pod/node cục bộ qua API server/runtime | Có thể ảnh hưởng workloads trên node |
| etcd | Lưu trạng thái cluster và nhiều dữ liệu nhạy cảm | Lộ hoặc thay đổi thông tin điều khiển cluster |
| CI/CD, GitOps controller | Tự động deploy, cập nhật images/manifests | Quyền triển khai có thể lan rộng nếu thiếu least privilege |

### 2.1. Docker Engine và Kubernetes không có cùng control plane

Một Docker host có **Docker daemon** và Docker Engine API. Kubernetes có **Kubernetes API server và các thành phần điều khiển riêng**; kubelet thường giao tiếp với runtime qua **Container Runtime Interface (CRI)**. Nhiều cluster hiện đại dùng `containerd` hoặc `CRI-O` thay vì Docker Engine trực tiếp.

Không được suy ra “node chạy container” nghĩa là luôn có `/var/run/docker.sock`, hoặc “chặn Docker socket” là đã bảo vệ toàn bộ Kubernetes. Nếu runtime là containerd, socket như `/run/containerd/containerd.sock` cũng là giao diện đặc quyền cần quản lý theo threat model và cơ chế runtime.

### 2.2. Sơ đồ các ranh giới điều khiển

~~~mermaid
flowchart TD
    subgraph CLIENT["Ranh giới 1: Identity / management access"]
      OP["Operator / automation"]
      CICD["CI/CD / GitOps"]
    end
    subgraph DOCKER["Docker host riêng lẻ"]
      API["Docker Engine API: Unix socket hoặc remote endpoint"]
      DAEMON["Docker daemon"]
      CONT["Containers / volumes / networks"]
    end
    subgraph K8S["Kubernetes cluster"]
      KAPI["Kubernetes API server"]
      ADMISSION["AuthN, AuthZ, admission"]
      STORE[("etcd")]
      CTRL["Controllers / scheduler"]
      KUBELET["Kubelet trên node"]
      CRI["CRI runtime: containerd / CRI-O"]
      POD["Pods / network / volumes"]
    end
    OP --> API
    API --> DAEMON --> CONT
    OP --> KAPI
    CICD --> KAPI
    KAPI --> ADMISSION
    KAPI --> STORE
    KAPI --> CTRL
    KAPI --> KUBELET --> CRI --> POD
~~~

Hình là **mô hình logic**, không biểu diễn chính xác toàn bộ giao thức và luồng nội bộ của từng sản phẩm. Đặc biệt, Kubernetes không cần Docker daemon ở node khi CRI sử dụng một runtime khác.

## 3. Docker socket là gì và vì sao nhạy cảm?

Trên nhiều cài đặt Docker Engine Linux rootful, Docker daemon lắng nghe qua Unix domain socket `/var/run/docker.sock`. Docker CLI dùng socket đó để gửi **Docker Engine API** request; daemon sẽ thực thi các thao tác có quyền tương ứng với chính nó.

~~~text
Docker CLI / SDK / automation
        |
        |  HTTP API qua Unix domain socket
        v
/var/run/docker.sock
        |
        v
Docker daemon (dockerd)
        |
        +-- Quản lý containers
        +-- Quản lý volumes / bind mounts
        +-- Quản lý images và networks
        +-- Tương tác với host/runtime
~~~

Socket không chỉ trả về danh sách trạng thái. API còn có những thao tác **có tác dụng thay đổi** như tạo container với cấu hình nhạy cảm, mount đường dẫn host, quản lý volumes/networks và điều khiển vòng đời workload. Khi daemon chạy bằng quyền mạnh trên host, người điều khiển API có thể có khả năng vượt khỏi phạm vi của một container ứng dụng bình thường.

### 3.1. Tại sao nhóm `docker` thường được coi là đặc quyền cao?

Ở Docker Engine Linux rootful, quyền socket thường được phân cho `root` và nhóm `docker` hoặc một nhóm được cấu hình. Người được phép kết nối tới socket có thể yêu cầu daemon thực thi nhiều thao tác quản trị.

**Hệ quả:** với cấu hình rootful phổ biến, **thêm một user vào nhóm `docker` gần tương đương trao quyền root ở góc độ khả năng kiểm soát host**. Việc user đó chạy lệnh Docker CLI bằng tài khoản không phải root **không** làm các thao tác daemon trở thành an toàn.

Không nên:

- Tự động thêm mọi developer, CI agent hoặc service account vào `docker` group.
- Đặt quyền socket thành `0666` để sửa nhanh lỗi `permission denied`.
- Đặt socket trong shared folder cho nhiều ứng dụng không đáng tin.
- Dùng quyền truy cập socket làm bằng chứng “đã chỉ cấp read-only Docker monitoring”.

### 3.2. Socket Unix không phải API public, nhưng vẫn là một điểm vào

Unix socket không tự có địa chỉ IP để client trên Internet gọi trực tiếp. Tuy nhiên:

- Một container **bind-mount socket** có thể gửi API request tới daemon.
- Một tiến trình local bị chiếm quyền có thể dùng socket nếu OS permissions/ACL cho phép.
- TCP proxy hoặc một dịch vụ gateway đặt trước socket có thể **biến khả năng quản trị local thành khả năng truy cập qua mạng**.
- Quyền filesystem, mount namespace, SELinux/AppArmor/LSM và hardening host có thể tác động tới việc truy cập; phải kiểm chứng hiệu lực cụ thể.

**Có mount socket vào container** thường quan trọng hơn việc socket “nằm ở path nào”.

## 4. Sai lầm: mount Docker socket với `:ro` là đủ

Ví dụ một cấu hình **không an toàn**:

~~~yaml
# ANTI-PATTERN — CHỈ ĐỌC, KHÔNG TRIỂN KHAI.
services:
  dashboard:
    image: registry.example.test/monitoring/dashboard:demo
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
~~~

**Lý do:** hậu tố `:ro` chủ yếu liên quan tới cách mount filesystem trong container. Socket là **endpoint IPC**; nếu tiến trình vẫn được phép mở kết nối và gửi Docker Engine API requests thì nó có thể yêu cầu các thao tác **ghi/thay đổi** qua API. Nó **không biến daemon thành API read-only**.

Do đó câu “dashboard chỉ cần đọc nên gắn Docker socket `:ro`” thường là một nhận định sai về security boundary.

### 4.1. Khi container bị xâm nhập, blast radius có thể lớn tới đâu?

~~~mermaid
flowchart TD
    A["Dashboard / agent có lỗ hổng"] --> B["Attacker điều khiển tiến trình trong container"]
    B --> C{"Container nhìn thấy Docker socket và có quyền kết nối?"}
    C -->|"Không"| D["Phạm vi ảnh hưởng tiếp tục phụ thuộc quyền workload, network, volumes"]
    C -->|"Có"| E["Có thể yêu cầu Docker daemon thực hiện các thao tác được API cho phép"]
    E --> F["Nguy cơ ảnh hưởng containers khác, volumes, networks và host"]
    F --> G["Tác động tới dữ liệu, thông tin xác thực và khả năng phục vụ"]
~~~

Đây là **chuỗi rủi ro khái niệm**, không phải hướng dẫn khai thác. Nó cho thấy một thành phần có quyền API quản trị có thể biến một lỗi ứng dụng thành **sự cố hạ tầng**.

### 4.2. “Chỉ có root trong container mới nguy hiểm” có đúng không?

Không. Một tiến trình không phải root trong container **vẫn có thể** truy cập socket khi OS permissions, group IDs/ACL hoặc cơ chế mount cho phép. Quyền của Docker daemon có thể khác rất xa quyền UID của tiến trình gọi.

Biện pháp `USER non-root` có ích trong hardening workload, nhưng **không thay** việc cắt đường truy cập Docker Engine API.

## 5. Quản lý Docker daemon local: nguyên tắc nền tảng

| Biện pháp | Điều nó giảm thiểu | Giới hạn |
|---|---|---|
| Không mount Docker socket vào ứng dụng | Giảm đường truy cập daemon từ workload | Ứng dụng có thể còn kênh đặc quyền khác |
| Giới hạn root và nhóm được phép dùng socket | Giảm số principal có quyền điều khiển Docker | Nhóm được phép vẫn có quyền lớn |
| Hardening host, SSH, OS patches | Giảm đường chiếm quyền host trực tiếp | Không thay kiểm soát Engine API |
| Rootless Docker khi phù hợp | Giảm quyền hệ thống của daemon và runtime dưới user riêng | Chiếm quyền user đó vẫn gây ảnh hưởng lớn; có giới hạn tính năng |
| User namespace remapping | Ánh xạ UID/GID container sang host UID/GID khác | Không loại bỏ quyền mạnh của daemon rootful hoặc socket |
| Không dùng `--privileged`/host namespaces nếu không cần | Thu hẹp khả năng của container | Một socket có toàn quyền vẫn là vấn đề riêng |
| SELinux/AppArmor/seccomp/capabilities | Giảm quyền workload trong nhiều tình huống | Không đảm bảo ngăn Docker API quản trị đã được cấp |
| Host firewall/mgmt segmentation | Giảm network reachability tới remote daemon | Không bảo vệ local socket nếu bị mount |

### 5.1. Rootful, rootless và user namespace remapping

**Docker Engine rootful**: daemon thường có quyền hệ thống cao, cần đối xử với API như một giao diện quản trị host.

**Rootless mode**: daemon và container runtime hoạt động dưới một tài khoản người dùng không đặc quyền với các cơ chế namespace hỗ trợ. Nó có thể giảm **tác động tới host root**, nhưng không làm socket rootless trở thành an toàn với ứng dụng không tin cậy. Ai điều khiển daemon rootless vẫn có thể tác động tới containers, images, volumes và dữ liệu thuộc phạm vi tài khoản đó.

**`userns-remap`**: ánh xạ người dùng bên trong container sang UID/GID khác ở host. Nó giảm một số rủi ro giữa container và host nhưng **khác rootless daemon**: Docker daemon vẫn có thể là rootful.

Khi đánh giá, phải biết chế độ được bật **thật sự**, các exceptions, volume permissions, network driver support và rủi ro tương thích ứng dụng.

### 5.2. Docker Desktop khác Docker Engine Linux server

Trên macOS/Windows, Docker Desktop thường dùng VM/lớp tích hợp riêng để cung cấp Docker Engine và kết nối với host. Đường socket và blast radius có thể khác với Docker Engine Linux trực tiếp.

Không áp một cách máy móc mô hình `/var/run/docker.sock` ở host Linux cho mọi platform, nhưng vẫn cần coi **quyền điều khiển Engine API** là đặc quyền cao trong môi trường tương ứng.

## 6. Remote Docker API: bảo vệ kênh quản trị

Docker Engine có thể được cấu hình lắng nghe qua mạng thay vì chỉ Unix socket. Những cổng TCP **2375/2376** thường xuất hiện trong tài liệu/triển khai (2375 thường gắn với endpoint không TLS, 2376 thường gắn với TLS), nhưng **số cổng không tự chứng minh có mã hóa hoặc xác thực**.

### 6.1. Rủi ro của unauthenticated TCP API

Nếu Docker Engine API nghe trên địa chỉ mạng mà không có cơ chế xác thực/ủy quyền phù hợp, principal có reachability có thể điều khiển daemon ở phạm vi API hỗ trợ. Đây là **rủi ro nghiêm trọng**, kể cả khi port chỉ mở trong VPC/VPN; một workload nội bộ bị xâm nhập vẫn có thể tiếp cận.

Không:

- Public Docker Engine API trên `0.0.0.0` hoặc Internet như một endpoint quản trị thông thường.
- Coi “đã ở sau VPN” là thay thế cho authentication của Engine API.
- Bật remote TCP không TLS chỉ để dashboard/CI/CD hoạt động dễ hơn.
- Đưa certificate private key, bearer token hoặc access credentials vào URL, container image hay log.

### 6.2. SSH context hoặc TLS/mTLS

Các phương án quản trị từ xa có thể bao gồm:

- **Docker context qua SSH**, tận dụng xác thực SSH, quản lý host keys, quản trị user và chặn quyền ở host.
- **Docker daemon qua TLS với client certificate authentication** khi cấu hình phù hợp, cộng với kiểm tra server certificate, vòng đời CA/certs và firewall.
- **Management gateway/bastion** có MFA, phê duyệt phiên, ghi audit và đường kết nối hạn chế.

Nhưng **TLS/mTLS xác nhận peer không tự tạo RBAC chi tiết theo từng Docker Engine API action**. Nếu mọi client certificate hợp lệ có thể gọi toàn bộ API, mTLS chỉ xác định ai có quyền rất lớn; vẫn cần thiết kế ít principal, kiểm soát endpoint và chủ sở hữu.

### 6.3. Trust boundary cho remote management

~~~mermaid
flowchart LR
    DEV["Operator được ủy quyền"] -->|"MFA / device compliance"| BASTION["Bastion / management zone"]
    BASTION -->|"SSH hoặc mTLS được quản lý"| DAEMON["Docker Engine API"]
    DAEMON --> WORK["Containers / volumes / networks"]
    APP["Ứng dụng public/guest"] -.->|"DENY tới Engine API"| DAEMON
    AUDIT["Identity + host audit"] -.-> BASTION
    AUDIT -.-> DAEMON
~~~

Mục tiêu là **giảm số đường tới daemon**, xác định principal thực, tránh exposed port và có bằng chứng về những thao tác quản trị. Nếu sử dụng proxy đặt trước socket, proxy trở thành một thành phần nhạy cảm phải được harden/audit độc lập.

## 7. Docker socket proxy và cách hiểu “read-only”

Một số hệ thống sử dụng **Docker socket proxy** để agent gọi một tập API đã cho phép thay vì truy cập toàn daemon. Hướng tiếp cận này **có thể giảm quyền** nếu được thiết kế cẩn thận, nhưng không được đánh giá bằng tên sản phẩm hoặc một checkbox.

Những điều phải xác minh:

1. Proxy có **allowlist endpoint + HTTP method** cụ thể hay chỉ chặn sơ sài theo prefix?
2. Các endpoint chỉ dùng GET có thực sự **không đổi trạng thái** và không lộ dữ liệu nhạy cảm trong bối cảnh deployment không?
3. Proxy có parse URL/method, encoding và HTTP semantics nhất quán không? Có đường bypass tới socket gốc không?
4. Agent/proxy có thể xem **container environment, command, mount path, network topology, logs hoặc image metadata** chứa thông tin nhạy cảm không?
5. Proxy được đặt trong network policy riêng, authenticated, audit và update như một critical component không?
6. Có cơ chế **revocation và deny-by-default** khi proxy hoặc backend lỗi không?

**API chỉ đọc không đồng nghĩa không nhạy cảm**: metadata về host, container, biến môi trường, image registry, đường mount hoặc application logs có thể giúp lộ secret hay cấu trúc mạng. Nếu một phần dữ liệu là bí mật, cần hạn chế **nội dung có thể đọc**, không chỉ chặn POST/DELETE.

### 7.1. Phương án thay socket mount vào workload

- Dùng **telemetry exporter/agent được quản trị** thu đúng chỉ số, ghi ra API quan sát ít quyền hoặc metrics sink.
- Dùng **host-level monitoring do operator kiểm soát**, tránh truyền Docker API socket vào dashboard public.
- Dùng hệ thống orchestration API có **RBAC và audit thực sự**, không tạo một proxy Docker API không có identity.
- Dùng hệ thống build tách riêng khỏi production host/daemon, có credential ngắn hạn và giới hạn mạng.
- Khi bắt buộc dùng socket, ghi rõ quyết định ngoại lệ, owner, threat model, blast radius, hardening và kế hoạch loại bỏ.

Không yêu cầu từng ứng dụng biết cấu trúc Docker daemon để tự giám sát các container khác nếu có thể lấy metrics từ lớp quan sát được hỗ trợ.

## 8. CI/CD, Docker-in-Docker và build containers

Pipeline có thể cần build/push images nhưng **không nhất thiết cần socket của Docker daemon production**.

| Mô hình | Nguy cơ thường gặp | Cách giảm rủi ro |
|---|---|---|
| CI agent mount Docker socket của host | Pipeline có thể điều khiển daemon host | Tách build runner, không dùng production daemon, hạn chế repo/job được phép |
| Docker-in-Docker (DinD) | Có thể cần privileges/network/volumes rộng tùy cấu hình | Đánh giá rootless/isolated runner, lifecycle ngắn, quota và network |
| Remote builder | Client gửi build tới builder khác | mTLS/SSH, identity, network policy, registry controls |
| Daemonless/rootless build tooling | Giảm phụ thuộc socket Docker rootful trong một số môi trường | Vẫn phải bảo vệ runner filesystem, registry credential và supply chain |
| Shared multi-tenant runner | Job của nhiều nhóm dùng cùng host/daemon | Isolation cứng, không cho tenant dùng socket chung, ephemeral runners |

**Build script từ repository không tin cậy** có thể chạy với quyền của CI agent. Nếu agent có quyền Docker daemon host, việc “chỉ được build image” có thể trở thành quyền điều khiển nhiều workload. Phải review **pull request từ fork, token scope, secrets injection, cache/shared volumes và registry pushes**.

Một pipeline phát hành image không nên tự có quyền `cluster-admin` hoặc quyền tạo Pod đặc quyền nếu nhiệm vụ chỉ là push image và yêu cầu deploy được duyệt.

## 9. Kubernetes control plane: ngoài Docker socket còn gì?

Trong Kubernetes, thành phần trung tâm là **kube-apiserver**. Yêu cầu API thường trải qua:

1. **Authentication:** principal là ai (client cert, token, OIDC hoặc cơ chế khác)?
2. **Authorization:** principal có quyền với verb/resource/namespace đó không (ví dụ RBAC, webhook, node authorization theo cấu hình)?
3. **Admission:** các chính sách validate/mutate được áp sau khi đã authorize theo luồng API phù hợp.
4. **Persistence:** desired state được lưu vào etcd và controller/node sẽ thực hiện theo kiến trúc Kubernetes.

~~~mermaid
sequenceDiagram
    participant O as Operator / workload client
    participant API as kube-apiserver
    participant AU as Authentication / Authorization
    participant AD as Admission controls
    participant DB as etcd
    participant NODE as Kubelet / runtime
    O->>API: Kubernetes API request
    API->>AU: Xác thực và kiểm tra quyền
    AU-->>API: Allow hoặc Deny
    opt Request được cho phép và cần admission
        API->>AD: Mutating/validating admission theo quy tắc
        AD-->>API: Allowed/Denied/modified object
    end
    API->>DB: Lưu/đọc trạng thái theo thao tác
    DB-->>API: Kết quả
    API-->>O: API response
    Note over NODE: Controller và kubelet quan sát desired state, thực thi sau đó
~~~

Sơ đồ rút gọn; không phải mọi request đều có admission webhooks, và quá trình điều khiển reconciliation không phải một RPC trực tiếp từ client tới node. **Kubernetes RBAC chỉ kiểm soát hành vi qua API server**, không tự ngăn người có quyền trực tiếp vào host/runtime socket.

### 9.1. Kubernetes API server là endpoint đặc quyền

- Hạn chế network reachability tới API server theo môi trường quản trị (private endpoint, authorized networks, VPN/ZTNA hoặc firewall phù hợp).
- Xác thực client identity và dùng MFA/conditional access qua IdP/bastion khi thiết kế hỗ trợ.
- Không dùng tài khoản/credential admin chung cho toàn bộ automation.
- Có audit policy, lưu nhật ký truy cập/chính sách phù hợp và giám sát các hành vi nhạy cảm.
- Kiểm soát certificate, OIDC/JWKS, encryption và rotation của thành phần điều khiển.
- Tách đường **operator management** khỏi đường **workload-to-API** theo threat model; không cho public web container quyền truy cập admin endpoint.

Một API server chỉ reachable trong VPC vẫn có thể bị lạm dụng từ pod/VM nội bộ có credential hợp lệ nhưng bị đánh cắp. **Private control-plane endpoint là một lớp network boundary, không thay authentication/authorization**.

## 10. RBAC: một quyền nhỏ có thể có tác động lớn

RBAC liên kết **subjects** (user, group, ServiceAccount) với **Role/ClusterRole** và các **verbs** trên resources. Namespace scoping rất quan trọng nhưng không tự bảo đảm quyền là thấp nếu resource/verb có khả năng leo thang.

| Quyền/trường hợp | Tác động cần xem xét | Giảm rủi ro |
|---|---|---|
| `get/list/watch secrets` | Có thể đọc dữ liệu chứng thực nhạy cảm | Chỉ cấp cho thành phần bắt buộc, hạn chế namespace |
| `create/update pods` | Có thể chạy workload trong namespace, dùng SA và capabilities được phép | Pod Security Admission/policy, SA controls, quota và RBAC |
| `pods/exec` và `pods/attach` | Có thể thao tác phiên chạy của container | Cấp cực hẹp, audit phiên và approval |
| `create serviceaccounts/token` | Có thể xin token cho service account theo scope quyền | Xem như quyền nhạy cảm, rà soát TokenRequest |
| `bind`, `escalate` hoặc sửa RBAC | Có thể tăng quyền nếu không kiểm soát | Giới hạn quyền và kiểm tra role bindings |
| `impersonate` | Có thể thực hiện thao tác dưới identity khác nếu được cấp | Chỉ dùng cho automation tin cậy và audit |
| Sửa admission webhooks/policies | Có thể làm yếu kiểm soát tạo workload | Quyền control-plane rất hẹp, review hai người |
| `cluster-admin` | Quyền cực rộng trên cluster | Không cấp làm mặc định cho developer/CI |

Một principal có quyền **tạo Pod** trong namespace có ServiceAccount nhiều quyền, hoặc được phép tạo Pod với host access trong cluster không có admission phù hợp, có thể gián tiếp tăng khả năng thao tác. **RBAC phải được đánh giá cùng Pod Security Admission, ServiceAccount permissions và điều kiện runtime**, không chỉ xem tên Role.

### 10.1. Namespace không tự là một ranh giới bảo mật hoàn chỉnh

Namespace hỗ trợ phân nhóm tài nguyên và áp RBAC, quota, policies; nhưng:

- Một `ClusterRoleBinding` rộng có thể vượt phạm vi namespace.
- Host-level containers, volumes hoặc sockets có thể mở đường vượt isolation nếu policy cho phép.
- CNI/NetworkPolicy không mặc định cách ly mọi traffic giữa namespace.
- Đối tượng cluster-scoped vẫn ảnh hưởng tới nhiều namespace.
- Dữ liệu tenant cần **authorization riêng ở ứng dụng**.

Trong môi trường multi-tenant có đối thủ không tin cậy, một cluster dùng namespace riêng **không tự tương đương** các cluster/host cô lập hoàn toàn.

## 11. Admission controls và Pod Security Admission

Kubernetes hỗ trợ **Pod Security Admission (PSA)** áp các mức chính sách như **Privileged, Baseline, Restricted** trong phạm vi namespace, với các mode **enforce, audit, warn**. Khả năng bảo vệ thực tế phụ thuộc version, exceptions và cách tổ chức bật cấu hình.

Một số cấu hình cần đánh giá khi chặn workload rủi ro:

- `privileged: true` và `allowPrivilegeEscalation`.
- `hostNetwork`, `hostPID`, `hostIPC` và host namespaces khác.
- `hostPath` mount, đặc biệt các sockets/runtime paths.
- Capabilities, seccomp profile và quyền chạy root.
- Nhu cầu thiết bị đặc thù, CSI/storage drivers, DaemonSets hoặc system workloads cần exceptions có quản trị.

**Restricted** thường là điểm xuất phát cho workload ít đặc quyền, nhưng không thể áp mù với tất cả hệ thống nếu sẽ phá CNI/CSI, node agents hoặc ứng dụng di sản. Dùng **audit/warn trước**, phân loại ngoại lệ rồi chuyển enforce có canary.

### 11.1. Admission không thay kiểm soát host

Nếu một attacker đã có quyền Docker/containerd runtime socket **trực tiếp trên node**, yêu cầu có thể **không đi qua kube-apiserver** và do đó **không chịu RBAC/admission của API server**. Đây là lý do bảo vệ runtime socket và quyền node phải được xem là một lớp độc lập.

Ngược lại, bảo vệ socket node cũng không thay được quyền Kubernetes API như `create clusterrolebindings`, `update validatingwebhookconfigurations` hoặc đọc secrets.

### 11.2. Admission webhook cũng là control-plane dependency

Mutating/validating admission webhooks cần được bảo vệ:

- Service/endpoint được xác thực và phục vụ đúng TLS/CA bundle.
- Webhook RBAC và config owner có quyền tối thiểu.
- `failurePolicy`, timeout và HA được chọn theo mức độ rủi ro/availability.
- Tránh một webhook có thể chặn toàn cluster khi nó không sẵn sàng, hoặc bị cấu hình fail-open cho resource nhạy cảm ngoài chính sách.
- Theo dõi các deployment thay đổi webhook configs, selectors, namespaces và certificates.

Admission policies có thể bổ sung bảo vệ chứ không phải phép bảo đảm không tồn tại đường bypass ở các thành phần khác.

## 12. Etcd: cơ sở dữ liệu của control plane

**etcd** lưu trạng thái Kubernetes, bao gồm cấu hình và những dữ liệu nhạy cảm. Không nên xem nó như một key-value store mà mọi node/namespace có thể truy cập trực tiếp.

### 12.1. Bảo vệ đường mạng và danh tính etcd

- Giới hạn truy cập etcd chỉ cho control-plane principals và peers được phép theo topology.
- Dùng **mutual TLS/client certificate authentication** với CA/certificates được quản lý, kiểm tra SAN/peer identity và rotation.
- Hạn chế quyền truy cập host chứa etcd và đường backup/snapshot.
- Tránh đưa các cổng etcd (thường gặp client 2379 và peer 2380 theo cấu hình) ra Internet hoặc workload network công cộng.
- Giám sát membership changes, access errors, latency và disk pressure.

### 12.2. Encryption at rest khác transport encryption

TLS bảo vệ đường truyền client ↔ etcd khi được bật đúng, nhưng **không tự mã hóa dữ liệu đã ghi trên đĩa**.

Kubernetes có thể được cấu hình **encryption at rest** cho những API resources như `Secrets` bằng encryption provider/KMS theo kiến trúc. Cần quản lý key lifecycle, encryption provider configuration và migration/re-encryption khi đổi khóa.

Ngoài ra, backup/snapshots, log files và storage volume của etcd có thể chứa dữ liệu nhạy cảm; phải mã hóa, hạn chế truy cập, kiểm thử restore và kiểm soát retention. **Base64 encoding của Secret manifest không phải encryption**.

## 13. Kubelet, node và CRI socket

Trong Kubernetes, kubelet điều khiển runtime ở node theo desired state. Runtime endpoint thường là một Unix socket của **containerd** hoặc **CRI-O**, không nhất thiết có Docker Engine.

| Điểm quản lý | Quyền cần kiểm soát | Rủi ro |
|---|---|---|
| Kubelet API | Xác thực/ủy quyền, nguồn kết nối, TLS | Đọc/thao tác trạng thái node/pod theo quyền |
| CRI runtime socket | Truy cập host-local IPC, UID/GID/ACL | Điều khiển containers/pods trên node |
| Host filesystem/volumes | Root, mount points, device access | Đọc/ghi dữ liệu và credential node |
| Node credentials | Node identity, kubelet client certificates/tokens | Giả danh hoặc sử dụng quyền node |
| Container images/registry | Signed artifacts, provenance, pull secrets | Supply-chain compromise, credential leak |
| CNI plugin | Network namespaces, routing, policies | Cô lập mạng không hiệu lực nếu plugin/policy sai |

### 13.1. Kubelet authorization và Node authorizer

Tùy cách cluster triển khai, kubelet có endpoint HTTPS quản trị (thường trên 10250) cần được bảo vệ bằng authentication/authorization và network access controls. Không mở các chế độ anonymous/unauthorized truy cập vì tiện chẩn đoán. Những read-only interfaces di sản (ví dụ 10255 trong một số cài đặt cũ) cần **bị tắt hoặc kiểm soát theo chính sách**, không mặc định còn tồn tại trên mọi phiên bản.

Kubernetes **Node authorizer** và **NodeRestriction admission** có thể giảm quyền của node identities trong mô hình hỗ trợ. Chúng **không cứu được một node/host đã bị chiếm quyền root** và cũng không thay segmentation.

### 13.2. Vì sao CRI socket cần được đối xử tương tự Docker socket?

Một runtime socket host-local có thể cho phép thao tác mạnh trên node nếu principal được cấp quyền. Dù API/giao thức và quyền khác Docker Engine, nguyên tắc chung vẫn là:

**Không mount host runtime socket vào pod chỉ để “đọc trạng thái” nếu chưa có threat model, quyền giới hạn và phương án thay thế.**

Nếu một DaemonSet hệ thống bắt buộc cần quyền host/runtime, hãy cách ly riêng namespace/node pool, ghim hình ảnh được kiểm chứng, giới hạn egress, đánh giá privilege, patching, audit và quy trình phê duyệt.

## 14. Network security của control plane

### 14.1. NetworkPolicy không tự bảo vệ mọi host/control-plane traffic

Kubernetes `NetworkPolicy` phụ thuộc vào **CNI/network policy implementation**. Nó chủ yếu áp cho traffic của Pod ở những điều kiện được implementation hỗ trợ, không phải firewall host toàn diện.

Đặc biệt cần thận trọng:

- Host-network Pods và traffic liên quan tới host/kubelet có thể có hành vi khác Pod networking thông thường.
- API server/etcd có thể chạy ngoài pod network hoặc trên host/control-plane nodes riêng.
- Traffic sau NAT, service VIP, egress gateway và node-local endpoints có thể cần kiểm thử thực tế.
- Default-deny Pod policy có thể vô tình cắt DNS, service discovery, metrics hoặc controller connectivity.

**Không ghi “đã có Kubernetes NetworkPolicy nên Docker socket/etcd/kubelet an toàn”.** Những interface đó cần **OS file permissions, host/network firewall, management subnet và IAM/certificates** tương ứng.

### 14.2. Ma trận kết nối tối thiểu

| Nguồn → đích | Mục đích | Quy tắc logic |
|---|---|---|
| Operator bastion → kube-apiserver | Quản trị được xác thực | ALLOW đúng nguồn/port, audit và MFA ở lớp identity |
| Workload cần Kubernetes API → kube-apiserver | Chỉ API operations được phê duyệt | ALLOW có kiểm soát; RBAC ít quyền |
| App thông thường → Docker/CRI socket | Không có nhu cầu | **Không mount/không cấp quyền** |
| Public/guest network → Docker remote API/kubelet/etcd | Không có nhu cầu | DENY |
| Kube-apiserver → etcd | Lưu/đọc cluster state | ALLOW đúng TLS identities và đường được phê duyệt |
| Control-plane components ↔ kube-apiserver | Reconcile/scheduling | ALLOW theo deployment cụ thể |
| Kube-apiserver → kubelet | Tác vụ quản lý node theo kiến trúc | ALLOW đúng nguồn, TLS/authZ |
| CI runner → image registry | Push/pull artifact theo scope | ALLOW bằng identity ngắn hạn |
| CI runner → cluster API | Deploy đúng namespace khi có phê duyệt | ALLOW hẹp, không mặc định cluster-admin |
| Workload → ứng dụng/data service | Traffic nghiệp vụ | ALLOW theo service identity, network policy và AuthZ |

Các giá trị port/IP, hướng luồng và thành phần không giống nhau giữa self-managed cluster, managed control plane và CNI khác nhau. Ma trận là **yêu cầu chính sách**, không phải cấu hình firewall áp dụng trực tiếp.

### 14.3. Control plane tại cloud managed service

Với Kubernetes do nhà cung cấp quản lý, một số thành phần control plane có thể do cloud provider vận hành; người dùng không được truy cập host hoặc etcd trực tiếp. Tuy vậy vẫn cần:

1. Chọn **public/private API endpoint** và allowed source networks theo sản phẩm.
2. Kết hợp cloud IAM/OIDC/SSO với Kubernetes RBAC và cơ chế liên kết quyền có hiệu lực.
3. Kiểm tra node identity, workload identity, service accounts, admission và audit.
4. Hạn chế quyền sửa cluster-level networking, logging và security policies.
5. Đánh giá trách nhiệm chia sẻ: provider bảo vệ phần hạ tầng họ quản lý, **khách hàng vẫn chịu trách nhiệm về cấu hình, danh tính và workloads**.

“Managed” không đồng nghĩa nhà cung cấp đã cấp least privilege cho mọi ServiceAccount hoặc tự loại bỏ Pod đặc quyền.

## 15. Bảo vệ ServiceAccount tokens và secret trong control plane

### 15.1. Token có thể là chìa khóa của Kubernetes API

Một Pod có service account token có thể sử dụng token đó để xác thực với kube-apiserver theo phạm vi token và quyền RBAC. Bảo vệ token đòi hỏi:

- Cấp **ServiceAccount riêng cho mỗi workload** khi cần truy cập API, thay vì dùng tài khoản chung quyền rộng.
- Không tự động cấp API token cho ứng dụng **không cần** dùng Kubernetes API; cấu hình `automountServiceAccountToken: false` ở nơi phù hợp.
- Ưu tiên **bound/projected, short-lived tokens** được cấp qua cơ chế hỗ trợ, xem audience/expiration và rotation.
- Không lưu kubeconfig admin, static service-account token hoặc private key vào image/ConfigMap/logs.
- Giám sát ServiceAccount/RBAC changes, quyền đọc Secret, TokenRequest và hành vi API bất thường.

### 15.2. Quyền lấy Secret là quyền đọc dữ liệu nhạy cảm

Kubernetes Secret có thể chứa registry credentials, DB passwords, TLS keys hoặc token. Chỉ các workload/controller thực sự cần mới được đọc. Với production:

- Cân nhắc secret manager/KMS/CSI integration được quản lý, quyền truy cập theo workload identity.
- Mã hóa at rest ở API server/etcd theo cấu hình được hỗ trợ.
- Không đưa giá trị Secret vào pipeline log, kubectl output chia sẻ hoặc Git repository.
- Quy trình rotate/revoke và kiểm tra tác động workload.

**RBAC `get secrets`** có thể ảnh hưởng trực tiếp đến nhiều dịch vụ ngoài Kubernetes. Không gọi nó là quyền đọc vô hại chỉ vì verb là GET.

## 16. Cấu hình minh họa: container không có socket

Mẫu Docker Compose dưới đây chỉ minh họa **nguyên tắc không cấp quyền daemon** cho một tác vụ xử lý báo cáo nội bộ:

~~~yaml
# Ví dụ kiến trúc minh họa, cần có image và thư mục đầu vào hợp lệ.
services:
  report-reader:
    image: registry.example.test/monitoring/report-reader:1.0.0
    user: "10001:10001"
    read_only: true
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=64m
    volumes:
      - ./reports:/reports:ro
    networks:
      - isolated-reports

networks:
  isolated-reports:
    internal: true
~~~

**Điểm cần quan sát:**

1. **Không có** mount `/var/run/docker.sock` hay bất kỳ runtime socket nào.
2. Chạy bằng UID/GID không phải root và root filesystem read-only, thu hẹp bề mặt thay đổi.
3. Thư mục dữ liệu được mount read-only; không cấp cả host filesystem.
4. Network internal chỉ để minh họa một workload không cần egress; sản phẩm thực cần xác định DNS, metrics sink và proxy theo yêu cầu.
5. Những tùy chọn hardening vẫn **không thay kiểm tra lỗ hổng image, supply chain, credentials và workload permissions**.

**Không triển khai nguyên mẫu mà chưa đánh giá tương thích ứng dụng.** Image và đường dữ liệu là placeholder; không có nghĩa hệ thống sẽ tự tạo file hoặc sinh báo cáo.

### 16.1. Một bản đặc tả phòng thủ cho socket monitoring

Nếu một agent thực sự cần quan sát host:

~~~yaml
# Pseudo-policy phục vụ kiến trúc, KHÔNG phải Docker/Compose schema.
daemonObservability:
  requiredCapabilities:
    - container-health-metrics
    - lifecycle-events-with-redaction
  forbiddenCapabilities:
    - create-or-run-containers
    - exec-into-workloads
    - manage-volumes-or-host-mounts
    - read-container-env-secrets
  accessModel:
    preference: dedicated-observability-agent-with-least-privilege
    directDockerSocketMount: forbidden-by-default
    socketProxyException:
      requiresThreatModel: true
      endpointAndMethodAllowlist: true
      dataRedactionAndAuth: true
      independentSecurityReview: true
  network:
    egress: approved-metrics-collector-only
    managementPlane: isolated
  operations:
    owner: platform-security
    auditAccess: true
    rotateCredentials: true
~~~

**Ý nghĩa:** trước khi cấp socket, phải hỏi agent cần **dữ liệu gì**, có cách nào lấy qua metrics/logging API ít quyền hơn không, và ai chịu trách nhiệm khi quyền cấp quá rộng. Không có YAML giả định nào tự biến Docker API thành read-only.

## 17. Kubernetes mẫu: ServiceAccount và Role ít quyền

### 17.1. Workload không cần API token

~~~yaml
# Đặc tả Pod ví dụ; cần image và namespace tương ứng trong lab.
apiVersion: v1
kind: Pod
metadata:
  name: report-viewer
  namespace: observability
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: viewer
      image: registry.example.test/security/report-viewer:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: reports
          mountPath: /reports
          readOnly: true
  volumes:
    - name: reports
      emptyDir: {}
~~~

**Mục đích:** minh họa không mount Docker/CRI socket, không cấp ServiceAccount token vào container theo cơ chế auto-mount, giảm quyền Linux và bảo vệ filesystem. `emptyDir` được mount read-only ở container nên bản mẫu **không tự có dữ liệu báo cáo**; cần nguồn dữ liệu/sidecar được thiết kế riêng để đưa dữ liệu vào volume trước khi thực sự dùng trong hệ thống.

Tạo Pod còn phụ thuộc admission policy, image permissions, quota và runtime; đây **không phải manifest production hoàn chỉnh**. Không gọi “đã bật Restricted” chỉ vì có vài trường securityContext trong manifest.

### 17.2. Role chỉ đọc một loại tài nguyên khi thật sự cần API

~~~yaml
# RBAC ví dụ: chỉ đọc Deployment trong namespace observability.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: deployment-inspector
  namespace: observability
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: deployment-readonly
  namespace: observability
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: bind-deployment-inspector
  namespace: observability
subjects:
  - kind: ServiceAccount
    name: deployment-inspector
    namespace: observability
roleRef:
  kind: Role
  name: deployment-readonly
  apiGroup: rbac.authorization.k8s.io
~~~

Bản này **không cấp `get secrets`, `create pods` hay `cluster-admin`**. Nó chỉ minh họa RBAC cho một principal cần đọc metadata Deployment trong một namespace. Nếu Pod thật cần gọi API, phải cấu hình ServiceAccount/token phù hợp theo cơ chế Kubernetes **khác với Pod `automountServiceAccountToken: false` ở ví dụ trước**; không nhét admin kubeconfig vào image để giải quyết.

Ngay cả `get/list/watch deployments` có thể tiết lộ metadata hoặc thông tin vận hành nhạy cảm. Chỉ cấp khi nhiệm vụ cần; ghi lại danh tính, scope và thời hạn.

### 17.3. Pod Security Admission labels là policy, không phải phép chứng thực

Trong một namespace, đội vận hành có thể áp Pod Security Admission `enforce`/`audit`/`warn` theo policy như `restricted` khi cluster hỗ trợ và phù hợp:

~~~yaml
# Ví dụ phần metadata namespace để REVIEW, KHÔNG áp mù lên production.
apiVersion: v1
kind: Namespace
metadata:
  name: observability
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
~~~

Áp các labels này lên namespace có sẵn **có thể làm Pod mới/update bị từ chối** và cần xử lý exception cho system agents. Trước production rollout, kiểm tra policy version, exemptions, admission configuration và chạy audit/warn/canary. Namespace labels không thay kubelet/host runtime hardening.

## 18. Quan sát chỉ đọc: Docker host

Các lệnh dưới đây chỉ dành cho **host do bạn quản lý hoặc được ủy quyền**. Không tự thêm user vào nhóm docker, thay quyền socket, bật TCP API hay khởi tạo container mới trong bước quan sát.

### 18.1. Xem Unix socket và quyền hiện tại

~~~bash
# Xem owner/group và mode của socket Docker nếu path tồn tại.
ls -l /var/run/docker.sock
stat -c '%a %U %G %n' /var/run/docker.sock

# Kiểm tra UID/GID/nhóm của user hiện tại.
id

# Chỉ đọc thông tin nhóm docker, nếu được cấu hình trên host.
getent group docker
~~~

**Diễn giải:** nếu socket thuộc nhóm docker và user có quyền kết nối, phải xem đây là **privileged access**. Trên rootless Docker, Unix socket có thể ở vị trí khác, ví dụ dưới `/run/user/<uid>/docker.sock`. Nếu file không tồn tại, đừng vội kết luận “host không chạy container”: có thể dùng containerd/CRI-O hoặc Docker Desktop/runtime khác.

### 18.2. Đọc Docker context và daemon security options

~~~bash
# Chỉ đọc context được CLI biết; kết quả có thể tiết lộ endpoint quản trị.
docker context ls
docker context show

# Chỉ chạy nếu account đã được cấp quyền truy cập daemon.
docker version
docker info --format '{{json .SecurityOptions}}'

# Danh sách container được phép nhìn thấy (không in environment/secrets).
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
~~~

**Không yêu cầu thêm quyền root/docker group chỉ để chạy những lệnh này** nếu tài khoản không có quyền. Một số thông tin daemon có thể nhạy cảm; không gửi output có hostname, image repository nội bộ hoặc admin endpoint vào nơi công khai.

Lệnh `docker context ls` có thể cho biết remote endpoint đang dùng SSH/TCP/Unix, nhưng **không tự xác minh rằng TLS client cert được kiểm tra đúng, firewall đã đóng mọi port khác hoặc daemon không còn listening socket phụ**.

### 18.3. Quan sát listening TCP ports

~~~bash
# Quan sát socket listening của host được cấp quyền, không sửa cấu hình.
ss -lnt

# Nếu có quyền xem metadata process, có thể đọc chi tiết hơn.
ss -lntp
~~~

Khi thấy cổng quản trị Docker/Kubernetes/runtime, xác minh **bind address, firewall, route/VPN và TLS/authN** theo inventory. Port `2376` không chứng minh TLS đã được kiểm tra đúng; port `2375` không được mở ra Internet vì tiện vận hành.

## 19. Quan sát chỉ đọc: Kubernetes control plane

Các lệnh sau cũng cần **kubeconfig/context đã được cho phép** và có thể chỉ trả một phần dữ liệu do RBAC.

~~~bash
# Không đổi context; chỉ hiển thị đang thao tác với cluster nào.
kubectl config current-context

# Xem quyền của identity hiện tại trong một namespace.
kubectl auth can-i --list -n observability
kubectl auth can-i get secrets -n observability
kubectl auth can-i create pods -n observability
kubectl auth can-i create clusterrolebindings

# Liệt kê namespace và các nhãn Pod Security Admission.
kubectl get namespaces --show-labels

# Đọc các binding/Role được phép nhìn thấy.
kubectl get rolebindings -A
kubectl get clusterrolebindings

# Đọc danh sách pod để đối chiếu owner; không dump Secret values.
kubectl get pods -A -o wide
~~~

**Chú ý:** `kubectl auth can-i` chỉ đánh giá khả năng authorization của identity trong ngữ cảnh hiện tại; nó không chạy thao tác tương ứng. Nhưng danh sách quyền cho thấy **một phần quyền qua API server**, không đánh giá direct host/CRI socket, admission policy hoặc các đường IAM bên ngoài.

Kết quả `get pods -o wide` có thể có node names, pod IP, namespace và metadata hạ tầng; **không chia sẻ thô** với người ngoài phạm vi.

### 19.1. Tránh biến kiểm tra thành rủi ro

Không cần đọc `kubectl get secrets -o yaml` hay in kubeconfig admin để xác minh quyền. Nếu nhiệm vụ là xác nhận “Role có đọc Secret không”, dùng **`kubectl auth can-i get secrets`**, xem RBAC bindings và logs, không thực hiện đọc Secret thật.

Không thay đổi `kubelet` flags, socket permissions, RBAC hoặc admission rules trực tiếp trên production chỉ để “thử lý thuyết”. Phần triển khai phải qua change management riêng.

## 20. Threat modeling: 20 kịch bản rủi ro

| ID | Rủi ro | Boundary bị thử thách | Kiểm soát và bằng chứng |
|---|---|---|---|
| D01 | **Docker socket mount vào web container** | App → Engine API | Không mount; inventory volumes; review daemon access |
| D02 | **Socket mount `:ro` bị hiểu nhầm** | Filesystem mount → IPC API | Xác minh daemon API permissions, không coi `:ro` là read-only API |
| D03 | **User được thêm vào `docker` group tùy tiện** | OS user → rootful daemon | Privileged access review, group membership audit |
| D04 | **Docker TCP API exposed không TLS** | Untrusted network → daemon | Firewall, tắt endpoint, SSH/mTLS và authN |
| D05 | **TLS client key bị lộ** | Identity → remote daemon | Rotation/revoke, secret manager, network allowlist |
| D06 | **Socket proxy whitelist quá rộng** | Agent → privileged API | Method/resource allowlist, data redaction, security review |
| D07 | **CI runner dùng production Docker socket** | Build code → host | Ephemeral isolated builders, không dùng production daemon |
| D08 | **Kubernetes ServiceAccount có quyền rộng** | Pod → API server | Namespace RBAC, token control, least privilege |
| D09 | **`get secrets` cấp tràn lan** | API → confidential data | Rà soát bindings, audit secret access, KMS |
| D10 | **Pod có hostPath/runtime socket** | Pod isolation → host | PSA/admission, node isolation, host permission |
| D11 | **Privileged/hostNetwork Pod không kiểm soát** | Pod → host/control plane | Restricted policies, exceptions có owner |
| D12 | **API server public không có nguồn giới hạn** | Internet → Kubernetes control plane | Authorized networks/private endpoint, strong auth |
| D13 | **Kubelet API authZ thiếu** | Network → node | AuthN/AuthZ, TLS, host firewall, patching |
| D14 | **Etcd không tách mạng/TLS** | Pod/VM → cluster state | Etcd peer/client mTLS, isolated network |
| D15 | **Secrets at rest/backup lộ** | Storage → identity material | Encryption at rest, encrypted backups, retention |
| D16 | **Admission webhook fail-open không chủ đích** | API write → workload policy | Failure policy review, availability, regression |
| D17 | **Namespace giả định là tenant boundary tuyệt đối** | Tenant A → cluster resources/tenant B | RBAC, PSA, CNI, cluster isolation khi cần |
| D18 | **NetworkPolicy không chặn host services** | Pod network → host runtime/kubelet | Host firewall/ACL, node policy, CNI-specific tests |
| D19 | **Audit thiếu hoặc log chứa secret** | Incident response → evidence/PII | Structured audit, redaction, access control |
| D20 | **Control-plane policy drift/compromise** | CI/IAM → cluster role/admission | IaC, approval, immutable audit, alert và rollback |

### 20.1. Đặt mức độ ưu tiên

Một host rootful có socket mount vào ứng dụng public và không có giám sát là **rủi ro cao** vì mức quyền rất lớn và boundary ở sát bề mặt Internet. Một API server private nhưng cho hàng trăm service accounts quyền cluster-admin cũng rủi ro cao vì credential của bất kỳ workload nào trong nhóm đó có thể bị lạm dụng.

**Mức độ rủi ro không thể suy bằng tên công nghệ**; đánh giá xác suất bị chiếm quyền, privilege level, asset value, khả năng phát hiện, blast radius và đường khôi phục.

## 21. Bằng chứng quan sát và giám sát

| Nguồn | Dữ liệu nên quan sát | Giới hạn |
|---|---|---|
| Docker host/service manager | Daemon listening endpoints, service configuration change, process identity | Không tự chỉ ra tất cả API actions nếu không có audit |
| Host audit/eBPF/EDR khi được hỗ trợ | Truy cập Unix socket, process ancestry, quyền file, network egress | Cần test collector accuracy và policy riêng tư |
| Docker daemon/API gateway logs | AuthN, request metadata, principal, decision theo cơ chế triển khai | Engine API không mặc định có RBAC/audit per-user đầy đủ |
| CI/CD logs | Pipeline identity, branch/source, builder, artifact digest, approvals | Có thể lộ credential nếu logging kém |
| Kubernetes audit | Principal, verb, resource, namespace, response code, source IP | Audit policy/level ảnh hưởng dung lượng và PII |
| API server metrics | AuthN/AuthZ failures, admission denials, latency, errors | Cần phân biệt lỗi user và sự cố control plane |
| Admission policy logs | Pod Security warnings/audit violations, webhook rejects | Không phải mọi bypass host-level đi qua admission |
| Kubelet/runtime/OS logs | Runtime failures, service restart, privileged actions | Dữ liệu node và workload nhạy cảm |
| etcd metrics/audit | Health, TLS errors, peer changes, backup events | Không thay application/control-plane audit |
| Cloud IAM/control-plane audit | Cluster endpoint changes, IAM role binding, node pool changes | Shared responsibility, không đồng nhất Kubernetes RBAC |
| Network flows | Source/destination/port, allow/deny, traffic tới management zones | Không tự xác nhận API action đã được phép |

### 21.1. Những tín hiệu cần cảnh báo

- Container hoặc Pod mới được cấp mount tới Docker/CRI socket, `hostPath` nhạy cảm hoặc `privileged`.
- Principal được thêm vào `docker` group, thay quyền socket hoặc mở mới listener TCP daemon.
- Tạo bất thường các RoleBinding/ClusterRoleBinding cho quyền rộng, `cluster-admin` hoặc verbs nhạy cảm.
- Tăng số lần `pods/exec`, đọc secrets, impersonation hoặc ServiceAccount TokenRequest ngoài baseline.
- API server/kubelet/etcd reachable từ network không nằm trong allowlist.
- Thay đổi admission webhook failure policies, exemptions, namespace PSA labels hoặc tắt audit.
- Node audit/EDR mất telemetry đúng thời điểm một agent privileged được cập nhật.

Không coi **mọi thay đổi privileged** là tấn công: CNI, CSI, monitoring hoặc cluster upgrade đôi khi cần quyền cao. Cảnh báo phải đối chiếu **change ticket, principal, image digest, owner, thời gian và kết quả kiểm thử**.

### 21.2. Bảo vệ dữ liệu audit

Kubernetes audit log có thể chứa metadata identity, API resource names và ở mức ghi sâu có thể chứa body request/response chứa thông tin nhạy cảm. Thiết kế audit policy chọn mức dữ liệu phù hợp, **không vô tình ghi Secret values, tokens hoặc private keys** vào logging pipeline. Có retention, encryption, RBAC và truy vết quyền đọc log.

## 22. Ma trận kiểm thử bảo vệ Docker socket và control plane

Chỉ thực hiện **trong môi trường có quyền kiểm tra**; các ca liên quan quyền quản trị nên mô phỏng bằng account/thành phần lab, không khai thác endpoint thật hoặc gửi lệnh thay đổi host trái quy trình.

| ID | Phép kiểm tra | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | Operator thuộc nhóm được phép kiểm tra Docker host | Xem được thông tin daemon cần thiết | Host identity và read-only command result |
| N01 | User thường không thuộc nhóm được phép | Không truy cập Docker rootful socket | OS permissions và access decision |
| N02 | Web container không cần Docker API | Không có Docker/CRI socket mount hoặc đường proxy tương đương | Deployment manifest/volume inventory |
| N03 | File/socket mount `:ro` bị yêu cầu coi read-only API | Review xác nhận **không đủ**; không được chấp thuận | Design review và policy exception |
| N04 | App/guest network tới Docker TCP API | Bị deny theo firewall, không exposed | Network policy/source-specific observation |
| P02 | Operator qua SSH/mTLS management path | AuthN và route đúng, có audit | Host/identity/gateway logs |
| N05 | TLS peer/client cert không hợp lệ | Remote management từ chối | TLS/auth failure |
| N06 | CI runner không có production daemon permission | Không điều khiển host production | Identity/runner isolation evidence |
| P03 | CI builder đúng quyền push artifact | Build/push thành công trong môi trường cô lập | Artifact digest, pipeline logs |
| N07 | ServiceAccount không cần API | Không được mount token tự động | Pod spec và runtime verification |
| P04 | ServiceAccount được cấp quyền đọc Deployment | Chỉ được get/list/watch trong scope | `kubectl auth can-i` và RoleBinding |
| N08 | ServiceAccount thử quyền `get secrets` không được cấp | Authorization deny | RBAC policy test, API audit |
| N09 | ServiceAccount thử tạo privileged Pod ngoài policy | Admission deny trong namespace enforce | PSA/admission logs |
| N10 | Pod yêu cầu hostPath Docker/CRI socket | Bị chặn theo security policy được thiết kế | Admission policy và test object |
| N11 | Principal không có cluster-admin quyền | Không thể tạo ClusterRoleBinding đặc quyền | `kubectl auth can-i` và audit |
| P05 | Kubelet/etcd chỉ nhận kết nối hợp lệ từ management/control plane | TLS và allowlist pass theo topology | Network/PKI/config audit |
| N12 | Source ngoài allowlist tới API/kubelet/etcd | Network deny hoặc AuthN/AuthZ deny như thiết kế | Firewall/TLS/API logs |
| P06 | API server/admission components bình thường | Deploy workload hợp lệ thành công | API response, events, workload health |
| N13 | Admission webhook không sẵn sàng trong lab | Failure behavior đúng thiết kế, không tạo bypass bất ngờ | Webhook `failurePolicy` và API logs |
| P07 | Audit pipeline hoạt động | Ghi identity/verb/decision đủ, không lộ secrets | Sanitized audit sample |
| N14 | Pod trong namespace tenant A có route sang tenant B | Application/network authz vẫn từ chối theo policy | CNI firewall + service AuthZ |
| P08 | Thay policy theo canary | Workload được phép còn chạy, deny được thực thi | Admission events, SLO và config diff |
| N15 | Tắt một control-plane route không được phép | Không có đường bypass khác sang host-level sockets | Host firewall/connector tests |

**Các ca negative phải có đối chứng.** Một timeout tới API server đã dừng không chứng minh firewall chặn đúng; một Pod không chạy vì image không tồn tại không chứng minh Pod Security Admission hoạt động.

## 23. Troubleshooting theo trust boundary

| Triệu chứng | Giả thuyết | Cách kiểm tra an toàn |
|---|---|---|
| Docker CLI báo permission denied | User không được phép vào socket, mode/group/ACL | `id`, `stat`, owner/permission review |
| CLI không kết nối được daemon | Docker service dừng, context sai, socket path khác | `docker context ls`, service health và host logs |
| Có Docker API port exposed | Daemon listening ngoài phạm vi | `ss -lnt`, firewall, service configuration review |
| Agent cần socket nhưng security policy cấm | Kiến trúc monitoring phụ thuộc daemon quá rộng | Khảo sát telemetry API/metrics agent ít quyền |
| CI build chạy mà deploy thất bại | Registry/IAM/namespace RBAC khác nhau | Pipeline identity, Role/RoleBinding, admission events |
| Pod bị Pod Security Admission từ chối | hostPath, privilege, capabilities, seccomp hoặc policy version | Admission message, manifest review |
| Pod được tạo nhưng không gọi được API | Token không mount, RBAC deny, DNS/TLS/network | `kubectl auth can-i`, API error, CNI/route logs |
| Kubelet unreachable | Firewall, cert, authZ hoặc node/network lỗi | Control-plane/node logs, approved connectivity checks |
| etcd chậm/không healthy | TLS, quorum, disk, network hoặc capacity | Etcd/cluster metrics; không đọc raw data trái quyền |
| Secrets tồn tại nhưng service 403 | RBAC/API access không đồng nghĩa app credential hợp lệ | Application identity và permissions |
| NetworkPolicy áp rồi vẫn tới host | HostNetwork/CNI/policy coverage không đúng kỳ vọng | CNI docs/config và source-specific tests |
| Audit thiếu thao tác | Audit level/sink, bypass host socket, log pipeline | API/audit/EDR correlation |
| Managed cluster API public | Private endpoint/authorized networks chưa cấu hình đúng | Cloud control-plane config và network allowlist |

**Không sửa `permission denied` bằng `chmod 666 /var/run/docker.sock` hoặc thêm toàn bộ developer vào nhóm docker.** Lỗi quyền có thể là một policy đang hoạt động đúng. Hãy xác định nhu cầu và chọn con đường cấp quyền tối thiểu.

## 24. Quy trình hardening và rollout có kiểm soát

### Bước 1 — Kiểm kê surfaces và identity

Lập danh sách Docker hosts, rootful/rootless mode, socket paths, TCP listeners, client contexts, CI runners, kube-apiserver, kubelet/CRI sockets, etcd, admission webhooks, namespace/cluster roles và cloud management endpoints. Gắn owner, mức nhạy cảm và người được phép.

### Bước 2 — Xóa quyền socket không cần thiết

Tìm workload/agent có mount Docker/CRI socket hoặc có quyền API remote. Đánh giá từng nhu cầu; ưu tiên thay bằng metrics/logging APIs ít quyền. Không xóa socket của hệ thống đang chạy mà chưa có kế hoạch tương thích và rollback.

### Bước 3 — Cô lập network management

Giới hạn từ management subnet/bastion tới daemon, kube-apiserver/kubelet/etcd; dùng host firewall/cloud firewall, đúng endpoint policy, TLS/SSH và IAM. Tách application/guest traffic và quản trị container. Kiểm tra cả IPv6, route transit, node-private IP và VPN paths.

### Bước 4 — Giảm quyền users, service accounts và workload

Rà soát `docker` group, admin SSH, Kubernetes RoleBindings, ServiceAccount tokens, CI secrets, cluster-admin, `pods/exec`, `get secrets`. Đặt quyền ít nhất cần thiết, ưu tiên identity ngắn hạn và audit. Hardening containers bằng security contexts, capabilities, seccomp và read-only root FS khi phù hợp.

### Bước 5 — Bảo vệ API/admission/etcd

Bật kiểm soát authentication/authorization đúng, giảm quyền admin và audit actions; cấu hình Pod Security Admission theo namespace với giai đoạn warn/audit/enforce, bảo vệ etcd mTLS/encryption at rest/backup. Quản lý certificates và khóa qua lifecycle rõ ràng.

### Bước 6 — Canary và kiểm thử negative

Đầu tiên áp trên môi trường lab hoặc một node pool/namespace canary. Chạy các test về socket access, remote API, ServiceAccount RBAC, admission, kubelet/etcd network, CI isolation, token và audit. Kiểm tra các agents hệ thống như CNI/CSI/monitoring không bị phá.

### Bước 7 — Rollout và giám sát

Version hóa IaC/admission/RBAC và chính sách network; có ticket và approval. Theo dõi denial, Pod scheduling, agent health, rollout errors, API latency và security alerts. Chuẩn bị đường rollback **không cấp trở lại quyền vượt quá nhu cầu**.

### Bước 8 — Rà soát định kỳ và incident readiness

Rà soát khi thêm CI runner, monitoring agent, Docker host, runtime version, Kubernetes add-on, namespace tenant hoặc cloud control-plane endpoint. Khi nghi compromise, ưu tiên **cô lập host/credential, thu thập evidence có kiểm soát, rotate/revoke và phục hồi từ trusted artifacts**, không chỉ restart container.

## 25. Tình huống thực hành: dashboard quan sát kéo theo sự cố hạ tầng

**Bối cảnh giả định:** Công ty có ba Docker hosts và một Kubernetes cluster. Đội vận hành triển khai dashboard trong Docker container để hiển thị tên và trạng thái các container. Dashboard được xuất qua reverse proxy; file Compose mount `/var/run/docker.sock:/var/run/docker.sock:ro`. Một CI runner khác được thêm vào nhóm `docker` trên production host để tiện build. Trong Kubernetes, một ServiceAccount của agent giám sát có quyền `get/list secrets` và `create pods` ở nhiều namespace.

Trong một lần diễn tập, nhóm an ninh phát hiện:

| Quan sát | Câu hỏi cần đặt |
|---|---|
| Dashboard container chạy bằng UID 10001 và socket mount `:ro` | Những điều này có giới hạn **Docker Engine API actions** được phép không? |
| Web reverse proxy chỉ cho HTTPS vào dashboard | HTTPS bảo vệ kết nối tới dashboard có thay thế socket authorization không? |
| CI runner build từ mã PR không tin cậy | Pipeline có đang sở hữu quyền trên host production không? |
| Agent Kubernetes có `get secrets` nhiều namespace | Dữ liệu/tài khoản nào có thể bị lộ nếu agent bị chiếm? |
| Namespace đã có default-deny NetworkPolicy | Docker socket và kubelet/CRI có nằm trong phạm vi enforcement đó không? |
| Một managed cluster API server chỉ reachable trong VPC | IAM/RBAC/admission có cần kiểm tra độc lập không? |

### 25.1. Câu hỏi

1. Chỉ ra ít nhất **sáu trust boundaries** trong cả hai kiến trúc Docker và Kubernetes.
2. Vì sao `:ro` và UID non-root **không đủ** để kết luận dashboard chỉ có quyền xem trạng thái?
3. Đề xuất phương án quan sát **không cấp quyền điều khiển Docker daemon** cho dashboard.
4. Đề xuất cách chuyển build jobs ra khỏi production host và quản lý quyền registry/deploy riêng.
5. Viết ma trận quyền tối thiểu cho agent Kubernetes cần đọc tình trạng Deployment **nhưng không cần Secret**.
6. Liệt kê tối thiểu bốn negative tests liên quan socket, RBAC, admission và network.
7. Nếu đã phát hiện socket bị lạm dụng, nên ưu tiên cô lập, chứng cứ, rotation và phục hồi ra sao?

### 25.2. Gợi ý đối chiếu

- **Docker:** Internet/browser → dashboard, dashboard → Unix socket, socket → daemon, daemon → host/containers/volumes, CI code → runner/daemon, operator → SSH/management.
- **Kubernetes:** Pod identity → ServiceAccount token, token → API server authentication, RBAC → admission, API → etcd/controller, kubelet → CRI runtime, node host → network/data.
- `:ro` không chặn các request thay đổi trạng thái qua Unix socket; UID non-root không giúp nếu vẫn có quyền mở socket. Thay bằng agent độc lập thu chỉ số, exporter/metrics service được quản trị hoặc một endpoint quan sát hẹp có auth/audit.
- CI runner nên dùng builder tách biệt/ngắn hạn; không chạy mã PR không tin cậy trên production daemon. Quyền push artifact và quyền deploy cluster phải là những scopes riêng với approval.
- K8s Role chỉ đọc `deployments` trong namespace mục tiêu; không cấp `get secrets`, `create pods`, `cluster-admin` khi không cần. Pod không sử dụng API nên tắt automatic token mounting; nếu có sử dụng API, cấp token đúng audience/expiry.
- Negative tests: user không quyền bị từ chối socket; app container không có runtime socket mount; SA không có quyền Secret; privileged Pod bị admission deny; nguồn ngoài allowlist không tới kubelet/etcd.
- Khi compromise, xem host/cluster là **có nguy cơ bị thay đổi**, cô lập đường quản trị, lưu evidence theo quy trình, rotate credentials/secrets, xem xét rebuild từ image/host/cluster state tin cậy và kiểm tra persistence/automation.

## 26. Checklist bảo vệ Docker socket và control plane

- [ ] Đã phân biệt application data plane, Docker Engine API, Kubernetes API server và CRI runtime socket.
- [ ] Biết Docker Engine rootful socket thường là quyền quản trị host rất mạnh; nhóm `docker` không phải nhóm đọc vô hại.
- [ ] Không dùng `chmod 666` hay mở remote Docker API thiếu xác thực để xử lý lỗi permission.
- [ ] Không gắn `/var/run/docker.sock`/CRI socket vào ứng dụng/agent nếu không có nhu cầu được phê duyệt.
- [ ] Hiểu socket bind mount `:ro` **không biến Engine API thành read-only**.
- [ ] Đã đánh giá quyền UID/GID/ACL/SELinux/AppArmor, rootless và `userns-remap` theo hành vi thật.
- [ ] Remote Docker management qua SSH hoặc mTLS có xác thực đúng và network allowlist; không coi số cổng là chứng cứ TLS.
- [ ] Docker socket proxy nếu có được review API method/path/data exposure và không có đường bypass trực tiếp.
- [ ] CI build/push chạy trên builder được cô lập; không dùng production daemon cho mã không tin cậy.
- [ ] Kubernetes API access có AuthN/AuthZ/RBAC least privilege; không dùng cluster-admin mặc định cho automation.
- [ ] ServiceAccounts chỉ nhận API token khi cần, ưu tiên token giới hạn audience/thời gian sống.
- [ ] Quyền `get/list/watch secrets`, `pods/exec`, `create pods`, `impersonate` và `bind/escalate` được review.
- [ ] Pod Security Admission hoặc admission phù hợp kiểm soát hostPath, privileged, host namespaces, security contexts.
- [ ] Các ngoại lệ PSA/admission dành cho system agents có owner, scope, audit và thời hạn review.
- [ ] Kubelet/CRI và etcd có network isolation, authentication, TLS và host permissions phù hợp.
- [ ] Etcd secrets at rest, backup/snapshot và KMS/PKI keys được bảo vệ theo policy.
- [ ] Không coi `NetworkPolicy` là firewall cho toàn bộ hostNetwork, runtime socket hay managed control plane.
- [ ] Có ma trận allow/deny cho operator, workload, CI, kube-apiserver, kubelet và etcd.
- [ ] Managed cluster public/private API endpoint và cloud IAM được kiểm tra ngoài Kubernetes RBAC.
- [ ] Có audit các thao tác tạo Pods, đổi RBAC/admission, đọc Secrets, thay daemon socket/network.
- [ ] Logs không lộ credential, Secret values, private keys hoặc token không cần thiết; có retention và access audit.
- [ ] Có positive/negative tests cho socket, remote API, ServiceAccount, RBAC, admission và network.
- [ ] Có quy trình canary rollout, change review, rollback và khôi phục sự cố host/cluster bị chiếm quyền.
- [ ] Không tuyên bố “container non-root, Docker socket :ro, private API server” là đã an toàn nếu chưa chứng minh quyền thực tế.

**Ghi nhớ:** **Docker socket là cổng điều khiển Docker daemon, không phải chỉ là một file quan sát**. Trong Kubernetes, **API server, etcd, kubelet và runtime sockets** là các ranh giới đặc quyền khác nhau. Bảo mật hiệu quả cần **giảm quyền truy cập API và socket từ gốc, ngăn đường quản trị không cần thiết, xác minh danh tính và RBAC, kiểm soát admission/node, bảo vệ secrets và audit end-to-end**. Không một lớp riêng lẻ — `:ro`, non-root, NetworkPolicy, VPN hay “private control plane” — có thể thay toàn bộ những lớp còn lại.
