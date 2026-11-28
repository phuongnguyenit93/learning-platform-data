# DNS telemetry cho phát hiện truy vấn bất thường: Thu thập, phân tích và điều tra theo ngữ cảnh

## 1. Vì sao DNS là một nguồn telemetry an ninh quan trọng?

**Domain Name System (DNS)** giúp thiết bị và ứng dụng tìm dữ liệu phân giải tên, như bản ghi A/AAAA cho địa chỉ IP, MX cho mail server, SRV cho một số dịch vụ, TXT cho thông tin cấu hình hoặc nhiều loại bản ghi khác. DNS không chỉ xuất hiện khi người dùng mở trình duyệt: hệ điều hành, container, phần mềm bảo mật, ứng dụng SaaS, cơ sở hạ tầng cloud, malware và dịch vụ nội bộ đều có thể phát sinh truy vấn.

Trong giám sát an ninh mạng, **DNS telemetry** là tập các sự kiện/metrics quan sát được về việc **ai hỏi tên gì, khi nào, từ đâu, qua resolver nào, nhận phản hồi ra sao và hành vi có khác thông lệ không**. Nó đặc biệt hữu ích khi nội dung ứng dụng được mã hóa TLS và firewall chỉ thấy kết nối tới IP: một chuỗi truy vấn có thể cung cấp ngữ cảnh về **dịch vụ mà workload đang tìm cách sử dụng**.

Ví dụ: một máy chủ chỉ cần truy cập database nội bộ bỗng tạo hàng trăm truy vấn tới các subdomain chưa từng thấy. Tín hiệu này **đáng điều tra**, nhưng chưa đủ kết luận đó là malware: thư viện telemetry, cache busting, cơ chế kiểm thử hoặc cấu hình lỗi cũng có thể tạo ra mẫu tương tự.

Ngược lại, một máy bị xâm nhập có thể giao tiếp tới địa chỉ IP đã biết **mà không tạo truy vấn DNS mới**. Vì vậy, DNS telemetry là **một lớp quan sát bổ sung**, không thay netflow, firewall, proxy, IDS/IPS, endpoint detection, application audit hoặc khả năng kiểm soát egress.

Thuộc chương **Giám sát mạng và telemetry** trong học phần **SECURITY_NETWORK_SECURITY**, bài học này gắn phân tích DNS với **kiểm soát truy cập mạng, phân đoạn, firewall, VPN, cloud/container networking, phát hiện xâm nhập và bảo vệ hạ tầng DNS**, từ lúc thu thập đến khi có bằng chứng đủ tin cậy cho điều tra.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả luồng DNS client–recursive resolver–authoritative và chọn **điểm quan sát** phù hợp.
2. Giải thích những trường telemetry như **QNAME, QTYPE, RCODE, flags, answer, TTL, client identity, query/response timestamp và resolver**.
3. Phân biệt **DNS query logs, resolver metrics, passive DNS, authoritative logs, packet capture và encrypted DNS**; chỉ rõ phạm vi/điểm mù.
4. Chuẩn hóa sự kiện theo thời điểm và danh tính thiết bị/workload, xử lý **cache, NAT, forwarders, Kubernetes Pod IP reuse và clock skew**.
5. Xây baseline và các phép đo **NXDOMAIN rate, unique subdomain ratio, entropy, query burst, time periodicity, TTL/answer churn, record-type distribution**.
6. Triển khai phát hiện **DGA-like names, DNS tunneling indicators, C2-like periodic queries, suspicious TXT bursts, resolver bypass, domain/answer drift và DNS failures** mà không đồng nhất bất thường với tấn công.
7. Điều tra theo quy trình, kết hợp **EDR/process, firewall/flow, proxy, PKI/TLS, DNSSEC và cloud audit**, kiểm soát false positives, privacy, retention và độ tin cậy.
8. Tự phân tích tập dữ liệu giả lập qua lab offline, tạo detector có test và xây dashboard/alert có thể dùng trong vận hành.

## 2. DNS hoạt động như thế nào và telemetry sinh ở đâu?

### 2.1. Các thành phần

| Thành phần | Vai trò | Telemetry có thể có |
| --- | --- | --- |
| **Stub resolver/client** | Ứng dụng hoặc OS phát sinh yêu cầu | Process/device, hostname được hỏi, kết quả dùng bởi app |
| **Local cache / NodeLocal DNSCache** | Trả lời một số truy vấn gần client | Cache hits, forwarded requests, hit/miss metrics |
| **Recursive resolver** | Trả lời client bằng cache hoặc truy vấn các máy chủ khác | Client query/response logs, RCODE, latency, upstream events |
| **Forwarder** | Chuyển tiếp câu hỏi tới resolver khác | Source forwarder, upstream target, errors/latency |
| **Authoritative DNS** | Phục vụ bản ghi cho zone mà nó có thẩm quyền | Requests tới zone, DNS answers và nguồn requester nhìn thấy |
| **Network sensor** | Quan sát DNS khi traffic đi qua điểm đo | Packet metadata, query/response khi không bị mã hóa |
| **Endpoint/EDR** | Liên kết DNS với tiến trình/thiết bị khi được instrument | Process tree, executable, device identity, resolver calls |
| **Cloud DNS telemetry** | Logs/metrics từ dịch vụ DNS cloud | Các trường và phạm vi theo provider/feature |

**Một lần ứng dụng truy cập tên không đồng nghĩa một lần query xuất hiện ở mọi nơi.** Stub/OS cache có thể trả lời trước khi gửi gói; recursive resolver có thể trả lời từ cache; forwarder có thể gom truy vấn từ rất nhiều client. Tần suất nhìn thấy ở recursive resolver có thể khác số lần app gọi API phân giải tên.

### 2.2. Luồng phân giải minh họa

~~~mermaid
sequenceDiagram
    participant A as Application / stub
    participant L as OS hoặc local cache
    participant R as Recursive resolver
    participant AU as Authoritative chain
    A->>L: Hỏi api.partner.example A/AAAA
    alt Local cache hit
      L-->>A: Trả kết quả từ cache
    else Local cache miss
      L->>R: DNS question
      alt Recursive cache hit
        R-->>L: Cached response
      else Recursive cache miss
        R->>AU: Resolve qua các zone liên quan
        AU-->>R: Resource records / status
        R-->>L: Response
      end
      L-->>A: Kết quả cho ứng dụng
    end
~~~

Sơ đồ rút gọn: thực tế có thể có forwarding layers, CNAME/DNAME, DNSSEC validation, search suffixes, retries, EDNS(0), authoritative caching, dual-stack và các cơ chế bảo mật khác. Không suy ra client đã kết nối tới IP chỉ vì resolver trả bản ghi A/AAAA.

### 2.3. Recursive resolver thấy gì, không thấy gì?

Một resolver nội bộ thường có thể ghi **client source address** mà nó nhìn thấy, QNAME/QTYPE, RCODE, answer records hoặc thống kê, thời gian xử lý. Nhưng nếu **NodeLocal cache, forwarder hoặc NAT** đứng trước, địa chỉ nguồn ở resolver không luôn là Pod/workload gốc.

**Response NOERROR không chứng minh application đã kết nối thành công.** Nó chỉ nói về kết quả DNS; TCP, TLS, policy, proxy và backend vẫn có thể lỗi. Tương tự, một response NXDOMAIN không chứng minh domain độc hại; nó có thể là tên gõ sai, search suffix expansion hoặc cache-negative bình thường.

### 2.4. Truy vấn DNS có thể được thực hiện qua nhiều transport

- **UDP/53:** cách truyền DNS truyền thống, có giới hạn kích thước và khả năng retry tùy giao thức.
- **TCP/53:** được DNS sử dụng cho một số truy vấn/responses, zone transfer trong bối cảnh được phép, retries và các tình huống khác; không coi TCP/53 mặc nhiên bất thường.
- **DoT (DNS over TLS):** thường dùng TCP/853, mã hóa traffic giữa client và endpoint giải mã DoT, theo profile.
- **DoH (DNS over HTTPS):** DNS qua HTTPS; có thể chạy trên TLS và HTTP transports khác nhau, không đơn giản giới hạn ở một port.
- **DoQ (DNS over QUIC):** DNS qua QUIC, với cơ chế triển khai/port theo tiêu chuẩn và sản phẩm.
- **Private in-process resolver/other tunnels:** một số ứng dụng có thể phân giải tên qua cơ chế riêng, proxy hoặc SDK.

**TLS/HTTPS/QUIC mã hóa payload DNS trên đường truyền cho những sensors không nằm ở đầu cuối giải mã.** Các sensors network vẫn có thể thấy IP/port/bytes/timing, nhưng không tự đọc QNAME/QTYPE. Để quan sát chính xác cần telemetry **tại resolver/endpoint hoặc proxy nơi có quyền giải mã**.

## 3. Định nghĩa sự kiện DNS và các trường cần hiểu

### 3.1. Một DNS question không phải toàn bộ packet

DNS wire format có **header, question section, answer, authority, additional section**. Một packet thường chứa một question nhưng schema có khả năng biểu diễn phức tạp hơn; logs có thể ghi một sự kiện cho **question, response, transaction, cache lookup hoặc upstream query** tùy cảm biến. Khi tổng hợp, phải thống nhất **đơn vị đếm**.

Ví dụ câu hỏi:

~~~text
event_time: 2026-11-28T08:45:00.000Z  (giả lập)
client:     10.20.4.17
resolver:   10.20.0.53
qname:      api.partner.example.
qtype:      A
transport:  UDP
response:   NOERROR
answer:     192.0.2.40 (dải địa chỉ dành cho tài liệu)
latency_ms: 18
~~~

**Không đưa nguyên gói tin hoặc toàn bộ answers vào mọi alert** nếu chỉ cần thống kê. Payload DNS có thể chứa hostname nhạy cảm, identifiers hoặc thông tin mà một ứng dụng đã nhúng sai vào tên truy vấn.

### 3.2. Các trường chính và những hiểu nhầm thường gặp

| Trường | Ý nghĩa | Cẩn trọng khi phân tích |
| --- | --- | --- |
| **QNAME** | Tên được hỏi, dạng canonical/presentation | Normalize chữ hoa/thường, dấu chấm cuối, IDNA/punycode đúng |
| **QTYPE** | Loại record được hỏi: A, AAAA, MX, TXT, SRV, HTTPS, v.v. | TXT/HTTPS/SRV không tự là dấu hiệu malware |
| **QCLASS** | Class, thường là IN | Đừng hardcode kết luận khi gặp loại khác |
| **RCODE** | Mã phản hồi như NOERROR, NXDOMAIN, SERVFAIL, REFUSED | NOERROR có thể không có answer cho QTYPE |
| **Answer RRset** | Records trả về, TTL và các trường cần thiết | Response có thể gồm CNAME chain, nhiều A/AAAA |
| **TTL** | Thời gian cache logic của record được trả về | TTL nhìn thấy có thể đã giảm do cache; không phải thời gian session |
| **Flags RD/RA/AA/AD/TC** | Recursion desired/available, authoritative, authenticated data, truncated | Ý nghĩa tùy query/response và vai trò resolver |
| **EDNS(0) / OPT** | Mở rộng DNS truyền thống, metadata negotiation | OPT record không là TXT/data exfil theo mặc định |
| **Client source** | Địa chỉ nguồn resolver/sensor thấy | Có thể là NAT/forwarder, không phải endpoint gốc |
| **Resolver identity** | Resolver nào phục vụ và ghi log | Một client có thể dùng nhiều resolvers |
| **Transaction ID** | Giá trị trên wire dùng ghép request/response theo ngữ cảnh | Không dùng ID 16-bit đơn lẻ làm correlation key toàn hệ thống |
| **Event/ingest time** | Khi DNS event xảy ra / khi log vào hệ thống | Lệch clock hoặc collector lag làm sai timeline |
| **Latency/timeout** | Thời gian trả lời theo điểm đo | Client timeout khác upstream resolver timeout |
| **Cache status** | Hit/miss/prefetch/stale nếu nguồn cung cấp | Nhiều sản phẩm không expose hoặc định nghĩa khác nhau |
| **Policy action** | Allow, block, rewrite, sinkhole theo resolver | Response NXDOMAIN không tự là policy block |

### 3.3. Phân biệt NXDOMAIN, NODATA, SERVFAIL, REFUSED và timeout

- **NXDOMAIN (RCODE=3):** tên được hỏi không tồn tại theo nội dung câu trả lời DNS; không phải mọi trường hợp đều là malicious domain.
- **NOERROR nhưng không có answer thuộc QTYPE được yêu cầu (NODATA):** tên có thể tồn tại, nhưng không có record loại cần tìm; khác NXDOMAIN.
- **SERVFAIL (RCODE=2):** resolver không hoàn tất xử lý; có thể do upstream/DNSSEC validation/configuration và nhiều nguyên nhân khác.
- **REFUSED (RCODE=5):** server từ chối cung cấp dịch vụ cho truy vấn theo policy/khả năng.
- **Timeout:** client/observer không nhận phản hồi đúng thời gian; có thể do firewall, network loss, resolver overload hoặc packet capture thiếu response.
- **NOERROR cùng CNAME:** một kết quả có thể có alias chain; phải xem RRsets thay vì chỉ đếm một IP.

Một detector chỉ lấy **tỷ lệ NXDOMAIN** rồi tuyên bố DGA dễ sai khi DNS search domains tạo nhiều truy vấn tới tên không tồn tại. Cần phân tích **loại nguồn, QNAME pattern, baseline và nhóm truy vấn tương quan**.

### 3.4. Tên miền: FQDN, registered domain và public suffix

Ví dụ:

~~~text
FQDN:          a7b9d3.collector.vendor.example.
Subdomain:     a7b9d3.collector
Parent:        collector.vendor.example
Example suffix: example
~~~

**Không thể tách registered domain bằng cách lấy hai nhãn cuối một cách máy móc.** Public suffix có thể gồm nhiều nhãn, và private suffixes thay đổi tùy danh sách/tổ chức. Khi nhóm dữ liệu theo eTLD+1/registrable domain, dùng **Public Suffix List hoặc thư viện chuẩn được cập nhật** với cách xử lý IDNA/normalized QNAME phù hợp. Với private/internal zones, cần **tập zone riêng của tổ chức**, không áp eTLD+1 Internet cho mọi tên.

Mẫu **.example** dành cho tài liệu; các hostname/IP ở đây là giả lập. Không dùng chúng để suy ra DNS bên ngoài sẽ có answer thực.

## 4. Các điểm quan sát và giới hạn riêng

### 4.1. Bản đồ telemetry theo vị trí

~~~mermaid
flowchart LR
    APP["Ứng dụng/tiến trình"] --> STUB["OS stub/cache"]
    STUB --> DNS["Internal recursive / forwarder"]
    DNS --> AUTH["Authoritative DNS / upstream"]
    APP -. "Process telemetry" .-> EDR["EDR / endpoint logs"]
    STUB -. "Local visibility" .-> HOST["Host/OS DNS events"]
    STUB -. "Packets if not encrypted" .-> NET["CNI / packet sensor"]
    DNS -. "Query/response metadata" .-> RES["Resolver logs / dnstap"]
    AUTH -. "Zone access activity" .-> ALOG["Authoritative logs"]
    NET --> JOIN["Normalization + SIEM"]
    RES --> JOIN
    EDR --> JOIN
    HOST --> JOIN
    ALOG --> JOIN
~~~

Nhìn thấy một query ở **authoritative server** không bảo đảm biết trực tiếp client cuối: requester có thể là recursive resolver trung gian. Một query xuất hiện trong **resolver log** không bảo đảm app không dùng cache. **Mỗi điểm quan sát phải có mô tả source identity và độ phủ riêng.**

### 4.2. So sánh nguồn dữ liệu

| Nguồn | Ưu điểm | Nhược điểm/điểm mù |
| --- | --- | --- |
| **Recursive resolver query logging** | Thấy QNAME/QTYPE/RCODE của những client qua resolver | Query logs có thể lớn, không thấy bypass/caches trước resolver |
| **dnstap hoặc query–response capture hỗ trợ bởi server** | Cấu trúc sự kiện DNS chi tiết, hỗ trợ pipeline theo implementation | Feature và event types cần cấu hình, có chi phí |
| **CoreDNS plugin logs/metrics** | Hữu ích cho service discovery Kubernetes | Không tự gắn process/Pod UID nếu chỉ thấy node/forwarder source |
| **DNS firewall/filtering logs** | Có policy action/domain verdict | Chỉ thấy DNS đi qua hệ thống lọc |
| **Endpoint EDR/DNS telemetry** | Liên kết process, executable và device nếu hỗ trợ | Agent quyền rộng, thiếu unmanaged devices, sampling |
| **Network packet sensor** | Nhanh khi thấy plaintext DNS UDP/TCP/53 | DoH/DoT/DoQ mã hóa; packet loss, asymmetric routing |
| **CNI/eBPF flow logs** | Gắn workload identity, IP/port, policy verdict | Flow-only thường không thấy QNAME nếu không có L7 parser phù hợp |
| **Cloud DNS resolver logs** | Gắn với VPC/VNet/project theo khả năng | Field coverage, pricing, retention và nguồn clients khác nhau |
| **Authoritative logs** | Quan sát traffic tới authoritative zone | Thường thấy recursive resolvers, không biết requester gốc |
| **Passive DNS feeds** | Lịch sử tên↔answers từ mạng/nguồn được phép | Bias theo sensor, freshness và completeness khó biết |

### 4.3. Lựa chọn theo câu hỏi điều tra

**“Workload nào hỏi domain lạ?”** Ưu tiên **endpoint/process telemetry hoặc resolver queries có client attribution**, kết hợp Kubernetes/asset inventory.

**“Tại sao app không phân giải được?”** Ưu tiên **RCODE, latency, DNS server errors, DNSSEC, forwarding, route/firewall**.

**“Có truy vấn đến máy chủ DNS ngoài chính sách không?”** Ưu tiên **host/network/CNI flow + egress enforcement**, vì resolver nội bộ sẽ không thấy truy vấn bị bypass.

**“Domain từng trả IP nào trong một khoảng thời gian?”** Dùng **historical DNS answers/passive DNS** với rõ nguồn/độ tin cậy; không tra current DNS rồi gán ngược cho sự kiện quá khứ.

**“Có thực sự gửi dữ liệu ra không?”** DNS query logs chỉ thấy nội dung QNAME và một phần answers. Để xác định bản chất dữ liệu và ảnh hưởng thực tế còn cần **application/endpoint audit, proxy, DLP và incident evidence**.

## 5. Thiết kế pipeline DNS telemetry có thể vận hành

### 5.1. Các bước từ nguồn tới điều tra

~~~mermaid
flowchart TD
    RES["Resolvers / DNS policy engines"] --> COLLECT["Collectors"]
    EP["EDR / endpoint DNS events"] --> COLLECT
    CLOUD["Cloud DNS query logs"] --> COLLECT
    NET["Packet / CNI network telemetry"] --> COLLECT
    COLLECT --> QC["Schema / clock / loss checks"]
    QC --> NORM["Normalize QNAME / QTYPE / RCODE / times"]
    NORM --> ID["Time-aware client/workload enrichment"]
    ID --> DERIVE["Metrics, grouping, baseline and feature extraction"]
    DERIVE --> STORE["Log store / time-series / case records"]
    DERIVE --> DET["Detections + correlation"]
    DET --> TRIAGE["SOC / SRE triage"]
    TRIAGE -. "Feedback: FP/TP/unknown" .-> DET
~~~

Một resolver có thể xuất **query events**, **response events** hoặc cả hai; collectors không nên đếm cùng một DNS transaction thành hai query chỉ vì có hai bản ghi. Thiết kế pipeline phải ghi **event_type và observation_point**.

### 5.2. Trường tối thiểu và trường hữu ích

**Trường lõi:**

- **event_time_utc**, **ingest_time_utc**, **sensor_id**, **cluster/site/region**.
- **event_type**: query, response, combined transaction, cache, policy action, timeout.
- **client_address**, **resolver_address**, **transport** và client port nếu nguồn có.
- **normalized_qname**, **qtype**, **qclass**.
- **response_rcode** nếu có; nếu chưa có response thì **unknown/pending**, không gán NXDOMAIN.
- **policy_decision** (allowed/blocked/rewritten) nếu resolver có chức năng lọc.
- **collection_health**, **log_schema_version**, **sampling flag**.

**Trường bổ sung:**

- **original_qname**, flags, answers (đã hạn chế độ chi tiết theo use case), TTL, latency.
- **client_device_id / user_id / Pod UID / service account / process path** theo telemetry thực.
- **client_network_zone, site, subnet, NAT/forwarder identity**.
- **response source**, cache hit/miss, upstream resolver và DNSSEC validation result nếu có.
- **session/process correlation**, request ID hoặc event ID do sensor cấp.
- **source confidence**, parser status và timestamps của enrichment.

Trường không thu được phải để **null/unknown**; không tạo **process identity** từ một IP NAT dùng chung hoặc coi một hostname là chính xác user.

### 5.3. Một sự kiện chuẩn hóa minh họa

~~~json
{
  "schema_version": "dns.telemetry.lab.v1",
  "event_time_utc": "2026-11-28T09:14:02.130Z",
  "ingest_time_utc": "2026-11-28T09:14:03.012Z",
  "event_type": "dns_transaction",
  "sensor": {
    "id": "resolver-lab-east-01",
    "observation_point": "recursive_client_interface",
    "dropped_events_known": false
  },
  "client": {
    "ip": "10.20.4.17",
    "workload_id": "finance-lab/report-worker",
    "pod_uid": "lab-uid-report-011",
    "attribution_confidence": "high"
  },
  "resolver_ip": "10.20.0.53",
  "dns": {
    "qname": "api.partner.example.",
    "qtype": "A",
    "rcode": "NOERROR",
    "answers": [
      {
        "type": "A",
        "data": "192.0.2.40",
        "ttl_seconds": 120
      }
    ],
    "latency_ms": 18
  },
  "policy": {
    "action": "ALLOW",
    "rule_id": "approved-business-dns"
  }
}
~~~

**Tất cả giá trị ở đây là giả lập**, bao gồm Pod UID, workload identity và answer IP dành cho tài liệu. Đây không phải schema chính thức của một CNI, DNS server hoặc SIEM. Một resolver thực có thể không biết Pod UID; khi đó cần enrichment đáng tin theo lịch sử.

### 5.4. Chuẩn hóa QNAME đúng cách

Một bộ chuẩn hóa cần:

1. Ghi **raw/original QNAME** an toàn ở nơi có quyền khi cần làm chứng cứ.
2. Chuẩn hóa chữ hoa/thường theo nguyên tắc so sánh DNS names không phân biệt case trong những tình huống phù hợp.
3. Quyết định nhất quán về **dấu chấm cuối** của FQDN khi tính nhóm.
4. Xử lý **IDNA/punycode** bằng thư viện phù hợp, không tự thay chuỗi Unicode tùy tiện.
5. Phân biệt **FQDN, suffix nội bộ, registrable domain và subdomain**.
6. Giữ dấu hiệu malformed/invalid names riêng; không âm thầm “sửa” tên rồi coi như raw packet.
7. Giới hạn kích thước dữ liệu và chống log injection khi QNAME chứa ký tự đặc biệt trong presentation form.

**Cấu trúc tên trong DNS có giới hạn độ dài nhãn và tên theo wire format.** Nhãn thường có giới hạn 63 octets, tổng tên encoded bị giới hạn theo DNS protocol. Khi dựng detector cho “long names”, nên kiểm tra **độ dài sau encoding**, không chỉ số ký tự Unicode trên màn hình.

### 5.5. Gom transaction và chống đếm đôi

Ví dụ cùng một truy vấn:

~~~text
09:14:02.130  endpoint DNS_QUERY
09:14:02.132  recursive DNS_QUERY
09:14:02.146  recursive DNS_RESPONSE
09:14:02.151  endpoint DNS_RESPONSE
~~~

Đây có thể là **một giao dịch logic** nhìn ở hai điểm. Nếu đếm bốn events thành bốn DNS queries, rate và volume bị thổi phồng. Để correlation, dùng **sensor ID + client/resolver tuple + DNS transaction ID + QNAME/QTYPE + cửa sổ thời gian phù hợp** khi có; ID DNS 16-bit **không phải khóa toàn cục duy nhất** và retries có thể làm trùng lặp.

Không cố suy ra rằng mọi endpoint query luôn khớp một recursive query: **cache hit, forwarding, DNS over HTTPS và mất packet** làm tương quan không hoàn hảo.

### 5.6. Retention và lựa chọn mức chi tiết

Không phải mọi môi trường cần giữ **tất cả DNS answers thô** trong nhiều năm. Một thiết kế có thể tách:

| Dữ liệu | Mục đích | Mức truy cập |
| --- | --- | --- |
| Metrics tổng hợp theo workload/site | Quan sát xu hướng và cảnh báo | Nhóm SRE/SOC phù hợp |
| DNS query/response metadata trong khoảng giới hạn | Điều tra một incident gần đây | SOC, quản trị kiểm soát |
| Sự kiện đáng ngờ và enrichment | Case management, replay detection | Nhóm điều tra |
| Packet capture giới hạn | Xác minh giao thức trong lab/incident đã duyệt | Quyền đặc biệt, thời hạn ngắn |
| Historical object/device mapping | Truy ngược owner theo thời điểm | Platform/security hạn chế |

Thời hạn lưu cụ thể theo **rủi ro, pháp luật, hợp đồng, dữ liệu cá nhân và ngân sách**, không có một con số đúng cho mọi công ty.

## 6. Gán DNS events cho đúng thiết bị, workload và tiến trình

### 6.1. Địa chỉ client chưa phải identity bền vững

Resolver có thể thấy source IP **10.20.4.17**, nhưng một địa chỉ:

- Có thể được cấp lại bởi DHCP.
- Có thể là một **NAT hoặc DNS forwarder** đại diện hàng trăm endpoints.
- Có thể là IP của Kubernetes Pod vừa bị thay và tái sử dụng.
- Có thể là node IP của **NodeLocal DNSCache hoặc hostNetwork**.
- Có thể thuộc VPN pool, VDI session, proxy hoặc shared network appliance.

Vì vậy cần **time-aware identity mapping**:

~~~text
DNS event (time, sensor, source IP)
    |
    +-- DHCP/VPN assignment history  →  device/session
    +-- Kubernetes Pod UID history   →  namespace/workload owner
    +-- NAT/forwarder mapping        →  original source if available
    +-- EDR process observation      →  process lineage when supported
    +-- Identity/login telemetry     →  user account/session if grounded
~~~

Không lấy **current kubectl get pods** vào hôm nay để quy flow DNS tuần trước cho workload hiện tại có cùng IP.

### 6.2. Kubernetes và NodeLocal DNSCache

Một Pod gọi một Service thường gặp **DNS search suffixes** và có thể query nhiều tên trước khi tìm thấy tên hợp lệ. Với cấu hình DNS của Pod, **ndots**, search domains, CoreDNS, NodeLocal DNSCache hoặc custom DNSPolicy có thể làm QNAME volume và NXDOMAIN rate thay đổi lớn.

Ví dụ một ứng dụng query **payments** trong namespace có search domains:

~~~text
payments.ns.svc.cluster.local.
payments.svc.cluster.local.
payments.cluster.local.
payments.
~~~

Danh sách chỉ minh họa, **không phản ánh thứ tự hay nội dung bắt buộc của mọi resolv.conf**. Một số lần lookup bị NXDOMAIN vì search expansion **là hành vi hợp lệ**. Detector phải xét **internal domain suffix, Kubernetes cluster domain, ndots, Deployment rollout và DNS cache path**.

Nếu NodeLocal cache phục vụ truy vấn, CoreDNS có thể không thấy tất cả events; ngược lại một query từ NodeLocal tới CoreDNS có thể ghi **source là node/forwarder** thay vì Pod. Muốn gán Pod UID cần nguồn tại pod/host hoặc correlation đáng tin.

### 6.3. VPN, NAT và roaming endpoints

Một laptop dùng Wi-Fi ở nhà, VPN full tunnel hoặc split tunnel có thể gửi DNS qua **những resolvers khác nhau**. Nếu chỉ nhìn resolver data center:

- Thiết bị không còn thuộc vùng quan sát có thể biến mất khỏi metrics.
- Một public NAT IP có thể đại diện nhiều thiết bị.
- Địa chỉ VPN lease có thể đổi theo thời gian.
- BYOD hoặc browser tự dùng DoH có thể không xuất hiện.

Hãy phân biệt **“không thấy query”** với **“thiết bị không thực hiện DNS lookup”**. Endpoint agent health, VPN session logs, resolver policies và device enrollment là các tín hiệu độc lập cần kiểm tra.

### 6.4. Process-level attribution

EDR hoặc DNS client telemetry có thể xác định:

- Executable/process ID, parent process và chữ ký phần mềm.
- Device ID, logged-on user theo khoảng thời gian.
- Process start time và network activity liên quan.
- DNS API call hoặc query observed at endpoint.

Nhưng không thể giả định một **recursive resolver event** luôn gắn một process: nhiều processes dùng **shared OS resolver/cache**, ứng dụng khác có thể dùng DoH riêng, và process ID được tái sử dụng. Cần process **start time, device ID, sensor confidence** để tránh gán nhầm.

## 7. Baseline DNS: Đặt bất thường vào ngữ cảnh

### 7.1. Baseline theo vai trò, không áp một ngưỡng toàn mạng

Một **developer workstation** có thể query hàng trăm domains khi tải dependencies; một **domain controller** có nhiều SRV queries; một **database host** có thể rất ít external DNS; một **Kubernetes node** có nhiều lookup nội bộ do workloads. Áp cùng ngưỡng **50 NXDOMAIN mỗi 10 phút** cho tất cả dễ gây false positives.

Nên nhóm theo:

- **Environment:** prod/staging/dev/lab.
- **Asset role/workload owner:** database, CI runner, webserver, DNS resolver, user laptop.
- **Device management state:** managed/unmanaged.
- **Resolver/site/region** và DNS policy.
- **Namespace/service account**, nếu attribution đáng tin.
- **Time-of-day/weekday**, release window, batch/CronJob schedule.

Không xây baseline bằng cách mặc định **mọi traffic quan sát được đều hợp lệ**. Hãy gắn approved dependencies, incident history và các nguồn được biết là lỗi/malware trước khi “học chuẩn”.

### 7.2. Các chỉ số cơ bản

| Chỉ số | Câu hỏi giải quyết | Điểm cần chú ý |
| --- | --- | --- |
| **Queries/s (QPS)** | Tần suất thay đổi so với mức nền? | Cache và sampling ảnh hưởng số đếm |
| **Unique QNAMEs / window** | Nhiều tên chưa từng thấy? | Search suffix, CDN/cache busting |
| **Unique registered domains** | Có thêm nhiều nhóm domain mới? | Public suffix/IDNA cần chuẩn hóa |
| **Distinct subdomains per parent** | Có nhiều nhãn khác nhau dưới một domain? | Telemetry/service discovery hợp lệ |
| **NXDOMAIN ratio** | Tỷ lệ tên không tồn tại tăng? | Chỉ tính trên responses có RCODE |
| **SERVFAIL/timeout ratio** | Có lỗi resolver/upstream tăng? | Phân biệt outage với suspicious queries |
| **QTYPE distribution** | A/AAAA/TXT/SRV/HTTPS có đổi mạnh? | Dịch vụ hợp lệ cũng dùng TXT/HTTPS |
| **Mean/p95 QNAME length** | Có tên bất thường dài? | App identifiers/UUID tạo FP |
| **Subdomain entropy** | Các nhãn trông ít cấu trúc hơn? | Random không phải tấn công mặc định |
| **Time periodicity** | Query lặp ở khoảng thời gian đều? | Heartbeats/monitoring cũng tuần hoàn |
| **Answer IP/ASN churn** | IP đích thay đổi nhanh? | CDN/geo routing/anycast rất phổ biến |
| **TTL distribution** | TTL rất ngắn hay bất thường? | Cache TTL giảm, provider legitimate |
| **Resolver bypass flows** | Có app dùng resolver không được duyệt? | Không thấy QNAME khi encrypted |
| **Policy block count** | DNS filter/egress rule chặn gì? | Nhiều blocks có thể chỉ là client retry loop |

### 7.3. Các tỷ lệ phải có mẫu số đúng

Ví dụ:

\[
\operatorname{NXDOMAIN\ ratio} =
\frac{\text{số DNS responses có RCODE=NXDOMAIN}}
{\text{số DNS responses có RCODE được biết trong cửa sổ}}
\]

Không dùng **số query requests** làm mẫu số nếu response events bị mất hoặc không thu thập, vì ratio sẽ đánh lừa. Các transactions **timeout** cần metrics riêng; một client có thể retry và làm mẫu số lớn bất thường.

Một máy có 2/2 NXDOMAIN (100%) không nhất thiết đáng chú ý hơn máy có 800/1000 (80%): cần **minimum sample size, absolute count và baseline của asset role**.

### 7.4. Tỷ lệ tên mới theo parent domain

Để phát hiện một parent domain nhận nhiều nhãn thay đổi:

\[
\operatorname{unique\ subdomain\ ratio} =
\frac{\operatorname{distinct}(\text{subdomain labels under parent})}
{\operatorname{count}(\text{queries under parent})}
\]

Tỷ lệ gần 1 có thể do mỗi query dùng **mã ngẫu nhiên/UUID** hoặc một số cơ chế telemetry hợp lệ. Do đó cần thêm **volume, QNAME lengths, entropy, workload role, destination reputation, answer/response profile** và kiểm tra thay đổi ứng dụng.

### 7.5. Tính entropy: Thông tin hữu ích nhưng dễ báo nhầm

Với một chuỗi nhãn gồm các ký tự thuộc tập \(C\), Shannon entropy có thể viết:

\[
H(X)=-\sum_{c\in C}p(c)\log_2p(c)
\]

Trong đó \(p(c)\) là tỷ lệ ký tự \(c\) trong chuỗi. **Entropy cao** có thể chỉ một nhãn chứa chuỗi gần ngẫu nhiên, nhưng:

- UUID, hash, session nonce, analytics/correlation ID có thể tạo entropy cao hợp lệ.
- Một DGA có thể dùng từ điển và entropy không cao.
- Độ dài chuỗi nhỏ làm entropy estimate rất nhiễu.
- Punycode và encoding thay đổi phân phối ký tự.
- Trộn toàn bộ FQDN với suffix phổ biến có thể che tín hiệu ở **nhãn nghi vấn**.

Vì thế **không dùng một ngưỡng entropy cứng để tự động block mọi domain**. Nó phù hợp như **feature trong mô hình nhiều tín hiệu**, kết hợp mẫu có nhãn và feedback điều tra.

### 7.6. Đường nền phải thích ứng với thay đổi vận hành

Một build/deploy, auto-scaling, service discovery update, vendor migration hoặc DNS provider outage có thể đổi mạnh các metrics. Baseline cần:

1. Có thời gian tham chiếu đủ đại diện **ngày làm việc, cuối tuần, batch và deployment**.
2. Gắn **change records** và owners.
3. Tách anomaly về **availability** khỏi anomaly nghi **security**.
4. Không tự học lại ngay các giai đoạn có incident đang điều tra.
5. Có kế hoạch rollback/điều chỉnh detector sau false positives.

**Không thể đánh giá false negatives chỉ từ alerts đã phát**; cần kiểm thử dữ liệu có nhãn, incident retrospectives và các kịch bản được mô phỏng có kiểm soát.

## 8. Phát hiện truy vấn bất thường: Các nhóm tín hiệu

### 8.1. Bất thường tần suất và phân phối thời gian

**Dấu hiệu:** một workload bình thường chỉ gửi vài DNS queries/phút đột ngột tăng gấp nhiều lần hoặc tạo chuỗi truy vấn đều đặn trong thời gian dài.

**Có thể liên quan:** retry loop, lỗi client, DNS amplification/reflection activity trong phạm vi thích hợp, application dependency thay đổi, phần mềm có lịch gọi cố định hoặc malware cố duy trì liên lạc.

**Dữ liệu cần:** event time, client/workload identity, QNAME group, queries/s, unique names, retry/response profile, process name, change history.

**Không kết luận malware từ một burst ngắn**: khi máy vừa khởi động, ứng dụng mở nhiều tab hoặc cluster vừa triển khai, DNS volume có thể tăng tự nhiên. Đối chiếu baseline cùng giờ, cùng workload role và tổng số queries trên resolver.

### 8.2. NXDOMAIN burst và DGA-like patterns

Một số malware dùng **Domain Generation Algorithm (DGA)** để tạo nhiều tên miền ứng viên, cố tìm một tên đã được đăng ký/được điều khiển. Telemetry có thể cho thấy:

- Rất nhiều **QNAME khác nhau**, với tỷ lệ NXDOMAIN cao.
- Các tên có nhãn trông ngẫu nhiên hoặc thay đổi theo chuỗi.
- Một nhóm queries tập trung từ một endpoint/process bất thường.
- Sự khác biệt mạnh so với phần mềm/nhóm thiết bị tương tự.
- Sau chuỗi thất bại có một số tên trả lời thành công hoặc một connection đáng điều tra.

**Đây là một giả thuyết, không phải chữ ký chắc chắn.** DGA dạng từ điển có thể trông “bình thường”; telemetry/SDK dùng mã định danh cũng có thể có tính ngẫu nhiên và NXDOMAIN. Hãy phối hợp **EDR process tree, executable signer, asset role, answers, proxy/flow and threat intelligence**.

Ví dụ chỉ để nhìn pattern:

~~~text
09:00  pc-17 -> 7b2q4p.checks.example.     A  NXDOMAIN
09:01  pc-17 -> 1m9x5n.checks.example.     A  NXDOMAIN
09:02  pc-17 -> 2r8k3v.checks.example.     A  NXDOMAIN

09:00  ci-02 -> artifact-42.build.example. A  NOERROR
09:01  ci-02 -> artifact-43.build.example. A  NOERROR
09:02  ci-02 -> artifact-44.build.example. A  NOERROR
~~~

Cả hai nhóm đều thay đổi nhãn nhưng **RCODE, vai trò client và mục đích** khác nhau. Những tên ở đây chỉ là **dữ liệu giả lập trong tài liệu**, không chỉ ra hạ tầng độc hại.

### 8.3. TXT/NULL/record-type anomalies

DNS TXT records được sử dụng hợp lệ cho **SPF, DKIM, domain verification, ACME challenges, service configuration** và nhiều mục đích khác. Một số kỹ thuật lạm dụng DNS cũng có thể dùng những record types mang dữ liệu hoặc patterns khác thông lệ.

**Tín hiệu cần điều tra:** client vốn chủ yếu hỏi A/AAAA bắt đầu gửi nhiều TXT queries dưới một parent domain mới, với QNAME dài và lượng dữ liệu/độ dài answers khác baseline.

**Không coi một TXT lookup là exfiltration.** Cần đánh giá **mục đích ứng dụng, QNAME pattern, số lượng, network egress, endpoint process và nội dung được phép xem**. Khi một sensor không lưu TXT answers do privacy policy, không được suy diễn payload chưa thấy.

### 8.4. DNS tunneling / exfiltration candidate

Một kênh truyền trái phép có thể cố mã hóa dữ liệu trong **nhãn truy vấn hoặc phản hồi DNS**. Những indicator ở mức quan sát gồm:

- Subdomains dài và biến đổi nhiều dưới một parent domain.
- Chuỗi query dày hoặc đều đặn từ một workload ít cần DNS.
- Entropy cao, nhãn có độ dài/distribution khác những queries còn lại của client.
- Cặp QTYPE/response/record sizes không giống lịch sử dịch vụ.
- Tương quan với hành vi đọc file/data, process runtime đáng ngờ hoặc network policy violations.
- Những tên miền hiếm gặp và domain/authoritative infrastructure không liên quan mục tiêu nghiệp vụ.

**Không thể chứng minh dữ liệu nào đã bị tiết lộ chỉ từ tên nhãn “trông mã hóa”.** DNS tunneling cũng có thể tồn tại trong hoạt động quản trị/lab được phê duyệt. Khi cần xác minh dữ liệu, phải có **quyền điều tra, bằng chứng từ endpoint/application, DLP/audit, chuỗi sự kiện và giới hạn thu thập phù hợp**.

### 8.5. Truy vấn tuần hoàn như heartbeat hoặc C2-like beacon

**Dấu hiệu:** một endpoint truy vấn một domain theo khoảng thời gian gần đều, ví dụ mỗi 60 giây, trong suốt nhiều giờ. Kiểm tra:

- Thống kê **inter-arrival time** của cùng source/domain.
- Độ biến thiên khoảng cách giữa queries.
- Gắn với thời gian uptime, process/network status.
- Có cùng behavior trên những endpoints khác cùng phần mềm không?
- Có connections tương ứng sau DNS resolution và thay đổi khi idle không?

Các dịch vụ hợp lệ như **monitoring agent, auto-update, certificate checker, service health probe** cũng có thể query tuần hoàn. **Periodic DNS một mình là tín hiệu yếu**; ưu tiên cảnh báo khi kết hợp domain hiếm, process không được phê duyệt, policy deny và hành vi nối mạng bất thường.

### 8.6. Fast-flux-like answer churn

Một số hạ tầng lạm dụng DNS có thể xoay nhiều IP đích trong thời gian ngắn. Dấu hiệu:

- Một QNAME có nhiều **A/AAAA answers** khác nhau theo thời gian.
- TTL ngắn hoặc answer changes thường xuyên.
- Một số địa chỉ có ASN/địa lý khác biệt hoặc không nhất quán với nguồn được duyệt.
- Tên miền mới gặp và có nhiều endpoint kết nối tới IP đã trả về.

**CDN, geo load balancing, anycast, failover và managed SaaS cũng thường đổi IP/TTL.** Chỉ khi đối chiếu **provider, service role, historical DNS, threat intelligence và process/traffic** mới có thể đánh giá rủi ro.

**TTL thấp không tự chứng minh fast flux.** TTL từ recursive cache còn có thể giảm theo thời gian hoặc bị policy rewrite.

### 8.7. Truy vấn tới tên miền mới/ngoài dependency graph

Một workload cơ sở dữ liệu chỉ cần private DNS bỗng hỏi tên của một dịch vụ công cộng. Đây có thể là:

- Thay đổi hợp lệ do SDK/telemetry.
- Package mới bị thêm ngoài kiến trúc.
- CronJob, monitoring hoặc update client.
- Dấu hiệu egress ngoài ý định, SSRF hoặc phần mềm bị chiếm.

**Nguồn chứng minh:** Deployment/code dependency change, runtime/EDR events, DNS, HTTP proxy và cloud egress logs. Cần đo **new for this workload** thay vì chỉ **new for entire enterprise**; một domain SaaS phổ biến có thể rất khác thường với database workload.

### 8.8. Các domain trả về IP không phù hợp

Ví dụ:

- Một public hostname trả về **private/link-local address** ngoài kế hoạch.
- Một hostname quan trọng đột ngột trỏ tới network owner khác so với baseline và provider thông báo.
- Một internal FQDN trả về public IP trong lúc VPN/split DNS thay đổi.
- Response có dấu hiệu **DNS policy rewrite/sinkhole** nhưng client vẫn tạo kết nối sai đích.

Các nguyên nhân có thể hợp lệ: **split-horizon DNS, internal CDN, disaster recovery, cloud private endpoints hoặc thay đổi cấu hình**. Có thể nghi ngờ DNS rebinding/hijack, nhưng **không tự kết luận attack** nếu chỉ nhìn một answer khác.

Đối chiếu **resolver identity, DNSSEC validation status nếu có, DHCP/VPN DNS settings, cloud DNS change audit, TLS server identity và route thực**.

### 8.9. DNS errors và sự cố availability

Không phải mọi DNS anomaly là security incident. Các mẫu:

| Dấu hiệu | Giả thuyết chính | Kiểm chứng |
| --- | --- | --- |
| **SERVFAIL tăng hàng loạt** | Resolver/upstream/DNSSEC issue | Resolver health, upstream reachability, validation logs |
| **Timeout tăng theo một subnet** | Firewall/NAC/VPN route hoặc packet loss | Network flow, drops, DNS path |
| **NXDOMAIN tăng khi rollout** | Search suffix/ndots, typo trong config | Pod resolv.conf, deployment diff |
| **REFUSED cho một nhóm client** | ACL/resolver policy, split DNS | Resolver decision logs, source attribution |
| **No answer for AAAA nhưng A có** | Domain/service không có IPv6 answer phù hợp | Response type và ứng dụng dual-stack |
| **Latency p99 tăng** | Resolver CPU, upstream retry, DNSSEC, cache miss | Cache metrics, upstream latency, capacity |
| **DNS success nhưng app TLS fail** | Certificate/SNI/hostname mismatch | TLS/client logs, actual destination |

Một detector nên phân loại **security hypothesis** và **service-health hypothesis** riêng, sau đó liên kết khi có evidence. Ví dụ một client tạo nhiều retries vì resolver outage thường không nên bị kết luận đang tunneling.

## 9. Những điểm mù đặc biệt của DNS telemetry

### 9.1. DNS cache và truy vấn không tới resolver đang giám sát

Giả sử client đã phân giải **api.partner.example** lúc 09:00, sau đó mở nhiều connections trong khoảng cache hợp lệ. Resolver có thể chỉ thấy một truy vấn, trong khi firewall thấy hàng chục connections. Không được kết luận chỉ có một lần truy cập ứng dụng dựa vào DNS query count.

Tương tự, nếu ứng dụng truy cập trực tiếp IP hoặc có hardcoded hosts entry, nó có thể không hỏi DNS. **DNS telemetry không đo đầy đủ destination reachability**.

### 9.2. DoH, DoT, DoQ và ứng dụng dùng resolver riêng

~~~mermaid
flowchart LR
    APP["Endpoint application"] --> OS["OS resolver"]
    OS --> ENTERPRISE["Enterprise DNS"]
    APP -. "DoH/DoT/DoQ (nếu được phép hoặc bypass)" .-> ENCRYPTED["Other encrypted DNS resolver"]
    APP -. "Direct IP / cached answer" .-> IP["External service"]
    ENTERPRISE -. "Query logs" .-> SOC["SOC"]
    ENCRYPTED -. "Không có QNAME tại enterprise resolver" .-> SOC
    IP -. "Network flow only" .-> SOC
~~~

Khi một browser dùng DoH tới resolver riêng, sensor chỉ thấy **encrypted HTTPS connection** trừ khi có endpoint/DoH resolver telemetry được phép. Không áp dụng nhãn **DoH chắc chắn** cho mọi HTTPS tới một IP: cần verified endpoint/resolver identity và protocol context.

Kiểm soát có thể gồm **managed browser/endpoint policy, approved DNS resolver, egress firewall, secure proxy và L7 observability tại điểm hợp lệ**. Không cần cố giải mã toàn bộ HTTPS của người dùng để thu DNS telemetry.

### 9.3. Authoritative visibility và resolver attribution

Một authoritative server cho zone **example** có thể nhận query từ **recursive resolver của tổ chức**, không phải client thực. Đếm distinct source IP ở authoritative logs rồi gọi chúng là “số máy bị ảnh hưởng” là sai.

Ngược lại, **authoritative DNS query volumes** có thể hữu ích để quan sát abuse của một zone, nhưng cần gắn với query paths và cache behavior.

### 9.4. VPN split DNS và private namespaces

Trên laptop từ xa, các domain nội bộ có thể được gửi qua resolver VPN còn domains public qua resolver địa phương. Nếu DNS policy thay, hệ thống có thể thấy:

- Domain nội bộ bị gửi sai ra public resolver.
- Resolver nội bộ không thấy query của các apps.
- App không phân giải được khi tunnel bị ngắt.
- Phần mềm tự dùng DoH ngoài VPN.

Để điều tra cần **VPN assignment/policy history, endpoint DNS settings, device/network identity và resolver logs**, tránh suy diễn một sự thiếu vắng dữ liệu là an toàn.

### 9.5. Một số kỹ thuật bảo mật làm thay đổi quan sát

- **DNSSEC:** cung cấp cơ chế xác thực dữ liệu DNS khi validation đúng; validation failures có thể biểu hiện SERVFAIL. Nó không mã hóa QNAME và không tự là bộ lọc truy vấn độc hại.
- **Encrypted ClientHello (ECH):** có thể hạn chế khả năng suy ra domain từ một phần TLS handshake; DNS và TLS telemetry cần được đánh giá theo thực tế protocol.
- **EDNS(0):** có metadata protocol, kích thước UDP và options; không nên coi tất cả EDNS options là hành vi bí mật.
- **Serve-stale và prefetch:** resolver có thể trả cached/stale answers hoặc tự truy vấn upstream, làm tần suất/timestamps khác ý định client.
- **DNS policy sinkhole/rewrites:** RCODE/answer có thể là kết quả của giải pháp bảo mật chứ không phải authoritative truth.
- **DNS load balancing/anycast:** cùng resolver address có thể phục vụ bởi nhiều backend; việc gắn node/region cần logs tương ứng.

**Nền tảng giám sát phải ghi rõ thực thể quan sát đang trả lời câu hỏi gì**, thay vì kết hợp các nguồn rồi coi tất cả events tương đương.

## 10. Xây detector DNS dựa trên nhiều tín hiệu

### 10.1. Detector phải có giả thuyết và điều kiện quan sát

Trước khi viết rule, cần mô tả:

1. **Threat hypothesis:** muốn phát hiện DGA-like lookup, tunnel candidate, C2-like periodic query, resolver bypass hay DNS outage?
2. **Data source:** resolver logs, EDR, cloud DNS, CNI flow hay authoritative telemetry?
3. **Coverage:** có thấy đầy đủ client identities, record types, response codes và encrypted DNS không?
4. **Unit of analysis:** source workload, endpoint process, QNAME, registrable domain, time window hay DNS transaction?
5. **Expected benign behavior:** batch, CDN, update agents, search suffix, deployment?
6. **Action:** alert, enrich, observe, require manual review hay block theo policy đã phê duyệt?
7. **Validation:** positive test, negative test, false-positive review và khi sensor mất dữ liệu?

Một rule không rõ **mẫu số, observation point hoặc nguồn dữ liệu** có thể chạy “thành công” nhưng tạo ra kết luận sai.

### 10.2. Rule A — NXDOMAIN spike kèm tên mới

~~~text
GROUP dns_transactions BY source_workload, 10-minute window
CALCULATE:
    total_responded = count(rcode is known)
    nxdomain_count  = count(rcode == NXDOMAIN)
    distinct_qname  = count_distinct(normalized_qname)
    baseline_ratio  = learned_nxdomain_ratio(source_role, time_context)

IF total_responded >= minimum_sample_size
   AND nxdomain_count >= minimum_absolute_count
   AND nxdomain_count / total_responded > role_adjusted_threshold
   AND distinct_qname is above source baseline
THEN
    ALERT "Unusual failed DNS name generation candidate"
    INCLUDE source, affected suffixes, top qtypes, change context
    REQUIRE process and domain-context enrichment before escalation
~~~

Đây là **pseudocode**, không phải rule chạy trực tiếp. Không có một giá trị **10 phút**, count hay ratio chuẩn dùng cho mọi môi trường. Thử trên log có nhãn, đảm bảo các RCODE thuộc **response/transaction events** chứ không phải query-only events.

### 10.3. Rule B — Subdomain churn và long-name cluster

~~~text
GROUP BY source_identity, parent_domain, time_window
FEATURES:
    number_of_queries
    distinct_leftmost_labels
    distinct_subdomain_ratio
    qname_length_p95
    leftmost_label_entropy_distribution
    qtype_distribution
    observed_rcodes

IF source has no approved high-cardinality DNS dependency
   AND volume and distinct-label features exceed its baseline
   AND long-name/entropy indicators are consistent over multiple windows
THEN
    ALERT "DNS high-cardinality subdomain activity"
    CORRELATE with endpoint process, app data-access and egress flows
~~~

Không kết luận tunneling chỉ vì **leftmost label** dài: một số hợp lệ có nhiều nhãn, payload có thể nằm ở **nhiều nhãn**, và entropy phải được diễn giải với encoding/normalization. Đây là **detector gợi ý điều tra**, không là bằng chứng nội dung bị lấy.

### 10.4. Rule C — Truy vấn đều đặn tới domain hiếm

~~~text
GROUP BY source, normalized_domain
CALCULATE:
    inter_arrival_times_seconds = successive_query_time_diffs
    event_count
    median_interval
    interval_variability
    domain_prevalence_across_peer_group

IF event_count >= minimum_observations
   AND periodicity is unusual relative to source role
   AND domain is not an approved heartbeat/update dependency
THEN
    ALERT "Unusual periodic DNS behavior"
    ENRICH with EDR process and follow-up network flows
~~~

Một agent hợp lệ query mỗi 60 giây có thể có tính tuần hoàn rất cao. Cần xem **asset role, signed software inventory, domain ownership và recent change**. Ngoài ra, malware có thể dùng jitter làm che periodicity; không thấy chu kỳ đều **không phủ định rủi ro**.

### 10.5. Rule D — Resolver bypass

DNS query logs tại resolver nội bộ **không đủ phát hiện bypass**; cần quan sát network outbound:

~~~text
IF source_asset IN managed_assets
   AND outgoing_flow.destination IN known_or_verified_DNS_resolver_set
   AND destination NOT IN approved_resolvers_for_asset
   AND protocol/port behavior matches relevant DNS transport evidence
THEN
    ALERT "Unapproved DNS resolver path candidate"
    INCLUDE policy context, network path, device agent health
~~~

Với **encrypted DNS**, chỉ kết nối tới một host cung cấp DoH không tự chứng minh request cụ thể mang DNS; host đó có thể phục vụ nhiều ứng dụng. Cần **verified service evidence, endpoint configuration hoặc policy context**, ghi confidence rõ.

**Không suy từ absence of enterprise DNS logs** thành bypass nếu ứng dụng có cache hit hoặc không tạo query.

### 10.6. Rule E — Đổi answer của domain nhạy cảm

~~~text
FOR each protected_application_domain:
    compare observed_dns_answers_to:
       approved provider / private zone / change record
       expected resolver viewpoint and region
       historical TTL and IP/ASN distribution
    flag unexpected and persistent answer drift
    correlate with TLS hostname/certificate validation and route
~~~

Với CDN và multi-region, **expected addresses phải theo provider/region và thời gian**; một IP “mới” không đủ kết luận DNS hijack. Dùng domain được quản trị, đường phân giải trong/ngoài VPN và cloud DNS change audit.

### 10.7. Rule F — DNS availability anomaly

~~~text
GROUP BY resolver, site, query_type, 5-minute window
METRICS:
    served_transactions
    servfail_count, refused_count
    timeout_count (when visible)
    latency_p50, latency_p95, latency_p99
    recursive_cache_hit_ratio (if available)

IF failure rate and/or latency exceed site-specific SLO
THEN
    PAGE DNS/SRE owner
    CORRELATE firewall, upstream, DNSSEC validation, deployment
~~~

Đây là **reliability detector**; có thể có ý nghĩa an ninh khi DNS bị tấn công hoặc bị thay cấu hình, nhưng trước tiên nó chỉ xác nhận trải nghiệm phân giải có vấn đề.

### 10.8. Quy tắc ưu tiên: High-confidence vs exploratory

| Loại | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| **Vi phạm policy rõ ràng** | Managed host gọi resolver đã xác nhận không được phép; egress firewall thấy flow | High-priority review, có thể block theo runbook |
| **Nhiều tín hiệu tương quan** | High NXDOMAIN + domain churn + process bất thường + unexpected external connections | SOC investigation, containment tùy bằng chứng |
| **Một chỉ số yếu** | TXT query mới, high entropy label, TTL thấp | Enrichment/triage, không auto-quarantine |
| **Sự cố DNS availability** | SERVFAIL cao ở nhiều clients cùng resolver | SRE/DNS incident, security phối hợp nếu có dấu hiệu |
| **Visibility gap** | DoH policy thay đổi, resolver logs ngừng, collector mất events | Repair coverage/verify enforcement |

Severity nên xét **criticality của nguồn/đích, số workloads bị ảnh hưởng, quyền dữ liệu, tính bất thường so với peer group, độ tin cậy attribution và hậu quả nếu thật**. Không dùng một điểm entropy duy nhất làm cơ sở cô lập production servers.

## 11. Tương quan DNS với các lớp bảo mật khác

### 11.1. DNS → Flow → TLS → Application

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant D as DNS resolver
    participant F as Network firewall / flow sensor
    participant P as HTTPS proxy or TLS endpoint
    participant A as Application audit
    W->>D: Query api.partner.example
    D-->>W: Response 192.0.2.40
    W->>F: TCP connection tới 192.0.2.40:443
    F-->>P: Flow forwarded per policy
    P-->>A: HTTPS request/app action nếu đã authorized
    Note over W,A: Correlation bằng thời gian + identity + tuples/IDs phù hợp
~~~

Sơ đồ thể hiện các điểm quan sát có thể nối với nhau; **một DNS answer không bảo đảm được client sử dụng**. Client có thể bỏ answer, sử dụng cache, chọn A/AAAA khác hoặc proxy tự phân giải tên. Tương quan tên→IP **cần time window, resolver viewpoint, TTL/answer set và network source context**.

### 11.2. Một flow không nhất thiết có một DNS query

| Tình huống | Vì sao không có mapping 1:1 |
| --- | --- |
| **DNS cache hit tại OS** | Connection không phát sinh truy vấn mới ở resolver |
| **HTTP/2/keep-alive** | Nhiều HTTP requests qua một TCP/TLS session |
| **CDN shared IP** | Nhiều hostnames có thể trỏ tới cùng IP |
| **DNS load balancing** | Một tên trả nhiều IP; client chỉ dùng một |
| **Proxy** | Proxy có thể resolve thay client |
| **Forwarder/NAT** | Source IP quan sát khác client gốc |
| **Pod IP reuse** | Identity của source thay đổi theo thời gian |
| **Encrypted DNS** | Sensor network không thấy QNAME |
| **Direct-IP connection** | Không cần hostname lookup |
| **Background prefetch** | Có DNS query nhưng không có ứng dụng kết nối sau đó |

**Không ghi “source truy cập domain X” chỉ vì source nhìn thấy DNS answer X** nếu không có traffic/app evidence. Cách diễn đạt an toàn hơn: **“source đã thực hiện hoặc được ghi nhận liên quan tới DNS lookup tên X”**.

### 11.3. Endpoint process là bằng chứng quan trọng

Khi một laptop có DNS churn, EDR có thể cho biết truy vấn thuộc:

- Browser profile/tab hoặc tiến trình tự cập nhật.
- Agent giám sát/cấu hình có chữ ký hợp lệ.
- Script/CLI mới được chạy từ đường dẫn không chuẩn.
- Một tiến trình con phát sinh sau document/email attachment.
- SDK hợp lệ của app vừa được nâng cấp.

**Process path hoặc signer hợp lệ không chứng minh hành vi an toàn tuyệt đối**, và danh tính process có thể bị giả mạo hoặc sensor ghi thiếu. Nhưng correlation giúp giảm rất nhiều false positives so với chỉ một QNAME.

### 11.4. Egress control và DNS policy

Một tổ chức có thể **bắt endpoints/Pods dùng enterprise DNS** và **chặn direct Internet** qua firewall/NetworkPolicy/secure web gateway. Khi đó:

- DNS filter đưa ra policy decision về tên miền được hỏi.
- Egress firewall/proxy ngăn direct-IP bypass khi được thiết kế đúng.
- Proxy có thể kiểm tra destination application/TLS hostname theo khả năng.
- DLP/application security xác định nội dung có được phép chia sẻ hay không.

**DNS policy DENY không đủ ngăn kết nối IP trực tiếp.** Ngược lại, egress firewall DENY TCP/443 không tự phân loại domain đáng ngờ: đây là các lớp phòng thủ có chức năng khác nhau.

### 11.5. Sử dụng threat intelligence đúng mức

Threat intel có thể chứa **malicious domain indicators, passive DNS histories, registration features, reputation, infrastructure associations**. Cần:

1. Xác minh **nguồn, tuổi, phạm vi, điều kiện dùng và độ tin cậy** của indicator.
2. Phân biệt **đã từng liên quan** với **đang độc hại**.
3. Tránh block nhầm **shared hosting/CDN/legitimate compromised infrastructure**.
4. Dùng allow exceptions có phê duyệt nhưng tránh whitelist mọi traffic của một domain rộng.
5. Kết hợp **process/user/device context và DNS/flow evidence**.

Một indicator cũ có thể bị tái sử dụng bởi dịch vụ hợp lệ; một domain mới không có reputation **không tự là xấu**.

### 11.6. DNSSEC không phải hệ thống reputation

DNSSEC giúp các validating resolvers **xác thực dữ liệu DNS theo chain trust**, nhưng một domain được ký hợp lệ vẫn có thể phục vụ hạ tầng lạm dụng. Ngược lại, validation error có thể do vận hành/sự cố zone, không mặc định là tấn công.

Trong telemetry, ghi **DNSSEC validation result** khi resolver hỗ trợ, nhưng tránh:

- Coi **AD flag** trong mọi response là bằng chứng tuyệt đối nếu không hiểu trust boundary.
- Coi unsigned domain là malicious.
- Kết luận một SERVFAIL là DNS poisoning mà không có validation logs.

## 12. Phát hiện thay đổi cấu hình DNS và đường bypass

### 12.1. Control-plane changes cần theo dõi

Các thay đổi có thể làm DNS telemetry biến mất hoặc bị sai:

- Sửa DHCP-provided resolver address.
- Đổi VPN/split-DNS configuration.
- Bật browser DoH policy ngoài hệ thống được duyệt.
- Đổi Kubernetes **dnsPolicy, dnsConfig, CoreDNS ConfigMap, NodeLocal cache, CNI egress policy**.
- Sửa cloud private zone, forwarding rules, conditional resolver hoặc DNS firewall lists.
- Thay recursive resolver logging level, exporter/collector endpoints.
- Mở outbound UDP/TCP/53, TCP/853 hoặc các resolver endpoints được quản lý.
- Chuyển app sang một public DNS library mà endpoint/host logging không thấy.

**Một thay đổi được triển khai thành công chưa chắc là change có chủ đích**. Cần đối chiếu source-of-truth, actor, approval và behavior trước/sau.

### 12.2. Một detector cho “mất visibility”

Không thể chỉ dùng câu **“0 DNS queries = no traffic”**. Thiết kế:

~~~text
FOR each monitored site/resolver/collector:
    expected_traffic = baseline for active assets and time window
    observed_events = count(sensor events)
    agent_health = heartbeat / export status
    network_activity = independent flow / resolver metrics

IF active_assets > 0
   AND observed_events drop unusually
   AND (agent_unhealthy OR independent_traffic_persists)
THEN
    ALERT "DNS telemetry coverage degraded"
    SET detection_confidence_for_gap_period = low
~~~

Đây là **coverage detector**. Nó không thể tự tái tạo toàn bộ queries bị mất; cần ghi **gap window** trong incident timeline và xử lý collector/resolver trước khi kết luận không có truy vấn đáng ngờ.

### 12.3. Chặn bypass bằng các lớp độc lập

Một kiến trúc có thể:

1. Cấu hình **approved resolvers** cho OS/Pods/endpoints.
2. Áp network egress control để giới hạn **unapproved DNS paths**.
3. Quản lý browser/endpoint policies với thiết bị được quản lý.
4. Quan sát cloud/VPN/Kubernetes routes và interfaces.
5. Đo DNS coverage theo **assets active vs assets observed**.
6. Xử lý exception cho dịch vụ cần resolver/transport riêng qua review.

**Không bật TLS inspection trên toàn bộ mạng chỉ để thấy QNAME** nếu còn nguồn resolver/endpoint được phép ít xâm lấn hơn. Phải cân bằng visibility, privacy, security và khả dụng.

## 13. Quy trình SOC/SRE: Từ alert DNS tới kết luận có bằng chứng

### 13.1. Chuỗi xử lý thực tế

~~~mermaid
flowchart TD
    A["DNS alert: abnormal query pattern"] --> B["Validate sensor + schema + time window"]
    B --> C{"Có đủ client identity?"}
    C -->|Không| D["NAT/forwarder/DHCP/VPN/Pod history"]
    C -->|Có| E["Enrich asset role / process / change"]
    D --> E
    E --> F{"Availability or operational cause?"}
    F -->|Có thể| G["Resolver / DNSSEC / rollout / cache investigation"]
    F -->|Chưa giải thích| H["Domain/QNAME/answer/time pattern analysis"]
    H --> I["Correlate EDR + flows + proxy + app audit"]
    G --> J["Classify: benign, config fault, suspicious, unknown"]
    I --> J
    J --> K["Owner-approved action + evidence preservation"]
    K --> L["Verify control and update baseline/rule"]
~~~

**Đừng tự cô lập production server vì một truy vấn TXT hoặc một tên dài.** Trước tiên phải xác minh telemetry và tác động kinh doanh. Khi có nhiều bằng chứng compromise, áp incident-response runbook đã được phê duyệt.

### 13.2. Bước 1 — Xác minh alert và dữ liệu nguồn

Kiểm tra:

1. Detector/rule version, điều kiện threshold và time window.
2. Event type là **query**, **response**, **combined transaction**, **policy decision** hay flow?
3. Có **RCODE thực từ response** không, hay là timeout/missing response?
4. Event time có đồng bộ UTC và sensor/collector bị ingest lag không?
5. Bị sampling, double counting, retry, duplicate logs hoặc resolver cache ảnh hưởng không?
6. Alert chỉ ở một resolver hay cùng lúc trên nhiều resolvers?
7. Client/source identity có phải device/workload gốc hay là NAT/forwarder?

Nếu dữ liệu không đáng tin, **đánh dấu độ tin cậy thấp** và điều tra pipeline trước khi hành động ảnh hưởng nhiều người dùng.

### 13.3. Bước 2 — Xác định đối tượng bị ảnh hưởng

Với **DNS source IP tại thời điểm T**:

- Tra DHCP lease/VPN session history cho endpoint nếu nguồn là máy người dùng.
- Dùng Pod UID, namespace, workload owner, node và timestamp cho Kubernetes.
- Với proxy/forwarder, tìm original client mapping nếu logging hỗ trợ.
- Đối chiếu asset inventory, owner, environment và data classification.
- Với EDR, xem process ancestry và executable signatures/behaviors.

**Không quy kết user cụ thể chỉ từ public IP hoặc resolver cache.** NAT và shared devices làm giảm độ tin cậy; cần nhiều bằng chứng hơn trước khi có hành động nhân sự.

### 13.4. Bước 3 — Nhìn vào pattern, không chỉ một domain

Một mẫu đánh giá:

| Góc nhìn | Câu hỏi |
| --- | --- |
| **Thời gian** | Tăng khi nào? Lặp lại bao lâu? Có gắn deployment/schedule? |
| **QNAME** | Cùng parent domain hay trải rộng? Tên dài/ngẫu nhiên tới mức nào? |
| **QTYPE/RCODE** | Chủ yếu A/AAAA, TXT, HTTPS, SRV? NXDOMAIN hay SERVFAIL? |
| **Answer** | Các IP/TTL/ASN trả về có phù hợp provider/region? |
| **Asset role** | Database server, build worker, endpoint hay resolver? |
| **Process** | Tiến trình nào làm lookup? Có mới hoặc không thuộc allowlist? |
| **Data path** | Có firewall/HTTP connection sau lookup? Direct Internet hay proxy? |
| **Data access** | Có export/read/upload đáng nghi ở application audit? |
| **Change context** | Có release, vendor move, policy/DNS config update được phê duyệt? |
| **Confidence** | Sensor có gap, logging thiếu hoặc map client không chắc? |

### 13.5. Bước 4 — Phân loại

Một kết quả điều tra nên có **kết luận và phạm vi hỗ trợ**:

- **Benign/expected:** có ứng dụng/owner/luồng nghiệp vụ giải thích được, khớp logs và approved dependency.
- **Operational misconfiguration:** DNS search loop, invalid hostname, stale resolver config, broken TLS/DNSSEC, upstream outage.
- **Suspicious, not confirmed:** kết hợp anomaly và process/domain/flow khó giải thích; cần thu thập thêm.
- **Confirmed policy violation:** nguồn dùng resolver/đích ngoài policy và có enforcement/audit evidence.
- **Confirmed compromise/exfiltration:** chỉ khi bằng chứng điều tra cho thấy hành vi đó, không chỉ vì entropy/NXDOMAIN.
- **Unknown due to visibility gap:** event loss, NAT mapping không đủ, encrypted DNS ngoài sensor, không thể quy nguồn.

**“Chưa đủ dữ liệu” là kết quả hợp lệ**. Không biến mức nghi ngờ thành kết luận chắc chắn trong incident report.

### 13.6. Bước 5 — Phản hồi và bảo toàn bằng chứng

Theo mức rủi ro và quy trình:

1. Ghi lại **original event references, sensor ID, timestamps, normalized/raw QNAME khi được phép, rule version**.
2. Lưu **asset owner, process, DHCP/VPN/Pod mapping** và cách gán danh tính.
3. Chụp **firewall/proxy/EDR/application audit references** có quan hệ thời gian.
4. Nếu xác nhận đích không được phép, xem xét **DNS filtering/egress policy/endpoint containment** ở đúng phạm vi.
5. Không xóa log hoặc chỉnh resolver config tùy ý trước khi giữ bằng chứng, trừ trường hợp containment khẩn cấp theo runbook.
6. Kiểm tra hậu quả của block: hostname có phải **shared infrastructure/CDN** hoặc dependency business không?
7. Chỉ kết thúc case khi đã ghi **root cause/hypothesis, evidence, unknowns, action owner và outcome**.

### 13.7. Không để phản hồi tạo sự cố mới

Nếu một domain thuộc nhà cung cấp DNS/CDN dùng chung, block toàn domain/IP có thể gián đoạn rất nhiều dịch vụ hợp lệ. Khi cần kiểm soát:

- Ưu tiên **source workload / application scope** thay vì áp toàn mạng khi bằng chứng mới ở một host.
- Dùng **time-bound exception/quarantine**, test và rollback.
- Kiểm tra authoritative/registrable domain đúng, tránh match suffix quá rộng.
- Phân biệt block QNAME, policy ở resolver và network block tới IP.
- Xác minh client có thể dùng DNS cache/DoH sau khi block tên; không tuyên bố ngăn hết traffic chỉ từ DNS filter.

## 14. Lab offline: Phân tích DNS events giả lập và tránh kết luận vội

**Phạm vi an toàn:** bài lab dùng **dữ liệu tự tạo** và những tên miền reserved cho tài liệu. Không có yêu cầu truy vấn Internet, scan host, gửi dữ liệu ra ngoài hoặc tạo DNS tunnel thật. Chỉ làm trên máy/hệ thống do bạn được phép sử dụng. Các lệnh phân tích bên dưới là ví dụ với **jq**, không phải code phải chạy trong pipeline sản xuất.

### 14.1. Mô hình nguồn dữ liệu

Ba nhóm source:

1. **web-01:** web server hỏi vài domains hợp lệ liên quan ứng dụng.
2. **dev-01:** build/dev workstation hỏi các tên artifact khác nhau, có một số lỗi name resolution.
3. **db-01:** database server vốn ít external DNS bỗng hỏi nhiều tên khác nhau dưới một parent.

Mục tiêu là tìm **mẫu khác baseline**, không gắn nhãn “db-01 bị nhiễm malware” chỉ vì QNAME trông ngẫu nhiên.

### 14.2. Bộ dữ liệu JSON Lines

Sao chép những dòng sau vào một file lab **dns_lab.jsonl** nếu muốn tự chạy truy vấn:

~~~jsonl
{"time":"2026-11-28T09:00:00Z","source":"web-01","role":"web","qname":"api.partner.example.","qtype":"A","rcode":"NOERROR"}
{"time":"2026-11-28T09:00:05Z","source":"web-01","role":"web","qname":"api.partner.example.","qtype":"AAAA","rcode":"NOERROR"}
{"time":"2026-11-28T09:01:00Z","source":"web-01","role":"web","qname":"auth.partner.example.","qtype":"A","rcode":"NOERROR"}
{"time":"2026-11-28T09:00:00Z","source":"dev-01","role":"development","qname":"artifact-101.build.example.","qtype":"A","rcode":"NOERROR"}
{"time":"2026-11-28T09:01:00Z","source":"dev-01","role":"development","qname":"artifact-102.build.example.","qtype":"A","rcode":"NOERROR"}
{"time":"2026-11-28T09:02:00Z","source":"dev-01","role":"development","qname":"artifact-103.build.example.","qtype":"A","rcode":"NOERROR"}
{"time":"2026-11-28T09:03:00Z","source":"dev-01","role":"development","qname":"missing.build.invalid.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:00:03Z","source":"db-01","role":"database","qname":"9f3bx2.status.example.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:00:20Z","source":"db-01","role":"database","qname":"6a8qr1.status.example.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:00:39Z","source":"db-01","role":"database","qname":"x2m7p9.status.example.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:01:04Z","source":"db-01","role":"database","qname":"q7c2h4.status.example.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:01:27Z","source":"db-01","role":"database","qname":"n9v4t8.status.example.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:01:49Z","source":"db-01","role":"database","qname":"8k2z5m.status.example.","qtype":"A","rcode":"NXDOMAIN"}
{"time":"2026-11-28T09:02:05Z","source":"db-01","role":"database","qname":"monitoring.internal.example.","qtype":"A","rcode":"NOERROR"}
~~~

**Tên .invalid** dùng để minh họa tên không tồn tại; **.example** dùng cho tài liệu. Các responses NOERROR/NXDOMAIN ở đây là **nhãn của bộ dữ liệu giả lập**, không mô phỏng kết quả DNS thật trên Internet. Tên db-01/status.example không được khẳng định là độc hại.

### 14.3. Xem sự kiện ở dạng bảng

~~~bash
# Chỉ xử lý file JSONL offline vừa tạo.
jq -r '[.time, .source, .qname, .qtype, .rcode] | @tsv' dns_lab.jsonl
~~~

Tác vụ này không gửi truy vấn mạng. Nếu chưa cài **jq**, không bắt buộc cài trên production system; có thể dùng công cụ đọc JSON được phê duyệt trong lab.

### 14.4. Đếm NXDOMAIN theo nguồn

~~~bash
jq -s '
  group_by(.source)
  | map({
      source: .[0].source,
      total: length,
      nxdomain: (map(select(.rcode == "NXDOMAIN")) | length),
      unique_qnames: ([.[].qname] | unique | length)
    })
  | map(. + {
      nx_ratio: (if .total > 0 then .nxdomain / .total else null end)
    })
' dns_lab.jsonl
~~~

Kỳ vọng từ bộ dữ liệu này:

| Source | Tổng transactions | NXDOMAIN | Unique QNAME | Tỷ lệ NXDOMAIN |
| --- | ---: | ---: | ---: | ---: |
| **web-01** | 3 | 0 | 2 | 0% |
| **dev-01** | 4 | 1 | 4 | 25% |
| **db-01** | 7 | 6 | 7 | khoảng 85,7% |

**Tỷ lệ db-01 cao là tín hiệu cần xem tiếp**, nhưng tập chỉ 14 events, giả lập và không có baseline lịch sử. Không dùng số liệu này để xác lập ngưỡng production.

### 14.5. Group theo role để phát hiện source lệch đồng cấp

Nếu có nhiều thiết bị cùng role, có thể tính **trung vị/phân vị metrics của peer group**. Trong lab nhỏ này, role **database** chỉ có một host nên **không đủ peer data** để suy ra mẫu ổn định.

Một hướng phân tích:

~~~text
feature source=db-01:
  nx_ratio = 6/7
  unique_qnames = 7
  queries to status.example = 6

Questions:
  Is db-01 expected to perform external DNS lookups?
  Which process initiated them?
  Did a deployment or agent update occur?
  Does network flow evidence show a follow-up connection?
  Is resolver/client attribution reliable?
~~~

### 14.6. Nhận diện lỗi và kết luận cho phép

Một kết quả lab tốt:

> “db-01 có tỷ lệ NXDOMAIN và số unique names cao trong 09:00–09:02 so với hai nguồn khác. Cần xác minh role, owner/process, resolver mapping và change records. Chưa thể kết luận DGA, DNS tunneling hoặc thất thoát dữ liệu từ mẫu này.”

Đây là cách viết **evidence-based**: ghi **điều đã đo**, **giả thuyết** và **bằng chứng còn thiếu**.

### 14.7. Bài kiểm thử nhạy cảm dữ liệu

Không thêm user emails, device serials, tokens hay khách hàng thật vào **subdomain** để “kiểm tra DLP”. Nếu muốn kiểm thử khả năng masking, dùng chuỗi giả không liên quan người thật, rồi xác minh log pipeline không giữ raw payload ngoài phạm vi đã duyệt.

## 15. Lab có quyền: Kiểm tra đường phân giải và năng lực telemetry

### 15.1. Chuẩn bị

Lab này chỉ áp dụng trong **VM, container/cluster hoặc mạng thử nghiệm thuộc quyền quản trị**. Mục tiêu là gửi **một số ít câu hỏi DNS bình thường** tới resolver thử nghiệm, đối chiếu log và đo coverage. Không thử tạo hàng loạt tên để flood resolver, không thực hiện zone transfer không được cấp quyền và không gửi chuỗi chứa bí mật trong QNAME.

Chuẩn bị:

| Đối tượng | Ví dụ | Cần xác nhận |
| --- | --- | --- |
| **Client lab** | VM web-lab-01 hoặc Pod dns-lab | Có quyền tạo các truy vấn thử được duyệt |
| **Resolver lab** | enterprise resolver được phép | Đã bật query logging/metrics phù hợp |
| **Lab zone** | app.lab.example theo nội bộ | Có record đã được owner chuẩn bị |
| **Log backend** | SIEM/collector thử nghiệm | Có đúng sensor/client IDs, time/RCODE |
| **Network sensor** | CNI/host flow theo đường đi | Không mất event hoặc có chỉ báo sampling |

Đây là tên giả để hướng dẫn. Không giả định **app.lab.example** đã có trên DNS public; nếu chưa có zone nội bộ, chỉ dùng domains/records được chủ lab cung cấp.

### 15.2. Kiểm tra cấu hình DNS tại client

Trên Linux lab, các lệnh **chỉ đọc**:

~~~bash
cat /etc/resolv.conf
ip -br address
ip -4 route show
ip -6 route show
~~~

Từ đó xác định DNS server và search domains mà client hiện thấy. Lưu ý **/etc/resolv.conf** có thể do systemd-resolved/NetworkManager, DHCP, container runtime hoặc Kubernetes tạo ra; nó không nhất thiết thể hiện hết upstream resolver path. Trên hệ thống tối giản có thể thiếu một số tiện ích.

### 15.3. Truy vấn DNS có giới hạn

Chỉ khi có **resolver và lab FQDN thật**:

~~~bash
# Thay <lab-resolver-ip> và app.lab.example bằng thông số được cấp quyền.
# Một query ngắn cho A record, không tải nội dung ứng dụng.
dig @<lab-resolver-ip> app.lab.example. A +time=2 +tries=1

# Query AAAA để kiểm tra dual-stack; không có AAAA có thể bình thường.
dig @<lab-resolver-ip> app.lab.example. AAAA +time=2 +tries=1
~~~

**Lệnh dig thực hiện truy vấn mạng**, không đơn thuần đọc cấu hình. Do vậy chỉ chạy trong môi trường được phép; không dùng các địa chỉ/tên giả chưa tồn tại làm kết quả nghiệm thu.

Đối chiếu:

1. Log có ghi đúng QNAME/QTYPE không?
2. **RCODE** là gì và có đúng với cấu hình zone không?
3. **Client IP** ở resolver có đúng endpoint, forwarder hay NodeLocal cache?
4. Response latency ở dig và resolver có nhất quán trong giới hạn điểm đo?
5. Một câu hỏi từ client xuất hiện thành bao nhiêu events trong pipeline?
6. Có thể gắn **Pod UID/process** một cách có bằng chứng hay chỉ là source IP?

### 15.4. Không đánh đồng một response NXDOMAIN với policy block

Trong môi trường lab, có thể thử một tên không tồn tại do owner chọn và dự đoán **NXDOMAIN** khi resolver hoạt động. Tuy nhiên:

- Một DNS security product có thể **sinkhole/rewrite** câu trả lời thay NXDOMAIN.
- Một private zone có wildcard, split-horizon hoặc forwarding có thể cho response khác.
- NODATA và NXDOMAIN khác nhau; kiểm tra QTYPE và answer/authority sections.
- Thời gian chờ hoặc SERVFAIL không phải cùng nghĩa với NXDOMAIN.

**Expected result phải dựa vào cấu hình resolver và zone thực**, không dựa vào một giả định “tên trông lạ chắc chắn NXDOMAIN”.

### 15.5. Quan sát Kubernetes/DNS server chỉ đọc

Trong cluster lab được cấp RBAC:

~~~bash
# Pod DNS service và deployment inventory nếu namespace đó được phép xem.
kubectl get pods -n kube-system -o wide
kubectl get services -n kube-system

# DNS config từ Pod thuộc lab; thay tên pod thật.
kubectl describe pod -n dns-lab <pod-name>

# Các policy egress có thể chặn đường tới resolver.
kubectl get networkpolicies -n dns-lab
~~~

Các lệnh trên không trực tiếp chứng minh DNS query đã được log hay NetworkPolicy có hiệu lực; cần xác minh **CNI flow verdict, resolver access logs và actual Pod DNSPolicy/dnsConfig**.

Không xem toàn bộ log production của CoreDNS mà không có phạm vi, vì chúng có thể chứa **tên dịch vụ nội bộ và thông tin cá nhân/khách hàng**. Nếu hệ thống hỗ trợ filter theo namespace/source/time và RBAC, ưu tiên truy vấn giới hạn.

### 15.6. So sánh sensor points có chủ đích

Một kết quả lab có thể:

| Điểm quan sát | Kỳ vọng | Khi không thấy |
| --- | --- | --- |
| **Endpoint** | Sự kiện process hỏi tên (nếu EDR hỗ trợ) | Kiểm tra agent/OS cache/telemetry scope |
| **Pod/host sensor** | DNS flow tới resolver được duyệt | Kiểm tra namespace, interface, packet sampling |
| **Recursive resolver** | Query event hoặc cache/response event | Có thể NodeLocal hit hoặc khác resolver |
| **Authoritative** | Có thể thấy truy vấn upstream nếu không có cache | Không bắt buộc thấy một query cho mỗi client |
| **SIEM** | Event normalized đúng client/sensor/time | Kiểm tra queue, parser, collector, auth |

**Kết quả “không thấy authoritative event” khi recursive cache hit không có nghĩa sensor bị hỏng.** Lab phải có **mục tiêu rõ cho mỗi điểm đo**.

### 15.7. Kiểm thử mất dữ liệu telemetry

Trong staging/lab được chủ hạ tầng phê duyệt, có thể mô phỏng collector bị mất nguồn dữ liệu hoặc cho sensor ngừng xuất trong thời gian ngắn **mà không làm gián đoạn DNS service**. Mục tiêu là:

- Detector **coverage gap** phát cảnh báo.
- Alerts security khác không tuyên bố “bình thường” từ dữ liệu thiếu.
- Khi pipeline phục hồi, trạng thái backlog/ingest lag được ghi.
- Nếu không có replay của giai đoạn thiếu, incident timeline phải ghi rõ khoảng trống.

**Không cố tình tắt log production hoặc DNS resolver để thử** khi chưa có cửa sổ bảo trì và phê duyệt rõ.

## 16. Case study: DNS NXDOMAIN tăng sau rollout hay DGA?

### 16.1. Bối cảnh

Một tổ chức vận hành hai môi trường:

- **Cluster production shop:** Pods đặt hàng dùng CoreDNS và NodeLocal DNSCache.
- **Endpoint fleet:** máy nhân viên có EDR và truy cập Internet qua DNS resolver được duyệt.

Dashboard báo:

> “NXDOMAIN ratio tăng đột biến từ 6% lên 47% trong 15 phút, đồng thời unique QNAME tăng.”

Đây là **số liệu giả lập trong case study**, không phải quan sát thực. Hãy tránh quy ngay toàn bộ cluster hoặc user endpoints bị tấn công.

### 16.2. Timeline giả lập

| UTC | Nguồn | Dữ kiện |
| --- | --- | --- |
| 09:00 | GitOps | Rollout service checkout v2 với cấu hình service name mới |
| 09:02 | CoreDNS metrics | NXDOMAIN tăng ở source từ vài node/pods |
| 09:03 | Resolver logs | Nhiều lookup của checkout-api theo search domains |
| 09:04 | App traces | Checkout tăng lỗi lookup dependency |
| 09:05 | CNI network | Không có unexpected external egress từ checkout trong coverage đã đo |
| 09:06 | EDR endpoint | Một máy nhân viên khác cũng có nhiều QNAME high-entropy, nhưng không nằm trong checkout namespace |
| 09:08 | Config diff | App checkout đang gọi service tên không tồn tại |
| 09:10 | SOC | Tách thành hai giả thuyết và hai chủ sở hữu điều tra |

### 16.3. Phân tích sự cố checkout

**Giải thích hợp lý:** checkout v2 cấu hình sai tên service, resolver thực hiện search suffix expansion và trả NXDOMAIN. Bằng chứng:

1. NXDOMAIN bắt đầu ngay sau rollout.
2. QNAME có suffixes nội bộ và liên quan cùng dependency.
3. App logs ghi lỗi phân giải tên.
4. Source Pod UID gắn đúng Deployment checkout v2.
5. Các Pods chưa rollout không có mẫu tương tự.

Đây là **availability/configuration issue** có đủ bằng chứng, không phải DGA chỉ vì NXDOMAIN ratio tăng.

**Khắc phục:** sửa tên dependency tại source-of-truth, rollout canary, xác nhận DNS success và app health. Không block toàn bộ internal suffix hoặc cô lập checkout Pods mà không có bằng chứng compromise.

### 16.4. Phân tích sự kiện endpoint riêng

Máy nhân viên tạo nhiều QNAME high-entropy ở một parent domain không thuộc approved software inventory. Dữ kiện này vẫn **chưa đủ kết luận malware**. SOC cần:

- Đối chiếu EDR **process tree, signer, start time, recent downloads**.
- Xem parent domain có thuộc browser telemetry/enterprise software không.
- Kiểm tra **response RCODEs, distinct-label ratio, timing**.
- Xem có follow-up outbound connections tới IP trả về không.
- Kiểm tra endpoint DNS settings/DoH policy và resolver coverage.
- Xem asset role/user environment và các change events.

Nếu phát hiện process đáng ngờ, outbound vi phạm policy và dấu hiệu chiếm quyền, có thể nâng cấp incident theo runbook. Nếu là một agent mới được duyệt, detector nên được **điều chỉnh theo role/software**.

### 16.5. Bài học về correlation

Một dashboard cấp resolver có thể trộn:

- Kubernetes DNS search expansion lỗi.
- Browser/EDR agent telemetry hợp lệ.
- DNS queries của một endpoint thực sự đáng nghi.
- Forwarder retries sau upstream lỗi.

**Không nên điều tra hoặc containment theo resolver-wide KPI đơn lẻ.** Phải phân nhóm **asset/workload, QNAME suffix, process, event time và dữ liệu nguồn**.

### 16.6. Câu hỏi luyện tập case

1. Vì sao NXDOMAIN ratio 47% không tự chứng minh DGA?
2. Làm sao xác định lỗi checkout đến từ rollout?
3. Vì sao CoreDNS source IP có thể không phải Pod thật?
4. Khi client query nhiều short names có search suffixes, nên nhóm thế nào?
5. Trường nào cho biết query đã có DNS response thay vì timeout?
6. Tại sao DNS answer A không chứng minh app đã gọi IP đó?
7. High entropy trên endpoint có thể do phần mềm hợp lệ nào?
8. Để khẳng định exfiltration cần evidence ngoài DNS gì?
9. Khi sensor bị mất một phần dữ liệu, trình bày confidence thế nào?
10. Vì sao giải pháp đúng cho checkout không phải “chặn tên miền lạ”?

**Gợi ý:** (1) baseline/search expansion/operational context; (2) GitOps, Pod UID, app logs, event time; (3) NodeLocal/forwarder/NAT; (4) phân biệt internal suffix và dependency gốc; (5) response RCODE và event_type; (6) cache/unused answer/proxy; (7) update/telemetry/analytics; (8) app/endpoint data audit, flows, DLP; (9) ghi gap và unknown, không suy đoán; (10) cần sửa config và xác minh resolver/app health.

## 17. Bảo mật pipeline DNS và quyền riêng tư

### 17.1. DNS query không phải dữ liệu vô hại

Tên truy vấn có thể vô tình chứa **mã khách hàng, tên máy, hệ thống nội bộ, thiết bị, đường dẫn service, UUID hoặc thậm chí token nếu ứng dụng sai thiết kế**. Do đó DNS telemetry có thể tiết lộ:

- Thói quen truy cập dịch vụ của cá nhân/nhóm.
- Tên vùng nội bộ, cluster và kiến trúc hệ thống.
- Lịch hoạt động và dependency graph của ứng dụng.
- Dữ liệu nhạy cảm nhúng trong nhãn DNS.

Không lưu toàn bộ raw DNS logs vô hạn chỉ vì nó là metadata. Phải xác định **mục đích, quyền truy cập, thời hạn giữ, masking, encryption và cơ sở pháp lý/chính sách**.

### 17.2. Cách giảm thu thập không cần thiết

1. Ưu tiên **metrics tổng hợp theo service/role/sensor** cho dashboard diện rộng.
2. Dùng **access-controlled event store** cho QNAME/device attribution chi tiết.
3. Lọc/mask những nhãn được biết là chứa identifiers nếu không cần làm bằng chứng; giữ chính sách nhất quán, không làm sai forensic evidence.
4. Không đưa raw **usernames, cookies, access tokens** vào trường tag/metric label.
5. Cân nhắc **pseudonymization** client/user IDs ở dashboard tổng hợp.
6. Giới hạn retention theo classification, incident requirements và nghĩa vụ tổ chức.
7. Audit ai đọc/xuất DNS logs, đặc biệt khi điều tra cá nhân.
8. Tách quyền **quản trị resolver** khỏi quyền **xóa logs điều tra** khi yêu cầu bảo đảm integrity.

### 17.3. Bảo vệ DNS collector

Collector có thể yêu cầu network access và API credentials để đọc telemetry. Bảo vệ bằng:

- Least-privilege identities/credentials, rotation và secret storage.
- Kết nối được mã hóa/xác thực tới log backend.
- ACL/network policy cho đường export.
- Giới hạn CPU/memory/queue/retention và khả năng backpressure.
- Versioned parser/schema và rollback khi upgrade.
- Alert khi certificate hết hạn, agent chết hoặc dropped events tăng.
- Không mở arbitrary Internet egress cho collector chỉ vì “để gửi log”.

**Collector bị chiếm có thể nhìn thấy nhiều asset names và hành vi DNS.** Vì vậy ưu tiên agent nhẹ, scope nhỏ và review quyền.

### 17.4. Dữ liệu làm bằng chứng điều tra

Khi cần lưu records dài hơn cho incident:

- Ghi **nguyên nguồn, event time, ingest time, sensor/version, normalization changes**.
- Lưu reference/hashes và kiểm soát truy cập trong kho điều tra.
- Không sửa raw event để khớp hypothesis; giữ bản chuẩn hóa riêng.
- Ghi các **khoảng trống telemetry, source identity confidence và mô tả phép suy luận**.
- Hạn chế PCAP và response payload chứa dữ liệu nhạy cảm; chỉ thu đúng phạm vi phê duyệt.

**Độ trung thực của log và khả năng giải thích dữ liệu** quan trọng hơn số trường thu thập được.

## 18. Triển khai DNS anomaly monitoring theo giai đoạn

### Giai đoạn 1 — Chọn use case và nguồn

Không bật logging toàn hệ thống ở độ chi tiết tối đa trước khi biết cần trả lời điều gì. Bắt đầu với:

- **DNS availability:** SERVFAIL/timeout/latency tăng ở resolver phục vụ production.
- **DNS policy violations:** thiết bị/workload dùng resolver không được phép.
- **Security anomaly:** NXDOMAIN + high-cardinality names ngoài baseline của workload nhạy cảm.
- **Investigation support:** có thể truy QNAME/time/source với đủ độ tin cậy.

Kiểm kê các nguồn: endpoint/EDR, office DNS, VPN DNS, cloud resolver, Kubernetes CoreDNS/NodeLocal, service mesh, egress firewall và authoritative providers. Ghi rõ **encrypted DNS scope**.

### Giai đoạn 2 — Map identity và datapath

Vẽ:

~~~text
Device / workload / process
    |
    +-- OS stub/cache
    |    +-- enterprise resolver
    |    +-- VPN conditional resolver
    |    +-- NodeLocal DNSCache -> CoreDNS
    |    +-- approved encrypted DNS resolver
    |
    +-- flow to a destination resolved from cache
    +-- direct IP connection (DNS-independent)

Evidence:
  DHCP/VPN leases, Pod UID history, EDR, NAT/forwarder mappings,
  resolver logs, egress flow verdicts, policy change audit
~~~

Nếu thiếu danh tính gốc, **đặt explicit source_attribution_confidence** và đừng tạo alerts buộc tội một process/user từ IP shared NAT.

### Giai đoạn 3 — Dựng schema và kiểm tra dữ liệu

Chuẩn hóa event_type, QNAME/QTYPE/RCODE, resolver/client, timestamps, answer summaries, policy decisions. Kiểm thử:

1. Cùng query không bị **đếm hai lần** khi có request/response.
2. Response missing không bị gán **NXDOMAIN**.
3. Có thể phân biệt **NOERROR/NODATA** với NXDOMAIN.
4. Có thể đánh dấu **cache, sampling, truncation, DNS over TCP** nếu nguồn hỗ trợ.
5. Source identity đúng với DHCP/Pod/VPN time window.
6. Log pipeline có alert khi mất hoặc trễ dữ liệu.

### Giai đoạn 4 — Đặt baseline theo peer role

Chọn thời gian phù hợp:

- Representative weekday/weekend và workload cycles.
- Release/deployment/batch và incident windows.
- Asset types, office/VPN/remote, namespaces và regions.
- Các DNS policies/resolver configurations khác nhau.

Không cho model tự học lại các đợt incident chưa được giải thích; đó là nguy cơ **normalize malicious behavior**. Xây tập **allowlisted dependencies do owner xác minh**, không phải blanket whitelist cho một public suffix lớn.

### Giai đoạn 5 — Tạo detector theo từng giả thuyết

Bắt đầu từ những rule dễ kiểm chứng:

1. Unapproved resolver paths có firewall/EDR evidence.
2. DNS availability SLO failures.
3. New parent domain từ workload nhạy cảm.
4. NXDOMAIN spike với minimum sample size.
5. Multi-signal DGA/tunneling/beacon candidates.
6. Answer drift đối với tên miền có owner rõ.

Mỗi detector cần **owner, expected data, severity, response procedure, known limitations và test cases**.

### Giai đoạn 6 — Chạy shadow mode/triage

Nếu pipeline cho phép, thử cảnh báo trước khi tự động chặn:

- Review false positives từ build systems, monitoring, CDN, telemetry, autoscaling.
- Xác nhận sensor coverage và thresholds.
- Đo **alert volume, actionable findings, investigation cost**.
- Kiểm tra sự khác biệt sau DNS/EDR/CNI upgrades.
- Đảm bảo một detector không chặn chính **resolver hoặc SOC telemetry** vì query bất thường của service đó.

### Giai đoạn 7 — Tích hợp phản hồi có kiểm soát

Các hành động có thể gồm:

- Gửi alert đến SOC/SRE đúng owner.
- Mở case với sự kiện + timeline + confidence.
- Thu thập thêm logs có giới hạn và phê duyệt.
- Tạm điều chỉnh DNS firewall policy/egress rules theo runbook.
- Endpoint isolation hoặc credential response khi có nhiều bằng chứng compromise.
- Theo dõi recovery, false-positive rollback, app health và availability.

**Không tự động block mọi newly observed domain** ở môi trường production có dependency đổi nhanh. Policy enforcement cần hiểu **scope, business criticality và nguồn dữ liệu**.

### Giai đoạn 8 — Duy trì và kiểm chứng

Sau nâng cấp:

- DNS server/CoreDNS/BIND/Unbound/PowerDNS version và log format có đổi không?
- Cloud provider service logging features, costs và data fields có đổi không?
- DHCP/VPN, managed browser DoH settings hoặc endpoint agent policy đổi không?
- IPv6/DoQ/QUIC/HTTPS RR behavior có ảnh hưởng coverage không?
- Kubernetes workload ownership labels hoặc NodeLocal rollout có làm attribution sai không?
- Có tài nguyên mới chưa có collector, retention hoặc identity mapping không?

**Không duy trì detector chỉ bằng sửa threshold**. Cần kiểm tra **coverage, parser, enrichment, false positives/negatives và rule mục tiêu**.

## 19. Dashboard, đánh giá hiệu quả và nghiệm thu

### 19.1. Dashboard theo người sử dụng

| Đối tượng | Những góc nhìn cần |
| --- | --- |
| **Network/DNS SRE** | Query rate, NXDOMAIN/SERVFAIL, response time, cache hit, upstream failures, resolver health |
| **SOC** | Suspicious sources, new domains, high-cardinality queries, denied DNS policy, cross-sensor correlations |
| **Platform/Kubernetes** | Query rate per namespace/workload, Pod UID attribution, CoreDNS/NodeLocal coverage, CNI policy drops |
| **Endpoint team** | Device/process DNS activity, unmanaged/roaming coverage, policy bypass, EDR agent health |
| **Cloud security** | Resolver rule changes, private zones, outbound paths, DNS firewall/flow logs |
| **Data protection** | Suspected data exposure via sanctioned/unsanctioned paths, application/DLP correlation |

**Không để dashboard SOC biến thành nơi mọi người có thể tra lịch DNS cá nhân.** Phân quyền chi tiết, dùng aggregated views và audit truy cập.

### 19.2. Các chỉ số đánh giá vận hành detector

| Metric | Cách dùng | Cẩn trọng |
| --- | --- | --- |
| **Coverage ratio** | Active assets có DNS/endpoint visibility / active assets trong scope | Định nghĩa active assets và source confidence |
| **Detection latency** | Event time → alert time | Phân biệt ingest lag với rule processing |
| **Alert precision** | TP/(TP+FP) trên cases có nhãn | Không coi unknown là FP/TP tự động |
| **Recall (ước lượng)** | TP/(TP+FN) trên tập kiểm thử có ground truth | FN ngoài tập kiểm thử thường không thấy |
| **False-positive workload** | Số alert/giờ hoặc triage hours tiêu tốn | Ưu tiên ảnh hưởng vận hành, không chỉ tỷ lệ |
| **Data loss rate** | Sensor dropped events/ingest failures | Sampling cố ý phải được ghi riêng |
| **Attribution completeness** | Event có source identity tin cậy | Không nhầm “có IP” với “có user/Pod UID” |
| **Parser/schema error rate** | Log bị lỗi xử lý theo nguồn/version | Upgrade có thể gây silent data loss |
| **Time-to-containment** | Thời gian từ incident được xác nhận tới control có hiệu lực | Không dùng cho mọi anomaly chưa xác nhận |
| **Availability impact** | Số service outages do detector/policy gây ra | Chặn nhầm có thể nguy hiểm |

### 19.3. Đừng báo recall giả khi không biết ground truth

Giả sử detector đánh dấu 50 events, SOC xác nhận 10 là malicious và 20 là benign, còn 20 là **unknown**. Không thể tự công bố “precision = 10/50 và recall = 100%” nếu còn unknown và chưa kiểm tra những events **không được phát hiện**.

Một báo cáo chính xác hơn:

~~~text
Alert cases: 50
Confirmed true positive: 10
Confirmed false positive: 20
Unresolved/unknown: 20
Detection coverage: specified sensor population and time range
Recall: not estimated from these alerts alone
Next validation: labeled datasets and controlled negative tests
~~~

**Độ chính xác của nhãn điều tra và phạm vi dữ liệu** quan trọng hơn một tỷ lệ đẹp nhưng không có mẫu số hợp lệ.

### 19.4. Checklist nghiệm thu kỹ thuật

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng |
| --- | --- | --- |
| **Inventory** | Đã biết resolvers/forwarders/DoH paths và phạm vi? | Architecture + asset list |
| **Source instrumentation** | Log đúng query/response event types? | Test logs theo sensor |
| **Normalization** | QNAME/RCODE/QTYPE canonical, không đếm đôi? | Parser tests và sample records |
| **Timing** | Event/ingest times và sync được kiểm tra? | Lag/clock metrics |
| **Device identity** | DHCP/VPN lease timeline chính xác? | Temporal mapping tests |
| **Pod identity** | Không gán flow cũ vào Pod IP tái sử dụng? | Pod UID/history checks |
| **Cache and forwarding** | Có biết query bị cache hoặc nguồn là forwarder? | Resolver path test |
| **Encrypted DNS** | Có nêu rõ DoH/DoT/DoQ coverage? | Endpoint/proxy policy inventory |
| **RCODE semantics** | NXDOMAIN vs NODATA vs SERVFAIL/timeout rõ? | Unit tests và lab responses |
| **Baseline** | Theo asset/workload role, deployment cycle? | Baseline report and owner |
| **Multi-signal detection** | DGA/tunneling hypotheses có correlation? | Labeled tests và review |
| **Operational alerts** | Resolver outage có alert riêng security anomaly? | SRE test và dashboard |
| **Policy bypass** | Thấy external DNS paths và direct IP flows? | CNI/firewall/EDR evidence |
| **Collector health** | Mất log tạo cảnh báo coverage? | Synthetic event/loss test |
| **Privacy** | Không lộ bí mật/PII vượt mục đích? | Access review và retention policy |
| **Investigation playbook** | Có owner, source confidence và triage flow? | Case template |
| **Block safeguards** | Có review và rollback cho domain shared/CDN? | Change approval + negative test |
| **Maintenance** | CNI/DNS/EDR upgrades được regression test? | Versioned test history |

### 19.5. Câu hỏi quyết định trước khi cho phép auto-block

Trước khi một detector chuyển từ alert sang blocking, cần trả lời:

1. **False-positive impact** với payment, identity, DNS và cloud dependencies có đo được không?
2. Rule dựa vào **nhiều tín hiệu** hay một entropy/TTL threshold yếu?
3. Block ở **DNS resolver** có thể bị direct-IP/DoH bypass không?
4. Domain là dedicated malicious host hay **shared public service**?
5. Có change review, scope, TTL/exception, rollback và owner không?
6. Nếu thu hồi quyền một endpoint, có giữ evidence và giảm ảnh hưởng business không?

**Tự động hóa phản hồi cần độ tin cậy cao hơn tự động hóa quan sát.** Một alert có thể mang tính giả thuyết; một block có thể tác động lập tức tới khách hàng và hệ thống.

## 20. Câu hỏi tự kiểm tra kèm đáp án gợi ý

**1. DNS telemetry giúp SOC làm điều gì mà flow logs IP/port không luôn làm được?**

Nó có thể cung cấp **QNAME/QTYPE/RCODE, answer và hành vi phân giải tên**, giúp xác định nguồn đang hỏi dịch vụ nào ở những điểm đo có quyền quan sát. Nhưng DNS query không chứng minh client đã kết nối thành công.

**2. Vì sao không được coi số DNS queries bằng số lần truy cập website?**

Vì OS/recursive caches, retries, prefetching và persistent HTTP connections tạo quan hệ không 1:1 giữa DNS và HTTP requests.

**3. Recursive resolver có luôn thấy địa chỉ của Pod/thiết bị gốc không?**

Không. NodeLocal cache, DNS forwarders, NAT hoặc VPN có thể khiến nó chỉ thấy source trung gian. Cần temporal mapping và sensors ở endpoint/host để quy nguồn.

**4. Một authoritative DNS server có xác định được user cuối chỉ từ source IP không?**

Không. Nó thường thấy recursive resolver làm client upstream; phải xem kiến trúc và logging trước khi quy kết.

**5. NXDOMAIN khác NODATA như thế nào?**

NXDOMAIN cho biết tên được hỏi không tồn tại theo response; NODATA là trường hợp **NOERROR nhưng không có record loại được hỏi**, dù tên có thể tồn tại.

**6. SERVFAIL có tự chứng minh DNS poisoning không?**

Không. Nó có thể do upstream errors, DNSSEC validation failures, cấu hình hoặc nhiều nguyên nhân khác; cần server/resolver logs.

**7. Một truy vấn DNS bị timeout có RCODE gì?**

Timeout không phải một RCODE server trả về. Nếu không có response, **response_rcode nên là unknown/missing**, không gán NXDOMAIN hoặc SERVFAIL.

**8. DNSSEC bảo vệ điều gì và không bảo vệ điều gì?**

DNSSEC giúp xác thực tính toàn vẹn/nguồn của DNS data theo chain trust khi validation đúng; **không mã hóa QNAME**, không ngăn app gọi malicious domain đã được ký và không thay firewall.

**9. DoH/DoT/DoQ ảnh hưởng telemetry ra sao?**

Chúng mã hóa DNS payload trên mạng, nên packet sensor không nằm ở endpoint giải mã không đọc được QNAME. Cần **endpoint/resolver telemetry** hoặc network metadata với limitations rõ ràng.

**10. Vì sao “không có DNS query tại enterprise resolver” không chứng minh endpoint không truy cập Internet?**

Client có thể có cache, hosts entry, direct-IP connection, alternate resolver hoặc encrypted DNS path.

**11. Tại sao TXT queries không tự là DNS tunneling?**

TXT có nhiều use cases hợp lệ như SPF, DKIM, domain verification và ACME. Phải xem **volume, source role, name/answer patterns và process/application context**.

**12. Shannon entropy cao ở nhãn DNS có đủ để kết luận DGA không?**

Không. UUID, hashes, telemetry IDs và cache busting có thể entropy cao; DGA dạng từ điển có thể thấp. Entropy chỉ là một feature.

**13. Nếu một source có 1 NXDOMAIN trên 1 query, ratio 100% có đáng báo động hơn 800/1000 không?**

Không thể so theo ratio một mình; cần minimum sample size, absolute count, baseline và vai trò source.

**14. Tại sao search suffix trong Kubernetes có thể gây nhiều NXDOMAIN?**

Resolver có thể thử tên rút gọn kết hợp các suffixes theo cấu hình/ndots. Những tên trung gian không tồn tại có thể tạo NXDOMAIN hợp lệ.

**15. Vì sao Pod IP phải được gắn với event time và UID?**

Pod IP có thể tái sử dụng; truy vấn lịch sử theo IP hiện tại dễ gán sự kiện cho workload khác.

**16. Một client hỏi A record, nhận hai public IP, nghĩa là cả hai đã được kết nối?**

Không. DNS answer chỉ cung cấp lựa chọn; client có thể chọn một IP, không dùng IP nào hoặc dùng proxy.

**17. Tại sao TTL thấp không đủ để kết luận fast-flux?**

CDN, failover và provider routing có thể dùng TTL ngắn; TTL nhìn qua cache có thể đã giảm. Cần historical answers, provider/context và network evidence.

**18. “Periodic query mỗi 60 giây” có phải C2 chắc chắn?**

Không. Health checks và monitoring agents cũng tuần hoàn; phải ghép domain prevalence, process, destination và asset role.

**19. Kết quả NOERROR có nghĩa application request thành công không?**

Không. HTTP/TLS/network policy/app authorization có thể vẫn thất bại.

**20. Khi phản hồi DNS trả IP không mong đợi, cần xác minh gì?**

Resolver viewpoint, split DNS/private zone, cloud DNS change history, CDN/provider, DNSSEC/trust và TLS destination identity. Không kết luận hijack chỉ từ một IP khác.

**21. Vì sao không tách registered domain bằng hai labels cuối của QNAME?**

Public suffixes có thể nhiều nhãn và private/internal zones có quy tắc riêng. Cần Public Suffix List hoặc bộ zone phù hợp.

**22. RCODE NXDOMAIN cao trên nhiều Pods sau rollout hướng tới giả thuyết gì?**

Có thể do service name/config sai, DNS search expansion hoặc upstream issue; phải xem Deployment/Pod UID, resolver logs và app traces trước khi suy ra DGA.

**23. Vì sao một DNS transaction có thể tạo nhiều log records?**

Vì endpoint, network sensor, resolver query và response logging cùng quan sát; cần event_type/observation_point và dedup/correlation.

**24. Có thể dùng DNS transaction ID một mình làm global event key không?**

Không. DNS ID là trường ngắn trong ngữ cảnh kết nối/transaction; retries và nhiều clients có thể trùng. Dùng sensor, tuples, QNAME/QTYPE và time window phù hợp.

**25. Thế nào là một alert DNS có thể hành động?**

Nó có **source identity/confidence, time, QNAME group, RCODE/metrics, baseline, rule ID, correlation, business owner và điều chưa biết**, kèm hướng triage/rollback phù hợp.

**26. Vì sao không nên block một CDN IP chỉ vì một domain dưới đó đáng ngờ?**

IP có thể được dùng chung cho nhiều dịch vụ hợp lệ; block rộng có thể gây outage. Cần đánh giá **host/service-specific policy, provider context và scope**.

**27. Flow DNS ngoài policy khác điều tra exfiltration như thế nào?**

Flow ngoài policy có thể chứng minh **vi phạm đường kết nối** khi attribution/enforcement đáng tin; chứng minh **dữ liệu bị lấy cắp** đòi hỏi thêm data access/application audit, DLP, content evidence và timeline.

**28. Tại sao cần metrics collector health bên cạnh DNS QPS?**

QPS có thể về 0 do sensor/log export ngừng, không phải vì clients không query. Heartbeat, loss rate và independent activity giúp phát hiện coverage gap.

**29. DNS logs có phải dữ liệu phi cá nhân mặc định không?**

Không. QNAME/source identity có thể tiết lộ hành vi và identifiers; cần data minimization, access control, retention và privacy review.

**30. Khi nào DNS anomaly detection được coi là hoàn chỉnh?**

Khi có **phạm vi cảm biến và điểm mù rõ, schema đúng, identity theo thời điểm, baseline theo nguồn, detector được test, SOC/SRE runbook, telemetry health, privacy và bằng chứng hậu kiểm**. Không chỉ vì dashboard có biểu đồ NXDOMAIN.

## 21. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Mọi network connection phải có một DNS query ngay trước đó.” | Cache, proxy, hosts, direct IP và connection reuse có thể không tạo query mới. |
| “Resolver thấy query nghĩa user đã mở website.” | Lookup không chứng minh kết nối hoặc hành động app. |
| “Một query DNS là một network request.” | Các tầng cache và transaction logging làm mối quan hệ khác nhau. |
| “NXDOMAIN luôn do malware.” | Gõ sai tên, search suffix, deploy hoặc cấu hình có thể tạo NXDOMAIN. |
| “NXDOMAIN và SERVFAIL giống nhau.” | Một bên là name error; một bên là server không xử lý thành công. |
| “No answer nghĩa là NXDOMAIN.” | NOERROR/NODATA, timeout, SERVFAIL là những trường hợp khác. |
| “DNS response NOERROR nghĩa HTTP success.” | DNS và ứng dụng là hai lớp độc lập. |
| “TXT record là dấu hiệu DNS tunneling.” | TXT có nhiều ứng dụng hợp lệ, cần kết hợp tín hiệu. |
| “Entropy cao chứng minh DGA.” | UUID/hashes/telemetry cũng entropy cao; một số DGA dùng từ điển. |
| “Entropy thấp loại trừ DGA.” | Thuật toán tên theo từ điển/kiểu có cấu trúc có thể entropy thấp. |
| “Một truy vấn định kỳ là beacon độc hại.” | Health checks, agents và scheduling có thể rất đều. |
| “TTL thấp chứng minh fast flux.” | CDN, caching và failover cũng có TTL ngắn. |
| “Đổi DNS answer là DNS hijack.” | Region/CDN/private zones và DNS changes hợp lệ có thể đổi answers. |
| “DNSSEC làm DNS traffic bí mật.” | DNSSEC xác thực dữ liệu, không mã hóa QNAME. |
| “Domain có DNSSEC là chắc chắn an toàn.” | Domain độc hại vẫn có thể được ký hợp lệ. |
| “Có DoH nghĩa browser đang cố bypass.” | Managed/approved DoH có thể là cấu hình bảo mật hợp lệ. |
| “Mọi HTTPS tới resolver provider đều là DoH.” | Endpoint có thể cung cấp nhiều services; cần protocol/device context. |
| “Chặn UDP/53 sẽ chặn mọi DNS.” | Còn TCP/53, DoT, DoH, DoQ, cache, proxy và app-specific paths. |
| “Một sensor mạng đọc được mọi QNAME.” | Encrypted DNS, interface selection, NAT và sampling tạo điểm mù. |
| “Authoritative source IP là IP người dùng cuối.” | Thường là resolver/forwarder trung gian. |
| “Một Pod IP luôn xác định cùng workload.” | Pod IP có thể đổi/tái sử dụng, cần UID và thời gian. |
| “Process name trong EDR luôn đủ quy kết.” | Process ID/name có thể tái dùng hoặc không đầy đủ; cần lineage/timestamps. |
| “Cloud DNS logs tự biết Kubernetes service account.” | Chỉ khi có nguồn enrichment/tính năng phù hợp; nhiều trường hợp chỉ có IP/VPC. |
| “Dùng hai labels cuối là registered domain.” | Public suffix có thể phức tạp; private zones có rules riêng. |
| “Tỷ lệ NXDOMAIN 100% với 1 query rất nguy hiểm.” | Mẫu quá nhỏ; phải xét count và baseline. |
| “Cài query logger là detector tự biết chủ thể gốc.” | Forwarder/NAT/NodeLocal có thể che nguồn; cần identity history. |
| “Không có alert là không có suspicious DNS.” | Sensor có thể không phủ hoặc mất dữ liệu; unknown không bằng safe. |
| “Không thấy DNS query nghĩa source không ra Internet.” | Direct IP/caches/alternate encrypted DNS có thể nằm ngoài view. |
| “Block ở DNS đủ ngăn mọi egress.” | Client có thể gọi IP trực tiếp; firewall/proxy vẫn cần. |
| “Một parent domain lạ luôn phải block toàn tổ chức.” | Có thể là vendor legitimate hoặc shared infrastructure; cần owner/approval. |
| “DNS telemetry có thể chứng minh dữ liệu đã bị đánh cắp.” | Chỉ dấu hiệu; cần application/endpoint data evidence và incident analysis. |
| “Log càng nhiều raw payload càng tốt.” | DNS names có thể lộ identifiers/secrets; cần privacy/retention. |
| “SIEM đã ingest log là data không thể thiếu.” | Schema errors, lag, dropped events và source outages vẫn xảy ra. |
| “Cứ tăng threshold là giải quyết false positives.” | Cần sửa attribution, normalize, baseline và use-case logic trước. |
| “Thêm auto-block cho mọi anomaly là Zero Trust.” | Chặn sai gây outage; cần confidence, policy scope và rollback. |

## 22. Tổng kết

**DNS telemetry cho phát hiện truy vấn bất thường** mang lại góc nhìn quan trọng vào **hành vi phân giải tên của thiết bị, ứng dụng và workload**. Nhưng một tên được hỏi **không tự chứng minh** một kết nối đã xảy ra; một NXDOMAIN **không tự chứng minh** DGA; một nhãn entropy cao **không tự chứng minh** tunneling hoặc thất thoát dữ liệu.

Một hệ thống có giá trị cần:

1. **Hiểu luồng phân giải và cache:** stub, NodeLocal, recursive, forwarder, authoritative, DNSSEC và encrypted DNS có điểm quan sát khác nhau.
2. **Thu đúng dữ liệu:** QNAME/QTYPE/RCODE, answer/TTL, client/resolver identity, timestamps, event type, policy action và sensor health khi có.
3. **Gắn identity theo thời gian:** DHCP, VPN, Pod UID, NAT/forwarder và endpoint process; không quy từ current IP hay user chưa được xác minh.
4. **Chuẩn hóa/correlation cẩn thận:** tránh đếm đôi query/response, phân biệt NXDOMAIN/NODATA/SERVFAIL/timeout và ghi rõ source confidence.
5. **Baseline theo workload/role:** query volume, unique names, NXDOMAIN, QTYPE, entropy, periodicity và answer changes phải được đặt vào context.
6. **Detector nhiều tín hiệu:** DGA-like, DNS tunneling candidate, suspicious beacon, resolver bypass và answer drift phải có điều kiện, giới hạn và test.
7. **Kết hợp mạng và ứng dụng:** DNS + firewall/CNI flows + proxy/TLS + EDR + cloud/IAM + app/data audit giúp phân biệt nghi vấn với bằng chứng.
8. **Giữ khả năng vận hành:** resolver SLO, pipeline health, alerts có owner, false-positive feedback, privacy, retention và kiểm thử định kỳ.
9. **Phản hồi theo mức tin cậy:** không tự động cô lập thiết bị chỉ từ một QTYPE/entropy; tách DNS health issue khỏi security incident.

Trong học phần **SECURITY_NETWORK_SECURITY**, DNS telemetry là cầu nối giữa **bảo vệ DNS, IDS/IPS/NDR, network segmentation, kiểm soát egress, VPN, cloud/Kubernetes, xác thực dịch vụ và ứng phó xâm nhập**. Chất lượng của một chương trình DNS monitoring không được đo bằng **số lượng log thu thập**, mà bằng **khả năng trả lời có bằng chứng: ai hỏi tên nào, ở đâu, lúc nào, có điều gì khác thường, và còn thiếu dữ liệu gì để hành động an toàn**.

### Tài liệu tham khảo và hướng đọc thêm

- **RFC 1034 — Domain Names: Concepts and Facilities:** kiến trúc tên miền, các thành phần và phân giải.
- **RFC 1035 — Domain Names: Implementation and Specification:** DNS message sections, header/flags, questions và resource records.
- **RFC 2308 — Negative Caching of DNS Queries (DNS NCACHE):** negative caching, NXDOMAIN/NODATA considerations.
- **RFC 8499 — DNS Terminology:** thuật ngữ resolver, authoritative, cache, delegation và DNS response.
- **RFC 6891 — Extension Mechanisms for DNS (EDNS(0)):** DNS extensions và OPT pseudo-RR.
- **RFC 4033, RFC 4034, RFC 4035 — DNS Security Extensions:** DNSSEC concepts, resource records và protocol validation.
- **RFC 7858 — Specification for DNS over Transport Layer Security (TLS):** DoT và trust requirements.
- **RFC 8484 — DNS Queries over HTTPS (DoH):** DNS mapping vào HTTPS, visibility/trust considerations.
- **RFC 9250 — DNS over Dedicated QUIC Connections:** DoQ transport.
- **RFC 9460 — Service Binding and Parameter Specification via the DNS (SVCB and HTTPS RRs):** loại record mới ảnh hưởng query distributions.
- **RFC 8767 — Serving Stale Data to Improve DNS Resiliency:** stale cache responses và availability.
- **RFC 6761 — Special-Use Domain Names:** các tên dành cho mục đích đặc biệt, ví dụ .invalid.
- **RFC 2606 — Reserved Top Level DNS Names:** .example và các tên dùng cho tài liệu.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** IP addresses minh họa trong bài.
- **MITRE ATT&CK — T1071.004 Application Layer Protocol: DNS, T1568.002 Domain Generation Algorithms:** tham khảo ý tưởng phát hiện, không thay bằng chứng điều tra.
- **NIST SP 800-61 — Computer Security Incident Handling:** quy trình nhận diện, phân tích, ứng phó và lessons learned; đối chiếu bản hiện hành khi triển khai.
- **NIST SP 800-207 — Zero Trust Architecture:** sử dụng tín hiệu mạng/danh tính và policy để giảm quyền truy cập theo tài nguyên.
- **OWASP SSRF Prevention Cheat Sheet:** DNS resolution, URL allowlisting và kiểm soát luồng yêu cầu ra ngoài.
- **Kubernetes Documentation — DNS for Services and Pods, CoreDNS, Pod Lifecycle:** resolver configuration, search domains và mapping Pod identity.
- **BIND 9 / Unbound / PowerDNS Recursor / CoreDNS documentation:** query logging, dnstap, metrics, cache/forwarding và giới hạn dữ liệu theo phiên bản.
- **AWS Route 53 Resolver Query Logging, Azure DNS và Google Cloud DNS logging documentation:** cloud DNS fields, phạm vi ghi log, identity và retention theo provider.
- **OpenTelemetry và SIEM/NDR/EDR documentation của hệ thống đang triển khai:** pipelines, schema, entity correlation và sensor health.
- **Public Suffix List/IDNA specifications và tài liệu thư viện parser được sử dụng:** phân nhóm registered domain và chuẩn hóa DNS names.
