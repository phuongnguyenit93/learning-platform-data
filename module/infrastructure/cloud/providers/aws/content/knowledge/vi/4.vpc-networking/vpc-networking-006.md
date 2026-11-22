# Network ACL và quy tắc stateless

> **Chương:** Mạng VPC  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — tìm hiểu hạ tầng AWS, IAM, VPC và các dịch vụ ứng dụng nhằm thiết kế hệ thống an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

Trong Amazon Virtual Private Cloud (VPC), kết nối mạng được quyết định bởi nhiều lớp: địa chỉ IP, subnet, route table, Internet Gateway/NAT Gateway, **Network Access Control List (Network ACL hoặc NACL)** và **Security Group**. NACL là một lớp kiểm soát lưu lượng **ở ranh giới subnet**. Điểm quan trọng nhất: **NACL là stateless**, nên mỗi gói đi vào hoặc đi ra được đánh giá độc lập, kể cả khi gói thuộc kết nối TCP đã được thiết lập.

Bài học này giải thích cách NACL xử lý rule, vì sao cần mở cả chiều yêu cầu và chiều phản hồi, và cách áp dụng NACL kết hợp Security Group trong kiến trúc AWS an toàn. Các dải IP và tài nguyên ở ví dụ đều là giả định.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả NACL gắn với subnet như thế nào và khác Security Group ở điểm nào.
2. Đọc các trường rule: **số thứ tự**, protocol, dải port, CIDR, Allow/Deny và chiều inbound/outbound.
3. Giải thích **first-match** và **implicit deny** trong quy tắc NACL.
4. Xác định đúng port đích của gói yêu cầu và gói phản hồi, đặc biệt là **ephemeral ports**.
5. Thiết kế tập rule tối thiểu cho subnet web, ứng dụng và database; phân tích nguyên nhân kết nối bị gián đoạn.
6. Dùng AWS Console/CLI, VPC Flow Logs và công cụ kiểm tra đường mạng để đối chiếu cấu hình với hành vi thực tế.

## 2. Network ACL là gì?

**Network ACL** là tập quy tắc cho phép hoặc từ chối lưu lượng **đi vào (inbound)** và **đi ra (outbound)** một hoặc nhiều subnet của VPC. NACL kiểm tra lưu lượng qua ranh giới subnet, dựa trên thuộc tính gói tin như giao thức, IP và port. NACL không đảm nhiệm chức năng định tuyến: muốn một packet tới đích, mạng vẫn cần route và các thành phần kết nối phù hợp.

Quan hệ giữa VPC, subnet, NACL và Security Group:

~~~mermaid
flowchart TB
    Client["Client / mạng khác"] --> Route["Định tuyến qua IGW, NAT, TGW... tùy đường đi"]
    Route --> NACL_IN["NACL inbound tại ranh giới subnet"]
    NACL_IN --> SG_IN["Security Group tại ENI/instance"]
    SG_IN --> APP["EC2 / dịch vụ trong subnet"]
    APP --> SG_OUT["Security Group outbound"]
    SG_OUT --> NACL_OUT["NACL outbound tại ranh giới subnet"]
    NACL_OUT --> Route
~~~

*Sơ đồ diễn giải hai lớp lọc theo logic; đường đi thực tế tùy loại dịch vụ và đích đến. Không có hàm ý rằng mọi loại lưu lượng AWS nội bộ đều đi qua NACL theo cùng một cách.*

### 2.1. Phạm vi liên kết

- **Mỗi subnet phải liên kết với đúng một NACL** tại một thời điểm.
- **Một NACL có thể liên kết nhiều subnet** trong cùng VPC.
- Khi tạo subnet, nếu không gắn custom NACL, subnet liên kết với **default NACL** của VPC.
- NACL kiểm soát lưu lượng **đi vào hoặc ra khỏi subnet**; nó không kiểm soát lưu lượng trao đổi giữa hai tài nguyên **trong cùng subnet** theo cách lọc qua ranh giới subnet.
- NACL hoạt động với lưu lượng IPv4 và IPv6, nhưng phải thiết lập rule riêng tương ứng với CIDR IPv4/IPv6.

Nếu ứng dụng nằm ở nhiều Availability Zone (AZ), mỗi AZ chứa những subnet riêng. NACL gắn với **subnet** chứ không gắn trực tiếp vào AZ hay EC2. Hai subnet khác AZ có thể dùng chung NACL; tuy nhiên, thay đổi một NACL dùng chung sẽ ảnh hưởng đồng thời tới tất cả subnet liên kết.

### 2.2. Stateless nghĩa là gì?

Một bộ lọc **stateful** theo dõi trạng thái của kết nối và tự cho phép luồng phản hồi phù hợp. **NACL không ghi nhớ kết nối**, vì vậy:

- Gói **client → server** được xét bằng tập inbound hoặc outbound rule tương ứng tại ranh giới subnet.
- Gói **server → client** được xét **lại từ đầu** ở chiều ngược.
- Một inbound Allow **không** tự cấp outbound Allow cho gói phản hồi.
- Nếu gói phản hồi không khớp rule Allow ở chiều đi ra, kết nối có thể thất bại dù gói yêu cầu đã vào được.

Đây là điểm khác biệt quyết định khi so sánh NACL với Security Group.

## 3. Security Group và Network ACL khác nhau thế nào?

| Tiêu chí | Network ACL | Security Group |
| --- | --- | --- |
| Phạm vi | Subnet | Network interface (ENI), thường gắn với EC2 hoặc tài nguyên mạng của dịch vụ |
| Cơ chế | **Stateless** | **Stateful** đối với lưu lượng trả về đã được theo dõi |
| Rule | Có **Allow** và **Deny** | Rule cấp quyền **Allow**, không có rule Deny |
| Thứ tự | Xét rule theo **số tăng dần**, dừng ở rule đầu tiên khớp | Không có thứ tự ưu tiên kiểu số rule |
| Nếu không có rule cho phép | Mặc định từ chối qua quy tắc `*` | Mặc định không cho phép lưu lượng không khớp |
| Luồng phản hồi | Phải có rule thích hợp ở **cả hai chiều** | Thông thường phản hồi của kết nối được theo dõi được tự cho phép |
| Chọn nguồn/đích | CIDR IPv4/IPv6, theo các loại trường rule có hỗ trợ | CIDR, prefix list và có thể tham chiếu Security Group ở ngữ cảnh được hỗ trợ |
| Cách dùng phổ biến | Lớp kiểm soát thô ở ranh giới subnet, chặn dải mạng | Lọc truy cập chi tiết gần ứng dụng và giữa các tầng |

**Ví dụ:** Security Group của máy chủ ứng dụng có inbound `TCP 443` từ địa chỉ client; với kết nối TCP được theo dõi, máy chủ có thể gửi phản hồi mà không cần SG outbound mở cổng ephemeral tương ứng. Với NACL ở subnet chứa máy chủ, cần **inbound cho port 443** và **outbound cho port đích ephemeral của client**.

Không nên sử dụng NACL như công cụ thay thế Security Group. Cả hai có thể áp dụng đồng thời, nhưng trách nhiệm khác nhau: Security Group thường kiểm soát chi tiết theo tài nguyên; NACL bổ sung rào chắn ở mức subnet, bao gồm khả năng **explicit Deny** theo địa chỉ mạng.

## 4. Cấu trúc một NACL rule

Một NACL có **hai danh sách độc lập**: inbound rules và outbound rules. Mỗi rule gồm các trường:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Rule number** | `100`, `110` | Số thứ tự ưu tiên; **số nhỏ được xét trước** |
| **Type/Protocol** | HTTPS (TCP), HTTP (TCP), TCP tùy chỉnh, UDP, ICMP | Loại giao thức được lọc |
| **Port range** | `443` hoặc `1024–65535` | Port **đích** của gói TCP/UDP tại chiều đang xét |
| **Source** (inbound) | `203.0.113.0/24` | CIDR **nguồn** của gói đi vào subnet |
| **Destination** (outbound) | `0.0.0.0/0` | CIDR **đích** của gói đi ra subnet |
| **Allow / Deny** | `ALLOW` hoặc `DENY` | Cho phép hoặc từ chối gói khớp rule |
| **IPv4 / IPv6 CIDR** | `10.20.0.0/16`, `2001:db8::/32` | Chọn một họ địa chỉ cho từng rule; cần rule riêng cho họ địa chỉ còn lại |

Với TCP/UDP, hãy chú ý cách diễn giải **port là port đích của packet**. Source port cũng có trong gói TCP/UDP, nhưng NACL rule theo port range chủ yếu dùng **destination port**; do đó phản hồi TCP thường cần mở port ephemeral của **bên khởi tạo** tại chiều ngược.

### 4.1. Số rule và nguyên tắc first-match

AWS đánh giá các NACL rule theo **rule number tăng dần**, riêng cho từng chiều. **Rule đầu tiên khớp** với protocol, CIDR và port quyết định Allow/Deny; các rule có số lớn hơn không còn được xét cho packet đó.

Ví dụ inbound của subnet web:

| Rule | Protocol | Source | Port đích | Hành động |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `203.0.113.0/24` | 443 | **DENY** |
| 110 | TCP | `0.0.0.0/0` | 443 | **ALLOW** |
| * | All traffic | `0.0.0.0/0` | All | **DENY** |

Kết quả:

- Client `203.0.113.25` truy cập HTTPS: **Deny**, vì rule 100 khớp trước rule 110.
- Client `198.51.100.15` truy cập HTTPS: rule 100 không khớp, rule 110 **Allow**.
- Client `198.51.100.15` truy cập port 22: không khớp 100/110, đến rule `*` và bị **Deny**.

Các dải `203.0.113.0/24` và `198.51.100.0/24` dùng để **minh họa tài liệu**, không phải IP khách hàng thật. AWS có giới hạn số lượng entry và rule number; mặc định người quản trị thường đặt số cách nhau (100, 110, 120...) để còn chỗ thêm rule.

> **Lỗi thường gặp:** Đặt `ALLOW 443 0.0.0.0/0` ở rule 100 rồi đặt `DENY 443 203.0.113.0/24` ở rule 110 **không chặn được** dải IP đó vì yêu cầu đã khớp rule 100 trước.

### 4.2. Rule `*` và tình huống không có Allow

Ở cuối mỗi bảng inbound/outbound, console hiển thị rule **`*`**, có hành động **DENY**, áp dụng khi không có rule nào phía trên khớp. Đây là cơ chế **implicit deny** mặc định của NACL; không thể xóa rule bắt tất cả này.

Đừng nhầm default rule `*` với rule dùng wildcard CIDR `0.0.0.0/0`. CIDR `0.0.0.0/0` biểu thị mọi địa chỉ IPv4, nhưng kết quả vẫn phụ thuộc protocol, port, thứ tự và hành động của rule.

### 4.3. Default NACL và custom NACL

| Thuộc tính | Default NACL khi VPC mới được tạo | Custom NACL mới tạo |
| --- | --- | --- |
| Inbound | Mặc định có rule Allow mọi lưu lượng IPv4; có thể có rule IPv6 nếu VPC có IPv6 | Ban đầu **không có Allow** |
| Outbound | Mặc định có rule Allow mọi lưu lượng IPv4; có thể có rule IPv6 nếu VPC có IPv6 | Ban đầu **không có Allow** |
| Cuối danh sách | Rule `*` Deny khi không có rule trước khớp | Rule `*` Deny khi không có rule trước khớp |
| Hệ quả | NACL mặc định rộng; kiểm soát tinh hơn bằng Security Group và các lớp khác | Nếu gắn vào subnet mà chưa thêm rule, lưu lượng cần qua subnet boundary có thể bị chặn |

Default NACL là **một tài nguyên có thể chỉnh sửa**: nếu người quản trị đã thay rule, cấu hình thực tế có thể khác mô tả ban đầu. Luôn xem cấu hình đang dùng thay vì suy đoán theo tên “default”.

## 5. Luồng TCP: vì sao ephemeral ports quan trọng?

Khi một client mở kết nối HTTPS, nó thường chọn **source port tạm thời** (ephemeral port), trong khi server lắng nghe ở **destination port 443**. Server gửi phản hồi tới port tạm thời đó.

Ví dụ:

~~~text
Client 198.51.100.15:51842            Web server 10.20.1.20:443
           |                                       |
           | ---- TCP SYN: 51842 -> 443 ---------> |  (yêu cầu)
           | <--- TCP SYN-ACK: 443 -> 51842 ------ |  (phản hồi)
           | ---- TCP ACK: 51842 -> 443 ---------> |  (xác nhận)
           |                                       |
~~~

Nếu server nằm trong một subnet public, gói đầu tiên đi **vào subnet** có destination port 443; gói SYN-ACK đi **ra subnet** có destination port 51842.

Do NACL là **stateless**, một cấu hình tối thiểu minh họa cho kết nối này cần:

| Chiều NACL của subnet server | CIDR phía ngoài | TCP destination port | Mục đích |
| --- | --- | --- | --- |
| Inbound | `198.51.100.15/32` | `443` | Cho client truy cập HTTPS |
| Outbound | `198.51.100.15/32` | `51842` | Cho phản hồi tới port ephemeral của client |

Trong thực tế, server không thể đoán trước port 51842 của mọi client, nên rule outbound phải bao phủ **dải ephemeral ports** có thể xuất hiện, ví dụ `1024–65535` nếu muốn hỗ trợ nhiều loại client. Đây là phạm vi minh họa bao quát; hệ điều hành, NAT, proxy, load balancer và ứng dụng có thể dùng **dải ephemeral khác nhau**. Hãy xác minh hành vi bên thực sự khởi tạo kết nối để chọn phạm vi phù hợp.

### 5.1. Server cũng có thể là bên khởi tạo

Giả sử một ứng dụng trong private subnet gọi API HTTPS bên ngoài:

~~~text
App 10.20.11.20:49152  -- TCP 49152 -> 443 -->  API 198.51.100.20:443
App 10.20.11.20:49152  <-- TCP 443 -> 49152 --  API 198.51.100.20:443
~~~

Với NACL của private subnet:

- **Outbound:** cần Allow destination port **443** đến đích ngoài được phép.
- **Inbound:** cần Allow destination port thuộc **dải ephemeral** dùng bởi app.
- Nếu đi qua **NAT Gateway**, phải kiểm tra cả routing, NACL phía subnet đặt NAT Gateway và những địa chỉ/port sau khi dịch NAT. Chỉ sửa NACL của app không bảo đảm mọi đường đi thành công.

**Mẹo suy luận:** Xác định *ai mở kết nối?* → ghi cặp `sourceIP:sourcePort → destinationIP:destinationPort` → đảo chiều để vẽ gói phản hồi → áp quy tắc NACL inbound/outbound tại **từng subnet mà gói đi qua**.

### 5.2. Trường hợp UDP và ICMP

**UDP** cũng cần xét hai chiều dù không có bắt tay TCP. Một truy vấn DNS có thể gửi tới port 53 và nhận phản hồi về port tạm thời của client. Đừng chỉ mở UDP 53 ở cả hai chiều rồi mặc định phản hồi luôn đi đến port 53.

**ICMP/ICMPv6** dùng type/code thay cho TCP/UDP port; các thông điệp điều khiển mạng, chẩn đoán và khám phá MTU có thể cần rule riêng theo nhu cầu. Đặc biệt với IPv6, chặn ICMPv6 thiếu cân nhắc có thể ảnh hưởng đến hoạt động mạng. Không suy ra một rule TCP/UDP sẽ cho phép ICMP.

## 6. Ví dụ 1: công bố HTTPS từ một subnet web

**Bối cảnh:** một web server tại `10.20.1.20` nằm trong subnet `10.20.1.0/24`, có đường truy cập Internet phù hợp và Security Group chỉ cho phép HTTPS từ những client được chấp nhận. Mục tiêu NACL: cho phép HTTPS và phản hồi, không cấp thêm quyền quản trị SSH.

NACL gắn với subnet server có thể bắt đầu từ tập rule IPv4:

**Inbound:**

| Rule | Protocol | Source | Destination port | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `0.0.0.0/0` | `443` | ALLOW |
| * | All | `0.0.0.0/0` | All | DENY |

**Outbound:**

| Rule | Protocol | Destination | Destination port | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `0.0.0.0/0` | `1024–65535` | ALLOW |
| * | All | `0.0.0.0/0` | All | DENY |

Giải thích:

- Client gửi gói tới port **443** → inbound rule 100 khớp.
- Server trả gói về port **ephemeral** ở client → outbound rule 100 khớp.
- Yêu cầu SSH port 22 từ Internet → không có inbound Allow, bị Deny.
- Nếu server còn chủ động gọi AWS API, dịch vụ cập nhật, DNS hoặc gửi log, tập rule này **chưa đủ**: cần thêm rule phù hợp cho kết nối do server khởi tạo và gói phản hồi. Security Group, đường Internet, NAT, route table và listener cũng phải đúng.

**Giới hạn của ví dụ:** outbound ephemeral `0.0.0.0/0` là rule rộng để minh họa cơ chế kết nối với nhiều client; không phải khuyến nghị áp dụng nguyên trạng vào mọi hệ thống. Nếu có thể, thu hẹp CIDR theo mạng client hoặc chọn kiến trúc ALB/WAF và các lớp bảo vệ phù hợp.

## 7. Ví dụ 2: ứng dụng hai tầng qua ALB

**Bài toán:** khách truy cập ứng dụng HTTPS thông qua Application Load Balancer (ALB), sau đó ALB chuyển HTTP hoặc TCP ứng dụng tới target EC2 cổng 8080. Giả sử:

- Subnet ALB: `10.20.1.0/24`, public.
- Subnet ứng dụng: `10.20.11.0/24`, private.
- ALB lắng nghe `TCP 443` từ Internet, target application lắng nghe `TCP 8080`.
- Các CIDR chỉ minh họa **một cặp subnet**; nếu triển khai nhiều AZ, phải mở rộng thiết kế và kiểm tra mọi cặp subnet mà ALB và target có thể liên lạc.

~~~mermaid
sequenceDiagram
    participant C as Client Internet
    participant L as ALB (public subnet)
    participant A as App (private subnet)
    C->>L: TCP client_ephemeral → 443
    L-->>C: TCP 443 → client_ephemeral
    L->>A: TCP alb_ephemeral → 8080
    A-->>L: TCP 8080 → alb_ephemeral
~~~

Hai kết nối `Client ↔ ALB` và `ALB ↔ App` là **hai luồng TCP riêng**. NACL cần chấp nhận hướng đi và hướng về tại ranh giới **cả hai subnet**.

### 7.1. NACL của subnet ALB

| Chiều | Protocol | Source / destination | Port đích | Luồng được phục vụ |
| --- | --- | --- | --- | --- |
| Inbound | TCP | Source `0.0.0.0/0` | `443` | Client → ALB |
| Outbound | TCP | Destination `0.0.0.0/0` | `1024–65535` | ALB → port ephemeral của client |
| Outbound | TCP | Destination `10.20.11.0/24` | `8080` | ALB → App |
| Inbound | TCP | Source `10.20.11.0/24` | `1024–65535` | App → port ephemeral phía ALB |

### 7.2. NACL của subnet App

| Chiều | Protocol | Source / destination | Port đích | Luồng được phục vụ |
| --- | --- | --- | --- | --- |
| Inbound | TCP | Source `10.20.1.0/24` | `8080` | ALB → App |
| Outbound | TCP | Destination `10.20.1.0/24` | `1024–65535` | App → port ephemeral phía ALB |

Về phía Security Group, có thể cho SG của ALB nhận `TCP 443` từ các client phù hợp, còn SG của App chỉ cho phép `TCP 8080` với **source là SG của ALB** (khi kiểu tham chiếu được hỗ trợ). Phản hồi của các kết nối được theo dõi sẽ được SG xử lý statefully. NACL thì vẫn cần các port phản hồi như bảng trên.

**Không bỏ sót dịch vụ phụ trợ:** nếu App còn cần gọi database trên port 5432, Redis trên port 6379, DNS, secrets hoặc HTTPS endpoint, phải xét thêm từng luồng kết nối. Nếu ALB gửi health check đến target, cần bảo đảm port và đường mạng của health check được cho phép; nếu health check dùng port khác 8080, bảng trên phải được bổ sung.

### 7.3. Vì sao ví dụ này chưa phải cấu hình production hoàn chỉnh?

Hai bảng chỉ biểu diễn một chuỗi kết nối web và app; chưa bao gồm IPv6, các vùng AZ khác, NAT, các dịch vụ nền, database, cập nhật phần mềm hay cơ chế giám sát. Trong thiết kế nhiều AZ, ALB thường được bật trên subnet ở nhiều AZ và target có thể nằm ở những subnet khác nhau. Phải thống kê **mọi subnet có thể làm nguồn hoặc đích**, không cố định duy nhất một CIDR nếu ứng dụng thực tế trải qua nhiều AZ.

## 8. Khi ứng dụng kết nối database: áp dụng ngược cả hai chiều

Giả sử App tại `10.20.11.20` chủ động kết nối PostgreSQL tại `10.20.21.30:5432`:

~~~text
App 10.20.11.20:50030 -> DB 10.20.21.30:5432    (request)
DB  10.20.21.30:5432 -> App 10.20.11.20:50030    (response)
~~~

Nếu App và DB ở **hai subnet khác nhau**, mỗi subnet có NACL riêng, xét:

| Ranh giới | Chiều | CIDR phía đối diện | Port đích | Vì sao? |
| --- | --- | --- | --- | --- |
| App subnet | Outbound | `10.20.21.0/24` | TCP 5432 | App tạo kết nối đến DB |
| DB subnet | Inbound | `10.20.11.0/24` | TCP 5432 | DB nhận yêu cầu |
| DB subnet | Outbound | `10.20.11.0/24` | TCP ephemeral của App | DB gửi phản hồi |
| App subnet | Inbound | `10.20.21.0/24` | TCP ephemeral của App | App nhận phản hồi |

Không dùng bảng trên để tuyên bố rằng NACL thay thế toàn bộ bảo vệ database. Với RDS và các dịch vụ được quản lý, cần theo dõi subnet group, cách dịch vụ dùng ENI, khả năng failover giữa AZ và Security Group của database. Những địa chỉ thực tế có thể thay đổi sau failover. Khi policy có CIDR theo subnet, phải bao phủ các subnet dự phòng liên quan.

## 9. Các trạng thái lỗi thường gặp khi cấu hình NACL

| Triệu chứng | Nguyên nhân hay gặp | Cách tìm nguyên nhân |
| --- | --- | --- |
| Trình duyệt không kết nối HTTPS dù EC2 đang chạy | Inbound NACL không Allow TCP 443, hoặc SG/route không đúng | Kiểm tra inbound rule đầu tiên khớp, SG và đường Internet |
| TCP gửi SYN nhưng không hoàn thành handshake | **Thiếu outbound ephemeral** cho gói trả lời | Vẽ source/destination port của SYN và SYN-ACK |
| App gọi API HTTPS bên ngoài bị timeout | Thiếu outbound 443 hoặc inbound ephemeral, NAT/route bị lỗi | Kiểm tra từng subnet trên đường request/response |
| ALB báo target unhealthy | Thiếu port health check hoặc thiếu ephemeral ở một phía | Đối chiếu listener, target group health check, SG và NACL cả hai subnet |
| Rule Deny theo IP “không có tác dụng” | Allow rộng nằm ở **rule number nhỏ hơn** | Sắp lại rule để Deny khớp trước |
| Mới gắn custom NACL, toàn bộ ứng dụng mất kết nối | Custom NACL ban đầu chỉ có implicit Deny | Tạo đủ inbound/outbound rule trước khi liên kết subnet |
| IPv4 dùng được, IPv6 không dùng được | Chưa tạo IPv6 rules hoặc chưa cấu hình đường IPv6 | Xem IPv6 CIDR, route, SG, NACL và tính năng IPv6 |
| Giao tiếp giữa hai instance cùng subnet không bị rule NACL chặn | NACL kiểm soát **ranh giới subnet** | Dùng Security Group và kiểm soát tại host/ứng dụng khi cần |
| Kết nối lỗi sau failover database hoặc scale-out | IP/subnet hoặc port của thành phần mới khác giả định | Rà soát các subnet/AZ dự phòng và thay đổi topology |

**Phân biệt “REJECT” và nguyên nhân thực tế:** Một bản ghi VPC Flow Logs hiển thị `REJECT` cho biết lưu lượng bị từ chối ở lớp mạng được quan sát, nhưng **không trực tiếp chỉ ra đúng rule NACL nào gây ra**; Security Group và các tình huống khác cũng có thể khiến request bị từ chối. Cần kết hợp log với mô hình đường mạng và cấu hình tại thời điểm xảy ra lỗi.

## 10. Quy trình thiết kế NACL an toàn

Trong các hệ thống nhiều tầng, hãy thiết kế từ **luồng cần cho nghiệp vụ**:

1. **Vẽ sơ đồ subnet và AZ.** Liệt kê subnet public, app, database, subnet đặt NAT Gateway và những subnet còn lại liên quan.
2. **Lập bảng kết nối:** nguồn, đích, giao thức, port dịch vụ, ai chủ động mở kết nối, đường trả về.
3. **Với mỗi ranh giới subnet:** viết rule inbound cho yêu cầu, outbound cho phản hồi; sau đó bổ sung chiều ngược nếu máy trong subnet cũng chủ động khởi tạo kết nối.
4. **Thu hẹp CIDR** khi có thể. Dùng source/destination theo subnet hoặc mạng được quản trị thay vì `0.0.0.0/0` nếu nhu cầu cho phép.
5. **Xếp rule Deny rõ ràng trước Allow rộng** nếu cần chặn một nguồn cụ thể. Dành khoảng cách giữa rule number để có thể thêm rule mà không phải đánh số lại quá nhiều.
6. **Kiểm soát Security Group riêng biệt** ở tài nguyên. NACL không hỗ trợ tham chiếu SG, còn SG có thể lọc theo SG nguồn ở những trường hợp hỗ trợ.
7. **Kiểm tra cả IPv4 và IPv6**, các loại protocol khác TCP, health check và kết nối hệ thống phụ trợ.
8. **Chuẩn bị đường khôi phục** trước khi đổi NACL dùng chung. Sửa NACL có thể tác động ngay nhiều subnet; cân nhắc thử ở subnet cô lập hoặc môi trường staging trước.
9. **Giám sát và kiểm chứng:** dùng Flow Logs, Reachability Analyzer phù hợp và kiểm thử từ nguồn thật, theo dõi sau thay đổi.

### 10.1. Chi phí và tính sẵn sàng

NACL không phải một dịch vụ lưu trữ hay tính toán cần tự tạo máy chủ; tuy nhiên, thiết kế mạng liên quan **NAT Gateway, VPC endpoint, truyền dữ liệu giữa AZ**, load balancer và giải pháp giám sát có thể phát sinh chi phí. Một NACL quá chặt làm hỏng health check, dịch vụ phụ trợ hoặc failover sẽ ảnh hưởng **availability**. Vì vậy, cần xem tác động về hiệu năng, khôi phục và chi phí cùng với mục tiêu bảo mật.

### 10.2. Những điều NACL không làm được

- NACL **không quản lý danh tính IAM**, vai trò ứng dụng, phân quyền S3 hay quyền truy cập database ở tầng SQL.
- NACL **không quyết định routing** và không tự cung cấp Internet, NAT hoặc PrivateLink.
- NACL **không phải tường lửa kiểm tra nội dung HTTP**, không thay cho AWS WAF hay cơ chế chống DDoS.
- NACL **không chặn được tất cả luồng đến địa chỉ AWS đặc biệt**; có những traffic path như AmazonProvidedDNS/Route 53 Resolver, metadata hoặc cơ chế hạ tầng chịu quy tắc riêng. Không dựa vào NACL đơn độc để áp chính sách đầy đủ cho các thành phần đó.
- NACL không thực hiện lọc theo domain, IAM principal hoặc Security Group ID.

## 11. Thực hành chỉ đọc với AWS CLI

Các lệnh sau dùng để **quan sát**, không sửa cấu hình. Cần AWS CLI đã cấu hình và danh tính có quyền xem thông tin EC2/VPC. Thay Region và ID minh họa bằng tài nguyên thật.

### 11.1. Liệt kê NACL trong Region

~~~bash
aws ec2 describe-network-acls \
  --region ap-southeast-1 \
  --query "NetworkAcls[].{Id:NetworkAclId,Default:IsDefault,Vpc:VpcId}" \
  --output table
~~~

### 11.2. Xem NACL gắn với một subnet cụ thể

~~~bash
aws ec2 describe-network-acls \
  --region ap-southeast-1 \
  --filters Name=association.subnet-id,Values=subnet-0123456789abcdef0 \
  --query "NetworkAcls[].{Id:NetworkAclId,Associations:Associations[].SubnetId}" \
  --output json
~~~

`subnet-0123456789abcdef0` là ID minh họa; nếu không có subnet này trong tài khoản, kết quả có thể là mảng rỗng.

### 11.3. Xem các rule và thứ tự

~~~bash
aws ec2 describe-network-acls \
  --region ap-southeast-1 \
  --network-acl-ids acl-0123456789abcdef0 \
  --query "NetworkAcls[].Entries[].{No:RuleNumber,Out:Egress,Protocol:Protocol,Action:RuleAction,CIDR:CidrBlock,IPv6:Ipv6CidrBlock,Ports:PortRange}" \
  --output json
~~~

Đọc kết quả như sau:

- `Egress=false` nghĩa là **inbound**; `Egress=true` là **outbound**.
- `RuleNumber` quyết định thứ tự kiểm tra trong từng chiều.
- `RuleAction` thường là `allow` hoặc `deny`.
- `CidrBlock` hoặc `Ipv6CidrBlock` cho biết loại địa chỉ của rule.
- `PortRange` xuất hiện với những protocol áp dụng port range; không suy đoán mọi rule đều có phần này.

Sau khi có dữ liệu, tự tạo bảng phân tích cho một request `client:52000 → app:443`. Xác định inbound rule đầu tiên khớp, sau đó đổi chiều để tìm outbound rule của phản hồi `app:443 → client:52000`.

### 11.4. Kiểm tra đường mạng

**VPC Reachability Analyzer** hỗ trợ phân tích đường đi và cấu hình giữa các endpoint AWS tương thích. Nó có thể chỉ ra thành phần mạng nào có khả năng ngăn traffic trong mô hình phân tích. Với sự cố thực tế, cũng cần:

- Kiểm tra Security Group gắn trên ENI đích.
- Xác minh route table, Internet Gateway, NAT, transit gateway hoặc VPC endpoint trên đường đi.
- Kiểm tra listener/target và ứng dụng có mở port hay không.
- Bật và đọc **VPC Flow Logs** theo phạm vi phù hợp, đối chiếu thời gian và IP/port của request.
- Kiểm thử từ nguồn và mạng thực tế; không xem một bản mô phỏng là bằng chứng hệ thống luôn truy cập được.

## 12. Bài tập củng cố

### Bài tập 1 — Gói nào được Allow?

Một subnet có các inbound rule IPv4:

| Rule | Protocol | CIDR nguồn | Port đích | Action |
| ---: | --- | --- | --- | --- |
| 100 | TCP | `10.20.0.0/16` | 22 | DENY |
| 110 | TCP | `10.20.11.0/24` | 22 | ALLOW |
| 120 | TCP | `0.0.0.0/0` | 443 | ALLOW |
| * | All | `0.0.0.0/0` | All | DENY |

Xác định kết quả của ba request:

1. `10.20.11.50 → server:22`.
2. `198.51.100.20 → server:443`.
3. `198.51.100.20 → server:80`.

**Gợi ý đáp án:** (1) Deny vì rule 100 khớp **trước** 110; (2) Allow tại 120; (3) Deny theo `*`. Để cho phép SSH từ `10.20.11.0/24` nhưng chặn phần còn lại của `10.20.0.0/16`, cần đặt rule Allow hẹp trước rule Deny rộng (và vẫn cân nhắc rủi ro cấp SSH).

### Bài tập 2 — Thiếu chiều nào?

Một server public cho phép inbound TCP 443 từ Internet nhưng NACL outbound chỉ Allow TCP 443 ra Internet. Client gửi request từ port `53001`.

**Câu hỏi:** tại sao TCP handshake có thể thất bại? Phải xét thêm rule nào?

**Gợi ý đáp án:** server phản hồi tới **destination port 53001**, không phải port 443. Outbound chỉ Allow destination port 443 sẽ không khớp. Cần rule outbound cho dải ephemeral của client, thu hẹp CIDR nếu phù hợp.

### Bài tập 3 — Thiết kế hai AZ

Một hệ thống sử dụng ALB ở **hai public subnet** và EC2 ở **hai private app subnet**, tất cả trong một VPC. Backend dùng port 8080; app kết nối RDS trên port 5432.

Hãy vẽ đường đi của request/response khi ALB chọn target khác AZ. Xác định từng NACL và bảng inbound/outbound tương ứng, không quên phản hồi port ephemeral. Sau đó nêu điều gì thay đổi nếu RDS failover sang subnet ở AZ còn lại. Giải thích tại sao Security Group theo source SG thuận tiện hơn để quản trị quyền giữa các tầng, trong khi NACL vẫn lọc theo CIDR.

## 13. Ghi nhớ

**Network ACL = bộ lọc stateless ở ranh giới subnet.** Trong mỗi chiều, AWS xét rule từ số nhỏ đến số lớn và áp dụng **rule đầu tiên khớp**; nếu không có rule nào cho phép thì packet bị Deny. NACL hỗ trợ cả Allow và Deny, còn Security Group cho phép rule Allow với cơ chế theo dõi kết nối.

Để phân tích đúng một lỗi mạng, đừng chỉ nhìn “port dịch vụ” như 443 hay 5432. Hãy vẽ **hai chiều của từng kết nối**, xác định port đích của packet tại mỗi subnet và nhớ rằng **port phản hồi thường là ephemeral port của bên khởi tạo**. Thiết kế an toàn cần NACL, Security Group, route, giám sát và kế hoạch khôi phục phối hợp.

### Tài liệu AWS chính thức

- [Control subnet traffic with network access control lists](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html) — khái niệm, cơ chế subnet-level và stateless.
- [Network ACL rules](https://docs.aws.amazon.com/vpc/latest/userguide/nacl-rules.html) — thứ tự rule, cấu trúc và implicit deny.
- [Custom network ACL for your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/custom-network-acl.html) — tạo, sửa và liên kết NACL.
- [Compare security groups and network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Security.html) — các lớp bảo vệ của VPC.
- [Ephemeral ports](https://docs.aws.amazon.com/vpc/latest/userguide/custom-network-acl.html#nacl-ephemeral-ports) — lưu lượng phản hồi và dải port tạm thời.
- [VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html) — thu thập thông tin IP traffic.
- [VPC Reachability Analyzer](https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html) — phân tích kết nối và đường mạng.
