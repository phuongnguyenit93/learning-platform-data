# Route 53 hosted zone và quản lý bản ghi DNS

Khi người dùng mở `https://www.example.com`, ứng dụng không nhận trực tiếp tên miền đó: trước hết hệ thống **DNS (Domain Name System)** phải trả lời câu hỏi tên miền trỏ đến địa chỉ IP hoặc tên đích nào. Trên AWS, **Amazon Route 53** cung cấp dịch vụ DNS có thẩm quyền (*authoritative DNS*), đăng ký tên miền, kiểm tra tình trạng endpoint và các cơ chế chọn câu trả lời DNS theo chính sách định tuyến. Trung tâm của việc quản lý DNS là **hosted zone**: tập hợp các bản ghi cho một domain và những subdomain mà zone có thẩm quyền quản lý.

Bài thuộc chương **DNS và phân phối nội dung** của mô-đun **CLOUD_PROVIDERS_AWS**. Khi làm chủ hosted zone và bản ghi DNS, người học có thể trỏ domain tới Application Load Balancer của ứng dụng Java/Spring Boot trên EC2/ECS/EKS, đưa website tĩnh qua CloudFront và S3, đặt tên nội bộ cho dịch vụ trong VPC, kết nối Route 53 với IAM/ACM, thiết kế failover và giám sát, đồng thời kiểm soát số lượng hosted zones, truy vấn và các khoản phí liên quan.

> **Nguyên tắc:** Tạo bản ghi trong Route 53 chưa đủ để Internet dùng được bản ghi đó. Với **public hosted zone**, domain phải được **ủy quyền (delegation)** tới đúng các authoritative name servers; với **private hosted zone**, VPC/Resolver phải được cấu hình để nhìn thấy zone. DNS chọn đích để kết nối; DNS **không tự mở cổng, cấp quyền hoặc bảo đảm ứng dụng khỏe**.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt **registrar**, **domain registration**, **public/private hosted zone**, authoritative name server và **recursive resolver**.
2. Giải thích `NS`, `SOA`, `A`, `AAAA`, `CNAME`, `MX`, `TXT`, `CAA` và Route 53 **alias**.
3. Tạo kế hoạch đổi/delegate name servers đúng khi chuyển DNS sang Route 53; biết vì sao nhiều zone cùng tên không có nghĩa đều đang được Internet sử dụng.
4. Thiết kế bản ghi trỏ domain vào ALB, CloudFront hoặc endpoint ứng dụng; lựa chọn **alias** thay vì `CNAME` ở zone apex.
5. Giải thích TTL, cache, negative caching, thay đổi `PENDING → INSYNC` và cách rollout DNS ít gián đoạn.
6. Mô tả private hosted zone, VPC association, split-view DNS và yêu cầu Route 53 Resolver.
7. Đọc/kiểm tra hosted zones và record sets qua Console, AWS CLI, `dig`/`nslookup`; hiểu cấu trúc change batch.
8. Phân biệt routing policies, health checks, IAM, DNSSEC và chi phí DNS để có quyết định vận hành phù hợp.

## 2. DNS hoạt động thế nào trước khi ứng dụng nhận request?

DNS thường gồm những vai trò:

| Thành phần | Chức năng |
|---|---|
| **Stub resolver** trên máy người dùng | Hỏi DNS resolver đã cấu hình trong hệ điều hành/trình duyệt |
| **Recursive resolver** | Tra cứu và cache kết quả, ví dụ resolver của nhà mạng/doanh nghiệp hoặc Route 53 Resolver bên trong VPC |
| **Root/TLD name servers** | Chỉ dẫn tới authoritative name servers của miền, dựa trên delegation |
| **Authoritative name servers** | Trả lời các record theo cấu hình zone; Route 53 đóng vai trò này cho public hosted zone được delegate đúng |
| **Client và backend** | Sau khi phân giải DNS, client mới kết nối HTTPS/TCP tới đích; load balancer/CDN xử lý request tiếp theo |

~~~mermaid
sequenceDiagram
    participant U as Browser của người dùng
    participant R as Recursive DNS resolver
    participant P as Root / TLD và delegation
    participant Z as Route 53 authoritative DNS
    participant E as CloudFront / ALB / Endpoint
    U->>R: Hỏi A/AAAA www.example.com
    alt Cache còn hiệu lực
        R-->>U: Bản ghi đã cache
    else Cache miss
        R->>P: Tìm name servers cho example.com
        P-->>R: NS delegation
        R->>Z: Hỏi bản ghi www.example.com
        Z-->>R: A/AAAA/CNAME theo cấu hình
        R-->>U: Kết quả và TTL
    end
    U->>E: Kết nối HTTPS theo DNS answer
    E-->>U: HTTP response
~~~

Sơ đồ rút gọn quá trình thực tế: recursive resolver có thể cache NS, đi theo nhiều CNAME, dùng EDNS Client Subnet và chính sách khác. Điều quan trọng là **Route 53 trả lời DNS**, còn **CloudFront**, **ALB**, **EC2** hoặc ứng dụng mới nhận lưu lượng HTTP/TCP.

### 2.1. Ví dụ ứng dụng Java

Một Spring Boot service chạy trên ECS sau ALB có tên DNS do AWS cấp dạng `my-api-123.ap-southeast-1.elb.amazonaws.com`. Đội sản phẩm muốn khách hàng truy cập `api.example.com`. Họ tạo record Route 53 `api.example.com` là **alias A** trỏ tới ALB; sau khi DNS được phân giải, client truy cập ALB qua HTTPS, ALB chọn target ECS dựa trên target group health checks.

Route 53 không nhận request REST `/orders`, không đọc JWT và không tự gán Security Group cho ALB. Những việc đó thuộc lớp ứng dụng/load balancer/IAM/network tương ứng.

## 3. Domain registration, hosted zone và DNS delegation

Ba khái niệm thường bị gộp thành “mua tên miền trên Route 53”, nhưng chúng là ba phần khác nhau.

- **Domain registration:** ghi nhận quyền sử dụng `example.com` qua registrar và registry/TLD, gia hạn theo chu kỳ. Domain có thể đăng ký ở Route 53 hoặc nhà đăng ký khác.
- **Hosted zone:** tập hợp bản ghi DNS do Route 53 quản lý cho `example.com` hoặc một subdomain. Zone có **hosted zone ID** dạng `Z...`; tạo zone có thể phát sinh phí ngay cả khi không được ai query.
- **Delegation:** parent DNS zone/registrar chỉ tới **name servers** của hosted zone đang chịu trách nhiệm trả lời.

Tạo `example.com` public hosted zone thường sinh sẵn **NS** và **SOA** records. Route 53 cung cấp một bộ bốn name servers. Muốn domain đã đăng ký hoạt động qua zone này, phải cấu hình registrar/TLD để dùng **đúng bốn NS** của **đúng zone**. Việc sở hữu một zone có tên khớp với domain **không tự thay đổi NS ở registrar**.

### 3.1. Phân biệt hai bộ NS

Giả sử Route 53 cấp name servers minh họa:

~~~text
ns-100.awsdns-10.com.
ns-200.awsdns-20.net.
ns-300.awsdns-30.org.
ns-400.awsdns-40.co.uk.
~~~

Đây **chỉ là tên giả lập**, không phải danh sách có thể dùng để cấu hình một domain thật.

Có hai nơi cần nhìn:

1. **NS record trong hosted zone**: Route 53 tạo để công bố authoritative NS của zone.
2. **Delegation của domain ở parent/TLD qua registrar**: chỉ cho recursive resolver phải hỏi name servers nào khi cần `example.com`.

Nếu bộ NS ở registrar vẫn trỏ tới nhà cung cấp DNS cũ, Internet tiếp tục dùng các record của nhà cung cấp đó. Bạn có thể tạo `api.example.com` trong Route 53 suốt ngày mà người dùng ngoài Internet vẫn không thấy.

### 3.2. Nếu có nhiều hosted zone trùng tên?

AWS cho phép tạo nhiều public hosted zones tên `example.com`, mỗi zone có **hosted zone ID và NS set riêng**. Domain chỉ được delegate tới NS thực tế ở parent. Route 53 **không tự hợp nhất** record từ các zone cùng tên.

Đây là lỗi dễ xảy ra khi môi trường dev/staging/production hoặc IaC tạo zone mới rồi cập nhật record nhầm zone ID. Luôn đối chiếu **hosted zone ID**, **record sets** và **NS đang được delegate** trước khi thay đổi production.

## 4. Public hosted zone và private hosted zone

| Thuộc tính | **Public hosted zone** | **Private hosted zone (PHZ)** |
|---|---|---|
| Đối tượng tra cứu | Internet thông qua authoritative DNS delegation | Resolver cho các VPC liên kết và các đường DNS tích hợp phù hợp |
| Phạm vi | Tên miền và subdomain công khai | Namespace DNS riêng của hệ thống nội bộ |
| Cần NS ở registrar? | **Có** để domain Internet truy vấn đúng zone | **Không** để VPC tự phân giải PHZ; cần VPC association |
| VPC association | Không bắt buộc | Có; cross-account cần cơ chế cho phép association |
| DNS records | Website, email, domain validation, public API | Tên dịch vụ nội bộ, private ALB, RDS endpoint alias phù hợp |
| Quyền ứng dụng | DNS không thay thế TLS/SG/IAM | DNS không thay thế route/VPC security/auth |
| DNSSEC signing | Route 53 hỗ trợ theo điều kiện của public zone | **Không hỗ trợ signing trực tiếp trên PHZ** |
| Trường hợp chính | `www.example.com`, `api.example.com` cho khách hàng | `db.internal.example.com`, `service.corp.example.com` cho workload |

### 4.1. Public hosted zone không có nghĩa backend phải public

Public zone có thể chứa record cho một **CloudFront distribution**, ALB internet-facing hoặc các endpoint khác. Tạo record public `api.example.com` hướng tới một IP private không khiến Internet truy cập được IP đó, vì VPC routing/security vẫn chặn theo thiết kế. Công khai DNS record cũng có thể làm lộ naming/metadata không cần thiết; tránh đặt tên tài nguyên nhạy cảm trong public zone.

### 4.2. Private hosted zone cần điều kiện VPC DNS

Để sử dụng PHZ với các VPC được liên kết, đảm bảo các thuộc tính của VPC:

~~~text
enableDnsSupport   = true
enableDnsHostnames = true
~~~

Bên trong VPC, **Route 53 Resolver / AmazonProvidedDNS** phân giải record trong PHZ đã liên kết. Bản ghi tồn tại trong PHZ **không tự chia sẻ tới mọi VPC được peering hoặc nối bằng Transit Gateway**. Nếu muốn VPC B cũng dùng tên nội bộ của VPC A, phải thiết kế PHZ association cho B hoặc hệ thống forwarding/Resolver phù hợp, và cần mạng thông tới private endpoint thực tế.

Đối với máy chủ ở mạng on-premises qua VPN/Direct Connect, private hostname có thể cần **Route 53 Resolver inbound endpoints** và quy tắc DNS forward; một kết nối mạng vật lý/VPN đơn thuần không tự cho phép DNS ở on-prem biết các record private.

### 4.3. Split-view / split-horizon DNS

Một tổ chức có thể dùng **hai hosted zones cùng tên** `example.com`:

- Public zone: `api.example.com` → public ALB/CloudFront.
- Private zone: `api.example.com` → internal ALB/private IP dành cho workload trong VPC.

~~~mermaid
flowchart TD
    D["Truy vấn api.example.com"]
    D --> I{"Resolver ở đâu?"}
    I -->|"Internet"| P["Public hosted zone"]
    I -->|"VPC có PHZ association"| Q["Private hosted zone"]
    P --> W["CloudFront / Public ALB"]
    Q --> V["Internal ALB / private endpoint"]
~~~

Một điểm rất dễ nhầm: khi tên truy vấn **khớp** một private hosted zone đã liên kết, nhưng zone đó **không có record tương ứng**, Route 53 Resolver **không tự fallback** sang public zone cùng tên; có thể trả phản hồi không tìm thấy tên/record. Vì vậy, nếu cùng namespace public/private, phải chủ động quản lý các record cần xuất hiện trong mỗi view, hoặc tách namespace rõ ràng để tránh xung đột.

## 5. Một DNS record set gồm những gì?

Một resource record set trong Route 53 gồm các thuộc tính cơ bản như:

- **Name:** FQDN, ví dụ `api.example.com.` (dấu chấm cuối chỉ root, nhiều công cụ tự chấp nhận có/không có dấu chấm).
- **Type:** kiểu record như `A`, `AAAA`, `CNAME`, `MX`.
- **TTL:** thời gian (giây) recursive resolver có thể cache; record alias đến AWS resource dùng TTL theo target.
- **Value/ResourceRecords hoặc AliasTarget:** IP, hostname, cấu trúc dữ liệu DNS, hoặc đích alias.
- **Routing policy:** simple, weighted, latency, failover... có thể thêm `SetIdentifier`, weight, region, health check.

Một hosted zone `example.com` có thể chứa các record dưới đây (IP thuộc dải **documentation-only**, không phải IP server thật):

| Name | Type | Giá trị minh họa | Công dụng |
|---|---|---|---|
| `example.com.` | `A` alias | ALB hoặc CloudFront target | Tên miền gốc (zone apex) |
| `www.example.com.` | `CNAME` | `example.com.` | Alias DNS chuẩn cho subdomain |
| `api.example.com.` | `A` | `192.0.2.10` | IPv4 cho API khi dùng IP tĩnh |
| `api.example.com.` | `AAAA` | `2001:db8::10` | IPv6, nếu endpoint hỗ trợ |
| `example.com.` | `MX` | `10 mail.example.com.` | Mail server và độ ưu tiên |
| `example.com.` | `TXT` | `"v=spf1 include:_spf.example.net -all"` | TXT dùng cho SPF policy minh họa |
| `_acme-challenge.example.com.` | `TXT` | Validation token giả lập | Chứng minh quyền kiểm soát domain |
| `example.com.` | `CAA` | `0 issue "amazon.com"` | Chỉ định CA được phép phát hành cert theo CAA policy |

**Không dùng giá trị ví dụ để cấu hình hệ thống thật.** Những record về email, SPF/DMARC/DKIM, xác thực tên miền và TLS phải lấy giá trị **chính xác** từ nhà cung cấp có trách nhiệm. Record `MX` không làm email hoạt động nếu SMTP/mail provider chưa được thiết lập đúng.

### 5.1. Các loại record thường gặp

| Type | Ý nghĩa | Lưu ý |
|---|---|---|
| **A** | Tên → IPv4 | Có thể nhiều giá trị; với alias được Route 53 phân giải đến đích phù hợp |
| **AAAA** | Tên → IPv6 | Chỉ bật khi endpoint/đường mạng hỗ trợ IPv6 |
| **CNAME** | Một tên → tên canonical khác | **Không đặt CNAME ở zone apex**; không đồng tồn tại với nhiều loại record khác cùng tên theo DNS |
| **MX** | Định tuyến thư đến mail exchanger | Có priority; mail server đích phải phân giải DNS hợp lệ |
| **TXT** | Chuỗi text phục vụ domain verification, SPF, DKIM... | Có quy tắc quoting/chunking, phải theo hướng dẫn từng dịch vụ |
| **NS** | Chỉ ra authoritative name servers cho domain/subdomain | Cực kỳ quan trọng trong delegation |
| **SOA** | Thông tin thẩm quyền và negative caching parameters | Route 53 tạo mặc định; không chỉnh khi chưa hiểu |
| **CAA** | Cho phép/giới hạn certificate authorities | Có thể ảnh hưởng việc phát hành/chạy gia hạn TLS certificate |
| **SRV** | Định danh host/port của dịch vụ | Có format priority/weight/port/target |
| **PTR** | Phân giải ngược IP → tên | Tùy loại reverse DNS và quyền quản trị prefix/IP |

Route 53 còn hỗ trợ các record types khác tùy API như `DS`, `HTTPS`, `SVCB`. Không suy đoán mọi loại record đều hợp lệ trong mọi hosted zone/routing policy; cần kiểm tra tài liệu và tool version trước khi dùng.

### 5.2. Các record cùng Name/Type

Đối với **simple routing**, có thể đặt nhiều IP `A` trong **một record set**. Route 53 có thể trả nhiều địa chỉ; resolver/client chọn IP theo hành vi riêng. Đây **không phải health-aware load balancing**. Khi muốn weight/health, tạo các record sets cùng Name/Type nhưng khác `SetIdentifier` theo chính sách hỗ trợ và khai báo health checks phù hợp.

## 6. Alias, CNAME và zone apex

**Route 53 alias** là mở rộng riêng của Route 53 cho phép trỏ record tới một số AWS resources và record khác. Khi recursive resolver hỏi `A` hoặc `AAAA` của tên alias, Route 53 trả **địa chỉ đích tương ứng** mà không cần công khai CNAME alias record kiểu DNS thông thường.

| Tiêu chí | **CNAME** | **Route 53 alias A/AAAA** |
|---|---|---|
| Chuẩn DNS phổ biến | Có | Tính năng riêng của Route 53 |
| Dùng tại `example.com` (apex) | **Không** | **Có** khi target được hỗ trợ |
| Target | Tên miền canonical | Nguồn AWS tương thích hoặc record Route 53 phù hợp |
| TTL | Do bạn cấu hình | Khi alias tới AWS resource, dùng TTL của resource; alias tới record khác dùng TTL của target |
| Khi IP đích đổi | Resolver tiếp tục resolve CNAME/target | Route 53 tự trả IP cập nhật từ target hỗ trợ |
| Truy vấn DNS từ client | Có thể nhìn thấy CNAME | Nhìn thấy A/AAAA answer, không thấy thuộc tính alias |
| Chi phí truy vấn | Theo DNS query pricing | Alias đến **AWS resource** thường không tính phí Route 53 DNS query cho alias đó, theo quy tắc giá AWS |

### 6.1. Tên miền gốc cần alias thay vì CNAME

Không tạo `CNAME example.com → d123.cloudfront.net` ở apex vì apex cần NS/SOA và theo quy tắc DNS không thể là CNAME. Một cấu hình phổ biến:

~~~text
example.com.      A (Alias)  -> CloudFront distribution
www.example.com.  A (Alias)  -> CloudFront distribution
api.example.com.  A (Alias)  -> Application Load Balancer
~~~

Alias đến CloudFront/ALB yêu cầu **DNSName và HostedZoneId của chính target AWS** (khác với Route 53 hosted zone ID của domain). Khi tạo qua Console, các giá trị đích hỗ trợ thường được gợi ý; khi làm IaC/CLI phải lấy thuộc tính thật của target. Với ALB/NLB, có thể lấy `CanonicalHostedZoneId` từ `describe-load-balancers`.

### 6.2. S3 và CloudFront

Route 53 có thể alias tới S3 **website endpoint** trong các điều kiện hỗ trợ static website hosting, nhưng S3 website endpoint không tự cung cấp HTTPS bằng custom domain. Thiết kế website hiện đại thường dùng **CloudFront** làm CDN/HTTPS endpoint, với S3 bucket làm origin và **Origin Access Control (OAC)** khi muốn bucket private. Cần cấu hình:

1. CloudFront distribution và Alternate Domain Name (CNAME) phù hợp.
2. TLS certificate của AWS Certificate Manager phù hợp với hostname (certificate dùng cho CloudFront cần ở **us-east-1**).
3. Record `A` alias (và `AAAA` nếu dùng IPv6) của domain tới CloudFront.
4. Bucket policy/OAC và origin access chính xác; không mở public bucket chỉ để DNS hoạt động.

**Alias DNS không cấp tự động certificate.** Record có thể resolve thành công nhưng browser vẫn báo TLS hostname mismatch nếu certificate hoặc cấu hình CloudFront/ALB chưa đúng.

### 6.3. Evaluate target health

Alias record cho một số target như ELB có tùy chọn **Evaluate Target Health**; Route 53 có thể dựa vào tình trạng target theo cách dịch vụ đích hỗ trợ khi lựa chọn DNS answer. Không phải mọi loại alias target đều hỗ trợ tính năng này (ví dụ CloudFront có hạn chế riêng). Health evaluation **không thay thế** ALB target group health check, ứng dụng readiness hoặc chiến lược failover end-to-end.

## 7. Tạo public hosted zone và ủy quyền domain

Một quy trình production cần phân biệt **lập DNS records** và **chuyển quyền authoritative**.

### 7.1. Giai đoạn chuẩn bị

1. Liệt kê domain và những subdomain đang sử dụng: website, API, email, domain validation, DMARC/DKIM/SPF, service discovery.
2. Ghi lại record Name/Type/TTL/Values/health rules từ DNS provider hiện tại.
3. Xác định AWS account sở hữu Route 53 public hosted zone; dùng quyền IAM giới hạn.
4. Tạo hosted zone **public** cho `example.com` trong Route 53.
5. Tạo đầy đủ records cần thiết và đối chiếu với cấu hình cũ; kiểm tra các record nhạy cảm như MX/TXT/CAA.
6. Ghi lại **bốn NS** thuộc đúng hosted zone ID.
7. Lên kế hoạch cắt chuyển NS tại registrar, thời điểm giám sát và cách rollback.

### 7.2. Cập nhật registrar

Khi đã sẵn sàng, đổi authoritative nameservers của domain registration sang bốn name servers của hosted zone mới. Nếu domain được đăng ký ở registrar khác, thao tác thực hiện ở giao diện registrar đó; nếu đăng ký tại Route 53, thực hiện trong phần **Registered domains**, không phải chỉ sửa record NS bên trong hosted zone.

**Quan trọng:** Recursive resolvers đã cache delegation NS cũ có thể tiếp tục hỏi DNS provider cũ cho tới khi cache hết hạn. Giữ hosted zone cũ và record nhất quán trong khoảng chuyển tiếp thích hợp, đừng xóa ngay. Chỉ sau khi xác nhận Internet thực sự dùng NS mới và các dịch vụ hoạt động mới dọn tài nguyên cũ.

### 7.3. Giao quyền cho subdomain riêng

Giả sử đội ứng dụng quản lý `apps.example.com` trong hosted zone riêng (có thể ở account khác), còn đội nền tảng sở hữu parent zone `example.com`.

- Tạo public hosted zone `apps.example.com`, nhận bộ NS của **zone con**.
- Trong **parent zone `example.com`**, tạo **NS record cho `apps.example.com`** trỏ tới các name servers của zone con.
- Tạo các records như `api.apps.example.com` ở zone con, xác nhận việc phân giải từ Internet.

~~~mermaid
flowchart TD
    T["TLD .com"] --> P["NS delegation example.com"]
    P --> Z["Public hosted zone example.com"]
    Z --> S["NS delegation apps.example.com"]
    S --> C["Public hosted zone apps.example.com"]
    C --> A["api.apps.example.com → ALB"]
~~~

Không đủ nếu chỉ tạo zone con rồi quên NS delegation ở zone cha. Những record của zone con sẽ không được recursive resolver thông thường tìm thấy đúng đường.

## 8. TTL, DNS cache và thay đổi bản ghi

**TTL (Time to Live)** cho biết recursive resolver được phép giữ một DNS answer trong cache bao nhiêu giây, tính từ lúc nó lấy answer. TTL **không bảo đảm** toàn bộ client trên thế giới thấy thay đổi ngay khi bạn nhấn Save.

Ví dụ bạn đổi `api.example.com` từ `192.0.2.10` sang `192.0.2.20` lúc 10:00:

- Resolver vừa cache bản ghi cũ ở 09:59 với TTL 3600 có thể trả IP cũ gần một giờ nữa.
- Resolver chưa cache hoặc đã hết TTL có thể nhận bản ghi mới sớm hơn.
- Client OS, JVM, application library hoặc proxy có thể còn cache riêng theo chính sách của chúng.

### 8.1. TTL ngắn hay dài?

| TTL minh họa | Dùng khi nào? | Đánh đổi |
|---:|---|---|
| 60 giây | Đổi backend thường xuyên hoặc chuẩn bị cutover | Nhiều DNS lookups hơn, cache ngắn hơn |
| 300 giây | API/website với nhu cầu thay đổi tương đối linh hoạt | Cân bằng mức cache và khả năng thay đổi |
| 3600 giây | Endpoint ổn định | Ít tra cứu lặp lại nhưng rollout/failover qua DNS có thể chậm hơn |
| 86400 giây | Những record rất ổn định, được phép cache lâu | Thay đổi/rollback mất nhiều thời gian |

Các giá trị là **ví dụ**, không phải quy tắc cố định. TTL âm (negative caching) cho câu trả lời không tồn tại liên quan SOA và hành vi resolver. Một hostname vừa được tạo có thể vẫn chưa resolve tại một resolver vì nó đã cache kết quả `NXDOMAIN` trước đó.

### 8.2. Quy trình đổi DNS ít gián đoạn

1. **Trước vài TTL cũ**: giảm TTL của record hiện tại, kiểm tra rằng resolvers đã có thời gian cache giá trị TTL mới.
2. Chuẩn bị backend mới, health checks, TLS certificate và firewall trước cutover.
3. Thay record bằng Console/IaC/change batch; lưu bằng chứng bản cũ và phương án hoàn tác.
4. Chờ **Route 53 change status = INSYNC** trên authoritative name servers.
5. Kiểm tra cả authoritative NS và recursive resolvers từ các vantage points khác nhau; chấp nhận có thời gian cache chồng lấp.
6. Giữ backend cũ chạy trong khoảng phù hợp và monitor HTTP 5xx, latency, DNS query failures.
7. Khi ổn định, cân nhắc nâng TTL lại để giảm truy vấn và tăng khả năng cache.

**`INSYNC` không có nghĩa tất cả recursive resolvers đã bỏ record cũ.** Nó chỉ nghĩa thay đổi đã được đồng bộ tới authoritative name servers của hosted zone. Resolver/client caches vẫn bị ràng buộc bởi TTL và đặc điểm triển khai.

## 9. Route 53 routing policies và health checks

Khi nhiều endpoint cùng phục vụ một hostname, Route 53 có thể áp dụng **routing policy** để chọn DNS answer phù hợp.

| Policy | Ý tưởng | Ví dụ sử dụng |
|---|---|---|
| **Simple** | Trả record/alias theo cấu hình đơn giản | Một ALB cho `api.example.com` |
| **Weighted** | Phân phối câu trả lời theo trọng số | Chuyển dần 10% → 50% → 100% truy vấn sang bản mới |
| **Latency** | Ưu tiên endpoint AWS Region có độ trễ ước tính phù hợp với vị trí resolver/client | Ứng dụng đa Region |
| **Failover** | Primary/secondary theo health | DR site nhận truy vấn khi primary bị coi không khỏe |
| **Geolocation** | Trả lời theo quốc gia/vùng địa lý | Nội dung/quy định theo khu vực |
| **Geoproximity** | Trả lời theo vị trí tài nguyên và bias | Điều chỉnh vùng phục vụ giữa nhiều location |
| **Multivalue answer** | Trả nhiều IP/endpoint cùng kiểm tra sức khỏe khi cấu hình | Những backend đơn giản, không thay load balancer |
| **IP-based** | Trả lời theo CIDR của client/resolver đã xác định | Định tuyến theo nhóm IP nguồn, với loại hosted zone hỗ trợ |

Một số policy/feature được hỗ trợ khác nhau giữa **public** và **private** hosted zones. Ví dụ **IP-based routing không nằm trong danh sách routing policies hỗ trợ cho PHZ** theo tài liệu AWS; hãy kiểm tra nơi dùng thay vì suy rằng mọi policy khả dụng cho mọi zone.

### 9.1. Weighted DNS không đồng nghĩa đúng % request ứng dụng

Nếu tạo hai weighted records cùng Name/Type, gán weight 90 và 10, Route 53 cân nhắc **phần trăm DNS responses** theo trọng số (trong điều kiện health phù hợp), không trực tiếp chia 90% request HTTP. Một recursive resolver có thể cache một answer rồi phục vụ hàng nghìn người dùng; số request thực tế không nhất thiết bằng tỉ lệ record weight.

Để rollout có kiểm soát chính xác từng request, cân nhắc thêm chiến lược ở ALB/API gateway, deployment/canary hoặc application layer.

### 9.2. Failover với health check

Một cấu hình failover thường có:

- Record `PRIMARY` cho endpoint chính và health check/target health tương ứng.
- Record `SECONDARY` cho endpoint dự phòng.
- Chính sách DNS để trả secondary khi primary không khỏe theo logic Route 53.

Các health checks phải kiểm tra **đúng endpoint**. Khi tạo health check theo hostname, không tùy tiện dùng hostname DNS đang điều khiển bởi chính failover record làm URL kiểm tra, vì có thể kiểm tra nhầm backend. Đặt hostname cụ thể theo từng endpoint/vùng, ví dụ `primary-health.example.com` và `secondary-health.example.com`.

Health check từ Route 53 ở ngoài VPC **không mặc nhiên truy cập private IP**. Đối với backend private, cần cách phù hợp như **CloudWatch alarm-based health check** hoặc giám sát/endpoint được thiết kế an toàn. Failover DNS còn chịu TTL/cache; không hứa “chuyển ngay lập tức” khi backend gặp lỗi.

### 9.3. DNS không thay load balancer hoặc CDN

Route 53 đưa client tới endpoint, còn ALB cân bằng request theo target group và CloudFront cache nội dung ở edge. Với hệ thống Java/Spring Boot, thường là:

~~~text
client → DNS Route 53 → CloudFront (tùy chọn) → ALB → ECS/EC2 → RDS
~~~

Nếu cần phục hồi multi-AZ, ALB và Auto Scaling có thể xử lý ở lớp vùng/AZ. Nếu cần chuyển toàn Region, weighted/latency/failover DNS hoặc các dịch vụ global traffic khác là một phần của giải pháp, kèm replication database, dữ liệu, IAM và kiểm thử DR.

## 10. Sử dụng AWS Management Console

### 10.1. Tạo hosted zone

1. Đăng nhập AWS Console bằng IAM Identity Center/role đúng account.
2. Mở **Route 53 → Hosted zones → Create hosted zone**.
3. Nhập **Domain name**, ví dụ `example.com`.
4. Chọn **Public hosted zone** hoặc **Private hosted zone**.
5. Nếu private, liên kết VPC và Region có thẩm quyền sử dụng; kiểm tra DNS attributes.
6. Tạo zone, ghi lại **hosted zone ID**, NS set (public) và SOA.
7. Với public zone, chuẩn bị DNS records trước khi đổi registrar name servers.

Route 53 authoritative hosted zones là tài nguyên được quản lý ở **quy mô toàn cục**, không phải mỗi Region phải tạo một public hosted zone khác cho cùng một domain. Đối với VPC/ALB, phải nhận biết Region của **tài nguyên đích**; private zone associations ghi rõ VPC ID và Region.

### 10.2. Tạo record

Trong hosted zone, chọn **Create record** và xác định:

1. Record name, ví dụ `api` trong zone `example.com` (tạo `api.example.com`).
2. Type `A` hoặc `AAAA`, tùy endpoint IPv4/IPv6.
3. **Alias**: bật khi trỏ tới AWS resource được hỗ trợ; chọn đúng đích.
4. **Routing policy**: simple cho ca cơ bản, hoặc weighted/failover/... khi thiết kế yêu cầu.
5. Với non-alias record, nhập TTL và resource values; với alias dùng quy tắc TTL của target.
6. Rà soát đúng zone/account, target URL/IP và health rồi lưu.

Không sửa mặc định NS/SOA của public zone hoặc tạo record wildcard `*.example.com` khi chưa hiểu ảnh hưởng. Wildcard có quy tắc khớp khác hostname cụ thể và không tự thay thế certificate cho mọi tên.

## 11. AWS CLI: đọc hosted zones và record sets an toàn

Các lệnh phần này **chỉ đọc**, dùng AWS CLI v2 với profile giả định `dev` đã được quản trị viên cấp quyền. Với Route 53 API quản lý hosted zones/records, **không cần `--region`** như khi gọi EC2/VPC; đây là nhóm API quản lý DNS toàn cục. Vẫn phải kiểm tra account/role chính xác trước khi đọc hoặc thay đổi.

### 11.1. Xác định identity/account

~~~bash
aws --version
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

Không dùng tài khoản root để thao tác DNS thường ngày. Khi nhiều account cùng có zone mang tên `example.com`, `sts get-caller-identity` giúp phát hiện đang ở nhầm account trước khi tác động production.

### 11.2. Liệt kê hosted zones

~~~bash
aws route53 list-hosted-zones \
  --profile dev \
  --query 'HostedZones[].{Id:Id,Name:Name,Private:Config.PrivateZone,Records:ResourceRecordSetCount}' \
  --output table

aws route53 list-hosted-zones-by-name \
  --dns-name example.com \
  --profile dev \
  --output json
~~~

`list-hosted-zones-by-name` không nhất thiết chỉ trả **một** zone `example.com`; API trả danh sách theo thứ tự tên từ giá trị chỉ định, có thể có zone tên giống/khác và phân trang. Cần lọc **đúng Name và hosted zone ID** trước khi kết luận.

### 11.3. Xem chi tiết một hosted zone

~~~bash
aws route53 get-hosted-zone \
  --id Z012345EXAMPLE \
  --profile dev \
  --output json
~~~

Một kết quả public zone có thể chứa `DelegationSet.NameServers`; private zone có thể có danh sách VPCs. `Z012345EXAMPLE` là placeholder: dùng **hosted zone ID thật** của account. Khi private zone có association đặc biệt/cross-account, có thể cần đối chiếu thêm API liệt kê zone theo VPC hoặc quản trị network để có đầy đủ bức tranh.

### 11.4. Đọc các record sets

~~~bash
aws route53 list-resource-record-sets \
  --hosted-zone-id Z012345EXAMPLE \
  --profile dev \
  --query 'ResourceRecordSets[].{Name:Name,Type:Type,TTL:TTL,Alias:AliasTarget.DNSName,Values:ResourceRecords[].Value}' \
  --output json
~~~

Kết quả `TTL` có thể vắng ở alias records; trường `AliasTarget` có thể vắng ở standard records. Khi zone nhiều record, CLI hỗ trợ phân trang; **không thêm `--no-paginate`** rồi cho rằng đã đọc đủ toàn zone. API trả danh sách theo tên record và type, có marker để đi tiếp.

### 11.5. Kiểm tra câu trả lời DNS công khai

~~~bash
# Chỉ dành cho PUBLIC hosted zone: mô phỏng authoritative DNS answer.
aws route53 test-dns-answer \
  --hosted-zone-id Z012345EXAMPLE \
  --record-name www.example.com \
  --record-type A \
  --profile dev \
  --output json
~~~

`TestDNSAnswer` hỗ trợ **public hosted zones**, không phải private zones. Đây là cách kiểm tra Route 53 **sẽ trả gì** cho một loại query, không chứng minh registrar đã delegate tới zone hay recursive cache của mọi người đã cập nhật.

Từ một máy có công cụ `dig`:

~~~bash
# Tra cứu qua recursive resolver đang cấu hình
dig A www.example.com
dig AAAA www.example.com
dig NS example.com

# Hỏi trực tiếp một authoritative name server thực tế của hosted zone
dig @ns-real-authoritative.example A www.example.com
~~~

Dòng cuối dùng **placeholder**; cần thay bằng một name server trong `get-hosted-zone`, chẳng hạn `ns-xxxx.awsdns-yy.com` thuộc zone thật. Trên Windows có thể dùng:

~~~powershell
nslookup -type=A www.example.com
nslookup -type=NS example.com
~~~

Phân biệt kết quả khi hỏi **authoritative NS** và **recursive resolver**. Nếu Route 53 trả record mới nhưng người dùng vẫn thấy record cũ, thường cần kiểm tra delegation, TTL/cache hoặc DNS views.

## 12. AWS CLI: cấu trúc một change batch

Route 53 dùng API `ChangeResourceRecordSets` với danh sách thay đổi trong một batch:

- `CREATE`: tạo record set mới, lỗi nếu record set cùng định danh đã tồn tại.
- `UPSERT`: tạo nếu chưa có hoặc thay record set đã tồn tại.
- `DELETE`: xóa record set có giá trị/thuộc tính đúng theo yêu cầu API; cần đọc hiện trạng trước để không xóa nhầm.

Một batch được Route 53 **xác minh trước và áp dụng theo cơ chế all-or-nothing** đối với batch đó; không thể coi đây là transaction cùng với tạo ALB/CloudFront hoặc các hệ thống ngoài DNS.

### 12.1. Ví dụ JSON minh họa record A

Giả sử bạn đã có hosted zone `example.com` với ID `Z012345EXAMPLE` và muốn tạo record `api.example.com`. Tệp `change-a.json` được chuẩn bị **trước** khi chạy thao tác thay đổi:

~~~json
{
  "Comment": "Illustration: update api.example.com for approved lab",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "api.example.com.",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          { "Value": "192.0.2.10" }
        ]
      }
    }
  ]
}
~~~

**Địa chỉ `192.0.2.10` là IP tài liệu, không phải backend thật**. Đây là ví dụ để đọc cấu trúc, không được dùng nguyên văn trong production.

Lệnh dưới đây **thực sự sửa DNS** nếu dùng file/zone/credentials hợp lệ; chỉ thực thi sau phê duyệt và kiểm tra rằng `UPSERT` không ghi đè record quan trọng:

~~~bash
aws route53 change-resource-record-sets \
  --hosted-zone-id Z012345EXAMPLE \
  --change-batch file://change-a.json \
  --profile dev
~~~

Response gồm `ChangeInfo.Id` và `Status` thường bắt đầu `PENDING`. Truy vấn trạng thái:

~~~bash
aws route53 get-change \
  --id /change/C012345EXAMPLE \
  --profile dev \
  --output json
~~~

Thay `/change/C012345EXAMPLE` bằng **ChangeInfo.Id thật**. Khi `INSYNC`, thay đổi đã tới authoritative name servers; client cache vẫn có thể chưa hết TTL.

### 12.2. Ví dụ cấu trúc alias đến ALB

Một record alias thay `TTL` và `ResourceRecords` bằng `AliasTarget`:

~~~json
{
  "Name": "api.example.com.",
  "Type": "A",
  "AliasTarget": {
    "HostedZoneId": "ELB_CANONICAL_HOSTED_ZONE_ID",
    "DNSName": "my-alb-123.ap-southeast-1.elb.amazonaws.com.",
    "EvaluateTargetHealth": true
  }
}
~~~

Đây là **`ResourceRecordSet` bên trong ChangeBatch**, không phải toàn bộ request. `HostedZoneId` trong `AliasTarget` là **canonical zone ID của ALB**, khác `Z012345EXAMPLE` đang quản lý `example.com`. Không đoán ID theo Region hoặc copy một ID ví dụ; lấy từ mô tả load balancer thực tế và tài liệu AWS.

### 12.3. Guardrails khi thay đổi DNS production

- Xác nhận đúng AWS account, zone ID, record Name/Type, policy, target, TTL.
- Đọc và xuất bản ghi hiện tại để chuẩn bị rollback; chú ý weighted/latency records có `SetIdentifier`.
- Với `UPSERT`, kiểm tra toàn bộ values của record set; không mặc định thao tác “thêm một giá trị” sẽ giữ các giá trị đang có.
- Với `DELETE`, phải gửi bộ thuộc tính tương ứng với record đang tồn tại; đọc lại trước khi xóa.
- Hạn chế quyền IAM theo hosted zone, record names/types/actions khi phù hợp; review IaC.
- Đợi `INSYNC` và thử truy vấn DNS; tiếp tục theo dõi ứng dụng và recursive cache.
- Không ghi thông tin nhạy cảm trong TXT records hoặc comment/commit log.

## 13. Private hosted zones và Route 53 Resolver trong AWS VPC

### 13.1. Một ví dụ nội bộ

Ứng dụng Spring Boot trong VPC App cần gọi gRPC API qua internal ALB ở VPC Shared. Nhóm có thể đặt `grpc.internal.example.com` trong private hosted zone `internal.example.com`, gắn PHZ với VPC App và VPC Shared theo quyền phù hợp. Những workload truy vấn qua Route 53 Resolver của các VPC đã association sẽ nhận DNS answer riêng.

**DNS không tạo IP network route.** Nếu VPC App không có đường network thực tới internal ALB ở VPC Shared (VPC peering, Transit Gateway, PrivateLink hoặc mô hình hợp lệ khác) thì hostname vẫn có thể phân giải nhưng TCP connection vẫn fail.

### 13.2. Cross-account PHZ association

Khi PHZ thuộc account DNS nhưng VPC ở account ứng dụng, một quy trình tiêu biểu:

1. Account sở hữu PHZ tạo **association authorization** cho VPC ID và Region của account kia.
2. Principal ở account sở hữu VPC gọi API để **associate VPC với hosted zone**, có quyền tương ứng.
3. Sau khi association thành công, có thể xóa authorization không còn cần thiết.
4. Kiểm tra VPC DNS attributes và khả năng phân giải từ một tài nguyên bên trong VPC.
5. Đưa luồng association vào IaC/runbook, tránh cấu hình mất kiểm soát.

AWS có các cơ chế quản lý chia sẻ DNS mới và các lưu ý với Route 53 Profiles/Resolver; quy trình trên mô tả **association trực tiếp truyền thống**. Không giả định chỉ vì account cùng một AWS Organization mà PHZ tự xuất hiện trong tất cả VPC.

### 13.3. Resolver inbound/outbound endpoints

Route 53 Resolver có thể hỗ trợ DNS hybrid:

- **Inbound Resolver endpoint:** DNS server on-premises gửi query vào môi trường VPC/AWS qua cấu hình mạng/DNS forwarding phù hợp để tra các tên private.
- **Outbound Resolver endpoint + forwarding rule:** VPC Resolver chuyển những domain được chỉ định về DNS servers on-premises.
- **Resolver rules/associations:** quyết định VPC nào dùng forwarding rules tương ứng.

Các endpoint tạo network interfaces, cần Security Groups, subnet/AZ, route và phí riêng. Chỉ tạo nếu có nhu cầu hybrid DNS rõ ràng; hệ thống chỉ dùng tên trong một VPC có thể đơn giản hơn với PHZ association.

### 13.4. Split-view và lỗi NXDOMAIN

Ví dụ public zone có `www.example.com`, private zone cùng tên `example.com` **không có** `www` record. Nếu một EC2 trong VPC association hỏi `www.example.com`, nó có thể nhận **NXDOMAIN** thay vì record public. Đây là lỗi phổ biến: người vận hành nghĩ “thiếu trong private thì tự lấy public” nhưng Resolver chọn private namespace đã khớp.

Giải pháp là định nghĩa đầy đủ record cần dùng trong private view, hoặc chỉ tạo PHZ với namespace hẹp như `corp.example.com` khi kiến trúc phù hợp. Cần kiểm tra cả resolver rule precedence và những hosted zones có namespace lồng nhau.

## 14. Bảo mật IAM, TLS và DNSSEC

### 14.1. IAM và thay đổi DNS

Thay đổi DNS có thể đổi đường tới hệ thống sản xuất hoặc làm gián đoạn email. Người quản trị không nhất thiết phải có `AdministratorAccess`. Có thể phân vai trò:

| Nhiệm vụ | IAM action thường liên quan |
|---|---|
| Liệt kê hosted zones | `route53:ListHostedZones`, `route53:ListHostedZonesByName` |
| Xem hosted zone và records | `route53:GetHostedZone`, `route53:ListResourceRecordSets` |
| Tạo/sửa/xóa records | `route53:ChangeResourceRecordSets` trên hosted zone được phép |
| Xem tiến trình đổi records | `route53:GetChange` |
| Tạo hosted zone | `route53:CreateHostedZone` |
| Associate VPC và PHZ | `route53:AssociateVPCWithHostedZone`, authorization APIs và quyền VPC liên quan |
| DNSSEC key signing | Các hành động Route 53 DNSSEC và AWS KMS phù hợp |

Có thể sử dụng IAM condition keys như `route53:ChangeResourceRecordSetsNormalizedRecordNames`, `route53:ChangeResourceRecordSetsRecordTypes` và `route53:ChangeResourceRecordSetsActions` để hạn chế một role chỉ được cập nhật các tên/type/action nhất định trong một hosted zone. Kết hợp MFA, IAM Identity Center, approval và IaC change review. Không cấp quyền tạo/sửa NS delegation cho developer không quản lý domain.

### 14.2. DNS và HTTPS là hai bài toán

Bản ghi DNS có thể dẫn tới đúng ALB nhưng HTTPS vẫn fail nếu:

- ACM certificate không chứa hostname mà client yêu cầu.
- ALB HTTPS listener dùng cert sai hoặc chưa cấu hình TLS.
- CloudFront chưa có alternate domain name/certificate tương ứng.
- Target group unhealthy, Security Group/NACL chặn port hoặc backend chưa start.
- Browser/Java client kiểm tra TLS/SNI và server trả cert cho domain khác.

Giải quyết theo lớp: **DNS resolution → TCP/TLS → load balancer → application**. Không tắt TLS verification để “sửa DNS”.

### 14.3. DNSSEC

**DNS Security Extensions (DNSSEC)** giúp validating resolvers kiểm tra chữ ký DNS, hạn chế một số kiểu giả mạo/can thiệp DNS data. Route 53 hỗ trợ **DNSSEC signing cho public hosted zones**, không hỗ trợ bật signing trực tiếp cho private hosted zones.

Quy trình mức cao:

1. Xác minh các điều kiện DNSSEC, name server và rollback.
2. Tạo/đăng ký **KSK** dựa trên asymmetric AWS KMS key theo yêu cầu AWS, bật signing cho hosted zone.
3. Lấy **DS record** từ Route 53.
4. Thêm DS vào **parent zone/registrar** phù hợp để tạo chain of trust.
5. Giám sát DNSSEC errors qua CloudWatch và xác nhận query resolution.

**Không bật DNSSEC và thêm DS tùy tiện trên production:** nếu DS ở parent sai hoặc key/signing gặp sự cố, validating resolvers có thể không trả được record và toàn domain có thể ngừng hoạt động. AWS khuyến nghị CloudWatch alarms như `DNSSECInternalFailure`, `DNSSECKeySigningKeysNeedingAction`. DNSSEC không mã hóa lưu lượng DNS và không bảo vệ HTTP nếu không có TLS.

## 15. Giám sát, khả năng phục hồi và chi phí

### 15.1. Giám sát

- **CloudTrail:** ghi các hoạt động control plane như `ChangeResourceRecordSets`, `CreateHostedZone` hoặc thay đổi cấu hình khi được log phù hợp; hỗ trợ truy vết actor và timestamp.
- **Route 53 query logging:** ghi DNS queries theo khả năng của public hosted zone hoặc Resolver query logging cho VPCs, với cơ chế đích log riêng; đánh giá chi phí và dữ liệu nhạy cảm trong domain names.
- **Route 53 health checks:** theo dõi endpoint public, các health checking options hoặc CloudWatch alarms; chỉ dùng với routing policy phù hợp.
- **CloudWatch metrics/alarms:** health check status, DNSSEC và metrics theo tính năng; so sánh với application HTTP 5xx/latency tại ALB/CloudFront.
- **Reachability/Application logs:** DNS có thể đúng nhưng TCP/HTTP vẫn thất bại; cần logs ở nhiều lớp.

### 15.2. Chi phí cần dự trù

Route 53 có phí cho **hosted zone theo tháng** và **DNS queries** theo chính sách định giá, ngoài domain registration/renewal. Các tính năng như health checks, Resolver endpoints/query logging và một số traffic policies có thể phát sinh phí riêng.

| Hạng mục | Ví dụ phát sinh |
|---|---|
| Public/private hosted zone | Số hosted zones đang tồn tại, kể cả zone chưa được delegate |
| Standard/advanced DNS queries | Số lượng truy vấn và loại policy |
| Alias record tới AWS resource | Một số loại alias queries được miễn phí Route 53 theo quy tắc giá |
| Health checks | Số checks, cấu hình interval/feature |
| Route 53 Resolver endpoints | Giờ endpoint và số truy vấn theo biểu phí |
| Domain registration | Gia hạn hàng năm, độc lập với hosted zone |
| ALB/CloudFront/S3/EC2 | Dịch vụ nhận request tính phí riêng theo sử dụng |

Không mặc định “record mới không có phí”: query volume, số hosted zone, health check và dịch vụ đích ảnh hưởng tổng chi phí. Kiểm tra giá ở đúng thời điểm/Region/tính năng tại [Amazon Route 53 Pricing](https://aws.amazon.com/route53/pricing/) trước khi chốt thiết kế.

### 15.3. DR và ranh giới DNS

DNS failover có thể hướng các **kết nối mới** tới endpoint khác nhưng không chuyển trạng thái cơ sở dữ liệu. Để phục hồi ứng dụng Java qua Region, cần backup/replication dữ liệu, IAM roles, secrets, container images, network routes, ALB target health, TLS certificates và quy trình kiểm thử. DNS chỉ là một thành phần của failover.

## 16. Sự cố thường gặp và thứ tự chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/xử lý |
|---|---|---|
| Có record trong Route 53 nhưng Internet không resolve | Registrar/parent chưa delegate tới NS của zone đó | `dig NS`, đối chiếu NS tại registrar, zone ID và delegation chain |
| Có hai hosted zones cùng tên, query thấy record cũ | Đang sửa nhầm zone chưa được delegate | So sánh từng zone ID, NS set và parent delegation |
| `NXDOMAIN` ngay sau khi tạo record mới | Negative cache hoặc record chưa xuất hiện tại authoritative NS | Hỏi authoritative NS, kiểm tra SOA/negative TTL và kết quả `GetChange` |
| `INSYNC` nhưng người dùng vẫn vào IP cũ | Recursive/browser/JVM/proxy DNS cache vẫn còn TTL | Đo từ nhiều resolver, giữ backend cũ đủ thời gian |
| `api.example.com` trả CNAME khác kỳ vọng | Record alias/CNAME/policy khác, DNS view hoặc resolver cache | Dùng `dig A/AAAA/CNAME`, đọc record set/type/target |
| Apex `example.com` không tạo được CNAME | DNS cấm CNAME ở zone apex | Dùng Route 53 alias A/AAAA tới target hỗ trợ |
| Alias ALB trả lỗi khi tạo | Dùng sai `AliasTarget.HostedZoneId` hoặc DNSName/Region | Lấy CanonicalHostedZoneId từ ELB target thật |
| DNS đúng IP nhưng HTTPS cert lỗi | ACM/CloudFront/ALB hostname & TLS certificate chưa khớp | Kiểm tra certificate, listener, alternate domain names |
| Private DNS chỉ hoạt động ở VPC A | VPC B chưa association PHZ hoặc DNS attributes không đúng | Kiểm tra VPC association, `enableDnsSupport`/`enableDnsHostnames` |
| VPC đã peering nhưng tên PHZ không resolve | Peering không tự chia sẻ PHZ | Associate PHZ với VPC khác hoặc dùng Resolver forwarding |
| PHZ trùng public zone, thiếu vài record | Split-view không fallback public cho private zone đã khớp | Tạo record cần thiết trong private view/tách namespace |
| Failover không chuyển kịp | Health check sai, endpoint chưa unhealthy, DNS caches còn TTL | Kiểm tra `GetHealthCheckStatus`, routing policy và client TTL |
| Weighted 10% nhưng HTTP traffic không đúng 10% | DNS weights tác động tới answers, resolver cache/client behavior | Đo query/HTTP riêng; dùng rollout L7 nếu cần tỷ lệ request |
| DNS thay đổi đột ngột sau deploy | IaC/automation/manual ghi đè record | Xem CloudTrail, change sets và pipeline history |
| DNSSEC gây `SERVFAIL` tại validating resolver | Sai DS/KSK hoặc chain of trust/signing | Kiểm tra DNSSEC/CloudWatch và runbook rollback |
| Đã xóa hosted zone nhưng domain lỗi | Xóa zone trước khi chuyển delegation hoặc làm mất records | Khôi phục theo NS/record plan và thao tác registrar thích hợp |

### 16.1. Quy trình bốn lớp

1. **Tên DNS:** client hỏi hostname/type gì, ở public hay private view?
2. **Ủy quyền/authoritative:** parent trỏ NS nào, đúng zone ID, record có tồn tại trên authoritative server?
3. **Cache và policy:** TTL, negative caching, weighted/failover health và `GetChange` có ảnh hưởng?
4. **Đích ứng dụng:** IP/ALB/CloudFront có network path, TLS, health, authentication, backend readiness không?

Cách làm này giúp tránh sửa Security Group khi nguyên nhân nằm ở registrar, hoặc sửa record DNS khi ứng dụng đang trả lỗi 500.

## 17. Bài thực hành chỉ đọc: đối chiếu record và delegation

### 17.1. Điều kiện

Có AWS account học tập, AWS CLI v2 profile `dev` với quyền xem hosted zones/records và một public hosted zone được phép đọc. Không cần đăng ký domain mới hoặc thay đổi production. Nếu chưa có zone, sử dụng ví dụ `example.com` để phân tích cấu trúc.

### 17.2. Bước A — Xác định account

~~~bash
aws sts get-caller-identity --profile dev --output json
aws route53 list-hosted-zones-by-name \
  --dns-name example.com \
  --profile dev \
  --output json
~~~

Ghi account ID, zone ID và `Config.PrivateZone`. Nếu không có zone, không tự tạo chỉ để có dữ liệu; có thể phân tích JSON minh họa.

### 17.3. Bước B — Đọc NS/SOA và bản ghi ứng dụng

~~~bash
aws route53 get-hosted-zone \
  --id Z012345EXAMPLE \
  --profile dev

aws route53 list-resource-record-sets \
  --hosted-zone-id Z012345EXAMPLE \
  --profile dev \
  --output json
~~~

Thay zone ID placeholder bằng ID được cấp. Tìm `NS`, `SOA`, `A`, `AAAA`, `CNAME`, `MX`, `TXT`. Với alias record, xem `AliasTarget`; đối với standard record, xem `TTL` và `ResourceRecords`.

### 17.4. Bước C — So sánh Route 53 với recursive resolver

Nếu zone là **public** và đã được delegate, so sánh:

~~~bash
# Tra cứu qua DNS resolver mặc định
dig NS example.com
dig A api.example.com

# Thử câu trả lời trực tiếp của Route 53 cho zone được cấp
aws route53 test-dns-answer \
  --hosted-zone-id Z012345EXAMPLE \
  --record-name api.example.com \
  --record-type A \
  --profile dev
~~~

Trả lời: NS ở parent có trùng delegation set của zone không? Nếu `TestDNSAnswer` có dữ liệu nhưng `dig` không, bạn sẽ kiểm tra delegation hay cache trước?

### 17.5. Bước D — Chọn record phù hợp

| Nhu cầu | Thiết kế DNS đề xuất | Lưu ý |
|---|---|---|
| Root `example.com` vào CloudFront | `A` alias, và `AAAA` alias khi dùng IPv6 | Cần alternate domain/certificate đúng |
| `api.example.com` vào ALB | `A` alias, `AAAA` tùy IPv6 | AliasTarget canonical hosted zone ID của ALB |
| `www.example.com` vào root | CNAME hoặc alias hợp lệ | Không đặt CNAME ở apex |
| Gửi email cho `example.com` | `MX` + các `TXT` cần thiết | Lấy config thật từ email provider |
| Tên internal `db.internal.example.com` | PHZ và association VPC | DNS chỉ phân giải; RDS credentials/SG vẫn cần |
| Chuyển dần version v1/v2 | Weighted records | DNS weight không đảm bảo chính xác HTTP request ratio |
| Định tuyến dự phòng 2 Region | Failover records/health | Cần DR dữ liệu và TTL/cache strategy |

### 17.6. Bước E — Thiết kế kế hoạch chuyển DNS

Giả sử muốn chuyển `api.example.com` sang ALB mới lúc 10:00 ngày triển khai:

1. Kiểm tra authoritative zone, NS delegation và record TTL hiện tại.
2. Lên lịch giảm TTL **đủ sớm**, không đợi đến lúc cutover.
3. Chuẩn bị ALB/ACM/target health, chạy test HTTPS qua endpoint kiểm thử.
4. Thực hiện change batch qua IaC/approved workflow.
5. Chờ `INSYNC`, kiểm tra authoritative/recursive resolvers và HTTP success rate.
6. Giữ backend cũ đủ lâu cho client caches; có rollback record và runbook nếu lỗi.

## 18. Câu hỏi tự kiểm tra

1. Vì sao tạo hosted zone public có cùng tên với domain đang đăng ký vẫn không khiến người dùng thấy record mới?
2. Bốn name servers do Route 53 cấp cho một zone phục vụ mục đích gì? Nằm ở đâu trong delegation?
3. Private hosted zone có cần đặt NS tại registrar để EC2 cùng VPC phân giải không?
4. Điều kiện VPC DNS nào phải bật khi sử dụng private hosted zone?
5. Nếu private và public hosted zones cùng tên, private zone khớp truy vấn nhưng không có record thì resolver có tự fallback public không?
6. Vì sao không đặt `CNAME` tại `example.com` nhưng có thể dùng alias `A`?
7. Alias record tới ALB cần hai thông tin đích nào? Vì sao target HostedZoneId khác zone ID của domain?
8. Có thể suy HTTP request ratio chính xác từ weighted DNS 90/10 không?
9. Phân biệt `PENDING/INSYNC` và TTL ở recursive resolver.
10. Vì sao một health check không bảo đảm toàn bộ người dùng chuyển sang secondary trong vài giây?
11. Lệnh AWS CLI nào liệt kê record sets của một zone? Lệnh nào trả trạng thái một change batch?
12. `TestDNSAnswer` có dùng để kiểm thử trực tiếp private hosted zone không?
13. Bản ghi `MX`/`TXT` có thể ảnh hưởng hệ thống nào ngoài website?
14. Khi domain đã resolve đúng ALB nhưng trình duyệt báo lỗi certificate, cần kiểm tra gì?
15. Tại sao DNSSEC signing cho public zone cần DS record trong parent/registrar?
16. Những khoản phí nào còn tồn tại ngay cả khi public hosted zone chưa được ai truy vấn?

### Định hướng đáp án

Năng lực đạt yêu cầu là biết kiểm tra theo thứ tự **registrar/delegation → hosted zone/record → TTL/cache/routing policy → endpoint/TLS/application**, chọn đúng kiểu record, không nhầm DNS control plane với lưu lượng application, và có kế hoạch thay đổi/giám sát/rollback.

## 19. Tài liệu chính thức

1. [What is Amazon Route 53?](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Welcome.html) — DNS, domain registration, health checking.
2. [Working with public hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zones-working-with.html) — Tạo và quản lý public hosted zones.
3. [Considerations when working with public hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zone-public-considerations.html) — NS/SOA và các zone trùng tên.
4. [Working with private hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zones-private.html) — VPC association và private DNS.
5. [Considerations for private hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zone-private-considerations.html) — Split-view DNS và no-fallback behavior.
6. [Choosing between alias and non-alias records](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resource-record-sets-choosing-alias-non-alias.html) — Alias, CNAME và apex.
7. [DNS record types](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/ResourceRecordTypes.html) — A/AAAA/CNAME/MX/TXT/CAA và các types khác.
8. [Choosing a routing policy](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html) — Simple, weighted, latency, failover và các chính sách.
9. [How Route 53 chooses records when health checking is configured](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html) — Health-based routing caveats.
10. [AWS CLI route53 list-resource-record-sets](https://docs.aws.amazon.com/cli/latest/reference/route53/list-resource-record-sets.html) — Đọc record sets và phân trang.
11. [AWS CLI route53 change-resource-record-sets](https://docs.aws.amazon.com/cli/latest/reference/route53/change-resource-record-sets.html) — Change batch và record mutations.
12. [Route 53 GetChange API](https://docs.aws.amazon.com/Route53/latest/APIReference/API_GetChange.html) — `PENDING` và `INSYNC`.
13. [Route 53 TestDNSAnswer API](https://docs.aws.amazon.com/Route53/latest/APIReference/API_TestDNSAnswer.html) — Kiểm tra public DNS answer.
14. [DNSSEC signing in Route 53](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-configuring-dnssec.html) — KSK/DS và các lưu ý vận hành.
15. [Route 53 pricing and billing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/Route53Pricing.html) — Hosted zone/query/health costs.
16. [Amazon VPC DNS concepts](https://docs.aws.amazon.com/vpc/latest/userguide/AmazonDNS-concepts.html) — Resolver, VPC DNS attributes và private names.

> **Ghi nhớ:** **Hosted zone** lưu các bản ghi, **NS delegation** xác định zone nào đang có thẩm quyền, **TTL/cache** quyết định thời gian nhận thay đổi, còn **routing policy** chọn câu trả lời DNS. Với ứng dụng AWS, hãy xác minh DNS cùng với ALB/CloudFront/VPC, TLS, IAM, health monitoring, DR và chi phí trước khi đưa bản ghi vào production.

