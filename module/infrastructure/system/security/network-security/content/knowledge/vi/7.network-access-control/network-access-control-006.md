# Default deny trong Network Access Control

## 1. Default deny là gì?

**Default deny** (mặc định từ chối) là nguyên tắc **chỉ cho phép những kết nối đã được phê duyệt rõ ràng**, còn các kết nối không khớp với quy tắc cho phép sẽ bị từ chối tại điểm kiểm soát. Trong bảo mật mạng, đây là một phương pháp nền tảng để quản lý quyền truy cập qua **firewall, ACL, security group, network policy, gateway** và các cơ chế kiểm soát kết nối khác.

Ví dụ, một ứng dụng có ba lớp: người dùng, dịch vụ API và cơ sở dữ liệu. Người dùng chỉ cần HTTPS đến ứng dụng; API cần truy cập database; máy người dùng **không cần** truy cập database trực tiếp. Nếu mặc định mở toàn bộ, kẻ tấn công chiếm được một máy người dùng có thể dò tìm hoặc kết nối thẳng database. Theo default deny, luồng này bị chặn từ đầu theo chính sách, ngay cả khi chưa phát hiện hành vi tấn công cụ thể.

Trong module **SECURITY_NETWORK_SECURITY**, default deny kết nối trực tiếp với các chủ đề phân đoạn mạng, firewall, VPN, xác thực kết nối, IDS/IPS, kiểm soát DNS, mạng không dây, mạng cloud, phân tích lưu lượng và threat modeling. Nó giúp giới hạn bề mặt tấn công, giảm khả năng di chuyển ngang sau xâm nhập và buộc mỗi kết nối được cấp quyền phải có mục đích.

**Sau bài học, người học có thể:**

- Phân biệt default deny với allowlist, explicit/implicit deny, least privilege và zero trust.
- Xây dựng **ma trận lưu lượng được phép** theo nguồn, đích, giao thức, chiều và mục đích.
- Giải thích khác biệt giữa **stateful** và **stateless** trong xử lý gói phản hồi.
- Áp dụng nguyên tắc trên firewall, cloud security group và Kubernetes NetworkPolicy.
- Nhận diện các phụ thuộc hợp lệ dễ bị chặn nhầm, như DNS, NTP, identity, logging và health check.
- Kiểm thử luồng hợp lệ và không hợp lệ, giám sát deny và triển khai từng bước có kế hoạch khôi phục.

## 2. Default deny khác gì các khái niệm liên quan?

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Default deny** | Không có quyền rõ ràng thì không được truy cập | Mọi kết nối mới ngoài ma trận đã duyệt bị chặn |
| **Allowlist** | Khai báo chính xác những luồng được phép | Chỉ API được dùng TCP/5432 tới database |
| **Explicit deny** | Có một quy tắc từ chối được chỉ rõ | Chặn mạng khách truy cập vùng quản trị |
| **Implicit deny** | Nếu không rule nào cho phép thì chính sách mặc định là từ chối | Firewall xử lý hết allow rule rồi drop |
| **Least privilege** | Chỉ cấp quyền tối thiểu cần thực hiện một chức năng | Chỉ service A gọi service B qua port cần thiết |
| **Zero trust** | Không tin tưởng chỉ vì thiết bị nằm trong mạng nội bộ; kiểm tra liên tục theo tài nguyên và ngữ cảnh | Kiểm tra danh tính, thiết bị và quyền khi truy cập dịch vụ |
| **Defense in depth** | Bổ sung nhiều lớp bảo vệ | Network deny + mTLS + RBAC + audit log |

**Default deny không đồng nghĩa chặn tất cả.** Một hệ thống chỉ hoạt động khi các kết nối hợp lệ được cho phép và các kết nối không có nhu cầu nghiệp vụ bị từ chối. Cách làm đúng là xây dựng danh sách ngoại lệ có căn cứ, không phải bật một rule chặn toàn bộ rồi mở rộng bừa bãi sau khi ứng dụng lỗi.

**Default deny cũng không thay thế xác thực và phân quyền ứng dụng.** Khi firewall đã cho phép API kết nối database, tài khoản ứng dụng vẫn phải có quyền giới hạn ở tầng dữ liệu; một kết nối hợp lệ về mặt mạng vẫn có thể chứa thao tác trái phép nếu danh tính hoặc ứng dụng bị xâm phạm.

## 3. Phạm vi áp dụng: ingress, egress và east–west

| Hướng/phạm vi | Ý nghĩa | Ví dụ chính sách |
|---|---|---|
| **Ingress** | Lưu lượng đi vào hệ thống, vùng mạng hoặc workload | Chỉ reverse proxy được tiếp nhận TCP/443 từ Internet |
| **Egress** | Lưu lượng do workload/vùng khởi tạo đi ra | API chỉ kết nối đến database, resolver và dịch vụ đã duyệt |
| **North–south** | Giữa nội bộ và môi trường bên ngoài | VPN hoặc firewall biên giới hạn điểm vào từ Internet |
| **East–west** | Giữa các subnet, máy chủ hoặc workload nội bộ | Frontend chỉ có thể kết nối đến API, không kết nối DB |
| **Management plane** | Luồng điều khiển/quản trị hạ tầng | Chỉ bastion được phê duyệt truy cập SSH/HTTPS quản trị |
| **Wireless/guest** | Từ mạng khách/BYOD/IoT đến tài nguyên nội bộ | Guest chỉ được ra Internet qua dịch vụ đã duyệt |

**Điểm thực thi quyết định hiệu quả chính sách.** Nếu hai máy cùng subnet trao đổi trực tiếp mà không đi qua firewall trung tâm, rule deny trên firewall Internet không kiểm soát được luồng đó. Có thể cần host firewall, phân tách VLAN, distributed firewall, CNI policy hoặc giải pháp microsegmentation tại workload.

Mỗi đường đi cũng phải kiểm tra cả **IPv4 và IPv6**. Chặn cổng trên IPv4 nhưng không có chính sách IPv6 tương ứng có thể để lại một đường truy cập không mong muốn nếu tài nguyên có địa chỉ IPv6.

## 4. Xây dựng mô hình default deny từ yêu cầu nghiệp vụ

### 4.1. Ví dụ hệ thống bán hàng nhiều vùng

Giả sử một hệ thống có các vùng:

- **Public/DMZ:** cổng HTTPS của frontend.
- **Application:** API xử lý nghiệp vụ.
- **Data:** cơ sở dữ liệu đơn hàng.
- **Management:** bastion để vận hành được xác thực.
- **Shared services:** DNS, IdP, log collector, NTP và backup.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"HTTPS 443"| W["Web frontend / DMZ"]
    W -->|"TCP 8443"| A["API / App zone"]
    A -->|"TCP 5432"| D["Database / Data zone"]
    M["Bastion quản trị"] -.->|"Quản trị được duyệt"| A
    M -.->|"Quản trị được duyệt"| D
    A -.->|"DNS 53"| N["DNS resolver"]
    A -.->|"Telemetry"| L["Log collector"]
    X["Mạng guest"] -. "Default deny tới vùng nội bộ" .-> D
~~~

**Mũi tên liền** là kết nối nghiệp vụ dự kiến; mũi tên nét đứt mô tả luồng hỗ trợ hoặc luồng bị chặn. Sơ đồ không mô tả mọi chi tiết triển khai: các luồng quản trị và dịch vụ nền cần xác minh với nhóm vận hành.

### 4.2. Ma trận truy cập được phép

| Nguồn | Đích | Giao thức/port (minh họa) | Lý do | Quyết định |
|---|---|---|---|---|
| Client được phép | Frontend | TCP/443 | Truy cập ứng dụng | **ALLOW** |
| Frontend | API | TCP/8443 | Gọi API nội bộ | **ALLOW** |
| API | Database | TCP/5432 | Đọc/ghi đơn hàng | **ALLOW** |
| API/Frontend | DNS resolver được duyệt | UDP/TCP 53 | Phân giải tên | **ALLOW** |
| Workload cần giám sát | Log collector | Port theo agent thực tế | Thu thập sự kiện | **ALLOW**, sau khi xác minh |
| Bastion | API/DB theo quyền | SSH/HTTPS hoặc cổng quản trị cần thiết | Vận hành có phê duyệt | **ALLOW** có điều kiện |
| Client | Database | Bất kỳ | Không có nhu cầu trực tiếp | **DENY** |
| Frontend | Database | Bất kỳ | API chịu trách nhiệm kết nối DB | **DENY** |
| Guest/IoT | Management | Bất kỳ | Không có quyền quản trị | **DENY** |
| Nguồn không được liệt kê | Vùng data | Bất kỳ | Chưa có mục đích xác nhận | **DEFAULT DENY** |

Các port trên là **giả định học tập**, không phải cấu hình thực của mọi ứng dụng. Database có thể dùng cổng khác; log agent có thể dùng nhiều giao thức. Mọi rule allow phải có thông tin nguồn, đích, chiều truy cập, người sở hữu và cách kiểm chứng.

### 4.3. Mô hình quyết định

~~~mermaid
flowchart TD
    A["Nhận gói/kết nối"] --> B["Xác định zone, định danh, trạng thái"]
    B --> C{"Có quy tắc hợp lệ cho phép?"}
    C -- "Không" --> X["DENY / DROP; ghi log theo chính sách"]
    C -- "Có" --> D{"Điều kiện và state đều phù hợp?"}
    D -- "Có" --> E["ALLOW và giám sát"]
    D -- "Không" --> X
~~~

Sơ đồ biểu diễn **ý nghĩa** default deny, không phải thuật toán chung của mọi firewall. Một số sản phẩm áp dụng rule theo thứ tự; một số dùng tập quy tắc allow hợp nhất; một số có default rules riêng không thể thay đổi trực tiếp.

## 5. Cách xử lý rule, implicit deny và thứ tự

### 5.1. Thứ tự rule trên firewall truyền thống

Với những firewall áp dụng **first matching rule**, quy tắc rộng ở trên có thể vô hiệu hóa một quy tắc chặn ở dưới:

~~~text
# Ví dụ LOGIC, không phải syntax của một sản phẩm
1. ALLOW  source=10.20.0.0/16       destination=10.30.0.0/16       any
2. DENY   source=10.20.10.0/24     destination=10.30.40.0/24     any
3. DENY   other-new-connections
~~~

Rule 2 có thể không bao giờ áp dụng cho lưu lượng đã khớp rule 1. Muốn đảm bảo least privilege, phải thu hẹp rule allow và xác minh thứ tự thực tế.

### 5.2. Explicit deny và implicit deny

**Explicit deny** hữu ích khi cần bảo đảm chặn một nhóm kết nối cụ thể hoặc có counters/log dễ rà soát. **Implicit deny** xuất hiện khi một tập rule không cho phép kết nối và nền tảng tự chặn phần còn lại. Ở AWS security group, chẳng hạn, mô hình chủ yếu là các **rule allow** (không có explicit deny); kết nối không được cho phép sẽ bị loại bỏ theo cơ chế nhóm bảo mật. Ở AWS Network ACL có cả allow/deny theo thứ tự. Ở Kubernetes NetworkPolicy, các rule **allow** từ nhiều NetworkPolicy được **cộng gộp**, nên không dùng cùng tư duy thứ tự rule của firewall.

### 5.3. Quy tắc đánh giá một luồng

Một policy rõ ràng cần mô tả:

~~~text
source:       nhóm người dùng, subnet, workload label hoặc service identity
destination:  ứng dụng, database, host, subnet hoặc nhóm đích
direction:    ingress / egress tại điểm thực thi
protocol:     TCP / UDP / ICMP / ICMPv6 ...
port:         port đích hoặc điều kiện theo dịch vụ
identity:     VPN/thiết bị/nhóm/role khi công nghệ hỗ trợ
purpose:      nhu cầu nghiệp vụ đã được xác nhận
owner:        đội chịu trách nhiệm
evidence:     change ticket + effective rule + kết quả kiểm tra
expiry:       thời hạn rà soát, nhất là ngoại lệ tạm thời
~~~

Chỉ nhìn một địa chỉ IP không đủ để chứng minh nguồn hợp lệ trong mọi môi trường: NAT, DHCP, container và cloud workload có thể làm IP thay đổi hoặc đại diện cho nhiều tiến trình. Khi nền tảng hỗ trợ, có thể bổ sung danh tính workload hoặc nhóm tài nguyên để chính sách bám sát tài sản.

## 6. Stateful và stateless: vì sao chiều phản hồi quan trọng?

### 6.1. Stateful firewall

Firewall **stateful** có bộ theo dõi trạng thái kết nối (**connection tracking**). Khi cho phép một luồng mới, firewall có thể nhận diện gói trả lời thuộc cùng kết nối và xử lý theo trạng thái **ESTABLISHED** hoặc tương đương. Với TCP, một kết nối được client khởi tạo tới server TCP/443 thường không cần rule mở toàn bộ cổng động của client ở chiều ngược lại trên **cùng** firewall stateful.

~~~text
# Pseudocode cho một thiết bị stateful
ALLOW  tracked ESTABLISHED/RELATED traffic (nếu được thiết bị hỗ trợ)
ALLOW  NEW from api-zone to db-host TCP/5432
ALLOW  NEW from app-zone to approved-resolver UDP/TCP 53
DENY   other unauthorized NEW traffic
~~~

Phải kiểm tra **NAT, conntrack timeout, routing bất đối xứng, invalid packets** và chính sách thực tế. Nếu chiều đi qua firewall A nhưng chiều về đi qua firewall B chưa có trạng thái, luồng có thể bị chặn dù bảng rule trông đúng.

### 6.2. Stateless ACL

**Stateless ACL** xử lý từng gói độc lập mà không dựa vào trạng thái phiên đầy đủ. Để một TCP connection hoạt động, thường phải có rule cho **chiều khởi tạo tới port dịch vụ** và **chiều phản hồi từ port dịch vụ về ephemeral port của client**. Dải cổng động phải xác minh theo hệ điều hành và luồng thực tế; không mở toàn bộ các cổng tùy ý.

| Thuộc tính | Stateful | Stateless |
|---|---|---|
| Nhớ phiên | Thường có | Không theo dõi trạng thái phiên tương tự |
| Gói phản hồi | Có thể được cho phép nhờ trạng thái | Cần policy chiều về phù hợp |
| Ví dụ nền tảng | Nhiều firewall, host firewall, AWS security group | Một số router ACL, AWS Network ACL |
| Rủi ro cấu hình | NAT/đường bất đối xứng, hết hạn state | Thiếu rule chiều về, dải ephemeral quá rộng |

### 6.3. ICMP và IPv6

Không nên mặc định chặn **toàn bộ ICMP**. **ICMPv4 Fragmentation Needed** và **ICMPv6 Packet Too Big** quan trọng với Path MTU Discovery; một số loại ICMPv6 còn thiết yếu cho Neighbor Discovery và vận hành IPv6. Cần cho phép những loại thông điệp phù hợp với vai trò thiết bị, có giới hạn chống lạm dụng hợp lý.

Tương tự, **UDP** có thể được firewall stateful theo dõi theo timeout nhưng không có handshake như TCP. DNS, NTP, QUIC, VoIP và giao thức VPN cần được đánh giá riêng. Quy tắc allow TCP/443 không đồng nghĩa đã hỗ trợ HTTP/3, vì QUIC thường sử dụng **UDP/443**.

## 7. Default deny egress và kiểm soát di chuyển ngang

### 7.1. Chặn luồng ra ngoài không cần thiết

Một server chỉ có chức năng phục vụ API không nhất thiết được phép kết nối tới mọi địa chỉ Internet. Nếu kẻ tấn công lợi dụng ứng dụng đã bị chiếm quyền, đường egress quá rộng có thể cho phép liên lạc với hạ tầng bên ngoài hoặc gửi dữ liệu ra ngoài. **Egress allowlist** giới hạn những đích hoặc dịch vụ mà workload được phép gọi.

Tuy nhiên, trước khi triển khai phải thống kê phụ thuộc:

- DNS resolver được tổ chức phê duyệt (có thể cần UDP **và** TCP/53).
- NTP, dịch vụ danh tính và luồng xác thực có liên quan.
- Container registry, artifact repository và kho cập nhật bảo mật.
- Secret manager, certificate authority và các API cloud control plane cần thiết.
- Endpoint của nhà cung cấp SaaS/đối tác đã được duyệt.
- Dịch vụ giám sát, metrics, log, backup, health check và phục hồi.

Rule kiểu **allow TCP/443 tới toàn bộ Internet** thường không đạt mục tiêu least privilege cho một máy chủ chỉ cần một tập đích nhỏ. Tuy vậy, lọc theo tên miền (FQDN) có giới hạn do CDN, IP thay đổi, DNS cache, DoH/DoT và khả năng xác minh đích của thiết bị; có thể cần egress proxy hoặc cơ chế kiểm soát danh tính dịch vụ.

### 7.2. East–west và microsegmentation

Trong mạng phẳng, hai máy nội bộ có thể kết nối với nhau dù không có lý do nghiệp vụ. **Microsegmentation** giới hạn kết nối giữa các nhóm workload: ví dụ web chỉ gọi API, API chỉ gọi database, worker chỉ gọi hàng đợi. Quy tắc thường dựa vào tag, label, service identity hoặc security group, giúp tránh phụ thuộc hoàn toàn vào IP thay đổi.

Nếu cùng một dịch vụ có nhiều đường đi (load balancer, direct IP, service mesh, overlay), phải xác định điểm thực thi có chặn được **tất cả đường không được phép** không. Một rule trên gateway sẽ không giúp khi gói tin đi vòng qua gateway.

### 7.3. DNS, VPN, Wi-Fi và cloud

**DNS**: mất egress tới resolver có thể làm tất cả ứng dụng không tìm được dịch vụ, dù policy TCP chính xác.  
**VPN**: đăng nhập VPN thành công không nên đồng nghĩa được truy cập tất cả subnet nội bộ.  
**Wi-Fi**: guest/BYOD cần phân đoạn và chính sách truy cập khác mạng quản trị.  
**Cloud**: kiểm tra đồng thời security group, subnet ACL, route table, private endpoint, NAT và policy ở workload.  
**IDS/IPS**: lưu lượng bị deny cần được ghi nhận hợp lý; IDS/IPS giúp phát hiện và điều tra, nhưng không phải lúc nào cũng thay thế được rule allow/deny.

## 8. Các cơ chế phổ biến triển khai default deny

| Nền tảng | Cách biểu diễn thường gặp | Điều phải kiểm tra |
|---|---|---|
| Firewall truyền thống | Default policy deny/drop hoặc rule từ chối cuối | Thứ tự rule, zone, NAT và state |
| Linux nftables/iptables | Policy DROP ở chain/hook phù hợp, thêm allow rules | Loopback, gói đã thiết lập, IPv6, kênh quản trị |
| AWS Security Group | Chỉ định các rule allow; traffic không được phép bị chặn | Stateful; inbound và outbound; tất cả SG gắn resource |
| AWS Network ACL | Allow/deny theo thứ tự; implicit deny cuối | Stateless; cả hai chiều và ephemeral ports |
| Azure Network Security Group | Rule allow/deny theo priority, có default rules | Effective rules, ưu tiên, chiều, trạng thái |
| Kubernetes NetworkPolicy | Cô lập pod bằng policy chọn pod/chiều; khai báo allow | CNI có thực thi không, nhãn, namespace, tính cộng gộp |
| ZTNA/identity-aware proxy | Chỉ cấp quyền vào tài nguyên cụ thể sau xác minh danh tính/ngữ cảnh | Chính sách người dùng, thiết bị, đường bypass |

**Bẫy thường gặp:** áp dụng tư duy rule thứ tự của firewall lên Kubernetes NetworkPolicy. Trong Kubernetes, một pod có thể được chọn bởi nhiều policy và các quyền allow của chúng được hợp lại. Không tồn tại thứ tự deny/allow tương đương một ACL có số thứ tự. Một policy tên **default-deny** không vô hiệu hóa các allow khác được tạo hợp lệ.

## 9. Ví dụ cụ thể: Kubernetes NetworkPolicy

Giả sử namespace **orders** chứa các pod nhãn **app: frontend** và **app: api**. NetworkPolicy chỉ được thực thi nếu plugin mạng **CNI** hỗ trợ NetworkPolicy. Việc tạo thành công tài nguyên bằng Kubernetes API không đủ chứng minh lưu lượng đã bị chặn.

### 9.1. Cô lập mặc định cả ingress lẫn egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

**podSelector rỗng** chọn tất cả pod trong namespace **orders**. Policy không có rule allow ingress/egress nên cô lập pod đã chọn theo **cả hai chiều**. Nó không tự áp dụng cho pod trong namespace khác. Bật ngay trên production có thể cắt DNS, truy cập service và luồng giám sát nếu chưa khai báo ngoại lệ.

### 9.2. Cho frontend gọi API

Ở chiều **ingress của API**, cho phép frontend đến TCP/8443:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-ingress-from-frontend
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8443
~~~

Vì frontend cũng bị default-deny **egress**, cần mở chiều đi từ frontend tới API:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-egress-to-api
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: frontend
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: api
      ports:
        - protocol: TCP
          port: 8443
~~~

Khi cả hai phía bị cô lập, **egress của nguồn** và **ingress của đích** phải đồng thời được cho phép theo chính sách hiệu lực. Các policy allow khác trong namespace cũng có thể cộng thêm quyền.

### 9.3. Ngoại lệ DNS

Ví dụ sau giả định namespace hệ thống có nhãn **kubernetes.io/metadata.name: kube-system** và pod resolver có nhãn **k8s-app: kube-dns**. Cần **xác minh nhãn thực** trong cluster trước khi dùng, vì CoreDNS/NodeLocal DNSCache và CNI của từng môi trường có thể khác nhau.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-approved-dns
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

Lưu ý: đặt **namespaceSelector và podSelector trong cùng một mục** nghĩa là chọn pod đúng nhãn **trong namespace** được chỉ định. Đặt thành hai mục riêng sẽ mở quyền tới một hợp nhiều tập đích, có thể rộng ngoài ý muốn. Tùy hạ tầng, truy cập ClusterIP, dịch vụ NodeLocal DNSCache hoặc policy ở namespace đích còn có thể cần xử lý riêng.

### 9.4. Xem policy và kiểm chứng dataplane

~~~bash
# Chỉ đọc cấu hình namespace và workload
kubectl get networkpolicy -n orders
kubectl get pods -n orders --show-labels
kubectl describe networkpolicy default-deny-all -n orders

# Xác minh nhãn namespace và DNS resolver
kubectl get namespace kube-system --show-labels
kubectl get pods -n kube-system --show-labels
~~~

Sau đó kiểm tra từ một nguồn hợp lệ và nguồn phải bị chặn, đối chiếu với log/counters của CNI. Lệnh xem tài nguyên không thể chứng minh policy đã được thực thi ở tầng truyền gói. Cần cân nhắc service mesh, kube-proxy/eBPF, NAT và đường qua load balancer khi diễn giải kết quả.

## 10. Ví dụ pseudocode trên firewall stateful

~~~text
# PSEUDOCODE: minh họa mục tiêu, không phải cấu hình của sản phẩm cụ thể

1  ALLOW  tracked ESTABLISHED/RELATED traffic, where supported
2  ALLOW  frontend-zone -> api-service          TCP/8443    NEW
3  ALLOW  api-zone      -> database             TCP/5432    NEW
4  ALLOW  app-zones     -> approved-dns          UDP/TCP 53
5  ALLOW  bastion       -> approved-mgmt-hosts  approved-mgmt-ports
6  ALLOW  required ICMP/ICMPv6 types under approved policy
99 DENY   all remaining unauthorized traffic; log at controlled rate
~~~

Thực tế phải xét hướng rule, security zone, chain/hook, vị trí NAT, trạng thái phiên, routing và traffic tới chính firewall. Không được áp dụng pseudocode trực tiếp vì có thể làm mất quyền quản trị hoặc chặn các giao thức điều khiển cần thiết.

Các kết nối hạ tầng ít được chú ý cũng phải được xác định: **DHCP, ARP, IPv6 Neighbor Discovery, routing protocols, health checks, dịch vụ phát hiện service, NTP, PKI, IdP, hệ thống backup và giám sát**. Một số gói hoạt động ở tầng liên kết hoặc control plane nên không nằm trong cùng quy tắc xử lý với TCP/UDP ứng dụng.

## 11. Quy trình đưa default deny vào hệ thống đang chạy

### Bước 1 — Xác định phạm vi và người sở hữu

Khoanh vùng tài sản cần bảo vệ, luồng nghiệp vụ, ranh giới tin cậy và nơi đặt policy. Xác định nhóm chịu trách nhiệm, vùng production/staging, yêu cầu sẵn sàng và kênh khôi phục quản trị trong trường hợp cấu hình sai.

### Bước 2 — Thu thập luồng đang sử dụng

Đối chiếu flow logs, firewall logs, VPC flow logs, Kubernetes/CNI telemetry, inventory, tài liệu ứng dụng, cấu hình DNS và phân quyền truy cập. Dữ liệu quan sát giúp đề xuất allow rule nhưng **không có nghĩa mọi luồng hiện có đều hợp lệ**: có thể có kết nối dư thừa hoặc sai cấu hình.

### Bước 3 — Lập ma trận và duyệt ngoại lệ

Với mỗi luồng, ghi **source, destination, protocol, port, direction, mục đích, chủ sở hữu, môi trường, thời hạn và bằng chứng**. Xác định các phụ thuộc như DNS/NTP/IdP, monitoring, artifact registry, backup, health check và quyền quản trị.

### Bước 4 — Mô phỏng hoặc thử trên phạm vi hẹp

Nếu nền tảng có **policy simulator, shadow rule hoặc monitor-only**, dùng khả năng đó để đánh giá tác động. Nếu không, thử trong lab hoặc nhóm workload không trọng yếu. Kiểm tra **cả allow lẫn deny**: kết nối hợp lệ phải hoạt động, kết nối không hợp lệ phải bị chặn.

### Bước 5 — Triển khai có đường khôi phục

Thực hiện theo từng vùng/workload, theo dõi chỉ số ứng dụng và log firewall. Đảm bảo kênh quản trị phù hợp, phương án rollback và người phụ trách thay đổi. Đặc biệt chú ý khi sửa firewall từ xa, đường VPN hoặc security group gắn với chính máy đang dùng để quản trị.

### Bước 6 — Xác minh và bảo trì

Kiểm tra API, database, DNS, đăng nhập, TLS, health checks, tác vụ nền, telemetry và backup. Đánh giá deny logs theo source/destination/port, phát hiện các rule mở rộng bất thường, ghi lại lý do và thời điểm hết hạn của ngoại lệ. Mỗi lần thay đổi hệ thống, cloud, dịch vụ hoặc đối tác cần rà soát lại ma trận.

~~~mermaid
flowchart TD
    A["Inventory và luồng dữ liệu"] --> B["Ma trận allow có chủ sở hữu"]
    B --> C["Thử nghiệm/simulate"]
    C --> D{"Luồng hợp lệ hoạt động?"}
    D -- "Chưa" --> E["Xác minh phụ thuộc, sửa policy"]
    E --> C
    D -- "Có" --> F["Áp dụng phạm vi nhỏ"]
    F --> G["Thử cả allow và deny, theo dõi lỗi"]
    G --> H{"Có sự cố ngoài dự kiến?"}
    H -- "Có" --> I["Rollback / khôi phục theo kế hoạch"]
    I --> B
    H -- "Không" --> J["Vận hành, audit và rà soát"]
~~~

## 12. Chẩn đoán lưu lượng bị chặn

### 12.1. Nhận diện các nhóm nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| API không kết nối DB | Thiếu egress của API, ingress DB, sai port hoặc route | So sánh ma trận với effective policy cả hai phía |
| DNS lỗi sau khi bật deny egress | Chưa cho phép resolver/UDP–TCP 53 | Kiểm tra resolver thực, log deny và truy vấn DNS được phép |
| Chỉ IPv6 không hoạt động | Thiếu policy IPv6, routing hoặc ICMPv6 | Xem AAAA, luật IPv6, Packet Too Big và đường đi |
| TCP kết nối nhưng ứng dụng vẫn từ chối | TLS, xác thực, RBAC hoặc logic ứng dụng | Xem log ứng dụng, TLS, định danh service |
| Cloud subnet ACL làm kết nối ngắt | Thiếu rule chiều phản hồi trên ACL stateless | Kiểm tra ephemeral ports và policy chiều về |
| NetworkPolicy tồn tại nhưng vẫn truy cập được | CNI không thực thi, selector sai hoặc allow khác đang áp dụng | Kiểm tra CNI, nhãn và kết nối thử từ nguồn bị cấm |
| Chỉ lỗi khi đi qua VPN | Source IP/route khác, DNS split view, firewall zone khác | Ghi source IP thực, vị trí NAT, thiết bị xử lý |
| Lỗi thất thường | Conntrack timeout, IP động, load balancer, health check | Xem flow logs, session counters và lịch thay đổi |

Đừng quy mọi **timeout** cho firewall. Một timeout có thể do dịch vụ không lắng nghe, lỗi định tuyến, MTU/fragmentation, DNS hoặc rate limit. Bằng chứng mạnh nhất là log drop/deny ở đúng điểm thực thi, có thời điểm trùng với luồng bị lỗi.

### 12.2. Ghi lại một luồng cụ thể bằng 5-tuple

**5-tuple** của một kết nối IP thông thường gồm source IP, source port, destination IP, destination port và protocol. Khi điều tra, bổ sung **timestamp, vị trí bắt gói, NAT, state, rule ID, security group, hướng/zone, workload identity**.

~~~text
Ví dụ điều tra giả định:
Source IP:    10.20.10.21
Source port:  51734
Destination:  10.20.30.15
Dest port:    5432
Protocol:     TCP
Time (UTC):   2026-11-28T03:00:00Z
Observed:     DENY at internal firewall

Cần kiểm tra:
- IP nguồn có đúng API không? NAT có làm đổi IP?
- Rule egress API và ingress DB có đủ không?
- Firewall có thấy được kết nối NEW và state chiều về?
- Port 5432 có thật sự mở trên máy DB không?
- Cấu hình và log nào cho biết chính xác rule đã từ chối?
~~~

### 12.3. Công cụ quan sát

~~~bash
# Linux: đường đi theo routing table đến DB
ip route get 10.20.30.15

# Xem TCP listeners trên host được phép quản trị
ss -lntp

# Xem kết nối liên quan tới port 5432
ss -tn '( dport = :5432 or sport = :5432 )'

# Quan sát gói có liên quan khi được phép bắt lưu lượng
sudo tcpdump -ni any 'host 10.20.30.15 and tcp port 5432'

# Xem cấu hình nftables trên hệ thống có dùng nftables
sudo nft list ruleset
~~~

Những lệnh trên chủ yếu phục vụ quan sát. Bắt gói tại host nguồn không chứng minh được vị trí bị drop trên firewall trung gian. Cần kết hợp log của điểm thực thi và điều tra ở tầng ứng dụng.

## 13. Sai lầm thường gặp

| Nhận định sai | Giải thích chính xác |
|---|---|
| “Có firewall Internet là đủ.” | East–west nội bộ có thể không đi qua firewall Internet. |
| “Cứ đặt deny all cuối là an toàn.” | Rule allow quá rộng phía trước có thể đã cho phép lưu lượng. |
| “Default deny nghĩa là tắt mọi kết nối.” | Phải có allowlist cho nghiệp vụ và phụ thuộc kỹ thuật hợp lệ. |
| “Stateful và stateless cấu hình giống nhau.” | Stateless thường cần policy phản hồi riêng. |
| “Chặn toàn bộ ICMP tốt cho bảo mật.” | Có thể làm hỏng PMTUD và các cơ chế IPv6 thiết yếu. |
| “Chỉ cần kiểm tra IPv4.” | IPv6 có thể tạo đường vào/ra chưa được kiểm soát. |
| “Có Kubernetes NetworkPolicy là chắc chắn cô lập.” | Cần CNI hỗ trợ, selector đúng, xem quyền allow cộng gộp và thử dataplane. |
| “Cho TCP/443 ra mọi đích là least privilege.” | Cần xét giới hạn theo đích, tài nguyên, danh tính và chức năng. |
| “Kết nối hợp lệ về mạng thì an toàn.” | Tầng ứng dụng vẫn cần authentication, authorization và giám sát. |
| “Mọi traffic hiện có đều phải được allow.” | Phải xác nhận nhu cầu trước khi hợp thức hóa một kết nối. |

## 14. Bài tập vận dụng

### Bài 1 — Lập ma trận truy cập

Một frontend phục vụ người dùng qua HTTPS/443, gọi API qua TCP/8443; API gọi database TCP/5432. Hãy xác định ba luồng cần cho phép và ba luồng cần chặn.

**Gợi ý:** allow client → frontend:443, frontend → API:8443, API → database:5432. Deny client → database, frontend → database, guest → management. Bổ sung DNS/identity/logging sau khi xác nhận kiến trúc.

### Bài 2 — Stateful và stateless

Firewall stateful cho phép kết nối TCP từ client tới server port 443. Có cần mở toàn bộ ephemeral ports từ server về client không? Câu trả lời thay đổi ra sao với subnet ACL stateless?

**Gợi ý:** thiết bị stateful thường xử lý phản hồi dựa trên trạng thái đã ghi nhận. ACL stateless cần policy chiều phản hồi phù hợp. Phải xét NAT, routing, dải cổng và cơ chế thiết bị.

### Bài 3 — Cô lập Kubernetes

Sau khi bật default-deny-all trong namespace, frontend không phân giải được DNS. Hãy nêu ba giả thuyết kiểm tra.

**Gợi ý:** thiếu egress UDP/TCP 53, selector DNS không khớp, resolver thực tế là NodeLocal DNSCache hoặc cách CNI xử lý ClusterIP khác giả định. Đối chiếu resolver, CNI, label và log luồng.

### Bài 4 — Vì sao default deny không đủ?

Chính sách chỉ cho API truy cập database TCP/5432, nhưng tài khoản database của API có quyền đọc mọi bản ghi. Nếu API bị chiếm quyền, dữ liệu có thể vẫn bị lộ không?

**Gợi ý:** có. Default deny chặn đường mạng ngoài phạm vi, nhưng không giới hạn hành động của danh tính được phép. Cần quyền tối thiểu, quản lý secrets, audit, giới hạn truy vấn và giám sát dữ liệu.

### Bài 5 — Chẩn đoán luồng bị chặn

API **10.20.10.21** không kết nối được DB **10.20.30.15:5432** qua cloud network có security group và subnet ACL. Bạn cần tìm những bằng chứng nào?

**Gợi ý:** 5-tuple trước/sau NAT, timestamp, route, effective SG cả nguồn và đích, ACL hai chiều, trạng thái/port DB, flow log và rule deny cụ thể. Không khẳng định nguyên nhân chỉ dựa trên thông báo timeout.

### Bài 6 — Chuyển đổi chính sách egress

Đội hạ tầng đang dùng allow-all egress và muốn chuyển sang default deny. Đề xuất quy trình có thể giảm gián đoạn.

**Gợi ý:** inventory → thu thập flow logs → xác nhận phụ thuộc với chủ sở hữu → xây ma trận allow → thử nhóm nhỏ → triển khai có rollback → kiểm tra cả kết nối hợp lệ và bị cấm → theo dõi telemetry và rà soát ngoại lệ.

## 15. Kết luận và ghi nhớ

**Default deny là điểm xuất phát của kiểm soát truy cập mạng có chủ đích**: chỉ cho kết nối cần thiết đi qua, từ chối đường không có lý do nghiệp vụ. Hiệu quả phụ thuộc vào việc hiểu tài sản, luồng dữ liệu, trạng thái kết nối, đường đi và các ngoại lệ kỹ thuật. Chính sách an toàn phải bao phủ ingress, egress, east–west, quản trị, IPv4/IPv6 và đặc thù nền tảng.

Khi kết hợp với **phân đoạn mạng, VPN, xác thực kết nối, bảo vệ DNS, quản trị cloud, IDS/IPS và phân quyền tầng ứng dụng**, default deny giúp giảm phạm vi tác động khi một máy chủ hoặc tài khoản bị xâm phạm. Thước đo triển khai là **luồng hợp lệ vẫn chạy, luồng ngoài phạm vi bị chặn và mọi ngoại lệ đều có chủ sở hữu, lý do, bằng chứng cùng thời điểm rà soát**.

### Tài liệu tham khảo

- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): xây dựng và quản trị firewall policy.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): kiểm soát theo tài nguyên và danh tính.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): danh mục kiểm soát liên quan đến truy cập, bảo vệ truyền thông và giám sát.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): ngữ nghĩa cô lập pod, ingress/egress và cộng gộp quyền.
- [AWS — Security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html): mô hình allow và xử lý stateful.
- [AWS — Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html): quy tắc có thứ tự, stateless, allow/deny.
- [Microsoft Learn — Network security groups](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview): priority, default rules và effective policy.
