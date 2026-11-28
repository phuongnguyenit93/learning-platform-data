# Truy vết hostname, IP và certificate trong điều tra số trên mạng

Một SOC nhận cảnh báo máy chủ ứng dụng gửi nhiều kết nối TLS đến địa chỉ IP chưa có trong dependency inventory. Trong PCAP chỉ thấy địa chỉ nguồn, IP đích, cổng 443 và vài thông tin handshake. Người điều tra tra IP rồi thấy một nhà cung cấp CDN, kiểm tra DNS hiện tại thì một hostname lạ đang trỏ đến IP đó, trong khi công cụ tìm certificate lại trả nhiều tên miền khác nhau. **Có thể kết luận hostname lạ là đích truy cập thực tế, chủ sở hữu IP là kẻ tấn công và mọi domain trong certificate đều liên quan đến sự cố không?**

**Không thể kết luận như vậy chỉ từ một ánh xạ tĩnh.** Trong mạng hiện đại, quan hệ giữa **hostname ↔ DNS response ↔ IP ↔ TLS endpoint ↔ certificate ↔ workload/user** là quan hệ **phụ thuộc thời điểm, điểm quan sát và cơ chế chia sẻ hạ tầng**. Cloud load balancer, CDN, NAT, DNS split-horizon, IPv6, virtual hosting, QUIC và TLS 1.3 đều có thể làm bằng chứng trông khác kỳ vọng.

Bài học này hướng dẫn cách **truy vết và tương quan nhiều nguồn chứng cứ** nhằm trả lời những câu hỏi cụ thể:

- Hostname nào được client hỏi hoặc có ý định kết nối?
- Resolver đã trả lời IP nào **tại thời điểm sự cố**?
- Flow từ workload nào đã kết nối tới IP:port nào, trước/sau NAT?
- Client đã đề nghị hostname nào trong TLS SNI, nếu có và nếu quan sát được?
- Server đã trình bày certificate nào, chứng chỉ đó chứa những danh tính nào và có xác minh được không?
- Các dấu vết này chứng minh điều gì, **chưa chứng minh điều gì**, và phải bổ sung nguồn nào?

Chủ đề thuộc chương **Điều tra số trên mạng** của module **SECURITY_NETWORK_SECURITY**, gắn với bảo vệ DNS, TLS/PKI, firewall, VPN, phân đoạn mạng, IDS/IPS, network telemetry, packet capture, cloud và ứng phó sự cố.

> **Nguyên tắc quan trọng:** **Một hostname, một IP hay một certificate không tự định danh kẻ tấn công.** Chỉ đưa ra kết luận ở mức bằng chứng cho phép, ghi rõ thời gian, vantage point, nguồn dữ liệu và các cách giải thích thay thế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ quan hệ nhiều–nhiều và biến đổi theo thời gian giữa **hostname, DNS records, IP, TLS SNI và certificate**.
2. Phân biệt **hostname được truy vấn**, **DNS answer**, **hostname trong URL/HTTP Host**, **TLS SNI** và **Subject Alternative Name (SAN)**.
3. Thu thập bằng chứng từ **resolver logs, authoritative DNS, passive DNS, endpoint DNS cache, network flows, proxy, TLS logs, certificate inventory và Certificate Transparency (CT)** theo đúng phạm vi.
4. Giải thích vì sao **PTR/reverse DNS, ASN, WHOIS/RDAP, cùng IP, cùng certificate hoặc trùng CA issuer** không tự chứng minh quan hệ sở hữu hay actor attribution.
5. Đọc đúng certificate **subject/SAN, issuer, serial, validity, key usage/EKU, public key/SPKI, SHA-256 fingerprint và chain**.
6. Hiểu giới hạn quan sát **TLS 1.2 so với TLS 1.3, ECH, QUIC/HTTP/3, session resumption, proxy và mTLS**.
7. Dựng **timeline và correlation graph** nối DNS → flow → TLS → application → workload/identity với confidence và chain of custody.
8. Dùng các lệnh **chỉ đọc và ví dụ lab** để kiểm tra DNS, certificate và PCAP mà không mở rộng giám sát ngoài quyền.
9. Đánh giá IOC và threat intelligence bằng **time window, shared infrastructure, false positives, lifecycle changes và privacy**.
10. Viết báo cáo forensics có thể kiểm chứng, liệt kê giới hạn và đề xuất kiểm soát/điều tra tiếp.

## 2. Trước tiên: ta đang truy vết loại danh tính nào?

| Dấu vết | Ý nghĩa khi quan sát | Không tự chứng minh |
|---|---|---|
| **FQDN/hostname** | Tên mà một ứng dụng, người dùng hoặc resolver nhắc đến | Server nào thực sự nhận request hoặc ai sở hữu nội dung |
| **DNS QNAME/QTYPE** | Tên và kiểu bản ghi mà client/resolver truy vấn | Kết nối đã diễn ra hay client đã dùng DNS answer đó |
| **DNS answer** | Địa chỉ/alias được trả theo thời điểm và resolver | IP vẫn giống ở thời điểm khác, hoặc toàn bộ traffic đi qua IP ấy |
| **Destination IP:port** | Đích network tại một capture point | Hostname/virtual host thực hoặc URL đã gọi |
| **TLS SNI** | Tên server client khai báo trong handshake khi có/quan sát được | Hostname đã được server xác thực hoặc user thực là ai |
| **Certificate SAN** | Tên DNS/IP mà certificate yêu cầu được xác thực khi có trust validation phù hợp | Tất cả tên đó cùng đang phục vụ tại một IP |
| **Certificate fingerprint** | Digest của DER certificate cụ thể | Chủ vận hành không thay đổi hoặc cert đang được deploy ở thời điểm khác |
| **SPKI/public key hash** | Dấu vết public key của một certificate/key pair | Một tổ chức hay actor duy nhất sở hữu key đó trong mọi bối cảnh |
| **HTTP Host / :authority** | Tên virtual host ở HTTP layer nếu quan sát được | Được client gửi trung thực hoặc backend đã cho phép truy cập |
| **Cloud account/workload ID** | Danh tính infrastructure/workload từ inventory/audit | Một hành động là do người hợp lệ hay attacker điều khiển credential |

**Tách danh tính định tuyến với danh tính an ninh**: hostname và IP hỗ trợ tìm đường tới endpoint; certificate xác minh một danh tính TLS khi validation đúng; người dùng và workload còn cần **IdP, IAM, service identity, application logs và evidence khác**.

### 2.1. Một mapping không phải một chiều

~~~mermaid
flowchart LR
    A["api.orders.example.test"] --> D["DNS CNAME / A / AAAA theo thời gian"]
    B["static.orders.example.test"] --> D
    D --> I1["203.0.113.20"]
    D --> I2["2001:db8:20::20"]
    I1 --> V["Shared CDN / LB / reverse proxy"]
    I2 --> V
    V --> C1["Certificate X: SAN api.orders..."]
    V --> C2["Certificate Y: SAN static.orders..."]
    C1 -.-> HOST["Virtual-host selection: SNI / Host / policy"]
    C2 -.-> HOST
~~~

Sơ đồ minh họa, không phải topology thật. **Một hostname có nhiều A/AAAA**, một IP có thể phục vụ nhiều hostname/certificates, một certificate có nhiều SAN và một endpoint có thể đổi certificate khi rotate.

### 2.2. Ba câu hỏi điều tra khác nhau

1. **Network destination:** “Flow A đã gửi packet tới IP B:443 lúc 12:34 UTC?” — có thể xác minh bằng logs/PCAP ở đúng vantage point.
2. **Application destination:** “Client dự định nói với `api.orders.example.test`?” — cần DNS/SNI/proxy/app logs, và vẫn phải xét split DNS/redirect/proxy.
3. **Actor attribution:** “Ai điều khiển backend và vì sao traffic diễn ra?” — cần account/infrastructure ownership, endpoint/process evidence và hành vi, không đủ từ IP/ASN/certificate.

Lẫn lộn ba câu hỏi sẽ dẫn đến **chặn nhầm shared CDN**, quy sai một tên miền vô tội hoặc bỏ sót endpoint thực.

## 3. Quy trình điều tra theo thời gian, không theo ảnh chụp DNS hiện tại

### 3.1. Vì sao thời gian quan trọng?

Một hostname có thể trỏ tới `203.0.113.20` lúc 09:00 và `203.0.113.21` lúc 10:00 vì CDN failover, autoscaling, change hoặc TTL. Khi sự cố xảy ra lúc 09:15, lệnh DNS lookup lúc 15:00 **không phải bằng chứng xác nhận DNS response lúc 09:15**.

Điều quan trọng không chỉ là record đang tồn tại, mà là:

- **Timestamp** của query, response, connect, handshake, log và certificate observation.
- Resolver/view được dùng: corporate resolver, cloud private zone, public recursive hoặc local cache.
- Câu trả lời DNS thực tế, TTL, CNAME/HTTPS/SVCB chain khi liên quan.
- IP family IPv4/IPv6, DNS cache/happy-eyeballs và network path.
- DNS records **thay đổi theo thời gian** và certificate cũng có thể rotate.

~~~mermaid
sequenceDiagram
    participant C as Client app
    participant R as Recursive resolver
    participant D as Authoritative DNS
    participant E as CDN / endpoint
    C->>R: T0: A/AAAA lookup host H
    R->>D: Lookup nếu cache miss
    D-->>R: A/AAAA/CNAME, TTL
    R-->>C: T1: DNS answer có hiệu lực theo cache
    C->>E: T2: TCP/QUIC connect tới IP được chọn
    C->>E: T3: TLS handshake (SNI nếu có)
    E-->>C: Certificate/handshake; TLS validation
    C->>E: T4: HTTP/API request qua kênh bảo vệ
    Note over C,E: Các mốc trên không tự xuất hiện đầy đủ ở một PCAP
~~~

### 3.2. Lịch sử DNS không thể suy hoàn toàn từ một lần query

- **Recursive resolver cache:** response có thể đến từ cache, không tạo truy vấn lên authoritative lúc client gọi.
- **Client-side cache:** ứng dụng/OS/browser giữ kết quả; resolver log có thể không ghi request mới.
- **Negative caching:** NXDOMAIN/NODATA cũng có thời hạn cache theo DNS semantics; không suy rằng client luôn hỏi lại.
- **Split-horizon/private DNS:** cùng tên có thể trả địa chỉ khác cho các mạng, tài khoản hoặc resolver.
- **Geo/latency-aware CDN:** resolver ở hai vùng có thể nhận answers khác nhau.
- **Round-robin/weighted records:** client có thể chọn một trong nhiều IP.
- **DoH/DoT/DoQ hoặc hard-coded IP:** traditional UDP/53 logs có thể không thấy truy vấn.
- **Hosts file/service discovery:** một số ứng dụng không cần truy vấn DNS mạng để có IP.

**Khi thiếu historical DNS logs**, ghi rõ **không có bằng chứng về DNS answer thời điểm đó** thay vì dùng query hiện tại làm sự thật lịch sử.

## 4. Chọn nguồn chứng cứ và điểm quan sát

| Nguồn | Có thể trả lời | Điểm mù |
|---|---|---|
| **Endpoint resolver cache/logs** | Process/host hỏi hostname nào, response/TTL khi hỗ trợ | Cache chỉ là trạng thái gần đây, có thể bị xóa/ghi đè |
| **Recursive DNS logs** | QNAME/QTYPE, client/resolver identity, response codes/answers theo cấu hình | Không thấy browser DoH ngoài resolver, client cache hits |
| **Authoritative DNS logs/history** | Tên và records được phục vụ theo thời điểm | Không tự biết client nào dùng answer hoặc đã kết nối |
| **Passive DNS** | Quan sát lịch sử domain→IP ở các sensor | Dữ liệu thiếu vùng/private DNS, collection bias và timestamps |
| **PCAP/flow logs** | Source/destination IP, port, protocol, bytes, thời gian | Không tự biết hostname và identity; NAT/overlay có thể đổi view |
| **TLS proxy/ingress logs** | SNI, certificate/client auth, connection status khi nền tảng hỗ trợ | Có thể chỉ thấy proxy, không phải origin thật |
| **Application HTTP logs** | Host/:authority, URL/path, caller, request ID khi được ghi | Địa chỉ ở header có thể do client gửi; payload TLS cần endpoint logs |
| **Certificate Transparency** | Một chứng chỉ public-trust đã được ghi nhận trong CT | Không chứng minh cert từng được deploy, IP đích hay traffic đã xảy ra |
| **RDAP/registry/ASN/cloud inventory** | Allocation, routing organization, cloud resource ownership theo nguồn | Không gắn chắc một IP với actor hoặc tenant |
| **IdP/IAM/EDR/CNI** | User/workload/process/role và network context | Không giải thích hết một flow nếu telemetry thiếu |

### 4.1. View trước và sau NAT

~~~mermaid
flowchart LR
    POD["Pod orders-api: 10.2.1.7"] --> NAT["Node SNAT / cloud NAT"]
    NAT -->|"Public 203.0.113.50"| EDGE["Remote IP 198.51.100.20:443"]
    EN["CNI flow: source Pod identity"] -.-> POD
    NL["NAT translation log"] -.-> NAT
    FL["Cloud flow: public source"] -.-> EDGE
    APP["App/proxy: hostname + request ID"] -.-> POD
~~~

Các địa chỉ là ví dụ thuộc dải documentation. Nếu chỉ có cloud flow log ở sau SNAT, một IP public có thể đại diện cho **nhiều Pods hoặc máy chủ**. Muốn quy về đúng source cần **translation logs, port/time window, CNI/workload identity hoặc application trace**, không gán cả NAT IP cho một Pod.

### 4.2. Điểm quan sát trước và sau proxy

Một browser có thể gửi TLS tới **corporate proxy**, proxy lại thiết lập kết nối khác tới origin. PCAP trên client cho thấy IP của proxy, chứ không phải IP đích origin. Nếu proxy chấm dứt TLS, **hai kết nối có thể dùng certificates khác nhau** và HTTP Host headers có thể được gateway xử lý.

Vì vậy, sơ đồ hành trình cần tách:

~~~text
Client
  -> [TLS hop 1] ZTNA/HTTP proxy/gateway
  -> [TLS hop 2 or upstream connection] load balancer/CDN/origin
  -> application

Hostname/IP/certificate mỗi hop có thể khác nhau.
Luôn ghi hop nào tạo observation.
~~~

Không trộn certificate của proxy vào kết luận “origin đang dùng certificate này” nếu chưa có xác minh upstream.

## 5. Truy vết hostname qua DNS

### 5.1. Các record hay gặp

| Record | Vai trò | Cảnh báo khi diễn giải |
|---|---|---|
| **A** | IPv4 address cho tên | Nhiều A records, TTL/cache, CDN rotation |
| **AAAA** | IPv6 address | Nếu chỉ xem A sẽ bỏ lỡ IPv6 flows |
| **CNAME** | Alias canonical name theo DNS | Không tự chỉ owner của destination; cần theo chain |
| **PTR** | Reverse mapping IP→name | Chủ reverse zone có thể đặt tên khác; PTR không xác nhận forward DNS |
| **NS/SOA** | Delegation, authoritative zone metadata | DNS provider không nhất thiết là chủ nội dung ứng dụng |
| **MX** | Mail routing | Không phải endpoint HTTPS chính của domain |
| **TXT** | Metadata/SPF/verification và dữ liệu khác | TXT có thể chứa ngẫu nhiên, không tự chứng minh exfiltration |
| **CAA** | Gợi ý/quy tắc CA có thể cấp cert cho DNS name | Không chứng minh cert cụ thể đã phát hay server đang dùng cert |
| **HTTPS/SVCB** | Service binding, có thể chỉ endpoint/parameters hỗ trợ | Client support và resolution path phải được kiểm tra |
| **DS/DNSKEY/RRSIG** | DNSSEC signing/validation khi triển khai | DNSSEC xác thực DNS response chain, không xác định mục đích hợp pháp của server |

Không đánh đồng CNAME target với hostname được người dùng nhập hoặc HTTP virtual host cuối cùng. Khi theo chain, ghi **từng record và thời gian nhận**.

### 5.2. CNAME chain có thể dẫn tới shared infrastructure

~~~text
api.billing.example.test
  CNAME billing.edge.example.test
  CNAME region-a.cdn.example.test
  A     203.0.113.20
  AAAA  2001:db8:20::20

Ví dụ giả định trong môi trường lab.
Tên CDN trong chain chưa chứng minh CDN vận hành ứng dụng.
~~~

Một endpoint IP có thể phục vụ hàng trăm tenants. **Sự xuất hiện cùng CDN, ASN hoặc certificate issuer** thường là chỉ báo shared infrastructure, không phải bằng chứng các tên liên quan cùng actor.

### 5.3. Forward lookup và reverse lookup là hai phép khác

- **Forward DNS:** hostname → A/AAAA/CNAME.
- **Reverse DNS (PTR):** IP → một tên do zone reverse được quản lý.

Một PTR trả `node-123.cloud.example.test` **không chứng minh** flow đã gửi tới hostname đó, cũng không chứng minh hostname ban đầu đã resolve tới IP. **Forward-confirmed reverse DNS** có thể kiểm tra một phần nhất quán trong ngữ cảnh cụ thể, nhưng không biến PTR thành chứng thực quyền sở hữu hay danh tính ứng dụng.

### 5.4. Passive DNS và giới hạn lịch sử

Passive DNS services tổng hợp records đã được quan sát theo thời gian. Dữ liệu có thể hỗ trợ:

- Khi nào một tên **được sensor nào thấy** trỏ tới một IP.
- Domain có từng trỏ tới nhiều địa chỉ, quốc gia/ASN hoặc CDN khác không.
- Những hostname khác cùng chia sẻ một IP trong **time window** nào.
- Khi incident xảy ra, DNS response nào là **ứng viên** cần kiểm tra.

Nhưng **first seen/last seen của một nguồn passive DNS không nhất thiết là ngày bản ghi được tạo/xóa**. Nó chỉ thể hiện khi nguồn đó quan sát được. Private zones, internal resolvers, cache, geographic differences và missing collection có thể tạo khoảng trống.

### 5.5. Chỉ tra cứu domain được phê duyệt

Để thực hành, dùng zone do bạn quản lý hoặc tên thuộc **`example.test`** và resolver lab. Không cần quét hàng loạt tên miền thật, gửi hostname nhạy cảm tới dịch vụ public hoặc thu thập DNS của người khác chỉ để học kỹ thuật.

~~~bash
# Cú pháp dig tham khảo — chỉ chạy khi đã có resolver lab tại localhost.
# Các kết quả dưới đây có thể rỗng nếu lab chưa cấu hình zone .test.
dig @127.0.0.1 api.billing.example.test A +noall +answer
dig @127.0.0.1 api.billing.example.test AAAA +noall +answer
dig @127.0.0.1 api.billing.example.test CNAME +noall +answer
dig @127.0.0.1 api.billing.example.test HTTPS +noall +answer
~~~

Lệnh hiển thị answers của resolver lab **tại lúc chạy**, không dựng lại lịch sử DNS trong incident. Kết quả âm tính cũng cần xét negative caching, DNS policy và authority.

## 6. Truy vết IP: đích network, hạ tầng chia sẻ và sự biến động

### 6.1. IP là thuộc tính mạng, không phải định danh người điều khiển

Một IP có thể:

- Phục vụ **nhiều virtual hosts** qua SNI/HTTP Host.
- Là anycast IP của CDN/DNS, nhiều địa điểm mạng cùng công bố.
- Là egress NAT đại diện nhiều máy/Pods/tenants.
- Được cloud provider cấp lại cho tài khoản khác sau một thời gian.
- Là địa chỉ private trùng ở hai VPC/VNet độc lập.
- Có thể đổi vai trò từ load balancer sang một dịch vụ khác sau khi release.

Không suy một IP là “địa chỉ C2” vĩnh viễn từ một report cũ khi không có time window, ASN/cloud account và evidence bổ sung.

### 6.2. RDAP, ASN, WHOIS và route announcements

Thông tin từ registry/RDAP/ASN giúp xác định **đơn vị cấp phát và có thể là nhà mạng/cloud provider**, nhưng thường không chỉ rõ **tenant hoặc ứng dụng cụ thể**.

| Dữ liệu | Cho biết | Không cho biết chắc |
|---|---|---|
| RDAP/IP allocation | Dải địa chỉ và registry/organization | Actor đã phát request |
| ASN/BGP path | Đường routing hoặc mạng công bố prefix | Người sở hữu dữ liệu/ứng dụng sau proxy |
| GeoIP | Vị trí ước lượng theo dataset | Vị trí vật lý chính xác hoặc danh tính user |
| Passive DNS same-IP | Những domain từng xuất hiện cùng IP | Có liên hệ kiểm soát hay cùng chiến dịch |
| Cloud resource inventory | Owner của IP/ENI/LB trong tài khoản bạn quản lý | Client bên ngoài hoặc actor đằng sau compromised role |

**Quan hệ sở hữu IP, quyền điều khiển ứng dụng và actor attribution là ba cấp bằng chứng khác nhau**. Nếu cần kết luận quy trách nhiệm, phải phối hợp asset owner, provider, IAM/audit, application records và quy trình pháp lý/IR phù hợp.

### 6.3. IP family và NAT64

Các luồng cần xét:

- IPv4 A response và TCP/UDP IPv4 flow.
- IPv6 AAAA response và TCP/UDP IPv6 flow.
- Dual-stack Happy Eyeballs có thể thử/vào một address family khác với dự kiến.
- DNS64/NAT64 có thể tạo AAAA synthesis và translation, khiến IP ở client khác IP ở server.
- Load balancer/NAT theo từng chiều có thể tạo khác biệt giữa IP client, proxy và backend.

Vì vậy, dùng **A-only + IPv4-only PCAP** để kết luận “không có kết nối” là thiếu bằng chứng với ứng dụng dual-stack.

### 6.4. Khoảng thời gian và reuse

Khi IP bị cấp lại, một IOC theo IP có thể trở nên **lỗi thời**. Tổ chức cần:

1. Gắn IOC với **first known seen, last known seen, confidence, source**.
2. Ghi hostname, certificate/flow/application context tại thời điểm đó.
3. Có thời hạn review/expire và biết rủi ro block shared resources.
4. Kết hợp nhiều tín hiệu (principal, process, URL, resource ID, SNI, flow pattern) trước khi chặn.

Không áp một IP block vĩnh viễn chỉ vì danh sách đen bên ngoài từng đánh dấu nó ở quá khứ.

## 7. Certificate giúp xác minh điều gì?

Trong TLS, certificate thường gắn **public key** với **các danh tính được nêu trong chứng chỉ** và được cấp/chứng thực bởi CA hoặc PKI theo mô hình tin cậy. Với HTTPS thông thường, client cần kiểm tra **certificate chain**, **hostname match**, **validity**, **mục đích sử dụng** và các điều kiện trust/revocation phù hợp với chính sách.

Một certificate được trình bày trên một kết nối **không tự chứng minh người vận hành endpoint là ai**, cũng không khẳng định đích không chứa mã độc. Kẻ tấn công cũng có thể sở hữu domain riêng, xin một TLS certificate hợp lệ và triển khai phishing/C2 qua HTTPS.

### 7.1. Những trường quan trọng khi phân tích X.509

| Trường / thuộc tính | Mục đích điều tra | Sai lầm thường gặp |
|---|---|---|
| **Subject** | Các thuộc tính chủ thể được certificate ghi | Dùng CN làm nguồn matching chính thay SAN |
| **SAN dNSName / iPAddress** | Danh tính DNS/IP certificate yêu cầu xác thực | Coi mọi SAN là domain đã được server phục vụ/đã kết nối |
| **Issuer** | Tên đơn vị ký theo chain | Cho rằng hai cert cùng CA thuộc một actor |
| **Serial number** | Số serial do issuer gán | Coi serial duy nhất toàn Internet không xét issuer |
| **Not Before / Not After** | Khoảng hiệu lực chứng chỉ được khai báo | Dùng hiệu lực để suy cert đã deploy vào thời điểm đó |
| **Basic Constraints** | CA hay end-entity certificate | Tin một root/intermediate như leaf server cert |
| **Key Usage / EKU** | Khả năng sử dụng key và `serverAuth`/`clientAuth` khi cần | Chỉ nhìn hostname match, bỏ usage/trust policy |
| **Subject Public Key Info (SPKI)** | Thuật toán/key công khai và dấu vết key | Trùng public key = cùng người điều khiển chắc chắn |
| **Authority/Subject Key ID** | Gợi ý liên kết chain/khóa | Dùng như bằng chứng duy nhất về nguồn gốc |
| **AIA / CRL Distribution Points** | Metadata hỗ trợ tìm issuer/revocation | Suy chắc revocation status từ sự hiện diện URL |
| **SCT/CT-related evidence** | Quan sát issuance/logging trong CT ecosystem | Suy chứng chỉ đã từng được dùng tại IP quan sát |
| **SHA-256 fingerprint** | Nhận diện bytes của DER certificate cụ thể | Coi fingerprint không đổi sau certificate renewal |

**Trạng thái validation không thể suy từ một trường duy nhất.** Phải xét chain trust tới một trust anchor chấp nhận được, thời gian xác thực, hostname, usage, critical extensions và yêu cầu của ứng dụng/client.

### 7.2. SAN mới là trọng tâm hostname verification

Một certificate lab có thể có:

~~~text
Subject: CN=api.billing.example.test
X509v3 Subject Alternative Name:
  DNS:api.billing.example.test
  DNS:api.internal.example.test
  IP Address:192.0.2.20
Not Before: 2026-01-01 00:00:00 UTC
Not After : 2027-01-01 00:00:00 UTC
Issuer   : Example Lab CA
~~~

Ví dụ chỉ để đọc cấu trúc; **không phải certificate thật** và không chứng minh CA lab nằm trong trust store.

- **DNS SAN** dùng cho DNS name matching.
- **IP SAN** dùng cho việc xác minh địa chỉ IP khi client thực sự kết nối bằng IP và profile yêu cầu.
- **CN** không nên được coi là nguồn chính thay SAN trong TLS hostname verification hiện đại.
- **Wildcard `*.example.test`** không phải quyền xác thực mọi tên ở mọi độ sâu và không tự match apex `example.test`; quy tắc cụ thể phụ thuộc tiêu chuẩn/ứng dụng.
- Có SAN không có nghĩa server IP mà bạn nhìn thấy **đã phục vụ SAN đó** trong sự cố.

### 7.3. Kiểm tra chữ ký và chain không phải “certificate có issuer name đẹp”

Một chain thường có:

~~~mermaid
flowchart TD
    ROOT["Root CA / trust anchor"]
    INT["Intermediate CA"]
    LEAF["Leaf server certificate: SAN api.billing.example.test"]
    ROOT -->|"Ký intermediate theo chain"| INT
    INT -->|"Ký leaf theo chain"| LEAF
    CLIENT["TLS client trust policy"] -.->|"Validate chain, identity, time, usage"| LEAF
~~~

Trong PKI:

1. Certificate **leaf** mang public key dùng trong cơ chế xác thực endpoint.
2. Intermediate/root được đánh giá theo **đường dẫn chứng thực** và trust anchors được client chấp nhận.
3. Một attacker có thể gửi certificate chain giả; client không được chỉ tin chuỗi dữ liệu do server tự khai.
4. Certificate tự ký **có thể hợp lệ trong private PKI/lab** nếu được trust theo chính sách, nhưng không được mặc định tin trên Internet.
5. Certificate **đang trong thời hạn** chưa chắc valid nếu hostname sai, chain không được tin, usage không phù hợp hoặc revocation policy không đạt.

**Không tắt hostname/certificate verification** để làm evidence “TLS kết nối thành công”: nó chỉ chứng minh có thể thiết lập một kênh dưới các kiểm tra đã bị bỏ, không chứng minh danh tính peer.

## 8. Fingerprint, SPKI và certificate rotation

### 8.1. Fingerprint của certificate

SHA-256 fingerprint là hash của **DER-encoded certificate**. Thay đổi bất kỳ byte nào trong cert (ví dụ serial, SAN, validity, signature) thường làm fingerprint khác.

~~~text
Certificate v1 (serial A, validity X): fingerprint F1
Certificate v2 (serial B, validity Y): fingerprint F2

Có thể:
  SPKI v1 == SPKI v2 nếu cùng public key được tái sử dụng.
  F1 != F2 vì certificate được cấp mới.
~~~

Một IOC dựa hoàn toàn vào fingerprint leaf certificate có thể **hết phù hợp sau renewal**. Ngược lại, fingerprint giống nhau chứng minh bytes của certificate khớp, **không chứng minh một endpoint hiện tại vẫn đang dùng cert đó**, và private key tương ứng có thể đã bị sao chép.

### 8.2. SPKI hash và những gì nó bổ sung

Hash SPKI có thể giúp tìm các certificate khác nhau cùng sử dụng một public key. Nó hữu ích khi nghiên cứu rotation/reissue hoặc kiểm tra pinning, nhưng:

- Tái sử dụng key có thể là chính sách vận hành không tốt, chứ không tự là hành vi malicious.
- Một public key có thể được sao chép/khôi phục từ backup hoặc được dùng bởi nhiều endpoints dưới cùng owner.
- Nhiều certificates khác nhau có thể có key khác nhau nhưng vẫn phục vụ **cùng ứng dụng**.
- Cần phân biệt **certificate fingerprint** với **SPKI fingerprint** trong mọi báo cáo.

### 8.3. Serial và issuer

Certificate serial được diễn giải trong **phạm vi issuer**. Không liên kết hai cert bằng serial mà bỏ issuer/public key/chain. Một số nguồn lưu serial theo biểu diễn hex/decimal khác nhau; chuẩn hóa định dạng khi correlation.

### 8.4. Certificate Transparency (CT)

CT logs ghi nhận certificate/precertificate của hệ sinh thái public trust theo các quy tắc riêng, giúp phát hiện certificate issuance bất thường hoặc lịch sử SAN.

Một entry CT có thể hỗ trợ:

- Certificate mang **SAN nào** và key/issuer/validity ra sao.
- **Thời gian log** ghi nhận entry, phục vụ điều tra issuance history.
- Một domain từng có certificate khác trước/sau một mốc thay đổi.

Nhưng **CT không chứng minh**:

- Client thực tế đã kết nối tới domain.
- Certificate đã được deploy trên IP đang điều tra.
- Website tại domain đã tồn tại hoặc đã phục vụ nội dung.
- Domain/certificate nằm trong một chiến dịch tấn công.
- Private enterprise PKI được ghi public CT; đa số private certificates không nằm ở CT công cộng.

**CT là chứng cứ về issuance/logging, không phải chứng cứ network flow hoặc deploy state.** Cần kết hợp DNS lịch sử, TLS observation và infrastructure audit.

## 9. TLS SNI, HTTP Host và certificate: ba lớp cần phân biệt

Một request HTTPS thường có:

~~~text
DNS query:         api.billing.example.test A/AAAA
DNS answer:        203.0.113.20
Network connect:   203.0.113.20:443
TLS ClientHello:   SNI api.billing.example.test (nếu gửi và quan sát được)
TLS server:        certificate SAN api.billing.example.test
HTTP request:      Host/:authority api.billing.example.test (bên trong TLS)
Application:       route /payments, user/workload authorization
~~~

Đây là đường lý tưởng để minh họa, không phải lời hứa mọi field đều thấy được từ một PCAP.

### 9.1. TLS SNI là ý định khai báo của client, chưa phải xác minh server

**Server Name Indication (SNI)** trong ClientHello giúp server chọn virtual host/certificate. Nếu thấy SNI `api.billing.example.test` trong một ClientHello, có thể kết luận **client đã khai báo tên đó trong handshake được quan sát**. Tuy nhiên:

- Client có thể gửi SNI không đúng hoặc không gửi SNI.
- Server có thể trả default certificate, reject handshake hoặc chọn routing khác.
- Một proxy có thể gửi **SNI khác** trên hop upstream.
- ECH có thể che tên đích bên trong ClientHello; tên thấy được là **outer SNI**, không nhất thiết là inner target.
- QUIC/TLS có khác biệt transport và khả năng giải mã handshake.

**SNI không tự là bằng chứng certificate đã được xác minh.**

### 9.2. HTTP Host hoặc HTTP/2/3 :authority

Tên HTTP authority thường nằm **bên trong phần dữ liệu ứng dụng được bảo vệ bởi TLS**, vì vậy một observer trên mạng **không thể đọc trực tiếp nó trong HTTPS đúng triển khai** nếu không phải TLS endpoint hoặc không có quyền giải mã.

Với reverse proxy, gateway hay app logs đáng tin, ta có thể thấy HTTP authority, nhưng phải:

- Biết header đến từ **client**, proxy hay trusted server.
- Biết gateway có **overwrite/normalize** những forwarded headers không tin cậy hay không.
- Ghép request ID, upstream route và actual backend.
- Không dùng raw `X-Forwarded-Host` hoặc `X-User` từ Internet làm danh tính đã xác thực.

### 9.3. Certificate SAN và SNI có thể không khớp

Một SNI tên H đi kèm cert SAN không có H có thể dẫn tới **hostname validation failure** ở client có kiểm tra đúng. Nó cũng có thể là sự kiện probe, client bug, proxy config, load balancer default cert hoặc một nỗ lực tương tác với virtual hosting.

**Đừng kết luận MITM hoặc phishing chỉ từ sự khác nhau** nếu chưa có logs/chain validation, vị trí TLS termination và cấu hình server.

## 10. Khả năng quan sát khác nhau giữa TLS 1.2, TLS 1.3 và QUIC

Đây là điểm quan trọng trong network forensics: không phải mọi packet capture chứa cùng lượng thông tin certificate.

| Trường / tín hiệu | TLS 1.2 full handshake (thường) | TLS 1.3 full handshake | QUIC với TLS 1.3 |
|---|---|---|---|
| IP/UDP/TCP và timing | Thấy ở layer mạng theo vantage point | Thấy theo vantage point | Thấy UDP/QUIC outer metadata |
| SNI trong ClientHello không dùng ECH | Thường có thể nhìn trong passive capture | Thường có thể nhìn ClientHello trước ECH | Có thể phân tích QUIC Initial khi cấu hình/format hỗ trợ; ECH giới hạn inner name |
| Server certificate từ passive PCAP | **Thường nhìn được** trong full TLS 1.2 handshake khi chưa có cơ chế đặc biệt | **Bị mã hóa** trong handshake; không đọc được từ passive PCAP thông thường | TLS certificate được bảo vệ; không tự đọc được từ packet capture thông thường |
| Application HTTP Host/path/body | Mã hóa sau TLS establishment | Mã hóa | Mã hóa |
| Session resumption / 0-RTT | Có thể không có full certificate message | Có thể không có full certificate message, 0-RTT theo điều kiện | Có thể có resumption/0-RTT; yêu cầu decode đúng |
| Quan sát khi đứng ở TLS endpoint | Có thể xem cert/session details theo quyền | Có thể xem cert/session details theo quyền | Có thể xem cert/session details nếu endpoint logs hỗ trợ |

### 10.1. TLS 1.2: certificate thường có thể nhìn trên wire

Trong một **full TLS 1.2 handshake**, server certificate message thường được gửi trước khi handshake encryption hoàn tất, nên có thể được phân tích từ PCAP nếu:

- Capture có **đúng connection và phần đầu handshake**, không bỏ gói.
- Có đủ packet bytes, không bị snaplen truncation.
- Chưa bị proxy/tunnel encapsulation che mất inner TLS flow.
- Không phải một resumed handshake không gửi lại full certificate.

**Không thấy certificate trong TLS 1.2 PCAP** có thể do captured window, session resumption, wrong decode, NAT/packet loss hoặc traffic không phải TLS như dự kiến. Không tự kết luận “server không có certificate”.

### 10.2. TLS 1.3: Certificate message được mã hóa

Trong TLS 1.3, phần lớn server handshake messages **sau ServerHello**, bao gồm **Certificate**, được mã hóa bằng handshake traffic keys. Một observer chỉ có PCAP thụ động thông thường **không giải mã/đọc trực tiếp server certificate**.

Muốn biết certificate TLS 1.3 endpoint thực sự trình bày, có thể dùng:

- **TLS endpoint/reverse proxy logs** được phê duyệt.
- **Certificate inventory/deployment records** của host/load balancer.
- **Active TLS verification** tới endpoint lab/asset thuộc quyền, ghi rõ thời gian và SNI.
- PCAP có bí mật phiên chỉ trong trường hợp forensic authority cho phép và data handling được kiểm soát; không yêu cầu dump secrets tùy tiện.

**Không dùng `tshark -r file.pcapng` để khẳng định chắc sẽ trích được certificate server TLS 1.3 khi không có key material.**

### 10.3. QUIC và HTTP/3

QUIC chạy trên UDP, thường cổng 443 nhưng **port không chứng minh QUIC**. QUIC Initial packets có cơ chế bảo vệ khóa có thể được phân tích bởi dissector phù hợp, giúp nhìn một phần TLS ClientHello khi không ECH và không có giới hạn capture. Phần ứng dụng HTTP/3 và TLS certificate **không tự hiện plaintext** trong passive PCAP thông thường.

Không dùng capture filter chỉ `tcp port 443` rồi tuyên bố không có HTTPS; HTTP/3 có thể chạy qua **UDP/443**, và ứng dụng có thể dùng port khác.

### 10.4. ECH và outer/inner SNI

**Encrypted ClientHello (ECH)**, khi thực sự được client/server hỗ trợ và đàm phán thành công, che những phần nhạy cảm của ClientHello, bao gồm **inner server name**; outer ClientHello có thể mang một tên public khác.

Vì vậy:

- Observer không nên coi outer SNI là hostname ứng dụng cuối cùng.
- Không có ECH ở một kết nối không có nghĩa hostname chắc được ghi ở mọi sensor.
- DNS HTTPS/SVCB records có thể mang thông tin ECH config trong những triển khai hỗ trợ, nhưng record **không chứng minh một phiên đã dùng ECH**.
- Muốn xác định origin/authority có thể cần endpoint, proxy/app logs và permission tương ứng.

### 10.5. mTLS và proxy TLS termination

Nếu client và server dùng mTLS, cả hai có thể dùng certificates để xác thực peer. Nhưng trong TLS 1.3, client/server certificate messages cũng có thể không đọc được từ passive PCAP. Một request qua service mesh sidecar, ingress gateway hoặc ZTNA connector có **nhiều TLS endpoints**:

~~~mermaid
flowchart LR
    B["Browser"] -->|"TLS A: cert Gateway"| G["Ingress / ZTNA Gateway"]
    G -->|"mTLS B: workloads cert"| P["Service mesh proxy"]
    P -->|"Local / application connection"| APP["Application"]
    C1["Certificate A"] -.-> G
    C2["Certificate B"] -.-> P
~~~

**Chỉ certificate của gateway được browser xác minh không chứng minh hop gateway→service được bảo vệ bằng mTLS.** Cũng không được suy certificate trên mTLS proxy là certificate mà browser đã thấy.

## 11. Kết luận về certificate: phân biệt các mức độ bằng chứng

| Bằng chứng có được | Kết luận có thể nêu | Không được nâng thành |
|---|---|---|
| CT entry cho SAN H | Certificate/precertificate mang H đã được CT ghi nhận | H đã deploy/có traffic với IP X |
| Certificate file trong inventory | Tài sản có artifact certificate đó | Endpoint thực đang phục vụ cert lúc incident |
| TLS 1.2 PCAP full handshake có cert F | Server hop quan sát đã gửi bytes certificate F | Client đã validate thành công |
| Active TLS connection lab với SNI H trả cert F | Endpoint tại thời điểm kiểm tra trình bày F | Incident lịch sử đã dùng cùng F |
| Client log xác nhận chain + H được verify | Client đã xác minh theo trust policy tại thời điểm log | Ứng dụng an toàn, không bị chiếm |
| Same certificate xuất hiện trên nhiều hosts | Có thể chia sẻ cert/key hoặc shared hosting | Tất cả hosts do cùng attacker điều khiển |
| Certificate hết hạn ở inventory | Artifact hết hạn | Mọi client kết nối đều đã nhận cert đó và thất bại |
| Certificate fingerprint đổi | Artifact certificate đã đổi | Chắc chắn server ownership đổi |

Trong báo cáo forensics, dùng đúng động từ: **“đã quan sát”, “đã xác minh tại thời điểm T”, “có tương quan”, “phù hợp với giả thuyết”**. Không dùng “chứng minh actor X” khi evidence mới là shared CDN và một certificate có issuer phổ biến.

## 12. Thu thập chứng cứ: ưu tiên dữ liệu có sẵn, kiểm soát hành động chủ động

**Digital forensics** cần dữ liệu nguyên gốc, nguồn đáng tin và quá trình xử lý có thể giải thích. Chọn **read-only logs/PCAP đã tồn tại** trước khi tạo network queries mới; mỗi active DNS/TLS check chỉ phản ánh **thời điểm truy vấn hiện tại**, và có thể tạo log/network traffic mới.

### 12.1. Quy trình thu thập được ủy quyền

1. Tạo incident/ticket ID, nêu câu hỏi và phạm vi assets/accounts được phép.
2. Ghi thời điểm, timezone, clock offset, collector và quyền thu thập.
3. Xác định logs có vòng đời ngắn cần export sớm: recursive DNS, VPC flow, proxy, edge, CNI, TLS gateway.
4. Bảo toàn raw evidence trong kho access-controlled, có hash, retention và access audit.
5. Phân tích trên **bản sao**, không chỉnh sửa raw PCAP, certificate hoặc logs gốc.
6. Liên kết evidence bằng nguồn, asset ID, timestamp, client connection/request ID và IP/port translations.
7. Phân biệt active observations mới với historical logs từ thời điểm incident.
8. Ghi gaps và alternative explanations; tránh bù chỗ trống bằng truy vấn DNS/CT hiện tại.

### 12.2. Evidence record nên có những trường nào?

~~~yaml
# Dữ liệu minh họa, không phải schema bắt buộc của SIEM.
incidentId: NET-FOR-EXAMPLE-004
evidenceId: E07
sourceType: recursive-dns-log
sourceSystem: internal-resolver-lab-a
collector: authorized-analyst
eventTimeUtc: "2026-11-28T09:12:03.240Z"
ingestedTimeUtc: "2026-11-28T09:12:05.001Z"
collectedTimeUtc: "2026-11-28T09:20:00Z"
vantagePoint: "client-side DNS resolver"
rawArtifact: "stored-in-restricted-evidence-vault"
integrity: "SHA-256 digest recorded separately from actual file bytes"
clockOffset: "documented"
fieldsPresent:
  - query-name
  - query-type
  - response-addresses
  - client-identity
limitations:
  - "Only queries handled by this resolver are visible"
  - "Client/browser caches and external DoH are not necessarily visible"
dataSensitivity: internal-confidential
~~~

Ở hồ sơ evidence thật, trường hash cần **giá trị SHA-256 thực tế**, không dùng mô tả “recorded separately” thay digest. Không ghi raw access token, session cookie hoặc private key trong metadata.

## 13. Các lệnh DNS chỉ đọc cho môi trường lab

Các ví dụ sử dụng **zone `example.test`, IP documentation và resolver localhost**. Chỉ dùng trên tài sản/lab được cấp quyền. Chúng **không được thực thi trong quá trình biên soạn bài**. Active DNS queries vẫn tạo mạng traffic nên không dùng để dò quét domain không thuộc quyền.

### 13.1. Linux: truy vấn resolver chỉ định

~~~bash
# Chỉ đọc answer của resolver DNS lab nếu đã cấu hình localhost:53.
# Không khẳng định kết quả là bản ghi tại thời điểm sự cố trong quá khứ.
dig @127.0.0.1 api.billing.example.test A +noall +answer
dig @127.0.0.1 api.billing.example.test AAAA +noall +answer
dig @127.0.0.1 api.billing.example.test CNAME +noall +answer
dig @127.0.0.1 api.billing.example.test HTTPS +noall +answer

# PTR cho một IPv4 lab/documentation address:
dig @127.0.0.1 -x 192.0.2.20 +noall +answer
~~~

Muốn thấy status/TTL/answer context:

~~~bash
# Không dùng +short nếu cần đọc response code/flags trong điều tra.
dig @127.0.0.1 api.billing.example.test A +noall +comments +answer

# Truy vấn kiểu TXT trong lab khi được phép.
dig @127.0.0.1 api.billing.example.test TXT +noall +answer
~~~

**DNS response từ resolver `127.0.0.1` chỉ có ý nghĩa nếu một DNS service lab thực sự đang lắng nghe ở đó.** Không có record hoặc resolver không chạy là kết quả bình thường của ví dụ, không phải bằng chứng DNS server production hỏng.

### 13.2. Windows PowerShell: resolver và cache

~~~powershell
# Một số lệnh cần OS/version phù hợp; chỉ đọc.
Get-DnsClientServerAddress
Get-DnsClientCache

# Truy vấn DNS server lab tại localhost, nếu có.
Resolve-DnsName -Name "api.billing.example.test" -Type A -Server 127.0.0.1
Resolve-DnsName -Name "api.billing.example.test" -Type AAAA -Server 127.0.0.1
Resolve-DnsName -Name "api.billing.example.test" -Type CNAME -Server 127.0.0.1
~~~

**Giới hạn:** browser/app có thể có DNS cache riêng hoặc dùng DoH; `Get-DnsClientCache` không chắc hiện mọi ánh xạ đã dùng. Tránh làm sạch cache (`ipconfig /flushdns`) trước khi thu bằng chứng nếu có thể làm mất state đang cần điều tra.

### 13.3. Xem đường mạng tại host

~~~bash
# Không thay route/NIC; chỉ xem trạng thái trên Linux.
ip -br address
ip -4 route show
ip -6 route show
ip -s link show
ss -tan
~~~

~~~powershell
# Không thay firewall/VPN route.
Get-NetIPConfiguration
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State
Get-Date -Format o
~~~

Một socket chỉ có `RemoteAddress` và port **không khẳng định hostname**. Để gắn đúng tiến trình/user, dùng endpoint/EDR/process telemetry có quyền và log correlation; PID có thể tái sử dụng, cần timestamp và process instance identity.

## 14. Các lệnh chỉ đọc để kiểm tra certificate lab

### 14.1. Phân tích một file X.509 đã được phê duyệt

Giả sử có file **`./approved-lab-server.pem`** do nhóm lab cung cấp; không đưa certificate private key hoặc credential vào bài thực hành.

~~~bash
# Thông tin định danh leaf certificate và hash certificate.
openssl x509 \
  -in ./approved-lab-server.pem \
  -noout \
  -subject -issuer -serial -dates -fingerprint -sha256

# Hiển thị Subject Alternative Names riêng.
openssl x509 \
  -in ./approved-lab-server.pem \
  -noout -ext subjectAltName

# Thông tin chi tiết về extensions/chain-related fields:
openssl x509 \
  -in ./approved-lab-server.pem \
  -noout -text
~~~

**`-text` có thể in toàn bộ certificate public contents và định danh**, cần xem sensitivity trước khi đưa output vào ticket. Certificate public không phải private key, nhưng SANs/organization metadata vẫn có thể lộ topology hoặc môi trường nội bộ.

### 14.2. Tính SPKI SHA-256 khác certificate fingerprint

~~~bash
# Extract public key/SPKI của certificate rồi hash bản DER SPKI.
# Không in hoặc đọc private key.
openssl x509 -in ./approved-lab-server.pem -pubkey -noout |
  openssl pkey -pubin -outform DER |
  openssl dgst -sha256
~~~

**`openssl x509 -fingerprint -sha256` hash certificate**, còn pipeline trên hash **public key/SPKI**. Không dùng chung một trường `fingerprint` không ghi rõ loại.

### 14.3. Xác minh TLS với endpoint lab hiện tại

~~~bash
# Chỉ dùng trên TLS server lab tại localhost:8443 do bạn quản lý.
# CA file chứa certificate CA lab đã được phê duyệt; không có private keys.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername api.billing.example.test \
  -verify_hostname api.billing.example.test \
  -verify_return_error \
  -CAfile ./approved-lab-root-ca.pem \
  -showcerts < /dev/null
~~~

**Lưu ý:**

- Cần kiểm tra cả **verify return code/handshake result**, chain, certificate validity, hostname, trust policy và endpoint đang phục vụ; một command exit code không phản ánh mọi policy của ứng dụng.
- `-servername` đặt SNI; `-verify_hostname` yêu cầu xác minh hostname; đây là **hai chức năng khác nhau**.
- `-CAfile` sử dụng một CA lab chấp nhận được; không nên thay nó bằng bất cứ certificate ngẫu nhiên nào chỉ để “PASS”.
- Kiểm tra ở **thời điểm hiện tại** không chứng minh cùng certificate đã được server dùng tại thời điểm incident cũ.
- Nếu hệ thống yêu cầu client certificate/mTLS, lab phải cung cấp một identity được phê duyệt; không vô hiệu xác thực để thử.
- Việc `-showcerts` hiển thị chuỗi certificate do endpoint gửi **không tự chứng minh toàn chain trusted**; phải xem kết quả validation.

### 14.4. Windows: hash và lưu evidence an toàn

~~~powershell
# Bảo toàn file PEM được phép, hash để đối chiếu tính toàn vẹn.
Get-FileHash -LiteralPath ".\approved-lab-server.pem" -Algorithm SHA256

# Hiển thị thời điểm thu evidence của workstation.
Get-Date -Format o
~~~

**SHA-256 của file PEM** (bao gồm text/base64/newlines) có thể **khác SHA-256 fingerprint của DER certificate** nếu PEM formatting thay đổi. Trong báo cáo ghi chính xác **đối tượng đã hash**: raw evidence file, DER cert hay DER SPKI.

## 15. Phân tích DNS/TLS từ PCAP có sẵn

Chỉ làm với **PCAP/PCAPNG đã được thu thập hợp lệ** và lưu trong kho được phép. Không tự bắt thêm toàn bộ network traffic hoặc giải mã sessions không có authorization.

### 15.1. Đọc flow summary bằng tcpdump

~~~bash
# PCAP lab đã có; chỉ đọc file, không bắt live traffic.
tcpdump -nn -r ./approved-lab-traffic.pcap \
  'host 192.0.2.10 and host 203.0.113.20 and (tcp port 443 or udp port 443)'
~~~

Không dùng display/capture filter quá hẹp làm bằng chứng phủ định cho những packet đã bị loại **trong quá trình thu ban đầu**. PCAP trống có thể do wrong interface, wrong filter, NAT, fragmentation, IPv6 hoặc packet loss.

### 15.2. Xem DNS fields từ PCAP lab bằng TShark

~~~bash
# -Y là display filter trên file đã có; không thay bytes file gốc.
# QNAME có thể có cả query và response, cần xét dns.flags.response.
tshark -r ./approved-lab-traffic.pcap \
  -Y 'dns' \
  -T fields \
  -e frame.time_epoch \
  -e ip.src -e ip.dst \
  -e dns.flags.response \
  -e dns.qry.name \
  -e dns.a -e dns.aaaa -e dns.cname
~~~

**Giới hạn:** fields có thể trống khi traffic là IPv6, protocol không decode được, gói bị cắt hoặc DNS đi trong DoH/DoT/DoQ. Với IPv6 cần thêm `ipv6.src`/`ipv6.dst`. Không dùng một dòng output của TShark để kết luận cả historical DNS timeline nếu capture không bao phủ.

### 15.3. Xem TLS ClientHello/SNI từ PCAP lab

~~~bash
# Chỉ hiển thị những ClientHello có thể được dissector nhận dạng.
# Với ECH, trường này có thể là outer name hoặc không có inner name.
tshark -r ./approved-lab-traffic.pcap \
  -Y 'tls.handshake.type == 1' \
  -T fields \
  -e frame.time_epoch \
  -e ip.dst -e ipv6.dst \
  -e tcp.dstport \
  -e tls.handshake.extensions_server_name
~~~

Các trường là ví dụ thông dụng, **tên field và khả năng decode phụ thuộc phiên bản Wireshark/TShark, packet capture và protocol**. Output trống không có nghĩa client không dùng TLS hoặc “không gửi SNI”; có thể PCAP không chứa ClientHello, ECH đang che tên, traffic là QUIC hoặc dissector chưa nhận dạng.

### 15.4. Không trích certificate TLS 1.3 bằng cách suy từ handshake cũ

Trước khi cố đọc certificate trong PCAP, xác định:

1. Flow là **TLS 1.2 hay 1.3**, TCP hay QUIC, có proxy/tunnel không?
2. Đã thu **full handshake** hay chỉ connection đã tồn tại?
3. TLS 1.3 certificate bị mã hóa — observer không có keys/endpoint logs thì không đọc plaintext cert.
4. Nếu TLS 1.2, có Certificate handshake message đầy đủ không, file có bị snaplen/truncation/drop?
5. Nếu có nhiều proxy hops, cert nhìn thấy thuộc **hop nào**?

**Không dùng công cụ tự động báo “unknown cert” làm bằng chứng server không có chứng chỉ**.

### 15.5. Có thể khớp flow và DNS bằng 5-tuple như thế nào?

Một flow network thường được mô tả bằng:

~~~text
Transport protocol:
  TCP hoặc UDP
Source IP / port:
  192.0.2.10:51324
Destination IP / port:
  203.0.113.20:443
Start/end times:
  timestamps có timezone
Network vantage:
  before-NAT client NIC / after-NAT gateway / cloud flow logger
~~~

DNS log không chứa TCP source port của flow; cần **client identity/process logs, timing và address selection** để nối. Trong mạng có shared DNS resolver, hàng nghìn clients hỏi cùng tên, nên **QNAME cùng IP trong vài giây không đủ để khẳng định cùng user**.

## 16. Dựng correlation timeline: từ rời rạc thành lập luận

### 16.1. Case study mô phỏng

Tất cả dữ liệu dưới đây **hư cấu**, sử dụng IP/tên dành cho tài liệu:

| UTC | Nguồn | Observation |
|---|---|---|
| 09:12:03.240 | Corporate DNS resolver | Client asset A hỏi `api.billing.example.test A` |
| 09:12:03.251 | Resolver response | CNAME tới `region-a.cdn.example.test`; A `203.0.113.20`, TTL quan sát là 60s |
| 09:12:04.010 | Endpoint process telemetry | Process `orders-api` của asset A mở TCP connection |
| 09:12:04.025 | Egress firewall | Source trước NAT là asset A, destination `203.0.113.20:443`, allow |
| 09:12:04.032 | Client-side PCAP | TLS ClientHello có SNI `api.billing.example.test` (không ECH trong lab) |
| 09:12:04.090 | TLS client/gateway log | Handshake validation thành công, certificate fingerprint SHA-256 được ghi |
| 09:12:04.150 | Application trace | Request ID `req-lab-901` tới billing API, response 200 |
| 11:30:00.000 | Active DNS lookup mới | Hostname đã chuyển sang một IP khác |

**Phân tích thận trọng:**

1. Resolver đã trả `203.0.113.20` cho client A tại 09:12:03, theo log trong phạm vi.
2. Process `orders-api` trên asset A đã mở kết nối tới `203.0.113.20:443` ngay sau đó, có sự phù hợp về thời gian và đích.
3. ClientHello khai báo SNI `api.billing.example.test` trên flow quan sát, tăng khả năng hostname đó liên quan kết nối.
4. TLS gateway/client log ghi validation và certificate fingerprint; **không được đọc fingerprint từ passive TLS 1.3 PCAP** nếu chưa có keys.
5. Application trace nối request ID tới hành vi nghiệp vụ; giờ đây có evidence tốt hơn chỉ IP/hostname.
6. DNS lookup mới lúc 11:30 **không phủ định** answer 09:12; đó có thể là CDN rotation.

### 16.2. Những điều case study vẫn không chứng minh

- Owner của CDN IP chính là chủ sản phẩm hoặc actor đứng sau mọi tenant trên IP.
- Không có request khác trên host khi telemetry chỉ nhìn một process/session.
- Toàn bộ payload đã đến origin không thay đổi khi có gateway/proxy có quyền xử lý.
- Token/user ở request đã được cấp quyền nghiệp vụ chỉ vì TLS thành công.
- Không có exfiltration nếu chỉ biết HTTP 200 và một flow.

Muốn nâng confidence về **data impact**, cần application/DB audit, data classification, endpoint process context và identity events.

### 16.3. Correlation graph

~~~mermaid
flowchart TD
    DNS["E1: resolver response at 09:12:03"] -->|"A=203.0.113.20"| IP["IP 203.0.113.20"]
    PROCESS["E2: orders-api process telemetry"] -->|"Opened connection"| FLOW["E3: TCP flow: client A → IP:443"]
    IP --> FLOW
    SNI["E4: observed TLS ClientHello SNI"] -->|"Matches requested hostname"| FLOW
    TLS["E5: endpoint verified certificate SAN"] -->|"Peer identity validated at hop"| FLOW
    FLOW --> REQ["E6: app request ID req-lab-901"]
    REQ --> IMP["Application authorization & data-impact analysis"]
    CT["CT historical certificate entry"] -.->|"Issuance context only"| TLS
~~~

Solid lines minh họa **liên kết theo evidence cụ thể** trong lab; dashed line thể hiện CT chỉ bổ sung issuance context. Khi triển khai thật, mỗi cạnh cần provenance, thời gian, phương pháp matching và alternative explanations.

## 17. Confidence và provenance: tránh nhảy cóc trong kết luận

Đề xuất dùng mức định tính **Low/Medium/High** để trao đổi (không phải thang điểm chuẩn):

| Kết luận | Bằng chứng | Confidence minh họa |
|---|---|---|
| “Có một record DNS hiện tại trỏ tới IP B” | Một query active ở resolver R | Cao **chỉ tại R và thời điểm query**, không nói lịch sử |
| “Client A nhận DNS answer H→B tại T” | Resolver log có source client, answer và timestamp | Cao nếu logs/clock/scope đáng tin |
| “Client A đã kết nối IP B:443” | Endpoint flow + firewall logs khớp trước/sau NAT | Cao nếu 5-tuple và time đồng bộ |
| “Flow dùng hostname H” | DNS H→B gần T + SNI H + app request ID | Cao hơn từng tín hiệu đơn lẻ, vẫn xét proxy/ECH |
| “Server trình bày cert F tại T” | TLS endpoint log hoặc TLS 1.2 full handshake có F | Phụ thuộc hop, collection và log trust |
| “Cert F được CA/hostname validation PASS” | Client verification record và trust policy | Cao theo policy của client tại T |
| “IP B thuộc actor X” | Chỉ RDAP/ASN hoặc same-IP passive DNS | **Thấp/không đủ** để quy actor |
| “Có data exfiltration” | Chỉ outbound bytes tới B | **Không đủ**; cần app/data/process evidence |

### 17.1. Công thức tư duy

~~~text
Observation
  + timestamp và time uncertainty
  + vantage point
  + evidence integrity/source reliability
  + matching identifiers
  + negative/alternative hypotheses
  = justified inference (không tự là actor attribution)
~~~

Đây là checklist lập luận, không phải phép toán xác suất. **Confidence** được củng cố khi có **nhiều nguồn độc lập tương quan**; hai dashboard cùng lấy một log feed không phải hai nguồn độc lập.

### 17.2. Khi gặp chứng cứ mâu thuẫn

Ví dụ DNS resolver log cho H→B, nhưng application trace nói request tới H2:

- Browser/client có dùng cache hoặc DoH riêng không?
- Proxy upstream đã rewrite Host/SNI hoặc route sang H2 không?
- DNS query H có phải của **cùng process/request** không?
- Hai logs đã được chuẩn hóa timezone và NAT source chưa?
- Trên cùng IP có nhiều virtual hosts không?
- Có redirection, Alt-Svc, HTTPS/SVCB record hoặc connection coalescing (khi client/protocol cho phép) không?

**Không chọn evidence “đẹp nhất” rồi bỏ log trái ngược**. Ghi rõ conflict, đưa giả thuyết cần kiểm tra và giữ confidence tương ứng.

## 18. Chain of custody và đạo đức điều tra

### 18.1. Bảo vệ dữ liệu network forensics

DNS, TLS metadata và PCAP đều có thể nhạy cảm: tên miền truy cập có thể tiết lộ hoạt động nhân viên, địa chỉ nội bộ/topology, tenant IDs; certificates có thể lộ SANs của hệ thống chưa công khai.

- Dùng **scope/approval** cho tài sản và thời gian, không quét domain/host của bên khác.
- Ưu tiên **flow/metadata và logs được giới hạn** thay raw payload nếu đủ câu trả lời.
- Không đưa access tokens, cookies, TLS private keys, session key logs hoặc PII vào chat/ticket mở.
- Lưu evidence trong kho có encryption, RBAC, access audit và retention.
- Tạo SHA-256 digest của **raw artifact**, ghi hash source và mọi lần chuyển giao.
- Phân tích trên bản sao, không sửa PCAP/logs/cert gốc để hợp một giả thuyết.
- Nếu có legal hold hoặc nghĩa vụ privacy, phối hợp bộ phận có thẩm quyền.

### 18.2. Vì sao redaction có giới hạn?

Thay IP bằng giá trị băm hoặc xóa hostname ở một báo cáo có thể không đảm bảo ẩn danh:

- Các mốc thời gian và lưu lượng có thể tái liên kết với user.
- ASN/domain/path/metadata khác còn đủ suy danh tính.
- Hash IP trong không gian nhỏ dễ bị brute force nếu không có bảo vệ thích hợp.
- Cắt nội dung gói có thể làm mất evidence/offset và tạo sai khác forensic.

Hãy tách **bản gốc được bảo quản** với **bản chia sẻ được rút gọn**, ghi rõ các trường bị xóa và tác động đến kết luận.

## 19. Những trường hợp đặc biệt thường dẫn tới quy kết nhầm

### 19.1. Cùng một IP nhưng khác tenant

Một IP CDN có thể được dùng đồng thời bởi:

~~~text
cdn IP 203.0.113.20
  - shop-a.example.test
  - docs-b.example.test
  - api.billing.example.test
~~~

Nếu DNS/CT cho thấy ba tên liên quan cùng IP, **chúng không tự thuộc một tổ chức hoặc actor**. Trên CDN dùng SNI/Host routing, client gọi một tenant cụ thể cần được chứng minh bằng request/proxy logs hoặc các tín hiệu TLS phù hợp.

**Hệ quả khi containment:** block toàn bộ IP có thể ảnh hưởng nhiều ứng dụng hợp lệ. Với một hostname nghi độc hại, chỉ sử dụng DNS/proxy/application policy hoặc IP block sau đánh giá phạm vi và khả năng chia sẻ hạ tầng.

### 19.2. Cùng certificate nhưng không cùng backend

Một wildcard certificate có thể được triển khai trên nhiều server/regions; cert bị copy cũng có thể xuất hiện trên hệ thống không thuộc owner. Cùng certificate có thể giúp liên kết **credential artifact** nhưng không tự chứng minh mọi IP cùng backend hoặc cùng kẻ điều khiển.

Ngược lại, một service có thể dùng **certificates khác nhau ở nhiều edge nodes**, nên fingerprint khác nhau không phải chắc domain đã bị chiếm.

### 19.3. DNS rebinding

DNS rebinding là một lớp kỹ thuật trong đó DNS name có thể trả **địa chỉ khác theo thời gian**, gây vấn đề khi một ứng dụng gắn quyền truy cập vào hostname nhưng không bảo vệ đích IP/tài nguyên tương ứng. Trong điều tra:

- Cần historical DNS responses, TTL và thời gian connection.
- Không suy một domain “an toàn” hiện tại vì query hôm nay trả public IP.
- Kiểm tra ứng dụng có **kiểm tra lại đích sau resolution/redirect** và bảo vệ SSRF hay không.
- Không coi mọi IP rotation/CDN behavior là malicious rebinding.

### 19.4. Domain fronting và sai khác SNI/HTTP authority

Một số cấu hình proxy/CDN và clients có thể khiến **SNI, HTTP authority và backend route** khác nhau. Đây có thể là cấu hình hợp pháp hoặc bị lạm dụng:

- Passive network observer thường chỉ thấy một phần ClientHello, không thấy HTTP authority trong TLS.
- Tại TLS termination, logs/route tables có thể tiết lộ authority thực tế nếu được ghi.
- Không áp luật “SNI ≠ Host nghĩa là attacker” khi chưa xét reverse proxy, connection coalescing và policy.
- Những giải pháp chặn domain fronting cần cân nhắc false positives với CDN/shared hosting.

### 19.5. CNAME cloaking

Một hostname bên dưới tên miền của tổ chức có thể là CNAME tới third-party service. Điều này **không tự là xấu**, nhưng có thể khiến network monitoring nhìn tên giống first-party dù backend do một vendor xử lý.

Cần:

1. Theo CNAME chain cùng thời gian, kiểm tra owner của từng dependency.
2. Đánh giá dữ liệu nào được gửi tới third-party backend và pháp lý/privacy.
3. Phân biệt DNS configuration legitimate với attacker-controlled DNS change.
4. Không suy cùng domain suffix đồng nghĩa cùng trust boundary.

### 19.6. Mã hóa hoặc cache che mất hostname

Không thấy SNI/DNS trong một PCAP không chứng minh client không dùng hostname:

- DNS đã được cache trên host, browser hoặc resolver.
- Ứng dụng dùng DoH/DoT hoặc OS proxy.
- Client gửi TLS 1.3 với ECH, inner name bị che.
- Session đã tồn tại trước capture; không có ClientHello trong cửa sổ.
- Client kết nối tới proxy/VPN endpoint thay vì origin.
- Traffic dùng HTTP/3 qua QUIC UDP.

Trong báo cáo hãy ghi “**hostname không quan sát được từ nguồn X**”, không viết “kết nối không có hostname” nếu chưa có endpoint evidence.

## 20. Threat model: 26 rủi ro trong truy vết DNS–IP–certificate

| ID | Rủi ro | Hậu quả | Bằng chứng/biện pháp kiểm soát |
|---|---|---|---|
| F01 | **Dùng DNS lookup hiện tại thay lịch sử** | Quy sai IP tại thời điểm incident | Resolver/passive DNS logs có timestamp |
| F02 | **Tin PTR là hostname request** | Gán sai ứng dụng/tenant | Forward/resolver records, SNI/app logs |
| F03 | **Quy một CDN IP cho một actor** | Block nhầm shared users | Tenant/SNI/request context và ownership |
| F04 | **Bỏ qua NAT/SNAT** | Gán sai nguồn kết nối | NAT mapping, time+port, CNI/process evidence |
| F05 | **Không xét IPv6** | Mất một phần flow/hostname answers | A+AAAA, IPv6 logs, dual-stack tests |
| F06 | **Chỉ quan sát UDP/53** | Bỏ DNS cache/DoH/DoT | Endpoint/browser/resolver visibility |
| F07 | **Trộn nhiều recursive DNS views** | Suy IP của resolver khác cho client | Record source resolver/view and time |
| F08 | **CT được coi là deployment evidence** | Gán sai cert/IP lịch sử | TLS endpoint observation at incident time |
| F09 | **Trùng issuer được coi cùng actor** | False linkage quy mô lớn | SAN, cert/key, infrastructure audit |
| F10 | **Trùng SAN được coi cùng live server** | Shared artifact bị quy kết nhầm | Per-hop live cert and flow evidence |
| F11 | **Không phân biệt cert vs SPKI hash** | Sai IOC và rotation timeline | Artifact type, hash algorithm/input |
| F12 | **Serial thiếu issuer** | Ghép nhầm certificates | Issuer + serial + certificate fingerprint |
| F13 | **CN thay SAN** | Hostname verification sai | SAN matching + client validation |
| F14 | **Tin cert validity đủ để xác minh** | Chấp nhận chain/hostname lỗi | Full trust/usage/time/revocation policy |
| F15 | **Đọc TLS 1.3 cert từ PCAP thụ động** | Kết luận sai hoặc bịa evidence | Endpoint logs; hiểu encrypted handshake |
| F16 | **Không xét session resumption** | Không thấy cert rồi suy không có TLS | Client/proxy session context |
| F17 | **Dùng outer ECH SNI như đích thật** | Gán nhầm hostname inner | Proxy/client/app logs, ECH caveat |
| F18 | **Bỏ UDP/443/QUIC** | Sai flow coverage | Dual TCP/UDP telemetry and decoding |
| F19 | **Sai TLS hop ở gateway/service mesh** | Gắn gateway cert cho origin | Hop diagram and endpoint logs |
| F20 | **Packet capture thiếu chiều/gói** | Sai handshake/network interpretation | Sensor drops, vantage, filters, timeline |
| F21 | **Clock skew và stale PID** | Ghép nhầm process↔flow | Clock offsets, process instance IDs |
| F22 | **Tin forwarded hostname header** | Bị spoof hoặc gán sai user/route | Trusted gateway rewriting and app audit |
| F23 | **Hash dữ liệu được coi là mã hóa** | Rò rỉ raw PCAP/cert inventory | Encrypted evidence vault and RBAC |
| F24 | **Không quản lý IOC expiration** | IP block stale, false positive | First/last seen, review/expiry |
| F25 | **Quy actor chỉ từ IP/ASN** | Sai attribution và escalation | Independent IAM/process/provider evidence |
| F26 | **Active scans ngoài phạm vi** | Xâm phạm riêng tư hoặc thay đổi trạng thái đích | Written scope, lab-only probes, owner approval |

### 20.1. Mức độ ưu tiên theo nguy cơ thật

Một sai lầm về **TLS chain/hostname verification** có thể dẫn đến bỏ qua MITM hoặc chấp nhận endpoint giả. Một sai lầm về **CDN shared IP** có thể khiến incident containment chặn nhiều tenant hợp lệ. Một sai lầm về **source IP sau NAT** có thể gây cô lập sai hệ thống. Ưu tiên phụ thuộc **impact, khả năng diễn ra, blast radius và chất lượng bằng chứng**, không phải mức độ bí ẩn của hostname.

### 20.2. Không dùng một IOC như chữ ký tuyệt đối

IOC về hostname/IP/certificate fingerprint cần:

~~~text
type:
  hostname / IP / certificate SHA-256 / SPKI SHA-256
value:
  artifact được chuẩn hóa, đúng loại
observedAt:
  time range, source logs
vantage:
  resolver / gateway / endpoint / passive intelligence
confidence:
  supported / suspected / unverified
expiration:
  reassessment window
alternativeExplanations:
  CDN/hosting/NAT/proxy/rotation hợp lệ?
action:
  observe / enrich / alert / block sau approval
~~~

**IOC enrichment không tự là incident response decision**. Hành động chặn cần biết hệ thống nào chịu ảnh hưởng và có rollback.

## 21. Ma trận kiểm thử positive/negative cho correlation

Những phép thử sau dùng **PCAP/logs/certificates trong lab được ủy quyền**, không thu traffic của người khác hoặc thực hiện active scan trên domain không thuộc phạm vi.

| ID | Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | DNS A H→B tại T0, flow A→B tại T1 | Ghép đúng time/source | DNS answer + 5-tuple |
| N01 | DNS lookup H→C sau incident | Không thay bằng lịch sử H→B | Two timestamps + source views |
| P02 | DNS CNAME chain H→Alias→B | Lưu từng link và TTL | Resolver response records |
| N02 | PTR(B) trả tên khác H | Không tự suy H đã bị thay | PTR/forward/SNI distinction |
| P03 | H có A và AAAA | Xem cả IPv4/IPv6 candidates | Dual-stack DNS logs |
| N03 | Chỉ có IPv4 capture trên IPv6 flow | Report coverage gap, không kết luận không có traffic | IPv6 control |
| P04 | Endpoint process A mở connection B:443 | Kết hợp process/time/flow | EDR + firewall logs |
| N04 | NAT public source đại diện nhiều Pods | Không quy flow cho Pod khi thiếu translation | NAT and CNI logs |
| N05 | Shared CDN IP có 3 hostnames | Không khẳng định cùng tenant/actor | Tenant/Host context |
| P05 | TLS 1.2 full handshake có leaf cert F | Nhận dạng đúng certificate/hop | PCAP handshake bytes and fingerprint |
| N06 | TLS 1.3 passive capture không có cert plaintext | Không suy server thiếu certificate | Protocol version and endpoint logs |
| N07 | TLS resumption không gửi full cert | Tránh false absence-of-certificate | Session/handshake status |
| P06 | Client SNI H, server SAN H, verification PASS | Ghi identity validation có điều kiện | Client/proxy verification log |
| N08 | Client SNI H nhưng cert SAN không chứa H | Hostname mismatch được chỉ ra | TLS validation denial |
| N09 | Certificate còn hiệu lực nhưng chain không trusted | Không gọi cert valid cho client | Chain validation result |
| N10 | Leaf cert fingerprint đổi sau renewal | Không suy owner đã đổi | Cert version and SPKI comparison |
| P07 | Cert v1/v2 dùng cùng key | SPKI hash giống, cert fingerprint khác | DER cert/SPKI hashes |
| N11 | Trùng certificate issuer phổ biến | Không suy actor chung | Multiple independent leafs |
| N12 | CT entry chứa H | Chỉ kết luận certificate logged, không suy deploy | CT source metadata |
| P08 | TLS client log có fingerprint F tại T | Gắn cert F với đúng TLS hop/time | Endpoint log and flow ID |
| N13 | Proxy và origin cert khác | Không gán proxy cert cho origin | Per-hop trace |
| N14 | Outer ECH SNI khác inner | Không coi outer name là target chắc chắn | ECH capability/endpoint log |
| P09 | HTTP request ID nối được TLS/flow | Correlation rõ nguồn và timestamp | Request ID/proxy logs |
| N15 | Client gửi raw `X-Forwarded-Host` giả | Không tin header là authenticated identity | Gateway sanitation and route |
| N16 | DNS over HTTPS ngoài resolver corp | Không suy thiếu DNS chỉ từ port 53 | Client/DoH usage evidence |
| N17 | QUIC UDP/443 nhưng capture chỉ TCP/443 | Phát hiện thiếu coverage | UDP/QUIC lab packet control |
| P10 | Multi-resolver split DNS H | Hiển thị đúng view/source của từng answer | Resolver ID/namespace |
| N18 | Two sensors lệch 30 giây | Không ghép nhầm unrelated flows | Clock offset correction |
| N19 | Same IP reused ở thời điểm khác | IOC hết hạn được review | Time-bounded asset allocation |
| P11 | Raw evidence hash check PASS | Artifact đã chuyển không đổi bytes | SHA-256 of source/target |
| N20 | Hash PEM file khác DER cert fingerprint | Không đánh đồng hai loại hash | Hash target documentation |
| N21 | Raw PCAP được chia sẻ không có quyền | Bị ngăn, chỉ cung cấp extract đã duyệt | RBAC and download audit |
| N22 | PCAP không thấy SNI do bắt giữa flow | Không kết luận “client không gửi SNI” | Capture window and session |
| N23 | App data-exfil nghi từ một IP | Không tuyên bố exfil chỉ từ network flow | App/DB audit correlation |
| P12 | Source workload+DNS+flow+SNI+app log khớp | Báo confidence với provenance | Multi-source timeline |
| N24 | Một evidence field không có timezone | Không ghép tự động như UTC | Timestamp normalization rule |
| N25 | DNS/CT provider “first seen” muộn | Không coi là ngày tạo domain | Source semantics/coverage |
| N26 | Authorized active TLS check hôm nay khác log cũ | Giữ kết luận riêng từng thời điểm | Live check timestamp and archive |

### 21.1. Test một negative conclusion phải có positive control

Ví dụ “client không truy cập hostname H” chỉ từ việc **không thấy H trong DNS logs** là quá mạnh. Cần xem:

- Resolver có đang nhận queries từ **client A**, và có known-good event trong cùng window không?
- Client có local/browser cache, hosts file hoặc DoH không?
- Địa chỉ đích có trùng với H trong historical DNS hay shared CDN không?
- Traffic có qua proxy hoặc đã mở connection trước capture không?
- Nếu có ECH, SNI observer nhìn thấy có phải outer name không?

**Absence of an observed hostname** chỉ có thể được phát biểu theo **nguồn và phạm vi**: “Trong resolver R từ T0 đến T1 không thấy query H từ client A, với visibility đã mô tả.”

## 22. Quy trình điều tra 10 bước từ alert tới kết luận

### Bước 1 — Đặt câu hỏi và phạm vi

Ví dụ: “Process `orders-api` trên host A đã kết nối tới domain `api.billing.example.test` hoặc một endpoint khác lúc 09:12 UTC hay chưa?” Xác định asset, source identity, thời gian, protocol và mục đích.

### Bước 2 — Bảo toàn bằng chứng dễ biến mất

Thu có quyền các logs TTL ngắn: resolver, proxy, flow, CNI, host process, cloud audit, TLS gateways. Lưu raw evidence và chain-of-custody, đồng thời ghi sensor health.

### Bước 3 — Dựng topology và TLS hops

Vẽ client → resolver, NAT, proxy, CDN/LB, origin và nơi terminate TLS. Ghi vPC/VNet, subnet, namespace, IPv4/IPv6, DNS view.

### Bước 4 — Tìm historical DNS answer

Lấy QNAME/QTYPE, answers, CNAME chain, TTL, resolver source, cache/DoH caveats tại thời điểm incident. **Không dùng current lookup thay logs cũ**.

### Bước 5 — Nối source identity với network flow

Từ EDR/application/CNI, nối process/workload tới 5-tuple; điều chỉnh NAT/IP translation. Ghi observation ID và timestamp/time uncertainty.

### Bước 6 — Phân tích TLS/protocol

Nếu có TLS ClientHello/SNI, ghi đúng hop và khả năng ECH. Xác định TLS version/TCP/QUIC, full handshake hay resume; không yêu cầu decrypt không được phép.

### Bước 7 — Đối chiếu certificate

Lấy certificate từ TLS 1.2 full handshake (nếu có) hoặc endpoint/proxy log/inventory/lab check, ghi issuer/serial/SAN/fingerprint/SPKI. Xác minh trust/hostname/validity theo policy, phân biệt thời gian hiện tại với incident.

### Bước 8 — Enrich một cách thận trọng

Dùng internal asset inventory, passive DNS/CT/ASN/RDAP theo quyền và privacy review. Ghi rõ **shared infrastructure, allocation timing và telemetry coverage**.

### Bước 9 — Kiểm tra hành vi và tác động

Correlate request IDs, app/DB audit, user/workload identity và data access; nếu nghi malicious, phối hợp IR/Legal trước containment/attribution.

### Bước 10 — Báo cáo kết luận và giới hạn

Ghi **confirmed observations, supported inferences, unverified hypotheses, data gaps, owner, next steps và recommended controls**. Không công bố actor attribution hoặc data breach khi không có evidence đủ.

## 23. Playbook tình huống: hostname lạ trên IP cloud shared

### 23.1. Kịch bản giả định

Cloud flow logs báo workload `analytics-job` kết nối TCP/443 tới `203.0.113.20`. Một threat intelligence feed đánh dấu IP này từng liên quan phishing. Một nhà phân tích thấy DNS hiện tại của `login-alert.example.test` trỏ tới IP ấy và CT logs có certificate SAN `login-alert.example.test`.

**Những dữ kiện còn thiếu:** DNS queries của workload lúc incident, SNI/HTTP Host của flow, certificate thực sự được server trình bày trên hop, process/API call context và owner của IP theo thời điểm.

### 23.2. Ba giả thuyết cạnh tranh

| Giả thuyết | Bằng chứng cần có | Điều phản bác |
|---|---|---|
| **H1: analytics-job gọi phishing endpoint** | Historical resolver answer, flow + SNI/Host, app/process/network audit | App logs chỉ ra một endpoint hợp lệ khác |
| **H2: workload gọi ứng dụng hợp lệ trên cùng CDN IP** | App request ID, DNS history của tên hợp lệ, verified cert | SNI/Host thật là domain nghi vấn và app context bất thường |
| **H3: IP/CNAME đã đổi tenant sau incident** | Time-bounded passive DNS, allocation/CT and deploy records | Historical logs xác nhận domain nghi vấn đã liên quan flow |

### 23.3. Hướng điều tra hợp lý

1. **Không block IP toàn cloud region ngay** chỉ vì threat intelligence feed, trừ trường hợp urgent containment đã được phê duyệt với assessment blast radius.
2. Thu flow 5-tuple/time và resolve source Pod/process qua NAT/CNI.
3. Kiểm tra DNS/cache/proxy logs cùng time window, cả A/AAAA/DoH possibilities.
4. Kiểm tra SNI từ capture nếu có, chú ý ECH và TLS version; cần endpoint logs nếu cert bị mã hóa.
5. Đối chiếu app request IDs, user/workload entitlements và business dependency.
6. Xác định **confidence và mức độ ảnh hưởng** trước khi chuyển IOC sang deny policy.
7. Nếu xác nhận malicious behavior, phối hợp IR containment có scope và giữ evidence.

### 23.4. Kết luận minh họa

> “Tại 09:12 UTC, workload analytics-job đã kết nối tới 203.0.113.20:443 (flow và CNI logs đã đối chiếu). Chưa có bằng chứng xác nhận hostname `login-alert.example.test` được dùng trong flow này; DNS lookup hiện tại và certificate CT chỉ phản ánh lịch sử/tình trạng khác. IP thuộc shared infrastructure theo inventory. Đang đối chiếu TLS proxy và application logs để xác định virtual host đích trước khi xem xét chặn.”

Đây là **kết luận có điều kiện**, không bao che nguy cơ. Nó tránh **nâng correlation thành quy kết** khi dữ liệu còn thiếu.

## 24. Khi tìm thấy bằng chứng compromise thật

Giả sử EDR xác nhận một process không thuộc baseline chạy dưới service account của workload, application logs ghi request tới URL nằm ngoài dependencies, TLS gateway log xác nhận target hostname H, và data audit cho thấy dữ liệu bí mật được đọc ngay trước outbound burst.

Khi đó cần **chuyển từ forensics sang incident response**:

1. Xác định incident commander, severity, scope và privacy/data owners.
2. Bảo toàn evidence và phân quyền truy cập dữ liệu nhạy cảm.
3. Cân nhắc cô lập host/workload hoặc chặn egress destination **có phạm vi** theo delegated authority.
4. Thu hồi/rotate account credentials và active sessions có rủi ro, xác minh revoke.
5. Phân tích lateral movement, DNS/egress alternatives và impacted tenants/data.
6. Remediate compromised host/app/CI, rebuild từ trusted source và khắc phục root cause.
7. Recovery theo canary, positive/negative tests và enhanced monitoring.
8. Post-incident review: vì sao telemetry hoặc policy không chặn/phát hiện sớm.

**Một hostname/IP/certificate IOC là đầu mối điều tra**, không thay việc chứng minh unauthorized access hay dữ liệu đã rời môi trường.

## 25. Troubleshooting: vì sao kết quả hostname/IP/certificate không khớp?

| Triệu chứng | Khả năng cần phân biệt | Bằng chứng ưu tiên |
|---|---|---|
| DNS hiện tại khác IP trong flow lịch sử | TTL/CDN rotation, failover, allocation change | Historical resolver logs và event timestamps |
| Resolver log không có QNAME nhưng có TCP/443 | Cache, DoH, hosts file, hard-coded IP, proxy | Client/EDR DNS cache, app/proxy logs |
| A record đúng nhưng client kết nối IPv6 | AAAA/Happy Eyeballs | Dual-stack DNS+flow logs |
| PTR trỏ hostname lạ | Reverse zone đặt tên khác forward lookup | PTR vs SNI/Host/forward DNS |
| Một IP match nhiều unrelated domains | CDN/virtual hosting | SNI/Host, app request ID, tenant/backend audit |
| Flow source IP không nằm trong asset inventory | SNAT, NAT64, VPN/proxy, reassigned IP | NAT translation, CNI, session records |
| Hostname H có CNAME tới bên thứ ba | CDN/service vendor hoặc CNAME cloaking | Chain, asset owner, vendor relationship |
| TShark không hiện TLS server certificate | TLS 1.3 encryption, resumption, capture truncation | TLS version và endpoint/proxy certificate logs |
| ClientHello không có SNI | ECH, no SNI, wrong capture point, incomplete handshake | Endpoint logs, ECH context, packet completeness |
| SNI và HTTP Host khác nhau | Proxy route, connection coalescing, misconfig, fronting | TLS endpoint/app logs, gateway route |
| Server trả cert khác khi đổi SNI | Virtual host cert selection | Active lab test đúng SNI và per-host config |
| Cert SAN chứa domain nhưng không thấy network traffic | Certificate issuance không đồng nghĩa deployment | Endpoint logs/flows, không chỉ CT |
| Cert fingerprint đổi nhưng SPKI giống | Certificate reissuance cùng key | DER certificate & SPKI hash |
| Hash PEM file khác fingerprint | Đối tượng hash khác nhau | Raw PEM vs DER X.509 |
| Cùng issuer xuất hiện ở nhiều hosts | CA phổ biến | Leaf certificate/tenant context |
| Hostname verification FAIL dù certificate “còn hạn” | SAN/chain/usage/clock/revocation sai | Validation reason, trust policy |
| Active TLS check hôm nay trả cert F2, incident ghi F1 | Renewal, failover, different edge, session time | Historical deployment/handshake evidence |
| Cloud flow cho IP nguồn là NAT gateway | Egress SNAT của nhiều Pods | NAT port/time mapping, CNI identity |
| Không thấy HTTP path trong HTTPS PCAP | HTTP nằm trong TLS encrypted records | Authorized application/proxy logs |
| CT log có cert mà DNS không có record | Cert chưa deploy, removed DNS, wildcard, preview | CT vs DNS historical comparison |
| Dữ liệu threat intel gắn IP “malicious” đã cũ | IP reuse, CDN sharing, false positives | Indicator time/expiry/source |
| Một PCAP không có TLS handshake | Capture bắt đầu muộn, connection reused | Flow start time, endpoint logs |
| Không có flow tại một sensor | Wrong NIC, asymmetric routing, tunnel, drops | Vantage and sensor health |
| Logs trái nhau vài giây | Clock skew, delayed ingestion, different timezones | Raw UTC/offset and receive time |

### 25.1. Không “sửa” bất nhất bằng cách chọn một bằng chứng đẹp

Một DNS response có thể liên quan hostname H nhưng application trace nói request dùng H2. Cần kiểm tra:

1. Flow A và DNS event có cùng **process/client identity**, không chỉ cùng NAT IP?
2. DNS record do resolver R trả có thực sự được **client sử dụng** không?
3. Có redirect, proxy rewrite, virtual hosting hoặc connection reuse không?
4. Logs ghi event time hay ingest time, clock offset bao nhiêu?
5. Hostname H2 có chung IP vì CDN, không hề liên quan H trong ứng dụng?

Nếu còn mâu thuẫn, ghi **unresolved correlation** và mức confidence thấp hơn, không tạo ra một câu chuyện tuyến tính không có dữ liệu.

## 26. Mẫu báo cáo network forensics có thể kiểm toán

Một báo cáo hữu ích nên tách bạch các phần:

~~~text
CASE: NET-FOR-EXAMPLE-004
Analyst / evidence custodian:
Authorization / scope:
Assets, accounts, networks và time window được phép:

INVESTIGATION QUESTION
Workload A đã kết nối tới hostname H qua IP B tại T hay chưa?

CONFIRMED OBSERVATIONS
E1: Resolver R response at T0, H -> B (TTL; view)
E2: Workload/process A flow to B:443 at T1 (before NAT)
E3: TLS ClientHello SNI H at T2 (nếu được quan sát)
E4: TLS endpoint verified SAN H with cert F at T3
E5: Application trace request ID X at T4

INFERENCES
I1: E1+E2+E3 support client A intended to contact H at T.
I2: E4 supports TLS peer authentication at the logged hop.

ALTERNATIVE EXPLANATIONS
Shared CDN, multiple IPs, proxy, cache, ECH, stale DNS, NAT.

LIMITATIONS
Resolver visibility, clock offsets, missing ClientHello,
packet drop/sample rate, incomplete data audit.

IMPACT
Observed network communication vs confirmed app/data impact.

CONFIDENCE
By conclusion and source, not one global label.

RECOMMENDATIONS
Telemetry, scope extensions subject to approval, safe controls.

EVIDENCE INDEX
Artifact ID, digest, raw file location, collector, custody,
time/version, retention.
~~~

### 26.1. Ngôn ngữ kết luận đúng và sai

| Cách viết quá mức | Cách viết dựa trên bằng chứng |
|---|---|
| “IP này chắc chắn của attacker X.” | “Theo registry tại thời điểm tra, IP thuộc dải do organization Y công bố; chưa có chứng cứ đủ để gán actor.” |
| “Hostname này đã được client gọi vì DNS hiện tại trỏ tới IP đó.” | “DNS hiện tại trỏ tới IP đó, nhưng chưa có historical answer/client connection evidence tại incident time.” |
| “CT thấy cert này nên server đã dùng nó.” | “CT ghi nhận certificate issuance/logging; deployment status chưa được xác nhận.” |
| “Không thấy cert trong PCAP nên server không có cert.” | “PCAP TLS 1.3 thụ động không cho thấy Certificate message plaintext; cần endpoint logs.” |
| “Cùng SAN là cùng chiến dịch tấn công.” | “Các certificates có SAN trùng, là tín hiệu correlation cần kiểm tra infrastructure/actor evidence.” |
| “Không thấy DNS query tức không có hostname.” | “Resolver R không quan sát được query trong window; cần xét cache/DoH/hosts/proxy.” |
| “Có HTTPS egress lớn nên đã exfiltrate.” | “Đã quan sát outbound bytes; chưa xác định được object/data nội dung hoặc tính trái phép.” |

## 27. Bài tập tự đánh giá

### 27.1. Câu hỏi

1. Vì sao một kết quả `dig` ở hiện tại không thể xác minh hostname đã trỏ tới IP ấy ba giờ trước?
2. Trong resolver log thấy CNAME H→C→B và flow tới B:443. Cần thêm gì để gắn flow với hostname H?
3. PTR(B) trả R, trong khi TLS SNI là H. Có mâu thuẫn bảo mật chắc chắn không?
4. Khi một IP CDN phục vụ ba tenants, dùng IP IOC để block có nguy cơ gì?
5. So sánh **DNS QNAME**, **TLS SNI**, **HTTP Host**, **certificate SAN** về ý nghĩa và mức quan sát.
6. Vì sao cùng certificate fingerprint không chứng minh các endpoints cùng actor?
7. Vì sao cert fingerprint đổi sau renewal mà public key/SPKI hash có thể giữ nguyên?
8. Phân biệt **hash file PEM**, **fingerprint DER certificate** và **hash SPKI**.
9. Vì sao một passive TLS 1.3 PCAP không cho phép trích plain certificate nếu không có endpoint/key context?
10. Khi ECH được sử dụng, outer SNI cho biết gì và không cho biết gì?
11. Một cuộc gọi HTTP/3 dùng transport nào và vì sao filter `tcp port 443` có thể không thấy?
12. Khi flow log sau SNAT chỉ có public IP, làm sao xác định đúng Pod/process?
13. Nếu device hỗ trợ DoH, có thể không thấy query ở resolver doanh nghiệp nhưng client vẫn truy cập một hostname không?
14. CT entry cho tên H giúp điều tra điều gì, và không chứng minh điều gì?
15. Nếu TLS client log cho “certificate verify PASS”, tại sao vẫn phải kiểm tra app-level AuthZ?
16. Một IP bị gắn IOC “malicious” từ năm trước có nên block hôm nay không? Điều kiện gì cần review?
17. Nêu ba loại **negative evidence** có thể bị hiểu sai là “không có traffic”.
18. Nêu ba trường cần lưu trong chain-of-custody của file PCAP.
19. Một active TLS check tới IP B trả cert F hôm nay có chứng minh incident cũ dùng cert F không?
20. Soạn một kết luận một đoạn với confidence và limits khi chỉ có flow B:443 và passive DNS/CT.

### 27.2. Gợi ý đáp án trọng tâm

- **DNS lịch sử:** phải dùng resolver logs/passive DNS/authoritative history tại **cùng thời điểm và đúng view**; current lookup chỉ bổ sung current state.
- **Truy vết hostname:** kết hợp client identity, DNS answer, NAT/flow 5-tuple/time, ClientHello SNI khi có, proxy/HTTP request logs.
- **PTR:** là reverse name record, không xác minh tên client đã yêu cầu.
- **TLS certificate:** SAN hỗ trợ hostname matching; fingerprint định danh cert bytes; SPKI hash định danh key data; certificate issuer không xác minh actor.
- **TLS 1.3:** Certificate message được mã hóa trong full handshake; passive PCAP thông thường không thấy plain certificate, dù một số ClientHello metadata có thể thấy.
- **IP shared:** source/destination có thể là shared CDN/NAT; một IOC IP cần scope/time/tenant context.
- **NAT:** dùng translation logs, network time, ports, CNI/EDR/process evidence và không gán cả egress IP cho một workload.
- **Data exfiltration:** outbound network bytes chưa đủ; cần app/DB/data access và owner/authorization context.
- **Evidence:** giữ raw artifacts, hash đúng loại bytes, UTC/clock offsets, custody và phân biệt observation với inference.

### 27.3. Bài tập lab theo nhóm

Tạo một **dữ liệu mô phỏng được phê duyệt**:

~~~text
Resolver response R1:
  09:00:00 UTC
  H1 -> CNAME edge.example.test -> A 203.0.113.20

Resolver response R2:
  09:03:00 UTC
  H2 -> A 203.0.113.20

Flow F1:
  09:00:01 UTC
  workload A -> 203.0.113.20:443

TLS client log T1:
  09:00:01 UTC
  SNI H1; server cert SHA-256 F1; hostname verification PASS

CT record C1:
  Public certificate issuance logged at some earlier date
  SAN includes H2
~~~

**Nhiệm vụ:** xây evidence table, correlation graph, confidence và limitations. **Kết luận mong muốn:** workload A có bằng chứng tốt cho flow tới H1 khi có TLS log T1, còn H2 cùng IP/CT SAN không chứng minh H2 là đích F1. Cần ghi rõ nguồn nào là historical log, nguồn nào là issuance record.

## 28. Checklist trước–trong–sau truy vết hostname, IP và certificate

### 28.1. Trước khi truy vết

- [ ] Có incident/ticket ID, câu hỏi, time window và assets được phê duyệt.
- [ ] Có owner/chủ evidence, quy tắc privacy, retention và quyền truy cập kho dữ liệu.
- [ ] Đã inventory DNS views, resolvers, proxies, VPN/NAT, CDN, cloud/LB và TLS termination points.
- [ ] Biết cách ánh xạ process/workload identity với traffic qua NAT/IPv6.
- [ ] Có thời gian UTC/clock offset và biết event time khác ingestion time.
- [ ] Đã xác định raw logs/PCAP có thể chứa dữ liệu nhạy cảm.
- [ ] Biết kết quả active DNS/TLS lookup **không thay thế historical evidence**.

### 28.2. Khi phân tích DNS và IP

- [ ] Phân biệt QNAME/QTYPE, CNAME chain, A/AAAA, HTTPS/SVCB và TTL.
- [ ] Ghi resolver/source view, response timestamp và DNS cache caveats.
- [ ] Kiểm tra private/split DNS, DoH/DoT/DoQ, client cache và hosts file khi phù hợp.
- [ ] Không xem PTR là hostname client đã truy cập.
- [ ] Có network flow 5-tuple, source/destination trước/sau NAT và IP family.
- [ ] Đã xem shared CDN/anycast/load balancer/NAT64/IP reuse trước khi quy kết IP.
- [ ] Không dùng RDAP/ASN/GeoIP như chứng minh identity một actor cụ thể.
- [ ] Không lấy passive DNS first/last seen làm ngày tạo/xóa DNS record chắc chắn.
- [ ] Không gán IP hiện tại cho flow lịch sử mà không có time-specific corroboration.

### 28.3. Khi phân tích TLS và certificate

- [ ] Đã phân biệt TLS SNI, HTTP Host/:authority, DNS hostname và SAN.
- [ ] Biết SNI có thể bị thiếu/khác do ECH, proxy, QUIC hoặc session capture window.
- [ ] Xác định đúng **TLS hop**: client→gateway, gateway→origin hoặc mesh workload.
- [ ] Đã xác định TLS 1.2 hay TLS 1.3, full handshake hay session resumption.
- [ ] Không đòi plain TLS 1.3 Certificate message từ passive PCAP thông thường.
- [ ] Certificate fields được đọc đủ: SAN, issuer, serial, validity, usage/EKU và chain.
- [ ] Xác minh hostname, trust anchor, thời gian, chain/usage theo client policy.
- [ ] Không thay certificate validation bằng `--insecure` hoặc bỏ hostname verification.
- [ ] Ghi rõ hash là file PEM, DER leaf certificate hay DER SPKI.
- [ ] Hiểu fingerprint cert đổi khi reissue; cùng key/SPKI không chắc là cùng actor.
- [ ] CT được dùng cho issuance history, không như bằng chứng endpoint đang deploy cert.
- [ ] Nếu có mTLS, tách workload peer identities với user/app authorization.

### 28.4. Khi tương quan và kết luận

- [ ] Mỗi correlation edge có source ID, timestamp, vantage point và giới hạn quan sát.
- [ ] Đã so tình huống có proxy/NAT/tenant sharing/certificate renewal.
- [ ] Đã đối chiếu thông tin trái nhau thay vì chọn chỉ một log thuận giả thuyết.
- [ ] Đã xét positive controls và sensor health trước khi suy “không thấy nên không xảy ra”.
- [ ] Chưa quy actor hoặc khẳng định exfiltration chỉ từ hostname/IP/certificate.
- [ ] Có app/DB/identity/process evidence nếu muốn kết luận impact hoặc unauthorized action.
- [ ] Confidence được ghi theo **từng kết luận**, không chỉ một nhãn chung cho cả incident.
- [ ] Mọi yêu cầu mở rộng telemetry/active probes đều có approval và mục đích.
- [ ] Raw PCAP/cert/logs được bảo vệ, hash/custody và chia sẻ tối thiểu.
- [ ] Indicators có time range, expiry/review và blast-radius assessment trước khi block.
- [ ] Báo cáo phân biệt confirmed observations, inferences, hypotheses và unknowns.
- [ ] Có owner, next steps, recovery/incident escalation và thời hạn quản lý evidence.

**Ghi nhớ:** **Truy vết hostname, IP và certificate là quá trình ghép chứng cứ có thời gian và nguồn, không phải một phép lookup đơn giản.** DNS answer phản ánh một resolver/view tại một thời điểm; IP có thể là NAT hoặc shared CDN; SNI là tên client khai báo khi thấy được; certificate SAN và fingerprint giúp kiểm tra peer/artifact nhưng không tự định danh actor hay dữ liệu đã truy cập. Một kết luận vững cần **resolver history + network flow + NAT/process context + TLS endpoint/certificate validation + application/identity evidence**, kèm **clock accuracy, chain of custody, mức tin cậy và những giới hạn quan sát**. Không nâng quan hệ “cùng IP/cùng issuer/cùng certificate” thành lời buộc tội hay containment diện rộng khi chưa có bằng chứng tương xứng.
