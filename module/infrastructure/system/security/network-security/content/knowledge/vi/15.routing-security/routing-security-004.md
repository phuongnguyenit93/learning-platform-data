# Route hijacking: chiếm dụng tuyến đường và bảo vệ tính toàn vẹn định tuyến

**Route hijacking (chiếm dụng tuyến đường)** là tình huống một chủ thể quảng bá hoặc làm cho hệ thống định tuyến chấp nhận một đường đi **không được chủ sở hữu/đơn vị vận hành tài nguyên cho phép**, khiến một phần lưu lượng hướng đến mạng đích bị chuyển sai đường. Trong Internet, ví dụ quan trọng là **BGP prefix hijacking**: một Autonomous System (AS) phát thông báo BGP về tiền tố IP mà nó không có quyền công bố, hoặc làm sai nguồn gốc/đường đi theo cơ chế định tuyến. Ở mạng nội bộ, những thay đổi route trái phép cũng có thể xảy ra qua giao thức định tuyến động, route tĩnh, default gateway hoặc hạ tầng điều khiển mạng.

Hệ quả có thể là **mất kết nối (blackholing/DoS)**, **chuyển hướng lưu lượng qua một mạng không mong muốn**, **suy giảm hiệu năng**, hoặc tạo điều kiện quan sát/chèn sửa lưu lượng nếu có thêm các điều kiện khác. **Không phải mọi route hijack đều đọc được dữ liệu mã hóa**: TLS/mTLS, xác thực máy chủ và các lớp bảo mật ứng dụng vẫn có vai trò quan trọng.

Bài học thuộc chương **Routing security** của module **SECURITY_NETWORK_SECURITY**, trong bối cảnh xây dựng kiến trúc mạng an toàn với phân đoạn, firewall, VPN, IDS/IPS, NAC/xác thực kết nối, bảo vệ DNS, mạng không dây và cloud. Người học sẽ kết hợp phân tích bảng định tuyến, giám sát control plane, mô hình hóa mối đe dọa, quản lý quyền quảng bá tuyến và phản ứng sự cố.

> **Phạm vi ví dụ:** Các địa chỉ thuộc 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 là dải **TEST-NET** dùng trong tài liệu; 2001:db8::/32 dành cho ví dụ IPv6; các AS số 64510, 64520, 64530, 64566 dưới đây dùng trong mô hình lab. Không phát quảng bá định tuyến cho các tiền tố giả lập này ra Internet công cộng. Bài thực hành sử dụng bản ghi tuyến và sự kiện tổng hợp/offline.

## 1. Mục tiêu học tập

Hoàn thành bài, bạn có thể:

1. Giải thích sự khác biệt giữa **data plane** và **control plane**, mạng đích/prefix, next hop, AS và đường đi BGP.
2. Phân biệt **prefix hijack**, **subprefix hijack**, **route leak**, **route misconfiguration** và thay đổi định tuyến nội bộ trái phép.
3. Phân tích cách **longest prefix match** làm một tuyến cụ thể hơn ảnh hưởng đến đường đi của lưu lượng.
4. Hiểu **ROA, RPKI, Route Origin Validation (ROV)** và trạng thái **Valid / Invalid / NotFound**, cùng những giới hạn của chúng.
5. Thiết kế biện pháp **prefix filtering, AS-path policy, kiểm soát BGP peer, IRR/RPKI, max-prefix, giám sát và quản lý thay đổi** phù hợp.
6. Nhận biết alert như origin-AS change, more-specific prefix, path change, route withdrawal và route leak có ngữ cảnh.
7. Xây dựng playbook kiểm chứng và phối hợp ứng phó, không chặn nhầm lưu lượng chỉ dựa vào một tín hiệu.
8. Thực hành đọc bảng tuyến, phân tích RPKI bằng dữ liệu giả lập và lập ma trận kiểm thử an toàn.

## 2. Nền tảng định tuyến: vì sao có thể bị chiếm dụng?

### 2.1. Định tuyến là một quyết định, không phải chứng minh danh tính

Khi một router muốn chuyển gói tới địa chỉ đích, nó thường tra **Forwarding Information Base (FIB)** được tạo từ các nguồn như route kết nối trực tiếp, route tĩnh và các giao thức định tuyến. FIB lựa chọn tuyến phù hợp theo **longest prefix match** rồi gửi gói qua interface/next hop tương ứng. **Routing Information Base (RIB)** lưu thông tin các tuyến ứng viên và kết quả chọn theo chính sách/thuật toán riêng của thiết bị.

Hai mặt quan trọng:

- **Control plane:** các router/AS trao đổi, học, chọn và quảng bá thông tin tuyến; nơi route policy và xác thực phiên định tuyến có tác dụng.
- **Data plane:** gói IP được chuyển thực tế theo FIB; nơi firewall, ACL, NAT, QoS và các cơ chế chuyển tiếp hoạt động.

Nếu control plane đưa thông tin sai vào quá trình lựa chọn, data plane có thể đi sai tuyến dù router vẫn chuyển packet đúng như FIB đã quy định. **Firewall cho phép TCP/443 không xác thực rằng đường BGP tới IP đích là tuyến được chủ sở hữu cho phép.**

### 2.2. Prefix và longest prefix match

Prefix CIDR mô tả một nhóm địa chỉ. Ví dụ:

~~~text
203.0.113.0/24 : bao phủ 203.0.113.0 đến 203.0.113.255
203.0.113.0/25 : bao phủ 203.0.113.0 đến 203.0.113.127

Địa chỉ đích: 203.0.113.42
  Khớp cả /24 và /25
  => Khi cả hai tuyến đã được cài trong FIB, /25 cụ thể hơn sẽ được chọn.

Địa chỉ đích: 203.0.113.200
  Không thuộc /25 ở trên
  => Tiếp tục dùng tuyến phù hợp khác, chẳng hạn /24.
~~~

**Chú ý:** BGP chọn đường tốt nhất giữa các ứng viên cho *cùng một NLRI/prefix* bằng các thuộc tính và chính sách BGP. Sau khi các tuyến được chọn và cài đặt, cơ chế **longest prefix match của IP forwarding** ưu tiên prefix cụ thể hơn khi nhiều prefix bao phủ cùng địa chỉ. Không đánh đồng chọn BGP best path với việc so độ dài prefix ở bước chuyển tiếp gói.

Trên Internet thực, nhiều mạng lọc prefix IPv4 dài hơn /24 hoặc IPv6 dài hơn /48 theo policy phổ biến, nhưng **không có một ngưỡng toàn cầu bảo đảm mọi router đều lọc như nhau**. Phạm vi ảnh hưởng của hijack phụ thuộc filter, route propagation và chính sách ở từng mạng.

### 2.3. Autonomous System và BGP

Một **Autonomous System (AS)** là tập hợp mạng có chính sách định tuyến tương đối thống nhất, được nhận diện bằng **ASN**. **BGP (Border Gateway Protocol)** trao đổi thông tin reachability giữa các AS (eBGP), cũng có thể vận hành trong một AS (iBGP).

Một thông báo BGP cho prefix có thể chứa:

| Trường / thuộc tính | Vai trò | Điều cần phân biệt |
| --- | --- | --- |
| NLRI/prefix | Mạng đích được quảng bá | Có thể là prefix được chủ sở hữu phân bổ hoặc prefix không được phép |
| AS_PATH | Danh sách các AS đã ghi trên đường đi theo ngữ nghĩa BGP | Dùng cho tránh vòng lặp và policy; không phải chứng thư toàn vẹn end-to-end mặc định |
| Origin AS | AS ở cuối đường AS_PATH công bố nguồn gốc tuyến theo mô hình thông thường | Không tự chứng minh ASN đó được phép công bố prefix |
| NEXT_HOP | Next hop BGP cho tuyến | Cần đạt được qua IGP/static/connected route phù hợp |
| LOCAL_PREF | Ưu tiên tuyến **bên trong AS** theo policy | Được cấu hình trong AS; không phải tín hiệu danh tính đáng tin từ Internet |
| MED | Gợi ý chọn một trong các đường vào AS đối tác trong các điều kiện của BGP | Việc so sánh phụ thuộc policy/router, không thay xác thực nguồn tuyến |
| Communities | Metadata để điều khiển hoặc gắn nhãn policy trên các mạng có hỗ trợ | Community do peer gửi cũng cần được kiểm soát, không phải quyền được chấp nhận tùy ý |

BGP được thiết kế để **trao đổi khả năng tiếp cận** và vận hành theo quan hệ tin cậy/chính sách giữa mạng. Trong mô hình BGP thông thường, một router nhận route từ peer **không tự có bằng chứng mật mã toàn diện** rằng mọi phần của đường AS_PATH hoặc mọi thông báo có quyền được công bố. Đây là một nguyên nhân khiến origin validation và filtering cần thiết.

### 2.4. Những điều xảy ra khi tuyến thay đổi

~~~mermaid
flowchart LR
    U["Người dùng ở AS64530"] --> ISP["Router / ISP"]
    ISP -->|"Tuyến hợp lệ"| O["AS64510\nOrigin được phép"]
    O --> S["Service 203.0.113.42"]
    ISP -. "Có thể đổi tuyến\nnếu nhận/ưu tiên update sai" .-> H["AS64566\nOrigin không được phép"]
    H -. "Blackhole / chuyển hướng\nphụ thuộc tình huống" .-> X["Đường đi không mong muốn"]
~~~

Mũi tên nét đứt biểu diễn tình huống rủi ro, **không có nghĩa mọi ISP sẽ chấp nhận tuyến sai**. Từng mạng có thể lọc prefix/ASN, áp RPKI origin validation hoặc chọn tuyến khác theo local policy. Cùng một biến cố có thể ảnh hưởng **một phần Internet**, không phải tất cả mạng.

## 3. Các dạng route hijacking và sự cố dễ nhầm

| Tình huống | Điều xảy ra | Rủi ro / phân biệt |
| --- | --- | --- |
| **Exact-prefix origin hijack** | AS không được phép quảng bá cùng prefix mà AS hợp lệ đang công bố | Có thể hút traffic từ một số mạng nếu tuyến được chấp nhận/ưu tiên |
| **More-specific / subprefix hijack** | Một AS quảng bá prefix con cụ thể hơn, chẳng hạn /25 dưới /24 | Ở mạng chấp nhận tuyến con, FIB có thể ưu tiên prefix đó cho địa chỉ tương ứng |
| **Route leak** | Route được học từ một quan hệ (khách hàng/peer/provider) bị xuất sang quan hệ khác trái với policy dự kiến | Đường có thể có origin hợp lệ nhưng đi qua AS không mong muốn; khác origin hijack |
| **Accidental misorigination** | Nhà mạng/đơn vị vận hành phát nhầm tuyến do cấu hình, nhập sai ASN/prefix | Hệ quả có thể giống hijack dù không có chủ ý tấn công |
| **Internal route manipulation** | Route OSPF/IS-IS/BGP nội bộ hoặc route tĩnh bị thêm/sửa trái phép | Chuyển hướng/blackhole bên trong doanh nghiệp, không nhất thiết liên quan BGP toàn cầu |
| **Default route hijacking nội bộ** | Client/router dùng gateway/default route do chủ thể không đáng tin quảng bá/cấu hình | Có thể đổi toàn bộ lưu lượng ra khỏi một mạng; cần xem DHCP/RA/IGP và bảo vệ lớp truy cập |
| **Traffic engineering được cho phép** | Chủ mạng chủ động quảng bá prefix cụ thể hơn hoặc thay route policy theo kế hoạch | Không tự coi mọi thay đổi origin/đường đi là tấn công; cần kiểm tra owner và change ticket |

**Route leak và hijack có thể cùng gây gián đoạn**, nhưng nguyên nhân và kiểm soát không hoàn toàn giống. RPKI ROV phát hiện một số **origin mismatch**, không xác minh toàn bộ quan hệ xuất/nhập route giữa AS, nên một **route leak có origin RPKI Valid** vẫn có thể gây ảnh hưởng.

### 3.1. Exact-prefix hijack

Trong mô hình hợp lệ, **AS64510** công bố prefix **203.0.113.0/24**. Một AS khác, chẳng hạn **AS64566**, phát cùng prefix với origin khác. Từng mạng nhận cả hai route có thể chọn đường dựa trên **local preference, AS_PATH, các thuộc tính BGP khác và chính sách của nó**. Vì vậy chỉ một số client có thể đi theo tuyến sai.

Quan sát thường thấy: xuất hiện **origin ASN mới** cho cùng prefix, thay đổi path đột ngột, đường tới dịch vụ chậm hoặc không thông, nhưng **một bản ghi route đơn lẻ không khẳng định intent của chủ thể quảng bá**.

### 3.2. More-specific prefix hijack

Nếu một tuyến hợp lệ **203.0.113.0/24** tồn tại và mạng khác chấp nhận thêm **203.0.113.0/25** không được phép, traffic tới **203.0.113.0–203.0.113.127** tại mạng đó có thể đi theo /25 vì longest prefix match. Phần địa chỉ còn lại vẫn có thể theo /24. Đây là lý do **chỉ giám sát exact prefix chưa đủ**.

Trên các mạng lọc IPv4 prefix dài hơn /24, quảng bá /25 có thể không được chấp nhận; điều đó làm giảm phạm vi ảnh hưởng nhưng **không thay nhu cầu lọc tuyến hợp lệ và giám sát prefix con**. Trên IPv6, ngưỡng lọc, chính sách quảng bá và các quy tắc RPKI maxLength cũng cần xét riêng.

### 3.3. Chuyển hướng traffic không đồng nghĩa giải mã được TLS

Nếu route hijack làm lưu lượng đi tới endpoint khác, những việc có thể xảy ra gồm:

- **Blackhole:** gói bị rơi, client timeout.
- **Degradation:** đường vòng, độ trễ cao hoặc packet loss.
- **Interception/observation:** một mạng trên đường mới có thể quan sát metadata và các gói không được mã hóa.
- **Impersonation/alteration:** chỉ xảy ra nếu các lớp xác thực/mã hóa hoặc ứng dụng có điểm yếu phù hợp; không thể mặc định đọc được HTTPS/TLS hiện đại được cấu hình và xác minh đúng.
- **Traffic redirection with forwarding:** lưu lượng đi vòng qua một AS rồi vẫn đến đích thực, khó nhận biết chỉ từ tình trạng ứng dụng "vẫn hoạt động".

Chính sách ứng cứu phải xem **tác động quan sát được** và các lớp bảo vệ đang có, tránh khẳng định dữ liệu đã bị lộ chỉ vì AS_PATH thay đổi.

## 4. Route hijacking ở Internet và trong mạng doanh nghiệp

### 4.1. BGP giữa các tổ chức

Ở Internet, một tổ chức không tự kiểm soát mọi router trung gian. Nó có thể quản lý:

1. Những prefix/ASN mình được phép quảng bá.
2. Những tuyến export cho transit/peer và các điều kiện trên BGP session của mình.
3. **ROA trong RPKI** nếu có quyền đối với IP resource.
4. IRR route objects, danh sách prefix/AS policy gửi cho đối tác.
5. Route monitoring qua collectors/looking glass và hệ thống cảnh báo.
6. Hợp đồng/phối hợp với upstream, peers và tổ chức quản lý tài nguyên IP khi phát hiện tuyến sai.

Không thể trực tiếp ra lệnh cho mọi mạng trên Internet loại bỏ một thông báo BGP; **thời gian và mức độ phục hồi phụ thuộc khả năng lọc, propagation và phối hợp giữa nhiều mạng**.

### 4.2. IGP và router nội bộ

Trong doanh nghiệp, những vấn đề tương tự có thể đến từ **OSPF, IS-IS, static route, DHCP default gateway, IPv6 Router Advertisement, VRF route leaking, BGP nội bộ hoặc SDN control plane**. Chúng không phải lúc nào cũng là BGP prefix hijack toàn cầu.

Các bảo vệ cần đánh giá theo giao thức:

| Bề mặt | Kiểm soát phòng vệ | Giới hạn |
| --- | --- | --- |
| OSPF/IS-IS adjacency | Xác thực neighbor theo cơ chế giao thức hỗ trợ, interface/passive-interface phù hợp, lọc mạng điều khiển | Xác thực neighbor không tự chặn route sai do một router có quyền bị chiếm |
| eBGP/iBGP session | ACL control-plane, xác thực TCP session khi hỗ trợ, GTSM/TTL-security trong mô hình phù hợp, quản lý peer | Chỉ bảo vệ phiên/peer; không tự xác thực mọi prefix được quảng bá |
| Static/default route | RBAC/config audit, change review, sao lưu và giám sát routing table | Route được admin thêm vẫn có thể sai nếu không review |
| LAN default gateway | DHCP snooping/RA Guard hoặc biện pháp L2/L3 theo thiết bị, NAC/802.1X, phân đoạn | Cơ chế cho IPv4/IPv6 và thiết bị hỗ trợ khác nhau |
| VRF/route redistribution | Kiểm soát import/export, tag/route policy, test đường về | Lộ tuyến giữa tenant/zone có thể tạo đường đi trái thiết kế |
| Cloud route table | IAM, policy IaC, route audit, network firewall | Cloud route table không tương đương BGP Internet, dù cũng ảnh hưởng next hop |

**Điều khiển route và kiểm soát dữ liệu phải đi cùng nhau.** Nếu một route sai đưa traffic vùng Web sang vùng dữ liệu, segmentation/firewall theo workload có thể hạn chế tác hại; nếu mọi zone dùng allow-all, route sai có thể làm mở rộng phạm vi tiếp cận.

### 4.3. Route hijack khác DNS hijack, ARP spoofing và NAT

| Hiện tượng | Mục tiêu bị tác động | Dấu hiệu chính |
| --- | --- | --- |
| Route hijacking | Đường đi IP/prefix hoặc next hop | RIB/FIB, BGP update/origin, routing table thay đổi |
| DNS poisoning/hijack | Ánh xạ **tên miền → IP** | DNS answers/resolver khác dự kiến; route tới IP có thể vẫn đúng |
| ARP spoofing / IPv6 ND abuse | Ánh xạ địa chỉ lớp mạng với địa chỉ lớp liên kết trong LAN | Neighbor/ARP table và L2 traffic không khớp |
| NAT misconfiguration | Địa chỉ/cổng được **dịch** khi lưu lượng qua gateway | Pre/post NAT mapping, rule hit và đường phản hồi |
| Application redirect/proxy misconfig | Endpoint HTTP được gọi/forward | HTTP Host/Location, proxy route, TLS và application logs |

Các vấn đề có thể xảy ra cùng lúc, nhưng **khắc phục DNS không tự sửa BGP** và ngược lại. Cần bắt đầu từ dữ liệu gốc: tên được giải, IP đích thật, route được chọn và response ở tầng ứng dụng.

## 5. RPKI, ROA và Route Origin Validation (ROV)

### 5.1. Vì sao cần thông tin origin được chứng thực?

Một tuyến BGP mang prefix và origin AS, nhưng chỉ nhìn AS_PATH không đủ để xác nhận **AS đó có được chủ tài nguyên IP cho phép phát prefix hay không**. **Resource Public Key Infrastructure (RPKI)** cung cấp hạ tầng chứng thực tài nguyên Internet, giúp các bên tạo và xác minh thông tin quyền liên quan tới dải địa chỉ IP/ASN theo cơ chế của RPKI.

**Route Origin Authorization (ROA)** là đối tượng được ký trong RPKI để chỉ ra **AS nào được phép là origin** của một prefix, cùng độ dài prefix tối đa được cho phép đối với phạm vi đó. Router hoặc hệ thống điều khiển nhận dữ liệu xác thực từ validator/cache được tin cậy, sau đó thực hiện **Route Origin Validation (ROV)** cho các BGP announcement.

~~~mermaid
flowchart LR
    H["Chủ tài nguyên IP"] -->|"Tạo/duy trì ROA"| PKI["RPKI publication"]
    PKI --> V["RPKI validator"]
    V -->|"Validated payloads\nRPKI-RTR"| R["BGP router áp ROV"]
    B["BGP peer gửi route"] --> R
    R --> D{"Origin validation state"}
    D -->|"Valid"| A["Đánh giá tiếp bằng BGP policy"]
    D -->|"Invalid"| I["Loại bỏ / xử lý theo policy"]
    D -->|"NotFound"| N["Chính sách riêng\nkhông phải Valid"]
~~~

**RPKI không làm router tự chặn tất cả các tuyến sai**. Chặn origin **Invalid** đòi hỏi router/nền tảng áp **ROV policy** đúng trong đường nhận route; validator cũng phải hoạt động và dữ liệu đủ mới. Trạng thái **NotFound** có ý nghĩa khác **Valid** và **Invalid**.

### 5.2. Các trường quan trọng trong ROA

Giả sử chủ prefix trong bài có quyền quản lý **203.0.113.0/24** và cho phép **AS64510** công bố:

~~~text
ROA mô phỏng:
  Prefix:     203.0.113.0/24
  Origin AS:  AS64510
  MaxLength:  24
~~~

| Trường | Ý nghĩa | Lưu ý an toàn |
| --- | --- | --- |
| Prefix | Phạm vi địa chỉ được chủ tài nguyên tạo chứng thực | Chỉ tạo cho tài nguyên tổ chức có quyền quản lý |
| Origin AS | ASN được phép khởi tạo các quảng bá được ROA bao phủ | Cần bao gồm những AS origin hợp lệ theo thiết kế multihoming/đối tác |
| MaxLength | Độ dài prefix cụ thể nhất được phép cho origin AS trong ROA | MaxLength quá rộng mở rộng khả năng xuất hiện các prefix con **Valid** không cần thiết |
| Chữ ký và chuỗi chứng thực | Cho phép validator kiểm tra đối tượng theo RPKI | ROA hết hạn, lỗi xuất bản hoặc chứng thực bị thu hồi có thể đổi trạng thái |

Với **MaxLength 24**, ROA đó cho phép **AS64510** làm origin của **203.0.113.0/24**. Một quảng bá **203.0.113.0/25** sẽ **không được xem là Valid theo ROA này**, dù cùng AS64510, vì độ dài /25 vượt MaxLength 24; nếu không có ROA khác phù hợp và có ROA bao phủ prefix đó, trạng thái là **Invalid**.

**Khuyến nghị:** đặt MaxLength bằng độ dài prefix thực sự cần công bố khi có thể; chỉ mở tới prefix con nếu có yêu cầu và kế hoạch quảng bá rõ ràng. Nếu AS64510 có chủ đích công bố nhiều prefix con, ROA phải tương ứng với danh sách origin/độ dài đó.

### 5.3. Ba trạng thái origin validation

Theo mô hình ROA ở trên, các tuyến được đánh giá như sau:

| BGP announcement đang xét | ROA bao phủ | Kết quả ROV lý thuyết | Lý do |
| --- | --- | --- | --- |
| 203.0.113.0/24, origin AS64510 | 203.0.113.0/24, AS64510, max24 | **Valid** | Khớp origin và độ dài |
| 203.0.113.0/24, origin AS64566 | Cùng ROA | **Invalid** | Origin AS khác AS được phép |
| 203.0.113.0/25, origin AS64510 | ROA /24 max24 bao phủ | **Invalid** | Prefix con vượt độ dài cho phép |
| 203.0.113.0/25, origin AS64566 | ROA /24 max24 bao phủ | **Invalid** | Sai cả origin và độ dài |
| 198.51.100.0/24, origin AS64520 | Giả sử **không có ROA nào bao phủ** | **NotFound** | Không có dữ liệu ROA để đánh giá đúng/sai nguồn gốc |
| 203.0.113.0/24, origin AS64510, AS_PATH thay đổi bất thường | Cùng ROA | **Valid** về origin | ROV không xác minh toàn bộ AS_PATH |

Các trạng thái thực tế phụ thuộc **toàn bộ tập ROA hợp lệ tại thời điểm kiểm tra**, không phải chỉ một dòng trong bảng. Một prefix có thể được bao phủ bởi nhiều ROA; thông báo **Valid khi ít nhất một ROA phù hợp với prefix/độ dài và origin**, còn **Invalid** khi có các ROA bao phủ nhưng không có ROA nào phù hợp. **NotFound** khi không tìm thấy ROA bao phủ theo quy tắc kiểm tra origin.

**Không coi NotFound là xác thực thành công.** Đó là trạng thái không có thông tin chứng thực origin trong RPKI, cần xem thêm IRR, quyền tài nguyên, hợp đồng và giám sát.

### 5.4. ROV bảo vệ được và không bảo vệ được gì?

ROV hữu ích khi mạng nhận route có **origin ASN không phù hợp với ROA đang có**, trong đó có nhiều trường hợp exact-prefix hoặc more-specific origin hijack. Tuy nhiên:

- **ROV chỉ kiểm tra nguồn gốc theo prefix/ASN**, không chứng thực mọi AS trên AS_PATH.
- Một **route leak với origin AS hợp lệ** vẫn có thể là **RPKI Valid**.
- Một kẻ xấu phát một đường đi có **origin AS đúng** nhưng làm sai các phần khác của đường không bị ROV phát hiện chỉ dựa vào origin.
- Một mạng không triển khai ROV vẫn có thể chấp nhận tuyến **Invalid**; bảo vệ có hiệu quả theo phạm vi những mạng thực thi.
- **ROA sai của chủ tài nguyên** có thể vô tình làm tuyến hợp lệ thành Invalid và gây mất kết nối ở các mạng lọc Invalid.
- **Validator/cache hỏng, dữ liệu stale hoặc lỗi kết nối router–cache** cần được giám sát; cách xử lý khi không có dữ liệu xác thực tùy policy hệ thống.
- **ROV không thay prefix filtering, quan hệ BGP, route leak prevention, TLS, giám sát hoặc kế hoạch ứng cứu**.

Ngoài RPKI, các cơ chế bảo vệ đường AS và quan hệ giữa AS còn đang được phát triển/triển khai với mức độ hỗ trợ khác nhau; khi chọn giải pháp cần xác minh khả năng tương thích của router, software, peer và tình trạng vận hành thực, không giả định một công nghệ tự bảo vệ mọi dạng hijack.

### 5.5. Các tình huống hợp lệ cần được xét trước khi phát hành ROA

Trước khi tạo hoặc sửa ROA cho prefix sản xuất, kiểm kê:

1. **Origin ASN hiện tại** của từng prefix IPv4/IPv6.
2. **Multihoming:** nhiều ISP nhưng có thể **cùng origin AS**; transit AS thường không trở thành origin chỉ vì mang traffic. Nếu dùng thực sự nhiều origin ASN, cần có ROA phù hợp.
3. **DDoS mitigation/scrubbing:** nhà cung cấp có thể cần quảng bá một số prefix hoặc origin khác trong sự cố; phải xác nhận mô hình với hợp đồng trước khi đổi ROA.
4. **Traffic engineering:** có công bố prefix con ở điều kiện được duyệt không? MaxLength và filter có phản ánh đúng không?
5. **Chuyển ASN/hợp nhất hệ thống:** giai đoạn chuyển đổi có thể tồn tại nhiều origin ASN hợp lệ theo kế hoạch.
6. **IPv6:** ROA và độ dài prefix phải được xét riêng với IPv4.
7. **Thay đổi dịch vụ cloud/bring-your-own-IP:** quy trình chứng thực và origin có thể có điều kiện riêng từ nhà cung cấp.

Không tạo ROA "maxLength mở rộng nhất có thể" chỉ để hết cảnh báo. Mỗi mở rộng phải có **owner, nhu cầu và phép thử**, vì nó ảnh hưởng đến bề mặt chấp nhận quảng bá.

## 6. Lớp kiểm soát BGP quanh route hijacking

### 6.1. Prefix filtering ở biên

**Ingress filtering** tại BGP peer quyết định **những tuyến nào được chấp nhận từ peer đó**. **Egress filtering** quyết định **những prefix nào được phép quảng bá ra peer**. Chúng giúp thực thi quan hệ kinh doanh và quyền quảng bá thay vì tin mọi thông báo BGP.

| Chính sách | Ví dụ ý định | Lợi ích |
| --- | --- | --- |
| Customer prefix allowlist | Chỉ nhận prefix được đăng ký/duyệt từ khách hàng tương ứng | Giảm nguy cơ khách hàng phát nhầm hoặc vượt quyền |
| Origin-AS checks và ROV | Loại/đánh dấu Invalid theo policy; dùng nguồn hợp lệ để kiểm chứng | Bảo vệ trước một phần origin hijack |
| IRR-based filtering | Tạo/review danh sách prefix/AS theo route objects được xác minh | Hỗ trợ vận hành quan hệ khách hàng, cần đánh giá dữ liệu có chính xác/mới không |
| Export policy | Chỉ công bố prefix của mình hoặc những route được phép theo quan hệ | Ngăn phát nhầm đường ra ngoài, giảm route leak |
| Prefix length policy | Giới hạn độ cụ thể, chính sách riêng cho v4/v6 | Giảm route bất thường và áp dụng policy vận hành |
| Default-route policy | Chỉ nhận hoặc phát default route khi được cho phép | Tránh đổi tuyến lớn ngoài thiết kế |
| Max-prefix / prefix limits | Phát hiện/kiểm soát số lượng prefix peer gửi vượt giới hạn | Hạn chế tác động rò rỉ hoặc lỗi update hàng loạt |
| Community controls | Chỉ chấp nhận community có nghĩa được thỏa thuận | Tránh peer điều khiển nhầm local preference/blackhole community |
| Peer/session security | Chỉ thiết lập kết nối BGP với neighbor được cấp quyền | Giảm rủi ro phiên định tuyến bị tạo hoặc giả mạo trái phép |

**Một prefix filter đúng phải xuất phát từ danh sách prefix/ASN được cấp quyền**, không tự tạo bằng cách chép bảng tuyến đang quan sát thấy, vì bảng đó có thể chứa route không mong muốn.

### 6.2. Bảo vệ quyền quảng bá và quan hệ BGP

Một ISP thường có các loại quan hệ như customer, peer và transit provider. Mỗi loại có **chính sách export/import** khác nhau; route leak thường xuất hiện khi route học từ một quan hệ bị chuyển sang quan hệ không phù hợp.

Ví dụ khái niệm:

~~~text
AS của doanh nghiệp nhận default route từ transit.
AS được phép công bố các prefix mà doanh nghiệp sở hữu/quản lý.

SAI:
  Export toàn bộ các route học từ provider A sang provider B
  dù không có chủ đích transit giữa hai provider.

ĐÚNG THEO Ý ĐỊNH:
  Export tới provider B chỉ những prefix được cấp quyền
  và các route bổ sung đã được hợp đồng/policy chấp thuận.
~~~

Đây là **tư duy policy**, không phải lệnh BGP. Các hệ thống multihoming, IX/route server, mạng transit hoặc dịch vụ đặc thù có yêu cầu khác nhau. Khi thiết kế cần phân biệt **customer cone, đường đi hợp lệ theo quan hệ và nhu cầu traffic engineering**; không áp một luật chung cho mọi mạng.

### 6.3. Xác thực session và kiểm soát control plane

Các biện pháp như xác thực BGP TCP session được hỗ trợ, ACL bảo vệ control plane, **GTSM/TTL-security** trong mô hình peer phù hợp, giới hạn nguồn kết nối và quản lý phiên có thể giảm nguy cơ giả mạo hoặc lạm dụng kết nối tới router. Chúng **không chứng thực origin cho mọi prefix**: một peer được xác thực vẫn có thể phát sai route do cấu hình hoặc bị chiếm quyền.

Cần bảo vệ:

- **Quyền quản trị router** bằng AAA, phân quyền theo vai trò, MFA/jump host theo kiến trúc.
- **SSH/API/telemetry** trên mạng quản trị, không công bố không cần thiết ra Internet.
- **BGP neighbor configuration** gồm ASN, địa chỉ peer, loại session, route policy và giới hạn.
- **Change control**, lưu cấu hình phiên bản, so drift và sao lưu cấu hình/rollback.
- **Khả năng xử lý update**: control-plane policing theo nền tảng, giới hạn tài nguyên và cảnh báo CPU/memory/route churn.

### 6.4. Route origin validation có thể triển khai từng bước

Quy trình phòng vệ ở một mạng kiểm soát được BGP router:

1. Kiểm kê router, phiên bản phần mềm, khả năng RPKI validator/RTR và luồng BGP v4/v6.
2. Thiết kế ít nhất một nguồn validator/cache **được tin cậy**, tính sẵn sàng và cơ chế kiểm tra dữ liệu.
3. Bật quan sát **RPKI state** và so với bảng route đang có trước khi quyết định lọc.
4. Điều tra các route **Invalid** thuộc doanh nghiệp/khách hàng: có thể là ROA lỗi, chuyển AS hoặc traffic engineering hợp lệ chưa được cập nhật.
5. Thiết kế ROV policy **không chấp nhận Invalid** theo mục tiêu bảo vệ và khả năng nền tảng, kèm phương án xử lý khi validator/cache gián đoạn.
6. Triển khai theo phạm vi/peer phù hợp, theo dõi reachability, số route Valid/Invalid/NotFound và số tác động tới traffic thật.
7. Review bằng dữ liệu route collectors và kiểm thử failover, sau đó mở rộng nếu đạt tiêu chí.

**Phân biệt invalid vì ROA sai** với **invalid vì quảng bá trái phép** trước khi thay đổi quy tắc ở mức tổ chức. Loại bỏ một prefix hợp lệ do dữ liệu ROA lỗi có thể làm dịch vụ mất kết nối trên mạng thực thi ROV.

## 7. Phát hiện và giám sát route hijacking

### 7.1. Dữ liệu nên thu thập

Một chương trình giám sát cần nhiều góc nhìn:

| Nguồn | Dữ liệu | Ý nghĩa | Giới hạn |
| --- | --- | --- | --- |
| BGP router của mình | Adj-RIB-In/Loc-RIB, best path, peer, update, withdraw theo khả năng | Biết route nào mình nhận và chọn | Không thể hiện toàn bộ lựa chọn của Internet |
| RPKI validator/ROV logs | Valid/Invalid/NotFound, thời gian cập nhật, tình trạng cache | Phát hiện thay đổi origin validation và lỗi dữ liệu | Không xác minh toàn bộ AS path |
| Public route collectors / looking glass | Prefix, origin AS, path từ nhiều vantage points | Quan sát propagation và origin thay đổi ở các mạng khác | Không có đầy đủ góc nhìn, có độ trễ, khác policy |
| IRR/route registry và dữ liệu quyền tài nguyên | Đối chiếu prefix–ASN và thay đổi đăng ký | Bổ sung thông tin vận hành | Dữ liệu có thể sai hoặc chưa cập nhật |
| Flow/NetFlow/IPFIX/sFlow | Thay đổi hướng đi, tải, next hop/cổng quan sát được tùy nguồn | Gợi ý ảnh hưởng tới traffic thật | Chỉ metadata; có sampling và vị trí quan sát |
| Active probes được cấp phép | Ping/traceroute/TCP/TLS checks từ nhiều vùng | Đánh giá availability, RTT, thay đổi hop/path | Traceroute có thể không phản ánh path BGP đầy đủ |
| DNS/application telemetry | Phân giải IP, kết nối TLS, lỗi ứng dụng | Phân biệt route issue và DNS/app issue | Không cho biết origin AS của đường Internet nếu đứng riêng |
| Control-plane/IAM audit | Cấu hình neighbor, prefix filter, ROA, thay đổi cloud routes | Xác minh thay đổi do ai và có được duyệt không | Thiếu log không chứng minh không có thay đổi |

**Không suy luận origin hijack chỉ từ traceroute.** Hop có thể ẩn, dùng MPLS/ECMP, ICMP rate limiting hoặc đường phản hồi bất đối xứng. Route collectors và ROV cung cấp tín hiệu control plane quan trọng hơn để đánh giá quảng bá prefix.

### 7.2. Dấu hiệu cảnh báo

- **Unexpected origin ASN:** một prefix tổ chức quản lý xuất hiện origin khác danh sách được duyệt.
- **Unexpected more-specific:** một prefix con xuất hiện không nằm trong kế hoạch công bố.
- **RPKI Invalid:** thông báo không phù hợp ROA bao phủ tại thời điểm kiểm tra.
- **Origin/path changes:** AS_PATH hoặc next hop biến động bất thường; có thể do traffic engineering hợp lệ.
- **Route withdrawals/route churn:** một prefix bị rút rồi quảng bá lại thường xuyên.
- **Reachability degradation:** tăng timeout, RTT hoặc packet loss từ nhiều vùng sau một route update.
- **Unexpected route exports:** các route học từ provider/peer bị phát sang neighbor không phù hợp.
- **Changes to ROA/IRR/BGP policy:** tài nguyên/định tuyến bị thay đổi ngoài kế hoạch.
- **Blackhole/traffic drop indicators:** đích trở nên không đến được từ một số khu vực; cần phân biệt với DDoS mitigation được duyệt.

Cảnh báo nên ưu tiên **các prefix đang phục vụ tài sản quan trọng**, có owner rõ ràng; đồng thời cần theo dõi các mạng liên quan như DNS resolver, identity provider, API gateway, VPN gateway và hệ thống điều khiển cloud.

### 7.3. Cấu trúc sự kiện giám sát

Ví dụ **JSON synthetic**, không phải schema cố định của router hoặc SIEM:

~~~json
{
  "event_id": "bgp-observer-20261128-001",
  "event_time": "2026-11-28T03:15:00Z",
  "observer": {"id": "route-collector-lab-1", "asn": 64530},
  "address_family": "ipv4",
  "prefix": "203.0.113.0/24",
  "origin_asn": 64566,
  "as_path": [64520, 64566],
  "rpki_state": "Invalid",
  "approved_origin_asns": [64510],
  "event_kind": "unexpected_origin",
  "action_taken": "alert_only",
  "source": "synthetic_lab_data"
}
~~~

Khi chuẩn hóa sự kiện, nên giữ:

| Trường | Lý do |
| --- | --- |
| event_time và ingest_time | Xử lý độ trễ/clock skew; nối với thay đổi cấu hình |
| observer/peer/ASN | Nhận diện vantage point và quan hệ BGP |
| AFI/SAFI, prefix, origin ASN | Phân biệt IPv4/IPv6 và loại tuyến; nhận biết prefix con |
| AS_PATH và attributes cần thiết | Điều tra đường đi và cơ chế chọn route |
| RPKI validation state + thời điểm dữ liệu | Đối chiếu với ROA và validator tại thời điểm đó |
| Approved origin registry + version | So với danh sách được duyệt có thay đổi kiểm soát |
| Update/withdraw, first_seen/last_seen | Biết vòng đời quảng bá và độ dài sự kiện |
| BGP policy result / action | Phân biệt chỉ phát hiện với route bị lọc thực tế |
| Asset/service/criticality/owner | Ưu tiên sự cố và người liên hệ |
| Raw source + correlation/case ID | Truy vết và kiểm toán |

Không ghi **"route blocked"** nếu bản ghi chỉ là cảnh báo từ hệ thống giám sát. Một observer có thể thấy thông báo dù router của mình đã lọc nó; hiệu lực ROV phải kiểm tra tại điểm thực thi.

### 7.4. SIEM correlation đa nguồn

Một use case có giá trị hơn raw BGP alert là:

~~~text
IF origin ASN của prefix quan trọng không thuộc allowlist
AND (trạng thái RPKI là Invalid
     OR xuất hiện prefix con không nằm kế hoạch)
AND thay đổi được thấy từ >= 2 vantage points độc lập
THEN tạo case cần điều tra
     gắn ROA snapshot, BGP paths, route owner và change calendar

IF đồng thời availability probes xấu đi
THEN tăng mức ưu tiên dựa trên impact đã đo được

KHÔNG tự chặn ASN hoặc rút route khỏi Internet chỉ từ case này.
~~~

Điều kiện **2 vantage points** ở đây chỉ là **một lựa chọn để tăng độ tin cậy**, không phải yêu cầu bắt buộc. Một hijack ảnh hưởng đúng một khu vực vẫn có thể nghiêm trọng; đừng đặt rule làm bỏ qua mọi cảnh báo chỉ quan sát tại một điểm.

### 7.5. Giám sát chủ động từ nhiều vùng

Nếu tổ chức có API ở AS64510, test nên gồm:

1. **Control plane:** prefix và origin ASN hiện tại tại các route collector, router của mình và ISP được phép xem.
2. **Data plane:** kiểm tra TCP/TLS/API availability từ các điểm khách hàng quan trọng được cấp quyền.
3. **Name resolution:** xác nhận DNS trả IP dự kiến, tránh nhầm route hijack với DNS record sai.
4. **RPKI health:** ROA, expiry/trust chain và validator/cache, bao gồm cả IPv4 lẫn IPv6.
5. **Change correlation:** các thay đổi ISP, ASN, cloud, mitigation, RPKI và route policy có được duyệt không?

Một probe trả HTTP 200 **không chứng minh không có traffic diversion**. Tùy tình huống, một route không mong muốn có thể tiếp tục chuyển tiếp tới dịch vụ thật. Ngược lại, HTTP 500 không tự chứng minh hijack vì ứng dụng có thể lỗi nội bộ.

## 8. Mô hình hóa mối đe dọa Route hijacking

| Tài sản / điểm vào | Đe dọa | Hậu quả | Kiểm soát / bằng chứng |
| --- | --- | --- | --- |
| Prefix IPv4/IPv6 public của tổ chức | Origin ASN không được phép quảng bá prefix | Traffic diversion, blackhole, gián đoạn | ROA chính xác, ROV ở peer, prefix filtering, route collectors |
| BGP session với upstream | Peer phát sai hoặc quá nhiều tuyến | Route leak, bảng tuyến lỗi, ảnh hưởng vận hành | Import/export policy, max-prefix, control-plane protection |
| Router control plane | Credential admin bị lộ hoặc cấu hình trái phép | Thay origin/policy/next hop, rút route | AAA/RBAC, audit, backup, change review, network management isolation |
| DDoS mitigation provider | Mô hình công bố tuyến trong sự cố không được cập nhật | Route hợp lệ thành RPKI Invalid, gián đoạn khắc phục | ROA/allowlist theo hợp đồng, diễn tập và phối hợp trước |
| Route registry/ROA | Thay đổi sai hoặc quyền quá rộng | Các mạng ROV từ chối tuyến hợp lệ, hoặc chấp nhận thêm origin không cần | Quản trị tài nguyên/IPAM, approval và kiểm tra định kỳ |
| IGP trong data center | Neighbor/route injection trái phép | Next hop sai, cô lập vùng, blackhole nội bộ | Xác thực neighbor, phân đoạn control plane, routing policy và giám sát |
| Cloud route table/VPN | Route tới workload bị đổi sang middlebox khác | Bypass kiểm soát, mất đường trả lời, rò traffic | Cloud IAM/audit, network firewall, test reachability/return path |
| End-user application | Traffic tới endpoint sai hoặc bị chặn | Lỗi TLS, gián đoạn hoặc rủi ro phiên nếu ứng dụng kiểm chứng yếu | TLS/mTLS đúng chuẩn, identity/authorization, telemetry và failover |
| Monitoring pipeline | Chỉ giám sát một vantage point, dữ liệu RPKI/log stale | Không phát hiện hoặc false positive | Multi-vantage, data quality, clock sync và health alerts |

### 8.1. STRIDE cho định tuyến

- **Spoofing:** giả danh nguồn gốc tuyến hoặc giả mạo peer nếu control plane chưa được bảo vệ.
- **Tampering:** thêm/sửa prefix, AS_PATH, next hop, route policy hoặc dữ liệu cho phép phát tuyến trái quy định.
- **Repudiation:** thiếu audit log và phiên bản cấu hình để xác định ai thay route/ROA.
- **Information disclosure:** lưu lượng đi qua một mạng không mong muốn có thể lộ metadata và traffic không mã hóa; không mặc định phá được TLS đúng cấu hình.
- **Denial of Service:** rút route, blackhole, tạo route churn hoặc đẩy traffic sang đường nghẽn.
- **Elevation of privilege:** tài khoản có quyền sửa BGP/ROA/cloud routes vượt phạm vi tổ chức cho phép, qua đó kiểm soát đường đi mạng.

### 8.2. Attack tree mức khái niệm

~~~mermaid
flowchart TD
    G["Mục tiêu: làm traffic tới prefix đi sai đường"] --> A{"Bề mặt bị ảnh hưởng"}
    A --> B["BGP Internet"]
    A --> C["IGP / static nội bộ"]
    A --> D["Cloud / VPN route policy"]
    B --> E["Origin không được phép"]
    B --> F["Route leak / sai export policy"]
    C --> H["Neighbor/route cấu hình trái phép"]
    D --> I["IAM hoặc route table bị sửa"]
    E --> R["RPKI ROA + ROV + prefix filter"]
    F --> S["Import/export policy + giám sát AS path"]
    H --> T["Control-plane protection + audit"]
    I --> U["Cloud IAM + change control + flow tests"]
~~~

Sơ đồ nhằm **xác định lớp bảo vệ và kiểm tra**, không phải trình tự thực hiện tấn công. Từng nhánh có điều kiện và ranh giới tin cậy khác nhau, cần đối chiếu với thiết kế mạng cụ thể.

## 9. Quy trình ứng phó khi nghi ngờ Route hijacking

Một incident routing có thể diễn biến nhanh, ảnh hưởng từng khu vực khác nhau và cần phối hợp với **ISP/transit, cloud, nhà cung cấp chống DDoS, bộ phận quản lý tài nguyên IP và nhóm ứng dụng**. Không thay đổi route hoặc ROA một cách vội vã dựa trên một dashboard đơn lẻ.

### 9.1. Bước 1 — Xác minh tín hiệu và phạm vi

Khi nhận cảnh báo:

1. **Định danh prefix:** ghi IP family, prefix, origin AS dự kiến, owner và mức quan trọng.
2. **Ghi điều quan sát được:** origin AS bất thường, more-specific prefix, route leak nghi vấn, AS_PATH khác thường, withdraw hay mất reachability?
3. **Đối chiếu nguồn độc lập:** ít nhất một hệ quan sát khác nếu có, log BGP router của mình và validator/ROV data.
4. **Xác minh thời gian:** event-time UTC, thời gian phát hiện, thay đổi route policy hoặc ROA gần nhất.
5. **Kiểm tra thay đổi hợp lệ:** migration ASN, maintenance, multihoming, CDN/anycast, DDoS mitigation hoặc update được nhà cung cấp duyệt.
6. **Xác định tác động thật:** khu vực bị ảnh hưởng, lỗi TCP/TLS, RTT, packet loss, traffic drop và chỉ số ứng dụng.

Đối với **more-specific prefix**, phải xác minh mạng quan sát có thực sự nhận tuyến con và dịch vụ nào nằm trong dải bị ảnh hưởng; không suy rằng mọi địa chỉ của prefix cha đều bị chuyển hướng.

### 9.2. Bước 2 — Phân loại nguồn và lớp lỗi

| Dấu hiệu | Giả thuyết cần kiểm tra | Bằng chứng có ích |
| --- | --- | --- |
| Origin khác danh sách duyệt, RPKI Invalid | Quảng bá origin không được phép hoặc ROA/registry lỗi | ROA snapshot, route collectors, thay đổi AS của khách hàng/đối tác |
| Origin hợp lệ nhưng path đi qua AS lạ | Traffic engineering, route leak hoặc thay đổi quan hệ BGP | AS_PATH đa vantage, import/export policy, hợp đồng provider |
| Prefix con xuất hiện đột ngột | Subprefix hijack hoặc quảng bá traffic engineering hợp lệ | Approved prefix inventory, maxLength, route filters |
| Prefix rút khỏi nhiều vùng cùng lúc | Sự cố upstream, lỗi router, policy/ROA hoặc DoS | BGP withdrawals, device health, ROA modifications, ISP status |
| Chỉ một ISP thấy tuyến lạ | Sự cố propagation cục bộ, filter hoặc policy của ISP | Looking glass của ISP, peer route, path từ nhiều vùng |
| DNS đổi IP nhưng BGP origin giữ nguyên | Có thể là DNS/ứng dụng, không phải route hijack | DNS authoritative changes, resolver log, route path đến IP mới |
| IP/TLS đúng nhưng latency tăng | Đường vòng, congestion, traffic engineering hoặc DDoS | Flow metrics, multi-region probes, AS path timeline |
| Cloud route table thay đổi, Internet BGP bình thường | Lỗi/tấn công định tuyến nội bộ cloud | Cloud IAM audit, route history, firewall and VPC flow logs |

Một **Origin Invalid** có độ ưu tiên kiểm tra cao nhưng **không tự chứng minh động cơ tấn công**. Cần liên hệ chủ prefix và các bên đang quảng bá, nhất là khi có thay đổi ROA hoặc DDoS provider.

### 9.3. Bước 3 — Giữ bằng chứng và tránh làm gián đoạn thêm

Tạo case gồm:

- Bản ghi BGP update/withdraw, prefix, AS_PATH, RPKI state và danh sách ROA tương ứng (kèm thời gian).
- Vantage points/collectors và thông tin peer, sự khác nhau giữa các mạng quan sát.
- Cấu hình prefix filters, ROV policy, ROA/IRR objects **trước và sau** thay đổi nếu có.
- Route table/RIB/FIB tại điểm được phép quan sát; trạng thái BGP sessions.
- Kết quả synthetic check ứng dụng, TLS, DNS, RTT và network flow được thu thập hợp lệ.
- Mốc thời gian/UTC, change tickets, người quản trị/đầu mối ISP, quyết định và biện pháp đã thực hiện.

Không gửi secret router, private keys hoặc dữ liệu khách hàng vào ticket công khai. Nếu báo cáo cho ISP hoặc cộng đồng vận hành, chỉ chia sẻ những trường cần để họ xác định tuyến, thời điểm và nguồn quảng bá theo quy trình.

### 9.4. Bước 4 — Phối hợp giảm thiểu đúng thẩm quyền

Tùy bằng chứng, nhóm vận hành có thể:

1. **Liên hệ upstream/peer hoặc nhà cung cấp phát tuyến bất thường** kèm prefix, ASN, thời gian và route evidence; yêu cầu kiểm tra/thu hồi tuyến sai theo trách nhiệm của họ.
2. **Xác minh ROA và IRR của chính tài nguyên mình**; sửa một cấu hình sai **nếu có quyền và có căn cứ**, không tự mở MaxLength/ASN chỉ để giải quyết nhầm.
3. **Đảm bảo xuất các tuyến hợp lệ** và import/export filter ở mạng mình đúng; xử lý route leak do chính mạng mình gây ra nếu có.
4. **Thực thi/điều chỉnh filtering ở biên do mình kiểm soát** theo chính sách đã duyệt; kiểm tra không chặn prefix/đường thiết yếu hợp lệ.
5. **Làm việc với DDoS mitigation/CDN/ISP** về phương án chuyển tuyến dự phòng khi phù hợp, bảo đảm dữ liệu ROA và quyền công bố nhất quán.
6. **Bảo vệ ứng dụng:** tiếp tục xác thực TLS/mTLS, theo dõi phiên, dữ liệu nhạy cảm và dịch vụ có thể bị ảnh hưởng.
7. **Thông báo cho các bên nội bộ** theo cấp độ: SOC, NOC, application owner, quản lý sự cố, khách hàng/đối tác nếu quy trình yêu cầu.

**Không có biện pháp "đổi một route để sửa toàn Internet" dùng chung cho mọi tình huống.** Những thay đổi quảng bá BGP sản xuất có thể gây hậu quả lan rộng và phải do người quản trị mạng có quyền thực hiện theo quy trình. Bài này không yêu cầu tạo hoặc gửi quảng bá BGP thật.

### 9.5. Bước 5 — Xác minh phục hồi và rủi ro còn lại

~~~mermaid
flowchart TD
    A["Cảnh báo origin / path bất thường"] --> B["Xác minh prefix, AS, thời gian, nhiều góc nhìn"]
    B --> C{"Có thay đổi hợp lệ được duyệt?"}
    C -- "Có" --> C1["Kiểm tra ROA/policy, cập nhật inventory và test"]
    C -- "Không hoặc chưa rõ" --> D["Tách loại origin hijack / leak / internal route"]
    D --> E["Đánh giá reachability và tác động ứng dụng"]
    E --> F["Phối hợp ISP, owner tài nguyên, NOC/SOC"]
    F --> G["Giảm thiểu được phê duyệt, bảo toàn bằng chứng"]
    G --> H{"BGP path, ROV, app probes đã ổn?"}
    H -- "Chưa" --> F
    H -- "Đã ổn" --> I["Theo dõi ổn định, rủi ro còn lại, postmortem"]
    C1 --> I
~~~

Tiêu chí phục hồi không chỉ là tuyến sai biến mất trên một collector. Cần xác minh:

- **Origin AS/prefix** và đường đi từ nhiều vantage points phù hợp với thiết kế.
- **ROV/ROA** không còn trạng thái Invalid gây mất tuyến hợp lệ.
- **Lưu lượng dịch vụ** trở về mức chấp nhận được ở những khu vực bị ảnh hưởng.
- **Không còn prefix con hoặc route leak** chưa được giải thích.
- **Các kết nối mã hóa, xác thực và ứng dụng** hoạt động đúng, không có dấu hiệu lạm dụng sau sự cố.
- **Phản ứng đã thực hiện có thể đảo ngược được** hoặc đã được ghi thành cấu hình vận hành được duyệt.

### 9.6. Sau sự cố: postmortem

Ghi root cause khi có bằng chứng (cấu hình, policy, quyền tài nguyên hay hành vi trái phép), tác động theo thời gian/khu vực, khả năng quan sát bị thiếu, chất lượng ROA/IRR/filter và những thay đổi đã phê duyệt. Nếu chưa rõ nguyên nhân, viết **"chưa xác định"**, không quy kết nhà mạng hoặc cá nhân khi thiếu dữ liệu.

Các hành động phòng ngừa thường gồm thu hẹp export/import policy, bổ sung ROA đúng, nâng cấp ROV hoặc monitoring, cải thiện IPAM/route inventory, kiểm thử failover và cập nhật đầu mối phản ứng của upstream.

## 10. Kết hợp bảo mật định tuyến với các lớp phòng vệ mạng

### 10.1. Firewall, ACL, segmentation và định tuyến

**Routing quyết định đường đi**, **firewall/ACL quyết định quyền lưu lượng ở điểm thực thi**. Route hijacking có thể làm traffic tới một đường khác **không đi qua firewall dự kiến**, nếu kiến trúc có đường bypass. Vì vậy:

- Đặt kiểm soát tại những điểm bảo vệ thật sự của mỗi trust boundary, không mặc định tất cả gói đều qua một firewall biên.
- Với phân đoạn mạng, kiểm soát east–west ở host, workload hoặc gateway phù hợp; route nội bộ sai không nên cho phép vượt quyền sang DB.
- Theo dõi **route table và security policy** cùng lúc khi một vùng bất ngờ có reachability mới.
- Đảm bảo đường phản hồi không bị lệch khỏi stateful firewall/NAT khiến phiên hợp lệ bị hỏng.
- Áp nguyên tắc default deny tại điểm thực thi, nhưng không xem default deny là đủ thay việc bảo vệ control plane.

### 10.2. VPN, BGP over tunnel và cloud hybrid

Site-to-site VPN hoặc đường private link có thể mang traffic ứng dụng và cũng có thể sử dụng BGP để trao đổi các route private. Một BGP update sai qua tunnel có thể ảnh hưởng **đường đi nội bộ**, kể cả khi đường Internet công cộng ổn định.

Ví dụ một kết nối cloud–on-prem có hai đường VPN dự phòng, nếu import route "0.0.0.0/0" không đúng dự kiến, một bên có thể chuyển nhiều traffic qua tunnel không phù hợp. Cần:

- Giới hạn **prefix import/export**, default route, ASN peer và route metric theo thiết kế.
- Xác thực và bảo vệ VPN, phiên BGP, route policy và quyền sửa cloud route tables.
- Kiểm tra IP chồng lấp/VRF và NAT policy nếu mạng hợp nhất nhiều đơn vị.
- Diễn tập **failover**, tránh đường trả lời đi khác điểm firewall/NAT dự kiến.
- Theo dõi tunnel health, BGP sessions, route changes, latency và application probes.

**RPKI ROV có mục đích chính là kiểm tra quyền origin prefix với dữ liệu ROA; không thể mặc định áp dụng trực tiếp để xác minh mọi route RFC1918 trong VPN doanh nghiệp.** Với private route, kiểm soát import/export và danh tính peer theo thiết kế là trọng tâm.

### 10.3. DNS, WAF, TLS và danh tính ứng dụng

Nếu ứng dụng báo không thể truy cập hostname, chuỗi điều tra nên phân biệt:

~~~text
Tên DNS trả địa chỉ IP nào?
  ↓
Tuyến IP đến địa chỉ đó có đúng không?
  ↓
Firewall/ACL/NAT trên đường thực tế có cho lưu lượng không?
  ↓
TLS/mTLS có xác minh hostname, certificate và peer không?
  ↓
WAF/reverse proxy/API có chấp nhận request và quyền ứng dụng không?
~~~

Trong route hijack gây chuyển hướng, **TLS đúng cấu hình** có thể giúp client phát hiện peer không phù hợp, giảm nguy cơ giả mạo dịch vụ. Tuy nhiên, điều đó không đảm bảo **khả dụng**: một kẻ gây blackhole vẫn khiến request timeout.

**Private DNS zone** không xác minh tuyến Internet; **DNSSEC** bảo vệ tính toàn vẹn DNS khi có chuỗi tin cậy phù hợp, không bảo vệ AS_PATH BGP. **WAF** kiểm tra request HTTP tại điểm traffic đi qua, không tự xác minh origin ASN. Mỗi lớp có nhiệm vụ riêng.

### 10.4. IDS/IPS, SIEM và route monitoring

IDS/IPS thường quan sát packet hoặc metadata trên mạng, SIEM có thể kết hợp **BGP/ROV alerts, DNS, firewall, flow log, VPN, WAF, cloud audit và application telemetry**:

| Chuỗi tín hiệu | Cách hiểu thận trọng |
| --- | --- |
| BGP origin thay đổi + RPKI Invalid + nhiều probe timeout | Có thể là incident routing ảnh hưởng reachability; cần xác minh ROA và change record |
| BGP origin giữ nguyên + AS_PATH thay đổi + latency tăng | Có thể route leak/traffic engineering/đường vòng; không nhất thiết origin hijack |
| Cloud route table thay đổi + VM egress đi qua appliance lạ | Cần kiểm tra IAM, thay đổi được duyệt và đường mạng thật |
| DNS record đổi IP + ứng dụng bắt đầu lỗi TLS | Có thể là lỗi DNS hoặc endpoint/proxy; cần kiểm tra BGP riêng nếu nghi |
| IPS thấy packet trên một đường, BGP collector thấy path khác | Vị trí sensor/traffic asymmetry, collector vantage và đường VPN có thể giải thích sự khác biệt |
| RPKI validator mất kết nối + số Invalid giảm mạnh | **Có thể là mất dữ liệu xác thực**, không phải chắc chắn số hijack giảm |

Khi đưa các event định tuyến vào SIEM, cần **nguồn dữ liệu đáng tin**, time synchronization, correlation ID/route key, phân quyền theo tài sản và cảnh báo sức khỏe ingest. Không tự động gọi API để đổi route hoặc khóa một AS chỉ từ dữ liệu do bên ngoài có thể ảnh hưởng.

### 10.5. Wireless và mạng người dùng

Trên Wi-Fi/ethernet người dùng, route control có thể bị ảnh hưởng bởi **DHCP gateway sai, IPv6 Router Advertisement không mong muốn, thiết bị phát quảng bá route trái phép hoặc VPN split tunneling**. Chúng khác BGP hijack Internet nhưng có cùng hậu quả "client chọn đường không mong muốn".

Các biện pháp như **NAC/802.1X, DHCP snooping, RA Guard, port security, phân đoạn mạng khách, MDM và policy VPN** có thể hỗ trợ theo công nghệ hạ tầng. Giám sát default gateway, DNS resolver và reachability từ client thực tế bổ sung cho việc chỉ giám sát BGP ở ISP.

## 11. Quản trị vòng đời prefix/ASN và cấu hình

### 11.1. Xây dựng sổ đăng ký tuyến được phép

Một bảng **routing intent** nội bộ giúp so sánh tín hiệu ngoài Internet với tình trạng được phê duyệt:

| Trường | Ý nghĩa | Ví dụ lab |
| --- | --- | --- |
| Address family / prefix | Dải địa chỉ cần bảo vệ | IPv4 203.0.113.0/24 |
| Owner / service | Ai chịu trách nhiệm và dịch vụ nào | NOC / API production |
| Approved origin ASNs | Các ASN được phép làm origin | AS64510 |
| Approved more-specifics | Có prefix con được phép không? | Không |
| ROA maxLength | Độ dài tối đa đã phê duyệt | /24 |
| Transit/peers | Nhà mạng, quan hệ và đầu mối | Provider-A / Provider-B (giả định) |
| IRR records / route policy | Dữ liệu hỗ trợ filtering | Reference nội bộ được quản lý |
| DDoS mitigation plan | Khi nào đổi origin/prefix, ai duyệt | Theo playbook và thỏa thuận |
| Monitors | Collectors, route alert, probes | NOC + SOC |
| Change ticket/version | Trạng thái thay đổi và thời hạn | RT-CHG-004 |

**Không sao chép tự động tất cả tuyến đang thấy thành allowlist**: một route bất thường đã được chấp nhận có thể trở thành "hợp lệ" trong sổ nếu làm vậy. Sổ phải dựa trên quyền tài nguyên và quyết định nghiệp vụ.

### 11.2. Quy trình thay đổi BGP/ROA có kiểm soát

1. **Yêu cầu:** prefix/ASN nào cần thay, vì sao, ai sở hữu và có bằng chứng quyền tài nguyên không?
2. **Phân tích ảnh hưởng:** IPv4/IPv6, more-specifics, ROA maxLength, IRR, prefix filtering của ISP, upstream changes, DDoS.
3. **Đánh giá security:** route leak risk, origin mismatch, thay đổi trust boundary, thay đổi cloud/VPN route nếu có.
4. **Chuẩn bị thử nghiệm:** kiểm tra dữ liệu route dự kiến bằng mô hình lab hoặc route policy simulator được phép, không phát thử prefix ra Internet.
5. **Phê duyệt:** mạng/NOC và chủ dịch vụ theo quy trình; thống nhất cửa sổ thay đổi và đầu mối liên hệ.
6. **Triển khai:** chỉ người/quy trình đã được cấp quyền thay ROA, BGP export/import policy hoặc cloud route table.
7. **Xác minh:** các vantage points thấy origin/path như dự kiến, ROV không báo Invalid cho tuyến hợp lệ, ứng dụng và HA vẫn hoạt động.
8. **Theo dõi:** route churn, latency, peer session, traffic, error rate và danh sách tuyến được công bố.
9. **Rollback:** có thay đổi đảo ngược phù hợp (khôi phục ROA/rule/route theo thiết kế) và đánh giá tác động cache/propagation.
10. **Đóng thay đổi:** ghi bản cấu hình cuối cùng, dữ liệu quan sát và các ngoại lệ cần rà soát.

### 11.3. Giới hạn của "rollback ngay"

Thông báo BGP có thể lan truyền hoặc bị rút ở các thời điểm khác nhau giữa nhiều mạng; **khôi phục cấu hình router không khiến toàn Internet lập tức hội tụ**. Với RPKI, dữ liệu xuất bản/cập nhật tới validator có độ trễ tùy kiến trúc; cần quan sát cả validator và router thực thi ROV.

Không đưa ra cam kết thời gian khắc phục tuyệt đối dựa trên TTL DNS hoặc một cấu hình timer BGP. Thời gian thực phụ thuộc chính sách, trạng thái peer và khả năng các bên hợp tác.

### 11.4. Chỉ số vận hành

| Chỉ số | Cách hiểu | Tác dụng |
| --- | --- | --- |
| Phần trăm prefix có ROA phù hợp | Coverage origin authorization đối với tài nguyên quản lý | Phát hiện prefix thiếu chứng thực hoặc sai maxLength |
| Tỷ lệ Valid/Invalid/NotFound khi quan sát route | Chất lượng dữ liệu RPKI và tuyến nhận vào | Tách Invalid thật khỏi ROA lỗi/validator hỏng |
| Thời gian từ event BGP đến alert | Detection latency | Đánh giá khả năng giám sát sớm |
| Số vantage points bị ảnh hưởng | Phạm vi quan sát | Không suy luận thành tỷ lệ người dùng bị ảnh hưởng trực tiếp |
| Tỷ lệ thay đổi origin/path có change ticket | Chất lượng quản trị | Nhận diện biến động chưa được giải thích |
| Route churn và peer flaps | Độ ổn định control plane | Phân biệt lỗi thiết bị/ISP với tấn công |
| Packet loss/latency/availability từ vùng khách hàng | Tác động data plane | Quyết định mức ưu tiên ứng phó |
| Max-prefix events / filter hits | Các tuyến bị policy phát hiện/từ chối | Hiểu độ hữu hiệu mà không mặc định tất cả là tấn công |
| Validator freshness và RTR session health | Độ tin cậy của ROV | Tránh hiểu nhầm thiếu dữ liệu thành mạng sạch |

Nên phân chia số liệu theo IPv4/IPv6, origin AS, từng provider, khu vực quan sát và mức quan trọng của dịch vụ; tổng số alert tăng không tự chứng minh bảo mật tốt hơn.

## 12. Bài thực hành offline: phát hiện prefix và origin không hợp lệ

Mục tiêu là **đọc thông báo định tuyến giả lập và phân loại rủi ro** mà không thay cấu hình router thực hay phát BGP announcements. Có thể thực hiện bằng bảng, spreadsheet nội bộ hoặc chương trình phân tích dữ liệu giả do học viên tự xây dựng; **không kết nối lab tới BGP Internet**.

### 12.1. Bối cảnh và dữ liệu được duyệt

Tổ chức lab sở hữu hai tài nguyên mô phỏng:

~~~text
IPv4: 203.0.113.0/24
  Approved origin: AS64510
  ROA: prefix=203.0.113.0/24, maxLength=24, origin=AS64510
  More-specific: chưa được phê duyệt

IPv6: 2001:db8:100::/48
  Approved origin: AS64510
  ROA: prefix=2001:db8:100::/48, maxLength=48, origin=AS64510
  More-specific: chưa được phê duyệt

Một mạng khác: 198.51.100.0/24
  Giả sử không có ROA bao phủ trong tập dữ liệu lab.
~~~

AS64510 là **origin hợp lệ**, AS64520 và AS64530 là các mạng trung gian/quan sát được phép trong tình huống, AS64566 là một ASN xuất hiện **ngoài danh sách origin đã được duyệt** của các prefix đang xét. Đây chỉ là nhãn dùng trong lab; **không kết luận một ASN thực nào là độc hại chỉ từ con số**.

### 12.2. Bộ BGP events giả lập

| ID | Thời điểm (UTC) | Prefix | Origin AS | AS_PATH nhìn thấy | Event | Góc quan sát |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | 09:00:00 | 203.0.113.0/24 | 64510 | 64520 64510 | Announce | collector-A |
| R02 | 09:03:10 | 203.0.113.0/24 | 64566 | 64530 64566 | Announce | collector-A |
| R03 | 09:03:12 | 203.0.113.0/24 | 64566 | 64520 64566 | Announce | collector-B |
| R04 | 09:03:15 | 203.0.113.0/25 | 64566 | 64530 64566 | Announce | collector-A |
| R05 | 09:04:00 | 203.0.113.0/24 | 64510 | 64520 64566 64510 | Announce | collector-B |
| R06 | 09:05:00 | 198.51.100.0/24 | 64520 | 64530 64520 | Announce | collector-A |
| R07 | 09:06:00 | 2001:db8:100::/48 | 64510 | 64520 64510 | Announce | collector-A |
| R08 | 09:06:10 | 2001:db8:100::/49 | 64510 | 64520 64510 | Announce | collector-A |
| R09 | 09:08:00 | 203.0.113.0/24 | 64566 | — | Withdraw | collector-A |
| R10 | 09:09:00 | 203.0.113.0/24 | 64510 | 64530 64510 | Announce | collector-A |

Với **Withdraw**, không cần diễn giải trường origin AS như một chứng thực mới. Thông báo rút tuyến cho NLRI tương ứng từ góc nhìn peer/collector, và thực tế BGP route withdrawal không nhất thiết mang một AS_PATH. Cột origin ở R09 chỉ là **nhãn của tuyến quan sát trước đó** được gắn vào sự kiện tổng hợp cho mục đích phân tích, không phải thuộc tính của packet UPDATE withdrawal thật.

### 12.3. Phân loại theo RPKI và ngữ cảnh

| Event | Trạng thái origin với tập ROA lab | Đánh giá ban đầu |
| --- | --- | --- |
| R01 | **Valid** | Tuyến gốc phù hợp, cần lưu baseline |
| R02 | **Invalid** | Origin không khớp ROA; cần điều tra, không khẳng định chủ ý |
| R03 | **Invalid** | Củng cố bằng chứng nhiều mạng đã quan sát origin lạ |
| R04 | **Invalid** | Origin sai và prefix /25 vượt maxLength /24; nhiều mạng có thể lọc /25 |
| R05 | **Valid** theo origin | AS_PATH có AS64566 bất thường; ROV không kết luận path hợp lệ về quan hệ |
| R06 | **NotFound** | Không có ROA bao phủ trong dữ liệu lab; không có nghĩa tuyến chắc chắn an toàn |
| R07 | **Valid** | IPv6 /48 khớp ROA |
| R08 | **Invalid** | Origin đúng nhưng /49 vượt maxLength /48 |
| R09 | **Không áp ROV như một announcement mới** | Theo dõi việc rút tuyến ở observer A, không suy tất cả mạng đã hội tụ |
| R10 | **Valid** | Origin trở lại được phép ở observer A, nhưng cần xác minh các tuyến khác và ảnh hưởng ứng dụng |

**Hai bài học quan trọng**:

1. **R05** có origin phù hợp ROA nhưng đường AS có một điểm đáng xem xét. ROV không xác minh toàn bộ AS_PATH; cần dữ liệu quan hệ BGP, route collectors và đối tác để kết luận liệu đây có phải route leak hoặc thao túng path.
2. **R09** không chứng minh tuyến R02 đã bị rút ở mọi nơi. Mỗi collector chỉ thấy các update theo peer/góc nhìn của nó, và có thể có nhiều đường thay thế trong mạng.

### 12.4. Pseudo-code kiểm tra trạng thái origin

Đây là giải thích logic **ở mức giáo dục**, không phải một bộ RPKI validator đầy đủ:

~~~text
function validate_origin(route, validated_roas):
    covering = []
    for roa in validated_roas:
        if same_address_family(roa.prefix, route.prefix)
           and route.prefix is_inside roa.prefix:
            covering.append(roa)

    if covering is empty:
        return "NotFound"

    for roa in covering:
        if route.origin_asn == roa.authorized_origin_asn
           and route.prefix_length <= roa.max_length:
            return "Valid"

    return "Invalid"
~~~

Thuật toán giả định tất cả ROA đầu vào đã được **kiểm tra chữ ký/chuỗi chứng thực và hiệu lực**. Hệ thống thực phải xử lý ASN/prefix ở dạng đúng, dữ liệu publication, cache, expiry, các đặc điểm RPKI protocol và những trường hợp ngoại lệ; không dùng pseudo-code này để điều khiển router sản xuất.

### 12.5. Bài tập longest prefix match

Giả sử một router lab có cả hai tuyến đã cài đặt:

~~~text
203.0.113.0/24 -> next-hop LEGIT
203.0.113.0/25 -> next-hop UNKNOWN
~~~

Hãy xác định FIB sẽ chọn tuyến nào:

| IP đích | Tuyến phù hợp hơn | Lý do |
| --- | --- | --- |
| 203.0.113.5 | 203.0.113.0/25 | IP nằm trong /25, dài hơn /24 |
| 203.0.113.127 | 203.0.113.0/25 | Địa chỉ cuối thuộc /25 đầu |
| 203.0.113.128 | 203.0.113.0/24 | Không thuộc /25 đầu |
| 203.0.113.250 | 203.0.113.0/24 | Không thuộc /25 đầu |
| 198.51.100.10 | Không có tuyến trên khớp | Cần kiểm tra route khác/default route |

Giả định cả /24 và /25 **đã được policy cho phép và cài vào FIB**. Nếu router lọc /25 hoặc nó không được chọn/cài, kết quả thực tế sẽ khác. Không dùng bảng này để suy rằng tuyến hijack chắc chắn được lan truyền trên Internet.

### 12.6. Các kịch bản kiểm thử phát hiện

| Test | Dữ liệu/điều kiện giả | Kết quả mong đợi |
| --- | --- | --- |
| L01 | R01 với ROA khớp | Valid, không tạo incident origin mismatch |
| L02 | R02 và R03, hai collectors độc lập | Gộp một case origin bất thường, giữ cả hai raw IDs |
| L03 | R04 prefix con không được duyệt | More-specific alert + RPKI Invalid |
| L04 | R05 AS_PATH thay đổi, origin vẫn Valid | Route-path anomaly cần review; không ghi "RPKI Invalid" |
| L05 | R06 không có ROA bao phủ | NotFound; chính sách xử lý riêng, không đổi thành Valid |
| L06 | R08 /49 quá maxLength | Invalid dù origin AS đúng |
| L07 | R09 withdraw tại collector-A | Đánh dấu first/last seen đúng góc quan sát, không tự đóng toàn bộ case |
| L08 | Router ROV cache mất dữ liệu | Cảnh báo pipeline health, không tự coi số Invalid giảm là giảm sự cố |
| L09 | Đổi origin hợp lệ theo change ticket có phê duyệt | Kiểm tra ROA/filter/route inventory trước; gắn thay đổi hợp lệ sau khi xác minh |
| L10 | Event R02 bị collector retry hai lần | Dedup event, không nhân đôi mức ảnh hưởng |
| L11 | Cùng prefix nhưng IPv4/IPv6 khác | Không ghép nhầm address family |
| L12 | Event time 09:03 nhưng ingest vào 09:08 | Correlation dựa trên event time, lưu ingest latency |

### 12.7. Câu hỏi điều tra sau lab

Từ R02–R10, viết bản báo cáo không quá một trang với:

- Prefix và ASN được phê duyệt trong nguồn dữ liệu giả.
- Các tuyến nào Invalid/Valid/NotFound và vì sao.
- Có bao nhiêu collector nhìn thấy origin bất thường, trong khoảng thời gian nào.
- Địa chỉ đích nào sẽ bị ảnh hưởng nếu /25 được nhận/cài vào FIB.
- Dữ liệu **chưa có** để kết luận impact thật: BGP best path tại khách hàng, route filtering, flow/application metrics, nguồn/ý định phát route.
- Playbook cần liên hệ ai, cung cấp bằng chứng gì và kiểm chứng phục hồi bằng cách nào.

Điểm đạt là **phân biệt observation với conclusion** và không đưa ra lệnh BGP quảng bá/thu hồi thật khi chỉ có dataset mô phỏng.

## 13. Trường hợp đặc biệt: multihoming, anycast, mitigation và IPv6

### 13.1. Multihoming không đồng nghĩa nhiều origin ASN

Một công ty có thể kết nối **nhiều transit providers**, nhưng vẫn tự công bố prefix bằng **cùng một ASN origin**. Hai AS_PATH khác nhau từ hai upstream hoàn toàn có thể là **hoạt động hợp lệ**, nên thay đổi đường đi không đủ kết luận hijack.

Nếu có hai origin AS hợp lệ vì thiết kế chuyển đổi hoặc nhiều miền điều hành, cần kiểm kê và chứng thực phù hợp. Không tạo ROA cho ASN của mọi transit provider chỉ vì chúng xuất hiện trên AS_PATH.

### 13.2. Anycast và quảng bá từ nhiều địa điểm

**Anycast** sử dụng cùng prefix để phục vụ từ nhiều vị trí; BGP có thể dẫn người dùng đến một vị trí có đường đi phù hợp theo policy. Việc lượng traffic dịch chuyển giữa các vùng có thể do bảo trì hoặc thay đổi định tuyến hợp lệ.

Tuy nhiên, mọi site/đối tác được phép công bố phải có **origin và policy phù hợp**, được xác định trong tài liệu khai thác. Monitoring cần hiểu các vùng anycast và những thay đổi chấp nhận được, nhưng vẫn cảnh báo khi prefix bị origin ASN chưa được duyệt công bố.

### 13.3. DDoS mitigation, scrubbing và blackhole community

Trong sự cố DDoS, tổ chức có thể dùng dịch vụ scrubber, route diversion có kiểm soát hoặc cơ chế **remotely triggered black hole (RTBH)** theo thỏa thuận. Những thay đổi route cộng với sự gián đoạn có thể trông giống hijack trong dashboard.

Khi thiết kế cần:

- Văn bản hóa **prefix/ASN và điều kiện công bố được phép** cho nhà cung cấp.
- Kiểm tra tương thích ROA, prefix filter và chính sách chấp nhận tuyến của upstream.
- Chỉ dùng community đặc biệt theo **đúng hợp đồng và giới hạn**, quản lý quyền kích hoạt.
- Cảnh báo khi mitigation kích hoạt ngoài playbook hoặc kéo dài ngoài khoảng thời gian được phê duyệt.
- Phân biệt traffic chủ động bị blackhole để bảo vệ hệ thống với đường đi bị chiếm dụng trái phép.

Không mặc định **origin ASN của scrubber phải khác origin thường ngày**; kiến trúc dịch vụ quyết định. Cần xác minh với bên cung cấp trước khi tạo ROA hoặc thay policy.

### 13.4. IPv6 và phạm vi kiểm soát riêng

IPv6 có prefix và maxLength khác IPv4; một tổ chức bảo vệ **203.0.113.0/24** bằng ROA không tự bảo vệ **2001:db8:100::/48**. Cần:

1. Inventory prefix IPv6 được cấp và quảng bá.
2. ROA/ROV và prefix filters riêng cho IPv6.
3. Monitoring route collector có khả năng quan sát IPv6.
4. Kiểm tra DNS AAAA, ứng dụng dual-stack và đường kết nối thực.
5. Chính sách xử lý more-specific IPv6 theo vận hành đối tác; không giả định mọi peer chấp nhận prefix dài hơn /48.

Một dịch vụ có thể vẫn hoạt động qua IPv4 trong khi khách hàng ưu tiên IPv6 bị ảnh hưởng bởi route bất thường; kiểm tra cả hai address families khi xử lý sự cố.

## 14. Case study: điều tra một cảnh báo origin-AS bất thường

Giả sử tại thời điểm 09:03 UTC, hệ thống của tổ chức quản lý **203.0.113.0/24** nhận:

- Một collector thấy route **203.0.113.0/24 origin AS64566**.
- Validator báo **Invalid** theo ROA 203.0.113.0/24 origin AS64510 max24.
- Collector thứ hai thấy origin AS64566 sau 2 giây.
- Probe từ vùng A timeout, vùng B vẫn trả HTTPS thành công.
- Route monitoring thấy thêm **203.0.113.0/25** ở một vantage point.
- Không tìm thấy change ticket cho origin mới hoặc more-specific prefix.

### 14.1. Xây dựng giả thuyết và kiểm chứng

| Giả thuyết | Bằng chứng hỗ trợ | Điều cần kiểm tra trước khi kết luận |
| --- | --- | --- |
| Origin hijack / misorigination | Origin không được duyệt, RPKI Invalid, nhiều góc quan sát | Liên hệ owner và ISP; có chuyển đổi hợp lệ chưa được cập nhật không? |
| More-specific diversion | /25 bất thường xuất hiện | Mạng vùng A có nhận/cài /25 không, vùng bị ảnh hưởng có nằm trong /25 không? |
| Route leak | AS_PATH có sự xuất hiện AS bất thường | Origin và quan hệ import/export; RPKI Valid không chứng minh không leak |
| Lỗi DNS | Một khu vực HTTPS timeout | DNS có trả cùng IP không, có A/AAAA khác nhau không? |
| Lỗi backend | Probe chỉ một khu vực hỏng | App/edge health, TLS, firewall/flow logs, latency |
| Thay đổi được duyệt | Không thấy ticket | Kiểm tra owner, mitigation provider, cập nhật thông tin thay đổi muộn |

### 14.2. Kết luận tạm thời phù hợp

Có **các quảng bá origin không khớp ROA được quan sát từ nhiều điểm**, kèm dấu hiệu **reachability suy giảm ở một khu vực**. Đây là **sự kiện routing đáng điều tra khẩn cấp**, chưa đủ để khẳng định ai có ý định tấn công, traffic đã bị đọc hay dữ liệu đã rò rỉ.

SOC/NOC nên lưu bằng chứng, liên hệ upstream và chủ tài nguyên, kiểm tra route export/ROA của mình, đánh giá đường đi của các khu vực và triển khai biện pháp đã được phê duyệt. Nếu có dấu hiệu dịch vụ bị truy cập qua endpoint trái phép, nhóm ứng dụng tiếp tục đánh giá log TLS/xác thực/dữ liệu.

### 14.3. Xác minh sau khi ISP sửa tuyến

Một collector không còn thấy AS64566 nhưng collector khác vẫn còn. Điều này có thể do thời gian hội tụ, lọc từng mạng, cập nhật chậm hoặc tuyến vẫn tồn tại tại góc khác. Không đóng case ngay.

Để xác nhận phục hồi:

- Quan sát đúng origin trên các collector đại diện.
- Không còn quảng bá /25 không được duyệt tại các điểm có thể quan sát.
- Probes ở vùng A/B và các khu vực bị ảnh hưởng hoạt động lại.
- Không có RPKI Invalid mới đối với các tuyến hợp lệ của tổ chức.
- Lỗi ứng dụng/network trở về baseline chấp nhận được.
- Đầu mối ISP xác nhận xử lý và các cấu hình tạm thời đã được rà soát.

## 15. Checklist rà soát bảo mật định tuyến

### 15.1. Quyền tài nguyên và RPKI

- [ ] Có inventory đầy đủ prefix IPv4/IPv6, ASN, owner, service và đối tác được phép công bố.
- [ ] ROA phản ánh đúng prefix, **origin ASN và MaxLength**; không mở maxLength rộng không có lý do.
- [ ] Những trường hợp multihoming, anycast, DDoS mitigation và chuyển ASN có tài liệu/chấp thuận.
- [ ] Theo dõi ngày/hiệu lực dữ liệu RPKI, tình trạng validator/cache và các kết nối đến router.
- [ ] Có quy trình sửa ROA lỗi trước khi triển khai ROV chặn Invalid gây ảnh hưởng tuyến hợp lệ.
- [ ] Có nguồn giám sát origin và more-specific prefix từ nhiều góc quan sát.

### 15.2. BGP policies và control plane

- [ ] Mỗi peer có quan hệ/ASN rõ ràng, danh sách prefix/route policy nhập–xuất phù hợp.
- [ ] Export policy không phát route học từ provider/peer ra bên khác ngoài thỏa thuận.
- [ ] Nhận tuyến customer được kiểm soát bằng prefix/ASN policy, IRR/RPKI theo khả năng.
- [ ] Có prefix-length policy và max-prefix phù hợp IPv4/IPv6; không gây chặn vô tình các tuyến cần thiết.
- [ ] Peer session có biện pháp bảo vệ control plane, quản trị router và logging.
- [ ] Community đặc biệt/RTBH hoặc thao tác DDoS có ranh giới quyền, owner và quy trình kiểm soát.
- [ ] Route configuration changes được lưu phiên bản, review, có audit và phương án rollback.

### 15.3. Định tuyến nội bộ, cloud và hybrid

- [ ] Mạng on-prem/IGP có xác thực neighbor và bảo vệ điểm truy cập quản trị theo giao thức/thiết bị.
- [ ] Cloud route tables, VPN BGP và VRF import/export policy dùng IAM/ACL đúng phạm vi.
- [ ] Không tạo đường bypass firewall/segmentation ngoài ý định khi thay next hop hoặc tunnel.
- [ ] Kiểm tra các route 0.0.0.0/0 và ::/0 cùng việc quảng bá/nhận default route theo hợp đồng.
- [ ] Đường trả lời của traffic stateful/NAT vẫn đi đúng điểm thực thi khi failover.
- [ ] Các mạng người dùng/wi-fi được bảo vệ khỏi gateway/RA/DHCP không được cấp quyền ở phạm vi phù hợp.

### 15.4. Giám sát và ứng phó

- [ ] Có alert **unexpected origin**, **more-specific**, **path change**, **route leak suspicion**, **ROA/ROV drift** và mất telemetry.
- [ ] Event chứa prefix, address family, ASN, AS_PATH, observer, timestamp, RPKI state, owner và link raw logs.
- [ ] So sánh sự kiện với **approved origin inventory**, change calendar và tình trạng DDoS mitigation.
- [ ] Có active probes TCP/TLS và application tests từ các vùng khách hàng quan trọng.
- [ ] SOC/NOC có đầu mối liên hệ ISP/peer và chủ tài nguyên, mẫu bằng chứng được chuẩn bị.
- [ ] Biện pháp tự động hóa không thay route/chặn ASN ngoài phạm vi được duyệt.
- [ ] Sau incident có postmortem, đánh giá blind spots, rủi ro còn lại và cập nhật filter/ROA.

## 16. Bài tập thiết kế và câu hỏi ôn tập

### 16.1. Đề bài tổng hợp

Một doanh nghiệp có:

- Prefix public IPv4/IPv6 và AS origin riêng.
- Hai đường transit BGP, một kết nối VPN BGP tới cloud và các mạng VPC/VNet production.
- Dịch vụ API dùng WAF/reverse proxy, DNS public và private DNS cho backend.
- Firewall phân đoạn giữa Web, Application và Database.
- NIDS/IPS giám sát biên, SIEM thu sự kiện BGP, DNS, firewall và ứng dụng.
- Một hợp đồng DDoS mitigation có thể thay đổi cách quảng bá prefix theo quy trình.

Hãy xây dựng một thiết kế **phòng vệ và giám sát Route hijacking** gồm:

1. **Sơ đồ mạng** chỉ rõ AS, BGP peer, tuyến public, VPN, trust boundaries, firewall, WAF, DNS, SIEM và vùng dữ liệu.
2. **Inventory prefix/ASN** và ROA dự kiến với maxLength, cả IPv4 và IPv6; giải thích vì sao các giá trị là tối thiểu cần thiết.
3. **Import/export policy** cho hai transit và cloud VPN; chỉ rõ route nào không được phát sang bên khác.
4. **Bảng dấu hiệu cảnh báo** cho unexpected origin, more-specific, route leak và thay đổi route nội bộ trái phép.
5. **Bộ dữ liệu synthetic** gồm ít nhất một Valid, một Invalid do origin, một Invalid do maxLength, một NotFound và một route leak có origin Valid.
6. **Phép kiểm chứng** ở control plane và data plane, với ít nhất ba vantage points và các dịch vụ có mức quan trọng khác nhau.
7. **Playbook ứng phó** có phân loại tình trạng, đầu mối upstream, phương án giữ bằng chứng và rollback.
8. **Biện pháp ứng dụng** để giảm tác hại khi đường đi bị chuyển sai: TLS/mTLS, authentication/authorization, high availability và kết nối dự phòng.

**Tiêu chí tự đánh giá:** Không lẫn lộn RPKI Valid với AS_PATH an toàn; không coi prefix con mặc nhiên được nhận ở mọi mạng; phân biệt origin hijack và route leak; không phát tuyến thử ra Internet; có phép thử kiểm chứng và trách nhiệm sở hữu rõ ràng.

### 16.2. Câu hỏi ôn tập

**Câu 1.** Route hijacking khác DNS hijacking thế nào?

*Gợi ý:* Route hijacking ảnh hưởng tuyến IP/next hop tới địa chỉ mạng; DNS hijacking ảnh hưởng câu trả lời tên → IP. Hai lớp có thể cùng bị tác động nhưng cần bằng chứng khác nhau.

**Câu 2.** Tại sao khi router có 203.0.113.0/24 và 203.0.113.0/25 trong FIB thì đích 203.0.113.42 thường chọn /25?

*Gợi ý:* Longest prefix match ưu tiên tuyến cụ thể hơn **nếu cả hai đã được cài đặt**. Điều đó khác quá trình BGP chọn best path cho cùng một prefix.

**Câu 3.** RPKI ROA gồm những trường nào quan trọng đối với ROV?

*Gợi ý:* Prefix, origin ASN được phép, MaxLength và tính hợp lệ của đối tượng chứng thực.

**Câu 4.** ROA 203.0.113.0/24, AS64510, maxLength 24. Quảng bá 203.0.113.0/25 origin AS64510 có trạng thái gì theo tập ROA chỉ gồm ROA này?

*Gợi ý:* **Invalid**, vì /25 vượt maxLength /24 dù ASN đúng.

**Câu 5.** "RPKI NotFound" có nghĩa là tuyến không nguy hiểm và đã được xác thực?

*Gợi ý:* Không. Không có ROA bao phủ để xác minh origin, cần chính sách và bằng chứng bổ trợ.

**Câu 6.** Vì sao một route leak có thể RPKI Valid?

*Gợi ý:* Origin ASN có thể đúng ROA, nhưng AS trung gian vẫn quảng bá route sang quan hệ không được phép; ROV không xác minh toàn bộ export policy hoặc đường AS.

**Câu 7.** Xác thực BGP peer bằng cơ chế bảo mật phiên có thay thế prefix filtering không?

*Gợi ý:* Không. Một peer hợp lệ vẫn có thể quảng bá prefix sai do lỗi cấu hình hoặc bị chiếm quyền.

**Câu 8.** Một hệ giám sát BGP thấy origin mới, trong khi ứng dụng vẫn trả HTTP 200. Có thể đóng cảnh báo không?

*Gợi ý:* Chưa đủ. Traffic có thể đi qua đường không mong muốn mà vẫn đến dịch vụ, hoặc chỉ một số mạng/địa chỉ bị ảnh hưởng. Cần xem ROA, owner, route policy và các góc quan sát.

**Câu 9.** Vì sao không thể kết luận mọi mạng bị ảnh hưởng khi hai collectors thấy cùng một tuyến bất thường?

*Gợi ý:* Mỗi AS có filter, policy, góc quan sát và tuyến được chọn khác nhau; collectors không đại diện tất cả khách hàng.

**Câu 10.** Một tổ chức có hai ISP thì có cần tạo ROA cho ASN của cả hai ISP không?

*Gợi ý:* Không mặc định. Nếu doanh nghiệp tự làm origin AS, các ISP chỉ làm transit trong AS_PATH. Chỉ thêm origin ASN khi nó thật sự được phép phát prefix theo mô hình dịch vụ.

**Câu 11.** ROV phát hiện chính xác mọi trường hợp quảng bá tuyến trái phép không?

*Gợi ý:* Không. ROV chỉ xét origin theo ROA; không bảo đảm AS_PATH đúng hoặc route leak không xảy ra, và chỉ phát huy khi mạng thực thi policy phù hợp.

**Câu 12.** Route hijack có đồng nghĩa đối tượng tấn công giải mã được TLS không?

*Gợi ý:* Không. TLS/certificate/hostname validation vẫn bảo vệ nội dung và xác thực peer khi được triển khai đúng; availability vẫn có thể bị ảnh hưởng.

**Câu 13.** Khi prefix đột nhiên RPKI Invalid sau khi đổi DDoS mitigation provider, nên làm gì trước?

*Gợi ý:* Đối chiếu prefix, origin ASN theo hợp đồng, ROA/MaxLength, route policy và change ticket; điều tra bản ghi sai thay vì tắt ROV hoặc mở ROA quá rộng vô điều kiện.

**Câu 14.** Vì sao cần giám sát IPv6 riêng?

*Gợi ý:* Prefix/ROA/prefix length/route propagation và đường ứng dụng IPv6 có thể khác IPv4; IPv4 control không tự bao phủ AAAA hoặc tuyến IPv6.

**Câu 15.** Khi NOC nhận cảnh báo BGP origin mismatch, bằng chứng nào nên được lưu đầu tiên?

*Gợi ý:* Prefix, origin/path, RPKI state và ROA snapshot, observer/peer, thời điểm, logs/config changes và kết quả probe; phân biệt bằng chứng quan sát với đánh giá ý định.

## 17. Tổng kết

- **Route hijacking** là nguy cơ một prefix hoặc đường đi IP bị quảng bá/điều khiển trái quyền, gây blackhole, chuyển hướng hay suy giảm mạng. **Route leak** thường liên quan **sai quan hệ export/import** và có thể xảy ra với origin hợp lệ.
- **Longest prefix match** giải thích tác động của subprefix khi tuyến được chấp nhận và cài vào FIB; không có bảo đảm một prefix con sẽ được mọi mạng trên Internet chấp nhận.
- **RPKI ROA xác định origin AS và MaxLength được phép; ROV phân loại Valid, Invalid, NotFound.** ROV không xác minh toàn bộ AS_PATH, không thay import/export policy và không có hiệu lực trên router chưa áp filtering phù hợp.
- **ROA và prefix/ASN inventory chính xác** là điều kiện quan trọng: ROA sai có thể làm mạng ROV từ chối tuyến hợp lệ; các kế hoạch multihoming, anycast, chuyển ASN và DDoS phải được cập nhật có kiểm soát.
- **Phòng vệ nhiều lớp** gồm prefix filtering, ROV, quan hệ BGP, bảo vệ peer/control plane, quản trị router, route policy nội bộ/cloud/VPN và network segmentation.
- **Giám sát có ngữ cảnh** kết hợp BGP updates từ nhiều vantage points, ROA/IRR, route policy, DNS, flow logs, TLS/API probes và SIEM. Một thay đổi đường đi không tự chứng minh dữ liệu đã bị đánh cắp hoặc tấn công đã thành công.
- **Ứng phó phải phân biệt origin hijack, route leak và lỗi cấu hình**, giữ bằng chứng, liên hệ đúng chủ tài nguyên/ISP, kiểm tra tác động thật và xác minh phục hồi tại nhiều mạng.
- **Bài tập an toàn nhất cho người học** là phân tích dữ liệu routing giả lập/offline, tạo chính sách theo ý định và viết playbook; mọi thay đổi quảng bá định tuyến ngoài mạng lab phải tuân theo thẩm quyền quản trị và quy trình vận hành.
