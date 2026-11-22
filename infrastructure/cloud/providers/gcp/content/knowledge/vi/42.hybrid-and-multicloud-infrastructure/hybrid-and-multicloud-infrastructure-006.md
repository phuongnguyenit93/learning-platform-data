# Google Distributed Cloud và nhu cầu triển khai tại chỗ

## 1. Bối cảnh và mục tiêu

Trong chương **Hạ tầng lai và đa đám mây** của mô-đun **CLOUD_PROVIDERS_GCP**, một câu hỏi kiến trúc thường gặp là: khi nào ứng dụng nên chạy ở Google Cloud region, và khi nào phải đưa năng lực xử lý về trung tâm dữ liệu hoặc địa điểm biên của khách hàng?

Doanh nghiệp có thể cần giữ dữ liệu ở địa điểm cụ thể, xử lý video và tín hiệu công nghiệp với độ trễ rất thấp, vận hành khi WAN gián đoạn hoặc khai thác hạ tầng bare metal/VMware đã đầu tư. **Google Distributed Cloud (GDC)** là danh mục giải pháp mở rộng nền tảng Kubernetes, khả năng tính toán và các dịch vụ được hỗ trợ của Google Cloud tới môi trường **on-premises và edge**.

Kiến thức bài học nối với các phần của lộ trình GCP: tổ chức project, IAM, VPC; Compute Engine, GKE, Cloud Run; lưu trữ, cơ sở dữ liệu, tự động hóa phát hành, giám sát độ tin cậy và quản lý chi phí. GDC cần được nhìn dưới góc **chọn nơi đặt workload và phân chia trách nhiệm vận hành**, không chỉ là một lựa chọn cài Kubernetes.

Sau bài học, người học có thể:

1. Nhận diện nhu cầu data residency, sovereignty, latency, lượng dữ liệu lớn, Internet không ổn định và tận dụng hạ tầng sẵn có.
2. Phân biệt **GDC connected**, **GDC air-gapped**, **GDC software only for bare metal** và **GDC software only for VMware**.
3. Vẽ ranh giới giữa data plane cục bộ, management/control plane và mạng Google Cloud.
4. Lập kế hoạch site readiness, network, capacity, bảo mật, backup, khả dụng và observability.
5. Chọn mô hình triển khai phù hợp với yêu cầu compliance và mô hình hỗ trợ.
6. Định nghĩa POC, TCO và kế hoạch vận hành thực tế trước khi đưa vào production.

## 2. Tại sao ứng dụng cần chạy tại chỗ?

### 2.1 Độ trễ và độ ổn định của vòng xử lý

Một nhà máy có camera phát hiện hàng lỗi cần trả kết quả trong 50 ms. Nếu toàn bộ hình ảnh phải truyền tới region qua WAN, độ trễ và jitter thay đổi có thể làm vi phạm SLO. Xử lý gần camera giúp rút ngắn hành trình dữ liệu. Nhưng phải đo **p95/p99 của toàn chuỗi**, gồm đọc cảm biến, network LAN, tiền xử lý, suy luận và trả kết quả.

### 2.2 Dữ liệu nhiều nhưng phần có giá trị gửi lên cloud ít

Video, log thiết bị, ảnh y tế, dữ liệu sensor liên tục phát sinh. Có thể xử lý tại site, chỉ gửi metadata, alarm, thống kê và báo cáo tổng hợp lên Google Cloud. Phải mô tả dữ liệu gốc ở lại bao lâu, bản sao dự phòng ở đâu và khi nào được phép xóa.

### 2.3 Lưu trú và chủ quyền dữ liệu

- **Data residency:** dữ liệu vật lý được lưu ở vùng/quốc gia nào.
- **Data sovereignty:** quyền kiểm soát dữ liệu dưới chính sách, hợp đồng và khuôn khổ pháp lý nào.
- **Operational sovereignty:** ai có quyền quản trị, ai nắm khóa, ai được truy cập hỗ trợ, có phụ thuộc kết nối bên ngoài hay không.

Đặt một máy chủ tại địa phương không tự bảo đảm tất cả yêu cầu. Cần xem cả log, telemetry, backup, metadata quản trị, chứng chỉ, khóa, quyền hỗ trợ và quy trình trao đổi dữ liệu.

### 2.4 Liên lạc WAN không luôn sẵn sàng

Cần phân biệt ba yêu cầu:

- Mất mạng vài phút/giờ nhưng ứng dụng cục bộ vẫn chạy.
- Có thể mất WAN nhiều ngày; sau đó đồng bộ dữ liệu còn tồn đọng.
- **Không được kết nối Internet hoặc Google Cloud trong quá trình vận hành.**

Ba mức yêu cầu dẫn tới lựa chọn khác nhau. Một sản phẩm cần kết nối định kỳ không được xem là air-gapped.

### 2.5 Tận dụng nền tảng cũ

Doanh nghiệp có máy Linux, VMware vSphere, SAN, switch và đội vận hành on-prem muốn chạy workload container theo chuẩn Kubernetes. GDC software only phù hợp để khảo sát, nhưng không có nghĩa mọi trách nhiệm hạ tầng được chuyển cho Google.

## 3. Bốn biến thể triển khai chính

Google Cloud hiện phân loại GDC thành ba hướng giải pháp: **connected**, **air-gapped** và **software only**; hướng software only gồm bare metal và VMware.

| Tiêu chí | Connected | Air-gapped | Software only |
| --- | --- | --- | --- |
| Cốt lõi | Cluster GKE trên phần cứng Google-certified tại site | Hạ tầng và dịch vụ tích hợp trong perimeter cô lập | Cluster GKE on-prem trên hạ tầng của khách hàng |
| Phần cứng | Mua qua đối tác tích hợp được chứng nhận | Rack hoặc appliance tích hợp theo cấu hình sản phẩm | Bare metal Linux hoặc VMware vSphere sẵn có |
| Kết nối Google Cloud | Cần định kỳ cho management | Không cần kết nối Google Cloud hoặc public Internet để vận hành | Tích hợp fleet/management qua Google Cloud theo cấu hình |
| Quản lý nền tảng | Google quản lý phần mềm connected | Vận hành trong môi trường cô lập theo hợp đồng | Khách hàng quản lý cluster/hạ tầng với công cụ Google |
| Workload | Containers, VM theo tính năng | VMs, containers, dịch vụ AI/data theo catalog | Kubernetes applications, tính năng khác tùy bản |
| Phù hợp | Edge có WAN, cần quản trị tập trung | Nơi cấm kết nối ngoài, dữ liệu tuyệt mật | Tận dụng hạ tầng và kỹ năng on-prem |
| Rủi ro đặc thù | Giới hạn WAN và dung lượng zone | Supply chain/updates/operations offline | Tự vận hành phần cứng, OS, vSphere, upgrade |

**Không được suy ra tính năng của một GDC variant áp dụng cho biến thể khác.** Các API, storage, runtime, khả dụng GPU, phiên bản phần mềm, tính năng AI, giới hạn cluster và hỗ trợ khác nhau.

### 3.1 Google Distributed Cloud connected

GDC connected chạy cluster Google Kubernetes Engine trên **máy chủ được chứng nhận** tại địa điểm khách hàng, gắn trực tiếp vào mạng nội bộ. Đội cloud có thể dùng Google Cloud console hoặc Google Cloud CLI để quản lý zone/cluster/node pool, cùng kubectl để thao tác workload.

Đặc trưng quan trọng:

- Connected zone thường được triển khai theo cấu hình **ba máy chủ** để tăng khả dụng; cấu hình và SKU thực tế phải xác nhận theo phiên bản/hardware.
- Google quản lý phần mềm và hoạt động giám sát liên quan, trong khi khách hàng/SI **mua, triển khai, bảo trì và sửa chữa phần cứng** cùng nguồn điện, làm mát và mạng.
- Phù hợp workload container/VM cần gần thiết bị, giảm độ trễ và truyền dữ liệu lớn.
- Có thể kết nối với VPC Google Cloud qua **Cloud VPN** trong kiến trúc được hỗ trợ.
- Dù control plane hoạt động cục bộ, **connected phải liên lạc Google Cloud định kỳ** cho management, logging, token và khóa.

**Giới hạn mất kết nối cần nhớ:** theo tài liệu Google Cloud hiện hành, workload trên GDC connected có thể tiếp tục hoạt động khi mất kết nối Google Cloud **tối đa bảy ngày**. Sau đó cần nối lại để làm mới authentication tokens, encryption keys và đồng bộ quản trị/audit. Không được dùng connected cho yêu cầu vận hành air-gap vĩnh viễn. Thử nghiệm mạng và năng lực xử lý khi mất kết nối là phần bắt buộc của POC.

Các máy GDC connected trong một zone có **công suất hữu hạn**, không thể coi chúng là một Google Cloud region có autoscaling vô hạn. Theo hướng dẫn lắp đặt, phần cứng chứng nhận được mua qua **Google-certified systems integrator**, phải có gói hỗ trợ **Enhanced Support** tối thiểu. Khả dụng theo quốc gia phải được Google xác nhận.

### 3.2 Google Distributed Cloud air-gapped

GDC air-gapped được thiết kế cho môi trường có yêu cầu cách ly vật lý và logic nghiêm ngặt, **không phụ thuộc kết nối Google Cloud hoặc Internet** trong vận hành. Đây là giải pháp tích hợp phần cứng và phần mềm, thường đặt trong data center có kiểm soát, cùng các biến thể appliance dành cho edge đặc thù.

Các điểm quan trọng:

- Hệ thống có cơ chế quản lý, mạng, định danh, storage, workload và catalog dịch vụ **trong perimeter cô lập**.
- Phạm vi VM, containers, AI/ML và dịch vụ khác cần xác nhận theo bản GDC air-gapped, không mặc định giống Google Cloud public.
- Cập nhật, image, artifact và dữ liệu đi vào vùng cô lập phải qua **quy trình nhận, quét mã độc, kiểm chữ ký/hash và phê duyệt**.
- Chính sách cấp quyền, phân loại dữ liệu, kiểm soát media, quản lý khóa và log phải tồn tại ngay cả khi không có Internet.
- Site survey về rack, nguồn, làm mát, bảo mật vật lý và khả năng vận hành là bước thiết kế chính thức.

Ngoài rack/data-center, **GDC air-gapped appliance** dành cho trường hợp di động/field có giới hạn HA, dung lượng và vận hành khác. Không mặc định appliance có thể thay thế một cụm data center có dự phòng đầy đủ.

**Không được nhầm:** ngắt Internet của một cụm GDC connected không biến cụm đó thành GDC air-gapped.

### 3.3 GDC software only trên bare metal

GDC software only for bare metal cung cấp nền tảng GKE on-prem để chạy Kubernetes trực tiếp trên máy Linux của khách hàng, tránh lớp hypervisor khi cần truy cập phần cứng trực tiếp hoặc đã có đội quản trị bare metal.

Mô hình thường có **admin cluster** để quản trị vòng đời các **user clusters** chạy ứng dụng. Khách hàng thiết kế IP, load balancer, storage, mạng, OS, thiết bị và khả năng phục hồi; kết nối **Fleet/Connect Agent** cho các tính năng quản trị chung qua Google Cloud.

Dữ liệu và workload chính của cluster ở data center on-prem. Tài liệu nêu Google Cloud nhận một số dữ liệu cluster như metadata, health và usage phục vụ quản trị, chứ không tự tải toàn bộ dữ liệu ứng dụng lên cloud.

GDC software only còn từng được gọi là **Google Distributed Cloud Virtual** và trước đó là **Anthos clusters on bare metal**. Khi tra tài liệu cũ phải đối chiếu phiên bản.

### 3.4 GDC software only trên VMware

Dòng VMware chạy node Kubernetes trong các máy ảo trên **vSphere** của tổ chức. Nền tảng sử dụng datastore vSphere (vSAN, VMFS hoặc NFS theo hỗ trợ) và **vSphere CSI driver** để provision persistent volume cho ứng dụng stateful.

Các thành phần thường gồm admin cluster, user cluster, admin workstation, load balancer/VIP, storage class, cấu hình vCenter, fleet membership và công cụ như gkectl, kubectl.

Ưu điểm là tận dụng kiến thức vCenter, hạ tầng SAN/vSAN và quy trình change management. Đổi lại cần kiểm soát hai lớp **vSphere/VM và Kubernetes**, cùng ma trận tương thích giữa version GDC, vSphere, network, storage, firmware và certificate.

**Software only cũng không mặc định là air-gapped.** Các chức năng quản trị/fleet có yêu cầu kết nối riêng; kiểm tra tài liệu version thực dùng.

## 4. Kiến trúc hybrid tham chiếu

~~~mermaid
flowchart LR
    subgraph SITE["Nhà máy / data center tại chỗ"]
      DEV["Camera, sensor, máy móc"] --> GW["Gateway mạng LAN"]
      GW --> APP["GDC workload: xử lý thời gian thực"]
      APP --> LOCAL[("Local storage / database")]
      APP --> QUEUE["Queue bền vững + checkpoint"]
    end
    QUEUE -->|"Chỉ dữ liệu được phép khi WAN sẵn sàng"| LINK["Kết nối bảo mật / VPN"]
    LINK --> CLOUD["Google Cloud VPC / dịch vụ đích"]
    CLOUD --> DWH[("Cloud Storage / BigQuery")]
    MGT["Google Cloud management: chỉ cho connected/software only khi phù hợp"] -.-> APP
~~~

Kiến trúc gồm hai luồng cần phân biệt:

- **Data plane:** thiết bị gửi dữ liệu tới ứng dụng tại site; kết quả được xử lý, lưu hoặc gửi ra ngoài theo chính sách.
- **Management plane:** Google Cloud có thể quản trị/giám sát phần GDC connected hoặc software only theo sản phẩm và kết nối đã cấu hình.

Trong **air-gapped**, management plane phải ở trong môi trường tách biệt. Không có VPN luôn bật tới Google Cloud. Việc nhập/xuất dữ liệu hoặc cập nhật đòi hỏi quy trình offline có phê duyệt.

### Phân loại dữ liệu và vị trí

| Dữ liệu | Ví dụ | Cần quyết định |
| --- | --- | --- |
| Thô | Video, ảnh y tế, telemetry | Có bắt buộc lưu local không? Retention bao lâu? |
| Kết quả | Cảnh báo lỗi, metadata, aggregate | Được gửi về cloud vùng nào? |
| Quản trị | Metadata cluster, health, billing usage | Kênh nào đi ra Google Cloud? |
| Log/audit | Hoạt động người dùng, truy cập admin | Có chứa PII/secret và phải giữ ở đâu? |
| Artifact | Container image, ML model, SBOM | Registry trực tuyến hay nhập offline? |
| Khóa và chứng chỉ | TLS key, KMS, secret | Ai quản lý, backup, rotate và khôi phục? |

**Chạy on-prem** không đồng nghĩa “mọi bit dữ liệu đều không bao giờ rời site” nếu management telemetry, support access hoặc log vẫn được gửi ra ngoài.

## 5. Quy trình lựa chọn sản phẩm theo yêu cầu

~~~mermaid
flowchart TD
    A["Ứng dụng cần triển khai tại chỗ"] --> B{"Cấm kết nối Google Cloud/Internet trong vận hành?"}
    B -- "Có" --> G["Đánh giá GDC air-gapped"]
    B -- "Không" --> C{"Muốn sử dụng phần cứng hiện có?"}
    C -- "Bare metal" --> BM["GDC software only for bare metal"]
    C -- "VMware" --> VM["GDC software only for VMware"]
    C -- "Không" --> D{"Chấp nhận quản trị qua Google Cloud định kỳ?"}
    D -- "Có" --> CON["GDC connected"]
    D -- "Không" --> RE["Xem lại yêu cầu; cân nhắc air-gapped"]
    G --> P["POC và đánh giá security, TCO, support"]
    BM --> P
    VM --> P
    CON --> P
    RE --> P
~~~

| Bài toán | Hướng đánh giá trước | Điều kiện quan trọng |
| --- | --- | --- |
| Inference camera tại nhà máy với WAN tương đối ổn định | Connected | Mua được hardware certified, chấp nhận kết nối quản trị |
| Dữ liệu yêu cầu tách tuyệt đối khỏi mạng ngoài | Air-gapped | Đáp ứng vận hành offline, site survey, quy trình cập nhật |
| Doanh nghiệp có hạ tầng VMware đủ mạnh | Software only VMware | Version vSphere, CSI, load balancer và storage phù hợp |
| Máy Linux bare metal tại nhiều site | Software only bare metal | OS, firmware, mạng, hardware đạt yêu cầu |
| Chỉ cần kết nối từ on-prem tới workload cloud | Cloud VPN/Interconnect và GCP | Có thực sự cần Kubernetes tại site không? |
| Cloud-native ứng dụng không yêu cầu local | GKE/Cloud Run/Compute Engine trong region | Đừng thêm chi phí và vận hành on-prem vô ích |

Không chọn air-gapped chỉ vì WAN yếu; đây là mô hình vận hành và hợp đồng khác hẳn. Ngược lại, connected không đáp ứng yêu cầu cô lập tuyệt đối.

## 6. Kiểm tra site trước triển khai

Đội kiến trúc cần có **site readiness checklist**:

1. **Không gian:** rack unit, tải trọng sàn, khu vực bảo trì, đường đi cáp.
2. **Điện:** UPS, PDU, công suất, nguồn dự phòng, quy trình mất điện.
3. **Làm mát:** HVAC, nhiệt độ, độ ẩm, giám sát môi trường.
4. **Mạng:** switch, VLAN, DNS, NTP, MTU, CIDR, route, firewall, uplink/VPN.
5. **Bảo vệ vật lý:** quyền ra vào rack, lưu dấu vết, camera và kiểm kê thiết bị.
6. **Vận hành:** NOC, SOC, on-call, phương án thay linh kiện và liên lạc SI/Google.
7. **Kế hoạch kết thúc vòng đời:** xuất dữ liệu, xóa ổ, trả thiết bị và đóng hợp đồng.

Với connected, làm việc với Google/đối tác trước khi mua để xác nhận **configuration certified, country availability, support** và khả năng mở rộng của zone. Với air-gapped, cần đánh giá khả năng hỗ trợ tại cơ sở được kiểm soát và quy trình chuỗi cung ứng. Với software only, đội nội bộ phải tự xác minh hardware, OS hoặc vSphere cùng storage/network.

### Mẫu tài liệu thiết kế mạng

~~~yaml
# Ví dụ minh họa để trao đổi với đội mạng, KHÔNG phải manifest GDC hợp lệ.
site_id: factory-01
local_cidr: 10.40.0.0/16
management_subnet: 10.40.10.0/24
workload_subnet: 10.40.20.0/24
storage_subnet: 10.40.30.0/24
dns: dns.factory-01.example
ntp: ntp.factory-01.example
connectivity: controlled-vpn
~~~

Trước triển khai, cần bổ sung Pod/Service CIDR, VIP, load balancer, ingress, route tới OT/VPC và tránh trùng CIDR giữa site. Các cấu hình cluster phải sử dụng **đúng schema của dòng và phiên bản GDC**, không lấy mẫu ý tưởng này đưa thẳng vào trình cài đặt.

## 7. Năng lực xử lý, HA và dự phòng tại edge

Một edge zone có **giới hạn vật lý** về CPU, RAM, GPU, disk và IOPS. Đừng coi autoscaling Pod là khả năng tạo thêm máy chủ tức thời. Khi định cỡ, cần:

- Lưu lượng ngày thường, p95/p99 peak, mùa cao điểm, tăng trưởng 12–24 tháng.
- Phần tài nguyên dành cho hệ thống Kubernetes, control plane và monitoring.
- Khả năng mất một node nhưng vẫn phục vụ mức tải quan trọng.
- Băng thông và dung lượng local storage cho cả dữ liệu gốc lẫn backlog.
- Nguồn điện, switch, rack, LAN, HVAC là những **failure domain** riêng.
- Thời gian mua/thay máy, RTO/RPO và backup đã kiểm chứng.

Hai Pod chạy trên cùng một node không tạo HA thực sự. Replica, topology spread, anti-affinity, local storage, failover và khả năng xử lý khi site mất điện cần được thiết kế cùng nhau.

GDC connected có cấu hình zone theo phần cứng được chứng nhận và giới hạn cụ thể; không mặc định bổ sung bất cứ số node nào sau khi zone hoạt động. Dự phòng công suất phải tính từ giai đoạn thiết kế.

## 8. Bảo mật và chia sẻ trách nhiệm

### 8.1 Danh tính và truy cập

Trong connected/software only, có thể kết hợp các quyền Google Cloud liên quan tới management với **Kubernetes RBAC**, ServiceAccount, namespace và network policy. Trong air-gapped, cơ chế IAM/identity hoạt động bên trong perimeter và có thể tích hợp hệ thống danh tính tại chỗ được hỗ trợ.

Không cấp quyền cluster-admin rộng cho mọi người vận hành; phân tách trách nhiệm hạ tầng, bảo mật, ứng dụng và các tài khoản phục hồi khẩn cấp.

### 8.2 Phân vùng IT/OT

Camera, PLC, robot thuộc mạng OT cần được tách khỏi mạng quản trị cluster và ứng dụng IT. Chỉ mở cổng/hướng dữ liệu đã được thiết kế. Với connected, cần firewall cho kênh quản trị Google Cloud và VPN khi dùng; không cho mọi Pod truy cập Internet mặc định nếu không cần.

Với air-gapped, bản thân thiết bị lưu trữ rời, model file và image registry là đường đưa dữ liệu/ phần mềm vào. Thiết lập **kiểm tra nguồn, chữ ký, hash, malware, SBOM, bản quyền và audit trail** trước khi nạp.

### 8.3 Mã hóa và quản lý khóa

Dữ liệu tại chỗ có thể cần mã hóa storage, TLS giữa dịch vụ, secret management, certificate rotation và phân quyền đọc backup. GDC connected hỗ trợ thiết kế **CMEK trên local storage** cho cấu hình phù hợp, liên quan tới Cloud KMS. Điều này có thể tạo phụ thuộc vào chu kỳ làm mới khóa và mạng; phải kiểm tra mô hình đứt kết nối.

GDC air-gapped sử dụng cơ chế khóa phù hợp môi trường cô lập; không tự giả định có thể gọi public Cloud KMS từ hệ thống đã ngắt Internet.

### 8.4 Compliance

Các yếu tố cần audit gồm data location, metadata cluster, log, quyền support, truy cập từ xa, backup, xóa thiết bị, lưu khóa và chuỗi cung ứng. Kết luận đáp ứng pháp lý cần có bằng chứng từ cấu hình, hợp đồng và đánh giá chuyên môn; **việc đặt thiết bị trên đất nước sở tại chưa phải bằng chứng đầy đủ**.

## 9. Trách nhiệm vận hành

| Hoạt động | Connected | Air-gapped | Software only |
| --- | --- | --- | --- |
| Rack, điện, làm mát, LAN | Khách hàng | Khách hàng / site operator | Khách hàng |
| Hardware và sửa chữa | Khách hàng/SI với phần cứng certified | Theo hợp đồng giải pháp tích hợp | Khách hàng |
| Nền tảng phần mềm | Google quản lý từ xa theo sản phẩm | Vận hành trong perimeter theo mô hình dịch vụ/hợp đồng | Khách hàng quản trị cluster/phiên bản với công cụ Google |
| Data backup/restore | Khách hàng | Thiết kế theo yêu cầu site | Khách hàng |
| Cấu hình workload | Chủ ứng dụng/khách hàng | Chủ ứng dụng trong môi trường cô lập | Khách hàng |
| IAM ứng dụng và network policy | Khách hàng | Khách hàng | Khách hàng |
| Khả dụng mạng WAN | Khách hàng | Không cần WAN Google Cloud để chạy | Khách hàng cho phần tính năng quản lý cần mạng |

**Cảnh báo từ tài liệu connected:** Google hoặc SI không thể bảo đảm phục hồi dữ liệu local nếu hardware bị lỗi; **khách hàng chịu trách nhiệm backup dự phòng có thể khôi phục**. Các bản sao cần được kiểm tra định kỳ và xuất ra khỏi thiết bị trước khi trả/khử dữ liệu theo hợp đồng.

Với connected, đặt cảnh báo thời gian từ lần nối Google Cloud cuối; ngưỡng bảy ngày là giới hạn vận hành được tài liệu nêu, không phải lời hứa uptime của ứng dụng. Với software only, cần tự kiểm thử tác động của mất Internet tới fleet/management theo phiên bản, không suy từ giới hạn connected sang tất cả sản phẩm.

## 10. Đưa ứng dụng lên cluster: ví dụ Kubernetes

Khi cluster GDC đã được tạo và bạn có kubeconfig hợp lệ, nhóm ứng dụng dùng các thao tác Kubernetes chuẩn. Ví dụ đơn giản tạo API phát hiện lỗi dưới namespace riêng:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: factory-analytics
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anomaly-api
  namespace: factory-analytics
spec:
  replicas: 2
  selector:
    matchLabels:
      app: anomaly-api
  template:
    metadata:
      labels:
        app: anomaly-api
    spec:
      containers:
        - name: api
          image: registry.factory.example/anomaly-api:v1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: anomaly-api
  namespace: factory-analytics
spec:
  selector:
    app: anomaly-api
  ports:
    - port: 80
      targetPort: 8080
~~~

Đây là **ví dụ ứng dụng**, không phải manifest tạo GDC cluster. Image registry.factory.example phải được thay bằng registry tồn tại; endpoint /ready phải do ứng dụng cung cấp. Với air-gapped, image cần nhập tới registry nội bộ theo quy trình kiểm tra.

Kiểm tra trong môi trường thử nghiệm:

~~~bash
kubectl config current-context
kubectl get nodes
kubectl apply -f anomaly-api.yaml
kubectl -n factory-analytics get deployments,pods,services
kubectl -n factory-analytics rollout status deployment/anomaly-api
~~~

Luôn xác minh Kubernetes context để tránh ghi nhầm production. Service mặc định chỉ có phạm vi nội bộ cluster; truy cập từ camera/LAN cần ingress, load balancer và firewall đúng dòng sản phẩm. Hai replica chỉ là điểm khởi đầu, cần topology spread/anti-affinity và dự phòng node thực tế.

## 11. Local-first, đồng bộ dữ liệu và xử lý mất mạng

Thiết kế điển hình gồm:

1. Sensor/camera gửi dữ liệu tới ứng dụng local.
2. Ứng dụng ghi dữ liệu thô vào storage cục bộ theo retention.
3. Worker tạo kết quả, alarm và thông tin tổng hợp.
4. Hàng đợi bền vững giữ event chưa gửi.
5. Khi được phép kết nối, worker chuyển event tới cloud đích, xác nhận và cập nhật checkpoint.
6. Nếu lỗi, retry có giới hạn, dead-letter hoặc báo động; dùng event ID để chống ghi trùng.

Không được giả định cơ chế gửi qua WAN có tính **exactly once**. Thiết kế idempotent consumer, deduplication key, timestamp, site ID và các quy tắc khi event tới trễ.

### Tính dung lượng backlog

Giả sử lượng event/metadata sau lọc cần đồng bộ bằng **15 GB/ngày**, đứt WAN **4 ngày**, cộng **30% dự phòng**:

~~~text
Backlog = 15 GB/ngày × 4 ngày = 60 GB
Dự phòng = 60 GB × 30% = 18 GB
Dung lượng tối thiểu minh họa = 78 GB
~~~

Đây là tính toán mức logic, chưa tính replica, filesystem overhead, WAL, retention và lượng phát sinh trong lúc giải phóng backlog sau khi WAN phục hồi. Định cỡ production phải đo throughput ghi/đọc, IOPS và trường hợp xấu nhất.

### Ranh giới backup

Định nghĩa RPO/RTO, nơi lưu bản sao và kiểm thử restore theo lịch. Đối với hệ thống chỉ có một site, sao lưu thêm sang địa điểm độc lập nếu cần bảo vệ khỏi cháy nổ, mất điện diện rộng hoặc sự cố toàn rack. Air-gapped cần cơ chế backup không phá vỡ chính sách cô lập và kiểm soát media.

## 12. Quan sát và vận hành SRE

| Nhóm | Metric hoặc log | Giá trị |
| --- | --- | --- |
| App | p50/p95/p99 latency, error rate, inference quality | Chứng minh SLO hoạt động cục bộ |
| Kubernetes | Node conditions, pod restart, readiness, rollout | Phát hiện lỗi cluster/workload |
| Hardware | Nhiệt độ, CPU, RAM, SSD health, nguồn | Ngăn gián đoạn bởi tài nguyên vật lý |
| Network | RTT, jitter, loss, VPN status, reconnect age | Phát hiện WAN và hỗ trợ giới hạn disconnected |
| Data | Queue depth, retry, sync lag, dead-letter | Tránh mất và tồn đọng dữ liệu |
| Security | Log đăng nhập, thay RBAC, image provenance | Phục vụ audit và ứng cứu |
| DR | Backup freshness, restore test, spare capacity | Xác nhận phục hồi thực tế |

Với air-gapped, **local observability và alerting** là bắt buộc; không trông cậy dashboard chỉ truy cập được qua Internet. Với connected/software only, có thể tích hợp Google Cloud monitoring theo khả năng phiên bản, nhưng vẫn cần cảnh báo site-level khi WAN mất.

Đừng chỉ dùng số trung bình tất cả nhà máy; một site có p99 rất xấu có thể bị che bởi các site còn lại.

## 13. TCO và quyết định mua

Tổng chi phí sở hữu GDC (TCO) gồm nhiều lớp:

- Hardware: mua/rack/SSD/GPU, thay linh kiện, thiết bị dự phòng.
- Data center: điện, UPS, HVAC, rack, mặt bằng, bảo vệ vật lý.
- Network: LAN, VPN/Interconnect, WAN dự phòng, vận chuyển dữ liệu.
- Software/support: GDC, VMware/OS nếu có, gói hỗ trợ, SI và dịch vụ triển khai.
- Operations: đội on-call tại site, nâng cấp, SOC, audit, backup và diễn tập DR.
- Chi phí rủi ro: downtime, thiếu spare parts, kết nối WAN yếu, thời gian thay hardware.
- Phần cloud kết hợp: Cloud Storage, BigQuery, processing, lưu kết quả, network charges theo mô hình thực tế.

| Phương án | Điểm mạnh | Điểm phải đánh giá |
| --- | --- | --- |
| Public Google Cloud region | Elasticity, managed infrastructure | Latency WAN, data movement, yêu cầu lưu trú |
| GDC connected | Local compute, Google management, Kubernetes | Certified hardware, SI, support và reconnect |
| GDC air-gapped | Cô lập vận hành, sovereign data | Chi phí/độ phức tạp offline, catalog dịch vụ và site |
| GDC software only | Tận dụng bare metal/VMware, thống nhất workflow | Đội nội bộ quản lý OS/vSphere, cluster, storage |
| Kubernetes tự quản lý | Tự chủ chọn stack | Tự tích hợp và chịu toàn bộ trách nhiệm vận hành |

Giá/điều kiện cung ứng thay đổi theo quốc gia, quy mô, cấu hình và hợp đồng; air-gapped thường cần liên hệ Google để lấy báo giá. Đừng dùng đơn giá máy ảo public cloud làm toàn bộ TCO on-prem.

## 14. Kế hoạch POC có tiêu chí nghiệm thu

### Bước 1: Xác định yêu cầu

Ghi site, workload, lượng sensor, thời hạn dữ liệu, SLO p99, băng thông WAN, thời gian mất mạng tối đa, RTO/RPO, yêu cầu compliance, ngân sách và người chịu trách nhiệm.

### Bước 2: Chọn ứng viên GDC

Kiểm tra hardware, khả dụng quốc gia, release/version, SKU, storage, networking, licensing và gói hỗ trợ. Với air-gapped, xác nhận quy trình cập nhật/nhập image; với connected, xác nhận khả năng reconnect.

### Bước 3: Triển khai tập thử

Dựng cluster ở môi trường không có dữ liệu thật, triển khai một workload đại diện, tải dữ liệu mô phỏng, cấu hình metric, log, backup, IAM/RBAC và network policy.

### Bước 4: Thử lỗi

- Mất WAN có kiểm soát và phục hồi, đo gián đoạn dịch vụ cùng backlog.
- Mất một node, mất một mạng nội bộ hoặc giới hạn tài nguyên.
- Thử load peak và kiểm tra p99 latency.
- Restore dữ liệu từ backup sạch vào môi trường thử.
- Với air-gapped, thực hiện nhập phiên bản image/model theo quy trình offline.
- Với connected, kiểm tra quy trình theo dõi thời gian mất liên lạc và làm mới token/khóa.

### Bước 5: Go/no-go

Chỉ mở rộng nếu đáp ứng các tiêu chí đã định: hiệu năng, tính sẵn sàng, backup, bảo mật, phê duyệt data movement, chi phí, khả dụng phần cứng và người trực vận hành.

## 15. Case study: hệ thống camera ở 20 nhà máy

Một công ty có 20 nhà máy, mỗi nơi 40 camera. Video được dùng để phát hiện lỗi sản phẩm; hệ thống cần phản hồi **dưới 80 ms**. Video gốc lưu tại chỗ 14 ngày; chỉ sự kiện, tỷ lệ lỗi và thống kê được đưa lên Google Cloud để phân tích dài hạn.

Phương án khảo sát:

1. **Ở site:** ingest video, xử lý inference, ghi kết quả và lưu video theo retention.
2. **GDC connected** ở những site có WAN và hỗ trợ thiết bị certified phù hợp; **software only** ở nơi có cụm bare metal/VMware sẵn và đội quản trị đủ năng lực.
3. **Mạng:** tách camera/OT, workload và management; thiết kế local ingress cùng firewall cần thiết.
4. **Cloud:** đồng bộ metadata có kiểm soát tới Cloud Storage hoặc BigQuery tùy pipeline, không gửi video gốc nếu hợp đồng không cho phép.
5. **Khả dụng:** node redundancy, backup độc lập, queue offline và cảnh báo thời gian từ lần kết nối cuối.
6. **Quản trị:** đo p99 latency, số event bị trì hoãn, lỗi đồng bộ, disk fullness, tỷ lệ phục hồi.
7. **Địa điểm bị cấm kết nối Internet hoàn toàn:** chuyển nhánh thiết kế sang đánh giá **GDC air-gapped** với chuỗi cung ứng cập nhật riêng; không tận dụng thiết kế connected rồi ngắt WAN vĩnh viễn.

Các sai lầm cần tránh: coi cluster hai Pod cùng node là HA; không sao lưu data local; không kiểm thử mất WAN; cho rằng mọi dịch vụ Google Cloud public đều có trong GDC air-gapped; không tính phí điện, SI, support và hardware replacement.

## 16. Checklist trước production

- [ ] Lý do đặt workload tại chỗ đã được lượng hóa: latency, sovereignty, data volume hoặc độ bền hoạt động khi WAN yếu.
- [ ] Đã phân biệt đúng connected, air-gapped, software only bare metal và VMware.
- [ ] Có sơ đồ data plane, management plane, phân loại dữ liệu và đường trao đổi dữ liệu.
- [ ] Site readiness: rack, điện, UPS, HVAC, switch, DNS, NTP, địa chỉ IP và an ninh vật lý.
- [ ] Đã xác nhận hỗ trợ sản phẩm, phiên bản, phần cứng, quốc gia và hợp đồng.
- [ ] Capacity có dự phòng khi mất node và không phụ thuộc giả định mở rộng vô hạn.
- [ ] Có thiết kế IAM/RBAC, network segmentation, image provenance và secret management.
- [ ] Backup dữ liệu ứng dụng có thể khôi phục và đã diễn tập DR.
- [ ] Với connected: có cảnh báo, runbook reconnect và quy định giới hạn offline.
- [ ] Với air-gapped: có quy trình update, scan, ký nhận media và audit offline.
- [ ] Monitoring và alerting vẫn hoạt động khi Internet mất.
- [ ] Có TCO, trách nhiệm support và kế hoạch cho vòng đời thiết bị.

## 17. Ghi nhớ

GDC mở rộng hạ tầng và dịch vụ Google Cloud tới data center/edge nhưng **không phải một sản phẩm duy nhất với một tập tính năng chung**. **Connected** chạy workload gần nguồn dữ liệu trên phần cứng certified, quản lý qua Google Cloud và có yêu cầu kết nối định kỳ. **Air-gapped** dành cho môi trường tách biệt hoàn toàn. **Software only** đưa nền tảng GKE on-prem lên bare metal/VMware do doanh nghiệp quản trị.

Lựa chọn đúng dựa trên yêu cầu dữ liệu, mạng, độ trễ, vận hành, HA, security, support và TCO, không chỉ trên khả năng chạy Kubernetes.

## Tài liệu Google Cloud chính thức

1. [Google Distributed Cloud — danh mục giải pháp](https://docs.cloud.google.com/distributed-cloud/docs)
2. [GDC connected — overview](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/overview)
3. [GDC connected — how it works](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/how-it-works)
4. [GDC connected — requirements](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/requirements)
5. [GDC connected — deploy workloads](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/deploy)
6. [GDC connected — availability và backup](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/availability)
7. [GDC air-gapped — overview](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/overview)
8. [GDC air-gapped — infrastructure and network security](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/security-infrastructure-network)
9. [GDC air-gapped appliance — overview](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/appliance/overview)
10. [GDC software only for bare metal — overview](https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/bare-metal/docs/concepts/about-bare-metal)
11. [GDC software only for VMware — overview](https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/overview)
12. [GDC software only for VMware — installation overview](https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/how-to/install-overview)
