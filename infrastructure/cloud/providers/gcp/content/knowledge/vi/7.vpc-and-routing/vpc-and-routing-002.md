# Custom mode VPC và quy hoạch địa chỉ IP

Một nhóm ứng dụng tạo VPC đầu tiên và chọn dải địa chỉ theo cảm tính. Vài tháng sau, nhóm phải kết nối với hệ thống tại văn phòng qua Cloud VPN và xây cụm GKE ở region khác; địa chỉ của các mạng trùng nhau, Pod không còn đủ IP, quy tắc firewall và route phải sửa hàng loạt. Các lỗi này thường không xuất phát từ một lệnh tạo VM, mà từ việc thiếu **quy hoạch IP ngay khi thiết kế mạng**.

Trong Google Cloud, **Custom mode VPC** cho phép nhóm tự quyết định các subnet sẽ được tạo ở region nào và dùng CIDR nào. Đây là lựa chọn quan trọng trong chương **VPC và định tuyến** của học phần **CLOUD_PROVIDERS_GCP**: từ tổ chức project, IAM, VPC đến vận hành Compute Engine, GKE, Cloud Run, lưu trữ/cơ sở dữ liệu và các tình huống triển khai cần kết nối an toàn, dễ mở rộng, có thể tự động hóa, giám sát và kiểm soát chi phí.

Sau bài học, bạn có thể:

- Phân biệt VPC global, subnet regional, zone và các chế độ tạo subnet.
- Đọc và tính dung lượng dải IPv4 theo ký hiệu CIDR; nhận diện các IP mà Google Cloud dành riêng.
- Thiết kế **IP address plan** cho nhiều môi trường, region và nhóm phát triển.
- Dành riêng primary range cho VM/GKE node và secondary range cho GKE Pod/Service khi cần.
- Phát hiện nguy cơ CIDR trùng nhau khi kết nối VPC Peering, Shared VPC hoặc on-premises.
- Tạo, kiểm tra và mở rộng Custom mode VPC bằng Console, `gcloud` và Terraform.

## 1. VPC, subnet và region trong Google Cloud

**Virtual Private Cloud (VPC)** là mạng ảo định nghĩa kết nối, routing, firewall và các subnet cho tài nguyên Google Cloud. Khác với cách nhiều hệ thống truyền thống triển khai mạng theo từng khu vực, **VPC network của Google Cloud là tài nguyên global**; **subnet là tài nguyên regional**.

~~~text
Project: shop-network-prod
└── VPC: prod-custom                 (global)
    ├── Subnet: prod-sg-app          (region asia-southeast1)
    │   ├── VM ở zone asia-southeast1-a
    │   ├── VM ở zone asia-southeast1-b
    │   └── GKE node/pod trong các zone phù hợp
    └── Subnet: prod-tokyo-app       (region asia-northeast1)
        └── VM và GKE node thuộc region này
~~~

| Thành phần | Phạm vi | Ý nghĩa khi quy hoạch |
|---|---|---|
| VPC network | Global | Một VPC có thể chứa subnet ở nhiều region, không có một “CIDR của cả VPC” bắt buộc phải khai báo. |
| Subnet | Regional | Có primary IPv4 range và có thể có secondary IPv4 range; các tài nguyên phù hợp trong nhiều zone cùng region có thể sử dụng. |
| VM Compute Engine | Zonal | NIC lấy primary internal IP từ subnet trong region chứa zone của VM. |
| GKE VPC-native | Cluster zonal hoặc regional theo cấu hình | Node thường dùng primary range; Pod dùng secondary range của subnet, còn Service tùy mô hình cấp phát. |
| Cloud Run | Regional | Kết nối VPC khi cần tài nguyên private; khả năng dùng IP phụ thuộc phương thức Direct VPC egress/connector. |
| Cloud Router | Regional | Trao đổi route động với mạng khác; cấu hình dynamic routing mode của VPC quyết định phạm vi route động nhận được. |

Khi một VPC có các subnet khác region, Google Cloud tạo **subnet routes** tương ứng để định tuyến địa chỉ của các subnet trong VPC. Tuy nhiên, có route chưa đủ để ứng dụng giao tiếp: firewall và quyền truy cập dịch vụ vẫn phải cho phép.

## 2. Auto mode và Custom mode khác nhau thế nào?

Google Cloud có hai chế độ tạo subnet:

| Tiêu chí | Auto mode VPC | Custom mode VPC |
|---|---|---|
| Khi tạo VPC | Có subnet IPv4 được tạo tự động ở các region | **Không có subnet nào được tạo tự động** |
| Dải địa chỉ | Các subnet tạo tự động nằm trong không gian `10.128.0.0/9` theo quy ước Google Cloud | Người thiết kế chọn các CIDR hợp lệ cho từng subnet |
| Khi Google Cloud có region mới | Tự có thêm subnet tạo tự động theo cơ chế dịch vụ | Chỉ có subnet mới khi quản trị viên chủ động tạo |
| Kiểm soát đặt subnet | Ít linh hoạt với các subnet được tạo tự động | Linh hoạt về region, số lượng, tên và CIDR |
| Khi cần kết nối hybrid/peering | Có thể gặp chồng lấn với những mạng hiện hữu | Dễ đặt dải địa chỉ không xung đột hơn nếu được quy hoạch |
| Phù hợp | Bắt đầu nhanh, bài thử nghiệm nhỏ | Nền tảng doanh nghiệp, nhiều project/môi trường, dự kiến phát triển lâu dài |

**Custom mode là chế độ tạo subnet, không có nghĩa VPC “custom” sẽ tự an toàn hoặc có route đặc biệt.** Vẫn phải cấu hình firewall, IAM, Cloud NAT, kết nối hybrid và các bảo vệ khác theo nhu cầu.

Có thể **chuyển từ Auto mode sang Custom mode**, nhưng không thể chuyển Custom mode trở lại Auto mode. Khi chuyển, các subnet đã tạo từ Auto mode vẫn tồn tại; quá trình chuyển không tự đổi toàn bộ CIDR sang địa chỉ mới. Nếu đã dùng mạng mặc định có phạm vi không phù hợp, nên xem xét xây mạng mới và di chuyển workload theo kế hoạch.

**Lưu ý:** project mới có thể có VPC `default` thuộc Auto mode nếu tổ chức chưa tắt việc tạo network mặc định. Với mô hình quản trị tập trung, nên cân nhắc chặn việc tự tạo VPC mặc định và chỉ dùng những VPC đã được phê duyệt.

## 3. CIDR: đọc dải IP và tính dung lượng

CIDR (Classless Inter-Domain Routing) biểu diễn địa chỉ mạng dưới dạng `địa_chỉ/prefix_length`, ví dụ `10.32.0.0/20`. Trong IPv4 có 32 bit; `/20` nghĩa là 20 bit thuộc phần prefix và 12 bit còn lại dành cho địa chỉ trong dải.

Số địa chỉ IPv4 của một CIDR:

\[
\text{Số địa chỉ IPv4} = 2^{32-p}
\]

trong đó `p` là độ dài prefix. Với **primary IPv4 subnet** thông thường của Google Cloud, **4 địa chỉ không dùng được**: địa chỉ đầu, địa chỉ gateway kế tiếp, địa chỉ áp cuối và địa chỉ cuối của dải.

| CIDR | Tổng IPv4 | Primary IP khả dụng cho tài nguyên thông thường | Ví dụ dải |
|---|---:|---:|---|
| `/29` | 8 | 4 | `10.1.1.0–10.1.1.7` |
| `/28` | 16 | 12 | `10.1.1.0–10.1.1.15` |
| `/24` | 256 | 252 | `10.1.1.0–10.1.1.255` |
| `/20` | 4.096 | 4.092 | `10.32.0.0–10.32.15.255` |
| `/16` | 65.536 | 65.532 | `10.32.0.0–10.32.255.255` |
| `/14` | 262.144 | 262.140 | `10.40.0.0–10.43.255.255` |

Ví dụ với primary subnet `10.32.1.0/24`:

~~~text
10.32.1.0      network address          (không cấp cho VM)
10.32.1.1      default gateway ảo       (không cấp cho VM)
10.32.1.2      IP thông thường đầu tiên
...
10.32.1.253    IP thông thường cuối cùng
10.32.1.254    dành riêng của Google Cloud
10.32.1.255    broadcast address        (không cấp cho VM)
~~~

**Chỉ áp phép trừ 4 cho primary IPv4 range.** Google Cloud không dành riêng bốn địa chỉ như vậy trong **secondary IPv4 ranges**; chúng dùng cho alias IP, không phải cùng cơ chế cấp primary IP cho VM. Dung lượng thực tế vẫn cần trừ nhu cầu và giới hạn của dịch vụ sử dụng địa chỉ.

### Ranh giới và tính căn chỉnh của CIDR

Một CIDR phải bắt đầu đúng ranh giới prefix. Ví dụ `10.32.0.0/20` hợp lệ; địa chỉ `10.32.5.0/20` nằm *trong* dải đó nhưng không phải địa chỉ đầu của dải `/20`. Khi xây IPAM, hãy biểu diễn CIDR đã chuẩn hóa và kiểm tra overlap bằng công cụ mạng, không chỉ so chuỗi văn bản.

**Các dải IPv4 private theo RFC 1918**:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

Google Cloud còn có một số dải IPv4 khác được phép dùng nội bộ trong điều kiện nhất định. Tuy nhiên, với mạng doanh nghiệp kết nối nhiều hệ thống, nên ưu tiên quy hoạch tập trung trong RFC 1918 và tránh dải xung đột với Docker, VPN người dùng hoặc hệ thống on-prem. Đừng coi địa chỉ “private” là bằng chứng cho phép mọi máy truy cập nhau.

## 4. Các nguyên tắc quy hoạch địa chỉ

Trước khi tạo Custom mode VPC, cần thu thập thông tin từ **toàn bộ các mạng có thể cần kết nối trong tương lai**, gồm:

1. Subnet mạng văn phòng, trung tâm dữ liệu và mạng đối tác qua Cloud VPN/Cloud Interconnect.
2. VPC đã có tại những project khác, gồm Shared VPC và VPC Peering.
3. Mạng của môi trường phát triển/staging/production và region cần dùng.
4. Dải dùng cho GKE node, Pod, Service và các thành phần đặc thù như private services access.
5. Dải của môi trường chạy container hoặc VPN trên máy developer; ví dụ tránh trùng bridge network local nếu lưu lượng cần đi qua VPN.
6. Tăng trưởng dự kiến về số VM, số node GKE, số Pod mỗi node, số region và các dịch vụ cần IP riêng.

Các nguyên tắc:

- **Không chồng lấn** primary/secondary subnet trong cùng VPC. Nếu dự kiến VPC Peering, các subnet trong hai VPC peered cũng phải có CIDR không chồng lấn.
- **Dành block theo môi trường** để tránh lẫn dev/prod và dễ nhận diện trong log, firewall, IPAM.
- **Dành khoảng trống có chủ đích** cho mở rộng subnet, thêm region, Pod hoặc service mới.
- **Chọn prefix theo nhu cầu thực tế**, không mặc định cấp `/16` cho mỗi nhóm nhỏ; địa chỉ rộng cũng là tài nguyên cần quản lý.
- **Tách thông tin “reserved for planning” với subnet thực tế**: reserve một supernet trong IPAM không tự tạo subnet hay route trong VPC.
- **Theo dõi từ IPAM trung tâm**, gồm môi trường, region, VPC, project, subnet, owner và tình trạng cấp phát. Không tạo CIDR ngoài registry.

### Vì sao không nên “tự chọn 10.0.0.0/16” cho mọi VPC?

Hai VPC độc lập có thể tạm thời cùng dùng một dải private khi không trao đổi lưu lượng. Nhưng khi kết nối qua **VPC Network Peering**, Google Cloud yêu cầu subnet routes không overlap. Cloud VPN/Interconnect cũng phát sinh vấn đề định tuyến nếu mạng on-prem có CIDR trùng. Dự án thử nghiệm hôm nay có thể trở thành dịch vụ tích hợp ngày mai; vì vậy cần kiểm tra khả năng liên kết ngay từ đầu.

## 5. Ví dụ IP plan cho hai môi trường và hai region

Giả sử công ty triển khai backend ở Singapore và Tokyo. Production và nonproduction dùng VPC khác nhau; nhóm platform giữ một không gian địa chỉ cho shared services và mạng on-prem.

**Phân bổ cấp cao trong sổ IPAM** (chưa phải cấu hình VPC):

| Phạm vi dự phòng | Block | Ghi chú |
|---|---|---|
| Production | `10.32.0.0/11` | Từ `10.32.0.0` đến `10.63.255.255` |
| Nonproduction | `10.64.0.0/11` | Từ `10.64.0.0` đến `10.95.255.255` |
| Shared services | `10.96.0.0/12` | Dành cho hạ tầng dùng chung sau này |
| On-premises | `172.20.0.0/16` | Giả định đã được network team xác nhận không overlap |

Trong mỗi VPC, dành **primary range cho VM/nodes**, **secondary range cho Pods** và **secondary range cho Services nếu chọn phương án cấp phát user-managed**:

| VPC | Region | Subnet | Primary (VM/node) | Secondary Pod | Secondary Service |
|---|---|---|---|---|---|
| `prod-custom` | Singapore: `asia-southeast1` | `prod-sg-app` | `10.32.0.0/20` | `10.40.0.0/14` | `10.44.0.0/20` |
| `prod-custom` | Tokyo: `asia-northeast1` | `prod-tokyo-app` | `10.32.16.0/20` | `10.48.0.0/14` | `10.52.0.0/20` |
| `nonprod-custom` | Singapore: `asia-southeast1` | `nonprod-sg-app` | `10.64.0.0/20` | `10.72.0.0/14` | `10.76.0.0/20` |
| `nonprod-custom` | Tokyo: `asia-northeast1` | `nonprod-tokyo-app` | `10.64.16.0/20` | `10.80.0.0/14` | `10.84.0.0/20` |

Đây là **mẫu minh họa** để học cách tổ chức không gian địa chỉ, không phải khuyến nghị cố định cho mọi ứng dụng. Các Pod range `/14` khá lớn, chỉ phù hợp nếu nhu cầu mở rộng tương ứng; team nên tính cỡ Pod CIDR từ số node dự kiến và thông số cấp IP của phiên bản GKE sử dụng.

~~~text
IPAM của công ty
├── 10.32.0.0/11  Production
│   ├── 10.32.0.0/20   SG nodes/VMs
│   ├── 10.40.0.0/14   SG Pods
│   ├── 10.44.0.0/20   SG Services (user-managed)
│   ├── 10.32.16.0/20  Tokyo nodes/VMs
│   ├── 10.48.0.0/14   Tokyo Pods
│   └── 10.52.0.0/20   Tokyo Services (user-managed)
├── 10.64.0.0/11  Nonproduction
│   └── Dải tương ứng được cấp cho SG và Tokyo
├── 10.96.0.0/12  Shared services (dự phòng)
└── 172.20.0.0/16 On-premises (giả định)
~~~

**Quan trọng:** `10.32.0.0/11` là khối **dự phòng trên giấy/IPAM**, không phải dải subnet phải tạo nguyên khối. Mỗi dòng primary hoặc secondary là một CIDR riêng, không overlap với các dòng khác. Phần không sử dụng được giữ để mở rộng sau này.

### Tại sao chia theo vùng và môi trường?

Hai subnet trong **cùng VPC** ở Singapore và Tokyo có thể giao tiếp theo đường định tuyến hệ thống, nhưng vẫn cần firewall. Hai VPC production và nonproduction không mặc nhiên kết nối chỉ vì chúng nằm trong cùng Organization. Nếu sau này cần peering hoặc kết nối qua hub, các dải trên đã không overlap, giúp giảm một loại trở ngại thường gặp.

Không nhất thiết mỗi nhóm ứng dụng cần một VPC riêng. Khi nhiều project sử dụng chung mạng do đội platform vận hành, có thể dùng **Shared VPC**; thiết kế CIDR thuộc host project còn các service project sử dụng subnet theo IAM và chính sách.

## 6. Quy hoạch IP cho GKE VPC-native

Trong **GKE VPC-native**, các loại IP chính gồm:

| Loại địa chỉ | Nguồn cấp | Dùng để làm gì |
|---|---|---|
| **Node IP** | Primary range của subnet | Địa chỉ NIC của VM chạy node |
| **Pod IP** | Secondary range cho Pod (alias IP) | Cấp cho Pod, quản lý theo node/pod range |
| **Service ClusterIP** | Secondary range cho Service *hoặc* GKE-managed service range, tùy phiên bản/cấu hình | Địa chỉ ảo để truy cập Kubernetes Service |
| **Control plane** | Phụ thuộc kiến trúc control plane và loại cluster | Quản trị cụm, có yêu cầu địa chỉ/kết nối riêng |
| **Internal load balancer** | Thường sử dụng IP nội bộ phù hợp với subnet và loại LB | Cung cấp endpoint nội bộ |

Trong các phiên bản GKE mới, **Service có thể sử dụng dải do GKE quản lý** như `34.118.224.0/20` thay vì secondary range do người dùng khai báo. Nếu đã chọn cách này, không nhất thiết phải tạo secondary Service range theo ví dụ ở mục trước. Cần quyết định theo **cluster version, chế độ Autopilot/Standard và khả năng sử dụng** của cấu hình thực tế.

### Tính Pod range không thể chỉ đếm Pod đang chạy

Trong mô hình VPC-native IPv4, GKE phân phối một **CIDR cho mỗi node** để cấp IP cho các Pod, phụ thuộc số Pod tối đa trên node và chế độ cluster. Ví dụ mức phân phối phổ biến của GKE Standard là `/24` mỗi node theo cấu hình mặc định; Autopilot có các quy tắc khác. Dùng một Pod range `/20` (4.096 địa chỉ) sẽ không tương đương việc có thể chạy đúng 4.096 Pod, vì IP được phân thành các block cho node.

Ví dụ giả định:

~~~text
Pod secondary range 10.40.0.0/20 = 4.096 địa chỉ
Giả sử mỗi node được cấp một block /24 = 256 địa chỉ
Số block /24 tối đa về mặt toán học: 4.096 / 256 = 16
=> Khoảng 16 node theo giả định /24, chưa kể giới hạn và cách quản lý của GKE
~~~

Phép tính này là **minh họa để hiểu cấp phát theo block**, không thay thế tài liệu công suất GKE. Cần kiểm tra giá trị `maxPodsPerNode`, vùng node, node pool, giới hạn cluster, tính năng đa Pod CIDR và dự phòng khi autoscale.

Các điểm khó sửa sau khi tạo:

- Primary subnet có thể **mở rộng**, nhưng không thu nhỏ hoặc thay thế bằng CIDR khác trong cùng subnet.
- Secondary range có thể được thay thế/xóa khi **không còn tài nguyên sử dụng**; một số cấu hình GKE đang dùng khiến thao tác này không khả thi nếu không di chuyển/đổi cluster.
- Với VPC-native cluster, Service range do người dùng cấp có giới hạn thay đổi; có tình huống cần tạo cluster mới nếu quyết định ban đầu quá hẹp.
- Nếu GKE tự chọn secondary range, phải kiểm tra sự phù hợp với IPAM và những mạng dự kiến nối qua peering/hybrid.

Vì vậy, hãy **dành không gian IP cho tăng trưởng GKE trước khi khởi tạo cluster**, đặc biệt là Pod range.

## 7. Các vấn đề khi kết nối mạng khác

### VPC Network Peering

VPC Peering trao đổi subnet routes giữa hai VPC theo các quy tắc của dịch vụ. Với những subnet dùng private IPv4:

- Subnet IPv4 ranges **không được trùng hoặc chứa nhau** giữa các VPC peered.
- Peering **không có tính chuyển tiếp**: nếu A peered với B và B peered với C, A không tự có kết nối đến C.
- Firewall của từng VPC vẫn phải cho phép traffic cần thiết.
- Route export/import cho custom routes cần được xem xét riêng theo tính năng và cấu hình.

Ví dụ: nếu VPC A đã có subnet `10.32.0.0/16`, VPC B không thể tạo subnet `10.32.0.0/20` rồi peering thành công với A, vì `/20` nằm trong `/16`. Đổi tên subnet không giải quyết xung đột này.

### Cloud VPN / Cloud Interconnect và on-premises

Khi kết nối on-premises bằng **Cloud VPN** hoặc **Cloud Interconnect**, phải kiểm tra cả route trên Cloud Router và mạng phía đối tác. Nếu mạng on-prem đã dùng `10.40.0.0/16` mà ta cấp GKE Pod `10.40.0.0/14`, lưu lượng có thể xung đột nghiêm trọng dù subnet nodes không trùng.

**Cloud Router** dùng BGP trao đổi route động trong các mô hình được hỗ trợ. Cấu hình **regional/global dynamic routing mode** liên quan cách mạng áp dụng dynamic routes được Cloud Router học. Nó **không** quyết định rằng subnet ở hai region trong cùng VPC có kết nối hay không; subnet routes của VPC là một cơ chế khác.

Khi thiết kế hybrid, cần dự kiến:

- Dải subnet hiện tại và tương lai ở hai phía.
- Dải GKE Pods/Services, các hệ thống dùng alias IP và các địa chỉ được dịch vụ Google quản lý.
- Địa chỉ dùng cho Private Service Access, Private Service Connect, proxy-only subnet hoặc các dịch vụ managed nếu có.
- Routing quảng bá/nhận qua BGP, route ưu tiên, đường hồi đáp, firewall hai phía và DNS.
- Tính sẵn sàng khi một tunnel hoặc vùng mạng gặp sự cố.

### Shared VPC

Trong mô hình **Shared VPC**, *host project* chứa VPC/subnet còn *service project* dùng subnet được chia sẻ. Quản lý CIDR cần tập trung ở host project, không để mỗi service project tự tạo một subnet cùng dải rồi cho rằng đã dùng chung mạng.

Nhóm mạng có thể phân bổ một subnet cho nhiều nhóm và điều tiết quyền `roles/compute.networkUser` trên subnet theo nhu cầu. Với workload cần bảo vệ dữ liệu production, IAM, firewall và cấu hình mạng vẫn phải giới hạn traffic dù dùng chung VPC.

## 8. Hướng dẫn tạo Custom mode VPC bằng Console

Trước khi thao tác:

1. Chọn **project mạng** phù hợp và xác nhận billing/API cần thiết.
2. Xác nhận tên VPC, vùng, tên subnet và CIDR đã được cấp từ IPAM.
3. Kiểm tra CIDR không chồng với subnet khác, peer hoặc on-prem.
4. Xác định yêu cầu GKE, firewall, NAT và truy cập Google APIs.
5. Có quyền quản lý network/subnet tại project đích; nếu dùng Shared VPC cần tuân thủ quy trình của host project.

Thực hiện trong **Google Cloud Console → VPC network → VPC networks → Create VPC network**:

1. Đặt tên mạng, ví dụ `prod-custom`.
2. Chọn **Subnet creation mode: Custom**.
3. Thêm subnet `prod-sg-app`, region `asia-southeast1`, primary IPv4 range `10.32.0.0/20`.
4. Nếu chuẩn bị GKE VPC-native với user-managed ranges, thêm secondary range `prod-sg-pods = 10.40.0.0/14` và `prod-sg-services = 10.44.0.0/20`.
5. Thiết lập Private Google Access trên subnet khi VM không có external IP cần truy cập các API/dịch vụ Google được hỗ trợ.
6. Chọn dynamic routing mode dựa trên thiết kế hybrid; giữ cấu hình phù hợp nếu chưa có Cloud Router.
7. Rà soát cấu hình firewall. Custom mode VPC không mặc định có các firewall rule “allow nội bộ” như VPC `default`.
8. Tạo VPC, sau đó kiểm tra danh sách subnet và route hệ thống.

Khi tạo subnet cho region khác, chọn **subnet mới trong cùng VPC**, không cần tạo VPC khác chỉ để hỗ trợ region Tokyo.

## 9. Thực hành `gcloud`: tạo và xác minh VPC

Đoạn sau là **mẫu Bash**; chỉ chạy trên project thử nghiệm được cấp quyền. Lệnh tạo VPC/subnet và những tài nguyên bổ sung sau đó có thể phát sinh phí sử dụng khi kết nối với các dịch vụ tính phí.

~~~bash
PROJECT_ID="my-network-project"
VPC="prod-custom"

gcloud config set project "$PROJECT_ID"

# Tạo Custom mode VPC: không sinh sẵn subnet.
gcloud compute networks create "$VPC" \
  --subnet-mode=custom \
  --bgp-routing-mode=regional

# Subnet tại Singapore; các secondary ranges dành cho GKE
# khi chọn user-managed Pod và Service ranges.
gcloud compute networks subnets create prod-sg-app \
  --network="$VPC" \
  --region=asia-southeast1 \
  --range=10.32.0.0/20 \
  --secondary-range=prod-sg-pods=10.40.0.0/14,prod-sg-services=10.44.0.0/20 \
  --enable-private-ip-google-access

# Subnet thứ hai ở Tokyo trong CÙNG VPC global.
gcloud compute networks subnets create prod-tokyo-app \
  --network="$VPC" \
  --region=asia-northeast1 \
  --range=10.32.16.0/20 \
  --secondary-range=prod-tokyo-pods=10.48.0.0/14,prod-tokyo-services=10.52.0.0/20 \
  --enable-private-ip-google-access

# Đọc lại cấu hình.
gcloud compute networks describe "$VPC"
gcloud compute networks subnets list --network="$VPC"
gcloud compute networks subnets describe prod-sg-app \
  --region=asia-southeast1
gcloud compute routes list --filter="network:$VPC"
~~~

Các giá trị trên chỉ là minh họa. Cần kiểm tra sự tồn tại của VPC, subnet và các CIDR trước khi chạy để tránh tạo trùng hoặc xung đột. `gcloud compute networks subnets list` và `describe` hỗ trợ hậu kiểm, nhưng việc kiểm tra overlap với **mạng ngoài GCP** vẫn cần sổ IPAM và phối hợp với đội mạng.

### Firewall: có route chưa chắc có kết nối

Custom mode VPC có các quy tắc firewall ngầm định: **deny ingress** và **allow egress** ở mức áp dụng tương ứng. Do đó, hai VM ở cùng VPC có route đến nhau nhưng gói ingress vẫn có thể bị chặn.

Ví dụ chỉ cho phép traffic TCP cổng 8080 từ subnet Singapore đến những VM có network tag `app-server`:

~~~bash
gcloud compute firewall-rules create allow-sg-app-8080 \
  --network=prod-custom \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=10.32.0.0/20 \
  --target-tags=app-server
~~~

Đây là quy tắc minh họa, không phải cấu hình bảo mật production hoàn chỉnh. VM đích phải có tag phù hợp, các **hierarchical/global/regional firewall policies** cũng có thể ảnh hưởng quyết định cuối cùng. Đừng mở `0.0.0.0/0` cho SSH hoặc toàn bộ cổng chỉ để kiểm tra kết nối.

### Mở rộng subnet khi thiếu địa chỉ

Google Cloud cho phép **mở rộng primary IPv4 range** của subnet sang một supernet hợp lệ nếu không xung đột với những dải khác. Ví dụ có thể muốn mở `10.32.0.0/20` lên `10.32.0.0/19`, nhưng thao tác này sẽ bao gồm cả `10.32.16.0/20` đang cấp cho Tokyo trong ví dụ. **Vì vậy mở rộng như vậy không hợp lệ.**

Để dự trữ khả năng mở rộng, cần giữ **block liền kề** chưa dùng ngay từ khi quy hoạch. Nếu đã chia sát nhau, có thể phải tạo subnet khác và di chuyển hoặc bổ sung tài nguyên phù hợp thay vì mở rộng subnet đang dùng.

**Primary range không thể thu nhỏ** sau khi đã mở rộng. Những firewall rule, authorized networks hoặc route bên ngoài dựa theo CIDR cũ cũng phải được rà soát. Vì thế, việc thay đổi kích thước subnet là thay đổi mạng cần review, không phải thao tác thử nghiệm tùy tiện.

## 10. Khai báo Custom mode VPC bằng Terraform

Infrastructure as Code giúp đồng bộ network ở nhiều môi trường, kiểm tra thay đổi CIDR trong pull request và giảm nguy cơ thao tác tay sai subnet. Ví dụ tối giản cho VPC production và một subnet Singapore:

~~~hcl
terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }
}

variable "project_id" {
  type = string
}

resource "google_compute_network" "prod" {
  project                 = var.project_id
  name                    = "prod-custom"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "prod_sg_app" {
  project                  = var.project_id
  name                     = "prod-sg-app"
  region                   = "asia-southeast1"
  network                  = google_compute_network.prod.id
  ip_cidr_range            = "10.32.0.0/20"
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "prod-sg-pods"
    ip_cidr_range = "10.40.0.0/14"
  }

  secondary_ip_range {
    range_name    = "prod-sg-services"
    ip_cidr_range = "10.44.0.0/20"
  }
}
~~~

Trước khi apply trong môi trường thật:

- Kiểm tra `terraform fmt`, `terraform validate` và `terraform plan`.
- Đối chiếu mọi CIDR với registry/IPAM và lịch sử cấp phát.
- Review thay đổi subnet, nhất là thao tác thay thế hoặc xóa có thể gây gián đoạn.
- Bảo vệ Terraform state, dùng danh tính pipeline có IAM tối thiểu.
- Với Shared VPC, đặt tài nguyên mạng tại host project và để service project sử dụng qua IAM; không nhân bản mạng chỉ vì thay project ứng dụng.
- Giữ cấu hình firewall, Cloud NAT, Cloud Router/Hybrid connectivity và monitoring trong các module được quản lý riêng hoặc liên quan rõ ràng.

Không nên để nhiều Terraform state độc lập cùng quản lý một network/subnet khi không có quy tắc sở hữu tài nguyên; điều đó dễ gây drift và thay đổi xung đột.

## 11. Routing, NAT và truy cập dịch vụ sau khi có IP plan

**Có IP plan** không đồng nghĩa tài nguyên có thể kết nối đến mọi đích. Sau khi tạo subnet, cần phân biệt:

| Thành phần | Giải quyết việc gì? | Không thay thế |
|---|---|---|
| **Subnet routes** | Định tuyến giữa các subnet trong cùng VPC | Firewall và quyền truy cập |
| **Static routes** | Chọn next hop cho những đích được chỉ định theo quy tắc GCP | Dịch vụ DNS và cơ chế NAT |
| **Cloud Router/BGP** | Học/quảng bá dynamic routes cho kết nối hybrid được hỗ trợ | Firewall policy |
| **Cloud NAT** | NAT chiều ra cho workload phù hợp không có external IP | Một route mới tới Internet hoặc firewall allow |
| **Private Google Access** | Hỗ trợ VM không có external IP truy cập các API và dịch vụ Google được hỗ trợ | Kết nối Internet thông thường |
| **Cloud DNS** | Phân giải tên dịch vụ, kể cả private zones | Quyền mạng và đường định tuyến |

Ví dụ, VM trong `prod-sg-app` không có external IP nhưng cần tải dependency từ Internet. Chỉ bật **Private Google Access** có thể chưa đủ; cần xem xét **Cloud NAT**, route mặc định, firewall egress và DNS theo loại đích. Ngược lại, nếu chỉ truy cập một Google API qua endpoint được hỗ trợ, cấu hình Private Google Access/DNS có thể đáp ứng mà không cần external IP.

Không tạo static route trùng với subnet route để “sửa kết nối”; Google Cloud có quy tắc ưu tiên và bảo vệ subnet routes. Khi traffic không đi được, kiểm tra route, firewall, IAM/dịch vụ đích và đường hồi đáp theo thứ tự.

## 12. Kiểm tra và xử lý sự cố IP

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Tạo subnet báo CIDR overlap | Trùng primary/secondary trong VPC hoặc với subnet của VPC peered | Liệt kê subnet/peering, kiểm tra IPAM |
| VM không tạo được do thiếu IP | Primary range đã dùng gần hết hoặc quota dịch vụ | Xem subnet utilization, yêu cầu mở rộng hợp lệ |
| GKE không thêm được node | Node primary range hoặc Pod range không đủ theo số IP cấp cho node | Kiểm tra Pod CIDR, maxPodsPerNode, cluster autoscaler |
| Không kết nối được VM cùng VPC | Firewall ingress hoặc policy khác chặn | Connectivity Tests, effective firewall, VM tags/service accounts |
| Kết nối Cloud VPN có route bất thường | CIDR trùng hoặc route quảng bá/nhận sai | Cloud Router BGP status, route table hai phía |
| Gọi Google API lỗi từ VM private | Private Google Access, DNS, route, egress hoặc IAM | Kiểm tra API endpoint, subnet config và quyền API |
| Không truy cập được Internet từ VM private | Chưa cấu hình NAT/route/egress phù hợp | Cloud NAT logs, default route, firewall |
| GKE Services xung đột IP | User-managed Service range hoặc config cluster không phù hợp | Xem IP allocation policy của cluster |

Các thao tác hậu kiểm hữu ích:

~~~bash
gcloud compute networks subnets list --network=prod-custom
gcloud compute networks subnets describe prod-sg-app \
  --region=asia-southeast1 \
  --format="yaml(ipCidrRange,secondaryIpRanges,privateIpGoogleAccess)"

gcloud compute routes list \
  --filter="network:prod-custom"

# Nếu có GKE cluster liên quan:
gcloud container clusters describe CLUSTER_NAME \
  --region=asia-southeast1 \
  --format="yaml(ipAllocationPolicy)"
~~~

**Connectivity Tests** trong Network Intelligence Center có thể giúp phân tích đường đi dự kiến và nhiều nguyên nhân chặn traffic. Kết hợp với VPC Flow Logs, Firewall Rules Logging và Cloud Monitoring khi cần, vì việc nhìn một bảng CIDR không cho biết packet thực tế đã đi tới đâu.

## 13. Bài toán tổng hợp: mở rộng dịch vụ Java từ một region lên hai region

Một ứng dụng thương mại điện tử dùng Cloud Run cho API Java, GKE cho tác vụ xử lý nền và Cloud Storage cho dữ liệu. Ban đầu chỉ có một region ở Singapore; sau đó doanh nghiệp thêm Tokyo và kết nối CRM nội bộ qua Cloud VPN. Nhóm vận hành muốn duy trì môi trường staging và production độc lập.

**Thiết kế đề xuất:**

1. Dùng **Custom mode VPC** do nhóm platform quản lý cho production và một VPC riêng cho nonproduction.
2. Cấp primary subnet theo region; dùng secondary range khi GKE VPC-native cần user-managed Pod/Service IP.
3. Giữ địa chỉ sản xuất trong `10.32.0.0/11` và nonproduction trong `10.64.0.0/11` theo IPAM, dành shared services `10.96.0.0/12`.
4. Đối chiếu dải CRM on-prem và các vùng VPN trước khi cấp CIDR; kiểm tra cả GKE Pod ranges, không chỉ primary subnet.
5. Dùng Shared VPC nếu nhiều project ứng dụng cần các subnet chuẩn, với IAM riêng cho host/service projects.
6. Phân quyền và firewall theo luồng thực tế: Cloud Run → backend, GKE → database, VM → Google APIs; giữ dữ liệu production tách khỏi dev.
7. Thiết lập Cloud NAT/Private Google Access, route hybrid, DNS và giám sát theo nhu cầu.
8. Lưu cấu hình network bằng Terraform; review các thay đổi CIDR và hậu kiểm trước khi deploy workload mới.

**Một lỗi minh họa:** đội mạng đã cấp `10.32.16.0/20` cho Tokyo. Sau đó có người muốn tăng subnet Singapore từ `10.32.0.0/20` lên `10.32.0.0/19`. Dải mới sẽ bao gồm cả subnet Tokyo; yêu cầu bị xung đột. Thiết kế ban đầu nên giữ khoảng trống ngay sau primary subnet nếu muốn có khả năng mở rộng tại chỗ, hoặc chọn block rộng hơn và chia subnet khác vị trí ngay từ đầu.

**Đánh đổi:** dành nhiều IP dự phòng giúp mở rộng, nhưng trong môi trường nhiều mạng phải nối với nhau, các block quá lớn có thể làm cạn không gian RFC 1918. Giải pháp là đo nhu cầu dự báo, giữ registry rõ ràng, phân bổ có chủ đích và kiểm tra thay đổi theo thời gian.

## 14. Checklist trước khi phê duyệt CIDR cho Custom mode VPC

- [ ] Xác nhận VPC nào, project/host project nào và các region cần triển khai.
- [ ] Có danh mục IPAM cho toàn tổ chức, on-prem, các VPC peered và kết nối tương lai.
- [ ] Primary và secondary ranges không overlap; các CIDR căn chỉnh đúng prefix.
- [ ] Ước lượng số IP VM/node, Pod và Service theo khả năng tăng trưởng.
- [ ] Dành khoảng trống phù hợp nếu dự kiến **mở rộng primary subnet**.
- [ ] Đã kiểm tra yêu cầu GKE-managed hay user-managed Service ranges.
- [ ] VPC/Subnet phân tách môi trường và nhóm theo nhu cầu an ninh thực tế.
- [ ] Thiết kế firewall, route, Cloud Router/BGP, Cloud NAT, Private Google Access và DNS khi cần.
- [ ] Không dùng quy tắc “tạo subnet tức là mọi VM giao tiếp được”; có kế hoạch kiểm tra firewall.
- [ ] Các CIDR, owner, ngày cấp và lý do được lưu trong IPAM và Terraform.
- [ ] Mọi thay đổi kích thước subnet hoặc kết nối hybrid đi qua review và hậu kiểm.

**Bài tập vận dụng:** Bạn được giao thiết kế Custom mode VPC cho một nhóm có Compute Engine VMs và GKE ở Singapore, sau sáu tháng cần thêm Tokyo. Network team thông báo on-prem đã dùng `10.40.0.0/16` và VPC của đối tác dùng `10.64.0.0/16`. Hãy (1) đề xuất các block IP không chồng lấn, (2) chia primary và secondary ranges cho từng region, (3) chứng minh số địa chỉ primary khả dụng của mỗi subnet, (4) kiểm tra điều kiện peering và Cloud VPN, (5) viết lệnh `gcloud` tạo VPC/subnet, (6) mô tả một kế hoạch mở rộng nếu dự kiến số GKE node tăng gấp ba. Giải thích vì sao cần kiểm tra cả Pod range chứ không chỉ địa chỉ node.

## Tài liệu tham khảo chính thức

- [VPC networks](https://cloud.google.com/vpc/docs/vpc) — mạng global, Auto/Custom mode và định tuyến.
- [Subnets](https://cloud.google.com/vpc/docs/subnets) — primary/secondary IPv4 ranges, địa chỉ reserved, giới hạn overlap.
- [Create and modify VPC networks](https://cloud.google.com/vpc/docs/create-modify-vpc-networks) — tạo Custom mode và mở rộng subnet.
- [VPC Network Peering](https://cloud.google.com/vpc/docs/vpc-peering) — điều kiện kết nối và không trùng subnet.
- [VPC firewall rules](https://cloud.google.com/firewall/docs/firewalls) — firewall policies và traffic trong VPC.
- [Cloud Router overview](https://cloud.google.com/network-connectivity/docs/router/concepts/overview) — dynamic routing/BGP.
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview) — NAT cho workload outbound.
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access) — truy cập Google APIs từ VM private.
- [GKE VPC-native clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips) — alias IP và Pod/Service ranges.
- [GKE networking best practices](https://cloud.google.com/kubernetes-engine/docs/best-practices/networking) — dự trù dung lượng GKE.
