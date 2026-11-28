# Microsegmentation: phân đoạn đến từng workload và luồng giao tiếp

**Microsegmentation (vi phân đoạn mạng)** là cách chia môi trường công nghệ thông tin thành các miền bảo vệ nhỏ và thực thi chính sách truy cập sát với ứng dụng, máy ảo, container hoặc workload. Thay vì mặc định rằng mọi máy trong một VLAN hoặc subnet có thể nói chuyện với nhau, microsegmentation giới hạn **workload nào được kết nối tới workload nào, qua giao thức/cổng nào, vì mục đích gì**. Mục tiêu là giảm phạm vi di chuyển ngang (*lateral movement*) của kẻ tấn công và thu hẹp tác động nếu một điểm bị xâm nhập.

Trong chương **Segmentation** của module **SECURITY_NETWORK_SECURITY**, microsegmentation là một lớp phòng vệ bổ trợ cho phân đoạn mạng truyền thống, firewall, VPN, NAC/xác thực kết nối, IDS/IPS, bảo vệ DNS, mạng không dây và hạ tầng cloud. Kiến trúc mạng an toàn cần đồng thời xem xét ranh giới mạng, danh tính workload, dữ liệu đang truyền, khả năng quan sát lưu lượng và kiểm soát ở tầng ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt phân đoạn mạng truyền thống với microsegmentation và giải thích tác động tới **north–south** và **east–west traffic**.
2. Xác định tài sản, trust boundary, quan hệ phụ thuộc giữa dịch vụ và điểm thực thi chính sách.
3. Thiết kế chính sách mặc định từ chối (*default deny*) với các ngoại lệ theo nguồn, đích, danh tính, giao thức và cổng.
4. So sánh thực thi ở firewall, host, hypervisor, cloud security group, Kubernetes CNI/NetworkPolicy và service mesh.
5. Đọc ví dụ Kubernetes NetworkPolicy và nhận biết các giới hạn khi áp dụng vào môi trường thực tế.
6. Lập kế hoạch triển khai theo giai đoạn, kiểm tra luồng hợp lệ/bị chặn, giám sát và xử lý sự cố.

## 2. Vì sao cần microsegmentation?

### 2.1. Hạn chế của việc chỉ chia VLAN/subnet

Giả sử doanh nghiệp đặt 100 máy chủ ứng dụng trong mạng 10.30.0.0/24, tách khỏi mạng người dùng bằng firewall. Quy tắc tại firewall chỉ cho phép người dùng truy cập một số cổng. Điều đó bảo vệ **ranh giới giữa các mạng** nhưng chưa chắc kiểm soát được lưu lượng **giữa hai máy chủ trong cùng subnet**: gói tin của hai máy trong cùng miền L2 có thể đi trực tiếp qua switch ảo hoặc switch vật lý mà không qua firewall liên VLAN.

Nếu một máy ứng dụng bị chiếm quyền, kẻ tấn công có thể thử tiếp cận các máy còn lại nếu chúng lắng nghe và không có kiểm soát ngang bổ sung. Microsegmentation đặt chính sách tại các điểm có thể chặn luồng này, ví dụ host firewall, lớp mạng ảo, CNI hoặc thiết bị phân đoạn phù hợp.

### 2.2. North–south và east–west

| Loại lưu lượng | Hướng điển hình | Nguy cơ nổi bật | Kiểm soát phù hợp |
| --- | --- | --- | --- |
| **North–south** | Thiết bị/người dùng bên ngoài ↔ ứng dụng tại edge | Tấn công từ Internet, truy cập trái phép từ mạng khách | Edge firewall, WAF, VPN/ZTNA, NAC, xác thực ứng dụng |
| **East–west** | Workload ↔ workload trong nội bộ, giữa pod, VM, dịch vụ hoặc vùng cloud | Di chuyển ngang, lạm dụng quyền, truy cập dữ liệu giữa dịch vụ | Microsegmentation, policy tại host/CNI, identity workload, firewall nội bộ, mTLS |

Hai hướng chỉ là mô hình để phân tích, không phải phân loại giao thức bắt buộc. Một dịch vụ nội bộ gọi API của bên thứ ba là lưu lượng đi ra khỏi ranh giới tổ chức, còn hai pod trên cùng node vẫn có thể là hai miền bảo mật riêng nếu chính sách yêu cầu.

### 2.3. So sánh segmentation và microsegmentation

| Khía cạnh | Segmentation truyền thống | Microsegmentation |
| --- | --- | --- |
| Đơn vị phân tách thường gặp | VLAN, subnet, zone, VPC/VNet | VM, pod, ứng dụng, process/workload hoặc nhóm nhỏ có cùng quyền |
| Quy tắc truy cập | Các luồng giữa vùng mạng | Các quan hệ cụ thể giữa workload và dịch vụ |
| Điểm thực thi | Router, firewall, gateway | Host firewall, hypervisor/vSwitch, CNI, cloud policy, distributed firewall, gateway |
| Cách định danh | Chủ yếu địa chỉ IP/subnet/zone | Có thể thêm label, tag, nhóm bảo mật, service identity và thuộc tính workload |
| Thay đổi khi workload di chuyển | Dễ cần sửa rule nếu lệ thuộc IP | Có thể đi theo danh tính/nhãn nếu hệ thống hỗ trợ đúng |
| Trọng tâm | Giảm tiếp xúc giữa các vùng lớn | Thu hẹp đường di chuyển ngang và blast radius của từng workload |

**Microsegmentation không thay thế segmentation:** chia vùng lớn giúp đơn giản hóa kiến trúc, định tuyến và phân tách mạng khách/quản trị; microsegmentation áp chính sách chi tiết trong và giữa các vùng đó.

## 3. Nguyên tắc cốt lõi

### 3.1. Default deny và least privilege

Nguyên tắc thiết kế là **chặn mọi kết nối khởi tạo không được cho phép tường minh**, rồi mở đúng những luồng phục vụ nghiệp vụ. Ví dụ, Web API được phép gọi Orders API trên TCP/8443, nhưng không được truy cập trực tiếp database hoặc cổng quản trị của Orders API.

Một quy tắc nên mô tả tối thiểu:

- **Nguồn**: workload, nhóm service hoặc identity nào cần kết nối.
- **Đích**: đúng service/pod/VM, nhóm ứng dụng hoặc endpoint cần bảo vệ.
- **Giao thức và cổng**: TCP, UDP, ICMP/ICMPv6; port đích trong trường hợp TCP/UDP.
- **Hướng**: ingress/egress theo điểm thực thi; xác định bên khởi tạo.
- **Hành động**: allow/deny theo ngữ nghĩa của hệ thống chính sách.
- **Mục đích, chủ sở hữu và thời hạn**: căn cứ nghiệp vụ để review, hết hạn ngoại lệ.
- **Kiểm chứng**: phép thử cho luồng hợp lệ và luồng phải bị chặn.

Không được dùng quy tắc rộng kiểu “allow any trong VPC” làm mặc định chỉ vì hai workload cùng thuộc môi trường sản xuất.

### 3.2. Identity và vị trí triển khai

Với hệ thống truyền thống, quy tắc thường gắn với IP như 10.30.20.12/32. Khi container tự động scale hoặc VM đổi địa chỉ, IP có thể không còn là định danh ổn định. Chính sách theo **label, tag, nhóm bảo mật, namespace, service account hay danh tính workload** có thể ổn định hơn.

Tuy nhiên, **nhãn không tự chứng minh danh tính**. Nếu tài khoản có thể sửa label để tự đưa workload vào nhóm đáng tin, chính sách dựa trên label có thể bị lợi dụng. Phải bảo vệ quyền sửa metadata bằng RBAC/IAM/admission policy và quản lý vòng đời danh tính.

### 3.3. Chặn kết nối không đồng nghĩa bảo vệ dữ liệu đầy đủ

Microsegmentation chủ yếu quản lý **đường kết nối**. Nếu một API được phép nhận TCP/443 nhưng có lỗi phân quyền cho phép người dùng đọc đơn hàng của người khác, microsegmentation không sửa lỗi đó. Cần TLS/mTLS để bảo vệ và xác thực các kết nối phù hợp, IAM và authorization ở ứng dụng để kiểm soát hành động, cùng giám sát để phát hiện hành vi bất thường.

## 4. Mô hình hóa luồng dữ liệu và ranh giới tin cậy

Xét hệ thống bán hàng giả định có gateway, Web API, Orders API, Payments API và database:

~~~mermaid
flowchart LR
    U["Người dùng"] -->|HTTPS 443| G["API Gateway"]
    G -->|HTTPS 8443| W["Web API"]
    W -->|HTTPS 8443| O["Orders API"]
    O -->|TCP 5432| D[("Orders DB")]
    O -->|HTTPS 8443| P["Payments API"]
    W -->|DNS theo chính sách| R["DNS Resolver"]
    O -->|DNS theo chính sách| R
    P -->|DNS theo chính sách| R
    subgraph Edge["Vùng edge"]
      G
    end
    subgraph App["Vùng ứng dụng"]
      W
      O
      P
    end
    subgraph Data["Vùng dữ liệu"]
      D
    end
    subgraph Platform["Dịch vụ nền tảng"]
      R
    end
~~~

Các mũi tên cho thấy **luồng khởi tạo kết nối mong muốn**, không phải minh chứng rằng những luồng khác đã bị chặn. Sơ đồ cũng không tự thể hiện mọi luồng thực tế như log, metrics, kiểm tra sức khỏe, đồng bộ thời gian và cập nhật hệ thống; các luồng đó phải được kiểm kê trước khi áp default deny.

### 4.1. Ma trận cho phép và từ chối

| ID | Nguồn | Đích | Giao thức/cổng đích | Mong muốn | Căn cứ |
| --- | --- | --- | --- | --- | --- |
| F01 | Người dùng qua edge | API Gateway | TCP/443 | ALLOW | Điểm vào web |
| F02 | API Gateway | Web API | TCP/8443 | ALLOW | Chuyển tiếp yêu cầu hợp lệ |
| F03 | Web API | Orders API | TCP/8443 | ALLOW | Truy vấn, tạo đơn hàng |
| F04 | Orders API | Orders DB | TCP/5432 | ALLOW | Đọc/ghi đơn hàng bằng tài khoản DB giới hạn quyền |
| F05 | Orders API | Payments API | TCP/8443 | ALLOW | Xử lý thanh toán qua API đã xác thực |
| F06 | Workload được cấp quyền | DNS Resolver | UDP/TCP 53 | ALLOW | Phân giải tên miền nếu dùng DNS truyền thống |
| F07 | Web API | Orders DB | Bất kỳ | DENY | Không được bỏ qua lớp Orders API |
| F08 | Payments API | Orders DB | Bất kỳ | DENY | Không có nhu cầu truy cập DB đơn hàng |
| F09 | Mạng người dùng | Cổng quản trị workload | TCP/22, TCP/3389 | DENY | Không quản trị trực tiếp từ client |
| F10 | Workload không được cấp quyền | Dịch vụ khác | Bất kỳ | DENY mặc định | Chống di chuyển ngang |

Các cổng là **giả định lab**. Trong hệ thống thật, cùng một dịch vụ có thể có cổng khác, DNS qua DoT/DoH hoặc endpoint cloud đặc biệt. Bảng trên cần chuyển thành **chính sách cho từng điểm thực thi**, xét ingress và egress, đồng thời có phép thử cho các hành vi bị từ chối.

### 4.2. Tư duy theo STRIDE và rủi ro còn lại

Nếu Web API bị xâm nhập, chính sách F07 giúp ngăn nó mở kết nối trực tiếp đến Orders DB tại điểm thực thi đang bảo vệ DB. Tuy vậy, Web API vẫn được phép gọi Orders API theo F03; nếu Orders API tin mọi request từ Web API và không kiểm tra danh tính/quyền nghiệp vụ, đường gián tiếp đó vẫn có thể bị lạm dụng.

Vì vậy, một threat record cần nêu rõ **tài sản**, **cách tiếp cận**, **đường được phép và bị chặn**, **kiểm soát khác** và **rủi ro còn lại**:

| Trường | Ví dụ |
| --- | --- |
| Tài sản | Dữ liệu đơn hàng trong Orders DB |
| Tác nhân/điều kiện | Web API bị chiếm quyền; có kết nối tới Orders API |
| Đe dọa | Di chuyển ngang đến DB hoặc lạm dụng API hợp lệ để đọc dữ liệu |
| Chính sách microsegmentation | Chỉ Orders API kết nối DB:5432; Web API → DB bị chặn |
| Kiểm soát bổ sung | Xác thực service, mTLS khi thích hợp, authorization tại Orders API, phân quyền tài khoản DB |
| Kiểm chứng | Thử từ Web API tới DB bị chặn; từ Orders API tới DB được phép; request trái quyền tới Orders API bị từ chối |
| Rủi ro còn lại | Nếu Orders API bị xâm nhập, cần kiểm soát quyền DB, audit và giám sát |

## 5. Điểm thực thi và công nghệ triển khai

### 5.1. Host firewall và distributed firewall

Trên máy vật lý/VM, host firewall có thể lọc kết nối vào và ra theo địa chỉ, cổng, interface hoặc thuộc tính khác tùy hệ điều hành. Firewall phân tán ở lớp hypervisor hay hạ tầng ảo có thể kiểm soát giao tiếp **VM tới VM ngay cả khi cùng subnet**, giúp tránh phụ thuộc vào việc lưu lượng phải đi qua thiết bị firewall trung tâm.

Những kiểm soát đó cần được quản lý tập trung và theo dõi thay đổi. Một máy có quyền quản trị hệ điều hành cao có thể làm thay đổi rule host; giải pháp thực thi nằm ngoài guest hoặc được bảo vệ bằng quản lý endpoint có thể tăng khả năng chống sửa đổi tùy kiến trúc.

### 5.2. Cloud security group, subnet ACL và cloud-native policy

Trong cloud, cần phân biệt **chính sách theo workload/network interface** với **chính sách tại ranh giới subnet**:

| Nền tảng / cơ chế | Cách hoạt động cần chú ý | Ứng dụng microsegmentation |
| --- | --- | --- |
| AWS Security Group | Stateful; gắn với network interface/tài nguyên được hỗ trợ; các quy tắc cho phép, không có deny tường minh trong SG | Có thể tạo nhóm theo vai trò dịch vụ và chỉ cho phép traffic giữa các nhóm cần thiết |
| AWS VPC Network ACL | Stateless; gắn với subnet; rule đánh số và xét theo thứ tự, cả inbound và outbound | Phòng vệ cấp subnet; không đủ thay cho tách chính sách từng workload |
| Azure Network Security Group | Lọc lưu lượng theo subnet hoặc NIC với các quy tắc có ưu tiên và theo dõi trạng thái | Hạn chế đường kết nối; cần thiết kế rõ ưu tiên, quy tắc mặc định |
| Google Cloud VPC firewall | Các loại rule theo phạm vi/tài nguyên hỗ trợ, với tiêu chí target/tag/service account; xử lý có trạng thái | Có thể thu hẹp giữa các workload dựa trên target và chính sách phù hợp |
| Kubernetes NetworkPolicy | Chọn pod/namespace, có thể khai báo ingress và egress; yêu cầu CNI hỗ trợ | Microsegmentation ở mức pod; chính sách L3/L4 chuẩn không tự hiểu đường dẫn HTTP |

Tên và phạm vi của cơ chế khác nhau: **không sao chép quy tắc của một nhà cung cấp sang nhà cung cấp khác** mà không kiểm tra thứ tự ưu tiên, default, quy tắc trả lời, NAT, ingress/egress và IPv6.

### 5.3. Container, CNI và pod policy

Trong Kubernetes, **NetworkPolicy** chuẩn sử dụng selector để xác định pod được áp dụng policy, cùng các điều kiện nguồn/đích và TCP/UDP/SCTP port. Các policy cho phép thường có ngữ nghĩa **cộng dồn**: nếu nhiều policy chọn cùng pod, tập các luồng được phép là hợp của các quy tắc cho phép, không dùng thứ tự first-match kiểu ACL router.

Một **default-deny policy** thường chọn mọi pod trong một namespace và khai báo cả Ingress lẫn Egress mà không có rule allow. Tuy nhiên, việc từ chối phụ thuộc CNI/network plugin có thực thi NetworkPolicy hay không; chỉ tạo YAML NetworkPolicy không bảo đảm các gói sẽ bị lọc trên một cụm không hỗ trợ.

Việc dùng namespace và label giúp tạo policy dễ duy trì hơn IP pod vốn thay đổi thường xuyên. Phải kiểm soát ai được sửa label, tạo pod, cấp quyền namespace và triển khai policy.

### 5.4. Service mesh và chính sách ở tầng ứng dụng

Một service mesh có thể sử dụng **mTLS** để xác thực và mã hóa lưu lượng giữa workload, đồng thời áp dụng chính sách theo danh tính dịch vụ hoặc thuộc tính request ở L7 nếu công nghệ được chọn hỗ trợ. Chẳng hạn, có thể cho phép một identity gọi một API nhưng từ chối identity khác.

**Mã hóa bằng mTLS không tự động thay thế NetworkPolicy hoặc host firewall.** Nếu các workload vẫn có thể kết nối trực tiếp qua đường không đi qua proxy, cần xác định cách ngăn bỏ qua điểm thực thi. Cả policy L3/L4 lẫn L7 đều phải kiểm thử theo đường lưu lượng thực tế, đặc biệt khi có service mesh sidecar, ambient mode, hostNetwork hoặc endpoint bên ngoài.

## 6. Ví dụ Kubernetes NetworkPolicy

Các ví dụ sau minh họa cú pháp **Kubernetes NetworkPolicy chuẩn**. Giả sử:

- Namespace **orders** chứa pod có nhãn **app: orders-api**.
- Namespace **web** chứa pod có nhãn **app: web-api**.
- Namespace **data** chứa pod có nhãn **app: orders-db**.
- Namespace có nhãn **kubernetes.io/metadata.name** đúng theo tên tương ứng, như trên các phiên bản Kubernetes hỗ trợ nhãn namespace này.
- CNI của cluster thực thi NetworkPolicy; đường mạng giữa các pod đi qua điểm thực thi phù hợp.

### 6.1. Mặc định chặn ingress và egress trong namespace orders

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Policy chọn **mọi pod trong namespace orders**, cô lập cả ingress lẫn egress nếu CNI hỗ trợ. Với pod đã bị policy cô lập, một kết nối được khởi tạo mới phải được policy tương ứng cho phép theo chiều của nó; lưu lượng phản hồi của kết nối được phép có thể được xử lý theo trạng thái bởi cơ chế mạng. Không áp dụng máy móc mô hình stateless ACL cần mở port trả lời cho mọi CNI.

### 6.2. Chỉ cho phép Web API gọi Orders API và Orders API gọi Orders DB

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-api-allow-required-flows
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: web
          podSelector:
            matchLabels:
              app: web-api
      ports:
        - protocol: TCP
          port: 8443
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: data
          podSelector:
            matchLabels:
              app: orders-db
      ports:
        - protocol: TCP
          port: 5432
~~~

Lưu ý cách viết **namespaceSelector và podSelector trong cùng một mục**: điều kiện phải đồng thời khớp pod thuộc namespace đã chọn. Nếu đặt chúng thành hai mục riêng trong danh sách, bạn có thể vô tình tạo phép **OR**, mở rộng nguồn được phép hơn dự định.

Ví dụ trên chỉ là **một phần** của ma trận: egress từ Web API cũng cần được cho phép theo policy của namespace web nếu pod nguồn bị cô lập; ingress tới Orders DB cũng cần được mở ở namespace data nếu DB đang bị policy ingress cô lập. Trường hợp cluster sử dụng DNS, telemetry hoặc dịch vụ phụ trợ, phải có các luồng tương ứng. Không dùng YAML này như cấu hình đầy đủ của hệ thống sản xuất.

### 6.3. Cho phép DNS có kiểm soát

Khi pod bị default deny ở egress, DNS có thể bị chặn và khiến ứng dụng báo lỗi phân giải tên thay vì lỗi kết nối. Một cách minh họa là mở egress tới pod DNS cụ thể trong namespace hệ thống:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
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

Đây là ví dụ cần **điều chỉnh theo thực tế**: CoreDNS có thể dùng nhãn khác, cluster có NodeLocal DNSCache hoặc DNS egress đi qua địa chỉ/đường khác; quá trình NAT, service IP và CNI cũng có thể ảnh hưởng điểm policy nhìn thấy đích. Kiểm tra manifest DNS của chính cluster, đường phân giải và tài liệu CNI trước khi áp dụng. Các truy vấn DoH/DoT hoặc kết nối qua proxy phải được mô hình riêng.

### 6.4. Những giới hạn cần biết

| Vấn đề | Giải thích |
| --- | --- |
| Chỉ có allow policy theo chuẩn | Kubernetes NetworkPolicy L3/L4 chuẩn không có rule deny ưu tiên hay log action độc lập như một số firewall |
| Tính cộng dồn | Một policy khác cho phép rộng có thể mở lại luồng đối với pod đang được chọn; cần review toàn bộ effective policy |
| CNI | Cần plugin thực thi NetworkPolicy; chức năng nâng cao như L7, logging, FQDN policy phụ thuộc sản phẩm |
| Selector/label | RBAC hoặc admission yếu có thể cho phép thay đổi label để vượt ranh giới |
| Host/network | HostNetwork, lưu lượng node, một số đường NAT hoặc datapath đặc biệt có hành vi phụ thuộc plugin |
| NetworkPolicy không giải mã payload | Cho phép TCP/8443 không có nghĩa endpoint đã kiểm tra TLS/mTLS hoặc authorization đúng |
| IPv4/IPv6 | Đảm bảo policy và bộ lọc thực thi bao phủ stack đang sử dụng; không giả định IPv4 rule cũng kiểm soát IPv6 |

Thay đổi policy nên được review như thay đổi mã nguồn: kiểm tra cấu trúc YAML, namespace, selector, cổng, các policy tương tác và đường truy cập khi có sự cố.

## 7. Quy trình triển khai microsegmentation an toàn

Áp dụng default deny đồng loạt trên môi trường chưa được kiểm kê thường làm gián đoạn DNS, API nội bộ, cơ chế giám sát hoặc đăng nhập. Một quy trình triển khai thực tế cần phân biệt **nhìn thấy lưu lượng**, **hiểu phụ thuộc**, **định nghĩa chính sách**, **thử nghiệm**, **thực thi** và **duy trì**.

### Bước 1 — Xác định tài sản, phạm vi và chủ sở hữu

Liệt kê các workload, môi trường, mức độ nhạy cảm và vai trò nghiệp vụ. Gán **owner** cho từng ứng dụng. Ghi rõ đâu là hệ thống công khai, workload xử lý dữ liệu nhạy cảm, dịch vụ nền tảng và công cụ quản trị.

Ví dụ:

| Workload | Vùng | Chủ sở hữu | Độ nhạy cảm | Phụ thuộc chính |
| --- | --- | --- | --- | --- |
| Web API | Web | Nhóm Web | Trung bình | Gateway, Orders API, DNS |
| Orders API | Ứng dụng | Nhóm đơn hàng | Cao | Orders DB, Payments API, DNS, logging |
| Orders DB | Dữ liệu | Nhóm dữ liệu | Rất cao | Orders API, backup, giám sát |
| Payments API | Ứng dụng | Nhóm thanh toán | Cao | Cổng thanh toán đối tác, DNS, secret store |
| DNS/metrics/identity | Nền tảng | Nhóm hạ tầng | Hệ thống trọng yếu | Các workload được cấp quyền |

Lưu ý: nhiều thành phần có thể cùng namespace/subnet nhưng cần **mức quyền khác nhau**. Cũng cần định nghĩa nguồn được phép dùng đường quản trị hoặc sửa policy.

### Bước 2 — Quan sát lưu lượng và xây dependency map

Thu thập luồng từ flow log, firewall log, CNI telemetry, service mesh, dữ liệu tracing hoặc giám sát được cho phép. Quan sát ít nhất các kịch bản nghiệp vụ quan trọng: đăng nhập, đọc/ghi dữ liệu, triển khai ứng dụng, tác vụ theo lịch, backup/restore, xử lý lỗi, scale-out và failover.

Mỗi bản ghi nên có đủ các trường để giải thích:

~~~text
timestamp, environment, source_workload, source_identity,
destination_workload, destination_identity, protocol, destination_port,
direction, observed_action, purpose, owner
~~~

Không sao chép payload, token hay thông tin cá nhân vào dependency map nếu không có nhu cầu. Đối với dịch vụ có địa chỉ động, ưu tiên nhận diện **service/identity** thay vì suy luận một IP quan sát được là cố định mãi mãi.

**Điều cần tránh:** xem mọi lưu lượng từng quan sát thấy là hợp lệ. Một phiên kết nối bất thường trong giai đoạn quan sát có thể là lỗi cấu hình hoặc hành vi trái phép. Mỗi luồng muốn được phép cần có căn cứ nghiệp vụ và người chịu trách nhiệm.

### Bước 3 — Phân loại và thiết kế chính sách

Phân chia lưu lượng thành:

1. **Required**: bắt buộc cho nghiệp vụ hoặc vận hành đã duyệt; tạo allow rule.
2. **Unnecessary**: không có yêu cầu hợp lệ; mục tiêu là deny.
3. **Unknown**: chưa rõ mục đích; phải điều tra với owner trước khi quyết định.
4. **Temporary**: luồng phục vụ chuyển đổi/sự cố trong thời gian giới hạn; có điều kiện, thời hạn và người phê duyệt.

Thiết kế policy dựa trên **source identity → destination identity → protocol/port**, có thể bổ sung môi trường, namespace, tag hoặc yêu cầu L7. Xác định ranh giới thực thi để lưu lượng không thể đi vòng qua policy bằng đường khác.

### Bước 4 — Đánh giá chính sách trước khi chặn thật

Nếu nền tảng có **simulation, audit-only hoặc policy recommendation**, dùng các chế độ đó để dự đoán tác động. Không mặc định Kubernetes NetworkPolicy chuẩn có chế độ dry-run cho **hành vi mạng thực tế**: việc kiểm tra object hợp lệ không chứng minh kết nối sẽ còn hoạt động sau khi policy được thực thi.

Ở môi trường thử nghiệm tương đồng, kiểm tra theo ma trận:

- Đúng luồng được phép vẫn kết nối và xử lý nghiệp vụ thành công.
- Luồng không được phép bị từ chối tại điểm dự kiến.
- DNS, telemetry, health checks, chứng chỉ, backup, job định kỳ và luồng quản trị hoạt động theo thiết kế.
- Kết nối hai chiều, phản hồi và các luồng sử dụng TCP/UDP/ICMP phù hợp.
- Pod mới, IP mới, scale-out, rolling update và failover vẫn đi theo policy.

### Bước 5 — Triển khai dần, giám sát và chuẩn bị rollback

Ưu tiên bắt đầu từ một dịch vụ hoặc nhóm workload có phụ thuộc rõ. Bật policy chi tiết, theo dõi lỗi kết nối và metric nghiệp vụ, rồi mở rộng theo từng nhóm. Chuẩn bị snapshot cấu hình, quyền truy cập quản trị ngoài băng nếu có, kế hoạch rollback và tiêu chí quay lại cấu hình trước khi áp thay đổi gây ảnh hưởng.

Rollback là **phương án khôi phục một thay đổi cụ thể**, không phải xóa toàn bộ policy lâu dài. Sau khi khôi phục, cần xác định chính xác luồng bị thiếu, thu hẹp rule bổ sung và kiểm thử lại.

### Bước 6 — Duy trì, rà soát và cập nhật

Microsegmentation là chính sách **sống**. Các sự kiện cần review gồm: tách dịch vụ, chuyển cloud, thay CNI, thêm namespace, triển khai service mesh, đổi nguồn DNS, cập nhật hệ thống quan sát, thêm API và chia sẻ workload với đối tác.

Theo dõi rule không còn được dùng, ngoại lệ hết hạn, policy quá rộng, label drift, sự chênh lệch giữa cấu hình mong muốn và cấu hình thực tế. Lưu vết thay đổi bằng Git/IaC hoặc hệ thống quản lý cấu hình tương đương.

## 8. Kiểm chứng bằng phép thử mạng và ứng dụng

Một phép thử thành công **không chỉ là ping được hoặc kết nối TCP thành công**. Cần xác minh đúng cặp nguồn–đích, giao thức/cổng, mục tiêu nghiệp vụ và ranh giới mà policy bảo vệ.

### 8.1. Bộ test case tham khảo

Với kiến trúc ở mục 4, có thể lập bộ kiểm thử:

| Test | Nguồn → Đích | Đặc tính | Kỳ vọng | Cách xác minh |
| --- | --- | --- | --- | --- |
| T01 | Gateway → Web API | TCP/8443 | ALLOW | TCP/TLS thành công, request hợp lệ được xử lý |
| T02 | Web API → Orders API | TCP/8443 | ALLOW | Truy cập endpoint được phép; không có drop ngoài dự kiến |
| T03 | Orders API → Orders DB | TCP/5432 | ALLOW | Kết nối DB với danh tính/quyền đúng |
| T04 | Web API → Orders DB | TCP/5432 | DENY | Kết nối không được thiết lập theo policy |
| T05 | Payments API → Orders DB | TCP/5432 | DENY | Không có đường kết nối trực tiếp |
| T06 | Web API → Payments API | TCP/8443 | DENY | Chỉ Orders API được gọi Payments API theo thiết kế |
| T07 | Orders API → DNS Resolver | UDP/TCP 53 | ALLOW nếu cần | Truy vấn DNS thành công qua resolver được duyệt |
| T08 | Workload → cổng quản trị của workload khác | TCP/22 | DENY | Không đi ngang sang giao diện quản trị |
| T09 | Orders API mới sau scale-out → Orders DB | TCP/5432 | ALLOW | Identity/label mới được policy nhận đúng |
| T10 | Mạng khách → Orders API | TCP/8443 | DENY | Không bỏ qua edge và ranh giới truy cập |

Để có bằng chứng, ghi **điểm xuất phát**, **đích**, **identity/pod/VM**, **thời điểm**, **kết quả thực tế**, **rule/flow log** và **người kiểm tra**. Kết quả timeout một mình chưa chứng minh policy đã chặn: có thể do sai route, không có listener, DNS hoặc lỗi TLS.

### 8.2. Công cụ quan sát trong môi trường lab

Với quyền đọc Kubernetes cluster đã được cấp, có thể kiểm tra các policy:

~~~bash
kubectl get networkpolicy -A
kubectl describe networkpolicy default-deny -n orders
kubectl describe networkpolicy orders-api-allow-required-flows -n orders
kubectl get pods -n orders --show-labels
kubectl get namespaces --show-labels
~~~

Các lệnh này chủ yếu đọc **cấu hình và label**, chưa chứng minh packet bị chặn. Để kiểm tra hiệu lực, dùng pod thử nghiệm trong môi trường được cho phép, tạo kết nối đúng giao thức tới host/port đích theo ma trận, rồi đối chiếu log CNI hoặc flow log:

~~~text
Source:       web-api ở namespace web
Destination:  orders-api ở namespace orders
Protocol:     TCP
Dest port:    8443
Expected:     ALLOW

Source:       web-api ở namespace web
Destination:  orders-db ở namespace data
Protocol:     TCP
Dest port:    5432
Expected:     DENY
~~~

Đừng dùng một pod kiểm tra có quyền đặc biệt, hostNetwork hoặc bị miễn áp policy rồi coi kết quả là đại diện cho mọi workload. Với Kubernetes, **egress của pod nguồn và ingress của pod đích đều cần được xét**, tùy policy nào đang cô lập mỗi bên.

### 8.3. Kiểm thử lớp mạng khác lớp ứng dụng

Giả sử một client kết nối TCP/8443 tới Orders API thành công. Cần tách ba câu hỏi:

1. **Network:** Bộ lọc có cho đúng nguồn gọi đúng đích không?
2. **Transport/security:** TLS có được xác minh đúng chứng chỉ, hostname/danh tính đối tác không?
3. **Application:** Request có được xác thực và phân quyền đúng đơn hàng không?

Kết nối TCP thành công không chứng minh quyền ứng dụng đúng. Ngược lại, HTTP 403 là bằng chứng request đã tới ứng dụng và được đánh giá quyền ở một lớp nào đó; không nên tự động suy ra microsegmentation bị lỗi.

## 9. Phát hiện sai cấu hình và xử lý sự cố

### 9.1. Các nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| API báo lỗi gọi dịch vụ sau khi áp default deny | Thiếu egress/ingress tới API phụ thuộc | Ma trận luồng, selector nguồn/đích, cổng thực tế |
| DNS không phân giải sau khi chặn egress | Thiếu UDP/TCP 53 hoặc DNS qua đường khác | DNS resolver, NodeLocal DNSCache, CNI, flow log |
| Pod được phép nhưng pod khác cùng app bị chặn | Nhãn khác, namespace khác hoặc policy chọn không đúng | Pod labels, namespace labels, selectors và deployment template |
| Rule hoạt động với một môi trường nhưng không hoạt động với nơi khác | CNI hoặc cloud policy khác, NAT/route khác | Effective policy, plugin, nguồn/đích tại điểm thực thi |
| Mất kết nối sau rolling update | IP thay đổi nhưng rule gắn IP tĩnh | Dùng identity/label/nhóm phù hợp, kiểm tra endpoint mới |
| Request được phép dù đã tạo default-deny | CNI không thực thi; policy allow khác; traffic không qua điểm lọc | Effective policies, datapath, hostNetwork, flow log |
| Chỉ chặn được IPv4 | IPv6 vẫn có đường kết nối | Kiểm tra dual-stack và chính sách IPv6 |
| Ứng dụng chậm hoặc bị timeout | Kết nối phụ bị chặn, state table/timeout hoặc DNS | Trace các luồng phụ, theo dõi gói đi/về và metrics |
| Log bị quá tải sau khi tăng giám sát | Flow logs quá chi tiết, thiếu retention/sampling | Thu thập đúng mức, phân quyền và lọc trường nhạy cảm |

### 9.2. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
    A["Luồng không đạt kỳ vọng"] --> B{"Đúng source/destination identity?"}
    B -- "Không" --> B1["Kiểm tra label, namespace, tag, workload"]
    B -- "Có" --> C{"Route và DNS đúng?"}
    C -- "Không" --> C1["Kiểm tra DNS, route, NAT, service endpoint"]
    C -- "Có" --> D{"Mọi điểm thực thi cho phép?"}
    D -- "Không" --> D1["Xem ingress, egress, CNI, SG, host firewall"]
    D -- "Có" --> E{"Transport/TLS hoạt động?"}
    E -- "Không" --> E1["Kiểm tra listener, chứng chỉ, kết nối trả lời"]
    E -- "Có" --> F{"Authorization và logic ứng dụng đúng?"}
    F -- "Không" --> F1["Kiểm tra identity và quyền API"]
    F -- "Có" --> G["Đối chiếu log, trace và test case"]
~~~

Luôn truy dấu theo **đường đi thực tế**. Một gói có thể đi qua cloud security group, host firewall, CNI policy và proxy; rule cho phép tại một lớp không vô hiệu hóa các lớp khác. Đối với kết nối giữa các node, cần xét overlay/underlay, NAT, các đường qua load balancer và các dịch vụ hệ thống tùy môi trường.

### 9.3. Những phép đo hữu ích

- **Luồng bị chặn đúng kỳ vọng**: thể hiện khả năng cô lập theo test case, không phải càng nhiều drop càng tốt.
- **Luồng nghiệp vụ hợp lệ thất bại**: ưu tiên xử lý vì ảnh hưởng khách hàng và vận hành.
- **Số rule quá rộng**: ví dụ allow-all trong vùng dữ liệu, cổng quản trị mở từ nhiều nguồn.
- **Rule không có owner/expiry**: rủi ro tích tụ chính sách không được rà soát.
- **Rule hoặc selector không còn được dùng**: có thể loại bỏ sau khi xác minh không có tác vụ định kỳ hoặc failover cần đến.
- **Thay đổi ngoài dự kiến**: policy bị sửa, workload được gắn nhãn khác hoặc quyền sửa policy tăng.
- **Rủi ro còn lại**: số đường trực tiếp/gián tiếp có thể tiếp cận dữ liệu nhạy cảm, kèm biện pháp bảo vệ ứng dụng.

Thống kê chỉ có ý nghĩa nếu thu thập từ đúng điểm và trong khoảng thời gian đại diện cho hoạt động hệ thống. Dữ liệu giám sát cần được bảo vệ bởi phân quyền, che thông tin nhạy cảm và thời hạn lưu phù hợp.

## 10. Ví dụ đánh giá mức giảm phạm vi di chuyển ngang

Hình dung 5 workload A, B, C, D và DB trong cùng một subnet. Trước khi phân đoạn, mọi workload có thể mở kết nối trực tiếp tới mọi workload khác nếu dịch vụ lắng nghe. Sau khi phân đoạn:

~~~mermaid
flowchart LR
    A["Gateway"] --> B["Web"]
    B --> C["Orders"]
    C --> D["Payments"]
    C --> DB[("Orders DB")]
~~~

Chính sách mong muốn chỉ giữ những **cạnh có lý do nghiệp vụ**. Nếu Web bị chiếm quyền, hệ thống lọc giúp chặn đường kết nối trực tiếp tới DB và Payments. Nhưng Web vẫn có một đường hợp lệ tới Orders, và từ Orders có các đường tới Payments/DB. Vì thế, **số cạnh mạng giảm không tự động chứng minh rằng không còn đường tấn công gián tiếp**.

Đánh giá blast radius nên xem:

1. **Reachability trực tiếp**: từ workload bị xâm nhập có thể kết nối tới service nào?
2. **Reachability qua dịch vụ trung gian**: workload trung gian có API cho phép hành động vượt quyền hay không?
3. **Danh tính và quyền truy cập**: token, service account, IAM role và tài khoản database có quyền gì?
4. **Dữ liệu/khóa có thể đọc được**: dù không kết nối DB trực tiếp, API hợp lệ có thể trả nội dung nhạy cảm?
5. **Điểm giám sát**: có phát hiện được chuỗi gọi bất thường, xuất dữ liệu hoặc thay đổi policy không?

Microsegmentation làm giảm bề mặt tiếp xúc và tăng chi phí di chuyển ngang, nhưng cần **phân quyền ở từng dịch vụ** để thu hẹp thực sự tác động của một workload đã bị xâm nhập.

## 11. Kết hợp microsegmentation với các lớp phòng vệ khác

| Lớp bảo vệ | Mục tiêu riêng | Cách phối hợp |
| --- | --- | --- |
| VLAN/VPC/subnet và firewall vùng | Tách mạng lớn, định tuyến và lọc biên | Microsegmentation giới hạn thêm luồng giữa workload cùng vùng |
| NAC/802.1X, VPN, ZTNA | Kiểm soát thiết bị/người dùng gia nhập mạng hoặc truy cập dịch vụ | Không cho phiên đã vào mạng mặc nhiên truy cập tất cả workload |
| TLS/mTLS, quản lý danh tính workload | Mã hóa, xác thực điểm cuối kết nối | Bảo vệ nội dung trên những luồng đã được network policy cho phép |
| IAM/RBAC, API authorization | Quyết định danh tính được làm gì với tài nguyên | Ngăn lạm dụng API qua cổng mạng đã mở hợp lệ |
| DNS security, policy egress | Giới hạn/quan sát truy vấn và kết nối ra ngoài | Không để workload tự liên lạc tùy ý với resolver hoặc endpoint không được duyệt |
| IDS/IPS, EDR, WAF | Phát hiện/chặn một số hành vi bất thường và khai thác | Bổ sung telemetry cho đường đi hợp lệ mà microsegmentation không thể đánh giá nội dung |
| Secrets management, logging, DLP | Giữ bí mật, phát hiện rò rỉ và bảo vệ dữ liệu | Hạn chế hậu quả nếu một dịch vụ vẫn có quyền truy cập dữ liệu |
| Cloud IAM và quản lý cấu hình | Bảo vệ quyền sửa tag/policy, log, tài nguyên cloud | Ngăn người không có quyền nới lỏng ranh giới phân đoạn |

Không nên dựa vào một công nghệ duy nhất cho mọi trường hợp. Chẳng hạn, **mTLS cung cấp danh tính peer và mã hóa**, nhưng policy mạng vẫn cần giảm kết nối không cần thiết. **NetworkPolicy cho phép kết nối TCP**, nhưng không quyết định một người dùng có được đọc hóa đơn của người khác hay không.

### 11.1. Bảo vệ điểm quản lý chính sách

Bộ điều khiển chính sách, API quản trị cloud và Kubernetes control plane là tài sản quan trọng. Nếu một tài khoản có thể sửa policy hoặc label của workload, attacker có thể nới lỏng phân đoạn. Nên:

- Giới hạn quyền sửa policy, namespace label, pod label và security group.
- Áp dụng review/change control cho thay đổi vùng dữ liệu và cổng quản trị.
- Ghi audit những lần thay đổi policy, danh tính, IAM và admission rule.
- Lưu policy phiên bản hóa để so sánh drift và phục hồi khi cần.
- Phân tách trách nhiệm giữa người yêu cầu kết nối và người duyệt mở rộng quyền theo quy trình tổ chức.

### 11.2. Mạng không dây, IoT và hệ thống kế thừa

Không phải thiết bị nào cũng hỗ trợ agent, CNI hoặc mTLS. Với **Wi-Fi khách, IoT, OT và ứng dụng kế thừa**, có thể kết hợp phân đoạn VLAN/zone với firewall nội bộ và gateway kiểm soát giao thức, giới hạn cổng quản trị và các kết nối bắt buộc. Tài sản không thể cài agent vẫn cần được đưa vào dependency map và threat model.

## 12. Các tình huống ra quyết định

### Tình huống A — Tạo default deny, đơn hàng không lưu được

Sau khi áp policy trong namespace orders, Orders API vẫn nhận request nhưng báo không truy cập được database.

**Phân tích:** kiểm tra namespace/label của Orders API và DB, rule egress của Orders API, rule ingress của DB, port TCP/5432 và đường mạng qua CNI. Nếu có DNS hoặc secret store trung gian, đối chiếu những luồng phụ đó. Đừng sửa bằng allow-all; tạo allowlist đúng từ Orders API đến Orders DB rồi xác minh lại.

### Tình huống B — Pod mới truy cập được DB dù pod cũ bị chặn

Một deployment mới được gắn nhãn app: orders-api và quyền đọc DB, trong khi chủ sở hữu dự kiến nhãn đó chỉ dùng cho workload đã được phê duyệt.

**Phân tích:** kiểm tra RBAC quyền tạo/sửa pod và labels, quy trình admission và nguồn triển khai. Nếu ai cũng có thể gắn nhãn để nhận quyền mạng, policy theo label đã mất một phần ý nghĩa an ninh. Cân nhắc danh tính được xác thực và cơ chế triển khai được kiểm soát.

### Tình huống C — Chính sách đúng ở Kubernetes nhưng VM vẫn truy cập được DB

NetworkPolicy của namespace data đã chặn nhiều pod, nhưng một máy ảo ngoài cluster vẫn kết nối trực tiếp với IP/port DB.

**Phân tích:** NetworkPolicy cho pod không tự điều khiển toàn bộ mạng ngoài cluster. Cần đánh giá cloud security group, firewall host, route, subnet policy và nơi DB thực sự chạy. Kiểm tra mọi đường tiếp cận dữ liệu, kể cả từ mạng VPN, hệ thống backup và công cụ vận hành.

### Tình huống D — Observability ngừng sau khi siết egress

Ứng dụng hoạt động bình thường nhưng metrics và tracing không còn lên hệ thống giám sát.

**Phân tích:** xác định chính xác endpoint, giao thức, cổng và danh tính collector. Chỉ bổ sung allow rule cho dịch vụ giám sát đã duyệt; kiểm tra rằng payload telemetry không chứa token hoặc dữ liệu cá nhân ngoài nhu cầu.

## 13. Bài thực hành tổng hợp

Hãy mô hình hóa một hệ thống giả định gồm **Gateway**, **Web API**, **Orders API**, **Payments API**, **Orders DB**, **DNS Resolver**, **Metrics Collector**, **bastion quản trị** và một **dịch vụ cloud bên thứ ba**.

Yêu cầu:

1. Vẽ DFD phân biệt edge, application, data, management và cloud; chỉ rõ ranh giới tin cậy, giao thức và điểm kết thúc TLS.
2. Lập ma trận ít nhất **10 luồng**, bao gồm các luồng nghiệp vụ bắt buộc, DNS/telemetry, quản trị, kết nối ra Internet và luồng phải bị chặn.
3. Viết chính sách default deny ở cấp workload/namespace và các allow rule có lý do. Nếu dùng Kubernetes, xác định **cả egress nguồn và ingress đích** khi hai bên bị cô lập.
4. Thiết kế **5 test allow và 5 test deny** với vị trí nguồn, cổng, danh tính, kết quả dự kiến và nguồn bằng chứng.
5. Mô phỏng việc Web API bị xâm nhập: nó kết nối trực tiếp được tới những đâu? Có còn đường gián tiếp qua Orders API không? Authorization của Orders API cần chặn trường hợp nào?
6. Đề xuất cách rollout cho môi trường có dữ liệu đang chạy: quan sát, kiểm thử, triển khai giới hạn, rollback và rà soát sau thay đổi.

**Tiêu chí tự đánh giá:** không có rule allow-all không có lý do; mọi đường đến database đều được đánh giá; policy có owner; DNS/metrics/backup được xét; mỗi luồng có phép thử thực tế; rủi ro còn lại của ứng dụng và tài khoản dịch vụ được ghi nhận.

## 14. Câu hỏi ôn tập

**Câu 1.** Vì sao đặt Web API và Orders DB trong hai subnet khác nhau chưa chắc đủ để bảo vệ DB?

*Gợi ý:* Nếu firewall giữa subnet cho phép một dải nguồn quá rộng, hoặc còn đường kết nối qua host/route khác, DB vẫn có thể tiếp cận được. Cần policy đúng đích và bảo vệ ở lớp dữ liệu.

**Câu 2.** Một NetworkPolicy có thể tự chặn request từ toàn bộ Internet đến dịch vụ chạy ngoài Kubernetes không?

*Gợi ý:* Không. NetworkPolicy chuẩn kiểm soát traffic pod thuộc phạm vi CNI hỗ trợ, không thay firewall biên hoặc chính sách cloud cho tài nguyên ngoài cluster.

**Câu 3.** Nếu đã có default-deny trong namespace orders, một policy allow rộng mới có thể làm tăng quyền mạng không?

*Gợi ý:* Có. Các rule NetworkPolicy được cộng dồn; cần đánh giá hiệu lực của **toàn bộ** policy chọn pod.

**Câu 4.** mTLS có đảm bảo Web API không được đọc dữ liệu đơn hàng trái phép không?

*Gợi ý:* Không. mTLS xác thực/mã hóa kết nối; Orders API vẫn cần kiểm tra quyền nghiệp vụ của từng request.

**Câu 5.** Vì sao không nên chỉ dựa trên IP pod để duy trì chính sách?

*Gợi ý:* Pod có thể đổi IP khi triển khai hoặc scale; nhóm workload bằng danh tính/label/tag phù hợp giúp policy dễ duy trì nhưng cần bảo vệ quyền sửa metadata.

**Câu 6.** Sau khi áp microsegmentation, một request đến API trả HTTP 403. Có thể kết luận CNI đang chặn kết nối không?

*Gợi ý:* Không. HTTP 403 thường cho thấy request đã tới một thành phần HTTP và bị từ chối theo chính sách quyền ở lớp đó. Cần kiểm tra đường mạng, nguồn trả lời và log ứng dụng.

## 15. Ghi nhớ

- **Microsegmentation** phân tách quyền kết nối theo workload/dịch vụ; tập trung giảm lateral movement và blast radius trong lưu lượng east–west.
- **Segmentation cấp subnet/zone** và **microsegmentation cấp workload** bổ sung cho nhau; cần xác định lưu lượng thật có đi qua điểm thực thi đã chọn không.
- **Default deny + allowlist theo nhu cầu** phải đi kèm dependency map, nhận diện workload đáng tin và review các luồng nền tảng như DNS, metrics, backup và quản trị.
- **Kubernetes NetworkPolicy** chuẩn là mô hình L3/L4 cho pod, có các rule allow cộng dồn và yêu cầu CNI hỗ trợ; không mặc định có chức năng deny ưu tiên hay phân quyền L7.
- **TLS/mTLS, IAM, authorization, IDS/IPS và log** xử lý những rủi ro mà policy mạng không giải quyết, đặc biệt là lạm dụng luồng hợp lệ.
- **Kiểm chứng allow và deny**, kiểm tra label/policy drift, rà soát ngoại lệ và chuẩn bị rollback là yêu cầu vận hành thường xuyên để phân đoạn vừa an toàn vừa không làm gián đoạn dịch vụ.
