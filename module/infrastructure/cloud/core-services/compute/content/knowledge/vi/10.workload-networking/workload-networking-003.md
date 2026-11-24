# Route, NAT và kết nối đi ra của máy không có IP công cộng

Máy ảo hoặc container không có địa chỉ IP công cộng vẫn có thể cần tải bản vá hệ điều hành, lấy image, gọi API bên ngoài, gửi log hoặc kết nối tới dịch vụ được quản lý. Để đáp ứng nhu cầu đó, mạng đám mây thường đặt workload trong subnet riêng và điều khiển đường đi ra bằng bảng định tuyến, NAT gateway, firewall, proxy hoặc private endpoint.

Thiết kế đúng giúp workload khởi tạo kết nối ra ngoài mà không phải công khai địa chỉ của từng máy. Tuy nhiên, chỉ thêm một tuyến mặc định tới NAT là chưa đủ: cần hiểu đường đi và đường về, phạm vi cho phép của firewall, DNS, khả năng cấp phát NAT, tính sẵn sàng theo vùng và cách quan sát lưu lượng.

Bài học này giải thích cách định tuyến và NAT hoạt động, cách tổ chức subnet công cộng và riêng tư, lựa chọn phương án egress cho IPv4 và IPv6, cùng quy trình kiểm tra khi máy không có IP công cộng không thể kết nối tới đích cần thiết.

Sau bài học, bạn có thể:

- Giải thích cách route table quyết định next hop cho lưu lượng đi ra.
- Mô tả quá trình NAT chuyển đổi địa chỉ và cổng nguồn cho kết nối từ workload riêng tư.
- Thiết kế đường đi từ subnet riêng tới Internet hoặc dịch vụ đám mây mà không gán IP công cộng cho máy.
- Phân biệt NAT gateway, NAT instance, proxy, firewall và private endpoint.
- Đánh giá bảo mật, tính sẵn sàng, chi phí và giới hạn kết nối của từng phương án.
- Chẩn đoán sự cố định tuyến, DNS, firewall, NAT và đường về.

## 1. Vì sao workload không có IP công cộng vẫn cần kết nối đi ra?

IP công cộng gắn trực tiếp với một máy khiến máy có thể được định tuyến từ Internet tới địa chỉ đó, nếu các lớp bảo mật cho phép. Điều này làm tăng bề mặt tấn công và khiến việc quản lý địa chỉ, allowlist, firewall trên từng máy trở nên phức tạp.

Trong nhiều hệ thống, máy ứng dụng chỉ cần **khởi tạo kết nối đi ra**. Ví dụ:

- Máy mới tải bản vá và gói phần mềm từ kho của nhà cung cấp.
- Container runtime lấy image từ registry.
- Ứng dụng gọi API thanh toán, dịch vụ bản đồ hoặc API của đối tác.
- Agent gửi log, metric và trace tới nền tảng giám sát.
- Worker lấy tác vụ từ hàng đợi hoặc đọc dữ liệu từ dịch vụ bên ngoài.
- Máy triển khai tải artifact từ kho lưu trữ.

Những máy này có thể dùng địa chỉ IPv4 riêng trong mạng ảo. Khi cần truy cập Internet, lưu lượng được đưa qua một thành phần egress có địa chỉ công cộng hoặc qua proxy/firewall được quản lý. Thành phần đó đại diện cho nhiều workload và che địa chỉ riêng của chúng khỏi đích bên ngoài.

Không có IP công cộng không đồng nghĩa với việc máy bị cô lập hoàn toàn. Khả năng kết nối phụ thuộc vào route table, gateway, chính sách bảo mật, DNS và chính sách ở phía đích. Ngược lại, có tuyến ra Internet cũng không có nghĩa mọi lưu lượng đều được phép: firewall hoặc security policy vẫn có thể chặn đích và cổng không được phê duyệt.

## 2. Định tuyến quyết định đường đi như thế nào?

Router sử dụng bảng định tuyến để chọn next hop cho một gói tin. Mỗi tuyến thường gồm:

- **Destination prefix:** mạng đích, viết dưới dạng CIDR.
- **Next hop/target:** nơi chuyển tiếp gói tin, ví dụ gateway, NAT, firewall, peering connection hoặc network interface.
- **Trạng thái tuyến:** tuyến đang hoạt động hay không.
- **Phạm vi áp dụng:** route table được liên kết với subnet hoặc mạng nào.

Khi có nhiều tuyến phù hợp, router thường chọn tuyến có prefix cụ thể nhất, tức longest-prefix match. Ví dụ, tuyến tới 10.30.0.0/16 được ưu tiên hơn tuyến mặc định 0.0.0.0/0 cho một địa chỉ nằm trong dải 10.30.0.0/16. Quy tắc ưu tiên chi tiết giữa các loại route hoặc route cùng prefix có thể khác nhau theo nền tảng đám mây; cần kiểm tra tài liệu của nhà cung cấp.

### Tuyến cục bộ và tuyến mặc định

Trong mạng ảo, thường có một tuyến cục bộ cho phép các subnet thuộc cùng mạng trao đổi lưu lượng theo thiết kế. Một tuyến mặc định IPv4 có dạng 0.0.0.0/0 và khớp với mọi địa chỉ IPv4 không có tuyến cụ thể hơn. Với IPv6, tuyến mặc định tương ứng là ::/0.

Ví dụ một route table của subnet ứng dụng riêng:

| Destination | Target | Ý nghĩa |
|---|---|---|
| 10.20.0.0/16 | local | Gửi lưu lượng tới các địa chỉ trong mạng ảo |
| 10.40.0.0/16 | peering hoặc transit gateway | Gửi tới mạng được kết nối riêng |
| 0.0.0.0/0 | NAT gateway | Gửi các đích IPv4 còn lại qua NAT |

Tuyến tới mạng nội bộ cụ thể hơn tuyến mặc định. Vì vậy, máy trong subnet riêng có thể truy cập dịch vụ nội bộ qua kết nối riêng, trong khi lưu lượng tới địa chỉ Internet đi qua NAT. Tuyến thực tế phải phản ánh topology và chính sách của tổ chức.

### Route table được gắn với subnet

Một route table chỉ có tác dụng với subnet hoặc phạm vi mạng được liên kết với nó. Hai subnet nằm trong cùng một VPC/VNet có thể dùng route table khác nhau:

- Subnet công cộng có tuyến tới Internet gateway.
- Subnet riêng có tuyến mặc định tới NAT gateway.
- Subnet dữ liệu có thể không có tuyến Internet mặc định, chỉ có tuyến tới các dịch vụ nội bộ cần thiết.

Tên gọi public subnet và private subnet thường dựa trên đường định tuyến, không chỉ dựa vào tên subnet hay việc địa chỉ máy thuộc dải riêng. Một subnet được xem là công cộng khi có đường tới Internet gateway và workload có địa chỉ công cộng cùng chính sách cho phép phù hợp. Nếu subnet không có đường trực tiếp như vậy và egress đi qua NAT hoặc proxy, nó thường được xem là subnet riêng.

## 3. NAT hoạt động ra sao?

NAT (Network Address Translation) thay đổi thông tin địa chỉ IP trong gói tin khi gói đi qua một thiết bị hoặc dịch vụ trung gian. Với nhu cầu workload riêng tư truy cập IPv4 Internet, loại thường gặp là source NAT (SNAT), thường kết hợp dịch địa chỉ và cổng nguồn (PAT/NAPT).

Giả sử:

- Máy ứng dụng có IP riêng 10.20.11.25.
- Máy cần gọi API tại 198.51.100.40 cổng TCP 443.
- NAT gateway có địa chỉ công cộng 203.0.113.10.

Khi ứng dụng mở kết nối, NAT tạo một ánh xạ cho luồng đó:

| Trước NAT | Sau NAT |
|---|---|
| Source: 10.20.11.25:51520 | Source: 203.0.113.10:62001 |
| Destination: 198.51.100.40:443 | Destination: 198.51.100.40:443 |

Địa chỉ và cổng ở trên chỉ là ví dụ minh họa. NAT ghi nhận trạng thái ánh xạ để khi phản hồi từ API quay về 203.0.113.10:62001, nó có thể chuyển gói tin trở lại 10.20.11.25:51520. Đích bên ngoài nhìn thấy địa chỉ egress của NAT thay vì địa chỉ riêng của máy ứng dụng.

### Luồng đi và luồng về

~~~mermaid
sequenceDiagram
    participant VM as Máy riêng 10.20.11.25
    participant RT as Route table
    participant NAT as NAT gateway
    participant IGW as Internet gateway
    participant API as API bên ngoài
    VM->>RT: Gửi TCP tới API:443
    RT->>NAT: Tuyến mặc định trỏ tới NAT
    NAT->>NAT: Ánh xạ IP/cổng nguồn
    NAT->>IGW: Gửi gói với IP egress công cộng
    IGW->>API: Chuyển tiếp tới API
    API-->>IGW: Phản hồi tới IP/cổng NAT
    IGW-->>NAT: Chuyển gói phản hồi
    NAT->>NAT: Tra ánh xạ kết nối
    NAT-->>VM: Chuyển phản hồi về IP riêng
~~~

NAT thường cho phép kết nối được khởi tạo từ bên trong và chuyển phản hồi thuộc kết nối đó về đúng máy. Nó không tự động cho phép một máy bất kỳ trên Internet chủ động mở kết nối mới tới workload riêng tư. Nếu cần công bố dịch vụ nhận kết nối từ bên ngoài, hãy dùng load balancer, reverse proxy, API gateway, VPN hoặc một kiến trúc inbound được thiết kế riêng.

NAT cũng không thay thế firewall. NAT giải quyết việc dịch địa chỉ/cổng và duy trì ánh xạ luồng; firewall quyết định lưu lượng nào được phép. Cần kết hợp route, security group, network ACL, firewall policy và chính sách ở ứng dụng.

## 4. Mẫu kiến trúc subnet riêng với NAT gateway

Một kiến trúc IPv4 phổ biến gồm một mạng ảo, subnet công cộng đặt NAT gateway và các subnet riêng đặt workload. NAT gateway có địa chỉ công cộng và có tuyến tới Internet gateway; máy ứng dụng không được gán IP công cộng.

Ví dụ mạng ảo sử dụng dải 10.20.0.0/16:

| Thành phần | Dải hoặc địa chỉ minh họa | Route chính |
|---|---|---|
| Public subnet | 10.20.1.0/24 | 10.20.0.0/16 local; 0.0.0.0/0 tới Internet gateway |
| NAT gateway | 10.20.1.10 và một địa chỉ egress công cộng | Chuyển lưu lượng ra Internet qua Internet gateway |
| Private app subnet | 10.20.11.0/24 | 10.20.0.0/16 local; 0.0.0.0/0 tới NAT gateway |
| Private data subnet | 10.20.21.0/24 | Chỉ các route nội bộ hoặc endpoint cần thiết |

Các dải và địa chỉ trên chỉ là ví dụ. Cần chọn CIDR không trùng với mạng tại chỗ, mạng đối tác hoặc các VPC/VNet được kết nối.

~~~mermaid
flowchart TB
    Internet["Internet / API bên ngoài"]
    IGW["Internet gateway"]
    subgraph VPC["Mạng ảo 10.20.0.0/16"]
        subgraph Public["Public subnet 10.20.1.0/24"]
            NAT["NAT gateway\nIP riêng + IP egress công cộng"]
        end
        subgraph PrivateApp["Private app subnet 10.20.11.0/24"]
            VM1["App VM A\n10.20.11.25"]
            VM2["App VM B\n10.20.11.26"]
        end
        subgraph PrivateData["Private data subnet 10.20.21.0/24"]
            DB["Database\n10.20.21.10"]
        end
        RT1["Route table public\n0.0.0.0/0 → IGW"]
        RT2["Route table private\n0.0.0.0/0 → NAT"]
    end
    VM1 --> RT2
    VM2 --> RT2
    RT2 --> NAT
    NAT --> RT1
    RT1 --> IGW
    IGW --> Internet
    VM1 --> DB
    VM2 --> DB
~~~

Để cấu hình mẫu này:

1. Tạo mạng ảo và các subnet với CIDR không chồng lấn.
2. Tạo Internet gateway hoặc thành phần tương đương và gắn với mạng ảo.
3. Liên kết route table công cộng với public subnet; thêm tuyến mặc định tới Internet gateway.
4. Tạo NAT gateway trong public subnet và gắn địa chỉ egress công cộng theo yêu cầu của nền tảng.
5. Bảo đảm subnet công cộng có tuyến tới Internet gateway để NAT có thể gửi lưu lượng ra ngoài.
6. Liên kết route table riêng với private app subnet; thêm tuyến mặc định IPv4 tới NAT gateway.
7. Tạo máy ứng dụng chỉ với IP riêng và áp dụng security policy giới hạn egress.
8. Kiểm tra DNS, firewall, route chiều đi và chiều về từ máy ứng dụng tới một đích được phép.

Nếu NAT gateway không có tuyến ra Internet gateway, hoặc public subnet không có đường ra hợp lệ, workload riêng vẫn không thể truy cập Internet. Cần kiểm tra toàn bộ chuỗi next hop thay vì chỉ nhìn route table của subnet ứng dụng.

## 5. Chọn NAT gateway, NAT instance, proxy hay firewall?

### NAT gateway được quản lý

NAT gateway do nhà cung cấp đám mây quản lý thường giảm công sức cài đặt và vận hành hệ điều hành, cập nhật phần mềm, theo dõi tiến trình NAT và thay thế máy hỏng. Nó phù hợp với nhu cầu egress IPv4 phổ biến của nhiều workload.

Các giới hạn cần kiểm tra theo từng nhà cung cấp:

- Phạm vi sẵn sàng: gateway gắn với một zone, nhiều zone hay là dịch vụ regional.
- Giới hạn số kết nối đồng thời, tốc độ xử lý, số cổng nguồn và băng thông.
- Thời gian timeout của ánh xạ kết nối nhàn rỗi.
- Số lượng địa chỉ egress có thể gắn và khả năng mở rộng.
- Phí theo thời gian chạy, dung lượng dữ liệu xử lý và lưu lượng liên vùng.
- Khả năng ghi log, metric và tích hợp với firewall.

NAT gateway thường đơn giản cho SNAT nhưng không nhất thiết cung cấp lọc theo tên miền, kiểm tra nội dung hoặc chính sách ứng dụng chi tiết. Nếu tổ chức cần kiểm soát egress theo domain, danh tính workload hoặc loại dữ liệu, có thể cần firewall hoặc proxy chuyên dụng.

### NAT instance tự quản lý

NAT instance là một máy ảo được cấu hình để chuyển tiếp lưu lượng và thực hiện NAT. Nó có thể cho phép tùy chỉnh firewall, proxy, logging hoặc phần mềm mạng theo nhu cầu.

Đổi lại, nhóm vận hành phải chịu trách nhiệm:

- Bật forwarding và cấu hình SNAT/PAT đúng cách.
- Cập nhật hệ điều hành, kernel và phần mềm mạng.
- Giám sát CPU, bộ nhớ, network throughput và bảng connection tracking.
- Thiết kế autoscaling hoặc cơ chế thay thế khi máy lỗi.
- Xử lý source/destination check hoặc cấu hình tương đương nếu nền tảng yêu cầu.
- Tránh để một instance đơn lẻ trở thành điểm lỗi duy nhất.

NAT instance có thể phù hợp với nhu cầu đặc thù hoặc lab, nhưng cần tính cả chi phí nhân lực và rủi ro vận hành. Không nên coi việc tạo một VM có IP công cộng và bật IP forwarding là một kiến trúc egress sẵn sàng cao.

### Proxy egress

Proxy là thành phần trung gian ở tầng ứng dụng hoặc tầng giao thức. Workload được cấu hình gửi yêu cầu qua proxy; proxy có thể xác thực workload, lọc domain, ghi log theo yêu cầu HTTP, áp dụng chính sách TLS hoặc giới hạn tốc độ.

Proxy có thể bổ sung khả năng kiểm soát mà NAT thuần túy không có, nhưng ứng dụng hoặc runtime phải biết sử dụng proxy. Không phải mọi giao thức đều tương thích với HTTP proxy; một số ứng dụng cần SOCKS hoặc proxy chuyên biệt. Cần quản lý chứng chỉ, xác thực, tính sẵn sàng và tránh để proxy trở thành điểm nghẽn.

### Firewall egress

Firewall tập trung chính sách lưu lượng đi ra theo địa chỉ, cổng, giao thức, domain hoặc danh tính tùy khả năng sản phẩm. Firewall có thể nằm trước NAT hoặc tích hợp với dịch vụ NAT/egress của nền tảng. Cần xác định rõ thứ tự xử lý để route và stateful inspection hoạt động đúng.

| Phương án | Điểm mạnh | Chi phí/rủi ro cần cân nhắc | Khi phù hợp |
|---|---|---|---|
| NAT gateway quản lý | Ít vận hành hệ điều hành, dễ dùng cho SNAT | Phí gateway và dữ liệu, giới hạn kết nối, phạm vi zone | Workload cần egress IPv4 thông thường |
| NAT instance | Tùy biến sâu, có thể chạy phần mềm mạng riêng | Tự vá, scale, giám sát và thiết kế HA | Lab hoặc yêu cầu tùy chỉnh đặc biệt |
| Proxy egress | Chính sách ở tầng ứng dụng, log chi tiết hơn | Cần cấu hình client, quản lý proxy và chứng chỉ | Kiểm soát domain/API và audit egress |
| Firewall egress | Chính sách bảo mật tập trung, lọc lưu lượng | Chi phí, độ trễ, thiết kế HA và quản lý rule | Môi trường cần kiểm soát lưu lượng nghiêm ngặt |
| Private endpoint | Lưu lượng tới dịch vụ được giữ trong mạng riêng | Phụ thuộc dịch vụ, vùng và chi phí endpoint | Truy cập dịch vụ cloud được hỗ trợ qua mạng riêng |

Các phương án có thể kết hợp. Ví dụ, workload gửi yêu cầu HTTP qua proxy để kiểm soát domain, còn proxy sử dụng NAT gateway để ra Internet; các yêu cầu tới object storage hoặc registry được hỗ trợ private endpoint để tránh đường Internet công cộng.

## 6. Private endpoint và kết nối riêng tới dịch vụ đám mây

Không phải mọi nhu cầu kết nối đi ra đều cần Internet. Nếu workload chỉ cần truy cập dịch vụ được cung cấp trong cùng hệ sinh thái đám mây, hãy kiểm tra khả năng dùng private endpoint, service endpoint hoặc kết nối mạng riêng tương đương.

Ví dụ:

- Máy ứng dụng tải artifact từ object storage qua endpoint riêng.
- Container runtime lấy image từ registry nội bộ.
- Worker truy cập message queue hoặc database qua địa chỉ riêng.
- Dịch vụ giám sát nhận log qua private link hoặc endpoint nội bộ.

Lợi ích thường gặp:

- Lưu lượng không cần đi qua Internet công cộng.
- Có thể tránh phí NAT hoặc phí truyền dữ liệu Internet cho một số đường đi.
- Chính sách truy cập có thể giới hạn theo mạng, endpoint hoặc danh tính dịch vụ.
- Giảm phụ thuộc vào IP công cộng và allowlist bên ngoài.

Private endpoint không tự động cho phép truy cập mọi dịch vụ. Cần kiểm tra dịch vụ và region có hỗ trợ hay không, DNS riêng đã trỏ đúng endpoint chưa, route và security policy có cho phép không, cùng quyền IAM hoặc quyền dịch vụ tương ứng. Một endpoint riêng vẫn cần xác thực và phân quyền ở tầng ứng dụng.

Khi một workload có cả nhu cầu private và public egress, nên tạo route cụ thể tới endpoint hoặc mạng riêng; chỉ các đích còn lại mới đi theo tuyến mặc định tới NAT hoặc proxy. Cần kiểm tra longest-prefix match và DNS để chắc chắn tên dịch vụ được phân giải thành địa chỉ của endpoint riêng.

## 7. IPv6 và egress-only gateway

IPv6 có cách tiếp cận khác IPv4. Một workload có thể dùng địa chỉ IPv6 global unicast có khả năng định tuyến toàn cục mà không cần NAT địa chỉ như IPv4. Vì vậy, bảo vệ egress IPv6 thường dựa vào route table, security group, firewall và một thành phần egress-only gateway nếu nền tảng cung cấp.

**Egress-only Internet gateway** cho phép workload IPv6 khởi tạo kết nối ra Internet và nhận phản hồi thuộc kết nối đó, đồng thời ngăn kết nối mới được khởi tạo từ Internet đi vào qua gateway này. Nó có vai trò tương tự mục tiêu egress-only của NAT IPv4, nhưng không dịch địa chỉ IPv6 theo cách SNAT IPv4 thông thường.

Route table của subnet IPv6 riêng có thể có:

| Destination | Target | Ý nghĩa |
|---|---|---|
| Dải IPv6 của mạng ảo | local | Lưu lượng nội bộ |
| ::/0 | Egress-only gateway | Egress IPv6 ra Internet theo trạng thái kết nối |

Nếu nền tảng không có egress-only gateway, cần dùng firewall hoặc kiến trúc egress IPv6 tương đương và kiểm soát chặt security policy. Địa chỉ IPv6 global không nên được xem là an toàn chỉ vì máy không có IPv4 public.

Với môi trường IPv6-only cần gọi dịch vụ IPv4-only, có thể cần NAT64/DNS64 hoặc một gateway chuyển đổi tương đương nếu nền tảng hỗ trợ. Đây là một đường chuyển đổi riêng, không nên nhầm với NAT gateway SNAT IPv4 thông thường. Hãy xác nhận cả DNS, khả năng hỗ trợ giao thức và chính sách của đích.

## 8. Bảo mật kết nối đi ra

Kết nối đi ra cũng là một phần của bề mặt tấn công. Nếu máy bị xâm nhập, kẻ tấn công có thể tìm cách tải công cụ, gửi dữ liệu ra ngoài hoặc điều khiển máy qua một máy chủ từ xa. Do đó, egress cần được quản lý theo nguyên tắc tối thiểu.

### Giới hạn đích và cổng

- Chỉ cho phép workload gọi tới dịch vụ cần thiết, ví dụ HTTPS tới API hoặc registry đã phê duyệt.
- Ưu tiên private endpoint cho dịch vụ cloud có hỗ trợ.
- Dùng proxy hoặc firewall khi cần lọc domain, ghi nhận yêu cầu hoặc kiểm tra chính sách nâng cao.
- Tránh mở egress mọi giao thức tới mọi địa chỉ nếu workload chỉ cần một số đích cụ thể.
- Kiểm tra cả IPv4 và IPv6; chỉ khóa IPv4 nhưng để IPv6 mở rộng có thể tạo ra đường đi ngoài dự kiến.

Security group thường là bộ lọc stateful: khi kết nối đi ra được cho phép, phản hồi thuộc luồng đó thường được cho phép tự động. Network ACL thường là bộ lọc stateless ở cấp subnet; phải cho phép cả chiều đi và chiều về, bao gồm dải cổng nguồn tạm thời (ephemeral ports) mà hệ điều hành sử dụng.

Firewall stateful cũng theo dõi trạng thái kết nối. Nếu đường về đi qua một firewall khác hoặc không đi qua cùng trạng thái đã ghi nhận, kết nối có thể bị chặn. Thiết kế định tuyến bất đối xứng cần được xem xét kỹ khi dùng nhiều firewall hoặc NAT.

### Không nhầm NAT với kiểm soát truy cập

NAT che địa chỉ riêng và hỗ trợ nhiều máy dùng chung địa chỉ egress, nhưng không phải cơ chế xác thực ứng dụng. Một workload có thể gọi tới rất nhiều địa chỉ Internet qua NAT nếu firewall cho phép. Vẫn cần:

- TLS để bảo vệ dữ liệu trên đường truyền.
- Xác thực API và quản lý secret.
- IAM hoặc workload identity cho dịch vụ cloud.
- Egress policy, log và cảnh báo.
- Kiểm soát DNS và tránh để workload tự ý dùng resolver không được phê duyệt.

Nếu đối tác yêu cầu allowlist IP nguồn, cung cấp địa chỉ egress công cộng ổn định của NAT hoặc firewall. Không dùng IP riêng của máy ứng dụng vì phía đối tác không nhìn thấy địa chỉ đó qua Internet. Khi có nhiều NAT gateway hoặc nhiều vùng, cần cung cấp đầy đủ các IP egress có thể được sử dụng.

## 9. Tính sẵn sàng và mở rộng NAT

NAT nằm trên đường đi của mọi kết nối egress được định tuyến qua nó. Nếu NAT lỗi, quá tải hoặc mất kết nối tới Internet gateway, nhiều workload có thể cùng mất khả năng tải gói, gọi API hoặc gửi telemetry. Do đó, NAT là một thành phần hạ tầng cần thiết kế HA.

### Thiết kế theo zone

Nếu dịch vụ NAT có phạm vi theo zone, một mẫu thường dùng là tạo NAT gateway ở mỗi zone có workload và cấu hình subnet riêng trong zone đó đi tới NAT cùng zone. Điều này giảm phụ thuộc liên zone và có thể tránh một phần chi phí truyền dữ liệu chéo zone. Nếu NAT của một zone gặp sự cố, các workload ở zone khác vẫn có đường egress riêng.

Một route tập trung qua NAT ở một zone có thể tiết kiệm số gateway nhưng tạo điểm lỗi tập trung và tăng lưu lượng liên zone. Nếu chọn thiết kế tập trung, cần có cơ chế failover route, kiểm thử chuyển vùng và tính cả chi phí truyền dữ liệu.

Không phải mọi nhà cung cấp triển khai NAT theo cùng một mô hình. Có dịch vụ NAT mang tính regional hoặc tự xử lý tính sẵn sàng bên dưới. Hãy xác minh phạm vi lỗi, SLA, cách scale và cơ chế failover thực tế trước khi nhân bản gateway.

### Giới hạn kết nối và cổng nguồn

NAT/PAT dùng một tập hợp địa chỉ và cổng nguồn để phân biệt các luồng kết nối. Khi số lượng kết nối đồng thời tăng cao, một NAT có thể chạm giới hạn băng thông, số kết nối, tốc độ tạo kết nối hoặc cổng nguồn khả dụng.

Các dấu hiệu có thể gồm:

- Một số kết nối mới thất bại hoặc timeout trong khi kết nối hiện tại vẫn hoạt động.
- Lỗi tăng khi nhiều worker đồng thời gọi cùng một API.
- Tỷ lệ lỗi thay đổi theo đích hoặc theo thời điểm tải cao.
- Metric của NAT cho thấy số kết nối, số cổng hoặc lưu lượng gần giới hạn.

Biện pháp giảm tải:

- Tái sử dụng kết nối HTTP/TCP thay vì tạo kết nối mới cho từng yêu cầu.
- Dùng connection pooling và keep-alive phù hợp.
- Giảm retry đồng loạt; dùng exponential backoff và jitter để tránh tạo bão kết nối.
- Chia workload qua nhiều NAT hoặc nhiều địa chỉ egress nếu dịch vụ hỗ trợ và kiến trúc cho phép.
- Dùng private endpoint cho lưu lượng tới dịch vụ cloud phù hợp.
- Theo dõi số kết nối, lỗi port allocation, byte/packet và throughput.

Đừng tăng số NAT chỉ dựa trên suy đoán. Hãy đo giới hạn thực tế và xác định bottleneck là cổng nguồn, băng thông, CPU của NAT instance, firewall hay phía API đích.

## 10. Chi phí và lựa chọn đường egress

Chi phí egress có thể gồm phí theo giờ của NAT gateway, phí theo GB xử lý, phí truyền dữ liệu giữa zone, phí truyền dữ liệu ra Internet, chi phí firewall/proxy và chi phí vận hành. Mô hình giá khác nhau theo nhà cung cấp và region.

Một cách đánh giá là phân loại lưu lượng:

| Loại lưu lượng | Đường đi nên xem xét | Lý do |
|---|---|---|
| API công cộng của đối tác | NAT hoặc proxy egress | Cần địa chỉ nguồn ổn định và kiểm soát kết nối |
| Object storage cùng cloud | Private endpoint/service endpoint nếu có | Giảm phụ thuộc Internet và có thể giảm phí NAT |
| Container registry nội bộ | Private endpoint hoặc mạng riêng | Tránh gửi image qua đường Internet |
| Dịch vụ trong mạng ảo khác | Peering, transit gateway hoặc kết nối riêng | Định tuyến nội bộ có kiểm soát |
| Hệ thống tại trung tâm dữ liệu | VPN hoặc dedicated connection | Kết nối riêng và chính sách định tuyến hai chiều |
| Internet tổng quát | NAT gateway kết hợp firewall/proxy theo chính sách | Một điểm egress có thể quản lý tập trung |

Ví dụ, một nhóm worker tải 2 TB dữ liệu mỗi tháng từ object storage cùng region. Nếu mọi byte đều đi qua NAT, nhóm có thể phải trả phí xử lý NAT và có thể cả phí liên zone. Nếu dịch vụ hỗ trợ private endpoint và route/DNS được cấu hình đúng, lưu lượng có thể đi qua mạng riêng và giảm chi phí egress qua NAT. Cần kiểm tra biểu phí thực tế, vì private endpoint cũng có thể có phí theo giờ hoặc dữ liệu.

Tính cả chi phí gián tiếp: một NAT đơn lẻ làm giảm chi phí gateway nhưng tăng rủi ro downtime; nhiều NAT tăng chi phí cố định nhưng cải thiện cô lập lỗi. Quyết định cần dựa trên mức độ quan trọng của workload, lưu lượng thực tế và yêu cầu phục hồi.

## 11. Quy trình thiết kế egress cho workload riêng tư

Có thể sử dụng quy trình sau khi xây dựng mạng mới hoặc đưa một workload hiện có vào subnet riêng:

1. **Liệt kê đích cần truy cập.** Ghi rõ domain/IP, cổng, giao thức, vùng và mục đích nghiệp vụ. Tách dịch vụ cloud, mạng nội bộ và Internet công cộng.
2. **Phân loại luồng.** Xác định luồng nào cần Internet, luồng nào có private endpoint, peering, VPN hoặc dedicated connection.
3. **Chọn CIDR và topology.** Tránh dải địa chỉ chồng lấn; xác định subnet theo workload, zone và mức độ tin cậy.
4. **Thiết kế route table.** Thêm tuyến nội bộ cụ thể, tuyến tới mạng riêng và tuyến mặc định tới NAT/firewall/proxy phù hợp.
5. **Thiết kế bảo mật.** Giới hạn security group, network ACL, firewall, DNS và quyền ứng dụng theo nguyên tắc tối thiểu.
6. **Thiết kế HA và capacity.** Xác định phạm vi zone/region, số NAT, địa chỉ egress, giới hạn kết nối và phương án failover.
7. **Kiểm tra đường đi và đường về.** Xác minh NAT có tuyến tới Internet gateway; kiểm tra return route, ephemeral ports và stateful inspection.
8. **Quan sát và tối ưu.** Bật flow log, metric NAT/firewall, DNS log nếu phù hợp; theo dõi lưu lượng, lỗi và chi phí.

Checklist kiểm tra kiến trúc:

- [ ] Workload không cần IP công cộng và chỉ có địa chỉ riêng phù hợp.
- [ ] Route table của subnet riêng trỏ đúng NAT/firewall hoặc endpoint.
- [ ] NAT có đường ra Internet gateway hoặc upstream egress hợp lệ.
- [ ] Route cụ thể tới mạng nội bộ và private endpoint được ưu tiên đúng.
- [ ] Security group, network ACL và firewall cho phép đúng chiều đi và chiều về.
- [ ] DNS phân giải tên dịch vụ về đúng địa chỉ công cộng hoặc private endpoint.
- [ ] Có đủ địa chỉ egress ổn định cho allowlist của đối tác.
- [ ] Có thiết kế HA theo zone và capacity cho số kết nối dự kiến.
- [ ] Có log, metric, cảnh báo và ngân sách cho lưu lượng egress.
- [ ] IPv6 được kiểm soát tương đương IPv4 nếu đang bật.

## 12. Chẩn đoán khi máy riêng tư không kết nối được

Không nên bắt đầu bằng việc gán IP công cộng cho máy để thử nhanh. Cách đó có thể làm thay đổi bề mặt bảo mật và che mất nguyên nhân thực sự. Hãy kiểm tra theo từng lớp từ máy nguồn tới đích.

### Bước 1: Kiểm tra DNS

Xác minh tên miền có phân giải được không và trả về địa chỉ đúng với đường kết nối dự kiến. Nếu dùng private endpoint, DNS có thể cần private hosted zone hoặc resolver rule. Nếu tên miền trả về IP công cộng trong khi dự định đi private endpoint, lưu lượng có thể đi nhầm qua NAT.

Các lệnh chẩn đoán phổ biến:

~~~bash
dig api.example.com
getent hosts api.example.com
~~~

Tên miền và lệnh chỉ là ví dụ; hệ điều hành hoặc môi trường container có thể cung cấp công cụ DNS khác.

### Bước 2: Kiểm tra route trên máy và route table của subnet

Xác nhận máy có default route, gateway phù hợp và route table được liên kết đúng subnet. Kiểm tra tuyến tới địa chỉ đích có bị một prefix cụ thể hơn đưa sang peering, VPN hoặc firewall khác không.

~~~bash
ip route
ip route get 198.51.100.40
~~~

Lệnh thứ hai giúp xem kernel dự kiến gửi gói tới địa chỉ ví dụ qua interface và next hop nào. Route table trong hệ điều hành chỉ là một phần; vẫn cần kiểm tra route table của mạng ảo trên cloud.

### Bước 3: Kiểm tra chính sách bảo mật

Kiểm tra egress rule của security group, network ACL, firewall policy và firewall trên máy. Với ACL stateless, xác minh chiều về có cho phép ephemeral port hay không. Nếu có proxy, xác minh biến môi trường hoặc cấu hình proxy và quyền xác thực.

### Bước 4: Kiểm tra NAT và upstream

Xác nhận NAT gateway đang hoạt động, có địa chỉ egress, có tuyến tới Internet gateway và không chạm giới hạn kết nối. Nếu dùng NAT instance, kiểm tra IP forwarding, SNAT rule, connection tracking, CPU và network interface. Kiểm tra cả firewall hoặc gateway ở phía upstream.

### Bước 5: Kiểm tra kết nối TCP/TLS và phía đích

~~~bash
nc -vz api.example.com 443
curl -v --connect-timeout 5 https://api.example.com/health
~~~

Nếu TCP không thiết lập được, vấn đề có thể nằm ở route, firewall, NAT hoặc phía đích. Nếu TCP thành công nhưng TLS hoặc HTTP lỗi, hãy kiểm tra chứng chỉ, SNI, proxy, xác thực, allowlist và trạng thái dịch vụ. Một lệnh ping thất bại không đủ để kết luận đường mạng hỏng vì ICMP có thể bị chặn trong khi TCP vẫn hoạt động.

### Bước 6: Dùng log và metric để xác định điểm mất gói

Flow log ở cấp network interface/subnet, metric của NAT, firewall log, DNS query log và log ứng dụng giúp xác định lưu lượng bị từ chối ở đâu. Tìm theo thời điểm, IP nguồn riêng, IP đích, cổng và giao thức. Nếu phía đích chỉ thấy IP NAT, hãy đối chiếu thời điểm và cổng nguồn đã được dịch.

| Triệu chứng | Lớp cần kiểm tra trước |
|---|---|
| Không phân giải được tên miền | DNS resolver, private zone, outbound DNS |
| Có IP nhưng không có route phù hợp | Route table subnet, default route, next hop |
| TCP timeout tới mọi đích Internet | NAT, Internet gateway, firewall, route chiều về |
| Chỉ một API không truy cập được | Allowlist IP nguồn, firewall đích, DNS và chính sách API |
| Kết nối lỗi khi tải tăng cao | Giới hạn NAT, cổng nguồn, connection pool, băng thông |
| Truy cập private endpoint nhưng đi qua NAT | DNS private, route cụ thể, endpoint policy |
| IPv4 hoạt động nhưng IPv6 không hoặc ngược lại | Route ::/0, egress-only gateway, firewall và DNS AAAA |
| Kết nối mở được nhưng ứng dụng báo lỗi TLS | Chứng chỉ, thời gian hệ thống, SNI, proxy và TLS policy |

## 13. Ví dụ thực tế: worker riêng tư tải image và gọi API

Một hệ thống xử lý đơn hàng chạy 12 worker trong hai zone. Các worker không có IP công cộng. Chúng cần:

- Kéo container image từ registry của tổ chức.
- Đọc thông điệp từ queue và ghi kết quả vào database nội bộ.
- Gọi một API đối tác qua HTTPS.
- Gửi log và metric tới dịch vụ quan sát.

Nhóm có thể thiết kế đường đi như sau:

1. Queue, database và registry có hỗ trợ endpoint riêng được truy cập qua private endpoint hoặc mạng nội bộ.
2. Route table có các tuyến cụ thể tới các mạng riêng và endpoint.
3. Chỉ lưu lượng gọi API đối tác hoặc dịch vụ công cộng cần thiết mới đi qua NAT/proxy egress.
4. Mỗi zone có NAT riêng nếu dịch vụ NAT có phạm vi zone, route của worker ưu tiên NAT cùng zone.
5. Firewall cho phép HTTPS tới domain/IP đối tác đã được phê duyệt; security group chỉ cho phép egress cần thiết.
6. DNS private phân giải registry và các dịch vụ nội bộ tới endpoint riêng.
7. Log và metric theo dõi số kết nối, lỗi NAT, độ trễ API và chi phí egress.

Nếu đối tác yêu cầu allowlist IP nguồn, nhóm cung cấp các địa chỉ egress công cộng ổn định của NAT hoặc firewall ở cả hai zone. Khi một zone gặp sự cố và worker được chuyển sang zone khác, địa chỉ egress có thể thay đổi; vì vậy danh sách allowlist và quy trình failover cần tính tới tất cả IP có thể sử dụng.

Thiết kế này giữ worker ở mạng riêng, tránh đưa toàn bộ lưu lượng cloud nội bộ qua Internet và tập trung kiểm soát các kết nối công cộng thực sự cần thiết.

## 14. Những lỗi thiết kế thường gặp

1. **Chỉ thêm default route tới NAT:** NAT không có đường ra Internet gateway hoặc upstream nên kết nối vẫn thất bại.
2. **Đặt NAT trong subnet riêng:** NAT không có đường egress hợp lệ tới Internet gateway, tạo vòng định tuyến hoặc mất kết nối.
3. **Cho rằng NAT là firewall:** NAT không thay thế chính sách lọc đích, cổng, danh tính hoặc nội dung.
4. **Quên đường về:** ACL stateless hoặc firewall chặn ephemeral port/phản hồi, khiến kết nối TCP không hoàn tất.
5. **Dùng một NAT cho mọi zone mà không tính rủi ro:** tạo điểm lỗi tập trung và có thể phát sinh phí truyền dữ liệu liên zone.
6. **Bỏ qua DNS:** private endpoint tồn tại nhưng tên dịch vụ vẫn phân giải ra địa chỉ công cộng.
7. **Không tính giới hạn cổng nguồn:** quá nhiều kết nối ngắn có thể làm NAT cạn tài nguyên ánh xạ.
8. **Allowlist thiếu IP egress:** đối tác chỉ cho phép một NAT trong khi workload có thể đi ra qua nhiều NAT hoặc vùng.
9. **Chỉ kiểm soát IPv4:** IPv6 có thể tạo đường egress khác ngoài chính sách dự kiến.
10. **Dùng NAT cho mọi dịch vụ:** lưu lượng nội bộ hoặc dịch vụ cloud có private endpoint bị đưa qua NAT không cần thiết, làm tăng chi phí và độ trễ.

## 15. Bài tập vận dụng

Một ứng dụng chạy trong private subnet có CIDR 10.50.10.0/24. Mạng ảo có dải 10.50.0.0/16. Máy ứng dụng không có IP công cộng và cần gọi API đối tác qua HTTPS. Nhóm đã tạo NAT gateway trong public subnet 10.50.1.0/24 và gắn địa chỉ egress công cộng cho NAT.

1. Route table của private subnet cần có những tuyến nào để gửi lưu lượng nội bộ và lưu lượng Internet?
2. Public subnet và NAT gateway cần có đường đi nào để gói tin ra Internet?
3. Vì sao API đối tác nhìn thấy IP egress của NAT thay vì IP riêng của máy ứng dụng?
4. Nếu TCP timeout dù DNS phân giải đúng, hãy nêu ít nhất bốn lớp cần kiểm tra.
5. Nếu có hai zone và workload phải tiếp tục hoạt động khi một zone lỗi, cần thay đổi thiết kế NAT và allowlist như thế nào?
6. Nếu ứng dụng tải nhiều dữ liệu từ object storage cùng cloud, private endpoint có thể giúp ích ra sao?

Gợi ý: private subnet cần tuyến local cho 10.50.0.0/16 và tuyến mặc định 0.0.0.0/0 tới NAT. Public subnet cần tuyến mặc định tới Internet gateway; NAT cần hoạt động trong subnet đó và có địa chỉ egress công cộng. Khi mở rộng đa zone, xem xét NAT theo zone, route tương ứng và toàn bộ địa chỉ egress có thể dùng. Với object storage, kiểm tra private endpoint, DNS và endpoint policy trước khi định tuyến qua NAT.

## Kết luận

Workload không có IP công cộng vẫn có thể kết nối đi ra bằng cách định tuyến qua NAT, proxy, firewall hoặc private endpoint. Một thiết kế đáng tin cậy cần xác định đúng route table và next hop, hiểu ánh xạ NAT cùng đường phản hồi, giới hạn egress theo nhu cầu, quản lý DNS và IPv6, đồng thời bảo đảm HA và capacity. Khi sự cố xảy ra, hãy kiểm tra từng lớp từ DNS, route, chính sách bảo mật, NAT tới phía đích bằng log và metric để tìm đúng điểm gây lỗi.
