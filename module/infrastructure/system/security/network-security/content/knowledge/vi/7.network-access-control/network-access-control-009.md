# Rule theo identity hoặc tag trong Network Access Control

Hãy hình dung một ứng dụng có ba máy chủ API và hai máy chủ cơ sở dữ liệu. Nếu chính sách firewall chỉ viết theo địa chỉ IP, mỗi lần API tự mở rộng (autoscaling), thay node hoặc chuyển subnet, nhóm vận hành có thể phải cập nhật danh sách địa chỉ. Một cách tiếp cận linh hoạt hơn là định nghĩa **“dịch vụ có danh tính `orders-api` được kết nối tới `orders-db` trên TCP/5432”**, hoặc **“workload mang nhãn `role=api` chỉ được gọi nhóm `role=db` qua cổng đã phê duyệt”**.

Đây là ý tưởng của **rule theo identity hoặc tag** trong chương **Network access control**, thuộc module **SECURITY_NETWORK_SECURITY**. Việc liên kết quyền truy cập với danh tính, vai trò và thuộc tính của thiết bị/workload giúp triển khai phân đoạn mạng, firewall, VPN/ZTNA, bảo vệ mạng không dây, kết nối nội bộ và hạ tầng đám mây một cách nhất quán. Tuy nhiên, **identity và tag không có cùng mức độ đảm bảo**; chính sách chỉ đáng tin khi nguồn cấp danh tính, quyền gán nhãn và điểm thực thi rule được bảo vệ.

## 1. Từ rule dựa trên IP đến rule dựa trên ngữ cảnh

### 1.1. Rule mạng truyền thống

Một rule firewall quen thuộc:

~~~text
ALLOW src=10.10.20.0/24  dst=10.10.30.15  protocol=TCP  dport=5432
DENY  src=ANY          dst=10.10.30.15  protocol=TCP  dport=5432
~~~

Ví dụ trên biểu diễn chính sách theo **địa chỉ và cổng**, không phải cú pháp của một sản phẩm cụ thể. Nó dễ triển khai ở lớp mạng, nhưng có một số hạn chế:

- IP có thể thay đổi khi scale, thay máy hoặc triển khai container.
- Nhiều ứng dụng có thể dùng chung subnet, nên cho phép cả subnet dễ mở phạm vi truy cập.
- Địa chỉ IP không tự chứng minh danh tính người dùng, thiết bị hoặc workload đang gửi dữ liệu.
- NAT, proxy và service mesh có thể làm IP mà điểm kiểm soát nhìn thấy khác IP của tác nhân gốc.
- Quyền nghiệp vụ như “nhân viên hỗ trợ chỉ đọc hồ sơ khách hàng được giao” không thể diễn đạt đầy đủ bằng một cặp IP/cổng.

Rule theo identity hoặc tag đưa **ngữ nghĩa về chủ thể và tài nguyên** vào quyết định truy cập. Tuy vậy, mạng vẫn truyền gói dựa vào địa chỉ và giao thức; sản phẩm thực thi có thể **dịch danh tính/nhóm/nhãn thành tập endpoint**, hoặc kiểm tra danh tính ở phiên kết nối. Không phải firewall nào cũng nhận diện người dùng hoặc workload trong mỗi gói tin.

### 1.2. Ba cách mô tả cùng một nhu cầu

| Kiểu rule | Ví dụ logic | Điểm mạnh | Điểm cần lưu ý |
|---|---|---|---|
| **IP/CIDR** | `10.10.20.0/24 -> 10.10.30.15:5432` | Đơn giản, phổ biến, hoạt động ở L3/L4 | Dễ dư quyền khi subnet chứa nhiều hệ thống |
| **Theo tag/nhóm** | `team=orders, role=api -> role=db:5432` | Theo nhóm tài nguyên khi địa chỉ thay đổi | Ai được gán/sửa tag? Hệ thống nào đồng bộ membership? |
| **Theo identity** | `service=orders-api -> service=orders-db:5432` | Bám vào chủ thể được xác thực, phù hợp service-to-service | Cần cấp và xác minh danh tính, quản lý chứng chỉ/token và vòng đời |

**Không có thứ tự an toàn tuyệt đối** giữa ba kiểu. Một tập IP rất hẹp có thể phù hợp cho thiết bị không hỗ trợ identity; trong khi rule gắn tag thiếu kiểm soát có thể cho phép đối tượng tự ý gia nhập nhóm đáng tin.

## 2. Identity và tag khác nhau thế nào?

### 2.1. Identity: danh tính của chủ thể

**Identity** trả lời “ai hoặc cái gì đang yêu cầu truy cập?”. Tùy môi trường, chủ thể có thể là:

| Chủ thể | Ví dụ danh tính | Cách xác minh điển hình |
|---|---|---|
| Người dùng | Tài khoản doanh nghiệp, nhóm nhân viên, vai trò | IdP, SSO, MFA; ngữ cảnh phiên do hệ thống truy cập xác thực |
| Thiết bị | Thiết bị được quản lý, chứng chỉ máy, thuộc tính tuân thủ | 802.1X/EAP-TLS, MDM/EDR, kiểm tra tình trạng thiết bị |
| Workload/service | Service account, workload ID, SPIFFE ID | Chứng chỉ workload, mTLS, token ngắn hạn, attestation tùy nền tảng |
| Tài nguyên cloud | Managed identity, IAM principal, instance/workload role | Cơ chế xác thực danh tính của cloud và chính sách IAM |

**Tên khai báo không phải bằng chứng định danh.** Một HTTP header như `X-User: admin`, một chuỗi `service=orders-api` hoặc hostname trong DNS không trở thành identity đáng tin nếu người gửi có thể tự đặt. Bên nhận phải kiểm tra chứng thực và xác định ai có quyền phát hành thông tin đó.

Danh tính workload dùng để xác thực **dịch vụ đang gọi**, không tự thay thế danh tính **người dùng cuối**. Một API xác thực mTLS tới dịch vụ dữ liệu vẫn phải kiểm tra quyền đọc/ghi của từng người dùng và đối tượng nghiệp vụ khi cần.

### 2.2. Tag/label: thuộc tính được gán cho tài nguyên

**Tag** hoặc **label** là metadata để phân loại tài nguyên, ví dụ:

~~~yaml
environment: production
team: payments
application: checkout
role: api
data-classification: internal
~~~

Ở đây nhãn `role=api` **không phải mật mã xác thực** và không chứng minh rằng dịch vụ thật sự là API được phép. Nó có ý nghĩa khi **control plane đáng tin** quản lý quyền gán nhãn và điểm thực thi lấy membership từ nguồn đáng tin.

Ví dụ của nhiều nền tảng:

- Kubernetes dùng **label selector** của Pod/Namespace để chọn đối tượng trong NetworkPolicy.
- Một số firewall hoặc nền tảng microsegmentation duy trì **nhóm endpoint động** theo tag do control plane quản lý.
- Một số dịch vụ cloud cung cấp **network tag**, nhóm tài nguyên hoặc thuộc tính gắn với chính sách mạng; cú pháp và độ mạnh bảo vệ khác nhau theo nhà cung cấp.
- IAM/ABAC có thể kiểm tra tag tài nguyên/người yêu cầu để quyết định quyền đối với API cloud; điều đó **không đồng nghĩa** firewall mạng tự đọc và thi hành rule IAM.

### 2.3. Chuỗi tin cậy của một tag

Để rule theo tag an toàn, cần trả lời:

1. **Ai tạo nhãn?** Pipeline triển khai, controller, đội vận hành, người dùng hay một dịch vụ tự khai báo?
2. **Ai được sửa?** Có giới hạn RBAC/IAM/admission policy đối với nhãn dùng cho bảo mật không?
3. **Tag được đối chiếu ở đâu?** Firewall, CNI, agent host, gateway hay bộ điều khiển chính sách?
4. **Membership cập nhật thế nào?** Có độ trễ, lỗi đồng bộ hoặc giữ lại quyền khi tài nguyên đã đổi vai trò không?
5. **Khi tag thiếu hoặc không xác minh được thì sao?** Chính sách có từ chối theo mặc định hay chuyển sang một rule quá rộng?

Một nhãn dùng cho báo cáo chi phí có thể cho phép nhiều nhóm chỉnh sửa. Khi dùng chính nhãn ấy làm căn cứ cấp quyền mạng, **quyền sửa nhãn trở thành quyền tác động tới chính sách bảo mật**.

## 3. Mô hình quyết định truy cập

Một quyết định truy cập có thể được mô tả như sau:

~~~text
Decision = Evaluate(
    subject,        # Người dùng, thiết bị hoặc workload đã được nhận diện
    resource,       # Dịch vụ, endpoint, dữ liệu hoặc thao tác đích
    action,         # Connect, read, write, administer...
    context,        # Môi trường, tình trạng thiết bị, thời điểm, rủi ro...
    policy          # Rule đã được phê duyệt
)
~~~

Đó là **mô hình logic**, không phải một API chuẩn dùng chung cho mọi sản phẩm. Với điều khiển mạng L3/L4, `action` thường là **được mở kết nối tới giao thức/cổng nào**. Với L7, `action` có thể là HTTP method, đường dẫn, RPC method hoặc thao tác nghiệp vụ.

### 3.1. RBAC, ABAC và chính sách theo nhóm

| Mô hình | Đối tượng quyết định | Ví dụ | Rủi ro triển khai |
|---|---|---|---|
| **RBAC** (Role-Based Access Control) | Vai trò được gán cho chủ thể | `role=operator` được vào giao diện vận hành | Vai trò quá rộng hoặc không được thu hồi khi đổi công việc |
| **ABAC** (Attribute-Based Access Control) | Thuộc tính chủ thể, tài nguyên, hành động, ngữ cảnh | `team=payments` được gọi dịch vụ của team khi `env=prod` | Thuộc tính không đáng tin, điều kiện khó kiểm toán |
| **Nhóm endpoint theo tag** | Membership của đối tượng mạng | Nhóm `role=frontend` được gọi `role=api` | Ai có quyền gán tag thành viên, chính sách đồng bộ ra sao |
| **Workload identity** | Danh tính được xác thực của workload | SPIFFE ID `orders-api` chỉ được gọi `orders-db` | Cấp phát danh tính sai, mất khóa, thiếu xác minh peer |

Thực tế thường **kết hợp các mô hình**: RBAC/IAM quản trị ai được gán nhãn, ABAC chọn phạm vi tài nguyên, mTLS xác thực workload, còn firewall/CNI giới hạn cổng và đường truy cập.

### 3.2. Nguyên tắc chính sách

- **Default deny:** chỉ mở những quan hệ truy cập có nhu cầu rõ ràng; nơi nào không có hỗ trợ deny-by-default phải thiết kế cách đạt kết quả tương đương.
- **Least privilege:** giới hạn chủ thể, tài nguyên, giao thức, cổng, hướng kết nối và thao tác L7.
- **Không dựa riêng vào vị trí mạng:** ở cùng VLAN, VPC hoặc namespace không đồng nghĩa có cùng quyền.
- **Xác thực trước khi tin thông tin ngữ cảnh:** không tin header, tag hay group tự khai báo từ nguồn không kiểm soát.
- **Phân biệt policy data plane và control plane:** quyền sửa policy/tag, cấp chứng chỉ, gán role có thể mạnh hơn nhiều quyền kết nối thông thường.
- **Có thể kiểm chứng:** rule nào đang có hiệu lực, vì sao một flow được cho phép/từ chối và ai đã thay đổi rule phải truy vết được.

## 4. Kiến trúc điển hình với danh tính và nhãn

~~~mermaid
flowchart LR
    subgraph ID["Control plane: danh tính và quản trị nhãn"]
        I["IdP / PKI / Workload identity"]
        T["Registry nhãn / Controller"]
        P["Policy engine"]
        I --> P
        T --> P
    end
    subgraph TRAFFIC["Data plane: đường truyền"]
        S["Source: app=orders, role=api"]
        E["Enforcement point: firewall / CNI / proxy"]
        D["Destination: role=db"]
        S -->|"Yêu cầu truy cập"| E
        E -->|"Luồng được cho phép"| D
    end
    P -.->|"Phân phối chính sách và membership"| E
    E -.->|"Sự kiện cho phép / từ chối"| O["Log / Giám sát"]
~~~

**Policy Decision Point (PDP)** đánh giá điều kiện và ra quyết định theo mô hình của giải pháp. **Policy Enforcement Point (PEP)** là nơi áp dụng quyết định: switch, firewall, agent, CNI, gateway hoặc proxy. Một sản phẩm có thể gộp hai vai trò, hoặc PEP nhận chính sách đã biên dịch trước thay vì gọi PDP cho mỗi kết nối.

Nếu điểm thực thi chỉ hiểu địa chỉ IP/cổng, danh tính hoặc tag có thể được **biến đổi thành tập địa chỉ được phép**. Điều này đưa thêm vấn đề đồng bộ membership, cập nhật endpoint, NAT/proxy và thời gian thu hồi quyền vào mô hình đe dọa.

### 4.1. Nơi mỗi lớp thực thi hiệu quả

| Lớp | Điều thường thực thi được | Ví dụ |
|---|---|---|
| **Switch/Wi-Fi NAC** | Trạng thái xác thực thiết bị/người dùng, VLAN, role, ACL tùy thiết bị | Thiết bị có chứng chỉ hợp lệ mới được vào vùng nhân viên |
| **Firewall/microsegmentation** | Nhóm nguồn/đích, IP, port, protocol; đôi khi tích hợp user identity | Nhóm workload `role=api` được kết nối TCP/5432 tới nhóm DB |
| **Kubernetes NetworkPolicy** | Chọn Pod/Namespace theo label, cổng và hướng ingress/egress | `app=orders-api` được kết nối `app=orders-db` |
| **Service mesh / API gateway** | mTLS, định danh dịch vụ, policy L7 tùy sản phẩm | Workload có identity đã xác minh mới được gọi RPC nhất định |
| **Application/DB/IAM** | Quyền với object, hàng dữ liệu, API cloud và thao tác nghiệp vụ | Người dùng chỉ đọc đơn hàng thuộc tài khoản của mình |

Không nên coi “đã qua network policy” là bằng chứng quyền dữ liệu. **Quyền kết nối tới dịch vụ và quyền thực hiện hành động bên trong dịch vụ là hai phép kiểm tra khác nhau.**

## 5. Network Access Control cho người dùng và thiết bị: 802.1X

Trong môi trường switch hoặc Wi-Fi doanh nghiệp, **802.1X** là cơ chế điều khiển truy cập dựa trên cổng, phổ biến với EAP và RADIUS:

- **Supplicant:** thiết bị/người dùng yêu cầu vào mạng.
- **Authenticator:** switch hoặc access point thực thi kiểm soát cổng.
- **Authentication server:** thường là RADIUS/AAA, kiểm tra phương thức EAP và thông tin định danh.

~~~mermaid
sequenceDiagram
    participant C as Thiết bị (supplicant)
    participant S as Switch / Access point
    participant R as RADIUS / AAA
    participant N as Mạng được cấp quyền
    C->>S: Yêu cầu kết nối, trao đổi EAP
    S->>R: Chuyển thông điệp xác thực qua RADIUS
    R->>R: Kiểm tra danh tính và chính sách
    R-->>S: Cho phép / từ chối, thuộc tính áp dụng nếu hỗ trợ
    S-->>C: Cập nhật trạng thái cổng / mạng
    C->>N: Chỉ trao đổi theo VLAN / ACL / role được cấp
~~~

Với **EAP-TLS**, thiết bị có thể xác thực bằng chứng chỉ và phía thiết bị phải kiểm tra danh tính máy chủ xác thực theo cấu hình. Tùy năng lực switch, WLAN controller và RADIUS, kết quả có thể ánh xạ người dùng/thiết bị vào **VLAN động**, ACL tải xuống hoặc **security group/role** riêng của nhà sản xuất.

Ví dụ chính sách:

| Identity/thuộc tính | Rule ở điểm truy cập | Quyền mạng |
|---|---|---|
| Thiết bị nhân viên được quản lý, xác thực mạnh và đạt điều kiện posture | Gán nhóm nhân viên | Chỉ đến các dịch vụ nội bộ phục vụ công việc |
| Thiết bị khách đã xác thực theo chính sách khách | Gán mạng khách | Chỉ Internet và dịch vụ cần thiết, không tới mạng dữ liệu nội bộ |
| Thiết bị IoT đã được xác minh, loại `printer` | Gán nhóm thiết bị in | Chỉ kết nối tới print server và dịch vụ quản trị cụ thể |
| Không xác thực hoặc kiểm tra không thành công | Từ chối hoặc đưa vào vùng cách ly theo chính sách | Không có quyền truy cập hệ thống nhạy cảm |

**MAC Authentication Bypass (MAB)** đôi khi được sử dụng cho thiết bị không hỗ trợ 802.1X. Vì địa chỉ MAC có thể bị giả mạo, MAB có mức đảm bảo danh tính yếu hơn EAP-TLS; nên kết hợp vùng mạng hạn chế, theo dõi và quyền tối thiểu thay vì coi MAC là danh tính mạnh.

Trong Zero Trust Network Access (ZTNA), cổng truy cập có thể đánh giá thêm danh tính người dùng, tình trạng thiết bị và quyền tới **ứng dụng đích**, khác với việc cấp một kết nối VPN cho phép truy cập rộng tới cả subnet. Tuy nhiên khả năng, phạm vi và điểm thực thi cụ thể phụ thuộc sản phẩm.

## 6. Rule theo label trong Kubernetes: ví dụ có thể áp dụng

Kubernetes NetworkPolicy cho phép viết rule chọn **Pod/Namespace theo label**. Đây là trường hợp điển hình của chính sách truy cập nhóm động: Pod thay IP nhưng vẫn được chọn nếu nhãn đúng.

Giả sử:

- Namespace `orders` có Pod `app=orders-api`.
- Namespace `payments` có Pod `app=payments-db`, lắng nghe TCP/5432.
- Chỉ nhóm `orders-api` được kết nối tới DB trên cổng đó.

### 6.1. Chặn ingress tới DB trước, mở đúng luồng sau

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-db-default-deny
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: payments-db
  policyTypes:
    - Ingress
  ingress: []
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-db-from-orders
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: payments-db
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
          port: 5432
~~~

Diễn giải chính xác:

1. Policy thứ nhất **chọn các Pod `payments-db` và không khai báo luồng ingress được phép**. Những Pod đó bị cô lập ingress đối với chính sách Kubernetes, trừ các kết nối được cho phép bởi policy khác áp dụng.
2. Policy thứ hai cho phép ingress TCP/5432 **từ Pod `app=orders-api` thuộc Namespace `orders`**. `namespaceSelector` và `podSelector` nằm **trong cùng một mục `from`**, nên điều kiện được kết hợp theo **AND**.
3. Hai NetworkPolicy **cộng gộp các quyền cho phép**. Kubernetes NetworkPolicy chuẩn không có quy tắc `deny` tường minh với độ ưu tiên cao hơn `allow`; một policy ingress rộng khác cùng chọn DB có thể làm phạm vi cho phép lớn hơn dự kiến.
4. Đây là **kiểm soát kết nối mạng**, không xác thực mật mã danh tính ứng dụng và không quyết định ai được đọc hàng dữ liệu nào bên trong database.

Label `kubernetes.io/metadata.name` là nhãn namespace do Kubernetes quản lý ở các phiên bản hỗ trợ (thông dụng từ Kubernetes 1.21). Nếu cluster có cơ chế khác, phải kiểm tra nhãn namespace thực tế và quyền thay đổi nhãn trước khi sử dụng.

### 6.2. Ba lỗi cú pháp/hiểu nghĩa dễ gây mở rộng quyền

**Một mục `from` kết hợp hai selector theo AND:**

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: orders
    podSelector:
      matchLabels:
        app: orders-api
~~~

**Hai mục `from` riêng biệt lại được hiểu theo OR:**

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: orders
  - podSelector:
      matchLabels:
        app: orders-api
~~~

Biểu thức thứ hai có thể cho phép **mọi Pod trong namespace `orders`**, cộng thêm các Pod `app=orders-api` **trong namespace chứa policy** (vì `podSelector` đứng riêng chỉ xét namespace của NetworkPolicy). Đây là phạm vi rất khác với “chỉ orders-api ở orders”.

Ngoài ra, `podSelector: {}` ở **cấp `spec` của NetworkPolicy** chọn toàn bộ Pod trong namespace chứa policy. Một rule quá rộng có thể vô hiệu hóa mục tiêu phân đoạn, kể cả khi bạn đã tạo một policy có tên “default deny”.

### 6.3. Điều kiện để NetworkPolicy thực sự bảo vệ được kết nối

- Cluster phải có **CNI/network plugin hỗ trợ thực thi NetworkPolicy**. Chỉ tạo đối tượng YAML mà dataplane không hỗ trợ có thể không chặn lưu lượng.
- Policy trên giới hạn **ingress ở Pod đích**. Nếu Pod nguồn cũng bị cô lập egress, phải có **egress rule tương ứng** ở phía nguồn thì kết nối mới thành công.
- Các policy khác có thể cho phép thêm lưu lượng. Phải kiểm tra **toàn bộ policy cùng chọn endpoint**, không chỉ hai policy trong ví dụ.
- Các luồng DNS, metrics, service discovery, health check, ingress controller và dịch vụ quản trị phải được xác định riêng; không mở rộng toàn bộ mạng chỉ để “sửa lỗi kết nối”.
- Thực thi NetworkPolicy phụ thuộc implementation, đặc biệt đối với host networking, xử lý traffic trước/sau NAT, đường node-local và các loại traffic đặc biệt. Cần kiểm tra hành vi của CNI thực tế.
- Label dùng để phân quyền phải được quản trị chặt. Người có quyền đổi nhãn Pod hoặc sửa namespace label có thể tác động tới membership của rule.

**NetworkPolicy chuẩn không phải cơ chế kiểm soát FQDN hay danh tính người dùng.** Một số CNI cung cấp chính sách mở rộng như FQDN filtering, identity-aware enforcement hoặc deny policies, nhưng không được suy tính năng đó từ YAML NetworkPolicy chuẩn.

## 7. Cloud: phân biệt tag, security group và IAM

Không có một cú pháp “rule theo tag” chung cho mọi cloud. Cùng cụm từ *tag-based policy* có thể chỉ các cơ chế bảo vệ rất khác nhau:

| Nền tảng / cơ chế | Nhóm được chọn theo gì? | Ý nghĩa bảo mật cần nhớ |
|---|---|---|
| **AWS Security Group** | Quy tắc tham chiếu **security group ID** nguồn/đích trong phạm vi được hỗ trợ, hoặc IP/CIDR | Membership là việc tài nguyên/network interface được gắn SG. **Tag EC2 không tự động là điều kiện nguồn/đích của SG rule** |
| **AWS IAM ABAC** | Tag của principal/resource/request theo policy IAM | Điều khiển hành động qua API cloud; **không tự tạo rule packet filtering ở L3/L4** |
| **Azure Application Security Group + NSG** | ASG nhóm network interface của ứng dụng và dùng trong rule NSG theo điều kiện hỗ trợ | Cho phép diễn đạt nhóm ứng dụng, vẫn cần quản lý quyền thay đổi ASG/NSG |
| **Google Cloud VPC firewall rule dùng network tag** | Tag mạng gắn với VM (theo cách triển khai hỗ trợ) | Có thể chọn VM/nguồn đích theo tag; cần quản trị quyền thay tag và kiểm tra phiên bản/chính sách |
| **Nền tảng microsegmentation / cloud-native firewall khác** | Tag, group, namespace, workload metadata, identity tùy sản phẩm | Cần đọc tài liệu provider để biết nghĩa chính xác, cập nhật membership và giới hạn enforcement |

Ví dụ **logic** về rule giữa nhóm ứng dụng và database:

~~~text
resource-group: app-sg
    purpose: traffic from orders API workloads

resource-group: db-sg
    purpose: traffic to database workloads

allow:
    source-group: app-sg
    destination-group: db-sg
    protocol: TCP
    destination-port: 5432
~~~

Đây **không phải cú pháp thực thi AWS/Azure/GCP**. Khi hiện thực, hãy cấu hình đúng đối tượng SG/ASG/rule theo nhà cung cấp, gắn thành viên vào nhóm đúng cách, kiểm tra chiều lưu lượng và loại bỏ quy tắc CIDR rộng còn tồn tại.

Điểm đặc biệt quan trọng: việc tham chiếu security group thể hiện **membership mạng do cloud quản lý**, không xác thực mật mã rằng process bên trong máy ảo thật sự là `orders-api`. Nếu máy được gắn SG đó bị chiếm quyền, kẻ tấn công có thể tận dụng kết nối đang được cho phép. Với hệ thống nhạy cảm, kết hợp mTLS/service identity, quyền ứng dụng và IAM tối thiểu.

## 8. Kết hợp network policy với workload identity

Một kiến trúc Zero Trust thực tế có thể dùng hai lớp:

1. **Network policy theo nhóm/label:** chỉ Pod trong nhóm nguồn được phép kết nối tới cổng dịch vụ, giảm đường di chuyển ngang (lateral movement).
2. **Policy theo workload identity ở proxy hoặc ứng dụng:** bên nhận xác minh danh tính nguồn (ví dụ chứng chỉ mTLS) và chỉ cho phép những danh tính được phê duyệt gọi API/RPC cụ thể.

Ví dụ một rule **giả lập ở mức ý tưởng**, không thuộc cú pháp của service mesh cụ thể:

~~~yaml
policyId: allow-orders-query
source:
  spiffeId: spiffe://example.org/ns/orders/sa/orders-api
destination:
  spiffeId: spiffe://example.org/ns/payments/sa/payments-db
connection:
  protocol: mTLS
  port: 5432
action: allow
~~~

SPIFFE ID là định danh workload trong miền tin cậy được tổ chức quản lý; phải xác minh chuỗi chứng thực và danh tính của peer theo cơ chế thực tế, không chỉ so sánh một chuỗi `spiffeId` do client truyền trong header. Nếu dùng service mesh, cũng cần xác định proxy nào xử lý kết nối, ứng dụng nào nhận identity đã xác minh và việc bypass proxy có bị chặn không.

**Mô hình đe dọa vẫn cần phân biệt:** source workload bị chiếm nhưng còn chứng chỉ hợp lệ, identity bị cấp sai, tag bị sửa trái phép, proxy không được áp dụng, hoặc API bị khai thác khi kết nối mạng hoàn toàn hợp lệ. Không có một rule nào giải quyết tất cả các trường hợp này.

## 9. Quy trình thiết kế rule theo identity/tag

### Bước 1 — Kiểm kê tài sản và luồng hợp lệ

Ghi rõ **chủ thể nguồn**, **tài nguyên đích**, giao thức/cổng hoặc hành động L7, độ nhạy cảm, vùng mạng và owner. Phân biệt traffic:

- **North–south:** người dùng/đối tác/Internet ↔ gateway/dịch vụ.
- **East–west:** API ↔ database, workload ↔ workload trong hoặc giữa các cụm/VPC.
- **Management/control plane:** nhân viên vận hành, CI/CD, controller ↔ hệ thống quản trị, IAM hoặc cấu hình mạng.

Đừng quên DNS, NTP, cập nhật chứng chỉ, trao đổi với IdP, hệ thống log, backup và health check khi cần. Quy tắc chặt nhưng bỏ qua luồng phụ thuộc hợp lệ có thể gây lỗi gián đoạn sau triển khai.

### Bước 2 — Xác định ngữ nghĩa danh tính và nhãn

Trả lời các câu hỏi:

- Nhãn nào chỉ để quản lý tài nguyên? Nhãn nào **tham gia quyết định quyền**?
- Danh tính do IdP/PKI/control plane nào cấp và xác minh?
- Ai có quyền tạo workload, sửa label, gắn security group, cấp certificate, thay đổi role?
- Có tách quyền giữa đội phát triển ứng dụng và nhóm quản trị security policy không?
- Điều gì xảy ra khi chứng chỉ hết hạn, RADIUS không phản hồi, controller không đồng bộ hoặc dịch vụ chuyển nhóm?

Những label nhạy cảm như `security-zone=restricted` hoặc `allow-db=true` không nên cho bên không được phê duyệt tùy ý thêm/xóa. Dùng RBAC/IAM, admission policy hoặc cơ chế quản trị tương ứng để bảo vệ.

### Bước 3 — Viết chính sách rõ điều kiện

Một bản mô tả cho người review:

~~~yaml
# Đặc tả yêu cầu, KHÔNG phải schema của một nền tảng cụ thể.
policyId: NAC-ORDERS-DB-001
owner: platform-security
source:
  namespace: orders
  workload: orders-api
destination:
  namespace: payments
  workload: payments-db
network:
  protocol: TCP
  destinationPort: 5432
decision: allow
assumptions:
  - Label do control plane quản lý và quyền đổi nhãn được giới hạn
  - Không tồn tại rule khác cho phép đích này từ nguồn rộng hơn
  - Database vẫn tự xác thực và phân quyền truy cập dữ liệu
verification:
  - Pod nguồn hợp lệ kết nối được theo luồng nghiệp vụ
  - Pod không thuộc nhóm nguồn không kết nối được
  - Thay IP hoặc tạo Pod hợp lệ mới không làm mất quyền
~~~

Đặc tả nên chỉ rõ **tiêu chí chấp nhận và tiêu chí từ chối**. Một rule mà chỉ có ca kiểm thử “đúng nhóm kết nối được” có thể đang mở quá rộng.

### Bước 4 — Triển khai theo điểm thực thi

Ở network layer, giới hạn địa chỉ/nhóm/cổng theo nguyên tắc tối thiểu. Ở service layer, xác thực peer và quyền API/RPC. Ở tầng dữ liệu, tài khoản DB và chính sách truy cập đối tượng vẫn cần độc lập. Bảo vệ control plane để tránh trường hợp người dùng tự gán nhãn được phép.

Với thay đổi lớn, nên quan sát traffic trước, triển khai theo nhóm nhỏ và chuẩn bị quy trình khôi phục; thay đổi default deny cùng lúc trên toàn hệ thống có thể cắt cả luồng xác thực/giám sát mà chính policy cần dựa vào.

### Bước 5 — Xác minh và giám sát

Kết hợp ít nhất ba loại bằng chứng:

| Bằng chứng | Cần trả lời |
|---|---|
| **Cấu hình** | Rule nào áp dụng? Endpoint nào thuộc nhóm? Có rule khác mở rộng quyền không? |
| **Lưu lượng/kiểm thử** | Chủ thể hợp lệ có kết nối được; chủ thể không hợp lệ có bị từ chối? |
| **Log và audit control plane** | Ai đã tạo/sửa label, role, SG, chính sách; có cảnh báo khi quyền thay đổi bất thường? |

Chính sách có thể cần thời gian để đồng bộ. **Không được mặc định** việc đổi tag hoặc xóa quyền sẽ ngay lập tức cắt mọi kết nối đã thiết lập; điều này phụ thuộc sản phẩm và trạng thái phiên. Với quyền nhạy cảm, cần biết chính xác cơ chế thu hồi, xử lý connection state và độ trễ cấu hình.

## 10. Các rủi ro đặc thù của identity/tag-based rule

| Rủi ro | Kịch bản | Biện pháp chính |
|---|---|---|
| **Tag tampering** | Người dùng có thể tự đổi `role=api` để được vào nhóm có quyền DB | Giới hạn quyền sửa label/tag, admission control, audit sự kiện |
| **Overbroad selector** | Dùng namespace selector quá rộng hoặc rule allow toàn bộ subnet | Kiểm tra điều kiện AND/OR, review tất cả rule cộng gộp, thử ca từ chối |
| **Stale membership** | Workload đổi vai trò nhưng vẫn nằm trong nhóm được phép vì đồng bộ chậm | Đồng bộ/quét drift, TTL hoặc tái đánh giá, quan sát thay đổi membership |
| **Identity spoofing** | API tin `X-Service-Name` do client đặt thay cho danh tính xác thực | mTLS/chứng thực phù hợp, gateway làm sạch header, xác minh nguồn danh tính |
| **Compromised workload** | Workload hợp lệ bị chiếm, kẻ tấn công dùng kết nối được phép | Giới hạn hành động L7/DB, phân đoạn tiếp, phát hiện bất thường, secrets rotation |
| **Control-plane privilege escalation** | Một role có thể vừa tự gán tag vừa sửa policy cấp quyền | Tách nhiệm vụ, least privilege, phê duyệt thay đổi, audit |
| **Fail-open khi hệ thống danh tính lỗi** | RADIUS/IdP hoặc policy controller không khả dụng khiến fallback cho phép rộng | Thiết kế hành vi lỗi theo mức rủi ro, vùng cách ly, kiểm tra khả dụng phụ thuộc |
| **Policy bypass** | Workload đi qua kênh không được proxy/CNI kiểm soát hoặc endpoint quản trị mở riêng | Kiểm tra dataplane thực, chặn đường tắt, quản lý tất cả interface |
| **Quyền dữ liệu bị bỏ sót** | Kết nối tới DB hợp lệ nhưng tài khoản DB có quyền đọc toàn bộ | AuthN/AuthZ tại ứng dụng/DB, phân quyền hàng dữ liệu, giám sát truy vấn |

Đối với từng rủi ro, ghi rõ **tài sản bị ảnh hưởng, điều kiện xảy ra, chủ sở hữu biện pháp, bằng chứng kiểm tra và rủi ro còn lại**. Không cần chọn một con số ưu tiên chỉ từ tên cơ chế; phải cân nhắc mức phơi bày, tác động và kiểm soát hiện hữu.

## 11. Vận hành và kiểm tra cấu hình

### 11.1. Quan sát Kubernetes bằng lệnh chỉ đọc

Các lệnh dưới đây dành cho cluster được phép quản lý, dùng để **kiểm tra** đối tượng và nhãn; chúng không tự sửa rule:

~~~bash
kubectl get namespaces --show-labels
kubectl -n orders get pods --show-labels
kubectl -n payments get pods --show-labels
kubectl -n payments get networkpolicies
kubectl -n payments describe networkpolicy payments-db-from-orders
~~~

Cần đối chiếu:

- Nhãn của Pod nguồn và đích có đúng không; có workload ngoài dự kiến cùng label không?
- Namespace có nhãn như policy yêu cầu không; ai có thể sửa nhãn?
- Có policy khác cũng chọn `payments-db` và cho phép luồng rộng hơn không?
- CNI của cluster có hỗ trợ NetworkPolicy, có quan sát được từ chối trong dataplane không?
- Các luồng egress của source, DNS và đường quản trị có bị tác động không?

**Đọc YAML và nhìn thấy tên NetworkPolicy chưa đủ chứng minh enforcement.** Cần kiểm thử kết nối từ nguồn hợp lệ và nguồn không hợp lệ trong môi trường được phép, hoặc đối chiếu các tín hiệu từ CNI/firewall. Không dùng các lệnh tạo tải hoặc thay đổi chính sách ngoài phạm vi được cấp quyền.

### 11.2. Phân tích sự cố bằng chuỗi quyết định

Khi kết nối bị từ chối, điều tra theo thứ tự:

1. **Danh tính và membership:** principal/certificate/service account/label có đúng và còn hiệu lực?
2. **Điểm áp rule:** switch, firewall, cloud SG/NSG, CNI, proxy hoặc chính ứng dụng đang từ chối?
3. **Điều kiện policy:** nguồn, đích, hướng, cổng, môi trường, trạng thái thiết bị và điều kiện AND/OR có khớp?
4. **Chính sách khác:** có rule allow rộng, deny ưu tiên hoặc điều kiện egress độc lập ảnh hưởng không? Cách giải quyết xung đột tùy sản phẩm.
5. **Kênh và ứng dụng:** DNS, TLS/mTLS, certificate trust, credential, quyền API/DB có lỗi riêng không?
6. **Control plane:** tag có đồng bộ, identity có bị thu hồi, policy có được đẩy tới mọi điểm thực thi?

Ví dụ API kết nối database thất bại sau khi triển khai NetworkPolicy: trước khi mở `0.0.0.0/0`, hãy xác định Pod nguồn có label đúng, namespace đã được chọn đúng, Pod đích có đang cô lập ingress/egress và tài khoản DB còn hợp lệ. Mở toàn bộ kết nối có thể che giấu lỗi mapping mà tạo rủi ro đáng kể.

## 12. Bài tập tình huống và lời giải gợi ý

Một công ty có ba môi trường `development`, `staging`, `production`. API quản lý đơn hàng chạy nhiều Pod theo autoscaling. Database chỉ dành cho production, trong khi nhóm phát triển có quyền tự thay đổi label của Pod ở namespace của họ.

Yêu cầu nghiệp vụ: **chỉ workload `orders-api` trong namespace production được phép kết nối TCP/5432 tới `orders-db`**. Hệ thống còn có gateway, dịch vụ danh tính và đội trực vận hành.

Hãy phân tích:

1. Vì sao cho phép theo toàn bộ CIDR của cluster chưa đủ chính xác?
2. Chọn selector nguồn/đích thế nào để tránh vô tình mở quyền cho Pod cùng nhãn ở development?
3. Quyền đổi label trở thành rủi ro gì? Cần kiểm soát từ control plane ra sao?
4. Nếu Pod nguồn bị chiếm nhưng nhãn vẫn đúng, điều gì vẫn có thể xảy ra?
5. Cần kiểm thử những ca cho phép và từ chối nào sau khi triển khai?

**Gợi ý đối chiếu:**

- Sử dụng label ứng dụng **kết hợp namespace cụ thể** ở cùng một mục policy peer, chọn chính xác Pod đích và đúng TCP/5432. Đảm bảo các rule khác không cho phép rộng hơn.
- Kiểm soát RBAC/admission đối với namespace và label dùng cho bảo mật; không để tác nhân thông thường tự tạo membership cấp quyền nhạy cảm.
- Kết hợp xác thực workload hoặc credential DB, quyền DB tối thiểu và giới hạn thao tác ứng dụng. Nhãn hợp lệ không làm một workload bị chiếm trở nên an toàn.
- Kiểm thử nguồn production hợp lệ, nguồn staging/development mang cùng `app` label, Pod production không thuộc nhóm, sai cổng, Pod mới được autoscale, Pod bị đổi label, tình huống mất IdP/controller và kết nối đã mở trước khi thu hồi quyền.
- Quan sát log của CNI/firewall, audit thay đổi policy/tag, sự kiện cấp/thu hồi chứng chỉ và log ứng dụng/DB để xác định nguyên nhân.

## 13. Checklist review rule theo identity hoặc tag

- [ ] Có tài sản, chủ thể nguồn, dịch vụ đích và mục đích truy cập rõ ràng.
- [ ] Phân biệt danh tính được chứng thực với nhãn/nhóm do control plane quản lý.
- [ ] Người có quyền cấp identity, gán tag/label, gắn security group và sửa policy được giới hạn.
- [ ] Policy áp dụng least privilege theo source, destination, action, protocol, port và môi trường.
- [ ] Các trường hợp thay IP, autoscaling, thay node và thay role không gây cấp quyền sai.
- [ ] Kiểm tra điều kiện AND/OR, selector rỗng và hiệu ứng cộng gộp của policy theo đúng nền tảng.
- [ ] Có cơ chế phân đoạn ingress/egress, quản lý DNS và luồng điều khiển cần thiết.
- [ ] Xác thực workload/người dùng phù hợp; ứng dụng và database vẫn tự kiểm tra quyền nghiệp vụ.
- [ ] Đã xác minh CNI/firewall/proxy thực sự áp rule, không chỉ tồn tại bản cấu hình.
- [ ] Có ca kiểm thử **được phép** lẫn **bị từ chối** và kiểm tra sau khi đổi nhãn/thu hồi danh tính.
- [ ] Giám sát thay đổi membership, cấp/thu hồi chứng chỉ, drift chính sách và truy cập bất thường.
- [ ] Có owner, lịch review, quy trình xử lý sự cố và phương án khôi phục khi policy gây gián đoạn.

**Ghi nhớ:** **Identity-based rule** cố gắng gắn quyền với một chủ thể đã được xác thực; **tag-based rule** gắn quyền với tập tài nguyên có metadata phù hợp. Cả hai giúp chính sách mạng thích ứng với hạ tầng thay đổi, nhưng bảo mật chỉ đạt được khi **bảo vệ nguồn thông tin nhận dạng, quyền quản lý membership và cơ chế thực thi**, đồng thời duy trì kiểm soát truy cập ở tầng ứng dụng và dữ liệu.
