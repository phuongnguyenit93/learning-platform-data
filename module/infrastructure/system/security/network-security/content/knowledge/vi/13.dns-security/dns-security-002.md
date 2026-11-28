# Recursive và authoritative DNS: vai trò, luồng phân giải và an toàn mạng

Trong chương **DNS security** thuộc module **SECURITY_NETWORK_SECURITY**, việc phân biệt **recursive DNS resolver** (máy chủ phân giải đệ quy) và **authoritative DNS server** (máy chủ DNS có thẩm quyền) là nền tảng để thiết kế bảo vệ DNS, phân tích lưu lượng, đặt firewall rule, theo dõi xâm nhập và xử lý sự cố truy cập dịch vụ. Cả hai đều sử dụng hệ thống tên miền DNS, nhưng có **trách nhiệm, dữ liệu, quan hệ tin cậy và bề mặt tấn công khác nhau**.

Khi một người dùng mở trang web, trình duyệt cần biết địa chỉ IP của tên miền. Recursive resolver thay người dùng **tìm câu trả lời**, có thể sử dụng cache và hỏi nhiều máy chủ DNS khác. Authoritative server **công bố câu trả lời có thẩm quyền cho vùng DNS (zone) mà mình phụ trách**. Nhầm hai vai trò dễ dẫn đến việc mở dịch vụ recursion ra Internet, cấp quyền chuyển vùng DNS quá rộng, hoặc đưa ra kết luận sai từ DNS log.

Sau bài học, bạn có thể:

- Phân biệt **stub resolver, recursive resolver, root/TLD server và authoritative server** trong quá trình phân giải DNS.
- Mô tả cơ chế iterative query, delegation, referral, NS/glue, bản ghi SOA và vòng đời cache.
- Đọc các trường quan trọng của DNS query/response, phân biệt kết quả authoritative, recursive và lỗi phân giải.
- Giải thích vì sao **DNSSEC** bảo vệ tính xác thực/toàn vẹn dữ liệu DNS, còn **DoT/DoH** bảo vệ kênh truyền trên từng chặng được hỗ trợ.
- Lựa chọn các control cho DNS recursion, DNS authoritative, zone transfer, chống cache poisoning và DNS amplification.
- Kiểm tra luồng phân giải, cấu hình mạng và triệu chứng lỗi bằng lệnh DNS thông dụng và log có quyền truy cập.

## 1. Bức tranh tổng thể: hai vai trò không thể thay thế cho nhau

DNS là hệ thống phân cấp, phân tán, ánh xạ tên như **www.example.test** sang một hoặc nhiều dữ liệu DNS, chẳng hạn bản ghi **A**, **AAAA**, **MX**, **TXT**, **NS**. Tên **example.test** và các địa chỉ trong ví dụ được dùng để học tập, không ngụ ý là dịch vụ thật.

| Tiêu chí | Recursive resolver | Authoritative DNS server |
| --- | --- | --- |
| **Khách hàng chính** | Máy người dùng, ứng dụng, DNS forwarder hoặc một resolver khác | Recursive resolver và các bên cần hỏi dữ liệu thuộc zone |
| **Nhiệm vụ** | Nhận yêu cầu, tìm lời giải đầy đủ theo chính sách, trả kết quả cho client | Trả lời từ dữ liệu zone được quản lý hoặc chỉ ra delegation |
| **Nguồn dữ liệu** | Cache, truy vấn tới DNS khác, local policy, forwarder nếu được cấu hình | Zone file/database và các bản ghi/metadata được quản trị |
| **Cache** | Thiết yếu để giảm độ trễ, số truy vấn và tải lên hạ tầng DNS | Không phụ thuộc cache đệ quy để công bố bản ghi thuộc zone |
| **Recursion** | Có thể thực hiện recursion cho client đã được phép | Thông thường không cung cấp recursion cho Internet |
| **Cờ DNS thường gặp** | Có thể đặt **RA=1** khi hỗ trợ recursion; câu trả lời từ cache thường **AA=0** | Trả lời authoritative có thể mang **AA=1** cho tên thuộc quyền quản lý |
| **Rủi ro nổi bật** | Open resolver, cache poisoning, lạm dụng truy vấn, quyền riêng tư của DNS logs | Zone manipulation, lộ AXFR, tấn công DDoS, cấu hình delegation/DNSSEC sai |
| **Control trọng tâm** | ACL recursion, validation DNSSEC, cache protection, egress policy, monitoring | Tách recursion, bảo vệ cập nhật zone, giới hạn AXFR, DNSSEC signing, HA/anycast |

**Hai vai trò có thể chạy trên cùng phần mềm hoặc máy chủ**, nhưng nên tách chức năng, quyền truy cập và cấu hình theo yêu cầu bảo mật. Một authoritative server public không nên tự động chấp nhận truy vấn recursion từ bất kỳ client Internet nào. Ngược lại, một recursive resolver nội bộ chỉ nên cho các mạng/danh tính được cấp phép sử dụng.

### 1.1. Các thành phần tham gia phân giải tên

1. **Ứng dụng:** trình duyệt hoặc service cần phân giải một tên miền.
2. **Stub resolver:** thành phần của hệ điều hành hoặc runtime nhận yêu cầu ứng dụng, gửi DNS query tới resolver đã cấu hình; thường không tự đi hỏi root/TLD/authoritative.
3. **Recursive resolver:** thực hiện việc tìm và trả lời; có thể cache bản ghi, kiểm tra DNSSEC và áp policy.
4. **Root DNS:** authoritative cho root zone **.**; chủ yếu hướng dẫn resolver đến máy chủ TLD thích hợp.
5. **TLD authoritative:** authoritative cho vùng như **.com**, **.org** hoặc **.test** tùy trường hợp; trả referral đến zone cấp dưới.
6. **Authoritative của domain:** phục vụ zone cụ thể và trả dữ liệu cuối cùng hoặc referral đến zone được ủy quyền sâu hơn.

Một DNS server nhận query không nhất thiết chỉ thực hiện một trong hai vai trò: thiết bị DNS forwarder có thể chuyển tiếp, cache một phần; resolver nội bộ có thể đồng thời phục vụ zone riêng. Cần xác định **cấu hình và chính sách cho từng view/client** thay vì gán vai trò chỉ từ tên phần mềm.

## 2. Luồng phân giải: client hỏi một lần, recursive hỏi nhiều nơi

Giả sử client muốn tìm bản ghi **A** cho **www.example.test** và recursive resolver không có cache phù hợp. Trong một môi trường DNS chuẩn có delegation tương ứng, luồng khái niệm là:

~~~mermaid
sequenceDiagram
    participant C as Stub resolver / Client
    participant R as Recursive resolver
    participant Root as Root DNS
    participant TLD as TLD authoritative
    participant Auth as Authoritative example.test
    C->>R: Q: www.example.test A (RD=1)
    R->>Root: Q: www.example.test A (iterative)
    Root-->>R: Referral tới máy chủ TLD
    R->>TLD: Q: www.example.test A (iterative)
    TLD-->>R: Referral tới NS của example.test
    R->>Auth: Q: www.example.test A
    Auth-->>R: Answer A + TTL (nếu có)
    R->>R: Kiểm tra và lưu cache theo policy/TTL
    R-->>C: Answer A, hoặc trạng thái lỗi
~~~

Đây là **mô hình chuẩn hóa để học**; truy vấn thực có thể khác do cache, DNSSEC, QNAME minimization, forwarder, CNAME, delegation nhiều tầng hoặc tối ưu của resolver. TLD **.test** là tên miền dành riêng cho thử nghiệm, do đó sơ đồ ví dụ không yêu cầu cơ sở hạ tầng Internet công cộng thực sự có bản ghi cho **example.test**.

### 2.1. Hai kiểu truy vấn: recursive và iterative

**Recursive query:** client yêu cầu resolver cung cấp câu trả lời cuối cùng hoặc báo lỗi theo khả năng và policy của resolver. Trong DNS header, bit **RD (Recursion Desired)** thể hiện mong muốn này. Resolver có thể trả lời ngay từ cache hoặc cần truy vấn thêm.

**Iterative query:** resolver hỏi một nameserver và chấp nhận câu trả lời hoặc **referral** đến nameserver gần hơn trong cây DNS. Root/TLD không cần thay mặt client đi tìm đến cuối tên miền.

Điểm quan trọng:

- **RD=1** là yêu cầu muốn recursion, không phải bằng chứng server chắc chắn đã hoặc sẽ thực hiện recursion.
- **RA=1** trong phản hồi cho biết server báo rằng tính năng recursion khả dụng; việc client cụ thể được sử dụng vẫn chịu ACL/policy.
- **AA=1** trong phản hồi cho biết server coi câu trả lời là authoritative trong ngữ cảnh được trả lời; **AA không phải chứng thực bằng mật mã**.
- Resolver có thể lấy dữ liệu từ cache, do đó client không thấy toàn bộ các truy vấn iterative phía sau.

### 2.2. Khi recursive đã có cache

~~~text
Client A -> Resolver: www.example.test A ?
Resolver -> Cache: còn bản ghi hợp lệ, TTL chưa hết
Resolver -> Client A: trả lời ngay, không cần hỏi authoritative

Client B -> Resolver: www.example.test A ?
Resolver -> Cache: dùng lại dữ liệu nếu còn hợp lệ
Resolver -> Client B: trả lời
~~~

Cache cải thiện độ trễ và giảm số request đến authoritative server. Tuy nhiên, việc sửa bản ghi tại authoritative **không lập tức xóa** các bản sao đang được cache ở mọi recursive resolver. Đó là lý do kế hoạch đổi IP dịch vụ cần quan tâm TTL và thời gian triển khai.

## 3. DNS zone, delegation, referral và glue

### 3.1. Domain khác zone

**Domain name** mô tả vị trí trong cây tên DNS. **Zone** là phần dữ liệu DNS mà một tập authoritative server được giao quản lý. Ranh giới zone có thể được tách khi ủy quyền một subdomain.

Ví dụ:

~~~text
.
└── test
    └── example.test       [zone do một nhóm authoritative quản lý]
        ├── www.example.test
        ├── api.example.test
        └── research.example.test
            └── app.research.example.test
~~~

Nếu **research.example.test** được delegation tới nameserver riêng, nó có thể trở thành **zone độc lập**. Authoritative của **example.test** sẽ công bố delegation (NS) cho zone con thay vì giữ quyền quản lý trực tiếp mọi bản ghi phía dưới.

### 3.2. NS, SOA và referral

| Bản ghi / khái niệm | Vai trò | Điều cần nhớ về bảo mật |
| --- | --- | --- |
| **NS** | Chỉ định nameserver phục vụ một zone hoặc delegation | Sửa NS sai có thể dẫn truy vấn tới hạ tầng không đúng |
| **SOA** | Chứa metadata zone như primary nameserver, mailbox quản trị dạng DNS, serial và các thông số thời gian | Serial hỗ trợ cơ chế theo dõi cập nhật zone; trường minimum tham gia negative caching theo quy tắc hiện hành |
| **A / AAAA** | Ánh xạ tên tới địa chỉ IPv4/IPv6 | Dữ liệu bị sửa sai có thể dẫn client đến endpoint giả mạo |
| **CNAME** | Alias tên tới một tên khác, yêu cầu resolver tiếp tục phân giải tên đích | CNAME có thể dẫn tới zone khác; alias không tự bảo đảm cùng chủ sở hữu |
| **MX** | Chỉ định mail exchanger cho domain | Sai cấu hình có thể ảnh hưởng định tuyến email |
| **DS / DNSKEY / RRSIG** | Thành phần của xác thực DNSSEC | Phải quản lý đúng chuỗi tin cậy và vòng đời khóa |

**Referral** thông thường chứa NS của zone con trong **Authority section**. Có thể đi kèm địa chỉ **glue** trong **Additional section** khi cần. Referrals không đồng nghĩa authoritative trả lời bản ghi A/AAAA cuối cùng của tên đang hỏi.

### 3.3. Vì sao có glue?

Giả sử zone **example.test** giao cho **ns1.example.test**. Để hỏi authoritative, resolver phải biết địa chỉ IP của **ns1.example.test**, nhưng tên nameserver này lại nằm ngay trong zone cần truy vấn. Parent zone có thể cung cấp **glue A/AAAA** để tránh phụ thuộc vòng:

~~~text
Parent zone:
  example.test.      NS   ns1.example.test.
  ns1.example.test.  A    192.0.2.53       # Glue minh họa

Child zone:
  example.test.      NS   ns1.example.test.
  ns1.example.test.  A    192.0.2.53       # Bản ghi trong zone
~~~

Glue là **thông tin hỗ trợ tìm nameserver**, không phải mặc nhiên là nguồn đáng tin cuối cùng cho mọi truy vấn tới tên đó. Resolver cần áp quy tắc chấp nhận dữ liệu đúng phạm vi (bailiwick) và tránh cho dữ liệu bên ngoài phạm vi thích hợp làm nhiễm cache.

Đối với hệ thống production, cần kiểm tra **NS tại parent và child**, địa chỉ glue (nếu cần), khả năng truy cập nameserver và tính nhất quán của zone. Sai delegation có thể gây lỗi truy vấn diện rộng dù máy chủ ứng dụng vẫn hoạt động.

## 4. Đọc gói DNS và ý nghĩa các trường thường gặp

DNS message cơ bản có **Header, Question, Answer, Authority, Additional**. Giao thức có thể được truyền qua nhiều transport và có extension, nhưng những trường sau rất quan trọng khi phân tích:

| Trường | Chức năng | Cách đọc trong điều tra |
| --- | --- | --- |
| **Transaction ID** | Ghép query với response theo phạm vi giao tiếp | Cần phối hợp tuple và thời gian; không phải chứng thực nguồn |
| **QR** | Phân biệt query (0) và response (1) | Dùng để xác định hướng trao đổi |
| **OPCODE** | Loại hoạt động DNS | Query thông thường hoặc thao tác khác theo chuẩn |
| **RD** | Recursion Desired | Client mong muốn resolver làm recursion |
| **RA** | Recursion Available | Server quảng bá recursion khả dụng |
| **AA** | Authoritative Answer | Server coi response authoritative trong ngữ cảnh hiện tại |
| **TC** | Truncated | Dữ liệu bị cắt ngắn; client/resolver có thể cần retry bằng TCP hoặc transport khác theo cơ chế hỗ trợ |
| **AD / CD** | Các bit liên quan xác thực DNSSEC | AD phản ánh dữ liệu đã được xác thực theo ngữ cảnh resolver; CD yêu cầu không chặn dữ liệu vì việc kiểm tra DNSSEC nếu được hỗ trợ |
| **RCODE** | Trạng thái phản hồi | NOERROR, NXDOMAIN, SERVFAIL, REFUSED... |
| **QNAME / QTYPE / QCLASS** | Tên, loại và lớp dữ liệu được hỏi | Ví dụ hỏi A hoặc AAAA cho một hostname |
| **TTL** | Thời gian dữ liệu RR có thể được cache theo quy tắc | Hết TTL cần xem xét truy vấn mới; resolver có thể có chính sách riêng |
| **Answer / Authority / Additional** | Các nhóm bản ghi trong message | Referral NS và glue khác với answer trực tiếp |

**AD=1** từ resolver mà client thực sự tin cậy có thể cho thấy kết quả đã được DNSSEC-validated theo policy. Nhưng một bit AD trong gói UDP không được bảo vệ khỏi giả mạo **không tự chứng minh** kết quả an toàn; cần bảo vệ và xác thực kênh tới resolver khi phù hợp.

### 4.1. Những mã trạng thái quan trọng

| RCODE | Ý nghĩa cơ bản | Gợi ý phân tích |
| --- | --- | --- |
| **NOERROR** | Truy vấn không lỗi ở mức DNS | Có thể có answer, hoặc **NODATA**: tên tồn tại nhưng không có loại bản ghi được hỏi |
| **NXDOMAIN** | Tên miền được hỏi không tồn tại trong ngữ cảnh phản hồi | Đối chiếu domain, delegation, negative cache và DNSSEC |
| **SERVFAIL** | Server không hoàn tất được xử lý truy vấn | Có thể do authoritative lỗi, timeout, DNSSEC validation fail, cấu hình forwarder hoặc lỗi khác |
| **REFUSED** | Server từ chối xử lý theo policy | Có thể do recursion ACL, policy zone hoặc server không phục vụ loại yêu cầu đó |
| **FORMERR** | Message không đúng định dạng mong đợi | Xem extension/EDNS, dữ liệu packet và tương thích |

**NOERROR với Answer rỗng** không đồng nghĩa NXDOMAIN. **SERVFAIL** cũng không tự xác nhận DNSSEC sai; phải xem log validation, chuỗi delegation và trạng thái liên lạc với authoritative.

## 5. Cache, TTL và negative caching

### 5.1. Cache làm thay đổi kết quả quan sát

Recursive resolver có thể cache các RRset và kết quả âm tính theo quy tắc. TTL do authoritative công bố ảnh hưởng vòng đời của thông tin trong cache; thời gian còn lại thường giảm dần khi client truy vấn.

Ví dụ triển khai chuyển IP:

~~~text
09:00  Authoritative công bố A = 192.0.2.10, TTL 3600s
09:30  Recursive R đã cache kết quả trên từ trước
09:45  Quản trị đổi authoritative A = 192.0.2.20
09:46  Client hỏi R, R vẫn có thể trả IP cũ khi TTL cache chưa hết
10:00+ Client có thể thấy IP mới sau khi cache hết hạn và được truy vấn lại
~~~

Các mốc chỉ để minh họa; TTL thực tế còn phụ thuộc thời điểm truy vấn, local cache, policy giới hạn TTL và trường hợp serve-stale. Thay đổi TTL sát giờ chuyển dịch vụ **không bảo đảm** những bản ghi đã cache với TTL lớn trước đó được cập nhật ngay.

### 5.2. NXDOMAIN và NODATA cũng có thể được cache

**Negative caching** cho phép resolver lưu kết quả tên không tồn tại (NXDOMAIN) hoặc không có loại RR được hỏi (NODATA) trong một khoảng phù hợp dựa trên thông tin SOA và quy tắc DNS. Điều này giảm tải lên authoritative khi cùng một tên không tồn tại được hỏi lặp lại.

Hệ quả: vừa thêm một bản ghi mới nhưng client vẫn thấy **NXDOMAIN** có thể là vì resolver còn negative cache. Khi chẩn đoán, đối chiếu authoritative trực tiếp, recursive cache và TTL âm; không chỉ xóa cache trên một máy rồi kết luận toàn mạng đã cập nhật.

Một số validating resolver còn hỗ trợ **aggressive use of DNSSEC-validated cache** để suy ra câu trả lời phủ định từ NSEC/NSEC3 khi hợp lệ. Đây là tối ưu có điều kiện và cần hiểu khi phân tích log truy vấn không đi tới authoritative.

### 5.3. Caching và nguy cơ cache poisoning

**DNS cache poisoning** xảy ra khi dữ liệu sai hoặc không đáng tin được đưa vào cache resolver, có thể khiến các client dùng chung resolver nhận địa chỉ sai. Các lớp phòng vệ gồm:

- Kiểm tra response thuộc query đang chờ, kiểm tra nguồn/đích và tính hợp lệ của dữ liệu, tránh chấp nhận additional data ngoài phạm vi.
- Tăng độ khó đoán bằng **random source port, transaction ID** và các biện pháp hardened resolver; những cơ chế này giảm khả năng giả mạo nhưng không thay thế xác thực bằng mật mã.
- **DNSSEC validation** với zone có chữ ký và chuỗi tin cậy hợp lệ.
- Vá phần mềm resolver, giới hạn ai được gửi truy vấn/nhận recursion và giám sát sai lệch đáng ngờ.
- Bảo vệ kênh stub → recursive nếu threat model có nguy cơ giả mạo hoặc nghe lén trên đoạn này.

**DNSSEC xác thực dữ liệu DNS của zone được ký**, nhưng không thay thế bảo vệ endpoint/app, không chứng minh website có quyền truy cập chính xác và không ngăn thay đổi độc hại do người có quyền quản trị zone thực hiện.

## 6. Vận chuyển DNS: UDP, TCP, EDNS và mã hóa

### 6.1. UDP/53 và TCP/53

DNS truyền thống thường gửi query nhỏ qua **UDP cổng 53**. Khi response lớn, mất gói, có yêu cầu cụ thể hoặc cần truyền dữ liệu zone, **TCP cổng 53** cũng rất quan trọng. Các recursive và authoritative server hiện đại cần hỗ trợ TCP theo chuẩn giao thức DNS tương ứng; cấu hình chỉ cho UDP/53 có thể gây lỗi với DNSSEC và phản hồi lớn.

**EDNS(0)** mở rộng cách truyền tham số DNS, chẳng hạn kích thước payload UDP mà client có thể nhận. Đặt UDP payload quá lớn có thể dẫn tới IP fragmentation và vấn đề qua firewall/đường truyền; quá nhỏ có thể tăng số lần fallback TCP. Cần chọn cấu hình phù hợp nền tảng và theo dõi tỷ lệ truncated response, fragmentation và timeout.

~~~text
Client ---- UDP/53 query ----> Resolver
Client <--- UDP/53 response -- Resolver

Nếu response bị cắt (TC=1), hoặc chính sách/transport yêu cầu:
Client ---- TCP/53 query ----> Resolver
Client <--- TCP/53 response -- Resolver
~~~

Đây là luồng khái niệm; DNS có thể hoạt động qua DoT, DoH hoặc các cơ chế khác, và việc retry cụ thể phụ thuộc resolver/client.

### 6.2. DoT, DoH và DoQ bảo vệ chặng nào?

| Cơ chế | Transport phổ biến | Bảo vệ | Giới hạn |
| --- | --- | --- | --- |
| **DNS cổ điển** | UDP/53 và TCP/53 | Cung cấp dịch vụ phân giải tên | Không tự mã hóa hay xác thực nội dung trên đường truyền |
| **DNS over TLS (DoT)** | TLS trên TCP, thường cổng **853** | Mã hóa và có thể xác thực kênh client ↔ DNS server khi cấu hình đúng | Không tự bảo đảm bản ghi authoritative đúng nếu không xác thực DNSSEC |
| **DNS over HTTPS (DoH)** | HTTPS, thường cổng **443** | Mã hóa truy vấn DNS trong HTTPS tới resolver được chọn | Có thể đi ngoài đường chính sách DNS nội bộ nếu tổ chức không quản lý endpoint |
| **DNS over QUIC (DoQ)** | QUIC trên UDP, thường cổng **853** | Kênh DNS mã hóa và có đặc tính QUIC | Đòi hỏi hỗ trợ ở client/server và chính sách mạng tương ứng |
| **DNSSEC** | Chữ ký ở lớp dữ liệu DNS, độc lập kênh vận chuyển | Xác thực nguồn gốc dữ liệu zone và tính toàn vẹn RRset có chữ ký theo chain of trust | Không mã hóa truy vấn; không che tên miền client hỏi |

Ví dụ, client dùng DoH tới recursive resolver có kết nối mã hóa **trên đoạn client–resolver**. Recursive resolver vẫn có thể hỏi root/TLD/authoritative bằng DNS truyền thống; các truy vấn phía sau không tự được mã hóa chỉ vì client ban đầu dùng DoH.

DoT/DoH có thể cải thiện riêng tư và chống can thiệp trên một số chặng, nhưng đối với mạng doanh nghiệp cũng cần cân nhắc **DNS policy enforcement, logging tối thiểu cần thiết, resolver identity và split DNS**. Không nên mặc định chặn toàn bộ 443 để cấm DoH, bởi nhiều dịch vụ hợp lệ cũng dùng 443; chính sách cần dựa trên kiến trúc, danh tính thiết bị và các điểm kiểm soát hỗ trợ.

## 7. DNSSEC: authoritative ký dữ liệu, recursive xác minh

DNSSEC là cơ chế xác thực dữ liệu DNS dựa trên chữ ký số và chuỗi tin cậy. Trách nhiệm thường phân chia:

- **Authoritative của zone được ký** công bố **DNSKEY**, các chữ ký **RRSIG** cho RRset và dữ liệu chứng minh không tồn tại phù hợp như **NSEC/NSEC3**.
- **Parent zone** có thể công bố **DS** trỏ tới khóa DNSSEC của child zone, tạo liên kết của *chain of trust*.
- **Validating recursive resolver** dùng trust anchor và chuỗi DS/DNSKEY/RRSIG để đánh giá dữ liệu là **secure**, **insecure** (không có chuỗi ký hợp lệ theo mô hình) hoặc **bogus** (dự kiến được bảo vệ nhưng validation thất bại), tùy kết quả và tình huống.

~~~mermaid
flowchart TD
    TA["Trust anchor của root"] --> RK["Root DNSKEY được xác minh"]
    RK --> DS1["DS cho TLD ở parent"]
    DS1 --> TK["TLD DNSKEY được xác minh"]
    TK --> DS2["DS cho example.test ở TLD"]
    DS2 --> CK["DNSKEY của example.test"]
    CK --> S["RRSIG xác minh RRset A/AAAA/..."]
    S --> V["Recursive trả lời dữ liệu validated"]
~~~

Sơ đồ chỉ minh họa **trường hợp zone được ký và delegation có chuỗi DS hợp lệ**. Một domain không được DNSSEC ký đúng cách có thể là **insecure** chứ không mặc nhiên là **bogus**; DNSSEC validator phải phân biệt các trạng thái theo chuẩn.

### 7.1. Lỗi DNSSEC có thể gây SERVFAIL

Những nguyên nhân thường gặp:

- DS ở parent **không khớp** DNSKEY của child sau khi đổi khóa.
- RRSIG **hết hạn** hoặc chưa có hiệu lực theo thời gian hệ thống.
- Chỉ một phần authoritative được cập nhật zone, khiến kết quả thiếu nhất quán.
- Dữ liệu liên quan đến delegation hoặc NSEC/NSEC3 không phù hợp.
- Resolver không thể liên lạc để lấy bản ghi cần validation, hoặc đồng hồ hệ thống sai.

Nếu DNSSEC validation thất bại với dữ liệu cần ký, một validating resolver thường trả **SERVFAIL** thay vì đưa dữ liệu bogus cho client. **Đừng tắt toàn bộ DNSSEC validation như cách sửa nhanh**. Cần kiểm tra DS/DNSKEY/RRSIG, trạng thái zone và thời gian, rồi sửa nguyên nhân hoặc dùng quy trình thay khóa an toàn.

### 7.2. DNSSEC không làm những việc gì?

DNSSEC **không**:

- Mã hóa QNAME hoặc giấu IP của client khỏi resolver đang dùng.
- Chứng nhận rằng endpoint HTTP/HTTPS không chứa mã độc hoặc người quản trị domain là bên đáng tin.
- Thay thế **TLS, xác thực dịch vụ, quản lý certificate** hoặc chính sách truy cập mạng.
- Chặn volumetric DNS DDoS hoặc ngăn một authoritative được quản trị hợp lệ công bố địa chỉ sai.

DNSSEC có thể tăng kích thước response, do đó cần kết hợp thiết kế **EDNS, TCP fallback, chống amplification và monitoring**.

## 8. Threat model riêng cho recursive và authoritative DNS

Hai vai trò có các nguy cơ khác nhau; một số attack path có thể ảnh hưởng cả hai.

| Threat / tình huống | Điểm yếu liên quan | Control phù hợp |
| --- | --- | --- |
| **Open recursive resolver bị lạm dụng** | Recursion mở cho Internet, cho phép nguồn không được quản lý sử dụng | Chỉ cấp recursion cho client/subnet/VPN được phép; firewall ingress; giám sát qps |
| **DNS reflection/amplification** | UDP có thể bị giả mạo IP nguồn; response lớn và resolver/authoritative mở public | BCP38/ingress anti-spoofing ở mạng nguồn, response rate limiting (RRL) ở authoritative khi phù hợp, hạn chế open recursion, chống DDoS upstream |
| **Cache poisoning** | Resolver chấp nhận response hoặc dữ liệu additional không hợp lệ | Resolver hardening, bailiwick checks, randomization, DNSSEC validation, cập nhật phần mềm |
| **Zone tampering/hijack** | Quyền registrar/DNS provider/API quá rộng, quản trị không MFA | MFA chống phishing khi có thể, quyền tối thiểu, audit log, change approval, domain/registrar lock phù hợp |
| **Lộ zone transfer** | AXFR được cấp quyền cho host không cần thiết | ACL AXFR/IXFR theo secondary DNS, TSIG khi phù hợp, giới hạn cổng và kiểm toán |
| **DNSSEC chain break** | DS/DNSKEY không đồng bộ, RRSIG hết hạn, đồng hồ sai | Quy trình key rollover, monitoring chữ ký và DS, kiểm tra từ validating resolver |
| **DNS tunneling / data exfiltration** | Client được phép gửi DNS tới resolver tùy ý, log/giám sát thiếu | Managed resolver, egress policy cho DNS/DoH/DoT theo mô hình, DNS analytics, EDR/DLP theo nhu cầu |
| **Rogue DHCP/DNS resolver** | Thiết bị chuyển DNS client sang máy chủ lạ | DHCP snooping/RA Guard ở mạng hỗ trợ, cấu hình resolver qua quản lý thiết bị, bảo vệ mạng Wi-Fi |
| **DDoS vào authoritative** | Domain phụ thuộc ít nameserver/đường mạng, thiếu phân tán | Nhiều authoritative độc lập, anycast khi phù hợp, upstream mitigation, giám sát availability |
| **Split DNS sai view** | Internal record bị lộ ra public hoặc resolver nội bộ không trả đúng | Tách public/private zone và quyền update, kiểm thử từng view/client, policy routing/DNS forwarding |

**Rate limiting không giải quyết được mọi threat DNS.** Nó có thể giảm bùng nổ truy vấn hoặc phản hồi nhưng không xác thực nội dung; DNSSEC và quản trị zone cũng không cứu được một liên kết Internet đã nghẽn bởi DDoS. Cần chọn control theo **đường tấn công cụ thể**.

### 8.1. Vì sao open resolver nguy hiểm?

Một recursive resolver public không có chủ đích cho phép bất kỳ ai gửi truy vấn. Kẻ tấn công có thể lợi dụng tài nguyên xử lý/cache, dùng server như nguồn phản hồi UDP trong các kịch bản **reflection/amplification**, và tạo lượng truy vấn lớn tới authoritative hạ nguồn.

Phòng vệ nên bao gồm:

1. **Recursion ACL:** chỉ cho các dải mạng/nguồn được quản lý sử dụng; authoritative public không bật recursion rộng.
2. **Network control:** hạn chế client ngoài phạm vi kết nối tới resolver nội bộ bằng firewall, segmentation và chính sách VPN.
3. **Rate/abuse monitoring:** theo dõi số truy vấn theo nguồn, QTYPE, RCODE, NXDOMAIN và đột biến.
4. **Host protection:** vá resolver, giới hạn tài nguyên, giám sát bất thường và backup cấu hình.
5. **Test ngoài vùng được phép:** xác nhận client Internet không thể sử dụng recursion khi policy không cho phép.

Với mạng doanh nghiệp, việc mở UDP/TCP 53 trên authoritative public để phục vụ zone là chuyện bình thường, **không đồng nghĩa** được phép cung cấp recursion cho mọi người. Cần kiểm tra **RD/RA và hành vi server**, không chỉ kiểm tra cổng 53 có mở.

### 8.2. AXFR/IXFR không phải truy vấn bình thường

**AXFR** là cơ chế chuyển toàn bộ zone giữa những DNS server được cấp phép, thường qua TCP. **IXFR** phục vụ chuyển thay đổi tương đối khi có hỗ trợ. Dữ liệu zone có thể chứa danh sách host, cấu trúc dịch vụ và thông tin nhạy cảm trong hệ thống nội bộ.

- Cấp phép secondary DNS **cụ thể** thay vì mở chuyển zone cho mọi client.
- Có thể dùng **TSIG** để xác thực và bảo vệ tính toàn vẹn thông điệp giữa các server theo khả năng hỗ trợ, quản lý và luân chuyển secret đúng cách.
- **TSIG không mã hóa nội dung zone transfer**. Nếu yêu cầu bảo mật đường truyền, cần tunnel/kênh mã hóa phù hợp như VPN hoặc cơ chế được sản phẩm hỗ trợ.
- Theo dõi cập nhật serial, thất bại đồng bộ và sự khác nhau giữa các authoritative.

Zone transfer bị từ chối với client không được phép là một **kết quả bảo mật mong muốn**; không nên coi mọi REFUSED/transfer failure là lỗi dịch vụ công khai.

## 9. Thiết kế kiến trúc DNS an toàn cho mạng doanh nghiệp và cloud

Một mô hình khái niệm:

~~~mermaid
flowchart LR
    C["Client nội bộ / Wi-Fi quản lý"] -->|DNS theo policy| R["Recursive resolver nội bộ"]
    V["Client VPN đã xác thực"] -->|DNS qua tunnel| R
    R -->|Iterative DNS / forwarder hợp lệ| I["Internet DNS hierarchy"]
    I --> P["Public authoritative DNS"]
    P --> A["Public zone của tổ chức"]
    R --> Z["Authoritative zone private nếu cần"]
    B["DNS admin / CI được cấp quyền"] -->|Thay đổi có kiểm toán| A
    B -->|Thay đổi có kiểm toán| Z
    R -. "Query/Rcode/validation metrics" .-> S["SOC / SIEM / DNS monitoring"]
    P -. "Availability + zone health" .-> S
~~~

Trong triển khai thực tế, recursive resolver có thể **forward** một số tên tới authoritative nội bộ hoặc cloud private DNS, thay vì gửi iterative query tới root/TLD cho mọi tên. Cần nêu rõ luồng nào **public**, luồng nào **private** và đường VPN/hybrid nào mang các truy vấn đó.

### 9.1. Nguyên tắc thiết kế recursive

- **Managed resolvers:** cấp danh sách resolver tin cậy qua DHCP, MDM, VPN profile hoặc cấu hình máy chủ; hạn chế client dùng resolver ngoài policy theo nhu cầu và quyền.
- **Recursion ACL:** tách nhóm người dùng/tenant và vùng mạng, không dùng resolver nội bộ như một open resolver.
- **DNSSEC validation:** triển khai validating resolver, theo dõi SERVFAIL/bogus và quy trình xử lý khi chữ ký/DS lỗi.
- **Privacy:** chỉ log QNAME/IP/user khi thật sự cần cho mục tiêu vận hành, giới hạn quyền, thời gian lưu và thực hiện ẩn danh ở mức phù hợp.
- **Response policy:** có thể dùng DNS firewall/RPZ/sinkhole cho tên được xác nhận độc hại, nhưng phải có exception chặt, kiểm thử và cơ chế xử lý false positive.
- **Resilience:** nhiều resolver đủ độc lập, cấu hình timeout/failover phù hợp, giám sát latency, cache hit ratio, QPS và sức khỏe upstream.
- **Egress rules:** kiểm soát DNS qua UDP/TCP 53, DoT/DoH theo chính sách; không phá khả năng phân giải thiết yếu hoặc giả định mọi DNS mã hóa đều xấu.

Một resolver private có thể cần hỏi authoritative public qua Internet. **Chặn toàn bộ UDP/TCP 53 outbound của chính resolver** sẽ làm hỏng kiến trúc iterative, trừ khi có forwarder/thay thế được cấu hình phù hợp. Vì vậy rule cần phân biệt **client → resolver nội bộ** với **resolver → upstream/authoritative**.

### 9.2. Nguyên tắc thiết kế authoritative

- **Public authoritative:** phục vụ zone công khai và có thể nhận query từ Internet; recursion phải được tắt hoặc hạn chế theo chính sách.
- **Tách quản trị zone:** chỉ các chủ thể được cấp quyền thay bản ghi, NS, DS và cấu hình server; bật MFA, audit và phê duyệt thay đổi phù hợp.
- **DNSSEC signing:** giữ an toàn khóa ký, lập kế hoạch rollover và kiểm tra chain of trust tại parent.
- **Availability:** triển khai nhiều nameserver ở hạ tầng/đường mạng độc lập; sử dụng anycast khi phù hợp nhưng vẫn cần bảo vệ control plane.
- **Zone transfer:** giới hạn AXFR/IXFR, xác thực secondary và bảo vệ đường truyền khi yêu cầu.
- **Đồng nhất dữ liệu:** theo dõi SOA serial, độ trễ đồng bộ secondary, trả lời giữa các authoritative và delegation/glue.
- **Chống lạm dụng:** RRL, chống DDoS ở upstream và giám sát băng thông; xác minh không chặn nhầm resolver hợp lệ.

### 9.3. Split-horizon DNS và hệ thống cloud/hybrid

Một tên có thể được trả lời khác nhau tùy **network view**:

~~~text
API public: api.example.test   -> 203.0.113.20  (minh họa)
API private: api.example.test  -> 10.20.10.20   (minh họa)
~~~

Nếu thiết kế split DNS, cần kiểm tra:

- Client công khai có nhìn thấy bản ghi private ngoài ý muốn không?
- Client VPN có dùng **đúng resolver nội bộ** và search domain có gây trùng tên không?
- VPC/VNet peering, private endpoint và hybrid forwarder có route hai chiều đúng không?
- DNSSEC validation cho private zone được thực hiện theo cách nào; zone private có trust anchor/signing phù hợp hay được quản lý bằng chính sách nội bộ?
- Khi cloud resolver hoặc VPN gặp sự cố, fallback có vô tình gửi tên internal tới public resolver không?

**DNS trả về IP private không tự tạo quyền truy cập**: routing, security group, firewall, xác thực service và TLS phải được thiết kế riêng. DNS chỉ giúp client xác định đích; một tên được phân giải thành công không chứng minh cổng ứng dụng mở.

## 10. Phân tích lưu lượng và kiểm tra DNS bằng công cụ

Các ví dụ sau chỉ chạy trong **mạng hoặc máy chủ được phép quản trị/kiểm tra**. Các IP 192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24 là dải dành cho tài liệu; lệnh dùng IP minh họa sẽ **không có nghĩa là truy vấn được một dịch vụ DNS thật**.

### 10.1. Lệnh kiểm tra với dig

~~~bash
# Hỏi resolver mặc định đang cấu hình trên máy.
dig www.example.com A

# Kiểm tra các trường ANSWER, flags và TTL của phản hồi.
dig www.example.com AAAA

# Hỏi nameserver cụ thể; thay 192.0.2.53 bằng IP resolver được cấp quyền.
dig @192.0.2.53 www.example.com A

# Yêu cầu KHÔNG recursion; hữu ích khi kiểm tra authoritative phù hợp.
dig @192.0.2.53 www.example.com NS +norecurse

# Yêu cầu bản ghi DNSSEC nếu phía trả lời hỗ trợ.
dig www.example.com A +dnssec

# Xem đường đi delegation/truy vấn gần với iterative resolution;
# chỉ dùng cho các tên và mạng có quyền kiểm tra.
dig +trace www.example.com A

# Thử DNS qua TCP/53 theo khả năng server và network policy.
dig +tcp www.example.com A
~~~

Các lệnh là ví dụ thao tác quan sát; domain **example.com** được dùng làm tên minh họa phổ biến. Để kiểm tra private DNS, thay bằng tên zone nội bộ và địa chỉ resolver/authoritative thực sự trong môi trường được phép. Cần đọc **SERVER**, **flags**, **ANSWER**, **AUTHORITY**, **ADDITIONAL**, **status**, **TTL** và thời gian truy vấn thay vì chỉ đọc một địa chỉ IP.

**Cẩn trọng với dig +trace:** cách truy vấn, các server được hỏi và địa chỉ nguồn phụ thuộc triển khai; trong mạng bị hạn chế egress hoặc dùng split DNS, kết quả không nhất thiết giống với đường phân giải bình thường qua recursive resolver doanh nghiệp. Không dùng +trace để khẳng định dữ liệu private DNS phải có trên Internet.

### 10.2. Đọc một response minh họa

~~~text
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 30125
;; flags: qr rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 1
;; QUESTION SECTION:
;www.example.test.           IN  A
;; ANSWER SECTION:
www.example.test.      120   IN  A    192.0.2.10
~~~

Phân tích:

- **qr** cho biết đây là response.
- **rd** cho biết yêu cầu recursion được phản ánh trong response.
- **ra** cho biết máy trả lời quảng bá khả năng recursion.
- Không có **aa**, nên đây **không được trình bày** như câu trả lời authoritative.
- **120** là TTL được hiển thị tại thời điểm response, không nhất thiết là TTL ban đầu của zone.
- Kết quả trả về một A record không chứng minh TLS/HTTP tới IP tương ứng an toàn.

### 10.3. Quan sát packet DNS có kiểm soát

~~~bash
# Quan sát tối đa 30 gói DNS truyền thống trên máy hoặc interface được cấp quyền.
sudo tcpdump -ni any -c 30 '(udp port 53 or tcp port 53)'

# Capture thời lượng/lượng dữ liệu giới hạn để phân tích offline.
# Chỉ chạy trên môi trường được phép; tập tin có thể chứa tên miền nhạy cảm.
sudo tcpdump -ni eth0 -c 100 -w dns-observation.pcap '(udp port 53 or tcp port 53)'
~~~

Trong Wireshark, display filter có thể giúp phân loại:

~~~text
dns
dns.flags.response == 1
dns.flags.rcode == 3
dns.flags.truncated == 1
dns.qry.type == 1
tcp.port == 53
~~~

Filter **dns** chỉ bắt được các gói được Wireshark nhận diện/lý giải là DNS trong capture. Truy vấn DoH/DoT/DoQ đã mã hóa có thể chỉ nhìn thấy kênh TLS/HTTPS/QUIC và metadata, nên **không có QNAME rõ** trong packet capture thông thường.

### 10.4. Phân biệt lỗi theo vị trí

| Quan sát | Khả năng cần kiểm tra | Bằng chứng tiếp theo |
| --- | --- | --- |
| Một client không phân giải được, client khác bình thường | DNS cấu hình trên client, mạng cục bộ, VPN, local cache, split view | Resolver list, route, query trực tiếp tới resolver được cấp phép |
| Tất cả client cùng resolver gặp SERVFAIL | Upstream không đáp ứng, DNSSEC validation, forwarder lỗi, resolver quá tải | Resolver log/metrics, query authoritative, DNSSEC chain |
| Resolver trả IP cũ, authoritative đã có IP mới | Positive cache/TTL, stale answer, khác biệt view | So TTL và truy vấn từng lớp; kiểm tra cache policy |
| Một số recursive trả NXDOMAIN, số khác trả A | Negative cache, delegation không đồng bộ, split DNS | SOA/NS, từng resolver, TTL và log zone update |
| UDP trả lời lỗi còn TCP hoạt động | Kích thước/EDNS, fragmentation, ACL UDP, packet loss | TC flag, tcpdump hai phía, firewall, đường đi |
| UDP hoạt động nhưng TCP/53 bị chặn | Firewall chỉ cho UDP, DNS server không lắng nghe TCP, policy network | TCP test, listener, firewall/session log |
| Chỉ validating resolver bị SERVFAIL | Có thể DNSSEC chain/record/signature lỗi | DS/DNSKEY/RRSIG, time sync, validator log |
| Public domain hoạt động, private zone lỗi qua VPN | Forwarding, resolver selection, policy, route tới authoritative private | VPN DNS config, forwarding rule, firewall nội bộ |

Không thể xác định nguyên nhân chỉ từ **một dòng lỗi trên client**. Cần so sánh cùng tên/QTYPE ở **client, recursive và authoritative**, biết chính xác resolver nào đang được dùng và ghi lại timestamps.

## 11. Tình huống thực hành: đổi IP dịch vụ nhưng một số người vẫn vào server cũ

### 11.1. Bối cảnh

Một đội vận hành đổi A record **api.example.test** từ **192.0.2.10** sang **192.0.2.20**. Authoritative đã trả địa chỉ mới, nhưng một số client qua VPN vẫn truy cập dịch vụ cũ; các client Internet khác hoạt động bình thường.

Một sơ đồ suy luận:

~~~text
Client VPN -> Recursive nội bộ -> cache? -> Authoritative public/private?
                               -> forwarder? -> resolver bên thứ ba?
Client Internet -> Public recursive -> Public authoritative
~~~

### 11.2. Các giả thuyết nên kiểm tra theo thứ tự

1. **Cùng tên hay khác view?** Private DNS có công bố IP khác public DNS hay không?
2. **Client sử dụng resolver nào?** VPN có đẩy resolver/search domain đúng và có đang split-tunnel không?
3. **Recursive có cache cũ?** TTL còn lại bao nhiêu, server có đang serve-stale hay có cache phụ?
4. **Authoritative có đồng nhất không?** Tất cả nameserver của zone trả cùng dữ liệu/SOA serial chưa?
5. **Delegation đúng chưa?** Parent NS/glue có hướng tới máy chủ đúng không?
6. **DNSSEC có lỗi không?** Nếu kết quả là SERVFAIL, so trạng thái validation và DS/DNSKEY/RRSIG.
7. **Ứng dụng có cache riêng không?** Browser, hệ điều hành, runtime hoặc service discovery có thể giữ kết quả theo quy tắc khác nhau.

### 11.3. Kế hoạch kiểm chứng

| Điểm kiểm tra | Cách làm | Điều muốn xác nhận |
| --- | --- | --- |
| Client VPN | Kiểm tra DNS server thực đang dùng, hỏi A/AAAA bằng công cụ phù hợp | Đúng resolver và đúng địa chỉ |
| Recursive nội bộ | Hỏi trực tiếp cùng QNAME/QTYPE, xem TTL, cache log | Có còn dữ liệu cũ/negative cache không |
| Public recursive | Hỏi từ môi trường được phép, đối chiếu kết quả | View công khai có khác private không |
| Authoritative trong zone | Query tới từng server có thẩm quyền theo policy | Tất cả đã trả dữ liệu/serial mới chưa |
| DNSSEC | Kiểm tra validation và chữ ký nếu dùng | Không còn lỗi DS/key/expiration |
| Ứng dụng | Kiểm tra log kết nối/tên/IP tới endpoint cuối | Không nhầm lỗi DNS với lỗi mạng/TLS/ứng dụng |

**Hành động an toàn:** xác định lớp còn trả dữ liệu cũ trước khi xóa cache hoặc sửa zone; nếu muốn giảm TTL cho lần chuyển dịch vụ tiếp theo, cần thực hiện đủ sớm để những bản ghi đã cache với TTL cao tự hết hạn. Không giảm bảo vệ DNSSEC hay mở firewall toàn mạng chỉ để làm mất triệu chứng.

## 12. Giám sát và đo lường chất lượng DNS security

Monitoring cần đo riêng **trải nghiệm resolver** và **sức khỏe authoritative**, bởi một phía hoạt động tốt không đảm bảo phía kia không lỗi.

| Nhóm | Metric / tín hiệu | Cách sử dụng |
| --- | --- | --- |
| **Recursive availability** | Success/error rate, request latency, timeout tới upstream | Phát hiện chậm hoặc không phân giải được |
| **Recursive cache** | Cache hit/miss ratio, TTL behavior, eviction, memory | Hiểu tải và sai lệch kết quả khi đổi zone |
| **DNSSEC validation** | Bogus/SERVFAIL do validation, trust-anchor state | Tìm lỗi chữ ký/chuỗi tin cậy, phân biệt với mạng lỗi |
| **Query behavior** | QPS theo client group, QTYPE, NXDOMAIN rate, query length, subdomain entropy | Phát hiện bùng nổ truy vấn hoặc mẫu tunneling đáng xem xét |
| **Amplification/abuse** | UDP response bytes, queries by untrusted sources, RRL hits | Theo dõi nguy cơ phản xạ và tác động rate limiting |
| **Authoritative availability** | Truy vấn thành công từ nhiều vantage point, response time, packet loss | Đánh giá khả năng truy cập zone |
| **Delegation correctness** | NS parent/child, glue, SOA serial giữa server | Phát hiện NS/glue sai hoặc secondary chậm |
| **DNSSEC zone health** | RRSIG gần hết hạn, DS mismatch, rollover state | Tránh outage do ký DNSSEC lỗi |
| **Zone administration** | Ai thêm/sửa/xóa bản ghi, thay NS/DS, cập nhật API | Phát hiện thay đổi không được phê duyệt |
| **Privacy/retention** | Quyền truy cập query log, thời hạn lưu và trường nhạy cảm | Giảm rủi ro từ dữ liệu giám sát |

### 12.1. Giảm false positive trong DNS analytics

Một tỷ lệ **NXDOMAIN cao** có thể xuất phát từ DGA/mã độc, nhưng cũng có thể do cấu hình sai, search suffix của máy trạm, ứng dụng thử nhiều hostname, hoặc kiểm tra availability hợp lệ. Truy vấn nhiều subdomain ngẫu nhiên có thể là tunneling, nhưng cũng có thể liên quan telemetry, CDN hoặc tracking.

Khi SOC điều tra, cần đối chiếu **nguồn, thời gian, loại truy vấn, tên miền, volume, policy, endpoint/process**, log web/proxy và dữ liệu môi trường. DNS analytics nên dùng để **ưu tiên điều tra**, không tự chứng minh endpoint nhiễm mã độc chỉ từ một chỉ số đơn lẻ.

## 13. Các nhầm lẫn cần tránh

1. **“Authoritative server sẽ đi hỏi thay client.”** Nhiệm vụ chính của authoritative là trả dữ liệu zone hoặc referral; recursion thường do recursive resolver thực hiện.
2. **“Một máy chủ vừa trả AA vừa nhận recursion thì hai khái niệm giống nhau.”** Có thể chung phần mềm, nhưng chức năng và quyền sử dụng khác nhau; phải xét view/response cụ thể.
3. **“RD=1 nghĩa là resolver đã phân giải đệ quy.”** RD chỉ biểu thị mong muốn từ client, còn kết quả chịu RA, policy và khả năng server.
4. **“Tên miền phân giải được chứng minh dịch vụ an toàn.”** DNS có thể dẫn tới IP hợp lệ hoặc độc hại; cần TLS, chứng chỉ, auth và các lớp bảo vệ khác.
5. **“DNSSEC mã hóa truy vấn DNS.”** DNSSEC xác thực dữ liệu DNS; DoT/DoH/DoQ mã hóa kênh tương ứng.
6. **“Bật DoH nghĩa mọi chặng tới authoritative đều được mã hóa.”** DoH chỉ bảo vệ chặng triển khai HTTPS, không tự thay đổi cách resolver hỏi upstream.
7. **“Đổi record trên authoritative là mọi máy thấy ngay.”** Cache tích cực/tiêu cực, TTL và nhiều view có thể trì hoãn.
8. **“SERVFAIL luôn do firewall.”** Có thể là validation DNSSEC, nameserver không phản hồi, cấu hình resolver hoặc nhiều nguyên nhân khác.
9. **“Chỉ cần mở UDP/53 cho DNS.”** TCP/53 cần cho nhiều trường hợp hợp lệ, đặc biệt response lớn và zone transfer.
10. **“Mở port 53 public tương đương open resolver.”** Authoritative public cần có thể trả lời query, nhưng phải hạn chế recursion riêng.
11. **“TSIG mã hóa AXFR.”** TSIG xác thực/bảo vệ tính toàn vẹn thông điệp, không mã hóa nội dung zone transfer.
12. **“Không thấy DNS query ở authoritative nghĩa client không hỏi.”** Cache, forwarder, split DNS và negative caching có thể làm giảm upstream queries.
13. **“DNS trả địa chỉ private thì đã bảo vệ được dịch vụ.”** Quyền truy cập còn phụ thuộc route, firewall, service identity và ứng dụng.
14. **“Không có log DNS là không có hoạt động DNS.”** DoT/DoH, cache cục bộ, resolver khác, sampling hoặc sai điểm giám sát đều có thể gây thiếu bằng chứng.

## 14. Bài tập vận dụng và gợi ý

### Bài 1 — Phân biệt vai trò từ log

Một client hỏi **www.example.test A** với RD=1. Server trả phản hồi NOERROR, RA=1, AA=0 và một A record có TTL còn lại 75 giây. Đó có phải dấu hiệu server trả từ cache không?

**Gợi ý:** rất phù hợp với một recursive resolver trả lời không-authoritative và có thể từ cache, nhưng **chưa đủ chứng minh** chỉ từ các bit/TTL đó. Cần cache statistics/log hoặc đối chiếu upstream. RA=1 không tự xác nhận cách xử lý nội bộ.

### Bài 2 — Open recursion và authoritative public

Một authoritative public phục vụ zone tổ chức trên UDP/TCP 53. Đội quản trị dự định chặn mọi DNS query từ Internet để ngăn amplification. Điều gì sẽ xảy ra? Nên bảo vệ thế nào?

**Gợi ý:** chặn toàn bộ query công khai sẽ làm domain không phân giải được qua hệ thống này. Nên duy trì authoritative service công khai, **tắt/giới hạn recursion**, cấu hình RRL phù hợp, DDoS protection và redundancy; anti-spoofing ở mạng nguồn là lớp phòng ngừa quan trọng với reflection.

### Bài 3 — Lỗi DNSSEC sau khi chuyển nhà cung cấp

Sau khi chuyển authoritative sang nhà cung cấp mới, một số validating resolver trả SERVFAIL trong khi non-validating resolver vẫn trả A record. Cần kiểm tra ba nhóm dữ liệu nào?

**Gợi ý:** (1) DS tại parent, (2) DNSKEY/RRSIG và thời hạn chữ ký của child, (3) trạng thái đồng bộ zone, delegation/NS và thời gian hệ thống. Việc DS cũ còn trỏ tới khóa không có ở nhà cung cấp mới là một khả năng.

### Bài 4 — Client VPN không đọc được private zone

Client VPN phân giải được public domain nhưng truy vấn **db.corp.example.test** bị NXDOMAIN. Bạn sẽ kiểm tra ở những đâu trước khi mở firewall?

**Gợi ý:** resolver client đang dùng, VPN DNS configuration, split DNS/forwarder, zone authoritative private, query log theo view, negative caching, sau đó mới xét route/ACL có liên quan. Có thể đang hỏi nhầm public resolver chứ không phải bị firewall chặn.

### Bài 5 — Thiết kế DNS security policy

Cho mạng có ba vùng **GUEST**, **USER** và **SERVER**, một recursive resolver nội bộ cùng authoritative public. Hãy viết các yêu cầu:

- Ai được dùng recursion?
- Client được gửi DNS trực tiếp tới Internet hay phải qua managed resolver?
- Resolver nào có quyền hỏi upstream/root/authoritative?
- Zone transfer được cấp cho secondary DNS nào và bảo vệ bằng cách nào?
- Metrics, log và positive/negative test nào chứng minh chính sách được thi hành?

**Gợi ý:** người dùng hợp lệ phải phân giải được cả domain public và zone private theo quyền; client không được cấp recursion phải bị từ chối đúng policy; authoritative public vẫn trả lời zone công khai và không cấp recursion rộng; AXFR chỉ cho secondary được phê duyệt.

## 15. Ghi nhớ và áp dụng vào thiết kế mạng an toàn

**Recursive resolver** tìm và có thể cache câu trả lời thay client; **authoritative DNS** công bố dữ liệu có thẩm quyền cho zone và chỉ dẫn delegation. **Root/TLD**, NS/glue, SOA, TTL và negative cache tạo nên cách một tên được tìm ra và được sử dụng lại. Khi điều tra, phải tách **query từ client đến recursive** với **query từ recursive tới authoritative**, cũng như phân biệt thông tin trong response và mức độ đáng tin của nó.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, bảo vệ DNS cần thực hiện ở **đúng trust boundary**: giới hạn recursion, bảo vệ cập nhật zone/AXFR, triển khai DNSSEC validation/signing khi phù hợp, mã hóa đoạn client–resolver theo threat model, kiểm soát DNS egress, giám sát truy vấn bất thường và duy trì authoritative có khả năng chống DDoS. Các bằng chứng từ resolver, authoritative, firewall, VPN, DNSSEC validator và ứng dụng phải được đối chiếu để nhận diện lỗi hoặc tấn công mà vẫn giữ cho các kết nối hợp lệ hoạt động.
