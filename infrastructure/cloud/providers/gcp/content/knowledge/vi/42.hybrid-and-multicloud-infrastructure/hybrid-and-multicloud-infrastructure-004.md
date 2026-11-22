# Connect Gateway và truy cập cluster qua fleet

## 1. Bài toán: quản trị Kubernetes trong hạ tầng lai và đa đám mây

Một tổ chức có thể đồng thời vận hành GKE trên Google Cloud, Kubernetes tại trung tâm dữ liệu và các cluster tại AWS hoặc Azure. Mỗi cluster thường có API server, mạng riêng, cơ chế xác thực và Kubernetes RBAC khác nhau. Nếu kỹ sư phải kết nối từng VPN, cấu hình bastion host hoặc lưu nhiều bộ kubeconfig chứa credential dài hạn, việc vận hành sẽ khó kiểm soát và audit.

**Fleet** cung cấp cách nhóm và quản trị tập hợp cluster theo một phạm vi logic trên Google Cloud. **Connect Gateway** là lối truy cập được quản lý để người dùng hoặc service account chạy lệnh Kubernetes tới những cluster đã đăng ký với fleet. Người quản trị có thể dùng `kubectl`, Google Cloud console hoặc hệ thống tự động hóa theo mô hình hỗ trợ mà không phải xây một proxy công khai riêng cho từng API server.

Một số mục tiêu thiết kế:

- Tìm cluster thuộc fleet từ một danh sách membership được quản lý tập trung.
- Dùng danh tính Google Cloud hoặc danh tính doanh nghiệp liên kết thay vì phát credential tĩnh cho từng người.
- Áp dụng Google Cloud IAM để kiểm soát ai được dùng gateway.
- Áp dụng Kubernetes RBAC **trên từng cluster** để quyết định người đó được đọc hoặc sửa resource nào.
- Giảm nhu cầu mở inbound firewall hoặc cung cấp public Kubernetes API endpoint cho cluster ngoài Google Cloud.
- Duy trì khả năng quản trị cluster từ console, laptop hoặc pipeline CI/CD trong phạm vi được cho phép.

Connect Gateway không phải load balancer cho ứng dụng, không thay thế VPC/VPN/Cloud Interconnect cho lưu lượng dữ liệu, không tự tạo fleet membership và không mặc nhiên cấp quyền `cluster-admin`. Đây chủ yếu là con đường truy cập **Kubernetes API/control plane**.

Trong phạm vi module **CLOUD_PROVIDERS_GCP**, bài học kết nối kiến thức về organization/project, IAM, VPC, GKE, CI/CD, reliability và hạ tầng lai. Cùng một mô hình danh tính và policy có thể hỗ trợ việc giám sát, kiểm tra tình trạng và triển khai có kiểm soát trên nhiều cluster, dù các workload không nằm cùng một cloud.

## 2. Ba khái niệm cốt lõi: fleet, membership và gateway

### 2.1. Fleet

Fleet là một nhóm logic chứa các Kubernetes cluster và tài nguyên liên quan, giúp áp dụng khả năng quản trị đa cluster trên Google Cloud. Fleet được quản lý thông qua một **fleet host project**. Cluster có thể thuộc những môi trường vật lý hoặc cloud khác nhau nhưng cùng xuất hiện trong bảng inventory của fleet.

Fleet không hợp nhất tất cả control plane thành một Kubernetes API duy nhất; mỗi cluster vẫn có Kubernetes API server, lịch trình nâng cấp, node, namespace và RBAC riêng. Lệnh thực thi qua gateway vẫn nhắm tới **một membership cụ thể**.

### 2.2. Membership

Mỗi cluster được đăng ký vào fleet có một **membership resource** trong Google Cloud. Membership có tên và location (có thể là `global` hoặc location cụ thể tùy loại cluster/cách đăng ký).

Ví dụ:

~~~text
projects/FLEET_PROJECT_ID/locations/global/memberships/onprem-hanoi
projects/FLEET_PROJECT_ID/locations/global/memberships/eks-orders
~~~

Tên trên chỉ để minh họa. Không suy diễn location luôn là `global`: người vận hành phải lấy đúng location của membership từ kết quả liệt kê hoặc mô tả resource.

Membership dùng để khám phá và chọn cluster đích. Tên membership không nhất thiết bằng tên cluster của cloud cung cấp hoặc bằng tên Kubernetes context cũ.

### 2.3. Connect Gateway và Connect service

Connect Gateway là API do Google quản lý để client đã xác thực truy cập Kubernetes API của cluster thuộc fleet. Với **cluster không phải GKE trên Google Cloud**, request thường đi qua Connect service và Connect Agent chạy trong cluster, rồi tới API server. Connect Agent chủ động duy trì kết nối ra các endpoint Google Cloud được hỗ trợ; kiến trúc này giúp tránh phải mở cổng inbound từ Internet tới Kubernetes API server chỉ vì cần dùng gateway.

Với **GKE clusters trên Google Cloud**, đường đi có thể kết nối trực tiếp qua tích hợp GKE của gateway và **không yêu cầu Connect Agent** cho gateway. Không áp dụng máy móc bước kiểm tra agent cho mọi GKE cluster. Loại cluster và phiên bản integration quyết định thành phần thực sự cần thiết.

### 2.4. Sơ đồ request flow

~~~mermaid
flowchart TB
    U[Operator / CI service account] --> AUTH[gcloud credential hoặc identity federation]
    AUTH --> GW[Connect Gateway API]
    GW --> IAM{Google Cloud IAM cho phép?}
    IAM -- Không --> DENY1[Chặn ở gateway]
    IAM -- Có --> TYPE{Loại cluster}
    TYPE -- GKE trên Google Cloud --> GK[GKE Kubernetes API]
    TYPE -- On-prem / attached / ngoài GCP --> CONNECT[Connect service]
    CONNECT --> AGENT[Connect Agent trong cluster]
    AGENT --> API[Kubernetes API server]
    GK --> RBAC{Kubernetes RBAC}
    API --> IMP{Agent được phép impersonate?}
    IMP -- Không --> DENY2[Chặn trong cluster]
    IMP -- Có --> RBAC
    RBAC -- Không --> DENY3[Forbidden]
    RBAC -- Có --> OK[Đọc / sửa resource theo quyền]
~~~

Sơ đồ mô tả các lớp kiểm soát logic. Đường đi và thành phần xác thực chi tiết có thể thay đổi giữa GKE, attached clusters, GKE Distributed Cloud và các chế độ identity. Hãy đối chiếu tài liệu dành riêng cho loại cluster được triển khai.

## 3. Connect Gateway khác kết nối Kubernetes trực tiếp thế nào?

| Khía cạnh | Kết nối trực tiếp API server | Qua Connect Gateway |
|---|---|---|
| Endpoint | IP/DNS riêng của API server | Endpoint gateway do Google Cloud quản lý và gắn với membership |
| Khám phá cluster | Tự duy trì danh sách endpoint | Liệt kê fleet memberships |
| Xác thực client | Theo cơ chế API server hoặc provider | Danh tính Google Cloud / phương án federation được hỗ trợ |
| Phân quyền | Kubernetes RBAC và cơ chế provider | IAM ở gateway, cộng RBAC tại cluster |
| Kết nối từ laptop | Thường cần VPN, peering hoặc bastion | Truy cập gateway qua kết nối phù hợp, không nhất thiết tới mạng private của cluster |
| Cluster ngoài Google Cloud | Có thể cần mở ingress tới API server | Connect Agent duy trì kết nối từ cluster ra Connect service |
| Quan sát/audit | Log cluster và hạ tầng riêng | Có thêm Google Cloud API audit cùng log Kubernetes |
| Khi gateway không hoạt động | Có thể còn đường quản trị trực tiếp | Có thể mất đường quản trị qua gateway; cần phương án break-glass |

Gateway **không thay thế** cơ chế vận hành khẩn cấp ở từng cluster. Đội platform nên duy trì quyền quản trị break-glass có kiểm soát và cách kết nối độc lập nếu mạng tới Google Cloud hoặc Connect service gặp sự cố.

## 4. Điều kiện tiên quyết

### 4.1. Công cụ và dự án

Cần chuẩn bị:

1. Project dùng làm fleet host project và quyền quản trị thích hợp.
2. Một Kubernetes cluster có thể đăng ký/đã đăng ký vào fleet; hình thức đăng ký phụ thuộc loại cluster.
3. Google Cloud CLI được cập nhật và `kubectl` tương thích với server.
4. Danh tính Google Cloud hợp lệ (user, service account hoặc workforce identity liên kết).
5. Quyền IAM cho gateway và quyền RBAC phù hợp bên trong cluster.
6. Một admin kubeconfig **có quyền trực tiếp vào cluster** để bootstrap RBAC lần đầu, nếu cluster chưa cấu hình chính sách cho gateway.
7. Network egress cho Connect Agent và thành phần xác thực ngoài Google Cloud, nếu loại cluster cần agent.

Tên project, membership, namespace, tài khoản và context trong các lệnh bên dưới đều là placeholder. Không chạy nguyên xi trên production; kiểm tra target trước khi làm bất kỳ thao tác thay đổi IAM hoặc RBAC nào.

### 4.2. Bật các Google Cloud APIs cần thiết

Theo hướng dẫn thiết lập Connect Gateway, quản trị viên có thể bật các API sau trên fleet host project:

~~~bash
gcloud services enable \
  connectgateway.googleapis.com \
  gkeconnect.googleapis.com \
  gkehub.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=FLEET_PROJECT_ID
~~~

Danh sách này áp dụng cho đường đi `kubectl`/gateway trong hướng dẫn cơ bản. Nếu chỉ đăng nhập bằng Google Cloud console, yêu cầu bật `connectgateway.googleapis.com` có thể khác. Với Google Groups, GKE Identity Service hoặc federation, có thể cần các API và cấu hình bổ sung. Không bật hàng loạt API mà không kiểm tra Organization Policy và quy trình quản trị dịch vụ.

Người thực hiện lệnh cần permission `serviceusage.services.enable` hoặc một role phù hợp như Service Usage Admin. Đây là công việc bootstrap do platform admin thực hiện, không phải quyền cấp cho mọi operator.

### 4.3. Kiểm tra membership đã tồn tại

~~~bash
gcloud container fleet memberships list \
  --project=FLEET_PROJECT_ID
~~~

Kết quả cho thấy membership name, external ID và các thông tin liên quan. Nếu cluster chưa đăng ký, phải đi theo quy trình **đúng loại cluster**: GKE trên Google Cloud, GKE attached cluster, GKE Distributed Cloud hoặc Kubernetes tự quản lý. Lệnh và Connect Agent có thể khác nhau.

Không nhầm `gcloud container clusters list` với `gcloud container fleet memberships list`: danh sách GKE của một project không phải danh sách toàn bộ cluster đã đăng ký vào fleet.

## 5. Agent và mạng cho cluster ngoài Google Cloud

### 5.1. Vai trò của Connect Agent

Ở các cluster không phải GKE trên Google Cloud, Connect Agent tạo kết nối bảo mật từ cluster tới dịch vụ Connect trên Google Cloud và chuyển request được phép từ gateway tới Kubernetes API server.

Để agent hoạt động, thường cần:

- Pod/agent được cài đặt đúng theo quy trình đăng ký.
- Cluster có thể giải DNS và gửi HTTPS/TLS egress tới endpoint cần thiết.
- Các network policies, firewall, proxy và chứng chỉ không chặn kết nối.
- Service identity của agent được cấu hình theo phương thức hỗ trợ.
- Agent có permission Kubernetes cần thiết để forward request và impersonate identity theo chính sách.
- Kubernetes API server hoạt động và agent có thể liên lạc với endpoint nội bộ của nó.

**Không mở public IP cho API server chỉ để thử sửa lỗi agent.** Kiểm tra egress, DNS, proxy và log trước. Nếu có private egress hoặc proxy doanh nghiệp, xác nhận hostname, SNI, CA trust và policy cho phép theo tài liệu của loại cluster.

### 5.2. GKE trên Google Cloud là trường hợp khác

Tài liệu Google Cloud hiện nay nêu rõ gateway tới GKE cluster có thể kết nối trực tiếp, không cần Connect Agent. Nếu operator không thấy namespace `gke-connect` trên một GKE cluster đã đăng ký, không nên kết luận ngay Connect Gateway hỏng.

Ngược lại, với cluster ngoài Google Cloud, lỗi không tìm thấy kết nối đang hoạt động thường cần kiểm tra agent và dịch vụ Connect. Khi đăng ký cluster bằng CLI, flag cài agent và mặc định đã thay đổi qua các phiên bản công cụ, nên cần kiểm tra hướng dẫn đăng ký của loại cluster và phiên bản CLI thay vì giả định luôn được cài.

### 5.3. Không phải data plane

Connect Gateway dùng để quản trị Kubernetes API. Luồng người dùng truy cập HTTP service trong cluster, replication dữ liệu, kết nối database hoặc traffic giữa pod ở các cloud **không đi qua gateway như một service mesh**.

Muốn kết nối workload lai/đa cloud cần thiết kế riêng: VPC, Cloud VPN, Cloud Interconnect, peering, DNS, firewall, ingress, service mesh hoặc phương thức được hỗ trợ khác. Việc `kubectl get pods` thành công qua gateway không có nghĩa pod có thể truy cập database ở cloud khác.

## 6. Hai lớp phân quyền: IAM và Kubernetes RBAC

### 6.1. Google Cloud IAM kiểm soát gateway

IAM quyết định identity có được gọi Connect Gateway API và lấy cấu hình kết nối của membership hay không. Các predefined role thường gặp:

| Role | Vai trò chính | Lưu ý |
|---|---|---|
| `roles/gkehub.viewer` | Xem membership và hỗ trợ lấy thông tin kubeconfig | Không tự cấp quyền đọc mọi pod |
| `roles/gkehub.gatewayReader` | Truy cập gateway ở phạm vi đọc | Thường dùng cho vận hành quan sát |
| `roles/gkehub.gatewayEditor` | Gateway read/write | Vẫn cần Kubernetes RBAC tương ứng |
| `roles/gkehub.gatewayAdmin` | Quản trị gateway và quyền dùng streaming API được hỗ trợ | Cấp cho nhóm nhỏ, không mặc nhiên là Kubernetes cluster-admin |

Permission `gkehub.gateway.stream` cần cho `kubectl exec`, `attach`, `cp` và `port-forward` qua gateway; trong các predefined gateway roles, `roles/gkehub.gatewayAdmin` bao gồm permission này. Khi không cần streaming, không tự động cấp Admin chỉ để chạy lệnh đọc đơn giản.

Các role gateway được cấp ở phạm vi Google Cloud phù hợp với membership/fleet project và policy tổ chức. Scope role ở Google Cloud **khác** namespace của Kubernetes.

### 6.2. Kubernetes RBAC quyết định được làm gì trong cluster

Khi request tới API server, Kubernetes RBAC kiểm tra permission theo `Role` hoặc `ClusterRole` đã gắn qua `RoleBinding`/`ClusterRoleBinding`. Với cluster ngoài GKE sử dụng agent, phải có thêm policy cho phép Connect Agent **impersonate** người dùng hoặc service account đứng sau request.

Vì thế quyền hoạt động phải vượt qua cả hai kiểm tra:

~~~text
Identity được phép dùng Connect Gateway?    IAM: CÓ
Connect Agent có quyền impersonate?         RBAC bootstrap: CÓ (khi cần agent)
Identity được phép get/list pods?           RBAC ở cluster: CÓ
==================================================
Kết quả                                     ĐƯỢC PHÉP
~~~

Nếu IAM cho phép nhưng Kubernetes RBAC từ chối, request vẫn thất bại. Nếu RBAC cho phép nhưng không có gateway IAM role, request có thể bị chặn trước khi tới Kubernetes API server.

### 6.3. Phân biệt identity thực và identity của Connect Agent

Có hai principal với trách nhiệm khác nhau:

- **Người gọi cuối** (ví dụ `alice@example.com` hoặc service account CI/CD): được xác thực ở gateway, phải có IAM role và Kubernetes permission.
- **Connect Agent**: đóng vai trò chuyển request tới Kubernetes API server và cần quyền impersonate danh tính người gọi khi con đường kết nối yêu cầu.

Không cấp `cluster-admin` cho mọi người chỉ vì agent cần cơ chế impersonation. Quyền impersonate của agent và quyền thao tác resource của end user là hai policy khác nhau.

## 7. Ví dụ cấp IAM quyền đọc cho operator

Giả sử một nhóm SRE cần quan sát pod ở cluster `onprem-hanoi` nhưng không được chỉnh sửa deployment.

Quản trị viên cấp IAM trên fleet host project:

~~~bash
gcloud projects add-iam-policy-binding FLEET_PROJECT_ID \
  --member="user:sre-reader@example.com" \
  --role="roles/gkehub.viewer"

gcloud projects add-iam-policy-binding FLEET_PROJECT_ID \
  --member="user:sre-reader@example.com" \
  --role="roles/gkehub.gatewayReader"
~~~

Email ở đây là ví dụ; trong hệ thống thực cần xác minh subject chính xác và tuân thủ quy trình phê duyệt quyền. Dùng Google Groups khi môi trường và tính năng xác thực đã hỗ trợ để giảm việc quản lý từng người; không giả định group support tự động bật trên mọi loại cluster.

Quyền IAM chỉ hoàn thành bước đầu. Người dùng vẫn cần Kubernetes RBAC cho namespace cần quan sát, đồng thời chính sách impersonation cho agent khi cần.

## 8. Tạo Kubernetes RBAC giới hạn namespace

### 8.1. Khai báo quyền chỉ đọc

Ví dụ cấp quyền xem pods/deployments trong namespace `team-a`:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: workload-reader
  namespace: team-a
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch"]
~~~

Role này chỉ có hiệu lực trong namespace `team-a`. Nếu muốn operator đọc `namespaces` hoặc `nodes` (resource ở cấp cluster) cần thêm `ClusterRole` và binding khác. Tránh cấp cluster-wide quyền khi chỉ cần quan sát một namespace.

### 8.2. Bind quyền với người dùng

Ví dụ `RoleBinding` cho một user, áp dụng trên cluster sau khi xác nhận mapping identity phù hợp:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: sre-reader-team-a
  namespace: team-a
subjects:
  - kind: User
    name: sre-reader@example.com
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: workload-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Tên `subjects[].name` phải khớp identity được cluster thấy qua gateway. Với group-based authentication hoặc identity federation, subject format khác tùy provider và cluster setup; không tự đổi `kind: User` thành `Group` nếu chưa có cơ chế chuyển nhóm đúng cách.

### 8.3. Cấu hình impersonation policy bằng công cụ hỗ trợ

Với cluster cần Connect Agent, Google Cloud cung cấp lệnh tạo RBAC để cài cả policy impersonation cần thiết và binding tương ứng:

~~~bash
gcloud container fleet memberships generate-gateway-rbac \
  --membership=onprem-hanoi \
  --role=role/team-a/workload-reader \
  --users=sre-reader@example.com \
  --project=FLEET_PROJECT_ID \
  --kubeconfig=PATH_TO_DIRECT_ADMIN_KUBECONFIG \
  --context=DIRECT_ADMIN_CONTEXT
~~~

Trước tiên tạo role `team-a/workload-reader` bằng quyền admin trực tiếp và kiểm tra YAML đầu ra. Sau khi review subject, namespace và permission, quản trị viên có thể chạy lại với flag `--apply`. Đây là thao tác bootstrap **làm thay đổi RBAC cluster**, không nên chạy bằng người dùng chỉ có quyền đọc và không nên cấp `clusterrole/cluster-admin` chỉ để “cho thử nhanh”.

Đường dẫn kubeconfig và context ở lệnh bootstrap phải trỏ tới **direct admin connection của đúng cluster**, không nhầm với một context gateway ở cluster khác. Có thể chạy `kubectl config current-context` và `kubectl get ns --context=DIRECT_ADMIN_CONTEXT` để xác nhận trước, nhưng chỉ dùng khi người vận hành đã được ủy quyền.

Lệnh generate-gateway-rbac và các tùy chọn có thể thay đổi; luôn xem help của Google Cloud CLI đang dùng. Với tổ chức quản lý RBAC qua GitOps, có thể review và áp dụng YAML qua pipeline được bảo vệ thay vì chỉnh tay.

## 9. Truy cập một fleet membership bằng kubectl

### 9.1. Đăng nhập gcloud

Operator đăng nhập bằng danh tính Google Cloud được cấp IAM role:

~~~bash
gcloud auth login
gcloud config set project FLEET_PROJECT_ID
~~~

Nếu dùng Workforce Identity Federation, làm theo luồng đăng nhập của provider. Không lưu access token, kubeconfig chứa credential hoặc file key vào source control.

### 9.2. Lấy gateway kubeconfig

~~~bash
gcloud container fleet memberships list \
  --project=FLEET_PROJECT_ID

gcloud container fleet memberships get-credentials onprem-hanoi \
  --project=FLEET_PROJECT_ID \
  --location=global
~~~

Cần thay `global` bằng location thực tế của membership. Lệnh `get-credentials` cấu hình `kubeconfig` để client gửi request qua gateway, đồng thời có thể **đổi current context**. Hãy xem `kubectl config get-contexts` và xác nhận context sau khi chạy.

Dùng biến môi trường `KUBECONFIG` trỏ tới một file riêng khi làm việc với nhiều cluster để tránh vô tình thay đổi context quản trị đang dùng. Không sửa thủ công server URL trong gateway kubeconfig; hãy tạo lại bằng phiên bản gcloud CLI mới khi cần.

### 9.3. Chạy lệnh chỉ đọc

~~~bash
kubectl config current-context
kubectl get pods -n team-a
kubectl get deployments -n team-a
kubectl auth can-i get pods -n team-a
kubectl auth can-i delete deployments -n team-a
~~~

Với role chỉ đọc ở `team-a`, kết quả mong muốn là được xem pod/deployment trong namespace đó và **không được xóa deployment**. Lệnh `kubectl get namespaces` có thể thất bại nếu operator không có quyền list resource cluster-scoped; đó có thể là hành vi RBAC đúng chứ không phải gateway lỗi.

Không dùng `kubectl apply`, `delete`, `rollout restart` hoặc `patch` trong bài kiểm thử đọc. Với production, ghi nhận change ticket trước những thao tác sửa.

### 9.4. Kiểm tra context và location

Khi quản lý nhiều fleet memberships, thao tác nhầm context có thể ảnh hưởng cluster khác. Luôn kiểm tra:

- Fleet host project đang chọn.
- Membership name và location.
- Kubeconfig file được dùng.
- `kubectl config current-context`.
- Namespace đang thao tác.
- Identity cuối cùng và role RBAC thực tế.

Ưu tiên script có bước kiểm tra project, context và namespace, đặc biệt trước thao tác có side effect.

## 10. Dùng service account impersonation cho automation

Một pipeline CI/CD không nên phụ thuộc vào quyền Google Cloud cá nhân của developer. Nên tạo service account riêng cho thao tác đọc hoặc triển khai qua gateway.

Ví dụ dùng cấu hình impersonation tạm thời trong gcloud:

~~~bash
gcloud config set auth/impersonate_service_account \
  fleet-deployer@FLEET_PROJECT_ID.iam.gserviceaccount.com

gcloud container fleet memberships get-credentials onprem-hanoi \
  --project=FLEET_PROJECT_ID \
  --location=global
~~~

Người hoặc workload nguồn phải có quyền impersonate service account phù hợp (ví dụ Token Creator trong luồng dùng impersonation). Service account đích cũng phải có IAM role gateway, viewer membership và Kubernetes RBAC trên cluster. **Quyền impersonate một service account không tự cấp quyền Kubernetes.**

Sau khi thao tác, dùng cấu hình gcloud tách biệt hoặc bỏ impersonation để tránh các lệnh sau vô tình tiếp tục mượn danh tính:

~~~bash
gcloud config unset auth/impersonate_service_account
~~~

Trong external CI như GitHub Actions, ưu tiên Workload Identity Federation để lấy credential ngắn hạn, không lưu service account JSON key lâu dài. Job triển khai chỉ nên có quyền vào membership và namespace thuộc môi trường đích. Tách pipeline staging và production bằng identity và approval riêng.

## 11. Google Groups và danh tính từ nhà cung cấp bên ngoài

### 11.1. Quản trị truy cập bằng nhóm

Khi số operator tăng, gắn IAM và RBAC cho từng email khó duy trì. Có thể dùng Google Groups kết hợp GKE Identity Service và khả năng group support của Connect Gateway để ủy quyền theo nhóm trong **những môi trường được hỗ trợ**.

Quy trình ở mức khái niệm:

1. Tổ chức duy trì nhóm SRE hoặc application team trong hệ thống danh tính.
2. Quản trị viên cấu hình group support cho loại cluster tương ứng.
3. IAM gateway roles được cấp cho group hoặc principal set.
4. Kubernetes RBAC bindings tham chiếu tên group đã được cluster authentication component hỗ trợ.
5. Kiểm tra thành viên mới được cấp quyền và người rời nhóm thực sự mất quyền.
6. Theo dõi giới hạn kích thước claim/group membership và log xác thực.

Không giả định mọi attached cluster và phiên bản GKE đều hỗ trợ Google Groups giống nhau; tra tài liệu setup groups cho loại cluster thực tế và lưu ý giới hạn/điều kiện hỗ trợ.

### 11.2. Third-party workforce identities

Doanh nghiệp có thể dùng Microsoft Entra ID, Okta hoặc OIDC/SAML identity provider khác thông qua **Workforce Identity Federation** để người dùng đăng nhập và được cấp IAM permission trên Google Cloud. Điều này khác **Workload Identity Federation** dành cho ứng dụng/workload không phải con người.

Khi dùng third-party identity:

- Ánh xạ subject/group claims chính xác.
- Dùng attribute condition để giới hạn identity provider/trust.
- Cấp gateway IAM role cho workforce principal/principal set có scope đúng.
- Thiết lập phía Kubernetes để nhận diện subject và group phù hợp.
- Kiểm tra revocation, token expiry, audit và giới hạn header/claim.
- Không sao chép syntax Google user email trực tiếp vào RBAC cho principal federated nếu tài liệu yêu cầu định dạng khác.

## 12. Streaming commands: exec, attach, cp và port-forward

Một số lệnh `kubectl` tạo luồng kết nối kéo dài, khác với request GET/LIST thông thường:

- `kubectl exec`: chạy command trong container.
- `kubectl attach`: nối tới tiến trình đang chạy.
- `kubectl cp`: truyền file qua cơ chế tương ứng.
- `kubectl port-forward`: tạo tunnel tới port của pod/service qua Kubernetes API.

Connect Gateway có các điều kiện bổ sung cho loại lệnh này:

1. Cần IAM permission `gkehub.gateway.stream`; predefined role có permission này là `roles/gkehub.gatewayAdmin`.
2. Cần Kubernetes RBAC cho subresource `pods/exec`, `pods/attach` hoặc `pods/portforward` theo lệnh sử dụng.
3. Theo hướng dẫn gateway hiện hành, cluster phải đạt Kubernetes **1.30 trở lên** đối với `attach`/`cp`/`exec` và **1.31 trở lên** với `port-forward`; `kubectl` client cần **1.31 trở lên**.
4. Các quyền streaming nên được cấp cho nhóm break-glass/điều tra có approval, không cấp mặc định cho mọi người đọc pod.

Một user có thể `kubectl get pods` thành công nhưng `kubectl exec` thất bại vì thiếu quyền stream, thiếu RBAC trên subresource hoặc phiên bản không đáp ứng. Đó không nhất thiết là lỗi mạng.

Không chạy `exec` vào workload sản xuất để lấy secret, dump environment hoặc xem dữ liệu nhạy cảm khi chưa có authorization và quy trình kiểm soát phù hợp.

## 13. Tích hợp với CI/CD và GitOps

### 13.1. Mô hình pipeline

Connect Gateway có thể hỗ trợ hệ thống tự động hóa dùng kubeconfig để kiểm tra trạng thái hoặc triển khai manifest lên cluster thuộc fleet. Một pipeline có thể triển khai cùng loại workload lên GKE, on-premises và attached clusters bằng những context khác nhau.

~~~mermaid
flowchart LR
    SRC[Git commit đã review] --> CI[Build + test]
    CI --> ART[Artifact Registry image digest]
    ART --> CD[Approval / deploy job]
    CD --> ID[CI service account]
    ID --> GW[Connect Gateway]
    GW --> S[Staging fleet membership]
    GW --> P[Production fleet membership]
    S --> V[Smoke / readiness verification]
    P --> MON[Monitoring + rollback]
~~~

Tách service account cho các môi trường và không cho pipeline pull request chưa tin cậy nhận quyền gateway production. Nếu đang dùng Cloud Deploy với GKE attached clusters, hãy tham khảo hướng dẫn dành cho **attached targets**, vì service account dùng để thực thi rollout phải được cấu hình IAM/RBAC phù hợp ở cluster đích.

### 13.2. Các bước vận hành an toàn

Một luồng triển khai có kiểm soát:

1. Build image một lần và lưu theo digest bất biến.
2. Scan, kiểm thử và ghi nhận provenance.
3. Pipeline được phê duyệt nhận credential ngắn hạn cho service account deploy.
4. Lấy kubeconfig gateway của membership staging.
5. Triển khai và kiểm tra readiness/rollout trên namespace được phép.
6. Chạy smoke test.
7. Promotion production sau approval, dùng lại cùng image digest.
8. Theo dõi SLO, error rate và latency; dừng hoặc rollback khi xuất hiện regression.

Không nhúng kubeconfig dài hạn vào repository. Nếu job tạm thời sinh kubeconfig, chỉ giữ trong workspace ephemeral và xóa sau khi hoàn thành. Kubeconfig mô tả endpoint/credential helper; dù không chứa private key tĩnh, nó vẫn có thể tiết lộ endpoint và context của cluster.

### 13.3. Ranh giới giữa quyền deploy và quản trị cluster

Deployment job chỉ cần quyền thao tác Deployment, Service, ConfigMap hoặc tài nguyên cụ thể trong namespace. Không cấp `cluster-admin` nếu chỉ cần cập nhật image. Những thay đổi ClusterRole, CRD, admission webhook, namespace, node và networking thường cần pipeline nền tảng với approval khác.

Dùng RBAC và policy as code để kiểm tra drift; không để CI tự cấp cho mình quyền cao hơn tại thời điểm deploy.

## 14. Bảo mật và kiểm soát rủi ro

### 14.1. Defense in depth

Một thiết kế tốt kiểm soát từng lớp:

| Lớp | Kiểm soát nên có |
|---|---|
| Identity | MFA hoặc federation, credential ngắn hạn, quản lý vòng đời tài khoản |
| Fleet inventory | Membership được đặt tên rõ, quản lý project và ownership |
| IAM | Gateway Reader/Editor/Admin phù hợp, viewer membership, periodic access review |
| Agent/connection | Cấu hình egress, TLS, service identity, health monitoring |
| Kubernetes RBAC | Role theo namespace, không cấp cluster-admin tùy tiện |
| Workload runtime | NetworkPolicy, Pod Security, secret handling, namespace isolation |
| Change management | GitOps/review, approval, tách CI và CD, audit |
| Incident response | Break-glass path, thu hồi IAM/RBAC, log, phương án restore |

Connect Gateway chỉ bảo vệ con đường truy cập qua gateway. Nó không tự động chặn tất cả đường truy cập trực tiếp tới Kubernetes API server. Nếu vẫn có kubeconfig tĩnh hoặc endpoint public, cần kiểm soát các con đường đó độc lập.

### 14.2. Nguyên tắc quyền tối thiểu

Ví dụ nhóm SRE chỉ đọc namespace `team-a`:

- Google Cloud IAM: gatewayReader + gkehub.viewer.
- Kubernetes RBAC: Role đọc pods/deployments trong namespace `team-a`.
- Agent impersonation: cấu hình cho end user theo hướng dẫn nếu cần.
- Không cấp `cluster-admin`, không cấp quyền tạo Secret, không cấp streaming nếu không có nhu cầu.

Ví dụ nhóm phát hành ứng dụng:

- IAM: gatewayEditor + viewer (hoặc quyền hẹp hơn phù hợp).
- RBAC: cập nhật Deployment và xem trạng thái trong namespace được phân công.
- Approval: tách production và staging.
- Không được sửa RBAC, CRD hoặc cluster-scoped resources nếu không có ủy quyền.

Một principal được IAM cho phép update vẫn có thể bị Kubernetes RBAC chặn nếu thiếu verb `patch` hoặc `update`; đây là hành vi mong muốn của hai lớp phân quyền.

### 14.3. Audit và dữ liệu nhạy cảm

Nên theo dõi:

- Cloud Audit Logs cho hoạt động liên quan đến gateway, IAM và fleet membership theo khả năng logging của dịch vụ.
- Kubernetes API server audit logs cho actor, verb, resource, namespace và kết quả.
- Log của Connect Agent/Identity Service khi có vấn đề forwarding hoặc xác thực.
- Lịch sử điều chỉnh IAM và RBAC, ticket/commit đã phê duyệt.
- Login/impersonation từ tài khoản người dùng, service account và workforce identities.

Tránh ghi access token, kubeconfig chứa thông tin nhạy cảm, credential provider response hoặc secret payload vào log. Khi cần debug `kubectl -v`, kiểm soát quyền xem log và xóa dữ liệu nhạy cảm trước khi chia sẻ.

## 15. Xử lý lỗi theo từng lớp

Khi `kubectl` không thể truy cập cluster qua gateway, cần khoanh vùng theo thứ tự từ ngoài vào trong thay vì ngay lập tức cấp quyền rộng hơn.

### 15.1. Quy trình chẩn đoán

~~~mermaid
flowchart TD
    A[kubectl qua gateway lỗi] --> B{Membership có trong fleet?}
    B -- Không --> C[Kiểm tra project, location, registration]
    B -- Có --> D{gcloud auth và IAM đúng?}
    D -- Không --> E[Kiểm tra user/SA, gateway role, viewer]
    D -- Có --> F{Kubeconfig gateway đúng?}
    F -- Không --> G[Regenerate get-credentials, check context]
    F -- Có --> H{Cluster reachable?}
    H -- Không --> I[Check Connect Agent / egress / DNS / API server]
    H -- Có --> J{RBAC và impersonation đúng?}
    J -- Không --> K[Check gateway impersonation RBAC + user RoleBinding]
    J -- Có --> L[Check resource, namespace, version, streaming permissions]
~~~

### 15.2. Bảng tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không thấy membership | Sai project/location hoặc chưa đăng ký fleet | `gcloud container fleet memberships list` và membership metadata |
| `get-credentials` bị từ chối | Thiếu role gateway/`gkehub.viewer` hoặc đăng nhập nhầm | Kiểm tra gcloud account, project, IAM bindings |
| Kubeconfig trỏ sai gateway endpoint | CLI cũ hoặc context cũ | Cập nhật CLI và chạy lại `get-credentials`; không sửa tay |
| Không có active connections | Agent mất kết nối hoặc chưa cài trên cluster ngoài GCP | Kiểm tra namespace `gke-connect`, pod/log, DNS/egress |
| `Forbidden` từ Kubernetes API | User thiếu RoleBinding hoặc agent không được impersonate | Kiểm tra hai loại RBAC policy |
| Xem pod được nhưng xem node không được | Role namespace-only, node là cluster-scoped | Đây có thể là phân quyền đúng; không tự cấp ClusterRole |
| `exec`/`port-forward` bị chặn | Thiếu stream permission/RBAC hoặc phiên bản thấp | Kiểm tra IAM role, subresource RBAC và kubectl/K8s version |
| Danh tính group không được nhận | Group support chưa cấu hình hoặc claim sai | Kiểm tra Identity Service, groups, federation mapping |
| Kết nối thành công nhưng lệnh chậm | Network/agent/API server quá tải, client timeout | Theo dõi latency, agent logs, API server health |
| Lỗi plugin xác thực | `gke-gcloud-auth-plugin` thiếu hoặc CLI không tương thích | Cài plugin, cập nhật CLI, sinh lại kubeconfig |

### 15.3. Đọc log agent đúng nơi

Với non-GKE cluster mà Connect Agent bị lỗi, kiểm tra workload `gke-connect` qua **kubeconfig quản trị trực tiếp** (nếu gateway đang mất kết nối). Kiểm tra pod status, restart, events, DNS, proxy và egress. Không dùng một lệnh `kubectl` qua gateway đang lỗi để chẩn đoán chính gateway mà bỏ qua phương án truy cập trực tiếp.

Với GKE cluster kết nối trực tiếp, ưu tiên kiểm tra membership, IAM, kubeconfig và control plane thay vì cố tìm agent không bắt buộc.

### 15.4. Phân biệt 401, 403 và kết nối đứt

- **401/unauthenticated:** token, login, credential helper hoặc identity provider.
- **403 ở gateway:** không đủ IAM permission để gọi gateway API.
- **403 từ Kubernetes:** RBAC user hoặc impersonation policy không cho phép.
- **Network/connection error:** membership chưa connected, Connect Agent mất egress, control plane không khỏe hoặc gateway path bị chặn.
- **404/resource not found:** có thể sai membership, namespace, resource name hoặc endpoint; xác minh request tới cluster nào trước.

Thông báo lỗi có thể khác nhau giữa phiên bản CLI/API; dùng response source, audit và log để xác định lớp bị chặn. Không chữa mọi lỗi bằng `roles/owner` hay `cluster-admin`.

## 16. Reliability, availability và kế hoạch break-glass

Gateway là một dependency trong đường quản trị Kubernetes. Nếu Google Cloud API, identity provider, DNS, Internet egress hoặc Connect Agent gián đoạn, operator có thể tạm thời không truy cập được qua gateway ngay cả khi workload trong cluster vẫn chạy bình thường.

Nên có:

- Phương án quản trị trực tiếp với quyền giới hạn, được kiểm soát và audit khi gateway không khả dụng.
- Runbook riêng cho cluster GKE trên Google Cloud và cluster ngoài Google Cloud.
- Theo dõi trạng thái Connect Agent, membership và latency của API.
- Credential rotation và quy trình cấp quyền khẩn cấp có thời hạn.
- Kiểm thử mất kết nối egress, identity provider outage và khôi phục agent.
- Phân loại incident: sự cố control plane, gateway, IAM hay ứng dụng.
- Không yêu cầu luồng ứng dụng business-critical phụ thuộc vào Connect Gateway để trao đổi dữ liệu thời gian thực.

Không giả định việc bật gateway tự cải thiện data-plane availability hoặc tự thực hiện cluster failover. Nó cung cấp lối quản trị nhất quán; chiến lược DR/HA của workload phải được thiết kế riêng.

## 17. Tình huống thực hành: GKE và cluster EKS cùng fleet

Một công ty có:

- `gke-prod`: GKE trên Google Cloud.
- `eks-orders`: cluster Amazon EKS được đăng ký vào fleet.
- `onprem-reporting`: Kubernetes tại trung tâm dữ liệu.
- Nhóm SRE cần đọc pods/deployments; nhóm platform có quyền quản trị; pipeline release cần cập nhật deployment trong namespace `orders`.

### 17.1. Thiết kế

1. Fleet host project chứa membership cho ba cluster.
2. Xác định cluster nào dùng Connect Agent và yêu cầu network egress tương ứng.
3. Nhóm SRE nhận IAM gatewayReader và gkehub.viewer; Kubernetes RBAC read-only tại những namespace cần xem.
4. Nhóm platform giữ quyền bootstrap IAM/RBAC và xử lý sự cố; không cấp quyền này cho tất cả developer.
5. Pipeline deploy dùng service account riêng và token ngắn hạn, gateway access chỉ cho membership môi trường đích.
6. Cluster ngoài GCP có impersonation policy cho agent và RoleBinding cho identity cuối.
7. Việc triển khai production có approval; sử dụng cùng image digest đã qua staging.
8. Quan sát Cloud Audit Logs, Kubernetes API audit, agent health và SLO ứng dụng.

### 17.2. Các bước kiểm chứng

Trong môi trường thử nghiệm được cho phép:

~~~bash
gcloud container fleet memberships list --project=FLEET_PROJECT_ID

gcloud container fleet memberships get-credentials eks-orders \
  --project=FLEET_PROJECT_ID \
  --location=MEMBERSHIP_LOCATION

kubectl config current-context
kubectl get pods -n orders
kubectl auth can-i get pods -n orders
kubectl auth can-i delete pods -n orders
~~~

Kết quả mong đợi cho SRE chỉ đọc:

- Membership xuất hiện trong inventory.
- Gateway kubeconfig tạo đúng context.
- Có thể đọc pod trong namespace được cấp quyền.
- Không được xóa pod hoặc thay đổi Deployment.
- Audit cho thấy identity và thao tác tương ứng.
- Khi thu hồi IAM gateway role hoặc Kubernetes RoleBinding, access bị từ chối tại lớp tương ứng.

Lưu ý không thực hiện thay đổi/thu hồi quyền trên production như một bài thử tự phát. Dùng sandbox cluster và tài khoản test riêng; có runbook phục hồi quyền nếu thử nghiệm ảnh hưởng truy cập.

### 17.3. Bài học rút ra

Một đội có thể thống nhất **cách kết nối và danh tính**, nhưng vẫn cần bảo vệ ranh giới Kubernetes của từng cluster. Fleet/Gateway không có nghĩa mọi cluster có cùng quyền hoặc cùng đặc điểm runtime. Phân quyền cần theo môi trường, namespace, trách nhiệm và mức độ rủi ro.

## 18. Checklist vận hành trước production

### Fleet và hạ tầng

- [ ] Cluster đã đăng ký đúng fleet host project, membership name/location được xác minh.
- [ ] Đã phân loại GKE trên Google Cloud với attached/on-prem/external clusters.
- [ ] Connect Agent được cài đúng nơi cần và có network egress phù hợp.
- [ ] API cần thiết được bật; CLI/kubectl/auth plugin có phiên bản tương thích.
- [ ] Có quản lý ownership, tài liệu runbook và break-glass path.

### IAM, authentication và RBAC

- [ ] Gateway IAM role được cấp theo nguyên tắc quyền tối thiểu.
- [ ] Có quyền viewer để khám phá membership khi cần.
- [ ] Agent impersonation policy được cấu hình cho cluster cần agent.
- [ ] Kubernetes Role/RoleBinding theo namespace và resource thực sự cần.
- [ ] Không dùng cluster-admin nếu workload/operator chỉ cần quyền đọc.
- [ ] Các group/third-party identity đã được kiểm thử end-to-end nếu sử dụng.
- [ ] Đã kiểm tra thu hồi quyền IAM và RBAC hoạt động như thiết kế.
- [ ] Không lưu token/key/kubeconfig nhạy cảm trong Git.

### Access và CI/CD

- [ ] Gateway kubeconfig được tạo từ đúng membership và location.
- [ ] Mọi thao tác ghi kiểm tra project/context/namespace trước.
- [ ] CI/CD dùng service account riêng và credential ngắn hạn.
- [ ] Production deploy có approval và quyền namespace hẹp.
- [ ] Streaming commands chỉ được cấp khi có nhu cầu và đáp ứng phiên bản.
- [ ] Audit logs của gateway và cluster có retention phù hợp.

### Reliability và bảo mật

- [ ] Có dashboard/alert cho Connect Agent, gateway access failure và API server health.
- [ ] Có kế hoạch ứng phó khi gateway/identity provider hoặc egress gặp sự cố.
- [ ] Không coi gateway thay thế VPN/service mesh/data-plane network.
- [ ] Đã kiểm thử đường quản trị khẩn cấp và quyền của operator chịu trách nhiệm.
- [ ] Có quy trình định kỳ rà soát IAM, RBAC và membership không còn sử dụng.

## 19. Câu hỏi tự kiểm tra

1. Fleet khác Kubernetes cluster và membership như thế nào?
2. Vì sao Connect Gateway không phải một Kubernetes API server chung cho toàn bộ fleet?
3. Đường đi của request khác nhau ra sao giữa GKE trên Google Cloud và cluster ngoài Google Cloud?
4. Vì sao người dùng đã có gatewayReader vẫn có thể bị `Forbidden` khi đọc pod?
5. Connect Agent cần impersonation policy để làm gì? Điều đó có đồng nghĩa người dùng được cấp cluster-admin không?
6. Vì sao `kubectl get namespaces` có thể thất bại dù `kubectl get pods -n team-a` thành công?
7. Khi nào cần `roles/gkehub.gatewayAdmin` thay vì gatewayReader/Editor?
8. Làm thế nào bảo đảm lệnh `kubectl` không vô tình thao tác vào cluster khác?
9. Vì sao nhóm SRE chỉ đọc không nên được cấp quyền streaming mặc định?
10. Connect Gateway có thay thế VPN, Interconnect hoặc service mesh cho workload traffic không?
11. Nếu EKS cluster mất kết nối Connect Agent, cần kiểm tra những thành phần nào?
12. Một pipeline deploy qua gateway nên dùng service account, IAM và Kubernetes RBAC ra sao?
13. Vì sao cần đường quản trị break-glass khi gateway hoặc identity provider không khả dụng?
14. Khi nào group-based RBAC và Workforce Identity Federation cần cấu hình bổ sung?

## Tài liệu tham khảo

- [Connect to registered clusters with the Connect gateway](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway)
- [Set up the Connect gateway](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/setup)
- [Using the Connect gateway](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/using)
- [Set up the Connect gateway with Google Groups](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/setup-groups)
- [Set up the Connect gateway with third-party identities](https://docs.cloud.google.com/kubernetes-engine/enterprise/multicluster-management/gateway/setup-third-party)
- [gcloud container fleet memberships get-credentials](https://docs.cloud.google.com/sdk/gcloud/reference/container/fleet/memberships/get-credentials)
- [GKE attached clusters overview](https://docs.cloud.google.com/kubernetes-engine/multi-cloud/docs/attached/eks/concepts/overview)
- [Cloud Deploy to GKE attached clusters](https://docs.cloud.google.com/deploy/docs/anthos-targets)
- [Kubernetes RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)

