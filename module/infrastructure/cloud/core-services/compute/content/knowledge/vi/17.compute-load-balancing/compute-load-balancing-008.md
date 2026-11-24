# Cân bằng tải theo zone hoặc region và ảnh hưởng của luồng mạng

Một dịch vụ compute có thể chạy trên nhiều máy ảo hoặc node ở nhiều availability zone, thậm chí nhiều region. Load balancer phân phối request tới các backend để tăng khả năng phục vụ, sử dụng tài nguyên hiệu quả và duy trì dịch vụ khi một instance hoặc vùng hạ tầng gặp sự cố. Tuy nhiên, đặt backend ở nhiều zone/region không tự động tạo ra tính sẵn sàng cao. Đường đi của request, đường phản hồi, DNS, health check, trạng thái phiên, kết nối tới database và chi phí truyền dữ liệu đều ảnh hưởng tới kết quả.

Cần phân biệt hai phạm vi: **cân bằng tải trong một region** thường phân phối traffic giữa các zone để tăng khả năng chịu lỗi và tận dụng capacity; **cân bằng tải giữa nhiều region** điều phối người dùng tới một cụm dịch vụ ở vị trí địa lý khác, phục vụ latency, disaster recovery hoặc yêu cầu residency. Bài học này trình bày các mô hình đó, cách luồng mạng tác động tới hiệu năng và chi phí, cùng phương pháp thiết kế và kiểm thử.

## 1. Vai trò của load balancing trong kiến trúc compute

Load balancer là thành phần nhận kết nối hoặc request từ client rồi chuyển tới một backend phù hợp theo thuật toán và chính sách đã cấu hình. Backend có thể là VM, container, node, service endpoint hoặc một load balancer tầng dưới.

Các mục tiêu chính:

- **Phân phối tải:** tránh dồn request vào một instance trong khi instance khác nhàn rỗi.
- **Tăng khả năng sẵn sàng:** loại backend không khỏe khỏi tập nhận traffic.
- **Mở rộng ngang:** cho phép thêm hoặc bớt backend theo nhu cầu.
- **Giảm độ trễ:** chọn backend gần client hoặc có capacity phù hợp.
- **Cô lập lỗi:** giới hạn tác động khi một instance, zone hoặc region gặp sự cố.
- **Điều phối traffic:** áp dụng routing theo giao thức, hostname, path, trọng số hoặc vị trí địa lý.

Load balancer không tự sửa lỗi ứng dụng, không thay thế replication dữ liệu và không bảo đảm mọi request đều có thể retry an toàn. Nó chỉ có thể đưa traffic tới backend được đánh giá là đủ điều kiện theo cơ chế health check và routing.

## 2. Phân biệt zone và region

**Availability zone (AZ)** là một miền hạ tầng độc lập tương đối trong một region, thường được thiết kế để giảm khả năng một sự cố cục bộ ảnh hưởng đồng thời tới mọi zone. Cách nhà cung cấp triển khai và ánh xạ zone có thể khác nhau giữa các tài khoản hoặc dịch vụ.

**Region** là một khu vực địa lý chứa một hoặc nhiều zone. Các region thường có khoảng cách địa lý đáng kể, mạng kết nối riêng và failure domain lớn hơn zone.

| Thuộc tính | Nhiều zone trong một region | Nhiều region |
|---|---|---|
| Mục tiêu thường gặp | Chịu lỗi zone, bảo trì, tăng capacity | Disaster recovery, giảm latency địa lý, đáp ứng residency |
| Độ trễ giữa backend | Thường thấp hơn liên vùng, nhưng vẫn qua mạng | Thường cao hơn và biến động hơn |
| Data replication | Có thể dùng replication đồng bộ hoặc bất đồng bộ tùy hệ thống | Thường cần thiết kế replication liên vùng và xử lý consistency |
| Chi phí network | Có thể phát sinh phí liên zone theo dịch vụ/nhà cung cấp | Thường có phí truyền liên vùng và data egress |
| Failover | Có thể chuyển sang zone khác trong cùng region | Chuyển traffic và có thể phải phục hồi dữ liệu ở region khác |
| Độ phức tạp | Vừa phải | Cao hơn do DNS/global routing, data consistency và vận hành đa vùng |

Không nên xem hai zone là hai region độc lập. Nếu sự cố ảnh hưởng toàn region, triển khai nhiều zone trong cùng region có thể vẫn không đủ để duy trì dịch vụ.

## 3. Các lớp cân bằng tải

Kiến trúc thực tế thường có nhiều tầng load balancing. Mỗi tầng có phạm vi và thông tin khác nhau.

| Lớp | Vị trí | Quyết định routing dựa trên |
|---|---|---|
| Global traffic management | Trước các region | Địa lý, latency, health, trọng số, failover |
| Regional load balancer | Trong một region | Backend pool, zone, health, thuật toán phân phối |
| Internal/service load balancer | Giữa các service trong mạng riêng | Service endpoint, port, protocol và health |
| Host/container proxy | Gần workload | Connection, request, retry, timeout hoặc routing nội bộ |

Ví dụ, người dùng truy cập DNS của một dịch vụ toàn cầu. Global routing chọn region Singapore. Regional load balancer trong region đó chọn một backend ở zone A hoặc B. Reverse proxy hoặc service mesh có thể tiếp tục định tuyến tới service nội bộ.

~~~mermaid
flowchart TD
    U[Người dùng] --> G[Global DNS / Global Load Balancer]
    G --> R1[Regional Load Balancer - Region A]
    G --> R2[Regional Load Balancer - Region B]
    subgraph A[Region A]
      R1 --> A1[Backend Zone A]
      R1 --> A2[Backend Zone B]
    end
    subgraph B[Region B]
      R2 --> B1[Backend Zone A]
      R2 --> B2[Backend Zone B]
    end
~~~

Cần xác định tầng nào chịu trách nhiệm cho từng quyết định. Nếu global routing gửi traffic tới một region unhealthy nhưng regional load balancer vẫn khỏe cục bộ, người dùng vẫn có thể gặp lỗi. Health signal phải phản ánh đúng trạng thái dịch vụ ở phạm vi mà tầng routing cần biết.

## 4. Cân bằng tải ở lớp 4 và lớp 7

### 4.1. Layer 4

L4 load balancer phân phối kết nối dựa trên thông tin tầng vận chuyển như IP, port và TCP/UDP. Nó không cần hiểu nội dung HTTP.

Ưu điểm:

- Phù hợp TCP/UDP và giao thức không phải HTTP.
- Có thể có overhead thấp.
- Hữu ích cho kết nối dài hoặc lưu lượng cần giữ nguyên protocol.
- Có thể chuyển tiếp ở mức connection mà không parse request.

Giới hạn:

- Khó routing theo hostname, URL path hoặc HTTP header.
- Health check thường tập trung vào kết nối hoặc endpoint; cần kiểm tra riêng ứng dụng.
- Một TCP connection thường gắn với backend đã chọn trong thời gian tồn tại của connection.

### 4.2. Layer 7

L7 load balancer hiểu giao thức ứng dụng như HTTP/HTTPS và có thể routing theo host, path, header, cookie hoặc thuộc tính request.

Ví dụ:

- api.example.com tới API backend.
- /images/* tới dịch vụ media.
- /v2/* tới phiên bản API mới.
- Một tỷ lệ nhỏ traffic tới canary backend.

Ưu điểm là chính sách routing phong phú và có thể tích hợp TLS termination, WAF hoặc request-level health. Đổi lại, L7 phải xử lý giao thức ứng dụng, có thể thêm latency và cần quản lý chứng thư, header, timeout và connection behavior.

### 4.3. Chọn lớp phù hợp

Dùng L4 khi cần phân phối TCP/UDP hoặc giữ protocol đầu cuối. Dùng L7 khi cần routing HTTP theo nội dung, TLS termination hoặc chính sách theo request. Một hệ thống có thể dùng L7 public ingress và L4 internal service cho các giao thức khác.

## 5. Cân bằng tải giữa các zone

Một regional load balancer có thể phân phối backend trên nhiều zone. Có hai cách nhìn thường gặp:

- **Zone-aware / zone-local:** ưu tiên backend trong cùng zone hoặc giữ traffic gần nguồn phát.
- **Cross-zone:** cho phép một load balancer node hoặc điểm nhận traffic phân phối tới backend ở các zone khác.

Tên gọi và hành vi mặc định phụ thuộc dịch vụ. Một số dịch vụ cung cấp tùy chọn cross-zone, một số tự phân phối trên nhiều zone hoặc tạo endpoint theo zone.

### 5.1. Zone-local routing

Trong mô hình zone-local, traffic đi vào một zone thường được xử lý bởi backend cùng zone nếu backend khỏe và đủ capacity.

Lợi ích:

- Giảm lưu lượng liên zone.
- Có thể giảm latency và phí truyền dữ liệu liên zone.
- Giữ traffic gần compute và data được đặt cùng zone.
- Giảm phụ thuộc vào mạng liên zone khi một zone gặp vấn đề.

Rủi ro:

- Một zone có ít backend hoặc tải cao có thể bị quá tải trong khi zone khác còn capacity.
- Nếu zone-local backend không khỏe, cần có fallback sang zone khác.
- Một điểm nhận traffic theo zone có thể cần health check và failover riêng.
- Phải bảo đảm capacity còn lại đủ khi một zone bị loại.

### 5.2. Cross-zone routing

Cross-zone cho phép traffic được nhận ở một zone chuyển tới backend ở zone khác.

Lợi ích:

- Có thể phân phối đều hơn trên toàn bộ backend pool.
- Giảm nguy cơ một zone thiếu backend trong khi zone khác dư capacity.
- Hữu ích khi số backend hoặc capacity giữa các zone không đồng đều.
- Có thể cải thiện khả năng tiếp tục phục vụ khi một zone bị suy giảm, nếu routing và health check phù hợp.

Trade-off:

- Request có thể đi qua mạng liên zone, làm tăng latency.
- Có thể phát sinh phí data transfer giữa zone tùy nhà cung cấp và dịch vụ.
- Nếu backend gọi database hoặc cache ở zone khác, traffic có thể đi qua nhiều chặng.
- Cần xem xét failure mode khi mạng liên zone suy giảm.

### 5.3. So sánh zone-local và cross-zone

| Tiêu chí | Zone-local | Cross-zone |
|---|---|---|
| Đường đi | Ưu tiên backend cùng zone | Có thể tới backend bất kỳ zone khỏe |
| Cân bằng capacity | Có thể không đều nếu tải theo zone lệch | Thường dễ phân phối đều hơn trên pool chung |
| Latency | Có thể thấp hơn khi backend cùng zone | Có thể tăng do hop liên zone |
| Network cost | Có thể giảm inter-zone traffic | Có thể phát sinh inter-zone transfer |
| Tác động khi một zone lỗi | Cần chuyển sang zone khác hoặc từ chối traffic | Có thể phân phối sang zone còn lại nếu capacity đủ |
| Độ phức tạp | Cần quản lý capacity và fallback theo zone | Cần hiểu phí và đường đi liên zone |

Không có lựa chọn luôn tốt hơn. Nếu các zone có tải không đều hoặc backend không đồng nhất, cross-zone có thể tăng utilization tổng thể. Nếu workload nhạy latency và dữ liệu đặt theo zone, zone-local có thể phù hợp hơn. Phải đo bằng traffic pattern thực tế.

## 6. Cân bằng tải giữa các region

Global load balancing điều phối người dùng hoặc kết nối tới một trong nhiều regional endpoint. Các mô hình thường gặp:

### 6.1. Geo-based routing

Chọn region dựa trên vị trí địa lý hoặc quốc gia của client. Mô hình này hữu ích khi muốn phục vụ người dùng gần khu vực của họ hoặc đáp ứng yêu cầu residency.

Địa chỉ IP của client không phải lúc nào cũng phản ánh chính xác vị trí người dùng, nhất là khi dùng VPN, proxy hoặc mạng di động. Cần hiểu dữ liệu định vị và chính sách fallback.

### 6.2. Latency-based routing

Chọn region được dự đoán có latency thấp hơn cho client. Kết quả phụ thuộc vị trí resolver, mạng ISP, peering và thời điểm. DNS-based latency routing có thể dựa vào vị trí DNS resolver thay vì thiết bị cuối, vì vậy không phải lúc nào cũng chọn được đường tối ưu cho từng người dùng.

### 6.3. Weighted routing

Phân phối theo trọng số, ví dụ 90% traffic tới region A và 10% tới region B. Dùng cho canary, migration hoặc kiểm tra capacity. Trọng số DNS không đảm bảo tỷ lệ request chính xác do DNS caching, connection reuse và phân bố client.

### 6.4. Failover routing

Bình thường dùng region chính; khi health check hoặc tín hiệu dịch vụ không đạt, chuyển traffic sang region dự phòng. Failover cần xác định rõ:

- Điều kiện nào kích hoạt chuyển vùng.
- Health check kiểm tra endpoint hay khả năng phục vụ nghiệp vụ.
- Thời gian phát hiện và thời gian chuyển traffic.
- DNS TTL và hành vi cache của resolver/client.
- Dữ liệu ở region đích có đủ mới để nhận ghi hay không.
- Cách tránh split-brain khi region cũ phục hồi.

### 6.5. Anycast và global network

Một số dịch vụ global dùng Anycast hoặc mạng backbone riêng để đưa client tới điểm hiện diện gần hơn. Từ đó, traffic được chuyển tới region/backend theo chính sách của nhà cung cấp. Anycast có thể cải thiện đường vào mạng, nhưng không tự giải quyết consistency dữ liệu, health của ứng dụng hoặc capacity ở region đích.

## 7. Active-active và active-passive

### Active-active

Nhiều region cùng nhận traffic production. Global routing phân phối request giữa chúng.

Ưu điểm:
- Sử dụng capacity ở nhiều region.
- Có thể phục vụ người dùng ở nhiều khu vực với latency tốt hơn.
- Một region lỗi có thể chuyển phần traffic sang region còn lại.

Thách thức:
- Cần xử lý ghi dữ liệu đa vùng và consistency.
- Cần idempotency khi retry hoặc failover.
- Cần tránh xử lý trùng job hoặc giao dịch.
- Cần đồng bộ cấu hình, secret, schema và phiên bản ứng dụng.
- Phải dự trù capacity để một region chịu được tải khi region kia mất.

### Active-passive

Một region chính nhận traffic; region dự phòng được giữ ở trạng thái warm, pilot-light hoặc cold tùy mục tiêu RTO.

Ưu điểm:
- Dễ kiểm soát nơi ghi dữ liệu chính.
- Có thể giảm chi phí khi region dự phòng không chạy full capacity.
- Phù hợp hệ thống chưa hỗ trợ ghi đa vùng.

Thách thức:
- Failover có thể mất thời gian để scale, khởi động và chuyển traffic.
- Cần kiểm tra bản sao dữ liệu và độ trễ replication.
- Region dự phòng phải được diễn tập, không chỉ cấu hình trên giấy.

| Tiêu chí | Active-active | Active-passive |
|---|---|---|
| Traffic bình thường | Nhiều region nhận request | Region chính nhận request |
| Capacity dự phòng | Đang được sử dụng | Có thể chạy ở mức thấp hoặc tắt |
| Độ phức tạp dữ liệu | Cao hơn, có thể cần conflict resolution | Thường đơn giản hơn nếu một writer chính |
| Chi phí | Thường cao hơn do nhiều region hoạt động | Có thể thấp hơn nhưng vẫn cần chi phí DR |
| Failover | Chuyển phần traffic khỏi region lỗi | Promote region dự phòng và chuyển traffic |
| Phù hợp | Dịch vụ toàn cầu, có kiến trúc đa vùng | Hệ thống cần DR nhưng chưa cần ghi đa vùng |

## 8. Luồng request và response qua nhiều tầng

Để hiểu ảnh hưởng của mạng, cần lần theo cả chiều đi và chiều về. Ví dụ request từ người dùng tới API có thể đi qua:

1. DNS resolver tìm global endpoint.
2. Client kết nối tới edge/global entry point.
3. Global routing chọn regional endpoint.
4. Regional load balancer chọn backend.
5. Backend gọi database, cache hoặc service khác.
6. Backend gửi response trở lại qua đường mạng đã thiết lập.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Global routing
    participant R as Regional LB
    participant A as App backend
    participant D as Database
    C->>G: DNS / kết nối tới endpoint
    G->>R: Chọn region khỏe
    R->>A: Chọn backend khỏe
    A->>D: Query qua private network
    D-->>A: Kết quả
    A-->>C: Response qua kết nối
~~~

Mỗi chặng thêm latency, khả năng timeout và chi phí truyền dữ liệu. Nếu request tới backend ở zone A nhưng database ở zone B, luồng nội bộ có thể đi liên zone dù load balancer đã chọn backend gần client. Vì vậy, topology của database, cache và service phụ thuộc cũng cần được xem xét.

## 9. Ảnh hưởng của luồng mạng tới latency

Latency end-to-end là tổng thời gian của nhiều thành phần, không chỉ thời gian xử lý ở VM:

\[
T_{total} =
T_{DNS} + T_{connect} + T_{TLS} +
T_{LB} + T_{network} + T_{backend} +
T_{dependency} + T_{response}
\]

Công thức này là mô hình khái niệm; một số giai đoạn có thể chồng lấp hoặc được tái sử dụng nhờ connection pooling. Khi phân tích thực tế, dùng trace/span để đo từng chặng.

Các yếu tố làm tăng latency:

- Client ở xa region được chọn.
- Request đi qua nhiều proxy, firewall hoặc gateway.
- Cross-zone/cross-region hop.
- DNS lookup hoặc TLS handshake lặp lại.
- Backend phải gọi nhiều dependency tuần tự.
- Network congestion, retransmission hoặc packet loss.
- Load balancer queueing hoặc backend saturation.
- Connection không được reuse.

Không nên chỉ chọn region gần về địa lý. Mạng Internet, ISP peering, vị trí DNS resolver và tình trạng backbone có thể khiến region gần hơn có latency thực tế cao hơn. Hãy đo từ các điểm người dùng đại diện.

## 10. Ảnh hưởng của luồng mạng tới chi phí

Chi phí mạng có thể xuất hiện ở nhiều điểm:

- Data transfer giữa các zone.
- Data transfer giữa các region.
- Internet egress từ cloud ra client hoặc dịch vụ ngoài.
- NAT gateway hoặc firewall processing.
- Load balancer capacity/processed bytes hoặc rule.
- Private connectivity và transit gateway.
- Replication dữ liệu liên vùng.
- Logging, backup và telemetry được gửi qua mạng.

Mô hình tính phí khác nhau theo nhà cung cấp, dịch vụ, region và loại traffic. Không nên mặc định mọi inter-zone traffic đều miễn phí hoặc mọi traffic qua load balancer có cùng cách tính.

Một mô hình ước lượng:

\[
C_{network} =
\sum_i (Bytes_i \times Rate_i) +
C_{NAT} + C_{LB} + C_{transit}
\]

Trong đó Rate_i là đơn giá của từng loại đường truyền, cần lấy từ bảng giá và billing export của môi trường thực tế.

### 10.1. Ví dụ ảnh hưởng của cross-zone

Giả sử một ứng dụng xử lý 2 TB dữ liệu mỗi ngày giữa backend và dịch vụ phụ thuộc. Nếu phần lớn traffic đi liên zone, chi phí truyền có thể đáng kể tùy đơn giá và cách nhà cung cấp tính. Nếu bố trí backend và data dependency cùng zone hoặc dùng zone-local routing, lượng inter-zone byte có thể giảm.

Tuy nhiên, đặt database replica hoặc cache ở cùng zone với mọi backend có thể làm tăng chi phí replication và phức tạp vận hành. Cần đo tổng network cost, không tối ưu một đường truyền riêng lẻ rồi tạo thêm traffic ở đường khác.

## 11. Routing bất đối xứng và stateful firewall

Routing bất đối xứng xảy ra khi gói tin chiều đi và chiều về đi qua các đường hoặc thiết bị mạng khác nhau. Điều này có thể gây lỗi với firewall hoặc network appliance stateful vì thiết bị chỉ thấy một nửa phiên và không nhận diện được trạng thái kết nối.

Ví dụ:
- Request từ backend A đi qua firewall X tới database.
- Response từ database quay về qua firewall Y.
- Firewall Y không có state của phiên và có thể drop response.

Các nguyên nhân thường gặp:
- Nhiều route table hoặc next hop khác nhau giữa subnet.
- NAT đặt ở nhiều vị trí.
- Multi-region peering hoặc transit routing phức tạp.
- ECMP hoặc route propagation không đồng nhất.
- Failover thay đổi đường về nhưng state firewall chưa đồng bộ.

Cách xử lý:
- Vẽ cả forward path và return path.
- Kiểm tra route table, NAT mapping, security group và firewall session.
- Dùng kiến trúc routing đối xứng khi stateful inspection yêu cầu.
- Xác minh source/destination IP sau NAT.
- Kiểm tra MTU, fragmentation và path MTU discovery nếu kết nối treo hoặc truyền payload lớn thất bại.

Không phải mọi hệ thống đều yêu cầu đường đi đối xứng. Nhưng khi có stateful firewall, NAT hoặc proxy, cần xác nhận rõ thiết bị nào giữ trạng thái phiên.

## 12. SNAT, port exhaustion và kết nối đi ra

Khi nhiều backend cùng đi ra Internet hoặc một endpoint qua NAT, địa chỉ nguồn có thể được dịch bằng SNAT. NAT gateway có số lượng port mapping hữu hạn theo địa chỉ IP và cách triển khai. Khi số kết nối đồng thời hoặc tốc độ tạo kết nối cao, có thể xảy ra port exhaustion hoặc thiếu mapping.

Dấu hiệu:

- Backend không mở được kết nối mới dù DNS vẫn hoạt động.
- Kết nối thất bại tăng khi scale-out hoặc tải tăng.
- Timeout tập trung ở outbound call.
- NAT metrics báo port allocation error hoặc connection count cao.
- Một số destination hoạt động, một số destination khác timeout.

Biện pháp:

- Reuse connection bằng HTTP keep-alive và connection pool.
- Tránh tạo kết nối mới cho từng request.
- Tăng capacity NAT theo hướng dẫn dịch vụ, ví dụ thêm địa chỉ nguồn hoặc phân bổ NAT theo subnet/zone khi phù hợp.
- Giới hạn concurrency và tốc độ kết nối.
- Theo dõi port utilization, dropped connection và NAT error.
- Ưu tiên private endpoint cho dịch vụ cloud nếu phù hợp để tránh đường Internet/NAT không cần thiết.

Tăng số NAT gateway hoặc public IP có thể tăng capacity nhưng cũng thay đổi chi phí và kiến trúc. Cần thiết kế phân bổ theo zone để tránh một NAT duy nhất trở thành điểm lỗi hoặc bottleneck.

## 13. Session affinity và trạng thái ứng dụng

Một số load balancer hỗ trợ session affinity (sticky session), nghĩa là cố gắng đưa các request tiếp theo của cùng client về một backend.

Sticky session có thể hữu ích với ứng dụng giữ session trong bộ nhớ cục bộ, nhưng tạo trade-off:

- Traffic có thể phân phối không đều.
- Backend bị lỗi có thể làm mất session nếu state không được chia sẻ.
- Scale-in hoặc deploy có thể làm client chuyển backend.
- Session affinity không thay thế lưu trạng thái bền vững.

Kiến trúc stateless thường dễ cân bằng giữa zone/region hơn. Lưu session trong distributed cache hoặc database có thể giúp request đi tới backend bất kỳ, nhưng cache/data layer cũng cần HA, latency và replication phù hợp.

Với multi-region, session affinity theo region có thể giảm round trip tới session store nhưng làm failover phức tạp hơn. Nếu region chính mất, session có thể phải tái tạo hoặc khôi phục từ store được replicate.

## 14. Health check và failover đúng phạm vi

Health check quyết định backend hoặc region có đủ điều kiện nhận traffic hay không. Một health check quá nông có thể báo healthy dù ứng dụng không thể phục vụ nghiệp vụ; một health check quá sâu có thể đánh dấu toàn bộ backend unhealthy khi một dependency phụ bị lỗi.

Nên phân biệt:

- **Liveness:** process còn sống và không bị kẹt tới mức cần restart.
- **Readiness:** instance có thể nhận request mới.
- **Dependency health:** database, cache hoặc service ngoài có đáp ứng không.
- **Regional health:** region có thể phục vụ luồng nghiệp vụ quan trọng hay không.

Health endpoint nên trả kết quả dựa trên các dependency thiết yếu, có timeout và tránh tạo tải lớn. Với global failover, cần health check từ nhiều vị trí hoặc nhiều tín hiệu để tránh false positive do một probe location gặp sự cố.

### 14.1. Failover có hysteresis

Nếu health thay đổi liên tục quanh ngưỡng, global routing có thể liên tục chuyển qua lại giữa các region (flapping). Dùng threshold, consecutive failures, recovery window và cooldown để giảm chuyển đổi không cần thiết.

Cần kiểm tra thời gian phát hiện, DNS TTL, resolver cache và client connection reuse. DNS failover không thể lập tức ngắt mọi connection đang mở hoặc ép tất cả resolver cập nhật cùng lúc.

## 15. Data consistency khi cân bằng tải đa vùng

Load balancing chỉ điều phối traffic. Dữ liệu cần được thiết kế riêng.

Các câu hỏi quan trọng:

- Region nào là writer chính cho từng dữ liệu?
- Replication là đồng bộ hay bất đồng bộ?
- Replication lag tối đa được chấp nhận là bao nhiêu?
- Khi failover, có thể mất các ghi chưa replicate không?
- Hai region cùng nhận write có thể tạo conflict không?
- Có cần idempotency key để tránh giao dịch lặp khi client retry?
- Khi region cũ phục hồi, quy trình rejoin và reconcile dữ liệu ra sao?

Với replication bất đồng bộ, region đích có thể thiếu các giao dịch gần nhất. RPO phụ thuộc replication lag tại thời điểm sự cố. Với replication đồng bộ, latency ghi có thể tăng do phải chờ xác nhận từ vùng khác. Chọn mô hình dựa trên yêu cầu nghiệp vụ và khoảng cách địa lý.

Không nên tự động chuyển write traffic sang region dự phòng nếu chưa xác định rõ writer/leader và cách tránh split-brain.

## 16. Ví dụ kiến trúc đa zone và đa region

Giả sử một API phục vụ người dùng tại Đông Nam Á và một nhóm người dùng ở châu Âu. Dịch vụ cần HA trong từng region và DR khi một region mất.

Một kiến trúc tham khảo:

1. Global DNS hoặc global load balancer chọn region theo latency/health.
2. Mỗi region có regional load balancer phân phối backend trên hai hoặc nhiều zone.
3. Backend chạy stateless, lưu session và dữ liệu nghiệp vụ ở dịch vụ stateful phù hợp.
4. Database có replication liên vùng theo RPO/RTO đã định.
5. Egress tới dịch vụ cloud dùng private endpoint khi phù hợp.
6. Health check khu vực kiểm tra endpoint nghiệp vụ quan trọng.
7. Khi một zone lỗi, regional LB chuyển traffic sang zone còn lại.
8. Khi cả region lỗi, global routing chuyển traffic sang region dự phòng theo runbook.
9. Sau failover, kiểm tra dữ liệu, queue, scheduled job và trạng thái ghi trước khi mở toàn bộ traffic.

~~~mermaid
flowchart TB
    C[Clients] --> G[Global traffic manager]
    G -->|Latency / health| L1[Region Singapore LB]
    G -->|Failover / policy| L2[Region Europe LB]
    subgraph SG[Region Singapore]
      L1 --> SGA[App Zone A]
      L1 --> SGB[App Zone B]
      SGA --> SGD[(Regional data endpoint)]
      SGB --> SGD
    end
    subgraph EU[Region Europe]
      L2 --> EUA[App Zone A]
      L2 --> EUB[App Zone B]
      EUA --> EUD[(Regional data endpoint)]
      EUB --> EUD
    end
    SGD <-->|Replication| EUD
~~~

Sơ đồ chỉ thể hiện khái niệm. Replication và quyền ghi cần được thiết kế theo database cụ thể. Không phải mọi database đều hỗ trợ active-active multi-region write hoặc failover tự động.

## 17. Các nền tảng cloud và cách triển khai

Các nhà cung cấp có dịch vụ tương đương về mặt chức năng nhưng khác về tên gọi, phạm vi và cách tính phí.

| Nền tảng | Cân bằng tải trong region/zone | Điều phối giữa region |
|---|---|---|
| AWS | Elastic Load Balancing với các loại ALB/NLB/GWLB và tùy chọn cross-zone tùy dịch vụ | Route 53 routing policy, AWS Global Accelerator và các mô hình multi-region |
| Azure | Azure Load Balancer, Application Gateway và dịch vụ liên quan với cấu hình zone/region tùy SKU | Azure Traffic Manager, Azure Front Door và mô hình global routing |
| Google Cloud | Cloud Load Balancing với các loại regional/global, external/internal và backend scope theo dịch vụ | Global external Application Load Balancer, Cloud DNS routing policy và kiến trúc multi-region |

Không nên suy luận rằng tất cả sản phẩm trong cùng một nền tảng có cùng hành vi cross-zone hoặc cùng phí. Trước khi triển khai, kiểm tra:

- Load balancer là regional hay global.
- Backend có thể nằm ở zone/region nào.
- Cross-zone có bật mặc định hay phải cấu hình.
- Health check được thực hiện từ đâu và theo giao thức nào.
- Source IP có được giữ nguyên hay cần PROXY protocol/forwarded header.
- TLS termination và certificate scope.
- Chi phí processed bytes, inter-zone transfer, inter-region transfer và egress.
- Hạn mức connection, throughput và số backend.

## 18. Kiểm thử và diễn tập failover

Không thể kết luận kiến trúc đa zone/region hoạt động chỉ từ việc tạo đủ backend. Cần kiểm thử đường đi và failure scenario.

Một kế hoạch kiểm thử có thể gồm:

1. Gửi tải ổn định tới tất cả backend và xác minh phân phối theo chính sách.
2. Tắt một backend và xác minh health check loại backend đó.
3. Làm mất một zone trong môi trường thử nghiệm và đo thời gian chuyển traffic.
4. Kiểm tra latency, error rate và capacity ở zone còn lại.
5. Tạo traffic liên zone có kiểm soát để đo byte và phí mạng.
6. Giả lập dependency đặt ở zone khác và đo round-trip latency.
7. Kiểm tra NAT/SNAT khi số outbound connection tăng.
8. Kiểm tra routing bất đối xứng qua firewall hoặc network appliance.
9. Giả lập region không phục vụ được và kiểm tra global failover.
10. Xác minh DNS cache, client retry và connection cũ.
11. Kiểm tra dữ liệu sau failover, replication lag và khả năng tiếp tục ghi.
12. Diễn tập failback về region chính và reconcile trạng thái.

### 18.1. Các chỉ số nên theo dõi

- Request count và backend distribution theo zone/region.
- Healthy/unhealthy host count.
- Latency p50/p95/p99 theo client location và backend zone.
- Error rate, timeout và retry rate.
- Cross-zone/cross-region bytes.
- NAT connection/port utilization và allocation errors.
- Load balancer active connections, processed bytes và queue nếu có.
- Database replication lag, failover time và write errors.
- DNS answer distribution và cache behavior.
- Capacity utilization sau khi mất một zone hoặc region.

## 19. Lỗi thiết kế thường gặp

**Triển khai nhiều zone nhưng không kiểm tra capacity khi một zone mất.** Các zone còn lại có thể quá tải sau failover. Hãy kiểm tra N-1 capacity và scale policy.

**Bật cross-zone mà bỏ qua chi phí và latency.** Traffic có thể đi qua mạng liên zone nhiều hơn dự kiến. Đo inter-zone bytes và latency trước khi quyết định.

**Dùng zone-local nhưng không có fallback.** Nếu backend trong zone không khỏe, traffic có thể bị lỗi dù zone khác còn capacity. Cần chính sách fallback rõ ràng.

**Dùng nhiều region nhưng chỉ có một data writer không được bảo vệ.** Global routing có thể chuyển traffic nhưng dữ liệu ở region đích không sẵn sàng. Thiết kế replication, promotion và RPO/RTO.

**Dùng DNS failover và giả định chuyển vùng tức thì.** Resolver và client có thể cache record; connection đang mở không tự chuyển. Đo TTL và hành vi client thực tế.

**Health check chỉ kiểm tra port.** Port mở không chứng minh ứng dụng xử lý nghiệp vụ được. Dùng readiness/health phù hợp và tránh health check quá sâu.

**Không xem return path.** Firewall stateful hoặc NAT có thể drop response khi routing bất đối xứng. Kiểm tra cả hai chiều và session state.

**Không reuse outbound connection.** SNAT port có thể cạn khi request tạo connection mới liên tục. Dùng keep-alive, pool và theo dõi NAT.

**Sticky session giữ traffic không đều.** Một số backend có thể quá tải trong khi backend khác nhàn rỗi. Ưu tiên stateless hoặc external session store nếu phù hợp.

**Failover không có failback plan.** Sau khi region chính phục hồi, dữ liệu có thể lệch hoặc traffic chuyển về quá sớm. Cần reconcile, kiểm tra writer và chuyển traffic có kiểm soát.

## 20. Checklist thiết kế load balancing theo zone/region

- [ ] Đã xác định mục tiêu: latency, HA trong zone, DR liên vùng hay residency.
- [ ] Đã phân biệt rõ phạm vi zone và region của từng dịch vụ.
- [ ] Đã chọn L4/L7 phù hợp với protocol và routing requirement.
- [ ] Backend được phân bố trên các zone và có capacity dự phòng.
- [ ] Đã quyết định zone-local hay cross-zone dựa trên latency, capacity và network cost.
- [ ] Có fallback khi backend/zone không khỏe.
- [ ] Global routing có policy geo/latency/weighted/failover phù hợp.
- [ ] Health check phản ánh khả năng phục vụ nghiệp vụ và có hysteresis.
- [ ] Đã tính DNS TTL, resolver cache và client connection reuse.
- [ ] Đã kiểm tra forward path và return path qua route, NAT và firewall.
- [ ] Đã đánh giá SNAT port capacity và connection reuse.
- [ ] Session không phụ thuộc vào một backend duy nhất nếu cần failover.
- [ ] Database/queue có replication, writer policy, RPO và RTO rõ ràng.
- [ ] Đã tính inter-zone, inter-region, NAT, load balancer và Internet egress cost.
- [ ] Có dashboard theo zone/region và cảnh báo khi traffic phân phối lệch.
- [ ] Đã kiểm thử mất backend, mất zone, mất region và failback.
- [ ] Runbook xác định người chịu trách nhiệm, tiêu chí chuyển vùng và tiêu chí quay lại.

## 21. Kết luận

Cân bằng tải theo zone giúp phân phối compute trong một region và tăng khả năng chịu lỗi cục bộ; cân bằng tải theo region điều phối traffic giữa các khu vực địa lý để giảm latency hoặc phục hồi khi một region gặp sự cố. Zone-local routing có thể giảm traffic liên zone nhưng cần capacity và fallback; cross-zone routing phân phối linh hoạt hơn nhưng có thể tăng latency và phí truyền dữ liệu. Multi-region routing cần giải quyết thêm DNS, data replication, writer ownership, RPO/RTO và failback.

Để thiết kế đúng, hãy lần theo cả request path và response path, tính các chặng network cùng chi phí, kiểm soát NAT/SNAT và stateful firewall, đồng thời đo latency theo vị trí người dùng. Health check, capacity dự phòng và diễn tập failover phải phản ánh khả năng phục vụ thực tế. Load balancer chỉ phát huy tác dụng khi compute, network và data layer được thiết kế như một hệ thống thống nhất.
