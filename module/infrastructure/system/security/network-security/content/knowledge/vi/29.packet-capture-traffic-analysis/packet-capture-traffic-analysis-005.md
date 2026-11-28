# Phân tích DNS packet: giải mã bản tin và điều tra lưu lượng mạng

**Phân tích DNS packet** là quá trình quan sát và giải mã các bản tin Domain Name System (DNS) để biết client hỏi tên gì, resolver hoặc authoritative server trả lời thế nào, độ trễ bao nhiêu, lỗi phát sinh ở đâu và tín hiệu nào cần điều tra thêm. Vì DNS thường diễn ra trước khi ứng dụng kết nối API, CDN, SaaS và dịch vụ nội bộ, lỗi DNS có thể trông giống lỗi firewall, VPN, TLS hoặc ứng dụng; lưu lượng DNS lạ có thể là tín hiệu liên quan C2, reconnaissance hoặc thất thoát dữ liệu.

Bài thuộc chương **Packet capture và phân tích lưu lượng**, module **SECURITY_NETWORK_SECURITY**. Kiến thức góp phần vào khả năng phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, hạ tầng cloud và xây dựng kiến trúc mạng an toàn theo hướng **quan sát được và kiểm chứng được**.

**Giới hạn:** DNS packet không nói toàn bộ nội dung phiên TLS, không tự chứng minh một domain được kết nối sau khi phân giải, và không luôn nhìn thấy hoạt động DNS khi client sử dụng cache hay DNS mã hóa. Các tên thuộc miền .example và địa chỉ thuộc dải tài liệu chỉ minh họa, không phải kết quả đo thật. Chỉ thực hành trên PCAP hoặc mạng lab được cấp phép; không thu lưu lượng của người khác và không chia sẻ PCAP chứa dữ liệu nhạy cảm.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt client stub, recursive resolver, authoritative server, cache, query và response.
2. Xác định DNS payload trong Ethernet/IPv4/IPv6/UDP/TCP và biết khi nào dữ liệu bị mã hóa.
3. Đọc **DNS header 12 byte**, transaction ID, flags và section counts.
4. Hiểu Question, Answer, Authority, Additional; QNAME/QTYPE/QCLASS; RR NAME/TYPE/CLASS/TTL/RDLENGTH/RDATA.
5. Nhận dạng name compression pointers, A/AAAA, CNAME, NS, SOA, MX, TXT, PTR, SRV, SVCB/HTTPS và record DNSSEC.
6. Ghép query/response, tính thời gian quan sát, phân biệt retry, timeout, NXDOMAIN, NOERROR/NODATA và SERVFAIL.
7. Phân tích EDNS(0), OPT pseudo-RR, UDP size, TC bit/TCP fallback và fragment.
8. Hiểu điều DNSSEC flags/records có thể chứng minh và không chứng minh.
9. Sử dụng Wireshark, tcpdump và TShark trong phạm vi lab, phân biệt capture filter với display filter.
10. Xác định giới hạn quan sát đối với DNS-over-TLS (DoT), DNS-over-HTTPS (DoH), DNS-over-QUIC (DoQ).
11. Correlate DNS với flow logs, firewall, IDS/IPS, proxy, endpoint và cloud audit theo provenance.
12. Xây ma trận kiểm thử, dashboard, checklist và runbook điều tra sự cố DNS.

## 2. DNS hoạt động trên những điểm nào?

Trong tình huống ứng dụng truy cập api.orders.example, nó có thể hỏi bản ghi A/AAAA, nhận nhiều IP, alias CNAME hoặc một lỗi. Resolver có thể dùng cache, hỏi forwarder hoặc thực hiện iterative resolution qua hệ thống phân cấp DNS.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant R as Recursive Resolver
    participant C as Cache
    participant NS as Authoritative DNS
    A->>R: Query A api.orders.example
    R->>C: Lookup cache
    alt Cache hit hợp lệ
      C-->>R: RRset còn hạn
    else Cache miss
      R->>NS: Resolution steps (được giản lược)
      NS-->>R: Answer / negative / referral
      R->>C: Cache theo policy
    end
    R-->>A: DNS response
    A->>A: Thực hiện kết nối riêng nếu hợp lệ
~~~

**Capture tại client→resolver không mặc định nhìn thấy các truy vấn resolver→authoritative.** Ngược lại, packet ở đường upstream có thể cho thấy IP của forwarder chứ không phải ứng dụng gốc. Một response trả DNS success không bảo đảm TCP/TLS kết nối tới địa chỉ sau đó sẽ thành công.

### 2.1. Bảng bằng chứng

| Câu hỏi | DNS packet có thể cho biết | Chưa thể kết luận |
|---|---|---|
| Client hỏi tên gì? | QNAME/QTYPE khi plaintext | Ai là end-user khi có NAT/cache |
| Server trả gì? | Answer RRs, RCODE, TTL | Ứng dụng đã dùng record nào |
| Phản hồi chậm? | Query–response time delta tại sensor | Toàn bộ ứng dụng chậm do DNS |
| Domain có đáng tin? | DNSSEC data/flags hiện diện | Đã được validate nếu chưa có trust evidence |
| Không thấy query? | Không có packet trong capture | Không có DNS vì cache/DoH/đường khác |
| Có NXDOMAIN? | RCODE=3 tại observation point | Tên không tồn tại ở mọi split-horizon view |

## 3. DNS trong các lớp giao vận

DNS truyền thống thường chạy **UDP/53**, đồng thời sử dụng **TCP/53** trong các trường hợp phù hợp. Port không tự là bằng chứng packet hợp lệ hoặc chỉ có DNS.

### 3.1. DNS qua UDP

~~~text
Link-layer header (Ethernet/VLAN hoặc kiểu link khác)
  -> IPv4/IPv6 header
  -> UDP header (source/destination port, length, checksum)
  -> DNS message:
       12-byte header
       Question section
       Answer section
       Authority section
       Additional section
~~~

Tại container veth, loopback, VPN tunnel hoặc cloud capture, dữ liệu link-layer có thể khác Ethernet. IPv4 options, IPv6 extension headers và VLAN tags thay đổi offset; **không tính offset cố định từ đầu frame** để giải mã DNS.

### 3.2. DNS qua TCP

~~~text
TCP byte stream:
    [2-byte DNS message length, network order]
    [DNS message có đúng số byte được khai báo]
    [có thể tiếp nối một length-prefixed DNS message khác]
~~~

**TCP có thể chia nhỏ một DNS message qua nhiều segments** hoặc chứa nhiều messages trong một stream. Wireshark/TShark cần stream reassembly phù hợp; một TCP packet không nhất thiết là một DNS message hoàn chỉnh.

### 3.3. Những cổng thường gặp

| Giao vận | Cổng thông dụng | Khả năng nhìn plaintext DNS |
|---|---|---|
| DNS over UDP | UDP/53 | Có nếu capture nhìn payload và message không mã hóa |
| DNS over TCP | TCP/53 | Có, khi reassembly đủ |
| DNS over TLS (DoT) | TCP/853 | Không nếu không có giải mã hợp lệ |
| DNS over HTTPS (DoH) | HTTPS thường TCP/443, có thể HTTP/3 | Không nếu chỉ thấy TLS/QUIC encrypted packets |
| DNS over QUIC (DoQ) | UDP/853 theo thiết kế DoQ | Không nếu không có giải mã hợp lệ |
| DNS trong tunnel/VPN | Phụ thuộc tunnel | Tại outer tap thường không thấy inner payload |

**Nonstandard ports và DNS relay/proxy có thể tồn tại.** Dùng protocol decode/metadata/endpoint config thay vì chỉ nhìn số port.

## 4. DNS wire format: 12-byte header

| Offset từ đầu DNS message | Dài | Trường | Ý nghĩa |
|---|---:|---|---|
| 0–1 | 2 byte | ID | Transaction identifier 16 bit |
| 2–3 | 2 byte | Flags | QR/opcode/AA/TC/RD/RA/Z/AD/CD/RCODE |
| 4–5 | 2 byte | QDCOUNT | Số questions |
| 6–7 | 2 byte | ANCOUNT | Số answer records |
| 8–9 | 2 byte | NSCOUNT | Số authority records |
| 10–11 | 2 byte | ARCOUNT | Số additional records |

Các trường nhiều byte của DNS header cơ bản dùng **network byte order (big-endian)**. IP nguồn/đích và cổng thuộc outer IP/transport headers, không nằm trong DNS header.

### 4.1. Bit layout của flags

~~~text
Bits in DNS 16-bit flags:
  QR    OPCODE      AA TC RD RA Z AD CD   RCODE
  1     4 bits      1  1  1  1  1  1  1    4 bits
 +---+------------+--+--+--+--+--+--+--+-----------+
 |QR | OPCODE     |AA|TC|RD|RA|Z |AD|CD|   RCODE   |
 +---+------------+--+--+--+--+--+--+--+-----------+
 15  14 ... 11   10  9  8  7  6  5  4    3 ... 0
~~~

Bit **AD/CD** được định nghĩa bởi DNSSEC extensions; không xem toàn bộ 3 bits sau RA là reserved trong mọi chuẩn hiện hành. Các extended response codes có thể dùng EDNS OPT để bổ sung phần cao.

### 4.2. Ví dụ query

Một standard query thường:
- ID: giá trị 16-bit để correlate trong transaction context.
- QR=0, opcode=0.
- RD=1 khi client muốn resolver thực hiện recursion.
- QDCOUNT=1.
- ANCOUNT=NSCOUNT=0.
- ARCOUNT=0 hoặc >0 nếu có EDNS OPT và option khác.

Đó là **mẫu phổ biến**, không phải tất cả message đều có cùng dạng: DNS còn UPDATE, NOTIFY, AXFR và các extensions.

## 5. Giải nghĩa flags và response codes

| Trường/cờ | Ý nghĩa | Tránh hiểu nhầm |
|---|---|---|
| **QR** | 0=query, 1=response | Không chứng minh network packet đã đến app |
| **OPCODE** | Loại thao tác, 0=QUERY | Không phải QTYPE |
| **AA** | Server trả authoritative answer theo semantics | Không là DNSSEC validation |
| **TC** | Truncated message | Có thể kích hoạt TCP fallback |
| **RD** | Recursion Desired | Không chứng minh cache miss |
| **RA** | Recursion Available | Không chứng minh response do iterative lookup |
| **Z** | Reserved bit theo layout hiện hành | Không gộp với AD/CD |
| **AD** | Authenticated Data theo validator semantics | Không tự là bằng chứng đáng tin trên insecure stub path |
| **CD** | Checking Disabled request semantics | Không có nghĩa transport được bảo vệ |
| **RCODE** | Response Code | 0 không chứng minh có record mong muốn |

### 5.1. Một số RCODE

| Code | Tên | Diễn giải |
|---:|---|---|
| 0 | NOERROR | Không có lỗi DNS theo header, có thể có Answer hoặc NODATA |
| 1 | FORMERR | Lỗi định dạng message |
| 2 | SERVFAIL | Server thất bại khi xử lý; có thể upstream/validation/policy |
| 3 | NXDOMAIN | Tên được hỏi không tồn tại trong context/view tương ứng |
| 4 | NOTIMP | Thao tác không được triển khai |
| 5 | REFUSED | Server từ chối theo policy |
| 16 | BADVERS (EDNS) | EDNS version không hỗ trợ theo extended RCODE |
| Khác | Extended RCODE | Cần xem EDNS OPT và chuẩn tương ứng |

**Không quy SERVFAIL tự động thành DNSSEC lỗi.** Có thể là timeout upstream, resolver overload, forwarding failure, validation hoặc server-side problems. Muốn phân biệt cần thêm resolver logs/counters và query context.

## 6. Bốn sections của DNS message

| Section | Đếm bởi | Thường chứa |
|---|---|---|
| Question | QDCOUNT | QNAME, QTYPE, QCLASS |
| Answer | ANCOUNT | Các RR trực tiếp trong câu trả lời, có thể có CNAME |
| Authority | NSCOUNT | NS referrals, SOA trong negative response, DNSSEC metadata |
| Additional | ARCOUNT | Glue records, OPT pseudo-RR và thông tin bổ trợ |

**OPT không phải bản ghi zone thông thường** và không dùng TTL như ordinary RR. ANCOUNT=3 không đồng nghĩa có ba địa chỉ IP: phải đọc **TYPE của từng RR**.

### 6.1. Referrals và glue

Một recursive resolver hỏi parent zone có thể nhận NS records trong Authority và glue A/AAAA trong Additional để tìm nameservers được ủy quyền. Referral **không phải** câu trả lời cuối cùng cho tên ứng dụng.

### 6.2. Dấu hiệu parse lỗi

Nếu header khai báo ANCOUNT=2 nhưng chỉ giải mã được 1 record:
- Packet bị cắt ở capture snaplen?
- DNS message thật bị truncated/malformed?
- Có pointer compression không hợp lệ?
- TCP reassembly thiếu segments?
- Decoder thiếu hỗ trợ RR type/EDNS?
- Có link-layer offset sai do VLAN/tunnel?

Không sửa bytes nhằm ép parse PASS; giữ raw evidence và báo record incomplete/malformed.

## 7. QNAME, QTYPE và QCLASS

**Question** gồm tên ở dạng label length, QTYPE 16-bit và QCLASS 16-bit. Ví dụ tên api.example. trên wire:

~~~text
03 61 70 69 07 65 78 61 6d 70 6c 65 00
^  a  p  i  ^  e  x  a  m  p  l  e  root
3-byte label  7-byte label               zero-length label
~~~

Tên được mã hóa với **độ dài từng label**, không đặt dấu chấm literal giữa các labels. Một ordinary label tối đa 63 octets; giới hạn wire-format name gồm labels và terminal root là 255 octets theo chuẩn DNS.

### 7.1. Những QTYPE thường gặp

| QTYPE/RR TYPE | Số | Vai trò |
|---|---:|---|
| A | 1 | IPv4 |
| NS | 2 | Name server |
| CNAME | 5 | Canonical alias |
| SOA | 6 | Zone authority metadata |
| PTR | 12 | Reverse lookup |
| MX | 15 | Mail server preference |
| TXT | 16 | Text data |
| AAAA | 28 | IPv6 |
| SRV | 33 | Service priority/weight/port/target |
| OPT | 41 | EDNS pseudo-RR, không phải ordinary zone record |
| DS | 43 | DNSSEC delegation signer |
| RRSIG | 46 | DNSSEC signature |
| NSEC | 47 | DNSSEC denial proof |
| DNSKEY | 48 | DNSSEC public key material |
| NSEC3 | 50 | DNSSEC hashed denial proof |
| SVCB | 64 | Service binding |
| HTTPS | 65 | HTTPS service binding parameters |

**QTYPE=ANY (255)** không bảo đảm server trả mọi record của tên; response và policy tùy server/chuẩn áp dụng.

### 7.2. QCLASS

Đa số Internet DNS sử dụng **IN (1)**. Không nhầm CLASS với TYPE. Một số message/phương thức có cách dùng đặc thù; phải dựa vào decoder và protocol spec tương ứng.

### 7.3. Chữ hoa/thường và 0x20 randomization

DNS name matching thường case-insensitive; một số resolvers randomize case của QNAME như lớp phòng vệ bổ sung khi so response. Khác case không mặc định là domain khác. Nhưng raw QNAME có thể hỗ trợ kiểm tra transaction consistency. Không xem biện pháp này thay DNSSEC, randomized source ports hoặc authenticated transport.

## 8. Name compression và compression pointers

Các tên lặp lại trong Answer/Authority có thể được **nén bằng pointer**, tiết kiệm kích thước DNS message.

~~~text
c0 0c
^^ ^^
High bits 11 indicate pointer; low 14 bits give offset 12
Offset is from start of DNS message, not Ethernet frame
~~~

Pointer C0 0C thường trỏ tới QNAME ngay sau header 12 byte khi layout đúng. Nó không phải label dài 192 byte.

### 8.1. Tại sao pointer dễ gây parser bugs?

- Offset vượt message/capture.
- Pointer tự trỏ hoặc tạo vòng lặp.
- Không phân biệt độ dài phần encoded và tên decompress.
- Dùng offset tính từ TCP length prefix thay vì đầu DNS message.
- Bỏ qua RDLENGTH khi RDATA chứa nhiều fields.
- Giả định mọi record type cho phép name compression ở mọi vị trí.

Một decoder an toàn cần **bounds checks, cycle detection, giới hạn expansion depth/name length và chính xác record-specific parsing**.

## 9. Resource Record (RR) và TTL

Một RR thông thường gồm:

~~~text
NAME
TYPE       16 bits
CLASS      16 bits
TTL        32 bits
RDLENGTH   16 bits
RDATA      RDLENGTH octets, format phụ thuộc TYPE
~~~

Ví dụ A có RDATA 4 byte; AAAA 16 byte; CNAME trỏ tới domain name; MX có preference + exchanger; TXT có các text strings theo encoding riêng; SVCB/HTTPS có structured parameters.

### 9.1. TTL nói gì?

- TTL đo bằng giây theo semantics caching.
- Cached response có thể trả TTL thấp hơn original.
- TTL=0 yêu cầu không giữ dữ liệu trong cache theo nguyên tắc tương ứng.
- TTL khác nhau giữa các RR không mặc định là bất thường.
- TTL cao **không chứng minh trustworthy**, TTL thấp không tự là dấu hiệu malicious.
- Application/OS/cache có thể áp TTL handling riêng; không suy từ packet ra toàn bộ lifetime trên client.

### 9.2. Ví dụ response sau decode

~~~text
Question: api.orders.example. IN A
RCODE: NOERROR
Answer:
  api.orders.example.  60  IN CNAME edge.orders.example.
  edge.orders.example. 120 IN A     198.51.100.25
  edge.orders.example. 120 IN A     198.51.100.26
ANCOUNT: 3
~~~

Tên/IP thuộc dải tài liệu. Ba answer records ở đây gồm **một alias và hai IP**, không phải ba IP.

## 10. Các kiểu RR và ý nghĩa điều tra

| RR TYPE | Có thể thấy | Không nên suy ra |
|---|---|---|
| A/AAAA | Địa chỉ trả về và TTL | Client chắc chắn mở kết nối tới từng IP |
| CNAME | Alias chain | HTTP redirect |
| NS | Delegation/referral | Lookup đã hoàn tất |
| SOA | Zone metadata/negative caching | Có mọi domain trong zone |
| TXT | Policy/verification/text strings | TXT dài chắc chắn exfil |
| PTR | Reverse name | Identity host được xác minh |
| MX | Mail destination candidates | Email thật đã được gửi |
| SRV | Target/port/priority/weight | App thật đã gọi endpoint |
| CAA | CA issuance policy | Certificate đang dùng hợp lệ |
| SVCB/HTTPS | Service/protocol hints/parameters | Kết nối TLS đã thành công |
| DNSKEY/DS/RRSIG | Dữ liệu cần cho DNSSEC | Validation đã PASS |
| NSEC/NSEC3 | Authenticated denial proof nếu validate | Tên không tồn tại ở mọi DNS view |
| OPT | EDNS negotiation/extended metadata | Một ordinary Answer RR có TTL cache |

### 10.1. CNAME và DNAME

CNAME tạo alias cho owner name, còn DNAME có semantics redirect cho một subtree. Một resolver có thể tổng hợp CNAME theo cơ chế DNAME. Khi phân tích cần đọc **TYPE**, không coi mọi trường hợp alias là một CNAME record gốc.

### 10.2. A/AAAA song song

Một dual-stack client có thể hỏi A và AAAA gần cùng thời điểm. Hai QTYPE khác nhau không mặc định là retries. DNS packet cũng không cho biết chính xác sau đó client chọn IPv4 hay IPv6; cần flow/TCP/TLS packet correlation.

## 11. Ghép query–response và đo RTT

Phải correlate theo **DNS ID + outer tuple + QNAME/QTYPE/QCLASS + time window + observation point**. ID chỉ 16 bit và có thể được dùng lại; không dùng ID đơn độc.

~~~text
08:00:00.100 10.24.8.15:53021 -> 10.24.0.53:53
             ID=0x4a91 QR=0 QTYPE=A QNAME=api.orders.example.

08:00:00.129 10.24.0.53:53 -> 10.24.8.15:53021
             ID=0x4a91 QR=1 RCODE=NOERROR ANCOUNT=2

Observed delta = 29 ms
~~~

**29 ms là elapsed time tại điểm capture**, có thể chứa network, cache và resolver work; không đồng nghĩa thời gian authoritative query. Đồng hồ sensor, direction, NIC offloads và packet duplication ảnh hưởng tính chính xác.

### 11.1. Retry

- Client có thể retry cùng resolver với cùng/different ID/port.
- Client có thể chuyển resolver khác sau timeout.
- DNS response có thể tới sau khi đã retry.
- TCP fallback sau TC=1 là logical continuation, không phải nhất thiết một name mới.
- Resolver cache refresh/prefetch có thể tạo upstream queries khác nhịp client.
- NAT/proxy có thể thay source port và transaction ID.

Không gắn nhãn một duplicate query là tấn công ngay; phân biệt **network loss, retransmission, application retry và transaction collision**.

### 11.2. Unmatched responses

Một response không có query tương ứng trong file có thể do query xảy ra trước khi bắt đầu capture, pcap bị cắt, filter thiếu chiều, UDP loss, asymmetric routing, NAT hoặc traffic bất thường. Ghi **unmatched** trước khi suy về spoofing/cache poisoning.

## 12. Recursion, forwarding, cache và split-horizon

**Stub resolver** thường hỏi configured recursive resolver. Recursive resolver có thể trả từ cache, forward lên resolver khác hoặc thực hiện iterative resolution qua root/TLD/authoritative servers.

### 12.1. RD và RA

- RD=1: client yêu cầu recursion.
- RA=1: server thông báo có recursion capability.
- Response có RA=1 không chứng minh cache miss.
- AA=1 có thể xuất hiện ở authoritative reply; AA không bằng DNSSEC authentic data.
- Cache hit không nhất thiết tạo query tới root/TLD trong cùng time window.

### 12.2. Referral và glue

~~~mermaid
flowchart TD
    S[Stub client] --> R[Recursive resolver]
    R --> T[Parent/root/TLD chain]
    T -->|Authority NS referral| R
    T -.Glue A/AAAA when applicable.-> R
    R --> A[Authoritative server]
    A -->|Answer/negative response| R
    R --> S
~~~

Một referral có NS records và có thể chứa **glue** trong Additional. Glue giúp tìm name server theo delegation, không thay mọi authoritative answer. DNS delegation có nhiều trường hợp và bailiwick rules, nên không kết luận glue address đáng tin chỉ vì nó ở Additional.

### 12.3. Split-horizon DNS

Một hostname có thể trả private address cho corporate/VPN resolver và public address cho Internet resolver. So packet phải xét **client location, resolver, DNS zone/view, VPN và thời điểm**; khác answer không tự chứng minh DNS hijack.

### 12.4. Nhiều cache layers

Ứng dụng, OS stub, node local DNS, CoreDNS, DNS forwarder và recursive server có thể cache. Capture ở Pod chỉ thấy query tới local resolver; capture ở upstream có thể thấy source IP của forwarder. Attribution tới Pod/user cần logs/mapping bổ sung, không dựa IP upstream thuần túy.

## 13. NXDOMAIN, NOERROR/NODATA, SERVFAIL và negative caching

Một trong những nguyên nhân khiến điều tra DNS sai hướng là **đồng nhất mọi response không có A/AAAA với NXDOMAIN**.

### 13.1. Phân biệt ba trạng thái

| Kết quả | Packet có thể trông thế nào | Diễn giải đúng |
|---|---|---|
| **NOERROR + A/AAAA** | RCODE=0, có Answer record đúng loại | Có RR đáp ứng query tại observation point |
| **NOERROR / NODATA** | RCODE=0 nhưng không có RR requested type trong answer, authority có thể có SOA | Tên tồn tại theo view nhưng không có requested type, hoặc cơ chế tương đương |
| **NXDOMAIN** | RCODE=3, Authority có thể có SOA/NSEC(3) | Tên được hỏi không tồn tại theo response/context |
| **SERVFAIL** | RCODE=2 | Resolver/server không xử lý thành công; chưa biết nguyên nhân |
| **REFUSED** | RCODE=5 | Server từ chối theo policy hoặc điều kiện tương ứng |
| **FORMERR** | RCODE=1 | DNS message bị coi là sai format |
| **Timeout/no response** | Chỉ thấy query, hoặc pcap thiếu reply | Không phải một RCODE; cần kiểm tra path/capture |

### 13.2. Negative caching

Resolvers có thể cache negative responses theo cơ chế DNS negative caching; SOA/TTL liên quan tới **thời hạn cache** theo chuẩn và policy. Không suy rằng negative answer bị giữ mãi hoặc client luôn hỏi lại ngay. Với RFC 2308, TTL negative caching có liên hệ **minimum giữa SOA.MINIMUM và SOA TTL** theo semantics của negative response; thực tế có giới hạn và tối ưu từ resolver implementation.

### 13.3. SOA không phải câu trả lời A

Khi hỏi A nhưng nhận Authority SOA với RCODE=0 và không có A RR, đó có thể là **NODATA**. Không lấy việc thấy SOA rồi suy zone chưa tồn tại. Khi có DNSSEC, NSEC/NSEC3 có thể được dùng làm bằng chứng phủ định dưới quá trình validation.

### 13.4. Những câu hỏi tiếp theo

- Tên sai/chưa publish hay type AAAA chưa có?
- Query đang đi tới resolver đúng split-horizon view?
- Negative cache đã được làm mới sau thay đổi zone chưa?
- Có resolver policy block trả NXDOMAIN, REFUSED hoặc address sinkhole không?
- Có DNSSEC validation failure tạo SERVFAIL?
- Response ở authoritative, forwarder hay local cache?

**Nên ghi timestamp, resolver, QNAME, QTYPE, RCODE, Authority SOA và TTL**, không chỉ chép một ảnh dòng Wireshark.

## 14. UDP, TCP fallback và kích thước DNS response

DNS dùng UDP hiệu quả cho nhiều truy vấn nhỏ, nhưng **TCP/53 là thành phần bình thường và cần được hỗ trợ** trong hệ sinh thái DNS hiện đại. Không chặn TCP/53 theo giả định rằng DNS “chỉ dùng UDP”.

### 14.1. Khi nào TCP hữu ích?

- Response bị truncated với **TC=1**, client/resolver cần retry phù hợp.
- Câu trả lời lớn như một số DNSSEC RRsets.
- Zone transfer AXFR thường chạy trên TCP, hoặc các nhu cầu truyền tin theo chuẩn.
- Resolver/client lựa chọn TCP để bảo đảm message delivery hoặc theo policy.
- DNS message vượt kích thước UDP khả dụng/không nên fragment.

### 14.2. Dòng fallback tiêu biểu

~~~mermaid
sequenceDiagram
    participant C as DNS Client
    participant S as DNS Resolver
    C->>S: UDP/53 query
    S-->>C: UDP response TC=1 (truncated)
    C->>S: TCP SYN/ACK/handshake
    C->>S: TCP/53 length-prefixed DNS query
    S-->>C: TCP/53 full DNS response
~~~

Đây là **hành vi minh họa**, không bảo đảm mọi client tự thực hiện đúng hoặc luôn dùng cùng transaction ID/ports. Cần kiểm tra TCP firewall, stateful ACL, SYN/ACK/connection resets và stream reassembly nếu fallback thất bại.

### 14.3. TCP length prefix

Nếu DNS message qua TCP có đúng 45 bytes, 2-byte prefix có thể là **00 2d** (45 thập phân), sau đó mới đến **DNS ID**. Khi phân tích hex, không nhầm length prefix với 2 byte ID. Một DNS TCP stream có thể chứa nhiều messages và có pipelining tùy implementation.

### 14.4. Không đồng nhất truncated capture với TC bit

- **TC=1:** cờ trong DNS header, được server đặt theo semantics.
- **Capture truncated:** sensor đã ghi thiếu bytes vì snaplen/file corruption.
- **IP fragmented:** packets chia thành fragments trên mạng.
- **TCP segmented:** một DNS message nằm trong nhiều TCP segments.

Bốn hiện tượng khác nhau, có cách chẩn đoán khác nhau.

## 15. EDNS(0) và OPT pseudo-resource record

**Extension Mechanisms for DNS (EDNS)** mở rộng một số giới hạn và trường điều khiển của DNS truyền thống. EDNS(0) thường được biểu diễn bởi **OPT pseudo-RR TYPE=41 trong Additional**.

### 15.1. OPT có gì đặc biệt?

| Field theo OPT wire format | Diễn giải |
|---|---|
| NAME | Root name (zero-length) |
| TYPE | 41 (OPT) |
| CLASS | UDP payload size mà sender quảng bá theo semantics EDNS |
| TTL, phần cao | Extended RCODE, EDNS version, flags (gồm DO) |
| RDLEN | Độ dài vùng options data |
| RDATA | Danh sách EDNS options dạng code/length/value |

Một số công cụ trình bày các trường OPT TTL thành **Extended RCODE, Version, Flags**; không coi chúng là TTL cache của zone RR.

### 15.2. UDP payload size

Phần lớn ứng dụng dùng EDNS để cho biết UDP response size có thể nhận. Các con số như **1232 bytes** thường được chọn trong nhiều triển khai để giảm nguy cơ fragmentation trên đường IPv6 tối thiểu MTU theo những giả định cụ thể, nhưng **không là kích thước bắt buộc cho mọi môi trường/đường truyền**. Kiểm tra phiên bản resolver, device MTU và policy; EDNS không miễn trừ khỏi packet loss.

### 15.3. DO bit

**DO (DNSSEC OK)** trong EDNS flags biểu thị client muốn nhận DNSSEC-related records theo semantics; **DO=1 không có nghĩa response đã được cryptographically validated**. Validation phụ thuộc resolver/client và chain of trust. Để biết một query có dùng DNSSEC, phải phân biệt DO (khả năng/nội dung) với AD/CD (tín hiệu/ý định) và bằng chứng xác thực.

### 15.4. Extended RCODE

4 bit RCODE thấp trong header có thể kết hợp phần extended trong OPT để biểu diễn RCODE lớn hơn, ví dụ EDNS BADVERS. Nếu chỉ đọc 4 bit thấp, analyst có thể gán sai một lỗi EDNS thành NOERROR. Wireshark thường trình bày combined response code; khi decode thủ công phải xét OPT.

### 15.5. Một số EDNS options

- **DNS Cookies:** hỗ trợ kiểm chứng ngữ cảnh client/server và giảm một số kiểu spoofing/amplification trong điều kiện hỗ trợ; không thay DNSSEC/mTLS.
- **EDNS Client Subnet (ECS):** có thể cung cấp prefix địa chỉ để quyết định routing/CDN; đồng thời có hệ quả privacy và cache partitioning.
- **EDNS Padding:** che phần kích thước message ở những triển khai phù hợp, thường hữu ích khi DNS transport mã hóa.
- **NSID:** có thể cung cấp server identifier cho chẩn đoán.
- Các options khác tùy chuẩn/vendor và version.

**Không coi mọi unknown EDNS option là tấn công**; cần tra code registry/implementation và kiểm tra RDLEN/option length.

## 16. MTU, fragmentation và “DNS chỉ thất bại với câu trả lời lớn”

Một số DNSSEC responses lớn hơn query thông thường. Nếu network path có fragment loss, firewall/drop policy hoặc EDNS size không phù hợp, client có thể gặp **query A nhỏ chạy nhưng DNSSEC/HTTPS/TXT response lớn timeout**.

### 16.1. Cách nhận diện theo packet

1. Xem query có **EDNS OPT** và UDP payload size gì.
2. Xem response length, TC flag và transport.
3. Xem IP fragmentation fields (IPv4 MF/fragment offset hoặc IPv6 Fragment Header khi có).
4. Xem có **fragments bị thiếu** trong capture hay IP reassembly warning không.
5. Xem TCP fallback có diễn ra sau TC=1 không.
6. Đối chiếu firewall, VPN/tunnel MTU, PMTUD và ICMP errors.
7. Kiểm tra whether capture điểm trước/sau fragment/drop.
8. Tránh kết luận từ một packet nếu đang nhìn fragments thiếu.

### 16.2. MTU và giao thức mã hóa

DNS-over-HTTPS/QUIC có framing và encryption khác UDP DNS; lỗi MTU/fragment hoặc QUIC path không hiển thị như một DNS TC bit. Phải phân tích đúng layer và transport. Không đơn giản hóa bằng cách “tăng buffer 65535 cho mọi resolver” mà không xem đường đi.

### 16.3. Những thay đổi phải có kiểm thử

Giảm advertised EDNS UDP size, bật TCP fallback hoặc thay firewall có thể khắc phục một số sự cố, nhưng phải đo **latency, CPU, network path, TLS/HTTP3 compatibility và security policy**. Thay đổi nên có config owner, test và rollback.

## 17. DNSSEC: DNS packet nào là bằng chứng?

**DNSSEC** dùng chữ ký số và chain of trust để xác thực nguồn gốc/tính toàn vẹn dữ liệu DNS trong phạm vi những RRsets được ký và được validate. DNSSEC **không mã hóa tên miền** và **không cấp quyền ứng dụng**.

### 17.1. Những records quan trọng

| Record | Vai trò |
|---|---|
| **DNSKEY** | Public keys của zone |
| **DS** | Băm/định danh liên kết delegation tới DNSKEY của child zone |
| **RRSIG** | Chữ ký trên RRset cùng metadata thời hạn/algorithm |
| **NSEC/NSEC3** | Bằng chứng có thể validate cho negative answers theo cơ chế |
| **CDS/CDNSKEY** | Hỗ trợ một số quy trình cập nhật chain of trust khi được dùng |

### 17.2. Luồng validation khái quát

~~~mermaid
flowchart TD
    ROOT[Trusted Root Anchor] --> DS[Parent DS]
    DS --> KEY[Child DNSKEY]
    KEY --> SIG[RRSIG on RRset]
    SIG --> RES{Cryptographic validation}
    RES -->|Pass| SEC[Secure answer under trust policy]
    RES -->|Fail| BAD[Validation failure / bogus]
    RES -->|No chain or unsupported case| INDET[Insecure / indeterminate as applicable]
~~~

Tên các trạng thái Secure/Insecure/Bogus/Indeterminate có semantics theo validator. **Trong packet đơn lẻ**, nhìn thấy RRSIG hoặc DS **không tự chứng minh validation PASS**; phải có chain of trust, đúng thời gian và cryptographic verification từ validator đáng tin.

### 17.3. AD và CD trong điều tra

- **AD=1:** một resolver báo Authenticated Data theo semantics; nên chỉ tin tín hiệu qua đường/trust setup được bảo vệ phù hợp.
- **CD=1:** client yêu cầu checking disabled theo cách được chuẩn hóa; phản hồi có thể khác khi validator kiểm tra thất bại.
- **SERVFAIL:** một số DNSSEC validation failures có thể dẫn đến SERVFAIL, nhưng **SERVFAIL còn nhiều nguyên nhân khác**.
- **DO=1:** muốn dữ liệu DNSSEC, không đồng nghĩa validator đã PASS.

### 17.4. DNSSEC không bảo đảm tất cả

DNSSEC không:
- Mã hóa DNS queries.
- Ngăn một signed domain phục vụ IP độc hại do zone operator/credential compromise.
- Xác thực người dùng cuối hoặc quyền truy cập API.
- Thay TLS server certificate verification.
- Bảo đảm mọi resolver/client đã validate đúng.

## 18. DNS mã hóa: DoT, DoH và DoQ

Không phải mọi DNS packet có thể đọc QNAME trực tiếp bằng network capture.

| Kiểu DNS | Giao vận thông dụng | Sensor thụ động thường nhìn thấy | Không nhìn thấy khi mã hóa |
|---|---|---|---|
| **Plain UDP/TCP DNS** | UDP/TCP 53 | DNS header, QNAME, RCODE, RRs nếu payload đầy đủ | Không áp dụng cho plaintext DNS |
| **DoT** | TLS qua TCP/853 | IP/port, timing, TLS metadata khi có | DNS message bên trong TLS |
| **DoH** | HTTPS thường TCP/443 hoặc HTTP/3 | IP/port, TLS/QUIC metadata theo visibility | HTTP DNS request/response bodies, QNAME |
| **DoQ** | QUIC qua UDP/853 theo chuẩn DoQ | IP/UDP/QUIC metadata hạn chế | DNS message bên trong QUIC encryption |
| **VPN tunnel** | IPsec/WireGuard/other | Outer endpoints, bytes, timing | Inner DNS traffic tại outer sensor |

### 18.1. DNS mã hóa không mặc định là hành vi xấu

DoT/DoH/DoQ có thể bảo vệ quyền riêng tư và giảm nghe lén trên mạng không tin cậy. Vấn đề bảo mật là **resolver có được phê duyệt, policy được thực thi ở đâu và endpoint telemetry có đủ hay không**, không phải “mọi DNS encrypted là độc hại”.

### 18.2. Cách phân tích khi không có plaintext payload

- Xem endpoint resolver, network policy và flow logs.
- Thu telemetry từ **approved resolver** hoặc application/endpoint ở vị trí giải mã hợp lệ.
- Dùng DNS query logs được cấp phép, private endpoint hoặc proxy auth metadata.
- Không suy QNAME từ một IP shared CDN hoặc visible SNI nếu dữ liệu không đủ.
- Không yêu cầu tắt TLS verification hoặc đánh cắp secrets chỉ để đọc plaintext.
- Với HTTP/3 DoH, nhớ request đi qua QUIC, không phải mọi kết nối 443 đều TCP.

### 18.3. SNI và HTTPS hostnames

Quan sát SNI trong TLS (khi có/nhìn được) không đồng nghĩa xác định **domain được hỏi trong DoH**: DoH server hostname là resolver endpoint, còn DNS QNAME nằm trong encrypted HTTP request. **ECH** có thể giảm visibility của một số TLS metadata. Phân biệt **resolver address** và **queried name**.

## 19. Chọn vị trí bắt gói: vị trí quyết định câu chuyện

Một PCAP có thể chính xác nhưng **không đại diện cho đường đi mình đang phân tích**.

| Điểm capture | Có thể thấy | Giới hạn |
|---|---|---|
| Ứng dụng/stub resolver | Query từ app khi ra socket | Cache trong app có thể không tạo packet |
| Pod veth/CNI | DNS traffic của Pod nếu đi qua hook | Pod IP reuse, NAT, overlay, hostNetwork |
| Node DNS cache | Queries/answers trên node | Source ở upstream có thể là node IP |
| CoreDNS/recursive server | Client queries và upstream traffic theo interface | Không biết mọi user sau forwarder/NAT |
| DNS forwarder edge | Northbound queries | Local cache hit không có upstream query |
| Firewall/VPN gateway | DNS flows ở boundary | Nếu encrypted tunnel, chỉ outer traffic |
| Authoritative server | Queries server nhận | Không thấy cache-hit requests của clients |
| Endpoint DoH client logs | DNS outcome khi instrument hợp lệ | Quyền riêng tư, API/SDK-specific |

### 19.1. Đường đi bị đảo hướng hoặc NAT

Một DNS response được ghi ở after-SNAT không nhất thiết giữ source/destination tuple giống ở before-NAT. Không kết luận giả mạo chỉ do tuple đổi nếu bạn đang so hai observation points. Cần firewall/NAT logs và timestamp mapping.

### 19.2. Mirror/SPAN, TAP và packet drop

- **SPAN/mirror** có thể bỏ packets khi overloaded; đôi khi một hướng chưa được mirror.
- **Network TAP** có đặc tính thu khác, vẫn cần capture appliance đủ khả năng.
- **Host capture** chịu ảnh hưởng CPU, kernel ring buffers, NIC offload, VLAN stripping.
- **PCAP snapshot length (snaplen)** có thể làm DNS response/trường bị cắt.
- **Timestamp accuracy** phụ thuộc NIC/driver/clock synchronization.

Phải ghi metadata sensor, interface, directions, capture filter, snaplen, sampling/drop counters và thời gian UTC. **PCAP thiếu một chiều không chứng minh resolver không phản hồi.**

## 20. Wireshark: đọc DNS packet theo từng lớp

Quy trình nên bắt đầu với PCAP **được cấp quyền hoặc synthetic**, chưa cần live capture.

### 20.1. Mở và xác định giao thức

1. Mở file PCAP/PCAPNG trong Wireshark.
2. Kiểm tra timestamps và time zone hiển thị.
3. Chọn một packet DNS plaintext.
4. Mở lần lượt **Frame → Link layer → IP → UDP/TCP → Domain Name System**.
5. Đối chiếu **DNS ID, QR, flags, counts, QNAME/QTYPE, answer TTL và RCODE**.
6. Nếu TCP, kiểm tra length prefix và reassembled stream.
7. Nếu thấy OPT, mở EDNS details/DO bit/UDP payload size.
8. Dùng follow packet/stream có kiểm soát theo nhu cầu; không xuất raw sensitive data tùy tiện.

### 20.2. Một số display filters thường gặp

~~~text
dns
dns.flags.response == 0
dns.flags.response == 1
dns.qry.name == "api.orders.example"
dns.qry.type == 1
dns.flags.rcode == 3
dns.flags.rcode == 2
dns.flags.truncated == 1
udp.port == 53 || tcp.port == 53
ip.addr == 10.24.0.53
~~~

Các dòng trên là **Wireshark display filter expressions**, dùng riêng từng dòng trong filter box, không paste cả block như một filter. Field names khả dụng phụ thuộc dissector/version; có thể dùng **right-click field → Apply as Filter** hoặc kiểm tra Field Reference của bản Wireshark đang dùng.

### 20.3. Phân biệt capture filter với display filter

| Loại | Cú pháp ví dụ | Được áp khi nào |
|---|---|---|
| **Capture filter (BPF)** | udp port 53 or tcp port 53 | Khi live capture, quyết định packets được lưu |
| **Display filter** | dns.flags.response == 1 | Sau khi có packets, quyết định rows hiển thị |

Không dùng cú pháp Wireshark display filter trong tcpdump capture filter. Một capture filter chỉ lấy port 53 có thể **bỏ mất DoH/DoT/DoQ**; không khẳng định DNS traffic không tồn tại.

### 20.4. Wireshark tự correlate?

Wireshark có thể thể hiện request/response relation hoặc response time khi đủ data và dissector hỗ trợ. Nhưng phải tự kiểm tra **ID reuse, NAT, retransmissions, capture gap, TCP reassembly** thay vì tin một field tự động như bằng chứng đầy đủ. Một kết quả expert-info “Malformed Packet” có thể do sensor cắt packet, không nhất thiết server gửi malformed bytes.

## 21. tcpdump và TShark: thực hành offline chỉ đọc

Dùng các lệnh dưới đây với PCAP synthetic **đã có**, không thay đổi firewall/route và không thực hiện live capture ngoài quyền.

### 21.1. Lọc DNS truyền thống với tcpdump

~~~bash
# Đọc file offline, không bắt traffic mới
tcpdump -nn -r dns-lab.pcap \
  'udp port 53 or tcp port 53'

# Hiển thị chi tiết decode với packet đã có
tcpdump -nn -vv -r dns-lab.pcap \
  'udp port 53 or tcp port 53'
~~~

**tcpdump BPF filter** chọn packets theo outer protocol/ports; nếu DNS qua tunnel/DoH hoặc port tùy biến, filter không cung cấp toàn bộ visibility. tcpdump có thể hiển thị DNS summary nhưng không phải trình kiểm chứng DNSSEC signatures.

### 21.2. TShark đọc DNS fields

~~~bash
# Các field được TShark hỗ trợ tùy version/dissector
tshark -r dns-lab.pcap -Y 'dns' -T fields \
  -e frame.time_epoch -e ip.src -e ip.dst \
  -e dns.id -e dns.flags.response \
  -e dns.qry.name -e dns.qry.type \
  -e dns.flags.rcode

# Chỉ những DNS responses có RCODE=3
tshark -r dns-lab.pcap -Y 'dns.flags.rcode == 3' \
  -T fields -e frame.time_epoch -e dns.id -e dns.qry.name
~~~

Dùng **IPv6 source/destination fields** khi packet dùng IPv6. TShark có thể có fields response-time và response links tùy version. Không tự tuyên bố truy vấn tên nào là exfil chỉ dựa trên một dòng xuất CSV.

### 21.3. Kiểm tra field names theo bản TShark

~~~bash
# Liệt kê fields của dissectors được cài; output có thể rất dài
tshark -G fields
~~~

Lệnh đọc metadata của bản cài, không thay đổi PCAP. Khi field code khác, tra được tên phù hợp trong output hoặc Wireshark GUI; không tự bịa field code để lệnh có vẻ chính xác.

### 21.4. Quyền riêng tư và xuất dữ liệu

Nếu export CSV/JSON:
- Chọn chỉ fields cần thiết, không xuất toàn DNS payload mặc định.
- Redact các internal hostnames, user IDs, partner identifiers khi chia sẻ.
- Giữ PCAP nguyên gốc trong kho approved/immutable nếu dùng làm evidence.
- Ghi tool version, filename/checksum và filtering assumptions.
- Đừng upload PCAP nhạy cảm lên public packet analyzer.

## 22. Ví dụ giải mã một DNS packet ở mức hex

Một DNS query A cho **api.example.** (không có EDNS) có thể có DNS payload:

~~~text
Offset  Hex bytes                                 Interpretation
00      4a 91                                     ID = 0x4a91
02      01 00                                     Flags = 0x0100 (RD=1)
04      00 01                                     QDCOUNT = 1
06      00 00                                     ANCOUNT = 0
08      00 00                                     NSCOUNT = 0
10      00 00                                     ARCOUNT = 0
12      03 61 70 69 07 65 78 61 6d 70 6c 65 00 QNAME=api.example.
25      00 01                                     QTYPE=A
27      00 01                                     QCLASS=IN
~~~

Độ dài **DNS message này là 29 bytes**, chưa tính IP/UDP headers. QNAME 13 bytes ở offsets 12–24, QTYPE offsets 25–26 và QCLASS offsets 27–28.

Một DNS response minh họa cho **api.example. A 198.51.100.25, TTL=60**:

~~~text
DNS HEADER
  4a 91 81 80 00 01 00 01 00 00 00 00
  ID=0x4a91, flags=0x8180 (QR=1, RD=1, RA=1, RCODE=0)
  QD=1, AN=1, NS=0, AR=0

QUESTION (same as query)
  03 61 70 69 07 65 78 61 6d 70 6c 65 00 00 01 00 01

ANSWER
  c0 0c                  NAME pointer -> DNS offset 12
  00 01                  TYPE=A
  00 01                  CLASS=IN
  00 00 00 3c            TTL=60 seconds
  00 04                  RDLENGTH=4
  c6 33 64 19            RDATA=198.51.100.25
~~~

Response DNS payload dài **45 bytes** (12 header + 17 question + 16 answer). Có thể kiểm tra: pointer C0 0C trỏ tới QNAME offset 12. Không có EDNS/OPT, DNSSEC, TCP prefix hoặc Ethernet/IP/UDP outer headers trong ví dụ.

### 22.1. Tự hỏi khi đọc hex

- DNS message bắt đầu ở offset nào trong packet?
- Flags=0x8180 có những bit gì?
- Header counts có khớp sections thật?
- QNAME có dùng byte đếm labels đúng?
- Answer pointer có trỏ đúng offset 12?
- TTL 00 00 00 3c nghĩa gì?
- RDLENGTH=4 có đúng cho TYPE=A?
- C6 33 64 19 là địa chỉ nào?
- Source IP/port của response có khớp query trong cùng transaction context không?

## 23. Tính latency, failure rate và coverage từ PCAP

### 23.1. DNS observed RTT

\[
t_{\text{DNS observed}} = t_{\text{response seen}} - t_{\text{query seen}}
\]

Chỉ có nghĩa khi correlate đúng transaction và sensor thấy cả hai chiều. Với TCP, cần phân biệt **connection setup** với thời gian DNS message; với DoH phải dùng instrumentation tại endpoint được cấp phép để biết DNS operation latency bên trong HTTPS.

### 23.2. Error ratio

Giả sử trong một cửa sổ capture đầy đủ có 10.000 matched DNS transactions, trong đó 150 responses RCODE=2:

\[
\text{Observed SERVFAIL share} = \frac{150}{10000}\times100\%=1.5\%
\]

Đây là share của matched transactions trong scope đã chọn, **không** là tỷ lệ lỗi người dùng trên mọi DNS calls nếu có packet drops, cache hits, sampling, multiple retries, DNS-over-HTTPS hoặc scope thiếu.

### 23.3. Một số chỉ số nên theo dõi

| Chỉ số | Nguồn | Giới hạn |
|---|---|---|
| Queries/s theo resolver | DNS plaintext packets / resolver metrics | Cache/DoH và sensor coverage |
| Response RCODE distribution | DNS headers | Cần phân biệt policy-manipulated responses |
| p50/p95 observed RTT | Matched queries/responses | Không đồng nhất total app DNS latency |
| NXDOMAIN/NODATA/SERVFAIL shares | QTYPE + RCODE + answer context | Negative caching và split-horizon |
| TCP fallback ratio | TC responses và correlated TCP queries | Pcap có thể thiếu packets |
| EDNS usage/payload sizes | OPT fields | Không bảo đảm path MTU thực |
| DNSSEC flags usage | DO/AD/CD/RRs | Không chứng minh validation thành công |
| Unmatched queries/responses | Correlation engine | Packet loss, NAT, retries, ambiguous IDs |
| Capture drop rate | Capture tooling/agent stats | Không suy từ PCAP thiếu |
| Query size/name length | Packet/decoded name | Không chứng minh tunneling hoặc DGA |
| Resolver destination mix | IP/port/identity | Resolver approval cần policy/inventory |
| Encrypted DNS egress | Network/endpoint signals | Không tự biết QNAME |

### 23.4. Một báo cáo có thể tái lập

Một kết quả phân tích nên ghi:
- Capture start/end UTC, sensor location/interface và direction.
- File hash, file format, snaplen, tool version.
- Capture/display filters, DNS protocol/transport scope.
- Counts of queries/responses/matched/orphaned packets.
- Rules for retransmissions, TCP reassembly, NAT và dedup.
- Coverage exceptions: cache, DoH/DoT/DoQ, IPv6, tunnels, SPAN drops.
- Statistical windows, sample sizes và uncertainty.
- Evidence IDs và kết luận giới hạn theo dữ liệu.

## 24. Threat model khi phân tích DNS packet

DNS có mặt trong nhiều luồng nghiệp vụ bình thường nên cũng là điểm quan sát có ích với những hành vi bất thường. Nhưng **query tới tên lạ không đồng nghĩa máy đã nhiễm malware**; một response có vẻ bất thường không tự chứng minh spoofing. Mô hình đe dọa cần nêu rõ **tài sản, trust boundary, khả năng đối tượng tấn công, điểm đo và độ tin cậy dữ liệu**.

### 24.1. Tài sản và quyền hạn

- Dữ liệu truy vấn DNS từ client, resolver, authoritative servers.
- Resolver caches, forwarder rules, conditional zones, DNSSEC trust anchors.
- DNS zone records, registrar và quyền thay đổi DNS.
- Service identities, endpoints, client devices và IP allocation history.
- DNS query logs, PCAP, IDS/IPS alerts, firewall decisions.
- Các API/ứng dụng phụ thuộc DNS để phân giải, kiểm tra certificate và định tuyến.
- Hệ thống telemetry và người có quyền đọc dữ liệu DNS.

### 24.2. Kịch bản và bằng chứng

| Kịch bản | Dấu hiệu DNS có thể thấy | Cần xác minh bằng |
|---|---|---|
| Resolver configuration drift | Query đi tới resolver mới ngoài inventory | DHCP/VPN/endpoint config và change record |
| Lateral movement discovery | Nhiều PTR/SRV/internal queries khác baseline | Endpoint/process activity và authorized change |
| DGA-related behavior | Số lượng domains lạ, nhiều NXDOMAIN, biến động tên | Domain reputation, endpoint telemetry, business baseline |
| DNS tunneling nghi vấn | QNAME dài/khác thường, TXT/subdomain pattern, query volume | Resolver logs, endpoint process, DLP, classification |
| Cache poisoning/spoofing | Conflicting replies, source mismatch, bất thường về ID/timing | Trustworthy resolver logs, path, DNSSEC validation |
| DNS amplification | Response lớn, nhiều UDP queries, traffic bất đối xứng | Interface counters, firewall, upstream provider |
| DNS rebinding | Tên ban đầu trả public IP rồi private/link-local IP | Application SSRF controls và actual connected IP |
| DNSSEC validation failure | SERVFAIL cùng validator diagnostic | DNSSEC chain, clock, resolver policy |
| Exfil qua allowed DNS | Nhiều tên dưới domain đã có permission | App/data audit, DNS content handling |
| DNS outage/packet loss | Retry/timeouts, thiếu response tại sensor | Network path, resolver health, capture drop stats |

### 24.3. Bốn câu hỏi điều tra

1. **Điều gì thực sự được quan sát?** Query, response, record type, timestamp, flow, packet hay derived enrichment?
2. **Điều gì chỉ là suy luận?** Hostname ownership, end-user identity, mục đích, dữ liệu trong TLS, attack attribution?
3. **Có thể thiếu gì?** Cache, DoH, IPv6, packets dropped, asymmetric routing, NAT, resolver split view?
4. **Làm sao kiểm chứng độc lập?** Resolver logs, endpoint/EDR, CNI/firewall, cloud audit, application log và DNSSEC validator state?

## 25. DGA, NXDOMAIN spikes và tên miền entropy cao

**Domain Generation Algorithm (DGA)** là một khái niệm liên quan tới việc tạo nhiều tên miền theo quy luật; DNS telemetry có thể cung cấp dấu hiệu, nhưng **tên trông ngẫu nhiên không phải bằng chứng chắc chắn**.

### 25.1. Tín hiệu hữu ích

- Tăng số **unique QNAME** từ một thiết bị.
- NXDOMAIN ratio cao bất thường sau khi đã loại tests/typos.
- Nhiều labels dài với tập ký tự phân bố khác thường.
- Các domains mới xuất hiện ngoài bộ SaaS/business allowlist.
- Tần suất, phiên theo thời điểm và domain patterns giống nhau trên nhiều hosts.
- Queries diễn ra gần thời gian endpoint detection hoặc process execution lạ.
- Thay đổi resolver destination, query types, TTL patterns.

### 25.2. Entropy không phải chứng cứ cuối

Một công cụ có thể tính Shannon entropy trên labels, nhưng CDN cache keys, content-addressed names, tracking/verification records, anti-abuse tokens và build systems hợp lệ cũng tạo chuỗi dài khó đọc. Không dùng một ngưỡng entropy đơn độc để chặn domain production.

### 25.3. Ví dụ dữ liệu tổng hợp

~~~text
Source A (build runner)
  1000 queries/hour to artifact hashes under approved CI domain
  NXDOMAIN share: 1%
  Approved change ticket: yes
  Interpretation: likely legitimate automated lookup; verify scope

Source B (user laptop)
  900 queries/15min to hundreds of unknown names
  NXDOMAIN share: 88%
  New browser process: not confirmed
  Interpretation: investigate, not yet classify malware
~~~

Các giá trị là **giả định để luyện reasoning**. Phải đối chiếu policy, historical baseline, authorized scanners và endpoint/process logs.

### 25.4. Chú ý negative caching

Vì NXDOMAIN/NODATA có thể được cache, capture ở client side và upstream resolver có **tỷ lệ NXDOMAIN khác nhau**. Không so hai lớp như cùng một mẫu thống kê.

## 26. DNS tunneling và nghi vấn thất thoát dữ liệu

DNS tunneling có thể dùng DNS labels/records để chuyển metadata hoặc dữ liệu theo những cơ chế khác nhau. Phân tích phòng vệ nhằm tìm **sự lệch chuẩn trong query structure, volume, source identity và quan hệ với dữ liệu nhạy cảm**.

### 26.1. Các tín hiệu mang tính chỉ báo

| Feature | Ý nghĩa có thể | Nguồn false positive |
|---|---|---|
| QNAME dài gần giới hạn hoặc labels lạ | Có thể đang mã hóa dữ liệu trong tên | Tracking IDs, service discovery, DNSSEC-related names |
| Một parent domain chứa nhiều subdomains độc nhất | Có thể là kênh trao đổi dữ liệu | CDN, sharded services, verification automation |
| TXT queries/responses nhiều | Có thể trao đổi thông tin không thông thường | SPF/DKIM, domain verification, config/service discovery |
| QTYPE mix đổi đột ngột | Tác vụ mới hoặc traffic lạ | Migration, security tooling |
| Query rate và byte volume cao | Có thể gửi metadata nhiều lần | Monitoring agents, CI, service orchestration |
| Queries với response nhỏ/thất bại nhiều | Có thể query-driven channel hoặc scan | DNS misconfiguration, DGA, offline service |
| Một resolver ngoài corporate baseline | Có thể policy bypass | DoH client hợp lệ theo policy hoặc VPN khác |

### 26.2. Nên làm gì khi thấy tín hiệu?

1. Xác nhận DNS packets có plaintext hay DNS đã được mã hóa.
2. Xác định source workload/endpoint theo time-based mappings.
3. Nhóm QNAME theo registrable domain, nhưng tính đến public suffix/zone ownership.
4. Phân tích length distribution, labels, query types, RCODE, bytes/time.
5. Xác minh vendor SaaS, build system hoặc telemetry agent có thể tạo patterns đó.
6. Correlate DNS resolver logs, network flow, EDR/process tree và DLP/data access audit.
7. Nếu policy yêu cầu, dùng incident-approved containment theo đúng source, không block cả DNS resolver.
8. Lưu evidence có redaction và nêu uncertainty.

### 26.3. Vì sao một QNAME dài không đủ?

Một DNS TXT record có thể dài do SPF/DKIM/domain verification hợp pháp. Một service discovery system có thể tạo những tên kỹ thuật dài. Ngược lại, đối tượng tấn công có thể dùng truy vấn ngắn hơn và rate thấp. **Bất thường thống kê là tín hiệu để điều tra, không phải kết luận tuyệt đối.**

### 26.4. Encrypted DNS và visibility

Nếu client dùng DoH/DoT/DoQ, middlebox không thấy QNAME trong encrypted messages. Có thể dùng **endpoint-approved DNS telemetry, managed resolver logs hoặc EDR** thay vì cố suy payload từ TCP/443. Dữ liệu DNS nhạy cảm cần policy truy cập nghiêm ngặt.

## 27. DNS spoofing, cache poisoning và transaction consistency

DNS truyền thống qua UDP không tự xác thực cryptographically từng response. Một đối tượng có khả năng gửi packet giả hoặc tác động path có thể cố tạo response sai. **Phân tích phòng vệ cần kiểm tra consistency và DNSSEC/trust evidence**, không cung cấp hướng dẫn tấn công các resolver ngoài quyền.

### 27.1. Các chỉ báo cần điều tra

- Nhiều responses cho cùng query ID/tuple/time nhưng nội dung khác bất thường.
- Response từ IP/port không nằm trong resolver inventory được duyệt.
- Transaction ID/port/QNAME/QTYPE không tương quan query.
- Domain trả IP thay đổi sang private/unknown destination ngoài business plan.
- TTL hoặc answer chain khác baseline cùng resolver/zone view.
- DNSSEC validation failures, RRSIG/DS/DNSKEY changes theo thời điểm.
- Resolver config, DHCP DNS option hoặc VPN settings bị thay ngoài change window.

### 27.2. Phải loại trừ nguyên nhân hợp lệ

- CDN/load balancing trả nhiều IP theo resolver/region/EDNS ECS.
- Anycast resolver dùng nhiều backend.
- Split-horizon và geo-aware responses.
- Responses trễ sau client retry.
- UDP packet duplication/reordering.
- Resolver cache và TTL expiry.
- QNAME case randomization.
- NAT/proxy hoặc capture hai điểm khác nhau.

**Conflicting answers không tự bằng poisoning**. Muốn khẳng định compromise cần evidence từ trusted resolver logs, zone ownership/control-plane audit, DNSSEC verification, packet path và endpoint behavior.

### 27.3. DNSSEC giúp được gì?

DNSSEC validation có thể phát hiện dữ liệu DNS bị sửa trái với chain of trust phù hợp, nhưng không thay trust vào **zone operator**. Một signed zone đã được attacker kiểm soát hợp lệ ở level zone vẫn có thể phục vụ records không mong muốn. Kết hợp registrar MFA, DNS management RBAC, audit và certificate monitoring.

## 28. DNS amplification/reflection và open resolver risks

Trong một số kiểu DDoS, attacker có thể lạm dụng **DNS UDP reflection/amplification** nếu có thể giả mạo nguồn hoặc tận dụng resolver mở sai chính sách. Phân tích DNS packets giúp tìm bất đối xứng traffic và tính chất phản hồi lớn.

### 28.1. Góc nhìn phòng vệ

- Số DNS responses lớn hơn nhiều requests thấy được tại sensor.
- Băng thông UDP/53 đến một victim tăng đột biến.
- Nhiều source resolver addresses và patterns cùng destination.
- Trả lời lớn có EDNS/DNSSEC-related records.
- TCP/53 pattern khác, không tự được xem cùng UDP reflection.
- Interface counters tăng trong khi capture bị drop do quá tải.

### 28.2. Không diễn giải ratio đơn giản thành amplification chính xác

Nếu request payload 60 bytes và response 600 bytes, tỷ lệ payload minh họa là 10:1. **Tỷ lệ wire-level** còn phụ thuộc UDP/IP/L2 overhead và packet/fragment behavior. Một PCAP có thể không thấy query nếu sensor chỉ nằm phía victim; không tự khẳng định địa chỉ nguồn giả mạo chỉ từ absence of query.

### 28.3. Kiến trúc phòng ngừa

- Hạn chế recursion cho clients được ủy quyền.
- Tránh public open resolver khi không có business purpose.
- Rate limiting và source validation theo capability thiết bị.
- BCP 38/source address validation ở mạng có thẩm quyền.
- Theo dõi response size distributions, QTYPE mix, allowed clients và device drops.
- Hợp tác upstream ISP/CDN/DDoS provider theo incident playbook nếu có volumetric attack.

Không thử tạo reflection traffic lên host bên thứ ba; với lab, dùng **synthetic traffic nhỏ và isolated** để kiểm tra logic detection.

## 29. DNS rebinding, SSRF và bảo vệ private endpoints

**DNS rebinding** mô tả tình huống tên miền được resolve tới địa chỉ khác ở thời điểm khác nhằm khai thác trust boundary, thường đáng chú ý đối với application fetch URL, webhook callbacks hoặc browser-to-local interfaces.

### 29.1. Một đường đi khái niệm

~~~mermaid
flowchart TD
    IN[User-supplied URL] --> APP[URL Fetcher]
    APP --> CHECK{Validate scheme/hostname/destination}
    CHECK -->|Approved| RES[Resolver + real connected IP]
    RES --> NET[Network enforcement]
    NET --> API[Approved external endpoint]
    CHECK -->|Denied| DROP[Reject + log]
    RES -.Risk if actual address unchecked.-> PRIVATE[Private/admin/metadata endpoint]
~~~

### 29.2. Tại sao packet DNS đơn độc chưa đủ?

Một DNS response có thể đưa ra public IP ở lần đầu và private IP ở lần sau. Nhưng để kết luận SSRF thành công, phải thấy **application actually connected** tới endpoint bị hạn chế, và xác định browser/URL fetcher behavior, redirect và network policy. DNS packet không chứa HTTP path hoặc authorization.

### 29.3. Phòng vệ nhiều lớp

- Parse URL bằng thư viện chuẩn, normalize hostname và port.
- Giới hạn scheme/protocol được phép.
- Kiểm tra resolved IP **thực sự được dùng khi connect**, chống TOCTOU.
- Chặn loopback/link-local/private/metadata ranges ngoài quyền.
- Revalidate sau redirects, IDN/punycode và IPv4/IPv6 literals.
- Giữ TLS hostname/certificate verification.
- Egress proxy/NetworkPolicy/cloud firewall enforce không chỉ app validation.
- Audit theo source workload và data access, không chứa secrets trong log.

## 30. DNS anomaly timeline: phân biệt nguyên nhân ứng dụng, DNS hay mạng

Một số sự cố điển hình:
- DNS query được gửi nhưng không có response.
- Response tới chậm hoặc chỉ ở resolver dự phòng.
- NODATA cho AAAA nhưng A vẫn thành công.
- SERVFAIL chỉ ở validating resolvers.
- Query trả IP khác zone view.
- TCP fallback bị firewall chặn.
- DoH ứng dụng thành công, UDP/53 tới corporate resolver thất bại.
- DNS query thành công nhưng HTTPS sau đó failed.

### 30.1. Decision tree

~~~mermaid
flowchart TD
    START[Ứng dụng báo không truy cập được tên] --> CAP{Có thể thấy DNS transaction?}
    CAP -->|Không| COV[Kiểm tra cache/DoH/điểm capture/drop]
    CAP -->|Có query, không response| PATH[Check route/ACL/resolver/log/timestamp]
    CAP -->|Có response| RC{RCODE/Answer}
    RC -->|NXDOMAIN/NODATA| ZONE[Check QTYPE/zone/view/cache/SOA]
    RC -->|SERVFAIL/REFUSED| R[Check resolver policy/upstream/DNSSEC]
    RC -->|NOERROR + expected answer| NEXT[Check TCP/TLS/HTTP/app separately]
    RC -->|TC=1| T[Check TCP fallback + MTU]
~~~

### 30.2. Không sửa DNS khi thực tế lỗi là lớp sau

Nếu packet cho thấy NOERROR + địa chỉ mong đợi, nhưng HTTPS thất bại do certificate/route/authorization, thay DNS record chưa chắc giải quyết được gì. Correlate:
- Client IP/port và DNS resolver.
- QNAME/QTYPE, response A/AAAA/CNAME/TTL.
- Destination IP thực của kết nối TCP/QUIC.
- TLS SNI/server identity nếu có, proxy status và application logs.
- Firewall/CNI allowed/denied flow.
- Cloud endpoint/IAM và deployment change.

### 30.3. Latency waterfall

Một request có thể gồm:
1. Stub cache lookup.
2. DNS lookup tới recursive resolver.
3. TCP/TLS handshake hoặc QUIC setup.
4. HTTP/gRPC request processing.
5. Database/other downstream calls.

**DNS response latency nhỏ không bảo đảm toàn request latency nhỏ**; DNS là một phần của waterfall, cần trace/app instrumentation để nhìn đầy đủ.

## 31. DNS trong Kubernetes, container và cloud

### 31.1. Kubernetes DNS thường có nhiều điểm trung gian

Một Pod thường dùng resolver config trong /etc/resolv.conf, truy vấn dịch vụ cluster DNS, có thể dùng CoreDNS/kube-dns, NodeLocal DNSCache và upstream forwarders. Service discovery có thể sinh queries cho:
- service.namespace.svc.cluster-domain.
- Pod/Service name với search suffixes.
- External domains theo policy.
- A/AAAA và đôi khi SRV queries.
- Retry khi CoreDNS/Nodelocal cache bị quá tải.

**Tên miền cluster và cấu hình DNS có thể tùy biến**; không mặc định mọi cluster sử dụng một domain cố định hoặc cùng cổng/hook.

### 31.2. Search paths và ndots

Khi ứng dụng hỏi một tên chưa kết thúc bằng dấu chấm root hoặc có độ dài khác, stub resolver có thể thêm **search suffixes** theo cấu hình, tạo nhiều DNS queries hơn tưởng tượng. Ví dụ nó có thể thử tên nội bộ rồi tên ngoài. Điều này có thể ảnh hưởng latency, RCODE distribution và NXDOMAIN spikes mà không có tấn công.

Một DNS packet capture tại Pod có thể giải thích vì sao có rất nhiều queries tên tương tự sau thay đổi resolver config. Cần so **/etc/resolv.conf, ứng dụng, ndots policy và cache**.

### 31.3. Cloud managed DNS

Cloud private zones, VPC resolver, conditional forwarding và private endpoints có thể tạo **split-horizon answers**. Flow logs có thể không chứa QNAME; managed resolver logs có thể chứa QNAME nhưng có quyền/retention riêng. DNS query thành công không chứng minh IAM/resource access được cấp.

### 31.4. Pod IP vs node IP

NAT, NodeLocal DNSCache hoặc overlay có thể làm upstream resolver thấy source IP của node, không phải Pod. Muốn attribution cần capture tại Pod/CNI, resolver logs và Pod UID/IP allocation timeline. **Không gán danh tính user cho một source IP dùng chung**.

### 31.5. Các lệnh kiểm tra chỉ đọc trong Pod được cấp quyền

~~~bash
# Lệnh minh họa trên Pod lab, không thay đổi cấu hình
kubectl get pods -n orders-lab -o wide
kubectl exec -n orders-lab orders-api-lab-0 -- cat /etc/resolv.conf

# Chỉ nếu container lab có nslookup
kubectl exec -n orders-lab orders-api-lab-0 -- \
  nslookup api.orders.example
~~~

Không tự cài phần mềm vào production image hoặc bật privileged packet capture chỉ để nhìn DNS. Trong môi trường được quản trị, có thể dùng **approved CNI/observability sensor** hoặc synthetic PCAP.

## 32. Tương quan DNS với network telemetry và security controls

DNS packet analysis có giá trị cao hơn khi được liên kết với **NetFlow/IPFIX/sFlow, firewall, proxy, endpoint, IDS/IPS, service mesh và application logs**.

| Nguồn | Có thể làm sáng tỏ | Giới hạn |
|---|---|---|
| DNS packet | QNAME/QTYPE/RCODE/RR/TTL/EDNS khi plaintext | Không thấy user/payload HTTPS |
| Resolver logs | Cache/upstream/validation/policy decisions | Có thể mất original client sau forwarder |
| NetFlow/IPFIX/sFlow | IP/port/bytes/timing/network behavior | Không tự biết domain trên shared IP |
| Firewall/CNI logs | Denied/allowed flow, policy and NAT context | Không tự hiểu DNS QNAME |
| HTTP proxy | Destination host, auth identity, request operation nếu L7 | Không thấy plaintext nếu tunnel không decrypt |
| Endpoint/EDR | Process responsible, DNS client API use | Quyền và coverage của agent |
| Service mesh logs | Verified workload identities, L7 request outcomes khi qua datapath | Không bao phủ mọi traffic ngoài mesh |
| Cloud DNS/API audit | Zone/policy changes, private resolver use | Không thay packet-level correlation |
| Application trace/log | Business operation, downstream latency | Không tự biết một packet bị drop |
| IDS/IPS/NDR | Signature/anomaly alerts theo sensor | Có thể có false positives và gaps |

### 32.1. Ghép DNS với kết nối

~~~mermaid
sequenceDiagram
    participant A as Application
    participant R as Resolver
    participant F as Firewall / CNI
    participant S as SaaS API
    A->>R: Query A api.orders.example
    R-->>A: 198.51.100.25
    A->>F: TCP SYN -> 198.51.100.25:443
    F->>S: Allowed flow if policy permits
    S-->>A: TLS/application response
    Note over A,F: DNS answer alone not proof of successful TCP/TLS
~~~

### 32.2. Không ghép QNAME bằng “DNS answer gần nhất của IP”

Một CDN IP có thể phục vụ nhiều domains. Client có thể dùng cache hoặc DNS answer trước capture. Reverse DNS cũng không phải lời khai thật của HTTP Host/SNI. Nếu correlation không có explicit request IDs, authenticated identity hoặc endpoint process evidence, ghi **confidence** và chỉ coi domain association là suy luận.

### 32.3. Tách allow/deny

DNS query bị resolver trả REFUSED khác với firewall chặn UDP/53 (không có DNS response). Một HTTP 403 sau DNS success là lỗi lớp HTTP/app/authZ, không phải DNS RCODE. **Phải phân tích từng enforcement point riêng**.

## 33. Quyền riêng tư, lưu trữ PCAP và chuỗi bằng chứng

DNS query names có thể tiết lộ:
- Internal hostnames, usernames trong service naming, môi trường Dev/Prod.
- Domain bệnh viện/tài chính, hoạt động duyệt web hoặc SaaS sử dụng.
- API partner, product codenames và hệ thống quản trị nội bộ.
- TXT tokens/verification strings nếu ứng dụng hoặc zone cấu hình sai.
- Một phần nội dung truy cập qua sampled payload/capture ở layer khác.

### 33.1. Data minimization

- Chỉ capture đúng host/interface/time window cần điều tra.
- Dùng BPF filter phù hợp, nhưng không quên encrypted DNS/tunnels có thể nằm ngoài filter.
- Nếu cần raw PCAP, mã hóa lưu trữ và hạn chế quyền đọc.
- Xuất báo cáo chỉ chứa QTYPE/RCODE/latency/aggregates nếu mục đích cho phép.
- Redact QNAME nội bộ và địa chỉ khi chia sẻ cho đội ngoài scope.
- Phân biệt sample/dữ liệu giả với incident evidence.
- Có retention, data residency và quy trình xóa theo chính sách của tổ chức.

### 33.2. Chuỗi bằng chứng

Khi phân tích phục vụ incident:
1. Ghi nguồn file, device/sensor và người thu.
2. Ghi capture UTC start/end, interface, link-layer type, filter, snaplen.
3. Tính/check file checksum bằng quy trình được duyệt (không sửa file gốc).
4. Lưu bản gốc read-only trong kho có kiểm soát.
5. Thực hiện phân tích trên bản sao, ghi tool version/filter.
6. Ghi nhận packet loss, capture gaps và timestamp uncertainty.
7. Lưu kết luận gắn packet numbers/flows/time windows.
8. Đảm bảo quyền truy cập và audit xem/đưa dữ liệu ra ngoài.

### 33.3. Sampled payload khác flow metadata

Nếu capture có packet đầy đủ, nó có thể chứa nhiều dữ liệu ngoài DNS; một PCAP lọc port 53 vẫn có thể chứa TXT payload hoặc thông tin nhạy cảm. Không chia sẻ raw file qua kênh công khai với lý do “chỉ là packet header”.

## 34. Đảm bảo chất lượng capture và tránh false negatives

### 34.1. Những cách mất dữ liệu

| Nguyên nhân | Tác động | Kiểm tra |
|---|---|---|
| Mirror/SPAN overload | Bỏ một số packets/hướng | Capture drop counters/switch telemetry |
| Snaplen quá ngắn | DNS payload/RR bị cắt | Frame captured length vs original length |
| Capture filter quá hẹp | Chỉ UDP/53, bỏ TCP/DoH/IPv6 | Filter inventory/protocol paths |
| NIC offload/virtual interfaces | Packet shape/checksum khác wire | Host capture context/driver settings |
| Asymmetric routing | Chỉ một chiều DNS transaction | Route map/sensors khác |
| Resolver cache | Không có upstream query | Cache metrics/stub-side observation |
| DNS encrypted | Không thấy QNAME ở middlebox | Endpoint/resolver logs |
| NAT/forwarding | Không thấy original client IP | NAT/DHCP/Pod UID time mapping |
| Packet timestamp skew | RTT âm/phi lý | Clock sync/timestamp source |
| PCAP corruption/truncation | Decode malformed/missing records | File integrity và parser diagnostics |
| Capture process overloaded | Kernel/agent drop packets | Capture tool performance counters |
| Clock/timezone confusion | Sai correlation với logs | UTC normalization |

### 34.2. Đừng đánh đồng “checksum incorrect” với tấn công

Host captures trước khi NIC xử lý checksum offload có thể báo checksum không đúng trên packet được quan sát ở software path. Phải xem **điểm capture/offload settings và evidence từ wire/TAP** trước khi kết luận packet bị giả mạo hoặc hỏng thực tế.

### 34.3. Packet duplication

SPAN hoặc capture tại nhiều interfaces có thể tạo duplicate packets, làm count queries và RTT matches sai. Cần xác định source/direction, packet hash với time window khi cần và giữ provenance; không xóa mọi duplicate theo DNS ID vì legitimate DNS retries cũng có thể giống nội dung.

## 35. Quy trình thực hành lab với DNS packet

Bài lab an toàn nên dùng **mạng giả lập và PCAP synthetic hoặc đã được cấp quyền**; các mốc dưới đây là **kịch bản kiểm thử, không phải xác nhận đã chạy**.

### 35.1. Chuẩn bị

1. Có client lab, recursive resolver lab và (nếu cần) authoritative server lab.
2. Có DNS test zone thuộc quyền sở hữu/được cấp phép, tránh ảnh hưởng public DNS.
3. Có clock đồng bộ và capture tại client/recursive resolver.
4. Có ứng dụng đọc PCAP (Wireshark/TShark) đúng version.
5. Có network path policy (UDP/53 và TCP/53), không chạy trên production ngoài change window.
6. Có mock domain trong .example hoặc DNS zone tự quản lý, dữ liệu giả và không có real tokens.
7. Có bản ghi expected QNAME/QTYPE/RCODE, TTL và request timing.
8. Có storage cho PCAP, quyền truy cập, retention và redaction.

### 35.2. Bài tập từ dễ đến khó

| Bước | Nhiệm vụ | Kỹ năng |
|---|---|---|
| L1 | Mở synthetic PCAP, phân biệt query/response | QR, ID, tuple |
| L2 | Decode A/AAAA answers và TTL | QTYPE, RDATA |
| L3 | Decode CNAME chain, NS referral và glue | Sections |
| L4 | Phân tích NXDOMAIN vs NODATA | RCODE, Authority SOA |
| L5 | Xem EDNS OPT và DO bit | EDNS0 |
| L6 | Đọc TC response và TCP fallback | UDP/TCP |
| L7 | Phân tích DNSSEC records/flags | Không nhầm validation |
| L8 | Ghép transactions/retry và RTT | Correlation/time windows |
| L9 | Đối chiếu capture trước/sau NAT | Source attribution |
| L10 | Phân biệt normal DNS và DoH/DoT flow visibility | Encryption boundary |
| L11 | Phân tích DNS query burst/length distribution | Detection vs false positives |
| L12 | Viết báo cáo evidence, uncertainty và privacy | Incident discipline |

### 35.3. Tiêu chí nghiệm thu lab

- Tất cả kết luận có packet number/time/rule rõ.
- Không dùng DNS ID một mình làm authentication.
- Có phân biệt IP/TCP/UDP/DNS message và TCP prefix.
- Không báo DNSSEC secure chỉ do AD=1 ngoài trust context.
- Không gọi NXDOMAIN khi thực tế NOERROR/NODATA.
- Có kiểm tra sampling/capture drops/DoH coverage.
- Đã redaction QNAME và hostnames nhạy cảm.
- Có ít nhất một **positive** và một **negative** test đối với policy DNS ở lab.
- Có ghi rõ **NOT_RUN** cho bất kỳ test nào chưa thực hiện.

## 36. Ma trận kiểm thử giải mã DNS packet và quan sát mạng

Các dòng dưới đây là **kế hoạch nghiệm thu**, không phải tuyên bố các phép thử đã được thực thi. Mỗi case cần ghi **environment, source, destination, PCAP timestamp, capture point, protocol, DNS ID/tuple, expected vs actual, evidence reference, status PASS/FAIL/NOT_RUN/BLOCKED**. Tests can thiệp firewall/zone/resolver chỉ thực hiện trong lab cô lập hoặc change window được duyệt.

| ID | Kịch bản | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| D01 | Plain DNS A query qua UDP/53 | Decode header và QTYPE=A | QNAME/ID/tuple |
| D02 | Plain DNS AAAA query | Thấy IPv6 RR hoặc negative response đúng type | QTYPE/Answer |
| D03 | Query và response cùng ID | Ghép đúng tuple/time/question | Transaction record |
| D04 | Hai queries đồng thời dùng lại ID | Không ghép nhầm theo ID trần | Five-tuple/QNAME |
| D05 | Response tới sau retry | Không tính response như request mới | Timing/retry evidence |
| D06 | Captured response thiếu request | Đánh dấu unmatched, không tự kết luận spoofing | Capture window/route |
| D07 | DNS query QDCOUNT=1 | Decode QNAME/QTYPE/QCLASS | Header/Question |
| D08 | Answer có CNAME và A records | Đếm đúng loại RR, không nhầm ANCOUNT thành số IP | Answer list |
| D09 | Authority NS referral | Phân biệt delegation với final answer | Authority/Additional |
| D10 | Additional glue A/AAAA | Không coi glue là validated application destination | RR names/types |
| D11 | Compression pointer C0 0C hợp lệ | Decode đúng offset 12 từ DNS start | Raw hex/decoded name |
| D12 | Compression pointer malformed synthetic | Parser báo lỗi an toàn, không đọc ngoài bounds | Decoder diagnostics |
| D13 | TTL=60 trên A RR | Đơn vị giây được hiển thị | RR TTL |
| D14 | Negative cached response | Hiểu TTL/context, không nhầm name existence | SOA/TTL |
| D15 | RCODE=NOERROR, Answer trống cho requested type | Phân loại NODATA đúng điều kiện | RCODE/Authority/QTYPE |
| D16 | RCODE=NXDOMAIN | Không tự coi như SERVFAIL hoặc NODATA | Header RCODE |
| D17 | RCODE=SERVFAIL | Xác định failure, chưa gán root cause | RCODE/upstream logs |
| D18 | RCODE=REFUSED | Correlate resolver policy | RCODE/resolver audit |
| D19 | Query A rồi AAAA | Không mặc định AAAA là retry của A | QTYPE/time |
| D20 | RD=1 và RA=1 | Không suy cache miss/lookup upstream | Flags/cache info |
| D21 | AA=1 ở authoritative reply | Không tự gán DNSSEC secure | Flags/trust context |
| D22 | EDNS OPT trong Additional | Decode TYPE=41/UDP size/version | Additional OPT |
| D23 | EDNS DO=1 | Không tự gắn AD=1 hoặc validated | OPT flags |
| D24 | EDNS extended RCODE (synthetic) | Decode kết hợp header + OPT | EDNS/RCODE |
| D25 | EDNS option unknown hợp lệ | Không làm crash decoder; giữ provenance | Option code/length |
| D26 | Response TC=1 | Thấy truncation DNS flag | Header TC |
| D27 | TCP fallback sau TC=1 | Thấy TCP/53 và DNS length prefix | TCP stream |
| D28 | DNS TCP message qua nhiều segments | TCP reassembly đủ trước decode | Reassembly events |
| D29 | TCP message chứa nhiều DNS messages | Parser phân biệt từng prefix/message | Stream boundaries |
| D30 | Snaplen cắt DNS response | Đánh dấu capture-truncated, không gán TC | Captured/original lengths |
| D31 | UDP IP fragments hợp lệ | Reassemble hoặc ghi rõ thiếu fragments | Fragment metadata |
| D32 | UDP response lớn thất bại theo MTU trong lab | Kiểm tra fragment loss/TCP fallback | IP/ICMP/firewall |
| D33 | DNSSEC RRSIG/DNSKEY/DS present | Ghi nhận records, không tự xác nhận chữ ký | RR types |
| D34 | Validator DNSSEC báo failure | Correlate SERVFAIL với validated diagnostics | Resolver validation logs |
| D35 | AD=1 qua stub path thiếu trusted transport | Không tự suy client đã xác thực end-to-end | Trust path |
| D36 | DoT TCP/853 | Ghi nhận encrypted DNS transport, không đọc QNAME | TLS/flow evidence |
| D37 | DoH HTTPS/443 | Không suy queried domain từ resolver hostname | Endpoint/resolver logs |
| D38 | DoQ UDP/853 | Phân biệt QUIC từ UDP DNS plaintext | QUIC/flow metadata |
| D39 | 0x20 case randomization | Compare names không nhầm domain khác | Raw QNAME/transaction |
| D40 | Split-horizon A response khác nhau | Nêu resolver/view thay vì poisoning | Resolver/VPN context |
| D41 | Client stub/cache hit | Thiếu packet upstream không bị coi là outage | Cache/endpoint logs |
| D42 | NodeLocal DNSCache trong Kubernetes | Map source Pod→node cache→CoreDNS đúng | Pod UID/flow |
| D43 | /etc/resolv.conf search suffix/ndots | Giải thích chuỗi queries cùng tên gần giống | Stub config/PCAP |
| D44 | IPv6 packet carrying DNS UDP/53 | Bắt đủ IPv6 addresses/flow | IPv6 packet details |
| D45 | NAT thay source port DNS query | Correlate bằng mapping/time | NAT logs/two captures |
| D46 | Asymmetric DNS return path | Không kết luận không response nếu sensor chỉ một chiều | Routing/sensor coverage |
| D47 | Wireshark display filter query | Chỉ hiển thị packet thích hợp | Field-filter result |
| D48 | tcpdump BPF port-53 filter | Không coi kết quả là toàn bộ encrypted DNS | Filter scope |
| D49 | TShark export timestamp/ID/QNAME/RCODE | Fields đúng parser/version | Structured output |
| D50 | Synthetic DNS NXDOMAIN burst | Detector phân biệt test/misconfig/DGA hypothesis | Endpoint/app changes |
| D51 | Synthetic long QNAME burst | Báo anomaly, không tự gán exfil confirmed | Name lengths/process audit |
| D52 | Resolver response source mismatch | Kiểm tra spoofing hypothesis có loại trừ NAT | Tuple/resolver inventory |
| D53 | Approved DNS resolver bị mất kết nối | Quan sát timeout/retry/secondary behavior | Query timeline |
| D54 | Firewall deny UDP/53 nhưng TCP/53 được phép trong lab | Phân biệt transport path | Firewall/packet captures |
| D55 | Capture agent dropped packets | Có coverage warning, không overclaim completeness | Capture stats |
| D56 | PCAP chứa sensitive names | Redaction/quyền truy cập đúng trước chia sẻ | Security data review |

### 36.1. PASS là gì?

Không đánh dấu PASS chỉ vì:
- DNS ID trùng nhưng tuple/time/QTYPE khác.
- Packet được nhận mà header/sections decode lỗi.
- Query không thấy response nhưng sensor thiếu chiều.
- Không thấy plaintext DNS vì tất cả queries chuyển DoH.
- TC=1 nhưng TCP fallback bị firewall chặn.
- DNSSEC RRSIG có mặt nhưng validator báo bogus.
- Chỉ nhìn một DNS response mà không kiểm tra split-horizon resolver.
- Dữ liệu đã được redact ở dashboard nhưng PCAP gốc vẫn mở public.
- Một alert phát hiện long QNAME nhưng chưa kiểm tra false positives.
- Không có packet drop counter hoặc capture metadata.

**Kết quả phù hợp cần có cả protocol accuracy, visibility scope và evidence quality.**

## 37. Mười tám tình huống phân tích

### Tình huống A — DNS query A thành công, HTTPS vẫn thất bại

PCAP thấy NOERROR với địa chỉ mong đợi; app nhận TLS certificate validation error.

**Phân tích:** DNS resolution thành công nhưng tầng TLS không đạt. Kiểm tra SNI/server certificate/trust chain, proxy và destination IP, không đổi DNS record bừa.

### Tình huống B — Cùng hostname trả IP private và public

Một client trong VPN nhận địa chỉ private; client ngoài Internet nhận public.

**Phân tích:** split-horizon DNS hoặc conditional forwarding có thể là thiết kế. So resolvers, VPN state, zone view và policy trước khi quy kết DNS hijack.

### Tình huống C — QTYPE AAAA không có Answer

Một resolver trả NOERROR, ANCOUNT=0 với Authority SOA cho AAAA, nhưng A vẫn có.

**Phân tích:** thường là NODATA cho AAAA, không phải NXDOMAIN. Cần QTYPE và các section/negative caching.

### Tình huống D — SERVFAIL chỉ tại một validating resolver

Cùng domain dùng nonvalidating resolver thành công; validating resolver trả SERVFAIL.

**Phân tích:** cần kiểm tra DNSSEC validation errors, chain of trust, clock và resolver upstream; không khẳng định DNSSEC là lỗi khi chưa có validator diagnostics.

### Tình huống E — Câu trả lời lớn bị TC=1

UDP DNS response bật TC; client không thử TCP do firewall chặn.

**Phân tích:** DNS hoạt động một phần, app có thể timeout. Kiểm tra TCP/53 policy, EDNS buffer, fragmentation và path MTU.

### Tình huống F — Wireshark báo malformed response

PCAP có captured length nhỏ hơn original length vì snaplen 96 bytes.

**Phân tích:** khả năng capture truncation, không mặc định server tạo malformed bytes. Bảo toàn evidence và tạo capture đúng scope/snaplen trong lab.

### Tình huống G — DNS header bắt đầu bằng số lạ

Một analyst giải mã DNS-over-TCP lấy 2-byte length prefix làm ID.

**Phân tích:** bỏ qua TCP length prefix sau khi stream reassembly, rồi mới đọc DNS header 12 byte. Kiểm tra message boundaries.

### Tình huống H — Pointer C0 0C được đọc thành tên lỗi

DNS response có compressed NAME C0 0C, decoder thủ công coi octet C0 là label length.

**Phân tích:** high bits 11 là pointer, low 14 bits là offset từ đầu DNS message. Có bounds/cycle checks.

### Tình huống I — Query DNS đến từ node thay vì Pod

CoreDNS upstream capture thấy source IP node; Pod thực sự hỏi local cache.

**Phân tích:** NodeLocal DNSCache hoặc forwarder có thể thay source. Dùng Pod UID, CoreDNS logs, CNI records đúng thời điểm; không gán node IP là toàn bộ client identity.

### Tình huống J — Laptop hỏi nhiều subdomains khó đọc

Laptop sau bản cập nhật browser hỏi các tên kỹ thuật dài; detector báo DGA.

**Phân tích:** domain labels và NXDOMAIN rate là chỉ báo cần review, không kết luận. Đối chiếu application process, approved vendors, historical baseline.

### Tình huống K — TXT queries tăng bất thường

Một CI runner hỏi TXT records khi thực hiện domain verification cho release.

**Phân tích:** xác minh change ticket và job logs; không gắn mọi TXT traffic là tunneling. Nếu sai policy, điều tra data access/resolver logs.

### Tình huống L — DNSSEC AD=1 trong response

Một resolver trả AD=1 qua plaintext UDP và analyst kết luận đường client→resolver đã an toàn.

**Phân tích:** AD là signaling từ resolver theo semantics, không tự bảo vệ transport. Cần trust boundary và local DNSSEC validation nếu cần bằng chứng độc lập.

### Tình huống M — UDP/53 không còn packet sau đổi browser config

Browser dùng DoH tới resolver được cấu hình; Wireshark port-53 filter không thấy gì.

**Phân tích:** không suy DNS đã ngừng hoạt động. Xem endpoint/resolver policy, DoH endpoint flows và approved logs.

### Tình huống N — Một transaction có hai responses khác nhau

Capture thấy hai responses cùng ID ở hai thời điểm, một từ resolver chính, một từ resolver khác.

**Phân tích:** kiểm tra query retries, source/destination tuple, NAT, alternative resolvers, timing và DNSSEC/trust evidence. Không coi cùng ID là proof of poisoning.

### Tình huống O — DNS request success nhưng không thấy TCP SYN

Ứng dụng hỏi DNS rồi hủy request trước khi kết nối.

**Phân tích:** DNS lookup không đảm bảo service đã được truy cập. Correlate app trace, socket/flow logs, cache và user cancellation.

### Tình huống P — NXDOMAIN spike sau thay ndots

Sau nâng cấp Kubernetes Pod resolver configuration, một short hostname sinh nhiều search-suffix queries thất bại.

**Phân tích:** nguyên nhân có thể là search domains/ndots và cache, không mặc định DGA. So /etc/resolv.conf và actual QNAME sequence.

### Tình huống Q — Cloud flow logs thấy DNS nhưng PCAP không thấy query

Cloud VPC logs có UDP/53 flow trong region khác; capture chỉ ở một node.

**Phân tích:** thiếu coverage/điểm quan sát và network route. Flow logs không chứa DNS QNAME; cần capture/resolver logs ở đúng điểm được cấp quyền.

### Tình huống R — Bắt DNS từ SPAN khi mạng nghẽn

PCAP chỉ có responses rời rạc, SPAN port báo drops khi traffic tăng.

**Phân tích:** dữ liệu thiếu; không tính server responsiveness dựa unmatched response count. Dùng switch drop counters, resolver metrics và capture được thiết kế lại.

## 38. Troubleshooting: đọc packet theo triệu chứng

### 38.1. Không thấy DNS query

**Có thể do:** app cache, system cache, DoH/DoT/DoQ, packet nằm ở interface khác, capture filter quá hẹp, VPN/tunnel, IPv6 hoặc source chưa thực sự gọi DNS.

**Kiểm tra:** app resolver config, endpoint DNS logs, protocol paths, PCAP metadata, CNI/firewall flows. Không mở privileged capture ngoài quyền để “thấy hết”.

### 38.2. Thấy query nhưng không có response

**Có thể do:** resolver down/timeout, UDP/53 blocked, packet loss, asymmetric route, capture drop hoặc response ở interface khác.

**Kiểm tra:** resolver health, firewall allow/deny, routes, capture drops, retry timeline và secondary resolvers. Không gọi đây là NXDOMAIN vì **NXDOMAIN là một response có RCODE=3**.

### 38.3. Thấy response nhưng không ghép được query

**Có thể do:** capture bắt đầu giữa transaction, NAT, source port rewrite, ID reused, retry, SPAN thiếu chiều, TCP stream từ trước.

**Kiểm tra:** full tuple/time/QNAME, sensor location, NAT logs, capture window và protocol decoder.

### 38.4. Response NOERROR nhưng không có A

**Có thể do:** NODATA, CNAME chain cần truy vấn tiếp, query loại khác, policy, Additional/Authority chứa metadata.

**Kiểm tra:** QTYPE, Answer TYPE, Authority SOA, CNAME resolution, application dual-stack behavior.

### 38.5. NXDOMAIN chỉ ở một resolver

**Có thể do:** split DNS, negative cache, stale forwarder, blocking policy hoặc zone config.

**Kiểm tra:** resolver identity, zone view, TTL, client VPN/network, approved change ticket. Không flush caches toàn doanh nghiệp nếu chưa có owner/rollback.

### 38.6. SERVFAIL tăng sau DNSSEC change

**Có thể do:** DS/DNSKEY/RRSIG chain, signature validity dates, clock skew, resolver DNSSEC policy, network upstream hoặc unrelated resolver outage.

**Kiểm tra:** validator error logs, DNSSEC trust chain, time sync, authoritative reachability, EDNS/TCP. Không vô hiệu hóa DNSSEC validation toàn bộ như cách sửa đầu tiên.

### 38.7. Query lớn chỉ lỗi qua VPN

**Có thể do:** MTU/tunnel overhead, IP fragmentation loss, EDNS UDP buffer hoặc TCP fallback bị chặn.

**Kiểm tra:** TC, OPT UDP size, fragments, ICMP/PMTUD, TCP/53 handshake và VPN route. Thay đổi phải được test trên lab hoặc change window.

### 38.8. Wireshark báo malformed EDNS

**Có thể do:** OPT option length không hợp lệ, packet thật malformed, capture snaplen, dissector cũ hoặc TCP reassembly thiếu.

**Kiểm tra:** raw OPT TYPE/CLASS/TTL/RDLEN, option boundaries, capture length, Wireshark version. Không đổi binary bytes để “sửa” evidence.

### 38.9. DNS traffic xuất hiện trên TCP/443

**Có thể là:** DoH trong HTTPS, proxy API request hoặc HTTPS thông thường, không thể xác định chỉ từ port/5-tuple.

**Kiểm tra:** endpoint/resolver app config, approved proxy logs, DNS client instrumentation. Không tự công bố QNAME suy luận từ IP CDN.

### 38.10. DNS query count tăng sau thêm CoreDNS cache

**Có thể do:** thay cache TTL, search suffix, app retry, cache miss, upstream resolver behavior hoặc pipeline đếm trùng giữa node/forwarder.

**Kiểm tra:** source layer, DNS cache hit/miss, per-Pod query counts, dashboards union/sampling và version change.

### 38.11. TShark filter không tìm ra DNS response

**Có thể do:** sai field name/version, display filter áp QTYPE không khớp, TCP reassembly chưa có hoặc file chỉ lưu partial capture.

**Kiểm tra:** thử filter rộng dns, xác minh dissector, kiểm tra packet details/QTYPE, version và capture metadata.

### 38.12. Response latency âm hoặc quá lớn

**Có thể do:** clock skew, timestamps từ sensors khác nhau, query/response ghép sai ID, duplicated packets hoặc response tới sau timeout/retry.

**Kiểm tra:** một sensor/same clock domain, full tuple, time normalization và retry chains. Không xuất p95/RTT trước khi loại ambiguous transactions.

## 39. Runbook điều tra sự cố DNS theo từng giai đoạn

### Giai đoạn A — Xác định mục tiêu và nguồn bằng chứng

1. Ghi **thời điểm UTC, incident ticket, source client/Pod/namespace, target domain và owner**.
2. Xác định ứng dụng báo **resolution failure**, latency hay error lớp TCP/TLS/HTTP sau DNS.
3. Chọn observation point gần source và resolver, tránh suy từ một sensor sai tầng.
4. Xem quyền thu thập và data classification trước khi đọc PCAP.
5. Kiểm tra PCAP integrity, start/end, filters, snaplen và dropped packet count.
6. Ghi tool versions, protocol dissector và timezone.
7. Giữ bản gốc read-only; phân tích bản sao.

### Giai đoạn B — Giải mã transaction

1. Xác định outer IP/port/protocol/IPv4-IPv6 và NAT nếu có.
2. Đọc DNS ID, QR, opcode, RD/RA/AA/TC/AD/CD, RCODE.
3. Đọc QNAME/QTYPE/QCLASS và toàn bộ RR types/TTLs.
4. Kiểm tra EDNS OPT, advertised UDP size, DO và extended RCODE khi có.
5. Correlate query/response theo full tuple/time/question.
6. Phân biệt retry, TCP fallback, fragments và capture truncation.
7. Tính elapsed time chỉ cho matched transactions có quality đủ.
8. Nếu DNS mã hóa, dùng nguồn endpoint/resolver logs được phê duyệt.
9. Phân loại response NOERROR+Answer, NODATA, NXDOMAIN, SERVFAIL, REFUSED hoặc no response.

### Giai đoạn C — Đối chiếu nguyên nhân

- **No response:** firewall/route/resolver/capture loss.
- **NXDOMAIN/NODATA:** zone, QTYPE, cache, split-horizon, search suffix.
- **SERVFAIL:** resolver health, forwarding, DNSSEC validator/clock.
- **TC/fragment:** EDNS buffer, MTU, TCP fallback/ACL.
- **Conflicting answers:** resolver identity, geo/load balancing, DNSSEC, zone changes.
- **Suspicious QNAME:** app baseline, endpoint/EDR, DNS logs và DLP.
- **DNS success nhưng app fail:** TCP/TLS/HTTP/authZ và cloud/mesh logs.
- **Coverage gap:** DoH/DoT/DoQ, cache, IPv6, VPN, SPAN drops.

### Giai đoạn D — Khắc phục có kiểm soát

1. Chuẩn bị fix theo **lớp gây lỗi thực tế**, không mở firewall DNS toàn Internet tùy tiện.
2. Với zone/cache changes, có owner và rollback.
3. Với MTU/TCP fallback, xác minh app/network security impact.
4. Với DNSSEC failure, xử lý chain/clock/authoritative issue; không tắt validation toàn cục.
5. Với resolver compromise nghi vấn, làm theo incident response approval, không sửa bỏ chứng cứ.
6. Với DNS abuse, giới hạn policy theo source/workload thay vì chặn toàn resolver nếu không cần.
7. Theo dõi legitimate traffic, RCODE rates, RTT và service SLO sau thay đổi.

### Giai đoạn E — Xác minh và hậu kiểm

- Chạy positive tests cho tên/record types cần thiết.
- Chạy negative tests cho zone/policy/SSRF boundaries.
- Xác minh UDP/TCP, IPv4/IPv6, EDNS và encrypted DNS paths theo scope.
- Xem capture coverage, DNSSEC validator status và resolver cache behavior.
- So timestamps/metrics với application error rates.
- Redact incident artifacts và lưu evidence access logs.
- Ghi root cause, missed signals, owner, deadline và regression tests.

**Không đóng incident chỉ vì một lệnh nslookup chạy thành công** nếu user-facing HTTPS vẫn lỗi hoặc security boundary còn bị bypass.

## 40. Các sai lầm thường gặp khi phân tích DNS packet

1. **Coi DNS packet chứa mọi dữ liệu ứng dụng.** DNS chỉ là một phần của hệ thống.
2. **Đọc UDP port 53 là DNS hợp lệ không cần decode.** Port không đủ.
3. **Bỏ DNS trên TCP/53.** Không có TCP fallback thì lookup lớn có thể lỗi.
4. **Nhầm TCP 2-byte length prefix thành DNS ID.** Sai offset.
5. **Giả định một TCP packet chứa trọn DNS message.** Có segmentation.
6. **Giả định Ethernet header luôn dài 14 bytes.** VLAN/tunnel/link type khác.
7. **Không đọc IPv6.** Bỏ DNS dual-stack hoặc AAAA queries.
8. **Ghép query/response chỉ theo 16-bit ID.** Có collision/reuse.
9. **Coi A và AAAA cùng tên là retry.** Hai câu hỏi khác nhau.
10. **Coi một response không ghép được là poisoning.** Capture có thể thiếu.
11. **Coi DNS response success là HTTP connection success.** Lớp khác.
12. **Coi RCODE=0 luôn có địa chỉ A.** Có NODATA/CNAME/other RRs.
13. **Coi NXDOMAIN và SERVFAIL là một.** Bản chất khác.
14. **Coi packet timeout là NXDOMAIN.** NXDOMAIN là response code.
15. **Không đọc Authority SOA khi gặp negative response.** Bỏ negative caching.
16. **Coi TTL cao nghĩa domain an toàn.** TTL chỉ về cache semantics.
17. **Coi CNAME như HTTP redirect.** Khác layer.
18. **Coi ANCOUNT là số IP.** Answer có nhiều TYPE.
19. **Coi OPT là ordinary zone RR.** Đây là EDNS pseudo-RR.
20. **Coi OPT TTL là TTL cache.** Có extended RCODE/version/flags.
21. **Coi DO=1 là DNSSEC validated.** Chỉ request DNSSEC-related content.
22. **Coi AD=1 đáng tin trên mọi untrusted path.** Cần trust context.
23. **Coi RRSIG presence chứng minh chữ ký hợp lệ.** Cần validation.
24. **Đọc C0 0C như label dài 192.** Là compression pointer.
25. **Bỏ pointer bounds/cycle checks.** Parser có thể lỗi.
26. **Nhầm DNS TC=1 với PCAP snaplen truncation.** Hai hiện tượng khác.
27. **Coi IP fragments là DNS packets độc lập.** Cần reassembly.
28. **Bỏ qua EDNS UDP payload size khi response lớn lỗi.** Có MTU risk.
29. **Coi DNS chỉ dùng UDP.** TCP quan trọng.
30. **Coi DoH/DoT/DoQ plaintext trên wire.** Payload được mã hóa.
31. **Suy queried domain từ SNI của DoH resolver.** SNI là resolver host.
32. **Coi mọi encrypted DNS là tấn công.** Còn quyền riêng tư/chính sách.
33. **Coi Wireshark display filter là tcpdump BPF syntax.** Khác ngôn ngữ.
34. **Dùng live capture trái quyền để debug.** Vi phạm bảo mật/privacy.
35. **Coi PCAP thiếu query là không có cache hit hoặc DoH.** Visibility gap.
36. **Coi SPAN capture 100% đầy đủ.** Có drops.
37. **Không ghi timestamp/timezone/filter/snaplen.** Khó tái lập.
38. **So RTT từ hai sensors chưa đồng bộ.** Có clock skew.
39. **Không kiểm tra NIC checksum offload.** False checksum errors.
40. **Coi domain dài là DNS tunneling confirmed.** Có false positives.
41. **Coi NXDOMAIN spike là DGA confirmed.** Có search suffix/misconfiguration.
42. **Coi TXT queries tự động là exfil.** Có SPF/DKIM/verification.
43. **Coi DNS response không có reverse query là attack.** Path capture thiếu.
44. **Tin reverse DNS tên là identity host.** PTR không là authentication.
45. **Gắn QNAME theo CDN IP từ DNS gần nhất.** Shared IP/TTL.
46. **Không xét NAT/NodeLocal DNSCache.** Gán source sai.
47. **Coi flow DNS trong NetFlow bằng nội dung QNAME.** Flow metadata không tự chứa DNS payload.
48. **Không phân biệt spoofing với split-horizon/CDN.** Có lý do hợp lệ.
49. **Mở mọi TCP/UDP 53 để chữa một resolver fail.** Mở rộng attack surface.
50. **Chia sẻ PCAP raw cho mọi người.** Có thể lộ internal names và identifiers.

## 41. Checklist phân tích DNS packet

- [ ] Có mục tiêu điều tra, owner và phạm vi capture được cấp quyền.
- [ ] Chọn đúng observation point, direction và network namespace.
- [ ] Xác định capture file loại PCAP/PCAPNG và link-layer type.
- [ ] Ghi start/end UTC, tool version, snaplen, filters và packet drops.
- [ ] Bảo quản file gốc và dùng bản sao để phân tích.
- [ ] Có quyền xử lý dữ liệu DNS nhạy cảm và retention policy.
- [ ] Không chỉ lọc UDP/53 nếu cần TCP hoặc encrypted DNS.
- [ ] Phân biệt UDP/TCP DNS, DoH, DoT, DoQ và tunnel visibility.
- [ ] Với TCP, đã xử lý length prefix và stream reassembly.
- [ ] Đọc đúng DNS header 12 byte và network byte order.
- [ ] Correlate ID cùng tuple, QNAME/QTYPE, time window.
- [ ] Phân biệt query/response bằng QR.
- [ ] Đọc RD/RA/AA/TC/AD/CD với đúng semantics.
- [ ] Đọc RCODE và extended RCODE nếu có EDNS.
- [ ] Phân biệt NOERROR/NODATA, NXDOMAIN, SERVFAIL, REFUSED.
- [ ] Đọc QNAME length labels và pointer compression an toàn.
- [ ] Đọc TYPE/CLASS/TTL/RDLENGTH/RDATA theo loại RR.
- [ ] Không coi ANCOUNT là số IP.
- [ ] Phân biệt referrals, glue và authoritative answer.
- [ ] Cân nhắc caches, TTL, forwarders và split-horizon.
- [ ] Cân nhắc search suffix/ndots và A/AAAA song song.
- [ ] Đọc EDNS OPT pseudo-RR, UDP size, DO bit và options.
- [ ] Phân biệt TC bit với capture truncation và IP fragmentation.
- [ ] Kiểm tra TCP fallback khi có truncated UDP response.
- [ ] Không kết luận DNSSEC validated chỉ từ RRSIG/AD/DO.
- [ ] Có DNSSEC validator logs nếu nghi chain-of-trust error.
- [ ] Đã kiểm tra IPv6 packets, routes và DNS records.
- [ ] Cân nhắc NAT, proxy, CNI, CoreDNS/NodeLocal DNSCache.
- [ ] Thời gian query/response được tính trên cùng clock domain.
- [ ] Chỉ đo RTT với matched transactions có quality đủ.
- [ ] Có đánh dấu orphan query/response và retries.
- [ ] Kiểm tra capture drop counters và asymmetric paths.
- [ ] Với encrypted DNS, dùng approved endpoint/resolver logs.
- [ ] Không quy kết QNAME theo shared CDN IP chỉ bằng DNS lookup.
- [ ] Detection NXDOMAIN/DGA/tunneling có baseline và false-positive review.
- [ ] Có correlate firewall/flow/EDR/IDS/IPS/app audit.
- [ ] Không gắn kết luận “exfil/C2 confirmed” chỉ từ một packet.
- [ ] Có positive và negative tests trong môi trường lab.
- [ ] Không thực hiện thử nghiệm volumetric/reflection trên bên thứ ba.
- [ ] Báo cáo có packet numbers/timestamps/filters và limitations.
- [ ] Báo cáo đã redaction hostnames/identifiers nhạy cảm khi chia sẻ.
- [ ] Đã phân biệt DNS thành công với TCP/TLS/HTTP success.
- [ ] Có root cause, remediation owner, rollback và regression plan.

## 42. Bảng thuật ngữ

| Thuật ngữ | Giải thích |
|---|---|
| **DNS packet/message** | Dữ liệu DNS mang trong UDP/TCP hoặc giao vận khác |
| **QNAME/QTYPE/QCLASS** | Tên, loại và lớp của câu hỏi |
| **RR/RRset** | Resource record / tập records cùng tên, loại, lớp theo semantics |
| **ID (TXID)** | Transaction identifier 16 bit của DNS message |
| **QR** | Query/Response bit |
| **RD/RA** | Recursion Desired/Available |
| **AA** | Authoritative Answer |
| **TC** | Truncated response flag |
| **AD/CD** | Authenticated Data/Checking Disabled |
| **RCODE** | DNS response code |
| **NODATA** | NOERROR nhưng không có RR thuộc requested type trong ngữ cảnh thích hợp |
| **NXDOMAIN** | Name Error, tên không tồn tại theo response/view |
| **SERVFAIL** | Server processing failure |
| **SOA** | Zone authority data, dùng trong negative response context |
| **TTL** | Time to Live của RR caching |
| **EDNS(0)** | Extension Mechanisms for DNS phiên bản 0 |
| **OPT** | EDNS pseudo-resource record TYPE 41 |
| **DO** | DNSSEC OK flag trong EDNS OPT |
| **DNSSEC** | DNS cryptographic data integrity/authentication validation |
| **DNSKEY/DS/RRSIG** | DNSSEC key/delegation/signature records |
| **NSEC/NSEC3** | DNSSEC authenticated denial mechanisms |
| **Compression pointer** | Byte sequence high bits 11, offset tới tên DNS message |
| **Recursive resolver** | Server có thể tìm/cache câu trả lời hộ client |
| **Authoritative server** | Server có thẩm quyền với zone dữ liệu |
| **Stub resolver** | Thành phần phía client hỏi resolver |
| **Referral/glue** | Delegation records và address help cho name servers |
| **Negative caching** | Cache câu trả lời phủ định theo quy định |
| **DoT/DoH/DoQ** | DNS over TLS/HTTPS/QUIC |
| **PCAP/PCAPNG** | Định dạng lưu packet captures |
| **Snaplen** | Số bytes tối đa ghi lại của mỗi packet khi capture |
| **BPF capture filter** | Filter giới hạn packets được thu trong capture theo cú pháp |
| **Wireshark display filter** | Filter packets hiển thị sau khi capture |
| **RTT** | Round-trip time ước tính theo observation point |
| **SPAN/TAP** | Cơ chế lấy bản sao traffic từ mạng |
| **NAT/NodeLocal DNSCache** | Những thành phần có thể đổi identity/đường đi DNS |
| **DNS rebinding** | Thay đổi DNS resolution để vượt ranh giới trust theo kịch bản |
| **DNS tunneling** | Chuyển dữ liệu trong DNS traffic theo kỹ thuật sử dụng DNS |
| **DGA** | Thuật toán tạo domain names theo quy luật |
| **DNS amplification** | Trường hợp UDP DNS response lớn hơn request, liên quan rủi ro DDoS |
| **False positive** | Tín hiệu cảnh báo nhưng hoạt động không vi phạm như giả thuyết |

## 43. Tổng kết

**Phân tích DNS packet** bắt đầu từ việc đọc đúng **DNS header 12 byte, các cờ QR/RD/RA/AA/TC/AD/CD/RCODE, Question, Answer, Authority, Additional, QNAME/QTYPE/QCLASS, resource records và TTL**. Sau đó cần ghép query/response trong đúng ngữ cảnh **source/destination ports, IP, thời gian và điểm capture**. Với TCP phải chú ý **length prefix/reassembly**; với EDNS và DNSSEC phải hiểu **OPT/DO/AD/CD/extended RCODE và giới hạn của chứng cứ xác thực**.

Một DNS packet phân giải thành công không chứng minh ứng dụng đã kết nối, một NXDOMAIN không giống SERVFAIL, một NODATA không phải NXDOMAIN, một QNAME dài không tự là DNS tunneling, và **không thấy DNS plaintext không chứng minh client không sử dụng DNS** khi có caches, split resolvers và DoH/DoT/DoQ. Muốn điều tra chính xác phải đặt packet trong bối cảnh **topology, NAT, firewall, CNI, DNS logs, endpoint telemetry, cloud/service identity, IDS/IPS và ứng dụng**.

Trong module **SECURITY_NETWORK_SECURITY**, một quy trình tốt là **capture có quyền, bảo toàn evidence, decode đúng protocol, kiểm tra coverage, diễn giải có uncertainty, đối chiếu nhiều lớp và chạy positive/negative tests**. Những thực hành này giúp phát hiện nhanh lỗi DNS, hiểu sự cố mạng liên quan resolution và nhận diện các tín hiệu bất thường một cách có trách nhiệm, thay vì biến một packet đơn lẻ thành kết luận bảo mật không có đủ bằng chứng.
