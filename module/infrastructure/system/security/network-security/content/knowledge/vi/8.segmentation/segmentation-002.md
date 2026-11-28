# Physical và logical segmentation: phân đoạn mạng vật lý và logic

**Network segmentation (phân đoạn mạng)** là việc chia hạ tầng thành các vùng với **ranh giới kết nối và chính sách truy cập rõ ràng**. Mục đích là để thiết bị chỉ liên lạc với những hệ thống cần thiết, giới hạn phạm vi ảnh hưởng khi một thành phần bị xâm nhập và tạo các điểm quan sát lưu lượng có thể quản trị. Hai cách tiếp cận nền tảng là **physical segmentation (phân đoạn vật lý)** và **logical segmentation (phân đoạn logic)**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, phân đoạn là một phần quan trọng của phòng vệ nhiều lớp, phối hợp với firewall, VPN, Network Access Control (NAC), IDS/IPS, bảo vệ DNS, mạng không dây và kiểm soát mạng đám mây. Khi phân tích lưu lượng hoặc mô hình hóa mối đe dọa, câu hỏi cần trả lời là: **vùng nào được phép nói chuyện với vùng nào, qua đường nào, bằng giao thức gì và ai thực thi quyết định đó?**

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, người học có thể:

1. Phân biệt phân đoạn vật lý và phân đoạn logic theo **hạ tầng, điểm thực thi, chi phí và mức độ cô lập**.
2. Giải thích vai trò của **VLAN, subnet, VRF, ACL, firewall, overlay và microsegmentation**.
3. Vẽ luồng truy cập **north–south** và **east–west**, xác định ranh giới tin cậy và nơi có nguy cơ di chuyển ngang.
4. Thiết kế ma trận chính sách theo **nguồn – đích – dịch vụ – điều kiện**, ưu tiên quyền tối thiểu.
5. Xác minh một thiết kế phân đoạn bằng cấu hình, bảng định tuyến, log và phép thử kết nối được ủy quyền.
6. Nhận ra những sai lầm như **coi VLAN là firewall**, định tuyến làm rò rỉ vùng hoặc chỉ lọc ở biên Internet.

## 2. Vì sao cần phân đoạn mạng?

Giả sử một công ty có máy người dùng, API nội bộ, cơ sở dữ liệu, thiết bị IoT, hệ thống quản trị và mạng khách. Nếu mọi thành phần cùng truy cập được tất cả các thành phần khác, một laptop bị nhiễm mã độc có thể dễ dàng thử kết nối tới các máy chủ, thiết bị quản trị hoặc camera không liên quan đến công việc của nó.

Phân đoạn nhằm giảm các đường liên lạc **không cần thiết**. Một thiết kế tốt hỗ trợ:

- **Giới hạn lateral movement:** thiết bị bị xâm nhập không tự do truy cập máy khác chỉ vì cùng mạng tổ chức.
- **Bảo vệ dữ liệu quan trọng:** vùng cơ sở dữ liệu chỉ nhận truy cập từ ứng dụng có quyền, thay vì mọi máy nhân viên.
- **Phân tách mức tin cậy:** khách, thiết bị cá nhân (BYOD), IoT, máy quản trị và dịch vụ sản xuất có chính sách khác nhau.
- **Tạo điểm kiểm soát và giám sát:** firewall, ACL, IDS/IPS hoặc chính sách workload có thể ghi nhận các luồng qua ranh giới.
- **Giảm phạm vi sự cố vận hành:** lỗi broadcast, thay đổi cấu hình hoặc thiết bị có hành vi bất thường có thể được giới hạn trong một phần hạ tầng tùy thiết kế.
- **Hỗ trợ vận hành và kiểm toán:** giải thích ai được tiếp cận hệ thống nào và vì sao.

**Phân đoạn không thay thế xác thực hoặc bản vá.** Nếu một dịch vụ được phép nhận kết nối nhưng có lỗ hổng, rủi ro vẫn tồn tại. Phân đoạn chỉ giảm những con đường có thể bị lợi dụng; cần kết hợp bảo vệ host, kiểm soát danh tính, mã hóa và theo dõi.

## 3. Physical segmentation: phân đoạn bằng hạ tầng vật lý

**Phân đoạn vật lý** dùng hạ tầng hoặc đường kết nối riêng để tạo ranh giới giữa các miền mạng. Tùy yêu cầu, có thể tách switch, cáp, router, đường truyền WAN, thiết bị bảo mật và thậm chí tủ/rack hoặc vị trí đặt hệ thống.

Ví dụ khái niệm:

~~~text
         MẠNG NGHIỆP VỤ                MẠNG THIẾT BỊ ĐẶC THÙ

  [Laptop nhân viên]                   [Bộ điều khiển OT]
           │                                   │
     [Switch riêng A]                    [Switch riêng B]
           │                                   │
     [Router/Firewall A]                 [Gateway riêng B]
           │                                   │
    Mạng doanh nghiệp                Mạng vận hành hạn chế

     Không có kết nối chéo trực tiếp theo thiết kế.
~~~

Nếu không có đường dẫn dữ liệu giữa hai miền, lưu lượng IP không thể đi trực tiếp từ miền này sang miền kia bằng việc định tuyến thông thường. Tuy nhiên, **cô lập vật lý thực tế phụ thuộc mọi kết nối tồn tại**: một máy hai card mạng, đường truy cập quản trị, modem, Wi-Fi phụ, thiết bị sao lưu hoặc USB có thể tạo cầu nối ngoài ý định. Vì vậy, không nên kết luận “air gap” chỉ từ việc hai mạng dùng switch khác nhau.

### 3.1. Ví dụ áp dụng

- **Mạng quản trị out-of-band (OOB):** cổng quản trị của thiết bị mạng hoặc máy chủ đi qua hệ thống switch/đường quản trị riêng, với tài khoản và phương án truy cập được kiểm soát.
- **Hệ thống công nghiệp/OT hoặc thiết bị an toàn:** có thể yêu cầu mạng vật lý riêng vì khả năng tương thích, yêu cầu vận hành hoặc mức tác động khi sự cố xảy ra.
- **Môi trường thử nghiệm có rủi ro cao:** thiết bị và đường uplink thử nghiệm được tách ra để hạn chế ảnh hưởng tới sản xuất.
- **Hạ tầng có yêu cầu cô lập đặc biệt:** một số tài sản cần tài nguyên truyền dẫn và thiết bị chuyên dụng để giảm các phụ thuộc dùng chung.

### 3.2. Ưu điểm và giới hạn

| Điểm mạnh | Giới hạn và chi phí |
|---|---|
| Ranh giới dễ chỉ ra bằng thiết bị, cổng và đường dây cụ thể | Cần thêm switch, cáp, router, không gian, điện và năng lực vận hành |
| Giảm sự phụ thuộc vào cấu hình chia sẻ như VLAN/VRF trên cùng hạ tầng | Việc mở rộng hoặc di chuyển tài sản có thể đòi hỏi thay đổi vật lý |
| Có thể giảm tác động của một số lỗi cấu hình hoặc lỗi phần mềm của hạ tầng dùng chung | Không loại bỏ cấu hình sai trên thiết bị trong từng miền |
| Thuận lợi cho một số yêu cầu về mạng OOB và hệ thống nhạy cảm | Vẫn phải kiểm tra các kết nối phụ, quản trị từ xa, sao lưu và người dùng hai mạng |

**Khác switch chưa chắc đã khác miền bảo mật.** Nếu hai switch được nối vào một router cho phép định tuyến không giới hạn, các máy ở hai phía vẫn có thể liên lạc. Đường cáp riêng tạo ranh giới vật lý, nhưng **chính sách kết nối** tại mọi điểm nối mới quyết định khả năng đi qua ranh giới.

## 4. Logical segmentation: phân đoạn trên hạ tầng chia sẻ

**Phân đoạn logic** sử dụng các cơ chế cấu hình hoặc ảo hóa để chia một hạ tầng vật lý dùng chung thành những miền lưu lượng và quyền khác nhau. Không nhất thiết phải có một switch riêng cho mỗi nhóm tài sản.

Các thành phần thường được kết hợp:

| Cơ chế | Tác dụng chính | Giới hạn cần hiểu |
|---|---|---|
| **VLAN (IEEE 802.1Q)** | Tách miền quảng bá Ethernet Layer 2 trên thiết bị hỗ trợ | **VLAN không tự chặn định tuyến giữa các VLAN**; cần kiểm soát tại L3 |
| **IP subnet** | Xác định phạm vi địa chỉ và quy tắc định tuyến ở Layer 3 | Khác subnet không bảo đảm bị cấm truy cập nếu router cho phép |
| **VRF (Virtual Routing and Forwarding)** | Duy trì bảng định tuyến độc lập trên cùng router/thiết bị hỗ trợ | Route leaking, kết nối service hoặc cấu hình sai có thể cho phép liên lạc giữa các VRF |
| **ACL (Access Control List)** | Cho phép/từ chối theo nguồn, đích, giao thức, cổng và các thuộc tính được thiết bị hỗ trợ | Phạm vi theo giao diện/chiều, thứ tự rule và chính sách mặc định phải rõ ràng |
| **Firewall stateful** | Thực thi chính sách và theo dõi trạng thái phiên tại ranh giới | Có thể bỏ sót luồng đi đường khác hoặc traffic cùng vùng không qua firewall |
| **VXLAN / overlay networking** | Chở các mạng logic trên nền IP, thường dùng trong data center/cloud | Overlay không mặc nhiên tạo chính sách bảo mật; cần kiểm soát kết nối và định tuyến |
| **Security group / NSG / NACL cloud** | Chính sách theo network interface, subnet hoặc tài nguyên tùy nền tảng | Khác nhau về stateful/stateless, hướng lưu lượng và phạm vi áp dụng |
| **Microsegmentation** | Cấp quyền chi tiết giữa workload, máy ảo, container hoặc dịch vụ | Cần inventory, danh tính/nhãn nhất quán, kiểm soát thay đổi và bao phủ mọi đường đi |

Sơ đồ logic trên một hạ tầng switch dùng chung:

~~~text
                    [Switch vật lý dùng chung]
                       │      │       │
                  VLAN 10  VLAN 20  VLAN 30
                  Employee  Server   Guest
                       │      │       │
                       └──────┴───────┘
                              │
                  [L3 Gateway / Firewall]
                              │
            Quyết định traffic giữa các vùng
            theo ACL, route, state và policy
~~~

**Không nên đồng nhất VLAN, subnet và security zone.** Một VLAN thường ánh xạ với một subnet IPv4/IPv6 trong thiết kế đơn giản, nhưng đó là **quy ước triển khai**, không phải quy luật bắt buộc. Một **security zone** là nhóm tài sản có chính sách tin cậy giống nhau; một zone có thể gồm nhiều VLAN/subnet và được thực thi ở những điểm khác nhau.

### 4.1. VLAN tách broadcast domain, không tự tạo firewall

VLAN 10 và VLAN 20 thường không trao đổi frame Layer 2 trực tiếp như những máy cùng VLAN. Tuy nhiên, nếu router hoặc Layer 3 switch có giao diện ở cả hai VLAN và cho phép route giữa chúng, máy VLAN 10 **vẫn có thể gửi IP traffic đến VLAN 20**.

~~~text
Host A (VLAN 10)                        Server B (VLAN 20)
        │                                      ▲
        ▼                                      │
    [Switch] ──> [Inter-VLAN Routing] ─────────┘
                        │
             Có ACL/firewall kiểm tra?
                        │
                Có: áp chính sách.
                Không: có thể route bình thường.
~~~

Điểm thực thi có thể là SVI trên Layer 3 switch, router, firewall hoặc một nền tảng mạng phân tán. Thiết kế phải chỉ rõ **ai kiểm tra, theo chiều nào và quy tắc mặc định là gì**, thay vì chỉ liệt kê các VLAN.

### 4.2. VRF, routing domain và điểm kết nối chéo

VRF thường cho phép cùng một router giữ nhiều bảng định tuyến độc lập. Ví dụ, route tới mạng quản trị không xuất hiện trong VRF dành cho khách trừ khi được cấu hình để kết nối hoặc chia sẻ route.

Tuy nhiên, **route leaking** giữa VRF, kết nối qua firewall tập trung, dịch vụ dùng chung hoặc tunnel có thể mở đường cho traffic qua vùng. Việc xem các bảng định tuyến và điểm nối chéo là bắt buộc khi đánh giá thực tế.

### 4.3. Microsegmentation đi sâu tới workload

Phân đoạn truyền thống thường tập trung **giữa VLAN, subnet hoặc zone**. Microsegmentation bổ sung chính sách **giữa các workload**, thậm chí những workload đang cùng một subnet.

Ví dụ một hệ thống ba tầng:

~~~text
       [Web/API workload] ── TLS :8443 ──> [Application workload]
                                                │
                                         DB TCP :5432
                                                ▼
                                          [Database]

       [Employee laptop] ── KHÔNG được đi thẳng ──> [Database]
       [Workload khác]   ── KHÔNG được đi thẳng ──> [Database]
~~~

Chính sách có thể được thực thi tại host firewall, hypervisor, virtual switch, Kubernetes NetworkPolicy/CNI tương thích hoặc service gateway. **Không phải mọi chính sách container mặc định đều giới hạn ingress và egress**, và hiệu quả phụ thuộc CNI/nền tảng hỗ trợ. Cần xác nhận chính sách được thực thi ở đúng điểm, đúng cả chiều yêu cầu và phản hồi.

## 5. So sánh physical và logical segmentation

| Tiêu chí | Physical segmentation | Logical segmentation |
|---|---|---|
| **Cách tạo ranh giới** | Hạ tầng, đường truyền hoặc thiết bị riêng | Cấu hình VLAN/VRF, route, ACL, firewall, overlay, chính sách workload |
| **Tài nguyên sử dụng** | Có thể tách riêng switch/router/cáp | Thường dùng chung một phần hạ tầng vật lý |
| **Linh hoạt mở rộng** | Thay đổi có thể cần cấp phát thiết bị và đi dây | Thường dễ mở rộng hơn bằng quản trị cấu hình và tự động hóa |
| **Chi phí trực tiếp** | Thường tăng phần cứng, không gian và vận hành | Giảm nhu cầu thiết bị riêng nhưng tăng yêu cầu quản lý policy |
| **Lỗi cấu hình đáng chú ý** | Kết nối chéo, dual-homed host, kết nối phụ không được kiểm kê | Trunk sai, route leaking, ACL quá rộng, chính sách workload chưa bao phủ |
| **Điểm kiểm tra** | Sơ đồ cáp, interface, uplink, gateway và mọi đường nối | VLAN/VRF, route table, policy, firewall rule, security group và luồng thực tế |
| **Giới hạn bảo vệ** | Vẫn tồn tại rủi ro từ người vận hành, thiết bị trung gian, đường quản trị | Vẫn phụ thuộc phần mềm thiết bị, chất lượng cấu hình và thực thi ở đúng chỗ |
| **Tình huống thường dùng** | OOB management, OT nhạy cảm, môi trường đặc biệt | Campus, Wi-Fi khách/nhân viên, data center, cloud, microservices |

**Không có lựa chọn nào luôn an toàn hơn trong mọi tình huống.** Hạ tầng vật lý riêng nhưng có đường quản trị mở rộng có thể kém an toàn hơn một hệ thống logic được kiểm soát nghiêm. Ngược lại, những hệ thống đặc biệt có thể cần cô lập phần cứng để giảm mức phụ thuộc dùng chung. Nhiều tổ chức sử dụng **kết hợp**: tách mạng OOB/OT trọng yếu bằng hạ tầng riêng, đồng thời chia nhiều vùng logic trên mạng nghiệp vụ.

## 6. North–south và east–west traffic: cần phân đoạn những hướng nào?

Hai khái niệm giúp xác định nơi chính sách cần được đặt:

- **North–south traffic:** lưu lượng đi vào/ra một miền hoặc data center, ví dụ Internet ↔ ứng dụng công khai, máy nhân viên ↔ dịch vụ SaaS. Cách định nghĩa ranh giới tùy kiến trúc.
- **East–west traffic:** lưu lượng giữa các máy/workload trong cùng miền hạ tầng, ví dụ API ↔ database, pod ↔ pod, host ↔ host.

~~~text
                     [Internet]
                         │
                 North–south traffic
                         │
                 [Firewall biên]
                         │
         ┌───────────────┼────────────────┐
         │               │                │
      [API 1] <── east–west ──> [API 2]   [Logging]
         │               │                │
         └──────────────> [Database] <────┘
                 East–west policy
~~~

Firewall biên chỉ kiểm tra lưu lượng **đi qua chính nó**. Nếu API 1 và API 2 có thể giao tiếp trực tiếp trong nội bộ mà không qua điểm thực thi, một rule firewall biên không kiểm soát được luồng đó. Vì vậy cần xem xét host firewall, microsegmentation hoặc đường ép lưu lượng qua firewall nội bộ theo thiết kế.

**Lưu lượng được phép đi qua không đồng nghĩa đã được xác thực ứng dụng.** TLS/mTLS, quản lý danh tính dịch vụ và authorization vẫn cần thiết, đặc biệt với traffic east–west giữa các workload.

## 7. Thiết kế segmentation dựa trên tài sản và luồng nghiệp vụ

Thay vì bắt đầu bằng câu hỏi “cần bao nhiêu VLAN?”, hãy bắt đầu bằng **tài sản, dòng dữ liệu và rủi ro**.

### Bước 1. Kiểm kê và phân nhóm tài sản

Ghi lại loại máy, chủ sở hữu, môi trường, vị trí và độ nhạy dữ liệu. Ví dụ:

| Nhóm tài sản | Dữ liệu hoặc chức năng | Mức ưu tiên bảo vệ |
|---|---|---|
| Máy nhân viên | Truy cập ứng dụng nghiệp vụ | Trung bình đến cao, tùy quyền người dùng |
| API ứng dụng | Xử lý yêu cầu của người dùng và backend | Cao |
| Database | Lưu dữ liệu kinh doanh hoặc thông tin nhạy cảm | Cao |
| Máy quản trị / jump host | Truy cập hệ thống vận hành | Rất cao |
| IoT, máy in, camera | Chức năng thiết bị chuyên biệt | Tùy môi trường; thường cần hạn chế giao tiếp |
| Mạng khách | Thiết bị bên ngoài tổ chức | Không được tin cậy để truy cập nội bộ |

### Bước 2. Vẽ đường đi cần thiết

Đối với mỗi ứng dụng, hỏi:

1. **Ai khởi tạo** kết nối?
2. **Đến đâu**, bằng DNS name, IP, cổng và giao thức nào?
3. Đường đi qua VPN, gateway, load balancer, firewall hoặc NAT nào?
4. Luồng nào là **bắt buộc cho hoạt động**, luồng nào chỉ xuất hiện do cấu hình rộng từ trước?
5. Phản hồi của phiên được thiết bị stateful xử lý ra sao?
6. Có traffic IPv6, đường dự phòng, luồng quản trị, backup, giám sát hoặc cập nhật phần mềm không?

### Bước 3. Nhận diện ranh giới tin cậy

Ví dụ: guest ↔ corporate, employee ↔ server, application ↔ database, production ↔ development, management ↔ production, on-premises ↔ cloud.

Ranh giới cần rõ **điểm kiểm tra**, chẳng hạn switch ACL, inter-VLAN firewall, host firewall, cloud security group hoặc identity-aware proxy. Nếu một đường đi có thể vòng qua điểm kiểm tra, chính sách trên điểm đó có thể không đủ.

### Bước 4. Xây ma trận truy cập

Một ma trận truy cập có thể biểu diễn **luồng được phép và luồng bị cấm**, là nền để cấu hình và kiểm thử.

| Nguồn | Đích | Giao thức/cổng (ví dụ) | Quyết định | Lý do |
|---|---|---|---|---|
| Internet | Reverse proxy công khai | TCP/443 | Allow | Tiếp nhận HTTPS công khai |
| Internet | Database | Mọi kết nối trực tiếp | Deny | DB không phải dịch vụ công khai |
| Mạng nhân viên | API nội bộ | TCP/443 | Allow theo policy | Truy cập nghiệp vụ được xác thực |
| Mạng nhân viên | Database | TCP/5432 | Deny | Chỉ application workload được kết nối DB |
| Application workload | Database | TCP/5432 | Allow theo danh tính/nguồn | Giao tiếp tầng ứng dụng đến dữ liệu |
| Jump host quản trị | Server quản trị | SSH TCP/22 hoặc kênh quản trị phù hợp | Allow có kiểm soát | Quản trị qua điểm đã xác thực |
| Mạng khách | Mạng nội bộ | Mọi kết nối trực tiếp | Deny | Không có nhu cầu truy cập tài nguyên nội bộ |
| IoT camera | Máy chủ ghi hình | Cổng ứng dụng được định nghĩa | Allow hạn chế | Chỉ truyền dữ liệu tới hệ thống quản lý |

**Các cổng trong bảng chỉ là ví dụ**, không đại diện mọi ứng dụng. Một số kết nối hỗ trợ như DHCP, DNS, NTP, monitoring, PKI/OCSP/CRL, cập nhật hoặc backup có thể cần đưa vào ma trận sau khi xác minh yêu cầu thực tế.

### Bước 5. Áp dụng mặc định từ chối và ghi ngoại lệ

Chính sách hướng tới **deny by default** giữa các vùng, sau đó mở đúng luồng có nhu cầu. Mỗi rule cần mô tả nguồn, đích, dịch vụ, hướng, owner, lý do, thời hạn ngoại lệ khi có và bằng chứng phê duyệt. Với firewall stateful, lưu lượng phản hồi thuộc phiên hợp lệ thường được phép tự động; không nên tự động tạo rule hai chiều quá rộng nếu nền tảng không yêu cầu.

## 8. Ví dụ kiến trúc phân đoạn cho tổ chức nhỏ

Giả sử công ty thiết kế các vùng sau trên hệ thống logic, đồng thời có đường quản trị thiết bị riêng:

~~~text
                      Internet
                         │
                 [Edge Firewall]
                         │
             +-----------+------------+
             |                        |
         [DMZ/Web]                [VPN Gateway]
             |                        |
             +------[Internal Firewall]+
                           │
            +--------------+------------------+
            |              |                  |
      [Employee]       [Application]     [Management]
      VLAN 10          VLAN 20           VLAN 40
                           │
                    [Database Zone]
                       VLAN 30

      [Guest VLAN 50] ──> Internet only (theo policy)
      [IoT VLAN 60]   ──> Thiết bị quản lý được chỉ định

      [OOB Switch riêng] ──> Cổng quản trị thiết bị
      (Có chính sách truy cập và tài khoản quản trị riêng)
~~~

**Ví dụ địa chỉ dành cho lab**, sử dụng RFC 1918, không phải thông tin của hệ thống thực:

| Zone | VLAN mẫu | Subnet IPv4 mẫu | Mục đích |
|---|---:|---|---|
| Employee | 10 | 10.20.10.0/24 | Laptop nhân viên |
| Application | 20 | 10.20.20.0/24 | Dịch vụ ứng dụng |
| Database | 30 | 10.20.30.0/24 | Hệ quản trị cơ sở dữ liệu |
| Management | 40 | 10.20.40.0/24 | Máy quản trị và jump host |
| Guest | 50 | 10.20.50.0/24 | Khách và BYOD giới hạn |
| IoT | 60 | 10.20.60.0/24 | Camera, máy in, thiết bị đặc thù |

Cần phân biệt **phân tách đường truyền** với **vị trí thực thi**: các VLAN có thể cùng đi trên một trunk vật lý, trong khi firewall kiểm soát inter-VLAN traffic. Nếu inter-VLAN routing xảy ra trực tiếp trên switch L3 trước khi tới firewall, phải có ACL tương đương hoặc thiết kế buộc traffic đi qua đúng điểm kiểm tra.

### Ví dụ biểu diễn policy theo ý nghĩa nghiệp vụ

~~~yaml
# Ví dụ mô tả chính sách; không phải cấu hình dùng trực tiếp
# cho một firewall hoặc thiết bị mạng cụ thể.
rules:
  - source_zone: employee
    destination_zone: application
    service: tcp/443
    action: allow
    reason: user-facing-api
  - source_zone: application
    destination_zone: database
    service: tcp/5432
    action: allow
    reason: application-database
  - source_zone: guest
    destination_zone: internal
    service: any
    action: deny
    reason: guest-isolation
  - source_zone: any
    destination_zone: database
    service: any
    action: deny
    reason: default-isolation
~~~

Đây là **ý tưởng policy**, không phải cấu hình có thể copy trực tiếp. Thứ tự xử lý, các ngoại lệ cụ thể, rule ưu tiên, NAT, stateful behavior và cú pháp triển khai phụ thuộc từng thiết bị. Đặc biệt, rule tổng quát phía cuối cần được kiểm tra để không vô tình chặn cả luồng hợp lệ từ application do thứ tự rule hoặc cách xử lý nhóm.

## 9. Phân đoạn trong cloud và môi trường container

Trong cloud, các vùng mạng thường sử dụng **VPC/VNet, subnet, route table, security group/NSG, NACL, cloud firewall, private endpoint, VPN và kết nối chuyên dụng**, tùy nền tảng. Tách subnet là điều kiện tổ chức tài nguyên, nhưng **không tự chứng minh các tài nguyên không thể truy cập nhau**.

Điểm cần quan sát:

- **Routing:** hai subnet trong cùng VPC/VNet có thể có đường nội bộ; peering, transit gateway hoặc VPN có thể mở rộng khả năng kết nối.
- **Network policy:** security group và NACL có thể áp dụng tại phạm vi khác nhau, với hành vi stateful/stateless khác nhau theo nền tảng.
- **Workload identity:** VM/container được phép có IP private vẫn cần xác thực với dịch vụ và quyền ứng dụng.
- **Private service connectivity:** kết nối private endpoint giúp giới hạn đường đi nhưng vẫn cần quyền ở cấp dịch vụ và DNS phù hợp.
- **Egress:** chỉ chặn inbound không ngăn được workload xâm nhập gửi dữ liệu ra ngoài bằng đường egress được phép.
- **Lưu lượng nội bộ:** traffic giữa các VM/pod có thể không đi qua thiết bị firewall biên nếu không có thiết kế kiểm soát phân tán.

### Container và Kubernetes

Trong cụm Kubernetes, **namespace** là cơ chế phân nhóm tài nguyên và quyền quản trị, **không mặc nhiên cách ly toàn bộ mạng giữa pod**. Muốn microsegmentation, cần thiết kế **NetworkPolicy** hoặc chính sách của nền tảng CNI và bảo đảm plugin mạng có hỗ trợ thực thi.

Ví dụ mô tả ý tưởng:

~~~text
Namespace: frontend   ── được phép ──> API service TCP/8443
Namespace: analytics  ── bị chặn ────> DB service TCP/5432
API workload          ── được phép ──> DB service TCP/5432
Khác                  ── mặc định từ chối theo chính sách
~~~

Một số policy chỉ áp dụng cho traffic pod và không kiểm soát đồng nhất mọi traffic từ host, node hoặc các luồng qua dịch vụ ngoài cụm. Cần hiểu triển khai thực tế, kiểm tra cả **ingress** và **egress**, DNS, health check và các thành phần quản trị trước khi khẳng định đã cô lập.

## 10. Liên hệ segmentation với NAC, firewall, VPN và IDS/IPS

| Lớp bảo vệ | Vai trò khi phân đoạn | Điểm cần chú ý |
|---|---|---|
| **Network Access Control (NAC), 802.1X** | Xác thực người dùng/thiết bị và có thể gán role/VLAN/ACL phù hợp | Gán VLAN chỉ là một phần; quyền giữa các VLAN vẫn cần policy |
| **Firewall/ACL** | Quyết định traffic nào được đi qua giữa zone hoặc workload | Bảo đảm lưu lượng thật sự đi qua đúng điểm thực thi; kiểm soát cả đường dự phòng |
| **VPN / kết nối chi nhánh** | Cung cấp đường truyền có xác thực/mã hóa theo cấu hình giữa các địa điểm | Tunnel có thể mở tuyến vào nhiều zone; vẫn phải giới hạn quyền bên trong |
| **IDS/IPS** | Giám sát hoặc chặn các luồng đi qua điểm quan sát | Cần visibility east–west; IDS đặt ngoài đường traffic không thấy mọi luồng |
| **DNS bảo mật** | Kiểm soát resolver, tên đích và một phần dấu hiệu truy cập | DNS không thay thế ACL; kiểm tra cả IP literal, IPv6 và đường egress khác |
| **Wi-Fi isolation** | Tách mạng nhân viên, khách và IoT theo SSID/VLAN/role | Nhiều SSID không bảo đảm phân đoạn đúng nếu gateway cho phép thông nhau |
| **Cloud security policy** | Phân đoạn theo subnet, interface hoặc nhãn workload | Quy tắc phụ thuộc nền tảng, cần kiểm tra route, peering và egress |

Một biện pháp phòng vệ không thể thay thế toàn bộ các biện pháp khác. **Firewall không tự xác thực máy**, **NAC không quyết định mọi quyền ứng dụng**, **VPN không làm mọi endpoint trở nên an toàn**, và **IDS không thấy traffic ngoài điểm đặt sensor**.

## 11. Rủi ro và đường vòng phá vỡ ranh giới phân đoạn

Mô hình hóa rủi ro nên xét cả lỗi cấu hình lẫn đường đi hợp lệ bị lạm dụng:

| Tình huống | Vì sao gây rủi ro? | Cách giảm thiểu |
|---|---|---|
| **Inter-VLAN routing mở rộng** | VLAN tách L2 nhưng router vẫn kết nối tới mọi subnet | ACL/firewall theo zone; mặc định từ chối các luồng không được phê duyệt |
| **Sai trunk/native VLAN hoặc cấu hình switch** | Có thể khiến traffic xuất hiện ở VLAN không mong muốn hoặc tạo nguy cơ tấn công L2 | Hạn chế VLAN allowed trên trunk, tắt trunk trên access port, tránh thiết kế native VLAN thiếu kiểm soát |
| **Route leaking giữa VRF/VPC** | Kết nối chéo làm vùng độc lập có thể thấy nhau | Kiểm tra route table, peering, transit và quy tắc policy theo nguồn/đích |
| **Dual-homed host / jump host** | Một máy có kết nối tới hai vùng có thể trở thành điểm trung chuyển | Hardening, tắt IP forwarding khi không cần, kiểm soát phiên quản trị và ghi log |
| **Rule any-to-any hoặc ngoại lệ lâu ngày** | Mất mục tiêu phân đoạn sau nhiều thay đổi | Owner và hạn ngoại lệ, rà soát rule định kỳ, dọn quyền không dùng |
| **Kết nối VPN quá rộng** | Một user từ xa có thể đi vào nhiều subnet ngoài nhu cầu | Phân quyền theo vai trò, giới hạn route/service, MFA và log |
| **Traffic east–west không qua firewall** | Điểm kiểm soát trung tâm không nhìn thấy traffic trong cùng vùng | Host firewall, microsegmentation hoặc kiến trúc buộc luồng qua điểm lọc |
| **Chỉ áp dụng IPv4** | IPv6 có thể tồn tại đường truy cập ngoài chính sách IPv4 | Kiểm kê dual-stack, kiểm tra firewall/ACL/ND/RA cho IPv6 |
| **Đường quản trị/backup/monitoring bỏ quên** | Dịch vụ vận hành tạo kênh truy cập khác đường ứng dụng | Mô hình hóa toàn bộ đường quản trị và dịch vụ phụ trợ |
| **Tài khoản/ứng dụng được cấp quyền rộng** | Kẻ tấn công lợi dụng luồng vốn được cho phép | mTLS, authorization, quản lý khóa, EDR, least privilege tại ứng dụng |

**Phân đoạn an toàn cần kiểm soát cả luồng “được phép”.** Nếu một API được phép kết nối database, việc API bị xâm nhập vẫn có thể gây nguy hại cho dữ liệu. Giảm quyền của tài khoản DB, lọc câu lệnh ở ứng dụng và giám sát hành vi cần được thực hiện song song.

## 12. Triển khai theo giai đoạn và quản lý thay đổi

Cắt mạng thành nhiều phân đoạn mà không hiểu luồng nghiệp vụ có thể gây mất kết nối nghiêm trọng. Một quy trình triển khai có kiểm soát:

1. **Khảo sát:** xác định tài sản, chủ sở hữu, ứng dụng, dependency, đường Internet/VPN/backup, IPv4/IPv6 và các luồng quản trị.
2. **Thu thập baseline:** flow logs, firewall logs, switch/router route table, DNS, dữ liệu inventory và cấu hình thực tế; phân biệt luồng cần thiết với luồng lịch sử không còn dùng.
3. **Đề xuất vùng và chính sách:** xác định zone, đường đi và điểm thực thi; tạo ma trận truy cập, bao gồm quyền phản hồi và ngoại lệ.
4. **Chạy thử trong lab hoặc phạm vi nhỏ:** xác minh cả lưu lượng cần cho phép và lưu lượng phải chặn.
5. **Triển khai từng phần:** dùng quy trình thay đổi, thông báo lịch, giám sát tỷ lệ lỗi, có cách hoàn tác cấu hình trong trường hợp gián đoạn.
6. **Giám sát sau thay đổi:** đối chiếu log drop/allow, lỗi DNS, kết nối ứng dụng, health check, độ trễ và đường dự phòng.
7. **Rà soát định kỳ:** thu hẹp quy tắc rộng, loại bỏ exception cũ, cập nhật ma trận khi ứng dụng thay đổi và kiểm tra lại sau nâng cấp mạng.

Đối với hệ thống OT và thiết bị khó cập nhật, cần kết hợp đánh giá an toàn vận hành và ý kiến của chủ hệ thống; không áp dụng ngay các thay đổi ACL hoặc quét chủ động có thể làm gián đoạn quy trình sản xuất.

### Khi cần chia sẻ dịch vụ giữa các zone

Một số dịch vụ được nhiều vùng sử dụng, chẳng hạn DNS resolver, NTP, cập nhật phần mềm, identity provider, logging, PKI, backup hoặc hệ thống quản lý cấu hình. Có thể đặt chúng trong **shared services zone** với rule cụ thể cho từng nhóm nguồn, thay vì mở kết nối tự do giữa mọi vùng.

Ví dụ, mạng khách có thể được dùng resolver được phép nhưng không được dùng đường DNS như cầu nối tới hệ thống quản trị. Cần xem xét cả giao thức và quyền ứng dụng: cho phép TCP/443 tới shared service không đồng nghĩa mọi API trên dịch vụ đó đều được sử dụng.

## 13. Kiểm chứng hiệu lực phân đoạn

Thiết kế chỉ thực sự có ý nghĩa khi kiểm chứng được rằng các đường **được phép hoạt động** và các đường **bị cấm được chặn tại điểm kiểm soát**.

### 13.1. Kiểm tra cấu hình và đường đi

Trong môi trường được phép quản trị, có thể đọc các nguồn thông tin sau:

- **Switch:** VLAN membership, trunk allowed VLAN, access port, MAC table, SVI và ACL gắn interface.
- **Router/L3 switch:** interface, route table, VRF, route leaking, default route, chính sách giữa các zone.
- **Firewall:** security zone, nguồn/đích, port/service, thứ tự rule, rule hit count, session và log allow/deny.
- **Cloud:** subnet, route table, peering/transit, security group/NSG, NACL, firewall, private endpoint.
- **Endpoint:** host firewall, trạng thái dịch vụ lắng nghe, địa chỉ IPv4/IPv6 và tuyến mạng.

Ví dụ một số lệnh **chỉ đọc** trên máy Linux do bạn quản trị:

~~~bash
ip -br addr           # Interface và địa chỉ mạng
ip route              # Bảng định tuyến IPv4
ip -6 route           # Bảng định tuyến IPv6
ss -lnt               # Các socket TCP đang lắng nghe
~~~

Trên Windows:

~~~text
ipconfig /all
route print
netstat -ano
~~~

Những lệnh này chỉ cho biết góc nhìn của máy đang kiểm tra; chúng **không thể tự xác minh toàn bộ** VLAN/VRF/firewall policy của hạ tầng.

### 13.2. Kiểm thử ma trận truy cập trong lab được ủy quyền

Giả sử lab dùng ứng dụng thử nghiệm và các máy thuộc subnet ví dụ:

| Nguồn thử | Đích thử | Kỳ vọng | Bằng chứng cần ghi |
|---|---|---|---|
| Employee | API TCP/443 | Allow | Kết nối thành công, log firewall và xác thực ứng dụng |
| Employee | Database TCP/5432 | Deny | Kết nối bị chặn tại đúng rule, log tương ứng |
| Guest | API nội bộ TCP/443 | Deny | Không thể kết nối, có log chặn hoặc xác nhận route/policy |
| Application | Database TCP/5432 | Allow | Kết nối đúng từ workload được duyệt; DB yêu cầu xác thực |
| IoT | Máy quản trị TCP/22 | Deny | ACL/firewall chặn; không có đường ngoại lệ |
| Jump host | Máy chủ quản trị TCP/22 | Allow có điều kiện | Tài khoản quản trị hợp lệ, log phiên và ACL phù hợp |

Cần lưu ý **timeout không đủ để chứng minh bị firewall chặn đúng chính sách**. Một route thiếu, host tắt hoặc service không lắng nghe cũng gây timeout. Phải kiểm tra log tại điểm thực thi, route thực tế và cấu hình dịch vụ để biết chính xác nguyên nhân.

### 13.3. Cách ghi nhận một phép thử

~~~text
Test ID:      SEG-EMP-DB-01
Thời gian:    [timestamp + timezone]
Nguồn:        Employee VLAN / IP thử nghiệm
Đích:         Database IP / TCP 5432
Expected:     DENY
Observed:     [kết quả thực tế]
Route:        [đường đi đã xác minh]
Policy hit:   [ID rule/ACL, allow hoặc deny]
Evidence:     [log, packet capture, kiểm tra service]
Result:       PASS / FAIL / INCONCLUSIVE
Owner:        [người chịu trách nhiệm]
~~~

Trạng thái **INCONCLUSIVE** quan trọng khi không đủ bằng chứng. Không nên ghi PASS chỉ vì một lần kết nối không thành công nếu chưa biết có thực sự đi tới điểm kiểm soát dự kiến hay không.

## 14. Tình huống thực tế: mạng khách truy cập được API nội bộ

**Bối cảnh giả định:** Một tổ chức có mạng khách ở VLAN 50 và API nội bộ ở VLAN 20. Chính sách viết rõ **guest → internal = DENY**. Trong kiểm tra định kỳ đã được phê duyệt, nhóm vận hành thấy một máy khách kết nối thành công tới API trên TCP/443.

**Dữ liệu quan sát ban đầu:**

~~~text
Guest:        10.20.50.25/24
API:          10.20.20.10:443
Expected:     DENY
Observed:     TCP/TLS kết nối thành công
Network:      Switch L3 và firewall biên dùng chung
~~~

Sự kiện này cho thấy **chính sách dự kiến có thể chưa được thực thi trên đường thực tế**, nhưng chưa khẳng định nguyên nhân. Quy trình phân tích:

1. **Xác minh đích và nguồn thực:** máy khách có thật trong VLAN 50 không? Tên miền có trỏ tới reverse proxy khác IP nội bộ không?
2. **Đọc route:** liệu đường guest → API được xử lý trực tiếp trên SVI của L3 switch và **không đi qua firewall biên**?
3. **Tìm điểm thực thi:** ACL ở SVI, VRF, firewall nội bộ hay host firewall nào được thiết kế để chặn luồng?
4. **Đối chiếu policy:** rule allow có phạm vi quá rộng không, có NAT hoặc đường ngoại lệ nào cho phép luồng này không?
5. **Đánh giá tác động:** tài nguyên nào nằm trong zone nội bộ, API có xác thực và phân quyền ứng dụng không, có bằng chứng truy cập dữ liệu trái phép không?
6. **Khắc phục có kiểm soát:** đặt rule tại đúng đường đi, giữ đường cần thiết cho DHCP/DNS/Internet của mạng khách, xác minh ảnh hưởng và khả năng hoàn tác.
7. **Kiểm thử lại:** xác nhận guest → API bị chặn, employee → API vẫn hoạt động và log ghi nhận đúng quy tắc.

Nếu nguyên nhân là inter-VLAN routing không qua firewall, chỉ thêm rule vào **firewall biên Internet** có thể không giải quyết sự cố. Phải thực thi tại **đường traffic thực sự đi qua**, hoặc thay đổi kiến trúc định tuyến để traffic buộc đi qua điểm kiểm soát.

### Câu hỏi tự kiểm tra

1. Vì sao chia mạng thành hai VLAN không đủ để đảm bảo chúng không truy cập nhau?
2. Một router có hai VRF riêng nhưng có route leaking có được xem là cô lập hoàn toàn không?
3. Khi nào nên cân nhắc hạ tầng vật lý riêng thay vì chỉ phân đoạn logic?
4. Vì sao chỉ kiểm thử kết nối “bị chặn” qua timeout có thể cho kết luận sai?
5. API ↔ database là traffic north–south hay east–west trong một data center thông thường?
6. Vai trò của NAC, firewall và xác thực ứng dụng khác nhau thế nào trong việc bảo vệ dữ liệu?
7. Vì sao IPv6, các đường VPN/backup và route dự phòng phải có trong ma trận phân đoạn?

## 15. Ghi nhớ trọng tâm

**Physical segmentation** tạo ranh giới bằng hạ tầng kết nối riêng; **logical segmentation** chia một phần hạ tầng dùng chung bằng VLAN, VRF, subnet, firewall, ACL, overlay hoặc chính sách workload. **VLAN chủ yếu tách miền Layer 2; việc có hay không có đường kết nối IP còn phụ thuộc định tuyến và chính sách Layer 3 trở lên.** Hai cách có thể kết hợp để phù hợp với mức độ rủi ro và yêu cầu vận hành.

Phân đoạn mạng hiệu quả bắt đầu từ **tài sản, luồng dữ liệu, ranh giới tin cậy và ma trận quyền tối thiểu**, sau đó đặt kiểm soát tại đúng điểm traffic đi qua. Cần quan sát cả **north–south** và **east–west**, kiểm tra IPv4/IPv6, VPN, dịch vụ dùng chung, cloud và đường quản trị. **Chỉ tuyên bố phân đoạn thành công khi kiểm thử được cả đường cho phép và đường từ chối, đồng thời có bằng chứng từ định tuyến và policy đang thực thi.**
