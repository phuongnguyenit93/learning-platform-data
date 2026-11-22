# Dependency protection, SSRF defense và egress control

## 1. Vì sao outbound dependency là một trust boundary?

API không chỉ nhận request từ client; nó còn chủ động gọi các hệ thống khác để lấy dữ liệu, xác minh token, gửi webhook, tải ảnh, xử lý URL import, gọi payment provider hoặc truy cập object storage. Mỗi outbound request tạo ra một trust boundary mới: destination có thể không đáng tin, dữ liệu trả về có thể độc hại và kết nối có thể bị lợi dụng để đi tới tài nguyên nội bộ.

Server-Side Request Forgery (SSRF) xảy ra khi attacker khiến server gửi request tới một destination mà attacker không được phép truy cập trực tiếp. Server thường có network access rộng hơn browser hoặc client bên ngoài, nên SSRF có thể biến API thành điểm pivot để truy cập:

- Cloud metadata service và credential của workload.
- Loopback, private network, Kubernetes service, database admin endpoint.
- Internal control plane, monitoring, debug hoặc management API.
- Service khác trong cùng VPC/VNet hoặc cluster.
- Endpoint chỉ có thể truy cập từ egress IP được tin cậy.
- Dịch vụ bên thứ ba có quyền hoặc dữ liệu mà server đang giữ.

SSRF không chỉ là lỗi kiểm tra URL. Một URL có vẻ hợp lệ vẫn có thể resolve sang IP nội bộ; redirect có thể chuyển sang destination bị cấm; DNS có thể thay đổi giữa lúc kiểm tra và kết nối; proxy có thể resolve hostname theo cách khác; response có thể làm parser tiêu tốn tài nguyên hoặc lộ dữ liệu.

Trong phạm vi **SECURITY_API_SECURITY**, dependency protection phải kết hợp validation ở application, kiểm soát DNS và kết nối, network egress policy, credential isolation, giới hạn response và giám sát. Mục tiêu là chỉ cho service gọi đúng dependency cần thiết, với quyền tối thiểu và khả năng kiểm chứng được.

Sau bài học này, người học có thể:

1. Nhận diện SSRF trong URL import, webhook, image fetch, document preview và các outbound integration.
2. Xác thực destination theo scheme, hostname, port và IP thực tế.
3. Ngăn DNS rebinding, redirect bypass và proxy confusion.
4. Thiết kế egress allowlist ở application, proxy, service mesh và network layer.
5. Bảo vệ cloud metadata, internal service và workload credential.
6. Cấu hình HTTP client trong Spring để giới hạn redirect, timeout, body và parser.
7. Tách credential của từng dependency và không gửi nhầm secret.
8. Kiểm thử SSRF theo cả IPv4, IPv6, DNS, redirect, proxy và network path.

## 2. Threat model cho outbound request

Trước khi chọn biện pháp, xác định ai điều khiển destination và server có thể truy cập những gì.

| Luồng | Input do ai kiểm soát? | Rủi ro chính |
|---|---|---|
| Import từ URL | User hoặc tenant | SSRF tới internal/cloud metadata |
| Fetch avatar/preview | User profile hoặc content | SSRF, response parser abuse |
| Webhook delivery | Tenant cấu hình callback URL | Egress tới internal host, credential leak |
| OAuth/JWKS discovery | Issuer/configuration | Trusting attacker-controlled issuer/JWKS URL |
| PDF/document conversion | User gửi URL hoặc file reference | SSRF từ converter/renderer |
| URL unfurl/link preview | User gửi link | Redirect, DNS rebinding, internal access |
| Third-party API client | Application configuration | Dependency compromise, credential exfiltration |
| Service-to-service | Workload identity | Lateral movement và excessive trust |

### 2.1. Các câu hỏi phải trả lời

- Destination có được user/tenant cung cấp không?
- Hostname, scheme, port, path hoặc redirect có thể bị caller kiểm soát không?
- Service chạy ở network nào và có route tới subnet nào?
- HTTP client có dùng proxy hoặc DNS resolver riêng không?
- Request có mang cookie, Authorization header, client certificate hoặc cloud credential không?
- Response được parse bằng thư viện nào và giới hạn ra sao?
- Destination có thể trả redirect, compressed body hoặc nội dung parser phức tạp không?
- Có cách nào gọi thẳng dependency mà bỏ qua egress gateway không?

### 2.2. SSRF có thể là blind SSRF

Attacker không cần đọc response để khai thác. Chỉ cần server tạo outbound connection là có thể:

- Gửi request tới endpoint nội bộ gây side effect.
- Kích hoạt callback hoặc scan port thông qua timing.
- Gửi DNS query tới domain do attacker kiểm soát.
- Gọi metadata endpoint và làm lộ credential qua một kênh khác.
- Tạo request tới dịch vụ có trust theo source network.

Vì vậy, chỉ kiểm tra response body hoặc chỉ chặn việc trả nội dung về client không ngăn được SSRF.

## 3. Reference architecture cho outbound dependency

Một luồng outbound an toàn có nhiều lớp. Application hiểu business intent và destination policy; egress layer kiểm tra network destination tại thời điểm kết nối; response được giới hạn trước khi đưa vào parser.

```mermaid
flowchart TD
    A["Inbound API request"] --> B["Authenticate caller"]
    B --> C["Authorize action and tenant"]
    C --> D["Resolve business destination policy"]
    D --> E["Parse and canonicalize URL"]
    E --> F["Scheme / host / port allowlist"]
    F --> G["Resolve DNS and classify all IPs"]
    G --> H["Egress proxy / controlled connector"]
    H --> I["Network egress firewall"]
    I --> J["Approved external dependency"]
    J --> K["Bounded response reader"]
    K --> L["Content-type and parser limits"]
    L --> M["Validated business result"]
    G -->|Denied| N["Reject and audit"]
    I -->|Denied| N
```

Các lớp không thay thế nhau:

- Application validation hiểu endpoint nào được phép gọi theo nghiệp vụ.
- DNS/IP policy kiểm tra destination thực tế.
- Egress proxy/firewall hạn chế đường mạng ngay cả khi application có lỗi.
- HTTP client giới hạn redirect, timeout, connection pool và response.
- Parser sandbox/limits giảm rủi ro từ nội dung trả về.

Nếu chỉ có URL regex ở controller, SSRF vẫn có thể xảy ra qua redirect, DNS rebinding hoặc client behavior khác.

## 4. Thiết kế destination policy theo nghiệp vụ

Tốt nhất là application không nhận một URL tùy ý nếu nghiệp vụ chỉ cần một loại dependency đã biết.

Ví dụ, thay vì cho client gửi URL payment provider, client gửi `providerCode`; server map providerCode sang endpoint cố định trong configuration. Thay vì cho user nhập URL JWKS, server lấy issuer từ danh sách identity provider được quản trị.

### 4.1. Ưu tiên destination identifier thay cho raw URL

Thiết kế API:

- Request nhận `sourceId`, `providerId` hoặc `integrationId`.
- Server tải destination đã đăng ký và được owner phê duyệt.
- Policy gắn với tenant, operation, scheme, hostname, port và credential.
- User chỉ được chọn integration thuộc tenant của mình.
- Thay đổi destination cần quyền quản trị và audit.

Cách này giảm đáng kể input attacker kiểm soát.

### 4.2. Khi nghiệp vụ buộc phải nhận URL

Ví dụ link preview hoặc import từ website công khai có thể cần URL do user cung cấp. Khi đó:

- Chỉ cho phép scheme cần thiết, thường là HTTPS.
- Chặn userinfo và URL syntax mơ hồ.
- Dùng parser chuẩn và một quy trình canonicalization duy nhất.
- Allowlist hostname/port nếu có thể.
- Kiểm tra DNS/IP ngay trước kết nối.
- Chặn redirect hoặc kiểm tra lại từng hop.
- Không forward credential/cookie của application.
- Gửi qua egress gateway có policy.
- Giới hạn thời gian, bytes, content type và parser.

Không xem URL đã qua validation là một capability vô hạn. Nó chỉ được phép cho một operation cụ thể và trong một giới hạn cụ thể.

### 4.3. Allowlist tốt hơn denylist

Denylist phải dự đoán mọi hostname/IP nội bộ, alias, encoding và protocol đặc biệt. Allowlist chỉ cho phép destination đã biết.

Nếu nghiệp vụ cần truy cập Internet rộng, vẫn phải có deny policy cho address space không được định tuyến công khai, metadata, loopback, link-local, private và các destination đặc biệt; đồng thời bắt buộc egress proxy/firewall. Với integration quan trọng, dùng allowlist domain chính xác.

## 5. Parse và canonicalize URL đúng cách

Không kiểm tra URL bằng regex đơn giản hoặc substring. URL parser và HTTP client có thể diễn giải authority khác nhau nếu input có encoding, userinfo, IPv6 literal hoặc ký tự phân cách bất thường.

### 5.1. Chỉ chấp nhận scheme cần thiết

Với HTTP fetch thông thường, chỉ cho phép `https`. Từ chối scheme không cần như:

- `file:`
- `ftp:`
- `gopher:`
- `jar:`
- `data:`
- `javascript:`
- `ldap:`
- `dict:`
- `smb:`

HTTP client của ứng dụng có thể không hỗ trợ một số scheme, nhưng parser, converter hoặc thư viện khác có thể hỗ trợ. Policy nên từ chối ngay ở boundary.

### 5.2. Reject URL có userinfo

Từ chối dạng `https://user:password@host.example/`. Userinfo có thể tạo ambiguity giữa parser, log và proxy; nó cũng có thể chứa secret không nên lưu hoặc forward.

Không dùng phần trước dấu `@` để xác định host. Dùng parser URI chuẩn và kiểm tra authority components.

### 5.3. Kiểm tra host và port tách biệt

- Host phải parse được và không rỗng.
- Port phải thuộc allowlist; nếu không chỉ định, áp dụng default port của scheme.
- Không chấp nhận port tùy ý chỉ vì scheme là HTTPS.
- Từ chối IPv6 zone identifier nếu nghiệp vụ không có use case rõ.
- Nếu chỉ cho phép hostname, từ chối IP literal.
- Không cho host có syntax mơ hồ hoặc parser không thể canonicalize an toàn.

### 5.4. Canonicalize hostname

Một quy trình có thể gồm:

1. Parse authority bằng URI parser chuẩn.
2. Lấy hostname đã tách khỏi userinfo/port.
3. Chuyển internationalized domain name sang ASCII bằng IDNA policy thống nhất.
4. Chuyển chữ thường.
5. Chuẩn hóa trailing dot theo policy.
6. So khớp allowlist trên hostname canonical.
7. Giữ một giá trị canonical duy nhất cho DNS, policy, logging và HTTP client.

Không decode `%2f`, `%40` hoặc ký tự authority bằng một helper tùy tiện rồi parse lại theo cách khác. Reject các dạng không chuẩn nếu các tầng không diễn giải thống nhất.

### 5.5. So khớp domain suffix đúng ranh giới

Nếu policy cho phép mọi subdomain của `example.com`, điều kiện phải là hostname bằng `example.com` hoặc kết thúc bằng `.example.com`. Không dùng `endsWith("example.com")` đơn thuần vì `evil-example.com` cũng có thể vượt qua.

Ngay cả suffix allowlist cũng cần cân nhắc ai có quyền tạo subdomain, CNAME và DNS record. Với destination nhạy cảm, allowlist exact hostname thường an toàn hơn.

### 5.6. Ví dụ validation cấu trúc URL trong Java

Đây là ví dụ minh họa lớp kiểm tra syntax và allowlist host. Nó chưa thay thế DNS/IP validation, connection pinning hoặc egress firewall:

```java
URI uri = URI.create(rawUrl);

if (!"https".equalsIgnoreCase(uri.getScheme())) {
    throw new IllegalArgumentException("Unsupported scheme");
}

if (uri.getRawUserInfo() != null || uri.getFragment() != null) {
    throw new IllegalArgumentException("Ambiguous URL components");
}

String host = uri.getHost();
if (host == null || host.isBlank()) {
    throw new IllegalArgumentException("Missing host");
}

String canonicalHost = IDN.toASCII(
    host,
    IDN.USE_STD3_ASCII_RULES
).toLowerCase(Locale.ROOT);

if (canonicalHost.endsWith(".")) {
    canonicalHost = canonicalHost.substring(
        0, canonicalHost.length() - 1
    );
}

int port = uri.getPort() == -1 ? 443 : uri.getPort();
if (port != 443 || !allowedHosts.contains(canonicalHost)) {
    throw new IllegalArgumentException("Destination not allowed");
}
```

Production code cần xử lý đúng IPv6 literal, IDN version/policy, malformed authority, default port, path/query và các khác biệt parser của HTTP client. Nếu URI parser không trả host rõ ràng, reject thay vì tự đoán.

## 6. DNS resolution và IP address validation

Allowlist hostname không đủ nếu hostname có thể resolve tới IP nội bộ. Attacker có thể kiểm soát DNS record hoặc domain được allowlist có subdomain do tenant quản lý.

### 6.1. Kiểm tra mọi A và AAAA record

Khi resolve hostname, kiểm tra tất cả địa chỉ IPv4 và IPv6 trả về:

- Nếu có bất kỳ địa chỉ không được phép, reject destination hoặc áp dụng policy rất rõ cho tập địa chỉ được chọn.
- Không chỉ kiểm tra record đầu tiên.
- Không bỏ qua AAAA vì IPv4 có vẻ an toàn.
- Không để Happy Eyeballs chọn một địa chỉ khác với địa chỉ đã kiểm tra.

Reject toàn bộ tập mixed public/private thường là policy dễ review và an toàn hơn.

### 6.2. Những nhóm địa chỉ cần chặn theo mặc định

Nếu service chỉ được gọi Internet công khai, chặn các nhóm đặc biệt như:

| Nhóm | Ví dụ | Lý do |
|---|---|---|
| Unspecified | `0.0.0.0`, `::` | Không phải public destination hợp lệ |
| Loopback | `127.0.0.0/8`, `::1` | Truy cập chính host/container |
| Private IPv4 | `10/8`, `172.16/12`, `192.168/16` | Internal network |
| Shared address space | `100.64.0.0/10` | Carrier-grade/shared network |
| Link-local | `169.254.0.0/16`, `fe80::/10` | Có thể tới metadata hoặc link-local service |
| Unique-local IPv6 | `fc00::/7` | Private IPv6 |
| Multicast | `224.0.0.0/4`, `ff00::/8` | Không phải unicast destination |
| Documentation/test ranges | Các dải IANA dành cho tài liệu/test | Không phải public production target |
| Reserved/future-use | Các dải reserved theo IANA | Không nên coi là Internet destination |
| IPv4-mapped IPv6 | `::ffff:127.0.0.1` | Có thể che giấu địa chỉ IPv4 nội bộ |

Danh sách này chỉ là ví dụ. Dùng IANA Special-Purpose Address Registries và policy mạng hiện tại để xây dựng classifier đầy đủ; không duy trì một regex hoặc danh sách viết tay thiếu cập nhật.

### 6.3. Java InetAddress flags không đủ

Các method như `isLoopbackAddress()`, `isSiteLocalAddress()` hoặc `isLinkLocalAddress()` hữu ích nhưng không phân loại đầy đủ mọi special-purpose range, shared address space, mapped IPv6 hoặc các dải đặc biệt theo môi trường cloud.

Dùng thư viện IP address parser/validator được duy trì hoặc egress policy ở lớp network. Việc parse IP phải chuẩn hóa IPv4/IPv6 và xử lý mapped address, zone identifier, unusual textual representation.

### 6.4. Xử lý CNAME và DNS chain

Hostname có thể là CNAME tới một hostname khác. Policy phải áp dụng trên địa chỉ cuối cùng mà socket thực sự kết nối, không chỉ record ban đầu.

Nếu dùng resolver riêng, kiểm tra kết quả cuối cùng của chain và tất cả A/AAAA record. Không cho CNAME chain chuyển sang destination ngoài policy.

### 6.5. Không chấp nhận mixed answer một cách vô thức

Một hostname có thể trả cả public IP và private IP. Nếu HTTP client tự chọn address theo thứ tự, family preference hoặc Happy Eyeballs, kiểm tra một record rồi kết nối record khác sẽ tạo bypass.

Policy mặc định nên reject nếu bất kỳ record nào thuộc dải cấm. Nếu có lý do nghiệp vụ chọn một address cụ thể, connection layer phải bị ràng buộc vào đúng address đã được policy duyệt.

## 7. DNS rebinding và time-of-check/time-of-use

DNS rebinding xảy ra khi hostname resolve thành địa chỉ public lúc kiểm tra nhưng trả về địa chỉ private khi HTTP client thực hiện kết nối. Đây là lỗi time-of-check/time-of-use (TOCTOU).

Luồng nguy hiểm:

1. Application kiểm tra `download.example` và thấy public IP.
2. TTL hết hoặc attacker thay DNS response.
3. HTTP client resolve lại cùng hostname.
4. DNS trả `127.0.0.1` hoặc private IP.
5. Server kết nối tới internal service.

### 7.1. Kiểm tra DNS một lần không đủ

Không thể bảo đảm an toàn nếu application kiểm tra DNS rồi để một HTTP client khác tự resolve lại không có ràng buộc. Cần đảm bảo IP được kiểm tra chính là IP dùng ở socket connection.

### 7.2. Connection pinning

Một mô hình an toàn:

- Resolve hostname bằng resolver được kiểm soát.
- Canonicalize và validate toàn bộ IP.
- Chọn một IP đã được phép.
- Kết nối socket tới đúng IP đó.
- Vẫn dùng hostname gốc cho TLS SNI và certificate hostname verification.
- Gửi Host header đúng hostname canonical.
- Không cho client tự resolve lại hoặc fallback sang IP chưa kiểm tra.

Connection pinning cần được triển khai ở DNS resolver/HTTP transport layer; không thay URL hostname thành IP một cách ngây thơ vì sẽ làm sai TLS hostname verification hoặc virtual hosting.

### 7.3. Egress proxy có thể thực hiện kiểm tra tại connect time

Một egress proxy chuyên dụng có thể nhận hostname, resolve, validate IP và tạo upstream connection theo một policy duy nhất. Proxy cần chặn private/special IP ở thời điểm kết nối và không cho client bypass bằng direct egress.

Đây thường là lựa chọn dễ quản trị hơn việc tự xây DNS pinning trong từng service.

### 7.4. DNS cache và TTL

Cache DNS giúp giảm latency nhưng không phải security control duy nhất. Cần biết resolver cache ở JVM, HTTP client, sidecar, proxy và operating system. TTL dài có thể giữ IP cũ; TTL ngắn không tự ngăn rebinding nếu connection layer resolve lại không kiểm tra.

## 8. Redirect là một SSRF bypass phổ biến

Một URL ban đầu có thể trỏ tới public host nhưng response trả `Location` tới loopback, private IP hoặc metadata endpoint.

Ví dụ:

```http
GET /preview HTTP/1.1
Host: public.example

HTTP/1.1 302 Found
Location: http://169.254.169.254/latest/meta-data/
```

Nếu HTTP client tự follow redirect, validation ban đầu không còn ý nghĩa.

### 8.1. Tắt auto-redirect cho URL do caller kiểm soát

Đối với fetcher có SSRF risk, mặc định không tự động follow redirect. Nếu nghiệp vụ cần redirect:

1. Đọc `Location`.
2. Resolve relative URI dựa trên URI hiện tại bằng parser chuẩn.
3. Parse/canonicalize lại URL mới.
4. Chạy lại scheme/host/port allowlist.
5. Resolve DNS và kiểm tra IP mới.
6. Áp dụng giới hạn redirect count nhỏ.
7. Chỉ sau đó mới tạo request tiếp theo.

### 8.2. Không forward credential qua redirect

Không mang Authorization header, Cookie, client certificate hoặc custom secret header sang destination khác. Redirect cross-origin phải được coi là một request mới với credential policy mới.

Với third-party dependency, credential nên gắn với exact destination và không được tự động kế thừa.

### 8.3. Redirect loop và method semantics

Giới hạn số hop, tổng deadline và tổng bytes qua tất cả hop. Hiểu semantics 301/302/303/307/308 đối với method/body; không để POST có side effect bị chuyển thành GET hoặc bị replay theo behavior không dự kiến.

## 9. Proxy, environment variable và route confusion

HTTP client có thể dùng proxy được cấu hình từ application, JVM hoặc environment. Proxy có thể resolve hostname ở phía proxy, vì vậy application-side DNS check có thể không tương ứng với IP thực tế.

Cần kiểm tra:

- `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` hoặc cấu hình tương đương có được dùng không.
- JVM system properties và HTTP client proxy selector.
- Proxy có tự resolve DNS và có destination policy không.
- Client có thể gửi absolute-form request hoặc override proxy không.
- `NO_PROXY` có wildcard/suffix behavior an toàn không.
- Internal service có bị bỏ qua egress proxy không.
- TLS CONNECT tunnel có được kiểm tra hostname/port/IP không.

Không tin `X-Forwarded-Host`, `Forwarded` hoặc header proxy do inbound client gửi để quyết định outbound destination. Trusted proxy metadata chỉ được chấp nhận từ proxy đã xác thực và được cấu hình rõ.

### 9.1. Direct egress bypass

Nếu network cho phép pod/container kết nối Internet trực tiếp, attacker có thể bỏ qua egress proxy bằng một code path hoặc thư viện khác. Dùng network policy/firewall để chỉ cho workload ra ngoài qua egress gateway cần thiết.

### 9.2. Proxy credential

Proxy authentication credential cũng là secret. Không đưa nó vào URL, exception message hoặc access log. Không để destination bên ngoài nhận proxy header hoặc proxy credential.

## 10. Chặn cloud metadata và internal control plane

Cloud metadata service thường cung cấp identity hoặc credential của workload. SSRF tới metadata có thể biến lỗi fetch URL thành compromise cloud account.

### 10.1. Cloud metadata

Các cloud environment có metadata endpoint riêng. Ví dụ nhiều nền tảng dùng địa chỉ link-local `169.254.169.254`; AWS IMDS, Azure IMDS và Google Cloud metadata có protocol/header behavior riêng. Một số nền tảng có địa chỉ hoặc hostname metadata khác.

Không chỉ chặn một URL cụ thể. Cần:

- Chặn link-local metadata IP ở egress network.
- Dùng metadata service mode bảo vệ phù hợp (ví dụ IMDSv2 khi chạy AWS).
- Giới hạn quyền IAM/workload identity tối thiểu.
- Không cho workload không cần metadata truy cập endpoint.
- Không expose metadata proxy cho container không tin cậy.
- Theo dõi request tới metadata destination.

IMDSv2 giảm một số kiểu SSRF đơn giản nhưng không thay thế egress restriction hoặc quyền IAM tối thiểu.

### 10.2. Kubernetes và platform endpoint

Chặn hoặc chỉ allowlist rõ:

- Kubernetes API server.
- Kubelet/read-only port hoặc node management.
- Internal DNS/admin endpoint.
- Service mesh admin/metrics endpoint.
- Container runtime socket proxy.
- Cloud control plane private endpoint.
- Database, cache và message broker management interface.

NetworkPolicy ở Kubernetes thường có semantics phụ thuộc CNI và không phải mọi môi trường đều enforce egress giống nhau. Xác minh bằng test network thực tế và kết hợp firewall/security group khi cần.

### 10.3. Không chỉ bảo vệ HTTP

Một số thư viện có thể mở socket TCP/UDP, dùng FTP, SMB hoặc protocol khác. Nếu attacker kiểm soát URL và parser, egress policy cần giới hạn protocol và port ở network layer, không chỉ HTTP scheme validation.

## 11. Network egress control

Egress control là lớp bảo vệ độc lập với application. Nó giới hạn workload có thể kết nối ra đâu, bằng protocol/port nào và qua điểm kiểm soát nào.

### 11.1. Default deny

Một baseline tốt:

- Deny outbound theo mặc định.
- Allow DNS tới resolver được chỉ định.
- Allow egress gateway/proxy cần thiết.
- Allow exact dependency hoặc destination group theo service.
- Chỉ mở port cần thiết.
- Không cho pod/container truy cập private network tùy ý.
- Quản lý exception có owner, reason và expiry.

Default deny phải được rollout có kiểm thử để không làm gián đoạn dependency hợp lệ hoặc DNS/time/identity service.

### 11.2. Network segmentation

Tách network theo workload và trust level:

- Public API ingress.
- Application service.
- Data tier.
- Management/control plane.
- Egress gateway.
- Third-party integration worker.

Một service chỉ cần gọi payment provider không nên có route tới database admin subnet hoặc metadata service. Segmentation làm giảm blast radius khi application validation có lỗi.

### 11.3. Egress proxy và firewall

Egress proxy có thể thực hiện:

- Destination hostname policy.
- DNS resolution và IP classification.
- Port/scheme restriction.
- Connection logging.
- TLS policy hoặc CONNECT control.
- Per-workload identity/quota.
- Deny metadata/private network.
- Centralized incident block.

Firewall/security group/network policy có thể enforce IP/port và chặn direct egress. Hai lớp kết hợp tốt hơn chỉ một proxy.

### 11.4. DNS policy không thay egress firewall

Chặn DNS query tới hostname nội bộ không ngăn được caller dùng IP literal, DNS-over-HTTPS hoặc resolver khác. Ngược lại, firewall chỉ chặn IP có thể khó quản lý các dependency dùng IP thay đổi.

Dùng DNS policy, egress proxy và network layer theo nhiều lớp; xác minh không có đường bypass.

### 11.5. FQDN allowlist và cloud IP range

Một số cloud provider thay đổi IP range. Không hardcode danh sách IP vĩnh viễn nếu provider công bố range động. Dùng egress proxy/domain policy, provider-managed prefix list hoặc automation cập nhật range đã xác minh.

Không cho phép toàn bộ cloud provider CIDR nếu chỉ cần một service cụ thể.

## 12. Bảo vệ dependency đã biết

Không phải mọi outbound request đều có input URL từ user. Dependency cố định vẫn cần bảo vệ vì DNS, TLS, credential, response và supply chain có thể bị compromise.

### 12.1. TLS verification

- Giữ certificate chain validation.
- Kiểm tra hostname.
- Không tắt hostname verification để “sửa lỗi certificate”.
- Dùng trust store được quản trị.
- Rotate CA/certificate theo kế hoạch.
- Với mTLS, cấp certificate riêng cho workload và scope.
- Không chấp nhận downgrade protocol/cipher ngoài policy.

### 12.2. Dependency identity

Dùng credential riêng cho từng dependency, không chia sẻ một API key rộng giữa nhiều provider. Ưu tiên workload identity hoặc short-lived credential khi hỗ trợ.

Mỗi outbound credential cần:

- Owner.
- Exact audience/destination.
- Scope tối thiểu.
- Expiry và rotation.
- Revoke mechanism.
- Usage monitoring.

### 12.3. Không gửi inbound identity sang third party

Không forward Authorization header, session cookie hoặc user token của inbound request sang third-party chỉ để tiện gọi. Nếu cần delegation, dùng token exchange hoặc credential được cấp đúng audience/scope.

Chỉ gửi dữ liệu user cần thiết cho operation. Không đưa tenant secret hoặc internal header vào outbound request.

### 12.4. Cookie jar và connection pool

Không dùng cookie jar dùng chung giữa user/tenant hoặc giữa dependency khác nhau. Tách connection pool theo trust boundary khi có credential hoặc TLS identity khác nhau. Không để cookie/Authorization header từ một request rò sang request khác.

## 13. Timeout, retry, circuit breaker và resource limits

Dependency có thể chậm, lỗi hoặc trả response rất lớn. Outbound call cần budget tài nguyên rõ ràng.

### 13.1. Timeout nhiều lớp

Cấu hình riêng:

- Connection pool acquisition timeout.
- DNS resolution timeout.
- TCP connect timeout.
- TLS handshake timeout.
- Response/header timeout.
- Read/idle timeout.
- Total request deadline.
- Parser/processing deadline.

Một read timeout không luôn đồng nghĩa tổng thời gian request bị giới hạn. Attacker có thể gửi từng byte nhỏ để kéo dài operation; cần total deadline.

### 13.2. Retry có kiểm soát

Retry có thể làm outage nặng hơn hoặc lặp side effect:

- Chỉ retry lỗi transient phù hợp.
- Dùng exponential backoff và jitter.
- Có retry budget/maximum attempts.
- Không retry 401/403/invalid destination.
- Không tự retry request có side effect nếu thiếu idempotency key.
- Không retry vô hạn khi dependency đang down.
- Tôn trọng `Retry-After` nếu contract yêu cầu.

### 13.3. Circuit breaker và bulkhead

Circuit breaker ngăn service tiếp tục gọi dependency đang lỗi. Bulkhead giới hạn số request đồng thời để một dependency không chiếm hết thread/connection pool.

Tách pool theo dependency và trust boundary. Không để một URL fetch do user điều khiển dùng chung pool với token introspection hoặc payment authorization.

### 13.4. Giới hạn response

Đặt giới hạn:

- Maximum response bytes thực tế đọc.
- Maximum decompressed bytes.
- Maximum header count/size.
- Maximum redirect hops.
- Maximum content length nếu khai báo, nhưng vẫn đếm bytes thật.
- Maximum JSON depth/array length/string length.
- Maximum XML entity/expansion (tắt external entities).
- Maximum archive entries/expansion ratio.
- Maximum image pixels/document pages.
- Maximum parser CPU/memory/time.

Không tải toàn bộ response vào byte array rồi mới kiểm tra size.

### 13.5. Content-Type không đủ tin cậy

`Content-Type` do server ngoài trả về có thể sai. Dùng allowlist media type, kiểm tra magic bytes/signature khi phù hợp và parse trong giới hạn. Không render HTML/SVG/Office/PDF trực tiếp ở context có quyền hoặc origin nhạy cảm mà không sandbox.

## 14. Webhook outbound và SSRF

Webhook thường cho tenant cấu hình callback URL. Đây là một nguồn SSRF phổ biến vì server gửi request tới destination do customer cung cấp.

### 14.1. Tách webhook dispatcher

Thiết kế một dispatcher riêng:

- Nhận webhook event nội bộ đã xác thực.
- Lookup endpoint đã được tenant đăng ký và verify.
- Áp dụng destination policy/egress gateway.
- Dùng signing secret riêng cho webhook.
- Không gửi application bearer token hoặc cloud credential.
- Giới hạn retry, timeout và payload.
- Lưu delivery attempt với status và request ID.

Không để mọi service tùy ý POST tới URL trong business object.

### 14.2. Verify endpoint ownership

Có thể yêu cầu endpoint verification challenge để chứng minh tenant kiểm soát destination. Tuy nhiên, challenge cũng là outbound request và phải đi qua SSRF validation. Không coi việc tenant sở hữu hostname là bằng chứng hostname an toàn về network.

### 14.3. DNS và redirect với webhook

Destination có thể đổi DNS sau khi verify hoặc redirect sang host khác. Mỗi delivery cần áp dụng policy tại thời điểm kết nối. Tắt redirect mặc định; nếu cho phép, validate lại từng hop.

### 14.4. Webhook response

Chỉ cần status/response metadata tối thiểu để xác định delivery. Không cần tải hoặc parse body tùy ý. Giới hạn response bytes và không dùng response body làm lệnh hoặc URL tiếp theo.

## 15. URL fetcher, image preview và document conversion

Các tính năng preview thường có nguy cơ SSRF vì nhận URL tùy ý và có thể chạy qua nhiều thư viện.

### 15.1. Image fetch

- Chỉ fetch HTTPS destination được phép.
- Chặn private/link-local/loopback và metadata.
- Giới hạn bytes, dimensions, frame count và decode time.
- Từ chối SVG hoặc xử lý trong sandbox vì SVG có thể tham chiếu external resource.
- Không để image decoder tải URL phụ mà bỏ qua egress policy.
- Xóa metadata không cần thiết khi re-encode.

### 15.2. Document/PDF conversion

Renderer có thể tải external image, font, stylesheet hoặc URL trong document. Một file có thể kích hoạt SSRF gián tiếp trong converter.

- Chạy converter trong isolated worker/container.
- Tắt network nếu không cần.
- Nếu cần network, dùng egress proxy policy riêng.
- Giới hạn CPU, memory, page count và execution time.
- Tắt external entity/remote resource loading theo thư viện.
- Không mount cloud credential hoặc service account token không cần thiết vào worker.

### 15.3. URL preview và HTML parsing

Không để HTML parser, browser automation hoặc headless renderer truy cập mọi URL phụ. Tắt JavaScript và external resource loading nếu không cần; nếu cần, mọi subresource request cũng phải qua egress policy.

## 16. OAuth, JWKS và callback destination

Các endpoint discovery như issuer metadata, JWKS URI, token endpoint và webhook callback là trust configuration.

### 16.1. Không nhận issuer tùy ý từ token

JWT `iss` là claim cần so sánh với issuer được tin cậy; không lấy giá trị `iss` từ token để tự động tải metadata/JWKS. Nếu làm vậy, attacker có thể điều khiển server gọi URL của họ hoặc internal service.

### 16.2. Allowlist identity provider

- Cấu hình issuer từ control plane hoặc allowlist đã quản trị.
- Ràng buộc issuer với audience và tenant.
- Fetch discovery/JWKS qua HTTP client có egress policy.
- Validate TLS và issuer metadata.
- Giới hạn response và refresh rate.
- Cache key theo issuer đã canonicalize.
- Unknown issuer phải thất bại an toàn.

### 16.3. Redirect và key rotation

JWKS endpoint hoặc metadata endpoint có thể redirect. Tắt redirect hoặc validate từng hop theo policy của issuer. Unknown `kid` có thể kích hoạt JWKS refresh; chống refresh storm và không cho `kid` điều khiển URL/path.

## 17. Bảo vệ response và chống data exfiltration

SSRF có thể dùng response từ internal service làm kênh exfiltration.

Cần kiểm soát:

- Chỉ trả dữ liệu cần thiết cho business operation.
- Không phản chiếu raw upstream body vào response public.
- Không trả internal IP, hostname, stack trace hoặc header nhạy cảm.
- Không lưu raw upstream response nếu không cần.
- Mask credential và query parameter nhạy cảm trong log.
- Không theo redirect sang destination ngoài policy.
- Không cho response điều khiển URL fetch tiếp theo mà không qua policy.
- Dùng schema validation trước khi dữ liệu upstream đi vào domain logic.

### 17.1. Error mapping

Phân biệt lỗi destination policy, DNS failure, connect timeout, TLS failure, upstream 4xx/5xx, body too large và parser error. Public response nên có error code ổn định nhưng không tiết lộ network topology.

### 17.2. DNS exfiltration và blind channel

Ngay cả khi response không được trả về client, request tới attacker-controlled DNS/domain có thể tạo side channel. Không cho user điều khiển hostname tùy ý trong những tính năng không cần Internet fetch. Theo dõi DNS query từ workload và egress destination lạ.

## 18. Spring Boot HTTP client hardening

Spring cung cấp `RestClient`, `WebClient` và các request factory/connector khác nhau. Security policy phải được áp dụng ở transport layer thực sự dùng, không chỉ ở wrapper service.

### 18.1. Dùng client riêng cho dependency

Tách client cho:

- Fixed first-party dependency.
- Third-party provider.
- User-supplied URL fetch.
- Webhook dispatcher.
- Identity/JWKS endpoint.

Mỗi client có destination policy, timeout, credential, pool, retry và logging riêng. URL fetcher do user điều khiển không dùng chung client có default Authorization header của internal service.

### 18.2. Ví dụ RestClient tắt redirect và đặt timeout

Ví dụ với Apache HttpClient 5 làm transport:

```java
CloseableHttpClient httpClient = HttpClients.custom()
    .disableRedirectHandling()
    .disableCookieManagement()
    .evictExpiredConnections()
    .build();

HttpComponentsClientHttpRequestFactory requestFactory =
    new HttpComponentsClientHttpRequestFactory(httpClient);

requestFactory.setConnectTimeout(Duration.ofSeconds(2));
requestFactory.setConnectionRequestTimeout(Duration.ofSeconds(1));

RestClient restClient = RestClient.builder()
    .requestFactory(requestFactory)
    .build();
```

Ví dụ này thể hiện redirect/cookie behavior và một số timeout. Cần cấu hình response/read/total deadline, response byte limit và TLS policy theo đúng phiên bản Apache HttpClient/Spring đang dùng. Đừng giả định connect timeout đã giới hạn toàn bộ request.

### 18.3. Ví dụ WebClient giới hạn thời gian và redirect

Với Reactor Netty, có thể tắt redirect và đặt connect/response timeout:

```java
HttpClient httpClient = HttpClient.create()
    .followRedirect(false)
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
    .responseTimeout(Duration.ofSeconds(5));

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
```

Đây chưa phải một SSRF-safe fetcher hoàn chỉnh. Cần thêm destination validation, DNS/IP policy tại connection layer hoặc egress proxy, total deadline, bounded body handling và parser limits.

### 18.4. Giới hạn response body theo bytes thực nhận

Với WebClient, tránh dùng `bodyToMono(byte[].class)` cho response không tin cậy nếu chưa có bounded reader. Dùng streaming `DataBuffer` và đếm tổng bytes; khi vượt limit, cancel subscription và release buffer đúng cách để tránh memory leak.

Không chỉ dựa vào `Content-Length`, vì response có thể không khai báo hoặc khai báo sai; compressed body có thể lớn hơn nhiều sau giải nén.

### 18.5. DNS resolver và connection pinning

Cấu hình HTTP client mặc định thường tự resolve hostname. Nếu application tự resolve và kiểm tra IP nhưng transport resolve lại, DNS rebinding vẫn có thể xảy ra.

Đưa DNS validation vào resolver/connector thực sự mở socket hoặc chuyển việc đó cho egress proxy. Giữ hostname gốc cho TLS hostname verification/SNI. Không thay host bằng IP trong URL rồi tắt certificate validation.

### 18.6. Proxy configuration

Cấu hình proxy rõ ràng trong application/connector. Không dựa vào environment variable ngoài kiểm soát mà không biết `NO_PROXY` hoặc bypass behavior. Egress network policy cần chặn direct route để mọi outbound request bắt buộc đi qua điểm kiểm soát.

## 19. Destination policy service trong application

Có thể xây một thành phần tập trung để các tính năng outbound dùng chung policy:

- `DestinationPolicy`: scheme, host, port, allowed path prefix, tenant/client, purpose.
- `UrlCanonicalizer`: parse và canonicalize URL.
- `DnsPolicyResolver`: resolve và classify IP.
- `OutboundRequestExecutor`: gọi qua connector đã pin/egress proxy.
- `ResponseLimiter`: byte/header/decompression limit.
- `AuditPublisher`: ghi decision và request reference.

Không để từng controller tự viết URL validation khác nhau.

### 19.1. Policy theo purpose

Cùng một hostname có thể được phép cho webhook nhưng không được phép cho identity discovery. Gắn policy với purpose và credential, không chỉ hostname.

Ví dụ:

| Purpose | Destination | Credential | Response |
|---|---|---|---|
| Payment API | Exact provider host | Provider-specific token | JSON schema nhỏ |
| JWKS | Trusted issuer JWKS | Không gửi user token | JWK set bounded |
| Webhook | Verified tenant endpoint | Webhook signature riêng | Status metadata |
| Link preview | Public HTTPS hosts theo policy | Không credential | HTML/image bounded |
| Internal service | Exact service identity/route | Workload identity | Contract nội bộ |

### 19.2. Tenant isolation

Tenant không được thay destination policy của tenant khác. Cache key phải bao gồm tenant/purpose khi policy khác nhau. Không dùng một global allowlist rộng nếu tenant có thể đăng ký endpoint tùy ý.

### 19.3. Fail closed

Nếu không thể xác minh URL, DNS, policy version hoặc egress identity, từ chối outbound call. Không fallback sang “bỏ qua validation” để tăng availability. Với dependency cố định, có thể có degraded mode chỉ đọc dữ liệu cache đã xác minh.

## 20. Logging, metrics và alerting cho egress

Telemetry phải giúp điều tra mà không biến log thành nơi chứa secret hoặc URL nhạy cảm.

### 20.1. Log decision

Ghi:

- Request/trace ID.
- Service và workload identity.
- Purpose và destination policy ID.
- Hostname canonical hoặc destination reference đã được mask theo policy.
- Scheme/port.
- Kết quả DNS/IP policy.
- Redirect count.
- Upstream status class.
- Bytes nhận được.
- Duration và timeout category.
- Policy decision allow/deny.
- Egress proxy/region.

Không ghi Authorization header, cookie, API key, signed URL đầy đủ, query parameter có secret hoặc response body raw. URL path/query có thể chứa PII và token; redact theo schema.

### 20.2. Metrics

Theo dõi:

- Outbound request count theo dependency/purpose.
- Destination denied.
- DNS answer chứa IP bị cấm.
- Redirect bị từ chối.
- Unknown host/port/scheme.
- Connect/TLS/response timeout.
- Response too large/parser limit.
- Egress proxy deny và direct-egress attempt.
- Bytes và duration theo dependency.
- Circuit breaker open/retry count.
- Metadata endpoint access attempt.
- JWKS/discovery refresh failure.

Dùng label cardinality thấp như service, purpose, dependency ID, decision và status class. Không dùng raw URL, tenant ID hoặc IP tùy ý làm metric label.

### 20.3. Alert

Alert ưu tiên cao khi:

- Workload cố kết nối metadata/private/loopback destination.
- Egress proxy phát hiện nhiều denied destination.
- Service bất ngờ tạo outbound tới hostname mới.
- Một endpoint URL fetch có tỷ lệ deny/redirect tăng.
- DNS answer của allowlisted hostname thay đổi sang special-purpose range.
- Direct egress xuất hiện ngoài baseline.
- Outbound credential bị dùng tới host không được phép.

## 21. Kiểm thử SSRF và egress policy

Test phải kiểm tra request có thực sự bị chặn trước khi kết nối và không chỉ kiểm tra response code.

### 21.1. URL parser/canonicalization

- Scheme không phải HTTPS.
- Userinfo có username/password.
- Host rỗng hoặc malformed.
- Port không được phép.
- IP literal IPv4/IPv6.
- Domain Unicode/IDN và trailing dot.
- Host suffix confusion như `trusted.example.attacker.test`.
- Encoded separator, backslash và authority ambiguity.
- IPv6 zone identifier.
- URL có fragment hoặc syntax không được hỗ trợ.
- Parser khác nhau giữa validator và HTTP client.

### 21.2. DNS/IP validation

- Host resolve tới loopback.
- Host resolve tới private IPv4.
- Host resolve tới link-local/metadata IP.
- Host resolve tới unique-local IPv6.
- Mixed public/private A/AAAA answers.
- CNAME chain tới private destination.
- IPv4-mapped IPv6.
- DNS response thay đổi giữa check và connect.
- DNS TTL hết hạn trong lúc request.
- Happy Eyeballs chọn address khác.
- DNS timeout hoặc resolver unavailable.

### 21.3. Redirect và proxy

- Public URL redirect tới loopback/private IP.
- Redirect tới metadata endpoint.
- Redirect qua nhiều hop hoặc loop.
- Relative redirect và scheme downgrade.
- Cross-origin redirect không được mang credential.
- Proxy resolve hostname thành IP khác.
- `NO_PROXY` bypass egress proxy.
- Direct egress không đi qua proxy.
- Proxy authentication không bị lộ.

### 21.4. Cloud/internal destination

- AWS/Azure/GCP metadata address/hostname theo môi trường.
- Kubernetes API/kubelet/internal DNS.
- Loopback service và private management port.
- Internal service có DNS name public-looking.
- Container không có quyền đọc cloud metadata hoặc service account token nếu không cần.
- Network firewall chặn egress dù application validation bị cố tình bypass trong test.

### 21.5. Response/resource limits

- Response không có Content-Length.
- Content-Length khai báo nhỏ hơn bytes thực.
- Compressed response expansion lớn.
- Header quá lớn hoặc quá nhiều.
- Slow response gửi từng byte.
- Redirect response body lớn.
- JSON/XML nesting quá sâu.
- HTML/SVG external resource.
- Image có pixel dimensions cực lớn.
- Archive có nhiều entry hoặc expansion ratio cao.
- Parser timeout và cancellation cleanup.

### 21.6. Dependency identity và credential

- Authorization header không được gửi tới URL fetcher.
- Credential của provider A không xuất hiện ở provider B.
- Cookie không chia sẻ giữa tenant.
- TLS certificate hostname mismatch bị từ chối.
- mTLS certificate đúng workload mới được dùng.
- Credential revoke/rotate được phản ánh ở outbound client.
- Log không chứa signed URL hoặc secret query parameter.

### 21.7. Test qua network thật

Unit test URL parser không chứng minh egress firewall hoạt động. Chạy integration test trong cùng network policy/container runtime hoặc môi trường staging tương đương production. Xác minh cả đường gateway, sidecar, proxy, DNS resolver và direct socket.

## 22. Những lỗi thiết kế thường gặp

1. **Dùng regex để validate URL.** Parser khác nhau có thể hiểu authority khác nhau.
2. **Chỉ allowlist hostname.** DNS có thể resolve tới private IP.
3. **Chỉ kiểm tra IPv4.** IPv6 hoặc mapped IPv6 có thể bypass.
4. **Chỉ kiểm tra record DNS đầu tiên.** HTTP client có thể chọn record khác.
5. **Resolve để kiểm tra rồi resolve lại khi connect.** Tạo DNS rebinding/TOCTOU.
6. **Tự động follow redirect.** URL public có thể redirect tới metadata/internal.
7. **Forward Authorization qua redirect.** Credential có thể rò sang host khác.
8. **Tin `NO_PROXY` hoặc environment proxy mặc định.** Có thể bypass egress gateway.
9. **Chỉ dùng denylist IP.** Bỏ sót alias, range đặc biệt hoặc destination mới.
10. **Chỉ dùng egress proxy nhưng vẫn cho direct egress.** Attacker có đường bypass.
11. **Chỉ dùng network firewall IP allowlist.** Khó quản lý hostname/provider range động nếu thiếu automation.
12. **Tắt TLS verification.** Cho phép dependency impersonation và MITM.
13. **Dùng HTTP client chung cho mọi dependency.** Cookie, credential, pool và policy bị trộn.
14. **Không giới hạn response bytes.** Upstream có thể làm cạn memory/disk.
15. **Chỉ tin Content-Length.** Chunked hoặc compressed response có thể vượt giới hạn.
16. **Parse HTML/PDF/SVG trong process chính.** External resource hoặc parser abuse có thể ảnh hưởng service.
17. **Cho webhook tenant tự gọi URL tùy ý.** Server trở thành SSRF proxy.
18. **Lấy JWKS URI từ token claim/header.** Token không tin cậy điều khiển outbound request.
19. **Log raw URL và query.** Có thể lộ signed URL, PII hoặc credential.
20. **Chỉ test application validation.** Không chứng minh DNS pinning hoặc network egress thực sự chặn.

## 23. Checklist triển khai dependency protection

Trước khi đưa outbound integration vào production, xác nhận:

- [ ] Có inventory dependency, purpose, owner và destination.
- [ ] Caller được authenticate và authorize trước khi tạo outbound request.
- [ ] Ưu tiên destination ID/configuration thay vì raw URL từ user.
- [ ] Chỉ cho phép scheme cần thiết, thường là HTTPS.
- [ ] URL được parse/canonicalize bằng một parser policy nhất quán.
- [ ] Userinfo, malformed authority và port ngoài allowlist bị từ chối.
- [ ] Host allowlist dùng exact match hoặc suffix boundary đúng.
- [ ] DNS kiểm tra tất cả A/AAAA và CNAME chain.
- [ ] Special-purpose/private/loopback/link-local/mapped IP bị chặn theo policy.
- [ ] DNS validation gắn với socket connection hoặc được egress proxy thực hiện tại connect time.
- [ ] TLS SNI và hostname verification vẫn dùng hostname gốc.
- [ ] Auto-redirect tắt; mỗi redirect hop được validate lại nếu được hỗ trợ.
- [ ] Credential/cookie không được forward sang destination khác.
- [ ] Cloud metadata và internal control plane bị chặn ở network layer.
- [ ] Egress default deny hoặc allowlist theo workload được áp dụng.
- [ ] Direct egress không thể bypass egress proxy.
- [ ] HTTP client có timeout, pool, retry và circuit breaker hợp lý.
- [ ] Response bytes/header/decompression/parser có giới hạn.
- [ ] Dependency credential riêng, scope tối thiểu, expiry và rotation.
- [ ] Webhook, preview và document conversion dùng isolated worker/dispatcher.
- [ ] JWKS/issuer destination đến từ trusted configuration.
- [ ] Log redact URL query, Authorization, cookie, API key và response body.
- [ ] Metrics/alerts có destination deny, metadata attempt và direct-egress signal.
- [ ] Test parser, DNS rebinding, IPv4/IPv6, redirect, proxy và cloud metadata.
- [ ] Test network policy thật, bao gồm direct socket và service mesh path.
- [ ] Incident runbook có bước revoke credential, block destination và preserve evidence.

## 24. Kết luận

Dependency protection bắt đầu từ việc coi mọi outbound destination và response là một trust boundary. SSRF không thể được ngăn chỉ bằng regex URL hoặc kiểm tra hostname: application phải canonicalize destination, kiểm tra scheme/host/port, xác thực DNS/IP và bảo đảm địa chỉ được kiểm tra chính là địa chỉ socket kết nối. Redirect, proxy, IPv6, CNAME và DNS rebinding đều phải nằm trong threat model.

Egress proxy, network firewall và workload segmentation tạo lớp bảo vệ độc lập nếu application có lỗi. Cloud metadata, loopback, private network và control plane cần bị chặn theo mặc định; dependency hợp lệ chỉ được cấp quyền outbound tối thiểu. HTTP client phải giới hạn redirect, timeout, retry, response bytes và parser; credential/cookie không được chia sẻ tùy tiện giữa destination.

Một kiến trúc tham chiếu tốt kết hợp destination policy theo purpose, DNS/connect-time enforcement, egress control, credential isolation, bounded response handling và telemetry. Kiểm thử phải chạy qua network path thực tế để chứng minh server không thể bị biến thành proxy truy cập tài nguyên nội bộ. Khi các lớp này hoạt động đồng bộ, API có thể tích hợp dependency cần thiết mà vẫn kiểm soát được destination, dữ liệu và blast radius.

