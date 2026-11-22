# Thực hành nối mạng tại chỗ với VPC trên Google Cloud

> **Chương:** DNS và kết nối hybrid  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một doanh nghiệp đang có hệ thống quản lý đơn hàng trong trung tâm dữ liệu riêng (on-premises). Nhóm phát triển triển khai thêm dịch vụ API trên Compute Engine hoặc GKE tại Google Cloud, nhưng ứng dụng vẫn cần truy cập dữ liệu nội bộ qua địa chỉ IP riêng. Mục tiêu không chỉ là “ping được”: hai mạng cần có **đường truyền phù hợp, định tuyến hai chiều, firewall giới hạn, DNS phân giải đúng, cơ chế dự phòng, monitoring và phương án dọn dẹp**.

Bài thực hành này dẫn dắt cách thiết kế, cấu hình và xác minh kết nối **on-premises ↔ Google Cloud VPC** bằng **HA VPN, Cloud Router và BGP**; đồng thời giải thích cách mở rộng sang Cloud DNS và Cloud Interconnect. Các lệnh dưới đây mô tả một môi trường lab giả định. Chỉ thực hiện bước tạo/sửa tài nguyên khi có quyền trên **project thử nghiệm** và phối hợp với quản trị viên hệ thống on-premises.

## Mục tiêu học tập

Sau bài, người học có thể:

1. Vẽ được sơ đồ end-to-end của một kết nối hybrid và lập bảng thông số mạng trước khi triển khai.
2. Giải thích vai trò của VPC, subnet, HA VPN gateway, external peer VPN gateway, VPN tunnel, Cloud Router và BGP.
3. Tạo một VPC, hai tunnel HA VPN và hai BGP session theo cấu hình mẫu, phối hợp các thông số tương ứng với thiết bị on-premises.
4. Kiểm tra trạng thái tunnel, BGP, learned/advertised routes, firewall và luồng thử kết nối hai chiều.
5. Bổ sung DNS phân giải tên nội bộ theo hai hướng bằng Cloud DNS forwarding và inbound DNS forwarding.
6. Chẩn đoán được lỗi IP chồng lấn, IKE/IPsec, route, DNS, MTU và quy tắc bảo mật.
7. Biết khi nào nên cân nhắc Dedicated/Partner Interconnect, tối ưu khả năng phục hồi và quản lý chi phí.

## 1. Kịch bản lab và kết quả cần đạt

Giả định doanh nghiệp có một site on-premises với mạng ứng dụng **172.20.50.0/24**. Google Cloud có một VPC dành cho môi trường thử nghiệm, với subnet **10.20.10.0/24** trong một region. Một VM riêng tư trong VPC mang IP **10.20.10.10**; một máy on-premises mang IP **172.20.50.20**. Một DNS server on-premises dùng IP **172.20.50.53**.

~~~mermaid
flowchart LR
    subgraph DC["Trung tâm dữ liệu tại chỗ"]
        PC["Client 172.20.50.20"]
        DNS["DNS 172.20.50.53"]
        PEER["VPN/BGP peer\nASN 65010\n2 public interfaces"]
        PC --- PEER
        DNS --- PEER
    end

    subgraph GCP["Google Cloud project: hybrid-lab"]
        subgraph VPC["VPC: hybrid-lab-vpc"]
            HA["HA VPN gateway\nInterface 0 + 1"]
            CR["Cloud Router\nASN 64514"]
            VM["VM riêng tư\n10.20.10.10"]
            GCDNS["Cloud DNS private/forwarding zones"]
            HA --- CR
            CR -. "dynamic routes" .-> VM
            GCDNS -. "phân giải" .-> VM
        end
    end

    PEER ==>|"IPsec tunnel 0"| HA
    PEER ==>|"IPsec tunnel 1"| HA
~~~

Sơ đồ là **logic**, không cho rằng Cloud Router trực tiếp chuyển gói tin qua VM: Cloud Router là dịch vụ điều khiển và trao đổi tuyến BGP; **data plane** sử dụng các tuyến VPC và tunnel tương ứng.

**Kết quả mong đợi:**

- Hai tunnel HA VPN ở trạng thái hoạt động và hai BGP session được thiết lập theo cấu hình.
- Google Cloud học được route tới **172.20.50.0/24**; thiết bị on-premises học được **10.20.10.0/24**.
- Client ở site on-premises gọi được một dịch vụ thử nghiệm có IP **10.20.10.10**, chỉ qua cổng được phép.
- Nếu thực hành DNS nâng cao: máy GCP phân giải được tên **app.corp.example.internal** qua DNS on-premises; máy on-premises phân giải được tên **vm1.gcp.example.internal** qua inbound DNS forwarding.
- Khi cố ý làm một tunnel mất kết nối, lưu lượng có thể chuyển sang đường còn lại theo thiết kế; việc này được kiểm tra có giám sát, không mặc nhiên bảo đảm không mất gói trong quá trình hội tụ.

### 1.1. Bảng quy hoạch thông số

| Thành phần | Giá trị lab | Ghi chú |
|---|---|---|
| Google Cloud project | hybrid-lab-project | Thay bằng project được cấp quyền |
| Region / zone | asia-southeast1 / asia-southeast1-a | Chọn region có dịch vụ được hỗ trợ |
| VPC / subnet | hybrid-lab-vpc / cloud-lab-subnet | VPC global, subnet regional |
| VPC subnet CIDR | 10.20.10.0/24 | Dải ví dụ dùng riêng cho lab |
| VM thử nghiệm | hybrid-test-vm / 10.20.10.10 | Không cần external IP |
| On-premises subnet | 172.20.50.0/24 | Không chồng lấn bất kỳ subnet liên quan nào |
| On-premises client | 172.20.50.20 | Máy thật phải có route qua VPN gateway |
| On-premises DNS | 172.20.50.53 | Có khả năng trả lời các truy vấn được phép |
| Cloud Router ASN | 64514 | ASN riêng, khác ASN on-premises |
| On-premises peer ASN | 65010 | ASN riêng, thống nhất giữa hai đầu |
| On-premises VPN public IP #0 | 198.51.100.10 | Địa chỉ tài liệu, không định tuyến trên Internet |
| On-premises VPN public IP #1 | 198.51.100.11 | Địa chỉ tài liệu, thay bằng IP thật |
| BGP link-local #0/#1 | Tự cấp phát 169.254.x.x/30 | Ghi lại sau khi tạo Cloud Router interface |
| Cloud VPN public IP #0/#1 | Do Google Cloud cấp | Lấy sau khi tạo HA VPN gateway |
| DNS trên cloud | gcp.example.internal. | Private zone |
| DNS tại chỗ | corp.example.internal. | Forwarding zone |

Các địa chỉ **198.51.100.10/11** là địa chỉ dành cho **tài liệu**, không hoạt động như endpoint Internet thực tế. Khi thực hành có thiết bị thật, thay bằng **địa chỉ IPv4 public có thể liên lạc** của thiết bị/đường Internet on-premises. Tất cả CIDR khác là giá trị minh họa; chỉ dùng nếu **không xung đột với mạng hiện có**.

## 2. Chọn công nghệ kết nối trước khi cấu hình

| Giải pháp | Phù hợp với | Đặc điểm và đánh đổi |
|---|---|---|
| **HA VPN** | Lab, kết nối hybrid qua Internet, triển khai nhanh, lưu lượng vừa phải | IPsec mã hóa trên Internet, hai interface/tunnel và BGP để dự phòng |
| **Dedicated Interconnect** | Doanh nghiệp có yêu cầu thông lượng ổn định, kết nối vật lý trực tiếp ở địa điểm hỗ trợ | Cần thiết kế mạch, cơ sở hạ tầng và dự phòng, thời gian triển khai/phí khác VPN |
| **Partner Interconnect** | Kết nối riêng qua nhà cung cấp mạng đối tác | Phụ thuộc nhà cung cấp, VLAN attachment, Cloud Router, SLA và phương án bảo vệ dữ liệu |
| **HA VPN over Cloud Interconnect** | Cần đường truyền Interconnect đồng thời cần bảo vệ IPsec theo yêu cầu | Kết hợp các thành phần, cấu hình và chi phí phức tạp hơn |
| **Cloud VPN Classic** | Bài toán kế thừa cần định tuyến tĩnh | Ít thuận tiện cho thiết kế HA mới; HA VPN/BGP thường được ưu tiên |
| **HTTPS API công khai có xác thực** | Chỉ cần gọi một vài endpoint ứng dụng qua Internet | Không tạo kết nối mạng riêng giữa toàn bộ hai CIDR; có thể đủ với bài toán nhỏ |

Bài này dùng **HA VPN với BGP**, vì người học có thể quan sát rõ quá trình **mã hóa tunnel, học route và xử lý failover**. HA VPN hiện hỗ trợ IPv4 và các kiểu IPv6 theo stack được chọn; lab cố ý dùng **IPv4 only** để giảm biến số.

**Lưu ý về SLA:** theo topology và điều kiện Google Cloud, HA VPN với hai tunnel qua hai interface có thể đạt mức SLA cao (ví dụ 99,99% với topology được hỗ trợ). **Một tunnel đơn không đáp ứng điều kiện HA đó**. Cấu hình peer, đường Internet và phần còn lại của hệ thống vẫn cần dự phòng tương xứng; không thể suy SLA toàn ứng dụng chỉ từ một con số của Cloud VPN.

## 3. Kiểm tra điều kiện trước khi bắt đầu

Thực hiện bảng kiểm tra này với nhóm mạng tại chỗ và quản trị viên Google Cloud.

### 3.1. Địa chỉ và định tuyến

- Không chồng lấn CIDR giữa VPC, on-premises và các mạng có liên kết, kể cả **secondary ranges** của GKE Pods/Services nếu có.
- Xác định rõ **đích cần đến**: VM nội bộ, database dùng private IP, GKE workload hoặc endpoint managed service.
- Xác định route hai chiều: phía GCP cần route tới **172.20.50.0/24**; phía on-premises cần route tới **10.20.10.0/24**.
- BGP ASN hai đầu phải phù hợp, tránh trùng ASN ngoài dự kiến và tuân thủ chính sách định tuyến của doanh nghiệp.
- Xác định **dynamic routing mode** của VPC (regional/global), vì phạm vi áp dụng và quảng bá tuyến phụ thuộc chế độ này.
- Với nhiều site, quyết định ưu tiên đường đi bằng các tham số được hỗ trợ như route priority/MED, không để hai site quảng bá CIDR chồng lấn mà không có chủ đích.

### 3.2. VPN gateway tại chỗ

Thiết bị/ứng dụng peer phải:

- Hỗ trợ IPsec/IKE tương thích Cloud VPN (lab dùng **IKEv2**).
- Hỗ trợ **BGP dynamic routing** cho HA VPN.
- Có địa chỉ public endpoint hoặc cấu hình NAT phù hợp với giới hạn của Cloud VPN.
- Được phép gửi/nhận lưu lượng IKE, ESP/NAT-T theo cấu hình thiết bị; kiểm tra thường gặp là **UDP 500, UDP 4500, ESP** và các giới hạn tại firewall upstream.
- Hỗ trợ hai tunnel và phương án dự phòng phù hợp topology mong muốn.
- Có người vận hành kiểm soát cấu hình peer, routing table, firewall và DNS.

Đừng giả định một firewall chỉ mở TCP 443 là đủ cho IPsec. Những cổng/protocol cụ thể cần dựa vào topology và có/không NAT-T. Với NAT ở phía peer, phải kiểm tra **one-to-one NAT** và các giới hạn của nhiều gateway chia sẻ một public IP.

### 3.3. Quyền và chi phí

Các thao tác cần có quyền quản trị mạng phù hợp, thường là nhóm quyền trong **roles/compute.networkAdmin** và các quyền liên quan đến VPC, gateway, router, tunnel, firewall; tạo VM/DNS có quyền riêng. Cần có project đã gắn billing account và bật các API cần thiết. Lệnh thực hành tạo **VPN gateways/tunnels, VM, disk, DNS** có thể phát sinh phí; ngay cả khi chưa có traffic, tài nguyên VPN hoặc VM vẫn có thể được tính phí.

Nếu chỉ học lý thuyết, có thể **đọc kết quả mẫu và mô phỏng bước kiểm tra**, không cần tạo tài nguyên thật. Các câu lệnh trong bài là ví dụ để người quản trị có thể triển khai trên project lab khi được phép.

## 4. Chuẩn bị môi trường Google Cloud

Các block lệnh bên dưới sử dụng **Bash** trên Cloud Shell hoặc máy có gcloud CLI. Thay toàn bộ biến theo môi trường được cấp. Lệnh tạo/sửa được ghi rõ; không chạy trong production nếu chưa review cấu hình và tác động.

### 4.1. Lệnh chỉ đọc để xác nhận môi trường

~~~bash
gcloud auth list
gcloud config list
gcloud projects describe YOUR_PROJECT_ID
gcloud services list --enabled --project=YOUR_PROJECT_ID

# Kiểm tra các mạng VPC đang có và chế độ định tuyến.
gcloud compute networks list --project=YOUR_PROJECT_ID
gcloud compute networks subnets list --project=YOUR_PROJECT_ID
~~~

Nếu một API chưa được bật, phải xử lý trong phạm vi được cấp quyền. Không tự bật dịch vụ hoặc mở IAM production để làm bài.

### 4.2. Biến môi trường lab

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
ZONE="asia-southeast1-a"
VPC="hybrid-lab-vpc"
SUBNET="cloud-lab-subnet"
GW="ha-vpn-hybrid"
PEER_GW="onprem-peer"
ROUTER="cloud-router-hybrid"
TUNNEL0="hybrid-tunnel-0"
TUNNEL1="hybrid-tunnel-1"
ONPREM_ASN="65010"

# Public IP peer chỉ là placeholder; nhập IP thật trước khi tạo.
PEER_PUBLIC_IP_0="198.51.100.10"
PEER_PUBLIC_IP_1="198.51.100.11"
~~~

**Không đưa pre-shared key (PSK)** vào file cấu hình ví dụ, Git, log hoặc biến môi trường được in ra. Hai tunnel có thể dùng **hai PSK riêng** để giảm ảnh hưởng nếu một thông tin bị lộ. Khi thao tác CLI, chú ý giá trị dùng trong argv, shell history và log có thể bị lộ; nhập qua phương thức quản lý secret được tổ chức cho phép.

## 5. Bước 1 — Tạo VPC và subnet riêng

~~~bash
# TẠO TÀI NGUYÊN — tạo VPC với subnet do người vận hành định nghĩa.
gcloud compute networks create "$VPC" \
  --project="$PROJECT_ID" \
  --subnet-mode=custom \
  --bgp-routing-mode=REGIONAL

# TẠO TÀI NGUYÊN — tạo subnet trong region lab.
gcloud compute networks subnets create "$SUBNET" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --range="10.20.10.0/24"

# CHỈ ĐỌC — xác minh dải IP và chế độ định tuyến.
gcloud compute networks describe "$VPC" --project="$PROJECT_ID"
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**Giải thích:**

- VPC là tài nguyên có phạm vi **global**, nhưng subnet có phạm vi **regional**.
- **REGIONAL** dynamic routing mode là lựa chọn lab với một region. Nếu có workload ở nhiều region cần dùng tuyến hybrid trên toàn VPC, phải đánh giá **GLOBAL** và hành vi quảng bá/học tuyến trước khi đổi.
- Một VPC mới không mặc nhiên có firewall rule cho phép người tại chỗ truy cập mọi VM.
- Dải **10.20.10.0/24** phải được duyệt trước; không thể sửa label để giải quyết chồng lấn IP.

### 5.1. Kiểm tra CIDR chồng lấn

Ví dụ on-premises đã sử dụng **10.20.0.0/16**. Khi đó dải **10.20.10.0/24** là một phần của dải on-premises; hai phía có thể chọn tuyến cục bộ sai và không thể truy cập như thiết kế. Hãy đổi **địa chỉ và subnet** ở bước thiết kế, hoặc cân nhắc giải pháp NAT/định tuyến được hỗ trợ sau khi phân tích kỹ. Đừng cố giải quyết bằng cách mở thêm firewall rule.

## 6. Bước 2 — Tạo HA VPN gateway, peer gateway và Cloud Router

### 6.1. Tạo HA VPN gateway

~~~bash
# TẠO TÀI NGUYÊN — gateway trên VPC và region của lab.
gcloud compute vpn-gateways create "$GW" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --stack-type=IPV4_ONLY

# CHỈ ĐỌC — ghi lại 2 public IP do Google Cloud cấp.
gcloud compute vpn-gateways describe "$GW" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(name,vpnInterfaces)"
~~~

HA VPN gateway có **hai interface**; mỗi interface được cấp một địa chỉ public riêng. Ghi hai địa chỉ này vào bảng cấu hình peer on-premises. Không tự chọn IP Google Cloud hoặc dùng IP subnet VM cho đầu cuối tunnel.

### 6.2. Khai báo thiết bị external peer VPN gateway

Với topology lab, giả định bên on-premises cung cấp **hai public IP** (cùng một thiết bị nhiều interface hoặc hai thiết bị theo thiết kế). Google Cloud lưu thông tin này dưới một **external VPN gateway resource**.

~~~bash
# TẠO TÀI NGUYÊN — hai IP peer thực tế phải thay thế placeholder.
gcloud compute external-vpn-gateways create "$PEER_GW" \
  --project="$PROJECT_ID" \
  --interfaces="0=$PEER_PUBLIC_IP_0,1=$PEER_PUBLIC_IP_1"

# CHỈ ĐỌC.
gcloud compute external-vpn-gateways describe "$PEER_GW" \
  --project="$PROJECT_ID"
~~~

Nếu site chỉ có một public IP, phải dùng **topology một interface peer** và ghép cả hai tunnel tới interface đó theo hướng dẫn Google Cloud. Không sao chép lệnh hai interface ở trên rồi đặt cùng IP vào cả hai trường. Yêu cầu HA toàn tuyến còn tùy khả năng dự phòng phần cứng/đường truyền peer.

### 6.3. Tạo Cloud Router

~~~bash
# TẠO TÀI NGUYÊN — Cloud Router cùng VPC và region với HA VPN.
gcloud compute routers create "$ROUTER" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --asn=64514

# CHỈ ĐỌC.
gcloud compute routers describe "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**Cloud Router** thực hiện trao đổi **BGP control plane**. Router không phải VM mà bạn SSH vào để chuyển tiếp mọi gói tin; tuyến được học từ BGP được đưa vào cơ chế routing của VPC theo quy tắc của Google Cloud. Dùng ASN **64514** ở phía GCP và **65010** ở phía on-premises trong ví dụ; có thể chọn ASN riêng khác miễn đáp ứng ràng buộc hệ thống.

## 7. Bước 3 — Tạo hai IPsec VPN tunnel

Trước khi tạo tunnel, quản trị viên hai phía phải thống nhất:

- **IKE version** và bộ thuật toán được thiết bị hỗ trợ, lab dùng IKEv2.
- Public IP interface Cloud VPN #0/#1 và peer #0/#1.
- Pre-shared key riêng cho từng tunnel.
- Thông số DPD, IPsec rekey, NAT-T và chính sách bên peer.
- Định tuyến động BGP, không dùng nhầm traffic selector của định tuyến tĩnh.
- Firewall/ACL trên thiết bị và đường Internet upstream.

**Ví dụ Bash giả định hai biến** VPN_SHARED_SECRET_0 và VPN_SHARED_SECRET_1 đã được nhập bằng phương thức an toàn được tổ chức quy định; không đưa giá trị bí mật vào tài liệu. Tránh bật **set -x** hoặc chụp log dòng lệnh có secret.

~~~bash
# TẠO TÀI NGUYÊN — lệnh sẽ có PSK trong tham số quy trình.
# Kiểm soát lịch sử shell/log/argv khi thực thi trong môi trường thật.

gcloud compute vpn-tunnels create "$TUNNEL0" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --vpn-gateway="$GW" \
  --interface=0 \
  --peer-external-gateway="$PEER_GW" \
  --peer-external-gateway-interface=0 \
  --router="$ROUTER" \
  --ike-version=2 \
  --shared-secret="$VPN_SHARED_SECRET_0"

gcloud compute vpn-tunnels create "$TUNNEL1" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --vpn-gateway="$GW" \
  --interface=1 \
  --peer-external-gateway="$PEER_GW" \
  --peer-external-gateway-interface=1 \
  --router="$ROUTER" \
  --ike-version=2 \
  --shared-secret="$VPN_SHARED_SECRET_1"
~~~

**Hai tunnel chưa UP ngay sau lệnh tạo** nếu thiết bị on-premises chưa cấu hình phần đối xứng. Đây là trạng thái bình thường trong lúc hai nhóm phối hợp.

~~~bash
# CHỈ ĐỌC — xem trạng thái tunnel hiện tại.
gcloud compute vpn-tunnels describe "$TUNNEL0" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,status,detailedStatus)"

gcloud compute vpn-tunnels describe "$TUNNEL1" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(name,status,detailedStatus)"
~~~

Một topology chỉ có một tunnel hoạt động vẫn có thể truyền dữ liệu, nhưng **chưa chứng minh khả năng chịu lỗi của cấu hình HA**.

## 8. Bước 4 — Cấu hình Cloud Router BGP cho hai tunnel

Mỗi tunnel cần **Cloud Router interface** và **BGP peer**. Bài dùng cách tự động cấp phát BGP link-local IPv4 để giảm sai sót với dải **169.254.0.0/16**; mỗi session sử dụng một cặp địa chỉ trong **/30** khác nhau. Sau khi tạo, quản trị viên on-premises phải đọc chính xác địa chỉ đã cấp rồi đặt chúng lên peer BGP tương ứng.

~~~bash
# TẠO/CẬP NHẬT — interface và BGP peer cho tunnel 0.
gcloud compute routers add-interface "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --interface-name="hybrid-if-0" \
  --vpn-tunnel="$TUNNEL0"

gcloud compute routers add-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-0" \
  --peer-asn="$ONPREM_ASN" \
  --interface="hybrid-if-0"

# TẠO/CẬP NHẬT — interface và BGP peer cho tunnel 1.
gcloud compute routers add-interface "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --interface-name="hybrid-if-1" \
  --vpn-tunnel="$TUNNEL1"

gcloud compute routers add-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-1" \
  --peer-asn="$ONPREM_ASN" \
  --interface="hybrid-if-1"

# CHỈ ĐỌC — xem cấu hình và địa chỉ BGP được cấp.
gcloud compute routers describe "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(interfaces,bgpPeers)"
~~~

Ở phía on-premises, mỗi BGP peer phải:

1. Dùng **ASN local = 65010**, **remote ASN = 64514** trong lab.
2. Đặt IP BGP local/remote đúng cặp **169.254.x.x/30** vừa nhận từ Cloud Router.
3. Quảng bá **172.20.50.0/24** về Google Cloud; không quảng bá route mặc định hoặc dải ngoài phạm vi nếu không có chủ đích.
4. Chấp nhận và cài đặt tuyến **10.20.10.0/24** từ Cloud Router theo chính sách nội bộ.
5. Có chính sách ưu tiên/kiểm tra tuyến khi một tunnel thất bại.

Cú pháp cấu hình **vendor-specific** của Cisco, Fortinet, Juniper, pfSense hoặc router Linux/FRRouting khác nhau. Không nên sao chép cấu hình của một hãng sang thiết bị khác; dùng đúng tài liệu vendor và thông số thực tế từ Cloud Router.

### 8.1. Kiểm tra trạng thái BGP

~~~bash
# CHỈ ĐỌC — trả tình trạng BGP, advertised routes và learned routes.
gcloud compute routers get-status "$ROUTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml

# CHỈ ĐỌC — kiểm tra subnet và tuyến VPC.
gcloud compute routes list \
  --project="$PROJECT_ID" \
  --filter="network:$VPC"
~~~

Trong output Cloud Router, tìm **BGP peer status** và các tuyến tới **172.20.50.0/24** được học ở hai session. Tên trường/biểu diễn có thể khác theo phiên bản API; kiểm tra trạng thái thực tế qua **get-status**, không suy từ thông báo “Creating peer … done”.

**BGP session UP không bảo đảm ứng dụng truy cập được**. Firewall, route phía on-premises, endpoint, DNS hoặc OS vẫn có thể chặn.

### 8.2. Dynamic routing mode và khu vực áp dụng

VPC có thể dùng **REGIONAL** hoặc **GLOBAL** dynamic routing mode:

- Với **REGIONAL**, route động học qua Cloud Router được áp dụng theo cơ chế vùng; những subnet/quảng bá ngoài region có thể cần cấu hình bổ sung hoặc mode khác.
- Với **GLOBAL**, có thể sử dụng phân bố route rộng hơn trên VPC, nhưng còn phụ thuộc chính sách quảng bá, ưu tiên và topology.
- Không thay mode của VPC production chỉ để một lab chạy thành công, vì thay đổi có thể ảnh hưởng nhiều workload và đường đi.

Trong bài lab chỉ có subnet **asia-southeast1**, mode REGIONAL giúp dễ quan sát kết quả.

## 9. Bước 5 — Tạo VM riêng tư và mở firewall tối thiểu

Chỉ tạo VM nếu project lab được phép phát sinh chi phí. VM không có external IP giúp kiểm thử chính xác đường **on-premises → VPN → VPC → VM** mà không vô tình đi Internet.

~~~bash
# TẠO TÀI NGUYÊN — VM kiểm thử không có IP public.
gcloud compute instances create "hybrid-test-vm" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="e2-micro" \
  --subnet="$SUBNET" \
  --private-network-ip="10.20.10.10" \
  --no-address \
  --tags="hybrid-test" \
  --labels="environment=development,application=hybrid-lab"

# CHỈ ĐỌC.
gcloud compute instances describe "hybrid-test-vm" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,networkInterfaces,tags,labels)"
~~~

Lưu ý một VM không có external IP có thể cần **Cloud NAT**, Private Google Access hoặc đường truy cập khác để cập nhật hệ điều hành/tải package. Cloud NAT là cơ chế **kết nối outbound phù hợp**, không dùng để tạo tunnel IPsec hoặc cấp đường on-premises vào VM.

Ví dụ cho phép **chỉ nguồn on-premises** truy cập **ICMP và SSH** vào VM được gắn network tag **hybrid-test**:

~~~bash
# TẠO TÀI NGUYÊN — firewall ở VPC, áp dụng cho VM gắn tag.
gcloud compute firewall-rules create "allow-onprem-hybrid-test" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --source-ranges="172.20.50.0/24" \
  --target-tags="hybrid-test" \
  --rules="icmp,tcp:22"

# CHỈ ĐỌC.
gcloud compute firewall-rules describe "allow-onprem-hybrid-test" \
  --project="$PROJECT_ID"
~~~

**Cần kiểm tra thêm**: VPC hierarchical firewall policies, firewall policy rules, guest OS firewall, IAM/OS Login và cách xác thực SSH. Rule trên không mở quyền truy cập cho toàn Internet, nhưng vẫn chỉ nên dùng trong môi trường thử nghiệm vì SSH cần phương án xác thực riêng. Với production, ưu tiên đích/cổng thật sự cần, danh tính workload và các cơ chế kiểm soát bổ sung.

### 9.1. Firewall ở cả hai phía

Ở on-premises, cần cho phép traffic đi từ **172.20.50.20** tới **10.20.10.10** theo các cổng dùng thử, đồng thời cho phép traffic chiều ngược lại/response tương ứng. Có thể có **hai lớp firewall**:

- **Firewall thiết bị VPN:** cho phép IKE/IPsec và lưu lượng qua tunnel.
- **Firewall nội bộ tại chỗ:** cho phép subnet/host ứng dụng truy cập service đích.

Mở rule GCP không tự mở rule on-premises; kết nối hybrid phải vượt qua **tất cả điểm kiểm soát trên đường đi**.

## 10. Bước 6 — Kiểm thử kết nối và phân biệt từng lớp lỗi

Sau khi **tunnel UP, BGP Established, route hai chiều tồn tại**, thực hiện kiểm thử từ một máy được phép ở on-premises.

~~~bash
# Chạy tại máy 172.20.50.20, không chạy trên Cloud Shell.
# ICMP có thể bị host hoặc firewall chặn.
ping -c 4 10.20.10.10

# Nếu VM có SSH daemon hoạt động và firewall cho phép TCP 22:
nc -vz -w 5 10.20.10.10 22

# Xem đường đi tại máy Linux của site on-premises:
ip route get 10.20.10.10
~~~

Không có phản hồi ping **không chứng minh VPN chết**. Hãy thử TCP port của dịch vụ thật, kiểm tra log, packet counters và route ở mỗi phía. Nếu dùng Windows, thay các lệnh trên bằng **Test-NetConnection**, **tracert** hoặc các công cụ phù hợp.

### 10.1. Ma trận kiểm tra từ dưới lên trên

| Lớp | Bằng chứng cần kiểm tra | Nếu lỗi |
|---|---|---|
| Public reachability | Peer public IP và Cloud VPN IP đúng; UDP/IKE/ESP đi được | Kiểm tra ISP, NAT, firewall outside |
| IKE/IPsec | Hai tunnel được thiết lập, có counters | Kiểm tra PSK, IKEv2, ciphers, peer interface |
| BGP | Session Established, ASN và link-local IP đúng | Kiểm tra BGP trên peer, tunnel, địa chỉ /30 |
| GCP routes | Cloud Router học **172.20.50.0/24** | Kiểm tra peer quảng bá prefix, filters, VPC mode |
| On-prem routes | Peer/site học **10.20.10.0/24** | Kiểm tra advertised prefixes, route install, local gateway |
| Firewall | Cho đúng nguồn/đích/cổng qua các lớp | Xem GCP firewall, policy và firewall tại chỗ |
| Host/service | VM có IP đúng, service lắng nghe | Kiểm tra OS firewall, daemon, status |
| DNS | Tên được phân giải ra IP phù hợp | Xem Cloud DNS policy/forwarding và DNS on-premises |
| Ứng dụng | TLS, IAM, xác thực và phản hồi nghiệp vụ | Kiểm tra log ứng dụng và quyền, không sửa VPN vô cớ |

### 10.2. Packet path hai chiều

~~~mermaid
sequenceDiagram
    participant H as On-prem client 172.20.50.20
    participant P as Peer VPN/BGP
    participant G as HA VPN / VPC
    participant V as VM 10.20.10.10
    H->>P: TCP SYN tới 10.20.10.10
    P->>G: IPsec tunnel đã chọn theo route
    G->>V: Firewall cho phép?
    V-->>G: TCP SYN-ACK
    G-->>P: Route ngược tới 172.20.50.0/24
    P-->>H: Trả về client
~~~

Thiếu **route ngược** khiến kết nối một chiều thất bại dù packet đầu tiên đến được VM. Trên hệ thống có nhiều gateway, cần xem lựa chọn đường trả lời, NAT và bộ lọc chống giả mạo địa chỉ.

## 11. Bước 7 — Phân giải DNS hybrid hai chiều

Nối được IP không đồng nghĩa tên máy nội bộ sẽ tự phân giải. Nếu ứng dụng dùng **api.corp.example.internal** hoặc **vm1.gcp.example.internal**, cần thiết kế DNS.

### 11.1. Cloud → on-premises: forwarding zone

Giả sử máy GCP cần hỏi DNS tại chỗ **172.20.50.53** cho tên thuộc zone **corp.example.internal.**. Tạo forwarding zone riêng tư được gắn vào VPC:

~~~bash
# TẠO TÀI NGUYÊN — chuyển truy vấn zone nội bộ về DNS tại chỗ.
gcloud dns managed-zones create "corp-onprem-forward" \
  --project="$PROJECT_ID" \
  --description="Forward corp.example.internal to on-prem DNS" \
  --dns-name="corp.example.internal." \
  --visibility=private \
  --networks="$VPC" \
  --forwarding-targets="172.20.50.53"

# CHỈ ĐỌC.
gcloud dns managed-zones describe "corp-onprem-forward" \
  --project="$PROJECT_ID"
~~~

**Điểm thường bị bỏ sót:** Cloud DNS truy vấn tới **DNS server on-premises** theo đường hybrid với nguồn có thể thuộc **35.199.192.0/19** (theo cơ chế forwarding được tài liệu mô tả). Site on-premises cần:

- Cho phép **UDP/TCP 53** từ nguồn phù hợp tới DNS server.
- Có **route trả về 35.199.192.0/19** qua cùng VPC và đường Cloud VPN/Interconnect hợp lệ.
- Cho phép DNS server đích gửi phản hồi trực tiếp, phù hợp yêu cầu khớp địa chỉ phản hồi.
- Tránh gửi phản hồi từ một DNS server khác khiến Cloud DNS từ chối kết quả.

Nếu DNS server ở site không có route trả về **35.199.192.0/19**, VPN và BGP tới subnet ứng dụng vẫn có thể hoạt động nhưng DNS forwarding bị timeout/SERVFAIL.

### 11.2. Quảng bá route trả lời DNS qua Cloud Router

Với mô hình lab dùng BGP, cần **custom advertisement** để on-premises học được đường trả lời tới **35.199.192.0/19**. Trên **Cloud Router riêng của lab**, có thể cấu hình cho **cả hai BGP peer**, giữ quảng bá các subnet bình thường bằng **ALL_SUBNETS**:

~~~bash
# CẬP NHẬT BGP ADVERTISEMENTS — chỉ dùng sau khi review
# các prefixes và bảo đảm router này không phục vụ workload khác.
gcloud compute routers update-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-0" \
  --advertisement-mode=CUSTOM \
  --set-advertisement-groups=ALL_SUBNETS \
  --set-advertisement-ranges="35.199.192.0/19"

gcloud compute routers update-bgp-peer "$ROUTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --peer-name="onprem-bgp-1" \
  --advertisement-mode=CUSTOM \
  --set-advertisement-groups=ALL_SUBNETS \
  --set-advertisement-ranges="35.199.192.0/19"
~~~

**Cảnh báo thao tác:** thay đổi advertisement trên router đang dùng cho hệ thống thật có thể làm mất các custom routes trước đó nếu dùng **--set**. Lệnh trên chỉ là mẫu cho **router mới dành riêng cho lab**. Với hệ thống đang vận hành, cần đọc cấu hình hiện tại, giữ đầy đủ các prefix hợp lệ và thử kiểm tra failover.

### 11.3. On-premises → Cloud DNS private zone: inbound forwarding

Giả sử bạn muốn máy on-premises phân giải tên **vm1.gcp.example.internal** trỏ tới **10.20.10.10**.

Tạo **Cloud DNS private zone** và A record:

~~~bash
# TẠO TÀI NGUYÊN — private managed zone.
gcloud dns managed-zones create "gcp-private-zone" \
  --project="$PROJECT_ID" \
  --dns-name="gcp.example.internal." \
  --description="Private names in hybrid lab" \
  --visibility=private \
  --networks="$VPC"

# TẠO BẢN GHI — bản ghi A chỉ là địa chỉ VM trong lab.
gcloud dns record-sets create "vm1.gcp.example.internal." \
  --project="$PROJECT_ID" \
  --zone="gcp-private-zone" \
  --type=A \
  --ttl=300 \
  --rrdatas="10.20.10.10"

# CHỈ ĐỌC.
gcloud dns record-sets list \
  --project="$PROJECT_ID" --zone="gcp-private-zone"
~~~

Để cho phép **DNS tại on-premises** hỏi các tên thuộc private zone, bật **inbound DNS forwarding** cho VPC:

~~~bash
# TẠO TÀI NGUYÊN — DNS policy gắn vào VPC.
gcloud dns policies create "hybrid-inbound-dns" \
  --project="$PROJECT_ID" \
  --description="Allow inbound DNS from on-prem over hybrid connectivity" \
  --networks="$VPC" \
  --enable-inbound-forwarding

# CHỈ ĐỌC — xem policy hiện tại.
gcloud dns policies describe "hybrid-inbound-dns" \
  --project="$PROJECT_ID"
~~~

Sau đó, trong Cloud DNS console hoặc công cụ phù hợp, lấy **inbound forwarding resolver IP** do Google Cloud cấp trong region phù hợp. Trên DNS server on-premises, cấu hình **conditional forwarder** cho **gcp.example.internal.** tới inbound IP, bảo đảm đường VPN và firewall cho phép **TCP/UDP 53**. Đây là **IP forwarding inbound** do dịch vụ cung cấp, không phải mặc định **169.254.169.254** của metadata server hoặc VM.

**Không cấu hình đồng thời nhiều policy DNS xung đột trên cùng VPC** mà chưa đánh giá ảnh hưởng tới phân giải tên hiện có.

### 11.4. Kiểm thử DNS

Chạy từ máy GCP đã được phép truy cập:

~~~bash
# Từ VM GCP, dùng resolver đã cấu hình trên môi trường.
dig app.corp.example.internal A
~~~

Chạy từ máy on-premises:

~~~bash
# Truy vấn qua local DNS server có conditional forwarder.
dig @172.20.50.53 vm1.gcp.example.internal A

# Nếu đã biết inbound forwarding IP thực tế:
dig @INBOUND_FORWARDING_IP vm1.gcp.example.internal A
~~~

DNS trả về **10.20.10.10** là điều kiện cần để dùng tên; vẫn phải kiểm tra kết nối TCP/HTTPS tới IP đó. Một DNS record đúng không chứng minh firewall, route hoặc ứng dụng đã hoạt động.

## 12. Kết nối tới dịch vụ được quản lý: khác với VM

Bài lab dùng VM vì dễ thấy packet path, nhưng ứng dụng sản xuất có thể truy cập Cloud SQL, GKE, Cloud Run hoặc Google APIs.

| Dịch vụ | Cách tiếp cận mạng cần xem xét | Không nên giả định |
|---|---|---|
| **Compute Engine VM** | IP nội bộ trong subnet và firewall VPC/OS | VM không có external IP thì tự đi đến mọi nơi |
| **GKE** | Node/subnet, secondary ranges cho Pods/Services, chính sách mạng, route và cluster connectivity | Chỉ cần route đến node là truy cập mọi Pod/Service |
| **Cloud SQL private IP** | Cơ chế private services access hoặc kiến trúc kết nối riêng được hỗ trợ, DNS/TLS/IAM/database auth | Cloud SQL nằm trực tiếp như một VM bình thường trong VPC |
| **Cloud Run** | URL HTTPS, ingress, IAM, direct VPC egress/connector nếu cần và cơ chế truy cập private được hỗ trợ | Cloud Run có một IP nội bộ VPC mặc định để on-premises gọi trực tiếp |
| **Cloud Storage / Google APIs** | Private Google Access for on-premises/Private Service Connect và DNS/route theo hướng dẫn | Mọi endpoint API sẽ tự đi qua tunnel bằng địa chỉ private |
| **BigQuery** | Endpoint/API/đường private phù hợp, IAM và chính sách dữ liệu | BGP tới subnet VPC là đủ cho mọi request BigQuery |

**Định tuyến và xác thực là hai lớp khác nhau.** Từ on-premises đến được endpoint không cấp quyền IAM. Với Cloud Run có yêu cầu xác thực, caller có thể cần Google-signed ID token đúng audience và quyền Invoker; với Cloud Storage/BigQuery API, thông thường dùng access token và IAM theo phạm vi dịch vụ.

### 12.1. Trường hợp Cloud SQL private IP

Giả sử on-premises cần truy cập Cloud SQL qua private IP. Ngoài VPN/BGP, cần:

1. Xác định cách Cloud SQL instance nhận private IP và kiến trúc **Private Services Access / Private Service Connect** được hỗ trợ.
2. Kiểm tra có tuyến về dải IP được quản lý của dịch vụ hay không; có thể cần custom route advertisement/route exchange theo tài liệu sản phẩm.
3. Xác minh kết nối chiều về, DNS, TCP port của database, TLS và phương thức xác thực database.
4. Chọn Cloud SQL Auth Proxy/connector hoặc phương thức kết nối thích hợp; không mở public IP nếu không có yêu cầu rõ ràng.

Không mở firewall “allow all” chỉ để giải quyết lỗi kết nối database.

## 13. Kiểm thử HA và failover có phương pháp

Một lab HA VPN chỉ hoàn chỉnh khi chứng minh điều gì xảy ra nếu một tunnel không dùng được. Tuy vậy, thao tác làm down tunnel là **thay đổi có ảnh hưởng** và chỉ thực hiện trên project/peer thử nghiệm theo kế hoạch.

### 13.1. Điều kiện trước thử nghiệm

- Tunnel 0/1 đã hoạt động và BGP session ở trạng thái mong đợi.
- Cả hai hướng đã có route tới subnet cần thiết.
- Có kết quả baseline về latency và tỷ lệ thành công của dịch vụ.
- Có người theo dõi peer VPN và Cloud Router ở hai phía.
- Có phương án phục hồi cấu hình và thời gian kiểm thử được phê duyệt.

### 13.2. Kịch bản

1. Từ on-premises, gửi request đều đặn tới dịch vụ thử nghiệm **10.20.10.10**.
2. Ghi tình trạng của tunnel 0/1 và BGP peer status ban đầu.
3. Trong môi trường lab, **vô hiệu hóa có kiểm soát một đường/tunnel ở thiết bị peer** hoặc dùng phương pháp vendor hỗ trợ.
4. Quan sát BGP session tương ứng mất kết nối và route tiếp tục tồn tại qua tunnel còn lại.
5. Đo thời gian gián đoạn, số request thất bại, trạng thái route; không giả định failover tức thời.
6. Khôi phục tunnel, xác minh hai session ổn định.
7. Lưu kết quả và những vấn đề cần điều chỉnh (BGP timer/BFD nếu thiết bị hỗ trợ, routing priority, topology).

~~~text
Kết quả thử nghiệm failover (mẫu)
--------------------------------
Thời gian bắt đầu:
Baseline: tunnel0=UP, tunnel1=UP; BGP0=UP, BGP1=UP
Sự kiện: mất tunnel0 theo phương pháp được duyệt
BGP0:
BGP1:
Route 172.20.50.0/24 còn không:
Request thành công / tổng:
Thời gian gián đoạn quan sát:
Thời gian khôi phục:
Các vấn đề phát sinh:
Người xác minh:
~~~

**SLA của dịch vụ VPN không thay thế bài thử failover end-to-end.** ISP, thiết bị peer, firewall, DNS, backend và mô hình dịch vụ có thể tạo thêm điểm lỗi đơn.

## 14. Chẩn đoán sự cố theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Bước đầu nên làm |
|---|---|---|
| Tunnel không lên | Public IP/peer interface sai, PSK khác, IKE mismatch, UDP/ESP bị chặn | So peer config, trạng thái tunnel và log IKE/IPsec |
| Chỉ tunnel 0 hoạt động | Tunnel 1 thiếu config trên peer hoặc bị firewall/NAT chặn | Kiểm tra map interface 1 và PSK riêng |
| Tunnel UP nhưng BGP DOWN | ASN, link-local /30, BGP policy/port hoặc peer config sai | Đọc Cloud Router get-status và log BGP peer |
| BGP UP nhưng thiếu route on-prem | Peer không quảng bá prefix hoặc filter/route mode | Kiểm tra bảng BGP nhận và advertised prefixes |
| Có route một chiều | Thiếu quảng bá/route trả về hoặc sai next-hop | Kiểm tra bảng định tuyến hai đầu |
| Ping fail, TCP service được | ICMP bị chặn | Dùng đúng cổng ứng dụng làm tiêu chí |
| TCP connection timeout | Firewall/VPC policy, OS firewall, route, service không nghe | Dùng Connectivity Tests, logs, packet counters |
| Kết nối chỉ lỗi khi packet lớn | MTU, MSS, PMTUD, fragmentation | Đo MTU và kiểm tra TCP MSS clamping trên peer |
| DNS GCP → on-prem SERVFAIL | Không đi được tới DNS hoặc thiếu return route 35.199.192.0/19 | Kiểm tra UDP/TCP53, route, Cloud DNS forwarding config |
| DNS on-prem → GCP không được | Thiếu inbound DNS policy, sai resolver IP, thiếu conditional forwarder | Kiểm tra policy và DNS phía on-prem |
| Cloud SQL vẫn unreachable | Chưa có tuyến private service, auth/TLS hoặc database firewall | Đọc kiến trúc kết nối Cloud SQL cụ thể |
| VPC region khác không đi được on-prem | Dynamic routing mode REGIONAL, thiếu quảng bá/route | Xem routing mode và sơ đồ region |
| BGP đổi route ngoài dự kiến | Nhiều site quảng bá prefix chồng lấn, priority/MED khác | Kiểm tra bestRoutes, advertisement và route policy |
| Chi phí mạng tăng bất thường | Egress, tunnel traffic, cross-region/backend path | So Cloud Billing Reports với network metrics |

### 14.1. Dùng Connectivity Tests và Network Intelligence Center

**Connectivity Tests** giúp phân tích đường đi theo cấu hình mạng Google Cloud được hỗ trợ. Đây là công cụ hữu ích để tìm lỗi route/firewall, nhưng không phải lúc nào cũng quan sát được toàn bộ mạng hoặc tình trạng thiết bị vật lý on-premises. Kết luận cuối cùng cần log và số liệu từ cả hai phía.

Để điều tra:

1. Xác định **source/destination IP/port** đúng với request.
2. Kiểm tra tunnel/BGP trước khi đọc log ứng dụng.
3. Đọc **VPC firewall logs**, Cloud VPN logs/metrics nếu đã cấu hình.
4. Kiểm tra thiết bị on-premises với cùng timestamp và IP tuple.
5. Nếu DNS có lỗi, thử truy cập IP trực tiếp để tách lớp phân giải tên.
6. Nếu chỉ lỗi với packet lớn, đo MSS/MTU thay vì đổi IAM.

### 14.2. Lỗi route do VPC peering hoặc nhiều mạng

Nếu workload nằm trong **VPC khác** được nối bằng VPC Network Peering, không mặc nhiên có thể dùng route VPN qua VPC đầu tiên như một mạng transit. Google Cloud VPC peering có giới hạn **transitive routing** và tùy chọn import/export custom routes. Cần thiết kế Shared VPC, Network Connectivity Center hoặc topology được hỗ trợ theo mục tiêu kiến trúc.

Tương tự, nhiều on-premises sites có cùng CIDR cần thiết kế NAT/route policy riêng. Không để hai subnet trùng địa chỉ rồi chỉ điều chỉnh BGP priority để mong giải quyết triệt để.

## 15. Bảo mật kết nối hybrid

VPN mã hóa lưu lượng **giữa hai VPN endpoints**, nhưng không thay thế mọi lớp bảo vệ.

### 15.1. Quy tắc triển khai

- Chỉ quảng bá **các prefix thực sự cần**; không đưa cả 0.0.0.0/0 qua site nếu kiến trúc không có yêu cầu.
- Phân quyền IAM phù hợp cho quản trị viên VPC, Cloud Router, VPN và DNS.
- Quản lý PSK qua công cụ bí mật và xoay vòng theo chính sách; tránh chép vào IaC plain text.
- Giới hạn firewall theo nguồn, đích, giao thức và port; ưu tiên segment môi trường.
- Không coi “đã ở trong mạng riêng” là đủ để bỏ xác thực TLS/IAM ứng dụng.
- Bật log/metrics cần thiết; bảo vệ log không làm lộ hostname, topology hoặc dữ liệu nhạy cảm.
- Dùng labels cho owner/environment và ghi sơ đồ prefix/quyền liên quan vào hồ sơ vận hành.
- Thực hiện thay đổi route/quảng bá qua pull request hoặc change ticket có đánh giá ảnh hưởng.

### 15.2. Phân chia trách nhiệm

| Nhóm | Trách nhiệm |
|---|---|
| On-premises network | Thiết bị VPN, peer public IP, BGP ASN, LAN routes, DNS site, firewall |
| Cloud platform | VPC, subnet, Cloud VPN, Cloud Router, firewall, private DNS policy |
| Application | Endpoint, TLS/auth, timeout/retry, SLO, truy cập database/secret |
| Security | Kiểm tra tối thiểu quyền, phân đoạn mạng, PSK, log, audit |
| FinOps | Chi phí tunnel, transfer, compute test, monitoring, Interconnect nếu dùng |

Mọi bên cần dùng **cùng một bảng thông số**. Một sai lệch nhỏ như peer ASN, IKE PSK hoặc subnet CIDR có thể khiến cả hệ thống không liên lạc được.

## 16. Độ tin cậy, giám sát và chi phí

### 16.1. Monitoring

Các tín hiệu cần quan sát:

- **Tunnel status** và số tunnel đang hoạt động.
- **BGP session status**, số tuyến được học/quảng bá, thay đổi bất thường của best route.
- **Lưu lượng byte/packet** qua tunnel và nguy cơ gần chạm giới hạn throughput.
- **Độ trễ, packet loss** giữa các endpoint thử nghiệm, thời gian DNS resolve.
- **Lỗi ứng dụng** qua kết nối hybrid, lỗi retry và timeout.
- **Thời gian hội tụ** sau mất một đường.

Có thể sử dụng Cloud Monitoring cho các metric do Cloud VPN/Cloud Router cung cấp, đồng thời kết hợp hệ thống giám sát peer on-premises. Cảnh báo “tunnel0 down” nên phân biệt với “cả hai tunnel down và ứng dụng mất kết nối”.

### 16.2. Thành phần chi phí

Không suy rằng VPN miễn phí vì chỉ dùng IP riêng. Tổng chi phí có thể đến từ:

| Thành phần | Cách phát sinh |
|---|---|
| HA VPN/tunnels | Phí tài nguyên tunnel/gateway theo bảng giá hiện hành |
| Network egress | Lưu lượng ra khỏi Google Cloud theo chiều/điểm đến và loại dịch vụ |
| VM và disk thử nghiệm | Thời gian sử dụng compute/storage |
| Cloud DNS | Managed zones, queries hoặc tính năng liên quan theo giá áp dụng |
| Logging/Monitoring | Dữ liệu log/metric và retention vượt điều kiện miễn phí |
| Interconnect | Port/attachment, nhà cung cấp và transfer nếu dùng |
| Dự phòng | Hai đường tunnel/mạch để tăng HA có thể tăng phí vận hành |

**Cloud Billing Reports** giúp phân tích chi phí theo service/SKU, còn **Cost table** phục vụ đối soát hóa đơn. Khi so sánh VPN và Interconnect, cần tính cả chi phí truyền dữ liệu, thiết bị peer/ISP, vận hành và mục tiêu độ tin cậy; không chỉ so giá đơn vị của một tunnel.

## 17. Dọn dẹp lab và tránh tác động hệ thống khác

Chỉ dọn dẹp nếu **các tài nguyên được tạo riêng cho lab** và không có ứng dụng/nhóm khác đang dùng. Xóa tài nguyên mạng có thể làm mất đường kết nối; cần xác nhận phụ thuộc và thứ tự.

Thứ tự khái niệm:

1. Xác minh không còn test/traffic cần giữ và lưu kết quả lab.
2. Gỡ **DNS policy/private/forwarding zones** tạo riêng cho lab, sau khi kiểm tra không còn client sử dụng.
3. Xóa **VM thử nghiệm** và firewall rule liên quan.
4. Gỡ **BGP peers/Cloud Router interfaces** trên các tunnel lab, kiểm tra tác động định tuyến.
5. Xóa **VPN tunnels**, sau đó **Cloud Router**, **HA VPN gateway** và **external peer gateway** khi không còn phụ thuộc.
6. Xóa subnet và VPC riêng cho lab cuối cùng, sau khi xác nhận không còn tài nguyên.
7. Đối soát Cloud Billing/Resource Inventory để phát hiện tài nguyên còn lại có tính phí.

Ví dụ **chỉ đọc** để kiểm kê trước khi dọn:

~~~bash
gcloud compute vpn-tunnels list --project="$PROJECT_ID"
gcloud compute vpn-gateways list --project="$PROJECT_ID"
gcloud compute routers list --project="$PROJECT_ID"
gcloud compute instances list --project="$PROJECT_ID"
gcloud compute firewall-rules list --project="$PROJECT_ID"
gcloud dns managed-zones list --project="$PROJECT_ID"
gcloud dns policies list --project="$PROJECT_ID"
~~~

Bài này **không đưa chuỗi lệnh xóa hàng loạt** vì mỗi tài nguyên có thể được chia sẻ với workload khác; người vận hành phải xác nhận owner, phạm vi, phụ thuộc và cách phục hồi. Nếu có một link VPN đang phục vụ production, chỉ xóa theo kế hoạch thay đổi được phê duyệt.

## 18. Bài tập đánh giá sau thực hành

### 18.1. Bài tập A — đọc sơ đồ mạng

Một hệ thống có:

- VPC subnet **10.20.10.0/24**.
- On-premises subnet **172.20.50.0/24**.
- Tunnel 0/1 đều UP; BGP peer 0 UP, peer 1 DOWN.
- On-premises client không kết nối được VM, dù Cloud Router thấy tuyến tới **172.20.50.0/24**.

Trả lời:

1. Trạng thái trên đã đạt kỳ vọng HA chưa? Vì sao?
2. Việc Google Cloud thấy route tới on-premises đã chứng minh phía on-premises biết route **10.20.10.0/24** chưa?
3. Nên kiểm tra firewall và host ở những nơi nào?
4. Nên thử ping hay TCP port của ứng dụng trước khi kết luận?
5. Nếu chỉ one-way, cần xem thêm điều gì?

**Định hướng:** BGP peer thứ hai chưa hoạt động nên trạng thái HA chưa hoàn chỉnh; route GCP không chứng minh route chiều về; kiểm tra peer routes/firewall/OS, thử đúng cổng dịch vụ, đối chiếu traffic return path.

### 18.2. Bài tập B — DNS hoạt động không đầy đủ

Một VM Google Cloud phân giải **app.corp.example.internal** bị SERVFAIL, nhưng **ping 172.20.50.53** từ mạng ứng dụng có thể thành công. Hãy chỉ ra ít nhất bốn giả thuyết.

**Định hướng:** forwarding zone cấu hình sai; on-premises DNS từ chối UDP/TCP 53; thiếu route trả về **35.199.192.0/19**; DNS server trả lời từ IP khác; firewall/quy tắc ACL ngăn request; dịch vụ DNS không có record hoặc lỗi server. **Ping tới DNS server không kiểm chứng toàn bộ đường DNS forwarding**.

### 18.3. Bài tập C — lựa chọn công nghệ

Một doanh nghiệp truyền dữ liệu ổn định ở lưu lượng cao, cần thời gian truyền dự đoán được và có quy định kết nối vật lý riêng. HA VPN qua Internet có đủ phù hợp không? Hãy so sánh **HA VPN**, **Partner Interconnect** và **Dedicated Interconnect**, cân nhắc thông lượng, dự phòng, thời gian triển khai, chi phí, mã hóa và nhà cung cấp mạng.

**Định hướng:** không chọn theo một yếu tố giá. Với yêu cầu đường truyền riêng/quy mô cao, cần đánh giá Interconnect và cân nhắc IPsec khi yêu cầu bảo vệ dữ liệu trên đường truyền.

### 18.4. Mẫu báo cáo hoàn tất lab

~~~text
Project / VPC / Region:
Thời điểm kiểm tra (UTC):
GCP subnet / On-prem subnet:
Cloud VPN interface 0/1: [địa chỉ công khai đã che bớt]
Tunnel 0/1: [UP/DOWN + timestamp]
BGP peer 0/1: [ESTABLISHED/DOWN]
GCP learned routes:
On-prem learned routes:
Firewall source/destination/port:
Kết quả TCP / ICMP:
Kết quả DNS GCP -> on-prem:
Kết quả DNS on-prem -> GCP:
Kết quả failover:
Chi phí hoặc budget cảnh báo:
Vấn đề còn tồn tại:
Owner và ngày xử lý:
~~~

Báo cáo nên nêu **các bước đã thực sự chạy và kết quả đã quan sát**, không ghi “hoàn tất” chỉ vì tài nguyên được tạo thành công. Không đưa pre-shared key, token hoặc private key vào kết quả bài tập.

## 19. Tài liệu tham khảo Google Cloud

Các tài liệu chính thức hữu ích khi kiểm tra lệnh, điều kiện SLA và yêu cầu mạng:

- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Create an HA VPN gateway to a peer VPN gateway](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/creating-ha-vpn)
- [Configure a peer VPN gateway](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/configuring-peer-gateway)
- [HA VPN topologies](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/topologies)
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices)
- [View Cloud Router details and BGP state](https://docs.cloud.google.com/network-connectivity/docs/router/how-to/viewing-router-details)
- [VPC dynamic routing mode and best path selection](https://docs.cloud.google.com/network-connectivity/docs/router/how-to/create-network-set-modes)
- [Cloud DNS forwarding zones](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones)
- [Cloud DNS best practices](https://docs.cloud.google.com/dns/docs/best-practices)
- [Cloud DNS server policies](https://docs.cloud.google.com/dns/docs/policies)
- [Cloud VPN troubleshooting](https://docs.cloud.google.com/network-connectivity/docs/vpn/support/troubleshooting)
- [Cloud VPN pricing](https://cloud.google.com/network-connectivity/pricing)

Tên lệnh, cờ CLI, cấu hình sản phẩm, giá và điều kiện SLA có thể được Google Cloud cập nhật. Khi triển khai thật, luôn kiểm tra tài liệu theo phiên bản CLI và thiết bị peer, đồng thời đối chiếu chính sách của tổ chức.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** nối on-premises với VPC là bài thực hành tổng hợp **project/IAM, VPC/subnet, HA VPN/BGP, Cloud DNS, firewall, Compute Engine và đường truy cập tới dịch vụ quản lý**. Khi mở rộng sang GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, người học cần giữ cách tư duy từ **địa chỉ và định tuyến** đến **danh tính, bảo mật, tự động hóa, giám sát, chi phí và khả năng phục hồi**. Một kết nối hybrid được coi là vận hành tốt khi có thể **chứng minh thông suốt hai chiều, giới hạn quyền truy cập, phát hiện sự cố và khôi phục theo thiết kế**.

