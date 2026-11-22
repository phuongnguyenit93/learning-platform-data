# Địa chỉ IPv4, IPv6, IP nội bộ và IP bên ngoài trên Google Cloud

> **Chương:** VPC và định tuyến  
> **Bài học:** Địa chỉ IPv4, IPv6, IP nội bộ và IP bên ngoài  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ cách tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; qua đó biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Hiểu **địa chỉ IP** là tiền đề để xây dựng những hệ thống ấy: VM cần liên lạc với database qua đường riêng, API cần phục vụ người dùng internet, còn job chạy nền có thể chỉ cần tải bản vá và gọi Google APIs.

Một địa chỉ IP trả lời câu hỏi **đích/nguồn mạng là gì**. Loại IP, subnet, route, firewall, IAM và cấu hình dịch vụ phối hợp quyết định **gói tin có đi đến nơi, yêu cầu có được chấp nhận không**. Bài này phân biệt bốn khái niệm dễ trộn lẫn: **IPv4**, **IPv6**, **IP nội bộ (internal)** và **IP bên ngoài (external)**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận biết cú pháp IPv4/IPv6, tiền tố CIDR, dải IPv4 riêng theo RFC 1918 và IPv6 dùng nội bộ.
2. Giải thích VPC là tài nguyên toàn cục, subnet thuộc region và IP được gán cho giao diện mạng VM như thế nào.
3. Phân biệt **internal/external**, **private/public**, **ephemeral/static** và **regional/global**.
4. Mô tả IPv4-only, dual-stack, IPv6-only và cách Google Cloud phân bổ IPv6 cho subnet/VM.
5. Chọn phương án kết nối: external IP, load balancer, **Public NAT**, **Private Google Access** và kết nối dịch vụ riêng.
6. Đọc cấu hình IP, route, firewall qua Console/`gcloud` và điều tra nguyên nhân không kết nối được.
7. Thiết kế sơ đồ IP cho Compute Engine, GKE, Cloud Run, Cloud SQL với bảo mật, khả năng mở rộng và chi phí hợp lý.

## 2. Các trục phân loại không đồng nghĩa với nhau

| Trục | Giá trị | Câu hỏi |
|---|---|---|
| **Phiên bản giao thức** | IPv4 / IPv6 | Địa chỉ thuộc họ giao thức nào? |
| **Phạm vi sử dụng** | Internal / External | Địa chỉ phục vụ kết nối nội bộ hay có thể định tuyến công khai? |
| **Vòng đời địa chỉ** | Ephemeral / Static | IP được cấp tạm theo tài nguyên hay được giữ trước bằng reservation? |
| **Phạm vi tài nguyên** | Regional / Global | IP gắn với vùng hay loại tài nguyên toàn cầu nào? |

Một VM có thể có **internal IPv4 ephemeral** và **external IPv4 static regional**. Load balancer có thể có **global external IP**. VM dual-stack có thể có internal IPv4 và external IPv6. Nhìn thấy địa chỉ `10.x.x.x` không đủ để biết địa chỉ ấy có cố định hay không.

**Ghi nhớ:** IP bên ngoài của Google Cloud là địa chỉ công khai có thể định tuyến trên internet, nhưng **có IP ngoài không đồng nghĩa cổng đã mở**. Firewall, listener, route, TLS và xác thực vẫn có thể chặn truy cập. Ngược lại, VM không có external IPv4 vẫn có thể đi ra internet IPv4 qua Public NAT.

## 3. IPv4, CIDR và quy hoạch dải địa chỉ

### 3.1. Cấu trúc địa chỉ IPv4

IPv4 sử dụng địa chỉ **32 bit**, viết thành bốn số thập phân trong khoảng 0–255, ví dụ `10.24.0.10`. CIDR ghép địa chỉ mạng với **độ dài prefix**, ví dụ:

- `10.24.0.0/24`: 24 bit đầu xác định tiền tố mạng, còn 8 bit cho các giá trị địa chỉ.
- `10.24.0.0/20`: dải lớn hơn, có 4.096 giá trị địa chỉ.
- `10.24.0.10/32`: biểu diễn một địa chỉ IPv4 đơn lẻ trong firewall/routing.

Ví dụ, **primary IPv4 range** `10.24.0.0/24` trên Google Cloud:

| Thành phần | Giá trị |
|---|---|
| CIDR | `10.24.0.0/24` |
| Tổng giá trị IPv4 | `2^(32-24) = 256` |
| Địa chỉ mạng | `10.24.0.0` |
| Gateway ảo | `10.24.0.1` |
| Hai địa chỉ cuối dành riêng | `10.24.0.254` và `10.24.0.255` |
| Khoảng có thể cấp trong primary range | `10.24.0.2` đến `10.24.0.253` |
| Số địa chỉ khả dụng | **252** |

Google Cloud dành riêng **bốn địa chỉ** của **primary IPv4 range**: hai địa chỉ đầu và hai địa chỉ cuối. Quy tắc này **không áp dụng như vậy** cho **secondary IPv4 range**: theo tài liệu VPC, mọi địa chỉ trong secondary range đều có thể sử dụng theo cơ chế của dịch vụ.

| Primary CIDR | Tổng địa chỉ | Khả dụng sau dự trữ bốn địa chỉ |
|---|---:|---:|
| `/28` | 16 | 12 |
| `/26` | 64 | 60 |
| `/24` | 256 | 252 |
| `/20` | 4.096 | 4.092 |

Không nên thiết kế dải chỉ vừa khít số VM hiện tại: autoscaling, các lớp node/pod GKE, VM mới và địa chỉ dự trữ có thể làm cạn subnet.

### 3.2. Private IPv4 và các dải đặc biệt

Ba dải IPv4 **riêng** theo RFC 1918:

| Dải | Phạm vi |
|---|---|
| `10.0.0.0/8` | Không gian lớn cho doanh nghiệp |
| `172.16.0.0/12` | Từ `172.16.0.0` đến `172.31.255.255` |
| `192.168.0.0/16` | Thường gặp ở mạng nhỏ, văn phòng, lab |

Một số loại đặc biệt:

- `127.0.0.0/8`: loopback, điển hình `127.0.0.1`.
- `169.254.0.0/16`: link-local, không phải dải subnet để tùy ý cấp cho workload.
- `198.51.100.0/24`, `203.0.113.0/24`, `192.0.2.0/24`: dải **dành cho tài liệu minh họa**, không sử dụng làm IP internet thật.

Trong Google Cloud có trường hợp **privately used public IPv4**: một số dải công khai hợp lệ có thể được cấu hình làm **internal IPv4** trong VPC theo quy tắc dịch vụ. Vì vậy, từ **internal** không luôn đồng nghĩa tuyệt đối với “thuộc ba dải RFC 1918”.

### 3.3. Địa chỉ trùng lặp và CIDR chồng lấn

Hai subnet trong cùng VPC không được có các dải địa chỉ chồng lấn trái quy tắc. Khi kết nối qua **Cloud VPN**, **Cloud Interconnect**, **VPC Network Peering** hoặc private services access, cần kiểm tra cả mạng đối tác/on-premises.

~~~text
VPC retail-vpc (global)
├── subnet-app-sg       asia-southeast1  10.24.0.0/24
├── subnet-batch-sg     asia-southeast1  10.24.1.0/24
└── subnet-app-tokyo    asia-northeast1  10.25.0.0/24
~~~

Ba subnet trên không chồng lấn. Nếu mạng văn phòng đã dùng `10.24.0.0/16`, cần giải quyết xung đột trước khi kết nối hybrid; route không tự giải quyết mọi trường hợp địa chỉ trùng.

## 4. VPC, subnet và network interface

### 4.1. VPC global, subnet regional

Trong Google Cloud:

- **VPC network** là tài nguyên **global**; route và firewall được quản lý trong phạm vi VPC và policy có liên quan.
- **Subnet** là tài nguyên **regional**, có dải primary IPv4 và, theo cấu hình, secondary IPv4/IPv6.
- **Compute Engine VM** chạy trong một **zone**; mỗi network interface kết nối với một subnet thích hợp trong cùng region.
- **Giao diện mạng** của một VM có thể có primary internal IPv4, external IPv4 tùy chọn và cấu hình IPv6 khi subnet/interface hỗ trợ.

~~~mermaid
flowchart TB
    V["VPC retail-vpc (global)"]
    V --> S1["Subnet app-sg<br/>10.24.0.0/24, Singapore"]
    V --> S2["Subnet batch-sg<br/>10.24.1.0/24, Singapore"]
    V --> S3["Subnet app-tokyo<br/>10.25.0.0/24, Tokyo"]
    S1 --> A["VM app-1: 10.24.0.10"]
    S2 --> B["VM batch-1: 10.24.1.20"]
    S3 --> C["VM app-2: 10.25.0.10"]
~~~

VM trong cùng VPC có thể liên lạc qua IP nội bộ giữa các subnet/region khi route hợp lệ, nhưng **firewall ingress và egress** vẫn phải cho phép lưu lượng. “Cùng VPC” không đồng nghĩa mọi cổng mặc định mở.

### 4.2. Primary và secondary IPv4 ranges

Một subnet IPv4 có **primary range** để cấp primary internal IPv4 cho VM. **Secondary ranges** có thể phục vụ alias IP và các dịch vụ như **GKE VPC-native**.

| Thành phần | Vai trò thường gặp |
|---|---|
| Primary IPv4 range | Địa chỉ chính của VM/node |
| Secondary IPv4 range | Alias IP, phạm vi Pod/Service trong các mô hình GKE hỗ trợ |
| Alias IP | Một hay nhiều địa chỉ/dải IPv4 bổ sung được gắn với interface VM |

GKE có nhiều chế độ network và cơ chế cấp dải; cần kiểm tra loại cluster, phiên bản và số Pod/node dự kiến trước khi quy hoạch. Không tự suy rằng mọi cluster có cùng cách dùng secondary ranges.

### 4.3. Auto mode hay custom mode?

**Auto mode VPC** tự tạo subnet IPv4 cho region theo các dải mặc định của Google Cloud; tiện khám phá nhưng khó chủ động trong kiến trúc hybrid. **Custom mode VPC** cho phép chọn subnet/region/CIDR theo kế hoạch và phù hợp hơn khi cần kiểm soát IPv6, môi trường nhiều project hoặc peering.

Các subnet có IPv6 được hỗ trợ trong **custom mode VPC**. Với mạng auto mode đã tồn tại, cần chuyển sang custom mode theo quy trình hỗ trợ nếu muốn thêm subnet IPv6.

## 5. IP nội bộ và bên ngoài trên Compute Engine

### 5.1. Internal IPv4

Với interface IPv4-only hoặc dual-stack, VM có **một primary internal IPv4** từ primary subnet range. Hai cách cấp thông dụng:

- **Ephemeral internal IPv4**: được Compute Engine cấp tự động hoặc chỉ định phù hợp khi tạo VM; không phải một reservation tách biệt để giữ lâu dài.
- **Static internal IPv4**: được reserve theo scope thích hợp để giữ một địa chỉ cố định; có thể gán cho tài nguyên tương thích.

Static IP chỉ giải quyết việc giữ **định danh địa chỉ**, không bảo đảm VM luôn chạy. Nếu yêu cầu HA hoặc failover, cần thiết kế load balancing, instance group, dịch vụ managed và cơ chế khôi phục tương ứng.

### 5.2. External IPv4

External IPv4 là địa chỉ công khai có thể dùng để giao tiếp internet. Compute Engine thông thường ánh xạ external IPv4 qua **NAT một-một** đến primary internal IPv4 của interface; do đó IP public không nhất thiết xuất hiện như địa chỉ cấu hình trong hệ điều hành VM.

- **Ephemeral external IPv4** có thể thay đổi khi giải phóng, thay đổi cấu hình hoặc vòng đời VM.
- **Static external IPv4** là địa chỉ được reserve, phù hợp khi cần IP cố định cho DNS, quy tắc allowlist của đối tác hoặc frontend.
- External IPv4 gắn trực tiếp với VM thường là **regional**. Một số load balancer có frontend **global external IP** theo loại sản phẩm.
- External IPv4 có thể phát sinh **chi phí ngay cả khi đang được sử dụng**; địa chỉ giữ chỗ chưa dùng cũng có thể có phí. Cần kiểm tra bảng giá hiện hành.

### 5.3. IP bên ngoài không tự mở dịch vụ

Để truy cập VM từ internet ngoài external IP còn cần:

1. Route/khả năng định tuyến và **firewall ingress** cho phép nguồn, protocol, port.
2. Ứng dụng/OS **lắng nghe** trên địa chỉ/cổng phù hợp, không chỉ trên `127.0.0.1`.
3. DNS/TLS đúng nếu dùng tên miền và HTTPS.
4. Xác thực/ủy quyền ứng dụng, IAM cho thao tác quản trị, chính sách tổ chức hoặc kiểm soát mạng khác.

Nếu VM chỉ cần quản trị qua SSH, cân nhắc **IAP TCP forwarding** hoặc kết nối private được kiểm soát thay vì mặc định mở SSH rộng ra internet.

## 6. IPv6: địa chỉ 128 bit và các kiểu subnet

### 6.1. Cách viết IPv6

IPv6 sử dụng **128 bit**, viết thành các nhóm thập lục phân cách nhau bởi dấu hai chấm:

~~~text
2001:0db8:0001:0000:0000:0000:0000:0042
2001:db8:1::42
~~~

Hai biểu diễn trên chỉ cùng một địa chỉ. Dấu `::` rút gọn một chuỗi các nhóm 0, chỉ dùng một lần trong địa chỉ. Prefix `2001:db8::/32` dành cho **tài liệu**, không phải địa chỉ internet được cấp để chạy thử.

| Dải / loại | Ý nghĩa |
|---|---|
| `::1/128` | IPv6 loopback |
| `fe80::/10` | Link-local |
| `fc00::/7` | Unique Local Address (ULA), dùng cho nội bộ |
| `2001:db8::/32` | Documentation prefix |
| Global unicast được cấp hợp lệ | Có thể được định tuyến công khai theo route và firewall |

IPv6 còn kéo theo DNS `AAAA`, route mặc định `::/0`, khả năng OS/network stack và hỗ trợ riêng của từng dịch vụ. Không thể dùng route IPv4 để gửi gói IPv6.

### 6.2. Internal IPv6 và external IPv6

Trong một custom mode VPC:

- **Internal IPv6** của subnet dùng dải ULA do Google Cloud cấp theo cấu hình mạng. Nó phục vụ giao tiếp trong phạm vi được hỗ trợ và **không định tuyến trực tiếp trên internet**.
- **External IPv6** sử dụng dải công khai, có thể định tuyến ra internet và cũng có thể dùng để liên lạc giữa VM trong VPC; vẫn chịu firewall.
- **Dual-stack** cho phép interface có IPv4 và IPv6 cùng lúc.
- **IPv6-only** chỉ có IPv6 trên interface theo cấu hình được hỗ trợ; cần kiểm tra giới hạn hệ điều hành/image và khả năng tới dịch vụ IPv4-only.

### 6.3. Prefix /64 ở subnet và /96 trên VM

Với subnet hỗ trợ IPv6, Google Cloud cấp **dải IPv6 `/64`** theo access type **internal hoặc external**. Network interface VM gắn vào subnet phù hợp nhận **một dải `/96`**, loại internal **hoặc** external theo subnet. Địa chỉ IPv6 đầu tiên (`/128`) của dải `/96` thường được cấu hình trên interface.

~~~text
Custom-mode VPC
└── Subnet dual-stack
    ├── Primary internal IPv4: 10.24.0.0/24
    ├── IPv6 subnet: /64, INTERNAL hoặc EXTERNAL
    └── VM nic0:
        ├── Internal IPv4: 10.24.0.10
        ├── External IPv4: tùy chọn
        └── IPv6: một /96 tương ứng access type subnet
~~~

**Một interface không có đồng thời internal `/96` và external `/96` IPv6.** VM cần cả hai loại có thể phải dùng nhiều interface theo quy định sản phẩm. Muốn dùng internal IPv6, VPC phải được chuẩn bị dải internal IPv6 thích hợp trước khi cấu hình subnet.

### 6.4. IPv6 và NAT

External IPv6 cho phép kết nối tới đích IPv6 công khai theo route/firewall; không cần NAT44 để “có internet IPv6”. Nhưng nguồn **IPv6-only** không tự nói chuyện được với đích **IPv4-only**. Khi có yêu cầu này, kiểm tra cấu hình **DNS64/NAT64** được Google Cloud hỗ trợ cho loại workload tương ứng.

VPC có **implied deny ingress** cả với IPv6. Có bản ghi AAAA hoặc external IPv6 không làm cổng HTTPS/SSH tự mở. Phải cấu hình firewall cho **IPv6 source range**, port và target tương ứng; tránh vô tình mở `::/0` cho dịch vụ nội bộ.

## 7. Bảng phối hợp kiểu interface và IP

| Interface | Internal IPv4 | External IPv4 | IPv6 |
|---|---|---|---|
| **IPv4-only** | Bắt buộc | Tùy chọn | Không |
| **Dual-stack** | Bắt buộc | Tùy chọn | Một `/96` internal hoặc external |
| **IPv6-only** | Không | Không | Một `/96` internal hoặc external |

Bảng thể hiện **một network interface**. VM có nhiều interface có thể có nhiều đường kết nối và kiểu địa chỉ hơn; cần đối chiếu các giới hạn service khi thiết kế.

| Workload giả định | Ví dụ IP | Ý nghĩa |
|---|---|---|
| VM batch | `10.24.1.20` internal, không external IPv4 | Xử lý nền, outbound qua NAT khi cần |
| VM legacy | `10.24.0.12` internal và external IPv4 tùy nhu cầu | Có thể cần kết nối với đối tác |
| VM dual-stack | Internal IPv4 cộng một dải IPv6 external `/96` | Thử nghiệm giao tiếp IPv6 |
| Backend Cloud SQL | Private endpoint theo cấu hình dịch vụ | Không phải VM trực tiếp gắn vào primary range tùy ý |
| HTTPS load balancer | Public frontend IP theo loại LB | Điểm vào web công khai tập trung |

## 8. Định tuyến: IP có đường đi như thế nào?

### 8.1. Route khác firewall

**Route** quyết định hướng gói tin đi tới dải đích; trong VPC, routes đặc biệt quan trọng cho **egress**. Subnet routes cho phép tìm đường giữa các dải trong VPC; default route hoặc các route được học/cấu hình có thể hướng tới internet hay mạng hybrid.

**Firewall** quyết định lưu lượng được phép theo nguồn/đích, protocol/port, direction và target. VPC có quy tắc **ngầm định deny ingress, allow egress**, trừ khi policy/rule khác áp dụng và ưu tiên. Firewall là stateful đối với các kết nối được cho phép.

~~~mermaid
flowchart LR
    VM["VM 10.24.1.20<br/>không external IPv4"]
    VM --> E["Egress firewall + route"]
    E --> D{"Đích nào?"}
    D -->|Internal| P["VM/DB private hợp lệ"]
    D -->|Internet IPv4| NAT["Public NAT"]
    NAT --> NET["Internet IPv4"]
    D -->|Google APIs| PGA["Private Google Access<br/>hoặc endpoint riêng"]
    PGA --> API["Google Cloud APIs"]
~~~

Sơ đồ là tập hợp **các phương án phải cấu hình**, không hàm ý mọi đường đã có sẵn. Internal IPv6 và external IPv6 có quy tắc route riêng, không đi qua NAT44 theo mặc định.

### 8.2. Default route và subnet routes

| Destination CIDR | Ý nghĩa |
|---|---|
| `0.0.0.0/0` | Đường mặc định IPv4 |
| `::/0` | Đường mặc định IPv6 |
| `10.24.1.0/24` | Đường đến một subnet IPv4 cụ thể |
| Prefix IPv6 subnet | Đường đến các địa chỉ IPv6 thuộc phạm vi được cấu hình |

Google Cloud lựa chọn đường đi theo **loại route, tiền tố, scope và priority** của các route áp dụng. Không nên chỉ nhìn một default route rồi kết luận tất cả lưu lượng phải đi qua internet.

### 8.3. Ví dụ “cùng subnet nhưng không kết nối được”

VM A `10.24.0.10` gọi VM B `10.24.0.20:8080`. Nếu VM B không có ingress allow rule phù hợp hoặc ứng dụng chỉ lắng nghe `127.0.0.1:8080` thì kết nối vẫn lỗi. Thứ tự chẩn đoán nên là:

1. Địa chỉ/subnet/route và họ IPv4/IPv6 có đúng không?
2. Egress và ingress firewall có cho phép nguồn, target, protocol, port không?
3. OS firewall và tiến trình có lắng nghe trên IP/cổng phù hợp không?
4. DNS, TLS và xác thực ứng dụng có hoạt động không?

## 9. VM không có external IPv4 có thể truy cập bên ngoài ra sao?

### 9.1. Public NAT cho outbound IPv4

**Public NAT** (một loại Cloud NAT) giúp tài nguyên trong subnet được cấu hình, chẳng hạn VM không có external IPv4, **chủ động** kết nối tới đích IPv4 trên internet qua một hay nhiều external IPv4 dùng chung. Hồi đáp của kết nối đã thiết lập được chuyển về VM; Public NAT **không** cho phép kết nối inbound chưa được chủ động khởi tạo.

~~~text
VM batch: 10.24.1.20:53000
      → Public NAT (dịch source thành public IPv4 + port)
      → updates.example.org:443
      ← phản hồi của kết nối đã thiết lập
~~~

Cloud NAT là dịch vụ được quản lý, cấu hình gắn với **Cloud Router** trong vùng và phục vụ các subnet/range được chọn. Cloud Router điều khiển cấu hình, không phải VM proxy mà người học phải tạo rồi gửi toàn bộ gói tin xuyên qua. Cloud NAT có thể phục vụ nhiều loại workload được hỗ trợ; với Cloud Run hoặc GKE phải xem điều kiện kết nối VPC của từng dịch vụ.

Điều cần giám sát: **số cổng NAT khả dụng, lỗi cấp cổng, dropped packets, số lượng connection, IP NAT và chi phí egress**. Khi nhiều VM cùng mở rất nhiều kết nối tới một đích, hạn chế NAT ports có thể gây lỗi dù CPU và RAM vẫn bình thường.

### 9.2. Private Google Access cho Google APIs

**Private Google Access** cho phép VM không có external IP kết nối tới **các Google APIs/services được hỗ trợ** mà không cần gán public IP trực tiếp cho VM. Tính năng được bật theo **subnet**, kết hợp DNS, route, firewall và quyền IAM phù hợp.

Ví dụ, VM `10.24.1.20` cần đọc object từ Cloud Storage API. Các điều kiện cần kiểm tra:

1. Subnet được **bật Private Google Access** khi cần theo kiểu kết nối.
2. Google API endpoint/DNS và route được cấu hình đúng; có thể dùng domain mặc định hoặc private/restricted VIP theo yêu cầu.
3. VPC firewall egress và chính sách mạng cho phép lưu lượng.
4. API cần thiết đã bật nếu dịch vụ yêu cầu; service account có quyền đọc bucket/object.
5. Đích thực sự là loại Google API/service mà cơ chế Private Google Access hỗ trợ.

**Private Google Access không cấp IAM role và không là Public NAT cho mọi website.** VM có thể gọi một endpoint Google API thành công nhưng vẫn không thể tải file từ website internet không thuộc phạm vi PGA.

### 9.3. Private Service Connect và private services access

| Cơ chế | Nhu cầu điển hình | Điều không nên suy diễn |
|---|---|---|
| **Public NAT** | Mở kết nối **ra** internet IPv4 từ VM không có external IPv4 | Không mở cổng inbound công khai |
| **Private Google Access** | Gọi Google APIs từ VM không có external IP | Không phải Internet NAT chung |
| **Private Service Connect (PSC)** | Endpoint riêng để truy cập Google APIs hoặc dịch vụ đã publish theo sản phẩm | Không phải cứ có internal IP là dùng được mọi service |
| **Private services access** | Truy cập một số dịch vụ managed qua cơ chế kết nối riêng Service Networking/VPC peering | Không phải một VM service được gắn tùy ý vào subnet |
| **VPC Network Peering** | Kết nối hai VPC qua dải địa chỉ riêng theo khả năng được hỗ trợ | Không mặc định chuyển tiếp xuyên nhiều VPC peering |
| **Cloud VPN/Interconnect** | Kết nối VPC với on-premises hoặc cloud khác | Không tự xóa xung đột CIDR hay tự mở firewall |

Khi làm việc với **Cloud SQL**, chọn private endpoint/PSC/private services access theo chế độ và khả năng hiện hành của phiên bản dịch vụ. Không nên suy ra rằng việc tạo Cloud SQL “private IP” đơn giản là tự chọn một địa chỉ trong primary subnet VM rồi gán cho instance DB.

### 9.4. NAT64 và luồng IPv6-only

Trong các cấu hình Google Cloud có hỗ trợ, **DNS64/NAT64** giúp workload chỉ có IPv6 truy cập dịch vụ **IPv4-only**. Cần kiểm tra cả dịch vụ workload, DNS resolver, phương thức NAT, route và giới hạn sản phẩm.

External IPv6 công khai đã có đường đến internet IPv6 khi route/firewall phù hợp; **không cần NAT44** cho luồng IPv6-to-IPv6. Cũng không thể lấy một địa chỉ external IPv6 rồi mặc định dùng được tất cả API chỉ có IPv4.

## 10. Chọn IP theo dịch vụ trong mô-đun Google Cloud

| Workload | Mô hình IP/kết nối khởi đầu | Việc cần xác minh |
|---|---|---|
| **Compute Engine backend** | Chỉ internal IPv4; dùng NAT/PGA/PSC nếu cần | Nhu cầu outbound, OS, route, firewall, IAP hoặc private access |
| **VM web public** | Ưu tiên đánh giá HTTPS load balancer có public frontend, backend nội bộ | TLS, WAF, health checks, HA và DNS |
| **GKE VPC-native** | Primary range cho node; secondary ranges/alias IP cho Pod/Service theo mode | Cạn dải IP, CIDR overlap, egress NAT, network policy |
| **Cloud Run web API** | Endpoint HTTPS/ingress do Cloud Run cung cấp; LB nếu kiến trúc cần | Không coi service như VM có public IP cố định trên NIC |
| **Cloud Run kết nối private** | Direct VPC egress hoặc connector theo khả năng hỗ trợ | Service account, route, firewall, private DB endpoint |
| **Cloud SQL** | Private endpoint nếu không cần kết nối công khai | Private services access/PSC, database auth, network policy |
| **Cloud Storage** | Truy cập qua endpoint/API và IAM | PGA/PSC khi VM không có external IP, không nhầm với gán bucket vào subnet |
| **Giao diện load balancer** | External IPv4/IPv6 theo loại load balancer | Regional/global, tier, static reservation, backend health |

**Lưu ý về Cloud Run:** một service có URL HTTPS và cấu hình ingress/authentication riêng. Việc Cloud Run gọi IP nội bộ của VPC (egress) không có nghĩa client khác trong VPC có thể kết nối vào “internal IP của container” như VM. Cần dùng cơ chế ingress/endpoints được Cloud Run hỗ trợ.

## 11. Tình huống triển khai: hệ thống đơn hàng ở Singapore

Công ty bán lẻ có **Orders API trên Cloud Run**, **Cloud SQL PostgreSQL** chứa đơn hàng và một **VM legacy** xử lý batch. VM batch chỉ cần tải bản vá từ internet IPv4, đọc object từ Cloud Storage, không cần tiếp nhận kết nối công khai. Người mua truy cập API qua HTTPS từ IPv4 hoặc IPv6.

~~~mermaid
flowchart TB
    Client["Người mua internet IPv4/IPv6"]
    LB["HTTPS frontend/load balancer khi cần"]
    API["Cloud Run Orders API"]
    SQL[("Cloud SQL private endpoint")]
    VM["VM batch<br/>10.24.1.20, không external IPv4"]
    NAT["Public NAT - outbound IPv4"]
    NET["Internet - nguồn cập nhật phần mềm"]
    PGA["Private Google Access"]
    GAPI["Google APIs / Cloud Storage"]
    OBS["Cloud Logging + Monitoring"]
    Client --> LB
    LB --> API
    API -->|"Private connectivity được cấu hình"| SQL
    VM --> NAT
    NAT --> NET
    VM --> PGA
    PGA --> GAPI
    API -->|"API access + IAM"| GAPI
    API -. "Log/metric" .-> OBS
    VM -. "Log/metric" .-> OBS
~~~

Sơ đồ là **mô hình khái niệm**, không phải cấu hình triển khai trực tiếp. Cloud Run có thể cung cấp HTTPS endpoint không cần load balancer riêng; nếu dùng LB phải chọn sản phẩm và cách kết nối backend được hỗ trợ. Cloud SQL private endpoint cần cấu hình kết nối riêng cụ thể, không nhất thiết mang một IP thuộc primary subnet VM.

### 11.1. Phương án CIDR minh họa

| Thành phần | Giá trị giả định | Mục đích |
|---|---|---|
| VPC | `retail-prod-vpc`, custom mode | Ranh giới mạng toàn cục |
| Subnet app | `retail-app-sg`, `10.24.0.0/24`, `asia-southeast1` | Workload liên quan ứng dụng |
| Subnet batch | `retail-batch-sg`, `10.24.1.0/24`, `asia-southeast1` | VM nền không có public IPv4 |
| VM batch | Internal IPv4 `10.24.1.20` | Không tiếp nhận inbound từ internet |
| Public NAT | Region `asia-southeast1`, áp dụng subnet batch | Outbound IPv4 |
| Private Google Access | Bật trên subnet batch nếu cần | Gọi Google APIs |
| Public HTTPS frontend | External IP theo loại LB/Cloud Run | Người mua kết nối qua HTTPS |
| IPv6 | Chọn dual-stack/IPv6-only trên subnet khi cần | Đánh giá support và firewall trước khi mở |

Nếu mạng on-premises dự kiến kết nối đã dùng `10.24.0.0/16` thì không nên triển khai các dải ví dụ trên. Cần lập **IP address plan** cho toàn mạng liên quan trước.

### 11.2. Kiểm soát an toàn

- **API public, database private:** không đặt database dưới địa chỉ internet-routable nếu chỉ ứng dụng được truy cập.
- **Backend không cần external IP:** dùng NAT/PGA hoặc private endpoints; hạn chế ingress.
- **Firewall theo port và target:** chỉ cho phép HTTPS tại frontend và cổng DB từ workload hợp lệ.
- **Danh tính workload:** dùng service account Cloud Run/VM có quyền tối thiểu để truy cập Google APIs.
- **Bảo vệ DNS/TLS:** bản ghi `A` và `AAAA` phải trỏ tới endpoint hỗ trợ đúng họ địa chỉ; kiểm thử TLS thực tế.
- **Quy trình quản trị:** IAM hạn chế quyền sửa routes/firewalls/public IP; ghi log các thay đổi quan trọng.

### 11.3. Độ tin cậy và chi phí

Một thiết kế tốt cần xét cả **IP exhaustion** của subnet, số cổng NAT, khả năng failover, health checks, Cloud SQL connections và số request/traffic. Static IP giữ địa chỉ ổn định nhưng **không tự tạo HA**.

Chi phí có thể đến từ **external IPv4**, NAT gateway/traffic, load balancer, cross-region/egress, Cloud VPN/Interconnect và logs. Đội ngũ cần đặt **Cloud Billing budgets**, gắn label phù hợp và phân tích chi phí theo service/SKU. Budget alert cảnh báo chi tiêu, không mặc định dừng toàn bộ dịch vụ.

## 12. Thực hành chỉ đọc trên Console và Cloud Shell

**Mục đích:** người học phân loại IP của một project sandbox mà không tạo tài nguyên mới. Chỉ dùng project được cấp quyền, ghi lại `PROJECT_ID` thật, không chạy lệnh thay đổi khi chưa được phê duyệt.

### Bước 1. Quan sát Console

1. Mở [Google Cloud Console](https://console.cloud.google.com/) và chọn project sandbox.
2. Vào **VPC network → VPC networks**. Ghi VPC name, auto/custom mode, danh sách subnet.
3. Chọn subnet để xem **region**, primary/secondary IPv4 ranges, stack type, IPv6 access type và Private Google Access khi có.
4. Xem **Compute Engine → VM instances**: internal IPv4, external IPv4, IPv6, network interfaces và zone.
5. Xem **VPC network → Routes**, **Firewall** và khu vực **IP addresses** để phân biệt đường đi, chính sách và static addresses.
6. Nếu có Cloud NAT, xác nhận gateway phục vụ subnet/region nào. Trang có thể được sắp xếp ở vị trí khác theo phiên bản Console.

### Bước 2. Kiểm tra CLI và danh tính

~~~bash
# Các lệnh chỉ đọc.
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="yaml(projectId,name,projectNumber)"
~~~

`PROJECT_ID` là placeholder, không phải chuỗi để chạy nguyên xi. Nếu project mặc định của CLI khác project chọn trong Console, dùng cờ `--project=PROJECT_ID` cho truy vấn.

### Bước 3. Liệt kê mạng, subnet và IP

~~~bash
gcloud compute networks list --project=PROJECT_ID
gcloud compute networks subnets list --project=PROJECT_ID
gcloud compute networks subnets list --project=PROJECT_ID --format=json

gcloud compute instances list --project=PROJECT_ID --format=json
gcloud compute addresses list --project=PROJECT_ID
~~~

Khi đọc JSON VM, tìm `networkInterfaces`:

- `networkIP`: primary internal IPv4.
- `accessConfigs`/`natIP` khi hiện diện: external IPv4.
- Trường IPv6/address access type: phụ thuộc kiểu interface và phiên bản dịch vụ.
- `subnetwork`: đường dẫn đến subnet, giúp xác minh region.

**Không dùng `compute addresses list` để kết luận mọi VM ephemeral đều không có IP.** Danh sách address resource chủ yếu thể hiện IP đặt trước/quản lý như address reservation; thông tin network interface VM mới là nơi xác minh địa chỉ trực tiếp của VM.

### Bước 4. Đọc routes và firewall

~~~bash
gcloud compute routes list --project=PROJECT_ID
gcloud compute firewall-rules list --project=PROJECT_ID
~~~

Tìm đích route (IPv4/IPv6), next hop, network và priority. Kiểm tra firewall direction, priority, source/destination range, targets, ports và trạng thái enabled. **Một route tồn tại không chứng minh traffic được phép qua firewall.**

Nếu được phép truy cập một VM Linux sandbox, các lệnh **chỉ đọc trong VM**:

~~~bash
ip -brief address
ip route
ip -6 route
getent ahosts example.com
~~~

External IPv4 gắn VM có thể không xuất hiện trong `ip -brief address` do ánh xạ NAT một-một; cần đối chiếu Console/API. **Gateway ảo primary IPv4 của Google Cloud không nhất thiết trả lời ping**, nên ping gateway thất bại không đủ kết luận mất mạng.

### Bước 5. Mẫu ghi nhận

| Mục | Giá trị cần ghi | Nhận xét |
|---|---|---|
| VPC | Name, mode | Global, có bao nhiêu subnet? |
| Subnet | Region, primary/secondary CIDR | Có overlap hoặc thiếu IP? |
| IPv6 | Stack type, internal/external access | Đã kiểm tra khả năng hỗ trợ chưa? |
| VM | Internal/external IPv4, IPv6 | Static hay ephemeral? |
| Route | Destination, next hop | Đường đến nội bộ/internet? |
| Firewall | Direction, source, target, port | Có đúng nguyên tắc tối thiểu không? |
| Private Google Access | On/Off | VM không external IP có gọi Google API cần dùng không? |
| NAT | Region, subnet được phục vụ | Outbound IPv4 của VM nào phụ thuộc NAT? |

## 13. Thiết lập subnet mẫu trong môi trường thực hành (tùy chọn)

Đây là **minh họa thao tác tạo tài nguyên**, khác các bước chỉ đọc ở phần 12. Chỉ thực hiện trong sandbox được cho phép; kiểm tra dải CIDR và quyền trước khi chạy. Dù bản thân một VPC/subnet có thể không tính phí riêng, tài nguyên gắn theo và traffic vẫn có thể phát sinh phí.

~~~bash
# Tạo custom VPC.
gcloud compute networks create training-vpc --subnet-mode=custom --project=PROJECT_ID

# Tạo primary IPv4 subnet trong region Singapore.
gcloud compute networks subnets create training-app-sg --network=training-vpc --region=asia-southeast1 --range=10.40.0.0/24 --project=PROJECT_ID

# Đọc lại trạng thái.
gcloud compute networks subnets describe training-app-sg --region=asia-southeast1 --project=PROJECT_ID
~~~

Ví dụ này **chưa tạo VM, external IP, firewall mở rộng hoặc Cloud NAT**. Nếu cần triển khai IPv6, vào Console chọn **dual-stack/IPv6-only** trên custom VPC, lựa chọn **IPv6 access type INTERNAL/EXTERNAL** và làm theo quy trình dải IPv6 được hỗ trợ. Với internal IPv6 cần chuẩn bị dải internal IPv6 cho VPC. Không tự bịa một địa chỉ từ prefix tài liệu `2001:db8::/32` để cấp cho VM thực tế.

Nếu đã tạo tài nguyên chỉ để thực hành, chỉ dọn dẹp khi chắc chắn mạng không được dùng bởi workload khác, có quyền được giao và thực hiện theo quy trình sandbox:

~~~bash
# Chỉ thực hiện với subnet/VPC training thật sự thuộc bài lab.
gcloud compute networks subnets delete training-app-sg --region=asia-southeast1 --project=PROJECT_ID
gcloud compute networks delete training-vpc --project=PROJECT_ID
~~~

Lệnh xóa có thể thất bại nếu mạng đang được tài nguyên sử dụng. Không dùng `--quiet` để bỏ qua kiểm tra trong lab cần xác minh rõ.

## 14. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Khả năng | Cách kiểm tra |
|---|---|---|
| VM có `10.x.x.x` nhưng không ra internet IPv4 | Không external IPv4, Public NAT không phục vụ subnet, route/egress chặn | Interface, NAT subnet/region, route mặc định, firewall |
| VM có public IPv4 nhưng SSH/HTTP timeout | Ingress rule chặn, OS listener sai, VM không chạy | Source/target/port, OS firewall, app status |
| VM không external IP không gọi được Cloud Storage API | PGA/DNS/route/firewall/IAM chưa phù hợp | Cấu hình subnet, API endpoint, lỗi `PERMISSION_DENIED` |
| Hai VM cùng VPC không liên lạc được | Firewall, route đặc biệt hoặc app bind localhost | Kiểm tra gói tin, IP, ingress/egress, listener |
| Không tạo được VM vì thiếu địa chỉ | Subnet primary hết IP khả dụng | CIDR và IP đã dùng/reserve |
| Không thấy public IPv4 trong `ip addr` | Google dùng NAT một-một cho external IPv4 | Xem network interface trong Compute API |
| DNS AAAA có mà IPv6 lỗi | Thiếu IPv6 frontend/route/firewall, TLS hoặc app | Thử kết nối IPv4 và IPv6 riêng, xem logs |
| IPv6-only không gọi được đích IPv4 | Thiếu DNS64/NAT64 theo khả năng hỗ trợ | Kiểm tra resolver, NAT64, route và dịch vụ |
| Không thể thêm IPv6 subnet | VPC auto mode hoặc chưa có cấu hình IPv6 phù hợp | Kiểm tra VPC mode, access type và dải internal |
| Peering hoặc VPN thất bại | CIDR overlap, route/BGP/firewall | Đối chiếu dải hai phía, learned routes |
| Public NAT lỗi khi tải tăng | Thiếu NAT ports hoặc IP, quá nhiều kết nối | NAT metrics, drops, source ports |
| Chi phí tăng sau mở public frontend | External IPv4, LB, NAT, egress hoặc reserved IP | Cloud Billing reports theo service/SKU |

Một quy trình chẩn đoán có ích: xác nhận **project → VPC/subnet → địa chỉ nguồn/đích → route → firewall → DNS/listener → IAM/ứng dụng → logging/metrics**. Tránh “sửa nhanh” bằng việc cho phép toàn bộ traffic từ `0.0.0.0/0` hoặc `::/0`.

## 15. Bài tập thiết kế và câu hỏi tự đánh giá

### 15.1. Bài toán

Một công ty cần triển khai:

- Web API công khai cho người dùng IPv4 và IPv6 qua HTTPS.
- VM xử lý nền gọi website cập nhật IPv4 và Cloud Storage API, không nhận truy cập từ internet.
- Database đặt hàng chỉ cho API/VM được ủy quyền kết nối.
- Mạng văn phòng đã dùng `192.168.10.0/24`; sau này sẽ nối Cloud VPN.
- Nhóm vận hành muốn ít IP public, có giám sát chi phí, đủ IP cho tăng tải.

**Câu hỏi:**

1. Chọn VPC auto hay custom? Đề xuất hai subnet IPv4 không chồng lấn và giải thích lý do.
2. Subnet primary `10.40.0.0/24` có bao nhiêu địa chỉ IPv4 tất cả và bao nhiêu khả dụng?
3. VM batch có cần external IPv4 không? Chọn cách đi internet IPv4 và gọi Google APIs.
4. Làm sao cấp điểm vào HTTPS cho cả IPv4/IPv6? Cần cấu hình DNS và firewall nào?
5. So sánh subnet dual-stack **internal IPv6** với dual-stack **external IPv6**.
6. Vì sao database private endpoint vẫn cần IAM/database auth và firewall/đường kết nối đúng?
7. Chọn hai chỉ số phát hiện sự cố IP/NAT và hai nguồn chi phí mạng để giám sát.
8. VM không ping được gateway ảo thì có đủ kết luận subnet mất mạng không?
9. Nếu ứng dụng ghi đè AAAA nhưng backend không hỗ trợ IPv6, người dùng có thể gặp gì?
10. Khi kết nối VPN với mạng có CIDR trùng, vì sao default route chưa đủ giải quyết?

### 15.2. Hướng dẫn đối chiếu

Một lời giải có cơ sở thường bắt đầu từ **custom VPC** với CIDR đủ rộng và không trùng văn phòng/những mạng sẽ nối. Chẳng hạn có thể cân nhắc `10.40.0.0/24` và `10.40.1.0/24` nếu toàn bộ quy hoạch liên quan không chồng lấn.

Subnet primary `/24` có **256 địa chỉ**, Google Cloud dành **4** địa chỉ, còn **252** địa chỉ khả dụng. VM batch có thể chỉ dùng internal IPv4, qua **Public NAT** khi truy cập internet IPv4 và **Private Google Access** để gọi Google APIs theo cấu hình thích hợp. Frontend HTTP nên dùng endpoint hoặc load balancer hỗ trợ cả hai họ địa chỉ, có DNS A/AAAA, TLS, health check và firewall phù hợp.

Internal IPv6 không được định tuyến trực tiếp trên internet; external IPv6 có thể internet-routable nhưng không tự mở port. Database private vẫn cần **đúng tuyến mạng, firewall và chứng thực/ủy quyền**, chứ IP private không đủ bảo mật. Các chỉ số nên gồm **số IP còn trống, NAT dropped packets/ports, lỗi kết nối**, đồng thời quan sát **external IPv4, NAT, load balancing và network egress**. Gateway ảo không phản hồi ICMP là hiện tượng có thể xảy ra, không đủ chứng minh mạng hỏng.

## 16. Checklist trước khi triển khai thực tế

- [ ] Chọn VPC auto/custom phù hợp; tính CIDR và tránh overlap với hybrid/peer networks.
- [ ] Dự trù primary IPv4, secondary ranges, alias IP, GKE nodes/pods và autoscaling.
- [ ] Phân biệt internal/external, static/ephemeral, regional/global cho từng endpoint.
- [ ] Chỉ cấp external IP khi cần; backend/database ưu tiên private access phù hợp.
- [ ] Nếu có IPv6: xác định dual-stack/IPv6-only, access type, hỗ trợ OS/dịch vụ, DNS và firewall.
- [ ] Kiểm tra route IPv4/IPv6, firewall ingress/egress, OS listener, TLS và IAM ứng dụng.
- [ ] VM không external IPv4 có Public NAT, Private Google Access hoặc private endpoint theo nhu cầu thực tế.
- [ ] Có số liệu kiểm thử kết nối, logs, NAT port usage, IP availability và cảnh báo.
- [ ] Đã tính external IPv4, NAT, load balancer, network egress và phí mạng liên quan.
- [ ] Có chủ sở hữu cấu hình mạng, quy trình phê duyệt và kịch bản khôi phục khi thay đổi route/firewall/IP.

## 17. Tài liệu tham khảo chính thức

Các khả năng IPv6, cách cấp IP, giới hạn sản phẩm và giá có thể thay đổi. Khi triển khai lên project thật, kiểm tra tài liệu cập nhật:

- [VPC networks](https://docs.cloud.google.com/vpc/docs/vpc) — phạm vi global của VPC và regional subnet.
- [Subnets](https://docs.cloud.google.com/vpc/docs/subnets) — primary/secondary IPv4, IPv6 `/64` và bốn địa chỉ IPv4 được dự trữ.
- [IP addresses in VPC](https://docs.cloud.google.com/vpc/docs/ip-addresses) — internal/external, private/public.
- [Compute Engine IP addresses](https://docs.cloud.google.com/compute/docs/ip-addresses) — giao diện và IPv6 `/96`.
- [Configure IPv6 addresses](https://docs.cloud.google.com/compute/docs/ip-addresses/configure-ipv6-address) — dual-stack, IPv6-only và network interface.
- [VPC routes](https://docs.cloud.google.com/vpc/docs/routes) — đường đi và default routes.
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls) — ingress/egress và implied rules.
- [Cloud NAT overview](https://docs.cloud.google.com/nat/docs/overview) — NAT outbound, NAT44/NAT64.
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access) — Google APIs từ VM không có external IP.
- [Private access options](https://docs.cloud.google.com/vpc/docs/private-access-options) — PSC, private services access và các phương án riêng.
- [IPv6 support in Google Cloud](https://docs.cloud.google.com/vpc/docs/ipv6-support) — khả năng hỗ trợ theo dịch vụ.

**Điểm cần nhớ:** **IPv4/IPv6** mô tả họ địa chỉ; **internal/external** mô tả phạm vi kết nối; **static/ephemeral** mô tả vòng đời; **regional/global** mô tả phạm vi tài nguyên. Thiết kế Google Cloud an toàn phải ghép **IP + subnet + route + firewall + danh tính/quyền truy cập + cấu hình dịch vụ**. Nắm chắc những lớp này giúp đội ngũ chọn Compute Engine, GKE, Cloud Run và các dịch vụ dữ liệu theo yêu cầu về bảo mật, độ tin cậy, mở rộng và chi phí.
