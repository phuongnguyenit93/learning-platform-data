# Chọn VPN hoặc Interconnect theo yêu cầu kết nối

> **Chương:** DNS và kết nối hybrid  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Khi đưa một phần hệ thống từ trung tâm dữ liệu doanh nghiệp lên Google Cloud, câu hỏi quan trọng không chỉ là “làm sao cho hai mạng nhìn thấy nhau”. Đội kỹ thuật phải quyết định **kết nối qua Internet có mã hóa IPsec hay qua đường kết nối riêng**, cần bao nhiêu băng thông, độ trễ cho phép, chịu lỗi ra sao, ai vận hành thiết bị và mức chi phí nào phù hợp. Lựa chọn giữa **Cloud VPN** và **Cloud Interconnect** ảnh hưởng trực tiếp đến hiệu năng, bảo mật, tính sẵn sàng và khả năng mở rộng.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu cách tổ chức project, IAM và VPC; triển khai Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu; bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài học này tập trung vào quyết định kết nối hybrid, để một API trên Cloud Run hoặc workload trên GKE/Compute Engine có thể liên lạc có kiểm soát với cơ sở dữ liệu, DNS, hệ thống xác thực hoặc ứng dụng đặt tại on-premises.

**Sau khi học, bạn có thể:**

1. Phân biệt Cloud VPN, Dedicated Interconnect, Partner Interconnect, Cross-Cloud Interconnect và HA VPN over Cloud Interconnect.
2. Dùng yêu cầu băng thông, độ trễ, mã hóa, SLA, địa điểm, thời gian triển khai và chi phí để chọn công nghệ phù hợp.
3. Giải thích vai trò của VPC, Cloud Router, BGP, gateway, VLAN attachment và thiết bị phía doanh nghiệp.
4. Thiết kế sơ đồ có đường chính, đường dự phòng, chiều đi/chiều về và kiểm tra failover.
5. Xây dựng bảng quyết định kiến trúc, dự trù chi phí và kế hoạch kiểm chứng trên môi trường được phép.
6. Nhận diện lỗi định tuyến, overlap CIDR, firewall, MTU, BGP, DNS và các giới hạn của từng công nghệ.

## 1. Bài toán kết nối hybrid là gì?

**Hybrid connectivity** cho phép các mạng ở trung tâm dữ liệu, văn phòng, mạng của đối tác hoặc nhà cung cấp đám mây khác kết nối với một hoặc nhiều **VPC network** của Google Cloud. Mục tiêu thường là truy cập qua **địa chỉ private IP**, không phải công khai từng dịch vụ lên Internet.

Ví dụ ứng dụng đặt hàng được triển khai từng phần:

~~~text
On-premises: 172.16.0.0/16
├── Hệ thống ERP          172.16.10.20
├── CSDL nghiệp vụ        172.16.20.10
└── DNS nội bộ            172.16.53.10

Google Cloud VPC: 10.20.0.0/16
├── Compute Engine VM     10.20.1.10
├── GKE worker/pod ranges (theo cấu hình)
└── Cloud Run qua VPC egress phù hợp
~~~

Các dịch vụ GCP cần truy cập `172.16.20.10:5432` mà không đưa CSDL ra public Internet. Kết nối phải hỗ trợ gói tin **từ GCP sang on-premises và chiều trả lời ngược lại**.

Để thiết kế được, cần tách bốn lớp:

| Lớp | Câu hỏi cần trả lời |
| --- | --- |
| **Đường truyền** | Đi qua Internet bằng IPsec, mạch riêng đến Google hay đường của nhà cung cấp kết nối? |
| **Định tuyến** | VPC biết prefix `172.16.0.0/16` từ đâu? Mạng doanh nghiệp biết đường về `10.20.0.0/16` ra sao? |
| **Bảo mật** | Đường truyền có mã hóa? Ai được truy cập? Firewall và DNS được cấu hình thế nào? |
| **Vận hành** | Có đường dự phòng, theo dõi BGP/tunnel/circuit và kiểm thử mất một đường chưa? |

**Lưu ý:** Cloud VPN là **site-to-site IPsec VPN**, không phải dịch vụ VPN client cho nhân viên dùng máy tính cá nhân quay số vào VPC. Nếu yêu cầu là truy cập từ từng laptop, cần giải pháp truy cập người dùng phù hợp thay vì giả định Cloud VPN cung cấp client VPN.

## 2. Năm lựa chọn cần phân biệt

### 2.1. Cloud VPN: đường IPsec trên Internet

**Cloud VPN** nối mạng phía doanh nghiệp hoặc mạng khác với VPC bằng đường hầm **IPsec**. Dữ liệu được mã hóa trên đoạn mạng giữa các VPN gateway; với Cloud VPN thông thường, lưu lượng đi qua **public Internet**.

Google Cloud cung cấp:

- **HA VPN:** lựa chọn được khuyến nghị cho kết nối mới cần độ sẵn sàng. Gateway có hai interface với địa chỉ external IP riêng, sử dụng **dynamic routing (BGP) qua Cloud Router**. Cấu hình topology đúng điều kiện có thể đủ SLA **99,99%**; các topology khác có thể chỉ đạt **99,9%** hoặc không đủ SLA.
- **Classic VPN:** gateway một interface, hỗ trợ định tuyến tĩnh (route-based/policy-based), SLA **99,9%**. Chủ yếu nên hiểu để bảo trì/migrate hệ thống hiện có; HA VPN là điểm xuất phát tốt hơn cho thiết kế mới dùng BGP.

Tốc độ mỗi Cloud VPN tunnel bị giới hạn theo **packet rate** (theo tài liệu hiện tại là tối đa khoảng **250.000 packet/giây** cho tổng chiều vào và ra). Tùy kích thước gói, hiệu năng tương đương khoảng **1–3 Gbps/tunnel**. Đây **không phải băng thông được bảo đảm**. RTT, packet loss, năng lực peer gateway, MTU, số luồng TCP và tải mã hóa đều ảnh hưởng thông lượng thực tế.

**Khi nên cân nhắc:** Kết nối thử nghiệm, lưu lượng vừa hoặc thấp, cần bắt đầu nhanh, chưa có hạ tầng colocated, backup tạm thời hoặc kết nối có thể chấp nhận biến động của Internet.

### 2.2. Dedicated Interconnect: kết nối vật lý trực tiếp

**Dedicated Interconnect** thiết lập các kết nối Ethernet vật lý giữa mạng của doanh nghiệp và mạng Google tại **colocation facility** được hỗ trợ. Doanh nghiệp cần router/thiết bị phù hợp, liên hệ nhà cung cấp cơ sở vật lý và hoàn thành quy trình đặt mạch, LOA-CFA, cross-connect, thử nghiệm và kích hoạt.

Các link vật lý được hỗ trợ gồm **10 Gbps, 100 Gbps và 400 Gbps**, theo địa điểm và thiết bị. Một kết nối Dedicated Interconnect có thể gồm nhiều circuit, còn **VLAN attachment** phân chia khả năng kết nối với VPC cụ thể.

Ưu điểm điển hình:

- Đường mạng không đi qua Internet công cộng.
- Băng thông lớn, khả năng dự báo lưu lượng/độ trễ tốt hơn một tuyến Internet thông thường.
- Tối ưu cho vận chuyển dữ liệu lớn và hệ thống hybrid ổn định lâu dài.
- Doanh nghiệp chủ động hơn về kết nối tại facility, thiết bị và dung lượng.

Đánh đổi: Chi phí port/circuit, cross-connect, router, vận hành, nhân lực và **thời gian triển khai vật lý**. Nếu hệ thống không cần cỡ dung lượng này hoặc không thể đưa mạng đến colocation, Dedicated có thể không phù hợp.

### 2.3. Partner Interconnect: kết nối qua nhà cung cấp

**Partner Interconnect** nối doanh nghiệp đến Google Cloud thông qua **service provider** được hỗ trợ. Doanh nghiệp không nhất thiết phải tự đưa thiết bị đến một Google colocation facility. Với loại kết nối này, capacity của một **VLAN attachment** theo tài liệu hỗ trợ từ **50 Mbps đến 50 Gbps**, tùy mức mà nhà cung cấp và vị trí cung cấp thực tế.

Partner Interconnect có hai mô hình:

| Kiểu Partner | Ai quản lý BGP gần Google? | Khi nào phù hợp? |
| --- | --- | --- |
| **Layer 2** | Doanh nghiệp cấu hình BGP giữa router on-premises và Cloud Router | Muốn tự kiểm soát BGP/prefix và có năng lực vận hành routing |
| **Layer 3** | Service provider thiết lập BGP với Cloud Router; cấu hình phía doanh nghiệp tùy hợp đồng | Muốn nhà cung cấp quản lý một phần routing, giảm thao tác trực tiếp |

Ưu điểm: Băng thông có mức chia nhỏ hơn Dedicated, hỗ trợ địa điểm khó tiếp cận colocation. Đánh đổi: Phụ thuộc nhà cung cấp, SLA/giá và trách nhiệm vận hành gồm cả đường từ doanh nghiệp đến provider.

**Quan trọng về SLA:** SLA Google dành cho Partner Interconnect áp dụng cho đoạn **VPC ↔ mạng của service provider**, không tự bảo đảm toàn bộ đoạn **mạng doanh nghiệp ↔ provider ↔ Google Cloud**. Cần xem SLA của cả provider và thiết kế đường vật lý của họ.

### 2.4. Cross-Cloud Interconnect

Nếu đầu bên kia không phải trung tâm dữ liệu riêng mà là **mạng trên một cloud provider khác**, Google Cloud có **Cross-Cloud Interconnect** để nối trực tiếp đến các nhà cung cấp được hỗ trợ. Nó nằm trong họ Cloud Interconnect, có điều kiện đặt cổng, vùng ghép nối, khả năng hỗ trợ, BGP và giá riêng.

Lựa chọn này đáng khảo sát khi lượng dữ liệu giữa Google Cloud và AWS/Azure/OCI hoặc cloud được hỗ trợ lớn, ổn định hoặc cần kết nối chuyên dụng. Không tự thay Cross-Cloud bằng Dedicated Interconnect on-premises trong sơ đồ, vì bên vận hành đầu kia và quy trình provisioning khác nhau.

Với các giải pháp partner Cross-Cloud/managed cloud partner, danh mục sản phẩm và vùng hỗ trợ có thể thay đổi. Hãy đối chiếu tài liệu hiện hành của cloud nguồn và đích.

### 2.5. HA VPN over Cloud Interconnect: kết hợp đường riêng và IPsec

**Cloud Interconnect không mã hóa lưu lượng mặc định.** Nếu phải mã hóa IP giữa mạng doanh nghiệp và VPC, có thể triển khai **HA VPN over Cloud Interconnect** trên Dedicated hoặc Partner Interconnect. Như vậy:

- **Cloud Interconnect** cung cấp đường truyền đến Google, không đi qua Internet công cộng.
- **HA VPN tunnels** mã hóa IPsec bên trên đường truyền đó.
- Cần cấu hình **hai tầng**, bao gồm VLAN attachments/Cloud Router cho Interconnect và HA VPN gateways/tunnels/Cloud Router cho VPN.
- Để có dự phòng/SLA, cần số attachment và topology phù hợp, không chỉ bật một tunnel.
- **Giới hạn packet rate của VPN tunnel vẫn tồn tại**; việc có circuit 10/100 Gbps không đồng nghĩa một tunnel IPsec đạt tốc độ circuit.

Đây là lựa chọn phù hợp khi có yêu cầu **đường riêng và mã hóa lớp mạng**. **MACsec for Cloud Interconnect** cũng có thể được sử dụng trên những kết nối hỗ trợ, nhưng phạm vi mã hóa là đoạn kết nối Ethernet giữa router và edge router được hỗ trợ; MACsec không tự bảo vệ end-to-end toàn bộ đường trong mạng Google. Có thể kết hợp MACsec với IPsec/TLS theo yêu cầu bảo mật.

## 3. Bảng so sánh nhanh để định hướng

| Tiêu chí | HA VPN | Dedicated Interconnect | Partner Interconnect | HA VPN over Interconnect |
| --- | --- | --- | --- | --- |
| **Đường đi** | IPsec qua public Internet | Kết nối vật lý đến Google | Qua service provider | IPsec qua Interconnect |
| **Mã hóa mặc định** | Có IPsec | Không | Không | Có IPsec |
| **Năng lực truyền** | Bị giới hạn theo tunnel/packet rate; có thể mở nhiều tunnel | Các circuit 10/100/400 Gbps, tùy cấu hình | Attachment 50 Mbps–50 Gbps, tùy provider | Interconnect và giới hạn từng IPsec tunnel |
| **Thời gian triển khai** | Thường nhanh nếu đã có peer VPN và IP công cộng | Cần đặt mạch/cross-connect, lâu hơn | Phụ thuộc thời gian provider cấp đường | Cần Interconnect trước rồi thiết lập VPN |
| **Yêu cầu phía doanh nghiệp** | IPsec peer và BGP phù hợp | Router, facility hoặc backhaul, BGP, VLAN | Hợp đồng provider; BGP L2 hoặc L3 | Thiết bị VPN cùng yêu cầu Interconnect |
| **Độ trễ** | Ảnh hưởng bởi Internet và RTT | Thường ổn định, ít hop public hơn | Phụ thuộc mạng provider | Độ trễ của Interconnect cộng chi phí xử lý IPsec |
| **SLA** | 99,99% khi topology HA đủ điều kiện; không suy từ 1 tunnel | 99,9%/99,99% theo topology đúng điều kiện | 99,9%/99,99% cho phạm vi Google–provider, cần SLA provider | Theo topology Interconnect/HA VPN được hỗ trợ |
| **Chi phí** | Tunnel/gateway và dữ liệu truyền, chi phí mạng peer | Port/circuit, attachment, dữ liệu truyền, colocation | Attachment, dữ liệu truyền, phí provider | Interconnect + VPN + vận hành |
| **Dùng làm backup?** | Phổ biến nếu cần đường khác công nghệ | Có thể là đường chính hoặc một nhánh | Có thể là đường chính hoặc nhánh khác | Có nếu thiết kế HA và route phù hợp |

Bảng chỉ giúp **lọc phương án**, không thay thế bài tính capacity và đánh giá topology SLA theo tài liệu chính thức. Con số “99,99%” gắn với **điều kiện triển khai và phạm vi dịch vụ**, không phải quyền lợi tự động chỉ từ tên sản phẩm.

## 4. Sáu nhóm yêu cầu cần thu thập trước khi chọn

### 4.1. Nhu cầu băng thông và kiểu lưu lượng

Hãy đo:

- **Lưu lượng trung bình và đỉnh**, chiều từ GCP ra on-premises và chiều ngược lại.
- **Packet rate (pps)**, kích thước packet, tỷ lệ gói nhỏ, số TCP flows đồng thời.
- **Khối lượng truyền theo ngày/tháng**, ví dụ backup, đồng bộ dữ liệu, DB replication.
- **Độ tăng trưởng dự kiến** trong 12–24 tháng.
- **Yêu cầu khi failover:** đường còn lại phải chịu bao nhiêu phần trăm tải?
- **Độ nhạy với packet loss/RTT**, đặc biệt replication đồng bộ và transaction DB.

Một cách ước lượng băng thông trung bình sơ bộ:

~~~text
Average bandwidth (Mbps)
  = bytes truyền trong kỳ × 8 / số giây của kỳ / 1.000.000

Required capacity
  ≈ lưu lượng đỉnh + headroom + phần tải cần gánh khi failover
~~~

Không dùng average bandwidth một mình để đặt hàng circuit. Một hệ thống chuyển 1 TB/ngày có thể có throughput trung bình vừa phải nhưng vẫn cần vài Gbps trong một cửa sổ backup ngắn. Kiểm tra tốc độ đỉnh và packet rate thực tế.

**Đối với Cloud VPN:** 250.000 pps trên mỗi tunnel là một giới hạn rất đáng chú ý. Một workload gồm gói nhỏ có thể chạm pps limit trước khi đạt mức Gbps kỳ vọng. Với Interconnect, cũng phải tính overhead VLAN, MTU, năng lực router, attachment size và băng thông provider.

### 4.2. Độ trễ và tính ổn định

“Private Interconnect” thường có đường truyền ít phụ thuộc Internet public, nên có thể giúp ổn định độ trễ. Tuy nhiên, **không có con số RTT cố định** cho mọi điểm đến. RTT còn phụ thuộc khoảng cách địa lý, metro, tuyến provider, số hop, tải ứng dụng và thiết bị mã hóa.

Cần đo độ trễ từ **vị trí thật của ứng dụng** đến **dịch vụ thật** ở on-premises, không chỉ ping từ một VM mẫu đến địa chỉ gateway. Với ứng dụng Java/SQL cần nhiều round trip, chênh lệch RTT có thể khuếch đại thành độ trễ giao dịch.

### 4.3. Mức sẵn sàng và khôi phục

Ghi rõ **SLO** và **RTO/RPO** của ứng dụng. Một kết nối “có 99,99% SLA” chưa bảo đảm cơ sở dữ liệu không bị lỗi khi mạng rớt vài giây, hoặc failover BGP diễn ra đủ nhanh cho transaction. Cần test khả năng retry, timeout, connection pool và cơ chế phục hồi phía ứng dụng.

### 4.4. Bảo mật và tuân thủ

Đặt câu hỏi:

1. Có bắt buộc **mã hóa trong quá trình truyền** không?
2. Chính sách có cho phép truyền qua Internet đã mã hóa IPsec không?
3. Dữ liệu có yêu cầu đi qua network provider/vùng địa lý cụ thể?
4. Có cần TLS ở tầng ứng dụng bất kể đường mạng?
5. Firewall, segmentation và nhật ký truy cập được quản lý ở đâu?

**Private path không đồng nghĩa encrypted path.** Nếu quy định yêu cầu IPsec, chọn HA VPN hoặc HA VPN over Interconnect; nếu chỉ cần an toàn đoạn Ethernet nhất định có thể khảo sát MACsec, nhưng phải ghi rõ vùng được bảo vệ.

### 4.5. Địa điểm và khả năng triển khai

- Có router/doanh nghiệp ở **colocation** được Google hỗ trợ cho Dedicated không?
- Có thể thuê đường backhaul/cross-connect đến colocation và có nhân lực vận hành?
- Service provider nào có điểm kết nối, bandwidth, SLA và giá phù hợp cho Partner?
- Cloud region/VPC cần kết nối nằm ở đâu? Metro và edge availability domain nào liên quan?
- On-premises có IP public cố định hoặc thiết bị IPsec/BGP phù hợp cho HA VPN không?
- Kết nối phải hoạt động trong vài ngày hay có thể triển khai theo chu kỳ mua sắm, lắp đặt và phê duyệt nhiều tuần?

### 4.6. Tổng chi phí sở hữu (TCO)

Giá dịch vụ Google là một phần; còn chi phí thiết bị, đường truyền, vận hành, hỗ trợ và dự phòng.

| Nhóm chi phí | Cloud VPN | Dedicated | Partner |
| --- | --- | --- | --- |
| Tài nguyên Google | Gateway/tunnel và traffic liên quan | Physical connection/ports, VLAN attachments, traffic | VLAN attachment và traffic |
| Chi phí ngoài Google | Peer VPN gateway, ISP, thiết bị mã hóa | Colocation, cross-connect, router, backhaul | Cước provider/circuit, phí vận hành |
| Dự phòng | Nhiều tunnel/gateway/peer, có thể nhiều ISP | Nhiều connection, metro, domain, thiết bị | Nhiều attachment/provider/metro |
| Vận hành | IPsec, key, BGP, phiên tunnel | Circuit, BGP, optics, capacity và colocation | SLA provider, BGP theo L2/L3, phối hợp xử lý sự cố |
| Mở rộng | Thêm tunnel, cân nhắc limit theo pps | Tăng/đặt thêm link/circuit, attachment capacity | Tùy dịch vụ và năng lực nhà cung cấp |

So sánh theo **một cùng kỳ** (tháng/năm), cùng tổng data egress, cùng redundancy level và cùng lưu lượng đỉnh. Không chọn phương án chỉ bằng cách so giá một VPN tunnel với một Interconnect port; phạm vi chi phí khác nhau.

## 5. Kiến trúc mẫu và vai trò của Cloud Router

### 5.1. Mẫu HA VPN có hai đường

~~~mermaid
flowchart LR
    subgraph DC["Mạng doanh nghiệp"]
      LAN["172.16.0.0/16"]
      PEER1["Peer VPN gateway A"]
      PEER2["Peer VPN gateway B"]
      LAN --> PEER1
      LAN --> PEER2
    end
    subgraph GCP["Google Cloud"]
      VPC["VPC 10.20.0.0/16"]
      GW0["HA VPN gateway interface 0"]
      GW1["HA VPN gateway interface 1"]
      CR["Cloud Router · BGP"]
      GW0 --> CR
      GW1 --> CR
      CR -. "Quản lý route" .-> VPC
    end
    PEER1 == "IPsec tunnel + BGP" ==> GW0
    PEER2 == "IPsec tunnel + BGP" ==> GW1
~~~

Tùy thiết bị peer và topology, có thể dùng một peer có hai interface hoặc hai peer độc lập. Để có khả năng đáp ứng mức SLA cao nhất được hỗ trợ, cần **kết nối cả hai interface**, cấu hình tunnel pair và tính dự phòng phía peer phù hợp. Một HA VPN gateway chỉ có một tunnel hoặc chỉ một interface hoạt động **không mặc nhiên đủ SLA**.

**Cloud Router** quản lý phiên **BGP** và các tuyến động. Hạ tầng routing của VPC làm công việc chuyển tiếp gói. Không mô tả Cloud Router như một router VM nhận và forward mọi packet.

### 5.2. Mẫu Dedicated Interconnect

~~~mermaid
flowchart LR
    ON["Router on-premises"] --> COL["Colocation / Cross-connect"]
    COL == "Dedicated Ethernet circuits" ==> EDGE["Google edge router"]
    EDGE --> VLAN["VLAN attachment"]
    VLAN --> CR["Cloud Router · BGP"]
    CR -. "Dynamic routes" .-> VPC["VPC 10.20.0.0/16"]
~~~

Sơ đồ trên **chỉ minh họa một đường**, chưa đáp ứng cấu hình HA production. Một kiến trúc production cần nhiều circuit/connection, edge availability domains, có thể nhiều metros, VLAN attachments, Cloud Routers và thiết bị khách hàng theo topology SLA tương ứng.

Các khái niệm:

- **Connection:** tài nguyên vật lý được provision đến mạng Google.
- **VLAN attachment:** kết nối logic giữa connection Interconnect và một VPC/region; có bandwidth capacity và BGP.
- **Cloud Router:** trao đổi route BGP; có thể áp dụng regional/global dynamic routing theo VPC và topology.
- **Edge availability domain:** miền bảo trì độc lập trong một metro, thường tên `zone1`/`zone2`; khác với **Compute Engine zone**.
- **Metro:** khu vực đô thị có các điểm kết nối; các điều kiện redundancy áp dụng theo metro/domain.

### 5.3. Mẫu Partner Interconnect

~~~mermaid
flowchart LR
    ON["Mạng doanh nghiệp"] --> CSP["Partner: mạng dịch vụ"]
    CSP --> EDGE["Google edge"]
    EDGE --> VLAN["VLAN attachment"]
    VLAN --> CR["Cloud Router / BGP"]
    CR -. "Dynamic routes" .-> VPC["Google Cloud VPC"]
~~~

Ở Partner **Layer 2**, phiên BGP thường chạy giữa router doanh nghiệp và Cloud Router trên kết nối do provider vận chuyển. Ở Partner **Layer 3**, nhà cung cấp quản lý BGP ở phía Google theo mô hình dịch vụ và khách hàng cần phối hợp với provider về định tuyến phía mình.

**Đường Google–provider được bảo đảm khác đường provider–khách hàng.** Khi đánh giá availability end-to-end, thêm SLA của carrier/last mile, thời gian sửa chữa và khả năng đặt đường vật lý độc lập.

### 5.4. Mẫu HA VPN over Interconnect

~~~mermaid
flowchart LR
    LAN["On-premises LAN"] --> PEER["Peer VPN gateway"]
    PEER --> ATT["VLAN attachments qua Interconnect"]
    ATT --> HAGW["HA VPN gateway gắn attachment"]
    HAGW --> VPC["VPC private workloads"]
    BGP1["Cloud Router cho Interconnect"] -. "Trao đổi prefix VPN gateways" .-> ATT
    BGP2["Cloud Router cho HA VPN"] -. "Trao đổi prefix workload" .-> HAGW
~~~

Ở đây **hai Cloud Router có vai trò khác nhau**: router ở tầng Interconnect hỗ trợ tiếp cận các VPN gateway qua attachment, còn router ở tầng HA VPN trao đổi prefix thực tế giữa VPC và mạng doanh nghiệp. Đây là mô hình phức tạp hơn một đường IPsec trực tiếp qua Internet.

**Điểm thiết kế:** Khi bật IPsec trên VLAN attachment, lựa chọn phải được thực hiện trong lúc tạo attachment; không giả định có thể chuyển một attachment đang chạy bình thường thành attachment mã hóa bằng một tùy chọn đơn giản. Cần đọc quy trình migration và dự phòng.

## 6. Chọn tuyến bằng BGP và thiết kế failover

Cả **HA VPN** và **Cloud Interconnect** thường dùng **Cloud Router + BGP** để trao đổi prefix giữa VPC và hệ thống phía doanh nghiệp. Lựa chọn đúng sản phẩm vẫn có thể thất bại nếu route không được quảng bá hoặc đường về sai.

### 6.1. Cần định nghĩa rõ prefix hai phía

Ví dụ:

~~~text
VPC Google Cloud:          10.20.0.0/16
On-premises:               172.16.0.0/16

Cloud Router nhận từ peer: 172.16.0.0/16
Peer router nhận từ GCP:   10.20.0.0/16
~~~

Trước khi cấu hình:

- CIDR **không chồng lấn** giữa VPC và mạng on-premises.
- Cả hai phía quảng bá đúng dải và biết **đường phản hồi**.
- Firewall ingress/egress cho phép **đúng protocol/port**.
- Dynamic routing mode của VPC đáp ứng region của workload và gateway.
- Kiểm tra static/PBR routes cụ thể hơn có thể thay đổi next hop mong đợi.

Không dùng default route `0.0.0.0/0` từ peer một cách tùy tiện: nó có thể làm nhiều luồng VPC đi qua on-premises ngoài dự định, tạo phụ thuộc hoặc chi phí mạng.

### 6.2. BGP không đồng nghĩa gói tin được giao thành công

BGP session ở trạng thái **Established** chứng minh hai BGP peers có thể trao đổi routing updates. Nhưng TCP từ VM tới database còn phụ thuộc:

1. Dynamic route đã được tạo và có hiệu lực với **region** chứa VM?
2. VPN tunnel hoặc VLAN attachment thực sự đang forward được dữ liệu?
3. Routing trong mạng doanh nghiệp có đường đến DB và đường về VPC?
4. Firewall/ACL/NAT và chính sách mạng có cho phép kết nối?
5. Dịch vụ đích có chạy và lắng nghe cổng cần thiết?

Với Partner Layer 3, trạng thái BGP từ Cloud Router có thể phản ánh phiên với **provider**, không bảo đảm chặng cuối đến router khách hàng đã hoạt động.

### 6.3. Active/active, active/passive và capacity dự phòng

| Kiểu | Đặc điểm | Điều kiện cần kiểm tra |
| --- | --- | --- |
| **Active/active** | Nhiều đường cùng được dùng khi route/priority phù hợp; có thể ECMP | Cân bằng theo flow, stateful firewall, NAT và capacity |
| **Active/passive** | Một đường ưu tiên hơn; đường phụ được chọn khi chính không còn dùng được | BGP advertisement/MED, failover detection, kiểm thử chuyển tuyến |
| **Nhiều nhà cung cấp/metro** | Giảm rủi ro một carrier hoặc địa điểm | Độc lập tuyến vật lý, thiết bị và SLA chặng cuối |
| **VPN dự phòng Interconnect** | Có đường IPsec qua Internet khi circuit private mất | Đủ capacity, cùng prefix/routing, chính sách bảo mật và failback |

**Không tự chọn mô hình chỉ bằng số lượng đường.** Nhiều đường cùng đi qua một router, cùng một ISP hoặc cùng edge availability domain vẫn có điểm lỗi chung.

### 6.4. Điều kiện SLA phải khớp topology

Theo tài liệu hiện hành:

- **HA VPN:** topology đủ điều kiện thường gồm **hai tunnel trên hai interface** và peer cấu hình tương ứng; một số topology có SLA 99,99%, một số chỉ 99,9% hoặc không có SLA.
- **Dedicated Interconnect:** topology **99,9%** và **99,99%** có yêu cầu khác nhau về số connection, địa điểm, edge domain và VPC routing mode. Ví dụ multi-region production cổ điển dùng ít nhất **bốn connection ở hai metro**, phân bổ hai edge domain; tài liệu hiện cũng có **phương án single-region** đủ điều kiện 99,99% với phân bổ connection/facility đặc thù.
- **Partner Interconnect:** topology production thường dùng **bốn VLAN attachments**, phân tán metro/edge domain và Cloud Router theo tài liệu; SLA Google chỉ bao gồm phần kết nối với provider.
- **HA VPN over Interconnect:** SLA tùy topology Interconnect bên dưới; một attachment đơn không đủ điều kiện SLA của mô hình HA.

Không nhân số SLA của từng dịch vụ rồi tuyên bố đó là SLA end-to-end của ứng dụng. Phải kiểm tra **cam kết hiện hành, ngoại lệ và phạm vi** từ Google, carrier, phần on-premises, cùng SLO của workload.

## 7. Mã hóa và trách nhiệm bảo mật

| Cơ chế | Bảo vệ ở đâu? | Không nên suy luận |
| --- | --- | --- |
| **IPsec Cloud VPN** | Mã hóa lưu lượng giữa VPN gateways | Không tự giới hạn người dùng/app ở hai phía |
| **Cloud Interconnect** | Đường truyền private không dùng Internet public | Không tự mã hóa payload |
| **MACsec for Cloud Interconnect** | Lớp Ethernet trên đoạn link hỗ trợ giữa router và Google edge | Không tự mã hóa toàn tuyến trong hạ tầng Google hoặc tới ứng dụng |
| **HA VPN over Interconnect** | IPsec trên lưu lượng đi qua Interconnect | Không bỏ qua giới hạn pps/tunnel và cấu hình HA |
| **TLS/mTLS ứng dụng** | Bảo vệ phiên ứng dụng giữa các endpoint tham gia | Không thay thế IAM, firewall, kiểm soát mạng |
| **Firewall / IAM** | Kiểm soát truy cập theo mạng và danh tính, tùy dịch vụ | Không tự tạo đường truyền hay tự mã hóa dữ liệu |

Ví dụ hệ thống ERP có dữ liệu nhạy cảm cần đường private và mã hóa: chọn Dedicated/Partner Interconnect kèm **HA VPN over Interconnect**, hoặc thiết kế TLS/mTLS end-to-end nếu đáp ứng chính sách. Nếu dùng Partner, phải xem đoạn lưu lượng bên trong mạng provider có được mã hóa trên toàn tuyến theo yêu cầu hay không.

Ngoài mã hóa, cần quản lý khóa IPsec, phân quyền IAM trên project/network, policy tổ chức, quyền thay đổi Cloud Router/attachments, firewall, log và cấu hình DNS. **Không nhúng shared secrets/khóa vào repository hoặc tài liệu học tập**.

## 8. DNS trong hệ thống hybrid

Tên chương là **DNS và kết nối hybrid** vì có kết nối IP chưa đủ để ứng dụng truy cập tài nguyên qua tên miền nội bộ. Giả sử API trong GCP cần truy cập `db.corp.example` trỏ đến `172.16.20.10`:

- Phải có route và firewall đến DNS resolver on-premises nếu query được chuyển về mạng doanh nghiệp.
- Có thể dùng **Cloud DNS forwarding zones** hoặc cơ chế inbound/outbound forwarding được hỗ trợ để phân giải tên qua VPC.
- DNS server phía doanh nghiệp cần có khả năng phân giải những zone trên GCP khi ứng dụng hai chiều yêu cầu.
- Phải kiểm tra policy, forwarder, IP nguồn từ Cloud DNS và rule mạng liên quan; không giả định truy vấn DNS đi trực tiếp từ từng VM tới DNS on-premises theo một đường chung.
- Phân giải DNS thành công **không chứng minh** TCP tới IP đích thành công; và ping IP thành công không chứng minh tên miền phân giải đúng.

**Khác biệt:** DNS xác định **địa chỉ đích**, còn VPN/Interconnect và routing xác định **đường đi đến địa chỉ đó**. Khi troubleshoot, kiểm tra lần lượt: truy vấn DNS, route IP, firewall, TCP/TLS và ứng dụng.

Các kết nối quản trị/hybrid trong Shared VPC hoặc Network Connectivity Center có thêm yêu cầu về project host/service, kết nối VPC, route exchange và DNS policy. Không tự giả định một tunnel đến một VPC làm mọi VPC khác tự kết nối qua đó.

## 9. Chi phí: so theo cùng tải và topology

### 9.1. Thành phần chi phí thường gặp

- **Cloud VPN:** phí Cloud VPN tunnels/gateway theo quy định hiện hành và dữ liệu truyền; peer VPN appliance, băng thông ISP, nhân sự quản lý.
- **Dedicated Interconnect:** cổng/circuit vật lý, VLAN attachments, data transfer, colocation/cross-connect/router/backhaul; mức giá phụ thuộc khu vực và cấu hình.
- **Partner Interconnect:** VLAN attachments, data transfer tính bởi Google, phí do service provider thu, đường kết nối đến provider, dự phòng.
- **HA VPN over Interconnect:** chi phí Interconnect **cộng** chi phí thành phần VPN và vận hành; không lấy giá Interconnect đơn lẻ để ước lượng.
- **Các dịch vụ khác:** logging, monitoring, dịch vụ cloud phát sinh egress, kiểm thử và thiết bị on-premises.

Đừng trộn phí “dữ liệu từ VPC ra on-premises”, phí lưu lượng Internet và phí cước provider thành một đơn giá chung. Mô hình giá và cách tính egress thay đổi theo sản phẩm, địa điểm, kích thước và hợp đồng.

### 9.2. Ví dụ bảng ước tính TCO

| Hạng mục | Thông tin cần điền |
| --- | --- |
| Nhu cầu | Peak Gbps, pps, TB/tháng, dự báo tăng trưởng |
| Kiến trúc | HA VPN / Dedicated / Partner / Hybrid encryption |
| Số đường | Số tunnel, connection, VLAN attachment và provider |
| Tài nguyên Google | Phí cố định theo tháng và phí traffic |
| Tài nguyên bên ngoài | Circuit, thiết bị, colocation, support |
| Độ tin cậy | SLA topology, số đường sau một failure, chi phí dự phòng |
| Khả năng mở rộng | Chi phí tăng băng thông và thời gian bổ sung |
| TCO | Tổng theo tháng/năm, gồm kịch bản cao điểm |

Với dữ liệu thực tế, có thể dùng **Cloud Billing export to BigQuery** để đối chiếu chi phí network/hybrid và kiểm tra biến động sau khi tối ưu. Giá sản phẩm nên được tra tại **Cloud VPN pricing** và **Cloud Interconnect pricing** tại thời điểm ra quyết định, thay vì cố định đơn giá trong bài học.

## 10. Quy trình quyết định có thể áp dụng

Đừng bắt đầu bằng tên dịch vụ. Đầu tiên phân loại **yêu cầu**, sau đó mới loại dần các phương án.

~~~mermaid
flowchart TD
  S["Cần kết nối private giữa VPC và mạng khác"] --> C{"Đầu bên kia là cloud khác?"}
  C -- "Có" --> X["Đánh giá Cross-Cloud Interconnect, partner cross-cloud hoặc HA VPN"]
  C -- "On-premises" --> B{"Cần bandwidth lớn, ổn định, đường private?"}
  B -- "Chưa cần" --> V["Đánh giá HA VPN + BGP + 2 đường"]
  B -- "Có" --> LOC{"Có khả năng colocation / backhaul đến Google?"}
  LOC -- "Có" --> D["Đánh giá Dedicated Interconnect"]
  LOC -- "Không" --> P["Đánh giá Partner Interconnect"]
  D --> ENC{"Cần mã hóa IPsec end-to-end qua kết nối?"}
  P --> ENC
  ENC -- "Có" --> HV["Xem HA VPN over Interconnect và giới hạn tunnel"]
  ENC -- "Không/đã có cơ chế khác" --> SEC["Kiểm tra MACsec/TLS, IAM, firewall"]
  V --> SLA["Tính SLA topology, capacity khi mất 1 đường"]
  HV --> SLA
  SEC --> SLA
  X --> SLA
  SLA --> T["So TCO và đo thử failover/latency/throughput"]
~~~

### 10.1. Quy tắc lựa chọn khởi đầu

1. **Lưu lượng vừa/nhỏ, cần kết nối nhanh và có mã hóa:** bắt đầu bằng **HA VPN**.
2. **Băng thông lớn, cần dự báo đường truyền và có mặt tại Google colocation:** đánh giá **Dedicated Interconnect**.
3. **Băng thông đáng kể nhưng không có hiện diện colocation hoặc cần capacity linh hoạt:** đánh giá **Partner Interconnect**.
4. **Vừa muốn đường riêng vừa yêu cầu mã hóa lớp mạng:** xem **HA VPN over Interconnect** và khả năng mở rộng nhiều tunnel.
5. **Kết nối giữa nhiều cloud:** đánh giá **Cross-Cloud Interconnect**, các lựa chọn partner hoặc HA VPN dựa trên topology cụ thể.
6. **Production yêu cầu sẵn sàng cao:** thiết kế **redundancy theo SLA topology** ngay từ đầu và đo failover end-to-end, không dùng một tunnel/circuit làm điểm lỗi đơn.

Đây là **bước lọc sơ bộ**. Quyết định chính thức phải qua kiểm tra kỹ thuật, giá, các vùng được hỗ trợ và phê duyệt bảo mật.

### 10.2. Bảng chấm điểm gợi ý

Một bảng nhỏ giúp tránh lựa chọn cảm tính:

| Tiêu chí | Trọng số giả định | Cách đánh giá |
| --- | ---: | --- |
| Đáp ứng throughput/pps đỉnh | 25% | Kiểm thử hoặc capacity planning |
| Availability và failover | 25% | SLA topology, độc lập đường, RTO thực nghiệm |
| Bảo mật/tuân thủ | 20% | IPsec/TLS, địa điểm, chính sách |
| Chi phí TCO | 15% | Giá Google + provider + thiết bị + vận hành |
| Thời gian triển khai | 10% | Băng thông/chứng từ/hợp đồng/provisioning |
| Vận hành và mở rộng | 5% | Kỹ năng đội ngũ, monitoring, tự động hóa |

Các trọng số **chỉ để minh họa**: một dự án có yêu cầu dữ liệu nghiêm ngặt có thể đặt bảo mật làm điều kiện bắt buộc trước khi chấm điểm. Phương án không đáp ứng yêu cầu cứng phải bị loại dù tổng điểm cao.

## 11. Tình huống triển khai: ứng dụng Java kết nối ERP on-premises

### 11.1. Bối cảnh

Một doanh nghiệp có:

- Dịch vụ Java trên Compute Engine và backend API Cloud Run.
- Dữ liệu đơn hàng trong Cloud SQL, nhưng cần tra cứu ERP ở trung tâm dữ liệu.
- Mạng on-premises `172.16.0.0/16` và VPC `10.20.0.0/16`.
- Lưu lượng hiện tại vừa, tăng mạnh trong giờ đồng bộ; không được công khai ERP lên Internet.
- Yêu cầu mã hóa, có khả năng dự phòng, đội vận hành nhỏ và chưa có hiện diện colocation.

**Ứng viên ban đầu:** HA VPN với tunnel pair/BGP, hai đường peer phù hợp. Lý do là có IPsec, triển khai nhanh hơn đường vật lý và có thể chọn topology HA đúng điều kiện. Tuy nhiên, cần đo peak Mbps/pps và mô phỏng lỗi để xác nhận trước khi chốt.

### 11.2. Khi nào thay đổi quyết định?

Sau sáu tháng, nếu đồng bộ dữ liệu tăng mạnh, traffic duy trì liên tục và cần đường truyền chuyên dụng, nhóm nên so **Partner Interconnect** (nếu provider có coverage phù hợp) với **Dedicated** (khi đã có router ở colocation). Nếu vẫn bắt buộc IPsec, lập phương án **HA VPN over Interconnect** và tính số tunnel theo packet rate.

### 11.3. Hồ sơ quyết định kiến trúc (ADR) mẫu

~~~text
Decision: HA VPN, hai tunnel trên hai interface, BGP qua Cloud Router
Workload: Java VM + Cloud Run truy cập ERP on-premises
VPC: 10.20.0.0/16 ; On-premises: 172.16.0.0/16
Yêu cầu cứng: Không public ERP; IPsec; redundant path
Yêu cầu định lượng: Peak throughput, pps, latency p95, RTO khi mất tunnel
Alternative: Partner Interconnect, Dedicated Interconnect, HA VPN over IC
Lý do hiện tại: Quy mô vừa, chưa có colocation, cần triển khai nhanh
Giả định: Peer hỗ trợ BGP/IPsec; hai phía không overlap CIDR
Rủi ro: Internet jitter, peer gateway hỏng, MTU/MSS, failover ngắt TCP
Kiểm chứng: BGP routes, VPN tunnel status, Connectivity Tests, ứng dụng thực
Scale trigger: Throughput/pps chạm ngưỡng, TCO VPN > phương án private
Owner: Platform/Network/Security; ngày review tiếp theo: ...
~~~

Cần bổ sung số liệu thực tế, vùng đặt tài nguyên và trích dẫn giá/điều kiện SLA của nhà cung cấp trước khi duyệt production.

## 12. Kiểm tra read-only bằng Google Cloud CLI

Phần này dành cho **xác minh** sau khi kết nối được triển khai bởi nhóm có quyền. Các lệnh dưới đây không tạo hoặc xóa hạ tầng; thay placeholder bằng ID thật.

~~~bash
# Kiểm tra project đang được sử dụng
gcloud config get-value project

# Xem các VPC và subnet
gcloud compute networks list --project=PROJECT_ID
gcloud compute networks subnets list --project=PROJECT_ID

# Xem HA VPN gateways và tunnels
gcloud compute vpn-gateways list --project=PROJECT_ID
gcloud compute vpn-tunnels list --project=PROJECT_ID

# Xem trạng thái một VPN tunnel thuộc đúng region
gcloud compute vpn-tunnels describe TUNNEL_NAME \
  --region=REGION --project=PROJECT_ID

# Xem Cloud Routers và phiên BGP
gcloud compute routers list --project=PROJECT_ID
gcloud compute routers get-status ROUTER_NAME \
  --region=REGION --project=PROJECT_ID

# Xem đường vật lý Interconnect và VLAN attachments (nếu có)
gcloud compute interconnects list --project=PROJECT_ID
gcloud compute interconnects attachments list --project=PROJECT_ID

# Xem attachment theo đúng region
gcloud compute interconnects attachments describe ATTACHMENT_NAME \
  --region=REGION --project=PROJECT_ID
~~~

**Phân biệt phạm vi dữ liệu:** Cloud Router status dùng để xem BGP/learned/advertised routes liên quan, còn các lệnh liệt kê tài nguyên chỉ xác định sự tồn tại và metadata. Không suy “mọi thứ hoạt động” từ một dòng trạng thái resource.

Google Cloud VPC có **Effective routes** trong Console để kiểm tra tuyến có thể dùng, nhưng route được nhìn thấy vẫn phải đối chiếu với **nguồn gửi, region, firewall, return path** và trạng thái ứng dụng. Với kết nối phức tạp, dùng **Network Intelligence Center – Connectivity Tests** để mô phỏng trace nếu API/IAM và giới hạn sản phẩm cho phép.

### 12.1. Tạo bảng kiểm chứng trước khi đưa vào vận hành

| Kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Kết nối tunnel/circuit | Status hoạt động từ cả hai phía |
| BGP peers | Session Established, prefix learned/advertised chính xác |
| Network/VPC routing | VPC có route tới on-prem, on-prem có return route |
| Redundancy | Khi một tunnel/circuit không sẵn sàng, đường còn lại xử lý được tải |
| Firewall | Chỉ mở protocol/port cần thiết, log tùy nhu cầu |
| DNS hybrid | Tên dịch vụ nội bộ phân giải đúng từ nguồn app |
| Hiệu năng | Throughput, packet rate, RTT, jitter, loss được đo |
| MTU | Không bị blackhole gói lớn; TCP MSS phù hợp nếu cần |
| Bảo mật | IPsec/TLS/MACsec theo thiết kế, quyền hạn và rotation |
| Chi phí | Chi phí theo tháng, egress, provider/circuit, log |

## 13. Khắc phục sự cố phổ biến

| Triệu chứng | Khả năng cần kiểm tra | Bước chẩn đoán |
| --- | --- | --- |
| VPN tunnel không lên | Sai IP peer, PSK/IKE/IPsec proposal, NAT-T, firewall phía peer | Kiểm tra tunnel status và peer logs; so cấu hình hai bên |
| VPN lên nhưng BGP không Established | ASN, BGP IP, peer interface, route/access | Xem `gcloud compute routers get-status` và cấu hình peer |
| BGP Established nhưng app timeout | Missing route, return route, firewall, NAT, dịch vụ đích | Xem Effective routes hai phía, Connectivity Tests, app logs |
| Một tunnel hỏng làm mất toàn bộ kết nối | Chỉ một đường hoặc redundancy cấu hình chưa đủ | Xem HA VPN topologies và kiểm tra failover thực |
| VPN throughput thấp | Giới hạn 250k pps/tunnel, RTT/loss, MTU, peer CPU | Đo pps, packet size, nhiều TCP flows và gateway capacity |
| Interconnect attachment chưa chạy | Chưa kích hoạt, provider chưa provision, BGP chưa cấu hình | Xem attachment operational status và portal provider |
| Interconnect đủ băng thông nhưng có packet loss | Thiết bị/circuit quá tải, shaping, link errors, capacity failover | Kiểm tra metric port/attachment và thiết bị peer |
| Có private connection nhưng vi phạm chính sách mã hóa | Interconnect mặc định không IPsec | Xem HA VPN over IC, MACsec/TLS theo yêu cầu |
| Truy cập bằng IP được, tên miền lỗi | Hybrid DNS forwarding, resolver, zone hoặc firewall DNS | Kiểm tra DNS query path và policy tương ứng |
| Sai subnet được quảng bá | Routing mode regional/global hoặc custom advertisements | Kiểm tra Cloud Router advertised/learned routes |
| Khi failover, một phần TCP session ngắt | ECMP/stateful appliance/NAT, BGP convergence | Kiểm thử ứng dụng retry và thiết kế stateful path |
| Dùng Partner nhưng nhà cung cấp báo lỗi chặng cuối | SLA Google chỉ tới mạng provider | Thu thập tracing, provider SLA và ticket theo ranh giới |

### 13.1. MTU và MSS

IPsec thêm header/overhead; VLAN và các lớp encapsulation cũng ảnh hưởng MTU. Một kết nối có thể truyền gói nhỏ tốt nhưng lỗi/treo khi truyền payload lớn hoặc một số handshake. Các vấn đề thường liên quan:

- Kích thước packet vượt payload MTU hữu dụng.
- ICMP “fragmentation needed” bị chặn, làm **Path MTU Discovery** thất bại.
- Hai bên áp dụng MSS/MTU khác nhau sau khi đi qua IPsec.
- Gói có encapsulation chồng lớp (ví dụ IPsec over Interconnect) nhưng chưa tính overhead.

Cách xử lý là đọc **MTU specification của đúng sản phẩm/topology**, kiểm tra thiết bị peer và cấu hình TCP MSS clamping/PMTUD phù hợp. Không đặt một MTU “chuẩn cho mọi VPN/Interconnect” khi chưa biết IP version và cipher.

### 13.2. Đo từ ứng dụng thật

Đo latency đến ERP bằng yêu cầu nghiệp vụ thực thay vì chỉ ping router. Với API có nhiều truy vấn SQL đồng bộ, RTT dù nhỏ cũng có thể khiến độ trễ cộng dồn tăng. Khi tăng băng thông, hãy so throughput trong nhiều luồng, packet size và CPU encryption trên peer gateway. Khi phát hiện packet loss, kiểm tra cả **chiều đi và chiều về**.

**Kiểm thử failover** nên ghi rõ: đường nào bị mô phỏng lỗi, sau bao lâu traffic phục hồi, có request thất bại không, throughput lúc chỉ còn một đường, ứng dụng có retry đúng và chi phí có thay đổi không. Bài kiểm chứng có thể đòi cửa sổ bảo trì/cho phép thao tác trên hạ tầng; không thử ngắt tunnel production tùy tiện.

## 14. Bài thực hành quyết định (không cần tạo tài nguyên)

Hãy lập bảng quyết định cho bốn yêu cầu dưới đây. Bạn có thể sử dụng kiến thức trong bài và tài liệu chính thức; mục tiêu là **giải thích điều kiện lựa chọn**, không phải đoán tên sản phẩm.

| Tình huống | Yêu cầu | Ứng viên ban đầu |
| --- | --- | --- |
| **A. Lab hybrid** | Cần nối mạng dev với on-prem; vài trăm Mbps, ít dữ liệu nhạy cảm nhưng phải mã hóa IPsec, triển khai sớm | HA VPN |
| **B. Đồng bộ dữ liệu lớn** | Chuyển dữ liệu liên tục, đỉnh nhiều Gbps, có router tại Google colocation, yêu cầu đường riêng | Dedicated Interconnect |
| **C. Chi nhánh xa** | Không có colocation, muốn đường private và tăng băng thông theo hợp đồng với nhà mạng | Partner Interconnect |
| **D. Dữ liệu tài chính** | Đòi đường private, mã hóa lớp mạng, HA và ứng dụng dùng ERP on-prem | HA VPN over Interconnect |

**Nhiệm vụ:**

1. Với mỗi tình huống, ghi **ít nhất ba điều kiện** cần xác nhận: băng thông/pps, region, ISP, mức mã hóa, SLA và chi phí.
2. Xác định **topology dự phòng**: số đường/tunnel/attachment theo tài liệu SLA, edge availability domains, thiết bị peer.
3. Xác định route từ mạng GCP đến on-prem và chiều về; ghi rõ Cloud Router/BGP ở đâu.
4. Chọn ít nhất **một phương án thay thế**; giải thích lý do chưa chọn.
5. Lập kế hoạch kiểm thử gồm kết nối cơ bản, DNS, MTU, throughput, failover và log.
6. Dự toán các khoản tiền Google, carrier/colocation, gateway và vận hành trong cùng kỳ.

**Gợi ý:** Tình huống A chọn HA VPN có lý, nhưng chỉ khi băng thông/pps và trạng thái peer phù hợp. B có thể cần nhiều circuit để đạt SLA, không đủ với một đường vật lý. C cần xác minh SLA đoạn provider ↔ doanh nghiệp và bandwidth tại địa điểm thật. D phải kiểm tra số tunnel mã hóa đủ capacity, bởi chỉ đưa một tunnel lên circuit lớn sẽ trở thành nút thắt.

### 14.1. Mẫu bảng quyết định để điền

| Thuộc tính | Phương án 1 | Phương án 2 |
| --- | --- | --- |
| Dữ liệu và lưu lượng | … | … |
| Path (Internet/private) | … | … |
| Mã hóa | … | … |
| Peak Gbps, pps | … | … |
| SLO/SLA và topology | … | … |
| Region/metro/provider | … | … |
| Thời gian triển khai | … | … |
| TCO 12 tháng | … | … |
| Điểm lỗi và dự phòng | … | … |
| Kết quả thử nghiệm | … | … |
| Kết luận có điều kiện | … | … |

**Tiêu chí hoàn thành:** Bạn không chỉ chọn đúng tên sản phẩm, mà có thể trình bày **giả định, nguồn tài liệu, phép đo xác nhận và rủi ro còn lại**.

## 15. Câu hỏi tự kiểm tra

1. **Cloud VPN có phải VPN client cho laptop không?** Không. Cloud VPN cung cấp site-to-site IPsec đến mạng peer.
2. **HA VPN có dùng static routes như Classic VPN không?** Không. HA VPN sử dụng BGP dynamic routing qua Cloud Router.
3. **Mọi HA VPN đều có SLA 99,99%?** Không. Phải cấu hình topology/tunnel/peer đúng điều kiện; một số topology có mức thấp hơn hoặc không đủ.
4. **Dedicated Interconnect khác Partner ở điểm trọng tâm nào?** Dedicated cần connection vật lý riêng tới Google tại colocation; Partner đi qua provider được hỗ trợ.
5. **Tại sao Interconnect không tự đáp ứng yêu cầu mã hóa?** Đường riêng không có IPsec mặc định; cần IPsec/TLS/MACsec phù hợp.
6. **Cloud Router có chuyển tiếp mọi packet không?** Không. Cloud Router quản lý BGP/control plane; VPC data plane xử lý forwarding.
7. **Có thể dùng một HA VPN tunnel để khai thác trọn circuit 100 Gbps?** Không; còn limit packet rate của từng tunnel và overhead IPsec.
8. **Partner Interconnect có SLA end-to-end đến tận mạng khách hàng do Google bảo đảm?** Không tự động; Google SLA có phạm vi tới provider, cần xem hợp đồng provider.
9. **Vì sao hai mạng không được overlap CIDR?** Overlap làm route đến một số đích mơ hồ/xung đột và gây khó thiết kế hybrid; cần tái đánh địa chỉ hoặc giải pháp NAT có chủ đích.
10. **Tại sao đường về quan trọng?** TCP và các giao thức yêu cầu response; một chiều route đúng chưa đủ.
11. **Khi nào dùng Cross-Cloud Interconnect?** Khi đầu bên kia là mạng ở CSP khác được hỗ trợ và yêu cầu kết nối chuyên dụng phù hợp.
12. **Vì sao cần test failover dưới tải?** Đường còn lại có thể không đủ băng thông hoặc các ứng dụng stateful có thể ngắt dù BGP đã chuyển tuyến.

## 16. Checklist trước khi chốt thiết kế

- [ ] Đã xác định VPC/project, region, CIDR hai phía, không overlap hoặc có phương án xử lý.
- [ ] Đã ghi peak Gbps, pps, TB/tháng, RTT/packet loss và tăng trưởng dự kiến.
- [ ] Đã xác định yêu cầu về IPsec/TLS, dữ liệu nhạy cảm và đường private.
- [ ] Đã so HA VPN, Dedicated, Partner và giải pháp kết hợp nếu phù hợp.
- [ ] Đã xác nhận địa điểm colocation/metro/edge domain hoặc provider coverage.
- [ ] Đã thiết kế Cloud Router/BGP, advertised/learned prefixes và return path.
- [ ] Đã chọn topology và phạm vi SLA theo tài liệu hiện hành của Google và provider.
- [ ] Đã tính băng thông còn lại khi mất một đường và thời gian failover mục tiêu.
- [ ] Đã xác định IAM, firewall, DNS forwarding, NAT và MTU/MSS.
- [ ] Đã dự trù TCO gồm phí ngoài Google và vận hành.
- [ ] Đã có test plan, giám sát, alerting, runbook và kịch bản rollback.
- [ ] Đã ghi ADR với giả định, trade-off, kết quả kiểm chứng và thời điểm đánh giá lại.

## 17. Nguồn tham khảo Google Cloud chính thức

Những tài liệu dưới đây nên được đọc lại tại thời điểm triển khai vì capacity, pricing, topology SLA, các tính năng mới và địa điểm hỗ trợ có thể thay đổi:

- [Choosing a Network Connectivity product](https://docs.cloud.google.com/network-connectivity/docs/how-to/choose-product) — quy trình so Cloud VPN/Dedicated/Partner và điều kiện chung.
- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview) — IPsec, HA/Classic VPN, throughput, giới hạn.
- [HA VPN topologies](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/topologies) — tunnel pair và SLA theo topology.
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices) — BGP, peer redundancy và vận hành.
- [Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/overview) — các loại Interconnect, bảo mật, throughput.
- [Dedicated Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/dedicated-overview) — mạch vật lý, port capacity và topology.
- [Partner Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/partner-overview) — provider, L2/L3, attachment và SLA.
- [Cross-Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview) — kết nối trực tiếp giữa các nhà cung cấp cloud.
- [HA VPN over Cloud Interconnect](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/ha-vpn-interconnect) — IPsec, kiến trúc hai tầng, MTU/limits.
- [MACsec for Cloud Interconnect](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/macsec-overview) — phạm vi mã hóa lớp 2.
- [Cloud Router overview](https://docs.cloud.google.com/network-connectivity/docs/router/concepts/overview) — BGP/control plane và dynamic routing.
- [Dedicated 99.99% availability topology](https://docs.cloud.google.com/network-connectivity/docs/interconnect/tutorials/dedicated-creating-9999-availability) — yêu cầu single-region/multi-region.
- [Cloud VPN troubleshooting/status](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/checking-vpn-status) — kiểm tra tunnel và BGP.
- [Cloud VPN pricing](https://cloud.google.com/network-connectivity/docs/vpn/pricing) và [Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/docs/interconnect/pricing) — tra giá cập nhật trước khi tính TCO.
- [Cloud DNS forwarding zones](https://docs.cloud.google.com/dns/docs/zones/forwarding-zones) — tích hợp phân giải tên trong hybrid.
- [Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — kiểm chứng đường mạng theo nguồn/đích.

**Điều cần ghi nhớ:** **HA VPN** phù hợp khi cần IPsec và lưu lượng chưa đòi hỏi đường chuyên dụng; **Dedicated/Partner Interconnect** phù hợp khi cần kết nối private, băng thông lớn hoặc ổn định hơn; **HA VPN over Interconnect** kết hợp ưu điểm đường riêng với mã hóa IPsec. Quyết định đúng phải dựa trên yêu cầu đo được, topology dự phòng, kết quả thử nghiệm và tổng chi phí vận hành.
