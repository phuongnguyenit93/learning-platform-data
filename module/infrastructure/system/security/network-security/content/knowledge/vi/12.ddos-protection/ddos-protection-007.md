# HTTP flood: Nhận diện và bảo vệ dịch vụ web trước DDoS tầng ứng dụng

## 1. HTTP flood là gì?

**HTTP flood** là một dạng **tấn công từ chối dịch vụ bằng lưu lượng HTTP ở tầng ứng dụng (Layer 7)**, trong đó nhiều yêu cầu truy cập được gửi đến website, API hoặc dịch vụ web với mục tiêu làm cạn kiệt tài nguyên hoặc khiến người dùng hợp lệ không thể sử dụng dịch vụ bình thường. Mục tiêu chịu ảnh hưởng có thể là reverse proxy, máy chủ ứng dụng, bộ nhớ đệm (cache), cơ sở dữ liệu, hệ thống xác thực, hàng đợi tác vụ hoặc một dịch vụ phụ thuộc.

Đặc trưng của HTTP flood không nhất thiết là lượng băng thông lớn. **Một yêu cầu HTTP có kích thước nhỏ có thể tạo ra công việc xử lý lớn** nếu nó khiến backend thực hiện truy vấn phức tạp, xác thực nhiều bước hoặc gọi hàng loạt dịch vụ khác. Vì vậy, một hệ thống có đường truyền còn nhiều băng thông vẫn có thể quá tải CPU, connection pool, database hoặc số worker xử lý request.

Trong chương **DDoS** của module **SECURITY_NETWORK_SECURITY**, chủ đề này liên quan trực tiếp đến kiến trúc phòng vệ nhiều lớp: **firewall, phân đoạn mạng, DNS, VPN, IDS/IPS, theo dõi lưu lượng, WAF, CDN, xác thực kết nối và bảo vệ cloud**. Firewall chặn truy cập trái phép ở tầng mạng là cần thiết, nhưng thường chưa đủ để quyết định một yêu cầu HTTPS hợp lệ về cú pháp có nên tiêu thụ tài nguyên ứng dụng hay không.

**Mục tiêu học tập:**

1. Phân biệt HTTP flood với tấn công gây nghẽn đường truyền, bất thường ứng dụng và đợt người dùng thật tăng đột biến (*flash crowd*).
2. Hiểu tác động của HTTP GET/POST, HTTP/1.1, HTTP/2 và HTTP/3 ở góc độ phòng thủ.
3. Phân tích chỉ số edge, WAF, load balancer, origin và database để xác nhận nguồn gốc suy giảm dịch vụ.
4. Thiết kế bảo vệ theo lớp: CDN, cache, rate limit, bot management, challenge, admission control và giới hạn tài nguyên backend.
5. Viết một chính sách rate limiting **minh họa** và hiểu nguy cơ chặn nhầm người dùng hợp lệ.
6. Xây dựng playbook ứng cứu, kiểm thử an toàn và tiêu chí phục hồi.

> **An toàn thực hành:** các ví dụ dùng số liệu giả định, cấu hình mẫu và **phân tích log đã thu thập**. Không tạo công cụ gửi HTTP flood, không kiểm thử tải lên hệ thống ngoài quyền quản lý. Đánh giá sức chịu tải cần môi trường cách ly hoặc chương trình kiểm thử được phê duyệt với ngưỡng tải, cơ chế dừng và người chịu trách nhiệm.

## 2. Cơ chế HTTP flood ở tầng ứng dụng

### 2.1. Vì sao request nhỏ vẫn gây tác động lớn?

Một request web có thể đi qua nhiều bước xử lý:

~~~mermaid
flowchart LR
    C["Client / trình duyệt"] --> E["DNS + CDN / Edge"]
    E --> W["WAF + bot / rate policy"]
    W --> L["Load balancer"]
    L --> A["Web / API origin"]
    A --> D["Database / cache"]
    A --> I["Identity / external API"]
    W -. "Logs / signals" .-> S["SIEM / giám sát"]
    A -. "APM / metrics" .-> S
~~~

Một yêu cầu được CDN phục vụ trực tiếp từ cache có thể sử dụng rất ít tài nguyên ở origin. Nhưng yêu cầu tới endpoint động có thể phải đi qua các bước xác thực, phân quyền, truy vấn database, xây dựng kết quả, đọc object storage và gọi service khác. Nếu số request hợp lệ về cú pháp tăng mạnh, **nút thắt** có thể xảy ra ở bất kỳ thành phần nào.

Không phải request phức tạp nào cũng là tấn công. Một số nghiệp vụ hợp lệ như tìm kiếm, xuất báo cáo và thanh toán thực sự cần tài nguyên lớn. Phòng vệ tốt phải nhận diện và ưu tiên traffic theo ngữ cảnh thay vì chỉ áp dụng một ngưỡng cho toàn website.

### 2.2. Khái niệm bất đối xứng chi phí

Tạm gọi:

- \(R\): tốc độ yêu cầu đến một thành phần, tính bằng **requests/second (RPS)**.
- \(C\): mức công việc xử lý trung bình trên mỗi request, ví dụ CPU time, database operations hoặc số truy vấn phụ thuộc.
- \(K\): năng lực xử lý hiệu quả của thành phần trong điều kiện vận hành xác định.

Ta có thể dùng mô hình **định tính**:

\[
\text{Áp lực lên tài nguyên} \propto R \times C
\]

Nếu mức công việc phát sinh vượt năng lực xử lý bền vững của nút thắt, hàng đợi và độ trễ thường tăng, tiếp theo là timeout, từ chối hoặc lỗi 5xx. Đây **không phải** công thức dự đoán chính xác RPS an toàn: hệ thống thực có nhiều hàng đợi, cache, giới hạn đồng thời, độ biến thiên yêu cầu và cơ chế autoscaling.

Ví dụ: hai endpoint nhận cùng 200 RPS nhưng một endpoint chỉ trả dữ liệu tĩnh từ cache, trong khi endpoint còn lại truy cập database và gọi hệ thống bên thứ ba. Tác động đến origin có thể khác rất lớn.

### 2.3. Tài sản nào cần bảo vệ?

| Tài sản | Dạng suy giảm khi bị quá tải | Dữ liệu cần quan sát |
|---|---|---|
| Edge/CDN/WAF | Tăng request xử lý, rule/challenge hoạt động bất thường | Edge RPS, action, cache hit, error và latency |
| Load balancer/reverse proxy | Cạn kết nối, queue, worker hoặc giới hạn kết nối đến upstream | Active connections, upstream errors, queue, p95/p99 |
| Web/API worker | CPU/heap/threads/event loop quá tải | Saturation, request queue, timeouts, RPS theo route |
| Database | Hết connection pool, truy vấn chậm, lock contention | Connections, query latency, CPU/IO, pool wait |
| Cache/session store | Hot key, miss tăng, connection pool hoặc memory pressure | Hit/miss, eviction, latency, error |
| IdP/dịch vụ xác thực | Login/check token quá tải | Authentication rate, 429, error, downstream dependency |
| Dịch vụ thứ ba | API quota hoặc latency cao làm dây chuyền chậm | Dependency failures, retry volume, circuit-breaker state |
| Telemetry | Log quá nhiều, pipeline trễ hoặc bị mất | Ingestion lag, dropped logs, sampling, chi phí |

Mục đích của bảo vệ DDoS là **duy trì chức năng quan trọng cho người dùng hợp lệ**, không chỉ giảm số lượng request đến thấp nhất.

## 3. Các kiểu áp lực HTTP flood mà đội phòng thủ cần nhận biết

### 3.1. Tăng truy cập tới một endpoint

Khi nhiều yêu cầu tập trung vào một đường dẫn, thành phần xử lý phía sau có thể trở thành nút thắt. Endpoint tĩnh thường được cache tốt; endpoint có truy vấn hoặc xác thực có thể tốn tài nguyên hơn. Đội phòng thủ cần có biểu đồ **RPS theo route/nhóm endpoint**, không chỉ tổng số request toàn hệ thống.

### 3.2. Lưu lượng tới API động hoặc khó cache

Các endpoint trả dữ liệu theo người dùng, yêu cầu xác thực, giao dịch ghi hoặc báo cáo theo thời gian thực thường không thể cache tùy ý. Khi tăng tải, ứng dụng còn có thể tăng số kết nối tới database, phụ thuộc IdP hoặc hệ thống hàng đợi. Chính sách nên dùng **giới hạn theo tài nguyên/định danh và mức chi phí thực**, tránh áp dụng cùng một rate limit với ảnh tĩnh.

### 3.3. Nhiều nguồn phân tán

DDoS thường liên quan nhiều điểm gửi traffic, nên **một IP đơn lẻ có thể không có RPS cao**. Rate limit theo IP vẫn hữu ích trong một số trường hợp nhưng có thể bỏ sót traffic phân tán. Phòng thủ cần kết hợp tín hiệu **IP/ASN/địa lý theo ngữ cảnh, session, token, cookie, endpoint, hành vi truy cập, bot score và telemetry tầng ứng dụng**. Một nguồn IP có lượng truy cập lớn cũng có thể là NAT của nhiều người dùng thật.

### 3.4. Lưu lượng gần giống người dùng hợp lệ

HTTP flood có thể dùng các yêu cầu hoàn toàn hợp lệ về phương thức, header và URL. Khác biệt nằm ở **số lượng, nhịp truy cập, mối quan hệ giữa session và hành vi, mức độ sử dụng tài nguyên, tỷ lệ hoàn tất quy trình nghiệp vụ và bối cảnh thời gian**. Không thể kết luận chắc chắn đó là tấn công chỉ dựa trên HTTP status 200 hay User-Agent.

### 3.5. Cần phân biệt với các dạng khác

| Hiện tượng | Cơ chế tác động chính | Phân biệt với HTTP flood |
|---|---|---|
| **Volumetric DDoS** | Bão hòa băng thông hoặc hạ tầng mạng bằng lượng traffic lớn | HTTP flood có thể đạt mục tiêu khi băng thông chưa đầy |
| **SYN flood** | Gây áp lực tài nguyên kết nối TCP/khả năng tiếp nhận | HTTP flood xảy ra ở tầng request sau khi giao thức mạng/vận chuyển hoạt động |
| **Slow HTTP / slow connection attack** | Giữ connection và tiến trình xử lý trong thời gian dài | Dùng cơ chế cạn kiệt connection theo thời gian; có thể cùng nhóm L7 DoS nhưng không đồng nhất với burst HTTP flood |
| **Flash crowd** | Người dùng thật tăng mạnh vì sự kiện, chiến dịch hoặc tin tức | Tác động kỹ thuật có thể giống nhưng cần ưu tiên phục vụ traffic hợp lệ |
| **Bot hợp lệ** | Crawler, tích hợp tự động, health checks hoặc công cụ kiểm thử có phép | Cần quản lý định danh/quota và lịch, không mặc định mọi bot là tấn công |
| **Sự cố ứng dụng** | Deploy lỗi, truy vấn chậm, dependency outage | Có thể tạo 5xx và retry storm ngay cả khi lưu lượng vào không tăng |

Lưu lượng tăng và lỗi 5xx chưa đủ để khẳng định đang xảy ra **DDoS**. Cần phân tích diễn tiến, tín hiệu hành vi, tác động hệ thống và các sự kiện vận hành gần thời điểm đó.

## 4. HTTP/1.1, HTTP/2 và HTTP/3 có ý nghĩa gì đối với phòng thủ?

| Phiên bản | Đặc điểm cần biết | Hệ quả cho quan sát và kiểm soát |
|---|---|---|
| **HTTP/1.1** | Có keep-alive, có thể tái sử dụng connection cho nhiều request | Đếm connection mới không phản ánh trực tiếp số request |
| **HTTP/2** | Nhiều stream/request có thể chạy đồng thời trên một TCP connection | Cần đo request/stream/concurrency, không chỉ TCP connections |
| **HTTP/3** | HTTP trên QUIC, thường dùng UDP/443 | Bộ lọc chỉ theo TCP/443 có thể bỏ sót đường HTTP/3 |

**Không dùng số connection thay cho RPS.** Một số kết nối có thể phát ra nhiều request; ngược lại một lượng lớn connection không nhất thiết chứng minh số request ứng dụng tương ứng.

Các cơ chế giới hạn **max concurrent streams, request body size, header size, handshake rate, idle timeout, request timeout, upstream concurrency** là lớp bảo vệ tùy nền tảng. Chúng cần cấu hình dựa trên năng lực và yêu cầu ứng dụng, vì giới hạn quá thấp có thể làm lỗi ứng dụng hợp lệ, đặc biệt ứng dụng di động và trình duyệt sử dụng HTTP/2/3.

**TLS** là yếu tố quan trọng: nếu traffic được mã hóa, thiết bị mạng ngoài điểm TLS termination có thể chỉ thấy IP, cổng và một số metadata, không nhìn thấy path, cookie hay nội dung HTTP. Để dùng rule tầng ứng dụng, cần đặt khả năng quan sát và thực thi tại **CDN/WAF/reverse proxy hoặc điểm giải mã được phê duyệt**. Không mặc định IDS/IPS ở biên đọc được payload HTTPS.

## 5. HTTP flood xuất hiện ở đâu trong kiến trúc?

~~~mermaid
flowchart TD
    A["Người dùng thật và lưu lượng không mong muốn"] --> B["DNS / CDN / Anycast edge"]
    B --> C["Bot protection / WAF / L7 rate limiting"]
    C --> D{"Quyết định edge"}
    D -- "Block / challenge / throttle" --> X["Không chuyển tiếp hoặc yêu cầu xác minh"]
    D -- "Allow" --> E["Load balancer / reverse proxy"]
    E --> F["Origin / API"]
    F --> G["Cache / Database / IdP"]
    B -. "Edge metrics" .-> M["Monitoring / SOC"]
    C -. "Action logs" .-> M
    F -. "APM + 5xx + saturation" .-> M
    G -. "Dependency metrics" .-> M
~~~

**Edge** là điểm bảo vệ gần nguồn traffic; **origin** là hệ thống cung cấp ứng dụng gốc. Một chiến lược hiệu quả không chỉ chặn request bất thường ở edge mà còn làm cho origin **chịu lỗi, giới hạn tài nguyên và phục hồi nhanh** khi một phần traffic vẫn lọt qua hoặc traffic tăng hợp lệ.

### 5.1. Khi nào CDN hữu ích?

Với nội dung được cache đúng, CDN có thể trả nhiều request mà không yêu cầu origin xử lý mỗi lần. Tuy nhiên, việc bật CDN **không tự giải quyết** flood vào endpoint động hoặc có xác thực. Cần xác định cache eligibility và cache hit cho từng nhóm route.

### 5.2. Khi nào WAF/bot management hữu ích?

WAF và lớp bot management có thể đánh giá request theo quy tắc, tín hiệu hành vi, session, nguồn và thách thức phù hợp. Chúng có thể block, challenge, throttle hoặc chỉ ghi log, tùy cấu hình. Việc một rule WAF được bật **không chứng minh** tất cả HTTP flood đã được chặn: traffic có thể khác đặc điểm rule hoặc đi thẳng tới origin nếu đường vào chưa được khóa.

### 5.3. Khi nào cần bảo vệ upstream?

Nếu đường truyền/thiết bị mạng phía trước bị bão hòa, rate limit đặt bên trong origin có thể **quá muộn** vì traffic đã chiếm tài nguyên upstream. Khi đó cần phối hợp ISP, CDN, nhà cung cấp DDoS mitigation hoặc cơ chế bảo vệ mạng ở phía trước. Ngược lại, khi băng thông vẫn ổn nhưng database quá tải, cần tập trung vào **L7 protection và năng lực origin/dependency**.

## 6. Các tín hiệu nhận diện HTTP flood

### 6.1. Quan sát theo nhiều lớp

| Nhóm chỉ số | Ví dụ cần theo dõi | Câu hỏi giúp trả lời |
|---|---|---|
| **Traffic edge** | RPS, peak burst, nguồn, nhóm mạng, đường dẫn, HTTP version | Traffic tăng ở đâu và tập trung vào endpoint nào? |
| **WAF/bot** | Action ALLOW/BLOCK/CHALLENGE, rule IDs, challenge pass rate, tín hiệu bot | Bao nhiêu request được kiểm soát trước khi tới origin? |
| **Cache** | Hit ratio, origin fetch rate, bytes served edge/origin | Traffic có được hấp thụ ở edge hay tràn về origin? |
| **Ứng dụng** | p50/p95/p99 latency, 5xx, request concurrency, queue, timeouts | Người dùng hợp lệ có bị suy giảm? |
| **Hạ tầng** | CPU, RAM, connection pool, worker/event-loop saturation | Nút thắt có nằm tại reverse proxy hoặc server? |
| **Database/IdP** | Query latency, DB pool wait, lock, rate limit/quota downstream | Có hiện tượng khuếch đại công việc xuống dependency? |
| **Người dùng** | Success rate của luồng đăng nhập/thanh toán, tỷ lệ giao dịch hoàn tất | Chức năng quan trọng có còn hoạt động không? |
| **Vận hành** | Deploy, marketing campaign, maintenance, origin error trước/sau | Đây có thể là flash crowd hoặc sự cố không phải DDoS? |

**RPS** là tốc độ yêu cầu; **p95** là ngưỡng mà khoảng 95% mẫu được đo có thời gian phản hồi không vượt quá trong tập đo. Không nên dùng mỗi giá trị trung bình: một nhóm người dùng có thể gặp độ trễ rất cao trong khi trung bình vẫn thấp.

### 6.2. Những mẫu có thể đáng điều tra

- RPS tăng khác thường ở một số endpoint nhưng không tương ứng với số lượt hoàn tất tác vụ nghiệp vụ.
- Origin RPS và database operations tăng mạnh dù traffic cacheable hoặc tổng số người dùng hợp lệ không tăng tương ứng.
- Tỷ lệ cache miss cao bất thường ở nhóm route trước đó được cache tốt, sau khi đã loại trừ thay đổi phiên bản và chính sách cache.
- Độ trễ p95/p99, request queue hoặc connection pool tăng đồng thời với traffic.
- Nhiều request bị challenge/block, hoặc xuất hiện thay đổi hành vi session mà hệ thống quản lý bot đánh dấu đáng nghi.
- Tăng 429/503 hoặc 5xx ở một thành phần trong chuỗi, cần xác định chính xác **lớp trả status**.

Mỗi tín hiệu chỉ là **giả thuyết**. Một chương trình khuyến mại, sự kiện bán vé, ứng dụng mới ra mắt hoặc deploy làm mất cache cũng có thể tạo biểu đồ tương tự.

### 6.3. Phân biệt edge metrics với origin metrics

Nếu edge xử lý 50.000 RPS nhưng origin chỉ nhận 500 RPS và vẫn khỏe, hệ thống có thể đang **hấp thụ tải hiệu quả**. Nếu edge chỉ có 3.000 RPS nhưng tất cả dồn vào một API tìm kiếm có truy vấn database nặng, origin có thể quá tải. Do đó, phải đo **tốc độ yêu cầu tới từng điểm trong chuỗi**, không lấy tổng edge requests làm số request thực sự đã xử lý tại backend.

## 7. Phân tích một bộ số liệu giả định

Giả sử hệ thống thương mại điện tử có dashboard như sau trong hai cửa sổ 5 phút:

| Chỉ số | Bình thường | Khi có bất thường | Nhận xét ban đầu |
|---|---:|---:|---|
| Edge requests/s | 800 | 12.000 | Tăng 15 lần |
| Origin requests/s | 450 | 8.500 | Origin chịu phần lớn tải tăng |
| Cache hit ratio ở các route đủ điều kiện | 82% | 28% | Cần kiểm tra thay đổi phân bố route và cache |
| p95 latency của API | 140 ms | 1.900 ms | Chức năng API suy giảm mạnh |
| Origin 5xx rate | 0,2% | 11% | Lỗi ứng dụng hoặc upstream tăng |
| Database pool wait p95 | 8 ms | 740 ms | Có thể là nút thắt downstream |
| Tỷ lệ giao dịch mua hàng hoàn tất | 94% | 61% | Tác động tới người dùng thật |

**Các con số đều giả lập.** Tỷ lệ **edge tăng 15 lần** là phép so sánh 12.000 / 800, **không phải** ngưỡng DDoS chung. Cache hit ratio trong bảng áp dụng cho **những request đủ điều kiện cache**; không dùng trực tiếp để suy ra mọi request từ edge được phục vụ bởi cache.

### 7.1. Chuỗi suy luận hợp lý

1. Edge RPS tăng nên cần xác định **route, session, nguồn và thời điểm**, so với lịch marketing và hoạt động hợp lệ.
2. Origin RPS tăng mạnh, chứng tỏ lớp edge chưa giảm tải đủ; cần so sánh với các quy tắc WAF/CDN và chính sách cache.
3. p95 API và database pool wait tăng cùng thời gian; có thể API/database là nút thắt. Phải xem thêm CPU, queue, query và tác động dependency.
4. Tỷ lệ giao dịch hoàn tất giảm: **mục tiêu vận hành bị ảnh hưởng**, cần ưu tiên bảo vệ các luồng mua hàng hợp lệ thay vì chỉ giảm tổng RPS.
5. Quyết định “đây là DDoS” chỉ nên đưa ra sau khi đối chiếu hành vi request, logs và các khả năng khác (deployment, flash crowd, lỗi database).

### 7.2. Tránh kết luận vội

**Độ trễ p95 cao không tự chứng minh tấn công.** Một truy vấn database mới chưa có index, thay đổi cấu hình cache hoặc sự cố IdP cũng có thể làm 5xx tăng. **Nhiều IP truy cập không tự chứng minh botnet**, và nhiều request trên một IP không tự chứng minh người dùng xấu vì có NAT hoặc hệ thống tích hợp hợp lệ.

## 8. Thiết kế telemetry cho điều tra HTTP flood

### 8.1. Các trường log cần có

Một bản ghi request lý tưởng tại edge hoặc reverse proxy chứa:

| Trường | Mục đích |
|---|---|
| Timestamp UTC | Tương quan giữa edge, WAF, origin và dependency |
| Request ID / trace ID | Theo dõi một giao dịch xuyên qua các hệ thống |
| Host và route được chuẩn hóa | Xác định ứng dụng và endpoint bị áp lực |
| HTTP method/version | Phân biệt GET/POST, HTTP/2/3 |
| Response status và nguồn trả status | 429/403/503 do edge hay origin? |
| Latency, upstream time | Xác định vị trí tăng độ trễ |
| Cache status | HIT, MISS, BYPASS hoặc trạng thái tương đương |
| WAF action / rule ID | Quy tắc gì đã block/challenge/allow? |
| Client identity/segment (khi phù hợp) | Session, token, API consumer, nhóm người dùng |
| IP nguồn và proxy chain được tin cậy | Truy vết nguồn thực có ngữ cảnh NAT/CDN |
| Số byte gửi/nhận, request size | Phân tích băng thông và chi phí |
| Origin status, upstream server | Truy vết nút thắt và lỗi ở backend |

**Bảo vệ dữ liệu log:** URL query, header, cookie, token, email hoặc dữ liệu người dùng có thể nhạy cảm. Không log thông tin xác thực/bí mật ở dạng thô; giảm thiểu dữ liệu, kiểm soát quyền đọc và thời gian lưu theo chính sách tổ chức.

### 8.2. Ví dụ log JSON đã lược dữ liệu nhạy cảm

~~~json
{
  "time": "2026-11-28T06:00:00Z",
  "request_id": "lab-req-0001",
  "route": "/api/search",
  "method": "GET",
  "http_version": "2",
  "response_status": 429,
  "response_source": "edge_rate_limit",
  "edge_action": "throttle",
  "cache_status": "BYPASS",
  "latency_ms": 12,
  "upstream_time_ms": null,
  "client_class": "anonymous",
  "origin_reached": false
}
~~~

Đây là **schema minh họa**, không phải định dạng bắt buộc của nhà cung cấp. Trong phân tích thực tế, cần biết field nào chỉ có ở edge, field nào tồn tại ở origin và field nào được ghi theo sampling.

### 8.3. Phân tích thụ động log đã thu thập

Nếu phòng lab có file **sample-edge-access.jsonl** theo cấu trúc minh họa ở trên, có thể dùng lệnh **chỉ đọc file log** để thống kê những route xuất hiện nhiều nhất:

~~~bash
# Đọc log cục bộ đã được cho phép truy cập; không tạo HTTP traffic.
jq -r 'select(.route != null) | .route' sample-edge-access.jsonl \
  | sort \
  | uniq -c \
  | sort -nr \
  | head
~~~

Kết quả chỉ cho biết **số dòng log theo route** trong file; nếu hệ thống lấy mẫu hoặc log bị mất, không nên coi số dòng bằng số request thật. Ngoài ra, tổng số request theo route không nói lên mức chi phí xử lý nếu không có latency, cache status và dependency metrics.

## 9. Hệ thống phòng vệ nhiều lớp đối với HTTP flood

### 9.1. Lớp edge/CDN: hấp thụ và giảm tải

- Đưa nội dung công khai, tĩnh hoặc phù hợp vào cache, giảm số lượt về origin.
- Đặt WAF và rate limiting trước origin để tránh backend phải xử lý những request không cần thiết.
- Dùng năng lực edge phân tán/Anycast hoặc nhà cung cấp DDoS mitigation phù hợp khi kiến trúc và mức rủi ro yêu cầu.
- Đảm bảo origin chỉ chấp nhận các đường vào được duyệt (chẳng hạn qua CDN/load balancer/private connectivity) **khi phù hợp**, tránh để một hostname/IP origin công khai mở đường đi vòng WAF.
- Duy trì log và health của edge, vì một dashboard khỏe ở origin có thể che việc edge đang xử lý lượng traffic bất thường.

**Không tự động cache nội dung cá nhân hoặc nội dung xác thực.** Cache configuration phải xét Cache-Control, cookie, Authorization, Vary, cache key và phân vùng người dùng. Một cache rule sai có thể tạo sự cố rò rỉ dữ liệu nghiêm trọng hơn vấn đề hiệu năng cần giải quyết.

### 9.2. Lớp WAF/bot: quyết định theo ngữ cảnh

Tùy nền tảng, cơ chế có thể gồm:

- Rate limit theo route, session, API key, user identity hoặc tập điều kiện có nghĩa.
- Kiểm tra hình dạng request, dấu hiệu giao thức bất thường và chính sách ứng dụng.
- Bot reputation hoặc behavior analysis, phù hợp mục tiêu bảo mật và quyền riêng tư.
- Challenge dành cho một phần traffic chưa đủ tin cậy; có ngoại lệ hợp lý cho API máy-máy hoặc người dùng có nhu cầu trợ năng.
- Quản lý quy tắc theo trạng thái **log-only → challenge/throttle → block**, có giám sát false positive.

Không nên xem **User-Agent, một IP, quốc gia hoặc ASN** là bằng chứng duy nhất để chặn. Những đặc tính này có thể trùng giữa user hợp lệ và nguồn không mong muốn, hoặc thay đổi theo proxy/NAT.

### 9.3. Lớp load balancer/reverse proxy: giới hạn tiêu thụ

- Giới hạn số kết nối/requests đồng thời, request body/header size và timeout hợp lý.
- Giới hạn rate hoặc concurrency cho endpoint có chi phí cao.
- Giữ các hàng đợi được **bounded**, hạn chế tình trạng chờ vô hạn rồi tiêu thụ hết memory.
- Có health checks, retry policy và circuit breakers tránh khuếch đại sự cố.
- Phân tách đường kiểm soát/quản trị với traffic công khai, bảo vệ khả năng vận hành khi tải lớn.

### 9.4. Lớp ứng dụng và dữ liệu: giữ ổn định chức năng

- Dùng cache có kiểm soát cho kết quả có thể cache; kiểm tra chính sách dữ liệu và quyền.
- Phân tách pool/worker hoặc quota giữa endpoint nhạy cảm và endpoint tốn tài nguyên nếu kiến trúc cho phép.
- Tối ưu truy vấn, index, connection pool và giới hạn fan-out tới các dịch vụ phụ thuộc.
- Thực hiện **admission control/load shedding**: từ chối sớm một phần việc ít ưu tiên khi nguồn lực đã đầy, thay vì đợi toàn hệ thống timeout.
- Xây **idempotency** và xử lý retry an toàn cho thao tác ghi để tránh tạo giao dịch lặp do client tự động retry.
- Có circuit breaker và timeout rõ ràng để một dependency lỗi không kéo sập toàn API.

**Autoscaling không phải phương án thay thế kiểm soát DDoS.** Nó có độ trễ khởi tạo, giới hạn quota và chi phí; trong một số kiến trúc, tăng số web pod chỉ đẩy áp lực lớn hơn sang cùng một database.

## 10. Rate limiting: thiết kế đúng thay vì chặn bừa bãi

### 10.1. Chọn khóa áp dụng giới hạn

| Khóa | Điểm mạnh | Rủi ro/giới hạn |
|---|---|---|
| **Client IP** | Đơn giản, dùng được trước đăng nhập | NAT/CGNAT làm nhiều user dùng chung IP; IP phân tán giảm hiệu quả |
| **User/session** | Công bằng hơn khi đã xác thực | Phải tin cậy định danh; cần tính đến nhiều thiết bị và session |
| **API key/tenant** | Hợp với API máy-máy và quota khách hàng | Một tenant có thể có nhiều người dùng; khóa có thể bị lộ |
| **Route/operation** | Phù hợp chi phí và mức quan trọng mỗi endpoint | Cần quản lý route chuẩn hóa và thay đổi API |
| **Kết hợp các khóa** | Có thể giới hạn tổng và giới hạn cho từng người dùng/endpoint | Tăng độ phức tạp, có nguy cơ giới hạn nhầm |

**Tránh tin trực tiếp header do client tự gửi** như `X-Forwarded-For` nếu chưa cấu hình danh sách reverse proxy đáng tin và chuẩn hóa chuỗi proxy. Nếu sai, attacker có thể làm danh tính IP trong log/rate limit không chính xác; nếu chỉ lấy IP edge/CDN, nhiều client lại có thể bị gộp vào một nhóm.

### 10.2. Hai mô hình cơ bản

**Fixed window:** đếm số yêu cầu trong từng cửa sổ thời gian. Dễ triển khai nhưng có thể tạo burst ở ranh giới giữa hai cửa sổ.

**Token bucket:** mỗi đối tượng có một số token tối đa \(B\); hệ thống nạp token với tốc độ \(r\) token/giây. Mỗi request đủ điều kiện tiêu thụ một token; nếu không đủ token, có thể throttle, delay hoặc reject theo chính sách.

~~~text
Minh họa token bucket cho một nhóm client giả định:

Capacity B      = 20 tokens
Refill rate r   = 5 tokens / second
Request cost    = 1 token / request

Trạng thái full bucket: có thể chấp nhận burst ngắn.
Sau đó mức chấp nhận bền vững bị giới hạn bởi tốc độ nạp.
~~~

Các con số **20 và 5** là **giả định minh họa toán học**, không phải ngưỡng khuyến nghị cho website thật. Ngưỡng cần dựa trên phân bố request hợp lệ, độ biến thiên, độ quan trọng endpoint, khả năng tài nguyên và trải nghiệm người dùng.

### 10.3. Ví dụ Nginx rate limit (chỉ minh họa)

~~~nginx
# MẪU HỌC TẬP - không triển khai trực tiếp khi chưa review.
# Đặt trong cấu hình nginx hợp lệ và kiểm tra các context/đường xử lý.
http {
    limit_req_zone $binary_remote_addr zone=login_per_ip:10m rate=5r/s;

    upstream app_backend {
        server 127.0.0.1:8080;
    }

    server {
        listen 8081;

        location = /api/login {
            limit_req zone=login_per_ip burst=10 nodelay;
            limit_req_status 429;
            proxy_pass http://app_backend;
        }
    }
}
~~~

Trong cấu hình minh họa:

- `limit_req_zone` khai báo vùng trạng thái và ngưỡng trung bình **5 request/giây trên mỗi khóa IP**.
- `burst=10` cho phép xử lý một mức vượt ngưỡng ngắn hạn theo thuật toán module trước khi request bị từ chối; `nodelay` ảnh hưởng cách xử lý phần burst.
- `limit_req_status 429` trả **HTTP 429 Too Many Requests** khi request bị giới hạn; cần xem hành vi thực của phiên bản Nginx và đặt thông điệp/phục hồi phù hợp cho client.
- Ví dụ nghe trên **8081** để minh họa cấu trúc, không đại diện cho cấu hình HTTPS và WAF production.

**Lưu ý quan trọng:** nếu Nginx đứng sau CDN/load balancer mà không có cấu hình real client IP đúng và danh sách proxy đáng tin, `$binary_remote_addr` có thể chỉ là IP của proxy. Điều này làm nhiều người dùng hợp lệ cùng chịu một ngưỡng. Ngoài ra, chỉ bảo vệ `/api/login` thì các endpoint khác vẫn cần đánh giá riêng. Ngưỡng 5r/s không được chọn chỉ vì xuất hiện trong ví dụ.

### 10.4. 429, Retry-After và client retry

HTTP **429 Too Many Requests** thể hiện yêu cầu bị giới hạn. Server có thể cung cấp **Retry-After** khi phù hợp để client biết lúc nên thử lại; client cần backoff và jitter theo hợp đồng API. Nếu client tự động retry ngay lập tức mọi 429/503, có thể hình thành **retry storm**, làm tình hình nặng hơn.

**403** thường biểu thị từ chối theo chính sách truy cập; **429** chỉ giới hạn yêu cầu; **503** có thể biểu thị dịch vụ tạm thời không khả dụng. Trong thực tế edge/WAF có thể sử dụng các mã khác nhau, nên phải ghi **lớp phát sinh status** thay vì suy duy nhất từ mã HTTP.

## 11. Bảo vệ origin và dependency

### 11.1. Khóa đường vào origin theo thiết kế

Nếu ứng dụng dự kiến chỉ nhận truy cập qua CDN/WAF, cần hạn chế đường truy cập trực tiếp tới origin **bằng các cơ chế phù hợp với nhà cung cấp và kiến trúc**: allowlist nguồn edge, xác thực giữa edge–origin, private endpoint, network policy hoặc giải pháp được hỗ trợ. Chỉ dựa trên hostname công khai hoặc một IP allowlist tĩnh có thể không đủ nếu các dải edge thay đổi hoặc tồn tại đường phụ khác.

### 11.2. Bảo vệ database và dịch vụ xác thực

Giới hạn số request có thể xử lý đồng thời theo chi phí, ví dụ:

- API tìm kiếm đẩy nhiều truy vấn tới database: có concurrency cap và tối ưu query/cache.
- Login phụ thuộc IdP: có quota hợp lý theo danh tính/route và cơ chế giảm tải.
- Endpoint xuất dữ liệu/báo cáo: dùng hàng đợi bất đồng bộ và điều tiết tài nguyên khi phù hợp.
- Trạng thái truy cập giữa APP–DATA: default deny, chỉ mở những kết nối cần thiết, kết hợp IAM/RBAC và xác thực database.

Nếu backend không sẵn sàng, nên **từ chối hoặc xếp hàng có giới hạn** thay vì không ngừng tạo request và retry. Hạn mức tài nguyên cần tránh việc một nhóm tác vụ ít quan trọng chiếm hết khả năng xử lý của đăng nhập, thanh toán hoặc API thiết yếu.

### 11.3. Duy trì khả năng vận hành khi có sự cố

Sẵn sàng của monitoring, đường quản trị, DNS, IdP và các công cụ đổi chính sách là điều kiện để xử lý HTTP flood. Phân đoạn mạng, giới hạn quyền thay đổi WAF/DNS và tài khoản quản trị có MFA giúp giảm nguy cơ sai sót hoặc bị lạm dụng trong lúc đội ứng cứu đang chịu áp lực.

## 12. Phân biệt HTTP flood với flash crowd

Một chương trình bán vé hoặc khuyến mại có thể tạo traffic nhiều lần lớn hơn bình thường mà không có ý đồ xấu. **Chặn sai người dùng thật** có thể gây thiệt hại đáng kể, nên luôn xét các nguồn thông tin:

| Dấu hiệu | Có thể xuất hiện trong HTTP flood | Có thể xuất hiện trong flash crowd |
|---|---|---|
| RPS tăng mạnh | Có | Có |
| Người truy cập đến từ nhiều vùng/IP | Có | Có |
| Cache và database quá tải | Có | Có |
| Chênh lệch giữa request và giao dịch hoàn tất | Có thể | Có thể, nếu ứng dụng lỗi do tải |
| Phản hồi với challenge | Có thể thấp hoặc khác thường | Có thể cao với trình duyệt thật, nhưng phụ thuộc thiết bị |
| Tương quan với chiến dịch/sự kiện | Không nhất thiết | Thường có thể tìm thấy bằng chứng |
| Mẫu session/hành vi | Có thể bất thường | Có thể hợp lý theo luồng nghiệp vụ |

Không một dòng nào trong bảng là quy tắc tuyệt đối. Cần phối hợp **Security, SRE/Operations, Product, Marketing và chủ ứng dụng** để phân biệt tình huống và chọn chính sách giảm tải phù hợp. Trong sự cố chưa rõ nguồn gốc, ưu tiên hành động **ít chặn nhầm**, có giám sát và có thể rollback.

### 12.1. Bảo vệ người dùng có tính chính đáng

- Cân nhắc người dùng sau NAT/CGNAT, mạng doanh nghiệp, mạng di động và các ứng dụng tự động có phép.
- Tránh challenge không phù hợp với API máy-máy hoặc gây khó khăn không cần thiết cho người dùng sử dụng công nghệ hỗ trợ.
- Dùng quota theo tenant/API key khi phù hợp, với giới hạn ngân sách và cảnh báo rõ ràng.
- Cung cấp thông báo lỗi dễ hiểu, kiểm soát retry và cơ chế chờ/queue có thể dự đoán.
- Nếu cần áp dụng rule diện rộng, đặt **thời hạn và tiêu chí hạ cấp rule** khi tải trở về bình thường.

## 13. Playbook ứng cứu HTTP flood

### Giai đoạn A — Phát hiện và xác thực tác động

1. Nhận alert về RPS, origin saturation, latency, 5xx hoặc người dùng không hoàn tất giao dịch.
2. Xác nhận tác động tới những endpoint **quan trọng**: đăng nhập, thanh toán, API nghiệp vụ, DNS/IdP phụ thuộc.
3. Ghi lại thời điểm UTC, tên ứng dụng, route, RPS edge/origin, status code và thay đổi gần đây.
4. Phân biệt sự cố triển khai/dependency, flash crowd, automated abuse và khả năng HTTP flood; ghi mức tin cậy của giả thuyết.

### Giai đoạn B — Phân loại và khoanh vùng

1. Xác định nhóm endpoint hoặc ứng dụng nhận áp lực; so sánh edge vs origin để xem traffic được hấp thụ ở đâu.
2. Đánh giá WAF action, bot signals, cache hit, session/tenant, tốc độ truy cập và phân bố theo thời gian.
3. Truy vết từ load balancer tới API và database: pool wait, queue, CPU, dependency errors.
4. Xác định hiện tượng là L7, L3/L4 hay kết hợp; nếu băng thông upstream bị bão hòa, cần phối hợp nhà cung cấp mạng/CDN từ sớm.

### Giai đoạn C — Giảm thiểu theo mức rủi ro

1. Đặt rule ở **điểm bảo vệ sớm nhất có đủ thông tin**, thường là WAF/CDN/reverse proxy.
2. Ưu tiên **rate limit theo route/định danh**, challenge có chọn lọc và caching phù hợp; tránh block diện rộng chỉ vì một chỉ số.
3. Bảo vệ origin bằng admission control, connection/concurrency limits và giảm tải dependency.
4. Giữ luồng quan trọng hoạt động, không tự thay DNS, firewall hoặc route mà thiếu kế hoạch khôi phục.
5. Theo dõi ngay tác động rule: người dùng hợp lệ, 429/403, origin error, latency, CPU/database và doanh thu/giao dịch.

### Giai đoạn D — Khôi phục và đánh giá sau sự cố

1. Khi tải ổn định, hạ cấp các rule khẩn cấp theo kế hoạch; không để biện pháp tạm trở thành quyền/chặn vĩnh viễn không có chủ sở hữu.
2. Kiểm tra lại hiệu lực CDN/WAF và sức khỏe origin; xác nhận SLO nghiệp vụ.
3. Lưu timeline, evidence, rule ID, thay đổi cấu hình, liên hệ nhà cung cấp và quyết định đã thực hiện.
4. Rút kinh nghiệm: endpoint tốn tài nguyên, thiếu observability, false positives, cache, giới hạn gói dịch vụ, khả năng dự phòng và quy trình phối hợp.

~~~mermaid
flowchart TD
    A["Alert traffic hoặc SLO suy giảm"] --> B["Xác minh ảnh hưởng người dùng"]
    B --> C["So sánh edge - WAF - origin - dependency"]
    C --> D{"Nguyên nhân đủ tin cậy?"}
    D -- "Chưa" --> E["Điều tra deploy, flash crowd, lỗi phụ thuộc"]
    E --> C
    D -- "Có traffic bất thường" --> F["Áp dụng mitigation L7 có chọn lọc"]
    F --> G["Đo 429/403, 5xx, p95, tỷ lệ giao dịch"]
    G --> H{"SLO phục hồi, false positive chấp nhận?"}
    H -- "Chưa" --> I["Điều chỉnh rule / bảo vệ origin / phối hợp provider"]
    I --> G
    H -- "Đạt" --> J["Ổn định, rút rule tạm, postmortem"]
~~~

### 13.1. Phân công vai trò

| Nhóm | Trách nhiệm chính |
|---|---|
| Security/SOC | Điều tra dấu hiệu, tuning WAF/bot/IDS, giám sát block và ghi evidence |
| SRE/NOC | Đánh giá latency/5xx, capacity, routing, CDN, load balancer, khôi phục |
| App/DB team | Xác định endpoint tốn chi phí, dependency bottleneck, giải pháp load shedding |
| Product/Support | Đánh giá ảnh hưởng khách hàng, các sự kiện hợp lệ, thông báo và trải nghiệm |
| Nhà cung cấp CDN/ISP | Phối hợp khi vượt năng lực edge, có vấn đề upstream hoặc cần mitigation chuyên dụng |

Trách nhiệm cụ thể thuộc quy trình tổ chức; không để nhiều nhóm tự thay rule mâu thuẫn trên cùng một dịch vụ trong lúc xử lý sự cố.

## 14. Kiểm thử an toàn khả năng bảo vệ HTTP flood

### 14.1. Cần chứng minh điều gì?

| Test ID | Mục tiêu | Tiêu chí chấp nhận |
|---|---|---|
| **OBS-01** | Có đủ dữ liệu edge/origin | RPS, route, action, latency và status có thể đối chiếu theo thời gian |
| **RATE-01** | Rule rate limit hoạt động | Request thử **vượt ngưỡng trong lab có phép** được xử lý theo chính sách; có rule ID/log |
| **ALLOW-01** | Truy cập hợp lệ không bị chặn nhầm | Người dùng thử nghiệm hoàn tất luồng nghiệp vụ theo kịch bản |
| **NAT-01** | Nhiều user sau một proxy/NAT | Rule không gộp nhầm mọi người dùng thành một danh tính ngoài ý định |
| **CACHE-01** | Nội dung được phép cache phục vụ từ edge | Cache hit được ghi nhận và không phát sinh rò rỉ dữ liệu cá nhân |
| **ORIGIN-01** | Origin không bị mở bypass ngoài dự kiến | Đường vào origin tuân thủ kiến trúc đã duyệt |
| **APP-01** | Endpoint quan trọng được ưu tiên | Khi mô phỏng tải nhỏ có kiểm soát, luồng quan trọng giữ SLO kỳ vọng |
| **RECOV-01** | Rollback/tháo rule khẩn cấp | Trạng thái bình thường và quyền truy cập hợp lệ phục hồi |

Các phép thử cần có **đầu vào, giới hạn rate/concurrency, thời gian, điều kiện dừng, owner, log và dự kiến tác động**. Không dùng kịch bản gây ngập thực tế hoặc tấn công hệ thống công khai để xác minh khả năng phòng vệ.

### 14.2. Quan sát một request hợp lệ

~~~bash
# Một request HEAD tới endpoint lab do bạn quản lý;
# lệnh không tạo tải flood.
curl -I --connect-timeout 3 --max-time 10 \
  https://web.lab.example.test/health
~~~

Trong lab cần cấu hình DNS và chứng chỉ TLS cho tên minh họa; nếu không, lệnh có thể không kết nối được. **Một request** chỉ xác minh đường đi và phản hồi tại thời điểm thử, chưa kiểm tra rate limiting ở điều kiện tải. Việc đánh giá hiệu lực limit cần công cụ đo phù hợp trong **phòng lab giới hạn tải**, không nên tự tăng request vô kiểm soát.

### 14.3. Môi trường kiểm thử tải được phê duyệt

Khi cần thử khả năng chịu tải, nên có:

- Môi trường staging/lab có kiến trúc đủ đại diện, dữ liệu kiểm thử không nhạy cảm.
- Giới hạn RPS, concurrency, thời gian, ngân sách và **kill switch**; thử tuần tự tăng tải trong ngưỡng đã duyệt.
- Tài nguyên giám sát độc lập, ghi đủ edge, WAF, origin, database và SLO.
- Kịch bản luồng hợp lệ và luồng mà chính sách **định nghĩa** phải được throttle/challenge.
- Chủ sở hữu ứng dụng, đội vận hành và bên cung cấp CDN/ISP đồng ý nếu phép thử tác động hệ thống của họ.
- Quy trình dừng và khôi phục khi latency, error hoặc saturation vượt tiêu chí.

Kết quả cần báo rõ **môi trường và cấu hình đã kiểm**, không suy khả năng production từ một bài test nhỏ trên lab.

## 15. Case study: API tìm kiếm quá tải khi traffic tăng

### 15.1. Kiến trúc và sự kiện giả định

Một cửa hàng dùng CDN/WAF, load balancer, cụm API và database. Static assets được cache tốt, nhưng API tìm kiếm dùng dữ liệu theo thời gian thực nên mỗi request cần truy vấn nhiều bảng. Vào một thời điểm, edge RPS tăng và khoảng 70% request mới tập trung vào nhóm API tìm kiếm.

SRE thấy p95 API tăng, database pool wait cao, trong khi link Internet chưa bão hòa. Security thấy nhiều session truy cập với tần suất bất thường, nhưng đội Product cũng đang chạy một chiến dịch quảng cáo.

**Điểm quan trọng:** không thể dựa riêng vào 70% request hoặc mức tăng lưu lượng để kết luận DDoS. Đội xử lý cần phân biệt lượng người dùng mới hợp lệ, thói quen session và traffic không mong muốn; các tín hiệu này có thể trộn lẫn.

### 15.2. Phân tích đa lớp

| Quan sát | Ý nghĩa | Hành động điều tra |
|---|---|---|
| CDN cache hit cao với ảnh, thấp với API tìm kiếm | Lớp cache giảm tải ảnh nhưng API vẫn về origin | Tách dashboard theo route và cache eligibility |
| API p95 cao, DB pool wait tăng | Có dấu hiệu nút thắt ở dependency | Xem truy vấn chậm, pool, cache kết quả và fan-out |
| 429/403 tăng sau khi WAF bật rule | Rule có tác dụng nhưng có thể ảnh hưởng người thật | Xem rule ID, tỷ lệ challenge thành công và yêu cầu hỗ trợ |
| Doanh thu/giao dịch hoàn tất giảm | Đang có suy giảm nghiệp vụ | Ưu tiên giữ luồng mua hàng hoạt động |
| Có marketing campaign cùng thời điểm | Có khả năng flash crowd hoặc traffic hỗn hợp | Đối chiếu lịch chiến dịch, referral và session hợp lệ |

### 15.3. Phương án giảm thiểu

1. Tách nhóm endpoint **search**, **product detail**, **checkout** trong dashboard và chính sách.
2. Đặt giới hạn **có căn cứ theo chi phí** cho search tại edge, cân nhắc session/identity/tenant và NAT để giảm false positive.
3. Đánh giá cache kết quả tìm kiếm cho dữ liệu công khai được phép cache; không đưa dữ liệu cá nhân vào shared cache.
4. Hạn chế đồng thời truy vấn database, tối ưu query và áp dụng admission control để bảo vệ checkout.
5. Chạy rule mới ở chế độ quan sát hoặc phạm vi giới hạn; theo dõi response code, p95, DB pressure và tỷ lệ giao dịch hoàn tất.
6. Khi tình hình ổn định, xem lại những rule khẩn cấp, ghi chủ sở hữu và tiêu chí hạ cấp.

**Kết luận case:** một cách phòng vệ tốt không chỉ là “chặn nhiều request hơn” mà là **giảm áp lực lên nút thắt trong khi bảo toàn chức năng quan trọng cho người dùng hợp lệ**.

## 16. Sai lầm phổ biến

| Quan niệm sai | Vì sao sai | Cách cải thiện |
|---|---|---|
| “HTTP flood phải có băng thông rất lớn.” | L7 có thể làm nghẽn CPU/DB với RPS không quá lớn | Theo dõi chi phí xử lý và origin/dependency |
| “Chặn một IP đông request là đủ.” | NAT có người dùng thật; DDoS có thể phân tán | Kết hợp IP với identity/session/route và hành vi |
| “Có CDN nghĩa là không sợ HTTP flood.” | Endpoint động vẫn về origin | WAF/rate limit và bảo vệ origin |
| “Chỉ firewall L3/L4 là đủ.” | Request HTTP hợp lệ về cú pháp có thể gây tải ứng dụng | L7 policy và quản lý tài nguyên |
| “CPU tăng là do tấn công.” | Deploy lỗi, cache miss, retry storm cũng gây tăng | Tương quan dữ liệu và thay đổi gần thời điểm |
| “429 càng nhiều càng tốt.” | Có thể chặn nhầm và làm giảm tỷ lệ giao dịch thật | Theo dõi false positive và kết quả nghiệp vụ |
| “Cứ dùng ngưỡng rate limit chung cho mọi route.” | Chi phí xử lý giữa static/search/login/checkout khác nhau | Giới hạn theo endpoint/định danh và baseline |
| “Đọc X-Forwarded-For đầu tiên luôn đúng IP nguồn.” | Header có thể không đáng tin nếu proxy chain chưa cấu hình | Chỉ tin trusted proxies và chuẩn hóa real IP |
| “Tăng số web pod sẽ giải quyết mọi vấn đề.” | DB/quota/dependency có thể là nút thắt | Admission control và quản lý tài nguyên downstream |
| “WAF rule mới không cần rollback.” | False positive có thể gây sự cố lớn | Rollout giới hạn, log và kế hoạch hạ cấp |
| “Không có alert IDS tức không có HTTP flood.” | TLS, đường đi và giới hạn chữ ký có thể tạo điểm mù | Kết hợp edge/WAF/app/DB telemetry |
| “Dùng HTTP 403 là chứng minh đã chặn ở mạng.” | 403 là phản hồi tầng HTTP; kết nối mạng có thể đã hoạt động | Phân biệt tầng mạng, WAF và ứng dụng |

## 17. Bài tập tự kiểm tra

### Bài 1 — Phân biệt nút thắt

Một hệ thống nhận 5.000 RPS, băng thông mới đạt 30% năng lực đường truyền nhưng p95 API tăng gấp 10 và pool database đầy. Đây có thể là HTTP flood không? Điều gì còn thiếu để kết luận?

*Gợi ý:* có thể là L7 overload, nhưng cũng có thể là flash crowd, query chậm, cache thay đổi hoặc retry storm. Cần xem route distribution, hành vi session, triển khai gần thời điểm, logs WAF/edge, nguồn dữ liệu và kết quả nghiệp vụ.

### Bài 2 — Chọn rate-limit key

Một API phục vụ hàng trăm người dùng qua proxy/NAT cùng IP. Áp dụng limit thấp theo IP gây nhiều 429 cho người dùng thật. Bạn nên xem xét phương án gì?

*Gợi ý:* chọn limit theo user/session/tenant/API key khi phù hợp; phân biệt anonymous với authenticated, thiết kế burst, dùng trusted proxy config và xác minh false positive trước khi triển khai.

### Bài 3 — HTTP/2

Vì sao giới hạn **số kết nối TCP mới** không đủ đại diện cho lượng công việc mà một HTTP/2 application phải xử lý?

*Gợi ý:* nhiều stream và request có thể dùng chung một TCP connection; cần đo request, concurrent streams, CPU và thời gian xử lý.

### Bài 4 — Cache

Lớp CDN hiện xử lý tốt ảnh tĩnh nhưng endpoint `/api/account` có Authorization và dữ liệu cá nhân không được cache chung. Có nên bật cache công cộng cho endpoint này để chống flood?

*Gợi ý:* không tùy tiện. Nguy cơ rò rỉ dữ liệu khi shared cache vượt xa lợi ích; cần chính sách riêng theo danh tính, private cache khi phù hợp, rate limit và tối ưu backend.

### Bài 5 — Tín hiệu 429/503

Sau khi bật WAF rate limit, số request 429 tăng nhưng p95 origin giảm mạnh và người dùng hợp lệ vẫn hoàn tất giao dịch tốt. Nhận định thế nào?

*Gợi ý:* đây có thể là dấu hiệu mitigation hiệu quả. Tuy nhiên phải tiếp tục xem 429 theo user/tenant, nguồn phát sinh, tỷ lệ khiếu nại và false positive trước khi kết luận đầy đủ.

### Bài 6 — Flash crowd

Website bán vé có RPS tăng mạnh trong 10 phút, số session hợp lệ và giao dịch thành công cũng tăng. Có nên block toàn bộ các IP truy cập nhiều nhất không?

*Gợi ý:* không. Cần làm rõ người dùng thật, NAT, queue/capacity, ưu tiên các chức năng thiết yếu và giảm tải có chọn lọc. Chặn diện rộng có thể gây thiệt hại.

### Bài 7 — Bypass origin

WAF ở CDN ghi nhận nhiều request bị chặn nhưng origin vẫn nhận traffic đáng kể qua một điểm vào khác. Câu hỏi kiến trúc cần đặt ra là gì?

*Gợi ý:* còn đường đi trực tiếp hoặc qua LB/private endpoint ngoài WAF không? Route/ACL/origin authentication có kiểm soát đúng nguồn được duyệt không? Cần rà soát tại điểm bảo vệ, không chỉ thêm chữ ký.

### Bài 8 — Kế hoạch kiểm thử

Thiết kế một test case kiểm tra rate limiting cho API trong môi trường lab, nhưng không được gây quá tải. Những điều kiện nào bắt buộc?

*Gợi ý:* xác định ngưỡng thấp phù hợp lab, số request và khoảng thời gian giới hạn, owner, SLO, điều kiện dừng, kết quả mong đợi (allow/429), log WAF, kiểm tra người dùng hợp lệ và phương án rollback.

## 18. Checklist sẵn sàng phòng vệ HTTP flood

- Có **sơ đồ edge → WAF → load balancer → origin → dependency**, bao gồm các đường truy cập phụ.
- Biết **endpoint quan trọng và endpoint tốn chi phí**, cùng dữ liệu baseline theo thời gian.
- Có log/metrics **RPS, route, HTTP version, cache status, WAF action, origin latency, 5xx, 429, DB pool**.
- Đã phân biệt **status do edge trả** và status do ứng dụng/origin trả.
- Có **rate limiting theo route/định danh** và đã đánh giá NAT, API consumers, false positives.
- Cache được cấu hình **đúng quyền riêng tư và đặc điểm dữ liệu**, không cache nhầm thông tin cá nhân.
- Đường trực tiếp tới origin được kiểm soát theo kiến trúc; không chỉ trông cậy vào DNS ẩn tên origin.
- Có **admission control, bounded queue, concurrency limits, timeout/circuit breaker** phù hợp với ứng dụng.
- Các lớp phòng vệ bảo vệ cả **HTTP/1.1, HTTP/2, HTTP/3** trong phạm vi dịch vụ và edge thực tế.
- Có kế hoạch **mở rộng/giảm tải** hiểu rõ giới hạn quota và nút thắt database/IdP.
- Có **playbook ứng cứu**, owner của WAF/CDN, NOC/SRE, app/DB, kênh liên hệ ISP/provider.
- Có **test trong lab được phê duyệt**, tiêu chí an toàn, dừng và rollback; không gây flood lên môi trường ngoài phạm vi.
- Có quy trình rà soát các **rule khẩn cấp, false positives, chi phí và thời gian khôi phục** sau sự cố.

**Ghi nhớ:** HTTP flood là thách thức **đảm bảo tính sẵn sàng ở tầng ứng dụng**, không chỉ bài toán băng thông. Cách bảo vệ hiệu quả kết hợp **quan sát request đúng ngữ cảnh, giảm tải từ edge, giới hạn theo tài nguyên, bảo vệ origin và dependency, kiểm chứng trải nghiệm người dùng hợp lệ**. Mục tiêu sau cùng là duy trì các luồng nghiệp vụ quan trọng ngay cả khi traffic trở nên bất thường.

### Tài liệu tham khảo

- [NIST SP 800-61 Rev. 2 — Computer Security Incident Handling Guide](https://csrc.nist.gov/pubs/sp/800/61/r2/final): các giai đoạn xử lý sự cố bảo mật; tham khảo phương pháp lập playbook.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): kiểm soát truyền thông, tính sẵn sàng, giám sát và quản trị thay đổi.
- [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): các nguyên tắc phòng vệ DoS và kiểm soát tài nguyên ứng dụng.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): định nghĩa HTTP 429 Too Many Requests.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa HTTP, status và header liên quan.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): cách HTTP/2 xử lý connection và stream.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP trên QUIC.
- [NGINX — ngx_http_limit_req_module](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html): cách cấu hình và hiểu cơ chế giới hạn request.
