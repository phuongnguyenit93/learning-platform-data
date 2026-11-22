# Cloud Router và trao đổi tuyến bằng BGP

Một doanh nghiệp có hệ thống quản lý kho chạy trong trung tâm dữ liệu riêng và dịch vụ đặt hàng mới triển khai trên **Google Cloud**. Dịch vụ đặt hàng dùng **Cloud Run**, một số tác vụ chạy trên **Compute Engine** và **GKE**, dữ liệu được lưu trong **Cloud SQL** và **Cloud Storage**. Các workload cần trao đổi dữ liệu với hệ thống nội bộ, trong khi doanh nghiệp muốn giữ địa chỉ riêng, hạn chế đường truyền qua Internet công cộng và có khả năng chuyển đường khi một kết nối gặp sự cố.

Để thiết kế kết nối **hybrid** giữa mạng doanh nghiệp và **VPC** trên Google Cloud, ngoài VPN hoặc Interconnect còn cần một cơ chế để hai đầu **biết mạng nào có thể đi qua kết nối nào**. Google Cloud cung cấp **Cloud Router**, sử dụng **Border Gateway Protocol (BGP)** để trao đổi thông tin định tuyến động với thiết bị hoặc hệ thống BGP ngang hàng. Khi thêm mạng, rút mạng hoặc mất đường truyền, thông tin route có thể được cập nhật mà không phải quản lý tất cả đường đi bằng các static route thủ công.

Bài học thuộc chương **DNS và kết nối hybrid** của mô-đun **CLOUD_PROVIDERS_GCP**. Mục tiêu là hiểu rõ vai trò của Cloud Router/BGP trong thiết kế VPC, VPN và Interconnect; biết cấu hình và kiểm tra kết nối; đồng thời liên hệ định tuyến với IAM, bảo mật, phát hành ứng dụng, độ tin cậy và chi phí vận hành.

## 1. Cloud Router nằm ở đâu trong kiến trúc hybrid?

### 1.1. Cloud Router là dịch vụ định tuyến được quản lý

**Cloud Router** là dịch vụ được Google Cloud quản lý để trao đổi thông tin route bằng BGP. Một Cloud Router được tạo trong **một VPC** và **một region**. Nó có thể thiết lập BGP session với các peer qua những kết nối hỗ trợ, điển hình:

- **HA VPN:** kết nối IPsec giữa Cloud VPN gateway và VPN gateway của doanh nghiệp; các tunnel đủ điều kiện liên kết với interface/BGP peer trên Cloud Router.
- **Dedicated Interconnect hoặc Partner Interconnect:** kết nối chuyên dụng/đối tác với Google; BGP chạy qua **VLAN attachment** gắn với Cloud Router.
- Một số kiến trúc **Network Connectivity Center/router appliance** được hỗ trợ cũng sử dụng Cloud Router; cần đối chiếu hướng dẫn riêng của giải pháp.

Cloud Router **không phải máy ảo làm router cho từng gói tin**. Nó giữ vai trò **control plane**: học route từ peer, quảng bá route tới peer và cung cấp thông tin để VPC tạo đường định tuyến động phù hợp. **Data plane** chuyển gói tin qua Cloud VPN tunnel, Cloud Interconnect attachment và hạ tầng mạng Google Cloud theo route được chọn.

~~~mermaid
flowchart LR
    subgraph ON["Trung tâm dữ liệu doanh nghiệp"]
      DB["Mạng nội bộ 172.20.0.0/16"]
      PEER["Router/VPN thiết bị on-premises\nASN 65020"]
      DB --- PEER
    end
    subgraph GCP["Google Cloud - VPC retail-vpc"]
      TRANS["HA VPN tunnel hoặc Interconnect VLAN attachment"]
      CR["Cloud Router\nASN 65010 - control plane"]
      VPC["VPC routes và Google data plane"]
      APP["VM / GKE / ứng dụng 10.40.0.0/16"]
      VPC --- APP
    end
    PEER <-- "BGP: quảng bá/học prefix" --> CR
    PEER <-- "Luồng dữ liệu qua kết nối" --> TRANS
    TRANS --- VPC
    CR -. "Thông tin tuyến động" .-> VPC
~~~

Hai mũi tên giữa các thành phần biểu diễn **hai trách nhiệm khác nhau**: BGP quyết định việc trao đổi thông tin định tuyến, còn tunnel/attachment truyền traffic của ứng dụng. Một BGP session ở trạng thái `Established` **chưa chứng minh** ứng dụng kết nối được; cần kiểm tra route, firewall, DNS, quyền và dịch vụ đích.

### 1.2. Cloud Router không thay thế thành phần nào?

| Thành phần | Công việc chính | Điểm khác Cloud Router |
| --- | --- | --- |
| **HA VPN** | Tạo đường hầm IPsec và bảo vệ traffic qua kết nối VPN. | Cloud Router không tự tạo VPN tunnel hoặc mã hóa lưu lượng. |
| **Cloud Interconnect** | Cung cấp kết nối giữa mạng doanh nghiệp và Google qua hạ tầng kết nối được hỗ trợ. | Cloud Router trao đổi BGP trên attachment, không cung cấp đường truyền vật lý. |
| **VPC routes** | Xác định đường đi của các gói tin trong VPC. | Cloud Router đóng góp route động, nhưng VPC còn có subnet routes, static routes và các quy tắc chọn đường khác. |
| **Cloud DNS** | Phân giải hostname thành địa chỉ IP. | BGP trao đổi **IP prefixes**, không trao đổi tên DNS hoặc bản ghi `A`, `CNAME`, `SRV`. |
| **VPC firewall / policy** | Kiểm soát lưu lượng được phép đi qua. | Route có mặt không đồng nghĩa cổng TCP/UDP được cho phép. |
| **IAM** | Quyết định ai được quản trị tài nguyên hoặc gọi Google APIs. | BGP không cấp IAM role, service account hay database privilege. |

Ví dụ, ứng dụng dùng tên `erp.corp.example` để gọi API nội bộ. Cloud DNS forwarding hoặc một cơ chế phân giải hybrid có thể giúp tìm IP `172.20.10.15`; Cloud Router/BGP giúp Google Cloud biết đường đi tới **prefix** chứa IP đó. Cả hai phải đúng, nhưng mỗi thành phần giải quyết một vấn đề riêng.

## 2. Nắm vững BGP qua những khái niệm cơ bản

### 2.1. ASN, BGP peer và BGP session

**Border Gateway Protocol** là giao thức định tuyến trao đổi các mạng đích, gọi là **prefix** hoặc **CIDR**, giữa các hệ thống định tuyến. Trong tình huống Cloud Router kết nối với router doanh nghiệp, thông thường sử dụng **eBGP**, nghĩa là hai phía thuộc hai **Autonomous System Numbers (ASN)** khác nhau.

| Khái niệm | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| **Local ASN** | ASN cấu hình trên Cloud Router. | `65010` |
| **Peer ASN** | ASN của router BGP tại doanh nghiệp. | `65020` |
| **BGP session** | Phiên trao đổi thông tin định tuyến giữa hai peer. | `cloud-router ↔ on-prem-router` |
| **Interface IP** | Địa chỉ dùng cho phiên BGP trên kết nối hỗ trợ. | `169.254.21.1` |
| **Peer IP** | Địa chỉ BGP của đầu đối diện. | `169.254.21.2` |
| **Advertised prefix** | Dải địa chỉ mà một phía thông báo có thể đi tới qua mình. | Google quảng bá `10.40.0.0/16`. |
| **Learned prefix** | Dải địa chỉ nhận được từ phía bên kia qua BGP. | Google học `172.20.0.0/16`. |
| **Route priority / MED** | Thông tin giúp kiểm soát ưu tiên một số đường đi, tùy chính sách định tuyến và cách peer xử lý. | Ưu tiên đường chính và đường dự phòng theo thiết kế. |

Hai ASN `65010` và `65020` là ví dụ về **private ASN**. Trên môi trường thật cần chọn ASN hợp lệ, tránh xung đột với topology và chính sách của nhà mạng/thiết bị. ASN Cloud Router và ASN của BGP peer cần khác nhau cho eBGP. Địa chỉ `169.254.21.1/30` và `169.254.21.2/30` chỉ minh họa **cặp IP BGP link-local** cho một kết nối, **không phải** subnet IP ứng dụng và cũng không phải địa chỉ dùng để kết nối Cloud SQL.

### 2.2. Mỗi phía quảng bá và học những gì?

Giả sử:

~~~text
VPC Google Cloud:
  subnet-orders = 10.40.0.0/20
  subnet-data   = 10.40.16.0/20

On-premises:
  mạng ERP      = 172.20.10.0/24
  mạng kho      = 172.20.20.0/24
~~~

Khi cấu hình đúng:

1. **Cloud Router** quảng bá các prefix subnet phù hợp của VPC tới router on-premises, theo chế độ định tuyến và chính sách quảng bá đang dùng.
2. **Router on-premises** quảng bá các prefix nội bộ `172.20.10.0/24` và `172.20.20.0/24`.
3. **Cloud Router** nhận những prefix này, và Google Cloud có thể tạo các route động có hiệu lực cho VPC theo cơ chế chọn route.
4. Router on-premises dùng các route đã học để gửi traffic tới mạng của Google Cloud.

**Quan trọng:** không tự suy rằng mọi route trong VPC, mọi static route hoặc mọi route Cloud Router học từ một peer khác đều được quảng bá lại sang on-premises. Mặc định, Cloud Router quảng bá các subnet prefix theo quy tắc của chế độ định tuyến; phạm vi custom advertisement phải được cấu hình riêng khi cần. Google Cloud cũng không mặc nhiên biến VPC thành **transit router** giữa hai mạng bên ngoài.

### 2.3. BGP session có vòng đời

Một phiên BGP thông thường trải qua quá trình thiết lập TCP, trao đổi thông tin ASN/khả năng, chuyển sang trạng thái **Established** rồi truyền thông điệp cập nhật và keepalive. Khi kết nối hoặc peer mất ổn định, phiên có thể **Down**, các route học qua phiên đó có thể bị rút sau khi hệ thống phát hiện sự cố và cập nhật.

~~~mermaid
flowchart LR
    A["Tunnel/attachment sẵn sàng"] --> B["BGP session thiết lập"]
    B --> C["Established: trao đổi prefixes"]
    C --> D{"Đường hoặc peer gặp lỗi?"}
    D -- "Không" --> C
    D -- "Có" --> E["BGP Down / thu hồi learned routes"]
    E --> F["VPC và peer chọn route còn khả dụng"]
    F --> B
~~~

Chuyển đổi tuyến **không tức thời tuyệt đối**: có độ trễ phát hiện lỗi, xử lý BGP, lan truyền route và phản ứng của ứng dụng. Nếu đặt mục tiêu phục hồi chặt, cần kiểm thử tình huống mất một tunnel/attachment thực tế và đo từ góc nhìn người dùng.

## 3. Cloud Router và chế độ dynamic routing của VPC

### 3.1. Regional hay global?

VPC có thuộc tính **dynamic routing mode**. Đây là quyết định ở **cấp VPC network** và ảnh hưởng đến cách áp dụng dynamic routes, cũng như phạm vi subnet mà Cloud Router quảng bá trong chế độ mặc định.

| Chế độ | Ý nghĩa khái quát | Ví dụ ảnh hưởng |
| --- | --- | --- |
| **Regional dynamic routing** | Route động học qua Cloud Router ở một region được áp dụng trong phạm vi region đó theo quy tắc Google Cloud. Quảng bá subnet mặc định tập trung vào các subnet của region tương ứng. | VPC có workload ở Singapore và Tokyo, nhưng kết nối hybrid tại Singapore: workload ở Tokyo không mặc nhiên sử dụng route học tại Singapore. |
| **Global dynamic routing** | Route động học ở một region có thể được dùng bởi các region khác trong cùng VPC. Quảng bá mặc định có thể bao gồm subnet từ các region trong VPC theo quy tắc của global mode. | Workload ở nhiều region có thể sử dụng kết nối hybrid đặt tại Singapore, nếu thiết kế route, firewall và năng lực đường truyền cho phép. |

Với global mode, việc chọn giữa route cùng region và route từ region khác còn bị chi phối bởi quy tắc ưu tiên và **chi phí liên vùng** trong cơ chế dynamic routing của Google Cloud. Global **không có nghĩa mọi route có cùng ưu tiên** hoặc mọi traffic luôn đi qua kết nối gần nhất theo địa lý.

Sơ đồ minh họa:

~~~text
VPC retail-vpc
  asia-southeast1: 10.40.0.0/20 (Cloud Router kết nối on-premises)
  asia-northeast1: 10.50.0.0/20 (workload dự phòng)

On-premises: 172.20.0.0/16

REGIONAL: route học ở asia-southeast1 có phạm vi sử dụng theo region.
GLOBAL:  route học ở asia-southeast1 có thể có hiệu lực trên nhiều region.
~~~

Chuyển routing mode là **thay đổi phạm vi mạng**, có thể ảnh hưởng đến cả ứng dụng, firewall và lựa chọn đường đi. Không thay từ `REGIONAL` sang `GLOBAL` chỉ để xử lý một trường hợp mất kết nối mà chưa đánh giá các route đang được học và chi phí/độ trễ khi đi liên vùng.

### 3.2. Kiểm tra routing mode

Các lệnh sau là **read-only**:

~~~bash
PROJECT_ID="retail-prod"
NETWORK="retail-vpc"

gcloud compute networks describe "$NETWORK" \
  --project="$PROJECT_ID" \
  --format="yaml(name,autoCreateSubnetworks,routingConfig)"
~~~

Kết quả minh họa:

~~~yaml
name: retail-vpc
routingConfig:
  routingMode: GLOBAL
~~~

Mạng thực tế có thể có trường bổ sung. Nếu dùng **Shared VPC**, hãy kiểm tra cấu hình network trong **host project** của VPC, không nhầm với project chỉ chạy Compute Engine/GKE/Cloud Run.

### 3.3. Default advertisement và custom advertisement

Trong **default advertisement mode**, Cloud Router quảng bá các prefix subnet của VPC dựa trên dynamic routing mode. Một số kiến trúc cần **custom advertised routes** để:

- Chỉ quảng bá những prefix đã được phê duyệt.
- Quảng bá thêm những dải đặc thù mà kiến trúc mạng yêu cầu.
- Áp dụng lựa chọn riêng ở cấp router hoặc cấp BGP peer khi công cụ hỗ trợ.

Khi dùng custom advertisement, phải hiểu rõ cấu hình có còn bao gồm nhóm **all subnets** hay không. Có thể vô tình ngừng quảng bá subnet đang phục vụ production nếu chỉ để lại một dải custom. Quảng bá prefix không có đường đi thực tế cũng có thể tạo **blackhole** ở mạng peer.

Chẳng hạn, nếu một phía quảng bá route mặc định `0.0.0.0/0`, đó là một quyết định lớn: nó có thể kéo lưu lượng rộng hơn dự kiến qua VPN/Interconnect. Chỉ làm như vậy khi thiết kế có đường egress, firewall, NAT và phương án dự phòng tương ứng. Không coi default route là cách nhanh để tránh khai báo các prefix cần thiết.

## 4. BGP route selection, ưu tiên và dự phòng

### 4.1. Nhiều đường tới cùng một prefix

Trong thiết kế production, doanh nghiệp thường có hai đường hybrid độc lập. Nếu cả hai peer quảng bá `172.20.0.0/16`, Cloud Router có thể học cùng prefix từ nhiều phiên BGP:

~~~text
Peer A qua tunnel A: 172.20.0.0/16
Peer B qua tunnel B: 172.20.0.0/16
~~~

Khi nhiều route cạnh tranh, Google Cloud áp dụng quy tắc route selection, phạm vi region, prefix specificity và priority có hiệu lực. Các thuộc tính như **MED** (*Multi-Exit Discriminator*) có thể tham gia vào lựa chọn, nhưng không phải mọi thiết bị và mọi hướng traffic đều sử dụng giống nhau. Một prefix cụ thể hơn thường có thể chi phối đường đi so với prefix rộng hơn, nên không nên phân tích chỉ bằng MED.

Nếu thiết kế active/active, cần kiểm tra liệu đường truyền và workload có chấp nhận traffic qua cả hai đường. Nếu thiết kế active/passive, phải thiết lập ưu tiên và thử chuyển sang đường dự phòng. **Không bảo đảm đường đi hai chiều đối xứng** chỉ vì cấu hình hai BGP peers giống nhau: chiều từ on-premises tới Google và chiều ngược lại do hai bên lựa chọn route.

### 4.2. Không phải cứ có hai tunnel là đạt HA

HA VPN sử dụng các tunnel cùng BGP sessions để cung cấp phương án dự phòng theo topology hỗ trợ. Tuy nhiên cần xét:

1. Hai tunnel có nằm trên những VPN gateway interface và kết nối độc lập theo thiết kế HA không?
2. Router/VPN gateway phía doanh nghiệp có đường dự phòng phù hợp không?
3. Mỗi tunnel có BGP session riêng, địa chỉ peer đúng và quảng bá đủ prefix không?
4. Các route có được rút/chọn lại sau sự cố không?
5. Firewall, thiết bị, DNS và ứng dụng có tiếp tục làm việc sau khi đổi đường không?

Với Interconnect, dự phòng còn liên quan đến số kết nối, vị trí kết nối, attachment, router của doanh nghiệp và nhóm failure domain. **SLA có thể phụ thuộc topology đủ điều kiện**, không tự sinh ra chỉ vì tạo thêm một Cloud Router.

### 4.3. Kiểm tra hướng quay về

Ví dụ VM `10.40.1.10` gọi ERP `172.20.10.15`:

~~~text
Google → on-prem:
  VM 10.40.1.10 → route tới 172.20.10.0/24 → tunnel A/B → ERP

On-prem → Google:
  ERP 172.20.10.15 → route tới 10.40.0.0/20 → tunnel A/B → VM
~~~

Cả hai phía phải có route trả lời. Nếu on-premises không nhận prefix `10.40.0.0/20`, gói có thể tới ERP nhưng kết nối vẫn timeout vì không có đường quay về. Nếu có nhiều firewall stateful hoặc NAT, asymmetric routing còn có thể khiến gói phản hồi bị chặn dù route tồn tại.

## 5. Chuẩn bị trước khi cấu hình Cloud Router

### 5.1. Bảng thông số thiết kế

Trước khi viết Terraform hoặc chạy `gcloud`, chuẩn bị một bảng tương tự:

| Thông số | Ví dụ | Vì sao cần rõ |
| --- | --- | --- |
| Project / VPC | `retail-prod` / `retail-vpc` | Đúng phạm vi tài nguyên và IAM. |
| Region | `asia-southeast1` | Cloud Router và kết nối được hỗ trợ gắn với region. |
| Dynamic routing mode | `REGIONAL` hoặc `GLOBAL` | Xác định khả năng dùng route giữa các region. |
| Local / peer ASN | `65010` / `65020` | eBGP cần ASN phù hợp và không xung đột. |
| VPC subnets | `10.40.0.0/20`, `10.40.16.0/20` | Dải cần quảng bá tới mạng doanh nghiệp. |
| On-prem prefixes | `172.20.10.0/24`, `172.20.20.0/24` | Dải Google Cloud cần học. |
| HA VPN / VLAN attachments | `tunnel-a`, `tunnel-b` | Đường truyền dữ liệu và failure domain. |
| BGP link IPs | `169.254.21.1/30 ↔ 169.254.21.2/30` | Cặp IP cho một phiên BGP; mỗi phiên độc lập cần cặp phù hợp. |
| Traffic được phép | Ví dụ TCP 443 tới ERP API, TCP 5432 tới database nếu ứng dụng thật cần. | Route không thay thế firewall hay authentication. |
| SLO và giám sát | Kết nối ERP thành công; cảnh báo peer down. | Đo chất lượng từ hệ thống sử dụng, không chỉ trạng thái router. |

Các giá trị ví dụ không phải hướng dẫn cấp dải mạng cho sản xuất. Trước khi triển khai, kiểm tra **CIDR không trùng lặp**, cấu hình VLAN/tunnel có sẵn, tài nguyên cùng region theo yêu cầu, dải IP BGP được phép, quota và khả năng hỗ trợ của thiết bị đối tác.

### 5.2. Tránh trùng dải địa chỉ

Giả sử on-premises có dải `10.40.0.0/16` trong khi VPC cũng sử dụng `10.40.0.0/16`. BGP không thể tự giải quyết việc hai đầu cùng sở hữu một khoảng IP: route có thể bị ưu tiên sai hoặc không thể xác định đích mong muốn.

Nên xây **IP address plan** toàn tổ chức, bao gồm các subnet VPC, subnet on-premises, dải được quảng bá, môi trường dự phòng và những mạng kết nối qua VPN/Interconnect. Nếu không thể thay CIDR, cần đánh giá phương án dịch địa chỉ/migration được hỗ trợ và hạn chế của ứng dụng, thay vì chỉ tăng priority BGP.

### 5.3. Độ sâu bảo mật cần có

Cloud Router cần quyền quản trị tài nguyên Google Cloud phù hợp để cấu hình; thiết bị đối tác cần quy trình quản trị BGP riêng. Quyền thay đổi route có tác động rộng, nên phân tách danh tính tạo hạ tầng với runtime service account của ứng dụng.

Để cho phép ERP API qua kết nối hybrid, vẫn cần **firewall ingress/egress**, DNS nội bộ, chứng chỉ TLS và cơ chế authentication của ERP. Nếu ứng dụng truy cập **Google APIs** như Cloud Storage hoặc Secret Manager, đó là đường kết nối khác với phiên BGP tới on-premises; cần kiểm tra Private Google Access/egress, IAM và thông số dịch vụ tương ứng.

## 6. Kiến trúc Cloud Router với HA VPN

### 6.1. Các thành phần và luồng thiết lập

Một thiết kế HA VPN thường gồm:

1. **VPC** chứa workload và subnet.
2. **HA VPN gateway** của Google Cloud.
3. **External VPN gateway/thiết bị on-premises** và các đường kết nối cần thiết.
4. **Các VPN tunnels** với thông số IPsec phù hợp.
5. **Cloud Router** cùng region và các **interface** liên kết với tunnel.
6. **BGP peers** cho từng tunnel để học/quảng bá các prefix.

~~~mermaid
flowchart LR
    subgraph DC["On-premises"]
      P1["VPN/router peer A"]
      P2["VPN/router peer B"]
    end
    subgraph GC["Google Cloud"]
      GW["HA VPN gateway"]
      T1["Tunnel A"]
      T2["Tunnel B"]
      CR["Cloud Router"]
      NET["VPC retail-vpc"]
      GW --- T1
      GW --- T2
      T1 -. "BGP peer A" .-> CR
      T2 -. "BGP peer B" .-> CR
      CR -. "Dynamic routes" .-> NET
    end
    P1 <-- "IPsec A" --> T1
    P2 <-- "IPsec B" --> T2
~~~

Đây là sơ đồ logic; khi triển khai cần theo đúng topology hỗ trợ của **Cloud VPN** về interface, peer gateway, số tunnel và khả năng đáp ứng HA/SLA. Một Cloud Router có thể quản lý nhiều phiên BGP, nhưng không nên hiểu nó là một thiết bị truyền gói riêng cho mỗi tunnel.

### 6.2. Điều gì xảy ra khi một tunnel hỏng?

Giả sử hai tunnel đều có kết nối tới `172.20.0.0/16`. Khi tunnel A mất kết nối, BGP session A có thể ngừng hoạt động và những route chỉ được học từ A bị rút. Nếu B tiếp tục quảng bá prefix hợp lệ và VPC route selection cho phép, traffic có thể được đưa qua B. Điều này còn phụ thuộc cấu hình on-premises để chiều quay về cũng sử dụng được B.

Không thiết kế ứng dụng với giả định kết nối sẽ **không mất packet nào** trong lúc failover. Đối với tác vụ gọi API và truy cập database, cần timeout, retry có kiểm soát, idempotency và kế hoạch xử lý giao dịch bị gián đoạn.

## 7. Cloud Router với Dedicated/Partner Interconnect

Trong phương án Interconnect, **VLAN attachment** kết nối môi trường on-premises với VPC và sử dụng BGP qua Cloud Router. Cloud Router học/quảng bá prefix qua interface gắn với attachment; traffic thực tế đi qua kết nối Interconnect.

| Khía cạnh | HA VPN | Dedicated/Partner Interconnect |
| --- | --- | --- |
| Kết nối dữ liệu | IPsec tunnel qua nền tảng VPN được hỗ trợ. | Kết nối qua hạ tầng Interconnect/đối tác và VLAN attachment. |
| Vai trò BGP | Trao đổi route trên các BGP peers gắn với VPN tunnel. | Trao đổi route trên peers gắn với VLAN attachment. |
| Thiết kế dự phòng | Dựa vào gateway interfaces, tunnel và thiết bị đối tác theo topology HA. | Dựa vào kết nối/attachment/vị trí và router on-premises theo topology dự phòng. |
| Mã hóa | VPN cung cấp IPsec cho tunnel. | Không mặc định xem mọi kết nối Interconnect là IPsec; nếu cần mã hóa, đánh giá giải pháp được hỗ trợ như HA VPN over Cloud Interconnect. |
| Khả năng chọn | Khi cần VPN linh hoạt hoặc phù hợp nhu cầu lưu lượng. | Khi cần phương án kết nối theo yêu cầu băng thông, độ trễ, độ ổn định và hiện diện mạng của doanh nghiệp. |

Không có quy tắc “Interconnect luôn nhanh hơn VPN trong mọi trường hợp”. Hiệu năng phụ thuộc địa lý, thiết bị, capacity, độ tải, đường đi thực tế và kiến trúc đối tác. Quyết định nên dựa trên đo lường, nhu cầu bảo mật, tính sẵn sàng và tổng chi phí.

## 8. Thao tác với Cloud Router bằng gcloud

Các ví dụ sau sử dụng giá trị mẫu. **Lệnh `list`, `describe`, `get-status` là thao tác đọc. Lệnh `create`, `add-interface`, `add-bgp-peer` tạo hoặc thay đổi cấu hình thật.** Chỉ chạy nhóm lệnh ghi trong project thử nghiệm hoặc theo kế hoạch hạ tầng đã được phê duyệt, khi HA VPN tunnel/Interconnect attachment và phía on-premises đã sẵn sàng.

### 8.1. Khảo sát VPC và Cloud Routers

~~~bash
PROJECT_ID="retail-prod"
REGION="asia-southeast1"
NETWORK="retail-vpc"
ROUTER="cr-retail-hybrid"

# Xem dynamic routing mode hiện tại của VPC.
gcloud compute networks describe "$NETWORK" \
  --project="$PROJECT_ID" \
  --format="yaml(name,routingConfig)"

# Liệt kê Cloud Routers trong project.
gcloud compute routers list \
  --project="$PROJECT_ID" \
  --format="table(name,region.basename(),network.basename(),bgp.asn)"

# Xem cấu hình interface, BGP peer và quảng bá route.
gcloud compute routers describe "$ROUTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"

# Xem BGP peers và các route trạng thái hiện tại.
gcloud compute routers get-status "$ROUTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml"
~~~

Trong `describe`, chú ý `bgp.asn`, `interfaces`, `bgpPeers` và cấu hình advertised routes. Trong `get-status`, chú ý trạng thái từng BGP peer, prefix đã học, những route được chọn và các thông tin trạng thái mà API thực sự trả về. Tên field cụ thể có thể thay đổi theo định dạng và phiên bản CLI; dùng `--format=yaml`/`json` để đọc cấu trúc trước khi lọc cột.

### 8.2. Ví dụ tạo Cloud Router

~~~bash
# Lệnh ghi minh họa; VPC retail-vpc cần đã tồn tại.
gcloud compute routers create cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --network=retail-vpc \
  --asn=65010
~~~

Tạo Cloud Router **chưa tự thiết lập đường hybrid**. Để BGP thực sự hoạt động cần interface/BGP peer gắn với **tunnel hoặc VLAN attachment đã cấu hình**, có địa chỉ phiên BGP, ASN tương thích và cấu hình phía đối tác.

### 8.3. Gắn interface và BGP peer cho tunnel đã tồn tại

Giả sử tổ chức **đã tạo** VPN tunnel tên `tunnel-retail-a` và phía on-premises cấu hình IP BGP `169.254.21.2`, ASN `65020`:

~~~bash
# Lệnh ghi: dùng khi tunnel/region/IP pair đã được xác minh.
gcloud compute routers add-interface cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --interface-name=if-retail-a \
  --vpn-tunnel=tunnel-retail-a \
  --ip-address=169.254.21.1 \
  --mask-length=30

# Tạo BGP peer cho interface vừa liên kết.
gcloud compute routers add-bgp-peer cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --peer-name=peer-retail-a \
  --interface=if-retail-a \
  --peer-ip-address=169.254.21.2 \
  --peer-asn=65020
~~~

`if-retail-a` và `peer-retail-a` chỉ là tên định danh của ví dụ. Hai IP phải tạo cặp BGP hợp lệ theo yêu cầu tunnel và không xung đột với các phiên khác. Lệnh trên không tạo VPN tunnel, không thiết lập IKE/IPsec ở thiết bị on-premises và không hoàn thiện topology HA. Đường B thông thường cần interface và peer riêng với IP pair khác, ví dụ `169.254.22.1/30` và `169.254.22.2/30`.

Với **Interconnect VLAN attachment**, giao diện Cloud Router dùng phương án liên kết attachment tương ứng thay cho `--vpn-tunnel`. Không lấy nguyên các lệnh HA VPN để cấu hình Interconnect.

### 8.4. Xác minh sau khi cấu hình

~~~bash
gcloud compute routers describe cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="yaml"

gcloud compute routers get-status cr-retail-hybrid \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format="yaml"
~~~

Các yếu tố cần đối chiếu:

1. **BGP session:** peer nào đang hoạt động, peer nào chưa `Established`/`UP` theo phản hồi của API.
2. **Learned routes:** on-premises có quảng bá đúng `172.20.10.0/24`, `172.20.20.0/24` không?
3. **Advertised routes:** Cloud Router có quảng bá những VPC subnet mà on-premises cần trả lời không?
4. **Effective routes:** các route học có được sử dụng tại region của VM cần liên lạc hay không?
5. **Data plane:** traffic ứng dụng từ đúng VM/pod đến đúng IP/port có hoạt động không; chiều phản hồi có đường về không?

Không dựa duy nhất vào `gcloud compute routes list` để kết luận về **mọi dynamic routes có hiệu lực**; dùng trạng thái Cloud Router và phương pháp kiểm tra effective routes tương ứng với VPC/tài nguyên theo công cụ hiện hành. Bảng route bên trong hệ điều hành guest VM cũng không nhất thiết hiển thị đầy đủ cách Google Cloud VPC chọn dynamic routes.

### 8.5. Mẫu thông tin trạng thái để đọc

Ví dụ giả định:

~~~yaml
bgpPeers:
  - name: peer-retail-a
    localAsn: 65010
    peerAsn: 65020
    status: UP
    learnedPrefixes:
      - 172.20.10.0/24
      - 172.20.20.0/24
  - name: peer-retail-b
    localAsn: 65010
    peerAsn: 65020
    status: UP
    learnedPrefixes:
      - 172.20.10.0/24
      - 172.20.20.0/24
~~~

Đây là **mẫu diễn giải logic**, không phải cam kết schema JSON/YAML nguyên văn của `gcloud compute routers get-status`. Khi viết script giám sát, hãy dùng field thực tế của Cloud Router API/CLI và có xử lý trạng thái thiếu dữ liệu, không cắt chuỗi từ ví dụ trình bày này.

## 9. Kết nối hybrid không chỉ có BGP

### 9.1. DNS và IP routing giải quyết hai việc khác nhau

Nếu ứng dụng Cloud Run qua VPC cần gọi `erp.corp.example`, cần trả lời:

- **DNS:** tên này được phân giải thành địa chỉ nào? Cloud DNS forwarding, inbound policy hoặc private zone có được thiết kế hợp lệ giữa các môi trường?
- **Routing:** prefix chứa IP đó có được quảng bá qua BGP và áp dụng tới VPC/region của workload?
- **Firewall:** các IP nguồn và đích, giao thức và cổng được cho phép ở cả hai phía chưa?
- **Ứng dụng:** endpoint, TLS, token, timeout và database credentials có đúng không?

BGP không trao đổi các bản ghi DNS, còn DNS trả về địa chỉ đúng không đồng nghĩa đã có route.

### 9.2. IAM, VPC firewall và dữ liệu

Cloud Router dùng cơ chế quản trị tài nguyên Google Cloud và quyền thích hợp cho quản trị viên; BGP hoạt động giữa thiết bị mạng. Sau khi đường kết nối hybrid sẵn sàng:

- **VPC firewall** vẫn kiểm soát traffic đến VM/tài nguyên phù hợp.
- Ứng dụng trên **GKE** có thể còn chịu chính sách Kubernetes/NetworkPolicy và cơ chế danh tính.
- **Cloud Run** cần được cấu hình đúng chế độ VPC egress để traffic tới địa chỉ on-premises dùng đường hybrid; không tự suy rằng mọi request của Cloud Run đều qua VPC.
- **Cloud SQL** có các lựa chọn kết nối riêng và xác thực database; việc học route tới on-premises không thay thế cấu hình Cloud SQL private IP/connector.
- Truy cập **Cloud Storage** và **Google APIs** cần đường Google API phù hợp cùng IAM, khác với việc học prefix ERP nội bộ.

Không áp dụng role `Owner` hoặc mở cổng rộng chỉ để che đi lỗi route. Tách từng lớp chẩn đoán giúp giải quyết nguyên nhân gốc và giữ nguyên tắc quyền tối thiểu.

## 10. Tình huống triển khai: từ retail VPC đến ERP on-premises

### 10.1. Yêu cầu

Doanh nghiệp bán lẻ có:

- **VPC `retail-vpc`**, subnet ứng dụng `10.40.0.0/20`, subnet dữ liệu `10.40.16.0/20`.
- **ERP on-premises** tại `172.20.10.0/24`, hệ thống kho tại `172.20.20.0/24`.
- Workload **Compute Engine/GKE** cần truy cập một API ERP qua HTTPS.
- Backend **Cloud Run** có một luồng xử lý phải kết nối VPC rồi đi đến ERP.
- Dữ liệu giao dịch Google Cloud nằm ở **Cloud SQL**; file lưu trong **Cloud Storage**.
- Mục tiêu vận hành: không mất kết nối lâu khi một VPN tunnel gặp lỗi; đội vận hành theo dõi được trạng thái BGP và chi phí đường truyền.

Các CIDR chỉ dùng để minh họa, đã được giả định **không trùng lặp**.

### 10.2. Thiết kế đề xuất

| Hạng mục | Thiết kế | Lý do |
| --- | --- | --- |
| Cloud Router | Một Cloud Router trong `asia-southeast1`, ASN `65010`. | Quản lý BGP peers trong region kết nối hybrid. |
| Thiết bị on-premises | ASN `65020`, có thiết kế VPN redundancy. | Tách ASN và cho phép học/quảng bá động. |
| Đường truyền | HA VPN hai tunnel theo topology được hỗ trợ. | Có phương án thay đường khi một tunnel mất. |
| Phiên BGP | Mỗi tunnel một peer và cặp IP link-local riêng. | Theo dõi và rút route theo từng kết nối. |
| Prefix Google quảng bá | Những VPC subnet cần on-premises quay về. | Tránh on-premises không có route phản hồi. |
| Prefix on-premises quảng bá | `172.20.10.0/24`, `172.20.20.0/24`. | Giới hạn đích được học theo nhu cầu. |
| Dynamic routing mode | Chọn `REGIONAL` nếu chỉ dùng kết nối tại region; cân nhắc `GLOBAL` khi workload multi-region cần dùng route. | Tránh vô tình mở rộng đường đi liên vùng và tăng độ trễ/chi phí. |
| DNS | Phân giải `erp.corp.example` tới IP nội bộ ERP bằng phương án DNS hybrid phù hợp. | Không phụ thuộc vào IP hard-code trong ứng dụng. |
| Firewall và identity | Chỉ mở cổng/dải đã được yêu cầu; giữ IAM/service account độc lập. | Giảm bề mặt tấn công. |
| Giám sát | Trạng thái BGP, VPN tunnel, route và tỷ lệ kết nối ERP thành công. | Sự cố control plane và sự cố ứng dụng cần phát hiện riêng. |

### 10.3. Luồng một request

~~~mermaid
sequenceDiagram
    participant APP as Workload trong VPC
    participant DNS as DNS hybrid
    participant ROUTE as VPC routing
    participant VPN as HA VPN tunnel
    participant ERP as ERP on-premises
    APP->>DNS: erp.corp.example?
    DNS-->>APP: 172.20.10.15
    APP->>ROUTE: TCP 443 tới 172.20.10.15
    Note over ROUTE: Prefix 172.20.10.0/24 được học qua BGP
    ROUTE->>VPN: Gửi qua route động được chọn
    VPN->>ERP: Chuyển request
    ERP-->>VPN: Phản hồi theo route tới VPC
    VPN-->>APP: Phản hồi qua mạng Google Cloud
~~~

Request chỉ thành công khi các đường đi ở hai chiều hoạt động, firewall cho phép, ERP đang phục vụ và TLS/xác thực phù hợp. Khi một tunnel hỏng, hệ thống cần kiểm thử rằng BGP rút route cũ và chọn được đường còn lại. Đội ứng dụng vẫn phải xử lý timeout và retry trong thời gian hội tụ.

### 10.4. Kịch bản diễn tập failover

1. Ghi nhận trạng thái bình thường của cả hai BGP sessions, learned prefixes và tỷ lệ request ERP thành công.
2. Trong môi trường test/diễn tập được phê duyệt, mô phỏng mất một đường kết nối theo phương án an toàn.
3. Quan sát tunnel state, BGP session state, learned/best routes và thời gian ứng dụng bắt đầu thành công trở lại.
4. Kiểm tra chiều đi/về, DNS và firewall; đo tác động tới các giao dịch đang mở.
5. Khôi phục đường kết nối, xác nhận route trở về trạng thái dự kiến và không tạo vòng lặp hoặc kết nối bị lệch.
6. Ghi nhận bài học cho runbook, cảnh báo, capacity và quy trình thay đổi hạ tầng.

Thời gian phục hồi đo được là số liệu của **kiến trúc triển khai**, không nên gán cho một Cloud Router riêng lẻ nếu chưa có số liệu và điều khoản tương ứng.

## 11. Sự cố thường gặp và cách khoanh vùng

| Dấu hiệu | Khả năng | Cách kiểm tra ưu tiên |
| --- | --- | --- |
| BGP peer không lên | Tunnel/attachment chưa hoạt động, sai ASN, sai cặp BGP IP, interface chưa gắn đúng hoặc phía đối tác chưa cấu hình. | `describe` router/tunnel, `get-status`, kiểm tra BGP config ở peer. |
| BGP `UP` nhưng thiếu prefix nội bộ | On-premises chưa advertise, policy/filter BGP chặn, route bị loại hoặc vượt giới hạn. | Kiểm tra advertised routes ở on-premises và learned routes trên Cloud Router. |
| On-premises không thấy subnet VPC | Cloud Router default/custom advertisement không gồm prefix; sai routing mode hoặc BGP policy. | Kiểm tra `describe` và route nhận được tại peer. |
| VM region khác không tới on-premises | VPC ở regional mode, route động không có hiệu lực ở region đó. | Đọc `routingConfig.routingMode`; đối chiếu effective routes. |
| Có route nhưng `curl` timeout | Firewall, ACL, NAT, thiếu route chiều về, ERP down hoặc asymmetric routing. | Kiểm tra từng chiều, cổng và logs mạng/ứng dụng. |
| Tên nội bộ không phân giải | Cloud DNS/on-prem DNS forwarding chưa thiết lập. | Kiểm tra resolver, DNS zones, forwarding rules. |
| Một tunnel hỏng thì ứng dụng ngừng | Thiếu peer/route dự phòng hoặc đường dự phòng không thực sự hoạt động. | Kiểm tra trạng thái BGP A/B và diễn tập chuyển đường. |
| Một prefix bị “mất” sau thay đổi advertisement | Custom advertisement vô tình bỏ subnet hoặc quảng bá prefix sai. | So sánh cấu hình trước/sau và danh sách prefixes trên peer. |
| Traffic đi qua region xa hơn dự kiến | Routing mode global, route priority, prefix specificity hoặc chính sách peer không như mong muốn. | Xem route selection và đo RTT, egress/cost thực tế. |
| Truy cập Google API báo `403` | Thiếu IAM/token hoặc kiểm soát API; chưa chắc liên quan BGP. | Kiểm tra danh tính, IAM và đường tới Google API. |

### 11.1. Quy trình điều tra theo từng lớp

**Lớp 1 — Kết nối:** VPN tunnel hoặc Interconnect VLAN attachment có đang hoạt động? Thiết bị peer có kết nối tới Google như thiết kế không?

**Lớp 2 — BGP:** Session có `UP/Established`? ASN, BGP IP, interface và peer có khớp nhau? Có nhận đúng prefixes không?

**Lớp 3 — VPC route:** Learned route có được sử dụng trong region của workload? Có prefix cụ thể hơn hoặc policy khiến route khác được chọn không?

**Lớp 4 — Chiều về:** Router on-premises có biết CIDR của subnet Google Cloud? Có NAT hoặc stateful firewall làm thất bại phản hồi không?

**Lớp 5 — DNS và bảo mật:** Hostname có phân giải đúng IP? Firewall cho phép protocol/port? Identity và certificate của ứng dụng có đúng không?

**Lớp 6 — Nghiệp vụ:** Nếu TCP/TLS thành công nhưng ứng dụng lỗi, đối chiếu HTTP status, database credentials, timeout, retry, quota và logs của workload.

Đừng sửa BGP route khi bằng chứng chỉ ra một lỗi DNS hoặc IAM. Thay đổi route có thể ảnh hưởng nhiều dịch vụ khác cùng sử dụng kết nối hybrid.

## 12. Quan sát độ tin cậy, tự động hóa và chi phí

### 12.1. Tín hiệu cần theo dõi

- Trạng thái từng **BGP peer** và **VPN tunnel/Interconnect attachment**.
- Tập prefix được **advertise/learn** và những thay đổi khác thường.
- Traffic, packet loss, latency hoặc sự cố trên đường kết nối, theo metrics có sẵn.
- SLI ở tầng ứng dụng như tỷ lệ **ERP request thành công** và độ trễ p95/p99.
- Sự kiện đổi cấu hình network, router, firewall, DNS hoặc policy.

Cloud Monitoring và logs của dịch vụ hỗ trợ quan sát kỹ thuật; SLO của ứng dụng cần đo thêm từ workload thực. Một peer vẫn `UP` trong khi ERP API trả `500` thì người dùng vẫn gặp sự cố.

### 12.2. Quản lý cấu hình bằng mã

Khi có nhiều VPC và region, cấu hình Cloud Router, interfaces, BGP peers, quảng bá route, tunnel/attachments và policy nên được quản lý có kiểm soát bằng **Terraform** hoặc công cụ hạ tầng dưới dạng mã phù hợp. Một thay đổi BGP có thể ảnh hưởng cả Google Cloud và thiết bị on-premises, nên quy trình phát hành cần:

1. Xác định chủ sở hữu mạng ở hai phía và lịch triển khai.
2. Review thay đổi CIDR, ASN, advertisement, priority và region.
3. Kiểm tra kế hoạch trước khi áp dụng; có phương án khôi phục.
4. Giám sát trạng thái BGP và ứng dụng ngay sau thay đổi.
5. Cập nhật sơ đồ, runbook và danh sách prefix được phép.

Cloud Router tự động cập nhật tuyến theo thông tin BGP, nhưng không thay thế việc quản lý **configuration drift** hoặc kiểm soát thay đổi chủ động.

### 12.3. Các khoản chi phí cần tính

Cloud Router là thành phần control plane; chi phí giải pháp hybrid còn gắn với **VPN tunnels, Cloud Interconnect connections/VLAN attachments, lưu lượng dữ liệu, truyền liên vùng và dịch vụ mạng liên quan** theo bảng giá/điều khoản hiện hành. Nếu routing mode global khiến ứng dụng đi tới kết nối ở region xa hơn, cần tính thêm độ trễ và khả năng phát sinh chi phí. Log, metrics, kết nối dự phòng và capacity cũng cần có ngân sách.

Không kết luận “BGP dynamic route miễn phí nên kết nối hybrid miễn phí” hoặc “thêm peer là luôn đạt SLA cao hơn”. Tổng chi phí và độ tin cậy phải dựa trên **topology, traffic đo được, cấu hình redundancy và các điều khoản dịch vụ**.

## 13. Bài tập thực hành

### Bài 1 — Phân biệt control plane và data plane

Một Cloud Router đã có BGP session `UP`, nhưng API ERP từ VM vẫn không phản hồi. Hãy nêu bốn nguyên nhân ngoài BGP và cách kiểm tra.

**Gợi ý:** firewall, route chiều về, DNS, ứng dụng ERP/TLS. Cloud Router không chuyển gói dữ liệu trực tiếp như một proxy.

### Bài 2 — Regional và global

VPC có VM ở `asia-southeast1` và `asia-northeast1`; chỉ có Cloud Router ở `asia-southeast1` học prefix `172.20.0.0/16`. Trong **regional mode**, điều gì cần xem xét nếu VM Tokyo phải gọi hệ thống này? Nếu chuyển sang **global mode**, những tác động nào cần kiểm thử?

**Gợi ý:** phạm vi dynamic routes, route selection, độ trễ, firewall, đường trả về và chi phí liên vùng.

### Bài 3 — Chẩn đoán route bị thiếu

Cloud Router peer `UP`, nhưng không học prefix `172.20.20.0/24`. Hãy nêu trình tự điều tra ngắn.

**Gợi ý:** kiểm tra peer on-premises có quảng bá prefix hay không, BGP policy/filter, giới hạn route, session được kết nối đúng và danh sách learned routes qua `get-status`.

### Bài 4 — Thiết kế BGP redundancy

Với hai VPN tunnels, hãy thiết kế hai BGP peers có cặp IP link-local riêng. Giải thích vì sao hai peer quảng bá cùng một mạng không tự bảo đảm failover đạt SLO.

**Gợi ý:** hai hướng route, trạng thái tunnel, policy ưu tiên, failure domain, thời gian hội tụ và test request từ ứng dụng.

### Bài 5 — Chọn công cụ phù hợp

Với các yêu cầu sau, chọn thành phần chính:

| Yêu cầu | Thành phần phù hợp |
| --- | --- |
| Trao đổi CIDR on-premises và VPC động. | Cloud Router + BGP trên VPN/Interconnect được hỗ trợ. |
| Đường truyền IPsec giữa hai hệ thống. | HA VPN. |
| Phân giải `erp.corp.example` thành IP nội bộ. | Cơ chế DNS hybrid, ví dụ Cloud DNS forwarding thích hợp. |
| Chặn TCP tới một VM. | Firewall/policy ở những lớp tương ứng. |
| Cấp quyền đọc Cloud Storage cho service account. | IAM của dịch vụ đích. |

## 14. Checklist thiết kế và tài liệu chính thức

| Câu hỏi thiết kế | Điều cần có trước khi triển khai |
| --- | --- |
| Đã kiểm tra CIDR hai phía? | Prefix không trùng lặp, có IP plan và danh sách mạng được quảng bá. |
| ASN và BGP peers hợp lệ? | Local/peer ASN đúng, link IP/interface tương ứng, không trùng giữa sessions. |
| Đường dữ liệu đã sẵn sàng? | HA VPN tunnel hoặc Interconnect attachment đúng topology và region. |
| Dynamic routing mode phù hợp? | Đã hiểu phạm vi regional/global và ảnh hưởng tới mọi workload trong VPC. |
| Advertisements chính xác? | Không thiếu subnet cần trả lời, không quảng bá dải quá rộng hoặc không có đường đi. |
| Có dự phòng? | Hai hoặc nhiều đường độc lập theo nhu cầu, đo được chuyển đường và khả năng quay về. |
| Firewall và DNS hoàn chỉnh? | Kiểm tra hostname, IP, route hai chiều, port, certificate và authentication. |
| Có giám sát? | Theo dõi peer/tunnel, traffic, learned routes, SLI ứng dụng và runbook sự cố. |
| Có governance? | IaC, review, IAM tối thiểu, người sở hữu cấu hình on-premises và cloud. |
| Có kế hoạch chi phí? | Dự toán VPN/Interconnect, truyền dữ liệu, dự phòng, quan sát và liên vùng. |

Nguồn tài liệu Google Cloud để đối chiếu kiến trúc và cú pháp mới nhất:

- [Cloud Router overview](https://cloud.google.com/network-connectivity/docs/router/concepts/overview)
- [Cloud Router BGP routes](https://cloud.google.com/network-connectivity/docs/router/concepts/bgp-routing)
- [Cloud Router advertised routes](https://cloud.google.com/network-connectivity/docs/router/concepts/advertised-routes)
- [Cloud Router best path selection](https://cloud.google.com/network-connectivity/docs/router/concepts/best-path-selection)
- [VPC dynamic routing mode](https://cloud.google.com/vpc/docs/vpc#dynamic-routing-mode)
- [HA VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [gcloud compute routers reference](https://cloud.google.com/sdk/gcloud/reference/compute/routers)

Điểm cốt lõi: **Cloud Router trao đổi thông tin route bằng BGP, còn VPN/Interconnect truyền gói tin**. Một thiết kế hybrid hoạt động ổn định cần đồng thời có prefix chính xác, route có hiệu lực ở đúng region, đường đi hai chiều, firewall/DNS phù hợp, giám sát và phương án dự phòng đã được thử nghiệm.
