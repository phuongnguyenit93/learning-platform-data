# Rule matching trong firewall: cách xác định quy tắc áp dụng cho lưu lượng

Trong chương **Firewall** của module **SECURITY_NETWORK_SECURITY**, *rule matching* là quá trình firewall so sánh thông tin của gói tin hoặc luồng mạng với các điều kiện trong chính sách để quyết định **cho phép, từ chối, ghi log, chuyển tới bước kiểm tra khác** hoặc thực hiện hành động được cấu hình. Nắm được cơ chế này giúp xây dựng các lớp phòng vệ mạng, phân đoạn vùng tin cậy, bảo vệ truy cập VPN và cloud, đồng thời giải thích vì sao một kết nối được cho phép hoặc bị chặn.

Khi một ứng dụng không kết nối được tới máy chủ, câu hỏi “Có mở cổng chưa?” thường chưa đủ. Firewall có thể xét đồng thời **hướng lưu lượng, vùng mạng, địa chỉ nguồn và đích, giao thức, cổng, trạng thái kết nối, danh tính**, thời điểm và thứ tự quy tắc. Địa chỉ nhìn thấy tại một điểm kiểm tra cũng có thể đã thay đổi do NAT, proxy hoặc đường hầm VPN.

Sau bài học, bạn có thể:

- Phân biệt *match condition*, *action*, *rule priority*, *default policy* và *connection state*.
- Dự đoán kết quả cho phép/chặn của lưu lượng theo danh sách rule có thứ tự.
- Giải thích ảnh hưởng của NAT, routing, zone/interface, IPv4/IPv6 và stateful inspection đến rule matching.
- Nhận diện các rule chồng lấn, bị che khuất (*shadowed*), quá rộng hoặc không bao giờ được khớp.
- Thiết kế kịch bản kiểm thử và đọc log/counter để xác minh firewall thực sự thi hành chính sách mong muốn.

## 1. Một firewall rule gồm những gì?

Về bản chất, rule mô tả một tập lưu lượng thỏa mãn điều kiện và cách xử lý khi điều kiện đó đúng.

~~~text
IF traffic matches (source, destination, protocol, port, direction, ...)
THEN apply action (ALLOW / DENY / REJECT / LOG / INSPECT / ...)
~~~

Ví dụ chính sách khái niệm:

~~~text
Nguồn       : Vùng ứng dụng (APP)
Đích        : Máy chủ DB 10.20.30.10
Giao thức   : TCP
Cổng đích   : 5432
Hướng       : APP -> DATA
Hành động   : ALLOW
Điều kiện   : Chỉ workload API được phê duyệt
~~~

Rule này cần được chuyển thành cú pháp và điều kiện mà **firewall cụ thể thực sự hỗ trợ**. Nếu sản phẩm chỉ hỗ trợ đối tượng theo subnet, yêu cầu “chỉ workload API” có thể cần cơ chế khác như danh tính workload, microsegmentation hoặc host firewall để đạt độ chính xác mong muốn.

### 1.1. Các trường thường được sử dụng để match

| Trường | Diễn giải | Ví dụ và điểm cần chú ý |
| --- | --- | --- |
| **Source IP / subnet** | Địa chỉ hoặc mạng nguồn nhìn thấy tại điểm lọc | 10.20.10.0/24; có thể là IP đã được NAT |
| **Destination IP / subnet** | Địa chỉ hoặc mạng đích nhìn thấy tại điểm lọc | 10.20.30.10/32; có thể là địa chỉ private sau DNAT |
| **L3 protocol / address family** | IPv4 hoặc IPv6; đôi khi điều kiện IP protocol riêng | Một rule chỉ xét IPv4 không tự bảo vệ IPv6 |
| **L4 protocol** | TCP, UDP hoặc loại giao thức khác | TCP/443 và UDP/443 là hai loại lưu lượng khác nhau |
| **Source port** | Cổng nguồn; thường là cổng tạm thời phía client | 51842; không nên giả định client chỉ dùng một dải cố định |
| **Destination port** | Cổng dịch vụ đích | TCP/443, UDP/53, TCP/5432 |
| **ICMP type/code** | Phân biệt loại thông điệp ICMP | Echo Request, Destination Unreachable, Packet Too Big |
| **Ingress/egress interface, zone, direction** | Đường đi và vùng tin cậy của gói tại firewall | WAN → DMZ, APP → DATA |
| **Connection state** | Gói mới, thuộc luồng đã được theo dõi, liên quan hoặc bất thường | NEW, ESTABLISHED, RELATED, INVALID trong một số hệ thống |
| **Identity, tag, application, URL, schedule** | Điều kiện mở rộng của firewall có khả năng tương ứng | Nhóm người dùng VPN, tag cloud, ứng dụng nhận diện qua DPI |

Một **5-tuple** phổ biến để nhận diện luồng là:

~~~text
(source IP, source port, destination IP, destination port, protocol)

(10.20.10.25, 51842, 10.20.30.10, 5432, TCP)
~~~

Tuy nhiên, **5-tuple chưa đủ để tự xác định rule cuối cùng**: còn phải biết gói đi qua thiết bị nào, chiều/zone nào, chính sách được áp dụng ở bước nào, trạng thái luồng và kết quả chuyển đổi địa chỉ.

### 1.2. Khớp cổng nguồn khác cổng đích

Trong một kết nối TCP điển hình, client sử dụng **cổng nguồn tạm thời** để liên hệ **cổng đích của dịch vụ**:

~~~text
Client 10.20.10.25:51842  --->  DB 10.20.30.10:5432
              source port                 destination port
~~~

Để cho phép client kết nối DB, rule thường xét **destination port = 5432** của gói bắt đầu kết nối. Không nên viết nhầm “source port = 5432”, vì khi đó rule có thể chỉ khớp gói phản hồi hoặc lưu lượng khác. Với firewall stateful, gói phản hồi thường được xử lý theo trạng thái luồng đã thiết lập; với lọc stateless, cần xét riêng đường phản hồi.

Port chỉ là **dấu hiệu về dịch vụ**, không chứng minh nội dung ứng dụng. Một tiến trình khác vẫn có thể lắng nghe trên TCP/443; firewall L3/L4 thông thường không tự xác minh đó là HTTPS hợp lệ.

## 2. Quy trình xử lý trước khi một rule được chọn

Rule matching không diễn ra tách rời đường truyền. Một packet có thể bị loại ngay từ các bước kiểm tra trước policy, không được route qua firewall, hoặc đi vào một policy khác với dự đoán.

~~~mermaid
flowchart TD
    A["Packet đi vào interface / zone"] --> B{"Điều kiện sơ bộ hợp lệ?\n(route, anti-spoof, validity...)"}
    B -- "Không" --> X["Drop hoặc xử lý theo thiết bị"]
    B -- "Có" --> C["Xác định hướng, zone và ngữ cảnh NAT"]
    C --> D{"Có luồng được theo dõi / rule stateful phù hợp?"}
    D -- "Có" --> E["Xử lý theo state/policy tương ứng"]
    D -- "Không hoặc cần đánh giá" --> F["Đánh giá các rule trong policy áp dụng"]
    F --> G{"Có rule phù hợp?"}
    G -- "Có" --> H["Thực hiện action của rule"]
    G -- "Không" --> I["Áp dụng default action"]
    E --> J["Xử lý các bước tiếp theo và chuyển tiếp nếu được phép"]
    H --> J
    I --> J
~~~

Sơ đồ biểu diễn **luồng tư duy**, không phải thứ tự pipeline chuẩn cho mọi sản phẩm. Trong thực tế, NAT, routing, kiểm tra trạng thái, chống giả mạo và policy có thể nằm ở những hook hoặc stage khác nhau. Một số firewall có nhiều nhóm rule như ingress, egress, forward, security, application hoặc global policy; quyết định cuối cùng có thể chịu tác động của nhiều lớp.

Muốn phân tích đúng một gói tin, hãy xác nhận:

1. Gói có thực sự **đi qua firewall** hay bị định tuyến trực tiếp, đi đường khác hoặc dừng trước đó?
2. Gói được nhìn thấy trên **interface/zone** nào, theo hướng nào?
3. Địa chỉ, cổng đang xét là **trước hay sau NAT**?
4. Đây là gói **mở luồng mới** hay gói trong luồng đã được connection tracking nhận biết?
5. Traffic chịu **policy/chain** nào và cách xử lý thứ tự ra sao?
6. Rule cụ thể nào đã match; có log, counter hoặc trace chứng minh không?

## 3. Thứ tự và ưu tiên: first match, default action và các biến thể

### 3.1. Mô hình first-match

Trong nhiều ACL và firewall policy **có thứ tự**, thiết bị xét từ rule ưu tiên cao hơn tới thấp hơn; **rule đầu tiên khớp** sẽ quyết định action cho gói tin hoặc phiên được kiểm tra theo cơ chế đó.

Giả sử thiết bị đang dùng *first-match, top-down* và các điều kiện đều áp vào **luồng mới** ở cùng một policy:

| Thứ tự | Nguồn | Đích | Protocol/port đích | Action | Ý nghĩa |
| --- | --- | --- | --- | --- | --- |
| 10 | 10.20.50.0/24 (GUEST) | 10.20.30.10 (DB) | TCP/5432 | DENY + LOG | Khách không được vào DB |
| 20 | 10.20.10.0/24 (APP) | 10.20.30.10 (DB) | TCP/5432 | ALLOW | APP được vào DB |
| 30 | 10.20.99.0/24 (ADMIN) | 10.20.10.10 (WEB) | TCP/22 | ALLOW | Quản trị SSH từ vùng được chỉ định |
| 40 | Any | 10.20.10.10 (WEB) | TCP/443 | ALLOW | Người dùng truy cập HTTPS trên TCP |
| 50 | Any | 10.20.30.10 (DB) | Any | DENY + LOG | Chặn truy cập DB còn lại |
| 90 | Any | Any | Any | DENY | Chính sách mặc định minh họa |

Điều kiện của ví dụ: nơi áp policy đã xác định đúng vùng/đường đi, các địa chỉ là những gì policy **thực sự nhìn thấy**; thiết bị cho phép xử lý gói phản hồi thuộc luồng được phép qua stateful tracking. Con số 10, 20, 30 là **thứ tự minh họa**: có nền tảng số nhỏ ưu tiên trước, có nền tảng áp dụng mô hình khác.

Thử một số lưu lượng:

| Gói bắt đầu kết nối | Diễn biến match | Quyết định |
| --- | --- | --- |
| 10.20.10.25:51842 → 10.20.30.10:5432 TCP | Rule 10 không khớp nguồn; **rule 20 khớp** | ALLOW |
| 10.20.50.8:53000 → 10.20.30.10:5432 TCP | **Rule 10 khớp đầu tiên** | DENY + LOG |
| 10.20.60.7:53001 → 10.20.30.10:5432 TCP | Không khớp 10/20; **rule 50 khớp** | DENY + LOG |
| 10.20.99.8:51000 → 10.20.10.10:22 TCP | **Rule 30 khớp** | ALLOW |
| 198.51.100.18:52000 → 10.20.10.10:443 TCP | **Rule 40 khớp** nếu IP đích nội bộ được xét sau DNAT | ALLOW |
| 10.20.50.8:53002 → 10.20.10.10:22 TCP | Không rule chuyên biệt nào khớp; **rule 90** | DENY |

Đọc rule theo một **kịch bản gói cụ thể** tốt hơn nhìn riêng từng dòng. Cùng TCP/443, một gói từ Internet tới WEB và một gói từ WEB tới Internet có nguồn, đích, hướng và trạng thái khác nhau; chúng không nhất thiết dùng cùng rule.

### 3.2. Khi rule cụ thể bị che khuất (shadowing)

Xét hai rule được đánh giá trong cùng policy first-match:

~~~text
10  ALLOW  src=any             dst=10.20.30.10  tcp/5432
20  DENY   src=10.20.50.0/24  dst=10.20.30.10  tcp/5432
~~~

Mọi gói khớp rule 20 **cũng khớp rule 10 trước đó**. Rule 20 trở thành *shadowed* hoàn toàn, không bao giờ quyết định kết quả trong ngữ cảnh này. Đây là lỗi nguy hiểm vì cấu hình có vẻ có dòng chặn khách nhưng luồng thực tế vẫn được cho phép.

Cách sửa phụ thuộc **mục tiêu chính sách**: nếu chỉ APP được vào DB, thay rule 10 bằng allowlist APP và giữ deny DB; nếu cần chặn riêng GUEST trước một rule allow rộng hơn, ưu tiên deny GUEST trước. Không có quy tắc tổng quát “DENY luôn đặt trước ALLOW” cho mọi nền tảng hoặc mọi trường hợp.

Ngoài *shadowing*, cần phân biệt:

- **Overlap:** hai rule có giao nhau về tập lưu lượng; rule trước có thể xử lý một phần của rule sau.
- **Redundancy:** bỏ một rule mà kết quả chính sách không đổi trong phạm vi đã xét.
- **Conflict:** hai rule có action mâu thuẫn trên tập lưu lượng giao nhau; mô hình ưu tiên quyết định kết quả thực tế.
- **Unreachable rule:** rule không thể được đánh giá do chain/zone không được dùng, điều kiện bất khả thi hoặc đã bị rule trước bao phủ.

Một rule chưa có hit counter **chưa chắc** bị che khuất: traffic có thể chưa phát sinh, log/counter bị reset hoặc rule nằm trên nhánh ít dùng.

### 3.3. Không phải firewall nào cũng dùng first-match

Cách đánh giá phải lấy từ tài liệu và cấu hình của **nền tảng thực tế**:

| Mô hình | Cách quyết định thường gặp | Điều phải xác minh |
| --- | --- | --- |
| **Ordered first-match** | Dừng hoặc đưa ra verdict khi rule đầu tiên khớp theo policy | Hướng xét, thứ tự rule, quy tắc với chain/jump, rule đặc biệt |
| **Policy ưu tiên bằng số** | Một priority được dùng để xếp thứ tự đánh giá | Số nhỏ hay lớn ưu tiên trước; có nhóm policy/global override không |
| **Allowlist cộng gộp** | Nhiều điều kiện cho phép kết hợp thành tập lưu lượng được mở | Nền tảng có hỗ trợ explicit deny không; có lớp policy khác vẫn chặn không |
| **Nhiều tầng policy** | Quyết định đi qua security group/ACL/host firewall hoặc chain khác nhau | Control nào được đánh giá trước và điều kiện “được phép ở tất cả tầng” |
| **Application-aware / NGFW** | Có thể cần nhận diện ứng dụng, người dùng hoặc hoàn tất kiểm tra thêm | Khi chưa nhận diện được ứng dụng, rule tạm thời hoặc fallback hoạt động ra sao |

Ví dụ, **security group** của một số cloud hoạt động như tập *allow rules* chứ không có explicit deny trong cùng nhóm; **network ACL** của cùng nền tảng có thể xử lý rule đánh số theo thứ tự và áp theo kiểu stateless. Không lấy quy tắc ưu tiên của một sản phẩm áp dụng máy móc sang sản phẩm khác.

### 3.4. Implicit deny và default action

Khi không có rule phù hợp, kết quả phụ thuộc **default action** của policy/chain. Theo nguyên tắc tối thiểu quyền, nhiều thiết kế dùng **default deny** để buộc kết nối mới cần được cho phép rõ ràng. Một số hệ thống lại có default allow ở một số hướng, zone hoặc profile; phải kiểm tra cấu hình thay vì đoán.

*DENY/DROP* thường loại gói mà không gửi phản hồi trực tiếp. *REJECT* có thể gửi thông báo từ chối như TCP RST hoặc ICMP phù hợp tùy giao thức/thiết bị. Việc client báo **timeout** hay **connection refused** là manh mối, **không phải bằng chứng duy nhất** về rule đã khớp.

## 4. Stateful và stateless: ảnh hưởng trực tiếp đến rule matching

### 4.1. Stateless: đánh giá từng gói độc lập

Một bộ lọc **stateless** thường chỉ dựa vào header và thông tin của từng packet. Nếu rule cho phép chiều client → server nhưng không có quy tắc phù hợp cho chiều server → client, phản hồi có thể bị chặn.

Ví dụ:

~~~text
Client 10.20.10.25:51842 -> Server 10.20.30.10:5432 : TCP SYN
Server 10.20.30.10:5432 -> Client 10.20.10.25:51842 : TCP SYN+ACK
~~~

Hai gói có source/destination IP và port **đảo chiều**. Với lọc stateless, cần thiết kế quy tắc phản hồi đủ chặt theo hướng, loại gói và phạm vi phù hợp; một rule “allow high ports” quá rộng có thể mở đường không mong muốn.

### 4.2. Stateful: theo dõi trạng thái của luồng

Firewall **stateful** thường duy trì bảng kết nối (*connection tracking/conntrack*), liên kết gói phản hồi với phiên đã được chấp thuận. Khái niệm trạng thái thường gặp:

| State khái niệm | Ý nghĩa | Cách xử lý cần cân nhắc |
| --- | --- | --- |
| **NEW** | Gói bắt đầu một luồng chưa được xác nhận/ghi nhận như luồng đang tồn tại | So rule mở kết nối theo nguồn, đích, dịch vụ |
| **ESTABLISHED** | Gói thuộc luồng đã được ghi nhận; cách đặt nhãn cụ thể phụ thuộc engine | Thường được phép tiếp tục theo session policy |
| **RELATED** | Lưu lượng liên quan đến một luồng hiện có theo cơ chế theo dõi phù hợp | Chỉ cho phép khi đúng nhu cầu và helper/inspection đáng tin |
| **INVALID** | Gói không phù hợp trạng thái đã biết hoặc không thể được phân loại hợp lệ | Thường nên chặn/ghi nhận tùy chính sách |

Các nhãn ở đây gắn với cách diễn đạt của **một số engine conntrack**, không phải các trạng thái TCP chuẩn. TCP có SYN-SENT, ESTABLISHED, FIN-WAIT, TIME-WAIT… theo ngữ nghĩa riêng; firewall có thể dùng một biểu diễn trạng thái nội bộ khác.

Với **UDP**, không có handshake SYN/ACK/FIN như TCP. Một firewall stateful có thể tạo trạng thái tạm khi thấy datagram đi ra, rồi nhận diện datagram trả về dựa trên tuple và timeout. Điều này **không có nghĩa UDP tự tạo kết nối tin cậy**.

Những điểm dễ nhầm:

- **Cho phép kết nối mới** không đồng nghĩa mọi gói phản hồi chắc chắn qua được: có thể có asymmetric routing, state timeout, NAT sai hoặc policy ở thiết bị khác.
- **Đổi rule** khi một session đã mở không nhất thiết lập tức cắt session đó. Hành vi phụ thuộc nền tảng, cấu hình *session re-evaluation* và việc flush state.
- **Bảng trạng thái có giới hạn:** lưu lượng lớn, DDoS hay timeout dài có thể làm cạn tài nguyên connection tracking.
- **Một rule LOG** không nhất thiết ghi lại mọi packet; nhiều nền tảng ghi khi mở phiên, đóng phiên, từ chối hoặc lấy mẫu.

## 5. NAT, routing và zone có thể làm thay đổi điều kiện match

### 5.1. DNAT và địa chỉ đích trước/sau dịch

Giả sử người dùng Internet truy cập public HTTPS:

~~~text
Client: 198.51.100.18:52000
Public VIP: 203.0.113.20:443
DNAT -> Private WEB: 10.20.10.10:443
~~~

Nếu security policy được xét **sau DNAT**, destination mà rule cần so có thể là **10.20.10.10**. Nếu sản phẩm xét rule theo **địa chỉ trước NAT**, object cần so có thể là **203.0.113.20**. Một số hệ thống có cách dùng địa chỉ gốc và địa chỉ dịch khác nhau giữa NAT rule, security rule, log và session table.

**Không thể suy thứ tự NAT và filtering bằng một quy tắc chung cho mọi firewall.** Phải xem packet flow của sản phẩm, xác định stage đang đánh giá và đối chiếu log phiên.

### 5.2. SNAT, VPN và proxy làm thay đổi nguồn

Một client nội bộ đi Internet có thể bị đổi **source IP** khi SNAT. Truy cập từ xa qua VPN có thể dùng IP trong pool VPN thay vì địa chỉ Wi-Fi/Internet ban đầu. Khi một proxy đại diện client mở kết nối tới backend, backend có thể thấy IP của proxy, còn danh tính client gốc chỉ nằm trong trường ứng dụng như forwarded header được tin cậy có điều kiện.

Vì vậy, khi thiết kế rule cho “nhân viên từ xa vào server”, cần xác nhận firewall nào nhìn thấy **IP nguồn trước/ sau NAT hoặc giải mã VPN** và có thể map IP đó về tài khoản/thiết bị đáng tin hay không.

### 5.3. Route, zone và asymmetric path

Firewall có thể gắn policy theo *from-zone → to-zone*, ingress/egress interface hoặc loại luồng như *input*, *forward*, *output*. Nếu packet đi vào một interface khác dự kiến, có thể khớp **rule khác** hoặc không tới rule mong muốn.

~~~text
Hệ thống gửi gói qua:  APP -> Firewall A -> DATA
Hệ thống trả lời qua : DATA -> Firewall B -> APP
~~~

Nếu Firewall B không có trạng thái của kết nối đi qua Firewall A, gói phản hồi có thể bị coi là không hợp lệ. Với hệ thống HA hoặc nhiều đường truyền, cần thiết kế **symmetry, state synchronization** hoặc cơ chế phù hợp và kiểm tra failover.

Một vấn đề khác: route không tồn tại hoặc host không lắng nghe có thể gây kết nối thất bại **trước khi kết luận firewall chặn**.

## 6. Điều kiện match đặc biệt và giới hạn thực tế

### 6.1. IPv4, IPv6, ICMP và packet fragmentation

- **IPv4 và IPv6** có thể áp dụng các bảng/chính sách riêng. Chỉ cấu hình rule IPv4 không đảm bảo chặn được dịch vụ qua IPv6.
- **ICMP/ICMPv6** có nhiều type/code dùng cho chẩn đoán và hoạt động bình thường của mạng. Chặn toàn bộ ICMP có thể cản Path MTU Discovery; IPv6 còn phụ thuộc một số thông điệp ICMPv6 để hoạt động đúng.
- **Packet fragmentation** có thể khiến các mảnh không chứa TCP/UDP port header. Khả năng match L4 phụ thuộc cách firewall tái lắp ráp, lưu trạng thái phân mảnh và chính sách với fragment.
- **Header và extension** ở IPv6 có thể ảnh hưởng khả năng nhận diện giao thức tầng trên. Chính sách cần xét cách sản phẩm xử lý các trường hợp bất thường.

### 6.2. FQDN, đối tượng động và workload thay đổi IP

Rule theo tên miền, FQDN object, IP set hoặc cloud tag rất tiện cho dịch vụ thay đổi địa chỉ, nhưng phải biết:

- Thiết bị cập nhật địa chỉ khi DNS record thay đổi theo cách nào, với tần suất và TTL nào?
- Một FQDN trả nhiều A/AAAA record, sử dụng CDN hoặc địa chỉ chia sẻ có được xử lý đúng không?
- Rule áp dụng cho **IP kết nối** hay có khả năng nhận diện **tên miền trong traffic ứng dụng**?
- Nếu DNS, identity provider hoặc API cloud không hoạt động, rule dùng tập địa chỉ cũ hay xử lý thế nào?

**Rule theo FQDN không đồng nghĩa nhận diện/ủy quyền ứng dụng bằng tên miền**. Cũng cần phân biệt DNS query thông thường với các kết nối dùng DoH/DoT và việc HTTPS mã hóa một phần metadata.

### 6.3. Application, user và TLS inspection

Firewall thế hệ mới có thể dùng thông tin người dùng, app signature, URL category hoặc TLS metadata. Những điều kiện này có thể cần **nhiều gói đầu tiên** của luồng để nhận diện; hành vi trước và sau khi nhận diện phụ thuộc sản phẩm. TLS/QUIC được mã hóa có thể giới hạn nội dung mà thiết bị quan sát được nếu không có cơ chế tương ứng.

Không dùng “application=HTTPS” thay thế vô điều kiện cho chính sách IP/cổng và xác thực phía server. Ngược lại, chỉ mở TCP/443 cũng **không chứng minh** đó là HTTPS hợp lệ. Khi threat model yêu cầu bảo vệ dữ liệu hoặc danh tính, cần phối hợp TLS, xác minh chứng chỉ, authN/authZ và bảo vệ tầng ứng dụng.

### 6.4. Thứ tự giữa policy, logging, IPS và exception

Trên một số thiết bị, luồng đã **ALLOW** ở firewall vẫn có thể bị chặn ở IPS, policy ứng dụng hoặc cơ chế bảo vệ DoS. Một rule “LOG” cũng có thể là hành động bổ sung không làm đổi allow/deny. Tùy nền tảng, exception hoặc rule được áp ở global policy có thể ảnh hưởng kết quả.

Vì vậy cần phân biệt:

- **Rule match:** điều kiện nào phù hợp?
- **Policy verdict:** allow, deny, reject hay tiếp tục sang chain/engine khác?
- **Final forwarding outcome:** gói có thực sự được chuyển tiếp, NAT/route được và dịch vụ có phản hồi không?

Ba kết quả này có liên hệ nhưng **không phải lúc nào cũng giống nhau**.

## 7. Thiết kế rule hiệu quả theo threat model và nguyên tắc tối thiểu quyền

Một rule tốt phải bắt đầu bằng **luồng nghiệp vụ hợp lệ** và ranh giới cần bảo vệ. Giả sử kiến trúc gồm:

~~~mermaid
flowchart LR
    I["Internet"] --> F["Firewall / Edge"]
    F --> W["WEB 10.20.10.10"]
    W -->|TCP 5432| D[("DB 10.20.30.10")]
    M["ADMIN 10.20.99.0/24"] --> F
    G["GUEST 10.20.50.0/24"] --> F
    F -. "Flow logs" .-> S["SIEM / Giám sát"]
~~~

Các *security requirements* có thể là:

1. Internet chỉ tới **WEB trên TCP/443** qua VIP và DNAT được kiểm soát.
2. Chỉ workload web/API **cần thiết** được liên hệ **DB trên TCP/5432**; không cho toàn bộ mạng nội bộ đi vào DB.
3. SSH tới WEB chỉ đến từ **vùng quản trị** đã xác thực; truy cập quản trị từ xa cần qua VPN/ZTNA phù hợp.
4. Vùng GUEST không được truy cập trực tiếp APP, DATA và MANAGEMENT.
5. Các luồng bị chặn tại ranh giới quan trọng cần được quan sát theo chính sách log, có cảnh báo khi phù hợp.

Từ đó, tạo bản ghi rule:

~~~yaml
rule_id: FW-APP-DB-01
description: "Allow approved API workloads to the database"
from_zone: APP
to_zone: DATA
source: "Approved API workload group"
destination: "DB service 10.20.30.10"
protocol: TCP
destination_port: 5432
action: ALLOW
log: "Session start/end according to platform policy"
owner: "Network/Platform"
justification: "API requires database connectivity"
review_trigger: "Service, workload identity or DB topology changes"
~~~

Đây là **mẫu mô tả chính sách**, không phải cấu hình áp trực tiếp lên một sản phẩm. Nếu firewall không hỗ trợ nhận diện workload, hãy nêu rõ độ rộng của IP/subnet đang được dùng, bổ sung host policy hoặc identity control và ghi rủi ro còn lại.

### Những nguyên tắc giúp tránh rule quá rộng

- **Nguồn/đích cụ thể:** ưu tiên service hoặc mạng được xác định, hạn chế Any–Any.
- **Cổng/giao thức cụ thể:** chỉ mở đúng TCP hoặc UDP cần thiết; không dùng Any protocol nếu không có lý do và bằng chứng.
- **Đúng chiều:** người dùng truy cập ứng dụng không mặc nhiên cho phép ứng dụng khởi tạo kết nối ngược đến người dùng.
- **Xác thực và phân quyền:** một kết nối được firewall cho phép vẫn phải được dịch vụ/ứng dụng kiểm tra danh tính và quyền.
- **Ranh giới rõ ràng:** tách guest, user, app, data và management; hạn chế lateral movement nếu một vùng bị chiếm.
- **Giới hạn thời gian và sở hữu:** rule tạm có hạn hết hiệu lực, ticket, người duyệt và người chịu trách nhiệm.
- **Observability:** bật log theo rủi ro, theo dõi policy hit và điều chỉnh khối lượng log hợp lý để không gây bão log.

## 8. Kiểm chứng rule matching bằng log, counter và packet capture

**Không xem cấu hình là bằng chứng đủ.** Cần thử cả luồng **được phép** và **phải bị chặn**, sau đó đối chiếu rule hit với kết quả kết nối.

### 8.1. Bộ test cho ví dụ

Giả sử policy first-match ở mục 3 đang được áp dụng như mong đợi:

| Test | Luồng mới | Kỳ vọng | Bằng chứng cần thu |
| --- | --- | --- | --- |
| **P1** | APP 10.20.10.25 → DB 10.20.30.10 TCP/5432 | ALLOW (rule 20) | Session và hit counter rule 20; DB lắng nghe, kết nối thành công |
| **N1** | GUEST 10.20.50.8 → DB TCP/5432 | DENY (rule 10) | Deny log rule 10; không thấy DB nhận kết nối hợp lệ |
| **N2** | USER 10.20.60.7 → DB TCP/5432 | DENY (rule 50) | Deny log rule 50; xác nhận đường đi qua firewall |
| **P2** | ADMIN 10.20.99.8 → WEB TCP/22 | ALLOW (rule 30) | Rule hit và phản hồi SSH từ service có lắng nghe |
| **P3** | Internet 198.51.100.18 → public VIP TCP/443 | ALLOW nếu DNAT và security rule phù hợp | NAT/session log, rule hit, TCP/TLS handshake |
| **N3** | GUEST 10.20.50.8 → WEB TCP/22 | DENY (rule 90) | Default deny hoặc deny log phù hợp |
| **N4** | APP không thuộc danh sách được cấp quyền → DB TCP/5432 | DENY trong chính sách **đã siết theo workload** | Log từ policy mới; bảo đảm không có allow subnet quá rộng |
| **R1** | DB phản hồi phiên TCP được phép | Được phép theo state nếu thiết kế stateful | Session table và đường quay về đối xứng/được đồng bộ |

**Điều kiện kiểm thử:** chạy trên host, mạng và địa chỉ thuộc phạm vi được ủy quyền; kiểm thử các rule có thể gây gián đoạn nên tiến hành ở staging hoặc cửa sổ thay đổi có rollback. Các địa chỉ 198.51.100.0/24 và 203.0.113.0/24 là dải tài liệu minh họa, không phải máy public để truy cập thật.

### 8.2. Quan sát từ máy Linux và thiết bị được quản lý

Trong môi trường Linux mà bạn được phép kiểm tra, các lệnh **đọc trạng thái** hữu ích gồm:

~~~bash
# Xem các dịch vụ TCP đang lắng nghe trên máy đích.
ss -lnt

# Xem route mà máy sử dụng tới địa chỉ đích.
ip route get 10.20.30.10

# Liệt kê policy nftables nếu hệ thống dùng nftables; có thể cần quyền cao.
sudo nft -a list ruleset

# Quan sát một số packet của luồng APP -> DB; chỉ capture trên hệ thống được cấp quyền.
sudo tcpdump -ni any -c 30 'host 10.20.30.10 and tcp port 5432'

# Xem bảng trạng thái nếu Linux có cài công cụ conntrack.
sudo conntrack -L
~~~

Lệnh **nft** không đại diện cho tất cả triển khai; hệ thống có thể dùng iptables hoặc firewall appliance/cloud API. Capture có thể chứa thông tin nhạy cảm; phải tuân thủ phạm vi thu thập và bảo vệ log. Đừng đánh đồng “không thấy packet ở host” với “firewall đã drop”: packet có thể chưa đến được tuyến đó.

Một firewall thường có những nguồn bằng chứng đặc trưng:

- **Traffic/session log:** timestamp, nguồn/đích và port, protocol, interface/zone, session ID, policy ID, action.
- **NAT translation/session:** địa chỉ gốc và địa chỉ đã dịch nếu có, giúp tránh nhầm rule pre-/post-NAT.
- **Hit counter:** rule nào được khớp; cần xem khoảng thời gian/cách reset và granularity.
- **Packet trace/policy simulator:** theo các stage xử lý để tìm rule kết luận và nơi packet bị chặn.
- **Route/state table:** xác minh đường đi và tình trạng session tracking.

Log có thể chứa IP nguồn ban đầu, IP sau NAT hoặc chỉ một phần trường tùy sản phẩm. Cần biết **ý nghĩa từng cột** trước khi dựa vào chúng để sửa rule.

### 8.3. Quy trình tìm nguyên nhân khi gói bị chặn hoặc lọt qua

~~~mermaid
flowchart TD
    A["Mô tả đúng 5-tuple, hướng và thời gian"] --> B{"Packet có tới firewall? "}
    B -- "Chưa rõ / Không" --> C["Kiểm tra DNS, route, endpoint, capture"]
    B -- "Có" --> D["Xác định ingress/egress zone, NAT, policy"]
    D --> E{"Là session cũ / gói phản hồi?"}
    E -- "Có" --> F["Kiểm tra conntrack, timeout, asymmetric path"]
    E -- "Không" --> G["Kiểm tra thứ tự rule, object, default action"]
    F --> H["Đối chiếu policy ID, hit counter, log/trace"]
    G --> H
    H --> I["Đánh giá IPS/L7, routing, TLS và dịch vụ đích"]
    I --> J["Sửa cấu hình có kiểm soát rồi test lại"]
~~~

Một vài dấu hiệu và cách diễn giải:

| Quan sát | Khả năng cần kiểm tra | Không nên kết luận vội |
| --- | --- | --- |
| Client gửi SYN lặp lại, không thấy SYN+ACK | Firewall/ACL, route, dịch vụ không nhận, đường trả về lỗi | “Firewall chắc chắn chặn” |
| TCP RST trả về | Service từ chối, proxy/firewall reject hoặc thiết bị trung gian reset | “Rule deny gây ra RST” |
| Firewall báo ALLOW nhưng ứng dụng timeout | Chặng sau, response path, NAT, service, TLS, L7 inspection | “Toàn bộ mạng đã thông” |
| Rule mới không có hit | Traffic chưa tới policy, sai interface/zone, rule trước che, session cũ | “Rule bị hỏng” |
| Lưu lượng vẫn đi sau khi chuyển allow thành deny | Session cũ, rule áp sai policy, route bypass, cấu hình chưa đẩy | “Thiết bị không tôn trọng deny” |
| UDP không nhận phản hồi | Đích không xử lý, bị lọc, timeout session/NAT hoặc ứng dụng im lặng | “UDP port chắc chắn đóng” |

### 8.4. Tình huống phân tích: “đã DENY nhưng guest vẫn vào DB”

Giả sử người quản trị thấy rule **DENY GUEST → DB TCP/5432** nhưng kiểm thử từ guest vẫn kết nối được. Một quy trình có thể là:

1. Xác nhận địa chỉ nguồn thực của guest, địa chỉ/port DB và liệu luồng có đi qua đúng firewall không.
2. Mở session log/trace để xem **policy ID thực sự khớp** và địa chỉ có bị NAT/proxy biến đổi hay không.
3. Kiểm tra một rule **ALLOW rộng hơn đặt trước** có bao phủ guest không; nếu có, rule deny có thể đang bị *shadowed*.
4. Kiểm tra **session đã tồn tại** từ trước lúc thay policy, trạng thái conntrack và thời gian áp dụng rule mới.
5. Kiểm tra đường đi IPv6, interface/zone và khả năng có đường bypass.
6. Sau khi xác định nguyên nhân, sửa trong quy trình change control; test lại ca guest bị chặn **và** ca APP hợp lệ vẫn hoạt động.

Nếu chỉ chèn thêm một DENY mà không xác minh priority và policy path, lỗi có thể tiếp tục tồn tại.

## 9. Quản lý thay đổi rule để tránh rủi ro bảo mật và gián đoạn

Một rule mới có thể vô tình mở rộng bề mặt tấn công hoặc chặn DNS, giám sát, backup, kết nối quản trị và đường phản hồi. Nên có vòng đời rõ ràng:

1. **Yêu cầu:** ghi mục tiêu nghiệp vụ, threat cần giảm, nguồn/đích, giao thức/cổng, hướng, thời hạn và người sở hữu.
2. **Phân tích ảnh hưởng:** rà soát policy sẵn có, NAT, route, rule shadowing, IPv4/IPv6 và các phụ thuộc hợp lệ.
3. **Thiết kế:** ưu tiên nguồn/đích cụ thể, nguyên tắc tối thiểu quyền, rule comment và ID ổn định.
4. **Rà soát:** đánh giá tính cần thiết, phản hồi từ các đội phụ trách ứng dụng/mạng, đường quản trị và cách rollback.
5. **Triển khai:** áp cấu hình vào đúng policy, đúng vị trí ưu tiên; theo dõi session và kế hoạch xử lý khi thay đổi gây lỗi.
6. **Kiểm chứng:** chạy positive/negative tests, đối chiếu session/rule hit/log và xác nhận không phá đường đi bắt buộc.
7. **Vận hành:** thống kê unused/overly broad rules, đánh giá ngoại lệ, hết hạn rule tạm, rà soát khi hệ thống thay đổi.

Khi loại bỏ rule, cần xác nhận nó thực sự không còn cần qua inventory luồng, log theo khoảng thời gian đại diện và trao đổi với service owner. Counter bằng 0 trong một buổi kiểm tra ngắn không đủ để khẳng định rule vô dụng.

### Checklist dành cho người review

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Rule phục vụ luồng hợp lệ hay kiểm soát threat nào? | Ticket, sơ đồ luồng, threat ID và lý do |
| Nguồn/đích/cổng/hướng chính xác chưa? | Mẫu 5-tuple, topology, IP/identity objects |
| Rule được áp vào đúng policy và vị trí ưu tiên chưa? | Policy trace, rule ID, cấu hình đang chạy |
| Có chồng lấn/che khuất rule khác không? | Review rule trước/sau và kết quả test |
| Có xét NAT, state, route và IPv6 chưa? | NAT log, session table, route/zone map, test từng address family |
| Nếu dịch vụ hợp lệ hoặc trái phép thử kết nối sẽ thế nào? | Positive/negative tests có kết quả và log |
| Ai chịu trách nhiệm và khi nào rà soát? | Owner, expiry/review trigger, phương án rollback |

## 10. Các lỗi tư duy phổ biến

1. **“Cổng 443 mở là HTTPS luôn an toàn.”** TCP/443 chỉ là điều kiện L4; cần TLS, xác minh certificate và bảo vệ ứng dụng.
2. **“Rule DENY nằm đâu trong danh sách cũng chặn.”** Trong policy first-match, một ALLOW rộng trước đó có thể che mất DENY.
3. **“Rule áp cho IPv4 tự áp cho IPv6.”** Cần xác định family và policy tương ứng.
4. **“Một rule ALLOW client → server sẽ cho phép mọi phản hồi.”** Điều này chỉ đúng khi stateful processing và đường trả về phù hợp; lọc stateless cần xét phản hồi riêng.
5. **“Kết nối không được nghĩa firewall đã chặn.”** DNS, route, host firewall, service, TLS và IPS cũng có thể gây lỗi.
6. **“Bật NAT là đã có firewall.”** NAT đổi địa chỉ/cổng, không thay thế chính sách allow/deny và xác thực.
7. **“Không có hit nghĩa rule thừa.”** Có thể chưa có lưu lượng trong khoảng quan sát hoặc session không đi tới đúng policy.
8. **“Tăng độ ưu tiên rule mới luôn sửa được lỗi.”** Cần hiểu mục tiêu, điểm match, overlap và tác động lên luồng khác.
9. **“Đổi rule là phiên cũ lập tức bị chặn.”** Stateful session có thể còn tồn tại tùy cách thiết bị xử lý thay đổi policy.
10. **“Firewall là lớp bảo vệ đủ cho dữ liệu.”** Firewall giới hạn kết nối; phân quyền, xác thực, mã hóa và giám sát ứng dụng vẫn cần thiết.

## 11. Bài tập tự luyện và đáp án tham khảo

**Bài 1 – Dự đoán rule:** Một policy first-match có ba rule được xét từ trên xuống:

~~~text
10 ALLOW  10.20.10.0/24 -> 10.20.30.10  TCP/5432
20 DENY   10.20.10.25/32 -> 10.20.30.10 TCP/5432
90 DENY   any -> any
~~~

Hỏi: Kết nối mới từ 10.20.10.25 tới DB TCP/5432 được xử lý thế nào? Muốn chặn riêng máy này mà vẫn cho các máy APP khác, cần đổi gì?

**Đáp án:** Rule 10 match trước nên **ALLOW**. Rule 20 bị che khuất cho tập lưu lượng mô tả. Có thể đặt deny /32 trước allow /24, hoặc dùng allowlist chi tiết chỉ gồm các nguồn thực sự được phép; kiểm thử cả trường hợp được và bị từ chối.

**Bài 2 – Gói phản hồi:** Client 10.20.10.25:51842 mở TCP tới 10.20.30.10:5432. Với firewall stateless, chỉ có một rule cho chiều client → DB. Liệu response có tự được phép không?

**Đáp án:** Không chắc. Gói phản hồi từ 10.20.30.10:5432 về 10.20.10.25:51842 có tuple đảo chiều và có thể cần điều kiện cho đường về. Với stateful firewall, response có thể match session đã được chấp thuận nếu bảng trạng thái và đường đi phù hợp.

**Bài 3 – NAT:** Một request tới 203.0.113.20:443 được DNAT sang 10.20.10.10:443. Rule chỉ match đích 203.0.113.20 nhưng policy được đánh giá sau DNAT. Điều gì có thể xảy ra?

**Đáp án:** Rule có thể **không match** vì tại stage đó địa chỉ đích đã là 10.20.10.10. Cần kiểm tra pipeline NAT/policy của sản phẩm rồi sửa object/điểm áp rule, sau đó xác nhận bằng packet trace hoặc NAT/session log.

**Bài 4 – Phân đoạn:** GUEST không được vào DB nhưng APP được vào DB. Hãy đề xuất tối thiểu ba ca kiểm chứng.

**Đáp án gợi ý:** (1) APP hợp lệ → DB TCP/5432 **ALLOW**; (2) GUEST → DB TCP/5432 **DENY**; (3) USER hoặc workload không được phê duyệt → DB TCP/5432 **DENY**. Mỗi test cần xác nhận đường đi qua đúng firewall và log/rule hit; có thể thêm test IPv6, thay đổi IP/workload và lưu lượng phản hồi.

## 12. Ghi nhớ

**Rule matching** là việc so điều kiện của **lưu lượng thực tế tại đúng điểm đánh giá** với **policy thực sự áp dụng**. Muốn giải thích kết quả chính xác cần ghép nhiều dữ kiện: *source/destination IP, protocol/port, direction/zone, NAT, connection state, thứ tự ưu tiên, default action và đường đi*.

Một firewall được thiết kế tốt không chỉ có danh sách ALLOW/DENY hợp lý trên giấy. Chính sách phải phản ánh phân đoạn mạng và threat model, giới hạn quyền theo nhu cầu, kết hợp xác thực kết nối và các lớp giám sát IDS/IPS/DNS/VPN/cloud khi thích hợp. **Kết quả cuối cùng cần được chứng minh bằng positive/negative tests, log và trạng thái thực tế**, đồng thời có người sở hữu để duy trì và rà soát các rule khi hệ thống thay đổi.
