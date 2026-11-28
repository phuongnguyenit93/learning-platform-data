# East-west isolation: cô lập lưu lượng nội bộ để hạn chế di chuyển ngang

**East-west isolation** là việc kiểm soát những kết nối giữa các máy, workload, ứng dụng hoặc vùng mạng **bên trong** hạ tầng, kể cả những đối tượng được đặt trong cùng một mạng hoặc cùng một môi trường đám mây. Mục tiêu không phải làm mọi thành phần ngừng giao tiếp, mà là chỉ cho phép **các luồng cần thiết cho nghiệp vụ** và ngăn một thiết bị hoặc dịch vụ đã bị xâm nhập dễ dàng tiếp cận các tài sản khác.

Trong chương **Segmentation** của học phần **SECURITY_NETWORK_SECURITY**, east-west isolation là một lớp phòng vệ trọng yếu, bổ sung cho firewall biên, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và kiến trúc cloud. Bài học tập trung vào nguyên tắc phân đoạn, mô hình luồng truy cập, vị trí thực thi policy, triển khai trên LAN/cloud/Kubernetes, giám sát và kiểm chứng.

Sau bài này, người học có thể phân biệt lưu lượng east-west với north-south; giải thích vì sao firewall biên không đủ để ngăn lateral movement; thiết kế policy cho phép theo nguồn–đích–giao thức–cổng hoặc danh tính workload; và kiểm thử cả kết nối hợp lệ lẫn kết nối bị từ chối.

## 1. East-west traffic là gì?

Trong tài liệu mạng, hai hướng lưu lượng thường được mô tả như sau:

| Thuật ngữ | Ý nghĩa chính | Ví dụ |
|---|---|---|
| **North-south traffic** | Lưu lượng đi giữa hệ thống nội bộ và mạng/người dùng bên ngoài ranh giới đang xét | Internet → website public; nhân viên từ xa → VPN gateway |
| **East-west traffic** | Lưu lượng giữa các hệ thống hoặc vùng cùng thuộc phạm vi nội bộ đang xét | App → database; pod → pod; VM → VM; máy nhân viên → file server |
| **East-west isolation** | Hạn chế các kết nối nội bộ dựa trên chính sách cụ thể | Chỉ App được gọi TCP/5432 tới DB; mạng khách không được truy cập máy quản trị |

Đây là cách **mô tả theo ranh giới kiến trúc**, không phải thuộc tính tuyệt đối của một gói tin. Một kết nối đi từ cloud VPC này sang cloud VPC khác qua private peering có thể được coi là east-west ở phạm vi doanh nghiệp, nhưng lại là lưu lượng vượt ranh giới giữa hai VPC. Tương tự, lưu lượng từ VPN tới database là kết nối nội bộ sau khi đã vào VPN nhưng vẫn cần kiểm soát ở ranh giới danh tính và phân đoạn.

~~~mermaid
flowchart LR
    U[Internet / remote user] -->|North-south| E[Firewall / VPN biên]
    E --> FE[Frontend]
    FE -->|East-west| APP[Application]
    APP -->|East-west| DB[(Database)]
    APP -->|East-west| CACHE[(Cache)]
    STAFF[Máy nhân viên] -->|East-west| FILE[File server]
~~~

**Điểm quan trọng:** có firewall ở đường Internet vào frontend không chứng minh rằng frontend, application, database và các máy nội bộ đã được cô lập với nhau.

## 2. Vì sao cần cô lập east-west?

### 2.1. Bài toán lateral movement

**Lateral movement (di chuyển ngang)** là quá trình một đối thủ tận dụng quyền, cấu hình hoặc kết nối có sẵn từ một điểm đã kiểm soát để tiếp cận thêm máy, dịch vụ, tài khoản hoặc tài sản. Một kịch bản đơn giản:

1. Một máy trạm của nhân viên bị chiếm quyền ở mức tài khoản thông thường.
2. Máy đó vẫn được kết nối LAN hoặc VPN và có thể gửi yêu cầu đến các dịch vụ nội bộ.
3. Nếu mạng cho phép **mọi máy nói chuyện với mọi máy**, đối thủ có nhiều đích để khảo sát và thử lạm dụng thông tin đăng nhập, dịch vụ chia sẻ, công cụ quản trị hoặc ứng dụng nội bộ.
4. Nếu mạng áp **deny-by-default** cho những luồng không cần thiết, số lượng đích trực tiếp được tiếp cận giảm. Đối thủ phải vượt thêm một ranh giới hoặc tìm đường hợp lệ khác.

~~~text
Không có phân đoạn nội bộ phù hợp:

Host đã bị chiếm ----> Web server
                  \--> Database
                   \-> Backup server
                    -> Hệ thống quản trị

Có cô lập theo vai trò:

Host đã bị chiếm ----> Intranet HTTPS (được phép)
                    X-> Database TCP/5432
                    X-> Backup SMB
                    X-> SSH vào Management
~~~

Dấu **X** trong sơ đồ biểu thị luồng bị từ chối bởi kiểm soát phù hợp. Nó **không** có nghĩa endpoint đã an toàn tuyệt đối: đối thủ có thể tiếp tục lạm dụng một ứng dụng được phép truy cập nếu có quyền hay lỗ hổng tương ứng.

### 2.2. Giảm blast radius

**Blast radius** là phạm vi tác động khi một thành phần bị hỏng hoặc bị xâm nhập. Phân đoạn tốt giúp giảm số hệ thống mà một workload bị chiếm có thể trực tiếp tiếp cận, nhờ đó thu hẹp khả năng lan truyền sự cố hoặc mã độc và hỗ trợ khoanh vùng điều tra.

Ví dụ: một container xử lý ảnh chỉ cần gọi API metadata nội bộ có thể bị hạn chế mọi kết nối đến cơ sở dữ liệu thanh toán. Nếu container bị chiếm, kẻ tấn công sẽ không có đường mạng trực tiếp đến DB qua policy đã được kiểm chứng. Tuy nhiên, nếu API metadata được phép làm trung gian truy cập DB bằng quyền quá rộng, rủi ro vẫn tồn tại ở tầng ứng dụng.

### 2.3. Những mục tiêu cần phân biệt

East-west isolation có thể phục vụ nhiều mục tiêu:

- **Confidentiality:** giảm khả năng một đối thủ từ vùng ít tin cậy kết nối đến nơi lưu dữ liệu nhạy cảm.
- **Integrity:** giới hạn những nguồn có thể gửi lệnh hoặc yêu cầu thay đổi dữ liệu đến dịch vụ nội bộ.
- **Availability:** hạn chế một số dạng lan truyền, truy cập ngoài mong đợi và quá tải giữa vùng, dù vẫn cần kiểm soát DoS, dự phòng và capacity planning.
- **Compliance và audit:** chứng minh rằng luồng giao tiếp giữa các vùng được định nghĩa, giám sát và phê duyệt.
- **Khả năng vận hành:** xác định rõ dependency thật giữa ứng dụng, từ đó có cơ sở quản lý thay đổi và xử lý sự cố.

Mỗi mục tiêu cần có tiêu chí kiểm chứng. Một sơ đồ VLAN đẹp mắt không phải bằng chứng rằng mọi luồng ngoài danh sách đã bị chặn.

## 3. Các ranh giới tin cậy trong mạng nội bộ

**Trust boundary (ranh giới tin cậy)** là nơi thay đổi giả định về quyền truy cập, danh tính hoặc mức độ nhạy cảm của tài sản. Một mạng nội bộ có thể có các vùng:

| Vùng | Thành phần tiêu biểu | Nguyên tắc truy cập |
|---|---|---|
| Guest / BYOD | Khách, thiết bị cá nhân chưa quản lý | Chỉ các dịch vụ được cấp, thường không đến LAN nhạy cảm |
| Staff | Máy trạm nhân viên | Truy cập frontend, dịch vụ theo vai trò; tránh kết nối trực tiếp DB |
| Web / frontend | Reverse proxy và máy phục vụ web | Giao tiếp đến application backend qua cổng được phê duyệt |
| Application | Service xử lý nghiệp vụ | Chỉ được gọi các backend, queue, cache, DB cần thiết |
| Data | Database, kho secrets, storage nhạy cảm | Nhận kết nối từ workload định danh và được cấp quyền |
| Management | Jump host, switch/controller, monitoring | Chỉ role/quy trình quản trị được phép |
| Backup / recovery | Backup server, repository | Quyền truy cập hạn chế, kiểm soát xóa/sửa và tài khoản độc lập |
| Control plane cloud | API quản trị IAM/network/cluster | Phân quyền mạnh; theo dõi thay đổi chính sách |

Không nên coi một vùng là “đáng tin” chỉ vì có tên **internal** hoặc **production**. Một workload ở production vẫn có thể bị chiếm và dùng quyền được cấp để gửi yêu cầu không mong muốn.

### 3.1. Vị trí trong mạng và danh tính là hai yếu tố khác nhau

Rule theo địa chỉ IP/CIDR trả lời **gói đến từ địa chỉ nào tại điểm thực thi**. Nó không luôn xác định được người dùng hoặc dịch vụ thực sự:

- Một máy có thể đổi IP qua DHCP.
- Nhiều máy có thể chia sẻ một IP nguồn khi đi qua NAT hoặc proxy.
- Workload trong môi trường cloud có thể được tạo/hủy và đổi IP.
- Kẻ kiểm soát một host có thể sử dụng những kết nối mà chính host đó được phép thực hiện.

Do đó, cùng với mạng phân đoạn, hệ thống nhạy cảm thường dùng **802.1X/NAC, workload identity, mTLS, IAM, xác thực ứng dụng và quyền dữ liệu tối thiểu**. Cô lập mạng giúp thu hẹp reachability; danh tính và ủy quyền tiếp tục quyết định ai được làm gì sau khi kết nối đến dịch vụ.

## 4. Các mức độ phân đoạn và cách thực thi

Có nhiều cơ chế để cô lập east-west, mỗi cơ chế có phạm vi áp dụng khác nhau.

| Cơ chế | Điểm thực thi điển hình | Phạm vi kiểm soát | Giới hạn |
|---|---|---|---|
| **VLAN / phân đoạn L2** | Switch, AP, bridge | Chia broadcast domain và nhóm thiết bị | VLAN một mình không phải rule phân quyền giữa các VLAN; không chặn host cùng VLAN nói chuyện |
| **Subnet / routing L3** | Router, switch L3 | Tách miền IP và xác định điểm định tuyến | Nếu định tuyến liên subnet không có ACL/firewall, vẫn có thể giao tiếp |
| **Firewall liên vùng / ACL** | Firewall, router, switch, gateway | Match source/destination/protocol/port, zone, state | Chỉ áp với traffic thực sự đi qua điểm thực thi |
| **Host-based firewall** | OS của server/endpoint | Chặn/cho luồng tại chính host, kể cả host cùng VLAN | Policy phân tán khó quản trị nếu không tự động hóa |
| **Distributed firewall / microsegmentation** | Hypervisor, agent hoặc datapath workload | Cô lập chi tiết giữa VM/container/workload, đôi khi cùng subnet | Phụ thuộc chính sách nhãn/identity và năng lực nền tảng |
| **Cloud security group / network firewall** | NIC/VM, VPC/VNet, subnet gateway | Giới hạn ingress/egress theo chính sách cloud | State, thứ tự và tính năng tùy nhà cung cấp |
| **Kubernetes NetworkPolicy** | CNI/datapath hỗ trợ | Kiểm soát pod ingress/egress theo selector, CIDR và port | Không mọi cluster/CNI hỗ trợ giống nhau; cần xét DNS, node và traffic đặc thù |
| **Service mesh / mTLS authorization** | Proxy/sidecar/ambient datapath | Xác thực workload, kiểm soát kết nối theo danh tính/dịch vụ | Chỉ bảo vệ traffic đi qua enforcement phù hợp; không thay thế mọi kiểm soát L3/L4 |

**Microsegmentation** thường chỉ việc đưa ranh giới kiểm soát đến gần từng workload, ứng dụng hoặc nhóm ứng dụng nhỏ, thay vì cho phép toàn bộ các máy trong một subnet truy cập lẫn nhau. Microsegmentation có thể triển khai bằng distributed firewall, host firewall, CNI policy hoặc công nghệ khác; không có một sản phẩm duy nhất bắt buộc.

### 4.1. VLAN tách broadcast domain nhưng không đủ

Giả sử VLAN 10 là nhân viên và VLAN 30 là database. Một router định tuyến giữa hai VLAN:

~~~text
Staff VLAN 10 ---- Switch L2 ---- L3 gateway ---- DB VLAN 30
                                        |
                                 ACL / Firewall?
~~~

Nếu gateway định tuyến tự do, chỉ đổi tên VLAN và subnet **không chặn** các kết nối từ Staff đến DB. Phải có rule tại điểm định tuyến hoặc host/workload. Ngược lại, hai máy trong **cùng VLAN 10** có thể truyền frame trực tiếp qua switch, nên một firewall đặt giữa VLAN 10 và VLAN 30 không thể tự kiểm soát luồng Staff ↔ Staff.

Đây là nguyên nhân thường gặp của nhận định sai **“đã tách VLAN nghĩa là mọi traffic nội bộ đã bị cô lập”**.

### 4.2. Phân đoạn bằng host và distributed firewall

Đưa điểm thực thi tới host hoặc hypervisor có thể giải quyết vấn đề cùng subnet:

~~~text
              VLAN 20 / subnet 10.20.20.0/24
     App-A ---------------------------- App-B
       |                                  |
    Host FW A                         Host FW B
       |                                  |
  Cho TCP/443 từ                    Chặn SSH từ App-A
  frontend hợp lệ                    nếu không có nhu cầu
~~~

Một hệ thống quản trị tập trung có thể phân phối policy dựa trên **nhãn** như role=app, environment=prod, owner=team-a. Tuy nhiên nhãn và quyền được thay nhãn phải đáng tin: nếu đối thủ có thể tự gán nhãn **role=database-admin** cho workload của mình, chính sách phân đoạn có nguy cơ bị vượt qua qua control plane.

## 5. Xác định luồng east-west theo nguồn, đích và nhu cầu nghiệp vụ

Bước đầu tiên là xác định **ai cần kết nối đến ai, bằng giao thức và cổng nào**. Với TCP/UDP, có thể mô tả bằng các trường:

~~~text
Source zone / source workload / source IP
Destination zone / destination workload / destination IP
L4 protocol, destination port
Direction, connection state, identity nếu có
Action, log, owner, justification
~~~

Ví dụ, ứng dụng thanh toán cần gọi PostgreSQL:

~~~text
Source:      payment-api (App zone)
Destination: payment-db (Data zone)
Protocol:    TCP
Dest. port:  5432
Action:      ALLOW
Reason:      Truy xuất giao dịch
~~~

Như vậy khác với một rule **ALLOW App zone → Data zone ANY PORT**. Rule sau dễ tạo đường truy cập không cần thiết tới các dịch vụ quản trị hoặc DB khác.

### 5.1. Ma trận kết nối minh họa

| ID | Nguồn | Đích | Giao thức/cổng đích | Kỳ vọng | Chủ sở hữu/lý do |
|---|---|---|---|---|---|
| EW-01 | Frontend | Application API | TCP/8443 | Allow | Web gọi API |
| EW-02 | Application API | Database | TCP/5432 | Allow | Giao dịch nghiệp vụ |
| EW-03 | Application API | Cache | TCP/6379 | Allow | Đọc/ghi cache |
| EW-04 | Workload hợp lệ | Internal DNS resolver | UDP/53, TCP/53 | Allow | Phân giải tên |
| EW-05 | Monitoring | Agent/metrics endpoint | TCP/9100 (nếu dùng) | Allow | Thu thập telemetry |
| EW-06 | Backup service | Backup endpoint/DB theo thiết kế | Cổng, chiều và quyền cụ thể | Allow có điều kiện | Sao lưu |
| EW-07 | Staff | Database trực tiếp | TCP/5432 | Deny | Staff chỉ qua ứng dụng |
| EW-08 | Guest | App/Data/Management | All không được cấp | Deny | Tách vùng không tin cậy |
| EW-09 | App zone | Management | TCP/22, 3389 | Deny mặc định | Không cho đường quản trị ngang |
| EW-10 | Workload bất kỳ ngoài danh sách | Tài sản nhạy cảm | Luồng mới chưa cấp | Deny mặc định | Quyền tối thiểu |

Các port là ví dụ; phải thay bằng giao thức thực tế, kể cả mTLS, gRPC, database proxy hoặc cổng riêng của từng hệ thống. Dịch vụ quản lý có thể cần kết nối hai chiều hoặc một đường agent outbound; nên quan sát hoạt động thực trước khi chốt rule.

### 5.2. Default deny theo vùng nhạy cảm

**Default deny** có nghĩa một luồng mới không nằm trong danh sách được cho phép sẽ bị chặn tại điểm kiểm soát tương ứng. Với mạng nội bộ, cách thường dùng là:

1. Xác định tập workload và traffic quan trọng cần bảo vệ.
2. Thiết lập baseline các luồng hợp lệ.
3. Cho phép chính xác những luồng bắt buộc.
4. Từ chối những luồng mới không được cấp.
5. Ghi log/telemetry đủ để phát hiện cả lỗi nghiệp vụ và hành vi đáng ngờ.

Default deny không có nghĩa chặn bừa mọi gói phản hồi: firewall stateful thường cho phép traffic phản hồi thuộc kết nối đã được cấp. Với ACL stateless, phải mô tả luồng chiều về rõ ràng.

### 5.3. Không chỉ dùng destination port

Cho phép TCP/443 từ mọi workload tới mọi đích không tạo cô lập có ý nghĩa: hầu hết dịch vụ nội bộ và API quản trị có thể dùng 443. Với tài sản quan trọng, nên giới hạn **cả nguồn, đích, giao thức/cổng và danh tính** khi nền tảng hỗ trợ.

Cũng không mặc định TCP/443 là HTTPS an toàn: ứng dụng có thể chạy giao thức khác trên port đó, TLS có thể kết thúc ở proxy, và quyền ứng dụng vẫn cần được kiểm tra.

## 6. Thiết kế một kiến trúc east-west isolation

Giả sử doanh nghiệp có:

~~~mermaid
flowchart TD
    Internet[Internet] --> EDGE[Firewall / Reverse Proxy]
    EDGE --> FE[Frontend VLAN 10]
    FE --> FW[Firewall liên vùng]
    FW --> API[Application VLAN 20]
    API --> HFW[Host/Distributed policy]
    HFW --> DB[(Database VLAN 30)]
    HFW --> CACHE[(Cache VLAN 40)]
    STAFF[Staff VLAN 50] --> FW
    GUEST[Guest VLAN 60] --> GF[Guest isolation / policy]
    MGMT[Management VLAN 99] --> FW
    GF --> Internet
    VPN[Admin VPN] --> FW
~~~

Đây là sơ đồ logic. Hệ thống thực có thể dùng cùng VLAN cho nhiều workload, overlay SDN, cloud VPC hoặc Kubernetes; điều kiện quan trọng là **lưu lượng thực đi qua đúng điểm thực thi chính sách**.

### 6.1. Chọn trust boundary

Đặt ranh giới tối thiểu giữa:

- Guest/IoT và Staff.
- Staff và App/Data.
- Frontend public và backend nhạy cảm.
- Application với DB, cache, queue và secret store.
- Workload thông thường và Management/Control plane.
- Production với staging/dev/test.
- Backup với các máy nghiệp vụ và mạng người dùng.
- Đơn vị, khách hàng hoặc tenant khác nhau khi yêu cầu cách ly cao.

Tách quá thô để nhiều dịch vụ khác độ nhạy trong cùng một zone có thể làm thiếu ranh giới. Tách quá nhỏ khi chưa hiểu dependency sẽ gây gián đoạn, rule khó quản trị và nguy cơ mở ngoại lệ quá rộng sau sự cố. Phạm vi policy nên dựa vào **tài sản và luồng nghiệp vụ**.

### 6.2. Đặt policy trên đường dữ liệu thực tế

Ví dụ hai VM cùng subnet có thể chuyển qua switch/virtual switch mà không đi qua firewall gateway. Muốn chặn VM-A → VM-B cần một trong các điểm kiểm soát có thể thấy luồng đó, như host firewall, distributed firewall hoặc thay đổi kiến trúc định tuyến.

Trong cloud, một số traffic giữa workload cùng subnet/VPC có thể được lọc bởi security group hoặc distributed policy tại NIC; network ACL ở subnet lại có ranh giới và đặc tính khác. **Không giả định tất cả lưu lượng cloud đều đi qua một firewall trung tâm**, kể cả khi sơ đồ có vẽ nó.

### 6.3. Thiết kế đường quản trị riêng

Máy ứng dụng thông thường không nên có quyền trực tiếp SSH/RDP đến hàng loạt máy khác. Có thể giới hạn quyền quản trị vào **jump host/bastion, VPN quản trị, PAM và nhóm được xác thực**.

Cần cân nhắc các công cụ quản lý cấu hình, backup, giám sát và sửa lỗi thường có quyền rộng. Những luồng đó phải có owner, logging, xác thực mạnh và chính sách truy cập cụ thể; không vì chúng mang nhãn “management” mà cấp quyền đến mọi tài sản.

## 7. Stateful, stateless và chiều kết nối

**Stateful firewall** theo dõi kết nối đã được cho phép; phản hồi phù hợp với phiên có thể được chấp nhận mà không cần mở cổng động cho toàn bộ mạng. **Stateless ACL** đánh giá từng gói độc lập, có thể cần rule chiều về với source/destination đảo chiều.

Một luồng TCP đến DB:

~~~text
Ứng dụng                          Database
10.20.20.21:52011  ------->  10.20.30.15:5432   TCP SYN
10.20.20.21:52011  <-------  10.20.30.15:5432   TCP SYN-ACK
10.20.20.21:52011  ------->  10.20.30.15:5432   TCP ACK / data
~~~

Rule cho kết nối mới nên nhắm **destination port 5432**, không nhầm với source port động 52011. Nếu có thiết bị stateless trên đường phản hồi, phải kiểm tra policy cho **DB:5432 → App:ephemeral port**. NAT và proxy có thể thay IP hoặc port ở điểm quan sát.

UDP không có bắt tay như TCP; một số firewall tạo trạng thái theo cặp địa chỉ/cổng và timeout. Với DNS, phải xét cả UDP/53 và TCP/53 nếu luồng yêu cầu. ICMP/ICMPv6 không dùng cổng TCP/UDP và có một số loại thông báo thiết yếu cho hoạt động mạng; chặn tất cả có thể làm hỏng Path MTU Discovery hoặc Neighbor Discovery.

**Không đủ để nói “đã allow một chiều” rồi mặc định ứng dụng sẽ hoạt động.** Đường đi, chiều về, state tracking, routing bất đối xứng và host firewall đều có thể ảnh hưởng.

## 8. Cô lập east-west với switch, VLAN và firewall nội bộ

### 8.1. Tách mạng người dùng và mạng máy chủ

Một thiết kế LAN có thể dùng VLAN theo chức năng:

| VLAN | Vai trò | Quy tắc đề xuất |
|---|---|---|
| 10 | Frontend | Chỉ nhận luồng public/Staff được cấp, chỉ gọi API đã định |
| 20 | Application | Gọi DB/cache/DNS/queue theo danh sách cần thiết |
| 30 | Database | Chỉ nhận luồng từ App/backup/monitoring được phê duyệt |
| 50 | Staff | Truy cập frontend và dịch vụ nội bộ qua cổng cụ thể |
| 60 | Guest | Internet và các dịch vụ khách được phép; không vào Management/Data |
| 99 | Management | Giới hạn theo bastion, NAC và tài khoản quản trị |

Những VLAN này chỉ là ví dụ số. Phải cấu hình VLAN access/trunk, định tuyến và policy ở điểm giao tiếp giữa các VLAN. **Tách VLAN làm giảm broadcast domain; ACL/firewall mới thể hiện điều kiện kết nối liên VLAN**, nếu không có cơ chế khác hạn chế.

### 8.2. Trong cùng một VLAN

Một tập máy Windows cùng subnet có thể giao tiếp trực tiếp qua switching. Nếu mục tiêu là chặn máy người dùng truy cập SMB của máy người dùng khác, cần xét **host firewall, client isolation, private VLAN/protected port, phân nhóm endpoint hoặc distributed firewall**, tùy thiết bị và ứng dụng.

Nên phân biệt các kỹ thuật:

- **Port isolation/private VLAN:** hạn chế tương tác L2 giữa các cổng/endpoint theo cơ chế thiết bị.
- **Host firewall:** giới hạn ingress/egress ngay trên máy, có thể match IP, port, profile, chương trình hoặc danh tính tùy nền tảng.
- **Microsegmentation agent/SDN:** áp policy cho nhóm workload, kể cả khi chúng cùng subnet.
- **Routing qua firewall:** chuyển một số luồng qua điểm thực thi policy có kiểm soát, với điều kiện topology thật sự bảo đảm mọi đường bắt buộc đi qua.

Không có cơ chế nào mặc định thay thế xác thực ứng dụng hoặc giải quyết mọi loại tấn công ở L2 như ARP/ND manipulation; cần bảo vệ L2, NAC và giám sát riêng khi phù hợp.

## 9. East-west isolation trong cloud

Cloud có thể cung cấp security group, firewall quản lý, network ACL, route table, private endpoint, workload identity và network telemetry. Những công cụ này khác nhau theo nhà cung cấp; cần xác minh ngữ nghĩa thực tế thay vì áp một mô hình duy nhất.

### 9.1. Security group và network ACL

| Thuộc tính | Security group của nhiều nền tảng | Network ACL hoặc policy tại subnet |
|---|---|---|
| Điểm áp | Thường gắn với NIC/VM/workload | Gắn với subnet hoặc điểm mạng tương ứng |
| Cách chọn nguồn/đích | CIDR, SG/object reference hoặc cơ chế tương đương | Thường IP/CIDR, protocol và port |
| Trạng thái phiên | Nhiều SG (ví dụ AWS SG) là **stateful** | Một số cloud NACL (ví dụ AWS NACL) là **stateless** |
| Allow/Deny | Có sản phẩm chủ yếu là rule allow | Có thể hỗ trợ allow/deny và thứ tự |
| Chiều về | Tùy state tracking của nền tảng | Có thể cần rule riêng cho ephemeral port |

**Ví dụ AWS:** security group cho DB thường có thể cho phép TCP/5432 từ **security group của app** thay vì toàn bộ VPC CIDR. Tuy nhiên quyền thực tế phụ thuộc các SG gắn với tài nguyên, quan hệ tham chiếu, route, NACL, policy tổ chức và cấu hình DB. NACL stateless có thể cần cho phép traffic phản hồi thích hợp theo chiều và dải port động.

**Ví dụ Azure/GCP:** network security group, firewall rule và policy trong các nền tảng đó có cách gắn tài nguyên, độ ưu tiên, implied rules và state tracking khác nhau. Không chép nguyên cú pháp hoặc suy luận thứ tự từ AWS sang sản phẩm khác.

### 9.2. East-west giữa VPC/VNet, vùng và tài khoản cloud

Các kết nối private peering, transit hub, VPN site-to-site hoặc private link có thể tạo đường giữa các vùng mạng trước đó tách biệt. Một route hợp lệ **không tự động cho phép traffic**, nhưng cũng không bảo đảm đã có firewall giữa các workload.

Cần kiểm tra **cả data plane và control plane**:

- Data plane: route, network ACL, SG, firewall, host policy, DNS, load balancer.
- Control plane: ai có thể sửa SG, route table, IAM role, private endpoint, cluster policy hoặc log cấu hình?
- Identity plane: workload có credential/token nào để truy cập dịch vụ?
- Telemetry: flow logs, audit logs, thay đổi policy, sự kiện truy cập có đủ để điều tra không?

Nếu một tài khoản IAM bị lộ có quyền tự mở SG của DB, cô lập ban đầu có thể bị vô hiệu bằng thay đổi cấu hình. Do đó cần IAM tối thiểu, phân tách nhiệm vụ, approval, audit và guardrail độc lập với người quản trị workload.

### 9.3. Serverless và dịch vụ được quản lý

Một hệ thống có thể sử dụng serverless functions, managed database hoặc API dịch vụ cloud không đặt cùng subnet như VM thông thường. Hãy xem dịch vụ hỗ trợ những tùy chọn **private endpoint, mạng gắn VPC/VNet, service perimeter, IAM và policy theo danh tính** nào.

Không đồng nhất việc có tên “private” với không thể truy cập từ nguồn khác; phải xác minh public exposure, endpoint policy, DNS, route và quyền dịch vụ.

## 10. Cô lập pod và dịch vụ trong Kubernetes

Kubernetes có mô hình mạng pod-to-pod; **namespace tự nó không phải firewall**. Trong nhiều cluster, pod ở namespace khác nhau vẫn có thể trao đổi mạng nếu không có policy chặn. Kubernetes **NetworkPolicy** là một API khai báo rule ingress/egress, được thực thi bởi **CNI/datapath có hỗ trợ**. Nếu CNI không thực thi, có đối tượng NetworkPolicy vẫn chưa chứng minh cô lập hoạt động.

### 10.1. Ví dụ: DB chỉ nhận từ API được chỉ định

Giả sử:

- Namespace **data** có label **zone=data** và các pod DB mang label **app=postgres**.
- Namespace **apps** có label **zone=apps** và các pod API mang label **app=payment-api**.
- DB lắng nghe TCP/5432.
- Chỉ API được kết nối DB theo đường pod ingress; các nguồn khác mặc định bị từ chối bởi policy trong phạm vi này.

Hai NetworkPolicy minh họa được áp ở namespace **data**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: data
spec:
  podSelector: {}
  policyTypes:
    - Ingress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-payment-api-to-postgres
  namespace: data
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              zone: apps
          podSelector:
            matchLabels:
              app: payment-api
      ports:
        - protocol: TCP
          port: 5432
~~~

**Cách đọc:**

1. Policy đầu tiên chọn **mọi pod trong namespace data** và cô lập chiều ingress của chúng; không có danh sách ingress allow nên luồng ingress đến các pod đó phải được một policy phù hợp khác cho phép.
2. Policy thứ hai chọn pod có label **app=postgres** trong namespace data và cho phép ingress TCP/5432 từ những pod **đồng thời** nằm trong namespace mang label **zone=apps** và mang label **app=payment-api**.
3. Hai selector namespace và pod **nằm trong cùng một phần tử danh sách from**, vì vậy kết hợp bằng AND. Nếu viết thành **hai phần tử from riêng**, policy sẽ cho phép một hợp rộng hơn theo OR; đây là lỗi dễ mắc.
4. Các NetworkPolicy có hiệu lực được **cộng gộp quyền allow** theo từng chiều, không tuân theo nguyên tắc first-match như ACL truyền thống. Một policy khác cho phép nguồn rộng hơn vẫn có thể mở thêm đường vào DB.
5. Ví dụ chỉ định nghĩa **ingress tại DB**. Nếu API bị cô lập egress, cần có policy **egress tại namespace nguồn** cho phép đi tới DB và các dependency cần thiết.
6. Policy không đồng nghĩa đã xác thực DB; vẫn phải kiểm tra PostgreSQL auth, quyền user, TLS và secrets.

Để kịch bản hoạt động như mô tả, phải gắn label đúng cho namespace và pod bằng quy trình quản trị cluster; bảo vệ quyền sửa label/policy, kiểm tra CNI và luồng traffic thực tế. Những thành phần dùng **hostNetwork**, NodePort, CNI đặc thù, service mesh hoặc đường qua node có thể có hành vi khác nhau tùy nền tảng; cần test trong cluster tương ứng.

### 10.2. Default deny egress và dependency bị quên

Nếu thêm **default deny egress** tại namespace apps, API có thể bị mất khả năng:

- Gửi DNS đến CoreDNS hoặc NodeLocal DNSCache.
- Kết nối DB, cache, message broker và API cần thiết.
- Gọi services ngoài cluster theo chính sách.
- Gửi telemetry tới collector.
- Truy cập dịch vụ cấp chứng chỉ hoặc identity nếu kiến trúc yêu cầu.

**Không nên mở egress toàn bộ để sửa nhanh** nếu mục tiêu là cô lập. Trước tiên xác định DNS path, CIDR và loại endpoint, rồi thêm rule hẹp cho những luồng cần thiết. Khi dùng Service IP, kube-proxy hoặc eBPF datapath, thời điểm DNAT và cách NetworkPolicy áp lên gói có thể khác nhau; nên kiểm tra thực tế sau khi deploy.

### 10.3. Kiểm tra policy hiện có

Trong môi trường Kubernetes được phép quản trị, các lệnh sau **chỉ đọc** trạng thái:

~~~bash
# Xem các network policy trong cluster
kubectl get networkpolicy -A

# Xem nội dung policy thuộc namespace data
kubectl describe networkpolicy -n data

# Kiểm tra nhãn namespace và pod để phát hiện selector sai
kubectl get namespaces --show-labels
kubectl get pods -n data --show-labels
kubectl get pods -n apps --show-labels
~~~

Sự tồn tại của policy trong API server chưa đủ. Cần thử luồng **được phép và bị cấm** từ pod/nguồn có quyền được tạo trong lab, rồi đối chiếu flow logs hoặc telemetry của CNI, log ứng dụng và route.

## 11. Kết hợp identity, mTLS và Zero Trust

Cách ly theo mạng giới hạn **reachability**. **mTLS (mutual TLS)** bổ sung xác thực hai chiều và bảo vệ kênh trong phạm vi kết nối TLS. Một hệ thống Zero Trust thường không tin tưởng chỉ vì lưu lượng đến từ địa chỉ nội bộ; mỗi yêu cầu cần được xác minh theo danh tính, quyền và bối cảnh phù hợp.

Các lớp có thể vận hành cùng nhau:

~~~text
1) Network segmentation / host firewall:
   App chỉ kết nối được DB TCP/5432.

2) Workload authentication:
   DB/proxy xác minh danh tính App bằng chứng chỉ/token thích hợp.

3) Application/database authorization:
   Danh tính App chỉ được đọc/ghi bảng và thao tác cần thiết.

4) Audit + monitoring:
   Theo dõi truy cập, quyền, thay đổi chính sách và hành vi bất thường.
~~~

**Chú ý ranh giới:** mTLS không tự ngăn app đã được xác thực lạm dụng quyền nghiệp vụ, và không tự chặn gói làm nghẽn mạng trước khi phiên được xác thực. Ngược lại, chỉ chặn IP/port không xác thực được lời gọi ứng dụng. Nếu dùng service mesh, phải chắc rằng traffic mục tiêu **không bypass** được điểm thực thi mTLS/authorization qua đường khác.

Với VPN, việc người dùng vượt qua bước xác thực tunnel chỉ có nghĩa họ được tạo kết nối VPN theo chính sách. Hệ thống còn cần giới hạn đến đúng subnet, app, port và vai trò; không coi “đã vào VPN” là quyền truy cập mọi workload.

## 12. Những dịch vụ nền phải tính đến khi cô lập

Một chiến lược default deny có thể vô tình phá vỡ hệ thống nếu bỏ qua dependency. Những luồng cần đánh giá theo kiến trúc thực:

| Dịch vụ/phụ thuộc | Mục đích | Điểm cần xét trong policy |
|---|---|---|
| DNS | Phân giải tên cho ứng dụng | Resolver phù hợp, UDP/TCP 53 hoặc DoH/DoT nếu được dùng |
| DHCP | Cấp thông tin mạng cho endpoint | Luồng broadcast/relay và vị trí DHCP server |
| NTP / đồng bộ thời gian | Đồng bộ thời gian phục vụ log, TLS, xác thực | Đích đồng bộ được quản trị, thường UDP/123 |
| Directory / identity | Kerberos, LDAP/LDAPS, AD, OIDC endpoints | Các cổng thực tế, DNS, chứng chỉ, dependency chéo |
| PKI / certificate lifecycle | Cấp, gia hạn, kiểm tra trạng thái chứng chỉ | Certificate manager, CA, OCSP/CRL theo hệ thống |
| Monitoring / logging | Thu thập metrics, log, traces, alerts | Hướng agent → collector hoặc collector → agent; port và auth |
| Backup / recovery | Sao lưu và khôi phục | Nguồn, đích, thời điểm, quyền xóa/sửa và isolation của backup |
| Orchestration / control plane | Kubernetes API, cloud API, config management | API endpoint và danh tính được phép, quyền sửa policy |
| Image / package registry | Pull image, cập nhật phần mềm | Endpoint registry, proxy, lịch deploy và chính sách egress |
| Health check / load balancer | Kiểm tra backend sẵn sàng | Nguồn health checker và port/URI được phép |

Không nhất thiết tất cả dịch vụ trên đều tồn tại trong một mạng. Cách đúng là thu thập dependency đang được sử dụng và mô tả từng luồng, thay vì sao chép một danh sách port cố định vào mọi môi trường.

Một lưu ý đặc biệt là **DNS**: cô lập DB hoặc App nhưng chặn nhầm resolver có thể gây lỗi ứng dụng khó nhận biết. Ngược lại, cho phép DNS đến mọi đích ngoài Internet có thể phá mục tiêu quản lý phân giải tên; cần xem các resolver được phép và đường DoH/DoT theo chính sách tổ chức.

## 13. Quan sát east-west traffic trước khi chặn

Không thể viết policy tối thiểu nếu chưa biết hệ thống đang giao tiếp như thế nào. Các nguồn dữ liệu có thể bao gồm:

- **Firewall allow/deny logs:** cho biết quyết định ở điểm policy được thực thi.
- **Flow telemetry (NetFlow/IPFIX, VPC/VNet flow logs, CNI flow logs):** mô tả các cặp nguồn–đích, port, chiều và khối lượng; độ chi tiết tùy sản phẩm.
- **Host network telemetry:** kết nối, listener, process, interface, socket và các sự kiện của agent.
- **DNS logs:** có thể liên hệ hostname với đích được gọi, nhưng kết quả cache, NAT, shared resolver và DNS mã hóa làm giới hạn quan sát.
- **Service mesh traces/logs:** thấy workload identity và RPC trong các luồng được mesh kiểm soát.
- **IDS/IPS hoặc NDR:** phát hiện mẫu hành vi mạng bất thường, lateral movement, scan hoặc dữ liệu có dấu hiệu lạ, trong phạm vi sensor thực sự quan sát được.
- **Cloud audit/Kubernetes audit:** thay đổi policy, nhãn, IAM, service, route và cấu hình control plane.

### 13.1. Lập dependency map

Một cách làm có kiểm soát:

1. Liệt kê ứng dụng, owner, vùng và độ nhạy dữ liệu.
2. Thu luồng trong khoảng thời gian đại diện, bao gồm chạy batch, backup, bảo trì và failover.
3. Nhóm các luồng theo service identity hoặc workload role, không chỉ IP động.
4. Xác nhận **luồng nào là nghiệp vụ được phê duyệt**, luồng nào do cấu hình dư thừa, thử lại bất thường hoặc hoạt động lạ.
5. Định nghĩa policy đề xuất và chạy ở chế độ **audit/observe** nếu nền tảng hỗ trợ.
6. Kiểm thử và chuyển sang enforcement theo phạm vi nhỏ, đồng thời theo dõi log bị từ chối.

**Không tự coi “đã thấy traffic” là bằng chứng traffic đó phải được cho phép.** Log có thể ghi các lần quét, malware hoặc truy cập không mong muốn. Phải được owner nghiệp vụ xác nhận.

### 13.2. Log không luôn chứa bản rõ

TLS, VPN, MACsec và một số overlay bảo vệ dữ liệu trong phiên/chặng. Sensor đặt sai vị trí có thể chỉ thấy đường hầm, các IP gateway hoặc metadata, không thấy dịch vụ bên trong. Vì vậy nên kết hợp log tại **điểm thực thi policy hoặc endpoint**, nơi thông tin identity và workload có ý nghĩa, với telemetry mạng tại các ranh giới.

## 14. Kiểm chứng cô lập bằng những ca kiểm thử có chủ đích

Một policy được coi là đúng khi **luồng cần thiết hoạt động** và **luồng không được phép thực sự bị từ chối** từ các vị trí phù hợp.

### 14.1. Ma trận kiểm thử minh họa

Giả sử dùng các vùng trong mục 6:

| Test | Source | Destination | Traffic | Kỳ vọng |
|---|---|---|---|---|
| T1 | Frontend | Application API | TCP/8443 | Allow |
| T2 | Application API | DB | TCP/5432 | Allow |
| T3 | Application API | Cache | TCP/6379 | Allow |
| T4 | Staff | DB | TCP/5432 | Deny |
| T5 | Guest | Management | TCP/22 | Deny |
| T6 | Một App không được cấp quyền | DB | TCP/5432 | Deny |
| T7 | App hợp lệ | DNS resolver | UDP/53 và TCP/53 | Allow khi thuộc dependency |
| T8 | App | Một workload khác cùng subnet nhưng không có quan hệ nghiệp vụ | Cổng ngoài allowlist | Deny |
| T9 | VPN user thường | DB trực tiếp | TCP/5432 | Deny |
| T10 | Management được cấp phép | Endpoint quản trị theo role | Protocol/port đã duyệt | Allow |

**Test T8 rất quan trọng:** nếu firewall chỉ nằm giữa các subnet, nó có thể không thấy traffic cùng subnet. Kết quả T8 giúp xác minh liệu host/distributed policy có bảo vệ ranh giới ở mức workload hay không.

### 14.2. Ba loại kết quả cần tách biệt

| Dấu hiệu | Có thể suy ra | Chưa thể suy ra |
|---|---|---|
| TCP connect thành công | Có đường và có thành phần nhận kết nối TCP ở thời điểm thử | Người gọi có quyền vào ứng dụng, DB, hoặc dữ liệu |
| TCP timeout / không phản hồi | Đường truyền hoặc đích không hoàn tất phép thử | Chắc chắn bị firewall chặn; có thể do mất gói, listener, route |
| Log firewall ghi DENY đúng flow | Điểm thực thi có quyết định chặn với flow đó | Không còn đường thay thế nào khác nếu chưa kiểm tra topology |

Cần đối chiếu log **rule ID, source/destination thực tế, port, giao thức, thời gian và direction**. Với NAT, overlay hoặc service mesh, IP nhìn thấy tại điểm kiểm soát có thể khác địa chỉ ứng dụng dùng.

### 14.3. Lệnh quan sát trong môi trường được quản trị

Các lệnh sau dùng để **đọc trạng thái**, trừ phép thử kết nối được ghi chú riêng. Chỉ dùng trên máy và hệ thống được cấp quyền.

Trên Linux:

~~~bash
# Các TCP/UDP listener trên host
ss -lntup

# Đường đi dự kiến đến một IP trong lab private
ip route get 10.20.30.15

# Xem policy cục bộ nếu hệ thống dùng nftables
sudo nft list ruleset

# Thống kê giao diện để chẩn đoán lỗi nền
ip -s link
~~~

Trên Windows PowerShell:

~~~powershell
# Xem route và trạng thái card mạng
Get-NetRoute
Get-NetAdapter

# Xem một phần các quy tắc Windows Firewall
Get-NetFirewallRule |
  Select-Object -First 20 DisplayName, Direction, Action, Enabled

# Phép thử kết nối chủ động: chỉ dùng với đích thuộc lab được cho phép
Test-NetConnection -ComputerName 10.20.30.15 -Port 5432
~~~

Nếu dùng Wireshark hoặc tcpdump, chỉ bắt lưu lượng tại giao diện/điểm mirror được cấp quyền. Một switch bình thường không gửi mọi traffic unicast giữa các cổng khác cho máy quan sát.

**Xem counter và log tại điểm thực thi** thường quan trọng hơn việc lặp lại nhiều lần phép thử kết nối. Một probe chưa hoàn tất không đủ để quy lỗi cho phân đoạn nếu không có dữ liệu về route, listener, ACL và packet loss.

## 15. Lộ trình triển khai mà vẫn bảo đảm hoạt động hệ thống

Cô lập nội bộ thường ảnh hưởng nhiều phụ thuộc nên cần triển khai có trình tự.

### Giai đoạn 1 — Khám phá và xác định trách nhiệm

Lập inventory tài sản, owner, data classification, môi trường, subnet, cluster và dependency. Xác định ứng dụng nào là public, nào chỉ nội bộ, và những tài sản nào có mức nhạy cảm cao (DB, secrets, backup, quản trị).

### Giai đoạn 2 — Xây policy theo nguyên tắc quyền tối thiểu

Xây ma trận allow theo nguồn, đích, protocol, port, identity và direction; bổ sung dependency nền. Ghi rõ trạng thái phiên, rule priority, vị trí thực thi và xử lý IPv6. Phân loại rule bắt buộc và rule ngoại lệ có thời hạn.

### Giai đoạn 3 — Quan sát/audit

Nếu nền tảng có chế độ detect-only hoặc rule logging phù hợp, quan sát trước khi chặn. Theo dõi backup, batch, failover, update, health check và luồng quản trị không diễn ra thường xuyên.

### Giai đoạn 4 — Enforce theo phạm vi nhỏ

Ưu tiên tài sản nhạy cảm, chẳng hạn DB và management plane, hoặc nhóm workload dễ xác định dependency. Áp rule hẹp với chủ sở hữu, thời gian theo dõi, rollback và kế hoạch ứng phó. Tránh thay policy toàn bộ mạng trong một đợt khi chưa có coverage kiểm chứng.

### Giai đoạn 5 — Kiểm chứng tích cực và tiêu cực

Kiểm thử cả luồng allow lẫn deny từ **đúng nguồn quan sát**; đối chiếu log mạng và sức khỏe ứng dụng. Các ca failover, DNS, backup và đường IPv6/overlay cần được bao phủ theo kiến trúc.

### Giai đoạn 6 — Duy trì theo thay đổi

Tự động so sánh policy mong muốn với cấu hình thực (drift), phát hiện rule không còn dùng, rule quá rộng, thay đổi security group/CNI/host firewall và luồng phát sinh sau triển khai mới. Hủy quyền ngoại lệ hết hạn; xem xét lại các quan hệ dịch vụ khi ứng dụng đổi topology.

## 16. Các sai lầm thường gặp

1. **Tin rằng firewall Internet đủ để cô lập nội bộ.** Lưu lượng App → DB hoặc host → host có thể không đi qua firewall biên.
2. **Cho rằng VLAN một mình chặn truy cập.** VLAN chia miền L2; nếu router cho định tuyến liên VLAN tự do, các vùng vẫn liên lạc.
3. **Bỏ qua hai workload cùng subnet.** Gateway firewall có thể không thấy traffic đi trực tiếp qua switch hoặc virtual switch.
4. **Cấp quyền theo subnet quá rộng.** Cho cả App subnet vào DB có thể cấp đường cho các workload không cần DB; identity-based rules có thể chính xác hơn.
5. **Chặn mọi egress rồi quên DNS, NTP, identity, telemetry và backup.** Dịch vụ có thể lỗi gián tiếp dù cổng nghiệp vụ chính được mở.
6. **Quên kết nối phản hồi trên đường stateless.** TCP có thể thất bại vì ACL chiều về thiếu ephemeral port, hoặc đường bất đối xứng.
7. **Tưởng NetworkPolicy là deny rule ưu tiên cao.** Trong Kubernetes, các allow policy được cộng gộp; có policy khác cho phép rộng vẫn làm luồng được phép.
8. **Không kiểm tra CNI và selector.** Một đối tượng NetworkPolicy tồn tại không chứng minh enforcement đã có; label nhầm làm lệch nguồn/đích.
9. **Nhầm mTLS với phân đoạn L3/L4.** mTLS xác thực/bảo vệ phiên nhưng không tự giảm mọi đường tới listener hoặc khả năng DoS.
10. **Không kiểm soát control plane.** IAM, tài khoản quản trị hoặc quyền sửa label/policy bị lộ có thể mở đường mạng vốn bị chặn.
11. **Quên IPv6, VPN, peering và đường cloud private.** Cùng một tài sản có thể còn đường tiếp cận qua ranh giới khác.
12. **Coi traffic quan sát được đều là traffic hợp lệ.** Cần owner xác nhận nghiệp vụ và phát hiện hành vi bất thường trước khi allow.
13. **Đánh giá thành công chỉ qua test từ một nguồn.** Cần các test negative từ Guest, Staff, App không có quyền và đường thay thế.
14. **Tắt logging vì sợ nhiễu rồi mất khả năng điều tra.** Thay vào đó thiết kế telemetry, sampling, retention và alert có mục tiêu.
15. **Bỏ quên quyền của ứng dụng sau khi kết nối được.** Một app bị chiếm vẫn có thể khai thác những quyền tới DB đã được cho phép; cần least privilege ở tầng dữ liệu.

## 17. Bài tập tình huống và đáp án gợi ý

### Tình huống A — Hai VM cùng VLAN

Hai máy VM-A và VM-B nằm trong **10.20.20.0/24**. Chính sách liên VLAN đã chặn toàn bộ App → Management, nhưng VM-A vẫn kết nối được tới dịch vụ TCP trên VM-B.

**Câu hỏi:** có phải firewall liên VLAN bị lỗi?

**Gợi ý:** chưa chắc. VM-A và VM-B có thể trao đổi trực tiếp trong cùng subnet qua virtual switch, không đi qua firewall liên VLAN. Muốn giới hạn ở mức VM cần host firewall/distributed firewall hoặc kiến trúc đưa traffic qua điểm kiểm soát phù hợp.

### Tình huống B — API gọi DB được, Staff gọi DB bị chặn

Một policy chỉ cho **payment-api → payment-db TCP/5432**. Kiểm chứng từ API thành công; từ laptop Staff kết nối TCP/5432 bị từ chối.

**Câu hỏi:** đã chứng minh an toàn hoàn toàn cho dữ liệu chưa?

**Gợi ý:** chưa. Đây là bằng chứng có ích về ranh giới mạng tại các nguồn đã thử. Còn cần kiểm tra nguồn khác, đường IPv6, host/cluster policy, tài khoản DB, quyền data, bảo vệ secret, TLS và khả năng API bị chiếm rồi lạm dụng kết nối hợp lệ.

### Tình huống C — Kubernetes có policy nhưng pod lạ vẫn vào DB

DB có NetworkPolicy như mục 10; một pod khác trong namespace khác vẫn kết nối TCP/5432 thành công.

**Câu hỏi:** điều gì phải kiểm tra trước?

**Gợi ý:** xác nhận CNI thực thi NetworkPolicy, labels namespace/pod, các policy allow khác đang áp dụng, network namespace/hostNetwork, cách Service DNAT và datapath xử lý. NetworkPolicy có cơ chế gộp allow, nên policy hiện có có thể mở thêm quyền.

### Tình huống D — Default deny egress làm ứng dụng không khởi động

Một ứng dụng sau khi chặn egress chỉ còn cho kết nối TCP/5432 tới DB, nhưng không phân giải được hostname của DB.

**Câu hỏi:** có nhất thiết mở toàn bộ egress không?

**Gợi ý:** không. Tìm luồng DNS thực tế (CoreDNS, NodeLocal DNSCache, resolver nội bộ, port và IP), thêm allow phù hợp, rồi kiểm chứng những dependency khác như CA, registry hoặc telemetry. Mục tiêu là khôi phục dependency chính xác mà không mở rộng quyền quá mức.

### Tình huống E — VPN cấp đường vào mạng quản trị

Một người dùng VPN thông thường có IP thuộc VPN pool và có route tới Management subnet. Firewall management hiện cho **toàn bộ VPN pool** SSH vào jump host.

**Câu hỏi:** còn vấn đề thiết kế nào?

**Gợi ý:** có route và IP nguồn thuộc VPN chưa chứng minh người dùng có role quản trị. Nên kiểm tra quyền theo nhóm/danh tính, MFA, trạng thái thiết bị, ACL theo vai trò, host authentication và audit phiên; chỉ những tài khoản được cấp mới tới jump host.

### Tình huống F — Security group bị thay đổi

DB chỉ cho App security group truy cập. Một principal cloud có quyền sửa security group đã thêm một rule rộng **0.0.0.0/0 TCP/5432**.

**Câu hỏi:** đây là thất bại của lớp nào và cần làm gì?

**Gợi ý:** một vấn đề control plane làm thay đổi chính sách data plane. Xác minh route, public exposure và policy thực tế, thu hồi quyền sửa thừa, áp guardrail/chính sách tổ chức, kiểm tra audit log và khôi phục SG đúng thiết kế. Mở rule không tự chứng minh DB đã truy cập được từ Internet nếu thiếu public route/endpoint, nhưng là biến đổi rủi ro cần xử lý.

## 18. Checklist review east-west isolation

- [ ] Đã định nghĩa phạm vi east-west và north-south theo kiến trúc cụ thể.
- [ ] Đã xác định tài sản nhạy cảm, owner, data flow và ranh giới tin cậy.
- [ ] Đã lập ma trận allow theo nguồn, đích, protocol/port, direction và nhu cầu nghiệp vụ.
- [ ] Đã kiểm tra nguồn bị chiếm hoặc role ít quyền **không** có đường trực tiếp tới DB/Management/Backup ngoài nhu cầu.
- [ ] Đã xác định tất cả điểm thực thi firewall/ACL/host/distributed policy, bao gồm traffic cùng VLAN/subnet.
- [ ] Đã cân nhắc cả IPv4 và IPv6, VPN, NAT, peering, proxy, overlay và đường cloud riêng.
- [ ] Đã hiểu stateful/stateless và luồng phản hồi.
- [ ] Đã bảo vệ quyền sửa policy, labels, routes, identity và cloud security groups.
- [ ] Đã tính dependency DNS, time, directory/identity, PKI, telemetry, backup, orchestration.
- [ ] Đã kiểm tra hiệu lực của CNI/NetworkPolicy nếu dùng Kubernetes; hiểu quy tắc selector và allow cộng gộp.
- [ ] Đã triển khai xác thực dịch vụ/mTLS hoặc quyền ứng dụng khi độ nhạy yêu cầu.
- [ ] Đã có kết quả kiểm tra **allow** và **deny** từ các nguồn phù hợp.
- [ ] Đã đối chiếu thử nghiệm với log/counter/flow telemetry tại điểm thực thi.
- [ ] Đã có quy trình rollout, giám sát, rollback, xử lý ngoại lệ và review theo thay đổi.

## 19. Kết luận

**East-west isolation** biến nguyên tắc **“chỉ cho phép luồng thật sự cần thiết”** thành các ranh giới thực thi giữa những thành phần nội bộ. Phân đoạn bằng VLAN/subnet định hình mạng; firewall, ACL, host/distributed policy và cloud/Kubernetes controls quyết định traffic nào được đi qua; identity, mTLS và quyền ứng dụng hạn chế việc lạm dụng một kết nối đã được cấp.

Cách thiết kế bền vững bắt đầu từ **inventory và dependency map**, sau đó xác định trust boundary, viết rule hẹp, giám sát lưu lượng thực, thử nghiệm từ nhiều điểm nhìn và duy trì kiểm soát khi hạ tầng thay đổi. Khi mạng đã giới hạn được các đường đi ngang không cần thiết, một thiết bị hoặc workload bị xâm nhập sẽ khó mở rộng tác động tới toàn bộ hệ thống hơn, đồng thời đội vận hành có bằng chứng rõ ràng để đánh giá và cải thiện kiến trúc an toàn.
