# NAT và tác động tới policy của firewall

**Network Address Translation (NAT)** là cơ chế thiết bị mạng thay đổi địa chỉ IP nguồn hoặc đích của gói tin khi gói đi qua một điểm xử lý. Trong một số dạng NAT, thiết bị còn thay đổi **cổng TCP/UDP** để nhiều luồng có thể dùng chung địa chỉ IP. NAT thường xuất hiện tại firewall biên, router, VPN gateway, load balancer, cổng ra Internet của cloud và các mạng cần xử lý địa chỉ trùng nhau.

NAT có ảnh hưởng trực tiếp tới **firewall policy**: tại điểm đánh giá một quy tắc, thiết bị có thể nhìn thấy địa chỉ **trước khi dịch (pre-NAT)** hoặc **sau khi dịch (post-NAT)**, tùy nền tảng và vị trí xử lý. Nếu không xác định rõ điều đó, kỹ sư dễ viết rule sai đối tượng, mở quyền quá rộng hoặc chặn nhầm một luồng hợp lệ.

Trong chương **Firewall** của module **SECURITY_NETWORK_SECURITY**, bài này đặt NAT vào kiến trúc phòng vệ nhiều lớp: phân đoạn mạng, network ACL, VPN, IDS/IPS, xác thực kết nối, DNS, hạ tầng cloud và giám sát. NAT giúp kết nối và quản lý không gian địa chỉ; **NAT tự nó không phải cơ chế xác thực, mã hóa hoặc thay thế firewall**.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài, người học có thể:

1. Giải thích SNAT, DNAT, PAT/NAPT, static/dynamic NAT, hairpin NAT và mục đích của từng dạng.
2. Truy dấu bộ thông tin **IP nguồn, cổng nguồn, IP đích, cổng đích, giao thức** trước và sau một phép dịch.
3. Phân tích cách NAT tương tác với routing, stateful firewall, stateless ACL và luồng phản hồi.
4. Xác định policy phải tham chiếu **địa chỉ gốc hay địa chỉ đã dịch**, dựa trên điểm thực thi và tài liệu nền tảng.
5. Đánh giá nguy cơ của port forwarding, NAT dùng chung, VPN có địa chỉ chồng lấp, log thiếu khả năng quy nguồn, NAT trong cloud và IPv6.
6. Thiết kế ma trận luồng, bộ test cho kết nối được phép/bị chặn, quy trình khắc phục lỗi và kiểm soát thay đổi NAT.

## 2. NAT thay đổi điều gì trong gói tin?

### 2.1. Khái niệm địa chỉ, cổng và 5-tuple

Với một luồng TCP hoặc UDP, ta thường mô tả bằng **5-tuple**:

~~~text
(Source IP, Source port, Destination IP, Destination port, Protocol)
~~~

Ví dụ một máy ứng dụng nội bộ gọi dịch vụ HTTPS:

~~~text
Trước NAT:
(10.20.10.25, 52340, 192.0.2.80, 443, TCP)

Sau SNAT/PAT:
(203.0.113.20, 40001, 192.0.2.80, 443, TCP)
~~~

Các địa chỉ 192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24 trong bài thuộc các dải **dành cho tài liệu và ví dụ (TEST-NET)**. Chúng không phải địa chỉ Internet sản xuất được cấp cho tổ chức; chỉ sử dụng trong sơ đồ hoặc lab cô lập.

Trong ví dụ, firewall thay địa chỉ nguồn riêng 10.20.10.25 thành địa chỉ đại diện 203.0.113.20 và thay cổng nguồn 52340 thành 40001. Server bên ngoài thấy nguồn là **203.0.113.20:40001**. Khi phản hồi về địa chỉ/cổng đã dịch, thiết bị NAT tra ánh xạ để đưa gói trở lại **10.20.10.25:52340**.

Phép dịch IP cần cập nhật những trường gói tin liên quan (và checksum khi cần). **NAT không tự đọc hiểu payload ứng dụng**; các giao thức nhúng địa chỉ IP/cổng trong payload có thể cần cơ chế hỗ trợ riêng hoặc không làm việc nếu thiết bị chỉ thay header.

### 2.2. NAT mapping và bảng trạng thái

Nhiều hệ thống lưu ánh xạ NAT trong một **translation table** hoặc cơ chế theo dõi kết nối (connection tracking). Ví dụ:

| Trường | Giá trị trước NAT | Giá trị bên ngoài sau NAT |
| --- | --- | --- |
| Client/source | 10.20.10.25 | 203.0.113.20 |
| Source port | 52340 | 40001 |
| Server/destination | 192.0.2.80 | 192.0.2.80 |
| Destination port | 443/TCP | 443/TCP |
| Ánh xạ khi trả lời | 203.0.113.20:40001 | Chuyển phản hồi về 10.20.10.25:52340 |

Thiết bị có thể tái sử dụng một địa chỉ IP ngoài cho nhiều máy nội bộ bằng các cổng nguồn ngoài khác nhau. **Không thể quy người dùng từ mỗi IP ngoài đơn lẻ** khi nhiều máy cùng chia sẻ NAT; cần thêm thời điểm, giao thức, cổng đã dịch và log ánh xạ.

Đừng đánh đồng **bảng NAT** với **bảng session của firewall**: trên nhiều thiết bị chúng liên kết chặt, nhưng NAT mapping và quyết định cho phép theo security policy là hai chức năng cần phân biệt. Một ánh xạ có thể tồn tại mà một luồng cụ thể vẫn bị chặn theo policy.

### 2.3. Cổng mặc định và giới hạn quan sát

NAT có thể thay đổi **cổng TCP/UDP** nhưng không tự chuyển TCP thành UDP hoặc ngược lại. HTTP/3 sử dụng QUIC trên UDP, vì vậy NAT/ACL chỉ xử lý TCP/443 sẽ không bao phủ HTTP/3 qua **UDP/443**. Các giao thức không có khái niệm cổng TCP/UDP, chẳng hạn ICMP, có cách ánh xạ và theo dõi riêng tùy thiết bị.

Khi NAT chia sẻ địa chỉ và cổng, nó phụ thuộc vào tài nguyên như số ánh xạ có thể tạo và thời gian tồn tại phiên. **Cạn kiệt cổng nguồn khả dụng, bảng phiên đầy hoặc timeout UDP quá ngắn** có thể gây lỗi kết nối dù DNS, routing và rule cho phép đều đúng.

## 3. Các loại NAT phổ biến

| Kiểu NAT | Thay đổi | Mục đích thường gặp | Điều phải chú ý trong policy |
| --- | --- | --- | --- |
| **SNAT** (Source NAT) | Địa chỉ nguồn, có thể cả cổng nguồn | Client nội bộ đi ra Internet, ẩn cấu trúc IP nội bộ khỏi đích | Phía ngoài nhìn thấy IP đã SNAT; log cần đủ dữ liệu quy ngược |
| **DNAT** (Destination NAT) | Địa chỉ đích, có thể cả cổng đích | Công bố dịch vụ nội bộ qua một địa chỉ/cổng công khai | Đích gốc và backend khác nhau; firewall rule có thể khớp một trong hai theo nền tảng |
| **PAT/NAPT** | Kết hợp địa chỉ và cổng, đặc biệt khi nhiều client dùng chung IP ngoài | Tiết kiệm IPv4, chia sẻ địa chỉ egress | Port mapping, số lượng kết nối, timeout, quy nguồn |
| **Static NAT** | Ánh xạ cố định giữa các địa chỉ/đầu cuối | Dịch vụ có địa chỉ cần ổn định | Ánh xạ cố định không mặc nhiên cho phép gói tin đi qua |
| **Dynamic NAT** | Chọn ánh xạ từ pool theo nhu cầu | Nhiều client dùng một tập IP ngoài | Thay đổi ánh xạ, quản lý pool và log |
| **Twice NAT / policy NAT** | Có thể đổi cả nguồn lẫn đích theo điều kiện | VPN, địa chỉ chồng lấp, nhiều tenant | Rất dễ nhầm địa chỉ nhìn thấy tại từng chặng |
| **Hairpin / NAT loopback** | Client nội bộ truy cập địa chỉ công khai rồi quay tới server nội bộ | Dùng cùng một hostname từ trong và ngoài mạng | Đường vòng, SNAT bổ sung, phản hồi bất đối xứng |
| **NAT64** | Phiên dịch giữa địa chỉ/gói IPv6 và IPv4 theo cơ chế phù hợp | Client IPv6-only truy cập dịch vụ IPv4 | Kết hợp DNS64 hoặc phương pháp khám phá khác khi cần; policy phải xét cả hai họ địa chỉ |

**Port forwarding** là tình huống DNAT (thường đi kèm dịch cổng): ví dụ IP công khai cổng 443 trỏ tới IP riêng cổng 8443. **Masquerading** thường chỉ dạng SNAT sử dụng địa chỉ của interface ra, thích hợp khi địa chỉ phía ngoài có thể thay đổi.

### 3.1. SNAT: dịch nguồn cho kết nối đi ra

~~~mermaid
sequenceDiagram
    participant A as App 10.20.10.25
    participant F as Firewall / SNAT
    participant S as Server 192.0.2.80
    A->>F: TCP 10.20.10.25:52340 → 192.0.2.80:443
    Note over F: SNAT/PAT nguồn thành 203.0.113.20:40001
    F->>S: TCP 203.0.113.20:40001 → 192.0.2.80:443
    S-->>F: TCP 192.0.2.80:443 → 203.0.113.20:40001
    Note over F: Tra ánh xạ NAT và trạng thái phiên
    F-->>A: TCP 192.0.2.80:443 → 10.20.10.25:52340
~~~

Đối tượng ở phía server thường thấy IP nguồn đã SNAT. Nếu chính sách truy cập của đối tác dùng **allowlist IP**, hãy xác nhận đúng địa chỉ egress thực tế và tính đến thay đổi địa chỉ khi chuyển tuyến/thiết bị. Tuy nhiên, một IP nguồn được allowlist không chứng minh danh tính người dùng hoặc ứng dụng: nhiều workload có thể chia sẻ cùng IP NAT.

### 3.2. DNAT: công bố một dịch vụ nội bộ

Giả sử một tổ chức có:

- Địa chỉ dịch vụ công khai: **203.0.113.10:443/TCP**.
- Reverse proxy ở DMZ: **10.30.20.10:8443/TCP**.
- Chỉ nhóm đối tác được phép từ **198.51.100.0/24** truy cập theo hợp đồng.

~~~text
Trước DNAT tại firewall:
198.51.100.25:54000 -> 203.0.113.10:443 TCP

Sau DNAT để chuyển tới reverse proxy:
198.51.100.25:54000 -> 10.30.20.10:8443 TCP

Phản hồi qua đúng đường NAT:
10.30.20.10:8443 -> 198.51.100.25:54000

Phản hồi gửi ra ngoài sau dịch ngược:
203.0.113.10:443 -> 198.51.100.25:54000
~~~

~~~mermaid
flowchart LR
    C["Đối tác\n198.51.100.25"] -->|"TCP tới 203.0.113.10:443"| F["Firewall\nDNAT + security policy"]
    F -->|"TCP tới 10.30.20.10:8443"| P["Reverse proxy DMZ"]
    P -->|"TLS và ứng dụng theo cấu hình"| A["API nội bộ"]
~~~

**Quan trọng:** DNAT chỉ thay đích/port. Nó không bảo đảm request được phép hoặc đã xác thực. Cần **firewall rule giới hạn nguồn**, TLS/chứng chỉ hợp lệ, xác thực/authorization ở API và bảo vệ kết nối giữa proxy với backend.

### 3.3. Hairpin NAT và truy cập bằng hostname chung

Người dùng trong mạng nội bộ có thể nhập cùng URL công khai mà khách ngoài Internet dùng. Nếu DNS nội bộ cũng trả IP công khai, gói có thể đi tới firewall, **DNAT quay trở lại một server trong mạng nội bộ**. Một số kiến trúc phải dùng thêm **SNAT trên đường hairpin** để phản hồi đi qua thiết bị NAT, nếu không server có thể trả lời trực tiếp cho client và làm đứt phiên.

Thay vì mặc định bật hairpin cho mọi nơi, có thể cân nhắc **split-horizon DNS** để nội bộ nhận IP nội bộ. Cách nào phù hợp phụ thuộc TLS hostname, routing, điểm thực thi policy, log và yêu cầu có một URL thống nhất; cần kiểm thử cả người dùng nội bộ lẫn bên ngoài.

## 4. NAT tác động tới firewall policy ở đâu?

### 4.1. Khác biệt giữa địa chỉ gốc và địa chỉ đã dịch

Một thiết bị có thể thực hiện nhiều bước: nhận gói, xác định zone/interface, lookup route, tìm ánh xạ NAT, kiểm tra security policy, dịch địa chỉ, tạo connection state rồi chuyển gói. **Trật tự chính xác phụ thuộc nền tảng, loại NAT, hướng kết nối và chế độ cấu hình**.

Do đó, không có một câu trả lời đúng cho mọi firewall rằng “ACL luôn viết bằng địa chỉ trước NAT” hoặc “policy luôn viết bằng IP đã NAT”. Cần biết:

1. **Rule được thực thi ở đâu**: interface vào, interface ra, host, subnet, VM, container hay cloud firewall.
2. **Rule khớp thông tin nào**: original source/destination hay translated source/destination; port gốc hay port mới.
3. **NAT và security policy có độc lập không**: một số thiết bị buộc định nghĩa cả NAT rule và access rule; một số dịch vụ cloud tự cung cấp NAT ở lớp mạng được quản lý.
4. **Có stateful inspection không**: phản hồi có được liên kết với phiên và ánh xạ NAT không; stateless ACL có cần rule chiều về riêng?
5. **Đường đi có đối xứng không**: luồng phản hồi có đi lại qua đúng thiết bị giữ mapping/trạng thái không?

### 4.2. Cùng một yêu cầu, hai cách biểu diễn policy

Với ví dụ DNAT ở trên, ý định nghiệp vụ là: **chỉ đối tác 198.51.100.0/24 được truy cập reverse proxy qua dịch vụ công khai TCP/443**.

| Thuộc tính | Trước DNAT | Sau DNAT |
| --- | --- | --- |
| Source | 198.51.100.25 | 198.51.100.25 nếu không có SNAT bổ sung |
| Destination | 203.0.113.10 | 10.30.20.10 |
| Destination port | TCP/443 | TCP/8443 |
| Điểm nhìn | Phía Internet trước dịch | Phía DMZ sau dịch |

Hai cách diễn đạt policy minh họa:

~~~text
Biểu diễn A – điểm thực thi xét thông tin gốc:
ALLOW source=198.51.100.0/24
      destination=203.0.113.10/32
      tcp destination_port=443

Biểu diễn B – điểm thực thi xét thông tin sau dịch:
ALLOW source=198.51.100.0/24
      destination=10.30.20.10/32
      tcp destination_port=8443
~~~

**Chọn A hay B phải theo tài liệu và phép thử của nền tảng.** Đây chỉ là mô tả khớp gói, không phải lệnh có thể sao chép vào sản phẩm cụ thể. Trong triển khai thật, cần thêm chiều/hướng, zone, IPv4/IPv6, ứng dụng và trạng thái phù hợp.

### 4.3. NAT không tự cho phép lưu lượng

Cần phân biệt ba chức năng:

| Thành phần | Câu hỏi nó giải quyết | Điều không bảo đảm |
| --- | --- | --- |
| NAT | Gói được dịch sang địa chỉ/cổng nào? | Không cấp quyền cho người dùng hay ứng dụng |
| Routing | Gói sẽ được chuyển qua đường/next hop nào? | Không cho phép kết nối theo chính sách |
| Firewall/ACL | Gói hoặc kết nối có được đi qua điểm bảo vệ không? | Không thay thế xác thực/authorization của ứng dụng |

Một DNAT tới database **không có nghĩa** database đã được công khai nếu firewall policy còn chặn; ngược lại, có DNAT và ALLOW rộng nhưng thiếu phân quyền ứng dụng có thể làm lộ dịch vụ. Đừng xem việc địa chỉ IP riêng không được định tuyến trực tiếp từ Internet là lớp bảo vệ đủ mạnh khi đã có ánh xạ tới nó.

### 4.4. Stateful firewall và stateless ACL

Trên firewall **stateful**, một kết nối hợp lệ thường tạo trạng thái phiên. Phản hồi phù hợp với phiên có thể được cho qua và được dịch ngược theo mapping. Nếu phản hồi đi qua đường khác hoặc mapping hết hạn, phiên có thể hỏng.

Trên **stateless ACL**, mỗi hướng có thể cần được cho phép riêng: gói khởi tạo và gói phản hồi có IP/port khác nhau theo góc nhìn ở mỗi điểm thực thi. Ví dụ server HTTPS trả về từ **source port 443** tới **destination ephemeral port** của client; nếu có PAT, cổng nhìn thấy phía ngoài có thể khác cổng client gốc.

Không suy diễn rằng quy tắc stateless “cho phép tất cả cổng cao” là luôn cần hoặc an toàn. Hãy xác định **dải cổng tạm thời đang sử dụng, hướng và điểm lọc**, rồi áp quy tắc hẹp nhất có thể hoặc dùng stateful filtering phù hợp.

## 5. Thiết kế NAT và security policy theo luồng nghiệp vụ

Trước khi tạo NAT rule, hãy lập ma trận các **luồng được phép khởi tạo**. Dưới đây là kiến trúc minh họa:

| Thành phần | Địa chỉ / vùng | Vai trò |
| --- | --- | --- |
| Đối tác ngoài | 198.51.100.0/24 (giả định) | Gọi API qua HTTPS |
| IP dịch vụ công khai | 203.0.113.10 | Địa chỉ nhận kết nối, DNAT tới DMZ |
| Reverse proxy | 10.30.20.10 | Kết thúc TLS ở DMZ rồi gọi backend |
| App API | 10.30.30.10 | Xử lý nghiệp vụ |
| Database | 10.30.40.10 | Lưu dữ liệu nội bộ |
| NAT egress | 203.0.113.20 | Địa chỉ nguồn đại diện cho traffic ra Internet |
| Dịch vụ cập nhật bên ngoài | 192.0.2.80 | Đích thử nghiệm HTTPS |

### 5.1. Ma trận luồng và điểm lọc

| ID | Nguồn → Đích thực tế | Giao thức/cổng | NAT | Security policy mong muốn |
| --- | --- | --- | --- | --- |
| F01 | Đối tác → IP công khai dịch vụ | TCP/443 | DNAT → Proxy:8443 | **ALLOW** từ đối tác được phê duyệt, chặn nguồn khác |
| F02 | Reverse proxy → App API | TCP/8443 | Không bắt buộc | **ALLOW** riêng cho proxy |
| F03 | App API → Database | TCP/5432 | Không bắt buộc | **ALLOW** từ App API được cấp quyền |
| F04 | App API → dịch vụ cập nhật | TCP/443 | SNAT/PAT → IP egress | **ALLOW** đích/nhu cầu cụ thể |
| F05 | Đối tác → Database | Bất kỳ | Không công bố DB | **DENY** |
| F06 | Internet → cổng quản trị proxy | SSH/RDP hoặc cổng khác | Không công bố | **DENY**; chỉ quản trị qua vùng đã xác thực |
| F07 | App API → Internet bất kỳ | Bất kỳ | Có thể SNAT nếu ra ngoài | **DENY theo mặc định** |

Đây là bảng **ý định kết nối**, chưa phải toàn bộ rule trên một thiết bị. Nếu có lọc stateless ở cả hai hướng, phải thêm phép phân tích phản hồi; nếu một gateway NAT nằm giữa hai vùng, cần chuyển địa chỉ nguồn/đích theo **góc nhìn cụ thể** của gateway và firewall ở chặng sau.

### 5.2. Biểu diễn chính sách trung lập

Ví dụ dưới đây là **pseudo-YAML để review**, không phải định dạng triển khai của một nhà sản xuất:

~~~yaml
network_intent:
  - id: publish-partner-api
    original_flow:
      source: 198.51.100.0/24
      destination: 203.0.113.10/32
      protocol: tcp
      destination_port: 443
    translation:
      type: dnat
      new_destination: 10.30.20.10/32
      new_destination_port: 8443
    security:
      action: allow
      default_for_other_sources: deny
      identity_and_tls_checks: required_at_application
    owner: partner-integration

  - id: api-approved-egress
    original_flow:
      source: 10.30.30.10/32
      destination: 192.0.2.80/32
      protocol: tcp
      destination_port: 443
    translation:
      type: snat_pat
      public_source: 203.0.113.20/32
    security:
      action: allow
      other_egress: deny_by_default
    owner: api-operations
~~~

Trong môi trường thực tế, endpoint của đối tác có thể thay IP; việc quản lý allowlist hoặc identity cần xét cập nhật địa chỉ, DNS, CDN và yêu cầu mTLS. Chỉ kiểm tra IP của đối tác không đủ thay cho xác thực ứng dụng.

### 5.3. Thứ tự quy tắc và khả năng khớp sai

Firewall có thể có thứ tự rule, NAT rule ưu tiên và các điều kiện phức tạp. Hai lỗi thường gặp:

1. Một NAT rule **quá rộng** bắt mọi nguồn/đích trước rule dành cho dịch vụ cụ thể, khiến phép dịch xảy ra ngoài ý định.
2. Một security rule **ALLOW ANY** đứng trước rule DENY mục tiêu trên nền tảng xử lý kiểu first-match, khiến từ chối không còn tác dụng.

Ví dụ minh họa:

~~~text
Mục đích:
Chỉ 198.51.100.0/24 -> 203.0.113.10 TCP/443 được phép.

Sai về mức quyền:
ALLOW ANY -> ANY TCP/443

Đúng về mục đích:
ALLOW source=198.51.100.0/24
      destination=service-mapped-by-DNAT
      tcp=443-original-or-8443-translated-according-to-platform
DENY các nguồn không được cấp quyền tới dịch vụ
~~~

Không thể chỉ đọc tên object firewall để kết luận phạm vi: object có thể đã gộp nhiều subnet/IP, hoặc địa chỉ được dùng ở bước khớp có thể là địa chỉ gốc hay đã dịch. Rà **effective policy**, thứ tự rule và dữ liệu phiên thực tế.

## 6. NAT kết hợp với các lớp phòng vệ

### 6.1. NAT và phân đoạn mạng

Phân đoạn thường sử dụng subnet/VLAN, zone, firewall hoặc chính sách workload để ngăn truy cập trái phép. NAT không làm cho những ranh giới này biến mất, nhưng có thể **che nguồn gốc hoặc thay đích nhìn thấy** ở một số điểm.

Ví dụ, tất cả workload trong vùng ứng dụng dùng chung địa chỉ SNAT đi ra. Firewall ở mạng đối tác chỉ nhìn thấy IP công khai đó, nên không thể biết chính xác workload nào đã khởi tạo kết nối chỉ dựa vào IP nguồn. Cần chính sách egress tại vùng ứng dụng và log NAT tại thiết bị dịch.

Ngược lại, DNAT công bố một server bên trong vùng DMZ có thể tạo đường kết nối qua biên. Nếu firewall cho phép từ mọi nguồn thay vì chỉ những bên được cấp quyền, chính sách phân đoạn bị nới rộng. **NAT rule và security rule cần được review như một thay đổi chung về đường tiếp cận**.

### 6.2. NAT và VPN có địa chỉ chồng lấp

Khi hai tổ chức cùng dùng **10.0.0.0/8** hoặc các subnet cụ thể bị trùng, một VPN site-to-site có thể không định tuyến chính xác tới IP phía đối tác. Một giải pháp là dùng **policy NAT/twice NAT** để ánh xạ mỗi bên sang một dải địa chỉ không trùng **trong phạm vi liên kết VPN**.

Ví dụ giả định:

~~~text
Công ty A: server thật 10.10.1.20
Địa chỉ A quảng bá/biểu diễn cho B: 172.20.1.20

Công ty B: server thật 10.10.1.20
Địa chỉ B quảng bá/biểu diễn cho A: 172.21.1.20

Ứng dụng tại A truy cập đối tác bằng 172.21.1.20.
Các gateway áp dụng dịch địa chỉ phù hợp theo chiều kết nối.
~~~

Các dải 172.20.0.0/16 và 172.21.0.0/16 ở đây được giả định chưa dùng bởi các mạng liên quan; cần **kiểm tra thực tế** trước khi chọn. Thiết kế còn phụ thuộc route, VPN traffic selector/encryption domain, firewall policy, DNS và thứ tự NAT so với xử lý IPsec. Đừng áp dụng một công thức dịch cố định cho mọi firewall hay VPN.

NAT giúp giải quyết trùng IP nhưng làm tăng độ phức tạp trong nhật ký, debug và nhận diện peer. Nếu có thể quy hoạch lại địa chỉ để tránh chồng lấp, đó có thể là giải pháp bền vững hơn về vận hành.

### 6.3. NAT, TLS, HTTP và reverse proxy

NAT ở tầng mạng/vận chuyển **không tự kết thúc TLS**. Nếu DNAT chuyển TCP/443 tới một server TLS, handshake và chứng chỉ vẫn được xử lý tại điểm kết thúc TLS của server hoặc proxy. Thay IP/port đích không tự sửa hostname yêu cầu trong TLS/HTTP.

Một reverse proxy có thể **kết thúc TLS và tạo kết nối mới** tới backend, vì vậy backend thường thấy IP của proxy làm nguồn; điều này **khác** với SNAT thuần túy dù hai hiện tượng có thể cùng xuất hiện. Header chuyển tiếp như **X-Forwarded-For** hoặc **Forwarded** chỉ được tin nếu do chuỗi proxy đáng tin thiết lập và đã loại bỏ/chuẩn hóa header do client tự cung cấp. Chúng không phải bằng chứng danh tính có thể thay thế token, mTLS hoặc authorization.

Nếu dịch cổng **443 → 8443**, backend vẫn có thể dùng HTTPS ở cổng 8443; cổng số không quyết định tự động giao thức đã được mã hóa. Cần cấu hình TLS và kiểm tra đúng đường từ client tới điểm kết thúc.

### 6.4. NAT, DNS và kết nối bằng tên miền

Một dịch vụ công khai có thể được phân giải sang IP DNAT, trong khi người dùng nội bộ có thể cần truy cập địa chỉ riêng qua split-horizon DNS. Thay đổi DNS, TTL, cache và bản ghi A/AAAA có thể làm kết nối đi qua **một đường NAT khác** hoặc bỏ qua NAT.

Một thay đổi firewall chỉ kiểm thử bằng IP trực tiếp có thể bỏ sót vấn đề hostname, SAN của chứng chỉ hoặc DNS trả địa chỉ không đúng. Khi xác minh, hãy kiểm tra:

- IP dịch vụ mà DNS trả cho **client ngoài** và **client nội bộ**.
- Vị trí/hướng hairpin và rule tương ứng nếu client nội bộ dùng địa chỉ công khai.
- Endpoint IPv4/IPv6 có cùng mức bảo vệ không.
- Ghi log truy vấn DNS theo nhu cầu, giới hạn quyền xem và thời hạn lưu để tránh tạo rủi ro thông tin riêng tư.

### 6.5. NAT và IDS/IPS, flow log

Nhiều cảm biến IDS/IPS và công cụ log chỉ nhìn thấy **một phía của quá trình dịch**. Sensor trước SNAT thấy IP client gốc; sensor sau SNAT thấy IP công khai. Cảm biến trước DNAT thấy đích công khai; sau DNAT thấy đích nội bộ.

Để tương quan sự kiện cần thu thập đúng điểm quan sát, thời gian, giao thức, port và ánh xạ NAT. Nếu một hệ thống giám sát gộp dữ liệu từ nhiều sensor mà không chuẩn hóa thông tin gốc/đã dịch, có thể xuất hiện cảnh báo trùng hoặc suy đoán sai host nguồn. Tránh lưu payload, token hay thông tin nhạy cảm quá mức trong log/packet capture.

## 7. NAT trên nền tảng cloud và môi trường hiện đại

### 7.1. NAT gateway cho luồng ra Internet

Nhiều hệ thống cloud cung cấp **managed NAT gateway** để workload ở vùng private khởi tạo kết nối tới dịch vụ bên ngoài mà không cần IP công khai riêng. Thông thường, NAT gateway xử lý dịch nguồn và trả lời của các phiên phù hợp, **không phải cổng công bố tùy ý dịch vụ nội bộ vào Internet**.

Việc có NAT gateway **không tự tạo quyền egress an toàn**: security group, network ACL, route table, cloud firewall, policy ứng dụng hoặc các điều kiện dịch vụ khác vẫn quyết định luồng được phép. Cần kiểm tra cơ chế của từng nhà cung cấp về giao thức, số kết nối, SNAT ports, IP egress, tính sẵn sàng và logging.

### 7.2. Cần phân biệt policy tại từng tầng cloud

| Điểm chính sách | Thông tin/đối tượng cần kiểm tra | Sai lầm thường gặp |
| --- | --- | --- |
| Subnet network ACL | Hướng inbound/outbound, IP/port tại điểm áp dụng, stateless/stateful | Chỉ mở chiều đi rồi quên đường về |
| Workload security group / NIC rule | Nguồn/đích và dịch vụ được phép theo ngữ nghĩa nhà cung cấp | Cho rằng NAT gateway thay thế quyền kết nối |
| NAT gateway / egress gateway | Ánh xạ nguồn, IP egress, timeout và số phiên | Dùng chung IP egress rồi không còn log quy nguồn |
| Cloud firewall | Rule, NAT rule, route, zone và thứ tự xử lý theo sản phẩm | Dùng nhầm IP pre-NAT hoặc post-NAT |
| Load balancer / proxy | Điểm kết thúc TLS, IP nguồn backend thấy, health check | Nhầm kết nối proxy mới với luồng NAT của client |
| Container / Kubernetes policy | Pod/namespace/label, ingress/egress, CNI enforcement | Nghĩ chính sách pod kiểm soát mọi traffic qua cloud NAT |

Ví dụ **AWS VPC Network ACL** là stateless ở phạm vi subnet, còn **AWS Security Group** là stateful và áp dụng theo đối tượng được hỗ trợ. Quy tắc của **Azure NSG**, **Google Cloud VPC firewall** và **Kubernetes NetworkPolicy** có ngữ nghĩa riêng. Không chuyển trực tiếp một ví dụ policy/NAT từ sản phẩm này sang sản phẩm khác mà không xác định lại điểm thực thi, địa chỉ được thấy và cách xử lý phản hồi.

### 7.3. Container và service discovery

Trong Kubernetes hoặc overlay network, các lớp mạng như **Service VIP, kube-proxy/eBPF, CNI, ingress gateway và cloud load balancer** có thể thực hiện chuyển hướng/ánh xạ lưu lượng. Pod IP thay đổi theo vòng đời container, còn Service IP hoặc identity/label có thể ổn định hơn.

Một security rule ở điểm khác nhau có thể thấy IP Service hoặc IP endpoint thực tế, tùy datapath và thời điểm dịch. Khi xây policy, cần tìm hiểu **effective datapath**, không mặc định rằng mọi policy luôn kiểm tra địa chỉ Service trước NAT hay địa chỉ pod sau NAT. Với network policy, xét cả egress pod nguồn và ingress pod đích nếu cả hai bên bị cô lập.

## 8. IPv6 và NAT: những điều dễ nhầm

IPv6 cung cấp không gian địa chỉ lớn; nhiều mạng IPv6 triển khai **định tuyến toàn cục cùng firewall stateful** mà không dùng NAT44 kiểu chia sẻ địa chỉ như IPv4. **Không dùng NAT không đồng nghĩa mọi host IPv6 được phép nhận kết nối từ Internet**: firewall vẫn có thể áp default deny inbound.

| Cơ chế | Mục tiêu | Lưu ý |
| --- | --- | --- |
| IPv4 NAT44/PAT | Dịch IPv4 sang IPv4, thường chia sẻ IP công khai | Log nguồn/port, cạn ánh xạ, DNAT và state |
| IPv6 routing + firewall | Kết nối IPv6 trực tiếp theo tuyến với policy | Phải lọc IPv6 riêng; IPv4 policy không tự bao phủ IPv6 |
| NPTv6 | Dịch **prefix** IPv6 theo mô hình phù hợp | Không phải NAT44/PAT chia sẻ nhiều host qua cổng |
| NAT66 | Dịch địa chỉ IPv6 sang IPv6 | Cần đánh giá kỹ nhu cầu, tính phức tạp và ảnh hưởng end-to-end |
| NAT64 (thường cùng DNS64) | IPv6-only client truy cập dịch vụ IPv4 | Kiểm tra phép dịch, DNS64 khi dùng, ứng dụng có nhúng địa chỉ và policy hai họ địa chỉ |

Một hostname có cả **A (IPv4)** và **AAAA (IPv6)** có thể khiến hai client hoặc hai lần kết nối sử dụng **đường đi khác nhau**. Vì vậy, siết DNAT/port forwarding IPv4 nhưng quên đường IPv6 có thể làm dịch vụ vẫn bị tiếp cận ngoài ý muốn. Cần kiểm tra cả hai address family và cả TCP/UDP theo nhu cầu.

Với IPv6, **ICMPv6** tham gia nhiều chức năng quan trọng như Neighbor Discovery và thông báo liên quan tới MTU; không chặn toàn bộ ICMPv6 một cách tùy tiện khi xây policy.

## 9. Phân tích rủi ro bảo mật khi kết hợp NAT và firewall

### 9.1. NAT không đồng nghĩa firewall

Địa chỉ riêng RFC 1918 thường không được định tuyến công khai trên Internet, và SNAT có thể làm host nội bộ không nhận được kết nối trực tiếp theo cách thông thường. Nhưng điều đó **không phải xác thực hay phân quyền**:

- Nếu firewall có rule mở rộng hoặc DNAT công bố dịch vụ, đối tượng bên ngoài có thể kết nối tới dịch vụ đó theo policy.
- Nếu máy bên trong khởi tạo kết nối độc hại, SNAT vẫn có thể chuyển lưu lượng ra Internet khi chính sách egress cho phép.
- Nếu dịch vụ có lỗ hổng ở tầng ứng dụng hoặc token bị đánh cắp, NAT không ngăn việc lạm dụng một kết nối đã được cho phép.
- Nếu bên trong mạng cùng segment, nhiều luồng không đi qua cổng NAT biên; việc ẩn IP ra Internet không giảm bề mặt di chuyển ngang nội bộ.

Vì thế, phải kết hợp **default deny, allowlist có chủ đích, phân đoạn, xác thực kết nối, TLS, phân quyền ứng dụng, giám sát và kiểm soát egress**.

### 9.2. Port forwarding làm mở rộng bề mặt tấn công

Một DNAT từ IP ngoài vào server nội bộ là **mở một đường truy cập mới** nếu security policy cho phép. Đánh giá:

1. Có thật sự cần công bố dịch vụ không, hay có thể dùng VPN/ZTNA hoặc reverse proxy được bảo vệ?
2. Đích DNAT đang thuộc DMZ hay có thể tới thẳng vùng dữ liệu?
3. Nguồn được cho phép đã giới hạn theo đối tác hoặc nhu cầu thực tế chưa?
4. Dịch vụ có TLS, chứng chỉ đúng, xác thực và authorization, rate limit và giám sát không?
5. Rule có owner, lý do, thời hạn/chu kỳ rà soát và cách thu hồi khi không còn cần?

Không dùng **UPnP hoặc cơ chế tự mở port không được kiểm soát** trên hệ thống quản trị nhạy cảm. Nếu môi trường cần cơ chế ánh xạ động, phải hạn chế quyền tạo mapping, theo dõi và gắn chính sách an ninh tương ứng.

### 9.3. Chia sẻ IP NAT gây khó quy trách nhiệm

Giả sử hai client nội bộ cùng dùng 203.0.113.20 làm địa chỉ nguồn ngoài:

~~~text
10.20.10.25:52340 -> 203.0.113.20:40001 -> 192.0.2.80:443 TCP
10.20.10.26:52340 -> 203.0.113.20:40002 -> 192.0.2.80:443 TCP
~~~

Server bên ngoài nhìn thấy cả hai phiên tới từ **203.0.113.20**. Một log chỉ có IP công khai mà thiếu **source port sau NAT, protocol, destination và timestamp** không đủ để phân biệt hai phiên này. Khi dùng CGNAT hoặc qua nhiều lớp NAT, có thể cần tương quan nhiều bảng ánh xạ.

Log NAT phục vụ điều tra nên ghi theo nhu cầu và chính sách quản trị:

| Trường | Ý nghĩa |
| --- | --- |
| Thời gian bắt đầu/kết thúc và timezone | Liên hệ sự kiện giữa nhiều hệ thống; đồng bộ thời gian là thiết yếu |
| Protocol | Phân biệt TCP, UDP và trường hợp giao thức khác |
| Original source IP:port | Xác định endpoint trước khi dịch |
| Translated source IP:port | Đối chiếu với log của hệ thống bên ngoài |
| Original/translated destination | Quan trọng khi có DNAT hoặc twice NAT |
| Rule/policy, device, interface/zone | Giải thích mapping phát sinh ở đâu và vì sao được phép |
| Session/flow identifier nếu có | Hỗ trợ ghép sự kiện nhiều hệ thống và xử lý trùng |

Cần bảo vệ **quyền xem/xuất log**, độ chính xác thời gian và thời hạn lưu. Log chứa IP/định danh kết nối có thể là dữ liệu nhạy cảm tùy ngữ cảnh; không thu thập payload hoặc credential chỉ để quy nguồn NAT.

### 9.4. Rủi ro availability từ số lượng mapping

NAT gateway có giới hạn tài nguyên. Một ứng dụng mở rất nhiều kết nối ra cùng một đích, không tái sử dụng connection hoặc có timeout không phù hợp có thể tạo **SNAT port exhaustion**. Dấu hiệu gồm kết nối ra ngoài lúc thành công lúc timeout, tăng số phiên, tăng lỗi connect hoặc tăng tỷ lệ mapping failure.

Các hướng giảm thiểu:

- Dùng connection pooling/keep-alive đúng cách khi giao thức hỗ trợ.
- Theo dõi số mapping, cổng khả dụng, kết nối tới từng đích, retransmission và timeout.
- Kiểm tra giới hạn của nền tảng, quy hoạch địa chỉ egress, độ sẵn sàng và cân bằng lưu lượng khi cần.
- Tránh mở rộng timeout cực lớn mà không đánh giá khả năng giữ state, và tránh timeout UDP quá ngắn làm gián đoạn ứng dụng.
- Đánh giá theo **đúng loại giao thức**: TCP có trạng thái khác UDP/QUIC.

Đây là rủi ro **tính sẵn sàng** liên quan thiết bị NAT; không chứng minh trực tiếp một hành vi tấn công. Cần phân biệt tải ứng dụng hợp lệ, lỗi cấu hình và lưu lượng bất thường bằng quan sát.

### 9.5. Mô hình đe dọa mẫu

| Đe dọa | Điều kiện | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| DNAT công bố nhầm DB | Mapping trỏ thẳng tới DB; security rule cho phép nguồn rộng | Tiếp cận cổng dữ liệu từ bên ngoài | Không công bố DB, DMZ/proxy, allowlist nguồn, quyền DB tối thiểu |
| API nội bộ có thể gửi dữ liệu ra endpoint bất kỳ | SNAT egress và policy outbound quá rộng | Nguy cơ rò rỉ dữ liệu qua kết nối hợp lệ | Egress filtering, identity workload, DLP/giám sát phù hợp |
| Log không xác định được host sau NAT | Nhiều host chia sẻ một IP; thiếu port/time | Điều tra sai đối tượng, khó xử lý sự cố | Translation log đầy đủ và đồng bộ thời gian |
| Rule chỉ lọc IP công khai trước DNAT nhưng downstream mở rộng | Policy ở tầng sau xét IP dịch mà không hạn chế nguồn phù hợp | Mở thêm đường truy cập ngoài phạm vi dự kiến | Xác định điểm pre/post NAT, rà effective policy mọi chặng |
| Cạn SNAT ports hoặc state table | Tải lớn, mapping tồn tại lâu, quy hoạch thiếu | Gián đoạn outbound | Theo dõi capacity, connection pooling, quy hoạch NAT |
| Địa chỉ chồng lấp qua VPN | Hai phía dùng cùng dải, NAT/routing hoặc traffic selector sai | Kết nối nhầm hệ thống hoặc thất bại | Thiết kế twice NAT, route, DNS và rule có thử nghiệm hai chiều |

Một threat record tốt phải ghi **tài sản**, **luồng nguồn–đích**, **điểm NAT**, **điểm thực thi policy**, **điều kiện**, **hậu quả**, **kiểm soát**, **owner** và **cách xác minh**. Việc chỉ ghi “bật NAT để an toàn” không đủ cho threat modeling.

## 10. Kiểm chứng NAT và firewall policy trong phòng lab

Chỉ thử trên hệ thống của bạn hoặc môi trường đã được phép quản trị. Dùng địa chỉ/hostname lab và **dữ liệu giả**, không lưu mật khẩu, session token hay thông tin khách hàng vào bản chụp gói hoặc ticket.

### 10.1. Các bước thực hành

**Bài A — SNAT outbound**

Thiết lập một client nội bộ, gateway NAT và server bên ngoài mô phỏng trong môi trường được kiểm soát.

1. Ghi 5-tuple gốc của kết nối TCP client → server: IP/port nguồn và IP/port đích.
2. Ghi 5-tuple được quan sát ở phía ngoài gateway; xác định IP/port nào đã thay đổi.
3. Đối chiếu mapping từ firewall log hoặc công cụ trạng thái mà quản trị viên được phép sử dụng.
4. Kiểm tra gói phản hồi đi qua gateway và được dịch về đúng endpoint nội bộ.
5. Thử một kết nối không thuộc allowlist để xác minh NAT tồn tại không đồng nghĩa gói được phép.

**Bài B — DNAT công bố web tại DMZ**

Đặt dịch vụ thử nghiệm có TLS hợp lệ ở máy DMZ. Cấu hình DNAT từ IP/cổng dịch vụ lab tới port backend được cho phép. Thử từ một máy trong nhóm được duyệt và một máy từ nguồn **không** được duyệt.

Kỳ vọng: client được duyệt kết nối đến đúng dịch vụ HTTPS; client ngoài danh sách bị policy chặn; database không có đường DNAT trực tiếp; hostname và chứng chỉ TLS vẫn khớp.

**Bài C — Tìm điểm policy đọc pre-NAT hay post-NAT**

Sử dụng công cụ mô phỏng policy hoặc hit counter của firewall:

1. Chọn một luồng test duy nhất với IP nguồn, IP đích và cổng xác định.
2. Ghi NAT rule và security rule dự kiến khớp.
3. Phát luồng test từ client được cấp quyền.
4. Đọc **rule hit/flow log** và thông tin session/NAT để xác nhận policy đã dùng địa chỉ gốc hay đã dịch.
5. Ghi kết luận vào tài liệu cấu hình thay vì suy đoán từ cú pháp mẫu trên Internet.

### 10.2. Lệnh minh họa quan sát

Trên Windows PowerShell, có thể kiểm tra kết nối TCP tới **IP lab thực tế**:

~~~powershell
Test-NetConnection -ComputerName 10.30.20.10 -Port 8443
Test-NetConnection -ComputerName 10.30.40.10 -Port 5432
~~~

Lưu ý các IP này nằm trong ví dụ; cần thay cho phù hợp với lab của bạn. Một kết quả TCP thành công chỉ chứng minh đường TCP tới cổng đích hoạt động tại thời điểm thử, **không xác nhận** policy đã siết đúng cho mọi nguồn.

Để thử HTTP và xác minh chứng chỉ qua hostname khi DNS chưa được cấu hình, có thể dùng curl với một IP thực của lab:

~~~bash
curl --resolve api.example.test:443:203.0.113.10 \
  --connect-timeout 5 --head https://api.example.test/
~~~

Địa chỉ 203.0.113.10 chỉ là **địa chỉ tài liệu**; câu lệnh cần thay bằng IP gateway thực sự trong lab và hostname/chứng chỉ phù hợp. Tham số **--resolve** đặt ánh xạ hostname cho kết nối thử; nó không tắt xác minh TLS. Không sử dụng tùy chọn bỏ qua xác minh chứng chỉ để che lỗi cấu hình.

Với hệ thống cho phép bắt gói, có thể quan sát cùng một luồng ở **interface trong và interface ngoài** để thấy phép dịch:

~~~bash
tcpdump -nn -i eth0 'tcp port 443'
~~~

Đổi tên interface và bộ lọc theo lab. Trên firewall chuyên dụng, dùng công cụ packet capture hoặc flow debug do nhà sản xuất hỗ trợ. Hãy bảo vệ các tệp capture vì chúng có thể chứa dữ liệu nhạy cảm.

### 10.3. Ma trận kiểm thử

| Test | Nguồn | Đích/luồng | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- | --- |
| T01 | Đối tác được cấp quyền | Public IP:443 → Proxy:8443 | ALLOW + DNAT đúng | NAT mapping, rule hit, TLS và HTTP hợp lệ |
| T02 | Nguồn Internet khác | Public IP:443 → Proxy:8443 | DENY | Rule deny/flow log tại điểm thực thi |
| T03 | Đối tác được cấp quyền | Public IP → DB:5432 | DENY | Không có mapping công bố DB, effective policy |
| T04 | Proxy DMZ | App API:8443 | ALLOW | TCP/TLS/ứng dụng đúng, rule hit |
| T05 | App API | Dịch vụ ngoài được phê duyệt TCP/443 | ALLOW + SNAT | Source mapping và phản hồi hợp lệ |
| T06 | App API | Endpoint ngoài không được duyệt | DENY | Egress rule hit và bằng chứng thử |
| T07 | Client nội bộ | Hostname công khai đi về dịch vụ nội bộ | Theo thiết kế hairpin hoặc split DNS | DNS, route, NAT mapping hai chiều |
| T08 | IPv6 client nếu có | AAAA của cùng dịch vụ | Theo policy IPv6 | Flow log/route IPv6, không phụ thuộc rule IPv4 |
| T09 | Client qua VPN | Đích có dải chồng lấp | Đúng IP sau policy NAT | Mapping hai phía, VPN selector, routing |
| T10 | Nhiều client nội bộ | Cùng đích ngoài qua shared SNAT | Kết nối đúng và quy nguồn được | NAT mapping gồm IP/port và timestamp |

Trong báo cáo test, ghi **thời điểm**, **nguồn/đích thực tế**, **giao thức/port**, **điểm quan sát**, **rule ID**, **kết quả dự kiến/thực tế**, **người kiểm tra** và **đường dẫn bằng chứng**.

## 11. Khắc phục sự cố liên quan NAT và firewall

### 11.1. Sơ đồ tìm lỗi theo lớp

~~~mermaid
flowchart TD
    A["Kết nối không đạt kỳ vọng"] --> B{"DNS / IP đích đúng?"}
    B -- "Không" --> B1["Kiểm tra A/AAAA, split DNS, cache"]
    B -- "Có" --> C{"Route và đường đi/về đúng?"}
    C -- "Không" --> C1["Kiểm tra next hop, VPN, hairpin, NAT return path"]
    C -- "Có" --> D{"NAT mapping đúng?"}
    D -- "Không" --> D1["Kiểm tra NAT rule, thứ tự, interface, IP/port"]
    D -- "Có" --> E{"Security policy đúng điểm pre/post NAT?"}
    E -- "Không" --> E1["Xem rule hit, zone, direction, ACL/SG/firewall"]
    E -- "Có" --> F{"State/cổng dịch/timeout ổn?"}
    F -- "Không" --> F1["Kiểm tra state table, ephemeral ports, SNAT capacity"]
    F -- "Có" --> G{"TLS / ứng dụng / quyền đúng?"}
    G -- "Không" --> G1["Kiểm tra listener, hostname, certificate, authorization"]
    G -- "Có" --> H["Đối chiếu gói, phiên và log hai phía"]
~~~

### 11.2. Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Điều cần kiểm tra |
| --- | --- | --- |
| DNAT đã tạo nhưng không truy cập được dịch vụ | Security policy không cho phép; sai public IP/port; route không tới backend | Pre/post NAT, rule hit, listening port, đường về |
| Chỉ một số client truy cập được | Allowlist nguồn, ISP/đường đi, IPv4/IPv6, NAT ở phía client | Source thật tại firewall, A/AAAA, log |
| Gói tới backend nhưng response không về | Default gateway của backend sai; asymmetric routing; NAT state bị mất | Đường trả lời, bảng phiên và thiết bị HA |
| Client nội bộ dùng hostname công khai bị timeout | Hairpin NAT thiếu hoặc DNS nội bộ chưa phù hợp | Split DNS, đường loopback, SNAT nếu cần |
| Lúc đầu kết nối tốt rồi gián đoạn | State timeout, NAT port exhaustion, tài nguyên gateway quá tải | Session count, port use, timeout theo protocol |
| Server đối tác chặn traffic dù client nội bộ được phép | IP egress sau SNAT khác allowlist đối tác | IP ngoài thực tế, SNAT pool, dự phòng/đa vùng |
| Log phía đối tác chỉ thấy một IP NAT | Nhiều client chia sẻ IP, thiếu log dịch port | Translation log và timestamp |
| Firewall cho phép TCP/443 nhưng HTTP/3 thất bại | QUIC dùng UDP/443 | UDP policy, proxy/CDN, firewall và hỗ trợ HTTP/3 |
| API trả HTTP 403 sau khi kết nối TCP được | Application authorization hoặc proxy policy | Identity, token, quyền ứng dụng; không tự kết luận NAT lỗi |
| IPv4 được bảo vệ nhưng IPv6 vẫn vào được | IPv6 path khác, policy IPv6 thiếu | AAAA, route, IPv6 firewall/SG |
| VPN thiết lập thành công nhưng ứng dụng sai đích | Trùng IP, translation/route, selector không khớp | Mạng thật/ảo, VPN policy NAT, DNS và log cả hai phía |

### 11.3. Phương pháp điều tra hai đầu

Khi nghi ngờ NAT:

1. **Ghi 5-tuple nguyên gốc** từ client, bao gồm cổng nguồn nếu có.
2. **Xác định đường đi**: interface/zone vào, gateway, bảng định tuyến, NAT gateway, proxy và các điểm policy trung gian.
3. **So sánh địa chỉ ở từng chặng** với bảng NAT/conntrack, flow log hoặc capture được cho phép.
4. **Xác minh rule quyết định** trên đúng điểm: security policy, NAT rule, network ACL, cloud security group và host firewall nếu có.
5. **Theo dõi chiều trả lời**; kiểm tra stateful session, DNAT/SNAT reverse mapping và đường bất đối xứng.
6. **Kiểm tra tầng trên**: listener, TLS, DNS, HTTP response và quyền ứng dụng.
7. **Đóng kết luận bằng bằng chứng**, rồi sửa thay đổi nhỏ nhất đáp ứng luồng hợp lệ và kiểm thử lại cả trường hợp phải bị chặn.

Nếu thiết bị có nhiều chế độ xử lý như transparent/route-based VPN, policy-based VPN, inspection path hoặc offload, thông tin quan sát tại một interface có thể chưa phản ánh toàn bộ xử lý. Dùng tài liệu vendor và công cụ kiểm tra effective datapath để tránh kết luận sai.

## 12. Quản trị thay đổi NAT và policy trong vận hành

### 12.1. Một bản ghi thay đổi có thể kiểm toán

| Trường | Ví dụ minh họa |
| --- | --- |
| NAT Rule ID | NAT-PARTNER-009 |
| Security Rule ID | FW-PARTNER-HTTPS-009 |
| Mục đích | Cho phép đối tác gọi API qua gateway DMZ |
| Nguồn được duyệt | 198.51.100.0/24 |
| Original destination | 203.0.113.10:443/TCP |
| Translated destination | 10.30.20.10:8443/TCP |
| Điểm thực thi và điều kiện khớp | Ghi rõ zone/interface và pre/post NAT theo nền tảng |
| Owner, ticket và thời hạn | Đơn vị vận hành, lý do nghiệp vụ, hạn review |
| Bằng chứng kiểm thử | Cho phép đối tác; chặn nguồn khác; TLS đúng |
| Log và monitoring | NAT translation, security rule hit và cảnh báo khác thường |
| Rollback | Hoàn tác chính xác NAT rule/security rule liên quan, kiểm thử lại |

### 12.2. Quy trình an toàn

1. **Khảo sát hiện trạng:** kiểm kê NAT rule, security rule, object địa chỉ, subnet, port, route và dịch vụ đang dùng.
2. **Mô tả ý định:** ai được kết nối với ai, giao thức, cổng, điều kiện xác thực và phạm vi thời gian.
3. **Xác nhận điểm khớp:** phân biệt original/translated IP và port, hướng, zone, thứ tự NAT/rule.
4. **Đánh giá rủi ro:** liệu ánh xạ có mở thêm bề mặt công khai, tạo đường vòng phân đoạn, che danh tính source hoặc ảnh hưởng HA/capacity không?
5. **Chuẩn bị kiểm chứng và rollback:** test allow, deny, chiều trả lời, TLS, IPv6, log, tải/timeout; lưu cấu hình trước thay đổi.
6. **Triển khai có kiểm soát:** theo quy trình tổ chức, có owner và cửa sổ thay đổi khi cần.
7. **Theo dõi sau triển khai:** rule hit, packet drop, mapping errors, state table, hiệu năng và telemetry ứng dụng.
8. **Rà soát định kỳ:** xóa mapping không còn nhu cầu, thu hẹp rule quá rộng, cập nhật IP đối tác/egress và xử lý ngoại lệ hết hạn.

Khi muốn sửa lỗi bằng cách chuyển sang **ALLOW ANY** hoặc tắt kiểm tra TLS, cần tiếp tục điều tra nguyên nhân thay vì chấp nhận quy tắc rộng. Mỗi thay đổi phải bảo toàn **những luồng cần chặn**, không chỉ làm cho một phép thử kết nối thành công.

## 13. Tình huống ứng dụng

### Tình huống A — Partner API mở nhầm cho toàn Internet

Một doanh nghiệp DNAT 203.0.113.10:443 về 10.30.20.10:8443. Người vận hành cấu hình ALLOW nguồn ANY vì nghĩ “NAT đã che IP nội bộ”.

**Phân tích:** NAT đưa mọi gói đúng đích/cổng tới backend theo mapping; allow rộng làm nhiều client có thể tiếp cận dịch vụ. Sửa security rule theo nguồn đối tác được duyệt, giới hạn port, bật TLS và xác thực ứng dụng, đồng thời kiểm tra từ nguồn được cấp quyền và nguồn không được cấp quyền.

### Tình huống B — Công cụ giám sát không xác định được client sau SNAT

Nhiều pod cùng đi qua một egress NAT gateway; hệ thống đích bên ngoài ghi nhận chỉ một IP công khai. Một request đáng ngờ cần xác định nguồn nhưng log NAT không có port và thời điểm chính xác.

**Phân tích:** IP ngoài không đủ quy nguồn. Cần telemetry tại nguồn, log NAT có IP/port gốc và dịch, giao thức, thời gian, session ID nếu có; cân nhắc tách egress theo workload nhạy cảm khi kiến trúc hỗ trợ. Quyền truy cập log phải được kiểm soát.

### Tình huống C — Firewall được phép nhưng dịch vụ TLS vẫn báo lỗi

Quy tắc DNAT 443 → 8443 hoạt động, client kết nối TCP được nhưng trình duyệt báo chứng chỉ sai hostname.

**Phân tích:** DNAT không thay hostname mà client dùng để xác minh chứng chỉ. Kiểm tra chứng chỉ ở điểm kết thúc TLS, SAN, SNI, cấu hình reverse proxy và DNS. Đừng tắt xác minh chứng chỉ; lỗi xảy ra sau khi đường mạng đã hoạt động.

### Tình huống D — Kết nối VPN dùng sai hệ thống vì trùng địa chỉ

Hai công ty đều dùng 10.10.1.0/24. VPN hoạt động nhưng request gửi tới một server cùng IP của mạng nội bộ thay vì tới đối tác.

**Phân tích:** cần kiểm tra route, policy NAT/twice NAT, selectors và split DNS; tạo dải đại diện không trùng nhau nếu cần rồi kiểm thử kết nối ở cả hai đầu. Rule firewall phải tham chiếu đúng địa chỉ gốc/đã dịch theo vị trí, không chỉ mở thêm route hay cổng.

### Tình huống E — DNS trả AAAA khiến thay đổi NAT44 không đủ

Ứng dụng có cả IPv4 và IPv6. Nhóm hạ tầng chặn truy cập ngoài qua DNAT IPv4 nhưng vẫn thấy truy cập trực tiếp tới địa chỉ IPv6 của backend.

**Phân tích:** NAT44 không kiểm soát đường IPv6. Kiểm tra bản ghi DNS, IPv6 routing và firewall policy IPv6; định nghĩa yêu cầu công bố ứng dụng cho cả IPv4/IPv6 rồi kiểm thử theo từng giao thức.

## 14. Câu hỏi ôn tập

**Câu 1.** Một rule SNAT biến nguồn 10.20.10.25 thành 203.0.113.20. Firewall ở phía dịch vụ đối tác sẽ thấy nguồn nào?

*Gợi ý:* Thường là 203.0.113.20 ở phía sau phép SNAT. Điểm lọc nằm trước NAT có thể vẫn thấy địa chỉ gốc; phải xác định vị trí.

**Câu 2.** Nếu đã tạo DNAT 203.0.113.10:443 tới 10.30.20.10:8443 thì mọi client ngoài đều được phép truy cập chưa?

*Gợi ý:* Chưa thể kết luận. NAT tạo ánh xạ; security policy, routing, trạng thái phiên và bảo vệ tại dịch vụ vẫn quyết định kết quả.

**Câu 3.** Có thể khẳng định mọi firewall đều yêu cầu rule bằng địa chỉ IP trước DNAT không?

*Gợi ý:* Không. Ngữ nghĩa phụ thuộc sản phẩm và điểm thực thi. Xác minh tài liệu, packet path và rule hit.

**Câu 4.** Vì sao hai client dùng chung địa chỉ SNAT vẫn có thể được phân biệt?

*Gợi ý:* Port mapping, giao thức, IP/port đích và thời gian giúp ánh xạ phiên về nguồn tương ứng, nếu log đầy đủ.

**Câu 5.** Khi client nội bộ gọi tên miền công khai của máy chủ nội bộ bị lỗi, cần kiểm tra gì?

*Gợi ý:* Hairpin NAT, SNAT bổ sung nếu cần, split DNS, định tuyến chiều phản hồi và policy tại các điểm thực thi.

**Câu 6.** NAT gateway đã xử lý egress thì có cần allowlist, TLS hoặc phân quyền ứng dụng không?

*Gợi ý:* Vẫn cần. NAT không tự ngăn dữ liệu được gửi tới endpoint không được duyệt, không mã hóa và không xác thực người dùng.

**Câu 7.** Trong dual stack IPv4/IPv6, việc chặn một mapping DNAT IPv4 có đủ bảo vệ dịch vụ không?

*Gợi ý:* Không nếu IPv6 có đường truy cập khác. Cần kiểm tra A/AAAA, IPv6 firewall và dịch vụ đang lắng nghe.

## 15. Bài tập thiết kế tổng hợp

Thiết kế chính sách cho một doanh nghiệp có **Internet, đối tác VPN, DMZ reverse proxy, API nội bộ, database, DNS resolver, egress NAT gateway** và **mạng quản trị**. Dải địa chỉ có thể là dải lab được kiểm soát; không dùng thông tin tài khoản hay địa chỉ thực của doanh nghiệp.

Yêu cầu nộp:

1. **Sơ đồ mạng và trust boundary**: đánh dấu NAT gateway, firewall, điểm kết thúc TLS, đường VPN và chặng proxy → API.
2. **Ma trận tối thiểu 10 luồng**: ghi source, destination, protocol/port, ingress/egress, allow/deny và lý do nghiệp vụ.
3. **Ba phép dịch NAT**: ít nhất một SNAT/PAT, một DNAT/port forwarding và một trường hợp hairpin hoặc twice NAT; biểu diễn 5-tuple trước và sau.
4. **Policy theo điểm thực thi**: với mỗi rule cần chỉ ra đó là pre-NAT hay post-NAT theo nền tảng giả định, điểm nhìn IP/port và cách quản lý phản hồi.
5. **Bộ kiểm thử**: ít nhất 5 trường hợp phải thành công và 5 trường hợp phải bị chặn; ghi cách đọc log/counter/mapping và chứng chỉ nếu có HTTPS.
6. **Threat model**: phân tích nguy cơ mở rộng bề mặt công khai, che nguồn do shared SNAT, trùng địa chỉ VPN, cạn SNAT ports và đường IPv6 bỏ sót.
7. **Kế hoạch vận hành**: owner, rà soát rule, thời hạn ngoại lệ, backup, rollback, cảnh báo và khả năng quy nguồn khi điều tra.

**Tiêu chí đánh giá:** mô hình hóa đúng địa chỉ/cổng trước–sau NAT; không đánh đồng NAT với quyền truy cập; rule có nguồn/đích hẹp và được kiểm chứng; không bỏ qua chiều phản hồi, DNS, TLS, VPN, IPv6 và logging.

## 16. Ghi nhớ

- **SNAT đổi nguồn**, **DNAT đổi đích**; **PAT/NAPT** cho phép thay cổng để phân biệt nhiều luồng dùng chung địa chỉ.
- Đánh giá firewall rule phải biết **địa chỉ/cổng trước NAT hay sau NAT**, vị trí policy, thứ tự xử lý và ngữ nghĩa của chính nền tảng đó.
- **NAT mapping, routing và security policy là ba chức năng khác nhau**; NAT không xác thực, không mã hóa và không thay cho default deny hoặc authorization tại ứng dụng.
- **Stateful session và đường trả lời** quyết định khả năng hoạt động của nhiều phép dịch. Với stateless ACL, phải phân tích riêng từng hướng.
- **VPN có địa chỉ trùng, hairpin NAT, cloud NAT gateway, container datapath và IPv6** làm thay đổi góc nhìn source/destination, cần kiểm thử trên đường đi thật.
- Log NAT muốn quy nguồn phải đủ **IP/port gốc và đã dịch, protocol, thời gian và điểm thực thi**, đồng thời được bảo vệ thích hợp.
- Thiết kế có trách nhiệm gồm **ma trận luồng, NAT rule và security rule cùng được review, test allow/deny, giám sát, owner và phương án rollback**.
