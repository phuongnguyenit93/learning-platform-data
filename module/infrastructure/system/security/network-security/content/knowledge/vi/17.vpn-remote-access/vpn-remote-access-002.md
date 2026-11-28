# IPsec tunnel mode và transport mode: cấu trúc gói, bảo mật và ứng dụng VPN

## 1. IPsec bảo vệ điều gì?

**Internet Protocol Security (IPsec)** là bộ giao thức và cơ chế bảo mật ở **lớp IP**, dùng để bảo vệ các gói tin theo chính sách và các **Security Association (SA)** đã được thiết lập. Tùy cấu hình, IPsec có thể cung cấp **tính bí mật (confidentiality), toàn vẹn, xác thực nguồn gói theo SA, chống phát lại (anti-replay)** và phân tách lưu lượng cần bảo vệ khỏi lưu lượng không thuộc phạm vi. IPsec không tự thay thế việc xác thực người dùng ứng dụng, phân quyền hay an ninh endpoint.

Hai cách đóng gói quan trọng là:

- **Tunnel mode:** Bảo vệ **toàn bộ gói IP gốc** bằng cách đặt nó vào một gói IP bên ngoài mới. Thường thấy ở **site-to-site VPN**, kết nối **remote-access VPN tới security gateway**, các mạng cloud/hybrid.
- **Transport mode:** Bảo vệ **payload phía sau IP header hiện hữu** (và các cấu trúc liên quan theo ESP/AH) mà **không bọc toàn bộ gói IP gốc trong IP header mới**. Thường dùng khi chính các đầu IPsec là endpoint của kết nối hoặc khi bảo vệ một giao thức tunnel như GRE giữa hai gateway.

Trong module **SECURITY_NETWORK_SECURITY**, chủ đề này liên kết trực tiếp với kiến trúc **VPN, firewall, segmentation, IDS/IPS, xác thực kết nối, phân tích lưu lượng, cloud networking và threat modeling**. Chọn sai mode có thể khiến traffic selector không phù hợp, lộ metadata ngoài dự định, đường VPN không hoạt động hoặc thiếu kiểm soát trên đường từ gateway tới ứng dụng.

### Mục tiêu học tập

Sau bài, người học có thể:

1. Vẽ cấu trúc gói **plaintext, ESP transport, ESP tunnel và ESP qua NAT-T**.
2. Giải thích **phần nào được mã hóa/xác thực**, phần nào vẫn nhìn thấy trên đường truyền.
3. Phân biệt **IPsec mode**, **ESP/AH**, **IKEv2**, **CHILD_SA**, **route-based/policy-based VPN**.
4. Chọn mode thích hợp cho **host-to-host, gateway-to-gateway, remote access, GRE, hybrid/cloud**.
5. Phân tích **NAT-T, MTU/MSS, anti-replay, rekey, routing bất đối xứng** và firewall policies.
6. Xây dựng ma trận kiểm thử có cả traffic được phép và bị từ chối, cùng quy trình điều tra sự cố IPsec an toàn.

## 2. Trước hết phải phân biệt ba câu hỏi

| Câu hỏi | Thành phần trả lời | Ví dụ |
| --- | --- | --- |
| **Dùng cách bảo vệ gói nào?** | **ESP** hoặc **AH** (theo kiến trúc/giao thức) | ESP có mã hóa và xác thực/toàn vẹn phù hợp |
| **Bọc gói như thế nào?** | **Tunnel mode** hoặc **transport mode** | Tunnel mode thêm outer IP header |
| **Hai đầu thương lượng khóa và chính sách ra sao?** | **IKEv2** hoặc cơ chế quản lý SA được hỗ trợ | IKE_SA, CHILD_SA, key exchange và traffic selectors |

Đây là các trục **khác nhau**. “Dùng IKEv2” chưa cho biết đang dùng tunnel hay transport mode; “dùng AES-GCM” cũng chưa cho biết traffic đi qua những gateway nào. Trong thực tế, nhiều VPN dùng **ESP + tunnel mode + IKEv2**, nhưng đó là một cấu hình phổ biến chứ không phải định nghĩa của IPsec.

### 2.1. Gói IP gốc và endpoint

Giả sử một client gửi HTTPS tới server:

~~~text
IP header gốc:
  Source IP      = 10.10.10.20
  Destination IP = 10.20.20.30

Payload:
  TCP source port 51500 -> destination port 443
  TLS application data

Gói ban đầu:
  [ IP(gốc) ][ TCP ][ TLS data ]
~~~

Trong ví dụ, **TLS** đã mã hóa dữ liệu ứng dụng, còn **IPsec** có thể mã hóa thêm ở lớp IP. Hai lớp không loại trừ nhau; một site-to-site VPN có thể chở HTTPS, SSH, DNS, database traffic và những giao thức khác.

## 3. ESP là gì và trường nào hiện diện trong gói?

**Encapsulating Security Payload (ESP)** là giao thức IPsec được sử dụng rộng rãi để bảo vệ nội dung gói. ESP hỗ trợ bảo mật thông qua các **thuật toán mã hóa và/hoặc xác thực/toàn vẹn** được cấu hình theo Security Association; nhiều triển khai hiện đại dùng **authenticated encryption (AEAD)** như AES-GCM để cung cấp mã hóa và xác thực toàn vẹn theo cấu hình thích hợp.

Các thành phần thường gặp:

| Trường | Vai trò |
| --- | --- |
| **SPI (Security Parameters Index)** | Cùng địa chỉ đích, giao thức và ngữ cảnh thích hợp, giúp bên nhận tìm SA để xử lý gói |
| **Sequence Number** | Hỗ trợ kiểm tra thứ tự và cơ chế chống phát lại của SA |
| **Protected payload** | Dữ liệu được bảo vệ: transport payload hoặc toàn bộ inner IP packet tùy mode |
| **Padding / Pad Length / Next Header** | Đệm, chiều dài đệm và chỉ thị giao thức/dữ liệu tiếp theo |
| **Integrity data / authentication tag** | Hỗ trợ kiểm tra toàn vẹn/xác thực theo thuật toán đã thương lượng |

**SPI và sequence number trong ESP header không được mã hóa để bên nhận có thể chọn SA và xử lý gói.** Trong cấu hình ESP có bảo vệ toàn vẹn/xác thực, những trường thích hợp trong ESP header cũng nằm trong phạm vi xác thực; **outer IP header không được ESP bảo đảm tính toàn vẹn theo cùng cách**. Cần phân biệt *được nhìn thấy*, *được mã hóa* và *được xác thực*.

### 3.1. Hai Security Association cho hai hướng

IPsec SA truyền thống là **đơn hướng**: cần trạng thái bảo vệ outbound và inbound tương ứng. IKEv2 thông thường thiết lập một **cặp SA cho hai hướng** trong một CHILD_SA. Mỗi hướng có SPI, khóa, bộ đếm và trạng thái anti-replay phù hợp.

~~~mermaid
sequenceDiagram
    participant A as Gateway A
    participant B as Gateway B
    Note over A,B: IKEv2 xác thực và thương lượng CHILD_SA
    A->>B: ESP outbound của A (SPI theo SA nhận ở B)
    B->>B: Lookup SA + integrity + anti-replay + decrypt
    B->>A: ESP outbound của B (SPI theo SA nhận ở A)
    A->>A: Lookup SA + integrity + anti-replay + decrypt
~~~

Không tự cấu hình cùng một khóa/sequence counter cho mọi hướng nếu sản phẩm không hướng dẫn; hệ thống IKEv2 quản lý SA theo chuẩn và chính sách.

## 4. Tunnel mode: bọc toàn bộ gói IP gốc

Ở **ESP tunnel mode**, gói IP gốc được xem là **inner packet** và được đặt bên trong vùng payload được bảo vệ. Một **outer IP header mới** được thêm vào để Internet/WAN định tuyến giữa các **IPsec endpoints**, thường là hai security gateway.

~~~text
Trước IPsec:
  [ IP-inner: client -> server ][ TCP ][ TLS data ]

ESP tunnel mode (mã hóa + xác thực):
  [ IP-outer: gateway A -> gateway B ]
  [ ESP header: SPI, sequence ]
  { ENCRYPTED: [ IP-inner ][ TCP ][ TLS data ]
               [ ESP padding / trailer ] }
  [ ESP integrity/tag theo thuật toán ]

Nhìn thấy trên đường WAN:
  Outer source/destination IP, ESP header, kích thước, timing

Không thấy plaintext nếu cấu hình mã hóa đúng:
  Inner source/destination IP, TCP ports, nội dung được bọc
~~~

Dấu **ngoặc nhọn** là minh họa vùng bảo mật, không phải format byte chính xác cho mọi thuật toán. Vị trí và dạng tag, IV/nonce, padding phụ thuộc transform/thuật toán; không dùng sơ đồ như bản đặc tả nhị phân đầy đủ.

### 4.1. Đường đi site-to-site

~~~mermaid
flowchart LR
    C["Client 10.10.10.20"] --> GA["IPsec Gateway A | public 198.51.100.10"]
    GA ==>|"ESP tunnel qua WAN: outer IP 198.51.100.10 → 203.0.113.10"| GB["IPsec Gateway B | public 203.0.113.10"]
    GB --> S["Server 10.20.20.30"]
~~~

Gói từ client ban đầu mang **10.10.10.20 → 10.20.20.30**. Gateway A chọn gói thuộc policy/route cần IPsec, mã hóa inner packet và gửi giữa hai public gateway IP. Gateway B kiểm tra, giải mã và **chuyển tiếp inner packet** tới server theo routing, firewall và segmentation của mình.

**Các IP 198.51.100.0/24 và 203.0.113.0/24 là dải tài liệu TEST-NET**, dùng minh họa. Trong lab cô lập có thể thay bằng địa chỉ được cấp hợp lệ.

### 4.2. Tunnel mode che giấu và không che giấu điều gì?

- Che được **inner IP header, protocol payload và nội dung** khỏi người quan sát trên đoạn WAN được mã hóa đúng cách.
- **Không** che outer gateway IP, sự tồn tại của lưu lượng, kích thước gói, hướng, thời gian hoặc toàn bộ đặc trưng lưu lượng.
- Không đảm bảo traffic **trước gateway A** và **sau gateway B** được mã hóa; nếu LAN nội bộ không có TLS/mTLS/host IPsec, những đoạn đó có rủi ro riêng.
- Không tự hạn chế ứng dụng nào được truy cập; cần **traffic selectors, routing, firewall allow/deny, IAM, DNS policy** và xác thực đầu cuối.
- Không biến gói có inner source IP thành bằng chứng xác thực người dùng; gateway tin tưởng peer/SA trong một phạm vi, nhưng **người dùng/thiết bị bên trong** vẫn phải được quản lý.

### 4.3. Dùng khi nào?

**Tunnel mode** phù hợp khi **security gateway đại diện cho nhiều thiết bị ở phía sau**, vì các host nội bộ không cần chạy IPsec cho từng kết nối. Nó cũng phù hợp khi **remote-access client** tạo tunnel từ endpoint tới gateway và được cấp virtual inner address để truy cập tài nguyên doanh nghiệp.

Tunnel mode không đòi hỏi **hai mạng LAN khác nhau**: một client đơn lẻ vẫn có thể làm IPsec endpoint. Điều quyết định là **có inner IP packet được bọc thêm outer IP header**.

## 5. Transport mode: bảo vệ payload, giữ IP header hiện tại

Trong **ESP transport mode**, IP header hiện hữu vẫn được dùng làm IP header chuyển tiếp. ESP được đặt sau phần header IP tương ứng (theo chuẩn áp dụng cho IPv4/IPv6) và bảo vệ **upper-layer payload**, ví dụ TCP segment hoặc một phần giao thức bên trên IP.

~~~text
Trước IPsec:
  [ IP: host A -> host B ][ TCP ][ Application data ]

ESP transport mode (mã hóa + xác thực):
  [ IP: host A -> host B ]
  [ ESP header: SPI, sequence ]
  { ENCRYPTED: [ TCP ][ Application data ]
               [ ESP padding / trailer ] }
  [ ESP integrity/tag theo thuật toán ]

Trên đường truyền:
  IP nguồn/đích gốc vẫn được nhìn thấy ở ngoài ESP.
  TCP/UDP header và data được bảo vệ nếu nằm trong ESP payload.
~~~

Khác với tunnel mode, **transport mode không tạo một inner IP header hoàn chỉnh mới để mã hóa**. Do đó metadata địa chỉ IP đầu cuối hiển thị trên đường truyền (ngoại trừ những lớp tunnel/NAT khác có thể đã tồn tại và các đặc điểm của IPv6 extension headers).

### 5.1. Host-to-host transport mode

~~~mermaid
flowchart LR
    A["Host A 192.0.2.10 | IPsec endpoint"] ==>|"ESP transport mode"| B["Host B 192.0.2.20 | IPsec endpoint"]
~~~

Host A và B cùng tham gia IPsec. Bên gửi xử lý ESP trước khi phát packet lên mạng, bên nhận giải mã và đưa phần dữ liệu đã được bảo vệ cho stack giao thức tương ứng.

**Lợi ích:** Không thêm outer IP header chỉ để tạo IPsec tunnel; phù hợp cho bảo vệ trực tiếp giao tiếp giữa hai host hỗ trợ IPsec. **Giới hạn:** Quản trị identity, keying, policy, endpoint compatibility và trạng thái thiết bị có thể phức tạp khi rất nhiều host; các địa chỉ gốc vẫn là metadata bên ngoài.

### 5.2. Transport mode không chỉ giới hạn ở host-to-host

Một trường hợp hợp lệ là **GRE over IPsec transport mode** giữa hai router/gateway. GRE đã đóng gói lưu lượng nội bộ vào một packet IP giữa **GRE endpoints**; ESP transport mode có thể bảo vệ **payload GRE** của packet đó.

~~~text
Inner application packet:
  [ IP-client -> IP-server ][ TCP ][ Data ]

GRE encapsulation:
  [ IP-GRE-router-A -> IP-GRE-router-B ]
  [ GRE ][ IP-client -> IP-server ][ TCP ][ Data ]

ESP transport bảo vệ packet GRE:
  [ IP-GRE-router-A -> IP-GRE-router-B ]
  [ ESP header ]
  { ENCRYPTED: [ GRE ][ IP-client -> IP-server ][ TCP ][ Data ]
               [ ESP trailer ] }
  [ ESP integrity/tag ]
~~~

Vì **GRE đã cung cấp chức năng tunneling**, transport mode có thể bảo vệ GRE mà không cần thêm một lớp IP-in-IP từ ESP tunnel mode. Tuy nhiên, **GRE không tự mã hóa**, và không phải mọi thiết bị/hệ thống hỗ trợ cùng cách kết hợp GRE + IPsec. Tùy topology, cấu hình IPSec tunnel mode bảo vệ GRE cũng có thể tồn tại nhưng có overhead khác.

## 6. So sánh tunnel mode và transport mode

| Tiêu chí | ESP tunnel mode | ESP transport mode |
| --- | --- | --- |
| **IP header mới do mode thêm** | **Có outer IP header mới** | **Không thêm outer IP header** chỉ vì IPsec |
| **Phần được bảo vệ** | Toàn bộ **inner IP packet**, gồm inner IP header | **Payload phía sau IP header** tương ứng |
| **Địa chỉ IP hiển thị trên WAN** | Outer gateway/endpoint IP | IP nguồn/đích hiện hữu của packet được bảo vệ |
| **Inner IP header được mã hóa** | Thường **có**, khi ESP dùng encryption | Không có inner IP header được thêm bởi IPsec |
| **Vai trò phổ biến** | Security gateway ↔ gateway, remote client ↔ gateway | Host ↔ host; bảo vệ tunnel như GRE |
| **Hỗ trợ nhiều host phía sau gateway** | Tự nhiên khi bọc inner packets của nhiều host | Cần một cơ chế tunnel khác hoặc kiến trúc endpoint phù hợp |
| **Chi phí header** | ESP và outer IP (cộng NAT-T nếu có) | ESP (cộng NAT-T nếu có); thường ít overhead IPsec hơn |
| **Che inner subnet** | Có thể che inner source/destination trong đoạn được mã hóa | IP nguồn/đích packet đang bảo vệ vẫn nhìn thấy |
| **NAT, route, firewall** | Phải kiểm soát cả outer và inner flows | Phải xem endpoint/header gốc và NAT-T theo hỗ trợ |
| **Bảo vệ ứng dụng** | Bảo vệ đoạn từ IPsec endpoint A tới B | Bảo vệ đoạn từ IPsec endpoint A tới B |

Không nói “transport luôn tốt hơn vì nhanh hơn”: overhead là **một** yếu tố. Throughput, latency còn phụ thuộc thuật toán, CPU/crypto offload, MTU, NIC, packet size, packet rate và việc mode có đáp ứng đúng trust boundary hay không.

### 6.1. Hai câu hỏi quyết định nhanh

1. **Hai IPsec endpoints có trực tiếp là hai IP endpoints cần bảo vệ không?** Nếu có, transport mode là một ứng viên; cần xem NAT, identity và thiết bị hỗ trợ.
2. **Cần bảo vệ các mạng/host nằm phía sau security gateway hoặc che toàn bộ inner IP packet?** Tunnel mode thường là lựa chọn tự nhiên.

Nếu đang dùng **GRE/L2TP hoặc một tunnel khác**, hãy xét lớp encapsulation đã có; không tự áp dụng quy tắc “gateway thì luôn tunnel mode” bất kể giao thức.

## 7. ESP và AH khác mode như thế nào?

**Authentication Header (AH)** là một giao thức IPsec khác ESP. AH cung cấp **xác thực nguồn gói/toàn vẹn và cơ chế chống phát lại** theo SA; **AH không cung cấp mã hóa bảo mật nội dung**. AH còn bảo vệ một số trường IP header được xác định là bất biến hoặc có thể dự đoán trong quá trình truyền, nên thường **không tương thích thuận lợi với NAT** làm thay đổi địa chỉ IP.

| Đặc điểm | ESP | AH |
| --- | --- | --- |
| Confidentiality | Có thể có khi chọn thuật toán encryption | **Không** |
| Integrity/authentication | Có theo thuật toán và cấu hình được chọn | Là khả năng cốt lõi |
| Anti-replay | Có khi được cấu hình/kích hoạt phù hợp | Có khi được cấu hình/kích hoạt phù hợp |
| Tunnel/transport mode | **Cả hai** | **Cả hai** |
| NAT traversal | Thường dùng **ESP over UDP NAT-T** | Không có NAT-T phổ biến tương đương cho AH; NAT dễ phá kiểm tra |
| Sử dụng VPN thực tế | Rất phổ biến | Ít gặp hơn trong các triển khai VPN hiện đại |

**Mode ≠ protocol.** Có thể nói “ESP tunnel” hoặc “ESP transport”; cũng có AH tunnel/transport. Trong thực tế, hãy ưu tiên các cấu hình ESP/IKEv2 với thuật toán hiện đại được chính sách và nền tảng hỗ trợ, thay vì giả định AH là bắt buộc để có toàn vẹn.

### 7.1. ESP có thể không mã hóa không?

Trong đặc tả có những cách dùng ESP chỉ bảo vệ toàn vẹn mà không mã hóa payload; vì vậy phát biểu **“thấy ESP là chắc chắn payload bí mật”** là quá mức. Với VPN cần bảo mật nội dung, phải kiểm tra **transform/SA thực tế đã thương lượng** và chính sách yêu cầu encryption, không chỉ kiểm tra “tunnel UP”.

## 8. Sơ đồ tổng quan các lớp đóng gói

~~~mermaid
flowchart TD
    P["Gói gốc: IP-inner | TCP/UDP | App"] --> M{"Chọn ESP mode"}
    M -- "Tunnel" --> T["IP-outer | ESP | encrypted IP-inner + payload | tag"]
    M -- "Transport" --> R["IP-hiện-hữu | ESP | encrypted transport payload | tag"]
    T --> W["WAN: route theo outer IP"]
    R --> V["WAN: route theo IP header hiện hữu"]
    W --> D["Peer IPsec: lookup SA, anti-replay, decrypt"]
    V --> D
    D --> F["Policy + routing + firewall + ứng dụng"]
~~~

Với **transport mode bảo vệ GRE**, IP header hiện hữu ở nhánh transport có thể chính là header được GRE tạo ra, còn gói người dùng nằm trong GRE. Đừng nhầm khái niệm **IP header hiện hữu tại thời điểm IPsec áp dụng** với địa chỉ ứng dụng luôn cố định trong mọi kiến trúc.

## 9. IKEv2 thiết lập bảo mật cho tunnel/transport ra sao?

**Internet Key Exchange version 2 (IKEv2)** là giao thức thương lượng và quản lý Security Association cho IPsec: xác thực peers theo cấu hình, trao đổi khóa, chọn thuật toán/chính sách, duy trì và thay thế SA. IKEv2 không phải “tầng dữ liệu tunnel mode”; **ESP** mới xử lý phần lớn traffic dữ liệu được bảo vệ.

Ở mức khái niệm, IKEv2 có hai đối tượng:

- **IKE_SA:** Quan hệ bảo mật để bảo vệ thông điệp điều khiển IKE giữa hai peers, gồm khóa và trạng thái của IKE.
- **CHILD_SA:** Tập SA dùng bảo vệ **luồng dữ liệu** qua IPsec (thông thường một SA mỗi chiều), gắn với transform và **Traffic Selectors (TS)**.

### 9.1. Trình tự thương lượng khái quát

~~~mermaid
sequenceDiagram
    participant A as IPsec Peer A
    participant B as IPsec Peer B
    A->>B: IKE_SA_INIT: proposals, nonces, key exchange
    B->>A: IKE_SA_INIT: selected proposal, nonces, key exchange
    A->>B: IKE_AUTH: identity/authentication, CHILD_SA proposal, TS
    B->>A: IKE_AUTH: authentication, CHILD_SA result, TS
    Note over A,B: IKE_SA và CHILD_SA theo thương lượng hợp lệ
    A->>B: ESP protected data (SA A→B)
    B->>A: ESP protected data (SA B→A)
    Note over A,B: Rekey/liveness/recovery theo khả năng và cấu hình
~~~

Sơ đồ không liệt kê mọi payload, thông điệp bổ sung, yêu cầu EAP, tình huống NAT hoặc trường hợp đàm phán thất bại. Trong IKEv2, một **IKE_SA** có thể quản lý **nhiều CHILD_SA** tùy thiết kế. **Tunnel mode thường là mặc định được thương lượng theo chuẩn IKEv2**, trong khi transport mode có cơ chế yêu cầu/đồng thuận của hai peers; không giả định một peer có thể tự ép transport mode khi peer kia không hỗ trợ.

### 9.2. Những tham số cần đồng thuận

| Tham số | Vai trò | Lỗi phổ biến |
| --- | --- | --- |
| Peer address/identity | Kết nối đúng đối tác, phân biệt IP giao tiếp với identity được chứng thực | Peer IP đúng nhưng certificate/ID không khớp |
| Authentication | PSK, chứng chỉ hoặc phương thức được hỗ trợ | PSK yếu, certificate hết hạn, trust store sai |
| IKE algorithms | Bảo vệ kênh điều khiển IKE | Hai bên không có proposal chung |
| Key exchange group | Thương lượng bí mật phiên theo nhóm được phê duyệt | Peer chỉ hỗ trợ nhóm yếu/không tương thích |
| ESP algorithms | Confidentiality/integrity cho data plane | Một bên yêu cầu AEAD, bên kia chỉ cấu hình transform khác |
| **Mode** | Tunnel hay transport cho data SA | Hai bên không thống nhất mode/đóng gói |
| Traffic selectors | Dải IP/giao thức/port thuộc CHILD_SA | Selector không giao nhau hoặc thiếu prefix |
| Lifetime/rekey | Thời gian thay SA, tránh gián đoạn khi hết hạn | Rekey thất bại, thiết bị giữ SA cũ |
| NAT-T/UDP encapsulation | Chuyển ESP qua NAT khi cần và được hỗ trợ | Chặn UDP 4500 hoặc NAT làm mất mapping |
| Route/forwarding | Gửi đúng traffic vào đường IPsec | CHILD_SA UP nhưng application traffic không đi vào SA |

**IKE authentication không chứng minh mỗi user nằm phía sau gateway đã được xác thực riêng.** Một site-to-site gateway có thể xác thực tổ chức/peer, còn quyền của host và user vẫn phải do firewall/IAM/NAC/mTLS hoặc lớp khác bảo vệ.

### 9.3. CHILD_SA rekey, liveness và tính sẵn sàng

Rekey đổi khóa/SA theo chu kỳ hoặc chính sách. Trong giai đoạn chuyển, hai peers phải xử lý các SA cũ/mới theo protocol và giới hạn thiết bị. Nếu quản lý lifetime, retransmission, đồng hồ, peer reachability hoặc NAT mapping không đúng, có thể thấy **VPN vẫn kết nối nhưng phiên dữ liệu gián đoạn**.

**Perfect Forward Secrecy (PFS)** thường được thảo luận ở key exchange: việc dùng trao đổi khóa tạm thời phù hợp làm giảm tác động khi lộ khóa dài hạn về sau, theo threat model và đặc tính thuật toán. Cần phân biệt khả năng bảo vệ của **IKE_SA**, việc dùng **Diffie–Hellman khi tạo/rekey CHILD_SA** và các lựa chọn cụ thể của nền tảng; không khẳng định bật một ô “PFS” luôn bảo vệ mọi loại khóa/phiên với cùng ý nghĩa.

## 10. Traffic Selectors, SPD và SAD

IPsec không nhất thiết xử lý mọi packet gửi đến một IPsec peer. Hệ thống có **chính sách chọn traffic** và **trạng thái SA** xác định packet nào cần bảo vệ, được phép bypass hoặc bị từ chối.

### 10.1. Security Policy Database (SPD)

**SPD** mô tả xử lý traffic theo selector: gói nào cần **PROTECT** bằng IPsec, gói nào có thể **BYPASS**, gói nào phải **DISCARD**. Trong thực tế, sản phẩm có thể biểu diễn bằng các policy, object, tunnel interfaces, rule tables hoặc cấu hình khác; không phải mọi giao diện quản trị đều lộ SPD đúng tên.

~~~text
Ví dụ chính sách logic cho site-to-site:

Nguồn nội bộ 10.10.10.0/24  → đích 10.20.20.0/24:
  PROTECT qua IPsec tunnel đã được phê duyệt

Nguồn guest 10.10.90.0/24  → đích 10.20.20.0/24:
  DISCARD / DENY theo phân đoạn

Traffic Internet khác:
  Áp dụng policy internet egress riêng; không tự đi vào VPN
~~~

### 10.2. Security Association Database (SAD)

**SAD** chứa thông tin phục vụ xử lý SA, như **SPI, thuật toán, khóa, sequence/anti-replay, lifetime và endpoint/mode** theo mô hình cụ thể. Khi nhận ESP, peer phải tìm đúng SA trước khi kiểm tra xác thực và giải mã.

### 10.3. Traffic Selectors (TSi, TSr) trong IKEv2

**Traffic Selectors** giới hạn những traffic được chấp nhận qua một CHILD_SA, ví dụ subnet nguồn/đích, protocol và khoảng port phù hợp. Cần xem **hướng của từng peer**: một selector “local subnet” của gateway A là “remote subnet” tương ứng ở gateway B.

| Gateway A | Gateway B |
| --- | --- |
| Local: 10.10.10.0/24 | Remote: 10.10.10.0/24 |
| Remote: 10.20.20.0/24 | Local: 10.20.20.0/24 |
| Chỉ bảo vệ vùng cần thiết | Chấp nhận vùng tương ứng theo quyền |

Hai phía có thể **thu hẹp (narrow)** traffic selectors theo quy tắc IKEv2 và chính sách được hỗ trợ. Đừng suy từ “IPsec SA established” rằng mọi subnet bạn muốn đã nằm trong CHILD_SA; phải xem **TS thực tế đã thương lượng** và counters theo traffic.

### 10.4. Traffic selectors khác firewall authorization

**TS nói traffic nào thuộc SA**, không tự thay thế kiểm soát ứng dụng và phân đoạn. Nếu TS là **0.0.0.0/0** ở một tunnel interface, không có nghĩa mọi host ở phía xa được quyền đến mọi DB. **Route, firewall policy, identity, security group, NAT và dịch vụ đích** vẫn quyết định quyền truy cập.

## 11. Site-to-site VPN: đi từ LAN A đến LAN B

### 11.1. Sơ đồ khái quát

~~~mermaid
flowchart LR
    L["LAN A 10.10.10.0/24"] --> A["Gateway A"]
    A ==>|"IKEv2 + ESP tunnel mode qua WAN"| B["Gateway B"]
    B --> R["LAN B 10.20.20.0/24"]
~~~

Đối với site-to-site, **gateway A và B là IPsec endpoints**, còn host nội bộ chỉ gửi packet như bình thường tới default gateway/routing domain. Điều đó làm **tunnel mode** phù hợp: inner header chứa địa chỉ host A/B, outer header chứa địa chỉ hai gateway.

### 11.2. Đường dữ liệu theo từng bước

1. Host A phát gói từ 10.10.10.20 tới 10.20.20.30.
2. Routing ở site A đưa gói tới gateway có policy/route cho site B.
3. Gateway A kiểm tra vùng nguồn/đích, route/selector và firewall policy.
4. Gói inner được mã hóa, xác thực thành **ESP tunnel**, outer source/destination là địa chỉ gateway theo thiết kế.
5. Mạng WAN chuyển packet theo outer IP; trên WAN người quan sát không thấy inner IP khi ESP mã hóa đúng.
6. Gateway B kiểm tra SA, anti-replay, giải mã, đối chiếu inbound policy và route inner packet vào LAN B.
7. Server B trả lời tới host A theo route phù hợp; gateway B mã hóa bằng **SA chiều B→A**.
8. Host A nhận được response nếu **return route, security policies, NAT, MTU và các ứng dụng** đều hợp lệ.

**Đường về là bắt buộc:** Tunnel A→B có ESP packet ra và counter tăng chưa bảo đảm return path B→A đã hoạt động. Khi phân đoạn, site B cần cho phép đúng lưu lượng và chặn những luồng không có quyền, không đơn giản “ALLOW entire subnet because VPN peer is trusted”.

### 11.3. Policy-based VPN và route-based VPN

Đây là **cách lựa chọn/đưa traffic qua IPsec**, không phải hai tên khác của tunnel mode/transport mode.

| Mô hình | Đặc điểm khái quát | Cần kiểm tra |
| --- | --- | --- |
| **Policy-based** | Chính sách/selector xác định luồng nào cần IPsec | Sự tương thích local/remote selectors, NAT exemption, thay subnet |
| **Route-based** | Dùng virtual tunnel interface (VTI/XFRM interface hoặc tương đương) và route đưa traffic đến interface | Route/VRF, firewall zone, TS thực tế và interface state |
| **Dynamic route over tunnel** | BGP/OSPF hoặc cơ chế tương tự chạy qua/nhờ tunnel phù hợp | Reachability peers, keepalive, route filtering và loop prevention |

Một route-based VPN vẫn dùng **IPsec SA và traffic selectors**; tùy giải pháp, TS có thể rộng để routing/zone policy quyết định luồng đi qua. Không nói “route-based tự động bảo mật hơn policy-based”, cũng không đồng nhất tunnel interface với encryption nếu SA chưa sẵn sàng.

## 12. Remote-access VPN: laptop, thiết bị di động và virtual IP

Trong **remote-access IPsec**, client thường là một **IPsec endpoint** và security gateway của tổ chức là endpoint còn lại. Với **tunnel mode**, client có thể được cấp một **inner/virtual IP** hoặc các cấu hình tuyến để truy cập các ứng dụng nội bộ theo quyền.

~~~mermaid
flowchart LR
    U["Remote client | outer IP: mạng nhà/4G"] -->|"IKEv2 auth + ESP tunnel"| G["Corporate VPN gateway"]
    G --> APP["Ứng dụng nội bộ"]
    G -. "Firewall/Identity policy" .-> DB["Dữ liệu/zone nhạy cảm"]
~~~

### 12.1. Đừng đồng nhất địa chỉ bên ngoài và bên trong

~~~text
Client ngoài Internet (outer):
  Public IP do ISP/NAT cấp: 198.51.100.55
  Gateway public IP:       203.0.113.10

Địa chỉ logic bên trong VPN (một ví dụ):
  Assigned inner IP:       10.50.10.25
  Internal application:    10.20.20.30:443

Trên WAN sau khi tạo tunnel:
  [ IP-outer 198.51.100.55 → 203.0.113.10 ]
  [ UDP/NAT-T nếu có ][ ESP ]
  { inner IP 10.50.10.25 → 10.20.20.30, TCP 443 ... }
~~~

Nếu client sau NAT, public IP ghi trên ví dụ có thể là địa chỉ NAT nhìn thấy bởi gateway, không nhất thiết là IP được gán cho NIC client. Các địa chỉ đều dành cho minh họa.

### 12.2. Full tunnel và split tunnel

| Cấu hình | Mô tả | Lợi ích/rủi ro |
| --- | --- | --- |
| **Full tunnel** | Traffic thuộc phạm vi cấu hình (thường gồm Internet egress) được đưa qua corporate VPN | Kiểm soát egress tập trung nhưng tăng tải gateway, độ trễ và nguy cơ phụ thuộc VPN |
| **Split tunnel** | Chỉ một số dải/dịch vụ thuộc VPN, traffic Internet khác có thể đi trực tiếp | Giảm tải gateway nhưng cần chính sách endpoint, DNS, EDR, firewall và chống rò rỉ rõ ràng |

**Full/split tunnel không phải một IPsec mode thứ ba.** Đây là chính sách **định tuyến và lưu lượng nào đi vào VPN**; cả hai thường dùng ESP tunnel mode. Bên cạnh IPv4 phải xem cả **IPv6, DNS split-horizon, proxy settings, application routes và nội dung không được phép bypass**.

### 12.3. Xác thực client và thiết bị

IKEv2 có thể kết hợp chứng chỉ, phương pháp xác thực được hỗ trợ và **EAP** trong những kiến trúc remote-access; một hệ thống có thể gắn thêm **MFA, device posture, certificate lifecycle, nhóm quyền và session timeout**. Phải xét **phương thức EAP cụ thể**, nền tảng client, xác thực gateway và giới hạn triển khai.

**Mã hóa tunnel không thay thế user authorization.** Một client được kết nối VPN vẫn có thể chỉ được phép tới một nhóm ứng dụng, không được đi tới DB hoặc quản trị mạng. Firewall phía sau gateway nên kiểm soát **identity, subnet, ứng dụng và logging**, không tự tin tưởng toàn bộ VPN pool.

## 13. NAT traversal (NAT-T) và cổng/giao thức cần lưu ý

ESP nguyên thủy thường được mang trực tiếp bằng **IP protocol number 50**. ESP không dùng **TCP/UDP port** trong cách mang native đó. IKE thường dùng **UDP 500** để thương lượng; khi phát hiện NAT hoặc cần encapsulation được hỗ trợ, **NAT Traversal (NAT-T)** thường dùng **UDP 4500** cho ESP-over-UDP và các thông điệp IKE liên quan.

| Thành phần trên đường mạng | Dấu hiệu thường gặp | Ghi chú |
| --- | --- | --- |
| IKEv2 ban đầu | UDP **500** | Thương lượng và phát hiện NAT theo quy trình |
| IKE qua NAT-T | UDP **4500** | Phân biệt thông điệp IKE với ESP encapsulated ở cổng này |
| ESP native | **IP protocol 50** | Không phải TCP/50 hoặc UDP/50 |
| ESP over UDP (NAT-T) | **UDP 4500** | Thêm UDP header; bảo vệ ESP payload theo SA |
| AH native | **IP protocol 51** | Không có NAT traversal phổ biến tương đương |

### 13.1. Packet dạng NAT-T

~~~text
Tunnel mode không NAT-T:
  [ Outer IP ][ ESP hdr ][ encrypted inner packet ][ ESP tag ]

Tunnel mode có NAT-T:
  [ Outer IP ][ UDP 4500 ][ ESP hdr ]
  [ encrypted inner packet ][ ESP tag ]
~~~

Trong UDP 4500, **IKE message** và **UDP-encapsulated ESP** có cách phân biệt theo định dạng quy định; IKE có **Non-ESP Marker** theo chuẩn, còn ESP encapsulation bắt đầu từ ESP header phù hợp. **Không suy mọi packet UDP 4500 đều là payload ESP data**.

### 13.2. NAT-T không phải thay thế tunnel mode

**NAT-T là lớp đóng gói ESP qua UDP để đi qua NAT/firewall**, không phải một mode thứ ba. Nó có thể xuất hiện với cấu hình IPsec phù hợp; hỗ trợ/giới hạn **transport mode qua NAT** phải được xác minh trên hai đầu vì liên quan địa chỉ/port/checksum và điều kiện triển khai.

### 13.3. Các lỗi NAT-T thường gặp

- Peer đến được UDP 500 nhưng **UDP 4500 bị chặn**, khiến IKE có thể bắt đầu mà data SA không truyền traffic như mong đợi.
- NAT mapping **hết hạn** hoặc thay đổi mạng Wi-Fi/4G làm gián đoạn kết nối.
- Nhiều client sau cùng NAT, cần **session mapping** đúng cho các peer.
- MTU/fragmentation tăng do thêm UDP header, outer IP và ESP overhead.
- Nơi kiểm soát chỉ cho phép ESP native (protocol 50) nhưng quên NAT-T hoặc ngược lại.
- VPN gateway nhận outer source IP đã NAT, gây sai **peer identity policy** nếu hệ thống nhầm IP nguồn với identity được chứng thực.

Giải pháp không phải mở toàn bộ inbound traffic: chỉ cấu hình những port/protocol và peers cần thiết, giới hạn quyền truy cập, bảo vệ control plane, kiểm tra logs ở cả hai phía và duy trì thông tin NAT-T/keepalive theo chuẩn/nền tảng.

## 14. MTU, MSS, fragmentation và chi phí đóng gói

Mọi lớp encapsulation tiêu thụ một phần **Maximum Transmission Unit (MTU)** trên đường WAN. Nếu một inner packet gần bằng MTU gốc rồi thêm outer IP, ESP header, IV/nonce, tag, padding và có thể UDP NAT-T, packet ngoài có thể **vượt Path MTU (PMTU)**.

### 14.1. Overhead phụ thuộc cấu hình

| Thành phần | Chi phí minh họa | Điều kiện |
| --- | --- | --- |
| Outer IPv4 header không options | **20 bytes** | Chỉ trong tunnel với outer IPv4 |
| Outer IPv6 header cơ bản | **40 bytes** | Chỉ trong tunnel với outer IPv6; extension headers có thể thêm |
| UDP header cho NAT-T | **8 bytes** | Khi ESP encapsulated over UDP |
| ESP header SPI + sequence number | **8 bytes** | ESP theo cấu trúc cơ bản |
| ESP trailer/padding/tag | **Thay đổi** | Theo transform, IV, block alignment, thuật toán, ESN |
| Inner IP header | **20 bytes IPv4 cơ bản** hoặc **40 bytes IPv6 cơ bản** | Được bảo vệ trong tunnel mode; có sẵn từ gói gốc |

**Không suy ra một con số overhead cố định cho mọi VPN.** Ví dụ AES-GCM và AES-CBC/HMAC có cấu trúc IV/nonce, padding/tag khác nhau; GRE over ESP transport lại có overhead GRE đã được thêm trước.

### 14.2. Ví dụ tính sức chứa khái quát

~~~text
PMTU của đường ngoài:            1500 bytes
Outer IPv4 (tunnel):              20 bytes
UDP NAT-T (nếu có):                8 bytes
ESP fixed header:                  8 bytes
IV/nonce, padding, trailer, tag:  thay đổi theo thuật toán
--------------------------------------------------------
Sức chứa cho inner IP packet
  < 1500 - 20 - 8 - 8  (vì còn cryptographic overhead)
~~~

Khi transport mode không cần thêm outer IP header riêng, overhead có thể thấp hơn; nhưng gói trên mạng vẫn cần vừa PMTU. **MSS clamping** chỉ điều chỉnh MSS TCP ở những vị trí phù hợp; không tự giải quyết mọi vấn đề của **UDP, ICMP, IPv6 PMTUD, tunnel lồng nhau hoặc ứng dụng gửi datagram lớn**.

### 14.3. Triệu chứng MTU/PMTUD bị lỗi

Một số request nhỏ qua VPN thành công nhưng tải dữ liệu lớn bị treo. Có thể do ICMP cần cho PMTUD bị chặn, gateway tạo packet lớn hơn PMTU, fragment bị loại hoặc offload/tunnel path xử lý không nhất quán.

Quy trình chẩn đoán an toàn:

1. Xác định **outer link PMTU**, địa chỉ outer IPv4/IPv6, NAT-T và ESP transform.
2. Kiểm tra packet size khi gửi và nhận, các counters **fragmentation/PMTU/ICMP** tại thiết bị có quyền quan sát.
3. Xem **TCP MSS** của các flow bị ảnh hưởng, so với những luồng đang hoạt động.
4. Thử có kiểm soát trong lab/staging với kích thước gói khác nhau; không dùng traffic flood.
5. Điều chỉnh MTU/MSS hoặc đường truyền **theo tài liệu thiết bị**, kiểm tra ứng dụng và lưu lượng UDP/IPv6 sau thay đổi.

**Nguyên tắc:** Không vô hiệu hóa mọi ICMP một cách máy móc; một số thông điệp ICMP/ICMPv6 cần thiết cho PMTUD và vận hành IP.

## 15. Anti-replay, khóa, identity và những giới hạn bảo mật

### 15.1. Anti-replay hoạt động ra sao?

ESP dùng **sequence number** để bên nhận phát hiện những packet đã xuất hiện hoặc nằm quá xa phía sau cửa sổ chấp nhận, tùy cơ chế và thiết lập. Điều này giúp giảm **replay** với gói thuộc SA.

~~~text
Ví dụ minh họa (không phải thuật toán đầy đủ):
  Receive seq=100: accept nếu integrity/SA hợp lệ
  Receive seq=101: accept nếu integrity/SA hợp lệ
  Receive seq=100 lần nữa: có thể bị drop vì duplicate

Thứ tự đường WAN:
  Packet có thể đến không theo thứ tự.
  Anti-replay phải xem xét cửa sổ, không đơn thuần
  yêu cầu sequence tăng liên tục từng gói.
~~~

**Extended Sequence Numbers (ESN)** và độ lớn cửa sổ anti-replay tùy hỗ trợ và thương lượng. Khi routing asymmetry, load balancing hoặc failover làm **đảo thứ tự đáng kể**, gói hợp lệ có thể bị loại nếu vượt cửa sổ; cần chẩn đoán counter và thiết kế đường đi, không tắt anti-replay tùy tiện.

### 15.2. Integrity không đồng nghĩa peer an toàn tuyệt đối

ESP có thể xác nhận gói thuộc **SA và khóa hợp lệ**, nhưng:

- Không kiểm tra server/web application không có lỗ hổng.
- Không chứng minh mọi user/host phía sau gateway đáng tin.
- Không bảo vệ data khi đã giải mã tại endpoint khỏi phần mềm độc hại trên endpoint.
- Không ngăn người quan sát phân tích **traffic pattern, gateway addresses và thời gian**.
- Không tự bảo vệ DNS resolution ngoài tunnel, routing bypass, chính sách split tunnel hoặc quản trị khóa yếu.

### 15.3. Khuyến nghị quản trị khóa

- Dùng **IKEv2** và bộ thuật toán mạnh được chính sách tổ chức, chuẩn áp dụng và hai bên hỗ trợ.
- Quản lý **certificate trust chain**, peer identity, expiration, revocation và account/secret lifecycle.
- Với PSK, dùng bí mật mạnh, cấp quyền tối thiểu, tránh chia sẻ cho quá nhiều peers; cân nhắc chứng chỉ khi thích hợp.
- Ghi nhận **rekey failure, authentication failure, SA lifetime** và liveness; không bật các transform cũ/yếu chỉ để “hết lỗi negotiation” mà không đánh giá.
- Nếu cần lưu lượng dữ liệu nhạy cảm, áp dụng **TLS/mTLS và kiểm soát ứng dụng** bổ sung theo threat model dù đã có IPsec tunnel.

## 16. Packet capture và điều gì có thể kết luận?

Tùy vị trí capture, người phân tích có thể quan sát:

| Điểm capture | Trong tunnel mode | Trong transport mode |
| --- | --- | --- |
| **Trước IPsec encryption** tại bên gửi | Inner IP, TCP/UDP và ứng dụng theo trạng thái mã hóa riêng | Original IP header và upper-layer data |
| **Trên WAN** | Outer IP, ESP SPI/sequence, length/timing, NAT-T nếu có | IP header hiện hữu, ESP SPI/sequence, length/timing |
| **Sau IPsec decryption** tại bên nhận | Inner IP, protocol và ứng dụng sau IPsec | Payload upper-layer đã được giải mã |
| **Trong endpoint/browser sau TLS** | Có thể xem dữ liệu ứng dụng theo quyền và điểm quan sát | Tương tự |

### 16.1. Các lệnh quan sát *read-only* trên Linux

Đây là lệnh **minh họa để học**, chỉ dùng với thiết bị/mạng thuộc quyền quản lý; không cần thực thi để hiểu bài.

~~~sh
# Xem policy và state xfrm từ kernel Linux (khi có quyền phù hợp)
ip xfrm policy
ip xfrm state

# Xem route và policy-based routing của host
ip route show
ip rule show

# Xem địa chỉ và interface
ip -br addr
~~~

**Lưu ý bảo mật đặc biệt:** Output của **ip xfrm state** trên một số hệ thống có thể **hiển thị thuật toán và vật liệu khóa bí mật**. Vì vậy, dù lệnh chỉ đọc, **không chụp màn hình, dán raw output hay xuất log toàn phần** vào ticket/chat không được bảo vệ. Tốt hơn là xem **trạng thái đã được che khóa** thông qua cơ chế quản trị an toàn của sản phẩm. Không chạy lệnh trên hệ thống không được cấp quyền.

### 16.2. Wireshark và IPsec

Khi capture chỉ có ESP đã mã hóa, Wireshark thường không tự khôi phục nội dung inner packet nếu không có **khóa SA và cấu hình giải mã hợp lệ**. Không thu thập hay chia sẻ khóa của VPN Production chỉ để minh họa bài học. Trong lab riêng có thể tạo hai peers và kiểm tra sự khác biệt giữa outer IP, ESP, UDP NAT-T và inner packet **trên dữ liệu được phép**.

**Một VPN “Connected” trên UI chưa đủ:** Cần kiểm tra IKE_SA/CHILD_SA, traffic selectors, route vào tunnel, packet/byte counters hai chiều, NAT policy, firewall rules và ứng dụng thực sự hoạt động.

## 17. Chọn mode theo trust boundary và mô hình hóa mối đe dọa

Trước khi chọn mode, hãy trả lời **cần bảo vệ dữ liệu trên đoạn nào, khỏi ai, và ai phải đọc được IP header nào để định tuyến**. Việc dùng tunnel mode thay transport mode không tự bảo đảm toàn bộ kiến trúc mạng an toàn.

### 17.1. Xác định các vùng tin cậy

~~~mermaid
flowchart LR
    A["Endpoint nội bộ Site A"] --> G1["Gateway A"]
    G1 ==>|"ESP tunnel mode: WAN không tin cậy"| G2["Gateway B"]
    G2 --> B["Endpoint nội bộ Site B"]
    G1 -. "Policy / logging" .-> FW1["Firewall zone Site A"]
    G2 -. "Policy / logging" .-> FW2["Firewall zone Site B"]
~~~

Từ endpoint A tới gateway A, dữ liệu có thể chưa được IPsec bảo vệ nếu VPN chỉ chạy giữa gateways. Đoạn gateway B tới endpoint B cũng có thể là plaintext ở lớp IPsec, dù ứng dụng còn dùng TLS riêng. Với **transport mode host-to-host**, IPsec bảo vệ trực tiếp giữa hai host, nhưng rủi ro ở chính **endpoint/process** vẫn còn.

### 17.2. Threat modeling cho IPsec modes

| Kịch bản | Tác động | Kiểm soát cần xem |
| --- | --- | --- |
| **Nghe lén trên WAN** | Lộ dữ liệu nếu ESP không dùng encryption phù hợp | ESP transforms, SA thực tế, khóa và cấu hình bắt buộc |
| **Lộ inner addressing** | Tiết lộ địa chỉ nội bộ qua WAN nếu không được bọc như dự kiến | Tunnel mode với encryption; kiểm tra capture tại đường không tin cậy |
| **Lộ outer metadata** | Biết gateway IP, timing, packet size dù payload mã hóa | Threat model traffic analysis; không cam kết anonymity |
| **Impersonated VPN gateway** | Client nối nhầm peer | Kiểm tra certificate/peer identity/trust chain, chống downgrade |
| **PSK hoặc private key lộ** | Peer giả mạo hoặc mất tính bảo vệ theo khả năng bị lộ | Quản lý secrets/certificate, rekey, thu hồi quyền, audit |
| **Traffic selectors quá rộng** | Đưa traffic trái chủ đích vào VPN hoặc gateway nhìn thấy subnet nhạy cảm | SPD/TS review, route, zone firewall, identity |
| **Split tunnel bypass policy** | Internet egress/IPv6/DNS đi ngoài đường quan sát | Endpoint policy, DNS routing, EDR/WAF, IPv6 tests |
| **Tunnel route leak** | Dev/Guest kết nối Prod/Management ngoài ý định | VRF, route filtering, ACL, segmentation, regression DENY |
| **Replay/reorder packets** | Gói trùng hoặc hợp lệ bị drop khi biến động đường | Anti-replay, route stability, window diagnostics |
| **NAT-T blocked/mapping expired** | VPN mất lưu lượng hoặc reconnect liên tục | UDP 500/4500 policy, keepalive, NAT/session monitoring |
| **IKE/ESP SA mismatch** | “Connected” nhưng không truyền data | IKE/CHILD_SA, mode, transforms, TS và counters |
| **IPsec gateway bị xâm nhập** | Data bị giải mã hoặc policy bị thay đổi tại trust boundary | RBAC, MFA, hardening, firmware, logs và bảo vệ khóa |
| **Security gateway HA mất state** | Session cũ reset/route bất đối xứng sau failover | Peer health, SA sync theo khả năng, routing, ứng dụng reconnect |

### 17.3. Chọn mode theo tình huống

| Bối cảnh | Mode thường phù hợp | Lý do |
| --- | --- | --- |
| **Chi nhánh ↔ data center** với nhiều thiết bị phía sau gateway | **ESP tunnel** | Bọc inner packets, hai gateway đại diện cho nhiều host |
| **Cloud VPC ↔ on-prem** site-to-site | **ESP tunnel** | Bảo vệ các prefix nội bộ qua WAN và peer gateways |
| **Laptop remote-access ↔ corporate VPN gateway** | **ESP tunnel** | Virtual inner address, split/full tunnel, quyền theo user/device |
| **Hai host trực tiếp hỗ trợ IPsec** | **ESP transport** là ứng viên | Bảo vệ upper-layer traffic giữa chính hai endpoint |
| **GRE router ↔ GRE router đã tạo outer GRE IP header** | **ESP transport** có thể phù hợp | Bảo vệ GRE payload, không cần thêm một outer IP riêng do ESP |
| **Yêu cầu mã hóa cả inner IP header qua WAN** | **ESP tunnel** | Inner source/destination nằm trong vùng mã hóa |
| **Ứng dụng HTTPS tới Internet công cộng không có peer IPsec** | Thường **TLS**, không tự triển khai IPsec | HTTPS không đòi endpoint Internet hỗ trợ IKEv2/ESP |
| **L2TP/IPsec hoặc vendor-specific overlay** | Tùy giao thức và nền tảng | Lớp tunnel hiện hữu và mode cần đúng tài liệu triển khai |

**Không dùng mode làm cơ chế phân quyền.** Sau khi packet được giải mã, luôn áp dụng **security zone policy, identity, service access và logging** phù hợp.

## 18. Quy trình điều tra khi IPsec không hoạt động

Người vận hành thường gặp ba trạng thái: **IKE không lên**, **IKE lên nhưng CHILD_SA không có**, hoặc **SA có mà dữ liệu ứng dụng không đi được**. Mỗi trạng thái có nguyên nhân khác nhau; đừng sửa đồng thời tất cả cấu hình.

### 18.1. Bước 1 — Xác nhận kết nối tới peer và giao thức

- Xác định **địa chỉ peers, interface, NAT**, thời gian UTC và thay đổi gần nhất.
- Xem DNS nếu peer được định danh bằng FQDN; kiểm tra path tới **UDP 500/4500** và ESP protocol 50 khi dùng native ESP.
- Kiểm tra security group/ACL/provider policies có cho đúng **IKE/ESP** không; cần xét chiều và thiết kế stateful/stateless.
- Nếu có NAT, xem peer đã chuyển sang UDP encapsulation và NAT mapping còn sống không.

**Không mở mọi protocol từ Internet** như một cách “thử nhanh”. Dùng log và phép kiểm được phê duyệt trên đúng các địa chỉ/port liên quan.

### 18.2. Bước 2 — Kiểm tra IKE và xác thực

| Dấu hiệu | Nhóm nguyên nhân |
| --- | --- |
| Không có IKE response | Peer IP/route sai, upstream ACL, UDP blocked, NAT hoặc peer service lỗi |
| Authentication failure | PSK/certificate/peer ID, trust chain, policy xác thực |
| No matching IKE proposal | Algorithms/key-exchange groups không giao nhau |
| IKE_SA established nhưng không có CHILD_SA | ESP proposals, mode, traffic selectors hoặc quyền của peer |
| SA liên tục rekey/reconnect | Lifetime/liveness, policy mismatch, NAT mapping, HA và thiết bị quá tải |

Không xuất **private keys, raw IKE secrets hoặc key material từ SA** để chia sẻ hỗ trợ; dùng các logs đã được redaction.

### 18.3. Bước 3 — Kiểm tra mode và selectors

Hỏi rõ:

1. Hai bên cùng dự định dùng **ESP tunnel hay transport**?
2. Với tunnel mode, **inner local/remote prefix** đã nằm trong TS? Outer endpoint addresses có đúng peer?
3. Với transport mode, hai **IPsec endpoints** có tương ứng với IP header hiện hữu cần bảo vệ?
4. Với GRE over transport, GRE endpoints, IP protocol 47 và chính sách IPsec có áp đúng packet GRE (sau khi tạo header GRE) không?
5. Hệ thống có **selector narrowing** khiến một số subnet/port bị loại khỏi CHILD_SA không?
6. Vùng DMZ/Dev/Prod và các luồng cần DENY có còn bị chặn dù TS chấp nhận traffic?

### 18.4. Bước 4 — Xem route, NAT, firewall và counters

~~~text
Client:
  src IP:port / dst IP:port / protocol
  route tới VPN gateway hoặc virtual tunnel interface

Gateway A:
  SPD/route match?  outbound CHILD_SA byte/packet counter tăng?
  NAT/no-NAT policy?  rule ALLOW/DENY nào xử lý?

WAN:
  ESP protocol 50 hoặc UDP encapsulated 4500 có đi/đến?
  outer peer IP là gì, MTU/fragmentation thế nào?

Gateway B:
  inbound CHILD_SA counter tăng? integrity/replay drops?
  inner packet sau decrypt có được route/allow đúng?

Server:
  nhận được request không? route trả về tới client IP ở đâu?
~~~

Một dấu hiệu đặc trưng: **SA tồn tại nhưng outbound counter luôn bằng 0**, gợi ý traffic chưa được route/chọn vào SA. Ngược lại, **A outbound tăng nhưng B inbound không tăng**, cần xem đường WAN, NAT-T, filter và peer. Nếu **B inbound tăng nhưng server không thấy dữ liệu**, xem firewall/routing/NAT **sau giải mã**. Cách diễn giải counter tùy vendor: có nền tảng đếm trước/sau encrypt hoặc áp filter theo cách khác.

### 18.5. Bước 5 — Kiểm chứng MTU, return path và ứng dụng

Khi ping nhỏ được nhưng HTTP tải lớn lỗi, kiểm tra **PMTUD/MSS**. Khi chỉ một subnet lỗi, kiểm tra **TS, policy, route prefix cụ thể hơn, NAT exemption**. Khi một chiều hoạt động, xem **asymmetric routing, SA mapping và return route**. Khi data tới server nhưng app fail, kiểm tra **TLS, DNS, certificate, authorization và backend**.

### 18.6. Bước 6 — Thay đổi có kiểm soát và rollback

Mỗi thay đổi mode, cipher, TS, route, NAT hoặc firewall cần lưu:

~~~text
Incident/change ID:
Time UTC:
Peer identities and roles:
Expected mode: tunnel/transport
IKE/CHILD_SA summary: no secrets
Local/remote TS and environment:
Outer IP and NAT-T path:
Observed counters and application impact:
Proposed adjustment:
Security impact and approvals:
Rollback plan:
Post-change ALLOW/DENY test evidence:
~~~

Đặc biệt **không chuyển cả site-to-site sang transport mode chỉ vì tunnel không lên**. Nếu hai gateway đang bảo vệ LAN phía sau, transport mode đơn thuần có thể không mang inner packets theo kiến trúc mong muốn.

## 19. Case study 1: site-to-site chọn sai transport mode

**Bối cảnh giả định:** Site A có subnet **10.10.10.0/24**, site B có **10.20.20.0/24**. Hai firewall được giao tạo VPN giữa hai LAN; đội triển khai quen dùng transport mode để bảo vệ chính các giao tiếp **firewall A ↔ firewall B** rồi áp mode này cho policy site-to-site.

### 19.1. Điều mong muốn và điều đã triển khai

~~~text
Mong muốn:
  Inner IP 10.10.10.20 -> 10.20.20.30
  Outer IP 198.51.100.10 -> 203.0.113.10
  ESP tunnel mode bảo vệ toàn inner packet.

Thiết lập nhầm:
  ESP transport mode trên packet IP của gateway
  198.51.100.10 -> 203.0.113.10
  nhưng không có GRE/tunnel khác để mang inner packet.

Hệ quả:
  Chính sách bảo vệ packet gateway-to-gateway không tự
  cung cấp IP-in-IP để chở traffic LAN-to-LAN như thiết kế.
~~~

Đừng kết luận mọi phần mềm chắc chắn thương lượng được SA rồi mất dữ liệu: một số nền tảng sẽ **từ chối mode/policy không hợp lệ trước đó**. Kết quả phụ thuộc sản phẩm và cách trùng khớp selectors; ý chính là **encapsulation và traffic cần bảo vệ không tương ứng**.

### 19.2. Cách điều tra

| Bằng chứng | Quan sát có thể có | Bước xử lý |
| --- | --- | --- |
| IKE_AUTH / CHILD_SA | Mode mismatch hoặc TS không phù hợp | Đối chiếu hai đầu, không tự đổi thuật toán ngẫu nhiên |
| Outbound ESP counters | Chỉ tăng với packet giữa gateway, không với LAN traffic | So route/selector và mục đích tunnel |
| Capture WAN | Không thấy ESP đại diện cho lưu lượng LAN đang kiểm thử | Xác nhận packet được chọn vào IPsec hay không |
| Inner subnet reachability | TCP/HTTPS từ LAN A tới LAN B thất bại | Kiểm tra forward/return, route, zone policy |
| Change record | Yêu cầu thực sự là gateway-to-gateway site-to-site | Chuyển thiết kế về ESP tunnel mode có phê duyệt |

### 19.3. Khắc phục

1. Xác nhận LAN prefixes, owner, phân đoạn và ứng dụng được phép.
2. Cấu hình **ESP tunnel mode** và selectors/route đúng theo tài liệu của cặp gateway.
3. Kiểm tra NAT/no-NAT, route đến protected prefixes, anti-spoofing và gateway firewall rules.
4. Giới hạn quyền **ALLOW** đến đúng server/port cần thiết; giữ các bài thử **Dev → Prod DB DENY**.
5. Đo IKE/CHILD_SA, ESP counters hai chiều và ứng dụng end-to-end; có rollback.

**Bài học:** Tên “VPN” hay “đã có SA” không nói đủ về khả năng chở traffic. Phải hiểu IP header **nào** được tạo, giữ nguyên hoặc mã hóa.

## 20. Case study 2: remote-access VPN lên nhưng traffic bị bypass

**Bối cảnh giả định:** Nhân viên kết nối VPN IKEv2 bằng tunnel mode từ Wi-Fi công cộng. UI báo *Connected*; người dùng truy cập ứng dụng nội bộ qua IPv4 được, nhưng một ứng dụng thử nghiệm có địa chỉ IPv6 public lại đi trực tiếp qua mạng Wi-Fi, trái với ý định “mọi lưu lượng công việc phải được kiểm soát”.

### 20.1. Nguyên nhân cần kiểm tra

- Chính sách **full tunnel IPv4** đã được cấu hình nhưng **IPv6 không có route/selector phù hợp**, làm một số traffic IPv6 đi ngoài VPN.
- DNS trả kết quả **AAAA** trong khi split DNS và split tunnel policy chỉ đề cập IPv4.
- Một số ứng dụng sử dụng **proxy/DoH** hoặc mạng riêng theo policy của endpoint.
- Endpoint có nhiều interface và **route metrics** thay đổi sau khi Wi-Fi/VPN reconnect.
- Gateway có TS rộng nhưng **client routing** vẫn không chọn gửi traffic qua đường được bảo vệ.

### 20.2. Phân tích và khắc phục

1. Xác định **ý định**: full tunnel thật sự gồm IPv4, IPv6, DNS và những traffic loại nào?
2. Kiểm tra client effective routes, **IPv4/IPv6 selectors** và DNS resolver được dùng; quan sát bằng logs và kiểm tra theo quyền.
3. Xem VPN gateway policy có cho phép các luồng cần thiết và chặn các luồng trái quyền không.
4. Cấu hình routing/endpoint security cho các address families phù hợp, tránh lỗi **IPv6 bypass**; nếu chưa hỗ trợ IPv6 tunnel, thiết kế phải có biện pháp thay thế rõ ràng, không tự che giấu khoảng trống.
5. Đo các hành trình người dùng, đặc biệt ứng dụng có A/AAAA, DNS, authentication và các phần mềm proxy.
6. Thử tình huống client đổi từ Wi-Fi sang 4G, thay NAT mapping, tunnel reconnect và logout; xác minh các route được thu hồi hoặc phục hồi đúng.

**Bài học:** **Tunnel mode** đã bảo vệ các gói **được chọn vào tunnel**; nó **không tự buộc mọi kết nối trên thiết bị phải đi qua VPN**. Kiểm soát đường đi là tổng hợp của traffic selectors, client routes, DNS, endpoint posture và policy.

## 21. Thực hành Python offline: nhìn metadata và tính overhead IPsec

Bài lab này dùng **số liệu và gói giả lập có sẵn**, không tạo VPN, không phát packet, không đụng đến firewall hoặc mạng bên ngoài. Mục tiêu: mô tả **khác biệt metadata hiện ra ngoài ESP** và minh họa vì sao tunnel mode thường cần thêm số byte cho outer IP header.

### 21.1. Mô hình hóa một gói

Giả định gói IP gốc dài **1.200 bytes**, gồm inner IP header + upper-layer payload. Chọn tổng IV/nonce/trailer/tag/padding là **32 bytes giả định** để làm toán; con số **không phải overhead chuẩn cố định của AES-GCM hay sản phẩm nào**. ESP fixed header 8 bytes, outer IPv4 20 bytes, NAT-T UDP 8 bytes trong ví dụ.

~~~python
from dataclasses import dataclass
from typing import Literal


Mode = Literal["tunnel", "transport"]


@dataclass(frozen=True)
class IPsecExample:
    mode: Mode
    original_ip_bytes: int
    source_ip: str
    destination_ip: str
    gateway_a: str
    gateway_b: str
    nat_t: bool = False
    # Các số dưới đây chỉ dùng làm số liệu giả định để học.
    esp_fixed_header_bytes: int = 8
    crypto_overhead_bytes: int = 32
    outer_ip_header_bytes: int = 20


def describe(packet: IPsecExample) -> dict:
    if packet.original_ip_bytes <= 0:
        raise ValueError("Original packet size must be positive")
    if packet.mode not in ("tunnel", "transport"):
        raise ValueError("Unsupported mode")

    # Transport giữ IP header hiện hữu, tunnel thêm outer IP header.
    added_outer = packet.outer_ip_header_bytes if packet.mode == "tunnel" else 0
    added_udp = 8 if packet.nat_t else 0
    length = (
        packet.original_ip_bytes
        + added_outer
        + added_udp
        + packet.esp_fixed_header_bytes
        + packet.crypto_overhead_bytes
    )

    visible_src = (
        packet.gateway_a if packet.mode == "tunnel" else packet.source_ip
    )
    visible_dst = (
        packet.gateway_b if packet.mode == "tunnel" else packet.destination_ip
    )
    return {
        "mode": packet.mode,
        "on_wire_bytes_estimate": length,
        "visible_ip_pair": (visible_src, visible_dst),
        "inner_ip_header_encrypted": packet.mode == "tunnel",
    }


sample = {
    "original_ip_bytes": 1200,
    "source_ip": "10.10.10.20",
    "destination_ip": "10.20.20.30",
    "gateway_a": "198.51.100.10",
    "gateway_b": "203.0.113.10",
}

tunnel = describe(IPsecExample(mode="tunnel", nat_t=True, **sample))
transport = describe(IPsecExample(mode="transport", nat_t=False, **sample))

for row in (tunnel, transport):
    print(
        row["mode"],
        "bytes=", row["on_wire_bytes_estimate"],
        "visible=", row["visible_ip_pair"],
        "inner_header_encrypted=", row["inner_ip_header_encrypted"],
    )

assert tunnel["on_wire_bytes_estimate"] == 1268
assert transport["on_wire_bytes_estimate"] == 1240
~~~

Kết quả dự kiến:

~~~text
tunnel bytes= 1268 visible= ('198.51.100.10', '203.0.113.10') inner_header_encrypted= True
transport bytes= 1240 visible= ('10.10.10.20', '10.20.20.30') inner_header_encrypted= False
~~~

### 21.2. Hiểu đúng giới hạn lab

- Đây là **phép cộng kích thước**, không phải mã hóa IPsec, không có khóa thật, không kiểm tra xác thực và không mô phỏng SA/anti-replay.
- Giá trị 32 bytes crypto overhead là **giả định học thuật**, thay đổi theo ESP transform; tag/IV/padding/extension headers không nhất thiết có cấu trúc cố định.
- Dòng **inner_header_encrypted = True** chỉ diễn giải khi ESP tunnel **có bật encryption hợp lệ**; đây là tiền đề của bài lab.
- Với **transport mode bảo vệ GRE**, source/destination được hiển thị là **IP header của GRE tunnel**, không nhất thiết là IP của client ứng dụng.
- Kết quả không tính header L2, VLAN/MPLS, outer IPv6, GRE thêm, TCP retransmission, IP fragmentation hoặc cloud/provider encapsulation.
- Dùng tunnel và transport với NAT-T khác nhau để cho thấy hai nguồn overhead; muốn so sánh riêng phần **mode** thì đặt cùng giá trị **nat_t** ở cả hai case.

### 21.3. Bài tập mở rộng

1. Chạy mô hình tư duy với **transport + NAT-T**, dự đoán thêm bao nhiêu byte so với transport không NAT-T.
2. Đổi **outer_ip_header_bytes = 40** cho tunnel dùng outer IPv6 cơ bản; so sánh packet length.
3. Thêm một trường **is_encryption_enabled** và chỉ xác nhận inner header được bảo mật bí mật nếu chế độ encryption có hiệu lực.
4. Thêm **path_mtu = 1500** và cảnh báo khi length vượt giới hạn; giải thích vì sao MSS hoặc PMTUD có thể cần thay đổi.
5. Thêm case GRE+ESP transport có **GRE overhead riêng**, rồi phân biệt nó với outer IP do ESP tunnel mode tạo.
6. Viết bộ câu hỏi không cần chạy code để phân biệt thông tin **được nhìn thấy** với **được mã hóa** và **được xác thực** trong một gói ESP.

## 22. Ma trận kiểm thử IPsec tunnel/transport mode

Mọi kiểm thử chủ động phải thực hiện trong **lab/staging hoặc cửa sổ thay đổi được phê duyệt**, trên peers và tài sản thuộc quyền quản lý. Không quét peer bên ngoài, chặn NAT/ISP, ép failover hay thay chính sách Production khi chưa được cấp phép.

| Test ID | Kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| VPN-01 | Gateway A ↔ B thương lượng IKEv2 được phép | IKE_SA được xác thực đúng peer identity, proposal được duyệt |
| VPN-02 | Site-to-site dùng **ESP tunnel mode** | Quan sát WAN thấy outer gateway IP, không lộ inner IP nếu encryption đúng |
| VPN-03 | Host-to-host dùng **ESP transport mode** | WAN thấy IP header host hiện hữu, phần upper layer được bảo vệ |
| VPN-04 | GRE được bảo vệ bằng ESP transport theo thiết kế | GRE/IPsec phối hợp đúng, inner application packet được chuyển |
| VPN-05 | Một peer yêu cầu tunnel, peer kia transport | Thương lượng thất bại hoặc từ chối mode sai theo platform; không âm thầm nới chính sách |
| VPN-06 | CHILD_SA TS chỉ cho 10.10.10.0/24 ↔ 10.20.20.0/24 | Luồng trong scope vào tunnel, ngoài scope không được phép vô ý |
| VPN-07 | App HTTPS từ LAN A tới server được phép LAN B | TCP/TLS và giao dịch ứng dụng thành công cả hai chiều |
| VPN-08 | Guest/Dev đến DB Prod không được phép | **DENY** dù VPN tunnel đang UP và TS có thể rộng |
| VPN-09 | ESP native qua firewall/ISP | Cho đúng IP protocol 50 khi thiết kế yêu cầu, không nhầm TCP/50 |
| VPN-10 | NAT-T sau một NAT gateway trong lab | IKE/ESP qua UDP 4500 hoạt động, mapping ổn định |
| VPN-11 | NAT mapping thay đổi/reconnect | Peer khôi phục hoặc báo lỗi theo mục tiêu, không mất identity validation |
| VPN-12 | Gói nhỏ và gói gần PMTU | Không có black-hole bất ngờ; counters/PMTUD/MTU đã kiểm tra |
| VPN-13 | Remote client đổi Wi-Fi ↔ 4G | VPN reconnect/route theo quy trình, session/user identity còn phù hợp |
| VPN-14 | Full tunnel/IPv4 + IPv6 | Không có đường bypass ngoài ý định, DNS và endpoint policy đúng |
| VPN-15 | Split tunnel các prefix nội bộ | Chỉ traffic được chọn vào tunnel; đường còn lại theo chính sách rõ ràng |
| VPN-16 | Rekey CHILD_SA trong lab | Traffic phục hồi/tiếp tục theo mục tiêu, không kéo dài khóa/SA cũ ngoài chính sách |
| VPN-17 | Anti-replay thấy packet trùng trong mô phỏng engine được phép | Packet trùng bị xử lý theo policy; không tự tắt bảo vệ |
| VPN-18 | Hai hướng đi khác firewall khi HA/failover | Route/SA/session ownership không gây bypass hoặc drop ngoài mục tiêu |
| VPN-19 | Cloud route table/NAT exemption đổi trong lab | Counter và application test cho thấy traffic đi đúng gateway/tunnel |
| VPN-20 | Chính sách IKE yếu hoặc certificate/identity sai | Từ chối peer/proposal không được phép |
| VPN-21 | Sau decryption tại gateway B | Firewall/logging/segmentation của inner traffic còn hiệu lực |
| VPN-22 | Tắt tunnel và rollback theo runbook | Route/SA/policy trở về trạng thái trước, lưu dấu vết và không có ngoại lệ rộng |

### 22.1. Mẫu ghi kết quả một ca

~~~text
Test ID:
Environment:
Date/time UTC:
Peer identity A/B:
IPsec mode and ESP transform:
Outer addresses and NAT-T:
Inner source/destination and protocol:
Negotiated IKE_SA/CHILD_SA summary (NO SECRETS):
Traffic selectors and route:
Expected allow/deny:
Observed encrypted/decrypted counters:
Application outcome:
Integrity/replay/MTU errors:
Owner/approval:
Rollback status:
~~~

**Kiểm chứng hai lớp:** (1) **Bảo mật đường truyền đúng**: mode, crypto, selectors, peer identity, routing. (2) **Ứng dụng và phân quyền đúng**: giao dịch hợp lệ thành công, traffic không có quyền bị từ chối, giám sát và audit không có vùng mù.

## 23. Giám sát và vận hành IPsec lâu dài

| Nhóm | Dấu hiệu cần theo dõi | Vì sao quan trọng |
| --- | --- | --- |
| **IKE** | IKE_SA up/down, auth failure, proposal mismatch, liveness timeout | Tìm lỗi đàm phán/peer identity |
| **CHILD_SA** | SPI/transform/mode/TS summary, rekey, inbound/outbound bytes | Xác nhận data plane và selector thực |
| **ESP** | Integrity failures, anti-replay drops, invalid SPI, sequence/ESN state | Phát hiện lỗi state, lưu lượng không hợp lệ hoặc reordering |
| **NAT-T** | UDP 4500 reachability, NAT mapping/keepalive, reconnect | Phát hiện lỗi chuyển mạng và NAT |
| **Path** | Route/VRF, WAN loss, latency, PMTU, fragmentation | Phát hiện routing asymmetry và black-hole MTU |
| **Performance** | Encryption CPU/offload, throughput, pps, tunnel concurrency | Tránh quá tải gateway khi mở rộng |
| **Remote access** | User/device authentication, MFA status, virtual IP assignment | Bảo vệ danh tính và least privilege |
| **Segmentation** | Rule hits/denies giữa Prod/Dev/Management và VPN pool | Chứng minh không có đường truy cập trái quyền |
| **Endpoint/cloud** | IPv4/IPv6 routes, DNS policy, effective cloud route tables | Phát hiện split-tunnel leak và đường bypass |
| **Governance** | Certificate/PSK lifecycle, firmware, change history, backups | Kiểm toán và giảm rủi ro mất quyền kiểm soát |

### 23.1. Cập nhật và khả năng tương thích

Khi nâng cấp VPN gateway/client:

1. Kiểm tra **mode, IKE/ESP algorithms, proposal set, traffic selectors** và certificate validation.
2. Xác định **cặp phiên bản client/server** được hỗ trợ, nhất là EAP/MFA và NAT-T trên thiết bị di động.
3. Đo tác động **rekey, tunnel reconnect, PMTU** trong lab.
4. Thử cả **full/split tunnel, IPv4/IPv6, DNS và route-based/policy-based**, theo đúng profile đang sử dụng.
5. Có rollback và kế hoạch thu hồi các transform/PSK cũ khi chuyển đổi thành công.

### 23.2. Theo dõi license/HA và giới hạn công suất

Một VPN cluster có thể có giới hạn **số tunnel, IKE SA, CHILD SA, kết nối đồng thời, CPU crypto, throughput có inspection và khả năng sync state**. Khi một node lỗi, node còn lại phải có năng lực thực sự để gánh số peers/traffic dự kiến. **Stateful failover không mặc nhiên bảo toàn mọi SA**; phải thử riêng các phiên IPsec site-to-site và remote access.

## 24. Những nhầm lẫn thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Tunnel mode mã hóa luôn outer IP header.” | Outer header phải nhìn thấy để route; **inner packet** mới được ESP tunnel bảo vệ khi bật encryption. |
| “Transport mode không mã hóa dữ liệu.” | ESP transport mode **có thể mã hóa upper-layer payload**; chỉ giữ IP header hiện hữu bên ngoài. |
| “Tunnel chỉ dành cho hai gateway, không dùng remote access.” | Remote client ↔ security gateway cũng thường dùng tunnel mode. |
| “Transport chỉ dùng cho hai ứng dụng trên cùng host.” | Nó dùng giữa IPsec endpoints và có thể bảo vệ GRE giữa routers. |
| “IKEv2 là tunnel mode.” | IKEv2 thương lượng SA; mode là thuộc tính cách bảo vệ dữ liệu. |
| “ESP và AH khác nhau chủ yếu vì tunnel/transport.” | ESP/AH là giao thức bảo vệ; cả hai có thể dùng tunnel hoặc transport. |
| “Thấy IPsec/ESP là chắc chắn có mã hóa.” | Cần xem transform và policy; ESP có những trường hợp integrity-only. |
| “NAT-T nghĩa là IPsec luôn chạy TCP/4500.” | NAT-T đi qua **UDP 4500**, ESP native là IP protocol 50. |
| “Đã có CHILD_SA nghĩa là mọi subnet đi được.” | TS, route, firewall, NAT và return path phải khớp. |
| “Full tunnel là một mode IPsec khác.” | Full/split tunnel là chính sách route/scope, không phải tunnel/transport mode. |
| “Tunnel tự bảo vệ toàn bộ laptop khi dùng Wi-Fi công cộng.” | Chỉ các gói đi vào tunnel được bảo vệ theo SA; cần endpoint security và DNS/IPv6 policy. |
| “IPsec bảo vệ toàn bộ traffic kể cả sau gateway.” | Bảo vệ ở **đoạn giữa hai IPsec endpoints**; sau decrypt cần kiểm soát khác. |
| “MSS clamp giải quyết được mọi lỗi MTU.” | MSS chỉ liên quan TCP ở những vị trí phù hợp; UDP/IPv6/fragmentation vẫn cần xét. |
| “uRPF/ACL không quan trọng khi đã có VPN.” | Source validation, route, zone policy vẫn quan trọng sau giải mã. |
| “VPN Connected chứng minh ứng dụng được phép truy cập.” | Cần kiểm tra CHILD_SA, counters hai chiều, route, DNS, TLS và authorization. |
| “Muốn chẩn đoán nhanh thì có thể chia sẻ khóa IPsec.” | Key material là bí mật; dùng logs đã redaction và lab riêng. |

## 25. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **Tunnel mode khác transport mode ở điểm quan trọng nhất nào?** Tunnel thêm outer IP và bảo vệ toàn inner IP packet; transport giữ IP header của packet hiện hữu và bảo vệ payload phía sau.
2. **Trên WAN của ESP tunnel mode, người quan sát thấy những IP nào?** Thông thường thấy **outer endpoints**; inner addresses được che khi ESP encryption đúng.
3. **ESP transport có thể bảo vệ TCP header không?** Có, vì TCP segment nằm trong phần payload ESP được bảo vệ theo mode/transform.
4. **Host-to-host transport có thay outer IP header không?** Không thêm outer IP do mode; địa chỉ nguồn/đích của packet hiện hữu vẫn ở header bên ngoài.
5. **Khi nào GRE over ESP transport có ý nghĩa?** Khi GRE đã cung cấp IP-in-IP/tunneling, còn IPsec bảo vệ GRE payload giữa endpoints.
6. **AH có mã hóa nội dung không?** Không; AH tập trung xác thực/toàn vẹn và anti-replay.
7. **Tại sao SA có thể UP nhưng LAN-to-LAN không thông?** Route, selectors, policy, NAT, MTU, return traffic hoặc ứng dụng có thể sai.
8. **IKEv2 làm nhiệm vụ gì?** Thương lượng và quản lý IKE_SA/CHILD_SA, keys, peer authentication và các tham số phù hợp.
9. **UDP 4500 dùng cho cơ chế nào?** NAT-T/ESP-over-UDP và IKE trên cổng đó theo quy định, không phải TCP VPN mặc định.
10. **Một thiết bị VPN từ xa cần gì ngoài encryption?** Identity/MFA, device policy, virtual IP, route, DNS, firewall authorization và audit.
11. **Bảo vệ ESP tunnel có thay được TLS/mTLS không?** Không nhất thiết; TLS/mTLS bảo vệ xác thực/dữ liệu ứng dụng ở đoạn khác và threat boundary khác.
12. **Lý do gói lớn có thể lỗi trong khi gói nhỏ thành công?** ESP/outer headers làm tăng kích thước, gây PMTU black-hole/fragmentation nếu mạng không xử lý đúng.
13. **Anti-replay kiểm tra điều gì?** Sequence number và cửa sổ nhận để hạn chế packet trùng/phát lại thuộc SA.
14. **Khi nào một gói hợp lệ có thể bị anti-replay drop?** Khi reordering/độ trễ vượt giới hạn của cơ chế nhận hoặc state không đồng bộ.
15. **Một IPv6 public flow có thể đi ngoài full-tunnel IPv4 không?** Có nếu IPv6 route/selectors/endpoint policy không được bao phủ đúng.
16. **Sau khi sửa tunnel phải test những loại quyền nào?** Cả traffic **ALLOW hợp lệ** và traffic **DENY bắt buộc**, tại các zone/identity đã được phê duyệt.

### Bài tập cuối chương

Một doanh nghiệp có hai văn phòng nối IPsec site-to-site, 150 nhân viên truy cập từ xa, hai môi trường Dev và Production trong cloud, cùng hệ thống DNS nội bộ. Một nhà cung cấp đề xuất “bật transport mode ở mọi nơi vì tiết kiệm header”.

Hãy lập bản thiết kế:

1. Vẽ **host-to-host transport**, **gateway-to-gateway tunnel**, **remote-client-to-gateway tunnel** và **GRE over transport**. Với mỗi hình, đánh dấu inner/outer IP.
2. Chọn mode cho từng đường và giải thích theo **điểm kết thúc IPsec, trust boundary, metadata cần che giấu**.
3. Tạo bảng **IKEv2 peer ID, authentication, ESP transform, traffic selectors, route, NAT-T**, không ghi secrets.
4. Xây dựng chính sách **remote-access split/full tunnel** cho IPv4, IPv6, DNS, EDR và quyền theo người dùng/thiết bị.
5. Tính **packet overhead giả định** của ESP tunnel có NAT-T so với transport không NAT-T; ghi rõ giới hạn.
6. Liệt kê **ít nhất 10 ca regression test**, bao gồm tunnel UP nhưng data fail, wrong mode, certificate mismatch, PMTU, HA, Dev → Prod DENY và VPN logout.
7. Đề xuất quy trình **key rotation, certificate renewal, rollback và giám sát SA** theo trách nhiệm từng nhóm.

**Gợi ý:** Câu trả lời tốt không chỉ “tunnel tăng một header, transport giảm một header”, mà phải giải thích **đường nào đang được bảo vệ và ai cần thực thi chính sách sau giải mã**.

## 26. Checklist triển khai IPsec tunnel/transport mode

- [ ] Đã xác định **IPsec endpoints** và luồng ứng dụng cần bảo vệ?
- [ ] Đã phân biệt **ESP/AH**, **IKEv2** và **tunnel/transport mode**?
- [ ] Với tunnel mode, outer IP và inner IP được chỉ rõ trong thiết kế?
- [ ] Với transport mode, có hiểu **IP header hiện hữu** và upper-layer data được bảo vệ?
- [ ] Nếu dùng GRE/L2TP hoặc overlay khác, thứ tự encapsulation và mode đúng theo hỗ trợ?
- [ ] IKE peer ID, certificate/PSK, trust chain và authentication được xác minh?
- [ ] IKE/ESP algorithms và key-exchange groups được phê duyệt, không dùng transform yếu vì tiện?
- [ ] CHILD_SA traffic selectors/route-based hoặc policy-based policy khớp hai đầu?
- [ ] Có kiểm tra **routes, VRF, NAT exemption, return path và asymmetric routing**?
- [ ] Nếu có NAT, đã kiểm chứng **UDP 500/4500, NAT-T và session lifetimes**?
- [ ] Firewall trên WAN phân biệt **ESP protocol 50** với TCP/UDP ports?
- [ ] Đã đo **ESP overhead, PMTU/MSS, IPv6 và nested tunnels**?
- [ ] Anti-replay, SA lifetime, rekey, peer liveness và lỗi integrity được giám sát?
- [ ] Với remote access, có kiểm tra **MFA, user identity, virtual IP, DNS, split/full tunnel, IPv4/IPv6**?
- [ ] Các vùng Dev/Prod/Management có **segmentation và DENY** sau khi decrypt?
- [ ] Không lộ key material/PSK/private key trong log, ticket, bản chụp hoặc tài liệu chia sẻ?
- [ ] Đã kiểm chứng traffic bằng **SA counters hai chiều và ứng dụng thực tế**, không chỉ trạng thái VPN UI?
- [ ] HA/failover có phương án cho mất SA/session, route hội tụ và client reconnect?
- [ ] Có owner, change approval, kiểm thử ALLOW/DENY, rollback và audit?
- [ ] Có runbook xử lý IKE, CHILD_SA, NAT-T, route, PMTU và lỗi ứng dụng?

**Kết luận:** **Tunnel mode** thêm outer IP header và bảo vệ cả **inner IP packet**, rất phù hợp khi IPsec gateway kết nối những mạng/thiết bị ở phía sau hoặc remote client vào hệ thống nội bộ. **Transport mode** bảo vệ payload của IP packet hiện hữu, phù hợp với host-to-host và một số kiến trúc có sẵn lớp tunnel như GRE. Để chọn đúng, phải xét **ESP/IKEv2/SA, traffic selectors, NAT-T, routing, MTU, khóa, danh tính, firewall và vùng tin cậy**. Đánh giá thành công không chỉ bằng **“VPN connected”**, mà bằng việc **dữ liệu được bảo vệ đúng đoạn, ứng dụng hợp lệ hoạt động, và truy cập không có quyền vẫn bị từ chối**.
