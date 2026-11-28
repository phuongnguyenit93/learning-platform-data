# Split tunnel và full tunnel trong VPN truy cập từ xa

Một nhân viên làm việc tại nhà cần truy cập ứng dụng nội bộ `intranet.corp.example.test`, tham gia cuộc họp trực tuyến và mở dịch vụ SaaS công khai. Khi bật VPN, lưu lượng nào cần đi qua mạng doanh nghiệp, lưu lượng nào được ra Internet tại nhà? Nếu chỉ nói “mọi traffic phải qua VPN thì mới an toàn”, doanh nghiệp có thể làm nghẽn cổng VPN và tăng độ trễ cuộc họp; nếu cho mọi traffic ra ngoài để tăng hiệu năng, các chính sách DNS, proxy, giám sát và bảo vệ thiết bị đầu cuối có thể không còn bao phủ như dự kiến.

**Split tunnel** và **full tunnel** là hai cách thiết kế **định tuyến/điều hướng lưu lượng khi client kết nối VPN**, chứ không phải hai thuật toán mã hóa. Việc chọn mô hình cần dựa vào tài sản, ứng dụng, mức tin cậy thiết bị, chính sách truy cập, các đường mạng và khả năng vận hành. Bài thuộc chương **VPN và truy cập từ xa** của module **SECURITY_NETWORK_SECURITY**, liên kết với phân đoạn, firewall, xác thực kết nối, DNS, IDS/IPS, bảo mật không dây, hạ tầng cloud và threat modeling.

**Nguyên tắc:** VPN bảo vệ một đoạn kết nối và thiết lập đường truy cập theo chính sách. **Đã đi qua VPN không đồng nghĩa người dùng được phép sử dụng mọi tài nguyên**, và **full tunnel không tự động ngăn toàn bộ đường rò rỉ** nếu endpoint, DNS, IPv6 hoặc routing policy không được quản lý đúng.

## 1. Nền tảng: VPN làm thay đổi đường đi nào?

Trong truy cập từ xa, VPN client thường tạo một **interface/tunnel logic** giữa thiết bị và VPN gateway/concentrator. Dữ liệu được encapsulate, bảo vệ theo giao thức và chính sách VPN, rồi được chuyển tới điểm cuối tunnel. Sau điểm cuối, lưu lượng tiếp tục theo mạng và các biện pháp bảo vệ ở đích.

| Thành phần | Nhiệm vụ | Điều phải xác minh |
|---|---|---|
| **Remote endpoint** | Thiết bị người dùng, VPN client, OS routing và DNS resolver | Thiết bị được quản lý, route nào có hiệu lực, DNS đi đâu? |
| **VPN tunnel** | Truyền lưu lượng theo chính sách, thường có xác thực và bảo vệ mật mã | Tính bảo mật, phiên, khóa, giao thức, MTU và trạng thái kết nối |
| **VPN gateway** | Kết thúc tunnel, kiểm soát phiên và đường ra | Người dùng/thiết bị nào được vào, đích nào được phép? |
| **Identity provider / MFA** | Xác thực và cung cấp tín hiệu danh tính | Session, điều kiện truy cập, thu hồi quyền và kiểm tra thiết bị |
| **Firewall / segmentation** | Kiểm soát các kết nối từ vùng remote-access tới mạng khác | Default deny, least privilege, IPv4/IPv6 và log |
| **DNS / proxy / SASE** | Phân giải tên, truy cập web và áp chính sách tùy kiến trúc | Split DNS, DNS leak, đường egress thực và exception |
| **Ứng dụng** | Xác thực, phân quyền tài nguyên/dữ liệu | Quyền theo vai trò/tenant, không tin duy nhất IP nguồn VPN |

Một VPN có thể dùng IPsec/IKEv2, TLS-based VPN, WireGuard hoặc giao thức khác. Khả năng thiết lập route, DNS, per-app tunnel, MFA, kiểm tra posture và khóa truy cập **phụ thuộc sản phẩm, hệ điều hành và cấu hình**, không phải đặc tính mặc định của mọi giao thức.

### 1.1. Các loại lưu lượng cần phân loại

Giả sử nhân viên có ba nhu cầu:

1. **Private:** kết nối tới server nội bộ `10.70.10.20`, chỉ reachable qua VPN hoặc kênh riêng được phê duyệt.
2. **Public SaaS:** tham gia họp hoặc mở dịch vụ công khai trên Internet.
3. **Local LAN:** in qua máy in tại nhà hoặc truy cập gateway/router trong mạng nhà.

Mô hình tunnel có thể đưa những nhóm này theo các đường **khác nhau**. Không suy kết quả chỉ từ tên “split” hay “full”: cần xem route, DNS, proxy, local-LAN exception, IPv6, app policy và VPN reconnect thực tế.

## 2. Full tunnel: đưa lưu lượng qua điểm egress do tổ chức quản lý

**Full tunnel** thường có nghĩa VPN client đưa **phần lớn hoặc toàn bộ lưu lượng IP được thiết kế nằm trong phạm vi chính sách** vào tunnel, bao gồm cả truy cập Internet công khai. Sau khi tới VPN gateway, traffic được phân loại, kiểm tra, NAT/proxy hoặc chuyển tiếp theo chính sách của tổ chức.

~~~mermaid
flowchart LR
    C["Laptop từ xa"] -->|"Traffic internal + Internet"| T["VPN tunnel"]
    T --> G["VPN gateway / egress"]
    G --> F["Firewall / proxy / DNS controls"]
    F --> I["Internal applications"]
    F --> W["Public Internet / SaaS"]
    L["Mạng Wi-Fi tại nhà"] -.-> C
~~~

**Sơ đồ là đường đi mục tiêu**, không chứng minh mọi kết nối thật đều đi tunnel. Client có thể giữ host route cần thiết tới VPN gateway, traffic local-link, ngoại lệ đường quản trị hoặc luồng IPv6 ngoài tunnel nếu cấu hình chưa đầy đủ.

### 2.1. Lợi ích thường gặp

- **Chính sách egress nhất quán:** lưu lượng web có thể đi qua proxy, DNS filter, firewall và kiểm soát được thiết kế chung.
- **Quan sát tập trung:** đội SOC có thể liên kết VPN session với firewall/IDS/IPS/proxy logs, khi chính sách logging và packet path hỗ trợ.
- **Giảm sự phụ thuộc vào bảo vệ của mạng truy cập không tin cậy** đối với những luồng nằm trong tunnel.
- **Kiểm soát truy cập theo vị trí egress:** một số dịch vụ cho phép kết nối từ IP/cổng được quản lý, dù vẫn nên xác thực danh tính ứng dụng.
- **Đơn giản hóa yêu cầu kiểm soát lưu lượng** trong tổ chức có chính sách buộc các luồng được quản lý qua một số điểm giám sát.

### 2.2. Đánh đổi và giới hạn

| Đánh đổi | Giải thích | Cách giảm tác động |
|---|---|---|
| **Hairpin/trombone routing** | SaaS gần người dùng nhưng traffic đi vòng qua data center/VPN gateway rồi mới ra Internet | Egress theo khu vực hoặc split tunnel có chính sách cho SaaS khi phù hợp |
| **Tải gateway/đường Internet** | Cả video, download, OS update có thể dùng năng lực VPN | Capacity planning, HA, QoS và kiến trúc egress phân tán |
| **Độ trễ và jitter** | Video/voice nhạy cảm đường vòng và packet loss | Đo RTT/jitter, chọn topology và exception có kiểm soát |
| **Điểm lỗi tập trung** | Sự cố VPN/gateway/proxy có thể ảnh hưởng cả Internet | Dự phòng, failover, hành vi khi mất tunnel rõ ràng |
| **Chi phí và dữ liệu giám sát** | Băng thông, log, TLS inspection và retention tăng | Chọn telemetry cần thiết, privacy và sizing |
| **Ứng dụng địa phương** | Máy in tại nhà hoặc thiết bị local có thể không reachable | Local-LAN exception có đánh giá rủi ro hoặc luồng riêng |

Full tunnel **không đồng nghĩa TLS của ứng dụng được giải mã**. Nếu tổ chức không triển khai một điểm giải mã được phép, firewall/proxy có thể chỉ thấy metadata hoặc một phần traffic. Dữ liệu sau VPN gateway đi tiếp tới đích theo cơ chế bảo vệ riêng; **VPN encryption không tự kéo dài end-to-end tới backend**.

## 3. Split tunnel: chỉ chọn một phần lưu lượng đi VPN

**Split tunnel** cho phép **một tập luồng nhất định** (theo prefix, ứng dụng, domain/policy hoặc tổ hợp) đi qua VPN; phần khác sử dụng đường local/Internet trực tiếp, tùy khả năng của client và sản phẩm.

~~~mermaid
flowchart LR
    C["Laptop từ xa"] --> D{"Route / app policy"}
    D -->|"Tài nguyên private được cấp"| T["VPN tunnel"]
    T --> G["VPN gateway + firewall"]
    G --> I["Internal apps"]
    D -->|"Internet công khai theo policy"| H["Router / ISP tại nhà"]
    H --> W["SaaS / Public Internet"]
    D -.->|"Local-link khi được phép"| L["Thiết bị LAN tại nhà"]
~~~

Split tunnel không nhất thiết thiếu kiểm soát: luồng Internet trực tiếp có thể được bảo vệ bằng **endpoint firewall, EDR, DNS/web security agent, browser policy, device posture và xác thực ứng dụng**. Ngược lại, nếu tổ chức chỉ áp security control tại data center, đưa traffic ra ngoài tunnel có thể làm mất một phần khả năng quan sát.

### 3.1. Các kiểu split tunnel

| Kiểu | Tiêu chí đưa qua VPN | Ưu điểm | Điểm khó |
|---|---|---|---|
| **Route-based include** | Chỉ các IP prefix được phê duyệt đi tunnel | Dễ hình dung, hợp private network có prefix ổn định | IP/cloud/tenant thay đổi, prefix chồng lấn, DNS có thể lệch |
| **Route-based exclude** | Mặc định qua tunnel, loại trừ các prefix được chỉ định | Giữ phần lớn traffic trong VPN, giảm tải cho nhóm cụ thể | Không dễ định nghĩa SaaS bằng IP bền vững; cần quản lý ngoại lệ |
| **Application-based** | Chỉ traffic từ một số ứng dụng/process/bundle được quản lý đi tunnel | Phù hợp ứng dụng đặc thù và môi trường MDM hỗ trợ | Process identity, helper processes, OS/sản phẩm hỗ trợ khác nhau |
| **Domain/FQDN-based** | Client/policy phân loại tên miền rồi xử lý đường đến IP liên quan | Thuận tiện với SaaS/private names có IP thay đổi | DNS cache, CNAME/CDN, IP dùng chung, DoH, SNI/ECH và thời gian cập nhật |
| **Policy/identity-based** | Quyết định theo người dùng, thiết bị, zone và ứng dụng | Tùy biến theo rủi ro | Cần nhận diện đáng tin và enforcement nhất quán |

**Không có một chuẩn split tunnel duy nhất** bắt mọi VPN làm giống nhau. Một số client kết hợp DNS policy với route; một số hỗ trợ application-specific tunnel hoặc dynamic exclusion; một số chỉ đưa route qua giao diện VPN.

### 3.2. Ví dụ route-based split tunnel

Giả sử laptop có kết nối Internet từ nhà và được cấp IP trong VPN pool. Doanh nghiệp muốn tất cả `10.70.0.0/16` đi tunnel, còn các đích công khai đi trực tiếp:

~~~text
Endpoint routes (minh họa, không phải bảng route thật):
Destination           Next hop / interface      Ý nghĩa
10.70.0.0/16          VPN virtual interface     Mạng nội bộ qua VPN
192.168.1.0/24        Home Wi-Fi interface      LAN tại nhà
0.0.0.0/0             Home router / ISP         Internet mặc định

Packet to 10.70.10.20      -> VPN virtual interface
Packet to 198.51.100.80   -> Home router
~~~

`198.51.100.0/24` là dải IP dành cho **tài liệu minh họa**, không đại diện một SaaS thật. `10.70.0.0/16` và `192.168.1.0/24` là địa chỉ private giả định; phải kiểm tra xung đột với môi trường thực trước khi thiết kế.

Trong lựa chọn route IP thông thường, **prefix cụ thể hơn** thường ưu tiên prefix rộng hơn; các route cùng độ dài cần xét route metric và các quy tắc hệ điều hành. Nhưng **policy-based routing, VPN filters, per-app tunnels và nhiều routing tables** có thể thay đổi kết quả. Đừng nhìn riêng `0.0.0.0/0` rồi kết luận traffic đi đâu.

### 3.3. Split tunnel theo route khác split DNS

**Split DNS** quyết định **resolver nào xử lý câu hỏi DNS** theo tên miền/suffix/chính sách. **Split tunnel** quyết định **đường IP của kết nối**. Hai cơ chế thường phối hợp nhưng không đồng nhất:

~~~text
intranet.corp.example.test
  -> Internal DNS qua VPN
  -> A: 10.70.10.20
  -> Route 10.70.0.0/16 qua VPN
  -> Firewall cho phép đúng application port

public.example.test
  -> Public resolver theo chính sách
  -> Public IP
  -> Route mặc định qua ISP (nếu split include như ví dụ)
~~~

Một client có thể nhận đúng IP private nhưng không có route VPN tới IP đó; hoặc có route VPN nhưng hỏi nhầm public DNS và nhận public answer. Vì vậy luôn kiểm tra **DNS resolution rồi routing rồi kết nối/authorization**, không suy tất cả từ ping.

## 4. Bảng so sánh split tunnel và full tunnel

| Tiêu chí | Full tunnel (mô hình điển hình) | Split tunnel (mô hình điển hình) |
|---|---|---|
| Lưu lượng tới tài nguyên private được phép | Qua VPN | Qua VPN khi route/app policy khớp |
| Lưu lượng Internet công khai | Thường qua VPN gateway/egress tổ chức | Thường trực tiếp theo chính sách |
| DNS | Có thể dùng resolver/chính sách tập trung | Có thể dùng split DNS; dễ sai khi nhiều resolver |
| Proxy/web filter ở data center | Có thể bao phủ phần traffic đã đi qua | Chỉ bao phủ luồng vào data center, trừ khi có agent/edge khác |
| Trải nghiệm SaaS/video | Có thể gặp hairpin và jitter | Có thể giảm đường vòng/độ trễ |
| Dung lượng VPN gateway | Phải tính cả lưu lượng Internet của user | Thường nhỏ hơn nếu phần lớn Internet không qua VPN |
| Rủi ro từ endpoint bị nhiễm mã độc | **Vẫn tồn tại**; malware có thể dùng tunnel trong phạm vi quyền được cấp | **Vẫn tồn tại**, thêm đường trực tiếp ngoài gateway tổ chức |
| Phụ thuộc VPN outage | Có thể ảnh hưởng cả Internet nếu chính sách chặn direct | Private apps bị ảnh hưởng; public apps có thể tiếp tục nếu cho phép |
| Kiểm soát local LAN | Phải quy định rõ ngoại lệ và route on-link | Cần kiểm soát nguy cơ endpoint nối đồng thời home LAN + corporate |
| Dùng IPv4/IPv6 | Phải xử lý cả hai stack | Phải xử lý cả hai stack và split policy tương ứng |
| Phù hợp với mọi tổ chức? | Không | Không |

Điểm quyết định không phải “full an toàn, split nguy hiểm” theo kiểu tuyệt đối. **Full** thuận lợi cho kiểm soát egress tập trung nhưng vẫn phụ thuộc endpoint và đường bypass. **Split** có thể phù hợp khi có quản trị endpoint và secure web/DNS filtering độc lập, nhưng đòi hỏi mô hình trách nhiệm/giám sát rõ ràng.

## 5. Đường đi gói tin, route và policy thực sự có hiệu lực

### 5.1. Full tunnel thường sử dụng default route

Ở mức khái niệm:

~~~text
IPv4:
  Internal subnet: 10.70.0.0/16 -> VPN
  Internet default: 0.0.0.0/0 -> VPN
  Reachability to VPN server itself -> đường ISP phù hợp

IPv6, nếu được quản lý đầy đủ:
  Internet default: ::/0 -> VPN (hoặc chính sách chặn ngoại tuyến)
~~~

Một số client có thể triển khai full IPv4 bằng **cặp route cụ thể hơn** (chẳng hạn `0.0.0.0/1` và `128.0.0.0/1`) thay vì thay `0.0.0.0/0` theo cách dễ thấy trong bảng. Vì vậy cần kiểm tra **route lookup tới đích đại diện** và traffic thực tế, không chỉ tìm một dòng default route.

Ngoài ra, phải có đường tới địa chỉ public của **VPN gateway** để tunnel tiếp tục hoạt động. Không nên tự xóa host route, sửa metric hoặc đổi default gateway trên thiết bị đang kết nối production chỉ để thử.

### 5.2. Route conflict và mạng tại nhà

Giả sử private service doanh nghiệp dùng `192.168.1.20`, đúng lúc router nhà cũng cấp mạng `192.168.1.0/24`. Nếu VPN chỉ thêm route trùng prefix, OS có thể chọn sai giao diện theo metric, policy routing hoặc cách client kiểm soát route. Hệ quả là không tới được private service hoặc traffic đi nhầm LAN tại nhà.

Các hướng xử lý có thể gồm:

- Thiết kế **khối địa chỉ doanh nghiệp có quy hoạch**, tránh những dải phổ biến nếu thực tế khả thi.
- Thêm route host/per-app cụ thể có kiểm soát khi phù hợp, nhưng tránh tạo ngoại lệ khó duy trì.
- Dùng application proxy/ZTNA thay vì yêu cầu client route trực tiếp vào subnet chồng lấn.
- Khi buộc liên thông mạng trùng IP, đánh giá NAT hoặc kiến trúc translation một cách chính thức, có kiểm tra DNS và return path.

Không coi việc “đổi subnet router nhà người dùng” là giải pháp có thể áp cho mọi nhân viên và nhà thầu.

### 5.3. Return path và firewall state

VPN client đến ứng dụng nội bộ không chỉ cần **request route**; phản hồi cũng phải đi đúng đường. Gateway và firewall có thể cần NAT, route cho VPN address pool, policy stateful và kiểm tra anti-spoofing.

~~~mermaid
flowchart LR
    C["VPN client 10.250.20.15"] -->|"Encrypted tunnel"| G["VPN gateway"]
    G -->|"Source được route/NAT theo thiết kế"| F["Internal firewall"]
    F --> A["App 10.70.10.20"]
    A -->|"Response route"| F
    F --> G
    G -->|"Tunnel response"| C
~~~

Nếu route tới `10.250.20.0/24` không có hoặc NAT/stateful policy sai, client có thể nhận IP VPN và phân giải DNS đúng nhưng vẫn timeout khi kết nối ứng dụng. Trong nhiều kiến trúc VPN có NAT hoặc proxy nên backend **không nhìn thấy trực tiếp IP VPN client**; identity trong application/API và logs cần thiết để điều tra chính xác.

### 5.4. Always-on VPN và kill switch

Hai cơ chế cần phân biệt:

- **Always-on VPN:** client cố gắng tự kết nối và duy trì phiên theo chính sách.
- **Kill switch / block-outside-tunnel:** client hoặc OS chặn một số luồng khi tunnel không sẵn sàng để tránh vô tình đi ra đường không được phép.

**Always-on không mặc định có kill switch**, và kill switch có thể có exception (captive portal, khởi tạo VPN, mạng LAN, cứu hộ thiết bị) tùy sản phẩm. Cần kiểm tra trạng thái **trước khi VPN kết nối, lúc mất VPN, sau reconnect, lúc sleep/wake và khi đổi Wi-Fi**. Với split tunnel, một chính sách có thể cố ý cho Internet ngoài tunnel tiếp tục hoạt động, nhưng phải bảo đảm **traffic private không tự chuyển sang tuyến không được phê duyệt**.

## 6. DNS, DoH/DoT và rò rỉ thông tin tên miền

DNS là chỗ dễ làm cho cấu hình VPN nhìn có vẻ “đúng route” nhưng truy cập vẫn sai.

### 6.1. Các mô hình DNS thường gặp

| Mô hình | Hành vi dự kiến | Điểm phải kiểm tra |
|---|---|---|
| **Full tunnel + corporate DNS** | DNS của client tới resolver được tổ chức chỉ định qua VPN | Client/browser có dùng resolver riêng? DNS IPv6? |
| **Split tunnel + split DNS** | Tên private qua resolver nội bộ; tên public theo chính sách ngoài tunnel | Suffix matching, CNAME, cache, NRPT/OS behavior |
| **Split tunnel + secure DNS agent** | DNS/public browsing được bảo vệ bởi agent/cloud edge riêng | Agent có hoạt động khi VPN ngắt? Log & privacy ra sao? |
| **App-specific tunnel** | Ứng dụng private dùng DNS/connection theo chính sách của ứng dụng | Helper process, embedded resolver và app update |

**DNS leak** là cách gọi rộng cho truy vấn đi tới resolver hoặc qua đường không theo chính sách kỳ vọng, khiến tên miền nội bộ/nhạy cảm có thể bị tiết lộ hoặc client nhận câu trả lời khác view. Tuy nhiên một truy vấn DNS công khai đi ngoài VPN **không tự là lỗi** nếu chính sách split tunnel chủ động cho phép và bảo vệ riêng.

### 6.2. Những lỗi phổ biến

1. **Split DNS thiếu suffix:** tên nội bộ được hỏi từ public resolver, có thể nhận NXDOMAIN hoặc địa chỉ public.
2. **Browser DoH/DoT riêng:** ứng dụng bỏ qua DNS setting của OS, đặc biệt khi kết nối mạng từ xa; cần policy endpoint phù hợp.
3. **IPv6 DNS ngoài VPN:** dù IPv4 DNS đi tunnel, resolver IPv6 vẫn nhận truy vấn ngoài đường đã định.
4. **Cache cũ:** client chuyển từ Internet sang VPN nhưng giữ câu trả lời public cho cùng FQDN.
5. **CNAME chain:** tên private trỏ qua CNAME tới zone hoặc CDN có chính sách khác; resolver và route có thể không cùng ý định.
6. **DNS64/NAT64 hoặc captive portal:** tên và địa chỉ được biến đổi/điều hướng theo cấu hình mạng; phải phân biệt lỗi bảo mật với hành vi mạng hợp lệ.
7. **Không đồng bộ policy:** gateway cho route private mới nhưng DNS zone chưa được thêm hoặc ngược lại.

Với private DNS, cân nhắc **split-horizon DNS** theo VPN/identity/zone. Không dùng hostname “ẩn” làm bảo mật thay cho firewall, segmentation và AuthN/AuthZ. Nếu DNSSEC validation được triển khai, phải bảo đảm private DNS policy không tạo xung đột trust chain ngoài ý định.

### 6.3. Không nhầm DNS path và kết nối ứng dụng

Một lần `dig` trả `10.70.10.20` không chứng minh packet HTTPS tới IP đó đã đi tunnel. Cần kiểm tra:

- Resolver thực tế có trả lời đúng theo policy không?
- Route lookup cho IP kết quả có đi interface VPN không?
- Firewall/gateway có thấy session được cho phép không?
- TLS tới ứng dụng có xác minh đúng certificate hostname không?
- Backend có xác thực và phân quyền user/tenant/thiết bị độc lập với VPN IP không?

## 7. IPv6, nhiều interface và các đường bypass

### 7.1. IPv4 full tunnel không có nghĩa IPv6 full tunnel

Nếu VPN chỉ đưa IPv4 default qua tunnel nhưng OS còn IPv6 Internet route qua router nhà, một ứng dụng có thể dùng địa chỉ **AAAA** và đi trực tiếp ngoài tunnel. Đây có thể là **vi phạm policy** nếu tổ chức kỳ vọng full tunnel cho cả hai stack.

Với split tunnel cũng tương tự: chỉ route `10.70.0.0/16` không bảo vệ ứng dụng private có IPv6 prefix được cấp. Cần quy hoạch các IPv6 route/policy/ACL theo cùng ranh giới tin cậy, hoặc chặn những luồng không được phép một cách có chủ đích.

Ví dụ prefix IPv6 dành riêng cho tài liệu:

~~~text
Corporate IPv4: 10.70.0.0/16
Corporate IPv6: 2001:db8:70::/48  # Minh họa, không định tuyến Internet thật
Remote VPN IPv4 pool: 10.250.20.0/24

Split tunnel policy:
  route to 10.70.0.0/16 -> VPN
  route to 2001:db8:70::/48 -> VPN
  remaining traffic -> approved local/secure edge policy
~~~

`2001:db8::/32` là prefix dùng cho tài liệu. Trong thực tế phải dùng các prefix IPv6 được cấp hợp lệ hoặc ULA được quy hoạch, đồng thời kiểm soát **RA, route precedence và firewall IPv6** trên endpoint.

### 7.2. Multi-homing: Wi-Fi + Ethernet + cellular

Laptop có thể đồng thời có Wi-Fi, Ethernet, modem cellular, adapter ảo Docker/VM và VPN interface. Một số ứng dụng có thể sử dụng proxy hoặc socket binding riêng. Khi có route metric, policy-based routing hoặc network change, **đường đi thực** có thể khác với kết quả chỉ đọc một dòng trong bảng route.

Kiểm tra các trường hợp:

- Chuyển từ Wi-Fi công cộng sang hotspot/4G, VPN tự reconnect và giữ policy?
- Interface phụ có route ưu tiên cao hơn, DNS server khác hoặc IPv6 không?
- Máy ảo/container dùng NAT/bridge qua host có đi tunnel như kỳ vọng không?
- Local network exception có cho phép truy cập router nhà/thiết bị IoT không đáng tin?
- VPN disconnect trong khi ứng dụng giữ session có gây fallback trực tiếp không?

Không dùng một phép thử “IP công khai của trình duyệt” làm bằng chứng tất cả tiến trình đã đi đúng tunnel. Cần **ma trận ứng dụng, giao thức, IPv4/IPv6 và trạng thái kết nối**.

## 8. Bảo mật endpoint khi split tunnel và full tunnel

### 8.1. Vì sao split tunnel đòi hỏi đánh giá rủi ro cẩn thận?

Thiết bị được kết nối đồng thời tới Internet/local LAN và VPN doanh nghiệp có thể trở thành **điểm giao giữa hai miền tin cậy**. Nếu endpoint bị xâm nhập, malware có thể sử dụng chính danh tính/phiên VPN được cấp để tiếp cận hệ thống nội bộ. Tuy nhiên, chỉ có split tunnel **không tự biến endpoint thành router chuyển tiếp gói giữa hai mạng**; khả năng bridging/forwarding phụ thuộc cấu hình OS, quyền attacker và firewall.

Những rủi ro cần đánh giá:

- **Đường web ngoài gateway tổ chức:** thiếu kiểm soát web/DNS/proxy nếu không có endpoint/cloud security tương ứng.
- **Mạng nhà/khách không tin cậy:** rogue DNS, thiết bị LAN dễ tổn thương, captive portal, Wi-Fi giả, công cụ chia sẻ file.
- **Phân quyền VPN quá rộng:** khi client đã được xác thực, nó có thể thấy nhiều subnet nếu gateway chỉ dựa vào “connected”.
- **Endpoint yếu:** thiếu disk encryption, patching, EDR, hardening hoặc có browser extension nguy hiểm.
- **Lộ dữ liệu khi offline:** ứng dụng tải dữ liệu về máy trước đó, full tunnel không kiểm soát được dữ liệu đã nằm ở endpoint.

### 8.2. Full tunnel còn cần lớp bảo vệ nào?

Ngay cả full tunnel, thiết bị có thể bị lây nhiễm qua file, phần mềm hoặc nguồn đã được phép. Kẻ tấn công có thể sử dụng **một tunnel hợp lệ**, hoặc lợi dụng quyền quá rộng phía trong VPN. Nên có:

- MFA/conditional access và ràng buộc danh tính user/thiết bị khi hỗ trợ.
- EDR/host firewall, cập nhật OS/browser, disk encryption và quản lý ứng dụng.
- Least-privilege authorization trong VPN gateway, zone firewall và ứng dụng.
- Segmentation theo nhóm tài sản, tenant, dịch vụ, không mở “any internal subnet” cho mọi nhân viên.
- Audit và khả năng thu hồi token, VPN session, chứng chỉ hoặc credential khi phát hiện sự cố.
- DLP và chính sách dữ liệu nơi cần; không giả định “qua tunnel” nghĩa là dữ liệu không thể bị sao chép.

**Full tunnel không thay thế Zero Trust**, cũng không thay xác thực và phân quyền ứng dụng. VPN thuộc một lớp kết nối; quyền dữ liệu phải được đánh giá lại ở đích.

### 8.3. ZTNA/SASE không đồng nghĩa split tunnel

**ZTNA** thường thiết kế quyền truy cập tới **ứng dụng cụ thể dựa trên danh tính/thiết bị/ngữ cảnh**, thay vì mở định tuyến rộng tới mạng nội bộ. **SASE/SSE** có thể kết hợp bảo vệ web/DNS/CASB/ZTNA theo mô hình dịch vụ cloud. Chúng có thể phối hợp với split hoặc full tunnel, nhưng **tên kiến trúc không chỉ ra route thực tế**.

Khi dùng ZTNA/SASE, vẫn cần hỏi:

- Client gửi traffic tới app qua connector, proxy, tunnel hay Internet trực tiếp?
- Nền tảng có kiểm tra mọi luồng mong muốn, kể cả UDP/QUIC, DNS và IPv6 không?
- Quyền user/tenant được xác minh ở đâu, thời hạn session và khả năng revoke thế nào?
- Có đường bypass bằng IP public của origin hoặc subnet private khác không?

## 9. Chọn mô hình theo công việc và mức kiểm soát

| Tình huống | Hướng thiết kế có thể cân nhắc | Lý do |
|---|---|---|
| Nhân viên thiết bị được quản lý, dùng nhiều SaaS video | Split tunnel có chính sách hoặc egress an toàn theo khu vực | Giảm hairpin, giữ EDR/web/DNS control độc lập |
| Hệ thống yêu cầu web egress qua proxy tập trung | Full tunnel hoặc secure agent/edge bao phủ tương đương | Giảm khác biệt chính sách nhưng cần capacity và HA |
| Nhà thầu chỉ cần một ứng dụng | App-specific VPN/ZTNA hoặc split scope rất hẹp | Không cấp route rộng vào mạng nội bộ |
| Tài khoản quản trị hệ thống quan trọng | Kênh đặc quyền riêng, MFA mạnh, bastion/ZTNA và device posture | Hạn chế quyền, giám sát thao tác; tunnel mode không phải biện pháp duy nhất |
| Client BYOD không quản trị đầy đủ | Ưu tiên quyền tới ứng dụng hẹp qua proxy/ZTNA; không mặc nhiên cấp full LAN VPN | Giảm rủi ro từ endpoint không biết trạng thái |
| Workload có IP private cố định và không có SaaS dependency | Split include theo prefix private hoặc full tùy policy | Dễ quản lý đường route; vẫn phải kiểm tra DNS và ACL |
| Dịch vụ cần truy cập tài nguyên local tại nhà | Chọn local exception có đánh giá rủi ro | Tránh phá chức năng printer/Internet mà không mở quá quyền |

Không quyết định “toàn công ty dùng split” hoặc “toàn công ty dùng full” chỉ vì sở thích cá nhân. Cần phân loại **vai trò, loại thiết bị, dữ liệu, địa điểm, ứng dụng và quy định tuân thủ**. Một tổ chức có thể dùng nhiều profile VPN với chính sách khác nhau, nhưng phải tránh profile chồng lấn hoặc không có owner.

## 10. Capacity planning và trải nghiệm người dùng

### 10.1. Tại sao full tunnel có thể tạo điểm nghẽn?

Giả sử có **2.000 nhân viên đồng thời**, trung bình mỗi người dùng khoảng **3 Mbit/s** traffic Internet và ứng dụng. Nếu toàn bộ lưu lượng này đi full tunnel, thông lượng lý thuyết cần xử lý trong thời điểm đo là:

\[
2{,}000 \times 3\ \mathrm{Mbit/s} = 6{,}000\ \mathrm{Mbit/s} = 6\ \mathrm{Gbit/s}.
\]

Đây **không phải thông số capacity đủ để mua thiết bị**: còn phải xét peak/burst, encryption throughput, packet/s, concurrent sessions, TLS handshake, overhead encapsulation, bidirectional traffic, gateway failover, VPN licenses, proxy/firewall inspection và headroom.

Nếu split tunnel chỉ đưa trung bình **0,6 Mbit/s/người** của lưu lượng private qua gateway, tổng trung bình minh họa là:

\[
2{,}000 \times 0{,}6\ \mathrm{Mbit/s} = 1{,}2\ \mathrm{Gbit/s}.
\]

Như vậy đường VPN có thể giảm tải đáng kể, nhưng phần lưu lượng trực tiếp phải được kiểm soát bằng lớp khác theo policy, và các chỉ số sử dụng dữ liệu cần được đo thay vì suy luận từ nhãn ứng dụng.

### 10.2. Các số liệu nên đo trước khi chọn

| Chỉ số | Câu hỏi |
|---|---|
| **VPN concurrent users** | Bao nhiêu phiên đang hoạt động lúc cao điểm, có bao nhiêu thiết bị/user? |
| **Ingress/egress bps và pps** | Gateway có đủ năng lực khi nhiều người tải file hoặc họp không? |
| **RTT/jitter/loss** | Route tới SaaS có vòng qua data center xa không? |
| **MTU/MSS và retransmission** | Tunnel overhead có gây fragmentation/PMTU black-hole không? |
| **Gateway CPU, crypto và session table** | Thiết bị đang nghẽn vì mã hóa, chuyển tiếp hay xử lý state? |
| **DNS latency và failure rate** | Split DNS/forwarder có chậm hoặc trả sai view không? |
| **Application SLO** | Login, business API, video, voice, upload có bị ảnh hưởng không? |
| **Security coverage** | Traffic nào được giám sát qua proxy/EDR/DNS/firewall/SOC? |

### 10.3. MTU, encapsulation và TCP MSS

VPN thêm header/overhead nên **effective path MTU** có thể thấp hơn đường vật lý. Nếu packet quá lớn và Path MTU Discovery hoạt động không đúng, có thể thấy **một số web/app chạy, số khác timeout hoặc upload lớn lỗi**.

Các nguyên tắc:

- Kiểm tra MTU/MSS theo giao thức và nền tảng; không dùng một giá trị “chuẩn” cho mọi VPN.
- Không chặn toàn bộ ICMP/ICMPv6 có vai trò cần thiết cho PMTU chỉ vì lo bảo mật.
- Đo TCP retransmission và độ trễ khi qua tunnel, đặc biệt video/voice và ứng dụng dùng UDP.
- Tính đường đi qua NAT, firewall, IPv6 và proxy; một số sản phẩm có tự điều chỉnh MSS nhưng không nên giả định.

## 11. Threat modeling: các điểm thất bại thường gặp

| ID | Rủi ro / boundary | Kịch bản | Biện pháp và phép kiểm chứng |
|---|---|---|---|
| V01 | **IPv6 bypass** | IPv4 full tunnel nhưng AAAA đi trực tiếp | Kiểm tra `::/0`, route lookup IPv6, DNS và egress policy |
| V02 | **DNS leak** | Private domain bị hỏi ngoài đường được phép | Split DNS suffix, DoH/DoT policy, resolver logs |
| V03 | **Route conflict** | Home LAN trùng corporate prefix | IPAM, route lookup, điều hướng app/proxy phù hợp |
| V04 | **Endpoint compromise** | Malware dùng VPN session hợp lệ | EDR, MFA, posture, least privilege, segment nội bộ |
| V05 | **Overprivileged VPN pool** | Mọi remote user vào được server/management | Zone firewall, role-based network access, AuthZ ở app |
| V06 | **Misconfigured kill switch** | Tunnel mất và traffic private đi route ngoài ý muốn | Test disconnect/reconnect, OS firewall policy |
| V07 | **Local LAN exposure** | Thiết bị gia đình không tin cậy truy cập laptop đang VPN | Host firewall, share settings, local exception hẹp |
| V08 | **SaaS direct egress blind spot** | Split direct nhưng web/DNS controls chỉ đặt tại data center | Secure endpoint/cloud egress, log coverage review |
| V09 | **Full tunnel bottleneck** | VPN gateway/ISP/proxy quá tải khi hội họp | Capacity, HA, khu vực egress, QoS và SLO |
| V10 | **Broken return path** | Internal app không có route/NAT đúng về VPN pool | Kiểm tra route, firewall state, NAT/session logs |
| V11 | **Credential/session theft** | Kẻ xấu dùng account/chứng chỉ VPN | MFA, device binding khi hỗ trợ, revoke, anomaly monitoring |
| V12 | **Origin bypass** | Ứng dụng private có IP public không qua gateway | Firewall, private ingress, authentication và inventory |
| V13 | **Policy drift** | Route/DNS exception cũ không còn hợp với cloud/CDN | Owner, versioning, rule review, regression tests |
| V14 | **Multi-interface path** | VPN Wi-Fi ổn nhưng cellular/VM đi sai đường | Kiểm thử nhiều NIC, IPv4/IPv6, process và app |
| V15 | **Captive portal / onboarding** | Full tunnel chặn portal trước khi đăng nhập mạng khách | Bootstrap exception có phạm vi, an toàn và test |
| V16 | **Log identity mismatch** | NAT/proxy làm mọi user có cùng IP gateway | Correlate VPN session, IdP, firewall and application IDs |

### 11.1. Không suy ra an toàn từ một địa chỉ egress

Một website “What is my IP?” cho thấy địa chỉ IP mà **một request cụ thể** xuất hiện trên Internet. Nó không chứng minh những ứng dụng khác, những đích IPv6, DNS, local routes hoặc traffic từ máy ảo đều qua cùng đường.

Một kết luận về mô hình tunnel nên dựa vào **route và policy, kiểm thử từng loại lưu lượng, telemetry của VPN gateway/firewall/endpoint, và kết quả ứng dụng**, với sự đồng ý và quyền kiểm tra thích hợp.

### 11.2. Ví dụ sự cố: split tunnel bị chồng lấn route

~~~mermaid
flowchart TD
    A["Nhân viên báo intranet timeout"] --> B["Kiểm tra VPN authentication/session"]
    B --> C{"DNS private name đúng?"}
    C -->|"Không"| D["Kiểm tra resolver, suffix, DoH và cache"]
    C -->|"Có"| E["Route lookup cho IP đích"]
    E --> F{"Có đi VPN theo chính sách?"}
    F -->|"Không"| G["Phân tích local subnet, metric, IPv6, per-app policy"]
    F -->|"Có"| H["Kiểm tra firewall, return path, AuthZ và app SLO"]
    D --> I["Đối chiếu logs và sửa nhỏ nhất có thể"]
    G --> I
    H --> I
    I --> J["Regression tests và rollback nếu cần"]
~~~

## 12. Kiểm tra đường đi bằng các lệnh chỉ đọc

Chỉ thực hiện trên **endpoint và mạng được quyền kiểm tra**. Các địa chỉ trong ví dụ là dải dành cho tài liệu hoặc private lab; các lệnh dưới đây **không tự đổi route, DNS hay VPN profile**.

### 12.1. Windows PowerShell

~~~powershell
# Liệt kê interface, IP, gateway và DNS đang có.
Get-NetIPConfiguration
Get-DnsClientServerAddress

# Liệt kê route IPv4/IPv6 và các thông số quyết định đường đi.
Get-NetRoute |
  Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric |
  Sort-Object DestinationPrefix

# Thông tin VPN profile của người dùng hiện tại (nếu là Windows VPN native).
Get-VpnConnection

# Chỉ kiểm tra tên private bằng resolver đã được cấp quyền.
Resolve-DnsName -Name "intranet.corp.example.test" -Type A
Resolve-DnsName -Name "intranet.corp.example.test" -Type AAAA
~~~

`Get-VpnConnection` chỉ phản ánh profile mà cmdlet Windows quản lý, **không liệt kê đầy đủ mọi VPN client bên thứ ba**. Tùy phiên bản Windows, quyền và endpoint policy, một số cmdlet có thể không sẵn có. Khi dùng PowerShell từ xa, cần đối chiếu route **ngay trên máy đang thực sự kết nối VPN**.

### 12.2. Linux

~~~bash
# Xem các interface và địa chỉ đang được cấp.
ip -br address

# Đọc bảng route; lưu ý một số VPN dùng nhiều bảng/policy routing.
ip -4 route show
ip -6 route show
ip rule show

# Xem route lookup cho một private và một public IPv4 destination.
ip route get 10.70.10.20
ip route get 198.51.100.80

# Xem route lookup IPv6 ví dụ theo prefix tài liệu.
ip -6 route get 2001:db8:70::20

# Resolver theo từng interface (nếu dùng systemd-resolved).
resolvectl status
~~~

Lệnh `ip route get` kiểm tra quyết định route theo điều kiện truy vấn mặc định tại thời điểm đó; **không phải bằng chứng packet đã được ứng dụng gửi thành công**, đặc biệt nếu có per-process VPN, namespace/container, proxy, OS firewall hoặc routing theo mark. Khi có nhiều policy tables, cần tham chiếu cách client VPN quản lý route trong logs/công cụ chính thức.

### 12.3. Quy trình quan sát thực tế

1. Ghi **VPN profile, chế độ tunnel, user role, phiên bản client, endpoint OS, thời gian và mạng truy cập**.
2. Kiểm tra DNS answer của tên private và public bằng resolver thực được thiết bị dùng.
3. Kiểm tra route tới **IP kết quả phân giải**, không chỉ gateway chung.
4. Kiểm tra ứng dụng kết nối được và **đúng quyền**; đối chiếu request ID, firewall/action và authentication logs.
5. Lặp lại trên IPv4/IPv6, Wi-Fi/Ethernet/cellular và trạng thái reconnect.
6. Thử khi VPN tắt/ngắt **theo kế hoạch được phê duyệt**; không làm gián đoạn máy người dùng đang vận hành dịch vụ quan trọng.

Không tự thay default route, tắt host firewall, tắt DNS validation hay can thiệp vào VPN của tổ chức chỉ để “chứng minh split tunnel”.

## 13. Thiết kế chính sách tunnel có thể audit

Tài liệu sau là **pseudo-policy dùng để thảo luận yêu cầu**, không phải cấu hình có thể triển khai trực tiếp cho bất kỳ sản phẩm VPN nào:

~~~yaml
policyId: REMOTE-ACCESS-EMPLOYEE-001
scope:
  users: managed-employees
  devices: compliant-corporate-endpoints
identity:
  mfaRequired: true
  sessionRevocationSupported: true
tunnel:
  mode: split-include
  ipv4Includes:
    - 10.70.0.0/16
  ipv6Includes:
    - 2001:db8:70::/48  # Prefix chỉ dành cho tài liệu
  internetTraffic:
    path: approved-local-egress-with-endpoint-security
  localLan:
    allowedOnlyWhenApproved: true
dns:
  privateSuffixes:
    - corp.example.test
  privateResolver: authorized-corporate-resolver
  publicResolver: approved-secure-dns-policy
security:
  endpointEDRRequired: true
  remoteAccessRole: employee
  allowManagementByDefault: false
  ipv6AndDnsLeakProtectionRequired: true
failureBehavior:
  privateTraffic: block-when-vpn-unavailable
  publicTraffic: follow-managed-endpoint-policy
observability:
  - vpn-session-and-identity
  - route-policy-version
  - dns-and-egress-policy-status
  - gateway-firewall-actions
owner: network-security-team
review: on-new-app-or-routing-change
~~~

**Các trường trong YAML không tự enforce bảo mật.** Ví dụ `privateTraffic: block-when-vpn-unavailable` chỉ là **yêu cầu**; phải cấu hình và thử trên OS/VPN product thực tế. `approved-local-egress-with-endpoint-security` yêu cầu tổ chức có agent/web/DNS control hoạt động, không phải tự nhiên được bảo vệ chỉ vì ghi trong file.

### 13.1. Gắn policy với điều kiện vận hành

| Trường trong hồ sơ | Câu hỏi kiểm chứng |
|---|---|
| **Owner và version** | Ai phê duyệt thay đổi route/DNS/app exception? Có rollback? |
| **User/device scope** | User bị thu hồi hoặc thiết bị không đạt posture có bị từ chối truy cập? |
| **Routing includes/excludes** | Prefix hiện tại còn đầy đủ không? Cloud service mới có được đưa vào? |
| **DNS policy** | Split-horizon đúng view và IPv4/IPv6 không rò rỉ ngoài phạm vi? |
| **Egress security** | Traffic Internet direct có được bảo vệ bởi agent/proxy/cloud edge đã chọn? |
| **Failure mode** | Mất VPN, đổi Wi-Fi, sleep/wake có fallback sai policy không? |
| **Monitoring** | SOC có phân biệt traffic qua gateway và direct traffic theo quyền riêng tư phù hợp? |

## 14. Ma trận kiểm thử trước khi rollout

| ID | Môi trường/luồng | Kết quả mong muốn | Bằng chứng |
|---|---|---|---|
| P01 | Split: private IPv4 `10.70.10.20` | Đi tunnel; nếu được cấp quyền thì kết nối thành công | Route lookup, VPN/firewall logs, app result |
| P02 | Split: public IPv4 `198.51.100.80` | Đi đường egress theo policy split, không qua gateway nội bộ ngoài ý định | Route/egress observation phù hợp |
| P03 | Full: public Internet | Đi qua egress tổ chức theo policy, cả DNS liên quan | VPN gateway/proxy/firewall telemetry |
| N01 | User chưa có quyền quản trị | Truy cập management zone | Bị từ chối dù VPN connected |
| P04 | Private FQDN | DNS trả đúng private answer; route tới IP qua VPN | Resolver logs, route, TLS/application |
| N02 | Private FQDN từ resolver công khai ngoài phạm vi | Không lộ dữ liệu private ngoài chính sách | Public DNS answer, DNS policy logs |
| P05 | IPv6 private app | Được route và authorize đúng nếu có IPv6 VPN | AAAA/IPv6 route/firewall |
| N03 | IPv6 ngoài VPN trong profile full bắt buộc | Bị route qua VPN hoặc chặn theo policy, không rò ra ngoài | IPv6 route và egress logs |
| P06 | Split public SaaS/video | Hoạt động đúng latency/jitter và egress security | App SLO, agent/web security logs |
| N04 | VPN disconnect/reconnect | Private traffic không fallback ra ngoài; Internet hành xử theo profile | Endpoint route/firewall state, VPN logs |
| N05 | Home LAN trùng IP corp | Không gửi private data nhầm LAN; có kế hoạch xử lý conflict | Route, test đích đại diện, failure message |
| P07 | Chuyển Wi-Fi → cellular | Tunnel phục hồi, giữ đúng route/DNS/role | Client logs và app connectivity |
| N06 | Browser DoH/DoT riêng | Tuân thủ chính sách tên miền nội bộ; không bypass không được phép | Browser/OS resolver policy |
| N07 | VM/container cùng endpoint | Không truy cập private zone trái chính sách | Namespace/VM route và access tests |
| P08 | Gateway failover được thử trong lab | Traffic còn được xử lý theo HA/fail mode đã công bố | HA logs, SLO, packet loss, recovery |
| N08 | Gateway/app origin có public route phụ | Không bypass kiểm soát bằng direct IP | Firewall, ingress, app AuthZ |
| P09 | Sau thay đổi route/DNS | Quan sát và rollback về policy trước nếu tiêu chí fail | Version diff, change ticket, test results |

**Một negative test phải có điểm đối chứng.** Ví dụ kết nối quản trị thất bại vì server đang tắt không chứng minh firewall chặn đúng. Cần ghi nhận firewall action và thử từ một role hợp lệ nếu quy trình kiểm thử cho phép.

## 15. Quy trình thay đổi split/full tunnel an toàn

### Bước 1 — Kiểm kê tài sản và data flow

Liệt kê private network, cloud VPC/VNet, ứng dụng, SaaS, quản trị, DNS, proxy, VPN pool, split-horizon zones, IPv6 và local LAN exceptions. Có chủ sở hữu từng nhóm tài nguyên. Dựng DFD minh họa cả **đường request, response và identity**.

### Bước 2 — Phân loại người dùng và thiết bị

Xác định nhóm employee, contractor, admin, BYOD và thiết bị quản lý; tách quyền network theo vai trò, nhất là truy cập quản trị. Thiết lập MFA, posture và quy trình thu hồi quyền phù hợp trước khi mở bất kỳ route mới nào.

### Bước 3 — Chọn đường đi và lớp bảo vệ bù trừ

Đánh giá full hay split bằng rủi ro, performance và coverage. Với split, xác minh web/DNS/endpoint security bảo vệ luồng ngoài tunnel. Với full, tính capacity gateway/egress/HA và tác động SaaS/video. Kiểm tra cả IPv6, local LAN và ứng dụng dùng proxy/DoH.

### Bước 4 — Dựng baseline và test

Đo VPN throughput, latency/jitter, DNS failure, login success, app errors, firewall denied flows và endpoint health. Tạo bộ positive/negative tests theo ma trận, chạy ở lab hoặc canary nhóm được phép.

### Bước 5 — Thay đổi nhỏ, có version và rollback

Ghi policy diff, người phê duyệt, thời điểm, tiêu chí rollback. Tránh một bước đổi toàn bộ nhân viên sang full tunnel mà không có gateway capacity dự phòng; tránh một lần mở split route ngoài phạm vi rồi mất khả năng giám sát.

### Bước 6 — Theo dõi sau rollout

Đối chiếu **route/DNS thực tế trên client**, VPN gateway/firewall logs, EDR/web security health và SLO của ứng dụng. Khi có đường sai, ưu tiên khoanh vùng prefix/role/client cụ thể và khôi phục policy; không tùy tiện tắt firewall/EDR.

### Bước 7 — Review định kỳ

Khi thêm cloud subnet, tenant, SaaS/CDN, thay IdP, cập nhật client OS, dùng IPv6 hoặc thay mạng nhà cung cấp, review lại route, DNS suffix, bypass, client posture và quyền tài nguyên. Một policy đúng hôm nay có thể **drift** khi địa chỉ/tên miền và đường mạng thay đổi.

## 16. Bài tập tình huống: VPN nhanh hơn nhưng còn đúng boundary không?

**Bối cảnh:** Công ty có 1.500 nhân viên làm việc từ xa. Ứng dụng `intranet.corp.example.test` sử dụng IP private `10.70.10.20`, hệ thống quản trị ở `10.70.50.0/24`. Trong chế độ full tunnel trước đây, mọi người gặp giật hình khi họp trực tuyến và VPN gateway gần mức bão hòa vào giờ cao điểm. Đội network dự định cho SaaS đi trực tiếp bằng split tunnel nhưng giữ route `10.70.0.0/16` qua VPN.

**Dữ kiện bổ sung:**

| Quan sát | Câu hỏi cần đặt |
|---|---|
| Nhân viên mở private app đúng khi ở văn phòng | Khi ở nhà, split DNS/route có đổi không? |
| Một số người dùng mạng nhà `10.70.0.0/16` | Có route conflict; có giải pháp per-app/renumber phù hợp? |
| Browser dùng DoH không theo OS policy | Private FQDN có bị hỏi ngoài resolver doanh nghiệp? |
| Một số nhân viên có kết nối IPv6 riêng | Có AAAA hoặc IPv6 route ngoài policy không? |
| SaaS video chiếm nhiều băng thông qua VPN | Direct egress có EDR/web/DNS protection đúng yêu cầu không? |
| VPN management subnet nằm trong `10.70.0.0/16` | Đưa cả khối qua VPN có làm user thường truy cập được admin không? |
| Một số device dùng VM/container | Mạng khách có dùng routing khác host VPN client không? |

**Câu hỏi:**

1. Phân biệt lợi ích performance của split tunnel với **mức độ kiểm soát** phải bù trừ.
2. Vì sao `10.70.0.0/16` qua VPN vẫn chưa chứng minh quyền tới management `10.70.50.0/24` là đúng?
3. Lập các kiểm thử DNS và IPv4/IPv6 cho `intranet.corp.example.test`, public SaaS, và khi VPN bị ngắt.
4. Đề xuất cách xử lý người dùng mạng nhà trùng corporate prefix mà **không** bảo họ tắt bảo mật trên router.
5. Hệ thống giám sát phải thu những gì để so sánh trải nghiệm người dùng và coverage trước/sau?
6. Có nên bật split tunnel cho admin hoặc BYOD y hệt managed employee không? Vì sao?

**Gợi ý đối chiếu:**

- Đo p95 latency/jitter cho cuộc họp, bps/pps ở VPN gateway và lỗi SaaS; đưa public traffic direct có thể giảm hairpin, nhưng cần endpoint/web/DNS control hoạt động ngoài VPN.
- Route tới `10.70.0.0/16` chỉ cho **khả năng định tuyến**; firewall phải **DENY management mặc định** với employee thường, chỉ cho admin role qua đường được phê duyệt; ứng dụng quản trị vẫn xác thực/MFA/audit.
- Kiểm tra A/AAAA và DNS suffix qua resolver thực, route lookup từng IP, VPN logs, firewall action và application AuthZ. Test trạng thái mất tunnel và dùng DoH/multi-interface để tìm bypass.
- Với mạng trùng IP, cân nhắc ZTNA/application proxy, route cụ thể có kiểm soát, NAT/renumber theo kiến trúc; không hứa một phương pháp phù hợp mọi endpoint.
- Thu policy version, client OS/VPN version, gateway throughput, health của EDR, secure DNS, VPN/RADIUS/IdP, login success, firewall denied/allowed, app SLO và rủi ro privacy của log.
- Admin/BYOD có threat model, ownership và posture khác; thường cần profile và cấp quyền riêng, không mở đường mạng rộng chỉ vì cùng nhu cầu remote.

## 17. Checklist review split tunnel và full tunnel

- [ ] Đã phân biệt tunnel routing, VPN encryption, DNS routing và application authorization.
- [ ] Có inventory các private prefix/zone, VPN pool, ứng dụng, SaaS, IPv4/IPv6 và người sở hữu.
- [ ] Biết chính xác client đưa traffic nào vào tunnel: route lookup, per-app policy, proxy và exceptions.
- [ ] Full tunnel không mặc định được coi là “không thể rò rỉ”; đã test IPv6, DNS và multi-interface.
- [ ] Split tunnel có web/DNS/EDR/host firewall bảo vệ các luồng trực tiếp theo policy.
- [ ] Split DNS, DoH/DoT, DNS cache, CNAME và split-horizon names được kiểm chứng.
- [ ] Đã kiểm tra home LAN overlap, local LAN exception và nguy cơ bridging/forwarding từ endpoint.
- [ ] Traffic private không fallback không được phép khi VPN disconnect, sleep/wake hoặc đổi mạng.
- [ ] VPN gateway/firewall kiểm soát theo user/device/role và zone, không chỉ tình trạng “connected”.
- [ ] Quyền tới management network, DB và tenant khác bị hạn chế độc lập với route.
- [ ] Endpoint compliance, MFA, certificate/credential lifecycle và khả năng revoke được thiết kế.
- [ ] Có return routing, NAT/state và kiểm tra hairpin, MTU/MSS, session khi failover.
- [ ] Capacity planning cho gateway, Internet egress, proxy, DNS, IDS/IPS và các kỳ cao điểm.
- [ ] Đo app SLO, latency/jitter, DNS failures, packet loss và security control coverage.
- [ ] Có test positive/negative cho full/split, IPv4/IPv6, Wi-Fi/cellular, VM/container và client DoH.
- [ ] Logs nối được VPN session/identity với firewall/application mà không ghi dữ liệu bí mật quá mức.
- [ ] Có chính sách riêng cho employee, contractor, BYOD và admin thay vì một profile cho mọi vai trò.
- [ ] Rollout theo canary, kiểm soát phiên bản, ticket phê duyệt và rollback đã được thử.
- [ ] Đã review route/DNS/app exception khi SaaS, cloud, địa chỉ, thiết bị hoặc threat model thay đổi.

**Ghi nhớ:** **Full tunnel ưu tiên đưa nhiều lưu lượng qua điểm egress được quản lý; split tunnel ưu tiên lựa chọn luồng cần VPN và cho một số luồng ra ngoài theo chính sách.** Không mô hình nào tự cung cấp an ninh đầy đủ. Kiến trúc an toàn phải chứng minh **đường đi thực tế, DNS đúng, cả IPv4/IPv6, endpoint được bảo vệ, phân đoạn và phân quyền ở đích, telemetry đủ và hành vi khi tunnel lỗi** — sau đó chọn đánh đổi phù hợp với nghiệp vụ.
