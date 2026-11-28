# Segmentation theo tenant: cô lập khách hàng trong hạ tầng mạng dùng chung

Một nền tảng SaaS có thể phục vụ hàng trăm doanh nghiệp trên cùng hạ tầng. Mỗi doanh nghiệp là một **tenant**: có người dùng, cấu hình, dữ liệu và quyền truy cập riêng. Nếu hệ thống phân đoạn không đúng, lỗi ở một ứng dụng, quy tắc mạng hoặc bộ định tuyến yêu cầu có thể cho phép truy cập tài nguyên của tenant khác, dù mỗi người dùng đã đăng nhập hợp lệ.

**Segmentation theo tenant** là cách tạo, thực thi và kiểm chứng các ranh giới để lưu lượng và quyền truy cập của tenant A không tự động mở sang tenant B. Trong module **SECURITY_NETWORK_SECURITY**, nội dung này kết nối phân đoạn mạng, firewall, VPN/ZTNA, xác thực kết nối, IDS/IPS, bảo vệ DNS và đám mây với **threat modeling** và giám sát luồng. Mục tiêu cuối cùng không chỉ là vẽ nhiều subnet mà là ngăn **truy cập chéo tenant trái phép** trên cả mạng, dịch vụ, dữ liệu và control plane.

## 1. Tenant, ranh giới tin cậy và mục tiêu cô lập

### 1.1. Tenant khác user, role và môi trường triển khai

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Tenant** | Đơn vị khách hàng hoặc miền tổ chức có tài sản và chính sách riêng | Công ty A và công ty B cùng dùng ứng dụng kế toán SaaS |
| **User** | Một chủ thể thuộc tenant hoặc có quyền được ủy quyền | Nhân viên của công ty A |
| **Role** | Nhóm quyền trong phạm vi xác định | `accountant`, `tenant-admin`, `platform-support` |
| **Resource** | Đối tượng cần bảo vệ | Hóa đơn, bản sao lưu, cơ sở dữ liệu, bucket, hàng đợi |
| **Environment** | Môi trường triển khai, có thể chứa nhiều tenant | `production`, `staging` |
| **Security zone** | Miền áp dụng một tập kiểm soát bảo mật | Internet, edge, workload, data, management |

Một tenant có nhiều user; một user có thể được cấp quyền ở nhiều tenant. **Một role tên giống nhau ở hai tenant không có nghĩa là quyền của hai bên được gộp lại.** Hệ thống phải gắn phép kiểm tra với đồng thời **danh tính, tenant đang hoạt động, tài nguyên và thao tác**.

**Trust boundary** là nơi mức tin cậy hoặc quyền quản trị thay đổi. Giữa hai tenant khác nhau luôn cần xem xét ranh giới quyền, dù họ ở chung VPC, cluster, namespace hoặc cùng bảng dữ liệu. Vùng mạng riêng giúp thực thi một phần chính sách, nhưng không chứng minh ứng dụng đã kiểm tra đúng tenant.

### 1.2. Bốn mục tiêu bảo mật của segmentation

1. **Confidentiality (bí mật):** dữ liệu, token, secret và log của tenant A không bị tenant B đọc.
2. **Integrity (toàn vẹn):** tenant A không thể sửa cấu hình, bản ghi hoặc tài nguyên của tenant B.
3. **Availability (sẵn sàng):** lỗi hoặc lượng tải bất thường của một tenant không dễ làm cạn tài nguyên chung khiến tenant khác ngừng hoạt động.
4. **Accountability (truy vết):** hành động quản trị, đường truyền và yêu cầu nghiệp vụ có đủ ngữ cảnh tenant để điều tra mà không lộ dữ liệu nhạy cảm.

Cách diễn đạt một yêu cầu kiểm soát tốt: **“Workload thuộc tenant A chỉ được kết nối tới những dịch vụ đã phê duyệt của tenant A; mọi yêu cầu đọc hóa đơn phải kiểm tra chủ thể có quyền trong tenant sở hữu hóa đơn.”** Câu “hai tenant nằm ở hai subnet” chưa đủ xác định quyền ở tầng dữ liệu.

## 2. Các mô hình cô lập tenant

Mức cô lập cần tương ứng với độ nhạy cảm, cam kết khách hàng, nhu cầu vận hành và chi phí. Ba mô hình phổ biến:

| Mô hình | Kiến trúc thường thấy | Ưu điểm | Giới hạn và điểm phải bảo vệ |
|---|---|---|---|
| **Silo / dedicated** | Một account/project/subscription, VPC, cluster hoặc bộ dịch vụ riêng cho mỗi tenant (tùy lựa chọn) | Giảm thành phần dùng chung; dễ đặt giới hạn tài nguyên/quyền độc lập | Chi phí và vận hành tăng; control plane, CI/CD, DNS hoặc giám sát chung vẫn có thể là đường chéo tenant |
| **Pool / shared** | Nhiều tenant dùng chung API, worker, database và mạng, phân biệt bằng `tenant_id` và chính sách | Tối ưu tài nguyên, đơn giản triển khai tính năng | Phụ thuộc rất mạnh vào tenant context, phân quyền từng đối tượng, cô lập dữ liệu và quota |
| **Bridge / hybrid** | API/gateway chung nhưng dữ liệu, worker hoặc tài nguyên nhạy cảm tách theo tenant | Cân bằng chi phí và mức bảo vệ | Routing và mapping tenant → tài nguyên là điểm nhạy cảm; thành phần chung có thể truy cập nhiều miền |

**Cô lập logic** và **cô lập hạ tầng** không phải hai trạng thái đúng/sai tuyệt đối. Một hệ thống có thể tách database theo tenant nhưng dùng chung cluster; hoặc dùng VPC riêng nhưng dùng chung IdP, hệ thống quản lý secret và cơ chế triển khai. Phải ghi rõ **những gì được tách** và **những gì vẫn chia sẻ**.

### 2.1. Các cấp độ cô lập trong một hệ thống

| Lớp | Kiểm soát theo tenant | Ví dụ |
|---|---|---|
| **Network** | VPC/VNet, subnet, security group, firewall, CNI NetworkPolicy, egress | Workload A không thể mở TCP tới database B |
| **Connection/service** | mTLS/workload identity, service authorization, gateway routing | Chỉ danh tính dịch vụ A được gọi API nội bộ dành cho A |
| **Application** | Xác minh tenant context, authorization với từng đối tượng | User thuộc A không thể yêu cầu `invoiceId` của B |
| **Data** | Database/schema/bảng riêng; row-level security; bucket/prefix policy và key phù hợp | Truy vấn chỉ thấy những bản ghi thuộc tenant được xác thực |
| **Compute/resources** | Quota, limit, hàng đợi, pool kết nối, autoscaling | Tenant A không làm cạn toàn bộ worker dành cho B |
| **Control plane** | IAM/RBAC, quyền thay tag/label, deployment, secret và audit | Đội vận hành tenant A không thể sửa policy của tenant B |

Một lỗi quan trọng là chỉ thực hiện segmentation ở một lớp, sau đó kỳ vọng các lớp còn lại tự kế thừa ranh giới đó. **Network policy không thay kiểm tra quyền nghiệp vụ; tenant ID trong dữ liệu không tự chặn kết nối mạng.**

## 3. Vẽ data flow và trust boundary theo tenant

Giả sử nền tảng hóa đơn có một gateway dùng chung và hai môi trường xử lý riêng:

~~~mermaid
flowchart LR
    subgraph EXT["Internet: thiết bị khách hàng"]
        UA["Người dùng tenant A"]
        UB["Người dùng tenant B"]
    end
    subgraph EDGE["TB1: Vùng dùng chung - gateway và xác thực"]
        G["API gateway"]
        AUTH["Xác minh danh tính và tenant context"]
        G --> AUTH
    end
    subgraph A["TB2A: Workload tenant A"]
        WA["Invoice API A"]
        DA[("Kho hóa đơn A")]
        WA -->|"TLS / quyền dữ liệu A"| DA
    end
    subgraph B["TB2B: Workload tenant B"]
        WB["Invoice API B"]
        DB[("Kho hóa đơn B")]
        WB -->|"TLS / quyền dữ liệu B"| DB
    end
    subgraph CTRL["TB3: Control plane dùng chung"]
        P["Policy / identity / deploy"]
        LOG[("Log tập trung có phân quyền")]
        P --> WA
        P --> WB
    end

    UA -->|"HTTPS / request"| G
    UB -->|"HTTPS / request"| G
    AUTH -->|"Luồng đã kiểm tra dành cho A"| WA
    AUTH -->|"Luồng đã kiểm tra dành cho B"| WB
    WA -.->|"Event có tenant context"| LOG
    WB -.->|"Event có tenant context"| LOG
~~~

Sơ đồ trên **minh họa mô hình bridge**. Việc chuyển tiếp tới A/B dựa trên tenant context đã được xác minh theo chính sách; các mũi tên thể hiện đường đi hợp lệ, không ngụ ý mọi người dùng có thể gọi cả hai nhánh. Luồng trả về, DNS, backup và kết nối quản trị đã được lược bớt để dễ nhìn; chúng vẫn phải được bổ sung khi đánh giá thực tế.

### 3.1. Ranh giới cần xác định

- **TB1 — người dùng tới gateway:** dữ liệu HTTP, tên tenant trong URL/hostname/header và cookie do client cung cấp đều phải xem là đầu vào chưa đáng tin. Gateway phải xác thực đúng ngữ cảnh trước khi chọn route nhạy cảm.
- **TB2A/TB2B — dịch vụ của từng tenant:** traffic từ gateway tới workload cần được giới hạn theo chính sách. Tài nguyên A và B không có quyền truy cập ngang nhau chỉ vì cùng tổ chức vận hành.
- **TB3 — hệ thống quản trị chung:** pipeline triển khai, hệ thống cấp secret, controller, log collector và nhân viên hỗ trợ có thể chạm tới nhiều tenant. Đây là **miền đặc quyền cao**, cần phân quyền, kiểm soát thay đổi và giám sát độc lập.
- **Ranh giới dữ liệu:** dù dùng DB riêng hay DB chung, quyền truy vấn phải bị ràng buộc bởi tenant sở hữu bản ghi và vai trò người yêu cầu.
- **Ranh giới bên thứ ba:** IdP, email provider, message broker, object storage hoặc API đối tác có thể nhận dữ liệu của nhiều tenant; cần xác định quyền và thông tin tenant được truyền đi.

Trong mô hình pooled API, một instance có thể phục vụ A và B trên cùng socket. Khi đó **không tồn tại ranh giới mạng giữa hai request đi qua cùng process**; điều kiện không rò rỉ tenant phụ thuộc trực tiếp vào authN/authZ, quản lý state và dữ liệu ở ứng dụng.

### 3.2. Bảng kiểm kê luồng mẫu

| Mã | Nguồn → đích | Dữ liệu | Kiểm soát quan trọng |
|---|---|---|---|
| F1 | Trình duyệt A → gateway | Token/cookie, yêu cầu và mã tenant đầu vào | TLS, xác minh token/session, tenant membership, rate limit |
| F2 | Gateway → API A | Tenant context đã xác minh, thao tác nghiệp vụ | Định tuyến có kiểm soát, xác thực upstream/mTLS khi phù hợp, hạn chế đường bypass |
| F3 | API A → DB A | Truy vấn hóa đơn của tenant A | Quyền DB tối thiểu, mạng chỉ mở luồng cần thiết, phân quyền ở API/DB |
| F4 | API A/B → log chung | Event, request ID, tenant ID, mã trạng thái | Lọc PII/token, IAM theo nhu cầu, tách quyền truy cập log |
| F5 | Platform operator → control plane | Thay policy, secret, cấu hình và routing | SSO/MFA, phân quyền, phê duyệt và audit |
| F6 | Tenant workload → API bên thứ ba | Dữ liệu nghiệp vụ được phép gửi | Egress policy, xác minh đích, giới hạn dữ liệu, quota và danh tính |

Khi điều tra, phải biết **tenant context được tạo ở đâu, được chứng thực và truyền qua những hop nào, nơi nào quyết định allow/deny**, và mũi tên nào có thể xuất hiện nếu một thành phần đã bị chiếm.

## 4. Tenant identity và authorization trước khi chọn route

### 4.1. Không tin tenant ID chỉ vì client gửi lên

Ví dụ request:

~~~http
GET /api/tenants/tenant-b/invoices/4821 HTTP/1.1
Host: billing.example.test
Authorization: Bearer <redacted-token>
X-Tenant-ID: tenant-b
~~~

Header `X-Tenant-ID`, đường dẫn và host đều có thể bị client tự đặt. Ứng dụng phải xác minh token/session, xác định **chủ thể có thuộc tenant được chọn không**, sau đó kiểm tra quyền đối với **hóa đơn 4821**. Nếu token hợp lệ cho tenant A nhưng client yêu cầu tenant B, phải từ chối khi không có quyền rõ ràng.

Một access token được ký cũng chưa đủ nếu bên nhận bỏ qua `iss` (issuer), `aud` (audience), thời hạn, chữ ký hoặc điều kiện được phép sử dụng. Claim tenant chỉ đáng tin khi được phát hành/kiểm chứng bởi thành phần có thẩm quyền và có ngữ nghĩa rõ cho ứng dụng đích.

**Quy tắc:** tenant ID trong URL, header hay message chỉ là **giá trị được yêu cầu**, không phải bằng chứng độc lập của quyền truy cập.

### 4.2. Luồng xử lý một request

~~~mermaid
sequenceDiagram
    participant U as Người dùng tenant A
    participant G as Gateway / AuthN
    participant API as Invoice API
    participant DB as Kho dữ liệu
    U->>G: GET /tenants/A/invoices/42
    G->>G: Xác minh session/token và tenant membership
    G->>API: Chuyển ngữ cảnh đã xác minh qua kênh tin cậy
    API->>API: Kiểm tra quyền đọc invoice 42 trong tenant A
    API->>DB: Truy vấn có phạm vi tenant A
    DB-->>API: Kết quả theo điều kiện truy vấn/chính sách
    API-->>U: Dữ liệu được phép hoặc lỗi phù hợp
~~~

Sơ đồ giả định gateway đã xác minh danh tính và truyền ngữ cảnh một cách an toàn. Dịch vụ API vẫn phải **xác thực nguồn ngữ cảnh** hoặc kiểm chứng token được truyền đến; không được tin một header có thể đến từ Internet qua đường bypass.

Nếu một nhân viên có quyền trên nhiều tenant, việc **chuyển tenant đang hoạt động** phải gắn với quyền được cấp và được ghi log. Không được giữ tenant context trong biến toàn cục dùng chung giữa các request, bộ nhớ thread tái sử dụng hoặc connection pool mà không cô lập vòng đời.

### 4.3. Phòng thủ ở tầng dữ liệu

Với bảng dùng chung:

~~~sql
SELECT id, amount, status
FROM invoices
WHERE tenant_id = :authorized_tenant_id
  AND id = :invoice_id;
~~~

`:authorized_tenant_id` phải đến từ **ngữ cảnh đã xác thực và phân quyền**, không lấy trực tiếp từ query parameter hay header. Truy vấn cần dùng tham số có binding chuẩn để tránh SQL injection.

Có thể bổ sung **Row-Level Security (RLS)** nếu database hỗ trợ, hoặc cô lập theo schema/database. Nhưng RLS chỉ bảo vệ đúng khi role DB không có quyền bypass, chính sách áp dụng cho cả đọc và ghi, tenant context được gắn an toàn theo request/transaction và không rò rỉ qua connection pool. **Tenant filtering ở ứng dụng và RLS đều phải được kiểm thử chéo tenant.**

Trong mô hình database riêng, cần kiểm tra **mapping tenant → connection/secret/database**. Một lỗi chọn nhầm connection string vẫn có thể trả dữ liệu của tenant khác, dù mạng đã chia thành hai vùng.

## 5. Cô lập mạng theo tenant trong cloud

### 5.1. Chọn đơn vị cô lập phù hợp

| Phương án | Phạm vi cách ly | Cách kiểm soát phổ biến | Giới hạn |
|---|---|---|---|
| **Account/project/subscription riêng** | Control plane và tài nguyên thuộc đơn vị cloud khác nhau | IAM tổ chức, policy cấp cao, peering/private connectivity có chủ đích | Quản trị trung tâm và pipeline vẫn có thể có quyền liên miền |
| **VPC/VNet riêng trong một đơn vị quản trị** | Routing và vùng mạng tách biệt | Route table, SG/NSG, firewall, endpoint riêng | Cùng account vẫn chia sẻ IAM/control plane |
| **Subnet/security group riêng** | Chia nhóm tài nguyên và giới hạn kết nối | Default deny theo đích, chỉ mở port cho nguồn hợp lệ | Subnet riêng không tự ngăn thao tác qua API cloud hoặc ứng dụng chung |
| **Namespace/NetworkPolicy trong cluster chung** | Nhóm Pod theo namespace/label và áp chính sách L3/L4 | CNI policy, RBAC, admission, quota | Cùng kernel/node và cluster control plane; cần kiểm tra phạm vi CNI |
| **Không tách mạng, tách tenant ở ứng dụng/dữ liệu** | Hạ tầng pool chung | AuthN/AuthZ, RLS, quota, observability | Không chặn lateral movement chỉ bằng mạng giữa các request cùng process |

Sử dụng **private IP**, NAT, VPN hoặc subnet riêng không tự chứng minh workload đáng tin. Nên gắn thêm danh tính workload, mTLS khi cần, IAM/quyền DB tối thiểu và kiểm soát đường quản trị.

### 5.2. Lưu ý triển khai theo nhà cung cấp

- **AWS:** có thể dùng account/VPC riêng, security group, network ACL, IAM và SCP theo phạm vi thích hợp. Rule SG tham chiếu security group hoặc CIDR theo khả năng nền tảng; **tag EC2 không tự biến thành điều kiện nguồn/đích cho SG rule**. IAM tag/ABAC kiểm soát API cloud, không tự chặn TCP giữa hai máy.
- **Azure:** có thể tách subscription/resource group/VNet, áp NSG, Azure Firewall và private endpoint theo kiến trúc. Resource group chủ yếu là miền quản lý; muốn cô lập lưu lượng phải cấu hình mạng và quyền tương ứng.
- **Google Cloud:** có thể tách project/VPC, áp firewall rule/ policy, service account và IAM. Network tag hoặc danh tính service account có thể tham gia chọn tài nguyên theo những loại rule được hỗ trợ; cần đối chiếu phiên bản và quyền sửa tag.
- **Hybrid/on-premise:** VLAN/VRF, routing domain, firewall, ACL, VPN/ZTNA và thiết bị NAC có thể giúp phân tách kết nối của khách hàng. Kênh quản trị, DNS, hệ thống ảo hóa và backup vẫn cần quy tắc riêng.

Không có một “tenant tag” tự động tạo ra phân đoạn mạng ở mọi nền tảng. Cần xác định **ai được gán tag, ai được gắn SG/role, policy được phân phối thế nào và khi thu hồi membership thì kết nối cũ được xử lý ra sao**.

### 5.3. Lưu lượng east–west và north–south

- **North–south:** Internet/đối tác → edge → workload tenant; xác thực tenant ở điểm vào, định tuyến đúng miền và giới hạn public endpoint.
- **East–west:** API/worker → DB, cache, broker và các dịch vụ của tenant; dùng chính sách allow cụ thể, chặn kết nối A → B mặc định.
- **Control plane:** CI/CD, IAM, secret manager, quản trị cluster/cloud, máy chủ logging; hạn chế quyền xuyên tenant và audit mọi thay đổi.
- **Egress:** workload tenant → Internet, DNS, API đối tác, dịch vụ cloud; nên quản lý đích đến/loại dữ liệu/identity theo tenant, tránh đường gọi tới mạng quản trị, metadata service hoặc tài nguyên tenant khác.

Cân nhắc **DNS** riêng hoặc policy resolver nếu tenant có tên miền/dịch vụ riêng. DNS ghi đúng tên đích không tự tạo quyền kết nối; DNSSEC hoặc DNS mã hóa không thay thế firewall, TLS và authorization.

## 6. Kubernetes: tách Namespace và NetworkPolicy theo tenant

Giả sử tenant A có namespace **`tenant-a`** chứa hai nhóm Pod: **`app=invoice-api`** và **`app=invoice-db`**. Tenant B có namespace **`tenant-b`**. Mục tiêu minh họa: khóa ingress/egress mặc định cho các Pod ở tenant A và chỉ mở kết nối API A → DB A trên TCP/5432.

### 6.1. Chính sách mặc định và luồng cụ thể

~~~yaml
# 1. Cô lập ingress và egress cho tất cả Pod trong tenant-a.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: tenant-a
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
---
# 2. DB A chỉ chấp nhận ingress từ invoice-api cùng namespace.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-db-ingress
  namespace: tenant-a
spec:
  podSelector:
    matchLabels:
      app: invoice-db
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: invoice-api
      ports:
        - protocol: TCP
          port: 5432
---
# 3. Phía API được phép mở kết nối tới DB A.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-db-egress
  namespace: tenant-a
spec:
  podSelector:
    matchLabels:
      app: invoice-api
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: invoice-db
      ports:
        - protocol: TCP
          port: 5432
~~~

Đây là **ví dụ một luồng backend cụ thể**. Nếu áp dụng nguyên trạng, các luồng khác của tenant A (người dùng/gateway → API, DNS, log, cấp secret, backup, cập nhật phần mềm...) vẫn bị cô lập khi không có chính sách cho phép tương ứng. Trước khi sử dụng trong hệ thống thật, phải lập danh sách luồng hợp lệ và mở chính xác các tuyến đó.

Giải thích những điểm dễ sai:

1. `podSelector: {}` ở cấp `spec` chọn **mọi Pod trong namespace có NetworkPolicy**.
2. `podSelector` chỉ xuất hiện riêng trong một peer `from` hoặc `to` chọn **Pod trong cùng namespace với NetworkPolicy**. Vì vậy rule trên không cho phép `invoice-api` của tenant B chỉ vì tên nhãn giống nhau.
3. Ingress và egress được đánh giá theo **hai hướng độc lập**: Pod đích phải cho phép ingress, Pod nguồn đang bị cô lập egress phải có rule egress tương ứng.
4. Các NetworkPolicy chuẩn **cộng gộp quyền allow**; một policy khác chọn DB và mở ingress rộng vẫn có thể cho phép tenant B. Không có quy tắc deny riêng được ưu tiên trong Kubernetes NetworkPolicy chuẩn.
5. CNI/network plugin phải **thực thi NetworkPolicy**. Chỉ tạo object YAML không chứng minh lưu lượng đã bị chặn.

### 6.2. Khi thật sự cần luồng DNS

Trong cluster điển hình, DNS chạy ở namespace **`kube-system`**. Có thể thêm một policy egress riêng cho DNS, nhưng **phải kiểm tra nhãn Pod DNS thực tế và cách CNI xử lý DNS Service**:

~~~yaml
# Minh họa; xác minh label k8s-app=kube-dns trên cluster trước khi dùng.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-egress
  namespace: tenant-a
spec:
  podSelector: {}
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

Trong một peer, `namespaceSelector` và `podSelector` đặt cùng mục được hiểu là **AND**: Pod DNS với nhãn mong muốn thuộc namespace kube-system. Viết hai mục `to` tách riêng sẽ tạo **OR** và có thể cho phép nhiều đích hơn dự kiến.

**Lưu ý vận hành:** một số cluster dùng NodeLocal DNSCache, CoreDNS với nhãn khác, hoặc đường Service/NAT mà NetworkPolicy và CNI quan sát theo cách khác. Quy tắc minh họa cần được điều chỉnh cho triển khai thực và kiểm thử từ Pod trong tenant A. Không cho phép egress tới mọi địa chỉ chỉ để khắc phục lỗi DNS.

### 6.3. Namespace chưa phải security boundary hoàn chỉnh

Namespace là cơ chế nhóm tài nguyên và phạm vi RBAC. Nó không tự đặt firewall, cô lập kernel, giới hạn cluster admin hoặc bắt buộc mã hóa traffic. Để dùng namespace theo tenant, cần bổ sung:

- **RBAC/IAM:** tenant A không được tạo, sửa, xóa workload, policy, secret hay nhãn dùng cho bảo mật trong namespace B.
- **Admission/pod security:** hạn chế privileged Pod, hostNetwork, hostPath, capability và quyền truy cập node theo chính sách; đánh giá nguy cơ từ workload có quyền cao.
- **NetworkPolicy/CNI:** default deny ingress/egress trong phạm vi phù hợp và kiểm thử traffic chéo namespace.
- **Service account và secret:** mỗi tenant/workload dùng danh tính riêng, không chia sẻ quyền cloud hoặc token mặc định quá rộng.
- **Quota và giới hạn:** ResourceQuota, LimitRange, HPA và các cơ chế bảo vệ dịch vụ dùng chung nhằm giảm ảnh hưởng khi một tenant tạo quá nhiều Pod/kết nối.
- **Dữ liệu và observability:** PersistentVolume, object storage, log, metric và backup cần được phân quyền tách biệt.

Người có đặc quyền quản trị cluster hoặc tài nguyên node có thể vượt ranh giới namespace. Với tenant không tin cậy nhau và yêu cầu cô lập mạnh, hãy đánh giá **cluster hoặc account riêng, runtime isolation bổ sung và miền quản trị khác nhau**.

## 7. Dịch vụ dùng chung là điểm vượt ranh giới

Trong đa số nền tảng nhiều tenant, không thể tách tuyệt đối mọi thành phần. Những hệ thống chung cần có chính sách riêng:

| Thành phần chia sẻ | Nguy cơ chéo tenant | Biện pháp cần kiểm tra |
|---|---|---|
| **API gateway/ingress** | Route sai tenant, tin header giả mạo, cache trả sai kết quả | Xác thực context, routing có kiểm tra, loại bỏ header không tin cậy, cache key theo tenant |
| **Service-to-service call** | Worker A gọi API B do mạng cho phép | mTLS/identity nếu phù hợp, policy theo endpoint, xác minh tenant context tại dịch vụ đích |
| **Database chung** | Thiếu điều kiện tenant, RLS sai, connection pool giữ tenant trước | Phân quyền theo bản ghi, giới hạn DB role, quản lý transaction/context |
| **Message broker/queue** | Consumer A nhận sự kiện B, topic dùng chung không phân quyền | Namespace/topic/quyền producer-consumer, tenant context được xác thực, kiểm soát dead-letter queue |
| **Cache** | Key trùng nhau giữa tenant, dữ liệu A bị đọc bởi B | Namespacing key, phân quyền và TTL, không cache dữ liệu nhạy cảm sai phạm vi |
| **Object storage** | Bucket/prefix policy sai, URL chia sẻ quá rộng | IAM theo tài nguyên, signed URL hạn chế thời hạn/phạm vi, kiểm tra sở hữu object |
| **Log/metrics/traces** | Dashboard hoặc trace của B hiển thị cho người A | Tenant-aware query, IAM đọc log, redact secret và lọc dữ liệu |
| **Backup/restore** | Khôi phục nhầm tenant hoặc lộ dữ liệu khi xuất bản sao | Mapping sở hữu backup, mã hóa, kiểm tra quyền restore và diễn tập |
| **DNS/secrets/CI-CD** | Secret, route hoặc policy của một tenant ảnh hưởng tenant khác | Phân quyền control plane, xác minh mục tiêu triển khai, audit, kiểm soát thay đổi |

### 7.1. Không dùng tenant context chưa xác minh làm quyền

Đừng truyền một header `X-Tenant-ID` từ Internet qua mọi dịch vụ rồi coi nó là chứng thực. Có thể dùng tenant context **được gateway xác minh và chuyển qua kênh nội bộ tin cậy**, hoặc token ngắn hạn có chữ ký, issuer/audience rõ ràng và quyền tương ứng. Mỗi điểm nhận cần xác định **nguồn ngữ cảnh có thể bị giả mạo hay bypass không**.

Nếu dịch vụ A được phép gọi dịch vụ dùng chung, điều đó chỉ chứng minh quyền kết nối của A. Dịch vụ dùng chung vẫn phải kiểm tra thao tác có nằm trong tenant mà A đang đại diện hợp lệ không.

### 7.2. Cô lập tài nguyên và chống noisy neighbor

**Noisy neighbor** là khi tenant sử dụng nhiều CPU, bộ nhớ, kết nối DB, dung lượng hoặc băng thông khiến tenant khác bị ảnh hưởng. Network segmentation giúp giới hạn đường kết nối nhưng chưa đủ cho khả dụng.

Cần thiết kế quota và rate limit theo tenant/identity ở API gateway, queue, worker, DB connection pool, storage và mạng khi có cơ chế phù hợp. Đối với hệ thống có SLA nghiêm ngặt, cân nhắc worker pool hoặc hạ tầng riêng cho tenant có lưu lượng lớn.

## 8. Threat modeling các đường vượt tenant

Mô hình hóa kẻ tấn công có thể là người dùng hợp lệ của tenant A, một workload A bị chiếm, người vận hành có quyền sai hoặc một yêu cầu từ Internet. Trường hợp **người dùng hợp lệ của A cố truy cập B** rất quan trọng vì quá trình xác thực ban đầu vẫn có thể thành công.

| ID | Điểm bị tấn công | Kịch bản | Tác động | Kiểm soát và bằng chứng |
|---|---|---|---|---|
| T01 | API / object ID | User A thay ID hóa đơn bằng ID của B (Broken Object Level Authorization) | Lộ dữ liệu hoặc sửa bản ghi B | Kiểm tra tenant sở hữu object ở mỗi API; kiểm thử 403/404 đúng cách |
| T02 | Gateway / routing | Header tenant giả mạo được dùng để chọn backend B | Truy cập sai miền tenant | Xác thực tenant context, không tin header ngoài, chặn bypass gateway |
| T03 | Cluster network | NetworkPolicy có selector quá rộng hoặc tồn tại allow-all khác | A kết nối DB/Pod B | Audit toàn bộ policy, default deny, kiểm thử Pod A → Pod B bị chặn |
| T04 | Cloud IAM | Tenant workload dùng role cloud chung quyền đọc bucket B | Lộ file hoặc thay đổi tài nguyên B | Role riêng, quyền tối thiểu, kiểm tra đường đọc object và audit IAM |
| T05 | Shared DB | Connection pool giữ `tenant_id` của request trước | Kết quả truy vấn trộn tenant | Set/reset context theo transaction, RLS đúng quyền, test đồng thời |
| T06 | Queue/cache | Key không có tenant hoặc quyền subscribe topic quá rộng | B nhận dữ liệu A và ngược lại | Partition/key namespace theo tenant, kiểm soát producer/consumer, test chéo |
| T07 | Admin/control plane | Operator A sửa nhãn/policy của B hoặc CI/CD deploy nhầm | Mất ranh giới và gián đoạn diện rộng | RBAC/IAM, phê duyệt, audit, policy-as-code và bảo vệ pipeline |
| T08 | Shared service | Tenant A tạo lượng tải lớn chiếm DB connections/worker | Tenant B không còn tài nguyên | Rate limit, quota, resource isolation, theo dõi theo tenant |
| T09 | Egress/SSRF | Workload A được dẫn truy cập metadata cloud hay endpoint nội bộ của B | Lấy credential hoặc gọi tài nguyên liên miền | Egress policy, hạn chế metadata, kiểm tra URL/redirect, quyền IAM tối thiểu |

Khi ưu tiên rủi ro, phân tích **đường khai thác cụ thể, tài sản, độ nhạy cảm, khả năng xảy ra, ảnh hưởng và kiểm soát đang có**. Không gán mức độ rủi ro chỉ từ tên công nghệ.

### 8.1. Kịch bản: chỉ cần đổi đường dẫn để đọc dữ liệu

Giả sử API cho phép:

~~~http
GET /tenants/tenant-a/invoices/100
GET /tenants/tenant-b/invoices/991
~~~

Người dùng A đăng nhập hợp lệ nhưng ứng dụng chỉ kiểm tra **có phiên đăng nhập**, rồi truy vấn hóa đơn theo ID mà không đối chiếu tenant. Firewall và TLS đều có thể đang hoạt động hoàn hảo, còn dữ liệu B vẫn bị lộ. Lỗi nằm ở **authorization đối tượng**, không phải chỉ ở mạng.

Biện pháp: từ session/token đã xác minh, lấy tập tenant mà chủ thể có quyền; buộc resource lookup theo tenant được phép; kiểm tra quyền trên thao tác và object; áp thêm RLS khi phù hợp. Viết kiểm thử negative với tài khoản tenant A gửi object ID thuộc B.

### 8.2. Kịch bản: mạng tách nhưng control plane vẫn chung

Tenant A ở VPC A, tenant B ở VPC B, nhưng một automation role có thể sửa route/firewall và gắn secret cho cả hai môi trường. Nếu role này bị chiếm, ranh giới mạng có thể bị thay đổi hoặc đường truy cập mới được tạo.

Biện pháp: giới hạn IAM theo phạm vi tenant, tách nhiệm vụ, dùng credential ngắn hạn, phê duyệt thay đổi nhạy cảm và theo dõi audit log. Với yêu cầu cô lập cao, đánh giá account/subscription/project riêng và quyền tổ chức có kiểm soát.

## 9. Quy trình thiết kế và triển khai segmentation theo tenant

### Bước 1 — Xác định ràng buộc và phạm vi

Liệt kê các tenant, loại dữ liệu, nhu cầu tuân thủ/hợp đồng, mức cô lập được cam kết và những thành phần phải dùng chung. Phân biệt **isolation requirement** (mục tiêu) với **implementation** (subnet, namespace, database hoặc cluster cụ thể).

### Bước 2 — Vẽ DFD và inventory luồng

Vẽ gateway, IdP, workload, DB, queue, cache, log, secret manager, DNS, backup, admin và API bên thứ ba. Với mỗi luồng ghi nguồn/đích, tenant sở hữu, dữ liệu, giao thức, cổng, identity, điểm thực thi và owner. Đánh dấu những luồng được phép **xuyên vùng**.

### Bước 3 — Xác định tenant context và quyền quản trị

Chọn nguồn tenant context đáng tin, luồng xác minh membership, cách route đến tài nguyên và cách truyền context giữa các service. Kiểm soát ai có quyền tạo tenant, đổi mapping, sửa namespace label/SG, cấp certificate, truy cập backup và đổi IAM.

### Bước 4 — Thiết kế defense in depth

Xây chính sách **default deny** theo phạm vi phù hợp; cho phép các đường cụ thể bằng firewall, CNI, SG/NSG, service identity và quyền ở ứng dụng/DB. Thêm quota, rate limit và chính sách log. Đảm bảo DNS, giám sát, health check, CI/CD và phương án khôi phục vẫn hoạt động.

### Bước 5 — Kiểm thử positive và negative

Kiểm thử A → A **được phép** theo luồng nghiệp vụ và A → B **bị từ chối** ở các lớp liên quan. Kiểm tra cả trường hợp sai role, sai endpoint, sai cổng, sai tenant claim, thay tag, autoscaling, đổi IP, cache key trùng, token hết hạn và kết nối cũ sau thu hồi quyền.

### Bước 6 — Giám sát và duy trì

Tập hợp flow log/firewall deny, authN/authZ log, CNI events, DB audit và cloud IAM audit với **tenant ID đã xác minh, request ID và dịch vụ nguồn**. Không ghi token, mật khẩu hoặc dữ liệu cá nhân không cần thiết. Rà soát drift policy và quyền admin khi thêm tenant, thay topology hoặc cập nhật phần mềm.

## 10. Ma trận kiểm chứng trước khi đưa vào vận hành

| Ca thử | Nguồn | Đích/thao tác | Kết quả kỳ vọng |
|---|---|---|---|
| P01 | API tenant A | DB tenant A TCP/5432 | Được phép nếu đúng identity và quyền DB |
| N01 | API tenant A | DB tenant B TCP/5432 | Bị chặn ở ranh giới mạng với mô hình có DB tách riêng |
| N02 | User tenant A | Xem hóa đơn B qua API chung | Bị từ chối do không có quyền đối với object B |
| N03 | Pod trong tenant B tự đặt `app=invoice-api` | DB tenant A | Bị chặn khi chính sách và quyền gán nhãn được thiết kế đúng |
| N04 | Workload A | Bucket/secret B qua cloud API | IAM hoặc data policy từ chối |
| N05 | User tenant A | Đọc log hoặc backup tenant B | Bị từ chối theo quyền dữ liệu/observability |
| P02 | Tenant A tạo Pod mới đúng policy | API/DB A được phê duyệt | Vẫn hoạt động sau thay IP, không mở quyền tới B |
| N06 | Tenant A tải lớn vượt quota | Worker/DB chung | Giới hạn theo tenant; B duy trì mức dịch vụ mục tiêu |
| P03 | Đội vận hành có quyền thích hợp | Khôi phục tenant A | Chỉ đúng backup A, có kiểm chứng và audit |

**Không thể dùng cùng một kỳ vọng kiểm tra L3/L4 cho mô hình pool hoàn toàn:** khi A và B đi qua chung một process hoặc database, phân đoạn phải được chứng minh chủ yếu bằng phép kiểm tra quyền ứng dụng, chính sách dữ liệu và quản lý state.

### 10.1. Quan sát Kubernetes bằng lệnh chỉ đọc

Trong cluster được phép quản trị, các lệnh sau giúp đối chiếu label và NetworkPolicy với thiết kế:

~~~bash
kubectl get namespaces --show-labels
kubectl -n tenant-a get pods --show-labels
kubectl -n tenant-a get networkpolicies
kubectl -n tenant-a describe networkpolicy default-deny-all
kubectl -n tenant-b get pods --show-labels
kubectl -n tenant-b get networkpolicies
~~~

Việc **nhìn thấy YAML** mới chứng minh policy đã được lưu vào control plane. Để xác minh enforcement, cần kiểm tra CNI, toàn bộ rule ảnh hưởng endpoint và thực hiện các thử kết nối hợp lệ/từ chối trong môi trường được phép. Nếu không có namespace `tenant-a`/`tenant-b`, các lệnh minh họa sẽ báo không tìm thấy; không tự tạo tài nguyên trên production chỉ để chạy ví dụ.

## 11. Tình huống thực hành

**Bối cảnh:** Một dịch vụ quản lý tài liệu có ba tenant A, B, C. Gateway và API dùng chung; worker xử lý file chạy trong cùng cluster; file được lưu vào một object storage dùng chung theo prefix `tenant-a/`, `tenant-b/`, `tenant-c/`. API hiện nhận tenant ID từ header do client gửi và dùng chung một cloud role có quyền đọc mọi prefix. Mạng giữa các worker chưa có NetworkPolicy, còn log tập trung có một dashboard chung cho mọi người dùng.

Hãy đánh giá:

1. Có những ranh giới tin cậy nào? Các thành phần nào đang chia sẻ quyền xuyên tenant?
2. Vì sao tách namespace sẽ giúp giảm nguy cơ nhưng **không tự sửa** lỗi chọn tenant từ header?
3. Cần thiết kế lại mapping tenant → object storage như thế nào?
4. Những rule ingress/egress và vai trò cloud nào cần giới hạn?
5. Làm sao chứng minh user A, worker A và operator A không thể đọc dữ liệu B?

**Gợi ý đối chiếu:**

- Tenant context phải được **suy ra hoặc xác minh từ danh tính và quyền membership**, không tin header thô. API kiểm tra quyền theo tài nguyên, đối chiếu prefix/object với tenant đã xác minh.
- Dùng identity/role phù hợp cho từng workload/tenant, IAM policy chỉ cho phép tài nguyên cần thiết. Nếu vẫn dùng chung role có quyền rộng, lỗi ở một worker có thể ảnh hưởng toàn bộ object storage.
- Áp NetworkPolicy/segmentation giữa các nhóm Pod, giới hạn egress, kiểm tra secret và quyền triển khai. Kiểm tra cả metadata cloud và service account.
- Tách quyền đọc log và dữ liệu backup theo tenant; bổ sung request ID/tenant ID đã xác minh vào telemetry, lọc token và thông tin nhạy cảm.
- Kiểm thử âm bằng tài khoản A yêu cầu object B, worker A truy cập endpoint B, message/cache sử dụng khóa của B và user A mở dashboard B. Review quyền admin, role và nhãn để đảm bảo không bypass.

## 12. Checklist thiết kế tenant segmentation

- [ ] Đã xác định tenant, tài sản, mức cô lập yêu cầu và các dịch vụ dùng chung.
- [ ] Mọi luồng ingress, east–west, egress, quản trị, DNS, log và backup được thể hiện trong DFD khi liên quan.
- [ ] Tenant context được xác minh từ danh tính có thẩm quyền, không dựa riêng vào URL/header do client tự đặt.
- [ ] Các quyết định API và truy vấn dữ liệu đều gắn với tenant sở hữu tài nguyên và quyền hành động.
- [ ] Có chính sách mạng chỉ mở các nguồn, đích, hướng và cổng cần thiết; kiểm tra cả ingress lẫn egress.
- [ ] Nếu dùng Kubernetes, đã bảo vệ namespace, label, RBAC, service account, workload đặc quyền và CNI enforcement.
- [ ] Nếu dùng cloud, IAM, SG/NSG/firewall, tag và quyền của control plane được đánh giá độc lập.
- [ ] Các thành phần chung (cache, queue, log, object storage, secret, backup) có phạm vi truy cập theo tenant.
- [ ] Có rate limit/quota và bảo vệ tài nguyên chung trước noisy neighbor.
- [ ] Đã kiểm thử luồng hợp lệ A → A và các luồng từ chối A → B ở cả mạng, ứng dụng, dữ liệu, quản trị.
- [ ] Audit log đủ tenant/request context để điều tra nhưng không chứa secret hoặc dữ liệu cá nhân không cần thiết.
- [ ] Có owner, quy trình cập nhật policy và kiểm tra lại khi thêm tenant, thay role, scale, failover hoặc chuyển môi trường.

**Ghi nhớ:** Segmentation theo tenant không chỉ là tách địa chỉ IP hoặc namespace. Một kiến trúc nhiều tenant an toàn cần **đúng ranh giới mạng, đúng danh tính, đúng quyền với từng đối tượng dữ liệu, kiểm soát thành phần dùng chung và bằng chứng kiểm thử chéo tenant**. Đây là nền tảng để hạn chế lateral movement, rò rỉ dữ liệu và sự cố lan rộng trong hệ thống SaaS, cloud và mạng doanh nghiệp.
