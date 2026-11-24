# Micro-segmentation — Phân đoạn vi mô trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Chủ đề:** Micro-segmentation  
> **Phạm vi module:** Quản lý vòng đời danh tính và quyền truy cập trong IAM theo **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp quyền, rà soát, thay đổi và thu hồi. Bài học gắn phân đoạn vi mô với **IdP, SSO, SCIM, RBAC/ABAC, danh tính workload/service account, kiểm toán và giảm quyền truy cập tồn dư**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **micro-segmentation** và mục tiêu giảm **lateral movement** (di chuyển ngang) cùng **blast radius** (phạm vi ảnh hưởng) khi một user, thiết bị hoặc workload bị chiếm quyền.
2. Phân biệt **network segmentation**, **micro-segmentation**, **Zero Trust Network Access (ZTNA)**, **identity-aware access** và **authorization ở tầng ứng dụng**; biết vì sao chúng hỗ trợ nhau nhưng không thay thế nhau.
3. Xác định **tài nguyên, luồng truy cập, chủ thể, ranh giới tin cậy** và chuyển chúng thành chính sách có **source, destination, action, protocol, context, scope và thời hạn** rõ ràng.
4. Thiết kế PEP ở gateway, host, cloud, Kubernetes, service mesh hoặc API; kết hợp PDP/thuộc tính danh tính với RBAC/ABAC và chính sách **deny mặc định**.
5. Giải thích các đặc điểm kỹ thuật của **Kubernetes NetworkPolicy**, workload identity, mTLS, service-mesh L7 authorization và cách kiểm tra tenant ở backend.
6. Gắn sự kiện **Joiner–Mover–Leaver**, cấp quyền JIT, token/phiên còn hạn và service account mồ côi với việc cấp, điều chỉnh, thu hồi **đường kết nối** và **quyền thực hiện hành động**.
7. Xây dựng kế hoạch triển khai theo giai đoạn, kiểm thử luồng được phép/bị cấm, đối soát policy và giám sát các chỉ số về **độ phủ, độ trễ thực thi, sai lệch và lỗi chặn nhầm**.

## 2. Micro-segmentation là gì?

**Micro-segmentation (phân đoạn vi mô)** là cách chia môi trường ứng dụng, hạ tầng và dữ liệu thành những **ranh giới truy cập nhỏ, được bảo vệ bằng chính sách cụ thể**, thay vì cho phép hầu hết thực thể trong cùng một mạng hoặc môi trường tự do kết nối với nhau.

Mục tiêu là:

- Chỉ cho **đúng nguồn** kết nối tới **đúng đích** để thực hiện **mục đích cần thiết**.
- Không xem vị trí “đang ở mạng nội bộ” hoặc “cùng Kubernetes cluster” là bằng chứng đủ để cho phép.
- Giảm khả năng một danh tính hoặc workload bị xâm nhập có thể quét, truy cập hay lạm dụng nhiều dịch vụ khác.
- Cho phép **theo dõi, kiểm tra và thu hồi** từng nhóm kết nối khi nhu cầu thay đổi.

Trong ngữ cảnh **Zero Trust IAM**, micro-segmentation hiệu quả nhất khi ranh giới mạng kết hợp với **danh tính, trạng thái vòng đời, quyền nghiệp vụ và điều kiện ngữ cảnh**. Chính sách không nên chỉ có “subnet A được tới subnet B”, mà cần biết **service hoặc người dùng nào được truy cập tài nguyên gì, vì sao, trong bao lâu**.

### Ví dụ: môi trường quản lý thuê nhà

Giả sử nền tảng có các dịch vụ:

- **web-gateway** nhận yêu cầu của khách.
- **tenant-api** quản lý thông tin hợp đồng theo tenant.
- **billing-api** xử lý hóa đơn.
- **notification-worker** gửi thông báo.
- **finance-db** chứa dữ liệu thanh toán.
- **admin-tool** phục vụ vận hành được phê duyệt.

Nếu tất cả cùng một mạng phẳng và có thể tự kết nối, việc chiếm một instance notification-worker có thể mở đường tới finance-db dù worker chỉ cần gửi email. Với micro-segmentation:

- web-gateway chỉ gọi các API đã định danh và được phép.
- tenant-api chỉ truy cập dữ liệu của phạm vi cần thiết.
- billing-api mới được kết nối tới finance-db qua cổng và cơ chế bảo vệ đã quy định.
- notification-worker không có kết nối trực tiếp tới finance-db hoặc admin-tool.
- admin-tool chỉ có đường kết nối qua kênh quản trị/JIT, còn API đích vẫn kiểm tra hành động.

**Điểm mấu chốt:** cho phép kết nối mạng không đồng nghĩa được phép đọc mọi hàng trong database; mạng chặn đường đi, còn **AuthZ ở ứng dụng/dữ liệu** kiểm tra hành động và bản ghi cụ thể.

## 3. Những khái niệm liên quan cần phân biệt

| Khái niệm | Ranh giới thường dùng | Ví dụ | Điều không tự giải quyết |
|---|---|---|---|
| **Network segmentation** | VLAN, subnet, zone, mạng vật lý/ảo | Mạng người dùng tách khỏi mạng production | Trong cùng zone có thể vẫn quá nhiều kết nối |
| **Micro-segmentation** | Workload, ứng dụng, nhóm tài nguyên, luồng kết nối nhỏ | notification-worker không được tới finance-db | Không tự kiểm tra tenant của invoice trong API |
| **Network ACL / security group / firewall** | IP, CIDR, port, protocol, đôi khi nhãn/danh tính tùy nền tảng | Chỉ billing-api được mở TCP tới finance-db | IP/port không nhất thiết chứng minh service thực |
| **ZTNA** | Người dùng/thiết bị/phiên tới ứng dụng cụ thể | Nhân viên Support chỉ được vào CRM qua proxy | Không tự bảo vệ toàn bộ east–west giữa các microservice |
| **Service mesh / identity-aware proxy** | Danh tính workload, kết nối dịch vụ, đôi khi method/path | Chỉ identity billing-api gọi endpoint Billing | Không tự có quyền nghiệp vụ trên từng bản ghi |
| **RBAC / ABAC / ReBAC** | Vai trò, thuộc tính, quan hệ với tài nguyên | Finance đọc invoice cùng tenant, không duyệt giao dịch do mình tạo | Không tự cô lập mạng hoặc ngăn mọi kết nối |
| **PAM / JIT** | Quyền và thời hạn truy cập đặc quyền | Mở phiên quản trị production 20 phút | Không tự đóng mọi kết nối nếu điểm thực thi không nhận revoke |

Trong một môi trường mạnh, các lớp có thể xếp chồng:

**Network allowlist → workload/user authentication → session/context evaluation → API authorization → data-level authorization → audit.**

Không nhất thiết các lớp diễn ra tuyến tính trên mỗi request; ý nghĩa là **mất một lớp không nên làm mất mọi ranh giới**.

### Tránh hai cực đoan

- **Mạng phẳng, chỉ tin SSO:** một service có thể kết nối quá nhiều đích, gia tăng bề mặt bị lợi dụng, dù API có AuthZ.
- **Chỉ chặn bằng firewall:** một service được phép kết nối có thể vẫn khai thác lỗi BOLA/IDOR hoặc có quyền API quá rộng nếu backend thiếu kiểm tra.

Micro-segmentation là **một thành phần của Zero Trust**, không phải toàn bộ chương trình Zero Trust.

## 4. Vì sao micro-segmentation liên quan trực tiếp đến IAM?

Trong IAM, danh tính và quyền quyết định **ai được phép làm gì**. Nhưng nếu mạng và runtime cho phép một chủ thể đi tới quá nhiều dịch vụ, việc quản trị quyền trở nên khó phòng thủ khi token hoặc credential bị lộ.

Giả định một service account có quyền read-only trong billing-api. Nếu nó có thể trực tiếp truy cập database, message broker quản trị và secret store với cùng một credential được chia sẻ, **đường đi ngoài API** có thể bỏ qua kiểm soát AuthZ của billing-api.

Do đó cần thiết kế:

1. **Identity:** service chính xác là ai, owner nào chịu trách nhiệm?
2. **Network reachability:** service được kết nối tới những đích nào?
3. **Authentication of peer:** đích có xác minh service đang kết nối không?
4. **Authorization:** service được thực hiện method/action nào trên resource nào?
5. **Lifecycle:** quyền và đường kết nối khi service bị đổi vai trò, retire hoặc bị quarantine được cập nhật thế nào?
6. **Evidence:** có thể chứng minh kết nối ngoài phạm vi bị chặn và truy cập hợp lệ vẫn hoạt động không?

**Micro-segmentation không yêu cầu biến mỗi người dùng thành một VLAN.** Một số ranh giới bảo vệ **dịch vụ/workload**; những ranh giới khác bảo vệ **đường người dùng đến ứng dụng**, và authorization nghiệp vụ vẫn thuộc API.

### Tư duy Assume breach

Giả định một pod web-gateway bị chiếm. Những câu hỏi đáng đặt:

- Nó có thể kết nối trực tiếp tới finance-db không?
- Nó có thể gọi admin-api hay chỉ những endpoint gateway được ủy quyền?
- Nó có đọc được secret/token của service khác từ runtime hoặc secret store không?
- Nếu token của nó bị lấy cắp, API khác có chặn do issuer/audience/scope/tenant không?
- Khi bị quarantine, policy có ngăn kết nối mới và xử lý phiên đang tồn tại kịp không?

Giảm bề mặt từ một pod bị chiếm giúp **hạn chế blast radius** và giảm khả năng lateral movement, ngay cả khi không loại bỏ hoàn toàn được rủi ro.

## 5. Phân loại luồng truy cập trước khi viết policy

Thông thường cần phân biệt:

- **North–South:** truy cập từ bên ngoài vào ứng dụng hoặc từ ứng dụng ra hệ thống bên ngoài, ví dụ người dùng qua ZTNA/gateway tới CRM.
- **East–West:** lưu lượng giữa các workload, service, VM, database và tầng dữ liệu trong môi trường nội bộ hoặc giữa các môi trường kết nối.

Trong ứng dụng microservices, east–west là trọng tâm vì **cùng cluster không phải một nhóm tin cậy duy nhất**. Tuy nhiên, north–south vẫn cần kiểm soát danh tính người dùng/thiết bị/ứng dụng qua IdP và PEP.

### Một bản đồ dependency tối thiểu

| Nguồn | Đích | Mục đích hợp lệ | Phương thức | Trạng thái mong muốn |
|---|---|---|---|---|
| web-gateway | tenant-api | Xử lý hợp đồng và thông tin tenant | HTTPS/gRPC theo định danh service | Allow có policy; API kiểm tra user/tenant |
| web-gateway | finance-db | Không có nhu cầu trực tiếp | Database protocol | Deny |
| billing-api | finance-db | Đọc/ghi giao dịch hóa đơn cần thiết | DB qua cổng xác định, credential riêng | Allow hẹp |
| notification-worker | finance-db | Không có nhu cầu | Database protocol | Deny |
| notification-worker | notification-provider | Gửi thông báo đã phê duyệt | HTTPS egress có kiểm soát | Allow hẹp |
| monitoring-agent | telemetry-collector | Gửi metric/log | Giao thức đã phê duyệt | Allow hẹp |
| admin-tool | cloud-admin-api | Xử lý sự cố có ticket | Kênh PAM/JIT | Allow có thời hạn và audit |

**Khác nhau giữa reachability và quyền dữ liệu:** billing-api được tới finance-db không có nghĩa nó được chạy truy vấn tùy ý bằng tài khoản database admin. Cần cấp DB role và câu lệnh/đối tượng đúng nghiệp vụ.

### Tạo đồ thị luồng

Hãy mô hình hóa hệ thống thành:

- **Nút:** user, device, workload, API, database, namespace, cloud account, SaaS.
- **Cạnh:** quyền kết nối hoặc hành động từ nguồn tới đích.
- **Nhãn cạnh:** protocol/port/method, identity, resource scope, thời hạn và policy ID.
- **Thuộc tính nút:** owner, environment, tenant, criticality, lifecycle state.

Đồ thị này giúp nhận ra những đường kết nối không phục vụ nghiệp vụ, các “điểm trung chuyển” có khả năng gây thiệt hại lớn và các policy cần ưu tiên siết chặt.

## 6. Mô hình chính sách: nguồn, đích, hành động, điều kiện

Một chính sách micro-segmentation cần tránh cấu hình chỉ mang tên “allow_internal”. Bản mô tả tối thiểu nên có:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **Source identity** | Workload/user/nhóm đích thực được phép khởi tạo | spiffe://example.test/ns/finance/sa/billing-api |
| **Source scope** | Môi trường, project, namespace, tenant hoặc vùng triển khai | production / finance |
| **Destination** | Dịch vụ/nhóm tài nguyên có owner rõ ràng | finance-db |
| **Operation** | Connect, read, write, method/path, API action tùy lớp thực thi | TCP 5432 hoặc invoice.read |
| **Trust condition** | Peer identity, token audience, device/workload posture | mTLS peer verified, workload active |
| **Lifecycle/time** | Effective/expiry, JIT approval, version | grant đến 12:30Z |
| **Default** | Không có match phải xử lý thế nào | Deny |
| **Owner/audit** | Ai chịu trách nhiệm và bằng chứng | finance-platform, policy v7 |

Lưu ý: **IP/CIDR** vẫn có vai trò, nhưng IP của pod hoặc autoscaling instance có thể thay đổi nhanh. Danh tính workload và **label do platform đáng tin kiểm soát** thường phù hợp hơn cho chính sách dịch vụ, nếu hệ thống thực sự hỗ trợ và bảo vệ được nguồn nhãn.

### Chính sách khái niệm

~~~yaml
# Pseudocode trình bày ý định, không phải cấu hình trực tiếp cho một sản phẩm.
policy_id: microseg.finance-db
default: deny
source:
  workload_identity: billing-api
  environment: production
  namespace: finance-prod
  lifecycle_status: active
destination:
  service: finance-db
  environment: production
connection:
  protocol: tcp
  port: 5432
  mutual_authentication: required
conditions:
  workload_posture: acceptable
  entitlement: db.connection.billing
  policy_version: current
governance:
  owner: finance-platform
  justification: "Ghi và đọc nghiệp vụ hóa đơn"
  review_cycle: periodic_risk_based
audit:
  capture: [source_identity, destination, action, policy_id, decision, timestamp]
~~~

Một policy như vậy có thể cần **nhiều điểm thực thi khác nhau**. NetworkPolicy thực thi pod/namespace/port; service mesh xác minh peer identity; DB đánh giá credential/role; ứng dụng kiểm tra quyền trên bản ghi. Không nên tưởng rằng paste nguyên YAML minh họa vào một hệ thống sẽ tạo đủ các lớp bảo vệ.

## 7. Lớp thực thi: PEP, PDP và đường đi thực tế

~~~mermaid
flowchart LR
    U["Người dùng / Client"] --> G["ZTNA / API Gateway PEP"]
    IDP["IdP / SSO / JML"] --> POLICY["PDP + thuộc tính hiện tại"]
    RISK["Device / workload / session risk"] --> POLICY
    G --> POLICY
    G --> W["web-gateway"]
    W --> N["Network PEP: host/CNI/cloud"]
    N --> M["Service mesh / mTLS PEP"]
    M --> A["tenant-api / billing-api"]
    A --> B["Backend AuthZ"]
    B --> DB["Database / data policy"]
    POLICY --> M
    POLICY --> B
    S["SCIM / provisioning / IAM events"] --> POLICY
    L["Audit / SIEM"] --> POLICY
    G --> L
    N --> L
    M --> L
    B --> L
~~~

Sơ đồ mô tả **các vai trò bảo vệ bổ trợ**, không bắt buộc triển khai đúng số lượng thành phần.

**PEP (Policy Enforcement Point)** có thể nằm ở:

- Cloud security group, distributed firewall, endpoint agent, host firewall, CNI.
- Service mesh sidecar/ambient proxy hoặc identity-aware proxy.
- API gateway, ZTNA gateway, backend authorization middleware.
- Database/resource policy hoặc secret-management gateway.

**PDP (Policy Decision Point)** lấy policy và thuộc tính để quyết định; có thể nằm trong service hoặc tập trung. **Policy Administrator (PA)** trong mô hình ZTA điều phối việc thiết lập/chấm dứt đường truy cập theo quyết định. Cần tách vai trò này khỏi các nghiệp vụ phê duyệt con người để tránh lẫn thuật ngữ.

### Đặt câu hỏi theo từng lớp

1. **Network PEP:** gói tin/flow này có được đi từ workload A đến B không?
2. **Peer authentication:** B có chắc đang nói với workload A chứ không phải một pod giả nhãn?
3. **L7 policy:** A có được gọi method/path của B không?
4. **Business AuthZ:** user hoặc workload có được thực hiện action trên invoice thuộc tenant X không?
5. **Data protection:** kết quả truy vấn có bị giới hạn đúng record và trường dữ liệu không?
6. **Audit:** có thể xác định lớp nào cho phép/từ chối, dựa vào version chính sách nào?

Một connection được allow ở lớp 3/4 **không là chứng chỉ quyền ở lớp 7**. Ngược lại, API có AuthZ đúng không có nghĩa nên để mọi service trong cluster kết nối trực tiếp tới DB.

## 8. Danh tính nguồn: con người và workload cần cách bảo vệ khác nhau

### 8.1. User đến ứng dụng

Một nhân viên Support đăng nhập qua IdP, MFA và nhận phiên tới CRM. Chính sách ZTNA có thể giới hạn:

- User active, được gán đúng nhóm, hợp đồng còn hiệu lực.
- Device posture đạt điều kiện với dữ liệu cần truy cập.
- Chỉ expose ứng dụng CRM thay vì cả subnet production.
- Phiên có TTL và khả năng đánh giá lại khi user Mover/Leaver.
- API thực thi **RBAC/ABAC và kiểm tra tenant/ticket**.

**Không nên gán toàn bộ danh tính người dùng cho một IP NAT**, vì nhiều người có thể dùng chung mạng và IP có thể thay đổi. Nếu lớp mạng chỉ biết ứng dụng/thiết bị, phải giữ kiểm tra user ở tầng ứng dụng.

### 8.2. Workload gọi workload

Một service không nhập MFA tương tác cho mỗi request; thay vào đó cần:

- Principal/service identity riêng và owner nhóm.
- Credential ngắn hạn, issuer/audience rõ và bảo vệ khóa khi phù hợp.
- Chứng thực peer bằng mTLS hoặc cơ chế identity tương đương.
- Kiểm tra source identity thực thay vì tin hostname/header tùy ý.
- Quyền ở destination theo service/action/resource.
- Trạng thái workload (active, quarantined, retired) và policy hiện hành.

**Workload identity federation, SPIFFE/SPIRE, cloud service identity hoặc Kubernetes service account** là các cơ chế có thể sử dụng tùy kiến trúc. Không phải cứ có tên service hoặc label trong token là danh tính đáng tin nếu token không được phát hành/kiểm chứng theo trust policy phù hợp.

### 8.3. Hạn chế credential bị phát lại

Nếu dùng bearer token, một token bị lộ có thể bị phát lại theo phạm vi hiệu lực. Giảm rủi ro bằng token tuổi ngắn, audience hẹp, kiểm tra authorization hiện hành và sender constraints (như mTLS hoặc DPoP khi phù hợp). **mTLS ở giữa hai service không tự làm access token chỉ dùng được bởi đúng client**, trừ khi thiết kế token binding/kiểm tra liên quan thực sự được triển khai.

## 9. Kubernetes NetworkPolicy: ví dụ phân đoạn ở L3/L4

Kubernetes NetworkPolicy chuẩn cho phép kiểm soát lưu lượng tới/vào pod theo **pod selector, namespace selector, IPBlock, port, protocol**, tùy CNI. Đây là **phân đoạn ở tầng kết nối**; API/business authorization không nằm trong NetworkPolicy.

Để minh họa, giả sử:

- Namespace **finance-prod** chứa pod **billing-api** và **finance-db**.
- Chỉ **billing-api** được kết nối tới **finance-db** qua TCP 5432.
- Đích cần từ chối lưu lượng không khớp, không mở cho mọi pod khác.

### 9.1. Default-deny ingress cho namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: finance-prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Policy này chọn mọi pod ở namespace **finance-prod** và cô lập ingress theo ngữ nghĩa NetworkPolicy chuẩn nếu CNI hỗ trợ. Nó không tự chặn **egress**. Các kết nối đến pod sẽ chỉ được phép khi một NetworkPolicy áp dụng cho pod đó cho phép.

### 9.2. Cho billing-api tới finance-db

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-billing-to-finance-db
  namespace: finance-prod
spec:
  podSelector:
    matchLabels:
      app: finance-db
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: billing-api
      ports:
        - protocol: TCP
          port: 5432
~~~

Đây là **allow inbound của finance-db** từ các pod có nhãn app=billing-api trong cùng namespace. Trong NetworkPolicy chuẩn, danh sách allow của các policy áp dụng là **cộng dồn**: một policy khác quá rộng vẫn có thể cho phép nhiều nguồn vào cùng pod. Vì vậy cần rà soát **tất cả policy áp dụng**, không chỉ hai manifest ví dụ.

### 9.3. Giới hạn egress của billing-api

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: billing-egress
  namespace: finance-prod
spec:
  podSelector:
    matchLabels:
      app: billing-api
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: finance-db
      ports:
        - protocol: TCP
          port: 5432
~~~

Khi pod billing-api bị cô lập egress, policy chỉ cho kết nối TCP 5432 đến finance-db trong cùng namespace, theo selector đã khai. **Manifest này chưa mở DNS, telemetry hoặc các API khác**; nếu ứng dụng cần chúng, phải thiết kế các luồng cho phép bổ sung theo yêu cầu, tránh mở rộng bằng allow-all.

**Lưu ý triển khai quan trọng:**

1. NetworkPolicy chỉ có hiệu lực khi **plugin/CNI thực sự hỗ trợ và thực thi** chính sách. API object tồn tại không đồng nghĩa mạng đã bị chặn.
2. **Ingress và egress là hai chiều kiểm soát riêng.** Với một kết nối, cần có quyền theo các chiều có cô lập tương ứng; kiểm thử thực tế ở cả nguồn và đích.
3. **NetworkPolicy chuẩn không có một deny rule ưu tiên cao hơn allow.** Các policy allow hợp lệ được hợp nhất theo tập.
4. Chỉ có label trong pod không tương đương danh tính bảo mật mạnh. Phải giới hạn ai có thể tạo pod, sửa namespace/label, service account và admission policy.
5. Trong một rule, **namespaceSelector và podSelector cùng một mục from/to** có nghĩa lấy pod thỏa cả hai điều kiện; ở hai mục riêng thì các peer được cộng theo ý nghĩa OR.
6. Khi triển khai policy egress, cần kiểm tra DNS/service discovery, monitoring, external API và luồng bootstrap; không tự thêm allow toàn cluster để “chữa” lỗi.
7. Kubernetes NetworkPolicy chuẩn không giải quyết L7 method/path, user identity, role theo tenant hay trạng thái token JWT.

### 9.4. Ví dụ selector kết hợp namespace và pod

~~~yaml
# Một đoạn peer trong ingress rule, cùng một phần tử => AND.
from:
  - namespaceSelector:
      matchLabels:
        purpose: finance-clients
    podSelector:
      matchLabels:
        app: report-worker
~~~

Đoạn trên cho phép các pod report-worker **trong các namespace có label purpose=finance-clients**, không có nghĩa mọi pod trong finance-clients hoặc mọi report-worker ở mọi namespace.

Không để team chưa được ủy quyền tùy ý sửa label **purpose** của namespace nếu label này quyết định ranh giới truy cập. Đối với môi trường tenant nhạy cảm, nên xem xét thêm danh tính workload được xác thực qua proxy/mTLS thay vì chỉ dựa trên label.

## 10. Service mesh và chính sách L7 theo workload identity

**Service mesh** có thể hỗ trợ mTLS giữa service và policy theo danh tính peer, HTTP method/path, namespace hoặc thuộc tính khác. Khả năng cụ thể tùy sản phẩm, chế độ triển khai và cách định nghĩa identity.

Mô hình điển hình:

1. Mesh xác thực **peer workload identity**.
2. Network PEP xác định liệu nguồn có thể nối tới đích/port.
3. L7 PEP kiểm tra source principal, method/path và các thuộc tính giao thức được hỗ trợ.
4. Backend kiểm tra quyền nghiệp vụ: actor, action, tenant, ownership, SoD.
5. Event retire/quarantine/revoke có đường phản ánh tới policy và credential.

### Pseudocode chính sách service identity

~~~yaml
# Chính sách mô tả, KHÔNG phải CRD/cú pháp của service mesh cụ thể.
rule_id: billing-api-to-finance-report
source:
  workload_principal: "spiffe://corp.example/ns/finance-prod/sa/billing-api"
  lifecycle_state: active
destination:
  workload_principal: "spiffe://corp.example/ns/finance-prod/sa/report-api"
transport:
  mutual_tls: required
layer_7:
  methods: [GET]
  paths: ["/v1/reports/summary"]
conditions:
  source_posture: acceptable
  environment: production
default: deny
~~~

**Vì sao không chỉ kiểm tra đường dẫn?** Nếu không xác thực source principal, một service khác có thể gọi cùng method/path. Nhưng nếu chỉ kiểm tra identity của billing-api, API vẫn phải xác nhận **billing-api có quyền đọc báo cáo của tenant đang được yêu cầu**.

### Cảnh giác với đường bỏ qua sidecar/proxy

Một triển khai có thể có traffic không đi qua mesh (host networking, cổng admin trực tiếp, database endpoint khác, legacy client). Cần kiểm kê các đường bypass, bảo vệ inbound/outbound ở tầng mạng và kiểm thử đường đi thực tế.

mTLS **bảo vệ kết nối và xác thực peer** theo cấu hình, không tự động quyết định RBAC/ABAC cho business records. Đồng thời không mặc định rằng “mọi pod có sidecar” là đã được bảo vệ: cần kiểm tra chính sách thực thi, mode cho phép plaintext và đường không qua proxy.

## 11. Cloud, VM, database và SaaS: phân đoạn không chỉ nằm ở container

### 11.1. VM và security group

Với VM/cloud, có thể phân đoạn bằng security group, distributed firewall, network ACL hoặc policy dựa trên tài nguyên. Hạn chế quy tắc như:

- Mở toàn bộ cổng từ mọi subnet “internal”.
- Cho bất kỳ VM trong một project đều kết nối đến database.
- Dùng chung một security group admin cho ứng dụng và workload runtime.
- Mở SSH/RDP thường trực từ mạng lớn cho mọi server.

Thay vào đó, phân tách **app tier, data tier, management plane, logging plane**, có owner, mục đích và baseline riêng. Nơi hỗ trợ, sử dụng tham chiếu nhóm/tài nguyên được quản trị; nơi chỉ có IP/CIDR, cần automation và kiểm soát drift khi autoscaling hoặc thay máy.

### 11.2. Database và secret store

Ngay cả khi chỉ billing-api được mở cổng tới finance-db, hãy kiểm tra:

- Database credential có **vai trò tối thiểu** không?
- Có tách quyền read/write, schema, tenant, dataset không?
- Secret được cấp cho đúng workload principal, lifetime và rotation thế nào?
- Khi service retire, credential còn dùng được không?
- Có đường database admin, backup, ETL hoặc reporting bypass API không?

**Database role và row-level security** có thể bảo vệ thêm ở tầng dữ liệu. Nếu mọi service cùng sử dụng một DB user toàn quyền, segmentation ở mạng chưa đủ để giới hạn thiệt hại.

### 11.3. SaaS và đối tác

Micro-segmentation không luôn là “chặn packet” khi API nằm ở SaaS bên ngoài. Đối với kết nối này, có thể phân đoạn theo:

- OAuth client/integration riêng;
- API scope, resource tenant và domain;
- Workload principal, IP allowlist nếu phù hợp và chính sách đích hỗ trợ;
- Expiry, chủ sở hữu, giới hạn xuất dữ liệu và audit;
- Thu hồi token, webhook secret và quyền đối tác khi hợp đồng hết hạn.

**SCIM giúp đồng bộ tài khoản và nhóm**, nhưng không phải giao thức micro-segmentation hay authorization trực tiếp của từng API request.

## 12. JML: thay đổi vai trò phải thay đổi cả đường truy cập

Micro-segmentation không phải cấu hình “một lần rồi để nguyên”. Người dùng và workload thay đổi vai trò; những đường kết nối từng hợp lệ có thể trở thành **quyền tồn dư**.

| Sự kiện | Trạng thái quyền | Thay đổi phân đoạn/đường đi | Điều phải xác minh |
|---|---|---|---|
| **Joiner** | User/service được tạo và cấp quyền ban đầu | Chỉ expose ứng dụng/luồng cần thiết theo role | Luồng hợp lệ hoạt động; luồng ngoài phạm vi bị deny |
| **Mover** | Role, tenant, project hoặc môi trường thay đổi | Gỡ đường tới tài nguyên cũ, thêm đường mới có phê duyệt | Phiên/token/connection cũ không còn cho truy cập ngoài phạm vi |
| **Leaver** | User/integration hết ủy quyền | Chặn đăng nhập mới, thu hồi phiên, role và đường kết nối liên quan | Không còn truy cập tại API/SaaS/DB bằng credential cũ |
| **Privilege expiry** | Quyền JIT hoặc ngoại lệ hết hạn | Đóng hoặc không cho tạo tiếp kết nối/action đặc quyền | Kết nối dài và token cũ bị xử lý theo SLA |
| **Periodic access review** | Kiểm tra quyền hiệu lực và nhu cầu | Xóa policy quá rộng, stale rule, tài khoản không owner | Policy đã xóa không bị phục hồi do cấu hình khác |

### 12.1. Joiner: cấp quyền ứng dụng, không mở cả mạng

Nhân viên Support mới được tuyển cần truy cập CRM. Quy trình tốt:

1. HR/hợp đồng xác minh danh tính, vai trò, manager, tenant và ngày có hiệu lực.
2. IAM/IdP tạo subject ID, thiết lập xác thực phù hợp, cấp role Support tối thiểu.
3. ZTNA hoặc access gateway chỉ cho phép user đi tới CRM; không cho network-level access tới toàn subnet production.
4. CRM thực thi quyền ticket theo tenant/assignment; hành động export và admin có policy riêng.
5. Kiểm thử request với user mới: CRM được phép đúng scope, Finance và admin API bị từ chối.

Nếu user được quyền **xem ticket** thì không vì vậy được mở SSH tới VM của CRM hoặc kết nối trực tiếp tới database.

### 12.2. Mover: đặc biệt nguy hiểm khi quyền chồng lấp

Nhân viên An chuyển từ Support sang Finance lúc 09:00.

~~~text
Trước Mover:
  User An -> CRM (ticket.read, ticket.comment, tenant-A)
  User An -X-> Finance production
  Legacy VPN group -> internal-operations-subnet (quyền cũ quá rộng)

Sau Mover mong muốn:
  User An -X-> CRM operations
  User An -> Finance app (invoice.read, tenant-A)
  User An -X-> Finance DB direct / admin plane
  Legacy VPN group -> revoked
~~~

Cần **đối soát desired và actual**:

- Gỡ role/nhóm cũ ở IdP và ứng dụng đích.
- Gỡ membership điều khiển ZTNA/VPN/network rule nếu không còn phù hợp.
- Điều chỉnh ABAC resource scope và SoD.
- Xử lý access token, refresh token, phiên SaaS và kết nối đang mở còn quyền cũ.
- Kiểm tra quyền trực tiếp/nhóm lồng nhau, local account và ngoại lệ có thời hạn.
- Theo dõi SCIM/provisioning lỗi tới khi dữ liệu đích đã thay đổi.
- Kiểm thử **lối cũ bị chặn ở mạng và ở API**, không chỉ nhìn thấy group IdP đã xóa.

Nếu cần chuyển giao hai vai trò trong vài ngày, phải có **grant ngoại lệ hữu hạn, scope hẹp, owner/phê duyệt và ngày kết thúc**, không để “giữ quyền Support cho tiện”.

### 12.3. Leaver: không chỉ khóa user tại IdP

Một người rời tổ chức có thể còn:

- VPN/ZTNA session, ứng dụng local session hoặc WebSocket;
- Refresh token, access token JWT còn hạn, API key/PAT/SSH key;
- DB credential hoặc quyền truy cập storage trực tiếp;
- Delegation/chia sẻ file và quyền cloud kế thừa;
- Bot/service account chạy bằng credential cá nhân.

Cần tắt đăng nhập mới, gỡ quyền ở IdP và ứng dụng, xử lý token/phiên, thu hồi key/chứng chỉ, đối soát đường kết nối và **xác nhận tại data plane**. Một JWT tự chứa không tự mất hiệu lực chỉ vì IdP disable account nếu resource server kiểm offline mà không có cơ chế phản ánh thay đổi.

## 13. Service account và vòng đời workload trong phân đoạn vi mô

Danh tính máy cũng có vòng đời tương tự JML ở mức thiết kế:

- **Register (Joiner tương tự):** service mới được cấp principal riêng, owner, namespace, scope, đường kết nối và approval.
- **Change (Mover tương tự):** đổi môi trường/tenant/release/owner, tính lại quyền và kết nối.
- **Retire (Leaver tương tự):** dừng deployment, thu hồi credential, gỡ role, secret, rule, webhook và xác nhận đường cũ không còn hoạt động.

### Mô hình quản trị một service

| Thông tin | Ví dụ cho billing-api |
|---|---|
| Principal | svc-billing-api-prod |
| Owner | finance-platform |
| Mục đích | Xử lý hóa đơn tenant A/B được ủy quyền |
| Environment | production |
| Đích hợp lệ | finance-db, audit-collector, payment-provider đã phê duyệt |
| Action thực tế | invoice.read/write theo rule nghiệp vụ |
| Credential | Workload identity riêng, token/chứng chỉ ngắn hạn khi phù hợp |
| Posture | Release/config được phê duyệt, instance active, không quarantine |
| Review | Theo rủi ro và sau thay đổi lớn |
| Retire | Gỡ workload, role, network rule, key, session và xác nhận deny |

Nếu kỹ sư sở hữu bot rời công ty, không nên giữ API key cá nhân để bot còn chạy. Chuyển ownership sang nhóm, cấp service identity độc lập rồi thu hồi credential cá nhân theo kế hoạch không gián đoạn.

### Vì sao service account chia sẻ là anti-pattern?

Ba job cùng dùng **svc-admin**, cùng được tới finance-db và secret-store. Khi một job bị chiếm, khó biết job nào tạo request và không thể chặn riêng mà không ảnh hưởng các job khác. Tách principal theo workload/tenant/môi trường giúp **định danh, thu hồi và giới hạn blast radius** hiệu quả hơn.

## 14. Phiên, token và kết nối dài: ranh giới cần có thời gian

Micro-segmentation không chỉ kiểm tra lúc TCP connection được tạo. Một số quyền có thể thay đổi giữa phiên:

~~~text
08:50  Nhân viên An mở phiên ZTNA đến CRM.
09:00  HRIS phát Mover: An không còn role Support.
09:01  IdP cập nhật group; CRM chưa xử lý SCIM do lỗi.
09:05  ZTNA connection vẫn mở, JWT CRM có hạn đến 10:50.
09:06  An gọi API export bằng phiên cũ.
09:06  Nếu backend kiểm quyền hiện tại: deny.
09:06  Nếu chỉ tin claim cũ/session: có thể allow sai.
~~~

### Cần tách ít nhất bốn vòng đời

1. **Network session/tunnel:** VPN/ZTNA/mesh connection có còn được sử dụng không?
2. **Authentication session:** browser/SSO/session app có còn tin cậy không?
3. **Authorization grant:** role/ABAC/resource policy hiện có cho action không?
4. **Credential lifetime:** token/chứng chỉ/API key còn hợp lệ và có bị thu hồi không?

Đóng tunnel có thể chặn một đường nhưng người dùng vẫn có token gọi API public nếu API không kiểm quyền. Ngược lại, API deny đúng nhưng kết nối tới DB vẫn mở có thể là rủi ro khi còn một credential phụ được chấp nhận.

### Cách phản ánh thay đổi

- Event JML và revoke được xác thực nguồn, có **version/effective time**.
- IdP/gateway/session manager kết thúc hoặc hạn chế phiên theo khả năng.
- PEP/PDP invalidation cache hoặc tra cứu trạng thái hiện tại cho action nhạy cảm.
- Workload/service mesh dùng chứng chỉ và token có thời hạn phù hợp, xoay hoặc thu hồi khi sự cố.
- Đối với kết nối lâu dài (WebSocket, streaming, DB session), quyết định **khi nào cần kiểm lại, đóng kết nối hoặc chặn action tiếp theo**.
- Với workload bị cách ly, kiểm tra **các request mới và request đang chờ** theo phạm vi và SLA đã công bố.

Độ trễ thu hồi phải được đo tại điểm truy cập, không chỉ tính thời điểm phát sự kiện.

## 15. Thiết kế theo tenant và dữ liệu nhạy cảm

Trong hệ thống multi-tenant, micro-segmentation hỗ trợ cô lập dịch vụ và dữ liệu nhưng **không bảo đảm cách ly tenant tự động**.

### Ba kiểu cô lập thường gặp

| Kiểu | Ranh giới | Lợi ích | Kiểm soát bổ sung |
|---|---|---|---|
| Shared application, shared database | Cùng runtime nhưng record có tenant_id | Tiết kiệm tài nguyên | Bắt buộc object/row-level AuthZ, dữ liệu và cache theo tenant |
| Shared app, database/schema tách tenant | Một số ranh giới dữ liệu riêng | Giảm giao thoa dữ liệu ở DB | Kiểm tra mapping user/service tới DB/tenant đúng |
| Workload/data tách theo tenant | Namespace/cluster/project/service riêng theo tenant | Ranh giới mạng và IAM rõ hơn | Kiểm soát cross-tenant API, CI/CD, admin và secret |

Không có một mô hình luôn đúng. **Quyền truy cập dữ liệu** phải được kiểm thử ở backend và database, kể cả khi namespace và network policy đã tách.

### Ví dụ báo cáo của tenant A

Service report-worker có kết nối mạng hợp lệ tới report-api. API nhận request GET /reports/R-204, nhưng bản ghi R-204 thuộc tenant B. Kết quả đúng là **deny**, dù report-worker dùng mTLS và đúng namespace.

Nếu workload được phép đọc báo cáo cho nhiều tenant theo nhiệm vụ, phải lưu **phạm vi đã phê duyệt**, không cho client tùy ý khai tenant của chính mình. Đối với batch export, quyền cần được áp dụng cho **mọi bản ghi được xuất**, không chỉ endpoint tạo job.

## 16. Chiến lược triển khai: đừng chặn mù trong một đêm

Việc chuyển mạng phẳng sang micro-segmentation cần hiểu **luồng phụ thuộc thực tế**. Nếu đặt default deny toàn bộ mà chưa biết DNS, monitoring, callback và luồng bootstrap, hệ thống có thể ngừng hoạt động.

### Giai đoạn 1 — Kiểm kê

- Liệt kê ứng dụng, workload, API, DB, queue, secret store, cloud account, SaaS và owner.
- Xác định dữ liệu nhạy cảm, đích production, principal đặc quyền.
- Thống kê network flows và dependency từ nhiều nguồn đáng tin.
- Nhận diện luồng east–west, north–south, đường quản trị, backup/monitoring, DNS và health check.
- Tìm principal/service account mồ côi và quyền truy cập không có lý do nghiệp vụ.

**Telemetry về một flow từng tồn tại không tự chứng minh flow đó hợp lệ**. Phải có người sở hữu ứng dụng xác nhận nhu cầu.

### Giai đoạn 2 — Thiết kế chính sách mục tiêu

- Nhóm theo **ứng dụng, môi trường, tenant, độ nhạy dữ liệu và trust boundary**.
- Viết allowlist theo source/destination/action/protocol; xác định owner và thời hạn.
- Phân biệt policy L3/L4, peer identity L7 và authorization nghiệp vụ.
- Xác định đường truy cập phải bảo vệ khẩn cấp trước.
- Chọn cơ chế label/identity thật sự được bảo vệ và được PEP hỗ trợ.

### Giai đoạn 3 — Đánh giá/quan sát an toàn

- Dùng flow logs, tracing hoặc policy shadow/dry-run **nếu nền tảng hỗ trợ**.
- So luồng quan sát với luồng được nghiệp vụ phê duyệt.
- Phát hiện dependency bỏ sót và các rule quá rộng.
- Viết test cho các request lẽ ra phải bị deny, không chỉ test happy path.

Không xem “log-only” là đã thực thi; nó chỉ giúp chuẩn bị rollout.

### Giai đoạn 4 — Thực thi theo phạm vi nhỏ

- Ưu tiên một dịch vụ hoặc namespace có owner và bản đồ dependency rõ ràng.
- Áp dụng default deny có điều kiện và allow rõ cho luồng cần thiết.
- Theo dõi lỗi kết nối, latency, denied flows, mức ảnh hưởng tới batch và dịch vụ ngoài.
- Có rollback **đúng phạm vi**, không dùng rule allow-all thường trực.
- Nếu có nhiều PEP, xác nhận không có đường khác bypass policy mới.

### Giai đoạn 5 — Mở rộng và tự động hóa

- Quản lý policy như cấu hình có version, review và kiểm thử trước merge/deploy.
- Tự động cập nhật các thuộc tính nguồn từ IAM/service registry.
- Gắn JML, retirement, incident quarantine vào thay đổi quyền và rule.
- Thiết lập owner, expiry, lý do cho policy ngoại lệ.

### Giai đoạn 6 — Vận hành và cải tiến

- So sánh **desired policy** với **effective policy** tại từng PEP.
- Rà soát quyền tồn dư, rule không dùng, shadowed/overlapping rules, privilege lớn.
- Diễn tập Mover/Leaver, token còn hạn, CNI/mesh lỗi và event trễ.
- Báo cáo chỉ số coverage, deny effectiveness, revocation latency, false deny và availability.

~~~mermaid
flowchart LR
    A["Inventory + flow mapping"] --> B["Policy model + owner"]
    B --> C["Review + tests"]
    C --> D["Observe / shadow khi hỗ trợ"]
    D --> E["Canary enforcement"]
    E --> F{"Hợp lệ và sẵn sàng?"}
    F -->|"Không"| G["Khắc phục / rollback giới hạn"]
    G --> B
    F -->|"Có"| H["Mở rộng theo ranh giới"]
    H --> I["Audit + JML + reconciliation"]
    I --> B
~~~

## 17. Policy-as-code, thay đổi an toàn và tính nhất quán

Các rule phân đoạn thường nằm rải rác ở cloud security group, Kubernetes NetworkPolicy, service mesh và API. Nếu không quản trị, một rule mới ở tầng này có thể mở đường vượt chính sách tầng khác.

### Bộ yêu cầu cho mỗi policy change

| Mục | Câu hỏi bắt buộc |
|---|---|
| Owner | Ai chịu trách nhiệm nghiệp vụ và kỹ thuật? |
| Source/destination | Đúng service nào, môi trường nào, tenant nào? |
| Action/port | Luồng nào là tối thiểu đủ dùng? |
| Justification | Vì sao cần kết nối? Có ticket/design review? |
| Time | Quyền có thời hạn hay event kết thúc nào? |
| Effective scope | Có policy khác cộng dồn mở rộng quyền không? |
| Regression tests | Allow flow hợp lệ, deny flow sai, cross-tenant, credential cũ? |
| Rollout | Canary, giám sát, rollback thế nào? |
| Audit | Có thể truy policy version tới request và operator không? |

### Tránh các lỗi nhất quán phổ biến

- **Label drift:** namespace đổi nhãn khiến nhiều pod được match rộng ngoài ý muốn.
- **Policy merge:** một NetworkPolicy allow rộng còn sót làm mất mục tiêu default deny.
- **Version skew:** PEP A dùng policy v10, PEP B vẫn dùng v8.
- **Stale identity:** service đã retire nhưng certificate/key hoặc principal còn được chấp nhận.
- **Out-of-order event:** revoke mới bị event grant cũ ghi đè.
- **Shadow rule:** một allow-all ở cloud hoặc mesh khiến rule hẹp phía khác không có tác dụng dự kiến.
- **Rule khó truy trách nhiệm:** không biết vì sao luồng được mở, không có owner để quyết định gỡ.

Quy tắc phát hành nên có kiểm thử tự động, phê duyệt phù hợp và khả năng **quan sát chính sách hiệu lực**, chứ không chỉ kiểm tra file cấu hình đang lưu.

## 18. Rủi ro vận hành: DNS, telemetry, sự cố và fail-safe

Một lỗi phổ biến khi áp default deny egress là quên các dependency cơ bản:

- DNS/service discovery, control plane hoặc certificate rotation.
- Telemetry, audit collector, logging, tracing và health check.
- Kênh lấy secret, token issuer, artifact registry hoặc time synchronization.
- Callback từ payment provider, message broker, object storage.
- Kênh khôi phục thảm họa hoặc quản trị khẩn cấp.

**Giải pháp không phải allow toàn internet hay mở toàn cluster.** Cần định danh những dependency hợp lệ, owner, action/protocol và phương án giảm phụ thuộc.

### Khi PEP/PDP không khả dụng

| Tình huống | Rủi ro | Hướng thiết kế |
|---|---|---|
| CNI/controller gặp lỗi | Rule không được triển khai đồng nhất, flow bị chặn hoặc mở ngoài ý muốn | Kiểm tra bảo đảm enforcement ở data plane, alert và runbook của nền tảng |
| Mesh control plane không sẵn sàng | Sidecar/proxy thiếu policy/certificate mới | Xác định chính sách cache/hết hạn/fail-safe cụ thể |
| IdP/issuer mất kết nối | Không xác minh hoặc cấp lại workload/user credential | Credential có hạn, truy cập khẩn cấp có kiểm soát nếu cần |
| PDP timeout | Không ra quyết định mới | Action nhạy cảm không mặc định permit; fallback theo risk đã duyệt |
| Audit/telemetry mất | Không đủ bằng chứng xử lý sự cố | Queue log bền vững hoặc hạn chế action nhạy cảm theo policy |
| Event JML bị trễ | Quyền cũ còn ở điểm thực thi | TTL/invalidation/reconciliation; kiểm thử revocation SLA |

**Fail closed** là từ chối khi không thể kiểm tra các điều kiện bắt buộc, nhưng cần thiết kế tính sẵn sàng. Với nghiệp vụ ít rủi ro, có thể có chế độ suy giảm có phạm vi và thời hạn, nếu đã được phê duyệt; không được coi lỗi hạ tầng là lý do mở toàn bộ truy cập.

### Break-glass và JIT

Khi cần khôi phục dịch vụ do cấu hình phân đoạn sai, đường break-glass phải:

- Có chủ thể/nhóm được phê duyệt, credential được bảo vệ.
- Mở **đúng đường/port/action cần sửa**, trong thời hạn ngắn.
- Có ticket sự cố, audit và cảnh báo.
- Được thu hồi và kiểm thử sau khi sự cố kết thúc.

Không nên để rule emergency allow-all tồn tại lâu dài sau khi hệ thống trở lại bình thường.

## 19. Anti-pattern và cách sửa

| Anti-pattern | Tác động | Hướng cải thiện |
|---|---|---|
| “Internal traffic = trusted” | Một workload bị chiếm có thể gọi nhiều service | Default deny east–west, xác minh peer và AuthZ |
| Chia nhóm theo subnet quá lớn | Mọi service trong zone có nhiều đường không cần thiết | Phân đoạn theo workload/app/tenant/risk |
| Chỉ dựa IP của pod | IP thay đổi hoặc tái sử dụng, khó gắn owner | Dùng policy theo label đáng tin và identity khi nền tảng hỗ trợ |
| Coi NetworkPolicy thay RBAC/ABAC | API đúng cổng vẫn trả sai tenant | Backend kiểm tra action/resource/tenant |
| Một service account cho cả cluster | Không giới hạn được blast radius và khó audit | Principal riêng theo service/môi trường, scope hẹp |
| Có mTLS thì allow toàn bộ RPC | Peer hợp lệ gọi action không hợp lệ | L7 policy và AuthZ nghiệp vụ |
| Rule allow-all “tạm” không expiry | Quyền vượt nhu cầu tồn tại lâu | Ngoại lệ có owner, ticket, TTL, rà soát |
| Chỉ xét luồng mạng tại thời điểm triển khai | Mover/Leaver không làm thay đổi kết nối và token cũ | Tích hợp JML, event, revoke và data-plane test |
| Chặn UI nhưng API/DB mở trực tiếp | Lách ranh giới theo đường khác | Bảo vệ mọi đường tương đương đến resource |
| Không kiểm effective policy | Policy khác cộng dồn mở rộng quyền | Kiểm kê và test policy hợp nhất |
| Bật default deny không có dependency map | Gián đoạn DNS/monitoring/production | Observe, review, canary và hồi quy |
| Audit chỉ ghi “allow/deny” ở firewall | Không xác định người, workload và dữ liệu thực | Correlate identity, policy, action/resource và kết quả |

**Một chính sách hẹp nhưng không được thực thi là không có giá trị phòng thủ.** Cần chứng minh bằng các phép thử kết nối và request đúng lớp.

## 20. Kiểm toán micro-segmentation

Một log quyết định hữu ích nên cho biết:

- **Source identity** (user hoặc workload), instance/session reference nếu cần.
- **Destination identity**, service, resource scope và hành động/protocol.
- **Network decision** và **application authorization decision** khi có.
- **Policy ID/version**, kết quả sau khi các rule được hợp nhất.
- **Lifecycle version** hoặc trạng thái quyền hiện hành, mốc hiệu lực.
- **Timestamp và correlation ID** để nối sự kiện JML, policy rollout, incident và request.
- **Enforcement outcome**: thực sự block, allow, disconnect hay obligation được áp dụng.
- **Reason code** đủ phục vụ điều tra nhưng không tiết lộ bí mật.

### JSON audit minh họa

~~~json
{
  "timestamp": "2026-11-23T09:06:13Z",
  "event_type": "microseg_enforcement",
  "correlation_id": "req-a41f",
  "source_principal": "svc-notification-worker-prod",
  "source_environment": "production",
  "destination_service": "finance-db",
  "destination_port": 5432,
  "protocol": "TCP",
  "network_policy_id": "finance-db-ingress",
  "network_policy_version": 17,
  "network_decision": "deny",
  "enforcement_action": "connection_blocked",
  "reason_code": "SOURCE_NOT_IN_ALLOWLIST",
  "source_lifecycle_state": "active"
}
~~~

Đây là **mẫu khái niệm**, không phải schema chuẩn của Kubernetes/CNI. Không ghi mật khẩu, bearer token, private key, secret hoặc dữ liệu khách hàng nguyên văn. Bảo vệ log khỏi sửa/xóa trái phép và giữ retention theo nhu cầu điều tra và chính sách riêng tư.

### Kết hợp network và API logs

Một luồng hợp lệ như **web-gateway → billing-api** có thể được network PEP cho phép, nhưng billing-api từ chối invoice.read sai tenant. Hai loại log nên có **correlation** để chứng minh:

- Kết nối chỉ được phép theo policy mạng phù hợp.
- Peer identity và phiên được xác thực.
- Request có action/resource cụ thể, đúng hoặc sai quyền.
- Không có dữ liệu lộ khi AuthZ deny.

Không mặc định mọi network flow gắn được với end-user nếu thiết kế không truyền ngữ cảnh người dùng tới backend. Cần phân biệt **identity của service kết nối** và **identity của actor nghiệp vụ**.

## 21. Các chỉ số đánh giá hiệu quả

| Chỉ số | Cách đo | Ý nghĩa |
|---|---|---|
| **Segmentation coverage** | Tỷ lệ workload/ứng dụng nhạy cảm có ranh giới enforce thật, không chỉ policy mô tả | Phát hiện vùng mạng phẳng |
| **Unnecessary reachability** | Số cạnh kết nối đang allow nhưng không có nhu cầu/phê duyệt | Giảm blast radius |
| **Cross-boundary deny effectiveness** | Tỷ lệ kịch bản cố tình vượt ranh giới bị chặn | Đo năng lực phòng thủ thực |
| **Identity-aware enforcement coverage** | Tỷ lệ đường nhạy cảm xác minh source principal/peer | Giảm phụ thuộc vào IP/label |
| **JML-to-enforcement latency** | Từ Mover/Leaver đến khi luồng/quyền cũ không còn dùng được | Đo quyền tồn dư |
| **Policy drift/version skew** | Policy hiệu lực khác desired hoặc PEP dùng version quá hạn | Phát hiện rollout sai |
| **Temporary rule expiry rate** | Ngoại lệ/JIT được thu hồi đúng hạn | Ngăn rule tạm thành thường trực |
| **False block/false allow** | Kết quả sai được xác minh qua điều tra/test | Cân bằng bảo mật và vận hành |
| **Denied flow volume** | Lượt kết nối bị chặn phân theo nguồn/đích/rule | Phát hiện bất thường, không tự coi nhiều deny là tốt |
| **Policy rollout failures** | Tỷ lệ thay đổi gây gián đoạn hoặc lệch chính sách | Cải tiến quy trình triển khai |
| **Orphaned principal/rule count** | Service account, security group, policy không owner hoặc không còn workload | Tìm quyền tồn dư |
| **Lateral movement blast-radius score** | Số/độ nhạy tài nguyên có thể đến từ một nguồn giả định bị chiếm theo mô hình tổ chức | Ưu tiên siết những nguồn có tác động lớn |

**Tỷ lệ có NetworkPolicy = 100% không đủ.** Các policy có thể cho phép mọi nguồn; CNI có thể không thực thi; DB có thể có đường khác; service có thể dùng token admin chung. Kết hợp inventory, phép thử **negative** và log data plane.

## 22. Ma trận kiểm thử end-to-end

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| M1 | web-gateway gọi tenant-api qua đúng port | Kết nối được nếu peer và AuthZ hợp lệ |
| M2 | notification-worker thử kết nối finance-db | Bị chặn bởi network PEP |
| M3 | billing-api có kết nối tới finance-db nhưng dùng DB role không có quyền DROP | Database từ chối lệnh |
| M4 | Service dùng mTLS hợp lệ nhưng gọi API ngoài scope | L7/backend deny |
| M5 | Support user đăng nhập SSO, gọi Finance app không được phép | ZTNA/API từ chối theo role |
| M6 | User đúng role nhưng đọc record của tenant khác | Backend/data layer deny |
| M7 | Pod có label giả billing-api nhưng không có identity hợp lệ | Mesh/identity PEP từ chối hành động yêu cầu identity |
| M8 | NetworkPolicy đúng manifest nhưng CNI không hỗ trợ enforce | Kiểm thử phát hiện không bị chặn; không ghi nhận PASS |
| M9 | Một NetworkPolicy khác allow rộng finance-db | Kiểm thử effective policy phát hiện kết nối ngoài scope |
| M10 | Mover gỡ Support role, JWT cũ còn hạn | CRM/PEP từ chối action cũ theo SLA |
| M11 | Leaver còn VPN session và API key cá nhân | Session/key bị xử lý; API không còn cho phép quyền cũ |
| M12 | Service retire nhưng network rule và credential còn | Reconciliation phát hiện và yêu cầu revoke; negative test deny |
| M13 | JIT admin đã hết TTL nhưng tunnel vẫn mở | Action đặc quyền bị từ chối hoặc kênh bị ngắt theo policy |
| M14 | Workload bị quarantine giữa kết nối dài | Policy phản ánh risk event, hạn chế luồng trong SLA |
| M15 | Event grant cũ đến sau revoke mới | Không khôi phục quyền nhờ version/effective time |
| M16 | DNS/telemetry bị chặn khi bật egress deny | Phát hiện và bổ sung chính sách đúng phạm vi, không allow-all |
| M17 | PDP lỗi khi yêu cầu truy cập secret production | Fail closed hoặc đường khẩn cấp đã phê duyệt riêng |
| M18 | Export worker xử lý job do actor đã Leaver tạo | Reevaluate actor/approval trước side effect theo policy |
| M19 | Policy v18 có rule deny theo scope, PEP B còn v16 | Phát hiện version skew, hạn chế và cập nhật |
| M20 | Một signed URL được phát trước khi quyền user đổi | Đánh giá vòng đời URL và phương án chặn theo khả năng kiến trúc |
| M21 | Workload ở staging cố gọi production secret API | Network/identity/resource policy deny |
| M22 | Service có endpoint admin ngoài mesh | Kiểm thử phát hiện bypass và yêu cầu bảo vệ riêng |

### Phương pháp kiểm thử

1. Tạo **danh tính thử nghiệm** và workload trong môi trường được ủy quyền, sử dụng dữ liệu mẫu.
2. Chỉ định các luồng **phải được phép** (positive) và **phải bị từ chối** (negative).
3. Ghi trước policy/version, source identity, destination và expected outcome.
4. Thử thực tế ở **network layer**, **service authentication layer** và **API/data layer** khi tương ứng.
5. Với Mover/Leaver, đặt mốc sự kiện, dùng token/phiên cũ, đo thời gian chặn thực tế.
6. Đối chiếu log PEP/PDP và backend, xác nhận deny xảy ra **trước khi có dữ liệu lộ hoặc side effect**.
7. Kiểm tra các đường phụ và tình huống mất tín hiệu; sửa policy, chạy hồi quy.

**Không thực hiện quét hay tấn công môi trường production ngoài phạm vi có thẩm quyền.** Với diễn tập phát hiện di chuyển ngang, dùng workload được kiểm soát và kế hoạch thử nghiệm đã phê duyệt.

## 23. Bài tập tình huống: hạn chế lateral movement khi Mover và service bị chiếm

### Bối cảnh

Một nền tảng dùng IdP/SSO cho nhân viên, SCIM đồng bộ nhóm tới CRM/Finance, Kubernetes cho microservice và cloud security group cho database.

Kiến trúc:

- **web-gateway** nhận request người dùng, gọi tenant-api và billing-api.
- **billing-api** đọc/ghi finance-db.
- **notification-worker** gửi email qua notification-provider.
- **report-worker** tạo báo cáo tenant A với workload identity riêng.
- **admin-tool** có đường bảo trì production bằng phiên PAM/JIT.
- Nhân viên **Hà** là Support manager tenant A và sẽ chuyển sang Finance.

#### Dòng thời gian

| Mốc | Sự kiện |
|---|---|
| 08:40 | Hà đăng nhập SSO; CRM phát access token có hạn đến 10:40. |
| 09:00 | HRIS báo Hà Mover; IdP gỡ nhóm Support, thêm Finance. |
| 09:02 | CRM SCIM update bị lỗi; ZTNA group cache vẫn còn quyền tới CRM. |
| 09:05 | Một instance notification-worker có hành vi bất thường, nhưng vẫn có network reachability tới finance-db do allow-all policy cũ. |
| 09:06 | notification-worker cố kết nối trực tiếp finance-db; DB credential dùng chung giữa nhiều service. |
| 09:08 | Hà dùng token CRM cũ gửi yêu cầu export dữ liệu tenant A. |
| 09:10 | Kỹ sư vận hành bật allow-all egress để sửa lỗi DNS, quên đặt expiry. |
| 09:15 | Security nhận alert bất thường và kích hoạt khoanh vùng. |

### Nhiệm vụ

1. Vẽ **đồ thị luồng được phép** và đánh dấu ít nhất bốn đường không nên tồn tại.
2. Thiết kế bộ policy tối thiểu ở **network**, **mesh/peer identity**, **API/AuthZ** và **DB**.
3. Xác định rủi ro từ token cũ của Hà và SCIM bị lỗi; cần liên kết JML tới các điểm thực thi nào?
4. Với notification-worker nghi xâm nhập, thiết kế hành động containment để giảm blast radius mà hạn chế ảnh hưởng các service khác.
5. Giải quyết allow-all egress lúc 09:10 như thế nào để vẫn phục hồi DNS an toàn?
6. Đề xuất ba phép thử negative và ba chỉ số vận hành để xác nhận đã khắc phục.

### Lời giải tham khảo

**1. Đồ thị mong muốn:** web-gateway → tenant-api/billing-api; billing-api → finance-db; notification-worker → notification-provider và telemetry theo scope đã duyệt; report-worker → report API/đích hợp lệ; admin-tool → đường PAM/JIT. Các đường không nên tồn tại gồm notification-worker → finance-db, notification-worker → admin-tool, web-gateway → finance-db trực tiếp, staging workload → finance-db production, mọi workload → secret-store admin.

**2. Các lớp policy:** Kubernetes/cloud default deny và allow hẹp; mesh/mTLS xác minh principal thật trước khi chấp nhận kết nối và method nhạy cảm; billing API kiểm tra invoice/tenant/action; database dùng credential riêng và role tối thiểu, không dùng DB user chung toàn quyền. Thử kết nối bị chặn và thử request sai quyền nghiệp vụ.

**3. Mover:** gỡ group và quyền trực tiếp ở CRM, ZTNA/VPN, IdP/session, SCIM app, kiểm soát JWT cũ ở backend; thử customer.export sau mốc hiệu lực và xác nhận deny. **SCIM lỗi phải có alert/retry/reconciliation**, không đánh dấu thu hồi hoàn tất khi chưa kiểm chứng.

**4. Containment:** đánh dấu workload instance rủi ro, giới hạn kết nối từ notification-worker theo policy, chặn/thu hồi credential liên quan và điều tra log. Tách credential/service principal cho các job để có thể cách ly riêng. Không mặc định đóng finance-db cho mọi ứng dụng nếu còn đường giới hạn an toàn hơn, trừ khi mức độ sự cố đòi hỏi.

**5. DNS:** tìm dependency DNS được phép, mở đúng giao thức/đích và phạm vi nguồn; đưa rule qua review/test/canary. Rule allow-all tạm phải có owner, cảnh báo và expiry/thu hồi sau khi phục hồi. Nếu có sự cố khẩn cấp, ghi audit của ngoại lệ và kiểm thử lại những đường bị cấm.

**6. Kiểm thử và metric:** notification-worker → finance-db phải deny; JWT cũ của Hà sau Mover không export được; staging/nhãn giả không vượt qua peer identity; quyền DB không cho thao tác ngoài nhiệm vụ. Đo **JML-to-enforcement latency**, **unnecessary reachability** và **temporary-rule expiry compliance**; có thể thêm policy-version drift và false-block rate.

### Mở rộng

Nếu team đang dùng **NetworkPolicy chỉ dựa vào label**, hãy đề xuất cách bảo vệ label/namespace bằng RBAC và admission; rồi bổ sung lớp **workload identity mTLS và API AuthZ** để giảm rủi ro giả mạo metadata. Giải thích vì sao ba lớp tạo ra bằng chứng độc lập hơn một label được đặt tùy ý.

## 24. Checklist triển khai và tài liệu đọc thêm

### Checklist

- [ ] Có inventory về ứng dụng, workload, user, thiết bị, database, owner, môi trường và dữ liệu nhạy cảm.
- [ ] Đã phân biệt micro-segmentation với ZTNA, network segmentation, service identity và business AuthZ.
- [ ] Lập đồ thị các luồng east–west/north–south, xác nhận mục đích và scope từng đường.
- [ ] Chính sách có **source, destination, operation, context, owner, thời hạn và default deny** phù hợp.
- [ ] Không dùng network location nội bộ làm bằng chứng truy cập duy nhất.
- [ ] Workload principal được xác minh, token/chứng chỉ có issuer/audience/TTL phù hợp, không dùng key admin chung.
- [ ] Kubernetes NetworkPolicy được **CNI thực thi thật**; rà soát hiệu lực cộng dồn các policy và egress DNS.
- [ ] Service mesh/mTLS policy xác minh peer identity; backend vẫn kiểm tra tenant/action/resource.
- [ ] Cloud/VM/database/SaaS có ranh giới và credential riêng, tránh đường bypass API.
- [ ] JML xử lý role, nhóm, ZTNA/VPN, SCIM, phiên/token, service accounts và kết nối tồn dư.
- [ ] Có cơ chế hạn chế/quarantine workload theo sự kiện rủi ro, hỗ trợ điều tra và khôi phục.
- [ ] Policy thay đổi có review, version, negative tests, canary, rollback có kiểm soát.
- [ ] Ngoại lệ khẩn cấp/JIT có owner, scope hẹp, TTL và bằng chứng thu hồi.
- [ ] Kiểm thử đường allow và deny ở nhiều lớp, kể cả sai tenant, token cũ và kết nối dài.
- [ ] Log có source/destination identity, policy version, quyết định và enforcement outcome, không lộ secret.
- [ ] Đo coverage, reachability, event-to-enforcement latency, false deny và orphaned rules.

### Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Micro-segmentation** | Phân chia và kiểm soát các luồng truy cập ở phạm vi workload/ứng dụng/tài nguyên nhỏ |
| **East–West** | Lưu lượng giữa các thành phần nội bộ hoặc giữa dịch vụ với nhau |
| **North–South** | Lưu lượng vào/ra ứng dụng hoặc môi trường |
| **Lateral movement** | Di chuyển từ một điểm bị xâm nhập sang hệ thống/tài nguyên khác |
| **Blast radius** | Phạm vi ảnh hưởng có thể phát sinh từ một sự cố |
| **ZTNA** | Truy cập ứng dụng theo Zero Trust, thường kết hợp danh tính/ngữ cảnh |
| **PEP / PDP / PA** | Điểm thực thi / thành phần quyết định / thành phần quản trị đường truy cập theo ZTA |
| **mTLS / workload identity** | Xác thực hai đầu kết nối / danh tính dùng cho service hoặc tiến trình |
| **NetworkPolicy** | Đối tượng Kubernetes để xác định những kết nối pod/namespace được phép tại L3/L4 |
| **RBAC / ABAC** | Phân quyền theo vai trò / thuộc tính và ngữ cảnh |
| **IdP / SSO / SCIM** | Xác thực tập trung / đăng nhập liên kết / đồng bộ user, group |
| **JML** | Joiner–Mover–Leaver, quản lý danh tính theo gia nhập, đổi vai trò và rời đi |
| **Effective policy** | Tập quyền kết nối/truy cập thực tế khi hợp nhất mọi rule liên quan |
| **Residual access** | Đường kết nối, role, phiên hoặc credential còn hoạt động sau khi hết ủy quyền |
| **Policy drift** | Sai khác giữa chính sách mong muốn và chính sách đang có hiệu lực |

### Tài liệu tham khảo khái niệm

- **NIST SP 800-207 — Zero Trust Architecture:** nguyên tắc, PEP/PDP/PA, policy-driven access và giảm tin cậy ngầm.
- **NIST SP 800-207A — A Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Cloud Environments:** áp dụng ZTA cho workload và ứng dụng cloud-native.
- **NIST SP 800-53 — Security and Privacy Controls:** các nhóm kiểm soát truy cập, cấu hình, audit và giám sát.
- **Kubernetes Documentation — Network Policies:** ngữ nghĩa podSelector, namespaceSelector, ingress/egress và tính cộng dồn của các policy.
- **Kubernetes Documentation — Pod Security Standards và RBAC:** bảo vệ workload/namespace, cấu hình runtime và quyền chỉnh metadata.
- **SPIFFE/SPIRE và tài liệu service mesh:** mô hình định danh workload, mTLS và policy theo principal khi nền tảng hỗ trợ.
- **RFC 7643 / RFC 7644 — SCIM:** đồng bộ user/group trong IAM, không thay runtime authorization.
- **OpenID Connect / OAuth 2.0:** phân biệt xác thực SSO, token, scope và kiểm tra resource server.
- **OWASP API Security Top 10:** kiểm soát object-level/function-level authorization để bổ sung cho phân đoạn mạng.

**Điều cần nhớ:** Micro-segmentation trong Zero Trust IAM không chỉ là “đóng bớt cổng mạng”. Đó là năng lực chứng minh rằng **đúng người hoặc workload, đúng trạng thái và quyền, chỉ có thể đi qua những ranh giới cần thiết để thực hiện hành động được ủy quyền trên tài nguyên phù hợp**. Khi danh tính, vai trò, phiên, workload hoặc rủi ro đổi theo **JML và vận hành thực tế**, các đường truy cập phải được cập nhật, thu hồi và **kiểm chứng tại điểm thực thi**, từ đó giảm lateral movement và quyền truy cập tồn dư.
