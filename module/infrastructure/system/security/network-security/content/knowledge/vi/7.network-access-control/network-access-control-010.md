# Rule order và shadowed rule trong Network Access Control

## 1. Vì sao thứ tự rule ảnh hưởng đến an ninh mạng?

Trong **Network Access Control (NAC)**, ACL và firewall policy kiểm soát luồng truy cập giữa các máy, VLAN, subnet, vùng an ninh, dịch vụ hoặc danh tính. Một rule thường mô tả **điều kiện khớp** (ví dụ nguồn, đích, giao thức, cổng, hướng và trạng thái kết nối) và **hành động** (cho phép, từ chối, ghi log, chuyển tiếp đến bước xử lý khác).

Trên nhiều firewall và ACL truyền thống, thiết bị đánh giá các rule **từ trên xuống dưới** và dừng ở **rule đầu tiên khớp có hành động kết thúc** (*first-match, terminal action*). Vì thế, **cùng các rule nhưng sắp xếp khác thứ tự có thể tạo ra chính sách hoàn toàn khác**.

**Shadowed rule** là rule không còn cơ hội quyết định kết quả vì những rule đứng trước đã bắt hết lưu lượng mà nó định xử lý. Một rule cấp quyền tưởng như hợp lệ có thể không bao giờ được thực thi; nguy hiểm hơn, một rule từ chối có thể bị rule cho phép rộng hơn phía trên che khuất.

Đây là chủ đề trọng tâm của module **SECURITY_NETWORK_SECURITY**, liên quan trực tiếp đến phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và kiến trúc mạng/đám mây an toàn. Muốn đánh giá đúng một chính sách, phải xác định **cách thiết bị xử lý thứ tự**, **luồng nào khớp** và **điều gì thật sự xảy ra khi rule khớp**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích cơ chế first-match và ảnh hưởng của thứ tự rule đến quyết định cho phép/từ chối.
2. Phân biệt **full shadowing**, **partial shadowing**, **redundant rule** và **overlap/conflict**.
3. Phân tích các rule theo tập lưu lượng, tìm điều kiện làm rule không thể được áp dụng.
4. Nhận ra những hệ thống có mô hình xử lý khác first-match, đặc biệt cloud security group và Kubernetes NetworkPolicy.
5. Rà soát, sửa và kiểm chứng rule theo quy trình thay đổi an toàn.

## 2. Mô hình đọc một rule

Xét chính sách ingress vào ứng dụng web trong mạng lab. Một rule minh họa có thể viết:

~~~text
ID:            R20
Direction:     ingress
Source zone:   users
Source IP:     10.20.30.0/24
Destination:   192.0.2.10/32
Protocol:      TCP
Destination:   port 443
Action:        ALLOW
Logging:       enabled
~~~

Ý nghĩa: Nếu một gói thuộc **hướng ingress được kiểm tra**, đi từ vùng **users** với IP nguồn thuộc **10.20.30.0/24**, hướng tới máy **192.0.2.10** qua **TCP/443** và đáp ứng mọi điều kiện khác của policy, rule cho phép luồng đó.

| Thuộc tính | Ví dụ | Câu hỏi khi kiểm tra |
| --- | --- | --- |
| Vị trí/priority | Rule 20 | Rule nào được đánh giá trước? Priority nhỏ hơn có nghĩa là ưu tiên cao hơn hay không? |
| Ingress/egress | ingress | Rule áp dụng tại cổng, interface, zone hoặc chiều nào? |
| Source | 10.20.30.0/24 | IP nguồn được xem trước hay sau NAT? Có đối tượng nhóm/danh tính không? |
| Destination | 192.0.2.10/32 | Là IP ảo/VIP, IP thật hay đối tượng sau NAT? |
| Protocol | TCP | Có phân biệt TCP, UDP, ICMP và các protocol khác không? |
| Port | 443 | Có lọc destination port, source port hay service object không? |
| Stateful condition | new, established... | Trạng thái phiên có khiến traffic bỏ qua một phần kiểm tra không? |
| Time/identity/application | Ca làm việc, user, app | Các điều kiện động có được áp dụng và cập nhật như thế nào? |
| Action | allow/deny/reject | Khớp rule có dừng xử lý hay chỉ ghi log/đánh dấu? |
| Log/counter | Enabled | Có hit counter và log theo rule hay chỉ theo phiên? |

Địa chỉ **192.0.2.10** thuộc dải ví dụ TEST-NET-1. Các mạng **10.x.x.x** là địa chỉ riêng theo RFC 1918; bài này dùng chúng để trình bày logic, không mô tả hệ thống đang vận hành.

### 2.1. First-match: luồng xử lý

~~~mermaid
flowchart TD
    A["Nhận lưu lượng cần kiểm tra"] --> B["Xác định policy set / hướng / zone"]
    B --> C["Kiểm tra rule ưu tiên cao nhất"]
    C --> D{"Có khớp mọi điều kiện?"}
    D -- "Không" --> E["Xét rule kế tiếp"]
    E --> F{"Còn rule?"}
    F -- "Có" --> D
    F -- "Không" --> G["Áp dụng hành động mặc định"]
    D -- "Có, action kết thúc" --> H["ALLOW hoặc DENY/REJECT"]
~~~

Sơ đồ mô tả một **policy set với các hành động kết thúc**. Trong thực tế, thiết bị có thể có các bước xử lý trước policy, nhiều giai đoạn policy, rule kiểu **continue/jump/return**, NAT, kiểm tra session, hoặc phần cứng tối ưu hóa việc so khớp. Do đó, **first-match là giả định cần kiểm tra trên đúng sản phẩm và đúng loại rule**, không phải định luật chung của mọi giải pháp NAC.

### 2.2. Một bộ policy mẫu

Giả sử áp dụng first-match với thứ tự từ trên xuống:

| Thứ tự | ID | Source | Destination | Protocol/port | Action | Ý định |
| ---: | --- | --- | --- | --- | --- | --- |
| 10 | R10 | 10.20.0.0/16 | 192.0.2.10 | TCP / mọi cổng | **DENY** | Chặn nhóm mạng users |
| 20 | R20 | 10.20.30.0/24 | 192.0.2.10 | TCP / 443 | **ALLOW** | Cho nhóm admin truy cập HTTPS |
| 30 | R30 | 10.30.0.0/16 | 192.0.2.10 | TCP / 443 | **ALLOW** | Cho nhóm backend truy cập HTTPS |
| 40 | R40 | Mọi nguồn | Mọi đích | Mọi protocol | **DENY** | Từ chối các luồng còn lại |

Khi **10.20.30.5 → 192.0.2.10:443/TCP**, gói khớp **R10** trước R20, vì 10.20.30.5 nằm trong 10.20.0.0/16. Kết quả là **DENY**; R20 không bao giờ được xét cho luồng này.

Trong khi đó **10.30.5.5 → 192.0.2.10:443/TCP** không khớp R10/R20, rồi khớp **R30** và được **ALLOW**.

**Vấn đề:** R20 được thiết kế để cho admin truy cập HTTPS nhưng bị R10 chặn toàn bộ. Đây là một **fully shadowed rule**.

## 3. Shadowed rule là gì và vì sao xuất hiện?

Gọi **M(R)** là tập tất cả luồng khớp điều kiện của rule R, có tính đến zone, IP, protocol, port, hướng, thời gian, danh tính và những điều kiện thực tế khác.

Trong **một chuỗi first-match với action kết thúc**, phần lưu lượng còn có thể tới rule Rk là:

\[
E(R_k) = M(R_k) \setminus \bigcup_{i<k} M(R_i)
\]

Trong đó **E(Rk)** là *effective match set* của Rk, còn hợp các tập đứng trước là vùng lưu lượng đã bị xử lý trước khi đến Rk.

- **Full shadowing:** E(Rk) rỗng. Không tồn tại luồng nào có thể đến Rk.
- **Partial shadowing:** E(Rk) không rỗng, nhưng nhỏ hơn M(Rk). Rule vẫn xử lý được **một phần** luồng dự kiến.
- **Không bị shadow:** E(Rk) bằng M(Rk). Các rule trước không giành xử lý lưu lượng thuộc Rk.

**Quan trọng:** Rk có thể bị che hoàn toàn bởi **một rule** đứng trước hoặc bởi **hợp của nhiều rule** đứng trước. Chỉ so từng cặp rule sẽ bỏ sót các trường hợp bị che bởi nhiều rule kết hợp.

### 3.1. Full shadowing

~~~text
R10: DENY   src=10.20.0.0/16    dst=192.0.2.10   TCP any-port
R20: ALLOW  src=10.20.30.0/24   dst=192.0.2.10   TCP 443
~~~

Mọi luồng khớp R20 cũng khớp R10. Do R10 đứng trước và kết thúc việc đánh giá, **R20 hoàn toàn không có tác dụng** trong policy này.

Nguyên nhân có thể là sơ suất thứ tự, thêm một rule tổng quát mới lên trên, đổi subnet trong object, hoặc nhập policy giữa các vùng/thiết bị mà không kiểm tra lại thứ tự.

### 3.2. Partial shadowing

~~~text
P10: ALLOW  src=10.20.0.0/24    dst=192.0.2.10   TCP 443
P20: DENY   src=10.20.0.0/23    dst=192.0.2.10   TCP 443
~~~

Ở đây **10.20.0.0/23** bao phủ hai subnet **10.20.0.0/24** và **10.20.1.0/24**.

- Lưu lượng từ **10.20.0.0/24** khớp P10 trước nên được ALLOW, không tới P20.
- Lưu lượng từ **10.20.1.0/24** không khớp P10 nhưng khớp P20 nên bị DENY.

P20 **bị shadow một phần**. Nếu người thiết kế muốn chặn toàn bộ **10.20.0.0/23**, policy hiện tại không đạt ý định. Nếu muốn cho phép nhánh **10.20.0.0/24** và chặn phần còn lại, thứ tự này có thể **hoàn toàn có chủ đích**.

### 3.3. Full shadowing bởi nhiều rule

~~~text
Q10: DENY  src=10.20.0.0/25     dst=192.0.2.10  TCP 443
Q20: DENY  src=10.20.0.128/25   dst=192.0.2.10  TCP 443
Q30: ALLOW src=10.20.0.0/24     dst=192.0.2.10  TCP 443
~~~

Không rule nào trong Q10 hoặc Q20 **một mình** bao phủ Q30. Nhưng hợp của hai subnet **/25** bao phủ toàn bộ **/24**, nên Q30 vẫn **fully shadowed**.

Đây là lý do bộ phân tích chuyên dụng có thể cần tính toán trên **tập IP, khoảng cổng, protocol, điều kiện identity và tập hợp nhiều rule**, thay vì chỉ so sánh văn bản giữa hai dòng policy.

## 4. Shadowing, redundancy, overlap và conflict

Các thuật ngữ thường bị dùng lẫn nhau, nhưng sự khác biệt ảnh hưởng tới quyết định sửa.

| Thuật ngữ | Mô tả theo tập lưu lượng | Ví dụ | Hệ quả |
| --- | --- | --- | --- |
| **Full shadowing** | Toàn bộ M(R) đã bị các rule trước xử lý | DENY TCP any-port đứng trước ALLOW TCP 443 cùng phạm vi | Rule sau không bao giờ quyết định |
| **Partial shadowing** | Chỉ một phần M(R) đã được xử lý | ALLOW một /24 đứng trước DENY /23 | Hành vi trên phạm vi bị chia theo thứ tự |
| **Redundant rule** | Bỏ rule không đổi hành vi cần bảo toàn theo tiêu chí đã xác định | Hai rule ALLOW hoàn toàn giống nhau, không khác logging/counter/side effect | Có thể dọn sau khi xác minh ý nghĩa toàn policy |
| **Overlap** | Hai rule có tập lưu lượng giao nhau | TCP 443 của một /24 và TCP 443 của /23 | Chưa đủ kết luận có lỗi |
| **Conflict** | Hai rule có hành động/ý định trái nhau trên phần giao nhau | ALLOW và DENY cùng một phạm vi | Thứ tự hoặc cơ chế xử lý quyết định hành vi |
| **Unreachable rule** | Không có đường thực thi tới rule trong ngữ cảnh policy | Rule nằm sau terminal deny all | Không nhất thiết do riêng IP/port; còn có thể do cấu trúc xử lý |

**Shadowing là quan hệ về khả năng được đánh giá**, còn redundancy là **mức độ thay đổi hành vi nếu loại bỏ một rule**. Hai khái niệm liên quan nhưng không đồng nhất.

Ví dụ:

~~~text
S10: ALLOW  src=10.20.0.0/16  dst=192.0.2.10  TCP 443
S20: ALLOW  src=10.20.30.0/24 dst=192.0.2.10  TCP 443
~~~

S20 bị S10 che hoàn toàn và có vẻ dư thừa về kết quả **ALLOW**. Tuy nhiên, nếu S20 từng được dùng để ghi log riêng, áp QoS, gắn profile kiểm tra nội dung, giới hạn theo thời gian hoặc là điểm chuẩn bị cho thay đổi tương lai, **không được xóa chỉ dựa vào action giống nhau**.

Ngược lại:

~~~text
S10: ALLOW  src=10.20.0.0/16  dst=192.0.2.10  TCP 443
S20: DENY   src=10.20.30.0/24 dst=192.0.2.10  TCP 443
~~~

S20 bị che hoàn toàn, nhưng lần này **hậu quả an ninh** có thể nghiêm trọng: lưu lượng từ 10.20.30.0/24 được cho phép vì S10, trái với ý định từ chối của S20. Đây không phải trường hợp nên tự động xóa S20 để “dọn policy”.

## 5. Rule order có giống nhau trên mọi nền tảng không?

**Không.** Phải kiểm tra tài liệu và cấu hình thật của từng cơ chế trước khi kết luận rule bị shadow.

| Nền tảng/cơ chế | Đặc điểm xử lý điển hình | Hệ quả khi rà soát |
| --- | --- | --- |
| **ACL router/switch kiểu ordered** | Các dòng ACE được đánh giá theo thứ tự có hiệu lực, thường dừng tại match đầu tiên | Rule rộng đứng trước có thể che rule hẹp |
| **Firewall policy kiểu first-match** | Policy được chọn theo thứ tự/priority, với terminal allow/deny; có thể thêm kiểm tra state, application, security profile | Phải xét cả action và ngữ cảnh phiên/giai đoạn policy |
| **AWS Network ACL (NACL)** | Rule có số thứ tự, số nhỏ được xét trước; **stateless**, có inbound và outbound riêng | Có shadowing theo thứ tự; phải xét lưu lượng trả về và port phù hợp |
| **AWS Security Group** | Rules cho phép được **tổng hợp**; không dựa trên first-match deny/allow theo thứ tự, và cơ chế SG có tính stateful | Không áp dụng khái niệm “deny phía trên che allow phía dưới” như ACL ordered |
| **Azure Network Security Group (NSG)** | Rule được ưu tiên theo **priority số nhỏ trước**, first-match trong hướng áp dụng, có default rules | Rule có priority cao hơn (số nhỏ hơn) có thể che rule sau |
| **Kubernetes NetworkPolicy chuẩn** | Những policy áp dụng cho pod được **kết hợp** theo tập điều kiện cho phép; không có thứ tự ALLOW/DENY theo dòng kiểu ACL | Phân tích cô lập ingress/egress và **hợp các allow**, không dùng thuật toán shadowing first-match |
| **Cơ chế mở rộng/CNI, WAF, service mesh** | Có thể có priority, nhiều policy tier, action continue hoặc deny rõ ràng | Phải đọc mô hình thực thi và quy tắc ưu tiên của đúng sản phẩm |

**Ví dụ quan trọng:** AWS Security Group không có luật DENY tường minh như NACL; không thể “di chuyển một deny rule lên đầu Security Group” để chặn truy cập. Cần sửa các **allow rule** đang mở rộng quyền hoặc dùng một lớp kiểm soát có khả năng từ chối tương ứng.

Với **Kubernetes NetworkPolicy**, khi pod được chọn và trở thành isolated theo một hướng, kết quả cho phép là hợp các policy áp dụng cho hướng đó, theo mô hình chuẩn. Một policy allow rộng và một policy allow hẹp không tạo hiệu ứng first-match. Nếu dùng CNI có chính sách mở rộng hỗ trợ deny/priority/tier, phân tích phải theo **ngữ nghĩa của phần mở rộng**, không suy ra từ chuẩn Kubernetes.

### 5.1. Những cơ chế không nên nhập nhằng

- **Route selection / longest-prefix match:** Router chọn tuyến theo prefix và các tiêu chí định tuyến; đây **không phải** thứ tự first-match của ACL.
- **Security policy và NAT policy:** Tùy sản phẩm, NAT có thể diễn ra trước hoặc sau các bước kiểm tra nhất định. Địa chỉ/cổng hiển thị cho rule phải khớp giai đoạn thực tế.
- **Connection tracking:** Luồng trả về của một phiên stateful có thể được cho phép dựa trên trạng thái phiên, không cần xét lại mọi rule như gói SYN mới.
- **Implicit default action:** Có nền tảng mặc định deny, có nền tảng triển khai default rules khác. Không giả định mọi hệ thống đều có một rule “deny any any” đang hoạt động theo cùng cách.
- **Rule action không kết thúc:** Match một rule ghi log/mark/continue có thể **không** chặn việc xét rule phía dưới.

## 6. Phân tích shadowed rule bằng tư duy tập hợp

Muốn xác định R2 có bị R1 che hay không trong policy first-match, phải kiểm tra **tất cả chiều** của điều kiện:

~~~text
Phạm vi nguồn IP của R2        ⊆ phạm vi nguồn IP của R1?
Phạm vi đích IP của R2         ⊆ phạm vi đích IP của R1?
Giao thức của R2               ⊆ giao thức của R1?
Cổng/nhóm dịch vụ của R2       ⊆ cổng/nhóm dịch vụ của R1?
Zone/interface/hướng của R2    ⊆ phạm vi áp dụng của R1?
Identity/app/schedule của R2   ⊆ điều kiện tương ứng của R1?
Action của R1 có kết thúc việc đánh giá trước R2?
~~~

Nếu **một rule trước** bao phủ tất cả chiều, thì R2 bị shadow hoàn toàn. Nếu không, vẫn cần xem **hợp nhiều rule trước**.

### 6.1. Ví dụ với CIDR và port

| Rule | Source | Destination | Protocol | Port | Có bao phủ rule phía sau? |
| --- | --- | --- | --- | --- | --- |
| A | 10.20.0.0/16 | 192.0.2.10/32 | TCP | mọi cổng | Bao phủ B |
| B | 10.20.30.0/24 | 192.0.2.10/32 | TCP | 443 | B nằm trọn trong A |
| C | 10.20.0.0/16 | 192.0.2.10/32 | UDP | 443 | **Không** bao phủ B vì khác protocol |
| D | 10.20.0.0/16 | 192.0.2.20/32 | TCP | 443 | **Không** bao phủ B vì khác destination |
| E | 10.20.0.0/16 | 192.0.2.10/32 | TCP | 80 | **Không** bao phủ B vì khác port |
| F | 10.20.0.0/16 | 192.0.2.10/32 | TCP | 443–8443 | Bao phủ B nếu khoảng cổng có chứa 443 |

**Lưu ý port:** Trong firewall rule, một “service” có thể gồm **protocol + source port + destination port** hoặc các thuộc tính khác. “TCP/443” thường được hiểu là *destination port 443*, nhưng phải kiểm tra đối tượng service cụ thể. Không được chỉ so số cổng mà bỏ qua protocol.

### 6.2. Độ phức tạp tăng khi dùng object group

Một rule có thể trỏ tới object động:

~~~text
R10: DENY  source=ALL_CORPORATE_SUBNETS  destination=APP_INTERNAL
R20: ALLOW source=PAYROLL_TEAM         destination=APP_INTERNAL TCP/443
~~~

Nếu **PAYROLL_TEAM** nằm trong **ALL_CORPORATE_SUBNETS**, R20 có thể bị che. Nhưng các nhóm có thể thay đổi theo ngày, danh tính, địa chỉ động, FQDN hoặc policy cập nhật từ hệ thống quản lý tập trung. Báo cáo phân tích phải ghi **thời điểm và phiên bản object** dùng để đưa ra kết luận.

Tương tự, rule được bật trong một time window có thể chỉ che một phần thời gian của rule khác. Một rule theo **application identity** không thể được quy đổi hoàn toàn thành TCP/443 nếu ứng dụng được nhận diện ở giai đoạn khác của phiên.

## 7. Cách khắc phục: sửa đúng ý định truy cập

Quay lại bộ rule:

~~~text
R10 DENY  10.20.0.0/16    -> 192.0.2.10   TCP any
R20 ALLOW 10.20.30.0/24   -> 192.0.2.10   TCP 443
R30 ALLOW 10.30.0.0/16    -> 192.0.2.10   TCP 443
R40 DENY  any             -> any           any
~~~

Nếu yêu cầu nghiệp vụ đã được xác minh là **nhóm admin 10.20.30.0/24 chỉ được truy cập ứng dụng qua TCP/443**, một cách sửa cho policy first-match là đặt ngoại lệ hẹp lên trước deny rộng:

~~~text
R20 ALLOW 10.20.30.0/24   -> 192.0.2.10   TCP 443
R10 DENY  10.20.0.0/16    -> 192.0.2.10   TCP any
R30 ALLOW 10.30.0.0/16    -> 192.0.2.10   TCP 443
R40 DENY  any             -> any           any
~~~

**Kết quả dự kiến:**

- Admin **10.20.30.5 → 192.0.2.10:443/TCP** khớp R20, được **ALLOW**.
- Cùng admin truy cập **TCP/22** không khớp R20, bị R10 **DENY**.
- User **10.20.40.5 → 192.0.2.10:443/TCP** không khớp R20, bị R10 **DENY**.
- Backend **10.30.5.5 → 192.0.2.10:443/TCP** khớp R30, được **ALLOW**.
- Nguồn khác bị R40 từ chối nếu không khớp rule trước.

Tuy nhiên, việc **đưa một allow lên trên deny** thực chất mở quyền mới trên phạm vi hẹp. Trước khi thay đổi, đội vận hành phải xác minh rằng quyền này **thật sự được phê duyệt**, không phải do một rule sai hoặc không còn hiệu lực. Các phương án khác có thể phù hợp hơn:

1. **Giữ deny:** Nếu người dùng không được phép truy cập, xóa hoặc vô hiệu hóa allow bị shadow sau khi bảo đảm không cần hành vi log/profile.
2. **Đổi scope của deny:** Chia subnet/đối tượng để không chặn ngoại lệ hợp lệ, khi mô hình policy yêu cầu diễn đạt tách biệt.
3. **Di chuyển ngoại lệ hẹp lên trước:** Chỉ khi hành vi cho phép đúng với chính sách được duyệt.
4. **Chuẩn hóa nhóm và service object:** Thay nhóm IP quá rộng bằng nhóm có owner rõ ràng và hạn mức đặc quyền phù hợp.
5. **Tách policy set/zone:** Khi các rule phục vụ những ranh giới khác nhau, cân nhắc kiến trúc policy dễ kiểm tra hơn.

Không áp dụng máy móc “đặt DENY trước mọi ALLOW” hoặc “đặt ALLOW trước mọi DENY”. **Thứ tự phải phản ánh ngoại lệ và nguyên tắc quyền tối thiểu** trong ngữ nghĩa thực tế của platform.

## 8. Quy trình rà soát policy đang vận hành

### Bước 1. Lấy đúng phiên bản cấu hình và phạm vi

Ghi lại thiết bị/tenant, phiên bản software, tên policy set, hướng ingress/egress, zone/interface, đối tượng source/destination, rule priority và chính sách mặc định. Khi có thay đổi đang chờ triển khai, phân biệt **cấu hình đã commit/push** với bản nháp trong hệ thống quản trị.

### Bước 2. Xác minh ngữ nghĩa xử lý

Kiểm tra trên đúng loại thiết bị:

- Quy tắc **first-match, last-match, priority hoặc additive**?
- Action nào kết thúc xử lý? Có action **continue**, policy tier, exception không?
- Có stateful tracking, pre-rule/post-rule, NAT, identity mapping hoặc application-based rule?
- Rule được đánh giá ở hướng nào và ở giai đoạn nào của đường đi?

### Bước 3. Lập danh sách rule có rủi ro

Ưu tiên kiểm tra **allow rộng đứng trước deny hẹp**, deny rộng trước allow hẹp, rule không có lượt hit, đối tượng nguồn/đích quá rộng, rule sử dụng any-any, policy tạm thời đã hết hạn, hoặc nhóm object không còn chủ sở hữu.

**Hit count = 0 không chứng minh shadowing.** Có thể đơn giản là chưa có lưu lượng, bộ đếm mới reset, dữ liệu đi đường khác hoặc thiết bị đếm theo phiên/thành phần phần cứng. Ngược lại, hit count khác 0 cũng không chứng minh mọi thành phần của rule đều đã được kiểm tra theo đúng ý định.

### Bước 4. Phân tích tập khớp

So sánh M(R) với các M(rule đứng trước), gồm các điều kiện IP, port, zone, identity, ứng dụng, thời gian và những điều kiện quan trọng khác. Nếu cần kết luận **full shadow**, chứng minh có bao phủ đầy đủ; nếu **partial**, xác định được phân vùng nào còn hiệu lực.

### Bước 5. Xác minh mục đích và người chịu trách nhiệm

Đối chiếu change ticket, yêu cầu ứng dụng, data flow, chủ hệ thống và mức phân loại dữ liệu. Một rule có vẻ “thừa” có thể thực chất là biện pháp chặn bắt buộc hoặc một ngoại lệ đang bị che.

### Bước 6. Mô phỏng thay đổi và kiểm thử

Lập bộ luồng mong đợi được **ALLOW** và bộ luồng phải **DENY**. Dùng policy simulator/packet-tracer có sẵn trên thiết bị nếu có và môi trường staging/lab được phê duyệt. Sau đó rà soát cấu hình dự kiến, phê duyệt, áp dụng theo quy trình, quan sát log và sẵn sàng rollback.

### Bước 7. Xác minh sau thay đổi

Kiểm tra các luồng hợp lệ, luồng bị từ chối, session mới/đã tồn tại, lưu lượng trả về, DNS và đường qua VPN hoặc NAT nếu liên quan. Ghi lại phiên bản cấu hình, thời điểm áp dụng, kết quả kiểm thử và owner.

## 9. Thực hành phân tích first-match bằng Python

Bài lab dùng dữ liệu mô phỏng tại máy cục bộ, không kết nối thiết bị mạng và không tự thay đổi firewall. Đầu tiên, mô phỏng đúng tập rule R10–R40 ở mục 2, sau đó phát hiện trường hợp một rule **bị che hoàn toàn bởi một rule đứng trước**.

~~~python
from ipaddress import ip_address, ip_network

# dst_ports=None được hiểu là "mọi cổng" trong mô hình đơn giản này.
rules = [
    {"id": "R10", "src": "10.20.0.0/16",
     "dst": "192.0.2.10/32", "proto": "tcp", "dst_ports": None,
     "action": "DENY"},
    {"id": "R20", "src": "10.20.30.0/24",
     "dst": "192.0.2.10/32", "proto": "tcp", "dst_ports": {443},
     "action": "ALLOW"},
    {"id": "R30", "src": "10.30.0.0/16",
     "dst": "192.0.2.10/32", "proto": "tcp", "dst_ports": {443},
     "action": "ALLOW"},
    {"id": "R40", "src": "0.0.0.0/0",
     "dst": "0.0.0.0/0", "proto": "any", "dst_ports": None,
     "action": "DENY"},
]


def matches(rule, packet):
    if ip_address(packet["src"]) not in ip_network(rule["src"]):
        return False
    if ip_address(packet["dst"]) not in ip_network(rule["dst"]):
        return False
    if rule["proto"] != "any" and rule["proto"] != packet["proto"]:
        return False
    if rule["dst_ports"] is not None:
        if packet["proto"] not in ("tcp", "udp"):
            return False
        if packet["dst_port"] not in rule["dst_ports"]:
            return False
    return True


def evaluate(ordered_rules, packet):
    for rule in ordered_rules:
        if matches(rule, packet):
            return (rule["id"], rule["action"])
    return ("DEFAULT", "DENY")


def fully_shadows(earlier, later):
    # Đúng cho mô hình IPv4, terminal first-match và protocol
    # tcp/udp/any; không mô hình hóa zone, source port, NAT,
    # session, schedules hay nhóm object động.
    if not ip_network(later["src"]).subnet_of(ip_network(earlier["src"])):
        return False
    if not ip_network(later["dst"]).subnet_of(ip_network(earlier["dst"])):
        return False
    if earlier["proto"] != "any" and earlier["proto"] != later["proto"]:
        return False
    if earlier["dst_ports"] is None:
        return True
    if later["dst_ports"] is None:
        return False
    return later["dst_ports"].issubset(earlier["dst_ports"])


admin_https = {
    "src": "10.20.30.5",
    "dst": "192.0.2.10",
    "proto": "tcp",
    "dst_port": 443,
}
backend_https = {
    "src": "10.30.5.5",
    "dst": "192.0.2.10",
    "proto": "tcp",
    "dst_port": 443,
}

print("R10 che R20:", fully_shadows(rules[0], rules[1]))
print("Admin trước sửa:", evaluate(rules, admin_https))
print("Backend:", evaluate(rules, backend_https))

# Chỉ thay thứ tự cho bộ mô phỏng; không thay firewall thật.
reordered = [rules[1], rules[0], rules[2], rules[3]]
print("Admin sau đổi thứ tự:", evaluate(reordered, admin_https))
~~~

Kết quả dự kiến:

~~~text
R10 che R20: True
Admin trước sửa: ('R10', 'DENY')
Backend: ('R30', 'ALLOW')
Admin sau đổi thứ tự: ('R20', 'ALLOW')
~~~

**Giới hạn thuật toán:**

- Hàm **fully_shadows** chỉ kiểm tra **một rule đứng trước có bao phủ trọn một rule đứng sau**; nó không tìm được full shadow do **hợp nhiều rule** như Q10 + Q20 trong mục 3.3.
- Mô hình chỉ có IPv4, source/destination, protocol, destination port và terminal action. Nó **không đại diện cho policy production** với NAT, IPv6, stateful inspection, identity, user group, zone, schedule, application detection, FQDN hoặc nhiều giai đoạn xử lý.
- **ALLOW** trong mô hình nghĩa là quyết định của policy đơn giản, không đảm bảo luồng ngoài đời sẽ kết nối thành công: routing, DNS, service health, TLS, ACL khác, IDS/IPS và host firewall vẫn có thể từ chối.
- Bài lab không tính tới log, profile kiểm tra nội dung hoặc QoS; vì vậy **không** được dùng nó để tự động đề xuất xóa rule.

### Bài tập mở rộng

1. Thêm gói **10.20.30.5 → 192.0.2.10:22/TCP**; dự đoán kết quả trước và sau khi đổi thứ tự.
2. Thêm một rule **ALLOW UDP/443** nằm trước R20; kiểm tra vì sao nó **không** che R20/TCP.
3. Mô phỏng Q10/Q20/Q30 ở mục 3.3; giải thích vì sao hàm **fully_shadows** kiểm tra cặp vẫn trả false cho từng cặp, dù Q30 không bao giờ được áp dụng.
4. Bổ sung cơ chế báo cáo luồng nào được rule đầu tiên khớp, từ đó tạo bảng regression test trước khi sửa cấu hình.

## 10. Case study: phân đoạn mạng quản trị bị mở sai

**Bối cảnh giả định:** Hệ thống có ba vùng:

~~~mermaid
flowchart LR
    U["Users VLAN: 10.20.0.0/16"] --> F["Firewall / NAC"]
    A["Admin VLAN: 10.20.30.0/24"] --> F
    B["Backend VLAN: 10.30.0.0/16"] --> F
    F --> W["Ứng dụng: 192.0.2.10 TCP/443"]
~~~

Admin VLAN **là subnet nằm trong dải 10.20.0.0/16** theo ví dụ địa chỉ; không nên xem biểu đồ như một thiết kế VLAN vận hành chính thức nếu hai nhánh được yêu cầu tách biệt ở tầng 2/3. Chính sự bao phủ này là tình huống cần phân tích.

### Tình huống A: deny rộng che allow hợp lệ

Đội vận hành có yêu cầu cho phép admin vào ứng dụng qua 443, nhưng ACL phía trước đã từ chối **10.20.0.0/16**. Sau khi triển khai, admin không truy cập được. Lệnh thử kết nối thất bại là **triệu chứng**, còn bằng chứng quyết định là đường khớp rule (R10 được chọn trước R20), cùng cấu hình đúng thiết bị/đúng hướng.

**Khắc phục:** Xác minh ngoại lệ được phê duyệt; đặt rule cho phép hẹp ở vị trí phù hợp hoặc điều chỉnh deny đúng phạm vi; kiểm thử admin/nhóm khác và toàn bộ luồng liên quan.

### Tình huống B: allow rộng che deny quan trọng

Sau một lần di chuyển policy, một rule **ALLOW 10.20.0.0/16 → 192.0.2.10 TCP/443** bị đặt trước rule **DENY 10.20.40.0/24**. Người dùng ở 10.20.40.0/24 được cho phép ngoài ý định phân đoạn; rule DENY vẫn tồn tại nhưng không bao giờ quyết định cho luồng này.

**Tác động:** Ranh giới giữa nhóm người dùng không có quyền và ứng dụng nhạy cảm bị suy yếu. Firewall có thể vẫn ghi nhận traffic “allowed”, còn hệ thống ứng dụng cần tiếp tục xác thực và phân quyền để giới hạn tác động.

**Khắc phục:** Trả deny/exception về thứ tự và phạm vi được duyệt, giảm rule allow quá rộng, kiểm tra cả traffic chưa được quan sát và đánh giá liệu đã có truy cập trái phép hay chưa bằng log có thẩm quyền.

### Tình huống C: traffic qua VPN hoặc NAT khác với policy tưởng tượng

Một user từ xa đi qua VPN và được cấp IP trong **10.40.0.0/16**. Policy chỉ allow mạng văn phòng **10.20.30.0/24**, nên user VPN không khớp. Ở một thiết kế khác, thiết bị có thể thực hiện NAT trước một bước policy và thay đổi IP được dùng để so khớp.

**Bài học:** Không chẩn đoán lỗi chỉ dựa vào địa chỉ IP gốc do người dùng báo. Phải biết IP/zone mà rule engine thực sự thấy, đối tượng address group, xử lý NAT và vị trí áp dụng policy. **Không** tự thêm any-any để “làm VPN chạy” trước khi tìm nguyên nhân.

## 11. Ma trận kiểm thử trước và sau khi sửa thứ tự

Một bộ regression test mẫu cho chính sách đã sửa ở mục 7:

| Nguồn | Đích | Giao thức/cổng | Kết quả mong đợi | Rule quyết định |
| --- | --- | --- | --- | --- |
| 10.20.30.5 | 192.0.2.10 | TCP/443 | **ALLOW** | R20 |
| 10.20.30.5 | 192.0.2.10 | TCP/22 | **DENY** | R10 |
| 10.20.40.5 | 192.0.2.10 | TCP/443 | **DENY** | R10 |
| 10.30.5.5 | 192.0.2.10 | TCP/443 | **ALLOW** | R30 |
| 10.30.5.5 | 192.0.2.10 | TCP/22 | **DENY** | R40 |
| 172.16.1.5 | 192.0.2.10 | TCP/443 | **DENY** | R40 |
| 10.20.30.5 | 192.0.2.20 | TCP/443 | **DENY** | R40 |

Hãy ghi kết quả tại ba cấp:

1. **Static policy analysis:** Theo cấu hình, rule nào sẽ khớp trước?
2. **Policy simulation:** Công cụ mô phỏng của thiết bị cho quyết định nào với địa chỉ, zone, NAT và state thực tế?
3. **End-to-end validation:** Truy cập dịch vụ thật (trong môi trường/phạm vi được phép) có phù hợp với ý định, xét cả DNS, TCP, TLS, ứng dụng và đường trả về không?

Ba cấp độ có thể cho kết quả khác nhau nếu policy không được áp dụng vào đúng luồng, có một lớp firewall khác, session đã tồn tại hoặc service ngừng hoạt động. Hãy ghi nguyên nhân cụ thể, không suy từ “ping thất bại” ra “rule DENY đã hoạt động”.

## 12. Kết hợp rule review với logging và giám sát

| Tín hiệu | Cách sử dụng | Lưu ý |
| --- | --- | --- |
| **Rule hit counter** | Tìm rule chưa từng khớp hoặc bất thường về tần suất | Có thể reset, tính theo session, tối ưu phần cứng hoặc không ghi mọi gói |
| **Deny log** | Nhận diện luồng bị từ chối, service bị gián đoạn | Thiếu log không chứng minh không có deny; cần kiểm tra sampling và policy log |
| **Allow log / session log** | Xác minh nguồn/đích và rule đang cho phép | Không chứng minh ứng dụng đã xử lý thành công hoặc người dùng được phép |
| **Traffic flow logs** | Đối chiếu quan hệ mạng giữa zone/subnet và đường đi | Nhiều hệ thống flow log không nêu rule ID hoặc nội dung ứng dụng |
| **Change/audit logs** | Tìm thời điểm rule, priority, address group bị sửa | Liên kết commit, người phê duyệt và hoạt động deploy |
| **IDS/IPS/NDR** | Phát hiện luồng bất thường dù ACL đã cho phép | Hệ thống giám sát không thay chính sách truy cập và có thể bị giới hạn bởi mã hóa |

Đặt cảnh báo cho những thay đổi có thể mở quyền bất ngờ: **allow any-any**, mở rộng source group, thêm rule ưu tiên cao với phạm vi rộng, bỏ deny, hoặc xóa quy tắc kiểm soát giữa các vùng. Cần điều chỉnh ngưỡng để giảm cảnh báo cho những thay đổi định kỳ đã được phê duyệt.

## 13. Những lỗi tư duy phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có rule ALLOW nghĩa là luồng chắc chắn được cho phép.” | Với first-match, ALLOW có thể bị rule đứng trước che; các lớp kiểm soát khác cũng có thể chặn. |
| “Rule không có hit thì nên xóa.” | Hit thấp có thể do ít lưu lượng, counter reset, interface không đúng hoặc shadow; phải xác minh mục đích. |
| “Cứ rule cụ thể hơn thì tự động thắng.” | Đây có thể là quy tắc của **routing prefix**, không phải ACL first-match; cần xét thứ tự thực tế. |
| “Hai rule trùng điều kiện đều có thể xóa một.” | Logging, tracking, inspection, schedule và ý định audit có thể khác; phải đánh giá toàn policy. |
| “DENY lúc nào cũng phải đặt trước ALLOW.” | Ngoại lệ hẹp được phê duyệt có thể cần đứng trước một deny rộng; điều cốt lõi là quyền tối thiểu và logic đúng. |
| “Security Group, NACL và Kubernetes NetworkPolicy đều xử lý như ACL của router.” | Mỗi cơ chế có mô hình khác nhau; đặc biệt SG và NetworkPolicy chuẩn dùng cách tổng hợp allow. |
| “Một rule bị shadow nghĩa là thiết bị bị tấn công.” | Có thể là lỗi cấu hình hoặc ngoại lệ có chủ đích; phải đánh giá tác động và bằng chứng. |
| “Thứ tự policy cố định, không bị ảnh hưởng khi sửa object.” | Đổi address/service group có thể làm phạm vi bao phủ thay đổi mà **không cần** đổi vị trí rule. |
| “Chỉ kiểm tra chiều đi là đủ.” | Với stateless ACL/NACL cần kiểm tra chiều về; với stateful vẫn phải xem ranh giới phiên và policy khác. |
| “Firewall ALLOW đồng nghĩa người dùng có quyền đọc dữ liệu.” | Xác thực và phân quyền tại ứng dụng vẫn cần kiểm tra; mạng chỉ là một lớp bảo vệ. |

## 14. Câu hỏi tự kiểm tra

1. **First-match nghĩa là gì?** Rule đầu tiên có điều kiện khớp và hành động kết thúc quyết định xử lý lưu lượng trong policy set được áp dụng.
2. **Vì sao R20 trong ví dụ bị shadow?** Toàn bộ tập nguồn, đích, protocol và cổng của R20 đã được R10 bao phủ; R10 đứng trước và kết thúc bằng DENY.
3. **Full shadowing bởi hai rule có khác full shadowing bởi một rule không?** Về kết quả, đều làm rule sau không còn traffic; về cách phát hiện, cần xét **hợp các tập rule trước**.
4. **Partial shadowing có luôn là lỗi không?** Không; có thể là ngoại lệ được thiết kế có chủ đích. Cần kiểm tra yêu cầu nghiệp vụ.
5. **Cho ví dụ overlap không tạo full shadow.** ALLOW cho 10.20.0.0/24 TCP/443 đứng trước DENY cho 10.20.0.0/23 TCP/443; phần 10.20.1.0/24 vẫn tới rule DENY.
6. **Vì sao đổi thứ tự giữa ALLOW rộng và DENY hẹp có thể làm tăng rủi ro?** Nếu ALLOW đứng trước, lưu lượng cần bị chặn có thể được cho qua; deny không được đánh giá.
7. **Vì sao không áp dụng phát hiện shadow kiểu first-match cho AWS Security Group?** SG tổng hợp các rule cho phép và không dùng deny ưu tiên theo thứ tự tương tự ACL.
8. **Những thông tin gì cần có trước khi sửa rule?** Ngữ nghĩa platform, policy set/hướng/zone, thứ tự hiện hành, NAT/state, nguồn-đích-service, owner, ý định truy cập, log và bộ ca kiểm thử.
9. **Rule không có hit có chắc đã bị shadow không?** Không. Cần phân tích tập điều kiện và khả năng quan sát của bộ đếm.
10. **Khi nào có thể xóa một rule được cho là redundant?** Sau khi chứng minh bỏ rule không làm thay đổi hành vi cần giữ, bao gồm decision, side effects và cam kết kiểm toán, đồng thời đã được phê duyệt theo quy trình.

### Bài tập tình huống

Một firewall first-match có các dòng:

~~~text
10 ALLOW src=10.50.0.0/16  dst=192.0.2.50  TCP 443
20 DENY  src=10.50.8.0/24  dst=192.0.2.50  TCP 443
30 ALLOW src=10.50.8.0/24  dst=192.0.2.50  TCP 22
40 DENY  any              -> any        any
~~~

Hãy xác định:

1. Rule nào bị che toàn bộ hoặc một phần, với **lý do về nguồn, đích, protocol, port**?
2. Lưu lượng **10.50.8.10 → 192.0.2.50:443/TCP** bị chặn hay được phép? Rule nào quyết định?
3. Lưu lượng **10.50.8.10 → 192.0.2.50:22/TCP** khớp rule nào?
4. Nếu yêu cầu an ninh là “10.50.8.0/24 không được dùng 443, nhưng được dùng SSH chỉ khi có phê duyệt”, hãy đề xuất thứ tự/phạm vi mới và bộ regression test tương ứng.

**Gợi ý kiểm tra:** Rule 20 bị rule 10 che hoàn toàn trên TCP/443, do 10.50.8.0/24 nằm trong 10.50.0.0/16. Rule 30 không bị rule 10 che vì dùng **TCP/22**, khác cổng của rule 10. Luồng HTTPS từ 10.50.8.10 hiện được **ALLOW bởi rule 10**, còn SSH khớp rule 30. Một sửa đổi phù hợp cần đặt deny cụ thể cho TCP/443 trước allow rộng, rồi kiểm chứng SSH và các subnet khác; yêu cầu phê duyệt SSH phải được xác minh riêng.

## 15. Checklist áp dụng trong môi trường thực tế

- [ ] Đã xác định loại policy engine: first-match, priority, additive hay nhiều tầng?
- [ ] Đã chọn đúng chính sách được triển khai, hướng ingress/egress, zone và interface?
- [ ] Đã đối chiếu NAT, VPN, IPv4/IPv6, stateful/stateless và đường trả về?
- [ ] Đã mở rộng address/service/identity group theo phiên bản cấu hình hiện tại?
- [ ] Đã tìm cả full shadowing, partial shadowing và trường hợp hợp nhiều rule?
- [ ] Đã kiểm tra sự khác nhau giữa ALLOW/DENY và các side effect như log, inspection?
- [ ] Đã đối chiếu intent, chủ tài sản và phê duyệt quyền truy cập?
- [ ] Đã có ca kiểm thử **ALLOW hợp lệ** và **DENY bắt buộc**, bao gồm trường hợp biên?
- [ ] Đã mô phỏng thay đổi và xác định kế hoạch triển khai/rollback?
- [ ] Đã kiểm tra trạng thái sau triển khai, log, session và thay đổi bất thường?

**Kết luận:** Shadowed rule là dấu hiệu cho thấy **chính sách được viết ra có thể khác với chính sách thiết bị thực sự thực thi**. Phân tích đúng cần bắt đầu từ ngữ nghĩa xử lý rule của nền tảng, so khớp **toàn bộ điều kiện của luồng**, xét **tập hợp các rule đứng trước** rồi đối chiếu với yêu cầu truy cập. Một thay đổi an toàn phải bảo toàn nguyên tắc quyền tối thiểu và được chứng minh bằng các trường hợp được phép lẫn bị từ chối.
