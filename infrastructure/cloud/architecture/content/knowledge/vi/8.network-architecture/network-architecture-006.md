# Thiết kế DNS công cộng, DNS nội bộ và phân giải tên lai

## 1. Vì sao DNS là một quyết định kiến trúc cloud?

**Domain Name System (DNS)** là hệ thống phân giải tên miền thành các bản ghi mà ứng dụng và hạ tầng có thể sử dụng, chẳng hạn địa chỉ IPv4/IPv6, máy chủ thư hoặc thông tin xác minh tên miền. Trong một hệ thống cloud, DNS quyết định người dùng tìm đến điểm vào công cộng nào, workload nội bộ tìm đúng dịch vụ riêng tư ra sao, và hệ thống tại trung tâm dữ liệu truyền thống có tra cứu được tên của tài nguyên trên cloud hay không.

DNS có ảnh hưởng trực tiếp đến trải nghiệm nghiệp vụ: người dùng không phân giải được tên sẽ không truy cập được ứng dụng dù các máy chủ vẫn khỏe; một dịch vụ dùng sai địa chỉ có thể kết nối qua Internet thay vì tuyến riêng, làm tăng độ trễ, chi phí và rủi ro bảo mật. Khi có nhiều môi trường, mạng và nhà cung cấp, một thay đổi nhỏ trong zone hoặc forwarding rule cũng có thể làm đứt cả chuỗi phụ thuộc.

Trong module **CLOUD_ARCHITECTURE**, thiết kế DNS gắn với lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Một phương án phù hợp phải cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**, đồng thời có thể đánh giá theo tư duy Well-Architected. Bài này tập trung vào ba phần: **DNS công cộng**, **DNS riêng trong mạng nội bộ** và **phân giải tên lai giữa on-premises với cloud**.

Sau bài học, bạn có thể:

- Giải thích vai trò của authoritative DNS, recursive resolver, zone, delegation, TTL và bộ nhớ đệm.
- Thiết kế tên miền và bản ghi cho ứng dụng công cộng, dịch vụ riêng tư và mạng lai.
- Phân biệt private DNS zone, split-horizon DNS, conditional forwarding và DNS resolver endpoint.
- Vẽ và giải thích đường đi truy vấn DNS từ Internet, mạng doanh nghiệp và workload cloud.
- Xác định yêu cầu mạng, kiểm soát truy cập, dự phòng, ghi log và các tình huống lỗi của DNS.
- Kiểm thử thiết kế bằng lệnh tra cứu từ từng vị trí, thay vì chỉ nhìn vào cấu hình zone.

## 2. Những thành phần DNS cần phân biệt

Một truy vấn DNS thông thường trải qua các vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Stub resolver** | Thư viện/hệ điều hành nhận yêu cầu từ ứng dụng và gửi đến DNS resolver được cấu hình | Resolver của laptop hoặc máy chủ ứng dụng |
| **Recursive resolver** | Tìm câu trả lời thay cho client; có thể truy vấn các authoritative server, dùng cache hoặc forward tới resolver khác | DNS của doanh nghiệp, DNS do cloud cung cấp |
| **Authoritative name server** | Trả lời các bản ghi trong zone mà nó có thẩm quyền quản lý | Authoritative DNS cho **example.com** |
| **DNS zone** | Phạm vi dữ liệu có thẩm quyền, chứa bản ghi và thông tin quản trị | Zone công cộng **example.com**, zone riêng **cloud.example.com** |
| **Delegation** | Vùng cha chỉ định name server có thẩm quyền cho vùng con qua bản ghi NS; có thể cần glue record | Ủy quyền **shop.example.com** cho DNS riêng của một đơn vị |
| **Forwarder** | Resolver nhận truy vấn và chuyển một số hoặc mọi truy vấn đến resolver khác | DNS văn phòng chuyển **cloud.example.com** sang resolver cloud |
| **Cache / TTL** | Lưu kết quả tra cứu trong thời gian cho phép để giảm độ trễ và tải | Resolver cache A record trong tối đa 300 giây |

**Authoritative server** và **recursive resolver** không phải cùng một vai trò. Authoritative server trả lời cho vùng dữ liệu mình quản lý, còn recursive resolver thực hiện công việc tra cứu cho client. Một phần mềm DNS có thể cung cấp cả hai chức năng, nhưng khi thiết kế phải phân biệt ranh giới trách nhiệm và chính sách truy cập của chúng.

### 2.1. Phân giải tên từ Internet hoạt động thế nào?

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt / OS
    participant R as Recursive resolver
    participant Root as Root DNS
    participant TLD as .com DNS
    participant Auth as Authoritative example.com
    U->>R: booking.example.com A?
    alt Chưa có dữ liệu hợp lệ trong cache
        R->>Root: Hỏi đường đến .com
        Root-->>R: NS cho .com
        R->>TLD: Hỏi đường đến example.com
        TLD-->>R: NS cho example.com
        R->>Auth: booking.example.com A?
        Auth-->>R: Bản ghi A / CNAME liên quan
    else Cache còn hiệu lực
        Note over R: Dùng kết quả đã lưu
    end
    R-->>U: Kết quả + TTL còn lại
~~~

Sơ đồ là luồng điển hình ở mức khái niệm. Trong thực tế, resolver có thể đã cache thông tin NS, CNAME hoặc câu trả lời; có thể hỏi AAAA, HTTPS hoặc các loại bản ghi khác. Không phải mọi yêu cầu đều đi đến root và TLD.

### 2.2. Các bản ghi thường gặp

| Record | Công dụng | Điểm cần lưu ý |
| --- | --- | --- |
| **A / AAAA** | Ánh xạ tên sang IPv4 / IPv6 | Địa chỉ phải đúng với khả năng định tuyến từ vị trí client |
| **CNAME** | Đặt bí danh của một tên tới tên khác | Tại một tên có CNAME không được tồn tại các dữ liệu khác; apex zone thông thường không thể dùng CNAME |
| **NS / SOA** | Chỉ định name server, thông tin quản trị và tham số zone | NS tại ranh giới delegation phải nhất quán với thực tế |
| **MX** | Xác định máy chủ nhận thư của tên miền | Tên đích phải phân giải phù hợp |
| **TXT** | Lưu dữ liệu văn bản như xác minh tên miền, chính sách email | Không chứa bí mật; TXT của DNS công cộng có thể bị đọc bởi người ngoài |
| **CAA** | Giới hạn các tổ chức phát hành chứng chỉ theo chính sách DNS | Kiểm tra trước khi tự động cấp/gia hạn chứng chỉ |
| **SRV** | Công bố một số dịch vụ với target và port | Chỉ hữu ích khi client hiểu quy ước SRV |
| **PTR** | Tra cứu ngược IP sang tên | Quản lý trong reverse zone; phụ thuộc chủ sở hữu dải IP |
| **DS / DNSKEY / RRSIG** | Thành phần DNSSEC để xác thực nguồn gốc và tính toàn vẹn dữ liệu DNS | Cần phối hợp khóa và delegation; DNSSEC không mã hóa dữ liệu DNS |

Một số nhà cung cấp hỗ trợ **ALIAS, ANAME hoặc CNAME flattening** để trỏ apex đến dịch vụ có tên DNS động. Đây là tính năng của nền tảng, **không phải bản ghi CNAME chuẩn tại zone apex**. Khi chọn giải pháp, kiểm tra dịch vụ DNS đích hỗ trợ record và health-based routing thế nào.

### 2.3. TTL là chính sách cache, không phải đồng hồ chuyển tuyến chính xác

**Time To Live (TTL)** cho biết thời gian một DNS response có thể được lưu trong cache theo chính sách resolver. Với TTL 300 giây, thay bản ghi không có nghĩa toàn bộ client sẽ thấy IP mới sau đúng 5 phút: có resolver đã cache từ trước, ứng dụng giữ kết nối lâu hơn, local cache độc lập, hoặc resolver áp đặt cách xử lý riêng. Câu trả lời **NXDOMAIN** (tên không tồn tại) cũng có thể bị lưu trong cache âm theo thông tin SOA của zone.

TTL thấp thường giúp các thay đổi được nhìn thấy sớm hơn, nhưng tăng số truy vấn, chi phí và sự phụ thuộc vào DNS khi cache hết hạn. TTL cao giảm tải nhưng kéo dài thời gian chuyển đổi. Chọn TTL theo **tần suất thay đổi, mục tiêu chuyển tuyến, độ tin cậy của đường phân giải, đặc tính client và chi phí**; diễn tập thay đổi thật trước khi đưa vào runbook.

## 3. Khởi đầu từ yêu cầu và quy hoạch tên miền

Trước khi tạo zone, nhóm kiến trúc cần biết ai sẽ hỏi DNS, họ đứng ở mạng nào, tên nào cần phân giải và câu trả lời mong đợi là địa chỉ công cộng hay riêng tư.

| Câu hỏi | Vì sao quan trọng |
| --- | --- |
| Người dùng ở Internet, văn phòng, trung tâm dữ liệu hay trong VPC/VNet? | Quyết định authoritative source, resolver, mạng định tuyến và đường đi |
| Tên nào phải công khai và tên nào chỉ dành cho dịch vụ nội bộ? | Quyết định public/private zone và chính sách công bố |
| Có mạng on-premises, nhiều tài khoản cloud, nhiều VPC/VNet hay nhiều provider không? | Quyết định forwarding, zone association/visibility, kết nối giữa mạng |
| Có trùng suffix hoặc tên với DNS cũ, Active Directory hay hệ thống đối tác không? | Tránh split-horizon sai, xung đột thẩm quyền và vòng lặp forwarding |
| Tài nguyên thay đổi IP khi scale, redeploy hoặc failover không? | Ưu tiên target ổn định, bản ghi động hoặc tự động hóa DNS |
| SLO/RTO/RPO, độ trễ tra cứu, mức chịu mất liên kết on-prem↔cloud ra sao? | Quyết định số resolver/endpoint, dự phòng, TTL và điều kiện thất bại |
| Ai quản trị zone, cấp quyền cập nhật, chứng chỉ và logging? | Thiết kế ownership, audit, change management và bảo mật |

Một bảng yêu cầu có thể đo:

| Mã | Yêu cầu mẫu | Cách xác minh |
| --- | --- | --- |
| DNS-01 | Client Internet phân giải **booking.example.com** sang điểm vào công cộng của ứng dụng | Tra cứu từ mạng ngoài doanh nghiệp và đối chiếu với cấu hình authoritative |
| DNS-02 | Máy nội bộ cloud phân giải **api.cloud.example.com** thành địa chỉ thuộc mạng riêng cho phép | Truy vấn từ workload ở những network được liên kết với private zone |
| DNS-03 | Client văn phòng phân giải tên cloud riêng qua liên kết riêng, khi đường mạng và resolver bình thường | Truy vấn tại on-prem resolver; kiểm tra lưu lượng và địa chỉ trả về |
| DNS-04 | Workload cloud phân giải **erp.office.example.com** qua on-prem resolver được phép | Truy vấn từ cloud, quan sát đúng rule và lưu lượng về DNS tại văn phòng |
| DNS-05 | Khi một DNS endpoint riêng ngừng hoạt động, truy vấn vẫn thành công qua endpoint còn lại theo mục tiêu phục hồi đã duyệt | Chạy kiểm thử failover và đo tỷ lệ thành công/độ trễ |

Những ngưỡng định lượng về latency, tỷ lệ thành công và thời gian khôi phục phải được chủ sở hữu nghiệp vụ/SRE xác nhận, không tự lấy một số chung làm cam kết.

### 3.1. Quy hoạch không gian tên theo quyền sở hữu và nơi sử dụng

Một phương án minh họa dùng tên miền **example.com** (tên dành cho tài liệu) và ba nhánh:

| Namespace | Tầm nhìn | Chủ sở hữu | Ví dụ |
| --- | --- | --- | --- |
| **example.com** | DNS công cộng | Đội quản trị domain/platform | **booking.example.com**, **www.example.com** |
| **cloud.example.com** | Private DNS trong mạng cloud được cấp quyền | Đội platform/cloud | **api.cloud.example.com**, **db.cloud.example.com** |
| **office.example.com** | DNS nội bộ tại doanh nghiệp | Đội mạng/on-prem | **erp.office.example.com**, **ldap.office.example.com** |

Các namespace riêng dưới một tên miền có quyền sở hữu hợp lệ giúp quy định ranh giới và tránh chọn hậu tố nội bộ không được kiểm soát. **Private namespace không bắt buộc phải được ủy quyền công khai**: resolver nội bộ có thể được cấu hình để biết nguồn thẩm quyền riêng. Tuy nhiên, phải bảo đảm hệ thống phân giải từ mạng ngoài không vô tình dựa vào bản ghi riêng và không gây rò rỉ tên nhạy cảm.

**Tránh dùng một suffix cho nhiều đội quản lý độc lập mà không có quy tắc rõ.** Nếu công ty dùng cùng **app.example.com** trong zone công cộng và zone riêng, cần chủ động quản lý split-horizon; bản ghi có thể có giá trị khác nhau tùy resolver và network.

## 4. Thiết kế DNS công cộng

**Public DNS** trả lời những tên cần được phân giải từ Internet, chẳng hạn website, API công khai, email và các bản ghi phục vụ xác minh domain/chứng chỉ. Public authoritative zone thường được quản lý bằng dịch vụ DNS có khả năng sẵn sàng cao, kiểm soát thay đổi và các điểm phục vụ được phân tán.

~~~mermaid
flowchart LR
    Browser["Client trên Internet"] --> Rec["Recursive DNS của client"]
    Rec --> Auth["Public authoritative zone: example.com"]
    Auth -->|"A/AAAA hoặc alias của booking.example.com"| Rec
    Browser -->|"HTTPS đến địa chỉ đã phân giải"| Edge["WAF / CDN / public load balancer"]
    Edge --> App["Ứng dụng ở cloud"]
~~~

DNS **chỉ đưa client đến địa chỉ/tên đích**, không thay thế HTTPS, certificate validation, WAF, firewall, cân bằng tải hoặc kiểm tra quyền truy cập. Bản ghi trỏ tới service phải có khả năng định tuyến và chứng chỉ TLS phù hợp với tên ứng dụng.

### 4.1. Quyết định các record công cộng

- **Website và API:** Dùng A/AAAA cho IP công cộng ổn định hoặc record alias được nền tảng hỗ trợ để trỏ vào CDN/load balancer. Tránh hard-code IP tạm của instance hoặc container.
- **Tên phụ:** Dùng CNAME đến target theo chính sách khi không ở apex. Cần theo dõi target DNS và chuỗi CNAME quá dài.
- **Apex example.com:** Không đặt CNAME chuẩn đồng thời với SOA/NS ở cùng owner name; nếu dịch vụ đích không có IP tĩnh, cân nhắc ALIAS/flattening theo hỗ trợ của DNS provider.
- **Email và xác minh:** Quản lý MX, SPF/DKIM/DMARC qua các bản ghi thích hợp, TXT và CAA theo yêu cầu; phân quyền ghi vì lỗi có thể tác động hệ thống không liên quan ứng dụng.
- **Dịch vụ đa vùng:** Có thể dùng latency/weighted/geolocation/failover routing hoặc global load balancing theo sản phẩm được chọn. Kiểm tra điều kiện health check và tính chất cache trước khi dùng làm cơ chế DR.

### 4.2. Public DNS failover cần phối hợp với sức khỏe ứng dụng

Giả sử **booking.example.com** trỏ đến hai điểm vào vùng A và vùng B. Một dịch vụ DNS hỗ trợ health-based failover có thể trả về điểm B khi A không khỏe, nhưng:

1. Health check phải kiểm tra một tín hiệu đủ đại diện; chỉ thấy TCP mở chưa chắc ứng dụng có thể xử lý đặt chỗ.
2. Resolver và client vẫn có thể giữ địa chỉ cũ đến khi cache hết hạn; ứng dụng có thể tiếp tục dùng kết nối đã mở.
3. Dữ liệu và giao dịch phải được thiết kế để B thực sự phục vụ đúng khi chuyển tuyến. DNS không đồng bộ database.
4. Cần diễn tập tình huống mất vùng, đo thời gian khôi phục thực tế so với RTO/RPO đã thỏa thuận.

Public DNS có thể cấu hình **DNSSEC** để xác thực nguồn gốc và tính toàn vẹn response bằng chuỗi tin cậy từ zone cha; việc thay đổi khóa và bản ghi DS phải phối hợp cẩn thận để tránh làm resolver xác thực trả SERVFAIL. DNSSEC **không mã hóa** truy vấn và không thay thế HTTPS.

## 5. Thiết kế DNS nội bộ và private zone

**Private DNS** trả lời những tên chỉ nên được sử dụng trong mạng được phép: database, API nội bộ, service discovery, endpoint riêng của dịch vụ cloud và hệ thống quản trị. Private DNS zone thường được liên kết với một hoặc nhiều mạng ảo, tài khoản hoặc dự án theo cơ chế của nhà cung cấp.

~~~mermaid
flowchart LR
    VM["Ứng dụng trong VPC/VNet"] --> Resolver["Cloud recursive resolver"]
    Resolver --> Zone["Private zone: cloud.example.com"]
    Zone --> Resolver
    Resolver --> VM
    VM -->|"Kết nối tới 10.42.20.15"| API["Private API, không public IP"]
~~~

Trong ví dụ, **api.cloud.example.com** được trả về **10.42.20.15** chỉ khi workload dùng resolver có quyền nhìn thấy zone và có đường mạng phù hợp. Đây là một địa chỉ private minh họa. Không phải mọi client Internet đều truy vấn được private zone, và có bản ghi A private **không có nghĩa network đã mở đường**.

### 5.1. Nguồn dữ liệu có thẩm quyền và khả năng nhìn thấy zone

- Xác định zone **cloud.example.com** được quản lý ở đâu và mạng nào được liên kết. Nếu workload ở một VPC/VNet khác, phải có quyền liên kết, peering hoặc cơ chế phân giải tên thích hợp; việc có đường mạng đến IP chưa bảo đảm nhìn thấy DNS zone.
- Với dịch vụ cloud có **private endpoint**, kiểm tra cách provider quản lý tên DNS riêng, CNAME hoặc bản ghi trong private zone. Chọn hostname mà client thực sự dùng; không tự giả định mọi endpoint có IP cố định.
- Với nhiều môi trường **dev/staging/prod**, cân nhắc suffix riêng hoặc quyền liên kết tách biệt để tránh record bị cập nhật nhầm. Ví dụ **api.prod.cloud.example.com** và **api.dev.cloud.example.com** với quy tắc zone/association rõ ràng.
- Trong Kubernetes, DNS của cluster (thường phục vụ **service.namespace.svc.cluster.local**) là một lớp service discovery khác với private DNS của VPC/VNet. Không nên giả định tên service trong cluster tự động phân giải được từ toàn bộ mạng on-prem hoặc Internet.

### 5.2. Split-horizon DNS: một tên có nhiều câu trả lời

**Split-horizon** (còn gọi split-view hoặc split-brain DNS trong một số tài liệu) nghĩa là kết quả DNS cho cùng một tên phụ thuộc vào vị trí/client hoặc resolver được dùng.

| Nơi truy vấn | Tên được hỏi | Kết quả ví dụ |
| --- | --- | --- |
| Internet | **portal.example.com** | IP public của CDN/WAF |
| Mạng nội bộ | **portal.example.com** | IP private của internal load balancer |
| Internet | **db.cloud.example.com** | Không được công bố dữ liệu trong private zone |
| VPC/VNet được liên kết | **db.cloud.example.com** | IP private của database hoặc private endpoint |

Split-horizon có thể hữu ích khi người dùng trong công ty cần truy cập cùng hostname qua tuyến riêng và certificate vẫn dùng đúng tên. Nhưng nó tạo trách nhiệm đồng bộ các bản ghi cần thiết giữa các view. **Private zone cùng tên/suffix với public zone có thể che khuất các bản ghi public**: khi private resolver tìm trong private zone mà bản ghi thiếu, nó có thể trả NXDOMAIN thay vì tự động tìm bản ghi từ public zone. Hành vi chính xác phụ thuộc resolver và dịch vụ cloud, nên phải kiểm thử, không được giả định luôn có fallback.

Nếu không cần dùng cùng hostname, tách namespace rõ ràng như **public booking.example.com** và **private api.cloud.example.com** thường dễ vận hành hơn.

### 5.3. DNS riêng không phải là tường lửa

Không công bố tên trong public DNS giúp giảm khả năng tìm thấy dịch vụ, nhưng **không thay thế** segmentation mạng, ACL/security group, IAM, xác thực dịch vụ, TLS hoặc kiểm soát dữ liệu. Bên biết IP hoặc tên vẫn có thể thử kết nối nếu tuyến mạng và quyền cho phép. Thiết kế private DNS và chính sách network phải được kiểm tra cùng nhau.

## 6. Phân giải tên lai: hai chiều giữa on-premises và cloud

**Hybrid DNS** giải quyết bài toán các client ở on-premises và cloud cần phân giải tên của nhau qua kết nối riêng như site-to-site VPN hoặc dedicated private connectivity. Trọng tâm là chọn **recursive resolver nào có quyền hỏi authoritative source nào** và thiết lập đường truyền đến các resolver được phép.

Hai hướng truy vấn chính:

1. **On-premises → Cloud:** Client văn phòng cần tra cứu **api.cloud.example.com** trong private zone cloud. DNS on-prem chuyển truy vấn theo suffix đến **cloud inbound resolver endpoint**; resolver cloud tìm private zone và trả địa chỉ private.
2. **Cloud → On-premises:** Workload cloud cần tra cứu **erp.office.example.com**. Cloud resolver có **conditional forwarding rule** chuyển truy vấn đến DNS on-prem qua **cloud outbound resolver endpoint** hoặc cơ chế tương đương.

~~~mermaid
flowchart LR
    subgraph Office["Mạng on-premises"]
      Client["Client văn phòng"]
      OnDNS["DNS nội bộ / recursive resolver"]
      ERP["ERP: 10.10.20.15"]
      Client --> OnDNS
    end
    subgraph Link["VPN / kết nối riêng có định tuyến"]
      Tunnel["Private network link"]
    end
    subgraph Cloud["Cloud VPC/VNet"]
      In["Inbound DNS resolver endpoint"]
      CloudDNS["Cloud recursive resolver + private zone cloud.example.com"]
      Out["Outbound DNS resolver endpoint"]
      Workload["Ứng dụng cloud"]
      API["API riêng: 10.42.20.15"]
      Workload --> CloudDNS
      In --> CloudDNS
      CloudDNS --> Out
    end
    OnDNS -->|"cloud.example.com"| Tunnel
    Tunnel --> In
    Out -->|"office.example.com"| Tunnel
    Tunnel --> OnDNS
    CloudDNS -.-> API
    OnDNS -.-> ERP
~~~

Sơ đồ mô tả **đường đi truy vấn logic**, không mô tả đường trả về DNS response hoặc kết nối ứng dụng thực tế. Dù tên phân giải đúng, máy client vẫn cần route, firewall/security group, TLS và quyền truy cập để kết nối tới IP của API hoặc ERP.

### 6.1. Cloud inbound endpoint làm gì?

Inbound endpoint cung cấp địa chỉ IP riêng mà DNS on-prem được phép gửi truy vấn vào dịch vụ resolver cloud. Nó **không phải public authoritative DNS**, không nên công bố trực tiếp ra Internet, và không tự tạo tuyến mạng tới VPC/VNet. Phải bảo đảm source IP từ on-prem được route đến endpoint và được phép gửi DNS trên giao thức phù hợp.

### 6.2. Cloud outbound endpoint làm gì?

Outbound endpoint là đường mà dịch vụ resolver cloud dùng để gửi truy vấn từ cloud đến các DNS server ngoài phạm vi resolver, ví dụ hệ thống DNS nội bộ tại doanh nghiệp. Cần có **forwarding rule theo suffix**, target IP của DNS on-prem và liên kết rule với mạng phù hợp. Một số provider dùng tên khác hoặc mô hình chính sách khác; mục đích logic vẫn là chuyển đúng câu hỏi tới nguồn có thẩm quyền.

### 6.3. Conditional forwarding khác gì delegation?

- **Conditional forwarding:** Recursive resolver chuyển các truy vấn thuộc một suffix cụ thể đến resolver/forwarder đích. Hữu ích với private zone do cloud managed DNS quản lý, nhất là khi chỉ có inbound resolver IP mà không có authoritative NS công bố trực tiếp.
- **Delegation:** Parent authoritative zone công bố bản ghi NS của child zone. Phù hợp khi có authoritative server cho child và resolver có thể truy cập đúng server đó. Không được nhầm **địa chỉ recursive inbound resolver** với **authoritative name server** dùng để delegation.
- **DNS peering / sharing:** Một số nền tảng có cơ chế liên kết private zone giữa các mạng/tài khoản/dự án hoặc chính sách DNS peering. Khả năng và giới hạn phụ thuộc provider, khác với network peering thuần túy.

Trong mạng lai, conditional forwarding thường là lựa chọn thực dụng để nối một private zone ở cloud và DNS doanh nghiệp; tuy nhiên, cần so sánh yêu cầu quản trị zone, quyền truy cập, chính sách cache, tính sẵn sàng và loại endpoint.

## 7. Ví dụ xuyên suốt: ba namespace và ba đường phân giải

Giả sử doanh nghiệp sử dụng:

| Thành phần | Giá trị minh họa | Phạm vi |
| --- | --- | --- |
| Domain công cộng | **example.com** | Public authoritative DNS |
| Ứng dụng công cộng | **booking.example.com** → public entrypoint | Internet |
| Private cloud zone | **cloud.example.com** | Cloud VPC/VNet liên kết |
| Private API | **api.cloud.example.com** → **10.42.20.15** | Cloud và client on-prem được phép |
| DNS inbound endpoint tại cloud | **10.42.1.10**, **10.42.2.10** | Hai subnet/vùng lỗi khác nhau nếu sản phẩm hỗ trợ |
| Private on-prem zone | **office.example.com** | DNS doanh nghiệp |
| ERP on-prem | **erp.office.example.com** → **10.10.20.15** | On-prem và workload cloud được phép |
| DNS on-prem | **10.10.0.53**, **10.11.0.53** | Hai resolver trong vùng lỗi khác nhau |
| Kết nối lai | VPN hoặc private link đã được định tuyến | 10.10.0.0/16 ↔ 10.42.0.0/16 (minh họa) |

Những địa chỉ và record trên **chỉ dùng để luyện thiết kế**. Trong triển khai thật phải chọn IP, routing, zone association và subnet theo network plan, không sao chép các giá trị này vào production.

### 7.1. Client Internet hỏi booking.example.com

~~~text
Internet client
  -> recursive resolver bên ngoài
  -> public authoritative zone example.com
  -> bản ghi của booking.example.com
  -> IP / hostname public entrypoint
  -> client kết nối HTTPS qua Internet
~~~

Không cần gửi truy vấn này qua DNS nội bộ của doanh nghiệp. Nền tảng cloud có thể ẩn sau CDN/WAF/load balancer; DNS công cộng không nên tiết lộ địa chỉ quản trị hoặc database nội bộ.

### 7.2. Client văn phòng hỏi api.cloud.example.com

~~~text
Laptop ở văn phòng
  -> recursive DNS on-prem 10.10.0.53
  -> rule cho cloud.example.com
  -> kết nối riêng tới cloud inbound DNS 10.42.1.10 hoặc 10.42.2.10
  -> private zone cloud.example.com
  -> A 10.42.20.15
  -> kết quả quay về laptop
  -> laptop kết nối private API theo policy và route
~~~

Resolver văn phòng không cần biết tất cả bản ghi cloud; nó chỉ cần biết **nguồn để hỏi khi gặp suffix cloud.example.com**. Khi API đổi địa chỉ theo quy trình có kiểm soát, đội cloud cập nhật private zone thay vì thay toàn bộ cấu hình DNS văn phòng.

### 7.3. Workload cloud hỏi erp.office.example.com

~~~text
Workload trong cloud
  -> cloud resolver
  -> rule cho office.example.com
  -> outbound DNS endpoint theo tuyến VPN/private link
  -> DNS on-prem 10.10.0.53 hoặc 10.11.0.53
  -> authoritative data của office.example.com
  -> A 10.10.20.15
  -> kết quả quay về workload
  -> workload kết nối ERP theo policy và route
~~~

**Hai hướng yêu cầu hai loại cấu hình khác nhau**: on-prem forwarding tới inbound cloud và cloud forwarding tới target on-prem qua outbound. Chỉ xây dựng một chiều sẽ khiến một số ứng dụng hoạt động nhưng chiều gọi ngược vẫn thất bại.

## 8. Thẩm quyền, forwarding rule và cách tránh vòng lặp

Sai lầm DNS lai thường không bắt nguồn từ thiếu record mà từ việc **hai resolver không thống nhất ai có thẩm quyền với một suffix**. Nếu cả văn phòng và cloud đều chuyển câu hỏi cho bên còn lại, truy vấn có thể lặp đến khi hết giới hạn và trả SERVFAIL. Nếu một resolver cho rằng mình có authoritative zone nhưng thiếu record, nó có thể trả NXDOMAIN mà không hỏi nơi khác.

### 8.1. Bảng phân quyền authoritative và forwarding

| Suffix | Authoritative source | DNS văn phòng làm gì? | DNS cloud làm gì? |
| --- | --- | --- | --- |
| **example.com** (công cộng) | Public authoritative DNS | Phân giải công cộng theo chính sách mặc định | Phân giải công cộng theo chính sách mặc định |
| **cloud.example.com** (riêng) | Cloud private zone | **Forward** tới cloud inbound endpoint | Tìm trong private zone đã liên kết |
| **office.example.com** (riêng) | DNS on-prem | Trả lời từ zone nội bộ | **Forward** qua cloud outbound endpoint tới DNS on-prem |
| Tên khác ngoài các suffix trên | Authoritative source tương ứng | Theo chính sách recursive DNS hiện có | Theo chính sách recursive DNS hiện có |

Ở đây, **cloud.example.com** và **office.example.com** là hai nhánh tách biệt nên không buộc hai nhóm phải cùng quản lý một zone. Nếu một tổ chức dùng cây tên miền phức tạp hơn (ví dụ parent/child với nhiều private subzone), cần kiểm tra thứ tự chọn rule theo suffix cụ thể nhất, cơ chế delegation và hành vi authoritative NXDOMAIN trên từng resolver.

### 8.2. Những tình huống dễ tạo lỗi

| Tình huống | Điều có thể xảy ra | Phòng tránh |
| --- | --- | --- |
| On-prem forward mọi tên **example.com** vào cloud, còn cloud forward mọi tên **example.com** về on-prem | Vòng lặp hoặc phân giải sai record public | Chuyển **chỉ suffix thuộc quyền mỗi bên**, dùng policy cụ thể |
| Cloud có private zone **example.com** nhưng thiếu **booking.example.com** | Private zone che public zone, có thể trả NXDOMAIN | Tách suffix nội bộ hoặc quản lý split-horizon đầy đủ, kiểm thử bản ghi thiếu |
| Hai DNS đều là authoritative cho cùng private zone với dữ liệu khác nhau | Client thấy kết quả không nhất quán | Quy định một nguồn thẩm quyền hoặc cơ chế đồng bộ/ủy quyền có chủ sở hữu |
| Forwarder dùng cơ chế fallback public khi private endpoint lỗi | Truy vấn private lọt ra DNS ngoài hoặc trả kết quả không mong muốn | Xem xét **forward only** cho zone riêng, thiết kế dự phòng riêng |
| Quy tắc chỉ có cho một chiều kết nối | On-prem→cloud thành công nhưng cloud→on-prem thất bại | Kiểm tra hai luồng riêng với ma trận thử nghiệm |
| Đưa IP resolver endpoint làm NS khi endpoint chỉ nhận truy vấn recursive | Delegation không hoạt động như kỳ vọng | Phân biệt recursive inbound endpoint với authoritative NS |

Khi có nhiều VPC/VNet hoặc nhiều cloud, hãy thiết kế một **bảng ownership và chiều forwarding** cho mọi suffix trước khi tạo hàng loạt rule. Một suffix có thể cần chia nhỏ thành nhiều nhánh, nhưng không nên có hai tuyến mâu thuẫn không có người chịu trách nhiệm.

### 8.3. DNS forwarding có nên fallback sang Internet?

Với **tên riêng**, chính sách forward chỉ đến resolver được cấp quyền thường dễ bảo vệ hơn. Nếu đường riêng lỗi, nên trả lỗi rõ ràng và kích hoạt cảnh báo thay vì âm thầm hỏi public DNS, nơi có thể không có bản ghi hoặc vô tình nhận tên nội bộ.

Với **tên công cộng**, resolver vẫn cần đường phân giải Internet bình thường hoặc một forwarder được phê duyệt. Cân bằng giữa độ tin cậy và không rò rỉ query là một quyết định được ghi lại trong chính sách DNS doanh nghiệp.

## 9. Ví dụ cấu hình conditional forwarding

### 9.1. BIND9 tại on-premises

Nếu DNS văn phòng sử dụng BIND9 làm recursive resolver, một cấu hình minh họa cho suffix cloud có thể như sau:

~~~conf
// Trên recursive DNS on-prem (minh họa, không phải cấu hình hoàn chỉnh).
zone "cloud.example.com" IN {
    type forward;
    forward only;
    forwarders {
        10.42.1.10;  // Cloud inbound resolver, vùng lỗi A
        10.42.2.10;  // Cloud inbound resolver, vùng lỗi B
    };
};
~~~

Ý nghĩa: khi client hỏi tên thuộc **cloud.example.com**, BIND gửi truy vấn đến hai endpoint được cấu hình theo chính sách lựa chọn server của BIND. **forward only** tránh tự tra cứu theo đường khác khi forwarder không trả lời được. Hai IP cần được cấp từ endpoint thật, có kết nối mạng và ACL phù hợp; đây không phải tên DNS để public.

Nếu DNS on-prem cũng quản lý authoritative zone **office.example.com**, cấu hình zone có thể nằm trên cùng dịch vụ hoặc trên authoritative server riêng:

~~~conf
// Trên authoritative DNS nội bộ (chỉ minh họa chức năng).
zone "office.example.com" IN {
    type primary;
    file "/etc/bind/zones/office.example.com.zone";
};
~~~

Trong triển khai thực tế, tên kiểu zone, quyền đọc zone file, giới hạn recursion, view, ACL, DNSSEC validation và cơ chế reload phải được kiểm tra trên phiên bản BIND đang dùng. **Không mở recursive resolver cho toàn Internet** vì có thể bị lợi dụng làm DNS amplification/reflection và làm lộ namespace nội bộ.

### 9.2. Cloud forwarding sang on-premises

Với dịch vụ DNS cloud được quản lý, cấu hình logic có thể biểu diễn:

~~~text
Nguồn truy vấn:
  Workload trong VPC/VNet đã liên kết với DNS ruleset

Quy tắc:
  Suffix: office.example.com
  Hành động: FORWARD
  Đường gửi: outbound DNS resolver endpoint
  Target DNS server:
    - 10.10.0.53
    - 10.11.0.53

Riêng suffix cloud.example.com:
  Trả lời từ private zone cloud.example.com gắn với mạng

Các tên công cộng khác:
  Dùng đường recursive/default resolver đã được phê duyệt
~~~

Đoạn trên là **mô tả chính sách**, không phải Terraform hoặc câu lệnh cấu hình có thể dán trực tiếp vào mọi cloud. Cách tạo forwarding rules, gắn ruleset với mạng và cấu hình outbound endpoint khác nhau theo nhà cung cấp.

### 9.3. Dùng IaC và quản lý thay đổi

Trong dự án thật, nên quản lý zone, bản ghi, association, forwarding rules, firewall rule và resolver endpoint bằng **Infrastructure as Code** khi nền tảng hỗ trợ. Thay đổi cần có review về tác động, owner và cách kiểm tra:

1. Tạo kết nối và endpoint/resolver được phép.
2. Thử trực tiếp truy vấn tới endpoint từ mạng nguồn.
3. Tạo conditional forward cho đúng suffix.
4. Kiểm thử bằng resolver mặc định của client, tránh phải chỉ định endpoint thủ công.
5. Xác minh không phá các truy vấn public và suffix khác.
6. Theo dõi log/metrics và cập nhật runbook.

Không nên đổi đồng thời hàng chục zone và rule trước khi kiểm thử một đường phân giải hoàn chỉnh. Với thay đổi liên quan zone authoritative, cần chú ý TTL và negative caching trước khi chuyển.

## 10. Các điều kiện mạng để hybrid DNS thực sự hoạt động

Một bản ghi hợp lệ không có nghĩa client sẽ tìm được nó. Hybrid DNS cần cả **mạng đi và về**, **resolver được phép trả lời**, và **khả năng kết nối ứng dụng sau khi phân giải**.

| Thành phần | Kiểm tra cần thực hiện |
| --- | --- |
| **Kết nối riêng** | VPN/private connectivity đã hoạt động, có route tới subnet IP resolver và route phản hồi |
| **Firewall/ACL** | Chỉ cho DNS server được phê duyệt gửi truy vấn qua UDP **và TCP** port 53 tới endpoint thích hợp |
| **Network security group** | Inbound endpoint chỉ nhận từ CIDR hoặc IP DNS on-prem đáng tin cậy; outbound được phép tới DNS on-prem |
| **Policy trên DNS server** | Allow-query, allow-recursion, view, ACL và forwarder không từ chối client/resolver hợp lệ |
| **Dự phòng** | Có ít nhất hai IP resolver/endpoint ở các miền lỗi phù hợp khi dịch vụ hỗ trợ; không cùng phụ thuộc một thiết bị duy nhất |
| **NAT và source IP** | DNS target nhìn thấy source IP nào sau VPN/NAT; ACL phải phù hợp với source thực tế |
| **MTU và EDNS(0)** | Response lớn có thể bị cắt ngắn/fragment; DNS phải hoạt động khi chuyển sang TCP |
| **Phân giải địa chỉ kép** | Nếu dùng IPv6, kiểm tra AAAA, định tuyến IPv6, firewall và khả năng IPv6 của resolver/endpoint |
| **Đích ứng dụng** | IP được trả về có route và quyền truy cập trên port ứng dụng, chẳng hạn HTTPS 443 |

**Vì sao cần TCP port 53?** DNS thường dùng UDP để tra cứu thông thường, nhưng TCP được dùng khi response bị cắt ngắn, với một số giao dịch DNS và khi client/resolver chọn dùng TCP. Một hệ thống chỉ cho UDP 53 có thể hoạt động với bản ghi nhỏ nhưng lỗi khó hiểu khi response lớn hoặc DNSSEC cần dữ liệu bổ sung. Không phải cứ thấy timeout DNS là do mất record.

### 10.1. Tách đường truy vấn DNS khỏi đường dữ liệu ứng dụng

Ví dụ, laptop văn phòng phân giải **api.cloud.example.com** thành **10.42.20.15** qua inbound DNS endpoint. Sau đó laptop cần kết nối HTTPS tới **10.42.20.15**. Đường đi đến IP resolver (10.42.1.10) **không tự bảo đảm** có route hoặc firewall rule đến IP ứng dụng (10.42.20.15).

Hãy kiểm tra cả hai:

~~~text
DNS control path:
  On-prem DNS -> VPN/private link -> cloud inbound resolver -> private zone

Application data path:
  On-prem client -> VPN/private link -> private API load balancer / service
~~~

Mô hình tương tự áp dụng chiều cloud → on-prem. Phân biệt hai đường giúp xác định sự cố thật: nếu phân giải thành công nhưng ứng dụng timeout, lỗi có thể nằm ở route, firewall, TLS hoặc chính dịch vụ chứ không phải DNS.

### 10.2. Thiết kế nhiều mạng hoặc tài khoản

Nếu ứng dụng nằm ở nhiều VPC/VNet, hãy xác minh mạng nào nhìn thấy private zone và forwarding rules. Có thể cần liên kết zone, share rule, DNS peering hoặc resolver tập trung tùy provider. Không giả định **network peering đồng nghĩa DNS zone sharing**; đây thường là hai chức năng khác nhau.

Resolver tập trung giúp giảm số endpoint và rule trùng lặp, nhưng cũng tạo **điểm phụ thuộc chung** cần HA, kiểm soát quyền và hạn mức throughput. Resolver phân tán tăng tính tự chủ nhưng làm tăng chi phí, lượng cấu hình và nguy cơ bất nhất. Chọn theo số mạng, owner, độ trễ, tính sẵn sàng và khả năng quản trị.

## 11. Độ tin cậy, TTL và chuyển đổi khi gặp lỗi

DNS là một thành phần của chuỗi phục vụ ứng dụng. Nếu dependency vào DNS không hoạt động, nhiều tác vụ có thể thất bại dù compute và database vẫn bình thường. Vì vậy mục tiêu khôi phục và giám sát DNS cần liên hệ trực tiếp đến các hành trình nghiệp vụ.

### 11.1. Thiết kế theo miền lỗi

- **Public DNS:** Chọn authoritative DNS có khả năng phục vụ đa điểm và chính sách kiểm soát thay đổi phù hợp; nếu dùng nhiều provider, phải giải quyết đồng bộ zone, DNSSEC, delegation và hoạt động khi một bên lỗi.
- **On-prem DNS:** Có resolver/authoritative server dự phòng tại các vùng lỗi thích hợp, không cùng phụ thuộc một máy ảo, nguồn điện hoặc đường truyền duy nhất nếu tác động sự cố lớn.
- **Cloud resolver endpoint:** Khi sản phẩm hỗ trợ, đặt nhiều endpoint IP trên các subnet/zone khác nhau; theo dõi hạn mức và khả năng reachability.
- **Kết nối lai:** Một đường VPN hoặc private connectivity duy nhất có thể là điểm lỗi chung cho DNS và lưu lượng ứng dụng. Đường thứ hai có giá trị khi phù hợp với yêu cầu phục hồi.
- **Client resolver:** Xác minh thứ tự DNS server và hành vi retry của hệ điều hành/runtime; việc liệt kê hai resolver không đảm bảo mọi client tự chuyển ngay sang server còn lại.

### 11.2. Không dùng TTL như giải pháp HA duy nhất

TTL thấp có thể giảm thời gian giữ bản ghi cũ nhưng không giải quyết được mất DNS authoritative/resolver, timeout, kết nối ứng dụng đang mở hoặc dữ liệu chưa đồng bộ. Với chuyển vùng công cộng, xem xét health checks, cân bằng tải toàn cầu và DR ứng dụng. Với private DNS, xem xét HA của endpoint, forwarding và tuyến mạng.

TTL quá thấp có thể gây áp lực lên resolver và phí truy vấn. TTL quá cao khiến thay đổi hướng traffic chậm phản ánh. Cần kiểm tra cả **negative caching** khi tạo record mới sau khi hệ thống trước đó trả NXDOMAIN.

### 11.3. Thiết kế mục tiêu theo mức độ quan trọng

Ví dụ minh họa:

| Luồng | Tác động khi lỗi | Giải pháp độ tin cậy cần đánh giá |
| --- | --- | --- |
| Khách truy cập website công cộng | Mất truy cập, ảnh hưởng doanh thu | Public DNS có HA, giám sát từ Internet, health-based routing nếu cần |
| Ứng dụng cloud kết nối database riêng | Lỗi giao dịch quan trọng | Private zone/endpoint ổn định, failover tương thích database, giám sát từ workload |
| Cloud truy vấn ERP tại văn phòng | Chậm hoặc ngừng đồng bộ | DNS on-prem dự phòng, VPN dự phòng, queue hoặc xử lý lỗi tạm thời nếu nghiệp vụ cho phép |
| Văn phòng truy cập private API cloud | Người dùng nội bộ không thao tác được | Inbound DNS endpoint HA, conditional forwarder dự phòng, tuyến ứng dụng HA |

RTO/RPO không do DNS tự quyết định; DNS là một yếu tố ảnh hưởng đến RTO toàn hệ thống. Cần đo thời gian hồi phục **end-to-end**, không chỉ thời gian cập nhật record.

## 12. Bảo mật và quản trị vòng đời DNS

### 12.1. DNS công cộng

Quyền quản trị tên miền, thay đổi NS/DS, zone và record có thể ảnh hưởng toàn bộ doanh nghiệp. Cần:

- Bảo vệ tài khoản registrar và DNS provider bằng MFA, quyền tối thiểu, quy trình thay đổi và nhật ký audit.
- Tách quyền cập nhật bản ghi ứng dụng khỏi quyền thay đổi delegation, NS, DNSSEC key và cấu hình toàn domain.
- Đánh giá DNSSEC và luân chuyển khóa có kiểm soát nếu sử dụng; việc cấu hình DS không nhất quán có thể làm resolver xác thực thất bại.
- Quản lý CAA, quy trình cấp/gia hạn chứng chỉ và record xác minh domain; không đặt token/secret thật vào record TXT công khai.
- Bảo vệ cơ chế automation cập nhật record: phân quyền theo zone/record nếu nền tảng hỗ trợ, kiểm soát thay đổi và kiểm thử.

### 12.2. DNS nội bộ và lai

- Giới hạn recursive DNS và inbound endpoints cho client/DNS server được cấp quyền. **Không xây dựng open resolver**.
- Chỉ forward các suffix cần thiết; tránh đưa thông tin namespace nội bộ ra resolver công cộng.
- Bảo đảm lưu lượng DNS nội bộ đi trên mạng riêng được bảo vệ; DNS qua UDP/TCP 53 thông thường **không tự mã hóa payload**. Nếu cần mã hóa tầng DNS, đánh giá DoT/DoH hoặc cơ chế phù hợp có hỗ trợ ở cả hai đầu; kết nối VPN có thể bảo vệ đường truyền giữa site nhưng không thay thế mọi chính sách đầu cuối.
- Ngăn sửa record trái phép, lưu audit trail và theo dõi bất thường; hạn chế người có quyền thay đổi zone và resolver rule.
- Xác thực ứng dụng và dùng TLS cho kết nối đến dịch vụ, vì **private DNS không phải biện pháp xác thực hoặc phân quyền**.
- Xem xét quyền riêng tư của DNS query logs: các tên tra cứu có thể phản ánh dịch vụ nội bộ, tài khoản hoặc hành vi truy cập; cần chính sách lưu giữ và truy cập phù hợp.

Các nguy cơ thường được xem xét gồm **DNS spoofing/cache poisoning**, cấu hình sai dẫn đến điều hướng sang đích không mong muốn, **DNS tunneling** làm kênh thoát dữ liệu, DDoS hoặc lạm dụng resolver, và thay đổi record không được ủy quyền. Biện pháp phòng vệ phải dựa vào mô hình đe dọa thực tế, không chỉ bật DNSSEC rồi coi hệ thống đã an toàn toàn diện.

### 12.3. Quyền sở hữu và quản trị record

| Vai trò | Trách nhiệm |
| --- | --- |
| Domain owner / registrar admin | Kiểm soát tên miền gốc, delegation và các thao tác nhạy cảm ở registrar |
| Public DNS owner | Quản lý public zone, DNSSEC, kiểm tra record và thay đổi ảnh hưởng khách hàng |
| Cloud platform team | Quản lý private zones, association, resolver endpoints và forwarding rules |
| Network / on-prem team | Quản lý DNS nội bộ, VPN/routing và firewall cho hybrid DNS |
| Application owner | Định nghĩa hostname, target, kỳ vọng TTL và giám sát tác động đến ứng dụng |
| Security / SRE | Đánh giá quyền, audit, DNS logging, SLO, cảnh báo và diễn tập sự cố |

Với mỗi zone, cần một nguồn thay đổi được phê duyệt; tránh chỉnh record thủ công ở nhiều nơi mà không có quy trình đối chiếu. Khi xóa dịch vụ, phải thu hồi record, quyền và rule liên quan theo kế hoạch để tránh dangling DNS hoặc trỏ nhầm tài nguyên.

## 13. Ánh xạ mô hình vào các nhà cung cấp cloud

Các dịch vụ có cách đặt tên và giới hạn khác nhau. Bảng này chỉ là **bản đồ khái niệm** để chọn thành phần; trước khi triển khai, cần đối chiếu tài liệu hiện hành về region, quota, DNS forwarding, network association và tính năng bảo mật.

| Nhu cầu | AWS | Microsoft Azure | Google Cloud |
| --- | --- | --- | --- |
| DNS công cộng | Route 53 public hosted zone | Azure DNS public zone | Cloud DNS public zone |
| DNS nội bộ | Route 53 private hosted zone gắn với VPC phù hợp | Azure Private DNS zone liên kết VNet | Cloud DNS private zone được cấp quyền cho network |
| Truy vấn on-prem → cloud private DNS | Route 53 Resolver inbound endpoint | Azure DNS Private Resolver inbound endpoint | Cloud DNS inbound forwarding theo server policy và cấu hình mạng phù hợp |
| Truy vấn cloud → on-prem DNS | Route 53 Resolver outbound endpoint + forwarding rule | Azure DNS Private Resolver outbound endpoint + DNS forwarding ruleset | Cloud DNS forwarding zones / outbound server policy theo nhu cầu và giới hạn sản phẩm |
| Kết nối mạng lai | VPN / Direct Connect | VPN Gateway / ExpressRoute | Cloud VPN / Cloud Interconnect |

Những lựa chọn trên không hoàn toàn tương đương 1:1. Ví dụ việc share private zone giữa tài khoản/dự án, cơ chế resolver của spoke network và xử lý tên trùng có thể khác. Khi thiết kế đa cloud, cần ghi rõ **dịch vụ nào có thẩm quyền với suffix nào**, loại endpoint nào nhận được truy vấn và nơi phải đặt forwarding rule.

Một giải pháp tự vận hành BIND/Unbound có thể phù hợp khi có yêu cầu kiểm soát đặc thù hoặc cần tích hợp hệ cũ, nhưng đội phải chịu trách nhiệm HA, patch, backup, monitoring, capacity planning và bảo mật. DNS được quản lý thường giảm gánh vận hành, đổi lại có giới hạn tính năng/chi phí/phạm vi tích hợp cần chấp nhận.

## 14. Kiểm thử đúng từ từng vị trí truy vấn

DNS có thể trả lời khác nhau theo network, resolver, view và trạng thái cache. Vì vậy kiểm thử một truy vấn từ laptop quản trị **không chứng minh** client Internet, máy văn phòng và workload cloud đều hoạt động đúng. Cần một ma trận kiểm thử với nguồn, resolver thực dùng, tên, loại record, kết quả mong đợi và đường kết nối ứng dụng.

### 14.1. Ma trận kết quả mong đợi

| Vị trí / resolver | **booking.example.com** | **api.cloud.example.com** | **erp.office.example.com** |
| --- | --- | --- | --- |
| Internet / public recursive resolver | Địa chỉ hoặc alias **công cộng** | Không được nhận bản ghi của private zone từ public DNS | Không được nhận bản ghi của private zone từ public DNS |
| VPC/VNet được phép / cloud resolver | Public entrypoint theo chính sách | **10.42.20.15**, nếu zone được liên kết và record tồn tại | **10.10.20.15** qua rule forward về on-prem |
| Mạng văn phòng / on-prem recursive resolver | Public entrypoint theo chính sách | **10.42.20.15** qua forward đến inbound cloud endpoint | **10.10.20.15** từ authoritative DNS on-prem |
| VPC/VNet **không** được cấp quyền private zone | Public entrypoint theo chính sách | Không được giả định phân giải được private zone | Chỉ phân giải nếu được thiết kế và cấp quyền riêng |

Kết quả của các tên private từ mạng không được phép có thể là NXDOMAIN, NODATA, REFUSED hoặc lỗi khác tùy kiến trúc resolver; tiêu chí chính là **không nhận được dữ liệu riêng thông qua đường không được ủy quyền**, đồng thời không phá DNS công cộng.

### 14.2. Các lệnh kiểm tra với dig

Các lệnh sau là ví dụ để chạy **tại vị trí có quyền truy vấn** và sau khi thay domain/IP ví dụ thành địa chỉ lab thật. **example.com** và các IP trong bài không đại diện cho bản ghi đang tồn tại trong Internet.

Từ máy được phép ở văn phòng:

~~~bash
# Kiểm tra đường mặc định: máy -> recursive DNS on-prem -> cloud inbound
dig @10.10.0.53 api.cloud.example.com A +time=2 +tries=1

# Kiểm tra trực tiếp inbound cloud DNS để tách lỗi forwarder on-prem
dig @10.42.1.10 api.cloud.example.com A +time=2 +tries=1

# Kiểm tra TCP fallback trên endpoint được cấp quyền
dig +tcp @10.42.1.10 api.cloud.example.com A

# Kiểm tra tên on-prem tại nguồn authoritative/recursive đã định nghĩa
dig @10.10.0.53 erp.office.example.com A
~~~

Từ workload trong cloud dùng DNS mặc định đã cấu hình:

~~~bash
# Kiểm tra rule cloud -> outbound endpoint -> on-prem DNS
dig erp.office.example.com A +time=2 +tries=1

# Kiểm tra private zone cloud tại chính mạng đang chạy
dig api.cloud.example.com A +time=2 +tries=1

# Kiểm tra ứng dụng vẫn phân giải được một tên công cộng
dig booking.example.com A
~~~

Từ môi trường thử nghiệm Internet:

~~~bash
# Kiểm tra đường public recursive DNS -> authoritative public zone
dig @1.1.1.1 booking.example.com A

# Xem chuỗi delegation của public domain (không dùng cho private-only zone)
dig +trace booking.example.com A
~~~

Không gửi tên nội bộ nhạy cảm của production ra resolver công cộng chỉ để thử bảo mật; nếu cần kiểm tra vùng private không bị công bố, thực hiện với **tên thử nghiệm được phê duyệt** và kiểm tra cấu hình authoritative public zone.

Một số trường của kết quả **dig** cần hiểu:

- **status: NOERROR** có nghĩa truy vấn được xử lý thành công về mặt DNS, **không bảo đảm có bản ghi A**. Nếu không có A nhưng tên tồn tại với loại khác, có thể nhận NOERROR với ANSWER rỗng (*NODATA*).
- **status: NXDOMAIN** cho biết tên không tồn tại theo nguồn trả lời được resolver chấp nhận; kiểm tra có bị private zone che hoặc cache âm không.
- **status: SERVFAIL** báo lỗi xử lý/truy vấn; có thể do upstream, DNSSEC validation, forwarding loop hoặc lỗi backend DNS.
- **status: REFUSED** thường gợi ý chính sách ACL, recursion hoặc quyền truy vấn.
- **Timeout** khác NXDOMAIN; kiểm tra tuyến mạng, firewall, DNS server availability và source IP.
- Trường **SERVER** cho biết server đã trả lời truy vấn từ góc nhìn máy chạy lệnh; không phải bằng chứng nó là authoritative source cuối cùng.
- **ANSWER / AUTHORITY / ADDITIONAL** và TTL còn lại giúp xác định dữ liệu và chuỗi trả lời, nhưng resolver có thể dùng cache.

### 14.3. Kiểm tra cả kết nối sau DNS

Nếu lệnh dig trả **10.42.20.15** đúng mà client vẫn không gọi được API, hãy kiểm tra thêm tuyến route, ACL/security group, port ứng dụng, TLS certificate, SNI và chính sách xác thực. Thử truy cập ứng dụng phải dùng **hostname mong đợi** để đánh giá TLS/SNI; kết nối thô tới IP có thể cho kết quả khác.

Khi kiểm chứng failover, nên mô phỏng một endpoint không truy cập được trong môi trường thử nghiệm được phép, rồi đo thời gian client chuyển sang endpoint còn lại. Sau đó thực hiện tương tự với mất liên kết VPN/on-prem DNS nếu đây là kịch bản có trong mục tiêu độ tin cậy. Đừng chỉ xác nhận bản ghi đúng lúc hệ thống khỏe.

## 15. Cách chẩn đoán sự cố DNS theo triệu chứng

Sự cố DNS dễ bị nhầm với lỗi ứng dụng hoặc mạng. Một quy trình chẩn đoán tốt đi theo hướng: **client hỏi resolver nào → resolver chọn rule/zone nào → truy vấn đi qua đường nào → nguồn authoritative trả gì → kết quả có được cache không → ứng dụng có kết nối được IP nhận về không?**

| Triệu chứng | Nguyên nhân cần xem xét | Bước kiểm tra tiếp |
| --- | --- | --- |
| **NXDOMAIN** khi hỏi một tên private vừa tạo | Private zone không có record, private zone khác che dữ liệu, cache âm, sai suffix | Hỏi trực tiếp resolver đúng zone; kiểm tra zone association, SOA/authority và TTL âm |
| **SERVFAIL** cho một suffix, tên công cộng khác vẫn tốt | Forwarding loop, upstream không trả lời, DNSSEC validation, lỗi recursive resolver | So sánh truy vấn trên từng hop; kiểm tra logs, forwarding rules và DNSSEC |
| **Timeout** khi hỏi cloud inbound endpoint | VPN/route, firewall UDP/TCP 53, endpoint unavailable, ACL hoặc source IP khác dự tính | Kiểm tra reachability từ DNS on-prem, route đi/về, packet/log tại hai đầu |
| **REFUSED** | Client hoặc target không có quyền dùng recursion/query | Xem allow-recursion, allow-query, resolver policy và network association |
| Có **A** nhưng không có **AAAA** hoặc ngược lại | Record type/IPv6 policy khác mong đợi | Hỏi riêng A/AAAA, kiểm tra địa chỉ và khả năng định tuyến giao thức |
| Query nhỏ chạy, query lớn thất bại | Chặn TCP 53, EDNS(0), MTU hoặc fragmentation | Thử truy vấn +tcp và kiểm tra đường UDP/TCP, kích thước response |
| On-prem → cloud OK, cloud → on-prem lỗi | Thiếu outbound rule, route hoặc DNS on-prem không cho phép source endpoint | Tra cứu tại cloud resolver, kiểm tra cloud outbound và ACL phía văn phòng |
| Tên đúng từ một VPC nhưng lỗi ở VPC khác | Private zone chưa link, ruleset chưa association hoặc DNS peering khác biệt | So sánh cấu hình network association và resolver thực dùng |
| Client có IP cũ sau đổi record | Cache ở OS/runtime/recursive, TTL, negative caching hoặc kết nối cũ | Kiểm tra TTL từng hop và tiến trình kết nối; so sánh authoritative với client |
| DNS đúng nhưng HTTP vẫn timeout / TLS lỗi | Sai route đến đích, security group, service health, certificate/SNI | Kiểm tra đường dữ liệu và dịch vụ, không tiếp tục sửa DNS khi lời giải đã đúng |
| Một số tên public lỗi sau khi thêm private zone lớn | Split-horizon che bản ghi public | Kiểm tra private zone cùng suffix, các record thiếu và chính sách fallback |

### 15.1. Quy trình điều tra có thể tái sử dụng

1. **Ghi nhận bằng chứng:** thời gian, nguồn truy vấn, DNS server được dùng, tên, record type, kết quả, TTL và tỷ lệ lỗi.
2. **So sánh các vị trí:** public, on-prem, cloud network A, cloud network B; tìm ranh giới mà kết quả bắt đầu khác nhau.
3. **Đi theo từng hop:** recursive resolver của client → conditional forwarder → inbound/outbound endpoint → nguồn authoritative; không nhảy thẳng tới việc sửa zone.
4. **Xác nhận DNS và network riêng:** kiểm tra UDP/TCP 53, VPN route, ACL và sau đó port ứng dụng.
5. **Kiểm tra cache:** thử truy vấn tới authoritative/source phù hợp để phân biệt dữ liệu đã đổi với cache còn giữ kết quả cũ.
6. **Khắc phục trong phạm vi nhỏ:** sửa rule/record/ACL có bằng chứng; thử lại các truy vấn public và private liên quan để tránh tác động dây chuyền.
7. **Cập nhật runbook:** lưu tình huống lỗi, điều kiện phát hiện, owner và cách kiểm tra sau thay đổi.

### 15.2. Giám sát và cảnh báo

Một thiết kế trưởng thành kết hợp ba lớp quan sát:

- **Synthetic DNS probes:** Từ Internet và các vị trí mạng nội bộ tiêu biểu, truy vấn định kỳ một tập tên quan trọng rồi kiểm tra response code, dữ liệu mong đợi và latency.
- **Resolver/endpoint metrics:** Theo dõi tỷ lệ thành công, SERVFAIL, REFUSED, timeout, độ trễ, throughput, lỗi forwarding, hạn mức và mức sử dụng.
- **Application symptoms:** Theo dõi lỗi connect, DNS resolution failure, request timeout và tác động đến SLO của các hành trình nghiệp vụ.

Đừng chỉ cảnh báo khi DNS server không ping được: resolver có thể còn chạy nhưng trả sai dữ liệu hoặc có lỗi với một suffix cụ thể. Log cần có chính sách lưu giữ, quyền truy cập và ẩn thông tin nhạy cảm phù hợp.

## 16. Đánh đổi kiến trúc theo Well-Architected

DNS ảnh hưởng đồng thời tới nhiều mục tiêu; một thay đổi tốt cho một phía có thể khiến phía khác phức tạp hơn.

| Góc nhìn Well-Architected | Quyết định thường gặp | Đánh đổi cần đánh giá |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Chuẩn hóa naming, IaC, owner, logs, quy trình đổi record | Giảm lỗi thủ công nhưng cần governance và kiểm soát change blast radius |
| **Security / Bảo mật** | Private zones, giới hạn recursion, DNSSEC public, ACL theo nguồn, DNS logging | Tăng bảo vệ nhưng thêm trách nhiệm key, quyền, privacy và policy |
| **Reliability / Độ tin cậy** | Resolver HA, nhiều endpoint, tuyến VPN dự phòng, health-based routing | Độ sẵn sàng tốt hơn nhưng tăng chi phí và điểm cấu hình cần thử nghiệm |
| **Performance Efficiency / Hiệu quả hiệu năng** | DNS gần workload, TTL/cache phù hợp, resolver tập trung hay phân tán | Cache giảm latency và query volume nhưng có thể giữ dữ liệu cũ |
| **Cost Optimization / Tối ưu chi phí** | Managed DNS, central resolver, số endpoint, logs, private connectivity | Giảm công vận hành có thể tăng phí dịch vụ; tối ưu hóa toàn bộ chi phí sở hữu |
| **Sustainability / Bền vững** | Tránh DNS query lặp, cấu hình dư thừa và tài nguyên nhàn rỗi | Tối ưu tài nguyên phải giữ đủ dự phòng theo yêu cầu |

### 16.1. Tập trung hay phân tán resolver?

**Resolver tập trung** có thể giúp quản lý suffix, giám sát và kết nối on-prem ở một nơi; phù hợp khi tổ chức có platform team mạnh. Nhưng nó có thể tăng dependency liên vùng/mạng, blast radius và chi phí truyền tải nếu mọi ứng dụng đều đi qua một hub.

**Resolver phân tán** đem lại tự chủ và có thể giảm phụ thuộc mạng xuyên vùng, nhưng cần nhiều endpoint, IaC module, quyền, quy trình cập nhật và kiểm toán. Một phương án thực dụng là giữ **quản trị nhất quán** nhưng đặt điểm phân giải theo miền lỗi/địa lý cần thiết; quyết định từ dữ liệu tải, độ trễ và mô hình tổ chức.

### 16.2. Chỉ số cần đưa vào thiết kế

| Chỉ số | Cách đo | Ý nghĩa |
| --- | --- | --- |
| Tỷ lệ truy vấn thành công theo tên quan trọng | Synthetic probe từ mỗi vị trí, phân loại response code | Phát hiện mất phân giải hoặc sai dữ liệu |
| Latency p50/p95/p99 của truy vấn | Đo tại client/resolver và theo suffix | Phát hiện chậm do network, forwarding hoặc resolver |
| Tỷ lệ lỗi theo lớp | NXDOMAIN bất thường, SERVFAIL, REFUSED, timeout | Xác định lỗi dữ liệu, policy hoặc kết nối |
| Thời gian nhận record mới | Đo trước/sau thay đổi ở các recursive resolver đại diện | Đánh giá TTL, cache và quy trình phát hành |
| Thời gian phục hồi khi endpoint/link lỗi | Diễn tập từ client thật; đo cả khả năng kết nối ứng dụng | Đối chiếu với SLO/RTO của nghiệp vụ |
| Chi phí DNS | Hosted zones, query volume, endpoints, traffic, logs, vận hành | Tối ưu hóa dựa trên tổng chi phí |

Chỉ số và ngưỡng cảnh báo cần được thỏa thuận theo mức độ quan trọng của từng hành trình. **Không đặt mục tiêu “DNS luôn trả lời 100%”** nếu chưa xác định vị trí đo, loại truy vấn, cửa sổ đánh giá và trách nhiệm của các dependency.

## 17. Bài thực hành: thiết kế hybrid DNS cho hệ thống đặt hàng

Một doanh nghiệp có website bán hàng công khai, ERP ở trung tâm dữ liệu và cụm dịch vụ nội bộ trên cloud. Trong sáu tháng tới, công ty chuyển phần API đơn hàng lên cloud nhưng giữ ERP on-prem. Công ty có hai văn phòng, một VPN chính và nhiều VPC/VNet; nhóm vận hành muốn đảm bảo luồng xác nhận đơn hàng không bị dừng chỉ vì một DNS endpoint hoặc một DNS server gặp sự cố.

Thông tin giả định:

- Public domain: **shop.example.com** phục vụ khách từ Internet.
- Private cloud API: **orders.cloud.example.com**, không công bố trên Internet.
- ERP nội bộ: **erp.office.example.com**.
- On-prem DNS: hai server trong hai vùng lỗi khác nhau.
- Cloud networking: các workload ứng dụng phân tán ở hai network ảo; chưa chắc private zone/ruleset đã liên kết với cả hai.
- Cloud↔on-prem có kết nối riêng, nhưng kế hoạch dự phòng link chưa được phê duyệt.

**Yêu cầu bài làm:**

1. Vẽ sơ đồ thể hiện **public authoritative DNS, DNS on-prem, private zone cloud, cloud inbound/outbound endpoints, kết nối riêng và các client ở ba vị trí**.
2. Lập bảng **suffix → authoritative source → resolver chuyển tiếp → network được phép truy vấn**. Chỉ rõ ai sở hữu và phê duyệt từng zone.
3. Chọn cách tổ chức zone để tránh vòng lặp, tránh trùng suffix và không rò rỉ tên nội bộ. Nếu dùng split-horizon, giải thích bản ghi nào phải được đồng bộ.
4. Viết chính sách conditional forwarding hai chiều và các rule mạng cho **UDP/TCP 53**, gồm IP nguồn thực tế và đường route phản hồi.
5. Tạo **ma trận ít nhất 9 phép thử**: ba tên từ ba vị trí; nêu rõ kết quả mong đợi, cách kiểm tra, trường hợp query không được phép và sự khác biệt với đường ứng dụng.
6. Đề xuất cách ứng phó khi **mất một inbound endpoint**, **mất một DNS on-prem** và **mất VPN**. Nêu yếu tố DNS không thể tự giải quyết, chẳng hạn việc ứng dụng không còn tuyến kết nối ERP.
7. Chọn TTL công cộng và riêng cho tình huống có yêu cầu chuyển tuyến; giải thích ảnh hưởng cache, negative caching và số lượng truy vấn. Không cần đưa con số cố định khi chưa có SLO.
8. Viết một **Architecture Decision Record** ngắn: chọn mô hình resolver tập trung hay phân tán, các phương án bị loại, rủi ro, chi phí và điều kiện xem lại.

### Gợi ý đánh giá bài làm

Một phương án đạt yêu cầu cần giữ public zone riêng và dễ phân giải từ Internet, phân giải hai chiều cho namespace private qua đúng DNS source, không có forwarding loop, và có quyền truy vấn theo nguyên tắc tối thiểu. Ma trận test phải chứng minh được **phân giải từ network thật**, không chỉ sự tồn tại của bản ghi trong console.

Trong phần DR, cần phân biệt:

- **DNS vẫn phân giải được nhưng VPN mất:** Client có thể nhận IP private hợp lệ song không kết nối ứng dụng on-prem/cloud qua đường đã mất.
- **DNS endpoint lỗi nhưng tuyến ứng dụng còn:** Có thể cần resolver endpoint dự phòng, forwarding timeout phù hợp và retry.
- **Tên sai do split-horizon:** Có thể cần chỉnh zone/rule và chờ cache hết hạn; chỉ tăng số server không sửa được dữ liệu sai.

## 18. Checklist trước khi đưa DNS vào production

- [ ] Đã liệt kê client, mạng nguồn, hostname, loại bản ghi và kết quả mong đợi theo từng vị trí.
- [ ] Mỗi public/private zone có **authoritative source, chủ sở hữu và phương thức quản lý thay đổi** rõ.
- [ ] Namespace công cộng, cloud riêng và on-prem riêng được quy hoạch; các trường hợp split-horizon được ghi rõ.
- [ ] Public domain delegation, NS/SOA, CAA và DNSSEC (nếu dùng) được kiểm tra cùng quy trình chứng chỉ.
- [ ] Private zone đã được liên kết với đúng VPC/VNet/account/project; không giả định liên kết mạng tự chia sẻ DNS.
- [ ] Đã định nghĩa **on-prem → cloud inbound** và **cloud → on-prem outbound** theo suffix cụ thể.
- [ ] Không có vòng lặp forwarding, quy tắc phủ quá rộng hoặc hành vi fallback công cộng ngoài ý muốn.
- [ ] Có route đi/về, source IP đúng, firewall/ACL cho **UDP và TCP 53**, kiểm tra NAT và các phản hồi DNS lớn.
- [ ] Có phương án dự phòng cho resolver, DNS on-prem và đường mạng lai theo mức độ quan trọng nghiệp vụ.
- [ ] Đã đo và chọn TTL/negative caching phù hợp với thay đổi bản ghi, scaling và chuyển tuyến.
- [ ] DNS query logs, audit, IAM, quyền thay đổi record và giới hạn recursion được cấu hình theo chính sách.
- [ ] Synthetic probes từ Internet, on-prem và từng cloud network quan trọng xác minh đúng response và latency.
- [ ] Có runbook phân biệt **NXDOMAIN, SERVFAIL, REFUSED, timeout và kết nối ứng dụng thất bại**.
- [ ] Đã diễn tập ít nhất các lỗi DNS/đường mạng phù hợp với SLO/RTO; có owner xử lý và kế hoạch rollback.
- [ ] Chi phí zone, endpoint, query, kết nối riêng, logging và nhân lực vận hành nằm trong đánh giá kiến trúc.

**Ghi nhớ:** DNS công cộng xác định cách người dùng Internet tìm ứng dụng; DNS nội bộ tạo không gian tên có giới hạn truy cập cho dịch vụ riêng; hybrid DNS kết nối hai thế giới bằng **quy tắc thẩm quyền và forwarding có chủ đích**. Thiết kế tốt bắt đầu từ quyền sở hữu zone, đường truy vấn ở từng vị trí và cơ chế dự phòng, sau đó chứng minh bằng kiểm thử mạng, DNS và ứng dụng thực tế. Những quyết định về TTL, bảo mật, cloud resolver và kết nối lai phải được xem xét cùng các đánh đổi Well-Architected về tin cậy, hiệu năng, chi phí và vận hành.
