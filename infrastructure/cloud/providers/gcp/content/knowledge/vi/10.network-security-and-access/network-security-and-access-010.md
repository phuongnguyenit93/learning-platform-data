# Access Context Manager và truy cập theo ngữ cảnh

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **Access Context Manager** định nghĩa và đánh giá ngữ cảnh của một yêu cầu như thế nào; phân biệt **access policy**, **access level**, **basic/custom conditions** và nơi **thực thi** chính sách.
2. Nhận biết các thuộc tính ngữ cảnh gồm **địa chỉ IP nguồn, vị trí địa lý, danh tính, trạng thái thiết bị** và các access levels phụ thuộc; hiểu giới hạn của từng tín hiệu.
3. Thiết kế **truy cập theo ngữ cảnh** cho ứng dụng nội bộ qua **Identity-Aware Proxy (IAP)** bằng IAM Conditions, và cho Google Cloud APIs qua **VPC Service Controls** khi thích hợp.
4. Tạo, đọc và cập nhật một access level với **gcloud**; biết cách kiểm thử trường hợp hợp lệ và trường hợp bị từ chối trước khi triển khai production.
5. Phân tích nguyên tắc **Zero Trust**, IAM quyền tối thiểu, rủi ro khóa nhầm người dùng, audit logs và tác động đến độ tin cậy, chi phí, vận hành.

## 1. Bài toán: đúng tài khoản chưa chắc đã đủ an toàn

Trong mô-đun **CLOUD_PROVIDERS_GCP**, một tổ chức triển khai project, IAM, VPC, Compute Engine, GKE, Cloud Run, cơ sở dữ liệu, lưu trữ và pipeline phát hành. Nhân viên có thể làm việc tại văn phòng, từ xa hoặc qua thiết bị không được tổ chức quản lý. Chỉ dựa vào việc một tài khoản **có quyền IAM** để cho phép mọi yêu cầu ở bất kỳ ngữ cảnh nào có thể không đáp ứng yêu cầu bảo vệ dữ liệu nhạy cảm.

Ví dụ:

- Một kỹ sư được cấp quyền truy cập **cổng quản trị đơn hàng**. Nhóm bảo mật chỉ muốn họ đăng nhập qua **IAP** khi thiết bị có mã hóa đĩa và khóa màn hình, hoặc khi kết nối từ dải IP doanh nghiệp được tin cậy theo chính sách đã duyệt.
- Nhóm phân tích có quyền IAM đọc **BigQuery**, nhưng dữ liệu trong một project được bảo vệ bởi **VPC Service Controls service perimeter**; các yêu cầu từ ngoài perimeter còn phải đáp ứng các quy tắc nhập vào (ingress).
- Một tài khoản bị lộ mật khẩu hoặc phiên đăng nhập có thể xuất hiện từ mạng và thiết bị bất thường. **Ngữ cảnh yêu cầu** là một tín hiệu bổ sung để giảm rủi ro, không thay thế xác thực mạnh, IAM hay giám sát.

**Access Context Manager (ACM)** là dịch vụ khai báo các **access levels**, tức những tập điều kiện dùng để phân loại một yêu cầu theo thuộc tính ngữ cảnh. **Tạo access level không tự động chặn truy cập.** Bạn phải gắn nó với một cơ chế thực thi có hỗ trợ, chẳng hạn **IAP** hoặc **VPC Service Controls**.

### Phân biệt nhanh ba câu hỏi

| Câu hỏi | Công cụ/lớp chính | Ví dụ |
|---|---|---|
| **Ai đang yêu cầu?** | Identity, xác thực, IAM principal | nhân viên@example.com, service account |
| **Yêu cầu có được phép làm gì?** | IAM roles, permissions, IAM Conditions phù hợp | được truy cập ứng dụng qua IAP, được đọc một bucket |
| **Yêu cầu xuất phát trong ngữ cảnh nào?** | Access Context Manager access levels; tín hiệu thiết bị/IP/nguồn | IP doanh nghiệp, thiết bị mã hóa, nhánh truy cập hợp lệ |
| **Ranh giới dịch vụ hoặc dữ liệu có cho đi qua không?** | VPC Service Controls, IAP hoặc control tương ứng | từ ngoài perimeter có được gọi API dữ liệu hay không |
| **Gói IP có đi tới đích không?** | VPC routes, firewalls, Cloud Armor, load balancing | TCP/443 đến backend của ứng dụng |

Chỉ khi **tất cả lớp kiểm soát liên quan** cho phép, yêu cầu mới có thể thành công. Một access level đạt yêu cầu không tự cấp quyền BigQuery, không bỏ qua IAM và không tự mở cổng VPC.

## 2. Kiến trúc logic của Access Context Manager

~~~mermaid
flowchart TD
    USER["Người dùng / workload gửi yêu cầu"] --> CTX["Ngữ cảnh: principal, IP, region, thiết bị"]
    ORG["Organization-level access policy"] --> L["Access levels: CorpNet, TrustedDevice, AdminAccess"]
    CTX --> L
    L --> IAP["IAP + IAM conditional binding"]
    L --> VPCSC["VPC Service Controls perimeter"]
    IAP --> APP["Ứng dụng nội bộ HTTP(S) / TCP"]
    VPCSC --> API["Google Cloud API và dữ liệu được bảo vệ"]
    IAM["IAM roles / quyền thực tế"] --> IAP
    IAM --> API
~~~

Trong sơ đồ:

1. **Access policy** là đối tượng chứa access levels và service perimeters. Nó có số định danh riêng và được quản lý theo tổ chức/phạm vi được hỗ trợ.
2. **Access level** là một bộ quy tắc đánh giá **đúng/sai** theo ngữ cảnh yêu cầu.
3. **Enforcement point** là nơi dùng kết quả đánh giá: **IAM binding trên tài nguyên IAP** hoặc **service perimeter** và ingress rules.
4. **IAM** vẫn là lớp cấp quyền đối với tài nguyên hoặc ứng dụng.

**Điểm mấu chốt:** Một chính sách về ngữ cảnh chỉ hữu ích khi kết quả đánh giá được **nối vào đường truy cập thật**. Nếu tạo level **CorpNet** nhưng không tham chiếu level đó ở IAP hay perimeter liên quan, hành vi truy cập hiện tại không tự thay đổi.

## 3. Access policy, access level và phạm vi quản trị

### 3.1. Access policy là vùng chứa cấu hình

Một **Access Context Manager access policy** chứa các access levels và các service perimeters thuộc phạm vi của nó.

Google Cloud hỗ trợ:

- **Organization-level access policy**: một chính sách cấp tổ chức. Đây là loại cần dùng với **IAP context-aware access** và có thể dùng cho VPC Service Controls.
- **Scoped access policies**: chính sách ở phạm vi folder hoặc project nhằm phân quyền quản trị **VPC Service Controls**. Tài liệu hiện hành giới hạn loại scoped policy cho VPC Service Controls; không thay thế organization-level policy khi dùng IAP.

Mỗi access policy có **numeric policy ID**, ví dụ **123456789012**. Định danh đầy đủ của level:

~~~text
accessPolicies/123456789012/accessLevels/CorpNet
~~~

Trong đó **123456789012** là **số policy**, không phải project ID hay organization ID. Hai tổ chức có thể dùng cùng tên **CorpNet** nhưng định danh đầy đủ khác nhau. Cách viết **accessLevels** phân biệt chữ hoa/thường: **accesslevels** không tương đương.

### 3.2. IAM quản trị Access Context Manager

Một số role thường gặp:

| Role | Ý nghĩa chính |
|---|---|
| **roles/accesscontextmanager.policyReader** | Đọc các access policies/access levels theo quyền được cấp |
| **roles/accesscontextmanager.policyEditor** | Tạo/cập nhật access policies và levels theo phạm vi được phép |
| **roles/accesscontextmanager.policyAdmin** | Quản trị Access Context Manager theo phạm vi được cấp |
| **roles/iap.httpsResourceAccessor** | Cho phép principal truy cập ứng dụng web được IAP bảo vệ nếu các điều kiện IAM kèm theo thỏa |
| **roles/iap.tunnelResourceAccessor** | Quyền truy cập IAP TCP tunnel tương ứng |

Những role này **không giống nhau**. Người được quyền **sửa access level** có thể ảnh hưởng đến nhiều ứng dụng nếu level đó được tái sử dụng. Nên tách vai trò quản trị policy với người phê duyệt quyền ứng dụng và có review thay đổi.

Với scoped access policies, việc cấp role ở một project thông thường **không mặc nhiên** tạo quyền quản trị scoped policy. Theo tài liệu IAM của Access Context Manager, role cần được cấp ở **organization** hoặc **chính access policy** theo cách được hỗ trợ.

### 3.3. Đổi access level có thể tác động nhiều nơi

Giả sử **TrustedDevice** được dùng trong 5 IAM bindings của IAP và một service perimeter. Nếu quản trị viên sửa level từ “thiết bị mã hóa” thành “bất kỳ thiết bị nào”, nhiều tài nguyên có thể bị nới truy cập đồng thời. Ngược lại, siết điều kiện quá mức có thể khiến nhiều đội không thể làm việc.

Quy trình thay đổi cần có: danh sách nơi tham chiếu level, bản cấu hình cũ, người phê duyệt, thử nghiệm đối tượng bị ảnh hưởng và khả năng rollback.

## 4. Những thuộc tính ngữ cảnh thường dùng

### 4.1. Bảng tín hiệu

| Thuộc tính | Ví dụ điều kiện | Giá trị sử dụng | Giới hạn cần hiểu |
|---|---|---|---|
| **IP subnetworks** | Nguồn ở 203.0.113.0/24 | Nhận diện mạng văn phòng/VPN đã biết | NAT, proxy, IP thay đổi; IP không chứng minh danh tính |
| **Region** | Chỉ nguồn được định vị ở VN/SG | Hạn chế phạm vi địa lý theo chính sách | GeoIP ước lượng; VPN/proxy phản ánh vị trí egress |
| **Members** | Chỉ tài khoản user hoặc serviceAccount cụ thể | Bổ sung điều kiện principal khi loại tiêu thụ hỗ trợ | Không thay thế quyền IAM; nhóm không hỗ trợ trực tiếp trong thuộc tính này |
| **Device policy** | Màn hình khóa, disk encrypted, OS version | Xác nhận thiết bị đáp ứng chính sách | Cần thiết bị được báo cáo và license/MDM/Endpoint Verification thích hợp |
| **Required access levels** | Vừa đạt CorpNet vừa đạt ManagedDevice | Kết hợp level đã có | Sai quan hệ AND/OR có thể mở hoặc khóa truy cập |
| **Custom CEL expression** | Kiểm tra điều kiện không biểu đạt dễ bằng basic level | Điều kiện linh hoạt theo nguồn ngữ cảnh hỗ trợ | Cú pháp/thuộc tính và license có giới hạn; phải thử kỹ |

**Các CIDR 203.0.113.0/24, 198.51.100.0/24 trong bài là dải dành cho tài liệu**, không phải mạng doanh nghiệp có thể dùng thật. Khi triển khai, cần thay bằng **địa chỉ IP public egress thực tế** mà Google Cloud nhìn thấy, không lấy ngẫu nhiên dải subnet private bên trong văn phòng.

### 4.2. IP nguồn không phải luôn là IP máy người dùng

Một nhân viên kết nối qua corporate VPN có thể xuất hiện với **IP public egress của VPN**, không phải IP private trên laptop. Nếu dùng proxy, NAT hoặc dịch vụ trung gian, địa chỉ quan sát ở enforcement point có thể khác với IP người dùng tự thấy trong hệ điều hành.

Các trường hợp cần phân tích:

- VPN nội bộ ra Internet qua một IP pool cố định: allowlist phải dùng pool **public egress** đó.
- Người dùng đổi mạng nhà sang mạng di động: context có thể thay đổi ngay cả khi user và device giống nhau.
- Service account hoặc workload trong Google Cloud gọi API qua **Private Google Access**: thông tin nguồn IP có thể không mang giá trị public IP mà rule IP allowlist mong đợi.
- VPC Service Controls có nhiều cơ chế xử lý request source; không mặc định cho rằng allowlist IP public của Cloud NAT được sử dụng như chính nguồn IP trong mọi luồng truy cập Google APIs.

Với request từ tài nguyên GCP khác project hoặc perimeter, cần đánh giá **ingress rule theo nguồn project/VPC hoặc service account**, không cố suy từ một IP public duy nhất.

### 4.3. GeoIP không phải “người đang ở quốc gia đó”

Điều kiện **regions** dùng mã quốc gia ISO 3166-1 alpha-2, chẳng hạn **VN**, **SG**. Nó dựa vào địa chỉ IP quan sát được. Với VPN ra Internet từ Singapore, yêu cầu có thể được xem là xuất phát từ **SG** dù người dùng vật lý đang ở Việt Nam.

Tài liệu Access Context Manager lưu ý hạn chế với các request chỉ có IP private: vùng địa lý có thể không xác định được. Do đó, geo restriction nên là tín hiệu bổ sung, không phải yếu tố xác thực chính.

### 4.4. Device signals và chuẩn bị thiết bị

Các điều kiện thiết bị phổ biến:

- **requireScreenlock**: yêu cầu có khóa màn hình.
- **allowedEncryptionStatuses: [ENCRYPTED]**: storage đã mã hóa.
- **requireCorpOwned**: thiết bị được xác định là tài sản công ty.
- **requireAdminApproval**: thiết bị đã được quản trị viên phê duyệt.
- **osConstraints**: giới hạn OS và version tối thiểu, có thể kết hợp điều kiện xác minh ChromeOS.

Để dùng device attributes, tổ chức phải chuẩn bị **Endpoint Verification** cho desktop hoặc **MDM** cho mobile theo tài liệu; nhiều tính năng còn yêu cầu **Chrome Enterprise Premium** hoặc license phù hợp. Nếu không có dữ liệu thiết bị đáng tin cậy, level yêu cầu device state có thể từ chối người dùng hợp lệ.

Không mặc định rằng mọi client API, service account hoặc trình duyệt đều gửi device posture đầy đủ. Hãy kiểm tra loại ứng dụng IAP/Context-Aware Access được hỗ trợ trước khi áp dụng.

## 5. Basic access levels và logic điều kiện

**Basic access level** gồm một hoặc nhiều **conditions**. Một condition có thể chứa nhiều thuộc tính như **ipSubnetworks** và **devicePolicy**.

### 5.1. Logic bên trong một condition

Trong một condition, các thuộc tính được kết hợp theo **AND**:

~~~text
Condition A:
  IP thuộc 203.0.113.0/24
  VÀ thiết bị mã hóa
  VÀ thiết bị khóa màn hình
  → A đạt chỉ khi tất cả điều kiện đều đạt
~~~

Các phần tử trong một danh sách cùng loại thường có logic **OR** theo quy tắc thuộc tính, ví dụ IP nằm trong **một trong hai** CIDR được liệt kê. Thuộc tính **negate: true** đảo kết quả của condition theo cơ chế được định nghĩa; đây không phải cách viết allowlist phủ định tùy ý.

### 5.2. Logic giữa nhiều conditions

Khi có **hai conditions** trong cùng basic access level, tùy **combineFunction**:

- **AND**: yêu cầu phải đạt **cả hai** conditions.
- **OR**: yêu cầu đạt **ít nhất một** condition.

Ví dụ mong muốn:

> Chỉ cho nhân viên truy cập nếu họ ở **mạng doanh nghiệp** **và** dùng **thiết bị đã mã hóa**.

Phải dùng **AND**. Nếu vô tình dùng OR, một thiết bị cá nhân chưa mã hóa nhưng ở mạng doanh nghiệp vẫn có thể được xem là đạt; hoặc thiết bị đã mã hóa trên mạng không mong muốn cũng có thể đạt.

| IP thuộc allowlist | Thiết bị mã hóa | **AND** | **OR** |
|---|---|---|---|
| Có | Có | **Cho phép theo level** | Cho phép theo level |
| Có | Không | Không đạt | **Cho phép theo level** |
| Không | Có | Không đạt | **Cho phép theo level** |
| Không | Không | Không đạt | Không đạt |

“Cho phép theo level” ở đây chỉ có nghĩa **level được đánh giá là thỏa**; IAP/IAM hoặc perimeter vẫn thực thi các điều kiện/quyền khác.

### 5.3. Ví dụ basic level đơn giản: CorpNet

Tập điều kiện dạng YAML mà CLI nhận qua **--basic-level-spec**:

~~~yaml
# corp-net.yaml — ví dụ để nhập vào CLI, không phải Kubernetes manifest
- ipSubnetworks:
    - 203.0.113.0/24
    - 198.51.100.0/24
~~~

Hai CIDR trên được kết hợp theo **OR**: IP thuộc một dải là đủ. Tuy nhiên đây vẫn là một condition và chưa ràng buộc trạng thái thiết bị.

### 5.4. Ví dụ kết hợp IP và thiết bị trong cùng condition

~~~yaml
# corp-managed-device.yaml — bắt buộc cả IP và device posture
- ipSubnetworks:
    - 203.0.113.0/24
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

Trong cấu trúc này, điều kiện IP và device policy phải **đồng thời đạt**. Nhóm vận hành cần xác minh trước Endpoint Verification/MDM và license phù hợp. Nếu dùng cơ chế thay thế, chẳng hạn “thiết bị corp-owned có thể truy cập từ mọi mạng”, cần xây dựng **hai conditions có combineFunction=OR** hoặc một biểu thức tùy biến đã review; không sửa ngẫu nhiên các cờ.

### 5.5. Required access levels: tái sử dụng nhưng cần kiểm tra vòng phụ thuộc

Một access level có thể yêu cầu level khác bằng **requiredAccessLevels**:

~~~yaml
- requiredAccessLevels:
    - accessPolicies/123456789012/accessLevels/CorpNet
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

Ví dụ trên chỉ thỏa khi **CorpNet** thỏa **và** device policy thỏa. Những level phụ thuộc phải tồn tại trong policy phù hợp; cần tránh phụ thuộc vòng và ghi nhận những nơi dùng lại để không tạo tác động dây chuyền khi sửa level nền.

## 6. Custom access levels với Common Expression Language

**Custom access level** dùng một tập con của **Common Expression Language (CEL)** để viết điều kiện linh hoạt hơn basic level, chẳng hạn kiểm tra nguồn IP, vùng hoặc thông tin thiết bị/ngữ cảnh từ các nguồn được hỗ trợ.

Ví dụ file YAML đơn giản:

~~~yaml
# trusted-region.yaml — minh họa CEL, không nên dùng geo rule làm điều kiện duy nhất
expression: "origin.region_code in ['VN', 'SG']"
~~~

Ví dụ dùng dải nguồn theo hàm **inIpRange**:

~~~yaml
# trusted-ip.yaml
expression: "inIpRange(origin.ip, ['203.0.113.0/24'])"
~~~

Trong CEL, **origin.ip** và **origin.region_code** có thể không xác định được đối với một số request. Khi thuộc tính thiếu, biểu thức có thể không đánh giá như dự kiến; cần thử luồng yêu cầu thật, không chỉ nhìn việc CLI nhận cú pháp.

### Khi nào nên chọn custom thay vì basic?

Chọn **basic level** nếu chính sách chỉ cần IP/regions/device attributes đơn giản và logic AND/OR rõ ràng. Chọn **custom level** khi điều kiện thực sự cần CEL hoặc data từ hệ thống an ninh/endpoint bên thứ ba theo tính năng được hỗ trợ.

**Advanced Mode** và một số tính năng device/custom access levels có điều kiện cấp phép riêng. Hãy kiểm tra license, thuộc tính CEL được hỗ trợ và tính tương thích với enforcement point trước khi dùng production.

## 7. Access Context Manager không giống IAM Conditions

Cả hai đều có chữ “conditions” nhưng chức năng khác nhau:

| Khả năng | Access Context Manager | IAM Conditions |
|---|---|---|
| Nơi cấu hình | Access policy và access level | Conditional binding trên IAM policy |
| Điều kiện đặc trưng | IP, region, device, members, custom CEL được hỗ trợ | Thuộc tính request/resource/time theo loại permission |
| Tạo quyền truy cập? | **Không** | IAM binding cấp role có điều kiện khi role/permission hợp lệ |
| Có thể kết hợp? | **Có**, khi enforcement point hỗ trợ, ví dụ IAP | IAP có thể tham chiếu access level qua thuộc tính IAM Condition |
| Áp dụng ở mọi API? | Không; phụ thuộc consumer | Cũng không; các thuộc tính chỉ được hỗ trợ ở loại quyền/tài nguyên cụ thể |

Quan trọng: **request.auth.access_levels** trong IAM Conditions có phạm vi hỗ trợ với những yêu cầu đi qua **IAP** như IAP web application và IAP TCP tunneling. Không sao chép điều kiện này lên một IAM binding thông thường của **Cloud Storage/BigQuery/Compute Engine** rồi mặc định API sẽ kiểm tra device context; loại thuộc tính không được hỗ trợ ở những binding đó.

## 8. Thực thi ngữ cảnh với Identity-Aware Proxy (IAP)

### 8.1. IAP bổ sung kiểm soát theo identity và context cho ứng dụng

IAP có thể bảo vệ **web application** phía sau ứng dụng/LB được hỗ trợ, hoặc **TCP forwarding** tới VM/tunnel destination. Người dùng phải được xác thực và đáp ứng IAM role/condition trước khi qua IAP.

~~~mermaid
sequenceDiagram
    participant U as Nhân viên
    participant I as IAP
    participant A as Access Context Manager
    participant IAM as IAM policy của IAP
    participant W as Web app nội bộ
    U->>I: HTTPS request /admin
    I->>A: Đánh giá access levels theo IP/device
    A-->>I: Các access levels thỏa
    I->>IAM: Kiểm tra role và IAM Condition
    alt Đủ quyền và thỏa context
        IAM-->>I: Allow
        I->>W: Chuyển tiếp request
        W-->>U: Response theo ứng dụng
    else Không đủ quyền hoặc context
        IAM-->>I: Deny
        I-->>U: Không được truy cập
    end
~~~

Sơ đồ biểu diễn logic, không phải cam kết thứ tự tất cả lời gọi nội bộ. **IAP và IAM** là enforcement point; access level là dữ liệu ngữ cảnh để đối chiếu.

### 8.2. IAM conditional binding minh họa

Giả sử:

- Organization access policy: **123456789012**.
- Access level: **CorpManagedDevice**.
- Nhóm nhân viên: **platform-team@example.com**.
- Ứng dụng có IAP enable và được bảo vệ qua backend hỗ trợ.

Một binding IAM trên **IAP resource** (đoạn cấu hình để hiểu, không phải policy đầy đủ):

~~~yaml
bindings:
  - role: roles/iap.httpsResourceAccessor
    members:
      - group:platform-team@example.com
    condition:
      title: CorpManagedDeviceOnly
      description: Chỉ nhóm platform từ ngữ cảnh thiết bị được phê duyệt
      expression: "'accessPolicies/123456789012/accessLevels/CorpManagedDevice' in request.auth.access_levels"
~~~

Chỉ khi principal thuộc nhóm được cấp role **và** access level tương ứng có mặt trong **request.auth.access_levels**, binding mới cấp quyền qua IAP.

**Tên IAM role là quyền truy cập ứng dụng**, không phải quyền quản trị ACL của Access Context Manager. Không nhầm role **roles/iap.httpsResourceAccessor** với **roles/accesscontextmanager.policyEditor**.

### 8.3. Kết hợp thêm URL path hoặc time restriction

IAP IAM Conditions có thể dùng các thuộc tính như **request.host**, **request.path** và **request.time** theo phạm vi được hỗ trợ. Ví dụ giới hạn thêm khu vực quản trị của ứng dụng:

~~~text
'accessPolicies/123456789012/accessLevels/CorpManagedDevice'
    in request.auth.access_levels
&&
(request.path == '/admin' || request.path.startsWith('/admin/'))
~~~

Điều kiện trên chỉ áp dụng cho URL path cụ thể theo rule của IAM; phải xét các dạng **URL encoding, normalize path, trailing slash**, endpoint khác dẫn đến cùng hành động và logic routing của backend. Đừng dựa vào path string condition thay cho xác thực/ủy quyền trong ứng dụng.

**Lưu ý bảo mật:** Có thể tồn tại các binding IAP khác cũng cho principal quyền truy cập mà không yêu cầu access level. Các IAM allow bindings được đánh giá theo quy tắc tổng thể, nên cần rà soát **mọi** binding có hiệu lực, cả cấp cao hơn, để không có đường truy cập ngoài ý muốn.

### 8.4. Các bước cấu hình IAP bằng Console

1. Bảo đảm ứng dụng đã chạy phía sau mô hình **IAP supported** và bật IAP theo hướng dẫn.
2. Tạo access level trong **Access Context Manager** của organization-level policy.
3. Vào **Security → Identity-Aware Proxy**; chọn đúng web app/backend service hoặc IAP tunnel resource.
4. Thêm principal hoặc Google Group vào role **IAP-secured Web App User** (hoặc role TCP tương ứng).
5. Thêm **IAM Condition** dựa vào access level đã tạo; kiểm tra tên full resource có đúng số policy và chữ hoa/thường.
6. Test truy cập từ thiết bị đạt chuẩn và thiết bị không đạt chuẩn trước khi áp dụng rộng.
7. Kiểm tra Data Access audit logs của IAP sau khi bật logging cần thiết; theo dõi tỷ lệ denied và phản hồi của người dùng.

Với chính sách nhạy cảm, không sửa project IAM policy bằng cách ghi đè toàn bộ file chỉ để bổ sung một binding IAP. Hãy dùng thao tác API/Console chuyên biệt cho resource IAP và review diff.

### 8.5. IAP và network security khác nhau như thế nào?

IAP bảo vệ request đi qua IAP. Nó không tự động bảo vệ một backend nếu vẫn còn **đường truy cập trực tiếp** không đi qua IAP. Phải kiểm tra cấu hình LB/ingress, firewall, mạng riêng và đường gọi nội bộ đến backend để tránh bypass. Với Cloud Run, GKE, Compute Engine, đường đi và loại backend được hỗ trợ khác nhau; không giả định bật IAP ở một nơi sẽ chặn mọi endpoint.

IAP không thay thế:

- **MFA/2-Step Verification** và bảo vệ tài khoản.
- **IAM roles** cho tài nguyên GCP, ví dụ Storage bucket.
- **Cloud Armor** hoặc firewall để bảo vệ trước lưu lượng không hợp lệ ở các lớp tương ứng.
- Kiểm tra **authorization trong ứng dụng** khi quyết định người nào được xem/sửa đơn hàng.

## 9. Thực thi access levels với VPC Service Controls

### 9.1. Service perimeter dùng để làm gì?

**VPC Service Controls (VPC SC)** tạo một **service perimeter** quanh những project và dịch vụ Google Cloud được hỗ trợ, nhằm giảm nguy cơ truy cập trái phép/exfiltration qua API giữa các ranh giới.

Ví dụ **analytics-prod-001** có BigQuery và Cloud Storage nhạy cảm. Dù một người dùng có IAM role trên dataset hoặc bucket, request từ ngoài perimeter có thể vẫn bị **chặn bởi ranh giới VPC SC** nếu không có đường vào được phép.

~~~mermaid
flowchart LR
    EXT["Client ngoài perimeter"] --> EV{"Access level hoặc<br/>ingress rule hợp lệ?"}
    EV -->|Không| DENY["VPC SC chặn"]
    EV -->|Có| IAM["IAM và các policy khác"]
    IAM -->|Đủ quyền| DATA["BigQuery / Cloud Storage<br/>trong perimeter"]
    IAM -->|Thiếu quyền| DENY2["IAM chặn"]
~~~

**Chặn ở VPC SC và chặn ở IAM là hai nguyên nhân khác nhau.** Không sửa role IAM để xử lý một VPC SC violation khi người dùng vốn đã đủ quyền IAM.

### 9.2. Access levels và ingress rules là hai cơ chế bổ trợ

Theo tài liệu VPC SC:

- Nếu một request từ **ngoài perimeter** tới tài nguyên được bảo vệ **đáp ứng một access level** đã gắn với perimeter **hoặc** đáp ứng một **ingress rule** phù hợp, nó có thể được VPC SC cho phép đi vào.
- Nếu thêm **nhiều access levels** vào perimeter, việc đáp ứng **một** level trong danh sách có thể đủ qua nhánh access levels. Đây là logic **OR**, không phải mặc định AND.
- Một level **không** tự cấp quyền IAM. Sau khi qua perimeter, request vẫn cần quyền trên API/tài nguyên.
- Access levels gắn ở perimeter chủ yếu mở đường cho **truy cập từ bên ngoài vào**; **không** thể dùng access level đó như quy tắc cho mọi đường **egress** từ tài nguyên bên trong ra ngoài.

Ví dụ nếu bạn thêm cả **CorpNet** (IP doanh nghiệp) lẫn **TrustedDevice** (thiết bị quản lý) dưới dạng hai access levels riêng vào perimeter, cách hiểu “phải thỏa cả hai” là **sai** nếu semantics là OR. Muốn cả hai, tạo **một composite access level** kết hợp IP và thiết bị bằng AND, rồi chỉ tham chiếu level đó; hoặc dùng ingress rules được thiết kế chính xác.

### 9.3. Những tình huống access level không thay thế ingress/egress

| Tình huống | Cơ chế cần cân nhắc |
|---|---|
| Người dùng bên ngoài perimeter cần truy cập BigQuery nhạy cảm theo điều kiện IP/device | Access level phù hợp gắn với perimeter, cộng IAM |
| Workload trong project khác cần gọi API được bảo vệ | Ingress rule ràng buộc source project/VPC/service account và API operations, cộng IAM |
| Dịch vụ bên trong perimeter gọi sang tài nguyên khác bên ngoài perimeter | **Egress rule** phù hợp; access level dùng để mở ingress không đủ |
| Hai perimeters cần trao đổi dữ liệu | Ingress/egress ở cả hai phía theo yêu cầu; không kỳ vọng access level đơn lẻ vượt qua mọi ranh giới |
| Muốn giới hạn HTTP path **/admin** của một web app | **IAP + IAM Conditions**, không phải VPC SC cho API perimeter |
| Muốn khóa cổng TCP trên VM | Firewall/IAP TCP hoặc network control tương ứng; access level chỉ hữu ích qua enforcement point hỗ trợ |

**Giới hạn quan trọng:** Access levels không phải cách chuẩn để cho phép một request từ **perimeter khác** đi vào mà bỏ qua egress policy của perimeter nguồn. Với luồng giữa các perimeters, phải phân tích cả **egress nguồn và ingress đích**.

### 9.4. VPC SC không phải tường lửa cho mọi gói dữ liệu

VPC SC bảo vệ những dịch vụ/API hỗ trợ theo cơ chế của Google Cloud. Nó không thay thế:

- **VPC firewall rules** cho lưu lượng VM/endpoint.
- **Cloud Armor** trước các ứng dụng web.
- **Network routing/VPN/Private Service Connect** để có đường đi.
- **Database authentication** hay IAM permissions.
- **Data Loss Prevention** và kiểm soát dữ liệu ở lớp ứng dụng.

Ví dụ bật perimeter cho project chứa Compute Engine không có nghĩa mọi API tự xây trên VM đều được bảo vệ bởi VPC SC. Phải xác định **restricted services** của perimeter và loại request thực tế.

### 9.5. Dry-run trước khi enforcement

VPC SC có **dry-run configuration** để đánh giá ảnh hưởng của perimeter/policies mà chưa thực thi tương đương trên traffic. Nên dùng để quan sát các yêu cầu hợp lệ có thể bị chặn, đặc biệt khi dự án có Cloud Build, GKE, BigQuery, Storage, Artifact Registry và pipeline CI/CD.

Khi chuyển từ dry-run sang enforced, cần:

1. Liệt kê dịch vụ/API và luồng dữ liệu liên project cần thiết.
2. Kiểm tra IAM, caller identity, source project/VPC, destination, method.
3. Tạo ingress/egress policies theo least privilege.
4. Quan sát vi phạm giả định và thực tế qua audit logs.
5. Chuẩn bị phương án rollback trước khi chặn production.

## 10. Hướng dẫn CLI: tạo và đọc access levels

Bài thực hành này chủ yếu **khai báo access level**, chưa tự tạo một ứng dụng IAP hoặc service perimeter. Cần có quyền tổ chức phù hợp; các ID/emails/IP đều là giả định. Không chạy trên production nếu chưa được giao quyền và phê duyệt.

### 10.1. Bước 1 — Tìm organization và access policy hiện có

Giả sử tổ chức có organization ID **987654321098**:

~~~bash
# Liệt kê access policies trong tổ chức
gcloud access-context-manager policies list \
  --organization=987654321098
~~~

Kết quả có thể có **organization-level policy** và các **scoped policies** cho VPC Service Controls. Tìm **numeric policy ID** đúng cho mục đích. Ví dụ đặt **POLICY_NUMBER=123456789012** trong các lệnh phía dưới, nhưng phải thay bằng ID thật từ kết quả.

Nếu tổ chức **chưa có organization-level policy**, quản trị viên phù hợp mới thực hiện tạo nó:

~~~bash
# Ví dụ thao tác quản trị tổ chức; không chạy nếu policy đã tồn tại
gcloud access-context-manager policies create \
  --organization=987654321098 \
  --title="Corporate Access Policy"
~~~

**Một tổ chức không thể tạo hai organization-level access policies cùng vai trò.** Nếu policy đã tồn tại, dùng policy hiện có thay vì tạo tiếp. Scoped policies dành cho các use cases VPC Service Controls cần quản trị tách biệt và không phải lựa chọn thay thế cho IAP.

### 10.2. Bước 2 — Soạn basic access level giới hạn IP

File **corp-net.yaml**:

~~~yaml
# Hai mạng này chỉ là dải tài liệu. Thay bằng public egress IP thật.
- ipSubnetworks:
    - 203.0.113.0/24
    - 198.51.100.0/24
~~~

### 10.3. Bước 3 — Tạo access level

~~~bash
gcloud access-context-manager levels create CorpNet \
  --policy=123456789012 \
  --title="Corporate network" \
  --description="Allow evaluated requests from approved egress networks" \
  --basic-level-spec=corp-net.yaml \
  --combine-function=and
~~~

Trong ví dụ chỉ có một condition nên **combine-function=and** không tạo khác biệt; cờ này có ý nghĩa khi có nhiều conditions. Tạo level không tự cấp quyền IAP hoặc mở VPC SC perimeter.

### 10.4. Bước 4 — Liệt kê và mô tả chính xác

~~~bash
gcloud access-context-manager levels list \
  --policy=123456789012

gcloud access-context-manager levels describe CorpNet \
  --policy=123456789012
~~~

Xác nhận:

- Level nằm dưới đúng **accessPolicies/123456789012**.
- Tên chính xác **CorpNet**.
- Các subnet được lưu đúng.
- Phân loại là basic level và các conditions như kỳ vọng.

### 10.5. Bước 5 — Chuyển sang điều kiện thiết bị khi đủ điều kiện

File **corp-managed-device.yaml**:

~~~yaml
- ipSubnetworks:
    - 203.0.113.0/24
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

Lưu ý cần chuẩn bị Endpoint Verification/MDM và license để thiết bị cung cấp được tín hiệu. Tạo một access level **mới** cho thử nghiệm:

~~~bash
gcloud access-context-manager levels create CorpManagedDevice \
  --policy=123456789012 \
  --title="Managed device on corp network" \
  --description="Approved network AND compliant device" \
  --basic-level-spec=corp-managed-device.yaml \
  --combine-function=and

gcloud access-context-manager levels describe CorpManagedDevice \
  --policy=123456789012
~~~

**Không sửa level đang dùng ở nhiều nơi** trước khi có danh sách người dùng và tài nguyên bị tác động. Có thể tạo level mới rồi thử nghiệm với một ứng dụng IAP staging.

### 10.6. Bước 6 — Cập nhật hoặc sử dụng custom level

Nếu cần thay CIDR của một basic level, soạn file mới rồi update:

~~~bash
gcloud access-context-manager levels update CorpNet \
  --policy=123456789012 \
  --basic-level-spec=corp-net.yaml
~~~

Nếu cần tạo custom level từ CEL file **trusted-region.yaml**:

~~~bash
gcloud access-context-manager levels create TrustedRegion \
  --policy=123456789012 \
  --title="Trusted geographic region" \
  --custom-level-spec=trusted-region.yaml
~~~

Đây là ví dụ cú pháp. **Custom level** có điều kiện tính năng/license, và một rule địa lý đơn lẻ chưa đủ cho hệ thống dữ liệu nhạy cảm. Khi update level production, ghi lại bản cũ, xác minh dependencies và chuẩn bị rollback.

## 11. Kết nối access level vào IAP: quy trình có kiểm soát

Sau khi đã có **CorpManagedDevice**, thiết kế một ứng dụng Java chạy trên GKE/Compute Engine hoặc Cloud Run phía sau load balancer/IAP phù hợp:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Project ứng dụng | **orders-admin-stg** | Chứa ứng dụng staging |
| Ứng dụng | **admin.orders.example.com** | Giao diện quản trị nội bộ |
| Nhóm dùng | **platform-team@example.com** | Người được quyền qua IAP |
| Access policy | **123456789012** | Chứa access levels |
| Access level | **CorpManagedDevice** | IP doanh nghiệp AND thiết bị mã hóa/khóa màn hình |
| Enforcement | **IAP IAM binding** | Cho phép nhóm khi đạt level |

### Quy trình

1. Tạo ứng dụng staging và bật IAP theo mô hình hỗ trợ; kiểm tra authentication hoạt động trước khi thêm điều kiện context.
2. Tạo **CorpManagedDevice** nhưng **chưa** dùng nó cho toàn bộ production.
3. Trong IAP IAM policy của đúng ứng dụng, thêm binding **roles/iap.httpsResourceAccessor** cho nhóm và condition tham chiếu full access level name.
4. Chạy test từ ít nhất bốn ngữ cảnh: IP đúng/device đúng; IP đúng/device không đạt; IP sai/device đúng; IP sai/device không đạt.
5. Test người dùng **không thuộc nhóm** nhưng cùng mạng và thiết bị đạt chuẩn: vẫn phải bị IAM từ chối.
6. Kiểm tra log access và log ứng dụng, xác nhận có thể phân biệt lỗi IAP context với lỗi backend.
7. Chỉ khi kết quả đúng mới nhân rộng policy sang production qua quy trình review.

**Chú ý trải nghiệm người dùng:** thay mạng, ngắt VPN, bật lại máy, hết phiên xác thực hoặc Endpoint Verification chưa cập nhật có thể khiến người dùng bị từ chối. Cần tài liệu xử lý, kênh hỗ trợ và quy trình khẩn cấp **được phê duyệt và kiểm toán**, không tự ý bỏ điều kiện.

## 12. Kết nối access level vào VPC Service Controls

Giả sử tổ chức có service perimeter **prod-data** bảo vệ **analytics-prod-001** với các restricted services phù hợp. Quản trị viên cân nhắc cho phép một nhóm yêu cầu từ mạng doanh nghiệp đi vào khi thỏa **CorpNet**.

### 12.1. Xem perimeter trước

~~~bash
gcloud access-context-manager perimeters list \
  --policy=123456789012

gcloud access-context-manager perimeters describe prod-data \
  --policy=123456789012
~~~

Đọc rõ **resources**, **restrictedServices**, **accessLevels**, các **ingress/egress policies** và trạng thái enforced/dry-run theo tài nguyên đang dùng.

### 12.2. Ví dụ lệnh liên kết access level với perimeter

~~~bash
# Lệnh THAY ĐỔI perimeter, chỉ chạy khi đã được phê duyệt
gcloud access-context-manager perimeters update prod-data \
  --policy=123456789012 \
  --add-access-levels="accessPolicies/123456789012/accessLevels/CorpNet"
~~~

Lệnh trên thêm **CorpNet** vào danh sách access levels hiện có của perimeter, không phải tạo access level mới. Nó có thể **mở thêm đường ingress** cho nhiều danh tính thuộc mạng được chấp nhận, tùy IAM và các rule liên quan. Vì vậy phải xem xét liệu **CorpNet** một mình có quá rộng hay không; đôi khi cần **CorpManagedDevice** hoặc ingress rule có phạm vi identity/API rõ hơn.

### 12.3. Access level trong VPC SC không dùng cho mọi đường đi

- Request **từ ngoài vào** protected service: có thể được cho phép bởi **access level hoặc ingress rule**.
- Request **từ trong ra ngoài**: xem **egress policy**, không dựa vào access level được thêm ở bước 12.2.
- Request từ **perimeter khác**: kiểm tra egress của nguồn và ingress của đích.
- Đối với lời gọi private từ workload Google Cloud, nguồn theo project/VPC/service account có thể phù hợp hơn IP public; dùng **ingress rules** với metadata đúng.

Trước khi áp dụng rộng, ưu tiên thử trong **dry-run** và kiểm tra audit logs. **VPC SC không tự cho người dùng quyền đọc dữ liệu**; IAM vẫn quyết định.

## 13. Zero Trust: thiết kế chính sách theo nhiều lớp

Nguyên tắc **Zero Trust** không đơn giản là “mọi người đều phải dùng VPN”. Nó yêu cầu đánh giá quyền theo danh tính, ngữ cảnh, độ nhạy tài nguyên, thời điểm và rủi ro, thay vì tự tin tưởng yêu cầu chỉ vì nó đến từ một subnet nội bộ.

Một mô hình quản trị minh họa:

~~~mermaid
flowchart TB
    ID["Identity: SSO/MFA + Google Group"] --> DEC["Quyết định truy cập"]
    DEV["Device: managed + encrypted + screenlock"] --> DEC
    NET["Network: corporate egress / địa chỉ nguồn"] --> DEC
    RES["Resource: app IAP hoặc protected API"] --> DEC
    IAM["IAM least privilege"] --> DEC
    DEC -->|Đủ điều kiện| ALLOW["Cho phép theo phạm vi quyền"]
    DEC -->|Thiếu điều kiện| DENY["Từ chối + audit/triage"]
~~~

### 13.1. Ràng buộc theo mức nhạy cảm

| Loại tài nguyên | Kiểm soát ngữ cảnh gợi ý | Cần thêm |
|---|---|---|
| Dashboard quan sát nội bộ | IAP, nhóm được phép, access level theo yêu cầu tổ chức | SSO/MFA, quyền chỉ đọc, audit |
| Cổng quản trị đơn hàng | IAP + managed device + nhóm quản trị, bổ sung network signal khi cần | Ứng dụng kiểm soát role và hành động nhạy cảm |
| BigQuery nhạy cảm | VPC SC perimeter + ingress/egress phù hợp; IAM theo dataset | IAM, audit, review data access |
| Cloud Storage dữ liệu kiểm toán | VPC SC cho protected APIs nếu phù hợp | Bucket IAM, retention, encryption, logging |
| GKE admin interface | IAP phù hợp với ứng dụng web/tunnel | RBAC, network policy, kubeconfig và cluster IAM |
| Cloud Run public API | IAP nếu mô hình bảo vệ app được hỗ trợ, hoặc auth/application access control phù hợp | Không giả định ACM chặn mọi endpoint public |
| CI/CD service account | Workload Identity Federation, IAM và ingress rules nếu cần | Tránh đánh đồng device policy của người dùng với machine workload |

### 13.2. Quy tắc đặt tên và tái sử dụng

Đặt tên theo **ý nghĩa tín hiệu** thay vì tên một ứng dụng, ví dụ:

- **CorpNet**: IP nguồn là mạng egress được duyệt.
- **TrustedDevice**: thiết bị đáp ứng posture cơ bản.
- **CorpManagedDevice**: CorpNet **AND** TrustedDevice.
- **RemoteAdminApproved**: policy được phê duyệt cho người quản trị từ xa.

Khi nhiều ứng dụng cùng tham chiếu level, cách đặt tên và tài liệu phải đủ chính xác để người quản trị hiểu **tác động toàn cục khi sửa**. Không gọi level **HighSecurity** nếu thực chất chỉ kiểm tra IP.

### 13.3. Tách môi trường và quyền thay đổi

Staging cần có chính sách thử trước, nhưng không được làm production dễ truy cập hơn. Những thay đổi mức trust cần review độc lập với thay đổi IAM role. Tách quyền:

- Người xác định **chính sách bảo mật** và owner của level.
- Người quản trị **Access Context Manager**.
- Người quản trị **IAP** của ứng dụng.
- Người quản trị **VPC SC service perimeter**.
- Người chịu trách nhiệm **ứng dụng và dữ liệu**.

Việc ghi nhận approver, mục đích, dự kiến ảnh hưởng và rollback là phần của quy trình vận hành, không phải tính năng tự động của ACM.

## 14. Chẩn đoán lỗi và đánh giá quyền theo ngữ cảnh

### 14.1. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
|---|---|---|
| Tạo level thành công nhưng IAP không đổi hành vi | Level chưa được tham chiếu bởi IAM binding của IAP | IAP IAM policy, full access level name |
| IAP từ chối người dùng trong mạng doanh nghiệp | IP egress không nằm trong CIDR; thiếu device signal; sai group | IP quan sát, VPN, device posture, IAM binding |
| Người dùng trên device cá nhân vẫn qua IAP | Condition dùng OR thay AND hoặc có binding IAP khác không yêu cầu level | Logic level, tất cả IAM bindings hiệu lực |
| Thiết bị đã mã hóa nhưng level không thỏa | Endpoint Verification/MDM chưa triển khai hoặc chưa báo cáo, license không hợp lệ | Device inventory, management status, phiên đăng nhập |
| IAP báo 403 nhưng ứng dụng trả 200 khi vào đường khác | Backend còn lối vào bỏ qua IAP | LB, ingress/firewall, URL khác, network path |
| IAM role BigQuery có rồi mà API vẫn lỗi | VPC SC perimeter violation hoặc IAM/API restriction khác | Cloud Audit Logs, restricted services, ingress/egress |
| Request từ workload ngoài perimeter không khớp IP allowlist | Caller IP hiển thị nội bộ, NAT/Private Google Access | Source project/VPC/identity, ingress rule |
| Thêm nhiều access levels mà cửa mở rộng | Các levels ở perimeter kết hợp theo OR | Composite level nếu muốn AND; review ingress |
| Policy ID trên IAM Condition sai | Nhầm organization ID/project ID hoặc chữ hoa thường trong accessLevels | List policies/levels, full name chính xác |
| Custom CEL hoạt động khác dự kiến | Thuộc tính không khả dụng, syntax/semantics không phù hợp | Attribute reference, kiểm thử case âm tính |
| Một nhóm mất truy cập sau khi đổi level dùng chung | Level có nhiều consumers | Danh sách tham chiếu, diff cấu hình, rollback |
| Không tạo được level vì thiếu quyền | Thiếu ACM Editor/Admin hoặc chính sách scope không đúng | IAM ở organization hoặc policy, license |
| Access level thêm vào perimeter nhưng data vẫn bị chặn | IAM, restricted service, egress/ingress, nguồn perimeter khác | Phân tích violation logs và tổng thể policy |

### 14.2. Cách tách lỗi IAP và ứng dụng

Nếu một web app bị từ chối:

1. Kiểm tra **người dùng đã đăng nhập đúng identity** và thuộc Google Group được cấp IAP role chưa.
2. Kiểm tra **IAM binding được áp dụng trên đúng IAP resource**, condition đúng access level full name.
3. Kiểm tra **IP nguồn quan sát được**; đối chiếu địa chỉ egress thực và CIDR, không dựa vào IP private trên laptop.
4. Kiểm tra **device posture** và trạng thái Endpoint Verification/MDM.
5. Kiểm tra **IAP Data Access audit logs** khi được bật; đối chiếu access levels mà request thực sự thỏa.
6. Nếu IAP đã cho request đi qua, chuyển sang logs của app/backend, health, HTTP status và application authorization.

Một request có thể thỏa **CorpNet** nhưng không thỏa **CorpManagedDevice**; việc nhìn thấy một access level trong log không có nghĩa mọi level đều thỏa.

### 14.3. Cách tách lỗi VPC SC

1. Tìm **perimeter** và **restricted service** có liên quan.
2. Kiểm tra caller ở trong hay ngoài perimeter, identity, nguồn project/VPC và API method.
3. Nếu từ ngoài vào: có access level hoặc ingress rule được chấp nhận không?
4. Nếu từ trong ra ngoài: có egress rule đúng không?
5. Nếu qua hai perimeters: hai phía có chính sách cho phép không?
6. Đối chiếu Cloud Audit Logs với tình trạng IAM; không nới IAM tùy tiện khi nguyên nhân là perimeter.
7. Sửa nhỏ nhất có thể, thử dry-run nếu phù hợp và giám sát sau khi thay đổi.

### 14.4. Không bỏ qua vấn đề về cache, token và độ trễ

Thay đổi membership Google Group, trạng thái thiết bị, IP/VPN hoặc policy có thể mất thời gian để hệ thống và session cập nhật. Với người dùng không vào được ngay sau khi thay đổi, kiểm tra độ trễ cập nhật và session, không lập tức tắt condition. Phân tích theo log timestamp, principal, request path và thay đổi gần nhất.

## 15. Tình huống tổng hợp: cổng quản trị bán hàng và dữ liệu phân tích

Doanh nghiệp **An Thành** vận hành:

- **shop-prod-001**: Cloud Run/Compute Engine phục vụ API và ứng dụng.
- **orders-admin-prod**: web app quản trị đơn hàng, truy cập qua IAP.
- **analytics-prod-001**: BigQuery và Cloud Storage chứa dữ liệu cần kiểm soát.
- **admin-users@example.com**: nhóm nhân sự được phê duyệt quản trị.
- **Văn phòng** có public egress IP ổn định; nhân viên từ xa dùng thiết bị doanh nghiệp.

### 15.1. Yêu cầu bảo mật

1. Chỉ nhóm quản trị được vào **orders-admin**; người dùng phải dùng thiết bị đáp ứng chính sách, có thể bổ sung điều kiện network theo mức rủi ro.
2. Dữ liệu phân tích không được API client bất kỳ từ Internet truy cập chỉ vì caller có IAM role.
3. Tác vụ CI/CD chạy service account cần truy cập một số API đã bảo vệ theo quy trình có ghi log, nhưng không dùng “thiết bị được mã hóa” của nhân viên làm điều kiện giả cho workload.
4. Không làm ngừng hệ thống khi policy được siết: phải có staging test, đường xử lý khẩn cấp được kiểm toán và kế hoạch rollback.

### 15.2. Thiết kế khuyến nghị

| Lớp | Cổng quản trị orders-admin | BigQuery/Storage analytics-prod |
|---|---|---|
| Identity | SSO/MFA và Google Group **admin-users** | User/service account đúng mục đích |
| Context | **CorpManagedDevice** hoặc access level phù hợp với VPN/remote policy | Access level khi truy cập từ ngoài, hoặc ingress rule theo workload |
| Enforcement | **IAP + IAM Condition** | **VPC SC perimeter + ingress/egress rules** |
| IAM | **roles/iap.httpsResourceAccessor** có condition | Dataset/bucket IAM role tối thiểu |
| Network | LB, ingress path, firewall loại bỏ bypass | Route/Private Google Access và VPC SC config theo kiến trúc |
| Vận hành | IAP audit logs, denied rate, app errors | Violation logs, method/project/source attribution |
| Bảo vệ thay đổi | Review nhóm và condition, negative tests | Dry-run, review nguồn dataflow, rollback |

**Không dùng một access level duy nhất như biện pháp bảo vệ tất cả hệ thống.** Việc cùng tên **CorpManagedDevice** được áp dụng khác nhau tùy điểm thực thi, loại client, IP, device signals và IAM.

### 15.3. Ma trận kiểm thử trước phát hành

| Test | Kỳ vọng IAP admin | Kỳ vọng VPC SC analytics |
|---|---|---|
| Đúng nhóm, IP đúng, device đúng | Cho phép vào IAP; ứng dụng vẫn kiểm tra quyền | Chỉ được phép nếu API/IAM/perimeter cùng cho phép |
| Đúng nhóm, IP sai, device đúng | Từ chối nếu level yêu cầu cả hai | Access level IP không thỏa; ingress khác chỉ cho phép nếu được thiết kế |
| Đúng nhóm, IP đúng, device không đạt | Từ chối nếu device bắt buộc | Từ chối qua level; xem các ingress rule khác |
| Không thuộc nhóm, mọi context đúng | **Từ chối bởi IAM** | Từ chối nếu thiếu IAM trên dữ liệu |
| Pipeline CI dùng service account | Chỉ được IAP cho phép nếu mô hình đó được thiết kế riêng | Dùng ingress/egress quy định workload source và IAM |
| Request từ perimeter khác | Không liên quan trực tiếp đến quyền IAP web | Cần egress nguồn và ingress đích |
| Người dùng hợp lệ từ ứng dụng bypass IAP | **Phải chặn đường bypass** | Không liên quan trực tiếp; kiểm tra perimeter của API đích |

### 15.4. Đánh đổi thực tế

- **Bảo mật:** thêm context giảm bề mặt rủi ro, nhưng IP-only có thể cho phép nhiều thiết bị cùng dùng NAT.
- **Khả dụng:** nếu Endpoint Verification hỏng hoặc VPN egress thay đổi, nhân viên hợp lệ có thể bị khóa.
- **Chi phí:** Endpoint management/license, vận hành, audit logs, VPC SC/Cloud services có thể phát sinh chi phí; không có căn cứ mặc định cho rằng Access Context Manager làm tăng phí trên mỗi request. Cần xem bảng giá chính thức của sản phẩm và license.
- **Khả năng mở rộng:** một level được dùng bởi nhiều teams cần change control và quyền ownership rõ ràng.

## 16. Bài tập thực hành

### Bài tập A — Kiểm tra logic access level

Một access level yêu cầu:

~~~yaml
- ipSubnetworks:
    - 203.0.113.0/24
  devicePolicy:
    requireScreenlock: true
    allowedEncryptionStatuses:
      - ENCRYPTED
~~~

Hãy xác định kết quả với bốn yêu cầu:

1. IP trong CIDR, device encrypted, screen lock bật.
2. IP trong CIDR, encrypted nhưng không có screen lock.
3. IP ngoài CIDR, encrypted, screen lock bật.
4. IP ngoài CIDR, thiết bị không báo cáo device posture.

**Đáp án:** Chỉ (1) đạt level nếu tín hiệu thiết bị được xác minh hợp lệ; các trường hợp còn lại không đạt. Đây là **AND giữa các thuộc tính trong cùng condition**.

### Bài tập B — Phân biệt ACM, IAP và IAM

Kỹ sư tạo level **CorpNet**, thêm role **roles/iap.httpsResourceAccessor** cho nhóm quản trị nhưng **không thêm IAM Condition** nào tham chiếu CorpNet. Có chắc IP ngoài doanh nghiệp bị từ chối không?

**Đáp án:** Không. Level chưa được dùng như điều kiện của binding và IAP policy có thể vẫn cho phép theo role. Cần liên kết access level vào IAM Condition của đúng IAP resource và kiểm tra mọi IAM bindings khác.

### Bài tập C — Logic VPC SC nhiều levels

Perimeter **analytics-prod** tham chiếu hai levels: **CorpNet** và **ManagedDevice**. Một client không thuộc CorpNet nhưng có ManagedDevice được đánh giá thỏa. Client có thể vượt qua nhánh access-level ingress của perimeter không?

**Đáp án:** Có thể, vì nhiều access levels trong perimeter được xét theo **OR**. Sau đó client vẫn cần IAM và các điều kiện liên quan. Nếu yêu cầu bắt buộc **cả IP và device**, tạo composite level AND hoặc thiết kế ingress phù hợp.

### Bài tập D — Đọc log để tìm lỗi

Người dùng từ VPN không vào được cổng quản trị sau khi IT đổi IP egress. Một số log IAP cho thấy user đã authenticated nhưng không có **CorpNet** trong danh sách access levels thỏa. Hãy nêu:

1. Những thông tin cần thu thập.
2. Cách xác minh IP thực tế trong request.
3. Vì sao không nên cấp Owner/Editor để giải quyết.
4. Quy trình sửa CIDR an toàn với review, staging test và rollback.

**Gợi ý:** cấp thêm IAM role không làm IP context đúng; phải kiểm tra VPN/public egress, version của access level, IAM Condition và các level phụ thuộc. Thay đổi CIDR cần đánh giá tác động lên mọi consumer.

### Bài tập E — Thiết kế truy cập cho ba loại principal

Thiết kế riêng cho:

- Nhân viên quản trị qua trình duyệt vào web app IAP.
- Java service chạy trên GKE đọc BigQuery trong cùng perimeter.
- Pipeline ngoài Google Cloud dùng Workload Identity Federation để triển khai Cloud Run và phải gọi API bị VPC SC bảo vệ.

**Định hướng:** người dùng web: IAP + IAM + context; GKE workload: IAM + perimeter behavior + nguồn project/VPC; CI: WIF identity, IAM, ingress/egress rules và API methods. Không áp đặt device policy của trình duyệt lên token workload.

## 17. Ghi nhớ và tài liệu tham khảo

**Bảy điểm cần nhớ:**

1. **Access Context Manager định nghĩa access levels**, không tự làm enforcement.
2. **Basic level** kết hợp attributes bên trong condition theo AND; giữa nhiều conditions có **combineFunction=AND hoặc OR**.
3. **Custom level** dùng CEL theo các thuộc tính và license được hỗ trợ; phải thử cả case đúng và case sai.
4. **IAP** có thể dùng **request.auth.access_levels** trong IAM Conditions của role IAP được hỗ trợ. Không áp dụng thuộc tính này mặc định cho IAM role thông thường của mọi Google Cloud API.
5. **VPC Service Controls** có thể dùng access levels để cho request từ ngoài vào perimeter; các access levels trong danh sách có semantics OR; **ingress/egress** và IAM vẫn quan trọng.
6. **IP, vị trí địa lý và trạng thái thiết bị** đều có giới hạn; không tín hiệu nào tự thay thế MFA, IAM hay quản lý endpoint.
7. Mọi thay đổi của access level được nhiều ứng dụng tham chiếu phải có **review, test, logging và rollback**.

**Tài liệu Google Cloud chính thức:**

1. [Access Context Manager overview](https://docs.cloud.google.com/access-context-manager/docs/overview) — access policy, basic/custom levels và cơ chế ngữ cảnh.
2. [Access level attributes](https://docs.cloud.google.com/access-context-manager/docs/access-level-attributes) — IP subnetworks, regions, members, devicePolicy và requiredAccessLevels.
3. [Create a basic access level](https://docs.cloud.google.com/access-context-manager/docs/create-basic-access-level) — YAML conditions và gcloud.
4. [Custom access levels](https://docs.cloud.google.com/access-context-manager/docs/custom-access-levels) — CEL và Advanced Mode.
5. [Access Context Manager access control](https://docs.cloud.google.com/access-context-manager/docs/access-control) — IAM roles và phạm vi quyền.
6. [Create an access policy](https://docs.cloud.google.com/access-context-manager/docs/create-access-policy) — organization-level/scoped policy.
7. [Set up context-aware access with IAP](https://docs.cloud.google.com/iap/docs/cloud-iap-context-aware-access-howto) — IAM conditional binding và IAP audit logs.
8. [IAM Conditions attribute reference](https://docs.cloud.google.com/iam/docs/conditions-attribute-reference) — phạm vi của **request.auth.access_levels**.
9. [Use access levels with VPC Service Controls](https://docs.cloud.google.com/vpc-service-controls/docs/use-access-levels) — perimeter ingress và các giới hạn.
10. [VPC Service Controls ingress and egress rules](https://docs.cloud.google.com/vpc-service-controls/docs/ingress-egress-rules) — ranh giới truy cập và data flow.
11. [gcloud access-context-manager levels create](https://docs.cloud.google.com/sdk/gcloud/reference/access-context-manager/levels/create) — CLI reference và định dạng basic/custom spec.
