# DNS cache poisoning

> **Chương:** DNS security  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Phạm vi:** Bảo vệ quá trình phân giải tên miền và bộ nhớ đệm DNS trong kiến trúc phòng vệ mạng nhiều lớp: phân đoạn, firewall, VPN, IDS/IPS, DNS, Wi-Fi, cloud, phân tích lưu lượng và giám sát xâm nhập.

## 1. DNS cache poisoning là gì?

**DNS cache poisoning** (đầu độc bộ nhớ đệm DNS) xảy ra khi thông tin DNS **không đúng hoặc không được xác thực hợp lệ** được đưa vào cache của một thành phần phân giải tên, khiến những truy vấn tiếp theo nhận kết quả sai cho đến khi mục cache bị thay thế, hết hạn hoặc được xử lý. Thành phần bị ảnh hưởng có thể là **recursive resolver**, DNS forwarder, DNS proxy, hoặc cache ở hệ điều hành/ứng dụng, tùy con đường và cơ chế gây nhiễm bẩn.

Một ví dụ giả định: người dùng truy cập portal.example.com, lẽ ra phải đến địa chỉ 203.0.113.24 của dịch vụ được quản lý. Nhưng một cache bị nhiễm bẩn lại trả về 198.51.100.66. Nếu client tin câu trả lời đó, nó sẽ thử kết nối tới sai đích. Hậu quả có thể là **chuyển hướng truy cập**, **đánh cắp thông tin nếu các lớp xác thực khác cũng thất bại**, gián đoạn dịch vụ, hoặc đưa người dùng tới hạ tầng do bên không được phép vận hành.

Các tên và địa chỉ IP trong bài là ví dụ thuộc không gian dùng cho tài liệu, **không phải dữ liệu DNS đang hoạt động**. Việc DNS trả về IP khác kỳ vọng **chưa đủ chứng minh có đầu độc cache**: CDN, geo-routing, split-horizon, DNS failover và bản ghi vừa đổi cũng có thể tạo kết quả khác nhau một cách hợp lệ.

**Điểm cốt lõi:** DNS cache poisoning phá vỡ **tính toàn vẹn và nguồn gốc đáng tin của dữ liệu phân giải**. Nó không đơn thuần là “DNS chậm” hoặc “một tên miền không phân giải được”. Để phòng vệ phải kiểm soát **nguồn dữ liệu đi vào cache, cách xác thực phản hồi, thiết bị nào đang dùng resolver, và cách theo dõi thay đổi bất thường**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích luồng recursive DNS lookup và những loại bản ghi được cache.
2. Phân biệt DNS cache poisoning với DNS spoofing trên đường truyền, DNS hijacking và thay đổi bản ghi hợp lệ.
3. Hiểu vai trò của kiểm tra phản hồi, transaction ID, source port, bailiwick và DNSSEC.
4. Thiết kế resolver nội bộ an toàn với mạng phân đoạn, VPN, Wi-Fi, DNS egress policy và cloud.
5. Sử dụng log, TTL, kết quả từ nhiều điểm quan sát và các truy vấn chẩn đoán để xác định sự cố.
6. Thực hiện quy trình điều tra, cô lập, sửa nguyên nhân, làm sạch cache có kiểm soát và xác minh hồi phục.

## 2. DNS phân giải tên miền và sử dụng cache ra sao?

Khi ứng dụng cần địa chỉ của một hostname, nó thường nhờ **stub resolver** của hệ điều hành hoặc thư viện, có thể dùng cache tại máy, rồi gửi câu hỏi tới một **recursive resolver** được cấu hình. Recursive resolver tìm hoặc lấy dữ liệu từ cache; nếu không có dữ liệu phù hợp, nó có thể thực hiện các bước phân giải thông qua root, TLD và authoritative DNS server hoặc chuyển tiếp qua DNS forwarder đã được cấu hình.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Ứng dụng / Stub resolver
    participant R as Recursive resolver + Cache
    participant Root as Root DNS
    participant TLD as TLD DNS
    participant Auth as Authoritative DNS
    U->>R: Hỏi A/AAAA của portal.example.com
    alt Cache hợp lệ còn TTL
        R-->>U: Trả RRset từ cache
    else Chưa có dữ liệu phù hợp
        R->>Root: Truy vấn để tìm hướng phân giải
        Root-->>R: Thông tin delegation phù hợp
        R->>TLD: Truy vấn tiếp
        TLD-->>R: Thông tin authoritative
        R->>Auth: Hỏi bản ghi cần tìm
        Auth-->>R: Câu trả lời DNS
        R->>R: Kiểm tra, xác thực theo chính sách và cache
        R-->>U: Trả kết quả
    end
~~~

Sơ đồ mô tả **mô hình khái niệm**. Trên thực tế resolver thường đã cache delegation, có thể sử dụng forwarder, DNSSEC validation, aggressive negative caching, QNAME minimization, kết nối TCP hoặc cơ chế DNS được mã hóa ở một chặng. Một query không nhất thiết đi qua đủ ba cấp root/TLD/authoritative mỗi lần.

### 2.1. Cache được dùng để làm gì?

Cache giảm độ trễ, giảm truy vấn lặp lại đến authoritative server và tăng khả năng phục vụ. Khi nhận được dữ liệu đủ điều kiện lưu, resolver giữ **RRset (tập bản ghi cùng tên, loại và lớp)** trong khoảng thời gian dựa trên **TTL (Time to Live)** và các quy tắc của nó.

| Thành phần DNS | Nội dung | Ý nghĩa với cache poisoning |
|---|---|---|
| **QNAME/QTYPE/QCLASS** | Tên, loại bản ghi và lớp truy vấn | Dữ liệu trả lời phải tương ứng truy vấn thực sự được gửi |
| **A/AAAA** | Địa chỉ IPv4/IPv6 của hostname | Trả sai IP có thể chuyển hướng client |
| **CNAME** | Bí danh tới một tên khác | Cache sai có thể khiến client phân giải tiếp sai chuỗi |
| **NS và delegation** | Máy chủ có thẩm quyền cho vùng DNS | Dữ liệu delegation sai có thể ảnh hưởng nhiều truy vấn |
| **MX/SRV** | Điểm đến dịch vụ thư hoặc dịch vụ có định danh | Sai dữ liệu có thể ảnh hưởng thư và dịch vụ khám phá |
| **DNSKEY/DS/RRSIG** | Thông tin dùng trong DNSSEC | Hỗ trợ kiểm tra tính xác thực của dữ liệu được ký |
| **NXDOMAIN/NODATA** | Kết quả phủ định, có quy tắc cache riêng | Cache phủ định sai có thể làm dịch vụ dường như không tồn tại |
| **TTL** | Thời gian được phép giữ dữ liệu | Giúp xác định khoảng ảnh hưởng, nhưng không chứng minh dữ liệu đúng |

### 2.2. Những nơi có thể giữ cache

- **Recursive resolver tập trung:** được dùng chung bởi nhiều máy nội bộ.
- **DNS forwarder** tại router, firewall, chi nhánh hoặc dịch vụ cloud.
- **Hệ điều hành và ứng dụng:** DNS Client ở Windows, systemd-resolved hay thư viện DNS; browser/runtime cũng có thể giữ cache riêng.
- **Hạ tầng container/Kubernetes:** CoreDNS, node-local DNS cache, sidecar hoặc lớp proxy nếu triển khai.
- **Mạng/VPN riêng:** client có thể sử dụng resolver do VPN cung cấp hoặc một resolver khác theo cấu hình split DNS.

**Cùng một sai lệch DNS có thể tồn tại ở nhiều lớp cache.** Xóa cache trên máy người dùng không giải quyết được recursive cache bị đầu độc; ngược lại, flush recursive resolver mà quên cache local có thể khiến triệu chứng còn xuất hiện trên một số client.

## 3. Cơ chế cache poisoning ở mức mô hình phòng vệ

Một cache chỉ trở nên nguy hiểm khi resolver **chấp nhận và sử dụng dữ liệu không đáng tin như dữ liệu phân giải hợp lệ**. Điều này có thể xảy ra vì kiểm tra phản hồi yếu, thành phần nguồn bị xâm nhập, cấu hình forwarder sai hoặc một đường truyền thiếu xác thực cho phép thay đổi dữ liệu.

~~~mermaid
flowchart TD
    A[Client yêu cầu phân giải tên] --> B[Resolver tìm cache]
    B --> C{Cache hợp lệ còn TTL?}
    C -- Có --> D[Trả dữ liệu đã cache]
    C -- Không --> E[Truy vấn DNS ra nguồn được cấu hình]
    E --> F{Dữ liệu trả về có vượt qua kiểm tra?}
    F -- Không --> G[Loại bỏ hoặc báo lỗi theo resolver]
    F -- Có --> H{DNSSEC / chính sách xác thực có áp dụng và thành công?}
    H -- Không hợp lệ với dữ liệu được bảo vệ --> G
    H -- Đạt yêu cầu theo trust model --> I[Cache RRset và phản hồi client]
    I --> D
~~~

Sơ đồ chỉ trình bày **mô hình kiểm soát**: không phải mọi tên miền đều có DNSSEC và việc không có chữ ký **không tự động** khiến resolver từ chối một vùng chưa ký. Độ an toàn phụ thuộc việc resolver áp dụng đúng chính sách đối với vùng **secure**, **insecure** hay dữ liệu **bogus**.

### 3.1. Dữ liệu có thể bị đưa sai vào cache ở đâu?

| Tình huống | Ranh giới tin cậy bị ảnh hưởng | Cần kiểm soát |
|---|---|---|
| Phản hồi DNS giả mạo từ ngoài đường đi (*off-path*) | Resolver quyết định phản hồi nào thực sự thuộc truy vấn đang chờ | Kiểm tra khớp transaction, entropy, bailiwick, DNSSEC validation |
| Sửa/giả mạo phản hồi trên đường truyền (*on-path*) | Tính toàn vẹn của đường resolver–upstream hoặc client–resolver | DNSSEC, bảo vệ kết nối tới resolver được tin cậy, chống xâm nhập mạng |
| Forwarder hoặc resolver bị chiếm quyền | Nguồn dữ liệu mà client/resolver tin cậy | Hardening, IAM, giám sát cấu hình, cập nhật bản vá |
| Máy client bị cấu hình DNS độc hại | Lựa chọn resolver của endpoint | DHCP/RA protection, endpoint security, NAC, VPN DNS policy |
| Thay đổi trái phép vùng authoritative | Bản ghi nguồn có thẩm quyền bị thay đổi | Quản lý quyền DNS provider/registrar, audit, MFA, thay đổi được duyệt |
| Cache local của ứng dụng/OS bị sửa hoặc sai | Dữ liệu trả về trong phạm vi endpoint | Bảo vệ endpoint, xác minh resolver path, xóa cache sau khi giữ bằng chứng |

Không phải mọi hàng ở bảng đều là **cache poisoning theo nghĩa hẹp**. Ví dụ thay đổi bản ghi authoritative hợp lệ về mặt DNS nhưng trái phép là **DNS account/zone compromise**; endpoint chuyển sang rogue resolver là **DNS hijacking**. Phân biệt này quyết định nơi xử lý nguyên nhân gốc.

## 4. Kiểm tra phản hồi DNS: vì sao không chỉ so tên miền?

Trong phân giải DNS truyền thống qua UDP, resolver cần biết một response có thực sự thuộc **outstanding query** hay không. Các yếu tố có thể gồm:

1. **Transaction ID (DNS ID):** trường định danh truy vấn và phản hồi.
2. **Cặp địa chỉ và cổng:** địa chỉ resolver, server, **source/destination UDP port**, cùng hướng trao đổi.
3. **Thông tin câu hỏi:** QNAME, QTYPE, QCLASS và trạng thái truy vấn.
4. **Thời điểm/đúng phiên xử lý:** phản hồi đến khi truy vấn vẫn đang chờ hay không.
5. **Tính hợp lý của dữ liệu trả lời:** authority, delegation và bailiwick.
6. **Xác thực mật mã nếu áp dụng:** DNSSEC validation của RRset và chuỗi tin cậy.

Việc chỉ đối chiếu một trường như transaction ID là **không đủ** để dựa vào làm phòng vệ. Khi nhiều đặc trưng truy vấn khó đoán và được kiểm tra nhất quán, việc giả một phản hồi được chấp nhận khó hơn; tuy nhiên những đặc trưng này **không tạo ra bảo đảm mật mã về nguồn gốc dữ liệu**.

### 4.1. Entropy của transaction ID và source port

- **DNS transaction ID** có kích thước giới hạn trong header DNS; không đủ để làm bằng chứng xác thực.
- **Ngẫu nhiên hóa source port** cho các truy vấn ra ngoài bổ sung một thành phần khó đoán. Nếu NAT, middlebox hoặc thiết bị mạng làm source port trở nên dễ đoán, lợi ích phòng vệ có thể giảm.
- **Không dùng source port hoặc transaction ID như một loại chữ ký mật mã.** Chúng là kiểm soát giảm xác suất chấp nhận phản hồi không thuộc truy vấn.
- **DNS Cookies** và một số kỹ thuật khác có thể hỗ trợ chống spoofing theo khả năng của resolver/authoritative server, nhưng không thay thế DNSSEC khi cần xác thực dữ liệu.

Trong đánh giá cấu hình, hãy xác minh **phiên bản resolver, cơ chế entropy, NAT và giới hạn từ thiết bị trung gian** theo tài liệu sản phẩm. Không cần thử tạo hoặc phát các phản hồi giả lên mạng để xác nhận điều kiện này.

### 4.2. Bailiwick checking

**Bailiwick** là cách resolver đánh giá dữ liệu đi kèm phản hồi có thuộc phạm vi thẩm quyền phù hợp và được phép đưa vào cache hay không. Ví dụ một phản hồi từ nguồn authoritative của một vùng không nên được tùy tiện sử dụng để đưa bản ghi tùy ý thuộc **vùng hoàn toàn không liên quan** vào cache.

Sự khác biệt giữa **answer**, **authority** và **additional section**, bản ghi glue trong delegation và trạng thái của vùng DNS khiến xử lý bailiwick không chỉ là một phép so chuỗi tên miền. Phần mềm resolver cần cập nhật và tuân thủ các quy tắc tin cậy phù hợp.

**Bailiwick checking giảm rủi ro**, nhưng không thay cho việc kiểm tra tính xác thực của dữ liệu được ký khi DNSSEC có sẵn.

## 5. DNSSEC: lớp xác thực dữ liệu DNS quan trọng nhất

**DNS Security Extensions (DNSSEC)** bổ sung khả năng xác minh **tính toàn vẹn và nguồn gốc xác thực của dữ liệu DNS** thông qua chữ ký số và chuỗi tin cậy. Resolver có chức năng DNSSEC validation có thể phát hiện dữ liệu giả mạo cho một vùng được bảo vệ đúng cách, thay vì chỉ dựa vào việc gói phản hồi có vẻ khớp truy vấn.

### 5.1. Các thành phần DNSSEC

| Thành phần | Vai trò |
|---|---|
| **DNSKEY** | Khóa công khai của vùng DNS dùng để kiểm tra chữ ký |
| **RRSIG** | Chữ ký số gắn với một RRset được ký |
| **DS** | Bản ghi trong vùng cha liên kết tới DNSKEY của vùng con, phục vụ chuỗi tin cậy |
| **Trust anchor** | Điểm neo tin cậy ban đầu của validator, thường là root trust anchor được quản lý đúng |
| **NSEC/NSEC3** | Bằng chứng đã ký cho dữ liệu không tồn tại theo cơ chế tương ứng |
| **Validating resolver** | Resolver thực sự kiểm tra chữ ký và chuỗi tin cậy trước khi chấp nhận dữ liệu |

### 5.2. Luồng xác thực ở mức khái niệm

~~~mermaid
flowchart TD
    A[Resolver có trust anchor tin cậy] --> B[Kiểm tra liên kết DS / DNSKEY qua các vùng]
    B --> C[Nhận RRset và RRSIG tại vùng được ký]
    C --> D{Chữ ký và chain of trust hợp lệ?}
    D -- Có --> E[Trạng thái secure: có thể trả dữ liệu hợp lệ]
    D -- Không khi dữ liệu phải được xác thực --> F[Bogus: không dùng dữ liệu như câu trả lời hợp lệ]
    B --> G{Vùng con chưa ký nhưng việc chưa ký được xác nhận đúng?}
    G -- Có --> H[Insecure: xử lý theo chính sách DNSSEC, không giả là secure]
~~~

Không phải mọi trường hợp thiếu chữ ký đều dẫn tới **SERVFAIL**: một vùng chưa ký được chứng minh là **insecure** có thể vẫn phân giải theo DNS bình thường, không có bảo đảm DNSSEC. Trong khi đó dữ liệu **bogus** (đáng ra phải xác thực nhưng kiểm tra thất bại) thường khiến validating resolver từ chối sử dụng và trả lỗi phù hợp, thường là SERVFAIL.

### 5.3. DNSSEC có những giới hạn nào?

- DNSSEC **không mã hóa truy vấn** và không che hostname khỏi các bên quan sát mạng.
- DNSSEC **không xác thực người dùng**, không kiểm tra quyền truy cập website và không thay chứng chỉ TLS/HTTPS.
- Nếu **authoritative zone hoặc khóa ký hợp lệ bị chiếm quyền**, dữ liệu sai nhưng được ký phù hợp vẫn có thể vượt qua validation; phải bảo vệ hệ thống quản trị DNS và vòng đời khóa.
- DNSSEC không tự bảo vệ client trước **rogue resolver, ứng dụng bỏ qua validator, cấu hình trust anchor không đúng** hoặc kết quả bị sửa sau điểm validation.
- Vùng **chưa ký** không được hưởng bảo đảm mật mã của DNSSEC.
- DNSSEC không giải quyết mọi **DoS/DDoS**; câu trả lời có chữ ký cũng vẫn cần năng lực mạng và hệ thống.

**DoT/DoH không đồng nghĩa DNSSEC.** DNS over TLS (DoT) hoặc DNS over HTTPS (DoH) bảo vệ kênh giữa client và resolver đã xác thực theo cơ chế tương ứng, giúp giảm nguy cơ quan sát/sửa dữ liệu **trên chặng đó**, nhưng **không chứng minh dữ liệu authoritative được ký đúng** nếu phía resolver không validation. Ngược lại DNSSEC có thể bảo vệ dữ liệu được ký ngay cả khi DNS truyền qua UDP không mã hóa, nếu client tin đúng validating resolver và câu trả lời không bị thay đổi sau điểm validation.

### 5.4. Rủi ro vận hành DNSSEC

DNSSEC yêu cầu chú ý **thời gian hệ thống, chữ ký hết hạn, rollover khóa, DS tại registrar/parent zone và trust anchor**. Nếu cấu hình DNSSEC sai, validator có thể từ chối bản ghi hợp pháp; đây là sự cố khả dụng chứ không tự động là một cuộc tấn công.

Khi thấy SERVFAIL, kiểm tra DNSSEC validation failure, kết nối tới authoritative, transport TCP/UDP, firewall, MTU và trạng thái của zone. **Không tắt DNSSEC validation toàn hệ thống chỉ để che một lỗi chưa tìm được nguyên nhân**.

## 6. DNS cache poisoning khác những vấn đề DNS nào?

| Hiện tượng | Cơ chế nổi bật | Dấu hiệu / phân biệt |
|---|---|---|
| **DNS cache poisoning** | Cache lưu dữ liệu không đúng/không đáng tin | Nhiều client dùng chung resolver nhận cùng dữ liệu sai; cần chứng minh dữ liệu trong cache |
| **DNS response spoofing** | Giả mạo phản hồi trên đường đi hoặc off-path | Có thể bị resolver loại bỏ; chỉ trở thành cache poisoning nếu dữ liệu sai được chấp nhận/cache |
| **DNS hijacking** | Ép client dùng resolver khác hoặc thay hướng phân giải | Kiểm tra DHCP, VPN, router, browser DoH, endpoint configuration |
| **Authoritative DNS compromise** | Bản ghi/zone ở nguồn có thẩm quyền bị sửa trái phép | Kiểm tra zone change log, registrar/DNS provider IAM, đồng nhất authoritative NS |
| **DNS rebinding** | Câu trả lời DNS thay đổi theo thời gian trong một kịch bản lợi dụng ranh giới trình duyệt/mạng | Không nhất thiết cần đầu độc recursive cache; cần kiểm soát lớp web/network tương ứng |
| **DNS tunneling** | Dữ liệu được mã hóa/đưa qua truy vấn và phản hồi DNS | Chủ yếu là abuse/exfiltration kênh DNS, không nhất thiết gây kết quả cache sai |
| **Cache staleness** | Cache giữ bản ghi cũ còn TTL, serve-stale hoặc client cache riêng | Có thể hợp lệ theo thiết kế; kiểm tra TTL và thời điểm thay đổi |
| **Split-horizon / CDN geo-routing** | Câu trả lời hợp lệ khác theo mạng/vùng/thời điểm | So với chính sách và bản ghi authoritative theo từng góc nhìn |

Điều tra dựa vào **bản ghi nào là đúng theo chủ sở hữu zone** và **đường phân giải của client cụ thể**. Không suy từ “hai resolver trả IP khác nhau” rằng một trong hai đã bị tấn công.

## 7. Các nguy cơ tác động đến người dùng và dịch vụ

### 7.1. Chuyển hướng website hoặc API

Nếu bản ghi A/AAAA sai khiến client kết nối tới máy không mong đợi, nguy cơ có thể là phishing, lấy cắp dữ liệu hoặc gián đoạn. Tuy nhiên, khi ứng dụng dùng **HTTPS và xác minh chứng chỉ/hostname đúng**, việc chuyển tới một máy không có chứng chỉ hợp lệ thường gây **cảnh báo TLS hoặc lỗi kết nối**, chứ không tự tạo một phiên HTTPS hợp lệ với endpoint bị giả.

Phòng vệ cần **DNS integrity + TLS hostname verification + authentication**. Không tắt xác minh TLS chỉ vì DNS có vấn đề.

### 7.2. Thư điện tử và service discovery

Thông tin MX/SRV sai có thể khiến ứng dụng thử gửi dữ liệu tới dịch vụ không mong đợi. Với email và dịch vụ có lớp xác thực khác, tác động thực tế phụ thuộc TLS, chính sách domain, quy trình xác thực và cấu hình gửi/nhận. Cần đánh giá **dữ liệu nào thực sự được trao đổi** thay vì chỉ nhìn bản ghi DNS.

### 7.3. Sai lệch diện rộng

Recursive resolver phục vụ nhiều subnet, chi nhánh hoặc khách VPN có thể làm một kết quả sai ảnh hưởng **nhiều người dùng cùng lúc**. Vì vậy việc bảo vệ resolver tập trung, phân quyền thay đổi DNS và giám sát các zone nhạy cảm là rất quan trọng.

### 7.4. Tính sẵn sàng và độ tin cậy

Cache phủ định sai, delegation sai hoặc resolver liên tục xác thực thất bại có thể làm một dịch vụ không thể phân giải, khiến ứng dụng báo timeout dù origin vẫn hoạt động bình thường. Sự cố về DNS đôi khi biểu hiện giống lỗi firewall, VPN hoặc backend; cần tách quá trình **phân giải tên** khỏi quá trình **kết nối tới IP** trong chẩn đoán.

## 8. Kiến trúc resolver doanh nghiệp an toàn

Giả sử một doanh nghiệp có **Users, Application, Database, Guest Wi-Fi, VPN-admin, Management và Cloud workloads**. Hệ thống dùng resolver tập trung cho các tài sản được quản lý.

~~~mermaid
flowchart TB
    U[Users subnet] --> F[DNS egress policy]
    A[Application subnet] --> F
    V[Managed VPN clients] --> F
    G[Guest Wi-Fi] --> GF[Chính sách DNS riêng cho Guest]
    F --> R[Recursive resolver nội bộ có validation]
    R --> Q[DNS forwarder / upstream được kiểm soát]
    Q --> I[Internet authoritative DNS]
    R --> L[DNS query / validation logs]
    F --> L
    L --> S[SOC / SIEM]
    M[Management / IAM] -. Quản trị được kiểm soát .-> R
    GF --> GR[Guest resolver theo chính sách]
~~~

Sơ đồ là **mô hình logic**: một validating resolver có thể tự phân giải iterative thay vì phải dùng forwarder; với split DNS, các zone nội bộ có thể được chuyển đến authoritative server nội bộ theo conditional forwarding. **Không cho authoritative public và recursive nội bộ cùng quyền truy cập không hạn chế chỉ vì dùng chung phần mềm DNS**.

### 8.1. Các ranh giới phải bảo vệ

| Ranh giới | Quy tắc thiết kế |
|---|---|
| **Client → resolver** | Client chỉ được truy cập resolver được cấp phép, qua UDP/TCP 53 hoặc DoT/DoH được quản lý tùy mô hình |
| **Resolver → nguồn DNS** | Egress giới hạn theo vai trò, cập nhật phần mềm, kiểm soát NAT và lọc phản hồi bất thường |
| **Resolver management** | Chỉ Management subnet/VPN-admin đã xác thực được sửa cấu hình; MFA, RBAC, change log |
| **DNS nội bộ / split horizon** | Xác định authoritative nội bộ/forwarder chính xác, không làm rò tên nội bộ ra ngoài |
| **Guest Wi-Fi và IoT** | Không tự được truy cập zone nội bộ; DNS policy phù hợp với mức tin cậy |
| **Cloud/VPN** | Cân nhắc route, VPC/VNet resolver, split DNS, private zone và các đường DNS đi vòng |
| **Resolver → SOC** | Log được chuẩn hóa, hạn chế dữ liệu nhạy cảm, giữ đường giám sát độc lập khi phù hợp |

### 8.2. DNS egress policy không thể chỉ là một rule UDP/53

DNS có thể dùng **TCP 53**, DoT thường dùng **TCP 853**, DoH có thể chạy trong **HTTPS 443**, và ứng dụng có thể có resolver riêng. Chặn UDP/53 ra ngoài không đủ để chứng minh mọi ứng dụng đều dùng resolver nội bộ.

Trong mạng có quản lý tập trung, cần kết hợp:

- Cấu hình resolver trên thiết bị, DHCP/VPN và chính sách endpoint.
- Firewall egress theo subnet/zone, bao gồm UDP/TCP 53 phù hợp.
- Kiểm soát DoT/DoH bằng quản lý endpoint, browser policy hoặc egress gateway có khả năng phù hợp, không chỉ dựa vào port.
- Kiểm thử ở **IPv4 và IPv6**, qua VPN split-tunnel và các mạng Wi-Fi.
- Giám sát các đường truy vấn khác như DNS proxy/forwarder của cloud hay container.

Việc buộc DNS về một resolver tin cậy **không tự thay DNSSEC validation** và không bảo vệ khi chính resolver nội bộ bị xâm nhập.

## 9. Hardening recursive resolver

### 9.1. Danh sách kiểm soát nền tảng

| Kiểm soát | Vai trò với cache poisoning | Ghi chú vận hành |
|---|---|---|
| **Cập nhật resolver thường xuyên** | Vá lỗi parsing, validation hoặc cache handling | Theo dõi CVE và kế hoạch rollback |
| **Giới hạn recursion theo client** | Ngăn trở thành open resolver và giảm bề mặt abuse | Phân biệt authoritative public và recursive internal |
| **DNSSEC validation được cấu hình đúng** | Xác minh dữ liệu DNS có chữ ký và chain of trust | Monitor bogus/SERVFAIL, rollover và trust anchor |
| **Ngẫu nhiên hóa transaction ID/source port** | Giảm khả năng chấp nhận phản hồi giả không thuộc truy vấn | Kiểm tra NAT và middleware không làm giảm entropy |
| **Bailiwick và xử lý delegation đúng** | Hạn chế tin dữ liệu ngoài thẩm quyền trong response | Dựa vào resolver đã bảo trì, tránh phần mềm lỗi thời |
| **Egress/upstream tin cậy** | Giảm số nguồn trả lời không được mong đợi | Xem bảo vệ kết nối khi forwarding |
| **Least privilege cho tài khoản chạy dịch vụ** | Hạn chế tác động khi resolver bị khai thác | Quản trị tách biệt, logging, filesystem và sandbox nếu hỗ trợ |
| **Tách vai trò/quyền truy cập** | Giảm rủi ro thay zone và recursive cache bằng tài khoản chung | IAM, MFA, audit và change control |
| **Giới hạn abuse/rate theo chính sách** | Hỗ trợ khả dụng, giảm quá tải | Không chặn traffic DNS hợp lệ với ngưỡng cứng tùy ý |
| **Telemetry và baseline** | Phát hiện thay đổi bất thường về answer và validation | Bảo vệ dữ liệu log |

### 9.2. Cấu hình ý định, không phải cú pháp một sản phẩm

~~~yaml
# Pseudocode mô tả yêu cầu; KHÔNG áp dụng trực tiếp cho BIND/Unbound/CoreDNS.
resolver_policy:
  name: "enterprise-validating-resolver"
  role: "recursive"
  listeners: ["approved-internal-interfaces"]
  allowed_clients: ["managed-users", "app-subnets", "approved-vpn-pools"]
  public_open_recursion: false
  dnssec_validation: true
  trust_anchor_management: "automated-and-monitored"
  accept_only_matching_responses: true
  source_port_randomization: true
  enforce_bailiwick: true
  upstreams:
    - "approved-forwarder-or-iterative-resolution"
  management:
    authorized_roles: ["network-security-admin"]
    audit_changes: true
  monitoring:
    track: ["answer_changes", "dnssec_failures", "cache_events", "query_errors"]
    redact_sensitive_queries: true
  incident_response:
    preserve_evidence_before_cache_invalidation: true
~~~

Các lựa chọn như source port randomization và bailiwick handling có thể là **hành vi mặc định của engine**, không có tùy chọn cấu hình mang cùng tên. Chỉ chuyển ý định thành cấu hình thật bằng tài liệu chính thức cho phiên bản resolver đang sử dụng.

## 10. Giám sát DNS để phát hiện dữ liệu sai

Phát hiện cache poisoning khó hơn việc chỉ tìm một chữ ký: nhiều kết quả trả về có thể thay đổi hợp lệ theo TTL, CDN hoặc địa điểm. Mô hình phát hiện nên kết hợp **tính đúng của dữ liệu, bối cảnh mạng và chuỗi hoạt động**.

| Tín hiệu | Giải thích có thể | Bằng chứng cần đối chiếu |
|---|---|---|
| Hostname trọng yếu đột ngột trả IP không nằm trong tập dự kiến | Poisoning, thay đổi DNS hợp lệ hoặc failover | Owner DNS, authoritative data, change ticket, CDN policy |
| Nhiều client cùng resolver nhận dữ liệu sai | Cache/forwarder chung là nghi phạm | Resolver identity, per-hop lookup, TTL và cache status |
| DNSSEC validation failures/SERVFAIL tăng | Dữ liệu bogus, khóa/chữ ký lỗi, network path lỗi | DS/DNSKEY/RRSIG, validator log, authoritative reachability |
| Truy vấn trả lời bất thường ở authority/additional | Có thể là dữ liệu delegation/glue không mong muốn | Bailiwick logic, query-response trace theo quy trình được phép |
| DNS answer khác biệt IPv4/IPv6 | Cấu hình AAAA, CDN, split-horizon hoặc vấn đề DNS | Kiểm tra cả A/AAAA, VPN và DNS egress path |
| Resolver đổi đột ngột trên thiết bị | DHCP/RA/VPN/browser config sai hoặc hijacking | Endpoint policy, DHCP logs, router logs, browser DoH |
| Lỗi DNS lan rộng sau thay đổi mạng | Firewall/NAT đang chặn TCP 53 hoặc EDNS/PMTU | Route, ACL, logs, TCP fallback và packet sizing |
| Cache có TTL hoặc bản ghi không phù hợp kỳ vọng | Dữ liệu stale hoặc chính sách cache khác | TTL authoritative, serve-stale, negative caching và thời điểm hỏi |

### 10.1. Telemetry nên thu từ đâu?

- **Resolver query/response/validation logs** hoặc DNS security telemetry nếu sản phẩm hỗ trợ.
- **Firewall flow logs** giữa client và resolver; giữa resolver và upstream.
- **Endpoint configuration/logs**, bao gồm thay đổi DNS server, VPN và DoH/DoT policy.
- **Authoritative DNS/provider audit**, zone version, record updates và registrar events.
- **IDS/IPS/NDR** tại những đường DNS mà sensor có thể quan sát.
- **Synthetic DNS checks** từ vài mạng/vị trí khác nhau, có so sánh với nguồn dữ liệu authoritative theo đúng split-horizon.

DNS query log có thể tiết lộ **hostname nội bộ, dịch vụ người dùng truy cập hoặc hành vi nhạy cảm**. Áp dụng giảm thiểu dữ liệu, giới hạn quyền truy cập, retention và che dữ liệu khi chia sẻ sự cố.

### 10.2. Không nhầm anomaly với kết luận

Trả về nhiều A/AAAA records hoặc IP của CDN khác nhau là bình thường trong nhiều kiến trúc. TTL giảm qua các lần hỏi là hành vi bình thường khi cache đang đếm ngược. Một số resolver phục vụ **stale data có kiểm soát** để giữ khả dụng khi authoritative không trả lời. Cần hiểu chính sách trước khi gắn nhãn “poisoned”.

## 11. Cách đọc DNS response và DNSSEC ở mức an toàn

### 11.1. Các cờ DNS hữu ích

| Cờ hoặc trường | Ý nghĩa thực tiễn | Không được suy ra |
|---|---|---|
| **QR** | Đây là query hay response | Không chỉ ra dữ liệu đúng |
| **AA** | Phản hồi được đánh dấu authoritative bởi server trả lời | Không tự chứng minh nguồn đáng tin hoặc dữ liệu không bị sửa |
| **RD / RA** | Client yêu cầu recursion / server hỗ trợ recursion | Không có nghĩa resolver đang DNSSEC validate |
| **AD (Authenticated Data)** | Validator tin cậy đánh dấu dữ liệu được xác thực theo DNSSEC | Không đáng tin nếu lấy từ server/đường truyền không đáng tin mà client không tự validation |
| **CD (Checking Disabled)** | Client yêu cầu không thực hiện một số kiểm tra validation ở resolver theo semantics DNSSEC | Không nên dùng để che lỗi DNSSEC trên production |
| **RCODE** | Trạng thái như NOERROR, NXDOMAIN, SERVFAIL | SERVFAIL có nhiều nguyên nhân, không chỉ DNSSEC |
| **TTL** | Thời gian lưu cache còn lại hoặc theo phản hồi | Không là chữ ký bảo đảm bản ghi đúng |

Nếu dùng dig với **+dnssec**, công cụ yêu cầu dữ liệu DNSSEC khi thích hợp; **việc có RRSIG trong output không có nghĩa dig tự thực hiện DNSSEC validation**. Cần dùng một validating resolver được tin cậy hoặc công cụ có xác thực chữ ký và trust anchor thích hợp.

### 11.2. Chỉ số cần phân biệt

- **NXDOMAIN:** tên được hỏi không tồn tại trong ngữ cảnh DNS được trả lời.
- **NOERROR với dữ liệu trống (NODATA):** tên có thể tồn tại nhưng không có record type được hỏi.
- **SERVFAIL:** resolver không hoàn thành phân giải; có thể do DNSSEC bogus, timeout, lỗi liên lạc hoặc cấu hình.
- **REFUSED:** server từ chối phục vụ loại truy vấn hoặc nguồn client này theo chính sách.

Không nên diễn giải mọi **NXDOMAIN** hoặc **SERVFAIL** là kết quả của cache poisoning.

## 12. Các lệnh truy vấn và kiểm tra được phép

Các ví dụ dưới đây chỉ truy vấn DNS thông thường, phục vụ hệ thống mà bạn có quyền giám sát. **10.50.0.53** là resolver nội bộ giả định; **portal.example.com** và địa chỉ IP ví dụ không đại diện cho một hệ thống đang chạy.

### 12.1. Linux / macOS (nếu có dig)

~~~bash
# Quan sát câu trả lời A từ resolver nội bộ giả định
dig @10.50.0.53 portal.example.com A

# Quan sát AAAA cho môi trường dual-stack
dig @10.50.0.53 portal.example.com AAAA

# Yêu cầu dữ liệu DNSSEC khi thích hợp; không tự chứng minh validation
dig @10.50.0.53 portal.example.com A +dnssec

# Thử DNS over TCP 53 để chẩn đoán vấn đề UDP/path
dig @10.50.0.53 portal.example.com A +tcp

# Nếu máy có systemd-resolved, xem resolver hệ thống đang được cấu hình
resolvectl status
~~~

**Chú ý:** lệnh truy vấn có thể đi tới resolver riêng của hệ thống hoặc chuyển qua VPN tùy cách cấu hình. Phải xác nhận đang so **cùng DNS view**. Khi kiểm tra authoritative server, trước tiên xác định server đúng từ tài liệu/quyền sở hữu zone, không tự giả định một địa chỉ bất kỳ là authoritative.

### 12.2. Windows PowerShell

~~~powershell
# Kiểm tra DNS server hệ thống theo từng interface
Get-DnsClientServerAddress

# Xem dữ liệu trong Windows DNS Client cache nếu khả dụng
Get-DnsClientCache

# Hỏi một resolver được phép kiểm thử
Resolve-DnsName portal.example.com -Type A -Server 10.50.0.53
Resolve-DnsName portal.example.com -Type AAAA -Server 10.50.0.53
~~~

**Khác nhau giữa query trực tiếp và cache local:** lệnh hỏi một resolver chỉ cho biết server được chọn trả gì ở thời điểm đó. Client có thể còn cache local hoặc ứng dụng/browser có resolver riêng. Không kết luận cache local đã sạch chỉ từ kết quả một lệnh.

### 12.3. Xác minh DNSSEC

Nếu có công cụ hỗ trợ validation độc lập như **delv** với trust anchor được thiết lập đúng, có thể dùng trong môi trường cho phép:

~~~bash
# Xác minh theo cấu hình trust anchor và resolver của công cụ
delv example.com A
~~~

Không dùng một câu trả lời có cờ **AD** từ một resolver không tin cậy làm bằng chứng duy nhất, và không tắt validation để “làm cho kết quả đúng”. Các tên miền **chưa ký** phải được đánh giá theo trạng thái insecure đúng nghĩa; không mặc định delv sẽ cho ra một kết quả có chữ ký với mọi domain.

## 13. DNSSEC trong cloud, VPN, Kubernetes và Wi-Fi

### 13.1. Cloud DNS và private zones

Một cloud provider có thể cung cấp resolver nội bộ, forwarding rules, private hosted zones và một số chức năng DNSSEC. **Khả năng ký zone và khả năng validation tại resolver là hai tính năng khác nhau**; không nên đánh đồng việc DNS authoritative hỗ trợ ký DNSSEC với việc mọi recursive resolver tự xác minh câu trả lời.

Khi triển khai phải kiểm tra:

- Private/public zone nào là authoritative, có split-horizon hoặc conditional forwarding không?
- VPC/VNet nào dùng resolver nào và qua route/firewall nào?
- Resolver có DNSSEC validation cho những truy vấn/zone nào theo tài liệu sản phẩm?
- Các request từ peering, VPN, serverless, container hoặc workload khác có đường bypass resolver nội bộ không?
- Log DNS có đi được vào SOC và có ranh giới quyền truy cập phù hợp không?

### 13.2. Kubernetes và dịch vụ khám phá nội bộ

Trong Kubernetes, **CoreDNS** thường cung cấp phân giải tên dịch vụ và có thể forward truy vấn ngoài cluster tới upstream. Cache có thể tồn tại ở CoreDNS, NodeLocal DNSCache (nếu được triển khai), runtime hoặc ứng dụng.

Kiểm tra **ConfigMap, upstream forwarding, network policy, service discovery, phân quyền cập nhật cấu hình**, và cơ chế DNSSEC của các zone được hỏi. Không giả định tên nội bộ của cluster tự được bảo vệ bằng DNSSEC công cộng. Nếu sửa upstream hoặc chính sách DNS egress, cần kiểm thử các phụ thuộc của pod, control plane và dịch vụ hệ thống.

### 13.3. VPN, Wi-Fi và thiết bị đầu cuối

VPN có thể cung cấp DNS resolver nội bộ và search suffix, đôi khi chỉ áp cho một số namespace tên miền (**split DNS**). Một thiết bị dùng nhiều interface có thể hỏi nhiều resolver khác nhau tùy OS/browser chính sách.

Trên mạng Wi-Fi, DHCPv4, DHCPv6 hoặc **Router Advertisement với thông tin DNS (RDNSS)** có thể ảnh hưởng lựa chọn DNS của client khi được hỗ trợ. **Rogue AP, DHCP server hoặc RA** là nguy cơ ở lớp truy cập, cần xác thực Wi-Fi, NAC, DHCP snooping/RA Guard (nếu phù hợp), client isolation và chính sách endpoint. DNSSEC validation không thay thế các biện pháp bảo vệ **đường kết nối tới resolver** hoặc xác thực thiết bị.

## 14. Một ví dụ phân tích dữ liệu DNS bị sai

Giả sử tổ chức sở hữu **portal.example.com**, theo thay đổi được duyệt có A record **203.0.113.24** trong một DNS view cụ thể. Nhóm hỗ trợ nhận báo cáo rằng một số thiết bị ở subnet Users lại nhận **198.51.100.66**.

### 14.1. Quan sát ban đầu

| Thành phần | Kết quả giả định | Câu hỏi |
|---|---|---|
| Authoritative DNS đúng view | 203.0.113.24 | Có được owner xác nhận đúng theo change record không? |
| Recursive resolver nội bộ R1 | 198.51.100.66 | Có đang trả dữ liệu sai từ cache/forwarder không? |
| Recursive resolver nội bộ R2 | 203.0.113.24 | Vì sao R1 khác R2? |
| Máy A dùng R1 | 198.51.100.66 | Có cache local hoặc DNS proxy nào khác không? |
| Máy B dùng R2 | 203.0.113.24 | Có khác DNS view/VPN/interface không? |

**Đây chưa phải bằng chứng kết luận bị tấn công.** Cần kiểm tra địa chỉ, TTL, chuỗi CNAME, split DNS, cập nhật bản ghi, CDN policy, authoritative NS và dữ liệu từ resolver.

### 14.2. Giả thuyết cần xét

1. R1 có **cache bị nhiễm bẩn** sau khi chấp nhận một phản hồi không đáng tin.
2. R1 đang hỏi **forwarder/upstream khác** và nhận dữ liệu từ nguồn đã bị sửa.
3. R1 đang dùng **view nội bộ khác** hoặc bản ghi còn TTL chưa hết sau thay đổi hợp lệ.
4. Một thay đổi **zone authoritative/registrar** đã diễn ra mà nhóm ứng dụng chưa cập nhật.
5. Client thật ra không hỏi R1 do **browser DoH/VPN/split DNS**.
6. DNSSEC bị cấu hình sai hoặc chưa triển khai, và dữ liệu chỉ được đánh giá bằng cơ chế DNS thường.

### 14.3. Hướng xử lý có kiểm soát

Thu thập log và cache entry của R1 trước khi thay đổi; ghi timestamp, TTL còn lại, QNAME/QTYPE, dữ liệu trả về, upstream đã hỏi, phiên bản cấu hình, các thay đổi gần đây và trạng thái DNSSEC. Sau khi xác định nguyên nhân, sửa policy/forwarding/validator hoặc nguồn authoritative, rồi **invalidate có phạm vi tối thiểu** các cache bị ảnh hưởng. Kiểm thử lại từ client thực, từ R1/R2 và qua cả A/AAAA, HTTPS/TLS.

**Không flush cache toàn doanh nghiệp ngay lập tức nếu chưa giữ bằng chứng và chưa xử lý đường tạo dữ liệu sai.** Một resolver còn nhận phản hồi sai có thể bị nhiễm bẩn lại; flush diện rộng cũng làm tăng số truy vấn tới upstream và có thể ảnh hưởng hiệu năng.

## 15. Quy trình ứng phó sự cố DNS cache poisoning

### Giai đoạn 1 — Phát hiện và khoanh vùng

1. Nhận thông tin từ user, SOC, synthetic monitoring, EDR hoặc hệ thống ứng dụng.
2. Xác định **hostname, QTYPE, DNS view, subnet, client, resolver, thời gian** và tác động đến HTTPS/API/email/VPN.
3. Ghi **câu trả lời sai và đúng kỳ vọng theo owner** với thời gian/TTL; không dựa vào một IP “quen thuộc” đã ghi trong tài liệu cũ.
4. So sánh log/response từ **đúng authoritative source**, validating resolver tin cậy và resolver bị nghi vấn, chú ý geo/CDN/split-horizon.
5. Xác định có một client, một resolver, một chi nhánh hay toàn tổ chức bị ảnh hưởng.

### Giai đoạn 2 — Thu thập bằng chứng

- Resolver configuration/version, upstream/forwarder, NAT/firewall path và quyền truy cập.
- Query/response log, cache entry, negative cache và trạng thái validation khi có.
- DNS provider audit, zone/registrar change history, DNSKEY/DS/RRSIG khi dùng DNSSEC.
- Endpoint DNS settings, VPN/DoH policy, Wi-Fi/DHCP/RA logs.
- Dấu vết kết nối của client tới **IP nhận được**, cùng TLS errors, application logs và proxy.

Lưu dữ liệu điều tra có phạm vi, giới hạn quyền và **không ghi token/mật khẩu** vào bằng chứng.

### Giai đoạn 3 — Ngăn ảnh hưởng và sửa nguồn

| Phát hiện | Ưu tiên xử lý |
|---|---|
| Recursive cache nhiễm bẩn, upstream/config đã được xác minh sạch | Invalidate đúng RRset/cache có liên quan, kiểm tra propagation |
| Forwarder không tin cậy hoặc bị sửa | Chuyển sang nguồn được phê duyệt theo change control, bảo vệ kết nối |
| Resolver bị xâm nhập | Cô lập quản trị, giữ forensic evidence, khôi phục hệ thống tin cậy |
| DNS provider/registrar bị chiếm quyền | Khóa truy cập, sửa bản ghi theo owner, rà soát MFA/keys/audit |
| Rogue DNS ở client/Wi-Fi | Sửa DHCP/RA/VPN/endpoint policy và loại bỏ nguồn trái phép |
| DNSSEC chain bị lỗi vận hành | Sửa chữ ký/DS/DNSKEY/time/rollover theo owner, giữ validation bật |

Không nên xử lý sự cố DNS bằng cách **tắt TLS hostname verification, cho phép mọi DNS server, bỏ MFA hoặc vô hiệu hóa DNSSEC validation toàn mạng**.

### Giai đoạn 4 — Xác minh phục hồi

- Query từ nhiều client và zone cho kết quả phù hợp authoritative policy.
- Validator xử lý đúng dữ liệu **secure/insecure/bogus** và không có lỗi DNSSEC mới.
- Cache entry sai đã được thay thế hoặc hết hiệu lực ở các tầng có liên quan.
- DNS over UDP/TCP, IPv4/IPv6, VPN và cloud forwarding hoạt động như thiết kế.
- Ứng dụng tiếp tục xác minh **TLS certificate/hostname**, API/SSO/email hoạt động.
- Query/validation logs, firewall/IDS telemetry và alert pipeline trở lại bình thường.

### Giai đoạn 5 — Hậu kiểm

Lập timeline, nguyên nhân gốc, phạm vi ảnh hưởng, đường tin cậy bị phá vỡ, các yếu tố khiến dữ liệu sai vào cache, quyết định ứng phó, rủi ro tồn dư và hành động cải tiến. Xác nhận **owner, thời hạn và bài thử hồi quy** cho từng thay đổi hạ tầng DNS.

~~~mermaid
flowchart TD
    A[Cảnh báo DNS sai / bất thường] --> B[Xác minh owner, view và authoritative answer]
    B --> C[Khoanh vùng cache / forwarder / endpoint]
    C --> D[Thu bằng chứng trước khi thay đổi]
    D --> E{Nguyên nhân nằm ở đâu?}
    E -- Cache/Resolver --> F[Hardening / sửa forwarding / invalidate có phạm vi]
    E -- Authoritative/Registrar --> G[Khôi phục zone, quyền và DNSSEC]
    E -- Client/VPN/Wi-Fi --> H[Sửa resolver selection và NAC/endpoint policy]
    F --> I[Kiểm thử A/AAAA, DNSSEC, app/TLS]
    G --> I
    H --> I
    I --> J[Giám sát tái diễn và hậu kiểm]
~~~

## 16. Các chỉ số và cảnh báo nên duy trì

| Chỉ số/cảnh báo | Mục đích | Nguy cơ diễn giải sai |
|---|---|---|
| Thay đổi RRset cho domain trọng yếu ngoài change window | Phát hiện sai lệch cần xác minh | CDN/failover hợp lệ cũng thay IP |
| Lỗi DNSSEC validation theo zone và resolver | Phát hiện dữ liệu bogus hoặc sai cấu hình | SERVFAIL còn có nguyên nhân kết nối |
| Tỷ lệ NXDOMAIN/NODATA/SERVFAIL | Phát hiện bất thường phân giải | Lỗi tên hoặc ứng dụng thử truy vấn cũng tăng NXDOMAIN |
| Tỷ lệ query qua resolver được quản lý | Đo DNS egress policy coverage | DoH/DoT và app riêng có thể nằm ngoài quan sát |
| Resolver config/forwarder/trust anchor drift | Phát hiện thay đổi nguồn tin cậy | Cần mapping với change ticket |
| TTL bất thường và serve-stale events | Giúp tìm sự cố cache | TTL giảm dần là hành vi cache bình thường |
| DNS trả IP đích không thuộc danh sách dự kiến | Giảm thời gian phát hiện chuyển hướng | Geo/CDN/split-horizon có thể hợp lệ |
| Dịch vụ TLS errors cùng thời điểm DNS đổi | Tương quan kết quả DNS và ứng dụng | Lỗi chứng chỉ riêng cũng gây triệu chứng giống |
| Tăng recursive query hoặc outbound port anomalies | Hỗ trợ phát hiện sai lệch resolver/network | Cần baseline, tránh khẳng định spoofing từ một metric |

Đừng giám sát mỗi **số query DNS**. Mục tiêu của cache poisoning là **độ tin cậy dữ liệu trả về**; một cache sai có thể trả cùng câu trả lời nhiều lần mà không tạo lượng truy vấn đột biến.

## 17. Kiểm thử và xác minh phòng thủ mà không tạo cuộc tấn công

Kiểm thử nên dựa trên **các quyền và môi trường được phê duyệt**. Không cần giả mạo gói, đoán transaction ID hoặc phát phản hồi độc hại trên mạng thực để đánh giá chất lượng phòng vệ.

| Test | Tình huống | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| T-01 | Truy vấn A/AAAA từ Users, App và VPN | Resolver/path đúng theo chính sách từng zone | DNS server config, flow logs, response |
| T-02 | Domain DNSSEC hợp lệ được xác minh bằng validator tin cậy | Dữ liệu được trả với trạng thái xác thực phù hợp | Validator status, log hoặc kết quả từ công cụ validation |
| T-03 | Dữ liệu DNSSEC không hợp lệ trong lab được kiểm soát | Validator không trả dữ liệu bogus như hợp lệ | Validation error và response status |
| T-04 | Domain chưa ký, được chứng minh insecure | Resolver xử lý theo trust model, không giả là secure | Validator classification |
| T-05 | Client dùng DNS khác ngoài danh sách cho phép | Egress policy phát hiện/chặn theo thiết kế | Firewall, endpoint policy và log |
| T-06 | Client bật browser DoH hoặc dùng VPN split DNS | Không phá chính sách DNS doanh nghiệp | Browser/VPN policy, resolver logs |
| T-07 | Thay đổi bản ghi hợp lệ có TTL được kiểm soát | Cache hết hạn/được cập nhật theo chính sách | Authoritative, recursive, client timing |
| T-08 | Ngắt upstream tạm trong lab | Resolver phục hồi hoặc báo lỗi theo thiết kế, không giữ dữ liệu sai | Availability logs, serve-stale metrics |
| T-09 | Thay đổi DNS server qua rogue DHCP/RA trong lab riêng | NAC/endpoint phát hiện hoặc ngăn theo chính sách | DHCP/RA Guard events và client config |
| T-10 | Cấu hình DNSSEC rollover thử nghiệm | Chữ ký và DS/DNSKEY chuyển đổi đúng, không gây SERVFAIL diện rộng | DNSSEC validation trước/sau |
| T-11 | Một resolver chứa dữ liệu test stale trong môi trường riêng | Có quy trình evidence → invalidate đúng phạm vi → verify | Cache audit, query response và change log |
| T-12 | Ứng dụng nhận IP sai trong lab | HTTPS hostname verification không bị tắt để “sửa” DNS | TLS error và log client |

Trong test T-03/T-09, chỉ dùng **lab cô lập hoặc harness chuyên dụng đã được cấp quyền**, không tạo dữ liệu giả vào resolver production hay tác động thiết bị của người khác.

## 18. Những sai lầm phổ biến

| Ngộ nhận/sai lầm | Vì sao không đúng | Cách làm phù hợp |
|---|---|---|
| “DNS cache poisoning là mọi lần IP trả về khác nhau.” | CDN, split DNS và failover có thể thay đổi hợp lệ | Đối chiếu authoritative view, owner, TTL và lịch thay đổi |
| “Chỉ bật DNSSEC trên authoritative là mọi client an toàn.” | Cần validator đáng tin và chuỗi tin cậy được kiểm tra | Kiểm thử end-to-end, quản lý trust anchor |
| “DoH/DoT tự bảo đảm bản ghi authoritative đúng.” | Mã hóa một chặng không chứng minh zone data đã được ký/validated | Kết hợp transport protection với DNSSEC validation |
| “Transaction ID khớp thì phản hồi chắc chắn thật.” | Trường có không gian giới hạn và không xác thực mật mã | Port entropy, matching, bailiwick và DNSSEC |
| “Thấy AD thì chắc chắn server đáng tin.” | Flag có thể xuất hiện qua đường không tin cậy | Dùng validator tin cậy, bảo vệ client–resolver path |
| “Mọi SERVFAIL chứng minh đang bị tấn công.” | Có thể DNSSEC rollover lỗi, timeout hoặc TCP 53 bị chặn | Xem validator logs, route, time, DS/DNSKEY |
| “Flush cache là giải quyết triệt để.” | Upstream hoặc resolver bị xâm nhập có thể lại trả dữ liệu sai | Giữ bằng chứng, sửa nguồn, invalidate đúng phạm vi |
| “Tắt UDP/53 ra ngoài là không còn DNS bypass.” | TCP 53, DoT, DoH và resolver riêng vẫn có thể tồn tại | Endpoint/browser policy, egress và quan sát phù hợp |
| “DNSSEC làm cho HTTPS không còn cần chứng chỉ.” | DNSSEC xác thực dữ liệu DNS, không tự xác thực phiên TLS | Giữ certificate/hostname validation và authz |
| “Chỉ đo query rate là phát hiện poisoning.” | Một entry sai có thể được cache và tái sử dụng lâu | Giám sát RRset, validation, DNS view và nguồn cấu hình |
| “DNS chỉ có A record nên không cần xét IPv6.” | AAAA và nhiều loại RRset khác cũng ảnh hưởng kết nối | Kiểm tra A/AAAA/CNAME/NS/MX và dual-stack |

## 19. Checklist bảo vệ DNS cache

- [ ] Có inventory recursive resolvers, forwarders, stub caches và các tuyến DNS trong LAN, VPN, cloud, Kubernetes.
- [ ] Biết chủ sở hữu authoritative zone, registrar/provider và người phê duyệt thay đổi.
- [ ] Chỉ cho client được cấp quyền sử dụng recursive resolver; không vô tình mở public recursion.
- [ ] Resolver được vá lỗi và kiểm tra version/health, source-port entropy và NAT behavior.
- [ ] Resolver kiểm tra câu trả lời khớp truy vấn và bailiwick theo engine đã bảo trì.
- [ ] Dùng DNSSEC validation cho dữ liệu được ký; quản lý trust anchor, DS/DNSKEY/RRSIG và rollover.
- [ ] Biết phân biệt secure, insecure và bogus; không tắt validation để né SERVFAIL.
- [ ] Quản lý DNS egress UDP/TCP 53, DoT, DoH, IPv4/IPv6 và các DNS proxy của workload.
- [ ] Kiểm soát DNS server selection qua DHCP, VPN, Wi-Fi, RA và endpoint/browser policy.
- [ ] Tách Management và Guest Wi-Fi khỏi quyền DNS nội bộ không cần thiết.
- [ ] Tách quyền quản trị resolver, authoritative DNS và registrar; dùng IAM/MFA, audit và change control.
- [ ] Giám sát RRset/TTL cho tên trọng yếu và các DNSSEC validation errors, có baseline hợp lệ.
- [ ] Correlate resolver logs với firewall, IDS/IPS, endpoint, VPN và application/TLS telemetry.
- [ ] Bảo vệ DNS query logs khỏi lộ tên nội bộ, dữ liệu cá nhân, secret và quyền truy cập trái phép.
- [ ] Có playbook xác minh authoritative view, lưu bằng chứng, xử lý nguồn, invalidate cache theo phạm vi và test lại.
- [ ] Có bài kiểm thử DNSSEC, split DNS, cloud forwarding, cache expiry và dự phòng.
- [ ] Không coi DNSSEC là thay thế TLS hostname verification, ứng dụng an toàn hoặc giám sát sự cố.

## 20. Câu hỏi tự kiểm tra

**1. DNS cache poisoning khác DNS spoofing ở điểm nào?**  
DNS spoofing là hành vi cung cấp hoặc giả mạo câu trả lời sai; cache poisoning xảy ra khi một thành phần phân giải **chấp nhận và lưu** dữ liệu sai, ảnh hưởng những truy vấn sau. Không phải phản hồi giả nào cũng đi vào cache.

**2. Vì sao source-port randomization và transaction ID chưa đủ để chứng minh dữ liệu đúng?**  
Chúng làm phản hồi khó đoán và khó giả mạo hơn, nhưng không kiểm tra được chữ ký mật mã của RRset. DNSSEC mới cung cấp bảo đảm nguồn gốc/tính toàn vẹn cho dữ liệu được ký và được validation đúng.

**3. Bailiwick checking bảo vệ điều gì?**  
Nó hạn chế resolver tiếp nhận/cache dữ liệu DNS đi kèm từ nguồn không có thẩm quyền phù hợp, đặc biệt ở các phần authority/additional và xử lý delegation.

**4. Vì sao hai recursive resolver có thể trả IP khác nhau mà không có cuộc tấn công?**  
Có thể do CDN, split DNS, geo-routing, TTL, serve-stale hoặc thay đổi bản ghi hợp lệ. Cần xác định đúng DNS view và authoritative policy trước khi kết luận.

**5. DNSSEC có mã hóa truy vấn DNS không?**  
Không. DNSSEC xác thực tính toàn vẹn/nguồn gốc dữ liệu được ký. DoT/DoH bảo vệ kênh giữa các endpoint tương ứng, không thay thế DNSSEC validation.

**6. Tại sao một vùng chưa ký vẫn có thể phân giải qua validating resolver?**  
Nếu việc vùng chưa được bảo vệ được chứng minh đúng theo chuỗi tin cậy, resolver có thể xem là **insecure** và trả kết quả theo chính sách; không gán nhầm trạng thái secure.

**7. Vì sao không nên flush mọi cache ngay khi thấy IP lạ?**  
Vì có thể làm mất bằng chứng và không sửa được nguồn dữ liệu sai. Trước tiên cần xác minh authoritative view, khoanh vùng cache bị ảnh hưởng, sửa nguyên nhân rồi invalidate có kiểm soát.

**8. Làm thế nào biết client có dùng resolver doanh nghiệp?**  
Đối chiếu DNS server settings, DHCP/VPN, IPv4/IPv6, browser DoH, network flow logs và truy vấn từ đúng client. Không chỉ dựa vào một policy UDP/53.

**9. Nếu DNS trả IP sai nhưng HTTPS báo lỗi chứng chỉ, điều đó chứng minh gì?**  
Nó cho thấy lớp TLS hostname/certificate verification có thể đang ngăn thiết lập kết nối không đáng tin. Vẫn cần xử lý DNS sai; không được tắt kiểm tra TLS.

**10. SERVFAIL xuất hiện hàng loạt sau đổi DNSSEC key có nhất thiết là cache poisoning không?**  
Không. Có thể do DS/DNSKEY hoặc chữ ký bị sai, trust anchor/clock không đúng. Kiểm tra validation logs và quá trình rollover trước khi kết luận.

## 21. Tài liệu tham khảo

- [RFC 3833 — Threat Analysis of the Domain Name System (DNS)](https://www.rfc-editor.org/rfc/rfc3833): phân tích các dạng đe dọa tới DNS.
- [RFC 5452 — Measures for Making DNS More Resilient against Forged Answers](https://www.rfc-editor.org/rfc/rfc5452): kiểm soát tính khớp truy vấn, source-port randomization và giả mạo phản hồi.
- [RFC 4033 — DNS Security Introduction and Requirements](https://www.rfc-editor.org/rfc/rfc4033): khái niệm, mô hình tin cậy và giới hạn DNSSEC.
- [RFC 4034 — Resource Records for DNSSEC](https://www.rfc-editor.org/rfc/rfc4034): DNSKEY, DS, RRSIG và các bản ghi DNSSEC.
- [RFC 4035 — Protocol Modifications for DNSSEC](https://www.rfc-editor.org/rfc/rfc4035): xác minh dữ liệu và xử lý DNSSEC tại resolver.
- [RFC 2308 — Negative Caching of DNS Queries](https://www.rfc-editor.org/rfc/rfc2308): lưu cache cho các kết quả phủ định.
- [RFC 7873 — Domain Name System (DNS) Cookies](https://www.rfc-editor.org/rfc/rfc7873): một cơ chế bổ sung hạn chế spoofing/abuse ở DNS.
- [RFC 7858 — DNS over Transport Layer Security (TLS)](https://www.rfc-editor.org/rfc/rfc7858): bảo vệ kênh DNS bằng TLS.
- [RFC 8484 — DNS Queries over HTTPS (DoH)](https://www.rfc-editor.org/rfc/rfc8484): DNS qua HTTPS và những điểm cần quản trị.
- [NIST SP 800-81-2 — Secure Domain Name System (DNS) Deployment Guide](https://csrc.nist.gov/pubs/sp/800/81/2/final): hướng dẫn triển khai DNS/DNSSEC an toàn.

**Ghi nhớ:** DNS cache poisoning là sự cố **dữ liệu phân giải không đáng tin bị chấp nhận vào cache**, có thể ảnh hưởng hàng loạt người dùng và ứng dụng. Bảo vệ hiệu quả đòi hỏi **resolver được bảo trì, phản hồi được kiểm tra chặt, DNSSEC validation, quản lý đường DNS từ client, kiểm soát thay đổi authoritative zone và giám sát nhiều lớp**. Khi điều tra, hãy xác minh **đúng DNS view và nguồn authoritative**, giữ bằng chứng, sửa **nguồn sai** rồi mới làm sạch cache và xác nhận dịch vụ đã phục hồi.
