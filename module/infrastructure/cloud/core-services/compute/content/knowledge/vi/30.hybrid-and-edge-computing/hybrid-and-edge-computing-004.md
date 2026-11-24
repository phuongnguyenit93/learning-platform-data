# Quản lý danh tính, cấu hình và chính sách trên các cụm phân tán

Một hệ thống hybrid và edge thường có nhiều cụm Kubernetes hoặc container cluster ở các region, datacenter, nhà máy, cửa hàng và điểm biên. Các cụm cần dùng chung chuẩn bảo mật và cấu hình nền tảng, nhưng vẫn phải hoạt động khi kết nối WAN không ổn định hoặc trung tâm quản lý tạm thời không truy cập được. Nếu mỗi cụm tự tạo danh tính, lưu secret và áp dụng policy theo cách riêng, tổ chức sẽ khó kiểm soát quyền truy cập, phát hiện cấu hình lệch và chứng minh tuân thủ.

**Quản lý danh tính đa cụm** xác định người dùng, workload, node và cluster nào được phép xác thực hoặc truy cập tài nguyên. **Quản lý cấu hình đa cụm** phân phối cấu hình mong muốn đến từng cluster và theo dõi trạng thái thực tế. **Quản lý chính sách đa cụm** đặt ra các quy tắc bảo mật, network, tài nguyên và vận hành được áp dụng nhất quán trên toàn fleet.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, cần thiết kế một mô hình quản trị vừa có chuẩn chung vừa cho phép mỗi site xử lý công việc cục bộ. Control plane trung tâm có thể quản lý đăng ký cluster, danh tính, cấu hình và policy; từng cluster vẫn cần cơ chế xác thực, cache cấu hình cần thiết, lưu state và thực thi policy tại chỗ để duy trì hoạt động khi bị ngắt kết nối.

## 1. Bài toán quản lý một fleet cluster

Một fleet có thể gồm:

- Cluster trung tâm chạy dịch vụ dùng chung.
- Cluster production theo từng region.
- Cluster tại datacenter hoặc chi nhánh.
- Cluster edge ở nhà máy, cửa hàng hoặc thiết bị gateway.
- Cluster thử nghiệm và môi trường phát triển.
- Cluster do đối tác hoặc đơn vị khác vận hành.

Các cluster có thể khác phiên bản Kubernetes, phần cứng, network, khả năng kết nối và yêu cầu dữ liệu. Vì vậy, quản lý tập trung không có nghĩa mọi cluster phải có cấu hình giống hệt nhau.

### 1.1. Các vấn đề cần giải quyết

| Vấn đề | Hệ quả nếu không quản lý |
| --- | --- |
| Danh tính người dùng không thống nhất | Tài khoản cục bộ tồn tại lâu, khó thu hồi và audit |
| Workload dùng credential dài hạn | Secret bị lộ có thể cho phép truy cập kéo dài |
| Cluster tự cấp quyền tùy ý | Quyền vượt nhu cầu và khó kiểm soát giữa các site |
| Cấu hình phân tán không có version | Các cụm chạy hành vi khác nhau |
| Policy được cập nhật thủ công | Một cụm có thể bỏ sót baseline bảo mật |
| Cluster offline không có policy cache | Workload có thể không tạo được hoặc không được kiểm soát |
| Không theo dõi drift | Cấu hình thực tế lệch khỏi cấu hình được phê duyệt |
| Không có owner rõ ràng | Không biết ai xử lý sự cố hoặc phê duyệt ngoại lệ |

### 1.2. Control plane trung tâm và enforcement tại chỗ

Một kiến trúc phổ biến tách hai vai trò:

- **Central management plane:** quản lý inventory, identity federation, policy bundle, configuration release, audit và trạng thái fleet.
- **Local cluster control plane:** xác thực request, áp dụng RBAC/admission policy, chạy workload, lưu cấu hình đã nhận và tiếp tục hoạt động khi kết nối trung tâm gián đoạn.

~~~mermaid
flowchart TB
    IDP["Enterprise Identity Provider"] --> HUB["Central Fleet Management"]
    GIT["Config and Policy Repository"] --> HUB
    HUB --> REG["Cluster Registry and Audit"]
    HUB --> C1["Region Cluster"]
    HUB --> C2["Datacenter Cluster"]
    HUB --> C3["Edge Cluster"]
    C1 --> W1["Workloads and Local Policy"]
    C2 --> W2["Workloads and Local Policy"]
    C3 --> W3["Workloads and Cached Policy"]
    C3 -. "WAN unavailable" .-> OFF["Local operation with last valid release"]
~~~

Central management plane phân phối trạng thái mong muốn và thu thập kết quả. Cluster cục bộ vẫn cần đủ thành phần để xác thực, thực thi policy và phục vụ workload trong phạm vi được phép.

### 1.3. Phân biệt management plane và workload plane

Management plane chịu trách nhiệm quản trị fleet; workload plane xử lý nghiệp vụ. Nếu mọi request của ứng dụng đều phải đi qua management plane trung tâm, sự cố WAN có thể làm gián đoạn hoạt động edge.

Nên giữ luồng dữ liệu và điều khiển cần thiết tại chỗ:

- API và worker cục bộ gọi dịch vụ nội bộ trong site.
- Admission controller và RBAC thực thi trong cluster.
- Policy bundle đã xác minh được cache cục bộ.
- Telemetry được buffer khi offline rồi chuyển tiếp khi kết nối phục hồi.
- Các thao tác quản trị nhạy cảm có thể yêu cầu kết nối trung tâm hoặc phê duyệt bổ sung.

## 2. Phân loại danh tính trong hệ thống đa cụm

Không nên dùng chung một loại credential cho người vận hành, workload và cluster. Mỗi loại danh tính có vòng đời, quyền và cách xác minh khác nhau.

| Loại danh tính | Chủ thể | Ví dụ |
| --- | --- | --- |
| Human identity | Người dùng hoặc quản trị viên | SRE, platform engineer, auditor |
| Workload identity | Ứng dụng hoặc service account | API, controller, batch worker |
| Cluster identity | Một cluster đã đăng ký | edge-site-017, region-prod-a |
| Node identity | Máy worker hoặc thiết bị edge | node serial, VM instance identity |
| Service identity | Dịch vụ giao tiếp với dịch vụ khác | SPIFFE ID hoặc certificate subject |
| Automation identity | CI/CD, GitOps controller, provisioning agent | deployment pipeline, policy sync agent |

Danh tính cần gắn với owner, environment, scope, thời hạn và trạng thái. Không dùng một tài khoản dùng chung cho toàn fleet vì khi credential bị lộ sẽ khó xác định phạm vi ảnh hưởng và thu hồi riêng.

## 3. Quản lý danh tính người dùng

### 3.1. Dùng identity provider tập trung

Tổ chức thường có enterprise identity provider để quản lý vòng đời nhân sự, nhóm và xác thực đa yếu tố. Cluster có thể tích hợp thông qua OIDC hoặc cơ chế xác thực được nền tảng hỗ trợ.

Luồng cơ bản:

1. Người dùng đăng nhập qua identity provider.
2. Identity provider xác thực, áp dụng MFA và phát token.
3. Kubernetes API hoặc cổng quản trị xác minh token.
4. Group/claim được ánh xạ thành quyền RBAC.
5. Audit ghi lại principal, action, resource, cluster và thời điểm.

Không nên tạo user cục bộ riêng trên từng cluster nếu có thể dùng identity tập trung. Tuy nhiên, cần duy trì quy trình break-glass có kiểm soát cho tình huống identity provider hoặc WAN không khả dụng.

### 3.2. Ánh xạ group sang RBAC

Group trong identity provider có thể được ánh xạ thành role:

- Fleet viewer: xem inventory và trạng thái.
- Cluster operator: quản lý workload trong phạm vi cluster được giao.
- Namespace developer: triển khai ứng dụng trong namespace được cấp.
- Security auditor: đọc policy, audit và compliance evidence.
- Platform administrator: quản lý thành phần nền tảng.

Không cấp cluster-admin cho nhóm developer chỉ vì họ cần triển khai ứng dụng. Hãy dùng Role/RoleBinding theo namespace và ClusterRole/ClusterRoleBinding cho quyền thực sự cần phạm vi cluster.

### 3.3. Ví dụ RBAC giới hạn theo namespace

Manifest sau cấp quyền đọc pod, deployment và xem log trong namespace production-app:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: app-observer
  namespace: production-app
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log", "services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: app-observer-binding
  namespace: production-app
subjects:
  - kind: Group
    name: platform-observers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: app-observer
  apiGroup: rbac.authorization.k8s.io
~~~

Group name trong ví dụ phải khớp với username/group claim mà API server nhận được sau khi cấu hình OIDC. RBAC chỉ phân quyền; nó không tự xác thực người dùng hoặc kiểm tra MFA.

### 3.4. Just-in-time access và break-glass

Quyền quản trị cao nên được cấp theo thời gian và nhu cầu:

- Người dùng yêu cầu quyền kèm lý do và ticket.
- Hệ thống kiểm tra approval và thời hạn.
- Quyền được cấp trong scope nhỏ nhất.
- Audit ghi lại thời điểm cấp, thao tác và thu hồi.
- Quyền tự hết hạn sau cửa sổ truy cập.

Break-glass là quyền khẩn cấp khi hệ thống xác thực tập trung không dùng được. Credential break-glass phải được bảo vệ riêng, lưu offline hoặc trong vault có kiểm soát, được kiểm kê và thử định kỳ. Mọi lần sử dụng cần alert và review sau sự cố.

## 4. Danh tính workload và service account

Workload identity cho phép pod hoặc container xác thực với database, cloud API, secret manager hoặc dịch vụ nội bộ mà không nhúng access key dài hạn vào image.

### 4.1. Service account riêng cho từng workload

Không nên để mọi pod dùng default service account với quyền rộng. Tạo service account theo ứng dụng hoặc chức năng, sau đó gắn đúng Role/RoleBinding hoặc cơ chế federation.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: production-app
automountServiceAccountToken: false
~~~

Ví dụ này tắt tự động mount Kubernetes API token. Nếu workload cần gọi Kubernetes API hoặc dùng projected token cho workload identity federation, phải cấu hình volume/token audience và thời hạn phù hợp thay vì tắt token mà không có phương án thay thế.

### 4.2. Workload identity federation

Một mô hình phổ biến dùng OIDC issuer của cluster để phát hành token ngắn hạn cho service account. Cloud provider hoặc identity broker tin cậy issuer đó và đổi token lấy credential giới hạn cho workload.

Luồng khái quát:

1. Pod chạy dưới service account riêng.
2. Cluster cấp projected service account token có audience cụ thể.
3. Workload gửi token đến identity endpoint được tin cậy.
4. Identity provider xác minh issuer, signature, subject, audience và thời hạn.
5. Workload nhận credential ngắn hạn với quyền được ánh xạ.
6. Credential được làm mới theo vòng đời, không ghi vào image.

### 4.3. Không chia sẻ trust quá rộng

Mỗi cluster có issuer và trust configuration riêng. Nếu nhiều cluster dùng chung một trust relationship quá rộng, token từ cluster ít bảo vệ hơn có thể được chấp nhận ở tài nguyên production.

Nên giới hạn federation theo:

- Issuer chính xác của cluster.
- Subject/service account cụ thể.
- Audience cụ thể.
- Namespace hoặc workload identity.
- Environment và resource scope.
- Thời hạn token và điều kiện thu hồi.

Không chấp nhận mọi subject từ mọi cluster chỉ vì token được ký bởi một issuer đã tin cậy.

### 4.4. Service-to-service identity

Trong hệ thống phân tán, service có thể xác thực lẫn nhau bằng mTLS và certificate ngắn hạn. SPIFFE/SPIRE là một ví dụ về mô hình định danh workload và cấp SVID/certificate theo trust domain.

Các nguyên tắc:

- Định danh service không phụ thuộc IP hoặc hostname tạm thời.
- Certificate có thời hạn ngắn và tự động rotation.
- Trust bundle được phân phối và cập nhật có kiểm soát.
- Xác minh peer identity và authorization riêng biệt.
- Có quy trình thu hồi hoặc loại bỏ trust khi cluster bị xâm nhập.

TLS mã hóa kênh truyền; authorization vẫn phải xác định service nào được gọi API hoặc tài nguyên nào.

## 5. Danh tính cluster và node

Cluster cần có danh tính ổn định để được đăng ký, nhận cấu hình và gửi telemetry.

### 5.1. Đăng ký cluster

Khi tạo cluster, hệ thống quản lý fleet nên ghi:

- Cluster ID duy nhất.
- Tên và owner.
- Environment: dev, staging, production.
- Site, region và failure domain.
- Provider/platform và mode triển khai.
- Kubernetes version hoặc runtime version.
- Network reachability và kết nối quản trị.
- Trust domain và identity issuer.
- Policy/configuration release hiện tại.
- Ngày tạo, trạng thái và ngày hết hạn credential.

Không dùng tên cluster làm credential. Tên có thể đổi hoặc trùng; cluster ID và cryptographic identity cần được xác minh riêng.

### 5.2. Bootstrap identity

Bootstrap identity là credential dùng để đăng ký cluster lần đầu. Nó cần:

- Có thời hạn ngắn hoặc chỉ dùng một lần.
- Bị giới hạn vào thao tác registration.
- Được lưu trong secret store hoặc quy trình provisioning an toàn.
- Không nhúng vào image node hoặc script công khai.
- Được thay bằng identity thường trực sau khi đăng ký.
- Được thu hồi sau bootstrap.

Nếu một bootstrap token bị lộ, kẻ tấn công có thể đăng ký cluster giả hoặc chiếm quyền quản trị tùy scope. Vì vậy không dùng bootstrap credential như credential vận hành lâu dài.

### 5.3. Node identity

Node cần danh tính để tham gia cluster và lấy certificate/runtime credential. Cần kiểm soát:

- Node registration và authorization.
- Certificate rotation.
- Instance replacement và decommission.
- Node attestation nếu môi trường yêu cầu.
- Không tái sử dụng credential của node đã bị xóa.

Khi node bị mất hoặc nghi ngờ bị xâm nhập, thu hồi identity và certificate, loại node khỏi cluster, kiểm tra workload đã chạy trên node và thay credential liên quan.

## 6. Quản lý certificate và trust bundle

Trong hybrid/edge, certificate có thể dùng cho API server, kubelet, mTLS, ingress, webhook, registry và service-to-service traffic.

### 6.1. Vòng đời certificate

Một quy trình cần có:

1. Cấp certificate từ CA hoặc certificate authority được tin cậy.
2. Gắn certificate với identity và mục đích sử dụng.
3. Theo dõi thời hạn và cảnh báo trước expiry.
4. Rotation tự động trước khi hết hạn.
5. Xác minh certificate mới hoạt động trước khi bỏ certificate cũ.
6. Thu hồi certificate khi identity bị xâm nhập hoặc không còn hợp lệ.

Không nên dùng certificate dài hạn không rotation chỉ vì edge site thường mất kết nối. Thay vào đó, cần thiết kế thời hạn phù hợp, trust bundle được cache và quy trình cấp lại khi kết nối phục hồi.

### 6.2. Trust bundle đa cụm

Các cluster có thể thuộc các trust domain khác nhau. Nếu cần giao tiếp cross-cluster, phân phối trust bundle theo scope và version:

- Cluster A chỉ tin service identity từ domain được phê duyệt.
- Cluster B không tự động tin mọi certificate của fleet.
- Trust bundle có version, checksum/chữ ký và thời điểm hiệu lực.
- Khi CA bị compromise, có thể thu hồi và thay trust root theo quy trình khẩn cấp.

Tránh một root CA dùng chung không giới hạn cho toàn bộ thiết bị edge nếu phạm vi compromise quá lớn. Có thể phân tầng CA theo region, site hoặc security domain.

## 7. Quản lý cấu hình đa cụm

Cấu hình cần được quản lý như một trạng thái mong muốn có version, owner và lịch sử thay đổi. Không nên chỉnh sửa thủ công từng cluster rồi kỳ vọng chúng tự đồng bộ.

### 7.1. Phân tầng cấu hình

Một cấu trúc phân tầng hữu ích:

1. **Organization baseline:** chuẩn chung về bảo mật, logging và identity.
2. **Fleet profile:** cấu hình theo nhóm cluster, ví dụ production hoặc edge.
3. **Region/site profile:** endpoint, network, timezone và storage cục bộ.
4. **Cluster profile:** capacity, add-on và topology riêng.
5. **Workload configuration:** cấu hình của ứng dụng.

Thứ tự kế thừa và quy tắc override phải rõ ràng. Cấu hình nhạy cảm như secret không nên được kế thừa dưới dạng plaintext từ repository.

### 7.2. Cấu hình khai báo và GitOps

GitOps dùng repository làm nguồn trạng thái mong muốn. Controller tại cluster so sánh cấu hình thực tế với revision đã được phê duyệt và reconcile drift.

Luồng thường gặp:

1. Engineer tạo thay đổi cấu hình trong pull request.
2. CI kiểm tra schema, policy, lint và security scan.
3. Người có thẩm quyền review và approve.
4. Repository ghi nhận commit/version bất biến.
5. Fleet controller hoặc GitOps agent phân phối release đến cluster mục tiêu.
6. Agent xác minh, áp dụng và báo trạng thái.
7. Drift được phát hiện và xử lý theo policy.

~~~mermaid
flowchart LR
    DEV["Engineer"] --> PR["Pull request"]
    PR --> CHECK["Validation and policy checks"]
    CHECK --> APPROVE["Approval"]
    APPROVE --> REPO["Versioned config repository"]
    REPO --> HUB["Fleet release controller"]
    HUB --> G1["Region GitOps agent"]
    HUB --> G2["Datacenter agent"]
    HUB --> G3["Edge agent"]
    G1 --> S1["Reconcile and report"]
    G2 --> S2["Reconcile and report"]
    G3 --> S3["Reconcile or use cached release"]
~~~

GitOps không đồng nghĩa mọi thay đổi phải tự động ghi đè trạng thái thực tế. Một số drift cần được cảnh báo hoặc đưa vào quy trình phê duyệt thay vì tự sửa ngay, đặc biệt khi thay đổi thủ công là phản ứng khẩn cấp.

### 7.3. Version hóa và tính bất biến

Mỗi release cấu hình nên có:

- Version hoặc commit ID.
- Danh sách cluster target.
- Digest của bundle.
- Schema version.
- Thời điểm tạo và người phê duyệt.
- Policy compatibility.
- Điều kiện rollout và rollback.

Cluster cần báo chính xác version đang áp dụng. Không dùng tag mutable như latest làm căn cứ duy nhất cho production release.

## 8. Secrets và cấu hình nhạy cảm

Config và secret có vòng đời khác nhau. Config thông thường có thể lưu trong Git; secret cần được quản lý qua secret manager, encryption và access policy.

### 8.1. Nguyên tắc quản lý secret

- Không commit plaintext secret vào repository.
- Không đóng gói secret vào container image.
- Không truyền secret qua label hoặc annotation.
- Hạn chế secret xuất hiện trong log, crash dump và command line.
- Mỗi workload chỉ đọc secret cần thiết.
- Dùng short-lived credential khi có thể.
- Rotation có kiểm thử và có thời gian chuyển tiếp.
- Audit ai đọc hoặc thay đổi secret.

### 8.2. Phân phối secret đến edge

Edge site có thể mất WAN trong một khoảng thời gian. Cần quyết định secret nào được cache tại chỗ và trong bao lâu.

Một chính sách có thể:

- Cache credential ngắn hạn cho hoạt động cục bộ được phép.
- Không cache credential quản trị fleet nếu không cần thiết.
- Mã hóa dữ liệu lưu cục bộ và bảo vệ key bằng TPM/HSM nếu có.
- Đặt expiry và giới hạn quyền offline.
- Khi kết nối phục hồi, refresh credential và kiểm tra trạng thái thu hồi.
- Nếu secret hết hạn trong thời gian offline, chuyển workload sang chế độ an toàn thay vì tiếp tục dùng credential vô thời hạn.

Không có cách rotation trung tâm nào có thể cập nhật ngay một site đang offline. Thiết kế cần xác định rõ thời gian chịu đựng offline và rủi ro của credential còn hiệu lực trong cửa sổ đó.

## 9. Quản lý policy trên nhiều cluster

Policy là quy tắc xác định hành động nào được phép, bị từ chối hoặc cần cảnh báo. Policy có thể áp dụng ở nhiều lớp:

- Identity và authorization.
- Admission control của Kubernetes.
- Image provenance và registry.
- Pod security và Linux capabilities.
- Network ingress/egress.
- Resource quota và limit range.
- Node/region placement.
- Data residency và encryption.
- Logging, audit và retention.

### 9.1. Policy-as-code

Policy-as-code biểu diễn quy tắc bằng cấu hình có thể review, test, version và phân phối tự động. Ví dụ công cụ gồm OPA/Gatekeeper, Kyverno, Kubernetes Pod Security Admission và policy engine riêng của cloud provider.

Một policy tốt cần có:

- Owner và mục tiêu rõ ràng.
- Scope cluster/namespace/workload.
- Mức enforce, warn hoặc audit.
- Lý do từ chối và hướng khắc phục.
- Version và ngày hiệu lực.
- Quy trình exception có expiry.
- Test case cho workload hợp lệ và không hợp lệ.

### 9.2. Enforce, audit và warn

| Mode | Hành vi | Khi dùng |
| --- | --- | --- |
| Audit | Ghi nhận vi phạm nhưng không chặn | Khảo sát baseline và phát hiện tác động |
| Warn | Trả cảnh báo cho người triển khai | Chuyển đổi dần trước khi enforce |
| Enforce | Từ chối tài nguyên không tuân thủ | Quy tắc đã được kiểm thử và cần bắt buộc |

Không bật enforce trên toàn fleet trước khi kiểm tra phiên bản cluster, workload cũ, webhook availability và các ngoại lệ cần thiết. Một policy sai có thể chặn rollout hoặc làm hệ thống không tạo được workload mới.

### 9.3. Fail-open và fail-closed

Admission webhook có thể được cấu hình theo cách xử lý khi webhook không truy cập được:

- **Fail-closed:** request bị từ chối nếu không kiểm tra được policy. Bảo vệ chặt hơn nhưng có thể ảnh hưởng availability khi policy service lỗi.
- **Fail-open:** request có thể tiếp tục nếu webhook không phản hồi. Tăng khả năng sẵn sàng nhưng có thể bỏ qua kiểm soát.

Lựa chọn phụ thuộc rủi ro của policy. Với quy tắc bảo vệ ranh giới bảo mật quan trọng, fail-closed có thể phù hợp; với policy tư vấn hoặc không thiết yếu, có thể cân nhắc fail-open kèm audit. Cần có timeout ngắn, HA và giám sát webhook.

## 10. Policy baseline và ngoại lệ

Một baseline fleet có thể gồm:

- Chỉ cho phép image từ registry được phê duyệt.
- Yêu cầu image được scan hoặc ký theo policy.
- Chặn privileged container và host namespace nếu không có exception.
- Yêu cầu resource requests/limits.
- Giới hạn hostPath và volume type.
- Yêu cầu non-root và drop capabilities.
- Kiểm soát ingress/egress.
- Yêu cầu audit và log retention.
- Giới hạn region, zone hoặc node pool.
- Yêu cầu workload identity thay cho static key.

### 10.1. Phân tầng policy

Không phải mọi cluster có cùng yêu cầu. Ví dụ:

- Production có thể enforce image signature và network segmentation.
- Development có thể cho phép debug image trong namespace riêng.
- Edge offline có thể cần cache registry và policy bundle đã ký.
- Cluster xử lý dữ liệu nhạy cảm có thể cần region pinning và encryption bắt buộc.

Baseline tổ chức vẫn là lớp tối thiểu. Profile riêng chỉ được nới lỏng quy tắc khi có phê duyệt và lý do.

### 10.2. Exception có kiểm soát

Ngoại lệ cần có:

- Policy được miễn.
- Resource/namespace/cluster cụ thể.
- Owner chịu trách nhiệm.
- Lý do nghiệp vụ và rủi ro.
- Người phê duyệt.
- Ngày hết hạn.
- Biện pháp bù.
- Audit và lịch review.

Không tạo wildcard exception cho toàn fleet chỉ để một workload triển khai thành công. Exception không có expiry dễ trở thành policy vĩnh viễn ngoài kiểm soát.

## 11. Drift detection và reconciliation

Drift là khác biệt giữa cấu hình mong muốn đã phê duyệt và trạng thái thực tế tại cluster.

Nguyên nhân:

- Người vận hành chỉnh sửa trực tiếp.
- Controller khác thay đổi resource.
- Cluster offline và bỏ lỡ release.
- API version hoặc default behavior thay đổi sau upgrade.
- Policy bị sửa hoặc bị disable.
- Secret/certificate rotation chưa hoàn tất.

### 11.1. Phân loại drift

| Loại drift | Ví dụ | Hành động |
| --- | --- | --- |
| Benign | Field được API server default | Chuẩn hóa trước khi so sánh |
| Operational | Replica count thay đổi bởi HPA | Loại field động khỏi so sánh desired state |
| Unauthorized | RBAC binding được cấp thủ công | Alert, rollback hoặc yêu cầu review |
| Security-critical | Privileged pod xuất hiện | Chặn, cô lập hoặc remediation theo runbook |
| Connectivity | Cluster chưa nhận release mới | Giữ last-known-good và báo trạng thái stale |
| Version drift | Cluster chưa upgrade theo baseline | Lập lịch rollout hoặc đánh giá compatibility |

Không nên tự động reconcile mọi field. HPA, controller và operator có thể quản lý field riêng; GitOps cần tránh tranh chấp ownership và vòng lặp ghi đè.

### 11.2. Drift remediation

Có ba hướng:

- **Notify-only:** báo drift để owner xử lý.
- **Reconcile:** đưa resource về trạng thái mong muốn.
- **Quarantine:** ngăn workload hoặc cluster tham gia traffic/quản trị nhạy cảm khi drift nghiêm trọng.

Chọn hành động theo mức độ rủi ro. Với thay đổi quyền admin ngoài dự kiến, cần ưu tiên containment và audit. Với cấu hình không quan trọng, cảnh báo có thể đủ.

## 12. Quản lý cụm edge khi mất kết nối

Edge cluster thường có băng thông hạn chế, độ trễ cao và có thể mất kết nối trung tâm. Quản lý danh tính, cấu hình và policy phải hỗ trợ chế độ hoạt động offline có giới hạn.

### 12.1. Local autonomy

Khi WAN mất:

- Workload cục bộ tiếp tục phục vụ trong phạm vi được phép.
- Local control plane tiếp tục thực thi RBAC và admission policy đã cài.
- GitOps agent giữ release cuối cùng đã xác minh.
- Telemetry được buffer và gửi lại khi kết nối phục hồi.
- Các thao tác yêu cầu identity provider trung tâm có thể bị hạn chế.
- Không nhận bundle hoặc certificate chưa xác minh chữ ký.

### 12.2. Last-known-good configuration

Cluster nên lưu một release cấu hình và policy cuối cùng đã xác minh. Khi nhận release mới:

1. Kiểm tra chữ ký và digest.
2. Xác minh version/schema tương thích.
3. Kiểm tra policy và dependency.
4. Áp dụng vào staging hoặc nhóm tài nguyên thử nếu có.
5. Health check và đánh giá kết quả.
6. Đánh dấu release mới là active chỉ sau khi thành công.
7. Giữ bản trước để rollback.

Nếu rollout lỗi, cluster quay lại last-known-good theo quy trình an toàn. Không xóa release cũ ngay sau khi áp dụng bản mới.

### 12.3. Offline identity

Đối với edge site, xác thực cục bộ có thể dùng credential ngắn hạn đã cấp trước, certificate hoặc cache identity có thời hạn. Cần xác định:

- Ai được phép đăng nhập offline?
- Quyền nào được giữ lại?
- Credential tồn tại tối đa bao lâu?
- Khi nào cần online revalidation?
- Nếu user đã bị disable ở trung tâm nhưng site offline thì hành vi ra sao?

Không thể biết ngay một tài khoản vừa bị thu hồi nếu site không nhận được thông tin mới. Với thao tác nhạy cảm, có thể yêu cầu kết nối trung tâm hoặc dùng credential có thời hạn rất ngắn.

### 12.4. Conflict khi kết nối phục hồi

Trong thời gian offline, local operator có thể đã thực hiện thay đổi khẩn cấp. Khi kết nối trở lại:

- So sánh local state với desired state.
- Phân biệt emergency change được phê duyệt với drift không rõ nguồn.
- Không tự động xóa thay đổi có thể ảnh hưởng an toàn vận hành.
- Ghi audit và yêu cầu owner xác nhận nếu có xung đột.
- Reconcile theo thứ tự ưu tiên và version đã quy định.

## 13. Phân phối cấu hình và policy theo rollout ring

Không nên phát hành một policy hoặc cấu hình mới đến tất cả cluster cùng lúc. Một lỗi ở baseline có thể làm mất khả năng triển khai workload trên toàn fleet.

### 13.1. Rollout ring

Một chiến lược có thể chia:

1. Lab/dev cluster.
2. Canary cluster đại diện cho một region/site.
3. Nhóm production ít quan trọng.
4. Production rộng hơn.
5. Edge cluster theo từng nhóm kết nối và phần cứng.

Mỗi ring cần điều kiện promote:

- Agent đã nhận đúng version.
- Policy test pass.
- Không tăng lỗi admission bất thường.
- Workload health không suy giảm.
- Không có drift hoặc credential failure nghiêm trọng.
- Owner chấp thuận với thay đổi rủi ro cao.

### 13.2. Rollback

Rollback policy cần được thiết kế trước:

- Giữ version trước đó và artifact có chữ ký.
- Biết field nào có thể rollback an toàn.
- Không rollback schema/data migration không tương thích.
- Có quy trình khôi phục identity trust nếu CA hoặc issuer thay đổi.
- Có audit cho người kích hoạt rollback.

Một số thay đổi như rotate CA hoặc thu hồi certificate có thể không thể đảo ngược đơn giản. Cần quy trình overlap trust bundle và chuyển đổi theo giai đoạn.

## 14. Audit, compliance và ownership

Quản lý đa cụm cần trả lời được ai thay đổi gì, ở đâu, lúc nào và theo phê duyệt nào.

### 14.1. Audit event

Một audit record nên chứa:

- Actor identity và authentication method.
- Cluster ID và site.
- Resource/namespace.
- Action và kết quả.
- Timestamp đồng bộ.
- Source IP hoặc device context khi phù hợp.
- Change request/approval ID.
- Config/policy release version.
- Correlation ID.

Không ghi access token, private key hoặc secret value vào audit log.

### 14.2. Ownership metadata

Mỗi cluster và workload nên có owner và contact rõ ràng. Metadata hữu ích:

- Business owner.
- Technical owner.
- Environment.
- Cost center.
- Data classification.
- Criticality tier.
- Region/site.
- Policy profile.
- Support window.

Thiếu owner làm chậm xử lý incident và khiến ngoại lệ bảo mật không được review.

### 14.3. Compliance evidence

Có thể thu thập:

- Danh sách cluster và version.
- Policy bundle/version đang active.
- Kết quả compliance scan.
- Danh sách exception và ngày hết hạn.
- RBAC binding và privileged access history.
- Certificate expiry/rotation status.
- Drift report.
- Backup/restore và DR exercise result.

Evidence cần có timestamp, nguồn và trạng thái cập nhật. Báo cáo cũ không chứng minh cluster hiện tại đang tuân thủ.

## 15. Bảo vệ control plane và agent quản lý

Agent quản lý fleet có thể có quyền lớn trong cluster. Nếu agent bị compromise, kẻ tấn công có thể thay đổi policy hoặc triển khai workload trái phép.

Các biện pháp:

- Dùng service account riêng với quyền tối thiểu.
- Tách agent chỉ đọc inventory khỏi agent được phép ghi resource.
- Xác minh chữ ký bundle và source repository.
- Bảo vệ webhook và API endpoint bằng mTLS hoặc identity phù hợp.
- Không mở management API ra Internet nếu không cần.
- Giới hạn egress và inbound.
- Theo dõi version, heartbeat và integrity của agent.
- Có cơ chế revoke cluster identity.
- Tách quyền phê duyệt release khỏi quyền triển khai.

Không để một credential trung tâm không giới hạn có thể quản trị mọi cluster mà không có scope, approval hoặc audit.

## 16. Ví dụ cấu trúc repository cho fleet

Một cấu trúc GitOps có thể phân tách baseline, profile và workload:

~~~text
fleet-config/
  policies/
    baseline/
    production/
    edge/
    exceptions/
  clusters/
    region-a-prod/
      profile.yaml
      workloads/
    datacenter-b/
      profile.yaml
      workloads/
    edge-site-017/
      profile.yaml
      workloads/
  identities/
    trust-bundles/
    service-account-mappings/
  releases/
    release-2026-11/
      manifest.yaml
~~~

Đây là cấu trúc minh họa. Không lưu secret plaintext trong các thư mục này. Có thể lưu reference đến secret manager, encrypted secret manifest hoặc policy về cách lấy secret tại runtime.

### 16.1. Ví dụ cluster profile

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: site-profile
  namespace: fleet-system
data:
  site: edge-site-017
  environment: production
  region: ap-southeast
  policyProfile: edge-restricted-v3
  configRelease: release-2026-11
  offlineMode: "enabled"
~~~

ConfigMap này chỉ chứa metadata không bí mật để minh họa. Một controller có thể dùng label/annotation hoặc custom resource để liên kết cluster với profile. Không coi ConfigMap là nguồn tin cậy để xác thực cluster; danh tính mật mã phải được xác minh riêng.

## 17. Quy trình xử lý khi cluster bị xâm nhập hoặc mất trust

Khi nghi ngờ cluster bị compromise, cần xử lý identity, policy và connectivity cùng nhau:

1. Xác định cluster ID, site, issuer và credential liên quan.
2. Ngừng cấp credential mới cho cluster đó.
3. Thu hồi hoặc giới hạn certificate/token bị nghi ngờ.
4. Cô lập đường quản trị và egress theo incident plan.
5. Giữ lại audit, log và evidence cần điều tra.
6. Đánh giá workload, node, secret và trust bundle bị ảnh hưởng.
7. Tạo lại node/cluster từ artifact tin cậy nếu cần.
8. Cấp cluster identity mới và đăng ký lại.
9. Phân phối policy/config release đã xác minh.
10. Chỉ đưa cluster trở lại fleet sau khi owner/security phê duyệt.

Không chỉ xóa cluster khỏi dashboard rồi xem sự cố đã kết thúc. Credential hoặc trust cũ có thể vẫn được chấp nhận ở hệ thống khác nếu chưa thu hồi.

## 18. Các lỗi thiết kế thường gặp

- Dùng chung cluster-admin hoặc service account cho nhiều workload.
- Dùng credential dài hạn trong image hoặc manifest.
- Trust mọi subject từ mọi cluster trong cùng một issuer.
- Không rotation certificate hoặc không theo dõi expiry.
- Lưu secret plaintext trong Git.
- Không version hóa config và policy bundle.
- Gửi policy mới đến toàn fleet mà không có canary ring.
- Enforce policy chưa được test, làm admission chặn workload hợp lệ.
- Dùng fail-open cho policy bảo mật quan trọng mà không có compensating control.
- Dùng fail-closed cho webhook không HA, gây outage toàn cluster khi webhook lỗi.
- Tự động reconcile field do HPA/operator quản lý, tạo vòng lặp drift.
- Không có last-known-good cho edge offline.
- Cache credential offline vô thời hạn.
- Không có expiry cho exception.
- Không thu hồi trust khi cluster bị decommission hoặc compromise.
- Không có owner, audit và runbook cho từng site.

## 19. Checklist quản lý danh tính, cấu hình và policy

**Identity**

- [ ] Human identity tích hợp IdP, MFA và group mapping.
- [ ] RBAC theo least privilege và scope nhỏ nhất.
- [ ] Workload có service account/identity riêng.
- [ ] Federation giới hạn issuer, subject, audience và resource.
- [ ] Bootstrap credential có thời hạn và được thu hồi sau đăng ký.
- [ ] Certificate rotation và trust bundle có version.
- [ ] Break-glass có owner, audit và expiry.

**Configuration**

- [ ] Cấu hình được phân tầng theo organization/fleet/site/cluster/workload.
- [ ] Desired state có version và approval.
- [ ] GitOps agent reconcile theo ownership rõ ràng.
- [ ] Secret được lưu trong secret manager hoặc cơ chế mã hóa phù hợp.
- [ ] Có drift detection và remediation policy.
- [ ] Edge có last-known-good và local autonomy.

**Policy**

- [ ] Baseline security áp dụng cho toàn fleet.
- [ ] Policy có owner, scope, mode và test.
- [ ] Audit/warn được dùng trước enforce khi phù hợp.
- [ ] Fail-open/fail-closed được chọn theo rủi ro và HA của webhook.
- [ ] Exception có lý do, approval và expiry.
- [ ] Policy rollout theo ring và có rollback.

**Operations**

- [ ] Mỗi cluster có ID, owner, site và environment.
- [ ] Audit ghi actor, action, cluster và release version.
- [ ] Có alert cho cluster stale, agent offline và certificate sắp hết hạn.
- [ ] Telemetry được buffer khi edge offline.
- [ ] Có runbook decommission, compromise và re-enrollment.
- [ ] Có báo cáo compliance evidence cập nhật.

## 20. Quy trình triển khai quản trị fleet

1. Kiểm kê cluster, site, owner, environment và trust boundary.
2. Chọn identity provider và mô hình federation cho human/workload/cluster.
3. Chuẩn hóa RBAC, service account và workload identity.
4. Thiết lập bootstrap, certificate lifecycle và trust bundle.
5. Xây dựng repository cấu hình khai báo và policy-as-code.
6. Chia baseline, fleet profile, site profile và workload config.
7. Tích hợp CI validation, approval, signing và release version.
8. Cài local agent/controller với quyền tối thiểu.
9. Thiết lập cache last-known-good và offline policy cho edge.
10. Bắt đầu ở audit/warn, xử lý vi phạm và tạo exception có expiry.
11. Enforce theo rollout ring sau khi test và đo tác động.
12. Bật drift detection, audit, compliance dashboard và alert.
13. Diễn tập mất WAN, credential expiry, policy rollback và cluster compromise.
14. Review quyền, exception, certificate và ownership theo chu kỳ.

## 21. Nguyên tắc vận hành

1. **Danh tính riêng cho từng chủ thể:** người dùng, workload, node và cluster không dùng chung credential.
2. **Federation có giới hạn:** xác minh issuer, subject, audience và scope; không trust toàn fleet một cách mặc định.
3. **Credential ngắn hạn và có rotation:** giảm tác động khi token hoặc certificate bị lộ.
4. **Cấu hình khai báo, có version:** repository và release đã phê duyệt là nguồn trạng thái mong muốn.
5. **Policy-as-code có kiểm thử:** audit/warn trước enforce khi cần và có exception hết hạn.
6. **Enforcement tại chỗ:** cluster phải thực thi RBAC và policy ngay cả khi management plane offline.
7. **Edge có last-known-good:** chỉ áp dụng bundle đã xác minh và giữ khả năng rollback.
8. **Drift có phân loại:** phân biệt thay đổi động hợp lệ, thay đổi khẩn cấp và vi phạm bảo mật.
9. **Rollout theo ring:** kiểm tra tác động ở nhóm nhỏ trước khi mở rộng toàn fleet.
10. **Audit và ownership đầy đủ:** mỗi cluster, policy và exception có owner, lịch sử và runbook.

Quản lý danh tính, cấu hình và chính sách trên các cụm phân tán đòi hỏi một mô hình fleet có chuẩn chung nhưng không phụ thuộc hoàn toàn vào kết nối trung tâm. Identity federation giúp xác thực người dùng, workload và cluster theo scope; GitOps và versioned configuration giữ trạng thái mong muốn nhất quán; policy-as-code kiểm soát việc triển khai và vận hành; còn local enforcement, cached release và last-known-good cho phép edge tiếp tục hoạt động an toàn khi offline. Kết hợp các cơ chế này với certificate rotation, audit, drift detection và rollout theo ring giúp tổ chức kiểm soát fleet hybrid/edge ở quy mô lớn mà vẫn duy trì khả năng tự chủ tại từng site.
