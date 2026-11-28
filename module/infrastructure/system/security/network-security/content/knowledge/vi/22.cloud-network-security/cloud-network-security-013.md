# Flow log cho điều tra lưu lượng trong mạng cloud

## 1. Vì sao flow log quan trọng đối với cloud network security?

Trong hạ tầng cloud, một request có thể đi từ Internet qua CDN, load balancer, security group, NAT gateway, VPC/VNet peering, transit hub, firewall ảo rồi tới một VM, container hoặc dịch vụ private. Khi ứng dụng gặp lỗi kết nối, bị nghi dò quét hay có dấu hiệu dữ liệu bị đưa ra ngoài, người điều tra cần trả lời **ai kết nối tới đâu, ở thời điểm nào, qua giao thức/cổng gì, đi theo hướng nào và được thiết bị quan sát xử lý ra sao**.

**Network flow log** ghi nhận **metadata của luồng/giao tiếp mạng** tại một hoặc nhiều điểm của hạ tầng. Một bản ghi thường chứa địa chỉ IP, cổng nguồn/đích, giao thức, thời gian, số gói/byte và một số trường về hướng, interface, hành động hoặc trạng thái thu thập. Dữ liệu có thể được **tổng hợp theo khoảng thời gian, lấy mẫu hoặc biến đổi** tùy cloud provider và cấu hình.

Trong module **SECURITY_NETWORK_SECURITY**, flow logs là công cụ hỗ trợ **phân đoạn, firewall, VPN, IDS/IPS, phân tích lưu lượng, threat modeling, phát hiện xâm nhập, DNS security và cloud network architecture**. Chúng cung cấp bằng chứng hữu ích nhưng **không thay thế packet capture (PCAP), ứng dụng logs, identity logs hay audit sự kiện thay đổi cấu hình**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Đọc và chuẩn hóa bản ghi flow với **5-tuple, timestamps, direction, bytes/packets, action và log status**.
2. Phân biệt **flow log, firewall log, packet capture, DNS log, HTTP/application log và cloud control-plane audit**.
3. Hiểu **aggregation, sampling, độ trễ, thiếu bản ghi, NAT và thay đổi địa chỉ** khi phân tích.
4. Truy vết lưu lượng **hai chiều** qua subnet, instance NIC, load balancer, NAT, VPN và cloud peering.
5. Điều tra các trường hợp **kết nối bị chặn, truy cập ngoài vùng, port scan, exfiltration và route bất đối xứng** mà không suy diễn quá mức.
6. Bảo vệ pipeline thu thập, retention, IAM, logs có IP nhạy cảm và tính toàn vẹn bằng chứng.
7. Thực hiện một lab **phân tích flow logs tổng hợp hoàn toàn offline** và xây dựng checklist/ma trận kiểm thử phục vụ SOC.

## 2. Flow log là gì và không phải là gì?

Hãy hình dung một luồng TCP từ máy client tới server:

~~~text
Client 10.10.1.25:51320
  -> Server 10.20.2.15:443 / TCP

Trên một điểm quan sát có thể ghi:
  source IP, destination IP, source port, destination port,
  protocol, interface, start/end, packet count, byte count,
  direction và disposition/status theo nguồn log.
~~~

Một **flow record** không nhất thiết tương đương **một kết nối TCP từ SYN đến FIN**. Nhà cung cấp có thể chia cùng giao tiếp thành nhiều bản ghi theo **aggregation interval**, thay đổi route, interface, timeout hoặc loại traffic. Với **UDP**, khái niệm flow thường được suy ra từ bộ trường giao tiếp và timeout, chứ không có TCP handshake.

| Nguồn bằng chứng | Thường thấy được | Điều không mặc nhiên có |
| --- | --- | --- |
| **VPC/VNet network flow log** | IP/port/protocol/time, counts, direction/action theo nền tảng | HTTP URI, SQL, token, đầy đủ TCP flags/payload |
| **Firewall/NGFW log** | Rule/zone, ALLOW/DENY, threat signature, NAT/session theo sản phẩm | Mọi packet đã đi qua bên ngoài firewall |
| **Packet capture (PCAP)** | Headers và payload còn quan sát được tại interface, thứ tự packets | Traffic không đi qua điểm capture; plaintext của TLS/IPsec |
| **DNS resolver log** | Truy vấn/tên miền, loại record, response theo resolver | Mọi kết nối IP và nội dung HTTPS |
| **L7 proxy/WAF log** | Host/path, method, status, policy, client identity theo cấu hình | Mọi TCP/UDP flow không qua proxy |
| **Application / database log** | User/action/resource/error theo ứng dụng | Đường đi mạng hoặc packets đã bị chặn trước ứng dụng |
| **Cloud audit/control-plane log** | Ai sửa route, security group, IAM, load balancer, logging | Packet đã đi qua hay ứng dụng đã trả lời thành công |

**Flow log là quan sát ở một điểm và với một mô hình thu thập cụ thể.** Nó **không phải bản sao toàn bộ traffic**. Nếu log ghi ACCEPT, không thể kết luận người dùng đã đăng nhập thành công; nếu không có dòng log, cũng không thể kết luận không có packet.

### 2.1. Những câu hỏi flow log giúp trả lời tốt

- Có traffic từ IP nguồn X đến IP đích Y trên cổng Z **được quan sát** trong khoảng thời gian T không?
- Những **subnet, interface, nguồn mạng, ứng dụng hoặc hướng** nào có mẫu traffic bất thường?
- Có bao nhiêu flows/bytes/packets theo những bản ghi đã thu, từ nhóm nào tới nhóm nào?
- Hành động **ACCEPT/REJECT** theo semantics của nguồn log là gì và thay đổi trước/sau một cấu hình?
- Lưu lượng outbound tăng ở một VM hoặc private endpoint cụ thể trước thời điểm cảnh báo?
- Có hướng trả lời tương ứng, hay chỉ thấy một phía tại điểm quan sát?

### 2.2. Những câu hỏi cần bằng chứng khác

- “Ai đã đăng nhập bằng tài khoản nào?” — cần authentication/identity/application logs.
- “Request HTTP gọi /admin và chứa dữ liệu gì?” — cần proxy/app logs hoặc capture ở vị trí hợp pháp có khả năng giải mã.
- “Tại sao security group này bị thay?” — cần cloud audit, change record và review.
- “Gói đã đến application process chưa?” — cần đối chiếu host firewall, socket/app telemetry và packet path.
- “Có tấn công chắc chắn không?” — cần correlation, phân biệt hoạt động quản trị/test hợp lệ, false positive.

## 3. Mô hình flow: 5-tuple và các trường mở rộng

Một bộ **5-tuple** phổ biến là:

\[
(\text{source IP},\ \text{source port},\ \text{destination IP},\ \text{destination port},\ \text{IP protocol})
\]

Ví dụ:

~~~text
Source IP:       10.10.1.25
Source port:     51320
Destination IP:  10.20.2.15
Destination port: 443
IP protocol:     TCP (protocol number 6)
~~~

Các protocol numbers phổ biến: **TCP = 6**, **UDP = 17**, **ICMPv4 = 1**, **ICMPv6 = 58**. Với những protocol **không có TCP/UDP ports**, trường source/destination port có thể **không áp dụng hoặc mang giá trị thay thế**, tùy log format. Không diễn giải port 0, -1 hoặc null của ICMP như một dịch vụ ứng dụng.

### 3.1. Các trường phải bổ sung để điều tra đúng

| Nhóm | Trường ví dụ | Ý nghĩa |
| --- | --- | --- |
| Time | start, end, ingestion time, aggregation interval | Phân biệt lúc traffic xảy ra với lúc log tới hệ phân tích |
| Location | account/subscription/project, region/zone, VPC/VNet, subnet, interface ID | Tìm điểm quan sát và chủ sở hữu tài sản |
| Address | src/dst, pre/post NAT fields nếu provider có, IP family | Xác định host trước/sau dịch địa chỉ |
| Service | protocol, src/dst port, service tag/route/endpoint metadata nếu có | Gắn với app/service ở mức metadata |
| Direction | ingress/egress hoặc flow direction theo định nghĩa nguồn | Hướng nhìn tại một interface, không mặc định tương đương request/response |
| Volume | packets, bytes, sampling multiplier nếu được định nghĩa | Mức lưu lượng quan sát, có thể đã tổng hợp/lấy mẫu |
| Action | accept/reject/allow/deny theo semantics nguồn | Tín hiệu chính sách của **điểm log**, không phải kết luận end-to-end |
| Quality | log status, skip reason, sampling mode, delivered/failed | Biết bản ghi có đáng dùng cho định lượng hay không |
| Context | VM/Pod identity, security group, LB/NAT resource ID được enrichment | Hỗ trợ attribution nhưng cần thời điểm đúng |

### 3.2. Vì sao 5-tuple chưa đủ làm khóa duy nhất?

Một cặp IP/port có thể **được tái sử dụng** sau một thời gian; IP của VM/Pod có thể đổi chủ; NAT có thể chia sẻ public address cho nhiều private hosts. Cùng 5-tuple cũng xuất hiện ở nhiều **VPC, tenant, tài khoản hoặc time windows**. Để tránh gộp nhầm, hãy xét ít nhất:

~~~text
cloud_account/project
VPC/VNet + resource/interface ID
time window + log source + IP family
direction
5-tuple
NAT/LB mapping và identity enrichment khi có
~~~

Với **VPC peering, Transit Gateway, shared VPC, service mesh và multi-account**, log ở hai điểm có thể mô tả cùng một kết nối nhưng khác địa chỉ/interface và số byte.

## 4. Điểm quan sát, pipeline và phạm vi bao phủ

~~~mermaid
flowchart LR
    C["Client / Pod / VM"] --> N["NIC / VPC fabric"]
    N --> G["Firewall / NAT / LB / Transit"]
    G --> S["Private service / Internet"]
    N -. "Flow metadata" .-> L["Cloud flow log collector"]
    G -. "Gateway-specific telemetry" .-> L
    L --> Q["Log sink: object storage / logs service"]
    Q --> E["Normalize / enrich / quality checks"]
    E --> A["SIEM / query / incident timeline"]
~~~

**Không phải mọi cloud fabric đều ghi log chính xác tại cùng điểm.** Có dịch vụ thu ở **VM NIC**, có chức năng ở **VPC/subnet/network**, hoặc logs riêng cho **firewall, NAT, private endpoint, load balancer**. Các phạm vi này không tự thay thế nhau. Thiết kế collection phải dựa vào **mô hình điểm quan sát và khả năng của provider**, không dùng tên chung “VPC Flow Logs” để suy ra bao phủ toàn mạng.

### 4.1. Bốn thời điểm khác nhau

1. **Event/packet time:** Lúc traffic thực sự xuất hiện tại điểm quan sát.
2. **Flow aggregation time:** Khoảng thời gian collector nhóm packets vào record.
3. **Delivery/ingestion time:** Lúc record được chuyển tới log sink và có thể query.
4. **Detection/alert time:** Lúc SIEM phát hiện mẫu và tạo cảnh báo.

Vì thế, một alert nhận lúc **10:15 UTC** có thể bắt nguồn từ traffic xảy ra **10:08–10:10 UTC**. Đừng so các mốc chỉ theo ingestion timestamp và kết luận “route thay đổi sau traffic”; phải kiểm tra **thời gian sự kiện, timezone UTC, độ trễ pipeline và clock synchronization**.

### 4.2. Aggregation, sampling và log gaps

- **Aggregation:** nhiều packets trong một khoảng được tổng hợp; có thể có nhiều records cho cùng 5-tuple.
- **Sampling:** một số implementations chỉ xem/ghi một phần traffic; có thể không phù hợp suy ra số kết nối chính xác.
- **Skip/dropped records:** tài nguyên thu thập hoặc pipeline có thể bỏ một số records; provider có thể ghi log status.
- **Filtering:** chỉ thu **ACCEPT**, **REJECT** hoặc một phạm vi; thiếu các nhóm khác là do cấu hình.
- **Delivery latency:** log có thể chậm; alert real-time cần đánh giá giới hạn trễ, không coi flow logs luôn tức thời.
- **Lifecycle:** VM/Pod/interface bị xóa, IAM đổi hoặc collector ngừng hoạt động có thể tạo **vùng mù theo thời gian**.

**Số byte trong flow logs không luôn là lượng payload thực tới ứng dụng.** Tùy nguồn, bytes có thể đại diện cho bytes của packets quan sát được, không đồng nghĩa file được tải thành công; retransmission, headers, sampling, encapsulation và NAT làm con số khác ở hai điểm.

## 5. Cấu trúc một bản ghi và cách đọc có điều kiện

Để học xuyên nền tảng, ta sử dụng **schema JSON giả định**, không phải bản sao nguyên văn của AWS, Azure hay Google Cloud:

~~~json
{
  "event_start": "2026-10-17T09:10:00Z",
  "event_end": "2026-10-17T09:10:59Z",
  "ingested_at": "2026-10-17T09:12:10Z",
  "cloud": "example-cloud",
  "account": "account-demo",
  "region": "region-a",
  "network_id": "vpc-demo",
  "interface_id": "nic-application-a",
  "direction": "egress",
  "src_ip": "10.10.1.25",
  "src_port": 51320,
  "dst_ip": "10.20.2.15",
  "dst_port": 443,
  "protocol": 6,
  "packets": 18,
  "bytes": 12240,
  "action": "ACCEPT",
  "log_status": "OK",
  "collection": "aggregated-example"
}
~~~

### 5.1. Diễn giải chính xác

Tại thời gian sự kiện, **điểm quan sát nic-application-a** ghi nhận những packets phù hợp với source/destination và TCP/443, được tổng hợp thành record 18 packets/12.240 bytes, direction egress và action ACCEPT theo semantics đã định nghĩa của nguồn.

**Chưa thể khẳng định:**

- Server đích đã nhận đủ packets hay ứng dụng trả HTTP 200.
- Đây là một phiên TCP hoàn chỉnh và không có retransmission.
- Người dùng nào thực hiện request và URL HTTPS nào được gọi.
- Tất cả traffic mạng đều đã được thu; log status OK chỉ là trạng thái theo collector.
- Dữ liệu không mã hóa, chứa payload độc hại hoặc đã bị rò rỉ.

### 5.2. Tách IP nguồn thực và IP quan sát

Flow ghi **IP tại điểm thu**. Khi qua **SNAT, DNAT, NAT gateway, load balancer, service mesh hoặc tunnel**, cùng kết nối có thể được ghi như những bộ địa chỉ khác nhau. Để xác định actor ban đầu cần **NAT translation records, resource IDs, LB logs hoặc connection metadata** nếu platform cung cấp; không chỉ tra cứu public IP rồi kết luận VM sở hữu IP đó là nguồn gốc duy nhất.

### 5.3. Cảnh giác với dữ liệu thiếu và giá trị giả

Nếu một trường như src_port không tồn tại, **không tự điền 0** rồi gộp thành port 0 thật. Nếu direction/action không được provider cung cấp, nên giữ **unknown/null**; nếu bytes sampled, ghi rõ sampled. Khi không rõ schema version, phải kiểm tra field mapping trước khi đưa rule detection vào production.

## 6. Direction ingress/egress và vì sao cần quan sát hai chiều

**Ingress** và **egress** phải được hiểu **tại điểm quan sát**, không mặc định là client request và server response. Một packet tới server thường là **ingress** trên NIC server nhưng có thể là **egress** trên NIC client. Chiều trả lời đảo ngược.

~~~mermaid
flowchart LR
    A["VM A 10.10.1.25"] -->|"egress A: TCP SYN"| N["Cloud network"]
    N -->|"ingress B: TCP SYN"| B["VM B 10.20.2.15"]
    B -->|"egress B: SYN-ACK"| N
    N -->|"ingress A: SYN-ACK"| A
~~~

| Điểm quan sát | Flow | Direction đối với điểm đó |
| --- | --- | --- |
| NIC A | 10.10.1.25:51320 → 10.20.2.15:443 | Egress |
| NIC B | 10.10.1.25:51320 → 10.20.2.15:443 | Ingress |
| NIC B | 10.20.2.15:443 → 10.10.1.25:51320 | Egress |
| NIC A | 10.20.2.15:443 → 10.10.1.25:51320 | Ingress |

**Bốn bản ghi không phải bốn kết nối.** Đó có thể là quan sát ở bốn vị trí/hướng cho cùng một kết nối. Không lấy tổng packets ở cả NIC A và NIC B rồi tuyên bố có gấp đôi traffic, vì có thể đã **đếm hai lần** trên những điểm khác nhau.

### 6.1. Reverse tuple và khoảng thời gian

Để tìm phản hồi cho một flow TCP, ta thử tra **reverse 5-tuple**:

~~~text
Forward: 10.10.1.25:51320 -> 10.20.2.15:443, TCP
Reverse: 10.20.2.15:443 -> 10.10.1.25:51320, TCP
~~~

Nhưng reverse tuple **chỉ là một tín hiệu đối chiếu**. Lý do có thể không khớp:

- Return packet đi qua **giao diện/sensor khác** hoặc không thuộc scope collection.
- Một chiều có **NAT/port translation** hoặc load balancer đổi source/destination.
- **Aggregation windows** không trùng (một chiều bắt đầu gần cuối phút).
- Provider **sampling** hoặc bỏ log records.
- UDP không có phản hồi bắt buộc; TCP chưa chắc có session hoàn chỉnh.
- Response nằm trong **flow dài** đã được tổng hợp với nhiều packets khác.

**Không có reverse record không đủ kết luận server không trả lời.** Hãy kiểm tra nơi thu thập, NAT mapping, firewall policy, route và ứng dụng.

## 7. ACCEPT, REJECT và lý do packet vẫn có thể mất

Một record có **action ACCEPT/ALLOW** thường nói rằng packet hoặc flow được chính sách của **thành phần đã tạo log** chấp nhận theo định nghĩa tương ứng. Nó không phải bằng chứng chắc rằng toàn bộ đường từ client đến ứng dụng đã hoạt động.

Ngược lại, **REJECT/DENY** là tín hiệu hữu ích về chính sách tại điểm đó, nhưng **không nhất thiết nêu chính xác firewall rule nào đã chặn**. Với một số nguồn, action có thể phản ánh đánh giá của network ACL/security group ở một mức cụ thể; với nguồn khác là policy của firewall chuyên dụng. Cần đọc semantics của log source.

### 7.1. Bảng suy luận

| Quan sát | Có thể suy ra | Chưa thể kết luận |
| --- | --- | --- |
| ACCEPT tới TCP/443 | Traffic được quan sát và chấp nhận tại điểm log | TLS handshake, HTTP success, backend health |
| REJECT tới TCP/22 | Chính sách tại điểm log từ chối traffic thuộc tuple | Có tấn công hoặc attacker đã bị chặn ở mọi đường |
| Không thấy record | Chưa có bằng chứng trong phạm vi query | Không có packet, không có scan, không có kết nối |
| ACCEPT egress, không thấy ingress đích | Có dấu traffic đi tại nguồn | Gói đã tới đích; đường giữa có thể drop hoặc logging thiếu |
| ACCEPT hai chiều | Có traffic hai hướng được quan sát theo phạm vi | Không đảm bảo transaction hợp lệ hoặc không mất gói |
| BYTES rất lớn | Khối lượng quan sát có vẻ cao | Đã có exfiltration dữ liệu nhạy cảm |
| Nhiều đích/cổng bị REJECT | Có mẫu bị từ chối ở các tuples | Scan trái phép chắc chắn; có thể là monitoring hay cấu hình lỗi |

### 7.2. “Flow log nói ACCEPT nhưng ứng dụng timeout”

Giả thuyết cần kiểm tra:

1. **Route** giữa điểm log và ứng dụng sai, next hop không reachable hoặc route blackhole.
2. **NAT state** không đúng, response về nhánh khác hoặc mapping hết hạn.
3. Firewall ở **hop khác** chặn hoặc IPS loại flow.
4. **Host firewall/process** không listen trên port đã cho.
5. **TLS, DNS, mTLS, application authorization** hoặc backend dependency lỗi.
6. **MTU/PMTUD** làm request lớn không qua được dù SYN/TCP nhỏ thành công.
7. **Timestamps và aggregation** khiến so nhầm flow khác hoặc instance đã đổi IP.

Flow log góp phần **thu hẹp vùng lỗi**, không thay thế chẩn đoán tầng ứng dụng.

### 7.3. Stateful và stateless controls

Cloud **security group** ở một số nền tảng là stateful và cho phép return traffic của kết nối được chấp nhận theo cơ chế state tracking. **Network ACL** ở những hệ thống có thể stateless, phải cho phép cả hai hướng/các port phù hợp. Đừng áp cấu hình cụ thể của một provider sang provider khác. Khi thấy REJECT trên return flow, hãy xác nhận **policy model**, ephemeral ports, NAT và anti-spoofing tại đúng nơi.

## 8. Ba hệ sinh thái cloud: AWS, Azure và Google Cloud

Khả năng flow logging **khác theo phiên bản dịch vụ, region, resource type và thời điểm triển khai**. Bảng này chỉ giúp chọn đúng **nguồn/điểm quan sát**, không thay cho tài liệu cấu hình của cloud provider hiện hành.

| Nền tảng | Nhóm chức năng thường gặp | Điểm cần đặc biệt chú ý |
| --- | --- | --- |
| **AWS** | VPC Flow Logs cho phạm vi VPC, subnet hoặc elastic network interface; destination logs service/object storage/streaming theo hỗ trợ | Chọn trường/record version, aggregation interval, ACCEPT/REJECT, log status và resource identity; traffic không ghi/skip theo giới hạn |
| **Azure** | Virtual Network Flow Logs và những logs khác ở Network Watcher/Firewall/gateway theo dịch vụ | Phân biệt luồng do **virtual network flow log** cung cấp với **NSG flow logs legacy**; kiểm tra migration/deprecation và schema cụ thể |
| **Google Cloud** | VPC Flow Logs ở các phạm vi được hỗ trợ; cấu hình sampling/aggregation/metadata | Sampling và aggregation ảnh hưởng định lượng; enrichment metadata theo cấu hình, logs query trong Logging/analytics |

**Azure NSG flow logs:** Đây là loại logging **legacy** trong lịch sử; với thiết kế mới hãy kiểm tra hướng dẫn hiện hành của Azure về **Virtual Network Flow Logs** và kế hoạch chuyển đổi, không mặc định tiếp tục triển khai legacy NSG logging. Không tự suy rằng hai schema có cùng trường/action/coverage.

### 8.1. AWS — quan sát theo VPC/subnet/ENI

Khi một instance có nhiều **ENIs**, việc chỉ bật collection trên một ENI có thể bỏ sót traffic ở ENI khác. Với NAT gateway, load balancer, VPC endpoint và transit connectivity, **source/dest address và resource associations** có thể thay đổi theo điểm log; không đánh đồng một dòng source IP với instance owner.

Các trường thường gặp trong định dạng AWS flow logs lịch sử gồm **account ID, interface ID, srcaddr/dstaddr, srcport/dstport, protocol, packets, bytes, start/end, action, log-status**; các field mở rộng phụ thuộc format/version và tùy chọn. **Không gán ý nghĩa tuyệt đối cho một field nếu chưa biết format**; một số traffic hoặc nguồn hệ thống không có record như bạn mong chờ.

### 8.2. Azure — VNet, network watcher và hạ tầng định tuyến

Cloud network của Azure có **VNet/subnet, NSG, Azure Firewall, routing/UDF, private endpoints, Application Gateway, load balancers và hybrid connectivity**. Khi điều tra cần chọn log sources theo **VNet flow, firewall rule logs, load balancer logs/metrics, Activity Log và resource-specific diagnostics**.

Một record ở VNet không chứng minh **mọi security decision** của một Azure Firewall chuyên dụng; muốn biết rule ID/action trên firewall cần **firewall-specific logs** nếu được bật và hỗ trợ. NSG flow logs và VNet flow logs có **khác biệt schema/lifecycle**, cần đọc đúng tài liệu của triển khai thực tế.

### 8.3. Google Cloud — sampling, metadata và VPC architecture

Ở Google Cloud, VPC flow logging có thể cung cấp metadata về **subnet/VPC, VM/instance và remote endpoint** tùy logging configuration và dữ liệu nguồn. Nhưng **sampling** là yếu tố cần kiểm soát khi phân tích **số kết nối, bytes hoặc thời điểm**. Một record có thể đại diện mẫu traffic đã qua aggregation; so giá trị với firewall logs hay packet capture cần hiểu **sampling fraction và expansion semantics** của provider.

Đối với **Shared VPC, peering, Private Service Connect, Cloud NAT, Cloud Load Balancing, Cloud VPN/Interconnect**, việc chọn điểm thu và liên kết resources là một bài toán riêng. Không suy log của subnet VM bao trùm mọi traffic qua một managed service hoặc mọi hop phía ngoài.

### 8.4. Một sơ đồ so sánh hành trình quan sát

~~~mermaid
flowchart TB
    X["Cloud VPC/VNet, subnet, NIC"] --> F["Network flow log"]
    N["NAT / load balancer / private endpoint"] --> G["Managed-service logs & metrics"]
    W["Cloud firewall / WAF"] --> H["Security rule & threat logs"]
    C["Cloud APIs / IAM / config changes"] --> A["Audit/control-plane logs"]
    F --> S["SIEM / forensic query"]
    G --> S
    H --> S
    A --> S
~~~

**Bài học:** Chọn **log source theo câu hỏi**. Nếu muốn tìm “rule nào chặn”, hãy ưu tiên logs có rule attribution. Nếu muốn nhận diện luồng IP/port trong mạng cloud, flow logs giúp tốt hơn. Nếu muốn biết **ai sửa firewall**, audit/control-plane logs mới là nguồn trọng tâm.

## 9. Thiết kế thu thập flow logs: scope, chi phí và độ tin cậy

### 9.1. Những quyết định trước khi bật

1. **Phạm vi:** Những accounts/projects/subscriptions, VPC/VNets, subnets, ENIs/NICs, environments nào bắt buộc có?
2. **Loại traffic:** ACCEPT, REJECT hay cả hai; ingress/egress; IPv4/IPv6; production và đường quản trị?
3. **Granularity:** Aggregation interval, sampling, metadata enrichment và hạn mức log service.
4. **Đích lưu:** Object storage, logs service, analytics warehouse hoặc streaming pipeline được hỗ trợ.
5. **Vùng dữ liệu:** Residency, cross-region delivery, quyền của collector và encryption/key management.
6. **Retention:** Online search window, archive, legal hold và delete lifecycle theo phân loại dữ liệu.
7. **Chất lượng:** Heartbeat/ingestion health, status skipped/dropped, end-to-end delivery lag, schema version.
8. **Chi phí:** Volume bytes, ingestion/egress/storage/index/query costs, giá trị security use cases.

### 9.2. Scope theo rủi ro

| Khu vực | Giá trị flow logs | Điều cần đặc biệt giám sát |
| --- | --- | --- |
| Internet-facing workloads | Phát hiện inbound attempts/egress anomalies | DDoS, ports, external IPs, WAF/LB context |
| Production database subnets | Truy vết east-west và access boundary | Ai kết nối DB, unexpected zone |
| Management/jump hosts | Giám sát đường quản trị | SSH/RDP/WinRM theo quyền và time |
| Kubernetes worker/Pod network | Phát hiện Pod egress/lateral movement | IP churn, CNI overlays, service NAT |
| Transit/VPN hybrid | Kiểm tra cross-site paths | Route, NAT, policy symmetry, traffic scope |
| Dev/Test | Baselines và phát hiện truy cập Prod | Không thu quá mức dữ liệu thử nghiệm nhạy cảm |
| Shared platform services | Correlate service-to-service | Metadata IP ownership theo thời điểm |

**Không có công thức “bật ở một subnet là đủ cho mọi phiên kết nối”.** Với môi trường critical, cần ma trận **luồng dự kiến và các điểm quan sát** để chứng minh coverage.

### 9.3. Cân bằng mức chi tiết và chi phí

Giảm sampling hoặc tổng hợp dài có thể bớt chi phí nhưng tăng **false negatives** với những luồng ngắn/hiếm. Thu mọi flow mọi nơi có thể đẩy chi phí lên cao và làm SIEM bị nhiễu. Nên phân tầng:

- **Bảo mật nhạy cảm:** cần coverage/retention theo risk và policy, theo khả năng provider.
- **Triage gần thời gian thực:** ưu tiên nguồn có latency phù hợp; có thể bổ sung firewall/IDS streaming logs.
- **Forensic/historical:** lưu records gốc bất biến theo policy, cùng schema version và đường dẫn truy vết.
- **Analytics tổng hợp:** materialized views, sampling-aware calculations; không xóa evidence gốc khi chưa hết retention.

### 9.4. IAM tối thiểu cho collector và người xem

Collector cần quyền **ghi vào đích được phê duyệt**, không mặc nhiên cần đọc mọi secrets hoặc sửa firewall. Analyst có quyền **truy vấn** theo environment/case, không có quyền sửa hoặc xóa logs gốc. Admin thay cấu hình collection phải được **audit riêng**. Cân nhắc encryption at rest/in transit, key rotation, multi-account sink và bảo vệ chống xóa/sửa trái quyền theo dịch vụ hỗ trợ.

## 10. Kiểm tra chất lượng pipeline trước khi dùng để điều tra

Chất lượng bằng chứng phụ thuộc việc log còn đầy đủ, đúng schema và liên kết đúng resources.

| Health signal | Điều cần xem | Rủi ro khi không giám sát |
| --- | --- | --- |
| Collection enabled coverage | Số VPC/subnet/NIC được bật theo inventory | Có resource mới không được thu |
| Collector status / skip count | Skipped/unsupported/failed logs nếu được cung cấp | Missing records dẫn đến false negatives |
| Ingestion latency | Median/p95/p99 sự chênh giữa event và ingest | Alert chậm, timeline xáo trộn |
| Volume baseline | Events/bytes theo network/env | Pipeline đứt bị nhầm là traffic giảm |
| Schema parsing errors | Unknown fields/protocol/action/version | Rule sai hoặc rơi records |
| Duplicate rate | Bản ghi trùng khi retry/replay log delivery | Thổi phồng counts |
| Timestamp quality | UTC normalization, start <= end, clock issues | Sai thứ tự sự kiện |
| Resource enrichment freshness | IP → instance/Pod mapping đúng timestamp | Attribution sai khi IP được tái sử dụng |
| Retention/access | Query window, lifecycle, IAM, KMS availability | Mất bằng chứng trước incident |
| Cross-region/account | Logs về tập trung đầy đủ theo policy | Vùng mù khi DR/failover |

### 10.1. Chất lượng dữ liệu không chỉ là “đã có record”

Một pipeline có thể tiếp tục ghi một số dòng nhưng **chỉ còn ACCEPT** vì cấu hình bị thay; analytics cho rằng số REJECT bằng 0. Vì thế cần monitor **record counts theo category**, đối soát cấu hình collection với inventory và kiểm tra **schema compatibility** sau khi đổi version log format.

### 10.2. Không dùng logs như nguồn định lượng tuyệt đối khi sampling

Nếu hệ thống lấy mẫu **một phần traffic**, số flow quan sát không thể được gọi là **tổng số kết nối thật**. Có những phương pháp ước lượng theo sampling probability ở một số sản phẩm, nhưng phải biết **định nghĩa mẫu, weight, aggregation, loại traffic và sai số**. Đừng đơn giản nhân một hệ số chung rồi coi độ chính xác là tuyệt đối.

## 11. NAT và load balancer: một giao tiếp, nhiều địa chỉ

**Network Address Translation (NAT)** và proxy/load balancer có thể thay **IP nguồn, IP đích, source port, destination port**, hoặc thiết lập một kết nối hoàn toàn mới. Một flow log trên VM, một log ở NAT gateway và access log của L7 proxy có thể chứa ba bộ địa chỉ khác nhau cho cùng một hành trình request.

### 11.1. Ví dụ SNAT outbound

~~~mermaid
flowchart LR
    VM["VM 10.10.1.25:51515"] --> NAT["NAT Gateway"]
    NAT -->|"198.51.100.25:61001 -> 203.0.113.40:443"| DST["External HTTPS service 203.0.113.40"]
~~~

~~~text
Trước NAT:
  10.10.1.25:51515 -> 203.0.113.40:443 TCP

Sau NAT (ví dụ ánh xạ minh họa):
  198.51.100.25:61001 -> 203.0.113.40:443 TCP

Trả về từ Internet:
  203.0.113.40:443 -> 198.51.100.25:61001 TCP

Sau reverse translation:
  203.0.113.40:443 -> 10.10.1.25:51515 TCP
~~~

**Địa chỉ 198.51.100.0/24 và 203.0.113.0/24 là dải ví dụ TEST-NET**, không phải đích thực để kết nối trong production.

Nếu chỉ thấy **public 198.51.100.25**, không thể kết luận VM 10.10.1.25 là tác nhân duy nhất: **nhiều VM có thể chia sẻ một NAT public IP**. Cần bản ghi **NAT translation theo thời gian/port** hoặc telemetry liên quan từ subnet/NIC, với timestamp đủ chi tiết, để quy về workload nguồn.

### 11.2. DNAT, L4 proxy và L7 reverse proxy

| Hình thức | Flow thay đổi như thế nào? | Cần tìm thêm log |
| --- | --- | --- |
| **DNAT** tới backend | Địa chỉ/cổng đích đổi thành backend | NAT translation/conntrack và return path |
| **SNAT** | Địa chỉ/cổng nguồn bị thay | NAT gateway/egress mapping |
| **L4 full proxy** | Client↔LB và LB↔backend là hai kết nối khác | Connection ID, client IP metadata từ trusted proxy |
| **L7 reverse proxy** | HTTP request qua một TLS connection ở frontend và kết nối upstream khác | Request ID, upstream name, Host/path, auth/WAF decision |
| **DSR** | LB phân phối inbound, backend trả trực tiếp theo kiến trúc | Return route, backend/VIP và firewall state |
| **Service mesh sidecar** | Traffic có thể đi qua loopback/sidecar, TLS origination, proxy ports | Proxy logs, workload identity và CNI flow records |

**Không “nối” hai flows chỉ vì có cùng destination port 443.** Phải có đủ **time correlation, translated tuple, resource ownership, proxy request ID và loại protocol** để khẳng định một quan hệ.

### 11.3. Client IP trong HTTP headers

Một reverse proxy có thể ghi **X-Forwarded-For** hoặc **Forwarded**; nhưng headers này **có thể bị client tự tạo** nếu ingress không chuẩn hóa. Chỉ dùng chúng để attribution khi đã xác định **trusted proxy chain, edge policy, socket peer và header transformation**. Flow logs ở L3/L4 không biết header nào là IP “thật” của user nếu không có correlation đáng tin.

## 12. Cloud firewall, security group, ACL và các điểm drop khác

Trong một hành trình cloud, nhiều lớp có thể xử lý packet:

~~~mermaid
flowchart LR
    SRC["Source VM"] --> SG1["Egress policy"]
    SG1 --> RT["Route / NAT / Transit"]
    RT --> FW["Network firewall / NVA"]
    FW --> SG2["Destination ingress policy"]
    SG2 --> HOST["Host firewall / process"]
~~~

Một **REJECT** ở điểm SG1 không thể chứng minh SG2 cũng từ chối; packet có thể đã bị loại trước khi tới. Một **ACCEPT** ở SG1 không đảm bảo RT/FW/SG2/HOST cho phép. Để tìm **root cause**, cần xây **chuỗi quyết định policy** theo từng hop, sử dụng logs có **rule attribution** khi chúng tồn tại.

### 12.1. Phân biệt route, security policy và app listener

| Hiện tượng | Cần xác minh |
| --- | --- |
| Có route đúng nhưng traffic bị REJECT | Security group/NACL/network firewall, identity policy |
| Flow ACCEPT egress nhưng không tới server | Next hop, NAT, peering/Transit, firewall, remote ACL |
| Flow ACCEPT ingress server nhưng không có response | OS firewall, service listener, TLS/application, host resource |
| Response egress server nhưng client timeout | Return route, NAT mapping, stateful firewall, MTU |
| Traffic nội bộ đi sai region/zone | Effective route, TGW/peering/VRF, policy-based steering |

### 12.2. Stateful return traffic và hiểu sai “allow”

Một số stateful security controls cho phép packets chiều về dựa trên trạng thái kết nối đã được chấp nhận, dù không có rule inbound/outbound riêng cho từng chiều. Không suy **mỗi ACCEPT record** đều có một rule ACL tương ứng mở rộng. Ngược lại, nếu topology dùng **stateless ACL** hoặc traffic đi qua firewall stateful **không giữ cùng session owner**, return packet có thể bị chặn dù một chiều đã có log ACCEPT.

### 12.3. Route blackhole và logging coverage

Nếu packet bị mất ở **route blackhole hoặc dịch vụ mạng ngoài scope collection**, có thể **không có REJECT record** trên NIC đích, vì packet chưa từng tới điểm đó. Điều tra cần **route tables, effective next hops, cloud network analyzer/troubleshooter nếu có, logs của gateway/NVA và observations ở hai đầu**.

## 13. Kubernetes, container networking và IP động

Trong Kubernetes, workload identity không thể chỉ dựa vào địa chỉ IP: **Pod có thể bị xóa và IP được dùng lại**, cùng ứng dụng chạy trên nhiều Pods, còn service có thể dùng ClusterIP và NAT/eBPF để chuyển đến endpoint.

### 13.1. Ba lớp định danh cần giữ

| Lớp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Network address | Pod IP, Node IP, Service ClusterIP, external VIP | Địa chỉ nhìn thấy trên flow logs theo điểm capture |
| Workload resource | Pod UID, namespace, Deployment, node, container | Gắn IP với workload tại đúng timestamp |
| Security identity | Service account, workload identity, mTLS SPIFFE ID nếu có | Quyền/tin cậy vượt khỏi IP thay đổi |

**Pod IP hôm nay không chắc là Pod của tuần trước.** Với một incident quá khứ, cần **historical IP allocation, Kubernetes events/audit, CNI metadata và workload lifecycle**; join vào inventory hiện tại có thể gán nhầm traffic cho ứng dụng mới.

### 13.2. CNI, overlay và eBPF

Một Pod↔Pod request có thể xuất hiện dưới dạng **inner Pod IP**, **outer node IP qua VXLAN/Geneve** hoặc các addresses do CNI NAT/snat, tùy điểm quan sát. Cloud VPC flow log ở node ENI có thể thấy **node traffic** nhưng không có **pod-level context** cần thiết. Hãy kết hợp **CNI/eBPF flow telemetry, service mesh access logs, Kubernetes events và NetworkPolicy policy decisions** khi cần attribution chi tiết.

### 13.3. Kubernetes NetworkPolicy

NetworkPolicy phụ thuộc **CNI implementation hỗ trợ enforcement**; tài nguyên được khai báo không tự động bảo đảm mọi traffic chịu policy. Việc traffic bị chặn ở Pod/namespace có thể có logs CNI riêng nhưng không xuất hiện dưới dạng **REJECT** trong cloud VPC flow log. Cần test tại đúng enforcement point và giữ **ALLOW/DENY regression** sau thay đổi service networking.

### 13.4. Không lấy lưu lượng health probes làm bằng chứng tấn công

Kubelet, readiness/liveness, node agents và service meshes có thể tạo lưu lượng ngắn/lặp nhiều tới các ports. Khi phát hiện “nhiều IP kết nối một port”, hãy đối chiếu **workload owner, scheduler events, deployment, health checks và source network** trước khi coi là reconnaissance.

## 14. IPv6, DNS, VPN, transit và traffic mã hóa

### 14.1. IPv6 không phải IPv4 với địa chỉ dài hơn

Lưu lượng IPv6 dùng **ICMPv6** cho Neighbor Discovery và Path MTU Discovery theo cách khác IPv4; một số protocol/ports không có cùng ý nghĩa. Route, security groups, public exposure và flow logging có thể được cấu hình riêng cho **IPv4/IPv6**.

Nếu một detection rule chỉ so **src_ip là IPv4 private**, nó có thể bỏ sót workloads có **IPv6 public address** hoặc các flows tới IPv6 destinations. Cần parse IP address family đúng, không giả định **NAT44 sẽ xuất hiện trên mọi egress IPv6**.

### 14.2. VPN và hybrid WAN

Với IPsec tunnel, flow logs ở **outer interface** có thể chỉ thấy **gateway public IP, protocol ESP (50) hoặc UDP 4500 NAT-T**, không thấy inner client↔service tuples mã hóa. Sau khi **decrypt tại gateway**, một điểm log bên trong có thể thấy **inner IP tuples**.

~~~text
Inner (sau giải mã / trước mã hóa):
  10.10.1.25:51515 -> 10.20.2.15:443 TCP

Outer qua Internet:
  198.51.100.10 -> 203.0.113.10 ESP
  hoặc UDP/4500 nếu NAT-T theo triển khai.

Không lấy outer ESP flow để kết luận trực tiếp
có bao nhiêu HTTPS requests bên trong tunnel.
~~~

Ngoài cloud flow logs, cần **VPN/SD-WAN tunnel health, IPsec SA counters, route/BGP changes, firewall logs, on-prem collectors** để xác minh đường đi hai chiều. Nếu on-prem không có logs tương đương, ghi rõ **blind spot** thay vì suy toàn bộ return path từ cloud.

### 14.3. DNS và hostname attribution

Flow log thường cho biết **destination IP**, không tự cho biết hostname mà ứng dụng đã truy vấn. Một IP có thể phục vụ **nhiều domains phía CDN**. Ghép với DNS resolver logs có thể giúp xây giả thuyết nhưng có giới hạn:

- Client cache DNS, query không được ghi ở resolver của tổ chức hoặc dùng DoH/DoT.
- DNS response có nhiều A/AAAA records và TTL; IP có thể đổi theo thời gian.
- Một IP CDN/shared hosting phục vụ nhiều hostnames; nối IP↔domain không là bằng chứng chắc user gọi đúng hostname đó.
- TLS SNI/ECH có visibility khác nhau; application Host/authority có thể không lộ trên wire.

Không suy **“đích IP thuộc CDN X”** nghĩa là dữ liệu gửi đến **domain Y** nếu thiếu DNS, proxy hoặc application evidence.

### 14.4. Peering và transit gateway

Traffic giữa VPCs/VNets có thể đi qua **peering, transit gateway/hub, virtual WAN hoặc appliance**. Một log ở subnet nguồn và một ở subnet đích có thể mô tả cùng flow nhưng **không chứng minh không có NVA giữa đường**; đối chiếu **effective routes, attachment IDs, transit logs, NAT và security rules**.

## 15. Quy trình điều tra một flow có chứng cứ

Quy trình hiệu quả là **bắt đầu từ câu hỏi và phạm vi**, không tải toàn bộ logs rồi tìm từ khóa ngẫu nhiên.

~~~mermaid
flowchart TB
    A["Câu hỏi incident + flow/time scope"] --> B["Chuẩn hóa 5-tuple, UTC, nguồn log"]
    B --> C["Kiểm tra coverage, sampling, log-status"]
    C --> D["Xác định NIC/VPC/subnet/workload tại thời điểm"]
    D --> E["Tìm forward và reverse flow"]
    E --> F["Đối chiếu NAT/LB, routing, SG/firewall"]
    F --> G["Correlate DNS, IAM, app, audit events"]
    G --> H{"Giả thuyết được chứng minh?"}
    H -- "Chưa" --> I["Ghi unknowns và thêm evidence phù hợp"]
    H -- "Có" --> J["Phân loại impact, điều tra/ứng phó"]
    I --> G
~~~

### 15.1. Bước 1 — Ghi rõ mục tiêu và giới hạn

Ví dụ: “Vì sao máy quản trị 10.10.1.25 không kết nối được máy chủ ứng dụng 10.20.2.15:443 từ **09:10 đến 09:20 UTC**?” Từ đó xác định **environment, account, subnet, interface, IP family, expected ALLOW/DENY và triệu chứng thực**.

### 15.2. Bước 2 — Chọn đúng điểm và thời gian

Query cả **source NIC và destination NIC**, cộng logs của **firewall/NAT/LB** nằm giữa nếu có; mở rộng **time window** đủ để chịu aggregation và delivery lag. Đặt query theo **event_start/event_end**, không chỉ lúc ingest. Khi dùng UTC chuyển đổi timezone địa phương, ghi cả offset để tránh hiểu nhầm.

### 15.3. Bước 3 — Xác định nguồn/đích tại thời điểm

Liên kết IP với **VM/ENI/Pod resource ID và thời gian hiệu lực**. Nếu IP có thể được tái sử dụng, inventory hiện tại chưa đủ. Kiểm tra cloud resource inventory, audit creation/deletion, route/SG snapshots hợp pháp trong phạm vi incident.

### 15.4. Bước 4 — Tìm cặp luồng và chỗ đứt

Quan sát forward/reverse với bối cảnh NAT. Xây một bảng theo các điểm:

| Điểm | Request forward | Response reverse | Nhận định |
| --- | --- | --- | --- |
| Source NIC | Có/không, action, count | Có/không | Source có phát traffic và nhận trả lời? |
| Transit/NAT/LB | Có/không, mapping | Có/không, mapping | Có translation hoặc policy change? |
| Destination NIC | Có/không, action | Có/không, action | Gói có được quan sát gần server? |
| Application | Request/connection log | Response/status | Ứng dụng xử lý thế nào? |

### 15.5. Bước 5 — Đối chiếu control-plane

Xem các thay đổi gần thời điểm lỗi: **security group/NSG/ACL, route table, NAT gateway, ingress/LB target, IAM, instance replacement, VPN/BGP**, thông qua **cloud audit/control-plane logs**, change tickets và snapshots. Không kết luận một thay đổi gây lỗi chỉ do **trùng thời điểm**; cần kiểm tra **tác động tại đúng path**.

### 15.6. Bước 6 — Kết luận theo mức độ chắc chắn

Viết tách ba nhóm:

- **Quan sát:** Flow log tại NIC A ghi ACCEPT tới 10.20.2.15:443 trong interval X.
- **Giả thuyết:** Return path có thể bị chặn tại firewall phía server.
- **Cần xác minh:** Log NIC B hoặc firewall quyết định, app trace, effective route.

Chỉ khi có bằng chứng đủ mới ghi **root cause**; nếu không, báo **không đủ evidence** cùng gaps và bước lấy dữ liệu tiếp.

## 16. Truy vấn và chuẩn hóa: tránh ngộ nhận từ kết quả SQL

Ví dụ dạng **SQL giả lập đã chuẩn hóa**, không phải cú pháp chạy trực tiếp trên AWS CloudWatch Logs Insights, Azure KQL hay Google Cloud Logging. Thay schema, query engine và chức năng lọc theo nguồn trước khi sử dụng:

~~~sql
-- PSEUDOCODE: flow_logs là bảng chuẩn hóa giả định.
-- Truy vấn theo event time, không chỉ ingestion time.
SELECT
  event_start,
  interface_id,
  direction,
  src_ip, src_port,
  dst_ip, dst_port,
  protocol, action,
  packets, bytes, log_status
FROM flow_logs
WHERE event_start >= TIMESTAMP '2026-10-17 09:10:00'
  AND event_start < TIMESTAMP '2026-10-17 09:20:00'
  AND account = 'account-demo'
  AND (
    (src_ip = '10.10.1.25' AND dst_ip = '10.20.2.15')
    OR
    (src_ip = '10.20.2.15' AND dst_ip = '10.10.1.25')
  )
ORDER BY event_start, interface_id;
~~~

### 16.1. Những kiểm tra trước khi tổng hợp

1. **Normalize protocol** và phân biệt port không áp dụng với port 0.
2. Giữ **record source, schema version, sampling status và interface**.
3. Phân biệt các logs **duplicate vì delivery** với cùng flow nhìn ở **hai interfaces**; hai trường hợp không giống nhau.
4. Kiểm tra **start/end windows overlap**; query chỉ lọc event_start có thể bỏ những record bắt đầu trước cửa sổ nhưng vẫn hoạt động trong cửa sổ. Khi cần bao phủ mọi overlapping flow, dùng điều kiện **start < window_end và end >= window_start** với semantics end-time được xác nhận.
5. Nếu source được sampling/aggregation, ghi nhãn **observed** và phương pháp ước lượng có giới hạn.
6. Không tự quy **ACCEPT = successful connection** hay **REJECT = số packet bị drop chính xác** nếu record semantics khác.

### 16.2. Aggregation không phải deduplication

Hai records có cùng 5-tuple ở hai phút liền nhau có thể là **một kết nối dài** được chia thành nhiều intervals. Nếu đếm records là connections, kết quả sai. Ngược lại một record tổng hợp cũng có thể đại diện nhiều packets mà chưa rõ bao nhiêu attempts. Để đếm **new connections/handshakes**, cần logs/metrics có semantics chuyên biệt hoặc phương pháp dựa trên fields được hỗ trợ và validated.

### 16.3. Join IP với tài sản theo thời gian

~~~text
Không đáng tin:
  src_ip = 10.10.1.25
  JOIN current_VM_inventory ON current_VM_inventory.ip = src_ip

Hợp lý hơn:
  src_ip = 10.10.1.25
  JOIN historical_ip_assignment
    ON IP match
   AND event_time BETWEEN assignment_start AND assignment_end
   AND VPC/account/network scope match
~~~

Nhờ đó không gán traffic của **Pod đã xóa tuần trước** cho **Pod mới hôm nay**, hoặc gán nhầm IP overlap của hai VPC khác nhau.

## 17. Phát hiện bất thường: từ tín hiệu tới giả thuyết

Flow logs phù hợp để tìm **mẫu giao tiếp ở cấp IP/port**, đặc biệt khi kết hợp **baseline theo workload, identity, environment và lịch thay đổi**. Nhưng một mẫu bất thường **không phải bằng chứng chắc chắn đã bị xâm nhập**.

| Detection hypothesis | Tín hiệu flow | Cần correlation | False positive điển hình |
| --- | --- | --- | --- |
| **Reconnaissance/port sweep** | Một source tới nhiều destination ports hoặc host, nhiều REJECT | Approved scanner inventory, asset owner, IDS, IAM | Vulnerability scanner được phép, monitoring |
| **Unexpected admin access** | Public/untrusted source tới SSH 22, RDP 3389 hoặc ports quản trị | Bastion/VPN authorization, security policy, host logs | Quản trị hợp lệ qua jump host |
| **East-west lateral movement** | Workload Dev/Guest tới nhiều Prod IP/ports ngoài allowlist | Workload identity, NetworkPolicy, AD/auth, change logs | Deploy/migration, service discovery |
| **Potential data exfiltration** | Egress bytes tăng mạnh tới external IP hiếm | DLP, proxy DNS, data owner, process/app audit | Backup, artifact mirror, software update |
| **Beacon-like periodic contact** | Flows outbound ngắn lặp đều đến một destination | DNS, EDR, process identity, change schedule | NTP, health check, metrics agent |
| **DDoS/connection flood** | Tăng nhanh ingress flow volume/ports/sources | Edge DDoS telemetry, CDN, SYN counters, application SLI | Product launch, load test |
| **Crypto mining / malicious egress** | Kết nối lạ tới remote endpoints/ports | EDR/process, threat intel đã kiểm chứng, workload ownership | CDN/shared IP, hợp pháp telemetry |
| **Segmentation drift** | Connection giữa hai security zones vốn phải DENY | Intended path, firewall/SG config, app auth | Rule exception được phê duyệt nhưng inventory chưa cập nhật |
| **NAT/route regression** | Egress tăng ở nguồn nhưng reverse/dest flow biến mất | NAT mapping, route changes, SA/LB state | Sampling gaps, collector outage |
| **Unexpected cloud metadata access** | Traffic tới endpoint metadata hoặc nội bộ không dự kiến | Host/EDR, workload IAM, network restrictions | SDK/agent cloud hợp lệ |

### 17.1. Baseline theo ứng dụng, không theo một ngưỡng cho toàn cloud

Một backend API có thể tạo **hàng chục nghìn connections đến database** theo pool design, trong khi một VM quản trị gần như không có outbound traffic. Cùng một ngưỡng 1.000 flows/phút sẽ **báo sai** trên API và **bỏ sót** hoạt động lạ trên VM quản trị.

Baseline nên xét:

- **Workload type:** web/API, DB, CI/CD runner, monitoring, bastion, backup.
- **Environment:** Dev, Staging, Prod, DR; các vùng có permissions khác nhau.
- **Time:** business hours, batch window, deployment, maintenance, end-of-month.
- **Protocol/service:** TCP/443, UDP/53, VPN, metadata, database ports.
- **Direction và vùng:** East-west nội bộ, ingress Internet, egress external.
- **Quality:** Sampled records, aggregation, skipped logs và gaps.

### 17.2. Tạo allowlist theo identity và business need

Không nên chỉ dùng một danh sách **IP ranges “an toàn”** rồi cho qua tất cả. Cloud IP có thể **thay đổi, shared giữa tenants hoặc thuộc CDN**. Mẫu tốt hơn là kết hợp **workload/service identity, approved destination class, domain via trusted logs, TLS/app identity, allowed ports, ownership và thời gian**.

**Threat intelligence IP** là tín hiệu hỗ trợ triage; không có nghĩa mọi traffic tới địa chỉ từng bị gắn cờ là malicious. IP shared hosting hoặc cloud services có thể thay đổi chủ. Cần xem độ mới, độ tin cậy và ngữ cảnh trước khi đề xuất block.

### 17.3. Khi lưu lượng đã mã hóa

Flow log vẫn thấy một số metadata IP/port/volume dù payload TLS/IPsec mã hóa; nó **không tự giải mã nội dung**. Với DoH/DoT, QUIC hoặc VPN tunnel, một flow tới một IP có thể chở **nhiều logical requests**. Đừng cố dựng lại URL hay tài liệu đã gửi chỉ từ bytes.

## 18. Thiết kế cảnh báo SIEM trên flow logs

### 18.1. Một rule tốt có điều kiện bao phủ và giới hạn

Ví dụ rule minh họa:

~~~text
RULE: Possible unauthorized management access

Scope:
  Production workloads in approved cloud accounts.

Condition:
  Observed ingress flows from untrusted network to
  destination TCP/22 or TCP/3389.
  Require source not in approved management path.

Enrichment:
  Resource/owner, SG/ACL policy, NAT and LB context,
  VPN/bastion inventory, change window, log health.

Severity:
  Higher for accepted unexpected flows to critical hosts;
  lower or informational for already rejected attempts.

Required evidence:
  Original flow record, time, interface, quality/sampling,
  app/host or firewall corroboration where possible.

Action:
  Create triage ticket; no automatic broad network block
  without approved decision and false-positive controls.
~~~

**Không đánh đồng ACCEPT với successful SSH login.** Muốn xác định phiên đăng nhập và actor, cần **bastion/SSH/auth logs, identity logs, EDR/host evidence**, có thể cùng connection records.

### 18.2. Ba tầng xử lý tín hiệu

1. **Detection:** Một pattern đạt điều kiện kỹ thuật, mang nhãn **suspected/anomalous**.
2. **Triage:** Phân tích environment, source identity, baseline, changes, logs, exemptions.
3. **Incident conclusion:** Chỉ xác nhận compromise/policy violation khi có bằng chứng đáp ứng tiêu chí của đội an ninh.

Không để alert tự động chuyển thành “confirmed data exfiltration” chỉ vì **egress bytes vượt threshold**.

### 18.3. Risk-scoring thay vì block theo một field

| Signal | Ý nghĩa | Hạn chế |
| --- | --- | --- |
| Destination IP mới đối với workload | Chưa thấy trong baseline | Có thể là rollout hợp lệ |
| Egress bytes tăng 10 lần | Data transfer bất thường | Có thể do release, backup |
| Destination hiếm và chưa có owner | Cần kiểm tra | Không chứng minh là attacker |
| Workload nằm trong subnet nhạy cảm | Tăng mức độ ảnh hưởng | Không phải bằng chứng compromise |
| Firewall reject liên tục | Nhiều attempts bị chặn | Có thể do cấu hình client lỗi |
| App/EDR alert tương quan cùng thời gian | Tăng độ tin cậy | Phải kiểm tra nguồn evidence độc lập |
| Collection status SKIP/DROP | Bằng chứng incomplete | Có thể làm giảm confidence, không tăng threat severity |

Một điểm số chỉ có ích khi **dữ liệu đầu vào có quality labels, được calibrate, có lịch sử false positives và reviewer**. Tự động chặn broad CIDR dựa trên một số “risk score” chưa kiểm nghiệm có thể gây outage.

### 18.4. Hạn chế cardinality và alert fatigue

Nếu tạo một alert cho mỗi **REJECT record**, Internet-facing service có thể nhận vô số alerts không hữu ích. Hãy **nhóm theo resource, source/dest cohort, port class, time window**, phân biệt **known noisy background** và những attempts tới tài sản critical. Khi nhóm, giữ đủ **sample evidence và distinct counts** để có thể điều tra mà không mất ngữ cảnh.

## 19. Case study A: yêu cầu HTTPS bị timeout qua subnet khác

**Bối cảnh giả định:** Một application VM trong subnet **10.10.1.0/24** không gọi được API ở subnet **10.20.2.0/24** trên TCP/443 sau một thay đổi network policy. Flow logs đã bật tại cả hai NIC, nhưng đội hỗ trợ chỉ xem bản ghi ở máy nguồn.

### 19.1. Các observations

| Nguồn | Quan sát giả định | Diễn giải |
| --- | --- | --- |
| NIC nguồn | Egress flow 10.10.1.25:51320 → 10.20.2.15:443, ACCEPT | Lưu lượng được chấp nhận tại điểm nguồn |
| NIC đích | Ingress cùng 5-tuple, REJECT | Có bằng chứng policy chặn tại điểm đích theo semantics nguồn |
| Route table | Prefix 10.20.2.0/24 có next hop dự kiến | Không loại trừ vấn đề policy |
| Audit changes | Ingress allow rule đích bị thu hẹp ngay trước lỗi | Có quan hệ thời gian cần xác minh bằng rule evaluation |
| Application log | Không có request tại API server | Phù hợp packet bị chặn trước application, nhưng không chứng minh duy nhất |

~~~mermaid
flowchart LR
    A["App 10.10.1.25"] -->|"ACCEPT egress"| R["Route"]
    R -->|"REJECT ingress"| S["API 10.20.2.15"]
    R -. "Network policy decision" .-> P["Destination security control"]
~~~

### 19.2. Các giả thuyết và kiểm chứng

1. Source egress đã cho phép TCP/443 nhưng **destination ingress policy** mới không còn cho phép source subnet/identity.
2. Một **NSG/ACL/security group** hoặc cloud firewall nằm trên path đang chặn, log ở đích phản ánh quyết định đó.
3. Route hoặc NIC đã thay đổi khiến traffic đi qua **security zone khác**.

Điều tra bằng **effective rules, cloud audit change, workload identity và packet/flow path**. Nếu xác nhận policy lỗi, tạo thay đổi **phạm vi hẹp** chỉ cho đúng service identity/subnet và port 443; không mở ANY/ANY để thử.

### 19.3. Regression tests

- App đúng identity/subnet → API TCP/443: **ALLOW**.
- Dev/Guest hoặc unauthenticated source → API/DB: **DENY**.
- SSH/RDP từ Internet vào API server: **DENY**.
- Return path, NAT nếu có, và application TLS/HTTP: hoạt động đúng.
- Logs ở source/destination và policy audit: tiếp tục thu đầy đủ sau sửa.

**Bài học:** Flow log ACCEPT ở một NIC không phải kết luận toàn đường cho phép. **Đối chiếu hai chiều và policy tại từng điểm** là chìa khóa để tìm root cause mà không nới lỏng bảo mật.

## 20. Case study B: egress bytes tăng sau khi VM đổi owner

**Bối cảnh giả định:** Một VM có private IP **10.10.1.25** vốn chạy tác vụ báo cáo ít traffic, bỗng xuất hiện nhiều bản ghi egress TCP/443 tới **198.51.100.80** qua NAT gateway. Một alert gắn nhãn “potential exfiltration”. Trong cùng tuần, nhóm SRE đã đổi deployment/VM và chạy một tác vụ backup hợp lệ.

### 20.1. Không kết luận quá sớm

| Dữ liệu | Có thể cho biết | Không chứng minh |
| --- | --- | --- |
| Flow log VM egress | Metadata và bytes đã quan sát | File nào, dữ liệu bí mật hay transfer hoàn tất |
| NAT public mapping | Public tuple của kết nối ra WAN | User/process trong VM |
| Historical IP assignment | VM/resource nào có IP tại thời điểm log | Người dùng nào điều khiển process |
| DNS/proxy logs | Hostname/request context nếu được ghi | Mọi traffic tới shared IP là đúng hostname đó |
| EDR/process and app logs | Process/command/job đã kết nối | Các bytes thực đã đi đâu nếu app logs thiếu |
| Cloud audit | Ai thay VM/IAM/route, khi nào | Thay đổi đó là nguyên nhân chắc chắn |
| Business change ticket | Có backup/copy data dự kiến | Không có data leakage ngoài ticket |

### 20.2. Quy trình điều tra an toàn

1. **Cố định timeline UTC**, ghi current vs historical resource owner và interface.
2. Kiểm tra **collection quality**: logs sampled hay toàn bộ, có skipped records không?
3. Tìm flow trước NAT và mapping sau NAT; không quy mọi traffic NAT public cho một VM.
4. Tra baseline cùng workload, cùng giờ/ngày và các lần backup định kỳ.
5. Correlate **DNS, proxy, data classification, EDR, process/container identity, IAM và object-storage audit** theo quyền.
6. Xác định **đích có được phê duyệt** hay không, loại dữ liệu có rời trust boundary thực sự hay không.
7. Nếu nghi incident có chứng cứ, phối hợp SOC/incident commander để **cô lập có kiểm soát, bảo toàn logs, keys, process evidence**.
8. Ghi rõ **confidence level và gaps**; không thông báo “exfiltration confirmed” chỉ vì bytes tăng.

### 20.3. Tình huống dễ gây báo sai

VM **10.10.1.25** đã được thu hồi, private IP tái sử dụng cho một batch worker mới trong cùng subnet. Analyst join logs quá khứ với inventory hiện tại rồi gán sai traffic cho workload báo cáo cũ. **Historical resource ID và IP allocation time** khắc phục nhầm lẫn đó.

**Bài học:** Flow logs xác định dấu vết giao tiếp và lượng traffic tại điểm quan sát, không tự cho biết ý định hay nội dung dữ liệu. **NAT ownership, time-aware enrichment và ứng dụng/endpoint evidence** quyết định chất lượng kết luận.

## 21. Case study C: mất log sau khi điều chỉnh IAM

**Bối cảnh giả định:** SOC thấy egress traffic và REJECT alerts giảm gần bằng 0 sau khi đội nền tảng đổi IAM policy cho log sink. Dashboard báo “mạng sạch hơn”, nhưng application throughput vẫn bình thường.

### 21.1. Tín hiệu phân biệt

| Metric | Trước thay đổi | Sau thay đổi | Ý nghĩa |
| --- | --- | --- | --- |
| Flow records ingested | 100.000 records/giờ (giả định) | 100 records/giờ | Có thể pipeline thiếu |
| App RPS | 2.000 requests/s | 2.100 requests/s | Traffic vẫn diễn ra |
| NIC throughput | Bình thường | Bình thường | Giảm logs không đồng nghĩa ít traffic |
| Sink delivery errors | 0 | Tăng | Bằng chứng lỗi pipeline |
| Cloud audit | Không thay IAM | Có thay role/policy log writer | Gợi ý nguyên nhân cần xác minh |

### 21.2. Xử lý

1. **Phát cảnh báo data-quality incident**, không hạ threat level chỉ vì thiếu events.
2. Xem **collector enabled status, delivery errors, role permissions, encryption key grants, destination quotas** theo quyền.
3. Phục hồi policy writer tối thiểu cần thiết, ghi approval/change ID.
4. Kiểm tra **gaps theo resource và time window**; xác định có khả năng backfill từ nguồn nào không.
5. Correlate firewall/app/EDR logs còn lại cho thời gian thiếu, **không hứa sẽ phục hồi bản ghi không tồn tại**.
6. Triển khai alerts trên **ingestion lag, volume baseline, skip count, config drift**.

**Bài học:** Bản thân **hệ thống logging cũng là tài sản cần bảo vệ và giám sát**. Không có dòng bất thường khi pipeline ngừng ghi chỉ là **không có bằng chứng**, không phải tình trạng an toàn.

## 22. Lab Python offline: thống kê các flow log tổng hợp

Lab này **không mở socket, không quét mạng, không gọi cloud API, không đọc file và không thay firewall**. Dữ liệu hoàn toàn được tạo trong source code, dùng IP private và các IP tài liệu TEST-NET. Mục tiêu là **tính đúng những gì đã quan sát**, phân biệt status SKIPPED, thống kê REJECT theo nguồn và phát hiện **egress tới IP ngoài phạm vi mạng nội bộ dự kiến**.

### 22.1. Input và quy ước

- Một **Flow** tương ứng **một record tổng hợp giả định**, không bắt buộc bằng một connection.
- **bytes** là số byte đã quan sát trong record, không phải dữ liệu ứng dụng thực sự truyền thành công.
- **status != OK** được đưa vào danh sách quality issues, không gộp vào thống kê định lượng.
- Việc xác định đích ngoài mạng là **ngoài dải nội bộ 10.0.0.0/8 của mô hình lab**, không dựa vào IP public/private của Python để tránh hiểu sai những dải tài liệu.
- Action **REJECT** chỉ có ý nghĩa của collector giả định trong lab; không quyết định tấn công.

### 22.2. Code mô phỏng độc lập

~~~python
from collections import Counter, defaultdict
from dataclasses import dataclass
from ipaddress import ip_address, ip_network


INTERNAL = ip_network("10.0.0.0/8")


@dataclass(frozen=True)
class Flow:
    event_start: str
    interface: str
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str
    direction: str
    action: str
    bytes: int
    log_status: str


records = [
    Flow("2026-10-17T09:10:00Z", "nic-api",
         "203.0.113.7", "10.0.1.10", 51410, 22,
         "TCP", "ingress", "REJECT", 300, "OK"),
    Flow("2026-10-17T09:10:05Z", "nic-api",
         "203.0.113.7", "10.0.1.10", 51411, 3389,
         "TCP", "ingress", "REJECT", 300, "OK"),
    Flow("2026-10-17T09:10:10Z", "nic-api",
         "203.0.113.7", "10.0.1.10", 51412, 8080,
         "TCP", "ingress", "REJECT", 300, "OK"),
    Flow("2026-10-17T09:11:00Z", "nic-api",
         "10.0.1.10", "198.51.100.80", 51515, 443,
         "TCP", "egress", "ACCEPT", 900000, "OK"),
    Flow("2026-10-17T09:11:05Z", "nic-api",
         "10.0.1.10", "10.0.2.20", 51300, 443,
         "TCP", "egress", "ACCEPT", 6000, "OK"),
    Flow("2026-10-17T09:11:06Z", "nic-db",
         "10.0.2.20", "10.0.1.10", 443, 51300,
         "TCP", "egress", "ACCEPT", 4800, "OK"),
    Flow("2026-10-17T09:12:00Z", "nic-api",
         "10.0.1.10", "198.51.100.80", 51516, 443,
         "TCP", "egress", "ACCEPT", 0, "SKIPPED"),
]


def analyze(flows: list[Flow]) -> dict:
    quality_issues = [f for f in flows if f.log_status != "OK"]
    usable = [f for f in flows if f.log_status == "OK"]

    # Đây là số RECORDS bị REJECT, không phải số attempts thực.
    rejected_records_by_source = Counter(
        f.src_ip for f in usable
        if f.direction == "ingress" and f.action == "REJECT"
    )

    # Định nghĩa destination outside INTERNAL của riêng bài lab.
    external_egress_bytes = defaultdict(int)
    for f in usable:
        if (
            f.direction == "egress"
            and f.action == "ACCEPT"
            and ip_address(f.src_ip) in INTERNAL
            and ip_address(f.dst_ip) not in INTERNAL
        ):
            external_egress_bytes[f.src_ip] += f.bytes

    return {
        "usable_records": len(usable),
        "quality_issues": len(quality_issues),
        "rejected_records_by_source": dict(
            sorted(rejected_records_by_source.items())
        ),
        "external_egress_observed_bytes": dict(
            sorted(external_egress_bytes.items())
        ),
    }


def reverse_tuple(a: Flow, b: Flow) -> bool:
    """Chỉ là phép tìm tuple đảo, không chứng minh cùng session."""
    return (
        a.src_ip == b.dst_ip
        and a.dst_ip == b.src_ip
        and a.src_port == b.dst_port
        and a.dst_port == b.src_port
        and a.protocol == b.protocol
    )


result = analyze(records)
print(result)
print("possible_reverse_tuple:", reverse_tuple(records[4], records[5]))

assert result["usable_records"] == 6
assert result["quality_issues"] == 1
assert result["rejected_records_by_source"] == {"203.0.113.7": 3}
assert result["external_egress_observed_bytes"] == {"10.0.1.10": 900000}
assert reverse_tuple(records[4], records[5])
~~~

Kết quả dự kiến:

~~~text
{
  'usable_records': 6,
  'quality_issues': 1,
  'rejected_records_by_source': {'203.0.113.7': 3},
  'external_egress_observed_bytes': {'10.0.1.10': 900000}
}
possible_reverse_tuple: True
~~~

### 22.3. Cách diễn giải lab

Ba records bị REJECT tới 22, 3389, 8080 từ cùng source **có thể gợi ý dò port**, nhưng cũng có thể do **scanner được phê duyệt, ứng dụng cấu hình lỗi hoặc bộ kiểm tra mạng**. Không xác định chủ ý chỉ bằng record count.

Mô hình ghi nhận **900.000 bytes outbound** từ 10.0.1.10 tới IP ngoài dải 10.0.0.0/8 theo scope lab. Không thể khẳng định đó là **exfiltration**, vì chưa có **process context, domain, dữ liệu, business change và remote confirmation**.

Một record **SKIPPED** được tách ra để cảnh báo thiếu chất lượng; không coi 0 bytes là chắc không có traffic. Phép **reverse_tuple** chỉ tìm bộ trường đảo; cần **time, resource, NAT, sampling và session evidence** để chứng minh liên quan.

### 22.4. Giới hạn quan trọng

1. Không có **parsing logs thật** của AWS/Azure/GCP; field names được chuẩn hóa giả định.
2. Không xử lý **aggregation windows overlap** hoặc deduplicate delivery; cùng 5-tuple nhiều records vẫn được đếm riêng.
3. Không có **sampling expansion**; counts/bytes là observed values trong dataset giả.
4. Không map **NAT public tuple, shared IP, Pod IP theo thời gian** hoặc layer 7 user identity.
5. Không phát hiện **TCP handshake thành công**, không kết luận bytes đến application.
6. Không có policy engine, threat intel validation, SIEM schema hay xử lý permissions.
7. Không dùng địa chỉ TEST-NET minh họa để suy về một host public thực.
8. Dữ liệu và kết quả **không phải bằng chứng một cuộc tấn công thực**.

### 22.5. Bài tập mở rộng

- Thêm trường **account, VPC, interface, IP family, end timestamp** và chỉ so flows trong cùng network scope.
- Thêm trường **sampling**; nếu có record sampled, không gán confident count of connections.
- Tạo dataset chứa **IPv6 records** và phân loại source/destination bằng thư viện ipaddress phù hợp.
- Thêm **NAT translation mapping giả lập** theo port/time, chứng minh hai tuples có thể thuộc cùng workload.
- Thêm **ingestion timestamp** và tính delivery lag cho records có event time.
- Thêm threshold **trên baseline theo workload** thay vì cùng threshold cho mọi VM.
- Thêm **historical resource ownership** với validity intervals, tránh gán IP cũ cho Pod mới.
- Thêm **unknown action/log status** và báo quality issue thay vì ép thành ACCEPT.

## 23. An toàn dữ liệu, lưu trữ và chuỗi bằng chứng điều tra

Flow logs không nhất thiết chứa HTTP body, nhưng vẫn là **dữ liệu nhạy cảm về cấu trúc mạng và hành vi**: internal IPs, remote partners, service ports, thời điểm truy cập, lượng traffic và account/resource identifiers.

### 23.1. Nguyên tắc bảo vệ

| Mối quan tâm | Yêu cầu vận hành |
| --- | --- |
| **Least privilege** | Analyst chỉ đọc cần thiết, collection writer không thể sửa policy hay xóa logs |
| **Encryption** | Mã hóa khi lưu/chuyển theo khả năng dịch vụ, quản lý khóa và quyền giải mã |
| **Tamper resistance** | Audit thay đổi, versioning/immutable retention phù hợp, tránh admin tùy ý xóa |
| **Retention** | Phù hợp incident window, luật/quy định và ngân sách; có quy tắc xóa đúng hạn |
| **Data residency** | Không tập trung logs qua biên giới vùng dữ liệu trái policy |
| **Access auditing** | Ghi ai query/export/downloading logs và hành vi truy xuất lớn |
| **Data minimization** | Chỉ lưu fields cần cho use cases, tránh enrichment lộ PII không cần thiết |
| **Sharing evidence** | Redact/pseudonymize khi có thể, giới hạn người nhận và thời gian |
| **Backup/restore** | Kiểm tra khả năng phục hồi log sink và truy vấn trong disaster |
| **Clock/schema provenance** | Giữ format, timezone, source, schema version, collection scope |

### 23.2. Evidence preservation

Trong điều tra bảo mật, một bản trích xuất phải có **nguồn, điều kiện lọc, thời gian trích xuất, checksum/hash của artifact khi cần, người thực hiện, quyền truy cập và chuỗi bàn giao**, theo quy trình tổ chức. Nếu dữ liệu cloud do provider quản lý, không mặc định có thể chứng minh **tính toàn vẹn pháp lý** chỉ từ một file CSV tải về.

**Không chỉnh sửa log gốc để làm timeline đẹp hơn.** Hãy lưu **bản ghi raw và normalized representation** cùng version của parser; khi redaction, giữ bằng chứng nguồn có kiểm soát và ghi rõ các trường bị biến đổi.

### 23.3. An toàn khi chia sẻ trong ticket

Không dán trực tiếp **public IP của đối tác nhạy cảm, mô tả hệ thống quản trị, IPAM toàn tổ chức, credentials, private keys, session cookies hoặc liên kết storage có quyền đọc công khai** vào ticket không được kiểm soát. Flow log có thể chứa IP thật, còn dữ liệu enrichment từ SIEM có thể chứa user identities; cần chính sách phân loại và phân quyền phù hợp.

### 23.4. Monitoring của chính hệ thống log

Collection config, writer IAM, KMS policy, sink lifecycle và SIEM parsers đều cần **change monitoring**. Hành vi bất thường như **vô hiệu hóa flow logs ngay trước khi có egress lạ**, không đủ chứng minh ý định xấu nhưng cần ưu tiên điều tra; đối chiếu cloud audit, owner và change approval.

## 24. Ma trận kiểm thử flow logging và điều tra

Các ca bên dưới được thiết kế cho **lab/staging hoặc hạ tầng được cấp quyền**. Không gửi packet scan/port sweep hay tạo lưu lượng DDoS tới dịch vụ công cộng. Những ca giả lập deny, route failure, failover và mất collector phải có **owner, scope, maintenance plan, rollback**. Không thực hiện giả mạo source IP ngoài lab.

| Test ID | Tình huống | Kỳ vọng / bằng chứng |
| --- | --- | --- |
| FL-01 | Luồng TCP/443 được phép giữa hai VM | Có bản ghi phù hợp tại nguồn/đích theo coverage và latency đã công bố |
| FL-02 | Luồng TCP/22 bị chặn bởi policy trong lab | Có evidence REJECT/log chuyên policy nếu nguồn hỗ trợ; app không nhận |
| FL-03 | Luồng TCP/443 ACCEPT nhưng backend không listen | Flow log không bị suy thành HTTP 200; có host/app corroboration |
| FL-04 | Truy vấn forward/reverse 5-tuple | Kết quả có hướng, thời gian và interface; không đếm trùng |
| FL-05 | Cùng 5-tuple qua hai aggregation windows | Không tự báo là hai kết nối độc lập |
| FL-06 | Một record có log status SKIPPED | Được gắn quality issue, không coi missing là zero traffic |
| FL-07 | Pipeline delivery delay có biến động | Alert theo event time và ingestion lag được đo |
| FL-08 | Flow log lấy mẫu theo cấu hình | Dashboard ghi sampled data và giới hạn ước lượng |
| FL-09 | VM có nhiều NIC | Scope thu bao gồm đúng NICs, resource ID ghi đầy đủ |
| FL-10 | Pod bị xóa và IP được cấp lại | Historical IP mapping không gán traffic sai Pod |
| FL-11 | Pod→Service qua CNI NAT/overlay | Log cloud và CNI được correlation theo topology |
| FL-12 | Egress qua SNAT NAT gateway | Pre/post NAT tuples chỉ được join khi có mapping và time |
| FL-13 | L4 full proxy hoặc L7 LB | Không gộp client/backend sockets làm một 5-tuple sai |
| FL-14 | DSR trả trực tiếp theo topology lab | Không kết luận missing reverse tại LB là failure |
| FL-15 | TCP/443 qua VPN IPsec | Phân biệt inner traffic và outer ESP/UDP4500 theo điểm log |
| FL-16 | IPv6 egress | Parsing, route, flow coverage và policy phù hợp IPv6 |
| FL-17 | Ingress Internet được WAF/CDN xử lý | Flow logs được correlate với WAF/L7 logs, không đo URL từ 5-tuple |
| FL-18 | Cross-VPC/VNet peering hoặc transit | Cả hai network scopes và attachments được kiểm tra |
| FL-19 | DB subnet chỉ cho phép API identity | ALLOW đúng luồng, DENY Dev/Guest trái policy |
| FL-20 | Route blackhole trong lab | Không suy rằng thiếu REJECT nghĩa là gói đã đến |
| FL-21 | Security group/ACL đổi trong lab | Flow decision và audit change đối chiếu đúng timestamp |
| FL-22 | Scan nhiều ports đã được phê duyệt trong lab | Rule chỉ báo suspected, gắn scanner identity, hạn chế false positive |
| FL-23 | Backup lớn hợp lệ | Egress anomaly được triage cùng change/EDR/app logs, không auto exfil |
| FL-24 | Flow logs bị ngừng thu do IAM writer sai trong lab | Data-quality alert phát hiện dù application SLI bình thường |
| FL-25 | Ingestion có duplicate do retry | Dedupe đúng delivery event nhưng không loại nhầm quan sát tại hai NIC |
| FL-26 | Provider thay schema/version | Parser detect changes, unknown fields không bị ép thành ACCEPT |
| FL-27 | DR region failover | Resource coverage, sink IAM và dashboards hoạt động cho DR |
| FL-28 | Query logs qua account boundary | RBAC/encryption/access audit đúng, không rò sensitive IP inventory |
| FL-29 | Record có timestamp ngay ranh giới cửa sổ | Query overlap không bỏ sót flow kéo dài |
| FL-30 | Phát hiện unexpected admin access | Kết luận dựa trên log + bastion/host auth evidence, không chỉ ACCEPT |
| FL-31 | DNS query về một IP CDN shared | Không quy chắc hostname nếu không có DNS/proxy evidence phù hợp |
| FL-32 | Lưu archive phục vụ incident | Bảo toàn raw data, schema, retention, source và kiểm tra truy xuất |
| FL-33 | Tắt/rollback policy phát hiện false positive | Không làm mất collection hoặc mở firewall trái phép |
| FL-34 | Cloud provider flow log và firewall rule logs khác kết quả | Phân biệt observation point và log semantics trước khi kết luận |
| FL-35 | Test ALLOW/DENY sau chỉnh phân đoạn Prod/Dev | Service được phép hoạt động, đường trái quyền vẫn bị chặn |
| FL-36 | Collector phục hồi sau outage | Cập nhật data gaps và evidence confidence, không hứa backfill khi nguồn không có |

### 24.1. Mẫu ghi một ca

~~~text
TEST / CHANGE ID:
Owner / approver / environment:
UTC event window:
Source/destination IP:port and protocol:
Cloud account/project/subscription, VPC/VNet, interface:
Collection point, interval and sampling:
Expected ALLOW/DENY and policy:
Observed action, bytes, packets, log status:
Forward/reverse and NAT/LB mappings:
Correlated firewall/IDS/app/audit evidence:
Actual service behavior:
Quality gaps / confidence:
Rollback and next action:
~~~

### 24.2. Đừng bỏ qua thử nghiệm âm tính

**ALLOW test** chứng minh rằng service hợp lệ hoạt động **đến đâu đó**, nhưng chưa chứng minh phân đoạn an toàn. **DENY test** chứng minh một đường trái quyền bị chặn ở điểm phù hợp; cũng chưa chứng minh mọi đường bypass đã đóng. Cần test **Internet, private access, IPv4/IPv6, transit, VPN và DR** theo threat model và inventory.

### 24.3. Khi flow log không ghi một loại traffic dự kiến

Trước khi kết luận hệ thống logging lỗi, hãy kiểm tra **theo tài liệu của triển khai cụ thể** xem loại traffic đó có nằm trong phạm vi hỗ trợ không, có bị service fabric xử lý ngoài điểm quan sát không, đã bật đúng collection scope chưa, hay log record bị sample/skip. Khi không thể ghi traffic qua nguồn này, lựa chọn **log chuyên dụng** hoặc capture ở điểm có thẩm quyền, rồi mô tả blind spot.

## 25. Những ngộ nhận thường gặp khi đọc cloud flow logs

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Flow log là PCAP.” | Nó thường là metadata/aggregation, không phải đầy đủ packets/payload. |
| “ACCEPT nghĩa là kết nối ứng dụng thành công.” | Chỉ là quyết định/tín hiệu tại điểm quan sát theo semantics nguồn. |
| “REJECT cho biết chắc rule firewall nào chặn.” | Cần log có rule attribution hoặc control-plane data để xác định. |
| “Không có log nghĩa là không có traffic.” | Có thể vì scope, sampling, delay, collector outage hoặc loại traffic không hỗ trợ. |
| “Một record tương đương một TCP connection.” | Một flow có thể bị chia nhiều aggregation windows hoặc records. |
| “Một source/destination IP là một người dùng.” | NAT, proxy, shared IP, ephemeral workloads và IP reuse làm sai attribution. |
| “Egress bytes lớn chắc chắn là đánh cắp dữ liệu.” | Cần process, data owner, business context, endpoint/proxy logs. |
| “Nhiều REJECT ports là attack chắc chắn.” | Có thể là scanner được phép, health/monitoring hoặc cấu hình sai. |
| “Flow log luôn tức thời.” | Collection/aggregation/delivery có latency. |
| “Có ACCEPT ở NIC nguồn là server đã thấy packet.” | Route, NAT, firewall hoặc host còn có thể chặn. |
| “Không có reverse flow là server không trả lời.” | Return path khác, NAT, sampling, aggregation hoặc log scope khác. |
| “Cộng bytes cả hai NIC ra tổng network throughput.” | Có thể đếm hai lần cùng packets ở những observation points khác nhau. |
| “Có public IP NAT là tìm ngay được VM nguồn.” | Cần translation/port/time context và private-side records. |
| “Pod IP hiện tại xác định được Pod tạo traffic tháng trước.” | Pod IP có thể được tái sử dụng; cần historical mapping. |
| “VPC flow log thấy được URL HTTPS.” | Không, chỉ có network metadata; URL cần L7/app evidence hợp pháp. |
| “Traffic VPN outer ESP cho biết tất cả inner ports.” | Inner traffic được mã hóa, phải có log tại endpoint/inside nếu cần. |
| “VPC flow log và firewall threat logs là một.” | Điểm quan sát, schema, rule/action semantics khác nhau. |
| “Mọi provider và mọi region có flow log giống nhau.” | AWS, Azure, GCP có scope/sampling/aggregation/schema khác nhau. |
| “Azure NSG flow logs luôn là cách triển khai mới nhất.” | Cần kiểm tra hướng dẫn VNet flow logs và lifecycle của NSG logs legacy. |
| “Không thấy traffic IPv6 vì IPv4 đã thu đầy đủ.” | IPv6 có route/policy và coverage riêng. |
| “Tôi chỉ cần log ở một subnet cho toàn bộ transit.” | Traffic có thể qua nhiều hop/managed services nằm ngoài scope. |
| “Điểm SIEM cao nghĩa là đã bị tấn công.” | Risk score cần xác minh, false positives và evidence độc lập. |
| “Sau khi sửa IAM writer, mất log có thể tự hiện lại.” | Không bảo đảm backfill records vốn chưa được ghi/lưu. |
| “Nên ghi cả token và payload để điều tra.” | Flow logs không cần secrets; log enrichment phải bảo vệ PII và key material. |
| “Cấu hình logging hoạt động nghĩa là không cần kiểm tra quality.” | Phải theo dõi skip, sampling, delivery, schema và coverage. |
| “Lưu CSV là có chain of custody đầy đủ.” | Cần provenance, hash, access audit, timestamp và quy trình evidence. |

## 26. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **Flow log lưu thông tin gì?** Metadata giao tiếp mạng như IP/port/protocol/time/volume/action theo nguồn và cấu hình.
2. **5-tuple gồm gì?** Source IP/port, destination IP/port và transport protocol.
3. **Flow record có bằng một connection TCP không?** Không nhất thiết; aggregation và interval có thể chia/gộp.
4. **Action ACCEPT có chứng minh HTTP 200 không?** Không; phải có application/proxy logs.
5. **Action REJECT có cho biết chắc rule ID không?** Không với mọi nguồn; cần policy/firewall-specific logs.
6. **Vì sao ingestion time khác event time?** Aggregation, delivery và processing làm logs đến muộn.
7. **Thiếu record có kết luận không có traffic không?** Không; phải kiểm tra coverage, sampling và quality.
8. **Có thể ghép hai NIC logs chỉ bằng 5-tuple không?** Không đủ; cần network scope, thời gian, NAT/resource context.
9. **Sau SNAT, flow log egress public có thể hiện IP gì?** Public NAT IP/translated port tùy điểm quan sát.
10. **Tại sao cần mapping IP lịch sử trong Kubernetes?** Pod IP được tái sử dụng; inventory hiện tại có thể gán sai.
11. **Luồng IPv6 có thể bị bỏ sót nếu chỉ thu IPv4?** Có; cần IPv6 collection/policy.
12. **Một VPN ESP record có cho biết inner HTTP URL?** Không; outer ESP metadata không chứa plaintext ứng dụng.
13. **Vì sao cần log chuyên firewall?** Để tìm policy/rule decision và một số threat indicators không có trong VPC flow logs.
14. **Số REJECT tăng có chắc là tấn công?** Không; cần baseline, scan authorization, configuration changes.
15. **Nguồn nào chứng minh ai sửa route table?** Cloud control-plane/audit logs có identity/action.
16. **Sự khác biệt giữa Cloud flow log và DNS log?** Một bên ghi luồng IP/port, bên kia ghi queries/answers theo resolver.
17. **Làm sao nhận diện data exfiltration?** Flow logs là tín hiệu, cần process/app/DLP/asset/data classification và tương quan.
18. **Có thể đo chính xác byte throughput từ sampled logs không?** Không mặc định; phải biết sampling/expansion semantics và sai số.
19. **Một cloud application với WAF có cần flow logs?** Có thể cần để quan sát flows ngoài HTTP, east-west, egress và đường bypass.
20. **Một account không còn logs sau IAM change nên làm gì?** Tạo data-quality incident, kiểm tra writer/sink và audit, ghi gaps.
21. **Làm sao tránh đếm double bytes từ hai NIC?** Phân biệt điểm quan sát, chọn accounting boundary và phương pháp dedup/correlation.
22. **Vì sao DSR gây hiện tượng missing reverse tại LB?** Return traffic đi thẳng theo thiết kế, không qua LB.
23. **Khi route blackhole có bắt buộc REJECT tại NIC đích?** Không; packet có thể chưa tới điểm đó.
24. **Có thể dùng IP threat intel để block tự động mọi flow không?** Không nên; cần tính độ tin cậy, shared IP và đánh giá tác động.

### Bài tập tổng hợp

Một tổ chức có AWS, Azure và Google Cloud, kết nối hybrid bằng VPN; microservices trên Kubernetes; database Production được phân đoạn; public API qua CDN và L7 load balancer; outbound qua NAT. SOC phát hiện **egress bytes tăng**, đội ứng dụng báo **API timeout** và cloud audit có thay đổi security policy.

Hãy:

1. Vẽ **data flow diagram** từ client → CDN → ingress → Kubernetes Pod → DB và tuyến egress tới Internet/VPN.
2. Chọn **điểm flow log, firewall logs, audit, DNS, application/EDR logs** cần thu ở từng cloud.
3. Tạo **schema chuẩn hóa** chứa 5-tuple, interface/resource ID, direction, action, time, quality/sampling và ingestion.
4. Vạch **NAT/proxy translation** để liên kết private Pod/VM với public egress IP.
5. Thiết kế truy vấn tìm **forward/reverse flows** trong một cửa sổ và nêu những trường hợp thiếu record không chứng minh drop.
6. Thiết kế **ba hypotheses** về timeout, exfiltration và IAM/logging error; nêu evidence cần cho từng giả thuyết.
7. Chọn **baseline riêng** cho CI runner, DB và public API; giải thích vì sao một threshold không hợp tất cả.
8. Đặt **ALLOW/DENY tests** phù hợp: API đúng vùng tới DB được phép, Guest/Dev tới DB bị chặn, Internet không tới management trực tiếp.
9. Mô tả retention, chain of custody, access audit và phương án khi log sink mất quyền ghi.
10. Xây dựng runbook xử lý có owner, change approval, impact/SLO và rollback an toàn.

**Tiêu chí đánh giá:** Câu trả lời đúng phải phân biệt **điểm quan sát** và **kết quả end-to-end**, tách **bằng chứng** khỏi **giả thuyết**, và chỉ khẳng định incident khi đã đối chiếu được **network, control-plane, workload và ứng dụng**.

## 27. Checklist triển khai và điều tra flow logs

- [ ] Đã xác định câu hỏi nghiệp vụ/an ninh và network **trust boundaries** cần quan sát?
- [ ] Có inventory **account/project/subscription, VPC/VNet, subnet, NIC, environment, region và owner**?
- [ ] Đã chọn nguồn log phù hợp cho **network flow, firewall, WAF, DNS, audit, NAT, LB và VPN**?
- [ ] Scope collection có bao phủ **public ingress, east-west, egress, management, transit và DR**?
- [ ] Đã kiểm tra **IPv4/IPv6**, Pod/VM identity và các ENIs/NICs liên quan?
- [ ] Hiểu định nghĩa **5-tuple, direction, action, log-status, packet/byte count** của đúng nguồn?
- [ ] Có theo dõi **aggregation interval, sampling, skipped logs và delivery lag**?
- [ ] Gắn **event time UTC, ingestion time, schema version và log source** khi chuẩn hóa?
- [ ] Không coi **một flow record là một TCP connection** hoặc đếm trùng ở nhiều NIC?
- [ ] Có historical inventory để gắn **IP đã tái sử dụng** với VM/Pod đúng thời điểm?
- [ ] Có thể tra **NAT pre/post translation, L4/L7 proxy và return path** khi điều tra?
- [ ] Đã phân biệt **ACCEPT/REJECT tại điểm log** với ứng dụng thành công/thất bại?
- [ ] Có log chuyên **firewall/rule attribution** nếu câu hỏi liên quan policy?
- [ ] Khi không thấy reverse traffic, đã kiểm tra **sampling, path asymmetry, DSR, NAT, time windows**?
- [ ] Đã đối chiếu **route, SG/NSG/ACL, WAF, VPN, CNI/NetworkPolicy** với topology?
- [ ] Đã xét **TLS/IPsec encryption** và giới hạn quan sát URL/payload?
- [ ] Có baseline theo **workload, service, port, environment, business window** và thay đổi hợp lệ?
- [ ] Detection rule có **false-positive handling, reviewer và confidence/quality labels**?
- [ ] Không tự kết luận **exfiltration, port scan hay compromise** chỉ dựa trên bytes/REJECT counts?
- [ ] Log sink có **least privilege, encryption, retention, audit, tamper resistance** phù hợp?
- [ ] Có giám sát **collection disabled, permission failures, log volume drift và parser errors**?
- [ ] Có quy trình **bảo toàn raw evidence, checksums/provenance, redaction và chain of custody** khi cần?
- [ ] Có test **ALLOW hợp lệ và DENY bắt buộc** sau thay route/segmentation/firewall?
- [ ] Có kiểm chứng tương đương khi failover **AZ/region, VPN, NAT, cloud LB và IPv6**?
- [ ] Đã ghi **unknowns/gaps** thay vì suy traffic không tồn tại từ log thiếu?
- [ ] Có runbook incident, change ID, owner, approvals và rollback an toàn?

**Kết luận:** **Flow logs là bằng chứng metadata của lưu lượng được quan sát trong một phạm vi cloud cụ thể**, không phải packet capture hay nhật ký ứng dụng. Giá trị lớn nhất nằm ở khả năng **định vị các kết nối, hướng đi, thay đổi volume và tín hiệu chính sách** rồi kết hợp chúng với **NAT/LB mappings, routing, security controls, DNS, identity, workload và audit logs**. Khi điều tra, hãy luôn hỏi **log được thu ở đâu, có sampling/aggregation không, có thiếu records không và cần bằng chứng gì để xác minh giả thuyết**. Một hệ thống flow logging tốt vừa hỗ trợ **khôi phục kết nối hợp lệ**, vừa giúp chứng minh **đường trái quyền vẫn bị chặn**, trong khi bảo vệ chính dữ liệu điều tra trước truy cập và thay đổi trái phép.
