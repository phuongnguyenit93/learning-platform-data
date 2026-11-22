# Hierarchical firewall policies và network firewall policies trên Google Cloud

> **Chương:** Bảo mật và truy cập mạng  
> **Bài học:** Hierarchical firewall policies và network firewall policies  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Để quản trị mạng của nhiều dự án an toàn, một doanh nghiệp không thể chỉ tạo các quy tắc firewall riêng lẻ rồi hy vọng mọi đội áp dụng thống nhất.

**Hierarchical firewall policies** giúp quản trị viên áp quy tắc bảo mật nhất quán từ **organization** hoặc **folder** xuống các VPC thuộc project con. **Network firewall policies** tổ chức quy tắc theo **VPC network**, ở phạm vi **global** hoặc **regional**. Chúng là các thành phần của **Cloud Next Generation Firewall (Cloud NGFW)**, được đánh giá cùng với **classic VPC firewall rules** và các kiểm soát mạng khác.

Điểm quan trọng: **một rule có priority thấp hơn về số không đương nhiên thắng một rule nằm trong policy được đánh giá trước**. Bạn phải hiểu chính xác **phạm vi gắn policy**, **thứ tự các lớp firewall**, **hành động `allow`/`deny`/`goto_next`** và **đối tượng được bảo vệ** trước khi phán đoán một kết nối có đi qua hay không.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt hierarchical firewall policy, global network firewall policy, regional network firewall policy, Google-managed regional system firewall policy và classic VPC firewall rule.
2. Mô tả mối quan hệ **organization → folder → project → VPC → workload** với nơi chính sách firewall được liên kết.
3. Giải thích các trường của firewall rule: **direction, priority, action, match, source/destination, protocol/port, target, logging**.
4. Vận dụng **hai chế độ enforcement order** là `AFTER_CLASSIC_FIREWALL` và `BEFORE_CLASSIC_FIREWALL`.
5. Phân biệt tác dụng của `allow`, `deny`, `goto_next`, hành vi khi không có rule khớp và các implied actions.
6. Thiết kế chính sách cơ sở ở cấp tổ chức, phân quyền tự phục vụ ở cấp VPC, phân biệt bảo vệ VM/GKE node với Cloud Run và dịch vụ được quản lý.
7. Đọc **effective firewall rules** bằng Console/`gcloud` để chẩn đoán kết nối bị chặn hoặc mở ngoài dự kiến.
8. Tạo kế hoạch thay đổi có thể kiểm chứng với IAM tối thiểu, logging, kiểm thử, rollback và đánh giá chi phí.

## 2. Firewall điều khiển điều gì trong một VPC?

Firewall của Google Cloud đánh giá các kết nối trên **đối tượng được hỗ trợ**, dựa vào các trường như hướng lưu lượng, địa chỉ nguồn/đích, protocol, port và target. Đối với VM, quy tắc được thực thi ở lớp mạng ảo gắn với **network interface**, thay vì yêu cầu người vận hành cài một máy ảo firewall riêng cho từng subnet.

Ví dụ, một VM có internal IP `10.20.1.10` và chạy PostgreSQL cổng `5432`. Các câu hỏi độc lập gồm:

| Lớp | Câu hỏi | Công cụ/kiểm soát liên quan |
|---|---|---|
| Định tuyến | Có route tới `10.20.1.10` và route trả lời không? | VPC routes, Cloud Router, VPN/Interconnect khi hybrid |
| Firewall mạng | TCP/5432 từ nguồn cụ thể có được phép tới VM không? | Hierarchical, global/regional network, VPC firewall rules |
| Hệ điều hành | Máy có firewall OS hoặc tiến trình lắng nghe cổng này không? | Linux/Windows firewall, cấu hình server |
| Danh tính | Người hoặc workload có quyền truy cập tài nguyên/API không? | IAM, service account, Workload Identity |
| Ứng dụng | Database có cho phép user, TLS và truy vấn đó không? | PostgreSQL roles, network TLS, ứng dụng |
| Theo dõi | Có biết kết nối bị từ chối ở đâu không? | Effective firewalls, VPC Flow Logs, firewall logging |

**Firewall network không thay IAM, TLS hay quyền ứng dụng.** Ngược lại, cấp IAM `roles/compute.admin` không có nghĩa là firewall tự mở SSH, HTTP hay database port.

### 2.1. Ingress và egress

- **INGRESS**: gói tin cho kết nối mới đi **vào** đối tượng đích được bảo vệ. Ví dụ người dùng từ on-premises gọi TCP/443 tới VM frontend.
- **EGRESS**: gói tin cho kết nối mới đi **ra** từ đối tượng nguồn được bảo vệ. Ví dụ VM batch mở kết nối HTTPS đến API bên ngoài.
- Firewall của Google Cloud về cơ bản **stateful** đối với kết nối được cho phép; phản hồi của luồng được thiết lập hợp lệ được theo dõi theo cơ chế dịch vụ. Không cần tạo rule ingress chỉ để cho phép mọi gói phản hồi từ một kết nối egress hợp lệ.
- Chọn IPv4/IPv6 source/destination ranges đúng họ giao thức. Mở `0.0.0.0/0` là mọi nguồn IPv4, còn `::/0` là mọi nguồn IPv6; không thể thay thế nhau.

### 2.2. Một số điểm không thuộc phạm vi áp dụng tự động

Quy tắc firewall VPC/Cloud NGFW có các đối tượng mục tiêu được hỗ trợ rõ ràng (như VM interfaces và một số frontend của internal Envoy-based load balancer ở loại policy/tier thích hợp). Không mặc định coi mọi sản phẩm Google Cloud là VM target:

- **Compute Engine**: VM network interfaces là đối tượng điển hình; nhiều quy tắc có thể khớp vào cùng interface.
- **GKE**: node/network interfaces và lưu lượng tới workload theo mô hình networking của cluster có liên hệ với VPC firewall; **Kubernetes NetworkPolicy** và cơ chế GKE Dataplane V2 là lớp kiểm soát khác.
- **Cloud Run**: bảo vệ bằng ingress settings, IAM Invoker, HTTPS/Application Load Balancer/Cloud Armor và cấu hình VPC egress khi phù hợp; Cloud Run service không tự trở thành một VM target cho network firewall policy.
- **Cloud SQL**: kết nối private/public, xác thực database, IAM theo tính năng hỗ trợ và network access settings có phạm vi riêng; không suy rằng mọi rule VM áp trực tiếp vào Cloud SQL instance.
- **Cloud Storage**: IAM, bucket policy, endpoint, VPC Service Controls và các dịch vụ khác phù hợp hơn để kiểm soát truy cập object.

## 3. Năm lớp chính sách cần phân biệt

| Cơ chế | Nơi tạo/quản trị | Nơi gắn/phạm vi áp dụng | Vai trò thường gặp |
|---|---|---|---|
| **Hierarchical firewall policy (HFP)** | Cấp organization/folder, quản trị theo phân cấp | Association tại organization hoặc folder; ảnh hưởng các VPC trong project con phù hợp | Ranh giới bảo mật và chuẩn chung toàn doanh nghiệp |
| **Regional system firewall policy** | Do Google Cloud quản lý | Region/VPC nơi dịch vụ Google yêu cầu | Quy tắc hệ thống; người dùng chỉ có quyền chỉnh logging ở trường hợp được hỗ trợ |
| **Classic VPC firewall rules** | Project chứa VPC | Một VPC network, theo target của rule | Quy tắc cục bộ truyền thống |
| **Global network firewall policy** | Project | Association tới một hoặc nhiều VPC trong **cùng project**, áp mọi region | Nhóm quy tắc nhất quán theo VPC |
| **Regional network firewall policy** | Project và region | Association với VPC ở **region** tương ứng | Quy tắc riêng của region hoặc workload địa phương |

Điểm chung của ba nhóm **firewall policies do khách hàng quản lý**: một policy chứa nhiều **rules**, muốn phát huy tác dụng phải có **association** hợp lệ và đúng phạm vi. Một policy mới được tạo nhưng **chưa associate** thường **chưa ảnh hưởng traffic**.

### 3.1. Ví dụ phân cấp tài nguyên

~~~mermaid
flowchart TD
    O["Organization: example.com<br/>HFP nền: kiểm soát bảo mật chung"]
    O --> F1["Folder: Engineering<br/>HFP bổ sung theo nghiệp vụ"]
    O --> F2["Folder: Finance<br/>HFP giới hạn mạng nhạy cảm"]
    F1 --> P1["Project: app-dev"]
    F1 --> P2["Project: app-prod"]
    P2 --> N["VPC: prod-vpc<br/>Global network firewall policy"]
    N --> R["Region asia-southeast1<br/>Regional network firewall policy"]
    N --> R2["Region asia-northeast1"]
    R --> VM["VM/GKE nodes hoặc target được hỗ trợ"]
    P1 --> D["VPC: dev-vpc"]
~~~

Sơ đồ minh họa **hai trục gắn policy**: hierarchical đi theo **cây tổ tiên resource**, còn network policies đi theo **VPC và region**. Điều kiện một rule có thực sự áp vào gói tin còn phụ thuộc direction, target và những trường match của rule.

### 3.2. Hierarchical firewall policy

HFP cung cấp một tập rule tại cấp quản trị cao, áp dụng xuống những tài nguyên thuộc phạm vi association:

- Gắn tại **organization** để đặt chính sách cơ sở cho tất cả project thuộc tổ chức.
- Gắn tại **folder** để đặt ràng buộc bổ sung cho một nhóm project.
- Các policy liên quan được đánh giá từ **organization** rồi đến **folder tổ tiên gần gốc hơn**, tiến về folder chứa project.
- Nếu rule HFP khớp `allow` hoặc `deny`, quyết định đó **kết thúc đánh giá firewall**; rule ở tầng VPC không thể “ghi đè” quyết định bằng priority số nhỏ.
- Nếu khớp `goto_next`, chuyển sang **policy/lớp kế tiếp**, không tiếp tục thử các rule ưu tiên thấp hơn trong **cùng HFP**.
- Nếu không có rule nào khớp, hành vi của HFP tương đương **`goto_next` ngầm**.

HFP rất hữu ích để chặn các cổng/quãng nguồn bị cấm toàn công ty, áp baseline egress hoặc cho phép những đường quản trị đã phê duyệt. Tuy nhiên, một `allow` quá rộng ở HFP có thể **bỏ qua các deny ở cấp VPC**, nên chính sách tổ chức cần được thiết kế cẩn trọng.

### 3.3. Global network firewall policy

Global network firewall policy được cấu hình trong project và gắn vào VPC ở **cùng project**. Các rule áp dụng ở mọi region mà VPC có target phù hợp. Ví dụ:

- Một policy chung cho VPC production trong project host Shared VPC.
- Quy tắc ingress/egress cơ sở cho nhóm VM và một số target được hỗ trợ.
- Rule sử dụng **secure tags** hoặc **target service accounts** để nhắm đúng nhóm VM.
- Một số khả năng Cloud NGFW nâng cao như **Layer 7 inspection** với security profile group theo tier và sản phẩm được hỗ trợ.

Một VPC có thể gắn **một global network firewall policy** tại thời điểm nhất định. Hãy kiểm tra association trước khi sửa vì chỉnh rule của một policy đang gắn **có tác động tới mọi VPC mà policy đó đang phục vụ**.

### 3.4. Regional network firewall policy

Regional network firewall policy áp dụng cho VPC **trong một region** cụ thể. Nó phù hợp khi tài nguyên Singapore có yêu cầu khác Tokyo, hoặc khi doanh nghiệp muốn tách đội vận hành theo vị trí.

Ví dụ: VPC `prod-vpc` có VM tại Singapore và Tokyo. Một regional policy gắn cho Singapore chỉ tác động tới target trong region được associate; không được suy rằng policy đó điều khiển cả VM tại Tokyo.

### 3.5. Regional system firewall policy

Google Cloud có thể tạo **regional system firewall policy** khi một dịch vụ được hỗ trợ cần rule hệ thống. Các rule này do Google quản lý và được xét **sau HFP, trước các lớp do người dùng cấu hình còn lại**. Người quản trị thường chỉ có thể bật/tắt logging theo khả năng được hỗ trợ, không tùy ý sửa hành động của các rule đó.

Vì thế, khi tìm hiểu “vì sao traffic được phép?”, hãy xem cả **effective firewall rules** thay vì chỉ xem ba policy do đội bảo mật tạo.

## 4. Thành phần của một firewall policy rule

| Thành phần | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| **Priority** | Số nhỏ hơn có ưu tiên cao hơn **bên trong cùng policy** | Thường chọn khoảng cách 100, 200, 300 để còn chỗ chèn |
| **Direction** | `INGRESS` hoặc `EGRESS` | Xác định traffic đi vào hay đi ra target |
| **Action** | `allow`, `deny`, `goto_next` hoặc hành động inspection được hỗ trợ | Phân biệt terminal action và chuyển lớp |
| **Source/destination** | IP/CIDR hoặc thuộc tính khác được hỗ trợ theo loại policy/tier | Không dùng IP nguồn làm IP đích |
| **Layer 4 protocol/port** | TCP/443, TCP/22, UDP/53, ICMP, v.v. | Khớp cả protocol và destination port |
| **Target** | Tất cả target được hỗ trợ hoặc service account/secure tag/target resources theo loại rule | Mặc định target rộng nếu không giới hạn |
| **Logging** | Ghi connection decision theo cấu hình và khả năng sản phẩm | Có phí/khối lượng log; cần retention và bảo mật |
| **Disabled** | Tắt áp dụng rule mà vẫn giữ cấu hình | Đừng coi disabled rule là một deny hiện hành |
| **Description/owner** | Mục đích, ticket, người phụ trách, thời hạn | Hỗ trợ rà soát và thu hồi |

### 4.1. Priority là số trong một policy, không phải trên toàn hệ thống

Một rule priority `1000` trong **network policy** không thể tự đi trước rule priority `2000` của **HFP tại organization**: HFP là **lớp được đánh giá trước**.

Trong **một policy**, mỗi rule có priority riêng và duy nhất; **số nhỏ hơn** được xét trước. Trong classic VPC firewall rules, có quy tắc riêng: nếu hai rule **cùng priority**, cùng khớp traffic, một allow và một deny thì **deny thắng**. Đừng lấy quy tắc tie-break này áp sang hai policy khác nhau hoặc đánh đồng với thứ tự các lớp.

### 4.2. Action và kết quả

| Action | Tác dụng | Rule sau nó có còn được xét? |
|---|---|---|
| `allow` | Cho phép traffic đã match ở lớp firewall, theo điều kiện hỗ trợ | **Không**; quyết định allow là terminal |
| `deny` | Từ chối traffic đã match | **Không**; quyết định deny là terminal |
| `goto_next` | Nhường quyền đánh giá cho policy/lớp tiếp theo trong chuỗi | **Không còn xét phần còn lại của policy hiện tại** |
| Không rule nào khớp | Tương đương `goto_next` ngầm | Chuyển sang bước đánh giá tiếp theo |
| `apply_security_profile_group` | Chuyển lưu lượng khớp tới security profile/firewall endpoint theo sản phẩm được hỗ trợ | Quyết định sau inspection theo profile; không xử lý như `goto_next` |

`goto_next` là công cụ **ủy quyền quyết định cho lớp thấp hơn**, không phải allow traffic. Nó đặc biệt quan trọng khi muốn ranh giới tổ chức chỉ cấm các trường hợp bị cấm, còn đội project có quyền thiết kế các luồng hợp lệ.

### 4.3. Target, secure tags và service accounts

- **Target service account**: trong loại policy hỗ trợ, dùng danh tính service account **gắn với VM** để chọn các network interface phù hợp. Nó **không phải** cơ chế kiểm tra danh tính người dùng HTTP gọi vào ứng dụng.
- **Secure tags**: Resource Manager secure tags có thể dùng để chọn những target được phép theo khả năng của policy. Quyền tạo/đính tag phải được bảo vệ; người sửa được secure tag có thể gián tiếp thay đổi phạm vi rule.
- **Network tags truyền thống** trong classic VPC firewall rules khác với **secure tags** trong Cloud NGFW; không suy rằng việc đặt label `env=prod` hoặc network tag `prod` tự khớp điều kiện secure tag.
- **Source secure tags** và các trường nâng cao khác chỉ khả dụng với loại rule, hướng traffic và tier tương ứng; kiểm tra bản mô tả chính thức thay vì sao chép mọi tùy chọn từ loại policy này sang loại policy khác.

Ví dụ: một rule chỉ nhắm **VM mang service account của backend** sẽ giúp thu hẹp tác động hơn rule áp tất cả VM trong VPC. Tuy nhiên, việc đổi service account của VM có thể làm VM chuyển từ nhóm target này sang nhóm khác.

## 5. Thứ tự đánh giá: điểm dễ gây sai lầm nhất

Google Cloud cho phép chọn **network firewall policy enforcement order** trên VPC. HFP và regional system firewall policies luôn được đánh giá trước các lớp tùy chọn này.

### 5.1. Mặc định: `AFTER_CLASSIC_FIREWALL`

Với VPC mặc định sử dụng `AFTER_CLASSIC_FIREWALL`, thứ tự là:

1. **Hierarchical firewall policies:** organization trước, các folder tổ tiên từ gốc xuống.
2. **Regional system firewall policies:** nếu dịch vụ Google Cloud cần.
3. **Classic VPC firewall rules.**
4. **Global network firewall policy.**
5. **Regional network firewall policies.**
6. **Implied actions.**

~~~mermaid
flowchart TD
    A["Traffic vào/ra target"] --> H["Hierarchical policies<br/>organization → folder"]
    H --> S["Regional system policies"]
    S --> C["Classic VPC firewall rules"]
    C --> G["Global network firewall policy"]
    G --> R["Regional network firewall policies"]
    R --> I["Implied action"]
    H -. "allow/deny: dừng" .-> Stop["Kết quả terminal"]
    S -. "allow/deny: dừng" .-> Stop
    C -. "allow/deny: dừng" .-> Stop
    G -. "allow/deny: dừng" .-> Stop
    R -. "allow/deny: dừng" .-> Stop
~~~

**Hệ quả:** nếu classic VPC firewall rule đã **allow** traffic thì một rule **deny** trong global network firewall policy có thể **không được xét đến**. Do đó không thể tạo một deny network policy rồi kết luận chắc chắn nó chặn mọi allow classic hiện hữu khi enforcement order vẫn là mặc định.

### 5.2. Tùy chọn: `BEFORE_CLASSIC_FIREWALL`

Với `BEFORE_CLASSIC_FIREWALL`, thứ tự là:

1. Hierarchical firewall policies.
2. Regional system firewall policies.
3. **Global network firewall policy.**
4. **Regional network firewall policies.**
5. **Classic VPC firewall rules.**
6. Implied actions.

Đây là lựa chọn hữu ích nếu doanh nghiệp muốn network firewall policy kiểm soát traffic **trước các rule classic** đang tồn tại, chẳng hạn khi chuyển đổi chuẩn bảo mật từ classic VPC rules sang Cloud NGFW. Tuy nhiên, thay đổi enforcement order là **thay đổi hành vi của cả VPC**, có thể làm các ứng dụng trước đây được allow bị deny hoặc ngược lại.

### 5.3. Bảng so sánh nhanh

| Lớp policy | `AFTER_CLASSIC_FIREWALL` (mặc định) | `BEFORE_CLASSIC_FIREWALL` |
|---|---:|---:|
| Hierarchical | 1 | 1 |
| Regional system | 2 | 2 |
| Classic VPC rules | **3** | **5** |
| Global network | **4** | **3** |
| Regional network | **5** | **4** |
| Implied action | 6 | 6 |

**Không phải mặc định “network policy luôn chạy trước VPC rules”.** Hãy kiểm tra **thuộc tính enforcement order của VPC thực tế** khi chẩn đoán, nhất là project đã được migrate.

### 5.4. Implied actions: phải xét loại target

Nếu không có rule nào quyết định và đánh giá đã đi đến cuối:

- Với **VM network interface**, ingress có **implied deny**; egress có **implied allow**.
- Với một số **internal Envoy-based Application/Proxy Network Load Balancer forwarding rules** thuộc phạm vi tính năng hỗ trợ, implied ingress action có thể là **allow**, khác với VM ingress.
- Không lấy mặc định của VM để áp sang mọi tài nguyên Google Cloud hoặc mọi phiên bản/tier.

Vì implied egress có thể là allow, mạng an toàn không nên chỉ dựa vào việc “chúng tôi chưa cấu hình egress rule”. Khi yêu cầu kiểm soát outbound, thiết kế **egress policy rõ ràng**, đường Google APIs, DNS, patching và kết nối đối tác trước khi chặn.

## 6. Diễn giải các tình huống xung đột

### 6.1. HFP deny thắng allow VPC

- Organization HFP: priority `1000`, ingress `deny` TCP/22 từ `0.0.0.0/0` tới VM target.
- Classic VPC: priority `100`, ingress `allow` TCP/22 từ `203.0.113.10/32`.
- Traffic: từ IP trên đến VM TCP/22.

**Kết quả:** deny ở HFP được xét trước và dừng đánh giá. Số `100` ở VPC nhỏ hơn `1000` không giúp allow thắng.

### 6.2. HFP allow cũng có thể vượt deny bên dưới

- Organization HFP: ingress `allow` TCP/443 từ `0.0.0.0/0` cho tất cả VM.
- VPC policy: deny TCP/443 từ dải nguồn không thuộc nhóm khách hàng.

**Kết quả:** khi allow HFP match, các deny bên dưới không còn cơ hội thực thi. Đây là lý do không nên dùng allow rộng ở HFP trừ khi kiến trúc đã chứng minh điều đó là phù hợp.

### 6.3. `goto_next` để đội ứng dụng quyết định

- Organization HFP: deny TCP/22 từ Internet công khai, trừ đường hỗ trợ được phê duyệt.
- Rule tiếp theo của HFP (đúng target và traffic cần ủy quyền): `goto_next`.
- Folder/Network/VPC: đội ứng dụng cấu hình allow TCP/443 cho frontend, deny port backend bên ngoài.

**Kết quả:** `goto_next` không tự cho phép traffic; nó chuyển tới các lớp kế tiếp. Nếu một rule organization priority thấp hơn trong **cùng HFP** lẽ ra deny thì rule ấy **không còn được xét** khi `goto_next` đã match; vì thế vị trí của `goto_next` phải được kiểm tra kỹ.

### 6.4. Classic allow và global network deny theo hai enforcement order

| Thành phần | Rule |
|---|---|
| Classic VPC | `allow` TCP/443 từ `198.51.100.0/24` |
| Global network policy | `deny` TCP/443 từ `198.51.100.0/24` |
| Hierarchical/system | Không có rule terminal match |
| `AFTER_CLASSIC_FIREWALL` | **Allow từ classic**; global deny không được xét |
| `BEFORE_CLASSIC_FIREWALL` | **Deny từ global**; classic allow không được xét |

Ví dụ giả định target, direction và source/destination đều đã khớp. Hai dải `198.51.100.0/24` và `203.0.113.0/24` là dải dành cho **tài liệu**, không phải IP khách hàng thật.

### 6.5. HFP không khớp, regional policy không khớp

Không tìm thấy rule khớp trong một policy tương đương đi tiếp. Nếu tất cả lớp đều không có rule áp dụng, kết quả phụ thuộc **implied action** và target type. Không được coi “không có deny nào” như bằng chứng ingress tới VM được phép.

## 7. Thiết kế cho doanh nghiệp nhiều project và Shared VPC

### 7.1. Bối cảnh

Tổ chức `ExampleRetail` có các project:

- `retail-network-host`: VPC `prod-vpc` và subnet ở Singapore/Tokyo; làm host cho Shared VPC.
- `retail-app-prod`: workloads sử dụng VPC host; frontend qua load balancer, một số VM backend.
- `retail-data-prod`: VM/job dữ liệu và dịch vụ quản lý riêng.
- `retail-app-dev`: VPC development cho thử nghiệm.

Yêu cầu:

1. Không cho phép SSH trực tiếp từ Internet tới VM production.
2. Chỉ cho phép quản trị VM qua luồng được phê duyệt (ví dụ IAP TCP forwarding hoặc mạng quản trị riêng).
3. Frontend công khai chỉ expose TCP/443 theo thiết kế; backend không được mở trực tiếp đến Internet.
4. Đội ứng dụng tự quản lý luồng nội bộ được phép, nhưng không được phá baseline organization.
5. Có logging cho các rule nhạy cảm, quy trình change và báo cáo bất thường.

### 7.2. Kiến trúc chính sách

~~~mermaid
flowchart TD
    O["Organization HFP<br/>Baseline: cấm cổng quản trị từ nguồn không tin cậy"]
    O --> F["Folder HFP: Production<br/>Hạn chế đường vào production"]
    F --> H["Host project: retail-network-host"]
    H --> V["prod-vpc<br/>Global network firewall policy"]
    V --> SG["Singapore: regional policy nếu cần"]
    V --> TK["Tokyo: regional policy nếu cần"]
    SG --> App["VM backend / GKE node"]
    TK --> App2["VM batch"]
    Shared["Service projects"] -. "Dùng VPC host qua Shared VPC" .-> V
~~~

**Với Shared VPC:** xét quyền quản lý firewall và VPC ở **host project** nơi network tồn tại, kết hợp hierarchy của các project liên quan và loại target. Một workload nằm trong service project nhưng dùng network của host project **không** có nghĩa đội service project được tự quản lý network firewall policy trên host. IAM cho việc thay đổi policy cần tách với IAM triển khai workload.

### 7.3. Ma trận quy tắc tham chiếu

| Scope | Priority minh họa | Direction | Match | Action | Mục đích |
|---|---:|---|---|---|---|
| Organization HFP | 100 | Ingress | TCP/22 từ nguồn không tin cậy vào target VM được chọn | Deny | Baseline SSH |
| Organization HFP | 200 | Ingress | Luồng quản trị được phê duyệt đến target cần thiết | `goto_next` hoặc allow được kiểm soát | Chừa quyết định cho tầng gần workload |
| Folder Production HFP | 300 | Ingress | Dải nguồn bị cấm cho production | Deny | Quy định riêng của production |
| Global network policy | 500 | Ingress | HTTPS tới các VM/frontend target phù hợp | Allow | Mở đúng đường phục vụ ứng dụng |
| Regional network policy | 600 | Egress | Dải đích hoặc protocol riêng Singapore | Allow/Deny | Khác biệt theo region |
| Classic VPC rules | Tùy | Hai hướng | Luồng còn được giao cho project | Allow/Deny | Quy tắc cũ hoặc nhu cầu ứng dụng |

Bảng chỉ là **mô hình logic**, chưa phải bộ rule chạy được. Không dùng `0.0.0.0/0` làm “nguồn không tin cậy” trong khi lại muốn loại trừ IAP/mạng quản trị mà không tạo ngoại lệ chuẩn; phải viết điều kiện match và priority cụ thể.

### 7.4. Một phương án SSH có kiểm soát

Đối với VM cần SSH qua **IAP TCP forwarding**, dải IP nguồn của IAP là `35.235.240.0/20` trong các tình huống IPv4 phù hợp. Mô hình minh họa:

- Chặn ingress TCP/22 từ các nguồn khác qua policy được thiết kế đúng phạm vi.
- Cho phép kết nối từ `35.235.240.0/20` **chỉ đến VM cần quản trị** tại tầng policy thích hợp.
- Xác thực người dùng qua IAM/IAP phù hợp, SSH key/OS Login theo cấu hình; firewall allow **không cấp** quyền SSH.
- Không bật một HFP deny rộng tới `0.0.0.0/0` rồi kỳ vọng network policy allow IAP sẽ ghi đè.

Trong triển khai thật, có thể dùng hai rule HFP với thứ tự cụ thể để allow/tạo ngoại lệ cho IAP trước khi deny còn lại, hoặc dùng cơ chế target/điều kiện phù hợp. Xác minh **effective rules** và đường truy cập trên VM thử nghiệm trước khi áp toàn tổ chức.

## 8. Quy trình thiết kế và phê duyệt firewall policy

1. **Chốt yêu cầu theo luồng:** source, destination, port/protocol, target VM/service, region, chủ ứng dụng và lý do.
2. **Xác định scope:** baseline toàn công ty đặt ở HFP; quy tắc VPC dùng global network policy; ngoại lệ vùng dùng regional network policy.
3. **Chọn target chính xác:** service account/secure tag khi hỗ trợ, tránh mặc định all targets.
4. **Rà effective rules hiện tại:** HFP tổ tiên, regional system policies, classic VPC rules, global và regional policies.
5. **Kiểm tra enforcement order:** mặc định hay đã chuyển `BEFORE_CLASSIC_FIREWALL`?
6. **Thiết kế priority và actions:** những allow/deny nào terminal, chỗ nào cần `goto_next`, trường hợp không match?
7. **Dự kiến tác động:** mô phỏng các kết nối hợp lệ và bất hợp lệ; xét tác vụ quản trị, DNS, health checks, cập nhật phần mềm và đường quay lại.
8. **Tạo policy trong sandbox**, kiểm tra association và dùng target giới hạn trước khi mở rộng.
9. **Bật logging có chọn lọc**, kiểm thử và ghi nhận kết quả.
10. **Mở rộng theo change window được duyệt**, giám sát, có kế hoạch rollback.
11. **Định kỳ rà soát** rule hết hạn, ngoại lệ, thành viên có quyền sửa policy, cost và log.

**Thiết kế không chỉ là “deny càng nhiều càng tốt”.** Một policy egress quá rộng có thể phá DNS, truy cập Google APIs, kéo image từ Artifact Registry, gửi log, kết nối database, Cloud NAT hoặc các health checks cần thiết. Mục tiêu là chỉ cho phép **luồng có lý do**, với khả năng chẩn đoán và khôi phục khi có lỗi.

## 9. Khám phá và kiểm tra bằng Google Cloud Console

Trong Console, chọn đúng project/organization rồi truy cập trang **Firewall policies** hoặc khu vực **VPC network / Firewall** tương ứng (tên menu có thể thay đổi theo giao diện).

### 9.1. Xem hierarchical policies

1. Xác định **organization** chứa target project và chuỗi folder tổ tiên.
2. Mở danh sách hierarchical firewall policies, xem policy ID/short name, association và rules.
3. Kiểm tra policy nào gắn tại organization, folder nào, rule có match target của traffic không.
4. Đọc priority, direction, action và tình trạng bật/tắt.
5. Đối chiếu IAM của người/nhóm được quyền thay đổi policy.

### 9.2. Xem global/regional network policies

1. Chọn **project chứa VPC** (nếu dùng Shared VPC thì thường là host project).
2. Liệt kê policy **global** và policy **regional** tại region đang điều tra.
3. Mở **Associations** để xem policy thực sự gắn với network nào.
4. Xem rules và target filtering; lưu ý policy không associate sẽ không áp vào VPC.
5. Vào VPC network details, xem **Firewall rule view / effective rules** và enforcement order khi có quyền.

### 9.3. Xem một VM network interface

Từ trang **VM instances**, chọn VM và kiểm tra **Network interfaces → effective firewalls** hoặc đường dẫn tương đương. Kết quả giúp nhìn tập rule sau khi loại những rule không nhắm vào interface. Khi khắc phục sự cố ở khu vực có internal load balancer, cần dùng view đúng **region** và **target type**, không suy từ VM view cho load balancer.

## 10. Lệnh `gcloud` chỉ đọc để điều tra

Các lệnh dưới đây dùng để **quan sát**. Thay placeholder bằng giá trị thật trong project/organization được phép. Chúng không thay đổi firewall, network hay route.

~~~bash
# Xác nhận tài khoản và project của Google Cloud CLI.
gcloud auth list
gcloud config get-value project

# Hierarchical firewall policies được quản lý tại organization/folder.
gcloud compute firewall-policies list --organization=ORG_ID
gcloud compute firewall-policies list --folder=FOLDER_ID

# Chi tiết và các rule của hierarchical policy.
gcloud compute firewall-policies describe HFP_ID --organization=ORG_ID
gcloud compute firewall-policies list-rules HFP_ID --organization=ORG_ID

# Global network firewall policies trong project.
gcloud compute network-firewall-policies list \
  --project=HOST_PROJECT_ID \
  --global

# Regional network firewall policies trong project.
gcloud compute network-firewall-policies list \
  --project=HOST_PROJECT_ID \
  --regions=asia-southeast1

# VPC, classic rules và trạng thái mạng.
gcloud compute networks describe prod-vpc \
  --project=HOST_PROJECT_ID
gcloud compute firewall-rules list \
  --project=HOST_PROJECT_ID \
  --filter="network:prod-vpc"
~~~

**Ghi nhớ cú pháp:** `gcloud compute firewall-policies` dành cho **hierarchical**; `gcloud compute network-firewall-policies` dành cho **global/regional network**. Tên gần giống nhau nhưng loại tài nguyên và phạm vi khác nhau.

### 10.1. Xem effective firewall rules

~~~bash
# Các lớp firewall có hiệu lực cho một VPC.
gcloud compute networks get-effective-firewalls prod-vpc \
  --project=HOST_PROJECT_ID

# Các lớp firewall liên quan một region cụ thể của VPC.
gcloud compute network-firewall-policies get-effective-firewalls \
  --region=asia-southeast1 \
  --network=prod-vpc \
  --project=HOST_PROJECT_ID
~~~

Kết quả effective firewalls giúp xem các nguồn policy áp dụng, thứ tự đánh giá và rules liên quan. Không chỉ nhìn tên rule “allow-https” rồi kết luận nó quyết định traffic; cần kiểm tra đúng **target**, **priority**, **match** và **enforcement order**.

### 10.2. Xem một policy global

~~~bash
gcloud compute network-firewall-policies describe POLICY_NAME \
  --project=HOST_PROJECT_ID \
  --global
~~~

Với policy regional, thay `--global` bằng `--region=REGION`. Với một rule cụ thể, tra `gcloud compute network-firewall-policies rules describe --help` để dùng đúng loại `--global-firewall-policy` hoặc region cho phiên bản CLI hiện hành.

**Phân quyền đọc:** người được cấp vai trò xem network không nhất thiết xem được toàn bộ organization policy hoặc association ở tổ tiên. Nếu lỗi `PERMISSION_DENIED`, xác nhận project, organization, identity, IAM scope và policy trước khi yêu cầu quyền cao hơn.

## 11. Ví dụ thao tác tạo global network firewall policy trong sandbox

Chỉ thực hành khi có quyền tạo network policy và đã có **project sandbox/VPC dành cho thử nghiệm**. Các lệnh dưới đây **làm thay đổi hạ tầng** nếu thực thi thật; phần gắn association sẽ làm rules bắt đầu tác động tới các target khớp.

### 11.1. Tạo policy

~~~bash
gcloud compute network-firewall-policies create lab-global-fw \
  --project=SANDBOX_PROJECT_ID \
  --global
~~~

Sau khi tạo, policy **chưa tác động** tới VPC nếu chưa gắn association.

### 11.2. Tạo một rule mẫu

Ví dụ chặn kết nối SSH từ dải IP tài liệu `198.51.100.0/24` tới target VM được chọn trong sandbox:

~~~bash
gcloud compute network-firewall-policies rules create 1000 \
  --project=SANDBOX_PROJECT_ID \
  --firewall-policy=lab-global-fw \
  --global-firewall-policy \
  --direction=INGRESS \
  --action=DENY \
  --src-ip-ranges=198.51.100.0/24 \
  --layer4-configs=tcp:22 \
  --enable-logging
~~~

Dải `198.51.100.0/24` **chỉ để minh họa**; khi thử nghiệm có kiểm soát cần dùng dải IP nguồn thử được phê duyệt. Mẫu không có `--target-secure-tags` hoặc `--target-service-accounts` nên phạm vi target là **rộng** theo đặc tính rule; chỉ nên dùng trong VPC sandbox và không copy nguyên sang production.

### 11.3. Association với network

~~~bash
gcloud compute network-firewall-policies associations create \
  --project=SANDBOX_PROJECT_ID \
  --firewall-policy=lab-global-fw \
  --network=sandbox-vpc \
  --name=lab-global-fw-to-sandbox-vpc \
  --global-firewall-policy
~~~

Sau khi associate, **kiểm tra effective firewalls**. Nếu VPC vẫn dùng `AFTER_CLASSIC_FIREWALL` và classic rule **allow** SSH từ nguồn tương ứng đã match, deny ở network policy sẽ không quyết định luồng ấy. Phải đánh giá kết quả dựa vào **thứ tự thực tế**, không kết luận rule thất bại về cú pháp.

### 11.4. Chuyển enforcement order là thay đổi riêng

Mệnh lệnh minh họa dưới đây **thay đổi thuộc tính VPC** và có thể ảnh hưởng mọi workload:

~~~bash
gcloud compute networks update sandbox-vpc \
  --project=SANDBOX_PROJECT_ID \
  --network-firewall-policy-enforcement-order=BEFORE_CLASSIC_FIREWALL
~~~

Chỉ chạy sau khi đã so sánh effective rules và thử tác động có kiểm soát. Trong production, cần change ticket/owner, thời điểm thực hiện, kiểm thử trước/sau, phương án rollback về **giá trị cũ đã được ghi nhận**; không mặc định mọi VPC ban đầu đều là `AFTER_CLASSIC_FIREWALL`.

### 11.5. Thu hồi an toàn

Để dừng policy áp dụng cho một network, có thể **gỡ association** theo quy trình và quyền phù hợp, rồi đọc lại effective rules. Không xóa nhầm cả policy đang gắn với VPC khác. Đừng chỉnh cục bộ một rule trong shared policy khi chưa xác định tất cả association vì sẽ ảnh hưởng đồng thời nhiều network.

## 12. IAM, quản trị thay đổi và bảo vệ chính policy

### 12.1. Tách quyền quản trị organization và project

| Vai trò công việc | Nhu cầu | Phạm vi quyền phù hợp |
|---|---|---|
| **Org Security / Network Governance** | Thiết kế baseline HFP và association ở organization/folder | Quyền quản lý hierarchical policy và association trong scope được giao |
| **Network Platform Team** | Quản lý VPC, network global/regional policies, effective firewall | Project/VPC hoặc policy liên quan, thường là host project |
| **App Team** | Đề xuất lưu lượng ứng dụng, xem effective rules, một số rule được ủy quyền | Quyền xem và scope hẹp; hạn chế sửa baseline |
| **SRE** | Xem log, chẩn đoán network, xử lý sự cố | Quyền đọc Cloud Logging, Monitoring, network config |
| **Security Audit** | Xem thay đổi, IAM grants và cấu hình để đối soát | Quyền đọc, audit và retention thích hợp |

Role chuẩn như `roles/compute.securityAdmin` hoặc `roles/compute.orgSecurityResourceAdmin` có quyền rộng tương ứng loại tài nguyên và scope; cần **đọc danh sách permission thực tế** trước khi giao. Không cấp `roles/owner` chỉ vì người vận hành cần xem firewall logs.

### 12.2. Quản lý quy tắc như thay đổi bảo mật

- **Người đề xuất:** nêu luồng và mục đích nghiệp vụ, không chỉ “mở port”.
- **Người phê duyệt:** chủ dịch vụ và bảo mật khi target thuộc production.
- **Người triển khai:** kiểm tra association, quy tắc hiện hữu và triển khai theo pipeline/IaC nếu có.
- **Người xác nhận:** thử kết nối hợp lệ và không hợp lệ, xem logs và ứng dụng.
- **Người thu hồi:** xử lý ngoại lệ hết thời hạn; không để rule “temporary” tồn tại vô hạn.

Khi dùng **Terraform** hoặc hạ tầng dưới dạng mã, tránh sửa tay policy do pipeline sở hữu rồi để lần `apply` tiếp theo ghi đè bất ngờ. Dùng change review, import/state phù hợp và kiểm tra drift.

## 13. Chẩn đoán khi traffic không đúng kỳ vọng

### 13.1. Quy trình 8 bước

1. **Chốt flow:** IP nguồn, IP đích, protocol, port, direction, VPC, region và target VM/network interface.
2. **Phân biệt route và firewall:** route đi/về có tồn tại? DNS có trả đúng IP? VPN/BGP ổn không?
3. **Xem hierarchy:** organization/folder HFP nào được associate? Có rule terminal match không?
4. **Xem regional system policies:** có system rule liên quan target/region không?
5. **Xác nhận VPC enforcement order:** `AFTER_CLASSIC_FIREWALL` hay `BEFORE_CLASSIC_FIREWALL`?
6. **Đọc effective rules:** classic VPC, global và regional network policy; kiểm tra target tags/SA, source range, port, disabled, priority.
7. **Kiểm chứng từ đầu tới cuối:** OS firewall, listener, load balancer health, TLS, ứng dụng và quyền kết nối.
8. **Ghi bằng chứng:** rule ID/policy, thời điểm test, kết quả logging/Connectivity Tests, nguyên nhân và thay đổi tối thiểu cần thiết.

### 13.2. Ma trận triệu chứng

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh |
|---|---|---|
| Tạo network deny nhưng SSH vẫn được phép | `AFTER_CLASSIC_FIREWALL`, classic allow thắng trước | Xem enforcement order và classic effective rules |
| Tạo classic allow nhưng request vẫn bị chặn | HFP deny hoặc network deny trong `BEFORE_CLASSIC_FIREWALL` | Đọc effective rules theo lớp |
| Rule HFP không ảnh hưởng dev project | Policy chưa associate hoặc scope folder khác | Kiểm tra organization/folder ancestry và associations |
| Rule network policy không có tác dụng | Policy chưa associate VPC hoặc target mismatch | Kiểm tra policy association/secure tags/SA |
| Chỉ Singapore không truy cập được | Regional policy, subnet, route, frontend hoặc system rule | So kết quả effective firewalls theo region |
| Gán secure tag rồi vẫn không match | Tag scope/binding sai, quyền/propagation, target type không hỗ trợ | Kiểm tra tag effective và target của rule |
| VM sau đổi service account mất kết nối | Rule target dựa trên service account cũ | So cấu hình VM NIC và target account |
| GKE pod không truy cập được dù VPC allow | Kubernetes NetworkPolicy/GKE Dataplane, pod routing, DNS hoặc service mesh | So VPC firewall và policy trong cluster |
| Cloud Run API lỗi 403 dù VPC allow | IAM Invoker, ingress, identity, application auth | Kiểm tra Cloud Run config và HTTP response |
| Không có firewall log cho rule `goto_next` | `goto_next` không phải quyết định terminal | Xem log của rule allow/deny thực sự khớp |
| Timeout dù effective rule `allow` | Route, OS firewall, health check, TLS, backend | Dùng Connectivity Tests, logs và thử protocol/port |
| Chi phí log tăng sau bật ghi mọi rule | Số lượng flow lớn và retention dài | Lọc rule quan trọng, giám sát log volume |

### 13.3. Log và Connectivity Tests

**Firewall Rules Logging** ghi nhận các kết nối được cho phép hoặc từ chối theo quy tắc đã bật log. Đối với policy rule, trường log giúp xác định quyết định liên quan; không bật logging trên `goto_next` vì đó không phải action terminal. Log không đầy đủ ở mọi thời điểm/loại traffic và phải được đọc theo schema của dịch vụ.

**VPC Flow Logs** cung cấp quan sát lưu lượng IP ở phạm vi được hỗ trợ và có sampling/aggregation. **Connectivity Tests** (Network Intelligence Center) mô phỏng đường đi theo cấu hình Google Cloud, hữu ích để tìm route/firewall khả nghi nhưng không xác nhận mọi trạng thái bên trong hệ điều hành, on-premises peer hay ứng dụng.

Quan sát thêm:

- **Cloud Audit Logs**: ai tạo/sửa/xóa policy, rules và associations.
- **Cloud Monitoring**: kết nối lỗi, latency, status của ứng dụng, thay đổi lưu lượng.
- **Cloud Logging**: thông tin rule hit/deny khi logging đã bật, kết hợp request/application logs.
- **Policy/IaC revision history**: giải thích thay đổi trước và sau thời điểm xảy ra lỗi.

### 13.4. Đừng sửa bằng cách mở rộng tất cả

Khi một kết nối TCP/443 thất bại, không nên ngay lập tức tạo `allow all 0.0.0.0/0` ở organization. Hành động đó có thể bypass các deny ở dưới và ảnh hưởng hàng trăm project. Chẩn đoán phải tìm **rule terminal match đầu tiên trong đúng chuỗi enforcement** và xác nhận không còn lỗi từ route, DNS hay application.

## 14. Chi phí, độ tin cậy và giới hạn Cloud NGFW

### 14.1. Chi phí

Cloud NGFW có các nhóm tính năng/tier như **Essentials, Standard, Enterprise**, có khả năng và mức giá khác nhau. Một số kiểu match nâng cao (chẳng hạn FQDN, threat intelligence, address groups, Layer 7 inspection) có điều kiện hỗ trợ và chi phí riêng. Ngoài ra:

- **Firewall logging** có thể phát sinh phí lưu trữ/thu thập/truy vấn Cloud Logging khi khối lượng lớn.
- **Cloud Monitoring/Connectivity Tests** và sản phẩm giám sát có giới hạn và giá tùy loại.
- Traffic đi qua VPN/Interconnect, load balancer hoặc egress vẫn có chi phí mạng theo bảng giá tương ứng.
- Policy sai có thể gây downtime hoặc ngăn health checks, làm tăng chi phí khắc phục.

Không coi các chính sách bảo mật là “miễn phí vô hạn” chỉ vì không cần tạo VM firewall. Kiểm tra trang giá và tính khả dụng của **Cloud NGFW** theo region/tier trước khi triển khai thực tế.

### 14.2. Độ tin cậy và thay đổi quy mô lớn

HFP áp nhiều project rất hữu ích nhưng cũng có **blast radius lớn**. Trước thay đổi organization policy:

1. Liệt kê folder/project/VPC chịu ảnh hưởng.
2. Thử trong scope nhỏ hoặc nhóm tài nguyên đích được giới hạn.
3. Đặt policy/rules dưới kiểm soát phiên bản, gắn owner và ticket.
4. Quan sát kết nối thiết yếu: DNS, metadata/Google APIs, image registry, Cloud SQL, load balancer health checks, kết nối hybrid và pipeline.
5. Lập rollback **ở lớp policy phù hợp**, không tắt toàn bộ bảo mật để khôi phục.
6. Theo dõi sau triển khai và ghi chép bài học khi có gián đoạn.

## 15. Bài thực hành mô phỏng không tạo tài nguyên

### 15.1. Dữ liệu bài toán

Một doanh nghiệp có:

- Organization HFP `org-baseline`:
  - Priority 100: **deny** ingress TCP/22 từ `0.0.0.0/0` tới VM.
  - Priority 200: **goto_next** ingress TCP/443 từ `198.51.100.0/24`.
- Folder production HFP `prod-controls`:
  - Priority 300: **deny** ingress TCP/443 từ `198.51.100.128/25`.
- Classic VPC:
  - Priority 500: **allow** ingress TCP/443 từ `198.51.100.0/24`.
- Global network policy:
  - Priority 400: **deny** ingress TCP/443 từ `198.51.100.0/24`.
- VPC `prod-vpc` có VM frontend mục tiêu được hỗ trợ, global policy đã associate và không có regional system rule terminal match vào các luồng mô phỏng. Không xét deny/allow khác.

### 15.2. Câu hỏi

1. Nguồn `198.51.100.10` gọi TCP/22 tới VM: kết quả? Vì sao?
2. Nguồn `198.51.100.200` gọi TCP/443: rule nào quyết định?
3. Nguồn `198.51.100.10` gọi TCP/443 khi VPC dùng `AFTER_CLASSIC_FIREWALL`: kết quả?
4. Cùng nguồn TCP/443 khi chuyển sang `BEFORE_CLASSIC_FIREWALL`: kết quả?
5. Nếu bỏ global network policy association, quyết định nào còn lại cho tình huống câu 4?
6. Nếu bỏ rule HFP priority 100, liệu classic deny và global allow (nếu có) có tự suy ra kết quả không? Cần thông tin gì?
7. Trong mô hình nhiều project, vì sao không thể chuyển nhiệm vụ “deny SSH mọi production” thành một local rule của project bất kỳ rồi coi là baseline organization?
8. Nếu policy mới dùng `target-service-accounts` nhưng VM dùng service account khác, rule có áp dụng không?
9. Nếu một resource thuộc Cloud Run service chứ không phải VM target, cần dùng những lớp bảo vệ nào thay vì chỉ dựa vào rule VM?
10. Liệt kê tối thiểu năm bước kiểm tra trước khi thay đổi VPC enforcement order.

### 15.3. Gợi ý đáp án

- **Câu 1:** deny ở organization HFP, được xét đầu tiên.
- **Câu 2:** organization HFP priority 200 `goto_next` chuyển sang folder; folder `prod-controls` priority 300 deny vì nguồn thuộc `198.51.100.128/25`.
- **Câu 3:** sau organization `goto_next`, folder không match, classic VPC allow được xét trước global theo `AFTER_CLASSIC_FIREWALL`.
- **Câu 4:** sau HFP, global deny được xét trước classic trong `BEFORE_CLASSIC_FIREWALL`.
- **Câu 5:** không có global rule, classic allow được xét (giả định không có rule terminal khác).
- **Câu 6:** cần biết chính xác direction, target, match, policy associations, enforcement order và các lớp rule khác; không so priority giữa hai policy.
- **Câu 7:** local rule chỉ thuộc VPC của project; không quản lý toàn bộ organization và không có thứ tự ưu tiên HFP.
- **Câu 8:** target mismatch làm rule không áp dụng cho VM đó.
- **Câu 9:** Cloud Run ingress, IAM Invoker, load balancer/Cloud Armor hoặc cơ chế bảo vệ ứng dụng/mạng phù hợp.
- **Câu 10:** thu thập effective rules, traffic matrix, xác nhận các terminal match hiện hành, thử sandbox, đánh giá tác động, có rollback và giám sát.

Đây là **bài toán mô phỏng rule evaluation**, không phải lời khuyên sử dụng các CIDR giả định làm policy thật.

## 16. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ priority là thứ tự chung trên mọi policy | Dự đoán sai allow/deny | Xác định lớp policy trước, priority trong từng policy sau |
| Giả định global network luôn trước classic VPC rules | Deny mới có thể không chặn được allow cũ | Kiểm tra `networkFirewallPolicyEnforcementOrder` |
| Gắn HFP allow rộng vì “đội khác sẽ deny bên dưới” | Allow HFP terminal có thể bypass deny cấp dưới | Dùng `goto_next` và allow có phạm vi hẹp |
| Hiểu `goto_next` là “xét rule kế tiếp trong cùng policy” | Quy tắc sau `goto_next` không được thử | Hiểu nó chuyển sang policy/lớp kế tiếp |
| Quên associate policy | Rules không tác động traffic | Kiểm tra association và target scope |
| Dùng labels/network tags thay secure tags | Rule chọn sai target | Phân biệt tag model và quyền gắn tag |
| Tạo một rule all-targets khi chỉ một VM cần | Blast radius lớn | Dùng service account/secure tag/target resources hỗ trợ |
| Mở ingress IPv4 rồi suy rằng IPv6 đã được mở | IPv6 bị chặn hoặc có policy khác | Xét `::/0`, route và IPv6 rules riêng |
| Chỉ xem VPC rule list | Bỏ qua HFP, regional system và network policies | Xem effective firewalls đúng VPC/region/VM |
| Lấy firewall VM kiểm soát toàn bộ Cloud Run/Cloud SQL | Bỏ sót ingress IAM/service-level | Dùng đúng lớp bảo vệ từng dịch vụ |
| Bật logging cho mọi luồng không kiểm soát | Tăng volume/cost, khó tìm sự cố | Bật có chọn lọc, theo dõi lượng log |
| Gỡ policy chung để chữa lỗi một project | Ảnh hưởng các project khác | Kiểm tra associations, sửa phạm vi nhỏ và rollback |

## 17. Checklist trước khi triển khai

- [ ] Đã xác định **organization/folder/project/VPC/region** và owner của từng lớp.
- [ ] Đã phân biệt hierarchical, regional system, classic VPC, global network và regional network policies.
- [ ] Đã ghi **enforcement order thực tế** của VPC.
- [ ] Đã rà rule **terminal** và `goto_next` trên tất cả lớp chính sách liên quan.
- [ ] Đã chọn priority phù hợp **trong từng policy**; có khoảng trống cho rules bổ sung.
- [ ] Đã phân biệt target service accounts, secure tags, network tags, labels và target resources.
- [ ] Đã kiểm tra policy **association** và phạm vi ảnh hưởng, nhất là Shared VPC.
- [ ] Đã xác định source/destination, direction, IPv4/IPv6, protocol và port cho từng luồng.
- [ ] Đã thử **allow case** và **deny case**, kiểm tra cả ứng dụng, route, DNS và OS firewall.
- [ ] Đã xem effective firewall rules đúng network/region/VM interface.
- [ ] Đã bật logging cần thiết, giám sát chi phí và bảo vệ dữ liệu log.
- [ ] Đã có IAM tối thiểu, phê duyệt, phiên bản chính sách, rollback và người chịu trách nhiệm.
- [ ] Đã xác minh sau triển khai rằng Compute Engine/GKE/Cloud Run và dịch vụ dữ liệu vận hành đúng mong đợi.

## 18. Tài liệu chính thức của Google Cloud

Cú pháp, thứ tự đánh giá, loại target và điều kiện sử dụng tính năng nâng cao có thể thay đổi theo thời gian. Khi thực hiện trong project thật, kiểm tra tài liệu và phiên bản công cụ hiện hành:

- [Cloud NGFW — Firewall policies and rules](https://docs.cloud.google.com/firewall/docs/firewall-policies-overview)
- [Evaluation order for firewall policies and rules](https://docs.cloud.google.com/firewall/docs/firewall-policies-rule-eval-order)
- [Hierarchical firewall policies](https://docs.cloud.google.com/firewall/docs/hierarchical-firewall-policies)
- [Global network firewall policies](https://docs.cloud.google.com/firewall/docs/network-firewall-policies)
- [Regional network firewall policies](https://docs.cloud.google.com/firewall/docs/regional-firewall-policies)
- [Manage hierarchical firewall policies](https://docs.cloud.google.com/firewall/docs/manage-hierarchical-firewall-policies)
- [Manage global network firewall policies](https://docs.cloud.google.com/firewall/docs/manage-global-firewall-policies)
- [Manage regional network firewall policies](https://docs.cloud.google.com/firewall/docs/manage-regional-firewall-policies)
- [Cloud NGFW overview and pricing tiers](https://docs.cloud.google.com/firewall/docs/about-firewalls)
- [gcloud: network firewall policies list](https://docs.cloud.google.com/sdk/gcloud/reference/compute/network-firewall-policies/list)
- [gcloud: hierarchical firewall policies list](https://docs.cloud.google.com/sdk/gcloud/reference/compute/firewall-policies/list)

**Điểm cần nhớ:** Hierarchical firewall policies giúp tổ chức **ấn định ranh giới bảo mật từ trên xuống**; global/regional network firewall policies giúp **quản lý quy tắc theo VPC và region**. Một kết nối được quyết định bởi **đúng chuỗi policy đang được áp dụng**, **rule đầu tiên có kết quả terminal** và các thành phần mạng/ứng dụng liên quan. Nắm thứ tự mặc định `AFTER_CLASSIC_FIREWALL` và tùy chọn `BEFORE_CLASSIC_FIREWALL` là chìa khóa để thiết kế, triển khai, kiểm toán và xử lý sự cố Google Cloud nhất quán giữa nhiều project.
