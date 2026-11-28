# Split-horizon DNS: phân giải tên theo góc nhìn mạng và ranh giới tin cậy

Giả sử một doanh nghiệp cung cấp cổng thông tin tại tên miền `portal.example.test`. Nhân viên trong mạng công ty cần được chuyển đến địa chỉ riêng của ứng dụng; khách hàng trên Internet phải sử dụng điểm truy cập công khai qua WAF/CDN. Nếu cả hai nhóm đều nhận một địa chỉ DNS giống nhau, doanh nghiệp có thể phải đưa lưu lượng nội bộ vòng ra Internet, hoặc tệ hơn là vô tình công khai địa chỉ/đường vào của dịch vụ chỉ dành cho nhân viên.

**Split-horizon DNS** (còn gọi là *split-view* hoặc *split-brain DNS* trong một số ngữ cảnh) cho phép **cùng một tên miền nhận những câu trả lời DNS khác nhau tùy góc nhìn/nguồn truy vấn và chính sách phân giải**. Kiến trúc này liên quan trực tiếp tới chương **DNS security** của module **SECURITY_NETWORK_SECURITY**: kết hợp kiểm soát ranh giới mạng, firewall, VPN/ZTNA, bảo vệ DNS, IDS/IPS, workload cloud và giám sát để cung cấp khả năng kết nối đúng, hạn chế phơi bày dịch vụ, đồng thời xử lý sự cố một cách có thể kiểm chứng.

Mấu chốt: **DNS giúp client tìm đích nhưng không tự cấp quyền tới đích**. Một đáp án DNS nội bộ bị lộ, bị đoán hoặc được truy vấn bằng cách khác không được phép trở thành con đường truy cập trái quyền vào ứng dụng.

## 1. Hiểu split-horizon qua một ví dụ

### 1.1. Cùng một tên, hai câu trả lời hợp lệ

Giả sử doanh nghiệp dùng tên `portal.example.test`:

| Góc nhìn (view) | Client và resolver | Trả lời A cho `portal.example.test` | Ý định |
|---|---|---|---|
| **Internal** | Máy nhân viên trong mạng được quản lý, dùng DNS nội bộ | `10.20.30.15` | Đến private ingress của cổng nội bộ |
| **External** | Client Internet, hỏi DNS công khai | `203.0.113.80` | Đến edge/WAF công khai |
| **Remote qua VPN** | Máy có VPN và chính sách split DNS đúng | `10.20.30.15` | Truy cập đường riêng khi đã được phép |
| **Guest Wi-Fi** | Khách dùng resolver công khai/guest | `203.0.113.80` | Không nhìn thấy đường phân giải private |

Các tên miền `example.test` và địa chỉ `203.0.113.0/24` ở đây dành cho **tài liệu/lab minh họa**, không phải endpoint thực. Các IP `10.0.0.0/8` là địa chỉ riêng; muốn dùng trong lab phải chọn mạng thực sự do bạn quản lý và tránh trùng các dải hiện hữu.

Nhìn từ phía người dùng:

~~~text
Máy nội bộ:
    portal.example.test  -> 10.20.30.15

Máy bên ngoài:
    portal.example.test  -> 203.0.113.80
~~~

Hai câu trả lời **không bắt buộc** cùng khác nhau về A record. Một kiến trúc có thể khác về AAAA (IPv6), CNAME, SRV, TXT hoặc bản ghi của subdomain khác. Ngược lại, một số tên cần giữ câu trả lời nhất quán giữa các view, ví dụ tên dịch vụ bên ngoài mà nhân viên phải truy cập đúng cùng endpoint.

### 1.2. Split-horizon khác “split tunnel” của VPN

Hai khái niệm thường bị nhầm:

- **Split-horizon DNS:** quyết định **resolver nào trả lời thông tin gì** theo view/namespace/chính sách.
- **Split tunneling:** quyết định **lưu lượng IP nào đi qua VPN và lưu lượng nào đi trực tiếp qua Internet**.
- **Split DNS trong VPN:** client có thể được cấu hình gửi truy vấn tên miền nội bộ tới resolver qua VPN, còn tên miền khác tới resolver bình thường. Đây là một cách triển khai split-horizon, nhưng không đồng nghĩa mọi traffic IP phải đi VPN.

Một máy có VPN split tunnel đúng nhưng gửi DNS về resolver công khai có thể nhận **địa chỉ công khai**; ngược lại, máy nhận địa chỉ private nhưng không có tuyến/VPN/firewall allow tới mạng private sẽ vẫn không kết nối được.

## 2. Cơ chế DNS phía sau các view

### 2.1. Các vai trò khác nhau của DNS

| Thành phần | Nhiệm vụ | Liên hệ tới split-horizon |
|---|---|---|
| **Stub resolver trên client** | Gửi truy vấn DNS từ hệ điều hành/ứng dụng | Chọn DNS server hoặc routing theo suffix, interface, VPN |
| **Recursive resolver** | Phân giải tên qua cache, forwarder hoặc quá trình truy vấn hệ thống DNS | Có thể chọn zone private, forwarding rule hoặc view nội bộ |
| **Authoritative DNS** | Cung cấp câu trả lời có thẩm quyền cho một zone | Có thể có bản dữ liệu public/private riêng hoặc views |
| **Forwarder** | Chuyển một số truy vấn tới upstream DNS khác | Cần cấu hình đúng suffix, đường truyền, recursion và trust boundary |
| **DNS cache** | Giữ kết quả theo TTL và chính sách | Phải tránh trộn đáp án internal/external giữa các nhóm client |

Một triển khai có thể tạo hai bộ **authoritative zone data** riêng, hoặc dùng **DNS view** trên một server; client thường hỏi **recursive resolver**, không trực tiếp hỏi server authoritative. Đường đi sẽ quyết định **nguồn IP nào** mà authoritative DNS nhìn thấy để lựa chọn view.

### 2.2. Luồng nội bộ và bên ngoài

~~~mermaid
flowchart TB
    IN["Máy nội bộ"] --> RI["Recursive resolver nội bộ"]
    EXT["Máy Internet"] --> RE["Recursive resolver công khai"]
    RI --> ZI["Private DNS zone/view"]
    RE --> ZE["Public authoritative DNS"]
    ZI -->|"portal = 10.20.30.15"| PI["Private ingress"]
    ZE -->|"portal = 203.0.113.80"| PE["Public WAF / CDN"]
    PI --> APP["Ứng dụng với AuthN/AuthZ"]
    PE --> APP
~~~

Trong sơ đồ, resolver nội bộ trả đáp án từ vùng riêng và resolver công khai nhận dữ liệu public. Đây là **mô hình tham chiếu**, không phải yêu cầu mọi hệ thống đều phải triển khai hai cụm DNS. Các router, firewall, kết nối VPN, cache và đường hồi đáp được lược bớt.

**Điểm cần suy luận đúng:** nếu DNS authoritative chọn view theo **IP của bên gửi truy vấn trực tiếp**, nó có thể thấy IP của một recursive resolver, forwarder hoặc NAT gateway, **không phải IP người dùng cuối**. Không nên dùng view selection theo source IP như bằng chứng xác thực danh tính người dùng.

### 2.3. Tách namespace so với tách câu trả lời của cùng tên

Có hai mẫu phổ biến:

1. **Cùng một tên, khác đáp án:** `portal.example.test` trỏ tới private ingress trong mạng doanh nghiệp và edge công khai trên Internet.
2. **Zone riêng chỉ phục vụ nội bộ:** `db.corp.example.test` hoặc một subdomain private chỉ có trong hệ thống DNS nội bộ; DNS công khai không cung cấp bản ghi tương ứng.

Mẫu thứ hai có thể giúp giảm sự lẫn lộn khi cần phân biệt rõ public/private. Mẫu thứ nhất có thể giúp một URL giữ nguyên cho nhân viên đang ở văn phòng hoặc bên ngoài, nhưng đặt ra nhiều yêu cầu hơn về cache, DNSSEC, chứng chỉ, VPN, routing và kiểm thử.

## 3. Kiến trúc triển khai split-horizon DNS

### 3.1. Hai hệ thống DNS tách biệt

Một phương án thông dụng là:

- **Public authoritative DNS** đặt ở nhà cung cấp DNS công khai, chỉ xuất dữ liệu được duyệt cho Internet.
- **Internal recursive resolver** được máy doanh nghiệp/VPN sử dụng, sở hữu hoặc chuyển tiếp những zone private cần thiết; các tên khác được phân giải theo quy tắc bình thường.
- **Network firewall và access control** giới hạn ai được hỏi internal DNS, ai được vào private endpoint, và nguồn nào được quản trị các zone.

Ưu điểm: giảm nguy cơ cấu hình nhầm authoritative public và private trên cùng instance. Đánh đổi: cần đồng bộ những bản ghi **được phép giống nhau** giữa hai nguồn và quản trị thay đổi có kiểm chứng.

### 3.2. DNS view trên cùng một phần mềm authoritative

Một số sản phẩm (ví dụ BIND) cho phép tạo nhiều *view*, mỗi view có zone data và chính sách riêng. Server xác định view theo điều kiện hỗ trợ, thường gồm nhóm IP nguồn, interface hoặc tùy chọn khác.

Ưu điểm: một service có thể trả lời khác nhau tùy caller. Rủi ro: **thứ tự lựa chọn view**, cơ chế caching, forwarder chung và ACL sai có thể làm lộ câu trả lời nội bộ hoặc trả kết quả sai.

### 3.3. Cloud private DNS và hybrid forwarding

Các nền tảng cloud thường cung cấp private DNS zone, VPC/VNet-scoped name resolution hoặc resolver endpoint. Hybrid thường dùng conditional forwarder:

~~~mermaid
flowchart LR
    ON["On-prem client"] --> RN["On-prem resolver"]
    RN -->|"corp.example.test"| EP["DNS inbound endpoint trong cloud"]
    EP --> PZ["Private zone / cloud resolver"]
    RN -->|"Tên công khai khác"| PUB["Public DNS resolution"]
    VM["Cloud workload"] --> CR["Cloud resolver"]
    CR --> PZ
    CR --> PUB
    PZ --> IP["Private service endpoint"]
~~~

Mô hình trên yêu cầu **đường mạng giữa on-prem resolver và cloud inbound endpoint**, firewall cho phép DNS, quy tắc chiều đi/về phù hợp và quyền quản trị các zone/endpoint. Nếu mạng hybrid mất kết nối, cần xác định tên nào sẽ không phân giải được và chính sách failover phù hợp.

## 4. Ví dụ BIND 9 với hai view

Ví dụ sau minh họa **cấu trúc**, không phải cấu hình production hoàn chỉnh. Bạn phải điều chỉnh đường dẫn, quyền truy cập, phiên bản BIND, cách server lắng nghe, authoritative records và hạ tầng riêng.

### 4.1. Chọn view dựa trên client được nhìn thấy

~~~conf
// named.conf - phần minh họa cho máy authoritative thử nghiệm.
acl "trusted_dns_clients" {
    10.20.0.0/16;
    192.168.50.0/24;
    localhost;
};

view "internal" {
    match-clients { trusted_dns_clients; };
    recursion no;

    zone "example.test" {
        type primary;
        file "/etc/bind/zones/example.test.internal";
    };
};

view "external" {
    match-clients { any; };
    recursion no;

    zone "example.test" {
        type primary;
        file "/etc/bind/zones/example.test.external";
    };
};
~~~

Giải thích:

- `trusted_dns_clients` chỉ là **ACL theo địa chỉ nguồn mà server nhìn thấy**. Một DNS forwarder dùng chung hoặc NAT có thể khiến nhiều máy được phân loại cùng một view.
- `internal` phải được chọn trước `external` với điều kiện match phù hợp. View `external` dùng `any` ở cuối để bắt những nguồn còn lại.
- `recursion no` minh họa server authoritative không phục vụ recursion cho Internet; **không biến DNS public thành open resolver**. Trong hệ thống thực, tách resolver đệ quy và authoritative thường giúp giảm rủi ro.
- Hai view có thể khai báo **cùng tên zone** nhưng trỏ đến nội dung riêng. Cần kiểm soát quyền đọc file và quyền chỉnh dữ liệu zone.
- `localhost`, `192.168.50.0/24` và `10.20.0.0/16` chỉ là ví dụ. Không đưa mạng khách hoặc dải VPN không tin cậy vào ACL nếu chúng không được phép xem private zone.

Đoạn cấu hình trên **chưa xác định toàn bộ options, listener, log, DNSSEC, zone transfer hay chính sách bảo mật**. BIND có quy tắc riêng về cấu hình views: khi sử dụng views, các zone cần được tổ chức phù hợp trong view và không tùy tiện khai báo zone cùng tên ở phạm vi ngoài view.

### 4.2. Dữ liệu zone ở hai view

Ví dụ file zone internal:

~~~dns
$TTL 300
@ IN SOA ns1.example.test. hostmaster.example.test. (
    2026112801 3600 900 604800 300 )
  IN NS ns1.example.test.
ns1     IN A 10.20.0.53
portal  IN A 10.20.30.15
api     IN A 10.20.30.16
~~~

File zone external:

~~~dns
$TTL 300
@ IN SOA ns1.example.test. hostmaster.example.test. (
    2026112801 3600 900 604800 300 )
  IN NS ns1.example.test.
ns1     IN A 203.0.113.53
portal  IN A 203.0.113.80
api     IN A 203.0.113.81
~~~

Các số serial chỉ để mô phỏng. Khi cập nhật zone, quản lý serial theo quy trình được chọn để secondary nhận biết thay đổi; cấu hình primary/secondary, NOTIFY, transfer ACL/TSIG khi cần và DNSSEC signing thuộc phần triển khai đầy đủ. Các IP public minh họa thuộc dải dành riêng tài liệu, **không sử dụng như địa chỉ hạ tầng thực**.

### 4.3. Vì sao cấu hình đúng cú pháp vẫn có thể sai bảo mật?

| Sai sót | Hậu quả | Kiểm tra |
|---|---|---|
| ACL internal quá rộng | Client ngoài chính sách nhận địa chỉ private | Test truy vấn từ guest/VPN/forwarder và từ bên ngoài |
| Default view ưu tiên sai | Internal client nhận public answer hoặc ngược lại | Xác nhận thứ tự match và source IP server thấy |
| Forwarder chung cho mọi nhóm | Câu trả lời dựa trên IP của forwarder, không theo user | Kiểm tra đường truy vấn thực và chính sách phân biệt resolver |
| Open recursion public | Bị sử dụng trái phép, có nguy cơ lạm dụng DNS | Không phục vụ recursion công khai nếu không có chủ đích và cơ chế bảo vệ |
| Zone transfer không giới hạn | Lộ danh mục hostname hoặc zone data | Hạn chế AXFR/IXFR cho secondary được phép |
| DNSSEC/TTL không đồng nhất | Validation lỗi, kết quả cũ, phân giải không ổn định | Test validating resolver, TTL và cache theo mỗi view |
| Public record tham chiếu private | Client public nhận CNAME tới tên nội bộ không phân giải được | Kiểm tra chuỗi CNAME/AAAA và phụ thuộc DNS |

Ví dụ minh họa không phải chỉ dẫn mở dịch vụ DNS authoritative công khai mà chưa kiểm tra an toàn. Trong production, ưu tiên tính năng quản trị DNS của nền tảng đã có, review cấu hình và change window có rollback.

## 5. Phân giải cho nhân viên từ xa và VPN/ZTNA

### 5.1. Luồng DNS khi bật VPN

~~~mermaid
sequenceDiagram
    participant U as Laptop nhân viên
    participant V as VPN / DNS policy của OS
    participant R as Internal resolver
    participant A as Private application
    U->>V: Truy vấn portal.example.test
    V->>R: Gửi DNS theo suffix và policy được cấp
    R-->>V: A = 10.20.30.15
    V-->>U: Trả private address
    U->>A: Kết nối qua route được phép
    A-->>U: Ứng dụng tự xác thực/ủy quyền
~~~

Để dùng được đường riêng, cần **đồng thời**:

1. Máy có **resolver được phép** dùng private view.
2. DNS policy quyết định đúng truy vấn nào đi resolver nội bộ.
3. Routing/VPN hoặc kênh ZTNA tạo được đường tới private endpoint.
4. Firewall/ACL tại đích cho phép luồng theo danh tính/thiết bị/quy tắc thích hợp.
5. Ứng dụng kiểm tra authentication/authorization và TLS certificate phù hợp hostname.

Máy chỉ “biết IP nội bộ” chưa đáp ứng các điều kiện trên. Split-horizon **không phải một cơ chế cấp quyền VPN**.

### 5.2. Những lỗi thường gặp trên thiết bị người dùng

- VPN cấp đúng DNS server nhưng hệ điều hành ưu tiên resolver của interface khác hoặc dùng suffix search không như mong đợi.
- Browser/app sử dụng DNS over HTTPS (DoH), DNS over TLS (DoT) hoặc resolver riêng, không đi theo split DNS của OS.
- Máy truy vấn được private IP nhưng thiếu route, firewall rule hoặc ACL ở kênh truy cập.
- Kết quả public/private vẫn nằm trong cache khi người dùng bật/tắt VPN.
- Client sử dụng IPv6 public AAAA trong khi A private trỏ đúng; ứng dụng ưu tiên IPv6 theo hành vi kết nối.
- Policy chỉ xử lý FQDN một cách chính xác, nhưng app gọi tên khác, tên ngắn hoặc CNAME chain ngoài phạm vi suffix.

Đừng giải quyết bằng cách buộc toàn bộ thiết bị tắt bảo vệ DNS mã hóa mà không có thiết kế được phê duyệt. Trong môi trường doanh nghiệp, nên quản lý resolver/DoH/DoT theo khả năng hệ điều hành, chính sách endpoint và mô hình quyền riêng tư.

### 5.3. VPN có thể là một phần của ranh giới, không phải tất cả

Mạng VPN có thể gồm nhân viên, nhà thầu và thiết bị quản lý với mức tin cậy khác nhau. Gộp mọi địa chỉ VPN vào một DNS view nội bộ rất rộng có thể phơi bày những tên host không phù hợp. Có thể cần **nhiều view**, DNS policy theo nhóm hoặc zone tách biệt, kết hợp quyền tại ứng dụng và phân đoạn mạng.

## 6. DNSSEC và split-horizon

**DNSSEC** dùng chữ ký và chuỗi tin cậy để giúp resolver xác minh tính xác thực/toàn vẹn dữ liệu DNS trong phạm vi được ký. Nó **không mã hóa truy vấn** và không cung cấp cơ chế phân quyền người dùng.

Trong split-horizon, nếu cùng tên miền có **bản public được ký DNSSEC**, còn bản private là dữ liệu nội bộ khác, cần thiết kế cách resolver xác minh dữ liệu riêng một cách nhất quán.

### 6.1. Tại sao có thể xuất hiện SERVFAIL?

Giả sử zone public `example.test` có DNSSEC chain được resolver công khai tin cậy. Resolver nội bộ lại được hướng tới một bản private `example.test` chưa ký hoặc ký bằng bộ khóa không tương thích với kỳ vọng validation. Tùy mô hình phân giải và cấu hình trust, validating resolver có thể coi kết quả là **bogus** và trả `SERVFAIL` thay vì dữ liệu private.

Điểm cần nhớ:

- Việc server nội bộ trả `NOERROR` khi hỏi trực tiếp **không chứng minh** validating recursive resolver sẽ chấp nhận câu trả lời.
- Mỗi view có thể cần chính sách ký và chuỗi tin cậy phù hợp, hoặc sử dụng cơ chế private trust/validation có chủ đích theo sản phẩm.
- Không tắt DNSSEC validation toàn hệ thống chỉ để chữa một private zone cấu hình sai; điều này ảnh hưởng bảo vệ của những tên công khai khác.
- Phản hồi phủ định (`NXDOMAIN`, `NODATA`) cũng có thể liên quan DNSSEC proof, cache và câu trả lời khác nhau giữa view.

Nếu chọn subdomain riêng cho private DNS, vẫn phải đánh giá vấn đề **delegation và DNSSEC của parent zone**. Một namespace nội bộ chưa công bố trên Internet có thể có chính sách tin cậy khác với zone public đã ký.

### 6.2. Kiểm tra DNSSEC đúng điểm

Có thể dùng `dig +dnssec` để yêu cầu hiển thị dữ liệu DNSSEC liên quan khi có; nhưng chỉ nhìn thấy `RRSIG` hay cờ `AD` **chưa đủ chẩn đoán mọi vấn đề**. Phải biết resolver có validation thực, nhận trust anchor nào và nhận answer qua forwarding/override nào. Công cụ validating như `delv` (nếu môi trường có) hoặc log của recursive resolver có thể hỗ trợ.

Tránh dùng kết quả `dig +trace` như bằng chứng duy nhất cho split DNS: chế độ trace hỏi theo đường DNS delegation công khai có thể **bỏ qua routing view của recursive resolver nội bộ** mà người dùng thật sử dụng.

## 7. Cache, TTL và phản hồi phủ định

Một record có TTL 300 giây không có nghĩa mọi client đều thấy thay đổi ngay sau đúng 300 giây. Còn có OS/browser cache, recursive resolver cache, forwarder, các giới hạn TTL của sản phẩm và **negative caching** cho câu trả lời không tồn tại.

### 7.1. Lỗi do cache trộn view

Trong thiết kế kém, một recursive resolver có thể hỏi public zone và cache public IP; sau đó client nội bộ dùng cùng cache bị trả lại public IP dù mong muốn private IP. Ngược lại, public client không được nhận private IP từ cache chứa dữ liệu nội bộ.

Giải pháp là đảm bảo **cơ chế phân chia cache/chính sách resolver theo view** hoặc định tuyến truy vấn tới đúng nguồn dữ liệu. Không trông chờ DNS TTL tự tạo ranh giới tin cậy. Nếu thực hiện migration, cần kiểm tra cả cache path trước và sau thay đổi.

### 7.2. TTL phải cân bằng gì?

| TTL/ngữ cảnh | Lợi ích tiềm năng | Đánh đổi |
|---|---|---|
| TTL ngắn | Đáp án có thể thay đổi nhanh hơn khi cutover | Tăng truy vấn, phụ thuộc resolver/authoritative nhiều hơn |
| TTL dài | Giảm tải DNS, ổn định cache | Thay đổi view/IP chậm được nhận biết |
| TTL phủ định | Giảm truy vấn lặp đến tên không tồn tại | Khi mới tạo record, client có thể vẫn thấy NXDOMAIN/NODATA |
| Tạm giảm TTL trước migration | Có thể giảm thời gian tồn tại của answer cũ | Cần thực hiện đủ sớm để TTL cũ hết và vẫn không đảm bảo mọi client |

Khi kiểm thử, phải phân biệt **truy vấn trực tiếp authoritative** với **truy vấn qua recursive resolver thực tế của client**. Chúng có thể cho kết quả khác nhau nếu cache còn dữ liệu cũ.

## 8. Cloud, Kubernetes và thiết bị hybrid

### 8.1. Các mô hình cloud phổ biến

| Nền tảng | Cơ chế có thể dùng | Điểm cần kiểm tra |
|---|---|---|
| **AWS** | Route 53 public/private hosted zones, VPC resolver, Resolver inbound/outbound endpoints và forwarding rules | Zone gắn VPC nào, tên trùng public/private, quyền IAM, hybrid forwarding, resolver precedence |
| **Azure** | Public DNS, Azure Private DNS zones, VNet links, Azure DNS Private Resolver hoặc DNS forwarder phù hợp | VNet nào được liên kết, tên private endpoint, hybrid conditional forwarding, quyền RBAC |
| **Google Cloud** | Cloud DNS public/private zones, DNS policies, forwarding/peering và VPC-scoped name resolution | Zone visibility theo VPC, rule precedence, điều kiện cloud/on-prem, quyền IAM |
| **On-prem** | BIND views, Windows DNS policies/zones, forwarder và resolver riêng | ACL, thứ tự policy, replication, transfer, cache và routing tới DNS |

Đây là **bản đồ khái niệm**, không phải khẳng định mọi dịch vụ đều có cùng cách ưu tiên zone, resolver hoặc DNSSEC. Cần xem tài liệu và phiên bản thực tế của nền tảng khi triển khai; nhất là với **private endpoint**, DNS record có thể được nền tảng tạo/cập nhật tự động.

**Lỗi đáng chú ý:** liên kết private zone vào một VPC/VNet không mong muốn có thể khiến workload mới nhận private IP hoặc làm hỏng phân giải public. Ngược lại, quên liên kết zone/forwarder khiến workload đúng quyền nhận `NXDOMAIN` hoặc public IP.

### 8.2. Kubernetes: service discovery không tự bằng split public/private

Trong Kubernetes, CoreDNS thường phục vụ tên của Service trong cluster theo namespace/cluster domain. Đây là **service discovery nội bộ**, không tự động là split-horizon cho cùng domain public.

Một kiến trúc có thể:

- Dùng tên `service.namespace.svc.cluster.local` (với cluster domain phù hợp) cho service nội bộ.
- Forward những zone private cần thiết từ CoreDNS tới resolver tổ chức/cloud, nếu được thiết kế.
- Dùng public DNS cho các dịch vụ Internet bên ngoài.
- Giới hạn egress DNS, RBAC, quyền sửa ConfigMap/CoreDNS và private zone; kiểm thử ảnh hưởng khi scale.

Kubernetes NetworkPolicy chỉ có tác dụng khi CNI hỗ trợ enforcement, và không phải công cụ mặc định để cấp quyền đọc dữ liệu DNS. Không để mọi Pod tùy ý thay đổi CoreDNS configuration, private zone hoặc kết nối trực tiếp tới các resolver không được phê duyệt nếu chính sách yêu cầu kiểm soát DNS.

### 8.3. IPv6 và multi-homed clients

Nhiều hệ thống chỉ chia A record nhưng quên AAAA. Kết quả: client ở trong mạng vẫn có thể kết nối qua địa chỉ IPv6 public (hoặc không có route IPv6 phù hợp), dù A record trả private IPv4.

Checklist riêng cho IPv6:

1. Câu trả lời `AAAA` có giống ý định security zone hay không?
2. Có IPv6 firewall/route/VPN đúng với cách ứng dụng kết nối không?
3. Các tên `CNAME` có dẫn đến đích khác view không?
4. Client có dùng nhiều interface, DNS server hoặc resolver kết hợp không?
5. Khi IPv6 lỗi, client chuyển sang IPv4 theo cách nào; độ trễ tăng bao nhiêu?

## 9. Phân tích threat model cho split-horizon DNS

### 9.1. Tài sản và ranh giới

Các tài sản cần bảo vệ gồm: danh mục hostname private, địa chỉ backend, đường quản trị DNS, tài khoản/khóa cập nhật zone, cấu hình resolver, cache, lưu lượng DNS và khả năng truy cập ứng dụng.

Các ranh giới:

- **Public Internet ↔ authoritative public DNS:** phải chỉ trả dữ liệu được phép công khai và không phục vụ open recursion.
- **Mạng nội bộ/VPN ↔ private resolver:** cần kiểm soát nguồn truy cập, quyền quản lý và xử lý forwarder.
- **Private resolver ↔ cloud/private zone:** cần đường truyền, quyền cập nhật zone, trust/validation và quan sát lỗi.
- **DNS answer ↔ application connection:** đích IP phải tiếp tục được bảo vệ bằng mạng, TLS, identity và authorization.
- **Control plane ↔ DNS records:** chỉ những vai trò được duyệt mới có quyền thay record/zone/routing policy.

### 9.2. Bảng rủi ro

| ID | Rủi ro | Kịch bản | Biện pháp kiểm soát |
|---|---|---|---|
| D01 | **Private record disclosure** | Guest hoặc Internet nhận private A/AAAA từ view sai | ACL, resolver tách biệt, test negative từ bên ngoài |
| D02 | **Wrong view via forwarder** | Authoritative chỉ thấy IP forwarder dùng chung | Chọn kiến trúc resolver phù hợp, phân biệt nguồn/chính sách từ đầu |
| D03 | **Cache contamination** | Private/public answer bị trộn trong cache dùng chung | Tách cache/view đúng cơ chế của resolver, test cutover |
| D04 | **DNS bypass** | Client dùng DoH/DoT riêng và bỏ split DNS | Quản trị resolver/client policy, bảo vệ dịch vụ đích độc lập |
| D05 | **Open recursion** | DNS công khai trở thành resolver không giới hạn | Tắt recursion ở authoritative public hoặc giới hạn ACL chặt |
| D06 | **Zone transfer leakage** | Bên không được phép lấy được danh mục zone | Restrict AXFR/IXFR, bảo vệ TSIG/secondary |
| D07 | **DNSSEC validation failure** | Private answer mâu thuẫn chuỗi tin cậy public | Kiểm tra trust/validation theo view, không tắt DNSSEC toàn cục |
| D08 | **Stale/negative cache** | VPN vừa bật nhưng client vẫn thấy public IP/NXDOMAIN | TTL/negative caching, test OS/browser/recursive caches |
| D09 | **IPv6 mismatch** | AAAA công khai trong khi A riêng | Kiểm tra A/AAAA, firewall IPv6 và client address selection |
| D10 | **Unauthorized DNS change** | Nhân viên sửa private zone hoặc trỏ login sang endpoint khác | IAM/RBAC, MFA, audit, phê duyệt, record diff |
| D11 | **Direct access despite DNS hiding** | Người ngoài biết IP private qua đường VPN hoặc public bypass | Network segmentation, ZTNA, firewall, mTLS/AuthZ |
| D12 | **Dependency outage** | Hybrid DNS endpoint hoặc resolver bị lỗi | HA, giám sát, runbook và đánh giá failover |
| D13 | **Sensitive query logging** | Log chứa host nội bộ, người dùng hoặc token nằm trong query | Redaction, least privilege, retention hợp lý |
| D14 | **Misrouting for tenant** | Private zone liên kết nhầm VPC/VNet/tenant | Scope zone/links theo tenant, xét quyền cloud, test chéo tenant |

**Đặc biệt:** split-horizon không phải phương pháp *security through obscurity* đủ để bảo vệ secret. Hostname private và địa chỉ máy có thể bị suy ra từ log, email, certificate transparency khi cấp chứng chỉ công khai, mã nguồn, dữ liệu browser hoặc các nguồn khác. Bảo vệ hệ thống bằng phân đoạn và quyền thực thi độc lập với câu trả lời DNS.

## 10. Kiểm tra bằng các lệnh chỉ đọc

Chỉ chạy các lệnh dưới đây trên **resolver/hạ tầng được phép kiểm tra**. Trong ví dụ, `10.20.0.53` là internal DNS giả định; `203.0.113.53` là địa chỉ tài liệu, **không phải DNS server thực tế đang hoạt động**.

### 10.1. Dùng `dig` trên Linux/macOS

~~~bash
# Kiểm tra đáp án từ internal resolver trong lab hoặc mạng được ủy quyền.
dig @10.20.0.53 portal.example.test A +noall +answer
dig @10.20.0.53 portal.example.test AAAA +noall +answer
dig @10.20.0.53 portal.example.test CNAME +noall +answer

# Truy vấn tên trong ví dụ có yêu cầu dữ liệu DNSSEC nếu server hỗ trợ.
dig @10.20.0.53 portal.example.test A +dnssec
~~~

Lệnh không tự tạo record hoặc thay cấu hình DNS. Trường hợp chỉ được phép dùng một server khác, thay IP bằng resolver **thực tế được cấp quyền**; đừng giả định `10.20.0.53` tồn tại trong môi trường của bạn.

**Không kết luận view đúng chỉ vì dùng `@` trỏ tới DNS server mong muốn.** DNS server có thể nhận diện view dựa vào IP nguồn thực tế của máy hỏi/forwarder. Kiểm tra phải được thực hiện từ **những mạng nguồn khác nhau** và qua resolver mà client nghiệp vụ thực sự dùng.

### 10.2. Dùng PowerShell trên Windows

~~~powershell
# Chỉ đọc cấu hình DNS resolver đã gắn với các interface.
Get-DnsClientServerAddress

# Chỉ đọc chính sách DNS cho tên cụ thể (nếu server được phép truy vấn).
Resolve-DnsName -Name "portal.example.test" -Type A -Server "10.20.0.53"
Resolve-DnsName -Name "portal.example.test" -Type AAAA -Server "10.20.0.53"
~~~

Nếu `Resolve-DnsName` báo lỗi, cần phân biệt tên không tồn tại, resolver không thể truy cập, DNSSEC validation, timeout, policy hoặc firewall. Không thay đổi DNS server của toàn máy để thử trên môi trường doanh nghiệp nếu chưa được phê duyệt.

### 10.3. Ma trận kiểm thử bắt buộc

| Điểm thử | Query | Kết quả kỳ vọng theo ví dụ | Điều kiện cần xác minh thêm |
|---|---|---|---|
| Laptop trong mạng nhân viên | `portal.example.test A` | `10.20.30.15` | Route và TLS/AuthZ tới private ingress |
| Laptop ở Internet, không VPN | Cùng tên, resolver public | `203.0.113.80` | Không nhận private record, edge hoạt động |
| Laptop từ xa **có VPN** | Cùng tên qua DNS policy VPN | `10.20.30.15` | Split DNS suffix/route/firewall chính xác |
| Guest Wi-Fi | Cùng tên qua resolver guest | `203.0.113.80` | Guest không lấy private answer |
| VM cloud liên kết private zone | Cùng tên qua cloud resolver | `10.20.30.15` hoặc IP private được thiết kế | Zone link, quyền cloud, private connectivity |
| Cloud VM **không** liên kết zone | Cùng tên qua resolver của VM | Public answer theo kiến trúc | Không rò record private do link sai |
| Client IPv6 | `AAAA` + kiểm tra kết nối | Theo chính sách IPv6 đã thiết kế | Không bypass qua AAAA không kiểm soát |
| Client bật DoH riêng | Cùng tên với resolver khác | Có thể nhận view khác | Chính sách DNS endpoint và authz vẫn an toàn |
| Sau đổi record | A/AAAA, cả positive/negative query | Kết quả mới sau thời gian cache hợp lý | Không có stale cache và không gặp SERVFAIL |
| Validating resolver | `A +dnssec` và log validation | Kết quả không bị coi bogus | Trust chain/override đúng mô hình |

**Không dùng ping thành công** để suy kết luận rằng split DNS và chính sách truy cập đã đúng: một host có thể không trả ICMP nhưng HTTPS vẫn hoạt động, hoặc ngược lại. Cần kiểm thử **DNS answer, route, TCP/TLS và quyền ứng dụng** theo từng bước.

### 10.4. Cách phân biệt lỗi theo triệu chứng

| Triệu chứng | Giả thuyết cần thử | Nguồn kiểm chứng |
|---|---|---|
| Mạng nội bộ nhận public IP | Resolver sai, view sai, forwarder chung, cache cũ | Client DNS settings, DNS query log, view match, TTL |
| Internet nhận private IP | ACL public/private nhầm, cache/shared forwarder lộ | Truy vấn từ mạng ngoài, authoritative/recursive logs |
| `NXDOMAIN` cho tên mới | Chưa có record trong view, negative cache, sai suffix | SOA/authority, zone data, cached negative response |
| `SERVFAIL` chỉ với resolver xác thực | DNSSEC hoặc forwarding/delegation lỗi | Validation log, chain/trust, reachability |
| Có private IP nhưng app timeout | VPN route/firewall/ACL/TLS hoặc origin không hoạt động | Route table, firewall logs, TCP/TLS/application logs |
| Bật VPN xong vẫn thấy public | OS/browser DoH, cache, per-interface priority, NRPT/split DNS policy | Resolver selection và query path trên client |
| A đúng nhưng app đi public | AAAA được ưu tiên hoặc ứng dụng có cache riêng | A/AAAA, IPv6 routing, client connection logs |
| Chỉ cloud workload lỗi | Private zone link, resolver rule hoặc hybrid endpoint | Cloud DNS zone associations, forwarding và firewall |

## 11. Giám sát và vận hành

### 11.1. Telemetry tối thiểu

Các thông tin hữu ích cho DNS resolution (nếu giải pháp hỗ trợ) gồm:

- Timestamp có timezone, DNS server/resolver instance và view/policy được chọn.
- Tên zone hoặc **QNAME theo mức độ chi tiết phù hợp với quyền riêng tư**, QTYPE (A, AAAA, CNAME...), RCODE.
- Source network/forwarder đã được xác minh; lưu ý resolver có thể không biết user cuối.
- Thời gian phản hồi, timeout, SERVFAIL, NXDOMAIN/NODATA, cache hit/miss nếu có.
- Zone version/serial, thay đổi record, người phê duyệt, private zone association và audit cấu hình.
- Các sự kiện DNSSEC validation, forwarding error, health của VPN/private resolver/endpoint.

DNS query logs có thể chứa hostname nội bộ, thông tin nhân sự, nội dung dịch vụ và thậm chí dữ liệu nhạy cảm bị đưa nhầm vào subdomain. Áp **least privilege, giới hạn retention, lọc/redact và quy trình truy cập audit**.

### 11.2. Cảnh báo và baseline

| Chỉ số | Dấu hiệu đáng điều tra |
|---|---|
| **Sai view** | External client nhận private answer hoặc internal nhận public ngoài chủ đích |
| **Availability** | SERVFAIL, timeout và latency tăng tại private resolver |
| **Validation** | DNSSEC bogus tăng đột ngột sau thay zone/forwarding |
| **Routing** | On-prem ↔ cloud DNS endpoint bị ngắt hoặc VPN DNS rule không còn hiệu lực |
| **Change drift** | Zone bị cập nhật ngoài pipeline, bản ghi internal/public không đúng thiết kế |
| **Cache** | Số lượng client gặp đáp án cũ tăng sau migration |
| **Security** | Query bất thường tới tên nội bộ, AXFR trái phép, open recursion exposure |

Không đánh đồng **lượng query lớn** với tấn công DNS. Một đợt deploy, thay TTL, cache miss, ứng dụng lỗi retry hoặc user tăng theo giờ cao điểm đều có thể làm tăng QPS. Phân tích cùng logs của resolver, firewall, IDS/IPS và ứng dụng.

## 12. Quy trình thiết kế và triển khai

### Bước 1 — Kiểm kê tên miền và owner

Xác định domain/zone, record A/AAAA/CNAME/SRV/TXT cần giữ public hay private, hostname chỉ phục vụ quản trị, phụ thuộc certificate/TLS, nguồn cập nhật và người chịu trách nhiệm. Lập danh sách những tên **phải có cùng nội dung ở mọi view** để tránh drift.

### Bước 2 — Xác định ranh giới client và resolver

Phân loại nhân viên, VPN, nhà thầu, guest, cloud workload, container và đối tác; với mỗi nhóm, ghi rõ DNS server nào nhận query, server nhìn thấy địa chỉ nguồn nào, firewall/route nào bảo vệ kết nối và có proxy/forwarder trung gian không.

### Bước 3 — Chọn mô hình zone/view

Quyết định authoritative DNS tách biệt hay nhiều views, private zone trong cloud, conditional forwarding hybrid và cơ chế cache. Chọn cách quản trị rõ quyền và dễ kiểm chứng; không coi “dùng một DNS server cho mọi người” là kiến trúc đơn giản hơn nếu tạo rủi ro trộn view.

### Bước 4 — Bảo vệ control plane

Giới hạn quyền cập nhật DNS, zone transfers, tài khoản cloud/IAM, secret/TSIG và cấu hình resolver. Tách quyền của đội ứng dụng khỏi quyền sửa zone public/private nhạy cảm khi cần. Sử dụng thay đổi có review, versioning, kiểm tra record diff và kế hoạch rollback.

### Bước 5 — Kiểm thử theo ma trận nhiều điểm nhìn

Thử từ internal, public, guest, VPN, cloud và client có IPv6/DoH trong phạm vi được phép. Kiểm tra cả DNSSEC validation, positive/negative caching, CNAME chain, TLS hostname, routing và app authorization. Nhìn một câu trả lời `dig` trên máy quản trị là chưa đủ.

### Bước 6 — Triển khai từng phần và theo dõi

Giảm TTL trước migration nếu cần và đủ sớm; triển khai private resolver/zone association và mạng trước, sau đó chuyển client theo nhóm. Theo dõi NXDOMAIN/SERVFAIL, tỷ lệ chọn view đúng, lỗi ứng dụng, timeout, DNS query load và TLS. Không xóa bản ghi dự phòng trước khi biết vòng đời cache của các client.

### Bước 7 — Duy trì và diễn tập sự cố

Kiểm tra định kỳ quyền DNS, public record diff, health resolver, mất kết nối hybrid, thay VPN, đổi certificate, bổ sung cloud VPC/VNet/tenant và phân phối IPv6. Chuẩn bị quy trình phục hồi zone data/forwarder và kế hoạch chuyển lại đường cũ có đánh giá an toàn.

## 13. Bài tập tình huống: cổng ứng dụng của công ty

**Bối cảnh:** Doanh nghiệp dùng `portal.example.test` để phục vụ khách hàng Internet và nhân viên nội bộ. Public DNS trả `203.0.113.80` tới WAF, private DNS trả `10.20.30.15` tới ingress trong VPC. Văn phòng dùng DNS on-prem, nhân viên từ xa dùng VPN, VM trong VPC sử dụng cloud private zone. Một nhóm khách dùng guest Wi-Fi; một số nhân viên bật DoH riêng trong browser.

Sau đợt triển khai, đội vận hành nhận báo cáo:

1. Nhân viên trong văn phòng nhận public IP dù DNS trên client nhìn có vẻ đúng.
2. Nhân viên bật VPN nhưng browser vẫn truy cập đường WAF công khai.
3. VM ở VPC mới nhận `NXDOMAIN`.
4. Thi thoảng dịch vụ báo `SERVFAIL` chỉ ở validating resolver.
5. Nhóm khách guest nhận được private IP sau khi DNS server thay đổi.

Hãy phân tích:

- Những thành phần nào có thể chọn sai view hoặc cache sai record?
- Tại sao có private IP không đồng nghĩa guest có quyền truy cập ứng dụng?
- Làm thế nào kiểm tra VPC association, conditional forwarding, DNSSEC và A/AAAA mà không sửa production?
- Những kiểm thử âm/dương nào cần thiết trước khi đổi cấu hình?
- Nếu phải rollback, cần chú ý cache và độ trễ lan truyền thay đổi như thế nào?

**Gợi ý đối chiếu:**

- **Văn phòng:** xem resolver/forwarder upstream, IP nguồn mà authoritative thấy, thứ tự match view, cache và TTL. Một forwarder chung có thể làm cả nhóm được xếp cùng view.
- **VPN + DoH:** browser có thể dùng resolver riêng; so sánh DNS path của OS và browser, kiểm tra route/firewall/tính hợp lệ của split DNS policy. Không khuyến nghị chỉ tắt bảo vệ DNS mà bỏ qua thiết kế endpoint.
- **VPC mới:** kiểm tra zone association, resolver precedence, private endpoint/forwarding và IAM; record tồn tại ở VPC cũ không có nghĩa tự visible tại VPC mới.
- **SERVFAIL:** xác minh chuỗi DNSSEC, trust/validation ở resolver, nội dung private view và chính sách forwarder; không vội vô hiệu hóa toàn bộ DNSSEC.
- **Guest nhận private IP:** kiểm tra sai ACL, recursion/forwarding hoặc cache contamination; chặn rò đáp án. Độc lập với đó, private ingress vẫn cần firewall/identity/AuthZ chặn truy cập trái phép.
- **Rollback:** lưu zone/config diff, cấu hình resolver và TTL trước-sau, theo dõi negative caching, chuẩn bị trả về đường cũ nhưng không mở allow-all hoặc cho client guest dùng nội bộ.

## 14. Checklist review split-horizon DNS

- [ ] Đã phân biệt DNS view, VPN split tunnel, public/private zones và các quyền truy cập mạng.
- [ ] Có danh sách record phải khác/giống giữa internal và external, với owner rõ ràng.
- [ ] Biết DNS server nào nhận query và địa chỉ nguồn nào được dùng để chọn view.
- [ ] Internal DNS không cho phép nguồn ngoài chính sách lấy record private; public authoritative không trở thành open resolver.
- [ ] Quyền zone transfer, update, IAM/RBAC, secret và DNS policy đã được giới hạn.
- [ ] Conditional forwarding, VPC/VNet links và đường hybrid/VPN đã được kiểm tra theo từng nhóm client.
- [ ] Đảm bảo cache hoặc resolver policy không trộn đáp án private/public giữa các góc nhìn.
- [ ] Đã kiểm thử DNSSEC validation theo cả private/public view; không tắt validation toàn hệ thống làm biện pháp mặc định.
- [ ] Xét TTL, negative caching, client/browser caches và kế hoạch cutover/rollback.
- [ ] Đã kiểm tra A, AAAA, CNAME chain và đường IPv6/VPN tương ứng.
- [ ] Có chính sách cho client sử dụng DoH/DoT, DNS của browser/app hoặc nhiều interface.
- [ ] Kiểm thử từ mạng nội bộ, Internet, guest, VPN, cloud, container và tenant khác nếu liên quan.
- [ ] Có network firewall/segmentation, TLS và application authorization độc lập với DNS answer.
- [ ] Log/audit có timezone, resolver/view/RCODE và thay đổi cấu hình; bảo vệ quyền riêng tư dữ liệu truy vấn.
- [ ] Có giám sát SERVFAIL/NXDOMAIN, resolver health, DNSSEC, zone drift và sự cố hybrid.
- [ ] Thay đổi có owner, phê duyệt, kiểm thử, rollback và lịch rà soát khi topology thay đổi.

**Ghi nhớ:** **Split-horizon DNS là khả năng cung cấp câu trả lời DNS theo góc nhìn được thiết kế, không phải cơ chế xác thực hay ẩn dịch vụ đủ để thay thế kiểm soát truy cập**. Triển khai đúng đòi hỏi hiểu *ai đang hỏi, resolver nào thật sự nhận query, view nào được chọn, cache và DNSSEC hoạt động ra sao*, sau đó bảo vệ đường mạng và ứng dụng bằng các lớp phòng vệ độc lập.
