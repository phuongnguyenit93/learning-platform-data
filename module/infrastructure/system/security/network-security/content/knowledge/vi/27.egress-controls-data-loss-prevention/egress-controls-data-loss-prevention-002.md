# Allowlist domain và destination trong kiểm soát egress và chống thất thoát dữ liệu

**Allowlist domain và destination** là cơ chế chỉ cho phép workload hoặc người dùng tạo kết nối ra ngoài tới **những điểm đến đã được xét duyệt**, theo **danh tính nguồn, đích, giao thức, port, mục đích nghiệp vụ và ngữ cảnh bảo mật**. Đây là một lớp phòng vệ quan trọng trong **egress control**: khi một máy trạm, máy chủ, container hoặc ứng dụng bị xâm nhập, đối tượng tấn công không nên có đường tùy ý để kết nối đến mọi Internet host, máy chủ nội bộ hoặc hạ tầng điều khiển từ xa.

Trong chương **Kiểm soát egress và chống thất thoát dữ liệu** của module **SECURITY_NETWORK_SECURITY**, allowlist kết hợp **phân đoạn mạng, firewall, VPN, IDS/IPS, DNS security, TLS, xác thực kết nối, zero trust, cloud networking và giám sát lưu lượng**. Domain allowlist giúp quản trị *được gọi tên dịch vụ nào*; destination allowlist có thể quản trị *địa chỉ, port, dịch vụ, endpoint hay identity nào*; DLP (Data Loss Prevention) kiểm soát *dữ liệu nào được phép đi tới đó*. Ba câu hỏi này liên quan chặt chẽ nhưng không tương đương.

**Nguyên tắc xuyên suốt:** một tên miền hoặc IP nằm trong allowlist **không tự chứng minh nội dung truyền đi là hợp lệ**, và một kết nối tới TCP/443 cũng **không tự chứng minh đó là HTTPS tới đúng đối tác**. Phải kiểm chứng chính xác tầng mà policy thực thi, khả năng bị bypass và bằng chứng vận hành thực tế.

Các domain thuộc **.example** và địa chỉ IP thuộc dải tài liệu chỉ là giả định; cấu hình có nhãn *pseudopolicy* không phải cấu hình vendor có thể deploy trực tiếp. Các phép thử chỉ dành cho lab/staging hoặc hệ thống được cấp phép; không gây gián đoạn production, không thử khai thác máy chủ của bên thứ ba và không ghi nhận secrets thật vào log.

## 1. Mục tiêu học tập

Sau khi học, người học có thể:

1. Định nghĩa allowlist egress theo **source workload → destination → protocol/port → danh tính/điều kiện**.
2. Phân biệt **domain/FQDN, DNS answer, IP/CIDR, service endpoint, TLS SNI, HTTP Host, URL/path và service identity**.
3. Chỉ ra vì sao DNS filtering, firewall IP và forward proxy có **khả năng kiểm soát khác nhau**.
4. Thiết kế **default-deny** có ngoại lệ hẹp theo owner, environment, vòng đời và bằng chứng.
5. Hiểu **DNS caching, TTL, CNAME, nhiều A/AAAA records, CDN, split-horizon DNS, DNS rebinding** và thay đổi IP.
6. Nhận diện rủi ro từ **wildcards, domain takeover, domain fronting, redirect, shared hosting, DoH/DoT, ECH, QUIC/HTTP/3, hardcoded IP**.
7. Kết hợp **egress gateway/forward proxy, CNI/NetworkPolicy, firewall, private endpoints, cloud IAM và ứng dụng**.
8. Phân tích **SSRF, metadata access, data exfiltration** và trường hợp một đích hợp lệ trở thành kênh trung gian.
9. Thiết kế log/metrics, positive/negative tests, rollout, exception management và incident runbook.
10. Giải thích **allowlist là giảm đường mạng**, còn DLP và authorization là những lớp bổ sung để kiểm soát mục đích và nội dung dữ liệu.

## 2. Khái niệm allowlist: danh sách được phép là một quyết định có ngữ cảnh

Một allowlist không nên chỉ là danh sách tên miền. Một entry có nghĩa khi trả lời rõ:

- **Ai được đi?** Source workload/namespace/service account, user, device posture hoặc subnet.
- **Đi đâu?** Một FQDN, một service identity, private endpoint, IP/CIDR hoặc nhóm đích đã được kiểm tra.
- **Bằng gì?** Protocol TCP/UDP, port, HTTP method/path khi thiết bị có khả năng L7.
- **Để làm gì?** Gọi payment API, đồng bộ telemetry, lấy bản cập nhật, backup hay truy cập SaaS.
- **Trong điều kiện nào?** Môi trường Prod/Dev, identity đã xác thực, TLS đúng server, approval còn hiệu lực.
- **Được ghi nhận ra sao?** Allow/deny event, request metadata, người phê duyệt và thời điểm hết hạn.

Một quy tắc ý định có thể biểu diễn:

\[
\operatorname{Allow}(f) =
\operatorname{ApprovedSource}(f)\land
\operatorname{ApprovedDestination}(f)\land
\operatorname{ApprovedProtocol}(f)\land
\operatorname{SecurityConditions}(f)
\]

Đây là **mô hình thiết kế**, không phải công thức mà mọi firewall có thể thực hiện đầy đủ. Một ACL L3/L4 không biết danh tính end-user hoặc HTTP path; một DNS filter không biết toàn bộ connection state; một proxy L7 có thể thấy hostname/URL nhưng phải xử lý TLS, authentication và bypass.

### 2.1. Default-deny và explicit allow

- **Default deny:** chưa được duyệt thì không có đường ra tại enforcement points.
- **Explicit allow:** mỗi ngoại lệ được cấp cho đúng nguồn, đích, protocol/port.
- **Deny-by-default không đồng nghĩa deny toàn bộ:** phải inventory DNS, time sync, identity, certificate renewal, package mirrors, cloud APIs, monitoring và ứng dụng.
- **Least privilege:** cho đúng nhu cầu, không mở 0.0.0.0/0:443 chỉ vì app cần một API qua HTTPS.
- **Time-bound exceptions:** cấp tạm khi business yêu cầu và tự hết hạn theo quy trình đã phê duyệt.

### 2.2. Quy tắc không có owner là nợ kỹ thuật

Một allowlist entry không có owner/purpose/expiry dễ tồn tại sau khi nhà cung cấp đổi domain, project ngừng hoạt động hoặc môi trường bị tái sử dụng. Khi đó bề mặt tấn công tăng mà không ai biết rule còn cần hay không.

## 3. Những lớp destination có thể được allowlist

| Đối tượng đích | Ví dụ giả định | Thiết bị có thể thực thi | Điểm mù |
|---|---|---|---|
| **Domain/FQDN** | api.billing.example | DNS filter, FQDN-aware CNI, proxy | DNS answers thay đổi; domain không xác thực payload |
| **IP đơn lẻ** | 198.51.100.25/32 | Firewall, ACL, NetworkPolicy ipBlock | Shared IP, địa chỉ đổi, thiếu hostname identity |
| **CIDR** | 203.0.113.0/28 | Router, firewall, cloud SG/NACL | Có thể chứa nhiều services/tenants |
| **Protocol/port** | TCP/443 | L4 firewall | Không tự biết HTTPS đúng hostname |
| **HTTP Host + URI** | https://api.billing.example/v1/invoices | L7 proxy/API gateway phù hợp | TLS visibility, redirects, host spoofing |
| **TLS server identity** | Certificate SAN hợp lệ cho api.billing.example | TLS client/proxy xác minh | Không thay app authorization |
| **Workload/service identity** | Service account/P2P principal | Mesh mTLS, IAM, policy engine | Không tự biết user/tenant có quyền đọc |
| **Private endpoint** | Cloud object storage private interface endpoint | Cloud endpoint policy + routes + IAM | Bypass Internet gateway nếu không inventory |
| **DNS category** | Corporate resolvers / approved business domains | DNS security service | Direct IP, DoH/DoT, cache có thể đi đường khác |
| **Egress proxy target** | proxy.corp.example:3128 | NetworkPolicy/SG và proxy auth | Nếu direct path vẫn mở, proxy chỉ là lựa chọn |

**Destination có thể thuộc nhiều lớp cùng lúc.** Một API đối tác đúng thiết kế có thể yêu cầu *workload X → proxy Y → FQDN Z:443 → TLS server identity Z → HTTP path cho phép → token có scope phù hợp*.

## 4. Luồng egress và điểm thực thi policy

~~~mermaid
flowchart LR
    A[Workload / Pod / Device] --> D[Managed DNS Resolver]
    A --> F[CNI / Host Firewall]
    F --> P[Authenticated Egress Proxy]
    P --> G[Cloud Firewall / NAT]
    G --> X[Approved External Service]
    F -.Blocked direct access.-> X
    D -.DNS logs.-> S[Security Monitoring]
    P -.Policy decision logs.-> S
    G -.Flow/NAT logs.-> S
    A -.Application audit.-> S
~~~

Một thiết kế an toàn cần trả lời:
1. **Nguồn có thể bypass proxy không?** Nếu có direct Internet route, biến môi trường HTTPS_PROXY không đủ.
2. **DNS có được buộc qua resolver quản trị không?** DoH/DoT và hardcoded IP có thể né DNS filtering.
3. **Proxy dùng FQDN/SNI/HTTP Host nào để quyết định?** Nó có xác minh TLS và server identity không?
4. **Cloud firewall nhìn source IP nào?** Nếu SNAT đã xảy ra, firewall chỉ thấy gateway/worker node IP.
5. **IPv6 có dùng cùng đường egress và enforcement không?**
6. **Return path, NAT và stateful firewall có đúng không?**
7. **Có private endpoint hoặc alternate VPN/peering path không qua điểm giám sát?**

### 4.1. Egress control khác ingress control

Nếu một service có thể nhận HTTPS từ client nhưng bị default-deny egress, nó có thể trả response về connection đã được phép mà không có quyền **khởi tạo kết nối mới** tới Internet. Ý nghĩa này phụ thuộc connection tracking/datapath. Không mở outbound rộng chỉ vì incoming HTTPS cần hồi đáp.

### 4.2. Network segmentation vẫn cần

Dev và Prod đều dùng domain nội bộ không có nghĩa mọi luồng Dev→Prod được phép. Cần phân đoạn theo source/destination workload và app authorization. Một shared proxy có quyền đi Prod có thể trở thành **pivot** nếu không xác thực caller.

## 5. Domain, FQDN, DNS answer và destination IP: phân biệt cho chính xác

- **Domain name:** tên trong DNS namespace; ví dụ billing.example.
- **Fully Qualified Domain Name (FQDN):** tên đầy đủ, ví dụ api.billing.example.
- **DNS answer:** dữ liệu từ resolver, có thể gồm CNAME và A/AAAA; có thời hạn cache.
- **Destination IP:** địa chỉ thực sự mà socket kết nối tới theo góc nhìn tại một hop.
- **SNI:** tên server TLS client cung cấp theo cơ chế handshake, khi có và quan sát được.
- **HTTP Host/authority:** tên host mà HTTP client yêu cầu; có thể khác SNI/IP và có thể bị giả mạo nếu không được xác minh.
- **URL:** scheme, authority, path, query; chỉ L7 engine ở vị trí phù hợp mới kiểm soát path/query.
- **Server certificate:** công cụ xác minh TLS server identity khi client/proxy thực hiện hostname verification.
- **Cloud service identity/endpoint:** định danh logic của API/resource có IAM hoặc endpoint policy riêng.

### 5.1. Một domain có thể có nhiều IP

~~~text
api.billing.example
  -> CNAME edge.billing-cdn.example
  -> A     198.51.100.25
  -> A     198.51.100.26
  -> AAAA  2001:db8:abcd::25
~~~

Các IP và tên thuộc không gian tài liệu, chỉ minh họa. Địa chỉ thực có thể thay theo region, CDN, tải, thời gian và resolver. Việc viết firewall rule cho **một IP được nhìn thấy hôm nay** có thể làm ứng dụng lỗi ngày mai hoặc tạo allowlist quá rộng nếu dùng cả dải CDN lớn.

### 5.2. Một IP có thể phục vụ nhiều domain

Một CDN hoặc shared hosting endpoint có thể phục vụ hàng chục/nghìn domain trên cùng IP. Nếu firewall allow 198.51.100.25:443 thì **ở lớp L3/L4**, nhiều domain dùng IP đó có thể đi qua — trừ khi có proxy/kiểm tra đích mạnh hơn. Không gọi “IP allowlist” là “domain allowlist chính xác”.

### 5.3. Tên miền đúng nhưng server sai

DNS cache/hijack, cấu hình proxy sai hoặc chuyển hướng mạng có thể đưa request tới địa chỉ khác. **TLS hostname verification** giúp ứng dụng xác minh certificate khớp tên đích và trust chain đáng tin; nếu tắt xác thực certificate, allowlist domain trở nên yếu hơn. TLS verification cũng không thay application-level access control.

## 6. DNS lifecycle: TTL, cache và tính động của IP

Một FQDN-aware enforcement point thường cần biết cách tên miền được ánh xạ sang đích; cách làm thay đổi theo DNS proxy, firewall hoặc service.

### 6.1. Các giai đoạn

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Approved DNS Resolver
    participant E as Egress Policy Engine
    participant S as External Service
    A->>D: Resolve api.billing.example
    D-->>A: A / AAAA answers + TTL
    D-->>E: Observed approved DNS mapping (when supported)
    A->>E: Connect to destination IP:443
    E-->>A: Policy allow or deny
    E->>S: Forward allowed connection
    S-->>A: Response on approved path
~~~

Sơ đồ là **logic**. Không phải mọi policy engine có channel nhận DNS answers; DNS-aware CNI có thể dùng DNS proxy riêng, còn explicit HTTP proxy có thể tự resolve đích. Phải hiểu *ai resolve*, *ai cache* và *ai quyết định*.

### 6.2. TTL không phải cam kết IP ổn định

Một bản ghi TTL 60 giây không đảm bảo tất cả clients làm mới đúng ở mốc đó: có caching ở ứng dụng, OS, stub resolver, service mesh hoặc proxy. Ngược lại, TTL ngắn có thể gây churn IP/policy. Cần test cache hit/miss, retry và records thay đổi.

### 6.3. CNAME và chain of trust

Policy cho api.billing.example phải xác định semantics khi FQDN trỏ qua CNAME/CDN:
- Engine có đi theo CNAME chain không?
- Ánh xạ được giữ cho riêng **domain được allow** hay vô tình cấp quyền cho toàn IP của CDN?
- Địa chỉ IP trong response có thuộc private/internal/link-local ranges hay không?
- Redirect HTTP sau DNS resolution có được kiểm tra lại không?

### 6.4. DNS rebinding và TOCTOU

Một ứng dụng kiểu **fetch URL** có thể kiểm tra tên miền ban đầu rồi kết nối tới IP được resolve ở thời điểm khác (*time-of-check vs time-of-use*). Nếu DNS answer đổi sang địa chỉ nội bộ/metadata hoặc có redirect qua domain khác, một allowlist thiếu ràng buộc kết nối có thể bị lách.

Phòng vệ:
- Xác minh tên miền và **địa chỉ thực sự dùng cho socket** tại điểm được kiểm soát.
- Có quy tắc chặn địa chỉ internal/link-local/loopback không được phép.
- Kiểm tra lại sau redirect; kiểm soát protocol/scheme.
- Dùng egress proxy được tin cậy để quản lý resolution + connection.
- Không chỉ dựa vào regex của URL rồi cho ứng dụng tự mở kết nối tùy ý.
- Giữ TLS server-name validation và audit.

## 7. Wildcard, subdomain và domain ownership

Wildcard là đường tắt dễ mở rộng quyền ngoài ý định.

### 7.1. So sánh phạm vi

| Policy intent | Rủi ro |
|---|---|
| Chỉ api.billing.example | Phạm vi hẹp, phải có owner và quản lý thay đổi |
| Các hostname *.billing.example | Bao gồm các subdomains theo semantics của engine; có thể thêm đích ngoài ý định |
| Toàn bộ *.example | Rất rộng, dễ lẫn môi trường hoặc bên thứ ba |
| Cả billing.example và *.billing.example | Phải kiểm tra wildcard có bao gồm apex domain hay không |
| Chỉ suffix "example" theo string matching | Có thể match ngoài ý định nếu không kiểm tra label boundary/normalization |

**Wildcard semantics không đồng nhất giữa DNS firewall, proxy, CNI FQDN policy và URL matcher**. Một số engine hiểu wildcard chỉ một level; số khác hiểu nhiều level. Phải kiểm thử ví dụ cụ thể.

### 7.2. Nguy cơ subdomain takeover

Nếu công ty giữ DNS record trỏ đến dịch vụ bên thứ ba đã hủy nhưng chưa xóa record, một domain/subdomain được allow có thể bị bên khác chiếm quyền phục vụ nội dung trong một số điều kiện. Cần:
1. Quản lý domain owner và DNS record lifecycle.
2. Xóa stale CNAME/A records khi service ngừng.
3. Kiểm tra vendor tenancy/claim process.
4. Review wildcard exceptions định kỳ.
5. Không dựa riêng vào domain allowlist để xác thực business transaction.

### 7.3. IDN, chữ hoa và dấu chấm cuối

Tên miền có thể biểu diễn bằng **Internationalized Domain Names** dạng Unicode hoặc punycode A-label. So khớp policy cần dùng canonical normalization, xử lý case-insensitivity, trailing dot và domain labels đúng. **Không dùng substring match**: allow api.billing.example không có nghĩa allow api.billing.example.attacker.example.

## 8. TLS SNI, HTTP Host, certificate và domain-fronting risk

### 8.1. TLS SNI

**Server Name Indication (SNI)** giúp client cho biết tên server trong TLS ClientHello ở nhiều kết nối TLS. Một số firewall/egress proxy có thể dùng SNI để áp FQDN policy khi thông tin có thể quan sát. Nhưng:
- SNI **không có nghĩa certificate đã được xác minh**.
- SNI là dữ liệu do client gửi, có thể bị giả lập.
- SNI và HTTP Host/authority có thể khác nhau.
- Một số kết nối không có SNI hoặc dùng IP literal.
- ECH có thể che thông tin tên thực cần dùng để phân loại.

### 8.2. HTTP Host / :authority

HTTP/1.1 sử dụng Host header; HTTP/2/HTTP/3 có pseudo-header **:authority**. Nếu proxy giải mã HTTP, nó có thể kiểm tra host, path và method. Nhưng policy phải ràng buộc **destination identity**, không tin một header độc lập.

### 8.3. Domain fronting và mismatch

Một client có thể gửi các giá trị khác nhau ở **destination IP, TLS SNI và HTTP authority**. Nếu enforcement chỉ nhìn một trong các trường và upstream CDN dùng cơ chế routing linh hoạt, chính sách có thể không phản ánh đích thực. Để giảm rủi ro:
- Áp quy tắc consistency giữa **CONNECT target, SNI, HTTP Host/authority và verified server identity** ở điểm hỗ trợ.
- Từ chối hoặc xử lý theo policy khi tên đích không khớp, thay vì mặc định allow.
- Không cho CDN shared-IP range quá rộng nếu business chỉ cần một hostname.
- Sử dụng proxy có hostname allowlist và TLS validation phù hợp.
- Ghi log loại mismatch mà không ghi raw tokens.

### 8.4. TLS interception và privacy

Một forward proxy có thể chỉ làm **CONNECT tunnel** và không đọc HTTP payload. Muốn lọc **path/body**, thường cần terminate/inspect TLS tại điểm được phê duyệt, kéo theo quản lý CA keys, mTLS compatibility, privacy, compliance, hiệu năng và khả năng ứng dụng dùng certificate pinning. **Không bật TLS decryption trên toàn bộ traffic chỉ để xử lý một allowlist domain.**

## 9. ECH, QUIC, HTTP/3 và protocol visibility

### 9.1. Encrypted ClientHello (ECH)

ECH là cơ chế giúp che một phần thông tin TLS ClientHello, bao gồm tên server nhạy cảm trong cấu hình phù hợp. Một **SNI-based policy engine** có thể không nhìn thấy tên thật, vì vậy **không nên quảng cáo rằng SNI matching luôn phân biệt được mọi domain HTTPS**. Cách triển khai và mức hỗ trợ thay đổi theo client, server, TLS stack và policy engine.

### 9.2. HTTP/3 và QUIC

HTTP/3 dùng QUIC, thường qua UDP/443. Một firewall chỉ kiểm tra TCP/443 hoặc proxy chỉ hỗ trợ HTTP CONNECT/TCP có thể không nhìn thấy hoặc xử lý QUIC như mong đợi. Cần:
- Xác định ứng dụng có sử dụng HTTP/3/QUIC không.
- Chọn gateway/proxy hỗ trợ giao thức hoặc buộc traffic đi cơ chế được duyệt.
- Kiểm tra UDP/443 và các paths tương ứng; không giả định TCP policy đủ.
- Theo dõi fallback từ QUIC sang HTTP/2/TCP và ảnh hưởng latency.
- Có plan khi ECH/SNI visibility thay đổi.

### 9.3. Khả năng quan sát không bằng khả năng chứng minh danh tính

Nếu policy engine không có L7 visibility, nó chỉ có thể thực thi điều kiện nó thực sự quan sát được. **Không thể viết một rule “allow exact HTTPS hostname + URL path” trên firewall L3 rồi kỳ vọng có tính bảo đảm L7**. Khi cần chính xác, chọn **explicit proxy/controlled API broker** hoặc application-level destination authorization.

## 10. DNS filtering: một lớp, không phải ranh giới tuyệt đối

DNS filtering có thể allow/deny queries đến domain dựa trên owner/category/policy. Nó hữu ích để giảm tiếp cận domains không mong muốn và cung cấp telemetry tên miền, nhưng **không phải một firewall cho mọi kết nối**.

### 10.1. Những đường vượt ra ngoài DNS filter

- Ứng dụng gọi **hardcoded IP** mà không tra DNS.
- DNS được cache từ trước khi policy đổi.
- Client dùng **DoH/DoT** tới resolver không được phê duyệt.
- Container dùng custom resolver/hosts file.
- Application nhận IP từ API response, redirect hoặc config server.
- Traffic qua VPN/proxy khác có resolver riêng.
- DNS tunnel hoặc query tới một approved resolver có hành vi khác policy dự tính.

### 10.2. Thiết kế resolver có kiểm soát

1. Xác định resolvers được phép, không mở UDP/TCP 53 tới toàn Internet.
2. Cho đúng **UDP/53 và TCP/53** khi ứng dụng thực sự dùng DNS truyền thống.
3. Xem **NodeLocal DNSCache, kube-dns/CoreDNS, local stub resolver** và split-horizon.
4. Quản trị DoH/DoT tới approved resolver theo chính sách, không coi DNS mã hóa mặc định độc hại.
5. Có log/metric DNS lỗi, NXDOMAIN, blocked domain, latency và cache health theo mức cần thiết.
6. Phối hợp DNS filtering với proxy/firewall để direct-IP bypass vẫn bị chặn.
7. Không xem DNS query thành công là bằng chứng HTTPS session tới đích đã thành công.

### 10.3. DNS logging và privacy

DNS queries có thể bộc lộ domain đối tác, tên dịch vụ nội bộ hoặc hành vi truy cập người dùng. Áp **data minimization, retention, access controls** và tránh ghi nguyên query nhạy cảm khi không cần.

## 11. Forward proxy và egress gateway

**Forward proxy** nhận request từ client rồi kết nối đến đích theo policy. **Egress gateway** là một điểm mạng/dịch vụ tập trung cho outbound; có thể dùng HTTP CONNECT, service mesh egress, transparent proxy hoặc cloud managed firewall.

### 11.1. Ba phương án

| Phương án | Ưu điểm | Hạn chế |
|---|---|---|
| **Explicit HTTP(S) forward proxy** | Có thể kiểm soát CONNECT host/port, xác thực caller, access logging | App có thể bỏ proxy nếu direct route mở |
| **Transparent proxy** | Không yêu cầu app biết proxy, quản trị tập trung | NAT/redirect/HTTP3/TLS visibility và debugging phức tạp |
| **Service mesh egress gateway** | Workload identity, policy, telemetry và routing theo mesh | Không tự bảo đảm mọi traffic đi qua gateway |
| **Cloud firewall + DNS proxy** | Phân vùng theo VPC/subnet/CIDR/FQDN tùy dịch vụ | Pod/user identity không phải lúc nào cũng thấy |

### 11.2. Một proxy allowlist đúng nên kiểm tra gì?

- **Caller identity:** mTLS/service account, authenticated device/user hoặc proxy credentials.
- **Destination identity:** exact FQDN/CONNECT host, IP resolution, TLS server identity phù hợp.
- **Protocol/port:** TCP/443, HTTP CONNECT hoặc protocol được cho; không cho arbitrary tunneling ngoài policy.
- **URL/path/method:** chỉ khi proxy thực sự có L7 visibility và business yêu cầu.
- **Redirects:** request mới sau redirect có đi qua check mới không?
- **Rate/bytes:** quota/limits để giảm DLP và DoS risk.
- **Logging:** event allow/deny với source, destination, reason; redact secrets.
- **Bypass:** network firewall chặn direct egress trừ ngoại lệ đã duyệt.
- **HA:** failure mode và path khi gateway down; không mở direct Internet không xét duyệt.

### 11.3. Cẩn thận với HTTPS_PROXY và NO_PROXY

Biến môi trường **HTTP_PROXY/HTTPS_PROXY/NO_PROXY** chỉ là cấu hình client; không phải hệ thống cưỡng chế. Một ứng dụng có thể bỏ proxy, đọc NO_PROXY theo semantics riêng hoặc dùng library không hỗ trợ. **Nếu direct route còn mở, proxy allowlist có thể bị bypass.**

### 11.4. Proxy CONNECT và kiểm tra đích

~~~text
Orders Pod
  -> authenticated proxy
  -> CONNECT api.billing.example:443
  -> proxy kiểm tra allowlist + resolve IP + connect
  -> TLS client xác minh certificate api.billing.example
  -> application request theo hợp đồng
~~~

Với HTTP CONNECT tunnel không giải mã TLS, proxy có thể kiểm tra host/port đích nhưng **không có quyền đọc HTTP request path/body**. Domain allowlist phải kết hợp app/data controls nếu cần giới hạn nội dung.

## 12. SSRF, open redirects và destination validation

**SSRF (Server-Side Request Forgery)** xảy ra khi ứng dụng có thể bị điều khiển để tự gửi request tới destination ngoài ý định, thường thông qua URL fetcher, webhook, image importer hoặc PDF preview. Domain allowlist chỉ có giá trị nếu kiểm tra **toàn bộ chuỗi resolution → redirect → connect**.

### 12.1. Một attack path khái niệm

~~~mermaid
flowchart TD
    USER[Untrusted user input URL] --> APP[URL fetcher service]
    APP --> CHECK{Destination allowlist + URL validation}
    CHECK -->|Approved| PROXY[Controlled egress proxy]
    PROXY --> SAAS[Approved SaaS endpoint]
    CHECK -->|Denied| STOP[Reject + audit]
    APP -.Danger if bypass.-> META[Metadata / private admin endpoint]
    META -.Potential secret exposure.-> RISK[Incident]
~~~

### 12.2. Mẫu kiểm tra nhiều tầng

- **Parse URL bằng thư viện chuẩn**, không chỉ dùng substring/regex.
- Chỉ cho những schemes được duyệt, thường **https**.
- Chuẩn hóa hostname, IDN/punycode, percent-encoding và port.
- Không tin userinfo, hostname trông giống internal domain hay redirect tự động.
- Phân biệt IPv4/IPv6 literal, loopback, link-local, multicast, unique-local/private ranges, IPv4-mapped IPv6 và cách biểu diễn địa chỉ bất thường.
- DNS resolution phải được gắn với **IP thật được kết nối**, không bị thay đổi không kiểm tra.
- Mỗi HTTP redirect phải trải qua allowlist validation mới.
- Chặn metadata/control-plane/internal services trừ khi business purpose đã được duyệt.
- Áp network firewall/CNI deny để app-level validation error không tự tạo đường ra.
- Kiểm tra TLS certificate/hostname; không dùng **insecure TLS** chỉ vì DNS route được allow.

### 12.3. Một đích được phép vẫn có thể làm proxy

Nếu một **approved webhook/URL ingestion service** có khả năng gửi tiếp dữ liệu tới nơi khác mà không kiểm soát, attacker có thể lợi dụng nó làm **trusted intermediary**. Cần kiểm soát API scopes, payload types, tenant authorization, outbound destinations của intermediary và volume/quotas.

## 13. Destination IP/CIDR: địa chỉ không gắn cố định với tổ chức

Một CIDR allowlist dễ thực hiện nhưng có thể rộng hơn mục tiêu bảo mật.

### 13.1. Ví dụ dải

~~~text
Approved partner documentation example:
  FQDN: api.billing.example
  IPv4: 198.51.100.25/32
  IPv6: 2001:db8:abcd::25/128
  Port: TCP/443

Not automatically approved:
  0.0.0.0/0:443
  ::/0:443
  10.0.0.0/8:any
  entire CDN or hosting-provider CIDR
~~~

Những địa chỉ là **dải ví dụ**, không phải IP live. Luôn quản trị IP ownership, address change, DNS answers, application TLS validation và rủi ro shared hosting.

### 13.2. Nhóm IP cần xử lý đặc biệt

- **Loopback:** không cho một dịch vụ fetch từ xa tùy ý truy cập admin trên localhost.
- **Link-local:** có thể bao gồm endpoints metadata/host services; không coi mặc định là Internet thường.
- **Private RFC1918/IPv6 ULA:** các mạng management, DB hoặc hybrid cần tách trust domain.
- **Multicast/broadcast:** không giống API destination thông thường.
- **Cloud provider addresses:** có thể là private endpoints hoặc control plane; phải xét IAM và trust.
- **IPv4-mapped IPv6 / NAT64:** khả năng chuyển đổi địa chỉ có thể ảnh hưởng validation.
- **Shared CDN IP:** có thể phục vụ nhiều tenants/domains, không tương đương SaaS identity.

### 13.3. Route và permission là hai việc

Một VPC route tới CIDR không tự cho permission vào service; firewall và authorization vẫn cần. Ngược lại, allowlist IP ở CNI không có nghĩa packet có route hợp lệ hoặc TLS server đúng. **Thiết kế phải kết hợp cả chiều đi, chiều về và identity.**

## 14. Ma trận các lớp kiểm soát

| Lớp | Có thể enforce | Không tự enforce |
|---|---|---|
| **DNS resolver/filter** | Query domains, resolver policy | Connections hardcoded IP, L7 payload |
| **L3/L4 firewall** | Source/destination IP, port, protocol, connection state | Exact hostname, URL, verified user |
| **FQDN-aware firewall/CNI** | Mapping tên miền→IP theo khả năng vendor | URL path, business operation; DNS bypass có thể tồn tại |
| **HTTP proxy / API gateway** | CONNECT host, HTTP route/method theo visibility, caller identity | Tự chặn direct route ngoài proxy |
| **TLS client** | Server certificate + hostname verification | DLP nội dung ở mọi hop |
| **mTLS/service mesh** | Workload peer identity, service authz khi đi qua datapath | End-user object authorization |
| **Application** | URL validation, workflow, request payload, tenant scope | Toàn bộ network egress nếu không có firewall |
| **DLP engine** | Data classification/detection và policy tùy vị trí | Mọi nội dung của traffic end-to-end encrypted nếu không có visibility |
| **Cloud IAM/endpoint policy** | Quyền resource/API, private endpoint | URL path của SaaS không thuộc quyền |
| **Monitoring/SIEM** | Audit, anomalous traffic, alerts | Mặc định chặn packet |

Một kiến trúc trưởng thành đặt **nguyên tắc deny tối thiểu tại lớp mạng**, **xác thực/authorization tại lớp identity và ứng dụng**, **DLP tại điểm thấy nội dung hợp pháp**, **telemetry độc lập** để kiểm chứng và phát hiện sai lệch.

## 15. Kubernetes NetworkPolicy và giới hạn của FQDN allowlist

**Core Kubernetes NetworkPolicy** hỗ trợ Pod/namespace selectors, IP CIDR, protocol và port khi CNI thực thi. Nó **không có trường FQDN** và không hiểu URL, Host header, TLS identity hoặc payload. Vì vậy, muốn domain allowlist phải kết hợp proxy, CNI extension hoặc firewall có khả năng tương ứng.

### 15.1. Baseline default-deny egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: orders-prod
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Rule này chọn mọi Pods trong namespace orders-prod và cô lập egress theo cơ chế chuẩn **nếu CNI thực thi**. Nếu có các NetworkPolicies khác cho egress, quyền là **hợp của các allow rules**, không có thứ tự deny priority ở core API.

### 15.2. Cho phép đúng DNS path trong lab

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-dns
  namespace: orders-prod
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

Chỉ có ý nghĩa nếu DNS Pods/namespace có đúng labels và DNS traffic thực sự đi qua datapath CNI tương ứng. **NodeLocal DNSCache, Service VIP/ClusterIP translation, DNS proxy** có thể yêu cầu cấu hình khác. Hai selectors nằm **cùng một phần tử to** là AND; tách thành hai phần tử là OR.

### 15.3. Chỉ cho Orders tới egress proxy

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-to-proxy
  namespace: orders-prod
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: egress-security
          podSelector:
            matchLabels:
              app: egress-proxy
      ports:
        - protocol: TCP
          port: 3128
~~~

Policy này **chỉ mở network tới proxy**, không tự giới hạn proxy cho domain nào. Proxy cần client authentication, allowlist đích và TLS controls; source vẫn cần DNS policy nếu có resolver access. Destination proxy nếu ingress-isolated phải có ingress allow đúng. Chặn direct Internet/IPv6/hostNetwork bypass ở network/cloud layer.

### 15.4. IP cố định trong một lab tách biệt

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: lab-allow-fixed-ip
  namespace: lab-egress
spec:
  podSelector:
    matchLabels:
      app: lab-client
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 198.51.100.25/32
      ports:
        - protocol: TCP
          port: 443
~~~

Đây là ví dụ cho **lab riêng**, không áp thêm vào Orders proxy-only vì như vậy mở direct exception. IP thuộc dải tài liệu. **ipBlock** không xác minh FQDN/TLS identity và các vấn đề Service DNAT/CNI semantics phải được kiểm chứng.

### 15.5. Node egress không đồng nhất Pod egress

Node image pulls và các traffic phát từ kubelet/container runtime hoặc hostNetwork Pod có thể nằm ngoài phạm vi Core NetworkPolicy. Giới hạn bằng host/network/cloud firewall, node IAM và admission policies khi phù hợp; không kết luận namespace default deny đã bảo vệ mọi egress của node.

## 16. FQDN-aware CNI và cloud firewall

Một số CNI/firewall cung cấp **FQDN policies** dạng mở rộng riêng. Chúng có thể học IP từ DNS answer, chạy DNS proxy hoặc dùng proxy SNI/HTTP, tùy nhà cung cấp.

### 16.1. Câu hỏi kiểm tra vendor

1. FQDN policy có hiểu **A/AAAA, CNAME, TTL, negative cache và wildcard** không?
2. Có kiểm tra hostname ở kết nối hay chỉ **domain-to-IP mapping**?
3. Nếu hai domains cùng IP thì allow domain A có vô tình allow domain B không?
4. DNS via DoH/DoT, custom resolver hoặc hardcoded IP có bị kiểm soát không?
5. Có hỗ trợ **IPv6, UDP/443, HTTP/3, ECH và TLS passthrough** không?
6. Có priority/deny override khác Core NetworkPolicy không?
7. Có per-workload identity và authenticated source hay chỉ source IP sau NAT?
8. Khi DNS proxy/policy engine lỗi, **fail-open hay fail-closed**?
9. Có logs/simulation/canary cho positive và negative tests không?
10. Với hostNetwork/mesh/Cloud NAT, điểm thực thi có còn đúng không?

### 16.2. Mẫu biểu diễn ý định

~~~yaml
# Policy registry pseudocode; KHÔNG phải Cilium/Calico/vendor CRD.
rule_id: "orders-partner-egress"
source:
  namespace: "orders-prod"
  workload: "orders-api"
  identity: "serviceaccount:orders-api"
destinations:
  - fqdn: "api.billing.example"
    protocol: "tcp"
    port: 443
    tls_server_name: "api.billing.example"
network_enforcement: "proxy-only"
proxy_enforcement: "exact-hostname-and-client-auth"
default: "deny"
dns_resolver: "approved-corporate-resolver"
include_ipv6: true
owner: "billing-platform"
review_due: "2027-01-31"
evidence: ["canary-connectivity", "negative-domain-test", "policy-version"]
~~~

Trường tls_server_name **không thể thực thi chỉ bằng một firewall L3**. Đây là mô hình quản trị; cần chuyển sang sản phẩm/schema cụ thể và kiểm chứng thật.

## 17. Egress trên cloud: routes, NAT, firewall và private endpoints

~~~mermaid
flowchart LR
    A[Workload / Pod] --> V[VPC Routes]
    V --> H[Transit Hub]
    H --> I[Inspection Firewall / Proxy]
    I --> N[NAT / Egress IP]
    N --> S[Approved SaaS]
    V -.Private route.-> P[Cloud Private Endpoint]
    I -.Audit.-> MON[SIEM]
~~~

Một transit hub chỉ **định tuyến**, không tự kiểm tra domain. Firewall/cloud route tables, inspection appliances và DNS proxies phải tạo đường đi/đường về chính xác.

### 17.1. Private endpoint là một đường riêng

Một workload gọi Object Storage/Queue/KMS qua private endpoint có thể **không đi qua Internet egress gateway**. Để tránh lỗ hổng:
- Inventory endpoint, resolver private zones và account/region.
- Hạn chế source workloads bằng SG/CNI/network controls.
- Hạn chế resource bằng **IAM/resource policy/endpoint policy** khi hỗ trợ.
- Audit API operations và cloud identity.
- Đánh giá endpoint có bypass DLP/content inspection không.
- Test trực tiếp từ Dev/Prod khác nhau, không tin tên private tự bảo đảm permission.

### 17.2. Multi-AZ/region và failover

Khi egress proxy/NAT failover:
- Partner cần biết **public egress IP** mới nếu dùng IP allowlist.
- Policy exact domains và identity phải tương đương.
- TLS client cert/truststore/secret rotation phải hoạt động ở standby.
- Cần giữ denied destinations vẫn deny, không tự mở direct Internet.
- Kiểm tra DNS cache, route symmetry, latency/cross-zone cost và logs.

### 17.3. Capacity

Theo dõi active connections, requests/s, bytes/s, proxy CPU, NAT port exhaustion, connection tracking, TLS handshakes, cross-region transfer và log volume. Không vô hiệu hóa inspection/logging để xử lý chậm trước khi có đánh giá rủi ro.

## 18. DLP và allowlist domain: hai biện pháp khác nhau

**DLP (Data Loss Prevention)** ngăn hoặc phát hiện dữ liệu nhạy cảm rời tổ chức. Domain allowlist **giảm tập đích có thể tiếp cận**, nhưng không biết nội dung của một HTTPS upload có chứa thông tin khách hàng, API key hay mã nguồn không.

| Lớp | Kiểm soát chính | Giới hạn |
|---|---|---|
| Source data authorization | Ai đọc/xuất được hồ sơ nào | Không thay network egress |
| Domain/IP allowlist | Đường kết nối tới approved destinations | Không phân loại payload |
| Proxy/SWG/SSE DLP | Upload/HTTP content khi có visibility | TLS inspection, privacy, false positives |
| SaaS API/CASB policy | Quyền trong approved SaaS tenant | Provider/app semantics |
| Endpoint DLP | Copy/upload trên managed device | Device posture và data access |
| Cloud IAM/resource policy | Resource/bucket/queue/object access | Không kiểm tra mọi app-specific dữ liệu |
| Volume/behavior analytics | Bulk exports, unusual bytes/route | Không tự khẳng định rò rỉ |

### 18.1. Approved destination vẫn có thể là kênh exfil

Nếu app được phép upload tới một dịch vụ object storage hoặc logging SaaS, dữ liệu nhạy cảm có thể bị gửi ra **đúng domain allowlist** khi IAM/app validation sai. Bổ sung:
1. **Resource/tenant-scoped credentials**, không chỉ allowed domain.
2. Business authorization và data classification trước khi xuất.
3. DLP ở điểm có quyền xử lý nội dung.
4. Quota, anomaly detection và audit export actions.
5. Kiểm soát shared proxy/intermediary có thể chuyển tiếp dữ liệu.
6. Data retention và review quyền truy cập SaaS.

### 18.2. TLS end-to-end

Nếu proxy chỉ làm HTTP CONNECT mà không giải mã TLS, nó thường thấy host/port/bytes nhưng **không thấy HTTP body**. Content DLP cần điểm có visibility và quyền phù hợp, ví dụ application gateway, CASB/SaaS API hoặc endpoint DLP. Không tuyên bố “DLP mọi HTTPS” dựa vào IP/domain allowlist.

## 19. Source-specific policy theo business intent

| Source | Destination | Lý do nghiệp vụ | Chính sách |
|---|---|---|---|
| Orders API Prod | api.billing.example | Tạo invoice | Exact FQDN, TLS/443, API auth |
| Payment Worker | Bank partner gateway | Payment instruction | mTLS identity, partner contract |
| Build Runner | Corporate artifact mirror | Tải dependency | Registry allowlist + checksum/signing |
| Metrics Agent | Approved OTel Collector | Gửi telemetry | Collector identity, TLS, redaction |
| Backup Agent | Backup tenant/bucket | Sao lưu | Resource scope, rate, data classification |
| User browser | Approved enterprise SaaS | Công việc có SSO | SWG/CASB + device posture khi dùng |
| Dev Pod | Production DB | Không có nhu cầu | Deny segmentation + DB authZ |

**Không dùng một allowlist chung cho mọi nguồn**. Một domain được phép cho Build Runner không có nghĩa Payment Worker phải được quyền gọi nó.

### 19.1. Nguồn theo identity, không chỉ IP

Source có thể được nhận diện bằng service account, mTLS workload identity, managed device/user SSO hoặc cloud principal. NAT/gateway có thể che Pod IP ở firewall ngoài; dùng client auth và correlation trước SNAT nếu cần per-workload policy.

### 19.2. Domain có nhiều chức năng

Một domain SaaS có thể vừa cung cấp read API vừa cho upload/bulk export. Khi yêu cầu phân biệt route/method, chỉ dùng engine **có L7 visibility** và kiểm soát ở ứng dụng. Firewall L4 không thể lọc HTTP path trong TLS tunnel.

## 20. SaaS, CDN và domains thay đổi liên tục

SaaS có thể công bố hostnames, CDN domains, identity-provider redirects và IP lists theo region/tính năng. Nguy cơ:
- Pin **một CDN IP** khiến app mất kết nối khi DNS thay.
- Allow **toàn bộ provider CIDR** mở nhiều tenants/services khác.
- Wildcard rộng chứa subdomains cũ, staging hoặc takeover candidates.
- Hostnames thay đổi nhưng exception không có owner.

### 20.1. Biện pháp

- Chọn authenticated domain proxy hoặc FQDN-aware enforcement có DNS/TTL support.
- Sử dụng vendor-published requirements từ nguồn được phê duyệt; có change review.
- Dùng exact hostnames khi có thể, review wildcard semantics.
- TLS hostname verification và đúng SaaS tenant/account.
- Bảo vệ resource action qua IAM/OAuth scopes.
- Kiểm thử trước và sau vendor DNS/CDN/region changes.
- Có private endpoint khi business/provider hỗ trợ và IAM được quản lý.

### 20.2. Identity provider redirect

Một luồng đăng nhập có thể cần IdP, CDN và OAuth callbacks. Inventory *required destinations*, nhưng không biến toàn bộ Internet login category thành global allow. Mỗi domain cần scope, port, owner và business purpose.

## 21. Policy-as-code và exception lifecycle

Một allowlist entry cần được quản trị **như một thay đổi quyền**, không chỉ chỉnh text ở firewall.

### 21.1. Registry rule minh họa

~~~yaml
# Schema nội bộ minh họa, KHÔNG phải deployment YAML vendor.
rule_id: "EGR-ORDERS-001"
source:
  environment: "production"
  namespace: "orders-prod"
  workload: "orders-api"
destination:
  fqdn: "api.billing.example"
  exact_match: true
  protocol: "tcp"
  port: 443
purpose: "Create partner invoices"
data_classification: "confidential"
owner: "billing-platform"
security_reviewer: "network-security"
approval: "CHG-example-001"
review_due: "2027-01-31"
enforcement: ["cni-proxy-only", "authenticated-proxy-hostname-rule"]
tests:
  allow: ["orders-api -> api.billing.example:443"]
  deny:
    - "orders-api -> unknown.example:443"
    - "dev-api -> api.billing.example:443"
~~~

Quy tắc này nói rõ *ý định*, chưa phải điều kiện tự thực thi trên mọi engine. Cần review pipeline chuyển sang CNI/firewall/proxy config thực tế.

### 21.2. Vòng đời rule

1. **Request:** source, exact destination, port, protocol, owner, business purpose.
2. **Risk review:** domain ownership, wildcard/CDN, TLS, data classification, alternate paths.
3. **Approve:** security reviewer, time limit nếu ngoại lệ.
4. **Implement:** policy-as-code, IaC diff, test plan và rollback.
5. **Test:** positive + negative, DNS cache/IPv6/proxy bypass.
6. **Canary:** theo dõi availability và security denies.
7. **Operate:** monitor drift, unknown domains, destination changes, DLP alerts.
8. **Review/revoke:** xác nhận còn nhu cầu hoặc thu hồi rule, sau đó chạy deny tests.

### 21.3. CI guardrails

Flag hoặc từ chối:
- 0.0.0.0/0:443, ::/0:443 nếu không có phê duyệt đặc biệt.
- Wildcard hoặc suffix matching ngoài ý định.
- Rule không có source/owner/review_due.
- TLS hostname verification bị tắt.
- Domain allow nhưng direct outbound bypass proxy vẫn mở.
- IP/CDN list không có source/version/expiry.
- Policy change thiếu negative tests và rollback.
- Rule đồng nhất Dev/Prod/Mgmt không có lý do.
- Dữ liệu Restricted được gửi tới non-approved SaaS tenant.

**Policy lint không thay runtime test** vì DNS cache, NAT, CNI và TLS path có thể khác mong đợi.

## 22. Telemetry: chứng minh đường đi thay vì chỉ tin policy

| Nguồn | Có thể thấy | Giới hạn |
|---|---|---|
| DNS logs | Query FQDN, resolver, answer, deny | Hardcoded IP, custom DNS/DoH |
| CNI/host firewall | Pod/IP/port, allow/deny | Không tự biết HTTPS domain |
| Cloud flow logs | Flow/bytes/traffic path | Có thể chỉ thấy NAT IP |
| Proxy access logs | Caller, CONNECT host, policy decision, latency | Không thấy TLS body nếu tunneling |
| Application audit | User/tenant, API operation, business data classification | Không tự thấy mọi network hop |
| DLP/CASB | Data policy matches khi có visibility | False positives/visibility/privacy |
| Cloud/K8s audit | Ai đổi route, policy, IAM, endpoint | Không chứng minh từng request |
| IDS/IPS/NDR | Network anomaly tại sensor | Blind spots nếu traffic không đi qua |

### 22.1. Log decision schema

~~~json
{
  "timestamp_utc": "2026-11-28T07:00:00Z",
  "source_namespace": "orders-prod",
  "source_workload": "orders-api",
  "source_identity_verified": "spiffe://example.test/ns/orders-prod/sa/orders",
  "decision_layer": "authenticated-egress-proxy",
  "decision": "deny",
  "destination_hostname": "unknown.example",
  "destination_port": 443,
  "reason_class": "domain_not_approved",
  "policy_id": "EGR-ORDERS-001"
}
~~~

Đây là **schema tùy chỉnh minh họa**, không phải output native proxy. Trường verified identity chỉ có ý nghĩa khi lấy từ trustable TLS/proxy auth state, không từ user-supplied header. Không ghi JWT, Cookie, API key, full query strings hoặc payload nhạy cảm.

### 22.2. Chỉ số nên giám sát

- Allow/deny decisions theo workload, policy, hostname.
- Unexpected domains và policy wildcard use.
- DNS cache/TTL churn, query failures, A/AAAA changes.
- Proxy p95 latency, errors, 403/502, retries, saturation.
- NAT port exhaustion và throughput anomalies.
- Direct flows ngoài proxy từ workloads buộc phải dùng proxy.
- DLP events, false positive rate, unusual bulk upload.
- Policy changes, stale exceptions, missing owner.
- Collector/flow log ingestion loss và telemetry freshness.

**Không có log không chứng minh không có traffic**; phải kết hợp network path inventory, independent flows và controlled tests.

## 23. Threat model cho allowlist egress

| Actor/điều kiện | Rủi ro | Lớp phòng vệ |
|---|---|---|
| Compromised application Pod | Gửi data ra random host | Default deny + proxy exact allowlist |
| SSRF vào URL fetcher | Redirect/rebind sang private/metadata IP | Validate URL, resolved IP, redirect; network deny |
| Bị lộ proxy credential | Gọi approved destinations ngoài mục đích | Workload identity, quota, authZ, rotation |
| Approved SaaS bị lạm dụng | Gửi dữ liệu qua domain hợp lệ | SaaS tenant/IAM scope, DLP, application audits |
| CI/policy admin credential bị lộ | Mở default routes/wildcards | IAM least privilege, GitOps, config audit |
| CDN IP thay đổi | Availability outage hoặc mở rule quá rộng | FQDN policy đúng semantics, owner, canary |
| Proxy/gateway outage | Fail-open security gap hoặc loss of service | HA, approved failure mode, rollback |
| DNS hijack hoặc cache sai | Kết nối tới server không đúng | TLS hostname verification, trusted resolution |
| Proxy-based blind spot | Direct QUIC/IPv6/PrivateLink bypass | CNI/cloud firewall và negative tests |

### 23.1. Hai nhánh minh họa

~~~text
Một Pod bị xâm nhập
  -> thử kết nối random external host
  -> network/CNI deny nếu chính sách thực thi đúng

Nhánh thứ hai:
  -> gửi dữ liệu tới approved SaaS endpoint
  -> nếu API token cho phép upload rộng và không có DLP
  -> dữ liệu vẫn có thể rời mạng qua domain hợp lệ
~~~

Điều này chỉ ra allowlist cần phối hợp **source data authorization, application scopes, identity, quota, DLP và audit**.

### 23.2. Bảo vệ control plane

Quyền đổi **DNS, NetworkPolicy, gateway policy, VPC routes, SG, IAM và cloud endpoints** có thể làm thay đổi đường egress. Phân tách ApplicationOwner, NetworkOperator và SecurityReviewer; dùng MFA/SSO, least privilege và audit. Một emergency exception phải có owner, time limit, scope và test rollback.

## 24. URL/path allowlist cần enforcement L7

Một domain có thể có:
- GET /v1/status — thao tác tra cứu.
- POST /v1/upload — luồng dữ liệu đi ra.
- POST /v1/admin/export — thao tác nhạy cảm.

Firewall IP/port không phân biệt các thao tác này. Proxy CONNECT không giải mã TLS chỉ biết host/port ở điểm tunnel, **không thấy path/body**. Khi cần giới hạn URL/method:
- Dùng **trusted L7 proxy/API gateway** có visibility và quyền phù hợp.
- Dùng application HTTP client với allowed operations và schema payload.
- Scope OAuth/IAM/API token phía SaaS.
- Giới hạn redirects, uploads, tenant/resource access.
- Bảo vệ TLS inspection CA, privacy và compatibility khi TLS interception được phê duyệt.

**Substring matching của toàn URL không an toàn:** một hostname được phép có thể nằm trong URL path/query của hostname không được phép. Dùng URL parser, normalize authority, scheme, port và exact host comparison.

## 25. Allowlist cho registries, build runners và node egress

Pod Runtime, node image pull và CI package download là **ba nguồn khác nhau**:
- Kubelet/container runtime thường pull image **trước khi Pod khởi chạy**; Pod NetworkPolicy thường không quản lý việc này.
- CI runner có quyền mạng và credentials để tải package/dependencies.
- App container tự tải binary/package tại runtime tạo egress của workload.

Biện pháp:
1. Dùng approved artifact mirror/registry.
2. Cho đúng domain/IP/port của node và build runner.
3. Pin versions/digests và kiểm tra image signature/provenance/SBOM khi có quy trình.
4. Cấp registry credentials scope nhỏ, rotate secrets.
5. Review vendor CDN dependencies, DNS/redirects.
6. Hạn chế production runtime package downloads.
7. Tách update channel với business external API egress.

**Domain allowlist tới registry không chứng minh artifact an toàn**; cần integrity verification và supply-chain controls.

## 26. Hybrid/VPN và private destinations

Một container cloud có thể gọi ERP on-prem qua VPN/private circuit hoặc transit hub. Dù không qua Internet, vẫn cần:
- Split-horizon DNS và private FQDN accuracy.
- BGP/route/CIDR overlap management, return path.
- Firewall/segment theo source workload→destination service/port.
- TLS/mTLS và application authorization.
- Audit/IDS/IPS ở đúng path.
- Data classification khi dữ liệu rời cloud/region.
- Test HA/failover có security parity.
- Không tự allow toàn 10.0.0.0/8 chỉ vì thuộc mạng nội bộ.

**Private endpoint hoặc VPN không chứng minh end-user được quyền gọi mọi application**.

## 27. Lộ trình rollout egress allowlist

### Giai đoạn 1: Discovery

1. Inventory workloads/users/devices, owners, environment.
2. Thu DNS, proxy, CNI và cloud flow logs đủ chu kỳ batch/renewal.
3. Phân loại destinations required/optional/unknown/deprecated.
4. Xác định exact FQDN, IP/CIDR, protocols, data types, source identity.
5. Kiểm tra node vs Pod, IPv6, QUIC, DoH/DoT, private endpoints và alternative paths.
6. Đo baseline application SLO và traffic rate.

### Giai đoạn 2: Policy design

1. Định nghĩa default deny tại enforcement points.
2. Cho đúng DNS/identity/telemetry dependencies cần thiết.
3. Mỗi domain rule có owner/purpose/review_due.
4. Với dynamic SaaS dùng FQDN-aware proxy/firewall thay IP pinning sai.
5. Với confidential data thêm DLP/resource/tenant authorization.
6. Kiểm tra wildcard, CNAME, redirects, ECH/QUIC/TLS visibility.
7. Lập test matrix và safe rollback.

### Giai đoạn 3: Staging

1. Positive tests cho approved destinations.
2. Negative tests cho unknown domain, direct IP, Dev→Prod, metadata ngoài quyền.
3. DNS A/AAAA/CNAME/TTL/cache và dual-stack tests.
4. Proxy bypass, redirect/URL parsing và TLS hostname validation.
5. DLP rule với **dữ liệu giả**, không dùng dữ liệu khách hàng.
6. Đo latency, proxy/NAT capacity, cert rotation và token renewal.
7. Lưu policy version, test evidence và reviewer.

### Giai đoạn 4: Production canary

1. Deploy một workload/namespace có owner.
2. Theo dõi app success, p95, proxy denies/502, DNS failures.
3. So proxy logs với cloud flow logs để phát hiện direct bypass.
4. Không mở 0.0.0.0/0:443 chỉ để sửa một dependency.
5. Cấp exception hẹp có expiry và approval nếu thực sự cần.
6. Mở rộng theo waves, có rollback.
7. Đảm bảo DR/standby gateway giữ nguyên security controls.

### Giai đoạn 5: Ongoing operations

- Review domain stale/wildcard/ownership.
- Theo dõi vendor DNS/CDN/certificate changes.
- Chạy regression tests sau CNI/proxy/cloud upgrade.
- Alert policy drift, unexpected egress, telemetry loss.
- Thu hồi exceptions không còn cần và chứng minh deny sau thu hồi.

## 28. Chẩn đoán lỗi theo triệu chứng

### 28.1. DNS resolve được nhưng HTTPS timeout

**Có thể:** FQDN-to-IP mapping chưa cập nhật, IPv6 thiếu policy, proxy/firewall/NAT/return path lỗi hoặc network route không đúng. So DNS answer, actual destination IP, CNI/proxy decision và TLS logs.

### 28.2. SaaS hôm qua chạy, hôm nay lỗi

**Có thể:** CDN đổi A/AAAA, CNAME, IdP redirect, cert hoặc provider thêm domain. Xem vendor dependencies và TTL, không mở toàn provider CIDR không kiểm soát.

### 28.3. Proxy trả 403 cho domain trong allowlist

**Có thể:** proxy client auth, CONNECT port, hostname mismatch, path policy hoặc upstream application 403. Phân biệt **proxy-generated** và **upstream-generated** 403 bằng logs.

### 28.4. DNS deny nhưng hardcoded IP vẫn kết nối

DNS filtering không chặn trực tiếp IP. Áp CNI/firewall/proxy-only egress và test direct-IP deny trong lab.

### 28.5. Allow domain A nhưng domain B cùng IP vẫn đi được

Có thể **shared CDN IP**, DNS-to-IP matching, wildcard rule hoặc một allow-all rule khác. Xác minh semantics của engine, TLS SNI/Host consistency và actual connected IP.

### 28.6. Proxy logs không thấy request dù app kết nối thành công

Có thể direct route, PrivateLink, hostNetwork/node egress, logging loss hoặc alternate gateway. Đối chiếu cloud/CNI flow logs, routes và proxy configuration.

### 28.7. App lỗi sau bật TLS inspection

Có thể truststore, pinned certificate, mTLS, HTTP/3/ALPN hoặc proxy root CA issue. Xác minh hợp đồng bảo mật; không tắt certificate verification.

### 28.8. Identity thất bại sau chặn metadata

Có thể workload identity cần endpoint theo provider. Kiểm tra cloud IAM và approved identity flow, không mở metadata access cho mọi Pod.

### 28.9. Failover proxy khiến partner từ chối

Egress public IP hoặc mTLS cert khác standby, partner không allow. Kiểm tra IP inventory, partner allowlist, credentials, DNS và HA security parity.

### 28.10. DLP chặn nhầm upload hợp lệ

Xác minh classification, rule, false positives, app authorization và privacy. Đề xuất exception hẹp/time-bound, không tắt DLP toàn cục.

### 28.11. IPv4 bị deny nhưng IPv6 đi được

Kiểm tra AAAA records, ::/0 route, IPv6 SG/CNI/cloud firewall và QUIC. IPv4-only tests không chứng minh dual-stack security.

### 28.12. Proxy-only rollout tăng latency

Xem cross-AZ hairpin, proxy CPU, TCP/TLS handshake, NAT exhaustion, retries, DNS latency. Tối ưu capacity/HA theo đo lường và không tự mở direct Internet.

## 29. Thiết kế kiểm thử: allow và deny đều cần bằng chứng

Một triển khai allowlist được coi là **phù hợp** chỉ khi:
- Workloads hợp lệ có thể gọi đúng approved destinations.
- Workloads không được cấp quyền **không thể** gọi đích đó.
- Đích không có trong danh sách bị từ chối ngay cả khi dùng direct IP, IPv6 hoặc path ngoài proxy.
- Security controls giữ hiệu lực trong **failover, upgrade, autoscaling và DNS changes**.
- Có telemetry chứng minh hành vi thật, không chỉ một YAML được chấp nhận.
- Cơ chế application auth, TLS verification và DLP không bị nới để đạt connectivity.

### 29.1. Các thông tin của một test

Mỗi test cần tối thiểu:
- **ID, owner, version, approval**.
- Source: workload/Pod UID, namespace, user/device hoặc node.
- Destination: hostname, connected IP, protocol/port, intended API.
- Policy: CNI/firewall/proxy/URL rules, version, exact/wildcard semantics.
- Expected network outcome: allow hoặc deny.
- Expected application outcome: 2xx, auth failure, TLS validation failure hoặc business result theo hợp đồng.
- Đơn vị thời gian UTC, DNS answers, proxy/firewall logs và application audit.
- **Actual, status PASS/FAIL/NOT_RUN/BLOCKED/INCONCLUSIVE**, rollback notes.

### 29.2. Kiểm thử khác với quét mạng

Không cần dò cổng hàng loạt hoặc gửi request tới host bên thứ ba. Dùng **lab endpoints được cấp phép** giả lập approved/denied destinations, một số địa chỉ tài liệu nếu được route trong lab và synthetic HTTPS server có certificate đúng. **Không kiểm thử cloud metadata bằng cách lấy credentials thật**, chỉ kiểm chứng route/policy deny và sử dụng mock endpoint phù hợp.

### 29.3. Mục tiêu mỗi lớp

| Lớp | Positive test | Negative test |
|---|---|---|
| DNS | Approved resolver trả đúng FQDN | Custom/unapproved resolver bị chặn theo policy |
| CNI/firewall | Orders được tới proxy | Orders không direct-connect unapproved IP |
| Proxy | Orders CONNECT approved domain | Wrong source hoặc wrong domain bị deny |
| TLS | Certificate và hostname hợp lệ | Mismatch/expired/untrusted certificate bị từ chối |
| Application | Token đúng audience/scope | Token sai hoặc resource ngoài quyền bị deny |
| DLP | Payload giả hợp lệ được upload | Dữ liệu mẫu nhạy cảm được policy xử lý đúng |
| Monitoring | Event có identity/policy version | Ingest/export mất dữ liệu có cảnh báo |
| HA | Allowed flow phục hồi qua standby | Denied flow vẫn bị deny sau failover |

## 30. Ma trận kiểm thử allowlist domain và destination

Các cases dưới đây **chỉ là test plan**. Chạy trong lab/staging được cấp phép hoặc production change window theo quy trình đã duyệt; không coi kỳ vọng là kết quả đã đo.

| ID | Kịch bản | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| A01 | Orders Prod → approved FQDN qua proxy | Allowed, TLS hostname verified | Proxy + app logs |
| A02 | Orders Prod → unapproved FQDN qua proxy | Denied | Policy decision log |
| A03 | Dev Pod → approved Prod partner domain | Denied theo nguồn | Identity + proxy event |
| A04 | Unknown source tới egress proxy | Không tự nhận quyền | Proxy auth log |
| A05 | Default-deny egress mới | CNI thật sự enforce | Matching policy + flow |
| A06 | Có allow-all policy khác chọn Pod | Phát hiện unintended union | NetworkPolicy inventory |
| A07 | DNS query tới approved resolver | Allowed UDP/TCP 53 | DNS/CNI logs |
| A08 | DNS query tới unapproved resolver | Denied | Firewall/CNI verdict |
| A09 | NodeLocal DNSCache được dùng | DNS path đúng implementation | DNS cache/flow evidence |
| A10 | DoH đến resolver không được duyệt | Bị chặn hoặc buộc qua managed resolver | Proxy/firewall logs |
| A11 | DoT không được phê duyệt | Denied theo policy | TCP/853/proxy verdict |
| A12 | Client dùng hardcoded external IP | Không bypass domain-only policy | CNI/cloud flow logs |
| A13 | Approved FQDN đổi A record | Policy tiếp tục đúng theo thiết kế | DNS TTL + proxy |
| A14 | Approved FQDN trả AAAA record | IPv6 outcome tương đương IPv4 | IPv6 routes/flows |
| A15 | CNAME sang shared CDN IP | Không mở toàn bộ domain khác | FQDN-engine test |
| A16 | Unapproved hostname dùng cùng CDN IP | Denied nếu policy yêu cầu exact hostname | Proxy TLS/SNI decision |
| A17 | Wildcard hostname ở nhiều mức | Match đúng semantics đã duyệt | Domain matching test |
| A18 | Apex domain so với wildcard | Không nhầm subdomain và apex | Policy engine result |
| A19 | Domain có uppercase/trailing dot | Canonical matching đúng | Hostname normalization test |
| A20 | IDN/punycode hostname trong lab | Match đúng canonical identity | Parsed hostname evidence |
| A21 | Hostname chứa approved domain như substring | Không được allow | URL parser/proxy decision |
| A22 | HTTP redirect sang domain không duyệt | Request mới bị check và deny | Proxy/app audit |
| A23 | DNS rebinding trong lab giả lập | Actual connected IP được kiểm soát | DNS/connection verdict |
| A24 | Redirect tới private/loopback lab endpoint | Denied khi ngoài quyền | Application URL validation |
| A25 | Link-local/metadata path ngoài quyền | Denied; không truy xuất secrets | Network policy snapshot |
| A26 | Approved hostname nhưng TLS cert sai | Client từ chối | TLS verification log |
| A27 | CONNECT target và TLS SNI không khớp | Proxy xử lý theo policy an toàn | Proxy decision |
| A28 | HTTP Host khác verified destination | Phát hiện inconsistency tại L7 point | Gateway/proxy log |
| A29 | ECH bật khi SNI policy cần visibility | Không fail-open ngoài thiết kế | Firewall/proxy verdict |
| A30 | HTTP/3/QUIC qua UDP/443 | Không bypass TCP-based controls | UDP policy flow evidence |
| A31 | Proxy outage trong lab | Failure mode đúng; không direct bypass | HA + CNI tests |
| A32 | NAT failover đổi public source IP | Partner access đúng contract | Egress IP + partner logs |
| A33 | IPv4 deny nhưng thử kết nối IPv6 | Vẫn deny nếu ngoài quyền | Dual-stack evidence |
| A34 | Cloud private endpoint tới storage | Resource IAM/endpoint policy đúng | Cloud audit + route |
| A35 | Dev gọi Prod qua private endpoint | Từ chối nếu không được cấp | IAM + API audit |
| A36 | On-prem private FQDN qua VPN | Đúng route và firewall | Resolver + hybrid flow |
| A37 | Package registry image pull từ node | Có node-specific allowlist | Node runtime logs |
| A38 | App container tải package tùy ý | Bị policy giới hạn | App egress logs |
| A39 | Approved SaaS upload bị app authZ deny | Từ chối dù domain allow | App audit |
| A40 | SaaS tenant/bucket ngoài quyền | Bị resource policy chặn | Provider IAM audit |
| A41 | DLP dùng synthetic sensitive payload | Đúng policy, không log dữ liệu thật | DLP event |
| A42 | DLP false positive hợp lệ | Có quy trình appeal/exception | Reviewer ticket |
| A43 | Proxy log chứa Authorization header | Redaction loại bỏ | Sanitized test logs |
| A44 | Source sau NAT dùng IP chung | Truy vết tới workload identity được | NAT mapping + proxy |
| A45 | Thay rule không có approval | CI/admission guardrail phát hiện | IaC diff |
| A46 | Rule hết review_due | Nhắc review/thu hồi theo quy trình | Rule registry |
| A47 | SIEM ingest/log collector mất dữ liệu | Có telemetry-loss alert | Collector health |
| A48 | Production DR region failover | Security parity cho allow/deny | DR positive + negative evidence |

### 30.1. Khi nào đánh dấu PASS?

Không đánh dấu PASS khi:
- Chỉ có lệnh **curl thành công** nhưng chưa xác nhận đi qua đúng proxy.
- DNS resolve nhưng HTTPS không có TCP/TLS validation.
- Firewall policy có rule nhưng CNI không enforce.
- Request bị app trả 403 nhưng không biết proxy có allow domain sai không.
- Kết nối bị timeout vì lab server không chạy, thay vì thực sự bị policy deny.
- Chỉ kiểm tra IPv4 trong hệ thống dual-stack.
- Chỉ quan sát một DNS answer trong khi CDN có nhiều IPs.

Một **deny test** nên có bằng chứng tại **enforcement point**, không chỉ client timeout. Timeout còn có thể do hạ tầng lỗi. Với DLP, cần evidence về policy category/action và đúng xử lý dữ liệu giả.

## 31. Công cụ chỉ đọc và quan sát an toàn

Các lệnh sau **không thay firewall hoặc DNS policy**. Chỉ dùng trong lab/cluster được cấp quyền, tránh chia sẻ private topology, credentials hay nội dung request nhạy cảm.

### 31.1. Kiểm tra Kubernetes policies

~~~bash
# Chỉ đọc namespace và labels
kubectl get namespaces --show-labels

# Liệt kê NetworkPolicies của workload lab
kubectl get networkpolicies -n orders-prod

# Đọc policy để đối chiếu selector và union semantics
kubectl describe networkpolicy default-deny-egress -n orders-prod

# Đọc Pod labels và nơi Pod chạy
kubectl get pods -n orders-prod -o wide --show-labels
~~~

Không suy **policy đã được enforce** chỉ từ đối tượng API; cần CNI/runtime verdict.

### 31.2. Quan sát DNS trong Pod có công cụ được cấp quyền

~~~bash
# Chỉ dùng Pod lab có sẵn nslookup, không cài tool vào production image
kubectl exec -n orders-prod orders-api-lab-0 -- \
  nslookup api.billing.example

# Kiểm tra resolver configuration từ process nếu quyền cho phép
kubectl exec -n orders-prod orders-api-lab-0 -- \
  cat /etc/resolv.conf
~~~

Domain giả định có thể không tồn tại. DNS success **không chứng minh kết nối** và Pod test phải khớp selector/identity của workload được nghiệm thu.

### 31.3. Request HTTPS nhỏ tới endpoint lab được phép

~~~bash
# Endpoint placeholder: thay bằng HTTPS service do bạn sở hữu trong lab
curl --silent --show-error --max-time 5 \
  -I https://api.lab.example/
~~~

Lệnh minh họa: nếu hostname không tồn tại thì việc thất bại không cung cấp kết luận security. Không dùng --insecure để bỏ TLS verification. Khi test proxy, cần chứng minh connection thực sự đi qua authenticated proxy bằng **proxy logs và policy version**, không chỉ biến môi trường.

### 31.4. Quan sát Linux route (không thay đổi)

~~~bash
ip -4 route show
ip -6 route show
ip rule show
~~~

Các lệnh chỉ phản ánh **host network namespace** nơi chúng chạy, không phải toàn bộ cloud transit path. Trong container, kết quả phản ánh Pod/container namespace theo cấu hình. Không dùng route output đơn độc để kết luận traffic đã đi qua firewall.

### 31.5. Phân loại HTTP/TLS lỗi

| Quan sát | Diễn giải có thể | Bước tiếp theo |
|---|---|---|
| DNS NXDOMAIN | Tên sai, không có record, policy DNS hoặc split horizon | DNS responder/source |
| Proxy 403 | Deny domain/source/path hoặc auth | Proxy policy audit |
| Upstream HTTP 403 | SaaS app không cho hành động | API token/resource scope |
| TLS certificate mismatch | Không đúng hostname/trust | DNS/SNI/cert chain |
| TCP timeout | Routing/firewall/NAT/target unavailable | Network hop/flow logs |
| Connection reset | Middlebox/server/MTU/state issue | Transport logs |
| HTTP 502/503 từ proxy | Upstream connect/TLS/health failure | Proxy reason/endpoint |
| 200 từ app | Network thành công cho một request | Vẫn phải test denied destinations |

## 32. Tình huống phân tích và đáp án gợi ý

### Tình huống A — Cho mọi TCP/443 rồi gọi là domain allowlist

Một đội triển khai 0.0.0.0/0:443 vì hầu hết API dùng HTTPS.

**Phân tích:** đó là port allowlist rất rộng, không phải domain allowlist. Chỉ cho đúng proxy từ workload, dùng authenticated hostname policy, TLS verification và network deny direct bypass.

### Tình huống B — SaaS dùng CDN IP thay đổi

Ứng dụng mất kết nối sau khi CDN đổi A records; firewall chỉ allow một IP cũ.

**Phân tích:** IP pinning thiếu phù hợp với dynamic SaaS. Dùng FQDN-aware proxy hoặc process cập nhật vendor IP list có kiểm chứng; không mở toàn CDN ranges tùy tiện.

### Tình huống C — Hai domains chung một IP

FQDN engine ánh xạ api.billing.example tới shared CDN IP, sau đó unapproved.example cũng dùng IP ấy.

**Phân tích:** DNS-to-IP allow có thể không phân biệt hostname trên kết nối. Cần engine kiểm tra CONNECT/SNI/verified server identity hoặc chấp nhận và bù rủi ro rõ; kiểm thử negative domain.

### Tình huống D — Proxy-only trên giấy

Ứng dụng có HTTPS_PROXY nhưng vẫn có VPC default route thẳng ra Internet.

**Phân tích:** client proxy config không cưỡng chế. CNI/host/cloud firewall cần chặn direct egress, chỉ cho authorized proxy và approved internal flows.

### Tình huống E — Wildcard cho mọi subdomain

Đội vận hành cho *.partner.example và sau đó một subdomain thử nghiệm bị tiếp quản.

**Phân tích:** wildcard có thể tăng bề mặt. Thu hẹp exact hosts, quản lý DNS ownership/stale CNAMEs, review wildcard semantics, không tin domain alone thay app auth.

### Tình huống F — Redirect sang hostname ngoài danh sách

Ứng dụng chỉ kiểm tra URL đầu tiên là api.billing.example, nhưng HTTP redirect sang host khác.

**Phân tích:** kiểm tra lại mỗi redirect và actual connect target; egress proxy/network deny phải chặn đích mới nếu không thuộc quyền.

### Tình huống G — DNS rebinding

Ứng dụng validate public hostname, DNS answer thay thành private lab address khi connect.

**Phân tích:** URL/hostname check riêng lẻ không đủ. Bind DNS resolution tới connected IP, chặn private/loopback/link-local ngoài quyền, giảm TOCTOU và audit.

### Tình huống H — DoH qua 443

DNS policy chặn UDP/53 tới Internet, nhưng app được HTTPS tới mọi địa chỉ và tự dùng DoH resolver.

**Phân tích:** DoH đi qua HTTPS, cần domain/IP proxy allowlist và control sanctioned resolvers; không chỉ dựa vào port 53.

### Tình huống I — ECH khiến SNI filtering không biết đích thật

Một firewall chỉ allow theo visible SNI, client dùng ECH.

**Phân tích:** phải xác định khả năng thực của engine; dùng authenticated forward proxy hoặc app destination controls, quy định fail mode và kiểm thử ECH-capable clients.

### Tình huống J — HTTPS tới đúng domain nhưng sai tenant

Một app có quyền upload tới storage provider domain, nhưng token cho phép ghi bucket ngoài mục đích.

**Phân tích:** domain allowlist không ngăn exfil tới approved SaaS. Resource IAM/tenant scopes, application DLP/authorization và audit là lớp bắt buộc.

### Tình huống K — Proxy ghi đầy đủ query strings

DLP proxy giải mã TLS và log full URL chứa signed link hoặc access token.

**Phân tích:** đây là data leakage qua telemetry. Redact tại nguồn, giới hạn logging, xem retention/replication, thu hồi token nếu cần và tăng kiểm thử privacy.

### Tình huống L — Node image pull không chạy

Namespace Pod egress đã có registry allow, nhưng node firewall chặn registry CDN.

**Phân tích:** kubelet/runtime pull image qua **node egress**, không nhất thiết qua Pod policies. Tách node/CI/app egress và cho đúng registry/mirror dependencies.

### Tình huống M — IPv6 bypass firewall IPv4

Firewall áp IPv4 deny; client có AAAA record và kết nối IPv6 thành công.

**Phân tích:** cần dual-stack network policy, ::/0 review, IPv6 SG/CNI/proxy và negative tests; IPv4-only result không đủ.

### Tình huống N — Proxy failover đổi public IP

API đối tác chỉ allow public IP của primary NAT nên standby bị từ chối dù rule domain đúng.

**Phân tích:** quản lý toàn bộ approved egress IPs, TLS client cert, HA routing và partner allowlist; DR test cả allowed và denied flows.

### Tình huống O — Cloud Private Endpoint bỏ qua DLP

Prod app gọi object storage qua private endpoint, không đi Internet firewall nơi đặt DLP.

**Phân tích:** private path là alternate route cần inventory. Dùng IAM/endpoint policy, data classification, cloud audit và DLP tại app/storage API nếu cần.

### Tình huống P — HTTP 403 không phải network deny

Proxy allow CONNECT và TLS thành công, nhưng partner API trả 403 do token hết hạn.

**Phân tích:** network/domain policy đang làm đúng vai trò. Kiểm tra token audience/scope/expiry, không mở firewall thêm chỉ vì HTTP 403.

### Tình huống Q — Allowlist stale không có owner

Một domain cũ vẫn được phép ở 70 workloads dù sản phẩm không còn sử dụng.

**Phân tích:** là security debt. Gắn owner/review_due, phân tích logs/traffic, sunset rule theo staged change, test negative deny sau thu hồi.

### Tình huống R — DLP chặn nhầm báo cáo hợp lệ

Một upload tới approved SaaS bị DLP đánh dấu confidential dù dữ liệu đã được phép chuyển.

**Phân tích:** cần review data classification, luật DLP và business authorization; exception hẹp được phê duyệt và có hạn, không tắt policy toàn domain.

## 33. Runbook khi phát hiện egress trái chính sách hoặc thất thoát dữ liệu

### Giai đoạn A — Xác minh

1. Ghi incident time, source workload/user/device, cluster/account/region và owner.
2. Xác định actual destination: FQDN, connected IP, protocol, port và route.
3. Thu DNS answer/cache state, proxy/firewall/CNI verdict và policy version.
4. Đối chiếu mTLS/client identity, SaaS token scope, endpoint/resource IAM.
5. Kiểm tra có **direct path, IPv6, QUIC, DoH, PrivateLink, VPN, hostNetwork** ngoài inventory không.
6. Xem DLP alerts, data classification, volume/bytes và app audit theo nguyên tắc tối thiểu dữ liệu.
7. Xác định tình trạng: policy bypass, false positive, business dependency thiếu, credential compromise hay suspected exfil.
8. Bảo toàn evidence và loại bỏ tokens/PII khỏi ticket/chat công khai.

### Giai đoạn B — Khoanh vùng

- **Domain/IP ngoài quyền:** chặn tại đúng enforcement point theo incident policy; không xóa mọi routes/SG.
- **Domain được phép nhưng exfil nghi vấn:** thu hẹp resource token/IAM, app upload permissions, SaaS tenant policy, DLP/quotas.
- **SSRF:** validate URLs/redirects, block private/link-local targets và kiểm tra egress proxy enforcement.
- **Proxy credential compromise:** revoke/rotate, giới hạn proxy access, xem usage/audit.
- **DNS/policy drift:** khôi phục approved version và chặn sửa trái quyền.
- **Proxy outage:** dùng HA/rollback được duyệt, không bật unrestricted direct Internet.
- **DLP false positive:** ngoại lệ có owner/scope/expiry và review evidence; vẫn giữ baseline.

### Giai đoạn C — Khôi phục và nghiệm thu

1. Khôi phục các **approved business flows** trong phạm vi cần thiết.
2. Chạy negative tests với unapproved domain/direct IP/IPv6/Dev→Prod.
3. Xác nhận server TLS identity và application authorization.
4. Xác minh DLP hoạt động trên synthetic payload như policy yêu cầu.
5. Kiểm tra proxy/NAT/capacity/route symmetry và DNS TTL behavior.
6. Kiểm tra telemetry coverage, log integrity, auth/audit decisions.
7. Đánh giá region/AZ standby và security parity.
8. Ghi risk acceptance và reviewer nếu vẫn còn exception tạm.

### Giai đoạn D — Hậu kiểm

- Root cause: DNS dynamic, wrong match, route bypass, IAM, proxy auth hoặc application bug?
- Tại sao rule không có owner hoặc reviewer?
- Hệ thống có quan sát được direct path và TLS/HTTP3/ECH behavior không?
- Có mất hoặc lộ dữ liệu không, ở phạm vi nào, ai cần thông báo?
- Negative tests nào đã thiếu? CI/admission nào không bắt được?
- Phải cập nhật domain inventory, IaC, DLP, runbook và SLO nào?
- Ai chịu trách nhiệm remediation và deadline review?

**Đóng incident dựa trên cả availability, policy enforcement, identity/authorization và DLP evidence**, không chỉ vì một domain đã được thêm vào deny list.

## 34. Những sai lầm thường gặp

1. **Coi allow TCP/443 ra Internet là exact domain allowlist.** Nó chỉ giới hạn port.
2. **Coi DNS filtering là firewall.** Direct IP/DoH có thể đi đường khác.
3. **Tin DNS answer tương đương xác thực server.** Phải kiểm tra TLS identity.
4. **Coi one-time DNS lookup là IP vĩnh viễn.** CDN/DNS thay đổi.
5. **Mở cả shared CDN IP range cho một SaaS.** Tăng access surface.
6. **Cho wildcard không review subdomain ownership.** Có thể có stale/takeover records.
7. **Không kiểm tra wildcard có match apex domain không.** Semantics vendor khác.
8. **Dùng substring match hostname.** Có thể khớp nhầm domain lạ.
9. **Bỏ qua IDN/punycode và hostname canonicalization.** So khớp sai.
10. **Quên redirect check.** URL đầu đúng nhưng đích sau sai.
11. **Không ràng buộc resolved IP với connected IP.** Có DNS rebinding/TOCTOU risk.
12. **Tin SNI một mình là danh tính đã xác minh.** Client có thể tự gửi giá trị đó.
13. **Bỏ qua SNI/Host/CONNECT target mismatch.** Domain-fronting risk.
14. **Coi ECH luôn lộ SNI thật.** Một số cấu hình có thể che.
15. **Chỉ kiểm tra TCP/443, bỏ UDP/443.** QUIC/HTTP3 có thể bypass.
16. **Coi DNS qua port 53 luôn là duy nhất.** DoH/DoT/custom resolver.
17. **Bỏ IPv6/AAAA records.** Tạo đường đi ngoài IPv4 controls.
18. **Đặt HTTPS_PROXY rồi coi đã cưỡng chế.** Direct route vẫn có thể tồn tại.
19. **Chỉ ghi proxy logs rồi kết luận không có bypass.** Cần flow evidence.
20. **Tạo NetworkPolicy chuẩn có trường FQDN.** Core API không có trường đó.
21. **Coi default-deny policy override mọi allow khác.** Core policies union allow.
22. **Quên DNS/NodeLocal DNSCache và ingress phía proxy.** Hợp lệ vẫn timeout.
23. **Coi hostNetwork/node egress giống Pod thường.** Enforcement khác nhau.
24. **Cho client tải package trong production không cần thiết.** Supply chain risk.
25. **Coi registry domain đã allow nghĩa image đáng tin.** Cần integrity checking.
26. **Tin private endpoint/VPN tự tạo least privilege.** Còn IAM/app auth.
27. **Không kiểm soát endpoint resource/bucket/tenant.** Approved domain vẫn có thể exfil.
28. **Coi domain allowlist tự là content DLP.** Không biết TLS payload.
29. **Bật TLS interception thiếu privacy/trust review.** Có thể lộ dữ liệu và phá mTLS.
30. **Coi HTTP 403 luôn là domain deny.** Có thể app/authZ trả 403.
31. **Chỉ test positive requests.** Không phát hiện allowlist quá rộng.
32. **Đánh giá timeout là policy deny thành công.** Server có thể chỉ đang down.
33. **Chỉ kiểm tra một CDN A record.** Có thể có nhiều IP/IPv6.
34. **Không kiểm tra standby/proxy failover.** Security parity có thể sai.
35. **Không biết NAT public IP thay đổi.** Partner allowlist lỗi.
36. **Log full Authorization/URL query.** Lộ secrets.
37. **Coi source NAT IP là user identity.** Cần workload/time correlation.
38. **Không giám sát telemetry loss.** Có thể mất chứng cứ.
39. **Không có expiry/owner cho exceptions.** Tồn tại quyền không dùng.
40. **Bỏ application/data auth vì thấy mTLS.** Quyền resource vẫn cần.
41. **Cho phép mọi Dev→Prod vì cùng private zone.** Segmentation bị phá.
42. **Mở cả firewall khi một dependency lỗi.** Blast radius tăng.
43. **Chỉ review YAML, không đo datapath.** CNI/vendor semantics có thể khác.
44. **Không đánh giá false positives của DLP.** Gây outage do chặn nhầm.
45. **Tin policy đã deploy thì luôn đúng sau upgrade.** DNS/TLS/mesh thay đổi.

## 35. Checklist triển khai domain và destination allowlist

- [ ] Có sơ đồ outbound paths và security enforcement points.
- [ ] Có inventory source workloads/users/devices và owners.
- [ ] Mỗi rule gắn purpose, data classification, environment và reviewer.
- [ ] Có default-deny ở CNI/firewall/proxy phù hợp.
- [ ] Đã inventory mọi allow policy khác và union/priority semantics.
- [ ] Mỗi destination dùng exact FQDN/IP/service identity khi khả thi.
- [ ] Không có 0.0.0.0/0:443 hoặc ::/0:443 ngoài exception có approval.
- [ ] Wildcards, suffix matching và apex semantics đã được kiểm tra.
- [ ] Domain ownership, DNS records, stale CNAME và takeover risk được review.
- [ ] IDN/punycode, case, trailing dot và hostname parser được kiểm thử.
- [ ] Có A/AAAA/CNAME, TTL/cache và DNS change plan.
- [ ] Domain-to-IP mapping không mở shared CDN domain khác ngoài ý định.
- [ ] Client TLS hostname/certificate verification không bị tắt.
- [ ] SNI/Host/CONNECT consistency được xem xét theo proxy capability.
- [ ] ECH/HTTP3/QUIC/UDP visibility và fail mode được xác định.
- [ ] DNS resolver được duyệt, có logging phù hợp.
- [ ] DoH/DoT/custom resolver không tạo đường ngoài policy.
- [ ] Direct IP, redirect và DNS rebinding/SSRF cases được thử trong lab.
- [ ] Proxy có client authentication và identity đủ chi tiết.
- [ ] Direct Internet bypass proxy bị chặn tại network layer.
- [ ] App authorization, token scopes và tenant restrictions độc lập với allowlist.
- [ ] DLP có data classification, visibility và privacy governance.
- [ ] DLP false positives có quy trình appeal/exception.
- [ ] Sensitive-data egress được giới hạn volume/quotas khi phù hợp.
- [ ] Node/CI image pulls được quản trị riêng Pod egress.
- [ ] Private endpoints, VPN, peering và hybrid routes được inventory.
- [ ] Cloud IAM/resource/endpoint policies đáp ứng least privilege.
- [ ] IPv4/IPv6 policies và return path đều được kiểm chứng.
- [ ] HA/DR egress IPs và proxy policies có parity.
- [ ] Proxy/NAT capacity, latency và TLS failures được giám sát.
- [ ] DNS/CNI/proxy/cloud logs có policy version và source correlation.
- [ ] Logs được redacted; không chứa token, key hoặc raw sensitive payload.
- [ ] Có alerts unexpected egress, wildcard growth, DLP anomalies và log loss.
- [ ] Policy-as-code có lint, diff, approvals và rollback.
- [ ] Exceptions có owner, review_due và thu hồi tự động/theo quy trình.
- [ ] Có positive tests cho tất cả required domains.
- [ ] Có negative tests cho unknown domain, direct IP và source ngoài quyền.
- [ ] Có test redirects, TLS validation, DNS TTL, IPv6/QUIC.
- [ ] Có test approved SaaS nhưng resource/tenant trái quyền.
- [ ] Có test log redaction bằng synthetic data.
- [ ] Có kiểm thử failover vẫn deny các destinations không được phép.
- [ ] Runbook xác định rõ network vs DNS vs TLS vs proxy vs app vs DLP failures.
- [ ] Đã review quyền sửa DNS, NetworkPolicy, proxy, firewall, routes và IAM.
- [ ] Không coi domain allowlist là bảo vệ dữ liệu hoàn chỉnh.

## 36. Thuật ngữ tham khảo nhanh

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Egress** | Lưu lượng khởi tạo đi ra từ workload/miền bảo vệ |
| **Allowlist** | Tập các nguồn/đích/hành động được duyệt theo điều kiện |
| **Default-deny** | Không được cấp rõ thì bị từ chối ở enforcement point |
| **Domain/FQDN** | Tên DNS đầy đủ, có thể ánh xạ nhiều IP |
| **A/AAAA** | DNS records ánh xạ tên tới IPv4/IPv6 |
| **CNAME** | Bí danh DNS tới tên khác |
| **TTL** | Thời hạn cache DNS theo record và resolver behavior |
| **CIDR** | Dải địa chỉ IP dùng cho policy/routing |
| **SNI** | Server Name Indication trong TLS ClientHello khi có |
| **ECH** | Encrypted ClientHello, che một số thông tin ClientHello |
| **HTTP authority** | Tên authority đích HTTP, ví dụ Host hoặc :authority |
| **HTTP CONNECT** | Cơ chế proxy tạo tunnel tới host:port |
| **QUIC/HTTP3** | Giao thức thường dùng UDP/443, khác TCP/HTTPS thông thường |
| **DoH/DoT** | DNS over HTTPS/TLS |
| **DNS rebinding** | Thay đổi resolution có thể vượt URL/network trust boundary |
| **SSRF** | Server-Side Request Forgery, app bị điều khiển gọi đích ngoài ý định |
| **NAT/SNAT** | Chuyển đổi địa chỉ/port, có thể che source workload ở hop sau |
| **FQDN-aware policy** | Rule dựa vào domain với implementation-specific DNS/SNI/proxy semantics |
| **Egress gateway** | Điểm tập trung kiểm soát outbound traffic |
| **DLP** | Data Loss Prevention, kiểm soát dữ liệu nhạy cảm đi ra |
| **SWG/SSE/CASB** | Các lớp bảo mật web/SaaS theo kiến trúc và sản phẩm |
| **Private endpoint** | Đường dịch vụ riêng trong mạng/cloud, vẫn cần IAM |
| **Policy drift** | Cấu hình thực khác baseline được phê duyệt |
| **Positive/negative test** | Thử luồng được phép / không được phép |
| **TLS hostname verification** | Kiểm tra certificate server khớp hostname dự kiến |

## 37. Tổng kết

**Allowlist domain và destination** là nền tảng của kiến trúc egress bảo vệ hệ thống khỏi kết nối tùy ý: thay vì tin rằng mọi HTTPS/443 đều an toàn, ta xác định **source workload nào được phép tới đúng domain/IP/endpoint nào, qua giao thức và cổng nào, tại enforcement point nào, với identity và mục đích gì**. Đây là quyết định mạng và danh tính có thể đo kiểm, không chỉ là danh sách tên miền.

Một thiết kế thực tế phải hiểu **DNS/FQDN khác destination IP**, **SNI/HTTP Host khác verified TLS server identity**, **proxy khác firewall**, và **domain allowlist khác DLP**. Các tình huống **CDN/shared IP, wildcard, CNAME, TTL/cache, DNS rebinding, redirects, SSRF, DoH/DoT, ECH, QUIC/IPv6, private endpoints và NAT** có thể làm chính sách hoạt động khác mong đợi nếu không kiểm chứng.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, lựa chọn bền vững là kết hợp **default-deny ở network/CNI, authenticated proxy hoặc FQDN-aware engine đúng tính năng, TLS/application authorization, data classification/DLP, cloud IAM, logging đa lớp và policy-as-code có owner/expiry**. Thành công cần được chứng minh bằng **positive tests cho luồng nghiệp vụ, negative tests cho những đường ngoài quyền, security parity khi failover và khả năng phát hiện telemetry loss**. Khi đó, allowlist mới thực sự giảm nguy cơ lateral movement và data exfiltration mà vẫn giữ khả năng hoạt động của ứng dụng.
