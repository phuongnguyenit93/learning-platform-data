# Inline và out-of-band sensor trong IDS/IPS

## 1. Vì sao vị trí đặt sensor quan trọng?

**IDS (Intrusion Detection System)** là hệ thống phát hiện dấu hiệu xâm nhập hoặc hoạt động đáng ngờ và phát cảnh báo. **IPS (Intrusion Prevention System)** có thêm khả năng thực thi hành động phòng ngừa, chẳng hạn loại bỏ gói tin hoặc ngăn phiên kết nối, khi cơ chế và chính sách triển khai cho phép. Tuy nhiên, để đánh giá một hệ thống có thể chặn lưu lượng **ngay trên đường đi** hay chỉ quan sát được, phải nhìn vào **vị trí đặt sensor**:

- **Inline sensor** nằm trên đường lưu lượng thực, nhận gói trước khi chuyển tiếp đến chặng kế tiếp. Nếu được cấu hình chế độ ngăn chặn, nó có thể quyết định **cho qua hoặc chặn** tại điểm đó.
- **Out-of-band (OOB), passive sensor** nhận **bản sao** lưu lượng từ TAP, SPAN/mirror port, cơ chế traffic mirroring hoặc một nguồn quan sát khác. Nó có thể phát hiện và cảnh báo nhưng **không thể trực tiếp loại bỏ gói đang đi trên đường chính chỉ bằng bản sao này**.

Hai kiểu này giải quyết nhu cầu khác nhau. Inline hữu ích khi cần chặn tức thời tại ranh giới tin cậy; OOB giảm nguy cơ làm gián đoạn đường chính và thuận lợi cho giám sát, điều tra hoặc chạy thử chữ ký. Cả hai đều có giới hạn về vị trí quan sát, chất lượng dữ liệu, độ trễ xử lý và lưu lượng mã hóa.

Trong module **SECURITY_NETWORK_SECURITY**, chọn sensor cần gắn với phân đoạn mạng, firewall, VPN, xác thực kết nối, DNS, mạng không dây, cloud, phân tích lưu lượng và threat modeling. Đặt sensor đúng chỗ giúp quan sát lưu lượng giữa các vùng quan trọng, phát hiện hành vi bất thường, điều tra sự kiện và bổ sung lớp phòng vệ cho kiến trúc mạng.

**Sau bài học, người học có thể:**

1. Phân biệt inline, out-of-band, IDS, IPS và cơ chế phản ứng gián tiếp.
2. Giải thích cách nhận bản sao qua **SPAN, TAP** và cách chúng khác với đường chuyển tiếp thực.
3. So sánh **khả năng chặn, độ trễ, độ sẵn sàng, mức mất gói, HA và độ bao phủ** giữa các kiến trúc.
4. Phân tích fail-open, fail-closed, bypass, false positive và false negative.
5. Thiết kế vị trí sensor cho Internet, mạng nội bộ, VPN, Wi-Fi và cloud.
6. Xây dựng bộ kiểm thử và tiêu chí vận hành trước khi bật chế độ IPS ngăn chặn.

> **Phạm vi thực hành:** chỉ theo dõi hoặc gửi traffic thử trong môi trường được phép. Các địa chỉ IP, tên hệ thống và sự kiện được nêu dưới đây đều là ví dụ giả định, không phải thông tin hạ tầng thực. Việc bật chế độ chặn trên đường production cần có chủ sở hữu, cửa sổ thay đổi và kế hoạch khôi phục đã được phê duyệt.

## 2. Tách ba khái niệm dễ nhầm: thiết bị, vị trí và hành động

| Khía cạnh | Câu hỏi | Các lựa chọn |
|---|---|---|
| **Chức năng phân tích** | Hệ thống tìm tín hiệu gì? | Chữ ký (signature), bất thường (anomaly), giao thức, metadata, hành vi |
| **Vị trí sensor** | Sensor nhìn gói gốc hay bản sao? | Inline, OOB/passive; đôi khi chỉ thu flow/log |
| **Hành động khi phát hiện** | Kết quả phân tích được áp dụng thế nào? | Alert, log, drop, reject, reset, tạo ticket, yêu cầu firewall chặn |

Ba khía cạnh có liên hệ nhưng **không đồng nhất**:

- Một **IPS appliance đặt inline** vẫn có thể chạy **detect-only** trong giai đoạn thử nghiệm, nghĩa là thấy lưu lượng nhưng chưa chặn.
- Một **IDS đặt OOB** có thể gửi cảnh báo cho hệ thống tự động hóa để thêm rule firewall hoặc yêu cầu cách ly endpoint. Đây là **phản ứng qua thành phần khác**, không tương đương khả năng chặn trực tiếp gói đang được mirror.
- Một **firewall có tính năng kiểm tra xâm nhập** có thể vừa lọc truy cập vừa phân tích chữ ký ngay trong cùng dataplane; vẫn phải xác định luồng nào thực sự đi qua nó.
- Sensor phân tích **NetFlow/IPFIX, DNS log hoặc log proxy** có thể hỗ trợ phát hiện nhưng không có cùng mức nhìn thấy payload như sensor nhận packet.

### 2.1. Chuỗi hoạt động tối giản

~~~mermaid
flowchart TD
    A["Nguồn lưu lượng"] --> B["Đường đi mạng và điểm quan sát"]
    B --> C["Thu thập gói / metadata / luồng"]
    C --> D["Giải mã giao thức, ghép phiên, phát hiện"]
    D --> E{"Chế độ và quyền thực thi?"}
    E -- "Quan sát" --> F["Log, cảnh báo, phân tích"]
    E -- "Inline prevent" --> G["Cho qua / drop / reject theo policy"]
    E -- "Phản ứng gián tiếp" --> H["SIEM/SOAR, firewall hoặc NAC thực thi sau"]
~~~

Quy trình thực tế có thể có nhiều tầng preprocessor, policy, session tracking và bypass. Sơ đồ chỉ mô tả các chức năng logic cần phân biệt.

## 3. Inline sensor: đi qua sensor rồi mới đến đích

### 3.1. Đường đi và cơ chế cơ bản

Trong kiến trúc inline, lưu lượng cần bảo vệ được định tuyến hoặc chuyển tiếp **xuyên qua sensor**. Sensor ở chế độ prevention có thể kiểm tra lưu lượng và cho phép chuyển tiếp, hoặc loại bỏ/chặn tùy chính sách.

~~~mermaid
flowchart LR
    U["Internet / USER"] --> F["Firewall biên"]
    F --> I["Inline IPS"]
    I --> A["APP / DATA"]
    I -. "Alert / counters" .-> S["SIEM / SOC"]
~~~

Đặc tính thường gặp:

- Sensor phải xử lý kịp lưu lượng đi qua, kể cả lúc tải cao, lưu lượng burst và packet nhỏ.
- Khi chữ ký đúng và policy ở chế độ block, việc chặn có thể diễn ra **trước khi gói được chuyển đến đích**.
- Đường đi, failover, bypass, state table và cách phân tích phiên trở thành yếu tố ảnh hưởng trực tiếp đến **tính sẵn sàng** của ứng dụng.
- Sensor không thể ngăn những luồng **không đi qua nó**: ví dụ kết nối nội bộ trong cùng host/subnet, đường dự phòng không có sensor hoặc một VPN tunnel chưa được giải mã tại điểm quan sát.

### 3.2. Inline bridge và inline routed mode

| Kiểu | Đặc trưng | Điểm cần xác minh |
|---|---|---|
| **Transparent bridge / L2 inline** | Sensor được ghép vào đường L2; có thể chuyển tiếp mà không thay đổi mô hình địa chỉ IP của hai đầu | Bridge loops, VLAN tags, MTU, bypass, link state, STP/LACP nếu liên quan |
| **Routed / L3 inline** | Sensor hoặc gateway tham gia định tuyến và xử lý lưu lượng tại chặng L3 | Route, NAT, VRF, asymmetric path, failover, ACL và return traffic |
| **Inline virtual/service-chain** | Traffic được hướng qua VM, gateway hoặc appliance ảo theo routing/service insertion | Route tables, cloud fabric, autoscaling, HA, bypass và đường đi ngoài service chain |

Khả năng cụ thể do sản phẩm quyết định. Không nên mặc định mọi sensor inline đều thực hiện bridge, NAT, routing, packet modification hoặc HA giống nhau.

### 3.3. Chặn không có nghĩa mọi tấn công đều bị ngăn

Nếu sensor chỉ kiểm tra một chiều của kết nối, không giải mã được payload, đang mất gói hoặc không có signature phù hợp, **luồng nguy hiểm vẫn có thể đi qua**. Một rule dựa trên nội dung HTTP có thể không phát hiện được khi nội dung nằm bên trong TLS mà sensor không có quyền và khả năng giải mã. IPS cũng có thể bỏ sót hành vi mới, hành vi hợp lệ về giao thức nhưng lạm dụng quyền ứng dụng, hoặc traffic chưa nằm trong vùng được giám sát.

Do đó, IPS phải kết hợp với **default deny, phân đoạn mạng, xác thực, quản lý bản vá, ứng dụng an toàn, EDR, bảo vệ DNS và giám sát tập trung**.

## 4. Out-of-band sensor: quan sát bản sao, không nằm trên đường chặn

### 4.1. Sơ đồ out-of-band

~~~mermaid
flowchart LR
    U["Nguồn"] --> SW["Switch / router"]
    SW --> D["Đích ứng dụng"]
    SW -. "Mirror/SPAN hoặc TAP feed" .-> O["OOB IDS / NDR sensor"]
    O -. "Sự kiện" .-> S["SIEM / SOC"]
~~~

Sensor OOB nhận bản sao traffic, gửi log hoặc cảnh báo mà **không được chọn làm chặng chuyển tiếp bắt buộc** của kết nối chính. Nếu sensor OOB treo, lưu lượng ứng dụng thường vẫn được chuyển tiếp vì đường dữ liệu chính không phụ thuộc vào nó. Đổi lại, bản sao có thể bị mất hoặc bị cắt ngắn, nên khả năng quan sát phụ thuộc thiết kế thu thập.

### 4.2. SPAN / mirror port

**SPAN (Switched Port Analyzer)**, còn gọi là port mirroring trên nhiều nền tảng switch, sao chép traffic từ cổng/VLAN/nhóm nguồn sang cổng giám sát. Người vận hành có thể mirror một chiều hoặc cả hai chiều tùy thiết bị.

**Ưu điểm:** thuận tiện dùng trên switch hỗ trợ, không phải đưa sensor vào đường dữ liệu chính. **Giới hạn:**

- Nếu tổng traffic được mirror vượt năng lực **cổng đích hoặc sensor**, bản sao có thể bị drop; ứng dụng trên đường chính vẫn hoạt động bình thường.
- Tùy switch, một số frame lỗi, frame nội bộ hoặc thông tin lớp thấp có thể không xuất hiện trong mirror.
- Cấu hình chỉ mirror một chiều, sai interface/VLAN hoặc thay đổi topology có thể làm thiếu nửa kết nối.
- Bản sao hai chiều có thể chứa traffic trùng và thông tin timing không giống hệt đường thực.
- Khi packet được thu tại host, NIC offloading (GRO/LRO/TSO và checksum offload) có thể làm kết quả capture khác gói vật lý trên dây; cần hiểu vị trí và chế độ capture.

**SPAN không tự bảo đảm ghi đủ 100% lưu lượng.** Phải kiểm tra mức oversubscription, packet drops và điều kiện peak.

### 4.3. Network TAP

**Network TAP (Test Access Point)** tạo đường quan sát lưu lượng trên liên kết. Sensor nối vào các **cổng monitor** để nhận bản sao, còn các thiết bị sản xuất tiếp tục giao tiếp trên đường data theo thiết kế TAP.

Điểm khác với SPAN là một TAP phù hợp có thể quan sát lưu lượng ở mức liên kết độc lập với quyết định sao chép của switch. Tuy nhiên, **TAP vẫn là một thành phần được lắp trên liên kết**; việc lựa chọn, lắp đặt hoặc cấp nguồn không đúng vẫn có thể tác động tới kết nối, đặc biệt với một số TAP điện/copper. Các TAP quang, TAP điện, TAP hỗ trợ aggregation và packet broker có đặc tính khác nhau.

**Lưu ý:** một TAP được mắc vật lý trên đường dây **không làm sensor nhận dữ liệu từ cổng monitor trở thành inline IPS**. Sensor đó vẫn chỉ quan sát bản sao nếu gói chính không đi xuyên qua sensor để được quyết định cho qua/chặn.

### 4.4. Network packet broker và traffic aggregation

Để gom nhiều đường vào một cụm sensor, có thể dùng **network packet broker (NPB)** hoặc hệ thống cân bằng lưu lượng giám sát. Nó có thể lọc, phân phối, loại trùng, cắt gói hoặc chia session theo chính sách cấu hình. Điều này cải thiện khả năng triển khai nhưng tạo các câu hỏi:

- NPB có **làm rơi, truncate hoặc lọc bỏ** những packet cần dùng để phát hiện không?
- Các gói của một flow có được gửi tới cùng nơi phân tích khi cần **reassembly** không?
- Có bảo toàn cả hai chiều, thông tin VLAN/tunnel và timestamp cần thiết không?
- Những bộ lọc mirror có vô tình bỏ qua lưu lượng east–west, IPv6, UDP hay một vùng mới không?

## 5. So sánh inline và out-of-band

| Tiêu chí | Inline | Out-of-band / passive |
|---|---|---|
| **Vị trí** | Trên đường dữ liệu đi tới đích | Ngoài đường dữ liệu chính, nhận bản sao/telemetry |
| **Phát hiện** | Có nếu nhìn thấy traffic và engine phù hợp | Có nếu bản sao đủ và engine phù hợp |
| **Chặn gói trực tiếp** | Có thể khi bật IPS/prevent và dataplane hỗ trợ | Không, nếu chỉ nhận bản sao |
| **Phản ứng gián tiếp** | Có thể có | Có thể gửi lệnh tới firewall/NAC/SOAR, nhưng có độ trễ và phụ thuộc hệ khác |
| **Tác động độ trễ** | Có thể thêm latency/jitter cho luồng chính | Không trực tiếp nằm trên đường xử lý, nhưng hạ tầng mirror/TAP có giới hạn riêng |
| **Tác động khi sensor lỗi** | Phụ thuộc fail-open/fail-closed, bypass, HA | Thường mất quan sát, không trực tiếp cắt đường data |
| **Mất gói của sensor** | Có thể dẫn tới drop/chậm/chuyển tiếp theo chính sách fail/bypass | Có thể tạo **khoảng mù phát hiện** dù ứng dụng bình thường |
| **Tính sẵn sàng cần thiết** | Cần thiết kế HA, bypass và quy trình rollback cho dữ liệu chính | Cần theo dõi sensor/nguồn mirror, độ đầy đủ dữ liệu và dự phòng giám sát |
| **Khả năng đặt ở nhiều điểm** | Phải đảm bảo traffic thực đi qua mỗi điểm | Có thể thu thập nhiều điểm nhưng cần tính băng thông mirror và tổng hợp |
| **Thử chữ ký mới** | Nên chạy detect-only trước khi bật block | Thuận tiện chạy alert-only, so sánh false positive |
| **Giới hạn với TLS** | Không thấy payload plaintext nếu không có decryption phù hợp | Tương tự; bản sao encrypted vẫn encrypted |

**Không có lựa chọn tốt nhất cho mọi nơi.** Một tổ chức thường kết hợp cả hai: IPS inline tại những choke point cần chặn, IDS/NDR OOB cho vùng có nhiều traffic đông–tây hoặc nơi không thể chấp nhận rủi ro gián đoạn.

## 6. Fail-open, fail-closed và bypass

### 6.1. Hai chính sách thất bại khác nhau

- **Fail-open:** nếu cơ chế kiểm tra inline không còn hoạt động trong một số trạng thái lỗi được thiết kế, đường đi được chuyển sang bypass/forward để ưu tiên **tính sẵn sàng**. Khi đó kết nối có thể tiếp tục, nhưng lớp IPS của điểm đó **không còn chặn như bình thường**.
- **Fail-closed:** khi sensor hoặc cơ chế liên quan gặp lỗi, lưu lượng bị chặn/không chuyển tiếp để ưu tiên **không cho traffic chưa được kiểm tra đi qua**. Nguy cơ là gián đoạn dịch vụ, đặc biệt với đường mạng trọng yếu.

Tên gọi chỉ có ý nghĩa nếu xác định rõ **lỗi nào**: mất nguồn, chết tiến trình phân tích, CPU quá tải, mất heartbeat, đứt một cổng, mất đường quản trị, lỗi HA hoặc mất kết nối controller. Một thiết bị có thể fail-open trước lỗi phần cứng nhưng hành xử khác khi engine chậm hoặc process lỗi.

| Tình huống | Inline fail-open | Inline fail-closed | OOB sensor |
|---|---|---|---|
| Process phân tích dừng | Có thể bypass kiểm tra, tùy cơ chế | Có thể chặn data, tùy cơ chế | Đường data vẫn đi; cảnh báo có thể mất |
| Mất nguồn thiết bị | Cần bypass phần cứng/link design phù hợp; không mặc định luôn hoạt động | Liên kết có thể gián đoạn | Sensor mất dữ liệu, đường data thường độc lập |
| Sensor quá tải | Có thể bỏ qua/giới hạn inspection hoặc drop theo policy | Có thể gây độ trễ/lỗi kết nối | Mirror capture drop, sinh khoảng mù |
| Chuyển đổi HA | Có thể gián đoạn hoặc giữ phiên tùy thiết kế | Có thể chặn tạm khi failover | Có thể hụt quan sát trong chuyển đổi |

**Không đồng nhất fail-open với “an toàn hơn” hoặc fail-closed với “đúng hơn”.** Quyết định phải dựa trên **rủi ro bảo mật, SLA, tác động nghiệp vụ, đường dự phòng và khả năng giám sát**. Trong mạng y tế hoặc hệ thống sản xuất, sự cố gián đoạn có thể rất nghiêm trọng; ở vùng đặc biệt nhạy cảm, cho đi qua không kiểm tra có thể không chấp nhận được.

### 6.2. Bypass trong kiến trúc inline

Một **bypass switch** hoặc cơ chế bypass tích hợp có thể chuyển đường lưu lượng qua nhánh không qua engine IPS khi xảy ra sự kiện được cấu hình. Nó có thể dùng heartbeat, link state hoặc điều kiện sức khỏe khác. Cần kiểm chứng:

1. Khi IPS khỏe, traffic thực **đi qua engine** và chính sách ngăn chặn có hiệu lực.
2. Khi giả lập một lỗi được cho phép trong lab, đường lưu lượng được xử lý **đúng fail mode thiết kế**.
3. Khi bypass hoạt động, SOC có được **cảnh báo mất khả năng kiểm tra** không?
4. Khi khôi phục, có xảy ra **flap, mất session, đường bất đối xứng hoặc vòng lặp** không?
5. Có dự phòng cho cả thiết bị, nguồn điện, link, controller, điểm thu log và đường quản trị không?

**Fail-open không tương đương HA.** Fail-open có thể giữ đường truyền nhưng mất lớp phòng ngừa; HA có thể giữ năng lực kiểm tra nếu chuyển sang node khác phù hợp, song phải kiểm tra quản lý session và độ bao phủ.

## 7. Độ bao phủ: sensor nhìn thấy được bao nhiêu?

### 7.1. Điểm đặt quan sát quyết định dữ liệu

Một sensor giữa Internet và firewall có thể thấy scan hoặc traffic bị firewall chặn ở phía ngoài, nhưng chưa thấy lưu lượng sau khi vào vùng ứng dụng nếu nó đi tuyến khác. Một sensor phía **sau** firewall nhìn rõ hơn các kết nối được cho phép nhưng có thể không thấy các gói bị drop tại biên. Đặt một sensor ở DMZ không đảm bảo nhìn thấy mọi lưu lượng **east–west** giữa API, database và hệ thống quản trị.

~~~mermaid
flowchart LR
    IN["Internet"] --> PRE["Điểm A: trước firewall"]
    PRE --> FW["Firewall"]
    FW --> POST["Điểm B: sau firewall"]
    POST --> WEB["Web"]
    WEB --> API["API"]
    API --> DB["Database"]
    API -. "Có thể không qua A/B" .-> DB
~~~

Đặt sensor nên theo **threat model**: bảo vệ tài sản nào, attacker có thể bắt đầu ở đâu, ranh giới tin cậy nào cần quan sát, có phải thấy traffic trước và sau chính sách lọc không?

### 7.2. Lưu lượng hai chiều và bất đối xứng

Phân tích TCP thường hưởng lợi từ việc thấy **cả hai chiều** của một phiên: SYN/SYN-ACK/ACK, retransmission, dữ liệu và trạng thái kết thúc. Với routing bất đối xứng, ECMP hoặc nhiều gateway, sensor có thể chỉ nhìn một chiều; engine dễ gặp tình trạng **missing stream segments**, flow state không đầy đủ và cảnh báo sai/thiếu.

Trong trường hợp nhiều sensor hoặc broker chia traffic, cần chính sách đảm bảo **các gói của cùng flow được xử lý phù hợp**. Bắt mirror cả hai chiều có thể đưa đến các packet trùng; công cụ cần có khả năng xử lý hoặc dedup theo ngữ cảnh.

### 7.3. Lưu lượng nội bộ trong cùng host và overlay

Một VPC, VLAN hoặc subnet không đảm bảo mọi giao tiếp đều qua gateway quan sát. Trong Kubernetes, kết nối giữa pod trên cùng node, qua overlay/eBPF hoặc service mesh có thể không đi qua sensor ở biên. Với ảo hóa, traffic VM-to-VM trong cùng hypervisor có thể không chạm switch vật lý. Cần cân nhắc sensor trên host, virtual tap, CNI telemetry hoặc điểm mirror ở virtual switch nếu phù hợp.

### 7.4. NAT và định danh tài sản

Sensor đặt **trước NAT** và **sau NAT** có thể thấy source/destination IP khác nhau. Đối chiếu IDS alerts với firewall logs, DHCP, DNS, VPN và cloud flow logs để xác định đúng endpoint và người dùng. Một cảnh báo chỉ có IP public của NAT gateway chưa đủ để kết luận pod hoặc máy nội bộ nào sinh traffic.

## 8. Giới hạn với TLS, QUIC và dữ liệu mã hóa

Một IDS/IPS dựa trên packet không thể mặc định đọc payload khi traffic được mã hóa:

- **HTTPS/TLS:** có thể thấy một số metadata về IP, cổng, TLS handshake/cert hoặc kích thước/thời gian gói tùy phiên bản, cấu hình và khả năng phân tích, nhưng không thấy plaintext HTTP nếu không có giải mã hợp lệ.
- **QUIC/HTTP/3:** thường chạy trên UDP/443; sensor chỉ phân tích TCP/443 có thể bỏ sót hoặc diễn giải không đầy đủ.
- **VPN/IPsec:** sensor bên ngoài tunnel thường thấy địa chỉ endpoint/tunnel và lưu lượng mã hóa, không thấy đầy đủ luồng ứng dụng bên trong.
- **Encrypted DNS (DoT/DoH):** làm nội dung truy vấn DNS không hiển thị như DNS/53 thông thường tại điểm quan sát không giải mã.
- **ECH và các cơ chế bảo vệ riêng tư:** có thể hạn chế thêm những metadata TLS từng được quan sát trước đây; không nên dựa vào SNI luôn tồn tại ở dạng đọc được.

**Vị trí tương đối với điểm giải mã** rất quan trọng. Ví dụ, nếu TLS được kết thúc tại reverse proxy hoặc load balancer được quản lý, sensor phía sau có thể thấy kết nối khác hoặc nội dung plaintext **chỉ khi kiến trúc thực sự chuyển tiếp không mã hóa**. Nếu proxy mã hóa lại đến backend, sensor giữa proxy và backend vẫn thấy traffic được mã hóa.

Giải mã tập trung/TLS inspection có thể giúp kiểm tra payload nhưng mang thêm **chi phí tài nguyên, yêu cầu quyền riêng tư, quản lý khóa/chứng chỉ và rủi ro tạo điểm nhạy cảm**. Chỉ triển khai theo quy định và phạm vi được phê duyệt. Khi không thể giải mã, kết hợp metadata, DNS/proxy logs, endpoint telemetry, xác thực dịch vụ, hành vi ứng dụng và các lớp khác.

## 9. False positive, false negative và chính sách ngăn chặn

### 9.1. Hai loại sai số

- **False positive (FP):** sensor gắn cờ traffic hợp lệ là nguy hiểm. Trên OOB, FP tạo cảnh báo nhiễu. Trên inline IPS ở chế độ drop, FP có thể **làm gián đoạn ứng dụng hợp lệ**.
- **False negative (FN):** sensor bỏ sót hành vi nguy hiểm. Nguyên nhân có thể là chữ ký chưa có, mã hóa, packet loss, thiếu một chiều, bypass, cấu hình parser, traffic nằm ngoài điểm quan sát hoặc hành vi tấn công không phù hợp detection logic.

### 9.2. Quy trình nâng rule từ cảnh báo sang chặn

1. **Thu thập baseline:** định danh ứng dụng, nhóm người dùng, giao thức, mức tải, hành vi hợp lệ và traffic hiếm.
2. **Chạy detect-only:** dùng sensor OOB hoặc IPS inline không drop để thu alert.
3. **Triage có ngữ cảnh:** xác minh alert với chủ ứng dụng, packet/flow/log, tài sản đích và tác động nghiệp vụ; tránh chỉ dựa số lần bắn chữ ký.
4. **Tuning:** điều chỉnh phạm vi rule, threshold, biến mạng, exception theo chính sách và phiên bản chữ ký; không vô hiệu hóa toàn bộ engine vì một alert nhiễu.
5. **Thử trong lab/staging:** tạo traffic **lành tính có nhãn**, traffic mô phỏng theo rule test và kiểm tra phản hồi. Không cần tạo mã độc thực hoặc phá hỏng dịch vụ.
6. **Rollout giới hạn:** bật block trên vùng/ứng dụng được chọn, có người trực giám sát và rollback.
7. **Giám sát sau triển khai:** theo dõi drop rate, phản hồi ứng dụng, FP, trạng thái bypass, latency và tải sensor.

**Một signature phù hợp về mặt cú pháp không tự bảo đảm an toàn để bật chặn.** Chọn chế độ xử lý cần dựa trên bằng chứng về độ chính xác và hậu quả của false positive.

### 9.3. Hành động out-of-band không phải chặn trực tiếp

IDS OOB có thể gửi log đến **SIEM/SOAR**, từ đó tạo ticket, gọi API firewall hoặc NAC để chặn một IP/thiết bị. Chuỗi này có **độ trễ phát hiện–phân loại–thực thi** và rủi ro xác định nhầm IP (NAT, DHCP, IP dùng chung), độ sẵn sàng API, quyền điều khiển và rule quá hạn. Nếu dùng automated response:

- Xác minh độ tin cậy và điều kiện kích hoạt; có thể cần người phê duyệt ở kịch bản nhạy cảm.
- Giới hạn phạm vi chặn và đặt **TTL/expiration** cho rule tạm.
- Có audit log, quyền tối thiểu, thử nghiệm và cơ chế khôi phục.
- Không báo rằng out-of-band sensor đã ngăn gói đầu tiên chỉ vì hệ thống sau đó thêm rule firewall.

## 10. Hiệu năng: throughput, packets per second và packet loss

### 10.1. Không chỉ đo Gb/s

Để chọn kích thước sensor cần xét đồng thời:

| Chỉ số | Ý nghĩa | Vì sao quan trọng? |
|---|---|---|
| **Throughput (Gb/s)** | Lượng dữ liệu xử lý theo thời gian | Liên quan lưu lượng tổng và dung lượng link |
| **Packets per second (pps)** | Số gói xử lý mỗi giây | Nhiều gói nhỏ có thể gây tải cao dù Gb/s chưa đầy |
| **Concurrent flows / sessions** | Số phiên theo dõi đồng thời | Engine cần bộ nhớ/state, nhất là traffic east–west |
| **New connections per second** | Tốc độ tạo phiên mới | Burst kết nối có thể ảnh hưởng phân tích và conntrack |
| **Packet drop / capture loss** | Gói bị mất ở capture hoặc engine | OOB tạo điểm mù; inline có thể ảnh hưởng ứng dụng |
| **Latency / jitter** | Thời gian xử lý thêm trên đường đi | Đặc biệt quan trọng với ứng dụng độ trễ thấp |
| **Decryption / parser cost** | Chi phí phân tích sâu hoặc giải mã | Thông số nhà cung cấp khi bật tính năng có thể khác chế độ cơ bản |
| **Availability / HA** | Khả năng duy trì xử lý và đường đi | Tác động đến SLA và phương án phục hồi |

Thông số “IPS throughput” của nhà cung cấp thường phụ thuộc **traffic mix, số chữ ký đang bật, giao thức, giải mã, kích thước gói và feature set**. Không nên thiết kế chỉ dựa trên tốc độ danh nghĩa của cổng mạng.

### 10.2. Ví dụ mirror oversubscription

Giả sử một nhóm switch mirror hai chiều trên một liên kết mà tại giờ cao điểm có **8 Gb/s theo hướng A → B** và **8 Gb/s theo hướng B → A**. Nếu cấu hình gộp cả hai chiều vào **một cổng mirror 10 Gb/s**, lượng được yêu cầu sao chép có thể lên tới **16 Gb/s**, vượt năng lực cổng mirror. Sensor OOB có thể **không nhìn thấy toàn bộ lưu lượng**, dù link chính hai chiều 10 Gb/s vẫn hoạt động đúng.

~~~text
Lưu lượng cần mirror theo ví dụ:
  Chiều A -> B: 8 Gb/s
  Chiều B -> A: 8 Gb/s
  Tổng sao chép vào một đầu ra: 16 Gb/s
  Năng lực cổng mirror: 10 Gb/s

=> Có nguy cơ oversubscription, không được suy rằng capture là đầy đủ.
~~~

Các con số trên là giả định, chưa tính overhead, packet size, burst hoặc cách sản phẩm tính thông lượng. Giải pháp có thể là dùng nhiều cổng monitor, traffic aggregation phù hợp, packet broker đủ năng lực hoặc đặt sensor ở điểm khác; phải kiểm chứng thực tế.

### 10.3. Sức khỏe sensor cần được giám sát

Không chỉ giám sát process “đang chạy” mà cần theo dõi:

- Interface state, packet count, capture drops, queue/backpressure và số phiên không phân tích được.
- CPU, RAM, disk, độ trễ xử lý và tốc độ ingest.
- Thời gian cập nhật chữ ký/model, lỗi parser và sự thay đổi mức alert.
- Health của TAP/SPAN/NPB và khả năng nhận **cả hai chiều**.
- Trạng thái inline bypass, HA, failover, heartbeat và thời điểm khôi phục.
- Độ trễ từ sự kiện mạng đến alert/SIEM và khả năng tương quan với log nguồn khác.

Nếu sensor báo “healthy” nhưng mirror source đã cấu hình sai, hệ thống vẫn có thể ở trạng thái **mất quan sát**. Nên kiểm tra cả **data freshness** và test marker định kỳ có kiểm soát.

## 11. Lựa chọn vị trí triển khai theo threat model

### 11.1. Ranh giới Internet/DMZ

**Inline IPS** phù hợp khi cần chặn lưu lượng vào các dịch vụ công khai, có thể thiết kế HA, bypass, tuning và chính sách rõ ràng. **OOB IDS** trước/sau firewall có thể cung cấp góc nhìn bổ sung về scan, traffic bị chặn và traffic thực được phép. Vị trí trước firewall thường thấy nhiều nhiễu từ Internet; vị trí sau firewall gần ứng dụng hơn nhưng không nhìn thấy mọi kết nối bị chặn tại biên.

### 11.2. Lưu lượng east–west giữa các phân đoạn

Trong mạng nội bộ, tấn công có thể đi giữa máy người dùng, app, database, IdP và mạng quản trị. Chọn sensor tại **trust boundary** quan trọng, đặc biệt với tài sản nhạy cảm. Với môi trường ảo hóa/microsegmentation, có thể cần telemetry trên host hoặc CNI vì traffic không đi qua firewall trung tâm.

### 11.3. VPN và mạng truy cập từ xa

Sensor ngoài VPN thường chỉ nhìn thấy **tunnel được mã hóa** và địa chỉ VPN gateway; sensor sau điểm giải mã có thể thấy lưu lượng trong tunnel (nếu thiết kế chuyển qua sensor). Cần phân biệt người dùng, thiết bị, nhóm quyền và session bằng cách liên kết **VPN logs, IdP, DHCP/NAT** với event từ IDS/IPS. Đăng nhập VPN thành công không đồng nghĩa được phép truy cập toàn mạng nội bộ.

### 11.4. Wi-Fi khách, BYOD và IoT/OT

Wi-Fi khách có thể là vùng ít tin cậy, cần giám sát các đường tới nội bộ và Internet theo chính sách. Với IoT/OT hoặc thiết bị nhạy cảm, inline IPS có thể tạo rủi ro gián đoạn nếu parser/signature không tương thích; OOB giúp quan sát trước và thu baseline. Mọi thay đổi ở môi trường yêu cầu sẵn sàng cao phải đánh giá tác động vận hành.

### 11.5. Cloud VPC/VNet và container

Trong cloud, **traffic mirroring** ở virtual network thường cung cấp bản sao cho sensor OOB (tính năng, vùng hỗ trợ, loại traffic và giới hạn tùy nhà cung cấp). Nếu muốn đưa traffic qua thiết bị inline, thường cần **routing/service insertion/gateway** hoặc thiết kế riêng sao cho **cả chiều đi và chiều về** thực sự qua điểm thực thi. Cần kiểm tra:

- Route tables, security groups/NSGs, subnet ACLs, peering và transit.
- Tính sẵn sàng đa vùng (AZ), lưu lượng cross-zone, NAT và failover.
- Traffic giữa workload cùng host/node có đi qua điểm quan sát không?
- Logging từ VPC flow logs, DNS và cloud control plane có bổ sung những gì?

Không mặc định việc tạo một sensor VM trong VPC làm toàn bộ VPC được bảo vệ. Điều quan trọng là **traffic steering và phạm vi sensor thấy được**.

## 12. Kiến trúc tham khảo: kết hợp phòng ngừa và quan sát

~~~mermaid
flowchart LR
    IN["Internet"] --> FW["Firewall / default deny"]
    FW --> IPS["Inline IPS / prevention"]
    IPS --> APP["App zone"]
    APP --> DATA["Data zone"]
    APP -. "SPAN/TAP hoặc flow mirror" .-> IDS["OOB IDS / NDR"]
    DATA -. "Theo dõi luồng được phép" .-> IDS
    FW -. "Logs" .-> SIEM["SIEM / SOC"]
    IPS -. "Alerts + action" .-> SIEM
    IDS -. "Alerts + metadata" .-> SIEM
    VPN["VPN + IdP"] --> FW
~~~

Kiến trúc này minh họa **cách phối hợp**, không phải khuyến nghị đặt mọi công ty theo đúng thứ tự trên:

1. Firewall thực thi **allowlist/default deny** theo ranh giới, giảm số kết nối phải phân tích sâu.
2. IPS inline chặn những nội dung phù hợp chính sách prevention trên đường được kiểm soát.
3. IDS/NDR OOB bổ sung quan sát luồng nội bộ và hỗ trợ điều tra mà không trực tiếp quyết định forward.
4. SIEM tương quan sự kiện từ firewall, VPN, DNS, IPS, IDS, ứng dụng và endpoint để gắn cảnh báo với tài sản/người dùng.
5. SOC xử lý false positive, mất telemetry, hành vi mới và các lỗ hổng không được signature bao phủ.

**Tập trung vào defense in depth**: lỗi một sensor không nên đồng nghĩa mất mọi lớp bảo vệ hoặc toàn bộ khả năng giám sát.

## 13. Quy trình triển khai sensor an toàn

### Bước 1 — Xác định mục tiêu và tài sản

Ghi rõ cần **phát hiện** hay **ngăn chặn**, lưu lượng cần bảo vệ, tài sản có giá trị cao (database, IdP, DNS, VPN gateway, mạng quản trị), ranh giới và yêu cầu SLA. Định nghĩa loại hành vi muốn phát hiện, nguồn telemetry sẵn có và mức độ phản ứng được phê duyệt.

### Bước 2 — Lập bản đồ đường đi

Xác định ingress, egress, east–west, NAT, routing bất đối xứng, VLAN, VPN termination, load balancer, cloud peering và lưu lượng giữa workload cùng node. Phải trả lời **gói đi qua sensor nào** ở cả chiều đi và chiều về; sơ đồ logic không đủ nếu traffic có đường bypass.

### Bước 3 — Chọn chế độ và điểm thu thập

Với OOB, chọn SPAN/TAP/virtual mirror và kiểm tra năng lực đầu ra, buffer, timestamp, packet truncation, cả hai chiều. Với inline, xác định bridge/routed/service-chain, fail-open/fail-closed, bypass, HA, ảnh hưởng routing và kênh quản trị.

### Bước 4 — Sizing theo traffic thực

Thu số liệu peak/average, traffic mix, pps, concurrent flows, tốc độ tạo phiên, TLS/QUIC, số chữ ký và latency budget. Chừa headroom cho burst và tăng trưởng. Nếu có khả năng giải mã, đánh giá lại thông số khi bật tính năng đó.

### Bước 5 — Chạy detect-only và dựng baseline

Thu alert, phát hiện false positive, kiểm tra dữ liệu nguồn và tune policy theo ứng dụng. Xác minh sensor thực sự thấy traffic dự kiến và có đồng bộ thời gian. Đánh giá cảnh báo theo mức độ rủi ro tài sản, không chỉ theo mức độ nghiêm trọng gán sẵn của chữ ký.

### Bước 6 — Thử chế độ chặn trong lab/nhóm nhỏ

Chỉ bật prevention với các rule đã có bằng chứng. Thử luồng hợp lệ, luồng marker kiểm thử và tình huống failover, bypass; ghi nhận application health và performance. Chuẩn bị khả năng chuyển về detect-only/bypass hoặc rollback theo phương án được duyệt.

### Bước 7 — Triển khai có kiểm soát

Áp dụng lần lượt cho những vùng đã xác định, theo dõi alert/drop rate, latency, lỗi ứng dụng và sức khỏe thiết bị. Nếu cần giảm tác động, chia nhóm signature thành alert-only và block theo độ tin cậy; không bật hàng loạt tất cả signature vào block mà chưa đánh giá.

### Bước 8 — Duy trì và kiểm tra hồi quy

Sau thay đổi cấu trúc mạng, VPN, cloud, DNS, ứng dụng hoặc rule firewall, xác minh lại phạm vi sensor thấy được, đường traffic đi qua và chính sách block. Tạo quy trình xử lý signature gây false positive, mất mirror, cổng TAP/NPB quá tải, bypass không mong muốn và log bị ngắt.

## 14. Ma trận kiểm thử inline và out-of-band

| Test ID | Cấu hình/vị trí | Mục đích | Tiêu chí quan sát |
|---|---|---|---|
| **VIS-01** | OOB qua SPAN/TAP | Chứng minh sensor thấy traffic hợp lệ | Packet/flow đến sensor, đúng source/dest/protocol và timestamp |
| **VIS-02** | OOB, mirror hai chiều | Chứng minh thấy cả request/response | Hai chiều của flow xuất hiện, không thiếu session do cấu hình |
| **VIS-03** | OOB lúc peak | Xác minh năng lực mirror | Không có mức capture loss ngoài ngưỡng được duyệt |
| **DET-01** | IDS/IPS ở detect-only | Marker thử sinh alert | Alert đúng chữ ký, rule ID, source/dest và thời điểm |
| **ALLOW-01** | Inline IPS | Traffic hợp lệ không bị gián đoạn | TCP/TLS/app health thành công; latency trong SLO đã thống nhất |
| **BLOCK-01** | Inline IPS có rule lab | Traffic marker phải bị chặn | Không nhận nội dung ở đích; action drop phù hợp ở sensor; có log |
| **SAFE-01** | Inline IPS với traffic lành tính tương tự | Kiểm tra false positive | Traffic hợp lệ vẫn thành công, không có drop sai |
| **FAIL-01** | Inline, lỗi sensor đã mô phỏng | Kiểm tra fail mode | Bypass hoặc chặn đúng thiết kế; giám sát mất inspection |
| **HA-01** | Cụm inline HA | Kiểm tra chuyển đổi node | Đường đi và trạng thái kiểm tra phù hợp SLA; log failover |
| **COV-01** | Có VPN/NAT/cloud | Kiểm tra phạm vi thực | Đúng gói nội bộ được quan sát sau giải mã/NAT hoặc ghi nhận giới hạn |
| **REG-01** | Sau đổi routing/firewall | Kiểm tra hồi quy | Sensor vẫn thấy đúng các đường và phản ứng theo policy |

Mỗi test nên ghi **nguồn, đích, protocol/port, vị trí sensor, expected decision, rule/signature ID, time UTC, bản ghi evidence và người phê duyệt**. Chỉ tiêu PASS phải gắn với yêu cầu thực, ví dụ “độ trễ tăng không vượt SLO đã được định nghĩa”, tránh tự đặt một con số không có dữ liệu nghiệp vụ.

### 14.1. Ví dụ kiểm tra đường sensor từ nguồn hợp lệ

Các lệnh sau thiên về **quan sát**, sử dụng địa chỉ phòng lab giả định. Chỉ chạy trên máy và network interface bạn được phép quản trị:

~~~bash
# Kiểm tra network interface và thống kê lỗi/drop cơ bản của Linux
ip -s link

# Xem thống kê NIC trên interface giám sát nếu driver hỗ trợ
sudo ethtool -S eth1

# Quan sát packet tới máy chủ thử trong phòng lab
sudo tcpdump -ni eth1 'host 192.0.2.20 and (tcp or udp)'

# Đọc thời gian hệ thống để hỗ trợ tương quan log
date -u
~~~

Trong môi trường OOB, `tcpdump` trên sensor cho biết sensor **có nhận packet tại interface được chỉ định** hay không; nó không chứng minh tất cả packet trên đường chính đều đã được mirror. Trong inline, một packet xuất hiện ở interface vào chưa có nghĩa nó được chuyển tiếp ra interface còn lại; cần capture/counter ở hai phía hoặc log quyết định IPS.

Nếu không có thiết bị lab, có thể dùng **PCAP vô hại được tạo/ghi trong môi trường đã cho phép** để kiểm tra parser và quy tắc phát hiện. **Replay offline** chứng minh khả năng phân tích bộ dữ liệu đó, không chứng minh khả năng chặn trên dataplane production.

### 14.2. PASS, FAIL, INCONCLUSIVE

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **PASS** | Đúng kỳ vọng và có bằng chứng phù hợp | OOB thấy cả hai chiều; inline chặn marker test với log drop đúng |
| **FAIL** | Có bằng chứng trái với mục tiêu | Traffic hợp lệ bị block; SPAN không gửi traffic cần quan sát; HA không đạt SLO |
| **INCONCLUSIVE** | Điều kiện thử/bằng chứng chưa đủ | Đích test đang tắt, mirror quá tải, thiếu log, packet chỉ thấy một phía |

**Timeout không tự động là thành công của IPS.** Kết nối có thể timeout vì DNS, route, host down hoặc firewall khác. Khi đánh giá block, cần chứng minh **rule/action tại inline sensor** đã loại bỏ traffic và đích còn hoạt động cho luồng kiểm soát được phép.

## 15. Chẩn đoán sự cố và điểm mù

| Triệu chứng | Giả thuyết | Hướng xác minh |
|---|---|---|
| Ứng dụng chậm sau khi bật IPS | Engine quá tải, kiểm tra sâu, flow table, TLS inspection | Đo latency, CPU/pps, concurrent flows, bypass state, rule mới |
| Kết nối hợp lệ bị ngắt khi bật block | False positive, parser, stateful timeout, chính sách quá rộng | Liên hệ app owner, xem signature/drop log, so sánh detect-only |
| OOB không thấy request nhưng ứng dụng hoạt động | Sai SPAN source/VLAN, traffic đi đường khác, mirror drop | Kiểm tra topology, counters, mirror configuration, capture tại nguồn |
| Sensor chỉ thấy một nửa TCP flow | Mirror một chiều, ECMP/routing bất đối xứng, broker chia flow sai | So sánh hai hướng tại nhiều điểm, route và hash policy |
| Sensor có traffic nhưng không báo alert | Rule chưa bật, payload mã hóa, traffic không khớp, packet loss | Kiểm tra rule version, signature, decoder và test marker |
| OOB báo nghi ngờ nhưng không ngăn kết nối | Sensor không inline, phản ứng cần bước ngoài | Kiểm tra workflow SIEM/SOAR và hành động của firewall |
| Inline IPS mất nguồn và mạng vẫn thông | Bypass/fail-open có thể đang hoạt động | Kiểm tra fail policy, trạng thái inspection và cảnh báo |
| Inline IPS lỗi làm cả vùng mất kết nối | Fail-closed hoặc lỗi đường không bypass | Kiểm tra HA, bypass, nguồn, link và phương án rollback |
| Flow log khác alert IP | NAT, proxy, VPN hoặc gắn IP động | Đối chiếu 5-tuple trước/sau NAT, session/user và timestamp |
| Không thấy hoạt động pod cùng node | Luồng không đi qua điểm mirror/gateway | Kiểm tra virtual switch, CNI/eBPF, host telemetry |

**Cách điều tra có hệ thống:**

1. Xác định một **flow cụ thể** và 5-tuple tại nguồn, đích, thời điểm.
2. Truy vết packet qua **interface nhận – điểm xử lý – interface ra/đích**.
3. Tại inline, xem rule ID, **action/drop**, flow state, bypass và các lớp firewall khác.
4. Tại OOB, xem khả năng sao chép, packet drops, filter, source VLAN, hướng và freshness.
5. Đối chiếu ứng dụng, DNS, TLS, NAT, VPN và cloud telemetry.
6. Kết luận dựa trên bằng chứng thay vì chỉ một alert hoặc một timeout.

## 16. Case study: chọn sensor cho hệ thống xử lý đơn hàng

### 16.1. Bối cảnh

Một doanh nghiệp có người dùng Internet truy cập web frontend qua firewall, phía sau là API và database riêng. Nhân viên có VPN; log được thu vào SIEM. Đội bảo mật muốn **chặn một số mẫu xâm nhập rõ ràng vào ứng dụng** và đồng thời **theo dõi traffic đông–tây** giữa API và database.

Giả sử mục tiêu nghiệp vụ là:

- Dịch vụ web không được gián đoạn ngoài ngưỡng đã phê duyệt.
- Các luồng cần chặn có tiêu chí rõ; những chữ ký chưa đủ tin cậy phải chỉ cảnh báo.
- Có khả năng phát hiện kết nối bất thường giữa các vùng dữ liệu và quản trị.
- Có dữ liệu truy vết khi xác thực qua VPN, DNS hoặc cloud có thay đổi.

### 16.2. Phương án kết hợp

| Vị trí | Lựa chọn minh họa | Vì sao? |
|---|---|---|
| Biên sau firewall tới web | **Inline IPS**, ban đầu detect-only rồi bật block có chọn lọc | Có thể ngăn traffic tại choke point đã kiểm soát |
| Lưu lượng API ↔ DB | **OOB IDS/NDR** từ mirror hoặc sensor phù hợp workload | Quan sát east–west không đưa thêm điểm chặn ngay lập tức |
| Sau VPN gateway | Sensor nhận lưu lượng **đã ra khỏi tunnel** nếu tuyến đi qua | Gắn alert với VPN/IdP logs và thấy flow nội bộ |
| SIEM | Tương quan IPS drop, OOB alert, DNS, firewall, ứng dụng | Phân biệt các sự kiện và ưu tiên theo tài sản |

**Không tự động thấy payload HTTPS** chỉ vì IPS đặt sau firewall. Nếu TLS kết thúc tại web frontend, IPS phía trước frontend vẫn có thể chỉ thấy ciphertext. Cần dựa vào kiến trúc TLS và quyền xử lý dữ liệu đã xác nhận.

### 16.3. Bộ phép thử

**T1 – Positive path:** một request HTTPS hợp lệ tới frontend và truy vấn API hoạt động, latency trong SLO.

**T2 – Detection path:** gửi mẫu marker hợp lệ trong lab đến endpoint thử; cả IPS detect-only và OOB sensor liên quan có alert nếu chúng thật sự thấy nội dung mà rule được thiết kế để kiểm tra.

**T3 – Inline prevention:** với rule lab được bật block, xác nhận test marker bị chặn tại IPS, không phải do firewall khác hoặc backend ngừng chạy.

**T4 – OOB coverage:** xác nhận bản sao API ↔ DB có cả hai chiều, không bị cắt hoặc mất do mirror quá tải; đối chiếu flow telemetry.

**T5 – Failure behavior:** mô phỏng tình huống lỗi **đã được phê duyệt trong lab**, xác minh fail-open/fail-closed, HA và cảnh báo mất năng lực inspection.

**T6 – Regression:** sau khi chuyển dịch vụ lên cloud hoặc thay route VPN, chạy lại kiểm tra sensor visibility, policy block và luồng ứng dụng.

### 16.4. Ví dụ biên bản

~~~text
Scenario: LAB-IPS-OOB-01 (dữ liệu giả định)
Path: Internet -> Firewall -> IPS -> Web
Secondary visibility: API <-> DB via OOB mirror
Inline mode: alert-only for baseline; selected lab rule in block mode
Expected:
  - Legitimate HTTPS request succeeds
  - Test marker generates alert at intended sensor
  - Lab block rule drops only matching test traffic
  - OOB sensor receives both directions of API/DB test flow
  - On approved failure test, bypass/HA action matches design
Required evidence:
  - time, 5-tuple, rule/signature ID, IPS action, mirror counters
  - application status, latency, drop counters, bypass state
Conclusion: pending execution; no production test claimed
~~~

## 17. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “IDS là OOB, IPS chắc chắn inline.” | IDS/IPS nói về chức năng; sensor topology và chế độ hành động là các chiều khác nhau. |
| “Sensor OOB không chặn nên không hữu ích.” | OOB hữu ích để phát hiện, điều tra, tuning, tăng độ bao phủ và giảm rủi ro gián đoạn. |
| “OOB gửi lệnh firewall nên chặn packet ngay lập tức.” | Phản ứng gián tiếp có độ trễ và không tương đương drop trực tiếp trên dataplane. |
| “Có TAP nghĩa là sensor inline.” | Sensor nối cổng monitor vẫn thụ động; TAP chỉ tạo nguồn quan sát. |
| “Có SPAN thì luôn bắt được mọi packet.” | Có thể mất bản sao do oversubscription, filter, lỗi cấu hình và giới hạn thiết bị. |
| “Inline có fail-open là được HA.” | Fail-open có thể duy trì kết nối nhưng bỏ qua kiểm tra; HA là mục tiêu khác. |
| “Fail-closed luôn bảo mật hơn mà không có đánh đổi.” | Có thể gây gián đoạn nghiệp vụ nghiêm trọng; phải đánh giá SLA và rủi ro. |
| “IPS nhận gói TLS là đọc được HTTP bên trong.” | Không thấy plaintext nếu không có giải mã phù hợp. |
| “Một sensor ở biên nhìn thấy mọi east–west traffic.” | Nhiều flow nội bộ/cloud/overlay không đi qua biên. |
| “Bật block càng nhiều chữ ký càng an toàn.” | False positive có thể làm gián đoạn ứng dụng, phải tune và rollout. |
| “Không có alert nghĩa là không có tấn công.” | Có thể thiếu visibility, mất gói, thiếu signature hoặc hành vi nằm ngoài detection logic. |

## 18. Bài tập tự kiểm tra

### Bài 1 — Chọn mô hình

Một hệ thống giao dịch rất nhạy cảm với độ trễ, cần phát hiện hành vi bất thường trước khi cân nhắc chặn tự động. Nên thử kiến trúc nào đầu tiên?

*Gợi ý:* có thể dùng **out-of-band IDS/NDR** hoặc inline **detect-only** trong môi trường được duyệt để lấy baseline, đo FP và visibility. Nếu cần chặn, phải xây quyết định riêng về vị trí inline, SLA, HA và rollback.

### Bài 2 — Trạng thái fail-open

Inline IPS mất engine phân tích, lưu lượng vẫn đi qua nhờ bypass phần cứng. Có thể nói hệ thống vẫn được bảo vệ bởi IPS không?

*Gợi ý:* không. Đường truyền có thể vẫn sẵn sàng nhưng **kiểm tra và chặn bởi engine đó đang mất hoặc bị bỏ qua**. Cần cảnh báo và dùng lớp bảo vệ khác trong giai đoạn này.

### Bài 3 — Mirror oversubscription

Một đường hai chiều có 8 Gb/s mỗi chiều và cả hai chiều được mirror vào một cổng 10 Gb/s. Vì sao IDS có thể bỏ sót alert?

*Gợi ý:* tổng lưu lượng sao chép có thể là **16 Gb/s**, vượt khả năng cổng mirror; packet bị mất trước khi đến IDS. Cần đo drops, peak và thiết kế lại đường thu thập.

### Bài 4 — TLS inspection

Sensor đặt giữa firewall và reverse proxy phục vụ HTTPS. Vì sao một rule dựa trên nội dung URI có thể không phát hiện?

*Gợi ý:* HTTPS còn mã hóa đến reverse proxy; sensor không đọc được URI plaintext nếu không có giải mã phù hợp. Cân nhắc điểm quan sát sau termination, proxy logs hoặc những nguồn metadata khác.

### Bài 5 — OOB phản ứng tự động

IDS OOB phát hiện traffic bất thường, SOAR gọi API firewall chặn IP nguồn sau một khoảng trễ. Gói đầu tiên có chắc chắn đã bị ngăn không? Nguy cơ nào khi IP nguồn nằm sau NAT?

*Gợi ý:* không. Hành động diễn ra sau phát hiện; IP có thể đại diện cho nhiều thiết bị, nên chặn nhầm hoặc quá rộng. Cần định danh và giới hạn TTL/điều kiện phản ứng.

### Bài 6 — Cloud visibility

Đội mạng tạo một IDS VM trong VPC và bật flow logging, rồi kết luận mọi kết nối pod-to-pod đã được giám sát ở mức payload. Lập luận đúng không?

*Gợi ý:* không. Cần xác minh traffic mirroring/steering, loại dữ liệu flow logs, đường intra-node, mã hóa và năng lực sensor. Flow metadata không đồng nghĩa payload capture.

### Bài 7 — Kiểm chứng prevention

Một request thử không tới được web khi IPS bật chặn. Làm sao phân biệt do IPS rule drop hay do ứng dụng/database lỗi?

*Gợi ý:* chạy **positive control** cho request hợp lệ, kiểm tra rule/action và flow log tại IPS, packet trước/sau điểm thực thi, ứng dụng và các firewall trên tuyến; không dựa vào timeout đơn lẻ.

### Bài 8 — Chọn điểm quan sát

Yêu cầu là điều tra truy cập bất thường từ VPN tới mạng quản trị, trong khi VPN traffic mã hóa qua Internet. Nên ưu tiên điểm nào?

*Gợi ý:* nơi lưu lượng **đã giải tunnel** và đi qua được sensor, kết hợp VPN/IdP/session logs để gắn nguồn với người dùng. Sensor ngoài tunnel chủ yếu thấy kết nối VPN mã hóa.

## 19. Checklist thiết kế và vận hành

Trước khi kết luận một sensor triển khai hiệu quả, cần xác minh:

- Có **tài sản mục tiêu, ranh giới tin cậy và chức năng detect/prevent** được mô tả rõ.
- Sensor đang ở chế độ **inline hay OOB** theo dataplane thực tế, không chỉ dựa tên sản phẩm.
- Đã xác minh **mọi đường được kỳ vọng** đi qua hoặc được mirror tới sensor; có ghi giới hạn east–west và intra-host.
- Có dữ liệu về **cả hai chiều phiên**, NAT, VPN, IPv4/IPv6, QUIC/TLS và khả năng giải mã phù hợp.
- SPAN/TAP/NPB được sizing theo **Gb/s, pps, burst**, kiểm tra packet loss/truncation và freshness.
- Inline có thiết kế **fail-open/fail-closed, bypass, HA, kênh quản trị và rollback** theo SLA.
- Chữ ký đã được chạy **detect-only**, tuning và thử nghiệm trước khi bật block.
- Có **positive test, detection test, prevention test, failure test** cùng tiêu chí PASS/FAIL/INCONCLUSIVE.
- Log có **timestamp, flow, rule/signature ID, action, asset/identity context** để điều tra và liên kết SIEM.
- Có cơ chế cảnh báo **mất visibility, engine lỗi, bypass đang hoạt động và sensor quá tải**.
- Có quy trình rà soát khi thay đổi **firewall, VPN, DNS, cloud routing, workload, ứng dụng hoặc TLS termination**.

**Kết luận:** inline IPS và out-of-band IDS không phải hai sản phẩm loại trừ nhau mà là hai cách đặt sensor với **đánh đổi khác nhau giữa ngăn chặn, quan sát và tính sẵn sàng**. Chọn đúng vị trí, hiểu rõ dữ liệu thực sự nhìn thấy, kiểm soát false positive và có bằng chứng thử nghiệm là điều kiện để biến IDS/IPS thành lớp phòng vệ đáng tin cậy trong kiến trúc an toàn mạng.

### Tài liệu tham khảo

- [NIST SP 800-94 — Guide to Intrusion Detection and Prevention Systems (IDPS)](https://csrc.nist.gov/pubs/sp/800/94/final): các mô hình IDPS, kiến trúc sensor, vận hành và phản ứng.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): thiết kế firewall và phân chia chính sách truy cập.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): kiểm soát truy cập theo tài nguyên, ngữ cảnh và ranh giới.
- [MITRE ATT&CK — Enterprise Matrix](https://attack.mitre.org/matrices/enterprise/): hệ thống hóa hành vi đối phương để xây use case phát hiện.
- [IETF RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000): nền tảng vận chuyển QUIC.
- [IETF RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS và các giới hạn quan sát plaintext.
- [IETF RFC 9232 — Network Telemetry Framework](https://www.rfc-editor.org/rfc/rfc9232): kiến trúc telemetry mạng và các nguồn quan sát.
