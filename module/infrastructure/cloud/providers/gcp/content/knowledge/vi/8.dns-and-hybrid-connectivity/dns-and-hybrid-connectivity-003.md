# DNS forwarding, peering và phân giải DNS hybrid

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Phân biệt **Cloud DNS private zone**, **forwarding zone**, **DNS peering zone** và **DNS server policy**; giải thích khi nào cần từng loại.
2. Thiết kế phân giải tên hai chiều giữa workload trên Google Cloud và hệ thống DNS tại trung tâm dữ liệu/on-premises thông qua **Cloud VPN** hoặc **Cloud Interconnect**.
3. Giải thích tại sao **DNS peering không phải VPC Network Peering**, cách chọn producer/consumer VPC và giới hạn DNS peering qua các hop.
4. Triển khai và kiểm chứng một kiến trúc hybrid DNS với các lệnh **gcloud**, truy vấn **dig/nslookup**, quy tắc DNS 53/TCP+UDP và đường trả lời về dải **35.199.192.0/19**.
5. Chẩn đoán các lỗi phổ biến như **NXDOMAIN**, **SERVFAIL**, chọn sai vùng DNS, sai route/region, cache TTL và thiếu quyền IAM.
6. Đánh giá bảo mật, độ tin cậy, quan sát hệ thống và chi phí của cấu hình DNS khi sử dụng Compute Engine, GKE, Cloud Run cùng các dịch vụ lưu trữ/cơ sở dữ liệu.

## 1. Vì sao kiến trúc cloud cần phân giải DNS hybrid?

Một tổ chức thường không di chuyển toàn bộ hệ thống lên cloud cùng lúc. Ví dụ:

- API Java trên **Compute Engine** hoặc **GKE** cần gọi dịch vụ hóa đơn có tên **billing.corp.example.com** đang chạy on-premises.
- Hệ thống giám sát nội bộ cần truy cập một dịch vụ trên Google Cloud bằng tên **api.gcp.example.com**.
- Nhiều project ứng dụng sử dụng chung DNS do nhóm mạng quản trị ở một **hub VPC**.
- Một tác vụ phát hành trên **Cloud Run** cần kết nối database qua mạng riêng và phân giải tên do doanh nghiệp quản lý.

Lệnh gọi HTTPS, kết nối PostgreSQL hoặc ping theo tên đều phụ thuộc vào **phân giải DNS** trước khi lớp truyền dữ liệu có thể hoạt động. Có IP route qua VPN chưa bảo đảm tên miền được phân giải; có DNS trả về IP đúng cũng chưa chứng minh firewall và ứng dụng cho phép kết nối.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học học cách tổ chức project, IAM và VPC, lựa chọn Compute Engine/GKE/Cloud Run, bảo vệ lưu trữ/cơ sở dữ liệu, tự động phát hành và theo dõi độ tin cậy cùng chi phí. DNS hybrid kết nối những kiến thức này: **tên miền đúng → địa chỉ đúng → route đúng → chính sách truy cập đúng → dịch vụ sẵn sàng**.

### Mục tiêu của ví dụ xuyên suốt

Ta giả định doanh nghiệp có ba vùng quản trị:

| Thành phần | Project/VPC | Dải mạng minh họa | Vai trò |
|---|---|---|---|
| Hub Google Cloud | **net-hub-001 / vpc-hub** | **10.50.0.0/16** | Có Cloud VPN/Interconnect và cấu hình DNS trung tâm |
| Spoke ứng dụng | **app-dev-001 / vpc-app** | **10.60.0.0/16** | VM/API Java; không trực tiếp nối VPN với on-premises |
| On-premises | Mạng doanh nghiệp | **172.16.0.0/16** | DNS resolver **172.16.100.10** và **172.16.100.11** |

Hai không gian tên:

- **corp.example.com.**: DNS authoritative đặt ở hệ thống on-premises.
- **gcp.example.com.**: bản ghi private được quản trị trong Cloud DNS.

Tất cả ID, CIDR, tên miền và IP trong bài là **giả định đào tạo**, không phải tài nguyên đã được tạo. Khi triển khai thật, phải dùng domain mà tổ chức kiểm soát, xác nhận IP/route và chính sách DNS hiện có.

## 2. Các khái niệm cơ sở cần phân biệt

### 2.1. DNS resolution khác kết nối mạng

Một truy vấn DNS thường diễn ra theo hai giai đoạn:

1. **Resolver** tìm địa chỉ IP hoặc bản ghi DNS tương ứng tên miền.
2. **Ứng dụng** mở kết nối đến địa chỉ IP nhận được bằng TCP/UDP hoặc giao thức phù hợp.

Ví dụ **billing.corp.example.com → 172.16.20.25** có thể phân giải thành công, nhưng kết nối vẫn thất bại nếu Cloud VPN down, không có route trở về hoặc firewall chặn TCP/443. Ngược lại, ứng dụng kết nối trực tiếp được đến **172.16.20.25** nhưng phân giải tên thất bại là tín hiệu tập trung điều tra lớp DNS.

### 2.2. Authoritative server, recursive resolver và conditional forwarder

| Khái niệm | Công việc | Ví dụ |
|---|---|---|
| **Authoritative DNS server** | Giữ bản ghi có thẩm quyền cho một DNS zone | DNS nội bộ quản lý **corp.example.com.** |
| **Recursive resolver** | Trả lời truy vấn bằng cách tìm nguồn có thẩm quyền hoặc dùng cache | Resolver của VM, DNS nội bộ của tổ chức |
| **Forwarder** | Chuyển truy vấn đến resolver/name server khác | Cloud DNS forwarding zone gửi **corp.example.com.** đến DNS on-prem |
| **Conditional forwarding** | Chỉ chuyển các tên khớp một suffix nhất định | DNS nội bộ forward **gcp.example.com.** đến Cloud DNS inbound IP |
| **Private DNS zone** | Cung cấp bản ghi theo phạm vi mạng được cho phép | Zone **gcp.example.com.** chỉ hiển thị trong một hoặc nhiều VPC |
| **DNS peering zone** | Cho phép một VPC tra cứu tên theo quy tắc DNS của VPC khác | Spoke hỏi hub về **corp.example.com.** |

### 2.3. Cloud DNS resolver của VM

VM Compute Engine thường sử dụng **metadata server 169.254.169.254** làm DNS resolver. Cloud DNS áp dụng quy tắc phân giải của VPC mà VM thuộc về để trả lời truy vấn private DNS, forwarding zone, peering zone hoặc truy vấn công khai tùy cấu hình.

~~~text
VM trong VPC → DNS resolver tại 169.254.169.254
                  |
                  +→ Private zone: dữ liệu Cloud DNS
                  |
                  +→ Forwarding zone: hỏi DNS khác theo suffix
                  |
                  +→ Peering zone: hỏi theo phân giải của VPC producer
                  |
                  +→ Public DNS: khi không bị cấu hình private/forwarding chặn
~~~

Đây là sơ đồ khái quát. Thứ tự phân giải thật còn phụ thuộc **response policy**, GKE cluster-scoped DNS, **longest matching suffix**, DNS server policy và những quy tắc riêng của Cloud DNS. Khi có nhiều cấu hình chồng nhau, phải xem tài liệu **VPC name resolution order** và thử truy vấn thực tế.

## 3. Ba thành phần chính: forwarding zone, peering zone và server policy

### 3.1. Private managed zone: giữ bản ghi private

Ví dụ tạo **gcp.example.com.** trong hub VPC. Bản ghi **api.gcp.example.com. A 10.50.10.20** do Cloud DNS quản lý. Những VPC được gắn với zone có thể hỏi bản ghi theo phạm vi nhìn thấy DNS. Đây không phải một public zone có thể truy vấn tự do từ Internet.

### 3.2. Forwarding zone: chuyển truy vấn một suffix đến DNS target

**Forwarding zone** là một dạng Cloud DNS private zone. Nó không chứa trực tiếp các bản ghi kiểu A/CNAME để người dùng tự thêm. Nó chứa **DNS suffix** và các **forwarding targets**.

Ví dụ:

~~~text
Trong vpc-hub:
  Forwarding zone  : corp.example.com.
  Target name server: 172.16.100.10, 172.16.100.11

VM hỏi billing.corp.example.com.
→ Cloud DNS chọn forwarding zone
→ Cloud DNS chuyển truy vấn đến resolver on-prem
→ Nhận trả lời A 172.16.20.25 hoặc mã lỗi DNS tương ứng
~~~

Chỉ các tên trong phạm vi zone mới được chuyển theo cấu hình này. Vì thế forwarding zone thường phù hợp hơn việc ép **mọi truy vấn DNS** trong VPC đi qua resolver on-premises.

### 3.3. DNS peering zone: chia sẻ kết quả phân giải giữa VPC

**DNS peering zone** tạo một quan hệ **consumer VPC → producer VPC** cho một DNS suffix.

- **Consumer** là mạng có workload thực hiện lookup.
- **Producer** là mạng mà Cloud DNS sử dụng quy tắc phân giải để tra cứu tên cho consumer.
- Từ góc nhìn consumer, các bản ghi private, forwarding zones, Compute Engine internal names hoặc alternative name server phù hợp trong producer có thể được dùng theo quy tắc của producer.

Ví dụ **vpc-app** là consumer cho **corp.example.com.**, còn **vpc-hub** là producer vì hub có forwarding zone đến on-premises.

**DNS peering không yêu cầu VPC Network Peering**. Chúng là hai khả năng khác nhau: DNS peering trao đổi **truy vấn phân giải tên**, còn VPC Network Peering trao đổi **route IP** giữa các VPC. Có tên nhưng không có đường mạng đến địa chỉ IP trả về thì ứng dụng vẫn không kết nối được.

### 3.4. DNS server policy: inbound và outbound ở cấp VPC

Một **DNS server policy** liên kết với VPC có thể khai báo:

- **Inbound forwarding**: cho phép hệ thống on-premises gửi truy vấn DNS đến các **inbound forwarding entry points** của Cloud DNS trong VPC.
- **Outbound forwarding bằng alternative name servers**: chuyển phần lớn truy vấn DNS của VPC sang DNS servers chỉ định, theo thứ tự phân giải riêng của Cloud DNS.
- Các tùy chọn bổ sung được dịch vụ hỗ trợ, như DNS logging hoặc DNS64, với những ràng buộc riêng.

Một VPC chỉ liên kết với **tối đa một DNS server policy**. Nếu cần cả inbound và outbound trong cùng VPC, cấu hình trong **một policy**, thay vì tạo hai policy cạnh tranh.

**Cảnh báo thiết kế:** Alternative name servers của outbound server policy có thể làm Cloud DNS bỏ qua khả năng phân giải nhiều private/forwarding/peering zones và Compute Engine internal DNS theo quy tắc mặc định. Với nhu cầu chỉ forward một domain on-prem, ưu tiên **forwarding zone theo suffix**.

### 3.5. Bảng quyết định

| Yêu cầu | Cơ chế thường phù hợp | Phạm vi |
|---|---|---|
| Tạo bản ghi private được quản trị ở Google Cloud | **Private managed zone** | VPC được phép truy vấn |
| VM trên Google Cloud hỏi tên **corp.example.com.** tại on-prem | **Forwarding zone** | DNS suffix cụ thể |
| Một spoke VPC hỏi tên mà hub VPC phân giải được | **DNS peering zone** | Consumer → producer, một DNS suffix |
| Máy chủ on-prem hỏi tên **gcp.example.com.** trong Cloud DNS | **Inbound DNS server policy** + conditional forwarding ở on-prem | VPC chứa entry point và kết nối hybrid |
| Muốn mọi truy vấn từ VPC qua DNS doanh nghiệp | **Outbound server policy** với alternative name servers | Tác động rộng lên VPC, cần kiểm thử cẩn thận |
| Các project dùng chung private zone trên một mạng Shared VPC | **Private zone trên host network/cross-project binding** khi thích hợp | Quản trị theo network |
| Chỉ truy cập một dịch vụ private trong VPC khác | Có thể xem **Private Service Connect** và DNS đi kèm | Dịch vụ/endpoint, khác DNS peering |

## 4. Kiến trúc hybrid DNS hai chiều

### 4.1. Từ Google Cloud đến on-premises

~~~mermaid
flowchart LR
    A["VM vpc-hub<br/>hoặc VM vpc-app"] --> B["Cloud DNS resolver"]
    B --> C{"corp.example.com.?"}
    C -->|Trong hub| D["Forwarding zone<br/>corp.example.com."]
    D --> E["Cloud VPN / Interconnect"]
    E --> F["DNS on-prem<br/>172.16.100.10/.11"]
    F --> G["A 172.16.20.25"]
~~~

Khi VM ở **vpc-app** dùng peering zone sang hub, truy vấn được xử lý theo DNS producer (**vpc-hub**) trước khi đến forwarding targets on-premises. Kết nối hybrid phải nằm trong VPC có forwarding zone và tuyến DNS được hỗ trợ.

### 4.2. Từ on-premises đến Google Cloud

~~~mermaid
flowchart LR
    A["Ứng dụng on-prem"] --> B["DNS resolver on-prem"]
    B -->|"Conditional forward<br/>gcp.example.com."| C["Cloud VPN / Interconnect"]
    C --> D["Cloud DNS inbound<br/>entry point tại vpc-hub"]
    D --> E["Private zone<br/>gcp.example.com."]
    E --> F["A 10.50.10.20"]
~~~

Đường **inbound** dùng một hoặc nhiều **regional internal IP addresses** do Cloud DNS cấp cho VPC có inbound server policy. Các IP này đóng vai trò điểm nhận truy vấn DNS, không phải IP name server public và không phải **169.254.169.254** mà máy on-premises có thể gọi trực tiếp.

Điểm ingress DNS phải phù hợp với region/VPC nơi lưu lượng hybrid đi vào. Theo tài liệu Cloud DNS, **inbound entry points không truy cập được qua VPC Network Peering hoặc NCC boundaries**; cần đặt inbound policy tại VPC **chứa kết nối hybrid tới on-premises** hoặc thiết kế các entry point cục bộ tương ứng.

### 4.3. Kết quả cuối cùng chưa đủ để truy cập ứng dụng

DNS hybrid chỉ giúp trả lời câu hỏi **“Tên này tương ứng địa chỉ nào?”**. Sau khi ứng dụng có **172.16.20.25** hoặc **10.50.10.20**, lưu lượng nghiệp vụ còn cần:

1. Route đi và route trả về qua Cloud VPN/Interconnect/VPC connection phù hợp.
2. Firewall rules, tổ chức mạng và ACL cho đúng protocol/port.
3. IAM hoặc xác thực ứng dụng/dữ liệu phù hợp.
4. Dịch vụ đang lắng nghe đúng địa chỉ và hoạt động.

**DNS peering zone không tự tạo IP connectivity**. Không được xem cấu hình DNS là thay thế cho thiết kế mạng.

## 5. Chi tiết forwarding zone: target, route và đường trả lời

### 5.1. Những forwarding target nào được hỗ trợ?

Cloud DNS hỗ trợ nhiều nhóm target, với lựa chọn **standard routing** hoặc **private routing**:

| Nhóm target | Ví dụ | Yêu cầu mạng chính |
|---|---|---|
| **Type 1: internal IP trong VPC được phép dùng forwarding zone** | VM DNS hay internal passthrough Network Load Balancer ở VPC đó | Cloud DNS dùng subnet route đến target, firewall cho DNS |
| **Type 2: DNS server on-premises qua hybrid link** | 172.16.100.10 qua VPN/Interconnect | Có custom route tới DNS và route trả lời về dải Cloud DNS |
| **Type 3: public DNS target** | Resolver có public IP trên Internet | Dùng standard routing theo quy tắc public target |
| **Type 4: FQDN target** | dns.corp.example.net. được giải ra IP | Chỉ một FQDN target; giới hạn số IP và phương thức routing phù hợp |

Với một forwarding zone, có thể khai báo **nhiều IP target** hoặc **một FQDN target**, không kết hợp cả hai kiểu cùng một zone. Đối với FQDN target, Cloud DNS thực hiện phân giải ra IP trước khi forward và có các giới hạn riêng; dùng IP tường minh thường đơn giản hơn cho DNS on-prem.

**Không dùng Type 1 target là VM nằm ở một VPC khác** chỉ vì hai VPC đã peering hoặc có VPN. Nếu DNS target thực sự ở VPC thứ hai, tạo forwarding zone trong VPC của target rồi dùng **DNS peering zone** từ VPC thứ nhất.

### 5.2. Dải nguồn 35.199.192.0/19 có ý nghĩa gì?

Khi Cloud DNS forward truy vấn đến private targets theo đường forwarding thông thường, truy vấn xuất phát từ dải **35.199.192.0/19** của Cloud DNS. Đây là dải dùng bởi cơ chế forwarding của Google, không phải subnet của VM gửi truy vấn.

Do đó DNS on-prem phải cho phép:

- **Nguồn:** 35.199.192.0/19.
- **Đích:** resolver on-prem, ví dụ 172.16.100.10 và 172.16.100.11.
- **Giao thức:** UDP **53** và TCP **53**.
- **Phản hồi:** trở về đúng Cloud DNS source IP qua **VPC/đường hybrid nơi truy vấn đi ra**.

On-premises cần route đến **35.199.192.0/19** về **cùng VPC** chứa forwarding zone và kết nối VPN/Interconnect. Với Cloud Router BGP, có thể cấu hình **custom route advertisement** cho prefix đó; với kết nối static routing cần route tương đương theo phương án mạng hỗ trợ.

~~~text
Google Cloud DNS 35.199.192.0/19
        |
  VPC hub → VPN/Interconnect → 172.16.100.10:53
        ^                             |
        |                             v
        +----- route trở về 35.199.192.0/19
                 qua đúng VPC hub
~~~

**Trả lời từ chính target đã nhận câu hỏi.** Nếu DNS server **172.16.100.10** chuyển tiếp cho server khác và server khác trả gói DNS trực tiếp về Cloud DNS bằng IP riêng của mình, phản hồi có thể bị bỏ vì source IP không trùng IP target được Cloud DNS gửi truy vấn. Resolver 172.16.100.10 cần trả kết quả từ chính địa chỉ của nó.

### 5.3. Region và hạn chế khi đi qua peering

Cloud DNS chọn tuyến từ **VPC được phép dùng forwarding zone**. Với Type 2 target, các tuyến custom static/dynamic hợp lệ dẫn đến on-prem phải hiện diện trong đúng VPC và vùng theo điều kiện định tuyến của dịch vụ.

Cloud DNS **không dùng IP connectivity bắc cầu qua VPC Network Peering** để truy cập forwarding target. Một VM ở spoke có thể **dig trực tiếp** đến DNS on-prem do route VPN được nhập qua peering, nhưng **forwarding zone đặt trong spoke** trỏ vào DNS on-prem qua VPN của hub vẫn có thể thất bại. Cách đúng:

1. Đặt forwarding zone tại **hub** có hybrid link.
2. Đặt **DNS peering zone** tại spoke và trỏ tới hub.
3. Kiểm tra giới hạn DNS peering/region, route và DNS target như thiết kế.

### 5.4. Cache và tính sẵn sàng

Cloud DNS có thể cache kết quả trả về từ forwarding targets. Với target đang hoạt động, thời gian cache bị giới hạn bởi **giá trị nhỏ hơn giữa TTL của record và 60 giây** theo mô hình forwarding zone được tài liệu mô tả. Nếu mọi target mất liên lạc, kết quả đã cache có quy tắc giữ lại theo TTL riêng.

**TTL không thay thế HA.** Nên có ít nhất hai resolver on-prem phù hợp, chạy ổn định, được phép trả lời DNS qua VPN/Interconnect. Cloud DNS chọn target theo thuật toán xếp hạng có xét kết quả và độ trễ; **không mặc định truy vấn theo thứ tự cố định** giống danh sách trong câu lệnh.

## 6. Chi tiết DNS peering: consumer, producer và giới hạn hop

### 6.1. DNS peering là quan hệ một chiều

Nếu **vpc-app → vpc-hub** cho suffix **corp.example.com.**, các workload trong vpc-app có thể được phân giải tên theo chính sách DNS ở vpc-hub. Điều này **không tự động** cho phép vpc-hub phân giải một suffix chỉ có trong vpc-app.

Muốn tra cứu chiều ngược lại, cần thiết kế riêng một peering zone hoặc private zone visibility phù hợp. Đừng giả định **DNS peering hai chiều** vì tên gọi là *peering*.

### 6.2. DNS peering khác VPC Network Peering ở khả năng truyền tuyến

**VPC Network Peering không định tuyến IP bắc cầu**: A ↔ B, B ↔ C không cho phép chuyển IP từ A đến subnet C qua B.

**Cloud DNS peering lại hỗ trợ tối đa một transitive hop** giữa **ba VPC** theo tài liệu chính thức. Ví dụ:

~~~mermaid
flowchart LR
    A["VPC A<br/>DNS consumer"] -->|"Peering zone A → B"| B["VPC B<br/>trung gian"]
    B -->|"Peering zone B → C"| C["VPC C<br/>DNS producer cuối"]
~~~

Đây là **truyền tiếp truy vấn DNS** giữa producer/consumer, không phải chuyển tiếp gói IP cho ứng dụng. Không được thiết kế chuỗi DNS peering dài hơn mức hỗ trợ, và vẫn phải kiểm tra quy tắc phân giải của từng suffix/producer.

### 6.3. DNS peering không yêu cầu peering IP

Bạn có thể cấu hình DNS peering giữa hai VPC không kết nối trực tiếp bằng VPC Network Peering. Nếu sau khi nhận kết quả A record, ứng dụng cần kết nối đến IP ở VPC producer, vẫn phải thiết kế riêng:

- VPC Network Peering trực tiếp, Shared VPC, NCC hoặc kết nối khác theo tính năng được hỗ trợ.
- **Private Service Connect** nếu chỉ cần tiêu thụ một dịch vụ thay vì toàn bộ dải subnet.
- Firewall, route, IAM và DNS của service đích.

### 6.4. Khi DNS producer có forwarding zone

Một thiết kế hub/spoke hợp lệ:

~~~text
VM trong vpc-app
  -> DNS peering zone (corp.example.com.) trong vpc-app
  -> Cloud DNS xử lý theo vpc-hub
  -> forwarding zone (corp.example.com.) trong vpc-hub
  -> resolver on-prem qua VPN/Interconnect của vpc-hub
~~~

Khi **global dynamic routing** ở producer VPC không bật, Cloud DNS có giới hạn region đối với forwarding qua peering: producer cần có VM, VLAN attachment hoặc Cloud VPN tunnel trong **cùng region với VM consumer** đang thực hiện truy vấn để chọn tuyến phù hợp. Vì vậy một kiến trúc DNS hoạt động ở region A nhưng lỗi từ region B cần kiểm tra **producer's regional resources**, dynamic routing và route reachability.

### 6.5. Quyền IAM khi tạo peering zone

Người tạo peering zone cần quyền quản lý DNS zone trong project consumer. Để chọn producer VPC, principal tạo zone còn cần quyền **dns.networks.targetWithPeeringZone**, thường được cấp qua **roles/dns.peer** trên project producer theo cấu hình IAM được chấp thuận.

IAM DNS peering chỉ kiểm soát **quyền tạo quan hệ phân giải**; nó không cấp **quyền truy cập tài nguyên** ở producer và không tự mở firewall.

## 7. Thực hành cấu hình từ hub ra on-prem bằng forwarding zone

Trong các lệnh sau, project, network, domain và IP là ví dụ. Chỉ thực hiện trên môi trường thực hành được phép và thay bằng cấu hình thực tế. Trước khi tạo zone, phải xác minh Cloud DNS API được bật, principal có quyền **roles/dns.admin** hoặc quyền tương ứng, DNS target đã hoạt động và VPC hub có kết nối hybrid hợp lệ.

### Bước 1 — Khảo sát tài nguyên

~~~bash
# Kiểm tra project và VPC hub
gcloud projects describe net-hub-001
gcloud compute networks describe vpc-hub --project=net-hub-001

# Xem những DNS zones hiện có, tránh trùng suffix/nhầm mô hình
gcloud dns managed-zones list --project=net-hub-001

# Xem DNS server policies đang liên kết
gcloud dns policies list --project=net-hub-001
~~~

Kiểm tra trên hệ thống mạng thực: Cloud VPN/Interconnect, route đến **172.16.100.10/11**, route trả lời đến **35.199.192.0/19**, DNS ACL và các thiết bị firewall.

### Bước 2 — Tạo forwarding zone trong vpc-hub

~~~bash
gcloud dns managed-zones create corp-forward \
  --project=net-hub-001 \
  --description="Forward corp.example.com to on-prem DNS" \
  --dns-name="corp.example.com." \
  --visibility=private \
  --networks=vpc-hub \
  --forwarding-targets=172.16.100.10,172.16.100.11
~~~

**--forwarding-targets** sử dụng **standard routing**; đối với private IP RFC 1918 của hệ thống hybrid, Cloud DNS định tuyến trong VPC có zone tới on-prem như thiết kế. Tùy nhu cầu, **--private-forwarding-targets** có thể áp dụng private routing cho những IP đặc biệt ngoài RFC 1918; cần xác nhận loại IP target và giới hạn sản phẩm trước khi chọn.

Đừng nhập URL ứng dụng **https://billing.corp.example.com** làm target. Target của forwarding zone phải là **DNS name server** (IP hoặc FQDN trong loại được hỗ trợ), không phải web service.

### Bước 3 — Đọc lại cấu hình

~~~bash
gcloud dns managed-zones describe corp-forward \
  --project=net-hub-001 \
  --format="yaml(name,dnsName,visibility,privateVisibilityConfig,forwardingConfig)"
~~~

Xác nhận suffix **corp.example.com.**, VPC được phép tra cứu và danh sách forwarding targets. Forwarding zone không chứa các A record doanh nghiệp; bản ghi thuộc DNS on-prem.

### Bước 4 — Kiểm thử từ một VM trong vpc-hub

Trên VM Linux đang gắn NIC vào vpc-hub và dùng DNS resolver mặc định:

~~~bash
# Dùng metadata resolver của Compute Engine
dig @169.254.169.254 billing.corp.example.com. A

# Truy vấn server on-prem trực tiếp để khoanh vùng lỗi (nếu route/ACL cho phép)
dig @172.16.100.10 billing.corp.example.com. A

# Khi cần kiểm tra phản hồi qua TCP thay vì UDP
dig +tcp @169.254.169.254 billing.corp.example.com. A
~~~

Nếu truy vấn trực tiếp đến **172.16.100.10** thành công nhưng qua metadata resolver thất bại, tập trung kiểm tra forwarding zone, dải nguồn Cloud DNS, đường trở về và cấu hình DNS target. Nếu cả hai đều thất bại, cần kiểm tra route, firewall, dịch vụ DNS nguồn và tên miền.

**Cẩn trọng:** Direct dig từ VM dùng source IP của VM; Cloud DNS forwarding dùng source **35.199.192.0/19**. Vì vậy direct dig thành công **không chứng minh** on-prem firewall đã cho phép Cloud DNS.

## 8. Thực hành DNS peering từ spoke đến hub

Giả sử **vpc-app** của **app-dev-001** cần tra cứu **corp.example.com.** theo forwarding zone của hub. Ở project consumer, tạo **peering zone** trỏ producer:

~~~bash
gcloud dns managed-zones create corp-from-spoke \
  --project=app-dev-001 \
  --description="Resolve corp.example.com via hub VPC" \
  --dns-name="corp.example.com." \
  --visibility=private \
  --networks=vpc-app \
  --target-project=net-hub-001 \
  --target-network=vpc-hub
~~~

Lệnh yêu cầu principal có quyền tạo Cloud DNS zone ở **app-dev-001** và quyền **dns.networks.targetWithPeeringZone** trên **vpc-hub** của producer. Nếu bị **403**, kiểm tra IAM, project và VPC trước khi cho rằng DNS routing lỗi.

~~~bash
gcloud dns managed-zones describe corp-from-spoke \
  --project=app-dev-001 \
  --format="yaml(name,dnsName,visibility,peeringConfig,privateVisibilityConfig)"
~~~

Kiểm thử từ VM thuộc **vpc-app**:

~~~bash
dig @169.254.169.254 billing.corp.example.com. A
~~~

Đường phân giải dự kiến: **vpc-app → DNS peering zone → vpc-hub → forwarding zone → DNS on-prem**. Cần xác minh cả kết quả trả về và khả năng ứng dụng **kết nối đến IP** tương ứng theo mạng thực. Không phải tạo **VPC Network Peering** chỉ để làm cho DNS peering hoạt động.

## 9. Thực hành chiều ngược lại: on-premises hỏi Cloud DNS private zone

### Bước 1 — Tạo private zone ở hub

~~~bash
gcloud dns managed-zones create gcp-private \
  --project=net-hub-001 \
  --description="Private service names in hub" \
  --dns-name="gcp.example.com." \
  --visibility=private \
  --networks=vpc-hub
~~~

Thêm bản ghi minh họa:

~~~bash
gcloud dns record-sets transaction start \
  --project=net-hub-001 \
  --zone=gcp-private

gcloud dns record-sets transaction add 10.50.10.20 \
  --project=net-hub-001 \
  --zone=gcp-private \
  --name="api.gcp.example.com." \
  --type=A \
  --ttl=300

gcloud dns record-sets transaction execute \
  --project=net-hub-001 \
  --zone=gcp-private
~~~

Trước khi dùng thật, địa chỉ **10.50.10.20** phải thuộc dịch vụ hợp lệ trong mạng và dịch vụ phải có đường truy cập, firewall và xác thực đúng.

### Bước 2 — Tạo inbound DNS server policy

~~~bash
gcloud dns policies create hub-inbound \
  --project=net-hub-001 \
  --description="Inbound Cloud DNS for on-prem resolvers" \
  --networks=vpc-hub \
  --enable-inbound-forwarding
~~~

Nếu VPC đã có một server policy khác, cần **cập nhật policy hiện tại** thay vì cố gắn policy thứ hai lên cùng VPC.

### Bước 3 — Tìm regional inbound DNS entry points

~~~bash
gcloud compute addresses list \
  --project=net-hub-001 \
  --filter='purpose = "DNS_RESOLVER"' \
  --format='table(address,region,subnetwork)'
~~~

Đối chiếu các IP **DNS_RESOLVER** với VPC và region của kết nối hybrid. Đây là những internal IP do Google quản lý cho inbound forwarding. IP có thể thay đổi nếu tắt/bật lại inbound forwarding hoặc tạo lại VPC; cần ghi nhận trong cấu hình DNS nội bộ và quy trình cập nhật.

Google Cloud tự nhận **TCP/UDP 53** tại inbound entry points; không cần tạo firewall rule Google Cloud dành riêng cho chính địa chỉ inbound resolver như với VM. Nhưng **router, firewall và DNS forwarder on-prem** vẫn phải được cấu hình để gửi được truy vấn đến IP này.

### Bước 4 — Cấu hình conditional forwarder tại on-premises

Tại DNS nội bộ (Windows Server DNS, BIND hoặc thiết bị DNS của doanh nghiệp), tạo rule:

~~~text
Suffix cần chuyển : gcp.example.com.
Target DNS server : <IP inbound Cloud DNS tại region nối VPN/Interconnect>
Transport         : UDP 53 và TCP 53
Fallback/HA       : Thiết kế theo các entry point và region được hỗ trợ
~~~

Không trỏ conditional forwarder vào **169.254.169.254**. Địa chỉ này là resolver của VM trong Google Cloud, không phải DNS endpoint để on-premises truy cập.

### Bước 5 — Kiểm thử từ on-premises

~~~bash
# Dùng địa chỉ DNS inbound thật đã tìm được
dig @INBOUND_DNS_IP api.gcp.example.com. A

# Kiểm tra qua DNS resolver doanh nghiệp sau khi cấu hình conditional forwarding
dig @ONPREM_DNS_IP api.gcp.example.com. A

# Nếu cần kiểm tra TCP
dig +tcp @INBOUND_DNS_IP api.gcp.example.com. A
~~~

Mong đợi một A record trỏ về **10.50.10.20**. Tiếp theo kiểm tra **route on-prem → 10.50.10.20**, firewall, cổng ứng dụng và khả năng trả lời; không đánh đồng thành công DNS với thành công HTTPS.

### Bước 6 — Nếu spoke cũng cần tra cứu tên của hub

Ví dụ workload trong **vpc-app** muốn phân giải **api.gcp.example.com.**. Có thể:

- Tạo thêm một **DNS peering zone** cho suffix **gcp.example.com.** trong vpc-app trỏ về vpc-hub.
- Hoặc cân nhắc chia sẻ private zone với nhiều VPC theo mô hình quản trị và tính năng được hỗ trợ.

Chỉ tạo peering zone **corp.example.com.** trong vpc-app **không tự làm mọi suffix khác của vpc-hub có hiệu lực**.

## 10. Những khác biệt giữa outbound forwarding zone và outbound server policy

Sự khác biệt này quyết định một hệ thống DNS có thể giữ được phân giải nội bộ của Google Cloud hay không.

### 10.1. Forwarding zone: chỉ chuyển các tên phù hợp

Ví dụ VPC có hai private DNS suffix:

- **gcp.example.com.** do Cloud DNS quản lý.
- **corp.example.com.** cần forward đến on-premises.

Forwarding zone dành cho **corp.example.com.** giúp hai nguồn DNS cùng tồn tại. Truy vấn tên khác có thể tiếp tục theo quy tắc phân giải VPC và public DNS nếu không bị cấu hình khác chặn.

### 10.2. Outbound server policy: thay đổi rộng đường đi của truy vấn

Ví dụ cấu hình toàn VPC dùng alternative name server:

~~~bash
# Chỉ là ví dụ để hiểu cơ chế; cần phân tích tác động trước khi áp dụng
gcloud dns policies create hub-outbound \
  --project=net-hub-001 \
  --networks=vpc-hub \
  --alternative-name-servers=172.16.100.10,172.16.100.11
~~~

Khi VM vẫn dùng metadata resolver nhưng VPC có alternative name servers, Cloud DNS gửi phần lớn truy vấn tới alternative name servers theo cơ chế outbound server policy. Điều này có thể khiến VM **không còn phân giải được private zones, peering zones, forwarding zones và Compute Engine internal DNS** theo đường mặc định. Đây là thay đổi phạm vi rộng, dễ gây lỗi cho workload.

Hơn nữa VPC chỉ có **một DNS server policy**. Nếu đã có **hub-inbound**, không thể tạo **hub-outbound** thứ hai cùng áp dụng cho vpc-hub. Cần chỉnh **hub-inbound** thành một policy chứa cả inbound và outbound khi thiết kế thực sự cần.

**Khuyến nghị:** triển khai **forwarding zone theo suffix** khi cần truy vấn domain on-premises, và dùng outbound server policy khi đã hiểu toàn bộ yêu cầu DNS, có giải pháp alternative name server chịu trách nhiệm phân giải mọi tên cần thiết.

## 11. DNS resolution order, overlapping zones và split-horizon

### 11.1. Longest suffix match

Giả sử có:

- Private zone **example.com.**
- Forwarding zone **corp.example.com.**

Khi VM hỏi **app.corp.example.com.**, Cloud DNS xét zone phù hợp nhất theo thứ tự phân giải và suffix cụ thể hơn sẽ chi phối. Những nguyên tắc ưu tiên còn phụ thuộc loại zone và chính sách hiện hành. Phải kiểm tra **VPC name resolution order**, đặc biệt khi có nhiều zone trùng suffix, peering zone hoặc response policy.

### 11.2. Split-horizon DNS

Một tên miền có thể có bản ghi **private** khi truy vấn từ VPC được phép và bản ghi **public** khi truy vấn từ Internet. Ví dụ:

~~~text
api.example.com. từ VM VPC:   10.50.10.20 (private)
api.example.com. từ Internet: 203.0.113.20 (ví dụ public)
~~~

Các địa chỉ trên chỉ để minh họa. Cần bảo đảm mỗi không gian tên được quản lý rõ ràng; private zone có thể che thông tin public bên dưới suffix đối với VPC được phép. Nếu bản ghi không tồn tại trong private zone đang được chọn, không nên mặc định rằng resolver sẽ tự tìm bản ghi cùng tên ở public DNS.

### 11.3. NXDOMAIN, SERVFAIL và timeout nói lên điều gì?

| Kết quả | Ý nghĩa cơ bản | Gợi ý điều tra |
|---|---|---|
| **NOERROR + ANSWER** | Resolver trả bản ghi | Kiểm tra đúng IP và TTL; sau đó kiểm tra IP connectivity |
| **NOERROR nhưng không có A** | Có thể tồn tại tên nhưng không có record type được hỏi | Thử AAAA/CNAME, xem dữ liệu zone và ứng dụng |
| **NXDOMAIN** | Resolver không tìm được tên theo nguồn dữ liệu được chọn | Tên sai, suffix/zone sai, private zone che public zone, record không tồn tại |
| **SERVFAIL** | Resolver gặp lỗi xử lý hoặc không thể lấy kết quả từ upstream | Forwarding target không tới được, quá hạn, lỗi DNSSEC/upstream/route |
| **Timeout** | Không nhận phản hồi trong thời gian chờ | Route/firewall/TCP-UDP 53, DNS server down, response bị bỏ |
| **REFUSED** | DNS server từ chối truy vấn | DNS ACL, chính sách resolver, nguồn truy vấn không được phép |

**Không nên sửa IAM hoặc firewall một cách ngẫu nhiên chỉ dựa vào NXDOMAIN.** Hãy xác định truy vấn đã đi đến resolver nào, chọn zone nào, target nào và nhận được mã trả lời nào.

## 12. Bảo mật và độ tin cậy trong DNS hybrid

### 12.1. Kiểm soát đường DNS

- Chỉ cho phép **UDP/TCP 53** giữa các resolver nguồn/đích được phê duyệt; không mở rộng toàn bộ dải mạng nếu không cần.
- Với forwarding đến private targets, on-prem phải cho phép nguồn **35.199.192.0/19**. Đây là phạm vi nguồn của Cloud DNS forwarding, không phải yêu cầu cho phép mạng đó trên mọi dịch vụ nội bộ.
- Hạn chế quyền **roles/dns.admin** và **roles/dns.peer** theo nguyên tắc ít quyền nhất; review mọi thay đổi zone, server policy, peering.
- Đặt private zone trong đúng mạng cần dùng; không cấp quyền phân giải rộng hơn phạm vi nghiệp vụ.
- Bảo vệ DNS on-prem khỏi open recursion và cấu hình để tránh vòng lặp forwarding **corp → gcp → corp**.
- DNS giải quyết tên, **không thay thế** IAM, mã hóa kết nối TLS hay phân đoạn mạng ứng dụng.

### 12.2. High availability

Sự phụ thuộc gồm **Cloud DNS**, VPN/Interconnect, Cloud Router/route, mạng on-prem và resolver bên ngoài. Để giảm điểm lỗi đơn:

1. Dùng nhiều DNS targets on-prem ở các failure domains phù hợp.
2. Thiết kế hybrid connectivity dự phòng và return routes rõ ràng.
3. Kiểm tra ảnh hưởng khi một region không còn hybrid link hoặc khi policy inbound bị thay đổi.
4. Đặt TTL phù hợp, không quá thấp gây tăng query volume và không quá cao gây khó đổi bản ghi.
5. Kiểm thử chuyển đổi khi một resolver upstream hoặc VPN tunnel mất kết nối.
6. Theo dõi chất lượng phân giải **từ chính vị trí workload** thay vì chỉ đo từ máy quản trị.

### 12.3. Quan sát và vận hành

Cloud DNS hỗ trợ logging/monitoring theo các tính năng và phạm vi của dịch vụ. Cần phối hợp:

- **Cloud DNS query logging** hoặc logging phù hợp với private DNS và policies, cân nhắc dữ liệu nhạy cảm trong tên truy vấn.
- **Cloud Monitoring** đối với dịch vụ DNS được hỗ trợ, VPN/Interconnect, latency, error rates và availability.
- **VPC Flow Logs/firewall logs** hoặc network telemetry khi bật và phù hợp với đường đi của traffic.
- **Log DNS on-prem** để xác định Cloud DNS queries từ nguồn **35.199.192.0/19** có tới target không.
- **Synthetic tests** chạy định kỳ từ VM trong hub, VM trong spoke và một máy on-prem; kiểm tra cả A/AAAA/CNAME hoặc các record type cần dùng.

### 12.4. Chi phí

Cloud DNS có thể tính phí theo **managed zones**, **số truy vấn**, loại bản ghi/tính năng và logging theo bảng giá hiện hành. Kết nối Cloud VPN/Interconnect, egress và hệ thống DNS on-prem cũng có chi phí riêng. Truy vấn DNS forwarding qua hybrid không đồng nghĩa dữ liệu ứng dụng sau khi phân giải được truyền miễn phí. Theo dõi budget theo project và service; kiểm tra giá hiện hành trước khi dự toán.

## 13. Quy trình chẩn đoán khi DNS hybrid lỗi

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra ưu tiên |
|---|---|---|
| VM hub hỏi **corp.example.com** được nhưng VM spoke không được | Thiếu/wrong DNS peering zone, thiếu quyền mạng consumer, regional forwarding limits | Zone consumer, producer, DNS suffix, region và route |
| VM spoke **dig trực tiếp on-prem** được nhưng lookup qua forwarding zone không được | Forwarding zone đặt sai VPC/đường transitive không được hỗ trợ | Đưa forwarding zone về hub; tạo peering zone trong spoke |
| On-prem truy vấn **gcp.example.com** timeout | Inbound forwarding chưa bật, dùng sai entry point IP/region, thiếu route/ACL | DNS policy, IP DNS_RESOLVER, Cloud VPN/Interconnect |
| Forwarding zone trả **SERVFAIL** | Target down, không được route, DNS firewall chặn nguồn Cloud DNS, trả lời sai source | Target health, **35.199.192.0/19**, UDP/TCP 53, route trả về |
| Truy vấn qua on-prem DNS trả **NXDOMAIN** | Conditional forwarder sai suffix hoặc authoritative zone thiếu record | Kiểm tra zone và bản ghi tại source |
| DNS name đúng nhưng ứng dụng kết nối thất bại | IP routing/firewall/TLS hoặc ứng dụng lỗi | Route đi/về, cổng TCP, IAM và log dịch vụ |
| Sau thay server policy, tên nội bộ Compute Engine không phân giải | Alternative name servers override private DNS | Đọc lại outbound DNS policy và name resolution order |
| Chỉ lỗi từ VM region B | Thiếu regional resource của producer khi dynamic routing không global | VPC producer, Cloud Router và region của VM consumer |
| Tên hoạt động chập chờn sau khi đổi A record | Cache/TTL, resolver khác nhau giữa clients | TTL, response theo từng resolver, log forward |
| Lỗi tạo DNS peering zone **403** | Thiếu quyền trên producer VPC hoặc consumer project | **roles/dns.peer**, **roles/dns.admin**, đúng principal |
| Một tên resolve khác nhau giữa on-prem và VPC | Split-horizon, private zone override, suffix conflict | So sánh output từ từng resolver và zone association |
| Client DNS nhận **REFUSED** | DNS ACL hoặc policy của upstream | Xem nguồn request, DNS server log, IP allowlist |

### Từng bước khoanh vùng

1. **Xác định điểm xuất phát:** VM hub, VM spoke, pod GKE, service Cloud Run hay máy on-prem? DNS của từng môi trường có thể khác.
2. **Hỏi trực tiếp resolver đang dùng** và ghi lại FQDN, record type, response code, TTL, answer section.
3. **Xác định zone khớp suffix** và policy đang có hiệu lực cho VPC.
4. **Nếu DNS peering:** kiểm tra producer/consumer, điều kiện region và giới hạn hop.
5. **Nếu forwarding:** kiểm tra DNS target, source **35.199.192.0/19**, return route, Cloud VPN/Interconnect và UDP/TCP 53.
6. **Nếu inbound:** kiểm tra policy, đúng regional entry point, conditional forwarder, route/ACL on-prem và vùng hybrid.
7. **Nếu DNS có kết quả đúng:** chuyển sang điều tra IP connectivity, firewall, service và authentication của ứng dụng.

Ví dụ một cặp lệnh dễ so sánh:

~~~bash
# Trong VM Google Cloud, kiểm tra theo quy tắc DNS của VPC
dig @169.254.169.254 billing.corp.example.com. A

# Từ VM có route trực tiếp đến DNS on-prem, kiểm chứng bản ghi gốc
dig @172.16.100.10 billing.corp.example.com. A
~~~

Lưu lại **QUERY TIME, status, ANSWER, TTL và SERVER** trước/sau thay đổi. Khi có nhiều DNS targets, truy vấn từng target trực tiếp để phát hiện dữ liệu không đồng bộ.

## 14. Tình huống tổng hợp: Java API, database và hệ thống ERP on-prem

Công ty **Hòa Bình** đang dần chuyển dịch vụ lên Google Cloud:

- **API Java/Spring** chạy trên Compute Engine trong **vpc-app**.
- **Cloud Run** chạy worker kiểm kê, tích hợp qua mạng riêng phù hợp với VPC.
- **Cloud SQL** lưu dữ liệu đơn hàng trên Google Cloud.
- **ERP on-prem** còn lưu lịch sử và cung cấp endpoint **erp.corp.example.com.**
- **Hệ thống vận hành on-prem** cần gọi **orders.gcp.example.com.** qua private connectivity.

Nhóm mạng quản lý **vpc-hub**, Cloud VPN và DNS on-prem; nhóm ứng dụng chỉ quản trị **vpc-app**.

### 14.1. Thiết kế phù hợp

~~~mermaid
flowchart LR
    APP["Java API / worker<br/>vpc-app"] -->|"DNS peering cho corp.example.com."| HUB["Cloud DNS tại vpc-hub"]
    HUB -->|"Forwarding zone"| ONDNS["DNS on-prem"]
    ONDNS -->|"erp.corp.example.com."| ERP["ERP private IP"]
    OPS["On-prem operations"] -->|"Conditional forwarding<br/>gcp.example.com."| IN["Cloud DNS inbound hub"]
    IN --> ZONE["Private zone<br/>gcp.example.com."]
    ZONE --> ORD["orders.gcp.example.com."]
~~~

Thiết kế gồm hai chiều DNS độc lập:

1. **GCP → on-prem:** spoke peering zone cho **corp.example.com.**; hub forwarding zone đến DNS on-prem.
2. **On-prem → GCP:** on-prem conditional forwarding cho **gcp.example.com.** tới inbound entry points của hub; hub private zone lưu records.

Đường IP của dữ liệu ERP và API vẫn phải được kiểm tra riêng, chẳng hạn cấu hình route/VPC connectivity, firewall, IAM và TLS.

### 14.2. Tiêu chí nghiệm thu

| Kiểm thử | Điểm kiểm tra | Kỳ vọng |
|---|---|---|
| VM trong hub hỏi **erp.corp.example.com.** | Hub | Có A record on-prem chính xác |
| VM trong spoke hỏi cùng tên | Spoke | Có A record theo producer hub |
| VM trong spoke kết nối ERP bằng IP được trả về | Spoke → on-prem | Route/firewall/port hợp lệ |
| On-prem hỏi **orders.gcp.example.com.** | Conditional forwarder | Có A record từ Cloud DNS private zone |
| On-prem kết nối địa chỉ trả về | On-prem → Google Cloud | Route và chính sách cho phép |
| Tắt một DNS server on-prem | Hub/spoke | Vẫn có phân giải qua DNS target còn khỏe khi thiết kế HA phù hợp |
| Kiểm tra nguồn DNS request tại target on-prem | On-prem firewall/log | Thấy dải nguồn Cloud DNS expected |
| Một region mất hybrid link | Region liên quan | Biết hành vi suy giảm/failover theo thiết kế |
| Thay đổi DNS record | Cả hai chiều | TTL/cache phù hợp, không kết luận sai trước khi hết TTL |
| Kiểm tra IAM và logs | Hub/consumer | Zone và peering chỉ do nhóm có quyền quản lý |

### 14.3. Những lựa chọn cần cân nhắc

- Nếu nhiều service projects dùng chung **Shared VPC**, có thể dùng private zone liên kết trực tiếp host network và giảm số DNS peering zones.
- Nếu chỉ muốn công bố **một dịch vụ** cho ứng dụng khác, cân nhắc **Private Service Connect** và DNS endpoint tương ứng thay vì chia sẻ cả subnet.
- Nếu có nhiều trung tâm dữ liệu, cần đánh giá nơi nào là DNS authoritative, cách đồng bộ bản ghi, chiến lược failover và khả năng gây vòng lặp conditional forwarding.
- Nếu application dùng GKE hoặc Cloud Run, xác minh DNS resolver/ngữ cảnh networking thực tế của từng sản phẩm; không mặc định mọi container dùng cùng nameserver hay cùng đường ra như VM.

## 15. Bài tập thực hành

### Bài tập A — Chọn đúng cơ chế

Cho các yêu cầu:

1. VM ở Google Cloud muốn phân giải **ldap.corp.example.com.** do DNS on-prem quản lý.
2. VM trong spoke muốn dùng cùng resolver của hub để tra cứu tên của doanh nghiệp.
3. Máy chủ tại văn phòng muốn phân giải **db.gcp.example.com.** trong một Cloud DNS private zone.
4. Nhóm hạ tầng muốn ép mọi truy vấn DNS của VPC qua resolver kiểm duyệt của doanh nghiệp.
5. Hai VPC đã có VPC Network Peering, nhưng DNS của VPC B không tự phân giải được internal VM names của VPC A.

**Định hướng:** (1) forwarding zone; (2) DNS peering zone; (3) inbound DNS server policy và on-prem conditional forwarding; (4) outbound server policy nếu hiểu rõ tác động; (5) thêm DNS peering hoặc mô hình zone visibility phù hợp, vì VPC Network Peering không tự chia sẻ DNS.

### Bài tập B — Tìm nguyên nhân SERVFAIL

Trong hub, VM gọi **dig @169.254.169.254 billing.corp.example.com.** nhận **SERVFAIL**, nhưng **dig @172.16.100.10 billing.corp.example.com.** lại trả A record.

Hãy trình bày tối thiểu năm điều cần kiểm tra. Gợi ý: zone suffix, target config, source **35.199.192.0/19**, UDP/TCP 53, route trả về cùng VPC, IP nguồn của packet phản hồi, DNS target availability và log.

### Bài tập C — Giới hạn truyền tuyến DNS

Có ba VPC A, B, C. A tạo DNS peering zone trỏ tới B; B có DNS peering zone trỏ tới C.

1. Trường hợp này có thể hoạt động theo Cloud DNS hay không?
2. Nếu thêm D sau C, có thể tiếp tục peering A→B→C→D không?
3. Kết quả DNS trả IP của VM trong C có nghĩa A tự kết nối được tới VM đó không?
4. Vì sao DNS peering zone đặt trong A trỏ tới forwarding zone của B có thể đúng, còn forwarding zone đặt trong A dùng đường VPN qua B có thể sai?

**Định hướng:** (1) Có thể, DNS peering hỗ trợ tối đa một hop trung gian; (2) Không vượt giới hạn; (3) Không, IP route và firewall riêng; (4) Cloud DNS forwarding không hỗ trợ transitive IP routing đến target, DNS peering chuyển quyền phân giải đến producer có kết nối hybrid trực tiếp.

### Bài tập D — Viết runbook vận hành

Hãy soạn runbook một trang cho lỗi **ERP name resolution down** gồm: điểm phát hiện, truy vấn kiểm tra từ hub/spoke, lệnh xem forwarding và peering zone, log DNS on-prem, kiểm tra VPN/Cloud Router, dải nguồn **35.199.192.0/19**, người quyết định thay DNS policy và cách rollback. Phân loại trường hợp **DNS hỏng** với **DNS đúng nhưng API ERP không kết nối được**.

## 16. Ghi nhớ và tài liệu tham khảo

**Sáu ý cốt lõi:**

1. **Forwarding zone** chuyển các truy vấn khớp một DNS suffix đến DNS target; **private zone** giữ bản ghi; **peering zone** cho VPC consumer tra cứu theo DNS producer.
2. **Inbound forwarding** cho hệ thống on-prem hỏi Cloud DNS qua regional entry points; **outbound server policy** thay đổi rộng đường đi truy vấn của VPC và cần cân nhắc kỹ.
3. **DNS peering khác VPC Network Peering**: không cần peering IP để hỏi DNS; Cloud DNS peering hỗ trợ tối đa một hop trung gian, còn VPC Network Peering không cho phép IP routing bắc cầu.
4. Với private forwarding targets, Cloud DNS dùng nguồn **35.199.192.0/19** theo đường forwarding thông thường; DNS on-prem phải cho phép **UDP/TCP 53** và có **route trả về đúng VPC**.
5. **DNS đúng không đồng nghĩa kết nối ứng dụng thành công**. Kiểm tra route, firewall, TLS/IAM và listener sau khi biết IP đã đúng.
6. Lựa chọn DNS ảnh hưởng đến **bảo mật, độ tin cậy, cache, quan sát và chi phí**; cần kiểm thử từ cả hub, spoke và on-prem.

**Tài liệu Google Cloud chính thức:**

1. [Cloud DNS overview](https://docs.cloud.google.com/dns/docs/overview) — private DNS, forwarding và hybrid architecture.
2. [DNS zones overview](https://docs.cloud.google.com/dns/docs/zones/zones-overview) — forwarding zones, peering zones, transit limitations và cache.
3. [Create a forwarding zone](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones) — cú pháp gcloud, target types, source 35.199.192.0/19 và return routes.
4. [Create a peering zone](https://docs.cloud.google.com/dns/docs/zones/peering-zones) — producer/consumer, gcloud và roles/dns.peer.
5. [DNS server policies](https://docs.cloud.google.com/dns/docs/server-policies-overview) — inbound/outbound, DNS forwarding entry points và resolution order.
6. [Configure DNS server policies](https://docs.cloud.google.com/dns/docs/policies) — tạo inbound forwarding policy và lấy địa chỉ DNS_RESOLVER.
7. [Cloud DNS best practices](https://docs.cloud.google.com/dns/docs/best-practices) — thiết kế hybrid DNS, firewall, BGP advertisement và HA.
8. [Troubleshoot Cloud DNS](https://docs.cloud.google.com/dns/docs/troubleshooting) — kiểm tra SERVFAIL, ACL, forward targets và return routes.
