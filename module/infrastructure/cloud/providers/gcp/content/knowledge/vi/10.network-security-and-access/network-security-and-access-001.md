# VPC firewall rules và xử lý ưu tiên luật trên Google Cloud

> **Chương:** Bảo mật và truy cập mạng  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi một ứng dụng không gọi được API chạy trên Compute Engine hoặc một VM bất ngờ nhận được kết nối từ ngoài Internet, nguyên nhân có thể nằm ở **VPC firewall rules**. Muốn giải thích đúng, cần biết **request đi từ đâu đến đâu, qua VPC nào, thuộc hướng ingress hay egress, rule nào áp dụng và ưu tiên nào được xét trước**. Nếu organization còn gắn hierarchical/network firewall policies, phải tính cả thứ tự giữa các lớp chính sách.

Bài học hướng dẫn cách đọc, cấu hình, so sánh và kiểm chứng VPC firewall rules. Trọng tâm là **priority**: số nhỏ được xét trước, quy tắc cụ thể hơn không mặc nhiên thắng, và DENY chỉ thắng ALLOW cùng mức priority trong lớp classic VPC rules.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích tác dụng và giới hạn của VPC firewall rules đối với VM NIC, GKE nodes, load balancer và đường kết nối hybrid.
2. Xác định đủ các trường **network, direction, action, priority, target, source, destination, protocol/port, disabled, logging**.
3. Tính đúng kết quả ALLOW/DENY trong những tình huống có rule giao nhau, priority trùng và implied actions.
4. Phân biệt classic VPC firewall rules với hierarchical, global/regional network và regional system firewall policies.
5. Dùng network tags hoặc service accounts có kiểm soát để xác định target và sources.
6. Thực hành kiểm kê rule, thiết lập lab ưu tiên luật bằng gcloud, đọc effective firewall rules và log.
7. Phân tích lỗi kết nối và thiết kế rule phù hợp với Compute Engine, GKE, Cloud Run, VPC/VPN, các dịch vụ lưu trữ và cơ sở dữ liệu.

## 1. VPC firewall kiểm soát lưu lượng như thế nào?

VPC là mạng logic trên Google Cloud. Firewall rule của VPC được cấu hình ở phạm vi **một VPC network**, nhưng được thực thi tại những **network interface/tài nguyên đích được hỗ trợ**. Trường hợp dễ hình dung nhất là NIC của Compute Engine VM: rule có thể cho phép hoặc chặn một kết nối mới đi vào hoặc đi ra.

~~~mermaid
flowchart LR
    C["Client"] --> R["DNS / route / VPN / NAT"]
    R --> F["Firewall evaluation"]
    F --> VM["VM backend"]
    VM --> G["Guest OS + application + IAM/TLS"]
    VM --> E["Egress evaluation"]
    E --> D["DB / API / mạng khác"]
~~~

Một kết nối hoàn chỉnh thường phải vượt qua **nhiều lớp độc lập**:

| Lớp | Ví dụ câu hỏi |
|---|---|
| Định tuyến | Máy gửi có route đến IP đích và đường trả lời có hợp lệ không? |
| VPC firewall | Rule nào cho phép/chặn kết nối mới trên NIC đích/nguồn? |
| Hệ điều hành | Guest firewall và daemon có cho phép port đó không? |
| Ứng dụng | Backend có lắng nghe và chấp nhận request, TLS/auth có đúng không? |
| IAM | Principal có quyền gọi Cloud Run, Cloud Storage hay database qua cơ chế phù hợp không? |

Một rule **ALLOW tcp:443** chỉ giải quyết phần firewall trong phạm vi áp dụng. Nó không tạo route, không cấp IAM và không khởi chạy web server.

### 1.1. Ingress và egress nhìn từ target

| Direction | Target | Kết nối mới minh họa |
|---|---|---|
| **INGRESS** | VM NIC nhận gói tin | 10.60.0.10 → 10.60.0.20:8080 |
| **EGRESS** | VM NIC gửi gói tin | 10.60.0.20 → 172.20.5.20:5432 |

Một rule chỉ có **một direction**. Để kiểm soát kết nối mới khởi tạo từ cả hai phía, cần phân tích mỗi hướng theo đúng target. Đừng lấy một rule INGRESS của server làm bằng chứng client được phép EGRESS.

### 1.2. Stateful: traffic trả lời được xử lý khác kết nối mới

VPC firewall rules là **stateful**. Khi kết nối mới được cho phép, gói trả lời phù hợp với trạng thái kết nối cũng được phép đi qua. Bộ theo dõi dùng thông tin tương ứng với **5-tuple** (source IP, destination IP, source port, destination port, protocol), đảo chiều khi nhận response.

~~~mermaid
sequenceDiagram
    participant C as Client 10.60.0.10
    participant F as VPC firewall
    participant B as Backend 10.60.0.20
    C->>F: TCP SYN tới 10.60.0.20:8080
    F->>F: Kiểm tra connection mới
    F->>B: ALLOW nếu có rule phù hợp
    B-->>F: TCP SYN-ACK trả lời
    F->>F: Khớp connection tracking
    F-->>C: Cho phép response hợp lệ
~~~

Không cần một ingress allow ngược chỉ để cho SYN-ACK của connection vừa được phép. Tuy nhiên, nếu backend **tự mở một connection mới** tới client thì đó là flow khác, cần kiểm tra direction tương ứng.

Stateful không bảo đảm mọi phản hồi tới được client: còn có route, NAT, firewall tại chỗ và giới hạn của cơ chế connection tracking. Với traffic phân mảnh hoặc trạng thái kết nối hết hạn, kiểm tra tài liệu protocol cụ thể.

### 1.3. Implied actions với VM NIC

Nếu mọi lớp chính sách liên quan đều không đưa ra kết quả và quá trình đánh giá tới bước cuối, Google Cloud có hành động ngầm định:

- **Ingress tới VM NIC:** **DENY**.
- **Egress từ VM NIC:** **ALLOW**.

Đó là kết quả cuối khi không có rule nào quyết định trước; không phải hai rule hữu hình mà người dùng luôn có thể chỉnh sửa. Với **một số managed Envoy proxy/forwarding rule của internal load balancer**, implied ingress action có thể là **ALLOW**. Vì vậy không áp dụng máy móc kết luận “mọi ingress đều deny” cho mọi loại target.

Một VPC **default** có thể được tạo kèm các rule như **default-allow-internal, default-allow-ssh, default-allow-rdp, default-allow-icmp**, thường priority 65534. Đây là những rule **tạo sẵn**, có thể liệt kê/sửa/xóa theo quyền; chúng khác implied actions. Một **custom VPC** mới thường không có bộ allow ingress đó.

## 2. Thành phần của classic VPC firewall rule

| Thuộc tính | Ý nghĩa | Giá trị ví dụ |
|---|---|---|
| **Name** | Tên duy nhất của rule trong project | allow-api-from-private |
| **Network** | VPC chứa rule | app-vpc |
| **Direction** | INGRESS hoặc EGRESS | INGRESS |
| **Action** | ALLOW hoặc DENY | ALLOW |
| **Priority** | Số nguyên **0–65535**, càng nhỏ ưu tiên càng cao | 900 |
| **Target** | Các NIC/VM mà rule áp dụng | target tag backend |
| **Source** | IP ranges hoặc source tag/SA theo direction | 10.60.0.0/24 |
| **Destination** | IP ranges đích nếu được dùng | 10.60.0.20/32 |
| **Protocol/port** | TCP, UDP, ICMP và destination ports | tcp:8080 |
| **Disabled** | Bỏ qua rule khi bị vô hiệu hóa | false |
| **Logging** | Ghi thông tin connection khớp rule | enabled |

**Các mặc định dễ gây rủi ro:** priority thường là **1000**, direction mặc định là **INGRESS**, target mặc định là **mọi VM trong mạng** nếu không chỉ định, và khi không chọn source ingress IPv4 có thể là **0.0.0.0/0**. Vì vậy không tạo allow rule chỉ với tên và port khi chưa xác định source/target.

### 2.1. Network, target và source có vai trò riêng

~~~text
VPC: app-vpc
  VM A: 10.60.0.10, network tag=client
  VM B: 10.60.0.20, network tag=backend
  VM C: 10.60.0.30, network tag=admin
~~~

Rule có **network=app-vpc**, **target-tags=backend**, **source-ranges=10.60.0.0/24**, **rules=tcp:8080** chỉ khớp kết nối mới đến VM B trên TCP 8080 từ nguồn đúng CIDR. Nó không tự mở cổng VM A hoặc VM C.

**Target tags** khác **source tags**. Target của INGRESS là đối tượng **nhận**; target của EGRESS là đối tượng **khởi tạo kết nối gửi**.

### 2.2. Protocol/port không chỉ là tên dịch vụ

- **tcp:22** là TCP với destination port 22.
- **tcp:443** là TCP với destination port 443.
- **udp:53** là UDP với destination port 53; DNS có thể còn dùng TCP 53.
- **icmp** là ICMP, không phải TCP; ping có thể thất bại khi TCP vẫn hoạt động.
- **tcp** không kèm danh sách port có thể mở rộng tới toàn bộ TCP destination ports theo cấu hình.

Chỉ dùng protocol/port thật sự cần thiết. Tránh mở **all protocols** để xử lý sự cố khi chưa biết luồng chính xác.

### 2.3. IPv4, IPv6 và các giới hạn

CIDR **0.0.0.0/0** bao phủ mọi địa chỉ IPv4 nhưng **không bao phủ IPv6**. Nếu VPC có IPv6, cần xét IPv6 rules/source ranges như **::/0** theo cấu hình được sản phẩm hỗ trợ. Một classic VPC rule không trộn IPv4 và IPv6 ranges trong cùng một rule.

Ngoài ra, một số loại lưu lượng như metadata server của Compute Engine có quy tắc đặc biệt, không nhất thiết chịu classic VPC firewall theo cùng cách. Không dựa vào một deny-all egress để thay thế kiểm soát quyền tới metadata server.

## 3. Thuật toán xử lý priority trong classic VPC rules

Để xét một kết nối mới, trước tiên chỉ lấy các classic rules:

1. Thuộc **đúng VPC** và đang **enabled**.
2. Có **direction** phù hợp.
3. Có **target** phù hợp với NIC/VM.
4. Có source/destination hợp lệ và **khớp IP** của traffic.
5. Có protocol/port khớp request.

Sau đó:

- Chọn **priority có số nhỏ nhất** trong các rule còn khớp.
- Nếu có cả **ALLOW** và **DENY** cùng priority, **DENY thắng**.
- Nếu nhiều rule cùng priority, cùng action, kết quả giống nhau nhưng không nên dựa vào tên rule được báo áp dụng trong logs.
- Nếu không có rule khớp, việc đánh giá có thể **chuyển sang network firewall policies** theo enforcement order của VPC; chỉ cuối cùng mới tới implied action.

~~~mermaid
flowchart TD
    S["Kết nối mới"] --> F["Lọc network, enabled, direction, target, IP, protocol/port"]
    F --> M{"Có classic rule khớp?"}
    M -- "Không" --> NEXT["Lớp policy tiếp theo hoặc implied action"]
    M -- "Có" --> P["Chọn priority nhỏ nhất"]
    P --> T{"ALLOW và DENY cùng priority?"}
    T -- "Có" --> D["DENY"]
    T -- "Không" --> A["Áp dụng action của rule ưu tiên cao nhất"]
~~~

### 3.1. Ưu tiên số nhỏ hơn

| Rule | Priority | Source | Port | Action |
|---|---:|---|---|---|
| allow-app | **800** | 10.60.0.0/24 | tcp:8080 | ALLOW |
| deny-app | 1000 | 10.60.0.0/24 | tcp:8080 | DENY |

Request từ **10.60.0.10** tới backend TCP 8080 được **ALLOW** trong lớp classic rules, vì 800 được xét trước 1000.

### 3.2. DENY chỉ thắng ALLOW khi cùng priority

| Rule | Priority | Source | Port | Action |
|---|---:|---|---|---|
| allow-admin-ssh | 900 | 10.60.0.10/32 | tcp:22 | ALLOW |
| deny-subnet-ssh | 900 | 10.60.0.0/24 | tcp:22 | DENY |

Request **10.60.0.10 → backend:22** khớp cả hai rule, nên **DENY**. Nếu chuyển priority allow-admin về **800** và giữ deny ở 900, request từ admin được **ALLOW**, trong khi client **10.60.0.30** vẫn bị deny.

### 3.3. Độ cụ thể không tự thắng

| Rule | Priority | Source | Port | Action |
|---|---:|---|---|---|
| deny-ssh-all | **500** | 0.0.0.0/0 | tcp:22 | DENY |
| allow-specific-admin | 800 | 10.60.0.10/32 | tcp:22 | ALLOW |

Request từ **10.60.0.10** vẫn bị deny. Không áp dụng nguyên tắc **longest prefix match** của routing để suy priority của firewall. Source /32 cụ thể hơn không tự thắng source /0 khi priority thấp hơn.

### 3.4. Cho phép trùng priority nhưng nên hạn chế

Classic VPC rules cho phép nhiều rule có cùng priority. Nếu hai rule cùng priority, cùng ALLOW, cùng khớp request, kết quả vẫn ALLOW nhưng tên rule được báo là thắng có thể không xác định. Với firewall policy rules thuộc cùng policy, quy tắc uniqueness/priority có khác biệt.

Để dễ chèn rule mới và giải thích log, nhóm có thể dùng các bước nhảy priority **100, 200, 300...** thay vì tăng từng đơn vị. Đây là quy ước nội bộ, không phải phân vùng số do Google Cloud dành riêng.

## 4. Tính kết quả một ma trận có rule chồng nhau

Giả sử VPC **lab-vpc** có VM backend mang network tag **backend**, các classic rules như sau:

| Rule | Priority | Direction | Source/destination | Protocol | Action |
|---|---:|---|---|---|---|
| R1 allow-admin-ssh | 800 | INGRESS | Source 10.60.0.10/32 | tcp:22 | ALLOW |
| R2 deny-ssh | 900 | INGRESS | Source 10.60.0.0/24 | tcp:22 | DENY |
| R3 allow-app | 1000 | INGRESS | Source 10.60.0.0/24 | tcp:8080 | ALLOW |
| R4 deny-app-other | 1200 | INGRESS | Source 0.0.0.0/0 | tcp:8080 | DENY |
| R5 deny-external | 1000 | EGRESS | Destination 203.0.113.0/24 | tcp:443 | DENY |

Giả định không có hierarchical/network policies quyết định trước. Các địa chỉ **203.0.113.0/24** và **198.51.100.0/24** dùng cho ví dụ tài liệu.

| Flow mới | Rule khớp | Kết quả |
|---|---|---|
| 10.60.0.10 → backend:22 | R1 và R2 | **ALLOW**, priority 800 |
| 10.60.0.30 → backend:22 | R2 | **DENY**, priority 900 |
| 10.60.0.30 → backend:8080 | R3 và R4 | **ALLOW**, priority 1000 |
| 10.61.0.10 → backend:8080 | R4 | **DENY**, priority 1200 |
| backend → 203.0.113.5:443 | R5 | **DENY egress** |
| backend → 198.51.100.5:443 | Không khớp R5 | Có thể tới implied **ALLOW egress** |
| 10.60.0.30 → backend:3306 | Không có allow ingress khớp | Implied **DENY ingress VM** nếu lớp khác không quyết định |
| Client → VM không mang tag backend | Các rule target backend không áp dụng | Cần xét rule khác và implied action |

**Tự thử đổi priority:** R2 chuyển từ 900 xuống **700** thì admin SSH bị deny vì 700 thắng 800. Nếu R1 cũng chuyển xuống **700**, vẫn deny vì hai rule cùng priority và khác action.

## 5. Implied actions không thay thế routing, NAT hoặc IAM

**ALLOW egress** không bảo đảm VM truy cập Internet. Để kết nối Internet, VM còn cần đường route, external IP hoặc Cloud NAT/giải pháp tương ứng, DNS và dịch vụ đích hoạt động.

**ALLOW ingress** không bảo đảm TCP handshake thành công. Máy nhận có thể chưa lắng nghe port, guest firewall chặn hoặc route trả về lỗi.

Mạng **default** có thể chứa rule **default-allow-ssh** priority 65534. Một classic rule **deny-ssh** priority 1000 khớp sẽ chặn trước rule default đó. Không nhầm **default-allow-ssh** với implied ingress action.

### 5.1. Source tag và service account có thể mở rộng tập nguồn

Trong ingress classic rule, nếu vừa đặt:

~~~text
source-ranges = 10.60.0.0/24
source-tags   = trusted
~~~

thì tập nguồn là **hợp (OR)** giữa IP ranges và các nguồn khớp tag theo điều kiện được hỗ trợ, **không phải giao (AND)**. Cùng điểm cần chú ý với những tổ hợp source ranges và source service accounts được hỗ trợ.

### 5.2. Egress deny và ingress allow là hai việc khác nhau

Nếu VM A có **egress DENY tcp:5432**, nhưng VM B có **ingress ALLOW tcp:5432** từ A, kết nối mới do A khởi tạo vẫn có thể bị chặn tại A. Rule ingress trên B không tự xóa bỏ egress deny ở A.

## 6. Khi có nhiều lớp firewall policy

Google Cloud có **Cloud Next Generation Firewall (Cloud NGFW)** với nhiều lớp chính sách. Nếu organization gắn hierarchical policy hoặc VPC gắn network firewall policy, **không thể so trực tiếp số priority của hai rule nằm ở hai lớp khác nhau**.

Các lớp cần phân biệt:

- **Hierarchical firewall policies:** policy gắn ở organization hoặc folder, có thể được kế thừa xuống những VPC thuộc các project con.
- **Regional system firewall policies:** do Google quản lý để hỗ trợ một số sản phẩm; không phải bộ policy người dùng tự tạo thông thường.
- **Global network firewall policy:** policy gắn vào VPC có phạm vi toàn mạng.
- **Regional network firewall policies:** policy áp dụng ở region phù hợp của VPC.
- **Classic VPC firewall rules:** các rule tạo bằng **gcloud compute firewall-rules create**, mỗi rule thuộc một VPC.
- **Implied actions:** kết quả cuối khi các lớp trước không kết thúc đánh giá.

### 6.1. Hai enforcement order quan trọng

Thuộc tính VPC **networkFirewallPolicyEnforcementOrder** điều khiển việc global/regional network firewall policies được xét **trước hay sau** classic VPC rules.

| Thứ tự | **AFTER_CLASSIC_FIREWALL** (mặc định) | **BEFORE_CLASSIC_FIREWALL** |
|---:|---|---|
| 1 | Hierarchical firewall policies | Hierarchical firewall policies |
| 2 | Regional system firewall policies | Regional system firewall policies |
| 3 | **Classic VPC firewall rules** | **Global network firewall policy** |
| 4 | Global network firewall policy | Regional network firewall policies |
| 5 | Regional network firewall policies | **Classic VPC firewall rules** |
| 6 | Implied actions | Implied actions |

Trong hierarchical layer, xét policy của **organization trước**, rồi các folder tổ tiên từ cao xuống thấp. Trong mỗi policy, rule được đánh giá theo target/direction/priority của policy đó.

~~~mermaid
flowchart TD
    S["Connection mới"] --> H["Hierarchical policies: org → folders"]
    H --> SYS["Regional system policies"]
    SYS --> MODE{"VPC enforcement order?"}
    MODE -->|"AFTER_CLASSIC"| C1["Classic VPC rules"]
    C1 --> G1["Global network policy"]
    G1 --> R1["Regional network policies"]
    MODE -->|"BEFORE_CLASSIC"| G2["Global network policy"]
    G2 --> R2["Regional network policies"]
    R2 --> C2["Classic VPC rules"]
    R1 --> I["Implied action"]
    C2 --> I
~~~

Sơ đồ chỉ diễn tả **đường đi nếu lớp trước chưa quyết định kết quả**. Một rule ALLOW hoặc DENY khớp trong lớp được xét có thể kết thúc đánh giá; không phải packet luôn đi qua mọi ô.

### 6.2. goto_next khác ALLOW và DENY

Trong một số firewall policy:

- **ALLOW:** cho phép traffic và dừng đánh giá theo cơ chế policy.
- **DENY:** chặn traffic và dừng đánh giá.
- **goto_next:** nhường quyền đánh giá cho policy/lớp tiếp theo.
- Không khớp rule nào trong policy thường dẫn tới hành vi chuyển tiếp tương ứng.

Classic VPC firewall rules chỉ có hai action **ALLOW/DENY**; không dùng **goto_next** như một action của classic rule.

Một số policy hỗ trợ các action bổ sung cho kiểm tra mạng nâng cao, ví dụ chuyển tới security profile group. Khả năng đó phụ thuộc loại policy và cấu hình Cloud NGFW, không nên tự suy diễn từ classic firewall.

### 6.3. Priority chỉ được so trong phạm vi đánh giá

Giả sử organization có hierarchical **DENY tcp:22 từ Internet priority 2000**. Trong VPC có classic **ALLOW tcp:22 priority 100** cùng khớp.

**Kết quả là DENY** vì hierarchical policy được xét trước; con số 100 thấp hơn 2000 không khiến classic rule thắng. Muốn tạo ngoại lệ hợp lệ phải sửa policy ở đúng phạm vi hoặc dùng cơ chế được policy hỗ trợ, sau khi review bảo mật.

Tương tự, network policy **DENY tcp:8080** và classic VPC **ALLOW tcp:8080** có thể cho kết quả khác nhau tùy network firewall policy enforcement order:

- **AFTER_CLASSIC_FIREWALL:** classic ALLOW có thể quyết định trước.
- **BEFORE_CLASSIC_FIREWALL:** network policy DENY có thể quyết định trước.
- Hierarchical và regional system policies vẫn đứng ở trước trong cả hai trường hợp.

**Không thay enforcement order ở production** chỉ để thử sửa một kết nối mà chưa tính tác động tới tất cả ứng dụng.

### 6.4. Cách xác minh nhiều lớp

Cần trả lời theo thứ tự:

1. VPC đang dùng enforcement order nào?
2. Có hierarchical policy nào gắn vào organization/folder tổ tiên của project?
3. Có regional system policies hoặc global/regional network policies không?
4. Rule nào ở **lớp được xét trước** khớp direction, target, source, destination và protocol?
5. Nếu rule đó là **goto_next** hoặc không có rule khớp, đánh giá lớp tiếp theo.
6. Với classic VPC rules, so priority **0–65535** và xử lý tie ALLOW/DENY.
7. Khi tất cả lớp chuyển tiếp, xem implied action của **đúng loại target**.

## 7. Network tags, service accounts và lựa chọn target

### 7.1. Network tags

**Network tag** là chuỗi gắn lên VM để nhóm các máy chịu cùng rule. Ví dụ ba VM trong VPC:

~~~text
web-1:    tag=frontend
api-1:    tag=backend
admin-1:  tag=admin
~~~

Rule **target-tags=backend** áp dụng cho các NIC tương ứng của VM có tag backend trong VPC đó. Tên tag không tự tạo route hay cấp IAM. Người có quyền sửa network tags của VM có thể làm thay đổi những firewall rule áp dụng cho VM, nên phải bảo vệ quyền này.

**Network tags** không phải **resource labels** và cũng không đồng nhất với **secure tags** dùng trong một số Cloud NGFW firewall policy.

### 7.2. Target service account

Classic VPC rules cũng có thể target theo **service account gắn cho VM**, ví dụ **api-runtime@PROJECT_ID.iam.gserviceaccount.com**.

Ưu điểm là danh tính VM thường được quản trị chặt hơn một chuỗi tag tùy ý. Tuy nhiên:

- Một classic rule **không dùng đồng thời** target network tags và target service accounts.
- Cũng có giới hạn khi kết hợp source tags với target service accounts hoặc source service accounts với target tags.
- Ở standalone VPC, service accounts dùng trong tiêu chí phải phù hợp phạm vi project; Shared VPC có quy tắc riêng giữa host/service projects.
- Đổi service account của VM có thể yêu cầu dừng/khởi động lại.
- Trên GKE, tiêu chí service account của VPC rule áp dụng với **node VM**, không phải Kubernetes ServiceAccount của từng Pod.

### 7.3. Những giới hạn của source tag/source service account

Trong classic ingress rules, source network tag/service account chỉ suy ra các địa chỉ IP nguồn **được tài liệu hỗ trợ** của network interface VM trong cùng VPC. Chúng không bao trùm tùy ý toàn bộ source alias IP ranges, public IP hoặc client on-premises.

Nếu nguồn là mạng tại chỗ qua Cloud VPN/Interconnect, thường cần dùng **source CIDR** theo sơ đồ IP, kiểm tra NAT và kết hợp IAM/ứng dụng. Không gán một source tag ở Google Cloud rồi cho rằng nó đại diện cho mọi máy on-premises.

## 8. Thực hành đọc cấu hình hiện tại bằng gcloud

Phần này **chỉ đọc**, có thể chạy trên project đã được cấp quyền. Không cần tạo VM hoặc thay policy.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
VPC="YOUR_VPC_NAME"

# Các classic VPC firewall rules của project.
gcloud compute firewall-rules list \
  --project="$PROJECT_ID" \
  --format="table(name,network,direction,priority,disabled)"

# Chỉ rule của một VPC.
gcloud compute firewall-rules list \
  --project="$PROJECT_ID" \
  --filter="network:$VPC" \
  --format="table(name,direction,priority,sourceRanges,allowed,denied)"

# Chi tiết một rule.
gcloud compute firewall-rules describe "RULE_NAME" \
  --project="$PROJECT_ID" \
  --format=yaml

# VPC config; quan sát enforcement order và network details.
gcloud compute networks describe "$VPC" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

Với mỗi rule, ghi lại:

| Câu hỏi | Giá trị cần tìm |
|---|---|
| Rule đang enabled? | disabled |
| Nó áp dụng cho mạng nào? | network |
| Direction là gì? | INGRESS/EGRESS |
| Priority và action? | priority, allowed hoặc denied |
| Target là ai? | targetTags/targetServiceAccounts hoặc all instances |
| Source/destination? | sourceRanges, destinationRanges, sourceTags, sourceServiceAccounts |
| Port nào? | allowed/denied protocol/ports |
| Có logging? | logConfig |

Nếu một rule không hiện ra, chưa kết luận traffic được phép: còn **network firewall policies, hierarchical policies, regional system policies** và implied actions.

### 8.1. Effective firewall rules của NIC VM

~~~bash
gcloud compute instances network-interfaces get-effective-firewalls \
  "VM_NAME" \
  --zone="ZONE" \
  --network-interface="nic0" \
  --project="$PROJECT_ID"
~~~

Lệnh giúp xem các firewall rules được áp dụng lên **NIC được chọn**, bao gồm nguồn policy được hỗ trợ. Một rule được liệt kê ở đây **không chứng minh rule đó thắng với mọi traffic**: còn phải kiểm tra tuple IP/protocol/port và thứ tự lớp/priority.

Trong **Shared VPC**, mạng thuộc **host project**, VM có thể thuộc **service project**. Người điều tra cần đọc đúng NIC của VM và policy/rules của host network, thay vì chỉ tìm trong service project.

## 9. Lab tạo firewall rules có ngoại lệ priority

Lab này **tạo tài nguyên và có thể phát sinh chi phí**, chỉ thực hiện trong project học tập được phép. Ví dụ chọn VPC custom để tránh các allow ingress có sẵn của default VPC.

### 9.1. Thông số và yêu cầu

| Thành phần | Giá trị lab |
|---|---|
| Project | YOUR_PROJECT_ID |
| VPC | firewall-priority-lab |
| Subnet/region | demo-subnet / asia-southeast1 |
| CIDR | 10.60.0.0/24 |
| Admin VM | 10.60.0.10 |
| Ordinary client VM | 10.60.0.30 |
| Backend VM | 10.60.0.20, network tag backend |
| API | TCP 8080 |
| SSH | TCP 22 |

Chính sách mong muốn:

- ALLOW TCP **8080** từ **10.60.0.0/24** vào backend.
- DENY TCP **22** từ subnet vào backend.
- Tạo ngoại lệ ALLOW TCP **22** cho đúng admin IP **10.60.0.10/32**, với priority cao hơn deny.
- Không mở một rule SSH/RDP cho **0.0.0.0/0**.

~~~mermaid
flowchart LR
    ADMIN["10.60.0.10 admin"] -->|"TCP 22 ALLOW; TCP 8080 ALLOW"| B["10.60.0.20 backend"]
    CLIENT["10.60.0.30 client"] -->|"TCP 22 DENY; TCP 8080 ALLOW"| B
    INTERNET["Internet"] -. "Không có allow ingress mới" .-> B
~~~

### 9.2. Tạo VPC và subnet

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
VPC="firewall-priority-lab"
SUBNET="demo-subnet"

# THAY ĐỔI — chỉ làm trong project lab.
gcloud compute networks create "$VPC" \
  --project="$PROJECT_ID" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --range="10.60.0.0/24"

# CHỈ ĐỌC — xác nhận.
gcloud compute networks describe "$VPC" --project="$PROJECT_ID"
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Trước khi chọn CIDR, bảo đảm nó không chồng lấn với VPC khác hoặc mạng hybrid có kết nối. Rule firewall không thể giải quyết lỗi route khi CIDR bị chồng lấn.

### 9.3. Rule ALLOW TCP 8080

~~~bash
# THAY ĐỔI — chỉ target VM có tag backend.
gcloud compute firewall-rules create "lab-allow-api" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --source-ranges="10.60.0.0/24" \
  --target-tags="backend" \
  --rules="tcp:8080" \
  --enable-logging
~~~

### 9.4. Rule DENY TCP 22

~~~bash
# THAY ĐỔI — deny SSH từ subnet tới backend.
gcloud compute firewall-rules create "lab-deny-ssh" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=900 \
  --action=DENY \
  --source-ranges="10.60.0.0/24" \
  --target-tags="backend" \
  --rules="tcp:22" \
  --enable-logging
~~~

### 9.5. Ngoại lệ ALLOW TCP 22 cho admin

~~~bash
# THAY ĐỔI — chỉ cho 10.60.0.10/32 với priority cao hơn deny.
gcloud compute firewall-rules create "lab-allow-admin-ssh" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=800 \
  --action=ALLOW \
  --source-ranges="10.60.0.10/32" \
  --target-tags="backend" \
  --rules="tcp:22" \
  --enable-logging
~~~

**Đối chiếu theo priority:**

| Source | Port đích | Rule trong lớp classic | Kết quả |
|---|---:|---|---|
| 10.60.0.10 | 22 | lab-allow-admin-ssh, priority 800 | ALLOW |
| 10.60.0.30 | 22 | lab-deny-ssh, priority 900 | DENY |
| 10.60.0.10 | 8080 | lab-allow-api, priority 1000 | ALLOW |
| 10.60.0.30 | 8080 | lab-allow-api, priority 1000 | ALLOW |
| IP ngoài CIDR | 8080 | Không có lab allow | Implied deny VM nếu policy khác không quyết định |

Đây là **ví dụ hiểu priority**, không phải khuyến nghị mở SSH trực tiếp trong production. Với production có thể dùng IAP, OS Login và những cơ chế quản trị được phê duyệt.

### 9.6. Xác minh bộ rule đã ghi

~~~bash
gcloud compute firewall-rules list \
  --project="$PROJECT_ID" \
  --filter="network:$VPC" \
  --sort-by="priority" \
  --format="table(name,priority,direction,sourceRanges,allowed,denied,targetTags)"

gcloud compute firewall-rules describe "lab-allow-admin-ssh" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

**Để kiểm thử thật**, cần VM backend có network tag **backend**, IP đúng, OS firewall phù hợp và một ứng dụng đang lắng nghe TCP 8080. Chỉ tạo firewall rule **không mở một dịch vụ**. Có thể dùng VM đã được chuẩn bị sẵn trong project học tập.

Nếu tạo VM mới, lưu ý:

- Chỉ dùng máy thử nghiệm được phép phát sinh phí.
- Tránh external IP khi không cần; IAP/đường quản trị riêng cần cấu hình IAM và firewall tương ứng.
- Kiểm tra subnet, IP chưa dùng, network tag và guest OS.
- Không dùng kết quả **ping** làm kiểm chứng cho TCP 22 hoặc TCP 8080, vì ping sử dụng ICMP.

Ví dụ kiểm tra từ VM client/admin khi có công cụ netcat và backend đang lắng nghe:

~~~bash
# CHẠY TRONG VM CLIENT/ADMIN CỦA LAB.
nc -vz -w 5 10.60.0.20 8080
nc -vz -w 5 10.60.0.20 22
~~~

Khi request trả **connection refused**, backend có thể không có listener. Khi timeout, cần phân biệt firewall, route và host firewall. Khi nhận 401/403 HTTP, có thể cần kiểm tra xác thực và phân quyền ứng dụng.

## 10. Các trường hợp nâng cao cần suy luận riêng

### 10.1. Allow quá rộng thắng deny hẹp

| Rule | Priority | Source | Protocol | Action |
|---|---:|---|---|---|
| allow-all-tcp | **300** | 0.0.0.0/0 | tcp | ALLOW |
| deny-ssh | 500 | 0.0.0.0/0 | tcp:22 | DENY |

Cả hai khớp khi client gọi TCP 22. Kết quả **ALLOW** vì 300 thắng 500 dù deny chỉ nhắm TCP 22. Phải đánh giá thứ tự và thu hẹp rule cho phép, không chỉ nhìn tên deny-ssh.

### 10.2. Cùng priority 900: DENY thắng

Hai classic rules cùng khớp TCP 443:

- allow-https priority 900.
- deny-https priority 900.

Kết quả **DENY**, không phụ thuộc thứ tự tạo.

### 10.3. Hierarchical deny không thể bị classic allow ghi đè

Hierarchical policy tại organization **DENY SSH từ Internet**, trong VPC có classic **ALLOW SSH priority 0**. Nếu hierarchical rule khớp và kết thúc đánh giá, request vẫn **bị chặn**.

### 10.4. Network enforcement order làm thay đổi kết quả

Có network policy **DENY 8080** và classic VPC **ALLOW 8080** cùng khớp:

- **AFTER_CLASSIC_FIREWALL:** classic ALLOW có thể quyết định trước.
- **BEFORE_CLASSIC_FIREWALL:** network policy DENY có thể quyết định trước.

Mọi kết luận vẫn cần xác định hierarchical/system policy trước, chứ không chỉ hai rule trong ví dụ.

### 10.5. Khác direction không phải xung đột

Một **EGRESS deny TCP 5432** trên VM client có thể chặn connection mới tới database dù DB VM có **INGRESS allow TCP 5432**. Hai rule đang áp dụng ở **hai NIC/chiều khác nhau**, nên không có chuyện allow của server “thắng” deny của client.

## 11. GKE, Cloud Run, load balancer và hybrid

### 11.1. GKE

GKE dùng Compute Engine nodes và VPC networking, nên VPC firewall có thể áp dụng cho NIC của nodes. Tuy nhiên:

- Rule dựa trên **service account VM** nhận diện node, không phải Kubernetes ServiceAccount của từng Pod.
- Với VPC-native GKE, Pod IP có thể ở **secondary alias ranges**; source tags/service accounts có giới hạn trong việc xác định IP nguồn và không mặc nhiên bao phủ alias IP.
- GKE có thể tạo/duy trì một số rule cho cluster, node hoặc load balancer; sửa trực tiếp rule do GKE quản lý có thể gây vấn đề khi controller reconcile.
- Với yêu cầu Pod-to-Pod isolation, kiểm tra **Kubernetes NetworkPolicy** hoặc cơ chế bảo mật pod được GKE hỗ trợ.

### 11.2. Cloud Run

Không dùng classic VM target tag để quyết định mọi HTTP request inbound tới Cloud Run service. Cloud Run có **ingress settings**, IAM, cơ chế load balancer và Cloud Armor tùy kiến trúc.

Khi Cloud Run truy cập VPC qua **Direct VPC egress** hoặc connector được hỗ trợ, phải xem firewall/network policy ảnh hưởng **đường egress thực tế** theo chế độ kết nối. Firewall allow chỉ là một phần, không thay cho quyền gọi Cloud SQL, Storage hoặc service nội bộ.

### 11.3. Load balancer và health checks

Nhiều load balancer yêu cầu rule ingress cho **health checks** và traffic từ proxy đến VM/backend.

- Với Google Front Ends, cần kiểm tra dải nguồn health-check/proxy theo loại load balancer.
- Với một số Envoy-based load balancers, backend thấy kết nối từ **proxy-only subnet**.
- Backend unhealthy có thể do health check bị deny, dù client tới frontend vẫn kết nối thành công.

Không lấy một danh sách IP nguồn health-check chung để áp cho mọi loại LB; dùng tài liệu của loại load balancer đang triển khai.

### 11.4. Cloud VPN, Interconnect, Shared VPC

Kết nối từ on-premises tới VM qua Cloud VPN/Interconnect vẫn cần ingress phù hợp trên VM, thường theo **CIDR thực** sau NAT. Firewall ở site on-premises và route hai chiều cũng phải đúng.

Trong Shared VPC, firewall rules và logs liên quan **host project** sở hữu VPC; VM có thể nằm ở service project. Một classic rule không được tự chia sẻ cho VPC khác chỉ vì có Peering hoặc VPN.

## 12. Firewall Rules Logging và effective rule troubleshooting

### 12.1. Bật logging đúng mục đích

Trong lab đã thêm **--enable-logging** cho ba classic firewall rules. Tùy loại rule và tùy chọn log, Google Cloud ghi thông tin connection được xử lý vào **Cloud Logging**.

~~~bash
# CHỈ ĐỌC — kiểm tra logging và priority của một rule.
gcloud compute firewall-rules describe "lab-deny-ssh" \
  --project="$PROJECT_ID" \
  --format="yaml(name,priority,logConfig)"

# THAY ĐỔI — chỉ bật sau khi được phép sửa và tính chi phí logs.
gcloud compute firewall-rules update "RULE_NAME" \
  --project="$PROJECT_ID" \
  --enable-logging
~~~

Trong **Logs Explorer**, có thể lọc theo nguồn firewall log:

~~~text
resource.type="gce_subnetwork"
logName="projects/YOUR_NETWORK_PROJECT/logs/compute.googleapis.com%2Ffirewall"
~~~

**YOUR_NETWORK_PROJECT** là project sở hữu VPC; ở Shared VPC thường là **host project**. Các trường của log có thể chứa VM name, firewall rule, action, protocol, source/destination và metadata theo cấu hình.

**Không thấy log không đồng nghĩa không có traffic**:

- Rule có logging bị rule/policy ở lớp trước quyết định, nên không tới lượt.
- Source/destination, direction, target hoặc protocol không khớp.
- Logging chưa bật hoặc cấu hình mới chưa được áp dụng hoàn toàn.
- Người dùng thiếu quyền xem Logs Viewer, chọn sai project hoặc khoảng thời gian.
- Traffic bị chặn ở một lớp mạng trước khi tới NIC/rule đang kiểm tra.

Bật log tạo chi phí lưu trữ/ingestion theo mức sử dụng. Cần kiểm soát thời gian lưu và quyền truy cập vì log có thể tiết lộ topology, IP nội bộ và hoạt động của ứng dụng.

### 12.2. VPC Flow Logs và Audit Logs khác gì?

| Nguồn log | Trả lời câu hỏi |
|---|---|
| **VPC Firewall Rules Logging** | Kết nối phù hợp được firewall rule xử lý như thế nào? |
| **VPC Flow Logs** | Có những flow nào đi qua hạ tầng được hỗ trợ, lưu lượng bao nhiêu? |
| **Cloud Audit Logs** | Ai đã tạo/sửa/xóa firewall rule, VPC hoặc policy? |
| **Guest OS logs** | Dịch vụ đang chạy/đang lắng nghe cổng nào, có bị OS firewall chặn không? |
| **Application logs** | Request đã tới ứng dụng chưa, TLS/auth/business logic trả lỗi gì? |

VPC Flow Logs có cơ chế lấy mẫu/tổng hợp, không phải packet capture toàn bộ. Không dùng một flow log để chứng minh IAM của ứng dụng đã cho phép.

### 12.3. Network Intelligence Center — Connectivity Tests

**Connectivity Tests** hỗ trợ kiểm tra đường đi dựa trên cấu hình mạng Google Cloud. Công cụ có thể cho biết route, firewall rule hoặc policy nào là yếu tố chặn theo mô hình.

Quy trình:

1. Xác định **source IP/resource**, **destination IP/resource**, **protocol, port** và project/VPC liên quan.
2. Chạy test với đúng những thông số đó.
3. Đọc kết quả về route, firewall decision, VPC/hybrid path và backend khi được hỗ trợ.
4. Nếu mô hình báo blocked, kiểm tra chính xác policy layer, rule, priority và target.
5. Nếu mô hình báo reachable nhưng request thật fail, kiểm tra listener, guest firewall, DNS, TLS, IAM và trạng thái dịch vụ.

Connectivity Tests không quan sát được toàn bộ thiết bị hoặc đường mạng ngoài Google Cloud. Khi điều tra Cloud VPN/Interconnect, cần kết hợp thông tin từ thiết bị on-premises.

## 13. Quy trình chẩn đoán kết nối thất bại

Ví dụ VM **client 10.60.0.30** không gọi được backend **10.60.0.20:8080**.

~~~mermaid
flowchart TD
    A["Request thất bại"] --> D{"DNS ra đúng IP?"}
    D -- "Không" --> DNS["Kiểm tra DNS"]
    D -- "Có" --> R{"Route 2 chiều hợp lệ?"}
    R -- "Không" --> ROUTE["Kiểm tra routing, VPN, NAT"]
    R -- "Có" --> E["Xem effective firewalls + policy order"]
    E --> F{"Rule nào quyết định?"}
    F -- "Hierarchical/network" --> H["Kiểm tra association, rule action và goto_next"]
    F -- "Classic VPC" --> C["Kiểm tra direction, target, source, port, priority"]
    F -- "Không có deny" --> OS["Kiểm tra OS firewall, listener, TLS, IAM"]
    H --> L["Connectivity Tests + logs"]
    C --> L
    L --> FIX["Thay đổi nhỏ nhất rồi kiểm chứng lại"]
~~~

### 13.1. Tám câu hỏi điều tra theo thứ tự

1. **Source thực tế** là IP nào? NAT hoặc load balancer có làm đổi IP nguồn không?
2. **Destination thực tế** là IP/port nào? DNS/redirect có đưa request tới một backend khác không?
3. **NIC đích và NIC nguồn** thuộc VPC nào? VM có nhiều NIC không?
4. Đang phân tích **connection mới ingress/egress**, hay chỉ là **return traffic**?
5. Các **target tags/service accounts** của VM có khớp rule không?
6. Có **hierarchical, regional system, global/regional network policy** nào áp dụng trước classic rules không?
7. Trong lớp classic, priority nhỏ nhất thuộc rule nào? Có **ALLOW và DENY trùng priority** không?
8. Nếu firewall đã cho phép, **route, OS firewall, app listener, TLS/IAM** có vấn đề không?

### 13.2. Những triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Có allow SSH nhưng vẫn bị chặn | Hierarchical deny hoặc classic deny priority cao hơn; thiếu IAP/OS Login | Effective firewalls, IAM, source thực tế |
| Client A gọi API được, client B không | Nguồn khác /32, CIDR, source tag hoặc route | So 5-tuple và các rule khớp |
| Firewall allow nhưng TCP bị refused | Dịch vụ chưa listen, host firewall hoặc destination sai | Guest logs, port listener |
| API trả HTTP 403 | IAM/authorization ở ứng dụng hoặc gateway; kết nối có thể đã đến server | Request logs, principal và quyền |
| VM có egress allow nhưng không ra Internet | Thiếu Cloud NAT/external IP, route hoặc DNS | Kiểm tra routing, NAT, DNS |
| GKE service bị unhealthy sau sửa rule | Chặn node, proxy/health check hoặc rule GKE quản lý | Backend health, GKE controller, policy |
| Classic allow hoạt động khác sau cấu hình VPC mới | Network firewall policy enforcement order thay đổi | Đọc thuộc tính VPC và policy associations |
| Không thấy firewall logs | Sai project, rule không thắng, logging chưa bật | Effective rules và Cloud Logging |
| Dùng source-ranges cùng source-tags gây mở rộng quyền | Hai nguồn được kết hợp theo OR | Kiểm tra tất cả nguồn thực sự khớp |
| IPv6 request không khớp rule IPv4 | Chỉ khai báo 0.0.0.0/0 | Kiểm tra IPv6 ranges/dual stack |
| On-premises tới VM bị timeout | Firewall ingress, routing BGP/VPN, NAT, peer firewall | Connectivity Tests và log hai đầu |

Không bật tạm rule **allow all** để chứng minh mạng có thể hoạt động: việc đó có thể làm lộ VM ra Internet và vẫn không xác định được nguyên nhân. Nên kiểm tra từng lớp và giới hạn phạm vi thay đổi.

## 14. Thiết kế firewall rule cho hệ thống production

### 14.1. Nguyên tắc ít quyền nhất

- Chỉ **allow những port/protocol cần thiết**.
- Giới hạn **source IP ranges** hoặc định danh nguồn được hỗ trợ theo luồng thực tế.
- Dùng **target tags/service accounts** phù hợp, tránh target all instances nếu không cần.
- Bảo vệ quyền có thể **đổi network tags**, service account và firewall policies.
- Hạn chế SSH/RDP từ Internet; ưu tiên IAP, OS Login, bastion hoặc đường quản trị đúng kiến trúc được duyệt.
- Phân tách môi trường development/staging/production bằng project/VPC/policy rõ ràng.
- Dùng hierarchical policies cho ranh giới bảo mật chung khi organization có yêu cầu.
- Trước khi deny diện rộng, kiểm tra **health checks, proxy-only subnet, traffic nội bộ và dịch vụ hệ thống**.
- Duy trì bảng owner, lý do, ticket và ngày rà soát cho những rule ngoại lệ.

### 14.2. Ghi rõ ý định thay vì chỉ ghi rule name

Một change request tốt:

~~~text
Ứng dụng: checkout-api
Môi trường: production
VPC / Project: [định danh]
Nguồn: GKE backend node/workload theo IP/subnet thực tế
Đích: VM legacy-api
Protocol/Port: TCP 8080
Direction: INGRESS tại VM legacy-api
Target selector: target service account hoặc network tag có kiểm soát
Policy layer: classic VPC / network policy / hierarchical
Priority: [số và lý do]
Hành động: ALLOW
Thời hạn rà soát: [ngày]
Owner / approver: [nhóm]
Kết quả kiểm thử: allowed flow PASS, denied flow PASS
Rollback: [PR/config version]
~~~

Không cần dùng tên ngẫu nhiên như allow-test123 mà thiếu mục đích. Khi audit, việc giải thích **nguồn nào, đích nào, port nào, vì sao** quan trọng hơn tổng số rule.

### 14.3. Ví dụ Terraform

~~~hcl
resource "google_compute_firewall" "allow_api_from_private" {
  name    = "allow-api-from-private"
  network = "firewall-priority-lab"

  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["10.60.0.0/24"]
  target_tags   = ["backend"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}
~~~

Đây là cấu hình minh họa cho classic rule, chưa bao gồm đầy đủ provider/project/version và lifecycle của VPC. Khi áp dụng thực tế, quản lý state Terraform, chạy plan/diff, review IAM và policy hiệu lực trước khi apply.

### 14.4. Quy trình thay đổi có kiểm soát

1. Mô tả request bằng source IP, destination IP, port, protocol và direction.
2. Đọc trạng thái hiện tại, effective rules và các lớp policy.
3. Xác định thay đổi nhỏ nhất cần tạo/sửa, tránh mở rộng target hoặc source không cần thiết.
4. Kiểm tra IaC plan/Connectivity Tests; ghi phương án rollback.
5. Triển khai vào môi trường thử nghiệm hoặc change window phù hợp.
6. Kiểm thử **flow được phép** và **flow đáng lẽ phải chặn**, quan sát logs/SLO.
7. Lưu bằng chứng, owner và lên lịch rà soát rule ngoại lệ.

Khi bật deny/allow mới trên mạng có nhiều dịch vụ, cân nhắc traffic từ load balancer, monitoring agent, CI/CD và hệ thống backup; một rule có thể gây sự cố ngoài nhóm ứng dụng trực tiếp.

## 15. Case study: checkout, GKE, VM legacy và Cloud SQL

Giả sử một doanh nghiệp chạy frontend Cloud Run, API container trên GKE, backend tác vụ cũ trên VM Compute Engine và cơ sở dữ liệu Cloud SQL. Các workload kết nối trong một VPC production, đồng thời có đường Cloud VPN tới mạng tại chỗ.

### 15.1. Ma trận luồng và kiểm soát

| Luồng | Lớp cần đánh giá | Kiểm soát bổ sung |
|---|---|---|
| GKE workload → VM legacy TCP 8080 | GKE node egress nếu có deny; VM ingress theo IP nguồn thực | GKE NetworkPolicy, mTLS, app auth |
| VM legacy → database | VM egress; private service connectivity và network config theo kiểu Cloud SQL | DB credentials, TLS, IAM nếu dùng |
| Cloud Run → API private | Cloud Run ingress, IAM và đường mạng theo cấu hình | ID token, Cloud Run Invoker |
| Ops → VM TCP 22 | VPC ingress và IAP/đường quản trị | IAM, OS Login, SSH keys |
| On-premises → VM | VPC ingress theo CIDR sau NAT, VPN/BGP | On-prem firewall, TLS và route hai chiều |
| Internet → VM SSH | Không có allow phù hợp hoặc chính sách deny có chủ đích | Không gắn external IP không cần thiết |

### 15.2. Sai lệch thứ nhất: classic allow không có tác dụng

Tổ chức áp dụng hierarchical policy **deny SSH từ 0.0.0.0/0** cho môi trường production. Nhóm ứng dụng thêm classic **allow SSH priority 0** nhưng vẫn không vào được. Thêm classic rule thấp số hơn nữa không có ích, vì hierarchical policy đã quyết định trước.

Cách xử lý: xác định đường quản trị hợp lệ (IAP/OS Login hoặc phương án được tổ chức duyệt), đưa yêu cầu ngoại lệ đến nhóm sở hữu policy nếu cần.

### 15.3. Sai lệch thứ hai: API 403 bị nhầm là firewall deny

GKE gọi một API và nhận **HTTP 403** từ server. Đây có thể là dấu hiệu HTTP request đã tới ứng dụng/gateway và bị chặn bởi IAM hoặc business authorization. Nhóm phải đối chiếu logs và header/định danh theo cách an toàn, không mở thêm cổng để “sửa” 403 khi chưa có bằng chứng mạng bị chặn.

### 15.4. Sai lệch thứ ba: tunnel UP nhưng database không truy cập được

Cloud VPN tunnel và BGP session đều UP, nhưng VM không kết nối được tới database tại chỗ. Kiểm tra cần bao gồm route chiều đi/về, source IP sau NAT, firewall on-premises, VPC egress và port database. **Firewall rule ALLOW chỉ là một điều kiện**, không thay thế việc xác minh toàn bộ đường truyền và auth DB.

### 15.5. Đo hiệu quả sau sửa

Khi thay đổi rule, nhóm kiểm tra:

- Flow cần thiết có thành công không?
- Flow không được phép có còn bị deny không?
- Health checks của load balancer và workload latency có ổn định không?
- Logs có cho biết đúng rule đã xử lý không?
- Có phát sinh lượng logs và chi phí ngoài dự kiến không?

## 16. Bài tập tự kiểm tra

### 16.1. Câu hỏi

1. ALLOW TCP 443 priority **800** và DENY TCP 443 priority **900** cùng khớp classic rules. Kết quả?
2. ALLOW source **10.60.0.10/32 priority 900** và DENY source **10.60.0.0/24 priority 900** cùng khớp. Kết quả?
3. DENY TCP 22 priority 500 source 0.0.0.0/0 và ALLOW TCP 22 priority 800 source /32. Nguồn /32 có được phép không?
4. Vì sao **source ranges + source tags** trong một ingress rule không được hiểu là phép AND?
5. Có thể dùng classic VPC firewall để cấp **roles/run.invoker** cho Cloud Run không?
6. VPC ở chế độ **BEFORE_CLASSIC_FIREWALL** có network policy DENY khớp và classic ALLOW. Kết quả trong trường hợp policy trước đã kết thúc đánh giá?
7. Có thể so priority classic rule **100** với hierarchical rule **1000** để kết luận classic thắng không?
8. Implied ingress deny dành cho VM có phải kết quả mặc định của mọi internal proxy load balancer forwarding rule không?
9. VPC firewall ALLOW egress mà VM không ra Internet được: kể hai nguyên nhân khác firewall.
10. Tại sao không nên đánh giá TCP 8080 chỉ bằng ping?
11. Một GKE node có service account phù hợp với rule target SA. Rule này có tự tạo NetworkPolicy cho từng Pod không?
12. Khi bật logging cho rule nhưng không thấy log, nên kiểm tra gì?
13. Làm sao biết danh sách firewall rules thực sự áp dụng cho NIC VM?
14. Khi chuẩn bị thay một rule production, phải kiểm thử những chiều lưu lượng nào?

### 16.2. Đáp án định hướng

1. **ALLOW** vì 800 thắng 900 trong cùng lớp.
2. **DENY** vì tie priority và cả hai rule khớp.
3. **Không**; deny priority 500 được xét trước.
4. Vì tập nguồn hiệu lực là **OR/union** theo khả năng của rule.
5. **Không**; IAM/Cloud Run quản lý quyền gọi service.
6. **DENY** nếu network policy đã quyết định và không chuyển tiếp.
7. **Không**; phải xét policy layer trước rồi mới so priority bên trong.
8. **Không**; implied action phụ thuộc target resource type.
9. Thiếu route, Cloud NAT/external IP, DNS hoặc endpoint không hoạt động.
10. Vì ping dùng **ICMP**, còn request cần kiểm tra **TCP 8080**.
11. **Không**; VM service account selector không thay thế Pod network isolation.
12. Rule có thể không khớp/không thắng, thiếu quyền logs, sai network project hoặc log chưa được ghi nhận.
13. Dùng **get-effective-firewalls** trên NIC đúng, kiểm tra policy association và tuple traffic.
14. Kiểm thử cả **request phải được phép** lẫn **request phải bị chặn**, bao gồm health checks và đường trả lời liên quan.

## 17. Tài liệu tham khảo chính thức

Những trang Google Cloud nên được dùng để đối chiếu hành vi/cú pháp hiện hành:

- [VPC firewall rules — Concepts](https://docs.cloud.google.com/firewall/docs/firewalls)
- [Use VPC firewall rules — Console và gcloud](https://docs.cloud.google.com/firewall/docs/using-firewalls)
- [Evaluation order for firewall policies and rules](https://docs.cloud.google.com/firewall/docs/firewall-policies-rule-eval-order)
- [Firewall policies and rules overview](https://docs.cloud.google.com/firewall/docs/firewall-policies-overview)
- [Hierarchical firewall policies](https://docs.cloud.google.com/firewall/docs/firewall-policies)
- [Global network firewall policies](https://docs.cloud.google.com/firewall/docs/network-firewall-policies)
- [Network tags for Compute Engine VM](https://docs.cloud.google.com/vpc/docs/add-remove-network-tags)
- [Manage VPC firewall rules logging](https://docs.cloud.google.com/firewall/docs/manage-vpc-firewall-rules-logging)
- [Troubleshoot firewall policy logs](https://docs.cloud.google.com/firewall/docs/troubleshoot/firewall-policies-logs)
- [Load balancer firewall rules](https://docs.cloud.google.com/load-balancing/docs/firewall-rules)
- [Cloud Run ingress settings](https://docs.cloud.google.com/run/docs/securing/ingress)

Cấu hình Cloud NGFW, kiểu policy, phiên bản CLI, hỗ trợ target và chi phí logging có thể thay đổi. Khi triển khai thật, xác minh với **effective firewalls** và điều kiện hiện tại của organization/VPC đang sử dụng.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** VPC firewall rules là một lớp kiểm soát mạng cho Compute Engine và các workload GCP có đường truy cập VPC phù hợp. Một kiến trúc an toàn còn cần organization/IAM policies, VPC routes, DNS, Cloud VPN, bảo mật GKE/Cloud Run và quyền cơ sở dữ liệu. Khi phân tích một request, hãy **xác định luồng → kiểm tra đúng policy layer → lọc target/source/destination/port → so priority → xác minh bằng effective rules và logs → thử cả flow được phép và flow phải bị chặn**. Kết quả có thể đưa vào IaC/CI/CD để quản trị nhất quán, theo dõi độ tin cậy và kiểm soát chi phí theo thời gian.





