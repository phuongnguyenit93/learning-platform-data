# Luồng dữ liệu, độ trễ và chi phí egress giữa các cloud

Một hệ thống **hybrid và multicloud** có thể chạy API trên Google Cloud, xử lý dữ liệu ở AWS hoặc Azure và còn giao tiếp với hệ thống đặt tại trung tâm dữ liệu riêng. Lúc đó mỗi lần gọi API, sao chép object, gửi event, đồng bộ database hoặc xuất log đều có thể vượt ranh giới mạng, làm tăng **độ trễ**, **rủi ro vận hành** và **chi phí data transfer out (egress)**.

Bài này thuộc chương **Hạ tầng lai và đa đám mây** của module **CLOUD_PROVIDERS_GCP**. Theo phạm vi module, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua tình huống triển khai, người học lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài học kết nối những chủ đề này bằng một cách làm định lượng: **vẽ dữ liệu đi đâu, đo mất bao lâu, xác định ai trả phí và thiết kế để không gửi dữ liệu vô ích**.

Sau bài học, bạn có thể:

- Lập danh mục data flow giữa GCP, cloud khác và on-premises, tách chiều truyền, khối lượng và trách nhiệm billing.
- Phân biệt RTT, latency, throughput, bandwidth, jitter, packet loss và application latency.
- Nhận diện ứng dụng chatty, N+1 call, xử lý tuần tự xuyên cloud và hairpin routing.
- Phân loại chi phí Internet egress, inter-zone, inter-region, VPN, Interconnect, NAT, CDN và các dịch vụ lưu trữ.
- Ước tính chi phí theo GiB và theo bậc giá, không đánh đồng giá minh họa với giá thực.
- Sử dụng VPC Flow Logs, Cloud Monitoring, Cloud Billing Reports và BigQuery billing export để kiểm tra thiết kế.
- Chọn caching, batch, CDC, compression, async events hoặc đưa compute đến gần data nhằm giảm latency và egress.

**Lưu ý giá:** toàn bộ đơn giá trong bài toán số học bên dưới chỉ là **giả định sư phạm**, không phải báo giá của Google Cloud hoặc cloud khác. Chi phí thực tế thay đổi theo dịch vụ, SKU, location, tier, hợp đồng và chính sách tại thời điểm triển khai.

## 1. Luồng dữ liệu khác với sơ đồ tài nguyên

Một sơ đồ có hai VPC và một database chưa cho biết chuyện gì xảy ra khi người dùng nhấn "Đặt hàng". Nhóm kiến trúc cần biết **ai gửi thông tin nào, đến đâu, bao lâu một lần, theo đường mạng nào và dữ liệu có thể gửi lại hay không**.

Danh mục thông tin tối thiểu:

| Thuộc tính | Nội dung cần đo hoặc xác định |
|---|---|
| Source | Cloud, project/account, VPC, subnet, region và service phát dữ liệu |
| Destination | Cloud, location, endpoint, database, bucket hoặc network nhận |
| Direction | GCP → AWS/Azure, AWS/Azure → GCP, hay đi/về on-prem? |
| Payload | JSON, protobuf, image, logs, CSV/Parquet, database rows hay event |
| Volume | GiB/ngày, request/giây, bytes/request, peak throughput |
| Pattern | Synchronous RPC, async queue, snapshot, CDC hoặc batch |
| Frequency | Mỗi request, mỗi phút, mỗi giờ hoặc theo sự kiện |
| Freshness | Dữ liệu cần gần real-time hay chấp nhận trễ 5–30 phút? |
| Latency | P50/P95/P99, timeout và end-to-end SLO |
| Reliability | Retry, idempotency, checkpoint, ordering và replay |
| Security | TLS/mTLS, IAM, data classification, encryption, egress allowlist |
| Cost owner | Nhóm/project trả data transfer, NAT, gateway và xử lý |
| Observability | Logs, metrics, tracing, billing SKU và người trực xử lý |

### Ví dụ ba cloud và datacenter

~~~mermaid
flowchart LR
    U["Browser"] --> WEB["GCP Cloud Run: frontend"]
    WEB --> API["GCP GKE: Orders API"]
    API -->|"Query nhỏ"| EXT["Cloud B: pricing service"]
    EXT -->|"Response"| API
    API -->|"Events"| ERP["On-prem ERP"]
    API -->|"CDC / batch"| LAKE["Cloud C: data lake"]
    API -->|"HTTP response"| WEB
~~~

Có **nhiều chiều egress khác nhau**:

1. Request GCP gửi sang Cloud B có thể tạo data transfer out ở GCP.
2. Response Cloud B gửi lại GCP có thể tạo data transfer out ở Cloud B.
3. GCP gửi CDC/batch sang Cloud C là một luồng khác, có pricing path khác.
4. GCP gửi event về datacenter có thể sử dụng Cloud VPN/Interconnect.
5. Frontend trả nội dung tới browser là luồng Internet egress phục vụ người dùng.

Nếu chỉ tổng hợp "GCP ↔ Cloud B: 5 TiB/tháng" thì khó đối chiếu hóa đơn. Cần tách các chiều và xác định dịch vụ phát sinh traffic.

## 2. Ingress, egress và các ranh giới tính phí

**Ingress** là dữ liệu đi vào phạm vi tài nguyên/mạng được tính cước. **Egress** là dữ liệu đi ra. Trong Google Cloud, network data transfer vào GCP qua Internet thông thường không có phí transfer in, nhưng các dịch vụ nhận/ghi/xử lý dữ liệu vẫn có thể tính phí riêng.

| Loại đường | Ví dụ | Nơi kiểm tra pricing |
|---|---|---|
| Internet out từ GCP | VM/API trả kết quả ra cloud khác hoặc người dùng | Internet data transfer out, product-specific SKU |
| Network in vào GCP | AWS gửi response tới GCP | Phí phía cloud gửi, GCP receiver service fees nếu có |
| Inter-zone | VM zone A → VM zone B cùng region | VPC inter-zone rates, exceptions theo service |
| Inter-region | GCP region A → region B | GCP inter-region rates hoặc service pricing |
| Cloud Storage → cloud khác | Export object từ bucket | Cloud Storage data transfer/operations/retrieval |
| Cloud VPN | Private networks qua IPsec | Tunnel, network egress và peer-side costs |
| Cloud Interconnect | Kết nối datacenter/provider | Port, VLAN attachment, transfer out và partner |
| Cross-Cloud Interconnect | GCP tới CSP hỗ trợ | Google + remote cloud attachment/port/data transfer |
| Cloud NAT | Private workload đi ra ngoài | NAT processing/gateway và transfer out |
| Cloud CDN/Load Balancing | Cache hoặc proxy trả nội dung | Cache fill, serving, proxy data processed và egress |

Giá VM-to-VM trong VPC không đại diện cho toàn bộ Cloud Run, Cloud Storage, BigQuery hay các sản phẩm managed khác. Phải xác nhận **đúng SKU của sản phẩm, vùng nguồn/đích và network tier**.

Nguồn: [VPC network pricing](https://cloud.google.com/vpc/pricing), [Cloud Storage pricing](https://cloud.google.com/storage/pricing).

## 3. Bốn kiểu data flow cần phân tích riêng

### 3.1. API đồng bộ xuyên cloud

~~~mermaid
flowchart LR
    A["Orders API trên GCP"] -->|"HTTP/gRPC"| B["Remote pricing API"]
    B -->|"Price response"| A
    A --> R["Response người dùng"]
~~~

**Ưu điểm:** reuse service sẵn có, logic tương đối đơn giản.

**Rủi ro:** RTT và xử lý ở remote cloud nằm trực tiếp trên critical path của request. Remote outage làm tăng timeout, retry và latency của Orders API.

**Thường phù hợp:** payload nhỏ, tần suất kiểm soát được, đã có timeout/circuit breaker và phương án fallback.

### 3.2. CDC hoặc event streaming

~~~mermaid
flowchart LR
    DB["Cloud SQL GCP"] --> CDC["CDC / outbox"]
    CDC --> Q["Queue / transfer"]
    Q --> LAKE["Cloud khác: data lake"]
~~~

Chỉ gửi bản ghi thay đổi thay vì toàn bộ dữ liệu. Cần theo dõi replication lag, schema evolution, ordering, duplicate delivery, replay và dead-letter queue. Eventual consistency phù hợp analytics hoặc search index, không nhất thiết phù hợp mọi giao dịch thanh toán.

### 3.3. Bulk object/file transfer

~~~mermaid
flowchart LR
    CS["Cloud Storage GCP"] --> W["Transfer worker"]
    W --> L["Internet / Interconnect"]
    L --> OBJ["Object storage ở cloud khác"]
~~~

Với file lớn, throughput, checksum, resume và tính toàn vẹn quan trọng hơn một API RTT. Có thể cần nhiều stream song song và checkpoint để không phải chuyển lại toàn bộ khi job lỗi.

### 3.4. Hybrid on-premises

~~~mermaid
flowchart LR
    APP["GCP workload"] --> VPC["Google VPC"]
    VPC --> LINK["HA VPN / Interconnect"]
    LINK --> DC["On-premises ERP"]
    DC --> LINK
    LINK --> VPC
~~~

Ngoài bandwidth phải kiểm tra BGP, route, CIDR overlap, firewall hai chiều, DNS, VPN encapsulation, packet loss và cơ chế failover. Kết nối private **không tự biến API chatty thành API nhanh**.

## 4. Đặt compute gần dữ liệu: data gravity

Data gravity mô tả chi phí và khó khăn khi khối lượng dữ liệu lớn bị di chuyển liên tục giữa các hạ tầng. Một ML job đặt ở cloud khác nhưng mỗi ngày cần đọc cả kho dữ liệu 20 TiB tại GCP có thể tốn network nhiều hơn chi phí chạy compute.

Có ba hướng:

| Chiến lược | Lợi ích | Đánh đổi |
|---|---|---|
| Chạy xử lý gần data nguồn | Giảm egress và RTT để đọc data | Cần vận hành compute ở nơi lưu data |
| Chuyển data đến nơi đã có compute | Tận dụng pipeline có sẵn | Egress, consistency, storage duplication |
| Chuyển subset/aggregate/cache | Ít bytes hơn, read local nhanh | Staleness, cache invalidation, schema sync |

Ví dụ nếu remote cloud chỉ cần tổng hợp 2% dữ liệu cho dashboard, tính aggregate tại nguồn rồi chuyển 2% thường hợp lý hơn copy cả kho dữ liệu mỗi giờ. Tuy nhiên cần kiểm tra tài nguyên CPU/BigQuery/ETL để tạo aggregate cũng có chi phí.

**Nguyên tắc:** so sánh khối lượng *theo thời gian*. Một lần chuyển 10 TiB có thể hợp lý khi migration; chuyển 10 TiB mỗi ngày suốt nhiều tháng cần được xem lại.

## 5. Phân biệt latency, RTT, throughput và bandwidth

| Khái niệm | Đơn vị | Ý nghĩa |
|---|---|---|
| Latency | ms | Thời gian một thao tác/request trải qua hệ thống |
| RTT | ms | Thời gian dữ liệu đi tới đích rồi phản hồi quay lại |
| Throughput | Mbit/s, GiB/s | Tốc độ truyền thực tế |
| Bandwidth/capacity | Gbit/s | Năng lực danh nghĩa của đường mạng |
| Jitter | ms | Biến thiên độ trễ giữa các lần đo |
| Packet loss | % | Phần gói không đến hoặc cần gửi lại |
| TTFB | ms | Thời gian đến byte phản hồi đầu tiên |
| P95/P99 | ms | Phân vị của request latency |

Đường truyền 10 Gbit/s vẫn có thể trả kết quả API chậm nếu RTT lớn, service đích xử lý lâu, DNS/TLS phải handshake thường xuyên hoặc ứng dụng thực hiện nhiều RPC tuần tự.

### 5.1. Phân rã một request HTTPS

Một request trên connection mới có thể trải qua:

~~~text
DNS resolution
→ TCP connection
→ TLS negotiation
→ Remote application / database processing
→ Response transfer
→ Client-side parsing
~~~

Không cộng cứng mọi mốc đo của curl với nhau, vì các mốc được tính từ khi bắt đầu request và có thể chồng lấn hoặc được loại bỏ nhờ connection reuse. HTTP/2 hoặc gRPC sử dụng kết nối dài hạn có thể giảm overhead bắt tay.

### 5.2. Latency budget

Giả sử Orders API có mục tiêu P95 dưới 400 ms:

| Thành phần | Budget thiết kế |
|---|---:|
| Browser → frontend GCP | 50 ms |
| Frontend → Orders API | 40 ms |
| Business logic | 60 ms |
| Pricing RPC xuyên cloud | 150 ms |
| Database | 50 ms |
| Buffer | 50 ms |
| **Tổng ngân sách** | **400 ms** |

Đây chỉ là cách chia **latency budget**, không phải phép tính xác suất cho P95 end-to-end: tổng P95 của các thành phần không mặc nhiên bằng P95 của toàn request. Phải đo trace xuyên các dịch vụ và phân phối độ trễ thực tế.

## 6. Khi nhiều round trip làm request chậm

Một checkout gọi tuần tự 4 API tại cloud khác. Nếu đường truyền có RTT 80 ms và mỗi call cần ít nhất một round trip:

\[
T_{\text{network tối thiểu}} \approx 4 \times 80 = 320\ \text{ms}
\]

Đây chưa gồm processing, queuing, TLS handshake, serialization và database. Nếu 4 call độc lập chạy song song, critical path có thể gần độ trễ của call chậm nhất hơn là tổng bốn call.

### 6.1. N+1 query xuyên cloud

Ví dụ Orders API lấy danh sách 100 sản phẩm, rồi gọi Inventory API của cloud khác 100 lần để lấy số lượng tồn. Nếu mỗi call chờ một RTT, độ trễ tích lũy rất lớn dù mỗi payload chỉ vài byte.

Cải thiện:

1. Dùng bulk endpoint nhận nhiều product IDs trong một call.
2. Batch và gửi song song có **giới hạn concurrency**.
3. Dùng cache/read model gần nơi gọi nếu chấp nhận staleness.
4. Đồng bộ thay đổi tồn kho bằng events/CDC.
5. Tránh giữ database transaction mở trong lúc chờ remote cloud.

### 6.2. Retry không miễn phí

Khi remote API timeout, ứng dụng có thể retry. Mỗi lần retry tạo thêm request/response, có thể tăng cả egress và độ trễ, đặc biệt khi các service retry lồng nhau.

Cần có deadline propagation, exponential backoff + jitter, circuit breaker, giới hạn retry, idempotency key và alert khi tỷ lệ retry tăng.

## 7. Bandwidth-delay product và truyền dữ liệu lớn

Với TCP, đường truyền bandwidth cao nhưng RTT lớn cần đủ dữ liệu **in flight** để tận dụng capacity.

\[
BDP_{\text{bits}}=\text{Bandwidth (bit/s)}\times RTT(\text{s})
\]

Ví dụ bandwidth 1 Gbit/s và RTT 80 ms:

\[
BDP=1.000.000.000\times0,08=80.000.000\ \text{bit}
\]

Tương đương khoảng 10 MB dữ liệu đang truyền trước khi nhận ACK. Nếu TCP receive window/sender buffer nhỏ hoặc packet loss cao, throughput có thể thấp hơn rất nhiều so với 1 Gbit/s.

Những yếu tố ảnh hưởng throughput:

- TCP congestion control, window scaling và số luồng song song.
- Packet loss, retransmission và jitter.
- MTU/MSS khi qua IPsec/VXLAN tunnel.
- CPU encrypt/decrypt tại gateway, disk I/O, số request/s của storage.
- Quota/bandwidth thực của attachment, VPN tunnel hoặc cloud service.
- Source/destination application backpressure.

Một phép ping đo ICMP RTT **không chứng minh** throughput file transfer hoặc HTTP P95. Cần đo cả RTT và transfer workload đại diện.

## 8. Lựa chọn Internet, VPN và Interconnect

| Phương án | Ưu điểm | Hạn chế / chi phí |
|---|---|---|
| Public Internet + TLS | Thiết lập nhanh, phù hợp lưu lượng nhỏ | Internet egress, bảo vệ endpoint, biến thiên network |
| HA VPN | IPsec kết nối private networks | Tunnel-hour, data transfer, packet rate, MTU |
| Dedicated/Partner Cloud Interconnect | Đường private từ GCP tới datacenter/provider | Port, VLAN attachment, circuit, transfer out |
| Cross-Cloud Interconnect | Dedicated link giữa Google và CSP được hỗ trợ | Tài nguyên hai cloud, physical provisioning, egress |
| Partner Cross-Cloud Interconnect | Đối tác quản lý connectivity | Phụ thuộc region/provider và model phí |
| Transit qua on-premises | Tận dụng hạ tầng sẵn có | Hairpin tăng RTT, hai lần network boundary và fault domain |
| Managed transfer/pipeline | Retry, checkpoint, tích hợp monitoring | Service processing/storage/operations + egress |

### 8.1. Cloud VPN

Cloud VPN là kết nối site-to-site IPsec, **không phải** giải pháp biến VPC thành general Internet gateway cho client. Từng tunnel có giới hạn packet-per-second; throughput thực chịu ảnh hưởng RTT, packet size, packet loss, IPsec overhead và peer gateway.

Cần giám sát tunnel health, Cloud Router/BGP, transferred bytes, drops và failover. Với truyền file lớn, đo cả single stream và parallel streams.

### 8.2. Cross-Cloud Interconnect

Cross-Cloud Interconnect cho phép thiết lập đường kết nối chuyên dụng giữa Google Cloud và một CSP được hỗ trợ. Bài toán chi phí phải tính:

- Port/connection và VLAN attachments tại Google Cloud.
- Port/circuit/attachment ở provider đối tác.
- Data transfer out theo đường interconnect.
- Inter-region transfer nếu tài nguyên nằm ở region khác attachment.
- Redundant links và chi phí vận hành/giám sát.

Có nhiều mô hình đối tác với cách tính phí riêng; không áp dụng giá dedicated connection cho mọi phương án partner.

Nguồn: [Cross-Cloud Interconnect](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview), [Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/interconnect/pricing).

### 8.3. Đường dự phòng

Kết nối private chỉ có một đường vẫn có single point of failure. Thiết kế production có thể cần attachment ở edge availability domains khác nhau, hai Cloud Router/BGP session, dự phòng địa lý theo SLA, route filter và kiểm thử link failover.

Cloud Router quản lý **BGP routing**, không phải một thiết bị dataplane nhận từng packet của ứng dụng.

## 9. Những lỗi network thường gây tăng latency/egress

### 9.1. CIDR bị trùng

GCP và cloud khác dùng cùng dải 10.0.0.0/16 có thể gây xung đột route. Cần quy hoạch IP toàn tổ chức hoặc thiết kế NAT/transit riêng, biết rõ nguồn/đích sau translation.

### 9.2. DNS và đường đi sai

Hostname có thể resolve public IP thay vì private endpoint. Một link private đã được tạo không có nghĩa toàn bộ ứng dụng dùng link đó. Kiểm tra DNS và route **ở cả hai chiều**, tại runtime của Cloud Run/GKE/VM và tại provider bên kia.

### 9.3. MTU và fragment

VPN/IPsec encapsulation làm giảm payload MTU. Nếu Path MTU Discovery hỏng hoặc ICMP bị chặn, request nhỏ chạy nhưng file lớn có thể treo. Quan sát MSS, retransmission và gateway metrics.

### 9.4. Hairpin và asymmetric routing

Traffic GCP → AWS có thể đi qua on-prem rồi quay lại AWS thay vì đường ngắn trực tiếp; response có thể đi đường khác. Kết quả là thêm RTT, chi phí nhiều hop và khó áp firewall stateful.

### 9.5. Security

Dù dùng private link, nên bảo vệ API bằng TLS/mTLS, IAM, short-lived token và least-privilege firewall. Network private không đồng nghĩa authentication. Với dữ liệu nhạy cảm, phải đáp ứng data residency và không ghi raw payload/secret vào logs.

## 10. Phân loại đầy đủ các khoản chi phí

Công thức tư duy:

\[
C_{\text{network}} \approx
\sum_i(\text{GiB}_i\times\text{rate}_i)
+\text{fixed link fees}
+\text{processing}
\]

Bảng chi phí:

| Hạng mục | Yếu tố cần tính |
|---|---|
| GCP Internet data transfer out | Source product/region, destination và usage tier |
| Cloud bên kia data transfer out | Chiều phản hồi hoặc chiều đồng bộ ngược |
| Inter-region / inter-zone | Các hop nội bộ GCP, SKU theo dịch vụ |
| Cloud VPN | Tunnel-hour và data transfer, đối ứng ở provider |
| Interconnect | Port, connection, VLAN attachment, egress, provider circuit |
| Cloud NAT | Uptime/data processed và Internet egress |
| Load Balancer / CDN | Proxy processing, request, cache fill, serving egress |
| Cloud Storage | Operations, retrieval, transfer out và lưu dữ liệu |
| Network telemetry | Flow Logs, firewall logging, Cloud NAT logs và retention |
| Pipeline compute | CPU/memory/worker hours để transform/compress |
| Retries | Bytes và requests phát sinh thêm |

**Một flow có thể có nhiều line item** ở hai provider. Ngoài ra billing có thể tính theo các mức tier khác nhau. Không lấy một rate/GiB rồi nhân toàn bộ traffic nếu bảng giá có nhiều bậc.

Cloud Interconnect có mức data transfer đặc thù và phí port/attachment theo thời gian. Nếu attachment không ở region nơi workload phát dữ liệu, có thể phát sinh cross-region charges trước khi ra attachment.

Nguồn: [VPC pricing](https://cloud.google.com/vpc/pricing), [Interconnect pricing](https://cloud.google.com/network-connectivity/interconnect/pricing).

## 11. Bài toán mẫu: đồng bộ dữ liệu giữa hai cloud

Giả sử pipeline ở GCP xuất **1,5 TiB/ngày** sang data lake ở cloud khác, chạy 30 ngày. Ta dùng **đơn giá giả định** 0,08 USD/GiB, bỏ qua các bậc giá thực, phí cloud nhận và service khác.

### 11.1. Không tối ưu

\[
V_{\text{tháng}}=1,5\times30=45\ \text{TiB}
\]

\[
45\ \text{TiB}\times1024=46.080\ \text{GiB}
\]

\[
C_{\text{giả định}}=46.080\times0,08
=3.686,40\ \text{USD/tháng}
\]

### 11.2. Lọc 70% dữ liệu tại GCP

Nếu downstream chỉ cần 30% bản ghi/cột sau aggregate:

\[
V_{\text{mới}}=46.080\times0,30=13.824\ \text{GiB}
\]

\[
C_{\text{mới}}=13.824\times0,08=1.105,92\ \text{USD}
\]

Chênh lệch:

\[
3.686,40-1.105,92=2.580,48\ \text{USD/tháng}
\]

| Phương án | GiB/tháng | Giá minh họa | Egress estimate |
|---|---:|---:|---:|
| Full copy hằng ngày | 46.080 | 0,08 USD/GiB | 3.686,40 USD |
| Chỉ gửi 30% | 13.824 | 0,08 USD/GiB | 1.105,92 USD |
| **Giảm** | **32.256** | — | **2.580,48 USD** |

Chi phí khác có thể gồm compute filter, data pipeline, Cloud Storage operations, NAT, VPN/Interconnect và cả cloud đích. Đây là **mô hình học cách tính**, không phải dự báo hóa đơn production.

## 12. Internet hay private Interconnect: so sánh TCO

Chọn phương án connectivity dựa trên **total cost of ownership (TCO)**, độ tin cậy, bảo mật và latency SLO, không chỉ giá truyền một GiB.

~~~text
Internet_TCO =
  GCP_Internet_egress
+ Counterpart_cloud_egress_on_reverse_flows
+ NAT_LB_Storage_Processing
+ Network_operations

Private_TCO =
  GCP_connection_and_attachment_hours
+ Other_cloud_ports_and_circuits
+ Interconnect_transfer_out
+ Cross_region_data_transfer_if_applicable
+ Other_cloud_egress_and_transfer_fees
+ Network_processing_and_operations
+ Redundant_links
~~~

| Hạng mục | Internet + TLS | Private Interconnect |
|---|---|---|
| Upfront setup | Thường đơn giản | Có thể cần provisioning/circuit |
| Phí đường cố định | Thấp hoặc không | Port/attachment/partner |
| Data transfer out | Internet SKU | Interconnect/partner SKU |
| Phí cloud còn lại | Có thể có | Có thể có và có attachment fee |
| Khả năng dự phòng | Dựa kiến trúc endpoint/Internet | Phải thiết kế nhiều link nếu cần HA |
| Jitter/latency | Phụ thuộc mạng public | Có thể ổn định hơn, tùy topology |
| Thời gian triển khai | Ngắn hơn trong nhiều trường hợp | Có thể dài với dedicated physical |

So sánh hai phương án cần cùng traffic, số chiều dữ liệu, region, SLA và yêu cầu bảo mật. Đừng so đường private một link với Internet có nhiều đường dự phòng rồi kết luận về độ tin cậy.

## 13. Giảm egress mà không đánh đổi dữ liệu đúng

Các biện pháp tối ưu nên được phân nhóm theo **byte volume**, **số lần gọi** và **hướng truyền**, không tùy tiện bật cache cho mọi dữ liệu.

### 13.1. Giảm tổng số byte

- Dùng CDC/delta update thay full snapshot.
- Lọc các cột và hàng mà downstream thực sự cần.
- Aggregate gần source rồi chỉ gửi kết quả thống kê.
- Dùng Parquet hoặc các định dạng columnar phù hợp với analytics.
- Nén JSON/binary khi lợi ích giảm bytes lớn hơn overhead CPU/latency.
- Gắn checksum hoặc content digest để không copy lại object đã có.
- Không xuất trùng traces/logs sang nhiều provider nếu không có yêu cầu.

Nén dữ liệu đã nén như JPEG, MP4 có thể không hiệu quả. Cần thử với dữ liệu thật. Nếu bước filter tốn nhiều compute, phải cộng chi phí transform vào TCO.

### 13.2. Giảm số lần vượt ranh giới cloud

- Batch nhiều record thành một RPC thay vì N+1 calls.
- Dùng bulk API và pagination hợp lý.
- Đặt cache/materialized read model gần nơi xử lý request.
- Dùng event-driven asynchronous transfer để tách availability của hai cloud.
- Tách OLTP transaction khỏi data export và analytics.
- Với ML, cân nhắc đặt inference model gần ứng dụng, còn training lớn ở cloud khác.

### 13.3. Giảm coupling khi cloud khác sự cố

- Propagate deadline từ frontend đến downstream.
- Retry có backoff + jitter và giới hạn tổng thời gian.
- Dùng circuit breaker, bounded queue và backpressure.
- Thêm idempotency key cho event có side effect.
- Đặt giới hạn concurrency tránh làm nghẽn link hoặc remote API.
- Cảnh báo khi queue lag hoặc retry rate tăng.

**Không cache tùy tiện thông tin giá, tồn kho, thanh toán hoặc dữ liệu nhạy cảm.** Cần thống nhất TTL, cơ chế invalidation, encryption, access control và ngưỡng staleness với business owner.

## 14. Đồng bộ và bất đồng bộ: chọn theo consistency

| Thuộc tính | RPC/HTTP đồng bộ | CDC/event/batch bất đồng bộ |
|---|---|---|
| Freshness | Có thể phản ánh trạng thái tại lúc gọi | Chậm theo replication lag |
| User latency | Phụ thuộc remote RTT và service | Đọc local thường nhanh hơn |
| Data transfer | Theo request/response | Theo delta hoặc batch |
| Khi cloud khác outage | Có thể lan lỗi tới request | Queue cho phép retry sau |
| Tính nhất quán | Đơn giản hơn cho một số read | Cần ordering, dedupe và reconciliation |
| Complexity | Dễ bắt đầu, rủi ro nếu chatty | Vận hành pipeline và schema version |

Với checkout cần xác nhận thanh toán, có thể vẫn phải dùng một luồng đồng bộ được thiết kế an toàn. Với báo cáo doanh thu theo giờ, dữ liệu chậm vài phút có thể hoàn toàn chấp nhận được và cho phép dùng CDC/batch.

Cả hai phương án cần xác định **source of truth**. Nếu cả GCP và cloud khác cùng ghi primary database mà không có giải pháp multi-writer consistency được thiết kế, rất dễ phát sinh dữ liệu phân kỳ hoặc split-brain.

## 15. SLO và latency budget cho dependency xuyên cloud

Khi một dependency có RTT lớn, cả nhóm API/SRE/Network phải thỏa thuận:

1. End-to-end SLO, ví dụ P95 checkout dưới 400 ms.
2. Thời gian dành cho từng call và tổng deadline.
3. Remote service được phép timeout bao lâu.
4. Có fallback/degraded mode hay không.
5. Có thể cache dữ liệu gì và stale bao lâu.
6. Retry tối đa bao nhiêu lần để tránh tăng egress vô hạn.
7. Chỉ tiêu connection reuse, error rate và packet loss.
8. Ngưỡng cảnh báo khi SLO bị phá vỡ.

Một bảng budget minh họa:

| Flow | Budget P95 | Error budget riêng | Chủ sở hữu |
|---|---:|---|---|
| Browser → Cloud Run | 80 ms | Theo frontend SLO | Web team |
| Cloud Run → GKE API | 40 ms | Theo API SLO | App team |
| GKE → remote pricing | 150 ms | Có fallback/cache | Integration team |
| GKE → Cloud SQL local | 50 ms | Không làm mất transaction | Data team |
| Business processing/buffer | 80 ms | Theo quy tắc nghiệp vụ | App/SRE |
| **Tổng thiết kế** | **400 ms** | — | Product/SRE |

Các số này là **ngân sách thành phần**, không phải cam kết rằng P95 của tổng bằng tổng các P95. Phải đo end-to-end trace.

## 16. Đo latency theo đúng lớp

### 16.1. Distributed tracing

~~~text
checkout request
  ├─ auth
  ├─ local Cloud SQL query
  ├─ cross-cloud pricing request
  │   ├─ connection / TLS (nếu mới)
  │   ├─ remote service processing
  │   └─ response transfer
  └─ order commit
~~~

Span nên gắn service, cloud, region, dependency name và số lần retry. Tránh ghi token hoặc payload nhạy cảm. Khi P95 tăng, xác định thời gian nằm ở network, remote compute, database hay queue.

### 16.2. curl timing

Ví dụ đo HTTP endpoint được phép truy cập:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'dns=%{time_namelookup} connect=%{time_connect} tls_until=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' \
  https://api.example.com/health
~~~

Các giá trị đều là mốc **tính từ đầu request**. Chúng không phải các durations độc lập cần cộng lại. Với TLS handshake mới, thời gian riêng của TLS có thể ước tính bằng time_appconnect trừ time_connect; với connection reuse thì kết quả khác.

### 16.3. Throughput benchmarking

Trên **hai endpoint mà tổ chức cho phép thử nghiệm**, đo cả:

- Single stream và nhiều TCP streams.
- Peak và off-peak throughput.
- RTT, jitter, packet loss, retransmission và CPU.
- MTU/MSS, VPN encryption overhead.
- Data checksum, retry count và total transfer elapsed.
- Throughput ứng dụng thực tế chứ không chỉ link line rate.

Không chạy load test lớn vào môi trường production/endpoint đối tác chưa được phê duyệt. Công cụ thử nghiệm là một phần của runbook capacity testing, không thay thế product metrics.

## 17. VPC Flow Logs và Network Monitoring

**VPC Flow Logs** lấy mẫu network traffic và tổng hợp theo 5-tuple gồm source/destination IP, port và protocol. Theo cấu hình hỗ trợ, có thể quan sát traffic từ VM/GKE, Cloud Run với Direct VPC egress và traffic qua Cloud VPN hoặc Cloud Interconnect VLAN attachment.

Những câu hỏi Flow Logs giúp trả lời:

- Flow nào gửi nhiều bytes ra ngoài GCP?
- Có lưu lượng không mong muốn đi qua region hoặc Internet path khác dự kiến?
- Sau deployment mới, số connection ra cloud khác có tăng không?
- Một source VPC/subnet có đang giao tiếp với endpoint không được phép?
- Có biểu hiện network hairpin hoặc kết nối thất bại cần điều tra không?

**Hạn chế rất quan trọng:** Flow Logs sử dụng sampling và aggregation. Nó không phải một bộ đếm đầy đủ để **tái tạo chính xác hóa đơn**. Độ lệch so với billed bytes còn đến từ protocol overhead, SKU và phạm vi tài nguyên. Hãy dùng Flow Logs để tìm nguyên nhân; dùng Billing export để đối chiếu chi phí tài chính.

### 17.1. Metrics cần theo dõi

| Metric | Nguồn | Ý nghĩa |
|---|---|---|
| Request latency P50/P95/P99 | Cloud Monitoring/Trace | Tác động tới SLO |
| Error rate/retries | App metrics | Sự cố khuếch đại traffic |
| Bytes sent/received | Network/service metrics | Volume trend |
| VPN status, throughput | Cloud VPN metrics | Capacity/tunnel health |
| Interconnect attachment throughput | Interconnect metrics | Utilization |
| Loss/retransmission | Host/network telemetry | Throughput degradation |
| Queue depth/CDC lag | Data pipeline metrics | Freshness và backlog |
| Cache hit ratio | CDN/application cache | Hiệu quả giảm egress |
| Cost per SKU | Cloud Billing Reports/BigQuery | Chi phí thực tế |

### 17.2. Cost của observability

Network telemetry logs có thể phát sinh phí vended logs, lưu trữ, export và BigQuery; sampling/retention cần được thiết kế có kiểm soát. Đừng bật logging ở mức tối đa toàn tổ chức mà không tính chi phí và dữ liệu nhạy cảm.

Nguồn: [VPC Flow Logs](https://cloud.google.com/vpc/docs/flow-logs), [VPC Pricing](https://cloud.google.com/vpc/pricing).

## 18. Cloud Billing Reports: tìm khoản egress

Trong Google Cloud Console, chọn **Cloud Billing → Reports**. Nhóm nên:

1. Lọc theo billing account, project, service và khoảng thời gian.
2. **Group by SKU** để phát hiện data transfer line items.
3. Kiểm tra từng product: Networking/Compute Engine, Cloud Run, Storage, Load Balancing và các service khác.
4. So sánh tuần trước/tuần sau khi triển khai kiến trúc mới.
5. Đối chiếu SKU tăng chi phí với flow ID, bytes và trace.
6. Thiết lập budget alert cho dự án hoặc nhóm dịch vụ.
7. Kiểm tra tổng trước/sau credits theo đúng cách báo cáo tài chính của tổ chức.

Đừng chỉ lọc service bằng một tên sản phẩm rồi kết luận đó là toàn bộ egress: transfer có thể xuất hiện dưới SKU của nhiều sản phẩm.

Nguồn: [Billing Reports](https://cloud.google.com/billing/docs/how-to/reports).

## 19. Xuất billing sang BigQuery để đo theo SKU

Cloud Billing standard/detailed usage export cung cấp service, SKU, project, location, cost, usage, credits, currency và các thông tin liên quan. Muốn phân tích chi tiết, cần bật billing export trước; khả năng backfill phụ thuộc dataset location và loại export.

SQL minh họa dưới đây tổng hợp theo ngày, project và SKU. Tên bảng chỉ là **placeholder**; thay bằng bảng export thật (nếu project ID có dấu gạch nối, bao tên bảng bằng dấu backtick theo cú pháp BigQuery):

~~~sql
SELECT
  DATE(usage_start_time) AS usage_day,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  currency,
  ROUND(SUM(cost), 2) AS cost_before_credits,
  ROUND(
    SUM(
      cost + IFNULL(
        (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
        0
      )
    ), 2
  ) AS cost_after_row_credits
FROM
  BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_v1_XXXXXX
WHERE
  usage_start_time >= TIMESTAMP('2026-11-01')
  AND usage_start_time < TIMESTAMP('2026-12-01')
  AND (
    REGEXP_CONTAINS(
      LOWER(sku.description),
      r'egress|data transfer|network|interconnect|vpn|nat'
    )
    OR REGEXP_CONTAINS(LOWER(service.description), r'networking')
  )
GROUP BY
  usage_day, project_id, service_name, sku_name, currency
ORDER BY
  usage_day DESC, cost_before_credits DESC;
~~~

Lưu ý:

- Regex là bộ lọc **khám phá**, không bảo đảm bắt được mọi egress SKU. Dùng **SKU ID allowlist** sau khi kiểm tra hóa đơn thật.
- Cost sau line-item credits không nhất thiết bằng hóa đơn cuối cùng (có tax/adjustments/invoice-level items).
- Không cộng lẫn nhiều currency.
- Dataset billing export có thể có độ trễ, không phù hợp làm real-time network meter.
- Nếu cần chargeback theo team, gắn labels hợp lệ vào resource hoặc data pipeline để phân nhóm.

Nguồn: [Export Cloud Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery).

## 20. Lab: tối ưu Orders API và machine learning trên cloud khác

Giả sử công ty triển khai:

- Orders API trên Cloud Run, database giao dịch ở Cloud SQL cùng region.
- ML training trên một cloud khác.
- ERP tại datacenter riêng, nhận đơn hàng qua sự kiện.
- Analytics cần bản tổng hợp 5 phút một lần.

### 20.1. Phương án A: request phụ thuộc cloud khác

~~~mermaid
flowchart TD
    USER["Người dùng"] --> ORD["GCP Orders API"]
    ORD --> SQL["Cloud SQL"]
    ORD --> ML["Remote ML API"]
    ML --> DB2["Remote feature store"]
    ORD --> ERP["On-prem ERP"]
~~~

Rủi ro:

- Checkout chờ remote ML API/feature store.
- Response của ML có thể lớn, tạo transfer out ở cloud khác.
- Khi remote ML timeout, retries tăng latency và bytes.
- Khi ERP chậm, transaction có thể giữ tài nguyên quá lâu nếu gọi đồng bộ.

### 20.2. Phương án B: tách inference và data transfer

~~~mermaid
flowchart TD
    SQL["Cloud SQL GCP"] --> CDC["CDC/export delta"]
    CDC --> AGG["Filter/aggregate"]
    AGG --> TRAIN["ML training cloud khác"]
    TRAIN -->|"Model artifact/version"| MODEL["Inference gần Orders API GCP"]
    MODEL --> ORD["Orders API"]
    ORD --> Q["Durable event queue"]
    Q --> ERP["On-prem ERP"]
~~~

Bài toán chuyển từ nhiều **small synchronous RPCs** thành đồng bộ dữ liệu/bản model theo chu kỳ có kiểm soát. Nếu model có thể phục vụ gần Orders API, checkout có thể giảm RTT và remote dependency. Nhưng phải kiểm tra freshness, data residency, chi phí compute/model serving và tính chính xác của dự đoán.

### 20.3. Điền flow register

| Flow ID | Source → Destination | Pattern | Data/SLO cần đo |
|---|---|---|---|
| F1 | Orders API → Cloud SQL | Synchronous local | Query P95, connections |
| F2 | GCP → ML training cloud | Batch/CDC | GiB/ngày, retry, freshness |
| F3 | ML cloud → GCP model artifact | Versioned transfer | Artifact size, checksum, provenance |
| F4 | Orders API → ERP | Async event | Queue lag, idempotency, throughput |
| F5 | Orders API → browser | HTTP | Response P95, bytes, CDN |

Người học cần tính volume hai chiều, kiểm tra pricing SKU tương ứng, đo SLO và đề xuất ít nhất một tối ưu tạo lợi ích lớn nhất.

## 21. Kế hoạch thử nghiệm thay đổi

1. **Baseline:** đo 7–14 ngày về bytes, P95/P99, retry count, cache hit và billing.
2. **Hypothesis:** ví dụ "chuyển full copy sang CDC sẽ giảm ≥60% outbound GiB nhưng data freshness không quá 10 phút".
3. **Controlled change:** thử ở staging hoặc canary nhỏ.
4. **Measure:** đo raw bytes/response, data transfer theo route, errors, cloud billing, lag và tính nhất quán.
5. **Security review:** IAM, encryption, network path, data residency và log redaction.
6. **Compare:** TCO và SLO trước/sau cùng kỳ, cùng traffic.
7. **Decision:** giữ/rollback, ghi owner và các vấn đề còn lại.

Không lấy một phép đo 5 phút lúc ít traffic rồi ngoại suy 12 tháng. Batch cuối tháng, backup, lỗi/retries và peak season thường làm volume thay đổi mạnh.

### Tiêu chí nghiệm thu minh họa

| Chỉ tiêu | Trước | Sau khi tối ưu | Đo bằng |
|---|---|---|---|
| Data transfer GCP out | 1,5 TiB/ngày | ≤0,6 TiB/ngày | Bill + network/app metrics |
| P95 checkout | 600 ms | ≤400 ms | Distributed traces |
| Data freshness | Query trực tiếp | ≤10 phút | CDC lag |
| Duplicate event side effect | Chưa kiểm soát | 0 trong test idempotency | Business test |
| Monthly network cost | Baseline thực | Giảm ≥30% | Billing SKU report |
| Link availability | Không rõ | Đạt SLO đã duyệt | VPN/Interconnect metrics |

Các số ở đây là target của bài tập, không phải ngưỡng mặc định của GCP.

## 22. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Egress bill tăng khi request không tăng | Response lớn, log export, retry, backup, cross-region fetch | Billing SKU, flow logs, release timeline |
| P95 chậm chỉ ở một cloud | RTT, DNS/TLS, remote API, packet loss | Distributed tracing và RTT/packet metrics |
| VPN packet loss hoặc throughput thấp | MTU/MSS, encryption CPU, peer capacity, retransmit | Tunnel metrics và controlled benchmark |
| Link 10 Gbit/s nhưng copy file chậm | Single stream/window/RTT hoặc storage IOPS | BDP, parallel transfer, source/destination I/O |
| Flow Logs bytes không khớp bill | Sampling/aggregation và billing product scope | Flow Logs cho chẩn đoán, Billing export cho tài chính |
| Traffic qua Internet dù có private link | Public DNS, sai route/BGP quảng bá | Kiểm tra route/DNS cả hai phía |
| Unit confusion | Nhầm GB/GiB, Gbit/s/GB/s | Chuẩn hóa đơn vị và nhãn chart |
| Cache giảm bill nhưng trả dữ liệu cũ | TTL/invalidation không đáp ứng nghiệp vụ | Freshness contract tests |
| CDC tăng lag | Backlog, resource thiếu, retry loop | Queue metrics, replication lag, DLQ |
| Interconnect bill tăng | Attachment khác region source hoặc nhiều port không cần | Pricing theo location và resource |
| Hai cloud đều tính data transfer | Traffic hai chiều, mỗi provider có SKU riêng | Tách source/destination của từng flow |
| NAT cost bất ngờ | Gateway processing và traffic phát sinh | NAT SKU, route, egress amount |

## 23. Checklist kiến trúc đa cloud

- [ ] Có data flow diagram với source, destination, region và chiều gửi.
- [ ] Đo GiB/ngày, peak MiB/s, request/s và size của response.
- [ ] Phân biệt ingress, Internet egress, inter-zone, inter-region và interconnect.
- [ ] Xác nhận bảng giá theo đúng sản phẩm/SKU, destination và usage tiers.
- [ ] Tính cả fees từ cloud khác, NAT, VPN, Interconnect, LB, storage, logs và compute.
- [ ] Đo RTT, P95/P99, throughput, jitter, loss và retry trên workload thật.
- [ ] Xác định synchronous call fanout/N+1 và timeout budget.
- [ ] Chọn Internet/VPN/Interconnect theo SLO, bảo mật, TCO và volume.
- [ ] Kiểm tra CIDR, route/BGP, DNS, firewall và MTU.
- [ ] Không giả định private link làm egress miễn phí.
- [ ] Có phương án batch/CDC/cache/filter/compression với dữ liệu phù hợp.
- [ ] Có idempotency, replay, bounded retry và cơ chế xử lý lỗi.
- [ ] VPC Flow Logs và billing export có retention/filter/cost guardrail.
- [ ] Có dự toán, budget alerts và owner cho từng data flow.
- [ ] Đảm bảo encryption, IAM, data residency và log không làm lộ dữ liệu.
- [ ] Canaries và failover test đã được thực hiện trước production.
- [ ] Có chu kỳ xem lại kiến trúc khi data volume hoặc pricing thay đổi.

## 24. Câu hỏi tự kiểm tra

**1. Vì sao phải tách traffic GCP → cloud B và cloud B → GCP?**

Mỗi chiều có source và volume khác nhau. Request nhỏ từ GCP có thể có response lớn từ cloud B, tạo phần lớn data transfer out ở cloud B.

**2. GCP ingress miễn phí có nghĩa nhận dữ liệu không bao giờ tốn phí?**

Không. Network transfer in thông thường có thể miễn phí, nhưng dịch vụ nhận/ghi/xử lý, load balancing và storage operations vẫn có thể tính phí riêng.

**3. Vì sao bandwidth cao không đủ để có API latency thấp?**

RTT, DNS/TLS, xử lý bên kia, request fanout, queuing và packet loss đều ảnh hưởng thời gian phản hồi; bandwidth chỉ mô tả năng lực truyền.

**4. BDP 1 Gbit/s với RTT 80 ms xấp xỉ bao nhiêu?**

80 Mbit, tương đương 10 MB dữ liệu đang truyền. TCP window/parallelism/packet loss có thể quyết định throughput thực.

**5. Có thể dùng VPC Flow Logs để tái dựng chính xác hóa đơn egress không?**

Không. Logs được lấy mẫu và tổng hợp, không bao phủ đầy đủ mọi product/SKU. Dùng Billing export làm dữ liệu tài chính, Flow Logs để tìm flow gây chi phí.

**6. CDC giảm egress thế nào?**

Nó gửi những thay đổi mới thay vì truyền lại toàn bộ dữ liệu. Cần kiểm soát lag, schema, ordering, dedupe và reconciliation.

**7. Cross-Cloud Interconnect có luôn rẻ hơn Internet không?**

Không. Cần cộng port/attachment, counterpart provider, data transfer, redundant links, monitoring và cross-region transit khi có.

**8. Trong bài toán 1,5 TiB/ngày, lọc 70% tiết kiệm giả định bao nhiêu?**

Với 30 ngày và giá mô phỏng 0,08 USD/GiB, estimate giảm từ 3.686,40 USD xuống 1.105,92 USD, chênh 2.580,48 USD/tháng, chưa tính compute/connection fees và pricing tiers thực.

## 25. Tài liệu tham khảo

- [Google Cloud: VPC network pricing](https://cloud.google.com/vpc/pricing)
- [Google Cloud: Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Google Cloud: Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Google Cloud: Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- [Google Cloud: Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/interconnect/pricing)
- [Google Cloud: Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [Google Cloud: Cross-Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview)
- [Google Cloud: Cloud VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Google Cloud: VPC Flow Logs](https://cloud.google.com/vpc/docs/flow-logs)
- [Google Cloud: Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports)
- [Google Cloud: Export Cloud Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud: Set up Billing export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Google Cloud: Networking products](https://cloud.google.com/products/networking)


