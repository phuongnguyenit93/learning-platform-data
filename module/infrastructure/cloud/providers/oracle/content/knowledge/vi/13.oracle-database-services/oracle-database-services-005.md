# Thiết kế subnet, NSG và DNS cho DB System

Trong chương **Oracle Database trên OCI** của module **CLOUD_PROVIDERS_ORACLE**, bài học này trình bày cách thiết kế mạng cho DB System của **Oracle Base Database Service**. Nội dung kết nối tenancy, compartment, IAM, VCN và Compute với các yêu cầu truy cập cơ sở dữ liệu, vận hành dịch vụ, giám sát và tính sẵn sàng.

Một DB System ở trạng thái hoạt động chưa chứng minh ứng dụng kết nối được. Client còn phải phân giải đúng tên, có đường mạng hai chiều, được các lớp kiểm soát cho phép và gọi đúng database service. Thiết kế tốt mô tả rõ từng điều kiện này trước khi triển khai.

## 1. Mục tiêu và phạm vi

Sau bài học, người học có thể:

- Chia subnet cho ứng dụng, database, quản trị và DNS endpoint.
- Chọn route tới ứng dụng, on-premises và Oracle Services Network.
- Xây dựng NSG theo các luồng cần thiết, đồng thời kiểm tra security list.
- Chuẩn bị DNS cho DB System một node và RAC.
- Thiết kế phân giải tên giữa OCI và on-premises.
- Kiểm chứng kết nối theo các lớp DNS, TCP và Oracle Database.

Ví dụ chính dùng IPv4, private DB subnet và Internet and VCN Resolver của OCI. Các dải mạng là số liệu minh họa, cần thay theo kế hoạch địa chỉ của tổ chức.

Bài tập trung vào Base Database Service DB System. Mạng của Autonomous Database, Exadata hoặc các dịch vụ phục hồi riêng cần được thiết kế theo yêu cầu của đúng dịch vụ đó.

## 2. Kiến trúc tham chiếu

Một ứng dụng xử lý đơn hàng chạy trên Compute trong VCN, dùng database trong subnet riêng. Người quản trị truy cập qua đường quản trị đã kiểm soát. Nếu có mạng doanh nghiệp, kết nối riêng qua DRG và VPN hoặc FastConnect.

| Thành phần | Địa chỉ minh họa | Vai trò |
| --- | --- | --- |
| VCN | 10.40.0.0/16 | Không gian mạng của hệ thống |
| App subnet | 10.40.10.0/24 | Các máy ứng dụng được phép gọi database |
| DB subnet | 10.40.20.0/24 | DB System và các địa chỉ liên quan |
| Management subnet | 10.40.30.0/24 | Máy hoặc thành phần quản trị đã phê duyệt |
| DNS endpoint subnet | 10.40.40.0/27 | Endpoint DNS khi cần phân giải liên mạng |
| Mạng on-premises | 10.80.0.0/16 | Mạng doanh nghiệp đã kết nối riêng |

~~~mermaid
flowchart LR
    App["Compute ứng dụng / NSG app"] -->|"SQL*Net"| DB["Private DB subnet / NSG db"]
    Admin["Đường quản trị / NSG admin"] -->|"SSH theo quyền"| DB
    Office["On-premises"] --> Link["VPN hoặc FastConnect"]
    Link --> DRG["DRG"]
    DRG -->|"Route riêng và quyền phù hợp"| DB
    DB -->|"HTTPS tới dịch vụ Oracle"| SG["Service Gateway"]
    SG --> OSN["Oracle Services Network"]
    CorpDNS["DNS doanh nghiệp"] -.->|"Truy vấn domain OCI"| Resolver["OCI DNS listening endpoint"]
    Resolver -.-> Names["Private DNS của VCN"]
~~~

Luồng DNS và luồng SQL là hai luồng khác nhau. DNS doanh nghiệp có thể hỏi được tên database nhưng máy ứng dụng vẫn thiếu route tới IP database. Ngược lại, gọi bằng IP có thể thành công trong khi cấu hình tên của ứng dụng vẫn sai.

Trong ví dụ, compartment quản lý mạng có thể khác compartment quản lý DB System. Compartment phục vụ tổ chức tài nguyên và cấp quyền IAM; nó không tự tạo phân đoạn mạng giữa các máy.

## 3. Thiết kế DB subnet trước khi tạo hệ thống

### Chọn private subnet và phạm vi regional

Base Database Service cần VCN, subnet, route, security rules và khả năng kết nối tới Oracle Services Network. Oracle hỗ trợ subnet theo availability domain hoặc regional, đồng thời khuyến nghị regional subnet. [Nguồn: VCN and Subnets](https://docs.oracle.com/en/cloud/paas/base-database/guide/vcn-subnets.html).

Trong thiết kế tham chiếu:

- Chọn private subnet cho DB System.
- Dùng regional subnet để kế hoạch subnet không bị buộc vào một availability domain.
- Gắn route table và DHCP options đúng ngay từ đầu.
- Tách subnet ứng dụng để quản lý vòng đời và quyền truy cập rõ ràng.

Regional subnet không tự triển khai database trên nhiều availability domain và không tự cung cấp giải pháp DR. Mức sẵn sàng còn phụ thuộc loại DB System, cách bố trí node, backup và kế hoạch phục hồi.

Private subnet cũng không đồng nghĩa mọi lưu lượng ra ngoài đều bị chặn. Khả năng truy cập ra phụ thuộc gateway, route và security rules. Thiết kế trong bài dùng Service Gateway cho các dịch vụ Oracle phù hợp.

### Lập kế hoạch địa chỉ và IP dự phòng

Đừng tính kích thước subnet chỉ bằng số máy database hiện tại. Cần tính thêm:

- Các địa chỉ nền tảng dành riêng trong subnet.
- Địa chỉ node, VIP và SCAN theo cấu hình DB System.
- Tài nguyên bổ sung hoặc đợt triển khai thay thế.
- Không gian cho thử nghiệm phục hồi và tăng trưởng đã dự kiến.

Dải /24 trong ví dụ là lựa chọn minh họa để dễ lập kế hoạch, không phải kích thước bắt buộc cho mọi DB System. Kiểm tra yêu cầu địa chỉ của loại hệ thống và số IP còn trống trước khi tạo.

Tránh trùng CIDR với app subnet, mạng on-premises và các VCN dự kiến kết nối. Một kế hoạch không chồng lấn giúp đơn giản hóa route và kết nối doanh nghiệp về sau.

Ngoài kiểm tra chồng lấn thông thường, Oracle yêu cầu client subnet của cả DB System một node và RAC không được chồng với **192.168.16.16/28**, dải dùng cho Oracle Clusterware private interconnect. [Nguồn: Create a DB System — Network Information](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-create-new.html).

Không tự cấu hình lại private interconnect của dịch vụ để khắc phục một kế hoạch CIDR sai. Sửa thiết kế subnet trước khi triển khai.

## 4. Thiết kế route theo từng đích

### Route table của DB subnet

| Đích | Cách đi trong thiết kế tham chiếu |
| --- | --- |
| App subnet cùng VCN | Đường nội bộ VCN theo cấu hình routing hiện tại |
| Management subnet cùng VCN | Đường nội bộ VCN, có kiểm soát truy cập |
| 10.80.0.0/16 | DRG, nếu cần kết nối on-premises |
| All <region> Services in Oracle Services Network | Service Gateway của VCN |
| Đích Internet khác | Chỉ bổ sung khi có nhu cầu đã xác định và đường ra phù hợp |

Trong mô hình VCN thông thường, không cần tạo một route qua Internet Gateway để app subnet gọi DB subnet cùng VCN. Nếu kiến trúc có firewall hoặc thiết bị kiểm tra lưu lượng trung gian, phải xét đường đi thực tế của cả hai chiều.

Đối với on-premises, route của DB subnet mới chỉ là một phần. Kiểm tra thêm route phía doanh nghiệp, DRG attachment, bảng route của DRG và cơ chế quảng bá hoặc nhập route đang sử dụng. Route một chiều có thể làm quá trình bắt tay TCP không hoàn tất.

### Service Gateway cho hoạt động của dịch vụ

Thiết kế private subnet của Oracle dùng Service Gateway để tới Oracle Services Network, phục vụ các hoạt động như provisioning, backup và managed updates, cùng các Oracle YUM repository được hỗ trợ. Route sử dụng service CIDR label theo region, thay vì một danh sách IP tự nhập. [Nguồn: Private Subnet with Service Gateway](https://docs.oracle.com/en/cloud/paas/base-database/guide/vcn-subnets.html).

Đặt đúng nhãn **All <region> Services in Oracle Services Network** và đúng gateway trong route table của subnet DB. Đồng thời cần rule egress phù hợp, thường là HTTPS tới service label tương ứng.

Nếu chọn sao lưu tới Object Storage, đưa đường tới dịch vụ này vào kiểm tra. Nếu dùng một dịch vụ phục hồi với subnet hoặc endpoint riêng, bổ sung yêu cầu mạng của dịch vụ đó; không coi route Service Gateway là câu trả lời cho mọi đích backup.

Service Gateway không tạo đường cho một máy bất kỳ trên Internet gọi vào database. Nó cũng không thay route giữa DB subnet và on-premises.

### NAT Gateway và Internet Gateway

NAT Gateway có thể phục vụ các nhu cầu ra Internet khác từ mạng riêng khi kiến trúc cần. Không thêm default route qua NAT chỉ vì chưa tìm ra nguyên nhân lỗi provisioning.

Nếu một tài nguyên phải liên lạc với đích ngoài Oracle Services Network, mô tả đích, giao thức và lý do trước khi mở đường ra. Đối với thiết kế DB private của bài, đường dịch vụ Oracle được chuẩn bị riêng bằng Service Gateway.

## 5. NSG: xây quyền theo vai trò và luồng kết nối

### Các nhóm trong ví dụ

| NSG | Thành viên dự kiến |
| --- | --- |
| nsg-app-orders | VNIC của các máy ứng dụng đơn hàng |
| nsg-db-orders | DB System phục vụ đơn hàng |
| nsg-db-admin | Máy quản trị được phê duyệt |
| nsg-dns-endpoints | DNS resolver endpoints khi có kết nối liên mạng |

Tạo NSG chưa làm nó có hiệu lực trên DB System. Phải chọn NSG trong cấu hình DB System hoặc cập nhật liên kết theo cơ chế được dịch vụ hỗ trợ.

OCI cho phép rule NSG tham chiếu một NSG khác làm nguồn hoặc đích **trong cùng VCN**. Do đó có thể mô tả app-to-db bằng quan hệ nhóm, thay vì phải cập nhật danh sách IP của từng máy ứng dụng. [Nguồn: Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

Nếu client nằm ở VCN khác hoặc on-premises, không dùng NSG ở mạng đó như một tham chiếu xuyên VCN. Chọn nguồn CIDR hoặc cơ chế phù hợp với đường kết nối và địa chỉ nguồn thực sự tới DB.

### Ma trận quyền ứng dụng và quản trị

Các rule dưới đây là phần quyền theo ứng dụng, chưa thay thế toàn bộ bộ rule nền mà DB System yêu cầu:

| Nơi đặt rule | Chiều | Nguồn hoặc đích | Giao thức/cổng đích | Mục đích |
| --- | --- | --- | --- | --- |
| nsg-app-orders | Egress | nsg-db-orders | TCP 1521 | Ứng dụng khởi tạo kết nối SQL |
| nsg-db-orders | Ingress | nsg-app-orders | TCP 1521 | Nhận kết nối từ ứng dụng |
| nsg-db-orders | Ingress | nsg-db-admin | TCP 22 | Quản trị SSH qua đường đã kiểm soát |
| nsg-db-orders | Ingress | CIDR client on-premises đã phê duyệt | TCP 1521 | Chỉ thêm nếu có client kết nối trực tiếp |
| nsg-db-orders | Egress | Service label Oracle Services Network | TCP 443 | Tác vụ dịch vụ Oracle cần HTTPS |

Dùng **source port = All** cho kết nối client thông thường, vì cổng nguồn thường là cổng tạm thời do hệ điều hành chọn. Cổng 1521 trong ví dụ là cổng đích listener, không phải cổng mà client phải dùng làm nguồn.

Đối chiếu cổng thực tế trước khi triển khai. Kết nối TCPS cần cấu hình listener, chứng thư hoặc wallet và cổng tương ứng; mở TCP 1521 không tự bật mã hóa TLS.

### Bộ rule nền và các tính năng bổ sung

Tài liệu Base Database Service yêu cầu xét cả kết nối nền, ICMP cần thiết cho mạng và các luồng riêng của database. Ví dụ:

- ICMP type 3/code 4 cho IPv4 Path MTU Discovery.
- ICMP phục vụ thông báo lỗi kết nối trong VCN.
- TCP 22 hai chiều giữa node theo yêu cầu của RAC.
- TCP 6200 khi ứng dụng sử dụng ONS/FAN theo thiết kế.
- Luồng tới dịch vụ Oracle và các đích vận hành cần thiết.

Oracle mô tả các rule DB System là stateful, đồng thời yêu cầu điều chỉnh phạm vi SSH và egress theo các host thực sự cần liên lạc. [Nguồn: Security Rules for the DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/security-rules.html).

Không lấy bảng TCP 1521 ở trên làm bộ firewall hoàn chỉnh rồi xóa mọi rule khác. Với RAC, bộ rule nội bộ node và yêu cầu provisioning phải được kiểm tra trước khi thu hẹp.

ICMP phục vụ Path MTU Discovery không phải quyền SQL từ Internet. Chặn toàn bộ ICMP có thể tạo lỗi khó hiểu: kết nối nhỏ hoạt động nhưng truyền dữ liệu lớn bị treo.

### Stateful và giới hạn của một phép thử

Với rule stateful, OCI theo dõi kết nối và cho phép lưu lượng phản hồi tương ứng. Không cần mở mọi cổng đích tạm thời ở DB chỉ để trả lời một kết nối SQL đã được theo dõi.

Nếu trộn rule stateful và stateless cùng phủ một luồng, phải đánh giá lại hành vi theo tài liệu OCI. Bài thực hành giữ các luồng DB theo yêu cầu stateful của dịch vụ.

Kiểm tra thêm firewall trên hệ điều hành DB System. Quyền ở NSG không tự sửa listener đang dừng, ứng dụng dùng sai cổng hoặc firewall tại host. [Nguồn: Stateful Rules và OS Firewall](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

## 6. NSG và security list cộng gộp quyền

Security list áp dụng theo subnet, còn NSG gắn với các tài nguyên hoặc VNIC thuộc nhóm. Khi dùng cả hai, bộ rule cho phép áp dụng trên VNIC là hợp các rule liên quan. Một NSG hẹp không phủ định một rule mở rộng trong security list. [Nguồn: Security Rules — Using Both](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Ví dụ sai về kết quả mong đợi:

~~~text
Security list của DB subnet:
  Cho phép 10.40.0.0/16 tới TCP 1521

nsg-db-orders:
  Chỉ khai báo nsg-app-orders tới TCP 1521
~~~

Trong tình huống này, các nguồn khác thuộc dải VCN vẫn có thể được security list cho phép. Muốn chỉ app được kết nối, phải rà soát và sửa cả rule rộng đó, sau khi xác định các phụ thuộc thực sự.

Trình tự kiểm tra:

1. Liệt kê mọi security list đang gắn với DB subnet.
2. Liệt kê mọi NSG đang gắn với DB System.
3. Tìm các rule phủ rộng cổng SQL hoặc SSH.
4. Đối chiếu với ma trận luồng đã phê duyệt.
5. Thử kết nối mới từ nguồn được phép và nguồn không được phép.

Một kết nối SQL đã tồn tại không phải phép thử tốt để xác định thay đổi rule đã chặn kết nối mới hay chưa. Dùng phiên thử mới và ghi lại thời điểm thay đổi.

IAM là lớp khác: quyền xem hoặc sửa DB System qua Console/API không tự cấp quyền đăng nhập Oracle Database. Quyền truy cập mạng tới listener cũng không thay thế tài khoản và quyền database.

## 7. DNS nội bộ cho DB System

### Chuẩn bị DNS labels và DHCP options

Với Internet and VCN Resolver:

- Bật DNS hostnames khi tạo VCN và đặt VCN DNS label.
- Bật DNS hostnames khi tạo subnet và đặt subnet DNS label.
- Gắn DHCP options sử dụng Internet and VCN Resolver.
- Chọn hostname prefix hợp lệ và duy nhất khi tạo DB System.

Các DNS label này cần được quyết định từ đầu vì không đổi được sau khi tạo. Tên hiển thị của subnet không thay thế DNS label. [Nguồn: DNS in a Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns.htm).

Ví dụ:

~~~text
VCN display name: vcn-orders-prod
VCN DNS label:   prodsg
Subnet display: subnet-db-private
Subnet label:   db
Hostname prefix: ordersdb

FQDN minh họa một node:
ordersdb.db.prodsg.oraclevcn.com
~~~

Đây là cách đọc cấu trúc tên. Khi cấu hình client, lấy hostname và connection details thực tế của DB System, không tự tạo tên bằng cách ghép chuỗi rồi giả định đã tồn tại.

Chọn label ngắn, dễ phân biệt môi trường và tuân thủ giới hạn tên của DB System. Khi kết nối qua nhiều subnet hoặc VCN, dùng FQDN để tránh phụ thuộc search domain trên máy client.

### Resolver phải phân giải được nhiều loại endpoint

DB System cần phân giải tên phục vụ vận hành, không chỉ tên để ứng dụng gọi SQL. Tài liệu Oracle liệt kê các endpoint Object Storage, Swift, Oracle YUM repository và SCAN cho RAC.

Base Database Service hỗ trợ custom resolver với VM DB System một node theo điều kiện tài liệu; với multi-node RAC, lựa chọn được liệt kê là Internet and VCN Resolver. [Nguồn: DNS for the DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dns.html).

Do đó, không thay DHCP DNS của RAC sang DNS doanh nghiệp chỉ để giải quyết một tên nội bộ công ty. Đánh giá private resolver endpoints và forwarding trong kiến trúc được hỗ trợ, đồng thời giữ khả năng phân giải các tên nền mà dịch vụ cần.

Đổi DHCP options cũng không bảo đảm mọi máy lập tức dùng cấu hình mới; cần tính đến việc client nhận lại cấu hình và cache DNS. Thực hiện thay đổi theo quy trình phù hợp với DB System.

### Phân giải được không đồng nghĩa kết nối được

Internet and VCN Resolver có thể phân giải tên công khai mà máy không có đường Internet. Vì vậy:

~~~text
DNS lookup thành công
  chưa chứng minh route tới IP tồn tại

TCP tới listener thành công
  chưa chứng minh Oracle service đã đăng ký

Đăng nhập database thành công
  chưa chứng minh ứng dụng có đúng quyền nghiệp vụ
~~~

Khi kiểm tra đường tới Oracle Services Network, xác minh cả việc phân giải endpoint lẫn route và quyền egress. Chỉ thử nslookup rồi kết luận backup hoạt động là chưa đủ.

## 8. DNS cho ứng dụng, RAC và connection string

### Một node và RAC dùng điểm vào khác nhau

Đối với single-instance DB System, connection string thường dùng hostname tương ứng. Với RAC, client sử dụng **Single Client Access Name — SCAN**. SCAN có thể trả nhiều địa chỉ; không cố định một địa chỉ trả về vào cấu hình ứng dụng rồi bỏ phần còn lại. [Nguồn: Database Connection Strings](https://docs.oracle.com/en/cloud/paas/base-database/guide/connect.html).

Trong RAC, client liên hệ SCAN listener rồi có thể được chuyển tới local listener của node phục vụ service. Vì vậy, thiết kế route và quyền phải cho phép cả các endpoint đích sau redirect, không chỉ một IP SCAN được chọn để thử TCP. [Nguồn: Connecting to Oracle RAC Using SCANs](https://docs.oracle.com/en/database/oracle/oracle-database/19/riwin/about-connecting-to-an-oracle-rac-database-using-scans.html).

Đây là lý do một lệnh thử tới SCAN port thành công vẫn chưa đủ để chứng minh client hoàn tất kết nối database.

### Chọn đúng database service

Ứng dụng cần service phù hợp với PDB hoặc workload. Default administration service ở cấp CDB không phải lựa chọn mặc định để đưa vào ứng dụng nghiệp vụ. Lấy thông tin service từ quản trị database và connection details thực tế. [Nguồn: Database Services](https://docs.oracle.com/en/cloud/paas/base-database/guide/connect.html).

Ví dụ hình thức JDBC cho phép thử một node:

~~~text
jdbc:oracle:thin:@//DB_HOST_FQDN:1521/APP_SERVICE_FQDN
~~~

DB_HOST_FQDN là hostname được phân giải từ nơi ứng dụng chạy. APP_SERVICE_FQDN là tên service Oracle Database, không phải tên DB System, SID hoặc tên tài nguyên hiển thị.

Với RAC và yêu cầu tính sẵn sàng, dùng connect descriptor và cấu hình timeout/retry phù hợp với driver và dịch vụ. Bài không dùng một URL tối giản làm cam kết failover của toàn ứng dụng.

Không đưa mật khẩu vào URL hoặc log kiểm tra. Chuỗi kết nối mô tả đường tới dịch vụ; thông tin xác thực cần được quản lý theo cơ chế của ứng dụng.

## 9. Phân giải DNS với on-premises hoặc VCN khác

### Hai chiều truy vấn cần thiết kế riêng

| Nơi phát sinh truy vấn | Tên cần tìm | Luồng thiết kế |
| --- | --- | --- |
| Client on-premises | Tên DB trong OCI | DNS doanh nghiệp forward domain phù hợp tới OCI listening endpoint |
| Máy OCI | Tên dịch vụ doanh nghiệp | OCI forwarding endpoint và resolver rule tới DNS doanh nghiệp |
| Client ở VCN khác | Tên DB trong VCN đích | Chia sẻ khả năng phân giải qua private DNS view hoặc forwarding phù hợp |
| Client cùng VCN | Tên DB của VCN | Resolver nội bộ theo DHCP options |

Có VPN, FastConnect hoặc peering chưa tự giải quyết việc phân giải private hostname. OCI cung cấp listening endpoint để nhận truy vấn từ mạng khác và forwarding endpoint để gửi truy vấn theo resolver rule. [Nguồn: Private DNS](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm).

### Luồng từ doanh nghiệp tới OCI

Một thiết kế mẫu:

1. Tạo OCI DNS listening endpoint trong subnet có route tới mạng doanh nghiệp.
2. Xác nhận resolver của endpoint nhìn thấy domain chứa tên DB System.
3. Trên DNS doanh nghiệp, tạo conditional forwarder cho domain OCI cần thiết.
4. Cho phép DNS server doanh nghiệp tới IP listening endpoint.
5. Kiểm tra DNS từ chính client doanh nghiệp.
6. Sau đó kiểm tra SQL từ client được cấp quyền.

Ưu tiên forward domain cụ thể theo kiến trúc thay vì chuyển mọi truy vấn của doanh nghiệp sang OCI. Tránh vòng lặp giữa hai resolver: cùng một tên bị OCI gửi về doanh nghiệp rồi doanh nghiệp lại gửi ngược về OCI.

Listening và forwarding là hai vai trò endpoint riêng. Các endpoint cần subnet, địa chỉ IP và quyền mạng phù hợp; endpoint DNS có thể gắn NSG. [Nguồn: Resolver Endpoints](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-resolver_endpoints.htm).

### Quyền mạng của DNS endpoint

Với thiết kế cần cả UDP và TCP DNS, mô tả các luồng cổng 53 tới đúng DNS server hoặc endpoint, cùng chiều phản hồi theo cấu hình stateful/stateless đang sử dụng. Nếu dùng rule stateless, không bỏ sót chiều phản hồi.

Nguồn được cho phép nên là DNS server doanh nghiệp thực sự gửi truy vấn, thay vì mặc định toàn bộ mạng doanh nghiệp. Đồng thời cần route hai chiều qua kết nối riêng.

Địa chỉ resolver link-local **169.254.169.254** trong VCN không phải IP endpoint để máy on-premises tùy ý truy vấn qua VPN. Dùng listening endpoint có địa chỉ trong subnet được thiết kế cho kết nối đó.

Các chi tiết quyền UDP/TCP và kết nối giữa các resolver được mô tả trong [Private DNS — VCN Connectivity](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm).

## 10. Trình tự triển khai có thể kiểm tra lại

Thực hiện trong compartment lab hoặc môi trường đã xác định:

1. Chốt CIDR không chồng lấn và kiểm tra dải dành cho private interconnect.
2. Tạo VCN, DNS label và các subnet cần thiết.
3. Gắn route table, DHCP options và security list theo thiết kế.
4. Tạo Service Gateway và route tới Oracle Services Network.
5. Chuẩn bị DRG cùng đường doanh nghiệp nếu có client on-premises.
6. Tạo NSG, thêm rule nền và rule theo vai trò.
7. Xác minh DNS từ máy thử nghiệm trong app subnet.
8. Khi tạo DB System, chọn đúng VCN, DB subnet, NSG và hostname prefix.
9. Lấy endpoint và service thực tế sau khi DB System sẵn sàng.
10. Kiểm tra từ nguồn được phép và nguồn không được phép.
11. Kiểm chứng tác vụ vận hành, bao gồm đường backup hoặc cập nhật theo môi trường.
12. Lưu bản đồ cấu hình và bằng chứng để đối chiếu khi thay đổi.

Nếu đã có DB System, bắt đầu bằng việc đọc cấu hình hiện tại và xác định các ứng dụng phụ thuộc. Không thay DHCP, route hay gỡ rule nền đồng loạt khi chưa biết phạm vi ảnh hưởng.

Quyền tạo mạng, quyền chọn subnet/NSG khi tạo DB System và quyền quản lý database có thể thuộc các nhóm khác nhau. Chuẩn bị phân quyền IAM ở đúng compartment cho từng phần việc.

## 11. Đọc cấu hình bằng OCI CLI và kiểm tra kết nối

Các lệnh dưới đây là hướng dẫn thực hành, không phải lệnh đã chạy trên tenancy. Cần OCI CLI đã xác thực và quyền đọc các tài nguyên tương ứng.

### Đọc DB System và subnet

~~~powershell
$Region = 'THAY_REGION'
$DbSystemId = 'THAY_OCID_DB_SYSTEM'
$DbSubnetId = 'THAY_OCID_DB_SUBNET'
$DbNsgId = 'THAY_OCID_NSG_DB'
$DbRouteTableId = 'THAY_OCID_ROUTE_TABLE_DB'

$DbArgs = @(
    'db', 'system', 'get',
    '--region', $Region,
    '--db-system-id', $DbSystemId
)
oci @DbArgs

$SubnetArgs = @(
    'network', 'subnet', 'get',
    '--region', $Region,
    '--subnet-id', $DbSubnetId
)
oci @SubnetArgs
~~~

Đối chiếu subnet ID, NSG IDs, DNS label/domain, route table và DHCP options với thiết kế. Đừng chỉ so sánh tên hiển thị vì tên đó có thể trùng giữa các compartment. [Tham chiếu DB System get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/system/get.html), [Subnet get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/subnet/get.html).

### Đọc toàn bộ NSG rules và route table

~~~powershell
$NsgArgs = @(
    'network', 'nsg', 'rules', 'list',
    '--region', $Region,
    '--nsg-id', $DbNsgId,
    '--all'
)
oci @NsgArgs

$RouteArgs = @(
    'network', 'route-table', 'get',
    '--region', $Region,
    '--rt-id', $DbRouteTableId
)
oci @RouteArgs
~~~

Tùy chọn --all giúp tránh chỉ đọc trang đầu của danh sách NSG rules. Sau đó vẫn phải kiểm tra các NSG khác và security list liên quan, không chỉ một NSG được đặt tên là “db”. [Tham chiếu NSG rules list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg/rules/list.html), [Route table get](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/get-details-routetable.htm).

### Kiểm tra DNS và TCP từ đúng nguồn

Từ máy Windows có đường mạng và quyền theo thiết kế:

~~~powershell
$DbHost = 'THAY_FQDN_HOST_HOAC_SCAN'
$ListenerPort = 1521

Resolve-DnsName -Name $DbHost -Type A
Test-NetConnection -ComputerName $DbHost -Port $ListenerPort
~~~

Ghi lại resolver đang dùng và toàn bộ địa chỉ trả về. Với SCAN, thử các địa chỉ phù hợp và kiểm chứng kết nối database thật, bao gồm chặng tới listener sau redirect.

Từ client Linux, có thể dùng:

~~~bash
DB_HOST='THAY_FQDN_HOST_HOAC_SCAN'
getent ahostsv4 "$DB_HOST"
~~~

Thực hiện trên máy ứng dụng hoặc máy đại diện đúng subnet, route và danh tính mạng. Một laptop ngoài mạng hoặc Cloud Shell không có private connectivity tương ứng không thay thế được phép thử từ app subnet.

### Kiểm tra dịch vụ database

Trên máy đã cài Oracle client và có quyền ứng dụng thử nghiệm, dùng đúng service cho phép thử một node:

~~~text
sqlplus -L app_user@//DB_HOST_FQDN:1521/APP_SERVICE_FQDN
~~~

Nhập mật khẩu khi công cụ yêu cầu. Với RAC, dùng connect descriptor đã được chuẩn bị cho client và service tương ứng.

Sau khi đăng nhập:

~~~sql
select
    sys_context('USERENV', 'SERVICE_NAME') as service_name,
    sys_context('USERENV', 'CON_NAME') as container_name
from dual;
~~~

Kết quả giúp xác minh đang ở service và container dự kiến. Không dừng ở việc cổng TCP mở rồi kết luận chuỗi kết nối ứng dụng đã đúng.

## 12. Ma trận xác minh và chẩn đoán

### Kiểm tra cả nguồn được phép và không được phép

| Nguồn thử | DNS | Kết nối SQL mới | Ý nghĩa |
| --- | --- | --- | --- |
| Máy thuộc nsg-app-orders | Phân giải đúng | Thành công với tài khoản hợp lệ | Đường ứng dụng hoạt động |
| Máy khác trong VCN, không được phê duyệt | Có thể vẫn phân giải được | Bị chặn theo thiết kế | DNS không đồng nghĩa quyền truy cập |
| Máy quản trị được phê duyệt | Phân giải đúng | Theo quyền đã cấp, SSH kiểm tra riêng | Đường quản trị được tách |
| Client on-premises được phê duyệt | Phân giải qua DNS doanh nghiệp | Thành công nếu đã có route và quyền | Cả DNS lẫn data path hoạt động |
| Máy Internet không có kết nối riêng | Không dùng để chứng minh truy cập private | Không kết nối trực tiếp trong mô hình này | Phù hợp thiết kế private DB |

Một phép thử bị chặn chỉ có ý nghĩa khi xác nhận đúng nguồn, IP đích và luồng. Nếu DNS đã sai từ đầu, kết quả timeout không chứng minh NSG đang giới hạn đúng.

### Điều tra theo lớp

| Triệu chứng | Hướng kiểm tra trước |
| --- | --- |
| Không phân giải được FQDN DB | Resolver của client, DHCP, DNS label, private view hoặc conditional forwarding |
| OCI phân giải được nhưng on-premises không | Listening endpoint, domain forward, route và quyền cổng 53 |
| Có IP nhưng TCP timeout | Route hai chiều, NSG/security list, host firewall, listener |
| TCP được nhưng Oracle báo service không tồn tại | SERVICE_NAME, trạng thái đăng ký service và PDB |
| Kết nối một SCAN IP được nhưng ứng dụng chập chờn | Các SCAN IP khác và đích local listener sau redirect |
| Ứng dụng kết nối được nhưng backup/cập nhật lỗi | DNS endpoint dịch vụ, Service Gateway, route và egress liên quan |
| Máy ngoài nhóm app vẫn vào được DB | Rule rộng trong security list, NSG khác hoặc nguồn mạng được hiểu sai |
| Truyền nhỏ được nhưng dữ liệu lớn treo | MTU, ICMP cần thiết, đường VPN và thiết bị trung gian |
| Đổi DNS nhưng máy vẫn dùng cấu hình cũ | DHCP lease, cache OS, cache runtime hoặc connection pool |

Lỗi xác thực Oracle không được xử lý bằng cách mở rộng NSG. Tương tự, lỗi DNS không được sửa bằng cách mở mọi cổng tới toàn VCN.

Khi có bằng chứng gói bị chặn, có thể dùng VCN Flow Logs và các công cụ quan sát mạng phù hợp. Đối chiếu với log listener, resolver và ứng dụng theo thời điểm; giới hạn nội dung log để không ghi mật khẩu hoặc dữ liệu nghiệp vụ.

## 13. Vận hành, tính sẵn sàng và chi phí

DNS là một phụ thuộc của kết nối mới. Cần thử tình huống resolver doanh nghiệp không truy cập được OCI, một endpoint không phản hồi hoặc database được phục hồi sang môi trường khác.

Đối với RAC, không ghim ứng dụng vào một node để “sửa nhanh” lỗi SCAN rồi coi đó là thiết kế cuối cùng. Đối với DR, chuẩn bị cả route, DNS, quyền và service của hệ thống phục hồi; thay một bản ghi DNS không tự chuyển trạng thái database hay giao dịch.

Khi thay rule, route hoặc DHCP:

- Ghi nhận cấu hình hiện tại và các nguồn sử dụng.
- Chuẩn bị thay đổi cùng phương án quay lại.
- Kiểm tra kết nối mới, pool ứng dụng và tác vụ dịch vụ Oracle.
- Quan sát lỗi và độ trễ sau khi áp dụng.
- Thu hồi quyền tạm thời sau khi xác minh.

Về chi phí, tính cả kết nối riêng, gateway hoặc thiết bị mạng được triển khai, DNS theo mô hình sử dụng, log, máy thử nghiệm và tài nguyên database. Dùng quy mô lab phù hợp và kiểm tra điều kiện tính phí thực tế trước khi triển khai.

Không chọn CIDR quá nhỏ chỉ để tạo cảm giác tiết kiệm tài nguyên. Ngược lại, đừng tạo thêm gateway hoặc DNS endpoint nếu chưa có luồng sử dụng rõ ràng.

## 14. Bài thực hành củng cố

Trong môi trường lab, hoàn thành:

1. Vẽ VCN và các subnet, ghi rõ CIDR, DNS label và route table.
2. Viết ma trận app-to-db, quản trị, DNS và Oracle Services Network.
3. Kiểm tra rule hiệu lực từ mọi NSG và security list liên quan.
4. Xác minh FQDN DB từ app subnet rồi đăng nhập đúng application service.
5. Thử kết nối mới từ một máy không được phê duyệt và giải thích kết quả.
6. Nếu có on-premises, kiểm tra riêng DNS cổng 53 và SQL cổng listener.
7. Với RAC, giải thích đường SCAN tới local listener và cách tránh bỏ sót endpoint.
8. Lập phương án kiểm tra backup/cập nhật sau khi thu hẹp egress.

Kết quả cần có là sơ đồ mạng, danh sách luồng, bản đồ DNS và bằng chứng kiểm tra theo từng lớp. Giữ lại các rule cần thiết của dịch vụ, khôi phục cấu hình đã thay để thử lỗi và chỉ dọn đúng tài nguyên lab sau khi kiểm tra phụ thuộc.

Thiết kế subnet quyết định vị trí và đường đi; NSG cùng security list quyết định luồng được phép; DNS cung cấp điểm vào ổn định. Kết nối DB System chỉ đáng tin cậy khi cả ba phần khớp với service và cách vận hành của ứng dụng.