# Phân biệt lỗi ứng dụng với lỗi network bằng packet capture và phân tích lưu lượng

## 1. Mục tiêu và vấn đề thực tế

Khi người dùng báo “ứng dụng chậm”, “không đăng nhập được” hoặc “API timeout”, triệu chứng quan sát ở màn hình chưa cho biết nguyên nhân nằm ở mạng hay ở ứng dụng. Một lần truy cập có thể đi qua DNS, firewall, NAT, load balancer, VPN, reverse proxy, TLS termination, máy chủ ứng dụng, database và dịch vụ bên thứ ba. Lỗi tại một khâu có thể xuất hiện ở khâu khác dưới dạng `connection reset`, `502`, `504` hoặc `timeout`.

Bài học thuộc chương **Packet capture và phân tích lưu lượng** của module **SECURITY_NETWORK_SECURITY**. Việc phân biệt sự cố là kỹ năng quan trọng khi vận hành mạng an toàn: giám sát IDS/IPS, firewall, phân đoạn mạng, VPN, DNS, lưu lượng đám mây và các kết nối có xác thực. Packet capture (PCAP) hỗ trợ dựng lại diễn biến gói tin; kết luận đáng tin cần đặt PCAP bên cạnh metric, log và distributed tracing.

Sau bài này, bạn có thể:

- Xác định lỗi xảy ra **ở giai đoạn nào** của một yêu cầu từ client đến ứng dụng.
- Dùng thông tin TCP/UDP, DNS, TLS, HTTP, ICMP và thời gian phản hồi để phân biệt một số nhóm nguyên nhân.
- Đọc các dấu hiệu retransmission, RST, zero window, handshake failure, 4xx/5xx và request latency đúng ngữ cảnh.
- Lựa chọn vị trí bắt gói và đối chiếu hai đầu kết nối để kiểm chứng giả thuyết.
- Biết giới hạn của PCAP với HTTPS, HTTP/2, HTTP/3 (QUIC), NAT, offload và capture loss.
- Viết kết luận có bằng chứng, mức độ chắc chắn và nhóm cần phối hợp xử lý.

> **Tư duy quan trọng:** “Lỗi network” và “lỗi ứng dụng” không phải hai hộp hoàn toàn tách biệt. Sự cố ứng dụng có thể làm đầy hàng đợi và gây timeout ở tầng vận chuyển; chính sách firewall hoặc load balancer có thể tạo HTTP 503. Hãy xác định **điểm đầu tiên xuất hiện hành vi sai** và phạm vi ảnh hưởng thay vì quy lỗi theo thông báo cuối cùng.

## 2. Mô hình một yêu cầu đi từ client tới ứng dụng

~~~mermaid
flowchart LR
    C["Client / Browser"] --> R["DNS resolver"]
    C --> E["LAN / Wi-Fi / VPN / Firewall"]
    E --> L["LB / Proxy / TLS gateway"]
    L --> S["Ứng dụng / API"]
    S --> D["Database / Cache / Dịch vụ ngoài"]
    D --> S
    S --> L
    L --> E
    E --> C
~~~

Luồng này có thể giản lược hoặc thay đổi: DNS thường xảy ra trước khi kết nối, ứng dụng có thể dùng kết nối đã mở, proxy có thể giải mã TLS rồi mở kết nối TLS mới đến backend. Khi điều tra, cần ghi rõ **điểm quan sát** vì mỗi điểm thấy tập gói và địa chỉ khác nhau.

| Giai đoạn | Client muốn làm gì? | Bằng chứng có thể quan sát | Nhóm nguyên nhân thường gặp |
|---|---|---|---|
| 1. Phân giải tên | Có IP cho tên dịch vụ | DNS query/response, mã kết quả, độ trễ, cache | DNS, cấu hình tên miền, resolver, chính sách chặn |
| 2. Kết nối mạng/vận chuyển | Thiết lập TCP hoặc trao đổi QUIC/UDP | SYN/SYN-ACK/ACK, ICMP, UDP, thay đổi đường đi | Routing, ACL, firewall, NAT, mất gói, endpoint không lắng nghe |
| 3. Thiết lập bảo mật | TLS handshake và xác thực server | TLS ClientHello/ServerHello/Alert khi thấy được; lỗi ở client | Chứng chỉ, CA, SNI, ALPN, cipher/version, proxy TLS |
| 4. Gửi yêu cầu | Chuyển request đến endpoint đúng | HTTP headers khi quan sát được; proxy/access log | Sai URL, xác thực, header, body, định tuyến L7 |
| 5. Xử lý | Ứng dụng thực thi logic và gọi dependency | App logs, spans, DB metrics, server timing | Code, pool, CPU, GC, lock, DB, cache, dịch vụ phụ thuộc |
| 6. Trả kết quả | Truyền response về client | ACK, window, retransmission, response status/bytes nếu đọc được | Mất gói, nghẽn, client đọc chậm, response lớn, lỗi app |
| 7. Đóng/tái sử dụng | Giải phóng hoặc giữ kết nối | FIN, RST, idle timeouts, keep-alive | Timeout, cấu hình pool/LB, giới hạn kết nối |

Không nên mặc định mọi request phải trải qua đầy đủ các bước: DNS có thể được cache, TCP và TLS có thể được tái sử dụng, QUIC gom nhiều pha kết nối và TLS 1.3, HTTP/2 hoặc HTTP/3 có thể multiplex nhiều request trên một kết nối.

### 2.1. Xác định ranh giới cần kiểm tra

Đối với sự cố “đăng nhập chậm”, cần tách những câu hỏi:

1. Client có phân giải đúng IP theo môi trường (prod/staging, IPv4/IPv6, DNS split-horizon) không?
2. Có thiết lập được kết nối đến điểm cuối tiếp nhận, hay gặp SYN timeout/RST?
3. TLS handshake thành công không; nếu thất bại, lỗi xác thực chứng chỉ hay đường truyền?
4. Request có tới reverse proxy/backend không; backend có bắt đầu xử lý không?
5. Nếu request tới app, phần thời gian chậm nằm ở ứng dụng, database hay chờ truyền response?
6. Client nhận đủ byte và hiển thị chậm, hay server thực sự chưa trả nội dung?

Trả lời từng câu bằng bằng chứng giúp tránh suy luận “ping thành công nên network tốt” hoặc “HTTP 500 nên chắc chắn lỗi code”.

## 3. Lập baseline và thu thập bằng chứng đa nguồn

**Baseline** là hành vi khi hệ thống hoạt động bình thường: latency p50/p95/p99, tỷ lệ lỗi, lưu lượng, RTT, retransmission, HTTP status theo endpoint, DNS latency và thời gian xử lý server. So sánh với baseline ở cùng khu vực, thời điểm, phiên bản và lượng tải để tránh đánh giá sai.

Các nguồn chứng cứ bổ trợ cho nhau:

| Nguồn | Giúp trả lời | Giới hạn |
|---|---|---|
| **PCAP tại client** | Client gửi/nhận packet gì, mốc thời gian và thứ tự | Có thể không thấy nội dung TLS; NIC offload và packet drop có thể làm sai biểu hiện |
| **PCAP tại server/LB** | Gói thực sự đến đâu, phản hồi từ điểm đó | NAT/proxy đổi tuple; capture ở proxy không đại diện cho backend |
| **DNS logs** | Resolver dùng kết quả nào, TTL, NXDOMAIN/SERVFAIL | Cache của client có thể khiến không có DNS query mới |
| **Firewall/VPN/NAT logs, flow telemetry** | Session bị deny, SNAT hết port, route change, volume | Chỉ nhìn thấy flow/metadata; log có thể không đầy đủ |
| **HTTP proxy/access logs** | Status, upstream target, request time, upstream response time | Tên metric khác nhau giữa các proxy; status có thể do proxy tạo |
| **App logs + distributed tracing** | Request ID, handler, dependency span, exception | Instrumentation chưa phủ kín hoặc sampling làm mất trace |
| **Host và DB metrics** | CPU, memory, GC, connection pool, queue, locks, slow query | Không trực tiếp chứng minh đường truyền tốt hay xấu |
| **Synthetic test/APM** | Khác biệt theo vùng, endpoint, HTTP phase | Test có thể đi đường khác với user thật |

Trước khi bắt gói, ghi tối thiểu: thời điểm UTC và múi giờ, client IP, tên miền, IP/cổng đích (nếu biết), giao thức, request ID hoặc correlation ID, loại lỗi, số lần lặp, thiết bị/mạng truy cập, và có hay không dùng VPN, proxy, CDN. Dùng **đồng bộ thời gian NTP** để đối chiếu; timestamp lệch vài giây có thể phá hỏng kết luận về ai chờ ai.

Cần ưu tiên **tính tương quan** hơn số lượng log: một request ID xuất hiện ở proxy và ứng dụng thường hữu ích hơn hàng triệu packet thiếu ngữ cảnh. Đảm bảo request ID không chứa dữ liệu nhạy cảm hoặc token.

## 4. Bảng triệu chứng → giả thuyết → cách xác nhận

| Dấu hiệu | Giả thuyết cần xem xét | Bằng chứng để phân định |
|---|---|---|
| DNS timeout hoặc `SERVFAIL` | Resolver không phản hồi, lỗi upstream DNS, cấu hình/ACL | Query đi/đến resolver, log resolver, kiểm tra qua resolver khác được phép |
| DNS trả IP không mong đợi | Bản ghi/caching/split DNS hoặc DNS hijack | So sánh truy vấn theo resolver, TTL, môi trường và câu trả lời thực tế |
| SYN lặp, không thấy SYN-ACK tại client | Mất gói, đường đi/ACL/firewall, server/LB không phản hồi | Bắt ở hai điểm, xem route, firewall drop, SYN backlog, LB health |
| Nhận RST ngay sau SYN | Port không lắng nghe hoặc thiết bị chủ động từ chối | Nguồn RST, log host/firewall/LB, kiểm tra listening socket |
| Bắt tay TCP thành công, TLS thất bại | Chứng chỉ/SNI/ALPN/version/policy TLS hoặc giữa đường | TLS alert nếu quan sát được, lỗi chứng chỉ từ client, TLS logs ở gateway |
| TCP/TLS tốt, request chờ rất lâu trước byte response đầu | App/DB/queue/upstream chậm, hoặc mạng/luồng giữa các tầng | Access log upstream timing, tracing, capture tại nhiều điểm |
| Tăng retransmission khi tải tăng | Mất gói, congestion, queue, host quá tải, offload/capture artifact | So sánh hai đầu, interface drops, RTT, CPU, TCP stats |
| `TCP Zero Window` kéo dài | Bên nhận không đọc nhanh hoặc buffer đầy | Cửa sổ do endpoint nào quảng bá, app đọc socket, CPU/memory/GC |
| HTTP 400/401/403 | Request, auth, authorization, WAF/proxy/policy | Response tạo ở tầng nào, access/security logs, correlation ID |
| HTTP 500 | App/backend thất bại; đôi khi proxy tạo mã lỗi | Log ứng dụng, exception, response origin, upstream logs |
| HTTP 502/503/504 | LB/proxy/upstream, health check, capacity hoặc timeout | Phân biệt `upstream_connect_time`, `upstream_response_time`, backend logs |
| Download chậm sau khi response bắt đầu | TCP throughput, receive window, packet loss, client đọc/ghi chậm, máy chủ gửi chậm | TCP stream và tốc độ hai đầu, app send metrics, disk/client metrics |
| Chỉ một ISP/vùng lỗi | Đường đi, DNS/CDN, peering, firewall policy theo địa lý | So sánh endpoint và route trên cùng phiên bản dịch vụ |

**Chú ý:** đây là bảng **đặt giả thuyết**, không phải thuật toán kết luận tự động. Chẳng hạn `504 Gateway Timeout` thường do gateway/proxy hết hạn chờ upstream, nhưng upstream có thể chậm do database, socket backlog hoặc đường mạng giữa proxy và backend.

## 5. Phương pháp điều tra có thứ tự

Một quy trình thực dụng gồm sáu pha:

1. **Chuẩn hóa triệu chứng:** URL/API, operation, mã lỗi, thời điểm, thời lượng, phạm vi user, tần suất. Phân biệt “không kết nối được”, “không có response”, “có response lỗi” và “response đúng nhưng giao diện chậm”.
2. **So sánh phạm vi:** tất cả client hay chỉ một site? Chỉ IPv6, Wi-Fi, VPN hay một route? Chỉ một endpoint hay toàn bộ ứng dụng? Đặt baseline và so với lần thành công.
3. **Tách từng pha giao tiếp:** DNS → kết nối → TLS → request → xử lý → response; dùng công cụ hỗ trợ thời gian pha.
4. **Đối chiếu nhiều nguồn:** PCAP hai đầu, firewall/LB logs, app trace, metrics cùng cửa sổ UTC và correlation ID.
5. **Thử giả thuyết có kiểm soát:** chẳng hạn kiểm tra một resolver khác, chạy từ client tại vùng khác, so sánh request đơn giản và request chậm, kiểm tra health backend. Không thay đổi production tùy tiện để “xem có hết lỗi không”.
6. **Ghi kết luận và kiểm chứng khắc phục:** mô tả packet/log cụ thể, vấn đề còn chưa chứng minh, chủ sở hữu xử lý, tiêu chí hồi phục và kết quả theo dõi.

~~~mermaid
flowchart TD
    A["Người dùng báo timeout / chậm / lỗi"] --> B{"DNS trả lời phù hợp?"}
    B -->|"Không"| BD["Kiểm tra DNS resolver, cache, ACL, record"]
    B -->|"Có"| C{"TCP/QUIC đến được điểm cuối?"}
    C -->|"Không"| CN["Đối chiếu client/server PCAP, route, firewall, LB"]
    C -->|"Có"| D{"TLS và xác thực thành công?"}
    D -->|"Không"| TL["Xem cert, SNI, ALPN, TLS logs, middlebox"]
    D -->|"Có"| E{"Request đến app và response hợp lệ?"}
    E -->|"Không hoặc lỗi L7"| AP["Đối chiếu proxy log, trace, app/dependency"]
    E -->|"Có nhưng chậm"| F["Phân rã TTFB và thời gian tải dữ liệu"]
    F --> G["So sánh app span, throughput, RTT, retransmission, window"]
    BD --> H["Kiểm chứng kết luận và khắc phục"]
    CN --> H
    TL --> H
    AP --> H
    G --> H
~~~

### 5.1. Tránh kết luận từ một điểm quan sát

Nếu PCAP ở client thấy ba SYN và không có SYN-ACK, điều đó chỉ chứng minh **client không quan sát được phản hồi** tại điểm capture ấy. Chưa đủ để khẳng định “router làm mất SYN”: có thể SYN không rời NIC, ACL ở tầng khác chặn, server quá tải, hoặc SYN-ACK đi theo đường bất đối xứng và bị chặn.

Để mạnh hơn, đối chiếu theo hướng:

- **Client thấy SYN → server không thấy SYN:** xem đường đi, firewall, NAT, routing, các điểm trung gian và liệu đúng interface/địa chỉ sau NAT được bắt hay chưa.
- **Server thấy SYN và gửi SYN-ACK → client không thấy SYN-ACK:** kiểm tra đường về, ACL, định tuyến bất đối xứng, NAT mapping.
- **Server nhận và ACK đầy đủ request → app chưa bắt đầu xử lý:** xem load balancer, socket accept queue, worker pool hoặc proxy. TCP ACK chỉ xác nhận byte đã đến TCP stack, **không chứng minh app đã đọc hoặc xử lý**.
- **App xử lý nhanh, server đã gửi response → client nhận thiếu/chậm:** ưu tiên đường truyền, window và tốc độ đọc phía client; nhưng xem thêm proxy buffering và server kernel send queue.

Với NAT/LB/proxy, tuple `(src IP, src port, dst IP, dst port, protocol)` có thể đổi giữa các hop. Phải có ánh xạ từ NAT logs hoặc request ID và hiểu ranh giới **TCP được kết thúc ở đâu** trước khi so sánh seq/ack.

## 6. Đọc TCP đúng cách: từ handshake đến kết thúc phiên

### 6.1. TCP three-way handshake và từ chối kết nối

~~~text
Client                       Server
  |---- SYN, seq=x ----------->|
  |<--- SYN-ACK, seq=y, ack=x+1 |
  |---- ACK, ack=y+1 --------->|
  |        TCP established      |
~~~

Trong bắt tay bình thường, SYN, SYN-ACK, ACK xuất hiện đúng thứ tự nếu góc quan sát và thời điểm capture bao phủ cả phiên. Dấu hiệu cần phân biệt:

| Mẫu gói | Diễn giải hợp lý | Việc cần xác minh |
|---|---|---|
| SYN, SYN, SYN, không thấy SYN-ACK | TCP setup thất bại từ góc nhìn client | Có SYN ở server chưa? ACL/routing/LB/SYN backlog? |
| SYN → RST-ACK | Có thiết bị/chủ thể từ chối chủ động | RST từ máy chủ, firewall hay proxy? Port có listener? |
| SYN ↔ SYN-ACK nhưng thiếu ACK cuối | Bên gửi SYN-ACK có thể chưa thấy ACK | Bắt hai chiều, packet loss hoặc thiết bị lọc |
| Kết nối established rồi RST | Bị reset sau thiết lập | Bên nào gửi? Timeout, app close/reset, proxy, lỗi protocol? |
| FIN/ACK hợp lệ | Đóng kết nối có thứ tự | Có phải kỳ vọng của protocol và thời điểm kết thúc? |

**RST không đồng nghĩa “lỗi mạng”.** Ứng dụng đóng socket theo cách gây reset, kernel từ chối cổng, proxy timeout hoặc firewall có thể sinh RST. Hãy xác định **điểm đầu tiên phát ra hoặc đưa RST vào luồng** bằng capture gần từng đầu và log tương ứng. IP nguồn của RST không đủ để chứng minh tác nhân thật vì thiết bị trung gian có thể thay/giả địa chỉ nguồn.

### 6.2. Retransmission, duplicate ACK và RTT

TCP retransmit khi chưa xác nhận được dữ liệu theo kỳ vọng. Có thể do packet data/ACK bị mất, trễ, tái sắp xếp, timeout hoặc quan sát packet capture thiếu gói. Các nhãn `tcp.analysis.retransmission`, `fast_retransmission`, `duplicate_ack` của Wireshark là **phân tích suy ra từ trace**, không phải nhãn do TCP trên mạng gửi.

Ví dụ:

~~~text
t=0 ms     Client -> Server : Data seq=1001 len=1000
t=20 ms    Client <- Server : ACK=2001
t=40 ms    Client -> Server : Data seq=2001 len=1000
t=90 ms    Client -> Server : Data seq=2001 len=1000 (gửi lại)
t=105 ms   Client <- Server : ACK=3001
~~~

Từ một trace phía client, chỉ thấy dữ liệu `seq=2001` đã được gửi lại; **chưa đủ khẳng định** packet đầu bị rớt ở đâu. Capture ở server có thể chỉ thấy bản gửi lần hai, hoặc thấy cả hai bản (ACK trên đường về bị mất/trễ). RTT tăng, queueing và congestion cũng khiến ứng dụng chậm dù không mất kết nối hoàn toàn.

Các kiểm tra bổ sung:

- Vẽ **I/O graph** về retransmission, throughput và RTT theo thời gian; so với cửa sổ không có lỗi.
- Đối chiếu retransmission theo hướng client→server và server→client.
- Xem counters NIC/interface (drops/errors), firewall sessions, tunnel loss, congestion, host CPU và socket buffers.
- Kiểm tra TCP receive window, window scaling, ECN và thông tin congestion nếu có.
- Đừng nhầm **capture dropped packets** do công cụ hoặc packet offload (GRO/LRO/TSO/GSO/checksum offload) với lỗi thực trên dây.

Nếu máy nhận quảng bá `Zero Window`, sender phải ngừng gửi dữ liệu thường (ngoại trừ cơ chế kiểm tra cửa sổ). Nguyên nhân có thể do **ứng dụng bên nhận đọc socket chậm**, worker pool không xử lý kịp, CPU hoặc memory pressure; không nên quy ngay về thiết bị mạng.

### 6.3. MTU, fragmentation và đường truyền bất đối xứng

Một ứng dụng có thể kết nối/TLS được nhưng treo khi truyền request/response lớn. Khi đó kiểm tra MTU, PMTUD, firewall chặn ICMP cần thiết, tunneling/VPN overhead và IPv6 Packet Too Big. Dấu hiệu “gói nhỏ thành công, gói lớn lỗi” là manh mối, không đủ để kết luận MTU black hole: app cũng có thể giới hạn body hoặc xử lý file lớn chậm.

Khuyến nghị kiểm tra bằng công cụ có kiểm soát trên đúng đường đi và kết hợp counters/path logs; đừng tắt cơ chế an toàn hoặc thay MTU toàn mạng chỉ dựa trên một capture.

## 7. DNS, TLS, HTTP và QUIC: lỗi tầng nào?

### 7.1. DNS: sai tên, sai câu trả lời hay không có câu trả lời

Trình tự điều tra:

1. Client thực sự dùng resolver nào, IPv4/IPv6 có được bật và có cache nội bộ không?
2. Query có gửi ra không; có response không; `NOERROR`, `NXDOMAIN`, `SERVFAIL` hay timeout?
3. IP trong câu trả lời có đúng môi trường và khớp với CDN/LB policy không?
4. TTL, record CNAME/AAAA/A, split-horizon, resolver cache và chính sách DNS bảo vệ có liên quan không?

PCAP thông thường có thể không hiển thị DNS query trong hệ thống dùng DNS over HTTPS/TLS hoặc cache; “không có DNS packet” **không có nghĩa** DNS không được dùng. Cần dùng resolver/client logs thích hợp.

### 7.2. TLS: network reachable nhưng xác thực hoặc cấu hình bị lỗi

Một TCP handshake thành công chỉ chứng minh TCP đã kết nối đến endpoint tại thời điểm đó. TLS có thể lỗi do:

- Chứng chỉ hết hạn, sai hostname, CA không được tin cậy, thiếu intermediate chain, sai đồng hồ client.
- Không khớp protocol version/cipher, SNI, ALPN hoặc yêu cầu mTLS/client certificate.
- TLS inspection, proxy cấu hình sai hoặc firewall/IDS/IPS can thiệp phiên.
- Timeout/mất gói trong TLS handshake hoặc backend TLS khác với frontend TLS.

PCAP có thể cho thấy **một số** bản tin TLS handshake/alert, nhưng với TLS 1.3, nhiều thông điệp sau ServerHello được mã hóa; không phải alert hay chi tiết nào cũng thấy nếu không có khóa phiên. Đối chiếu thông báo xác thực của client và log TLS ở nơi kết thúc kết nối. Không dùng tùy chọn bỏ xác minh chứng chỉ như giải pháp sửa lỗi.

### 7.3. HTTP status không tự xác định chủ thể gây lỗi

- **400/422:** request không phù hợp schema/validation hoặc bị proxy/WAF kiểm tra.
- **401/403:** xác thực/phân quyền/token/policy; có thể do app, API gateway hoặc WAF trả.
- **404:** route ở app, proxy hoặc triển khai sai cấu hình.
- **429:** rate limiting có thể xảy ra tại gateway hoặc app.
- **500:** lỗi nội bộ của thành phần tạo response; cần biết thành phần nào.
- **502:** gateway/proxy không nhận được upstream response hợp lệ; có thể upstream reset hoặc sai giao thức.
- **503:** dịch vụ không sẵn sàng, maintenance, backend unhealthy, saturation hoặc chính sách giới hạn.
- **504:** gateway/proxy chờ upstream quá thời hạn; cần xác định là app chậm, upstream network chậm hay các lần retry/circuit-breaker.

Response mã lỗi có thể là **phản hồi hợp lệ trên mạng** dù nghiệp vụ thất bại. HTTP 200 cũng chưa bảo đảm ứng dụng thành công: body có thể chứa `{"ok":false}`, trả dữ liệu sai hoặc UI render lỗi. Phân tích ở nhiều tầng, đặc biệt khi LB/CDN chèn thêm header hoặc mã lỗi riêng.

### 7.4. UDP và QUIC/HTTP/3

QUIC chạy trên UDP, tích hợp bảo mật TLS 1.3, multiplex stream, quản lý loss và congestion. Không thể áp quy tắc “không thấy SYN/SYN-ACK” để kết luận QUIC bị chặn. Với QUIC, cần kiểm tra:

- Lưu lượng UDP/cổng 443, reachability hai chiều, chính sách chặn UDP ở firewall/VPN.
- QUIC Initial/Handshake nếu quan sát được, phiên có tiếp tục hay fallback sang HTTP/2/TCP.
- Loss/RTT/stream metrics ở client và server, các QUIC transport errors, idle timeouts, conn migration.
- Endpoint có hỗ trợ HTTP/3 thực sự không; trình duyệt có reuse connection hay chuyển protocol theo điều kiện mạng không.

Không có QUIC response tại một sensor không xác nhận UDP bị chặn: có thể điểm bắt sai, NAT path khác, browser fallback hoặc server không hỗ trợ. Để nhìn request HTTP/3 cụ thể, cần logs/tracing hoặc giải mã có thẩm quyền; PCAP ciphertext chủ yếu cho thấy metadata, timing và kích thước.

## 8. Công cụ và ví dụ có thể thực hành

Các ví dụ dưới đây dùng **địa chỉ tài liệu TEST-NET** `192.0.2.10` và tên miền minh họa `api.example.test`; phải thay bằng hệ thống thử nghiệm được phép, không dùng lệnh thu thập lên mạng của người khác.

### 8.1. Đo thời gian từ phía client bằng curl

~~~bash
# In thời gian tích lũy tính từ lúc bắt đầu transfer; API có thể cần auth.
curl --silent --show-error --output /dev/null \
  --write-out 'HTTP=%{http_code}\nDNS=%{time_namelookup}s\nTCP=%{time_connect}s\nTLS=%{time_appconnect}s\nTTFB=%{time_starttransfer}s\nTOTAL=%{time_total}s\n' \
  https://api.example.test/health
~~~

Các thời điểm `time_namelookup`, `time_connect`, `time_appconnect`, `time_starttransfer`, `time_total` là **mốc cộng dồn** (tính từ đầu giao dịch), không cộng tất cả số này lại. Ước lượng khi thiết lập TCP/TLS mới, không qua redirect và không dùng proxy:

~~~text
Thời gian DNS                ≈ time_namelookup
Thời gian TCP sau DNS        ≈ time_connect - time_namelookup
Thời gian TLS sau TCP        ≈ time_appconnect - time_connect
Thời gian đến byte đầu sau TLS ≈ time_starttransfer - time_appconnect
Thời gian tải còn lại        ≈ time_total - time_starttransfer
~~~

**Cảnh báo diễn giải:** `time_starttransfer - time_appconnect` bao gồm truyền request, thời gian chờ/xử lý qua các tầng và đường truyền về byte đầu tiên. Nó **không phải** phép đo riêng thời gian xử lý business logic. Với HTTP keep-alive, kết nối tái sử dụng, proxy, DNS cache, HTTP/3, redirect hoặc nhiều connect attempt, một số mốc có thể bằng 0 hoặc không chia được theo công thức trên; phải xét cách request cụ thể được thực hiện. `time_appconnect` phản ánh mốc hoàn tất TLS/SSH handshake khi áp dụng.

Ví dụ giả định một request có các mốc:

| Metric của curl | Giá trị |
|---|---:|
| `time_namelookup` | 0,010 s |
| `time_connect` | 0,030 s |
| `time_appconnect` | 0,070 s |
| `time_starttransfer` | 2,470 s |
| `time_total` | 2,520 s |

Suy ra DNS ~10 ms, TCP sau DNS ~20 ms, TLS sau TCP ~40 ms, **khoảng chờ tới byte đầu sau TLS ~2,40 s** và tải phần còn lại ~50 ms. Chưa đủ để quy 2,40 giây này cho backend: cần so sánh với proxy upstream timing, app span và đường truyền giữa proxy với server.

Có thể kiểm tra IP trong một thử nghiệm có kiểm soát bằng `--resolve api.example.test:443:192.0.2.10` để ánh xạ tên→IP cho lệnh curl mà vẫn dùng hostname cho TLS SNI/xác minh chứng chỉ. Tuy vậy, thao tác này có thể **đi đường khác CDN/LB**, và IP phải thực sự phục vụ chứng chỉ/hostname tương ứng; không dùng để kết luận về DNS thật nếu chưa xác định điều kiện kiểm thử.

### 8.2. Bắt gói phạm vi hẹp với tcpdump

~~~bash
# Chỉ thực hiện trên sensor/test host được quản lý và có quyền.
# Thư mục phải đặt trên vùng lưu mã hóa, hạn chế quyền truy cập.
sudo install -d -m 0700 /var/secure-pcap

# Ví dụ Linux: tối đa 120 giây hoặc 50.000 packet.
sudo timeout --signal=INT 120s tcpdump \
  -i eth0 -nn -s 128 -c 50000 \
  -w /var/secure-pcap/diagnose-api.pcap \
  'host 192.0.2.10 and (tcp port 443 or udp port 443)'

# Kiểm tra định dạng/bản ghi trên một bản capture của bạn:
sudo tcpdump -nn -r /var/secure-pcap/diagnose-api.pcap -c 20
~~~

Diễn giải:

- `-i eth0` chỉ là interface ví dụ. Với mạng chứa VLAN, tunnel và proxy cần xác nhận bắt đúng điểm; `host` chỉ áp dụng cho địa chỉ có thể quan sát tại sensor (trước/sau NAT có thể khác).
- `-s 128` ghi tối đa 128 byte mỗi packet từ vị trí bắt; không bảo đảm chỉ giữ header vì VLAN, IPv6 extension và encapsulation có kích thước khác nhau. Nếu cần phân tích payload/HTTP plaintext phải xem xét mức bảo vệ dữ liệu và phê duyệt.
- `-c` và `timeout` khống chế tài nguyên. Mã thoát 124 của GNU timeout có thể biểu thị hết hạn mặc dù PCAP đã được ghi; kiểm tra file và log.
- Lệnh chỉ lọc cổng 443, không bắt DNS hoặc lưu lượng backend cổng khác; điều tra DNS có thể cần capture riêng đúng resolver/cổng và quyền.
- Tránh lưu PCAP plaintext vào Downloads, ticket hoặc thư mục chia sẻ; giới hạn retention và quyền truy cập vì IP, timing, SNI hiện diện tùy giao thức, đôi khi cả token/payload.

**Không thay full capture bằng lệnh chụp toàn bộ phân đoạn mạng không giới hạn thời gian.** Nếu điểm quan sát không có quyền thấy nội dung mã hóa, hãy dùng metadata và logs, đừng tự ý thu thập khóa TLS.

### 8.3. Display filters hữu ích trong Wireshark

| Mục đích | Display filter (Wireshark) | Cần nhớ |
|---|---|---|
| TCP đến/từ host IPv4 | `ip.addr == 192.0.2.10 && tcp` | Với IPv6 dùng `ipv6.addr`; host NAT có thể đổi |
| Chỉ SYN khởi đầu | `tcp.flags.syn == 1 && tcp.flags.ack == 0` | Không bắt được phiên đã mở trước lúc capture |
| TCP reset | `tcp.flags.reset == 1` | Phải xác minh bên thực sự phát RST |
| Retransmission gợi ý | `tcp.analysis.retransmission` | Heuristic phụ thuộc độ đầy đủ và góc capture |
| Fast retransmission | `tcp.analysis.fast_retransmission` | Không chứng minh điểm rơi packet |
| Zero Window | `tcp.analysis.zero_window` | Có thể do app ở đầu nhận không đọc nhanh |
| DNS response không thành công | `dns.flags.response == 1 && dns.flags.rcode != 0` | Timeout không tạo response; dùng thêm timeline |
| TLS alert thấy được | `tls.alert_message` | Một số TLS 1.3 alert bị mã hóa |
| HTTP 5xx đọc được | `http.response.code >= 500` | Chỉ áp dụng nếu traffic HTTP được dissector giải mã/hiển thị |
| QUIC packet | `quic` | Không có nghĩa đọc được stream HTTP/3 |

Đây là **display filter** sau khi đã capture: không xóa dữ liệu khỏi file gốc. Với TCP, chọn một flow rồi dùng **Follow → TCP Stream**, **Statistics → TCP Stream Graphs** và **Statistics → I/O Graphs** để xem thứ tự, RTT và diễn biến. Khi TLS mã hóa, Follow TCP Stream thường chỉ cho thấy ciphertext.

Kết quả phân tích TCP có thể sai khi trace chỉ ghi một chiều, bắt giữa phiên, có packet drop tại sensor hoặc bị checksum/segmentation offload. Kiểm tra thống kê packet dropped của tcpdump/Wireshark và vị trí capture trước khi kết luận mất gói.

## 9. Phân tích thời gian: chậm do app hay do đường truyền?

Hai loại latency dễ bị nhầm:

- **Time to first byte (TTFB):** thời gian phía client chờ đến byte đầu tiên của response. Nó bao gồm nhiều pha tùy cách đo và không chỉ là thời gian server xử lý.
- **Backend processing latency:** thời gian xử lý business logic đo trong backend/tracing, có thể loại trừ hoặc bao gồm database/network calls tùy instrumentation.

### 9.1. Cùng một request, nhiều đồng hồ

Giả sử tại client, kết nối TLS hoàn thành vào 10:00:00.100, request được gửi xong vào 10:00:00.120 và byte response đầu tiên nhận vào 10:00:02.500. Khoảng chờ sau khi gửi request là **2,380 giây**.

Tại proxy, access log cho biết:

~~~text
request_id=abc-123
received_at=10:00:00.125Z
upstream_connect=0.005s
upstream_response_wait=2.300s
response_sent=10:00:02.490Z
~~~

Ở app, trace cùng `request_id` ghi:

~~~text
handler_total=2.290s
  authenticate=0.015s
  database_query=2.200s
  serialize=0.020s
  other=0.055s
~~~

Trong ví dụ này, **DB query là giả thuyết mạnh nhất** vì một span 2,2 s giải thích gần như toàn bộ khoảng chờ. TCP handshake/TLS ngắn và proxy không ghi upstream connect chậm. Tuy vậy vẫn cần kiểm tra DB span đo gì, có network giữa app và database hay không, và app có queue trước khi nhận request không.

**Ví dụ đối lập:** nếu app trace chỉ ~20 ms, proxy response_sent sớm nhưng client nhận response sau vài giây, cần xem capture ở proxy/client, đường về, retransmission/receive window, CDN buffering và thiết bị client. Không được dùng phép trừ giữa timestamp hai máy khi đồng hồ chưa đồng bộ; ưu tiên thời lượng đo bởi cùng một hệ thống và kiểm tra độ lệch UTC.

### 9.2. Lưu ý với proxy và HTTP/2 multiplexing

Ở proxy, `request_time` và `upstream_response_time` có định nghĩa cụ thể theo sản phẩm/cấu hình, có thể bao gồm thời gian gửi/nhận nội dung và retry. Không được mặc định tất cả đều đo “thời gian CPU của app”. Khi proxy buffer response, thời điểm upstream trả xong có thể khác thời điểm client nhận xong.

Với HTTP/2, nhiều request chạy đồng thời trong cùng TCP connection; thấy một TCP retransmission chưa xác định request cụ thể bị ảnh hưởng nếu không có khung HTTP/2 đã giải mã hoặc trace. Với QUIC, các stream được vận chuyển trên cùng connection nhưng có cơ chế phục hồi loss khác TCP; cần app metrics và QUIC logs để quy về một request.

## 10. Đối chiếu PCAP hai đầu để xác định nơi mất/chậm

Lập một bảng sự kiện tối thiểu từ client và server. Không cần lấy toàn bộ lưu lượng nếu chỉ có một flow đang lỗi.

| Thời điểm tương đối | Client PCAP | Server/LB PCAP | Nhận định |
|---|---|---|---|
| 0 ms | Gửi SYN | Nhận SYN | SYN đã đến điểm B |
| 10 ms | Nhận SYN-ACK | Gửi SYN-ACK | Đường đi về có phản hồi |
| 20 ms | Gửi request data | Nhận data và ACK | TCP stack B nhận byte |
| 30–2.030 ms | Chờ, không thấy response | Không có response từ B | Kiểm tra app/proxy queue, backend, chưa kết luận mạng tốt hoàn toàn |
| 2.040 ms | Nhận data response | B gửi data response | Thời gian chờ nằm trước thời điểm server gửi response |

Khi so sánh, phải cân nhắc:

- PCAP đã bắt từ đầu phiên chưa; sensor có bị drop packet không?
- Timestamp hai đầu có lệch và có cùng độ chính xác không? Nên dựa trên trình tự và mốc đồng hồ đồng bộ.
- TCP có bị kết thúc ở LB/proxy không? Nếu có, tạo **hai bảng riêng**: client↔proxy và proxy↔app.
- NAT, TCP seq translation, tunneling, load balancing, IPv6 và đường đi bất đối xứng có làm thay đổi cách xác định cùng flow không?
- Host TCP stack ACK dữ liệu trước khi ứng dụng xử lý; ACK chỉ khẳng định ở tầng TCP.
- Bên nhận quảng bá window và app socket reads có chỉ ra nghẽn nội bộ không?

Khi packet được gửi tại A nhưng không thấy tại B, cần xác nhận cảm biến ở B chắc chắn quan sát đúng hướng/flow. Sau đó mới khoanh vùng từ A tới B, thu thêm firewall/session logs hoặc bắt tại một điểm trung gian có thẩm quyền.

## 11. Các tình huống chẩn đoán mẫu

### Tình huống A — API trả HTTP 504 sau đúng 30 giây

**Hiện tượng:** client mở TCP/TLS nhanh, gọi `POST /orders` rồi nhận 504 sau khoảng 30 giây. PCAP tại client không thấy retransmission đáng kể.

**Điều tra:** proxy log ghi upstream timed out sau 30 s; trace ở app ghi một truy vấn SQL chờ khóa 45 s. Kết luận phù hợp: proxy trả timeout do upstream xử lý lâu, nguyên nhân sâu có thể là database lock. Firewall không mất gói ở flow client↔proxy **không chứng minh** flow app↔DB không có sự cố; cần xác minh dependency span và DB.

**Hành động:** nhóm ứng dụng/DB kiểm tra transaction và contention; nhóm proxy đối chiếu timeout, retry policy và circuit breaker, tránh chỉ tăng timeout để che vấn đề.

### Tình huống B — Chỉ người dùng qua VPN bị time out kết nối

**Hiện tượng:** cùng API, thiết bị ngoài VPN thành công, thiết bị qua VPN gửi SYN lặp nhiều lần và không thấy SYN-ACK.

**Điều tra:** PCAP ở ứng dụng không thấy SYN của client VPN, nhưng VPN firewall log có deny theo dải IP sau khi thay đổi chính sách. Kết luận có căn cứ: traffic bị chặn ở chính sách mạng/đường VPN trước khi đến dịch vụ.

**Hành động:** kiểm tra đúng policy, route và rule precedence; sửa theo quy trình thay đổi đã được phê duyệt. Sau sửa, capture ở client/server chứng minh TCP setup và request thành công; kiểm tra IDS/IPS không phát sinh cảnh báo bất thường.

### Tình huống C — Trang web tải chậm dù backend xử lý nhanh

**Hiện tượng:** app trace chỉ 50 ms; proxy bắt đầu gửi response sau 80 ms nhưng client mất 8 giây để tải file 20 MB.

**Điều tra:** PCAP thấy tốc độ thấp, nhiều retransmission phía proxy, RTT biến động; interface metrics ở đường WAN có packet drops. Đồng thời cần loại trừ client đọc chậm (zero window), proxy throttling hoặc disk bottleneck.

**Kết luận:** có bằng chứng nghiêng về nghẽn/mất gói trên đường truyền response; chỉ kết luận khi đối chiếu điểm phát/nhận, counters và giai đoạn có loss.

### Tình huống D — TLS lỗi sau khi thay chứng chỉ

**Hiện tượng:** TCP connection thành công nhưng client báo certificate verify failed; một số thiết bị vẫn truy cập được.

**Điều tra:** kiểm tra certificate chain, SAN/hostname, client trust store, đồng hồ và TLS termination point. PCAP cho thấy handshake chưa đi tới dữ liệu ứng dụng; log gateway cho biết missing intermediate certificate.

**Kết luận:** lỗi cấu hình chứng chỉ ở tầng TLS, không phải mất IP connectivity. Thay đúng chain, xác minh các client đại diện; không tắt xác minh chứng chỉ.

### Tình huống E — Retransmission nhưng root cause không nằm ở router

**Hiện tượng:** người dùng gọi API hàng loạt; response chậm, Wireshark hiện `Zero Window` và retransmissions.

**Điều tra:** backend bị GC pause, tiến trình đọc socket không kịp; receive buffer đầy, cửa sổ đóng. Một số gói được gửi lại do timeout. Sau khi sửa GC/worker sizing, cửa sổ nhận bình thường và response latency giảm.

**Kết luận:** PCAP chứng minh hiện tượng ở tầng transport nhưng phối hợp với host/app metrics mới chỉ ra nguyên nhân ở xử lý ứng dụng. Đừng tự động quy mọi retransmission cho “mạng yếu”.

### Tình huống F — DNS phân giải được nhưng dẫn đến sai môi trường

**Hiện tượng:** một nhóm người dùng nhận giao diện cũ, API trả 404; những người khác bình thường.

**Điều tra:** so sánh A/AAAA records, TTL, resolver cache, split-horizon DNS và hostname cấu hình trên client. Một resolver trả IP staging trong khi resolver khác trả production.

**Kết luận:** nguyên nhân nằm ở cấu hình/phân phối DNS; HTTP 404 là triệu chứng của việc truy cập sai backend. Sau sửa, theo dõi TTL và cache trước khi tuyên bố toàn bộ client đã hồi phục.

## 12. Phân công xử lý dựa trên bằng chứng

Khi cần chuyển vụ việc giữa nhóm network, security và application, một phiếu điều tra nên đủ thông tin để người tiếp nhận kiểm chứng độc lập:

~~~text
Incident ID: INC-2026-115
Triệu chứng: POST /orders trả 504, p95=30s, xảy ra từ 10:00Z
Phạm vi: chỉ vùng B, 12% requests, client qua VPN
Điểm quan sát: client VPN, ingress LB, application trace
Dấu hiệu: TCP/TLS thành công; proxy tạo 504 sau upstream timeout
Evidence: trace abc-123, firewall session 456, PCAP ID cap-789
Giả thuyết: upstream backend đợi DB lock
Chưa xác minh: app-to-DB RTT tại thời điểm lỗi
Owner phối hợp: App + DB; Network kiểm tra path dependency
Biện pháp/đánh giá: kiểm tra lock, so sánh trace và latency sau sửa
~~~

Không đính kèm PCAP thô hoặc access token vào ticket công khai. Lưu capture trong kho được mã hóa, chỉ cấp quyền theo vụ việc, giới hạn thời gian, xóa bản sao đúng chính sách retention; chỉ dẫn tham chiếu tới evidence khi chuyển việc.

### 12.1. Mức độ tự tin của kết luận

Một báo cáo tốt tách ba mức:

- **Quan sát:** “client gửi SYN ba lần trong PCAP và không ghi nhận SYN-ACK.”
- **Giả thuyết:** “đường VPN hoặc ACL có thể làm mất phản hồi.”
- **Xác nhận:** “log firewall tại gateway ghi deny đúng flow và timestamp; sau cập nhật rule đã được phê duyệt, SYN/SYN-ACK/ACK và API request thành công.”

Cụm từ “không thấy” trong một capture nên đi cùng **tên sensor, chiều traffic và giới hạn thu thập**, tránh trình bày như chứng cứ tuyệt đối về điều không xảy ra trên hệ thống.

## 13. Những ngộ nhận phổ biến

1. **Ping chạy được nên network không lỗi.** ICMP echo có thể đi đường và chính sách khác TCP/UDP, lại không kiểm tra TLS, HTTP, path MTU hoặc tình trạng proxy.
2. **TCP ACK nghĩa là ứng dụng đã xử lý.** ACK xác nhận tầng vận chuyển nhận byte; request có thể còn ở kernel buffer, proxy queue hoặc app queue.
3. **Có RST chắc chắn firewall cắt.** RST có thể xuất phát từ kernel, application, proxy, gateway hoặc thiết bị khác.
4. **Retransmission luôn do packet loss trên dây.** Còn có ACK loss, reorder, host overload, capture artifacts và retransmission không cần thiết.
5. **HTTP 500/504 là lỗi ứng dụng hoặc lỗi mạng một cách tuyệt đối.** Cần biết thành phần phát status và nguyên nhân ở upstream/dependency.
6. **Không thấy HTTP request trong PCAP nghĩa là client không gửi.** Có thể bị TLS mã hóa, dùng HTTP/2 hoặc HTTP/3, bắt sai interface hoặc file bị cắt gói.
7. **Client TTFB bằng thời gian xử lý backend.** TTFB chứa nhiều pha và có thể bị proxy buffer, network và connection setup tác động.
8. **Thử bằng curl thành công chứng minh browser không lỗi.** Browser có cookie/auth, HTTP/3, proxy settings, cache, CORS, JavaScript và connection reuse khác.
9. **Chỉ capture tại LB là đủ.** TLS termination, NAT, backend network và proxy buffering làm khác biệt client↔LB và LB↔server.
10. **Đổi timeout lớn hơn tức là đã sửa sự cố.** Có thể chỉ trì hoãn lỗi và tăng số kết nối chờ; phải điều tra nút thắt và giới hạn tài nguyên.

## 14. Checklist điều tra nhanh

- [ ] Đã có thời điểm, endpoint, request ID, phạm vi user và cách tái hiện.
- [ ] Đã ghi baseline: error rate, p95/p99, DNS/TCP/TLS/TTFB/total, theo vùng và giao thức.
- [ ] Đã kiểm tra DNS/cache/IPv4/IPv6 và tên dịch vụ đích chính xác.
- [ ] Đã phân biệt không thiết lập kết nối, TLS lỗi, HTTP lỗi và response chậm.
- [ ] Đã xác định điểm kết thúc TCP/TLS, LB/proxy/NAT và điểm capture.
- [ ] Đã kiểm tra SYN/SYN-ACK/ACK, RST/FIN, retransmission, RTT, zero window và packet drops.
- [ ] Đã đối chiếu PCAP, firewall logs, proxy timings, app trace và dependency metrics với timestamp đồng bộ.
- [ ] Đã kiểm tra các yếu tố QUIC, HTTP/2, MTU, proxy buffering hoặc offload khi liên quan.
- [ ] Đã phân tách quan sát, giả thuyết, bằng chứng xác nhận và phạm vi chưa xác minh.
- [ ] Đã ghi owner khắc phục, cách kiểm tra hồi phục và lịch theo dõi sau sửa.
- [ ] Đã giới hạn phạm vi thu thập và bảo vệ PCAP theo chính sách dữ liệu nhạy cảm.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Client gửi SYN nhưng không thấy SYN-ACK. Có thể kết luận server không phản hồi không?

*Gợi ý:* Chưa. Bắt tại server/LB, kiểm tra routing/ACL/NAT, capture loss và đường về rồi mới xác định vị trí thất bại.

**Câu 2.** Curl báo DNS 10 ms, TCP 30 ms, TLS 70 ms, TTFB 2.470 ms. Thời gian từ hoàn tất TLS đến byte đầu khoảng bao lâu?

*Đáp án:* Khoảng **2.400 ms** theo phép trừ các mốc cộng dồn. Chưa thể quy toàn bộ cho backend nếu thiếu proxy/tracing.

**Câu 3.** PCAP có nhiều `tcp.analysis.retransmission`, nhưng ứng dụng bên nhận bị kẹt GC và quảng bá zero window. Nên gọi là lỗi gì?

*Đáp án:* Cần phân tích nguyên nhân ở app/host đọc socket chậm và tác động transport; nhãn retransmission riêng lẻ không chứng minh lỗi router.

**Câu 4.** HTTP 504 là do thành phần nào trả, và làm sao chứng minh?

*Đáp án:* Thường gateway/proxy trả sau upstream timeout. Xem access/error logs và request trace để xác định chính xác thành phần phát và nguyên nhân upstream không kịp trả.

**Câu 5.** Vì sao PCAP thông thường không hiển thị body của HTTPS hoặc HTTP/3?

*Đáp án:* Nội dung được TLS/QUIC mã hóa; phân tích cần logs/tracing hoặc dữ liệu giải mã trong phạm vi được cho phép. Không nên bật thu khóa/giải mã tràn lan.

---

**Ghi nhớ:** Khoanh vùng sự cố theo **DNS → kết nối TCP/QUIC → TLS → HTTP → ứng dụng/dependency → truyền response**. Mỗi nhận định phải gắn với packet, log, span hoặc metric cụ thể; khi dữ liệu từ nhiều điểm mâu thuẫn, tìm điểm kết thúc kết nối và sai khác trong đường đi trước khi kết luận lỗi thuộc nhóm network hay application.
