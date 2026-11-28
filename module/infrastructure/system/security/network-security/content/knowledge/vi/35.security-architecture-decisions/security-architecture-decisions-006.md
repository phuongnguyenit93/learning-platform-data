# Thiết kế multi-region và failover trong kiến trúc bảo mật mạng

**Chương:** Quyết định kiến trúc bảo mật mạng  
**Chủ đề:** Thiết kế multi-region và failover  
**Phạm vi:** Kiến trúc hệ thống phân tán qua nhiều vùng địa lý, bảo đảm liên tục dịch vụ và giữ nguyên các lớp phòng vệ mạng khi xảy ra sự cố.

## 1. Vì sao phải thiết kế multi-region?

Một hệ thống chỉ triển khai ở một vùng (region) có thể sử dụng nhiều availability zone (AZ), nhiều máy chủ và load balancer dự phòng mà vẫn chịu một **miền lỗi chung**: gián đoạn dịch vụ cấp vùng, hỏng đường kết nối diện rộng, mất phụ thuộc dùng chung hoặc sự cố cấu hình trên toàn vùng. Kiến trúc **multi-region** đặt năng lực cung cấp dịch vụ ở ít nhất hai region với khả năng chuyển lưu lượng và vận hành khi một region không còn đủ điều kiện phục vụ.

Tuy nhiên, tăng độ sẵn sàng không đồng nghĩa tăng an toàn nếu đường dự phòng đi vòng qua WAF, firewall, quản lý danh tính, ghi log hay kiểm soát khóa. **Thiết kế failover đúng phải duy trì các ranh giới bảo mật cốt lõi ngay cả ở chế độ suy giảm.**

Trong module `SECURITY_NETWORK_SECURITY`, bài này kết nối các lớp phòng vệ như phân đoạn, firewall, VPN, IDS/IPS, xác thực, DNS, giám sát lưu lượng, hạ tầng cloud và threat modeling với quyết định về khả năng khôi phục, vận hành và chi phí multi-region.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt region, AZ, failure domain, failover, failback, disaster recovery (DR), high availability (HA) và business continuity.
2. Chuyển yêu cầu kinh doanh thành RTO, RPO, SLO và kịch bản mất vùng có thể kiểm chứng.
3. So sánh active–passive, warm standby, pilot light, active–active và mô hình đa vùng tự chủ.
4. Thiết kế ingress, DNS/routing, mạng nội bộ, phân đoạn, egress, VPN, danh tính, khóa, giám sát và dữ liệu khi một region hỏng.
5. Nhận diện rủi ro split-brain, stale DNS, capacity thiếu, drift chính sách bảo mật và phụ thuộc điều khiển tập trung.
6. Lập decision record, runbook failover/failback và kiểm thử có điều kiện dừng, có chứng cứ.

## 2. Khái niệm và ranh giới lỗi

| Thuật ngữ | Ý nghĩa thực tế | Câu hỏi cần đặt ra |
|---|---|---|
| **Availability zone (AZ)** | Miền lỗi độc lập tương đối về điện, mạng và cơ sở hạ tầng trong một region | Sự cố một AZ có làm sập toàn bộ dịch vụ không? |
| **Region** | Vùng địa lý/logical deployment gồm một hoặc nhiều AZ | Những thành phần nào vẫn dùng chung giữa các region? |
| **HA** | Giữ dịch vụ hoạt động khi một thành phần thông thường lỗi | Có loại bỏ được điểm lỗi đơn ở mỗi region không? |
| **DR** | Khôi phục sau sự cố vượt quá khả năng chịu lỗi thông thường | Bao lâu chuyển được sang vùng dự phòng? Có mất dữ liệu không? |
| **Failover** | Chuyển xử lý/lưu lượng từ hệ thống không đủ điều kiện sang hệ thống thay thế | Ai hoặc cơ chế nào quyết định chuyển? |
| **Failback** | Đưa hệ thống trở lại trạng thái phục vụ mong muốn sau khi khôi phục | Dữ liệu và phiên có được đồng bộ/đối soát trước khi quay về? |
| **Fault domain / failure domain** | Tập tài nguyên có thể cùng bị ảnh hưởng bởi một sự cố | Có phụ thuộc ẩn nào khiến hai region cùng lỗi không? |
| **Control plane** | Nơi thiết lập cấu hình, cấp quyền và thay đổi trạng thái hạ tầng | Nếu control plane lỗi, data plane đang chạy có tiếp tục phục vụ không? |
| **Data plane** | Nơi luồng yêu cầu và dữ liệu thực tế được xử lý | Luồng người dùng có phụ thuộc quá chặt vào một API điều khiển không? |
| **Blast radius** | Quy mô hệ thống, danh tính hoặc dữ liệu bị tác động từ một lỗi/sự cố | Một thay đổi sai hoặc danh tính bị lộ có ảnh hưởng cả hai vùng không? |

**Multi-AZ** chủ yếu chống lỗi ở cấp zone. **Multi-region** tăng khả năng chịu lỗi cấp vùng nhưng cũng mở thêm đường mạng, điểm điều khiển, quyền truy cập và luồng dữ liệu liên vùng. Hai region có chung một nhà cung cấp, cùng hệ thống triển khai, cùng kho bí mật hoặc cùng root account vẫn có những rủi ro tương quan.

### Không đánh đồng tính sẵn sàng với tính nhất quán

Một region phụ có thể vẫn nhận HTTP request nhưng không xử lý đúng nếu database replica chưa đồng bộ, kho khóa không giải mã được dữ liệu hoặc hệ thống thanh toán bên ngoài mất kết nối. Health check chỉ kiểm tra `HTTP 200` tại trang chủ thường không đủ để xác định vùng đó **sẵn sàng phục vụ nghiệp vụ**.

## 3. Xác định yêu cầu trước khi chọn kiến trúc

### 3.1. RTO, RPO và SLO

**Recovery Time Objective (RTO)** là thời gian tối đa mong muốn để khôi phục chức năng sau gián đoạn. **Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa chấp nhận theo thời gian. Đây là **mục tiêu thiết kế**, không phải con số bảo đảm nếu chưa diễn tập và đo.

Ví dụ đối với ứng dụng giao dịch nội bộ:

| Chức năng | RTO giả định | RPO giả định | Hướng thiết kế |
|---|---:|---:|---|
| Trang thông tin công khai | 15 phút | 1 giờ với nội dung tĩnh | CDN đa vùng, origin dự phòng |
| Đăng nhập và API người dùng | 5 phút | Phiên có thể đăng nhập lại | Identity có khả năng phục hồi, ứng dụng stateless |
| Lệnh thanh toán/đơn hàng | 10 phút | Gần 0 hoặc mức được nghiệp vụ duyệt | Cơ chế ghi có kiểm soát, đối soát, chống ghi trùng |
| Báo cáo phân tích | 4 giờ | 30 phút | Replica/batch và phục hồi bất đồng bộ |

RPO = 0 cho dữ liệu nghiệp vụ quan trọng có thể đòi hỏi cơ chế ghi đồng bộ/quorum hoặc giao thức nghiệp vụ đặc thù; không thể suy ra từ việc “đã bật replication”. Đồng bộ liên vùng cũng làm tăng độ trễ và có thể giảm khả năng ghi khi đường liên vùng mất.

Đối với SLO, phải thống nhất **người dùng đo được gì**: tỷ lệ request thành công, độ trễ p95/p99, khả năng hoàn thành giao dịch và tính đúng của dữ liệu. Thời gian DNS cập nhật chưa chắc là thời gian khôi phục được nghiệp vụ.

Ví dụ: mục tiêu RTO = 10 phút nhưng quy trình phải chờ 12 phút để một nhóm trực on-call nhận cuộc gọi thì mục tiêu này không khả thi ngay từ thiết kế tổ chức.

### 3.2. Danh sách kịch bản lỗi có thể kiểm thử

Ít nhất cần phân biệt:

- **Lỗi một AZ:** kiểm tra autoscaling/load balancing trong region hiện tại.
- **Lỗi data plane một region:** request hoặc giao dịch thất bại dù control plane vẫn truy cập được.
- **Lỗi control plane:** không tạo hoặc cập nhật được tài nguyên nhưng các đường dữ liệu hiện hữu có thể vẫn chạy.
- **Đứt tuyến liên vùng:** hai phía còn sống nhưng không liên lạc/đồng bộ; nguy cơ split-brain.
- **Lỗi DNS/traffic management:** backend khỏe nhưng không định tuyến được người dùng.
- **Sự cố danh tính, KMS, chứng chỉ hoặc secret store:** máy ứng dụng khỏe nhưng không thể xác thực/giải mã/khởi động.
- **Lỗi triển khai đồng thời:** một bản cấu hình sai được đẩy sang cả hai region.
- **Sự cố bảo mật tại region chính:** cần cô lập và chuyển vùng mà không đồng bộ hóa dữ liệu/cấu hình đã bị xâm phạm.

Mỗi kịch bản phải có tiêu chí **không đưa vào phục vụ**: region dự phòng thiếu log bắt buộc, không có WAF, chứng chỉ không hợp lệ, replica chưa nhất quán, thiếu năng lực xử lý hoặc chưa khẳng định được quyền truy cập.

## 4. Các mẫu kiến trúc multi-region

| Mẫu | Cách hoạt động | Ưu điểm | Điểm cần kiểm soát |
|---|---|---|---|
| **Backup & restore** | Region phụ được dựng lại từ backup và cấu hình hạ tầng | Chi phí thường thấp, phù hợp RTO dài | Thời gian dựng, kiểm chứng backup, khóa giải mã, nguồn artifact |
| **Pilot light** | Chỉ duy trì dữ liệu và các thành phần tối thiểu ở vùng phụ | Giảm chi phí so với chạy hai stack đầy đủ | Thời gian scale-out và khởi tạo lớp mạng/bảo mật |
| **Warm standby** | Region phụ chạy sẵn nhưng năng lực thấp hơn | Chuyển nhanh hơn pilot light | Phải tăng công suất trước/đúng lúc sự cố; tắc nghẽn khi tải tăng |
| **Active–passive/hot standby** | Vùng phụ gần như đầy đủ nhưng bình thường không nhận hoặc nhận ít tải | Quy trình sở hữu ghi đơn giản hơn | Tài nguyên nhàn rỗi; cấu hình có thể drift; cần diễn tập |
| **Active–active** | Hai hoặc nhiều region cùng phục vụ lưu lượng thật | Khai thác tài nguyên và giảm độ trễ theo địa lý | Phân phối dữ liệu, nhất quán, routing, lỗi tương quan và dư tải khi một vùng hỏng |

Tên gọi có thể khác giữa tổ chức; hãy mô tả **hành vi thực tế**, mức tải bình thường và cách chuyển khi lỗi thay vì chỉ ghi “active–active”.

### Hướng lựa chọn

- RTO vài giờ, chấp nhận RPO theo chu kỳ backup: có thể bắt đầu bằng **backup & restore**.
- RTO vài chục phút, hạ tầng có thể tái dựng bằng IaC: cân nhắc **pilot light** hoặc **warm standby**.
- RTO vài phút, cần đường thay thế có sẵn: cân nhắc **hot standby** hoặc **active–active** kèm điều kiện kiểm thử nghiêm ngặt.
- Yêu cầu giao dịch đồng thời đa vùng với RPO rất thấp: phải giải quyết mô hình ghi, xung đột và tính nhất quán ngay từ tầng dữ liệu; chỉ thêm load balancer không giải quyết được.

Thiết kế luôn phải đi kèm phân tích chi phí, kỹ năng vận hành và kịch bản lỗi tương quan, không chỉ so sánh thông số “uptime”.

## 5. Kiến trúc tham chiếu: hai region, các lớp phòng vệ tương đương

Giả sử hệ thống có **Region A** và **Region B**, mỗi vùng có nhiều AZ, ingress, web/API, dữ liệu, egress, firewall và telemetry riêng. DNS/traffic steering định tuyến đến region đủ điều kiện phục vụ. Hệ thống danh tính, bí mật và quản lý khóa được thiết kế để không tạo điểm lỗi đơn trên đường khôi phục.

~~~mermaid
flowchart TD
    U["Người dùng / đối tác"]
    D["Authoritative DNS / Global traffic manager<br/>health-based routing"]
    U --> D
    subgraph A["Region A"]
      IA["DDoS/WAF + public LB A"]
      AA["App A<br/>>= 2 AZ"]
      DA[("Database A")]
      EA["Egress controls A"]
      LA["Logs / metrics A"]
      IA --> AA
      AA --> DA
      AA --> EA
      IA -. telemetry .-> LA
      AA -. telemetry .-> LA
    end
    subgraph B["Region B"]
      IB["DDoS/WAF + public LB B"]
      AB["App B<br/>>= 2 AZ"]
      DB[("Database B")]
      EB["Egress controls B"]
      LB["Logs / metrics B"]
      IB --> AB
      AB --> DB
      AB --> EB
      IB -. telemetry .-> LB
      AB -. telemetry .-> LB
    end
    D --> IA
    D --> IB
    DA <-->|"Replication / controlled promotion"| DB
    LA --> SIEM["Tập trung và lưu trữ sự kiện<br/>trong failure domain độc lập"]
    LB --> SIEM
~~~

**Các đặc điểm quan trọng:**

1. Region B có đủ **WAF, chứng chỉ, policy, nhóm mạng, IAM/service identity, KMS/key access, logging** và nguồn cấu hình cần thiết trước khi được phép nhận tải.
2. Region A và B có ranh giới mạng rõ; không mở “allow all” liên vùng để đơn giản hóa replication.
3. Đường dữ liệu cần vận hành mà không phụ thuộc vào thao tác tạo tài nguyên hoặc cấp quyền khẩn cấp trong một control plane đang lỗi.
4. DNS/traffic manager phải được xem là một phụ thuộc riêng với độ sẵn sàng, bảo vệ và kế hoạch vận hành.
5. Mô hình sao chép dữ liệu phụ thuộc yêu cầu nghiệp vụ; sơ đồ hai chiều **không mặc định có nghĩa cả hai bên cùng được ghi**.

### Lưu ý về phụ thuộc chung

Sơ đồ có hai region chưa đủ nếu cả hai phụ thuộc vào một NAT gateway, một VPN concentrator, một IdP endpoint, một key vault, một kho container image, một máy chủ DNS nội bộ hoặc một pipeline triển khai ở Region A. Cần vẽ **dependency graph** đến tầng vận hành, không chỉ luồng HTTP công khai.

## 6. Thiết kế lưu lượng vào: DNS, CDN, Anycast và load balancer

### 6.1. Lựa chọn cơ chế chuyển hướng

| Cơ chế | Ưu điểm | Giới hạn và điều kiện |
|---|---|---|
| **DNS health-based / weighted routing** | Dễ tích hợp, không cần một IP toàn cục | TTL không bảo đảm mọi resolver/client đổi ngay; cache, kết nối cũ và negative caching |
| **Global L7 load balancing** | Có thể đo health ở lớp ứng dụng và chuyển vùng nhanh | Là một phụ thuộc toàn cục; phải xem năng lực chống DDoS, WAF, chứng chỉ và nơi xử lý TLS |
| **Anycast / BGP steering** | Cho phép một IP công bố ở nhiều điểm mạng | Tốc độ hội tụ và trạng thái phiên phụ thuộc thiết kế mạng; cần quyền vận hành định tuyến, chống route leak/hijack |
| **CDN + nhiều origin** | Bảo vệ ingress, cache giảm tải và chuyển origin | Không che được lỗi của chức năng động khi origin/data thiếu; cache policy phải đúng |
| **Client-side failover** | Ứng dụng client biết nhiều endpoint | Cần xử lý retry, idempotency, bảo mật chứng chỉ và tránh retry storm |

Không nên dùng đồng thời nhiều cơ chế chuyển hướng với quyền quyết định độc lập mà thiếu thứ tự ưu tiên; nếu chúng đánh giá health khác nhau, client có thể bị đẩy qua lại giữa các region.

### 6.2. TTL và thời gian chuyển

Giả sử TTL bản ghi DNS là 60 giây và hệ thống health check nhận ra lỗi sau 30 giây. Không thể kết luận RTO = 90 giây: một số resolver kéo dài cache; client có thể giữ kết nối, có DNS cache riêng hoặc retry đến IP cũ. Thời gian chuyển quan sát được là tổng hợp của phát hiện lỗi, quyết định, phân phối tuyến, tái kết nối, warm-up và khả năng xử lý nghiệp vụ.

Sử dụng DNSSEC nếu kiến trúc/threat model yêu cầu bảo vệ tính toàn vẹn trả lời DNS; bảo đảm cấu hình ký và quản lý khóa tồn tại trên toàn bộ đường chuyển. Cần kiểm tra việc đổi đích có giữ đúng hostname, chứng chỉ TLS và chính sách mTLS hay không.

### 6.3. Health check phải đại diện cho nghiệp vụ

Một thiết kế hữu ích dùng nhiều tầng:

| Tầng health | Ví dụ | Mục đích |
|---|---|---|
| L3/L4 | Kết nối đến endpoint trên port yêu cầu | Loại bỏ hỏng đường hoặc listener |
| L7 | API probe có deadline, trả status đúng | Phát hiện web/API không phản hồi |
| Readiness | Ứng dụng kết nối được DB/cache/secret store cần thiết | Ngăn chuyển vào vùng ứng dụng không sẵn sàng |
| Business canary | Giao dịch giả lập được phép, không tạo dữ liệu thật | Kiểm tra toàn tuyến phục vụ nghiệp vụ |
| Security readiness | WAF, xác thực, chứng chỉ, rate limit, logging bắt buộc | Ngăn chuyển vùng vào đường kém bảo vệ |

Đừng để một kiểm tra quá nặng tạo thêm tải và làm cả hai region suy giảm. Probe nên có ngưỡng, timeout, retry có kiểm soát, nhiều vị trí quan sát và chống dao động (hysteresis). **Một region mất monitoring** không đương nhiên tương đương **region đã chết**.

## 7. Mạng và phân đoạn liên vùng

### 7.1. Kế hoạch địa chỉ và routing

Ví dụ phân bổ CIDR không trùng lặp:

| Vùng | Dải ví dụ | Các phân đoạn trong vùng |
|---|---|---|
| Region A | `10.84.0.0/16` | Ingress `10.84.10.0/24`, App `10.84.20.0/24`, Data `10.84.30.0/24`, Management `10.84.40.0/24` |
| Region B | `10.85.0.0/16` | Ingress `10.85.10.0/24`, App `10.85.20.0/24`, Data `10.85.30.0/24`, Management `10.85.40.0/24` |

Dải này minh họa cách tránh CIDR chồng lấn; triển khai thật phải kiểm tra va chạm với mạng on-premises, VPN, peering và nhà cung cấp. Cần thiết kế route table theo miền tin cậy, tránh default route hoặc quảng bá prefix rộng khiến luồng từ App vùng A đi vào Data vùng B không được kiểm soát.

Inter-region networking có thể dùng peering, transit hub, mạng backbone của cloud, IPsec VPN hoặc kết nối riêng. Các lựa chọn khác nhau về tính sẵn sàng, mã hóa in transit, throughput, chi phí truyền dữ liệu và điểm kiểm soát. Khi dùng VPN, nên đánh giá gateway, đường ISP, khóa/chứng chỉ, cấu hình IKE/IPsec và cơ chế tái lập tunnel ở cả hai đầu. Một cặp đường hầm đi qua cùng một thiết bị biên vẫn có điểm lỗi chung.

### 7.2. Ma trận kiểm soát east–west

| Source | Destination | Giao thức/dịch vụ | Nguyên tắc |
|---|---|---|---|
| Internet | Public ingress A/B | HTTPS 443 | Chỉ qua lớp DDoS/WAF, không vào thẳng app/data |
| Public ingress trong region | App cùng region | Cổng dịch vụ đã công bố | Allow theo workload identity/nhóm, giới hạn nguồn |
| App trong region | Database cùng region | Cổng DB được phê duyệt | Chỉ định danh dịch vụ cần thiết; tối thiểu quyền |
| DB A | DB B | Kênh replication cụ thể | mTLS/IPsec theo khả năng, chỉ các endpoint replication |
| Management A/B | Workload được quản trị | Giao thức quản trị theo role | JIT/PAM, MFA ở điểm vào, audit hoạt động |
| App A | Data B | Mặc định deny | Chỉ mở khi kiến trúc nghiệp vụ yêu cầu cụ thể |
| Internet | Management/Data | Deny | Không công bố trực tiếp endpoint nhạy cảm |

Các quy tắc phải được áp dụng **theo cả hai chiều của phiên phù hợp**, đặc biệt với firewall stateful, NAT và route bất đối xứng. Network ACL/stateless firewall cần cho phép luồng phản hồi theo thiết kế; mở port ephemeral tùy tiện có thể làm tăng bề mặt tấn công.

### 7.3. Điểm khó với firewall stateful và NAT

Khi chuyển region, bảng trạng thái kết nối (conntrack), phiên NAT và TCP/TLS thường **không được chuyển theo**; client cần tái kết nối. Nếu có stateful inspection ở đường liên vùng, cần kiểm tra đường đi và về đi qua cùng thiết bị/cặp thiết bị. Route bất đối xứng có thể khiến firewall đánh rớt gói hợp lệ sau failover.

Egress cũng cần được dự phòng. Nếu vùng phụ có IP egress khác, đối tác sử dụng allowlist địa chỉ IP có thể chặn yêu cầu. Tránh giải pháp mở toàn bộ egress lúc khẩn cấp; hãy đăng ký dải egress dự phòng, giới hạn đích và kiểm thử kết nối từ trước.

## 8. Giữ nguyên bảo mật trong chế độ failover

### 8.1. Identity, quyền và xác thực

- Bảo đảm người dùng và service identity được xác thực ở vùng dự phòng theo kiến trúc đã duyệt; phân biệt **IdP control plane** với token validation cục bộ ở data plane.
- Nếu một IdP trung tâm không sẵn sàng, xác định chính xác tác vụ nào vẫn được phép nhờ token đã cấp, thời hạn token và thời điểm cần refresh. Không mặc định gia hạn vô hạn hoặc bỏ xác thực.
- Cấu hình RBAC/IAM, policy network, service account, role trust và scope dữ liệu tương đương về **mức bảo vệ**; có thể khác định danh tài nguyên giữa vùng nhưng cùng ý định chính sách.
- Quản trị viên dùng MFA, PAM/JIT và tài khoản khẩn cấp có kiểm soát, có audit, kiểm tra định kỳ. Tránh yêu cầu phát sinh quyền admin diện rộng trong lúc failover.
- Nếu sử dụng hệ thống directory tự quản trị, kiểm tra DNS, replication, sites/subnets, thời gian và điều kiện đăng nhập khi mất một region.

**Mấu chốt:** phiên mới trên region B phải có khả năng xác thực hợp lệ trong điều kiện lỗi đã giả định, nhưng vẫn tuân thủ chính sách truy cập bắt buộc.

### 8.2. Mã hóa, khóa, chứng chỉ và secrets

Với dữ liệu mã hóa bằng KMS/HSM theo region, chỉ sao chép ciphertext là chưa đủ: region B còn cần cơ chế sử dụng khóa hợp lệ. Lựa chọn key replication, multi-region keys hoặc thiết kế decrypt/re-encrypt phải dựa vào mô hình quản lý khóa thực tế và quy định dữ liệu; các nhà cung cấp có ngữ nghĩa khác nhau.

Nên kiểm thử:

1. Region B khởi chạy ứng dụng và đọc secrets khi Region A không thể truy cập.
2. Region B giải mã được dữ liệu sao chép đúng quyền; không yêu cầu root/admin thao tác khẩn cấp.
3. Chứng chỉ TLS/mTLS, chuỗi tin cậy, revocation policy và vòng đời gia hạn hoạt động độc lập với region lỗi.
4. Backup chứa dữ liệu mã hóa có thể phục hồi bằng khóa hợp lệ; khóa backup phải có chính sách phục hồi và kiểm soát truy cập.
5. Khóa/secrets bị nghi xâm phạm phải có luồng **rotate/revoke/contain** riêng; failover không được nhân bản bí mật đã bị chiếm mà không đánh giá.

### 8.3. WAF, DDoS, IDS/IPS và quan sát

- WAF/rate limit/bot defense cần có chính sách tương đương ở cả hai ingress, bao gồm ngoại lệ, rule cập nhật và phương án rollback.
- DDoS protection phải bao phủ endpoint thực tế sau khi DNS/Anycast chuyển; tải chuyển vùng có thể bị hiểu nhầm là spike tấn công.
- IDS/IPS, NDR và EDR phải giám sát được mạng east–west lẫn luồng management của region B. Nếu cần kiểm tra mã hóa, xác định điểm TLS termination và vấn đề riêng tư.
- Log xác thực, truy cập mạng, WAF, firewall, DNS và audit control plane phải tồn tại khi vùng chính mất. Cân nhắc lưu trữ/tổng hợp log trong failure domain độc lập với nguồn sinh sự kiện, có retention và quyền read riêng.
- Quy tắc SIEM nên nhận biết `region_id`, `failover_event_id`, thay đổi lưu lượng, destination và status của dịch vụ để không mất ngữ cảnh.

Không nên tắt WAF, MFA, mTLS hoặc logging chỉ để tăng tỷ lệ thành công trong một sự cố. Nếu có chế độ **degraded operation** được duyệt, phải mô tả rõ chức năng nào tạm ngưng và dữ liệu nào vẫn được bảo vệ.

## 9. Dữ liệu: replication, split-brain và giao dịch

### 9.1. Các cách sao chép dữ liệu

| Mô hình | Đặc điểm | Rủi ro chính |
|---|---|---|
| **Asynchronous replication** | Vùng phụ nhận thay đổi sau vùng chính | Có replication lag, RPO có thể lớn hơn 0 |
| **Synchronous replication** | Ghi chỉ hoàn thành theo điều kiện ack/quorum | Độ trễ liên vùng, giảm khả năng ghi khi đứt kết nối |
| **Single-writer + replica promotion** | Chỉ một writer hợp lệ tại một thời điểm | Cần fencing writer cũ trước khi promote vùng phụ |
| **Multi-writer** | Nhiều vùng nhận ghi đồng thời | Xung đột, thứ tự cập nhật, partition, logic hòa giải |
| **Backup/snapshot** | Khôi phục trạng thái ở một thời điểm | Khả năng mất dữ liệu và tốc độ restore; kiểm tra backup độc lập |

Chọn mô hình theo **bất biến nghiệp vụ**: một đơn hàng chỉ được ghi nhận thanh toán một lần, tồn kho không âm, số dư phải đối soát, sự kiện phải xử lý idempotent. Không được để traffic manager tự quyết định hai vùng đều được ghi nếu database không hỗ trợ nhất quán tương ứng.

### 9.2. Split-brain và fencing

Tình huống: liên kết giữa A và B mất, nhưng cả hai còn sống. Nếu mỗi bên tự coi bên kia đã chết và cùng nhận write, dữ liệu có thể phân nhánh. Health check từ một vị trí duy nhất không đủ để phân biệt **region down** với **network partition**.

Phòng ngừa gồm các cơ chế tùy nền tảng:

- Có một **nguồn thẩm quyền xác định writer** (quorum/consensus/lease với điều kiện phù hợp), không dùng hai bộ điều khiển failover độc lập.
- **Fencing** writer cũ trước khi promote writer mới; đối với nền tảng thiếu fencing tin cậy, ưu tiên ngừng ghi hơn là nhận ghi sai.
- Dùng transaction ID, idempotency key, outbox/inbox hoặc cơ chế chống xử lý trùng khi retry.
- Giữ cơ chế đối soát và xác nhận replication lag/commit index/LSN theo loại database trước khi tiếp tục.
- Nếu failover do xâm nhập, xác định **mốc dữ liệu sạch**; replica đồng bộ có thể đã nhận dữ liệu bị sửa độc hại.

### 9.3. Phân biệt failover ứng dụng và failover dữ liệu

Có thể chuyển web/API sang B rất nhanh trong khi database vẫn là A. Kiến trúc như vậy vẫn phụ thuộc A ở lớp dữ liệu; nếu mất toàn Region A thì ứng dụng B không hoạt động đúng. Cần ghi rõ đường dữ liệu bình thường và đường dữ liệu khi A thật sự biến mất.

## 10. Tính toán năng lực dự phòng và giới hạn tải

Giả sử tải giờ cao điểm của hệ thống là **9.000 request/giây**, hai region phục vụ 50/50. Bình thường mỗi region nhận 4.500 request/giây.

Nếu mỗi region chỉ có khả năng xử lý tối đa 6.500 request/giây, sau khi A mất thì B phải nhận 9.000 request/giây và sẽ quá tải **2.500 request/giây**. Gọi đây là “active–active, nên có HA” là đánh giá thiếu cơ sở.

Mô hình đơn giản:

\[
C_{\text{mỗi vùng}} \geq \frac{L_{\text{đỉnh còn phục vụ}}}{N-k} \times (1+m)
\]

Trong đó `N` là số region hoạt động bình thường, `k` là số region phải chịu lỗi đồng thời, `L` là tổng tải cần phục vụ, `m` là hệ số dự phòng (headroom). Với hai region và yêu cầu chịu lỗi một region, `N-k=1`. Nếu chọn headroom 25%:

\[
C_{\text{mỗi vùng}} \geq 9{,}000 \times 1{,}25 = 11{,}250\ \text{request/giây}.
\]

Đây chỉ là **ước lượng capacity ở tầng request**, chưa tính giới hạn DB connections, queue, cache miss, upstream API, WAF/DDoS rate limit, NAT ports, băng thông egress hay chi phí cross-region. Với warm standby, cần đo **thời gian scale thành công khi vùng còn lại cũng đang có tải cao** và giới hạn quota của nhà cung cấp.

Nên áp dụng load shedding, backpressure, queue có giới hạn, exponential backoff có jitter và retry budget. Một cơn bão retry từ client có thể khiến vùng dự phòng sập dù có đủ capacity theo lưu lượng bình thường.

## 11. Tự động hóa failover: điều kiện kích hoạt và chặn chuyển sai

### 11.1. Mẫu state machine

~~~mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Suspect: Dấu hiệu lỗi
    Suspect --> Normal: Phục hồi trong cửa sổ xác nhận
    Suspect --> Assess: Lỗi bền vững và đủ chứng cứ
    Assess --> Blocked: Không đạt security/data/capacity readiness
    Blocked --> Assess: Đã khắc phục, xác nhận lại
    Assess --> Failover: Đủ điều kiện và có quyền chuyển
    Failover --> ServingB: Chuyển tuyến + xác nhận nghiệp vụ
    Failover --> Blocked: Kiểm tra sau chuyển thất bại
    ServingB --> Recovery: A phục hồi / đối soát dữ liệu
    Recovery --> ServingB: Chưa đạt điều kiện failback
    Recovery --> Normal: Failback được phê duyệt và xác minh
~~~

Một lỗi “probe thất bại một lần” không đủ để quyết định failover. Quy trình chuyển nên yêu cầu:

1. Tín hiệu lỗi từ nhiều vantage point, vượt ngưỡng về thời gian/số lần, có đánh giá tính xác thực.
2. Vùng đích vượt qua kiểm tra application + data + security readiness.
3. Database có chủ sở hữu write rõ ràng; nếu cần promote, thực hiện fencing và kiểm tra trạng thái theo cơ chế được hỗ trợ.
4. Vùng đích còn đủ capacity, quota, đường mạng/egress và logging.
5. Quyết định chuyển có audit, người/quy trình chịu trách nhiệm, giới hạn quyền và rollback plan.
6. Sau chuyển, xác thực giao dịch thử nghiệm và error budget, không chỉ ping/health HTTP.

### 11.2. Pseudocode quyết định

~~~text
if persistent_region_failure(A) and confidence_from_multiple_probes():
    freeze_concurrent_failover_decisions()
    assert approved_change_window_or_incident_authority()
    assert region_B.application_ready()
    assert region_B.security_controls_ready()
    assert region_B.capacity_ready_for_peak()
    assert region_B.data_promotion_safe()
    if write_owner_must_change:
        fence_old_writer_A()
        promote_writer_B_with_quorum_or_approved_procedure()
    steer_new_traffic_to_B()
    validate_end_to_end_business_canaries()
    if validation_failed:
        stop_new_promotions_and_follow_runbook()
    else:
        record_failover_event_and_notify_operators()
else:
    keep_current_state_and_investigate()
~~~

Đây là **logic minh họa**, không phải script có thể chạy nguyên xi. Những phép kiểm `data_promotion_safe` và `fence_old_writer_A` phải dựa vào khả năng thật của database/cluster. Đặc biệt, rollback traffic không có nghĩa tự động đảo ngược được dữ liệu đã ghi vào B.

### 11.3. Tránh flapping và tự động hóa nguy hiểm

Cần hysteresis, cooldown, minimum dwell time và quyền xác nhận đối với failback. Failback thường phức tạp hơn failover vì phải hòa giải dữ liệu, làm nóng cache, tái đồng bộ secrets/certificates, kiểm tra tuyến về và trạng thái security policy. Trong sự cố đang bị tấn công, tự động chuyển hướng theo traffic anomaly có thể chuyển kẻ tấn công sang vùng dự phòng; hãy kết hợp tín hiệu an ninh với health signal.

## 12. Threat modeling cho multi-region

| Tình huống | Tác động | Kiểm soát thiết kế | Phép kiểm chứng |
|---|---|---|---|
| Region A bị mất hoàn toàn | Gián đoạn ingress/data plane | Region B độc lập, health routing, dữ liệu và secret sẵn sàng | Cô lập A trong lab/staging; đo RTO/RPO |
| A–B đứt mạng nhưng cả hai còn chạy | Split-brain, mất/ghi trùng dữ liệu | Quorum, fencing, one-writer policy, retry idempotent | Network partition có kiểm soát |
| Một tài khoản CI/CD bị chiếm | Triển khai cấu hình độc hại sang cả hai vùng | Phân quyền, yêu cầu phê duyệt, ký artifact, rollout theo đợt | Thử revoke quyền pipeline trong staging |
| WAF của B thiếu rule | Failover thành đường bypass | Policy-as-code, drift detection, security readiness gate | So policy giữa các vùng trước khi chuyển |
| KMS/secrets chỉ sẵn có tại A | B có dữ liệu nhưng không giải mã được | Kế hoạch khóa đa vùng, grant tối thiểu, kiểm thử decrypt | Mất kết nối tới A và chạy canary ở B |
| DNS bị sửa trái phép | Chuyển người dùng đến endpoint giả | IAM tối thiểu cho DNS, MFA/approval, audit, DNSSEC khi phù hợp | Diễn tập phát hiện đổi bản ghi không được duyệt |
| DDoS chuyển từ A sang B | B quá tải | DDoS controls cả hai vùng, capacity, rate limiting | Load test/attack simulation hợp pháp trong môi trường tách biệt |
| Backup bị mã hóa/xóa bởi attacker | Không thể phục hồi sạch | Immutable/isolated backup, quyền xóa tách biệt, restore drill | Khôi phục từ điểm sạch kiểm chứng được |
| Tất cả traffic/log đều đi qua một trung tâm | Trung tâm lỗi gây mất phục vụ/khả năng điều tra | Local buffering, log sink độc lập, đường truyền dự phòng | Cắt đường kết nối tới log collector, kiểm tra lưu đệm |

**Đặc điểm cần nhớ:** một lỗi hệ thống vật lý và một sự cố bị xâm nhập không nhất thiết có cùng runbook. Khi nghi mã độc đã chiếm quyền tài khoản/CI/CD hoặc dữ liệu đã bị sửa, ưu tiên **containment và phục hồi từ trạng thái sạch**; promote một replica chứa cùng thay đổi độc hại có thể làm sự cố lan rộng.

## 13. Configuration parity, IaC và triển khai an toàn

### 13.1. Những thành phần phải kiểm soát drift

- Security groups, network firewall, route tables, endpoint policies, ingress WAF và rate limit.
- IAM roles, trust policy, workload identity, PAM/JIT, quyền truy cập service-to-service.
- TLS/mTLS, CA trust, renewal, bí mật, KMS grants, backup encryption policy.
- DNS/health-check policy, traffic weights, LB listeners, canary và rollback.
- Logging sinks, SIEM agents, alert thresholds, retention, time sync và cấu hình EDR/NDR.
- Quotas, auto-scaling, reserved capacity, NAT/egress, private endpoints, kết nối bên ngoài.

Các region cần cùng **bất biến bảo mật** nhưng không phải mọi ID/IP đều giống nhau. Hãy mô tả chính sách thành template/biến được review, kiểm thử liên vùng và so sánh kết quả triển khai (drift), tránh sao chép thủ công các tài nguyên mạng.

### 13.2. Mẫu khai báo chính sách bất biến (minh họa)

~~~yaml
service: order-api
regions:
  primary: region-a
  recovery: region-b
security_requirements:
  ingress_tls: required
  waf: required_in_all_serving_regions
  admin_access: privileged_jump_and_mfa
  public_database_endpoint: forbidden
  identity_validation: required
  application_audit_log: required
  network_flow_log: required
  encryption_at_rest: required
  inter_region_replication_encryption: required
failover_gates:
  business_canary: passing
  security_readiness: passing
  database_writer_fenced: true
  capacity_peak_rps: 9000
  replication_state: acceptable_to_rpo
~~~

Mẫu trên là **policy specification tự định nghĩa**, không phải cú pháp mặc định của Terraform/Kubernetes/cloud. Nó có thể được chuyển thành policy-as-code và kiểm tra trước triển khai/cho phép failover. Cần quyết định cụ thể công cụ nào là nguồn sự thật và cách xử lý trường hợp kiểm tra thất bại.

### 13.3. Tránh lỗi tương quan khi release

Triển khai đồng thời một cấu hình sai đến A và B làm mất lợi ích dự phòng. Có thể phân tách pipeline thành từng đợt (region canary/staggered rollout), có test bảo mật và thời gian quan sát trước khi áp dụng rộng hơn. Song song, phải tránh để region B “đứng yên” quá lâu khiến phiên bản phần mềm, schema, WAF rule và chứng chỉ không còn tương thích với luồng traffic mới.

## 14. Runbook failover và failback

Runbook phải được thử nghiệm; tài liệu chỉ ghi “chuyển DNS sang B” là chưa đủ.

| Giai đoạn | Thao tác | Bằng chứng tối thiểu |
|---|---|---|
| **Detect** | Xác nhận sự cố và phạm vi với nhiều tín hiệu; ghi thời điểm bắt đầu | SLO/error/latency, network health, incident ID |
| **Assess** | Kiểm tra B có app, dữ liệu, quyền, khóa, WAF, log và capacity đáp ứng không | Readiness report theo region |
| **Decision** | Xác định người/cơ chế có thẩm quyền; chốt kịch bản failover hoặc cô lập | Quyết định được audit |
| **Protect data** | Kiểm soát writer, fencing/replica promotion nếu cần | Trạng thái replication, write owner |
| **Switch traffic** | Thay đổi traffic weight, global LB hoặc DNS theo kiến trúc | Change event, bản ghi route |
| **Verify** | Chạy canary đọc/ghi hợp lệ, kiểm tra xác thực, nghiệp vụ, latency, bảo mật | Transaction IDs, SIEM/EDR/network logs |
| **Stabilize** | Quan sát tải và error budget, bảo đảm không retry storm, giữ nguyên chính sách | Dashboard, incident timeline |
| **Recover & failback** | Khôi phục A, đối soát/sync, kiểm tra bảo mật, lên lịch chuyển có kiểm soát | Reconciliation, readiness, approval, kết quả canary |
| **Review** | Tính RTO/RPO thực đo, gaps, hành động cải tiến | Postmortem và backlog có owner |

### Ví dụ timeline giả lập

| UTC | Sự kiện | Diễn giải |
|---|---|---|
| 08:00:00 | Region A suy giảm, canary nghiệp vụ lỗi | Điểm bắt đầu tính thời gian gián đoạn |
| 08:00:45 | Bộ đo xác nhận lỗi liên tục từ nhiều điểm | Chưa chuyển cho đến khi kiểm tra B |
| 08:02:10 | B vượt qua security/capacity readiness, dữ liệu đủ điều kiện | Quyết định chuyển được ghi nhận |
| 08:03:20 | Hoàn thành chuyển traffic | Lưu lượng mới bắt đầu đổ về B |
| 08:05:40 | Giao dịch thử nghiệm và phần lớn SLI về ngưỡng | Thời điểm khôi phục nghiệp vụ theo định nghĩa |

Nếu định nghĩa phục hồi là giao dịch thành công đạt SLO ở 08:05:40, **RTO thực đo = 5 phút 40 giây**, không phải 3 phút 20 giây (thời điểm đổi routing). RPO phải lấy từ bằng chứng về bản ghi cuối cùng còn nguyên vẹn, xác định theo loại dữ liệu/transaction; không suy diễn chỉ từ replication lag dashboard.

### Failback: không vội quay lại

Sau khi Region A phục hồi, cần đối soát các write trong B, xác định lại writer chính, đồng bộ dữ liệu, kiểm tra phiên và kết nối, chạy tải thử, xác thực IAM/WAF/log và chuẩn bị kế hoạch rollback. Một số hệ thống vận hành tốt nhất khi **giữ B làm chính lâu hơn** thay vì tự động chuyển ngược khi A vừa “xanh” trở lại.

## 15. Kiểm thử có kiểm soát và tiêu chí nghiệm thu

Một chương trình diễn tập có thể tăng dần mức độ:

1. **Tabletop:** mô phỏng sự cố trên sơ đồ, rà quyết định, người trực, phụ thuộc, thời điểm và bằng chứng cần thu.
2. **Readiness test:** kiểm tra chạy canary ở region B, khớp chính sách bảo mật, khóa, định danh và log mà chưa chuyển người dùng thật.
3. **Partial traffic shift:** chuyển một tỷ lệ nhỏ lưu lượng thử nghiệm được giám sát, bảo đảm xử lý giao dịch/phiên đúng.
4. **Controlled regional failover:** thực hiện trong staging hoặc production được phê duyệt, có rollback, người chịu trách nhiệm, giới hạn tác động.
5. **Failure injection:** cô lập link, làm lỗi service/dns/egress phụ thuộc trong môi trường phù hợp để xác nhận hành vi trước các kiểu lỗi khác nhau.
6. **Failback rehearsal:** chuyển trở lại sau đối soát, đo tác động và xác minh security posture.

**Điều kiện dừng:** phát hiện mất toàn vẹn dữ liệu, hai writer không xác định, nghi xâm nhập thật, không có telemetry bắt buộc, vượt ngưỡng lỗi cho phép, hoặc phương án khôi phục không còn thực hiện được. Với chaos/failure injection, chỉ tác động đến tài nguyên và khung thời gian đã duyệt.

### Tiêu chí nghiệm thu tham khảo

| Nhóm | Ví dụ tiêu chí có thể kiểm chứng |
|---|---|
| Sẵn sàng | Các chức năng trọng yếu phục hồi trong RTO đã thống nhất |
| Dữ liệu | Mất dữ liệu thực đo không vượt RPO; không tạo double-write hoặc sai giao dịch |
| Bảo mật | WAF/TLS/identity/segment/egress vẫn cưỡng chế đúng policy ở B |
| Năng lực | B chịu được tải lỗi vùng + retry hợp lý với độ trễ trong SLO |
| Quan sát | Có log điều khiển, xác thực, ứng dụng, mạng ở từng region và correlation theo incident |
| Điều hành | Có người/cơ chế quyết định, bằng chứng thay đổi, cleanup và lịch failback |
| Phục hồi | Khôi phục được từ backup sạch, thử được khi key/secret hoặc vùng chính mất |

Không tuyên bố “PASS” dựa trên việc health check trở lại `green`; phải đối chiếu với các tiêu chí đã duyệt trước diễn tập.

## 16. Quyết định kiến trúc bằng ADR

**Architecture Decision Record (ADR)** giúp lưu lại vì sao chọn phương án, những rủi ro chấp nhận và điều kiện xem xét lại.

Ví dụ:

~~~text
ADR-006: Multi-region cho order-api
Status: Proposed

Context:
- Cần phục hồi API đơn hàng trong <= 10 phút.
- Nghiệp vụ yêu cầu xác định được giao dịch nào đã ghi nhận.
- Mỗi region có >= 2 AZ; không phụ thuộc DB ở region đang lỗi.
- Giữ WAF, TLS, IAM, firewall segmentation và audit ở region dự phòng.

Decision:
- Chọn active-passive với Region B hot standby.
- Chỉ một database writer; promotion phải có fencing/quorum theo công nghệ DB.
- Global routing chuyển traffic khi health, security và data gates đều đạt.
- Cấu hình bằng IaC, kiểm tra drift, kiểm thử DR theo lịch.

Consequences:
- Chi phí duy trì B cao hơn backup-and-restore.
- Cần kiểm thử replication, routing và capacity.
- Failback là tác vụ riêng, có phê duyệt sau đối soát.

Rejected alternatives:
- Chỉ multi-AZ: không đáp ứng kịch bản mất toàn region.
- Active-active multi-writer: tăng độ phức tạp nhất quán và xử lý trùng
  trong khi nhu cầu hiện tại chưa biện minh được.

Review triggers:
- Tải tăng vượt capacity B, thay đổi RTO/RPO,
  phát sinh giới hạn dữ liệu theo quốc gia hoặc thay đổi nền tảng DB.
~~~

Con số và quyết định trên mang tính **ví dụ**. Trong ADR thật, thêm sơ đồ luồng, dependency inventory, threat model, kết quả benchmark, chi phí và người phê duyệt.

### Câu hỏi khi review một thiết kế

1. Nếu toàn bộ Region A bị mất **ngay lúc giao dịch đang ghi**, đâu là writer hợp lệ và làm sao chống xử lý trùng?
2. Với Region B còn sống nhưng IdP/KMS/secret store của A mất, những request nào thực sự còn chạy được?
3. Luồng vào B có đi qua WAF, TLS, cơ chế xác thực và segmentation như ở A không? Có lối đi tắt nào?
4. Nếu traffic toàn bộ chuyển về B vào giờ cao điểm, giới hạn đầu tiên là CPU, database, NAT, WAF hay đối tác?
5. Trong trường hợp đứt link A–B mà cả hai region vẫn sống, ai quyết định chuyển writer và bằng chứng fencing là gì?
6. Khi kẻ tấn công đã kiểm soát pipeline hoặc account điều hành, liệu hai region có bị thay đổi cùng lúc không?
7. RTO/RPO được đo bằng bài diễn tập thực tế hay chỉ suy ra từ cam kết của nhà cung cấp?

## 17. Bài tập áp dụng

**Bối cảnh:** một nền tảng API đang hoạt động ở Region A với hai AZ, có WAF phía trước, database primary và SIEM đặt tại A. Region B đã có web/API nhưng **chưa có bản sao KMS key đủ điều kiện** và firewall egress B chưa được đối tác cho phép. Hệ thống dùng DNS health-based routing TTL = 60 giây. Mục tiêu nghiệp vụ là RTO 8 phút, RPO 2 phút.

**Yêu cầu:**

1. Chỉ ra ít nhất bốn lý do khiến hiện trạng **chưa đạt** mục tiêu failover.
2. Xây checklist readiness trước khi B được đưa vào tập endpoint phục vụ.
3. Chọn cách xử lý database sao cho có writer rõ và đo được RPO.
4. Đề xuất nguồn telemetry để phân biệt lỗi DNS, lỗi dữ liệu và lỗi identity.
5. Lập phương pháp đo RTO mà không dùng thời điểm thay đổi DNS làm mốc hoàn tất.

**Hướng giải:** cần xác minh quyền giải mã bằng KMS ở B, allowlist egress đối tác, khả năng hoạt động của log/SIEM khi A mất, dữ liệu/replication và năng lực tải của B; kiểm tra readiness gồm WAF/TLS/IAM, firewall, EDR/IDS, canary nghiệp vụ, backup/restore và quota. Sử dụng cơ chế một writer với quy trình fencing/promotion phù hợp, thu bằng chứng các giao dịch cuối cùng để tính RPO. Đối chiếu DNS answers, LB/HTTP metrics, ứng dụng, DB, KMS/IdP, firewall và egress logs. Mốc kết thúc RTO là khi giao dịch trọng yếu lại thành công trong ngưỡng SLO đã thống nhất.

## 18. Ghi nhớ

Một kiến trúc multi-region chỉ thực sự có khả năng phục hồi nếu **vùng dự phòng có thể phục vụ nghiệp vụ một cách an toàn trong các failure mode đã giả định**. Phải thiết kế đồng thời luồng truy cập, dữ liệu, quyết định writer, danh tính, khóa, firewall, DNS, WAF, telemetry, capacity và con người. Failover là một **quy trình vận hành có điều kiện và bằng chứng**, không chỉ là thao tác chuyển DNS; failback là một quyết định độc lập cần đối soát và kiểm thử.
