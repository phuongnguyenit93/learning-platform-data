# Giới hạn của threat model

> **Chương:** Threat modeling mạng  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Phạm vi kiến thức:** Phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, hạ tầng cloud, phân tích lưu lượng, giám sát xâm nhập và kiến trúc mạng an toàn.

## 1. Threat model có thể và không thể làm gì?

**Threat modeling (mô hình hóa mối đe dọa)** là quá trình xác định tài sản cần bảo vệ, hệ thống và luồng dữ liệu, ranh giới tin cậy, tác nhân đe dọa, khả năng bị tấn công và biện pháp xử lý rủi ro. Sản phẩm thường là sơ đồ hệ thống, các kịch bản tấn công, danh sách giả định, đánh giá rủi ro và kế hoạch kiểm soát.

Threat model giúp đội bảo mật **đặt đúng câu hỏi, chọn đúng biện pháp và giải thích quyết định**. Nhưng nó chỉ phản ánh **phạm vi, dữ liệu, giả định và thời điểm thực hiện**. Một mô hình được lập kỹ lưỡng vẫn không thể chứng minh rằng hệ thống an toàn tuyệt đối, mọi nguy cơ đã được nhận diện, mọi kiểm soát hoạt động đúng hay tương lai sẽ giống hiện tại.

Ví dụ: một sơ đồ viết “Internet → WAF → Application → Database (private)”. Từ đó chưa thể kết luận database thực sự không có public endpoint, rằng quyền cloud IAM không cho phép truy cập trực tiếp, hay mọi gói tin đều đi qua WAF. Các kết luận này cần **bằng chứng về cấu hình và kiểm chứng vận hành**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích giới hạn về phạm vi, tính đầy đủ, độ chính xác và độ mới của threat model.
2. Nêu điểm mù của các kỹ thuật DFD, STRIDE, attack tree và MITRE ATT&CK khi áp dụng vào mạng.
3. Phân biệt giả định, bằng chứng, biện pháp được đề xuất, kiểm soát được xác minh và rủi ro tồn dư.
4. Phân tích giới hạn của mạng phân đoạn, firewall, VPN, IDS/IPS, DNS, Wi-Fi và cloud dưới góc nhìn threat model.
5. Thiết lập phương pháp kiểm chứng và cập nhật mô hình khi hệ thống hoặc mối đe dọa thay đổi.

## 2. Bốn nhóm giới hạn chính

| Nhóm giới hạn | Câu hỏi phải đặt | Hệ quả nếu bỏ qua |
|---|---|---|
| **Phạm vi** | Mô hình bao gồm hệ thống, môi trường, người dùng và bên thứ ba nào? | Các đường tấn công nằm ngoài sơ đồ bị hiểu nhầm là không tồn tại. |
| **Thông tin và giả định** | Inventory, kiến trúc, quyền truy cập và dữ liệu đầu vào đáng tin đến mức nào? | Mô hình suy luận hợp lý từ tiền đề sai và đưa ra kết luận sai. |
| **Phương pháp và con người** | Công cụ phân tích và chuyên môn của nhóm có phát hiện được những tình huống cần quan tâm? | Bỏ sót lỗ hổng liên lớp, chuỗi tấn công hoặc rủi ro quy trình. |
| **Thời gian và kiểm chứng** | Mô hình còn khớp hệ thống thực? Biện pháp bảo vệ đã được xác minh? | Cấu hình drift, thay đổi cloud và kiểm soát lỗi khiến kết luận cũ không còn đúng. |

**Giới hạn của mô hình** không phải lý do để ngừng threat modeling. Điều quan trọng là công khai những gì chưa biết, theo dõi phần rủi ro còn lại và nối mỗi kết luận quan trọng với bằng chứng.

## 3. Giới hạn về phạm vi: ngoài hình vẽ không có nghĩa là ngoài rủi ro

Để phân tích có trọng tâm, nhóm phải chọn phạm vi: ví dụ mạng VPC chạy ứng dụng nội bộ và luồng truy cập qua VPN. Tuy nhiên, một kịch bản tấn công có thể bắt đầu ở thành phần không nằm trong sơ đồ rồi đi qua nhiều vùng tin cậy.

Những phạm vi dễ bị bỏ quên:

- **Thiết bị đầu cuối:** máy làm việc bị nhiễm mã độc, token SSO bị chiếm, EDR/MDM không hoạt động.
- **Mạng văn phòng và Wi-Fi:** SSID khách, IoT, VLAN, cổng switch, điểm truy cập giả mạo, chuyển tiếp ngang giữa các máy.
- **Đường quản trị:** bastion, SSH/RDP, quản trị hypervisor, console cloud, tài khoản khẩn cấp.
- **Hạ tầng hỗ trợ:** DNS, DHCP, IdP, NTP, CA, giám sát, sao lưu, CI/CD và các dịch vụ nhà cung cấp.
- **Đường đi ngoài mong đợi:** IPv6 song song IPv4, NAT, split tunneling, route dự phòng, API public khác với đường vào ứng dụng chính.
- **Quy trình vận hành:** cấp quyền tạm, rule “mở trong lúc xử lý sự cố”, chuyển giao ca trực, khôi phục thảm họa.

Một bản threat model cần chỉ rõ **in scope**, **out of scope**, phụ thuộc liên quan và **người chịu trách nhiệm** đối với khoảng trống. Phần chưa khảo sát phải được ghi là *chưa đánh giá*, không tự nhận là *rủi ro thấp*.

| Thành phần | Phạm vi ghi nhận | Bước tiếp theo |
|---|---|---|
| VPC ứng dụng, subnet DB, firewall | Trong phạm vi | Lập luồng dữ liệu và ma trận truy cập. |
| Nhà cung cấp DNS, IdP | Phụ thuộc bên ngoài | Xem bảo đảm dịch vụ, fallback và đường phụ thuộc. |
| Laptop nhà thầu | Chưa có dữ liệu về posture | Phối hợp đội endpoint/IAM để xác minh. |
| Hệ thống sao lưu quản trị | Ngoài đợt phân tích này | Giao owner và lên lịch đánh giá riêng. |

## 4. Giới hạn của sơ đồ và mức trừu tượng

### 4.1. DFD không phải bản đồ mạng đầy đủ

**Data Flow Diagram (DFD)** thể hiện thực thể, tiến trình, kho dữ liệu, luồng dữ liệu và ranh giới tin cậy (*trust boundary*). Nó đặc biệt có ích để đặt câu hỏi về thông tin nhạy cảm và hành vi tại điểm vượt ranh giới.

Tuy vậy, một DFD thường không biểu diễn đủ:

1. **Data plane và control plane:** đường truyền ứng dụng không đồng nhất với luồng quản trị router, firewall, hypervisor, cloud control plane.
2. **Định tuyến thực tế:** NAT, policy route, ECMP, đường đi/về bất đối xứng, đường dự phòng, tunnel hoặc chồng nhiều lớp network overlay.
3. **Quy tắc truy cập thực tế:** thứ tự rule, rule kế thừa, default allow, security group, NACL, host firewall và quyền theo danh tính.
4. **IPv4/IPv6:** hai họ địa chỉ có thể dùng chính sách khác nhau; ICMPv6/Neighbor Discovery cần thiết để mạng hoạt động.
5. **Hệ thống biến động:** pod/container có IP tạm, workload tự mở rộng, instance được tạo/hủy và gán quyền theo nhãn.
6. **Lớp liên kết và phụ thuộc ngoài:** broadcast/multicast, Wi-Fi, ARP/NDP, DNS, BGP hoặc các dịch vụ ngoài hệ thống.

Do đó, ranh giới trong sơ đồ là **một giả thuyết kiến trúc**. Muốn khẳng định phân đoạn đang ngăn truy cập trái phép, phải đối chiếu **route, ACL, firewall rule, quyền IAM, luồng thực tế và kiểm thử kết nối**.

### 4.2. Quá đơn giản và quá chi tiết đều có hại

Nếu gộp toàn bộ “Backend” vào một hộp, người phân tích dễ bỏ qua quản trị, sao lưu và giao diện nội bộ. Nếu vẽ mọi IP/cổng trong một sơ đồ duy nhất, mô hình có thể trở nên khó đọc và nhanh lỗi thời.

Nên dùng nhiều mức nhìn: **bức tranh kiến trúc** → **luồng dữ liệu hoặc nghiệp vụ quan trọng** → **chi tiết đường tấn công tại thành phần rủi ro cao**. Tài liệu cần xác định rõ mỗi mức trả lời câu hỏi nào, điều gì vẫn phải tra trong cấu hình kỹ thuật.

## 5. Giới hạn của phương pháp phân tích

Các khung phân tích giúp giảm bỏ sót, nhưng **không tự bảo đảm độ bao phủ hoàn toàn**.

| Phương pháp | Giá trị | Giới hạn |
|---|---|---|
| **STRIDE** | Câu hỏi theo nhóm: giả mạo, sửa đổi, chối bỏ, lộ thông tin, từ chối dịch vụ và nâng quyền | Không tự khám phá đủ mọi đường tấn công, phụ thuộc bên thứ ba hoặc tình huống vận hành. |
| **Attack tree** | Phân rã một mục tiêu gây hại thành bước và điều kiện | Phụ thuộc mục tiêu, nhánh và giả định của người lập; nhánh chưa nghĩ tới bị bỏ sót. |
| **MITRE ATT&CK** | Ngôn ngữ chung mô tả hành vi đối thủ, hỗ trợ xác định telemetry và kiểm soát | Không phải danh sách đầy đủ mọi kỹ thuật hay thước đo chứng minh phòng vệ đủ. |
| **Ma trận risk 3×3/5×5** | Hỗ trợ thảo luận và so thứ tự xử lý | Điểm số thường chủ quan; không mặc nhiên là xác suất hay tổn thất đã định lượng. |

Ví dụ STRIDE trên VPN giúp nhận diện **Spoofing** khi tài khoản bị chiếm và **Elevation of Privilege** khi user đi tới subnet quản trị. Nhưng phân loại này **không tự chỉ ra** việc người dùng có thể bị lừa xác thực, quy trình cấp quyền khẩn cấp có ngoại lệ hay thiết bị đã được xác thực nhưng không còn đáng tin.

**Thiên lệch đội ngũ** cũng tạo điểm mù. Chuyên gia mạng có thể chú ý route và firewall, nhóm ứng dụng chú ý API, đội IAM chú ý đặc quyền, SOC chú ý log, trong khi vận hành hiểu rõ các exception. Đánh giá chéo các luồng trọng yếu giúp phát hiện các phụ thuộc mà một nhóm chuyên môn khó nhìn thấy.

## 6. Giới hạn từ dữ liệu đầu vào và các giả định

Các giả định sau cần được kiểm chứng trước khi dùng để đóng rủi ro:

- “Mọi truy cập vào ứng dụng đều qua VPN.”
- “Tất cả máy chủ đều gửi log đầy đủ về SIEM.”
- “Database chỉ có private IP nên Internet chắc chắn không thể tới.”
- “Firewall đang áp dụng đúng rule trong tài liệu thiết kế.”
- “Chỉ admin có quyền truy cập cổng quản trị.”
- “Bảo vệ DNS áp dụng cho mọi thiết bị và mọi hình thức truy vấn.”

### Sổ giả định và bằng chứng

| ID | Giả định | Nếu sai | Bằng chứng cần kiểm tra | Trạng thái |
|---|---|---|---|---|
| A-01 | DB không công khai | Có đường trực tiếp bỏ qua ứng dụng | Public endpoint, route table, SG/NACL, phép thử reachability | Chưa xác minh |
| A-02 | Quản trị chỉ qua VPN + MFA | Có đường quản trị khác hoặc tài khoản không MFA | VPN policy, IdP, bastion, IAM, log access | Chưa xác minh |
| A-03 | IDS quan sát đủ các luồng trọng yếu | Tấn công đi qua vùng không có sensor | Bản đồ sensor, traffic mirror/tap, kiểm thử cảnh báo | Chưa xác minh |
| A-04 | Phân đoạn áp dụng cả IPv6 | IPv6 là đường truy cập ngoài chính sách | Cấu hình dual-stack và phép thử cho từng zone | Chưa xác minh |

Ghi **mức tin cậy**, **nguồn chứng cứ**, **ngày xác minh** và **owner** cho từng giả định rủi ro cao. Đánh giá dựa trên tài liệu cũ cần được phân biệt với bằng chứng lấy từ cấu hình đang chạy.

## 7. Giới hạn thời gian: mô hình có thể lỗi thời sau một lần thay đổi

Threat model là ảnh chụp hệ thống tại một thời điểm. Trong thực tế, firewall được mở cổng tạm, route mới xuất hiện, quyền cloud IAM được thêm, nhà thầu có quyền VPN, hệ thống đổi DNS, ứng dụng triển khai thêm API hoặc mạng chuyển sang dual-stack.

~~~mermaid
flowchart TD
    A[Ngày 1: Mô hình và chính sách được duyệt] --> B[Ngày 10: Thêm subnet vận hành]
    B --> C[Ngày 11: Mở rule tạm để xử lý sự cố]
    C --> D[Ngày 30: Rule chưa thu hồi]
    D --> E[Mô hình vẫn mô tả truy cập tối thiểu]
    E --> F[Nhận thức rủi ro lệch với hệ thống thật]
~~~

Đặt **sự kiện kích hoạt cập nhật** khi:

- Thêm luồng dữ liệu, đối tác, dịch vụ Internet-facing, API hoặc kênh quản trị.
- Đổi subnet, firewall, router, VPN, DNS, Wi-Fi, mô hình truy cập từ xa hoặc cloud network policy.
- Đổi danh tính, MFA, nhóm quyền, thiết bị đầu cuối được phép, service account.
- Bật IPv6, tạo môi trường Kubernetes, chuyển cloud region hoặc thêm mạng hybrid.
- Xuất hiện sự cố, lỗ hổng có ảnh hưởng thực tế, hành vi đối thủ mới hoặc phát hiện rule sai.

Rà soát định kỳ theo mức quan trọng cũng cần thiết, nhưng **lịch định kỳ không thay thế đánh giá ngay khi thay đổi lớn**. Chủ hệ thống phải biết ai khởi tạo rà soát và cách tìm sự khác biệt giữa sơ đồ với cấu hình thật.

## 8. Chấm điểm rủi ro có giới hạn

Khả năng xảy ra và tác động kinh doanh thường được xếp theo các mức “thấp/trung bình/cao” hoặc điểm 1–5. Một kết quả 4 × 5 = 20 trên ma trận 5×5 là **thứ bậc ưu tiên theo quy ước**, không tự có nghĩa xác suất khoa học hay giá trị thiệt hại tiền tệ.

Các nguồn bất định:

- Không biết chắc mục tiêu, năng lực và nguồn lực của đối thủ.
- Thiếu thông tin về khả năng tiếp cận/khai thác lỗ hổng trên hệ thống cụ thể.
- Tác động phụ thuộc dữ liệu, thời điểm, khôi phục, khách hàng và nghĩa vụ pháp lý.
- Tấn công có thể kết hợp nhiều điểm yếu; rủi ro giữa IAM, mạng và log không độc lập.
- Dữ liệu lịch sử sự cố có thể thiếu hoặc mang thiên lệch báo cáo.

**CVSS** hỗ trợ biểu đạt mức nghiêm trọng kỹ thuật của lỗ hổng theo phương pháp chuẩn hóa, nhưng **không trực tiếp là xác suất bị tấn công** của tổ chức hay mức thiệt hại kinh doanh của hệ thống.

Thay vì chỉ ghi “Cao”, nên mô tả **kịch bản**, **đường tấn công**, **tài sản**, **hậu quả**, **điểm ưu tiên minh họa**, **mức tin cậy**, **chứng cứ**, **kiểm soát**, **rủi ro tồn dư** và **owner**.

| Trường | Ví dụ minh họa |
|---|---|
| Kịch bản | Tài khoản VPN của nhà thầu bị chiếm, truy cập trái phép subnet quản trị. |
| Đường đi | Thiết bị nhà thầu → VPN gateway → ACL → cổng quản trị. |
| Tác động | Thay đổi cấu hình firewall, dừng dịch vụ hoặc truy cập thông tin nhạy cảm. |
| Khả năng/tác động | Giả định 3/5 và 5/5, chỉ dùng để ưu tiên tương đối. |
| Độ tin cậy | Thấp: chưa kiểm chứng rule và mức bảo vệ MFA của tài khoản nhà thầu. |
| Bằng chứng cần có | ACL hiệu lực, role mapping, access log, thử kết nối bằng user giới hạn. |
| Biện pháp | Phân đoạn quản trị, MFA chống phishing, quyền tối thiểu, EDR và giám sát. |
| Rủi ro tồn dư | Thiết bị/tài khoản hợp lệ vẫn có thể bị xâm nhập hoặc lạm dụng. |

Không nên hạ mức rủi ro chỉ vì một control xuất hiện trong tài liệu; cần bằng chứng triển khai và kết quả kiểm chứng tương ứng.

## 9. “Có kiểm soát” trên sơ đồ khác với “kiểm soát hiệu quả”

| Kiểm soát | Điều threat model dễ bỏ qua | Cách xác minh |
|---|---|---|
| **Phân đoạn mạng** | Route ngoại lệ, policy quá rộng, đường IPv6 hay quyền IAM bypass | Ma trận source/zone → destination → port/protocol; route, flow log và kiểm thử deny/allow. |
| **Firewall / security group** | Thứ tự rule, default allow, exception lâu ngày, host firewall và kết nối chiều về | Cấu hình hiệu lực, lịch sử thay đổi, kiểm thử theo các đường truy cập. |
| **VPN và xác thực** | VPN chỉ bảo vệ đường kết nối; endpoint đã xác thực vẫn có thể bị chiếm hoặc lạm dụng | MFA, device posture, quyền theo vai trò, log phiên, đường admin phụ. |
| **IDS/IPS/NDR** | Luồng mã hóa, vị trí sensor sai, giới hạn hiệu năng, false positive/negative | Telemetry coverage và diễn tập kiểm chứng cảnh báo đầu cuối. |
| **DNS protection** | Resolver thay thế, DoH/DoT đi ngoài chính sách, DNS cấu hình sai | Egress policy, resolver log, hành vi truy vấn ở client. |
| **Wi-Fi** | Rogue AP, client isolation sai, VLAN không khớp, thiết bị IoT yếu | Cấu hình WPA-Enterprise/802.1X nếu áp dụng, VLAN và kiểm thử truy cập. |
| **Cloud network** | Public endpoint, NACL/SG, service mesh, route/IAM thay đổi | Inventory từ API, policy-as-code, phát hiện drift và kiểm thử. |
| **SIEM/SOC** | Không thu đủ nguồn log, mất event, cảnh báo không có người xử lý | Đối chiếu asset với telemetry, tạo sự kiện thử có kiểm soát, kiểm tra phản ứng. |

Một kiểm soát còn có thể làm gián đoạn mạng nếu áp dụng sai: chặn toàn bộ ICMP có thể gây vấn đề Path MTU Discovery; với IPv6, chặn ICMPv6 Neighbor Discovery hợp lệ có thể làm mất kết nối. Threat model phải xét **cả truy cập quá rộng lẫn cản trở lưu lượng điều khiển thiết yếu**.

## 10. Giới hạn trước các đường tấn công kết hợp và đe dọa mới

Đối thủ có thể nối các bước tưởng như độc lập:

~~~text
Lừa lấy thông tin đăng nhập
  → lợi dụng ngoại lệ MFA hoặc thiết bị đã được tin cậy
  → kết nối VPN bằng danh tính hợp lệ
  → đi tới subnet bị cấp quyền quá rộng
  → lợi dụng tài khoản quản trị hoặc API cloud
  → lấy dữ liệu, làm gián đoạn hệ thống hoặc tắt giám sát
~~~

Nếu chỉ mô hình hóa **VPN**, có thể bỏ lỡ quyền cloud. Nếu chỉ xem **firewall**, có thể bỏ lỡ trạng thái danh tính. Nếu chỉ xem **ứng dụng**, có thể không tính kênh sao lưu và quản trị. Kết quả đúng tại một thành phần có thể **không đúng cho đường tấn công xuyên nhiều thành phần**.

Threat model cũng không đoán chắc được lỗ hổng chưa công bố, biến thể khai thác mới, lỗi firmware, sự cố nhà cung cấp, thất bại nhiều dịch vụ cùng lúc hoặc hành vi sai sót trong vận hành. Các danh mục kỹ thuật không bao phủ chắc chắn mọi nguy cơ tương lai. Cần **phòng vệ nhiều lớp, khả năng phát hiện, ứng cứu và khôi phục** khi một giả định quan trọng bị phá vỡ.

## 11. Ví dụ: quản trị hạ tầng cloud từ văn phòng và máy từ xa

Giả sử tổ chức có ứng dụng quản trị mạng trên cloud, nhân viên truy cập qua SSO/VPN, cơ sở dữ liệu nằm trong subnet riêng, DNS có nhà cung cấp ngoài và SOC nhận log. Đây chỉ là một **mô hình giả định phục vụ học tập**.

~~~mermaid
flowchart LR
    H[Nhân viên và thiết bị] --> W[Wi-Fi / LAN]
    H --> I[Internet]
    W --> V[VPN / Identity]
    I --> V
    V --> F[Firewall / Cloud routes]
    F --> A[Ứng dụng quản trị]
    A --> D[(Database)]
    A --> N[DNS / external services]
    A -. Audit logs .-> S[SOC / SIEM]
    F -. Network logs .-> S
~~~

Sơ đồ thể hiện các trust boundary chính: **endpoint → mạng truy cập → vùng đã xác thực → cloud → dữ liệu**, kèm phụ thuộc DNS và SOC. Nhưng nó **chưa mô tả** kênh quản trị trực tiếp cloud, quyền service account, public endpoint hoặc cách truy cập subnet bằng IPv6.

### Danh sách khoảng trống cần chuyển thành việc cụ thể

| Điểm mù | Nguy cơ | Bằng chứng hoặc hành động |
|---|---|---|
| Chỉ vẽ VPN, quên public cloud management endpoint | Vượt qua VPN gateway | Kiểm kê endpoint, route và SG/NACL; thử reachability từ ngoài theo ủy quyền. |
| Không đưa IAM/SSO vào mô hình | Danh tính quá quyền có thể bỏ qua giới hạn mạng | So role, nhóm quyền, chính sách truy cập và log cấp quyền. |
| Coi SIEM “đã thu đủ log” | Không thấy đường bypass hoặc phản ứng chậm | Đối chiếu nguồn dữ liệu với inventory, phát sự kiện thử và kiểm tra cảnh báo. |
| Chỉ đánh giá IPv4 | IPv6 có chính sách khác, tạo đường bất ngờ | Kiểm tra dual-stack và các luồng IPv6 hợp lệ/bị cấm. |
| Không xem Wi-Fi khách và IoT | Có khả năng di chuyển ngang từ phân đoạn không tin cậy | So VLAN, isolation và kết quả kiểm thử theo SSID/role. |
| Bỏ quên rule tạm lúc xử lý sự cố | Quyền mở rộng tồn tại không có ngày hết hạn | Rà soát change log, cơ chế expiration và owner của exception. |
| Không tính DNS và kết nối ra ngoài | Bypass kiểm soát, rò dữ liệu hoặc lệ thuộc dịch vụ ngoài | So resolver policy, egress, DNS logs và phương án khi DNS lỗi. |

Không nhất thiết mở rộng một threat model thành toàn bộ hệ sinh thái. Mỗi khoảng trống phải có **quyết định có chủ sở hữu**: điều tra ngay, chuyển sang mô hình liên quan, xác minh bằng kiểm thử hoặc chấp nhận rủi ro có căn cứ.

## 12. Minh họa cách đánh giá rủi ro tồn dư

Một đội triển khai VPN, yêu cầu MFA và chặn subnet quản trị khỏi nhóm nhân viên thông thường. Họ muốn đổi rủi ro “Tài khoản VPN bị lạm dụng để chiếm thiết bị mạng” từ **cao** thành **thấp**.

Trước khi đổi mức, cần trả lời:

1. **Control đã triển khai chưa?** Cấu hình thực tế có đúng thiết kế, áp dụng cả nhóm nhà thầu và tài khoản khẩn cấp?
2. **Có đường phụ không?** Bằng cloud console, bastion, public IP hoặc IPv6 có thể bỏ qua gateway?
3. **Control có đáp ứng kịch bản?** MFA có chống phishing, thiết bị có được quản lý, user có quyền tối thiểu?
4. **Có bằng chứng vận hành?** Reachability test và log cho thấy luồng không được phép bị chặn, sự kiện bất thường có alert?
5. **Control hỏng thì sao?** Có phân đoạn bổ sung, giám sát hoạt động admin, backup và kế hoạch khôi phục?

Một kết luận có cơ sở có thể là: “Bề mặt truy cập đã giảm; rủi ro tồn dư tạm đánh giá **trung bình**, mức tin cậy **chưa cao**, chờ kiểm thử quyền nhà thầu và xác minh log.” Cách ghi này phản ánh phần đã biết và việc phải làm.

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identified** | Đã mô tả đe dọa và hậu quả | Có kịch bản tài khoản VPN bị chiếm. |
| **Mitigated** | Có kiểm soát và bằng chứng giảm nguy cơ | ACL giới hạn quyền, MFA hiệu lực, bài kiểm thử truy cập đạt. |
| **Residual risk** | Phần nguy cơ còn lại sau kiểm soát | Tài khoản hợp lệ vẫn có thể bị chiếm hoặc lạm dụng. |
| **Not assessed** | Chưa đủ phạm vi/dữ liệu để đánh giá | Chưa xem đường quản trị ngoài VPN. |

**Not assessed không thể bị đổi thành low risk** nếu chưa có phân tích hoặc cơ sở chấp nhận rủi ro.

## 13. Giảm giới hạn bằng quy trình xác minh liên tục

Threat modeling thuộc nhóm hoạt động **phân tích và ra quyết định**; kiểm thử, kiểm toán, capture, telemetry và vận hành là **bằng chứng thực nghiệm**. Nên kết hợp theo chu trình:

~~~mermaid
flowchart LR
    A[Inventory và bối cảnh] --> B[Luồng và trust boundary]
    B --> C[Đe dọa, giả định, ưu tiên]
    C --> D[Thiết kế kiểm soát]
    D --> E[Triển khai]
    E --> F[Kiểm thử và quan sát]
    F --> G[Drift và rủi ro tồn dư]
    G --> B
~~~

### Các lớp kiểm chứng nên sử dụng

- **Cấu hình:** so sơ đồ với network inventory, route, firewall rule, security group/NACL, VPN, DNS, quyền cloud IAM và host firewall.
- **Khả năng kết nối:** kiểm thử theo ma trận *source → destination → protocol/port → IPv4/IPv6 → expected allow/deny*, trên đúng zone và danh tính được cấp quyền.
- **Giám sát:** xác minh sensor có nhìn thấy lưu lượng, alert có được phát hiện và người phụ trách có thể điều tra từ log.
- **Kịch bản khôi phục:** kiểm tra backup/restore, phụ thuộc DNS/IdP, quyền khẩn cấp và xử lý khi VPN hay firewall lỗi.
- **Vận hành:** gắn ticket và sự kiện thay đổi cấu hình với mục trong threat model; phát hiện và xử lý drift.

Kiểm thử xâm nhập, diễn tập tabletop hoặc mô phỏng hành vi tấn công có kiểm soát có thể cung cấp bằng chứng cho những kịch bản ưu tiên, trong phạm vi được phép. **Một lần kiểm thử đạt không chứng minh hệ thống an toàn cho mọi đường tấn công và mọi thời điểm**.

### Bản ghi đánh giá có thể kiểm toán

~~~yaml
# Minh họa hồ sơ threat model; không phải cấu hình thiết bị
id: NET-TM-013-01
asset: "Hệ thống quản trị hạ tầng mạng"
trust_boundary: "VPN access -> Cloud management subnet"
threat: "Tài khoản hợp lệ bị chiếm và đi ngang ngoài quyền"
assumption: "Quyền quản trị được giới hạn theo danh tính và thiết bị"
assumption_status: "needs_evidence"
candidate_controls:
  - "MFA và kiểm soát posture thiết bị"
  - "Firewall giới hạn quyền tới subnet quản trị"
  - "Ghi log và phát hiện truy cập bất thường"
validation:
  - "Đối chiếu role và rule hiệu lực"
  - "Kiểm thử reachability với user quyền thấp"
  - "Kiểm tra log và alert"
confidence: "medium"
residual_risk: "pending_validation"
owner: "Network Security + IAM"
review_trigger: "Thay đổi VPN, IAM, route hoặc firewall"
~~~

Khi thay đổi mức rủi ro, cần thể hiện **bằng chứng mới**, **ngày cập nhật** và **người ra quyết định**. Các nhãn như *needs_evidence* và *pending_validation* giúp ngăn hiểu nhầm “đề xuất” là “đã xác minh”.

### Phân công trách nhiệm

- **Chủ hệ thống:** xác định tài sản, tác động nghiệp vụ và phê duyệt ưu tiên/rủi ro tồn dư theo quy trình.
- **Chủ kiểm soát:** triển khai, duy trì và cung cấp chứng cứ control hoạt động.
- **Nhóm an ninh và kiến trúc:** dẫn dắt phân tích, chất vấn giả định, xem đường đi liên lớp.
- **SOC và vận hành:** giám sát, ghi nhận thay đổi, phát hiện ngoại lệ và báo sự cố cần cập nhật mô hình.

## 14. Ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
|---|---|
| “Đã chạy đủ STRIDE là đủ mọi nguy cơ.” | Phương pháp định hướng câu hỏi, không đóng kín danh sách đe dọa. |
| “Sơ đồ có firewall nghĩa là đã cách ly.” | Cần rule thực, route, IAM, IPv4/IPv6 và kiểm thử. |
| “Threat model đã được duyệt nghĩa là hệ thống an toàn.” | Duyệt quyết định phân tích không tự xác nhận triển khai hay kết quả vận hành. |
| “Điểm số 20/25 là xác suất chính xác.” | Thang điểm thường là tương đối và dựa trên giả định, không phải xác suất đo được. |
| “Có IDS/IPS tức là mọi hành vi tấn công đều được phát hiện.” | Sensor có thể không nhìn thấy, không giải mã được, sai cấu hình hoặc bỏ sót sự kiện. |
| “Không ghi trong tài liệu thì rủi ro thấp.” | Có thể chưa khảo sát; phải ghi là vùng chưa đánh giá. |
| “Đã pentest đạt thì không cần cập nhật.” | Môi trường, quyền, nhà cung cấp và kỹ thuật tấn công tiếp tục thay đổi. |
| “Đã có biện pháp thì rủi ro bằng không.” | Control có thể lỗi, bị vượt qua, hoặc chưa xử lý toàn bộ đường tấn công. |

## 15. Checklist rà soát một threat model mạng

- [ ] Có tài sản ưu tiên, mục tiêu bảo vệ và hậu quả nghiệp vụ được mô tả cụ thể.
- [ ] Ghi rõ ranh giới đánh giá, thành phần ngoài phạm vi, phụ thuộc và người chịu trách nhiệm.
- [ ] Tách luồng dữ liệu với đường quản trị và ranh giới tin cậy.
- [ ] Xem cả Internet, VPN, LAN/Wi-Fi, DNS, cloud, IAM, endpoint và bên thứ ba liên quan.
- [ ] Cân nhắc IPv4/IPv6, NAT, route, exception và đường đi ngoài dự kiến.
- [ ] Có danh sách giả định, chứng cứ, mức tin cậy và ngày xác minh.
- [ ] Dùng STRIDE/ATT&CK/attack tree như công cụ hỗ trợ, không coi là bảo đảm độ phủ.
- [ ] Có owner, tình trạng triển khai, kế hoạch kiểm thử và điều kiện đóng cho rủi ro ưu tiên.
- [ ] Kiểm tra độ phủ logging/IDS/IPS và khả năng khôi phục khi một control thất bại.
- [ ] Phân biệt rõ identified, mitigated, residual risk và not assessed.
- [ ] Có trigger cập nhật sau thay đổi, phiên bản mô hình và lịch rà soát theo mức quan trọng.
- [ ] Không hạ rủi ro khi chưa có bằng chứng hoặc quyết định chấp nhận rủi ro phù hợp.

## 16. Câu hỏi tự kiểm tra

**1. Nếu DFD không vẽ đường từ Internet đến database thì DB chắc chắn không thể truy cập công khai?**  
Không. Cần đối chiếu endpoint, route, rule, IAM và phép thử reachability. Sơ đồ mô tả thiết kế, không chứng minh cấu hình thực.

**2. Vì sao CVSS cao không tự đồng nghĩa với rủi ro kinh doanh cao trong mọi hệ thống?**  
Vì mức phơi nhiễm, khả năng tiếp cận, biện pháp hiện hữu, dữ liệu liên quan và tác động nghiệp vụ đều phụ thuộc ngữ cảnh.

**3. MFA đã triển khai thì rủi ro tài khoản VPN bị chiếm đã được loại bỏ chưa?**  
Chưa. Cần xét phương thức MFA, thiết bị, token phiên, đường truy cập ngoại lệ, phân đoạn quyền và khả năng giám sát hành vi.

**4. Khi cloud rule khác với threat model, xử lý thế nào?**  
Xác minh chênh lệch, đánh giá ảnh hưởng, sửa cấu hình hoặc cập nhật mô hình theo quyết định hợp lệ và kiểm thử lại. Không ưu tiên sơ đồ cũ hơn bằng chứng hệ thống thật.

**5. Nếu một kỹ thuật tấn công không có trong checklist, có thể bỏ qua?**  
Không. Xem tài sản và mục tiêu của đối thủ, bổ sung kịch bản nếu có liên quan, đánh giá rủi ro và cập nhật khả năng phát hiện.

## 17. Tài liệu tham khảo

- [OWASP Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html): cách tiếp cận mô hình hóa và chu trình đánh giá.
- [NIST SP 800-30 Rev. 1 — Guide for Conducting Risk Assessments](https://csrc.nist.gov/pubs/sp/800/30/r1/final): nguyên tắc phân tích rủi ro, giả định và sự bất định.
- [NIST Cybersecurity Framework 2.0](https://www.nist.gov/cyberframework): quản trị rủi ro, bảo vệ, phát hiện, ứng phó và khôi phục.
- [MITRE ATT&CK](https://attack.mitre.org/): cơ sở tri thức hành vi đối thủ để phân tích và xây dựng phạm vi giám sát.
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/): minh họa cách chuyển yêu cầu thành tiêu chí kiểm chứng ở lớp ứng dụng.

**Ghi nhớ:** Threat model là **bản đồ hỗ trợ quyết định trong điều kiện thông tin không đầy đủ**. Mô hình có giá trị khi ghi rõ phạm vi và giả định, liên hệ được với bằng chứng cấu hình, thừa nhận rủi ro tồn dư và được cập nhật khi hạ tầng hoặc cách thức tấn công thay đổi.
