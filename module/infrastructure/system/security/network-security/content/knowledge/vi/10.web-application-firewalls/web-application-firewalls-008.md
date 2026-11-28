# Bot và automation control trong Web Application Firewall (WAF)

Một website thương mại điện tử phải phục vụ khách hàng thật, công cụ tìm kiếm, hệ thống giám sát và đối tác tích hợp API. Đồng thời, hệ thống có thể nhận hàng nghìn yêu cầu tự động nhằm thử thông tin đăng nhập, thu thập dữ liệu quá mức, tạo tài khoản rác hoặc chiếm tài nguyên xử lý. Điểm khó không phải là **chặn mọi bot**, mà là **phân biệt hoạt động tự động được cho phép với hành vi lạm dụng**, sau đó áp dụng kiểm soát tương xứng mà không làm hỏng trải nghiệm hợp lệ.

Đó là mục tiêu của **bot và automation control** trong chương **Web application firewall**, thuộc module **SECURITY_NETWORK_SECURITY**. Bài học kết nối WAF ở tầng HTTP/API với xác thực, phân đoạn mạng, firewall, quản lý lưu lượng, IDS/IPS, DNS, hạ tầng đám mây và giám sát xâm nhập. Trọng tâm là thiết kế chính sách có thể kiểm chứng, nhận biết giới hạn của từng tín hiệu và tránh kết luận rằng một điểm số bot hoặc một lần CAPTCHA đã bảo vệ hoàn toàn ứng dụng.

## 1. Bot, automation và lạm dụng tự động là gì?

**Bot** là phần mềm tự động gửi yêu cầu hoặc tương tác với dịch vụ. **Automation** chỉ cách thực hiện công việc bằng chương trình, không mặc định mang ý nghĩa độc hại. Điều cần đánh giá là **quyền, mục đích, phương thức, tần suất và tác động** của hoạt động đó đối với tài nguyên.

| Nhóm hoạt động | Ví dụ | Hướng xử lý |
|---|---|---|
| **Bot hợp lệ công khai** | Crawler của công cụ tìm kiếm, trình đọc nguồn cấp dữ liệu theo chính sách | Nhận diện có căn cứ, cung cấp phạm vi truy cập phù hợp, giám sát tải |
| **Automation có hợp đồng** | Đối tác đồng bộ đơn hàng qua API, hệ thống webhook | Xác thực API key/OAuth/mTLS khi thích hợp, quota và lịch sử truy cập |
| **Automation nội bộ** | Health check, synthetic monitoring, kiểm thử định kỳ, job CI/CD | Danh tính riêng, phạm vi tối thiểu, tránh nhầm với người dùng thật |
| **Lạm dụng đăng nhập/tài khoản** | Thử mật khẩu tự động, sử dụng cặp thông tin rò rỉ, tạo tài khoản giả | Kiểm soát theo tài khoản và ngữ cảnh, MFA, phát hiện bất thường |
| **Lạm dụng nội dung/kinh doanh** | Thu thập dữ liệu quá mức, giữ hàng ảo, thao túng chức năng đặt chỗ | Quota theo chủ thể, kiểm soát giao dịch, xác minh nghiệp vụ |
| **Lạm dụng tài nguyên** | Gửi nhiều yêu cầu tốn CPU/DB hoặc làm cạn quota | Rate limit, concurrency limit, cache/queue, bảo vệ upstream |

Việc một request do script thực hiện **không đủ để kết luận vi phạm chính sách**. Cần xét quyền hợp pháp và bối cảnh nghiệp vụ. Ngược lại, một trình duyệt thật hoặc phiên đăng nhập hợp lệ vẫn có thể được dùng để thực hiện hành vi lạm dụng.

### 1.1. WAF khác gì firewall mạng và hệ thống chống DDoS?

| Thành phần | Tín hiệu/điểm thực thi thường gặp | Vai trò chính |
|---|---|---|
| **Firewall L3/L4** | IP, port, protocol, zone, trạng thái phiên | Giới hạn đường kết nối giữa các mạng/dịch vụ |
| **WAF L7** | HTTP method, URI, header, cookie, body trong phạm vi có thể kiểm tra, ngữ cảnh request | Chặn/lọc yêu cầu web và thực thi chính sách HTTP/API |
| **Bot management** | Tần suất, hành vi, dấu hiệu client, danh tính, tín hiệu rủi ro | Phân loại và điều tiết automation, thường tích hợp với WAF/CDN |
| **DDoS protection** | Băng thông, packet/connection rate, lưu lượng phân tán, sức chịu tải | Giảm tác động làm quá tải ở các lớp khác nhau |
| **API gateway** | Route, identity, API key, quota, schema, quyền truy cập tùy giải pháp | Quản lý hợp đồng và khả năng truy cập API |
| **Ứng dụng/IdP** | Tài khoản, session, MFA, quyền nghiệp vụ, giao dịch | Quyết định ai được làm gì và bảo vệ dữ liệu |

Các lớp có thể trùng chức năng; không nên giả định mọi WAF đều hỗ trợ thiết bị fingerprinting, kiểm soát API hay chống DDoS L3/L4. WAF nhìn được nội dung HTTPS khi nằm ở điểm **kết thúc/giải mã TLS có quyền kiểm tra**, không thể mặc nhiên phân tích mọi kết nối TLS pass-through.

## 2. Các kịch bản đe dọa cần nhận diện

| Kịch bản | Mục tiêu thường gặp | Tín hiệu gợi ý | Điểm phòng vệ ngoài WAF |
|---|---|---|---|
| **Credential stuffing** | Dùng thông tin đăng nhập bị lộ để truy cập tài khoản | Nhiều lỗi đăng nhập phân tán, mẫu truy cập bất thường | MFA, kiểm tra mật khẩu bị lộ, phát hiện chiếm tài khoản |
| **Password guessing** | Thử mật khẩu trên một hoặc nhiều tài khoản | Tỷ lệ lỗi cao, nhiều biến thể tài khoản/nguồn | Rate limit theo tài khoản và nguồn, chống brute force |
| **Account enumeration** | Suy ra tài khoản nào tồn tại | Khác biệt response/timing, nhiều lần kiểm tra email | Thông báo trung tính, hạn chế khả năng phân biệt |
| **Fake account creation** | Tạo nhiều tài khoản hoặc tài nguyên giả | Tăng đột biến đăng ký, mẫu hành vi lặp | Xác minh đăng ký, quota, chống lạm dụng nghiệp vụ |
| **Scraping quá mức** | Thu thập dữ liệu hoặc tiêu thụ năng lực hệ thống | Nhiều trang sản phẩm, thứ tự truy cập bất thường | Quy định sử dụng, phân quyền dữ liệu, giới hạn danh mục |
| **Inventory hoarding / scalping** | Giữ hoặc mua số lượng bất thường | Nhiều lượt giữ chỗ, tỷ lệ hoàn tất thấp | Quota theo người dùng và chính sách đặt hàng |
| **Card testing** | Thử tính hợp lệ của dữ liệu thanh toán | Nhiều giao dịch nhỏ/thất bại liên tiếp | Chống gian lận từ PSP, tokenization, quy tắc nghiệp vụ |
| **L7 resource exhaustion** | Làm cạn CPU, worker, DB connection hoặc quota | Tăng request tới endpoint tốn tài nguyên, độ trễ tăng | Quota/concurrency, cache, timeout, autoscaling và bảo vệ DB |

Các chỉ báo chỉ là **dấu hiệu cần điều tra**, không phải bằng chứng đơn lẻ về ý định hoặc danh tính. Chẳng hạn nhiều request từ một IP có thể xuất phát từ văn phòng sử dụng NAT, còn một cuộc tấn công phân tán có thể dùng nhiều IP với tốc độ thấp trên mỗi nguồn.

## 3. Kiến trúc kiểm soát automation

Giả sử ứng dụng có CDN/WAF phía trước API gateway và dịch vụ backend:

~~~mermaid
flowchart LR
    subgraph OUT["Nguồn truy cập bên ngoài"]
        U["Trình duyệt / Mobile / Partner / Bot"]
    end
    subgraph EDGE["TB1: Edge / WAF / CDN"]
        W["Phân loại và kiểm soát HTTP"]
        R["Rate limit / Challenge / Block"]
        W --> R
    end
    subgraph APP["TB2: API và danh tính"]
        G["API gateway / AuthN"]
        A["Ứng dụng / AuthZ / Quota"]
        G --> A
    end
    subgraph DATA["TB3: Backend và quan sát"]
        D[("Database / Queue / Cache")]
        L[("Log / Metrics / Alerts")]
    end
    U -->|"HTTPS request"| W
    R -->|"Yêu cầu được phép"| G
    A -->|"Luồng nghiệp vụ được cấp quyền"| D
    W -.->|"Bot signal / action / request ID"| L
    G -.->|"Identity và HTTP status đã lọc"| L
    A -.->|"Kết quả giao dịch / lỗi / latency"| L
~~~

**TB1** đánh dấu ranh giới từ Internet tới điểm kiểm soát. **TB2** là nơi thông tin nguồn gốc cần được xác minh trước khi ứng dụng tin cậy; **TB3** là ranh giới của tài nguyên nhạy cảm. Bot management ở edge **không thay** phân quyền ứng dụng. API phải tiếp tục kiểm tra quyền thao tác và giới hạn tài nguyên ngay cả khi WAF cho phép request.

### 3.1. Ba đường dễ bị bỏ sót

1. **Origin bypass:** nếu backend vẫn có public endpoint cho phép kết nối trực tiếp, traffic có thể không đi qua WAF. Cần giới hạn nguồn tới origin, dùng xác thực kết nối và kiểm tra routing/DNS được phê duyệt.
2. **Endpoint khác:** một số API, ứng dụng di động, WebSocket/gRPC, cổng quản trị hoặc vùng staging có thể đi qua chuỗi kiểm soát khác. Kiểm tra rõ WAF có quan sát/điều tiết đúng loại traffic của từng tuyến không.
3. **Traffic nội bộ và đối tác:** webhook, monitoring, batch job và service-to-service call có thể không có JavaScript/cookie như browser; không nên dùng cùng challenge mà không xét danh tính và hợp đồng API.

TLS termination, CDN caching, reverse proxy, load balancer và chính sách egress quyết định tín hiệu nào còn hiện diện ở mỗi hop. Header địa chỉ nguồn như `X-Forwarded-For` chỉ đáng tin khi được **điểm proxy được ủy quyền ghi đè/kiểm tra** và ứng dụng chặn truy cập trực tiếp không qua chuỗi tin cậy.

## 4. Tín hiệu phân loại bot và giới hạn của chúng

Không có một thuộc tính client nào là “bằng chứng tuyệt đối rằng đây là bot”. Cách phân loại thực tế thường tổng hợp nhiều tín hiệu.

| Nhóm tín hiệu | Có thể cung cấp | Giới hạn và rủi ro sai |
|---|---|---|
| **IP và mạng nguồn** | Reputation, ASN, geo thô, số lần truy cập | NAT, VPN, mạng di động và IP thay đổi; không chứng minh danh tính |
| **HTTP metadata** | User-Agent, method, header, cookie, session continuity | Có thể thay đổi/giả mạo; trình duyệt cũng khác nhau |
| **Tần suất và phân bố** | Request/giây, burst, số endpoint, lỗi 4xx/5xx | Sale lớn, retry lỗi và cache miss có thể tạo mẫu tương tự |
| **Dấu hiệu client** | TLS/HTTP fingerprint, khả năng chạy JavaScript, tính nhất quán client | Trình duyệt cập nhật, thiết bị hỗ trợ tiếp cận, mobile SDK hoặc proxy có thể bị phân loại sai |
| **Danh tính đã xác thực** | User ID, API key, OAuth client, workload identity | Credential có thể bị chiếm hoặc chia sẻ; cần quyền và quota |
| **Hành vi nghiệp vụ** | Nhiều lần tìm kiếm/giữ hàng, tỉ lệ đăng nhập thất bại, tỉ lệ thanh toán lỗi | Phụ thuộc luồng kinh doanh; cần tránh đưa ra quyết định từ hành vi đơn lẻ |
| **Lịch sử và threat intel** | Bot score, kết quả challenge trước, nguồn bị báo cáo lạm dụng | Score có sai số, có độ trễ và khác ngữ nghĩa theo nhà cung cấp |

**User-Agent** chỉ là dữ liệu do client khai báo; không xác minh một crawler chính hãng bằng cách so sánh duy nhất chuỗi tên bot. Nếu cần danh sách bot hợp lệ, sử dụng cơ chế xác minh của nhà cung cấp/crawler, danh sách nguồn đáng tin được duy trì và quy trình quản lý thay đổi.

**robots.txt** hướng dẫn crawler tự nguyện tuân thủ quy tắc crawl; nó **không phải kiểm soát truy cập** và không bảo vệ dữ liệu bí mật. Nội dung cần bảo vệ phải dùng authentication, authorization và chính sách dữ liệu phù hợp.

### 4.1. Đánh giá mức độ tự tin thay vì quyết định một-bit

Một chiến lược tốt không gán nhãn “bot hay người” rồi chặn tất cả bot. Thay vào đó, có thể đánh giá:

- **Được xác minh và được phép:** crawler hợp lệ hoặc đối tác có credential, phạm vi và quota cụ thể.
- **Chưa đủ thông tin:** tiếp tục giám sát, đặt rate limit hợp lý hoặc yêu cầu bước xác minh tương thích.
- **Có dấu hiệu lạm dụng:** thắt quota, yêu cầu xác thực mạnh hơn hoặc hạn chế hành động nhạy cảm.
- **Vi phạm chính sách đã xác nhận:** chặn đúng phạm vi và ghi đủ bằng chứng để điều tra.

Điểm bot score có thể dùng như **một tín hiệu trong chính sách**, không nên là nguồn ra quyết định duy nhất cho đăng nhập, thanh toán hoặc quyền truy cập dữ liệu.

## 5. Rate limiting: kiểm soát cơ bản nhưng cần thiết kế đúng

**Rate limiting** giới hạn số request/hoạt động trong một khoảng thời gian hoặc theo khả năng xử lý. Nó có thể áp theo:

- IP nguồn đã xác minh ở chuỗi proxy.
- Tài khoản hoặc phiên đã xác thực.
- API key/OAuth client/tenant/workload identity.
- Endpoint hoặc nhóm endpoint, ví dụ login, search, checkout, export.
- Tổ hợp nguồn + tài khoản + hành động, kết hợp quota toàn hệ thống.

Chỉ dựa vào **IP** dễ ảnh hưởng nhiều người dùng hợp lệ dùng chung NAT; chỉ dựa vào **tài khoản** có thể không bảo vệ endpoint chưa đăng nhập và có nguy cơ bị lợi dụng để làm khóa tài khoản. Cần giới hạn nhiều cấp và lựa chọn phản hồi phù hợp.

### 5.1. Các thuật toán thường gặp

| Thuật toán | Ý tưởng | Ưu điểm | Hạn chế cần xét |
|---|---|---|---|
| **Fixed window** | Đếm số lượt trong từng cửa sổ cố định | Đơn giản, chi phí thấp | Burst có thể dồn ở ranh giới hai cửa sổ |
| **Sliding window** | Tính số lượt trong cửa sổ trượt hoặc xấp xỉ | Công bằng hơn quanh ranh giới thời gian | Tốn trạng thái hoặc cần cách xấp xỉ |
| **Token bucket** | Token được nạp lại theo tốc độ, mỗi request tiêu hao token | Cho phép burst ngắn nhưng giữ tốc độ dài hạn | Cần cấu hình dung lượng bucket và tốc độ refill hợp lý |
| **Leaky bucket/queue** | Làm phẳng tốc độ xử lý theo hàng đợi hoặc lịch thoát | Giảm burst tới backend | Hàng đợi có giới hạn, tăng latency hoặc phải từ chối khi quá tải |
| **Concurrency limit** | Giới hạn số tác vụ đang xử lý cùng lúc | Phù hợp endpoint tốn CPU/DB | Không trực tiếp giới hạn số lượt dài hạn |

Với token bucket, đặt sức chứa `B`, tốc độ nạp `r` token/giây, số token hiện có `T`, và thời gian `Δt` kể từ cập nhật gần nhất:

\[
T_{\mathrm{new}} = \min(B, T + r \times \Delta t).
\]

Nếu lượng token sau nạp lại **ít nhất bằng một**, trừ một token và cho phép request; nếu không, từ chối/hoãn theo chính sách. Giả sử `B=10`, `r=1` token/giây và một client sử dụng hết 10 token, sau hai giây hệ thống có thể nạp lại tối đa hai token (nếu không có request khác). **Sức chứa bucket không có nghĩa được cấp thêm 10 token mỗi giây**.

Đó là mô hình đơn giản, không xét trọng số cho những thao tác tốn tài nguyên khác nhau. Với API export hoặc query phức tạp, có thể phân bổ **cost** theo hành động, hoặc kết hợp quota/concurrency riêng.

### 5.2. Rate limit nhiều tầng để tránh bỏ sót

Ví dụ logic phòng vệ đăng nhập:

| Phạm vi | Điều kiện mẫu cần hiệu chỉnh | Mục đích |
|---|---|---|
| **Per source** | Giới hạn tốc độ yêu cầu tới nhóm endpoint xác thực | Chống burst từ một nguồn và giảm quá tải |
| **Per account** | Giám sát thất bại của từng tài khoản qua nhiều nguồn | Nhìn thấy hành vi phân tán |
| **Per source + account** | Giới hạn lặp lại cùng cặp nguồn–tài khoản | Bảo vệ tài khoản mà ít ảnh hưởng người dùng khác |
| **Per session / device** | Giới hạn thao tác có thể tạo nhiều chi phí | Giảm lạm dụng sau đăng nhập |
| **Global** | Giới hạn concurrency/tải tới dịch vụ auth hoặc database | Bảo vệ tài nguyên dùng chung |

Ngưỡng cụ thể phụ thuộc số lượng người dùng, đường truy cập, NAT, SLA, mức rủi ro và dữ liệu thực tế. Không có “5 lần đăng nhập/phút” áp dụng đúng cho mọi dịch vụ. Tránh khóa cứng tài khoản chỉ vì một người ngoài gửi nhiều lỗi đăng nhập đến tên người dùng của nạn nhân; điều đó có thể biến bộ lọc thành công cụ gây từ chối dịch vụ.

### 5.3. HTTP response khi vượt giới hạn

Ví dụ một API trả:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30
Cache-Control: no-store

{"error":"rate_limit_exceeded","requestId":"req-example-42"}
~~~

`429` cho biết yêu cầu đã bị giới hạn vì quá nhiều lượt. `Retry-After: 30` biểu diễn gợi ý chờ 30 giây trong ví dụ; không có yêu cầu rằng mọi WAF đều phải trả header này. Client hợp lệ nên áp **exponential backoff với jitter**, tránh retry đồng loạt; các giới hạn khác như payload hoặc concurrency có thể dùng hành động/status riêng theo thiết kế.

WAF/CDN có thể trả response trực tiếp mà backend không nhận request. Vì vậy cần truyền **request ID và action reason** qua telemetry phù hợp để phân biệt 429 ở edge với 429 do ứng dụng tự tạo.

### 5.4. Giới hạn khi triển khai phân tán

Nhiều instance WAF có thể có **counter cục bộ**, dẫn tới mức giới hạn thực tế cao hơn kỳ vọng nếu traffic được chia đều. Nếu cần hạn mức toàn cục, phải có cơ chế shared state/phân phối counter mà nền tảng hỗ trợ, đồng thời tính đến độ trễ, sai lệch đồng hồ, failover và mất liên lạc.

Một reverse proxy đứng sau CDN có thể nhìn mọi request đến từ IP của CDN. Nếu lấy IP nguồn sai, hệ thống sẽ áp giới hạn chung cho toàn bộ người dùng. Chỉ sử dụng `X-Forwarded-For` hoặc thông tin “real client IP” khi có **trusted proxy chain** rõ ràng và chặn việc client tự giả mạo header.

## 6. Hành động giảm thiểu theo mức độ rủi ro

| Hành động | Khi nào phù hợp | Giới hạn và lưu ý |
|---|---|---|
| **Allow + log** | Bot hợp lệ hoặc đang tìm hiểu hành vi | Phải có quan sát và giới hạn tối thiểu với endpoint đắt |
| **Rate limit / throttle** | Tần suất vượt nhu cầu nhưng chưa đủ căn cứ chặn toàn bộ | Cần nhiều khóa, quota hợp lý, xử lý retry |
| **Challenge tương tác** | Yêu cầu browser có mức rủi ro trung bình và client hỗ trợ | Gây ma sát; JavaScript, cookie, mobile API và công cụ hỗ trợ tiếp cận có thể gặp khó khăn |
| **CAPTCHA** | Một số bước nhạy cảm khi có dấu hiệu đáng kể | Không phải chứng minh danh tính tuyệt đối; ảnh hưởng accessibility và quyền riêng tư |
| **Step-up authentication** | Thao tác rủi ro cao, đăng nhập bất thường, thay thông tin nhạy cảm | Dựa vào IdP/MFA, không dùng WAF thay quy trình xác thực |
| **Block/deny** | Vi phạm rõ policy, nguồn được xác minh gây hại hoặc vượt kiểm soát nghiêm trọng | Phải có khả năng điều tra, xử lý false positive và rollback |
| **Queue / concurrency control** | Tác vụ tốn tài nguyên, export, report, tìm kiếm phức tạp | Cần giới hạn hàng đợi, timeout và thông báo phù hợp |

Một WAF không thể mặc định chèn CAPTCHA vào **mọi API client** mà không phá tích hợp: nhiều mobile app, webhook, CLI hoặc service account không thực hiện JavaScript/cookie challenge. Với API, ưu tiên danh tính ứng dụng, quota theo credential, schema validation, throttling, quyền chức năng và hợp đồng tích hợp.

### 6.1. Challenge không thể thay xác thực

CAPTCHA/JavaScript challenge nhằm tăng độ khó của một lớp automation cụ thể, không đảm bảo “đây là con người thật” và không thay thế authentication, authorization hay MFA. Một client vượt qua challenge vẫn có thể gửi request trái quyền nếu API có lỗi phân quyền.

Thiết kế nên có cách phục vụ người dùng cần hỗ trợ tiếp cận, thiết bị không chạy JavaScript và trường hợp có đánh giá sai. Không phân loại người dùng theo địa lý/IP đơn lẻ để dẫn đến chặn không có cơ chế khiếu nại hoặc thay thế.

### 6.2. Không dùng allowlist quá rộng

Đối tác có thể có IP tĩnh, nhưng allowlist IP **không tự xác thực** ứng dụng hay quyền với API. Nếu đặt rule “bypass toàn bộ WAF” cho cả CIDR rộng, những request ngoài mục đích cũng có thể bỏ qua lớp bảo vệ. Ưu tiên exception hẹp theo **identity đáng tin, route, action và thời hạn**, vẫn duy trì log và quota.

## 7. Chính sách theo hành trình người dùng

### 7.1. Đăng nhập và khôi phục tài khoản

Đây là bề mặt nhạy cảm vì một kẻ tấn công có thể dùng nhiều IP và nhiều tài khoản; đồng thời người dùng thật thường quên mật khẩu. Bộ kiểm soát nên bao gồm:

1. Quota theo nguồn **và** theo tài khoản, quan sát thất bại xuyên nguồn.
2. MFA/step-up khi có tín hiệu rủi ro; phát hiện đăng nhập thành công bất thường sau chuỗi thất bại.
3. Thông báo lỗi trung tính, tránh tiết lộ tài khoản tồn tại; log chi tiết an toàn ở phía backend.
4. Quản lý phiên, rotation/thu hồi token, bảo vệ reset password và chống replay theo thiết kế.
5. Kênh hỗ trợ người dùng hợp lệ bị chặn nhầm, đặc biệt qua mạng NAT doanh nghiệp.

WAF nên cung cấp tín hiệu và giới hạn tải, còn **IdP/ứng dụng** mới quyết định quyền xác thực và vòng đời tài khoản.

### 7.2. Tìm kiếm, danh mục và dữ liệu công khai

Không phải mọi lượt crawl đều có hại. Một công cụ tìm kiếm được cấp quyền có thể cần truy cập nhiều tài nguyên; trái lại việc crawl toàn bộ dataset có thể vượt chính sách hoặc gây quá tải.

Nên định nghĩa rõ dữ liệu nào được công khai, phạm vi được phép, quota cho API hoặc crawler, điều kiện sử dụng và caching. Nếu backend có tìm kiếm tốn tài nguyên, cân nhắc giới hạn concurrency, cache theo query, paging và kích thước phản hồi. **Không dùng WAF để thay quyết định rằng một trường dữ liệu nhạy cảm có nên xuất hiện công khai hay không.**

### 7.3. API đối tác, mobile và webhook

Đặt hợp đồng riêng cho:

| Loại client | Danh tính/điểm nhận diện đáng tin | Kiểm soát ưu tiên |
|---|---|---|
| API đối tác | API key, OAuth client, chữ ký request hoặc mTLS nếu thiết kế hỗ trợ | Quota theo credential/tenant, schema, phân quyền, rotation |
| Mobile application | Phiên người dùng, access token, thiết bị có thể được đánh giá theo mức rủi ro | Quota theo user/session, bảo vệ API, hạn chế phụ thuộc JavaScript challenge |
| Webhook đến | Chữ ký và timestamp/nonce theo hợp đồng provider | Xác minh nguồn/secret, chống replay, queue, quota và phân quyền |
| Monitoring/health check | Danh tính riêng và endpoint chuyên dụng | Allowlist hẹp hoặc identity, loại khỏi challenge không tương thích, giám sát |
| Crawler hợp lệ | Cơ chế xác minh crawler theo tài liệu chính thức và policy nội bộ | Giới hạn crawl hợp lý, tránh bypass rộng, quan sát lỗi |

Secret/API key bị đánh cắp vẫn có thể được dùng để gửi yêu cầu ở phạm vi hợp lệ; vì vậy phải áp least privilege, thời hạn, quota, audit và khả năng thu hồi.

### 7.4. Tác vụ nghiệp vụ dễ bị lạm dụng

Checkout, tạo mã giảm giá, gửi OTP, thử phương thức thanh toán, giữ chỗ và xuất báo cáo có thể cần kiểm soát theo **đối tượng nghiệp vụ** bên cạnh request rate. Chẳng hạn hạn mức “bao nhiêu lần gửi OTP cho một số điện thoại trong kỳ” phải thực thi ở dịch vụ nghiệp vụ; WAF không nhất thiết biết số điện thoại đã xác minh hoặc trạng thái giao dịch.

Đối với thao tác ghi, cơ chế **idempotency key**, hạn mức theo tài khoản, quota tài nguyên và kiểm soát gian lận có thể giúp giảm ảnh hưởng retry và automation; chúng không thay quyền thực hiện thao tác.

## 8. Ví dụ đặc tả policy nhiều tầng

Tài liệu sau là **schema minh họa để trao đổi yêu cầu**, không phải cấu hình có thể áp trực tiếp lên một sản phẩm WAF:

~~~yaml
policyId: WAF-AUTOMATION-LOGIN-001
scope:
  paths:
    - /api/auth/login
    - /api/auth/reset-password
  methods:
    - POST
objectives:
  - Bảo vệ năng lực dịch vụ xác thực
  - Phát hiện tăng bất thường lỗi đăng nhập
  - Giảm ảnh hưởng người dùng hợp lệ dùng chung NAT
controls:
  sourceRateLimit:
    key: verified_client_ip
    threshold: calibrated_from_baseline
  accountAbuseDetection:
    key: hashed_account_identifier
    signals:
      - failed_authentication_rate
      - distinct_sources_per_account
  sessionQuotas:
    key: authenticated_identity_when_available
  globalConcurrency:
    key: authentication_backend
    threshold: derived_from_capacity_test
  response:
    rateLimitedStatus: 429
    requestId: required
    safeErrorBody: true
exceptions:
  - Dịch vụ giám sát có danh tính riêng, scope hẹp, có audit
observability:
  - action
  - policy_id
  - request_id
  - timestamp
  - route
  - source_classification
owner: platform-security-and-auth-team
~~~

Điểm cần chú ý: `verified_client_ip` phải dựa vào proxy chain đáng tin; `hashed_account_identifier` chỉ là khóa nhóm sự kiện phục vụ giám sát, không phải phương pháp xác thực. Giá trị ngưỡng cần lấy từ **baseline và kiểm thử tải thực tế**, không phải một con số phổ quát.

### 8.1. Ví dụ Nginx giới hạn tốc độ theo IP tại một lớp edge

Nginx có cơ chế giới hạn tốc độ dựa vào shared memory zone (trên **một instance Nginx**). Ví dụ bên dưới chỉ minh họa cấu hình cho endpoint login trên **dịch vụ tự quản lý**:

~~~nginx
http {
    upstream auth_backend {
        server 127.0.0.1:9000;  # Backend thử nghiệm do bạn quản lý
    }

    limit_req_zone $binary_remote_addr zone=login_ip:10m rate=10r/m;

    server {
        listen 8080;

        location = /api/auth/login {
            limit_req zone=login_ip burst=5 nodelay;
            limit_req_status 429;
            proxy_pass http://auth_backend;
        }
    }
}
~~~

- `rate=10r/m` giới hạn tốc độ trung bình theo khóa `$binary_remote_addr`; `burst=5` hỗ trợ một mức burst bổ sung theo thuật toán của Nginx. **Không diễn giải thành “mỗi phút luôn được gửi 15 request tùy ý”**.
- `limit_req_status 429` chọn HTTP 429 khi request bị từ chối do bộ giới hạn này. Ví dụ không tự tạo `Retry-After`, không thiết kế chính sách theo tài khoản và không chống được lạm dụng phân tán.
- Nếu Nginx đứng sau load balancer/CDN, `$remote_addr` có thể là IP proxy. Chỉ cấu hình real client IP khi đã thiết lập **danh sách proxy tin cậy** và bảo vệ origin.
- Bộ đếm trong `login_ip` không mặc định là một quota toàn cầu trên nhiều node/region; phải xác minh kiến trúc phân phối state và chính sách giữa các instance.
- Cổng `127.0.0.1:9000` là upstream minh họa; chỉ hoạt động khi đã có backend do bạn quản lý lắng nghe ở đó. Cần điều chỉnh `listen`, upstream, TLS, đường dẫn và ngưỡng theo ứng dụng thực. Không áp trực tiếp lên production mà chưa kiểm thử với người dùng thật, NAT, retry, giám sát và kịch bản rollback.

WAF chuyên dụng thường có hành động **managed challenge, bot score, rate limiting theo nhiều khóa** và policy cấp cao khác; tên trường/tính năng phụ thuộc sản phẩm. Nếu nền tảng không hỗ trợ một tín hiệu, hãy nêu hạn chế và chuyển kiểm soát đó sang API gateway hoặc ứng dụng.

## 9. Thiết kế telemetry và giám sát

WAF có thể ra quyết định chặn nhưng không tự chứng minh việc chặn là chính xác. Muốn cải thiện policy, cần tương quan quyết định edge với kết quả ứng dụng.

### 9.1. Trường dữ liệu quan sát cần thiết

| Trường | Câu hỏi trả lời | Lưu ý bảo mật |
|---|---|---|
| Timestamp, timezone, edge/region | Sự kiện xảy ra ở đâu và khi nào? | Chuẩn hóa đồng hồ, theo dõi nhiều vùng |
| Request ID/correlation ID | Nối WAF log với API, auth và DB log ra sao? | Không đặt dữ liệu bí mật vào ID |
| Rule/policy ID, action, reason | Rule nào allow, challenge, throttle hoặc block? | Giữ phiên bản cấu hình, độ tin cậy của tín hiệu |
| Route/method/status | Endpoint nào bị ảnh hưởng, lỗi 429/403 phát sinh ở lớp nào? | Hạn chế lưu query string chứa PII/token |
| Source IP/ASN (khi phù hợp) | Nguồn và mạng nào có xu hướng bất thường? | Áp retention, phân quyền và chuẩn riêng tư |
| Identity/tenant đã xác minh | Lạm dụng phân tán trên một chủ thể hay nhiều chủ thể? | Không log raw token, password, API key |
| Auth result/business result | Challenge/block có thực sự giảm thất bại/tải/lạm dụng? | Cần correlation và định nghĩa metric thống nhất |
| Latency/CPU/DB saturation | Chính sách có bảo vệ backend? | Theo dõi cả ảnh hưởng từ retry/caching |

Đặt cảnh báo theo **tỷ lệ và baseline**, không chỉ số request tuyệt đối: ví dụ `rate_limited / total_requests` theo route và tenant, tỷ lệ lỗi đăng nhập, p95/p99 latency, tải backend, số người dùng hợp lệ bị challenge thất bại, mức độ lệch theo vùng.

### 9.2. False positive và false negative

- **False positive:** request hợp lệ bị phân loại là bot lạm dụng và bị chặn/challenge không cần thiết.
- **False negative:** automation gây hại đi qua mà không bị phát hiện/chặn.

Hai loại lỗi đều tốn chi phí: chặn nhầm ảnh hưởng doanh thu, accessibility và SLA; bỏ sót làm tăng gian lận, rò rỉ hoặc tải backend. Khi phân tích phải dùng **tập dữ liệu có nhãn đáng tin** hoặc điều tra thực tế, không tính accuracy chỉ bằng số lượng request bị chặn.

Ví dụ một công ty có hàng trăm nhân viên dùng chung IP NAT. Đặt rate limit thấp theo IP ở `/login` có thể chặn cả công ty khi bắt đầu giờ làm. Giải pháp không phải mở toàn bộ endpoint, mà là bổ sung quota theo tài khoản, xác minh nguồn, điều chỉnh mức giới hạn và dùng cơ chế phản hồi hợp lý.

### 9.3. Không để chính việc giám sát tạo rò rỉ

Request header/body có thể chứa `Authorization`, cookie, session ID, mật khẩu hoặc dữ liệu thanh toán. Không xuất toàn bộ payload vào kho log chỉ để điều tra bot. Sử dụng **redaction, phân quyền, thời hạn lưu, pseudonymization khi phù hợp** và quy trình truy cập log có audit.

## 10. Quy trình triển khai từ quan sát đến chặn

~~~mermaid
flowchart TD
    A["Kiểm kê endpoint và client hợp lệ"] --> B["Thiết lập baseline traffic, lỗi và tải"]
    B --> C["Rule theo route + identity + rate trong chế độ observe"]
    C --> D{"Có bằng chứng và kiểm tra false positive?"}
    D -->|"Chưa"| E["Điều chỉnh scope/ngưỡng, thu thêm dữ liệu"]
    E --> C
    D -->|"Có"| F["Áp throttle/challenge có kiểm soát"]
    F --> G["Kiểm tra user, partner, mobile, accessibility"]
    G --> H{"Kết quả và tác động đáp ứng mục tiêu?"}
    H -->|"Không"| I["Rollback hoặc nới có phạm vi; tìm nguyên nhân"]
    H -->|"Có"| J["Chặn có chọn lọc, theo dõi và review định kỳ"]
~~~

### Bước 1 — Lập danh sách endpoint và nhóm client

Phân biệt `/login`, `/register`, `/search`, `/checkout`, `/export`, API đối tác, mobile và webhook. Ghi chủ sở hữu, yêu cầu throughput, loại dữ liệu, độ nhạy cảm và phương thức xác thực. Không lấy ngưỡng trang chủ áp cho một API xuất báo cáo.

### Bước 2 — Thu baseline và mô hình đe dọa

Đo request rate, mức burst, tỷ lệ 4xx/5xx, auth failures, phân bố theo user/tenant, cache hit và tài nguyên backend. Bổ sung các kịch bản: nguồn phân tán, IP NAT, đối tác chạy batch, hệ thống theo lịch, và người dùng có quyền nhưng lạm dụng chức năng.

### Bước 3 — Thiết kế thứ tự xử lý và ngoại lệ

Xác định những rule nào chạy trước, rule nào ghi đè và cách cấu hình **managed rule**, allowlist, rate limit, challenge, block cùng tồn tại. Một exception quá rộng có thể bỏ qua cả quy tắc SQL injection hoặc chính sách auth theo cách riêng của sản phẩm. Chỉ ngoại lệ đúng route, chủ thể, mục đích và thời gian.

### Bước 4 — Triển khai observe / dry-run

Đầu tiên thu số lượng request **sẽ bị** ảnh hưởng, nhóm người dùng/đối tác và lý do. Chạy thử ở staging hoặc trên phần nhỏ lưu lượng; không bật block diện rộng trước khi biết tác động. Nhớ rằng staging thường không có cùng phân bố bot và người dùng thật như production.

### Bước 5 — Giới hạn và tăng mức can thiệp dần

Ưu tiên throttle/quota cụ thể ở endpoint cần bảo vệ. Với traffic browser có nghi ngờ, dùng challenge tương thích; với API, sử dụng quota theo credential và phản hồi có thể xử lý tự động. Block chỉ khi có đủ bằng chứng/rủi ro và cơ chế rollback.

### Bước 6 — Kiểm chứng và vận hành

Theo dõi tỷ lệ 429/403, auth success, đơn hàng hợp lệ, lỗi API đối tác, challenge completion, độ trễ và backend capacity. Duy trì dashboard theo policy version để nhận biết drift. Rà soát ngưỡng khi thay API, thêm tenant, cập nhật ứng dụng, mở vùng cloud hoặc thay topology CDN.

**Một rule chỉ được xem là triển khai tốt khi giảm lạm dụng hoặc tải không mong muốn mà vẫn bảo toàn hành vi hợp lệ trong các trường hợp đã cam kết.**

## 11. Threat modeling những điểm kiểm soát có thể thất bại

| ID | Ranh giới/tình huống | Rủi ro | Bảo vệ và cách xác minh |
|---|---|---|---|
| B01 | Internet → origin | Origin cho phép kết nối không qua WAF | Giới hạn nguồn, xác thực upstream, kiểm tra đường public |
| B02 | Client → WAF | Rate limit chỉ theo IP gây chặn nhầm NAT lớn | Bổ sung identity/route, benchmark với client hợp lệ |
| B03 | WAF → API | API tin header client IP hoặc bot score do client tự gửi | Xóa/ghi đè header không tin cậy, xác minh proxy chain |
| B04 | Browser ↔ challenge | Người dùng hỗ trợ tiếp cận hoặc mobile không giải challenge | Tạo phương thức thay thế, phân nhóm route và client |
| B05 | API partner | Partner được bypass WAF toàn site | Exception hẹp, credential/quota, kiểm tra rule hiệu dụng |
| B06 | Distributed edge | Counter cục bộ ở nhiều node vượt quota kỳ vọng | Xác minh cơ chế phân tán, test đa vùng, quan sát state |
| B07 | Shared backend | Một tenant dùng quá nhiều DB connections dù per-IP quota có hiệu lực | Quota theo tenant, concurrency, circuit breaker, giới hạn worker |
| B08 | Logs/telemetry | Log request chứa token/PII | Redact, least privilege, retention, test không rò secret |
| B09 | Application authz | WAF cho phép request nhưng API không kiểm tra quyền object | Kiểm thử phân quyền chức năng/dữ liệu, không coi bot score là authz |
| B10 | Thay đổi policy | Rule block/challenge mới làm hỏng login hoặc webhook hợp lệ | Canary, chỉ số SLO, quy trình rollback và contact của owner |

Trong mô hình đe dọa, cần phân biệt **bot classification** với **authorization**. Không có một HTTP fingerprint, CAPTCHA hay rate limit nào ngăn được toàn bộ lỗi phân quyền, credential bị chiếm, SSRF, SQL injection hoặc tổn thất khi backend đã có lỗ hổng.

## 12. Bài tập tình huống: giảm bot mà không phá API hợp lệ

**Bối cảnh:** Một hệ thống đặt vé có website, mobile app và đối tác phân phối vé. Sau đợt mở bán, số request vào `/api/search` và `/api/reservations` tăng mạnh; backend xuất hiện lỗi 503. Nhóm vận hành bật rule “quá 30 request/phút/IP → CAPTCHA”. Kết quả: một số nhân viên dùng chung Wi-Fi bị chặn, mobile app không qua được challenge, còn một số truy vấn tự động vẫn gây tải cao.

Các dữ kiện giả định:

| Nhóm request | Tín hiệu | Điều cần kiểm chứng |
|---|---|---|
| Nhân viên văn phòng | Nhiều người dùng thật chung IP NAT | Có xác thực user/session và hành vi hợp lệ? |
| Mobile app | Có access token, không xử lý web CAPTCHA | Quota nào áp theo user/device/route? |
| Đối tác | OAuth client được cấp quyền, chạy batch theo giờ | Hợp đồng rate, quyền dữ liệu và quota? |
| Browser chưa đăng nhập | Search liên tục, lặp query giống nhau | Có dấu hiệu lạm dụng ngoài baseline? |
| API reservations | Request tạo booking tốn DB connection | Có giới hạn đồng thời, quota theo tài khoản và idempotency? |

**Câu hỏi:**

1. Vì sao giới hạn theo IP và CAPTCHA cho mọi loại client không phù hợp?
2. Cần chia policy theo route và loại danh tính nào?
3. Nên thu thập log/metric gì để xác minh hoạt động bot và false positive?
4. Cần phối hợp WAF, API gateway và backend ra sao để bảo vệ `/reservations`?
5. Triển khai thay đổi theo bước nào để có thể rollback an toàn?

**Gợi ý đối chiếu:**

- Dùng quota đa tầng: per-IP ở edge cho nguồn chưa xác thực, per-user/session ở API cho ứng dụng thật, per-OAuth-client cho đối tác, concurrency và quota giao dịch theo tenant/tài khoản. Điều chỉnh ngưỡng từ baseline, không chọn một mức cho mọi route.
- Challenge chỉ áp cho những luồng browser phù hợp và có phương thức hỗ trợ thay thế; mobile và webhook không nên phụ thuộc web CAPTCHA.
- Bổ sung cache/pagination cho search, giới hạn CPU/DB connections, queue/timeout phù hợp cho reservations; ở backend áp idempotency và kiểm tra quyền giao dịch.
- Đối chiếu 429/403/503, p95/p99 latency, DB saturation, challenge completion, auth success và tỉ lệ đặt vé thành công, có request ID liên kết giữa edge và backend.
- Quan sát trước, áp throttle từng route/nhóm client, kiểm thử người dùng hợp lệ và đối tác, canary theo vùng, đặt tiêu chí rollback và theo dõi liên tục.

## 13. Checklist review bot và automation control

- [ ] Phân biệt bot hợp lệ, automation được cấp quyền và hành vi lạm dụng; có chủ sở hữu chính sách.
- [ ] Kiểm kê mọi HTTP/API endpoint, bao gồm mobile, webhook, partner, staging và đường origin.
- [ ] Đảm bảo lưu lượng cần bảo vệ đi qua điểm thực thi; không để origin bypass không được phép.
- [ ] Xác định chính xác proxy chain, IP thật, TLS termination và các giao thức mà WAF có thể phân tích.
- [ ] Không tin User-Agent, header client IP, cookie hoặc bot score do client tự khai báo.
- [ ] Dùng tín hiệu đa chiều thay vì quyết định chỉ từ IP hoặc một điểm bot score.
- [ ] Có quota theo route, nguồn, user/tenant/API key và giới hạn concurrency khi phù hợp.
- [ ] Kiểm tra cơ chế counter/state khi triển khai nhiều node hoặc region; có phương án khi hệ thống chia sẻ state lỗi.
- [ ] Không dùng CAPTCHA/JavaScript challenge cho API/mobile/webhook không tương thích; bảo đảm accessibility.
- [ ] Có cơ chế MFA/step-up, xác thực và phân quyền ứng dụng; WAF không thay các lớp này.
- [ ] Exception/allowlist được giới hạn phạm vi, thời hạn, có audit và không bypass toàn bộ biện pháp bảo vệ.
- [ ] Ghi được policy ID, action, request ID, tỷ lệ bị giới hạn, hiệu quả và false positive; bảo vệ dữ liệu trong log.
- [ ] Quan sát/dry-run và kiểm thử client hợp lệ trước khi bật block; có canary và rollback.
- [ ] Theo dõi chênh lệch traffic, tác động backend và kết quả nghiệp vụ sau rollout; cập nhật theo threat model.

**Ghi nhớ:** Bot management hiệu quả không phải “chặn càng nhiều càng tốt”. Đó là **kiểm soát automation theo rủi ro, danh tính và mục tiêu nghiệp vụ**, bằng rate limit/quota, phân loại có kiểm chứng, xác thực phù hợp và giám sát liên tục. WAF tạo một lớp bảo vệ quan trọng cho HTTP/API, nhưng kiến trúc an toàn vẫn cần firewall, phân đoạn, bảo vệ danh tính, phân quyền dữ liệu và khả năng chịu tải của backend.
