# Kết nối hàm với mạng riêng và dịch vụ phụ thuộc

Serverless giúp triển khai hàm hoặc ứng dụng mà không phải tự quản lý máy chủ. Tuy vậy, workload vẫn cần giao tiếp với database, cache, message broker, API nội bộ, hệ thống on-premises hoặc dịch vụ cloud khác. Khi các dependency chỉ được phép truy cập qua mạng riêng, cần thiết kế đường đi từ execution environment của function đến đúng subnet, route, DNS, firewall và endpoint.

Một function có thể chạy thành công khi chỉ gọi dịch vụ công khai nhưng thất bại ngay khi kết nối database private. Ngược lại, chỉ gắn function vào VPC/VNet cũng chưa bảo đảm kết nối được: subnet có thể thiếu route, security group chặn cổng, DNS phân giải sai, NAT không có, private endpoint chưa được tạo hoặc identity không đủ quyền.

Bài học tập trung vào cách kết nối serverless function với mạng riêng và các dependency trong môi trường cloud. Bạn sẽ phân biệt inbound và outbound connectivity, hiểu các mô hình VPC/VNet integration, kiểm soát egress, lựa chọn private endpoint, quản lý DNS và identity, đồng thời thiết kế khả năng sẵn sàng, capacity và quan sát cho đường mạng.

Sau bài học, bạn có thể:

- Mô tả luồng mạng từ function đến database, cache, API nội bộ và dịch vụ cloud.
- Phân biệt VPC/VNet integration, private endpoint, service endpoint và NAT/egress gateway.
- Chọn subnet, route table, security group/firewall và DNS phù hợp.
- Giải thích vì sao function đã gắn mạng riêng vẫn có thể không truy cập được dependency.
- Thiết kế kết nối đến on-premises hoặc mạng khác qua VPN/private connectivity.
- Quản lý identity, secret, TLS và quyền truy cập theo least privilege.
- Đánh giá tác động của concurrency, connection pool, ephemeral port và IP exhaustion.
- Kiểm thử và troubleshooting bằng log, trace, flow log, DNS log và các phép đo kết nối.

## 1. Vì sao serverless cần mạng riêng?

Serverless loại bỏ phần lớn công việc quản lý máy chủ, nhưng không loại bỏ network boundary. Function vẫn được thực thi trên hạ tầng do provider quản lý và phải tuân theo mô hình mạng mà nền tảng cung cấp.

Các dependency thường gặp:

| Dependency | Ví dụ | Nhu cầu kết nối |
|---|---|---|
| Database | PostgreSQL, MySQL, SQL Server, managed relational database | Private IP, private DNS, TLS, port database |
| Cache | Redis hoặc managed cache | Private subnet, TCP port, authentication/TLS |
| Internal API | Dịch vụ nghiệp vụ trong VPC/VNet | Private load balancer, service discovery, HTTP/gRPC |
| Message broker | Kafka, RabbitMQ hoặc managed broker | Private endpoint, TLS, identity/credential |
| Object/file storage | Object storage, shared file service | Private endpoint hoặc controlled egress |
| Identity/secrets | Secret manager, token service, KMS | Private endpoint hoặc đường egress được cho phép |
| On-premises | ERP, legacy database, internal service | VPN, dedicated private connection hoặc gateway |
| Internet API | Payment gateway, SaaS API, public endpoint | NAT/egress, proxy, DNS và allow-list nếu cần |

Mạng riêng giúp giảm bề mặt phơi lộ, kiểm soát nguồn truy cập và đáp ứng yêu cầu dữ liệu. Tuy nhiên, private networking làm tăng số thành phần cần cấu hình và quan sát: subnet, route, DNS, endpoint, firewall, NAT, certificate và quyền truy cập.

### Một function có hai hướng giao tiếp

- **Inbound:** client, event source hoặc service gọi function. Với nhiều nền tảng serverless, provider nhận request hoặc event rồi dispatch đến execution environment; function không nhất thiết phải có private IP có thể truy cập trực tiếp từ Internet.
- **Outbound:** function chủ động kết nối đến database, API hoặc dịch vụ khác. Đây là phần thường cần VPC/VNet integration hoặc cơ chế egress tương đương.

Không được nhầm việc function có thể nhận request từ một endpoint công khai với việc execution environment có thể truy cập tài nguyên private. Hai luồng có thể được cấu hình và bảo vệ riêng.

## 2. Các khái niệm mạng cần nắm

### VPC và VNet

VPC (Virtual Private Cloud) hoặc VNet (Virtual Network) là mạng logic cô lập trong cloud. Mạng này chứa subnet, route table, security policy, gateway và các resource có địa chỉ IP private.

Một VPC/VNet thường có:

- CIDR block và subnet address range.
- Route table điều khiển next hop.
- Security group, network security group hoặc firewall.
- Internet/NAT gateway hoặc egress gateway.
- Private endpoint/service endpoint.
- DNS resolver và private DNS zone.
- Peering, transit gateway hoặc hub network để kết nối mạng khác.

### Subnet

Subnet là một dải địa chỉ IP thuộc VPC/VNet, thường được gắn với một availability zone hoặc fault domain. Subnet có thể được thiết kế cho workload application, database, private endpoint hoặc egress gateway.

Tên public/private subnet không tự quyết định khả năng truy cập. Điều quan trọng là route table, địa chỉ public, gateway và firewall. Một subnet được gọi là private thường không có route trực tiếp ra Internet gateway cho resource không có public address; nó có thể dùng NAT hoặc private endpoint để đi ra ngoài.

### Route table

Route table quyết định traffic đến prefix nào sẽ đi qua next hop nào. Ví dụ:

- CIDR nội bộ của VPC/VNet đi trong mạng.
- Prefix database private đi qua local route hoặc peering/transit.
- Internet destination đi qua NAT/egress gateway nếu được thiết kế.
- On-premises prefix đi qua VPN hoặc dedicated connection.
- Service prefix có thể được định tuyến qua service endpoint theo mô hình provider.

Route có thể tồn tại nhưng traffic vẫn bị chặn bởi firewall, security group, network ACL hoặc policy ở phía đích.

### Security group và network firewall

Security group thường là firewall stateful gắn với network interface/resource; rule cho phép traffic dựa trên protocol, port, source/destination. Network ACL hoặc subnet firewall ở một số nền tảng có thể là stateless, cần rule cho cả chiều đi và chiều về.

Cần phân biệt:

- Egress rule của function.
- Ingress rule của database/cache/API đích.
- Network ACL hoặc firewall giữa các subnet.
- Firewall ở hệ thống on-premises.
- Policy ở endpoint hoặc dịch vụ cloud.

Mở một port ở phía function không đủ nếu phía database chưa cho phép source tương ứng. Hãy giới hạn nguồn theo security group, subnet hoặc identity-aware policy thay vì mở rộng cho toàn bộ CIDR khi không cần.

## 3. Mô hình VPC/VNet integration cho serverless

Nhiều nền tảng cho phép function truy cập resource trong mạng riêng thông qua một cơ chế integration. Chi tiết triển khai khác nhau theo provider và loại dịch vụ.

### Mô hình khái niệm

~~~mermaid
flowchart LR
    E[Event source / Client] --> P[Serverless platform]
    P --> F[Function execution]
    subgraph VPC["Private network VPC / VNet"]
      S[Integration subnet]
      SG[Security policy]
      DB[(Private database)]
      C[(Private cache)]
      API[Internal API]
      S --> SG
      SG --> DB
      SG --> C
      SG --> API
    end
    F -. private network path .-> S
~~~

Function được nền tảng khởi chạy trong execution environment và có đường kết nối vào mạng riêng theo cơ chế integration. Tùy dịch vụ, provider có thể tạo network interface, dùng connector hoặc dataplane quản lý riêng. Người dùng thường cấu hình subnet, security group, connector hoặc network attachment thay vì quản lý một VM cố định.

### Những điểm cần xác minh

- Function có hỗ trợ VPC/VNet integration ở loại runtime/plan đang dùng không?
- Integration áp dụng cho mọi outbound traffic hay chỉ traffic đến private address?
- Có cần chọn nhiều subnet/zone không?
- Provider tạo network interface hoặc connector ở đâu?
- Có giới hạn số network interface, IP, connection hoặc concurrency không?
- Khi scale-out, việc cấp IP hoặc tạo network path có làm tăng startup latency không?
- Function có còn truy cập Internet trực tiếp sau khi attach không?
- Có thể chọn private DNS resolver hoặc custom DNS không?
- Việc tích hợp có ảnh hưởng đến inbound invocation không?

Không suy luận hành vi chỉ từ tên tính năng. Một số dịch vụ dùng VPC connector, một số gắn network interface vào subnet, một số cung cấp direct VPC egress. Hãy kiểm tra semantics của đúng sản phẩm, runtime, region và plan.

## 4. Phân biệt function network integration với private endpoint

Hai cơ chế này giải quyết hai phía khác nhau:

- **VPC/VNet integration:** đưa đường outbound của function vào hoặc qua mạng riêng để function có thể truy cập tài nguyên private.
- **Private endpoint/private link:** cung cấp một địa chỉ hoặc network interface private để client trong mạng được phép truy cập một dịch vụ cụ thể.

Ví dụ function trong subnet riêng có thể kết nối database qua private IP. Nếu function cần truy cập object storage managed service, có thể dùng private endpoint để traffic đi trên private network path thay vì đi qua Internet công cộng, tùy dịch vụ hỗ trợ.

### Service endpoint

Service endpoint là cơ chế mở rộng định tuyến hoặc policy để resource trong mạng truy cập một dịch vụ cloud qua backbone/private routing của provider. Nó khác private endpoint ở cách địa chỉ và đường truy cập được cung cấp. Tên gọi và semantics khác nhau theo cloud.

### Bảng so sánh

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| VPC/VNet integration | Kết nối execution environment với mạng riêng | Function gọi database private |
| Private endpoint/private link | Tạo đường truy cập private đến một dịch vụ | Function truy cập storage qua private IP endpoint |
| Service endpoint | Cho subnet truy cập dịch vụ provider qua tuyến/policy được hỗ trợ | Subnet truy cập object storage service |
| NAT gateway | Cho resource private mở kết nối outbound đến public destination | Function gọi API SaaS |
| VPN/dedicated connectivity | Kết nối VPC/VNet với mạng on-premises hoặc mạng khác | Function gọi ERP nội bộ |

Một hệ thống có thể cần nhiều cơ chế đồng thời. VPC integration không tự tạo private endpoint cho mọi dịch vụ; private endpoint cũng không tự đưa function vào VPC.

## 5. Chọn subnet và availability zone

Khi cấu hình function network integration, hãy chọn subnet có đủ địa chỉ IP, route và khả năng tiếp cận dependency.

### Subnet selection

Các nguyên tắc:

- Chọn subnet ở những zone có dependency hoặc đường mạng dự phòng.
- Dành CIDR đủ lớn cho network interface/connector và scale-out.
- Tránh dùng subnet đã gần cạn IP cho function có concurrency biến động.
- Không đặt function và database trong subnet cùng dải chỉ vì muốn “gần”; thiết kế subnet theo security boundary và vận hành.
- Kiểm tra subnet route table và network ACL.
- Đảm bảo subnet có thể truy cập DNS resolver, secret manager và telemetry endpoint cần thiết.

### IP exhaustion

Một số nền tảng cấp network interface hoặc địa chỉ private cho execution environment/connector. Khi function scale-out, số IP hoặc network attachment cần thiết có thể tăng. Subnet nhỏ hoặc chia sẻ với nhiều workload có thể hết IP, làm scale-out thất bại hoặc startup chậm.

Theo dõi:

- Số IP còn khả dụng trong từng subnet.
- Số interface/network attachment đã sử dụng.
- Concurrency và tốc độ scale-out của function.
- Lỗi cấp phát network interface.
- Số lần retry hoặc cold start tăng do network provisioning.

Không giả định một invocation luôn cần đúng một IP. Mapping giữa concurrency, execution environment, ENI/connector và IP phụ thuộc provider.

### Multi-zone

Nếu function và database cần chịu lỗi zone:

- Cấu hình integration trên nhiều subnet/zone khi nền tảng hỗ trợ.
- Đảm bảo dependency có endpoint hoặc replica ở các zone cần thiết.
- Tránh route hoặc firewall chỉ hoạt động trong một zone.
- Kiểm tra latency và phí cross-zone.
- Diễn tập mất một zone và xác minh function vẫn truy cập dependency.

Chỉ thêm subnet ở nhiều zone chưa tạo ra HA nếu database, NAT, DNS hoặc endpoint vẫn chỉ tồn tại ở một zone.

## 6. Route và egress: function đi ra đâu?

Khi function cần gọi dependency, phải biết destination thuộc loại nào và traffic được định tuyến ra sao.

### Private destination trong cùng VPC/VNet

Nếu database hoặc API có private IP trong cùng mạng, route nội bộ thường được cung cấp tự động. Tuy nhiên, cần security group/firewall cho phép đúng port và source.

Ví dụ:

- Function integration subnet: 10.20.10.0/24.
- Database subnet: 10.20.30.0/24.
- Database listener: TCP 5432.
- Security rule database cho phép source từ security group của function trên TCP 5432.

Các địa chỉ chỉ là ví dụ. Trong production, ưu tiên tham chiếu security group/resource identity khi provider hỗ trợ, giảm phụ thuộc vào CIDR thay đổi.

### Public destination qua NAT

Function nằm trong private subnet muốn gọi public API thường cần NAT hoặc egress gateway nếu nền tảng không cung cấp Internet egress khác.

Luồng:

~~~mermaid
flowchart LR
    F[Function] --> S[Private subnet]
    S --> R[Route table]
    R --> N[NAT / egress gateway]
    N --> I[Internet API]
    I --> N
    N --> F
~~~

NAT thường cho phép kết nối outbound từ private resource, đồng thời che private address bằng địa chỉ egress. NAT không tự cho phép kết nối inbound mới từ Internet đến function.

Cần kiểm tra:

- NAT gateway có route và capacity không?
- Có một NAT duy nhất trong một zone tạo single point of failure không?
- Public egress IP có ổn định để allow-list không?
- Có giới hạn port mapping hoặc concurrent connection không?
- Chi phí theo giờ và theo GB truyền có phù hợp không?
- DNS resolution có hoạt động trước khi kết nối không?

### Không có NAT không đồng nghĩa không có outbound

Nếu workload chỉ cần truy cập resource private hoặc dịch vụ cloud qua private endpoint/service endpoint, có thể không cần NAT cho các đường đó. Hãy liệt kê toàn bộ destination và chọn đường mạng cho từng loại thay vì mặc định mọi traffic đều phải qua Internet.

### Egress allow-list

Một số tổ chức chỉ cho phép function gọi các destination đã duyệt. Có thể thực hiện bằng firewall, NAT egress IP, proxy hoặc network policy theo khả năng nền tảng.

Không chỉ lọc theo hostname nếu firewall chỉ hỗ trợ IP; SaaS endpoint có thể thay đổi IP. Cần chọn cơ chế phù hợp như FQDN-aware firewall, proxy hoặc service tag nếu provider hỗ trợ.

## 7. DNS và private name resolution

Function có thể có route đến database nhưng vẫn thất bại nếu hostname không phân giải đúng.

### Private DNS zone

Private DNS zone cho phép hostname nội bộ ánh xạ đến private address. Ví dụ:

- db.orders.internal → 10.20.30.15
- cache.orders.internal → 10.20.31.12
- api.inventory.internal → private load balancer address

Function phải sử dụng resolver có thể nhìn thấy private zone đó. Nếu VPC/VNet chưa được associate với zone hoặc forwarding rule, function có thể nhận public address hoặc NXDOMAIN.

### Split-horizon DNS

Một hostname có thể trả về địa chỉ khác nhau tùy nơi truy vấn. Bên trong VPC trả private IP, bên ngoài trả public IP hoặc không phân giải được. Đây là mô hình hữu ích nhưng cần kiểm tra từ đúng execution environment.

### Hybrid DNS

Khi truy cập on-premises, DNS có thể cần conditional forwarding đến DNS resolver của tổ chức. Cần xác định:

- Zone nào authoritative ở cloud?
- Zone nào authoritative ở on-premises?
- Resolver nào nhận truy vấn?
- Forwarding có vòng lặp không?
- UDP/TCP 53 hoặc DNS over TLS/HTTPS có bị firewall chặn không?
- DNS cache/TTL có làm chậm failover không?

### Kiểm tra DNS

Từ một runtime hoặc môi trường test có cùng network path, kiểm tra:

- Hostname có resolve không?
- Kết quả có đúng private IP không?
- Resolver có ổn định ở nhiều subnet/zone không?
- Sau failover, TTL và cache có cập nhật phù hợp không?

Không dùng địa chỉ IP hardcode trong ứng dụng để né DNS lỗi lâu dài. Cần sửa private zone, resolver hoặc forwarding đúng cách.

## 8. Kết nối đến database private

Database là dependency phổ biến nhất của serverless function và cũng là nơi dễ bị quá tải khi concurrency tăng đột ngột.

### Đường kết nối

1. Function nhận event hoặc request.
2. DNS resolve database hostname.
3. Route chọn private path đến database subnet/endpoint.
4. Firewall/security group cho phép source và port.
5. TLS handshake và authentication diễn ra.
6. Driver lấy connection từ pool hoặc mở connection mới.
7. Query thực thi và response quay về function.

Mỗi bước có thể tạo latency hoặc lỗi riêng. Một lỗi timeout không nhất thiết do route; có thể do DNS, TLS, connection limit hoặc database quá tải.

### Connection storm

Serverless có thể scale execution environment nhanh. Nếu mỗi environment mở một pool lớn, tổng số database connection có thể vượt giới hạn.

Ví dụ: concurrency 200 và mỗi environment mở pool tối đa 10 connection tạo tiềm năng 2.000 connection. Con số thực tế phụ thuộc cách reuse environment, pool lifecycle và concurrency, nhưng cần tính theo tổng fleet chứ không chỉ một invocation.

Biện pháp:

- Giới hạn pool size theo capacity database.
- Tái sử dụng connection trong execution environment khi runtime cho phép.
- Đặt connection timeout và idle timeout phù hợp.
- Dùng managed database proxy hoặc connection pooling service nếu phù hợp.
- Giới hạn concurrency của function.
- Dùng queue/buffer để điều tiết burst.
- Tránh mở connection mới cho từng query hoặc từng invocation nếu có thể.
- Theo dõi active connections, pool wait, connection errors và query latency.

### Connection reuse

Trong runtime hỗ trợ reuse execution environment, khởi tạo client/connection pool ngoài handler có thể giảm overhead giữa các invocation. Tuy nhiên, environment có thể bị đóng bất kỳ lúc nào; connection cũ có thể hết hạn hoặc bị database failover. Ứng dụng cần phát hiện connection stale và reconnect an toàn.

### TLS và xác thực

- Bật TLS đến database nếu dịch vụ hỗ trợ.
- Xác minh certificate chain và hostname.
- Lấy credential từ secret manager hoặc dùng IAM/database authentication khi phù hợp.
- Rotation secret mà không buộc toàn bộ function cùng reconnect đồng thời.
- Không ghi connection string có password vào log.
- Giới hạn database user theo schema/table/action cần thiết.

## 9. Kết nối cache và message broker

### Cache private

Cache thường nằm trong subnet riêng. Function cần đúng route, port, security rule, DNS và authentication.

Cần đánh giá:

- Cache cluster có endpoint riêng cho primary/reader không?
- Failover có làm đổi DNS hoặc endpoint không?
- TLS/authentication được bật thế nào?
- Connection pool và idle timeout ra sao?
- Cache miss có thể làm database quá tải không?
- Concurrency burst có tạo nhiều client connection không?

Nếu cache là cache có thể tái tạo, cache outage có thể được xử lý bằng fallback có giới hạn. Không để mọi invocation cùng fallback trực tiếp vào database khi cache mất; cần concurrency control hoặc load shedding.

### Message broker

Kafka, RabbitMQ và managed queue có thể dùng private endpoint. Ngoài network reachability, cần kiểm tra protocol, TLS, SASL/identity, certificate, topic/queue permission và DNS.

Một function consumer có thể scale theo số message hoặc event. Nếu mỗi execution environment mở nhiều broker connection, broker cũng có thể bị quá tải. Giới hạn concurrency và connection, batch message phù hợp, và dùng retry/backoff.

### Tránh retry storm

Khi broker hoặc database tạm lỗi, hàng trăm invocation retry đồng thời có thể kéo dài outage. Dùng:

- Exponential backoff với jitter.
- Retry cap và deadline.
- Queue redrive/DLQ.
- Circuit breaker hoặc tạm dừng consumer.
- Concurrency limit.
- Alert theo queue age và dependency error rate.

## 10. Kết nối internal API và service discovery

Function có thể gọi service nội bộ qua private load balancer, service registry hoặc private DNS.

### Private load balancer

Internal load balancer cung cấp endpoint chỉ truy cập từ mạng được phép. Function integration subnet cần route đến load balancer, còn backend cần rule cho phép source tương ứng.

Kiểm tra:

- Listener port/protocol.
- Backend health và readiness.
- TLS termination và certificate.
- Host header/SNI nếu virtual hosting.
- Idle timeout và keep-alive.
- DNS record trỏ đúng endpoint.
- Network policy giữa function và backend.

### Service mesh và service discovery

Một số kiến trúc dùng service mesh, proxy hoặc service registry. Serverless function có thể không hỗ trợ sidecar model như container lâu dài; cần xác minh cách tích hợp. Có thể gọi qua gateway hoặc internal API endpoint được quản lý.

### Timeout end-to-end

Nếu function timeout 30 giây nhưng internal API có timeout 60 giây, function có thể bị kết thúc trước khi dependency hoàn tất. Đặt timeout theo thứ tự:

- DNS/connect timeout ngắn.
- TLS/connection timeout phù hợp.
- Request timeout thấp hơn function deadline.
- Tổng thời gian retry nằm trong invocation deadline.
- Cleanup và response buffer có thời gian dự phòng.

Không để function timeout khi dependency vẫn tiếp tục xử lý side effect mà client không biết kết quả. Dùng idempotency key cho thao tác có thể retry.

## 11. Kết nối đến on-premises hoặc mạng khác

Một function có thể cần truy cập ERP, file server hoặc database ở data center. Đường kết nối có thể qua VPN site-to-site, dedicated private connection, transit gateway hoặc hub-and-spoke network.

### Các thành phần cần chuẩn bị

- VPC/VNet address range không chồng lấn với on-premises.
- VPN gateway hoặc private circuit.
- Route propagation/static route phù hợp.
- Firewall ở cả hai phía.
- DNS forwarding và private zone.
- MTU, fragmentation và throughput.
- Redundancy cho tunnel/circuit.
- Monitoring tunnel, BGP route và packet loss.

### CIDR overlap

Nếu VPC/VNet dùng cùng dải IP với on-premises, routing có thể không xác định được đường đến đích. Lập kế hoạch IP address management trước khi triển khai, đặc biệt khi có nhiều account/project và nhiều region.

### Độ trễ và tính sẵn sàng

VPN hoặc dedicated circuit có thể mất kết nối. Function cần timeout, retry có giới hạn và fallback theo nghiệp vụ. Với job dài, đưa công việc vào queue và xử lý lại khi kết nối phục hồi thường an toàn hơn giữ invocation mở quá lâu.

Không giả định private connectivity luôn có latency thấp hoặc bandwidth vô hạn. Đo RTT, throughput và packet loss từ đúng network path.

## 12. Bảo vệ mạng bằng least privilege

Private networking giảm khả năng truy cập công khai nhưng không thay thế authorization. Một function trong subnet riêng vẫn có thể bị xâm nhập hoặc lạm dụng quyền nếu role quá rộng.

### Security group/firewall

- Chỉ cho phép function truy cập dependency cần thiết.
- Giới hạn ingress ở database theo nguồn cụ thể.
- Không mở toàn bộ subnet hoặc toàn VPC nếu không cần.
- Dùng security group reference hoặc resource identity khi provider hỗ trợ.
- Tách subnet/SG theo workload role và môi trường.
- Review egress rule; mặc định allow-all có thể làm mất ý nghĩa kiểm soát egress.

### Identity và secret

- Dùng execution role/managed identity/service account riêng cho function.
- Cấp quyền đọc đúng secret và đúng resource.
- Ưu tiên workload identity hoặc short-lived credential.
- Rotation secret/certificate có kế hoạch và tránh restart đồng loạt.
- Không nhúng credential trong source code, environment file hoặc deployment artifact nếu có cơ chế secret manager.
- Audit quyền đọc secret và thao tác key.

### TLS

Dùng TLS cho kết nối đến database, broker và internal API khi phù hợp. Kiểm tra certificate expiry, trust store và hostname validation. Không tắt certificate verification để xử lý lỗi môi trường.

### Phân đoạn mạng

Tách function theo nhóm quyền:

- Function xử lý đơn hàng có thể truy cập database đơn hàng và queue thanh toán.
- Function tạo báo cáo chỉ đọc dữ liệu báo cáo và ghi object vào bucket báo cáo.
- Function gửi thông báo có thể truy cập email/SMS provider nhưng không cần quyền database nghiệp vụ.

Phân đoạn giúp giới hạn phạm vi nếu một function bị khai thác.

## 13. Concurrency, ephemeral port và IP capacity

Serverless concurrency ảnh hưởng trực tiếp đến số kết nối mạng đồng thời. Tăng concurrency có thể tăng throughput nhưng cũng làm tăng socket, NAT port, connection pool, DNS query và áp lực lên dependency.

### Tính kết nối tiềm năng

Một phép ước lượng đơn giản:

~~~text
Potential dependency connections
  ≈ concurrent execution environments
    × connections per environment
~~~

Đây là ước lượng capacity planning, không phải công thức ánh xạ chính xác giữa invocation concurrency và network interface. Một environment có thể xử lý nhiều invocation đồng thời tùy runtime, còn provider có thể chia sẻ hoặc quản lý network attachment theo cách riêng.

### Ephemeral port và NAT

Kết nối outbound TCP cần source port tạm thời. NAT gateway/proxy có giới hạn mapping/port và connection tracking. Quá nhiều kết nối ngắn, thiếu reuse hoặc nhiều destination có thể gây port exhaustion hoặc lỗi kết nối.

Biện pháp:

- Reuse connection khi runtime cho phép.
- Dùng keep-alive và pool có giới hạn.
- Giảm số destination/connection không cần thiết.
- Giới hạn concurrency và batch request.
- Theo dõi NAT port allocation, active connection và error.
- Tách egress path hoặc tăng capacity theo hướng dẫn provider.

### Subnet IP exhaustion

Nếu nền tảng cấp IP/interface theo scale, subnet có thể hết địa chỉ. Cần dự trù IP cho function, private endpoint, database, node và các resource khác. Không chỉ tính số VM; tính cả network interface do service-managed integration tạo ra.

### Backpressure

Khi dependency không đủ capacity, function không nên tiếp tục scale vô hạn. Có thể dùng queue, reserved/max concurrency, rate limit hoặc load shedding để điều tiết lượng công việc. Theo dõi queue age và thời gian hoàn tất để tránh backlog tăng âm thầm.

## 14. Availability và resilience của đường mạng

Một function có thể chạy ở nhiều execution environment nhưng vẫn phụ thuộc vào một NAT gateway, một DNS resolver hoặc một database endpoint duy nhất.

Các điểm cần xem:

- Function integration có hỗ trợ nhiều subnet/zone không?
- NAT/egress gateway có dự phòng theo zone không?
- Private endpoint có đủ zone hoặc có cơ chế failover không?
- Database có multi-AZ/replica và endpoint ổn định không?
- DNS resolver có redundant path không?
- VPN/circuit có nhiều tunnel hoặc route dự phòng không?
- Firewall policy có đồng nhất ở các zone không?
- Khi một dependency lỗi, function có timeout/fallback phù hợp không?

### Failure domains

Phân tích lỗi theo lớp:

1. Execution environment hoặc function runtime.
2. Integration connector/network interface.
3. Subnet hoặc availability zone.
4. Route table, NAT, firewall hoặc private endpoint.
5. DNS resolver/private zone.
6. Dependency service.
7. VPN/transit hoặc on-premises network.

Nếu chỉ test function invocation thành công, có thể chưa kiểm tra các failure domain này.

### Circuit breaker và fallback

Với dependency không thiết yếu, có thể dùng circuit breaker để ngừng gọi khi lỗi liên tục và thử lại sau thời gian nghỉ. Fallback có thể dùng cache, queue hoặc trả trạng thái tạm thời. Với dependency bắt buộc như database ghi đơn hàng, không nên giả vờ thành công khi không thể commit; trả lỗi có kiểm soát và giữ khả năng retry idempotent.

## 15. Quan sát đường mạng và dependency

Monitoring cần trả lời được: function không kết nối được vì DNS, route, firewall, TLS, identity, capacity hay dependency?

### Metric

- Invocation count, error rate, duration và timeout.
- Cold start/init duration.
- Concurrent execution và throttling.
- DNS lookup latency/failure.
- Connection establishment latency và TLS handshake time.
- Database active connections, pool wait và query latency.
- Cache latency, hit ratio và connection errors.
- Broker connection, publish/consume error và queue age.
- NAT gateway bytes, active connections, port allocation/error nếu provider cung cấp.
- Subnet IP availability và network interface count.
- VPN tunnel state, BGP route, RTT, packet loss và throughput.
- Private endpoint health và flow accept/reject.

### Logs và traces

Log nên ghi destination service name, operation, connect duration, error class và correlation ID. Không ghi password, token, session cookie hoặc full connection string có secret.

Distributed tracing giúp tách:

- Function initialization.
- DNS/connect/TLS.
- Connection pool wait.
- Dependency request duration.
- Retry/backoff.
- Serialization và application processing.

Không phải mọi runtime/provider đều tự tạo span DNS/connect. Có thể cần instrumentation ở client library hoặc custom metric.

### Flow logs và DNS logs

VPC/VNet flow logs giúp xác định flow được accept/reject, source/destination IP, port và protocol theo khả năng dịch vụ. DNS query logs giúp xem truy vấn hostname trả kết quả nào hoặc bị lỗi.

Flow log không nhất thiết chứa toàn bộ lý do firewall rule bị từ chối hoặc payload ứng dụng. Kết hợp với security rule, route table, DNS log và trace để điều tra.

## 16. Quy trình cấu hình function kết nối private database

Ví dụ một function xử lý đơn hàng cần truy cập PostgreSQL private trong VPC/VNet.

### Bước 1: lập bản đồ dependency

Ghi rõ:

- Function name/runtime/region.
- Database hostname, private IP range và port.
- Database subnet/zone và security policy.
- Secret hoặc identity method.
- DNS zone/resolver.
- RPO/RTO hoặc yêu cầu availability của database.
- Concurrency dự kiến và connection limit.

### Bước 2: chuẩn bị mạng

- Chọn integration subnet có đủ IP.
- Cấu hình route đến database subnet.
- Bảo đảm network ACL/firewall cho phép TCP 5432.
- Database ingress chỉ cho phép function security group hoặc source được duyệt.
- Liên kết private DNS zone hoặc resolver.
- Nếu cần Internet/API ngoài, thêm NAT/egress theo policy; không mở egress rộng nếu không cần.

### Bước 3: cấu hình function integration

- Gắn function với subnet/connector phù hợp.
- Chọn security group/NSG riêng.
- Xác minh function runtime có thể truy cập DNS và private endpoint.
- Đặt timeout và concurrency phù hợp.
- Kiểm tra quyền execution role/managed identity.

### Bước 4: kết nối an toàn

- Lấy credential từ secret manager hoặc dùng database IAM authentication.
- Bật TLS và xác minh certificate.
- Tạo connection pool nhỏ và có giới hạn.
- Reuse client khi runtime hỗ trợ.
- Xử lý stale connection và database failover.

### Bước 5: kiểm thử

- Resolve hostname từ đúng môi trường network.
- Kiểm tra TCP handshake đến port.
- Kiểm tra TLS handshake/certificate.
- Xác thực database.
- Chạy query read-only trước.
- Kiểm thử concurrency tăng dần.
- Mô phỏng database failover hoặc network interruption trong staging.
- Xác minh function timeout/retry không tạo transaction trùng.

### Sơ đồ luồng

~~~mermaid
sequenceDiagram
    participant E as Event source
    participant F as Serverless function
    participant D as Private DNS
    participant N as VPC route/security
    participant DB as Private database
    participant SM as Secret manager
    E->>F: Invoke
    F->>SM: Get credential using workload identity
    SM-->>F: Short-lived/managed secret
    F->>D: Resolve database hostname
    D-->>F: Private address
    F->>N: TCP + TLS connection
    N->>DB: Allow approved source and port
    DB-->>F: Query result
    F-->>E: Result/acknowledgement
~~~

## 17. Ví dụ cấu hình ở mức khái niệm

Cấu hình dưới đây minh họa các ý cần khai báo. Đây không phải schema dùng trực tiếp cho mọi cloud provider.

~~~yaml
function:
  name: orders-handler
  runtime: python
  timeout_seconds: 20
  max_concurrency: 40
  network:
    integration: vpc
    subnets:
      - private-app-zone-a
      - private-app-zone-b
    security_groups:
      - sg-orders-function
  dependencies:
    database:
      hostname: db.orders.internal
      port: 5432
      tls: required
      credential_source: secret-manager
    internal_api:
      hostname: inventory.internal
      port: 443
      tls: required
  egress:
    internet:
      enabled: false
    private_endpoints:
      - object-storage
      - secret-manager
  observability:
    metrics: enabled
    tracing: enabled
    network_flow_logs: enabled
~~~

Các giá trị subnet, security group và endpoint phải được thay bằng resource thực tế của môi trường. Tắt Internet egress chỉ phù hợp khi mọi dependency cần thiết đã có private path và runtime vẫn truy cập được control/telemetry endpoint cần thiết theo cách provider quy định.

### Ví dụ security rule

| Resource đích | Inbound rule | Source |
|---|---|---|
| PostgreSQL | TCP 5432 | Security group của function |
| Redis | TCP port theo cấu hình TLS | Security group của function |
| Internal HTTPS API | TCP 443 | Function subnet/SG được duyệt |
| DNS resolver | UDP/TCP 53 hoặc resolver endpoint | Network được phép |
| Secret manager private endpoint | TCP 443 | Function SG/subnet |

Không sao chép bảng này thành rule mở rộng cho mọi nguồn. Hãy dùng source cụ thể, port chính xác và policy theo môi trường.

## 18. Khác biệt giữa các nền tảng cloud

Tên và cách cấu hình tính năng thay đổi theo provider. Cần đọc tài liệu của đúng dịch vụ và plan trước khi triển khai.

| Nền tảng | Cách tích hợp mạng thường gặp | Điều cần kiểm tra |
|---|---|---|
| AWS Lambda | VPC configuration với subnet và security group; outbound đến private resources; public Internet egress thường cần NAT hoặc đường private phù hợp | ENI/IP capacity, subnet AZ, route, NAT, endpoint, execution role và cold start/network provisioning |
| Azure Functions | Regional VNet integration cho outbound; private endpoint cho inbound access đến app hoặc cho dependency service | Hosting plan hỗ trợ, subnet delegation/size, route-all behavior, NSG/UDR, DNS và NAT/egress |
| Google Cloud Functions/Cloud Run functions | Serverless VPC Access connector hoặc direct VPC egress tùy sản phẩm/runtime/region | Connector capacity hoặc direct egress settings, subnet/IP, route, firewall, DNS và Internet egress |
| Cloud Run | Direct VPC egress hoặc connector theo cấu hình dịch vụ | Network tags/service identity, subnet sizing, startup/scale behavior và egress mode |

Bảng này là định hướng khái niệm, không thay thế tài liệu cấu hình theo phiên bản. Tính năng và giới hạn có thể khác theo generation của sản phẩm, region và plan.

### Những câu hỏi cần trả lời trước khi chọn provider feature

- Có hỗ trợ private inbound, private outbound hay cả hai?
- Có thể chọn nhiều subnet và zone không?
- Traffic Internet có đi qua NAT không?
- Có route-all hoặc chỉ route private prefix?
- DNS custom/private zone được hỗ trợ thế nào?
- Có yêu cầu subnet delegation hoặc quyền tạo interface không?
- Connector có giới hạn throughput/concurrency/IP không?
- Cold start có chịu ảnh hưởng khi provision network path không?
- Có private endpoint cho secret, storage, logging và telemetry không?

## 19. Troubleshooting theo lớp mạng

Khi function không kết nối được, kiểm tra từ tên đích đến ứng dụng theo thứ tự.

### DNS lỗi

Triệu chứng: hostname không resolve, resolve public IP sai hoặc lúc được lúc không.

Kiểm tra:

- Private zone đã liên kết với VPC/VNet chưa?
- Function dùng resolver nào?
- Conditional forwarding có đúng không?
- Có record A/AAAA hoặc alias đúng không?
- TTL và cache có giữ record cũ không?
- DNS firewall/policy có chặn query không?

### Timeout khi kết nối TCP

Triệu chứng: connect timeout hoặc SYN không hoàn tất.

Kiểm tra:

- Function có network integration thật sự chưa?
- Subnet route có đến destination prefix không?
- Security group/NSG/ACL/firewall hai phía có cho phép không?
- Database/listener có đang lắng nghe đúng IP/port không?
- Peering/transit/VPN có route hai chiều không?
- NAT/egress gateway có healthy và đúng route không?
- CIDR có overlap hoặc route bị blackhole không?

### Connection refused

Triệu chứng: kết nối đến IP được nhưng port trả RST/refused.

Kiểm tra:

- Service đích có đang chạy và listen đúng port?
- Endpoint có trỏ đến backend đúng không?
- Security policy hoặc proxy có reject thay vì drop không?
- Database có giới hạn hoặc tạm ngừng listener không?

### TLS handshake/certificate lỗi

Kiểm tra:

- Certificate có hết hạn không?
- Hostname/SAN có khớp không?
- Function runtime có trust CA phù hợp không?
- TLS version/cipher có tương thích không?
- Clock của runtime có đúng không?
- Proxy có thay certificate hoặc yêu cầu client certificate không?

Không tắt certificate verification để làm cho kết nối “chạy được”.

### Authentication/authorization lỗi

Nếu TCP và TLS thành công nhưng nhận 401/403 hoặc database authentication error:

- Xác minh workload identity đúng.
- Kiểm tra secret version/rotation.
- Kiểm tra role, database grants và resource policy.
- Xác minh token audience/expiry.
- Kiểm tra clock skew và permission ở private endpoint.

### Lỗi chỉ xuất hiện khi scale

Kiểm tra:

- Subnet IP exhaustion.
- Connector/ENI capacity.
- NAT port exhaustion hoặc connection tracking.
- Database max connections và pool size.
- DNS query rate hoặc resolver capacity.
- Concurrency limit và burst scaling.
- Cold start/network provisioning time.

### Lệnh kiểm tra trong môi trường test

Một số công cụ có thể không tồn tại trong runtime serverless managed. Có thể chạy từ một VM/debug container nằm trong cùng subnet, security group và DNS path:

~~~bash
# DNS lookup
nslookup db.orders.internal

# TCP reachability (nếu nc có sẵn)
nc -vz db.orders.internal 5432

# TLS handshake (nếu openssl có sẵn)
openssl s_client -connect db.orders.internal:5432 -servername db.orders.internal

# HTTP dependency timing
curl -sS -o /dev/null -w 'connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' https://inventory.internal/health
~~~

Kiểm tra từ VM cùng subnet chỉ chứng minh đường mạng của VM đó. Function có thể dùng connector, security group, identity hoặc DNS context khác; cần xác minh từ chính function bằng một diagnostic invocation an toàn, hoặc dùng công cụ provider để kiểm tra network attachment.

## 20. Hiệu năng và chi phí của private connectivity

Private network integration có thể làm tăng chi phí và latency tùy kiến trúc.

Các nguồn chi phí:

- NAT gateway theo giờ và dữ liệu xử lý.
- Private endpoint theo giờ, endpoint usage hoặc dữ liệu.
- Cross-zone/cross-region traffic.
- VPN/dedicated connectivity.
- Connector capacity hoặc network appliance.
- Logging/flow log ingestion.
- Data transfer đến on-premises hoặc SaaS.

Các nguồn latency:

- DNS lookup và connection setup.
- TLS handshake.
- NAT/proxy hop.
- Cross-zone/region routing.
- Connector throughput contention.
- Connection pool wait.
- Database/cache saturation.

### Cách tối ưu

- Dùng private endpoint cho dịch vụ cloud quan trọng khi phù hợp.
- Reuse connection và bật keep-alive.
- Đặt function và dependency ở region/zone gần nhau theo thiết kế HA.
- Batch request để giảm số connection và round trip.
- Dùng cache đúng cách để giảm dependency calls.
- Hạn chế payload và tránh gọi nhiều dependency tuần tự nếu có thể song song an toàn.
- Đặt concurrency phù hợp với database và NAT capacity.
- Theo dõi chi phí NAT, endpoint và cross-zone transfer theo workload.
- Không tạo nhiều private endpoint trùng lặp nếu có thể dùng shared network service được quản lý an toàn.

Đừng tối ưu chi phí bằng cách loại bỏ NAT hoặc endpoint nếu điều đó làm lộ dependency hoặc vi phạm security boundary. So sánh tổng chi phí, rủi ro và độ trễ của từng phương án.

## 21. Checklist triển khai function vào mạng riêng

### Thiết kế và dependency

- [ ] Đã lập danh sách database, cache, API, broker, storage, secret và on-premises dependency.
- [ ] Đã xác định luồng inbound và outbound riêng biệt.
- [ ] Đã xác định destination private hay public và protocol/port cần dùng.
- [ ] Đã chọn VPC/VNet integration, private endpoint, service endpoint hoặc NAT đúng mục đích.
- [ ] CIDR không chồng lấn với mạng khác.

### Subnet, route và DNS

- [ ] Subnet đủ IP cho scale dự kiến và các network attachment.
- [ ] Có subnet/zone dự phòng khi yêu cầu HA.
- [ ] Route table có next hop đúng cho mọi dependency.
- [ ] Security group/NSG/firewall cho phép đúng nguồn, đích, protocol và port.
- [ ] Private DNS zone/resolver/forwarding được cấu hình và kiểm thử.
- [ ] NAT/egress IP và allow-list đối tác sẵn sàng nếu cần Internet outbound.
- [ ] VPN/private circuit và route hai chiều được kiểm tra nếu có on-premises.

### Identity và dữ liệu

- [ ] Function dùng workload identity/managed identity riêng.
- [ ] Secret lấy từ secret manager và có rotation.
- [ ] TLS và certificate validation được bật.
- [ ] Database role và service permission theo least privilege.
- [ ] Không ghi secret hoặc token vào log.
- [ ] Dependency có timeout, retry và idempotency phù hợp.

### Capacity và availability

- [ ] Function concurrency được giới hạn theo capacity dependency.
- [ ] Connection pool và connection reuse được cấu hình.
- [ ] NAT port, subnet IP và connector capacity được theo dõi.
- [ ] Database/cache/broker có HA và failover endpoint phù hợp.
- [ ] Egress path và DNS có dự phòng theo failure domain.
- [ ] Có backpressure, DLQ hoặc load shedding khi dependency quá tải.

### Observability và kiểm thử

- [ ] Có invocation, duration, error, concurrency và cold start metrics.
- [ ] Có dependency latency, pool wait và connection failure metrics.
- [ ] Có flow logs, DNS logs hoặc công cụ tương đương.
- [ ] Đã test DNS, TCP, TLS, authentication và query thực tế.
- [ ] Đã test scale burst, IP exhaustion và connection limit trong staging.
- [ ] Đã test mất một zone, NAT, VPN hoặc dependency theo phạm vi cho phép.
- [ ] Có runbook và owner cho sự cố network.

## 22. Tự kiểm tra

1. VPC/VNet integration và private endpoint giải quyết hai vấn đề nào khác nhau?
2. Vì sao function đã gắn vào private subnet vẫn có thể không kết nối được database?
3. Khi nào function cần NAT gateway, và khi nào private endpoint có thể thay thế đường Internet?
4. DNS private zone chưa liên kết với VPC/VNet có thể gây triệu chứng gì?
5. Vì sao security group ở function và database cần được kiểm tra ở cả hai phía?
6. Concurrency của serverless có thể gây connection storm đến database như thế nào?
7. Subnet IP exhaustion và NAT ephemeral port exhaustion khác nhau ra sao?
8. Vì sao kiểm tra từ VM cùng subnet chưa chứng minh function có network path giống hệt?
9. Cần chuẩn bị những thành phần nào để function truy cập hệ thống on-premises?
10. Hãy thiết kế đường kết nối an toàn từ function xử lý đơn hàng đến PostgreSQL private, Redis và internal inventory API.
11. Khi dependency chậm, cần kết hợp timeout, retry, circuit breaker và concurrency limit như thế nào?
12. Những metric và log nào giúp phân biệt lỗi DNS, route, firewall, TLS và authentication?

Kết nối serverless với mạng riêng là bài toán end-to-end. Function cần network integration đúng, subnet còn địa chỉ, route có next hop, DNS trả endpoint phù hợp, firewall cho phép đúng luồng và dependency đủ capacity. Identity, secret và TLS bảo vệ quyền truy cập; concurrency, connection reuse và backpressure giữ hệ thống ổn định khi scale. Khi kiểm thử từ chính execution environment và quan sát từng lớp mạng, đội ngũ có thể đưa function vào kiến trúc private mà vẫn kiểm soát được bảo mật, hiệu năng, tính sẵn sàng và chi phí.
