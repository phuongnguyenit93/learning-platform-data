# DNS enumeration: Khám phá tài sản mạng thông qua DNS

## 1. DNS enumeration là gì và dùng để làm gì?

**DNS enumeration** là quá trình thu thập, đối chiếu và phân tích các thông tin liên quan đến một miền DNS (domain): tên miền con (subdomain), bản ghi DNS, máy chủ phân giải, hạ tầng thư điện tử, dịch vụ được công bố và những mối quan hệ giữa tên với tài nguyên mạng. Đây là một phần của giai đoạn **reconnaissance** (trinh sát/khảo sát) trong đánh giá an toàn mạng.

DNS là hệ thống phân giải tên phân tán. Một tổ chức có thể dùng tên như **vpn.corp.example.test**, **app.corp.example.test** hay **mail.corp.example.test** để kết nối đến dịch vụ, nhưng một bản ghi tên miền không trực tiếp chứng minh rằng dịch vụ đó đang chạy, có thể truy cập từ mọi mạng hoặc thuộc quyền quản trị của tổ chức. DNS enumeration nhằm hình thành **giả thuyết có bằng chứng** về những tài sản có liên quan, sau đó kiểm chứng với chủ sở hữu và các nguồn inventory được phép.

Trong module **SECURITY_NETWORK_SECURITY**, kết quả DNS enumeration có ích cho:

- **Kiểm kê bề mặt tiếp xúc:** phát hiện miền con, dịch vụ và đường vào có thể chưa được ghi vào danh mục tài sản.
- **Threat modeling:** nhận diện tài sản cần bảo vệ, vùng tin cậy, mối phụ thuộc vào DNS, nhà cung cấp đám mây và dịch vụ định danh.
- **Đánh giá cấu hình bảo vệ:** phát hiện bản ghi cũ, hostname vô tình công bố, cấu hình zone transfer quá rộng hoặc tài nguyên DNS tham chiếu tới dịch vụ đã ngừng dùng.
- **Giám sát và ứng cứu:** lập đường cơ sở để so sánh thay đổi DNS, điều tra chuyển hướng sai, phân giải bất thường hoặc dấu hiệu DNS bị lạm dụng.
- **Thiết kế kiến trúc an toàn:** đối chiếu thông tin DNS với phân đoạn mạng, firewall, VPN, IDS/IPS, bảo vệ Wi-Fi và cloud networking.

**Mục tiêu học tập:** phân biệt được các phương pháp thu thập DNS thụ động và chủ động; đọc, diễn giải các bản ghi quan trọng; thực hiện truy vấn có kiểm soát; giải thích giới hạn của dữ liệu DNS; và chuyển kết quả thành hành động bảo vệ mạng.

> **Phạm vi thao tác:** các lệnh thực hành trong bài dùng miền mô phỏng **corp.example.test** và địa chỉ tài liệu **192.0.2.53**. Miền **.test** và dải **192.0.2.0/24** dành cho ví dụ, không biểu thị một máy chủ DNS thực trên Internet. Để chạy được, cần cấu hình DNS riêng trong phòng lab hoặc thay bằng hệ thống đã được cho phép kiểm tra. Với hoạt động khám phá chủ động, phải xác định phạm vi, người phê duyệt và giới hạn lưu lượng.

## 2. Kiến thức DNS nền tảng cần nắm

### 2.1. Một truy vấn DNS đi qua đâu?

Khi ứng dụng cần truy cập một tên miền, **stub resolver** trên máy người dùng thường gửi yêu cầu đến **recursive resolver** đã cấu hình. Recursive resolver có thể trả lời từ cache hoặc truy vấn các máy chủ **authoritative** theo hệ phân cấp DNS. Authoritative nameserver là nguồn có thẩm quyền cho zone tương ứng; recursive resolver thay mặt client tìm câu trả lời.

~~~mermaid
flowchart LR
    C["Ứng dụng / stub resolver"] --> R["Recursive resolver"]
    R -. "Cache nếu có" .-> R
    R --> ROOT["Root DNS"]
    ROOT --> TLD["Nameserver miền cấp cao"]
    TLD --> AUTH["Authoritative nameserver của zone"]
    AUTH --> R
    R --> C
~~~

Sơ đồ mô tả quá trình phân giải tổng quát khi chưa có câu trả lời phù hợp trong cache. Trong thực tế, resolver có thể tối ưu, dùng forwarder, áp dụng DNSSEC validation hoặc thực hiện **QNAME minimization**. Một số hệ thống dùng **split-horizon/split-view DNS**: cùng một tên có thể cho kết quả khác nhau khi truy vấn từ mạng nội bộ, VPN hay Internet.

### 2.2. Cấu trúc tên miền và zone

Với tên **api.prod.corp.example.test**:

- **example.test** là miền cha trong ví dụ; **corp.example.test** có thể là một zone được quản trị riêng.
- **prod** và **api** tạo các cấp nhãn (labels) của tên đầy đủ.
- **FQDN (Fully Qualified Domain Name)** là tên DNS đầy đủ. Trong cú pháp DNS, dấu chấm cuối như **api.prod.corp.example.test.** biểu thị tên tuyệt đối; nhiều công cụ tự bổ sung dấu chấm này.
- **Subdomain** không nhất thiết tương ứng một máy chủ độc lập. Một subdomain có thể trỏ đến load balancer, CDN, nhiều địa chỉ, một CNAME hoặc không có bản ghi địa chỉ.
- **Delegation** là việc zone cha ủy quyền phần không gian tên cho các nameserver của zone con, thường thể hiện qua bản ghi **NS**.

**DNS zone** là đơn vị dữ liệu được một nhóm authoritative nameserver phục vụ. **Domain** là tên trong hệ phân cấp. Trong thực tế, một domain có thể trải qua nhiều zone do delegation, vì vậy không thể suy rằng một zone file chứa tất cả subdomain của tổ chức.

### 2.3. Các loại bản ghi thường được khảo sát

| Loại bản ghi | Chức năng chính | Giá trị đối với reconnaissance và bảo mật |
|---|---|---|
| **A** | Tên → địa chỉ IPv4 | Liệt kê điểm đích IPv4 và đối chiếu với tài sản, firewall, cloud |
| **AAAA** | Tên → địa chỉ IPv6 | Phát hiện mặt tiếp xúc IPv6 có thể bị bỏ sót nếu chỉ kiểm tra IPv4 |
| **CNAME** | Bí danh → tên chuẩn khác | Nhận diện chuỗi phụ thuộc, CDN/SaaS, bản ghi còn trỏ tới dịch vụ cũ |
| **NS** | Nameserver có thẩm quyền cho zone/ủy quyền | Xác định nơi quản trị DNS và các zone được giao cho bên khác |
| **SOA** | Thông tin quản lý zone, serial, timers | Hỗ trợ xác nhận zone và so sánh trạng thái vận hành; không tự cung cấp toàn bộ bản ghi |
| **MX** | Máy chủ nhận thư của miền | Xác định nhà cung cấp/dịch vụ email và phụ thuộc cần bảo vệ |
| **TXT** | Dữ liệu văn bản; thường dùng SPF, xác minh sở hữu, DMARC, DKIM... | Hiểu cấu hình email, quan hệ nhà cung cấp; tránh coi mọi TXT là dữ liệu nhạy cảm |
| **SRV** | Chỉ định tên máy, cổng và độ ưu tiên của dịch vụ | Có thể hé lộ tên dịch vụ được đăng ký (VD: LDAP, SIP, Kerberos) |
| **PTR** | Ánh xạ ngược từ địa chỉ IP sang tên | Bổ sung manh mối về mục đích IP; không khẳng định quan hệ sở hữu |
| **CAA** | Giới hạn CA được phép phát hành chứng chỉ theo chính sách DNS | Hỗ trợ rà soát chính sách chứng chỉ và phạm vi tên miền |
| **DS, DNSKEY, RRSIG, NSEC/NSEC3** | Các thành phần DNSSEC | Kiểm tra ký xác thực và cách công bố bằng chứng không tồn tại |
| **HTTPS, SVCB** | Thông tin binding và tham số kết nối dịch vụ | Có thể cho biết endpoint/đặc tính kết nối; cần công cụ hỗ trợ loại bản ghi này |

**Lưu ý quan trọng:** DNS **không phải sơ đồ hạ tầng đầy đủ**. Một địa chỉ IP có thể phục vụ nhiều tên nhờ virtual hosting; một tên có thể có nhiều địa chỉ do cân bằng tải; DNS nội bộ có thể không hiển thị công khai. Bản ghi cũng có thể tồn tại khi dịch vụ đã ngừng.

## 3. Phương pháp thụ động và chủ động

### 3.1. Thu thập thụ động (passive enumeration)

**Passive enumeration** chủ yếu khai thác thông tin đã được hệ thống khác công bố hoặc lưu trữ, không chủ động gửi hàng loạt truy vấn đến hạ tầng đích. Các nguồn tham khảo có thể gồm:

1. **Certificate Transparency (CT) logs:** tên xuất hiện trong chứng chỉ TLS được ghi nhận công khai. Có thể hữu ích để tìm các hostname từng dùng HTTPS.
2. **Passive DNS và lịch sử DNS:** quan hệ tên/IP và thời gian quan sát từ bên cung cấp dữ liệu; cần xét độ mới, phạm vi thu thập, độ tin cậy và điều kiện sử dụng.
3. **RDAP/registry và thông tin tên miền công khai:** nhà đăng ký, nameserver, thời gian và một số thông tin quản lý; dữ liệu cá nhân có thể bị ẩn.
4. **Tài liệu, repository, sơ đồ mạng công khai và thông tin nhà cung cấp:** tên endpoint đôi khi xuất hiện trong hướng dẫn kết nối hoặc cấu hình mẫu.
5. **Nguồn nội bộ được cho phép:** CMDB, IPAM, nhật ký phân giải DNS, cấu hình cloud DNS, IaC và danh sách chứng chỉ. Đây là nguồn đối chiếu có giá trị đối với đội vận hành.

Ví dụ, một hostname **old-api.corp.example.test** có thể xuất hiện trong CT nhưng hiện không còn phân giải. Điều đó chỉ cho biết tên **đã từng xuất hiện trong dữ liệu chứng chỉ**; chưa đủ bằng chứng kết luận hệ thống đang tồn tại hay còn thuộc quyền kiểm soát.

**Ưu điểm:** tạo danh sách ban đầu ít gây ảnh hưởng đến hệ thống đang chạy; có thể tìm được tên đã từng tồn tại. **Hạn chế:** dữ liệu dễ cũ, không đầy đủ; nhiều tài sản không có chứng chỉ công khai; tên trong chứng chỉ có thể do bên khác yêu cầu cấp hoặc do cấu hình lịch sử.

### 3.2. Thu thập chủ động (active enumeration)

**Active enumeration** gửi truy vấn tới DNS resolver hoặc authoritative nameserver, có thể kiểm tra:

- Bản ghi hiện trả lời cho một FQDN đã biết.
- Cấu hình và máy chủ có thẩm quyền của zone.
- Các tên con ứng viên từ danh sách có giới hạn.
- Khả năng truy vấn theo IPv4/IPv6, sự khác nhau giữa DNS nội bộ và DNS bên ngoài.
- Những trường hợp trả lời khác nhau như **NOERROR**, **NXDOMAIN**, **SERVFAIL**, **REFUSED**.
- Chính sách **zone transfer (AXFR)** trong môi trường được phép.

**Ưu điểm:** thấy phản hồi DNS hiện tại từ vị trí truy vấn, có thể kiểm chứng bản ghi trực tiếp. **Hạn chế:** chịu ảnh hưởng của cache, ACL, split-view, wildcard, giới hạn tốc độ, resolver và tuyến mạng; có thể sinh nhật ký hoặc tải trên hệ thống đích.

### 3.3. Phân biệt “truy vấn DNS” với “thấy dịch vụ hoạt động”

| Quan sát | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Tên có bản ghi A/AAAA | DNS đang trả về địa chỉ tại thời điểm và vị trí truy vấn | Máy chủ còn chạy, cổng dịch vụ đang mở hoặc có quyền truy cập |
| Tên có CNAME tới nhà cung cấp cloud | Có phụ thuộc vào tên đích trong chuỗi phân giải | Tài khoản/ứng dụng nhà cung cấp vẫn thuộc tổ chức |
| Tên xuất hiện trong CT log | Tên từng nằm trong chứng chỉ được ghi log | Tên hiện tồn tại hoặc cấu hình đang an toàn |
| MX trỏ đến dịch vụ email ngoài | Miền công bố điểm nhận thư theo DNS | Toàn bộ email được bảo vệ đúng chính sách hoặc đang gửi/nhận thành công |
| PTR trả về hostname | Có dữ liệu reverse DNS do bên quản lý reverse zone công bố | Hostname đó thật sự có ứng dụng cụ thể hay thuộc cùng chủ thể |
| DNS trả NXDOMAIN | Tên được truy vấn không tồn tại theo phản hồi nhận được trong ngữ cảnh đó | Tên chưa từng tồn tại hoặc chắc chắn không tồn tại trong DNS nội bộ |

Mỗi nhận định nên đi kèm **thời điểm**, **nguồn truy vấn**, **resolver**, **loại bản ghi** và **bằng chứng**.

## 4. Quy trình DNS enumeration có kiểm soát

~~~mermaid
flowchart TD
    S["Xác định phạm vi và tài sản nghiệp vụ"] --> P["Thu thập nguồn thụ động / inventory"]
    P --> N["Chuẩn hóa và loại trùng FQDN"]
    N --> A["Truy vấn DNS chủ động trong phạm vi"]
    A --> W{"Có wildcard, split-view, cache hoặc lỗi? "}
    W -- "Có" --> V["Kiểm tra lại bằng chứng từ nhiều vị trí/nguồn"]
    W -- "Không" --> E["Ghi lại bản ghi và quan hệ phụ thuộc"]
    V --> E
    E --> R["Đối chiếu chủ sở hữu và phân loại rủi ro"]
    R --> H["Khuyến nghị kiểm soát / giám sát DNS"]
~~~

### Bước 1: Chốt phạm vi, vị trí quan sát và giới hạn

Ghi rõ zone được phép khảo sát, mạng truy vấn, những nameserver có thể sử dụng, loại hoạt động cho phép, ngưỡng lưu lượng, thời gian kiểm tra và cách báo cáo sự cố. Ví dụ trong phòng lab: chỉ **corp.example.test**, nameserver **192.0.2.53**, thực hiện truy vấn tuần tự ở tốc độ thấp. Không suy rằng được phép kiểm tra mọi domain liên quan đến một nhà cung cấp, đối tác hoặc một dịch vụ SaaS.

### Bước 2: Tạo danh sách tên và dữ liệu ban đầu

Ưu tiên FQDN đã có trong inventory, chứng chỉ, cấu hình được kiểm soát hoặc danh sách ứng dụng do chủ sở hữu xác nhận. Bổ sung các tên ứng viên có ý nghĩa theo quy ước môi trường như **www**, **api**, **vpn**, **mail**, **dns**, **portal** hoặc **staging**. Mọi tên ứng viên cần được ghi nguồn; không coi tên vừa đoán là tài sản đã phát hiện.

### Bước 3: Truy vấn bản ghi và trạng thái phản hồi

Truy vấn các loại bản ghi phù hợp; với kết quả không rõ, so sánh recursive resolver và authoritative nameserver được phép, đồng thời xem mã phản hồi thay vì chỉ nhìn địa chỉ. Duy trì log của câu hỏi, kết quả, thời điểm và nguồn.

### Bước 4: Kiểm tra sai lệch và loại tín hiệu giả

Đối chiếu kết quả từ tên ngẫu nhiên để phát hiện wildcard; ghi lại CNAME chain, cấu hình split-view, DNS cache và các tên có AAAA nhưng không có A. Kiểm tra hostname hợp lệ với CMDB, cloud inventory, chủ sở hữu dịch vụ và chính sách công bố.

### Bước 5: Liên kết kết quả với rủi ro

Đặt câu hỏi **tên nào phơi lộ dịch vụ quản trị?**, **có bản ghi cũ hoặc chưa có người sở hữu?**, **zone transfer có giới hạn?**, **dịch vụ phụ thuộc tên của bên thứ ba?**, **mạng nội bộ có bị công bố không cần thiết?**. Với từng phát hiện, lưu bằng chứng và hướng kiểm chứng trước khi khuyến nghị thay đổi.

## 5. Thực hành truy vấn DNS với dig

**dig** (Domain Information Groper) có mặt trên nhiều hệ thống Linux/macOS hoặc có thể cài bổ sung. Trong ví dụ dưới đây, giả định lab đã cấu hình authoritative DNS tại **192.0.2.53** và zone **corp.example.test**. Không có lab thì các lệnh có thể timeout; đó không phải bằng chứng về lỗi cấu hình DNS trên Internet.

### 5.1. Đọc A, AAAA, CNAME

~~~bash
# Đọc địa chỉ IPv4 của ứng dụng
dig @192.0.2.53 app.corp.example.test A +noall +comments +answer

# Đọc địa chỉ IPv6, kể cả khi đã có A
dig @192.0.2.53 app.corp.example.test AAAA +noall +comments +answer

# Kiểm tra một bí danh
dig @192.0.2.53 portal.corp.example.test CNAME +noall +comments +answer

# Truy vấn tên tuyệt đối (dấu chấm kết thúc FQDN)
dig @192.0.2.53 vpn.corp.example.test. A +noall +comments +answer
~~~

Giả định lab trả về:

~~~text
app.corp.example.test.    300  IN A     192.0.2.20
app.corp.example.test.    300  IN AAAA  2001:db8::20
portal.corp.example.test. 300  IN CNAME app.corp.example.test.
~~~

Trong mỗi dòng, **300** là TTL (giây), **IN** là lớp Internet, **A/AAAA/CNAME** là loại record và giá trị sau cùng là **RDATA**. Địa chỉ **192.0.2.20** và **2001:db8::20** được dành cho minh họa, không phải endpoint thực. TTL là tham số cache của bản ghi; không đảm bảo rằng mọi resolver sẽ trả đúng cùng một giá trị TTL tại mọi thời điểm.

Nếu một tên trả về CNAME, tiếp tục xem chuỗi trỏ tới đâu và có được kiểm soát hay không. Đừng mặc định một CNAME trỏ đến SaaS/CDN là một lỗ hổng; đó mới là dấu hiệu cần kiểm tra quyền sở hữu và tình trạng cung cấp dịch vụ.

### 5.2. Xác định NS, SOA và cấu hình zone

~~~bash
# Các nameserver được công bố cho zone
dig @192.0.2.53 corp.example.test NS +noall +comments +answer

# Bản ghi Start of Authority
dig @192.0.2.53 corp.example.test SOA +noall +comments +answer

# Kiểm tra trực tiếp authoritative server với recursion disabled
dig @192.0.2.53 corp.example.test SOA +norecurse +noall +comments +answer
~~~

Ví dụ phản hồi SOA:

~~~text
corp.example.test. 3600 IN SOA ns1.corp.example.test. hostmaster.corp.example.test. (
    2026112801  ; serial
    3600        ; refresh
    900         ; retry
    1209600     ; expire
    300         ; minimum / negative caching field
)
~~~

**SOA serial** giúp so sánh phiên bản zone theo quy trình quản trị DNS, nhưng cách đặt serial phụ thuộc nhà vận hành; không mặc định mọi serial là ngày tháng. **MNAME/RNAME** trong SOA là thông tin quản trị được công bố, không phải danh sách đầy đủ các máy chủ/dịch vụ. Trong DNS hiện đại, trường **minimum** dùng trong cơ chế TTL của negative caching theo quy định liên quan, không phải đơn giản là “TTL tối thiểu cho mọi record”.

### 5.3. Kiểm tra MX, TXT, CAA và bản ghi dịch vụ

~~~bash
# Máy chủ nhận thư của zone
dig @192.0.2.53 corp.example.test MX +noall +comments +answer

# Các TXT records ở apex
dig @192.0.2.53 corp.example.test TXT +noall +comments +answer

# Chính sách DMARC (nếu zone sử dụng email)
dig @192.0.2.53 _dmarc.corp.example.test TXT +noall +comments +answer

# Quy tắc CA được phép phát hành chứng chỉ
dig @192.0.2.53 corp.example.test CAA +noall +comments +answer

# Bản ghi dịch vụ trong lab (nếu có)
dig @192.0.2.53 _ldap._tcp.corp.example.test SRV +noall +comments +answer

# SVCB/HTTPS ở endpoint phù hợp, nếu server và dig hỗ trợ
dig @192.0.2.53 app.corp.example.test HTTPS +noall +comments +answer
~~~

SPF thường được công bố dưới dạng **TXT** và mô tả nguồn gửi email được ủy quyền theo chính sách; **DMARC** công bố chính sách xử lý/xác thực email ở tên bắt đầu bằng **_dmarc**. **DKIM** sử dụng bản ghi TXT theo selector, thường dưới dạng **selector._domainkey.example**. Không thể liệt kê toàn bộ selector DKIM chỉ bằng một truy vấn TXT ở apex. Cũng không nên suy rằng có SPF/DMARC nghĩa là toàn bộ hệ thống email đã an toàn.

Bản ghi **SRV** gồm priority, weight, port và target. Nó có thể chỉ ra nơi cung cấp dịch vụ, nhưng chỉ có ý nghĩa khi ứng dụng/giao thức sử dụng SRV và tên truy vấn đúng. Một hệ thống không có SRV không có nghĩa là dịch vụ tương ứng không tồn tại.

### 5.4. Reverse DNS (PTR)

~~~bash
# Tra ngược địa chỉ đã biết trong lab
dig @192.0.2.53 -x 192.0.2.20 +noall +comments +answer
~~~

Reverse DNS sử dụng cây tên **in-addr.arpa** đối với IPv4 và **ip6.arpa** đối với IPv6. Thông tin PTR có thể hữu ích khi rà soát log, định danh tài sản hoặc liên hệ đầu mối vận hành. Tuy nhiên, reverse zone có thể thuộc ISP/nhà cung cấp cloud; một hostname PTR không phải bằng chứng pháp lý về quyền sở hữu IP và không xác nhận dịch vụ ở địa chỉ đó đang hoạt động.

### 5.5. Xem RCODE: không trả record chưa chắc là không tồn tại

Khi phân tích, sử dụng tùy chọn giữ phần **comments/status** để đọc phản hồi DNS:

~~~bash
dig @192.0.2.53 nonexistent.corp.example.test A +noall +comments +answer
~~~

| Trạng thái/hiện tượng | Diễn giải đúng |
|---|---|
| **NOERROR** có answer | Có phản hồi cho loại record được hỏi; phải xem tên, loại và RDATA thực tế |
| **NOERROR** nhưng không có record đúng loại (**NODATA**) | Tên có thể tồn tại nhưng không có RRset của loại được hỏi |
| **NXDOMAIN** | Resolver/nameserver phản hồi rằng tên đang được hỏi không tồn tại theo góc nhìn DNS đó |
| **SERVFAIL** | Máy chủ không xử lý thành công; có thể do lỗi upstream, DNSSEC validation hoặc cấu hình |
| **REFUSED** | Máy chủ từ chối truy vấn theo chính sách; không chứng minh tên không tồn tại |
| **Timeout** | Không nhận được phản hồi trong thời gian chờ; có thể do đường truyền, firewall, rate limit hoặc server |

Một địa chỉ không trả **A** vẫn có thể có **AAAA**, **MX**, **TXT**, **CNAME** hoặc dữ liệu ở vùng khác. DNS có thể dùng cache âm (**negative caching**) cho các phản hồi phù hợp, nên kết quả vừa thay đổi chưa chắc hiển thị giống nhau ở mọi resolver. Cần ghi lại vị trí truy vấn để so sánh.

## 6. Khám phá subdomain và kiểm tra wildcard

### 6.1. Danh sách tên con từ nguồn có bằng chứng

Nguồn tên con nên đến từ inventory, CT, cấu hình đã duyệt, tài liệu nội bộ hoặc danh sách ứng viên nhỏ theo quy ước đặt tên. Một ví dụ truy vấn tuần tự trong lab:

~~~bash
dig @192.0.2.53 www.corp.example.test A +noall +comments +answer
dig @192.0.2.53 api.corp.example.test A +noall +comments +answer
dig @192.0.2.53 vpn.corp.example.test A +noall +comments +answer
dig @192.0.2.53 staging.corp.example.test A +noall +comments +answer
~~~

Các truy vấn này nhằm xác minh **tên ứng viên** có phản hồi như thế nào. Chúng không tự xác định tính nhạy cảm hay tình trạng thực tế của dịch vụ. Tránh suy rộng từ một danh sách từ khóa rằng đã “quét hết” toàn bộ zone. DNS **không có API phổ quát** để liệt kê mọi tên miền con trong một domain; nguồn dữ liệu và kỹ thuật thu thập quyết định mức bao phủ.

### 6.2. Wildcard DNS gây dương tính giả như thế nào?

Một **wildcard record** có thể khiến nhiều tên ngẫu nhiên cùng nhận một đáp án. Ví dụ zone có bản ghi bao phủ phần tên chưa được khai báo cụ thể; khi truy vấn **abc-random.corp.example.test**, DNS vẫn trả địa chỉ web gateway mặc định. Nếu công cụ liệt kê mọi tên có A là subdomain thực, kết quả sẽ chứa nhiều tên giả.

~~~bash
# So sánh tên có chủ đích với một tên khó có thật trong lab
dig @192.0.2.53 app.corp.example.test A +noall +comments +answer
dig @192.0.2.53 very-unlikely-q7m4.corp.example.test A +noall +comments +answer
~~~

**Cách xác minh:** so sánh nhiều tên ngẫu nhiên khác nhau và các loại record; xem authoritative answer và cấu hình zone nếu có quyền; đối chiếu với inventory và HTTP/TLS metadata được phép kiểm tra. Wildcard có thể tạo CNAME, địa chỉ hoặc hành vi phức tạp, và không nhất thiết trả cùng một IP ở mọi lần do load balancing. **Một câu trả lời giống nhau chưa đủ chứng minh wildcard**, đặc biệt khi có CDN hoặc cơ chế redirect.

### 6.3. CT log, wildcard certificate và DNS là ba nguồn khác nhau

- **CT log** cho biết chứng chỉ từng được cấp/ghi log chứa tên gì; đây là dữ liệu lịch sử, không trực tiếp là bản ghi DNS.
- **Wildcard certificate** như **\*.corp.example.test** chứng minh chứng chỉ bao phủ phạm vi tên nhất định theo quy tắc TLS; nó không liệt kê cụ thể các subdomain đang tồn tại.
- **Wildcard DNS** là cách máy chủ DNS trả lời những tên thỏa điều kiện nhất định, không liên quan bắt buộc đến wildcard certificate.

Việc đối chiếu giúp giảm bỏ sót và tránh đồng nhất “tên từng xuất hiện” với “dịch vụ đang hoạt động”.

## 7. Zone transfer (AXFR): chức năng quản trị và nguy cơ công bố dữ liệu

**AXFR** là cơ chế truyền nội dung zone DNS, thường dùng để đồng bộ giữa các authoritative nameserver theo cấu hình. AXFR có thể cung cấp nhiều bản ghi trong zone, vì vậy việc cho phép mọi nguồn tùy ý tải nội dung zone đôi khi làm lộ hostname và cấu trúc dịch vụ không cần công bố.

Trong lab mà bạn có quyền quản trị hoặc được phê duyệt thử nghiệm:

~~~bash
# Thử AXFR tới authoritative server được cho phép trong phòng lab
dig @192.0.2.53 corp.example.test AXFR +time=2 +tries=1
~~~

Một cấu hình hạn chế transfer có thể trả **REFUSED**, **Transfer failed** hoặc thông báo lỗi khác; một yêu cầu timeout cũng không tự nói lên chính sách. Đọc kết quả cùng ACL nguồn, cơ chế xác thực, cấu hình nameserver và log của dịch vụ.

**Giới hạn khi đánh giá AXFR:**

1. AXFR hợp lệ là cơ chế vận hành, **không phải mặc định là tấn công**; trong hệ thống đúng, nó phải được giới hạn cho nguồn nhận và cơ chế xác thực phù hợp.
2. **Không phải mọi authoritative DNS đều cho phép AXFR**, đặc biệt với DNS được quản lý bởi bên cung cấp cloud/CDN.
3. Có thể cấu hình **ACL theo nguồn, TSIG hoặc cơ chế bảo vệ vận chuyển** theo yêu cầu hạ tầng để chỉ cho bên nhận hợp lệ.
4. AXFR một zone **không đồng nghĩa liệt kê được mọi delegated zone** nằm dưới một domain.
5. **DNSSEC ký dữ liệu để xác thực/tăng toàn vẹn**, không mã hóa nội dung zone và không thay thế việc giới hạn AXFR.

Nếu phát hiện cấu hình transfer quá rộng, ghi rõ zone, nameserver, địa chỉ nguồn kiểm thử, phản hồi nhận được, phạm vi dữ liệu được công bố và mức ảnh hưởng. Không cần sao chép hoặc đưa vào báo cáo đầy đủ thông tin nhạy cảm nếu bản tóm tắt đã đủ để xác minh vấn đề.

## 8. DNSSEC và các giới hạn của việc liệt kê

**DNSSEC** bảo vệ tính xác thực nguồn gốc và tính toàn vẹn của câu trả lời DNS qua chữ ký mật mã cùng chuỗi tin cậy. Các loại record liên quan gồm **DNSKEY**, **DS**, **RRSIG**, **NSEC/NSEC3**.

~~~bash
# Trong lab có DNSSEC, xem DNSKEY và dữ liệu DNSSEC nếu có
dig @192.0.2.53 corp.example.test DNSKEY +dnssec +noall +comments +answer
~~~

Các điểm cần phân biệt:

- Có **DNSKEY/RRSIG** chưa đủ khẳng định chuỗi xác minh DNSSEC hoàn chỉnh từ trust anchor đến zone; phải đánh giá **DS ở zone cha** và quá trình validation.
- **NSEC** có thể tiết lộ quan hệ giữa các tên đã ký trong zone khi trả lời về tên không tồn tại; một số cấu hình có thể làm việc khám phá tên dễ hơn.
- **NSEC3** dùng hàm băm trong cách cung cấp bằng chứng không tồn tại; nó **không bảo đảm che giấu hoàn toàn** danh sách tên và có nhiều giới hạn, tùy cách triển khai.
- DNSSEC **không mã hóa truy vấn DNS**. Quyền riêng tư của kênh giữa client và resolver là một vấn đề khác, liên quan đến các giải pháp như DoT/DoH theo kiến trúc được lựa chọn.
- DNSSEC cũng không chứng minh endpoint ứng dụng là an toàn: chứng chỉ TLS, xác thực dịch vụ, phân quyền và firewall vẫn cần thiết.

Với đội phòng vệ, mục đích của kiểm tra DNSSEC là xác định chuỗi tin cậy đang hoạt động, chính sách ký/đổi khóa hợp lý, giám sát lỗi validation và những thông tin zone không cần thiết được công bố.

## 9. Kết quả DNS enumeration liên quan gì đến rủi ro mạng?

### 9.1. Các tình huống cần phân tích

| Phát hiện DNS | Tài sản/điểm phụ thuộc | Câu hỏi rủi ro | Bước kiểm chứng phòng vệ |
|---|---|---|---|
| Tên **admin** hoặc **vpn** có A/AAAA công khai | Cổng quản trị, VPN, danh tính | Giao diện quản trị có bị công bố ngoài phạm vi dự định? | Đối chiếu cấu hình firewall/VPN, ACL và chủ sở hữu |
| CNAME trỏ đến dịch vụ cloud/SaaS cũ | Namespace DNS, quyền thuê dịch vụ | Tài nguyên đích còn được tổ chức kiểm soát không? Có dấu hiệu dangling DNS không? | Kiểm tra tài khoản dịch vụ và quy trình ngừng sử dụng; không kết luận takeover chỉ từ CNAME |
| AXFR khả dụng từ nguồn không được dự kiến | Nội dung zone và kiến trúc tên | Danh sách tên nội bộ có bị công bố quá mức? | Xác minh chính sách transfer/ACL/TSIG và loại dữ liệu bị lộ |
| Tên nội bộ, thiết bị hoặc môi trường thử nghiệm xuất hiện trong DNS công khai | Thông tin cấu trúc hệ thống | Có công bố hostname không cần thiết, tạo manh mối cho kẻ tấn công? | Đối chiếu kiến trúc split-view và chính sách public DNS |
| A có nhưng AAAA cũng công bố | Bề mặt tiếp xúc IPv6 | Phòng vệ IPv6 có nhất quán với IPv4 không? | Rà soát IPv6 firewall/route, inventory, giám sát và kiểm thử kết nối hợp lệ |
| Cấu hình SPF/DMARC/CAA chưa tương ứng mục tiêu bảo vệ | Danh tính miền, hệ thống email/chứng chỉ | Sai chính sách có làm tăng nguy cơ giả mạo hoặc phát hành chứng chỉ ngoài dự kiến? | Đánh giá với đội email/PKI; xác minh chính sách và luồng thực |
| NS/đường phân giải phụ thuộc một nhà cung cấp | Tính sẵn sàng DNS | Khi nhà cung cấp mất dịch vụ, ứng dụng có còn phân giải được không? | Kiểm tra thiết kế dự phòng, SLA, thử khôi phục và giám sát |
| Log DNS ghi nhận tên bất thường | Telemetry, endpoint, DNS resolver | Có phải do cấu hình, phần mềm hợp lệ hay dấu hiệu điều khiển/thoát dữ liệu? | Tương quan log với thiết bị nguồn, thời điểm, khối lượng và hành vi ứng dụng |

**Dangling DNS** là tình huống bản ghi vẫn tham chiếu một tên/tài nguyên không còn được cấp phát đúng cách. Một số loại tài nguyên bên thứ ba có thể tạo rủi ro **subdomain takeover** nếu người khác được phép nhận lại tên tài nguyên; điều kiện khai thác tùy nhà cung cấp. Việc xác nhận cần đối chiếu quyền sở hữu tài nguyên với đội quản trị, không dựa duy nhất vào thông báo 404 hoặc DNS CNAME.

### 9.2. DNS enumeration không thay thế phân tích lưu lượng

DNS cho biết **cách tên được ánh xạ và công bố**; nó không tự mô tả luồng ứng dụng thực tế. Ví dụ, **db.corp.example.test** có địa chỉ riêng không khẳng định database chỉ cho phép kết nối từ subnet ứng dụng. Cần ghép với flow logs, cấu hình firewall, VPC/VNet route, security group, IAM và xác thực dịch vụ.

Trong threat modeling, đặt DNS bên cạnh các lớp bảo vệ khác:

- **Network segmentation:** ứng dụng có thể phân giải hostname nào và thực sự kết nối được tới đâu?
- **Firewall/ACL:** A/AAAA public có phù hợp chính sách truy cập? Chính sách IPv6 có tương đương?
- **VPN và xác thực kết nối:** truy vấn từ VPN có kết quả khác public? DNS nội bộ có rò rỉ tên ra resolver công cộng?
- **IDS/IPS và DNS monitoring:** có đủ telemetry từ resolver và đường ra để phát hiện bất thường?
- **Cloud:** zone, record, load balancer, security group, quyền sửa DNS và lifecycle tài nguyên có đồng bộ không?
- **Wi-Fi:** mạng khách, BYOD và mạng nội bộ có dùng resolver/chính sách phân giải phù hợp từng vùng?

### 9.3. Thực hành quản trị để giảm rủi ro

1. **Duy trì inventory tên miền và zone:** gắn mỗi zone/record quan trọng với ứng dụng, người sở hữu, mục đích và môi trường; quản lý thay đổi có thể truy vết.
2. **Giới hạn thay đổi DNS:** phân quyền quản trị tối thiểu, MFA cho tài khoản liên quan, review và audit log cho sửa record/zone.
3. **Kiểm soát zone transfer:** chỉ cấp quyền cho secondary/đầu nhận được phép, dùng cơ chế xác thực và bảo vệ kênh phù hợp.
4. **Tránh công bố tên không cần thiết:** cân nhắc split-view DNS, private zones và quy tắc đặt tên để không vô tình rò rỉ kiến trúc; split-view cần vận hành và giám sát cẩn thận.
5. **Theo dõi bản ghi mồ côi:** khi xóa dịch vụ cloud/SaaS phải kiểm tra CNAME, A/AAAA, NS và các record phụ thuộc còn sót.
6. **Bảo vệ resolver:** giới hạn open recursion theo nhu cầu, cập nhật phần mềm, áp dụng hạn chế truy vấn và cơ chế bảo vệ chống lạm dụng/phóng đại theo kiến trúc.
7. **Giám sát thay đổi:** theo dõi bản ghi nhạy cảm, cấu hình DNSSEC, NS, MX, TXT, quyền quản trị và các giá trị không phù hợp baseline.
8. **Thử tình huống gián đoạn:** đánh giá điểm lỗi chung, thời gian cache, chuyển đổi nameserver và ảnh hưởng tới DNS nội bộ, VPN, ứng dụng.

## 10. Mini case study: lập danh sách tài sản DNS cho một tổ chức

### 10.1. Dữ liệu giả định

Giả sử đội hạ tầng phụ trách **corp.example.test** và authoritative server nội bộ. Kiểm kê ban đầu có:

| FQDN/zone | Record (minh họa) | Nhóm tài sản | Quan sát cần xác minh |
|---|---|---|---|
| **app.corp.example.test** | A → 192.0.2.20; AAAA → 2001:db8::20 | Ứng dụng nghiệp vụ | Có cả IPv4 và IPv6; kiểm tra chính sách hai giao thức |
| **portal.corp.example.test** | CNAME → app.corp.example.test | Bí danh người dùng | Xác định chủ sở hữu và chuỗi phụ thuộc |
| **vpn.corp.example.test** | A → 192.0.2.30 | Cổng VPN | Xác thực nhiều lớp, log và giới hạn truy cập theo vai trò |
| **mail.corp.example.test** | A → 192.0.2.40 | Dịch vụ email | Xác minh MX, SPF, DKIM, DMARC theo thiết kế |
| **old-app.corp.example.test** | CNAME → retired.vendor.example | Tên đã ngừng dùng, cần điều tra | Kiểm tra tài nguyên đích và chủ sở hữu trước khi kết luận rủi ro |
| **corp.example.test** | NS/SOA/TXT | Quản trị DNS | Kiểm soát quyền sửa, AXFR và giám sát |

Toàn bộ tên, IP và kết quả nêu trên là **giả lập**. Ví dụ **retired.vendor.example** chỉ biểu diễn một phụ thuộc SaaS tưởng tượng; không phải kết luận về một nhà cung cấp cụ thể.

### 10.2. Chuyển quan sát thành bản ghi có thể kiểm chứng

Một mẫu kết quả kiểm kê tối giản:

~~~yaml
asset_id: DNS-APP-001
fqdn: app.corp.example.test.
observed_record_types: [A, AAAA]
observed_answers:
  A: [192.0.2.20]
  AAAA: ['2001:db8::20']
queried_nameserver: 192.0.2.53
source_type: authoritative_dns_query
environment: lab
business_owner: application_team
security_zone: application
evidence_note: "Observed in authorized lab; confirm asset ownership"
verification_status: pending_owner_confirmation
~~~

Trong hệ thống thật, bổ sung **timestamp UTC**, TTL, response code, DNS view, chuỗi CNAME, nguồn bằng chứng, mức độ nhạy cảm, mục đích dịch vụ và liên kết đến ticket kiểm tra. Nếu nhiều resolver trả khác nhau, lưu từng quan sát riêng thay vì ghi đè.

### 10.3. Phân tích ba phát hiện

**Phát hiện A — có bản ghi AAAA:** nếu giám sát và firewall chỉ kiểm soát IPv4 thì có nguy cơ bỏ quên đường IPv6. **Hành động:** đối chiếu effective policy IPv6, nguồn luồng được phép và mức quan sát trên mạng, không tự suy đoán IPv6 đang mở.

**Phát hiện B — CNAME của ứng dụng đã ngừng:** có thể chỉ là cấu hình rác, nhưng cũng có thể là dấu hiệu tài nguyên cloud chưa được tháo gỡ nhất quán. **Hành động:** liên hệ chủ sở hữu, kiểm tra trạng thái tài nguyên đích và xóa/sửa record thông qua quy trình thay đổi khi đã đủ bằng chứng.

**Phát hiện C — quyền sửa zone quá rộng:** việc có nhiều hostname không đồng nghĩa DNS nguy hiểm; điểm quan trọng là ai có thể thay đổi ánh xạ. **Hành động:** rà soát IAM/RBAC, lịch sử chỉnh sửa, MFA, phân quyền giữa môi trường và khả năng khôi phục từ cấu hình chuẩn.

Các phát hiện nên có mức tin cậy (*confirmed/likely/unverified*), tác động dự kiến, chủ sở hữu xử lý và bằng chứng đủ để kiểm chứng sau thay đổi.

## 11. Lưu ý khi diễn giải kết quả và xử lý sự cố

| Tình huống | Nguyên nhân có thể | Cách phân tích |
|---|---|---|
| Kết quả của hai máy khác nhau | Split-view DNS, resolver khác, VPN, cache hoặc policy | Ghi nguồn và resolver, đối chiếu authoritative/recursive theo quyền |
| Không có bản ghi A nhưng truy cập vẫn được | Có AAAA, CNAME, dữ liệu cache, proxy/hosts file hoặc định tuyến qua cơ chế khác | Kiểm tra đầy đủ các loại record và cấu hình thực tế |
| Trả nhiều địa chỉ IP thay đổi theo lần hỏi | DNS load balancing, CDN hoặc chính sách theo vùng | Thu thập nhiều lần có kiểm soát, phân biệt endpoint với hostname |
| Tên bất kỳ đều trả IP | Wildcard DNS, reverse proxy hoặc catch-all service | Dùng tên đối chứng và kiểm tra bằng chứng sở hữu |
| NXDOMAIN hôm nay nhưng CT từng có tên | Tài sản đã ngừng, DNS view khác hoặc CT lưu lịch sử | Xác minh với inventory và chủ sở hữu, không coi là bằng chứng hệ thống đang chạy |
| DNSSEC validation lỗi, SERVFAIL | Sai DS/DNSKEY, chữ ký hết hạn, đồng hồ không chuẩn hoặc lỗi resolver | Đối chiếu trạng thái DNSSEC từ các vị trí phù hợp |
| SOA/NS trông khác dự kiến | Delegation, secondary, cloud DNS, split-view, cấu hình lẫn lộn | Xác định zone có thẩm quyền thực và chain delegation |
| DNS truy vấn thành công nhưng ứng dụng không kết nối | TCP/UDP service, firewall, TLS, route hoặc quyền ứng dụng | Kết hợp DNS với phân tích mạng, log dịch vụ và chính sách truy cập |

**Đặc biệt với DNS qua UDP/TCP:** DNS truyền thống thường dùng UDP/53, nhưng TCP/53 có vai trò hợp lệ trong truy vấn, trả lời lớn và zone transfer. EDNS(0) hỗ trợ những tính năng DNS mở rộng; kích thước gói lớn có thể liên quan đến MTU, fragmentation hoặc kiểm soát firewall. Nếu một truy vấn DNS có vấn đề, cần quan sát cả mã phản hồi DNS, vận chuyển UDP/TCP, kích thước gói, ICMP báo lỗi và chính sách mạng, tránh quy toàn bộ sự cố về DNS record.

## 12. Bài tập tự kiểm tra

**Bài 1 — Chọn record:** bạn cần xác định một hostname có được công bố qua IPv6 hay không, máy chủ email nào được chỉ định và zone có dùng DNSSEC hay không. Bạn sẽ hỏi những loại bản ghi gì?

*Gợi ý:* hỏi **AAAA**, **MX**, sau đó xem **DNSKEY/DS/RRSIG** và quá trình validation thích hợp. Không thể kết luận DNSSEC hoàn chỉnh chỉ từ DNSKEY tại một nameserver.

**Bài 2 — Dương tính giả:** một công cụ phát hiện 10.000 “subdomain”, nhưng khi hỏi tên ngẫu nhiên đều trả cùng CNAME. Bạn có thể kết luận 10.000 dịch vụ đang hoạt động không?

*Gợi ý:* **không**. Kiểm tra wildcard, so sánh nhiều tên đối chứng và đối chiếu nguồn có bằng chứng về tài sản thực.

**Bài 3 — AXFR:** trên authoritative server của lab, một truy vấn AXFR từ máy không nằm trong danh sách secondary vẫn trả toàn bộ dữ liệu zone. Bạn sẽ báo cáo điều gì và kiểm tra biện pháp nào?

*Gợi ý:* ghi source IP, zone, nameserver, phản hồi và phạm vi lộ dữ liệu; đề xuất giới hạn AXFR bằng ACL/TSIG hoặc cơ chế phù hợp và xác minh lại từ nguồn không được phép. Không yêu cầu tắt toàn bộ AXFR nếu nó phục vụ đồng bộ hợp lệ.

**Bài 4 — Dangling DNS:** một CNAME còn trỏ về hostname của nhà cung cấp không còn sử dụng. Đây đã chắc chắn là subdomain takeover chưa?

*Gợi ý:* chưa. Cần kiểm tra trạng thái dịch vụ đích, quyền sở hữu, điều kiện của nhà cung cấp và cách thu hồi tên hợp lệ. DNS là đầu mối điều tra, không phải kết luận khai thác.

**Bài 5 — Phát hiện chênh lệch:** **app.corp.example.test** trả IP riêng khi ở VPN nhưng trả IP khác khi truy vấn DNS công cộng. Hai câu trả lời có buộc phải giống nhau không?

*Gợi ý:* không. Đây có thể là split-view DNS hợp lệ. Cần xác định ý định thiết kế, record owner, chính sách định tuyến/firewall và quyền truy cập ở từng vùng.

**Bài 6 — Ưu tiên xử lý:** bạn có các phát hiện sau: (1) hostname nội bộ cũ trong CT, (2) bản ghi AAAA của cổng quản trị chưa nằm trong inventory, (3) MX trỏ tới nhà cung cấp email đã được phê duyệt. Bạn sẽ ưu tiên xác minh gì?

*Gợi ý:* ưu tiên **(2)** vì có khả năng tồn tại đường truy cập chưa được theo dõi; vẫn xác minh quyền truy cập và policy trước khi kết luận lỗi. **(1)** cần đối chiếu tính hiện hành và mức nhạy cảm. **(3)** là cấu hình có thể hợp lệ nếu đúng thiết kế.

## 13. Tóm tắt kiến thức

DNS enumeration giúp tìm **manh mối về tài sản và quan hệ phụ thuộc** qua bản ghi tên miền. Phương pháp hiệu quả kết hợp nguồn thụ động, truy vấn chủ động có kiểm soát, phân tích record, xác minh wildcard/split-view và đối chiếu inventory. Một hostname trả lời DNS chưa chứng minh dịch vụ đang hoạt động, nhưng có thể chỉ ra điểm truy cập, sự phụ thuộc hoặc cấu hình cần kiểm tra.

Trong thực hành an toàn mạng, đầu ra quan trọng nhất không phải số lượng subdomain được tìm thấy, mà là **danh sách tài sản có nguồn bằng chứng, chủ sở hữu, mức phơi lộ, rủi ro và hành động phòng vệ có thể kiểm chứng**. Bản đồ đó giúp nhóm hạ tầng phối hợp quản lý DNS với firewall, VPN, IDS/IPS, phân đoạn mạng, bảo vệ danh tính và hạ tầng cloud.

### Tài liệu tham khảo

- [RFC 1034 — Domain Names: Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034): cấu trúc DNS, zone và phân giải tên.
- [RFC 1035 — Domain Names: Implementation and Specification](https://www.rfc-editor.org/rfc/rfc1035): định dạng bản ghi, thông điệp và các cơ chế DNS.
- [RFC 5936 — DNS Zone Transfer Protocol (AXFR)](https://www.rfc-editor.org/rfc/rfc5936): cơ chế chuyển zone.
- [RFC 4592 — The Role of Wildcards in the Domain Name System](https://www.rfc-editor.org/rfc/rfc4592): quy tắc DNS wildcard.
- [RFC 4033 — DNS Security Introduction and Requirements](https://www.rfc-editor.org/rfc/rfc4033): mô hình bảo vệ dữ liệu DNS bằng DNSSEC.
- [RFC 7766 — DNS Transport over TCP](https://www.rfc-editor.org/rfc/rfc7766): vai trò của TCP trong DNS.
- [RFC 9156 — DNS Query Name Minimisation to Improve Privacy](https://www.rfc-editor.org/rfc/rfc9156): giảm thông tin tên miền tiết lộ theo quá trình phân giải.
- [RFC 9460 — Service Binding and Parameter Specification via the DNS (SVCB and HTTPS)](https://www.rfc-editor.org/rfc/rfc9460): các bản ghi SVCB/HTTPS.
