# Rule ordering: thứ tự xử lý quy tắc trên firewall

**Rule ordering (thứ tự quy tắc)** là cách sắp xếp và đánh giá các điều kiện cho phép, từ chối hoặc xử lý lưu lượng trên firewall. Trong nhiều firewall và ACL truyền thống, khi một gói khớp **quy tắc đầu tiên theo thứ tự xét**, thiết bị thực hiện hành động của quy tắc đó và dừng tìm trong danh sách tương ứng. Vì thế, **cùng một tập rule nhưng đổi vị trí có thể tạo ra chính sách khác hẳn**: dịch vụ hợp lệ bị chặn hoặc đường truy cập đáng lẽ bị cấm lại được mở.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, hiểu rule ordering giúp thiết kế phân đoạn mạng, firewall và VPN, giám sát IDS/IPS, bảo vệ DNS, truy cập Wi-Fi và mạng cloud. Khi mô hình hóa mối đe dọa hoặc điều tra sự cố, câu hỏi quan trọng không chỉ là “có rule deny hay không?” mà còn là **“gói tin có thực sự đi tới rule deny đó không, và trước đó có rule nào đã quyết định kết quả?”**

> **Phạm vi:** Bài dùng mô hình **first-match** làm nền tảng vì dễ hiểu và phổ biến trong nhiều ACL/firewall. Không phải mọi nền tảng đều dùng cách này: một số cơ chế dùng tập rule cộng gộp, có chuỗi ưu tiên riêng hoặc nhiều giai đoạn xử lý. Muốn kết luận chính xác, phải kiểm tra ngữ nghĩa, phạm vi và thứ tự thực thi **của chính nền tảng đang vận hành**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô phỏng cách đánh giá rule **từ trên xuống** trong một danh sách áp dụng first-match.
2. Phân biệt **explicit allow/deny**, **implicit deny**, **drop/reject**, và trường hợp **không khớp rule**.
3. Nhận diện **shadowing, redundancy, overlap, rule conflict** và ngoại lệ được đặt sai vị trí.
4. Phân tích tương tác của **stateful inspection, NAT, zone, hướng lưu lượng và IPv4/IPv6** với rule ordering.
5. Thiết kế, kiểm thử và quản lý thay đổi rule theo **quyền tối thiểu** và ma trận truy cập mong muốn.
6. Đọc log, counter, thông tin phiên và đường định tuyến để giải thích vì sao một gói được cho phép hoặc bị chặn.

## 2. Firewall quyết định dựa trên những thông tin nào?

Một rule có thể chứa nhiều trường, tùy thiết bị:

| Trường điều kiện | Ví dụ | Điều cần lưu ý |
|---|---|---|
| Source zone/interface | Employee, Guest, WAN, VPN | Một IP có thể tới từ nhiều đường; phải kiểm tra nguồn thực sự được gán zone nào |
| Destination zone/interface | Application, Database, Management | Có thể phụ thuộc định tuyến; một số thiết bị chọn zone trước hoặc sau bước NAT |
| IP nguồn/đích | 10.10.10.0/24 → 10.20.20.10 | Phải biết rule kiểm tra địa chỉ **trước hay sau NAT** |
| Giao thức | TCP, UDP, ICMP, ICMPv6 | Không thể gộp mọi giao thức thành TCP/UDP port |
| Cổng/dịch vụ | TCP/443, UDP/53, TCP/22 | Cổng nguồn tạm thường thay đổi; rule rộng theo cổng nguồn dễ gây lỗi |
| Trạng thái phiên | NEW, ESTABLISHED, RELATED | Chỉ áp dụng theo cơ chế connection tracking của nền tảng |
| Danh tính/nhóm | Role nhân viên, tài khoản VPN, nhóm workload | Tùy khả năng xác thực và mapping của hệ thống |
| Thời gian/ứng dụng | Giờ làm việc, ứng dụng được nhận diện | Phụ thuộc khả năng kiểm tra tầng cao, độ tin cậy và trạng thái dịch vụ |
| Hành động | Allow, Drop/Deny, Reject, Log, Inspect | Không phải mọi hành động đều dừng việc xét rule ngay lập tức |

Một rule chỉ có ý nghĩa khi hiểu **nó được áp vào loại lưu lượng nào**: lưu lượng chuyển tiếp, lưu lượng đi vào chính firewall, lưu lượng do firewall phát ra, chiều vào/ra, một security zone hoặc một policy package cụ thể.

### Luồng xử lý khái quát của firewall first-match

~~~text
Gói đến điểm kiểm tra
          │
          ▼
Xác định interface/zone, route và ngữ cảnh
          │
          ▼
Các bước xử lý nền tảng (ví dụ: state, NAT)
          │
          ▼
Xét các rule có hiệu lực theo thứ tự
          │
          ├── Rule 1 khớp?  Có ──> hành động Rule 1
          │                    Không
          ▼
     Rule 2 khớp?  Có ──> hành động Rule 2
          │          Không
          ▼
     Rule 3 khớp?  Có ──> hành động Rule 3
          │          Không
          ▼
     ...
          │
          ▼
Chính sách mặc định nếu không có rule khớp
~~~

**Đây là mô hình học thuật**, không phải pipeline cố định của mọi thiết bị. Một số firewall đánh giá route, DNAT, security policy, SNAT hoặc xác thực ở những giai đoạn khác nhau. Trong hệ thống có nhiều chain/hook, “ACCEPT ở chain này” chưa chắc kết thúc mọi bước lọc khác.

## 3. First-match: thứ tự có thể đảo ngược quyết định

Giả sử firewall xử lý một danh sách rule theo **top-down, first-match**, gói được xét:

~~~text
Nguồn: 10.10.10.25
Đích:  10.20.20.10
TCP destination port: 443
State: NEW
~~~

Danh sách minh họa:

| Vị trí | Source | Destination | Service | Action |
|---|---|---|---|---|
| 10 | 10.10.10.0/24 | 10.20.20.10 | TCP/443 | **Allow** |
| 20 | 10.10.10.0/24 | 10.20.20.0/24 | Any | Deny |
| 90 | Any | Any | Any | Deny |

Gói khớp rule **10**, được **Allow** và không tới rule 20. Nếu hoán đổi rule 10 và 20, rule có destination **10.20.20.0/24 + service Any** sẽ khớp trước và **Deny** gói, dù rule Allow cụ thể vẫn tồn tại ở phía dưới.

Điểm cần nhớ: **thứ tự không tự động tính theo độ cụ thể**. Với một danh sách first-match, thiết bị thường không tự đưa rule có subnet nhỏ nhất lên trước chỉ vì rule đó “chi tiết hơn”. Độ ưu tiên thực tế phải được xác định bằng cách sắp xếp hoặc cơ chế priority đã cấu hình.

### Khi nào quy tắc tổng quát nên đứng cuối?

Thông thường, ta muốn **ngoại lệ có chủ đích** được xét trước một quy tắc bao phủ rộng hơn. Ví dụ, cho phép nhóm quản trị tới một jump host bằng TCP/22 rồi từ chối những truy cập SSH khác trong cùng phạm vi. Nhưng **không thể biến điều này thành quy luật “mọi allow phải đứng trước mọi deny”**: một deny đặc biệt có thể cần được xét trước một allow rộng để chặn một đích có rủi ro cao. Mục đích là **thể hiện chính sách mong muốn mà không để rule trước che khuất rule sau**.

## 4. Các dạng lỗi do thứ tự quy tắc

### 4.1. Shadowing: rule phía dưới không bao giờ được dùng

**Rule shadowing** xảy ra khi một hoặc nhiều rule đứng trước đã bao phủ toàn bộ tập lưu lượng mà một rule phía sau có thể khớp, làm rule sau không còn khả năng quyết định lưu lượng trong cùng phạm vi.

~~~text
10  ALLOW  source=10.10.0.0/16  destination=10.30.30.0/24  service=ANY
20  DENY   source=10.10.50.0/24 destination=10.30.30.0/24 service=TCP/5432
~~~

Trong một danh sách first-match áp dụng cho cùng zone/hướng, mọi gói thuộc rule 20 cũng khớp rule 10. **Rule 20 bị shadow hoàn toàn**; nó không thể chặn TCP/5432 từ subnet 10.10.50.0/24 như người viết mong đợi.

Giải pháp phải dựa vào mục tiêu: nếu subnet 10.10.50.0/24 cần bị từ chối, đặt một rule **Deny hẹp** phía trên rule Allow rộng, hoặc tốt hơn **thu hẹp rule Allow** để không bao phủ subnet/đích không được cấp quyền.

### 4.2. Overlap: hai rule cùng khớp một phần lưu lượng

**Overlap** là khi hai rule có giao nhau nhưng mỗi rule vẫn có một phần lưu lượng riêng. Ví dụ:

~~~text
10  ALLOW  source=10.10.0.0/16   dest=10.20.20.0/24  TCP/443
20  DENY   source=10.10.50.0/24  dest=10.20.0.0/16   ANY
~~~

Gói từ **10.10.50.25** tới **10.20.20.10:443** khớp cả hai; rule 10 thắng nếu xử lý first-match. Nhưng gói tới **10.20.30.10:22** không khớp rule 10, nên có thể bị rule 20 chặn. Như vậy rule 20 chỉ **bị che một phần**.

Để rà soát overlap, không chỉ nhìn tên rule: cần giao nhau đồng thời về **source, destination, service, zone, hướng, lịch áp dụng và điều kiện khác**.

### 4.3. Redundancy: rule trùng tác dụng

**Redundancy** là các rule có hành động giống nhau và phạm vi trùng hoặc được bao phủ, khiến một rule không bổ sung quyết định mới. Ví dụ:

~~~text
10  DENY  source=Guest  dest=Database  ANY
20  DENY  source=Guest  dest=Database  TCP/5432
~~~

Với điều kiện và phạm vi bằng nhau ngoài service, rule 20 có thể không bao giờ được thực thi. Dù hai rule cùng Deny, rule 20 vẫn có thể tồn tại vì **mục đích logging, mô tả kiểm toán hoặc yêu cầu vận hành**. Không nên xóa chỉ dựa trên giả định trùng lặp; phải kiểm tra hành động log, counter, schedule, điều kiện ẩn và quy trình thay đổi.

### 4.4. Conflict và các ngoại lệ sai chỗ

Hai rule **conflict** khi vùng giao nhau có hành động khác nhau: Allow và Deny. Một rule cho phép chung cả subnet có thể vô tình mở máy chủ bị cấm; một Deny quá rộng có thể làm ngoại lệ HTTPS cụ thể không bao giờ được xét.

Đừng mặc định rule có tên **“Critical Deny”** luôn được ưu tiên. Trong danh sách first-match, **vị trí thực và phạm vi áp dụng** mới là yếu tố quyết định. Một rule có tag quan trọng nhưng đứng dưới rule Allow bao phủ vẫn có thể mất tác dụng.

## 5. Explicit deny, implicit deny, drop và reject

**Explicit deny** là rule được tạo rõ ràng với hành động từ chối. **Implicit deny** là hành vi mặc định khi không có rule phù hợp trong một chính sách mặc định từ chối. Cả hai có thể chặn lưu lượng, nhưng khác nhau về **vị trí đánh giá, khả năng đặt log và cách hiển thị của thiết bị**.

| Cơ chế | Ý nghĩa | Vấn đề cần quan sát |
|---|---|---|
| Explicit Deny | Một rule cụ thể từ chối tập lưu lượng khớp điều kiện | Rule có bị rule trước che không? Có bật log? |
| Implicit Deny / Default Drop | Từ chối khi không có rule cấp phép trong policy hiện hành | Có log hay không tùy nền tảng; có thể khó truy nguyên nếu không cấu hình giám sát |
| Drop | Bỏ gói, thường không gửi phản hồi từ chính firewall | Client có thể timeout; timeout không tự chứng minh firewall drop |
| Reject | Từ chối và có thể trả một thông báo lỗi phù hợp giao thức | Thay đổi dấu hiệu quan sát, không nhất thiết giống trên mọi hệ thống |
| Allow/Accept | Cho phép gói/luồng tại điểm kiểm tra tương ứng | Có thể còn các lớp/hook/policy phía sau; không đồng nghĩa ứng dụng chấp nhận |

Ví dụ, một rule cuối dạng **Deny Any → Any** có thể giúp ghi log các kết nối ngoài danh mục cho phép. Nếu nền tảng đã có implicit deny và không yêu cầu log phân loại riêng, rule cuối có thể mang ý nghĩa vận hành khác. Cần chọn theo chính sách và khả năng của nền tảng.

**Bẫy vận hành:** Đưa rule “Deny Any → Any” lên vị trí đầu trong một chain first-match sẽ chặn cả các Allow phía dưới. Đưa “Allow Any → Any” lên đầu có thể vô hiệu hóa mọi Deny cụ thể phía sau.

## 6. Statefulness ảnh hưởng đến thứ tự như thế nào?

Firewall **stateful** lưu trạng thái các trao đổi mạng, ví dụ kết nối TCP được khởi tạo theo quy tắc Allow. Nhiều nền tảng dùng chính sách dành cho lưu lượng **đã thuộc một phiên được chấp nhận**, tách khỏi chính sách dành cho **kết nối mới**.

Một mô hình Linux conntrack thường gặp:

~~~text
1. Drop gói ct state INVALID theo chính sách.
2. Accept gói ct state ESTABLISHED,RELATED.
3. Với ct state NEW: duyệt allowlist nguồn/đích/dịch vụ.
4. Không có rule phù hợp: Drop theo mặc định.
~~~

**Lưu ý:** Đây là cách thiết kế mẫu, không phải quy tắc bắt buộc của mọi firewall. Một thiết bị có thể tái đánh giá policy trong phiên, cho phép điều khiển trạng thái bằng tính năng riêng hoặc duy trì các phiên đang có khi rule thay đổi. Phải biết **nhãn trạng thái** và **thứ tự xử lý policy** của hệ thống đang dùng.

### Ví dụ về phiên đã tồn tại

Giả sử trước 10:00, firewall cho phép Employee → API TCP/443 và một phiên TCP được tạo. Đến 10:00, người quản trị thêm rule Deny Employee → API mới ở vị trí cao hơn. **Một số firewall vẫn cho phiên cũ tiếp tục** cho tới khi nó đóng, timeout hoặc trạng thái bị xóa/thu hồi. Những **kết nối NEW** sau thay đổi có thể đã bị từ chối.

Vì vậy, khi xác minh rule mới, phải thử **một phiên mới thực sự** và đối chiếu state/session. Nếu cần chấm dứt ngay phiên cũ do sự cố, đội vận hành có thể phải áp dụng chức năng thu hồi/clear session theo quy trình; hành động này có thể làm gián đoạn dịch vụ.

### “ESTABLISHED” không phải một ngoại lệ cho mọi luồng

Cho phép **ESTABLISHED/RELATED** trong chain đúng chỗ **không tương đương** với Allow Any → Any cho mọi kết nối mới. Tuy nhiên, nếu policy đã cho phép NEW quá rộng, state table sẽ hợp thức hóa phản hồi cho các luồng mới đó. Vì thế cần đặc biệt thận trọng với **quy tắc tạo phiên mới**.

## 7. NAT và rule ordering: nên kiểm tra địa chỉ trước hay sau dịch?

**Network Address Translation (NAT)** có thể dịch đích (DNAT), dịch nguồn (SNAT/PAT) hoặc cả hai. Firewall security policy có thể kiểm tra địa chỉ ở giai đoạn **trước NAT** hoặc **sau NAT**, tùy kiến trúc và sản phẩm.

Ví dụ có một dịch vụ HTTPS nội bộ:

~~~text
Client ngoài mạng:  198.51.100.25:52000
IP công khai VIP:   203.0.113.10:443
Ứng dụng thực:      10.20.20.10:443

Client -> 203.0.113.10:443
             |
        [DNAT / Firewall]
             |
          10.20.20.10:443
~~~

Các địa chỉ **198.51.100.0/24** và **203.0.113.0/24** là dải ví dụ dành cho tài liệu. Nếu một firewall chọn security rule theo **IP đích gốc**, rule phù hợp có thể nhắm tới **203.0.113.10**. Nếu hệ thống xét theo **IP đích sau DNAT**, rule có thể cần nhắm tới **10.20.20.10**. Không thể chỉ suy từ sơ đồ để biết giá trị nào được so khớp.

Khi rà soát:

1. Xác định pipeline của thiết bị: route lookup, DNAT, security policy và SNAT diễn ra theo thứ tự nào trong ngữ cảnh đang xét.
2. Xác định các object IP/zone nào thực sự xuất hiện trong bộ so khớp của rule.
3. Đối chiếu log và packet capture trước/sau NAT khi được phép.
4. Kiểm tra liệu rule rộng dành cho VIP có làm lộ các backend khác ngoài phạm vi thiết kế không.
5. Kiểm tra hairpin NAT, VPN, proxy và IPv6 theo sơ đồ thực tế.

**NAT không thay thế kiểm soát truy cập.** DNAT công bố đường vào dịch vụ; firewall vẫn phải giới hạn nguồn, đích, cổng và ngữ cảnh phù hợp.

## 8. Rule ordering giữa nhiều chain, policy và thiết bị

Một gói có thể đi qua **nhiều điểm kiểm tra**: switch ACL, firewall giữa VLAN, host firewall, firewall VPN hoặc security group cloud. Thứ tự trong **một danh sách** chỉ giải thích một phần kết quả.

~~~text
   Client VLAN
       |
   [Switch ACL]      Rule có thể chặn trước khi tới firewall
       |
   [L3 Firewall]     Policy zone + state + NAT
       |
   [Host Firewall]   Policy áp tại chính máy chủ
       |
   [Ứng dụng]        Xác thực/ủy quyền riêng
~~~

Nếu switch ACL đã chặn gói, counter của firewall phía sau có thể không tăng. Ngược lại, firewall Allow gói nhưng ứng dụng trả HTTP 403 thì đó có thể là **từ chối của ứng dụng**, không phải lỗi rule ordering ở tầng mạng.

### 8.1. iptables/nftables và nhiều chain

Trên Linux, rule có thể nằm trong các **chain** tương ứng với traffic vào máy, ra máy hoặc được chuyển tiếp. Mỗi chain có quy tắc đánh giá của riêng nó. Trong **nftables**, các **base chain** có hook và priority; các chain trên cùng hook có thể được gọi theo **thứ tự ưu tiên số nhỏ hơn trước**.

Một điểm dễ hiểu sai: **accept tại một base chain không nhất thiết bảo đảm gói không thể bị drop tại base chain khác chạy sau đó**. Hành động drop có thể chấm dứt xử lý tương ứng. Bên cạnh đó, NAT và filter sử dụng những hook/giai đoạn riêng.

Vì thế khi kiểm tra Linux firewall cần xem **toàn bộ ruleset có liên quan**, gồm table, chain, hook, priority và đường nhảy vào chain, không chỉ đọc vài rule trong một chain.

### 8.2. Firewall trong cloud không dùng chung một mô hình ưu tiên

| Công nghệ / cơ chế | Ý nghĩa thứ tự | Cảnh báo khi thiết kế |
|---|---|---|
| **AWS Security Group** | Các rule Allow có hiệu lực **cộng gộp**, không áp thứ tự first-match giữa các rule SG; SG không có explicit deny thông thường | Không thể “đặt Deny ở trên Allow” trong Security Group; phải thu hẹp quyền Allow và phối hợp lớp khác |
| **AWS Network ACL (NACL)** | Rule được đánh giá theo **rule number tăng dần** trong chiều ingress/egress tương ứng; rule khớp đầu quyết định | NACL là **stateless**, cần xem cả chiều phản hồi và cổng tạm phù hợp |
| **Azure Network Security Group (NSG)** | Rule có priority; **số nhỏ hơn được xử lý trước** trong tập rule áp dụng; có default security rules | Cần xem hướng inbound/outbound, stateful behavior, áp dụng subnet/NIC và rule mặc định |
| **Kubernetes NetworkPolicy chuẩn** | Chính sách cho phép được **cộng gộp** khi pod bị áp chính sách; không có thứ tự deny/allow first-match chung trong API tiêu chuẩn | Hiệu lực phụ thuộc CNI hỗ trợ; tính năng deny theo thứ tự có thể là mở rộng riêng của nền tảng |

Các cơ chế này không thay thế nhau: ví dụ, một workload cloud có thể đồng thời chịu tác động của route table, network ACL, security group và host firewall. Không thể lấy quy tắc “rule 10 thắng rule 20” của một firewall vật lý để suy ra hành vi Security Group hoặc NetworkPolicy.

## 9. Một thiết kế rule first-match có thể kiểm thử

Giả sử tổ chức có các subnet:

| Zone | Địa chỉ ví dụ | Vai trò |
|---|---|---|
| Employee | **10.10.10.0/24** | Laptop nhân viên |
| Administrator | **10.10.20.0/24** | Máy quản trị |
| Guest | **10.10.50.0/24** | Thiết bị khách |
| Application | **10.20.20.10/32** | API nội bộ |
| Database | **10.30.30.10/32** | Database |
| Jump host | **10.40.40.10/32** | Cổng truy cập quản trị |

Yêu cầu nghiệp vụ:

- Employee được kết nối **Application TCP/443**, không truy cập trực tiếp Database.
- Chỉ Application được mở **Database TCP/5432**.
- Administrator được mở **Jump host TCP/22**, có xác thực và giám sát bổ sung.
- Guest không được khởi tạo kết nối tới các tài nguyên nội bộ.
- Mọi luồng không được khai báo phải bị từ chối theo chính sách.

### Ma trận quy tắc theo thứ tự khái niệm

Giả sử các rule này thuộc **cùng một policy first-match** dành cho những phiên **NEW** đi qua firewall:

| Thứ tự | Source | Destination | Service | Action | Mục đích |
|---:|---|---|---|---|---|
| 10 | Guest | Các vùng nội bộ | Any | **Deny + Log** | Cách ly mạng khách |
| 20 | Administrator | Jump host | TCP/22 | **Allow + Log** | Quản trị qua điểm kiểm soát |
| 30 | Employee | Application | TCP/443 | **Allow** | Sử dụng API |
| 40 | Application | Database | TCP/5432 | **Allow + Log** | Truy cập dữ liệu của ứng dụng |
| 50 | Employee | Database | Any | **Deny + Log** | Giúp nhận diện truy cập sai mục đích |
| 90 | Any | Any | Any | **Deny theo mặc định** | Chặn luồng không được phê duyệt |

Trong bảng này, rule 50 có thể **dư thừa về quyết định cuối** nếu đã có default deny và không có Allow nào khác bao phủ Employee → Database, nhưng nó vẫn có thể có giá trị ghi log và giải thích chính sách. Tên zone phải ánh xạ tới các nguồn/đích thực theo cấu hình; bảng không tự nói lên vị trí của IPsec, routing hay NAT.

**Một lỗi nguy hiểm:** nếu ai đó thêm rule **Allow 10.10.0.0/16 → 10.30.30.0/24 Any** trước rule 50, subnet Employee có thể được phép tới Database dù explicit deny vẫn hiện diện. Cách sửa bền vững là **thu hẹp Allow** và kiểm thử đầy đủ, không chỉ kéo một Deny lên đầu cho xong mà giữ lại Allow rộng không cần thiết.

## 10. Phương pháp rà soát thứ tự và tác động của rule mới

Trước khi tạo hoặc di chuyển rule, thực hiện các bước:

1. **Xác định mục tiêu:** luồng nghiệp vụ nào phải Allow, luồng nào bắt buộc Deny, và vì sao.
2. **Xác định điểm thực thi:** firewall nào, zone/hướng nào, policy package nào, route trước/sau NAT nào; có nhiều thiết bị không?
3. **Đọc ngữ nghĩa rule engine:** first-match, ordered priority hay additive; trường nào được so khớp trước/sau dịch.
4. **Chuẩn hóa điều kiện:** source/destination subnet, protocol, port, identity, schedule, interface và trạng thái NEW/ESTABLISHED.
5. **Kiểm tra overlap:** tìm mọi rule đứng trước có thể khớp cùng tập gói với rule mới.
6. **Tìm shadow/redundancy/conflict:** thử một gói đại diện cho từng phần giao nhau, kể cả biên subnet và service Any.
7. **Dự đoán tác động:** những phiên mới nào sẽ thay đổi, phiên cũ nào có thể vẫn tồn tại; có ứng dụng, DNS, VPN hoặc kiểm tra sức khỏe phụ thuộc không?
8. **Chạy kiểm thử trước và sau:** kiểm tra allow **và** deny từ nguồn/zone phù hợp, ghi log và rule hit.
9. **Ghi nhận và theo dõi:** lưu owner, lý do, thời gian/phiên bản thay đổi, yêu cầu rollback và kết quả thực tế.

### Dùng tập mẫu gói để kiểm tra ranh giới

Với chính sách ví dụ ở phần 9, có thể dùng bảng sau làm **test cases**:

| Test | Source | Destination | Protocol/port | Kỳ vọng | Rule kiểm chứng |
|---|---|---|---|---|---|
| R-01 | 10.10.10.25 | 10.20.20.10 | TCP/443 | **Allow** | 30 |
| R-02 | 10.10.10.25 | 10.30.30.10 | TCP/5432 | **Deny** | 50 |
| R-03 | 10.10.50.25 | 10.20.20.10 | TCP/443 | **Deny** | 10 |
| R-04 | 10.10.20.25 | 10.40.40.10 | TCP/22 | **Allow** | 20 |
| R-05 | 10.10.20.25 | 10.30.30.10 | TCP/5432 | **Deny** | 90 |
| R-06 | 10.20.20.10 | 10.30.30.10 | TCP/5432 | **Allow** | 40 |
| R-07 | 10.10.10.25 | 10.20.20.10 | TCP/22 | **Deny** | 90 |

Những test case này mô tả **kết quả mong muốn của phiên NEW**; không xác định kết quả của gói phản hồi thuộc một phiên đã được cấp quyền trước đó. Đối với mỗi test, cần bổ sung IPv6, đường VPN, NAT, route và các ứng dụng phụ trợ khi môi trường có chúng.

## 11. Ví dụ học thuật với nftables

Với Linux, **nftables** hỗ trợ quy tắc trong chain có thứ tự. Đoạn sau minh họa tập policy **forward** cho các địa chỉ trong phần 9. Nó chỉ phù hợp cho lab có cấu hình nền tương ứng; **không copy vào firewall production** nếu chưa đánh giá toàn bộ đường mạng, quy tắc IPv6, dịch vụ hỗ trợ và các base chain khác.

~~~nft
table inet segmentation_filter {
    chain forward {
        type filter hook forward priority filter; policy drop;

        ct state invalid drop
        ct state established,related accept

        # 10: deny khách vào các subnet nội bộ đã định nghĩa
        ip saddr 10.10.50.0/24 ip daddr { 10.20.20.0/24, 10.30.30.0/24, 10.40.40.0/24 } drop

        # 20: quản trị tới jump host
        ip saddr 10.10.20.0/24 ip daddr 10.40.40.10 \
            tcp dport 22 ct state new accept

        # 30: nhân viên tới API
        ip saddr 10.10.10.0/24 ip daddr 10.20.20.10 \
            tcp dport 443 ct state new accept

        # 40: ứng dụng tới database
        ip saddr 10.20.20.10 ip daddr 10.30.30.10 \
            tcp dport 5432 ct state new accept

        # 50: deny tường minh để giữ ranh giới nghiệp vụ
        ip saddr 10.10.10.0/24 ip daddr 10.30.30.10 drop
    }
}
~~~

Giải thích và các giới hạn:

- **policy drop** là hành vi mặc định của chain khi không có rule nào dẫn đến quyết định cho phép có hiệu lực.
- **ct state established,related accept** xử lý luồng phản hồi phù hợp trước những rule dành cho kết nối mới. Vì thế **đừng dùng thứ tự trong ví dụ này để suy ra rằng Deny mọi gói Guest ở mọi trạng thái**: nếu cần chặn tuyệt đối phiên đang tồn tại, phải thiết kế lại vị trí và xử lý state phù hợp.
- Rule nguồn Guest chỉ liệt kê **ba subnet đích mẫu**, không bao quát tất cả tài sản nội bộ của mọi mạng thật.
- Điều kiện **ip saddr/ip daddr** chỉ khớp IPv4; một table inet không tự động tạo chính sách IPv6 tương đương.
- Mã trên chưa có logging, NAT, chống giả mạo nguồn, kiểm soát egress, ICMPv6, DNS và các phụ thuộc khác; công cụ quản trị hạ tầng có thể tự sinh thêm chain.
- Trong nhiều hệ thống, nhận diện zone không chỉ dựa vào IP; cần đối chiếu interface/VRF và các ràng buộc khác trước khi tin rằng một gói thật sự thuộc mạng Guest hay Employee.

**Lệnh kiểm tra chỉ đọc trên host Linux được phép quản trị:**

~~~bash
sudo nft list ruleset -a
sudo conntrack -L
ip route
ip -6 route
~~~

Tùy hệ thống, tiện ích conntrack có thể chưa được cài hoặc yêu cầu quyền quản trị. **Rule handle/counter** trong output (nếu có) và trạng thái phiên giúp tìm dấu hiệu rule được dùng, nhưng không thay thế packet capture tại đúng vị trí và kết quả của bài kiểm thử có kiểm soát.

## 12. Đọc log và counter để xác nhận rule được xét

Một firewall thường cung cấp một hoặc nhiều nguồn dữ liệu:

| Nguồn | Có thể cho biết gì? | Điều không thể kết luận ngay |
|---|---|---|
| **Rule hit counter** | Rule đã khớp bao nhiêu lần theo cơ chế đếm của thiết bị | Counter tăng không đảm bảo ứng dụng nhận và xử lý thành công |
| **Session/connection table** | Kết nối đang được theo dõi, trạng thái, NAT mapping | Phiên được ghi nhận không chứng minh policy ứng dụng đúng |
| **Traffic log (allow/deny)** | Địa chỉ, port, zone, action, rule ID, timestamp khi được cấu hình | Thiếu log không đồng nghĩa gói không tồn tại hoặc không bị chặn |
| **Route/ARP/ND table** | Next hop, interface, đường đi cục bộ | Route có tồn tại không chứng minh firewall cho phép |
| **Packet capture** | Gói thật sự quan sát tại một interface/thời điểm | Không thấy gói ở một interface không chứng minh gói đã bị chặn tại firewall đó |
| **Application/proxy log** | HTTP status, TLS handshake, xác thực và quyền ứng dụng | Lỗi ứng dụng không mặc nhiên là lỗi firewall |

Ví dụ một log mô phỏng:

~~~text
2026-11-28T09:00:00+07:00
src_zone=guest src=10.10.50.25:52412
dst_zone=application dst=10.20.20.10:443
protocol=tcp session=new
action=deny rule_id=10
reason=guest-to-internal
~~~

Đây là **log minh họa**, không đại diện cú pháp sản phẩm cụ thể. Cần xác minh timestamp, source zone, NAT translation, rule ID và đường đi trước khi kết luận.

### Khi counter của rule Deny không tăng

Các khả năng thường gặp:

1. Gói bị **một Allow/Deny đứng trước** xử lý (shadowing).
2. Gói chưa tới firewall do route, ACL trên switch, DNS, firewall của host hoặc VPN.
3. Gói đi qua **firewall/policy/chain khác** (đường dự phòng hoặc traffic east–west).
4. Rule có điều kiện khác (zone, state, schedule, IP sau NAT, IPv6) nên không khớp.
5. Counter/log đã reset, chưa được bật hoặc cập nhật theo cơ chế có độ trễ.

Không nên di chuyển rule ngay khi thấy hit count bằng 0; trước tiên cần tái hiện **một luồng được phép thử**, đồng thời xác minh các điều kiện của nó.

## 13. Quản lý thay đổi và kiểm thử an toàn

Một thay đổi thứ tự rule có thể gây ra hiệu ứng rộng vì nó thay đổi quyền của **mọi gói nằm trong vùng giao nhau**, không chỉ gói đang gặp lỗi. Nên áp dụng quy trình:

- **Ghi chính sách mong muốn:** nguồn, đích, dịch vụ, điều kiện, owner, lý do và mức độ ưu tiên nghiệp vụ.
- **Đánh giá overlap/shadowing:** so sánh cả các rule ở trước và sau điểm chèn; tính đến nhóm địa chỉ và service object lồng nhau.
- **Kiểm tra trạng thái phiên:** xác định các phiên đang có có tiếp tục chạy sau khi đổi rule hay không; lên kế hoạch thu hồi khi cần.
- **Dựng test matrix:** có ca phải Allow, phải Deny và các ca ở biên subnet, TCP/UDP, IPv4/IPv6, VPN, guest, admin.
- **Triển khai qua quản lý thay đổi:** lưu phiên bản cấu hình, người phê duyệt, cửa sổ thay đổi, bước rollback và giám sát tác động.
- **Theo dõi sau thay đổi:** đo kết nối thành công, số deny/drop, rule hit, lỗi ứng dụng, độ trễ và cảnh báo IDS/IPS.
- **Tối ưu định kỳ:** thu hẹp ngoại lệ quá rộng, xem lại rule không dùng, kiểm tra quyền cloud và tài khoản/thiết bị không còn hoạt động.

### Phiếu kiểm thử rule

~~~text
Test ID:                 FW-ORDER-01
Source / zone:           [IP thực tế / Employee, Guest, VPN...]
Destination / zone:      [IP, tên dịch vụ, zone thực tế]
Protocol / port:         [TCP/443, UDP/53...]
Connection state:        [NEW hoặc phiên đã tồn tại]
Expected action:         [ALLOW / DENY]
Expected rule:           [ID, tên, priority]
Observed action:         [kết quả thực tế]
Actual rule / policy:    [ID đọc từ log/counter]
NAT addresses:           [trước và sau dịch nếu có]
Route / path:            [đường đã xác minh]
Evidence:                [log, capture, app check]
Result:                  [PASS / FAIL / INCONCLUSIVE]
~~~

**INCONCLUSIVE** là kết quả cần dùng khi chưa chứng minh được gói tới điểm kiểm tra. Một lần kết nối thất bại vì dịch vụ chưa bật hoặc mất route không phải bằng chứng firewall đã Deny đúng chính sách.

## 14. Tình huống: có rule Deny nhưng mạng khách vẫn vào database

**Bối cảnh giả định:** Đội bảo mật yêu cầu mạng Guest không được truy cập database. Người quản trị thấy một rule **Deny Guest → Database** trong policy, nhưng kiểm tra được ủy quyền cho thấy từ mạng Guest vẫn kết nối được TCP/5432.

Các rule hiện tại:

| Priority | Nguồn | Đích | Dịch vụ | Action |
|---:|---|---|---|---|
| 100 | 10.10.0.0/16 | 10.30.30.0/24 | Any | **Allow** |
| 200 | 10.10.50.0/24 | 10.30.30.10/32 | TCP/5432 | **Deny** |
| 900 | Any | Any | Any | Deny |

Guest sử dụng **10.10.50.25**, DB **10.30.30.10**. Gói TCP/5432 mới khớp **rule 100** vì nguồn thuộc 10.10.0.0/16 và đích thuộc 10.30.30.0/24; trong một policy first-match, thiết bị xử lý Allow trước khi tới rule 200. **Rule 200 bị shadow hoàn toàn đối với tập gói của nó.**

### Cách xử lý có căn cứ

1. **Xác minh thật sự là first-match:** đọc policy engine, rule set đang có hiệu lực và vị trí chính xác; loại trừ trường hợp kết quả đến từ một policy khác.
2. **Xác nhận luồng thực tế:** kiểm tra subnet, source zone, đích, NAT, state, route và log tương ứng; chỉ sử dụng phiên NEW trong phép thử quyết định thứ tự.
3. **Phân tích rule 100:** vì sao lại Allow cả 10.10.0.0/16 tới toàn bộ 10.30.30.0/24? Những nhóm nào thực sự cần quyền đó?
4. **Thu hẹp Allow:** chỉ giữ nguồn và dịch vụ cần thiết, ví dụ Application → DB TCP/5432 theo kiến trúc nghiệp vụ, thay vì All internal → All database.
5. **Đặt Deny bảo vệ thích hợp:** đưa Deny hẹp lên trước Allow rộng nếu vẫn có lý do duy trì Allow rộng cho các đích khác; xác nhận không gây shadow ngược cho luồng hợp lệ.
6. **Kiểm thử lại:** Guest → DB phải Deny; Application → DB phải Allow; Employee → API không bị ảnh hưởng; log phải trỏ tới rule đúng.
7. **Quản lý phiên đã tồn tại:** nếu thiết bị vẫn giữ một session được tạo trước thay đổi, xác minh chính sách về thu hồi và xử lý qua quy trình vận hành.

**Không nên giải quyết bằng cách tự động đẩy mọi Deny lên đầu.** Một Deny quá rộng có thể chặn cả dịch vụ hợp lệ và làm khó chẩn đoán. Mục tiêu là cấu hình thể hiện **đúng luồng được phép**, có kiểm soát phạm vi và có chứng cứ sau thay đổi.

### Câu hỏi kiểm tra tình huống

1. Rule 200 có được xét cho gói Guest → DB khi rule 100 đang Allow hay không?
2. Nếu đổi vị trí rule 100 và 200, những luồng nào có thể thay đổi ngoài Guest → DB?
3. Nếu không có counter trên rule 200, cần phân biệt shadowing với những nguyên nhân nào khác?
4. Nếu một phiên Guest → DB đã tồn tại trước khi sửa rule, vì sao nó có thể chưa ngắt ngay?
5. Cách thiết kế nào giúp giảm nguy cơ tái diễn khi nhân viên tạo thêm một Allow rộng?

## 15. Những hiểu nhầm cần tránh

| Hiểu nhầm | Vấn đề | Cách hiểu phù hợp |
|---|---|---|
| “Có Deny rồi nên chắc chắn bị chặn” | Rule Deny có thể bị Allow trước đó che | Kiểm tra đường xử lý, giao nhau của điều kiện và rule thực sự khớp |
| “Firewall tự ưu tiên rule cụ thể nhất” | Không đúng với nhiều policy first-match | Xác minh hành vi thật của rule engine và vị trí rule |
| “Luôn đặt tất cả Allow trước tất cả Deny” | Allow rộng che rule bảo vệ | Sắp theo chính sách cụ thể, kiểm soát overlap |
| “Luôn đặt tất cả Deny trước tất cả Allow” | Deny rộng chặn cả ngoại lệ hợp lệ | Định nghĩa ranh giới/ngoại lệ và kiểm thử |
| “Rule cuối là Deny thì đã an toàn” | Allow quá rộng phía trên có thể mở mọi luồng | Rà soát tập Allow, không chỉ default action |
| “Counter bằng 0 thì rule thừa” | Có thể rule là dự phòng, log chưa bật hoặc traffic chưa xuất hiện | Xác minh phạm vi, lịch, giá trị bảo vệ và thử nghiệm |
| “Đổi rule là ngắt mọi kết nối” | State tồn tại có thể tiếp tục được xử lý | Xác minh cơ chế phiên và quy trình thu hồi |
| “Rule theo địa chỉ công khai luôn khớp sau DNAT” | Thứ tự NAT/security policy tùy nền tảng | Kiểm tra pre-/post-NAT match thực tế |
| “Cloud security rules đều first-match” | Có cơ chế additive và ưu tiên theo số, khác nhau | Đọc ngữ nghĩa từng sản phẩm: SG, NACL, NSG, NetworkPolicy |
| “Firewall Allow nghĩa là ứng dụng phải hoạt động” | DNS, route, host firewall, TLS và authorization vẫn ảnh hưởng | Dùng log end-to-end và xác minh từng lớp |
| “Chỉ cần kiểm tra IPv4” | IPv6 có thể chịu bộ rule hoặc định tuyến khác | Kiểm thử cả hai giao thức khi dùng dual-stack |

## 16. Tự kiểm tra kiến thức

1. Trong firewall first-match, khi một gói khớp cả rule Allow ở vị trí 10 và Deny ở vị trí 20, kết quả là gì? Điều kiện gì có thể khiến câu trả lời thay đổi trên nền tảng khác?
2. Shadowing hoàn toàn khác overlap một phần ở điểm nào?
3. Vì sao một rule **Deny Any → Any** đặt trên cùng trong một chain first-match khiến các rule phía dưới mất tác dụng?
4. Explicit deny có ưu điểm vận hành gì so với implicit deny? Có bắt buộc phải dùng cả hai không?
5. NAT thay đổi thông tin nào của gói, và điều gì phải được xác minh khi một rule chỉ định IP đích?
6. Vì sao một kết nối TCP đang tồn tại có thể tiếp tục sau khi bổ sung rule Deny cho các kết nối mới?
7. AWS Security Group khác AWS Network ACL thế nào về thứ tự và cách quyết định?
8. Trong nftables, vì sao **Accept ở một base chain** không luôn đồng nghĩa gói sẽ thoát toàn bộ hệ thống lọc?
9. Khi hit counter của một rule bằng 0, có những khả năng nào ngoài việc rule bị shadow?
10. Để chứng minh Guest → Database được chặn bởi đúng policy, cần những thông tin và bằng chứng nào?

## 17. Ghi nhớ trọng tâm

**Rule ordering quyết định kết quả khi nhiều quy tắc có thể khớp cùng một luồng.** Trong danh sách **top-down, first-match**, quy tắc khớp trước quyết định hành động; một Allow hoặc Deny đặt sai chỗ có thể làm rule phía sau bị **shadow**, tạo **overlap** khó giải thích hoặc khiến **ngoại lệ** mất hiệu lực. Tuy nhiên, không nên áp mô hình đó cho mọi nền tảng: **Security Group cộng gộp quyền**, các ACL/NSG có thể dùng **priority**, còn nftables có **chain và hook** cần xem toàn bộ ngữ cảnh.

Để xây dựng firewall an toàn, hãy bắt đầu từ **ma trận luồng được phép**, giữ **quyền tối thiểu**, rà soát giao nhau của rule, xác nhận tương tác với **stateful inspection, NAT, zone, IPv4/IPv6 và các đường VPN/cloud**, rồi kiểm thử từ đúng điểm truy cập. **Một rule được viết đúng cú pháp chưa chắc được thực thi đúng ý định**: cần đối chiếu rule hit, session, đường đi, log và hành vi ứng dụng để chứng minh quyết định thực tế.
