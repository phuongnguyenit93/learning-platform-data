# NetFlow, sFlow và IPFIX: quan sát luồng mạng để vận hành và phát hiện rủi ro

**NetFlow, sFlow và IPFIX** là ba họ công nghệ giúp **thu thập telemetry về lưu lượng mạng** từ router, switch, firewall, gateway, hypervisor hoặc một số datapath phần mềm. Chúng trả lời những câu hỏi như: thiết bị nào trao đổi với thiết bị nào; dùng IP, port và giao thức gì; có bao nhiêu gói/byte; lưu lượng tăng từ đâu; có dấu hiệu quét cổng, di chuyển ngang, nghẽn liên kết hay xuất dữ liệu bất thường không?

Bài **NetFlow, sFlow và IPFIX** thuộc chương **Giám sát mạng và telemetry** của học phần **SECURITY_NETWORK_SECURITY**. Kiến thức này hỗ trợ phân tích lưu lượng, phân đoạn mạng, firewall, VPN, IDS/IPS, kiểm soát kết nối, bảo vệ DNS, mạng không dây và cloud, từ đó xây dựng **kiến trúc mạng an toàn có thể đo lường và điều tra**.

Điều quan trọng: **flow telemetry không tương đương full packet capture**. NetFlow/IPFIX thường xuất các **bản ghi tổng hợp kết nối/luồng**, còn sFlow thường **lấy mẫu gói cùng bộ đếm giao diện**. Độ phủ, độ chính xác, độ trễ và thông tin thấy được phụ thuộc **exporter, thiết bị, cấu hình, sampling, điểm quan sát, template và transport**. Không được kết luận “không có traffic” chỉ vì collector không ghi nhận flow.

**Phạm vi thực hành:** dùng lab/thiết bị được ủy quyền, địa chỉ IP minh họa thuộc dải tài liệu, dữ liệu giả và các lệnh đọc-only. Không bật mirror/capture trên hệ thống ngoài quyền hoặc đưa dữ liệu nội bộ, credential và sơ đồ mạng lên dịch vụ công cộng. Ví dụ cấu hình gắn nhãn *pseudoconfiguration* là minh họa, **không phải lệnh vendor dùng nguyên xi**.

## 1. Mục tiêu học tập

Hoàn thành bài học, người học có thể:

1. Phân biệt **packet, flow, conversation, interface counter, exporter, collector và observation point**.
2. Giải thích cơ chế **NetFlow v5, NetFlow v9, IPFIX (v10) và sFlow v5**.
3. Nêu sự khác biệt giữa **flow aggregation** và **packet sampling**, cách dùng template, counter sampling và selection metadata.
4. Đọc các trường **source/destination IP, port, protocol, bytes, packets, timestamps, interface, TCP flags, sampler và observation domain**.
5. Biết khi nào dữ liệu mang tính **đếm gần đầy đủ**, khi nào chỉ là **ước lượng có sai số**, và khi nào không thể dùng để kết luận.
6. Thiết kế pipeline **network device → exporter → collector → parser/enrichment → storage → dashboard/SIEM/NDR**.
7. Hiểu **active/inactive timeouts, cache eviction, exporter reboot, template loss, UDP drops, clock skew và duplicate records**.
8. Phân tích **NAT, asymmetric routing, overlay/VXLAN, IPv6, cloud flow logs và encrypted traffic**.
9. Áp flow telemetry vào **capacity planning, top talkers, DDoS, port scanning, east–west movement và data exfiltration investigation** mà không phóng đại bằng chứng.
10. Xây **security controls, data governance, SLI cho pipeline, ma trận kiểm thử và incident runbook**.

## 2. Flow telemetry dùng để trả lời câu hỏi nào?

Một kết nối TCP tới web API có thể trao đổi hàng nghìn packets. Nếu lưu từng packet, dung lượng và mức lộ thông tin có thể cao. **Flow record** thu gọn nhiều packet cùng đặc trưng thành một mục chứa counters/timestamps/metadata.

Ví dụ minh họa một bản ghi:

~~~text
Exporter: edge-router-a
Observation: uplink-outbound
Start UTC: 2026-11-28T08:00:00Z
End UTC:   2026-11-28T08:00:24Z
Src:       10.24.8.15:50214
Dst:       198.51.100.25:443
Protocol:  TCP (6)
Packets:   184
Octets:    156320
IfIn:      12
IfOut:     7
TCP flags: 0x1B (example aggregate bitmap)
Sampling:  none reported
~~~

**Đây là bản ghi được dựng để học**, không phải output mặc định của một exporter. Địa chỉ 198.51.100.25 thuộc dải tài liệu. TCP flags ở đây là **bitmask tổng hợp**, không mô tả thứ tự handshake; chính xác cách tổng hợp phụ thuộc exporter.

### 2.1. Ví dụ câu hỏi vận hành

- Liên kết WAN nào đang gần bão hòa? Top source/destination nào dùng nhiều bytes?
- Có đột biến outbound sau khi deploy một service không?
- Một subnet Prod có đột nhiên gửi kết nối sang Dev/Mgmt không?
- Gateway VPN đang chuyển bao nhiêu traffic theo các ứng dụng?
- Một application bị chậm do throughput, packets/second hay kết nối quá nhiều?

### 2.2. Ví dụ câu hỏi bảo mật

- Một workstation có chạm hàng trăm destination ports trong thời gian ngắn?
- Một workload gọi một địa chỉ ngoài danh sách partner đã phê duyệt?
- Có outbound bytes lớn và kéo dài đến destination chưa có owner?
- Có sự thay đổi đột ngột của DNS traffic hoặc connection attempts?
- Một security control vừa bị sửa có kéo theo thay đổi flow patterns không?

**Flow records trả lời “đường đi và hình thái traffic” tốt hơn “payload/ý nghĩa nghiệp vụ”**. Cần đối chiếu DNS, firewall decisions, TLS/proxy logs, IAM và application audit.

## 3. Packet, flow, conversation và observation point

| Thuật ngữ | Ý nghĩa | Minh họa |
|---|---|---|
| **Packet** | Đơn vị traffic tại lớp mạng với headers và có thể payload | Một IP packet TCP gửi 1.500 bytes |
| **Flow** | Nhóm packet theo key và khoảng thời gian quan sát của exporter | Src IP/port → Dst IP/port, protocol |
| **Unidirectional flow** | Một hướng của cuộc trao đổi | A:50214 → B:443 |
| **Biflow / conversation** | Hai hướng được liên kết theo phương thức thu/chuẩn hóa | A↔B với counters theo hướng nếu thiết bị hỗ trợ |
| **Exporter** | Thiết bị/phần mềm đo, tạo và gửi flow/sample records | Router, firewall, switch, software sensor |
| **Collector** | Hệ thống nhận export datagrams/messages và giải mã | Flow collector trong datacenter |
| **Observation point** | Nơi traffic được quan sát, ví dụ interface/hook | WAN uplink, vSwitch, tunnel endpoint |
| **Observation domain** | Nhóm observation points được định danh trong thiết kế export tương ứng | ID trong IPFIX/NetFlow v9 theo exporter |
| **Template** | Sơ đồ trường/định dạng cho records động | IPFIX/v9 Template ID và danh sách fields |
| **Sampling** | Chọn một phần gói/flow để đo | sFlow 1/N, sampled NetFlow/IPFIX |

### 3.1. Flow key là lựa chọn của exporter

Thường gặp **5-tuple**:
- Source IP.
- Destination IP.
- Source transport port.
- Destination transport port.
- IP protocol.

Có thể bổ sung **ingress interface, VLAN, VRF, DSCP, tunnel info, ICMP type/code, TCP flags, application ID hoặc exporter-specific context**. Hai exporters có flow keys/timeouts khác nhau có thể tạo số bản ghi khác nhau cho cùng traffic.

### 3.2. Một cuộc gọi có thể tạo hai bản ghi hướng ngược

~~~mermaid
sequenceDiagram
    participant A as Client 10.24.8.15:50214
    participant X as Observation Device
    participant B as API 198.51.100.25:443
    A->>X: TCP packets outbound
    X->>B: Client-to-server flow
    B->>X: TCP packets inbound
    X->>A: Server-to-client flow
    Note over X: Hai flow một chiều có thể export riêng
~~~

Với exporters quan sát **cả ingress lẫn egress** và nhiều thiết bị dọc đường, một packet còn có thể được tính hơn một lần nếu ta cộng các observation points. Phải chọn **điểm đo chuẩn** trước khi tính tổng traffic.

## 4. Tổng quan ba họ công nghệ

| Công nghệ | Mô hình dữ liệu | Định dạng | Điểm mạnh | Lưu ý |
|---|---|---|---|---|
| **NetFlow v5** | Tổng hợp flow với record layout cố định, truyền thống IPv4 | Fixed fields | Dễ triển khai/parse, nhiều hệ thống cũ | Không đủ linh hoạt cho nhiều thuộc tính hiện đại |
| **NetFlow v9** | Flow records theo **templates** do exporter mô tả | Template-based | Fields linh hoạt, hỗ trợ nhiều kiểu network info | Parser phải theo đúng templates, exporter/observation domain |
| **IPFIX (v10)** | Chuẩn mở dựa trên template architecture | Template-based + Information Elements | Tính chuẩn hóa và khả năng mở rộng, IPv6, vendor IEs | Có transport/template lifecycle, vẫn cần kiểm chứng implementation |
| **sFlow v5** | **Lấy mẫu gói** và **bộ đếm interface** | sFlow datagrams + sample records | Thích hợp quan sát high-speed switched networks, chi phí đo thấp tùy ASIC | Flow sample không là thống kê đủ mọi packet; độ chính xác phụ thuộc rate |

**NetFlow là tên gắn với hệ công nghệ ban đầu của Cisco**, được nhiều thiết bị triển khai dưới nhiều biến thể; **IPFIX** là chuẩn của IETF; **sFlow** là cơ chế sampling/telemetry riêng, không phải “NetFlow phiên bản nhẹ”. Một số nhà sản xuất dùng tên “flow telemetry”, “Flexible NetFlow” hoặc “J-Flow” cho sản phẩm có semantics khác nhau. Luôn xem export version và field support thực tế.

### 4.1. Dòng phát triển khái quát

~~~mermaid
flowchart LR
    V5[NetFlow v5: fixed layout] --> V9[NetFlow v9: templates]
    V9 --> IPFIX[IPFIX v10: IETF standard]
    SF[sFlow v5: packet/counter sampling] -.Khác cách đo.-> IPFIX
~~~

Mũi tên thể hiện **mối liên hệ thiết kế**, không có nghĩa mọi NetFlow v9 exporter tự tương thích byte-for-byte với IPFIX hoặc tất cả sFlow records đều chuyển đổi không mất mát thành IPFIX.

## 5. NetFlow v5: flow record cố định

NetFlow v5 là định dạng truyền thống thường có:
- IPv4 source/destination.
- Source/destination TCP/UDP ports.
- IP protocol và Type of Service/ToS theo dạng field.
- Ingress/egress interface indexes.
- Packet/byte counters.
- Start/end timestamps gắn với exporter uptime.
- TCP flags, AS numbers hoặc masks theo khả năng trường sẵn có.
- Header metadata như exporter timestamps và flow count.

### 5.1. Cách làm việc khái quát

1. Thiết bị quan sát traffic tại interface/hook được cấu hình.
2. Packet đủ điều kiện cập nhật entry trong **flow cache**.
3. Khi flow idle/active timeout hoặc eviction, thiết bị export record.
4. Collector nhận packet export và giải mã fixed layout.
5. Collector quy đổi thời gian/counters rồi đưa vào storage.

### 5.2. Giới hạn quan trọng

- **IPv4-focused fixed layout:** không biểu diễn IPv6 hoặc các thuộc tính hiện đại như một hệ template.
- Tập fields cố định khiến vendor cần extension/định dạng mới để hỗ trợ dữ liệu khác.
- UDP export nếu sử dụng có thể mất packets; không bảo đảm delivery.
- Packet/byte count có thể chịu ảnh hưởng sampling, exporter reset, cache behavior và điểm đo.
- Không ghi plaintext HTTP body, token hoặc nội dung TLS chỉ vì có flow.

### 5.3. Khi nào vẫn hữu ích?

Một hạ tầng cũ chỉ cần 5-tuple, volume và interface utilization có thể vẫn sử dụng v5. Nhưng **đối với IPv6, NAT correlation, VRF/tunnel metadata, app-level context hoặc khả năng mở rộng**, nên đánh giá v9/IPFIX hoặc sensor khác. Không bật migration mà không xét collector compatibility và capacity.

## 6. NetFlow v9: template-based flow export

NetFlow v9 tách **template** mô tả field layout khỏi **data records** chứa giá trị. Exporter có thể tạo các templates khác nhau cho nhiều loại flow, interface và routing domains.

### 6.1. Luồng template và data

~~~mermaid
sequenceDiagram
    participant E as NetFlow v9 Exporter
    participant C as Collector
    E->>C: Template FlowSet (Template ID, fields)
    E->>C: Data FlowSet (records theo Template ID)
    C-->>C: Decode theo template đã biết
    E->>C: Template refresh / restart
    E->>C: Data FlowSet mới
    Note over C: Nếu chưa có template thì chưa thể decode đúng
~~~

### 6.2. Những vấn đề cần xử lý

- Collector cần cache đúng template theo **exporter/source, domain/stream context, template ID và thời điểm hiệu lực**.
- **Template IDs có thể được tái sử dụng** cho schema khác sau restart/reconfiguration; không cache theo ID trần.
- Packet chứa data tới trước template, template bị mất hoặc collector restart → có records chưa thể decode.
- Exporter có thể gửi **Options Templates** chứa metadata sampling và context.
- Templates và vendor-specific fields không giống nhau giữa thiết bị/firmware.
- Export sequence và timestamps giúp phát hiện bất thường, nhưng cách dùng counters/sequence cần theo đúng format/version.

### 6.3. Khi nào v9 có lợi hơn v5?

Khi cần fields linh hoạt như IPv6, VRF, next-hop, flow direction hoặc vendor-specific metadata trên thiết bị hỗ trợ, v9 phù hợp hơn v5. Tuy nhiên **có template không bảo đảm mọi field đều thực sự được xuất**; phải kiểm tra cấu hình record definition và decoder.

## 7. IPFIX: Information Protocol Flow Information eXport

**IPFIX**, định danh protocol version 10, là chuẩn mở của IETF cho flow information export, thường gắn với **RFC 7011** và information model **RFC 7012** cùng các cập nhật/liên quan. Nó sử dụng **Template Sets, Data Sets và Information Elements (IEs)** để mô tả dữ liệu trong mỗi export stream.

### 7.1. Thành phần dữ liệu chính

| Thành phần | Vai trò |
|---|---|
| **Exporting Process** | Xuất IPFIX messages từ Observation Domain |
| **Collecting Process** | Nhận và giải mã IPFIX messages |
| **Observation Domain ID** | Phân biệt các observation domains của exporter |
| **Template Record** | Danh sách IE và độ dài fields của một record layout |
| **Options Template** | Metadata đi kèm như sampling, scope, exporter context |
| **Data Record** | Giá trị thuộc các field của template |
| **Information Element ID** | Định danh chuẩn của một thuộc tính IPFIX |
| **Enterprise Number** | Phân biệt vendor-specific IEs theo registry/enterprise |
| **Transport Session** | Kết nối/ngữ cảnh giao vận để chuyển messages và templates |

### 7.2. Information Elements thường gặp

- **sourceIPv4Address / destinationIPv4Address**.
- **sourceIPv6Address / destinationIPv6Address**.
- **sourceTransportPort / destinationTransportPort**.
- **protocolIdentifier**.
- **packetDeltaCount / octetDeltaCount** hoặc counters phù hợp record.
- **flowStartMilliseconds / flowEndMilliseconds** và các dạng timestamps khác.
- **ingressInterface / egressInterface**.
- **tcpControlBits**, **ipClassOfService**, **bgpSourceAsNumber**.
- IEs về **NAT, tunnel, sampling/selection** nếu exporter implementation hỗ trợ.

Tên IE/semantics cần xác minh theo **IANA IPFIX Information Element Registry và tài liệu exporter version**, không suy tất cả collectors tự hiểu mọi enterprise IE.

### 7.3. Template Set và Options Template

~~~text
IPFIX Export Message (conceptual)
  Header: version=10, export time, sequence, observationDomainId
  Template Set: templateId=300
    sourceIPv4Address (4 bytes)
    destinationIPv4Address (4 bytes)
    sourceTransportPort (2 bytes)
    destinationTransportPort (2 bytes)
    protocolIdentifier (1 byte)
    octetDeltaCount (8 bytes)
  Data Set for templateId=300
    record 1...
    record 2...
  Options Template Set (optional)
    scope and sampling metadata...
~~~

Dòng này **không phải byte-level wire format chuẩn**, chỉ cho thấy cấu trúc logic. IPFIX records cũng có thể dùng variable-length fields hoặc IEs không được ví dụ liệt kê; exporter quyết định layout.

### 7.4. Giao vận và bảo mật

IPFIX có khả năng sử dụng **SCTP, TCP, UDP** trong những cấu hình/implementation phù hợp, với những cơ chế bảo mật giao vận như TLS/DTLS tùy khả năng và tiêu chuẩn liên quan. **Không mặc định tất cả thiết bị hỗ trợ mọi transport hoặc mã hóa.**

- **UDP:** đơn giản, ít overhead nhưng không có cơ chế tự bảo đảm nhận/đúng thứ tự; template refresh và loss detection rất quan trọng.
- **TCP/SCTP:** có tính năng vận chuyển khác UDP, nhưng không loại bỏ mọi rủi ro khi exporter/collector quá tải hoặc reset.
- **TLS/DTLS được hỗ trợ:** tăng bảo mật data-in-transit và peer authentication theo kiến trúc. Có thể dùng private management network/VPN/IPsec/ACL khi thiết bị không hỗ trợ mã hóa native.
- **Transport security không tự bảo đảm semantic correctness** của counters, fields hoặc source identity nếu collector chấp nhận dữ liệu giả mạo từ đầu khác.

### 7.5. IPFIX hơn NetFlow v9 ở điểm nào?

IPFIX chuẩn hóa message, IE model, enterprise fields và các cơ chế liên quan để nhiều vendor cùng triển khai. **Không đồng nghĩa đổi port/version là đủ để migration thành công**: cần map IEs, templates, counter semantics, sampling info, parser compatibility và retention schema.

## 8. sFlow v5: sampling gói và interface counters

**sFlow** thường lấy mẫu **một số packets** tại thiết bị rồi xuất **Flow Samples**, đồng thời xuất **Counter Samples** (ví dụ interface octets, packets, drops/errors) theo chu kỳ hoặc cơ chế thu khác. **Một sFlow Flow Sample không phải flow-cache record tổng hợp toàn bộ một 5-tuple như NetFlow/IPFIX**.

### 8.1. sFlow agent hoạt động khái quát

~~~mermaid
flowchart LR
    P[Packets trên interface] --> S{Sampler 1:N}
    S -->|Sampled packets| H[Packet header sample + metadata]
    S -->|Unsampled packets| F[Forward bình thường]
    I[Interface counters] --> C[Counter Samples]
    H --> A[sFlow Agent]
    C --> A
    A --> D[sFlow Datagram UDP]
    D --> COL[sFlow Collector]
    COL --> OBS[Analytics / SIEM / Dashboards]
~~~

**Mũi tên sampled/unsampled là logic:** sFlow lấy mẫu để quan sát chứ không mặc định thay đổi forwarding behavior.

### 8.2. Hai tín hiệu cần đọc khác nhau

| Loại | Ví dụ | Cách diễn giải |
|---|---|---|
| **Flow Sample** | Phần đầu packet L2/L3/L4 đã được chọn, sampling rate, ingress/egress ifIndex, sample pool | Đại diện cho traffic được lấy mẫu, không bao phủ mọi packet |
| **Counter Sample** | ifInOctets/ifOutOctets, errors/drops hoặc interface counters tương ứng | Có thể đại diện gần đầy đủ cho interface counter tùy phần cứng, không cùng sai số với packet sampling |

### 8.3. Những trường sFlow v5 thường gặp

- Agent address/sub-agent ID.
- Datagram sequence number và agent uptime.
- Flow sample sequence number.
- Sampling rate, sample pool, dropped samples.
- Input/output interface metadata.
- Sampled packet header và original packet length theo record format.
- Interface counters và extended attributes khi exporter hỗ trợ.

**Các sampled headers có thể chứa nhiều hơn chỉ IP 5-tuple**, tùy header capture length, encapsulation và record type. Vì vậy sFlow có **rủi ro privacy cao hơn một số flow metadata exports** nếu sample gồm vùng payload ứng dụng. Không mặc định sFlow “chỉ thu địa chỉ và port”.

### 8.4. Điều sFlow làm tốt và không làm tốt

**Thường hữu ích cho:** nhìn **top talkers**, phân bố giao thức, traffic classes, link saturation khi kết hợp interface counters, xu hướng heavy hitters trong high-speed switching.

**Không đủ để kết luận một mình:** có hay không một flow rất ngắn/hiếm, đếm chính xác số kết nối, phát hiện mọi beacon nhỏ hoặc tái tạo toàn bộ TCP session. Sampling 1:1000 có thể bỏ sót phần lớn các flows ít packet.

## 9. So sánh chuyên sâu: chọn NetFlow, sFlow hay IPFIX?

| Tiêu chí | NetFlow v5 | NetFlow v9 | IPFIX | sFlow v5 |
|---|---|---|---|---|
| Đơn vị dữ liệu cốt lõi | Flow records | Template-based flow records | Standardized template-based records | Sampled packets + counters |
| Record layout | Fixed | Templates | Templates + IE registry | sFlow sample formats |
| IPv6 | Không native trong fixed v5 record | Có thể qua templates | Có IEs chuẩn | Có thể quan sát qua sampled packet header |
| Dynamic/custom fields | Hạn chế | Có theo exporter | Có standardized/enterprise IEs | Sample records/extended data theo agent |
| Sampling | Tùy exporter/config, không mặc định | Có thể dùng sampling/options | Có thể biểu diễn sampling/selection metadata | Packet sampling là trung tâm của flow samples |
| Interface counters | Không phải trọng tâm format v5 | Có thể qua option/vendor data | Có thể có IEs/options phù hợp | Counter samples là thành phần chính |
| Template lifecycle | Không | Có | Có | Không giống v9/IPFIX templates |
| Transport thường gặp | UDP | UDP | UDP/TCP/SCTP tùy hỗ trợ | UDP |
| Ước lượng heavy hitters | Dựa counters/selection behavior | Dựa counters/selection behavior | Dựa counters/selection behavior | Ước lượng từ samples và rate |
| Sự kiện rất ngắn | Có thể thành flow record nếu exporter nhìn/giữ và xuất | Tương tự | Tương tự | Có thể không được lấy mẫu |
| Security/privacy | 5-tuple/counters | Fields có thể mở rộng | IEs có thể rất chi tiết | Sample headers có thể lộ nội dung ngoài L3/L4 |
| Mức interoperable | Phù hợp legacy | Vendor semantics | Chuẩn hóa tốt hơn theo IE/schema | Phụ thuộc sFlow agent, collector |
| Điểm thích hợp | Hạ tầng IPv4 cũ | Flow metadata mở rộng | Multi-vendor flow analytics | High-speed switches và capacity monitoring |

**Không có người thắng tuyệt đối.** Cần chọn dựa trên **mục tiêu, loại thiết bị, datapath, loss/sampling, scalability, bộ mã hóa, quyền riêng tư và kỹ năng vận hành**. Một tổ chức có thể đồng thời dùng IPFIX ở WAN/firewall, sFlow ở fabric switches và cloud flow logs ở VPC.

## 10. Data model: phân biệt key, counters và enrichment

Một hệ thống phân tích nên tách **fields gốc** từ exporter và **fields được suy ra/làm giàu** sau ingest.

### 10.1. Fields gốc thường cần

| Field | Ví dụ | Tại sao cần |
|---|---|---|
| exporterId / agentAddress | edge-router-a | Biết ai quan sát |
| observationDomainId / subAgentId | 17 | Không nhầm records từ các observation contexts |
| sourceIp / destinationIp | 10.24.8.15 / 198.51.100.25 | Phân tích endpoints |
| sourcePort / destinationPort | 50214 / 443 | 5-tuple/transport |
| protocolNumber | 6 | TCP/UDP/ICMP… |
| firstSeen / lastSeen | Timestamps chuẩn UTC | Duration, timeline |
| packetCount / byteCount | 184 / 156320 | Volume/pps/bps theo semantics |
| ingressIfIndex / egressIfIndex | 12 / 7 | Routing/path attribution |
| flowDirection / tcpControlBits | Outbound / mask | Phân tích flow patterns |
| samplingMetadata | Selected 1:1000, method | Không suy đếm mẫu là exact |
| rawRecordType / templateId | IPFIX Template ID 300 | Truy vết parser/schema |
| transport / ingest timestamps | UDP, receivedAt | Phát hiện exporter/collector lag |

### 10.2. Fields được enrich nên có nguồn và thời điểm

- Geo/ASN mapping, DNS reverse lookup hoặc FQDN association.
- CMDB asset, team owner, environment, classification.
- Cloud workload/Pod UID, node và namespace (theo snapshot timeline).
- Firewall policy ID, NAT translations, VPN tunnel context.
- Threat intelligence match và confidence.
- Service/port labels hoặc application identity.

**Không gắn domain cho một IP chỉ vì DNS từng trả IP đó.** Trên CDN/shared hosting, nhiều domains dùng chung IP; reverse DNS không chứng minh HTTP hostname thật. Enrichment phải giữ **source, version/time và mức tin cậy**, tránh biến suy luận thành “ground truth”.

### 10.3. Một chiều với hai chiều

Nếu hai unidirectional flows được ghép thành conversation:
- Phải dùng canonicalized endpoint pair **và** time windows đủ phù hợp.
- NAT có thể thay 5-tuple ở giữa path.
- Asymmetric routing có thể khiến một chiều không xuất hiện.
- Hai flows có thể là hai kết nối khác nhau dùng lại port theo thời gian.
- Các exporter có thể xuất biflow counters sẵn theo implementation.

**Không tự tạo dữ liệu hướng trả lời** nếu chưa quan sát được nó.

## 11. Active timeout, inactive timeout và flow cache

**Flow cache** giúp exporter tổng hợp packets theo flow key trước khi xuất. Export không nhất thiết xảy ra ngay sau packet đầu tiên.

### 11.1. Inactive timeout

Nếu flow không có packet mới trong một khoảng cấu hình, exporter có thể **expire** entry và gửi record. Ví dụ một kết nối chỉ có vài packets có thể xuất sau khi không thấy traffic một khoảng. Nếu exporter bị reboot trước khi export hoặc cache thiếu tài nguyên, có thể mất record.

### 11.2. Active timeout

Một flow chạy liên tục, ví dụ video transfer hoặc replication, không nên ở trong cache mãi. **Active timeout** cho phép xuất các segment records định kỳ; flow vẫn đang hoạt động có thể sinh **nhiều bản ghi qua các cửa sổ**.

~~~mermaid
flowchart LR
    P[Packet stream for one long connection] --> C1[Flow cache interval A]
    C1 --> R1[Export record A]
    P --> C2[Flow cache interval B]
    C2 --> R2[Export record B]
    P --> C3[Final interval]
    C3 --> R3[Export record C]
    R1 --> S[Collector aggregate by semantics]
    R2 --> S
    R3 --> S
~~~

Không kết luận **ba bản ghi = ba TCP connections**. Phải đọc start/end timestamps, exporter context, TCP flags, active timeout và record reason (nếu có).

### 11.3. Timeout ảnh hưởng câu hỏi nào?

| Cấu hình/điều kiện | Tác động |
|---|---|
| Active timeout dài | Ít exports hơn nhưng visibility của long-lived connections chậm |
| Active timeout ngắn | Freshness tốt hơn, nhiều records/export traffic hơn |
| Inactive timeout dài | Flow ngắn xuất trễ, SIEM detection latency cao hơn |
| Inactive timeout ngắn | Entries expire nhanh, tách burst cùng 5-tuple thành nhiều records |
| Cache eviction/overflow | Có thể export sớm hoặc mất/đánh dấu records tùy thiết bị |
| Exporter reboot | Sequence reset, template loss, clock/uptime changes |
| Sampling mode thay đổi | Counters và record volume không còn cùng semantics |

Không có timeout tối ưu áp dụng mọi thiết bị; xác định theo **alert latency, throughput, exporter CPU/memory, number of active flows và collector load**.

### 11.4. Flow end reason

Một số IPFIX exporters có thể cung cấp Information Element như **flowEndReason** để chỉ timeout, end-of-flow, lack of resources hoặc các lý do khác. Nếu exporter không xuất trường này, đừng gán “TCP FIN” chỉ từ thời điểm record kết thúc. TCP flags được OR vào record cũng không thay toàn bộ event sequence.

## 12. Template IDs, Observation Domains và schema evolution

Với NetFlow v9/IPFIX, một **Template ID** không phải tên global cho cùng một record type. ID đó có nghĩa trong **ngữ cảnh exporter và transport session/observation domain** phù hợp, cùng version/time.

### 12.1. Một ví dụ thay template

~~~text
Time 10:00 - Exporter edge-a / Domain 17 / Template 300
  srcIPv4, dstIPv4, srcPort, dstPort, packetDeltaCount

Time 11:00 - Exporter config changed / Template 300 reused
  srcIPv6, dstIPv6, octetDeltaCount, flowStartMilliseconds
~~~

Nếu collector giữ cache cũ chỉ vì thấy ID 300, nó có thể decode sai hoặc từ chối messages. Vì vậy cần **template lifecycle management**: refresh, withdrawal khi áp dụng, session reset, parser versioning, kiểm tra field lengths và khả năng xuất unknown IEs nguyên vẹn.

### 12.2. Những thông tin parser cần lưu

- Sender/exporter identity và transport endpoint tin cậy.
- IPFIX observationDomainId hoặc NetFlow v9 source ID.
- Protocol version, transport session context.
- Template ID, template schema, first/last valid time.
- IANA IE identifiers và enterprise-specific IE mapping.
- Options/sampling metadata và thời điểm hiệu lực.
- Export sequence/time, collector receivedAt và parse status.
- Raw record identifier hoặc checksum/id để hỗ trợ debug khi được phép.

### 12.3. Template refresh khi dùng UDP

UDP có thể mất template packet và collector có data không decode được. Hệ thống vận hành cần **refresh policy** phù hợp thiết bị/traffic, theo dõi **unknown template records**, reset cache khi exporter reboot/session thay và không âm thầm gắn field đoán được.

### 12.4. Unknown enterprise IE

Nếu exporter gửi IE tùy biến mà collector chưa nhận ra:
1. Parse phần chuẩn và giữ raw metadata khi policy cho phép.
2. Đánh dấu field unknown và exporter model/firmware.
3. Map đúng enterprise number + IE ID + length/semantics.
4. Kiểm thử những bản ghi sau migration.
5. Không tự đặt semantic label như “threatScore” cho một field chưa xác minh.

## 13. Sampling: hiểu đúng định nghĩa trước khi nhân rộng counters

**Sampling** có thể diễn ra ở packet-level, flow-level, hardware ASIC hoặc software exporter. Hai bộ dữ liệu đều có trường rate=1000 nhưng không chắc **định nghĩa chọn mẫu giống nhau**.

### 13.1. Packet sampling

Một sFlow agent có thể chọn trung bình **1 trong N packets**. Nếu N=1000, một packet được chọn mang thông tin đại diện cho nhóm traffic lớn hơn theo thiết kế sampling. Khi đếm số sample, đây **không phải** số packet thật của kết nối.

### 13.2. Flow sampling

Một số NetFlow/IPFIX implementations chỉ chọn **một phần flows** hoặc một phần packets để tạo records. Nếu một record được sinh từ sampled packets, packet/byte counters của nó có thể là **raw sampled counters hoặc already scaled estimates** tùy exporter/field. **Không tự nhân N lần nữa** nếu firmware đã scale.

### 13.3. sFlow counter samples không giống packet sampling

Interface counter snapshots thường dựa vào số đo trực tiếp của thiết bị (ví dụ octets tổng qua interface) và có thể cho **link throughput** đáng tin hơn phép suy từ 3 sampled packets. Packet samples thì hữu ích để **phân bố traffic theo endpoints/protocols**, còn counter samples dùng để đo tổng tải và drops/errors theo thiết bị.

### 13.4. Metadata sampling nên giữ lại

- Sampling method: systematic, random hoặc phương pháp vendor.
- Sampling rate/probability và thời điểm áp dụng.
- Sampler/selector ID và observation point.
- Sample pool, dropped samples/queue overrun nếu hỗ trợ.
- Raw counters so với normalized/estimated counters.
- Confidence/coverage flags; thiết bị không report sampling là **unknown**, không tự gán unsampled.

## 14. Ước lượng từ samples và sai số

Với **independent random packet sampling** lý tưởng, xác suất chọn mỗi packet là:

\[
p=\frac{1}{N}.
\]

Nếu có **k** packets được chọn trong một nhóm và sampling rate N, ước lượng packet count đơn giản là:

\[
\widehat{P}=kN.
\]

Nếu sampled packet chứa thông tin **original packet length**, một ước lượng lượng bytes có thể là:

\[
\widehat{B}=\sum_{i=1}^{k}N L_i
\]

với **Lᵢ** là packet length cần đo và cùng semantics với thiết bị. Đây chỉ là mô hình cơ bản; hardware deterministic sampling, dropped samples, truncated headers và variation of sampling rate có thể làm sai lệch kết quả.

### 14.1. Ví dụ

Một interface sFlow sampling 1:1000 ghi được 25 packet samples thuộc một destination trong một cửa sổ.

\[
\widehat{P}=25\times1000=25{,}000\ \text{packets}.
\]

Con số 25.000 là **ước lượng**, không phải 25.000 packets đã được quan sát trực tiếp. Nếu một host chỉ tạo 3 packets, xác suất không lấy được sample của nó dưới independent Bernoulli p=0.001 xấp xỉ:

\[
(1-0.001)^3\approx 99.7\%.
\]

Vậy **một flow nhỏ không xuất hiện trong sFlow samples là bình thường**, không phải chứng cứ host đó không truyền gói.

### 14.2. Sai số tương đối

Dưới mô hình independent random sampling và **số sampled packets k đủ lớn**, sai số chuẩn tương đối của ước lượng counts thường xấp xỉ:

\[
\operatorname{RSE}\approx\frac{1}{\sqrt{k}}.
\]

Nếu chỉ có k=25 samples, RSE xấp xỉ 20%. Một khoảng gần 95% dưới giả định xấp xỉ chuẩn có thể rộng cỡ **±40%** quanh estimate; không phải bảo đảm xác suất chuẩn cho mọi thiết bị/traffic. Nếu k=1, RSE rất lớn; không dùng để phân tích chính xác long-tail flows.

### 14.3. Khi nào không nên dùng công thức nhân N?

- Samples chọn theo thuật toán deterministic có periodicity trùng loại traffic.
- Exporter đã chuẩn hóa/scale counters.
- Sample rate thay đổi giữa ports/thiết bị hoặc theo thời gian.
- sFlow collector bị drop datagrams hoặc queue overrun.
- Sampling chỉ áp dụng một hướng/interface.
- Có NAT/encapsulation khiến một packet được ghi ở nhiều hops.
- Bạn cần đếm **số kết nối khác nhau**, không phải số packets.

**Không nhân số flow records với sampling rate để mặc định ra số TCP sessions**. Flow selection probability và packet selection probability là hai thứ khác nhau; phân tích cardinality cần mô hình thống kê phù hợp.

### 14.4. Interface counters làm baseline

Để ước lượng tỷ lệ traffic theo protocol từ samples có thể so sample distribution với **total interface byte counters** trong cùng window. Nhưng phải kiểm tra packet length semantics, L2 overhead, VLAN/tunnel headers, drops, time alignment và interface identity. Không bắt dữ liệu từ hai scope khác nhau rồi coi tỷ lệ chính xác.

## 15. Kiến trúc thu nhận: exporter → collector → analytics

Một pipeline tối thiểu:

~~~mermaid
flowchart LR
    SW[Switch sFlow agent] --> IN[Collector Ingestion]
    RT[Router NetFlow v9] --> IN
    FW[Firewall IPFIX] --> IN
    IN --> PA[Parser / Template Cache]
    PA --> NO[Normalize / Quality Flags]
    NO --> EN[Inventory / DNS / NAT Enrichment]
    EN --> ST[Time-series / Columnar Storage]
    ST --> DB[Traffic Dashboards]
    ST --> SIEM[SIEM / NDR Detection]
    IN -.Ingestion metrics.-> HE[Pipeline Health Alerts]
    PA -.Parse / Template errors.-> HE
    ST -.Storage lag.-> HE
~~~

### 15.1. Ingestion

- Chỉ nhận từ **exporter sources được phê duyệt** (IP/identity/VPN/TLS nếu có).
- Phân biệt source devices, observation domains và transport sessions.
- Kiểm tra message version, length, record count và schema consistency.
- Rate-limit/queue quotas để một exporter lỗi không làm nghẽn toàn pipeline.
- Có buffer hoặc agent gần thiết bị khi product cho phép.

### 15.2. Parsing

- NetFlow v5 fixed decoder theo version.
- NetFlow v9/IPFIX template cache và options context.
- sFlow agent/subagent/datagram/sample decoder.
- Decode IPv4/IPv6, TCP/UDP/ICMP, TCP flags và tunnel fields theo schema.
- Ghi trạng thái parse errors/unknown fields; không gán defaults nguy hiểm.
- Có versioned normalization và regression tests.

### 15.3. Enrichment

- Map IP ↔ CMDB/asset/team/namespace **theo thời điểm**, không theo IP hiện tại.
- Map NAT original/translated tuples khi logs sẵn có.
- Map interface ifIndex ↔ interfaceName/VRF/zone/version.
- Đánh dấu source/destination thuộc Prod/Dev/Mgmt.
- Gắn threat-intel feeds với freshness/confidence, không coi match là bằng chứng tấn công.
- Phân biệt **observed** vs **enriched** vs **inferred** fields.

### 15.4. Analytics

- Dashboard top talkers, per-interface bps/pps, protocol mix, regional traffic.
- Security detections theo baseline, fan-out, off-hours, bytes, ports.
- Investigations theo five-tuple/time/device, NAT mapping và policy changes.
- Capacity planning theo link counters cùng sampled breakdown.

## 16. Bố trí exporter và observation point đúng chỗ

Một nơi quan sát sai có thể làm dữ liệu dù không mất packet cũng **không đại diện** cho câu hỏi đang nghiên cứu.

### 16.1. Các điểm thông dụng

| Vị trí | Hữu ích cho | Điều cần lưu ý |
|---|---|---|
| Internet edge/router | Internet ingress/egress, top talkers | NAT pre/post, asymmetric routing |
| WAN/MPLS router | Site-to-site utilization | Route changes, QoS, interface direction |
| Data-center switch | East–west sample mix, link utilization | ASIC sampling, overlays/VLAN |
| Firewall | Allowed connections, zones, NAT | Firewall log state vs exporter flow timeout |
| Load balancer/gateway | Service connection rates | Reverse proxy termination thay five-tuple |
| VPN gateway | Tunnel-level volume, remote-user paths | Inner traffic có thể nằm trong tunnel |
| Kubernetes CNI/node | Pod-to-Pod and external flows nếu supported | Pod UID/IP reuse, hostNetwork semantics |
| Cloud flow service | VPC/subnet/ENI flows | Provider format không tự là IPFIX |
| Wireless controller/AP | Client/SSID/VLAN traffic theo hỗ trợ | Roaming, tunneling, sampled vs full counters |

### 16.2. Chọn điểm đo cho Internet egress

Nếu hỏi “Prod workload nào gửi nhiều bytes ra ngoài?”, sensor ở **trước SNAT** có thể thấy private source IP, còn ở **sau SNAT** chỉ thấy public gateway IP. Có thể dùng cả hai cùng NAT translation logs để correlate, nhưng **không cộng bytes ở hai điểm** như hai traffic streams độc lập.

### 16.3. Tránh đếm kép

Một packet có thể đi qua top-of-rack, core, firewall và WAN edge; mỗi thiết bị đều có record. Khi tính tổng enterprise egress, chọn đúng **boundary và direction** thay vì cộng mọi exporters. Với ECMP, flows có thể phân bố nhiều router nên một router riêng có thể chỉ thấy một tập con.

### 16.4. Sampling theo từng interface

Một số thiết bị bật sFlow trên vài ports hoặc dùng per-interface sampling rates. Dashboard phải hiển thị **coverage map**; nếu port chưa bật sampler, không được xem traffic của nó bằng không. Interface counters có thể được collect riêng khi được hỗ trợ.

## 17. Overlay networking, encapsulation và tunnel visibility

Các lớp mạng hiện đại sử dụng **VXLAN, Geneve, GRE, MPLS, IPsec, WireGuard, SSL VPN và service mesh**. Flow exporter có thể quan sát **outer headers**, **inner headers** hoặc cả hai tùy phần cứng và nơi đặt hook.

### 17.1. Ví dụ overlay

~~~mermaid
flowchart LR
    P1[Pod A 10.244.1.5] --> N1[Node 1]
    N1 -->|VXLAN outer NodeIP-to-NodeIP| N2[Node 2]
    N2 --> P2[Pod B 10.244.2.8]
    N1 -.Inner flow telemetry if supported.-> C[Collector]
    N2 -.Outer flow telemetry if supported.-> C
~~~

Nếu chỉ quan sát outer tunnel, collector có thể thấy **node IP ↔ node IP UDP/4789** mà không biết Pod A gọi Pod B. Muốn attribution cần **inner flow records** từ CNI/node datapath hoặc mapping từ overlay metadata. Không nhận diện tất cả VXLAN UDP packets bằng ứng dụng thực dựa riêng port.

### 17.2. VPN encryption

Tại uplink bên ngoài IPsec/WireGuard, exporter có thể thấy tunnel endpoints, bytes/packets và protocol/port nhưng không biết inner destinations. Sensor phía **sau giải mã** hoặc tại workload có thể có flow metadata rõ hơn. Cần quyết định đúng vị trí và giới hạn quyền thu; không giải mã nội dung chỉ để cải thiện dashboards khi không có nhu cầu/phê duyệt.

### 17.3. Service mesh mTLS

Một sidecar/ambient datapath có thể tạo proxy telemetry bổ sung **service identity và L7 request statistics**; NetFlow/sFlow/IPFIX tại network fabric chủ yếu cho L3/L4/packet sample view. Hai lớp bổ trợ: flow metadata không tự biết user/API authorization, proxy logs không tự thấy mọi packet drops ở CNI/underlay.

## 18. NAT, proxies và bất đối xứng tuyến đường

### 18.1. NAT đổi five-tuple theo điểm đo

~~~text
BEFORE SNAT
  10.24.8.15:50214 -> 198.51.100.25:443
AFTER SNAT (illustrative)
  203.0.113.10:61002 -> 198.51.100.25:443

Different observers may export different tuples for one logical flow.
~~~

Flow metadata không tự ghép được hai tuple nếu không có NAT translation metadata/log đúng thời điểm. Một public egress IP có thể phục vụ hàng trăm Pods/users.

### 18.2. IPFIX và NAT metadata

Một số exporters/IPFIX implementations có thể xuất **NAT-related Information Elements hoặc NAT event records**. Khi hỗ trợ, cần map pre/post fields và event times, nhưng không mặc định mọi NetFlow/IPFIX source cung cấp đầy đủ NAT state. Nhiều hệ thống cần **firewall NAT logs/cloud NAT logs** riêng.

### 18.3. Asymmetric routing

Một chiều A→B có thể đi qua router X, chiều B→A đi qua router Y. Nếu chỉ quan sát X, bạn có thể thấy **outbound packets nhưng không có reply flow** dù kết nối hoạt động. Trước khi báo “scan/no response”, đối chiếu route telemetry và nhiều sensors.

### 18.4. Reverse proxy và load balancer

Một L7 proxy thường **chấm dứt kết nối client rồi tạo kết nối mới tới backend**. Hai five-tuples không là hai phần của cùng TCP session; chúng là hai sessions liên quan bởi application request. Cần trace/request ID hoặc proxy logs để correlate, không chỉ đảo src/dst.

## 19. IPv6, dual-stack và các vùng mạng nhạy cảm

**NetFlow v5 fixed records truyền thống không cung cấp địa chỉ IPv6**, trong khi NetFlow v9/IPFIX có thể diễn tả IPv6 qua template/IE, và sFlow có thể quan sát sampled IPv6 headers khi agent hỗ trợ.

### 19.1. Những trường cần giữ cho IPv6

- Full 128-bit addresses; không cắt về 32-bit.
- IPv6 source/destination prefix hoặc routing context nếu có.
- Protocol/transport ports, direction, interface.
- Các trường link-local/ULA/Global Unicast theo phân loại đúng.
- Flow label/extension-header metadata nếu exporter hỗ trợ.
- NAT64/IPv4-mapped addresses nếu có, kèm translation context.
- IPv6 firewall/routing/segmentation zones và cloud account.

### 19.2. Không lẫn address families khi aggregate

Một host dual-stack có thể tạo hai flows song song với A/AAAA khác nhau. Nếu dashboard chỉ lọc IPv4, có thể bỏ qua đường dữ liệu IPv6. Thiết kế collector/storage/query có **address-family field** và chuẩn IPv6 canonicalization.

### 19.3. Nội bộ không đồng nghĩa an toàn

RFC1918 IPv4, IPv6 ULA, link-local, cloud metadata, management endpoints và east–west Prod↔Dev traffic đều cần telemetry theo rủi ro. Một rule “chỉ giám sát public IP” dễ bỏ qua lateral movement. Khi dùng flow data để tìm SSRF/metadata, không có URL/payload nên phải đối chiếu app, DNS và IAM logs.

## 20. Cảnh báo về bảo mật và quyền riêng tư của flow exports

**Flow telemetry không hẳn là dữ liệu vô hại.** Source/destination IP, times, ports, interface names, NAT mapping, VLAN/VRF, TLS/domain extensions và sample headers có thể tiết lộ người dùng, internal topology, đối tác hoặc thậm chí một phần payload.

### 20.1. Threat model cho collector

- **Spoofed exporters:** bên lạ gửi NetFlow/sFlow/IPFIX giả vào UDP socket.
- **Record manipulation:** giả timestamps/counters hoặc template IDs làm parse sai.
- **Denial of service:** datagrams tốc độ cao, template churn, high-cardinality fields gây quá tải.
- **Eavesdropping:** UDP không mã hóa đi qua mạng không đáng tin.
- **Credential compromise:** đọc kho flow logs, query topology/nhân sự.
- **Tampering:** xóa/đổi dữ liệu hoặc tắt exporters để che hoạt động.
- **Supply chain vulnerability:** collector/parser có lỗi khi xử lý payload malformed.
- **Data over-retention:** records để quá lâu, không có quyền/hạn lưu rõ.
- **sFlow payload exposure:** truncated packet samples chứa thông tin vượt IP headers.

### 20.2. Network và transport hardening

1. Chỉ cho **known exporter sources** tới collector/ingest ports.
2. Ưu tiên **dedicated management network, VPN/IPsec hoặc authenticated/encrypted export** nếu sản phẩm hỗ trợ.
3. Không mở collector UDP listeners ra public Internet.
4. Tách ingest interfaces khỏi query/admin interfaces.
5. Rate-limit/queue resource budget và cảnh báo abusive exporters.
6. Version/patch collectors và sử dụng parser libraries có kiểm chứng.
7. Store data encrypted at rest, RBAC/ABAC, audit query access.
8. Quản lý sensitive fields/retention; không mặc định ghi full sFlow sampled payload.
9. Có independent monitoring cho collector/exporter liveness.
10. Rotate credentials/certificates và review network access sau thay đổi.

### 20.3. Không gán danh tính từ IP trần

Một IP có thể được cấp lại cho nhiều Pods/VMs hoặc NAT nhiều users. Nếu muốn quy kết tới workload, phải có **timestamp + IP allocation/Pod UID/NAT mapping + identity audit**. Reverse DNS hoặc GeoIP không phải bằng chứng chắc chắn về chủ thể.

### 20.4. Cân bằng telemetry và privacy

- Thu những fields có mục đích rõ.
- Hạn chế sampled header length của sFlow theo risk/feature requirements.
- Bỏ PII/payload không cần trước khi export hoặc lưu trữ.
- Phân quyền riêng cho SRE, SOC, network admins và incident analysts.
- Audit các truy vấn cross-tenant/cross-team.
- Đặt retention theo classification/compliance, không khẳng định một số ngày cố định cho mọi tổ chức.
- Ghi dữ liệu đúng vùng địa lý nếu có data residency requirements.

**Flow logs có thể là chứng cứ điều tra nhạy cảm.** Việc truy cập/mở rộng phạm vi thu phải theo authorization và privacy policy.

## 21. Sử dụng flow telemetry trong phát hiện an ninh

**NetFlow/IPFIX/sFlow tạo tín hiệu theo hành vi lưu lượng**, không tự xác định một gói là malware hoặc một user là attacker. Để điều tra, cần đánh giá **baseline của hệ thống, danh tính nguồn, mục đích nghiệp vụ, vị trí quan sát, sampling và tương quan với các nguồn khác**.

### 21.1. Các lớp phát hiện

| Tình huống | Feature từ flow | Nguồn cần đối chiếu |
|---|---|---|
| **Port scanning** | Nhiều destination ports/IPs, short-lived flows | Firewall deny, host EDR, change ticket |
| **Lateral movement** | East–west connectivity mới, đến management ports | Segment policy, IAM, auth logs |
| **DDoS / volumetric** | Tăng bps/pps, nhiều sources cùng một destination | Interface counters, firewall, LB, upstream ISP |
| **Data exfiltration** | Outbound bytes/ratio/duration khác baseline | Proxy/DLP, endpoint/app export audit |
| **C2 beaconing** | Các kết nối nhỏ lặp theo chu kỳ, destination lạ | DNS, endpoint detections, TI, proxy |
| **DNS tunneling nghi vấn** | Query frequency/size, DNS destination changes | DNS logs, resolver labels, entropy/rcode |
| **Misconfiguration** | Traffic tới networks không được phép, new port | IaC, ACL/NetworkPolicy changes |
| **Proxy/NAT bottleneck** | Flow churn, throughput, resets theo quan sát | Proxy queues, NAT ports, device health |
| **Unauthorized service discovery** | Fan-out connections từ user endpoint | Inventory, EDR và ticket vận hành |
| **Sudden traffic shifts** | Tăng traffic mới theo zone/ASN/region | Deployment, routing, business workload |

### 21.2. Từ feature tới alert

Một detection nên có:
- **Scope:** source zone, workload type, destination zone, direction.
- **Window:** ví dụ 5 phút, 1 giờ hoặc 1 ngày.
- **Feature:** số destinations độc lập, bytes, flows, observed ports, intervals.
- **Baseline:** so cùng time-of-day/day-of-week hoặc class service tương tự.
- **Exception:** backup, patching, vulnerability scans được phê duyệt.
- **Quality:** sample rate, percentage of exporters present, template validity, ingest lag.
- **Risk:** destination sensitivity, user/device identity, production criticality.
- **Evidence:** raw record IDs/time windows, không chỉ severity label.
- **Next step:** enrich, correlate, contain theo incident policy.

### 21.3. Không đảo chiều logic

Một IP xuất hiện trong threat intelligence có thể là shared hosting/CDN hoặc dữ liệu lỗi thời. Một flow TCP/443 tới IP đó không tự chứng minh dữ liệu đã bị đánh cắp. Ngược lại, một flow không xuất hiện do sampling hoặc exporter outage không chứng minh host an toàn. **Đánh giá cùng certainty/visibility flags**.

## 22. DDoS và lưu lượng đột biến: ưu tiên counters và tốc độ

DDoS volumetric gây bão hòa đường mạng/thiết bị. Flow/sFlow có thể gợi ý **top sources/destinations, protocols, ports và thay đổi traffic mix**.

### 22.1. Các phép tính cơ bản

Với một interface có **delta octets** trong khoảng \(\Delta t\) giây:

\[
\mathrm{bps}=\frac{8\times\Delta\mathrm{octets}}{\Delta t}
\]

Với delta packets:

\[
\mathrm{pps}=\frac{\Delta\mathrm{packets}}{\Delta t}
\]

Ví dụ trong 60 giây, interface nhận thêm 750.000.000 octets:

\[
\mathrm{bps}=\frac{8\times750{,}000{,}000}{60}
=100{,}000{,}000\ \mathrm{bps}=100\ \mathrm{Mbps}
\]

**Phải xử lý counter wrap/reset, interface errors và thời điểm lấy mẫu**. Với sFlow, dùng **Counter Samples** thích hợp để đo tổng utilization, dùng Flow Samples cho traffic attribution; không thay totals bằng lượng bytes sample nhân rate khi có counter tốt hơn.

### 22.2. Các chỉ số bổ sung

- Bytes/s và packets/s theo source/destination/service.
- Flows/s hay samples/s và **new flow rate**.
- TCP SYN-like patterns nếu exporter cung cấp **tcpControlBits**, nhưng bitmask không cho thứ tự handshake.
- UDP/ICMP traffic mix, fragments và asymmetric paths.
- Link drops, interface errors, queue occupancy, policer drops.
- Load balancer connection rejects và application 5xx.
- Sampling/collector loss khi attack volume tăng.

### 22.3. Giới hạn của flow exports trong microbursts

Active timeouts và counter sampling windows có thể **làm mượt burst ngắn**. Một burst 20 ms gây drop có thể không nổi bật trên biểu đồ trung bình 1 phút. Khi điều tra cần thiết bị có high-frequency interface/queue counters, packet telemetry hoặc network device drop diagnostics tương ứng.

### 22.4. Hành động khi nghi DDoS

Không tự kết luận DDoS chỉ từ top talkers. Đối chiếu business event, CDN, ISP upstream, firewall, load balancer và capacity. Các giải pháp mitigation như scrubbing/rate-limit/ACL phải theo playbook có thẩm quyền, được kiểm chứng về false positives và khả năng phá nhầm traffic hợp lệ.

## 23. Port scanning, fan-out và east–west movement

### 23.1. Các đặc trưng có thể quan sát

- Một source liên hệ nhiều **unique destination IPs** trong một cửa sổ ngắn.
- Một source thử nhiều **destination ports** tới một host.
- Nhiều short flows với ít bytes/packets.
- Tăng đột ngột hướng Dev→Prod, endpoint→server hoặc User VLAN→Management VLAN.
- Chuyển sang các ports quản trị khác baseline (SSH, RDP, database, remote admin).
- Dòng request từ service account bất thường tới cùng zone.

### 23.2. Ví dụ detection intent

~~~text
Window: 5 minutes
Source: one managed workstation in User VLAN
Distinct destination TCP ports: > 60
Distinct destination servers: > 20
Most flows: short and low-byte
Exceptions: approved vulnerability scanner / software inventory task
Evidence: unsampled or quality-qualified flow records + firewall events
Result: investigate; not automatically classify as malicious
~~~

Ngưỡng ở đây **chỉ minh họa**, không là rule dùng chung. Một monitoring agent, asset discovery platform hoặc deployment orchestrator hợp lệ cũng có fan-out cao. Hãy áp baseline theo **asset role, work schedule, change window và policy context**.

### 23.3. Flow sampling có thể bỏ short scans

Với sFlow 1:1000, hàng trăm kết nối mỗi kết nối chỉ có vài packets có thể không được lấy mẫu. **Không dùng sampled sFlow alone để bảo đảm phát hiện mọi scan**. Nếu bảo vệ management networks là mục tiêu quan trọng, có thể cần firewall connection logs, NetFlow/IPFIX unsampled theo năng lực, IDS/IPS hoặc host EDR.

### 23.4. Bất đối xứng tuyến khiến “không có phản hồi” chưa đủ

Nếu chỉ quan sát chiều request, bạn có thể không thấy response dù session thành công. Đừng dùng absence of reverse flow như bằng chứng quét thất bại/thành công mà chưa xem route/NAT/source/destination observation points.

## 24. Data exfiltration và C2: chỉ báo không phải kết luận

### 24.1. Những dấu hiệu outbound có thể hữu ích

- Outbound **byte volume** cao bất thường so với workload role.
- Chênh lệch bytes giữa hướng outbound và inbound đối với một destination.
- Long-lived connections tới external IP/domain không có business owner.
- Traffic xuất hiện ngoài giờ, sau credential change hoặc deploy lạ.
- Nhiều kết nối nhỏ định kỳ tới một destination ít gặp.
- Thay đổi protocol/port hoặc kết nối từ service không được phép ra Internet.

### 24.2. Exfil có thể đi qua approved destination

Một workload được allow gọi object storage/telemetry SaaS có thể gửi dữ liệu nhạy cảm tới **đúng destination hợp lệ** nếu application authorization và IAM sai. Flow records chỉ cho biết volume/direction, **không biết dữ liệu gửi đi là gì**. Cần:
- Data access audit và cloud object storage API logs.
- Proxy/SWG/CASB hoặc DLP ở điểm có visibility và quyền phù hợp.
- IAM/resource policy, tenant restrictions, token scopes.
- Egress policy và approved destinations inventory.
- Endpoint/process telemetry gắn workload và process.
- Cơ chế phân loại dữ liệu; không cần đọc payload trái quyền để suy đoán.

### 24.3. Beaconing và traffic định kỳ

Nếu một máy gửi request nhỏ mỗi 60 giây, có thể là C2 nhưng cũng có thể là health check/agent/metrics heartbeat. Sampling, active timeouts, exporter clock skew và record aggregation có thể làm **periodicity giả hoặc bỏ sót chu kỳ**.

Một phân tích thận trọng:
1. Chỉ dùng records cùng exporter/observation scope và quality tương thích.
2. Tính khoảng giữa flow start times.
3. So với baseline của ứng dụng, vendor agent và lịch scheduled jobs.
4. Correlate DNS/proxy/TLS/EDR và threat intel.
5. Tránh khẳng định “C2 confirmed” chỉ từ flow pattern.

### 24.4. DNS tunneling không thể xác minh từ IPFIX 5-tuple đơn thuần

Flow metadata có thể thấy DNS resolver/port, query volume hoặc byte sizes. Nhưng **DNS labels/query content** thường không có trong flow records chuẩn nếu exporter không cung cấp L7 extension; cần DNS query logs, resolver events hoặc packet inspection được cấp phép để đánh giá query entropy, NXDOMAIN, TXT records và unusual subdomains. Với DoH, flow thấy TCP/UDP 443 đến resolver/gateway, không tự thấy các DNS questions bên trong TLS.

## 25. Capacity planning, Top Talkers và chất lượng phân bổ

Đo băng thông và phát hiện bottleneck cần phân biệt **tổng traffic** với **phân bố các contributors**.

### 25.1. Quy trình Top Talkers

1. Chọn đúng **boundary/direction**: ví dụ WAN egress interface của cluster.
2. Lấy interface counter bps/pps để biết total.
3. Lấy flow records hoặc sFlow flow samples để phân bổ theo source/destination/service.
4. Sửa NAT/overlay attribution theo thời điểm nếu cần.
5. Phân loại **unsampled, sampled-and-weighted, unknown**.
6. Hiển thị confidence/coverage, không giả precision đồng đều.
7. So top contributors với business schedules, backups, deployments.
8. Kiểm tra multi-router ECMP và tránh đếm trùng observation points.

### 25.2. Một số loại biểu đồ

| Biểu đồ | Dữ liệu phù hợp | Mục đích |
|---|---|---|
| WAN bps/pps over time | Interface counters hoặc reliable flow aggregates | Capacity và saturation |
| Top source/destination | Flow/IPFIX counts hoặc weighted sFlow estimates | Traffic attribution |
| Protocol mix | Samples/flow data theo protocol và volume | Thay đổi giao thức |
| TCP connection churn | Unsampled connection records + firewall events | NAT/connection pressure |
| East–west heatmap | Source/destination zones theo flow | Segmentation review |
| DNS resolver usage | Flow + DNS query logs | Resolver governance |
| Failed connection trend | Firewall/proxy/TCP flags theo reliability | Troubleshooting |
| Sampling/collector drop rate | Collector/exporter self-metrics | Độ tin cậy telemetry |

### 25.3. Không nhầm octets trên wire

Một flow exporter có thể đếm **IP octets** còn interface counter đo **link-level octets** theo semantics của thiết bị. Ethernet framing, VLAN tags, encapsulation, FCS hoặc accounting boundaries có thể làm totals không bằng nhau. Không ép hai nguồn trùng tuyệt đối khi định nghĩa bytes khác.

### 25.4. Network throughput và application throughput khác nhau

Một ứng dụng gửi 10 MB response body có thể tạo network octets nhiều hơn do TLS, TCP/IP, retransmissions hoặc overlays. Ngược lại, HTTP compression làm payload khác raw resource size. Khi debug bottleneck, chọn cùng lớp đo hoặc ghi rõ sự khác biệt.

## 26. Normalized record schema và provenance

Các pipeline multi-vendor cần schema thống nhất **mà không làm mất thông tin nguyên gốc**.

### 26.1. Ví dụ JSON nội bộ

~~~json
{
  "recordId": "example-flow-record-0001",
  "eventTime": "2026-11-28T08:00:24Z",
  "receivedAt": "2026-11-28T08:00:25Z",
  "exporterId": "edge-router-a",
  "exportProtocol": "ipfix",
  "exportProtocolVersion": 10,
  "observationDomainId": 17,
  "templateId": 300,
  "sourceIp": "10.24.8.15",
  "sourcePort": 50214,
  "destinationIp": "198.51.100.25",
  "destinationPort": 443,
  "ipProtocol": 6,
  "addressFamily": "ipv4",
  "firstSeen": "2026-11-28T08:00:00Z",
  "lastSeen": "2026-11-28T08:00:24Z",
  "packetCount": 184,
  "byteCount": 156320,
  "measurementType": "flow_aggregate",
  "sampling": {
    "reported": false,
    "mode": "unknown",
    "rate": null,
    "alreadyScaled": null
  },
  "quality": {
    "templateValid": true,
    "clockChecked": true,
    "lossDetected": false,
    "completeCoverage": "unknown"
  },
  "enrichment": {
    "sourceZone": "prod",
    "destinationZone": "internet",
    "sourceIdentityConfidence": "medium"
  }
}
~~~

**Đây là schema chuẩn hóa do tài liệu minh họa, không phải IPFIX wire JSON**. Đặc biệt **reported:false không đồng nghĩa unsampled**: nếu exporter không công bố sampling, phải để mode=unknown cho tới khi xác minh cấu hình và counters.

### 26.2. Những cờ chất lượng hữu ích

| Flag | Khi nào dùng |
|---|---|
| templateValid | Decoder có đúng template/context |
| exporterClockQuality | Timestamps có khả năng lệch |
| observationPointKnown | Có mapping ifIndex/zone chính xác |
| samplingKnown | Rate/method verified |
| possibleDuplicate | Có thể là record từ nhiều sensors |
| sequenceGapDetected | Có bất thường vận chuyển/sequence theo schema |
| natMappingAvailable | Có original/translated tuple ở thời điểm |
| exporterHealthKnown | Sensor liveness và drops được theo dõi |
| expectedCoverage | Ghi source interfaces/directions thuộc scope |
| enrichmentConfidence | Phân biệt observed facts và lookup suy luận |

**Không bỏ quality flags khi chuyển dữ liệu sang SIEM**; nếu không, detection rules có thể biến ước lượng thiếu chính xác thành cảnh báo “100% chắc chắn”.

## 27. Phân tích dữ liệu bằng SQL: ví dụ có điều kiện

Giả sử một hệ thống lưu các **unsampled flow segments** trong bảng **flow_records** với các cột:

~~~text
event_time | exporter_id | observation_domain_id
src_ip | dst_ip | src_port | dst_port | ip_protocol
bytes_observed | packets_observed
sampling_mode | quality_status | observation_boundary
~~~

Tất cả examples sau chỉ là **SELECT read-only** trên bảng giả lập, không áp trực tiếp vào production database. Cần điều chỉnh field names, time data types, exporter semantics, session/window và storage engine thật.

### 27.1. Top outbound source hosts trong 15 phút

~~~sql
SELECT
    src_ip,
    SUM(bytes_observed) AS outbound_bytes,
    COUNT(*) AS records_seen
FROM flow_records
WHERE event_time >= TIMESTAMP '2026-11-28 07:45:00'
  AND event_time <  TIMESTAMP '2026-11-28 08:00:00'
  AND observation_boundary = 'prod-wan-egress'
  AND sampling_mode = 'unsampled'
  AND quality_status = 'valid'
GROUP BY src_ip
ORDER BY outbound_bytes DESC
LIMIT 20;
~~~

**Cảnh báo diễn giải:** chỉ cộng record segments nếu thiết bị xuất **delta/non-overlapping counters** phù hợp và không có duplicate records; active timeouts có thể sinh nhiều segments hợp lệ. Nếu exporter đã dùng cumulative totals hoặc observation points trùng, SUM sẽ sai.

### 27.2. Fan-out tới nhiều destination ports

~~~sql
SELECT
    src_ip,
    COUNT(DISTINCT dst_port) AS distinct_destination_ports,
    COUNT(DISTINCT dst_ip) AS distinct_destinations,
    COUNT(*) AS flow_record_count
FROM flow_records
WHERE event_time >= TIMESTAMP '2026-11-28 07:55:00'
  AND event_time <  TIMESTAMP '2026-11-28 08:00:00'
  AND observation_boundary = 'user-to-server'
  AND sampling_mode = 'unsampled'
  AND quality_status = 'valid'
  AND ip_protocol = 6
GROUP BY src_ip
HAVING COUNT(DISTINCT dst_port) > 60
ORDER BY distinct_destination_ports DESC;
~~~

**COUNT(DISTINCT dst_port)** là cardinality của ports thấy được, **không** là số kết nối TCP độc lập. Threshold 60 mang tính giả định; real policy cần baseline/authorized scanners, read permissions và incident review.

### 27.3. Lưu ý về thời gian và flow records

Nếu record có **firstSeen/lastSeen** trải qua 2 cửa sổ và được export tại end time, gộp theo **event_time** có thể dồn bytes vào thời điểm flow kết thúc, không phải thời điểm packets thực sự được gửi. Phân phối bytes theo thời gian có thể yêu cầu **interpolation hoặc time-sliced records** với assumptions rõ ràng. Không vẽ “per-second exact throughput” từ một flow 1 giờ rồi coi chính xác mỗi giây.

### 27.4. Dữ liệu sampled không dùng query giống unsampled

Với sampled records phải lưu **sampling methodology, rate, weight và confidence**; query riêng để ước lượng, phân biệt count of sampled observations với weighted packet/byte estimates. Với sFlow **interface counters**, có thể làm throughput dashboard theo delta snapshots và dùng sample distribution để gán contributors.

## 28. Ghép Flow + DNS + Firewall + VPN + IDS/IPS + IAM

Một phát hiện mạnh thường đến từ **nhiều nguồn độc lập**.

### 28.1. Một flow điều tra mạng ra ngoài

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant D as DNS Resolver
    participant F as Firewall/NAT
    participant E as Flow Exporter
    participant C as Collector/SIEM
    participant A as Application Audit
    W->>D: Resolve api.partner.example
    D-->>C: DNS query metadata
    W->>F: TCP/TLS connection
    F-->>C: Policy + NAT decision
    F->>E: Observed packets at boundary
    E-->>C: NetFlow/IPFIX/sFlow telemetry
    W->>A: Application API operation
    A-->>C: Action/identity outcome
    Note over C: Correlate time, tuples, verified identity and confidence
~~~

Mũi tên mô tả **ngữ cảnh logic**, không nhất thiết là cùng một implementation datapath. NetFlow export có thể đến sau active/inactive timeout; SIEM phải có time windows đủ cho record delay.

### 28.2. Trường liên kết

- **Flow:** src/dst IP, ports, protocol, first/last seen, exporter/ifIndex.
- **DNS:** query name, resolver, response A/AAAA, TTL, client, timestamp.
- **Firewall:** action allow/deny, rule ID, original/translated tuples.
- **Proxy:** authenticated caller, hostname, CONNECT target, URL route nếu có L7 visibility.
- **VPN:** tunnel/user/device identifier theo quyền hợp lệ.
- **Cloud IAM:** principal, resource, API action và result.
- **Application:** tenant/user/business action, request ID, data access decision.
- **IDS/IPS/NDR:** alert signature/anomaly, sensor placement và confidence.

### 28.3. Correlation không phải equality

Một DNS query có thể không dẫn tới connection; một cached DNS answer có thể tạo connection mà không có query trong window; một shared CDN IP có nhiều domains. Không biến **last DNS lookup for destination IP** thành “domain chắc chắn đã gọi”. Giữ provenance và mức tin cậy cho mọi association.

## 29. Collector reliability, template health và pipeline SLI

Một pipeline telemetry có thể **trông vẫn up** nhưng đang mất data, đổi schema hoặc ngập queue.

### 29.1. Những số liệu self-monitoring

| Chỉ số | Ý nghĩa |
|---|---|
| Exporters expected vs active | Thiết bị nào ngừng gửi |
| Datagrams/messages received | Lưu lượng ingest |
| Parse errors/malformed messages | Tính hợp lệ decoder |
| Unknown/missing templates | Khả năng giải mã v9/IPFIX |
| Sequence gaps/reset indicators | Dấu hiệu drop/reordering/restart, cần giải thích theo protocol |
| Sampler changes/rate unknown | Độ tin cậy ước lượng |
| Collector queue occupancy | Backpressure risk |
| Dropped messages/records | Mất telemetry tại collector |
| Records decoded/normalized/exported | Delivery completeness |
| Ingest lag (event vs received) | Freshness của dữ liệu |
| Storage index/query lag | Độ mới dashboard/SIEM |
| Device interface counters vs flow totals | Sanity check theo accounting semantics |
| High cardinality/IE schema churn | Resource pressure |
| TLS/auth rejection on ingest | Spoof attempts hoặc certificate misconfig |

### 29.2. Không gộp mọi sequence gap thành packet loss chính xác

Sequence semantics khác giữa NetFlow v5/v9, IPFIX và sFlow, và giữa vendors; UDP packet reordering, exporter reboot và transport session resets có thể làm số nhảy. Với **IPFIX**, sequence counter theo protocol records không đơn giản là đếm UDP datagrams. Với sFlow còn có **agent datagram/sample sequence**. Chỉ tính loss estimate sau khi phân biệt đúng version và state changes.

### 29.3. Telemetry freshness

Một security detection cần nhanh có thể bị vô hiệu nếu **active timeout 5 phút + collector queue 10 phút + SIEM ingest 5 phút**. Đo:
- Export delay từ end-of-observation tới send nếu có.
- Transport/collector received delay.
- Normalize/storage delay.
- Query/alert evaluation delay.

Nếu exporter timestamps không đáng tin do clock drift, cần ghi **collector arrival time** riêng và dùng source clock quality flags.

### 29.4. SLI gợi ý

Ví dụ một SLI ingestion completeness theo **expected exporters**:

> Trong mỗi khoảng 5 phút, ít nhất 99% exporters quan trọng có gửi heartbeat/valid telemetry theo phương thức thiết kế, và tất cả collectors đều cảnh báo khi source critical mất dữ liệu.

Đây là **SLI ví dụ**, cần thay thông số theo yêu cầu kinh doanh, exporter modes và độ trễ. **Exporter heartbeat healthy không bảo đảm mọi packet được quan sát**; phải có sampling/coverage, parse quality và gaps indicators.

### 29.5. HA và backpressure

- Phân vùng collectors theo region/source class/volume.
- Active-active/load balancing chỉ khi hỗ trợ template/session affinity phù hợp.
- Dùng queues/buffers hoặc local collectors khi tính năng cho phép.
- Rate-limit malformed/noisy exporters.
- Không tự bắn duplicate data đến hai collectors rồi cộng cả hai.
- Lưu monitoring riêng cho collector health và backend availability.
- Khôi phục template cache/session đúng sau failover.

## 30. Storage, cost, access control và retention

Flow records số lượng lớn có thể tăng nhanh; nếu biến mỗi src_ip/dst_ip/port/templateId thành label trong time-series metrics, **cardinality bùng nổ**.

### 30.1. Tách raw records và aggregated metrics

- **Raw/normalized flow records:** phù hợp columnar/time-partitioned search, kiểm soát data class và hạn lưu.
- **Aggregated metrics:** bps/pps by interface, top zone/service, exporter health; labels bounded.
- **Security events:** detections đã enrich, traceable tới record IDs/evidence.
- **Reference metadata:** exporter inventory, interface maps, NAT allocation history và parser versions.

### 30.2. Cardinality budget

Không đưa **every 5-tuple** vào nhãn Prometheus với mỗi timestamp; số series có thể rất lớn. Giữ metrics có tập labels hữu hạn như exporter_id, interface, region, direction, protocol class, zone và health status. Truy vấn chi tiết theo 5-tuple trong storage phù hợp và với quyền có giới hạn.

### 30.3. Chọn retention theo nhu cầu

| Loại dữ liệu | Nhu cầu | Rủi ro |
|---|---|---|
| Raw sFlow packet samples | Debug traffic distribution | Có thể lộ packet headers và phần dữ liệu nhạy cảm |
| Unsampled flow records | Incident timeline, connection reconstruction | Chứa hành vi của hosts/users |
| Aggregated traffic metrics | Capacity/SLO lâu dài | Mất chi tiết điều tra từng source |
| Security detections/evidence | Điều tra và compliance | Cần integrity/chain of custody |
| NAT/DNS enrichment snapshots | Attribution đúng thời điểm | Mapping nhạy cảm và có thể lỗi nếu stale |
| Collector health/audit logs | Chứng minh telemetry completeness | Có thể chứa internal topology |

Không áp một thời hạn lưu giữ “chuẩn” không có căn cứ; xác định theo classification, incident needs, compliance, privacy/data residency, storage budget và quyền xóa. Audit mọi export/query nhạy cảm.

### 30.4. Data minimization và query security

- Phân quyền theo role/tenant/team/security use case.
- Có cơ chế redact/mask các trường quá chi tiết khi không cần.
- Nếu sFlow lưu packet header length dài, đánh giá nội dung thực và giảm nếu có nguy cơ payload.
- Mã hóa at rest/in transit và quản lý keys.
- Có audit trail cho queries và exports.
- Không sao chép raw flow data tới tickets/LLM/services bên ngoài khi chưa được phê duyệt.
- Gắn schema/provenance để kết quả query không mất context.

## 31. Triển khai NetFlow/sFlow/IPFIX theo từng giai đoạn

Triển khai trên toàn mạng trong một lần có thể gây **quá tải exporter/collector**, làm đổi datapath/CPU của thiết bị, tăng volume lưu trữ hoặc làm rò topology. Cần đi theo nhu cầu quan sát và kiểm chứng tác động.

### Giai đoạn 1 — Xác định câu hỏi và phạm vi

1. Ghi business/security objectives: WAN capacity, DDoS, lateral movement, egress exfiltration hay cloud flow attribution.
2. Chọn **observation boundary** và hướng ingress/egress đúng câu hỏi.
3. Inventory routers, switches, firewalls, gateways, CNI/cloud exporters.
4. Xác định **NetFlow v5/v9, IPFIX, sFlow versions** và vendor support thực tế.
5. Xác định flows/packet samples/interface counters, sampling rates, timer semantics.
6. Tạo map interfaces/VRFs/VLANs/tunnels và NAT points.
7. Phân loại data sensitivity, authorization và destinations của exports.
8. Đo baseline device CPU/memory, line rate, drops, collector I/O.

### Giai đoạn 2 — Thiết kế pipeline

1. Chọn collector địa lý gần nguồn, có HA và network segmentation.
2. Chọn transport và mã hóa/phân đoạn management phù hợp capabilities của thiết bị.
3. Ghi source exporters/observation domains/template cache scope.
4. Tách **raw, normalized, sampled, inferred/enriched** data.
5. Quy định timestamp format, timezone UTC, clock sync, ingest time.
6. Tạo parser tests cho template refresh, vendor IE, IPv6 và malformed records.
7. Định nghĩa storage, index, retention và role-based query access.
8. Cấu hình exporter/collector self-monitoring: drops, gaps, lag, active sources.
9. Chọn canonical point cho link bps/pps và security thresholds.
10. Có rollback nếu export làm tăng tải thiết bị hoặc pipeline bottleneck.

### Giai đoạn 3 — Lab/staging và canary

1. Dùng **synthetic traffic thuộc quyền** trên mạng lab.
2. Xác nhận collector nhận đúng protocol/version/template/record fields.
3. Xác nhận sFlow flow samples khác counter samples.
4. So interface counters với flow totals trong cùng scope khi có thể.
5. Kiểm tra active/inactive timeouts và expected export delay.
6. Kiểm tra exporter restart, packet loss, template refresh, parser recovery.
7. Thử IPv4/IPv6, TCP/UDP, DNS và tunnel scenarios.
8. Đo sampling rate thực hoặc điều kiện dropped samples.
9. Kiểm tra dữ liệu sFlow sample không vượt data-minimization policy.
10. Đo ingestion/storage cost, query latency, backlog, CPU và disk.
11. Chạy positive/negative test cho telemetry loss alerts.
12. Review service ownership, false positive detections và incident paths.

### Giai đoạn 4 — Rollout production theo sóng

1. Bắt đầu từ một interface/thiết bị noncritical có owner.
2. Giám sát exporter CPU/memory, interface packet loss và collector queue.
3. Thêm devices/ports theo capacity budget, không bật mọi interface cùng lúc.
4. Đối chiếu throughput với interface counters/known traffic baseline.
5. Không đổi sampling rate giữa chừng mà quên gắn version/time vào dữ liệu.
6. Đảm bảo exporter identification không bị nhầm khi traffic qua NAT/gateway.
7. Kiểm tra records từ thiết bị mới không bị decode theo template cũ.
8. Mở rộng detection rules sau khi baseline đủ và có exceptions.
9. Có change record và xác nhận quyền xem dữ liệu theo nhóm.
10. Chỉ đánh dấu hoàn thành khi positive test, integrity và loss-monitoring đều đạt.

### Giai đoạn 5 — Vận hành và nâng cấp

- Review exporter coverage, template errors, collector lag và drop rate hằng ngày/tuần theo mục tiêu.
- Diễn tập collector restart, exporter reboot, firmware upgrade và routing failover.
- Audit vendor schema/IE changes sau update.
- Kiểm tra IP allocation/NAT mapping retention để attribution không sai theo thời gian.
- Theo dõi business traffic mùa vụ, backup jobs, patch schedules.
- Quản lý permissions, certificate rotation và network export ACL.
- Xóa stale exporters và thu hồi credentials/ports không còn dùng.
- Re-run regression tests khi cloud/CNI/mesh/firmware đổi.

## 32. Lab an toàn: quan sát dữ liệu và sức khỏe collector

Các ví dụ bên dưới là **read-only** trên **collector/thiết bị/lab được cấp quyền**. Tên service/namespace/interfaces là minh họa; thay theo môi trường thật. Không mở listener ra Internet, không bật packet capture tùy tiện và không xuất raw telemetry ngoài hệ thống được phê duyệt.

### 32.1. Kiểm tra máy collector trên Linux

~~~bash
# Đọc đồng hồ UTC, hữu ích khi kiểm tra timestamp drift
date -u

# Xem UDP sockets/listeners, không sửa cấu hình
ss -lun

# Đọc counters của interfaces được phép xem
ip -s link show

# Đọc route table, không thay đổi
ip route show
ip -6 route show
~~~

Các lệnh trên **không chứng minh collector đang giải mã records**; chúng chỉ giúp xem host/network conditions. Để xác nhận NetFlow/IPFIX/sFlow cần xem logs, parser status, templates và ingestion metrics của collector cụ thể.

### 32.2. Một số cổng thường gặp

| Giao thức | Port thường thấy trong triển khai | Lưu ý |
|---|---|---|
| NetFlow v5/v9 qua UDP | 2055, 9995 hoặc cổng được cấu hình | Không có một port bắt buộc cho mọi thiết bị |
| IPFIX | 4739 thường được dùng theo đăng ký giao thức, có các lựa chọn khác | Kiểm tra UDP/TCP/SCTP và bảo mật đúng vendor |
| sFlow v5 | UDP/6343 thường gặp | Cần ACL, source validation và drop monitoring |

**Không dùng port number đơn độc để xác định giao thức**: một listener UDP/2055 có thể nhận format khác; parser cần kiểm tra version/format. Nếu sản phẩm dùng cổng khác theo chính sách, phải ghi trong inventory.

### 32.3. Kiểm tra collector trên Kubernetes nếu được phép

~~~bash
# Tên namespace chỉ là ví dụ
kubectl get pods -n network-observability -o wide

# Tên Pod/containers minh họa, dùng đúng nguồn logs được cấp quyền
kubectl logs -n network-observability flow-collector-lab-0 \
  --since=10m --tail=100

# Đọc Services trong namespace collector
kubectl get services -n network-observability
~~~

Collector có thể không chạy trong Kubernetes; đừng suy không có Pod nghĩa không thu telemetry. Với sFlow packet samples có thể có dữ liệu nhạy cảm, **redact output trước khi ghi ticket**.

### 32.4. Kiểm tra những counters đúng ý nghĩa

Một collector tốt nên có health metrics kiểu:
- export packets/datagrams received.
- records decoded by protocol/version.
- missing template records.
- sequence gap/reboot indicators.
- sampling metadata known vs unknown.
- malformed packets/parse errors.
- dropped ingest queues, exporter not seen.
- event-time vs received-at lag.
- normalized records emitted/storage errors.

**Tên metrics API cụ thể tùy phần mềm**. Không sử dụng URL/path “/metrics” tự bịa trên production collector mà chưa xem tài liệu/cấu hình được phê duyệt.

### 32.5. Test đối chiếu bằng nguồn độc lập

Nếu một WAN interface counter tăng 1 GByte trong 1 phút nhưng NetFlow collector thấy ít hơn nhiều:
1. Có export tất cả directions/flows không?
2. Có sampling/packet counters semantics không?
3. Flow timeouts khiến data xuất trễ?
4. Có sFlow counter sample thay flow sample?
5. Có duplicate hoặc missing templates/UDP loss?
6. Có tính L2 framing, encapsulation và interface direction khác nhau?
7. Collector có lọc records/traffic ngoài phạm vi query?

**Không ép chỉnh một hệ số nhân cho đến khi số trùng**; tìm lý do đo lường khác nhau.

## 33. Ma trận kiểm thử exporter, collector và dữ liệu

Mỗi phép thử phải có **owner, lab/environment, exporter model/firmware, protocol/version, observation point/interface, sampler config, template version, timestamp, expected/actual và evidence**. Các phép thử network failure hoặc tải lớn chỉ chạy trong lab/staging hoặc production change window được duyệt.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| F01 | NetFlow v5 IPv4 record | Decode đúng fixed fields | Parsed 5-tuple/count |
| F02 | NetFlow v5 gặp IPv6 traffic | Không tuyên bố IPv6 được bao phủ | Coverage inventory |
| F03 | NetFlow v9 template trước data | Records decode đúng | Template cache status |
| F04 | NetFlow v9 data đến trước template | Chưa decode/đánh dấu, không gán nhầm field | Unknown-template metric |
| F05 | Template ID tái sử dụng schema khác sau restart | Không decode bằng template cũ | Session reset evidence |
| F06 | IPFIX v10 template-based record | IE types/lengths đúng | Parser decode test |
| F07 | IPFIX Options Template sampling info | Metadata gắn đúng period/source | Options state |
| F08 | Enterprise-specific IPFIX IE | Giữ provenance, không bịa nghĩa field | IE mapping table |
| F09 | IPFIX IPv6 src/dst | Lưu trọn 128-bit addresses | Normalized record |
| F10 | IPFIX record có timestamps khác kiểu | Quy đổi UTC/đơn vị đúng | Before/after conversion |
| F11 | sFlow v5 agent datagram | Nhận đúng agent/subagent/sequence | Datagram decode |
| F12 | sFlow Flow Sample | Packet header + sampling rate được đọc đúng | Sample record |
| F13 | sFlow Counter Sample | Counter delta dùng đúng cho throughput | Interface stats |
| F14 | sFlow sampled header dài hơn dự kiến | Không lưu payload ngoài privacy policy | Redaction validation |
| F15 | Sampling rate đổi trong lab | Weight/quality version theo thời gian | Config/event log |
| F16 | Sampling unknown | Không tự gắn unsampled | Quality flag |
| F17 | 1:1000 sampling flow rất nhỏ | Chấp nhận khả năng bị bỏ mẫu | Statistical check |
| F18 | Interface counters wrap/reset | Không sinh bps âm hoặc spike giả | Counter reset test |
| F19 | Active timeout long-lived connection | Có nhiều segments, không đếm thành sessions | Flow start/end metadata |
| F20 | Inactive timeout short flow | Record xuất sau delay hợp lý | Timelines |
| F21 | Exporter reboot | Sequence/time/template state phục hồi đúng | Reboot/reset logs |
| F22 | UDP export loss trong lab | Loss indicators và alerts xuất hiện | Collector health |
| F23 | Collector restart | Template/recovery đúng như thiết kế | Decoder health |
| F24 | Collector HA failover | Không double count/mất source quá scope | HA evidence |
| F25 | Malformed datagram từ synthetic source | Parser từ chối an toàn, không crash | Parser error logs |
| F26 | Source exporter không được duyệt | ACL/auth chặn ingest | Firewall/auth verdict |
| F27 | Exporter thiếu sync clock | Quality flag và timestamp handling | Clock monitoring |
| F28 | sFlow/NetFlow port không theo mặc định | Parser phân loại theo format thực | Listener/version logs |
| F29 | WAN ingress vs egress | Không cộng hai hướng cùng packet khi tính tổng | Observation mapping |
| F30 | Một packet qua hai routers | Không double-count cùng traffic | Boundary selection |
| F31 | ECMP split flows | Có coverage toàn bộ relevant paths | Exporter map |
| F32 | SNAT pre/post | Correlate original/translated tuple theo log | NAT audit |
| F33 | Proxy termination | Không nhầm hai TCP sessions thành một | Proxy correlation |
| F34 | Asymmetric return path | Không kết luận no reply khi sensor chưa thấy | Routing/flow diff |
| F35 | VXLAN outer-only sensor | Không tuyên bố thấy Pod inner 5-tuple | Overlay test |
| F36 | VPN encrypted outer traffic | Chỉ kỳ vọng tunnel metadata ở outer tap | Tunnel placement |
| F37 | IPv6 dual-stack egress | Có IPv6 data hoặc ghi rõ coverage gap | Flow schema |
| F38 | Cloud VPC flow log ingest | Không mặc định tương đương IPFIX wire format | Provider schema mapping |
| F39 | TCP/UDP traffic và ICMP | Decode protocol/ports/type đúng khả năng | Protocol test |
| F40 | DNS query có flow record nhưng không có L7 | Không suy ra query hostname | DNS-log correlation |
| F41 | Simulated port scanning trong lab | Detection theo baseline/quality, có false-positive review | Detections + firewall |
| F42 | Authorized vulnerability scanner chạy | Có exception/identity để tránh báo sai | Change ticket |
| F43 | Bulk outbound synthetic transfer | Volume anomaly có data confidence | Flow + app audit |
| F44 | Ứng dụng legitimate backup | Không nhầm backup với exfil | Schedule + owner |
| F45 | Data collected bằng sFlow samples | Confidence/uncertainty được hiển thị | Sampling stats |
| F46 | High-cardinality enrichment labels | Budget và alerts bảo vệ metrics | Storage/TSDB health |
| F47 | Collector ingest queue bị quá tải | Alert drops/lag, không mất âm thầm | Queue metrics |
| F48 | Malformed/sensitive telemetry field | Redaction và access controls đúng | Sanitized log test |
| F49 | Multi-region DR flow export | Policy/schema/retention/security parity | Region comparison |
| F50 | Restore historical IP→Pod mapping | Attribution theo thời điểm đúng | Inventory snapshot |

### 33.1. PASS phải dựa trên chứng cứ

Một test **không thể PASS** chỉ vì:
- UDP socket mở nhưng không có valid data records.
- Parser có records nhưng template chưa valid.
- Thấy sFlow Flow Samples mà không xác minh sampling metadata.
- Query không có flow tới management zone nhưng coverage thiếu exporter.
- Flow total khác interface counter mà chưa kiểm tra scope.
- Dữ liệu mất trong exporter/collector nhưng dashboard không cảnh báo.
- Phát hiện fan-out bị ghi “attack confirmed” mà không có review.

Đối với case có phép ước lượng sampling, ghi **confidence/assumptions** thay vì khẳng định measured exact.

## 34. Chẩn đoán lỗi thường gặp

### 34.1. Collector nhận UDP nhưng không có decoded flows

**Khả năng:** protocol version khác, data packet đến khi chưa có template, parser không hỗ trợ IE, malformed datagram, thiết bị đang xuất sFlow vào NetFlow listener.

**Kiểm tra:** exporter protocol/version, template cache, parser errors, received vs decoded counters, source addresses. Không đổi mọi devices sang một protocol trước khi xác minh.

### 34.2. NetFlow v9/IPFIX đột nhiên có fields vô nghĩa

**Khả năng:** template ID reuse, exporter restart/firmware upgrade, vendor IE mapping sai hoặc parser cache stale.

**Kiểm tra:** template scope, session reset, schema/length, observed domain, exact firmware và raw record metadata trong hệ thống được phép. Không sửa dữ liệu bằng cách gán tên field đoán được.

### 34.3. sFlow top talkers biến động mạnh

**Khả năng:** sample size nhỏ, heavy-tail traffic, sampling ratio thay đổi hoặc sampler bị drop.

**Kiểm tra:** sample counts/rate/pool, confidence, interface counters và window dài hơn. Không hạ alerts threshold dựa trên một sample ngẫu nhiên.

### 34.4. Interface bps cao nhưng flow bytes thấp

**Khả năng:** partial interface coverage, sampled NetFlow, active flow export delay, IP vs Ethernet byte accounting, UDP loss hoặc double-filter query.

**Kiểm tra:** counter semantics, directions, exporter timeouts, sample rate, parse health và time window. Đừng tự nhân một hệ số cố định.

### 34.5. Flow hiển thị toàn NAT gateway IP

**Khả năng:** observation point nằm sau SNAT. Cần pre-NAT exporter, NAT mapping logs hoặc authenticated proxy/app source metadata; không quy một IP public cho một user duy nhất.

### 34.6. Có only one-way flow records

**Khả năng:** asymmetric routing, return path qua sensor khác, direction filter, firewall drop hoặc exporter không quan sát reverse traffic.

**Kiểm tra:** interface/direction map, routes/NAT, firewall event logs và sensor coverage; không kết luận remote server không phản hồi chỉ từ một router.

### 34.7. IPv6 không xuất hiện

**Khả năng:** dùng NetFlow v5, exporter không bật IPv6 template, interface thiếu coverage, collector schema không có IPv6 field hoặc query chỉ lọc IPv4.

**Kiểm tra:** vendor feature/version, observation point, parser and database address-family support. Không khẳng định IPv6 traffic vắng mặt.

### 34.8. Dữ liệu xuất hiện chậm 10 phút

**Khả năng:** active/inactive timeout, exporter queue, collector ingestion lag, storage indexing hoặc clock skew.

**Kiểm tra:** firstSeen/lastSeen, exportTime, receivedAt, backend visibleAt; phân biệt source delay và processing lag.

### 34.9. Bị double-count traffic sau khi thêm router

**Khả năng:** sensors ở hai hops đều thấy cùng packet/flow, ECMP topology mapping sai hoặc HA duplicate export.

**Kiểm tra:** exporter, interface direction, flow tuples/timestamps, chosen boundary và dedupe strategy có provenance. Không tự xóa một trong hai sources nếu cần cho security investigations.

### 34.10. Collector restart khiến nhiều records không decode được

**Khả năng:** templates chưa được refresh, transport session context khác hoặc Options metadata mất.

**Kiểm tra:** template refresh cycle, unknown-template metrics, exporter restart behavior và collector recovery. Không cố decode record cũ với arbitrary template mới.

### 34.11. SIEM báo port scan từ monitoring server

**Khả năng:** vulnerability scan/asset inventory hợp lệ hoặc deployment automation. Kiểm tra identity, change ticket, host role, window và scan destinations; giảm false positives có kiểm soát, không tắt toàn bộ rule.

### 34.12. Nghi C2 beacon nhưng record intervals không đều

**Khả năng:** exporter active/inactive timeouts, sampling, long-lived connections, network retry, SIEM aggregation hoặc clock skew.

**Kiểm tra:** app/EDR/DNS/proxy logs, raw first/last timestamps, exporter timeouts và sampling data. Không gán C2 chỉ từ chu kỳ suy đoán.

### 34.13. Nghi sFlow chứa dữ liệu nhạy cảm

**Khả năng:** sampled packet header length bao gồm L7 payload ở một số packets. Thu hẹp access, phân loại dữ liệu, giảm header size/recorded fields theo policy và kiểm tra pipeline/storage/backup copies. Không chia sẻ raw samples để debug ngoài scope.

### 34.14. UDP drops tăng khi traffic spike

**Khả năng:** NIC kernel receive buffer, collector queue, CPU parser, route congestion, exporter burst. So exporter vs receiver counters, dropped packets, storage lag và resource usage. Dùng capacity scaling/rate budgeting/segmentation; không coi 100% records received chỉ vì exporter healthy.

## 35. Tình huống thực tế và phân tích

### Tình huống A — NetFlow v5 không hiển thị kết nối IPv6

Hệ thống dual-stack cho IPv6 outbound, nhưng collector chỉ có IPv4 v5 records.

**Phân tích:** fixed v5 record truyền thống không chứa IPv6. Cần v9/IPFIX hoặc sensor khác có IPv6 support, cùng query/storage schema. Không gọi đây là IPv6 deny.

### Tình huống B — Parser nhận Template ID 300 nhưng giải mã sai

Một firewall reboot và reuse Template ID 300 cho record layout mới.

**Phân tích:** template cache phải gắn exporter/session/observation domain/time, invalidate/refresh đúng. Không dùng ID 300 như global schema.

### Tình huống C — sFlow 1:1000 không thấy traffic scan nhỏ

Có 30 packets trong lab scan, collector không ghi sample.

**Phân tích:** sampling có khả năng bỏ sót rất cao. Dùng firewall events/IDS/unsampled flow logs khi cần chứng minh truy cập; sFlow samples phù hợp thống kê heavy traffic hơn.

### Tình huống D — sFlow Flow Samples và Counter Samples cho ra volume khác

Interface counter tăng nhiều nhưng chỉ vài sampled packets.

**Phân tích:** counter có thể đo tổng traffic; flow samples chỉ là mẫu. Không lấy số sample thô so trực tiếp octets tổng, cần đúng sample weights và byte accounting.

### Tình huống E — Một backup dài tạo 12 flow records

Một long-lived transfer xuất mỗi active timeout, SIEM tưởng 12 sessions độc lập.

**Phân tích:** segmentation theo timeout, không nhất thiết có 12 TCP handshakes. Dùng flowStart/End, TCP flags theo semantics, session correlation và application logs.

### Tình huống F — Sau chuyển collector, flow records biến mất 5 phút

IPFIX UDP data đến nhưng template mới chưa được nhận.

**Phân tích:** xem template refresh, session cache, unknown-template counts và exporter config. Không ép parser dùng stale template.

### Tình huống G — Public IP chỉ ra “một máy xuất dữ liệu”

WAN edge thấy source 203.0.113.10 gửi nhiều bytes nhưng đó là shared SNAT.

**Phân tích:** cần NAT translation log, time window, pre-NAT flow, workload identity; không quy kết cả hành vi cho một cá nhân.

### Tình huống H — Một link 10 Gbps có microburst mất gói

Biểu đồ NetFlow 1 phút bình thường nhưng switch queue drop tăng.

**Phân tích:** flow timeout/aggregation che burst; dùng high-frequency interface/queue counters và device telemetry. Không phủ nhận microburst vì bps trung bình thấp.

### Tình huống I — Trong VXLAN chỉ thấy UDP/4789

Core switch exporter thấy node-to-node tunnels, không thấy Pod inner IPs.

**Phân tích:** sensor nằm underlay. Cần CNI/host inner flow telemetry hoặc overlay metadata được phép; không gán toàn tunnel cho một app.

### Tình huống J — NetworkPolicy deny nhưng collector vẫn thấy attempt

CNI/firewall log có deny event, flow collector ở điểm trước enforcement có packets.

**Phân tích:** “flow observed” không tương đương “connection thành công”. Xác định observation placement và phối hợp deny/allow logs, TCP state.

### Tình huống K — Top talker IP chuyển sang máy khác

Một Pod IP được tái sử dụng sau rescheduling và dashboard hiện source owner sai.

**Phân tích:** enrichment phải dựa **Pod UID/CMDB allocation tại timestamp**, không map hiện tại. Cần lưu lịch sử và confidence.

### Tình huống L — SIEM báo C2 vì kết nối 60 giây

Một application heartbeat tới approved telemetry endpoint mỗi 60 giây.

**Phân tích:** periodicity là tín hiệu, không kết luận. So owner, schedule, DNS/proxy/TLS và EDR; threshold và exception có review.

### Tình huống M — Báo cáo exfil chỉ dựa outbound bytes

Một service backup gửi 100 GB theo lịch tới approved region, SIEM gắn severity critical.

**Phân tích:** flow volume chưa là exfil. Kiểm tra data classification, backup contract, app audit, IAM, time pattern và DLP. Không tắt rule, hãy bổ sung business context.

### Tình huống N — Multiple exporters cộng thành throughput gấp ba

Traffic Internet đi qua top-of-rack, core, WAN edge, mỗi thiết bị export cùng flow.

**Phân tích:** chọn canonical observation boundary hoặc có dedup/correlation đúng; không tổng mọi record theo five-tuple.

### Tình huống O — IPFIX decoded thành công nhưng sample rate unknown

Exporter bật packet sampling, nhưng collector không ingest Options metadata.

**Phân tích:** không coi byteCount là exact; lấy/đảm bảo selection metadata đúng version và ghi quality unknown cho giai đoạn thiếu. Không tự nhân rate lần hai.

### Tình huống P — Collector đang up nhưng storage chậm 20 phút

Dashboard gần hiện tại chỉ có ít traffic, network team tưởng egress giảm.

**Phân tích:** theo dõi receivedAt, storage lag, record delivery/drop metrics và interface counters độc lập. Cần alert telemetry freshness.

### Tình huống Q — Môi trường dùng sFlow captured header dài

Security team lưu sample headers dài, vô tình chứa một số bytes nội dung ứng dụng.

**Phân tích:** data governance và privacy incident. Giới hạn header length, redaction, access/retention, kiểm tra bản sao storage, không tự xem packet samples là metadata vô hại.

### Tình huống R — Disaster recovery đổi routing và mất một hướng flow

Sau failover, outbound qua router B còn inbound đi router A; chỉ một exporter được bật.

**Phân tích:** asymmetric routing và coverage drift. Kiểm tra route map, exporter inventory và HA telemetry parity; không gán no response.

## 36. Runbook khi telemetry bất thường hoặc nghi sự cố mạng

### Giai đoạn A — Xác minh độ tin cậy dữ liệu

1. Xác định **time window UTC, exporter(s), observation domain, interface và direction**.
2. Kiểm tra exporter liveness, collector received/decoded/dropped và template state.
3. Xác định NetFlow v5/v9, IPFIX hay sFlow, record type và sampling settings.
4. Kiểm tra counters đã raw hay scaled; có duplicate observation points không.
5. Kiểm tra active/inactive timeouts, exporter clock và ingest lag.
6. So với interface counters hoặc log nguồn độc lập.
7. Đánh dấu data-quality caveats trước khi dùng để ra quyết định.

### Giai đoạn B — Khoanh vùng lưu lượng

1. Xác định source/destination tuples và environment/zone.
2. Kiểm tra IPv4/IPv6, NAT, VPN, overlay, asymmetric routes.
3. Enrich theo asset/workload identity **ở đúng timestamp**.
4. Liên kết DNS answers và proxy/firewall decisions nếu có.
5. Đối chiếu với application, cloud IAM/endpoint và endpoint/EDR logs.
6. Phân biệt traffic mới, sanctioned maintenance, backup và unapproved activity.
7. Đánh giá confidentiality/integrity/availability impacts, không suy từ flow volume đơn độc.

### Giai đoạn C — Ứng phó theo rủi ro

- **Nghi scan/lateral movement:** kiểm tra firewall segmentation và nguồn identity, dùng incident-approved containment có chọn lọc.
- **Nghi exfil:** kiểm tra data access, DLP, resource IAM/token scope và approved SaaS destination; hạn chế export permissions theo playbook.
- **Nghi DDoS:** đối chiếu line-rate counters, device drops và ISP/LB, kích hoạt mitigation được phê duyệt nếu cần.
- **Mất telemetry:** khôi phục exporter/template/collector path, bật loss alerts, dùng nguồn độc lập tạm thời.
- **Parser/config drift:** rollback schema/firmware exporter nếu approved, tránh decode sai silent.
- **Privacy risk:** giới hạn quyền, ngăn thu thêm thông tin nhạy cảm và phối hợp data-incident process.

### Giai đoạn D — Phục hồi và nghiệm thu

1. Test legitimate traffic và security deny paths trong lab/change window.
2. Xác minh exporter/collector metrics hồi phục; không còn template errors bất thường.
3. So volume với interface counters theo accounting scope.
4. Xác minh sampling metadata và quality flags, không còn unknown ngoài phần được chấp nhận.
5. Xác minh multi-device, IPv6, NAT và DR coverage.
6. Kiểm tra dashboards/alerts theo baseline và false-positive handling.
7. Xem lưu lượng còn hoạt động nhưng vẫn có security controls/segmentation đúng.
8. Ghi recovery timeline, artifacts được redact và owner.

### Giai đoạn E — Hậu kiểm

- Root cause thuộc exporter, collector, template, transport, topology hay detection logic?
- Dữ liệu đã thiếu trong khoảng nào và quyết định nào bị ảnh hưởng?
- Có nhầm sampled flow với unsampled counters không?
- Có data leakage qua sampled packet headers hoặc query access không?
- Cần thay đổi sampling/timeouts, parser tests, coverage map hay storage schema gì?
- Ai sở hữu remediation, deadline và kiểm thử hồi quy?
- Có cần thông báo incident theo quy trình tổ chức không?

**Không tuyên bố điều tra hoàn tất chỉ vì dashboard sáng xanh**. Cần có đủ **provenance, quality, correlation và negative tests** để chứng minh luồng được phép/không được phép theo kiến trúc.

## 37. Những sai lầm thường gặp

1. **Coi NetFlow/IPFIX/sFlow là full PCAP.** Flow records không chứa toàn bộ packets.
2. **Coi sFlow Flow Sample là NetFlow cache record.** Cách đo khác nhau.
3. **Coi sample count là total packets.** Phải có phương pháp ước lượng phù hợp.
4. **Nhân sampling rate hai lần.** Có exporter đã scale counters.
5. **Coi sampling metadata không có nghĩa unsampled.** Thiếu dữ liệu phải đánh dấu unknown.
6. **Bỏ sFlow Counter Samples khi tính link utilization.** Packet samples không thay interface counters.
7. **Tin 1:1000 sample thấy mọi short flow.** Long tail dễ bị bỏ.
8. **Nhân số flow records với N để ra số sessions.** Không tương đương packet sampling.
9. **Dùng NetFlow v5 để kết luận IPv6 không có traffic.** v5 fixed record không chứa IPv6.
10. **Coi NetFlow v9 là IPFIX chỉ khác port.** Template/schema/protocol khác nhau.
11. **Cache Template ID không kèm exporter/context.** Decode nhầm.
12. **Không xử lý exporter restart/template reuse.** Schema corruption.
13. **Gán nghĩa ngẫu nhiên cho vendor enterprise IE.** Sai phân tích.
14. **Coi UDP export có delivery guaranteed.** Có packet loss/reordering.
15. **Bỏ qua collector dropped records/queue.** Mất visibility.
16. **Diễn giải sequence gap không theo protocol.** Không chứng minh loss count.
17. **Coi flow end là TCP connection end.** Active timeout có thể cắt long flow.
18. **Coi TCP flags aggregate thể hiện handshake đầy đủ.** Không có packet order.
19. **Nhầm flow count với request count.** HTTP keep-alive/retries/proxy làm khác.
20. **Không phân biệt observation point và direction.** Tính sai volume.
21. **Cộng nhiều exporters cùng thấy một packet.** Double counting.
22. **Bỏ qua ECMP/asymmetric routing.** Thiếu một hướng.
23. **Coi SNAT public IP là user identity.** NAT nhiều nguồn.
24. **Bỏ IP allocation history/Pod UID.** Attribution sai khi IP reuse.
25. **Tin reverse DNS là hostname đã được client yêu cầu.** Shared IP/CDN.
26. **Không xét outer/inner tunnel headers.** Overlay attribution sai.
27. **Coi encrypted VPN flow cung cấp inner endpoints.** Tùy sensor placement.
28. **Gộp IPv4 và IPv6 mà cắt IPv6 address.** Mất định danh/coverage.
29. **Không map ifIndex/VRF theo phiên bản.** Interface attribution drift.
30. **So Ethernet counter với IP octets như cùng định nghĩa.** Accounting khác.
31. **Phát hiện DDoS chỉ bằng bps trung bình 1 phút.** Bỏ microbursts.
32. **Tuyên bố C2 chỉ vì kết nối định kỳ.** Cần baseline/EDR/DNS context.
33. **Tuyên bố exfil chỉ vì outbound bytes lớn.** Backup/CDN hợp lệ có thể giống.
34. **Coi absence of flow là deny thành công.** Exporter/sampling có thể thiếu.
35. **Coi có flow nghĩa connection thành công.** Sensor có thể ở trước firewall deny.
36. **Không phân biệt source/destination zones.** Làm lệch lateral movement rules.
37. **Không bảo vệ ingest UDP.** Có thể spoof exporter hoặc DoS collector.
38. **Không mã hóa flow data khi qua mạng không tin cậy.** Lộ topology.
39. **Coi sFlow sampled headers luôn chỉ chứa metadata.** Có thể lộ payload.
40. **Cho mọi developer truy vấn toàn flow logs.** Privacy và tenant access risk.
41. **Không có retention/data classification.** Lưu quá nhiều dữ liệu nhạy cảm.
42. **Đưa mọi 5-tuple vào Prometheus labels.** Cardinality explosion.
43. **Không tách raw/enriched/inferred fields.** Biến suy đoán thành fact.
44. **Không theo dõi telemetry freshness.** Dashboard rỗng có thể do lag.
45. **Không thử failover/firmware schema changes.** Pipeline hỏng âm thầm.
46. **Chỉ làm positive tests và bỏ parser failure tests.** Không biết khi nào dữ liệu sai.
47. **Không ghi thời điểm/tham số sampling thay đổi.** So sánh lịch sử sai.
48. **Đồng nhất IPFIX với IDS/IPS.** Telemetry không mặc định chặn tấn công.

## 38. Checklist vận hành NetFlow, sFlow và IPFIX

- [ ] Xác định use case cụ thể: capacity, DDoS, east–west, exfil, troubleshooting.
- [ ] Có inventory exporters, owners, firmware, interfaces và observation domains.
- [ ] Có sơ đồ observation points và đường đi traffic/NAT/overlay.
- [ ] Biết device xuất NetFlow v5/v9, IPFIX v10 hay sFlow v5.
- [ ] Đã phân biệt **flow records**, **flow samples** và **counter samples**.
- [ ] Có map IPv4/IPv6 support và device feature limitations.
- [ ] Có danh sách template IDs/context, options và vendor IEs được hỗ trợ.
- [ ] Collector xử lý template refresh, reuse và missing template states.
- [ ] Có log/metric malformed records và unknown IE fields.
- [ ] Đã xác minh active/inactive timeouts và export delay.
- [ ] Sampling rate/method/time được lưu; unknown không mặc định là unsampled.
- [ ] Đã xác minh record counters raw hoặc already scaled.
- [ ] Không dùng packet sampling để đếm exact short flows.
- [ ] Có interface counters độc lập cho link capacity.
- [ ] Cẩn thận L2/IP bytes, VLAN/MPLS/VXLAN overhead.
- [ ] Không double-count observation points trên cùng boundary.
- [ ] Có coverage map cho ECMP, asymmetric routes và standby paths.
- [ ] NAT translation logs và IP/Pod allocation history được giữ theo thời điểm.
- [ ] IPv6 addresses lưu đủ 128-bit và có dual-stack dashboards.
- [ ] Có phân biệt outer/inner tunnel flow visibility.
- [ ] Collector chỉ nhận từ exporter sources/identities đã phê duyệt.
- [ ] Có network isolation hoặc authenticated/encrypted transport khi có thể.
- [ ] Có thiết kế rate-limit, queue/backpressure và collector HA.
- [ ] Có alerts exporter missing, queue drops, template errors, ingest lag.
- [ ] Có clock synchronization và giữ eventTime/receivedAt riêng.
- [ ] Có normalized schema version, provenance và quality flags.
- [ ] Enrichment CMDB/DNS/Geo/ASN/IAM có time/version/confidence.
- [ ] Có role-based access, audit log queries và data classification.
- [ ] sFlow sampled header length tuân privacy policy.
- [ ] Raw data và aggregate metrics được lưu đúng hệ thống.
- [ ] Không đưa every 5-tuple vào high-cardinality metric labels.
- [ ] Retention/time partitioning theo privacy/cost/compliance.
- [ ] Có baseline top talkers, zone flows và interface bps/pps.
- [ ] DDoS analysis kết hợp drops/queues và load balancer.
- [ ] Lateral movement/scan alerts có trusted identity và exception review.
- [ ] Exfil alerts được correlate với app/DLP/IAM, không chỉ bytes.
- [ ] Có DNS/proxy/firewall/VPN/IDS/IPS correlation khi cần.
- [ ] Tất cả security alerts có data-quality caveats.
- [ ] Có positive tests cho known traffic của đúng interfaces.
- [ ] Có negative tests cho template loss, UDP drop, exporter spoof.
- [ ] Có test sFlow sampling, interface counters và packet header sanitization.
- [ ] Có tests cho NAT, asymmetric routes, IPv6 và tunnel flows.
- [ ] Có test collector restart/HA/firmware upgrades.
- [ ] Có test telemetry-loss alert và ingestion freshness.
- [ ] Có process change review và rollback cho exporter settings.
- [ ] Không coi một dashboard có số liệu là bằng chứng coverage đầy đủ.

## 39. Bảng thuật ngữ và các điểm cần nhớ

| Thuật ngữ | Giải thích |
|---|---|
| **NetFlow v5** | Định dạng flow record cố định, truyền thống tập trung IPv4 |
| **NetFlow v9** | Cơ chế flow export dựa trên templates |
| **IPFIX v10** | Chuẩn IETF flow information export dùng templates và IEs |
| **Information Element (IE)** | Đơn vị field chuẩn/vendor trong IPFIX |
| **Template Set** | Mô tả field layout của IPFIX data records |
| **Observation Domain** | Nhóm observation points theo context của exporter |
| **Exporter** | Thiết bị/phần mềm đo và gửi telemetry |
| **Collector** | Hệ thống nhận, decode, lưu/forward records |
| **sFlow Flow Sample** | Mẫu packet/headers và metadata |
| **sFlow Counter Sample** | Mẫu đọc counters như interface octets/errors |
| **Sampling rate** | Xác suất/tỷ lệ chọn packet/flow theo định nghĩa exporter |
| **Sample pool** | Metadata liên quan tập packets được xem xét lấy mẫu |
| **Active timeout** | Khoảng xuất records cho flow còn hoạt động |
| **Inactive timeout** | Khoảng không có packet khiến flow có thể expire |
| **Five-tuple** | Source/destination IP, source/destination port và protocol |
| **Uniflow / Biflow** | Flow một chiều hoặc hai hướng theo mô hình exporter |
| **Sequence gap** | Bất thường sequence cần giải thích theo protocol |
| **NAT/SNAT** | Dịch source/destination IP/port qua security boundary |
| **ECMP** | Chia traffic qua nhiều equal-cost paths |
| **VXLAN/Geneve** | Overlay encapsulation làm đổi visibility outer/inner |
| **bps / pps** | Bits per second / packets per second |
| **Top talker** | Nguồn/đích đóng góp traffic lớn theo phạm vi chọn |
| **Cardinality** | Số tổ hợp labels/series khi aggregate |
| **Data provenance** | Nguồn, version, context và cách tạo fields |
| **Confidence/quality** | Đánh giá giới hạn đo/ước lượng/thiếu dữ liệu |
| **NDR** | Network Detection and Response |
| **SIEM** | Security Information and Event Management |
| **DLP** | Data Loss Prevention |
| **RSE** | Relative Standard Error của một phép ước lượng |

### 39.1. Điểm tự kiểm tra

- **NetFlow v5**: layout cố định; phù hợp legacy IPv4.
- **NetFlow v9**: template-based; collector phải xử lý template lifecycle.
- **IPFIX**: chuẩn IETF, IEs và enterprise extensibility; transport/config theo exporter.
- **sFlow**: packet samples và counter samples; không suy flow sampling là exact connection logging.
- **Coverage**: phụ thuộc interface, direction, routes, NAT, sampling và health.
- **Security**: flow cho metadata/behavior, cần DNS/firewall/identity/app/DLP để kết luận.

## 40. Tổng kết

**NetFlow, sFlow và IPFIX** giúp biến traffic khối lượng lớn thành những tín hiệu có thể phân tích về **source, destination, protocol, thời gian, volume, interface và network behavior**. Chúng hỗ trợ **capacity planning, performance troubleshooting, DDoS investigation, lateral movement detection và phát hiện outbound bất thường**. Tuy nhiên, dữ liệu chỉ đúng theo **điểm quan sát, exporter semantics, sampling, template và độ đầy đủ của pipeline**.

**NetFlow v5** hữu ích trong hạ tầng cũ với fixed IPv4 records; **NetFlow v9** đưa vào templates; **IPFIX v10** chuẩn hóa các Information Elements và khả năng mở rộng; **sFlow v5** dựa trên packet sampling và interface counters, thường phù hợp quan sát mạng tốc độ cao với chi phí lấy mẫu có thể kiểm soát. Không nên chọn công nghệ theo tên gọi mà phải xác nhận **coverage, byte accounting, IP version, sampling uncertainty, privacy và collector compatibility**.

Trong học phần **SECURITY_NETWORK_SECURITY**, flow telemetry đạt giá trị cao nhất khi kết hợp **firewall, VPN, DNS, proxy, IDS/IPS, mTLS/workload identity, cloud audit và DLP**. Khi triển khai, cần một pipeline **được bảo mật, có template/decoder chính xác, đo được loss/lag, quản lý NAT/IPv6/overlay, giữ provenance và có positive/negative tests**. Chỉ khi đó, dữ liệu mới đủ đáng tin để ra quyết định vận hành và bảo mật thay vì trở thành nguồn kết luận sai hoặc điểm mù trong kiến trúc mạng.
