# Monitoring thiết bị lạ trong mạng không dây

**Monitoring thiết bị lạ** là quá trình quan sát, đối chiếu danh tính và phân loại các điểm truy cập (**Access Point, AP**) hoặc thiết bị đầu cuối (**station/client**) được phát hiện trong môi trường Wi-Fi để nhận ra những thành phần **chưa được cấp quyền, không rõ chủ sở hữu hoặc có hành vi rủi ro**. Đối tượng quan sát không chỉ là thiết bị đã kết nối thành công vào WLAN của tổ chức: một AP giả danh, AP không được quản lý cắm vào mạng nội bộ, thiết bị khách liên tục thử xác thực, điện thoại bật hotspot hoặc thiết bị IoT dùng sai vùng mạng đều có thể cần đánh giá.

Bài học thuộc chương **Wireless security** của module **SECURITY_NETWORK_SECURITY**, gắn với phòng vệ nhiều lớp từ phân đoạn mạng, firewall, VPN, IDS/IPS và xác thực kết nối đến bảo vệ DNS, mạng không dây và hạ tầng cloud. Trọng tâm là biết phân tích tín hiệu vô tuyến và log kết nối, mô hình hóa mối đe dọa, giám sát xâm nhập và xây dựng kiến trúc mạng an toàn. **Phát hiện thiết bị lạ không đồng nghĩa thiết bị đó độc hại**: một mạng Wi-Fi của hàng xóm, thiết bị cá nhân được phép hoặc MAC được hệ điều hành thay đổi có thể xuất hiện trong dữ liệu mà không phải sự cố.

**Nguyên tắc an toàn:** chỉ thực hiện kiểm kê, đo đạc, thu thập gói và phản ứng trên hạ tầng do tổ chức quản lý hoặc được cấp quyền; không gây nhiễu sóng, phát frame ngắt kết nối, đánh chiếm AP của người khác hoặc truy cập vào thiết bị bên ngoài phạm vi. Bài thực hành sử dụng sự kiện và định danh giả lập, không cần thử kỹ thuật tấn công trên Wi-Fi thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **rogue AP**, **evil twin**, **neighbor AP**, **unauthorized client**, **BYOD chưa đăng ký**, **IoT lạ** và một hotspot được cấp quyền.
2. Hiểu những gì cảm biến WIDS/WIPS nhìn thấy từ **beacon, probe, association và tín hiệu vô tuyến**, cùng các giới hạn trong giám sát.
3. Thiết kế luồng telemetry từ **wireless controller/AP, RF sensor, RADIUS/802.1X, NAC, switch, DHCP, DNS, firewall, EDR và SIEM** để xác định thiết bị và phạm vi truy cập.
4. Giải thích vì sao **SSID, BSSID/MAC, RSSI, vendor OUI hoặc vị trí dự đoán** không đủ để kết luận danh tính, nhất là khi MAC randomization và nhiều radio cùng hoạt động.
5. Xây dựng quy tắc cảnh báo theo rủi ro, phân biệt **thiết bị chưa biết** với **thiết bị đã vượt ranh giới tin cậy**.
6. Thiết kế quy trình điều tra, xác minh chủ sở hữu, xử lý an toàn và khôi phục mà không gây gián đoạn mạng lân cận.
7. Kiểm tra hiệu quả phát hiện bằng dữ liệu tổng hợp và ma trận **true positive, false positive, false negative, telemetry gap**.
8. Quản lý inventory, quyền truy cập log, cảnh báo sức khỏe cảm biến và quy trình thay đổi cho WLAN doanh nghiệp.

## 2. Thế nào là một thiết bị Wi-Fi "lạ"?

Một thiết bị là **unknown** khi hệ thống chưa liên kết được nó với inventory/identity đáng tin tại thời điểm quan sát. Một thiết bị là **unauthorized** khi không có quyền sử dụng một tài nguyên hoặc chức năng cụ thể. **Suspicious** có nghĩa là tín hiệu/hành vi cần điều tra; **confirmed malicious** chỉ nên dùng khi đã có bằng chứng đủ cho kết luận theo quy trình ứng cứu.

| Nhóm phát hiện | Mô tả | Nguy cơ có thể có | Điều phải xác minh |
| --- | --- | --- | --- |
| **Managed AP** | AP được tổ chức quản lý, có inventory và chứng thực phù hợp | Thiết bị bị cấu hình sai hoặc tài khoản quản trị bị lạm dụng vẫn có thể rủi ro | Serial/controller ID, site, firmware, config, cổng uplink |
| **Rogue AP** | AP hoạt động không được phê duyệt, đặc biệt nếu nối vào mạng nội bộ được bảo vệ | Tạo đường vào WLAN bỏ qua NAC, policy hoặc phân đoạn | Có **kết nối wired/bridged tới mạng nội bộ thật không**, ai sở hữu |
| **Evil twin / impersonating AP** | AP phát tên hoặc đặc điểm khiến người dùng nhầm với mạng hợp lệ | Dẫn client kết nối nhầm; rủi ro thu thập thông tin hoặc trung gian tùy bảo vệ client | SSID, loại security, BSSID, chứng thực máy chủ, client association, quan sát đa nguồn |
| **Neighbor AP** | Wi-Fi của văn phòng/hộ dân lân cận nằm trong vùng thu sóng | Thường không phải incident; có thể ảnh hưởng kênh hoặc gây nhầm | Không thuộc mạng dây tổ chức, chủ sở hữu và chính sách địa điểm |
| **Personal hotspot / tethering** | Điện thoại/thiết bị tạo AP để chia sẻ kết nối | Có thể bỏ qua đường egress/DNS công ty nếu người dùng kết nối | Có được chính sách cho phép không; client thực sự kết nối nơi nào |
| **Unauthorized client / station** | Client thử hoặc đã kết nối vào WLAN không được cấp quyền | Truy cập sai VLAN, dùng credential không phù hợp, thiết bị chưa quản lý | RADIUS outcome, NAC posture, SSID, VLAN, session, identity |
| **BYOD chưa đăng ký** | Thiết bị cá nhân xuất hiện nhưng chưa được gắn quy trình chủ sở hữu | Truy cập chưa phân loại; không nhất thiết độc hại | Quy định BYOD, guest onboarding, MDM/endpoint posture |
| **IoT/OT không kiểm kê** | Camera, máy in, thiết bị hội nghị, cảm biến, thiết bị công nghiệp phát hiện mới | Firmware cũ, mật khẩu yếu, khả năng di chuyển ngang | Asset owner, loại thiết bị, vị trí, vùng mạng, nhu cầu kết nối |
| **Thiết bị được cấp phép tạm thời** | AP/sensor/thiết bị khách cho sự kiện, kiểm thử, nhà thầu | Có thể bị báo nhầm khi thiếu dữ liệu thay đổi | Ticket, thời hạn, vùng và kết nối được phép |
| **Thiết bị không xác định vì mất dữ liệu** | Có MAC/SSID nhưng thiếu association hoặc log controller | Phân loại sai do telemetry gap | Coverage, timestamp, nguồn quan sát, tình trạng collector |

**Một SSID giống tên công ty không đủ chứng minh đó là evil twin**, vì nhiều tổ chức cùng dùng tên như "Guest". Ngược lại, một AP có SSID khác tên công ty nhưng cắm vào cổng Ethernet nội bộ có thể là **rogue AP nghiêm trọng hơn** một AP giả tên đang ở ngoài phạm vi mạng dây.

### 2.1. Ba câu hỏi phân loại quan trọng nhất

1. **Thiết bị nào?** Có thể gắn observation với inventory, credential, radio/BSSID, serial hoặc tài khoản nào không?
2. **Thiết bị đang ở đâu và kết nối tới gì?** Chỉ được thu sóng trong không gian hay đã liên kết với switch/VLAN/SSID, truy cập VPN, DNS, ứng dụng và dữ liệu nội bộ?
3. **Có được cấp quyền cho hành động đó không?** Một thiết bị được phép vào Guest WLAN vẫn không mặc nhiên được phép vào hệ thống quản trị hoặc mạng sản xuất.

Thay vì gán trạng thái "an toàn/nguy hiểm" cố định cho một địa chỉ MAC, hãy xác định **identity + thời điểm + mạng/vùng + hoạt động + chứng cứ**.

## 3. Tín hiệu kỹ thuật của Wi-Fi dùng để phát hiện

### 3.1. AP, SSID, BSSID và radio

- **SSID:** tên mạng Wi-Fi mà người dùng thường thấy, không phải bằng chứng danh tính hay sở hữu. Nhiều AP phát cùng SSID để hỗ trợ roaming.
- **BSSID:** định danh của một basic service set trong kiến trúc 802.11; thường biểu diễn dưới dạng địa chỉ MAC và có thể liên quan tới từng radio/virtual AP. **Một thiết bị vật lý có thể có nhiều BSSID**.
- **Station/client MAC:** địa chỉ lớp liên kết phía client quan sát trong kết nối; có thể được thay đổi/ngẫu nhiên hóa.
- **Radio/channel/band:** xác định phạm vi thu phát, chẳng hạn 2,4 GHz, 5 GHz, 6 GHz ở hệ thống hỗ trợ.
- **AP name/controller ID/serial:** metadata quản trị đáng tin hơn SSID/BSSID khi lấy từ controller/inventory đã được kiểm soát.
- **RSSI/SNR:** chỉ số cường độ/tỷ số tín hiệu trên một điểm thu; hữu ích phân tích vùng phủ nhưng không trực tiếp chứng minh vị trí vật lý hay khoảng cách chính xác.

Ví dụ một AP hợp lệ có hai BSSID được controller quản lý:

~~~text
Inventory device: AP-HN-F3-014
Controller ID:     wlc-prod-01
Serial:            LAB-AP-014
Site:              Floor-3
Corporate BSSID:   02:1A:2B:3C:40:10
Guest BSSID:       02:1A:2B:3C:40:11
Uplink port:       sw-f3-02 / Ethernet1/0/14
~~~

Đây chỉ là bản ghi lab. Không coi BSSID trong bản scan RF là bằng chứng rằng thiết bị đúng serial; cần đối chiếu controller và switch port nếu mục đích là **chứng minh AP thuộc mạng doanh nghiệp**.

### 3.2. Các bước kết nối Wi-Fi

~~~mermaid
sequenceDiagram
    participant C as Wi-Fi client
    participant A as Access Point
    participant W as WLC / NAC / RADIUS
    C->>A: Quan sát beacon / probe theo hoạt động scan
    Note over C,A: SSID, BSSID, capability, channel có thể được quan sát
    C->>A: Authentication / Association (tùy loại WLAN)
    A->>W: Chính sách WLAN và xác thực doanh nghiệp nếu cấu hình
    W-->>A: Kết quả và thuộc tính phiên / role / VLAN
    A-->>C: Kết nối được thiết lập hoặc bị từ chối
    Note over C,W: 4-way handshake / key establishment theo bảo mật WLAN
    C->>A: Traffic đã được bảo vệ theo cấu hình phiên
~~~

Sơ đồ là mô hình đơn giản. **WPA2/WPA3-Personal, WPA2/WPA3-Enterprise và các giao thức 802.11** có trình tự chi tiết khác nhau; EAP/RADIUS không nhất thiết xuất hiện trong mạng dùng PSK/SAE. Không khẳng định mọi bước "authentication" ở 802.11 là xác minh danh tính người dùng như đăng nhập ứng dụng. Một số frame quản lý xuất hiện **trước khi phiên dữ liệu được bảo vệ hoàn toàn**.

### 3.3. Dữ liệu WIDS có thể quan sát

| Tín hiệu | Nội dung được nhìn thấy khi cảm biến hỗ trợ | Dùng để làm gì | Hạn chế |
| --- | --- | --- | --- |
| **Beacon** | SSID, BSSID, channel, capability/security advertised và timing | Tìm AP/SSID mới, thay đổi cấu hình phát sóng | Có thể bị giả; một beacon không chứng minh uplink vào mạng dây |
| **Probe request/response** | Tín hiệu khám phá mạng của client và AP | Nhận diện client/SSID scan, AP xuất hiện | Probe có thể bị giới hạn/ẩn, MAC randomization, privacy |
| **Association/reassociation** | Client cố liên kết với BSSID/AP | Xác định client và điểm WLAN đang được dùng | Cảm biến phải quan sát đúng kênh/thời điểm; log controller có thể rõ hơn |
| **Authentication/EAP/RADIUS metadata** | Kết quả xác thực, phương thức, danh tính được hệ thống xác thực | Phân biệt thất bại/hợp lệ và identity | Chỉ từ mạng/công cụ có quyền; không nên log secret/EAP payload nhạy cảm |
| **Deauthentication/disassociation event** | Sự kiện thay đổi trạng thái kết nối | Phân tích gián đoạn, roaming, hoạt động bất thường | Không mọi event là tấn công; một số management frames có thể được bảo vệ bởi PMF |
| **RSSI/SNR/channel utilization** | Cường độ và đặc điểm phổ/kênh từ điểm thu | Hỗ trợ phân vùng RF, phát hiện trùng/kênh nghẽn | Bị ảnh hưởng vật cản, đa đường, công suất phát, hướng anten |
| **WLAN controller client session** | AP phục vụ, SSID, thời điểm, role/VLAN, kết quả NAC | Bằng chứng endpoint đã kết nối với WLAN tổ chức | Không thấy AP lạ bên ngoài không quản lý nếu không có RF sensor |
| **Switch MAC table / LLDP / port status** | Cổng mạng dây nhìn thấy MAC và trạng thái link | Điều tra AP lạ có uplink vào LAN hay không | MAC học qua bridge, LLDP có thể thiếu/không đáng tin nếu do thiết bị ngoài phát |

**Passive monitoring** quan sát các frame có thể thu được mà không chủ động làm gián đoạn thiết bị. Cảm biến muốn thấy đầy đủ các kênh phải có radio/kênh và thời gian dwell phù hợp; một thiết bị đứng một kênh không thể nhìn mọi hoạt động trên toàn bộ băng tần cùng lúc.

### 3.4. Vì sao một thiết bị có thể trông như nhiều thiết bị?

Những yếu tố làm số đếm "thiết bị lạ" tăng mà không phải có thêm người dùng:

- Một AP phát nhiều BSSID trên cùng radio cho Corporate/Guest/IoT SSID.
- Client dùng **MAC ngẫu nhiên** khi scan, hoặc địa chỉ riêng theo SSID và thời điểm/hệ điều hành.
- Thiết bị có nhiều interface (Wi-Fi, Ethernet, Bluetooth, cellular).
- Cùng client di chuyển giữa AP trong roaming; log association có thể được ghi tại nhiều controller.
- Một số thiết bị có nhiều radio hoặc liên kết đa băng (ví dụ cơ chế **Multi-Link Operation** ở thiết bị hỗ trợ Wi-Fi 7), cần mô hình định danh tương ứng.
- Client bị reset/đổi network profile hoặc thay adapter; MAC khác trong khi owner không đổi.
- Collector nhận event trùng do retry hoặc nhiều sensor quan sát cùng một frame/thiết bị.

Vì vậy **đếm số MAC quan sát được không bằng số thiết bị vật lý**; báo cáo phải phân biệt **RF identities, authenticated sessions và managed assets**.

## 4. Kiến trúc giám sát thiết bị lạ theo nhiều lớp

~~~mermaid
flowchart LR
    RF["Không gian Wi-Fi\nAP quản lý, client, neighbor, unknown"] --> S["WIDS sensors / managed AP RF scans"]
    AP["WLAN controller / AP management"] --> COL["Collector / ingestion"]
    S --> COL
    SW["Switch, wired ports,\nDHCP, DNS, firewall"] --> COL
    ID["802.1X / RADIUS / NAC,\nMDM / EDR inventory"] --> COL
    COL --> P["Parse, normalize,\ntime-align, deduplicate"]
    P --> E["Enrichment:\nasset owner, site,\npolicy, session, RF"]
    E --> SIEM[("SIEM / WIDS analysis")]
    SIEM --> C["Case / SOC-NOC-WLAN triage"]
    C --> ACT["Phản ứng được phê duyệt\nport control / NAC / device owner"]
    ACT -. "Cập nhật và xác minh" .-> AP
    ACT -. "Cập nhật và xác minh" .-> SW
~~~

Nên tách **nguồn quan sát RF** và **bằng chứng kết nối vào mạng doanh nghiệp**. Một SSID lạ phát bên ngoài trụ sở chỉ là quan sát không dây; một cổng Ethernet thuộc mạng production có AP ngoài danh sách quản lý là vấn đề liên quan kiểm soát truy cập vật lý và LAN.

### 4.1. Vai trò của WIDS và WIPS

**Wireless IDS (WIDS)** quan sát và tạo alert về mạng không dây. **Wireless IPS (WIPS)** là hệ thống có thêm khả năng ngăn chặn/kiểm soát theo thiết kế sản phẩm, thường tích hợp AP/controller và chính sách WLAN. Tên tính năng và phạm vi thực thi không giống nhau ở mọi nhà cung cấp.

| Thành phần | Khả năng chính | Lưu ý |
| --- | --- | --- |
| Sensor RF thụ động | Quét và phân tích tín hiệu AP/client trong các băng/kênh hỗ trợ | Vị trí vật lý, kênh, thời gian scan quyết định coverage |
| Managed AP trong monitoring mode | Thu nhận RF telemetry ngoài việc phục vụ client (theo năng lực phần cứng) | Có thể ảnh hưởng dung lượng phục vụ khi radio chia thời gian; cần thiết kế |
| WLAN controller | Inventory AP, client association, SSID, security profile, roaming, event log | Không tự quan sát mọi rogue AP trên mọi kênh |
| WIDS analysis | Đối chiếu BSSID/SSID/capabilities và behavior với policy | Phải kiểm chứng alert với nguồn bổ trợ |
| WIPS enforcement | Chặn/giới hạn theo WLAN/NAC hoặc tính năng radio hỗ trợ | **Không tự ý phát deauth/jamming**; cần xem quyền, quy định và tác động |
| NAC/802.1X/RADIUS | Kiểm soát danh tính, posture, VLAN/role của client được quản lý | Không ngăn mọi hotspot riêng hoặc AP ở ngoài mạng doanh nghiệp |
| Wired access controls | 802.1X wired, port security, quản trị switch | Hữu ích để ngăn rogue AP nối mạng dây |
| SIEM/SOAR | Ghép sự kiện đa nguồn, case và hỗ trợ ứng phó | Không nên tự cô lập thiết bị quan trọng dựa trên một RF observation |

**WIPS không mặc nhiên có quyền can thiệp vào mọi AP đang phát sóng quanh văn phòng.** Ngắt kết nối client của mạng không thuộc tổ chức có thể trái chính sách/quy định và gây gián đoạn người khác. Ưu tiên các hành động tại **mạng, tài khoản, cổng và AP mà tổ chức sở hữu**.

### 4.2. Phân vùng mạng và đường đi dữ liệu

Một kiến trúc WLAN thường chia:

- **Corporate WLAN:** 802.1X, identity/managed posture và role/VLAN được duyệt; chỉ truy cập dịch vụ theo nhu cầu.
- **Guest WLAN:** tách logic/định tuyến khỏi mạng quản trị và dữ liệu; policy egress riêng.
- **IoT WLAN:** cấp quyền theo nhóm thiết bị, áp microsegmentation/firewall; hạn chế east–west.
- **Management network:** dành cho controller/AP/sensor, API quản trị và log; không cho khách thông thường truy cập.
- **Quarantine/onboarding network:** phục vụ thiết bị chưa xác minh, chỉ cho quy trình đăng ký/khắc phục.

Một rogue AP nối vào LAN có thể **bỏ qua chính sách cấp quyền của WLAN chính thức** nếu cổng dây không có kiểm soát thích hợp. Vì vậy, giám sát thiết bị lạ phải liên kết với **switch port authorization, NAC, VLAN, DHCP snooping và firewall**, không chỉ quan sát trên RF.

### 4.3. Mô hình vị trí sensor

| Vị trí | Ưu tiên quan sát | Điểm mù thường gặp |
| --- | --- | --- |
| Tầng làm việc đông người | Corporate/Guest SSID, roaming, hotspot, thiết bị BYOD | Nhiễu, vách ngăn, tầng lân cận |
| Phòng họp / hội nghị | AP lạ, thiết bị trình chiếu, hotspot tạm thời | Nhiều thiết bị mới hợp lệ theo sự kiện |
| Khu sản xuất/OT | WLAN công nghiệp, bridge IoT, thiết bị bảo trì | RF khó đo, không thể gây gián đoạn thiết bị an toàn |
| Kho và khu vực ngoại vi | AP gần cổng, thiết bị mới, dịch vụ guest | Coverage ở ngoại vi và kênh thay đổi |
| Data center / tầng kỹ thuật | AP cắm vào LAN, điểm quản trị không dây trái quy định | NIDS RF không chứng minh AP có nối cổng dây nào |
| Mạng chi nhánh | Inventory đồng bộ, SSID theo policy từng cơ sở | WAN/SIEM gián đoạn, controller cục bộ khác cấu hình |

**RF coverage không tương đương Wi-Fi client coverage.** Thiết kế cảm biến phải được khảo sát theo băng tần, kênh, công suất, vật cản và yêu cầu bắt sự kiện; đo tại một vị trí không bảo đảm nhìn thấy toàn bộ khu vực.

## 5. Nguồn dữ liệu và chuỗi bằng chứng nhận diện thiết bị

### 5.1. Quan sát RF và nhật ký truy cập khác nhau

Giả sử một sensor phát hiện BSSID lạ phát **Corp-WiFi** ở gần tầng 3. Chỉ với beacon, ta biết **có một tín hiệu tự nhận** tên mạng và đặc điểm như vậy, **chưa biết** AP đó có nối LAN công ty hay không, ai sở hữu, có client nào kết nối và đã truy cập tài nguyên gì.

Nếu controller ghi client X đã association với **managed AP**, RADIUS ghi identity X xác thực thành công, NAC gán role Guest và firewall chỉ cho phép Internet, ta mới có bức tranh về **phiên kết nối cụ thể**. Bên cạnh đó, một AP lạ có thể vẫn phát cùng SSID dù **không có client nào kết nối**, khiến mức độ phơi nhiễm khác trường hợp đã ghi nhận client được chuyển sang nó.

| Nguồn telemetry | Trường nên có | Câu hỏi hỗ trợ | Không chứng minh |
| --- | --- | --- | --- |
| WIDS RF | BSSID, SSID, channel/band, security capability, RSSI, first/last seen, sensor ID | Có tín hiệu AP/client nào mới xuất hiện? | AP có thật sự nối mạng công ty? |
| WLAN controller | AP ID/serial, radio, BSSID, SSID, association, roam, session state | Thiết bị đang nằm trên AP quản lý nào? | Một hotspot không được quản lý ngoài vùng controller |
| RADIUS / 802.1X | Auth result, identity đã được kiểm tra, EAP method, AP/NAS, timestamp, session ID | Ai/thiết bị nào đã được xác thực vào WLAN? | Người đó là chủ của mọi MAC từng quan sát |
| NAC / MDM / EDR | Device ID, certificate, posture, owner, loại/nhóm thiết bị, compliance status | Client có được quản lý/cấp quyền không? | RF sensor có thể thấy thiết bị khi không có agent |
| DHCP | MAC/client ID, lease IP, VLAN, thời điểm bắt đầu/kết thúc | IP nào được cấp cho client ở một thời điểm? | IP vẫn thuộc client đó ở thời điểm khác |
| Switch | Port/interface, learned MAC, VLAN, link state, dot1x status, LLDP khi có | Có dấu hiệu AP/bridge nối vào cổng nào? | LLDP và MAC đơn lẻ là danh tính được xác thực |
| DNS / DHCP / gateway | Query metadata, giao thức, IP nguồn, next hop | Thiết bị đã dùng dịch vụ mạng nào? | Thiết bị cố ý hoặc có khả năng tấn công |
| Firewall / IDS / IPS | 5-tuple, action, policy, NAT mapping, sensor | Thiết bị có tiếp cận vùng nhạy cảm không? | Quyền ứng dụng, bằng chứng chiếm quyền chỉ qua IP |
| SIEM / inventory | Event correlation, asset owner, change ticket, approved SSID/AP | Thiết bị có phù hợp với chính sách không? | Mọi bản ghi trong inventory đều còn đúng |

**Điểm mấu chốt:** tìm và lưu được **thời điểm hiệu lực** của identity/session. Một IP DHCP hoặc một địa chỉ MAC xuất hiện trong log hôm qua không mặc nhiên thuộc cùng thiết bị hoặc cùng người dùng hôm nay.

### 5.2. Các khóa join đáng tin và độ tin cậy

Có thể chia nhận diện thành các mức:

| Mức độ | Dữ liệu | Độ tin cậy có điều kiện |
| --- | --- | --- |
| Quan sát sơ bộ | SSID, BSSID, RSSI, OUI, tên được phát | **Thấp**: có thể bị giả, bị thay, không đủ chỉ định chủ sở hữu |
| Liên hệ phiên WLAN | Controller ID, AP ID, association ID, role/VLAN, timestamp | **Trung bình đến cao** cho kết nối qua AP quản lý nếu log xác thực được |
| Danh tính đã xác thực | 802.1X identity, EAP-TLS certificate identity, NAC device ID, session record | **Cao hơn** khi certificate validation, binding và lifecycle đúng |
| Liên kết endpoint/owner | MDM asset ID, EDR host ID, CMDB owner, change ticket | **Có giá trị** khi inventory mới, nguồn tin cậy và phân quyền quản trị đúng |
| Kết nối mạng thực tế | DHCP lease, switch port, flow logs và firewall rule ID | **Xác nhận đường đi/khả năng truy cập** ở điểm quan sát, không tự chứng minh động cơ |

Đừng nâng một phép gán danh tính **suy diễn** thành **đã được xác thực** trong SIEM. Ví dụ đặt trường 'identity_source=mac_oui_heuristic' và 'confidence=low' nếu chỉ đoán loại thiết bị từ OUI, thay vì ghi 'owner=Employee-A' không có bằng chứng.

### 5.3. MAC randomization và tính riêng tư

Nhiều hệ điều hành sử dụng **địa chỉ MAC ngẫu nhiên hóa** khi khám phá Wi-Fi, khi kết nối một SSID hoặc theo chính sách riêng. Địa chỉ có thể duy trì ổn định theo từng mạng trong một giai đoạn nhưng cũng có thể thay đổi. Vì vậy:

- Một MAC chưa có trong inventory không tự đồng nghĩa một người lạ đang xâm nhập.
- Một thiết bị có thể hiện nhiều MAC qua thời gian; **không dùng số MAC để ước lượng chính xác số người**.
- Nhãn **vendor OUI** trên MAC có thể sai khi dùng địa chỉ locally administered; không dựa vào OUI để quyết định model/loại thiết bị quan trọng.
- Không yêu cầu tắt MAC randomization cho toàn bộ thiết bị chỉ để tiện giám sát; đánh giá quyền riêng tư và chính sách endpoint.
- Với mạng doanh nghiệp, dùng **802.1X certificate identity, NAC/MDM identity** hoặc credential đã được kiểm tra để gắn thiết bị/phiên, thay vì biến MAC thành bằng chứng danh tính duy nhất.
- Khi thiết bị không thuộc quản lý tổ chức, chỉ thu thập dữ liệu tối thiểu phục vụ an toàn mạng; kiểm soát retention và quyền truy cập.

Ví dụ một tập sự kiện giả:

~~~text
09:00 - WLAN sees 02:11:22:33:44:55 on Corp-WiFi.
09:01 - RADIUS auth success; device certificate ID = lab-device-42.
14:00 - WLAN sees 02:66:77:88:99:AA after profile change.
14:01 - RADIUS auth success; device certificate ID = lab-device-42.

Interpretation:
  Có thể là cùng thiết bị ở hai phiên khác MAC,
  khi certificate identity được xác thực và quản lý đúng.
  Không gộp mọi MAC tương tự hoặc mọi certificate subject text tùy ý.
~~~

Trong ví dụ, mọi địa chỉ MAC và certificate ID đều là **giả lập**. Các chứng chỉ cần được xác minh CA, chuỗi tin cậy, thuộc tính danh tính và trạng thái hiệu lực theo cơ chế NAC thực tế; không dựa vào chuỗi subject do client tự khai.

### 5.4. NAT, proxy và IP không đủ quy nguồn

Một WLAN có thể đưa khách ra Internet qua **NAT chung**. Log ở dịch vụ cloud bên ngoài sẽ chỉ thấy IP egress, không có BSSID hoặc danh tính client. Tương tự, một firewall chỉ thấy IP của **wireless gateway** nếu traffic đã được NAT hoặc proxy:

~~~text
Client 10.40.30.55:53211 -> Gateway 10.40.30.1
NAT    203.0.113.20:41001 -> Dịch vụ ngoài 192.0.2.80:443
~~~

Để tương quan, cần **DHCP lease/role, NAC session, client IP–MAC mapping đúng thời điểm, NAT source-port mapping và flow time**. Địa chỉ trong TEST-NET ở đây dùng minh họa, không phải IP sản xuất. Một log bên ngoài chứa public IP NAT **không đủ** để xác định người dùng Wi-Fi đã tạo kết nối.

### 5.5. Đặc điểm vùng phủ và giới hạn định vị RF

Một số nền tảng WLAN sử dụng nhiều sensor đo cường độ tín hiệu hoặc phương pháp vị trí để ước lượng AP/client nằm trong khu vực nào. Kết quả phụ thuộc:

- Vị trí/mật độ cảm biến và khảo sát RF.
- Vật cản, đa đường, công suất phát, hướng anten và nhiễu.
- Channel hopping, dwell time, thiết bị chuyển radio/band.
- Thời điểm xuất hiện, client roaming và cấu trúc tòa nhà.

**RSSI lớn hơn không chứng minh thiết bị ở ngay cạnh sensor**; cũng không thể suy ra địa chỉ căn hộ hay vị trí người dùng chính xác từ vài quan sát RSSI không hiệu chuẩn. Dùng định vị để **ưu tiên kiểm tra vật lý trong khu vực được phép**, kết hợp switch/controller records, chứ không đưa kết luận danh tính từ tọa độ dự đoán.

## 6. Những trường hợp phát hiện cần ưu tiên

### 6.1. AP không được quản lý cắm vào mạng dây nội bộ

Một điểm truy cập cá nhân có thể được cắm vào switch của tổ chức. Nếu cổng không áp NAC hoặc port policy đúng, client Wi-Fi có thể đi vào mạng LAN mà không qua WLAN controller/802.1X của doanh nghiệp.

**Luồng kiểm chứng:**

1. WIDS thấy BSSID/SSID không có trong inventory tại khu vực văn phòng.
2. Switch có port mới lên link, learned MAC và đặc điểm traffic giống bridge/AP (chỉ là tín hiệu ban đầu).
3. NAC/wired 802.1X cho biết port/device **đã được cấp quyền hay chưa**, VLAN được gán.
4. DHCP/firewall/flow log thể hiện thiết bị sau port có thể nhận IP và tiếp cận mạng nào.
5. Chủ cổng, change ticket và owner địa điểm xác nhận thiết bị có được phép hay không.

**Mức ưu tiên cao** nếu có bằng chứng AP không được phép **kết nối vùng nội bộ nhạy cảm** hoặc bypass quyền. Hành động phù hợp thường là **kiểm soát cổng wired, thu hẹp VLAN/ACL hoặc tách port** theo phê duyệt, thay vì phát deauth vô tuyến có thể ảnh hưởng người khác.

### 6.2. Evil twin hoặc SSID impersonation

Ví dụ tổ chức phát **Corp-Secure** với WPA2/WPA3-Enterprise và xác thực máy chủ RADIUS bằng certificate. Một AP ngoài hệ quản lý xuất hiện cùng SSID nhưng có profile security khác, hoặc quảng bá thuộc tính bất thường.

**Tín hiệu cần xem:**

- BSSID/PHY/security advertisement không khớp danh sách managed AP.
- SSID giống một mạng cần bảo vệ nhưng thuộc tính cipher, AKM hoặc PMF không như policy.
- Có client cố liên kết tới BSSID chưa được duyệt hay không.
- RADIUS/controller log có chứng cứ kết nối hợp lệ tới managed AP không.
- Hệ điều hành/client có **xác minh chứng chỉ máy chủ EAP** đúng hay đã bị cấu hình bỏ qua.
- Khu vực và thời điểm có sự kiện mạng demo, nhà thầu, hàng xóm, AP cũ chưa tháo hay không.

**SSID/BSSID giống nhau không chứng minh AP đã giả được danh tính**: nhiều SSID trùng tình cờ, và BSSID có thể bị spoof. Sự khác biệt bảo mật làm tăng nghi vấn, nhưng cần kết hợp dữ liệu identity/session và quan sát được phép trước khi kết luận.

Phòng vệ quan trọng là **client profile cấu hình EAP-TLS hoặc phương thức Enterprise được chấp thuận với kiểm tra chứng chỉ máy chủ chính xác**, loại bỏ tự động kết nối mạng không được duyệt, quản lý cấu hình WLAN bằng MDM/GPO phù hợp, và dùng WIDS để phát hiện/điều tra.

### 6.3. Unauthorized client cố truy cập Corporate WLAN

Client lạ có thể thử association nhiều lần hoặc 802.1X xác thực thất bại. Một số trường hợp hợp lệ như mật khẩu đã thay, chứng chỉ hết hạn hoặc giờ hệ thống sai cũng tạo chuỗi lỗi tương tự.

Điều tra cần tách:

| Trạng thái | Diễn giải nên dùng | Bằng chứng |
| --- | --- | --- |
| Probe/scan thấy SSID | Client đang khám phá mạng | RF observation; **chưa xác thực** |
| 802.11 association attempt | Client đang thử liên kết | AP/controller event; có thể chưa qua NAC |
| 802.1X failed | Không được xác thực theo policy tại thời điểm đó | RADIUS result/reason, AP ID, EAP method |
| 802.1X success nhưng quarantine | Danh tính được nhận nhưng posture/chính sách còn giới hạn | NAC role, certificate/session, assigned VLAN |
| 802.1X success, corp role | Phiên được cấp quyền theo policy | Identity đã xác minh, AP, VLAN/role, timestamp |
| Client sau đó vào vùng nhạy cảm | Reachability thực tế cần đánh giá | Firewall/flow/application logs và quyền của ứng dụng |

Một client phát nhiều yêu cầu **không tự là tấn công brute-force**. Có thể do roaming, driver, bản vá 802.1X, RADIUS timeout hoặc profile lỗi. Dùng **tỷ lệ/chuỗi sự kiện cùng identity**, ngữ cảnh và số hệ thống ảnh hưởng.

### 6.4. Hotspot cá nhân, BYOD và thiết bị IoT lạ

Một điện thoại bật hotspot có thể là kết nối Internet dự phòng hợp lệ cho cá nhân, nhưng có thể vi phạm chính sách nếu:

- Thiết bị công ty đồng thời kết nối vào mạng quản trị/Corporate WLAN và Internet qua hotspot theo cách tạo đường bypass trái ý định.
- Người dùng chia sẻ kết nối từ máy có quyền truy cập dữ liệu nội bộ tới thiết bị không được quản lý.
- Hotspot hoặc bridge nối LAN nội bộ với WLAN không được cấp quyền.

Hãy phân biệt **hotspot ở gần** với **hotspot được máy doanh nghiệp dùng**, và phân biệt **thiết bị IoT mới được mua có ticket** với **thiết bị không rõ chủ**. Bản ghi MDM/EDR hoặc hệ điều hành có thể giúp biết network interface nào đang hoạt động, nhưng cần quyền truy cập endpoint và chính sách riêng tư.

### 6.5. AP thay cấu hình bảo mật hoặc phát thêm SSID

Managed AP bỗng phát một SSID mới hoặc chuyển từ Enterprise sang một kiểu xác thực yếu hơn có thể là **drift cấu hình** hoặc thay đổi có phê duyệt. Cần kiểm tra:

1. Tên AP/serial/controller và change history.
2. WLAN profile, AKM/cipher, PMF policy, VLAN/role.
3. BSSID/SSID được controller ánh xạ tới profile nào.
4. Người hoặc automation thay cấu hình, quyền RBAC.
5. Client nào đã được phép kết nối khi policy thay đổi.
6. Có đường từ SSID đó đến mạng nhạy cảm bị mở rộng không.

**Không chỉ dựa vào beacon** để kết luận một thiết bị vật lý bị cấu hình lại; đối chiếu cấu hình thực tại controller và audit log.

### 6.6. Sự kiện management frame bất thường

Tăng vọt sự kiện disassociation/deauthentication, association failure hoặc client roaming liên tục có thể do lỗi RF, thiết bị/driver, thay đổi kênh, AP reboot, 802.11r/PMF compatibility hoặc hành vi can thiệp.

Một WIDS có thể phát hiện mẫu đáng ngờ, nhưng **không đủ căn cứ từ số lần deauth để quy kết tấn công**. Cần so:

- Radio metrics: airtime, noise, channel switch, DFS event, client count.
- Controller/AP firmware, reboot và change timeline.
- PMF negotiation/profile và loại frame quan sát.
- Hành vi client trên nhiều AP/band và bằng chứng của sensor khác.
- Sự cố nguồn điện, uplink, DHCP hoặc RADIUS gây lặp kết nối.

Khuyến nghị **không phát frame chủ động** để "kiểm thử WIPS" ở môi trường chung nếu chưa có quyền, vùng RF cô lập và đánh giá tác động. Đối với hệ thống production, kiểm thử phòng vệ bằng sự kiện giả lập và kiểm tra cấu hình thường an toàn hơn.

## 7. Quy tắc phát hiện, mức độ ưu tiên và xử lý false positive

### 7.1. Phân loại theo mức ảnh hưởng, không chỉ dựa vào tên cảnh báo

| Case mẫu | Dữ liệu hiện có | Mức ưu tiên gợi ý | Cần xác minh |
| --- | --- | --- | --- |
| BSSID lạ phát một SSID phổ biến, không có uplink nội bộ | RF beacon từ neighbor | **Thấp / Inventory** | Có phải AP hàng xóm/sự kiện hợp lệ? |
| SSID Corporate bị phát bởi AP không quản lý, không thấy client kết nối | RF + managed AP inventory | **Trung bình / cần điều tra** | Profile security, phạm vi, phản hồi client, owner |
| AP không duyệt xuất hiện trên switch port mạng production | Switch/NAC + RF/inventory | **Cao** | Port, VLAN, asset owner, reachability, thay đổi |
| Một client lạ 802.1X thất bại vài lần | RADIUS failed | **Theo ngữ cảnh** | Thiết bị mới, cert hết hạn, profile hoặc sự cố NAC |
| Danh tính hợp lệ được gán role quản trị trái policy | NAC role + identity + firewall | **Cao** | Rule/config sai, quyền ứng dụng, có truy cập thực tế không |
| SSID Corporate bị đổi bảo mật xuống ngoài baseline | Controller audit + RF | **Cao** nếu hiệu lực | Change ticket, scope, client affected |
| Nhiều AP báo mất WIDS heartbeat sau thay firmware | Sensor health | **Vấn đề coverage** | Không có dữ liệu không bằng không có thiết bị lạ |
| Hotspot cá nhân chỉ phát sóng bên ngoài | RF observation, không có corporate client | **Thấp**, tùy policy | Không can thiệp mạng không thuộc quyền quản lý |
| Client doanh nghiệp chuyển sang hotspot ngoài, rồi có lưu lượng trái policy | MDM/network telemetry + flow | **Cần điều tra** | Kết nối thật, dữ liệu truy cập, quyền thiết bị |

Đây là mức ưu tiên **minh họa**, không phải khung chấm điểm bắt buộc. Ưu tiên thực tế phụ thuộc criticality, khu vực, loại mạng, quy định và khả năng kiểm chứng.

### 7.2. Quy tắc phát hiện khái niệm

~~~yaml
# Pseudo-YAML mô tả ý định; không phải policy áp trực tiếp lên WLC/WIDS/SIEM.
detection_id: WLAN-UNMANAGED-AP-01
title: Suspected unapproved AP with corporate wired connectivity
required_sources:
  - wireless_rf_observations
  - managed_ap_inventory
  - switch_port_or_nac_events
match:
  bssid_not_verified_as_managed: true
  observed_by_at_least_one_authorized_sensor: true
  wired_connection_evidence: required_before_label_rogue_connected
context:
  site: required
  event_time: required
  approved_change_or_exception: check
  critical_vlan: increase_priority_if_confirmed
action:
  create_case: true
  retain_raw_event_references: true
  isolate_wired_port: require_approval_and_dependency_review
  radio_disruption: disabled
~~~

Điều kiện **wired_connection_evidence** thể hiện nguyên tắc: không gán nhãn "AP rogue đang nối LAN" chỉ vì có beacon giống SSID công ty. Bằng chứng uplink có thể đến từ cổng switch và xác minh hiện trường; việc cùng xuất hiện một MAC trong hai nguồn chưa chắc chứng minh quan hệ vật lý nếu không có mapping đáng tin.

### 7.3. Tuning theo đặc điểm từng site

Một site hội nghị sẽ có nhiều hotspot mới, còn một kho sản xuất ít thay đổi có thể kỳ vọng danh sách thiết bị ổn định. Rule nên có:

- **Baseline** số AP/client theo thời gian, channel/band, địa điểm và loại khu vực.
- **Approved SSID/AP inventory** theo serial, controller, site và version.
- **Change calendar** cho sự kiện, nhà thầu, AP tạm thời, nâng cấp firmware.
- **Grouping** nhiều sensor thấy cùng RF identity trong cửa sổ thời gian hợp lý.
- **Deduplication** event do retry/roaming; lưu first_seen/last_seen và số nguồn thực.
- **Confidence/uncertainty** đối với MAC randomization, vị trí RF và owner chưa biết.
- **Negative testing** thiết bị ngoài vùng cấp quyền không thể vào Corporate/NAC role.
- **Điều kiện hết hạn ngoại lệ**, không giữ allowlist vĩnh viễn cho một BSSID mới không được xác thực.

Một rule "**SSID == Corp-Secure và BSSID chưa có trong danh sách → tự chặn**" có thể tạo false positive lớn khi controller thay AP hợp lệ hoặc môi trường hàng xóm có SSID trùng. Tốt hơn: tạo case, đối chiếu **inventory + security profile + liên kết mạng dây + client session + owner** trước khi containment.

### 7.4. Mức độ tin cậy và impact nên tách riêng

Ví dụ hai cảnh báo:

~~~text
Alert A:
  RF sensor phát SSID lạ, RSSI mạnh.
  Confidence rằng có AP phát sóng: tương đối cao.
  Confidence rằng AP nối LAN công ty: chưa đủ.
  Confirmed impact: chưa có.

Alert B:
  Switch/NAC ghi một port đã liên kết với thiết bị không được duyệt.
  DHCP/firewall ghi truy cập production từ VLAN đó.
  Confidence về network reachability: cao hơn nếu log tương quan đúng.
  Confirmed impact: cần xác minh quyền và hành vi thực tế.
~~~

Không cộng tùy tiện RSSI, số beacon, số event và một "AI threat score" thành bằng chứng xác thực mà không có thiết kế/validation. **Nhãn do mô hình dự đoán phải được kiểm tra bằng evidence**, nhất là trước hành động làm gián đoạn.

## 8. Cấu hình bảo mật WLAN hỗ trợ giám sát thiết bị lạ

### 8.1. Xác thực và mã hóa là lớp phòng vệ trước thiết bị chưa được duyệt

Monitoring không thể thay cho **kiểm soát truy cập ngay khi kết nối**. Cấu hình WLAN nên phù hợp loại thiết bị, khả năng hỗ trợ và chính sách tổ chức:

| Loại WLAN/cơ chế | Ưu điểm và tình huống | Lưu ý vận hành/bảo mật |
| --- | --- | --- |
| **WPA2-Enterprise / WPA3-Enterprise với 802.1X** | Cấp quyền theo user/device khi tích hợp hệ thống xác thực, RADIUS/NAC | Kiểm tra certificate/server identity ở client; EAP method và cipher phải được hỗ trợ/duyệt |
| **EAP-TLS** | Có thể xác thực bằng chứng chỉ client và danh tính máy chủ được kiểm tra, thuận tiện quản lý thiết bị | Cần PKI, vòng đời certificate, revocation/policy, chống cấp sai credential |
| **WPA3-Personal (SAE)** | Phù hợp một số môi trường nhỏ, thiết bị không có 802.1X | Dùng passphrase đủ mạnh; mật khẩu chung không xác định rõ danh tính từng user |
| **WPA2-Personal (PSK)** | Có thể cần cho thiết bị tương thích cũ | Quản lý/luân chuyển PSK và cô lập IoT; một PSK chung gây khó quy nguồn |
| **Enhanced Open/OWE** khi hỗ trợ | Mã hóa kết nối Wi-Fi không yêu cầu mật khẩu truyền thống trong một số mạng mở | **Không xác thực danh tính AP/người dùng như Enterprise**; không thay TLS/authorization |
| **Open guest WLAN** nếu còn dùng | Tiện truy cập khách | Dữ liệu trên liên kết có thể không được bảo vệ ở mức Wi-Fi như WLAN mã hóa; cần captive portal/chính sách và TLS ứng dụng phù hợp |

Đặc tính bảo mật của **6 GHz và các chuẩn Wi-Fi mới** khác môi trường 2,4/5 GHz; phải tuân theo yêu cầu bảo mật, PMF và khả năng được nền tảng hỗ trợ tại băng tần đó. Không suy rằng AP nào phát cùng SSID ở 2,4/5/6 GHz có cùng security profile hoặc sensor đều quét được cả ba băng.

**Không nên dùng MAC filtering như cơ chế xác thực chính**: MAC có thể thay đổi/giả mạo và không đại diện chắc chắn cho danh tính thiết bị. Cần xác thực bằng credential hoặc certificate đã được kiểm tra và giới hạn role/network theo nguyên tắc least privilege.

### 8.2. PMF (Protected Management Frames)

**IEEE 802.11w / Protected Management Frames (PMF)** bảo vệ **một số loại management frame quan trọng** trong các điều kiện phiên đã được thiết lập/đàm phán phù hợp, giúp giảm rủi ro giả mạo một số frame deauthentication/disassociation. Nhưng:

- PMF **không chứng minh BSSID/SSID là của tổ chức**, không tự ngăn AP khác phát tên giống.
- Không nên hiểu rằng **mọi beacon/probe/management frame đều có bảo vệ PMF**.
- Cần phân biệt PMF **capable, required, negotiated** theo capability WLAN và client; nếu profile yêu cầu PMF, client cũ có thể không kết nối được.
- Một cảnh báo deauth bất thường cần đối chiếu PMF state, loại frame và log controller, không suy ra một hành vi tấn công chỉ từ tên event.
- Roaming/fast transition và firmware cũ có thể tương tác với PMF; thử nghiệm tương thích trước khi đổi chính sách diện rộng.

Giám sát nên ghi **security policy kỳ vọng và policy thực** của mỗi SSID, bao gồm loại AKM/cipher, PMF và những ngoại lệ có phê duyệt.

### 8.3. 802.1X, RADIUS và quy trình cấp quyền

Đối với Corporate WLAN, chuỗi kiểm soát điển hình:

~~~mermaid
flowchart LR
    C["Client doanh nghiệp"] --> A["AP / WLC"]
    A --> R["RADIUS / AAA"]
    R --> I["PKI / IAM / device policy"]
    R --> NAC["NAC role / VLAN / posture"]
    NAC --> SEG["Network firewall / segmentation"]
    SEG --> APP["Ứng dụng với authn/authz riêng"]
    A -. "Client/AP event" .-> LOG["SIEM / WIDS"]
    R -. "Auth result" .-> LOG
    NAC -. "Assigned role" .-> LOG
    SEG -. "Allow / deny logs" .-> LOG
~~~

Trong sơ đồ, NAC có thể nằm trong controller, RADIUS policy engine hoặc hệ thống riêng. Kết quả xác thực có thể cấp một role/VLAN được phê duyệt, nhưng **không đồng nghĩa user đã có quyền truy cập mọi ứng dụng trong VLAN đó**.

Các kiểm soát phòng vệ:

1. Cấp client profile bằng MDM hoặc cơ chế quản trị được kiểm soát.
2. Yêu cầu kiểm tra **chứng chỉ máy chủ RADIUS đúng CA và danh tính mong đợi**, tránh tùy chọn bỏ qua xác minh.
3. Đối với EAP-TLS, quản lý private key, cấp/thu hồi certificate và liên kết identity tới asset owner.
4. Giới hạn số và phạm vi các exception cho thiết bị IoT không hỗ trợ 802.1X; không dồn mọi thiết bị ngoại lệ vào production VLAN.
5. Ghi kết quả authentication, assigned role, thời điểm và AP ID cho triage; **không ghi mật khẩu hoặc secret**.
6. Đảm bảo availability/HA của RADIUS/NAC để lỗi dịch vụ xác thực không bị nhầm thành thiết bị độc hại.

### 8.4. Network segmentation và kiểm soát đường dây

WLAN bảo mật tốt vẫn cần **firewall/microsegmentation** theo loại tài nguyên:

~~~text
Corporate SSID -> policy theo identity/role -> API được duyệt
Guest SSID     -> Internet egress theo policy; DENY private management/data
IoT SSID       -> broker/management được duyệt; DENY east-west tùy thiết kế
Quarantine     -> onboarding/repair endpoints; DENY production
AP management  -> controller/log server; chỉ từ mạng quản trị
~~~

Nếu một AP không được phép **cắm vào mạng dây**, các lớp như wired 802.1X, port security, giới hạn trunk/tagged VLAN, switch management ACL và inventory cổng giúp giảm khả năng bỏ qua chính sách WLAN. Không mặc định một **uplink mang VLAN production** phải được cấp cho mọi cổng có AP/bridge.

### 8.5. Bảo vệ management plane

Hãy bảo vệ **controller, AP, RF sensor, RADIUS, NAC và SIEM** như tài sản an ninh quan trọng: MFA/RBAC cho quản trị, TLS/API được chứng thực, vòng đời firmware và certificate, change audit, management VLAN, backup/restore. Một thiết bị "managed" nhưng controller credential bị lộ có thể thay đổi SSID hoặc role hợp lệ về hình thức.

## 9. Thu thập, chuẩn hóa và tương quan trong SIEM

### 9.1. Pipeline giám sát

~~~mermaid
flowchart LR
    RF["WIDS RF observations"] --> COL["Collector / transport"]
    W["WLC, RADIUS, NAC, switch,\nDHCP, MDM, firewall"] --> COL
    COL --> V["Validate schema, source, time"]
    V --> E["Enrich: site, asset,\nrole, session, approved change"]
    E --> D["Dedup + entity resolution\nđánh dấu confidence"]
    D --> SIEM[("SIEM detections / case history")]
    SIEM --> TRIAGE["SOC + WLAN + Network owner"]
    V --> H["Sensor/collector health alert"]
~~~

Những nguồn không đồng nhất có thể dùng syslog, webhook/API, JSON, message queue hoặc cloud log integration. Ưu tiên **kênh vận chuyển được xác thực/mã hóa**, buffer/retry, kiểm tra schema, timestamp và idempotency. Nếu collector lỗi, SIEM phải báo **mất visibility**, không gắn trạng thái "không có thiết bị lạ".

### 9.2. Schema sự kiện nên chuẩn hóa

| Trường logic | Mục đích | Cảnh báo diễn giải |
| --- | --- | --- |
| event.id, event.time, ingest.time | Định danh/dedup và so độ trễ | Phân biệt event-time với thời điểm ingest |
| observer.id, observer.site, observer.kind | Biết sensor/controller/switch nào thấy event | Sensor khác site có thể thấy cùng AP qua RF |
| event.category, event.action | Beacon seen, association, auth success/failure, switch link, policy deny | Không map "observed" thành "connected" |
| wlan.ssid, wlan.bssid, wlan.band/channel | Xác định RF identity | Chúng có thể bị giả hoặc thay theo radio |
| client.mac / client.session_id | Liên kết client với phiên | MAC randomization và roaming làm thay đổi định danh |
| ap.device_id / ap.serial / controller.id | Gắn AP với inventory quản lý | Chỉ tin từ controller/inventory đáng tin |
| auth.identity / cert_id / result | Nhận diện kết quả 802.1X | Phải xác thực identity; ẩn nội dung định danh theo chính sách |
| nac.role, vlan.id, switch.port | Phân tích quyền LAN | Role/VLAN thay theo thời gian và policy |
| network.src_ip/dst_ip, ports, direction | Tương quan DHCP/firewall/flow | Xét NAT, IP lease, điểm quan sát |
| rf.rssi, rf.sensor_count | Hỗ trợ zone/radio observation | Không tự biến RSSI thành tọa độ chính xác |
| classification, confidence, rationale | Trạng thái unknown/approved/suspicious/confirmed | Lưu **lý do và nguồn bằng chứng**, không chỉ điểm số |
| change.ticket, exception.expiry, owner | Giải thích thiết bị tạm thời | Ticket hết hạn không xác nhận thiết bị hiện tại |
| raw_event_ref, correlation_id | Truy vết quyết định | Lưu raw theo retention và quyền truy cập phù hợp |

### 9.3. JSON event giả lập

~~~json
{
  "event_id": "wids-hn-f3-0001",
  "event_time": "2026-11-28T03:00:00Z",
  "ingest_time": "2026-11-28T03:00:02Z",
  "observer": {"id": "rf-sensor-f3-02", "site": "HN-F3", "type": "passive_wids"},
  "event": {"type": "ap_beacon_observed", "action": "observed"},
  "wireless": {
    "ssid": "Corp-Secure",
    "bssid": "02:7A:30:40:50:66",
    "band": "5GHz",
    "channel": 36,
    "security_advertised": "lab-security-profile-differs-from-baseline"
  },
  "radio": {"rssi_dbm": -60},
  "inventory": {"managed_ap_match": false},
  "classification": "unverified_rf_ap",
  "confidence": "medium",
  "connected_to_corporate_lan": "not_established"
}
~~~

Đây là **schema minh họa**, không phải event format chính thức của một WLC/WIDS/vendor; địa điểm, BSSID và thời gian đều giả lập. **Bản ghi không nói rằng AP đã xâm nhập LAN**. Nếu sau đó thấy controller/wired logs, SIEM cần giữ cả evidence mới và trạng thái phân loại thay đổi theo thời gian.

Ví dụ sự kiện bổ trợ:

~~~json
{
  "event_id": "switch-hn-f3-0042",
  "event_time": "2026-11-28T03:00:10Z",
  "source": "managed_switch",
  "switch": {"id": "sw-f3-02", "port": "1/0/22", "vlan": 120},
  "observation": {
    "link_state": "up",
    "learned_mac": "02:7A:30:40:50:66",
    "device_authorization": "unapproved",
    "owner_record": null
  },
  "classification": "unapproved_wired_attachment_requires_verification",
  "notes": "MAC match is a lead; confirm physical/link identity before containment"
}
~~~

Trong thực tế **AP BSSID không nhất thiết trùng MAC Ethernet uplink**. Một MAC khớp trong hai log có thể do cấu hình sản phẩm hoặc giả mạo; cần chứng cứ mapping từ controller, switch LLDP đã được kiểm tra, NAC hoặc xác minh hiện trường trước khi kết luận là cùng một thiết bị vật lý.

### 9.4. Quy tắc correlation theo mức độ

**Use case A – AP lạ gần Corp-Secure:**

~~~text
IF RF sensor thấy SSID thuộc danh sách Corporate
AND BSSID chưa được xác minh là managed
AND security advertisement khác WLAN baseline
THEN tạo case "SSID impersonation suspected"
     gắn sensor/site/first_seen/last_seen
     tìm managed AP inventory và client association evidence
     KHÔNG tự ghi "rogue wired AP" hoặc phát frame ngắt kết nối
~~~

**Use case B – AP lạ có khả năng nối vào LAN:**

~~~text
IF RF alert cho AP không được phê duyệt
AND switch/NAC có bằng chứng kết nối không được duyệt
AND physical device/port mapping đã được xác minh
THEN nâng mức ưu tiên theo VLAN/role và reachable assets
     mở case với owner mạng và onsite support
     containment chỉ ở port/policy tổ chức sở hữu, có phê duyệt
~~~

**Use case C – unknown client được cấp role quá rộng:**

~~~text
IF RADIUS auth result == success
AND NAC identity/device posture chưa đạt yêu cầu
AND assigned role có production reachability trái chính sách
THEN tạo case kiểm tra NAC / WLAN authorization
     đối chiếu VLAN, policy change, firewall flow và asset owner
     hạn chế quyền theo quy trình; không suy đó là tấn công đã thành công
~~~

**Use case D – coverage suy giảm:**

~~~text
IF sensor heartbeat / RF scan coverage không còn dữ liệu
OR WLAN controller export log lỗi
THEN alert "wireless monitoring blind spot"
     ghi site, sensor, time window, data-loss estimate
     không kết luận "không thấy rogue AP" trong giai đoạn đó
~~~

Các rule trên chỉ mô tả **logic phát hiện**, không phải lệnh có thể triển khai nguyên vẹn trên một SIEM cụ thể. Cần xây schema mapping, event-time window và quyền truy cập phù hợp.

### 9.5. Tránh correlation sai khi client roaming

Một client có thể rời AP ở tầng 2 rồi kết nối AP ở tầng 3 trong vài giây. Nếu SIEM ghép mọi event "new BSSID + reassociation" thành case thiết bị lạ, số cảnh báo sẽ cao. Nên:

- Phân biệt **AP BSSID** với **client MAC** và identity đã xác thực.
- Ghi old/new AP ID, timestamp, roam reason và session continuity khi controller hỗ trợ.
- Dùng **session ID, cert/device ID, controller record** và cửa sổ thời gian được hiệu chỉnh để hiểu cùng một phiên.
- Không gộp các user khác nhau chỉ vì dùng cùng NAT IP/địa chỉ gateway.
- Khi có nhiều sensor phát cùng event, dedup theo sensor/event ID phù hợp nhưng vẫn giữ số sensor để xem coverage.

### 9.6. Sensor health là một loại cảnh báo bảo mật

Theo dõi AP/sensor không gửi dữ liệu, packet drops, radio/channel scanning bị vô hiệu, CPU overload, collector queue, lỗi parser, event lag và lệch đồng hồ. **Cảnh báo im lặng** là điều phải thiết kế chủ động: nếu một tầng mất telemetry, WIDS có thể không còn khả năng báo thiết bị mới.

## 10. Quy trình SOC/NOC xử lý khi phát hiện thiết bị lạ

### 10.1. Các bước điều tra

1. **Nhận alert và phân biệt loại sự kiện:** RF observation, auth failure, client association, wired port hoặc policy violation.
2. **Kiểm tra chất lượng:** sensor có hoạt động bình thường, clock đúng và event không trùng không?
3. **Đối chiếu inventory/approved change:** SSID/BSSID/serial/owner/ticket/site và thời hạn AP tạm thời.
4. **Xác minh radio/site:** sensor nào thấy, cùng băng/kênh nào, có AP hợp lệ đa BSSID hoặc neighbor đã biết không?
5. **Xác minh kết nối thật:** controller sessions, RADIUS/NAC, switch port, DHCP/IP mapping, firewall/flow và nguồn dữ liệu có quyền.
6. **Đánh giá rủi ro:** thiết bị có thực sự vào corporate LAN/role nhạy cảm hoặc gây suy giảm dịch vụ không?
7. **Chọn phản ứng đúng phạm vi:** sửa policy, khóa credential, NAC quarantine, kiểm soát switch port, liên hệ asset owner hoặc kiểm tra vật lý được phê duyệt.
8. **Xác minh sau xử lý:** connection path bị giới hạn như dự kiến, thiết bị hợp lệ vẫn hoạt động, alert và log kết quả được ghi.
9. **Đóng case và cải tiến:** cập nhật inventory, exception, WIDS rule, MDM profile, NAC policy, training hoặc quy trình thay đổi.

### 10.2. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["WIDS/SIEM: thiết bị lạ"] --> B{"Sensor và event có hợp lệ?"}
    B -- "Không / thiếu" --> BH["Khôi phục telemetry,\nđánh dấu unknown"]
    B -- "Có" --> C{"Có trong inventory / change ticket?"}
    C -- "Có" --> CI["Kiểm tra serial, site,\npolicy và hiệu lực"]
    C -- "Không" --> D{"Chỉ quan sát RF hay có kết nối thật?"}
    D -- "Chỉ RF" --> RF["Đánh giá neighbor / hotspot /\nSSID impersonation, theo dõi"]
    D -- "Có bằng chứng network" --> E{"Vượt quyền / vùng nhạy cảm?"}
    E -- "Không" --> P["Onboard/đăng ký, giới hạn role,\nđối chiếu owner"]
    E -- "Có hoặc nghiêm trọng" --> F["SOC/NOC review và phê duyệt\ncontainment có phạm vi"]
    F --> G["NAC / wired port / ACL\nhoặc hành động quản lý hợp pháp"]
    G --> H["Xác minh, bảo toàn bằng chứng,\nrollback khi cần"]
    CI --> H
    RF --> H
    P --> H
    BH --> H
~~~

### 10.3. Hành động ứng phó và tác động

| Hành động | Thường phù hợp khi | Điều kiện/giới hạn |
| --- | --- | --- |
| Mở ticket, thêm quan sát, kiểm kê onsite | Chỉ có RF observation, rủi ro thấp/chưa xác minh | Không được tự nhận thiết bị thuộc quyền tổ chức |
| Xác nhận với chủ địa điểm/owner | AP/IoT chưa có ticket, phát hiện tại phòng họp/kho | Không thu thập thông tin người dùng ngoài nhu cầu |
| Đưa client có quyền quản trị vào role quarantine | Identity/session trên WLAN do tổ chức kiểm soát không đạt posture | Có owner, quy trình, đường onboarding và rollback |
| Chặn/giới hạn switch port của tổ chức | AP không được phép có wired attachment đã xác minh | Kiểm tra port có gánh nhiều dịch vụ/thiết bị quan trọng không; phê duyệt |
| Thu hồi credential/certificate bị lạm dụng | Có bằng chứng quyền/identity bị chiếm hoặc vi phạm | Xác minh tài khoản, scope, quy trình ứng cứu và khả năng phục hồi |
| Đổi WLAN profile / tăng yêu cầu PMF/802.1X | Security baseline không đáp ứng | Kiểm thử compatibility, client IoT/legacy, kế hoạch cutover |
| Thông báo người dùng tránh kết nối SSID nghi vấn | Có nguy cơ impersonation cần cảnh báo | Cung cấp tên mạng/cấu hình chính thức; tránh quy kết đơn vị khác khi chưa rõ |
| Cải thiện NAC/port controls | Rogue AP phát hiện từ LAN | Ngăn kết nối trái quyền tại hệ thống mình sở hữu |
| Hành động chủ động trên RF | Một số WIPS có tính năng can thiệp | **Không phải lựa chọn mặc định**; chỉ sau đánh giá quyền, pháp lý, tác động và quy trình cụ thể |

**Không tự động dùng deauthentication để xử lý một AP nghi vấn.** Các cơ chế can thiệp RF có thể làm gián đoạn thiết bị của bên thứ ba, ảnh hưởng an toàn hoạt động và vi phạm quy định địa phương. Biện pháp quản trị **switch/NAC/firewall/identity mà tổ chức sở hữu** thường dễ kiểm soát và kiểm toán hơn.

### 10.4. Ví dụ case: AP lạ ở phòng kỹ thuật

Một sensor nhận BSSID chưa có trong inventory với SSID **Corp-Secure**. Switch log cùng khu vực báo cổng Ethernet chưa được phê duyệt, nhưng chưa xác định AP đó nối cổng nào.

**Không kết luận ngay** hai event là cùng thiết bị. SOC/NOC cần xác minh port–asset mapping bằng dữ liệu quản lý và kiểm tra hiện trường được phép. Nếu chứng minh có một AP ngoài quản lý nối vào **VLAN sản xuất**, ưu tiên kiểm soát cổng đó, đối chiếu các phiên/flow đã được cấp quyền, rà credential và kiểm tra cấu hình switch. Nếu chỉ là AP hàng xóm với SSID trùng, ghi nhận và điều chỉnh rule để tránh nhiễu.

### 10.5. Mẫu case có thể kiểm toán

| Trường | Nội dung cần ghi |
| --- | --- |
| Case ID và thời gian | ID, first_seen, last_seen, event_time và timezone |
| Loại quan sát | AP beacon, association, auth, wired port, policy change, health issue |
| Source/observer | Sensor/controller/switch ID, site, mức độ tin cậy dữ liệu |
| Wireless identity | SSID, BSSID, band/channel, security profile, MAC nếu cần |
| Đối chiếu asset | Serial/controller/AP ID, owner, change ticket, inventory match |
| Session/network evidence | RADIUS result, NAC role, switch VLAN/port, DHCP lease, firewall flow |
| Rủi ro và giới hạn | Known/unknown/unauthorized/confirmed, impact đã quan sát, dữ liệu còn thiếu |
| Biện pháp | Người duyệt, hành động, thời điểm, phạm vi và rollback |
| Kết quả | Có chặn đúng đường không, client hợp lệ còn hoạt động, số alert đã giảm? |
| Follow-up | Owner, thời hạn review, thay đổi inventory/policy và bằng chứng |

## 11. Mô hình hóa mối đe dọa trong giám sát thiết bị lạ

Thiết kế WIDS/WIPS nên xuất phát từ **tài sản cần bảo vệ, đường đi và ranh giới tin cậy**, không chỉ danh sách mẫu tấn công. Một thiết bị phát sóng trong tầm thu không có cùng quyền và tác động như một thiết bị đã được cấp role trong LAN.

### 11.1. Ma trận threat scenario

| ID | Tài sản/ranh giới | Tình huống rủi ro | Điều kiện cần xảy ra | Kiểm soát và bằng chứng |
| --- | --- | --- | --- | --- |
| W-01 | Corporate Wi-Fi | AP không được phê duyệt phát cùng SSID | Người dùng có thể nhầm AP và kết nối | Client profile Enterprise, kiểm tra server certificate, WIDS RF + association telemetry |
| W-02 | LAN production | Rogue AP cắm vào switch không bảo vệ | Cổng cấp mạng nội bộ cho thiết bị ngoài policy | Wired 802.1X, port controls, DHCP/flow, switch evidence |
| W-03 | Guest → production | Guest client truy cập VLAN/zone nhạy cảm | Firewall/ACL/role cấu hình quá rộng | Segmentation default deny, negative connectivity tests |
| W-04 | WLAN identities | Credential/certificate bị lạm dụng | Danh tính có thể xác thực sai người/thiết bị | PKI lifecycle, NAC/AAA audit, endpoint investigation |
| W-05 | IoT fleet | Thiết bị IoT chưa quản lý vào mạng rộng | Shared PSK/ngoại lệ được cấp VLAN quá mức | Inventory IoT, NAC/role, network isolation, application authorization |
| W-06 | Control plane | Controller/WIDS account bị sửa policy trái phép | Quyền quản trị quá rộng, audit thiếu | MFA, RBAC, change diff, SIEM alerts |
| W-07 | Wireless availability | Nhiều client rớt kết nối bất thường | RF interference, cấu hình lỗi hoặc can thiệp | PMF theo thiết kế, RF metrics, controller/session logs |
| W-08 | Monitoring coverage | Sensor bị tắt/không hỗ trợ băng mới | Có khoảng trống giám sát | Heartbeat, survey, channel/band coverage audits |
| W-09 | Tính riêng tư | Log probe/identity bị thu thập hoặc chia sẻ quá mức | Query/export không được kiểm soát | Data minimization, retention, RBAC, export audit |
| W-10 | Định danh | MAC randomization khiến gán sai owner | SIEM join theo MAC/OUI mà bỏ qua time/session | EAP-TLS/MDM identity, confidence annotation, event-time joins |
| W-11 | Response automation | SIEM tự cô lập cổng chứa thiết bị quan trọng từ RF alert sai | Không có human review/scope/rollback | Approval, dependency check, dry-run, time-limited change |
| W-12 | Hybrid/campus connectivity | AP ở chi nhánh gửi log muộn, SIEM gộp nhầm | WAN lag, clock skew, collector retry | Event time, buffer, dedup và data quality |

### 11.2. STRIDE cho mạng không dây

- **Spoofing:** AP tự nhận SSID/BSSID giống mạng công ty, hoặc thiết bị dùng danh tính/credential không hợp lệ.
- **Tampering:** thay WLAN security profile, VLAN/NAC role hoặc controller config trái quyền.
- **Repudiation:** không truy ra ai cấp quyền vào Corporate WLAN vì chỉ có MAC ngẫu nhiên và thiếu RADIUS/session logs.
- **Information disclosure:** client kết nối nhầm AP; log chứa danh tính/thiết bị hoặc traffic riêng tư bị lộ.
- **Denial of Service:** AP/controller hoặc RF bị quá tải/gián đoạn; phản ứng WIPS quá mạnh có thể trở thành nguyên nhân gián đoạn.
- **Elevation of privilege:** Guest/IoT hoặc thiết bị ngoài danh sách được cấp production role nhờ policy sai hoặc quyền quản trị bị lạm dụng.

STRIDE giúp đặt câu hỏi **đường tấn công nào cần thêm điều kiện**. Chẳng hạn một AP giả tên chỉ tạo cơ hội nhầm kết nối; để chiếm credential hoặc truy cập dữ liệu, còn phụ thuộc EAP server validation, mã hóa, người dùng, ứng dụng và các kiểm soát khác.

### 11.3. Attack tree mức phòng vệ

~~~mermaid
flowchart TD
    A["Mục tiêu rủi ro: thiết bị không được phép\ntruy cập hoặc ảnh hưởng WLAN"] --> B{"Đường tiếp cận"}
    B --> C["Qua RF/SSID"]
    B --> D["Qua LAN/uplink"]
    B --> E["Qua danh tính hợp lệ bị lạm dụng"]
    C --> CF["WIDS, client profile,\nserver certificate validation"]
    D --> DF["Wired NAC, switch/port control,\nsegmentation, change audit"]
    E --> EF["PKI/AAA, posture,\nrole và authorization"]
    CF --> R["SIEM triage và evidence"]
    DF --> R
    EF --> R
    R --> S["Containment thuộc hạ tầng sở hữu\nvà rollback được phê duyệt"]
~~~

Sơ đồ chỉ mô tả **điểm cần bảo vệ**, không phải hướng dẫn tạo AP giả hoặc khai thác mạng người khác.

### 11.4. Residual risk và kiểm soát quyền ứng dụng

Ngay cả khi khách/IoT được cấp đúng VLAN và AP là managed, hệ thống vẫn có thể gặp rủi ro từ lỗ hổng firmware, dịch vụ mặc định, tài khoản bị lộ hoặc phân quyền ứng dụng yếu. Vì vậy:

1. Áp policy mạng theo **least privilege** và giám sát east–west.
2. Xác thực/authorization ở ứng dụng và dịch vụ nhạy cảm, không chỉ dựa vào "đã kết nối SSID Corporate".
3. Quản lý bản vá và firmware của AP, controller, client và IoT.
4. Đưa log từ firewall/IDS/IPS/DNS/EDR vào SIEM để phát hiện hành vi sau kết nối.
5. Đặt mạng quản trị AP và hạ tầng AAA trong vùng bảo vệ riêng.

## 12. Triển khai monitoring có kiểm soát

### 12.1. Bước 1 — Xác định phạm vi và inventory

Trước khi bật cảnh báo:

- Kiểm kê **site, tầng, khu vực, SSID được cấp quyền, BSSID/radio, AP serial/controller, switch uplink và chủ sở hữu**.
- Liệt kê các **băng/kênh** mà hệ thống phải quan sát, bao gồm 6 GHz nếu WLAN tổ chức đang dùng và sensor hỗ trợ.
- Phân loại các mạng **Corporate, Guest, IoT, Quarantine và Management**.
- Ghi những mạng được phép xuất hiện gần khu vực: AP của đơn vị thuê chung, sự kiện nhà thầu hoặc mạng của khách.
- Quy định chuẩn WPA/802.1X/PMF, CA/certificate, role, VLAN và NAC policy mong đợi.
- Gắn quyền quản trị inventory và quy trình onboard/offboard AP, IoT, BYOD, thiết bị sự kiện.
- Xác định mục tiêu **privacy, retention và quyền điều tra** được chấp thuận.

Inventory không được xây chỉ từ một bản scan RF; nên lấy nguồn quản trị đáng tin và đối chiếu thực tế theo kỳ.

### 12.2. Bước 2 — Khảo sát coverage cảm biến

Khảo sát theo khu vực:

| Câu hỏi | Cách xác minh |
| --- | --- |
| Sensor quét băng/kênh nào? | Cấu hình radio và kết quả RF survey từ công cụ được cấp quyền |
| Có theo dõi được AP mới ở tầng/khu vực cần bảo vệ? | Đặt thiết bị test được cấp phép hoặc phát synthetic test event phù hợp, không quét mạng người khác |
| Sensor có thấy nhiều BSSID của managed AP? | So RF observations với controller inventory |
| Sensor có giảm coverage khi phục vụ traffic? | Theo dõi radio mode, scan schedule, channel utilization |
| Có blind spot khi DFS/channel changes hoặc triển khai 6 GHz? | Test monitoring capability theo thiết bị và quy định địa phương |
| WAN/collector mất kết nối có thông báo không? | Heartbeat tests, queue depth và event delivery alerts |
| Có vị trí nào thu sóng ngoài phạm vi tổ chức? | Review chính sách quyền riêng tư và phạm vi xử lý dữ liệu |

**Không kiểm thử bằng deauthentication hoặc gây nhiễu mạng lân cận.** Có thể dùng một AP lab được phép phát SSID thử nghiệm hoặc replay synthetic observation trong SIEM, sau đó đo liệu detector tạo đúng case hay không.

### 12.3. Bước 3 — Thiết lập đường thu thập đáng tin

Kết nối controller, sensor, NAC/RADIUS, switch, DHCP và firewall bằng các phương thức export log được hỗ trợ. Kiểm tra:

1. **Đồng bộ thời gian** (UTC trong SIEM và clock sync ở thiết bị).
2. **Nguồn có thể xác minh**: collector biết log đến từ AP/controller nào, không chấp nhận sự kiện giả từ người dùng ngoài.
3. **Truyền an toàn**: xác thực và mã hóa khi hỗ trợ; credential ingest có quyền tối thiểu.
4. **Buffer/retry/dedup**: log không bị mất im lặng khi WAN/collector đứt; không nhân đôi event sau retry.
5. **Schema mapping**: phân biệt seen, associated, authenticated, authorized, denied, disconnected và contained.
6. **Data quality**: nếu thiếu switch evidence thì trạng thái rogue-connected phải là **chưa xác minh**.

### 12.4. Bước 4 — Detection-only trước, enforcement sau

Giai đoạn đầu nên dùng **alert-only/count** để hiểu baseline và false positives. Có thể bật một số network access controls ngay từ đầu theo tiêu chuẩn tổ chức (ví dụ NAC không cho client thiếu identity vào VLAN production); không cần tắt các lớp bảo vệ hiện hữu chỉ vì WIDS đang ở chế độ quan sát.

Sau khi có evidence về rule:

- Đưa SSID/BSSID đã được xác minh hợp lệ vào inventory; **không** tự cho phép SSID chỉ vì xuất hiện nhiều lần.
- Tách rule "unknown AP RF" khỏi rule "unapproved wired AP" và "unauthorized Corporate association".
- Tuning theo site, band, role và thời gian thay đổi; ghi chủ owner.
- Xây test cases cho AP hợp lệ mới, hotspot lân cận, client random MAC, auth fail, rogue AP đã xác minh, sensor mất log.
- Thiết lập quy trình phê duyệt containment đối với cổng wired, NAC/quarantine hoặc đổi WLAN profile.

### 12.5. Bước 5 — Kiểm thử trước và sau thay đổi

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Thêm AP quản lý có ticket, serial và cấu hình chuẩn | Inventory cập nhật; không bị phân loại rogue sau đồng bộ |
| AP test chưa duyệt xuất hiện trong RF, không uplink LAN | Alert quan sát hoặc nghi vấn, **không** khẳng định có wired access |
| Cổng wired nối thiết bị không được duyệt | Wired NAC chặn/giới hạn theo policy và tạo log |
| Client có cert hợp lệ, profile đúng | Corporate WLAN auth success và role phù hợp |
| Client thiếu cert hoặc sai server validation | Không được xác thực vào role production |
| Guest client thử kết nối vùng quản trị | Firewall/segmentation deny đúng |
| Thiết bị IoT được duyệt | Có thể liên lạc đúng broker/dịch vụ, không đi rộng vào production |
| MAC client thay đổi theo OS | Không nhân đôi case hoặc gán nhầm owner nếu identity/session chứng minh |
| WIDS sensor hoặc collector ngừng gửi heartbeat | SIEM báo mất coverage, không kết luận không có AP lạ |
| Phép thử khôi phục từ quarantine | Role/port trở về trạng thái đúng theo phê duyệt, không gián đoạn ngoài phạm vi |

### 12.6. Bước 6 — Vận hành theo vòng đời

Khi đổi controller, AP firmware, SSID, security profile, EAP/CA, thêm băng 6 GHz, chuyển switch/uplink, triển khai MDM, thêm chi nhánh hoặc đổi SIEM schema, phải **review detection và coverage**. Một rule từng đúng có thể lỗi khi thiết bị được thay thế và BSSID thay đổi, hoặc RADIUS log đổi format.

Đặt **change version**, owner, ngày review, ngưỡng sức khỏe và các phép thử regression trong tài liệu vận hành. Các exception cho hội nghị/nhà thầu cần có thời hạn; sau sự kiện phải thu hồi quyền và rà lại thiết bị còn xuất hiện.

## 13. Đo lường, điều tra lỗi và chất lượng phát hiện

### 13.1. Metric cần theo dõi

| Chỉ số | Diễn giải | Lưu ý |
| --- | --- | --- |
| Managed AP inventory coverage | Tỷ lệ AP theo danh sách quản trị được giám sát và có liên kết site | Không chỉ dựa số BSSID |
| RF sensor coverage theo band/channel | Khu vực/kênh có khả năng quan sát | Có thể có blind spot hoặc dwell time không đủ |
| New/unknown RF identities per site | Xu hướng AP/client chưa khớp inventory | Không đồng nghĩa số thiết bị vật lý hoặc số tấn công |
| Auth success/failure per SSID/identity | Chất lượng kết nối/điều kiện NAC | Auth failures có thể do cert/driver/RADIUS lỗi |
| Rogue wired attachment confirmed | Số trường hợp có bằng chứng uplink trái policy | Cần tiêu chuẩn xác minh rõ ràng |
| False positive rate đã được điều tra | Chất lượng detection và công sức SOC | Không dùng "case đóng" thay cho false positive |
| Time to detect/triage/contain | Hiệu quả quy trình theo mức nghiêm trọng | Không tối ưu tốc độ bằng cách tự chặn không kiểm soát |
| Sensor/collector heartbeat và lag | Mức độ tin cậy telemetry | Mất log phải tạo health alert |
| NAC role drift / policy violations | Thiết bị được gán quyền vượt thiết kế | Đối chiếu change calendar và IAM |
| User experience | Roaming failures, disconnects, authentication latency | Theo dõi tác động của rule/PMF/firmware changes |
| Quarantine impact / rollback success | Khả năng khôi phục truy cập hợp lệ | Không coi số thiết bị bị cô lập cao là thành tích |
| Log retention/access audit | Quản trị quyền riêng tư và dữ liệu | Giảm MAC/identity và dữ liệu nhạy cảm không cần thiết |

### 13.2. Các nguyên nhân tạo báo động sai

| Triệu chứng | Nguyên nhân thường gặp | Điều cần làm |
| --- | --- | --- |
| Nhiều AP "lạ" sau khi thay AP mới | BSSID/serial chưa đồng bộ inventory | Đối chiếu controller và ticket đổi thiết bị |
| Cùng SSID Corporate xuất hiện tại nhiều nơi | Nhiều AP hợp lệ cùng SSID, hàng xóm dùng tên trùng | Kiểm tra managed AP ID, security profile, client session |
| Một người dùng xuất hiện nhiều MAC | MAC randomization hoặc nhiều adapter/interface | Liên hệ session/EAP-TLS/MDM, không dựa OUI |
| 802.1X failed tăng sau giờ cập nhật | CA/certificate hết hạn, RADIUS timeout, profile thay đổi | Kiểm tra AAA health, chứng chỉ và drift |
| Vùng RF báo deauth tăng | Roaming, channel change, driver, PMF mismatch, nghẽn | Xem RF/AP metrics và timeline sự cố |
| RSSI của AP lạ thay đổi mạnh | Multipath, vật cản, sensor chuyển kênh | Không suy ra di chuyển hoặc vị trí chính xác |
| Switch log có MAC giống BSSID ngoài RF | AP có MAC radio/uplink khác hoặc có spoof/mapping sai | Xác minh physical port/serial và policy |
| Sensor nhìn rất ít thiết bị mới | Mất RF coverage, sai radio mode, collector lỗi | Heartbeat, survey, scan config |
| WLAN log ghi client đã auth nhưng firewall không thấy | Local switching, VLAN, routing, log point, policy | Vẽ đường traffic thực; không kết luận client không kết nối |
| Cùng một case được mở nhiều lần | Event retry hoặc nhiều sensor nhận cùng frame | Dedup/grouping theo time/site/source với raw event references |
| Sự kiện đến muộn sau mất WAN | Buffer/replay, clock skew | Dùng event-time, lưu ingest-time và cảnh báo lag |
| Guest hotspot xuất hiện nhưng không có client doanh nghiệp | Neighbor hoặc hotspot cá nhân | Giới hạn điều tra theo quyền, không xử lý trái phạm vi |

### 13.3. Chuỗi kiểm tra khi phát hiện vấn đề

~~~text
Alert "unknown wireless device"
  |
  +-- Sensor/radio/collector khỏe và thời gian đúng?
  |      |
  |      +-- Không: xử lý telemetry gap trước
  |
  +-- Event là beacon/probe hay authenticated session?
  |      |
  |      +-- Chỉ RF: so inventory, security profile, site
  |      |
  |      +-- Session: so RADIUS, NAC role, device identity
  |
  +-- Có bằng chứng AP/client nối vào LAN của tổ chức?
  |      |
  |      +-- Chưa: không tự gán rogue wired / compromise
  |      |
  |      +-- Có: xác minh port, VLAN, DHCP, policy, asset
  |
  +-- Có đường tới tài sản nhạy cảm trái thiết kế?
  |      |
  |      +-- Có: ưu tiên containment trong phạm vi được duyệt
  |      |
  |      +-- Không/chưa đủ: theo dõi, làm rõ owner và bằng chứng
  |
  +-- Ghi quyết định, kiểm tra tác động, cập nhật detection
~~~

### 13.4. Phân biệt lỗi WLAN, DNS và ứng dụng

Một client có thể:

1. Nhìn thấy Corp-Secure.
2. Association thành công với AP quản lý.
3. 802.1X thành công và nhận role/VLAN.
4. Nhận IP/DNS từ DHCP.
5. DNS phân giải tên dịch vụ nội bộ.
6. Kết nối TCP/TLS tới API.
7. Bị ứng dụng từ chối HTTP 403.

Đây là **những bước độc lập**. Lỗi ở bước 7 không có nghĩa thiết bị là rogue hoặc WPA3/802.1X bị lỗi; có thể quyền ứng dụng hoạt động đúng. Ngược lại, auth success vào Corporate WLAN không chứng minh client được phép đọc một database. Kết hợp NAC/firewall/IDS/DNS/application logs để phân loại đúng tầng.

### 13.5. Bảo vệ dữ liệu giám sát

Các bản ghi gồm MAC, username, location/sensor, thời điểm và lịch sử di chuyển có thể phản ánh thói quen người dùng. Chính sách nên:

- Thu thập **dữ liệu tối thiểu** để phát hiện, xử lý và kiểm toán rủi ro.
- Gắn retention và access control theo mục đích (vận hành, SOC, điều tra).
- Pseudonymize/mask khi báo cáo tổng hợp không cần danh tính chi tiết.
- Audit việc truy vấn/export dữ liệu định danh và phân quyền phân tích location.
- Tránh lưu mật khẩu, EAP secret, packet payload hoặc credential trong telemetry không cần thiết.
- Chỉ dùng dữ liệu RF từ phạm vi được phép, không dùng kỹ thuật theo dõi cá nhân ngoài chính sách.

Thiết bị "lạ" không trao cho quản trị viên quyền thu thập mọi thông tin của người ở gần. Mọi thao tác cần phù hợp quy định và mục đích an ninh đã phê duyệt.

## 14. Bài lab tổng hợp: xác minh thiết bị lạ bằng sự kiện giả lập

Lab này chỉ dùng **synthetic event data** để người học mô phỏng SIEM/WIDS correlation, không cần tạo AP giả, ghi gói của bên thứ ba, phát deauth hoặc kết nối thử vào mạng không được phép.

### 14.1. Sơ đồ lab và chính sách mong đợi

~~~text
Khu vực HN-F3:
  Managed AP:
    AP-F3-014 (serial LAB-AP-014)
    Corp-Secure BSSID 02:1A:2B:3C:40:10
    Guest       BSSID 02:1A:2B:3C:40:11
    Wired uplink sw-f3-02 port 1/0/14 (approved)

  RF sensor:
    rf-sensor-f3-02

  Corporate WLAN:
    WPA2/WPA3-Enterprise theo policy được duyệt
    RADIUS + NAC role Corp
    Chỉ các workload/người dùng đúng quyền vào API nội bộ

  Guest WLAN:
    Isolated guest VLAN 230
    Không được truy cập vùng Management/Data

  IoT WLAN:
    Role IoT chỉ được truy cập IoT broker qua cổng được duyệt

  Phát hiện mới:
    BSSID 02:7A:30:40:50:66 phát Corp-Secure (chưa có inventory)
~~~

**Không dùng địa chỉ MAC lab làm bằng chứng định danh thực.** AP quản lý có thể phát nhiều BSSID, một BSSID RF không nhất thiết trùng MAC Ethernet, và không có cách ánh xạ an toàn phổ quát giữa hai loại MAC cho mọi thiết bị.

### 14.2. Bộ sự kiện đầu vào

~~~json
[
  {
    "id": "L01",
    "time": "2026-11-28T03:00:00Z",
    "source": "wids",
    "sensor": "rf-sensor-f3-02",
    "site": "HN-F3",
    "event": "ap_seen",
    "ssid": "Corp-Secure",
    "bssid": "02:7A:30:40:50:66",
    "security_profile": "different_from_corporate_baseline",
    "rssi_dbm": -60
  },
  {
    "id": "L02",
    "time": "2026-11-28T03:00:10Z",
    "source": "controller_inventory",
    "site": "HN-F3",
    "event": "inventory_check",
    "bssid": "02:7A:30:40:50:66",
    "managed_match": false
  },
  {
    "id": "L03",
    "time": "2026-11-28T03:01:00Z",
    "source": "switch",
    "site": "HN-F3",
    "event": "unapproved_device_link",
    "switch_id": "sw-f3-02",
    "port": "1/0/22",
    "vlan": 120,
    "physical_device_verified": false,
    "bssid_to_wired_device_mapping": "unknown"
  },
  {
    "id": "L04",
    "time": "2026-11-28T03:02:00Z",
    "source": "radius",
    "event": "authentication_failure",
    "client_mac": "02:10:20:30:40:50",
    "ssid": "Corp-Secure",
    "reason": "certificate_expired",
    "client_identity": "lab-device-42"
  },
  {
    "id": "L05",
    "time": "2026-11-28T03:02:10Z",
    "source": "mdm",
    "event": "managed_device_record",
    "device_id": "lab-device-42",
    "certificate_status": "renewal_pending",
    "owner": "training-lab-user"
  },
  {
    "id": "L06",
    "time": "2026-11-28T03:03:00Z",
    "source": "wids",
    "sensor": "rf-sensor-f3-02",
    "site": "HN-F3",
    "event": "ap_seen",
    "ssid": "Visitor-WiFi",
    "bssid": "02:EE:20:30:40:50",
    "rssi_dbm": -71
  },
  {
    "id": "L07",
    "time": "2026-11-28T03:03:10Z",
    "source": "approved_event_calendar",
    "site": "HN-F3",
    "event": "approved_vendor_demo",
    "ssid": "Visitor-WiFi",
    "valid_until": "2026-11-28T05:00:00Z",
    "owner": "facilities-and-network"
  },
  {
    "id": "L08",
    "time": "2026-11-28T03:04:00Z",
    "source": "firewall",
    "event": "deny",
    "source_vlan": 230,
    "destination_zone": "management",
    "protocol": "tcp",
    "destination_port": 443,
    "policy_id": "GUEST-MGMT-DENY"
  },
  {
    "id": "L09",
    "time": "2026-11-28T03:04:30Z",
    "source": "collector_health",
    "event": "missing_heartbeat",
    "observer_id": "rf-sensor-f2-01",
    "site": "HN-F2",
    "last_seen": "2026-11-28T02:45:00Z"
  },
  {
    "id": "L10",
    "time": "2026-11-28T03:05:00Z",
    "source": "controller",
    "event": "authenticated_client",
    "client_mac": "02:99:88:77:66:55",
    "identity_verified": "lab-device-99",
    "ssid": "Corp-Secure",
    "assigned_role": "Corp"
  },
  {
    "id": "L11",
    "time": "2026-11-28T03:06:00Z",
    "source": "controller",
    "event": "authenticated_client",
    "client_mac": "02:99:88:77:66:56",
    "identity_verified": "lab-device-99",
    "ssid": "Corp-Secure",
    "assigned_role": "Corp",
    "note": "device profile changed; certificate binding verified in lab"
  }
]
~~~

Tất cả bản ghi là **synthetic**, đặc biệt trường "physical_device_verified": false ở L03 chỉ ra **chưa có bằng chứng cổng 1/0/22 là AP mang BSSID ở L01**. Việc có hai sự kiện gần nhau trong thời gian/site chỉ gợi ý điều tra, không được tự gắn kết chúng thành một đối tượng vật lý.

### 14.3. Kết quả tương quan mong đợi

| Nhóm case | Dữ liệu | Kết luận tạm thời chính xác | Hành động tiếp theo |
| --- | --- | --- | --- |
| **CASE-A: SSID impersonation suspected** | L01 + L02 | AP RF phát Corp-Secure với profile khác, không khớp inventory | Kiểm tra RF/site, controller, client liên kết, owner; không khẳng định evil twin thành công |
| **CASE-B: wired attachment unapproved** | L03 | Có cổng switch với thiết bị chưa được phê duyệt; chưa chứng minh liên hệ CASE-A | Xác minh asset/uplink/port bằng nguồn quản trị và onsite, đánh giá VLAN |
| **CASE-C: client auth failure cần hỗ trợ** | L04 + L05 | Managed device có chứng chỉ chờ gia hạn; không có bằng chứng xâm nhập | Theo quy trình PKI/MDM, hỗ trợ chứng chỉ, kiểm tra auth sau renew |
| **CASE-D: AP tạm thời theo lịch** | L06 + L07 | Có lịch sự kiện hợp lệ phù hợp SSID/site/time, nhưng vẫn cần kiểm tra owner thực tế | Gắn event ticket, theo dõi tới expiry; không blanket trust tất cả BSSID cùng SSID |
| **CASE-E: segmentation hoạt động** | L08 | Guest→management đã bị firewall deny theo rule | Giữ log kiểm chứng, xem có nguồn cố ý thử trái quyền không |
| **CASE-F: blind spot** | L09 | Sensor HN-F2 không gửi heartbeat, thiếu khả năng giám sát | Khôi phục sensor/collector và ghi coverage gap |
| **CASE-G: client MAC đổi** | L10 + L11 | Cùng identity đã được xác minh trong lab dù MAC đổi | Không tạo incident nhân đôi; giữ từng session với timestamp |

**Tình huống đáng chú ý nhất:** CASE-A và CASE-B có thể liên quan nhưng **thiếu mapping đáng tin**. Dù CASE-B là một unapproved wired attachment cần xử lý theo policy, nó không tự chứng minh CASE-A là AP cắm trên đúng port đó.

### 14.4. Thuật toán giả cho pipeline tương quan

~~~text
input:
  RF observations
  controller and NAC sessions
  managed AP inventory and asset registry
  switch port records
  RADIUS/MDM records
  approved changes
  health telemetry

for event in event_time_order:
    validate_source_and_schema(event)
    normalize_time_and_site(event)
    preserve_raw_event_reference(event)

    if event.type == ap_seen:
        check_managed_inventory(event.bssid, event.site, event.time)
        check_expected_ssid_security_profile(event.ssid, event.site)
        create_rf_observation_if_unknown()

    if event.type == authenticated_client:
        join_using_verified_session_and_device_identity()
        do_not_assume_mac_equals_person()

    if event.type == unapproved_device_link:
        create_wired_attachment_case()
        require_verified_physical_or_controller_mapping()
        before_claiming_same_device_as_rf_observation()

    if event.type == missing_heartbeat:
        raise_telemetry_health_case()

before_containment:
    confirm_authorized_asset_and_network_scope()
    assess_business_dependencies_and_impact()
    require_appropriate_approval()
    record_rollback_and_success_criteria()
~~~

Pseudo-code không gắn với ngôn ngữ lập trình hay sản phẩm SIEM nào. Trong môi trường có nhiều sensor, cần cơ chế **event dedup, late events, time skew, enrichment provenance** và phân biệt "không có dữ liệu" với "không có sự kiện".

### 14.5. Bộ kiểm thử detection

| Test | Dữ liệu và thay đổi giả lập | Kết quả mong đợi |
| --- | --- | --- |
| DT01 | Chỉ L01, không có controller inventory | Phân loại **unknown AP**, không khẳng định rogue connected |
| DT02 | L01 + L02 | Cảnh báo AP lạ có SSID/profile nghi vấn, giữ evidence |
| DT03 | L01 + L03 nhưng physical mapping chưa xác minh | **Hai dấu hiệu độc lập**, không tự ghép chúng thành cùng thiết bị |
| DT04 | Thêm mapping onsite đã được xác nhận cho L01–L03 | Nâng độ tin cậy rogue wired AP sau khi review |
| DT05 | L04 + L05 | Hỗ trợ PKI/MDM thay vì mặc định gán brute-force |
| DT06 | L06 + L07, ticket còn hiệu lực | Có thể phân loại event được duyệt **khi xác minh owner**, không suppress vĩnh viễn |
| DT07 | L07 hết hạn nhưng L06 còn xuất hiện | Mở case rà lại/tắt thiết bị tạm nếu thuộc quyền |
| DT08 | L08 | Ghi nhận deny ở Guest→Management, không kết luận đã compromise |
| DT09 | L09 | Cảnh báo sức khỏe sensor, ghi khoảng trống coverage |
| DT10 | L10 + L11 và identity binding đã xác minh | Nhận diện cùng device asset khi phù hợp, giữ hai session riêng |
| DT11 | L01 bị sensor retry hai lần | Dedup RF event nhưng giữ số lần quan sát và sensor |
| DT12 | L03 bị ingest trễ 20 phút | Correlation theo event time, ghi độ trễ để đánh giá |
| DT13 | L01 xuất hiện ở hai site do sensor metadata sai | Đánh dấu data-quality anomaly; không suy di chuyển vật lý tức thì |
| DT14 | Client unknown thử auth rồi bị RADIUS reject | Không có bằng chứng client được vào Corporate role |
| DT15 | NAC gán role Corp cho client thiếu posture theo policy | High-priority policy mismatch, cần xác minh route/ACL và owner |
| DT16 | AP khác SSID nhưng nối cổng production ngoài policy | Vẫn phải phát hiện wired rogue; không chỉ tìm SSID trùng tên |

### 14.6. Bài thực hành ở máy được cấp quyền

Trên **máy Windows do bạn quản lý và được phép kiểm tra**, có thể dùng lệnh quan sát cấu hình mạng của chính máy:

~~~powershell
# Kiểm tra trạng thái kết nối WLAN của máy đang dùng.
netsh wlan show interfaces

# Xem các mạng được hệ điều hành quét và liệt kê.
netsh wlan show networks mode=bssid

# Kiểm tra IP và DNS theo giao diện đã được cấp quyền.
ipconfig /all
~~~

Các lệnh này không bảo đảm hiển thị đầy đủ RF evidence mà một WIDS chuyên dụng có, và hệ điều hành/driver có thể không trả mọi BSSID/PMF attribute. **Không dùng danh sách BSSID quanh máy để suy ra ai sở hữu hoặc ở phòng nào**. Việc scan mạng trong môi trường có quy định riêng vẫn phải tuân theo quyền và chính sách hạ tầng.

Trên máy Linux được cấp phép, tùy môi trường có thể dùng:

~~~bash
# Chỉ xem trạng thái Wi-Fi qua NetworkManager trên máy của bạn nếu có.
nmcli device status
nmcli device wifi list

# Xem địa chỉ IP và tuyến của chính máy.
ip address show
ip route
~~~

Không phải mọi máy Linux có NetworkManager hoặc card Wi-Fi hỗ trợ scan. Lệnh xem Wi-Fi có thể tạo quét thông thường theo cách driver quản lý; không tương đương thu thập toàn bộ gói hoặc cố ý thử xác thực AP lạ.

### 14.7. Câu hỏi trả lời sau lab

Viết bản phân tích một trang:

1. Những event nào là **RF observation**, những event nào là **bằng chứng xác thực** hoặc **wired network link**?
2. Có đủ căn cứ để gọi L01 là **rogue wired AP** chưa? Thiếu chứng cứ gì?
3. L04 có chứng minh client bị chiếm quyền hay đang thử mật khẩu không? Những nguyên nhân lành tính nào đáng kiểm tra?
4. L06 có nên bị WIPS tự ngắt ngay không? Ticket và ownership quyết định gì?
5. Vì sao L10 và L11 nên gắn cùng asset ID nhưng vẫn lưu hai phiên kết nối riêng?
6. Nếu L09 kéo dài, có thể nói "tầng 2 không có AP lạ" hay không?
7. Đề xuất **một hành động containment hợp pháp, hạn chế tác động** cho CASE-B nếu onsite xác minh thiết bị không được cấp quyền.
8. Tạo ma trận test **5 allow / 5 deny** cho Corporate/Guest/IoT/quarantine; không dùng kỹ thuật tấn công.

## 15. Tình huống vận hành thực tế

### Tình huống A — Phòng họp xuất hiện nhiều SSID không có trong inventory

Sáng thứ Hai, WIDS tăng 40% số BSSID chưa nhận diện tại tầng hội nghị. Ban tổ chức đang có nhiều đoàn khách và hotspot cá nhân.

**Phân tích:** biến động số BSSID không tương đương 40% số thiết bị độc hại. Đối chiếu lịch sự kiện, vị trí sensor, SSID/security, cổng switch được cấp và phiên Corporate của thiết bị công ty. Nếu không có bằng chứng truy cập trái phép, phân loại observation và điều chỉnh baseline theo site. Không phát deauth đối với hotspot của khách.

### Tình huống B — AP giống Corp-Secure nhưng client không kết nối được

WIDS phát hiện BSSID không quản lý quảng bá Corp-Secure và một số laptop báo thông báo cảnh báo chứng chỉ khi thử kết nối.

**Phân tích:** cần điều tra khả năng impersonation, nhưng cũng kiểm tra CA/certificate server RADIUS và thay đổi profile của AP hợp lệ. Tại endpoint, yêu cầu **không bỏ qua cảnh báo chứng chỉ**, chỉ dùng cấu hình WLAN chính thức và báo nhóm IT. SOC/WLAN lưu RF evidence, kiểm tra managed controller, identity log và mức ảnh hưởng; không kết luận credential bị đánh cắp nếu không có bằng chứng.

### Tình huống C — Máy in IoT dùng PSK chung vào VLAN production

Một máy in mới được nhân viên triển khai bằng shared PSK. NAC gán VLAN mặc định cho phép truy cập thêm các server production ngoài phạm vi in.

**Phân tích:** rủi ro chính là **quyền mạng quá rộng**, dù máy in không cố tình tấn công. Đưa máy in vào quy trình onboarding, xác định owner và phiên bản firmware, đổi role/VLAN IoT phù hợp, siết firewall theo máy chủ in được phê duyệt và kiểm tra luồng in bình thường. Không chỉ thêm MAC máy in vào allowlist.

### Tình huống D — Hệ thống WIDS báo "deauth attack" sau nâng cấp AP

Sau cập nhật controller/firmware, một số client cũ rớt kết nối; số event disassociation tăng, và WIDS đặt nhãn cảnh báo.

**Phân tích:** so PMF requirements, roaming/802.11r, channel management, driver client, RF load, RADIUS latency và change ticket. Nếu phát hiện thiết lập PMF yêu cầu khiến client không tương thích, cần kế hoạch xử lý thiết bị/SSID riêng được duyệt thay vì nới bảo mật toàn mạng tùy tiện. Không kết luận có AP lạ phát frame can thiệp khi chưa có dữ liệu.

### Tình huống E — Wi-Fi Guest truy cập được ứng dụng quản trị

Firewall cho phép nhầm Guest VLAN tới dashboard quản trị. Một client chưa được quản lý dùng Guest SSID gọi được TCP/443 của dashboard.

**Phân tích:** lỗi phân đoạn xảy ra ngay cả khi AP hoàn toàn được quản lý và không có evil twin. Kiểm tra effective ACL/firewall/routing, thu hẹp role mạng, yêu cầu MFA/authorization ở dashboard, test guest→management bị deny và corporate admin→management vẫn hoạt động.

### Tình huống F — Sensor không nhìn thấy hotspot ở băng 6 GHz

Một khu vực chuyển sang AP hỗ trợ 6 GHz nhưng RF sensor cũ chỉ có khả năng quét 2,4/5 GHz. Dashboard cho thấy "không có thiết bị mới".

**Phân tích:** đây là **khoảng trống giám sát**; không có alert không có nghĩa không có AP mới. Kiểm kê hỗ trợ băng/kênh, cập nhật khảo sát coverage, firmware/hardware và kiểm thử bằng thiết bị test được cấp phép. Theo dõi metric sensor capability thay vì chỉ kiểm số event.

### Tình huống G — Client được xem là "lạ" sau khi đổi MAC nhưng identity không đổi

Laptop công ty thay địa chỉ MAC riêng cho một profile Wi-Fi, khiến SIEM tạo nhiều case unknown clients. RADIUS vẫn xác thực thiết bị bằng chứng chỉ quản lý hợp lệ.

**Phân tích:** cần cập nhật entity resolution theo **device certificate/session ID** và thời gian, không tự vô hiệu hóa MAC randomization để giảm alert. Lưu lý do gắn hai phiên cùng một asset; tránh gán dữ liệu theo chuỗi certificate subject không được xác minh.

### Tình huống H — Rogue AP nghi vấn xuất hiện đồng thời với cổng switch mới

WIDS thấy AP chưa duyệt gần phòng kỹ thuật; switch ở cùng tầng có một cổng mới nhận DHCP lease và một MAC lạ.

**Phân tích:** đây là hai tín hiệu đáng ưu tiên nhưng chưa đủ để chứng minh cùng một thiết bị. NOC/onsite xác định cổng, thiết bị, uplink, VLAN và quyền kết nối. Nếu có bằng chứng AP không được duyệt nối vào production, áp wired NAC hoặc vô hiệu đúng port sau review tác động và phê duyệt; lưu log để kiểm tra lưu lượng đã đi qua trước khi xử lý.

## 16. Checklist triển khai và quản trị định kỳ

### 16.1. Inventory, phạm vi và quyền sở hữu

- [ ] Mọi AP quản lý có serial/controller ID, site/tầng, BSSID theo radio, loại SSID và uplink port được kiểm kê.
- [ ] Có quy trình bổ sung/xóa AP, BYOD/IoT, thiết bị nhà thầu và hotspot tạm thời.
- [ ] Có danh sách SSID/security profile đã phê duyệt theo khu vực, cả Corporate, Guest, IoT và Management.
- [ ] Quy trình thay controller/firmware/AP có cập nhật inventory, policy và detection.
- [ ] Xác định ranh giới khu vực được phép thu thập/điều tra RF và chính sách dữ liệu cá nhân.
- [ ] Inventory có owner, lần xác minh gần nhất, nguồn dữ liệu và thời gian hiệu lực.

### 16.2. Hạ tầng WLAN và bảo mật kết nối

- [ ] Corporate WLAN dùng cơ chế xác thực/mã hóa phù hợp, kiểm tra certificate RADIUS ở client.
- [ ] PKI/EAP-TLS hoặc phương thức Enterprise được duyệt có cấp/thu hồi certificate và kiểm soát identity.
- [ ] Profile PMF, roaming, cipher/AKM và các ngoại lệ legacy được review có kiểm thử.
- [ ] Guest/IoT/Quarantine tách mạng; default deny với các vùng production/management không được phép.
- [ ] Wired switch port và cổng AP có NAC/port policy/802.1X phù hợp để giảm rogue wired AP.
- [ ] Management plane AP/WLC/RADIUS/NAC/SIEM có RBAC, MFA khi phù hợp, audit và cập nhật bảo mật.
- [ ] Đường DNS, DHCP, NAT/VPN, firewall và ứng dụng được kiểm tra độc lập với trạng thái kết nối Wi-Fi.

### 16.3. WIDS/WIPS và cảm biến

- [ ] Biết sensor nào quét băng/kênh nào, nơi đặt, chế độ và thời điểm quét.
- [ ] Có RF survey và thử khả năng nhìn thấy AP test được cấp quyền, không chỉ dựa vào heartbeat.
- [ ] Biết giới hạn khi theo dõi 6 GHz hoặc thiết bị đa radio/multi-link.
- [ ] Rule phân biệt RF-only unknown AP, suspicious SSID impersonation và **confirmed rogue wired AP**.
- [ ] Có correlation với controller, RADIUS/NAC, switch, DHCP, firewall và inventory.
- [ ] Không coi MAC/OUI/SSID/RSSI là bằng chứng nhận diện tuyệt đối.
- [ ] Không bật auto-deauth/jamming ngoài phạm vi được duyệt; ưu tiên containment tại hạ tầng sở hữu.
- [ ] Có phát hiện sensor offline, thiếu kênh, queue đầy, parser lỗi và log trễ.

### 16.4. SIEM/SOC và phản ứng

- [ ] Event có thời gian, sensor/site, loại observation, identity/session, role và nguồn chứng cứ.
- [ ] Có event-time correlation, dedup, data-quality flag và evidence provenance.
- [ ] Có rule theo khu vực/rủi ro, owner, ngoại lệ có thời hạn và kiểm thử false positive.
- [ ] Các case phân biệt **observed, associated, authenticated, authorized, network reachable, compromised**.
- [ ] Có quy trình đối chiếu owner, review tác động, phê duyệt containment và rollback.
- [ ] Không tự chặn IP/MAC từ một RF alert đơn lẻ, đặc biệt khi endpoint hoặc VLAN dùng chung.
- [ ] Có negative tests Guest→Management, IoT→Production và client thiếu chứng chỉ→Corporate.
- [ ] Log MAC/location/identity được truy cập theo RBAC, giảm dữ liệu và giữ trong thời hạn cho phép.
- [ ] Sau incident có postmortem, kiểm tra sensor gap, cải tiến rule và chính sách mạng.

### 16.5. Sổ kiểm kê cảnh báo mẫu

| Tên use case | Phạm vi | Dữ liệu bắt buộc | Owner | Action mặc định |
| --- | --- | --- | --- | --- |
| Unknown AP observed | RF tại site | BSSID/SSID, sensor, time, inventory | WLAN team | Case/triage, không radio containment |
| Suspected SSID impersonation | Corporate SSID | RF profile, managed inventory, client evidence | WLAN + SOC | Điều tra, thông báo client theo policy |
| Unapproved wired AP | LAN/uplink | Switch/NAC, physical mapping, VLAN, owner | Network + SOC | Review kiểm soát port có phê duyệt |
| Unauthorized Corporate client | WLAN auth | RADIUS session, EAP result, NAC role, time | IAM/NAC + WLAN | Từ chối/quarantine theo policy |
| BYOD/IoT unknown | Guest/IoT/Onboarding | Device ID/owner, role, firewall | Endpoint/IoT owner | Onboarding và quyền mạng tối thiểu |
| WLAN security drift | AP/WLC config | Config diff, serial, change ticket | WLAN + Change mgmt | Điều chỉnh có kiểm soát |
| Monitoring blind spot | Sensor/WLC exporter | Heartbeat, last event, scan capability | WLAN monitoring | Khôi phục telemetry, ghi vùng bị ảnh hưởng |

## 17. Câu hỏi ôn tập

**Câu 1.** WIDS phát hiện SSID Corp-Secure từ một BSSID không có trong inventory. Đã đủ kết luận đây là rogue AP cắm vào LAN công ty chưa?

*Gợi ý:* Chưa. Cần phân biệt tín hiệu RF với wired uplink đã xác minh; SSID/BSSID có thể trùng, bị giả hoặc từ AP hợp lệ chưa đồng bộ inventory.

**Câu 2.** Rogue AP, evil twin và neighbor AP khác nhau thế nào?

*Gợi ý:* Rogue AP là AP không được cấp quyền, đặc biệt đáng lo khi nối mạng nội bộ; evil twin/impersonation tìm cách khiến client nhầm với mạng hợp lệ; neighbor AP có thể chỉ là mạng lân cận không liên quan.

**Câu 3.** Vì sao số lượng MAC trong RF log có thể vượt số thiết bị vật lý?

*Gợi ý:* MAC randomization, nhiều radio/BSSID, adapter và roaming, cùng dữ liệu trùng do collector.

**Câu 4.** Trong Corporate WLAN dùng 802.1X, dữ liệu nào giúp xác nhận một client có danh tính được cấp quyền?

*Gợi ý:* RADIUS authentication result, certificate/identity đã được xác minh, NAC role và session time từ nguồn được tin cậy. Không chỉ BSSID, SSID hoặc địa chỉ MAC.

**Câu 5.** PMF có ngăn được mọi AP phát SSID giả giống công ty không?

*Gợi ý:* Không. PMF bảo vệ một số management frame khi phiên thỏa điều kiện; không xác thực SSID/beacon hoặc thay thế server certificate validation.

**Câu 6.** Vì sao một RADIUS authentication failure không tự chứng minh client đang brute-force?

*Gợi ý:* Có thể do chứng chỉ hết hạn, đồng hồ, cấu hình EAP, driver, roaming hoặc RADIUS service lỗi. Cần xem session history và nguyên nhân.

**Câu 7.** Tại sao việc chỉ quét RF không đủ để xác định rogue AP đã vào VLAN production?

*Gợi ý:* RF observation không cho biết uplink; cần kiểm tra switch port, wired NAC, physical mapping, DHCP/firewall flow và zone.

**Câu 8.** Guest client đã kết nối thành công Guest SSID thì có được phép truy cập dashboard quản trị không?

*Gợi ý:* Không mặc định. Access control ở firewall/ACL/segmentation và quyền ứng dụng phải độc lập với việc association/authentication vào WLAN.

**Câu 9.** Vì sao cần kiểm soát cả AP ở mạng dây và thiết bị Wi-Fi đầu cuối?

*Gợi ý:* AP không được phép cắm vào LAN có thể bỏ qua WLAN controller/NAC; client đã kết nối Corporate vẫn có thể gây rủi ro nếu role hoặc quyền ứng dụng sai.

**Câu 10.** Một AP lạ xuất hiện mạnh RSSI ở phòng hội nghị. Có thể kết luận nó thuộc người ngồi gần sensor nhất không?

*Gợi ý:* Không. RSSI phụ thuộc công suất/vật cản/đa đường/anten; không dùng nó làm bằng chứng danh tính hoặc vị trí chính xác.

**Câu 11.** WIDS không gửi cảnh báo trong vài giờ. Có thể nói khu vực không có thiết bị lạ không?

*Gợi ý:* Chỉ khi đã xác nhận sensor/collector hoạt động và có coverage; "không có alert" không có nghĩa "không có sự kiện".

**Câu 12.** Vì sao không nên tự động phát deauth để chặn mọi hotspot lạ quanh trụ sở?

*Gợi ý:* Có thể làm gián đoạn mạng của bên thứ ba, vi phạm quy định và gây rủi ro an toàn; chỉ can thiệp trên hạ tầng và trong phạm vi được cấp quyền, ưu tiên network/identity containment.

**Câu 13.** Nếu client Wi-Fi được phép vào Corp VLAN nhưng API trả HTTP 403, nên sửa WLAN hay API?

*Gợi ý:* Xác định trước tầng nào từ chối. HTTP 403 có thể là authorization ứng dụng đúng, không phải lỗi Wi-Fi.

**Câu 14.** Vì sao một laptop có MAC mới nhưng EAP-TLS vẫn xác thực là cùng asset?

*Gợi ý:* Thiết bị có thể đổi MAC riêng, trong khi certificate/device identity được xác minh và quản lý ổn định theo session.

**Câu 15.** Một client IoT kết nối mạng bằng PSK đúng nhưng cần truy cập database production. Được cấp quyền chưa?

*Gợi ý:* Chưa. PSK/association không tương đương DB authorization hay firewall allow; chỉ mở luồng đã được duyệt.

**Câu 16.** Monitoring ở 2,4/5 GHz có đủ khi tổ chức bật 6 GHz không?

*Gợi ý:* Không thể khẳng định. Phải kiểm tra phần cứng/sensor, channel coverage, chế độ scanning, quy định radio và vùng phủ.

**Câu 17.** Vì sao một sự kiện RF tại tầng 3 và một sự kiện switch cổng mới tại tầng 3 chưa đủ để kết luận cùng thiết bị?

*Gợi ý:* Chỉ có quan hệ thời gian/địa điểm, thiếu physical mapping đáng tin giữa BSSID và MAC uplink/port; cần xác minh asset/onsite hoặc controller.

**Câu 18.** Dữ liệu nào cần giữ để điều tra mà không thu thập thông tin người dùng quá mức?

*Gợi ý:* Event time, nguồn sensor, identity đã xác minh khi cần, session/role/zone, rule/action, evidence ID; ẩn secret, giới hạn location/identity và retention.

## 18. Tổng kết

- **Monitoring thiết bị lạ** là bài toán **quan sát, xác minh danh tính, kiểm tra quyền và ranh giới mạng**, không chỉ liệt kê SSID hoặc MAC nhìn thấy trong không khí.
- **Unknown không đồng nghĩa malicious**. Cần phân biệt managed AP, neighbor AP, rogue AP đã xác minh uplink, evil twin nghi vấn, unauthorized client, BYOD và IoT theo bằng chứng.
- **WIDS/WIPS và RF sensor** cho thấy tín hiệu vô tuyến trong vùng phủ được thiết kế; muốn kết luận thiết bị đã vào LAN cần controller/NAC/RADIUS/switch/DHCP/firewall evidence phù hợp.
- **SSID, BSSID, RSSI, OUI và MAC** có giới hạn định danh; MAC randomization, multi-radio, nhiều BSSID và roaming có thể tạo false positive. Ưu tiên **identity/session đã xác thực** khi cần quy nguồn.
- **802.1X/EAP-TLS, WPA2/WPA3, kiểm tra certificate, PMF, VLAN/role và microsegmentation** là các lớp bảo vệ độc lập bổ trợ cho monitoring. PMF không tự chặn mọi SSID impersonation và kết nối Wi-Fi thành công không thay quyền ứng dụng.
- **SIEM correlation** cần event time, source provenance, asset owner, session identity, network path, rule action và data-quality flags. Sensor im lặng có thể do coverage gap.
- **Phản ứng an toàn** thường là quản lý tài khoản, NAC/quarantine, switch port, ACL hoặc kiểm tra onsite có phê duyệt trên hạ tầng tổ chức sở hữu; tránh tự ý deauth/jamming mạng của người khác.
- **Vận hành liên tục** cần inventory có owner, baseline theo site, thử cả trường hợp allow/deny, cập nhật sensor khi thay băng tần/firmware, cảnh báo health, kiểm soát thay đổi và bảo vệ dữ liệu cá nhân.
- **Kết quả tốt nhất** không phải số lượng "thiết bị lạ" bị chặn, mà là khả năng **phân biệt đúng rủi ro, kiểm chứng bằng chứng, giảm đường truy cập trái phép và duy trì tính sẵn sàng của WLAN hợp lệ**.
