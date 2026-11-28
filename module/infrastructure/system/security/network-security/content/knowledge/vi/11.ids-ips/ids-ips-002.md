# Intrusion Prevention System

**Intrusion Prevention System (IPS)** là hệ thống phát hiện những dấu hiệu xâm nhập hoặc vi phạm chính sách bảo mật trong hoạt động mạng hay trên máy chủ, đồng thời **có khả năng chủ động ngăn chặn** những hoạt động phù hợp với tiêu chí đã cấu hình. Với IPS trên mạng (*Network IPS – NIPS*), hệ thống thường được đặt **trực tiếp trên đường đi của lưu lượng** (*inline*) để có thể kiểm tra và quyết định cho phép, loại bỏ hoặc xử lý gói tin trước khi chúng tới đích.

Ví dụ, một máy bên ngoài gửi yêu cầu tới API nội bộ. Firewall có thể cho phép TCP 443 vì đây là dịch vụ công khai hợp lệ. IPS quan sát lưu lượng đi qua, nhận diện một mẫu khai thác đã biết hoặc hành vi không phù hợp giao thức, rồi chặn phiên liên quan theo chính sách. Tuy nhiên, **IPS không tự xác nhận người dùng có quyền truy cập dữ liệu nghiệp vụ** và không bảo đảm phát hiện được mọi kiểu tấn công.

Trong chương **IDS và IPS** thuộc module **SECURITY_NETWORK_SECURITY**, IPS là một lớp phòng vệ hỗ trợ phân đoạn mạng, firewall, VPN, xác thực kết nối, bảo vệ DNS, Wi-Fi và cloud. Nó cũng là nguồn sự kiện quan trọng cho giám sát xâm nhập, điều tra lưu lượng và mô hình hóa mối đe dọa.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích IPS hoạt động như thế nào và phân biệt IPS với IDS, firewall và WAF.
2. Mô tả quy trình thu thập, phân tích, so khớp, ra quyết định và thực thi ngăn chặn đối với lưu lượng mạng.
3. So sánh các phương pháp phát hiện dựa trên chữ ký, bất thường, phân tích giao thức và chính sách.
4. Chọn vị trí đặt IPS tại biên, giữa các trust zone và trước tài sản quan trọng, đồng thời đánh giá các đường đi bị bỏ sót.
5. Phân tích ưu/nhược điểm của triển khai inline, chế độ phát hiện, fail-open và fail-closed.
6. Giải thích giới hạn khi lưu lượng được mã hóa, bị phân mảnh, đi qua NAT hoặc sử dụng IPv6, HTTP/3/QUIC.
7. Thiết kế chính sách phòng ngừa có phạm vi, quy trình điều chỉnh false positive và kế hoạch kiểm thử an toàn.
8. Đọc nhật ký IPS và phối hợp sự kiện với firewall, IDS, SIEM, WAF, ứng dụng và endpoint.

## 2. IPS khác IDS ở điểm nào?

**Intrusion Detection System (IDS)** quan sát, phân tích và tạo cảnh báo khi phát hiện dấu hiệu cần điều tra. **Intrusion Prevention System (IPS)** có thêm khả năng **thực thi quyết định ngăn chặn**, chẳng hạn loại bỏ gói hoặc phiên.

| Khía cạnh | IDS | IPS |
| --- | --- | --- |
| Mục tiêu trực tiếp | Phát hiện và cảnh báo | Phát hiện và có thể chặn theo chính sách |
| Vị trí mạng phổ biến | Ngoài đường truyền trực tiếp, nhận bản sao qua TAP/SPAN; cũng có biến thể khác | Thường inline để chặn lưu lượng ngay trên đường đi |
| Hành động khi khớp quy tắc | Ghi log, cảnh báo, chuyển sự kiện | Ghi log, cảnh báo, drop, reject hoặc hành động ngăn chặn được hỗ trợ |
| Ảnh hưởng khi nhận diện sai | Có thể tạo cảnh báo sai và tốn nguồn điều tra | Có thể **ngắt lưu lượng hợp lệ**, ảnh hưởng dịch vụ |
| Yêu cầu vận hành | Bao phủ lưu lượng và chất lượng phát hiện | Bao phủ lưu lượng, chất lượng phát hiện **và** độ sẵn sàng của đường truyền |
| Khả năng phòng vệ | Giúp đội phản ứng kịp thời | Có thể giảm tác động trước khi yêu cầu đến đích |

Một số hệ thống IDS ngoài đường truyền có thể gửi lệnh cho firewall, SDN controller hoặc thiết bị khác để chặn về sau. Đó là **ngăn chặn qua cơ chế phối hợp**, không giống bảo đảm mỗi gói được kiểm tra trước khi tới đích. Việc dùng tên IDS hay IPS phải dựa vào **chế độ triển khai và khả năng thực thi thực tế**, không chỉ vào nhãn sản phẩm.

### 2.1. IPS và firewall không làm cùng một việc

**Firewall lọc gói truyền thống** thường quyết định dựa trên nguồn, đích, cổng, giao thức và trạng thái phiên. Ví dụ, firewall cho máy ứng dụng kết nối DB qua TCP 5432 nhưng chặn Internet truy cập DB trực tiếp.

**IPS** phân tích sâu hơn các dấu hiệu nguy hiểm trong lưu lượng **đã có đường đi**, ví dụ một yêu cầu tới dịch vụ đang được phép nhưng có mẫu khai thác hoặc vi phạm giao thức đã biết. Chức năng phân tích sâu và chặn có thể được tích hợp trong **Next-Generation Firewall (NGFW)**; khi đó nhiều lớp kiểm soát chạy trên cùng một thiết bị.

**WAF** tập trung vào HTTP và các rủi ro ứng dụng web như injection hoặc XSS trong dữ liệu mà nó quan sát được. Network IPS có thể phân tích nhiều giao thức, nhưng không đồng nghĩa nó hiểu đầy đủ logic nghiệp vụ hoặc thay thế WAF.

**Endpoint Detection and Response (EDR)** và các cơ chế bảo vệ trên host lại nhìn thấy hành vi tại máy: tiến trình, tệp, lệnh và sự kiện hệ điều hành. IPS mạng không tự thấy mọi hành động diễn ra sau khi lưu lượng tới endpoint.

## 3. Cơ chế hoạt động của Network IPS

Với NIPS inline, đường xử lý ở mức khái niệm:

1. **Nhận lưu lượng** đi qua interface hoặc chuỗi xử lý mà IPS được gắn vào.
2. **Phân tích mạng/giao vận:** xác định IP, TCP/UDP, ngữ cảnh phiên và hướng giao tiếp.
3. **Tái dựng luồng hoặc phân tích giao thức** khi nền tảng hỗ trợ, ví dụ xem yêu cầu HTTP hoặc đặc điểm của DNS.
4. **Áp dụng chính sách phát hiện:** so khớp chữ ký, điều kiện giao thức, mẫu bất thường hoặc quy tắc do vận hành định nghĩa.
5. **Ra quyết định:** cho qua, ghi cảnh báo, chặn gói/luồng hoặc chuyển sang cơ chế phản ứng khác.
6. **Ghi nhận sự kiện và thống kê:** rule ID, nguồn/đích, hành động, thời điểm, thông tin tương quan và lý do quyết định.

~~~mermaid
flowchart TD
    A["Gói hoặc luồng đi vào IPS"] --> B["Kiểm tra IP / TCP / UDP / session"]
    B --> C["Phân tích giao thức / tái dựng khi có hỗ trợ"]
    C --> D["So khớp signature / policy / anomaly"]
    D --> E{"Đánh giá chính sách"}
    E -->|"Không có dấu hiệu chặn"| F["Cho lưu lượng đi tiếp"]
    E -->|"Cần quan sát"| G["Cho đi tiếp và tạo alert"]
    E -->|"Khớp điều kiện block"| H["Drop / reset / block theo nền tảng"]
    F --> I["Ghi số liệu vận hành nếu cấu hình"]
    G --> I
    H --> I
    I --> J["SIEM / SOC / báo cáo"]
~~~

Đây là sơ đồ logic. Cách tái dựng phiên, thứ tự xử lý rule, xử lý TLS, bộ đệm, cập nhật trạng thái và chế độ high availability **khác nhau theo sản phẩm**. Một số engine thực thi phát hiện trong thời gian thực trên từng gói, số khác dựa trên dữ liệu được tái dựng hoặc ngữ cảnh luồng.

### 3.1. Ngăn chặn nghĩa là gì?

| Hành động | Hiệu ứng | Điều cần lưu ý |
| --- | --- | --- |
| Alert / log | Tạo sự kiện, không nhất thiết chặn | Phù hợp quan sát ban đầu và điều chỉnh rule |
| Drop packet | Loại bỏ gói được chọn | Có thể làm phiên lỗi hoặc thử lại; cần kiểm tra hành vi sản phẩm |
| Drop flow / block connection | Ngăn tiếp tục phiên hoặc lưu lượng của một luồng | Mức độ duy trì trạng thái và timeout tùy nền tảng |
| Reject / reset | Gửi phản hồi từ chối hoặc cố gắng kết thúc phiên, nếu hỗ trợ | TCP reset không áp dụng giống nhau cho mọi giao thức |
| Rate limit / quarantine / dynamic block | Hạn chế hoặc cô lập theo điều kiện, khi tích hợp hỗ trợ | Có nguy cơ ảnh hưởng nhiều người dùng nếu nguồn là IP NAT dùng chung |

**Một alert không đồng nghĩa lưu lượng đã bị chặn.** Muốn báo cáo IPS ngăn chặn thành công, phải xác minh action, đường truyền thực tế, gói hoặc phiên đã bị xử lý và kết quả quan sát tại endpoint.

## 4. Các phương pháp phát hiện của IPS

### 4.1. Signature-based detection

**Phát hiện dựa trên chữ ký** nhận diện những mẫu đã biết, chẳng hạn đặc điểm của một chuỗi yêu cầu, hành vi khai thác cụ thể, dấu hiệu giao thức bất thường hoặc một mẫu lưu lượng có tính đặc trưng.

Ưu điểm: thường dễ giải thích vì có rule/signature ID và lý do khớp. Nhược điểm: phụ thuộc độ bao phủ, cập nhật và mức phù hợp của chữ ký với hệ thống đang bảo vệ. Một chữ ký dùng cho sản phẩm không hiện diện trong mạng có thể tạo nhiễu; một kiểu khai thác chưa có chữ ký có thể không bị phát hiện.

**Ví dụ phòng vệ:** một hệ thống nhận nhiều yêu cầu có mẫu tương ứng với lỗ hổng đã được công bố ở phiên bản dịch vụ cũ. Nếu engine quan sát được nội dung liên quan và chữ ký áp dụng, IPS có thể cảnh báo hoặc chặn theo chính sách đã hiệu chỉnh.

### 4.2. Anomaly-based detection

**Phát hiện bất thường** so sánh lưu lượng hiện tại với baseline hoặc mô hình hành vi mong đợi, ví dụ thay đổi lớn về số lượng kết nối, tần suất lỗi hoặc phân bố dịch vụ.

Ưu điểm: có thể phát hiện một số hành vi chưa có chữ ký cụ thể. Nhược điểm: “khác thường” không tự đồng nghĩa “độc hại”. Sao lưu, quét kiểm thử được phép, sự kiện khuyến mại hoặc thay đổi triển khai có thể làm lưu lượng tăng hợp lệ.

Một IPS có khả năng phát hiện bất thường nên có chính sách xử lý **theo mức độ tin cậy và tác động**, tránh mặc định chặn mọi biến động của baseline.

### 4.3. Protocol analysis / stateful protocol inspection

**Phân tích giao thức** kiểm tra lưu lượng có phù hợp cấu trúc và trạng thái dự kiến của giao thức hay không. Chẳng hạn, engine hiểu một phần cú pháp HTTP, DNS hoặc SMB có thể nhận diện trường không hợp lệ, luồng trao đổi trái kỳ vọng hoặc mẫu nguy hiểm gắn với giao thức.

Điểm mạnh là có thêm ngữ cảnh so với chỉ nhìn chuỗi byte thô. Tuy vậy, parser của IPS phải tương thích đủ với cách ứng dụng thực sự diễn giải dữ liệu. **Khác biệt cách parse** có thể gây phát hiện sai hoặc bỏ sót; cần cập nhật engine và kiểm thử khi backend thay đổi.

### 4.4. Policy-based detection

Một tổ chức có thể cần cảnh báo hoặc chặn những giao tiếp **không phù hợp chính sách**, dù chưa thấy dấu hiệu khai thác. Ví dụ máy chủ nghiệp vụ không nên chủ động liên lạc với giao diện quản trị switch, hoặc thiết bị khách không được sử dụng giao thức quản trị trong vùng dữ liệu.

Nhiều trường hợp này cũng có thể thực thi bằng firewall/ACL. IPS nên **bổ sung thông tin phát hiện và ngăn chặn** dựa trên hành vi/phân tích giao thức, không thay thế một ma trận phân đoạn rõ ràng.

### 4.5. Kết hợp nhiều tín hiệu

Hệ thống hiện đại có thể kết hợp chữ ký, thống kê luồng, danh tính hoặc mức độ uy tín nguồn dữ liệu. Chẳng hạn, một request chỉ khớp tín hiệu yếu có thể cần ghi alert; nhưng nếu còn có dấu hiệu vi phạm giao thức và thuộc nhóm tài sản có rủi ro cao, chính sách có thể yêu cầu hành động mạnh hơn.

**Giải thích được quyết định** quan trọng hơn một “điểm rủi ro” không rõ cơ sở. SOC cần biết dấu hiệu nào khớp, nó còn phù hợp với phiên bản ứng dụng hay không và rủi ro gián đoạn nếu chặn.

## 5. Triển khai inline, passive và chế độ vận hành

### 5.1. Inline IPS

Ở chế độ **inline**, lưu lượng cần bảo vệ đi qua IPS trước khi đến đích. Điều này cho phép IPS chặn kịp thời, nhưng cũng đưa thiết bị hoặc engine vào **đường sẵn sàng của hệ thống**.

~~~mermaid
flowchart LR
    U["Internet / vùng ít tin cậy"] --> F["Firewall: lọc kết nối"]
    F --> P["IPS inline: phân tích và có thể chặn"]
    P --> A["Ứng dụng / API"]
    P -. "Sự kiện" .-> SIEM["SIEM / SOC"]
~~~

Khi thiết bị IPS mất kết nối hoặc xử lý chậm, lưu lượng hợp lệ có thể bị ảnh hưởng. Vì vậy cần kiểm tra thông lượng, số phiên đồng thời, độ trễ, kế hoạch HA và hành vi khi hỏng.

### 5.2. Passive / detection-only

Một engine IDS có thể nhận **bản sao** lưu lượng từ TAP hoặc SPAN thay vì là điểm trung chuyển. Cách này giảm nguy cơ trực tiếp làm gián đoạn đường truyền, nhưng **không có quyền quyết định giữ lại từng gói trước khi tới đích**.

Một sản phẩm IPS cũng có thể chạy ở chế độ **monitor-only** hoặc policy ở chế độ **alert**: nó có thể nằm inline nhưng không chặn theo một số quy tắc. Phải phân biệt **vị trí triển khai** với **chế độ hành động**.

### 5.3. TAP và SPAN

- **TAP** là cơ chế cung cấp bản sao dữ liệu mạng tới thiết bị giám sát, tùy loại có thể đáp ứng mục tiêu quan sát ổn định hơn khi được thiết kế đúng.
- **SPAN / port mirroring** tạo bản sao từ switch hoặc thiết bị mạng; khi tải cao, bản sao có thể bị mất hoặc không phản ánh đầy đủ tất cả đường đi.

Những phương thức này thường dành cho **quan sát**, không phải điểm ngăn chặn inline. Cần kiểm tra điểm lấy lưu lượng, chiều truyền, VLAN, tunnel và khả năng xử lý của cảm biến.

## 6. Fail-open, fail-closed và tính sẵn sàng

Vì NIPS inline nằm trên đường truyền, hệ thống cần định nghĩa điều gì xảy ra nếu engine hoặc phần cứng ngừng hoạt động.

| Chế độ | Ý nghĩa thông dụng | Đánh đổi |
| --- | --- | --- |
| Fail-open / bypass | Lưu lượng có thể tiếp tục đi qua khi chức năng kiểm tra mất hiệu lực | Giữ dịch vụ khả dụng hơn nhưng tạo khoảng thời gian **không được IPS bảo vệ** |
| Fail-closed | Khi chức năng bảo vệ mất hiệu lực, lưu lượng bị ngắt hoặc không tiếp tục qua điểm đó | Ưu tiên ranh giới ngăn chặn nhưng có thể làm gián đoạn dịch vụ |
| High availability / failover | Một thiết bị hoặc đường dự phòng tiếp quản khi có sự cố | Cần kiểm tra tính đồng bộ trạng thái, thời gian chuyển đổi và cách xử lý traffic |

**Fail-open/closed không phải lúc nào cũng là một công tắc đơn giản.** Hành vi khác nhau khi lỗi nguồn điện, hỏng phần cứng, lỗi phần mềm, policy chưa tải xong hoặc quá tải. Một số bypass NIC chỉ xử lý một số kiểu lỗi. Phải thử nghiệm kịch bản thực tế theo tài liệu thiết bị và yêu cầu hệ thống.

Ví dụ, một cổng API công khai cần SLA cao có thể chọn cấu hình HA và fail-open trong một số điều kiện, đi kèm firewall/WAF vẫn hoạt động và cảnh báo mất IPS. Một mạng đặc biệt nhạy cảm có thể ưu tiên fail-closed. Không có lựa chọn đúng tuyệt đối cho mọi tài sản.

### 6.1. Những yếu tố công suất cần tính

- **Thông lượng kiểm tra thực tế**, không chỉ tốc độ cổng vật lý.
- **Số lượng kết nối/giây và số phiên đồng thời**, đặc biệt với lưu lượng ngắn hoặc bùng nổ.
- **Độ trễ bổ sung** khi engine phân tích sâu, giải mã hoặc tái dựng luồng.
- **Dung lượng lưu trạng thái**, bộ đệm và nguy cơ bỏ gói khi quá tải.
- **Số lượng rule bật, loại giao thức được phân tích và tính năng inspection**.
- **Đường dự phòng, HA và khả năng scale** khi lưu lượng tăng.

Một IPS có tốc độ cổng 10 Gbit/s không mặc nhiên phân tích sâu tất cả giao thức ở 10 Gbit/s trong mọi cấu hình. Cần đánh giá theo profile lưu lượng và tính năng thật.

## 7. Đặt IPS ở đâu trong kiến trúc mạng?

IPS bảo vệ tốt nhất những lưu lượng **đi qua vị trí nó có thể quan sát và thực thi**. Đặt IPS ở biên nhưng bỏ qua kết nối giữa các workload có thể để lộ đường tấn công nội bộ.

### 7.1. North–south traffic

Lưu lượng **north–south** đi giữa Internet và các dịch vụ nội bộ. IPS ở đường vào hoặc sau điểm kết thúc TLS có thể phân tích những giao thức đang được công bố. Tuy nhiên, nếu web gateway hoặc CDN đã kết thúc TLS ở nơi khác, nội dung mà IPS nhìn thấy sẽ phụ thuộc topology thực tế.

### 7.2. East–west traffic

Lưu lượng **east–west** đi giữa ứng dụng, database, máy chủ hoặc phân đoạn nội bộ. Một máy trong DMZ bị chiếm quyền có thể thử liên lạc tới nhiều dịch vụ bên trong; IPS tại điểm giao giữa zone có thể phát hiện một số mẫu bất thường mà firewall cho phép ở mức cổng.

Nếu hai workload cùng subnet trao đổi trực tiếp và **không đi qua IPS**, engine trung tâm không quan sát được kết nối đó. Có thể cân nhắc microsegmentation, host-based IPS, cảm biến phân tán hoặc chính sách tại workload.

### 7.3. Đường VPN và mạng đối tác

Lưu lượng bên trong VPN được mã hóa trên đường vận chuyển. IPS cần đặt ở vị trí **sau khi traffic được giải mã** hoặc tích hợp với hệ thống có thể cung cấp dữ liệu cần kiểm tra, tùy công nghệ. Đường VPN kết nối thành công không đồng nghĩa nguồn VPN được phép truy cập mọi zone.

### 7.4. Mạng Wi-Fi và IoT

Guest Wi-Fi, thiết bị IoT và thiết bị nhân viên có rủi ro khác nhau. IPS có thể giám sát những luồng đi qua gateway, nhưng không mặc nhiên quan sát được mọi giao tiếp ngang giữa các client trên cùng SSID/VLAN. Cần kết hợp client isolation, VLAN, firewall, NAC/802.1X và bảo vệ controller.

### 7.5. Hạ tầng cloud

NIPS có thể là appliance ảo, engine gắn với gateway hoặc dịch vụ bảo mật cloud. Tuy nhiên, **VPC/VNet, subnet và security group không tự tạo khả năng phân tích IPS ở lớp ứng dụng**. Cần xác minh đường traffic, khả năng mirror/inline, những điểm mạng được kiểm soát và chính sách IAM quản trị.

## 8. Kiến trúc minh họa nhiều trust zone

Một hệ thống đặt hàng có các zone và IP **dành riêng cho ví dụ**:

| Zone | Dải địa chỉ nội bộ minh họa | Tài nguyên |
| --- | --- | --- |
| DMZ | 10.40.10.0/24 | Reverse proxy 10.40.10.10 |
| Application | 10.40.20.0/24 | Order API 10.40.20.15 |
| Data | 10.40.30.0/24 | PostgreSQL 10.40.30.5 |
| Management | 10.40.99.0/24 | Bastion 10.40.99.10, SIEM |
| Guest/IoT | 10.40.50.0/24 | Máy khách và thiết bị ít được quản lý |

~~~mermaid
flowchart TD
    I["Khách Internet"] -->|"HTTPS"| ED["Edge firewall + WAF"]
    ED --> R["DMZ: Reverse proxy"]
    R -->|"API traffic"| IPS1["IPS A: DMZ → Application"]
    IPS1 --> API["Application: Order API"]
    API -->|"DB traffic"| IPS2["IPS B: Application → Data"]
    IPS2 --> DB[("Data: PostgreSQL")]
    B["Management: Bastion"] -->|"Quản trị theo quyền"| FW["Management firewall"]
    FW --> API
    IPS1 -. "Alerts" .-> SOC["SIEM / SOC"]
    IPS2 -. "Alerts" .-> SOC
    G["Guest / IoT"] -. "Không được đến Data / Management" .-> BLOCK["Firewall deny"]
~~~

Các IPS trong sơ đồ là **điểm kiểm soát logic**; kiến trúc thực có thể dùng một hoặc nhiều thiết bị, engine phân tán hoặc tính năng IPS trong NGFW. Sơ đồ không cho phép ngầm mở kết nối DMZ → Data: quyền truy cập DB phải đi qua dịch vụ ứng dụng được khai báo.

### 8.1. Vai trò của từng lớp

1. **Edge firewall:** chỉ cho công bố các cổng/dịch vụ cần thiết.
2. **WAF:** kiểm tra rủi ro HTTP ở điểm có thể thấy nội dung ứng dụng.
3. **IPS A:** quan sát hoặc chặn mẫu tấn công trên luồng DMZ → API đi qua nó.
4. **IPS B:** quan sát hoặc chặn mẫu bất thường trên luồng API → database đi qua nó nếu có parser/phân tích phù hợp.
5. **Database và ứng dụng:** xác thực dịch vụ, phân quyền dữ liệu, áp dụng vá lỗi và ghi audit log.
6. **SIEM/SOC:** liên kết sự kiện giữa các lớp để xác minh mức độ rủi ro và hiệu quả chính sách.

Nếu kết nối API → DB được mã hóa end-to-end, IPS B có thể chỉ nhìn thấy metadata, không đọc được câu truy vấn SQL. **Mã hóa là yêu cầu bảo mật đường truyền; không nên tắt TLS chỉ để IPS xem nội dung**. Có thể kết hợp audit log của DB và bảo vệ tại workload để bù khoảng trống quan sát.

## 9. TLS, HTTP/3/QUIC và giới hạn quan sát

### 9.1. Lưu lượng TLS

IPS mạng có thể nhìn thấy địa chỉ, cổng, kích thước, hướng và một số metadata của lưu lượng TLS. Nhưng **nội dung ứng dụng bên trong TLS không thể được đọc trực tiếp** nếu không có cách quan sát plaintext hợp lệ.

Các lựa chọn kiến trúc có thể gồm:

- Đặt IPS ở đoạn mạng **sau điểm TLS termination** và trước nơi nội dung được mã hóa lại, nếu topology cho phép.
- Tích hợp kiểm tra trong proxy, gateway hoặc thành phần ứng dụng được phép xử lý plaintext.
- Sử dụng log ứng dụng, endpoint telemetry và các cơ chế kiểm soát khác khi không thể kiểm tra nội dung mạng.

Giải mã TLS trung gian, nếu triển khai, đòi hỏi quản trị khóa/chứng thư, chính sách quyền riêng tư, phạm vi tài sản, đánh giá tác động và bảo vệ dữ liệu. Không phải mọi mô hình mTLS, certificate pinning hay giao thức đều hỗ trợ cách triển khai đó một cách đơn giản.

### 9.2. HTTP/3 và QUIC

HTTP/3 thường sử dụng **QUIC trên UDP**, có cơ chế mã hóa và phiên khác với HTTP/1.1 hoặc HTTP/2 trên TCP. Một IPS chỉ hỗ trợ phân tích HTTP trên TCP có thể không đọc được nội dung HTTP/3 ở cùng mức độ. Cần xác minh **nền tảng hỗ trợ QUIC/HTTP3 đến đâu** và kiểm tra đường đi của UDP 443.

Không mặc định lưu lượng UDP 443 là độc hại hoặc là cách tránh kiểm tra. Nó có thể hoàn toàn hợp lệ; chính sách phải dựa trên dịch vụ cần bảo vệ, khả năng quan sát và rủi ro đã đánh giá.

### 9.3. IPv6, phân mảnh và đường dẫn khác

Trong mạng dual stack, cần bật giám sát/quy tắc phù hợp cho **cả IPv4 và IPv6**. Các trường hợp IP fragmentation, extension headers của IPv6, NAT, tunnel và định tuyến bất đối xứng ảnh hưởng khả năng tái dựng luồng và đối chiếu chính sách. Hãy kiểm tra engine hỗ trợ các trường hợp này, thay vì giả định rule IPv4 có hiệu lực tương đương với IPv6.

## 10. Xây dựng chính sách ngăn chặn có kiểm soát

Một quy tắc chỉ nên tự động chặn khi **chất lượng tín hiệu và mức rủi ro phù hợp với tác động có thể xảy ra**. Chính sách không nhất thiết xử lý mọi chữ ký bằng một hành động.

| Loại phát hiện | Hành động khởi đầu có thể phù hợp | Khi cân nhắc chặn |
| --- | --- | --- |
| Dấu hiệu yếu, có nhiều nguyên nhân hợp lệ | Alert và ghi log | Sau khi có thêm điều kiện hoặc ngữ cảnh |
| Chữ ký rõ cho dịch vụ đang chạy, đã kiểm thử trên môi trường tương tự | Monitor hoặc block tùy rủi ro | Khi xác nhận chất lượng phát hiện và tác động |
| Vi phạm giao thức nghiêm trọng mà ứng dụng không cần | Alert/Block theo chính sách | Khi xác minh không gây mất chức năng hợp lệ |
| Bất thường về lưu lượng hoặc tỷ lệ lỗi | Cảnh báo, đánh giá mức ảnh hưởng | Khi có nhiều tín hiệu đủ tin cậy và giới hạn tác động |
| Hoạt động quản trị trái ma trận mạng | Firewall deny + alert/IPS nếu phù hợp | Khi đường đi và quyền được xác minh |

### 10.1. Mẫu policy minh họa

Đây là **YAML trung lập với nhà cung cấp**, không phải cú pháp có thể triển khai trực tiếp lên một sản phẩm:

~~~yaml
ipsPolicy:
  name: order-services-protection
  mode: inline
  defaultTrafficAction: allow-under-existing-network-policy
  monitoring:
    enabled: true
    exportTo: security-event-platform
    sensitiveFieldRedaction: true
  rules:
    - id: high-confidence-protocol-violation
      sourceZone: dmz
      destinationZone: application
      detectionCategory: verified-protocol-violation
      action: block
      requirements:
        - tested-with-real-application
        - approved-by-service-owner
    - id: new-signature-evaluation
      sourceZone: dmz
      destinationZone: application
      detectionCategory: newly-enabled-signature
      action: alert
      requirements:
        - review-before-enforcement
    - id: unusual-database-traffic
      sourceZone: application
      destinationZone: data
      detectionCategory: suspicious-traffic-pattern
      action: alert
      requirements:
        - correlate-with-database-audit
  exceptionGovernance:
    requireOwner: true
    requireReason: true
    requireExpiry: true
    requireRetest: true
~~~

Giá trị **defaultTrafficAction** trong ví dụ giả định firewall hoặc chính sách phân đoạn đã quyết định luồng nào được tới IPS; **không phải** chỉ dẫn cho phép mọi kết nối. IPS bổ sung việc nhận diện/chặn mẫu đáng ngờ, trong khi firewall vẫn cần có mặc định từ chối đối với những kết nối không được công bố.

### 10.2. Chính sách thay đổi chữ ký

Khi cập nhật ruleset:

1. Đọc thay đổi và xác định dịch vụ nào có thể bị ảnh hưởng.
2. Ưu tiên môi trường thử nghiệm hoặc chạy monitor-only cho rule mới có độ rủi ro false positive cao.
3. Đối chiếu log với tác vụ hợp lệ và kiểm thử trường hợp bình thường.
4. Quyết định chặn theo nhóm rule có tín hiệu đủ tin cậy, không bật chặn hàng loạt một cách mù quáng.
5. Ghi lại version, người duyệt, thời điểm, hiệu ứng quan sát và đường rollback.

**Signature freshness** quan trọng nhưng không thay thế bản vá. IPS có thể giảm rủi ro trong thời gian chờ khắc phục, không phải cam kết ngăn mọi phương thức khai thác của một lỗ hổng.

## 11. False positive, false negative và hậu quả

**False positive (FP)**: IPS đánh dấu hoặc chặn lưu lượng thực tế hợp lệ. **False negative (FN)**: lưu lượng độc hại không được phát hiện hoặc không bị chặn như chính sách kỳ vọng.

| Tình huống | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Request nghiệp vụ hợp lệ bị nhầm với chữ ký tấn công | FP, lỗi người dùng hoặc gián đoạn dịch vụ | Kiểm tra rule, parser, nội dung hợp lệ và phạm vi ngoại lệ |
| Job sao lưu tạo lưu lượng đột biến bị coi là hành vi bất thường | FP, ảnh hưởng tiến trình sao lưu | Đối chiếu lịch nghiệp vụ; điều chỉnh ngưỡng/rule |
| Tấn công đi qua đường không có IPS | FN theo phạm vi triển khai | Kiểm kê đường đi, đặt thêm cảm biến/chính sách phù hợp |
| Nội dung nguy hiểm nằm trong TLS mà IPS không giải mã | Khoảng trống quan sát | Kết hợp WAF, log ứng dụng, EDR, kiểm soát tại đầu cuối |
| Chữ ký cũ không bao phủ kiểu khai thác mới | FN | Cập nhật, kiểm thử, bổ sung phân tích hành vi và bản vá |
| Parser của IPS và backend hiểu dữ liệu khác nhau | FP/FN | Kiểm tra định dạng, cập nhật engine và rà soát ứng dụng |

### 11.1. Precision và recall

Khi có bộ kiểm thử được gán nhãn đáng tin cậy, có thể tính:

- **True positive (TP):** hoạt động độc hại được phát hiện đúng.
- **False positive (FP):** hoạt động hợp lệ bị phát hiện nhầm.
- **False negative (FN):** hoạt động độc hại bị bỏ sót.
- **True negative (TN):** hoạt động hợp lệ không bị phát hiện nhầm.

\[
\text{Precision} = \frac{TP}{TP+FP}
\qquad
\text{Recall} = \frac{TP}{TP+FN}
\]

Đối với IPS, cần đo **thêm hiệu quả thực thi ngăn chặn**: một detection TP có thể chỉ tạo alert mà không block; cũng có thể block nhưng gây tác dụng phụ. Không nên đánh đồng tỷ lệ alert cao với hiệu quả bảo vệ cao.

### 11.2. Điều chỉnh ngoại lệ an toàn

Khi một rule gây false positive, trước tiên phải xác định **điều kiện khiến rule khớp**. Ngoại lệ nên hạn chế theo hostname, dịch vụ, đích, nguồn, thời gian hoặc đặc điểm luồng **trong khả năng của engine**. Tránh tắt cả nhóm chữ ký trên mọi tài sản chỉ vì một ứng dụng cụ thể.

Mỗi ngoại lệ cần có chủ sở hữu, lý do, bằng chứng, ngày hết hạn và điều kiện kiểm tra lại. Sau khi ứng dụng được sửa hoặc ruleset thay đổi, cần xem xét bỏ ngoại lệ.

## 12. Log và triage sự kiện IPS

Một alert IPS nên đủ chi tiết để SOC biết **lưu lượng nào bị ảnh hưởng, quy tắc nào khớp và IPS đã làm gì**.

| Trường log | Mục đích |
| --- | --- |
| Timestamp, timezone, sensor ID | Đối chiếu thời gian và vị trí cảm biến |
| Source/destination IP, port, protocol | Định vị phiên và tài sản |
| Zone/interface, direction | Xác định ranh giới và đường traffic |
| Signature/rule ID, category, severity | Biết cơ sở phát hiện và độ ưu tiên |
| Action | Phân biệt alert, drop, reject, reset và các chế độ khác |
| Connection/session ID hoặc flow key | Liên kết nhiều gói cùng luồng nếu có |
| Policy/ruleset version | Giải thích khác biệt sau cập nhật |
| TLS/HTTP metadata có thể quan sát hợp pháp | Bổ sung bối cảnh khi được hỗ trợ |
| Request/correlation ID hoặc host asset ID | Liên kết với ứng dụng, endpoint và ticket |

### 12.1. Log mẫu giả lập

~~~json
{
  "timestamp": "2026-11-28T10:18:15+07:00",
  "sensor_id": "ips-app-boundary-01",
  "source_zone": "dmz",
  "destination_zone": "application",
  "source_ip": "10.40.10.10",
  "destination_ip": "10.40.20.15",
  "protocol": "tcp",
  "destination_port": 8443,
  "signature_id": "LAB-IPS-0002",
  "category": "training-policy-match",
  "severity": "medium",
  "configured_action": "drop",
  "observed_action": "drop",
  "rule_version": "lab-2026-11",
  "application_effect_verified": false,
  "note": "Dữ liệu giả lập, không phải sự kiện hệ thống thật"
}
~~~

**Configured action** và **observed action** có thể cần phân biệt: policy đặt chặn nhưng engine đang ở detection mode, traffic đã bypass, hoặc cảm biến không nằm trên tuyến thì kết quả thực tế có thể khác dự kiến. Không kết luận “đã ngăn xâm nhập thành công” chỉ dựa trên tên trường severity.

### 12.2. Quy trình xử lý alert

1. **Xác định sự kiện:** nguồn, đích, thời gian, rule, action và zone nào.
2. **Xác minh asset và bối cảnh:** ứng dụng có chạy giao thức/phiên bản liên quan không, luồng có trong ma trận kết nối không?
3. **Đối chiếu log:** firewall, WAF, DNS, VPN, application, DB audit và endpoint có dấu hiệu cùng phiên không?
4. **Kiểm tra tác động:** IPS có chặn làm gián đoạn chức năng hợp lệ không, người dùng có lỗi tăng đột biến không?
5. **Xác định mức bằng chứng:** dấu hiệu đáng ngờ, false positive, lưu lượng đã bị chặn hoặc sự cố được xác nhận.
6. **Quyết định xử lý:** tiếp tục điều tra, mở ticket, sửa dịch vụ, điều chỉnh rule hoặc ứng phó sự cố.
7. **Lưu dấu vết:** ghi các thay đổi và kết quả sau xử lý.

Một IP nguồn từ NAT, proxy hoặc VPN có thể đại diện nhiều người dùng. **Không quy kết danh tính hay ý định** chỉ từ địa chỉ IP và một chữ ký.

## 13. Kiểm thử IPS trong môi trường được ủy quyền

IPS ngăn chặn lưu lượng hợp lệ do false positive có thể gây tác động sản xuất. Vì vậy nên kiểm thử trước bằng **lab hoặc môi trường đại diện**, với dữ liệu và dấu hiệu vô hại, không cần dùng payload khai thác thực tế.

### 13.1. Mục tiêu kiểm thử

| Mã | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| T-01 | Request HTTPS nghiệp vụ bình thường qua IPS | Được phép, không bị rule thử nghiệm chặn |
| T-02 | Marker vô hại được rule lab nhận diện trên HTTP đã giải mã | Tạo alert đúng rule ID trong monitor mode |
| T-03 | Cùng marker trong lab, rule được duyệt chuyển sang drop | IPS ghi action chặn; ứng dụng không nhận yêu cầu tương ứng |
| T-04 | Dữ liệu hợp lệ nhưng gần giống điều kiện phát hiện | Không chặn nhầm sau khi điều chỉnh |
| T-05 | Dịch vụ nội bộ đi qua tuyến dự phòng | Vẫn chịu chính sách phù hợp hoặc được nhận diện rõ khoảng trống |
| T-06 | Lưu lượng TLS end-to-end IPS không có plaintext | Không kỳ vọng signature dựa trên nội dung HTTP sẽ hoạt động |
| T-07 | IPv6 và UDP/QUIC hợp lệ trong môi trường có hỗ trợ | Có chính sách/đường kiểm tra tương ứng, không gây lỗi do cấu hình |
| T-08 | Chuyển đổi HA/failover trong lab | Phù hợp yêu cầu availability và hành vi fail mode đã khai báo |

### 13.2. Marker kiểm thử vô hại

Ví dụ, tổ chức có thể cấu hình **rule lab** để nhận diện giá trị header HTTP do chính đội kiểm thử tạo:

~~~http
GET /health HTTP/1.1
Host: lab.example.test
X-IPS-Lab-Marker: approved-training-002
~~~

Rule lab chỉ cần nhận diện chuỗi **approved-training-002** trong trường header đã biết; nó không đòi hỏi mô phỏng khai thác thật. Nếu dùng HTTPS, IPS phải có khả năng quan sát nội dung HTTP ở vị trí triển khai. **example.test** chỉ là tên miền dành cho minh họa; phép thử phải chạy trên host lab thực sự thuộc phạm vi được cấp quyền.

Khi chạy ở chế độ monitor, request nên tới ứng dụng và có log cảnh báo. Khi chạy ở chế độ drop trong lab, cần xác nhận **đích không nhận request** và IPS báo đúng action, không chỉ thấy client timeout. Timeout còn có thể do nhiều lỗi mạng khác.

### 13.3. Kế hoạch kiểm tra hiệu năng và khả dụng

Không thực hiện tải cao trên hệ thống chưa được phê duyệt. Trong môi trường thử nghiệm phù hợp, đo baseline trước/sau bật IPS về:

- Độ trễ của request và luồng quan trọng.
- Thông lượng, số kết nối mới và mức dùng CPU/bộ nhớ.
- Tỷ lệ thất bại của dịch vụ, số phiên bị ngắt.
- Tỷ lệ rule chặn nhầm trên bộ dữ liệu hợp lệ.
- Tình trạng hàng đợi, packet drop do quá tải và log bị mất.
- Hành vi khi đổi ruleset, restart engine hoặc failover có kiểm soát.

Cần ghi rõ **điều kiện thử, cấu hình rule và profile lưu lượng**. Kết quả trên lab không tự chứng minh hiệu năng ở mọi tải thực tế.

## 14. Bảo vệ DNS, VPN, Wi-Fi và môi trường cloud

### 14.1. DNS

IPS có parser DNS có thể phát hiện một số dấu hiệu bất thường về định dạng, tần suất truy vấn hoặc mẫu giao tiếp đáng ngờ. Tuy nhiên, truy vấn DNS hợp lệ cũng có thể nhiều và không ổn định theo thời gian. Nên kết hợp resolver log, DNS policy và kiểm soát nguồn–đích thay vì chặn bừa mọi tên miền lạ.

DNS qua HTTPS/TLS tạo thêm giới hạn quan sát vì nội dung được mã hóa. Firewall hoặc IPS dựa trên cổng không thể suy ra toàn bộ nội dung DNS chỉ từ việc thấy TCP/UDP 443.

### 14.2. VPN

VPN mã hóa traffic giữa các đầu kết nối. Nếu IPS đặt ở đường truyền bên ngoài tunnel, nó thường không thấy payload nội bộ. Cần thiết kế quan sát tại điểm sau giải mã hoặc kết hợp log VPN, truy cập theo danh tính và bảo vệ endpoint.

### 14.3. Mạng không dây

IPS mạng ở gateway có thể phân tích lưu lượng đi qua gateway, nhưng không mặc định thấy tất cả giao tiếp ngang trong cùng Wi-Fi. **Wireless IPS (WIPS)** là nhóm giải pháp riêng có thể theo dõi các sự kiện và mối đe dọa ở môi trường vô tuyến; cần phân biệt với NIPS xem lưu lượng IP tại gateway.

### 14.4. Cloud và container

Trong cloud, engine IPS có thể chạy trên appliance ảo, gateway bảo mật, host hoặc tích hợp dịch vụ managed. Điều quyết định không phải “đã có IPS trong VPC” mà là **luồng quan trọng có được đưa qua điểm kiểm tra**, chính sách nào có hiệu lực, có log, có HA, có đường bypass nào không.

Trong Kubernetes và môi trường container, thay đổi IP/workload nhanh làm chính sách tĩnh khó duy trì. Có thể cần nhãn, định danh workload, policy mạng và telemetry ở node/service mesh; các công nghệ này **không tự trở thành IPS** nếu không có cơ chế phân tích và ngăn chặn tương ứng.

## 15. Những lỗi triển khai và vận hành phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ lắp IPS ở Internet edge | Không thấy nhiều kết nối east–west | Kiểm kê các luồng quan trọng và điểm giao zone |
| Tin rằng IPS luôn đọc được HTTPS | Bỏ sót dấu hiệu chỉ có trong payload đã mã hóa | Thiết kế điểm quan sát hợp lệ hoặc bổ sung log ở ứng dụng |
| Bật toàn bộ signature ở chế độ block ngay trên production | False positive có thể làm gián đoạn dịch vụ | Monitor, kiểm thử, phân nhóm rule và triển khai chặn có kiểm soát |
| Chỉ đếm số alert như chỉ số an toàn | Nhiều cảnh báo không phản ánh hiệu quả hoặc sự cố | Đánh giá TP/FP/FN, action thực tế và tác động vận hành |
| Quên fail-open/fail-closed và HA | Sự cố IPS làm ngắt mạng hoặc mất lớp bảo vệ | Định nghĩa và kiểm thử hành vi fail mode |
| Mặc định IPS thay thế firewall | Đường truy cập không cần thiết vẫn mở | Dùng phân đoạn, default deny và quyền tối thiểu |
| Không theo dõi ruleset version | Khó lý giải phát hiện thay đổi | Ghi phiên bản, thời gian cập nhật, rollback |
| Vô hiệu cả nhóm chữ ký vì một false positive | Tạo khoảng trống phát hiện rộng | Ngoại lệ hẹp có chủ sở hữu và hạn rà soát |
| Không xét IPv6/QUIC/NAT/tunnel | Có đường đi không được kiểm soát như kỳ vọng | Kiểm kê hai họ IP, giao thức và mọi tuyến |
| Không đối chiếu log với dịch vụ | Nhầm cảnh báo với khai thác thành công | Ghép log IPS, firewall, ứng dụng và endpoint |

## 16. Tình huống phân tích: yêu cầu API đáng ngờ

Giả sử một tổ chức công bố Order API qua reverse proxy. Firewall cho phép kết nối tới API trên cổng 8443 từ proxy. IPS ở ranh giới DMZ → Application quan sát được một request có mẫu phù hợp một chữ ký nguy hiểm dành cho giao thức hoặc phiên bản dịch vụ cụ thể.

**Nếu policy ở monitor mode:** IPS ghi alert và cho lưu lượng đi tiếp. SOC cần đối chiếu rule, phiên bản API, log WAF và ứng dụng, xác định request có được xử lý hay bị ứng dụng từ chối. Không nên báo cáo rằng IPS đã chặn.

**Nếu policy ở block mode và lưu lượng đi qua IPS:** IPS có thể loại bỏ gói hoặc phiên. SOC cần xác nhận action thực tế, log tại đích và ảnh hưởng tới người dùng. Một kết nối bị chặn không chứng minh tất cả đường khai thác khác đã được loại bỏ.

**Nếu API có TLS end-to-end qua IPS:** chữ ký yêu cầu đọc nội dung HTTP có thể không hoạt động tại vị trí đó. Biện pháp hợp lý là dựa trên WAF/gateway ở điểm có plaintext, log của API, kiểm soát quyền truy cập, bản vá và bảo vệ endpoint, thay vì mặc định bỏ mã hóa.

**Nếu API đang chạy phiên bản không bị ảnh hưởng:** chữ ký có thể khớp request nhưng không có lỗ hổng tương ứng, tạo cảnh báo cần phân tích. Tùy mức độ tin cậy, tổ chức có thể chuyển rule về alert và kiểm tra chất lượng phát hiện trước khi chặn.

**Bài học:** IPS tăng khả năng ngăn chặn trong thời gian thực, nhưng **ngữ cảnh tài sản, khả năng quan sát, action và bằng chứng tại ứng dụng** quyết định chất lượng kết luận.

## 17. Câu hỏi tự kiểm tra

1. IPS khác IDS ở điểm nào? Tại sao vị trí inline lại quan trọng nếu muốn chặn trước khi gói đến đích?
2. Một thiết bị ghi alert “high severity” nhưng policy ở monitor-only. Có thể kết luận traffic đã bị chặn không?
3. Vì sao IPS phát hiện chữ ký dựa vào nội dung HTTP có thể bỏ sót yêu cầu HTTPS nếu TLS không được giải mã tại nơi quan sát?
4. Một request hợp lệ bị IPS drop sau cập nhật ruleset. Bạn cần kiểm tra những dữ kiện nào trước khi tạo ngoại lệ?
5. So sánh fail-open và fail-closed trong tình huống IPS inline bị hỏng. Điều kiện nào ảnh hưởng quyết định lựa chọn?
6. Vì sao một IPS đặt ở router biên chưa chắc thấy lưu lượng giữa hai pod hoặc hai máy cùng subnet?
7. Trong mạng có VPN, đặt IPS trước tunnel và sau tunnel có thể tạo khác biệt gì về dữ liệu quan sát?
8. Nếu phát hiện một chữ ký khớp nhưng ứng dụng không chạy phiên bản dễ bị ảnh hưởng, SOC nên kết luận thế nào?
9. Hai chỉ số precision và recall giúp đánh giá điều gì? Vì sao chúng chưa đủ để đo tác động chặn của IPS?
10. Một tổ chức có cả IPv4 và IPv6, HTTP/2 và HTTP/3. Những vấn đề nào cần kiểm tra khi triển khai IPS?

**Gợi ý:** (1) IPS có thể thực thi chặn, thường cần nằm trên tuyến; (2) không; (3) payload mã hóa không thể đọc nếu thiếu điểm quan sát hợp lệ; (4) rule ID, ngữ cảnh và tác động ứng dụng; (5) cân bằng giữa bảo mật và sẵn sàng; (6) traffic có thể không đi qua cảm biến; (7) khả năng thấy payload sau giải mã; (8) ghi nhận phát hiện nhưng chưa xác nhận khai thác; (9) chất lượng phân loại, cần đo action/gián đoạn; (10) đường đi, parser, metadata, mã hóa, IPv6/QUIC và hiệu năng.

### Bài tập thiết kế

Bạn phụ trách một mạng gồm **DMZ**, **Application**, **Data**, **Management**, **Guest/IoT** và **đầu VPN nhân viên**. Hãy:

1. Chọn hai ranh giới ưu tiên đặt IPS, nêu rủi ro muốn phát hiện và luồng nào sẽ đi qua đó.
2. Phân biệt việc nào nên xử lý bằng firewall/ACL, việc nào cần WAF, IPS hoặc log ứng dụng.
3. Thiết kế ba rule IPS ở mức mô tả: một rule block sau kiểm thử, một rule alert để đánh giá và một trường hợp cần điều tra thủ công.
4. Xây dựng bốn phép kiểm thử gồm hai traffic hợp lệ, một marker lab vô hại và một tình huống failover được phê duyệt.
5. Nêu các trường log cần thu thập, tiêu chí kết luận block thành công và giới hạn khi traffic mã hóa.
6. Đề xuất cách kiểm soát ngoại lệ, kế hoạch rollback và người chịu trách nhiệm xác minh sau thay đổi.

Bài đạt yêu cầu khi mỗi quyết định có **đường đi, điểm thực thi, mục đích, điều kiện đo và giới hạn được nêu rõ**.

## 18. Những điều cần ghi nhớ

- **IPS phát hiện và có thể ngăn chặn lưu lượng đáng ngờ theo chính sách**; IDS chủ yếu quan sát và cảnh báo.
- **Network IPS inline nằm trên đường truyền** nên hiệu quả chặn và độ sẵn sàng của dịch vụ phụ thuộc trực tiếp vào cách triển khai.
- **Signature, anomaly, protocol analysis và policy detection có ưu nhược điểm khác nhau**; không một phương pháp nào phát hiện mọi tấn công.
- **False positive có thể gây gián đoạn thật**. Hãy dùng monitor mode, kiểm thử và ngoại lệ có phạm vi trước khi mở rộng chặn tự động.
- **IPS không tự xem được nội dung đã mã hóa**, không bảo đảm thấy mọi luồng east–west và không thay thế firewall, WAF, IAM hay vá lỗi.
- **Cần tính cả fail-open/fail-closed, HA, công suất, IPv6, QUIC, NAT và VPN** khi đưa IPS vào kiến trúc mạng.
- **Bằng chứng ngăn chặn phải gồm action thực tế và kết quả tại đích**, không chỉ là độ nghiêm trọng của một alert.
- **IPS hiệu quả là một phần của phòng vệ nhiều lớp** với phân đoạn mạng, kiểm soát truy cập, log tập trung, SOC và bảo vệ tại ứng dụng/endpoint.
