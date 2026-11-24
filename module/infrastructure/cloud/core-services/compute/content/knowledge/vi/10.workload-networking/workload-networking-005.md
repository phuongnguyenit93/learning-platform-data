# DNS, hostname và phát hiện dịch vụ giữa các máy

Trong một hệ thống cloud, ứng dụng thường chạy trên nhiều máy ảo hoặc container và cần kết nối tới nhau. API phải tìm được địa chỉ của database, worker cần tìm queue, các service cần gọi nhau qua mạng nội bộ và load balancer phải chuyển request tới những instance đang hoạt động. Nếu cấu hình địa chỉ IP cố định trong mã nguồn, việc thay máy, mở rộng số bản sao hoặc chuyển workload sang subnet khác sẽ làm cấu hình nhanh chóng lỗi thời.

**DNS (Domain Name System)** ánh xạ tên miền hoặc tên máy sang thông tin mạng như địa chỉ IP. **Hostname** là tên nhận diện một máy trong hệ điều hành hoặc mạng. **Service discovery** là quá trình một thành phần tìm ra các instance đang cung cấp một dịch vụ và thông tin cần thiết để kết nối tới chúng. Ba khái niệm liên quan chặt chẽ nhưng không đồng nghĩa: hostname nhận diện máy, DNS giúp phân giải tên, còn service discovery tìm endpoint của dịch vụ theo vòng đời và trạng thái của workload.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, tập trung vào DNS, hostname và cách các máy tìm thấy dịch vụ của nhau trong môi trường VM, container và cloud. Nội dung bao gồm quy trình phân giải tên, bản ghi DNS, private DNS, DNS hybrid, service registry, Kubernetes DNS, chẩn đoán sự cố và bảo mật.

## 1. Vì sao workload cần DNS và service discovery?

Giả sử một hệ thống thương mại điện tử có ba API, một database, một cache và nhiều worker. Nếu API kết nối database bằng địa chỉ IP được ghi trực tiếp trong cấu hình, việc thay database hoặc chuyển nó sang subnet khác sẽ buộc phải cập nhật nhiều ứng dụng. Nếu mỗi lần scale-out lại phải sửa thủ công danh sách IP của worker, quá trình triển khai sẽ chậm và dễ sai.

DNS và service discovery giúp tách danh tính logic khỏi vị trí vật lý:

- Ứng dụng gọi tên như db.internal.example thay vì phụ thuộc vào IP cụ thể.
- Khi instance thay đổi, hệ thống quản lý DNS hoặc service registry cập nhật endpoint.
- Một tên dịch vụ có thể đại diện cho nhiều instance.
- Các workload ở những máy khác nhau có thể dùng cùng một cơ chế tìm kiếm.
- Cấu hình kết nối được quản lý tập trung và có thể áp dụng theo môi trường.

DNS đặc biệt hữu ích cho các endpoint có vòng đời tương đối ổn định. Với workload thay đổi rất nhanh hoặc cần kiểm tra sức khỏe, metadata và cân bằng tải ở mức ứng dụng, DNS thường được kết hợp với service registry, load balancer hoặc cơ chế discovery của nền tảng điều phối.

## 2. Phân biệt hostname, domain name và service name

Các tên xuất hiện trong hệ thống mạng có mục đích khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Hostname | Tên máy được cấu hình trong hệ điều hành | api-01 |
| Domain name | Tên trong không gian tên DNS | example.com |
| FQDN | Tên miền đầy đủ, xác định vị trí trong DNS hierarchy | api-01.prod.internal.example |
| Service name | Tên logic của một chức năng mà client cần gọi | orders-api |
| Endpoint | Thông tin để kết nối tới một instance hoặc dịch vụ | 10.20.4.15:8080 |

Hostname thường được đặt khi tạo VM hoặc trong bước bootstrap. Hệ điều hành có thể dùng hostname cho prompt, log, nhận diện máy và một số giao thức. DNS record là dữ liệu do DNS zone quản lý; thay đổi hostname trong guest không nhất thiết tự động cập nhật DNS nếu không có cơ chế đăng ký tương ứng.

FQDN (Fully Qualified Domain Name) là tên đầy đủ trong DNS. Ví dụ, api-01.prod.internal.example có thể biểu thị máy api-01 thuộc môi trường prod trong vùng tên internal.example. Dấu chấm cuối tên, như api-01.prod.internal.example., biểu thị tên tuyệt đối trong DNS; nhiều công cụ tự thêm dấu chấm này khi hiển thị.

Service name có thể trỏ tới một load balancer, một địa chỉ ảo, một nhóm bản ghi DNS hoặc được tra cứu trong service registry. Client thường chỉ cần biết service name và giao thức/port được công bố.

## 3. DNS hoạt động như thế nào?

DNS là hệ thống tên phân cấp và phân tán. Khi ứng dụng cần kết nối tới một hostname, hệ điều hành hoặc thư viện resolver sẽ tìm địa chỉ tương ứng thông qua DNS resolver được cấu hình.

Một luồng phân giải điển hình:

1. Ứng dụng yêu cầu phân giải một tên, ví dụ api.prod.internal.example.
2. Stub resolver trên máy kiểm tra cache cục bộ và cấu hình tìm kiếm tên.
3. Nếu chưa có kết quả, truy vấn được gửi tới recursive resolver đã cấu hình, thường do cloud provider, tổ chức hoặc mạng nội bộ quản lý.
4. Recursive resolver kiểm tra cache; nếu cần, nó truy vấn hệ thống DNS phân cấp hoặc authoritative DNS server.
5. Authoritative server trả lời bản ghi cho zone mà nó quản lý.
6. Resolver trả kết quả về máy và lưu cache theo TTL.
7. Ứng dụng dùng địa chỉ nhận được để mở kết nối mạng.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng / OS
    participant R as Recursive Resolver
    participant H as Root / TLD DNS
    participant N as Authoritative DNS
    A->>R: Tra cứu api.prod.internal.example
    alt Có kết quả trong cache
        R-->>A: Trả địa chỉ đã cache
    else Cache miss
        R->>H: Tìm máy chủ quản lý zone
        H-->>R: Referral tới DNS server tiếp theo
        R->>N: Truy vấn bản ghi
        N-->>R: Trả A/AAAA hoặc loại record khác
        R-->>A: Trả kết quả và TTL
    end
~~~

Trong mạng cloud, resolver có thể là dịch vụ DNS nội bộ của VPC/VNet hoặc resolver forward tới hệ thống DNS của doanh nghiệp. Người dùng VM thường không cần tự truy vấn root server; recursive resolver thực hiện phần lớn công việc này.

### 3.1. Stub resolver, recursive resolver và authoritative server

- **Stub resolver:** thành phần đơn giản trên máy khách, gửi truy vấn tới resolver được cấu hình.
- **Recursive resolver:** nhận truy vấn thay client, tìm câu trả lời và cache kết quả.
- **Authoritative DNS server:** trả lời có thẩm quyền cho zone mà nó quản lý.

Phân biệt các vai trò này giúp khoanh vùng sự cố. Nếu máy gửi truy vấn tới resolver sai, lỗi nằm ở cấu hình client hoặc DHCP. Nếu resolver không truy cập được authoritative server, lỗi có thể nằm ở forwarding, firewall hoặc delegation. Nếu authoritative server trả sai record, cần kiểm tra zone và quá trình cập nhật DNS.

### 3.2. Recursive query và iterative query

Client thường gửi recursive query tới resolver: resolver chịu trách nhiệm tìm câu trả lời cuối cùng hoặc trả lỗi. Trong quá trình tìm kiếm, resolver có thể gửi iterative query tới các DNS server phân cấp; mỗi server trả câu trả lời nếu biết hoặc referral tới nơi có thể biết.

Không nên nhầm recursive resolver với authoritative server. Một máy chủ có thể cung cấp cả hai chức năng trong một số kiến trúc, nhưng ở môi trường doanh nghiệp chúng thường được tách để giới hạn phạm vi và bảo mật.

## 4. Các loại bản ghi DNS thường dùng

DNS hỗ trợ nhiều loại resource record (RR). Các bản ghi quan trọng với workload:

| Loại record | Công dụng | Ví dụ |
|---|---|---|
| A | Ánh xạ tên tới địa chỉ IPv4 | api.internal.example → 10.20.4.15 |
| AAAA | Ánh xạ tên tới địa chỉ IPv6 | api.internal.example → 2001:db8:20::15 |
| CNAME | Bí danh trỏ tới một tên DNS khác | orders.internal.example → api-01.internal.example |
| PTR | Tra cứu ngược từ địa chỉ IP tới tên | 15.4.20.10.in-addr.arpa → api-01.internal.example |
| SRV | Công bố hostname, port, priority và weight của dịch vụ | _grpc._tcp.internal.example |
| TXT | Chứa văn bản phục vụ xác minh hoặc chính sách | SPF, domain verification |
| NS | Chỉ định authoritative name server của zone | ns1.example.net |
| SOA | Thông tin quản trị và đồng bộ zone | primary server, serial, refresh |

### 4.1. A và AAAA

A record trả về IPv4; AAAA record trả về IPv6. Một hostname có thể có cả hai loại record nếu dịch vụ hỗ trợ song song hai giao thức. Client có thể chọn địa chỉ dựa trên chính sách mạng và thuật toán kết nối.

Không nên công bố AAAA chỉ vì hạ tầng có IPv6 ở một phần mạng. Toàn bộ đường đi, firewall, route và dịch vụ phải hỗ trợ IPv6; nếu không, một số client có thể gặp timeout hoặc fallback chậm.

### 4.2. CNAME

CNAME tạo bí danh từ một tên sang tên khác. Ví dụ, api.internal.example có thể là alias của api-prod-lb.internal.example. Khi địa chỉ load balancer thay đổi, chỉ cần cập nhật record đích.

Theo quy tắc DNS chuẩn, một tên đã có CNAME không nên đồng thời có các loại record dữ liệu khác tại cùng owner name. CNAME ở apex của zone có giới hạn vì apex phải có SOA và NS; một số nhà cung cấp có cơ chế alias/flattening riêng để xử lý trường hợp này.

### 4.3. PTR và reverse DNS

PTR hỗ trợ tra cứu ngược từ IP sang tên. Reverse DNS thường được quản lý trong các zone in-addr.arpa cho IPv4 và ip6.arpa cho IPv6. PTR hữu ích cho log, kiểm tra hạ tầng, một số hệ thống email và công cụ vận hành. Tuy nhiên, PTR không thay thế xác thực danh tính; kết quả reverse lookup không chứng minh máy gửi là đáng tin cậy.

### 4.4. SRV

SRV record có thể công bố dịch vụ chạy trên hostname và port cụ thể, kèm priority và weight. Cấu trúc tên thường theo dạng _service._proto.name. Ví dụ, ứng dụng có thể tra cứu _grpc._tcp.orders.internal.example để biết endpoint gRPC.

Không phải mọi client library đều tự động tra cứu SRV. Cần xác minh thư viện có hỗ trợ record này hay không. Nếu không, ứng dụng có thể cần resolver riêng hoặc cấu hình endpoint rõ ràng.

## 5. Hostname và cấu hình tên máy trên VM

Hostname nên có quy tắc đặt tên nhất quán, dễ nhận diện và không chứa thông tin nhạy cảm. Một hostname có thể biểu diễn vai trò, môi trường, vùng hoặc số thứ tự.

Ví dụ:

| Hostname | Ý nghĩa |
|---|---|
| api-prod-hcm-01 | API production, vùng HCM, máy số 01 |
| worker-dev-02 | Worker development, máy số 02 |
| db-staging-01 | Database staging, máy số 01 |

Đây chỉ là quy ước minh họa. Nếu hệ thống có nhiều region hoặc account, nên xác định rõ thành phần nào của tên là duy nhất trong phạm vi DNS zone. Tránh đặt tên chứa tên cá nhân, số tài khoản, địa chỉ IP công khai hoặc dữ liệu bí mật.

### 5.1. Cấu hình hostname trên Linux

Trên các distro dùng systemd, hostname có thể được xem và thay đổi bằng hostnamectl:

~~~bash
# Xem hostname hiện tại
hostnamectl status

# Đặt hostname tĩnh
sudo hostnamectl set-hostname api-prod-hcm-01

# Xác nhận
hostname
hostname -f
~~~

hostname -f chỉ trả FQDN nếu hệ thống có cấu hình phân giải phù hợp. Việc đặt hostname không tự tạo A record trong DNS. Cần cập nhật zone hoặc dùng cơ chế đăng ký DNS được quản lý.

### 5.2. Cấu hình hostname trên Windows Server

PowerShell có thể xem và đổi tên máy:

~~~powershell
# Xem hostname hiện tại
hostname

# Đổi tên máy và yêu cầu khởi động lại
Rename-Computer -NewName "api-prod-hcm-01" -Restart
~~~

Trong domain, cần kiểm tra quy trình đổi tên computer account, DNS registration và thời điểm khởi động lại. Không nên thay hostname thủ công nếu hệ thống quản lý cấu hình hoặc domain policy đang kiểm soát tên máy.

### 5.3. Hostname, DNS và DHCP

DHCP có thể cung cấp địa chỉ IP, DNS resolver, search domain và một số tùy chọn hostname. Một số môi trường hỗ trợ client đăng ký DNS động khi nhận lease; môi trường khác để cloud control plane hoặc hệ thống quản trị cập nhật record. Hành vi phụ thuộc DHCP server, hệ điều hành, cloud provider và chính sách DNS.

Vì vậy, cần xác định rõ nguồn sự thật cho hostname và record:

- Hệ điều hành tự đăng ký DNS.
- DHCP server cập nhật DNS khi cấp lease.
- Cloud control plane tạo record theo instance metadata.
- Pipeline IaC hoặc configuration management cập nhật zone.
- Service registry đăng ký endpoint khi ứng dụng khởi động.

Tránh để nhiều hệ thống cùng ghi một record mà không có quy tắc ưu tiên, vì chúng có thể ghi đè lẫn nhau hoặc tạo record cũ.

## 6. DNS public và private trong cloud

Public DNS cung cấp tên có thể phân giải từ Internet. Private DNS chỉ được phân giải trong phạm vi mạng được phép, chẳng hạn VPC/VNet, mạng doanh nghiệp hoặc kết nối hybrid.

| Tiêu chí | Public DNS | Private DNS |
|---|---|---|
| Phạm vi truy vấn | Internet hoặc resolver công cộng | Mạng nội bộ hoặc resolver được liên kết |
| Tên thường dùng | api.example.com | api.prod.internal.example |
| Địa chỉ đích | Thường là public endpoint hoặc load balancer | Private IP, internal load balancer hoặc service endpoint |
| Rủi ro chính | Lộ thông tin endpoint, giả mạo hoặc chiếm quyền domain | Rò rỉ tên nội bộ, cấu hình split-horizon sai, truy cập chéo mạng |
| Quản trị | Registrar, authoritative DNS provider | Cloud private zone, DNS doanh nghiệp hoặc hệ thống nội bộ |

### 6.1. Private hosted zone hoặc private DNS zone

Cloud provider thường cung cấp private DNS zone có thể liên kết với một hoặc nhiều mạng ảo. VM trong các mạng được liên kết có thể truy vấn tên nội bộ và nhận private IP hoặc endpoint nội bộ. Cách liên kết, giới hạn số zone và điều kiện phân giải khác nhau giữa các nền tảng.

Ví dụ, zone internal.example có record:

~~~dns
api.prod.internal.example.  60  IN  A  10.20.4.15
db.prod.internal.example.   60  IN  A  10.20.8.10
cache.prod.internal.example. 60 IN  A  10.20.9.25
~~~

Đây là zone file minh họa. Các IP thuộc dải private và chỉ có ý nghĩa trong mạng được định tuyến phù hợp. Không công bố record nội bộ ra public zone nếu không có yêu cầu rõ ràng.

### 6.2. Split-horizon DNS

Split-horizon DNS (còn gọi split-view DNS) trả lời khác nhau tùy vị trí hoặc resolver của người truy vấn. Ví dụ, api.example.com có thể trả public load balancer cho người dùng Internet và private load balancer cho máy trong mạng doanh nghiệp.

Mô hình này giúp client nội bộ đi theo đường mạng riêng và giảm lưu lượng vòng qua Internet. Tuy nhiên, cần quản lý hai bộ dữ liệu nhất quán, kiểm tra resolver nào được dùng và tránh để client nội bộ nhận public IP khi cần truy cập private endpoint.

### 6.3. DNS giữa nhiều VPC/VNet và mạng doanh nghiệp

Trong kiến trúc nhiều mạng ảo, private zone có thể cần liên kết với nhiều VPC/VNet, hoặc dùng resolver forwarding để tra cứu tên giữa các mạng. Peering hoặc transit network chỉ cung cấp đường định tuyến; khả năng phân giải DNS có thể cần cấu hình riêng.

Trong môi trường hybrid, DNS forwarding thường được dùng để:

- Chuyển truy vấn tên nội bộ cloud tới resolver của doanh nghiệp.
- Chuyển truy vấn zone cloud từ mạng on-premises tới inbound resolver trong cloud.
- Dùng conditional forwarding cho từng domain.
- Giữ khả năng phân giải tên khi workload di chuyển giữa trung tâm dữ liệu và cloud.

Không nên mặc định rằng kết nối VPN hoặc private link tự động làm DNS hai phía nhìn thấy nhau. Cần cấu hình route, firewall UDP/TCP port 53, resolver endpoint, forwarding rule và quyền liên kết zone phù hợp.

## 7. TTL, cache và thời gian cập nhật DNS

Mỗi record DNS thường có TTL (Time To Live), chỉ khoảng thời gian resolver được phép cache câu trả lời. TTL tính bằng giây.

TTL thấp giúp client nhận thay đổi nhanh hơn sau khi cache hết hạn, nhưng làm tăng số truy vấn tới resolver và authoritative DNS. TTL cao giảm tải DNS nhưng khiến client có thể tiếp tục dùng IP cũ lâu hơn sau khi record thay đổi.

Ví dụ:

| TTL | Hành vi thường thấy | Khi cân nhắc |
|---|---|---|
| 30–60 giây | Cache ngắn, cập nhật có thể nhanh hơn | Endpoint thay đổi thường xuyên, cần chuyển đổi nhanh |
| 300 giây | Cân bằng giữa cache và khả năng cập nhật | Dịch vụ nội bộ có thay đổi định kỳ |
| 3600 giây | Cache dài hơn, ít truy vấn hơn | Tên ổn định, ít thay đổi |

TTL không bảo đảm mọi client sẽ cập nhật chính xác sau đúng số giây. Ứng dụng có thể cache DNS riêng; JVM hoặc runtime có thể có DNS cache policy; proxy, service mesh và resolver trung gian cũng có thể giữ kết quả. Một số hệ thống còn cache lỗi âm (negative caching) khi tên không tồn tại.

Khi thay IP của dịch vụ, quy trình an toàn thường là:

1. Giảm TTL trước thời điểm chuyển đổi đủ lâu để cache cũ hết hạn.
2. Chuẩn bị endpoint mới và kiểm tra kết nối.
3. Cập nhật record hoặc registry.
4. Theo dõi truy vấn, kết nối và lỗi từ client.
5. Giữ endpoint cũ trong thời gian chuyển tiếp nếu có thể.
6. Chỉ gỡ endpoint cũ sau khi xác nhận client đã chuyển.

Không nên giảm TTL xuống cực thấp vĩnh viễn nếu không cần thiết. TTL cần cân bằng giữa tốc độ chuyển đổi và tải hệ thống DNS.

## 8. Service discovery là gì?

Service discovery là cơ chế cho phép client tìm được địa chỉ và thông tin kết nối của dịch vụ mà không cần biết trước từng instance. Hệ thống có thể tìm endpoint bằng DNS, registry API, metadata của nền tảng hoặc cấu hình tĩnh.

Một service discovery system thường cần quản lý:

- Tên dịch vụ và định danh instance.
- Địa chỉ IP, port và protocol.
- Trạng thái đăng ký, heartbeat hoặc health.
- Metadata như region, zone, version và nhóm tải.
- Thời điểm đăng ký, hết hạn và deregister.
- Quyền truy cập và phạm vi nhìn thấy của client.

Ví dụ, service orders-api có ba instance:

| Instance | Endpoint | Zone | Trạng thái |
|---|---|---|---|
| orders-01 | 10.20.4.11:8080 | zone-a | Healthy |
| orders-02 | 10.20.5.12:8080 | zone-b | Healthy |
| orders-03 | 10.20.6.13:8080 | zone-c | Unhealthy |

Client chỉ nên nhận endpoint healthy. Nếu dùng DNS thuần, cần cơ chế cập nhật record hoặc DNS health check phù hợp; DNS record tự nó không chứng minh service đang khỏe.

## 9. Các mô hình service discovery

### 9.1. Cấu hình tĩnh

Client được cấu hình trực tiếp hostname hoặc IP của dịch vụ. Cách này đơn giản và phù hợp với số lượng endpoint ít, ít thay đổi hoặc môi trường lab. Khi instance thay đổi, người vận hành phải cập nhật cấu hình và triển khai lại client.

Không nên dùng danh sách IP tĩnh cho hệ thống autoscaling hoặc nhiều vùng nếu có cơ chế discovery tốt hơn.

### 9.2. DNS-based discovery

Client tra cứu service name bằng DNS và nhận một hoặc nhiều record. Cách này đơn giản, tương thích với hầu hết ngôn ngữ và hệ điều hành. DNS có thể trả một load balancer endpoint hoặc nhiều instance.

Ưu điểm là client chỉ cần resolver tiêu chuẩn. Hạn chế là cache và TTL làm thay đổi endpoint không tức thời; DNS cũng không tự cung cấp metadata phong phú hoặc bảo đảm health-aware routing nếu nền tảng không bổ sung tính năng đó.

### 9.3. Registry-based discovery

Service registry lưu thông tin instance đang cung cấp dịch vụ. Khi khởi động, instance đăng ký endpoint; khi dừng, instance deregister hoặc heartbeat hết hạn. Client có thể truy vấn registry để lấy danh sách endpoint.

Registry thường hỗ trợ health check, metadata và lọc theo region/zone/version. Đổi lại, hệ thống cần vận hành registry, bảo vệ API, xử lý heartbeat, consistency và khả năng registry bị lỗi.

Các công cụ phổ biến có thể cung cấp service registry hoặc discovery gồm Consul và một số nền tảng điều phối, service mesh hay cloud service catalog. Chọn công cụ theo môi trường và khả năng tích hợp, không triển khai registry riêng nếu nền tảng đã cung cấp discovery đủ dùng.

### 9.4. Load balancer làm điểm discovery

Client gọi một hostname ổn định của load balancer. Load balancer theo dõi target health và phân phối request tới instance khỏe mạnh. Đây là mô hình server-side discovery: client không cần biết từng backend.

Mô hình này phù hợp với HTTP API, TCP service và nhiều ứng dụng cần endpoint ổn định. Cần hiểu health check, connection draining, timeout, session persistence và giới hạn của load balancer.

### 9.5. Client-side và server-side discovery

| Mô hình | Cách hoạt động | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Client-side discovery | Client tra registry/DNS, chọn endpoint rồi kết nối trực tiếp | Có thể tùy biến lựa chọn instance, vùng và retry | Client phải tích hợp discovery, cache và load balancing |
| Server-side discovery | Client gọi endpoint ổn định; proxy/load balancer chọn backend | Client đơn giản, chính sách tập trung | Thêm lớp trung gian và phụ thuộc vào load balancer/proxy |

Một hệ thống có thể kết hợp cả hai: DNS tìm load balancer, còn load balancer dùng registry hoặc target group để tìm backend.

## 10. Service discovery trong container và Kubernetes

Container thường được tạo và thay thế thường xuyên. Địa chỉ IP container có thể thay đổi khi restart hoặc reschedule, vì vậy ứng dụng nên gọi tên service thay vì lưu IP container.

### 10.1. DNS trong Docker Compose

Trong một mạng Compose do người dùng định nghĩa, service thường có thể được tìm thấy bằng tên service. Ví dụ, ứng dụng web kết nối tới hostname db trên port database mà không cần biết IP container hiện tại.

~~~yaml
services:
  web:
    image: example/web:v1
    environment:
      DATABASE_HOST: db
      DATABASE_PORT: "5432"
    depends_on:
      - db
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
secrets:
  db_password:
    file: ./secrets/db_password.txt
~~~

Ví dụ minh họa cách dùng service name db trong mạng Compose. depends_on điều khiển thứ tự khởi tạo ở mức Compose nhưng không tự bảo đảm database đã sẵn sàng nhận kết nối. Ứng dụng vẫn cần retry kết nối có giới hạn và health check. Cách cấp secret trong production nên dùng secret manager hoặc cơ chế secret của nền tảng phù hợp.

### 10.2. DNS của Kubernetes

Kubernetes cung cấp DNS cluster thông qua thành phần như CoreDNS. Khi tạo Service, cluster DNS thường tạo tên có dạng:

~~~text
<service>.<namespace>.svc.<cluster-domain>
~~~

Ví dụ, Service tên orders-api trong namespace production có thể được truy cập bằng:

~~~text
orders-api.production.svc.cluster.local
~~~

Tên ngắn orders-api có thể được phân giải trong cùng namespace nhờ search domain trong cấu hình DNS của Pod. Từ namespace khác, nên dùng tên đầy đủ hoặc ít nhất service.namespace để tránh nhầm tên.

Ví dụ Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
  namespace: production
spec:
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
  type: ClusterIP
~~~

Service ClusterIP cung cấp địa chỉ ổn định trong cluster. EndpointSlice theo dõi các endpoint backend phù hợp với selector và trạng thái sẵn sàng. Client gọi service DNS name; kube-proxy hoặc dataplane tương ứng chuyển traffic tới backend.

### 10.3. Headless Service và StatefulSet

Headless Service đặt clusterIP là None. Thay vì cung cấp một địa chỉ service ảo, DNS có thể trả các địa chỉ Pod phù hợp. Cách này hữu ích khi client cần khám phá từng replica, ví dụ database cluster hoặc hệ thống phân tán cần danh tính node ổn định.

StatefulSet cung cấp danh tính mạng ổn định cho Pod theo ordinal và thường kết hợp với headless Service. Ví dụ một Pod có thể có tên orders-db-0.orders-db.production.svc.cluster.local. Tên này giúp node khác tìm đúng thành viên, nhưng không tự bảo đảm node đang khỏe; ứng dụng vẫn cần health check và cơ chế cluster membership.

### 10.4. SRV record trong Kubernetes

Với Service có named port, Kubernetes DNS có thể cung cấp SRV record cho client cần tìm port và protocol. Client cần hỗ trợ tra cứu SRV; nếu không, hãy cấu hình port rõ ràng.

### 10.5. DNS policy của Pod

Pod có thể dùng DNS policy mặc định của cluster, dùng host network với cấu hình phù hợp hoặc dùng nameserver/search domain tùy chỉnh. Các trường dnsPolicy và dnsConfig cho phép điều chỉnh hành vi. Thay đổi DNS policy có thể làm Pod không phân giải được service nội bộ hoặc domain bên ngoài; cần kiểm thử trước khi áp dụng rộng rãi.

## 11. Service registry và vòng đời instance

Registry cần xử lý việc instance khởi động, khỏe mạnh, mất kết nối và dừng. Một vòng đời điển hình:

1. Instance khởi động và kiểm tra các dependency cần thiết.
2. Instance đăng ký service name, endpoint và metadata.
3. Health check xác nhận instance có thể nhận traffic.
4. Client hoặc proxy lấy danh sách endpoint phù hợp.
5. Instance gửi heartbeat hoặc được health check định kỳ.
6. Khi shutdown, instance ngừng nhận tải và deregister.
7. Nếu instance biến mất đột ngột, lease hoặc health check hết hạn để registry loại endpoint.

Nếu heartbeat timeout quá ngắn, mạng chập chờn có thể làm instance bị đánh dấu unhealthy nhầm. Nếu timeout quá dài, endpoint lỗi có thể tồn tại trong registry lâu. Cần cân bằng theo thời gian phát hiện lỗi và khả năng chịu gián đoạn.

### 11.1. Đăng ký và hủy đăng ký phải idempotent

Một instance có thể khởi động lại hoặc nhận nhiều sự kiện đăng ký. Registry nên xử lý đăng ký lặp mà không tạo nhiều bản ghi không cần thiết. Tương tự, deregister lặp không nên làm hỏng trạng thái. Dùng instance ID hoặc service instance ID ổn định trong vòng đời tiến trình.

### 11.2. Kết hợp discovery với graceful shutdown

Khi instance sắp dừng, nên chuyển nó sang trạng thái draining hoặc deregister trước khi kết thúc. Điều này liên kết trực tiếp với graceful shutdown: discovery không nên tiếp tục quảng bá một endpoint đã ngừng nhận request. Tuy nhiên, cần giữ endpoint đủ lâu để request hiện tại hoàn tất và tính đến cache ở client.

## 12. Cân bằng tải và lựa chọn endpoint

DNS có thể trả về nhiều địa chỉ cho cùng một tên, nhưng không phải lúc nào cũng là load balancer hoàn chỉnh. Resolver có thể sắp xếp hoặc cache danh sách địa chỉ; client có thể chỉ chọn địa chỉ đầu tiên; một số client có thuật toán thử lần lượt hoặc chọn ngẫu nhiên.

Khi cần phân phối tải có kiểm soát, nên cân nhắc:

- Load balancer ở lớp mạng hoặc ứng dụng.
- Service mesh proxy.
- Client-side load balancing với health-aware registry.
- DNS weighted/latency routing nếu phù hợp với kiến trúc.

DNS round-robin đơn giản không bảo đảm phân phối đều, không tự phát hiện backend đang lỗi và không theo dõi số kết nối đang mở. Với dịch vụ quan trọng, hãy dùng cơ chế health-aware routing và connection draining.

## 13. Chẩn đoán DNS và service discovery

Khi ứng dụng không kết nối được tới một service name, cần kiểm tra theo từng lớp thay vì kết luận ngay rằng DNS bị lỗi.

### 13.1. Kiểm tra trên Linux

~~~bash
# Xem hostname và FQDN
hostnamectl status
hostname -f

# Xem DNS resolver đang được cấu hình
cat /etc/resolv.conf

# Tra cứu A/AAAA record
dig api.prod.internal.example A
dig api.prod.internal.example AAAA

# Xem câu trả lời ngắn gọn
dig +short api.prod.internal.example

# Tra cứu qua resolver cụ thể
dig @10.20.0.2 api.prod.internal.example

# Kiểm tra kết nối TCP tới endpoint
nc -vz api.prod.internal.example 443

# Kiểm tra resolver qua NSS
getent hosts api.prod.internal.example
~~~

Trong một số distro, /etc/resolv.conf được systemd-resolved hoặc NetworkManager quản lý; nội dung có thể trỏ tới resolver cục bộ. Thay đổi trực tiếp file này có thể bị ghi đè. Hãy dùng công cụ quản trị mạng tương ứng.

### 13.2. Kiểm tra trên Windows

~~~powershell
# Xem cấu hình DNS của card mạng
Get-DnsClientServerAddress

# Tra cứu tên
Resolve-DnsName api.prod.internal.example

# Xem cache DNS cục bộ
Get-DnsClientCache

# Xóa cache resolver cục bộ khi cần kiểm tra lại
Clear-DnsClientCache

# Kiểm tra kết nối tới port dịch vụ
Test-NetConnection api.prod.internal.example -Port 443
~~~

Xóa cache chỉ ảnh hưởng resolver cache trên máy đang chạy lệnh; nó không xóa cache của recursive resolver hoặc ứng dụng. Không nên flush cache như bước khắc phục mặc định nếu chưa xác định nguyên nhân.

### 13.3. Cây chẩn đoán

~~~mermaid
flowchart TD
    A["Ứng dụng không kết nối được service name"] --> B{"Tên có phân giải được?"}
    B -- "Không" --> C["Kiểm tra hostname, search domain và resolver"]
    C --> D["Kiểm tra zone, record, forwarding và quyền liên kết"]
    B -- "Có" --> E{"IP có đúng endpoint mong đợi?"}
    E -- "Không" --> F["Kiểm tra TTL, cache, split DNS và record cũ"]
    E -- "Có" --> G{"Kết nối tới port thành công?"}
    G -- "Không" --> H["Kiểm tra route, firewall, security group và listener"]
    G -- "Có" --> I["Kiểm tra TLS, giao thức, health và ứng dụng"]
~~~

### 13.4. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| NXDOMAIN | Tên không tồn tại trong zone được truy vấn | Kiểm tra chính tả, zone, search suffix và record |
| SERVFAIL | Resolver không lấy được câu trả lời hợp lệ | Kiểm tra authoritative server, DNSSEC, forwarding và mạng |
| Timeout khi truy vấn | Không tới được resolver hoặc firewall chặn | Kiểm tra route, UDP/TCP 53 và resolver address |
| Trả IP cũ | Cache chưa hết TTL hoặc ứng dụng tự cache | Kiểm tra TTL ở từng lớp và cache policy |
| Máy nội bộ nhận public IP | Split-horizon hoặc private zone không áp dụng | Kiểm tra resolver và liên kết private zone |
| Tên phân giải được nhưng kết nối lỗi | Route, firewall, port hoặc service không lắng nghe | Dùng nc/Test-NetConnection và kiểm tra backend |
| Một số Pod không phân giải được | DNS policy, CoreDNS, NetworkPolicy hoặc node issue | Kiểm tra Pod resolv.conf, CoreDNS và EndpointSlice |

## 14. Bảo mật DNS và service discovery

DNS và service registry có thể tiết lộ topology, tên hệ thống, vùng triển khai và các dịch vụ nội bộ. Nếu bị sửa trái phép, client có thể kết nối tới endpoint của kẻ tấn công hoặc dịch vụ giả mạo.

Các biện pháp cần cân nhắc:

- Phân tách public zone và private zone.
- Giới hạn quyền tạo, sửa và xóa record theo zone và vai trò.
- Bảo vệ API quản lý DNS bằng IAM/RBAC và MFA.
- Giám sát thay đổi record, delegation và resolver rule.
- Dùng DNSSEC khi cần xác thực tính toàn vẹn dữ liệu DNS trên các đường phân giải được hỗ trợ.
- Dùng TLS/mTLS để xác thực service endpoint; DNS không thay thế xác thực ứng dụng.
- Giới hạn truy cập recursive resolver để tránh open resolver và DNS amplification.
- Theo dõi truy vấn bất thường, tunneling hoặc exfiltration qua DNS.
- Không đưa thông tin nhạy cảm vào hostname, TXT record hoặc service metadata.

### 14.1. DNSSEC, DoT và DoH

DNSSEC dùng chữ ký số để xác thực tính toàn vẹn và nguồn gốc dữ liệu DNS trong chuỗi xác thực. DNSSEC không mã hóa nội dung truy vấn và không bảo đảm endpoint trả về là ứng dụng an toàn.

DNS over TLS (DoT) và DNS over HTTPS (DoH) mã hóa kênh giữa client và resolver. Chúng giúp giảm khả năng quan sát hoặc sửa truy vấn trên đường truyền, nhưng cần quản lý resolver, policy và logging phù hợp. Trong mạng doanh nghiệp, việc bật DoH ngoài kiểm soát có thể làm truy vấn bỏ qua DNS filtering hoặc split-horizon nội bộ.

### 14.2. DNS không phải cơ chế xác thực

Một record A hoặc CNAME chỉ cho biết tên được ánh xạ tới địa chỉ hoặc tên khác. Nó không chứng minh server sở hữu đúng danh tính dịch vụ. Với giao tiếp quan trọng, hãy dùng TLS certificate, mTLS, workload identity hoặc cơ chế xác thực phù hợp.

## 15. Thiết kế DNS cho hệ thống nhiều môi trường

Một tổ chức có thể có dev, staging và production trong các VPC/VNet khác nhau. Nên xác định quy tắc tên và phạm vi phân giải rõ ràng:

| Môi trường | Zone ví dụ | Service name |
|---|---|---|
| Development | dev.internal.example | orders-api.dev.internal.example |
| Staging | staging.internal.example | orders-api.staging.internal.example |
| Production | prod.internal.example | orders-api.prod.internal.example |

Có thể dùng một private zone chung với nhãn môi trường hoặc tách zone theo môi trường. Tách zone giúp ranh giới quản trị rõ hơn; zone chung giúp giảm số lượng cấu hình nhưng đòi hỏi quy ước tên và phân quyền cẩn thận.

Không nên để dev resolver có quyền truy vấn hoặc cập nhật record production nếu không cần thiết. Quyền liên kết private zone, quyền thay đổi record và quyền truy cập network cần được quản lý cùng nhau.

## 16. Ví dụ thực tế: các service trong ứng dụng thương mại điện tử

Một hệ thống thương mại điện tử có API gateway, catalog API, orders API, database và cache. Các thành phần chạy trong nhiều subnet private và có thể scale độc lập.

Một thiết kế tham khảo:

| Service | Tên logic | Endpoint được công bố | Cách discovery |
|---|---|---|---|
| API gateway | api.example.com | Public load balancer | Public DNS |
| Catalog API | catalog.prod.internal.example | Internal load balancer | Private DNS |
| Orders API | orders.prod.internal.example | Internal load balancer | Private DNS |
| Database | db.prod.internal.example | Private database endpoint | Private DNS do dịch vụ quản lý |
| Cache | cache.prod.internal.example | Private cache endpoint | Private DNS hoặc registry |

Client gọi catalog và orders bằng tên dịch vụ. Load balancer chọn backend healthy. Database và cache không được công khai ra Internet; security group chỉ cho phép các workload cần thiết kết nối tới port tương ứng.

Khi một orders API instance bị scale-in, nó chuyển sang draining và bị loại khỏi backend pool. DNS name orders.prod.internal.example không cần đổi vì nó trỏ tới internal load balancer ổn định. Khi database endpoint chuyển sang địa chỉ mới, private DNS record hoặc endpoint do nhà cung cấp quản lý được cập nhật; client phải xử lý DNS cache, connection retry và reconnect.

Thiết kế này tách ba trách nhiệm: DNS cung cấp tên ổn định, load balancer phân phối traffic tới backend khỏe mạnh, còn ứng dụng quản lý timeout, retry và xác thực kết nối.

## 17. Quy trình triển khai DNS và service discovery

Có thể áp dụng quy trình sau:

1. **Kiểm kê dịch vụ:** xác định service name, port, protocol, owner, môi trường và dependency.
2. **Đặt quy tắc tên:** chọn hostname, FQDN, private/public zone và search domain.
3. **Chọn mô hình discovery:** DNS tĩnh, DNS động, registry, load balancer hoặc discovery tích hợp của orchestrator.
4. **Thiết kế vòng đời record:** ai đăng ký, cập nhật, health-check và deregister endpoint.
5. **Chọn TTL:** cân bằng giữa cache, tốc độ thay đổi và tải resolver.
6. **Cấu hình kết nối mạng:** route, firewall, private zone association và DNS forwarding.
7. **Bảo vệ quyền:** phân quyền quản lý zone, resolver và registry; dùng TLS cho kết nối dịch vụ.
8. **Kiểm thử:** phân giải từ từng subnet/namespace, kiểm tra port, failover và cache.
9. **Giám sát:** theo dõi lỗi DNS, độ trễ truy vấn, record cũ và thay đổi bất thường.
10. **Vận hành:** rà soát record không còn dùng, cập nhật tài liệu và kiểm tra định kỳ.

## 18. Những sai lầm thường gặp

- **Hard-code IP trong ứng dụng:** làm tăng công sức khi thay máy hoặc scale.
- **Cho rằng đổi hostname tự cập nhật DNS:** cần có cơ chế đăng ký hoặc cập nhật record rõ ràng.
- **Dùng public DNS cho service nội bộ:** có thể làm lộ topology hoặc tạo đường truy cập không mong muốn.
- **Đặt TTL quá dài cho endpoint thay đổi thường xuyên:** client có thể tiếp tục dùng IP cũ.
- **Đặt TTL cực thấp cho mọi record:** làm tăng truy vấn và tải resolver không cần thiết.
- **Coi DNS round-robin là health-aware load balancing:** DNS không tự kiểm tra backend nếu không có cơ chế bổ sung.
- **Cho rằng VPN/peering tự động nối DNS:** định tuyến mạng và phân giải tên là hai phần cần cấu hình riêng.
- **Không tính cache trong ứng dụng:** thay record nhưng client vẫn giữ địa chỉ cũ.
- **Không deregister instance khi shutdown:** client có thể tiếp tục kết nối tới endpoint đang dừng.
- **Dùng DNS làm xác thực:** tên phân giải đúng không chứng minh server đáng tin cậy.
- **Để nhiều hệ thống cùng ghi record:** dễ tạo dữ liệu cũ hoặc ghi đè ngoài ý muốn.

## 19. Ghi nhớ

Hostname nhận diện máy; FQDN định vị tên trong hệ thống DNS; DNS phân giải tên thành địa chỉ hoặc thông tin dịch vụ; service discovery tìm endpoint đang hoạt động để client kết nối. Trong cloud, private DNS, resolver forwarding, service registry và DNS tích hợp của container orchestrator giúp workload tìm thấy nhau khi VM hoặc container thay đổi.

Để hệ thống hoạt động ổn định, cần đặt quy tắc tên nhất quán, quản lý record và TTL theo vòng đời workload, tách public/private DNS, cấu hình forwarding giữa các mạng, phối hợp discovery với health check và graceful shutdown, đồng thời dùng TLS hoặc cơ chế danh tính để xác thực dịch vụ. Khi chẩn đoán, hãy kiểm tra lần lượt phân giải tên, địa chỉ trả về, route, firewall, port và trạng thái ứng dụng.
