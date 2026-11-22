# Hub-and-spoke, mạng tập trung và mạng phân tán

Khi một ứng dụng cloud mở rộng từ vài dịch vụ thành nhiều môi trường, đội phát triển, tài khoản hoặc dự án, mạng không còn là một tập hợp subnet đơn giản. Kiến trúc sư phải quyết định **dịch vụ nào được kết nối với nhau, lưu lượng đi qua đâu, chính sách an ninh được áp dụng ở đâu và ai chịu trách nhiệm vận hành các kết nối đó**. Quyết định này ảnh hưởng trực tiếp đến hiệu năng, độ tin cậy, bảo mật, khả năng mở rộng và hóa đơn cloud.

Trong module **CLOUD_ARCHITECTURE**, bài học thuộc chương **Kiến trúc mạng** tập trung vào ba ý tưởng liên quan nhưng khác nhau: **hub-and-spoke** là mô hình kết nối, **mạng tập trung** là cách gom các chức năng và quyền quản trị mạng, còn **mạng phân tán** là cách đặt kết nối, kiểm soát và trách nhiệm gần từng workload. Không có một sơ đồ tối ưu cho mọi hệ thống. Cần chọn bằng chứng từ yêu cầu nghiệp vụ, luồng dữ liệu, chính sách bảo mật, tải thực tế và khả năng vận hành theo tư duy Well-Architected.

## 1. Ba khái niệm dễ bị đánh đồng

| Khái niệm | Bản chất | Ví dụ | Điều không nên suy ra |
| --- | --- | --- | --- |
| **Hub-and-spoke** | Hình thái kết nối: các mạng spoke kết nối đến một hub chung | Mỗi ứng dụng có một VPC/VNet, kết nối về một transit hub | Không có nghĩa mọi gói tin đều phải đi qua firewall ở hub |
| **Mạng tập trung (centralized networking)** | Các chức năng/quy tắc được quản lý tại một điểm hoặc nhóm dùng chung | Egress, DNS forwarding, firewall, hybrid connectivity do đội platform quản lý | Không nhất thiết mọi workload đặt chung một subnet hoặc tài khoản |
| **Mạng phân tán (distributed networking)** | Kết nối, điểm thực thi chính sách hoặc vận hành được phân bổ giữa nhiều mạng và khu vực | Mỗi workload có ingress/egress riêng, dùng private endpoints và chính sách cục bộ | Không đồng nghĩa thiếu quản trị, thiếu tiêu chuẩn hoặc phải tạo full mesh |

Hai trục quan trọng cần phân biệt là **topology kết nối** và **vị trí thực thi chính sách**. Một hệ thống hub-and-spoke có thể dùng hub để định tuyến liên mạng nhưng giữ firewall của từng workload. Ngược lại, một mạng nhiều điểm kết nối trực tiếp vẫn có thể được điều hành bằng chính sách bảo mật tập trung và hạ tầng tự động hóa chung.

### Các mục tiêu kiến trúc cần làm rõ

1. **Phân đoạn:** dữ liệu nhạy cảm, môi trường production và development có cần ranh giới riêng không?
2. **Khả năng kết nối:** workload nào cần trao đổi trực tiếp; mạng doanh nghiệp (on-premises) hoặc chi nhánh phải truy cập dịch vụ nào?
3. **Kiểm soát:** có bắt buộc kiểm tra gói tin, lưu audit, NAT hoặc áp dụng chính sách egress tập trung không?
4. **Độ trễ và băng thông:** có đường trao đổi lớn giữa các dịch vụ, availability zone (AZ) hoặc region không?
5. **Độ tin cậy:** mất hub, gateway hoặc đường hybrid sẽ làm gián đoạn hành trình nghiệp vụ nào?
6. **Chi phí và trách nhiệm:** chi phí truyền dữ liệu, gateway, kiểm tra lưu lượng, logging và vận hành được phân bổ ra sao?

Trước khi vẽ hub hoặc peering, nên lập **ma trận giao tiếp**: nguồn, đích, cổng/giao thức, tần suất, dữ liệu xử lý, yêu cầu bảo mật, độ trễ và chủ sở hữu. Đây là đầu vào cho định tuyến và firewall; một sơ đồ chỉ có những đường nối chưa đủ thể hiện chính sách.

## 2. Phân loại luồng lưu lượng để chọn đường đi

Các luồng khác nhau có yêu cầu khác nhau:

| Luồng | Đặc điểm | Câu hỏi cần quyết định |
| --- | --- | --- |
| **North–south ingress** | Từ Internet, đối tác hoặc người dùng vào ứng dụng | Endpoint công khai ở đâu? CDN/WAF/load balancer nào bảo vệ? |
| **North–south egress** | Từ ứng dụng ra Internet hoặc SaaS | Có cần IP nguồn cố định, NAT, lọc domain, logging hoặc proxy tập trung? |
| **East–west** | Giữa dịch vụ, subnet, spoke hoặc cluster | Định tuyến trực tiếp, qua hub hay qua private service endpoint? |
| **Hybrid** | Giữa cloud và mạng doanh nghiệp hoặc datacenter | VPN/kết nối chuyên dụng, BGP, phân giải DNS và đường dự phòng? |
| **Cross-region** | Sao chép dữ liệu, gọi API hoặc DR giữa các region | Độ trễ, phí truyền vùng, consistency, yêu cầu cư trú dữ liệu? |
| **Management/control** | CI/CD, giám sát, DNS, secrets, API quản trị | Ai được phép truy cập, audit và khả năng phục hồi của control plane? |

**Ingress không phải egress.** Internet-facing load balancer đưa người dùng vào API không thay thế được giải pháp NAT/proxy cho tiến trình ở subnet riêng cần gọi API ngoài. Cũng không nên bắt tất cả traffic giữa hai workload trong cùng VPC/VNet đi vòng qua hub nếu chúng đã có đường nội bộ được kiểm soát phù hợp.

Một quy trình phát hiện luồng hữu ích là lấy thông tin từ sơ đồ nghiệp vụ và tracing, đối chiếu với VPC/VNet flow logs hoặc công cụ quan sát mạng, rồi xác minh các kết nối thực sự cần. Lưu lượng không có lý do nghiệp vụ nên được đặt ở trạng thái **mặc định từ chối** theo chính sách áp dụng.

## 3. Những thành phần tạo nên kiến trúc mạng cloud

| Thành phần | Vai trò | Điểm kiểm tra quan trọng |
| --- | --- | --- |
| **VPC/VNet** | Không gian mạng logic cho workload | CIDR, subnet, route, DNS, cách cô lập môi trường/tài khoản |
| **Subnet và route table** | Xác định đường chuyển tiếp dựa trên địa chỉ đích | Đích rõ ràng, đường về, local route, route ưu tiên |
| **Peering** | Kết nối trực tiếp giữa các mạng theo điều kiện nhà cung cấp | Không giả định tự cung cấp transit tới mạng thứ ba |
| **Transit hub/router/gateway** | Kết nối nhiều mạng và định tuyến qua hệ thống dùng chung | Khả năng route propagation, phân đoạn, throughput và quota |
| **Firewall/inspection appliance** | Kiểm tra traffic theo chính sách network/application | Stateful flows, return path, HA, log, giới hạn xử lý |
| **NAT/proxy** | Kiểm soát nguồn/đích cho luồng đi ra | IP nguồn, số kết nối, giới hạn cổng, SNAT và chi phí |
| **DNS resolver/forwarder** | Phân giải tên dịch vụ private/public và tên hybrid | Split-horizon, cache, conditional forwarding, dự phòng |
| **Private endpoint/service connectivity** | Truy cập dịch vụ quản lý qua đường private theo khả năng nền tảng | Tên DNS, quyền truy cập endpoint, đường dữ liệu thực tế |
| **VPN/kết nối chuyên dụng** | Kết nối cloud với mạng bên ngoài | BGP/static route, băng thông, encryption, tuyến dự phòng |
| **WAF/CDN/load balancer** | Phân phối và bảo vệ luồng ứng dụng vào hệ thống | TLS, lớp 7, health check, nguồn IP khách, failover |
| **Network policy/security group/ACL** | Kiểm soát cho phép kết nối tại ranh giới cụ thể | Nguyên tắc tối thiểu, luật outbound, trạng thái kết nối |

Các cloud có tên tài nguyên và giới hạn khác nhau. Khi triển khai, cần kiểm tra chính xác **khả năng chuyển tiếp qua peering, quy tắc chọn route, việc route được quảng bá tự động, giới hạn kết nối và kiểu tính phí** của nhà cung cấp đã chọn. Một sơ đồ khái niệm không thể thay thế cấu hình route table và kiểm thử đường đi.

### Định tuyến khác bảo mật

**Route cho biết gói tin có thể đi đâu; policy quyết định gói tin có được đi hay không.** Tồn tại route giữa hai spoke không có nghĩa hai spoke được phép gọi mọi cổng. Ngược lại, firewall cho phép kết nối nhưng thiếu route khứ hồi thì traffic vẫn thất bại.

Phân đoạn thường áp dụng nhiều lớp: tách tài khoản/project và mạng, route domain, firewall, security group/network policy, xác thực dịch vụ, ủy quyền và mã hóa. Tránh xem firewall tại hub là lớp bảo vệ duy nhất cho dữ liệu nhạy cảm.

## 4. Hub-and-spoke hoạt động như thế nào?

Một **hub** tập trung kết nối dùng chung, các **spoke** chứa workload hoặc môi trường cần cách ly. Tùy nền tảng, hub có thể là VPC/VNet chia sẻ, một dịch vụ transit được quản lý, hoặc sự kết hợp của transit và các subnet dịch vụ mạng.

~~~mermaid
flowchart TB
    INTERNET["Internet / SaaS"]
    OFFICE["Mạng doanh nghiệp"]
    subgraph HUB["Hub mạng / tài khoản platform"]
        TRANSIT["Transit routing"]
        INSPECT["Firewall / inspection"]
        EGRESS["NAT / egress proxy"]
        DNS["Private DNS / resolver"]
        HYBRID["VPN / dedicated connectivity"]
    end
    subgraph SPK1["Spoke A — Catalog"]
        A["API và database"]
    end
    subgraph SPK2["Spoke B — Booking"]
        B["API và database"]
    end
    subgraph SPK3["Spoke C — Analytics"]
        C["Data workloads"]
    end
    A <--> TRANSIT
    B <--> TRANSIT
    C <--> TRANSIT
    TRANSIT <--> INSPECT
    INSPECT <--> EGRESS
    EGRESS <--> INTERNET
    TRANSIT <--> HYBRID
    HYBRID <--> OFFICE
    DNS --- TRANSIT
~~~

Sơ đồ mang tính logic: các đường từ spoke tới transit biểu thị **khả năng kết nối**, không ngụ ý tất cả các luồng đều phải qua inspection hoặc rằng DNS query luôn đi cùng đường packet dữ liệu. Người thiết kế phải chỉ rõ traffic class nào có route qua firewall, traffic nào được đi trực tiếp và traffic nào bị chặn.

### Hub thường cung cấp chức năng gì?

- **Kết nối:** một nơi tổng hợp các kết nối spoke, VPN và đường mạng doanh nghiệp.
- **Kiểm soát egress:** NAT, proxy, danh sách đích được phép và log cho workload đi ra Internet.
- **Inspection tập trung:** nếu chính sách yêu cầu, áp dụng firewall cho một số luồng spoke-to-spoke, hybrid hoặc Internet.
- **Dịch vụ dùng chung:** DNS resolver, endpoint dịch vụ, công cụ quản trị/quan sát nếu phù hợp.
- **Điểm quản trị routing:** tạo hoặc quảng bá route theo chính sách; phân tách route domain để tránh mọi mạng nhìn thấy nhau.

Hub có thể giảm số lượng kết nối và chuẩn hóa chính sách, nhưng cũng tạo **đường đi dài hơn**, phí xử lý qua gateway và khả năng ảnh hưởng nhiều workload khi tuyến chung lỗi. Cần phân tách **chức năng quản trị tập trung** với **điểm xử lý packet tập trung**: chính sách được điều hành từ một nơi vẫn có thể được thực thi bởi nhiều firewall/endpoint phân tán.

## 5. Luồng đi qua hub: route, đường về và inspection

Giả sử dùng dải private IPv4 minh họa:

| Mạng | CIDR | Chức năng |
| --- | --- | --- |
| Hub | 10.40.0.0/16 | Routing, firewall, DNS, egress |
| Spoke A | 10.41.0.0/16 | Catalog |
| Spoke B | 10.42.0.0/16 | Booking |
| Spoke C | 10.43.0.0/16 | Analytics |
| Mạng doanh nghiệp | 172.20.0.0/16 | Hệ thống on-premises |

Các CIDR này **không chồng lấn**; chúng chỉ là ví dụ cấu trúc địa chỉ, chưa thể hiện subnet thực tế và không tự áp dụng được cho mọi tài khoản cloud. Khi mở rộng cần dự trù chỗ cho subnet mới, mạng Kubernetes/pod, kết nối đối tác và địa chỉ phát sinh trong tương lai.

### 5.1. Spoke A gọi API nội bộ ở Spoke B

Giả sử chính sách quy định mọi kết nối giữa hai spoke phải được kiểm tra tại firewall:

1. Catalog trong Spoke A phân giải tên riêng của Booking ra IP private thuộc Spoke B.
2. Route từ Spoke A cho **10.42.0.0/16** đưa traffic tới hệ thống transit/hub.
3. Route ở hub chọn đường kiểm tra và firewall áp dụng chính sách **Catalog → Booking** trên đúng giao thức, cổng, nguồn/đích.
4. Sau khi được phép, hub chuyển packet tới Spoke B.
5. **Luồng trả lời** từ B về A phải đi qua đường có thể nhận diện state của kết nối hoặc qua cơ chế mà firewall hỗ trợ; nếu đường về đi tắt, firewall stateful có thể loại bỏ packet hoặc kết nối thất bại.

Định tuyến bất đối xứng (*asymmetric routing*) là lỗi hay gặp khi có nhiều AZ, nhiều route table hoặc nhiều firewall. Một luồng đi qua firewall ở AZ A nhưng gói trả lời đi qua firewall ở AZ B không chia sẻ trạng thái có thể lỗi dù mọi network ACL đều cho phép. Nếu dùng appliance stateful, phải thiết kế flow affinity, symmetric routing và HA theo cơ chế của nền tảng.

### 5.2. Spoke đi Internet qua egress tập trung

Trong mô hình egress tập trung, route cho đích Internet đưa packet từ spoke tới hub, rồi qua firewall/proxy và NAT ra ngoài. Lưu ý **NAT không mặc định là firewall ứng dụng**: NAT thay đổi địa chỉ/port theo cơ chế của nó; chính sách lọc domain, URL hoặc nội dung cần giải pháp tương ứng. Một egress IP cố định thường hữu ích cho allowlist của đối tác nhưng có thể tạo giới hạn cổng/kết nối nếu toàn bộ workload dùng chung một địa chỉ.

Đường egress không nên được ép qua hub đối với mọi đích một cách máy móc. Truy cập object storage, database được quản lý hoặc API nền tảng có thể sử dụng **private endpoint** tùy khả năng cloud; khi đó cần tách route, DNS và policy phù hợp để tránh đi vòng ra Internet.

### 5.3. Hybrid: Spoke tới hệ thống on-premises

Spoke có thể cần route **172.20.0.0/16** về hub rồi đi qua VPN hoặc kết nối chuyên dụng. Mạng on-premises cần route ngược cho dải spoke và chính sách firewall cho phép. Nếu dùng BGP, phải xem xét quảng bá prefix, lọc route, thứ tự ưu tiên và cơ chế dự phòng; sai route propagation có thể gây **blackhole** hoặc làm rò rỉ phạm vi kết nối ngoài dự kiến.

### Route table minh họa theo mục đích

| Nơi định tuyến | Đích | Đường xử lý mong muốn |
| --- | --- | --- |
| Spoke A | 10.42.0.0/16 | Transit/hub, có kiểm tra khi chính sách yêu cầu |
| Spoke A | 172.20.0.0/16 | Hub tới hybrid gateway |
| Spoke A | 0.0.0.0/0 | Hub egress nếu chọn central egress |
| Hub/transit | 10.41.0.0/16 | Kết nối tới Spoke A |
| Hub/transit | 10.42.0.0/16 | Kết nối tới Spoke B |
| Hub/transit | 172.20.0.0/16 | Kết nối hybrid |
| Hub egress | Internet | Firewall/proxy rồi NAT hoặc cơ chế public egress thích hợp |

Bảng chỉ thể hiện **ý đồ**, không phải lệnh cấu hình có thể sao chép. Phải xác minh route table cho từng subnet/attachment, route chiều về, ưu tiên route, việc chuyển tiếp qua thiết bị và giới hạn theo dịch vụ cloud cụ thể. Các dải nội bộ của VPC/VNet thường có tuyến local do nền tảng cung cấp; một default route không nên làm mất đường nội bộ hợp lệ.

## 6. Mạng tập trung: lợi ích và giới hạn

**Centralized networking** thường có một đội platform/network sở hữu hệ thống routing, kết nối on-premises, firewall, egress, DNS forwarding và tiêu chuẩn kết nối của các tài khoản/dự án. Mỗi đội ứng dụng triển khai workload trong spoke hoặc vùng mạng được phân quyền, sử dụng các chính sách đã được thống nhất.

Ưu điểm:

- **Nhất quán chính sách:** các luồng nhạy cảm có thể được áp dụng bộ quy tắc kiểm soát và lưu nhật ký thống nhất.
- **Quản lý hybrid thuận tiện:** thay vì mỗi VPC/VNet tạo một đường VPN riêng tới datacenter, hub tập hợp các kết nối và công bố route theo phạm vi được phép.
- **Tái sử dụng dịch vụ mạng:** một hệ thống phân giải tên, kiểm tra traffic, IP egress hoặc cơ chế quan sát chung có thể phục vụ nhiều spoke.
- **Thêm mạng theo mẫu:** đội platform cung cấp quy trình đăng ký CIDR, gắn attachment, cấp policy và kiểm thử kết nối.
- **Phân trách nhiệm:** nhóm ứng dụng chịu trách nhiệm service và security rule cục bộ; nhóm platform quản trị cấu trúc routing, kết nối ngoài và guardrail.

Giới hạn cần đánh giá:

- **Tập trung lỗi:** một thay đổi route hoặc firewall chung có thể ảnh hưởng nhiều sản phẩm; hub cần HA thực tế và quy trình thay đổi nghiêm ngặt.
- **Tắc nghẽn hoặc hairpin:** lưu lượng giữa hai spoke ở cùng khu vực có thể bị ép qua nhiều thiết bị, tăng latency và phí xử lý.
- **Quy trình thay đổi chậm:** nếu mọi yêu cầu mở cổng đều chờ một đội duyệt thủ công, team ứng dụng bị phụ thuộc về lịch triển khai.
- **Khó phân bổ chi phí:** gateway/inspection/egress dùng chung cần cơ chế phân bổ byte hoặc workload để tránh chi phí “vô chủ”.
- **Khó mở rộng một điểm xử lý:** throughput firewall, số tunnel, phiên đồng thời, port NAT và route entries có giới hạn, kể cả khi dịch vụ transit được quản lý scale theo thiết kế.

**Quản trị tập trung không có nghĩa sử dụng một instance firewall duy nhất.** Một thiết kế tập trung có thể cần nhiều AZ, nhiều instance/appliance, cấu hình đồng bộ và đường failover để tránh single point of failure.

## 7. Mạng phân tán: kiểm soát gần workload và quyền tự chủ

**Distributed networking** đặt các chức năng hoặc cơ chế thực thi kết nối gần nơi phát sinh traffic. Từng workload có thể quản lý subnet, ingress, egress, private endpoint, network policy, firewall cục bộ và lifecycle của mình trong giới hạn tiêu chuẩn chung.

~~~mermaid
flowchart TB
    POLICY["Guardrail chung: IAM / policy / IaC / audit"]
    subgraph RA["Mạng workload A"]
        A["API A"]
        EA["Egress / inspection A"]
    end
    subgraph RB["Mạng workload B"]
        B["API B"]
        EB["Egress / inspection B"]
    end
    subgraph RC["Mạng workload C"]
        C["API C"]
        EC["Egress / inspection C"]
    end
    A --> EA
    B --> EB
    C --> EC
    POLICY -.-> EA
    POLICY -.-> EB
    POLICY -.-> EC
    A <-->|"Kết nối riêng có kiểm soát"| B
    B <-->|"Kết nối riêng có kiểm soát"| C
~~~

Lưu ý: đây là minh họa **phân tán điểm thực thi**, không phải khuyến nghị tạo peering full mesh. Kết nối giữa các mạng có thể sử dụng private service connectivity, transit theo khu vực, service networking hoặc các phương thức được quản lý; mỗi đường đều cần route và policy.

Ưu điểm:

- **Đường đi ngắn hơn cho một số luồng:** tránh vòng qua firewall/transit khi workload và chính sách cho phép kết nối riêng trực tiếp.
- **Giảm blast radius của thiết bị mạng dùng chung:** sự cố egress của ứng dụng A ít ảnh hưởng hơn tới B nếu hai phần có tài nguyên và chính sách độc lập.
- **Tự chủ release:** đội ứng dụng có thể thay đổi policy triển khai cùng ứng dụng thông qua quy trình đã kiểm thử.
- **Lựa chọn kiểm soát phù hợp dữ liệu:** dịch vụ nhạy cảm có cơ chế xác thực, network policy và giám sát chi tiết ngay tại ranh giới của nó.

Giới hạn:

- **Nguy cơ không nhất quán:** nếu mỗi team dùng quy tắc riêng, dễ thiếu logging, cấu hình TLS hoặc kiểm soát egress.
- **Nhiều tài nguyên lặp:** NAT, firewall, gateway và đường kết nối cục bộ có thể làm tăng chi phí cố định.
- **Khó nhìn toàn cục:** routing, log và sự cố trải trên nhiều dự án; cần inventory và observability tập trung.
- **Dễ tạo mạng chồng chéo:** nhiều team độc lập chọn CIDR, DNS zone hoặc IP đích giống nhau có thể làm kết nối về sau khó xử lý.
- **Quản lý giao tiếp chéo phức tạp:** kết nối nhiều-mạng-với-nhiều-mạng nếu dùng peering điểm-điểm tăng nhanh và khó duy trì ma trận quyền.

**Distributed không phải unrestricted.** Một lựa chọn là giữ tập trung *policy definition, identity, asset inventory và kiểm toán*, trong khi *policy enforcement và data path* có thể phân tán. Đây thường là mô hình lai hữu ích.

## 8. Hub-and-spoke so với kết nối trực tiếp hoặc mô hình lai

| Tiêu chí | Hub-and-spoke có kiểm soát tập trung | Kết nối riêng trực tiếp/phân tán | Mô hình lai chọn lọc |
| --- | --- | --- | --- |
| Độ phức tạp tuyến ở quy mô nhiều mạng | Các spoke kết nối về hub, quản lý route domain rõ hơn | Peering từng cặp có thể tăng nhanh | Giữ transit cho phần lớn kết nối, cho phép đường riêng cần thiết |
| Độ trễ east–west | Có thể tăng nếu hairpin qua inspection | Thường ngắn hơn khi cùng khu vực và có tuyến trực tiếp | Đường nóng được tối ưu, luồng nhạy cảm được kiểm tra |
| Bảo mật | Dễ áp dụng chính sách chung ở điểm kiểm tra | Cần guardrail bảo đảm đồng nhất giữa team | Chính sách chung, thực thi phù hợp loại dữ liệu |
| Phạm vi ảnh hưởng sự cố | Hub hoặc route chung có blast radius lớn | Lỗi từng mạng thường cô lập hơn, nhưng phụ thuộc chéo vẫn tồn tại | Cô lập traffic quan trọng, HA cho các dịch vụ dùng chung |
| Vận hành | Một đội sở hữu routing/inspection; đổi cấu hình có thể ảnh hưởng nhiều team | Đội workload chủ động nhưng cần năng lực network/security | Chia rõ trách nhiệm và sử dụng automation |
| Chi phí | Gateway/inspection tập trung, có phí xử lý và trung chuyển | Tài nguyên có thể lặp, phí liên mạng trực tiếp | Chọn theo phân bố byte và tải thực |
| Hybrid/on-premises | Thuận lợi khi dùng vài gateway/tuyến tập trung | Nhiều đường/kết nối độc lập có thể tốn kém | Hybrid qua hub, một số luồng chuyên biệt có đường riêng |

Đây là đánh giá **định tính**. Hiệu năng và chi phí thực tế phụ thuộc sản phẩm transit, kiểu attachment, mức HA, cloud provider, AZ/region và nơi traffic được tính phí. Phải dùng các phép đo và bảng giá áp dụng cho cấu hình đang đề xuất.

### Cần tránh mô hình full mesh theo quán tính

Với \(n\) mạng cần kết nối trực tiếp từng cặp, số cạnh kết nối lý thuyết là:

\[
\frac{n(n-1)}{2}.
\]

Ví dụ **12 mạng** có thể đòi tới **66** kết nối cặp nếu tất cả phải peering với nhau. Trong hub-and-spoke đơn giản, 12 spoke cần 12 attachment vào hub, mặc dù nội bộ hub còn có route table, phân đoạn, gateway, kiểm tra và các chi phí khác. So sánh số cạnh chỉ giúp thấy áp lực quản trị; **không chứng minh hub rẻ hơn** khi traffic có khối lượng lớn.

Với một số luồng có thông lượng cao, đường truyền trực tiếp được kiểm soát có thể tốt hơn, ví dụ dịch vụ tính toán và kho dữ liệu trong cùng region. Ngược lại, luồng nhạy cảm như mạng phân tích truy cập dữ liệu thanh toán có thể phải đi qua điểm kiểm soát hoặc bị chặn hoàn toàn tùy chính sách.

## 9. Chính sách bảo mật: tách kết nối khỏi quyền được truy cập

Hub-and-spoke chỉ cung cấp cấu trúc. Kiến trúc bảo mật cần xác định **ai được phép kết nối đến đâu, bằng chứng gì chứng minh danh tính và dữ liệu nào được phép trao đổi**.

Một mô hình kiểm soát nhiều lớp:

1. **Phân vùng tài khoản và môi trường:** production, staging, development, workload chứa dữ liệu nhạy cảm có ranh giới riêng; một đội không mặc nhiên được quyền chỉnh route/policy toàn bộ.
2. **Phân đoạn mạng:** route domain và firewall giới hạn khả năng di chuyển ngang; route tồn tại chỉ phục vụ những kết nối thực sự cần.
3. **Lọc ở nguồn và đích:** network policy/security group cho đúng cổng, giao thức, nhóm dịch vụ; không dựa hoàn toàn vào firewall hub.
4. **Định danh và mã hóa ứng dụng:** mTLS/TLS, IAM và ủy quyền theo service hoặc workload identity, tránh tin mọi IP private.
5. **Kiểm soát egress:** giới hạn domain/service đích khi có thể, theo dõi truy cập bất thường, giữ secret ngoài mã nguồn và tránh egress Internet không cần thiết.
6. **Quan sát và audit:** flow logs, firewall decision logs, DNS query logs, cấu hình route và policy thay đổi; bảo vệ thông tin nhạy cảm trong log.
7. **Quy trình phát hành:** infrastructure as code (IaC), review, policy-as-code, kiểm thử route và kiểm tra drift.

### Ví dụ ma trận truy cập

| Nguồn | Đích | Mục đích | Chính sách minh họa |
| --- | --- | --- | --- |
| Catalog API | Booking API | Đọc thông tin trạng thái cần thiết | Chỉ cho phép HTTPS từ workload identity đã xác thực |
| Analytics | Booking database primary | Truy vấn trực tiếp dữ liệu giao dịch | **Từ chối**; cung cấp dataset/projection được kiểm soát |
| Booking | Cổng thanh toán | Gửi lệnh thanh toán | Egress đến endpoint được phép, TLS, secret quản lý tập trung |
| CI/CD agent | Workload production | Triển khai được ủy quyền | Quyền triển khai tối thiểu, audit và identity ngắn hạn |
| Internet | Database subnet | Kết nối thẳng | **Từ chối**; chỉ expose application ingress cần thiết |

Không nên dùng một địa chỉ egress NAT chung làm cơ chế **xác thực** giữa các dịch vụ: nhiều workload có thể cùng xuất hiện sau một IP. Phân quyền vẫn phải dựa trên danh tính ứng dụng và hợp đồng bảo mật.

### DNS và private endpoint là phần của chính sách mạng

Một hostname private có thể phân giải khác nhau bên trong từng spoke hoặc từ on-premises; cần quyết định **ai sở hữu DNS zone, vùng nào nhận bản ghi, quyền sửa bản ghi, thời gian cache và tuyến forward**. Với private endpoint, việc kết nối đến IP private có thể phụ thuộc cả vào private DNS, routing và chính sách tài nguyên được quản lý. Nếu DNS trả về IP public khi ứng dụng dự định đi private, policy firewall đúng vẫn không bảo đảm đường dữ liệu mong muốn.

Một lỗi DNS hoặc resolver dùng chung có thể làm nhiều dịch vụ mất khả năng tìm thấy nhau dù kết nối IP vẫn hoạt động. Cần dự phòng resolver, kiểm thử conditional forwarding và giám sát cả thời gian phân giải lẫn thất bại DNS.

## 10. Chi phí, độ trễ và thông lượng: phải xem đúng đường packet

Đường đi dài hơn có thể phát sinh **phí xử lý trên transit/inspection, phí truyền dữ liệu giữa AZ hoặc region, NAT, egress Internet và vận hành hệ thống chung**. Không thể ước lượng chỉ từ tổng GB/tháng vì các luồng đi qua các thiết bị và ranh giới tính phí khác nhau.

Một bảng phân loại chi phí cần ghi:

| Hạng mục | Khối lượng cần đo | Câu hỏi khi dự toán |
| --- | --- | --- |
| Transit/gateway attachment | Số attachment, thời gian duy trì, byte qua gateway | Mỗi hướng hoặc mỗi dịch vụ có cách tính phí khác nhau không? |
| Firewall/inspection | Số endpoint/instance, giờ hoạt động, byte xử lý | Traffic qua bao nhiêu điểm kiểm tra và bao nhiêu AZ? |
| NAT/proxy | Giờ hoạt động, byte và số kết nối | Có xử lý hết traffic Internet và cả service cloud qua NAT không? |
| Inter-AZ/inter-region | Byte giữa vùng và vị trí nguồn/đích | Có luồng đi vòng qua AZ khác hoặc giữa region không? |
| Egress Internet | Byte đi ra theo đích/vùng/tier | Có CDN cache hoặc nén làm giảm lượng dữ liệu nguồn không? |
| VPN/kết nối chuyên dụng | Đường kết nối, băng thông, port/hạ tầng, transfer | Có cần dự phòng và có nghẽn ở đường doanh nghiệp không? |
| DNS/logging | Query, dung lượng log, thời hạn lưu | Flow logs và firewall logs tạo bao nhiêu dữ liệu và chi phí? |

### Ví dụ tính thông lượng cần kiểm tra

Giả sử Catalog gọi Booking với **5.000 request/giây** ở giờ cao điểm; mỗi request có payload gửi trung bình **10 KB** và response **60 KB** (1 KB = 1.000 byte). Chỉ riêng payload ứng dụng của cả hai chiều:

\[
5.000 \times (10.000+60.000)\times 8
= 2.800.000.000\ \text{bit/s}\approx2{,}8\ \text{Gb/s}.
\]

Đây là lưu lượng tổng hai chiều qua một điểm trên đường đi, **chưa tính TLS/HTTP/IP overhead, tăng đột biến, retry và replication**. Nếu request và response đều qua một firewall trong hub, cần kiểm tra băng thông thực tế và số phiên đồng thời của firewall tại tải đó. Nếu luồng bị xử lý bởi hai dịch vụ gateway/inspection, byte tính phí của từng dịch vụ có thể khác nhau; không nên tùy tiện nhân đôi băng thông vật lý hay khoản phí khi chưa xác định cơ chế đo.

Nếu 2,8 Gb/s chỉ xuất hiện trong 10 phút, hóa đơn phải dự báo theo **phân bố traffic theo thời gian**. Ngược lại, việc chọn thiết bị đủ công suất phải xét **đỉnh trong cửa sổ ngắn**, không dựa vào trung bình 30 ngày.

### Độ trễ và nút thắt

Tổng độ trễ luồng gồm xử lý ứng dụng, đi qua mạng, gateway, inspection và queue. Một hub trong cùng region không tự tạo độ trễ lớn, nhưng nhiều đoạn inspection hoặc đi qua AZ khác có thể ảnh hưởng các hành trình có SLO rất thấp. Cần đo **p50/p95/p99**, TCP connection setup, tỉ lệ timeout và thời gian khi failover.

Hiệu năng còn phụ thuộc giới hạn **gói tin/giây, phiên đồng thời, số cổng NAT, throughput theo AZ, DNS query rate và giới hạn attachment/route**. Một firewall có băng thông lý thuyết cao chưa chắc xử lý tốt hàng triệu kết nối ngắn với nhiều quy tắc kiểm tra lớp 7.

## 11. Độ tin cậy: hub không được trở thành điểm lỗi duy nhất

Khi nhiều workload phụ thuộc vào một hub, một lỗi routing hoặc firewall có thể gây ảnh hưởng lớn hơn lỗi ở một spoke riêng lẻ. Thiết kế độ tin cậy phải xem xét **data plane** (packet đang được chuyển) và **control plane** (nơi thay đổi route, chính sách, kết nối) theo khả năng và giới hạn của dịch vụ đã chọn.

| Sự cố | Hệ quả có thể xảy ra | Biện pháp và phép thử |
| --- | --- | --- |
| Một firewall instance chết | Luồng mới và luồng đang mở có thể lỗi | HA theo nhiều AZ, health check, route failover, kiểm tra giữ/mất session |
| Một AZ mất kết nối | Đường inspection hoặc NAT tại AZ đó không dùng được | Mỗi AZ có năng lực cần thiết, route/flow affinity đúng, thử failover dưới tải |
| Transit/gateway chung suy giảm | Nhiều spoke mất đường liên lạc | Theo dõi SLI, quota, rate limit, xác định đường tránh khi được hỗ trợ |
| Route propagation sai | Traffic đi sai đích hoặc bị blackhole | Quản lý route bằng IaC, policy kiểm tra, canary và rollback |
| DNS resolver tập trung lỗi | Ứng dụng không tìm được dịch vụ | Resolver dự phòng, phân vùng failure domain, monitor DNS |
| NAT cạn cổng hoặc connection | Kết nối mới ra ngoài không thành công | Theo dõi connection/port exhaustion, phân chia egress IP hoặc NAT theo workload |
| VPN hoặc đường riêng hỏng | Hybrid mất kết nối | Nhiều tunnel, nhiều kết nối/thiết bị khi cần; kiểm thử route failover |
| Sai chính sách firewall diện rộng | Nhiều hành trình lỗi cùng lúc | Review, kiểm thử, staged rollout, drift detection, rollback an toàn |

### Phân phối chức năng theo AZ

Nếu dùng firewall stateful trong nhiều AZ, phải kiểm tra **cách dịch vụ transit chọn AZ cho packet**. Hai điều kiện cùng quan trọng:

1. Traffic đi và về của một phiên phải tuân thủ các yêu cầu statefulness, thường cần **đường đối xứng** hoặc cơ chế đồng bộ/ghim flow được nền tảng hỗ trợ.
2. Khi mất một AZ, phần còn lại phải **đủ công suất thực tế** chứ không chỉ còn một endpoint khỏe.

Đối với NAT, phương án egress trong cùng AZ có thể tránh một số luồng chuyển AZ và giảm phụ thuộc, nhưng tăng số tài nguyên phải quản trị. Nếu egress tập trung ở hai AZ nhưng một AZ đang gánh phần lớn traffic, cần đo tình huống mất AZ lớn nhất và việc các đường còn lại sẽ gánh bao nhiêu tải.

### Mục tiêu phục hồi theo luồng nghiệp vụ

Một firewall failover “xong trong 30 giây” không có nghĩa booking phục hồi trong 30 giây. TCP connection cũ có thể bị reset; client và application connection pool cần reconnect; DNS cache hoặc proxy có thể giữ tuyến cũ. SLI nên đo ở góc nhìn **API, request thành công và latency** của hành trình thực, song song với metric thiết bị mạng.

Nếu mạng giữa hai spoke bị cắt, có thể dùng cơ chế retry có giới hạn, hàng đợi cho tác vụ không đồng bộ và giảm cấp chức năng. Tuy nhiên **không được mở rộng firewall allow rule bừa bãi** để “cứu” kết nối; điều đó phá vỡ chính sách bảo mật và có thể làm phạm vi sự cố lớn hơn.

## 12. Thiết kế nhiều region: hub theo khu vực hay hub toàn cục?

Trong hệ thống phục vụ nhiều region, việc đưa tất cả traffic về **một region duy nhất** để kiểm tra có thể tạo độ trễ, phí truyền dữ liệu liên vùng và phụ thuộc vào vùng trung tâm. Một phương án thường được xem xét là **hub theo region**, với bộ tiêu chuẩn và cơ chế kiểm soát chung nhưng có khả năng xử lý traffic cục bộ.

~~~mermaid
flowchart LR
    subgraph R1["Region 1"]
        HUB1["Regional hub 1"]
        APP1["Application spoke"]
        DATA1["Data spoke"]
        APP1 <--> HUB1
        DATA1 <--> HUB1
    end
    subgraph R2["Region 2"]
        HUB2["Regional hub 2"]
        APP2["Application / DR spoke"]
        DATA2["Data / DR spoke"]
        APP2 <--> HUB2
        DATA2 <--> HUB2
    end
    HUB1 <-->|"Liên vùng được kiểm soát"| HUB2
    POLICY["Policy-as-code / audit / inventory"]
    POLICY -.-> HUB1
    POLICY -.-> HUB2
~~~

Đường liên vùng giữa các hub là **khả năng kết nối có điều kiện**, không phải yêu cầu luôn có toàn quyền qua lại. Cần phân biệt luồng sao chép dữ liệu, quản trị, DR và lời gọi API; chỉ cho phép các prefix và service cần thiết.

### Các quyết định then chốt

- **Locality:** người dùng và ứng dụng ở region nào; có cần đi qua region khác cho request hằng ngày không?
- **Dữ liệu:** dữ liệu nào được phép sao chép liên vùng, mức trễ chấp nhận, encryption và RPO/RTO?
- **Nối mạng giữa các vùng:** chọn kỹ thuật được nền tảng hỗ trợ, định tuyến dự phòng, route filtering và giới hạn hop.
- **Sự cố mất region:** các ứng dụng còn sống có truy cập độc lập tới DNS, identity, secrets, egress và database của region dự phòng không?
- **Khả năng quản trị khi control plane lỗi:** nếu không tạo được route mới hoặc không cập nhật được tài nguyên tại vùng lỗi, hệ thống đã có sẵn cấu hình cần để tiếp tục phục vụ chưa?
- **Failback:** khi region chính trở lại, tránh hai bên cùng tiếp nhận dữ liệu không nhất quán hoặc cùng quảng bá prefix gây thay đổi đường đi bất ngờ.

Không phải hệ thống nào cũng cần multi-region active-active. Nếu mục tiêu RTO/RPO cho phép, backup/restore hoặc warm standby có thể đáp ứng với chi phí thấp hơn. Đánh giá lựa chọn theo **hành trình nghiệp vụ** và loại sự cố thay vì chỉ theo số vùng được nối trên sơ đồ.

## 13. Thiết kế theo quy trình: từ yêu cầu tới route và policy

Một cách thực hiện có kiểm soát:

### Bước 1 — Xác định phạm vi và môi trường

Liệt kê tenant, tài khoản/project, production/staging, khu vực triển khai, vùng dữ liệu nhạy cảm, người dùng Internet, mạng doanh nghiệp và đối tác. Ghi rõ ai sở hữu thay đổi và ngân sách chi phí. Nếu có nhiều đội, thống nhất ai quản trị hub, ai quản trị spoke, ai duyệt policy.

### Bước 2 — Lập ma trận luồng giao tiếp

Với từng nguồn/đích ghi **giao thức, cổng, hướng khởi tạo, dữ liệu truyền, throughput dự kiến, latency SLO, tần suất, mức độ nhạy cảm và đường fallback**. Tách các luồng API nội bộ, public ingress, Internet egress, hybrid và sao chép liên vùng.

### Bước 3 — Lập kế hoạch địa chỉ và tên miền

Chọn các CIDR không chồng lấn; dự trù tăng trưởng, networking cho container/pod, VPN/đối tác và vùng mới. Ghi rõ mô hình DNS private, conditional forwarding, ai sở hữu zone và cơ chế khôi phục. Không giả định có thể sửa CIDR đã dùng rộng rãi mà không gián đoạn.

### Bước 4 — Chọn topology và ranh giới policy

Xác định nơi cần transit, inspection, NAT, private endpoint và direct connectivity. Có thể chọn hub cho hybrid, governance và egress, nhưng giữ traffic hiệu năng cao ở đường riêng được phép. Tách route domain cho vùng ít tin cậy hơn và deny mặc định với kết nối không có nhu cầu.

### Bước 5 — Thiết kế route hai chiều và xử lý lỗi

Vẽ đường **request và response** của từng luồng quan trọng, kèm AZ, firewall, NAT, DNS và các trạng thái khi mất một thành phần. Xác minh cách peering/transit hoạt động với dịch vụ cloud thực tế, không suy đoán transit tự động hoặc khả năng forwarding qua appliance.

### Bước 6 — Định lượng hiệu năng, chi phí và khả năng mở rộng

Đo GB/ngày theo đường đi, RPS, packet rate, flow concurrent, connection setup, p95/p99, băng thông cao điểm, byte inter-AZ và inter-region. Ước lượng chi phí transit, firewall, NAT, egress, kết nối hybrid, DNS và log. Đặt giới hạn quota và kế hoạch nâng công suất.

### Bước 7 — Tự động hóa và kiểm thử

Sử dụng IaC với quy trình review, kiểm tra cấu hình route/policy trước khi rollout, kiểm tra kết nối giữa các spoke và kiểm thử chặn truy cập sai quyền. Canary một nhóm kết nối trước khi áp thay đổi mạng diện rộng. Giữ baseline về latency, lỗi, byte xử lý và DNS để đánh giá kết quả.

### Bước 8 — Vận hành và định kỳ xem lại kiến trúc

Dashboard cần hiển thị trạng thái attachment/tunnel, route changes, lưu lượng, packet drop, firewall deny, NAT exhaustion, DNS failure và chi phí theo nguồn. Có runbook cho mất AZ, sai route, firewall quá tải, VPN flap và phục hồi connectivity. Khi xuất hiện workload mới hoặc luồng east–west tăng đột biến, xem lại giả định ban đầu.

~~~mermaid
flowchart LR
    REQ["Yêu cầu nghiệp vụ + SLO"]
    MATRIX["Ma trận traffic + dữ liệu"]
    TOPO["Topology + route + policy"]
    TEST["Kiểm thử kết nối và lỗi"]
    OBS["Đo hiệu năng, chi phí, rủi ro"]
    REQ --> MATRIX --> TOPO --> TEST --> OBS
    OBS --> MATRIX
~~~

## 14. Case study: nền tảng đặt lịch với nhiều môi trường và kết nối hybrid

Giả sử một công ty có ba nhóm workload:

- **Catalog:** API đọc nhiều, CDN cache; ảnh được lưu object storage.
- **Booking/Payment:** giao dịch chứa dữ liệu nhạy cảm; phải kiểm soát truy cập và egress tới cổng thanh toán.
- **Analytics:** xử lý dữ liệu theo lô, cần dataset được chọn lọc từ Booking và phải truy cập một số dịch vụ trong datacenter.

Hệ thống có nhiều đội phát triển, vùng production/staging riêng và một mạng on-premises 172.20.0.0/16. Đội security muốn có kiểm toán egress và kiểm soát hybrid, còn đội sản phẩm cần giảm độ trễ Catalog → Booking. Dữ liệu giao dịch không được truy cập trực tiếp bởi toàn bộ workload phân tích.

### Phương án A — Mọi thứ qua hub với inspection tập trung

Toàn bộ spoke kết nối tới hub; liên spoke, egress và hybrid đều được kiểm tra. Ưu điểm là một điểm quan sát và thực thi policy rõ ràng. Nhược điểm có thể là **hairpin Catalog ↔ Booking** làm tăng byte qua gateway và tạo phụ thuộc vào hạ tầng chung, trong khi phần lớn traffic này thực chất không cần cùng mức inspection với đường vào hệ thống thanh toán.

Phương án A có thể phù hợp nếu yêu cầu kiểm soát tập trung nghiêm ngặt và tải cho phép. Nhưng phải chứng minh **throughput, latency, failure handling và hóa đơn**. Nếu kiểm tra lưu lượng east–west nhiều GB/ngày, thiết kế này có thể đắt và khó mở rộng hơn dự kiến.

### Phương án B — Mọi workload dùng kết nối và egress riêng

Catalog, Booking và Analytics tự quản lý private endpoint, NAT, policy và kết nối. Có thể giảm phụ thuộc hub, đường đi ngắn hơn cho các cặp có traffic lớn. Đổi lại, mỗi nhóm phải tự giải quyết guardrail, audit, DNS, CIDR, quota và khả năng chịu lỗi. Nếu Analytics tự tạo đường truy cập trực tiếp database Booking, yêu cầu bảo mật và quyền sở hữu dữ liệu có nguy cơ bị vi phạm.

Phương án B phù hợp hơn khi có đội ngũ vận hành trưởng thành, chính sách tự động hóa nhất quán và lý do thực tế cho sự độc lập của từng network domain.

### Phương án C — Kết hợp hub với kiểm soát phân tán

Một hướng thiết kế:

1. **Hub dùng chung** cung cấp routing hybrid, conditional DNS forwarding, inventory, kết nối on-premises và egress của các workload phải kiểm tra tập trung.
2. **Booking** nằm trong spoke production riêng, kiểm soát inbound từ Catalog và egress tới cổng thanh toán; dùng workload identity, TLS và policy ở gần ứng dụng.
3. **Catalog** phục vụ người dùng qua CDN/WAF/ingress phù hợp; một số kết nối nội bộ có thể dùng private service connectivity không hairpin nếu nền tảng hỗ trợ và chính sách cho phép.
4. **Analytics** không truy cập database giao dịch trực tiếp; nhận dữ liệu qua event/export được kiểm soát hoặc API phục vụ mục đích phân tích.
5. **Staging** nằm trong route domain riêng, không tự có kết nối production. Đường vào quản trị đi qua hệ thống kiểm soát danh tính và audit.
6. **Đội platform** cung cấp mẫu IaC, quản trị địa chỉ, policy-as-code và dashboard tập trung, trong khi từng đội chịu trách nhiệm các rule và tài nguyên của workload mình.

Phương án C là ứng viên đáng **đưa vào kiểm thử**, không phải kết luận mặc định. Nếu luật tuân thủ bắt buộc inspection tập trung cho mọi east–west traffic, lựa chọn đường riêng cần được thay đổi. Nếu traffic lớn và gateway là điểm nghẽn, phải đo lại chính sách inspection và cấu trúc trung chuyển.

### Ma trận quyết định rút gọn

| Tiêu chí | Câu hỏi kiểm chứng | Bằng chứng cần thu |
| --- | --- | --- |
| Bảo mật | Analytics có bị ngăn truy cập trực tiếp Booking DB không? | Route reachability, firewall decision, IAM/identity policy |
| Hiệu năng | Catalog → Booking đạt latency SLO tại tải đỉnh không? | p95/p99, throughput, số hop, packet drop |
| Độ tin cậy | Mất một AZ ở hub có làm mất booking không? | Failover test, thời gian phục hồi, error budget |
| Vận hành | Thêm spoke mới có tạo route, DNS và policy chính xác không? | IaC plan, policy checks, connectivity test |
| Chi phí | Byte nào đi qua inspection, NAT, liên AZ và liên vùng? | Flow logs, billing tags, bảng tính theo traffic class |
| Hybrid | Mất một VPN tunnel có còn đường hoạt động đúng policy không? | BGP route, tunnel metrics, kiểm thử chuyển tuyến |

## 15. Những sai lầm thiết kế thường gặp

**1. Coi hub-and-spoke là mặc định mọi spoke nhìn thấy nhau.** Có attachment tới hub chỉ chứng minh cấu hình kết nối tiềm năng. Route domain, route table và firewall vẫn phải định nghĩa rõ cặp mạng nào được phép trao đổi. Một số dịch vụ peering không cấp transit tự động qua một VPC/VNet trung gian.

**2. Chỉ vẽ đường đi, quên đường về.** Stateful firewall yêu cầu đường đi của một flow phù hợp cơ chế xử lý state. Route bất đối xứng giữa AZ hoặc appliance có thể gây lỗi ngẫu nhiên khó tái hiện.

**3. Dùng hub tập trung nhưng triển khai một firewall/NAT duy nhất.** Đây có thể trở thành single point of failure và điểm nghẽn khi tải tăng. Cần HA, phân bố AZ, giới hạn công suất và kiểm thử failover.

**4. Bắt mọi byte đi qua inspection dù không có yêu cầu.** Hairpin và nhiều lớp gateway tăng độ trễ, chi phí và phạm vi lỗi. Nên phân loại traffic theo độ nhạy, đối tượng truy cập và đường xử lý phù hợp.

**5. Đánh đồng network reachability với ủy quyền.** Được định tuyến tới một private IP không chứng minh được danh tính hoặc quyền nghiệp vụ. Cần identity, TLS, quyền tối thiểu và kiểm tra ở application.

**6. Quên DNS khi chuyển sang private networking.** Route và endpoint có thể đúng nhưng resolver vẫn trả về public IP hoặc không forward được zone nội bộ, khiến ứng dụng đi sai đường hoặc timeout.

**7. Thiếu kế hoạch CIDR dài hạn.** Các mạng production, staging, Kubernetes và on-premises chồng địa chỉ làm việc mở rộng/hybrid trở nên tốn kém. Không nên cho từng đội tự chọn CIDR tùy ý rồi mới ghép các mạng.

**8. Dùng IP NAT chung làm bằng chứng danh tính.** Mọi workload sau cùng địa chỉ egress có thể bị nhầm là một ứng dụng; cấp quyền tới cổng thanh toán chỉ dựa trên IP là chưa đủ.

**9. Mặc định có HA là có DR.** Một hub chạy nhiều AZ vẫn có thể phụ thuộc một region, DNS hoặc cấu hình logic chung. Cần mục tiêu và kiểm thử độc lập cho mất AZ, mất region và sai cấu hình.

**10. Xem logging là miễn phí và vô hạn.** Flow log, DNS log và firewall log có thể phát sinh lượng dữ liệu đáng kể, bao gồm metadata nhạy cảm. Cần retention, sampling khi phù hợp, quyền truy cập và dự toán.

**11. Chỉ kiểm thử chiều vào Internet.** Một ứng dụng có thể phục vụ frontend tốt nhưng thất bại khi gọi payment, service nội bộ hoặc hệ thống on-premises. Phải kiểm tra tất cả luồng quan trọng, cả hai chiều và khi một thành phần mạng bị mất.

**12. So sánh chi phí chỉ bằng số lượng gateway.** Cần tính giờ duy trì, byte xử lý, AZ/region transfer, NAT, egress, DNS, log và công sức vận hành. Một gateway ít nhưng có lượng traffic trung chuyển rất cao chưa chắc rẻ.

## 16. Bài tập thực hành và đáp án định hướng

Một tổ chức triển khai cloud có các mạng:

| Workload | CIDR | Yêu cầu |
| --- | --- | --- |
| Hub | 10.80.0.0/16 | Hybrid gateway, DNS resolver, egress inspection |
| Spoke A — Frontend | 10.81.0.0/16 | Phục vụ người dùng, chỉ gọi API ở B |
| Spoke B — Orders | 10.82.0.0/16 | Giao dịch đơn hàng, gọi payment provider qua Internet |
| Spoke C — BI | 10.83.0.0/16 | Nhận dữ liệu phân tích từ pipeline; không truy cập DB Orders trực tiếp |
| On-premises | 172.21.0.0/16 | Chỉ truy cập cổng API nội bộ theo chính sách |

Đội platform muốn kiểm toán kết nối ra Internet, kiểm soát hybrid và chuẩn hóa vận hành. Đội Orders yêu cầu độ trễ API thấp, còn BI thường truyền lượng lớn dữ liệu theo lô.

### Câu 1 — Chọn topology

**Đề bài:** Nên triển khai full mesh, hub-and-spoke hay kết hợp? Hãy nêu một phương án có thể kiểm chứng.

**Đáp án định hướng:** Chọn **hub-and-spoke cho hybrid, DNS và một số egress cần inspection**, kết hợp **policy gần workload** cho giao tiếp Frontend → Orders. BI nên nhận dữ liệu qua luồng đã được kiểm soát, không cần truy cập DB Orders. Nếu Frontend → Orders có tải rất cao, có thể đánh giá đường riêng/private service connectivity khi chính sách và nền tảng cho phép. Đây là ứng viên thiết kế cần đo latency, chi phí và kiểm thử an ninh trước khi chốt.

### Câu 2 — Vẽ đường đi của một giao dịch

**Đề bài:** Frontend ở A gọi Orders API ở B qua firewall hub. Những thành phần nào phải được cấu hình và kiểm tra?

**Đáp án định hướng:** Cần tên miền/private DNS trả đúng địa chỉ, route A→B, forwarding/inspection ở hub, chính sách firewall chỉ cho đúng luồng, route đến B và **route ngược B→A** phù hợp stateful inspection. Ở đầu nhận còn có network policy/security group, identity/TLS và quyền API. Phải đo luồng cả hai chiều, kịch bản mất một AZ và DNS resolution sau failover.

### Câu 3 — Tính số đường kết nối cặp

**Đề bài:** Nếu có 15 spoke, full mesh lý thuyết có bao nhiêu kết nối từng cặp? Một hub trung tâm đơn giản có bao nhiêu attachment spoke?

**Lời giải:** Full mesh có \(15\times14/2=105\) kết nối cặp. Với hub-and-spoke, có **15 attachment spoke tới hub**. Số này chưa tính route table, hub infrastructure, đường dự phòng và policy; không dùng trực tiếp để kết luận phương án nào rẻ hơn.

### Câu 4 — Nhận diện rủi ro từ route và NAT

**Đề bài:** Spoke B dùng route mặc định qua hub để đi Internet. Sau triển khai, hệ thống payment timeout ngẫu nhiên khi tải cao, trong khi API Orders nội bộ vẫn ổn định. Có thể kiểm tra gì?

**Đáp án định hướng:** Đo connection/port exhaustion và throughput của NAT, firewall drops, session limit, stateful return path, latency DNS, rate limit hoặc timeout từ payment provider, số lượng retry và kết quả đối soát. Không kết luận NAT là nguyên nhân chỉ từ triệu chứng. Nếu network đã khỏe, cần kiểm tra ứng dụng, client pool và provider; nếu thật sự do NAT, xem cách chia nguồn egress hoặc tăng công suất theo hỗ trợ của nhà cung cấp.

### Câu 5 — Phản biện một yêu cầu “mọi traffic phải qua hub”

**Đề bài:** BI cần truyền dữ liệu có kích thước 2 TB mỗi ngày từ kho dữ liệu ở cùng region, nhưng đường qua firewall hub làm tăng chi phí và latency. Làm thế nào cân bằng bảo mật và hiệu năng?

**Đáp án định hướng:** Xác định chính sách cụ thể cần bảo vệ điều gì: quyền truy cập dữ liệu, kiểm tra nội dung, audit truy xuất hay chỉ phân đoạn mạng. Có thể đánh giá private endpoint hoặc kênh riêng với identity, encryption và log đầy đủ nếu chính sách cho phép. Nếu luật bắt buộc inspection, cần dự toán gateway/firewall theo lượng byte và bố trí để giảm trung chuyển liên AZ. Quyết định phải có phê duyệt policy tương ứng và bằng chứng đo lưu lượng thực tế.

### Câu 6 — Đánh giá độ tin cậy

**Đề bài:** Hub có hai firewall ở hai AZ; khi AZ A bị mất, route tự chuyển traffic sang AZ B nhưng mọi kết nối Orders → Payment đều phải mở lại. Có được coi là “không gián đoạn” không?

**Đáp án định hướng:** Chưa thể kết luận. Tùy SLO, một phần TCP session bị reset và request timeout có thể tiêu thụ error budget. Cần đo thời gian phục hồi từ **góc nhìn giao dịch Orders**, retry có idempotency, năng lực firewall/NAT ở AZ B và số request thất bại. RTO phải gắn với hành trình nghiệp vụ và điều kiện mất AZ, không chỉ trạng thái báo healthy của firewall.

## 17. Bảng kiểm tra cho buổi review kiến trúc

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Có danh sách toàn bộ kết nối bắt buộc và đường bị cấm chưa? | Ma trận nguồn–đích–giao thức–dữ liệu và chủ sở hữu |
| CIDR có tránh chồng lấn với spoke tương lai, on-premises và đối tác? | Sơ đồ phân bổ địa chỉ và quy trình đăng ký |
| Có mô tả request/response, transit, firewall, NAT, DNS từng luồng chính? | Sơ đồ luồng và route table hai chiều |
| Việc route cho phép có được kiểm soát bằng chính sách quyền truy cập? | Firewall rules, network policies, IAM, thử nghiệm deny |
| Egress có giới hạn nguồn, đích và đủ công suất? | Flow logs, firewall/NAT metrics, quota và load test |
| Một lỗi hub, AZ, VPN hoặc DNS ảnh hưởng bao nhiêu workload? | Failure-domain diagram, failover drill, SLI người dùng |
| Multi-region có giữ được data residency và RPO/RTO? | Route liên vùng, replication plan, DR test |
| Có đo chi phí theo byte qua gateway, AZ/region, Internet và log? | Mô hình chi phí gắn với telemetry và billing |
| Route/firewall thay đổi có kiểm soát và rollback được không? | IaC, policy-as-code, review, canary, audit trail |
| Trách nhiệm hub/spoke rõ ràng và có runbook không? | RACI/ownership, dashboard, lịch diễn tập và quy trình sự cố |

Một quyết định mạng có thể bảo vệ được trong buổi review cần cho thấy **vì sao một luồng đi qua hub hay đi trực tiếp, lớp bảo mật nào áp dụng, điều gì xảy ra khi tuyến hỏng, và chi phí/độ trễ đo được có đáp ứng yêu cầu nghiệp vụ không**. Với bằng chứng đó, người thiết kế có thể chọn hub-and-spoke, mạng tập trung, mạng phân tán hoặc cấu trúc lai mà vẫn cân bằng các mục tiêu Well-Architected.
