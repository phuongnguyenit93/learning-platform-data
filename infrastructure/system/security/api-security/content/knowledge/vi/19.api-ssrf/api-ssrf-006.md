# Egress network policy và timeout

## 1. Vì sao SSRF cần kiểm soát kết nối outbound?

Server-Side Request Forgery (SSRF) xảy ra khi API nhận dữ liệu do caller kiểm soát rồi dùng dữ liệu đó để tạo kết nối mạng từ phía server. Ví dụ, một endpoint nhận URL để tải ảnh, kiểm tra webhook, lấy nội dung tài liệu hoặc gọi một dịch vụ tích hợp. Nếu server có thể kết nối đến đích tùy ý, attacker có thể khiến nó truy cập hệ thống nội bộ, cổng quản trị, dịch vụ metadata của cloud hoặc tài nguyên chỉ có thể truy cập từ mạng server.

Một lớp kiểm tra URL trong ứng dụng là cần thiết, nhưng chưa đủ. Giữa lúc ứng dụng kiểm tra hostname và lúc socket thực sự kết nối có thể xuất hiện DNS rebinding, redirect hoặc thay đổi đường đi qua proxy. Một thư viện HTTP cũng có thể tự theo redirect, tái phân giải DNS hoặc sử dụng proxy được cấu hình ngoài dự kiến.

Vì vậy, phòng vệ SSRF cần nhiều lớp:

- Ứng dụng chỉ chấp nhận scheme, host, port và mục đích đã được cho phép.
- DNS và địa chỉ IP đích được kiểm tra theo chính sách.
- Egress proxy, firewall hoặc network policy giới hạn nơi workload có thể kết nối.
- Kết nối thực tế phải bị kiểm soát, kể cả sau redirect và DNS re-resolution.
- Timeout và giới hạn tài nguyên ngăn một request chiếm connection, thread hoặc bộ nhớ quá lâu.
- Log và monitoring giúp phát hiện request outbound bất thường.

Trong phạm vi **SECURITY_API_SECURITY**, kiểm soát outbound và timeout là lớp bảo vệ quan trọng cho endpoint có khả năng gọi URL, webhook, import dữ liệu hoặc tích hợp dịch vụ ngoài. HTTPS chỉ mã hóa kết nối; nó không ngăn server kết nối đến một địa chỉ nội bộ hoặc một endpoint không được phép.

Sau bài học này, người học có thể:

1. Thiết kế egress policy theo nguyên tắc default-deny.
2. Xây dựng allowlist theo hostname, protocol, port và mục đích nghiệp vụ.
3. Kiểm tra DNS A/AAAA và ngăn DNS rebinding.
4. Chặn redirect, proxy bypass và truy cập đến mạng nội bộ/metadata.
5. Áp dụng timeout theo từng pha và deadline tổng.
6. Cấu hình network policy, egress gateway và giới hạn connection pool.
7. Kiểm thử, giám sát và vận hành chính sách outbound an toàn.

## 2. Phân biệt kiểm tra URL và kiểm soát egress

Kiểm tra URL là quyết định ở tầng ứng dụng: URL có đúng format và nằm trong danh sách đích nghiệp vụ cho phép hay không. Egress control là quyết định ở tầng mạng: workload có thực sự được phép mở kết nối đến địa chỉ IP/port/protocol đó hay không.

Hai lớp này bổ sung cho nhau:

| Lớp | Câu hỏi | Ví dụ kiểm soát |
|---|---|---|
| URL validation | URL có đúng scheme, hostname và port? | Chỉ cho phép HTTPS tới api.partner.example |
| DNS validation | Hostname phân giải ra địa chỉ nào? | Từ chối địa chỉ loopback, private, link-local hoặc reserved |
| Connection enforcement | Socket thực tế kết nối đến IP nào? | Egress proxy/firewall kiểm tra destination IP |
| Network segmentation | Workload có thể tới mạng nào? | Chặn mặc định outbound, chỉ mở đích cần thiết |
| Timeout/resource control | Kết nối có thể giữ tài nguyên bao lâu? | Connect timeout, read timeout, total deadline |
| Authorization | Caller có được yêu cầu tích hợp này không? | Chỉ service có quyền webhook:deliver mới được gửi |

Một URL hợp lệ về cú pháp vẫn có thể trỏ đến địa chỉ nguy hiểm. Một hostname được allowlist vẫn có thể phân giải sang IP nội bộ. Một IP công khai vẫn có thể là dịch vụ không thuộc phạm vi nghiệp vụ. Vì vậy, không dùng một phép kiểm tra duy nhất thay cho toàn bộ chính sách.

### 2.1. Vì sao chỉ chặn private IP là chưa đủ?

Chặn private IP giúp giảm rủi ro truy cập RFC1918 hoặc loopback, nhưng chưa giải quyết hết SSRF:

- Một dịch vụ nội bộ có thể được công bố qua IP public.
- DNS có thể thay đổi sau khi ứng dụng kiểm tra.
- Redirect có thể chuyển sang host hoặc IP khác.
- Một proxy có thể phân giải hostname theo cách khác ứng dụng.
- Một endpoint công khai có thể kích hoạt hành động nhạy cảm hoặc tạo chi phí lớn.
- Các dải địa chỉ đặc biệt, IPv6 và địa chỉ metadata có thể bị bỏ sót.

Allowlist đích theo nghiệp vụ và enforcement ở tầng mạng thường đáng tin cậy hơn một danh sách deny IP đơn lẻ.

## 3. Nguyên tắc default-deny cho outbound

Mặc định, workload chỉ nên kết nối đến những đích cần thiết cho nhiệm vụ của nó. Không nên để mọi pod hoặc application server có quyền mở kết nối đến bất kỳ IP và port nào trên Internet hoặc mạng nội bộ.

Một chính sách egress tốt trả lời rõ:

- Workload nào được phép kết nối?
- Đích nào được phép: hostname, IP/CIDR, service identity hoặc destination group?
- Protocol và port nào được phép?
- Kết nối phục vụ nghiệp vụ gì?
- Có cần đi qua egress proxy/gateway không?
- Ai sở hữu policy và ai phê duyệt thay đổi?
- Cách ghi nhận và cảnh báo khi policy bị từ chối?

### 3.1. Chia workload theo nhu cầu outbound

Không nên áp dụng một policy outbound rộng cho toàn bộ hệ thống. Ví dụ:

| Workload | Đích cần thiết | Quyền outbound tham khảo |
|---|---|---|
| order-api | Database, message broker, internal inventory service | Chỉ CIDR/service và port nội bộ được chỉ định |
| image-fetcher | Một số CDN hoặc image provider đã phê duyệt | HTTPS qua egress proxy, hostname allowlist |
| webhook-delivery | Endpoint webhook của khách hàng | HTTPS qua proxy có SSRF enforcement |
| report-worker | Object storage và reporting service | HTTPS tới endpoint storage/service cụ thể |
| admin-api | Identity provider và audit service | Chỉ các dịch vụ quản trị cần thiết |

Một workload không cần outbound Internet thì nên bị chặn Internet. Nếu service cần gọi một API đối tác, chỉ mở đích đó thay vì mở toàn bộ port 443 đến mọi địa chỉ.

### 3.2. Phân tách môi trường

Development, staging và production cần policy khác nhau. Không để workload production dùng chung quyền outbound rộng được tạo cho môi trường thử nghiệm.

- Production chỉ kết nối đến endpoint production đã phê duyệt.
- Staging dùng credential và destination riêng.
- Development không được mặc định truy cập mạng nội bộ production.
- Test runner cần network sandbox riêng.
- Thay đổi policy cần review và audit.

### 3.3. Không dùng DNS name tự khai làm network identity

Tên service hoặc hostname trong request không chứng minh đích thực tế. Network policy thường cần kiểm soát theo IP/CIDR, service identity hoặc FQDN capability của nền tảng. Ứng dụng phải xác minh hostname; tầng egress phải kiểm soát địa chỉ mà kết nối thực sự đi tới.

## 4. Xây dựng destination allowlist

Với chức năng cần gọi dịch vụ ngoài, allowlist nên thể hiện đích nghiệp vụ cụ thể.

Ví dụ:

| Trường | Chính sách |
|---|---|
| Scheme | Chỉ HTTPS |
| Host | api.partner.example |
| Port | 443 |
| Path | Chỉ nhóm endpoint cần thiết nếu ứng dụng có thể kiểm soát |
| Redirect | Tắt mặc định hoặc kiểm tra lại từng hop |
| DNS result | Chỉ địa chỉ được policy cho phép |
| TLS | Xác minh certificate và hostname |
| Timeout | Deadline tổng và timeout theo pha |
| Response | Giới hạn kích thước và content type |

### 4.1. Ưu tiên hostname chính xác

Allowlist nên dùng hostname đầy đủ như api.partner.example. Nếu cần cho phép nhiều subdomain, quy tắc suffix phải kiểm tra ranh giới domain, ví dụ chỉ cho phép hostname kết thúc bằng .partner.example sau khi canonicalize đúng.

Không dùng kiểm tra chuỗi đơn giản như host.endsWith("partner.example") mà không kiểm tra boundary; chuỗi evilpartner.example có thể bị chấp nhận nhầm. Cũng không dùng wildcard rộng như *.example.com nếu không kiểm soát được toàn bộ subdomain và bên có quyền tạo DNS record.

### 4.2. Canonicalize hostname trước khi so sánh

Hostname cần được parse bằng URL/URI parser chuẩn và chuẩn hóa theo quy tắc IDNA/DNS trước khi so sánh allowlist. Cần xác định cách xử lý:

- Chữ hoa/chữ thường.
- Dấu chấm cuối hostname.
- Internationalized domain name và punycode.
- IPv4/IPv6 literal.
- User information trong URL.
- Port mặc định và port được ghi rõ.
- Ký tự percent-encoded hoặc dạng biểu diễn bất thường.

Từ chối URL có userinfo nếu không có nghiệp vụ cần thiết. Không cho caller tự điều khiển Host header hoặc TLS SNI khác với hostname đã được kiểm tra.

### 4.3. Giới hạn scheme và port

Chỉ hỗ trợ các scheme cần thiết, thường là HTTPS cho tích hợp bên ngoài. Không cho URL parser hoặc HTTP client tự mở rộng sang file:, ftp:, gopher:, jar:, data: hoặc protocol không thuộc contract.

Port cũng cần allowlist. Chỉ cho phép port 443 nếu dịch vụ đối tác sử dụng HTTPS chuẩn; nếu đối tác có port riêng, ghi rõ port đó trong policy và phê duyệt. Không cho caller chọn port tùy ý vì có thể dò cổng quản trị hoặc dịch vụ nội bộ.

### 4.4. Allowlist phải gắn với chức năng

Không nên tạo một allowlist global mà mọi endpoint đều dùng. Ví dụ, tính năng tải avatar có thể chỉ cần CDN ảnh; tính năng kiểm tra webhook cần endpoint do tenant đăng ký; tính năng import có thể chỉ được đọc từ object storage.

Gắn policy với operation giúp giảm quyền outbound của từng luồng và dễ điều tra khi một tính năng bị lạm dụng.

## 5. DNS resolution và kiểm tra địa chỉ IP

Hostname có thể phân giải thành một hoặc nhiều địa chỉ. Kiểm tra DNS là bước cần thiết khi URL do caller cung cấp hoặc khi destination policy dựa trên hostname.

### 5.1. Kiểm tra toàn bộ A và AAAA record

Một hostname có thể trả về nhiều IPv4 (A) và IPv6 (AAAA) address. Không chỉ kiểm tra địa chỉ đầu tiên rồi cho phép kết nối. Cần kiểm tra tất cả địa chỉ mà resolver trả về và xác định policy khi có bất kỳ địa chỉ không được phép nào.

Ví dụ, nếu một hostname trả về một IP public và một IP private, client có thể chọn địa chỉ private tùy thứ tự hoặc chiến lược fallback. Chính sách chặt thường từ chối hostname có bất kỳ kết quả không được phép nào, hoặc dùng một proxy có khả năng kiểm tra và chọn destination an toàn.

### 5.2. Chặn các dải địa chỉ không phù hợp

Với endpoint fetch URL công khai, thường phải từ chối ít nhất:

- IPv4 loopback, ví dụ 127.0.0.0/8.
- IPv4 private RFC1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16.
- IPv4 link-local, ví dụ 169.254.0.0/16.
- IPv4 unspecified, multicast, broadcast và các dải special-purpose/reserved không được phép.
- IPv6 loopback ::1/128, unspecified ::/128.
- IPv6 link-local fe80::/10, unique-local fc00::/7, multicast ff00::/8.
- IPv4-mapped IPv6 và các dạng biểu diễn có thể che địa chỉ IPv4.
- Địa chỉ metadata cloud và các destination nội bộ theo kiến trúc triển khai.

Danh sách trên là những nhóm quan trọng, không phải toàn bộ registry địa chỉ đặc biệt. Hãy dùng thư viện IP/CIDR đáng tin cậy và policy được cập nhật; không viết regex để phân loại IP.

### 5.3. Chặn cloud metadata endpoint ở tầng mạng

Dịch vụ metadata thường được đặt ở địa chỉ link-local hoặc địa chỉ đặc biệt của cloud provider. Nếu SSRF truy cập được metadata, attacker có thể tìm cách lấy credential hoặc thông tin cấu hình của workload.

Không chỉ dựa vào việc ứng dụng chặn một URL metadata đã biết. Hãy:

- Chặn route đến metadata endpoint từ workload không cần truy cập.
- Dùng cấu hình bảo vệ metadata theo khuyến nghị của cloud provider.
- Giới hạn quyền của workload identity/instance role.
- Không cấp credential cloud quá rộng.
- Theo dõi request đến các dải link-local hoặc metadata destination.

### 5.4. IPv4 và IPv6 phải được xử lý đồng nhất

Nếu chỉ chặn IPv4 private mà bỏ IPv6, attacker có thể dùng IPv6 literal hoặc DNS AAAA để đi đến mạng nội bộ. Cần kiểm tra cả hai họ địa chỉ, IPv4-mapped IPv6 và cách hệ thống chọn địa chỉ khi kết nối.

Không tự giả định mọi môi trường có IPv6 đều được định tuyến giống nhau. Hãy kiểm tra route thực tế, firewall và network policy của cluster/VPC.

## 6. DNS rebinding và kiểm tra địa chỉ tại thời điểm kết nối

DNS rebinding khai thác việc hostname có thể phân giải ra một IP ở thời điểm kiểm tra và IP khác ở thời điểm kết nối. Ví dụ, ứng dụng kiểm tra hostname và thấy IP public; sau đó HTTP client phân giải lại hostname và nhận IP nội bộ.

Đây là lỗi time-of-check/time-of-use (TOCTOU): quyết định an toàn được đưa ra trên một kết quả DNS nhưng socket thực tế sử dụng một kết quả khác.

### 6.1. Không chỉ validate rồi để HTTP client tự resolve lại

Một flow không an toàn:

1. Ứng dụng resolve hostname.
2. Kiểm tra IP trả về là public.
3. Ứng dụng truyền URL ban đầu cho HTTP client.
4. HTTP client tự resolve hostname lần nữa.
5. DNS trả về IP nội bộ và client kết nối đến đó.

Bước kiểm tra ban đầu không ràng buộc được socket cuối cùng.

### 6.2. Enforce destination tại egress proxy

Một egress proxy chuyên dụng có thể:

1. Nhận yêu cầu kết nối đến hostname/port.
2. Canonicalize và kiểm tra hostname theo allowlist.
3. Tự resolve A/AAAA.
4. Kiểm tra địa chỉ IP theo policy.
5. Kết nối trực tiếp đến IP đã được kiểm tra.
6. Giữ nguyên hostname logic cho TLS SNI và certificate verification.
7. Áp dụng timeout, giới hạn kết nối và log destination.
8. Từ chối redirect hoặc destination mới nếu chưa qua policy.

Điểm quan trọng là proxy phải kiểm soát IP thực tế được dùng để mở socket. Nếu chỉ kiểm tra hostname rồi để một thành phần khác resolve lại, DNS rebinding vẫn có thể xảy ra.

### 6.3. Pin địa chỉ kết nối đúng cách

Nếu triển khai pinning ở application, cần bảo đảm HTTP client kết nối đến đúng IP đã kiểm tra trong khi vẫn xác minh TLS certificate theo hostname gốc. Không được tắt hostname verification hoặc thay SNI bằng IP chỉ để pin địa chỉ.

Việc tự viết DNS resolver/socket factory hoặc sửa URL để thay hostname bằng IP dễ tạo lỗi TLS, proxy và connection pooling. Với hệ thống quan trọng, dùng egress proxy hoặc thư viện đã được thiết kế để bind DNS result với connection là lựa chọn dễ kiểm soát hơn.

### 6.4. Cache DNS có giới hạn

DNS cache quá lâu có thể giữ destination cũ sau khi policy hoặc bản ghi DNS thay đổi. Cache quá ngắn có thể tăng tải resolver. Cần cân bằng TTL, re-resolution và revocation; dù cache ở đâu, policy vẫn phải được áp dụng tại thời điểm mở kết nối mới.

## 7. Redirect và nhiều hop

HTTP redirect có thể khiến request đi đến một host khác với URL ban đầu. Một endpoint ban đầu nằm trong allowlist có thể trả 302 Location trỏ đến 127.0.0.1, địa chỉ metadata hoặc một hostname không được phép.

### 7.1. Tắt redirect mặc định

Với chức năng fetch URL do caller kiểm soát, nên tắt tự động redirect nếu nghiệp vụ không cần. Nếu cần redirect, application phải xử lý từng hop:

1. Parse URL mới.
2. Kiểm tra scheme, hostname, port và path theo policy.
3. Resolve DNS và kiểm tra toàn bộ địa chỉ.
4. Kiểm tra destination tại tầng egress.
5. Giảm số redirect còn lại.
6. Không chuyển tiếp credential hoặc header nhạy cảm sang origin khác.
7. Áp dụng lại deadline tổng cho toàn bộ chuỗi.

### 7.2. Giới hạn số hop

Nếu cho phép redirect, đặt số hop nhỏ và cố định. Từ chối vòng lặp, redirect chain quá dài, downgrade từ HTTPS xuống HTTP hoặc thay đổi scheme/port không được phê duyệt.

Không reset total timeout sau mỗi redirect. Một chuỗi redirect có thể làm request giữ tài nguyên lâu hơn nhiều so với deadline dự kiến nếu mỗi hop có timeout riêng nhưng không có deadline tổng.

### 7.3. Không chuyển tiếp credential qua origin khác

Nếu request outbound chứa authorization header, cookie hoặc API key của tích hợp, redirect sang origin khác có thể làm lộ credential. Không forward credential qua origin thay đổi trừ khi giao thức và policy đã xác định rõ. Với webhook delivery, secret ký request cần gắn với endpoint/tenant tương ứng và không gửi sang host khác.

## 8. Proxy và ngăn bypass egress control

Nhiều HTTP client hỗ trợ proxy qua cấu hình ứng dụng, biến môi trường hoặc system property. Nếu application dùng proxy nhưng workload vẫn có đường mạng trực tiếp, attacker có thể bypass proxy bằng client khác, protocol khác hoặc cấu hình không dùng proxy.

### 8.1. Proxy phải là trust boundary thực sự

Egress proxy cần:

- Xác thực workload gọi proxy.
- Áp dụng hostname, port và IP policy.
- Resolve DNS và kiểm tra destination thực tế.
- Giới hạn CONNECT target đối với HTTPS.
- Từ chối port và protocol không được phép.
- Áp dụng connection limit và timeout.
- Ghi log destination, caller workload và policy result.
- Không ghi credential hoặc payload nhạy cảm.

### 8.2. Chặn đường đi trực tiếp

Nếu policy yêu cầu mọi outbound đi qua proxy, firewall hoặc network policy phải chặn kết nối trực tiếp từ workload đến Internet và mạng không được phép. Chỉ cho phép workload kết nối tới proxy và các dịch vụ nội bộ được chỉ định.

Không coi việc đặt HTTPS_PROXY hoặc cấu hình proxy trong code là enforcement. Caller có thể bỏ qua biến môi trường nếu network vẫn cho phép kết nối trực tiếp.

### 8.3. Xử lý proxy chain rõ ràng

Không để một proxy tin proxy bất kỳ hoặc header forwarding do client gửi. Ghi rõ proxy nào được phép kết nối, cách truyền workload identity và cách xác định IP/hostname đích. Nếu có nhiều hop, cần bảo đảm policy được thực thi ở hop có thể quan sát destination thực tế.

## 9. Kubernetes NetworkPolicy cho outbound

Kubernetes NetworkPolicy có thể giới hạn egress ở lớp L3/L4 nếu CNI plugin hỗ trợ NetworkPolicy. Một policy egress mặc định từ chối giúp workload không tự do mở kết nối ra ngoài.

Ví dụ minh họa: mặc định chặn egress cho các pod trong namespace, sau đó chỉ cho DNS và một địa chỉ dịch vụ đã được phê duyệt:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: payments
spec:
  podSelector: {}
  policyTypes:
    - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-and-partner
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: webhook-worker
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
    - to:
        - ipBlock:
            cidr: 203.0.113.10/32
      ports:
        - protocol: TCP
          port: 443
```

Địa chỉ 203.0.113.10/32 thuộc dải tài liệu minh họa; phải thay bằng CIDR thực tế đã được phê duyệt. Label của DNS pod và namespace cũng cần khớp cluster thực tế.

### 9.1. Giới hạn của Kubernetes NetworkPolicy

NetworkPolicy chuẩn chủ yếu kiểm soát pod, IP/CIDR, protocol và port. Nó không cung cấp FQDN allowlist phổ quát trong API chuẩn. Nếu destination có IP thay đổi theo DNS, cần một trong các phương án:

- CNI hỗ trợ FQDN policy và có cơ chế DNS-aware phù hợp.
- Egress gateway/proxy thực thi hostname allowlist và kiểm tra IP.
- Dùng endpoint có IP ổn định được quản lý.
- Dùng service mesh/egress gateway có policy destination.

Không nên tự động cập nhật CIDR từ DNS mà không có kiểm tra, audit và xử lý race condition.

### 9.2. Cho phép DNS có kiểm soát

Pod cần DNS để resolve tên dịch vụ. Chỉ mở UDP/TCP 53 đến resolver được chỉ định. Nếu DNS đi qua node-local DNS cache hoặc một địa chỉ khác, policy phải khớp topology thực tế.

DNS query cũng là outbound traffic và có thể bị lạm dụng để exfiltrate dữ liệu qua tên miền. Với workload rủi ro cao, cân nhắc DNS logging, giới hạn resolver và giám sát query bất thường.

### 9.3. Policy có tính cộng gộp

Trong Kubernetes, nhiều NetworkPolicy áp dụng cho cùng pod thường có quyền egress được cộng gộp. Một policy default-deny không thể phủ định một policy khác đang cho phép outbound rộng. Cần rà soát toàn bộ policy áp dụng cho pod và test bằng traffic thực tế.

NetworkPolicy cũng phụ thuộc CNI; khai báo YAML thành công không tự chứng minh dataplane đang enforce đúng.

## 10. Egress gateway, firewall và phân đoạn mạng

Với workload cần gọi nhiều dịch vụ bên ngoài, egress gateway có thể tập trung policy và logging. Firewall/VPC security controls có thể bổ sung giới hạn ở network perimeter.

### 10.1. Egress gateway

Một egress gateway có thể cung cấp:

- Destination allowlist theo FQDN/IP.
- DNS resolution và IP validation.
- TLS policy hoặc CONNECT policy.
- Per-workload identity và quota.
- Timeout và connection limit.
- Audit và metrics tập trung.

Ứng dụng nên chỉ được phép kết nối đến gateway. Gateway cần được triển khai dự phòng và có capacity phù hợp để không trở thành điểm nghẽn hoặc single point of failure.

### 10.2. Firewall và security group

Ở cloud/VPC, dùng outbound firewall rule hoặc security group egress rule để giới hạn CIDR và port. Một số security group mặc định cho phép all egress; cần kiểm tra và thu hẹp theo nhu cầu.

Firewall theo IP/port không thay thế hostname validation. Nếu IP của đối tác thay đổi, policy phải có quy trình cập nhật có kiểm soát. Không mở 0.0.0.0/0:443 cho workload có thể nhận URL tùy ý nếu mục tiêu là giới hạn SSRF.

### 10.3. Tách mạng ứng dụng và mạng quản trị

Workload xử lý request từ Internet không nên có đường truy cập mặc định đến control plane, management subnet, database admin port hoặc metadata service. Tách network segment và identity để compromise một application không tự động mở đường sang các vùng nhạy cảm.

## 11. Bảo vệ metadata và dịch vụ nội bộ

SSRF thường nguy hiểm vì server có thể truy cập tài nguyên mà public caller không truy cập trực tiếp.

Các destination cần được xem xét:

- Cloud instance/workload metadata.
- Kubernetes API server và control-plane endpoints.
- Internal admin dashboard.
- Database, cache, message broker và management port.
- Service discovery, metrics và debug endpoints.
- Loopback listener và Unix/socket bridge được expose qua proxy.
- Internal DNS names hoặc service VIP.

### 11.1. Metadata protection

Không cho workload fetch URL tùy ý truy cập metadata. Chặn network path đến metadata endpoint ở lớp firewall/network policy; dùng cơ chế bảo vệ metadata của cloud provider; giới hạn role/identity và quyền credential.

Nếu nền tảng hỗ trợ yêu cầu token/session đặc biệt để truy cập metadata, hãy bật theo khuyến nghị của provider. Đây là lớp bổ sung, không phải lý do để cho phép SSRF đến metadata.

### 11.2. Internal service không phải destination công khai

Nếu một integration cần gọi service nội bộ, cấp quyền rõ ràng cho đúng service identity, operation và port. Không cho phép endpoint URL fetch truy cập toàn bộ private network chỉ vì có một số integration hợp lệ cần nội bộ.

Tách chức năng: API fetch Internet dùng egress policy công khai; luồng nội bộ dùng client/service cụ thể với authorization riêng. Không dùng một proxy có quyền rộng cho cả hai mục đích nếu không có policy phân biệt.

### 11.3. Hạn chế quyền của workload

Ngay cả khi SSRF vượt qua một lớp network control, workload identity chỉ nên có quyền tối thiểu. Metadata role, service account và credential không được cấp quyền quản trị toàn bộ cloud hoặc cluster.

Defense in depth giúp giảm tác động nếu một destination bị truy cập ngoài dự kiến.

## 12. Timeout theo từng pha của kết nối

Một timeout duy nhất không phải lúc nào cũng đủ. Một request outbound có nhiều pha, mỗi pha có thể bị trì hoãn hoặc giữ tài nguyên.

| Pha | Điều cần giới hạn | Ví dụ |
|---|---|---|
| DNS resolution | Thời gian resolver trả kết quả | DNS deadline |
| Connection pool acquisition | Thời gian chờ connection rảnh | Pool acquire timeout |
| TCP connect | Thời gian thiết lập socket | Connect timeout |
| TLS handshake | Thời gian thương lượng TLS | Handshake timeout |
| Request write | Thời gian gửi request body | Write timeout |
| Response headers | Thời gian chờ phản hồi đầu tiên | Response/header timeout |
| Response read | Thời gian giữa các lần đọc hoặc tổng thời gian body | Read/idle timeout |
| Total operation | Toàn bộ luồng từ đầu đến cuối | End-to-end deadline |

### 12.1. DNS timeout

Resolver có thể chậm hoặc không phản hồi. Nếu DNS lookup không có deadline, request có thể giữ thread hoặc event loop lâu hơn dự kiến.

Một số HTTP client dùng resolver của hệ điều hành và không cung cấp timeout DNS riêng ở API cấp cao. Khi cần kiểm soát chặt, dùng resolver có deadline hoặc để egress proxy thực hiện DNS theo policy. Không giả định connect timeout luôn bao gồm toàn bộ thời gian DNS ở mọi client.

### 12.2. Connect timeout

Connect timeout giới hạn thời gian thiết lập TCP connection. Nó giúp tránh giữ request quá lâu khi destination không phản hồi hoặc route bị blackhole.

Không đặt quá cao cho endpoint đồng bộ. Ngưỡng cần dựa trên latency mạng bình thường và SLA của dependency. Với destination bên ngoài Internet, cần tính đến độ trễ mạng nhưng vẫn phải có giới hạn cứng.

### 12.3. TLS handshake timeout

TCP kết nối thành công chưa có nghĩa TLS handshake hoàn tất. Peer có thể trì hoãn hoặc không hoàn tất handshake. Cần có giới hạn riêng hoặc bảo đảm total deadline bao phủ handshake.

Không tắt certificate validation hoặc hostname verification khi timeout xảy ra. Timeout là lỗi kết nối, không phải lý do để hạ mức bảo mật TLS.

### 12.4. Response và read timeout

Response timeout giới hạn thời gian chờ phản hồi; read timeout có thể giới hạn thời gian giữa các lần đọc. Một server có thể gửi một byte định kỳ để né idle timeout, do đó vẫn cần total deadline cho toàn bộ operation.

Cần phân biệt timeout chờ response header với timeout đọc body. Một số thư viện hoàn thành future khi headers đến rồi trả stream body riêng; request timeout có thể không tự giới hạn mọi lần đọc stream. Kiểm tra semantics của client library đang dùng.

### 12.5. Total deadline

Total deadline là giới hạn tổng cho toàn bộ operation, bao gồm DNS, pool wait, connect, TLS, request/response và redirect nếu được phép. Deadline nên được tính bằng monotonic clock và truyền xuống các bước con.

Nếu request còn 500 ms deadline, downstream call không nên tự đặt timeout 5 giây. Mỗi dependency phải nhận ngân sách thời gian còn lại, không reset đồng hồ ở mỗi hop.

## 13. Kết hợp timeout với connection pool và concurrency

HTTP client thường dùng connection pool để tái sử dụng TCP/TLS connection. Pool không giới hạn có thể giữ quá nhiều socket; pool quá nhỏ hoặc queue không giới hạn có thể làm request chờ lâu.

Cần cấu hình:

- Maximum total connections.
- Maximum connections per destination/route.
- Maximum pending acquisition requests.
- Pool acquire timeout.
- Idle connection timeout.
- Maximum connection lifetime.
- Connection eviction và DNS refresh behavior.
- Response body size và số request đang xử lý đồng thời.

### 13.1. Giới hạn pending queue

Khi pool đầy, request không nên xếp hàng vô hạn. Giới hạn queue và thời gian chờ giúp backpressure truyền ngược về caller. Nếu queue đầy, từ chối sớm bằng lỗi phù hợp thay vì để memory tăng không kiểm soát.

### 13.2. Connection reuse và DNS policy

Một connection đã mở có thể tiếp tục được tái sử dụng sau khi DNS record thay đổi. Cần xác định chính sách khi allowlist hoặc DNS mapping bị thu hồi: connection pool có cần đóng connection cũ không, lifetime tối đa là bao lâu và egress gateway có enforce policy trên từng connection hay chỉ khi mở mới.

### 13.3. Giới hạn response body

Một destination hợp lệ vẫn có thể trả body rất lớn hoặc stream vô hạn. Đặt giới hạn byte khi đọc, giới hạn thời gian, giới hạn decompression và chỉ chấp nhận media type cần thiết.

Không chỉ dựa vào Content-Length; response có thể streaming hoặc thiếu header đó. Bộ đếm byte phải theo dõi dữ liệu thực nhận.

## 14. Retry, redirect và timeout budget

Retry có thể giúp vượt qua lỗi mạng tạm thời nhưng cũng có thể khuếch đại tải hoặc làm thao tác nghiệp vụ chạy lặp.

### 14.1. Chỉ retry khi có thể bảo đảm semantics

- GET/HEAD thường có thể retry nếu operation thực sự an toàn và idempotent.
- PUT/DELETE cần xem xét semantics và implementation thực tế.
- POST không nên retry mù quáng nếu không có idempotency key hoặc cơ chế deduplication.
- Không retry lỗi policy như destination bị deny, hostname không hợp lệ hoặc TLS certificate không hợp lệ.
- Không retry liên tục khi DNS/egress policy từ chối destination.

### 14.2. Exponential backoff và jitter

Nếu retry được phép, dùng exponential backoff có giới hạn và jitter để nhiều worker không retry cùng lúc. Đặt số lần retry tối đa và tổng retry budget nằm trong total deadline.

Ví dụ, có thể chờ tăng dần 100 ms, 200 ms, 400 ms rồi thêm jitter; con số thực tế phụ thuộc SLA. Không reset total deadline mỗi lần retry.

### 14.3. Retry không được bỏ qua policy

Mỗi lần tạo connection mới cần tiếp tục đi qua egress enforcement. Không giữ một đường fallback direct connection khi proxy lỗi. Nếu policy store không khả dụng, hành vi phải theo fail-closed hoặc degraded mode đã định nghĩa.

### 14.4. Redirect không phải retry

Redirect là chỉ dẫn chuyển sang resource khác; retry là thử lại cùng operation. Không dùng cùng một cơ chế tự động cho cả hai. Mỗi redirect phải qua validation destination mới; mỗi retry phải giữ deadline và idempotency semantics.

## 15. Ví dụ cấu hình timeout trong Java

java.net.http.HttpClient cho phép đặt connect timeout, chính sách redirect và timeout cho từng request. Ví dụ cấu hình cơ bản:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

public final class OutboundClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public HttpRequest buildRequest(URI approvedUri) {
        return HttpRequest.newBuilder(approvedUri)
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "application/json")
                .GET()
                .build();
    }
}
```

Đoạn code minh họa cấu hình connect timeout, request timeout và tắt tự động redirect. Nó không tự tạo destination allowlist, không chặn private IP và không thay thế egress firewall/proxy.

### 15.1. Giới hạn response body

Khi đọc response từ destination bên ngoài, cần dùng streaming hoặc BodySubscriber có bộ đếm byte để dừng khi vượt giới hạn. Không đọc toàn bộ body không giới hạn vào memory rồi mới kiểm tra kích thước.

Với BodyHandlers.ofInputStream(), response có thể được coi là sẵn sàng khi headers đến và body stream được trả cho ứng dụng. Vì vậy, không giả định request timeout của HttpClient tự giới hạn toàn bộ thời gian ứng dụng đọc stream. Cần một read deadline/idle timeout riêng và total deadline bao phủ cả quá trình tiêu thụ body.

### 15.2. DNS và destination enforcement

HttpClient cấp cao không cung cấp một API đơn giản để ràng buộc mọi DNS result đã kiểm tra với socket cuối cùng trong mọi môi trường. Nếu SSRF risk cao, thực thi destination policy tại egress proxy/network layer là cần thiết. Ứng dụng vẫn phải validate URI và không tự cho phép redirect.

### 15.3. TLS phải luôn xác minh peer

Không tắt certificate validation hoặc hostname verification để xử lý lỗi kết nối. Dùng trust store phù hợp, xác minh hostname của endpoint allowlist và quản lý certificate theo quy trình. Không thay hostname bằng IP trong URL nếu điều đó làm mất SNI/hostname verification.

## 16. Quản lý policy và thay đổi cấu hình

Egress allowlist là một phần của security configuration và cần quản trị như code.

Một quy trình thay đổi có thể gồm:

1. Owner của API xác định nhu cầu outbound và đích cụ thể.
2. Ghi rõ hostname/IP, port, protocol, environment và mục đích.
3. Xác minh destination thuộc đối tác/dịch vụ đã phê duyệt.
4. Đánh giá rủi ro nếu destination bị compromise hoặc DNS thay đổi.
5. Review policy và quyền của workload.
6. Triển khai theo môi trường.
7. Kiểm thử allow/deny path.
8. Theo dõi log/metric sau triển khai.
9. Định kỳ loại bỏ rule không còn dùng.

Không thêm 0.0.0.0/0 hoặc toàn bộ private CIDR chỉ để sửa một lỗi kết nối. Nếu dependency thay đổi IP, ưu tiên giải pháp FQDN-aware proxy hoặc quản lý danh sách CIDR có owner, nguồn và lịch cập nhật.

### 16.1. Fail closed hay degraded mode

Nếu egress proxy, DNS policy service hoặc policy store không khả dụng, cần định nghĩa hành vi:

- **Fail closed:** từ chối outbound mới khi không thể xác minh destination. Phù hợp với luồng có rủi ro SSRF cao.
- **Degraded mode:** chỉ cho phép destination đã cache và còn hiệu lực theo giới hạn rõ.
- **Fail open:** bỏ qua enforcement khi policy service lỗi; rủi ro cao và thường không phù hợp cho URL do caller kiểm soát.

Không tự động chuyển sang direct Internet access khi proxy lỗi. Hành vi fallback có thể vô hiệu hóa toàn bộ kiểm soát SSRF.

## 17. Logging, monitoring và phát hiện outbound bất thường

Log outbound nên giúp xác định workload nào kết nối đến đâu và policy nào đã quyết định, nhưng không được làm lộ credential hoặc payload nhạy cảm.

Các trường hữu ích:

- Workload/service identity đã xác minh.
- Operation hoặc endpoint khởi tạo outbound.
- Destination hostname đã canonicalize.
- Destination IP và port thực tế ở mức cần thiết.
- Protocol/scheme.
- Egress policy ID và allow/deny result.
- DNS result category, không nhất thiết lưu toàn bộ dữ liệu nhạy cảm.
- Redirect count và destination thay đổi nếu có.
- Connect/TLS/response/read duration.
- Timeout phase và error category.
- Response byte count.
- Correlation/trace ID.

Không log URL có query chứa token, signed URL, API key, Authorization header, cookie hoặc response body nhạy cảm. Có thể log host/path đã redact và policy result.

### 17.1. Metric và alert

Theo dõi:

- Số kết nối outbound được phép/từ chối theo workload và policy.
- Số request cố truy cập loopback, private, link-local hoặc metadata range.
- DNS resolution failure và hostname trả về địa chỉ bị cấm.
- Redirect bị từ chối.
- Proxy bypass attempt hoặc direct egress deny.
- Timeout theo pha: DNS, pool, connect, TLS, response, read, total.
- Connection pool saturation và pending queue.
- Outbound request rate, response bytes và latency p95/p99.
- Tỷ lệ retry và lỗi từ dependency.

Cảnh báo khi một workload đột ngột kết nối đến nhiều hostname mới, nhiều port lạ, IP nội bộ hoặc metadata range; hoặc khi timeout/retry tăng nhanh.

### 17.2. Phân biệt policy deny và lỗi dependency

EgressDenied có nghĩa policy không cho phép destination. ConnectTimeout có nghĩa kết nối không hoàn tất trong thời gian cho phép. TLSValidationFailed cho biết peer không vượt qua xác minh TLS. Các lỗi này cần được phân loại riêng để nhóm vận hành không mở rộng allowlist chỉ nhằm che một sự cố DNS hoặc certificate.

## 18. Kiểm thử egress policy và timeout

Kiểm thử phải đi qua đúng đường mạng từ workload, qua proxy/firewall đến destination. Unit test URL validator không chứng minh egress policy đang được enforce.

### 18.1. Kiểm thử destination allowlist

- Hostname được phép và port đúng kết nối thành công.
- Hostname không được phép bị từ chối.
- Hostname gần giống allowlist nhưng khác domain bị từ chối.
- Scheme không hỗ trợ bị từ chối.
- Port không được phép bị từ chối.
- URL chứa userinfo hoặc authority mơ hồ bị từ chối.
- IP literal không thuộc policy bị từ chối.
- Hostname IDN/trailing dot được canonicalize nhất quán.
- DNS có cả A và AAAA record được kiểm tra đầy đủ.

### 18.2. Kiểm thử SSRF và DNS

Trong môi trường kiểm thử được kiểm soát:

- Hostname phân giải tới loopback/private/link-local bị từ chối.
- DNS trả kết quả public ở lần đầu và private ở lần sau không vượt qua enforcement.
- IPv6 loopback, ULA và IPv4-mapped IPv6 bị xử lý đúng.
- Metadata endpoint không thể truy cập từ workload không được phép.
- Redirect từ host được phép sang host/IP bị cấm bị chặn.
- Redirect chain quá dài hoặc downgrade HTTPS bị từ chối.
- Proxy không thể bị bypass bằng direct connection.
- Không có route outbound ngoài policy.

Không thực hiện kiểm thử trên metadata hoặc hệ thống nội bộ production nếu không có phạm vi và phê duyệt kiểm thử riêng. Dùng mock resolver, test server và network sandbox.

### 18.3. Kiểm thử timeout

- DNS resolver chậm hoặc không phản hồi.
- TCP connect bị blackhole.
- TCP connect thành công nhưng TLS handshake bị treo.
- Server không trả response headers.
- Server gửi body chậm từng byte.
- Server giữ connection mở nhưng không gửi thêm dữ liệu.
- Response body vượt giới hạn byte.
- Pool hết connection và pending queue đầy.
- Redirect chain tiêu tốn gần hết deadline.
- Retry không vượt total deadline.
- Proxy lỗi không kích hoạt direct egress fallback.

### 18.4. Kiểm thử network policy

- Pod không thể kết nối destination ngoài allowlist.
- DNS chỉ đi đến resolver được phép.
- Chỉ workload có label/identity phù hợp được dùng egress rule.
- Một NetworkPolicy khác không vô tình mở egress rộng.
- CNI thực sự enforce rule trên dataplane.
- Khi gateway hoặc policy store lỗi, hành vi đúng fail mode đã thiết kế.

## 19. Những lỗi thiết kế thường gặp

1. **Chỉ validate URL ở application.** Socket cuối cùng có thể kết nối đến IP khác sau DNS re-resolution.
2. **Chỉ chặn RFC1918 IPv4.** Bỏ sót IPv6, link-local, loopback, special-purpose và metadata.
3. **Allowlist hostname nhưng không kiểm tra DNS result.** Hostname có thể trỏ đến địa chỉ không được phép.
4. **Kiểm tra DNS một lần rồi để client tự resolve lại.** Tạo cửa sổ DNS rebinding.
5. **Cho phép redirect tự động.** Redirect có thể đưa request đến host/IP khác.
6. **Tin proxy configuration trong environment.** Workload có thể bỏ qua proxy nếu direct egress vẫn mở.
7. **Default allow outbound.** Một lỗi SSRF có thể truy cập gần như mọi dịch vụ mà workload nhìn thấy.
8. **Chỉ giới hạn port 443.** HTTPS không có nghĩa destination an toàn.
9. **Không chặn metadata ở network layer.** SSRF có thể tiếp cận credential của workload.
10. **Không phân đoạn workload.** Một service có quyền mạng quá rộng làm tăng blast radius.
11. **Chỉ đặt connect timeout.** DNS, TLS, response body hoặc pool wait vẫn có thể giữ tài nguyên.
12. **Không có total deadline.** Nhiều pha/redirect/retry cộng dồn làm request kéo dài.
13. **Retry không giới hạn.** Có thể gây retry storm và khuếch đại tải.
14. **Pool hoặc pending queue không giới hạn.** Outbound traffic có thể làm cạn socket và memory.
15. **Không giới hạn response body.** Destination hợp lệ vẫn có thể trả payload khổng lồ.
16. **Tắt TLS hostname verification.** Có thể biến một lỗi cấu hình thành nguy cơ MITM.
17. **NetworkPolicy được tạo nhưng không kiểm tra CNI.** YAML tồn tại nhưng dataplane có thể không enforce như mong đợi.
18. **Mở rộng allowlist khi gặp timeout.** Timeout thường cần điều tra DNS, route, proxy hoặc dependency trước khi cấp thêm quyền.

## 20. Checklist thiết kế và triển khai

Trước khi đưa một chức năng outbound vào production, hãy xác nhận:

- [ ] Workload có nhu cầu outbound rõ ràng và owner chịu trách nhiệm.
- [ ] Egress mặc định bị chặn; chỉ mở destination cần thiết.
- [ ] URL chỉ cho phép scheme, hostname và port theo allowlist.
- [ ] Hostname được canonicalize trước khi so sánh.
- [ ] DNS A và AAAA được kiểm tra; không bỏ qua địa chỉ thứ hai.
- [ ] Loopback, private, link-local, multicast, reserved và metadata destination bị chặn theo policy.
- [ ] IP thực tế mở socket được enforcement ở proxy/firewall/network layer.
- [ ] DNS rebinding và re-resolution được xử lý.
- [ ] Redirect tắt mặc định hoặc mỗi hop đều được validate lại.
- [ ] Credential không bị forward sang origin khác.
- [ ] Proxy không thể bị bypass bằng direct egress.
- [ ] Kubernetes NetworkPolicy/CNI/firewall được kiểm thử trên dataplane.
- [ ] Workload không có quyền mạng đến database/admin/control plane không cần thiết.
- [ ] Có DNS, pool acquire, connect, TLS, response, read và total timeout.
- [ ] Total deadline được truyền xuyên suốt các dependency và redirect/retry.
- [ ] Connection pool, pending queue, concurrency và response size có giới hạn.
- [ ] Retry có idempotency, backoff, jitter và retry budget.
- [ ] TLS certificate và hostname verification luôn bật.
- [ ] Log ghi workload, destination, policy result và timeout phase mà không lộ secret.
- [ ] Có alert cho metadata/private IP attempt, proxy bypass, timeout và outbound bất thường.
- [ ] Có test qua toàn bộ đường egress thực tế, không chỉ unit test URL parser.

## 21. Kết luận

Egress network policy và timeout là hai lớp kiểm soát bổ sung cho validation URL trong phòng chống SSRF. Ứng dụng cần giới hạn scheme, hostname, port và redirect; DNS/IP policy cần kiểm tra cả A/AAAA và ngăn địa chỉ không được phép; network layer hoặc egress proxy phải kiểm soát destination thực tế mà socket kết nối đến.

Nguyên tắc default-deny, workload segmentation, chặn metadata và ngăn proxy bypass giúp giảm phạm vi mạng mà một SSRF có thể tiếp cận. Timeout theo từng pha, total deadline, connection pool limit, response size limit và retry budget giúp một kết nối outbound không chiếm tài nguyên vô hạn.

Một thiết kế đáng tin cậy cần được kiểm thử qua đúng gateway, proxy, firewall và workload runtime. Khi URL validation, DNS enforcement, network policy, timeout, authorization và monitoring cùng hoạt động, API sẽ hạn chế đáng kể khả năng biến server thành proxy truy cập các hệ thống ngoài phạm vi cho phép.

