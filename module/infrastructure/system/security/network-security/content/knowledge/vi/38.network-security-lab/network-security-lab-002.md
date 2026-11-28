# Lab bảo mật mạng: Vẽ topology và các trust boundary

## 1. Bối cảnh và mục tiêu

Một sơ đồ mạng chỉ liệt kê router, switch và địa chỉ IP chưa đủ để giải thích hệ thống an toàn đến đâu. Đối với công việc bảo mật, cần nhìn thấy **dữ liệu đi từ đâu đến đâu**, **bên nào được tin cậy ở mức nào**, **điểm nào buộc phải kiểm tra quyền** và **đường nào bị cấm**. Đó là mục đích của việc vẽ **network topology** cùng các **trust boundary** (ranh giới tin cậy).

Trong module **SECURITY_NETWORK_SECURITY**, kiến thức về phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây và hạ tầng đám mây được đưa vào một bài tập thiết kế có thể kiểm chứng. Người học sẽ vận dụng phân tích lưu lượng và mô hình hóa mối đe dọa để tạo ra một bản đồ bảo mật phục vụ vận hành, rà soát thay đổi và ứng phó sự cố.

Sau khi hoàn thành lab, bạn có thể:

1. Đọc yêu cầu hệ thống và dựng topology ở mức mạng/vùng bảo mật.
2. Nhận diện tài sản, dữ liệu nhạy cảm, điểm vào và các chủ thể có mức tin cậy khác nhau.
3. Vẽ rõ **ranh giới tin cậy**, gắn từng luồng vượt ranh giới với điểm cưỡng chế chính sách.
4. Lập ma trận luồng mạng với hướng, giao thức, cổng, danh tính, mã hóa và trạng thái cho phép/chặn.
5. Chỉ ra đường truy cập trái phép tiềm năng và đề xuất biện pháp giảm thiểu.
6. Xây dựng bộ kiểm thử để chứng minh sơ đồ khớp với chính sách thực tế.

**Sản phẩm cuối của bài thực hành** là một sơ đồ topology chú thích đầy đủ, bảng trust boundary, ma trận luồng và danh sách kiểm thử có kết quả mong đợi. Bài học cung cấp dữ liệu và đáp án tham khảo để bạn thực hiện độc lập trong môi trường lab.

## 2. Những khái niệm phải phân biệt

### 2.1. Topology vật lý và topology logic

| Góc nhìn | Thể hiện | Dùng để trả lời |
| --- | --- | --- |
| **Vật lý** | Thiết bị, cổng mạng, kết nối cáp, access point, đường WAN | Sự cố hoặc lưu lượng có thể đi qua thiết bị nào? |
| **Lớp 2 / lớp 3** | VLAN, subnet, gateway, bảng định tuyến, VRF, NAT | Hai vùng có đường đi IP như thế nào? |
| **Logic ứng dụng** | Reverse proxy, API, database, DNS resolver, IAM, dịch vụ cloud | Dữ liệu nghiệp vụ di chuyển giữa thành phần nào? |
| **Bảo mật** | Trust zone, trust boundary, enforcement point, identity, allow/deny, sensor | Chính sách được thực thi ở đâu và có thể bị vượt qua thế nào? |

Trong bài này, ưu tiên sơ đồ **logic và bảo mật**. Có thể bổ sung sơ đồ vật lý riêng nếu cần đánh giá đường WAN dự phòng, điểm lỗi đơn hoặc nơi đặt cảm biến IDS/IPS.

### 2.2. Trust zone, trust boundary và điểm cưỡng chế

- **Trust zone:** tập hợp các thành phần được quản lý theo một chính sách truy cập tương đồng, chẳng hạn vùng DMZ, ứng dụng, dữ liệu, quản trị, khách Wi-Fi hoặc tài nguyên cloud.
- **Trust boundary:** nơi **giả định về độ tin cậy thay đổi** khi yêu cầu hoặc dữ liệu đi qua. Ví dụ Internet → DMZ, ứng dụng → database, nhân viên từ xa → quyền quản trị.
- **Enforcement point:** nơi thật sự kiểm tra và thi hành quyết định truy cập, chẳng hạn next-generation firewall (NGFW), ACL, ZTNA proxy, VPN gateway, PAM/bastion, security group, Kubernetes NetworkPolicy hoặc lớp xác thực của database.
- **Security control:** chính sách hoặc cơ chế bảo vệ: mặc định từ chối, MFA, TLS/mTLS, IDS/IPS, WAF, DNS filtering, ghi log, giới hạn cổng, xác thực dịch vụ.
- **Data flow:** một trao đổi có hướng giữa hai thành phần, kèm mục đích và điều kiện vận hành.

**Quan trọng:** trust boundary không bắt buộc trùng với VLAN, subnet hay thiết bị mạng. Hai tiến trình cùng subnet nhưng thuộc tenant khác nhau vẫn có ranh giới tin cậy; ngược lại, hai subnet khác nhau có thể do cùng một chính sách dịch vụ quản lý. **Vẽ một đường ranh giới không tự tạo ra kiểm soát bảo mật**: phải chỉ ra cơ chế nào chặn hoặc cho phép lưu lượng vượt đường đó.

### 2.3. Cách nhận diện ranh giới

Hãy đặt câu hỏi cho từng luồng: người gửi có cùng quản trị và cùng mức tin cậy với người nhận không; thông tin xác thực có được kiểm tra lại không; dữ liệu có đổi độ nhạy cảm; kết nối có rời khỏi máy, vùng, tenant, cloud account hoặc nhà cung cấp hay không? Một câu trả lời “có” thường báo hiệu cần mô tả trust boundary.

Ví dụ, việc người dùng đã đăng nhập VPN **không mặc nhiên** cấp quyền SSH vào database. Mạng VPN là điểm vào; phiên SSH hoặc truy cập dữ liệu vẫn cần kiểm tra quyền cụ thể tại bastion và máy đích.

## 3. Đề bài: hệ thống bán hàng đa vùng

Nhóm bảo mật được giao vẽ kiến trúc cho ứng dụng bán hàng với các thành phần:

- Khách hàng truy cập cổng HTTPS công khai thông qua NGFW và WAF/reverse proxy.
- Ứng dụng backend xử lý đơn hàng và truy cập cơ sở dữ liệu PostgreSQL.
- Nhân viên văn phòng chỉ được dùng giao diện web, không truy cập thẳng database.
- Nhân viên từ xa quản trị hệ thống qua cổng ZTNA có MFA và bastion.
- Mạng Wi-Fi khách chỉ được truy cập Internet; không được kết nối tới hệ thống nội bộ.
- Workload đối soát trên cloud cần gọi một API nội bộ được duyệt qua đường kết nối riêng.
- DNS resolver nội bộ cung cấp phân giải tên; SIEM thu thập log bảo mật.

Mục tiêu thiết kế là **cho phép đúng luồng cần thiết** nhưng không tạo đường đi tự do từ Internet, mạng khách hoặc máy trạm người dùng tới database và mạng quản trị.

### 3.1. Phạm vi và giả định lab

Các địa chỉ dưới đây là **địa chỉ minh họa**, không đại diện mạng production nào. Tất cả thay đổi và kiểm thử kết nối chỉ thực hiện trên hạ tầng thí nghiệm hoặc hệ thống đã được cho phép.

| Zone | Subnet / phạm vi mẫu | Thành phần nổi bật | Mức độ tin cậy tương đối |
| --- | --- | --- | --- |
| Z0 — Internet / đối tác bên ngoài | Không quản lý | Khách hàng, mạng nhân viên từ xa, Internet | Không tin cậy |
| Z1 — DMZ / edge | 10.60.10.0/24 | NGFW, WAF/reverse proxy **10.60.10.10**, cổng ZTNA | Vùng tiếp xúc với bên ngoài |
| Z2 — Ứng dụng | 10.60.20.0/24 | Backend API **10.60.20.10** | Tin cậy có điều kiện |
| Z3 — Dữ liệu | 10.60.30.0/24 | PostgreSQL **10.60.30.10** | Nhạy cảm cao |
| Z4 — Quản trị | 10.60.40.0/24 | Bastion **10.60.40.10** | Đặc quyền cao |
| Z5 — Văn phòng | 10.60.50.0/24 | Máy nhân viên, access switch | Thiết bị có quản trị nhưng chưa mặc nhiên có quyền server |
| Z6 — Wi-Fi khách | 10.60.60.0/24 | Thiết bị khách qua SSID guest | Không tin cậy |
| Z7 — Dịch vụ bảo mật | 10.60.70.0/24 | DNS **10.60.70.53**, SIEM **10.60.70.20** | Hạ tầng hỗ trợ cần bảo vệ |
| Z8 — Cloud | 10.80.10.0/24 | Job đối soát và cloud gateway | Khác miền vận hành, tin cậy có điều kiện |

**Giả định triển khai:** các subnet có gateway và phân đoạn, lưu lượng liên vùng được kiểm soát tại NGFW hoặc chính sách phân đoạn tương đương. Cổng Internet có NAT/định tuyến cần thiết. Cloud gateway có đường VPN site-to-site IPsec hoặc kết nối riêng với điểm kết thúc kiểm soát tại biên tổ chức. Ví dụ là **sơ đồ logic**; đường truyền vật lý, giao diện thiết bị và route cụ thể sẽ do bản thiết kế mạng riêng xác định.

**Phạm vi dữ liệu:** dữ liệu tài khoản khách hàng, địa chỉ giao hàng và đơn hàng được lưu trong Z3. Dữ liệu nhạy cảm không được chuyển sang Z0/Z6 bằng đường không được duyệt. Trách nhiệm của nhóm vận hành là bảo vệ cả lưu lượng lẫn quyền quản trị hệ thống chứa dữ liệu này.

## 4. Bước thực hành 1: vẽ topology tổng thể

Vẽ các zone theo mức độ tin cậy; mỗi zone chứa những thành phần chính. Mũi tên thể hiện **luồng logic đã dự kiến**, có nhãn ID để tra bảng ma trận. Mũi tên đi trực tiếp giữa hai service **không** có nghĩa là lưu lượng bỏ qua firewall; điểm kiểm soát bắt buộc được nêu ở bảng trust boundary và chính sách triển khai.

~~~mermaid
flowchart LR
    subgraph OUT["Z0 | Nguồn bên ngoài"]
        INTERNET["Khách Internet"]
        REMOTE["Nhân viên từ xa"]
    end
    subgraph EDGE["Z1 | DMZ và biên mạng"]
        FW["NGFW / NAT / IPS"]
        WAF["WAF + Reverse proxy<br/>10.60.10.10"]
        ZTNA["ZTNA gateway + MFA"]
    end
    subgraph APPZONE["Z2 | Ứng dụng"]
        API["Backend API<br/>10.60.20.10"]
    end
    subgraph DBZONE["Z3 | Dữ liệu"]
        DB[("PostgreSQL<br/>10.60.30.10")]
    end
    subgraph ADMIN["Z4 | Quản trị"]
        BASTION["Bastion / PAM<br/>10.60.40.10"]
    end
    subgraph OFFICE["Z5 | Văn phòng"]
        STAFF["Máy nhân viên"]
    end
    subgraph GUEST["Z6 | Wi-Fi khách"]
        VISITOR["Thiết bị guest"]
    end
    subgraph SECURITY["Z7 | Dịch vụ an ninh"]
        DNS["DNS resolver<br/>10.60.70.53"]
        SIEM["SIEM<br/>10.60.70.20"]
    end
    subgraph CLOUD["Z8 | Cloud"]
        JOB["Job đối soát"]
        CGW["Cloud VPN gateway"]
    end

    INTERNET -->|"F01 TLS/443"|FW
    FW -->|"F01"|WAF
    STAFF -->|"F07 TLS/443"|WAF
    WAF -->|"F02 TLS/8443"|API
    API -->|"F03 TLS TCP/5432"|DB
    REMOTE -->|"F04 TLS/443 + MFA"|ZTNA
    ZTNA -->|"F05 SSH/22"|BASTION
    BASTION -->|"F06 SSH/22"|API
    VISITOR -->|"F08 Internet only"|FW
    API -.->|"F09 DNS/53"|DNS
    FW -.->|"F10 Syslog TLS/6514"|SIEM
    WAF -.->|"F10 logs"|SIEM
    ZTNA -.->|"F10 logs"|SIEM
    JOB -->|"Tunnel riêng"|CGW
    CGW -->|"F11 qua IPsec"|FW
    FW -->|"F11 TLS/8443"|API
~~~

Sơ đồ trên là **topology logic**, chưa đủ thông tin để triển khai trực tiếp. Khi chuyển sang bản thiết kế thi công, cần bổ sung số lượng NIC, interface, VLAN trunk/access, route, HA gateway, địa chỉ NAT, điểm kết thúc IPsec và vị trí các cảm biến mạng. Một mũi tên F01 hoặc F11 có thể gồm nhiều hop vật lý.

### 4.1. Quy ước ký hiệu của bài lab

| Ký hiệu | Ý nghĩa |
| --- | --- |
| Khung **Z0–Z8** | Vùng mạng hoặc miền quản trị |
| Mũi tên liền, có Fxx | Luồng truy cập chính được đề xuất/đánh giá |
| Mũi tên nét đứt | Luồng hỗ trợ như DNS và log, vẫn phải có chính sách |
| **TB-xx** trong bảng ranh giới | Vị trí chuyển đổi mức tin cậy và kiểm tra truy cập |
| Biểu tượng database | Tài sản chứa dữ liệu cần bảo vệ |
| Nhãn giao thức/cổng | Gợi ý yêu cầu kết nối; phải xác minh với chủ dịch vụ |

Không dùng màu đỏ/xanh làm bằng chứng duy nhất về quyền truy cập. Nếu vẽ bằng diagrams.net, Visio hoặc công cụ tương tự, cần có chú giải “allow/deny/proposed”, vì ảnh in đen trắng hoặc người xem bị hạn chế thị giác vẫn phải hiểu được sơ đồ.

## 5. Bước thực hành 2: đánh dấu các trust boundary

Xác định điểm nào đang chuyển từ một miền tin cậy sang miền khác. Đặt mã **TB-01...TB-08** tại các cạnh qua ranh giới trên bản sơ đồ của bạn và liên kết với bảng sau:

| Boundary | Luồng vượt ranh giới | Câu hỏi bảo mật trọng tâm | Điểm kiểm soát / điều kiện cần có |
| --- | --- | --- | --- |
| **TB-01** Internet → DMZ | F01, F04 | Ai được kết nối đến edge? | NGFW giới hạn dịch vụ công khai; WAF ở nhánh web; ZTNA xác thực danh tính, MFA |
| **TB-02** DMZ → ứng dụng | F02 | Reverse proxy có thể gọi dịch vụ nào? | Firewall/segmentation chỉ cho WAF tới API TCP/8443; TLS, xác thực tại API phù hợp |
| **TB-03** Ứng dụng → dữ liệu | F03 | Service nào được đọc/ghi DB? | Chỉ backend được phép tới DB TCP/5432; TLS và tài khoản DB quyền tối thiểu |
| **TB-04** Người quản trị → vùng đặc quyền | F04–F06 | Danh tính có quyền vận hành hệ thống? | ZTNA + MFA + kiểm tra thiết bị + bastion/PAM, log phiên, quyền có thời hạn |
| **TB-05** Văn phòng → hệ thống phục vụ | F07 | Nhân viên được dùng dịch vụ nào? | Chỉ HTTPS tới giao diện được công bố; không cho đường trực tiếp tới DB/quản trị |
| **TB-06** Guest → mạng tổ chức | F08 | Wi-Fi khách có thoát khỏi vùng khách? | Tách SSID/VLAN, client isolation khi cần, deny tới RFC1918 nội bộ, cho egress Internet đã kiểm soát |
| **TB-07** Vùng ứng dụng → dịch vụ hạ tầng | F09–F10 | Có thể lạm dụng DNS, log, giám sát? | Resolver được duyệt; giới hạn DNS/egress; ACL/log transport và kiểm soát quyền SIEM |
| **TB-08** Cloud → on-premises | F11 | Workload cloud có được tin như máy nội bộ? | IPsec riêng, phân đoạn cloud/on-prem, xác thực workload, TLS, allow đúng API và service |

**Lưu ý:** một luồng có thể đi qua **nhiều** trust boundary. Chẳng hạn phiên quản trị F04–F06 đi từ Internet qua ZTNA tới bastion, rồi vượt sang Z2. MFA tại biên không thay thế quyền SSH trên máy đích; phiên tới máy đích cần được cấp và ghi log theo vai trò. Tương tự, IPsec chỉ bảo vệ đường truyền giữa hai gateway, không tự xác minh người gọi API.

### 5.1. Minh họa một đường đi vượt nhiều ranh giới

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Khách Internet (Z0)
    participant W as WAF/Reverse proxy (Z1)
    participant A as Backend API (Z2)
    participant D as PostgreSQL (Z3)
    C->>W: HTTPS 443 | qua NGFW / TB-01
    W->>W: Kiểm tra HTTP, áp rate limit / WAF policy
    W->>A: HTTPS 8443 | TB-02
    A->>A: Xác thực và kiểm tra quyền nghiệp vụ
    A->>D: TLS PostgreSQL 5432 | TB-03
    D-->>A: Dữ liệu đúng phạm vi quyền
    A-->>W: Phản hồi đã lọc dữ liệu
    W-->>C: HTTPS response
~~~

Tại mỗi chặng cần ghi nhận **ai chịu trách nhiệm kiểm soát**. Các bước xác thực nghiệp vụ và hạn chế dữ liệu trả về là biện pháp ở lớp ứng dụng; kiểm soát mạng chỉ hạn chế được đường đi IP và giao thức, không chứng minh truy vấn SQL nào là hợp lệ.

### 5.2. Boundary phải được đánh dấu ở mức quyền, không chỉ IP

Xem hai tình huống:

1. Hai workload cùng subnet Z2 nhưng khác service account. Workload thứ nhất có quyền cập nhật đơn hàng, workload thứ hai chỉ được đọc trạng thái. **Trust boundary theo danh tính dịch vụ vẫn tồn tại**, dù sơ đồ mạng không có router nằm giữa.
2. ZTNA gateway nhìn thấy nhiều người dùng đi ra cùng một IP NAT. Nếu rule quản trị chỉ cho phép “IP NAT → bastion”, mọi người có thể cùng sử dụng một đường mạng. **Bastion/PAM phải kiểm tra người dùng và vai trò** độc lập với giới hạn IP.

Vì vậy cần ghép **network topology** với **identity and access topology**. Có thể ghi chú service account, PKI/mTLS, RBAC và vai trò PAM ngay bên cạnh mũi tên quan trọng.

## 6. Bước thực hành 3: lập ma trận luồng

Mỗi dòng phải có ID, nguồn, đích, hướng, cổng, tính chất dữ liệu, cách xác thực, điểm cưỡng chế và quyết định. Ma trận này sẽ được dùng làm đầu vào cho policy firewall/security group và các bài kiểm thử.

### 6.1. Luồng cần cho phép

| ID | Nguồn → đích | Giao thức/cổng | Điều kiện và điểm kiểm soát | Mục đích |
| --- | --- | --- | --- | --- |
| **F01** | Internet → WAF tại DMZ | TCP/443, HTTPS | NGFW/NAT chỉ công bố HTTPS; WAF lọc request | Web công khai |
| **F02** | WAF 10.60.10.10 → API 10.60.20.10 | TCP/8443, HTTPS | Phân đoạn chỉ cho WAF; TLS re-encryption, auth phù hợp | Chuyển tiếp API |
| **F03** | API 10.60.20.10 → DB 10.60.30.10 | TCP/5432, PostgreSQL có TLS | Firewall chỉ cho source cụ thể; DB xác thực bằng danh tính service giới hạn quyền | Truy vấn nghiệp vụ |
| **F04** | Người quản trị từ xa → ZTNA | TCP/443, TLS | MFA, posture thiết bị, chính sách theo danh tính | Vào cổng truy cập |
| **F05** | ZTNA → bastion 10.60.40.10 | TCP/22, SSH (mô hình lab) | ZTNA policy + bastion xác thực, quyền thao tác phù hợp | Vào điểm quản trị |
| **F06** | Bastion → API 10.60.20.10 | TCP/22, SSH | Chỉ admin được duyệt, key/credential vòng đời ngắn; audit phiên | Bảo trì backend |
| **F07** | Máy nhân viên Z5 → WAF | TCP/443, HTTPS | Chỉ giao diện web; app xác thực và phân quyền | Thao tác nghiệp vụ |
| **F08** | Guest Z6 → Internet | Theo chính sách egress đã duyệt | Firewall và mạng Wi-Fi khách; không có route/allow tới vùng nội bộ | Internet khách |
| **F09** | API → DNS resolver 10.60.70.53 | UDP/TCP 53 | Chỉ resolver nội bộ; giới hạn truy vấn, giám sát log DNS | Phân giải tên |
| **F10** | Thiết bị phát log → SIEM 10.60.70.20 | TCP/6514 Syslog over TLS trong ví dụ | Chứng thực nguồn log, giới hạn nguồn/đích, quản lý chứng chỉ | Tập trung sự kiện |
| **F11** | Job đối soát cloud → API nội bộ | TCP/8443 HTTPS qua tunnel IPsec | Gateway, firewall, xác thực service/mTLS, scope API tối thiểu | Đồng bộ dữ liệu được duyệt |

**Chú ý khi triển khai:** đường F10 đại diện log từ NGFW/WAF/ZTNA; các thiết bị khác có thể dùng agent, HTTPS hoặc giao thức thu thập khác. Không suy diễn mọi thiết bị đều hỗ trợ Syslog TLS/6514. Luồng F08 phải xác định rõ DNS, captive portal, proxy và các cổng cần thiết theo chính sách Internet của mạng khách; tránh gán “any/any” chỉ vì bài lab viết ngắn.

### 6.2. Luồng cần từ chối rõ ràng

| ID | Nguồn → đích | Tại sao phải chặn? |
| --- | --- | --- |
| **D01** | Guest Z6 → DB Z3 (mọi cổng) | Mạng khách không có quyền truy cập dữ liệu nội bộ |
| **D02** | Máy văn phòng Z5 → DB Z3 TCP/5432 | Người dùng thao tác qua ứng dụng, không truy cập trực tiếp DB |
| **D03** | Internet → API Z2 trực tiếp TCP/8443 | Chỉ WAF/reverse proxy được đi tới API |
| **D04** | Internet → bastion Z4 TCP/22 | Quản trị bắt buộc qua ZTNA/MFA |
| **D05** | API Z2 → mọi host/cổng trong Z3 | Chỉ cho phép DB đúng địa chỉ và giao thức |
| **D06** | Cloud job Z8 → mạng quản trị Z4 | Đối soát chỉ cần API, không cần quyền quản trị |
| **D07** | Guest Z6 → resolver nội bộ Z7 | Ngăn khách lạm dụng DNS/service nội bộ |
| **D08** | Máy không được quản lý → kết nối ZTNA/quản trị | Không đáp ứng điều kiện thiết bị và danh tính |

Quy tắc **default deny** nên áp dụng theo ranh giới và điểm cưỡng chế phù hợp, sau khi đã kiểm kê các phụ thuộc như DNS, NTP, backup, monitoring, HA và đường quản lý thiết bị. Việc tách VLAN nhưng vẫn có rule liên vùng **allow any any** sẽ làm mất phần lớn giá trị phân đoạn.

## 7. Bước thực hành 4: gắn rủi ro với boundary

Việc đánh dấu trust boundary có ý nghĩa khi mỗi boundary gắn với **một giả định bảo mật có thể bị phá vỡ** và cách kiểm tra giả định đó.

| Boundary | Kịch bản đe dọa giả định | Tác động có thể xảy ra | Kiểm soát ưu tiên |
| --- | --- | --- | --- |
| TB-01 | Internet gửi request độc hại hoặc credential stuffing | Chiếm tài khoản, phá dịch vụ | WAF, rate limit, xác thực, quan sát log |
| TB-02 | DMZ bị xâm nhập rồi quét toàn bộ subnet ứng dụng | Di chuyển ngang từ edge | Allow WAF → API đúng cổng, hardening, IDS/IPS |
| TB-03 | Backend bị chiếm và dùng tài khoản DB quá nhiều quyền | Lộ/sửa dữ liệu | Chỉ mở 5432 tới DB, RBAC DB, audit, bảo vệ secrets |
| TB-04 | Tài khoản nhà vận hành bị lộ hoặc phiên quản trị bị chiếm | Chiếm quyền hạ tầng | MFA chống phishing khi có thể, PAM, JIT, session logging |
| TB-05 | Máy trạm văn phòng nhiễm mã độc | Truy cập trái phép vào backend/DB | Endpoint security, chặn liên vùng, xác thực app |
| TB-06 | Thiết bị khách dò mạng nội bộ | Lộ dịch vụ nội bộ | Wi-Fi isolation, guest VLAN, deny nội bộ |
| TB-07 | DNS bị thao túng hoặc log không được gửi | Điều hướng sai, mất khả năng phát hiện | Resolver được duyệt, DNS logging, TLS cho log, SIEM health |
| TB-08 | Workload/cloud credential bị lộ | Dịch chuyển từ cloud vào on-prem | Phân đoạn 2 chiều, mTLS/service identity, cloud SG, cloud audit |

Có thể áp dụng khung tư duy **STRIDE** để rà soát thêm: giả mạo (Spoofing), sửa đổi (Tampering), chối bỏ (Repudiation), tiết lộ thông tin (Information disclosure), từ chối dịch vụ (Denial of service) và leo thang đặc quyền (Elevation of privilege). Không cần cố gắng gán đủ sáu loại cho mọi cạnh; chọn các rủi ro có cơ sở từ dữ liệu, kết nối và quyền thực tế.

### Bài tập đường đi tấn công

Giả sử một laptop nhân viên Z5 bị nhiễm mã độc. Hãy lần theo:

~~~text
Laptop Z5 bị xâm nhập
  -> [D02: DENY] DB Z3 trực tiếp
  -> [F07: ALLOW] WAF/giao diện web
  -> [TB-02] API chỉ xử lý request đã xác thực/phân quyền
  -> [TB-03] DB chỉ cho phép kết nối từ API và quyền SQL tối thiểu
~~~

Điểm mấu chốt: **D02 giảm khả năng truy cập DB trực tiếp**, nhưng malware vẫn có thể lạm dụng tài khoản web của người dùng qua F07. Vì thế phân đoạn không thay thế xác thực mạnh, kiểm soát phiên và phân quyền nghiệp vụ. Hãy ghi cả **rủi ro còn lại** vào sơ đồ, thay vì đánh dấu đường đi là “an toàn tuyệt đối”.

## 8. Bước thực hành 5: chuyển sơ đồ thành quy tắc kiểm soát

Để người triển khai không phải tự đoán, thêm bên cạnh mỗi boundary các trường: **chủ sở hữu**, **nguồn/đích**, **giao thức**, **đối tượng danh tính**, **log**, **thời hạn** và **đường dự phòng**.

Ví dụ mô tả chính sách ứng dụng → DB:

~~~yaml
# Ví dụ trung lập nhà cung cấp; không phải cấu hình firewall thực tế.
ruleId: LAB-TB03-APP-DB
boundary: TB-03
decision: allow
source:
  zone: Z2
  cidr: 10.60.20.10/32
  workloadIdentity: sales-api
destination:
  zone: Z3
  cidr: 10.60.30.10/32
service:
  protocol: tcp
  destinationPort: 5432
  transportEncryption: tls
databaseAuthorization: least-privilege-role
enforcement:
  network: inter-zone-firewall
  application: postgresql-authz
logging:
  networkFlow: true
  databaseAudit: true
owner: application-and-database-teams
purpose: "Backend truy van du lieu don hang"
reviewCycle: "Theo chinh sach to chuc"
~~~

Địa chỉ /32 ở đây phù hợp vì bài lab giả định máy API và DB có địa chỉ cố định. Nếu triển khai trên Kubernetes, auto-scaling group hay HA database có IP động, có thể dùng nhóm tài nguyên hoặc selector theo danh tính/workload được quản lý. Vẫn cần giám sát sự thay đổi thành viên của nhóm để tránh vô tình mở rộng quyền.

**Không sinh thêm rule cho mọi cặp zone** chỉ vì chúng được vẽ trong sơ đồ. Những luồng không có mục đích nghiệp vụ phải bị từ chối ở vị trí cưỡng chế thích hợp. Nếu có đường bypass (route khác, secondary NIC, peering, IPv6, firewall khác), topology phải thể hiện hoặc ghi rõ trong phần giả định/giới hạn.

### 8.1. Ba dạng kiểm soát phải đi cùng nhau

1. **Network:** routing/VRF/VLAN, NGFW, ACL, security group, NACL, NetworkPolicy, phân đoạn ở host; kiểm soát kết nối nào có thể tới tài nguyên.
2. **Identity và application:** MFA, ZTNA/PAM, mTLS, IAM, service account, RBAC ở database/API; kiểm soát ai và thao tác nào được phép.
3. **Detection và operations:** IDS/IPS, DNS logs, firewall flow logs, WAF logs, SIEM, đối soát chính sách, quản lý thay đổi; phát hiện và điều tra hành vi vượt giả định.

Chẳng hạn VPN site-to-site mã hóa luồng F11 nhưng không thể một mình đảm bảo cloud job chỉ gọi đúng endpoint API; cần policy mạng và xác thực service ở hai đầu.

## 9. Bước thực hành 6: thiết kế kiểm thử xác minh

Một sơ đồ chỉ phản ánh **ý định thiết kế** cho tới khi được đối chiếu với cấu hình và lưu lượng thực. Tạo bảng kiểm thử để trả lời: luồng hợp lệ có chạy không, luồng sai có bị chặn không và người vận hành có xem được bằng chứng không?

| Test ID | Điều kiện kiểm thử | Kết quả kỳ vọng | Nguồn bằng chứng |
| --- | --- | --- | --- |
| **T01** | Client Internet gọi HTTPS tới WAF | F01 được phép; chỉ cổng dịch vụ đã công bố | WAF access log, NGFW log |
| **T02** | Client Internet gọi API Z2 trực tiếp | D03 bị chặn | Route/policy/firewall deny log |
| **T03** | WAF gọi API TCP/8443 | F02 hoạt động, xác thực/TLS hợp lệ | Reverse proxy log, API log |
| **T04** | API gọi DB TCP/5432 bằng service identity đúng | F03 thành công, chỉ quyền SQL được duyệt | DB audit, firewall flow |
| **T05** | Host khác trong Z2 cố tới DB | Bị từ chối nếu chưa được duyệt | Log tại điểm phân đoạn |
| **T06** | Guest Wi-Fi kết nối tới DB hoặc DNS nội bộ | D01/D07 bị chặn | Gateway/firewall deny log |
| **T07** | Guest Wi-Fi truy cập Internet theo egress policy | F08 hoạt động theo phạm vi cho phép | Guest gateway log |
| **T08** | Người quản trị từ xa không có MFA/posture hợp lệ | F04/F05 không được cấp | ZTNA identity log |
| **T09** | Admin đã được duyệt truy cập bastion, rồi SSH tới API | F04–F06 theo quyền và thời hạn; có audit phiên | ZTNA/PAM/bastion log |
| **T10** | Cloud job gọi API được duyệt | F11 hoạt động qua tunnel và xác thực service | Gateway, app, cloud flow logs |
| **T11** | Cloud job cố truy cập bastion Z4 | D06 bị chặn | Cloud SG/NGFW deny log |
| **T12** | API phân giải DNS qua resolver được duyệt | F09 thành công; resolver và truy vấn có log | Resolver query log |
| **T13** | Ngắt pipeline log/đổi rule giữa các zone | SIEM phát hiện nguồn log mất kết nối; có thể phát hiện drift | Monitoring và kiểm tra policy |
| **T14** | Thiết lập truy cập IPv6 hoặc route thay thế, nếu môi trường có | Không tạo đường bypass ngoài chính sách | Effective policy và log |

Đối với kiểm thử chặn, chỉ thấy ứng dụng “timeout” **chưa chứng minh firewall đã chặn**: timeout còn có thể do routing, DNS hoặc đích không lắng nghe. Cần kết hợp log tại điểm cưỡng chế, bộ phân tích policy và kiểm thử đầu cuối từ đúng source zone.

Khi kiểm thử rule trên firewall stateful, nhớ phân biệt **kết nối mới** với **phiên đã được thiết lập**. Việc xóa allow rule có thể không tự cắt các session đang mở, tùy thiết bị. Ghi rõ yêu cầu về xử lý session khi thay đổi policy, đặc biệt với kết nối quản trị và ngoại lệ có thời hạn.

### 9.1. Điền bảng kết quả

Bạn có thể dùng mẫu:

| Test ID | Kỳ vọng | Thực tế | PASS/FAIL | Bằng chứng và người kiểm tra |
| --- | --- | --- | --- | --- |
| T01 | ALLOW HTTPS tới WAF | Chưa chạy | NOT RUN | Điền sau khi thực hiện |
| T02 | DENY Internet tới API trực tiếp | Chưa chạy | NOT RUN | Điền sau khi thực hiện |
| T06 | DENY Guest tới DB | Chưa chạy | NOT RUN | Điền sau khi thực hiện |
| T09 | Admin qua ZTNA + bastion có audit | Chưa chạy | NOT RUN | Điền sau khi thực hiện |

Đây là **mẫu kết quả dự kiến**, không phải báo cáo rằng các lệnh kiểm thử đã được chạy. Không đánh dấu PASS trước khi có dữ liệu đo.

## 10. Mở rộng lab: DNS, Wi-Fi, VPN, IDS/IPS và cloud

### 10.1. Trust boundary cho DNS

DNS không chỉ là giao thức hỗ trợ; resolver nội bộ có thể trở thành điểm quan sát và điểm điều khiển truy vấn. Cần xác định:

- Client nội bộ nào được hỏi DNS resolver tại Z7, bằng UDP/TCP 53 hoặc giao thức DNS bảo mật nào đã được duyệt.
- Resolver nào được truy vấn upstream; có cần DNS-over-TLS (DoT), DNSSEC validation, lọc domain độc hại hoặc policy chống truy vấn bất thường không.
- Đường DNS công khai có bỏ qua resolver tổ chức hay không; ở môi trường có chính sách chặt, quản lý egress DNS và DoH cần dựa trên năng lực nền tảng.
- DNS query log có bảo vệ dữ liệu cá nhân, phân quyền truy cập và thời gian lưu phù hợp không.

Nếu cùng một resolver phục vụ nhiều zone, phải xác định policy theo client/zone và tránh biến nó thành đường truy cập dịch vụ nội bộ ngoài ý muốn.

### 10.2. Trust boundary cho Wi-Fi

SSID không phải bằng chứng phân đoạn nếu các SSID cùng được bridge vào một VLAN hoặc firewall vẫn cho phép guest tới mạng nội bộ. Khi vẽ:

- Thể hiện SSID nhân viên và khách, VLAN/VRF, gateway, chính sách inter-zone.
- Ghi cơ chế xác thực Wi-Fi phù hợp: 802.1X/WPA2-Enterprise hoặc WPA3-Enterprise cho mạng được quản trị, guest onboarding khi cần.
- Chỉ rõ guest isolation và policy cho DNS, captive portal, Internet egress; kiểm thử D01/D07 từ thiết bị guest thật.
- Nếu có thiết bị IoT hoặc BYOD, cân nhắc tách chúng khỏi mạng nhân viên và quản trị bằng zone/policy riêng.

### 10.3. Trust boundary cho VPN và ZTNA

Một đường tunnel được xác thực và mã hóa mới chỉ là **kênh vận chuyển**. Vẽ rõ sau khi VPN/ZTNA kết thúc, client có thể tới những subnet và ứng dụng nào. Xem xét các trường hợp split tunnel, posture, thiết bị lạ, token/phiên còn hiệu lực và quyền bị thu hồi. Với quản trị đặc quyền, đi qua bastion/PAM giúp tập trung audit và thu hẹp máy đích.

### 10.4. Trust boundary cho IDS/IPS

Phân biệt **IDS** giám sát/phát cảnh báo với **IPS** có thể chặn inline. Trên sơ đồ, đặt sensor tại các tuyến cần nhìn thấy: Internet↔DMZ, DMZ↔ứng dụng, ứng dụng↔dữ liệu, cloud↔on-prem nếu phù hợp. Nếu lưu lượng được mã hóa, sensor chỉ nhìn thấy metadata hoặc phần nội dung được giải mã tại điểm thích hợp; không giả định IDS có thể đọc toàn bộ HTTPS/mTLS.

### 10.5. Trust boundary cho cloud

Cloud có thêm các ranh giới **account/project/subscription, VPC/VNet, subnet, security group, IAM role, managed service**. Không thể kết luận peering hoặc IPsec làm hai mạng trở thành cùng mức tin cậy. Với F11, xác định cloud job identity, địa chỉ/nhóm nguồn, IPsec endpoints, cách định tuyến, TLS/mTLS tại API và logging ở cả hai phía.

## 11. Bài tập phát hiện lỗi trên sơ đồ

Giả sử người thiết kế ban đầu bổ sung các policy sau vào lab:

~~~text
R01: ALLOW source=10.60.0.0/16 destination=10.60.30.0/24 port=ANY protocol=ANY
R02: ALLOW source=0.0.0.0/0 destination=10.60.40.10/32 port=22 protocol=TCP
R03: ALLOW source=10.60.60.0/24 destination=10.60.70.0/24 port=ANY protocol=ANY
R04: ALLOW source=10.80.0.0/16 destination=10.60.0.0/16 port=ANY protocol=ANY
~~~

**Nhiệm vụ:** nối từng rule với các trust boundary liên quan, giải thích vì sao phạm vi không phù hợp với luồng F01–F11, và đề xuất cách thay thế.

**Đáp án tham khảo:**

| Rule | Sai lệch so với mục tiêu | Hướng sửa |
| --- | --- | --- |
| R01 | Cho gần như toàn bộ mạng nội bộ vào vùng DB, phá TB-03 | Chỉ cho API 10.60.20.10/32 → DB 10.60.30.10/32 TCP/5432; thêm luồng khác nếu được phê duyệt riêng |
| R02 | Mở SSH bastion từ Internet, bỏ qua ZTNA/PAM, rủi ro tại TB-01/TB-04 | Chỉ cho điểm ZTNA đã kiểm soát vào bastion, kiểm tra MFA và danh tính |
| R03 | Guest có thể tiếp cận hạ tầng DNS/SIEM, vi phạm TB-06/TB-07 | Chặn guest tới Z7; cung cấp DNS guest qua đường riêng/được phê duyệt |
| R04 | Workload cloud có đường đi quá rộng tới toàn bộ on-prem, vi phạm TB-08 | Chỉ cho cloud job đã xác thực → API 10.60.20.10/32 TCP/8443; thu hẹp cloud SG và policy on-prem |

Lưu ý: các rule được viết theo dạng giản lược để học cách đọc topology. Một rule thực tế còn có thứ tự, vùng vào/ra, NAT, loại firewall, đối tượng địa chỉ và tình trạng phiên. Khi phân tích, phải kiểm tra **effective policy** để tránh kết luận sai vì một allow/deny khác đang áp dụng.

## 12. Quy trình hoàn thiện và bàn giao sơ đồ

### 12.1. Các bước thực hiện

1. **Liệt kê tài sản:** xác định zone, IP/nhóm địa chỉ, vai trò, dữ liệu lưu trữ, người sở hữu.
2. **Xác định phạm vi và trust assumptions:** đâu là bên ngoài, nơi nào có đặc quyền, dữ liệu nhạy cảm nằm ở đâu, hệ thống nào quản trị bởi bên thứ ba.
3. **Vẽ khối và đường kết nối:** thể hiện nơi đặt edge, proxy, API, DB, admin, user, guest, cloud, DNS, SIEM.
4. **Gắn nhãn các boundary:** đánh mã TB-xx tại mọi đường vượt miền tin cậy; chỉ ra enforcement point và người quản lý chính sách.
5. **Lập flow matrix:** mỗi Fxx chỉ một luồng có mục đích, đúng giao thức/cổng/hướng; lưu ý NAT và IPv6.
6. **Liệt kê luồng deny:** kiểm tra đường guest, user, Internet và cloud tới tài nguyên nhạy cảm; đừng chỉ vẽ các đường được phép.
7. **Threat modeling:** chọn tối thiểu ba đường xâm nhập giả định, đánh giá tác động, kiểm soát và rủi ro còn lại.
8. **Đối chiếu cấu hình thực tế:** policy firewall, routing, security group, IAM, cấu hình Wi-Fi, DNS và tunnel; ghi rõ phần chưa xác minh.
9. **Kiểm thử có kiểm soát:** chạy bộ test T01–T14 phù hợp hạ tầng; lưu log, trạng thái và kết quả.
10. **Rà soát và cập nhật:** chủ hệ thống và nhóm an ninh xác nhận sơ đồ; bổ sung ngày phiên bản, lịch rà soát, thay đổi định tuyến/tài sản.

### 12.2. Bộ tài liệu cần bàn giao

| Tài liệu | Nội dung tối thiểu |
| --- | --- |
| **Topology overview** | Các zone, tên thành phần, kết nối logic, chú giải và phiên bản |
| **Trust boundary register** | TB-ID, nguồn/đích, chủ thể, điều kiện tin cậy, control, owner |
| **Flow matrix** | F-ID, hướng, IP/selector, giao thức/cổng, mục đích, allow/deny |
| **Threat notes** | Đường xâm nhập, giả định, tác động, giảm thiểu, rủi ro còn lại |
| **Validation sheet** | Test ID, điều kiện, kỳ vọng, thực tế, kết quả, log/screenshot liên quan |
| **Change history** | Ai sửa, ngày sửa, lý do, ticket và phần chưa chắc chắn |

Có thể lưu bản vẽ ở dạng **Mermaid, SVG hoặc tệp diagrams.net**, miễn có thể đọc lại và sửa được. Bản ảnh hoặc PDF xuất ra phục vụ phê duyệt nên kèm nguồn bản vẽ có khả năng biên tập.

### 12.3. Tiêu chí đánh giá gợi ý (100 điểm)

| Hạng mục | Điểm | Cách đánh giá |
| --- | ---: | --- |
| Topology và tài sản | 20 | Đúng zone, vai trò, kết nối, dữ liệu và chú giải |
| Trust boundary và enforcement | 25 | Có các TB trọng yếu, ràng buộc quyền và nơi thi hành rõ |
| Flow matrix | 20 | Đầy đủ hướng, protocol/port, mục đích, identity, allow/deny |
| Threat modeling | 15 | Nêu được đường đi, tác động, kiểm soát và rủi ro còn lại |
| Kiểm thử và bằng chứng | 15 | Có cả test allow/deny, kiểm tra effective policy, log đối chiếu |
| Khả năng bảo trì | 5 | Phiên bản, owner, phạm vi/giả định, quy trình cập nhật |

Điểm số là rubric dành cho thực hành, không phải chuẩn đánh giá tuân thủ của một tổ chức cụ thể.

## 13. Những lỗi hay gặp khi vẽ trust boundary

**Lỗi 1 — Chỉ vẽ VLAN rồi coi là đã phân đoạn an toàn.** Nếu router hoặc firewall đang có allow any-any, mọi vùng vẫn có thể truy cập nhau. Cần gắn policy thực tế vào các cạnh vượt boundary.

**Lỗi 2 — Vẽ mỗi mũi tên “HTTPS” mà không nêu đúng hướng và nguồn.** Hệ thống có thể có reverse proxy, NAT và nhiều địa chỉ. Cần chỉ rõ bên khởi tạo, điểm nhận, cổng đích, liệu có TLS termination/re-encryption và yêu cầu xác thực.

**Lỗi 3 — Cho rằng VPN/đường truyền private đồng nghĩa an toàn.** Tunnel giúp bảo vệ hoặc kết nối lưu lượng; danh tính service, policy mạng và quyền API vẫn phải được kiểm soát.

**Lỗi 4 — Bỏ quên đường quản trị, DNS, log và backup.** Những luồng hỗ trợ thường là đường đi có đặc quyền cao hoặc đường tác động toàn hệ thống. Vẽ chúng, nhưng phân biệt với luồng nghiệp vụ chính.

**Lỗi 5 — Không thể hiện vùng người dùng/guest/cloud.** Khi thiếu các vùng này, người xem dễ bỏ sót các điểm vào và luồng đi ngang.

**Lỗi 6 — Không xác minh chiều IPv6, NAT và route thay thế.** Một sơ đồ IPv4 đúng vẫn có thể bị bypass qua IPv6 hoặc đường peering. Ghi các đường tồn tại và policy đi kèm.

**Lỗi 7 — Dùng đường nét/màu mơ hồ.** Cần chú giải phân biệt luồng hợp lệ, đề xuất, bị từ chối và chưa xác minh; tránh lẫn lộn “mong muốn” với “đang thực thi”.

**Lỗi 8 — Tin bản vẽ hơn trạng thái thực tế.** Infrastructure drift, IP động, nhóm thành viên thay đổi hoặc thay đổi định tuyến khiến policy hiệu lực khác thiết kế. Sơ đồ cần được kiểm chứng và cập nhật theo vòng đời hệ thống.

## 14. Tự đánh giá cuối lab

Hãy trả lời bằng sơ đồ và bảng đã tạo:

1. **Có bao nhiêu trust boundary giữa khách Internet và dữ liệu đơn hàng?** Ít nhất TB-01, TB-02 và TB-03 trong mô hình này; lớp xác thực ứng dụng/database còn là điểm kiểm soát bổ sung.
2. **Nếu WAF bị chiếm, điều gì ngăn nó truy cập thẳng DB?** TB-02 chỉ cho WAF tới API đúng cổng; TB-03 chỉ cho API được duyệt tới DB, kết hợp DB auth và quyền SQL tối thiểu.
3. **Vì sao F11 đi qua IPsec vẫn cần mTLS hoặc xác thực API?** Tunnel bảo vệ/kết nối hai mạng; nó không chứng minh mọi workload từ cloud đều được quyền gọi API.
4. **Guest Wi-Fi có thể dùng chung một switch vật lý với mạng văn phòng không?** Có, nếu phân đoạn L2/L3, firewall, uplink và các chính sách liên quan thực thi đúng. Dùng chung thiết bị vật lý không có nghĩa cùng mức tin cậy.
5. **Nếu test “guest → DB” thất bại với timeout, có thể đánh dấu PASS chưa?** Chưa. Cần kiểm tra deny log/policy và loại trừ lỗi route hoặc dịch vụ chưa lắng nghe.
6. **Mũi tên đi qua hai zone có bảo đảm lưu lượng đi qua firewall trên hình vẽ không?** Không. Phải xem routing/topology vật lý và điểm cưỡng chế hiệu lực; đường vẽ chỉ mô tả ý định logic.
7. **Một workload mới có IP khác IP cũ trong cụm autoscale thì phải làm gì?** Cập nhật tập đối tượng được quản trị/selector hoặc cơ chế định danh, đánh giá tác động và đối soát phạm vi quyền.

### Checklist nộp bài

- [ ] Có sơ đồ logic với ít nhất các zone Internet, DMZ, app, DB, admin, user, guest và dịch vụ hỗ trợ.
- [ ] Có chú giải, mã Fxx và TB-xx đủ để tra chéo giữa sơ đồ với bảng.
- [ ] Biết rõ dữ liệu nhạy cảm nằm đâu và người dùng nào thực sự cần truy cập.
- [ ] Mỗi trust boundary có điểm cưỡng chế và yêu cầu xác thực, mã hóa, log phù hợp.
- [ ] Có ma trận allow/deny, bao gồm đường mạng guest, quản trị và cloud.
- [ ] Có kịch bản xâm nhập giả định và đánh giá rủi ro còn lại.
- [ ] Có kế hoạch kiểm thử, kết quả thực tế và bằng chứng, hoặc ghi rõ các test chưa chạy.
- [ ] Có phạm vi, giả định, người sở hữu, ngày phiên bản và cách cập nhật khi hệ thống thay đổi.

**Kết quả cần đạt:** một người chưa tham gia thiết kế vẫn có thể nhìn topology và biết **tài sản ở đâu, dữ liệu chảy qua đâu, ranh giới tin cậy nằm ở đâu, ai được vượt ranh giới bằng cơ chế nào và kiểm thử ra sao**. Khi đủ những thông tin đó, sơ đồ mới trở thành công cụ thực tế cho thiết kế, vận hành và giám sát an ninh mạng.
