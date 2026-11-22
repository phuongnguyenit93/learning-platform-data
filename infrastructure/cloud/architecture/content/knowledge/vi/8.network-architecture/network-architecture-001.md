# Quy hoạch không gian địa chỉ và tránh chồng lấn mạng

Trong thiết kế kiến trúc ứng dụng trên đám mây (**Cloud Architecture**), một lựa chọn tưởng như đơn giản — cấp dải địa chỉ IP cho mạng mới — có thể quyết định hệ thống có kết nối được với trung tâm dữ liệu, chi nhánh, đối tác, cụm Kubernetes hay vùng khôi phục thảm họa trong tương lai hay không. Nếu hai mạng cần trao đổi trực tiếp nhưng cùng sử dụng một dải địa chỉ, định tuyến không còn đủ thông tin để xác định đích chính xác. Kết quả có thể là lỗi kết nối khó tìm, yêu cầu đổi địa chỉ hàng loạt hoặc phải đưa NAT/proxy vào những nơi không cần thiết.

Bài học thuộc chương **Kiến trúc mạng**, tập trung vào **quy hoạch không gian địa chỉ (IP address planning)** và **tránh chồng lấn mạng (overlapping networks)**. Kiến trúc sư cần chuyển yêu cầu nghiệp vụ về kết nối, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành thành một kế hoạch địa chỉ có thể kiểm tra, cấp phát và phát triển theo thời gian. Những đánh đổi này cũng là một phần thiết thực của đánh giá kiến trúc theo tư duy **Well-Architected**.

Sau bài học, bạn có thể:

- Đọc và tính địa chỉ mạng từ ký hiệu CIDR, xác định dung lượng và phạm vi của subnet IPv4/IPv6.
- Xác định ranh giới định tuyến giữa cloud, hệ thống tại chỗ, chi nhánh, cụm container và đối tác.
- Xây dựng sơ đồ phân cấp CIDR có chỗ cho mở rộng, đa vùng và môi trường dự phòng.
- Nhận biết chồng lấn địa chỉ, lỗi định tuyến, nhầm lẫn DNS và những trường hợp NAT chỉ là giải pháp chuyển tiếp.
- Thiết lập quy trình **IP Address Management (IPAM)**, kiểm tra tự động và quy tắc thay đổi để giữ kế hoạch địa chỉ nhất quán.
- Chứng minh quyết định phân bổ địa chỉ bằng ma trận rủi ro, đo lường lưu lượng, kiểm thử kết nối và tài liệu kiến trúc.

## 1. Tại sao quy hoạch địa chỉ là yêu cầu kiến trúc?

Hãy hình dung một doanh nghiệp có hệ thống kế toán tại trung tâm dữ liệu, ứng dụng khách hàng ở cloud và hàng chục chi nhánh. Mỗi nhóm tự chọn dải 10.0.0.0/16 hoặc 192.168.1.0/24 vì đó là địa chỉ riêng, sau đó doanh nghiệp muốn kết nối chúng qua VPN và một mạng trung chuyển chung.

Việc trùng dải có thể chưa gây vấn đề khi các mạng hoàn toàn cô lập. Khi cần định tuyến giữa các mạng, cùng một địa chỉ đích có thể chỉ hai thiết bị khác nhau. Một route ở mạng nguồn không thể biết địa chỉ 192.168.1.10 đang chỉ máy chủ ở chi nhánh A hay chi nhánh B nếu không có cơ chế phân biệt bổ sung.

**Hệ quả thường gặp:**

- Không thể thiết lập một số kết nối peering hoặc transit do chính sách không cho phép CIDR chồng lấn.
- Route bị ưu tiên sai, lưu lượng đi về nhầm địa điểm hoặc bị blackhole.
- Dịch vụ dùng địa chỉ trong network overlay/container bị xung đột với mạng ngoài.
- DNS trả về địa chỉ có vẻ hợp lệ nhưng đích thực tế nằm trong mạng khác.
- Di chuyển workload sang cloud hoặc kết nối đối tác trở nên tốn kém.
- Hệ thống phải dùng NAT, proxy hoặc tách VRF kéo theo chi phí vận hành và khó kiểm toán lưu lượng.

Quy hoạch tốt cần dự đoán **những mạng sẽ phải trao đổi với nhau trong 2–5 năm tới**, kể cả các mạng chưa xây dựng ngay. Nó không đòi hỏi đoán chính xác mọi workload, nhưng phải có cơ chế cấp phát và dự trữ đủ linh hoạt để tránh quyết định địa chỉ ngẫu hứng.

## 2. Nền tảng IPv4 và CIDR

Địa chỉ IPv4 gồm 32 bit, thường được viết thành bốn số thập phân như 10.64.16.25. Ký hiệu **CIDR (Classless Inter-Domain Routing)** gồm địa chỉ mạng và độ dài tiền tố, ví dụ **10.64.16.0/20**. Số 20 cho biết 20 bit đầu nhận diện tiền tố mạng, còn 12 bit còn lại dành cho địa chỉ trong phạm vi đó.

Với tiền tố IPv4 **/p**, tổng số địa chỉ là:

**Số địa chỉ = 2^(32 − p).**

Nếu chia một mạng **/p** thành các mạng con **/q** với q lớn hơn p, số mạng con bằng:

**Số mạng con = 2^(q − p).**

### 2.1. Bảng CIDR thường dùng

| CIDR | Số địa chỉ IPv4 trong dải | Cách dùng tham khảo |
| --- | ---: | --- |
| /16 | 65.536 | Khối địa chỉ của một VPC/VNet lớn hoặc phạm vi được giao cho một đơn vị |
| /18 | 16.384 | Phân đoạn lớn cần dung lượng dự phòng |
| /20 | 4.096 | Subnet ứng dụng hoặc nhóm workload lớn |
| /21 | 2.048 | Subnet ứng dụng quy mô vừa |
| /22 | 1.024 | Phân đoạn dữ liệu hoặc dịch vụ trung gian |
| /24 | 256 | Subnet có nhu cầu địa chỉ nhỏ hơn |
| /26 | 64 | Đoạn mạng nhỏ, nếu nhà cung cấp hỗ trợ |
| /28 | 16 | Subnet rất nhỏ, phải kiểm tra hạn mức và địa chỉ dự trữ |

**Lưu ý:** đây là tổng số địa chỉ trong dải, **không phải số IP mà tài nguyên thực tế có thể sử dụng**. Nhiều nền tảng đám mây giữ lại một số IP trong mỗi subnet cho địa chỉ mạng, router, DNS hoặc mục đích hệ thống. Một số loại subnet có kích thước tối thiểu. Quy tắc và số lượng địa chỉ dùng được phải kiểm tra theo dịch vụ và nhà cung cấp cụ thể.

### 2.2. Tự tính phạm vi của một CIDR

Với **10.64.16.0/20**:

- /20 tương ứng subnet mask **255.255.240.0**.
- Phần octet thứ ba có bước nhảy **16**: ... 0, 16, 32, 48, 64...
- Dải chứa các địa chỉ từ **10.64.16.0** đến **10.64.31.255**.
- Tổng dung lượng là **2^12 = 4.096 địa chỉ**.
- **10.64.17.8** nằm trong dải này; **10.64.32.8** không nằm trong dải.
- CIDR **10.64.17.0/24** nằm hoàn toàn bên trong **10.64.16.0/20**.

Khi ghi một CIDR vào IPAM, hãy dùng **địa chỉ mạng đã chuẩn hóa**, chẳng hạn 10.64.16.0/20. Một giá trị như 10.64.17.8/20 có thể được một số công cụ hiểu là host thuộc mạng 10.64.16.0/20; nếu dùng nguyên chuỗi để so sánh sẽ dễ bỏ sót xung đột. Các công cụ kiểm tra phải chuẩn hóa network address trước.

### 2.3. Địa chỉ riêng và những khoảng dễ nhầm

Ba dải IPv4 riêng thông dụng theo RFC 1918:

| Dải | Phạm vi | Số địa chỉ tổng cộng |
| --- | --- | ---: |
| 10.0.0.0/8 | 10.0.0.0 – 10.255.255.255 | 16.777.216 |
| 172.16.0.0/12 | 172.16.0.0 – 172.31.255.255 | 1.048.576 |
| 192.168.0.0/16 | 192.168.0.0 – 192.168.255.255 | 65.536 |

Không phải mọi địa chỉ bắt đầu bằng **172.** hoặc **192.** đều là private IP. Chỉ các dải được chỉ định mới thuộc RFC 1918.

**100.64.0.0/10** là khoảng **Shared Address Space**, thường liên quan CGNAT; không nên tùy tiện coi đó là dải địa chỉ riêng doanh nghiệp tương đương RFC 1918. Các vùng link-local, loopback, multicast hoặc các khoảng được dành riêng cho mục đích khác cũng không được lấy làm pool địa chỉ thông thường.

Đối với ví dụ tài liệu và kiểm thử, có những dải được dành cho minh họa, như 192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24. Chúng không phải dải để một doanh nghiệp tự dùng làm địa chỉ public thực tế.

## 3. IPv6 phải được tính từ đầu

IPv6 có không gian địa chỉ 128 bit. Một số bài toán thiếu IPv4, kết nối diện rộng hoặc thiết bị lớn có thể được cải thiện khi hỗ trợ IPv6, nhưng việc triển khai dual-stack cũng tạo thêm yêu cầu về bảo mật, DNS, định tuyến và quan sát.

Những khái niệm cần nhớ:

- **IPv6 Global Unicast:** địa chỉ dùng cho kết nối IPv6 theo tiền tố được cấp/phê duyệt. Không tự chọn một tiền tố bất kỳ rồi cho rằng đã có quyền định tuyến toàn cầu.
- **Unique Local Address (ULA):** thuộc fc00::/7; trong thực hành cấp phát tại chỗ thường dùng tiền tố được tạo theo cơ chế locally assigned ở **fd00::/8**. ULA không mặc định được định tuyến trên Internet công cộng.
- **Link-local:** fe80::/10, dùng trong phạm vi liên kết và không phải địa chỉ để quy hoạch route liên vùng.
- **/64 subnet:** kích thước subnet IPv6 thường gặp trong mạng LAN và nhiều nền tảng cloud; cần tuân theo hạn mức/cách cấp phát của môi trường thực tế.
- **/48 hoặc /56:** có thể dùng làm khối được phân bổ cho một tổ chức, địa điểm hoặc mạng, nhưng cách cấp quyền phụ thuộc ISP và nhà cung cấp.

Ví dụ minh họa về ULA nội bộ, với tiền tố giả định **fd7a:1c2e:4f90::/48**:

| Phạm vi | IPv6 prefix ví dụ | Ghi chú |
| --- | --- | --- |
| Khối ULA của tổ chức | fd7a:1c2e:4f90::/48 | Một prefix chỉ để minh họa; triển khai thật cần quy trình tạo Global ID phù hợp và kiểm tra trùng |
| Mạng ứng dụng vùng A | fd7a:1c2e:4f90:10::/64 | Phân đoạn logic ở vùng A |
| Mạng dữ liệu vùng A | fd7a:1c2e:4f90:20::/64 | Phân đoạn logic khác |
| Mạng ứng dụng vùng B | fd7a:1c2e:4f90:110::/64 | Phân đoạn vùng B |

Từ một khối /48 có **2^16 = 65.536 mạng con /64** theo phép chia tiền tố. Không nên vì vậy bỏ qua cấu trúc phân vùng, quản trị cấp phát hoặc những giới hạn IPv6 của từng dịch vụ.

**Chuyển sang IPv6 không tự chữa mọi vấn đề.** Hai mạng cùng chọn một ULA prefix vẫn có thể chồng lấn. Dual-stack đòi hỏi kiểm tra cả địa chỉ IPv4 và IPv6, quy tắc firewall, DNS A/AAAA, NAT hoặc cơ chế truy cập tương ứng. Một thiết kế “IPv6 public, IPv4 private” cũng có bề mặt truy cập khác nhau cần đánh giá riêng.

## 4. Chồng lấn địa chỉ xảy ra khi nào?

Hai CIDR **overlap** nếu chúng có ít nhất một địa chỉ chung. Với hai mạng IPv4 hoặc IPv6 cùng họ địa chỉ, có thể kiểm tra bằng cách so sánh khoảng đầu–cuối đã chuẩn hóa, hoặc sử dụng thư viện xử lý CIDR.

Ví dụ:

| Mạng A | Mạng B | Chồng lấn? | Giải thích |
| --- | --- | --- | --- |
| 10.64.0.0/16 | 10.65.0.0/16 | Không | Hai mạng /16 khác nhau |
| 10.64.16.0/20 | 10.64.32.0/20 | Không | Phạm vi 16–31 và 32–47 ở octet thứ ba |
| 10.64.16.0/20 | 10.64.17.0/24 | Có | /24 nằm bên trong /20 |
| 192.168.1.0/24 | 192.168.1.128/25 | Có | /25 là một nửa của /24 |
| 10.64.0.0/17 | 10.64.128.0/17 | Không | Hai nửa của 10.64.0.0/16 |
| 10.64.0.0/16 | 10.64.0.0/17 | Có | /17 nằm trong /16 |

**Phân biệt “overlap” về tập địa chỉ với “xung đột cần xử lý”:** một pool cha 10.64.0.0/16 chứa các subnet con là điều **có chủ đích**. Chỉ khi hai **cấp phát đồng cấp** hoặc hai miền mạng cần định tuyến trực tiếp cùng sử dụng địa chỉ trùng nhau mà không có cơ chế phân tách mới là xung đột kiến trúc.

### 4.1. Tình huống hybrid cloud

Giả sử trung tâm dữ liệu hiện dùng **10.64.16.0/20**, nhóm cloud độc lập lại tạo VPC **10.64.0.0/16**. Khi kết nối qua VPN/đường truyền riêng:

- Dải của trung tâm dữ liệu đã nằm hoàn toàn trong VPC cloud.
- Route tới 10.64.16.25 có thể bị xác định là đường cục bộ trong VPC hoặc đi sai hướng theo bảng định tuyến.
- Một số nền tảng có thể từ chối kết nối mạng do chính sách không hỗ trợ CIDR trùng.
- Ứng dụng có thể dùng đúng DNS và đúng port nhưng vẫn không chạm được đích vì tuyến đường hoặc địa chỉ bị nhập nhằng.

Vấn đề **không tự biến mất** khi tăng băng thông VPN, thêm subnet hoặc tạo thêm DNS record. Cần giải quyết ranh giới địa chỉ hoặc dùng một giải pháp trung gian được thiết kế rõ.

### 4.2. Tại sao “longest prefix match” không cứu được mọi tình huống?

Router IP thường chọn route có prefix cụ thể nhất trong những route khớp. Ví dụ, nếu có route tới **10.64.0.0/16** và **10.64.16.0/20**, lưu lượng tới 10.64.20.9 phù hợp cả hai và thường đi theo route **/20**.

Điều này chỉ cho biết **quy tắc chọn đường**, không chứng minh người dùng đang tới đúng hệ thống. Nếu đích 10.64.20.9 tồn tại đồng thời tại hai miền, tuyến được chọn không chứa thêm thông tin để phân biệt hai máy. Route cục bộ, route đặc biệt hoặc hành vi nhà cung cấp còn có các ưu tiên và ràng buộc riêng.

## 5. Quy hoạch dựa trên phạm vi kết nối

Trước khi tính subnet mask, cần lập bản đồ **miền định tuyến (routing domains)** và nhu cầu kết nối.

### 5.1. Tập hợp các nguồn cần kiểm kê

- Mạng văn phòng, trụ sở, trung tâm dữ liệu và chi nhánh.
- VPC/VNet trên từng tài khoản, dự án, môi trường, region và nhà cung cấp cloud.
- Mạng máy ảo, container, Pod CIDR, Service CIDR và mạng overlay của các cụm Kubernetes.
- Mạng kết nối qua VPN, đường truyền riêng, SD-WAN, peering hoặc transit hub.
- Địa chỉ do đối tác sử dụng khi thiết lập private connectivity.
- Mạng quản trị, mạng backup, giám sát, thiết bị IoT/OT hoặc mạng ứng dụng kế thừa.
- Dải của các giải pháp bảo mật, kết nối điều khiển, client VPN, VDI hoặc máy phát triển nếu cần truy cập tài nguyên nội bộ.
- IPv6 prefixes, ULA và các subnet dual-stack đang hoặc sẽ được sử dụng.

Nếu một dải chưa rõ chủ sở hữu, đừng tự đánh dấu là “rảnh”. Cần thu thập từ router, firewall, IPAM, cloud account, cấu hình cụm và nhóm vận hành có trách nhiệm.

### 5.2. Ma trận nhu cầu kết nối

| Nguồn | Đích | Cần định tuyến trực tiếp? | Tác động tới quy hoạch |
| --- | --- | --- | --- |
| Ứng dụng cloud production | Database private cùng VPC/VNet | Có, trong ranh giới cho phép | Subnet và security rules rõ |
| Cloud production | Trung tâm dữ liệu kế thừa | Có, qua VPN/đường riêng | Không chồng lấn CIDR, route hai chiều và DNS |
| Cloud region A | Cloud region B | Có thể, cho DR hoặc replication | Cần dải địa chỉ tương thích và ranh giới truy cập |
| Cloud production | Cloud staging | Thường hạn chế hoặc không | Tách môi trường; không mặc định cần full-mesh |
| Ứng dụng cloud | SaaS qua HTTPS công khai | Không nhất thiết cần mạng riêng | Có thể giao tiếp qua endpoint public, policy và DNS |
| Cụm Kubernetes A | Cụm Kubernetes B | Phụ thuộc ứng dụng | Nếu cần Pod-to-Pod hoặc Service-to-Service theo IP, CIDR phải tương thích |
| Mạng cloud | Đối tác qua private link/VPN | Phụ thuộc hợp đồng | Kiểm tra dải đối tác trước khi cấp phát |

**Câu hỏi then chốt:** hai mạng nào có khả năng cần trao đổi trực tiếp trong tương lai? Các mạng hoàn toàn cô lập có thể sử dụng địa chỉ trùng mà vẫn hoạt động, nhưng nếu kế hoạch sáp nhập, kết nối hoặc chia sẻ dịch vụ thay đổi, việc trùng địa chỉ sẽ biến thành nợ kỹ thuật.

### 5.3. Quy hoạch theo phạm vi tổng thể trước, chi tiết sau

Một chiến lược hay dùng:

1. Chọn hoặc xác nhận **address pool** thuộc quyền tổ chức quản lý.
2. Giao các **khối CIDR lớn** cho loại hạ tầng/đơn vị hoặc vùng vận hành.
3. Từ các khối đó phân chia tiếp theo **region, môi trường và mục đích mạng**.
4. Từ từng VPC/VNet, dành subnet theo **availability zone, chức năng và tăng trưởng**.
5. Ghi **dải dự trữ** chưa cấp phát để mở rộng hoặc xử lý thay đổi.
6. Kiểm tra overlap ở **mọi cấp thực thi và định tuyến**, có xét quan hệ cha–con hợp lệ.

Không phải mọi tổ chức đều nên chia trước theo vùng địa lý. Một tổ chức đa cloud có thể cần phân trước theo nhà cung cấp hoặc môi trường; doanh nghiệp có nhiều chi nhánh có thể ưu tiên tổng hợp route theo địa điểm. Chọn phân cấp phản ánh **cách kết nối, cách quản trị và khả năng tổng hợp route**.

## 6. Ví dụ quy hoạch địa chỉ cho hệ thống nhiều vùng

Giả sử doanh nghiệp xây nền tảng thuê thiết bị với cloud production ở hai vùng, một môi trường staging, trung tâm dữ liệu kế thừa và nhiều chi nhánh. Mục tiêu là kết nối private qua mạng trung chuyển khi cần, nhưng vẫn giữ ranh giới môi trường.

Tổ chức chọn khối **10.64.0.0/10** để lập kế hoạch nội bộ. Dải này trải từ **10.64.0.0** đến **10.127.255.255** và chứa **64 khối /16**. Đây là ví dụ; trong dự án thực tế phải kiểm tra xem khối này có đang được sử dụng ở bất kỳ nơi nào kết nối hiện tại hoặc tương lai hay không.

### 6.1. Phân bổ các khối lớn

| Phạm vi | CIDR được dành | Vai trò |
| --- | --- | --- |
| Production, cloud region A | 10.64.0.0/16 | VPC/VNet ứng dụng chính |
| Production, cloud region B | 10.65.0.0/16 | VPC/VNet vùng thứ hai |
| Staging, cloud region A | 10.66.0.0/16 | Môi trường thử nghiệm |
| Trung tâm dữ liệu kế thừa | 10.96.0.0/16 | Mạng tại chỗ cần kết nối |
| Nhóm chi nhánh | 10.97.0.0/16 | Pool để chia cho từng địa điểm |
| Kubernetes cluster A — Pods | 10.112.0.0/16 | Pool Pod theo thiết kế CNI |
| Kubernetes cluster A — Services | 10.113.0.0/16 | Pool địa chỉ dịch vụ của cluster |
| Kubernetes cluster B — Pods | 10.114.0.0/16 | Pool Pod riêng |
| Kubernetes cluster B — Services | 10.115.0.0/16 | Pool Service riêng |
| Các khối chưa cấp phát | Phần còn lại của 10.64.0.0/10 | Cần ghi trạng thái dự trữ và chính sách cấp phát |

Các CIDR trên **không overlap với nhau**. Việc dùng /16 cho Pod hoặc Service chỉ để minh họa phân vùng; thực tế phải kiểm tra cách hoạt động của CNI, số node/pod, loại network, route và giới hạn của nền tảng. Service CIDR của Kubernetes có thể dùng địa chỉ ảo không được định tuyến trực tiếp ra ngoài, nhưng vẫn cần được kiểm kê để tránh xung đột tại lớp ứng dụng, DNS và các giải pháp kết nối cụm.

### 6.2. Sơ đồ định tuyến cấp cao

~~~mermaid
flowchart TB
    BR["Chi nhánh\n10.97.0.0/16"] --> HUB["Transit / WAN hub\náp dụng route và chính sách"]
    DC["Data center\n10.96.0.0/16"] --> HUB
    HUB --> PA["Cloud production A\n10.64.0.0/16"]
    HUB --> PB["Cloud production B\n10.65.0.0/16"]
    HUB -. "Kết nối có giới hạn" .-> ST["Cloud staging\n10.66.0.0/16"]
    PA --- K8A["Cluster A\nPod: 10.112.0.0/16\nService: 10.113.0.0/16"]
    PB --- K8B["Cluster B\nPod: 10.114.0.0/16\nService: 10.115.0.0/16"]
~~~

Sơ đồ chỉ là mô hình logic, **không hàm ý Pod CIDR hoặc Service CIDR tự động được quảng bá qua transit**. Trong triển khai thật, cần xét CNI, NAT, route advertisement, DNS, network policy và việc ứng dụng có thực sự cần kết nối bằng địa chỉ Pod/Service hay không.

### 6.3. Chia subnet cho production region A

Bên trong VPC/VNet **10.64.0.0/16**, giả sử dùng ba availability zone A, B và C:

| Chức năng | AZ A | AZ B | AZ C | Dung lượng mỗi subnet |
| --- | --- | --- | --- | ---: |
| Subnet public/ingress | 10.64.0.0/24 | 10.64.1.0/24 | 10.64.2.0/24 | 256 IP |
| Subnet private ứng dụng | 10.64.16.0/20 | 10.64.32.0/20 | 10.64.48.0/20 | 4.096 IP |
| Subnet private dữ liệu | 10.64.64.0/22 | 10.64.68.0/22 | 10.64.72.0/22 | 1.024 IP |
| Subnet endpoint/dịch vụ mạng | 10.64.80.0/24 | 10.64.81.0/24 | 10.64.82.0/24 | 256 IP |

Các subnet được cấp ở trên không trùng nhau. **Dải dự trữ chung, chưa gán cho AZ nào:** 10.64.96.0/19, bao phủ từ 10.64.96.0 đến 10.64.127.255 (8.192 IP tổng). Dải này chưa được dùng như một subnet đang hoạt động. Phần còn lại của /16 cũng chưa cấp phát và cần được đánh dấu rõ trong IPAM.

**Lưu ý quan trọng:** một “public subnet” không trở nên public chỉ vì CIDR thuộc một khoảng cụ thể. Tính public/private phụ thuộc route tới Internet gateway, cơ chế địa chỉ public, firewall, load balancer và chính sách truy cập. Cả subnet public lẫn private trong ví dụ đều dùng **địa chỉ RFC 1918**.

### 6.4. Cân bằng dung lượng và khả năng mở rộng

Giả sử một AZ dự kiến cần tối đa khoảng **1.200 địa chỉ IP** cho VM, node, Pod IP nếu mô hình mạng tiêu thụ IP của VPC, các node dự phòng và thời gian rolling deployment. Một subnet **/21** có tổng 2.048 địa chỉ, có thể đủ ở mức tính toán ban đầu; chọn **/20** cho phép 4.096 địa chỉ và chừa thêm chỗ cho tăng trưởng. Quyết định cuối cùng phải tính địa chỉ dự trữ của nhà cung cấp, cấu hình mạng của container, autoscaling và giới hạn quota.

Đừng chia mọi subnet bằng /24 theo thói quen. Ngược lại, cũng không nên luôn cấp /16 cho một workload nhỏ chỉ để “khỏi phải nghĩ”: cách dùng quá rộng gây lãng phí không gian IPv4 riêng, tăng quy mô định tuyến và có thể cản trở các hệ thống khác khi cần kết nối sau này.

## 7. Kiểm tra bằng phép tính và quy tắc máy đọc được

Thực tế nên dùng công cụ IPAM hoặc thư viện xử lý CIDR để tránh lỗi tính nhẩm. Mã giả thể hiện logic kiểm tra cơ bản:

~~~text
function validateAllocation(candidate, allocatedNetworks, delegatedParent):
    candidate = normalizeCIDR(candidate)

    assert candidate is inside delegatedParent
    assert candidate is aligned to its prefix
    assert candidate.prefixLength meets platform constraints

    for existing in allocatedNetworks:
        if existing is an intentionally delegated parent of candidate:
            continue

        if candidate overlaps existing:
            reject("CIDR overlaps an existing allocation")

    reserve candidate atomically in IPAM
    record owner, environment, region, purpose and approval
~~~

**Không so sánh chỉ bằng chuỗi:** 10.64.16.0/20 và 10.64.17.0/24 khác nhau về ký tự nhưng vẫn overlap. Cần so sánh khoảng mạng đã chuẩn hóa.

Cũng không thể áp dụng quy tắc “mọi CIDR có giao nhau đều sai” cho tất cả bản ghi IPAM, vì pool cha chứa các subnet con là **quan hệ phân cấp hợp lệ**. Công cụ phải phân biệt rõ **container/pool/reservation**, **subnet thực thi** và **quan hệ cấp phát giữa các miền định tuyến**.

### 7.1. Ví dụ kiểm tra CIDR với Python chuẩn

Đoạn mã dưới đây sử dụng **thư viện chuẩn ipaddress** để minh họa phép overlap; không phụ thuộc nhà cung cấp cloud:

~~~python
from ipaddress import ip_network

def overlap(a: str, b: str) -> bool:
    left = ip_network(a, strict=True)
    right = ip_network(b, strict=True)
    if left.version != right.version:
        return False
    return left.overlaps(right)

assert overlap("10.64.16.0/20", "10.64.17.0/24")
assert not overlap("10.64.16.0/20", "10.64.32.0/20")
assert not overlap("10.64.0.0/16", "10.65.0.0/16")
~~~

**strict=True** giúp phát hiện giá trị có host bit khác 0, như 10.64.17.8/20, thay vì âm thầm chuẩn hóa. Trong quy trình doanh nghiệp, ngoài phép toán CIDR còn phải đối chiếu **routing domain, quyền sử dụng, trạng thái dự trữ, vùng và kết nối trong tương lai**.

### 7.2. Biểu diễn địa chỉ có thể tái lập bằng IaC

Một số công cụ Infrastructure as Code có hàm chia subnet theo CIDR. Ví dụ với cú pháp **Terraform**:

~~~hcl
locals {
  vpc_cidr     = "10.64.0.0/16"
  app_az_a     = cidrsubnet(local.vpc_cidr, 4, 1) # 10.64.16.0/20
  app_az_b     = cidrsubnet(local.vpc_cidr, 4, 2) # 10.64.32.0/20
  app_az_c     = cidrsubnet(local.vpc_cidr, 4, 3) # 10.64.48.0/20
}
~~~

**newbits=4** biến prefix /16 thành /20; **netnum** chọn subnet con bắt đầu từ 0. Ví dụ giúp tái lập phân chia địa chỉ, nhưng tự nó không ngăn hai project IaC độc lập cùng chọn một netnum. IPAM hoặc quy trình cấp phát trung tâm vẫn phải là nguồn kiểm soát trước khi áp dụng vào hạ tầng.

### 7.3. Phân biệt kiểm tra tĩnh và kiểm tra thực tế

| Lớp kiểm tra | Phát hiện điều gì? | Giới hạn |
| --- | --- | --- |
| Kiểm tra nội dung YAML/IaC | CIDR không hợp lệ, overlap trong danh mục, cấu trúc cấp phát sai | Không nhìn thấy tài nguyên tạo thủ công hoặc môi trường ngoài danh mục |
| Kiểm tra trạng thái cloud | CIDR VPC/VNet, subnet, route table, attachments thực tế | Có thể không biết mạng đối tác chưa kết nối hoặc kế hoạch tương lai |
| Kiểm tra router/BGP/VPN | Route đang nhận/quảng bá và phạm vi reachable | Không tự chứng minh đúng nghiệp vụ hoặc đúng chủ sở hữu |
| Kiểm thử kết nối | Đường đi, DNS, firewall, ứng dụng truy cập được đích thật | Chỉ kiểm tra các trường hợp được thực hiện; cần thử hai chiều và khi lỗi |

Một kế hoạch địa chỉ được duyệt cần kết hợp **danh mục dự kiến (desired state)** với **kiểm kê thực tế (observed state)**. Sự chênh lệch giữa hai phần là drift cần điều tra.

## 8. IPAM: quản lý địa chỉ như tài nguyên có vòng đời

**IP Address Management (IPAM)** là tập quy trình và công cụ quản lý pool, subnet, cấp phát, chủ sở hữu, trạng thái và lịch sử thay đổi địa chỉ. Nó có thể là dịch vụ chuyên dụng, công cụ hạ tầng tích hợp hoặc hệ thống dữ liệu nội bộ có kiểm soát; một bảng tính không có cơ chế giữ chỗ đồng thời sẽ dễ phát sinh hai nhóm cùng dùng một CIDR.

### 8.1. Metadata tối thiểu của một cấp phát

| Trường | Mục đích |
| --- | --- |
| CIDR chuẩn hóa và họ IP | Xác định phạm vi IPv4/IPv6 chính xác |
| Pool cha / routing domain | Kiểm tra quyền cấp phát và mức xung đột cần kiểm tra |
| Trạng thái | Planned, reserved, allocated, in-use, deprecated, released |
| Chủ sở hữu và liên hệ | Người/nhóm phê duyệt và xử lý sự cố |
| Dự án, tài khoản, môi trường | Liên kết tài nguyên mạng với trách nhiệm thực tế |
| Region, AZ, site | Biết địa chỉ nằm ở đâu và có thể kết nối với những nơi nào |
| Chức năng | Ingress, application, database, Pod, service, management... |
| Nhu cầu hiện tại và dự báo | Chọn prefix phù hợp và thời điểm cần mở rộng |
| Hệ thống liên quan | VPC/VNet, cluster, transit, VPN, router, route advertisement |
| Ngày cấp phát, phê duyệt, lịch sử | Kiểm toán và quản lý thay đổi |
| Dữ liệu IPv6 tương ứng | Tránh chỉ theo dõi IPv4 khi dịch vụ đã dual-stack |

Ví dụ bản ghi IPAM minh họa:

~~~yaml
allocation_id: net-prod-a-app-az1
cidr: 10.64.16.0/20
ip_family: ipv4
parent_pool: 10.64.0.0/16
routing_domain: production-a
account: cloud-production
region: region-a
availability_zone: az-a
purpose: private_application
owner: platform_network_team
state: allocated
planned_peak_ips: 1200
growth_headroom_policy: approved_capacity_plan
connected_domains:
  - production-transit
change_reference: CHG-EXAMPLE-001
~~~

Các tên region/AZ, ID thay đổi và chính sách là ví dụ, không phải cấu hình nhà cung cấp. Trong thực tế, cần xác định **quy tắc cấp phát đồng thời**: hai yêu cầu đến cùng lúc không được lấy cùng subnet chỉ vì cùng nhìn thấy trạng thái available.

### 8.2. Vòng đời địa chỉ

~~~mermaid
flowchart LR
    A["Thiết kế nhu cầu"] --> B["Kiểm tra pool và routing domain"]
    B --> C{"Có CIDR không chồng lấn?"}
    C -- "Không" --> D["Chọn khối khác / điều chỉnh nhu cầu"]
    D --> B
    C -- "Có" --> E["Reserve atomically trong IPAM"]
    E --> F["Review và phê duyệt"]
    F --> G["Triển khai qua IaC"]
    G --> H["Đối chiếu trạng thái thực tế"]
    H --> I["Vận hành và theo dõi dung lượng"]
    I --> J["Thu hồi khi ngừng dùng"]
    J --> K["Xác nhận không còn route / tài nguyên / phụ thuộc"]
    K --> L["Release sau thời gian kiểm soát"]
~~~

Không nên tái sử dụng một subnet ngay sau khi xóa VPC nếu hệ thống DNS, route, firewall, log, backup hoặc đối tác vẫn còn tham chiếu cũ. Thu hồi địa chỉ cần có **bước kiểm tra phụ thuộc** và khoảng bảo vệ nếu chính sách yêu cầu.

## 9. Quy hoạch route và tổng hợp tiền tố

CIDR là đầu vào cho **routing**, nhưng một kế hoạch địa chỉ hợp lệ về toán học chưa chắc tạo ra một kiến trúc mạng đúng. Cần thiết kế bảng route, điểm kết nối và quyền quảng bá các prefix.

### 9.1. Route summarization

Nếu mọi subnet trong cloud production A đều nằm dưới **10.64.0.0/16** và cùng đi qua một ranh giới transit phù hợp, có thể quảng bá một route tổng hợp 10.64.0.0/16 thay vì hàng chục /20, /22, /24. Điều này đơn giản hóa bảng route và thay đổi.

Nhưng tóm tắt route chỉ an toàn khi **đích, quyền quản lý và khả năng reachable của cả khối thống nhất**. Nếu một phần 10.64.0.0/16 nằm ở nơi khác hoặc chưa có route chi tiết phù hợp, quảng bá /16 có thể làm traffic đi nhầm, gây blackhole hoặc vô tình mở phạm vi kết nối lớn hơn dự kiến.

### 9.2. Định tuyến phải nhất quán hai chiều

Đường từ ứng dụng cloud đến máy tại chỗ có thể hoạt động ở chiều đi nhưng phản hồi bị mất vì router tại chỗ không có route trở lại subnet ứng dụng hoặc firewall stateful chặn đường về.

Với một luồng kết nối cụ thể, cần xác minh:

1. DNS trên phía nguồn trả địa chỉ thuộc miền đích mong muốn.
2. Route ở phía nguồn đưa lưu lượng tới đúng VPN/transit/peering/egress.
3. Các hop trung gian chấp nhận quảng bá prefix và không có route che khuất ngoài ý muốn.
4. Firewall/security group/network policy cho phép đúng giao thức và đối tượng.
5. Đích có route phản hồi đúng, kể cả khi có NAT.
6. Kết nối ứng dụng hoạt động với thời gian đáp ứng và tiêu chí bảo mật được yêu cầu.

Khi có nhiều đường WAN hoặc đường dự phòng, còn phải thử **route failover**, hành vi BGP hoặc routing policy liên quan, và việc khôi phục không làm xuất hiện đường đi bất đối xứng không phù hợp với firewall.

### 9.3. Tách mạng và quyền truy cập là hai bài toán khác nhau

Hai ứng dụng có subnet riêng **không tự bảo đảm** chúng không thể truy cập nhau. Segmentation cần được hỗ trợ bởi route policy, firewall/security group, network ACL hoặc policy ở mức workload phù hợp. Ngược lại, phân chia quá nhiều subnet mà không có mục tiêu bảo mật hoặc vận hành sẽ khiến việc điều hành route và địa chỉ phức tạp hơn.

Mục tiêu thiết kế là **địa chỉ đủ phân biệt để định tuyến, chính sách đủ chi tiết để kiểm soát quyền**.

## 10. Chồng lấn với Kubernetes và hạ tầng container

Một cụm Kubernetes thường có nhiều lớp địa chỉ:

- **Node IP:** địa chỉ của máy/node, thường thuộc subnet VPC/VNet hoặc hạ tầng nơi node chạy.
- **Pod IP:** địa chỉ các pod theo cách CNI phân bổ; có thể là dải riêng, IP trực tiếp trong mạng cloud hoặc mô hình overlay.
- **Service IP/ClusterIP:** địa chỉ logic để ứng dụng truy cập dịch vụ trong cluster theo cơ chế điều phối mạng.
- **Ingress/Load Balancer IP:** địa chỉ nhận lưu lượng từ client trong hoặc ngoài môi trường.
- **Địa chỉ DNS và mạng container phụ trợ:** tùy nền tảng và plugin.

Các pool phải được đối chiếu với nhau và với các mạng dự kiến kết nối. Một pod CIDR trùng với địa chỉ VPN/on-prem có thể làm ứng dụng trong pod gửi kết nối đến địa chỉ tưởng là ngoài cluster nhưng lại bị xử lý như mạng local/overlay. Service CIDR trùng một vùng sử dụng ngoài cluster cũng có thể gây lỗi phân giải và route theo cách khó dự đoán.

### 10.1. Câu hỏi trước khi chọn Pod/Service CIDR

- CNI dùng IP overlay, routing thuần, cấp IP từ VPC/VNet hay một cơ chế hỗn hợp?
- Pod có cần kết nối trực tiếp với hệ thống ngoài cluster bằng IP thật không?
- Có nhiều cluster cần gọi nhau qua mesh, VPN hoặc transit không?
- Kế hoạch cluster mới và môi trường staging/DR dùng những pool nào?
- Có NAT hoặc gateway làm thay đổi địa chỉ nguồn/đích không?
- Hạn mức IP trên node, interface, subnet và cơ chế prefix delegation là gì?
- Kích thước pool có đáp ứng số node, max pods/node và thời gian rolling update không?

Một ví dụ đáng chú ý: cluster chạy 100 node, mỗi node có thể chứa tối đa 50 pod. Nhu cầu lý thuyết đã là **5.000 Pod IP**, chưa tính địa chỉ dùng cho daemon, hạ tầng, headroom và phương thức cấp phát của CNI. Subnet /20 có tổng 4.096 địa chỉ sẽ không đủ nếu giả định tất cả Pod IP phải lấy từ chính pool /20 đó. Phải thiết kế từ mô hình IP thực tế của CNI và quota nhà cung cấp, không dựa chỉ vào số node.

### 10.2. Vấn đề khi sáp nhập nhiều cluster

Nếu hai cluster độc lập cùng dùng Service CIDR **10.96.0.0/12**, chúng có thể vẫn chạy riêng nếu hoàn toàn không chia sẻ không gian route. Khi triển khai kết nối nhiều cluster, VPN hoặc service mesh, việc trùng dải có thể giới hạn hình thức kết nối; có giải pháp dùng gateway, DNS, dịch địa chỉ hoặc service identity nhưng chúng làm tăng phức tạp.

**Không nhất thiết phải quảng bá mọi Pod hoặc Service IP ra toàn mạng doanh nghiệp.** Có thể chọn API gateway hoặc ingress làm ranh giới kết nối. Dù vậy, phải ghi rõ phạm vi các địa chỉ đã dùng để tránh xung đột ngoài ý muốn trong hệ thống vận hành.

## 11. Chồng lấn khi kết nối đối tác, công ty con hoặc mạng kế thừa

Một vấn đề phổ biến là mạng đối tác không thuộc quyền quản lý của nhóm kiến trúc. Ví dụ:

- Đối tác A dùng 10.20.0.0/16; hệ thống nội bộ cũng có môi trường cũ dùng 10.20.0.0/16.
- Hai công ty sau sáp nhập đều sử dụng 192.168.0.0/16 cho chi nhánh.
- Một ứng dụng cũ có địa chỉ hardcode trong config, license, firewall rule hoặc thiết bị nhúng.

Trong trường hợp đó, không thể giả định “đổi CIDR ngay” là phương án chi phí thấp. Cần đo số lượng phụ thuộc và thời gian chuyển đổi.

### 11.1. Phương án xử lý và đánh đổi

| Phương án | Khi nào cân nhắc | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- | --- |
| **Đổi địa chỉ một phía (renumber)** | Có quyền kiểm soát mạng và thời gian chuyển đổi | Xóa nguyên nhân chồng lấn, đơn giản routing dài hạn | Cần sửa route, DNS, ACL, cấu hình ứng dụng, kiểm thử và kế hoạch cutover |
| **NAT hai chiều có kiểm soát** | Chưa thể đổi địa chỉ ngay; các luồng hữu hạn | Cho phép kết nối qua các địa chỉ đã dịch | Quản lý mapping, log, DNS; khó theo dõi địa chỉ gốc, có thể gây phức tạp giao thức |
| **Proxy/API gateway** | Chỉ cần một số dịch vụ mức ứng dụng | Giới hạn phạm vi chia sẻ, có thể kiểm soát auth/traffic | Không phù hợp mọi giao thức; gateway thành phụ thuộc vận hành |
| **Tách routing domain/VRF** | Cần cô lập nhiều miền trùng địa chỉ | Tránh va chạm trong từng miền | Cần gateway/chính sách rõ nếu trao đổi giữa các miền |
| **Kết nối qua dịch vụ ứng dụng** | Không cần route IP trực tiếp toàn mạng | Giảm phụ thuộc vào mạng bên kia | Phụ thuộc API, DNS, nhận dạng dịch vụ và phạm vi giao thức |

Không có phương án nào tự động an toàn. Ví dụ NAT có thể xử lý xung đột địa chỉ của luồng TCP đơn giản nhưng làm khó những giao thức đưa IP vào payload, kiểm toán địa chỉ nguồn, thiết lập kết nối chiều ngược hoặc xử lý DNS. Cần chứng minh bằng luồng dữ liệu cụ thể.

### 11.2. Ví dụ dịch địa chỉ tạm thời

Giả sử hai tổ chức đều dùng **10.20.1.0/24**, nhưng chỉ cần truy cập một API nội bộ ở 10.20.1.25 phía đối tác. Có thể trình bày đích đối tác bằng một địa chỉ ảo **10.200.1.25** thuộc một dải dịch địa chỉ được dành riêng, rồi ánh xạ qua gateway phù hợp.

Sơ đồ logic:

~~~mermaid
flowchart LR
    C["Ứng dụng nội bộ\n10.20.1.0/24"] --> DNS["DNS tên API đối tác\ntrả 10.200.1.25"]
    DNS --> GW["Gateway NAT/proxy\nđịa chỉ ảo 10.200.1.25"]
    GW --> P["Đối tác\nAPI thật 10.20.1.25"]
    GW -. "Ghi mapping, log và quyền" .-> AUD["Hệ thống quan sát / kiểm toán"]
~~~

Đây chỉ là **mô hình khái niệm**, không phải hướng dẫn cấu hình một thiết bị NAT cụ thể. Phải kiểm tra 10.200.1.0/24 có rảnh, có route phù hợp, translation là DNAT, SNAT hay cả hai theo topology và việc phản hồi có đi qua gateway nhất quán không. DNS, chứng chỉ TLS theo hostname, định tuyến và luật firewall cần khớp với thiết kế. Trong kế hoạch dài hạn, nên ghi thời hạn đánh giá lại việc đổi địa chỉ để không tích lũy các lớp dịch địa chỉ khó quản lý.

## 12. DNS và địa chỉ mạng phải được thiết kế cùng nhau

Không phải mọi lỗi “không tới được IP” là chồng lấn, và không phải mọi lỗi DNS là lỗi ứng dụng. Kiến trúc nhiều mạng cần làm rõ:

- **DNS resolution scope:** tên nội bộ được phân giải trong vùng nào? Có split-horizon DNS hay conditional forwarding không?
- **Địa chỉ trả về:** private IP của mạng đích hay public IP qua load balancer? Có dùng địa chỉ dịch NAT không?
- **Đường đi đến địa chỉ:** resolver trả về IP nhưng subnet nguồn có route tới đích không?
- **Quyền và bảo mật:** DNS nội bộ có thể làm lộ tên dịch vụ; kết nối vẫn phải xác thực và được phân quyền.
- **Thời gian cache:** sau khi đổi CIDR hoặc cutover, TTL và cache phía ứng dụng/OS có thể làm client tiếp tục dùng địa chỉ cũ.

Ví dụ tên **orders.corp.example.com** chỉ là tên minh họa. Nếu môi trường on-prem phải dùng địa chỉ 10.96.20.5 còn client cloud phải đi qua địa chỉ dịch 10.200.20.5, quy tắc DNS phải phản ánh ranh giới mạng đang sử dụng. Tuy nhiên, nhiều phiên bản địa chỉ cho một tên cũng làm tăng rủi ro vận hành, nên chỉ dùng khi thật sự cần.

**Không dùng DNS như biện pháp che giấu xung đột route.** Nếu hai đích có cùng IP và cùng xuất hiện trong một routing domain, đổi tên bản ghi không tạo thêm khả năng phân biệt địa chỉ ở lớp IP.

## 13. Tính toán dung lượng theo tăng trưởng

Quy hoạch địa chỉ nên dựa trên nhu cầu **đỉnh**, cơ chế mở rộng và độ dư, thay vì chỉ đếm số máy hiện tại.

### 13.1. Những loại địa chỉ cần cộng vào

- VM/node hiện tại và tối đa khi autoscaling.
- IP phụ gắn vào interface, load balancer và dịch vụ mạng.
- Pod IP hoặc prefix dùng bởi container theo CNI thực tế.
- Quota và địa chỉ dự trữ của nhà cung cấp ở mỗi subnet.
- Bản triển khai rolling/blue-green cần chạy song song phiên bản cũ và mới.
- Tài nguyên DR, migration, kiểm thử và khả năng tăng khu vực.
- Dải dự trữ cho dịch vụ chưa được tạo ngay nhưng đã nằm trong roadmap.

Ví dụ một nhóm ứng dụng dự báo cần:

| Nguồn sử dụng | Nhu cầu ở thời điểm đỉnh (minh họa) |
| --- | ---: |
| Node/VM và interface chính | 280 |
| IP phụ/POD IP được cấp trong subnet | 700 |
| Tài nguyên hạ tầng và dịch vụ mạng | 120 |
| Dư địa rolling deployment | 150 |
| Tổng nhu cầu ước tính | **1.250** |

Nếu dùng /21 (2.048 IP tổng) cần so với địa chỉ khả dụng thực tế và headroom chính sách. Dùng /20 (4.096 IP tổng) tạo thêm dư địa nhưng tiêu tốn gấp đôi không gian địa chỉ của /21. Quyết định cần được ghi trong bản dự báo, không phải chọn /20 theo cảm tính.

### 13.2. Không chỉ dự báo theo số IP

Khi nhiều workload dùng chung một database hoặc load balancer, số IP còn đủ **không có nghĩa hệ thống đủ khả năng mở rộng**. Quy hoạch địa chỉ cần kết hợp quota interface, số subnet, throughput thiết bị mạng, băng thông VPN/transit, route table limits và chi phí truyền dữ liệu. Sự thiếu hụt IP chỉ là **một trong các giới hạn**.

## 14. Các quyết định bảo mật gắn với không gian địa chỉ

Một dải IP riêng không chứng minh tài nguyên bên trong đáng tin cậy. Với cloud architecture, địa chỉ là **đầu vào cho định tuyến và chính sách**, còn danh tính, quyền và bảo mật phải được kiểm tra độc lập.

### 14.1. Bảo mật mạng ở nhiều lớp

| Lớp | Quyết định chính | Ví dụ kiểm soát |
| --- | --- | --- |
| Phân vùng cấp tổ chức | Môi trường prod/staging và dữ liệu nhạy cảm có cần kết nối không? | Tách tài khoản, VPC/VNet, routing domain và transit policy |
| Subnet/route | Tài nguyên nào cần Internet, private WAN hay không có egress? | Route table, network firewall, endpoint private, NAT nếu cần |
| Workload | Ai được gọi DB và theo giao thức nào? | Security group/ACL/network policy, service identity |
| Ứng dụng | Tài khoản/tenant có quyền truy cập bản ghi không? | Authentication, authorization, kiểm tra phạm vi dữ liệu |
| Quan sát | Có thể chứng minh đường đi và phát hiện bất thường không? | Flow log, audit, metrics, thay đổi route và policy |

Tránh thiết kế firewall chỉ dựa trên các khối địa chỉ quá rộng như **10.0.0.0/8** khi thực tế chỉ cần vài subnet. CIDR tổng hợp phù hợp định tuyến không nhất thiết phù hợp chính sách truy cập. Tổng hợp quá mức trong firewall có thể cho phép nhiều nguồn chưa được phê duyệt.

### 14.2. Khi nhiều mạng dùng địa chỉ giống nhau

Nếu dùng VRF/NAT để tạm chấp nhận chồng lấn, log và audit phải làm rõ **địa chỉ trước và sau dịch, thời điểm, miền mạng, danh tính liên quan**. Chỉ nhìn IP 10.20.1.25 mà không biết routing domain hoặc mapping thời điểm đó có thể dẫn đến kết luận điều tra sai.

### 14.3. Phạm vi địa lý và tuân thủ

Subnet và VPC CIDR không tự biểu thị **quốc gia lưu dữ liệu**. Một dải 10.64.0.0/16 có thể được dùng ở bất kỳ region nào được cấu hình. Đối với dữ liệu cá nhân hoặc dữ liệu ngành đặc thù, vẫn cần xác định vùng lưu, backup, replica, log, hệ thống đối tác và quyền truy cập từ xa. Quy hoạch địa chỉ hỗ trợ kiểm kê và kiểm soát luồng, nhưng **không thay thế** đánh giá nghĩa vụ pháp lý hoặc hợp đồng.

## 15. Quy trình triển khai thực tế

Đối với một dự án mạng cloud mới, quy trình nên có **đầu vào, phê duyệt, cấp phát, triển khai và kiểm tra** rõ ràng.

### Bước 1: Thu thập hiện trạng và kế hoạch kết nối

Xác định chủ sở hữu mạng tại chỗ, các VPC/VNet, network overlay, chi nhánh, VPN và đối tác. Thu CIDR và bảng route đang hoạt động; ghi những mạng dự kiến cần kết nối trong tương lai.

### Bước 2: Định nghĩa routing domains

Chia các mạng theo ranh giới được phép trao đổi, ví dụ production, staging, on-prem, partner. Tài liệu phải nêu những đường kết nối hiện tại, khả năng peering/transit trong tương lai và trường hợp mạng được cố ý cô lập.

### Bước 3: Chọn pool và lập phương án phân cấp

Dựa trên inventory đã xác minh, chọn pool cha và dự trù CIDR cho từng region, tài khoản, cluster, site. Tránh lấy các dải RFC1918 có vẻ “ít người dùng” khi chưa kiểm tra mạng kế thừa hoặc đối tác.

### Bước 4: Tính dung lượng và reserve

Ước tính peak IP theo dịch vụ/zone, cộng headroom theo kế hoạch. Reserve CIDR **trước khi tạo tài nguyên** và ghi owner, routing domain, mục đích, ngày cấp.

### Bước 5: Thẩm định overlap và route

Chạy so sánh CIDR trong IPAM, kiểm tra vùng cha, cấp phát đồng cấp, mạng đang hoạt động và những mạng dự kiến kết nối. Review route summarization, prefix advertisement, VPN, DNS và firewall.

### Bước 6: Triển khai bằng IaC

Tạo network/subnet và tài nguyên qua cơ chế quản lý cấu hình; hạn chế tạo CIDR thủ công không đưa vào nguồn dữ liệu chính. Đồng bộ ID tài nguyên tạo ra với IPAM để dễ đối soát.

### Bước 7: Kiểm thử kết nối và tình huống lỗi

Đo đường đi thực tế theo nguồn–đích, cả chiều phản hồi, độ trễ, DNS, NAT, failover, các bản ghi flow log và đường tới đích trong mỗi routing domain. Kiểm tra cả **trường hợp phải bị chặn**.

### Bước 8: Theo dõi và tái đánh giá

Theo dõi utilization, phát hiện subnet cạn IP, phát hiện route drift, rà soát tài nguyên không còn dùng; kiểm tra lại kế hoạch khi thêm region, sáp nhập doanh nghiệp, mở VPN đối tác hoặc thay đổi CNI.

### 15.1. Ma trận nghiệm thu mạng

| Yêu cầu | Bằng chứng cần xem |
| --- | --- |
| Không có subnet cấp phát trùng nhau trong miền phải kết nối | Báo cáo IPAM/CIDR overlap và danh sách phân cấp |
| Mạng cloud kết nối đúng mạng tại chỗ | Route hai chiều, DNS, kiểm thử TCP/ứng dụng, flow log |
| Mạng staging không truy cập dữ liệu production ngoài ý muốn | Kiểm thử từ nguồn staging, firewall/transit policy |
| Có khả năng mở rộng thêm một AZ hoặc cụm mới | CIDR dự trữ và thử cấp phát giả lập trong IPAM |
| Tăng số replica không làm cạn IP đột ngột | Dự báo peak, cảnh báo utilization, quota liên quan |
| Đối tác có CIDR trùng vẫn được xử lý an toàn | Tài liệu mapping NAT/proxy, log, test hai chiều và kế hoạch xử lý dài hạn |
| Dữ liệu và luồng đi đúng khu vực được phê duyệt | Inventory vùng dịch vụ, route policy và kiểm tra luồng dữ liệu thực tế |

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm | Cách phòng tránh |
| --- | --- | --- |
| Mỗi dự án tự chọn 10.0.0.0/16 | Khi kết nối chung sẽ xuất hiện overlap | Cấp phát từ IPAM/pool được quản lý |
| Chỉ kiểm tra subnet bên trong một VPC | CIDR có thể trùng on-prem, branch, partner hoặc cluster | Kiểm kê theo nhu cầu kết nối xuyên miền |
| Coi mọi CIDR cha–con overlap là lỗi | IPAM có thể từ chối phân bổ hợp lệ | Phân biệt pool cha, reservation và subnet được cấp |
| Chia tất cả subnet /24 bất kể workload | Dễ thiếu IP khi autoscale/rolling update | Dự báo peak theo loại dịch vụ và quota |
| Cấp mỗi workload /16 để dư địa vô hạn | Làm cạn dải RFC1918, khó kết nối về sau | Phân cấp hợp lý, dự trữ có chủ đích |
| Không kiểm tra Pod/Service CIDR | Container không tới được mạng ngoài hoặc lỗi DNS/routing | Ghi cả các pool ảo/overlay trong IPAM |
| Đổi route nhưng bỏ qua DNS | Client tiếp tục gọi địa chỉ cũ hoặc đích sai | Kiểm tra split DNS, TTL và kế hoạch cutover |
| Quảng bá route tổng hợp quá rộng | Traffic đi nhầm hoặc đến mạng chưa được phê duyệt | Quảng bá chỉ những prefix có chủ sở hữu/đường đi rõ |
| Dùng NAT để che mọi overlap | Tăng mapping, khó log, rủi ro giao thức và vận hành | Chỉ dùng theo luồng cần thiết, có kế hoạch renumber |
| Gắn nhãn private subnet chỉ dựa trên CIDR | Có thể route tới Internet/nguồn không mong muốn | Xác minh route, gateway, policy và egress |
| Không giữ reserve trước triển khai | Hai nhóm cùng lấy một dải | Reserve atomically rồi mới deploy |
| Tái sử dụng CIDR ngay khi xóa tài nguyên | DNS, firewall, route và đối tác vẫn trỏ tới địa chỉ cũ | Thu hồi theo quy trình và kiểm tra phụ thuộc |

## 17. Đánh đổi kiến trúc và Well-Architected

Không có phương án cấp phát địa chỉ tốt nhất cho mọi tổ chức. Quy hoạch cần giải thích sự đánh đổi với năm góc đánh giá:

| Góc nhìn | Câu hỏi thiết kế | Ví dụ đánh đổi |
| --- | --- | --- |
| **Độ tin cậy** | Kết nối DR và failover có sẵn dải/route không chồng lấn? | Dành dải cho region dự phòng giúp phục hồi dễ hơn nhưng làm giảm pool chưa sử dụng |
| **Bảo mật** | Các môi trường có bị kết nối ngoài ý muốn không? | CIDR tổng hợp đơn giản routing nhưng cần firewall đủ hẹp |
| **Hiệu quả hiệu năng** | Đường đi VPN/transit/NAT có tạo thêm hop hoặc nút thắt? | NAT giải quyết overlap tạm nhưng làm tăng phụ thuộc và có thể tăng latency |
| **Tối ưu chi phí** | Chi phí cấp phát quá rộng, renumber, gateway, route và vận hành là bao nhiêu? | Dành dư địa có chi phí cơ hội; thiếu dư địa làm migration tốn kém |
| **Khả năng vận hành** | Ai chịu trách nhiệm IPAM, drift, subnet cạn IP và thay đổi route? | Phân cấp và tự động hóa giảm lỗi nhưng cần quy trình kiểm soát thống nhất |

Ví dụ: dùng **10.64.0.0/16** cho một vùng cloud lớn có thể giúp route summary đơn giản. Nhưng nếu nhiều nhóm dùng riêng các /16 mà không có IPAM, tổng số dải hợp lệ sẽ nhanh chóng cạn và sự cố overlap xuất hiện khi kết nối mới. Quyết định đúng phải gắn **khối cha, chủ sở hữu, phạm vi định tuyến, nhu cầu tăng trưởng, chính sách cấp phát và điều kiện kiểm tra lại**.

## 18. Bài tập thực hành

Một công ty có những mạng sau:

| Mạng | CIDR | Nhu cầu |
| --- | --- | --- |
| Data center A | 10.80.0.0/16 | Kết nối cloud production |
| Chi nhánh B | 10.81.0.0/16 | Truy cập API nội bộ |
| Cloud production region 1 | 10.80.32.0/20 | Đã tạo, dự kiến kết nối VPN tới data center A |
| Cloud staging | 10.82.0.0/16 | Chưa cần kết nối production |
| Kubernetes cluster 1 (Pod) | 10.83.0.0/16 | Có thể cần kết nối workload on-prem |
| Đối tác P | 10.81.20.0/24 | Chỉ cần gọi một API từ chi nhánh B |

Hãy trả lời:

1. Cặp CIDR nào overlap? Có phải tất cả cặp này đều cần xử lý ngay không?
2. Nếu production region 1 chưa chạy tải thật, bạn sẽ đề xuất đổi CIDR ra dải nào và cần kiểm tra những gì trước khi chọn?
3. Nếu đối tác P không thể đổi địa chỉ, bạn sẽ cân nhắc NAT/proxy hay yêu cầu truy cập trực tiếp? Những log và kiểm thử nào cần có?
4. Nếu cluster 1 tăng gấp bốn số node, những thông số CNI và quota nào quyết định dải Pod CIDR có đủ không?
5. Thiết kế IPAM thế nào để các project tương lai không lặp lại lỗi đã xảy ra?

**Gợi ý phân tích:** 10.80.32.0/20 nằm trong 10.80.0.0/16; 10.81.20.0/24 nằm trong 10.81.0.0/16. Hai cặp này chồng lấn về địa chỉ; mức độ xung đột phụ thuộc vào việc có cần route trực tiếp cùng miền hay không. Các dải khác trong bảng không giao nhau. Việc chọn CIDR thay thế cần kiểm tra **toàn bộ inventory**, vì một dải có vẻ chưa dùng trong bảng bài tập chưa chắc rảnh trong hệ thống thực tế.

## 19. Checklist bàn giao bản thiết kế địa chỉ

- [ ] Có sơ đồ tất cả routing domain, VPC/VNet, subnet, on-prem, branch, partner và cluster liên quan.
- [ ] Mỗi CIDR có trạng thái IPAM, chủ sở hữu, mục đích, vùng và khối cha rõ ràng.
- [ ] Các cấp phát đồng cấp được kiểm tra overlap; quan hệ cha–con được ghi nhận có chủ đích.
- [ ] Nhu cầu IP theo peak, autoscaling, rollout và headroom đã được tính, kể cả địa chỉ dự trữ của nền tảng.
- [ ] CIDR của Kubernetes Pod, Service, node và các hệ thống overlay đã được kiểm kê.
- [ ] Route advertisement, route summary, DNS và đường phản hồi đã được thiết kế và kiểm chứng.
- [ ] Segmentation và chính sách firewall phù hợp với dữ liệu/ứng dụng; không chỉ dựa trên “private IP”.
- [ ] Những nơi dùng NAT/proxy/VRF có mapping, logging, owner, test và điều kiện đánh giá lại.
- [ ] IaC dùng giá trị cấp phát từ nguồn quản lý, có kiểm tra drift và cảnh báo subnet gần cạn.
- [ ] Phương án mở rộng region, DR, kết nối đối tác và sáp nhập mạng đã có dải dự trữ hoặc kế hoạch renumber.
- [ ] Mọi thay đổi CIDR có phương án chuyển đổi, rollback, cập nhật DNS và xác minh kết nối đầu cuối.

**Điểm cốt lõi:** một CIDR hợp lệ chỉ là điểm khởi đầu. Không gian địa chỉ phải được quy hoạch trên toàn bộ **phạm vi kết nối**, bao gồm những hệ thống chưa được xây dựng hôm nay nhưng có thể sẽ kết nối trong tương lai. Khi CIDR được cấp phát có chủ sở hữu, kiểm tra chồng lấn, định tuyến nhất quán và quản lý bằng IPAM, kiến trúc đám mây sẽ dễ mở rộng, phục hồi, bảo mật và vận hành hơn.
