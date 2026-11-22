# Nhận diện chi phí NAT, truyền dữ liệu và gọi liên vùng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện các thành phần tạo chi phí mạng trong ứng dụng serverless.
- Phân biệt chi phí NAT gateway, địa chỉ IP public, data processing, data transfer và request đến managed service.
- Đọc đường đi của traffic để xác định thành phần nào có thể bị tính phí.
- Phân biệt truyền dữ liệu trong cùng zone, khác zone, khác region, ra Internet và qua mạng hybrid.
- Ước tính chi phí theo GB, giờ chạy, số kết nối, số invocation và lượng retry.
- So sánh NAT với private endpoint, gateway endpoint, proxy và kết nối private.
- Phân bổ chi phí cho function, team, môi trường và sản phẩm theo nguyên tắc FinOps.
- Đưa ra quyết định tối ưu dựa trên tổng chi phí, độ sẵn sàng, bảo mật và độ trễ.

## 1. Vì sao mạng serverless có thể tạo chi phí đáng kể?

Serverless thường khiến người phát triển chú ý đến số invocation, thời gian thực thi và bộ nhớ của function. Tuy nhiên, một function có thể phát sinh chi phí mạng đáng kể khi gọi database, object storage, API đối tác, message broker hoặc dịch vụ ở region khác.

Các khoản phí có thể đến từ nhiều lớp:

- NAT gateway hoặc dịch vụ NAT xử lý traffic.
- Địa chỉ IPv4 public được reserve hoặc gắn với NAT.
- Dữ liệu được truyền qua Internet hoặc giữa zone/region.
- Private endpoint, interface endpoint hoặc PrivateLink.
- VPC connector, firewall, proxy, VPN, Interconnect hoặc ExpressRoute.
- Request, operation hoặc transaction tại dịch vụ đích.
- Compute tăng thêm do function chờ mạng lâu hoặc retry.
- Log, trace và metric dùng để quan sát lưu lượng.

Một request có thể đi qua nhiều lớp tính phí. Ví dụ, function ở private subnet gọi API public qua NAT: có thể phát sinh phí NAT theo giờ, phí xử lý dữ liệu NAT, phí data transfer out của cloud và phí request tại API đích. Cần đọc bảng giá của từng dịch vụ để xác định khoản nào áp dụng và khoản nào đã được bao gồm.

### 1.1. Phân biệt các khái niệm chi phí

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| NAT hourly/resource fee | Phí duy trì NAT gateway hoặc tài nguyên NAT theo thời gian | NAT Gateway tồn tại trong một giờ |
| NAT data processing | Phí xử lý mỗi GB đi qua NAT | Function tải 40 GB qua NAT |
| Public IP fee | Phí địa chỉ IPv4 public theo chính sách provider | Elastic IP hoặc reserved external IP |
| Data transfer out | Phí dữ liệu rời khỏi cloud hoặc region | Gửi response đến Internet |
| Inter-zone transfer | Phí truyền giữa các zone trong một region | Function ở zone A gọi database ở zone B |
| Inter-region transfer | Phí truyền giữa các region | Function tại region A gọi database region B |
| Endpoint fee | Phí tạo endpoint và/hoặc xử lý dữ liệu | Interface VPC endpoint |
| Service request fee | Phí API operation tại dịch vụ đích | Object GET, queue request, database I/O |
| Compute impact | Chi phí function chạy lâu hơn hoặc retry nhiều hơn | Request chờ API chậm thêm 2 giây |

Không cộng tất cả các dòng một cách máy móc. Một số dịch vụ có miễn phí theo loại traffic, quota, tier hoặc vùng; một số loại transfer được tính ở phía nguồn, phía đích hoặc cả hai theo quy tắc riêng. Cần dùng pricing calculator và tài liệu giá hiện hành của đúng provider, region, loại endpoint và SKU.

### 1.2. Đường đi của traffic quyết định hóa đơn

~~~mermaid
flowchart LR
    A[Serverless function] --> B{Destination}
    B -->|Public Internet| C[NAT / Internet egress]
    B -->|Private service| D[Private endpoint]
    B -->|Same VPC or VNet| E[Private route]
    B -->|Other region| F[Inter-region path]
    C --> G[External API]
    D --> H[Managed service]
    E --> I[Private database]
    F --> J[Remote region service]
~~~

Trước khi ước tính chi phí, hãy trả lời:

1. Function chạy ở region và zone nào?
2. Destination ở đâu: cùng subnet, cùng VPC, khác zone, khác region hay Internet?
3. Traffic đi qua NAT, endpoint, peering, transit gateway hay mạng hybrid?
4. Bao nhiêu GB được truyền theo chiều đi và chiều về?
5. Có bao nhiêu request, connection và retry?
6. Tài nguyên mạng nào chạy liên tục dù không có invocation?

## 2. Chi phí NAT gateway

NAT cho phép workload trong private network khởi tạo kết nối đến destination bên ngoài mà không cần public IP trực tiếp trên từng instance hoặc function. NAT thường được dùng khi function cần gọi public API, tải package hoặc truy cập dịch vụ không có private endpoint phù hợp.

NAT không miễn phí chỉ vì function là serverless. Nó là tài nguyên mạng riêng, có thể tính phí theo thời gian tồn tại, lượng dữ liệu xử lý, địa chỉ IP hoặc mức sử dụng khác tùy provider.

### 2.1. Các thành phần phí thường gặp

| Thành phần | Cách tính thường gặp | Câu hỏi cần kiểm tra |
|---|---|---|
| NAT gateway hourly | Theo giờ NAT được provision | Có cần NAT cả ngày hay chỉ theo môi trường hoạt động? |
| NAT data processing | Theo GB/GiB được NAT xử lý | Tổng byte outbound và inbound qua NAT là bao nhiêu? |
| Public IPv4 | Theo giờ hoặc theo trạng thái địa chỉ | NAT cần bao nhiêu IP public? |
| Data transfer out | Theo GB ra Internet | Cloud có tính riêng data egress ngoài phí NAT không? |
| Cross-zone path | Theo GB giữa zone | Subnet và NAT có nằm cùng zone không? |
| Logging/monitoring | Theo log ingestion, retention hoặc metric | Flow log có volume lớn không? |

Một NAT có thể tồn tại 730 giờ mỗi tháng ngay cả khi function chỉ chạy vài phút. Vì vậy, với traffic thấp và không liên tục, phí cố định theo giờ có thể lớn hơn phí xử lý dữ liệu.

### 2.2. AWS NAT Gateway

Với AWS, NAT Gateway thường có phí theo giờ và theo lượng dữ liệu được xử lý. Elastic IP hoặc public IPv4 có thể có khoản phí riêng theo chính sách địa chỉ hiện hành. Data transfer out ra Internet và một số đường truyền cross-AZ có thể được tính riêng.

Một kiến trúc phổ biến:

~~~mermaid
flowchart LR
    A[Lambda in private subnet] --> B[Route table]
    B --> C[NAT Gateway]
    C --> D[Internet Gateway]
    D --> E[Partner API]
~~~

Các điểm cần kiểm tra:

- NAT Gateway có được tạo ở mỗi Availability Zone hay không.
- Private subnet route đến NAT trong cùng zone hay đi cross-AZ.
- Function có gọi S3, DynamoDB hoặc dịch vụ AWS có thể truy cập qua VPC endpoint thay vì NAT không.
- Có interface endpoint nào làm giảm NAT traffic nhưng lại thêm phí endpoint theo giờ và data processing không.
- Public IPv4/EIP được cấp cho NAT có phát sinh phí riêng không.
- Data transfer out và cross-AZ có được tính thêm theo đường đi thực tế không.

Với Lambda trong VPC, đặt function vào subnet được gọi là public không tự cấp public IP cho network interface của Lambda. Nếu cần Internet IPv4 egress theo mô hình private subnet, thường phải cấu hình NAT và route phù hợp. Đừng tạo NAT trước khi kiểm kê destination: nhiều AWS service có thể được gọi qua endpoint riêng.

### 2.3. Google Cloud NAT

Cloud NAT cung cấp NAT cho tài nguyên trong VPC. Chi phí có thể liên quan đến gateway, data processing và external IP theo cấu hình/tier hiện hành. Serverless VPC Access connector có thể có chi phí compute riêng nếu function sử dụng connector; Direct VPC egress có mô hình chi phí và giới hạn khác.

Khi ước tính cho Cloud Run functions:

- Xác định function dùng Serverless VPC Access connector hay Direct VPC egress.
- Xác định egress mode: chỉ private ranges hay toàn bộ traffic.
- Kiểm tra Cloud NAT có cấp external IP tự động hay dùng địa chỉ reserve.
- Xác định số subnet, IP range và lượng dữ liệu đi qua NAT.
- Kiểm tra traffic đến Google APIs có thể dùng Private Google Access hoặc Private Service Connect.
- Đọc pricing theo region và loại NAT; không suy ra chi phí chỉ từ số function invocation.

Nếu function chỉ cần gọi private database, có thể không cần đưa toàn bộ Internet traffic qua Cloud NAT. Nếu bật all-traffic, mọi destination Internet có thể đi qua VPC, làm thay đổi lượng dữ liệu được tính phí và yêu cầu route/firewall.

### 2.4. Azure NAT Gateway

Azure NAT Gateway thường có phí theo thời gian provision và lượng dữ liệu được xử lý; public IP resource có thể có phí riêng. VNet integration và routing của Azure Functions phụ thuộc hosting plan và cấu hình networking.

Khi ước tính:

- Xác định NAT Gateway gắn với subnet nào.
- Kiểm tra số public IP/prefix được cấp.
- Xác định traffic function thực sự đi qua subnet tích hợp.
- Kiểm tra Azure Firewall hoặc proxy có nằm trên đường đi và có phí riêng.
- Xác định data transfer out, VNet peering hoặc kết nối hybrid phát sinh.
- Đọc giá theo region, SKU và loại IP.

NAT Gateway cung cấp outbound SNAT; nó không tự thực hiện domain allowlist hay thay thế Azure Firewall. Nếu triển khai thêm firewall/proxy để kiểm soát egress, cần tính cả chi phí xử lý của lớp đó.

### 2.5. NAT có phí cố định dù không có traffic

Giả sử một NAT chạy liên tục cả tháng, còn function chỉ được gọi vài lần. Phí hourly vẫn có thể xuất hiện trong thời gian NAT tồn tại. Vì vậy, hãy so sánh:

- NAT luôn chạy và sẵn sàng cho burst.
- NAT theo môi trường hoặc theo region.
- Private endpoint cho destination được gọi thường xuyên.
- Kiến trúc dùng queue để gom và điều tiết outbound.
- Egress proxy hoặc shared NAT phục vụ nhiều workload.

Shared NAT có thể giảm số tài nguyên hourly nhưng làm tăng mức phụ thuộc, độ phức tạp phân bổ chi phí, rủi ro capacity và blast radius. Cần cân nhắc chi phí cùng availability và isolation.

## 3. Chi phí truyền dữ liệu

Data transfer thường được tính dựa trên nơi dữ liệu đi đến, loại network path, region, zone và loại dịch vụ. Không nên coi mọi byte truyền trong cloud đều miễn phí.

### 3.1. Những hướng truyền phổ biến

| Đường truyền | Ví dụ | Khoản phí có thể gặp |
|---|---|---|
| Ingress từ Internet | Client upload file vào function | Có thể miễn phí ở lớp network, nhưng vẫn có phí request/compute/storage |
| Egress ra Internet | Function trả file hoặc gọi API public | Internet data transfer out |
| Same-zone | Function và database cùng zone | Thường thấp hoặc miễn phí theo một số path, cần kiểm tra |
| Cross-zone | Function zone A gọi database zone B | Inter-zone data transfer |
| Cross-region | Function region A gọi service region B | Inter-region transfer ở một hoặc nhiều đầu |
| Cloud-to-cloud | Function gọi SaaS hoặc cloud khác | Egress của cloud nguồn và phí của bên nhận nếu có |
| Hybrid network | Function gọi data center qua VPN/Interconnect | Port/hour, tunnel, data processing và transfer |

Provider có thể áp dụng giá khác nhau cho cùng một cặp region, loại dịch vụ hoặc loại network path. Luôn kiểm tra bảng giá cụ thể thay vì dùng một mức giá chung cho mọi loại traffic.

### 3.2. Ingress và egress

Ingress là dữ liệu đi vào cloud; egress là dữ liệu rời khỏi cloud hoặc dịch vụ theo định nghĩa billing của provider. Nhiều cloud có chính sách miễn hoặc ưu đãi cho một số loại ingress, nhưng vẫn tính egress và các phí xử lý ở đường đi.

Ví dụ, function nhận request 1 KB nhưng tải về file 100 MB từ một API public rồi gửi file 100 MB cho client. Lượng data transfer có thể lớn hơn rất nhiều so với payload request ban đầu. Hãy đo byte thực tế theo chiều đi và chiều về.

### 3.3. Cross-zone transfer

Function và database ở hai zone khác nhau có thể cần truyền dữ liệu qua network backbone. Một số provider tính phí cross-zone theo GB, kể cả khi traffic không rời region. Việc triển khai multi-zone tăng availability nhưng có thể làm phát sinh transfer khi request đi chéo zone.

Không nên ép mọi workload vào một zone chỉ để giảm phí. Làm vậy có thể giảm availability và tạo rủi ro mất dịch vụ khi zone gặp sự cố. Hãy so sánh chi phí cross-zone với lợi ích resilience và kiểm tra xem có thể đặt function, cache và database theo topology hợp lý hơn không.

### 3.4. Cross-region transfer

Gọi API hoặc database ở region khác có thể phát sinh:

- Data transfer giữa hai region.
- Phí request hoặc compute tại region đích.
- Phí NAT/egress nếu đường đi sử dụng NAT.
- Phí replication hoặc inter-region peering.
- Latency tăng khiến function chạy lâu hơn hoặc retry nhiều hơn.

Nếu function ở region A liên tục gọi database region B, chi phí không chỉ nằm ở lượng byte. Request nhỏ nhưng số lượng lớn vẫn có thể tạo chi phí request, connection, NAT hoặc gateway.

### 3.5. Request nhỏ vẫn có thể đắt

Một function gửi 1 KB cho API đối tác mỗi giây có lượng data thấp. Nhưng nếu mỗi invocation tạo kết nối TLS mới, gọi DNS, retry nhiều lần và đi qua NAT có phí hourly, chi phí mạng không tỷ lệ đơn giản với payload bytes.

Hãy đo cả:
- Số request và connection.
- Số lần handshake/reconnect.
- Byte gửi và nhận.
- Số lần retry.
- Thời gian function chờ network.
- Phí tài nguyên mạng cố định.

## 4. Chi phí gọi liên vùng và lựa chọn region

Vị trí function và vị trí downstream ảnh hưởng cả chi phí, latency, reliability và data residency.

### 4.1. Mô hình function và database khác region

~~~mermaid
flowchart LR
    A[Function Region A] --> B[Inter-region network]
    B --> C[Database Region B]
    A --> D[Logs Region A]
    C --> E[Backup Region B]
~~~

Ví dụ, API Gateway và Java function chạy ở một region gần người dùng, còn database đặt ở region khác để dùng chung với hệ thống cũ. Mỗi invocation có thể tạo nhiều round trip qua region boundary. Nếu function chạy nhiều query tuần tự, latency và data transfer cộng dồn.

### 4.2. Chi phí không chỉ tính trên response cuối

Một invocation có thể:
1. Đọc một bản ghi.
2. Gọi thêm ba query.
3. Gửi một event.
4. Retry một request do timeout.
5. Ghi audit log ở region khác.

Tổng lượng data transfer bằng tổng các luồng request/response, không phải chỉ kích thước response cuối cùng gửi cho client. Cần mô hình hóa fan-out và số round trip.

### 4.3. Chọn region theo tổng chi phí và yêu cầu nghiệp vụ

Khi chọn region, xem xét:

- Vị trí người dùng và latency mục tiêu.
- Vị trí database và các dependency chính.
- Phí inter-region và Internet egress.
- Availability Zone và disaster recovery.
- Data residency, compliance và yêu cầu lưu trữ.
- Giá compute, storage, NAT, endpoint và network.
- Dịch vụ serverless có sẵn ở region đó hay không.

Đặt function gần client có thể giảm latency cho client nhưng tăng chi phí nếu database ở xa. Đặt function gần database có thể giảm inter-region transfer nhưng làm người dùng xa hơn. Cần đo workload thực tế và xác định ưu tiên.

## 5. Private endpoint so với NAT: so sánh chi phí

Private endpoint có thể tránh một số đường Internet/NAT nhưng thường có phí endpoint hoặc data processing riêng. Không mặc định private endpoint luôn rẻ hơn NAT.

### 5.1. AWS Gateway endpoint và Interface endpoint

- Gateway endpoint cho một số dịch vụ như S3 và DynamoDB được thêm vào route table và không có phí hourly/data processing endpoint theo cách tính của interface endpoint; vẫn cần tính request/service charge và data transfer áp dụng cho service.
- Interface endpoint sử dụng PrivateLink, thường có phí theo giờ cho mỗi AZ endpoint và phí xử lý dữ liệu. Đổi lại, traffic đến service có thể đi qua private IP thay vì NAT/Internet.
- PrivateLink service, cross-AZ path và endpoint data processing cần kiểm tra theo bảng giá hiện hành.

Ví dụ, function thường xuyên đọc object từ S3: gateway endpoint có thể loại bỏ NAT processing cho đường S3 trong kiến trúc phù hợp. Nếu function gọi Secrets Manager qua interface endpoint, cần so sánh phí endpoint theo AZ và GB với NAT processing cùng các khoản transfer khác.

### 5.2. Google Cloud Private Google Access và Private Service Connect

Private Google Access cho phép một số workload không có external IP truy cập Google APIs/services được hỗ trợ. Private Service Connect tạo endpoint private cho các dịch vụ được hỗ trợ. Cấu hình DNS, endpoint, forwarding rule và region có thể ảnh hưởng chi phí.

So sánh:
- Cloud NAT gateway/data processing và public IP.
- PSC endpoint hoặc resource charge theo SKU.
- Data transfer đến dịch vụ đích.
- Cloud Run VPC connector nếu có.
- Lợi ích về bảo mật, route và vận hành.

Không phải mọi Google API đều dùng cùng một kiểu private access. Xác định đúng API, hostname và cấu hình endpoint trước khi tính giá.

### 5.3. Azure Private Endpoint

Azure Private Endpoint có thể phát sinh phí theo endpoint/giờ và data processed theo bảng giá hiện hành. Nếu dùng nhiều private endpoint, chi phí endpoint có thể tăng theo số service và subnet/region. Tuy vậy, private endpoint có thể giảm phụ thuộc NAT, firewall hoặc public exposure.

So sánh tổng chi phí:
- NAT Gateway hourly và data processed.
- Public IP.
- Azure Firewall/proxy nếu có.
- Private Endpoint hourly/data processing.
- VNet peering và data transfer.
- Request charge của dịch vụ đích.

### 5.4. Khi nào endpoint private đáng cân nhắc?

- Function gọi một managed service thường xuyên và có volume lớn.
- Chính sách yêu cầu traffic không đi qua public Internet.
- Muốn tránh NAT processing cho một nhóm destination.
- Muốn kiểm soát network path và DNS rõ hơn.
- Private endpoint có giá hợp lý so với NAT/proxy hiện tại.

Khi traffic rất thấp, phí hourly của interface endpoint có thể cao hơn NAT data processing tiết kiệm được. Khi traffic cao, phí data processing NAT có thể vượt chi phí endpoint. Hãy so sánh theo volume thực tế và số AZ/endpoint cần triển khai.

## 6. Chi phí mạng hybrid và kết nối đến data center

Một serverless function có thể cần gọi hệ thống chạy trong data center hoặc private cloud. Đường kết nối thường đi qua VPN, Direct Connect, Cloud Interconnect, ExpressRoute, transit gateway hoặc firewall tập trung.

### 6.1. Các khoản phí cần tính

| Thành phần | Cách tính có thể gặp |
|---|---|
| VPN gateway/tunnel | Theo giờ, theo gateway hoặc theo tunnel |
| Dedicated connectivity port | Theo giờ hoặc dung lượng cổng |
| Data transfer | Theo GB đi qua đường kết nối hoặc theo hướng egress |
| Transit gateway/hub | Phí attachment, giờ và data processing |
| Firewall/proxy | Phí tài nguyên, throughput hoặc GB xử lý |
| Cross-region path | Phí transfer giữa region trước khi đến mạng hybrid |
| Data center circuit | Phí nhà mạng/đường truyền riêng theo hợp đồng |

VPN managed thường có thể rẻ hơn dedicated circuit ở mức khởi đầu, nhưng throughput, latency và độ ổn định khác nhau. Dedicated connectivity có thể có phí port cố định và phí nhà mạng; không nên so sánh chỉ bằng đơn giá GB.

### 6.2. Đường đi có thể qua nhiều lớp

~~~mermaid
flowchart LR
    A[Serverless function] --> B[VPC / VNet]
    B --> C[Transit gateway or hub]
    C --> D[VPN / Direct Connect / Interconnect]
    D --> E[Corporate firewall]
    E --> F[Data center API]
~~~

Nếu function ở region khác với gateway hoặc hub, traffic có thể phát sinh inter-region transfer trước khi đi qua đường hybrid. Hãy vẽ toàn bộ route thay vì chỉ tính phí VPN.

### 6.3. Khi nào cần private circuit?

Private circuit phù hợp khi có yêu cầu throughput lớn, latency ổn định, kết nối hybrid lâu dài hoặc quy định mạng nghiêm ngặt. Với traffic thấp, VPN có thể kinh tế hơn. Quyết định cần tính cả:

- Phí port/circuit cố định.
- Phí data processing và transfer.
- Redundancy circuit ở nhiều vị trí.
- Chi phí router, firewall và vận hành.
- SLA, latency và thời gian khôi phục.
- Lượng traffic trung bình và burst.

## 7. Xây dựng mô hình ước tính chi phí

Ước tính chi phí mạng cần một mô hình đơn giản nhưng minh bạch. Trước tiên đo lượng traffic và thời gian tồn tại của tài nguyên, sau đó nhân với đơn giá từ bảng giá hiện hành.

### 7.1. Công thức tổng quát

Có thể mô hình hóa chi phí tháng:

\[
C_{\text{network}} =
C_{\text{NAT-hour}} +
C_{\text{NAT-data}} +
C_{\text{IP}} +
C_{\text{transfer}} +
C_{\text{endpoint}} +
C_{\text{hybrid}} +
C_{\text{logging}}
\]

Trong đó:

\[
C_{\text{NAT-hour}} = H_{\text{NAT}} \times P_{\text{NAT-hour}}
\]

\[
C_{\text{NAT-data}} = V_{\text{NAT}} \times P_{\text{NAT-GB}}
\]

\[
C_{\text{transfer}} = \sum_i V_i \times P_i
\]

- \(H_{\text{NAT}}\): số giờ NAT tồn tại trong kỳ.
- \(P_{\text{NAT-hour}}\): đơn giá NAT theo giờ.
- \(V_{\text{NAT}}\): lượng dữ liệu tính phí qua NAT.
- \(P_{\text{NAT-GB}}\): đơn giá xử lý dữ liệu NAT.
- \(V_i\): lượng dữ liệu thuộc loại transfer thứ \(i\).
- \(P_i\): đơn giá tương ứng của loại transfer đó.

Đây là mô hình khái niệm. Một provider có thể gộp hoặc tách các khoản khác nhau; một số transfer có tier miễn phí hoặc mức giá theo vùng. Không mặc định mọi traffic bị tính đồng thời ở tất cả các hạng mục.

### 7.2. Tính lượng dữ liệu từ request

Nếu biết số request, kích thước trung bình và số lần gọi:

\[
V_{\text{GB}} =
\frac{N \times S_{\text{bytes}}}{10^9}
\]

Với cách tính GB thập phân. Nếu bảng giá dùng GiB, chia cho \(2^{30}\) thay vì \(10^9\).

Cần cộng riêng chiều request và response:

\[
V_{\text{total}} =
V_{\text{request}} + V_{\text{response}} + V_{\text{retry}}
\]

Với request có fan-out, tính số lần gọi thực tế tới từng dependency. Nếu một invocation gọi ba API, không dùng số invocation làm số request dependency.

### 7.3. Ví dụ ước tính NAT và Internet egress

Giả sử một môi trường serverless có NAT chạy cả tháng và có các giả định minh họa sau:

| Biến | Giá trị giả định |
|---|---:|
| NAT hoạt động | 730 giờ |
| NAT hourly | 0,045 USD/giờ |
| NAT data processing | 0,045 USD/GB |
| Public IPv4 | 0,005 USD/giờ |
| Dữ liệu xử lý qua NAT | 500 GB |
| Internet egress tính phí | 200 GB |
| Internet egress đơn giá giả định | 0,09 USD/GB |

Các đơn giá ở đây chỉ dùng để minh họa phép tính, không phải báo giá hiện hành của AWS, Google Cloud hay Azure.

Tính từng dòng:

| Khoản phí | Phép tính | Chi phí giả định |
|---|---:|---:|
| NAT hourly | 730 × 0,045 | 32,85 USD |
| NAT data processing | 500 × 0,045 | 22,50 USD |
| Public IPv4 | 730 × 0,005 | 3,65 USD |
| Internet egress | 200 × 0,09 | 18,00 USD |
| **Tổng minh họa** | | **77,00 USD** |

Ví dụ này giả định 200 GB Internet egress nằm trong 500 GB NAT processed và cả hai SKU đều được tính riêng theo cấu trúc giá giả định. Trên cloud thực tế, cần kiểm tra cách provider định nghĩa byte được NAT xử lý, data transfer out, tier và trường hợp miễn phí để tránh tính trùng hoặc bỏ sót.

### 7.4. So sánh NAT và private endpoint bằng break-even

\[
C_{\text{NAT}} = H \times P_h + V \times P_n
\]

\[
C_{\text{endpoint}} = H \times A \times P_e + V \times P_d
\]

Trong đó:

- \(H\): số giờ trong kỳ.
- \(A\): số AZ có endpoint.
- \(P_h\): NAT hourly.
- \(P_n\): NAT data processing trên GB.
- \(P_e\): endpoint hourly trên AZ.
- \(P_d\): endpoint data processing trên GB.

Điểm hòa vốn khi hai tổng chi phí bằng nhau. Nếu endpoint có phí hourly lớn nhưng data processing thấp hơn, endpoint có thể phù hợp khi volume cao. Nếu volume thấp và endpoint phải tạo ở nhiều AZ, NAT có thể rẻ hơn. Cần cộng cả transfer, public IP, endpoint policy, resilience và chi phí vận hành.

Không so sánh một NAT dùng chung nhiều service với endpoint chỉ phục vụ một workload bằng toàn bộ phí NAT. Phân bổ đúng phần chi phí dùng chung trước khi kết luận.

### 7.5. Ví dụ cross-region

Giả sử function ở region A gọi database ở region B. Mỗi ngày có:

- 2 triệu request.
- Mỗi request gửi 2 KB.
- Mỗi response trả 8 KB.
- Retry trung bình 5% số request gốc.

Lượng dữ liệu request và response cơ bản:

\[
2.000.000 \times (2 + 8)\text{ KB}
= 20.000.000\text{ KB}
\]

Xấp xỉ 20 GB theo đơn vị thập phân, chưa tính protocol overhead. Nếu retry làm phát sinh thêm 5% request và response tương tự, volume có thể tăng khoảng 1 GB/ngày. Trong 30 ngày, đó là khoảng 630 GB tổng luồng dữ liệu theo giả định trên.

Số liệu chỉ minh họa cách tính. Cần xác định retry xảy ra ở chiều nào, payload có giống nhau không, response có được gửi lại không và provider tính phí ở từng hướng như thế nào.

## 8. Retry và latency cũng làm tăng chi phí

Retry có thể tạo ra nhiều loại chi phí cùng lúc:

- Thêm data processing qua NAT hoặc endpoint.
- Thêm data transfer nếu request/response đi qua region boundary.
- Thêm API request charge tại downstream.
- Tăng function duration do backoff và chờ network.
- Tăng log/trace ingestion.
- Tăng connection hoặc compute ở dịch vụ đích.

Một request timeout rồi retry không chỉ là thêm một HTTP call. Nó có thể giữ execution environment lâu hơn và tiêu thụ thêm compute. Với event-driven function, redelivery nhiều lần có thể làm cùng message được xử lý lặp và phát sinh phí compute, request hoặc queue operation.

### 8.1. Công thức cost per successful operation

Một chỉ số hữu ích:

\[
C_{\text{success}} =
\frac{C_{\text{compute}} + C_{\text{network}} + C_{\text{dependency}} + C_{\text{observability}}}
{N_{\text{successful operations}}}
\]

Nếu success rate giảm nhưng tổng chi phí vẫn tăng, cost per successful operation có thể tăng mạnh. Đây là chỉ số hữu ích hơn việc chỉ xem chi phí trên mỗi invocation.

### 8.2. Retry amplification trong hóa đơn

Giả sử 1 triệu operation thành công cần trung bình 1,1 attempt do retry 10%. Nếu mỗi attempt tạo 100 KB traffic qua NAT, volume là:

\[
1.000.000 \times 1,1 \times 100\text{ KB}
= 110\text{ GB}
\]

Nếu retry tăng từ 10% lên 50%, volume tăng lên 150 GB dù số operation nghiệp vụ không đổi. Theo dõi retry ratio giúp giải thích biến động chi phí mạng.

## 9. FinOps: gắn chi phí mạng với workload

Chi phí NAT và data transfer thường xuất hiện ở hóa đơn cấp account, subscription, project, region hoặc shared network. Nếu không có quy tắc phân bổ, team sử dụng function không biết workload nào tạo ra chi phí.

### 9.1. Phân bổ theo owner và workload

Nên gắn metadata cho tài nguyên có thể tag/label:

- `service` hoặc `application`.
- `team` hoặc `owner`.
- `environment` như dev, staging, production.
- `cost-center` hoặc product.
- `region` và network segment.
- `managed-by` hoặc repository.

Không phải mọi managed network resource đều hỗ trợ tag đầy đủ. Với NAT dùng chung, có thể phân bổ theo bytes, flow log, subnet, route table, endpoint hoặc tỷ lệ workload sử dụng.

### 9.2. Phân bổ chi phí shared NAT

Một NAT có thể phục vụ nhiều function và nhiều team. Một cách phân bổ là theo lượng byte:

\[
C_{\text{team}} =
C_{\text{shared}} \times
\frac{V_{\text{team}}}{V_{\text{all teams}}}
\]

Ví dụ, team A tạo 60% byte, team B tạo 30%, team C tạo 10%; shared NAT cost có thể được phân bổ theo các tỷ lệ đó. Nếu NAT hourly phục vụ cả ba team, phân bổ theo traffic là một lựa chọn, nhưng có thể cần kết hợp với baseline capacity hoặc số subnet để phản ánh mức sử dụng công bằng hơn.

Ghi rõ phương pháp allocation để tránh hiểu rằng số liệu chargeback là hóa đơn trực tiếp của provider. Allocation là quy tắc quản trị nội bộ.

### 9.3. Dùng billing export và network telemetry

Kết hợp:
- Cost and Usage Report hoặc billing export của provider.
- Resource tags/labels.
- NAT metrics và logs.
- VPC/VNet flow logs.
- Endpoint metrics.
- Application metrics về byte/request/retry.
- Trace để xác định service call gây volume lớn.

Billing export cho biết SKU và cost theo resource hoặc usage type; flow logs cho biết metadata network flow. Hai nguồn có thể khác độ trễ, granularity và cách nhóm. Cần map chúng qua account/project, region, resource ID, subnet, time window và owner.

### 9.4. Unit economics cho serverless

Theo dõi các chỉ số:

| Chỉ số | Câu hỏi |
|---|---|
| Network cost per invocation | Mỗi invocation tạo trung bình bao nhiêu phí mạng? |
| Network cost per successful operation | Một giao dịch thành công tiêu tốn bao nhiêu phí mạng? |
| Egress GB per 1.000 operations | Payload có tăng bất thường không? |
| Retry count per operation | Retry có làm tăng cost không? |
| NAT cost per team | Team nào sử dụng nhiều shared NAT? |
| Cross-region GB per service | Service nào gọi liên vùng thường xuyên? |
| Endpoint cost per GB | Private endpoint có hiệu quả theo volume không? |

Đừng tối ưu cost per invocation nếu điều đó làm giảm success rate hoặc tăng latency. Cost per successful operation kết hợp với SLO thường phản ánh trade-off tốt hơn.

## 10. Tối ưu chi phí NAT và data transfer

Tối ưu cần dựa trên traffic thực tế và kiến trúc. Không phải mọi traffic đều nên chuyển sang private endpoint, cũng không phải mọi NAT đều cần thay thế.

### 10.1. Đưa workload gần dependency

Nếu function và database thường xuyên gọi qua region boundary, cân nhắc đặt chúng cùng region hoặc dùng API/cache trung gian gần function. Lợi ích có thể gồm:

- Giảm inter-region data transfer.
- Giảm round trip và latency.
- Giảm thời gian function chờ network.
- Giảm khả năng timeout và retry.

Cần bảo đảm lựa chọn region đáp ứng data residency, availability, DR và yêu cầu người dùng.

### 10.2. Dùng private endpoint đúng chỗ

Nếu function gọi một managed service có volume lớn, private endpoint hoặc gateway endpoint có thể giảm traffic qua NAT. Nhưng phải so sánh phí endpoint hourly/data processing và số AZ.

Trên AWS, cân nhắc gateway endpoint cho S3/DynamoDB khi phù hợp; interface endpoint cho service được hỗ trợ. Trên Google Cloud, kiểm tra Private Google Access/PSC. Trên Azure, kiểm tra Private Endpoint. Không tạo endpoint cho service ít dùng nếu phí cố định lớn hơn phần NAT tiết kiệm được.

### 10.3. Giữ NAT path hợp lý theo zone

Nếu provider tính phí cross-zone, đặt NAT và workload theo topology phù hợp có thể giảm transfer. Trên AWS, nhiều kiến trúc tạo NAT Gateway theo AZ và route private subnet đến NAT cùng AZ để giảm cross-AZ dependency. Tuy nhiên, NAT theo từng AZ tăng phí hourly và cần quản lý IP. Cần so sánh chi phí với resilience và failure domain.

Không dùng một NAT duy nhất cho tất cả zone chỉ để tiết kiệm hourly nếu nó tạo single point of failure hoặc cross-zone traffic lớn.

### 10.4. Giảm số byte

- Chỉ trả những field client cần.
- Dùng pagination và giới hạn kích thước response.
- Nén payload khi client/server hỗ trợ và chi phí CPU hợp lý.
- Tránh tải file lớn qua function nếu có thể dùng object storage và signed URL.
- Dùng cache cho dữ liệu đọc lặp.
- Tránh serialize cùng payload nhiều lần giữa các service.
- Chọn định dạng dữ liệu phù hợp với use case.
- Dùng batch API khi giảm overhead mà không làm retry phạm vi quá lớn.

### 10.5. Giảm số request và connection

- Tái sử dụng HTTP client và connection pool.
- Dùng keep-alive phù hợp.
- Tránh DNS/TLS handshake mới cho mọi request nếu runtime cho phép reuse an toàn.
- Gộp các request nhỏ khi API hỗ trợ.
- Giảm fan-out tuần tự không cần thiết.
- Dùng bulk API hoặc query có giới hạn.
- Đặt timeout để không giữ connection vô thời hạn.

Tái sử dụng client trong execution environment có thể giảm handshake và connection churn. Tuy nhiên, không giữ connection vượt quá giới hạn của database hoặc không phù hợp với lifecycle serverless.

### 10.6. Kiểm soát retry và queue

Retry vô hạn vừa gây quá tải vừa tăng phí. Áp dụng:
- Retry budget theo request và dependency.
- Exponential backoff với jitter.
- Tôn trọng `Retry-After`.
- Idempotency cho side effect.
- Circuit breaker và concurrency limiter.
- Queue để điều tiết burst.
- DLQ và redrive có tốc độ giới hạn.

Đừng retry chỉ vì muốn giữ success rate tức thời. Một số request nên fail fast hoặc chuyển sang xử lý bất đồng bộ để tránh kéo dài invocation và chi phí.

### 10.7. Tránh đưa toàn bộ traffic qua NAT khi không cần

Một số cấu hình all-traffic qua VPC giúp áp dụng firewall tập trung, nhưng có thể khiến cả traffic đến destination không cần NAT đi qua cùng đường. Hãy phân loại:

- Private ranges cần đi vào VPC.
- Managed service có private endpoint.
- Public API cần NAT/static egress.
- Destination không được phép cần bị chặn.

Dùng route, endpoint và egress policy phù hợp. Bảo đảm traffic không bypass kiểm soát bảo mật chỉ vì mục tiêu giảm chi phí.

## 11. Đo lượng dữ liệu từ Java function

Cloud billing cho biết số liệu ở cấp network resource hoặc SKU. Application telemetry giúp hiểu request nào tạo ra volume. Hai nguồn nên được đối chiếu.

### 11.1. Đo payload bytes trong HTTP client

Ví dụ dưới đây đo số byte của body request và response ở lớp ứng dụng:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public final class PartnerApiClient {

    private final HttpClient client = HttpClient.newHttpClient();
    private final NetworkMetrics metrics;

    public PartnerApiClient(NetworkMetrics metrics) {
        this.metrics = metrics;
    }

    public byte[] fetch(URI uri, String requestId) throws Exception {
        byte[] requestBody = "{}".getBytes(StandardCharsets.UTF_8);

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofByteArray(requestBody))
                .build();

        long startedAt = System.nanoTime();
        HttpResponse<byte[]> response = client.send(
                request, HttpResponse.BodyHandlers.ofByteArray());

        long durationMs =
                (System.nanoTime() - startedAt) / 1_000_000;

        metrics.record(
                uri.getHost(),
                requestBody.length,
                response.body().length,
                response.statusCode(),
                durationMs,
                requestId);

        return response.body();
    }

    public interface NetworkMetrics {
        void record(
                String destination,
                long requestPayloadBytes,
                long responsePayloadBytes,
                int statusCode,
                long durationMs,
                String requestId);
    }
}
~~~

Đây là số byte payload ở lớp ứng dụng, không phải số byte billing chính xác. Nó không bao gồm đầy đủ TCP/IP, TLS, HTTP header, retransmission, framing hoặc cách provider đo data processing. Nếu dùng compression, cần xác định số byte được đo trước hay sau nén. Dùng flow logs, NAT metrics và billing export để đối chiếu.

Không ghi request body, token hoặc thông tin cá nhân chỉ để đo traffic. Ghi kích thước, destination đã chuẩn hóa, status, attempt và trace ID là đủ cho nhiều trường hợp.

### 11.2. Ghi nhận retry riêng

Mỗi request nên phân biệt:
- Operation gốc.
- Attempt đầu tiên.
- Retry attempt.
- Destination/dependency.
- Payload bytes.
- Response bytes.
- Status và error category.

Nếu chỉ đếm invocation, sẽ bỏ qua retry bên trong HTTP client hoặc SDK. Nếu retry nằm trong SDK, hãy dùng hook/interceptor phù hợp để quan sát attempt thật.

### 11.3. Đối chiếu với billing

Ứng dụng có thể ghi 100 GB payload nhưng billing ghi 112 GB data processed. Phần chênh lệch có thể đến từ protocol overhead, response, retransmission, traffic khác cùng NAT hoặc cách provider tính bytes. Ngược lại, billing có thể thấp hơn nếu traffic nội bộ không đi qua NAT.

Đối chiếu theo cùng:
- Khoảng thời gian.
- Region và zone.
- NAT/endpoint resource.
- Subnet hoặc workload.
- Destination/service.
- Đơn vị GB hay GiB.
- Chiều request/response và loại transfer.

## 12. Quy trình FinOps để phát hiện và xử lý chi phí bất thường

Một khoản phí mạng tăng bất thường có thể do traffic tăng thật, route thay đổi, retry storm, endpoint mới hoặc NAT được tạo lâu hơn dự kiến. Không nên chỉ nhìn tổng hóa đơn rồi giảm capacity ngay.

### 12.1. Quy trình điều tra

1. Xác định SKU hoặc usage type tăng trong billing export.
2. Xác định resource ID, region và khoảng thời gian phát sinh.
3. Kiểm tra NAT hourly, NAT data processing, public IP và data transfer out riêng.
4. Đối chiếu flow logs và NAT metrics để tìm subnet/destination tạo volume.
5. Đối chiếu application metrics về request count, payload bytes, retry ratio và latency.
6. Kiểm tra thay đổi route, VPC connector, endpoint, region placement hoặc deployment.
7. Ước tính phần tăng do traffic, phần do đơn giá/tier và phần do tài nguyên chạy lâu.
8. Đề xuất thay đổi, đo lại cost per successful operation và xác nhận SLO không suy giảm.

### 12.2. Budget và alert

Có thể đặt alert theo:
- Tổng network cost theo service/team.
- NAT data processing tăng theo ngày hoặc tuần.
- Data transfer out vượt forecast.
- Inter-region transfer tăng bất thường.
- Endpoint hourly cost tăng do thêm AZ hoặc endpoint.
- Network cost per successful operation vượt mục tiêu.
- Retry ratio hoặc queue redelivery tăng cùng lúc với network cost.

Alert nên có owner, ngưỡng, thời gian cửa sổ và hướng điều tra. Một ngày có traffic cao do batch job có thể là expected; so sánh với lịch chạy và business volume trước khi mở incident.

### 12.3. Forecast và anomaly

Forecast nên dựa trên driver của workload:
- Số operation nghiệp vụ.
- Payload trung bình.
- Fan-out mỗi operation.
- Retry ratio.
- Số giờ NAT/endpoint tồn tại.
- Tốc độ tăng user và traffic.
- Tỷ lệ traffic cross-region.

Dùng baseline theo ngày trong tuần hoặc mùa vụ nếu workload có pattern. Phân biệt thay đổi đơn giá với thay đổi lượng sử dụng. Anomaly detection cần biết các lần release, batch và failover để giảm false positive.

## 13. So sánh các lựa chọn kiến trúc theo chi phí

Không có lựa chọn rẻ nhất cho mọi workload. Hãy so sánh toàn bộ chi phí và yêu cầu vận hành.

| Lựa chọn | Chi phí có thể phát sinh | Điểm mạnh | Điểm cần cân nhắc |
|---|---|---|---|
| NAT Gateway | Hourly, data processing, public IP, egress | Dễ cung cấp outbound Internet và static IP | Có phí cố định; không tự lọc domain |
| Private endpoint | Endpoint hourly/data processing, service transfer | Private path, giảm public exposure | Nhiều endpoint/AZ có thể tăng phí cố định |
| Gateway endpoint | Có thể không có hourly/processing endpoint fee với dịch vụ được hỗ trợ | Hiệu quả cho một số object/key-value services | Hạn chế loại dịch vụ; vẫn có service/request charges |
| Shared egress proxy | Compute, license, throughput, logging, NAT | Domain policy và audit tập trung | HA, capacity và vận hành phức tạp |
| Direct public egress | Data transfer và IP/egress theo provider | Ít lớp hạ tầng | Có thể không đáp ứng static IP hoặc policy |
| VPN/hybrid | Gateway/tunnel, data processing, transfer | Kết nối private với data center | Latency và throughput phụ thuộc đường kết nối |
| Dedicated connectivity | Port/circuit, provider, transfer | Throughput và SLA tốt hơn trong use case phù hợp | Phí cố định và thời gian triển khai |

### 13.1. Ba kịch bản quyết định

**Kịch bản A: traffic rất thấp, chỉ gọi một API public.** NAT có phí hourly có thể chiếm phần lớn hóa đơn. Cân nhắc dùng egress path được provider hỗ trợ, chia sẻ NAT có kiểm soát hoặc kiến trúc phù hợp với yêu cầu static IP và bảo mật. Không bỏ NAT nếu policy bắt buộc static egress.

**Kịch bản B: traffic lớn đến một managed service.** So sánh NAT data processing với private/gateway endpoint. Nếu endpoint hourly được chia sẻ nhiều workload và data processing thấp hơn, endpoint có thể tiết kiệm. Cần tính số AZ và chi phí transfer.

**Kịch bản C: function gọi database ở region khác hàng triệu lần.** Giảm round trip và đặt function gần database có thể tiết kiệm transfer, giảm latency và giảm compute do chờ. Tuy nhiên, phải kiểm tra data residency, DR và trải nghiệm người dùng trước khi chuyển region.

### 13.2. Đánh giá tổng chi phí sở hữu

Khi so sánh hai kiến trúc, cộng:
- Phí network resource.
- Data transfer.
- Endpoint và public IP.
- Compute của function, connector, proxy và firewall.
- Request/operation của managed service.
- Log, trace và monitoring.
- Chi phí vận hành, support và incident.
- Rủi ro availability và thời gian phục hồi.

Một giải pháp rẻ hơn trên dòng NAT có thể đắt hơn nếu phải vận hành proxy riêng hoặc tăng latency làm function chạy lâu hơn.

## 14. Checklist trước khi triển khai production

- [ ] Đã vẽ đường đi từ function đến từng dependency.
- [ ] Đã ghi region, zone, subnet và loại network path.
- [ ] Đã phân biệt ingress, egress, same-zone, cross-zone, cross-region và Internet.
- [ ] Đã ước tính số giờ NAT/endpoint tồn tại.
- [ ] Đã đo hoặc ước tính byte request và response.
- [ ] Đã tính retry, fan-out và batch vào volume.
- [ ] Đã xác định phí public IP, NAT processing và data transfer riêng.
- [ ] Đã so sánh NAT với gateway/interface/private endpoint.
- [ ] Đã tính chi phí connector, proxy, firewall, VPN hoặc dedicated circuit nếu có.
- [ ] Đã kiểm tra pricing theo region, SKU, tier và đơn vị GB/GiB.
- [ ] Đã kiểm tra traffic có bị tính cross-AZ hoặc inter-region không.
- [ ] Đã gắn tag/label và owner cho network resource hỗ trợ.
- [ ] Đã có quy tắc phân bổ chi phí shared NAT/egress.
- [ ] Đã xuất billing data và đối chiếu với flow log/NAT metric.
- [ ] Đã theo dõi cost per successful operation.
- [ ] Đã đặt budget, forecast và alert cho chi phí mạng.
- [ ] Đã kiểm tra retry storm và behavior khi downstream throttling.
- [ ] Đã xác nhận tối ưu chi phí không làm giảm security, availability hoặc SLO.

## 15. Tự kiểm tra

**Câu 1.** Vì sao NAT Gateway có thể tạo chi phí ngay cả khi function không được gọi?

**Gợi ý trả lời:** NAT Gateway là tài nguyên mạng tồn tại độc lập với invocation. Nếu provider tính phí theo giờ provision, khoản hourly vẫn phát sinh trong thời gian tài nguyên tồn tại.

**Câu 2.** NAT data processing và Internet data transfer out có giống nhau không?

**Gợi ý trả lời:** Không. NAT data processing là phí xử lý traffic qua NAT; Internet data transfer out là phí dữ liệu rời cloud theo quy tắc billing. Một luồng traffic có thể liên quan đến nhiều SKU, nhưng phải kiểm tra cách provider tính để tránh cộng trùng.

**Câu 3.** Khi nào private endpoint có thể rẻ hơn NAT?

**Gợi ý trả lời:** Khi volume đến một managed service đủ lớn để phần tiết kiệm NAT processing/egress lớn hơn phí endpoint theo giờ và data processing. Cần tính số AZ, endpoint và transfer.

**Câu 4.** Vì sao gọi database ở region khác có thể làm tăng nhiều loại chi phí?

**Gợi ý trả lời:** Có thể phát sinh inter-region data transfer, request/compute tại dịch vụ đích, NAT hoặc gateway nếu đường đi cần, và function chạy lâu hơn do latency hoặc retry.

**Câu 5.** Vì sao cost per successful operation có ý nghĩa hơn cost per invocation?

**Gợi ý trả lời:** Invocation có thể thất bại hoặc retry nhiều lần. Chia tổng chi phí cho operation thành công phản ánh lượng tiền thực tế để hoàn tất một kết quả nghiệp vụ.

**Bài tập tình huống:** Một nhóm triển khai Java function tại region A. Function gọi database private ở region A, object storage và API thanh toán public. NAT Gateway chạy liên tục, có hai AZ. Tháng này phí NAT processing và data transfer tăng 70%, trong khi số invocation chỉ tăng 10%. Hãy lập kế hoạch điều tra. Xác định số liệu cần lấy từ billing export, flow logs, NAT metrics và application metrics; so sánh gateway endpoint/private endpoint, vị trí NAT, retry ratio và payload. Đề xuất cách phân bổ chi phí cho các team dùng chung NAT.

**Gợi ý:** Tách SKU hourly, data processing, public IP, cross-AZ và Internet egress. Kiểm tra route của object storage; nếu có gateway endpoint phù hợp, traffic có thể không cần qua NAT. Kiểm tra destination và byte theo subnet để tìm function hoặc API tạo volume. Đo request/response payload, fan-out và retry ratio; kiểm tra release gần thời điểm tăng phí. So sánh phí endpoint theo AZ với phần NAT tiết kiệm được. Phân bổ shared NAT theo bytes hoặc usage driver đã thống nhất, đồng thời ghi rõ phần hourly baseline.

## Kết luận

Chi phí mạng serverless không chỉ là phí data transfer. NAT có thể có phí hourly, data processing và public IP; private endpoint có thể có phí endpoint và dữ liệu; cross-zone, cross-region, Internet egress và hybrid path có quy tắc tính riêng. Retry, fan-out và latency làm tăng cả network usage lẫn compute và request charge. FinOps cần kết hợp billing export, flow logs, NAT metrics và application telemetry để gắn chi phí với workload. Tối ưu tốt bắt đầu từ việc hiểu đường đi của traffic, đo byte và retry thực tế, sau đó so sánh tổng chi phí với yêu cầu bảo mật, availability và latency.