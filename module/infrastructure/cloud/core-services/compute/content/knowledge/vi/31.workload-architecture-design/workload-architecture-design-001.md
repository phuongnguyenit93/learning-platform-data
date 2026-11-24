# Thiết kế dịch vụ web nhiều tầng trên nhóm máy ảo

Một dịch vụ web production thường gồm nhiều tầng có trách nhiệm riêng: tầng tiếp nhận lưu lượng, tầng web, tầng xử lý nghiệp vụ và tầng dữ liệu. Triển khai tất cả trên một máy ảo có thể phù hợp với thử nghiệm nhỏ, nhưng tạo ra điểm lỗi đơn, khó mở rộng từng thành phần và làm ranh giới bảo mật trở nên mờ nhạt. Thiết kế nhiều tầng trên các nhóm máy ảo giúp mỗi tầng có thể được mở rộng, cập nhật, giám sát và bảo vệ theo nhu cầu riêng.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, bài học này trình bày cách thiết kế một dịch vụ web nhiều tầng chạy trên nhóm máy ảo (VM groups/instance groups). Nội dung đi từ yêu cầu tải và tính sẵn sàng đến phân vùng mạng, load balancer, nhóm VM đa vùng sẵn sàng, tầng dữ liệu, autoscaling, bảo mật, triển khai, quan sát và tối ưu chi phí. Ví dụ xuyên suốt là một ứng dụng đặt hàng có web frontend, API xử lý nghiệp vụ, cache và cơ sở dữ liệu.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của edge, web tier, application tier và data tier.
- Vẽ luồng request và luồng quản trị giữa các tầng.
- Chọn cách bố trí subnet, route, security group/firewall và private access.
- Thiết kế nhóm VM có template thống nhất, phân bố trên nhiều Availability Zone.
- Cấu hình load balancer, health check, session handling và graceful draining.
- Ước tính số VM theo throughput, concurrency, headroom và mức sử dụng mục tiêu.
- Kết hợp horizontal autoscaling với vertical sizing và capacity planning.
- Tách trạng thái phiên, file và dữ liệu khỏi VM để hỗ trợ thay thế instance an toàn.
- Thiết kế tính sẵn sàng, backup, failover và phục hồi sau thảm họa.
- Áp dụng hardening, IAM, secrets, TLS, patching và least privilege.
- Xây dựng quy trình triển khai rolling/blue-green và theo dõi chất lượng dịch vụ.
- Đánh giá chi phí theo tầng và nhận diện các điểm gây lãng phí.

## 1. Vì sao nên thiết kế web service thành nhiều tầng?

Một web service thường có ít nhất ba nhóm trách nhiệm:

1. **Web/entry tier:** nhận kết nối từ người dùng, kết thúc TLS hoặc chuyển tiếp request, phục vụ nội dung tĩnh và định tuyến request.
2. **Application tier:** xác thực, thực thi nghiệp vụ, kiểm tra dữ liệu và phối hợp với các dịch vụ khác.
3. **Data tier:** lưu dữ liệu bền vững, cache, file/object và message phục vụ xử lý bất đồng bộ.

Có thể bổ sung edge tier gồm DNS, CDN, WAF và public load balancer. Edge bảo vệ và phân phối traffic trước khi request tới VM.

### 1.1. Lợi ích của phân tầng

- **Mở rộng độc lập:** web tier có thể cần nhiều VM vì số kết nối lớn, trong khi application tier cần CPU hoặc memory nhiều hơn.
- **Giảm phạm vi ảnh hưởng:** lỗi một web VM không nhất thiết làm mất toàn bộ ứng dụng nếu load balancer còn các backend khỏe.
- **Bảo mật theo lớp:** chỉ tầng cần thiết được phép giao tiếp với tầng kế tiếp; database không cần nhận kết nối trực tiếp từ Internet.
- **Triển khai linh hoạt:** có thể cập nhật application tier theo rolling hoặc blue-green mà không thay đổi toàn bộ hệ thống.
- **Quan sát rõ hơn:** metric theo tầng giúp xác định bottleneck nằm ở network, web, application hay database.
- **Quản lý chi phí:** chọn loại VM phù hợp với đặc điểm từng tầng và scale đúng phần đang thiếu capacity.

### 1.2. Chi phí và độ phức tạp

Nhiều tầng tạo thêm load balancer, subnet, firewall rule, VM group, endpoint và pipeline triển khai. Nếu tải thấp, một kiến trúc quá nhiều thành phần có thể tốn kém và khó vận hành. Số tầng nên phản ánh ranh giới mở rộng, bảo mật, ownership và failure domain thực tế.

Không bắt buộc mọi ứng dụng phải có một nhóm VM riêng cho từng tầng. Một web tier và application tier có thể chạy chung nhóm VM ở giai đoạn đầu nếu tải, quyền truy cập và vòng đời triển khai tương tự; khi cần scale hoặc cô lập, có thể tách chúng ra.

## 2. Kiến trúc tham chiếu

Ví dụ dưới đây dùng một dịch vụ đặt hàng. Người dùng truy cập qua DNS và HTTPS. WAF lọc request phổ biến, public load balancer phân phối traffic đến web VM group. Web tier chuyển API request tới application VM group ở private subnet. Application tier truy cập cache và database qua private network.

~~~mermaid
flowchart TB
    U[Browser / Mobile Client] --> DNS[DNS]
    DNS --> EDGE[CDN / WAF]
    EDGE --> LB[Public Load Balancer]
    subgraph VPC["Virtual Network / VPC"]
      subgraph PUB["Public subnets - AZ A and AZ B"]
        LB
        NAT[NAT / Egress Gateway]
      end
      subgraph WEB["Private web subnets - multiple AZs"]
        W1[Web VM A]
        W2[Web VM B]
      end
      subgraph APP["Private application subnets - multiple AZs"]
        A1[API VM A]
        A2[API VM B]
      end
      subgraph DATA["Isolated data subnets"]
        CACHE[(Cache)]
        DB[(Primary Database)]
        REPL[(Standby / Read Replica)]
      end
      LB --> W1
      LB --> W2
      W1 --> A1
      W1 --> A2
      W2 --> A1
      W2 --> A2
      A1 --> CACHE
      A2 --> CACHE
      A1 --> DB
      A2 --> DB
      DB --> REPL
      W1 --> NAT
      W2 --> NAT
      A1 --> NAT
      A2 --> NAT
    end
    OPS[Admin via VPN / Bastion / Session Manager] -.-> W1
    OPS -.-> A1
~~~

Sơ đồ là mô hình logic. Trong triển khai thực tế, load balancer có thể là dịch vụ managed; cache/database có thể là dịch vụ managed hoặc cluster VM riêng. Không nhất thiết phải tự vận hành mọi thành phần.

### 2.1. Vai trò từng tầng

| Tầng | Thành phần | Trách nhiệm | Không nên đảm nhiệm |
|---|---|---|---|
| Edge | DNS, CDN, WAF | Phân phối, lọc request, TLS policy và cache nội dung phù hợp | Lưu trạng thái giao dịch chính |
| Entry/web | Public load balancer, web VM group | Nhận traffic, reverse proxy, static asset, routing | Truy cập trực tiếp database nếu không cần |
| Application | API/service VM group | Nghiệp vụ, authorization, validation, tích hợp | Lưu session/file chỉ trên local disk của một VM |
| Data | Database, cache, object storage, queue | Lưu trữ, truy vấn, buffer và trao đổi dữ liệu | Nhận kết nối công khai không kiểm soát |
| Operations | Monitoring, logging, deployment, admin access | Quản trị, quan sát, patch và khôi phục | Chia sẻ quyền admin rộng với runtime workload |

### 2.2. Ranh giới tin cậy

Mỗi tầng là một ranh giới tin cậy riêng. Request từ Internet không được xem là đáng tin chỉ vì đã qua WAF. Web tier phải xác minh request và chỉ gọi endpoint application được phép. Application tier xác thực quyền nghiệp vụ và chỉ dùng credential cần thiết để truy cập data tier.

Không dùng việc đặt VM trong private subnet như biện pháp bảo mật duy nhất. Cần kết hợp route table, firewall/security group, IAM, TLS, host hardening, patching và kiểm soát danh tính.

## 3. Thiết kế mạng và phân vùng subnet

Mạng quyết định tầng nào có thể giao tiếp với ai, qua port nào và theo hướng nào. Phân vùng rõ giúp giảm bề mặt tấn công và hỗ trợ điều tra khi có sự cố.

### 3.1. Public và private subnet

- **Public subnet:** có route tới Internet Gateway hoặc cơ chế public ingress tương đương. Thường đặt public load balancer, NAT gateway hoặc thành phần edge cần public reachability.
- **Private subnet:** VM không có public IP và không nhận kết nối trực tiếp từ Internet. Outbound cần NAT, egress gateway hoặc private endpoint.
- **Isolated data subnet:** không có đường Internet trực tiếp; chỉ cho phép traffic từ application tier và các hệ thống quản trị/backup đã xác định.

Tên public/private phụ thuộc route và gateway, không chỉ dựa vào việc VM có public IP hay không. Kiểm tra route table thực tế để xác nhận đường đi.

### 3.2. Phân bố theo Availability Zone

Tạo subnet cho từng tầng ở ít nhất hai Availability Zone khi yêu cầu availability cần chịu được lỗi một zone. Đặt web VM group và application VM group trên nhiều zone; load balancer phải có backend ở các zone đó. Data tier cần topology replication/failover phù hợp.

Tránh đặt toàn bộ VM, NAT, endpoint hoặc database primary trong cùng một zone rồi gọi kiến trúc là multi-AZ. Các dependency dùng chung có thể trở thành điểm lỗi đơn.

### 3.3. Ma trận luồng mạng

| Nguồn | Đích | Port/protocol minh họa | Mục đích |
|---|---|---|---|
| Internet | WAF / public LB | TCP 443 | HTTPS từ client |
| Public LB | Web VM group | TCP 8080 hoặc 443 | Health check và forward request |
| Web VM group | Application VM group | TCP 8443 | API nội bộ qua TLS |
| Application VM group | Database | TCP 5432 hoặc port DB thực tế | Truy vấn và transaction |
| Application VM group | Cache | TCP 6379 hoặc port cache thực tế | Cache/session/data lookup |
| Application VM group | Queue/object endpoint | HTTPS 443 | Publish event và truy cập object |
| Admin network | Bastion/session endpoint | Port quản trị được kiểm soát | Truy cập vận hành |
| VM | Monitoring/log endpoint | HTTPS 443 hoặc private agent path | Gửi metric/log |

Các port trong bảng chỉ là ví dụ. Chỉ mở port thật sự cần thiết; dùng source security group/identity hoặc subnet CIDR hẹp thay vì mở từ mọi địa chỉ.

### 3.4. Egress và private endpoint

VM private có thể cần tải package, gửi log hoặc gọi dịch vụ cloud. Ưu tiên private endpoint/service endpoint khi có để giảm phụ thuộc NAT và giữ traffic trên private network. Nếu cần NAT, phân bố theo zone để tránh một NAT gateway trở thành điểm lỗi hoặc tạo cross-zone data transfer không cần thiết.

Kiểm soát outbound theo domain/service/port nếu nền tảng hỗ trợ. Không cấp quyền Internet outbound không giới hạn cho application tier nếu workload chỉ cần gọi một số API cụ thể.

## 4. Thiết kế nhóm máy ảo cho từng tầng

Nhóm VM (instance group, virtual machine scale set hoặc autoscaling group tùy nền tảng) quản lý nhiều máy có cấu hình và vòng đời tương tự. Thay vì sửa thủ công từng VM, tạo VM từ image/template đã kiểm thử rồi để nhóm quản lý số lượng instance.

### 4.1. VM template/image

Template nên xác định:

- Image hệ điều hành đã được harden và cập nhật.
- CPU, memory, disk type/size và network interface.
- Runtime, agent monitoring/logging và package nền tảng.
- Startup/bootstrap script có thể chạy lặp an toàn.
- Service identity/instance role tối thiểu.
- Labels/tags cho môi trường, owner, service, tier và cost center.
- Health check, shutdown behavior và log configuration.

Không nhúng secret, private key, database password hoặc access token dài hạn vào image/user-data. Lấy secret lúc runtime qua secret manager bằng identity của VM.

### 4.2. Immutable infrastructure

Khi cần thay đổi OS hoặc application runtime, build image/template mới và triển khai instance mới. Cách này giúp các VM trong group đồng nhất, dễ rollback và giảm configuration drift.

Tránh cấu hình thủ công khác nhau trên từng VM. Nếu cần thay đổi tạm thời để điều tra, ghi lại và đưa thay đổi đã xác nhận vào image hoặc automation sau đó.

### 4.3. Phân nhóm theo trách nhiệm

Tách web VM group và application VM group khi chúng có ít nhất một khác biệt đáng kể:

- CPU/memory profile khác nhau.
- Cần scale theo metric khác nhau.
- Có yêu cầu network/security khác nhau.
- Chu kỳ release và ownership khác nhau.
- Failure domain hoặc mức ưu tiên khác nhau.

Không tách nhóm chỉ để có nhiều thành phần quản trị hơn. Mỗi group cần mục tiêu capacity, health check, scaling policy và owner rõ.

### 4.4. Pet và cattle

VM trong autoscaling group nên được xem là instance có thể thay thế. Dữ liệu bền vững không nên chỉ tồn tại trên disk local của một instance. Nếu VM hỏng, group có thể tạo VM mới từ template và load balancer chỉ gửi traffic tới instance khỏe.

Nếu workload thật sự cần local state, cần xác định cách replicate, backup, fencing và phục hồi trước khi cho phép autoscaler xóa hoặc thay VM.

## 5. Load balancer và phân phối traffic

Load balancer nhận request từ client và chuyển đến backend phù hợp. Nó giúp phân phối tải, loại backend không khỏe khỏi pool và cung cấp một endpoint ổn định trước các VM có thể thay đổi.

### 5.1. Lớp 4 và lớp 7

- **Layer 4 load balancing:** định tuyến theo IP/port/protocol; phù hợp TCP/UDP và ít xử lý nội dung ứng dụng.
- **Layer 7 load balancing:** hiểu HTTP/HTTPS, host, path, header và có thể hỗ trợ routing theo rule, TLS termination, redirect hoặc WAF integration.

Chọn loại theo protocol, yêu cầu routing, TLS, WebSocket/gRPC và khả năng quan sát. Một hệ thống có thể dùng edge L7 load balancer rồi internal L4/L7 load balancer giữa các tầng.

### 5.2. Health check

Health check xác định backend có thể nhận traffic hay không. Phân biệt:

- **Liveness:** process còn sống và không bị kẹt không thể phục hồi.
- **Readiness:** instance có đủ dependency/configuration để phục vụ request.
- **Startup:** ứng dụng đã hoàn thành khởi tạo ban đầu chưa.

Health endpoint nên nhẹ, có timeout ngắn và không tạo tải lớn lên database. Nếu readiness phụ thuộc mọi dependency bên ngoài, một lỗi phụ trợ có thể loại toàn bộ backend khỏi pool. Hãy xác định dependency nào thực sự bắt buộc để phục vụ request.

### 5.3. Thuật toán phân phối

- Round robin phù hợp khi backend có capacity tương tự và request duration tương đối đồng đều.
- Least connections hữu ích khi request giữ kết nối lâu và số connection phản ánh tải.
- Weighted distribution cho phép instance có capacity khác nhau nhận tỷ lệ traffic khác nhau.
- Consistent hashing có thể giúp affinity/cache locality nhưng cần cân nhắc skew và rebalance.

Thuật toán không thay thế autoscaling. Theo dõi request rate, active connection, backend latency và error để phát hiện lệch tải.

### 5.4. Session affinity và sticky session

Sticky session giữ client gắn với một backend trong một khoảng thời gian. Nó có thể giúp ứng dụng cũ lưu session trong memory, nhưng tạo rủi ro:

- Một VM nhận quá nhiều session và bị lệch tải.
- VM bị thay thế làm mất session.
- Scale-in khó drain vì nhiều client còn affinity.
- Failover có thể làm client phải đăng nhập lại.

Ưu tiên lưu session trong shared cache hoặc store bền vững, hoặc dùng token stateless có chữ ký. Nếu bắt buộc sticky session, xác định TTL, behavior khi backend hỏng và giới hạn thời gian drain.

### 5.5. Connection draining

Khi VM cần cập nhật hoặc scale-in, load balancer ngừng gửi request mới đến backend, chờ request đang chạy hoàn tất trong thời gian drain, sau đó mới terminate VM. Ứng dụng phải xử lý SIGTERM/shutdown signal, đóng connection và hoàn tất hoặc từ chối công việc đang dang dở một cách an toàn.

## 6. Thiết kế web tier và application tier

### 6.1. Web tier

Web VM thường chạy reverse proxy/web server như Nginx, Apache hoặc runtime web phù hợp. Trách nhiệm thường gồm:

- Phục vụ static asset hoặc chuyển static asset sang CDN/object storage.
- Terminate TLS nếu kiến trúc đặt TLS tại web tier.
- Chuyển request tới application endpoint nội bộ.
- Thiết lập request size, timeout, connection limit và header policy.
- Ghi access log, correlation ID và metric cơ bản.

Web tier nên stateless. Nếu một VM bị thay thế, request tiếp theo có thể được phục vụ bởi VM khác mà không mất dữ liệu nghiệp vụ.

### 6.2. Application tier

Application VM chạy API hoặc service xử lý nghiệp vụ:

- Xác thực người dùng và authorization theo resource/action.
- Validate input, kiểm tra business rule và transaction.
- Truy cập database/cache qua connection pool.
- Publish event cho công việc nền.
- Trả response có mã lỗi và correlation ID nhất quán.

Không tin tưởng header do client tự gửi như user identity hoặc role nếu chúng chưa được gateway/authentication layer xác thực và ký/forward an toàn.

### 6.3. Tách cấu hình theo môi trường

Image có thể giống nhau giữa dev/staging/production; cấu hình môi trường được inject qua parameter/config service hoặc deployment system. Quản lý endpoint, feature flag và secret riêng theo environment. Không dùng một database credential hoặc signing key chung cho mọi môi trường.

## 7. Thiết kế data tier và quản lý trạng thái

VM stateless có thể được tạo/xóa nhanh. Dữ liệu cần tồn tại qua vòng đời VM phải đặt ở storage/service có semantics bền vững.

### 7.1. Database

Database lưu dữ liệu nghiệp vụ và cần kế hoạch cho:

- Transaction isolation và consistency.
- Connection limit/pooling.
- Backup, point-in-time recovery và restore test.
- Replication, failover và read replica.
- Schema migration tương thích với phiên bản ứng dụng.
- Encryption at rest/in transit và audit.

Nếu dùng database managed, vẫn phải thiết kế schema, index, query, backup policy và connection management. Managed không có nghĩa tự động đáp ứng mọi RPO/RTO.

Nếu tự vận hành database trên VM, cần thêm cluster/quorum, disk durability, replication, fencing, backup, patching, failover automation và kỹ năng trực vận hành. Đây là một workload stateful khác với web/application VM group.

### 7.2. Cache

Cache giảm latency và tải database cho dữ liệu có thể tái tạo hoặc có chính sách invalidation rõ. Xác định:

- TTL và chiến lược invalidation.
- Cache-aside, read-through hoặc write-through.
- Behavior khi cache unavailable.
- Stampede protection và request coalescing.
- Key design, eviction và memory sizing.
- Dữ liệu nào không được cache do tính nhạy cảm hoặc yêu cầu freshness.

Cache không nên là nguồn dữ liệu duy nhất cho giao dịch quan trọng trừ khi dịch vụ cache được thiết kế và vận hành như storage bền vững phù hợp.

### 7.3. File và object storage

Không lưu file upload hoặc generated report chỉ trên disk local của một web VM nếu người dùng có thể được định tuyến sang VM khác. Dùng object storage/shared file service, metadata trong database và URL có thời hạn khi cần truy cập.

Nếu ứng dụng cần local scratch space, coi nó là tạm thời, đặt giới hạn dung lượng và xóa sau khi xử lý. Không để scratch disk đầy làm VM mất khả năng phục vụ.

### 7.4. Queue và background worker

Tác vụ gửi email, tạo report, xử lý ảnh hoặc tích hợp chậm có thể đưa vào queue để tách khỏi request path. Worker group có thể scale độc lập theo queue depth/oldest message age. Thiết kế idempotency, retry, dead-letter queue và backpressure để message giao lại không tạo side effect trùng.

## 8. Capacity planning cho nhóm VM

Capacity planning bắt đầu từ tải nghiệp vụ, không phải chọn một loại VM rồi hy vọng đủ. Đo throughput an toàn của một instance tại mức latency/error mục tiêu, sau đó tính số instance và headroom.

### 8.1. Tính số instance theo throughput

Với:

- λ: arrival rate yêu cầu (request/giây).
- μ: throughput an toàn của một VM (request/giây).
- U: utilization mục tiêu, nhỏ hơn 1 để giữ headroom.

Số VM tối thiểu theo throughput:

\[
N=\left\lceil\frac{\lambda}{\mu\times U}\right\rceil
\]

Ví dụ API cần 1.200 request/giây. Load test cho thấy một application VM xử lý ổn định 100 request/giây tại latency mục tiêu. Chọn utilization mục tiêu 70%:

~~~text
N = ceil(1.200 / (100 × 0,70))
  = ceil(17,14)
  = 18 VM
~~~

Đây là capacity khi tất cả VM hoạt động. Nếu yêu cầu chịu mất một zone hoặc một phần instance, cần cộng thêm capacity để sau lỗi vẫn còn đủ throughput.

### 8.2. Tính capacity khi mất một zone

Giả sử 18 VM được phân bố đều trên 3 zone, mỗi zone 6 VM. Khi mất một zone, còn 12 VM. Nếu cần vẫn phục vụ 1.200 request/giây ở utilization 70%, mỗi VM phải có throughput an toàn:

~~~text
Capacity còn lại = 12 × 100 × 0,70
                 = 840 request/giây
~~~

840 thấp hơn 1.200; kiến trúc chưa đủ N-1 capacity. Có thể tăng số VM baseline, tăng throughput mỗi VM sau benchmark, giảm tải qua cache/queue hoặc chấp nhận degraded mode có giới hạn. Không được chỉ kiểm tra số lượng VM khi healthy.

### 8.3. CPU và memory

Theo dõi CPU usage, run queue, memory working set, swap, disk IOPS/latency, network throughput và application concurrency. CPU thấp không có nghĩa VM còn capacity nếu database pool, thread pool hoặc network đã bão hòa.

Memory cần headroom cho runtime, cache, request burst và rolling deployment. Nếu VM bắt đầu swap mạnh hoặc OOM, latency có thể tăng trước khi health check thất bại.

### 8.4. Vertical và horizontal scaling

- **Vertical scaling:** đổi VM sang shape có CPU/memory lớn hơn. Đơn giản với ứng dụng chưa scale ngang tốt nhưng có trần phần cứng và thường cần restart/migrate.
- **Horizontal scaling:** thêm VM vào group. Tăng capacity và availability nhưng yêu cầu statelessness, load balancing và shared data.

Thực tế thường dùng cả hai: chọn instance size hợp lý trước, sau đó scale ngang trong min/max đã kiểm thử.

### 8.5. Autoscaling policy

Scale theo metric phản ánh bottleneck:

- CPU utilization cho workload CPU-bound.
- Request count per target hoặc active connections cho web tier.
- Queue depth/oldest message age cho worker.
- Custom metric như in-flight request hoặc thread pool saturation cho application tier.

Không chỉ dùng CPU nếu request có thể chờ database lâu trong khi CPU thấp. Cũng không scale theo một metric nhiễu mà không có cooldown, stabilization hoặc min/max guardrail.

## 9. Thiết kế autoscaling group

Một VM group cần cấu hình nhất quán và hành vi scale-up/scale-down rõ.

### 9.1. Min, desired và max

- **Min:** số VM luôn giữ để phục vụ tải nền và availability.
- **Desired:** số VM group mong muốn tại thời điểm hiện tại.
- **Max:** giới hạn mở rộng theo quota, budget và downstream capacity.

Min không nên bằng 1 cho dịch vụ production cần HA. Max không nên lớn hơn khả năng chịu tải của database hoặc quota cloud.

### 9.2. Scale-out

Khi tải tăng:

1. Metric vượt threshold trong thời gian xác định.
2. Autoscaling policy tăng desired capacity.
3. VM mới được tạo từ image/template.
4. Bootstrap, agent và application service khởi động.
5. Instance đăng ký với target group.
6. Health check pass và load balancer bắt đầu gửi traffic.

Đo thời gian từ trigger đến khi instance nhận request. Nếu boot mất vài phút, giữ headroom hoặc scheduled scaling trước các đợt tải có thể dự báo.

### 9.3. Scale-in

Scale-in cần bảo vệ request/session/job đang chạy:

1. Chọn instance có thể loại bỏ theo policy.
2. Đánh dấu instance draining và ngừng nhận traffic mới.
3. Chờ connection/request đang chạy hoàn tất trong thời gian grace.
4. Ứng dụng dừng nhận job mới và hoàn tất/nhả lease công việc.
5. Flush log/metric và đóng connection.
6. Terminate instance.

Không scale-in quá nhanh khi traffic có tính chu kỳ. Dùng cooldown/stabilization và kiểm thử ngay sau scale-in để chắc rằng group còn đủ capacity.

### 9.4. Warm pool và scheduled scaling

Warm pool giữ sẵn VM đã boot hoặc gần sẵn sàng để giảm scale-out latency. Scheduled scaling tăng desired capacity trước giờ có tải định kỳ. Cả hai tăng chi phí idle; cần so sánh với SLO và p95 startup time.

## 10. Tính sẵn sàng và loại bỏ điểm lỗi đơn

High availability cần nhiều thành phần cùng hoạt động: load balancer, VM groups, network, database, DNS, identity và observability. Chỉ chạy nhiều VM trong một zone chưa đủ nếu zone hoặc network của zone đó gặp sự cố.

### 10.1. Multi-zone

- Load balancer trải backend qua nhiều zone.
- Web và application VM groups phân bố instance qua các zone.
- Subnet/IP capacity đủ cho scale-out ở từng zone.
- Database có standby/replica và failover theo mục tiêu.
- NAT/egress và private endpoints không tạo một điểm lỗi duy nhất.
- Deployment không cập nhật đồng thời mọi zone.

### 10.2. Health check và failover

Load balancer loại backend không khỏe khỏi pool. Autoscaling group có thể thay instance không đạt health check. Nhưng cần phân biệt lỗi process với lỗi dependency chung: nếu database đang down, tất cả application VM có thể fail readiness cùng lúc. Thiết kế health check để không gây cascade loại bỏ mọi backend khi một dependency phụ trợ lỗi.

### 10.3. Availability không chỉ là số VM

Đánh giá availability theo request thành công và khả năng phục hồi. Một dịch vụ có 10 VM nhưng tất cả cùng dùng một database không có HA vẫn có thể ngừng hoạt động khi database hỏng.

Xác định:

- RTO: thời gian tối đa để khôi phục dịch vụ.
- RPO: lượng dữ liệu tối đa có thể mất theo thời gian.
- Failure domain: VM, rack/host, zone, region, network hoặc dependency.
- Degraded mode: chức năng nào có thể tạm ngừng để giữ luồng quan trọng.
- Runbook: ai quyết định failover, cách kiểm tra dữ liệu và cách failback.

### 10.4. Disaster recovery

Multi-zone thường xử lý lỗi trong một region; disaster recovery region khác là bài toán riêng. Có thể chọn backup/restore, pilot light, warm standby hoặc active-active tùy RTO/RPO và chi phí.

Backup chỉ có giá trị khi đã thử restore. Diễn tập cả database restore, application deployment, DNS/traffic switch, secret/identity và kết nối dependency.

## 11. Bảo mật theo từng tầng

Thiết kế bảo mật cần nhiều lớp: network segmentation, identity, host hardening, application security, encryption và audit.

### 11.1. Network security

- Chỉ public load balancer nhận inbound từ Internet.
- Web VM chỉ nhận inbound từ load balancer.
- Application VM chỉ nhận API traffic từ web tier hoặc trusted internal caller.
- Database chỉ nhận kết nối từ application tier và hệ thống quản trị được phép.
- Admin access đi qua VPN, bastion hoặc session manager; tránh mở SSH/RDP trực tiếp ra Internet.
- Egress chỉ mở theo dependency cần thiết.

### 11.2. Identity và quyền

Mỗi VM/service dùng identity riêng với quyền tối thiểu. Web tier không cần quyền đọc database nếu chỉ proxy request. Application tier chỉ được đọc/ghi đúng secret, bucket, queue và database resource cần thiết.

Tách quyền deploy, runtime, operator và auditor. Không dùng một access key tĩnh chia sẻ giữa các VM. Ưu tiên managed identity/instance role và short-lived credentials.

### 11.3. TLS và dữ liệu

- Dùng HTTPS từ client đến edge.
- Cân nhắc TLS/mTLS giữa các tầng khi yêu cầu bảo mật và threat model cần.
- Mã hóa disk, database snapshot, object và backup.
- Quản lý certificate rotation và trust chain.
- Không ghi token, password, session cookie hoặc dữ liệu cá nhân không cần thiết vào log.

### 11.4. Host hardening và patching

- Tắt service/port không dùng.
- Áp dụng baseline OS và cập nhật security patch.
- Dùng EDR/agent bảo vệ endpoint theo chính sách.
- Giới hạn quyền sudo/admin.
- Đồng bộ thời gian và audit log.
- Quét image/package và quản lý lỗ hổng.
- Thay VM bằng image mới theo rolling process khi patch nền tảng.

### 11.5. WAF và bảo vệ ứng dụng

WAF giúp lọc một số mẫu tấn công phổ biến, nhưng không thay thế authentication, authorization, input validation, parameterized query, CSRF/XSS protection và secure coding. Theo dõi false positive để không chặn nhầm traffic hợp lệ.

## 12. Quản lý phiên và trạng thái ứng dụng

Khi load balancer phân phối request qua nhiều VM, ứng dụng không nên giả định request tiếp theo sẽ tới đúng VM trước đó.

### 12.1. Stateless application

Thiết kế API stateless: mỗi request mang token/context cần thiết, còn dữ liệu bền vững được đọc từ shared store. Điều này giúp:

- Thay VM mà không mất session.
- Scale-out/in không cần di chuyển session local.
- Deploy nhiều phiên bản đồng thời.
- Phân phối request qua nhiều zone.

### 12.2. Session store

Nếu cần server-side session, dùng cache/shared session store hoặc database có TTL. Xác định behavior khi session store unavailable, TTL, encryption, key rotation và logout/revocation.

Sticky session chỉ là giải pháp tương thích trong một số trường hợp. Nó không thay thế shared state nếu cần HA.

### 12.3. Idempotency và retry

Client, load balancer hoặc service mesh có thể retry request khi timeout. Với thao tác tạo đơn, thanh toán hoặc cập nhật trạng thái, dùng idempotency key và transaction/outbox để tránh thực hiện side effect hai lần.

## 13. Triển khai và cập nhật ứng dụng

Triển khai nhiều VM cần bảo đảm phiên bản tương thích trong khoảng thời gian rolling update.

### 13.1. Rolling deployment

1. Build artifact/image đã kiểm thử.
2. Tạo batch VM mới hoặc cập nhật từng phần theo launch template.
3. Đợi startup và readiness pass.
4. Cho load balancer đưa VM mới vào pool.
5. Drain VM cũ và chờ request đang chạy hoàn tất.
6. Tiếp tục batch kế tiếp.
7. Dừng rollout nếu error/latency vượt ngưỡng.

Giới hạn số instance unavailable đồng thời để không làm capacity xuống dưới yêu cầu.

### 13.2. Blue-green deployment

Tạo green group song song với blue group. Kiểm tra green bằng smoke/integration test, sau đó chuyển một phần traffic và tăng dần. Giữ blue trong thời gian rollback cần thiết.

Blue-green cần capacity tạm thời gần gấp đôi ở tầng được nhân bản và cần kiểm tra tương thích schema/database. Rollback application không tự động rollback dữ liệu đã ghi theo schema mới.

### 13.3. Database migration

Dùng expand-and-contract:

1. Thêm schema mới tương thích với phiên bản cũ.
2. Deploy ứng dụng đọc/ghi theo cách tương thích.
3. Backfill và xác minh dữ liệu.
4. Chuyển traffic/feature flag.
5. Sau thời gian an toàn mới loại bỏ schema cũ.

Tránh deploy migration phá vỡ backward compatibility cùng lúc với rolling update khi còn instance chạy phiên bản cũ.

### 13.4. Rollback

Rollback phải xác định rõ:

- Artifact/image/version cần quay lại.
- Cấu hình và secret tương ứng.
- Database schema có tương thích không.
- Queue/event nào đã được phát theo contract mới.
- Có cần tắt feature flag hoặc chuyển traffic không.
- Tiêu chí quyết định rollback và người có quyền quyết định.

## 14. Quan sát và vận hành

Một kiến trúc nhiều tầng cần observability theo tầng và theo request. Kết hợp metrics, logs, traces và synthetic checks.

### 14.1. Metrics hạ tầng

- VM count theo group/zone và trạng thái health.
- CPU, memory, disk utilization/latency/IOPS.
- Network throughput, packet drop và connection count.
- Load balancer request count, active connections, target health và 4xx/5xx.
- Autoscaling desired/current capacity và scaling activity.
- Database connections, replication lag, storage và query latency.
- Cache hit ratio, eviction và memory pressure.

### 14.2. Metrics ứng dụng

- Request rate, success/error rate.
- p50/p95/p99 latency.
- Thread pool, worker queue, in-flight request.
- Connection pool wait và timeout.
- Business metric như đơn hàng thành công, thanh toán lỗi, job backlog.
- Dependency call duration và retry count.

### 14.3. Logs và traces

Log cần có timestamp, service, environment, instance ID, trace/correlation ID, severity và outcome. Tránh ghi secret và payload nhạy cảm. Dùng centralized logging để log vẫn còn sau khi VM bị terminate.

Distributed trace nối request qua edge, web, application và database/cache. Sampling cần đủ để điều tra tail latency và lỗi hiếm mà không tạo chi phí quá lớn.

### 14.4. Alert và runbook

Alert nên gắn với tác động dịch vụ:

- Target healthy count thấp hơn ngưỡng.
- p99 hoặc error rate vượt SLO.
- Autoscaling không tạo được instance hoặc group đạt max.
- VM memory/disk gần cạn.
- Database connection/replication lag vượt ngưỡng.
- Queue age tăng kéo dài.
- Certificate sắp hết hạn hoặc patch compliance giảm.

Mỗi alert có owner, severity, dashboard, bước kiểm tra đầu tiên và điều kiện escalation.

## 15. Tối ưu hiệu năng và chi phí

### 15.1. Chọn VM shape theo tầng

| Tầng | Đặc điểm tải | Hướng chọn tài nguyên |
|---|---|---|
| Web/reverse proxy | Nhiều kết nối, TLS, network I/O | Cân bằng CPU, memory và network; benchmark TLS/connection |
| API/application | Logic, serialization, query và concurrency | CPU/memory theo profiling và request mix |
| Worker | Batch, CPU-bound hoặc I/O-bound | Chọn compute/memory/network theo job type; scale theo backlog |
| Cache | Memory capacity và network latency | Ưu tiên memory/network, đo hit ratio và eviction |
| Database | Memory, IOPS, storage durability và connection | Sizing theo query/working set, storage latency và HA topology |

Không chọn VM chỉ dựa trên vCPU. Benchmark bằng workload đại diện và tính cả license, disk, network egress, load balancer, NAT, backup và observability.

### 15.2. Rightsizing

Thu thập metric qua chu kỳ tải đủ dài, bao gồm peak và batch window. VM có CPU trung bình thấp nhưng p99 cao có thể bị giới hạn bởi single-thread, lock hoặc downstream. VM có memory cao có thể cần cache; giảm memory mà không hiểu working set có thể gây paging.

Thay đổi một yếu tố mỗi lần và so sánh throughput, p95/p99, error, cost per transaction.

### 15.3. Giảm chi phí không làm mất headroom

- Dùng autoscaling min/max dựa trên baseline và peak.
- Scheduled scaling cho workload có lịch.
- Tắt môi trường non-production ngoài giờ nếu phù hợp.
- Dùng instance family phù hợp và committed-use discount/reservation khi baseline ổn định.
- Dùng Spot/interruptible VM cho worker có checkpoint/retry, không đặt state quan trọng duy nhất trên instance đó.
- Cache static content và dữ liệu có thể cache để giảm load lên application/database.
- Giảm log debug, đặt retention và sampling hợp lý.
- Tối ưu NAT, cross-zone transfer và data egress.

Không scale-in chỉ vì CPU thấp trong một khoảng ngắn nếu cần headroom để chịu lỗi zone hoặc burst.

## 16. Các quyết định thiết kế cần ghi lại

Architecture Decision Record (ADR) giúp nhóm hiểu vì sao chọn một cấu hình và điều kiện cần xem xét lại.

Mỗi quyết định nên ghi:

- Bối cảnh và yêu cầu: tải, SLO, RTO/RPO, compliance, budget.
- Các phương án đã cân nhắc.
- Phương án chọn và lý do.
- Trade-off: chi phí, độ phức tạp, latency, availability và lock-in.
- Giả định cần kiểm chứng bằng test.
- Metric/threshold khiến quyết định cần xem lại.

Ví dụ: chọn hai application VM group ở hai zone, min 2 instance mỗi zone, scale theo request count và CPU; quyết định cần xem lại nếu p95 startup vượt 3 phút hoặc database connection trở thành bottleneck.

## 17. Quy trình thiết kế từ yêu cầu đến triển khai

1. **Thu thập yêu cầu:** traffic baseline/peak, request mix, SLO, security, RTO/RPO và budget.
2. **Vẽ luồng request:** client → edge → load balancer → web → application → data/dependency.
3. **Xác định failure domain:** VM, zone, region, network và dịch vụ managed.
4. **Thiết kế subnet và firewall:** chỉ mở luồng cần thiết giữa từng tầng.
5. **Chọn VM profile:** benchmark CPU, memory, disk và network theo từng tier.
6. **Tạo image/template:** hardening, agent, bootstrap và identity.
7. **Tạo VM group đa zone:** min/desired/max và health check.
8. **Cấu hình load balancing:** routing, TLS, health check và connection draining.
9. **Tách state:** database, cache, session, object storage và queue.
10. **Thiết kế scaling:** metric, threshold, cooldown, headroom và max downstream capacity.
11. **Thiết kế deployment:** rolling/blue-green, schema compatibility và rollback.
12. **Thiết lập observability:** dashboard, alert, trace và runbook.
13. **Kiểm thử:** load, spike, failover, zone loss, backup restore và security validation.
14. **Review chi phí:** VM hours, storage, network, managed service, logging và idle capacity.

## 18. Ví dụ thực tế: dịch vụ đặt hàng ba tầng

Một hệ thống đặt hàng có các thành phần:

- Web frontend phục vụ trang và chuyển API request.
- Application API kiểm tra giỏ hàng, tồn kho và tạo đơn.
- Database lưu đơn hàng và inventory.
- Cache giữ catalog và dữ liệu đọc nhiều.
- Queue xử lý email/notification và cập nhật báo cáo.

### 18.1. Luồng request tạo đơn

1. Client gọi HTTPS tới domain ứng dụng.
2. DNS trỏ tới CDN/WAF và public load balancer.
3. Load balancer chọn web VM khỏe.
4. Web tier chuyển request tới application endpoint nội bộ.
5. Application xác thực token, kiểm tra idempotency key và validate payload.
6. Application đọc cache/catalog và transaction với database.
7. Application ghi outbox/event hoặc publish event sau commit theo cơ chế bảo đảm nhất quán.
8. Response trả về order ID.
9. Worker đọc event từ queue và gửi notification.

### 18.2. Phân bố VM

| Nhóm | AZ A | AZ B | Scaling signal |
|---|---:|---:|---|
| Web VM | 2 | 2 | Request/target, active connections |
| Application VM | 3 | 3 | CPU, request rate, in-flight requests |
| Worker VM | 1 | 1 | Queue depth, oldest message age |

Các con số chỉ minh họa. Cần benchmark và kiểm tra capacity khi mất một zone. Database/cache được triển khai theo HA topology phù hợp; không mặc định số replica trong bảng bảo đảm database HA.

### 18.3. Xử lý khi application VM hỏng

- Health check phát hiện VM không phản hồi.
- Load balancer ngừng gửi request mới tới VM.
- Autoscaling group thay instance từ image chuẩn.
- Các request đang chạy được retry theo client policy; thao tác tạo đơn dùng idempotency key.
- VM mới lấy config/secret bằng instance identity và đăng ký vào target group sau readiness.
- Dashboard theo dõi healthy target count, replacement time và error rate.

### 18.4. Xử lý khi database chậm

- Application connection pool có giới hạn.
- Query timeout và request deadline tránh giữ thread vô hạn.
- Cache giảm một phần read load nhưng không được dùng để giả lập write đã commit.
- Rate limit/backpressure giảm tải vào database.
- Queue giữ tác vụ có thể xử lý bất đồng bộ.
- Alert theo connection wait, query latency, lock và replication lag.

## 19. Ví dụ cấu hình logic

Ví dụ sau mô tả một security group/firewall policy ở mức khái niệm. Cú pháp thực tế tùy cloud provider.

~~~yaml
networkPolicy:
  publicLoadBalancer:
    inbound:
      - source: internet
        protocol: TCP
        port: 443
    outbound:
      - destination: web-tier
        protocol: TCP
        port: 8080

  webTier:
    inbound:
      - source: public-load-balancer
        protocol: TCP
        port: 8080
    outbound:
      - destination: application-tier
        protocol: TCP
        port: 8443
      - destination: monitoring-endpoint
        protocol: TCP
        port: 443

  applicationTier:
    inbound:
      - source: web-tier
        protocol: TCP
        port: 8443
    outbound:
      - destination: database
        protocol: TCP
        port: 5432
      - destination: cache
        protocol: TCP
        port: 6379
      - destination: queue-and-secret-endpoints
        protocol: TCP
        port: 443

  dataTier:
    inbound:
      - source: application-tier
        protocol: TCP
        ports: [5432, 6379]
~~~

Đây là minh họa quan hệ nguồn/đích, không phải manifest có thể áp dụng trực tiếp. Cần bổ sung DNS, health check, backup, patch, admin access và egress cụ thể. Nếu dùng firewall stateful, response traffic thường được cho phép theo connection tracking; nếu dùng ACL stateless, cần quy tắc ephemeral port tương ứng.

## 20. Kiểm thử kiến trúc trước production

### 20.1. Functional và integration test

- Request đi đúng từ load balancer qua web tới application.
- Application chỉ truy cập dependency được cấp quyền.
- Session không phụ thuộc local memory của một VM.
- File/object có thể truy cập khi request được phục vụ bởi VM khác.
- Retry không tạo giao dịch trùng.
- Health check phân biệt startup, readiness và liveness.

### 20.2. Load và performance test

- Ramp từ baseline lên peak và giữ steady-state.
- Spike test để đo autoscaling delay.
- Theo dõi p50/p95/p99 theo từng tầng.
- Tăng concurrency đến khi tìm được bottleneck đầu tiên.
- Test database connection limit và cache miss.
- Xác nhận load generator không phải bottleneck.

### 20.3. Resilience test

- Terminate một web VM khi đang có traffic.
- Terminate một application VM và xác minh request đang chạy.
- Mất một zone trong môi trường thử nghiệm.
- Thử database failover và kiểm tra reconnect.
- Làm cache unavailable và xác minh fallback.
- Drain node/VM trong rolling deployment.
- Restore backup và đo RTO/RPO thực tế.

### 20.4. Security validation

- Scan public IP/port để xác minh chỉ edge được public.
- Kiểm tra web tier không thể truy cập database trực tiếp.
- Kiểm tra application tier không có quyền admin rộng.
- Xác minh certificate, TLS và secret rotation.
- Kiểm tra OS patch, image vulnerability và audit trail.
- Thử revoke identity/credential và xác nhận behavior an toàn.

## 21. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chạy mọi tầng trên một VM lâu dài | Điểm lỗi đơn, scale và patch khó | Tách tier theo trách nhiệm và nhu cầu |
| Đặt VM application có public IP | Mở rộng bề mặt tấn công | Đặt trong private subnet, chỉ nhận traffic nội bộ |
| Database nhận kết nối Internet | Rủi ro truy cập trái phép | Isolated subnet và firewall theo source identity |
| Lưu session/file trên local disk | Mất trạng thái khi VM bị thay | Shared session store/object storage |
| Dùng sticky session làm HA | VM hỏng có thể mất session | Stateless/token/shared session |
| Chỉ chạy một zone | Zone outage làm toàn dịch vụ ngừng | Multi-zone và test zone failure |
| Scale web tier theo CPU nhưng bottleneck ở DB | Thêm VM làm DB quá tải hơn | Theo dõi dependency và giới hạn concurrency |
| Không giới hạn connection pool | Connection storm khi scale-out | Tính tổng connection theo max VM/concurrency |
| Health check quá sâu | Lỗi dependency làm loại mọi backend | Thiết kế readiness theo khả năng phục vụ cần thiết |
| Không drain trước terminate | Request/job bị cắt giữa chừng | Graceful shutdown và connection draining |
| Sửa tay từng VM | Configuration drift | Image/template và immutable rollout |
| Rolling update toàn bộ cùng lúc | Mất capacity trong deployment | Batch rollout, surge và availability budget |
| Chỉ backup mà không restore test | Không biết backup có dùng được không | Diễn tập restore định kỳ |
| Chọn VM theo vCPU danh nghĩa | Bỏ qua memory/network/IO bottleneck | Benchmark workload thực |
| Scale-in quá nhanh | Cold capacity không đủ khi tải quay lại | Cooldown, stabilization và headroom |

## 22. Checklist production

**Kiến trúc và mạng**

- [ ] Luồng client → edge → web → application → data đã được mô tả.
- [ ] Mỗi tầng có trách nhiệm, owner và failure boundary rõ ràng.
- [ ] Web/application VM nằm trong subnet phù hợp; data tier không public.
- [ ] Security rule chỉ cho phép source, destination và port cần thiết.
- [ ] Có kế hoạch egress, private endpoint, DNS và IP capacity.
- [ ] Các tầng quan trọng được phân bố trên nhiều Availability Zone.

**VM groups và scaling**

- [ ] Image/template được harden, version hóa và không chứa secret.
- [ ] Min/desired/max capacity có căn cứ từ load test và quota.
- [ ] Health check và connection draining đã được kiểm thử.
- [ ] Autoscaling metric phản ánh bottleneck thật.
- [ ] Có headroom để chịu lỗi instance/zone và thời gian boot.
- [ ] Scale-in bảo vệ request, session và job đang chạy.

**Data và trạng thái**

- [ ] Session không phụ thuộc local memory của một VM.
- [ ] File bền vững đặt ở shared/object storage.
- [ ] Database có backup, restore test và failover plan.
- [ ] Connection pool được giới hạn theo max application capacity.
- [ ] Cache có TTL/invalidation và fallback.
- [ ] Queue có retry, idempotency, DLQ và backpressure.

**Bảo mật và triển khai**

- [ ] TLS được cấu hình cho public và internal path phù hợp.
- [ ] Runtime identity có least privilege.
- [ ] Admin access qua kênh được kiểm soát và audit.
- [ ] OS/image được patch và vulnerability scan.
- [ ] Rolling/blue-green deployment có rollback và schema compatibility.
- [ ] Secret/certificate rotation đã được thử.

**Vận hành**

- [ ] Có metrics, logs, traces và synthetic checks theo tầng.
- [ ] Dashboard hiển thị healthy targets, capacity và p95/p99.
- [ ] Alert có owner, severity và runbook.
- [ ] Có load, failover, zone-loss và restore drill.
- [ ] Chi phí VM, storage, network, database và observability được theo dõi.

## 23. Kết luận

Thiết kế dịch vụ web nhiều tầng trên nhóm máy ảo là việc chia trách nhiệm và failure boundary rõ ràng, sau đó kết nối các tầng bằng network rule, load balancing và identity có kiểm soát. Web/application tier nên có thể thay thế và scale ngang; trạng thái bền vững đặt trong data service phù hợp; VM group được tạo từ template chuẩn và phân bố trên nhiều zone.

Kiến trúc chỉ được xem là phù hợp sau khi đã kiểm thử tải, autoscaling, health check, graceful draining, dependency failure, zone loss và restore. Capacity cần tính cả headroom và giới hạn downstream; bảo mật cần áp dụng từ edge đến database; triển khai cần có rollback; observability cần nối metric hạ tầng với trải nghiệm người dùng. Các quyết định này giúp dịch vụ đáp ứng yêu cầu hiệu năng, tính sẵn sàng, bảo mật và chi phí trong vận hành thực tế.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Multi-tier architecture | Kiến trúc chia web, application và data thành các tầng trách nhiệm riêng. |
| VM group | Nhóm máy ảo được quản lý bằng template và chính sách capacity chung. |
| Autoscaling group | Cơ chế tự điều chỉnh số lượng VM theo metric hoặc lịch. |
| Availability Zone | Failure domain độc lập tương đối trong một region. |
| Load balancer | Thành phần phân phối traffic đến backend khỏe. |
| Reverse proxy | Thành phần nhận request và chuyển tiếp tới application backend. |
| Private subnet | Subnet không nhận inbound Internet trực tiếp theo route/security design. |
| Security group/firewall | Quy tắc kiểm soát traffic theo nguồn, đích, port và protocol. |
| Stateless service | Service không phụ thuộc trạng thái local tồn tại qua nhiều request. |
| Connection draining | Ngừng gửi request mới và chờ request hiện tại hoàn tất trước khi loại backend. |
| Headroom | Capacity dự phòng cho burst, failover và biến động tải. |
| Horizontal scaling | Tăng/giảm số instance. |
| Vertical scaling | Tăng/giảm CPU, memory hoặc cấu hình của một instance. |
| RTO | Thời gian mục tiêu tối đa để khôi phục dịch vụ. |
| RPO | Mức mất dữ liệu tối đa có thể chấp nhận, đo theo thời gian. |
| Immutable infrastructure | Cách triển khai thay instance bằng image/template mới thay vì sửa thủ công lâu dài. |
| Blue-green deployment | Duy trì hai nhóm phiên bản và chuyển traffic giữa chúng. |
| Degraded mode | Chế độ giảm một số chức năng để giữ luồng nghiệp vụ quan trọng. |
| Rightsizing | Chọn tài nguyên phù hợp với tải đo được và mục tiêu vận hành. |
