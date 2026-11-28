# TTL và failover trong DNS: Thiết kế chuyển hướng dịch vụ an toàn, có thể kiểm chứng

## 1. Bài toán: DNS ảnh hưởng thế nào đến khả năng phục hồi?

**Time to Live (TTL)** là khoảng thời gian, tính bằng **giây**, mà một bản ghi DNS được phép tồn tại trong cache theo chính sách TTL của dữ liệu và cách resolver xử lý. **DNS failover** là phương pháp thay đổi câu trả lời DNS khi một dịch vụ, địa chỉ hoặc khu vực triển khai gặp sự cố để các kết nối **mới** có thể tìm đến điểm phục vụ còn hoạt động.

Ví dụ: trang `shop.example.test` có máy chủ chính ở vùng A và một máy chủ dự phòng ở vùng B. DNS đang trả địa chỉ A, với TTL là 300 giây. Khi vùng A không hoạt động, hệ thống giám sát có thể đổi câu trả lời authoritative sang B. Tuy nhiên, nhiều recursive resolver và client **vẫn có thể dùng địa chỉ A đã cache** cho đến khi TTL liên quan hết hạn hoặc theo hành vi riêng của bộ nhớ đệm. Vì vậy, một lần cập nhật bản ghi thành công **không đồng nghĩa toàn bộ người dùng đã chuyển sang B**.

Trong chương **DNS security** thuộc module **SECURITY_NETWORK_SECURITY**, TTL và failover liên kết với kiến trúc mạng an toàn: bảo vệ DNS, firewall, VPN, IDS/IPS, phân đoạn mạng, giám sát luồng, xác thực kết nối và triển khai dịch vụ đa vùng/cloud. Thiết kế tốt phải đảm bảo **tính sẵn sàng (availability)** mà vẫn duy trì **tính toàn vẹn câu trả lời DNS, quyền thay đổi cấu hình và các biện pháp bảo vệ dữ liệu**.

**Mục tiêu sau bài học:**

1. Giải thích TTL của bản ghi, cache recursive/client, CNAME, negative caching và serve-stale.
2. Phân biệt **DNS failover**, load balancing, anycast, local failover và việc thay đổi nameserver/delegation.
3. Hiểu ảnh hưởng của TTL, health-check interval, detection time, policy switch và client behavior đến thời gian phục hồi.
4. Thiết kế active–passive hoặc active–active có health check, hysteresis, failback và bảo vệ origin.
5. Đọc câu trả lời từ authoritative và recursive resolver bằng `dig`; xây test matrix theo vùng và theo thời điểm.
6. Lập runbook thay đổi DNS có kiểm soát, phân tích lỗi và đo mức đạt SLO/RTO.

> **Phạm vi thực hành:** mọi tên miền `example.test`, IP `192.0.2.0/24`, `198.51.100.0/24` và `203.0.113.0/24` trong bài chỉ dùng cho tài liệu/lab giả định. Không chạy lệnh thay đổi zone công khai hoặc diễn tập ngắt dịch vụ ngoài hệ thống được phép quản trị.

## 2. Cơ chế DNS và nơi TTL được sử dụng

### 2.1. Từ client đến authoritative nameserver

~~~mermaid
flowchart LR
    C["Ứng dụng / trình duyệt"] --> S["Stub resolver / OS cache"]
    S --> R["Recursive resolver"]
    R --> A["Authoritative DNS"]
    A -->|"RRset + TTL"| R
    R -->|"Câu trả lời, TTL còn lại"| S
    S -->|"Địa chỉ đích"| C
    C -. "TCP/TLS/QUIC session tới địa chỉ đã chọn" .-> O["Origin / Load balancer"]
~~~

Thực tế có thể có thêm tầng cache của trình duyệt, runtime, proxy, sidecar, container hoặc thiết bị mạng. **Authoritative nameserver** chứa dữ liệu DNS có thẩm quyền cho zone; **recursive resolver** truy vấn thay client và có thể cache kết quả; **stub resolver** hoặc phần mềm ứng dụng nhận kết quả để mở kết nối.

**Điểm khác biệt quan trọng:** TTL gắn với dữ liệu DNS, không trực tiếp gắn với phiên TCP, TLS hoặc HTTP đã mở. Một ứng dụng đang dùng kết nối lâu dài tới IP A **không bắt buộc** tự ngắt phiên và chuyển sang IP B khi TTL bản ghi hết hạn.

### 2.2. TTL là thuộc tính của bản ghi DNS, không phải “đồng hồ toàn Internet”

Một Resource Record (RR) có các thành phần như tên, loại, lớp, TTL và dữ liệu. Các RR cùng **tên, loại, lớp** tạo thành một **RRset**; những RR trong cùng RRset cần được xử lý với TTL nhất quán theo quy tắc giao thức.

~~~dns
; Dữ liệu zone minh họa, không phải zone thực tế.
$ORIGIN example.test.
$TTL 300
shop         300  IN  A      192.0.2.20
api          120  IN  A      192.0.2.30
app          300  IN  CNAME  shop.example.test.
~~~

Trong ví dụ trên:

- `shop.example.test.` có TTL **300 giây** ở bản ghi A.
- `api.example.test.` có TTL **120 giây**.
- `app.example.test.` trỏ CNAME đến `shop.example.test.`, **mỗi RRset trong chuỗi có TTL riêng**.
- `$TTL 300` thiết lập TTL mặc định trong cú pháp zone file cho RR không khai báo TTL riêng; nó **không phải** chỉ thị ép mọi resolver cache mọi dữ liệu của zone đúng 300 giây.

Khi recursive resolver trả một bản ghi lấy từ cache, TTL hiển thị thường là **thời gian còn lại**, giảm dần. Nếu resolver đã cache địa chỉ A ở thời điểm T0 với TTL 300 giây, nó thường có thể tiếp tục trả dữ liệu đó đến gần T0 + 300 giây mà không truy vấn lại authoritative. Các resolver khác bắt đầu cache ở thời điểm khác sẽ có hạn hết cache khác nhau.

### 2.3. Những lớp cache tác động đến thời điểm đổi đích

| Lớp | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| **Authoritative server** | Nền tảng DNS được quản lý, primary/secondary authoritative | TTL và dữ liệu hiệu lực; trạng thái đồng bộ giữa các node |
| **Recursive resolver** | Resolver doanh nghiệp, ISP, public DNS | TTL còn lại, cache policy, min/max TTL, serve-stale, refresh |
| **OS/stub** | Hệ điều hành trên máy khách, VM, container | Cơ chế cache, thời điểm truy vấn lại, resolver được cấu hình |
| **Application/runtime** | Trình duyệt, JVM, HTTP client, database driver, proxy | Application DNS cache, connection pool, keep-alive và retry |
| **Service discovery/gateway** | Service mesh, DNS proxy, internal discovery | Cache riêng, cách tái phân giải, route và lựa chọn endpoint |

Các lớp cache có thể khiến hiệu quả thực khác tính toán lý tưởng theo TTL. Một số triển khai giới hạn TTL tối thiểu/tối đa, trả dữ liệu **serve-stale** khi authoritative không truy cập được, hoặc dùng chính sách cache riêng. Vì vậy, “TTL = 30 giây” **không phải bảo đảm tất cả client chuyển sang IP mới sau đúng 30 giây**.

## 3. Positive caching, negative caching và serve-stale

### 3.1. Positive caching

Khi resolver nhận được câu trả lời như A, AAAA, CNAME hoặc MX hợp lệ, nó có thể cache RRset theo TTL. Đổi A của `shop.example.test` tại authoritative không chủ động xóa bản ghi cũ tại mọi resolver.

**Ví dụ theo thời gian:**

~~~text
T0      Recursive resolver R lấy A = 192.0.2.20, TTL 300.
T+40    DNS authoritative được cập nhật sang 198.51.100.20.
T+60    Client hỏi resolver R: R có thể trả 192.0.2.20 với TTL còn ~240.
T+300   Cache cũ của R hết hạn theo mô hình lý tưởng.
T+301   R truy vấn mới và có thể lấy 198.51.100.20.
~~~

Đây là **mô phỏng đơn giản** không có serve-stale, prefetch, giới hạn TTL hay cache ứng dụng. Các recursive resolver khác sẽ hết cache ở thời điểm khác.

### 3.2. Negative caching: NXDOMAIN và NODATA

DNS không chỉ cache câu trả lời **có dữ liệu**, mà còn có thể cache **không tồn tại tên (NXDOMAIN)** hoặc **không có RRset của loại được hỏi (NODATA)**. Theo RFC 2308, thời gian negative caching được tính dựa trên **giá trị nhỏ hơn giữa TTL của SOA trong thông tin trả về và trường SOA.MINIMUM**, trong ngữ cảnh câu trả lời âm tính hợp lệ; cần kiểm tra hành vi resolver thực tế.

Hệ quả: nếu tên `backup.example.test` **chưa tồn tại** rồi được tạo ngay trước failover, người dùng đã hỏi tên này trước đó có thể tiếp tục nhận **negative cache** trong một thời gian. Do đó, thiết kế failover nên **chuẩn bị sẵn hostname/record dự phòng** và xác minh khả năng phân giải trước khi có sự cố.

**Phân biệt:** negative caching không phải TTL của bản ghi A. Không nên chỉ giảm TTL của A rồi mặc định việc tạo một tên mới sẽ có cùng thời gian hội tụ.

### 3.3. Serve-stale

Một số resolver hỗ trợ **serve-stale**: khi dữ liệu cache đã quá TTL và việc làm mới thất bại, resolver có thể tiếp tục trả bản ghi cũ để tăng khả năng phục hồi dịch vụ DNS, theo chính sách và giới hạn đã cấu hình. Cơ chế này được mô tả trong **RFC 8767**.

Serve-stale có lợi khi authoritative nameserver bị lỗi nhưng bản ghi cũ vẫn đưa người dùng tới một điểm hoạt động. Ngược lại, nếu bản ghi cũ trỏ tới **dịch vụ đã hỏng**, việc tiếp tục phục vụ dữ liệu cũ có thể trì hoãn hiệu quả failover đối với nhóm client đó.

> Cần đo hành vi resolver trong điều kiện vận hành thật; không suy ra thời gian hội tụ tuyệt đối chỉ từ TTL ở zone file.

### 3.4. CNAME, SVCB/HTTPS và chuỗi phụ thuộc

Nếu `www.example.test` là CNAME trỏ đến `site.cdn.example.test`, client có thể phải lấy **CNAME RRset** và RRset địa chỉ của đích. Từng RRset có TTL riêng. Thay đổi CNAME không làm bản ghi A/AAAA của hostname đích hết cache; đổi bản ghi A ở đích cũng không ép CNAME được hỏi lại.

Với những mô hình dùng **HTTPS/SVCB** hoặc alias/provider-specific record, cần xem TTL và hành vi tổng hợp câu trả lời của nhà cung cấp. Không được giả định giá trị `TTL=60` ở cấu hình frontend là TTL thực cho mọi dữ liệu được trả.

## 4. DNS failover là gì và điều gì nó không làm được?

### 4.1. Kịch bản active–passive

Một hệ thống có:

- **Primary:** vùng A, địa chỉ `192.0.2.20`.
- **Standby:** vùng B, địa chỉ `198.51.100.20`.
- **Authoritative DNS:** trả primary khi khỏe, đổi sang standby khi policy sức khỏe xác nhận primary không đáp ứng.

~~~mermaid
flowchart TD
    U["Client mới"] --> R["Recursive DNS"]
    R --> AD["Authoritative DNS / health-based answer"]
    H["Health checks độc lập"] --> AD
    AD -- "Primary healthy" --> A["Primary / 192.0.2.20"]
    AD -- "Primary unhealthy" --> B["Standby / 198.51.100.20"]
    R -. "Có thể vẫn cache IP cũ" .-> A
~~~

**Failover DNS hướng người dùng mới tới đích mới thông qua phân giải tên**. Nó không:

- Chủ động cắt các TCP/TLS/QUIC connection đang mở đến IP cũ.
- Ép mọi recursive resolver và client bỏ cache trước thời hạn.
- Đảm bảo dữ liệu ứng dụng đã được replicate hoặc standby có đủ năng lực phục vụ.
- Thay thế local load balancer, database HA, queue durability hay kiểm soát split-brain.
- Tự sửa các vấn đề firewall, TLS certificate, route, DNSSEC hoặc quyền truy cập ở vùng dự phòng.

### 4.2. So sánh các phương pháp chuyển vùng

| Cơ chế | Cách chọn đích | Ưu điểm | Giới hạn cần nhớ |
|---|---|---|---|
| **DNS active–passive** | DNS trả primary hoặc standby theo health/policy | Đơn giản ở mức hostname, dùng được đa vùng | Cache và hành vi client làm hội tụ không đồng nhất |
| **DNS active–active** | DNS trả nhiều vùng, dùng weighted/latency/geolocation hoặc health policy | Phân phối tải, giảm lệ thuộc một vùng | Phải xử lý dữ liệu và health từng vùng; cache ảnh hưởng thay đổi trọng số |
| **Load balancer với VIP ổn định** | VIP giữ nguyên, LB chọn backend còn khỏe | Failover backend có thể diễn ra mà client không đổi DNS | VIP/LB và kết nối hiện tại phải được thiết kế HA |
| **Anycast/BGP steering** | Nhiều điểm quảng bá cùng địa chỉ; routing chọn đường | Có thể chuyển tuyến ở tầng mạng | Phụ thuộc định tuyến/nhà cung cấp; không thay thế health ứng dụng |
| **Application/service discovery** | Client/gateway lựa chọn endpoint theo trạng thái | Có thể giảm phụ thuộc DNS TTL khi thiết kế phù hợp | Yêu cầu client và hệ thống discovery hỗ trợ, xử lý retry/state |

Không dùng “DNS failover” như tên gọi cho mọi loại high availability. Khi SLO yêu cầu phục hồi cực nhanh hoặc giữ kết nối đang hoạt động, chỉ đổi bản ghi DNS có thể không đáp ứng mục tiêu.

### 4.3. Không nên dùng thay đổi NS/delegation cho failover ứng dụng thông thường

Thay đổi **nameserver/delegation** không giống đổi bản ghi A/AAAA. NS RRset ở parent/child, glue khi cần, DS/DNSSEC và cache các dữ liệu này có TTL riêng. Việc chuyển nhà cung cấp authoritative DNS hoặc đổi delegation thường cần quy trình chuyển dịch riêng, không phải phương pháp thay IP origin tức thì khi có sự cố ứng dụng.

Đối với failover ứng dụng, ưu tiên cơ chế health-based answer tại tầng DNS authoritative đã sẵn sàng, hoặc một kiến trúc HA khác phù hợp, thay vì chờ thay đổi NS record trong sự cố.

## 5. TTL tác động thế nào đến thời gian phục hồi?

### 5.1. Phân rã thời gian chuyển đổi

Một kịch bản failover có nhiều giai đoạn:

1. **Sự cố bắt đầu:** primary không còn đáp ứng mục tiêu sức khỏe.
2. **Phát hiện:** hệ thống health monitoring quan sát đủ lần lỗi.
3. **Ra quyết định:** policy xác nhận cần chuyển, có thể có điều kiện chống dao động.
4. **Cập nhật DNS authoritative:** câu trả lời mới có hiệu lực ở các authoritative node liên quan.
5. **Hết hạn cache:** recursive resolver và các cache khác lấy câu trả lời mới theo hành vi của chúng.
6. **Client tái kết nối:** ứng dụng hỏi lại DNS và mở phiên mới tới standby.
7. **Standby phục vụ:** dịch vụ và các phụ thuộc ở vùng B sẵn sàng xử lý.

~~~mermaid
flowchart LR
    A["Primary lỗi"] --> B["Health check xác nhận"]
    B --> C["Policy chuyển đích"]
    C --> D["Authoritative trả IP standby"]
    D --> E["Resolver/client lấy đáp án mới"]
    E --> F["Client mở kết nối mới"]
    F --> G["Standby phục vụ thành công"]
~~~

Một mô hình ước lượng **để lập kế hoạch**:

\[
T_{\text{user recovery}} \approx
T_{\text{detect}} +
T_{\text{decision}} +
T_{\text{authoritative}} +
T_{\text{cache/client}} +
T_{\text{application}}
\]

Trong đó **thành phần cache/client có phân bố theo nhiều nhóm người dùng, không phải một hằng số**; các giai đoạn cũng có thể chồng lấp. Công thức minh họa giúp phân tích nút thắt, **không tạo giới hạn trên chắc chắn** cho mọi client.

### 5.2. Ví dụ TTL 300 giây so với 30 giây

Giả sử health checker cần **20 giây** để xác nhận lỗi; hệ thống authoritative cập nhật ngay khi nhận quyết định. Một recursive resolver vừa cache A tại thời điểm primary bắt đầu hỏng:

| Tình huống lý tưởng | TTL 300 giây | TTL 30 giây |
|---|---:|---:|
| Phát hiện và chuyển tại authoritative | 20 giây | 20 giây |
| Cache của resolver vừa được làm mới trước lỗi | Có thể còn gần 300 giây | Có thể còn gần 30 giây |
| Lúc resolver hỏi lại trong mô hình đơn giản | Khoảng 300 giây tính từ lần cache | Khoảng 30 giây tính từ lần cache |
| Độ tin cậy của thời gian cho mọi client | **Không được bảo đảm** | **Không được bảo đảm** |

Không cộng **20 + 300** một cách máy móc trong ví dụ này vì cache đã bắt đầu đếm trước khi health check phát hiện sự cố; các giai đoạn diễn ra **song song**. Với resolver khác mới cache bản ghi cũ ở một thời điểm gần lúc chuyển authoritative, thời gian tính từ **khi sự cố xảy ra** có thể khác. Cần đo từ góc nhìn **nhiều recursive resolver và client**.

TTL thấp thường giúp resolver hỏi lại sớm hơn sau thay đổi, **nhưng không bảo đảm mọi ứng dụng tái phân giải**, nhất là khi có connection pool, cache runtime hoặc serve-stale.

### 5.3. TTL quá thấp có đánh đổi gì?

| TTL thấp | TTL cao |
|---|---|
| Resolver có cơ hội cập nhật địa chỉ sớm hơn | Giảm tần suất hỏi authoritative khi cache có hiệu lực |
| Tăng số lần cache miss/refresh tại recursive resolver | Ít truy vấn refresh hơn đối với dữ liệu ổn định |
| Có thể tăng tải authoritative và phụ thuộc vào khả năng truy vấn DNS | Chậm chuyển địa chỉ hơn khi cần đổi đích |
| Không thắng được cache ứng dụng, min TTL hoặc serve-stale | Có thể tăng thời gian client còn dùng địa chỉ cũ |
| Phù hợp khi cần agility và hạ tầng DNS đã sizing đúng | Phù hợp hơn với dữ liệu ít thay đổi, nếu đáp ứng RTO |

**Minh họa định lượng:** trong một mô hình rất đơn giản, một resolver có nhu cầu liên tục với cùng RRset có thể refresh khoảng **mỗi TTL giây**. TTL 30 giây có thể khiến nó hỏi lại khoảng **10 lần thường xuyên hơn** so với TTL 300 giây. Đây không phải quy luật cho tổng QPS toàn Internet vì số resolver, lưu lượng, prefetch, min/max TTL, negative caching và cơ chế cache khác nhau.

### 5.4. RTO và RPO không giống TTL

- **RTO (Recovery Time Objective):** khoảng thời gian tối đa doanh nghiệp chấp nhận dịch vụ chưa khôi phục ở mức được xác định.
- **RPO (Recovery Point Objective):** mức dữ liệu có thể mất, tính theo thời điểm khôi phục/độ trễ dữ liệu, tùy mô hình hệ thống.
- **DNS TTL:** thuộc tính cache của câu trả lời DNS, **không phải chỉ tiêu khôi phục end-to-end**.

TTL 60 giây không có nghĩa RTO chắc chắn là 60 giây. Và dù DNS đưa client sang vùng B, nếu database ở đó thiếu các giao dịch mới nhất, vấn đề **RPO** vẫn còn.

## 6. Thiết kế health check đúng cho DNS failover

### 6.1. Kiểm tra điều gì?

Một health check chỉ ping ICMP hoặc mở TCP/443 có thể thấy máy còn kết nối được nhưng **ứng dụng đã hỏng**. Kiểm tra nên phản ánh chức năng phục vụ mà DNS đang hướng tới:

| Kiểu check | Phát hiện được | Giới hạn |
|---|---|---|
| ICMP/ping | Khả năng phản hồi mạng ở mức đơn giản | ICMP có thể bị chặn; không kiểm tra ứng dụng |
| TCP connect | Có listener và đường TCP đến đích | Không chứng minh HTTP/TLS/DB đang hoạt động |
| TLS handshake | Có thể đàm phán TLS tại endpoint | Chưa xác nhận API nghiệp vụ và dữ liệu |
| HTTP health endpoint | Ứng dụng trả mã/trạng thái được thiết kế | Có thể quá nông nếu không kiểm tra dependency |
| Readiness có kiểm soát | Có thể xử lý các yêu cầu thiết yếu | Cần tránh health endpoint tự gây tải hoặc phụ thuộc vòng |
| Synthetic transaction | Kiểm tra luồng người dùng tiêu biểu | Tốn chi phí, dễ gây sai lệch nếu chạy quá thường xuyên |

Phải quyết định **healthy nghĩa là gì**: vùng B có được phép nhận người dùng khi API hoạt động nhưng database replication chưa bắt kịp? Nếu ứng dụng đọc/ghi dữ liệu, health check cần liên hệ với cơ chế an toàn dữ liệu và chính sách khôi phục của hệ thống.

### 6.2. Đo từ nhiều vị trí độc lập

Một lần timeout từ một điểm giám sát có thể phản ánh sự cố **tuyến mạng của monitor**, không phải toàn bộ dịch vụ. Có thể kiểm tra từ nhiều vị trí mạng/vùng địa lý độc lập, dùng ngưỡng đồng thuận, loại trừ sự cố DNS resolver của chính monitor và ghi lại kết quả theo thời gian.

**Cẩn thận với lỗi chung:** nếu tất cả health probes đi qua cùng DNS, VPN, NAT, ISP hoặc một endpoint phụ thuộc, một lỗi ở điểm chung có thể khiến hệ thống hiểu nhầm nhiều vùng đều hỏng.

### 6.3. Hysteresis và tránh failover/failback liên tục

**Hysteresis** là cách yêu cầu một điều kiện kéo dài hoặc nhiều lần kiểm tra liên tiếp trước khi chuyển trạng thái:

~~~text
Ví dụ CHÍNH SÁCH GIẢ ĐỊNH:
- Probe mỗi 10 giây.
- Primary bị đánh giá unhealthy sau 3 lần thất bại liên tiếp.
- Secondary chỉ được chọn khi health, dữ liệu và capacity đều đạt.
- Chưa failback chỉ vì 1 probe primary thành công.
- Cần nhiều probe khỏe liên tiếp và thời gian ổn định trước failback.

Lưu ý: 3 x 10 giây không phải lúc nào cũng là đúng 30 giây phát hiện:
thời điểm lỗi, request timeout, scheduler và cửa sổ probe ảnh hưởng.
~~~

Mức timeout, số lần lỗi và cooldown cần dựa trên SLO và số liệu thực, không lấy từ ví dụ làm cấu hình mặc định. **Failback** về primary thường cần thận trọng hơn failover để tránh traffic dao động giữa các vùng hoặc ghi dữ liệu vào hai nơi chưa đồng bộ.

## 7. Active–passive và active–active

### 7.1. Active–passive

Vùng A phục vụ chính; vùng B được duy trì ở trạng thái sẵn sàng. Khi A unhealthy, DNS chuyển sang B.

**Ưu điểm:** mô hình điều hành dễ hiểu, có thể giảm các xung đột dữ liệu nếu chỉ một vùng cho phép ghi. **Thách thức:** standby phải được kiểm tra thường xuyên, đủ công suất và có dữ liệu/cấu hình cần thiết; nếu chỉ khởi chạy khi lỗi xảy ra, thời gian khởi tạo có thể vượt RTO.

Checklist standby gồm: chứng chỉ TLS, hostname/SNI, secrets, IAM, firewall/security group, DNS nội bộ, database, queue, outbound API, logging, autoscaling, quota, load balancer, backup và kiểm soát thay đổi. Standby **trả HTTP 200** chưa chắc đã có thể xử lý giao dịch thực.

### 7.2. Active–active

Hai hoặc nhiều vùng đồng thời nhận một phần traffic thông qua weighted DNS, health-aware routing hoặc cơ chế toàn cục tương tự.

**Ưu điểm:** các vùng dự phòng đã xử lý traffic thực, dễ kiểm tra liên tục, có thể phân phối tải. **Thách thức:** đồng bộ dữ liệu, lưu lượng giữa vùng, session affinity, quyền ghi, chi phí duy trì capacity và chính sách điều hướng khi một vùng bị lỗi.

Nếu A đang nhận 50% traffic và A hỏng, B phải có năng lực tiếp nhận thêm phần đó; không nên mặc định autoscaling tăng đủ nhanh. **DNS weighted routing không bảo đảm đúng tỷ lệ traffic người dùng** vì recursive caching, phân bố resolver và hành vi client.

### 7.3. Failover từng vùng không thay thế failover từng dịch vụ

Một ứng dụng gồm frontend, API, cache, DB, IdP, queue, DNS và hệ thống log. DNS global chỉ thay địa chỉ web có thể để sót dependency vẫn trỏ về vùng A. Cần có **dependency map** và xác định vai trò của:

- Failover DNS bên ngoài cho endpoint public.
- Load balancer nội bộ cho backend trong một vùng.
- Cơ chế cluster/replication của database.
- DNS/service discovery nội bộ cho API giữa các workload.
- Xử lý session, retry, idempotency và leader election ở tầng ứng dụng.

## 8. Ví dụ cấu hình và câu trả lời DNS

### 8.1. Zone record trước sự cố

~~~dns
; Zone giả định cho example.test.
$ORIGIN example.test.
$TTL 300
shop   60 IN A     192.0.2.20
shop   60 IN AAAA  2001:db8:100::20
api   120 IN A     192.0.2.30
~~~

TTL của RRset A và AAAA có thể được thiết lập riêng, và **cả IPv4 lẫn IPv6** cần chính sách failover nếu dịch vụ dual-stack. Địa chỉ `2001:db8::/32` là dải IPv6 dành cho ví dụ tài liệu.

### 8.2. Câu trả lời sau chuyển vùng

~~~dns
; Minh họa kết quả policy failover khi primary unhealthy.
$ORIGIN example.test.
shop   60 IN A     198.51.100.20
shop   60 IN AAAA  2001:db8:200::20
~~~

Hai đoạn zone trên chỉ minh họa **trạng thái dữ liệu được trả**, không phải một cơ chế health-aware DNS bằng bản ghi chuẩn. Việc quyết định **khi nào trả A hay B** phải do hệ thống điều phối/nhà cung cấp DNS được hỗ trợ hoặc quy trình thay đổi có kiểm soát thực hiện.

### 8.3. Dùng CNAME thay vì thay A thì sao?

~~~dns
shop           60 IN CNAME active-region.example.test.
active-region  60 IN A     192.0.2.20
~~~

Nếu thay CNAME từ `active-region` sang `standby-region`, resolver có thể vẫn giữ **CNAME cũ** đến khi TTL của chính CNAME hết hạn. Nếu chỉ thay A của đích, TTL của RRset A chi phối thời điểm địa chỉ mới xuất hiện. Khi thiết kế chuỗi alias, cần kiểm tra **từng RRset** và không tạo chuỗi CNAME dài khó chẩn đoán.

**Lưu ý tại zone apex:** CNAME thông thường không được đặt ở apex nếu cùng tên có các record bắt buộc như SOA/NS. Những tính năng **ALIAS/ANAME hoặc CNAME flattening** là triển khai của nhà cung cấp; kiểm tra tài liệu cụ thể về TTL và câu trả lời được tổng hợp.

## 9. Quan sát TTL và kiểm thử failover bằng dig

Tất cả lệnh dưới đây giả định có DNS lab tại các địa chỉ **dành cho tài liệu**, đã được người học cấu hình và được phép thử. Nếu chưa có lab, hãy **đọc như ví dụ cú pháp**, không mong chờ các IP minh họa phản hồi trên Internet.

### 9.1. Hỏi trực tiếp authoritative server

~~~bash
# Lab authoritative DNS giả định tại 192.0.2.53.
# +norecurse để không yêu cầu server thực hiện recursion.
dig @192.0.2.53 shop.example.test A +norecurse +noall +answer
dig @192.0.2.53 shop.example.test AAAA +norecurse +noall +answer

# Xem header và flags, kiểm tra cờ AA khi có câu trả lời authoritative.
dig @192.0.2.53 shop.example.test A +norecurse
~~~

**Cần kiểm tra:** bản ghi A/AAAA, TTL được khai báo và cờ **AA (Authoritative Answer)** khi server trả lời có thẩm quyền. Trong hệ thống thật, kiểm tra **nhiều authoritative node** khi cần, nhất là sau thay đổi zone, để phát hiện bản ghi không đồng nhất.

### 9.2. Hỏi recursive resolver và theo dõi TTL còn lại

~~~bash
# Resolver lab giả định tại 192.0.2.54.
dig @192.0.2.54 shop.example.test A +noall +answer

# Sau một khoảng thời gian ngắn, chạy lại để so sánh TTL còn lại.
dig @192.0.2.54 shop.example.test A +noall +answer

# Nếu cần so sánh các resolver lab khác nhau:
dig @192.0.2.55 shop.example.test A +noall +answer
~~~

**Ví dụ đầu ra giả định:**

~~~text
shop.example.test.    58 IN A 192.0.2.20
# Ít lâu sau trên cùng resolver:
shop.example.test.    41 IN A 192.0.2.20
# Sau khi cache hết hạn và authoritative đổi:
shop.example.test.    60 IN A 198.51.100.20
~~~

TTL thay đổi phụ thuộc cache miss/refresh, prefetch và chính sách resolver; **không phải** lúc nào cũng giảm đều trong các lần hỏi. Nếu muốn mô phỏng failover trong lab, đổi trạng thái health trong **bộ điều phối DNS được phép**, không dùng lệnh truy vấn để làm thay đổi record.

### 9.3. Kiểm tra chuỗi alias và negative cache

~~~bash
# Xem alias
dig @192.0.2.54 app.example.test CNAME +noall +answer

# Hỏi loại A để thấy các RRset liên quan theo resolver.
dig @192.0.2.54 app.example.test A +noall +answer

# Một hostname không tồn tại trong lab: xem RCODE và SOA ở authority.
dig @192.0.2.54 missing.example.test A +noall +comments +authority
~~~

Khi thấy **NXDOMAIN**, kiểm tra SOA trả kèm và chính sách negative caching. Đừng dùng việc giảm TTL của một RRset A để suy rằng cache của một câu trả lời NXDOMAIN đã được kiểm soát.

### 9.4. Kiểm tra khả năng phục vụ HTTPS ở vùng đích

~~~bash
# Chỉ một request đến địa chỉ dự phòng qua HTTPS; tên giữ nguyên
# để kiểm tra SNI và chứng chỉ cho shop.example.test.
curl -I --connect-timeout 3 --max-time 10 \
  --resolve shop.example.test:443:198.51.100.20 \
  https://shop.example.test/health
~~~

Lệnh này **bỏ qua DNS lookup thông thường cho lần kiểm tra đó**, giúp đánh giá riêng standby endpoint theo hostname. Nó **không chứng minh** recursive DNS đã chuyển và không nên thay thế các phép thử DNS từ client thực. Cần có HTTPS endpoint, chứng chỉ hợp lệ và môi trường lab được cấu hình đúng; không bỏ kiểm tra chứng chỉ để nhận định standby đã sẵn sàng an toàn.

### 9.5. Đối chiếu recursive DNS với kết nối ứng dụng

Nếu một máy hỏi DNS đã thấy B nhưng ứng dụng vẫn dùng A, hãy kiểm tra **cache của tiến trình, HTTP connection pool, proxy, địa chỉ đã resolve từ trước và cơ chế retry**. Một lệnh `dig` chạy riêng biệt không phản ánh chắc chắn resolver library và cache trong tiến trình ứng dụng.

## 10. Thiết kế failover an toàn với DNSSEC

**DNSSEC** dùng chữ ký số để giúp resolver có khả năng xác thực **nguồn gốc và tính toàn vẹn** dữ liệu DNS. Nó không mã hóa nội dung truy vấn và không tự phát hiện health của dịch vụ.

Trong failover:

- Nếu nhà cung cấp DNS tạo câu trả lời động, phải bảo đảm **các RRset được ký và phục vụ đúng cách** theo mô hình DNSSEC của họ.
- TTL của bản ghi, **RRSIG validity**, DNSKEY, DS và trạng thái ký zone là các yếu tố khác nhau. Không được đồng nhất “TTL hết” với “chữ ký hết hiệu lực”.
- Khi chuyển nhà cung cấp DNS hoặc thay khóa/DS, lỗi chain of trust có thể khiến resolver validating trả **SERVFAIL**, ngay cả khi A record đúng.
- Phải kiểm tra **IPv4/IPv6, tất cả authoritative node và validating resolver** sau những thay đổi lớn.
- Hạn chế thay đổi DNSSEC/delegation cùng lúc với chuyển vùng ứng dụng trong sự cố nếu chưa có quy trình và kịch bản diễn tập.

**Quan trọng:** DNSSEC ngăn một số hình thức giả mạo dữ liệu DNS ở tầng xác thực, nhưng **không bảo đảm hệ thống trả lời đúng đích khỏe**. Nếu tài khoản quản trị DNS bị chiếm và vùng được sửa thành record có chữ ký hợp lệ, DNSSEC có thể vẫn xác thực dữ liệu đã bị sửa trái phép. Cần IAM/MFA, kiểm soát thay đổi và giám sát cấu hình.

## 11. Rủi ro bảo mật trong DNS failover

### 11.1. Chiếm quyền thay đổi DNS

Quyền thay đổi authoritative DNS, health policy và routing là quyền nhạy cảm: attacker hoặc cấu hình sai có thể chuyển traffic sang máy chủ không đáng tin, gây mất dịch vụ hoặc rò rỉ thông tin. Biện pháp cơ bản:

1. **MFA, tài khoản quản trị riêng, least privilege và phân quyền phê duyệt** cho thay đổi DNS.
2. Quản lý **API token/secrets** bằng dịch vụ phù hợp, không nhúng trong script/repo/log.
3. Bật **audit logs** và cảnh báo thay đổi record, TTL, routing policy, health checker hoặc nameserver.
4. Dùng **Infrastructure as Code** và review nếu phù hợp, có diff rõ ràng và khả năng rollback.
5. Xác thực **đích dự phòng** trước khi thêm vào policy: quyền sở hữu tài nguyên, TLS, firewall, mTLS/IAM và dữ liệu.

### 11.2. Sai cấu hình làm hỏng phạm vi người dùng

Tình huống thường gặp:

- Health checker thấy lỗi từ một mạng nhất định và **failover quá sớm** dù primary còn khỏe với nhiều người dùng.
- Standby trả HTTP 200 từ `/health` nhưng database thực tế chưa sẵn sàng, gây lỗi giao dịch.
- Chỉ chuyển **A** còn **AAAA** vẫn trỏ vùng lỗi; client ưu tiên IPv6 có thể tiếp tục thất bại.
- Ghi CNAME sang hostname chưa tạo hoặc đang negative-cached.
- Firewall/WAF/CDN ở vùng B không cho đúng hostname, certificate hoặc nguồn client.
- Quy tắc DNS weighted/geo khiến một nhóm recursive resolver vẫn được gửi tới đích không còn khỏe.
- Tự động failback gây **flapping**, phiên người dùng bị chia giữa hai vùng.

### 11.3. DNS amplification và tính sẵn sàng của dịch vụ DNS

Hệ thống authoritative hoặc recursive DNS cũng có thể bị DDoS riêng. TTL thấp có thể làm tăng tần suất hỏi authoritative trong một số mẫu tải, nên cần sizing, nhà cung cấp DNS có năng lực chống DDoS, authoritative đa điểm và bảo vệ resolver. **Không biến recursive DNS nội bộ thành open resolver** để phục vụ failover; giới hạn quyền recursion và giám sát truy vấn bất thường.

### 11.4. Tính nhất quán của DNS nội bộ và DNS công khai

Với **split-horizon/split-view DNS**, cùng tên miền có thể trả đích khác nhau từ mạng LAN, VPN, cloud và Internet. Failover public DNS có thể không thay đổi câu trả lời ở private zone. Do đó, cần ma trận kiểm tra từng view và đường mạng, bảo vệ các đường quản trị/ứng dụng như một phần của mô hình phân đoạn mạng.

## 12. Quy trình triển khai TTL và failover

### Bước 1 — Xác định chức năng và RTO/RPO

Chốt ứng dụng được bảo vệ, nhóm người dùng cần ưu tiên, mức dữ liệu có thể mất và thời gian gián đoạn được chấp nhận. Kiểm tra liệu **DNS failover đơn thuần** có phù hợp với yêu cầu hay cần load balancer/VIP/anycast hoặc cơ chế HA tầng ứng dụng.

### Bước 2 — Lập sơ đồ phụ thuộc

Vẽ đường client → resolver → authoritative → CDN/LB → origin → database/IdP/queue. Ghi vị trí TLS termination, NAT, phân đoạn mạng, DNS internal/public, IPv4/IPv6 và kết nối lâu dài. Xác định đường nào **không thay đổi** khi record DNS đổi.

### Bước 3 — Chuẩn bị standby

Đảm bảo standby có dữ liệu, secrets, chứng chỉ, quyền truy cập, firewall, endpoint và công suất thích hợp. Dùng direct-endpoint test (ví dụ `curl --resolve` trong lab) để kiểm chứng trước khi cho traffic thật chuyển sang. Chuẩn bị sẵn record/hostname cần thiết nhằm tránh negative cache.

### Bước 4 — Chọn TTL bằng số liệu

Đo QPS DNS, TTL hiện tại, khả năng authoritative, phân bố các loại recursive resolver, DNS cache của runtime và độ trễ ứng dụng. Chọn TTL theo **mục tiêu RTO và năng lực vận hành**, không dựa vào khẩu hiệu “càng thấp càng tốt”. Nếu dự kiến bảo trì, có thể giảm TTL **trước thay đổi đủ sớm so với TTL cũ** để các cache trước đó có cơ hội hết hạn; vẫn phải tính cache ngoài kiểm soát.

### Bước 5 — Thiết kế health policy

Chọn health endpoint phản ánh readiness, kiểm tra đa vị trí, ngưỡng liên tiếp, cooldown, điều kiện standby khỏe và quy trình failback. Giảm nguy cơ **single point of failure của hệ thống điều phối DNS** hoặc monitoring.

### Bước 6 — Chạy diễn tập có phép

Diễn tập trong lab hoặc vùng thử nghiệm với dữ liệu không nhạy cảm. Đo thời gian từ sự cố giả định, health detection, câu trả lời authoritative mới, các recursive resolver chuyển đổi đến tỷ lệ client thành công tại standby. Thử IPv4/IPv6, VPN/split DNS, TLS và caching của ứng dụng.

### Bước 7 — Triển khai từng phần và giám sát

Nếu có khả năng, dùng canary/weighted traffic theo chính sách để xác minh standby nhận một phần traffic hợp lệ. Quan sát latency, error, database replication, capacity, DNS answer mix và phản hồi người dùng; có rollback.

### Bước 8 — Rà soát vòng đời

Mỗi khi thay IP, endpoint, CDN, DNS provider, certificate, health path, database hoặc network route, phải cập nhật sơ đồ và diễn tập lại. Kiểm soát thay đổi TTL/routing như một thành phần của **security change management** chứ không chỉ là thao tác “đổi IP trên DNS”.

## 13. Ma trận kiểm thử

| Test ID | Mục tiêu | Phương pháp | Điều kiện PASS |
|---|---|---|---|
| **TTL-01** | Authoritative trả TTL đúng | Truy vấn trực tiếp các authoritative node | TTL và RRset đúng thiết kế trên các node |
| **TTL-02** | Thấy thời gian còn lại trên recursive cache | Hỏi cùng resolver tại nhiều thời điểm | Diễn giải được TTL/caching, không giả định làm mới ngay |
| **DNS-01** | Active–passive trả đích đúng | Đánh dấu primary healthy/unhealthy trong lab | Authoritative chọn đúng IP theo policy |
| **DNS-02** | A/AAAA đồng nhất | Hỏi A và AAAA trước/sau switch | Không để một stack trỏ đích hỏng ngoài dự kiến |
| **DNS-03** | CNAME/alias không giữ đích sai | Hỏi theo chuỗi và ghi TTL từng RRset | Các alias và đích được cập nhật phù hợp |
| **DNS-04** | Không có lỗi negative cache bất ngờ | Kiểm tra hostname standby tồn tại trước diễn tập | Không bị NXDOMAIN/NODATA ngoài dự kiến |
| **HEALTH-01** | Phát hiện lỗi đúng | Giả lập lỗi app trong lab | State đổi sau ngưỡng được duyệt, không dựa một probe |
| **HEALTH-02** | Không failback quá sớm | Khôi phục health, đo cooldown | Trạng thái ổn định trước khi chuyển lại |
| **APP-01** | Standby phục vụ HTTPS/API | Truy cập với đúng Host/SNI/TLS | TLS hợp lệ và giao dịch thử thành công |
| **CACHE-01** | Resolver ở nhiều mạng hội tụ | So sánh public/corporate/VPN recursive resolvers | Ghi phân bố thời gian và tỷ lệ câu trả lời mới |
| **SEC-01** | DNSSEC hợp lệ sau switch | Validating resolver và xem SERVFAIL/AD theo ngữ cảnh | Không sinh lỗi xác thực do thay đổi |
| **SEC-02** | Chỉ người được phép đổi DNS | Review IAM, MFA, audit log, token scope | Đáp ứng quyền tối thiểu và truy vết thay đổi |
| **FAIL-01** | Không có đường origin phụ mở sai | So sánh firewall/CDN/standby route | Chỉ cho traffic theo kiến trúc được duyệt |
| **RECOV-01** | Phục hồi đạt SLO | Synthetic transaction từ nhiều client | Đo RTO thực tế theo nhóm, lỗi và thời gian |

### 13.1. Phân biệt PASS, FAIL và INCONCLUSIVE

- **PASS:** kết quả trùng mục tiêu **và** có log/bằng chứng ở đúng lớp. Ví dụ DNS authoritative trả B sau health fail, client test từ resolver X lấy B và HTTPS với SNI đúng hoạt động.
- **FAIL:** có bằng chứng trái kỳ vọng, như standby không được chọn dù health policy phải chuyển, hoặc IPv6 vẫn trỏ về primary hỏng.
- **INCONCLUSIVE:** test chưa hợp lệ hoặc thiếu bằng chứng, như DNS lab không được cấu hình, health checker không chạy, resolver dùng cache ngoài kiểm soát hoặc dịch vụ thử đã tắt không rõ nguyên nhân.

**Không coi một lần `dig` trả địa chỉ B là bằng chứng mọi người dùng đều đã khôi phục.** Phải đo trên nhiều network/resolver và ở tầng ứng dụng.

### 13.2. Mẫu biên bản diễn tập

~~~yaml
exercise_id: DNS-FAILOVER-LAB-01
scope: shop.example.test
environment: isolated-lab
mode: active-passive
primary: 192.0.2.20
standby: 198.51.100.20
record_ttl_seconds: 60
start_time_utc: "2026-11-28T02:00:00Z"
expected:
  authoritative_switch: after-approved-health-threshold
  tls_hostname: shop.example.test
  client_recovery: measured-not-assumed
evidence:
  - health-check-timeline
  - authoritative-answer-before-after
  - recursive-answer-time-series
  - dual-stack-results
  - client-tls-and-application-results
  - dns-change-audit
outcome: pending-execution
~~~

Mẫu trên **không khẳng định đã chạy phép thử**; thời gian và IP chỉ để minh họa cấu trúc lưu bằng chứng.

## 14. Playbook xử lý sự cố failover DNS

### Pha A — Phát hiện và phân loại

1. Nhận cảnh báo ứng dụng/health, ghi **thời điểm UTC**, hostname, loại bản ghi A/AAAA và nhóm người dùng bị ảnh hưởng.
2. Xác minh lỗi nằm ở **ứng dụng/origin**, **kết nối mạng**, **TLS**, **resolver**, **authoritative DNS** hay **DNSSEC**.
3. Kiểm tra dashboard health checker và log hệ thống; không kết luận failover chỉ từ một probe timeout.

### Pha B — Bảo vệ dữ liệu và xác nhận standby

1. Kiểm tra standby readiness, quyền kết nối, capacity, TLS certificate và trạng thái database replication.
2. Nếu có nguy cơ ghi hai vùng không nhất quán, phối hợp chủ dữ liệu và cơ chế leader/replication trước khi mở traffic.
3. Xác minh đường từ CDN/LB đến standby không vi phạm segmentation, firewall hoặc kiểm soát nguồn.

### Pha C — Chuyển điều hướng DNS theo quy trình

1. Kiểm tra policy health-based tự động đã chuyển hay chưa; nếu cần can thiệp thủ công, dùng tài khoản có quyền và change record phù hợp.
2. Đối chiếu câu trả lời **từ authoritative**, không chỉ recursive resolver đang cache.
3. Kiểm tra cả A/AAAA, alias và các DNS view (public/private/VPN).
4. Không xóa cache của tất cả recursive resolver ngoài kiểm soát bằng cách suy đoán; thay vào đó đo sự hội tụ và chuẩn bị hỗ trợ client.

### Pha D — Giám sát người dùng và phục hồi

1. Từ nhiều vị trí mạng, kiểm tra resolver, HTTPS/API có SNI đúng, tỷ lệ thành công, p95/p99 và các giao dịch quan trọng.
2. Theo dõi client vẫn kết nối primary do phiên cũ, cache hoặc retry; đánh giá có cần thêm biện pháp ở load balancer/gateway.
3. Theo dõi capacity và error tại standby, database, queue, DNS authoritative và monitoring.
4. Khi primary phục hồi, áp dụng **điều kiện failback** và xác nhận dữ liệu đồng bộ; tránh flapping.

### Pha E — Post-incident review

Lưu timeline: **T_failure, T_detect, T_decision, T_authoritative_change, T_resolver_observed, T_client_success**. Phân biệt nguyên nhân chính và các yếu tố kéo dài thời gian phục hồi; ghi nhận thay đổi bảo mật, IAM/audit và cập nhật runbook.

## 15. Chẩn đoán những lỗi thường gặp

| Triệu chứng | Giả thuyết | Hướng xác minh |
|---|---|---|
| Authoritative đã trả B nhưng một số client vẫn tới A | Recursive/app cache, TTL cũ, serve-stale, kết nối lâu dài | Hỏi đúng resolver client, kiểm tra cache và session |
| Một resolver trả A, resolver khác trả B | Cache được làm mới khác thời điểm hoặc policy theo vị trí | So sánh TTL còn lại, địa điểm, ECS nếu có và provider routing |
| A đã chuyển nhưng trình duyệt vẫn lỗi | AAAA còn trỏ A hoặc client ưu tiên IPv6 | Hỏi cả A/AAAA, kiểm tra dual-stack |
| `dig` thành công nhưng ứng dụng không chuyển | App DNS caching, pool kết nối, proxy resolve một lần | Kiểm tra runtime và connection reuse |
| Hostname dự phòng mới trả NXDOMAIN | Negative cache, zone sai hoặc record chưa tạo | SOA/negative TTL và authoritative consistency |
| DNS trả đúng B nhưng HTTPS lỗi chứng chỉ | SNI/Host/CA, certificate chưa được triển khai trên B | `curl --resolve` giữ hostname và xác thực TLS |
| DNSSEC validating resolver trả SERVFAIL | DS/DNSKEY/RRSIG không khớp, chữ ký hết hạn | Kiểm tra chain of trust, audit thay đổi |
| Failover liên tục qua lại | Health check thiếu hysteresis hoặc phụ thuộc bất ổn | Lịch sử probe, cooldown, readiness |
| B trả health 200 nhưng API lỗi | Health quá nông, dependency/replication chưa sẵn sàng | Synthetic transaction và DB/queue telemetry |
| Chỉ mạng VPN lỗi | Split DNS, route, ACL hoặc resolver nội bộ khác public | So sánh DNS view và đường ứng dụng |
| Chuyển NS nhưng DNS chưa ổn định | NS/delegation/glue/DS có TTL và quy trình riêng | Kiểm tra parent/child authoritative và DNSSEC |
| TTL đã giảm nhưng thời gian phục hồi vẫn lâu | Cache cũ, min TTL, app connection, serve-stale hoặc detection chậm | Timeline đa lớp thay vì chỉ TTL cấu hình |

### 15.1. Cách phân tách sự cố bằng hai câu hỏi

**Câu 1: DNS có trả đúng địa chỉ không?** Kiểm tra authoritative trước, rồi recursive resolver mà người dùng đang dùng. Nếu authoritative sai, xử lý policy/zone/health trước. Nếu authoritative đúng nhưng resolver khác, tập trung vào caching và DNS view.

**Câu 2: Địa chỉ đúng có phục vụ tốt không?** Dùng phép thử HTTPS đúng hostname/certificate, so sánh trực tiếp B với truy cập qua DNS thông thường. Nếu DNS đúng mà ứng dụng lỗi, tập trung vào standby readiness, firewall, dependency và TLS; không chỉ tiếp tục giảm TTL.

## 16. Case study: Website thương mại điện tử mất một vùng

### 16.1. Bối cảnh giả định

Một website có:

- `shop.example.test`, TTL A/AAAA đang đặt **300 giây**.
- Vùng A (`192.0.2.20`) hoạt động chính; vùng B (`198.51.100.20`) đã chuẩn bị dự phòng.
- Health check đo HTTPS readiness ở nhiều vị trí.
- Database replicate từ A sang B; bộ phận dữ liệu phải xác nhận điều kiện an toàn trước khi cho B nhận ghi.
- Một phần người dùng truy cập qua resolver của mạng doanh nghiệp và VPN có cache riêng.

Trong sự cố giả định, vùng A không phục vụ được API. Hệ thống health policy chuyển authoritative về vùng B sau khi đủ điều kiện.

### 16.2. Quan sát theo thời điểm minh họa

| Mốc (giả định) | Sự kiện | Ý nghĩa |
|---|---|---|
| 10:00:00 UTC | Vùng A bắt đầu lỗi | Bắt đầu tính thời gian tác động |
| 10:00:25 UTC | Health policy xác nhận lỗi | Độ trễ phát hiện 25 giây |
| 10:00:28 UTC | Authoritative trả địa chỉ B | DNS control plane đã đổi |
| 10:01:00 UTC | Một số resolver mới trả B | Nhóm client có thể khôi phục |
| 10:03:40 UTC | Nhiều resolver khác mới lấy B | Cache từ trước giữ A lâu hơn |
| 10:04:10 UTC | Một ứng dụng giữ connection cũ tới A | Tái phân giải chậm hơn trạng thái DNS |

**Không suy từ bảng rằng toàn bộ client phục hồi trước 10:04:10.** Đây là ví dụ có các nhóm client khác nhau; phải đo **tỷ lệ yêu cầu/giao dịch thành công theo thời gian** để xác nhận RTO thực tế. Một số resolver có thể còn trả dữ liệu cũ ngoài chuỗi mốc này do chính sách riêng.

### 16.3. Điều có thể cải thiện

1. Đặt TTL cho RRset cần failover dựa trên RTO và khả năng authoritative, chẳng hạn thử **60 giây trong lab** rồi đo tác động lên resolver và ứng dụng.
2. Kiểm chứng **client DNS cache/connection pool** và chính sách retry, không chỉ cấu hình DNS.
3. Bảo đảm A và AAAA cùng được xử lý đúng, cùng với alias/HTTPS record nếu dùng.
4. Giữ standby sẵn sàng và kiểm tra **database consistency, TLS, firewall, IdP, log, capacity**.
5. Dùng health checks đa vị trí, hysteresis và failback có kiểm soát.
6. Nếu SLO không chấp nhận thời gian chờ DNS cache, đánh giá **LB/VIP/anycast hoặc cơ chế service discovery/client failover** thích hợp.
7. Ghi timeline theo từng lớp và diễn tập định kỳ, thay vì chỉ báo “DNS đã chuyển xong”.

## 17. Các sai lầm phổ biến

| Ngộ nhận | Giải thích chính xác |
|---|---|
| “TTL = 60 nghĩa là failover hoàn tất trong 60 giây.” | TTL là tín hiệu cache, chưa bao gồm detection, policy, app cache, connection và standby readiness. |
| “Đổi A xong là mọi người dùng dùng IP mới.” | Resolver/client có thể giữ IP cũ đến khi làm mới. |
| “Cứ đặt TTL bằng 0 là tốt nhất.” | Tăng chi phí làm mới, phụ thuộc DNS và cache policy; chưa giải quyết connection reuse. |
| “Giảm TTL ngay lúc lỗi là có tác dụng tức thì.” | Resolver đã cache TTL cũ có thể chưa hỏi lại. |
| “Ping thành công chứng minh standby sẵn sàng.” | Phải kiểm tra TLS, ứng dụng và phụ thuộc dữ liệu. |
| “Đổi hostname dự phòng mới không cần chú ý negative cache.” | NXDOMAIN/NODATA cũng có thể được cache. |
| “Chỉ cần sửa IPv4.” | IPv6/AAAA có thể giữ client tới địa chỉ hỏng. |
| “CNAME chỉ có một TTL cho toàn bộ chuỗi.” | Mỗi RRset trên chuỗi có TTL của chính nó. |
| “DNSSEC bảo đảm primary/standby khỏe.” | DNSSEC xác thực dữ liệu DNS, không xác minh sức khỏe ứng dụng. |
| “Serve-stale luôn giúp failover nhanh hơn.” | Có thể tiếp tục trả địa chỉ cũ khi authoritative không thể làm mới. |
| “Failback ngay khi có một health check thành công.” | Có thể gây flapping và lỗi trạng thái dữ liệu. |
| “Weighted DNS cho chính xác 50/50 request.” | Resolver caching, phân bố client và DNS policy có thể làm sai khác tỷ lệ. |
| “Đổi NS là phương án nhanh để đổi IP khi gặp sự cố.” | Delegation, glue, DS và cache có cơ chế/TTL riêng. |
| “dig trả B là đủ xác nhận dịch vụ đã phục hồi.” | Cần kiểm tra HTTPS/API và người dùng ở nhiều mạng. |

## 18. Bài tập tự kiểm tra

### Bài 1 — TTL và cache

Resolver R đã cache `shop.example.test A=192.0.2.20` với TTL 300 giây. Sau 40 giây, authoritative đổi thành `198.51.100.20`. Trong điều kiện cache lý tưởng và không có prefetch/serve-stale, sau 60 giây kể từ lúc cache ban đầu, R có thể trả địa chỉ nào?

**Đáp án gợi ý:** R vẫn có thể trả `192.0.2.20`, với TTL còn khoảng **240 giây**. TTL được tính từ lúc cache, không từ thời điểm cập nhật authoritative.

### Bài 2 — TTL và RTO

Đội vận hành đặt TTL 30 giây và tuyên bố RTO chắc chắn là 30 giây. Liệt kê ít nhất bốn lý do kết luận sai.

**Đáp án gợi ý:** health check phát hiện chậm; policy switch/authoritative consistency; recursive resolver/app cache và serve-stale; connection pool không tái phân giải; standby chưa sẵn sàng; lỗi TLS/firewall/database.

### Bài 3 — Negative caching

Khi sự cố bắt đầu, đội vận hành tạo `backup.example.test` lần đầu rồi chuyển CNAME sang tên này. Một nhóm client vẫn thấy NXDOMAIN. Vì sao?

**Đáp án gợi ý:** resolver đã cache câu trả lời âm tính từ lúc hostname chưa tồn tại. TTL của CNAME hoặc A không tự kiểm soát negative cache; cần kiểm tra SOA và chính sách resolver.

### Bài 4 — Chuyển IPv4 nhưng quên IPv6

Sau failover, A trỏ B nhưng AAAA vẫn trỏ vùng A đã hỏng. Người dùng có IPv6 có thể gặp vấn đề gì?

**Đáp án gợi ý:** họ vẫn có thể kết nối tới địa chỉ IPv6 cũ hoặc thử luồng thất bại trước khi fallback; phải có chính sách và test cho **cả A/AAAA**, không suy tất cả client ưu tiên IPv4.

### Bài 5 — Serve-stale

Authoritative DNS tạm thời không truy cập được; một resolver bật serve-stale vẫn trả A cũ. Trường hợp nào có lợi và trường hợp nào bất lợi?

**Đáp án gợi ý:** có lợi nếu địa chỉ cũ vẫn khỏe và lỗi chỉ thuộc authoritative; bất lợi nếu đích cũ hỏng mà authoritative đã/đang cố chuyển đích, khiến client tiếp tục thử địa chỉ lỗi.

### Bài 6 — Health checks

Một health monitor duy nhất báo lỗi TCP/443 trong 10 giây nhưng nhiều người dùng vẫn vào web bình thường. Có nên failover ngay?

**Đáp án gợi ý:** chưa đủ thông tin. Kiểm tra các điểm đo độc lập, health ứng dụng, tuyến mạng của monitor và hysteresis; dùng policy đã duyệt để tránh failover giả và flapping.

### Bài 7 — DNSSEC

Sau khi chuyển DNS provider, một số validating resolver trả SERVFAIL trong khi hỏi thẳng authoritative thấy A đúng. Cần kiểm tra những gì?

**Đáp án gợi ý:** DS tại parent, DNSKEY, RRSIG, trạng thái ký của zone, chuỗi tin cậy và thời gian hiệu lực chữ ký; không chỉ hạ TTL hoặc tắt xác thực tùy tiện.

### Bài 8 — Đo thời gian phục hồi

Xây dựng kế hoạch diễn tập DNS failover cho API có RTO mục tiêu. Cần tối thiểu năm mốc thời gian và bốn nhóm bằng chứng nào?

**Đáp án gợi ý:** T_failure, T_detect, T_policy_switch, T_authoritative_new, T_resolver_new, T_client_success; health logs, authoritative answers, recursive observations, app/TLS/transaction results, capacity và audit thay đổi DNS.

## 19. Checklist triển khai và vận hành

- Đã nêu rõ **RTO/RPO**, những nhóm người dùng và giao dịch cần bảo vệ.
- Đã lập sơ đồ **client → cache → resolver → authoritative → LB/origin → dependency**.
- Hiểu TTL của **RRset A, AAAA, CNAME/alias, negative cache, NS/delegation** khi có liên quan.
- Biết resolver/runtime có **min/max TTL, prefetch, serve-stale, cache riêng và persistent connection** hay không.
- Standby đã được kiểm tra **HTTPS/TLS, dữ liệu, IAM, firewall, DNS nội bộ, sức chứa và log**.
- Health checker có **nhiều điểm đo, điều kiện readiness, ngưỡng lỗi, cooldown và failback** rõ ràng.
- Cả **IPv4/IPv6** và public/private/VPN DNS views đều nằm trong ma trận kiểm thử.
- Có **DNSSEC validation**, quyền thay đổi DNS tối thiểu, MFA, audit và cảnh báo.
- Có phép thử **authoritative, recursive và client application**, ghi thời điểm UTC theo nhóm người dùng.
- Đã kiểm chứng không có **đường bypass security controls** khi chuyển traffic tới standby.
- Có **runbook ứng cứu, người chịu trách nhiệm, rollback và post-incident review**.
- Không coi **TTL thấp** là lời hứa về thời gian khôi phục; đo **tỷ lệ giao dịch thành công và phân bố thời gian phục hồi thực tế**.

**Kết luận:** TTL là một nút điều chỉnh quan trọng cho khả năng thay đổi câu trả lời DNS, nhưng **không phải công tắc chuyển tất cả người dùng tức thì**. DNS failover đáng tin cậy chỉ xuất hiện khi **sức khỏe dịch vụ được xác minh, vùng dự phòng thật sự sẵn sàng, các lớp cache và kết nối được hiểu đúng, các biện pháp bảo mật DNS vẫn nguyên vẹn, và hiệu quả được đo từ góc nhìn người dùng**.

### Tài liệu tham khảo

- [RFC 1034 — Domain Names: Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034): kiến trúc DNS, phân giải và caching.
- [RFC 1035 — Domain Names: Implementation and Specification](https://www.rfc-editor.org/rfc/rfc1035): cấu trúc resource record và TTL.
- [RFC 2181 — Clarifications to the DNS Specification](https://www.rfc-editor.org/rfc/rfc2181): quy tắc RRset và TTL.
- [RFC 2308 — Negative Caching of DNS Queries](https://www.rfc-editor.org/rfc/rfc2308): negative caching với NXDOMAIN/NODATA.
- [RFC 8767 — Serving Stale Data to Improve DNS Resiliency](https://www.rfc-editor.org/rfc/rfc8767): serve-stale và ảnh hưởng tới dữ liệu trong cache.
- [RFC 4033 — DNS Security Introduction and Requirements](https://www.rfc-editor.org/rfc/rfc4033): mô hình xác thực của DNSSEC.
- [RFC 4035 — Protocol Modifications for the DNS Security Extensions](https://www.rfc-editor.org/rfc/rfc4035): xác thực và xử lý dữ liệu DNSSEC.
- [NIST SP 800-81-2 — Secure Domain Name System (DNS) Deployment Guide](https://csrc.nist.gov/pubs/sp/800/81/2/final): nguyên tắc triển khai và bảo vệ DNS.
