# Application firewall

> **Chương:** Firewall  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Phạm vi:** Tường lửa nhận biết ứng dụng, đặc biệt là Web Application Firewall (WAF), trong kiến trúc phòng vệ mạng gồm phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi, cloud và giám sát xâm nhập.

## 1. Application firewall là gì?

**Application firewall** là nhóm biện pháp kiểm soát lưu lượng dựa trên hiểu biết về **giao thức hoặc hành vi của ứng dụng**, thay vì chỉ dựa vào địa chỉ IP, cổng và giao thức vận chuyển. Khi nói đến bảo vệ ứng dụng web, thuật ngữ này thường chỉ **Web Application Firewall (WAF)**, một thành phần phân tích và quyết định đối với các yêu cầu HTTP/HTTPS đi tới ứng dụng hoặc API.

Ví dụ, firewall lớp mạng có thể cho phép kết nối TCP tới cổng 443. WAF có thể quan sát tiếp một yêu cầu HTTP: phương thức GET/POST, đường dẫn /api/orders, header, cookie, query string, kiểu nội dung, kích thước body và mẫu dữ liệu bất thường. Từ đó WAF có thể chặn một yêu cầu chứa dấu hiệu tấn công, giới hạn tốc độ hoặc ghi nhận sự kiện để điều tra.

Nhưng **WAF không tự làm cho ứng dụng an toàn**. Khi ứng dụng có lỗi phân quyền, lộ bí mật ở đầu ra hoặc xử lý nghiệp vụ sai, một yêu cầu HTTP hoàn toàn hợp lệ về cú pháp vẫn có thể gây thiệt hại. Bảo vệ đúng cách cần thiết kế ứng dụng an toàn, xác thực, phân quyền, kiểm thử, bảo vệ hạ tầng và giám sát nhiều lớp.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt WAF, firewall L3/L4, NGFW, host firewall, API gateway và IDS/IPS.
2. Giải thích nơi đặt WAF, ảnh hưởng của TLS, reverse proxy, load balancer, NAT và địa chỉ IP client thật.
3. Đọc chính sách WAF theo điều kiện match, hành động, độ ưu tiên, trạng thái giám sát và mức tin cậy.
4. Thiết kế các chính sách có giới hạn cho API/web, chống khai thác phổ biến, abuse và request flood.
5. Xây dựng kế hoạch triển khai, kiểm thử, xử lý false positive và đánh giá hiệu quả thực tế.

## 2. Phân biệt các loại firewall và thành phần gần nhau

| Thành phần | Thông tin thường xem xét | Trường hợp sử dụng chính | Giới hạn cần nhớ |
|---|---|---|---|
| **Network firewall L3/L4** | IP, subnet, protocol, port, direction, session state | Phân đoạn zone, chặn kết nối không được phép | Không tự hiểu logic URL, API, tham số hoặc quyền ứng dụng |
| **Next-Generation Firewall (NGFW)** | Kết nối, nhận diện ứng dụng, đôi khi TLS inspection, IPS, URL filtering | Kiểm soát ứng dụng đi qua mạng doanh nghiệp | Độ sâu kiểm tra phụ thuộc giải mã, tính năng và đường đi thực tế |
| **Web Application Firewall (WAF)** | HTTP request, URI, header, cookie, query/body, đặc trưng web | Bảo vệ website, reverse proxy và HTTP API | Không thay thế authz, code review, kiểm thử ứng dụng và phòng thủ DDoS L3/L4 |
| **Host/application-aware firewall** | Process, binary, user, kết nối trên endpoint; phụ thuộc OS/sản phẩm | Hạn chế ứng dụng nào được mở hoặc nhận kết nối | Không đồng nghĩa có khả năng phân tích và chặn payload HTTP |
| **API gateway** | Route API, token, quota, schema, transformation, auth khi cấu hình | Quản lý API, xác thực và định tuyến | Không phải mọi gateway đều có WAF hoặc khả năng chặn khai thác sâu |
| **IDS/IPS** | Chữ ký và hành vi bất thường ở traffic nhìn thấy được | Phát hiện/ngăn ngừa mẫu tấn công mạng | Phụ thuộc sensor, giải mã, vùng quan sát và false positive/negative |
| **RASP / kiểm soát trong ứng dụng** | Ngữ cảnh thực thi, dữ liệu và thao tác ở runtime | Bảo vệ các đường xử lý trong ứng dụng khi hỗ trợ | Không thay thế thiết kế ứng dụng an toàn hoặc policy biên mạng |

Do tên gọi **application firewall** được nhiều nhà cung cấp sử dụng khác nhau, khi chọn sản phẩm cần xác định chính xác: nó bảo vệ **HTTP ingress**, kiểm soát **egress theo ứng dụng**, giám sát **process tại endpoint**, hay kết hợp nhiều khả năng? Phần còn lại tập trung vào WAF ở tầng HTTP, đồng thời liên hệ với NGFW và kiểm soát mạng.

## 3. WAF hoạt động ở đâu trong mô hình OSI?

HTTP là giao thức tầng ứng dụng (thường ánh xạ với **lớp 7 OSI**). Vì vậy WAF thường được gọi là **firewall Layer 7**. Điều này không có nghĩa WAF độc lập với các tầng bên dưới: nó vẫn cần TCP hoặc cơ chế truyền tải tương ứng, TLS nếu có, định tuyến, DNS và các kết nối tới origin.

~~~mermaid
flowchart LR
    C[Browser hoặc API client] -->|HTTPS| E[DNS / CDN / Edge]
    E -->|HTTPS| W[WAF / Reverse proxy]
    W -->|HTTP hoặc HTTPS theo thiết kế| L[Load balancer]
    L --> A[Ứng dụng web / API]
    A --> D[(Database)]
    W -. HTTP security events .-> S[SOC / SIEM]
    L -. Access logs .-> S
    A -. Auth và application logs .-> S
~~~

Đây là sơ đồ **logic**: WAF có thể tích hợp ngay trong CDN, API gateway, load balancer, reverse proxy, dịch vụ cloud hoặc chạy như phần mềm riêng. Một tổ chức có thể có nhiều lớp WAF, nhưng mỗi lớp phải được cấu hình phù hợp để tránh xử lý trùng lặp hoặc tạo những điểm mù.

### 3.1. Các kiểu triển khai thường gặp

- **Reverse proxy inline:** client kết nối đến proxy/WAF, proxy tạo kết nối khác tới origin. Có thể xử lý và chặn request trước khi chuyển tiếp.
- **CDN/Cloud WAF:** request đi qua edge của nhà cung cấp trước khi tới hệ thống. Cần bảo đảm origin không thể bị truy cập trực tiếp ngoài đường hợp lệ.
- **WAF tích hợp trong API gateway/load balancer:** áp dụng rule theo listener, route, domain, API hoặc policy của nhà cung cấp.
- **Network inline hoặc bridge:** thiết bị đứng trên đường truyền và có thể kiểm tra traffic nếu hiểu/nhìn thấy HTTP; đặc tính TLS và failover khác nhau.
- **Phát hiện ngoài băng (out-of-band):** nhận bản sao traffic để phân tích, thường **không thể chặn yêu cầu đã đi qua** theo cách một proxy inline có thể làm.

**Điều kiện cốt lõi:** WAF chỉ bảo vệ **những yêu cầu thực sự đi qua điểm thực thi** và có dữ liệu ứng dụng mà nó đọc được. Nếu DNS, route, public IP, peering, tunnel hoặc máy quản trị tạo đường khác đến origin, rule ở WAF có thể bị bỏ qua.

## 4. TLS, reverse proxy và ranh giới tin cậy

### 4.1. Khi nào WAF đọc được HTTP bên trong HTTPS?

HTTPS mã hóa nội dung HTTP. WAF cần **được đặt tại điểm kết thúc/giải mã TLS hợp lệ**, hoặc nhận traffic HTTP rõ từ một thành phần được tin cậy, mới có thể kiểm tra phần lớn trường request và body. Nếu chỉ thấy các gói TLS đã mã hóa mà không giải mã, WAF không thể dựa vào toàn bộ nội dung HTTP để áp rule.

Các mô hình thường gặp:

| Mô hình | WAF thấy gì? | Điều cần bảo vệ |
|---|---|---|
| Client → **WAF kết thúc TLS** → Origin HTTPS | WAF thấy HTTP đã giải mã tại điểm kết thúc; đường sau được mã hóa lại | Chứng chỉ và khóa TLS, xác thực origin, TLS ở cả hai chặng |
| Client → TLS terminator → **WAF nhận HTTP nội bộ** → Origin | WAF thấy HTTP nếu terminator chuyển tiếp rõ | Phân đoạn mạng nội bộ, trust proxy, hạn chế truy cập vào HTTP nội bộ |
| Client → **WAF chỉ chuyển tiếp TLS pass-through** → Origin | Không thấy đầy đủ request HTTP nếu không có giải mã khác | Không thể kỳ vọng đầy đủ tính năng kiểm tra HTTP body |
| Client → CDN/WAF edge → Origin | WAF kiểm tra ở edge; origin nhận yêu cầu đã qua edge | Chặn origin bypass, xác nhận nguồn proxy và bảo vệ kết nối edge-origin |

WAF có thể hỗ trợ thêm TLS fingerprint hoặc tín hiệu kết nối, nhưng **TLS metadata không thay thế được kiểm tra payload HTTP**.

### 4.2. Địa chỉ IP thực của client

Khi nhiều proxy đứng trước ứng dụng, IP socket kết nối đến WAF có thể là địa chỉ của CDN hoặc load balancer. Các header như **X-Forwarded-For** hoặc **Forwarded** có thể chứa chuỗi địa chỉ được chuyển tiếp. Tuy nhiên, **client có thể tự gửi header giả** nếu hệ thống không xử lý đúng ranh giới tin cậy.

Quy tắc thiết kế:

1. Xác định **proxy nào được tin cậy**, bằng IP/identity và đường kết nối thực tế.
2. Chỉ lấy địa chỉ client từ **chuỗi header đã được proxy tin cậy chuẩn hóa**, theo cách nhà cung cấp hỗ trợ.
3. Bỏ qua hoặc ghi đè thông tin forwarded do client không tin cậy cung cấp; không tin mọi giá trị X-Forwarded-For xuất hiện trong request.
4. Kiểm thử các trường hợp đi qua nhiều proxy, NAT chia sẻ, IPv6 và thay đổi dải IP của nhà cung cấp.

Nếu xác định sai IP, rule rate limit, allowlist hoặc điều tra sự cố có thể nhắm **sai người dùng** hoặc bị bypass bằng header giả mạo.

## 5. WAF đánh giá một yêu cầu như thế nào?

Trình tự chi tiết phụ thuộc sản phẩm. Một mô hình logic:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu HTTP/HTTPS] --> B[Giải mã TLS tại điểm được phép]
    B --> C[Parse method, path, header, query, body]
    C --> D[Chuẩn hóa dữ liệu theo engine]
    D --> E{Đối chiếu policy / rule / anomaly score}
    E -- Rủi ro phù hợp chính sách --> F[Block, challenge hoặc rate limit]
    E -- Cần quan sát --> G[Log / count / monitor]
    E -- Hợp lệ --> H[Chuyển yêu cầu đến origin]
    G --> H
    F --> I[Ghi sự kiện để điều tra]
    H --> J[Ứng dụng xác thực và phân quyền]
~~~

**Các bước hay được kiểm tra:** phương thức HTTP, host, path, URL encoding, query parameter, header, cookie, kiểu nội dung, cấu trúc JSON/XML, kích thước body và tốc độ gọi API. Một số WAF có thể nhìn response, nhưng khả năng kiểm tra response body và dữ liệu nhạy cảm phụ thuộc sản phẩm/cấu hình; không mặc định WAF ngăn toàn bộ dữ liệu lộ ra ngoài.

### 5.1. Rule match và action

| Phần rule | Ví dụ minh họa | Mục đích |
|---|---|---|
| Đối tượng | Host api.example.com và path /v1/orders/* | Giới hạn rule tới dịch vụ cụ thể |
| Phương thức | Chỉ GET/POST theo API contract | Giảm giao diện không cần thiết |
| Điều kiện dữ liệu | Header bất thường, body vượt giới hạn, dấu hiệu payload nguy hiểm | Phát hiện yêu cầu không phù hợp |
| Mức ưu tiên | Rule xác định người dùng/exception trước hoặc sau rule chung theo semantics engine | Giải quyết xung đột và phạm vi |
| Chế độ | Monitor/count, challenge, block, rate limit | Thử tác động trước khi bật chặn |
| Thông tin bổ sung | ID rule, owner, lý do, hạn review, log và metric | Kiểm toán chính sách |

**Rule order không giống nhau giữa các WAF.** Có sản phẩm dùng priority, có sản phẩm cộng điểm bất thường rồi mới quyết định, có sản phẩm tách managed rule group và custom rule. Phải xác minh cách engine giải quyết trường hợp nhiều rule cùng khớp, exception tương tác với managed rule và action nào kết thúc xử lý.

### 5.2. Positive security model và negative security model

**Negative model** tìm mẫu được cho là độc hại: dấu hiệu SQL injection, XSS, path traversal hoặc chuỗi payload đáng ngờ. Cách này giúp bảo vệ nhiều ứng dụng nhanh, nhưng luôn có nguy cơ **false negative** khi kỹ thuật tấn công thay đổi.

**Positive model** định nghĩa hành vi được phép: API path, method, Content-Type, schema, kích thước, danh sách giá trị hợp lệ và quyền theo ngữ cảnh thích hợp. Cách này mạnh với API ổn định nhưng tốn công bảo trì, dễ gây **false positive** khi ứng dụng thêm chức năng hoặc đổi schema.

Thực tế có thể kết hợp: managed signatures/anomaly scoring, rate limiting, quy tắc riêng theo endpoint và **schema validation** tại API gateway hoặc ứng dụng. WAF vẫn không phải nguồn duy nhất quyết định quyền nghiệp vụ.

## 6. Những nhóm nguy cơ WAF có thể hỗ trợ giảm thiểu

| Kịch bản | WAF có thể làm gì? | Cần bổ sung gì? |
|---|---|---|
| **SQL injection** | Phát hiện/chặn một số mẫu truy vấn đầu vào đáng ngờ | Prepared statements, truy vấn tham số hóa, phân quyền DB |
| **Cross-Site Scripting (XSS)** | Phát hiện một số payload đi qua request | Encoding theo ngữ cảnh, template an toàn, CSP, loại bỏ DOM XSS trong mã |
| **Path traversal / file inclusion** | Kiểm tra path/parameter chứa dấu hiệu truy cập file trái phép | Chuẩn hóa path an toàn, kiểm tra quyền, cô lập filesystem |
| **Command injection / RCE qua input** | Phát hiện một số mẫu lệnh hoặc chuỗi nghi vấn | Không thực thi shell theo input, API an toàn, sandbox, least privilege |
| **SSRF** | Chặn một số mẫu URL/host hoặc đầu vào đáng ngờ | Egress firewall, metadata protection, allowlist đích tại ứng dụng |
| **HTTP request flood / bot abuse** | Rate limit, bot signals, challenge, rule theo URI/identity | DDoS ở edge/L3/L4, quota, auth, cache, autoscaling |
| **Malformed HTTP** | Từ chối một số request sai định dạng hoặc dấu hiệu tấn công parser | Đồng bộ hành vi proxy/origin, vá lỗi và kiểm thử request framing |
| **Quét lỗ hổng qua HTTP** | Ghi log/chặn các mẫu truy cập bất thường | Asset inventory, vá lỗi, phân tích log và phát hiện theo hành vi |
| **API abuse** | Quota, giới hạn kích thước, path/method và schema khi hỗ trợ | Authorization theo đối tượng, token scope, kiểm soát nghiệp vụ |

**Không phải mọi sản phẩm WAF đều hỗ trợ đầy đủ các tính năng trong bảng.** Cần xác minh engine có parse được giao thức, encoding, body và luồng ứng dụng đang sử dụng. Đối với traffic mà WAF không thể phân tích, chính sách giới hạn có thể chỉ hoạt động ở mức header, kết nối hoặc metadata.

### 6.1. Vì sao có thể bỏ sót tấn công?

Kẻ tấn công có thể lợi dụng biến thể cú pháp, mã hóa nhiều lớp, JSON lồng nhau, multipart, phân mảnh payload, request qua giao thức chưa được hỗ trợ, hoặc sự khác nhau giữa **cách WAF parse request** và **cách origin parse request**. Nếu hai thành phần diễn giải request không giống nhau, có thể phát sinh lỗ hổng ở ranh giới HTTP.

Do đó cần cập nhật rule, đồng bộ hành vi proxy/origin, giám sát kết quả thực tế và kiểm thử các đường parse phức tạp của ứng dụng. Không nên coi việc cài một bộ chữ ký chung là kết thúc việc bảo vệ.

### 6.2. Những nguy cơ WAF thường không giải quyết triệt để

- **Broken object-level authorization (BOLA/IDOR):** người dùng đăng nhập hợp lệ yêu cầu dữ liệu của người khác thông qua API hợp lệ.
- **Business logic abuse:** lặp thao tác hoàn tiền, dùng mã giảm giá sai quy tắc, thay đổi trạng thái đơn hàng bất thường.
- **Lộ thông tin từ server:** origin trả dữ liệu không phù hợp do lỗi phân quyền hoặc cấu hình.
- **Credential theft / session hijacking:** WAF có thể hỗ trợ phát hiện abuse nhưng không thay thế bảo vệ token, MFA và session management.
- **Tấn công nội bộ bỏ qua WAF:** ví dụ đi trực tiếp từ subnet workload tới origin hoặc gọi API quản trị riêng.
- **DDoS mạng:** packet flood, SYN flood hoặc nghẽn đường truyền trước khi traffic tới WAF HTTP.

Biện pháp nền tảng vẫn là **secure coding, cập nhật bản vá, xác thực/phân quyền, network segmentation, giới hạn egress và giám sát**.

## 7. Kiến trúc tham chiếu: website và HTTP API trên cloud

Giả sử tổ chức triển khai ứng dụng tại cloud. Đây là **môi trường minh họa**, không phải cấu hình thật của một doanh nghiệp:

- **Tên miền public:** app.example.com và api.example.com.
- **Địa chỉ công khai minh họa:** 203.0.113.20 (dải dành cho tài liệu).
- **Edge/WAF:** tiếp nhận HTTPS từ client, kiểm tra HTTP và chuyển tiếp theo route.
- **Private application subnet:** 10.60.20.0/24; backend tại 10.60.20.10.
- **Database subnet:** 10.60.30.0/27; DB tại 10.60.30.10.
- **Management subnet:** 10.60.40.0/27; jump host dành cho nhân viên được xác thực.
- **SOC:** nhận WAF events, firewall flow logs, authentication logs và application logs.

~~~mermaid
flowchart TB
    I[Internet clients] -->|HTTPS 443| W[CDN + WAF]
    W -->|HTTPS theo origin policy| L[Private application ingress]
    L --> A[Web / API 10.60.20.10]
    A -->|DB connection| D[(Database 10.60.30.10)]
    V[VPN / ZTNA admins] --> J[Jump host 10.60.40.10]
    J -->|Management only| A
    W -. WAF events .-> S[SOC / SIEM]
    A -. App/auth logs .-> S
    L -. Network flows .-> S
~~~

### 7.1. Phân trách nhiệm giữa WAF và network firewall

| Đường truy cập | Lớp kiểm soát | Quyết định |
|---|---|---|
| Internet → WAF, HTTPS | Edge, WAF, DDoS protection | Cho kết nối TLS hợp lệ tới endpoint công khai; kiểm tra request HTTP |
| Internet → origin trực tiếp | Security group/ACL, origin identity, route | **Deny** nếu không đi qua đường proxy đã cho phép |
| WAF → application ingress | Network firewall, xác thực origin và TLS | **Allow** từ nguồn/identity proxy tin cậy, đúng dịch vụ |
| Application → Database | Private subnet firewall + DB authentication | **Allow** đúng source, port và role cần thiết |
| Người dùng thường → quản trị | ACL, VPN/ZTNA, IAM, host firewall | **Deny** khi không có quyền quản trị |
| VPN admin → jump host | VPN/ZTNA, MFA, ACL, logging | **Allow có điều kiện**, xác thực/ủy quyền vẫn bắt buộc |
| Ứng dụng → DNS/IdP/monitoring | Egress policy, resolver kiểm soát | Cho phép các dịch vụ thực sự cần; giám sát phụ thuộc |

Một WAF được đặt trước website không bao phủ kết nối trực tiếp Application → Database, VPN → SSH, lưu lượng Wi-Fi cùng lớp 2, lưu lượng DNS hoặc IPsec. Những đường này cần **control phù hợp ở tầng mạng, danh tính hoặc endpoint**.

### 7.2. Ngăn bypass origin

Sai lầm thường gặp là công khai IP/load balancer origin và chỉ thay DNS trỏ đến WAF. Nếu firewall origin vẫn cho phép **any source → origin TCP 443**, bên ngoài có thể truy cập bằng đường trực tiếp mà không qua WAF.

Cách giảm nguy cơ:

1. Đặt origin trong private network hoặc chặn Internet truy cập trực tiếp khi kiến trúc hỗ trợ.
2. Chỉ cho nguồn/kết nối của edge/proxy tin cậy tới origin, duy trì cập nhật nguồn theo cơ chế nhà cung cấp.
3. Dùng **mTLS, origin authentication hoặc cơ chế xác thực edge-origin** khi có hỗ trợ; chỉ dựa vào một secret HTTP header tĩnh có thể chưa đủ trong mọi mô hình đe dọa.
4. Kiểm tra domain phụ, IPv6, IP cũ, route riêng, VPN/peering và cổng quản trị tránh tạo đường vòng.
5. Giám sát access log của origin để phát hiện traffic không qua WAF.

**DNS trỏ qua WAF không phải cơ chế cưỡng chế đi qua WAF**. Enforcement cần đến từ route, policy và xác thực kết nối của origin.

## 8. Thiết kế policy cho HTTP và API

Một policy tốt ưu tiên **đúng ứng dụng, đúng endpoint và đúng hành vi cần thiết**. Trước khi áp rule chặn, cần biết API contract, mức độ nhạy cảm, lượng request thông thường và hệ thống nào là client hợp lệ.

### 8.1. Ma trận policy minh họa

| ID | Host/đường dẫn | Điều kiện | Hành động dự kiến | Lý do |
|---|---|---|---|---|
| W-010 | app.example.com/* | HTTP method được ứng dụng hỗ trợ; HTTPS hợp lệ | Allow sau khi qua managed rules | Đường truy cập người dùng thông thường |
| W-020 | api.example.com/v1/orders | GET/POST theo contract; kiểu body và kích thước hợp lệ | Allow, ghi metric | API nghiệp vụ |
| W-030 | api.example.com/v1/orders | Method không được API hỗ trợ | Block hoặc trả 405 từ API/gateway theo thiết kế | Giới hạn bề mặt API |
| W-040 | app.example.com/admin/* | Yêu cầu qua cổng truy cập quản trị được xác thực | Giới hạn tại WAF và **kiểm tra authz trong app** | Bảo vệ giao diện quản trị |
| W-050 | Tất cả đường public | Managed rules cho các mẫu khai thác đã biết | Monitor trước, block sau khi kiểm chứng | Giảm nguy cơ các mẫu phổ biến |
| W-060 | Endpoint đăng nhập | Tốc độ bất thường theo tín hiệu phù hợp | Rate limit/challenge | Hạn chế abuse, lưu ý mạng NAT |
| W-070 | API public có quota | Vượt hạn mức theo API key đã xác minh hoặc danh tính tương đương | 429/quota policy | Bảo vệ tài nguyên và công bằng sử dụng |
| W-080 | Các đường chưa công bố | Không khớp API contract | Chặn theo chính sách nếu xác minh đủ độ phủ | Tránh endpoint ngoài dự kiến |

Các quyết định trên là **ví dụ thiết kế**, không phải cấu hình hợp lệ cho mọi WAF. Có ứng dụng cần OPTIONS/CORS preflight, PATCH hoặc các request health check; block mọi method khác GET/POST mà không khảo sát sẽ làm hỏng tính năng. Endpoint quản trị phải dựa vào **xác thực và phân quyền ở lớp ứng dụng hoặc cổng truy cập**, không coi allowlist IP là đủ.

### 8.2. Ví dụ chính sách khai báo dạng giả mã

~~~yaml
# Minh họa hồ sơ policy; không chạy trực tiếp trên nhà cung cấp WAF
policy_id: WEB-APP-PROTECTION-001
asset: "Public Web and HTTP API"
owners:
  - "Application Team"
  - "Network Security"
mode: monitor
scope:
  hosts: ["app.example.com", "api.example.com"]
  paths: ["/", "/v1/*"]
controls:
  managed_rules:
    enabled: true
    action_after_validation: block
  request_limits:
    max_body_size: "Theo API contract và giới hạn engine"
    allowed_content_types: ["application/json"]
    applicable_path: "/v1/orders"
  rate_limit:
    identity: "Verified API key or trusted client identity"
    threshold: "Xác định từ baseline; chưa đặt số cố định"
  exceptions:
    owner_required: true
    expires_at_required: true
validation:
  - "Allow legitimate API clients"
  - "Reject unsupported methods"
  - "Observe false-positive rate"
  - "Verify origin cannot bypass WAF"
rollout: "monitor -> selective block -> production enforcement"
~~~

Giới hạn Content-Type và body size phải xét theo từng path: một ứng dụng upload file cần multipart/form-data, trong khi API JSON chỉ cần application/json. Đặt cùng một điều kiện cho mọi URL có thể làm hỏng chức năng hợp lệ.

## 9. Rate limiting, bot mitigation và kiểm soát request flood

WAF thường hỗ trợ **rate limiting** để giảm request flood hoặc abuse có quy luật. Ví dụ một client gửi hàng nghìn yêu cầu đến endpoint tìm kiếm trong thời gian ngắn, làm backend tiêu tốn tài nguyên.

Các biến thiết kế cần xác định:

| Thành phần | Câu hỏi thiết kế |
|---|---|
| **Đơn vị tính** | Theo IP, phiên, tài khoản, API key đã xác thực, device identity hay kết hợp? |
| **Cửa sổ thời gian** | Sliding window, fixed window hoặc token bucket? Engine triển khai chính xác ra sao? |
| **Phạm vi** | Toàn domain, path, method, endpoint tốn tài nguyên hay mỗi tenant? |
| **Ngưỡng và burst** | Baseline, peak hợp lệ, retry của client, NAT chia sẻ và spike do chiến dịch? |
| **Action** | Log, delay, challenge, 429, tạm chặn theo chính sách? |
| **Khả năng phân tán** | Counter có dùng chung giữa các điểm edge/region không? |

**Giới hạn của rate limit theo IP:** hàng trăm người dùng hợp lệ có thể dùng chung IP doanh nghiệp/NAT; ngược lại một botnet có nhiều IP khác nhau. IP dễ bị giả trong header nếu trust proxy cấu hình sai. Khi API có xác thực, có thể xét rate theo **danh tính/token đã được xác minh**, tenant hoặc token bucket của gateway; nhưng vẫn cần bảo vệ trước bước xác thực và với client chưa xác thực.

Khi dùng HTTP **429 Too Many Requests**, API có thể cung cấp tín hiệu retry theo contract phù hợp, ví dụ header Retry-After. Không mặc định mọi tính năng rate limiting của WAF đều trả chính xác 429 hoặc có thể cấu hình cùng một cách.

### 9.1. WAF không giải quyết toàn bộ DDoS

WAF có thể giảm **HTTP request flood** nếu traffic đến được điểm lọc, nhưng không thể tự bảo vệ đường truyền khỏi **volumetric DDoS** xảy ra trước nó. Kiến trúc có thể cần CDN, dịch vụ anti-DDoS ở edge, upstream filtering, bảo vệ SYN/UDP flood, autoscaling, cache và kế hoạch phối hợp với ISP/cloud provider.

## 10. False positive, false negative và cách hiệu chỉnh rule

**False positive** là request hợp lệ bị WAF chặn hoặc bị gán là độc hại. Ví dụ người dùng nhập một đoạn mã vào diễn đàn kỹ thuật, upload tài liệu chứa các từ khóa đặc biệt hoặc API gửi JSON chứa cấu trúc lạ nhưng hợp lệ.

**False negative** là request nguy hiểm không bị phát hiện; có thể do mẫu tấn công mới, thiếu parser, request được mã hóa/biến đổi khác kỳ vọng hoặc lưu lượng bypass WAF.

| Dấu hiệu | Giả thuyết | Xử lý phù hợp |
|---|---|---|
| 403 tăng đột ngột sau bật managed rules | Rule chặn request hợp lệ | Xem event ID, path, matched variable, log ứng dụng và release mới |
| API upload file lỗi ngẫu nhiên | Kích thước body, multipart parser, timeout, upload limit | Đối chiếu contract, giới hạn engine và HTTP response từ từng hop |
| API vẫn bị truy cập trái phép dù WAF bật | Lỗi authz hoặc đường bypass origin | Kiểm tra quyền tại app, direct-origin traffic và access log |
| Request nghi vấn không có log WAF | Traffic không qua WAF hoặc telemetry không đầy đủ | Kiểm tra DNS, origin, route, log forwarding và zone |
| Sau rate limit, nhiều người dùng văn phòng cùng nhận 429 | NAT chia sẻ IP hoặc key rate không phù hợp | Điều chỉnh theo identity, path và baseline; tránh whitelist cả mạng quá rộng |

### Quy tắc xử lý exception

Ưu tiên **ngoại lệ hẹp** theo rule ID, endpoint, method, trường dữ liệu, client đã xác minh hoặc ngữ cảnh ứng dụng. Gắn lý do, owner, hạn hết hiệu lực và kiểm thử lặp lại. Không vô hiệu hóa toàn bộ nhóm bảo vệ chỉ vì một request hợp lệ bị chặn.

Đối với chữ ký có false positive, cần chọn giữa **tuning**, sửa validation của ứng dụng, thay rule, hoặc thêm exception chính xác. Mỗi lựa chọn phải cân nhắc phần nguy cơ còn lại.

## 11. Những dạng traffic hiện đại cần đánh giá riêng

### 11.1. JSON API và schema validation

WAF phải nhận diện JSON theo Content-Type và parser được hỗ trợ, xử lý object/array lồng nhau, chuỗi được escape, encoding và body size. **Schema validation** giúp giới hạn các trường, kiểu dữ liệu và kích thước được API chấp nhận; nhưng **không thể thay thế authorization theo đối tượng**.

### 11.2. GraphQL

GraphQL thường gửi nhiều thao tác qua một endpoint HTTP. Rule chỉ nhìn path /graphql không đủ phân biệt truy vấn nặng, mutation, introspection hay quyền trên từng field. Cần bổ sung ở gateway/application: giới hạn độ phức tạp, depth/cost theo chính sách, authz theo resolver và kiểm soát query batching/persisted query khi phù hợp.

### 11.3. WebSocket và kết nối kéo dài

WebSocket thường bắt đầu bằng **HTTP Upgrade handshake**, sau đó trao đổi các frame khác với request HTTP thông thường. Một WAF chỉ kiểm tra handshake không mặc nhiên hiểu và bảo vệ đầy đủ nội dung WebSocket. Cần kiểm tra khả năng hỗ trợ thực tế, xác thực/ủy quyền khi mở kết nối và validation ở máy chủ.

### 11.4. gRPC, HTTP/2 và HTTP/3

gRPC thường dùng HTTP/2 và payload Protocol Buffers; nhiều WAF không parse sâu toàn bộ message nếu thiếu tích hợp. HTTP/2 multiplexing và HTTP/3 trên QUIC cũng có khác biệt về luồng xử lý, TLS và proxy. Kiểm tra **giao thức hỗ trợ, giới hạn body, xử lý stream và logging** của từng sản phẩm, không coi “hỗ trợ HTTP” là đồng nghĩa hỗ trợ mọi hình thức API như nhau.

### 11.5. Request parsing giữa các proxy

Chuỗi Client → CDN → WAF → Reverse proxy → Application phải xử lý nhất quán các quy tắc framing và chuẩn hóa URL/header. Khác biệt trong cách xử lý HTTP request có thể tạo rủi ro như **request smuggling/desynchronization**. Cần cập nhật thiết bị, tuân thủ HTTP semantics, kiểm thử chuỗi proxy và giảm các biến đổi không cần thiết. Không chỉ phụ thuộc chữ ký WAF khi vấn đề nằm ở sự không thống nhất parser.

## 12. Vận hành WAF với network segmentation, VPN, DNS và cloud

Application firewall phát huy tác dụng khi được đặt trong **kiến trúc nhiều lớp**, mỗi lớp xử lý đúng loại rủi ro.

| Lớp bảo vệ | Vai trò bổ trợ WAF |
|---|---|
| **Network segmentation** | Origin, DB, quản trị ở subnet/zone riêng; hạn chế đường bypass WAF và lateral movement |
| **L3/L4 firewall, SG/NACL** | Chỉ cho kết nối cần thiết từ proxy đến origin; chặn truy cập trực tiếp từ Internet |
| **VPN / ZTNA + IAM** | Kiểm soát truy cập quản trị dựa trên danh tính, thiết bị và chính sách phiên |
| **TLS / mTLS** | Bảo vệ tính bí mật/toàn vẹn dữ liệu trên các chặng và xác thực đối tác khi phù hợp |
| **DNS security** | Quản lý tên miền public và resolver, giảm nguy cơ cấu hình sai và bất thường DNS |
| **Wi-Fi / NAC** | Bảo vệ mạng nội bộ và thiết bị đầu cuối; WAF công khai không lọc mọi traffic Wi-Fi |
| **IDS/IPS / NDR** | Quan sát traffic ở ranh giới mạng và hành vi ngoài HTTP, bổ sung telemetry cho WAF |
| **Cloud WAF / DDoS / CDN** | Chặn/giới hạn HTTP ở edge, bảo vệ khả năng phục vụ và hỗ trợ scale |
| **Ứng dụng / API gateway** | Xác thực, phân quyền, kiểm tra input, business logic, quota và log chi tiết |

### Hai luồng cần phân biệt

**North–south:** người dùng Internet gửi HTTPS đến website qua edge/WAF. Đây là luồng WAF công khai thường bảo vệ tốt nhất nếu cấu hình đầy đủ.

**East–west:** app server gọi API nội bộ, service mesh giao tiếp giữa microservice, worker truy cập DB. Các luồng này có thể **không đi qua WAF tại biên Internet**; cần API auth, host firewall, service mesh policy, mTLS, microsegmentation và giám sát thích hợp. Nếu muốn kiểm soát L7 trong mạng nội bộ, cần xác định một điểm thực thi riêng.

### Cẩn trọng với quản trị và phụ thuộc

WAF cũng là tài sản trọng yếu: tài khoản quản trị cloud/WAF, khóa API, certificate, policy update và quyền tắt rule đều phải được bảo vệ bằng IAM, MFA, phân quyền, audit log và quy trình thay đổi. Nếu kẻ tấn công có quyền quản trị WAF, họ có thể sửa chính sách hoặc tạo đường bỏ qua.

## 13. Thiết kế logging và giám sát cho WAF

Một WAF đưa ra nhiều tín hiệu, nhưng **có log không có nghĩa đã phát hiện hay xử lý được sự cố**. Cần liên kết event với dữ liệu ứng dụng, identity và network.

### 13.1. Trường log quan trọng

| Trường | Giá trị điều tra |
|---|---|
| Timestamp (múi giờ thống nhất) | Xác định thứ tự và tương quan sự kiện |
| Request ID / correlation ID | Nối WAF event với reverse proxy, API và application logs |
| Trusted client IP / nguồn proxy | Khoanh vùng nguồn thực theo chain proxy được tin cậy |
| Host, path, method, response status | Xác định API/endpoint bị tác động |
| Rule ID, rule group, action | Biết policy nào chặn, đếm hoặc thách thức request |
| Anomaly score / matched field nếu hỗ trợ | Phân biệt mẫu nguy cơ và false positive |
| Upstream/origin response, latency | Nhận biết lỗi do WAF, origin hoặc hệ thống phụ thuộc |
| User/session/tenant ID đã được xác minh (khi được phép ghi) | Liên hệ request với danh tính và nghiệp vụ |
| Device/edge/region, policy version | Điều tra chênh lệch khi triển khai nhiều điểm |

**Bảo vệ dữ liệu log:** request có thể mang cookie, Authorization header, dữ liệu cá nhân hoặc secret. Cần **mask/redact**, hạn chế truy cập, thời gian lưu phù hợp và tránh ghi toàn bộ body nhạy cảm chỉ để tăng khả năng quan sát. Không đưa mật khẩu hay token còn hiệu lực vào log.

### 13.2. Những chỉ số nên theo dõi

- Tỷ lệ request **allow/block/challenge/count** theo host, endpoint, rule và thời gian.
- Số request bị rate limit, tăng 403/429 và biến động độ trễ origin.
- False positive từ ticket người dùng, API error rate và so sánh trước/sau thay đổi policy.
- Tỷ lệ ứng dụng/đường public **được bảo vệ bởi WAF**; endpoint chưa đi qua WAF.
- Mức độ bao phủ log, độ trễ gửi log, rủi ro thay đổi rule và ngoại lệ hết hạn.
- Chỉ số abuse theo identity, IP/ASN/địa lý khi phù hợp, tránh suy đoán ác ý chỉ từ một nguồn.

### 13.3. Cảnh báo có ngữ cảnh

Ví dụ SOC thấy số lượng block SQLi tăng trên /v1/orders từ nhiều client. Thay vì chỉ đếm chữ ký, cần đối chiếu **origin access logs**, lỗi ứng dụng, thay đổi release, nguồn client, khả năng bỏ qua WAF và xu hướng traffic. Mục tiêu là xác định hành vi tấn công có tiến triển hay đây là một đợt kiểm thử hoặc false positive sau triển khai.

## 14. Quy trình triển khai an toàn từ monitor đến block

### Bước 1 — Kiểm kê ứng dụng và luồng

Liệt kê host/domain, IP/VIP, các proxy, service, API, phương thức HTTP, Content-Type, upload limit, authentication flow, WebSocket/gRPC/GraphQL nếu có, đường quản trị, client hợp lệ và phụ thuộc DNS/CDN/load balancer.

### Bước 2 — Xác định threat model

Phân tích tài sản và dữ liệu quan trọng, đường vào từ Internet/đối tác/VPN, ranh giới tin cậy, khả năng truy cập trực tiếp origin, kịch bản abuse và giới hạn quan sát của WAF. Xếp ưu tiên theo **mức tác động và khả năng kiểm chứng**, tránh chỉ bật mọi chữ ký mà không hiểu ứng dụng.

### Bước 3 — Thiết kế chính sách

Chọn managed rules, custom rules, positive validation, rate limiting, bot controls và phạm vi endpoint. Gắn rule với owner, lý do, phương thức đo hiệu quả và điều kiện ngoại lệ. Giữ chính sách L3/L4 và origin access độc lập với chính sách WAF.

### Bước 4 — Chạy ở chế độ quan sát

Nếu nền tảng hỗ trợ, bật **monitor/count/detection-only** để đo tỷ lệ match trên traffic hợp lệ trước khi chặn. Kiểm tra sai khác theo môi trường, tenant, quốc gia, phiên, peak traffic và người dùng sử dụng NAT chung.

### Bước 5 — Triển khai chặn chọn lọc

Bật block theo từng nhóm rule/endpoint đã kiểm chứng. Ưu tiên tác động thấp, có kế hoạch rollback và quyền quản trị khẩn cấp được kiểm soát. Với policy bảo vệ endpoint nhạy cảm, thử các trường hợp hợp lệ trước khi áp lên production.

### Bước 6 — Kiểm thử end-to-end

Xác minh **request hợp lệ qua WAF**, **request vi phạm bị xử lý như dự kiến**, origin không thể bị bypass, log/alert được gửi và downstream ứng dụng không bị lỗi. Với ứng dụng streaming, file upload và API đặc biệt, phải kiểm tra theo protocol thực tế.

### Bước 7 — Theo dõi và rà soát

Theo dõi 403/429, độ trễ, cache hit, request errors, false positive và thay đổi của API. Rà soát khi phát hành chức năng mới, thay proxy/CDN, đổi TLS, thay origin, xuất hiện kịch bản khai thác liên quan hoặc khi phát hiện sensor/log thiếu dữ liệu.

~~~mermaid
flowchart LR
    A[Inventory và API contract] --> B[Threat model / baseline]
    B --> C[Thiết kế managed và custom rules]
    C --> D[Monitor / Count]
    D --> E[Tune false positive]
    E --> F[Block chọn lọc]
    F --> G[Test allow / deny / bypass]
    G --> H[Monitor và cải tiến]
    H --> B
~~~

## 15. Ma trận kiểm thử WAF

Kiểm thử phải có **trường hợp hợp lệ** lẫn **trường hợp không hợp lệ**, quan sát nhiều lớp để tránh nhầm lỗi ứng dụng với lỗi WAF. Tất cả kiểm thử phải diễn ra trên endpoint/môi trường được phép, với dữ liệu tổng hợp không nhạy cảm.

| Test | Kịch bản | Kết quả dự kiến | Bằng chứng |
|---|---|---|---|
| T-01 | User hợp lệ GET trang web qua HTTPS | Thành công theo ứng dụng | HTTP status, WAF allow, origin access log |
| T-02 | API gửi JSON đúng schema và quyền hợp lệ | API trả kết quả đúng | Request ID, application log, không có WAF block |
| T-03 | Method không hỗ trợ trên endpoint cố định | Bị từ chối theo contract (WAF hoặc app/gateway) | HTTP status, policy ID nếu WAF xử lý |
| T-04 | Body vượt giới hạn của endpoint thử nghiệm | Chặn hoặc trả lỗi có kiểm soát theo chính sách | Rule match/limit log, không gây cạn tài nguyên |
| T-05 | Mẫu request giả lập do nhóm kiểm thử xác nhận sẽ khớp rule phòng vệ | Chặn/challenge/monitor theo policy đã đăng ký | WAF event và correlation ID |
| T-06 | Người dùng tải lên nội dung hợp lệ nhưng dễ gây false positive | Không bị chặn sai sau tuning | Log matched field và kết quả sử dụng |
| T-07 | Client vượt quota thử nghiệm trên endpoint riêng | 429/challenge theo cấu hình | Rate metric, trạng thái client, hệ thống không suy giảm |
| T-08 | Nhiều user hợp lệ dùng chung NAT | Không bị chặn hàng loạt vô cớ | Metrics theo identity, IP và feedback |
| T-09 | Client từ Internet cố truy cập origin trực tiếp theo kịch bản được phê duyệt | Bị chặn bởi network/origin policy | Network deny, origin log và kết quả kết nối |
| T-10 | Ứng dụng mới dùng WebSocket/gRPC nếu có | Không lỗi giao thức; mức bảo vệ được hiểu rõ | Handshake, dữ liệu ứng dụng, log WAF và origin |
| T-11 | Thay rule trong lúc có phiên/traffic thực | Hoạt động theo kế hoạch triển khai và rollback | Policy version, error rate, latency, log |

### 15.1. Lệnh kiểm tra cơ bản

Các lệnh dưới đây chỉ **xem hành vi HTTP thông thường**, chưa đủ để chứng minh WAF chặn khai thác. Hãy thay URL bằng môi trường bạn được quyền kiểm thử.

~~~bash
# Quan sát response status và header HTTP
curl -sS -i https://app.example.com/

# Kiểm tra API với JSON hợp lệ theo contract minh họa
curl -sS -i -X POST https://api.example.com/v1/orders \
  -H 'Content-Type: application/json' \
  --data '{"productId":"example","quantity":1}'

# Xác nhận API xử lý method không hỗ trợ theo contract
curl -sS -i -X TRACE https://api.example.com/v1/orders

# Đo tổng thời gian và mã phản hồi để so trước/sau rollout
curl -sS -o /dev/null -w 'status=%{http_code} total=%{time_total}\n' \
  https://app.example.com/
~~~

Trên môi trường thật, không chạy request tạo đơn hàng nếu chưa xác nhận API thử nghiệm và dữ liệu an toàn. Với các endpoint thay đổi trạng thái, sử dụng **staging/sandbox** hoặc request test đã được ứng dụng hỗ trợ.

### 15.2. Phân biệt lỗi và vị trí phát sinh

HTTP **403** có thể do WAF, API gateway hoặc ứng dụng trả về; **429** có thể do WAF, gateway, service hoặc reverse proxy. **502/504** có thể do kết nối origin, timeout hoặc proxy. Cần so **request ID**, thời gian, rule log, upstream status và backend log để xác định thành phần tạo lỗi, thay vì đoán chỉ từ status.

## 16. Tình huống vận hành

### Tình huống A — WAF chặn nhầm API sau phiên bản mới

**Hiện tượng:** Sau khi API bổ sung trường JSON chứa nội dung văn bản tự do, nhiều request hợp lệ trả 403.

**Phân tích:** Xem rule ID, trường JSON bị match, mode chặn, thời điểm triển khai và log ứng dụng. Có thể chuỗi văn bản hợp lệ bị signature nhận là payload nguy hiểm. Giải pháp là làm rõ API contract, tuning/exception hẹp cho đúng trường và endpoint, kiểm thử lại với dữ liệu thật đã loại bỏ bí mật. Không nên tắt toàn bộ nhóm managed rules để giải quyết một false positive.

### Tình huống B — Website đã bật WAF nhưng bot vẫn truy cập backend trực tiếp

**Hiện tượng:** WAF log không ghi nhận traffic, nhưng origin có hàng loạt request bất thường.

**Phân tích:** Có thể origin còn public IP/hostname, cổng mở trực tiếp hoặc luồng đi qua peering/VPN khác. Kiểm tra DNS phụ, route, security group, origin access log và policy xác thực giữa edge-origin. Sửa **đường bypass** trước khi tăng cường chữ ký WAF.

### Tình huống C — Rate limit theo IP ảnh hưởng cả văn phòng

**Hiện tượng:** Sau khi đặt ngưỡng thấp, nhiều nhân viên dùng chung egress NAT nhận 429.

**Phân tích:** Không nhất thiết là tấn công. Kiểm tra nhóm client chung IP, lịch sử request bình thường, endpoint đang chịu tải và khả năng gắn quota với danh tính hợp lệ. Điều chỉnh chính sách theo client identity/tenant/path và mức burst; không chỉ đưa cả IP công ty vào whitelist mọi rule.

### Tình huống D — WAF báo SQL injection nhưng ứng dụng vẫn bị đọc dữ liệu sai quyền

**Hiện tượng:** WAF chặn nhiều request có chữ ký khai thác, nhưng tài khoản hợp lệ vẫn truy cập đơn hàng của tài khoản khác bằng API bình thường.

**Phân tích:** Đây là vấn đề **authorization ở ứng dụng**, không nhất thiết thể hiện qua payload tấn công. Xử lý bằng kiểm tra quyền theo mỗi object, kiểm thử BOLA/IDOR, rà soát API token scope và giám sát truy cập dữ liệu bất thường.

### Tình huống E — Giao thức streaming hoặc upload bị gián đoạn

**Hiện tượng:** HTTP request nhỏ hoạt động, upload file lớn hoặc WebSocket stream lỗi sau khi đưa WAF vào đường đi.

**Phân tích:** Kiểm tra size limit, request buffering, timeout, content parser, WebSocket support, TLS termination và proxy behavior. Điều chỉnh theo endpoint có owner và kiểm thử streaming thực tế; không mặc định request lớn là độc hại.

## 17. Checklist review một application firewall

- [ ] Xác định rõ loại sản phẩm: WAF HTTP, NGFW application-aware, host firewall hay API gateway.
- [ ] Liệt kê ứng dụng, domain, API, phương thức, Content-Type, giao thức đặc biệt và chủ sở hữu.
- [ ] Xác định **đường đi thực tế**, điểm TLS termination và traffic nào WAF thực sự đọc được.
- [ ] Chặn đường bypass origin bằng route, network policy và xác thực edge-origin phù hợp.
- [ ] Xác minh cách lấy **trusted client IP** qua CDN/proxy; không tin header do client tự khai.
- [ ] Dùng managed rules, custom rules, positive validation và rate limit đúng phạm vi.
- [ ] Kiểm soát method, path, body size, schema và API quota theo contract thực tế.
- [ ] Đánh giá khác biệt hỗ trợ HTTP/2, HTTP/3, WebSocket, gRPC, GraphQL và upload/stream.
- [ ] Không thay thế authentication, authorization, input validation hay kiểm thử logic ứng dụng bằng WAF.
- [ ] Kiểm thử false positive/false negative có kiểm soát trước và sau bật block.
- [ ] Gắn exception với rule, endpoint, owner, lý do, thời hạn và bằng chứng test.
- [ ] Theo dõi 403/429, tần suất block, hiệu năng origin, availability và drift chính sách.
- [ ] Bảo vệ log khỏi lộ token, cookie, PII; xác định correlation ID và retention thích hợp.
- [ ] Bảo vệ quyền quản trị WAF, khóa API, certificate, thay đổi policy và lịch sử kiểm toán.
- [ ] Kết hợp segmentation, L3/L4 firewall, VPN, IAM, DNS, IDS/IPS và anti-DDoS theo threat model.
- [ ] Có kế hoạch failover, rollback và kiểm chứng sự cố khi WAF hoặc nhà cung cấp edge gián đoạn.

## 18. Câu hỏi tự kiểm tra

**1. WAF khác firewall L3/L4 như thế nào?**  
Firewall L3/L4 tập trung vào IP, cổng, protocol và trạng thái kết nối; WAF phân tích nội dung/hành vi HTTP khi có thể nhìn thấy request ở lớp ứng dụng.

**2. Vì sao HTTPS pass-through có thể làm WAF thiếu khả năng kiểm tra?**  
Vì payload HTTP vẫn được mã hóa nếu WAF không kết thúc/giải mã TLS hoặc không nhận traffic rõ từ thành phần được tin cậy.

**3. DNS đã trỏ domain qua WAF thì có chắc client không truy cập trực tiếp origin được không?**  
Không. DNS chỉ hỗ trợ định tuyến theo tên miền. Cần policy mạng, origin authentication và kiểm thử các đường khác đến origin.

**4. Một rule WAF chặn SQL injection có giải quyết được IDOR/BOLA không?**  
Không. BOLA/IDOR thường là lỗi kiểm tra quyền theo object; ứng dụng phải xác minh quyền của mỗi yêu cầu, kể cả request HTTP hoàn toàn bình thường.

**5. Vì sao rate limiting theo IP có thể chặn người dùng hợp lệ?**  
Vì nhiều người có thể dùng chung IP NAT, trong khi bot có thể phân tán trên nhiều IP. Cần baseline và tín hiệu danh tính/phiên/đường dẫn phù hợp.

**6. WAF có bảo vệ được database khỏi truy cập trực tiếp qua mạng quản trị không?**  
Không nếu luồng đó không đi qua WAF HTTP. Phân đoạn, L3/L4 firewall, IAM, DB auth và giám sát phải xử lý đường truy cập riêng.

**7. Thấy HTTP 403 có đủ kết luận WAF vừa chặn request không?**  
Chưa. 403 cũng có thể đến từ ứng dụng, gateway hoặc reverse proxy. Cần correlation ID, rule match và log từng lớp.

**8. Khi nào nên chuyển managed rules từ monitor sang block?**  
Sau khi xác minh độ phủ traffic, false positive, ảnh hưởng đến endpoint hợp lệ, đường rollback và các kịch bản test ưu tiên; sau đó giám sát kết quả liên tục.

## 19. Tài liệu tham khảo

- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): nguyên tắc triển khai và quản trị firewall.
- [OWASP Core Rule Set (CRS)](https://coreruleset.org/): bộ luật WAF mã nguồn mở và khái niệm phát hiện dựa trên rule/anomaly score.
- [OWASP Top 10](https://owasp.org/www-project-top-ten/): nhóm rủi ro ứng dụng web cần giải quyết cả ở mã nguồn và kiến trúc.
- [OWASP API Security](https://owasp.org/API-Security/): các nguy cơ bảo mật API như BOLA và abuse cần cơ chế ứng dụng/gateway phù hợp.
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/): yêu cầu kiểm chứng các lớp bảo mật ứng dụng.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): xác thực và kiểm soát truy cập theo danh tính/ngữ cảnh.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): phương thức, trạng thái và ngữ nghĩa HTTP phục vụ phân tích request.

**Ghi nhớ:** Application firewall, đặc biệt WAF, mang thêm **ngữ cảnh HTTP và hành vi ứng dụng** vào quyết định kiểm soát lưu lượng. Giá trị bảo vệ chỉ có khi request đi qua đúng điểm kiểm soát, TLS được xử lý phù hợp, rule bám đúng API contract, đường origin không bị bypass và kết quả được **kiểm thử, giám sát, hiệu chỉnh liên tục** cùng các lớp bảo vệ mạng và ứng dụng.
