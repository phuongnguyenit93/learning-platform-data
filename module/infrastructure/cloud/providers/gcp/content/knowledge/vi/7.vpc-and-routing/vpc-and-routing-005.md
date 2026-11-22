# Routes, thứ tự chọn tuyến và đường đi gói tin

> **Chương:** VPC và định tuyến  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một ứng dụng trên Google Cloud có thể chạy ở Compute Engine, GKE hoặc Cloud Run và cần kết nối đến VM khác, cơ sở dữ liệu, mạng on-premises hoặc Internet. Khi kết nối thất bại, câu hỏi đầu tiên thường là: **gói tin được gửi theo đường nào, next hop nào được chọn, và tại sao?**

Trong **CLOUD_PROVIDERS_GCP**, người học khám phá từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành, độ tin cậy và chi phí. Bài học **“Routes, thứ tự chọn tuyến và đường đi gói tin”** cung cấp cách tư duy để đọc bảng định tuyến Google Cloud VPC, giải thích lựa chọn đường đi, phát hiện cấu hình gây gián đoạn và kiểm tra trước khi triển khai. Nội dung đặt trong chương **VPC và định tuyến**; các tình huống tập trung vào data plane của VPC và kết nối đến mạng khác.

Sau bài học, bạn có thể:

1. Đọc được một route dựa trên destination prefix, next hop, priority, loại tuyến và phạm vi áp dụng.
2. Phân biệt subnet, static, dynamic, policy-based và các đường đi đặc biệt.
3. Áp dụng đúng thứ tự chọn tuyến Google Cloud thay vì chỉ nhớ “số priority thấp nhất thắng”.
4. Diễn giải đường đi VM → VM, VM → on-premises, VM → Internet và lưu lượng qua thiết bị kiểm tra.
5. Dùng Effective routes, Google Cloud CLI, Cloud Router và Connectivity Tests để điều tra.
6. Giải thích vì sao có route vẫn có thể không kết nối được: firewall, NAT, địa chỉ, vùng, next hop hoặc chiều phản hồi.

## 1. Hiểu đúng cơ chế định tuyến trong VPC

**Route** mô tả **đích đến** và **next hop** mà mạng sử dụng để chuyển tiếp gói tin. Với route kiểu truyền thống, destination được biểu diễn bằng prefix CIDR, chẳng hạn `10.20.0.0/16` hoặc `0.0.0.0/0`.

~~~text
Gói tin rời VM:
    source IP      = 10.10.1.10
    destination IP = 172.16.10.50
    protocol       = TCP
    destination port = 443

Tuyến ứng viên:
    destination = 172.16.10.0/24
    next hop    = Cloud VPN tunnel / VLAN attachment / VM gateway ...
    priority    = một giá trị số nếu loại route có thuộc tính này
~~~

Khác với thiết bị router vật lý do bạn quản lý, VPC Google Cloud sử dụng **cơ chế định tuyến ảo phân tán**. Không có một chiếc router riêng được gán cho toàn VPC. Các VM được áp dụng những tuyến phù hợp qua hạ tầng mạng Google; sự thay đổi tuyến được phân phối theo mô hình **eventual consistency**, nên có thể cần thời gian để có hiệu lực đồng nhất.

Một VPC là tài nguyên **global**, còn subnet là **regional**. Các subnet thuộc nhiều region có thể nằm trong một VPC. Việc gửi lưu lượng đến subnet khác vẫn phụ thuộc route, địa chỉ IP và quy tắc firewall; không mặc định đồng nghĩa mọi cổng đều được phép truy cập.

### 1.1. Những trường cơ bản khi đọc route

| Thuộc tính | Ý nghĩa | Ví dụ hoặc lưu ý |
| --- | --- | --- |
| **Destination** | Dải địa chỉ đích của tuyến | `172.16.10.0/24` |
| **Next hop** | Đích trung gian/hạ tầng nhận gói tiếp theo | Internet gateway, VM next hop, Cloud VPN, Interconnect, internal passthrough Network Load Balancer |
| **Priority** | Thứ tự ưu tiên của một số loại tuyến khi đến bước so sánh priority | `100` ưu tiên hơn `900`; thang số `0–65535` cho static route |
| **Route type** | Loại tuyến quyết định vị trí trong quy trình chọn tuyến | Subnet, local static, local dynamic, peering, NCC, policy-based |
| **Scope/applicability** | Tài nguyên nào trong VPC được dùng tuyến | Static route có thể áp dụng toàn VPC hoặc chỉ VM có network tag |
| **Region** | Phạm vi tác động của một số dynamic route/next hop | Dynamic routing mode có thể là regional hoặc global |
| **Network/VPC** | Bảng tuyến thuộc VPC nào | Không lấy route của VPC không kết nối làm căn cứ |

**Tuyến áp dụng (applicable route)** là tuyến có hiệu lực với **nguồn gửi cụ thể**; nó là một tập con của các tuyến tồn tại trong VPC. Hai VM trong cùng VPC có thể nhận tập applicable routes khác nhau do network tag, region, hoặc chính sách định tuyến.

### 1.2. CIDR và “đích cụ thể hơn”

`10.20.5.0/24` bao gồm `10.20.5.0–10.20.5.255`; `10.20.0.0/16` bao gồm phạm vi rộng hơn. Nếu gói đến `10.20.5.10`, cả hai prefix đều khớp nhưng `/24` **cụ thể hơn** `/16`.

| Prefix | Số bit mạng | Mức độ cụ thể |
| --- | ---: | --- |
| `0.0.0.0/0` | 0 | Rộng nhất trong IPv4 |
| `10.0.0.0/8` | 8 | Rất rộng |
| `10.20.0.0/16` | 16 | Nhỏ hơn /8 |
| `10.20.5.0/24` | 24 | Cụ thể hơn /16 |
| `10.20.5.10/32` | 32 | Một địa chỉ IPv4 |

Đây là cơ sở của *longest prefix match* (LPM). Tuy nhiên, **không áp LPM trước mọi loại tuyến**. Trong Google Cloud, special routing paths, policy-based routes và subnet routes được xét trước nhóm custom static/dynamic routes.

## 2. Các loại tuyến và đường đi trong Google Cloud

| Loại | Được tạo/điều khiển bởi | Ý nghĩa điển hình |
| --- | --- | --- |
| **Special routing path** | Nền tảng Google Cloud, không thể xóa từ route table | Đường đi cho một số load balancer, health checks, IAP, Cloud DNS... |
| **Policy-based route (PBR)** | Quản trị mạng | Chọn đường qua internal passthrough Network Load Balancer theo nguồn, đích, protocol |
| **Local subnet route** | Tạo tự động theo subnet local | Đưa gói đến IP trong subnet VPC |
| **Peering subnet route** | Nhập từ VPC peered | Đưa gói đến subnet được quảng bá từ VPC ngang hàng |
| **NCC subnet route** | Nhập từ Network Connectivity Center (NCC) VPC spoke | Đưa gói đến subnet có kết nối qua NCC |
| **Local static route** | Tạo thủ công hoặc theo cơ chế dịch vụ | Đưa gói đến next hop định trước, ví dụ VM appliance, Classic VPN, Internet gateway |
| **Local dynamic route** | Cloud Router học/điều khiển qua BGP | Đưa gói đến prefix on-premises qua HA VPN, Interconnect hoặc router appliance |
| **Peering custom route** | Nhập từ VPC peered khi bật trao đổi tương ứng | Đường đến các đích custom của mạng peer |
| **NCC dynamic route** | Nhập từ NCC hybrid spoke | Đường đến prefix học động qua hub |
| **System-generated default route** | Google Cloud tạo khi tạo VPC theo điều kiện hỗ trợ | `0.0.0.0/0` hoặc `::/0` với next hop `default-internet-gateway` |
| **Private Service Connect endpoint route** | Tạo bằng forwarding rule của endpoint, trong trường hợp được hỗ trợ | Đường tới endpoint cho Google APIs ở thứ tự riêng |

### 2.1. Subnet route

Khi subnet có primary IPv4 range, secondary range hoặc IPv6 range được hỗ trợ, Google Cloud tạo route subnet tương ứng. Ví dụ:

~~~text
VPC: app-net
├── subnet-a (asia-southeast1) : 10.10.1.0/24
└── subnet-b (asia-southeast2) : 10.10.2.0/24

VM-A: 10.10.1.10
VM-B: 10.10.2.20
~~~

Gói từ VM-A đến VM-B phù hợp với local subnet route `10.10.2.0/24`. Khi là subnet route **thông thường**, tuyến này được chọn ở bước subnet, trước static/dynamic custom routes. Nếu địa chỉ đích nằm trong dải subnet nhưng **không gắn với tài nguyên hợp lệ** hoặc VM đích đã dừng, gói có thể bị loại; hệ thống không tự chuyển sang default route để tìm một IP đó trên Internet.

Google Cloud **không cho tạo** static route có destination trùng hoặc nằm **bên trong** một local/peering/NCC subnet route thông thường. Ví dụ subnet `10.10.2.0/24` tồn tại thì không thể thêm static route `10.10.2.128/25` nhằm “đè” nửa subnet. Có ngoại lệ liên quan **hybrid subnet routing** cần đọc tài liệu riêng.

### 2.2. Static route

Static route định nghĩa một destination và next hop cố định. Các dạng next hop thường gặp:

- `default-internet-gateway` cho đường đến external IPv4/IPv6 theo điều kiện hỗ trợ.
- VM next hop được chỉ định bằng tên/zone hoặc địa chỉ IP được hỗ trợ, thường phục vụ thiết bị router/firewall ảo.
- **Internal passthrough Network Load Balancer** làm next hop của một cụm gateway appliance.
- **Classic VPN tunnel** trong trường hợp dùng static hoặc policy-based VPN.

Static route có thể mang **network tag**. Tuyến có tag chỉ áp dụng cho **VM có network tag tương ứng**, không áp cho mọi dạng nguồn (chẳng hạn Cloud VPN tunnel hoặc Interconnect VLAN attachment). Static route có tag không được trao đổi qua VPC Network Peering.

Giá trị `priority` nhỏ hơn có mức ưu tiên cao hơn **khi quy trình chọn tuyến đã đến bước so sánh priority**. Mức priority cao **không tự thắng** prefix cụ thể hơn hoặc loại route được Google Cloud xét trước.

### 2.3. Dynamic route và Cloud Router

Cloud Router là thành phần **control plane** trao đổi route qua BGP hoặc sử dụng custom learned routes. Cloud Router **không tự mình chuyển tiếp mọi gói dữ liệu** giống một VM router. Đường truyền gói thực tế có thể sử dụng next hop Cloud VPN tunnel, Interconnect VLAN attachment hoặc router appliance.

Ví dụ: hạ tầng doanh nghiệp quảng bá `172.16.0.0/16` qua BGP đến Cloud Router gắn với HA VPN. Khi phiên BGP và điều kiện quảng bá phù hợp, VPC có thể học dynamic route cho prefix này. Nếu BGP bị ngắt, route có thể bị thu hồi.

**Dynamic routing mode** ảnh hưởng phạm vi region nhận dynamic route:

- **Regional:** local dynamic route có phạm vi theo region chứa Cloud Router/next hop.
- **Global:** các local dynamic route phù hợp có thể được dùng trên nhiều region của VPC theo điều kiện loại route, next hop và cơ chế mạng.

Với VPC Network Peering, phạm vi dynamic route được xuất còn phụ thuộc **routing mode của VPC xuất route**, không chỉ VPC nhập. IPv6 và một số cấu hình hybrid có giới hạn riêng; cần kiểm tra tài liệu thay vì suy từ trường hợp IPv4.

### 2.4. Policy-based routing (PBR)

Policy-based route có thể khớp **source IP**, **destination IP** và **IP protocol**, thay vì chỉ dựa destination prefix. Mục đích thường gặp là **chuyển một nhóm lưu lượng qua firewall appliance** đặt sau internal passthrough Network Load Balancer.

Một số tính chất quan trọng:

- PBR được xét **sau special routing paths nhưng trước subnet và custom routes**.
- PBR so sánh **priority**, **không dùng LPM** để tự chọn tuyến có source/destination prefix cụ thể nhất.
- PBR có thể áp dụng cho toàn mạng, VM có tag hoặc VLAN attachment theo điều kiện; PBR không được trao đổi qua VPC Peering.
- Next hop PBR thường là **internal passthrough Network Load Balancer** hợp lệ; một dạng rule đặc biệt cho phép **skip các PBR khác** và trở lại định tuyến mặc định.
- Nếu nhiều PBR cùng priority cùng khớp, Google Cloud có thể chọn bằng thuật toán nội bộ không dựa trên prefix cụ thể hơn. Nên dùng priority **khác nhau** cho các rule có khả năng cùng khớp.
- PBR không hỗ trợ lọc theo **TCP/UDP port** trực tiếp, nên không viết ví dụ PBR “chỉ port 443” như thể đó là điều kiện được hỗ trợ.

PBR là công cụ mạnh nhưng cần kiểm thử chiều đi và chiều về, tính sẵn sàng của firewall backend, IP forwarding và ảnh hưởng tới luồng GKE control plane, Private Service Connect và các luồng đặc biệt.

### 2.5. Default route và kết nối Internet

Khi tạo VPC, Google Cloud thường tạo local static default route `0.0.0.0/0` với next hop `default-internet-gateway`. Với các subnet có external IPv6 range, có thể có `::/0` tương ứng.

**Có default route không đồng nghĩa VM chắc chắn ra Internet được.** Với IPv4, cần xem:

1. Gói có đi theo default Internet gateway hay bị một route cụ thể hơn/PBR chuyển sang next hop khác?
2. VM có external IPv4, hoặc subnet/VM có **Public Cloud NAT** hoạt động cho lưu lượng phù hợp?
3. Egress firewall/policy có cho phép kết nối?
4. DNS, địa chỉ đích, cấu hình guest OS và dịch vụ phía ngoài có hoạt động?
5. Với Google APIs, cơ chế **Private Google Access** hoặc Private Service Connect có thể tạo cách kết nối khác với truy cập Internet công khai.

**Cloud NAT là dịch vụ dịch địa chỉ, không phải một loại next hop tùy chọn trong static route**. Public Cloud NAT thông thường sử dụng đường `default-internet-gateway` của VPC; nếu tuyến đến đích được chuyển sang VPN/gateway tùy chỉnh thì không thể tự suy rằng NAT sẽ áp dụng.

## 3. Thứ tự chọn tuyến thực tế của Google Cloud

Trong một VPC có nhiều route cùng có thể khớp gói tin. Google Cloud sử dụng **quy trình theo thứ tự**, thay vì sắp toàn bộ route chỉ theo một trường priority.

### 3.1. Sơ đồ quyết định tổng quát

~~~mermaid
flowchart TD
    START["Gói tin rời nguồn trong VPC"] --> S{"Special routing path khớp?"}
    S -- "Có" --> SPECIAL["Dùng special path"]
    S -- "Không" --> P{"PBR hợp lệ khớp?"}
    P -- "Có, next hop ILB" --> ILB["Chuyển đến internal passthrough NLB"]
    P -- "Có, skip PBR" --> SUB
    P -- "Không" --> SUB{"Subnet route khớp?"}
    SUB -- "Có, thông thường" --> SR["Dùng subnet route"]
    SUB -- "Không" --> PSC{"PSC endpoint cho global Google APIs khớp?"}
    PSC -- "Có" --> PS["Dùng forwarding-rule route"]
    PSC -- "Không" --> LPM["Lọc static/dynamic theo prefix cụ thể nhất"]
    LPM --> TYPE["Chọn loại custom route được ưu tiên"]
    TYPE --> NEXT["Loại next hop không dùng được"]
    NEXT --> PRI["Chọn priority số thấp nhất"]
    PRI --> PREF["Xử lý loại next hop và ECMP"]
    PREF --> END["Gửi đến next hop hoặc drop"]
~~~

Sơ đồ đã **rút gọn** các bước lựa chọn peering/NCC và trường hợp **hybrid subnet**, được phân tích tiếp. Nó nhằm giúp nhìn luồng tổng quan; muốn xử lý các trường hợp phức tạp hãy đối chiếu [Routes: Routing order](https://docs.cloud.google.com/vpc/docs/routes#routing_order).

### 3.2. Mười hai bước trong tài liệu định tuyến

| Bước | Tên trong tài liệu Google Cloud | Ý nghĩa |
| ---: | --- | --- |
| 1 | **Special routing paths** | Kiểm tra những đường đi đặc biệt, thường không hiển thị trong bảng route thông thường. Nếu khớp thì dừng. |
| 2 | **Policy-based routes** | Xét PBR dựa trên thuộc tính gói và **priority**. Rule skip PBR cho phép quay lại nhánh thông thường. |
| 3 | **Subnet routes** | Kiểm tra local/peering/NCC subnet routes; với subnet thông thường, nếu khớp thì dùng tuyến này. |
| 4 | **PSC endpoints for global Google APIs** | Kiểm tra forwarding rule của endpoint Private Service Connect phù hợp. |
| 5 | **Most specific destination** | Trong **static/dynamic** còn lại, giữ prefix đích cụ thể nhất (LPM). |
| 6 | **Most favorable custom route type** | Với cùng prefix, ưu tiên **local custom** trước **NCC dynamic**, rồi đến **peering custom**. |
| 7 | **Peering custom routes from one VPC** | Nếu có nhiều peer cung cấp cùng đích, chọn next hops từ một VPC peer theo thuật toán nội bộ. |
| 8 | **Disregard unusable next hops** | Bỏ static/dynamic route với next hop không hợp lệ hoặc không dùng được theo tiêu chí Google Cloud. |
| 9 | **Disregard low-priority routes** | Giữ route có **priority số thấp nhất** trong tập còn lại. |
| 10 | **NCC dynamic routes from one routing VPC** | Nếu cần, chọn next hops NCC từ một routing VPC network. |
| 11 | **Most favorable preference category** | Với cùng prefix/priority, ưu tiên loại next hop theo thứ bậc của Google Cloud. |
| 12 | **Send or drop packet** | Một route thì gửi; nhiều route đủ điều kiện thì có thể ECMP; không còn route thì drop. |

**Vì sao thứ tự này quan trọng?** Một static route `priority=100` có thể **thua** dynamic route `priority=900` nếu dynamic route có prefix cụ thể hơn và cả hai đều ở nhánh static/dynamic phù hợp. Ngược lại, một **subnet route thông thường** khớp đích sẽ được xét trước cả hai route đó. Một PBR khớp có thể đưa gói qua next hop riêng ngay cả khi đích nằm trong một subnet.

### 3.3. Lưu ý về subnet “hybrid”

Phần lớn subnet sử dụng logic subnet route thông thường: đích khớp dải subnet thì đi theo subnet route, hoặc bị drop nếu IP không tồn tại/VM ngừng. Với **hybrid subnet routing** được cấu hình chủ động, khi IP không gắn với VM đang chạy hay internal forwarding rule, Google Cloud có thể xét tiếp một quy trình khác để tìm đường đến đích qua route phù hợp.

**Không dùng hybrid subnet làm lý do tổng quát** để nói rằng gói đến IP trống trong subnet mặc định sẽ tự fallback sang VPN. Trường hợp này là ngoại lệ có điều kiện, có giới hạn phạm vi và next hop riêng trong tài liệu chính thức.

### 3.4. So sánh prefix và priority đúng thứ tự

Tưởng tượng một VM ở `10.10.1.10` gửi đến `172.16.10.25`; không có PBR, subnet hoặc special path nào khớp đích.

| Tuyến | Destination | Priority | Next hop | Kết quả |
| --- | --- | ---: | --- | --- |
| Route A | `0.0.0.0/0` | 10 | Internet gateway | Bị loại ở bước 5 vì rộng |
| Route B | `172.16.0.0/16` | 100 | VPN A | Bị loại ở bước 5 vì rộng |
| Route C | `172.16.10.0/24` | 900 | VPN B | **Được giữ** vì `/24` cụ thể nhất |

**Kết luận:** `/24` thắng `/16` và `/0` trong nhánh custom route dù số priority là 900. Chỉ khi các route đủ điều kiện có **cùng destination prefix** mới tới các bước phân loại và chọn priority.

### 3.5. Cùng prefix: còn phải xem nguồn route và next hop

Giả sử nhiều route cùng destination `172.16.10.0/24`:

- Có **local dynamic route** và **peering custom route** cho cùng prefix: bước chọn loại custom route có thể chọn local route **trước khi** so priority với peer.
- Có hai **local** route cùng prefix và cùng nhóm được so sánh: route có priority số thấp hơn thường được giữ sau khi loại next hop không dùng được.
- Nếu còn nhiều route cùng prefix, cùng priority và loại next hop phù hợp, Google Cloud có thể thực hiện **ECMP**.
- Nếu các next hop thuộc những **preference category** khác nhau ở bước 11, **không ECMP giữa các category**.

Các preference category ở bước 11 theo thứ tự:

1. Static route có next hop VM hoặc Classic VPN tunnel.
2. Dynamic route thuộc một loại.
3. Static route tới internal passthrough Network Load Balancer.
4. Static route tới `default-internet-gateway`.

Bước này xảy ra **sau** khi lọc prefix, loại custom route, next hop không hợp lệ và priority. Không dùng danh sách preference category để phủ định thứ tự các bước trước đó.

### 3.6. Next hop hỏng có làm rơi về tuyến rộng hơn không?

**Không phải lúc nào cũng có fallback.** Ví dụ:

~~~text
Đích: 192.168.50.10

Route X: 192.168.50.0/24 → next hop VM đang dừng
Route Y: 192.168.0.0/16  → next hop VM đang chạy
~~~

Route X được chọn ở bước LPM và Route Y bị loại vì prefix rộng hơn. Nếu next hop của X bị xem là không dùng được ở bước sau, gói có thể **bị drop**, chứ không tự quay lại Route Y.

Tuy nhiên, nếu **hai route có cùng destination prefix**, route có next hop không dùng được có thể bị loại **trước** bước so priority, cho phép một route khác cùng prefix với next hop hợp lệ được dùng. Điều này lý giải vì sao phải kiểm tra cả **prefix** lẫn **trạng thái next hop** khi thiết kế dự phòng.

## 4. Gói tin đi như thế nào trong các tình huống phổ biến?

### 4.1. VM đến VM trong cùng subnet

~~~text
VM-A: 10.10.1.10
VM-B: 10.10.1.20
Subnet: 10.10.1.0/24
~~~

1. VM-A gửi gói đến `10.10.1.20`; guest OS quyết định chuyển qua network interface thích hợp.
2. Hạ tầng VPC áp dụng đường đi mạng, thông thường bằng local subnet route.
3. Google Cloud kiểm tra firewall/policy tương ứng với luồng.
4. Nếu VM-B đang hoạt động, có IP hợp lệ, firewall cho phép và dịch vụ lắng nghe, gói được giao.
5. Chiều phản hồi đi qua quy tắc định tuyến và trạng thái kết nối phù hợp; firewall stateful có thể cho phép gói trả lời đối với một kết nối đã được chấp nhận.

**Không có bước “đi lên router vật lý mặc định”** mà người dùng tự cấu hình cho từng subnet Google Cloud.

### 4.2. VM giữa hai subnet/region của cùng VPC

~~~mermaid
flowchart LR
  A["VM-A · 10.10.1.10 · asia-southeast1"] --> R["Google Cloud distributed VPC routing"]
  R --> B["VM-B · 10.10.2.20 · asia-southeast2"]
  R -. "Chính sách mạng" .- FW["Firewall / Hierarchical firewall policies"]
~~~

Nếu subnet `10.10.2.0/24` thuộc VPC, một local subnet route thông thường đưa gói đến vùng thích hợp. Việc lưu lượng đi được còn phụ thuộc firewall, IP ở hai đầu và dịch vụ đích; di chuyển qua region cũng có thể phát sinh chi phí truyền dữ liệu liên vùng. Không cần tự tạo static route chỉ để cho hai subnet cùng VPC kết nối.

### 4.3. VM đi on-premises qua HA VPN/Interconnect

~~~mermaid
flowchart LR
  VM["VM trong VPC · 10.10.1.10"] --> VR["VPC route selection"]
  VR --> TUN["HA VPN tunnel / Interconnect VLAN attachment"]
  TUN --> ON["Router on-premises"]
  ON --> APP["Server · 172.16.10.25"]
  CR["Cloud Router · BGP control plane"] -. "Học/quảng bá prefix" .-> VR
  CR -. "BGP" .-> ON
~~~

Giả sử on-premises quảng bá `172.16.0.0/16` và Cloud Router học được dynamic route thông qua BGP. Khi VM gửi đến `172.16.10.25`, không có subnet/PBR hoặc special path phù hợp, dynamic route có thể được chọn và hướng gói qua next hop VPN/Interconnect.

Những điểm phải kiểm tra:

- BGP peer đang hoạt động và VPC **đã học** prefix cần thiết?
- Dynamic route áp dụng được trong region của VM nguồn?
- Có route cụ thể hơn đưa gói sang next hop khác?
- Mạng on-premises có **return route** về `10.10.1.0/24`?
- Firewall hai phía cho phép traffic và có NAT/ACL làm đổi địa chỉ không?
- Tunnels/Interconnect thực sự chuyển tiếp được gói, không chỉ hiển thị trạng thái control plane?

Kết nối **hai chiều** cần đường về hợp lệ. Trạng thái BGP “Established” là một tín hiệu, nhưng chưa đủ chứng minh ứng dụng TCP sẽ kết nối được.

### 4.4. VM không có public IP đi Internet

~~~text
VM: 10.10.1.10 (chỉ có internal IPv4)
       |
       | 0.0.0.0/0 → default-internet-gateway
       v
VPC / Cloud NAT (Public NAT đã cấu hình cho nguồn hợp lệ)
       |
       v
Internet public endpoint
~~~

Các điều kiện thường có: default IPv4 route với next hop Internet gateway, cấu hình Public Cloud NAT đúng nguồn, firewall egress và dịch vụ đích sẵn sàng. Cloud NAT **dịch địa chỉ**, không phải next hop trong route table.

Nếu thay default route bằng một static route qua VM appliance hoặc VPN, lưu lượng đi theo next hop tương ứng; Public Cloud NAT không tự động áp dụng cho mọi đường đi khác.

### 4.5. Chèn firewall appliance bằng PBR

~~~mermaid
flowchart LR
  APP["VM ứng dụng"] --> PBR["Policy-based route khớp IP/protocol"]
  PBR --> ILB["Internal passthrough Network Load Balancer"]
  ILB --> FWA["Firewall VM / network appliance"]
  FWA --> DEST["Đích phù hợp"]
~~~

PBR có thể hướng một nhóm lưu lượng qua firewall VM để kiểm tra. Vì PBR được xét trước subnet routes, cấu hình sai có thể làm gián đoạn cả kết nối nội bộ. Cần kiểm tra backend firewall có **IP forwarding**, đường return path, network tags, rule ưu tiên hơn để skip PBR với những nguồn hoặc đích cần ngoại lệ, và tính sẵn sàng của internal passthrough load balancer.

**Ví dụ lý luận:** PBR priority 100 khớp nguồn `10.10.1.0/24`, đích `0.0.0.0/0` sẽ được xét trước subnet route đến `10.10.2.0/24`, trừ khi có special path hoặc PBR skip khác có ưu tiên cao hơn. Không nên mặc định “đích nội bộ luôn tránh firewall appliance”.

### 4.6. Kết nối VPC Peering và NCC

Khi hai VPC peered, Google Cloud có thể nhập **peering subnet routes** và một số **custom routes** nếu bật import/export phù hợp. Nhưng **VPC Network Peering không hỗ trợ transit routing giữa hai peer chỉ thông qua peer trung gian**. Kết nối A↔B và B↔C **không** đồng nghĩa A↔C có đường truyền trực tiếp.

Với **Network Connectivity Center**, các VPC spoke và hybrid spoke có quy tắc trao đổi subnet/dynamic routes phụ thuộc topology, export filters và các điều kiện tương ứng. Không suy cách chọn NCC route chỉ dựa số priority khi chưa kiểm tra bước ưu tiên **local custom → NCC dynamic → peering custom**.

## 5. Đọc routing table và kiểm tra tuyến có hiệu lực

### 5.1. Google Cloud Console: Effective routes

Để đánh giá đường đi, nên mở **VPC network → Routes → Effective routes** trong Google Cloud Console:

1. Chọn đúng **VPC network**.
2. Chọn **region** liên quan đến nguồn gửi (đặc biệt khi có dynamic routes).
3. Xem route types, destination, next hop và trạng thái áp dụng.
4. Bật hiển thị **suppressed routes** nếu cần hiểu vì sao một route bị loại.
5. Xác minh network tag/PBR scope, đường truyền đến on-prem và khả năng kết nối hai chiều.

**Quan trọng:** Mục **Route management** hiển thị các cấu hình tuyến có thể quản trị, còn **Effective routes** hỗ trợ thấy các tuyến có hiệu lực theo phạm vi. Cần kiểm tra nguồn VM/region cụ thể, không kết luận chỉ từ một danh sách route không có ngữ cảnh.

### 5.2. Lệnh Google Cloud CLI chỉ đọc

Các lệnh sau tra cứu tài nguyên đã có. Thay `PROJECT_ID`, `NETWORK_NAME`, `ROUTER_NAME` và `REGION` bằng giá trị thật của hệ thống:

~~~bash
# Kiểm tra project đang cấu hình
gcloud config get-value project

# Liệt kê VPC
gcloud compute networks list --project=PROJECT_ID

# Liệt kê subnet
gcloud compute networks subnets list --project=PROJECT_ID

# Liệt kê subnet routes và static routes
gcloud compute routes list --project=PROJECT_ID

# Xem một static route theo tên đã có
gcloud compute routes describe ROUTE_NAME --project=PROJECT_ID

# Xem BGP và trạng thái Cloud Router liên quan (nếu có)
gcloud compute routers get-status ROUTER_NAME \
  --region=REGION \
  --project=PROJECT_ID

# Liệt kê Connectivity Tests đã được tạo
gcloud network-management connectivity-tests list \
  --project=PROJECT_ID
~~~

**Giới hạn của `gcloud compute routes list`:** Theo tài liệu hiện tại, lệnh nhóm `gcloud compute routes` hiển thị **subnet routes và static routes**, **không hiển thị đầy đủ** policy-based, dynamic và peering routes. Khi cần phân tích toàn bộ lựa chọn đường đi, dùng **Effective routes** trong Console, kết hợp trạng thái Cloud Router/BGP và dữ liệu liên quan. Đừng kết luận “không có dynamic route” chỉ vì không thấy nó trong `gcloud compute routes list`.

Việc liệt kê Connectivity Tests yêu cầu API và quyền liên quan đã được cấu hình. Những lệnh ở đây không tạo/sửa tài nguyên. Truy vấn trạng thái không thay thế phép thử kết nối thực tế.

### 5.3. Ví dụ hình dung cấu hình static route

Giả sử bạn có một appliance gateway được phê duyệt trong VPC và muốn gửi lưu lượng đến dải mạng lab `192.168.50.0/24` qua next hop VM. Cú pháp ví dụ sau **có tác động tạo route**; chỉ sử dụng trong lab được cấp quyền và sau khi kiểm tra CIDR, VPC, next hop và đường phản hồi:

~~~bash
gcloud compute routes create lab-to-remote \
  --network=LAB_NETWORK \
  --destination-range=192.168.50.0/24 \
  --next-hop-instance=LAB_GATEWAY_VM \
  --next-hop-instance-zone=LAB_GATEWAY_ZONE \
  --priority=800 \
  --project=LAB_PROJECT_ID
~~~

Sau khi xác minh xong, nếu route này được tạo riêng cho bài lab và không còn cần thiết, có thể xóa có kiểm soát:

~~~bash
gcloud compute routes delete lab-to-remote \
  --project=LAB_PROJECT_ID
~~~

**Không sao chép các lệnh tạo/xóa vào project production.** Route có thể thay đổi đường đi của nhiều VM và gây mất kết nối. Trước khi áp dụng cần rà soát tác động và có phương án rollback.

### 5.4. Guest OS route khác với VPC route

Trên VM Linux, `ip route` có thể hiển thị default gateway và các route của hệ điều hành. Danh sách này **không phải toàn bộ** route table của VPC. VPC fabric quyết định next hop sau khi gói đi từ VM vào hệ thống mạng Google. Cần kết hợp thông tin guest OS, network interface, VPC Effective routes và firewall để hiểu đường đi đầy đủ.

## 6. Chẩn đoán khi kết nối không hoạt động

**Không thể ping** hoặc timeout một cổng dịch vụ không chứng minh route đã sai. Sự cố có thể ở DNS, nguồn/đích, firewall, guest OS, route, NAT, chính sách tổ chức hoặc return path.

### 6.1. Checklist theo từng tầng

| Tầng | Câu hỏi | Công cụ phù hợp |
| --- | --- | --- |
| **Địa chỉ nguồn/đích** | IP đúng chưa? Nguồn ở VPC/region/network interface nào? | Compute Engine interface details, DNS records |
| **Route áp dụng** | Route nào khớp? Có special path/PBR/subnet/PSC không? | Effective routes, Google Cloud Routes docs |
| **Prefix và priority** | Có đích cụ thể hơn? Loại custom route ưu tiên hơn? Next hop có hợp lệ? | Effective routes, route detail |
| **Dynamic control plane** | BGP session hoạt động? Prefix có được học/quảng bá và áp dụng đúng region? | Cloud Router status, BGP routes |
| **Next hop data plane** | Tunnel, appliance VM, ILB hoạt động và thực sự forward? | VPN/Interconnect monitoring, appliance logs |
| **Firewall/policy** | Quy tắc ingress và egress cho phép đúng IP/protocol/port? | Firewall rules, firewall policy, Firewall Rules Logging |
| **NAT/Internet** | Có external IP hoặc Public NAT? Đường default gateway còn phù hợp? | Cloud NAT status/logs, route |
| **Chiều trả lời** | Đích có route về nguồn không? Có asymmetric path hoặc NAT thay địa chỉ? | Effective routes hai phía, route on-prem |
| **Ứng dụng** | Service có lắng nghe port, TLS/DNS đúng, timeout phù hợp? | VM logs, application logs, metrics |

### 6.2. Connectivity Tests

[Network Intelligence Center – Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) cho phép mô phỏng luồng kết nối từ **nguồn đến đích** và phân tích cấu hình mạng như route, firewall, VPN, load balancer. Một số trường hợp còn hỗ trợ **live data plane analysis** và chỉ số packet loss/latency.

Cách dùng trong Console:

1. Chọn **Network Intelligence Center → Connectivity Tests**.
2. Tạo test với nguồn cụ thể (ví dụ VM-A), IP hoặc resource đích, protocol và port.
3. Đọc **trace** để xác định chặng nào bị chặn, loại route được sử dụng và điều kiện firewall.
4. Đối chiếu cấu hình ngay sau khi vừa sửa với thông tin thực tế; công cụ có độ trễ cập nhật trạng thái cấu hình.
5. Nếu analysis báo reachable nhưng ứng dụng vẫn lỗi, kiểm tra guest OS, service listener, DNS, TLS và các phụ thuộc.

**Lưu ý:** Tạo Connectivity Test là thao tác tạo tài nguyên chẩn đoán; cần quyền và có thể có chi phí/điều kiện API. Các test đã tạo có thể được liệt kê theo lệnh đọc ở mục 5.2.

### 6.3. VPC Flow Logs và Firewall Rules Logging

- **VPC Flow Logs** cho phép quan sát mẫu/metadata của những luồng trên subnet hoặc các tài nguyên được hỗ trợ, tùy cấu hình. Đây không phải full packet capture và có thể có sampling/aggregation.
- **Firewall Rules Logging** cho biết những kết nối phù hợp với các quy tắc được bật logging, hỗ trợ xác định rule allow/deny.
- **Cloud Router logs/metrics** cho biết tình trạng phiên BGP và tuyến học/quảng bá; điều này khác với việc xác thực một TCP session end-to-end.

Một gói không xuất hiện trong một loại log chưa đủ để kết luận nó không hề đi qua mạng. Cần hiểu phạm vi thu thập, sampling, quyền và thời gian ghi log.

## 7. Những lỗi suy luận rất thường gặp

1. **“Priority 100 luôn thắng priority 900.”** Sai khi so hai prefix khác nhau hoặc loại route khác bậc. Xét *routing order* trước.
2. **“Route 0.0.0.0/0 có thể ghi đè subnet.”** Subnet route thông thường được chọn trước custom routes.
3. **“Có route nghĩa là TCP kết nối được.”** Còn firewall, NAT, quyền, thiết bị đích, cổng và return path.
4. **“Cloud Router là router đang nhận và phát mọi gói.”** Cloud Router quản lý BGP/route; data plane đi qua next hop tương ứng.
5. **“Có route default thì VM private ra Internet được.”** Còn cần NAT hoặc đường truy cập phù hợp, firewall và chính sách.
6. **“PBR dùng longest prefix match giống static route.”** PBR xét priority và tiêu chí khớp; cùng priority khớp có thể chọn theo thuật toán nội bộ.
7. **“Static route có network tag áp dụng cho mọi nguồn cùng VPC.”** Route có tag chỉ áp dụng cho VM có tag phù hợp.
8. **“Hai VPC peered qua một VPC trung gian thì tự có transit.”** VPC Network Peering không phải kết nối bắc cầu tùy ý.
9. **“BGP up nghĩa là kết nối ứng dụng thành công.”** Cần route ứng dụng, tunnel, firewall, đích và chiều về hợp lệ.
10. **“Next hop hỏng sẽ quay lại route /0.”** Route cụ thể hơn đã loại route rộng ở bước trước; có thể drop thay vì fallback.
11. **“Đổi route có hiệu lực tức thì ở mọi VM.”** Google Cloud phân phối cập nhật theo eventual consistency.
12. **“gcloud compute routes list hiển thị đầy đủ mọi loại route.”** Cần Console Effective routes để nhìn các loại không hiện trong lệnh đó.
13. **“Cùng prefix và priority thì luôn ECMP mọi next hop.”** Google Cloud còn áp dụng bước chọn loại custom route, next hop network và preference category.
14. **“GKE hoặc Cloud Run tự dùng toàn bộ route VPC giống VM.”** Đường lưu lượng phụ thuộc chế độ mạng, cấu hình VPC egress/connectivity, địa chỉ Pod/alias range và loại dịch vụ; cần xem tài liệu của workload.

## 8. Bài tập phân tích bảng tuyến (không cần tạo hạ tầng)

**Giả định chung:** Một VM có IP nguồn `10.10.1.10` trong VPC `lab-net`, region `asia-southeast1`. Không có đường đi đặc biệt, không có PBR, trừ khi tình huống nói khác. Các đích remote không nằm trong subnet của VPC.

### Tình huống A — Prefix cụ thể hơn

| Route | Destination | Priority | Next hop |
| --- | --- | ---: | --- |
| A1 | `0.0.0.0/0` | 100 | default internet gateway |
| A2 | `172.16.0.0/16` | 200 | Cloud VPN-A |
| A3 | `172.16.20.0/24` | 800 | Cloud VPN-B |

**Câu hỏi:** Gói đến `172.16.20.15` đi theo next hop nào? Còn gói đến `172.16.30.15`?

**Gợi ý:** Gói tới `172.16.20.15` chọn A3 do `/24` cụ thể hơn. Gói đến `172.16.30.15` không thuộc `/24` nên chọn A2. Giá trị priority không thay đổi kết quả LPM trong ví dụ này.

### Tình huống B — Subnet có IP chưa được cấp

| Thành phần | Giá trị |
| --- | --- |
| Local subnet | `10.10.2.0/24` |
| Gói đích | `10.10.2.199` |
| IP đích | Chưa gắn cho VM hay forwarding rule |
| Default route | `0.0.0.0/0` đến internet gateway |

**Câu hỏi:** Gói có fallback ra Internet không?

**Gợi ý:** Với subnet route thông thường, không. Subnet route khớp và được chọn; vì không có resource đích phù hợp, gói bị drop. Tình huống hybrid subnet được cấu hình rõ ràng là ngoại lệ khác.

### Tình huống C — Cùng prefix, next hop dừng

| Route | Destination | Priority | Next hop |
| --- | --- | ---: | --- |
| C1 | `192.168.50.0/24` | 100 | Gateway VM đã dừng |
| C2 | `192.168.50.0/24` | 300 | Gateway VM hoạt động |
| C3 | `192.168.0.0/16` | 10 | Gateway VM hoạt động |

**Câu hỏi:** Đường nào có thể được chọn với `192.168.50.5`?

**Gợi ý:** C3 bị loại khi LPM. Nếu C1 bị loại ở bước xem xét next hop không dùng được, C2 cùng prefix có thể được chọn dù priority 300. Trạng thái guest OS của next hop vẫn cần xác minh: VM chạy không bảo đảm ứng dụng router/firewall đang forward được.

### Tình huống D — PBR can thiệp vào subnet

PBR khớp nguồn `10.10.1.0/24` và đích `0.0.0.0/0`, priority 100, next hop internal passthrough NLB. Có subnet route `10.10.2.0/24`. Gói đến `10.10.2.20` có nhất thiết đi thẳng theo subnet không?

**Gợi ý:** Không. Nếu PBR phù hợp và không có special path hoặc PBR skip có ưu tiên hơn, nó được xét trước subnet route và có thể đưa gói qua NLB/appliance. Thiết kế cần kiểm tra đường đi và firewall appliance để tránh blackhole.

### Tình huống E — VPN và Internet

VM không có external IPv4. VPC có default route `0.0.0.0/0` đến internet gateway và dynamic route `172.16.0.0/16` qua HA VPN. Chưa cấu hình Cloud NAT.

**Câu hỏi:** Gói đến `172.16.1.10` và `8.8.8.8` có hành vi giống nhau không?

**Gợi ý:** Không. Đích `172.16.1.10` phù hợp dynamic route cụ thể hơn, đi VPN nếu đường và firewall hợp lệ. Đích `8.8.8.8` phù hợp default gateway; VM chỉ có internal IPv4 và không có Public NAT/đường công khai phù hợp thường không thể dùng đường đó để truy cập Internet thông thường. Cũng phải xét chính sách egress.

## 9. Tình huống thiết kế: tách môi trường ứng dụng và mạng doanh nghiệp

**Bối cảnh:** Nhóm ứng dụng chạy API trên Cloud Run, xử lý công việc trên GKE, một hệ thống Java cũ trên Compute Engine và cần truy cập cơ sở dữ liệu on-premises qua HA VPN. VPC có hai subnet theo vùng, một đường Internet egress và các route động qua Cloud Router. Nhóm bảo mật yêu cầu một số luồng đi qua firewall appliance, còn nhóm vận hành muốn giám sát sự cố và chi phí.

Một bản thiết kế cần chỉ rõ:

- **Địa chỉ và ranh giới:** các subnet CIDR không chồng lấn và phân biệt mạng production/development.
- **Đường on-premises:** Cloud Router học dải nào, BGP peer có vùng nào và routing mode là regional/global.
- **Policy-based routes:** những nguồn/đích/protocol nào đi qua appliance, priority của PBR skip nếu cần, ILB có hoạt động đa vùng hay không.
- **Cloud Run egress:** cấu hình kết nối vào VPC phù hợp và phạm vi lưu lượng đưa qua VPC.
- **GKE:** cách Pod/Node dùng IP ranges, khả năng xung đột PBR và phạm vi áp dụng routes.
- **Return path:** phía on-premises đã có route đến VPC ranges, qua cùng đường hoặc đường được cho phép.
- **Firewall:** các rule dựa source/destination/port, network tags hoặc service account, cùng chính sách cấp tổ chức.
- **Observability:** trạng thái Cloud Router, VPN, Connectivity Tests và log phù hợp.
- **Chi phí:** egress Internet, dữ liệu liên vùng, VPN/Interconnect và xử lý tại appliance (nếu có).

**Ví dụ một hồ sơ quyết định kiến trúc ngắn:**

~~~text
Vấn đề: VM/GKE cần truy cập DB on-prem 172.16.20.10:5432.
Nguồn: subnet app 10.10.1.0/24, subnet worker 10.10.2.0/24.
Đường dự kiến: dynamic route 172.16.0.0/16 qua HA VPN.
Lý do: Cloud Router nhận quảng bá BGP và kiểm soát kết nối hybrid.
Bảo mật: giới hạn TCP/5432, service account và firewall hai phía.
Giả định: route áp dụng đúng region; on-prem có return route.
Kiểm chứng: Effective routes, Cloud Router status, Connectivity Tests.
Rủi ro: BGP down, sai prefix cụ thể hơn, asymmetric route, appliance down.
Phục hồi: theo dõi tunnel và quy trình failover/rollback đã thử nghiệm.
Tối ưu: kiểm tra băng thông, độ trễ và chi phí truyền dữ liệu.
~~~

Mỗi quyết định nên gắn **bằng chứng** chứ không chỉ một sơ đồ mũi tên. Routes là một phần của thiết kế mạng; độ tin cậy cần thêm kiểm thử và khả năng quan sát.

## 10. Câu hỏi ôn tập và đáp án định hướng

1. **Priority 50 có luôn thắng priority 200?** Không; còn special/PBR/subnet/PSC, LPM và loại custom route trước khi so priority.
2. **Khi nào Google Cloud tạo subnet route?** Khi subnet/dải địa chỉ của subnet được tạo hoặc thay đổi theo vòng đời hỗ trợ; không phải tự tạo một static route thủ công cho mỗi subnet.
3. **Cloud Router có forward packet như VM router không?** Không. Cloud Router tham gia trao đổi và quản lý BGP/dynamic routes; data plane dùng next hop tương ứng.
4. **Một IP nằm trong subnet nhưng chưa có VM có bị gửi ra default route không?** Không với subnet route thông thường.
5. **Vì sao PBR không dùng LPM như custom routes?** PBR có tập tiêu chí và thứ tự ưu tiên riêng trước subnet/custom routes.
6. **Có default route nghĩa là VM không public IP truy cập Internet được?** Không; còn cần cơ chế NAT hoặc đường truy cập hỗ trợ, firewall và các điều kiện mạng.
7. **Tại sao BGP Established mà TCP vẫn timeout?** Có thể thiếu route thực, firewall, đường về, dịch vụ đích hoặc next hop data plane.
8. **Static route gắn network tag có áp dụng cho Cloud VPN tunnel không?** Không, tag chỉ giới hạn VM có tag phù hợp.
9. **VPC Peering A–B, B–C tạo transit A–C không?** Không có transit Peering tự động.
10. **Khi hai route cùng prefix và priority, có luôn load balance ECMP?** Không; còn bước lọc next hop/loại route/preference category và các điều kiện ECMP.
11. **Tại sao phải nhìn Effective routes theo region?** Vì dynamic routes và một số next hop có phạm vi vùng.
12. **Vì sao một next hop VM đang chạy vẫn có thể làm gói bị drop?** Guest OS có thể chưa bật IP forwarding, appliance không xử lý hoặc firewall/route chiều về sai; trạng thái VM không chứng minh luồng thành công.

## 11. Checklist kiểm tra trước khi chỉnh route production

- [ ] Đã xác nhận đúng project/VPC/region và nguồn gửi gói.
- [ ] Biết IP nguồn, IP đích, protocol, cổng và hướng đi/về.
- [ ] Đã tìm special path, PBR và subnet route trước khi tính custom route.
- [ ] Đã áp LPM, loại custom route, next hop và priority theo đúng thứ tự.
- [ ] Đã kiểm tra network tag và phạm vi regional/global của dynamic route.
- [ ] Đã xác minh BGP/tunnel/Interconnect và tình trạng next hop thực tế.
- [ ] Đã kiểm tra firewall ingress/egress, NAT và return path.
- [ ] Đã kiểm tra route nguồn/đích với Console Effective routes.
- [ ] Đã dùng Connectivity Tests hoặc thử nghiệm phù hợp cho luồng quan trọng.
- [ ] Đã có phương án rollback và cửa sổ thay đổi phù hợp.
- [ ] Đã đánh giá độ tin cậy, chi phí mạng và quyền IAM của thao tác.

## 12. Tài liệu tham khảo chính thức

Google Cloud có thể cập nhật quy tắc route mới, đặc biệt ở Network Connectivity Center, hybrid subnet và Policy-based routes. Khi xử lý production, ưu tiên trang tài liệu chính thức và phần **Routing order** hiện hành.

- [Routes overview & routing order](https://docs.cloud.google.com/vpc/docs/routes) — loại tuyến, phạm vi áp dụng và 12 bước chọn tuyến.
- [Static routes](https://docs.cloud.google.com/vpc/docs/static-routes) — next hop, priority, tags, quy tắc xung đột.
- [Use routes & Effective routes](https://docs.cloud.google.com/vpc/docs/using-routes) — cách xem cấu hình và tuyến có hiệu lực.
- [Policy-based routes](https://docs.cloud.google.com/vpc/docs/policy-based-routes) — nguồn/đích/protocol, priority, next hop và ngoại lệ.
- [Use policy-based routes](https://docs.cloud.google.com/vpc/docs/use-policy-based-routes) — thao tác cấu hình, liệt kê và yêu cầu IAM/API.
- [Cloud Router overview](https://docs.cloud.google.com/network-connectivity/docs/router/concepts/overview) — BGP control plane, regional/global mode và learned routes.
- [VPC Network Peering](https://docs.cloud.google.com/vpc/docs/vpc-peering) — trao đổi subnet/custom routes, giới hạn transit.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — mô phỏng đường đi và chẩn đoán.
- [Create and run Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests) — hướng dẫn thực hành, điều kiện API/IAM.
- [Cloud NAT overview](https://docs.cloud.google.com/nat/docs/overview) — NAT và lưu lượng Internet của tài nguyên private.
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) — quan sát metadata lưu lượng.
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls) — kiểm soát truy cập tách biệt với route.

**Điều cần ghi nhớ:** Google Cloud định tuyến bằng **một thứ tự chọn đường cụ thể**, trong đó special paths, PBR và subnet routes xuất hiện trước các bước so prefix/priority của custom routes. Học đúng thứ tự, kiểm tra **next hop và chiều phản hồi**, rồi xác minh qua Effective routes/Connectivity Tests sẽ giúp giải thích hành vi gói tin và vận hành VPC an toàn hơn.
