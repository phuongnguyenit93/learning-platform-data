# Cloud DNS routing policies và điều hướng lưu lượng

> **Chương:** Cân bằng tải và phân phối nội dung  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Khi triển khai ứng dụng trên nhiều vùng của Google Cloud, người dùng thường truy cập qua một tên miền duy nhất, chẳng hạn `api.example.com`. Nhưng cùng một tên miền có thể dẫn tới nhiều endpoint: một endpoint chính ở Singapore, một endpoint tại Tokyo, hoặc phiên bản mới chỉ nhận một phần nhỏ truy vấn DNS. **Cloud DNS routing policies** giúp quyết định tập bản ghi DNS trả về theo trọng số, vị trí địa lý nguồn truy vấn hoặc trạng thái primary/backup.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu tổ chức project, IAM và VPC, lựa chọn Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài học thuộc chương **Cân bằng tải và phân phối nội dung**, giải thích cách Cloud DNS phối hợp với Cloud Load Balancing, Cloud CDN, Cloud Monitoring và các kết nối hybrid để hướng người dùng tới dịch vụ phù hợp.

**Sau bài học, bạn có thể:**

1. Phân biệt DNS-based traffic steering với cân bằng tải HTTP(S)/TCP ở tầng kết nối.
2. Chọn giữa **Weighted Round Robin (WRR)**, **Geolocation (GEO)**, **GEO với geofence** và **Failover**.
3. Giải thích vì sao TTL, recursive resolver và EDNS Client Subnet khiến tỷ lệ người dùng thực tế có thể khác tỷ lệ cấu hình.
4. Cấu hình record set và health checking phù hợp loại zone/endpoint.
5. Sử dụng Google Cloud Console và các lệnh `gcloud dns` để kiểm tra, thực hành và xử lý lỗi.
6. Thiết kế đường đi và kịch bản sự cố có tính đến IAM, tải backend, DNS cache, độ tin cậy và chi phí.

## 1. DNS định hướng lưu lượng như thế nào?

**DNS (Domain Name System)** chuyển một tên như `api.example.com` thành dữ liệu mà client sử dụng, phổ biến là địa chỉ IP trong bản ghi **A** hoặc **AAAA**. Trong mô hình cơ bản, một RRset (resource record set) có thể chứa một hoặc nhiều địa chỉ với cùng tên và loại.

Với **Cloud DNS routing policy**, một RRset có thể có các **policy items**. Thay vì luôn trả cùng một tập địa chỉ, Cloud DNS chọn câu trả lời theo chính sách tương ứng và thông tin có thể quan sát ở thời điểm truy vấn.

~~~mermaid
flowchart LR
    U["Trình duyệt / ứng dụng"] --> RES["Recursive DNS resolver"]
    RES --> AUTH["Cloud DNS authoritative zone"]
    AUTH --> POL{"Routing policy của RRset"}
    POL --> A["Trả A: 203.0.113.10"]
    POL --> B["Trả A: 198.51.100.20"]
    A -. "Sau khi phân giải" .-> LB1["Endpoint / Load balancer A"]
    B -. "Sau khi phân giải" .-> LB2["Endpoint / Load balancer B"]
~~~

*Các IP thuộc dải địa chỉ dùng cho tài liệu minh họa, không phải endpoint thực tế.*

**Luồng xử lý:**

1. Ứng dụng yêu cầu phân giải tên miền.
2. Resolver kiểm tra bộ nhớ đệm; nếu còn bản ghi hợp lệ, có thể trả lời **không cần hỏi Cloud DNS lại**.
3. Khi cần truy vấn authoritative server, Cloud DNS xét chính sách của RRset tương ứng.
4. Cloud DNS trả lại bản ghi IP/tên phù hợp; resolver và client có thể cache theo TTL.
5. **Client tự mở kết nối** đến một địa chỉ đã nhận. Từ đó routing VPC, Cloud Load Balancing, firewall và ứng dụng quyết định khả năng phục vụ.

**Cần phân biệt:** Cloud DNS quyết định **câu trả lời DNS**; nó không đứng giữa mọi request HTTP, không proxy TCP session và không điều khiển từng gói tin sau khi client đã kết nối. Khi một endpoint gặp lỗi, DNS policy có thể thay câu trả lời cho các lượt tra cứu tiếp theo, nhưng không tự chuyển một phiên TCP đã thiết lập sang endpoint khác.

### 1.1. Cloud DNS và Cloud Load Balancing phục vụ hai tầng khác nhau

| Tiêu chí | Cloud DNS routing policies | Cloud Load Balancing |
| --- | --- | --- |
| Đơn vị quyết định | Trả về RRset theo **truy vấn DNS** | Phân phối **kết nối/request** theo cấu hình load balancer |
| Tín hiệu định hướng | Trọng số, vùng nguồn DNS, tình trạng health endpoint được hỗ trợ | Kiểu LB, backend service, health checks, URL map, traffic policies... |
| Nhìn thấy HTTP path, host header? | Không dựa vào path HTTP để chọn đáp án A/AAAA | Application Load Balancer hỗ trợ định tuyến tầng HTTP(S) |
| Tính chính xác tỷ lệ | Bị ảnh hưởng bởi recursive DNS caching và hành vi client | Có thể điều khiển trực tiếp hơn tại lớp request/kết nối theo tính năng LB |
| Failover | Khi resolver hỏi lại và health signals cập nhật | Xử lý giữa các backend theo cơ chế LB |
| Kết hợp CDN | DNS có thể hướng tới IP hostname của LB/CDN | Cloud CDN thường dùng cùng External Application Load Balancer |
| Phù hợp | Chia nhiều endpoint/region/provider; active-backup ở tầng DNS | Phân phối vào backend của một hoặc nhiều service |

Ví dụ website tĩnh toàn cầu dùng **External Application Load Balancer + Cloud CDN** có thể chỉ cần một global frontend IP và một tên DNS A tĩnh. Không phải ứng dụng nhiều vùng nào cũng cần GEO policy. Cân nhắc DNS steering khi có **nhiều địa chỉ frontend khác nhau** hoặc yêu cầu điều hướng theo vùng/tỷ trọng ở lớp DNS.

### 1.2. Ba khái niệm chính xác cần nhớ

- **Managed zone:** nơi Cloud DNS quản lý dữ liệu một miền, có thể là **public** hoặc **private**.
- **Resource record set (RRset):** tập bản ghi cùng tên, loại và TTL, ví dụ `api.example.com. A`.
- **Routing policy:** một cấu hình **gắn với RRset**, không phải một quy tắc áp dụng tự động cho mọi bản ghi trong zone.

Cloud DNS còn có **server policies** (chuyển tiếp/hybrid DNS, logging) và **response policies** (ghi đè đáp án theo điều kiện tên truy vấn). Hai nhóm này **khác** DNS routing policies. Có thể phối hợp chúng theo phạm vi hỗ trợ, nhưng không nên hiểu “policy” nào cũng xử lý chia lưu lượng.

## 2. Chọn chính sách theo mục tiêu

Cloud DNS hỗ trợ ba nhóm routing policies chính: **WRR**, **GEO** và **FAILOVER**. GEO có tùy chọn **geofence**.

| Chính sách | Tín hiệu lựa chọn | Tình huống điển hình | Điều phải chú ý |
| --- | --- | --- | --- |
| **Weighted Round Robin (WRR)** | Trọng số giữa các policy items | Phân phối lưu lượng sang hai frontend, rollout theo tỷ lệ | Tỷ lệ dựa **truy vấn DNS**, không bảo đảm tỷ lệ request |
| **Geolocation (GEO)** | Vị trí nguồn của truy vấn khi vào hệ thống DNS | Đưa người dùng gần một vùng triển khai | Có thể dùng địa chỉ resolver/ECS; không phải vị trí GPS người dùng |
| **GEO với geofence** | GEO nhưng giữ câu trả lời trong ranh giới geolocation | Yêu cầu ràng buộc vùng phục vụ | Khi endpoint vùng đó lỗi, DNS vẫn có thể trả địa chỉ không khỏe |
| **Failover** | Primary/backup cùng health signals | VPC internal service active-backup | Chuyển khi **toàn bộ primary** bị xem là unhealthy, vẫn chịu DNS cache |

**Quy tắc phối hợp:** Một RRset chỉ dùng **một loại routing policy**. Không kết hợp WRR và GEO thành hai lớp tùy ý trên cùng RRset. Ngoại lệ được hỗ trợ là **FAILOVER có backup theo GEO**.

### 2.1. Chọn bằng tình huống

- “Muốn chuyển 10% truy vấn sang frontend mới trong lab” → **WRR**.
- “Muốn truy vấn DNS từ Singapore nhận frontend châu Á, từ Mỹ nhận frontend Mỹ” → **GEO**.
- “Khách hàng phải nhận câu trả lời của khu vực đã chỉ định dù vùng gặp lỗi” → **GEO + geofence**, nhưng cần chấp nhận rủi ro không phục vụ.
- “Muốn nội bộ dùng VIP A, chỉ khi A không khỏe mới trả VIP B” → **FAILOVER**.
- “Muốn định tuyến HTTP `/api/*` sang một dịch vụ và `/static/*` sang dịch vụ khác” → **Application Load Balancer URL map**, không phải DNS policy.
- “Muốn lưu file gần người dùng và giảm thời gian lấy nội dung cacheable” → Khảo sát **Cloud CDN** với load balancer, có thể không cần GEO RRset.

## 3. Weighted Round Robin (WRR)

WRR cho phép gán **weight** cho từng policy item. Cloud DNS phân phối câu trả lời tương ứng theo tỷ lệ trọng số giữa các mục có giá trị phù hợp.

Ví dụ:

| Policy item | DNS target | Weight | Tỷ lệ kỳ vọng qua nhiều lượt truy vấn độc lập |
| --- | --- | ---: | ---: |
| Stable frontend | `203.0.113.10` | 90 | Khoảng 90% |
| Candidate frontend | `198.51.100.20` | 10 | Khoảng 10% |

Cách tính tỷ trọng:

\[
P(\text{item }i) = \frac{w_i}{\sum_j w_j}
\]

Nếu trọng số là 9 và 1, tỷ lệ cũng là 90:10. Theo tài liệu, weight có thể bằng **0**; khi toàn bộ item cùng weight 0, Cloud DNS phân phối đều. Một item weight 0 có thể có vai trò dự phòng trong một số cấu hình health checks, vì vậy **không coi giá trị 0 là quy tắc tuyệt đối “vĩnh viễn không trả đáp án”**.

### 3.1. Vì sao 90:10 không tương đương 90:10 HTTP requests?

Một resolver có thể cache đáp án trong `TTL=60` giây, sau đó trả cùng câu trả lời cho hàng ngàn client trong cùng mạng. Một client có thể tạo 100 request HTTP sau **một lượt DNS lookup**. Ngược lại, các DNS resolvers khác nhau có tốc độ truy vấn khác nhau.

Ví dụ giả định:

~~~text
DNS authoritative queries trong 1 phút:
  Resolver A -> Stable  (5.000 request HTTP từ người dùng của A)
  Resolver B -> Candidate (80 request HTTP từ người dùng của B)
  Resolver C -> Stable  (10 request HTTP)

Tỷ lệ query sample: Stable 2/3, Candidate 1/3
Tỷ lệ request HTTP thực: khác hoàn toàn
~~~

Vì vậy, với rollout cần **chính xác** 10% user/session/request, khả năng traffic splitting của Cloud Run hoặc load balancer/application layer phù hợp hơn. DNS WRR có thể dùng để **dịch chuyển dần theo mức xấp xỉ** hoặc hướng nhiều endpoint độc lập.

### 3.2. WRR và health checks

Khi policy items có endpoint được hỗ trợ để kiểm tra sức khỏe, Cloud DNS có thể loại endpoint unhealthy khỏi kết quả và phân bổ lại trên các endpoint khỏe. Nhưng cần xác định:

- Health checking chỉ xảy ra nếu **đã bật và cấu hình đúng** với loại endpoint hỗ trợ.
- A record trỏ tới một IP bất kỳ **không tự có health check**.
- Các trường hợp weight 0 và item có/không health check có quy tắc fallback đặc biệt.
- **Nếu mọi endpoint đều unhealthy**, Cloud DNS vẫn có thể trả các endpoint như thể chúng healthy để không trả đáp án rỗng; đây không phải bảo đảm ứng dụng tiếp tục hoạt động.

### 3.3. Dùng WRR như công cụ canary: đánh giá rủi ro

Trước khi chuyển từ 100:0 sang 90:10:

1. Hai frontend có cùng contract API/behavior và đều phục vụ HTTPS/TLS đúng tên miền không?
2. Client có thể cache DNS lâu hơn TTL dự kiến không?
3. Session/state có được chia sẻ hay giữ nhất quán khi người dùng đổi endpoint?
4. Có metric lỗi, latency, request count **theo từng endpoint** không?
5. Có kế hoạch rollback khi endpoint candidate lỗi, và metric bao lâu mới phản ánh thay đổi?
6. Nếu truy vấn DNS đều đi từ một recursive resolver, liệu sample còn đại diện cho người dùng thực tế?

## 4. Geolocation routing policy (GEO)

GEO định nghĩa **source geography** và câu trả lời DNS theo geography đó. Trong Cloud DNS, các geography được gắn với **Google Cloud regions** có hỗ trợ. Khi không có rule khớp chính xác source region, Cloud DNS chọn geography phù hợp gần nhất theo thuật toán của dịch vụ.

Ví dụ cấu hình ý tưởng:

| Nguồn truy vấn được Cloud DNS xác định | Policy item | Kết quả |
| --- | --- | --- |
| Nguồn tương ứng `asia-southeast1` | Singapore | `203.0.113.10` |
| Nguồn tương ứng `us-central1` | US Central | `198.51.100.20` |
| Nguồn ở region không được khai báo | Gần location được cấu hình hơn | Một IP thuộc geography được chọn |

**GEO không đảm bảo vùng được chọn thực sự gần nhất với thiết bị của người dùng.** Nó dựa trên cách truy vấn DNS đến Google Cloud và thông tin địa lý được nhìn thấy.

### 4.1. Public DNS: nguồn là gì?

Đối với public zone, nguồn có thể được xác định từ:

- IP address của recursive resolver gửi truy vấn đến authoritative Cloud DNS; hoặc
- **EDNS Client Subnet (ECS)** nếu resolver đưa thông tin subnet client trong truy vấn.

Nếu người dùng Việt Nam sử dụng resolver ở châu Âu mà không chuyển ECS, Cloud DNS có thể suy nguồn theo resolver ở châu Âu. Do đó **không dựa vào GEO DNS như bằng chứng xác định quốc gia thực tế của người dùng** hay làm cơ chế duy nhất thực thi yêu cầu pháp lý lưu trú dữ liệu.

### 4.2. Private DNS: nguồn là region của hệ thống gửi truy vấn

Ở private zone, Cloud DNS **không dùng ECS** cho GEO:

- DNS query từ **Compute Engine VM** nằm trong VPC có source geography theo **region chứa VM**.
- DNS query gửi vào **inbound server policy** từ on-premises có source geography theo region của **Cloud VPN tunnel**, **Cloud Interconnect VLAN attachment** hoặc **Router appliance** nhận gói truy vấn.

Một truy vấn từ trung tâm dữ liệu ở Hà Nội đi qua tunnel đặt trong region khác có thể được xử lý theo **region của tunnel**, không theo vị trí vật lý của trung tâm dữ liệu. Khi triển khai hybrid DNS, cần ghi rõ đường vào và region ingress để giải thích kết quả.

### 4.3. GEO và health check: cách chuyển sang vùng kế tiếp

Nếu GEO có health checking và endpoint trong vùng được chọn không còn khỏe, khi **geofencing tắt**, Cloud DNS có thể trả endpoint ở **geography gần nhất kế tiếp**. Chính sách chỉ đổi DNS response ở lượt truy vấn tiếp theo; resolver vẫn có thể giữ địa chỉ cũ theo TTL.

~~~mermaid
flowchart TD
   Q["Truy vấn DNS nguồn châu Á"] --> GEO["GEO chọn Singapore"]
   GEO --> HC{"Target Singapore khỏe?"}
   HC -- "Có" --> SG["Trả VIP Singapore"]
   HC -- "Không, geofence OFF" --> ALT["Xét geography khỏe gần nhất"]
   ALT --> TK["Trả VIP region khác phù hợp"]
   HC -- "Không, geofence ON" --> STAY["Vẫn trả địa chỉ vùng được chọn"]
~~~

### 4.4. GEO với geofence

**Geofence** hạn chế tự động chuyển sang geography khác. Khi **geofence bật** và **toàn bộ endpoint vùng đích unhealthy**, Cloud DNS vẫn phải trả câu trả lời authoritative và có thể trả địa chỉ của vùng đó ngay cả khi chúng unhealthy.

Do vậy GEO + geofence là **ưu tiên vùng phục vụ**, không phải công tắc bảo đảm an toàn dữ liệu. Nếu workload thực tế bị lỗi và vẫn trỏ về vùng đó, người dùng sẽ thấy lỗi. Yêu cầu residency nghiêm ngặt còn cần kiểm soát nơi lưu dữ liệu, routing ứng dụng, IAM, network và policy độc lập với DNS.

### 4.5. Một geography có nhiều địa chỉ

Cloud DNS cho phép cấu hình nhiều IP ở một policy item GEO. Nếu policy trả tập này, resolver/client có thể nhận **nhiều địa chỉ** và lựa chọn theo hành vi riêng. Không coi đây là weighted 50:50 do client có thể ưu tiên một địa chỉ, giữ kết nối cũ hoặc cache record.

## 5. Failover routing policy

**Failover** phù hợp cấu hình **active-backup** cho **tài nguyên nội bộ VPC**. Một RRset khai báo primary VIPs và tập backup. Khi còn ít nhất một primary VIP khỏe, Cloud DNS phục vụ các primary VIP khỏe. Khi **tất cả primary VIP** được đánh giá unhealthy, dịch vụ chuyển sang backup.

Backup được cấu hình dưới dạng **GEO** theo khả năng hỗ trợ, cho phép chọn endpoint backup dựa trên region. Có thể bật **trickle traffic** để đưa một phần truy vấn sang backup khi primary vẫn khỏe nhằm đánh giá backup sẵn sàng.

~~~mermaid
flowchart TD
    Q["Client trong VPC phân giải db-api.internal.example."] --> DNS["Cloud DNS private zone"]
    DNS --> C{"Còn primary VIP khỏe?"}
    C -- "Có" --> PRI["Trả primary VIP(s)"]
    C -- "Không" --> BAK["Trả backup theo GEO"]
    PRI -. "Trickle tùy chọn" .-> BAK
    BAK --> LB["Backup internal load balancer"]
~~~

### 5.1. Trickle ratio

Trickle traffic được cấu hình như một **tỷ lệ 0–1**. Ví dụ:

| Trickle ratio | Ý nghĩa sơ bộ |
| ---: | --- |
| `0` | Không cố ý đưa truy vấn đến backup khi primary khỏe |
| `0.05` | Khoảng 5% lượt quyết định DNS đến backup |
| `0.1` | Khoảng 10% lượt quyết định DNS đến backup |
| `1` | Có thể dùng để hướng 100% truy vấn sang backup thủ công |

**Không biến trickle thành cam kết phân phối 5% request HTTP.** Recursive resolver cache và TTL khiến số request thực tế có thể chênh lệch. Với dịch vụ có session state, backup phải sẵn sàng xử lý dữ liệu/kết nối ngay cả khi chỉ nhận trickle traffic nhỏ.

### 5.2. Failover DNS khác disaster recovery hoàn chỉnh

Đưa DNS sang backup chỉ giải quyết việc **khách hàng mới phân giải thấy endpoint khác**. Một kế hoạch DR cần thêm:

- Dữ liệu ở backup đồng bộ như thế nào? RPO chấp nhận được là bao nhiêu?
- Database có thể nhận ghi hay vẫn ở chế độ standby?
- Backend backup có đủ năng lực xử lý 100% tải không?
- Token, secret, IAM, TLS certificate và dependencies có sẵn ở backup?
- Client đang giữ kết nối đến primary sẽ retry thế nào?
- Người dùng sau TTL có thể vẫn nhận IP cũ không?
- Sau khi primary hồi phục, có cần **failback thủ công** và giám sát lỗi không?

Mục tiêu RTO không thể suy trực tiếp chỉ từ TTL. Thời gian failover thực tế phụ thuộc health checking, DNS caching, hành vi client, kết nối mới và khả năng sẵn sàng của backup.

## 6. Health checks trong Cloud DNS routing policies

Có thể kết hợp WRR/GEO/Failover với **health signals** của những endpoint được hỗ trợ. Hai nhánh quan trọng là **internal load balancer** và **external endpoints**.

| Đặc điểm | Internal load balancer | External endpoint |
| --- | --- | --- |
| Zone sử dụng health checking | **Private zone** | **Public zone** |
| Endpoint | Internal Application LB, internal passthrough NLB, cross-region internal ALB; internal proxy NLB theo trạng thái tính năng | Public IP/port có thể truy cập từ Internet, gồm LB hoặc máy chủ ngoài GCP |
| Cách đánh giá | Dựa trên health signal của load balancer/backends tùy loại LB | Cloud DNS gửi probe TCP/HTTP/HTTPS từ các region được chỉ định |
| Bật bằng cách nào | Tham chiếu **forwarding rule**, không chỉ gõ VIP | Khai báo endpoint và health check tương ứng |
| Hạn chế | Global access của regional LB, IAM và cấu hình LB | Firewall, nguồn probe, port, HTTP status/content, interval |

### 6.1. Internal load balancers

Những loại được tài liệu Google Cloud nêu gồm:

- Regional **internal Application Load Balancer**.
- Cross-region **internal Application Load Balancer**.
- **Internal passthrough Network Load Balancer**.
- **Internal proxy Network Load Balancer** (kiểm tra trạng thái Preview/hỗ trợ tại thời điểm dùng).

Đối với internal Application/Proxy Load Balancer, DNS đánh giá tình trạng **load balancer endpoint**, còn load balancer chịu trách nhiệm phân phối vào backend khỏe. Đối với **internal passthrough NLB**, Cloud DNS sử dụng thông tin health của các backend instances để đánh giá endpoint; tài liệu nêu ngưỡng mặc định **20% backend khỏe**. Một passthrough NLB không có backend nào có thể vẫn bị Cloud DNS coi là “khỏe”, vì vậy **phải cấu hình ít nhất một backend** nếu muốn health checking phản ánh thực tế.

Khi sử dụng regional internal LB với Cloud DNS health checks, Google yêu cầu **global access** theo hướng dẫn cho LB loại đó. Cần đọc phạm vi kết nối và hỗ trợ của LB cụ thể trước khi bật.

**Đặc biệt quan trọng:** Trên CLI, khi bật health checking cho internal LB, phải cung cấp **tham chiếu forwarding rule**, không chỉ địa chỉ IP. Một A record IP bình thường được phân phối theo WRR/GEO nhưng không tự có health checks của LB.

### 6.2. External endpoints

Cloud DNS hỗ trợ health checking cho **external IP endpoints** trong **public zones**. Endpoint phải có thể truy cập qua Internet từ các health check probes. Tài liệu hiện hành nêu:

- Health checking TCP, HTTP hoặc HTTPS, với giới hạn thuộc tính tùy giao thức.
- HTTP/HTTPS cần phản hồi **HTTP 200** theo điều kiện kiểm tra; có thể cấu hình kiểm tra nội dung phản hồi.
- Health check interval cho external endpoint từ **30 đến 300 giây**.
- Cấu hình **ba Google Cloud source regions**; trong mỗi region có **ba prober**, tổng cộng chín prober cho endpoint theo thiết kế được mô tả.
- **Source IP ranges không cố định** như một số loại Google Cloud load balancer health checks; phải đọc hướng dẫn firewall dành cho Cloud DNS external health checks.

Điều này khác với Cloud Load Balancing backend health checks. Nếu chỉ copy allowlist IP của LB health checks sang firewall của endpoint ngoài, probes DNS có thể bị chặn và endpoint bị đánh dấu unhealthy.

Không nên nới firewall một cách tùy tiện trên production; hãy phối hợp với nhóm bảo mật về cổng kiểm tra và cách cho phép probe theo yêu cầu thực tế.

### 6.3. Khi tất cả endpoints không khỏe

Một giả định thường sai là “Cloud DNS sẽ trả NXDOMAIN hoặc một lỗi DNS nếu tất cả endpoint unhealthy”. Theo hành vi được mô tả, **khi tất cả policy buckets unhealthy, Cloud DNS có thể coi như tất cả endpoint healthy và trả địa chỉ**. Vì vậy client vẫn có thể kết nối vào dịch vụ lỗi.

**DNS health check không tạo backend mới, không phục hồi database và không bảo đảm tránh hoàn toàn endpoint hỏng.** Cần alerting, khả năng phục hồi và thử nghiệm với những tình huống toàn bộ endpoint mất sức khỏe.

### 6.4. Điều kiện DNSSEC và loại bản ghi

Cloud DNS routing policies hỗ trợ **A, AAAA, CNAME, MX, SRV, TXT** theo các giới hạn cụ thể.

- **A:** health check được hỗ trợ cho internal load balancer trong private zone và external endpoint trong public zone.
- **AAAA:** external endpoint health checks được hỗ trợ theo tài liệu; không giả định internal LB IPv6 health checks có cùng tính năng.
- **CNAME, MX, SRV, TXT:** có thể được dùng trong routing policy nhưng **không hỗ trợ health checks**.
- Khi **DNSSEC** bật trong managed zone, cấu hình health checking có hạn chế, chẳng hạn một IP trong mỗi policy item WRR/GEO; kiểm tra yêu cầu trước khi chuyển zone hoặc cập nhật record.
- Một policy item không phải lúc nào cũng được trộn địa chỉ có health check và không health check tùy tình huống; cần đọc phần caveat của loại policy và DNSSEC cụ thể.

**Không dùng CNAME health check** hoặc viết sơ đồ “Cloud DNS tự ping mọi bản ghi” khi loại bản ghi/endpoint không được hỗ trợ.

## 7. TTL, caching và độ trễ đổi tuyến

**TTL (Time to Live)** trong RRset là số giây mà recursive resolver có thể lưu câu trả lời. Ví dụ TTL 30 giây là chỉ dẫn thời hạn cache, **không bảo đảm mọi trình duyệt, hệ điều hành, proxy và recursive resolver sẽ hỏi lại chính xác sau 30 giây**.

### 7.1. Vì sao DNS failover không tức thì?

~~~mermaid
sequenceDiagram
   participant U as Client
   participant R as Recursive resolver
   participant D as Cloud DNS
   participant A as Endpoint A
   participant B as Endpoint B

   U->>R: Resolve api.example.com
   R->>D: DNS query
   D-->>R: A = Endpoint A, TTL 60s
   R-->>U: Endpoint A
   U->>A: HTTPS request
   Note over A: A bị lỗi sau đó
   U->>R: Resolve lại khi vẫn còn cache
   R-->>U: Endpoint A từ cache
   Note over D: Health checking phát hiện lỗi
   R->>D: Hỏi lại sau khi cache hết hạn
   D-->>R: Endpoint B
   R-->>U: Endpoint B
   U->>B: Request mới
~~~

Thời gian dịch chuyển chịu ảnh hưởng của ít nhất bốn thành phần: health-check interval/phát hiện lỗi, TTL/cache, client retry và sự sẵn sàng của endpoint backup. **Giảm TTL không giải quyết tất cả**: TTL thấp có thể tăng lượng truy vấn DNS, chi phí, tải resolver và vẫn không sửa được client kết nối lâu.

### 7.2. Chọn TTL theo nhu cầu

| Tình huống | Cách tiếp cận |
| --- | --- |
| DNS record tĩnh hiếm đổi | TTL vừa/cao để giảm nhu cầu truy vấn lặp |
| Canary theo WRR | TTL vừa đủ ngắn để quan sát dịch chuyển, đo traffic thực tế |
| Failover cần phản ứng nhanh | Cân nhắc TTL thấp hơn, nhưng kiểm thử cùng health checks và client retry |
| Truy vấn từ resolver tập trung của doanh nghiệp | Kiểm tra caching behavior thực tế và resolver override |
| Tên miền public có lượng truy vấn lớn | So tác động chi phí query, cache hiệu quả và mong muốn điều hướng |

**Khi chạy A/B test:** Số lượt DNS queries của mỗi policy item không đồng nghĩa số phiên người dùng hoặc HTTP requests. Phải đo ở tầng ứng dụng theo frontend, user cohort hoặc session khi cần tỷ lệ chính xác.

## 8. Phạm vi hỗ trợ và những cấu hình không phù hợp

Routing policies **không cấu hình được** trên một số loại private managed zones, gồm:

- **Forwarding zones**.
- **DNS peering zones**.
- **Managed reverse lookup zones**.
- **Service Directory zones**.

Nếu vừa cần phân giải tên on-premises vừa muốn định hướng endpoint theo WRR/GEO, cần thiết kế zone/record set phù hợp. Không thể cho rằng chỉ việc tạo một forwarding zone đến DNS on-premises rồi thêm WRR record set vào đó là hợp lệ.

Một RRset không được tự do kết hợp WRR+GEO, và sau khi đã chọn **routing policy type**, việc đổi sang loại khác có thể phải **xóa và tạo lại** record set theo quy trình phù hợp. Thay record có thể gây tác động rộng, đặc biệt với tên public và cache.

### 8.1. Public và private zones

| Yếu tố | Public zone | Private zone |
| --- | --- | --- |
| Ai phân giải? | Tên được công bố qua hệ thống authoritative DNS công khai khi delegation đúng | Các VPC được zone cho phép và những nguồn hybrid có đường phân giải phù hợp |
| GEO location | Resolver IP hoặc ECS | VM/source region hoặc ingress hybrid phù hợp |
| Health check được hỗ trợ | External IP endpoints | Internal load balancer endpoints |
| Địa chỉ thường trả | Public addresses của frontend/CDN/LB | Internal VIP/private addresses |
| Tình huống | API nhiều vùng/nhà cung cấp, đa CDN, rollout public | Ứng dụng nội bộ, service discovery, active-backup nhiều vùng |

Không xuất bản private VIP lên public zone như một giải pháp tạo kết nối; DNS public trả địa chỉ nội bộ **không làm private IP có thể truy cập từ Internet**. Ngược lại, private zone được gắn với VPC phù hợp không tự hiển thị cho mọi client của Internet.

### 8.2. CDN: DNS steering không thay chức năng caching

Nếu mục tiêu là phân phối ảnh, CSS, JavaScript hoặc tệp tĩnh đến người dùng toàn cầu:

- **Cloud CDN** có cache tại edge và hỗ trợ với load balancer phù hợp; giảm RTT và tải origin.
- **Cloud DNS** chỉ trả lời hostname/endpoint, không giữ/cấp phát nội dung.
- GEO record có thể hướng người dùng tới CDN provider hoặc frontend theo vùng, nhưng hiệu quả phải đo theo cache hit ratio, latency, error rate và chi phí egress.
- Không tự định tuyến người dùng theo GEO để thay thế hệ thống CDN khi một global load balancer + CDN đã giải quyết tốt bài toán.

## 9. Kiến trúc tham chiếu: API public ở hai vùng

**Bối cảnh:** Một ứng dụng thương mại điện tử có frontend API ở Singapore và Tokyo; sử dụng Cloud Run hoặc GKE phía sau các **regional external Application Load Balancers** phù hợp. Tên truy cập là `api.example.com`. Mục tiêu là hướng phần lớn người dùng châu Á đến endpoint mong muốn, có khả năng chuyển vùng khi gặp lỗi.

~~~mermaid
flowchart TD
  CLIENT["Người dùng / Resolver"] --> DNS["Public Cloud DNS zone example.com"]
  DNS --> GEO{"GEO policy: api.example.com A"}
  GEO --> SG["Regional external ALB - Singapore"]
  GEO --> JP["Regional external ALB - Tokyo"]
  SG --> APISG["API service Singapore"]
  JP --> APIJP["API service Tokyo"]
  SG -. "Health signal khi đã cấu hình" .-> H["Cloud DNS external endpoint health checks"]
  JP -. "Health signal khi đã cấu hình" .-> H
~~~

**Phương án GEO:** Khai báo policy item cho source region phù hợp, với hai public IP của frontend. Nếu có health checks cho external endpoints và **không bật geofence**, Cloud DNS có thể chuyển câu trả lời sang geography khỏe khác khi endpoint vùng gần nhất lỗi.

**Những điều phải kiểm tra ngoài DNS:**

1. Nếu một request đang chạy khi Singapore lỗi, client retry thế nào?
2. Hai vùng có truy cập database cùng schema/đúng quyền không? Có consistency/cross-region latency?
3. TLS certificate trên cả frontend có hợp lệ với `api.example.com`?
4. Nếu dùng session cookie, token hoặc idempotency key, hai vùng có tương thích không?
5. Nếu một vùng nhận 100% tải trong sự cố, có đủ quota, autoscaling và database connections không?
6. Đường network và firewall đến backend có cho phép các health probes tương ứng không?
7. Dữ liệu người dùng có được phép xử lý ở Tokyo theo quy định? Nếu không, GEO failover tự do có thể vi phạm chính sách.

### 9.1. Khi nào WRR tốt hơn GEO trong tình huống này?

Nếu muốn **giảm rủi ro rollout** bản API mới chạy trong cùng khu vực, WRR 95:5 là ứng viên phù hợp hơn GEO. Nhưng nếu yêu cầu 5% request/canary chính xác, sử dụng traffic splitting trong **Cloud Run** (dịch vụ hỗ trợ) hoặc cơ chế load balancer phù hợp với kiến trúc backend. Trọng số DNS chỉ là tỷ lệ mong đợi trên các lượt trả lời DNS.

### 9.2. Khi nào không nên dùng DNS policy?

Nếu hai nhóm backend đều nằm sau một **global external Application Load Balancer** với global anycast IP và Cloud CDN, frontend LB có thể đã quản lý điều phối đến backend và cache theo cấu hình. Thêm GEO Cloud DNS ở phía trước **có thể không tạo lợi ích** nếu vẫn chỉ trỏ về một IP toàn cục. Bắt đầu từ **mục tiêu kỹ thuật**, rồi mới quyết định có cần nhiều DNS endpoints hay không.

## 10. Kiến trúc tham chiếu: private failover cho ứng dụng doanh nghiệp

**Bối cảnh:** Hệ thống Java trên Compute Engine cần truy cập dịch vụ nội bộ ở hai region. Private zone `corp.internal.` được gắn với đúng VPC. Dịch vụ có một **primary internal load balancer** và một **backup internal load balancer** được cấu hình sức khỏe phù hợp.

~~~mermaid
flowchart LR
  VM["Java VM trong VPC"] --> DNS["Cloud DNS private zone"]
  DNS --> CH{"FAILOVER policy cho svc.corp.internal"}
  CH --> A["Primary internal LB VIP"]
  CH -. "Khi primary unhealthy" .-> B["Backup internal LB VIP"]
  A --> P["Workload primary"]
  B --> S["Workload standby"]
~~~

Một cấu hình ban đầu có thể đặt **trickle 0.05** để backup nhận một phần truy vấn DNS khi primary khỏe. Nhóm phải đảm bảo standby xử lý được request trong giai đoạn warmup; không chỉ kiểm tra rằng DNS có thể trả VIP.

**Cần định nghĩa rõ:**

- Primary unhealthy được quyết định bởi health signal nào?
- Bên backup có ứng dụng và dữ liệu sẵn sàng không?
- Có hiện tượng split brain nếu cả hai vùng cùng cho phép ghi dữ liệu không?
- Sau khi primary phục hồi, hệ thống có tự failback không và có tác dụng phụ không?
- DNS cache hoặc connection pool giữ endpoint cũ bao lâu?
- Private zone áp dụng cho những VPC nào; Shared VPC và peering có yêu cầu DNS visibility riêng không?
- Nếu truy vấn từ on-prem qua inbound DNS, GEO backup được chọn theo **region của VPN/Interconnect ingress**, có đúng mong đợi không?

**Không dùng failover DNS làm phương án đồng bộ database.** Vấn đề RPO, dữ liệu trùng lặp, khóa giao dịch và consistency cần giải ở tầng lưu trữ/ứng dụng.

## 11. Các bước cấu hình routing policy bằng Console

Dưới đây là trình tự chung theo tài liệu **Configure DNS routing policies and health checks**. Thực hiện trong project/lab được phân quyền và luôn xác nhận loại zone, DNS name, record type, TTL, endpoints và kế hoạch rollback.

### Bước 1 — Xác định zone và endpoint

1. Mở [Cloud DNS](https://console.cloud.google.com/net-services/dns/zones).
2. Chọn project chứa **managed zone**, ví dụ public zone cho `example.com.` hoặc private zone cho `corp.internal.`.
3. Kiểm tra delegation NS nếu là public zone; kiểm tra VPC visibility nếu là private zone.
4. Xác nhận frontend IP/forwarding rule và dịch vụ thực tế đang hoạt động.
5. Kiểm tra **A/AAAA** và phạm vi health checking có hỗ trợ.

### Bước 2 — Tạo một resource record set có policy

1. Trong zone, chọn **Add standard** hoặc **Create record set** theo phiên bản Console.
2. Nhập DNS name, record type (ví dụ **A**) và TTL.
3. Chọn **Routing policy**: WRR, Geolocation hoặc Failover.
4. Nhập trọng số/nguồn region/primary-backup theo chính sách.
5. Nếu GEO, xác nhận **geofencing** bật hay tắt; khi bật cần hiểu mất khả năng chuyển sang vùng khác.
6. Nếu cần health checks, chọn đúng internal LB forwarding rule hoặc external endpoint + health check tùy loại zone.
7. Xem lại và tạo record set.

### Bước 3 — Kiểm chứng và theo dõi

- Dùng `gcloud dns record-sets list` hoặc Console để xác nhận record set và policy.
- Đọc kết quả truy vấn qua một số recursive resolvers với `dig`/`nslookup`; kết quả có thể khác do caching.
- Xem health-check logs khi đã bật và kiểm tra chúng thực sự phản ánh tình trạng endpoint.
- So sánh Cloud DNS query behavior với **request metrics ở từng frontend**, không chỉ đếm truy vấn DNS.
- Kiểm tra lỗi TLS và HTTP từ client thật sau phân giải.
- Với failover, thử tình huống mô phỏng phù hợp trong lab, không chủ động làm hỏng endpoint production để kiểm tra.

### 11.1. Quyền IAM và API

Thiết lập routing policies cần **Cloud DNS API** và quyền sửa RRset. Tài liệu Google nêu các quyền như:

| Permission / Role | Khi nào cần |
| --- | --- |
| `dns.changes.create` | Tạo thay đổi record set |
| `dns.managedZones.list` | Liệt kê zones |
| `roles/dns.admin` | Vai trò quản trị DNS thường dùng khi cấu hình |
| `dns.networks.useHealthSignals` | Truy cập health signals cho internal passthrough NLB theo tình huống |
| `roles/dns.peer` | Vai trò đặc thù khi cần quyền DNS peering/health signal theo yêu cầu |

Quyền cụ thể có thể phụ thuộc việc LB và DNS zone nằm ở project khác nhau. Không cấp Owner/Editor toàn project chỉ để tạo một A record. Khi lab hoặc nhóm có quyền hạn giới hạn, yêu cầu người quản trị cấp đúng role/permission và kiểm tra cross-project IAM.

**Cẩn trọng:** Chuyển chính sách của một RRset đang phục vụ production có thể thay đáp án cho toàn bộ hostname. Hãy review trước khi tạo, cập nhật hoặc xóa.

## 12. Ví dụ Google Cloud CLI

### 12.1. Các lệnh chỉ đọc

Đầu tiên xác minh tài khoản và project:

~~~bash
gcloud config get-value project
gcloud auth list

# Liệt kê DNS managed zones
gcloud dns managed-zones list --project=PROJECT_ID

# Đọc RRsets trong zone
gcloud dns record-sets list \
  --zone=MANAGED_ZONE \
  --project=PROJECT_ID

# Xem các thay đổi DNS gần đây (nếu có)
gcloud dns record-sets changes list \
  --zone=MANAGED_ZONE \
  --project=PROJECT_ID

# Kiểm tra frontend load balancer và health checks
gcloud compute forwarding-rules list --project=PROJECT_ID
gcloud compute health-checks list --project=PROJECT_ID
~~~

Nếu một nhóm lệnh thay đổi hoặc không có trong phiên bản CLI đang dùng, đọc `gcloud dns --help` hoặc [gcloud reference](https://docs.cloud.google.com/sdk/gcloud/reference/dns). Lệnh liệt kê chỉ thấy tài nguyên trong phạm vi IAM có quyền đọc.

### 12.2. Ví dụ tạo WRR không health checking

Sau khi đã có **public zone thử nghiệm** `lab-zone` cho tên `api.example.com.` và đã chuẩn bị hai IP thực tế, lệnh mẫu có thể có dạng:

~~~bash
# Ví dụ thay đổi DNS: chỉ dùng trong lab được cho phép
gcloud dns record-sets create api.example.com. \
  --type=A \
  --ttl=30 \
  --zone=lab-zone \
  --project=LAB_PROJECT_ID \
  --routing-policy-type=WRR \
  --routing-policy-item=weight=9,rrdatas=203.0.113.10 \
  --routing-policy-item=weight=1,rrdatas=198.51.100.20
~~~

Hai IP trong ví dụ là **địa chỉ tài liệu**; phải thay bằng endpoint của lab nếu cần test kết nối thực tế. Ví dụ minh họa WRR **không bật health checks**, vì vậy Cloud DNS sẽ không tự loại IP chỉ vì endpoint ứng dụng lỗi.

Lệnh sử dụng `--routing-policy-item`, thay cho cờ cũ `--routing-policy-data` đã được đánh dấu **deprecated** trong tham chiếu CLI. Tham số có thể thay đổi khi nâng cấp CLI, nên kiểm tra cú pháp bằng `gcloud dns record-sets create --help` trước khi dùng.

### 12.3. Ví dụ tạo GEO không health checking

~~~bash
# Ví dụ thay đổi DNS: chỉ dùng trên managed zone lab
gcloud dns record-sets create geo-api.example.com. \
  --type=A \
  --ttl=30 \
  --zone=lab-zone \
  --project=LAB_PROJECT_ID \
  --routing-policy-type=GEO \
  --routing-policy-item=location=asia-southeast1,rrdatas=203.0.113.10 \
  --routing-policy-item=location=us-central1,rrdatas=198.51.100.20
~~~

GEO đưa ra **đáp án dựa trên source geography mà dịch vụ nhận diện**, không chọn IP gần vị trí người dùng nhất theo từng GPS coordinate. Không có health checking trong ví dụ này; geofencing và health checks nên được cấu hình riêng theo nhu cầu đã kiểm chứng.

### 12.4. Health checked RRsets

Khi cấu hình health check cho **internal LB**, lệnh cần tham chiếu forwarding rule hợp lệ; với external endpoints, cần IP cùng health check config phù hợp và **public zone**. Các option có thể nằm ở `--routing-policy-item`, `--health-check` hoặc cấu hình khi tạo bằng Console/API.

Không thay forwarding rule bằng một IP số học rồi giả định health checking vẫn hoạt động. Để học an toàn, nên thực hành phần này qua **Console** theo các bước chính thức, rồi dùng CLI **chỉ đọc** để kiểm tra kết quả. Lệnh tạo health check hoặc sửa RRset ảnh hưởng tài nguyên đang phục vụ và có thể phát sinh phí.

### 12.5. Kiểm tra DNS từ máy client

Trong terminal có `dig`:

~~~bash
# Truy vấn A record qua DNS resolver mặc định
dig api.example.com A

# Truy vấn thông qua một resolver công khai (chỉ minh họa góc nhìn của resolver)
dig @8.8.8.8 api.example.com A

# Xem thời gian TTL trong kết quả
dig api.example.com A +noall +answer
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
Resolve-DnsName api.example.com -Type A
nslookup api.example.com
~~~

Chạy liên tục từ **cùng một resolver** thường vẫn nhận đáp án cache. Nếu cần nghiên cứu WRR, lấy mẫu qua nhiều resolver/nguồn trong một khoảng đủ lớn và kết hợp request metrics. Không thực hiện DNS query flood để “kiểm tra tỷ lệ” trên public DNS production.

## 13. Quan sát và xử lý sự cố

### 13.1. Tín hiệu cần theo dõi

| Tín hiệu | Câu hỏi | Công cụ |
| --- | --- | --- |
| DNS query count theo tên/zone | DNS đang được sử dụng không? Lượng truy vấn tăng vì TTL thấp? | Cloud DNS monitoring/logging theo hỗ trợ |
| DNS response theo source/region | WRR/GEO có phân bố theo dự kiến không? | DNS query tests, health-check logging |
| Health của endpoint | Target nào unhealthy? Lỗi do probe, LB hay backend? | Cloud DNS health-check logs, LB monitoring |
| Frontend request count | Thực tế bao nhiêu HTTP requests vào mỗi LB? | Cloud Load Balancing/Cloud Run metrics |
| Error rate và p95/p99 latency | Một vùng/endpoint có chậm hoặc lỗi? | Cloud Monitoring, logs, traces |
| TTL/cache | Client có tiếp tục dùng IP cũ? | `dig`, resolver logs, client behavior |
| Chi phí | Query volume, health check và egress thay đổi ra sao? | Cloud Billing, dashboard FinOps |

### 13.2. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Tạo policy báo lỗi | Sai loại zone, RRset type, quyền IAM hoặc trường policy không hợp lệ | Đối chiếu zone type, supported records và gcloud reference |
| Không tìm thấy record mới trong public DNS | Chưa delegation NS đúng, cache, sai zone/project | Kiểm tra NS, managed zone và authoritative response |
| WRR 90:10 nhưng ứng dụng có tỷ lệ khác xa | Resolver cache, các cohort có lưu lượng khác nhau, connection reuse | So query volume với request metrics từng frontend |
| GEO trả IP vùng khác dự kiến | Resolver đặt ở vùng khác/ECS không có, nguồn là hybrid ingress | Kiểm tra resolver và region nơi query vào Google |
| GEO không fail over khi một vùng lỗi | Geofence bật, chưa bật health checking hoặc signal chưa unhealthy | Đọc cấu hình GEO, health logs và target type |
| GEO trả endpoint lỗi dù health check fail | Geofence bật hoặc toàn bộ buckets unhealthy | Đọc fallback behavior và chính sách |
| Failover không sang backup | Chưa mất **toàn bộ** primary, DNS cache, health signal chưa cập nhật | Kiểm tra primary set, TTL và health logs |
| Failover đã đổi DNS nhưng client vẫn lỗi | Connection cũ, app retry không có, backup chưa sẵn sàng | Đo từ client, backend readiness, data consistency |
| Internal LB được coi khỏe nhưng service lỗi | Health của LB khác app-level readiness hoặc passthrough NLB rỗng backend | Xem backend health và đường ứng dụng |
| External endpoint bị xem unhealthy | Probe bị firewall chặn, trả HTTP khác 200, sai port/URL/TLS | Kiểm tra logs, probe config và firewall |
| CNAME route không failover theo health | CNAME health check không hỗ trợ | Dùng A/AAAA được hỗ trợ và thiết kế frontend phù hợp |
| Phản hồi private DNS không tới on-prem | Thiếu inbound forwarding/network/route hoặc chính sách VPC | Kiểm tra DNS hybrid, Cloud VPN/Interconnect và IAM |
| Truy vấn DNS chạy nhưng TCP tới IP lỗi | Firewall, route, LB backend, TLS, service lỗi | Tách DNS test khỏi Connectivity Tests và HTTP probe |

### 13.3. Kiểm tra có trình tự

~~~text
Tên miền và zone có đúng không?
   ↓
Public delegation hoặc private VPC visibility có đúng không?
   ↓
RRset có đúng policy type, items, TTL, type?
   ↓
Nguồn DNS query thực sự ở đâu? Có cache/ECS?
   ↓
Health checking có hỗ trợ và hoạt động đúng?
   ↓
Endpoint trả lời có reachable? LB/backend/ứng dụng có khỏe?
   ↓
Metric request, lỗi, độ trễ, dữ liệu và chi phí có đúng mục tiêu?
~~~

**Khi nghi ngờ Cloud DNS:** Thử truy vấn authoritative và recursive resolver theo các góc nhìn khác nhau; hiểu rằng truy vấn authoritative có thể tạo một policy decision mới, trong khi resolver trả dữ liệu cache. **Khi nghi ngờ kết nối:** tiếp tục với route, firewall, load balancer và ứng dụng; đổi DNS không chữa mọi lỗi network.

## 14. Tình huống học tập: triển khai API đặt lịch ở hai vùng

**Bối cảnh:** Một hệ thống Java cung cấp API `booking.example.com`. Phiên bản hiện tại ở Singapore và phiên bản thử nghiệm ở Tokyo; dữ liệu chính nằm trong cơ sở dữ liệu quan hệ và phải nhất quán giữa các phiên. Đội dự định hướng một phần người dùng tới Tokyo, sau đó mở rộng.

### 14.1. Phương án A — WRR để đánh giá bản thử nghiệm

1. Tạo hai frontend IP/LB phục vụ cùng tên HTTPS.
2. Kiểm tra TLS, API contract, migration database, phiên người dùng và idempotency.
3. Đặt WRR 95:5 khi cần phân phối DNS ước lượng.
4. Thu thập **request count theo endpoint**, error rate, p95, DB query latency, số lượng phiên khác vùng.
5. Điều chỉnh trọng số hoặc rollback dựa trên số liệu.
6. Nếu cần 5% user chính xác, dùng traffic splitting/app routing thay thế.

### 14.2. Phương án B — GEO theo nguồn truy vấn

1. Chọn vùng frontend đáp ứng dữ liệu và độ trễ.
2. Khai báo geography cho các region nguồn DNS quan trọng.
3. Kiểm tra từ các recursive resolvers khác nhau, bao gồm resolver doanh nghiệp/hybrid.
4. Nếu bật health checks, kiểm tra GEO failover **không geofence** khi endpoint lỗi.
5. Nếu yêu cầu không cho phép chuyển vùng, cân nhắc geofence và hiểu rằng người dùng có thể bị lỗi khi vùng đã chọn down.

### 14.3. Phương án C — Một global ALB và Cloud CDN

Nếu mục tiêu là giảm latency của static content hoặc có backend ở nhiều vùng đã được global load balancer quản lý, so sánh phương án một public hostname và frontend global LB với Cloud CDN. Cần đo cache hit ratio, backend latency, cost và độ phức tạp vận hành thay vì tự mặc định DNS GEO tốt hơn.

### 14.4. ADR mẫu cho nhóm kỹ thuật

~~~text
Decision: Dùng WRR 95:5 cho hai external LB để đánh giá bản thử nghiệm
DNS name: booking.example.com
Zone: public
Endpoints: frontend A ở Singapore, frontend B ở Tokyo
Ràng buộc: API contract, TLS, database consistency, data policy
Metric chính: requests per endpoint, HTTP 5xx, p95, errors after retry
Kỳ vọng: 5% DNS responses về B; không cam kết 5% người dùng
Rollback: Đưa trọng số B về 0 / thay đổi record theo quy trình
Nguy cơ: TTL/cache, session affinity, failover và DB latency
Validation: DNS samples + LB request metrics + load test
Next review: Sau khi có đủ số liệu tại nhiều resolver/region
~~~

Đối với production có dữ liệu giao dịch nhạy cảm, cần review bảo mật, khôi phục, mô hình dữ liệu và chi phí trước khi mở rộng tỷ trọng.

## 15. Bài thực hành tự kiểm tra

**Bài 1 — Chọn policy theo tình huống**

| Nhu cầu | Lựa chọn dự kiến | Lý do |
| --- | --- | --- |
| 10% DNS answers đến bản mới | WRR | Có trọng số theo policy item |
| Client vùng Mỹ nhận frontend Mỹ | GEO | Theo source geography nhận diện |
| Chỉ dùng endpoint trong một vùng, dù vùng lỗi | GEO + geofence | Hạn chế chuyển vùng; đánh đổi tính sẵn sàng |
| Nội bộ có primary/backup VIP | FAILOVER | Có health signals, backup GEO và trickle |
| Chia theo HTTP path /images | Application LB | DNS không nhìn HTTP request path |
| Tăng tốc ảnh tĩnh gần client | Cloud CDN | Có edge caching, DNS không cache nội dung |

**Bài 2 — Tính tỷ lệ trọng số.** Cho ba item WRR weight lần lượt 5, 3 và 2. Tỷ lệ query mong đợi là bao nhiêu? Nếu resolver của nhóm thứ nhất tạo 10.000 HTTP requests nhưng chỉ 1 DNS query, kết quả còn đại diện cho 50% traffic HTTP không?

**Gợi ý:** Trọng số cho kết quả 50% / 30% / 20% trên một mẫu lớn các lượt quyết định DNS đủ độc lập. Không thể suy tỷ lệ request vì cache/resolver-client ratio thay đổi.

**Bài 3 — GEO và hybrid DNS.** Người dùng ở Hà Nội truy vấn public zone qua một resolver không gửi ECS đặt ở châu Âu. Còn một VM ở Singapore truy vấn private zone qua VPC, và một máy on-prem sử dụng inbound DNS qua VPN ở `asia-southeast1`. Ba nguồn được suy vị trí như thế nào?

**Gợi ý:** Public chủ yếu dựa resolver IP/ECS; private VM theo region VM; inbound hybrid theo region nơi gói truy vấn đi vào qua VPN/Interconnect appliance.

**Bài 4 — Health checking.** Một internal passthrough NLB không có backend instance nhưng Cloud DNS vẫn cho target “healthy”. Bạn kết luận endpoint có sẵn sàng xử lý giao dịch không?

**Gợi ý:** Không. Cần ít nhất một backend và giám sát application readiness; health signal của DNS không thay kiểm tra nghiệp vụ.

**Bài 5 — Failover.** TTL 60 giây, primary bị lỗi, health check phát hiện sau 30 giây, một recursive resolver vẫn cache IP cũ. Có thể cam kết mọi client chuyển trong 30 giây không?

**Gợi ý:** Không. Cần xét TTL, cache behavior, client retry và kết nối cũ. Con số là tình huống học tập, không phải SLA do Google công bố.

### Checklist khi hoàn thành bài thực hành

- [ ] Xác định zone public/private và record type/TTL.
- [ ] Chọn chính sách dựa trên yêu cầu, giải thích được trade-off.
- [ ] Biết GEO source location phụ thuộc resolver/ECS hoặc region VPC/hybrid ingress.
- [ ] Phân biệt trọng số DNS answers với tỷ lệ request/người dùng.
- [ ] Xác định health checking có hỗ trợ cho endpoint/record type hay không.
- [ ] Biết hành vi GEO geofence và failover/trickle.
- [ ] Hiểu DNS cache, fallback khi tất cả unhealthy và kết nối đã thiết lập.
- [ ] Có lệnh đọc kiểm tra RRsets và kế hoạch kiểm thử từ nhiều resolver.
- [ ] Có metric ứng dụng và phương án rollback.
- [ ] Đã đánh giá mô hình dữ liệu, SLO, bảo mật và chi phí.

## 16. Các lỗi suy luận cần tránh

1. **“WRR 90:10 nghĩa là 90% người dùng vào A.”** Chỉ là trọng số cho DNS decision; caching làm tỷ lệ request khác.
2. **“GEO biết GPS của người dùng.”** Cloud DNS dựa nguồn truy vấn/resolver/ECS hoặc region phía mạng private.
3. **“DNS giống global load balancer.”** DNS không quản lý từng TCP connection hoặc URL path.
4. **“Bật geofence khiến hệ thống đáng tin cậy hơn.”** Geofence có thể trả IP unhealthy của vùng đã chọn, đánh đổi availability.
5. **“Record trỏ tới IP là có health check.”** Health checking phải được bật đúng loại endpoint hỗ trợ.
6. **“Mọi bản ghi đều hỗ trợ health check.”** CNAME/MX/SRV/TXT không hỗ trợ; A/AAAA có phạm vi riêng.
7. **“Khi mọi endpoint unhealthy, DNS sẽ không trả đáp án.”** Cloud DNS có thể trả tất cả endpoint theo quy tắc fallback.
8. **“TTL=30 là RTO=30 giây.”** Health detection, cache và retry không tuân theo một đồng hồ chung.
9. **“Số lượng DNS queries là traffic volume thực.”** Một resolver query có thể phục vụ nhiều HTTP requests.
10. **“Cloud DNS thay thế Cloud CDN.”** CDN cache và phân phối nội dung, DNS chỉ phân giải endpoint.
11. **“Private zone tự dùng được ở mọi VPC.”** Cần VPC visibility/peering/forwarding phù hợp.
12. **“Internal LB health check dùng như external IP trên public zone.”** Hai mô hình có phạm vi và yêu cầu khác nhau.
13. **“Đổi WRR sang GEO chỉ cần sửa một thuộc tính.”** Policy type sau khi chọn có thể cần delete/recreate theo quy trình.
14. **“DNS answer đúng là ứng dụng đã khỏe.”** Cần kiểm tra route, firewall, TLS, backend readiness và dữ liệu.

## 17. Tài liệu Google Cloud chính thức

Các thông số về supported endpoints, health checking, giới hạn DNSSEC, loại policies và cú pháp CLI có thể thay đổi; kiểm tra trang chính thức tại thời điểm triển khai:

- [Cloud DNS overview](https://docs.cloud.google.com/dns/docs/overview) — vùng, public/private zones, cách phân giải.
- [DNS policies overview](https://docs.cloud.google.com/dns/docs/policies-overview) — server, response và routing policies.
- [DNS routing policies and health checks](https://docs.cloud.google.com/dns/docs/routing-policies-overview) — WRR, GEO, geofence, failover, health checks, supported RR types.
- [Configure DNS routing policies and health checks](https://docs.cloud.google.com/dns/docs/configure-routing-policies) — hướng dẫn Console, CLI, API và quyền.
- [gcloud dns record-sets create](https://docs.cloud.google.com/sdk/gcloud/reference/dns/record-sets/create) — cú pháp hiện tại, `--routing-policy-item`, các loại policy.
- [gcloud dns record-sets update](https://docs.cloud.google.com/sdk/gcloud/reference/dns/record-sets/update) — cập nhật RRsets và ràng buộc thay policy type.
- [Cloud DNS best practices](https://docs.cloud.google.com/dns/docs/best-practices) — vận hành và kiểm thử.
- [Cloud DNS logging and monitoring](https://docs.cloud.google.com/dns/docs/monitoring) — quan sát truy vấn và tình trạng DNS.
- [Cloud Load Balancing overview](https://docs.cloud.google.com/load-balancing/docs/load-balancing-overview) — các loại LB và quyết định phân phối backend.
- [Cloud CDN overview](https://docs.cloud.google.com/cdn/docs/overview) — cache edge, nội dung tĩnh và dynamic caching phù hợp.
- [Google Cloud DNS pricing](https://cloud.google.com/dns/pricing) — mô hình giá dựa zone và DNS queries.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — phân tích đường mạng bên dưới DNS.

**Điểm cốt lõi:** Cloud DNS routing policy điều khiển **đáp án DNS**, không phân phối từng request. **WRR** hợp với phân bổ theo trọng số, **GEO** hợp với chọn theo vùng nguồn truy vấn, **geofence** giữ vùng dù phải chịu rủi ro downtime, và **FAILOVER** hỗ trợ active-backup nội bộ theo health signals. Một phương án tin cậy cần đo DNS cache, tình trạng endpoint, khả năng phục vụ thực, dữ liệu và chi phí thay vì chỉ kiểm tra record đã tạo.
