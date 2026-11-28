# Bỏ qua IPv6 khi chỉ bảo vệ IPv4

## 1. Vì sao bảo vệ IPv4 không có nghĩa mạng đã an toàn?

Trong nhiều hệ thống, kỹ sư triển khai firewall rule, phân đoạn VLAN, VPN, giám sát IDS/IPS và kiểm thử xâm nhập chủ yếu bằng **IPv4**. Tuy nhiên, thiết bị đầu cuối, máy chủ, cloud workload, DNS, bộ định tuyến và hệ điều hành có thể **đồng thời hỗ trợ IPv6**. Nếu đường IPv6 đi qua chính sách khác, hoặc không đi qua điểm kiểm soát đã thiết kế, tổ chức có thể vô tình tạo ra một lối truy cập không được quản lý, dù các kiểm thử IPv4 đều đạt.

Đây là một sai lầm kiến trúc trong chương **Sai lầm thường gặp** của mô-đun **SECURITY_NETWORK_SECURITY**: chỉ bảo vệ một *address family* thay vì bảo vệ **toàn bộ các đường giao tiếp thực tế**. Bài học liên hệ trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, phân tích lưu lượng và cloud networking.

Ví dụ: firewall IPv4 không cho phép mạng GUEST truy cập ứng dụng nội bộ. Kỹ sư kiểm tra địa chỉ 10.20.0.10 và xác nhận TCP/8443 bị chặn. Nhưng cùng ứng dụng có một địa chỉ IPv6 và thiết bị mạng cho phép IPv6 đi qua boundary đó. Khi kiểm thử từ mạng GUEST bằng IPv6, kết nối có thể thành công. Vấn đề không phải **IPv6 tự vượt firewall**; vấn đề là firewall, route hoặc policy **cho IPv6 chưa được định nghĩa và kiểm chứng tương đương IPv4**.

**Mục tiêu sau bài học:**

- Hiểu vì sao một máy có thể dùng IPv4 và IPv6 song song, cả khi người vận hành chưa chủ động triển khai IPv6.
- Phân biệt sự hiện diện của IPv6 với khả năng thực sự tiếp cận một dịch vụ.
- Nhận diện các điểm bỏ sót IPv6: DNS AAAA, listener, ACL, VPN, cloud, Wi-Fi, container và hệ thống giám sát.
- Xây ma trận chính sách **IPv4/IPv6 theo cùng yêu cầu nghiệp vụ**; bảo vệ control plane của IPv6 mà không phá các giao thức cần thiết.
- Thực hiện kiểm tra ít tác động trên tài sản được cấp quyền, đối chiếu log và lập kế hoạch sửa cấu hình có rollback.

**Nguyên tắc:** mô hình hóa và kiểm thử quyền truy cập **theo dịch vụ, danh tính, zone, protocol và cả hai address families**; không suy từ một kết quả IPv4 rằng luồng IPv6 đã được kiểm soát.

## 2. Những khác biệt của IPv6 dễ dẫn tới sai quyết định

IPv4 thường được biểu diễn bằng địa chỉ 32 bit, ví dụ **192.0.2.10**; IPv6 sử dụng địa chỉ 128 bit, ví dụ **2001:db8:10:20::10**. Hai ví dụ thuộc các dải dành cho tài liệu. IPv6 không phải định dạng ghi khác của IPv4: hệ điều hành có thể có **bảng địa chỉ, route, neighbor discovery và rule lọc riêng**.

| Khía cạnh | IPv4 thường gặp | IPv6 thường gặp | Rủi ro khi chỉ xét IPv4 |
| --- | --- | --- | --- |
| Địa chỉ | 32 bit, địa chỉ private RFC 1918 | 128 bit, global, ULA, link-local và các phạm vi khác | Không kiểm kê địa chỉ thực tế của host |
| DNS | Bản ghi **A** | Bản ghi **AAAA** | Hostname có thể dẫn client tới endpoint IPv6 |
| Định tuyến | Route IPv4 | Route IPv6 độc lập | Một ranh giới có thể được định tuyến khác |
| Khám phá láng giềng | ARP | Neighbor Discovery dùng ICMPv6 | Chặn sai ICMPv6 làm đứt kết nối |
| Router mặc định | DHCPv4 hoặc cấu hình khác | Thường nhận từ Router Advertisement (RA) hoặc cấu hình tĩnh | Chỉ kiểm tra DHCP mà không thấy route IPv6 |
| Phân giải MTU | ICMP IPv4 và cơ chế PMTUD | ICMPv6 Packet Too Big là tín hiệu thiết yếu cho PMTUD | Chặn toàn bộ ICMPv6 gây lỗi đường truyền |
| NAT | NAT44 được dùng phổ biến | End-to-end routing thường không đòi hỏi NAT66 | Nhầm NAT với firewall và kiểm soát truy cập |
| Chuyển tiếp/giao thức | IPv4 forwarding | IPv6 forwarding và extension headers | Thiết bị có thể áp policy/parsing khác nhau |
| Truy cập dịch vụ | Listener trên IPv4 | Listener trên IPv6 hoặc dual-stack socket | Một cổng có thể mở trên một family ngoài dự kiến |
| Giám sát | IPv4 flow/log, allowlist theo IPv4 | IPv6 flow/log, địa chỉ đầy đủ và prefix | SIEM có vùng mù cho IPv6 |

**Không có kết luận chung rằng IPv6 mặc định ít an toàn hơn IPv4.** Cả hai đều cần identity, least privilege, segmentation, firewall và telemetry. Vấn đề xuất hiện khi tổ chức chỉ triển khai một nửa những yêu cầu đó.

### 2.1. Các dải địa chỉ IPv6 nên nhận biết

| Dải hoặc địa chỉ | Ý nghĩa | Lưu ý vận hành |
| --- | --- | --- |
| **::1/128** | Loopback | Không phải đích truy cập từ máy khác |
| **fe80::/10** | Link-local | Dùng trên một liên kết, thường cần interface/zone ID khi gọi |
| **fc00::/7** | Unique Local Address (ULA) | Không được định tuyến trên Internet công cộng theo mục đích thiết kế; vẫn cần kiểm soát nội bộ |
| **2000::/3** | Không gian global unicast hiện hành chủ yếu | Có địa chỉ global không đồng nghĩa Internet có thể kết nối trực tiếp |
| **ff00::/8** | Multicast | NDP, một số giao thức và dịch vụ dùng multicast |
| **::/128** | Unspecified address | Không dùng như địa chỉ đích của host bình thường |
| **2001:db8::/32** | Prefix dành cho tài liệu | Dùng trong ví dụ, không phải địa chỉ hệ thống thật |
| **::ffff:0:0/96** | Dạng IPv4-mapped IPv6 | Một số API/socket biểu diễn IPv4 theo cách này; cần hiểu semantics của ứng dụng |

Một host có thể đồng thời có **link-local**, **ULA**, **global IPv6** và nhiều địa chỉ tạm thời. Link-local không thể được định tuyến như một địa chỉ global qua Internet, nhưng vẫn đáng bảo vệ ở cùng segment vì các nguy cơ liên quan NDP, RA hoặc điều khiển truy cập lớp liên kết.

### 2.2. Có địa chỉ global không đồng nghĩa có đường truy cập công khai

Một host mang địa chỉ global unicast có thể vẫn bị firewall stateful, security group, route hoặc policy chặn từ Internet. Ngược lại, host không có global IPv6 vẫn có thể dùng ULA hoặc link-local để giao tiếp nội bộ. Tránh hai suy luận sai:

- “Địa chỉ IPv6 global chắc chắn đang mở ra Internet.”
- “Không có global IPv6 nên hệ thống không cần chính sách IPv6.”

Cần kiểm tra **địa chỉ + listener + route + policy + điểm nguồn + kết quả kết nối** trước khi xác định phạm vi phơi lộ.

## 3. Vì sao IPv6 xuất hiện dù đội vận hành chỉ thiết kế IPv4?

Nhiều hệ điều hành kích hoạt ngăn xếp IPv6 theo mặc định hoặc hỗ trợ nó mà không cần cấu hình ứng dụng riêng. Địa chỉ link-local có thể được tạo ngay cả khi tổ chức chưa cấp global IPv6. Khi mạng quảng bá prefix IPv6 hoặc có cấu hình route phù hợp, máy có thể tự hình thành thêm địa chỉ.

Các nguồn phát sinh IPv6 thường gặp:

1. **ISP/CPE/router:** cấp IPv6 prefix và phát Router Advertisement vào segment.
2. **Hệ điều hành:** có IPv6 stack, link-local interface, temporary/privacy addresses và route IPv6.
3. **DNS/CDN:** hostname có bản ghi AAAA; dịch vụ có nhiều endpoint IPv4/IPv6.
4. **Cloud:** subnet, NIC, load balancer hoặc service được cấu hình dual-stack.
5. **Container/service mesh:** CNI hoặc ingress controller được cấu hình IPv6/dual-stack.
6. **VPN:** tunnel chỉ vận chuyển IPv4 nhưng thiết bị khách vẫn có IPv6 qua mạng ngoài.
7. **Wi-Fi/BYOD:** một client nhận IPv6 từ mạng khách hoặc một RA không mong đợi.
8. **Transition technology:** NAT64/DNS64 hoặc tunnel/translation mechanism có thể tạo đường IPv6 khác với sơ đồ IPv4.

Tính sẵn có trên OS **không chứng minh IPv6 có route khả dụng**. Vì vậy bước kiểm tra phải ghi cả địa chỉ và route/default gateway, không chỉ xem một checkbox “IPv6 enabled”.

### 3.1. SLAAC, RA và DHCPv6 khác nhau

Với **SLAAC**, host nhận thông tin prefix từ Router Advertisement và tự tạo địa chỉ theo cơ chế áp dụng. RA còn có thể thông báo default router và một số tham số khác. **DHCPv6** có thể cung cấp địa chỉ hoặc các tham số bổ sung, nhưng **không phải phương thức chuẩn để cung cấp default router theo cách DHCPv4 thường làm**. DNS resolver có thể được thông báo qua RDNSS trong RA, DHCPv6 hoặc cấu hình khác tùy nền tảng.

**Sai lầm phổ biến:** không thấy DHCPv6 server nên kết luận “mạng không có IPv6”. Host vẫn có thể có link-local, nhận RA, tạo địa chỉ và định tuyến bằng IPv6. Kiểm tra **RA, IPv6 route và nguồn cấu hình DNS** mới đầy đủ.

## 4. Bản đồ trust boundary phải thể hiện cả IPv4 lẫn IPv6

Xét một môi trường giả định:

~~~mermaid
flowchart LR
    G[Wi-Fi GUEST / BYOD] --> R[Access switch / VLAN]
    R --> F[Firewall phân đoạn]
    A[Mạng APP] --> F
    F --> P[API gateway]
    P --> D[(Database)]
    V[Remote VPN client] --> F
    C[Cloud VPC / VNet] --> P
    T[SIEM / NDR / Flow logs] -. Giám sát .-> F
    T -. Giám sát .-> P
~~~

Một sơ đồ như vậy chưa đủ nếu chỉ gắn IPv4 CIDR lên đường truyền. Với mỗi mũi tên phải biết:

- Nguồn và đích có **IPv4, IPv6, cả hai hay chỉ một family**?
- Địa chỉ thuộc prefix nào; DHCP/SLAAC, ULA hay global IPv6?
- DNS trả **A/AAAA** nào cho cùng tên dịch vụ ở từng zone?
- Route IPv6 có qua **cùng firewall và cùng PEP** như route IPv4 không?
- ACL, security group, Kubernetes NetworkPolicy, host firewall có áp cho IPv6 không?
- VPN mang IPv6 trong tunnel hay để IPv6 thoát ra ngoài?
- Proxy/WAF/IDS/IPS/NDR có thực sự thấy traffic IPv6 ở đúng nơi không?
- Nếu một đường failover được kích hoạt, IPv6 có đi qua policy tương đương không?

### 4.1. Ma trận luồng theo từng address family

| Nguồn | Đích | Yêu cầu nghiệp vụ | IPv4 mong đợi | IPv6 mong đợi |
| --- | --- | --- | --- | --- |
| GUEST | Payment API | Không được gọi API nội bộ | Deny | Deny |
| APP order-service | Payment API | Chỉ service được định danh gọi TCP/8443 | Allow có điều kiện | Allow có điều kiện nếu IPv6 được triển khai |
| APP workload khác | Payment database | Không truy cập trực tiếp | Deny | Deny |
| VPN contractor | Management network | Không có quyền quản trị | Deny | Deny |
| VPN admin đã xác thực | Management API | Truy cập theo PAM/MFA và danh tính | Allow có điều kiện | Allow có điều kiện nếu path được phê duyệt |
| Internet | Public HTTPS edge | Chỉ public listener được công bố | Allow TCP/443 | Allow TCP/443 nếu dịch vụ dual-stack |
| Internet | Direct application origin | Không bypass edge | Deny | Deny |

**Nếu dịch vụ không chủ đích hỗ trợ IPv6**, yêu cầu nên ghi “không có đường IPv6 đến đích” và **kiểm thử điều đó**, thay vì bỏ trống cột IPv6. Nếu có hỗ trợ, policy hai family cần thể hiện **cùng ý định bảo mật** nhưng có thể phải triển khai bằng cú pháp/đối tượng riêng.

### 4.2. Data plane và control plane đều phải xét

Một rule IPv4 chặn packet tới database không bảo vệ được trường hợp tài khoản cloud bị cấp quyền rộng, có thể thay IPv6 security rule qua API hoặc bật IPv6 cho load balancer. Khi mô hình hóa, bổ sung:

**Data plane:** nguồn → route → firewall/security group → proxy/LB → backend.

**Control plane:** người dùng hoặc automation → IAM/API → thay đổi địa chỉ, prefix, RA, route, policy, DNS và quyền.

Sai lầm không chỉ là thiếu rule IPv6; còn là thiếu kiểm soát **ai được phép kích hoạt IPv6 hoặc sửa đường đi IPv6**.

## 5. DNS AAAA và cơ chế chọn IPv4/IPv6 của client

Một hostname có thể đồng thời trả bản ghi A và AAAA:

~~~text
api.example.test.  IN A     192.0.2.20
api.example.test.  IN AAAA  2001:db8:10:20::20
~~~

Đây là bản ghi minh họa sử dụng tên/địa chỉ dành cho tài liệu. Nhiều client hiện đại triển khai các thuật toán chọn địa chỉ hoặc cơ chế kiểu **Happy Eyeballs** để giảm độ trễ khi một family hoạt động không tốt. **Không được giả định ứng dụng luôn ưu tiên IPv4, cũng không khẳng định luôn chọn IPv6**; lựa chọn phụ thuộc hệ điều hành, resolver, routing, policy và kết quả kết nối.

Từ góc độ an ninh:

1. Đội network chỉ xác minh TCP/443 qua địa chỉ **A**.
2. Dịch vụ được xuất bản thêm **AAAA** qua edge hoặc origin.
3. Client có route IPv6 khả dụng.
4. IPv6 traffic đi qua rule khác hoặc backend không được bảo vệ tương đương.
5. Phát sinh đường kết nối không có trong ma trận kiểm soát ban đầu.

**AAAA record không tự chứng minh có lỗ hổng.** Phải kiểm chứng route, listener, firewall, TLS termination và hành vi ứng dụng thực tế từ đúng zone.

### 5.1. Split-horizon và load balancing làm tăng số đường đi

Doanh nghiệp có thể trả A/AAAA khác nhau ở DNS nội bộ, Wi-Fi khách và Internet. CDN có thể chuyển IP theo vị trí và tình trạng dịch vụ. Khi đánh giá exposure:

- Ghi DNS resolver nào được dùng, timestamp và kết quả **A** lẫn **AAAA**.
- Kiểm tra FQDN tại **từng vùng mạng có quyền kiểm thử**.
- Liên hệ địa chỉ tới VIP, reverse proxy hay direct origin.
- Không tự động mở phạm vi quét tới mọi IP của nhà cung cấp CDN chỉ vì hostname trỏ tới đó.

### 5.2. Domain và URL không thay thế kiểm thử IP

Một request qua domain có thể chọn IPv4 hoặc IPv6 dựa trên client. Để kiểm tra một family cụ thể, có thể dùng tùy chọn của client hoặc kiểm thử trực tiếp trên địa chỉ đã xác nhận. Lưu ý khi kiểm thử HTTPS theo IP: **SNI, hostname và certificate validation** có thể thay đổi kết quả; hãy phân biệt lỗi TLS/ứng dụng với kết nối TCP và không tắt xác minh chứng chỉ chỉ để làm bài test “thành công”.

## 6. Listener và host firewall: cùng port nhưng hai bề mặt kết nối

Một ứng dụng có thể lắng nghe trên địa chỉ IPv4, IPv6 hoặc cả hai. Ký hiệu **0.0.0.0** thường chỉ việc lắng nghe trên các địa chỉ IPv4 của host; **::** thường chỉ lắng nghe trên IPv6, và khả năng socket đó còn chấp nhận IPv4-mapped connections **phụ thuộc hệ điều hành/cấu hình IPV6_V6ONLY**. Không suy rằng cấu hình IPv4-only có hiệu lực cho IPv6.

| Listener minh họa | Có thể có nghĩa | Cần kiểm chứng |
| --- | --- | --- |
| 127.0.0.1:8080 | Bind vào loopback IPv4 | Không thể suy từ đó có IPv6 listener |
| 0.0.0.0:8080 | Bind tới các địa chỉ IPv4 | IPv6 có listener riêng hay không |
| [::1]:8080 | Bind loopback IPv6 | Không phải IPv6 global listener |
| [::]:8443 | Bind wildcard IPv6 | Có IPv4-mapped support không, host firewall thế nào |
| [2001:db8:10:20::20]:443 | Bind địa chỉ global IPv6 cụ thể | Route, zone, firewall và quyền ứng dụng |

Ví dụ, server được bảo vệ bởi rule IPv4 chỉ cho TCP/443 từ load balancer. Nhưng service vừa có listener **[::]:443** vừa có route IPv6 từ zone khác. Nếu host firewall chỉ được cấu hình ở family IPv4, rule đó **không mặc nhiên bảo vệ IPv6**.

**Không dùng việc đóng IPv6 stack toàn hệ thống làm giải pháp đầu tiên.** Một số ứng dụng/hạ tầng phụ thuộc IPv6 hoặc API dual-stack; tắt thiếu kế hoạch có thể làm lỗi DNS, cluster, VPN hay vận hành. Ưu tiên kiểm kê, giới hạn listener, định tuyến và áp chính sách IPv6 có kiểm soát.

## 7. Firewall, ACL và security group: phải xét cả hai family

Lỗi hay gặp nhất là nhân bản một chính sách chỉ ở IPv4:

~~~text
Thiết kế bảo mật:
  GUEST -> APP: deny tất cả ngoài luồng đã phê duyệt

Cấu hình thực tế thiếu sót:
  IPv4 GUEST -> APP: deny
  IPv6 GUEST -> APP: không có rule tương đương hoặc rule quá rộng

Hậu quả tiềm năng:
  IPv4 test: denied
  IPv6 test: có thể được allow theo đường/policy khác
~~~

Đây là mô hình nguyên nhân, **không phải quy tắc mặc định của mọi firewall**. Có sản phẩm chặn IPv6 theo mặc định, có sản phẩm tách IPv4/IPv6 policy, có engine áp chung theo đối tượng hai family và có những ngoại lệ phụ thuộc phiên bản. Phải đọc **effective ruleset** trên đúng platform và kiểm chứng bằng traffic từ các zone được cấp quyền.

### 7.1. Cú pháp và phạm vi rule khác nhau theo nền tảng

| Nền tảng | Điều cần biết |
| --- | --- |
| Linux nftables | Family **inet** có thể bao phủ cả IPv4/IPv6; family **ip** chỉ IPv4, **ip6** chỉ IPv6 |
| Linux iptables/ip6tables | Có bảng xử lý riêng theo address family; còn phụ thuộc backend nft/legacy thực tế |
| Host firewall Windows | Rule có thể giới hạn địa chỉ/protocol/profile; cần xem scope có IPv6 và profile phù hợp không |
| Firewall appliance | IPv4/IPv6 rulebase, object type, implicit deny và policy ordering tùy nhà cung cấp |
| Cloud security group/NSG | Các CIDR IPv4/IPv6 có thể là rule riêng; xem cả ingress lẫn egress |
| Network ACL | Có thể stateless, cần đúng cả hướng đi và response, gồm IPv6 |
| Kubernetes/CNI | NetworkPolicy và hỗ trợ IPv6/dual-stack phụ thuộc CNI/version; cần test trên hệ thống thật |

**Không bê nguyên một rule IPv4 sang IPv6 rồi giả định hoàn thành.** Prefix, nguồn danh tính, route, đối tượng dịch vụ, trạng thái kết nối và log fields có thể khác. Cũng không nên tạo rule **::/0 allow** chỉ để “kích hoạt IPv6”: đó là toàn bộ không gian địa chỉ IPv6, tương tự về độ rộng với 0.0.0.0/0 ở IPv4.

### 7.2. Ví dụ chính sách trừu tượng cho cả hai family

Đây là dữ liệu mô tả ý định, **không phải cấu hình cho một thiết bị cụ thể**:

~~~yaml
policy_id: guest-to-payment-boundary
owner: network-security
source_zone: GUEST
destination_service: payment-api
protocol: tcp
port: 8443
expected:
  ipv4: deny
  ipv6: deny
controls:
  - verify_ipv4_rule_and_route
  - verify_ipv6_rule_and_route
  - verify_host_firewall_for_both_families
  - verify_cloud_or_network_acl_if_present
evidence:
  - firewall_decision_log
  - endpoint_connection_test
  - policy_version
~~~

Phương án dùng một bộ policy-as-code có thể giúp **phát hiện nhánh IPv6 bị bỏ sót**, nhưng chỉ khi pipeline render đúng engine của nhà cung cấp và kiểm thử được **effective policy** chứ không chỉ kiểm tra file YAML.

### 7.3. Đặc biệt chú ý rule theo CIDR

IPv6 thường dùng prefix /64 ở một LAN hoặc /128 cho host address cụ thể, nhưng độ dài prefix phụ thuộc thiết kế. **Không biến mọi /64 thành nhóm tin cậy**, vì nó có thể chứa nhiều thiết bị và nhiều địa chỉ tạm thời. Một rule cho cả prefix cần owner, mục đích và đánh giá blast radius.

## 8. ICMPv6, NDP và Router Advertisement không thể xử lý như ICMPv4

Trong IPv6, **ICMPv6 là một phần thiết yếu của hoạt động mạng**, không chỉ là gói ping. Nhiều chức năng cốt lõi sử dụng ICMPv6:

| Loại sự kiện | Vai trò | Rủi ro khi chặn bừa |
| --- | --- | --- |
| Neighbor Solicitation/Advertisement (NS/NA) | Neighbor Discovery, xác định link-layer neighbor | Không phân giải láng giềng, mất kết nối local |
| Router Solicitation/Advertisement (RS/RA) | Host khám phá router/prefix và một số cấu hình | Không có default route/SLAAC khi cần |
| Packet Too Big | Path MTU Discovery của IPv6 | Kết nối lớn bị treo hoặc lỗi khó chẩn đoán |
| Destination Unreachable | Báo lỗi đích/đường đi | Lỗi ứng dụng khó hiểu, retry không cần thiết |
| Time Exceeded | Hop limit hết hoặc một số tình huống khác | Khó chẩn đoán đường đi |
| Multicast Listener Discovery (MLD) | Tham gia/quản lý nhóm multicast | Có thể ảnh hưởng multicast và hạ tầng L2 |
| Echo Request/Reply | Chẩn đoán reachability | Có thể giới hạn theo policy, không đại diện toàn ICMPv6 |

**Chặn toàn bộ ICMPv6 để “an toàn như chặn ping” là một sai lầm.** Cần chính sách cho phép các loại thông điệp cần thiết ở đúng scope và kiểm soát loại nhạy cảm, thay vì một rule broad drop cho mọi ICMPv6. Các khuyến nghị chi tiết phải theo nền tảng, loại thiết bị và kiến trúc.

### 8.1. Rogue RA và ranh giới mạng truy cập

Một host không được phép phát **Router Advertisement** có thể làm các client cùng segment nhận sai thông tin định tuyến hoặc DNS (tùy cơ chế), dẫn đến gián đoạn hoặc chuyển traffic qua điểm không mong muốn. Biện pháp có thể gồm:

- **RA Guard** trên switch/access network nếu platform hỗ trợ và đã kiểm chứng.
- Giới hạn cổng được phép phát RA và đánh dấu router uplink hợp lệ.
- Dùng NAC/802.1X, port security hoặc cơ chế kiểm soát IPv6 first-hop phù hợp.
- Giám sát RA/ND bất thường, prefix và router chưa được quản lý.
- Kiểm tra implementation với extension headers, fragmentation và giới hạn phần cứng; không giả định mọi thiết bị RA Guard đều có độ bao phủ giống nhau.

**RA Guard không thay thế firewall segmentation hoặc xác thực ứng dụng.** Nó xử lý một lớp vấn đề trên local link, còn quyền đi từ zone này sang zone khác phải được thực thi ở boundary tương ứng.

### 8.2. Neighbor Discovery không giống ARP

IPv6 sử dụng NDP dựa trên ICMPv6 thay cho ARP. Thiết kế giám sát chỉ quan sát ARP sẽ bỏ sót việc thiết bị nào đang sử dụng IPv6 trong một segment. Đánh giá tài sản cần kết hợp neighbor table, switch/controller telemetry, inventory, DHCPv6/RA state và endpoint logs; không lấy một địa chỉ IPv6 tạm thời làm định danh người dùng vĩnh viễn.

## 9. VPN dual-stack và rủi ro đường IPv6 ngoài tunnel

Một VPN client có thể được cấp route cho IPv4 nội bộ nhưng **không có chính sách định tuyến IPv6 tương đương**. Khi đó, cùng thiết bị có thể dùng:

~~~text
Ứng dụng của client
    |-- IPv4 nội bộ --> VPN tunnel --> Gateway doanh nghiệp --> Firewall
    |
    +-- IPv6 đến dịch vụ có AAAA --> Mạng truy cập hiện tại / ISP
                                      (có thể không qua gateway doanh nghiệp)
~~~

Đây là kịch bản **split tunnel hoặc đường đi chưa được bảo vệ theo yêu cầu**, không phải khẳng định mọi VPN IPv4-only đều rò rỉ IPv6. Tác động phụ thuộc OS route table, chính sách endpoint firewall, DNS resolution, VPN client features và cách quản lý mạng.

Các câu hỏi bắt buộc:

1. VPN là **full tunnel** hay **split tunnel** với IPv4, IPv6?
2. Client có default route IPv6 hoặc route tới địa chỉ đích qua interface ngoài VPN không?
3. DNS do VPN cấp có trả AAAA khiến traffic ứng dụng chọn IPv6 không?
4. Endpoint có policy chặn các đường ra ngoài tunnel khi yêu cầu doanh nghiệp cần như vậy không?
5. VPN gateway có xử lý và ghi log IPv6 inner traffic không?
6. Policy truy cập có dựa trên user/device identity hay chỉ IP sau NAT?
7. Khi VPN mất kết nối, reconnect hoặc failover, đường IPv6 thay đổi ra sao?

### 9.1. Không chỉ kiểm tra “what is my IPv4”

Kiểm thử VPN cần nhìn **IPv4/IPv6 routes, DNS A/AAAA, egress path và các đích nghiệp vụ được chỉ định**. Nếu yêu cầu là mọi lưu lượng công việc phải qua kiểm soát doanh nghiệp, cần chứng minh cả hai address families đi qua điểm kiểm soát hoặc bị chặn phù hợp.

Không tự ý vô hiệu hóa IPv6 trên mọi laptop để khắc phục nhanh. Đây có thể là biện pháp tạm trong phạm vi được quản lý nếu có đánh giá tương thích, nhưng thiết kế bền vững là **policy rõ theo user, device, destination và path**, kèm kiểm thử định kỳ.

## 10. Wi-Fi, BYOD và NAC: cùng SSID không có nghĩa cùng chính sách IPv6

Trong mạng không dây, một SSID có thể gắn vào VLAN khách hoặc doanh nghiệp; **802.1X/RADIUS/NAC** xác minh thiết bị/người dùng và ánh xạ vào nhóm quyền. Tuy nhiên:

- Client có thể nhận IPv6 từ RA khi chưa có DHCPv6.
- Các host cùng Wi-Fi segment có thể giao tiếp trực tiếp bằng IPv6 nếu **client isolation** hoặc local ACL chưa áp phù hợp.
- IPv4 firewall có thể chặn inter-VLAN nhưng IPv6 route/ACL đang khác.
- BYOD/IoT có thể có nhiều IPv6 addresses, kể cả temporary addresses.
- Wi-Fi controller có thể ghi IP/MAC/username không đồng bộ giữa IPv4 và IPv6.

Phép kiểm chứng nên gồm **guest client → guest peer**, **guest → corporate subnet**, **guest → management interface** và **guest → DNS/VPN dependencies**, mỗi trường hợp xét IPv4 và IPv6 nếu được thiết kế sử dụng. Từ chối kết nối tới địa chỉ IPv4 không chứng minh cùng tài nguyên không tiếp cận được qua IPv6.

### 10.1. Chú ý first-hop security

Với switch/controller hỗ trợ, đánh giá RA Guard, DHCPv6 Guard, IPv6 source guard hoặc các cơ chế neighbor validation thích hợp. Không áp chính sách mù quáng trên các port có router hoặc hạ tầng IPv6 hợp lệ; chặn RA/ND cần thiết sẽ tạo outage khó chẩn đoán.

## 11. Cloud và hybrid network: cấu hình IPv4 không bảo đảm IPv6

Trong cloud, IPv6 có thể được kích hoạt ở **VPC/VNet, subnet, network interface, virtual machine, load balancer, public endpoint hoặc managed service**. Nhiều nền tảng cho phép cấu hình IPv4 CIDR và IPv6 CIDR trong security policy bằng những đối tượng khác nhau. Khi chuyển một ứng dụng từ IPv4-only sang dual-stack, việc chỉ bổ sung địa chỉ IPv6 và AAAA là **chưa hoàn thành triển khai an ninh**.

### 11.1. Kiểm tra ít nhất bốn lớp

| Lớp | Câu hỏi kiểm chứng | Ví dụ lỗi |
| --- | --- | --- |
| **Addressing** | NIC/subnet/VIP có IPv6 prefix nào, ai sở hữu, có public không? | Gắn global IPv6 vào một instance ngoài dự kiến |
| **Routing** | IPv6 route table, gateway, peering, private link và failover như thế nào? | Có đường IPv6 không qua inspection point đã thiết kế |
| **Enforcement** | Security group/NSG, NACL, cloud firewall, host firewall có IPv6 policy không? | Chỉ định nghĩa IPv4 deny/allow, còn IPv6 có rule quá rộng |
| **Exposure/identity** | DNS AAAA, load balancer listener, origin, IAM và service authz thế nào? | Public VIP dùng WAF nhưng origin có IPv6 direct path |

**IPv6 không sử dụng NAT như một yêu cầu bắt buộc để đi Internet.** Tuy nhiên, **không dùng NAT** không có nghĩa tự nhiên mở inbound: security group, stateful firewall, route và policy vẫn kiểm soát reachability. Ngược lại, có NAT44 cũng chưa từng là bằng chứng đủ về quyền truy cập ở IPv4.

### 11.2. Stateful security group và stateless network ACL

Tùy nhà cung cấp, security group thường cho phép mô tả các rule theo address family và theo hướng, trong khi network ACL có thể **stateless**, đòi hỏi xét cả request và response, bao gồm port chiều về khi cần. Không sao chép một cú pháp chung cho mọi cloud; cần kiểm tra semantics thực tế của chính nền tảng.

Ví dụ yêu cầu:

~~~text
Public edge:
  IPv4 internet -> edge TCP/443: allowed
  IPv6 internet -> edge TCP/443: allowed, nếu dual-stack được duyệt

Application origin:
  IPv4 internet -> origin directly: denied
  IPv6 internet -> origin directly: denied

Gateway -> origin:
  IPv4 hoặc IPv6: chỉ nguồn/đích và service identity được duyệt
~~~

Nếu nhà cung cấp có **egress-only gateway cho IPv6**, phải hiểu nó bảo vệ **loại đường outbound** được cấu hình, không tự giải quyết mọi kết nối qua peering, private networking, VPN hoặc các interface khác.

### 11.3. Managed services và log provider

Không phải dịch vụ cloud nào hỗ trợ IPv6 giống nhau. Một API gateway có thể dual-stack trong khi backend hoặc managed database vẫn chỉ hỗ trợ IPv4, và chiều kết nối giữa các thành phần có thể được proxy/translate. Kiểm tra:

- Feature hỗ trợ IPv6, phiên bản và khu vực triển khai.
- DNS, listener, route, source-IP handling và client identity thực tế.
- Flow log format có đầy đủ IPv6 source/destination, action, interface và timestamp không.
- IAM permissions cho việc cấp IPv6 address/prefix, sửa route, sửa firewall và publish AAAA.
- Tác động của autoscaling, load-balancer target rotation và rollback khi bỏ IPv6.

**Cloud audit logs** về việc một resource được gán IPv6 giúp điều tra thay đổi, nhưng không thay cho phép kiểm tra network path. **Flow ACCEPT** ở một điểm cloud cũng chưa chứng minh ứng dụng đã nhận hoặc chấp thuận request.

## 12. Container, Kubernetes và service mesh dual-stack

Ở Kubernetes, ứng dụng có thể được phơi lộ qua **Pod IP, Service ClusterIP, Ingress/Gateway, node port hoặc external load balancer**, với khả năng IPv6 phụ thuộc cấu hình cluster, CNI, phiên bản và cloud integration. Một số lớp có thể IPv4-only trong khi lớp khác dual-stack.

### 12.1. Các điểm dễ bị bỏ qua

| Đối tượng | Cần xác định | Rủi ro |
| --- | --- | --- |
| Pod | Có IPv4, IPv6 hoặc cả hai; socket bind ra sao? | Service nghe IPv6 ngoài ý định |
| Service | ClusterIP/service address family và policy | Đường IPv6 mới không được kiểm thử |
| Ingress/Gateway | Public/private listener, TLS termination, IPv4/IPv6 | Có path bỏ qua WAF hoặc auth gateway |
| CNI | Có áp NetworkPolicy cho IPv6, egress và ingress không? | Rule dual-stack chỉ có hiệu lực một phần |
| NetworkPolicy | Selector, ipBlock, namespace và hướng bảo vệ | Một số traffic không được chọn bởi policy |
| Sidecar/mesh | Traffic IPv6 có đi qua proxy, có identity và mTLS không? | Mesh policy không bao phủ bypass path |
| Node/host network | Host firewall và route IPv6 của node | Nhầm giới hạn pod với giới hạn host |
| Egress gateway | Địa chỉ/route cho external destinations | IPv6 đi trực tiếp dù IPv4 buộc qua proxy |

**Kubernetes NetworkPolicy tiêu chuẩn không phải API authorization theo người dùng**, và việc thực thi phụ thuộc vào CNI. Đặc biệt, **ingress và egress là hai hướng độc lập**: có policy deny ingress không có nghĩa mọi outbound IPv6 đã bị chặn. Nhiều NetworkPolicy chọn cùng pod có thể có semantics cộng dồn quy tắc allow; không suy từ một YAML riêng mà phải kiểm tra hiệu lực tổng hợp.

### 12.2. Minh họa yêu cầu trước khi triển khai

Giả sử order-service cần gọi payment-service trong cùng cluster:

~~~yaml
control_intent:
  source_identity: order-service
  destination_identity: payment-service
  application_action: create-payment-intent
  transport:
    protocol: tcp
    port: 8443
  network_policy_expectation:
    ipv4: only-approved-workloads
    ipv6: only-approved-workloads-if-enabled
  service_authorization: require-verified-principal
  deny:
    - direct-database-access-from-order-service
    - unintended-external-origin-access
  validation:
    - ipv4-positive-and-negative
    - ipv6-positive-and-negative
    - failover-and-policy-readback
~~~

Đây là **schema diễn giải ý định**, không phải Kubernetes resource hợp lệ. Khi triển khai thực, cần dịch sang NetworkPolicy, CNI extension, gateway/mesh authorization và policy ứng dụng phù hợp với cụm. **mTLS không tự xác định caller được sửa giao dịch nào**; workload identity và resource-level authorization vẫn là các lớp riêng.

### 12.3. Dual-stack có thể tồn tại ở biên mà không có ở backend

Một public load balancer có thể nhận IPv6 rồi kết nối backend qua IPv4. Trong trường hợp đó, backend không nhất thiết có IPv6 listener; nhưng vẫn cần kiểm tra **edge IPv6 policies, WAF, TLS, rate limit, client-IP attribution và logging**. Không kết luận hệ thống không có IPv6 exposure chỉ vì pod hoặc database dùng IPv4.

## 13. Cơ chế chuyển đổi IPv4/IPv6 và đường đi không hiển thị trên sơ đồ cũ

Một hệ thống không nhất thiết truyền từ IPv6 client tới IPv6 server hoàn toàn end-to-end. Có những cơ chế chuyển đổi, dịch địa chỉ và tunnel để hỗ trợ các môi trường có địa chỉ khác nhau:

| Cơ chế | Ý nghĩa khái niệm | Cần kiểm tra |
| --- | --- | --- |
| **NAT64/DNS64** | Client IPv6-only có thể truy cập server IPv4 qua dịch địa chỉ và DNS hỗ trợ | Policy trước/sau translation, logs ánh xạ, identity |
| **464XLAT** | Hỗ trợ ứng dụng IPv4 trong mạng truy cập IPv6-only bằng các lớp translation | Đường thực, điểm logging và cách hiển thị endpoint |
| **Dual-stack proxy/LB** | Một family ở phía client, family khác ở upstream | TCP/TLS termination và ACL cho từng chặng |
| **Legacy IPv6-over-IPv4 tunnels** | IPv6 payload được đóng gói đi qua hạ tầng IPv4 | Có cho phép tunnel không, điểm phân tích nhìn outer hay inner traffic |
| **Site-to-site VPN dual-stack** | Một hoặc cả hai family đi qua tunnel được quản trị | Inner/outer policy, route và logging |
| **IPv6-only/private cloud segment** | Dịch vụ nội bộ sử dụng IPv6 hoặc translation tới phần còn lại | Policy phù hợp với identity và đường dữ liệu |

Ví dụ, nếu một cảm biến ngoài VPN chỉ thấy IPv4 outer traffic, nó chưa chắc đọc được IPv6 inner traffic được mã hóa. Ngược lại, firewall kiểm soát địa chỉ IPv4 **outer tunnel endpoint** có thể không biết nguồn/đích IPv6 bên trong nếu không có điểm thực thi ở đầu kết thúc tunnel.

Một số cơ chế tunnel tự động cũ có thể không còn được khuyến nghị hoặc bị tắt trên môi trường hiện đại. **Không nên giả định chúng đang hoạt động**, nhưng nên kiểm kê những gì được cho phép theo chính sách và những gì ứng dụng/hệ điều hành thực sự sử dụng.

### 13.1. IPv4-mapped IPv6 addresses không phải một kênh bảo mật riêng

Một số API biểu diễn IPv4 endpoint theo dạng **::ffff:192.0.2.10**. Điều này có thể ảnh hưởng cách ứng dụng log, so sánh địa chỉ hoặc áp allowlist khi dùng socket dual-stack. Nó **không tự biến một IPv4 connection thành đường IPv6 xuyên qua firewall**. Nếu viết application-level IP policy, cần normalize/parse địa chỉ đúng chuẩn và kiểm thử các kiểu biểu diễn để tránh nhầm identity và rule matching.

### 13.2. TLS/QUIC và extension headers

Đối với HTTPS, TLS mã hóa nội dung ứng dụng trên cả IPv4 và IPv6; HTTP/3 thường sử dụng QUIC/UDP. Thiết bị chỉ phân tích TCP/443 trên IPv4 có thể thiếu coverage cho **UDP/443 và IPv6**. Các extension headers và fragmentation của IPv6 cũng đòi hỏi engine kiểm tra packet hiểu đúng protocol; không mặc định tất cả IDS/IPS hoặc firewall phiên bản cũ xử lý tương đương.

Nếu một thiết bị tuyên bố hỗ trợ IPv6, cần kiểm thử trên **phiên bản và tính năng đang dùng**, kể cả logging, routing, failover và performance, không chỉ kiểm tra một checkbox hỗ trợ.

## 14. Monitoring, IDS/IPS và network forensics: vùng mù IPv6

Khi SOC chỉ có dashboard/alert theo IPv4, lưu lượng IPv6 có thể xuất hiện trong hệ thống nhưng không được phân loại, tương quan hoặc điều tra đúng. Các rủi ro:

- Flow exporter chỉ cấu hình cho IPv4 hoặc sensor không được đặt trên IPv6 path.
- SIEM parser không xử lý IPv6 literal, CIDR, địa chỉ dạng rút gọn hay IPv4-mapped IPv6.
- Correlation rule dựa trên regex IPv4 nên bỏ qua bản ghi IPv6.
- Asset inventory/DHCP chỉ lưu IPv4; một endpoint có nhiều temporary IPv6 addresses bị coi là nhiều máy.
- IDS/IPS signature hoặc policy có phạm vi protocol/address family khác mong đợi.
- Firewall deny logs chỉ được bật trong IPv4 rulebase.
- DNS visibility chỉ thu bản ghi A, bỏ AAAA và thông tin resolver.
- VPN logging chỉ phản ánh đường IPv4 trong tunnel.
- NDR nhìn thấy IPv4 outer tunnel nhưng không thấy IPv6 traffic bên trong.

**Không thấy alert IPv6 không đủ để kết luận không có rủi ro IPv6.** Phải biết telemetry source có nhìn được luồng hay không và rule phát hiện có được thiết kế để kiểm tra nó hay không.

### 14.1. Những trường nên có trong network telemetry

| Trường | Vai trò |
| --- | --- |
| event_time_utc / ingest_time_utc | Phân biệt mốc traffic và độ trễ pipeline |
| source_ip / destination_ip | Đầy đủ IPv4 hoặc IPv6, không cắt chuỗi theo khuôn IPv4 |
| address_family | Phân biệt family hoặc suy từ kiểu dữ liệu đã chuẩn hóa |
| source_asset_id / workload_id | Liên hệ nhiều địa chỉ của cùng host/workload |
| source_port / destination_port / protocol | Xác định 5-tuple và TCP/UDP |
| zone / interface / VRF / VPC / tenant | Gắn nguồn với trust boundary |
| action / policy_id / policy_version | Biết allow/deny do điểm nào quyết định |
| dns_query / dns_answer / resolver | Kiểm tra liên hệ A/AAAA và dịch vụ |
| nat_or_translation_context | Ánh xạ address/port trước/sau NAT64, proxy hoặc NAT |
| sensor_id / capture_scope | Biết vị trí có quan sát và giới hạn |
| user / device / service_identity | Quy kết bằng xác thực, không chỉ địa chỉ IP |

Nếu hệ thống SIEM yêu cầu normalize địa chỉ, nên dùng kiểu dữ liệu hoặc thư viện IP-aware xử lý đúng **IPv6 compression, canonicalization, CIDR/prefix và IPv4-mapped representations**. Không cắt địa chỉ ở dấu hai chấm vì IPv6 chứa dấu đó trong cú pháp.

### 14.2. Đối chiếu log từ nhiều nguồn độc lập

~~~mermaid
flowchart LR
    H[Endpoint / Client] --> R[IPv4 + IPv6 route]
    R --> F[Firewall / Security group]
    F --> W[WAF / Gateway]
    W --> S[Application]
    D[DNS A / AAAA] -. Context .-> H
    E[EDR + Asset inventory] -. Identity .-> H
    F -. Flow + decision log .-> SIEM[SIEM / Forensics]
    W -. HTTP + TLS / request ID .-> SIEM
    S -. App authz/audit .-> SIEM
    E -. Endpoint process .-> SIEM
    D -. Resolver events .-> SIEM
~~~

Nên đối chiếu **firewall session/flow, DNS AAAA, host listener, EDR và application access log** để phân biệt: IPv6 có tồn tại, có connection attempt, đã qua control, đã tới backend hay đã được application xử lý. Hai dashboard đọc cùng một nguồn flow chưa phải hai bằng chứng độc lập.

### 14.3. Temporary IPv6 addresses và quy kết tài sản

Một client có thể thay địa chỉ nguồn IPv6 theo thời gian vì cơ chế privacy address hoặc chính sách quản lý. Phân tích chỉ nhóm theo source IPv6 mà không có mốc thời gian, endpoint ID và thông tin kết nối có thể làm sai số lượng host hoặc nhầm người dùng. Bằng chứng quy kết có thể gồm:

- Endpoint/EDR device ID và timestamp.
- NAC/RADIUS/802.1X association hoặc VPN session identity.
- Lịch sử prefix/interface/neighbor mapping từ thiết bị mạng.
- DHCPv6 lease nếu mạng thực sự sử dụng DHCPv6.
- Cloud instance/pod UID và audit history.

**MAC hoặc IPv6 address đơn lẻ cũng không bảo đảm danh tính người thực hiện**; cần các nguồn identity có mức tin cậy phù hợp.

## 15. Kiểm kê IPv6 bằng công cụ chỉ đọc

Các lệnh sau dùng để **quan sát trên hệ thống có quyền quản trị/kiểm thử**, không thực hiện quét hàng loạt hay thay cấu hình. Các địa chỉ/tên miền trong ví dụ là placeholder; cần thay bằng asset lab hoặc tài sản đã được phê duyệt.

### 15.1. Linux: địa chỉ, route và listener

~~~bash
# Liệt kê IPv6 addresses của các interface.
ip -6 addr show

# Xem bảng định tuyến IPv6, gồm default route khi có.
ip -6 route show

# Xem route dự kiến tới một đích IPv6 được phép kiểm tra.
ip -6 route get 2001:db8:10:20::20

# Xem các socket TCP/UDP đang lắng nghe; kiểm tra bind ::, ::1 hoặc IPv6 cụ thể.
ss -lntup

# Xem thông tin neighbor hiện tại trên liên kết.
ip -6 neigh show
~~~

**Cách đọc:** có địa chỉ **fe80::** chưa chứng minh host có đường IPv6 ra Internet. Một default route IPv6 cho thấy ứng viên đường đi, nhưng không chứng minh firewall đã cho phép request. Listener **[::]:443** cần được kiểm tra cùng OS socket semantics và host firewall; không kết luận toàn bộ client ngoài mạng đều truy cập được.

### 15.2. Linux: firewall và DNS

~~~bash
# Đọc ruleset nftables đang có, không thay đổi rule.
sudo nft -a list ruleset

# Hệ thống sử dụng ip6tables có thể kiểm tra IPv6 rule riêng:
sudo ip6tables -S

# Kiểm tra DNS A và AAAA từ resolver đang được cấu hình:
dig api.example.test A
dig api.example.test AAAA
~~~

Lệnh **ip6tables** có thể không có hoặc không phản ánh toàn bộ firewall khi host dùng nftables, firewalld, cloud security group hay một engine khác. Phải xác định **nền tảng thực tế** và so các rule effective cho IPv4/IPv6. Tên **api.example.test** chỉ minh họa, không kỳ vọng có bản ghi thật.

Đối với nftables, family **inet** có thể lọc cả hai family; đừng báo “thiếu IPv6 firewall” chỉ vì không thấy chain family **ip6** khi đã có policy **inet** đúng. Ngược lại, chain family **ip** chỉ áp cho IPv4; phải có chính sách tương ứng cho IPv6 ở nơi thích hợp.

### 15.3. Windows: xác minh cấu hình IPv6 cục bộ

~~~powershell
# Liệt kê địa chỉ IPv6 và route theo address family.
Get-NetIPAddress -AddressFamily IPv6
Get-NetRoute -AddressFamily IPv6

# Xem cấu hình DNS resolver IPv6 nếu có.
Get-DnsClientServerAddress -AddressFamily IPv6

# Xem các TCP listener đang hoạt động.
Get-NetTCPConnection -State Listen

# Kiểm tra phân giải DNS cho cả hai loại bản ghi.
Resolve-DnsName api.example.test -Type A
Resolve-DnsName api.example.test -Type AAAA
~~~

Việc không có DNS server IPv6 riêng trong một output **không tự chứng minh client không truy vấn AAAA**: DNS vẫn có thể đi qua resolver bằng IPv4 và trả AAAA. Cần tách **protocol truyền truy vấn DNS** khỏi **loại record được truy vấn**.

### 15.4. Kiểm tra đường kết nối với phạm vi đã được phê duyệt

Trên host Linux có route và quyền phù hợp:

~~~bash
# Kiểm thử HTTPS có giới hạn thời gian đến FQDN được phê duyệt;
# buộc client sử dụng đúng address family.
curl -4 --connect-timeout 3 --max-time 8 -I https://api.example.test/
curl -6 --connect-timeout 3 --max-time 8 -I https://api.example.test/

# Kiểm tra đường IPv6 ở một đích được phép (trong lab):
traceroute -6 -n 2001:db8:10:20::20
~~~

Lệnh là **mẫu cú pháp**, không có đích thật để chạy từ bài học. Dùng trong RoE đã phê duyệt, với giới hạn số lần thử và giám sát. Nếu **curl -6** trả lỗi, cần phân biệt DNS không có AAAA, không có route, firewall deny, timeout TCP, TLS certificate failure hoặc HTTP error; không gộp tất cả thành “IPv6 bị chặn an toàn”.

Trên Windows, kiểm thử TCP tới một IPv6 literal được phép:

~~~powershell
Test-NetConnection -ComputerName "2001:db8:10:20::20" -Port 443
~~~

Kết quả chỉ xác nhận trạng thái TCP từ **máy đang kiểm thử** tại thời điểm đó; không chứng minh chính sách cho mọi zone, mọi port hoặc các luồng UDP/QUIC. Nếu kiểm tra link-local, công cụ và hệ điều hành có thể yêu cầu **scope/interface ID**, và đường đó chỉ có ý nghĩa trên local link.

### 15.5. Đừng lấy số lượng địa chỉ làm bằng chứng exposure

Một máy có nhiều IPv6 global addresses không nhất thiết mở nhiều dịch vụ. Một ứng dụng có một listener wildcard nhưng nhiều route/policy có thể tạo nhiều đường tới nó. Kiểm kê cần kết hợp **tài sản, listener, service identity, route, firewall và quyền ứng dụng**, không chỉ đếm địa chỉ.

## 16. Thiết kế kiểm thử hai family với kết quả có thể chứng minh

Trước kiểm thử, lập **Rules of Engagement**: owner, địa chỉ/zone, protocol/port, khung thời gian, phương pháp, tốc độ, log, điều kiện dừng và cách xử lý tác động. Bắt đầu bằng các phép thử đọc cấu hình và connection checks tới **đúng các endpoint được chỉ định**. Không quét toàn bộ prefix IPv6 hoặc nhắm tới bên thứ ba chỉ vì muốn kiểm chứng đường đi.

### 16.1. Ma trận test tối thiểu

| Mã | Nguồn | Đích | Family | Kỳ vọng | Bằng chứng cần thu |
| --- | --- | --- | --- | --- | --- |
| T01 | GUEST | APP API TCP/8443 | IPv4 | Deny | Client result + firewall deny |
| T02 | GUEST | APP API TCP/8443 | IPv6 | Deny | Client result + IPv6 policy/flow |
| T03 | APP service được phép | Payment API | IPv4 | Allow | TCP/TLS + app access log |
| T04 | APP service được phép | Payment API | IPv6 | Allow nếu được thiết kế | Same path + policy + identity |
| T05 | APP service khác | Payment DB | IPv4 | Deny | Firewall/DB audit |
| T06 | APP service khác | Payment DB | IPv6 | Deny | IPv6 deny + endpoint result |
| T07 | VPN contractor | Management port | IPv4 | Deny | VPN/auth/firewall |
| T08 | VPN contractor | Management port | IPv6 | Deny hoặc không có route theo thiết kế | VPN client route + logs |
| T09 | Internet | Public HTTPS edge | IPv4 | Allow | WAF/gateway/access log |
| T10 | Internet | Public HTTPS edge | IPv6 | Allow nếu được xuất bản | TLS/gateway/firewall IPv6 log |
| T11 | Internet | Direct origin | IPv4 | Deny | Origin/edge policy |
| T12 | Internet | Direct origin | IPv6 | Deny | Origin address/route + firewall deny |
| T13 | Internal test host | DNS resolver | IPv4 | Đúng ACL | DNS response + logs |
| T14 | Internal test host | DNS resolver | IPv6 | Đúng ACL | DNS response + IPv6 logs |

Nếu môi trường **không sử dụng IPv6** cho một luồng, trạng thái mong đợi không nên để trống. Nêu rõ “không được có đường IPv6 tới tài sản đích” và dùng kiểm thử/phân tích cấu hình có kiểm soát để chứng minh.

### 16.2. Các trạng thái cần phân biệt trong báo cáo

| Quan sát | Có thể nói | Không nên khẳng định |
| --- | --- | --- |
| Không tìm thấy AAAA | Resolver/view đang hỏi không trả AAAA tại thời điểm đó | Tài sản không có IPv6 hoặc không thể truy cập trực tiếp |
| Không có default IPv6 route | Host hiện không có default route IPv6 trong bảng đã kiểm tra | Không thể có traffic IPv6 link-local/ULA |
| TCP timeout | Không nhận được kết nối thành công trong cửa sổ thử | Một firewall cụ thể chắc chắn đã deny |
| TCP connection thành công | Port đích tiếp cận được từ nguồn đã thử | Dịch vụ đã xác thực/ủy quyền request |
| Firewall IPv6 deny log | Thiết bị áp quyết định deny cho flow được ghi | Mọi đường khác đều bị chặn |
| WAF access log | Request đã đi qua WAF tại thời điểm đó | Mọi request tới origin đều qua WAF |
| Không có NDR alert | Không có alert tương ứng trong nguồn đang kiểm tra | Không có traffic hoặc không có vấn đề bảo mật |
| IPv6 cùng chính sách với IPv4 | Các test đã chọn đạt yêu cầu trong phạm vi đó | Toàn bộ dual-stack deployment đã an toàn |

### 16.3. Bảo đảm chất lượng phép thử

- Kiểm tra **source interface, zone, VPN state và route thực tế** trước khi thử.
- Ghi rõ **IPv4/IPv6 literal**, FQDN, DNS answer và timestamp UTC.
- Không đổi đồng thời DNS, ACL, VPN và application listener rồi đánh giá nguyên nhân từ một phép thử.
- Kiểm tra cả **positive tests** (luồng hợp lệ) và **negative tests** (luồng phải chặn).
- So log tại **đúng enforcement point** và log ứng dụng; kiểm tra sensor có thấy cả hai chiều.
- Khi thử IPv6, cân nhắc ICMPv6 PMTUD/ND để tránh kết luận sai do cấu hình làm mạng hoạt động lỗi.
- Với đường bất đối xứng, failover và cloud dual-stack, thử thêm từ những điểm nguồn quan trọng theo RoE.

## 17. Case study: mạng khách bị chặn IPv4 nhưng vào được IPv6

### 17.1. Bối cảnh

Một công ty vận hành mạng **GUEST**, vùng **APP**, API gateway và firewall phân đoạn. Chính sách nghiệp vụ quy định thiết bị khách **không được gọi API quản trị nội bộ** ở cổng TCP/8443. Nhóm network đã thiết lập firewall policy chặn IPv4 từ GUEST tới APP và xác minh bằng kiểm thử TCP.

Sau một đợt triển khai IPv6 thử nghiệm, router quảng bá prefix IPv6 tới GUEST, ứng dụng có IPv6 listener và DNS nội bộ trả AAAA cho cùng hostname. Chính sách ở ranh giới IPv6 chưa được rà soát tương đương.

~~~text
GUEST client
  |-- IPv4: 10.50.0.20 --> FW IPv4 deny --> APP API 10.20.0.10:8443
  |
  +-- IPv6: 2001:db8:50::20 --> FW IPv6 policy khác --> APP API
                                           2001:db8:20::10:8443

Kỳ vọng nghiệp vụ: deny cả hai family từ GUEST.
Kết quả giả định: IPv4 bị chặn; IPv6 TCP connection thành công.
~~~

Đây là **kịch bản giáo dục giả định**, không phải mô tả của một tổ chức thực. IPv6 không tự bypass firewall; kết nối thành công vì **đường IPv6 và effective policy đã cho phép nó**.

### 17.2. Timeline điều tra minh họa

| UTC | Nguồn | Bằng chứng | Diễn giải |
| --- | --- | --- | --- |
| 09:00 | Change record | Router/segment được bật IPv6 và RA trong maintenance | Có thay đổi liên quan đường IPv6 |
| 09:05 | Endpoint inventory | GUEST client có prefix IPv6 và route tới APP | IPv6 path có thể tồn tại |
| 09:06 | DNS resolver | Hostname trả cả A và AAAA | Client có thể chọn IPv6 |
| 09:07 | Firewall policy | IPv4 GUEST→APP deny, IPv6 rule không tương đương | Policy gap cần xác nhận |
| 09:08 | Client test | IPv4 TCP/8443 thất bại, IPv6 TCP/8443 thành công | Khác biệt reachability đã quan sát |
| 09:08 | Firewall/flow logs | IPv6 flow đi qua ranh giới với action allow | Định vị điểm thực thi |
| 09:09 | API gateway log | Nhận kết nối/request test có marker | Xác nhận đường tới tầng ứng dụng nếu log tương ứng |

Các mốc này được đặt để minh họa **cách nối bằng chứng**, không phải giả lập một log thật đã được thu. Nếu TCP thành công nhưng ứng dụng từ chối HTTP 403, vẫn có phát hiện về **network reachability trái thiết kế** dù authorization tầng ứng dụng có thể đã chặn thao tác.

### 17.3. Xác định nguyên nhân gốc

Nhóm điều tra không nên ghi “IPv6 không an toàn” hoặc “firewall bị bypass” mà không xác minh. Một kết luận có căn cứ:

> **Nguyên nhân:** yêu cầu phân đoạn GUEST→APP được triển khai và kiểm thử ở IPv4 nhưng không được áp đủ trên IPv6. Sau khi router phát RA, DNS có AAAA và API listener hỗ trợ IPv6, một đường IPv6 thuộc phạm vi policy chưa kiểm soát cho phép kết nối từ GUEST tới APP. Phép thử từ GUEST, firewall session log và API gateway log xác nhận đường này trong cửa sổ đã kiểm tra.

Phải xem thêm liệu việc truy cập có tới resource nhạy cảm hay bị application authentication/authorization chặn; không suy rằng có dữ liệu bị lấy chỉ vì kết nối TCP thành công.

### 17.4. Khắc phục không làm gián đoạn vận hành

1. **Bảo toàn** cấu hình IPv4/IPv6, log, DNS answer, route và mốc thay đổi.
2. Xác định chủ sở hữu luồng, ranh giới và quy tắc **deny GUEST→APP ở cả hai family**.
3. Kiểm tra dependencies IPv6 hợp lệ: RA, ND, DNS, VPN, monitoring và traffic nội bộ được duyệt.
4. Tạo thay đổi policy trong staging, dùng native firewall/ACL/host policy phù hợp với nền tảng.
5. Kiểm thử cả GUEST IPv4/IPv6 bị deny và APP/service hợp lệ vẫn truy cập được.
6. Triển khai trong change window có giám sát, phiên bản cấu hình trước thay đổi và rollback.
7. Đọc lại effective policy, kiểm tra flow logs, API health và DNS sau thay đổi.
8. Bổ sung kiểm tra IPv6 vào CI/policy-as-code và các lần triển khai dual-stack tiếp theo.

**Không nên chặn mọi ICMPv6 hoặc xóa hàng loạt AAAA** như giải pháp mặc định. Những hành động đó có thể làm hỏng IPv6 hợp lệ và che lấp nguyên nhân thực là thiếu chính sách boundary.

### 17.5. Kết quả cần được báo cáo giới hạn đúng

Sau khắc phục, có thể kết luận: “Trong các đường thử đã phê duyệt, kết nối GUEST→APP TCP/8443 bị chặn ở IPv4 và IPv6; những luồng hợp lệ và dịch vụ phụ thuộc được xác nhận vẫn hoạt động”. **Không nên** báo “toàn hệ thống IPv6 đã an toàn” khi các subnet, ứng dụng, cloud endpoints hoặc failure paths khác chưa được kiểm chứng.

## 18. Playbook khắc phục lỗi chỉ bảo vệ IPv4

### Giai đoạn 1 — Khảo sát

1. Kiểm kê thiết bị/zone và loại hỗ trợ **IPv4-only, IPv6-only, dual-stack**.
2. Thu địa chỉ, prefix, RA, default route, DNS A/AAAA và listener.
3. Vẽ các đường đi qua firewall, router, VPN, LB, cloud gateway, CNI/mesh.
4. Xác định những nơi không có owner, không có chính sách IPv6 hoặc không có telemetry.

### Giai đoạn 2 — Đặt yêu cầu tương đương

Với mỗi flow, viết rõ **ai → tài nguyên nào → giao thức/port → quyền và mục đích**. Sau đó ánh xạ thành yêu cầu của IPv4 và IPv6. Quy tắc dựa trên identity vẫn cần network reachability phù hợp; không thay authorization của ứng dụng bằng địa chỉ nguồn.

### Giai đoạn 3 — Ưu tiên theo rủi ro

| Ưu tiên | Đối tượng | Lý do |
| --- | --- | --- |
| Cao | Management plane, VPN, payment/data stores, public origin | Có quyền cao hoặc dữ liệu nhạy cảm |
| Cao | Internet-facing AAAA/IPv6 VIP và đường direct-to-origin | Có thể tạo exposure ngoài kiểm soát edge |
| Cao | Guest/BYOD/contractor → corporate segments | Ranh giới giữa vùng ít tin cậy và tài sản quan trọng |
| Trung bình | Internal east-west, cloud workload egress, service mesh | Nguy cơ lateral movement và bypass |
| Tùy ngữ cảnh | Link-local, RA/ND trên mạng truy cập | Cần first-hop security và tính khả dụng |
| Theo lộ trình | Lab, hệ thống legacy hoặc mạng IPv6 chưa kích hoạt | Vẫn cần inventory và giới hạn trước khi bật |

### Giai đoạn 4 — Thiết kế thay đổi an toàn

- Dùng cấu hình được hỗ trợ, tránh viết packet filter tùy biến khi firewall/CNI đã có khả năng cần thiết.
- Bảo toàn **ICMPv6 thiết yếu**, first-hop policy và dependency.
- Phân quyền thao tác thay đổi route/prefix/DNS/ACL theo IAM/PAM phù hợp.
- Đặt guardrails cho **::/0**, source/destination prefix rộng hoặc các rule không có ngày hết hạn.
- Kiểm tra IPv6 flow tương ứng đã có logging và SIEM correlation.
- Lập backup, recovery point, health checks, change approval và rollback.

### Giai đoạn 5 — Triển khai và nghiệm thu

~~~mermaid
flowchart TD
    A[Inventory + DNS A/AAAA + routes] --> B[Ma trận trust boundary cho 2 family]
    B --> C[Review policy và dependencies ICMPv6]
    C --> D[Lab / staging / canary]
    D --> E{Positive và negative tests đạt?}
    E -->|Không| F[Sửa policy và phân tích lỗi]
    F --> D
    E -->|Có| G[Change approval + deploy từng vùng]
    G --> H[Readback effective config + flow/health logs]
    H --> I{Có ảnh hưởng hoặc bypass?}
    I -->|Có| J[Dừng / rollback / điều tra]
    I -->|Không| K[Đóng change, lưu bằng chứng, monitor drift]
~~~

**Tắt IPv6 hoàn toàn** chỉ có thể là quyết định kiến trúc riêng sau khi đã kiểm kê phụ thuộc và đánh giá tác động; không coi đó là phương án sửa mặc định cho mọi tổ chức. Nếu một môi trường cố ý IPv4-only, phải đảm bảo **IPv6 không có đường được phép ngoài thiết kế**, đồng thời không phá các thành phần hệ điều hành/dịch vụ cần thiết.

## 19. Những ngộ nhận và sai lầm cần tránh

| Ngộ nhận | Vì sao không đúng | Cách làm đúng |
| --- | --- | --- |
| “Firewall IPv4 đã chặn, IPv6 cũng bị chặn.” | Hai family có thể có policy/routing khác nhau | Đọc effective rules và test IPv4/IPv6 |
| “Không có DHCPv6 tức là không có IPv6.” | SLAAC và RA vẫn có thể cấp route/address | Kiểm tra RA, địa chỉ, route và DNS |
| “IPv6 global nghĩa là Internet chắc chắn vào được.” | Reachability phụ thuộc route, firewall, listener | Kiểm tra theo điểm nguồn và policy |
| “Chỉ có link-local thì không cần bảo vệ.” | Cùng LAN vẫn có rủi ro RA/ND và dịch vụ nội bộ | First-hop security và inventory |
| “IPv6 không có NAT nên không có firewall.” | NAT và stateful filtering là hai chức năng khác nhau | Áp firewall/ACL độc lập với NAT |
| “Tắt mọi ICMPv6 để harden.” | Phá ND, RA/PMTUD và một số luồng cần thiết | Cho phép loại cần thiết theo scope |
| “DNS query đi qua IPv4 nên không có AAAA.” | DNS transport và record type là hai khái niệm | Query A/AAAA và kiểm tra route |
| “Đã test hostname, không cần test hai family.” | Client có thể chọn family khác theo môi trường | Buộc/ghi rõ IPv4 và IPv6 trong test |
| “VPN full tunnel IPv4 đã bảo vệ hết traffic.” | IPv6 có thể đi theo route khác | Xác nhận cả IPv4/IPv6 path, DNS và endpoint policy |
| “WAF bảo vệ public IPv4 nên origin IPv6 cũng an toàn.” | Origin có thể có direct IPv6 path | Test direct-origin deny và edge IPv6 |
| “Một security group rule IPv4 áp cho ::/0.” | CIDR và family khác nhau | Review IPv6 ingress/egress riêng |
| “Có NetworkPolicy là Kubernetes dual-stack an toàn.” | CNI, selector và direction cần kiểm chứng | Test effective policy cho từng family |
| “Không có alert tức là không có IPv6 attack.” | Sensor/parser/pipeline có thể thiếu IPv6 | Kiểm tra coverage và raw flow |
| “Mỗi IPv6 source address là một host.” | Một host có thể có nhiều temporary addresses | Gắn với asset/identity theo thời gian |
| “IPv4-mapped IPv6 luôn là tunnel bypass.” | Có thể chỉ là cách biểu diễn socket API | Hiểu cơ chế API và normalize địa chỉ |
| “AAAA không có trong một DNS view là đủ.” | Split DNS, direct IP, cloud VIP có thể tồn tại | Kiểm tra nhiều zone và inventory |
| “Muốn sửa thì tắt IPv6 trên tất cả máy.” | Có thể phá dependency và che policy gap | Thiết kế theo boundary và rollback |
| “Một lần thử IPv6 bị timeout nghĩa là an toàn.” | Có thể là DNS/route/TLS/lỗi ngẫu nhiên | Đối chiếu client, FW, app logs và telemetry |

## 20. Checklist kiểm tra IPv6 trước khi kết luận mạng đã được bảo vệ

- [ ] Đã xác định trust boundary và yêu cầu nghiệp vụ cho cả **IPv4 và IPv6**.
- [ ] Có inventory asset, địa chỉ, prefix, IPv6-only/IPv4-only/dual-stack và owner.
- [ ] Đã ghi nhận link-local, ULA, global IPv6 và temporary addresses khi cần.
- [ ] Đã kiểm tra IPv6 default route, route liên vùng và đường failover.
- [ ] Đã xác minh DNS **A/AAAA**, split-horizon, resolver và actual target IP.
- [ ] Đã kiểm tra application listener, wildcard sockets và host firewall cho hai family.
- [ ] Đã đối chiếu firewall, ACL, security group/NSG, NACL và cloud firewall IPv6.
- [ ] Không có rule **::/0** quá rộng hoặc exception không owner ngoài mục đích phê duyệt.
- [ ] Đã kiểm tra guest/BYOD/contractor → management/APP/DATA theo cả hai family.
- [ ] Đã đánh giá VPN split/full tunnel và egress IPv6 từ endpoint ngoài tunnel.
- [ ] Đã xác định RA/SLAAC/DHCPv6/NDP, first-hop policy và nguồn RA hợp lệ.
- [ ] Không chặn toàn bộ ICMPv6; ND/RA/Packet Too Big và các dependency khác hoạt động đúng.
- [ ] Đã kiểm tra IPv6 trên Wi-Fi controller, NAC và client isolation nếu thuộc phạm vi.
- [ ] Đã rà soát cloud NIC, subnet, LB, public origin, IAM và route IPv6.
- [ ] Đã xác minh Kubernetes CNI/NetworkPolicy, Service, ingress, egress và mesh dual-stack.
- [ ] Đã kiểm kê NAT64/DNS64, proxy, translation và các tunnel có thể đổi đường đi.
- [ ] Đã xác minh NDR/IDS/IPS/firewall flow/SIEM thực sự tiếp nhận và phân tích IPv6.
- [ ] SIEM và inventory chuẩn hóa địa chỉ đúng, không ghép nhầm temporary IPv6 addresses thành nhiều người dùng.
- [ ] Có positive và negative tests cho mỗi boundary quan trọng với cả hai families hoặc trạng thái không hỗ trợ IPv6 được chứng minh.
- [ ] Các phép thử được cấp quyền, có source zone, timestamp UTC, traffic giới hạn và stop conditions.
- [ ] Có backup, owner, change approval, canary, rollback và post-change monitoring.
- [ ] Báo cáo ghi rõ những đường đã kiểm thử, chưa kiểm thử, nguồn bằng chứng và giới hạn kết luận.

**Kết luận:** Sai lầm “bỏ qua IPv6 khi chỉ bảo vệ IPv4” không nằm ở bản thân giao thức IPv6, mà ở việc **thiết kế, triển khai và giám sát kiểm soát an ninh chỉ cho một address family**. Một kiến trúc mạng an toàn phải hiểu đúng địa chỉ, DNS, route, identity, firewall, VPN, ICMPv6/NDP, cloud và các đường ứng dụng cho cả hai family. Khi yêu cầu bảo mật được viết theo trust boundary và được nghiệm thu bằng kiểm thử IPv4/IPv6 có kiểm soát, tổ chức có thể hỗ trợ dual-stack mà không tạo thêm đường truy cập bị bỏ sót.
