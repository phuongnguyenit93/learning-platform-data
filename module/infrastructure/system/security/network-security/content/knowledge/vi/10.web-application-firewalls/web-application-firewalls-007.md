# Rate limiting tại WAF: kiểm soát tốc độ yêu cầu và giảm lạm dụng ứng dụng web

Trong chương **Web application firewall** của module **SECURITY_NETWORK_SECURITY**, **rate limiting tại WAF** là biện pháp giới hạn tần suất hoặc lượng yêu cầu HTTP mà một nguồn, danh tính hay nhóm lưu lượng được phép gửi đến tài nguyên cần bảo vệ trong một khoảng thời gian. Mục tiêu là giảm tải do truy cập quá mức, hạn chế một số dạng tự động hóa độc hại và bảo vệ tính sẵn sàng của ứng dụng, API và các dịch vụ phía sau.

Rate limiting là một **control** trong kiến trúc phòng vệ mạng nhiều lớp. Nó phối hợp với phân đoạn, firewall L3/L4, chống DDoS ở biên mạng, xác thực, giám sát IDS/IPS và kiểm soát quyền tại ứng dụng. Một cấu hình rate limit chỉ thực sự phù hợp khi người thiết kế biết **đang bảo vệ endpoint nào, giới hạn ai, đếm sự kiện gì, áp thuật toán nào và xử lý ra sao khi vượt ngưỡng**.

Sau bài học, bạn có thể:

- Giải thích nơi WAF thực hiện rate limiting và phân biệt nó với giới hạn kết nối hoặc thông lượng tại firewall L3/L4.
- So sánh *fixed window*, *sliding window*, *token bucket*, *leaky bucket* và giới hạn yêu cầu đồng thời.
- Lựa chọn khóa giới hạn theo IP, danh tính đã xác minh, API key hoặc nhóm endpoint; nhận biết tác động của NAT, proxy và IPv6.
- Thiết kế rule, ngưỡng, ngoại lệ và hành động phù hợp với login, API, truy vấn tốn tài nguyên và luồng người dùng thông thường.
- Kiểm chứng chính sách bằng positive/negative tests, log, metric và đánh giá tỷ lệ chặn nhầm, rồi điều chỉnh có kiểm soát.

## 1. Rate limiting tại WAF nằm ở đâu trong đường đi?

Một WAF thường xử lý lưu lượng **HTTP/HTTPS ở lớp ứng dụng (Layer 7)** tại CDN/edge, reverse proxy, load balancer tích hợp WAF hoặc một dịch vụ bảo vệ tương đương. Với HTTPS, WAF cần có khả năng quan sát yêu cầu HTTP sau khi TLS được kết thúc hoặc thông qua cơ chế tích hợp phù hợp; một thiết bị chỉ nhìn thấy packet TCP/UDP đã mã hóa sẽ không tự đọc được đường dẫn, phương thức hay danh tính trong yêu cầu.

~~~mermaid
flowchart LR
    U["Browser / API client"] --> D["DNS và Internet"]
    D --> W["CDN / WAF ở edge"]
    W --> L["Load balancer / API gateway"]
    L --> A["Web / API service"]
    A --> DB[("Database / backend")]
    W -. "Rule match, rate counter, action" .-> O["Logs / metrics / SOC"]
    L -. "Auth, quota, telemetry" .-> O
    A -. "Latency, error, workload" .-> O
~~~

Trong ví dụ, WAF có thể chặn phần lớn yêu cầu vượt hạn mức **trước khi tới origin**. Nhờ đó, các nguồn lực phía sau như worker, thread pool, database connection, CPU hoặc ngân sách gọi API ít bị tiêu tốn hơn. Tuy nhiên, việc yêu cầu đã đến WAF cũng đòi hỏi năng lực nhận kết nối và xử lý ban đầu tại edge; đó là lý do phải phối hợp **chống tấn công lưu lượng lớn (volumetric DDoS)** ở hạ tầng mạng.

### 1.1. Phân biệt các dạng giới hạn

| Cơ chế | Đơn vị đếm | Ví dụ | Bảo vệ chủ yếu |
| --- | --- | --- | --- |
| **HTTP request rate limit tại WAF** | Số HTTP request theo khóa và thời gian | 60 yêu cầu/phút/IP tới một endpoint | Chống truy cập HTTP quá mức hoặc tự động hóa đơn giản |
| **API quota** | Số lượt hoặc đơn vị tiêu thụ trong kỳ | 10.000 API calls/ngày/khách hàng | Công bằng tài nguyên, kế hoạch sử dụng, giới hạn dịch vụ |
| **Concurrency limit** | Số request/tác vụ đang xử lý cùng lúc | Tối đa 5 tác vụ xuất báo cáo/tenant | Chống cạn worker/connection khi request chạy lâu |
| **Connection limit L3/L4** | Số kết nối TCP/UDP hoặc phiên đang mở | Số session đồng thời theo IP | Hạn chế cạn trạng thái/kết nối |
| **Bandwidth / packet rate limit** | Bit/giây hoặc packet/giây | Hạn chế PPS ở tầng mạng | Giảm áp lực đường truyền, giao thức mạng |
| **Application-level abuse control** | Hành vi hoặc ý nghĩa thao tác | Giới hạn mã OTP cho mỗi tài khoản | Bảo vệ nghiệp vụ và tài nguyên nhạy cảm |

Các giới hạn này **không tương đương**. Ví dụ, một request xuất báo cáo kéo dài 40 giây có thể làm cạn worker dù tổng request mỗi phút khá thấp; cần giới hạn concurrency hoặc hàng đợi ở ứng dụng. Ngược lại, kẻ tấn công phân tán hàng triệu request có thể gây áp lực trước cả khi WAF hoàn tất xử lý HTTP; cần năng lực bảo vệ upstream.

### 1.2. Phạm vi của một rule

Một rule rate limiting thường gồm:

~~~text
Traffic selector  : Điều kiện nào đưa request vào rule?
Counting key      : Các request được nhóm theo ai/cái gì?
Counter scope     : Đếm theo endpoint, nhóm URL, API, toàn site hay zone?
Algorithm/window  : Cách đếm và khoảng thời gian?
Threshold/burst   : Mức trung bình và biên độ đột biến cho phép?
Action            : Khi vượt ngưỡng sẽ log, delay, challenge, block, ...?
Exceptions        : Những luồng hợp lệ nào được xét khác?
Observability     : Đo được rule hit, nguồn, độ trễ, chặn nhầm bằng gì?
Owner/review      : Ai duy trì ngưỡng và khi nào phải đánh giá lại?
~~~

Không phải sản phẩm WAF nào cũng cung cấp đủ tất cả điều kiện hoặc hành động trên. Phải đọc cách nền tảng thực tế xử lý **priority, aggregation key, window, action duration và việc đồng bộ bộ đếm**.

## 2. Xuất phát từ threat và tải hợp lệ, rồi mới chọn ngưỡng

Một giới hạn “100 requests/phút cho toàn website” có vẻ đơn giản nhưng thường quá thô. Tốc độ tải hợp lệ khác nhau đáng kể giữa trang tĩnh, API danh sách, đăng nhập, tìm kiếm và kết xuất báo cáo.

Ví dụ về các kịch bản cần phân biệt:

| Kịch bản / điểm rủi ro | Endpoint minh họa | Mục tiêu của rate limit | Control bổ sung |
| --- | --- | --- | --- |
| Credential stuffing / password spraying | `POST /login` | Hạn chế số lần thử đăng nhập tự động | MFA, chống dò mật khẩu, phát hiện theo tài khoản và IP, login monitoring |
| Lạm dụng gửi OTP hoặc reset mật khẩu | `POST /otp/send`, `POST /password-reset` | Hạn chế số mã/tin nhắn được phát hành | Quota theo tài khoản/số điện thoại, timeout, cơ chế chống spam nghiệp vụ |
| Đọc API quá nhiều | `GET /api/items` | Giữ tài nguyên công bằng giữa các client | API key/JWT, quota theo tenant, caching |
| Endpoint tốn CPU/DB | `POST /reports/export` | Tránh dồn quá nhiều job nặng | Job queue, giới hạn concurrency, timeout, cache, quyền truy cập |
| Crawl/scraping dữ liệu | `GET /catalog/*` | Giảm tốc độ tự động hóa ngoài mong đợi | Bot management, chính sách truy cập, bảo vệ dữ liệu ở ứng dụng |
| Tấn công HTTP flood | Nhiều đường dẫn public | Giảm số request gây áp lực tới origin | CDN/cache, upstream DDoS mitigation, load shedding, autoscaling phù hợp |

### 2.1. Viết mục tiêu bảo vệ có thể kiểm chứng

Ví dụ:

> “Một tài khoản đã được xác minh chỉ được khởi tạo số lượng tác vụ xuất báo cáo nằm trong năng lực backend; truy cập tăng đột biến từ một nguồn phải được hạn chế trước khi làm ảnh hưởng đến người dùng khác. Khi bị giới hạn, client nhận tín hiệu rõ ràng và hệ thống ghi nhận được lý do.”

Từ mục tiêu đó, phải trả lời:

1. Đơn vị công bằng là **IP, account, tenant, API key, session** hay kết hợp nhiều khóa?
2. Sự kiện nào được đếm: **mọi request, chỉ POST, chỉ request thất bại, request đến một endpoint**, hay số đơn vị chi phí được gán cho tác vụ?
3. Giới hạn có cần **burst** ngắn để hỗ trợ trải nghiệm thực tế không?
4. Cơ chế khi quá ngưỡng là **429**, challenge, delay, log-only hay bước xử lý khác?
5. Khi một nguồn lạm dụng, liệu người dùng khác dùng cùng NAT/proxy có bị ảnh hưởng?

**Đặt ngưỡng dựa trên workload:** sử dụng phân vị về request rate và tần suất burst từ lưu lượng hợp lệ, sức chịu tải của origin, kết quả load test có quyền và tác động nghiệp vụ. Một số ngưỡng dưới đây chỉ nhằm minh họa cách tư duy, không phải giá trị mặc định khuyến nghị để sao chép.

## 3. Thuật toán đếm request: hiểu ngưỡng và burst

### 3.1. Fixed window counter

**Fixed window** chia thời gian thành các cửa sổ cố định, ví dụ 12:00:00–12:00:59 và 12:01:00–12:01:59. Trong mỗi cửa sổ, một khóa có thể gửi tối đa `N` request.

~~~text
Rule minh họa: 60 requests / 60 seconds / client

12:00:00 ---------------------- 12:00:59 | 12:01:00 ---------------
       Cửa sổ thứ nhất                   | Cửa sổ thứ hai
               tối đa 60                 |          tối đa 60
~~~

Ưu điểm: đơn giản, dễ triển khai và bộ nhớ đếm tương đối nhỏ. Hạn chế: **boundary burst**. Một client có thể gửi gần 60 request ngay cuối cửa sổ trước và thêm 60 ngay đầu cửa sổ sau, tức gần 120 request trong một khoảng rất ngắn dù mỗi cửa sổ riêng lẻ đều chưa vượt ngưỡng.

### 3.2. Sliding window log và sliding window counter

**Sliding window log** ghi mốc thời gian của các request rồi chỉ tính những request nằm trong khoảng thời gian lùi từ hiện tại, ví dụ 60 giây vừa qua. Cách này giảm hiện tượng dồn tải sát ranh giới nhưng tốn bộ nhớ và tính toán hơn khi số lượng request/khóa lớn.

**Sliding window counter** thường kết hợp bộ đếm của các khoảng thời gian lân cận với trọng số để **ước lượng** số request trong cửa sổ trượt. Nó tiết kiệm tài nguyên hơn log đầy đủ nhưng có sai số tùy cách triển khai và độ rộng bucket.

Ví dụ rule 60 request/60 giây với sliding window có thể ngăn phần lớn các đợt dồn 60 request cuối phút và 60 request đầu phút. Dù vậy, **cách xử lý burst của từng sản phẩm** vẫn cần được kiểm tra.

### 3.3. Token bucket

**Token bucket** có sức chứa tối đa `B` token. Hệ thống nạp lại token với tốc độ `r` token/giây. Mỗi request hợp lệ tiêu thụ một token hoặc nhiều token nếu có cơ chế quy đổi chi phí. Request được phép khi bucket đủ token; nếu không, policy quyết định chờ hoặc từ chối.

Ví dụ minh họa:

- Sức chứa bucket **10 token**.
- Nạp lại **1 token/giây**, tức **60 token/phút** khi có đủ thời gian.
- Mỗi HTTP request tiêu thụ **1 token**.

Với bucket đang đầy, một client có thể gửi nhanh **10 request đầu tiên**. Sau đó client cần chờ token được nạp để tiếp tục ở tốc độ trung bình khoảng **1 request/giây**; mức tối đa còn tùy cách đồng bộ và làm tròn thời gian của hệ thống.

~~~text
Token bucket (minh họa, không phụ thuộc nhà cung cấp)

capacity = 10
refill_rate = 1 token/second
cost_per_request = 1

on_request(key, now):
    tokens[key] = min(capacity,
                      tokens[key] + elapsed(key, now) * refill_rate)
    last_update[key] = now
    if tokens[key] >= cost_per_request:
        tokens[key] = tokens[key] - cost_per_request
        return ALLOW
    else:
        return RATE_LIMIT_ACTION
~~~

Đây là **pseudocode**, bỏ qua cơ chế cập nhật nguyên tử, đồng bộ phân tán, TTL của key và xử lý thời gian. Trong hệ thống nhiều worker/POP, việc đọc rồi ghi bộ đếm theo cách đơn giản có thể dẫn đến race condition và vượt ngưỡng nếu không được thiết kế đúng.

**Ý nghĩa vận hành:** token bucket phù hợp khi người dùng có thao tác dồn ngắn hợp lệ, nhưng bạn vẫn cần duy trì trần tốc độ trung bình.

### 3.4. Leaky bucket

**Leaky bucket** thường được mô tả như một hàng đợi chấp nhận đầu vào có giới hạn và xử lý/cho đi qua với tốc độ ổn định. Request đến quá nhanh có thể bị xếp hàng hoặc loại bỏ khi hàng đợi đầy. Một số nền tảng dùng thuật ngữ này cho biến thể có hành vi gần với token bucket; cần xác minh ngữ nghĩa cụ thể của sản phẩm.

Ưu điểm: làm mượt lưu lượng đến backend. Nhược điểm: hàng đợi làm tăng **latency**; với HTTP tương tác và timeout ngắn, xếp hàng lâu có thể làm trải nghiệm tệ hơn việc trả lỗi rõ ràng để client retry có điều tiết.

### 3.5. Concurrency limit và quota theo kỳ

Không nên thay thế mọi bài toán bằng requests/second:

- Một request chạy rất lâu hoặc chiếm nhiều bộ nhớ cần thêm **giới hạn đồng thời**.
- Một khách hàng có thể tạo quá nhiều dữ liệu trong một ngày dù lưu lượng mỗi phút thấp; cần **daily/monthly quota** được quản lý ổn định.
- Một endpoint có chi phí không đồng đều cần **weighted rate limit** hoặc quota dựa trên tài nguyên thực tế, nếu nền tảng hỗ trợ.
- Một yêu cầu dùng long polling, streaming hoặc WebSocket có thể chỉ tạo ít HTTP handshake nhưng giữ nhiều tài nguyên; phải kiểm soát tài nguyên sau khi kết nối được nâng cấp ở lớp thích hợp.

### 3.6. So sánh nhanh các thuật toán

| Thuật toán | Khả năng cho phép burst | Bộ nhớ/chi phí tương đối | Điều cần cảnh giác |
| --- | --- | --- | --- |
| Fixed window | Có thể dồn mạnh ở ranh giới cửa sổ | Thấp | Hai đợt sát ranh giới có thể vượt mức kỳ vọng |
| Sliding log | Kiểm soát cửa sổ trượt tương đối chính xác | Cao hơn theo số request | Lưu nhiều timestamp, cần dọn dữ liệu |
| Sliding counter | Hạn chế burst sát ranh giới tốt hơn fixed window | Trung bình/thấp tùy bucket | Ước lượng, phụ thuộc độ mịn khoảng đếm |
| Token bucket | Cho burst tối đa theo token tích lũy | Thường thấp theo mỗi khóa | Cần xác định refill, capacity và cập nhật nguyên tử |
| Leaky bucket / queue | Làm mượt tốc độ ra | Phụ thuộc kích thước queue | Có thể tăng độ trễ, tốn tài nguyên hàng đợi |
| Concurrent requests | Giới hạn số tác vụ đang chạy | Theo số tác vụ/luồng | Không tự hạn chế tổng request trong thời gian dài |

## 4. Counting key: “giới hạn theo ai?” quyết định tính đúng của policy

Một ngưỡng được cấu hình tốt nhưng dùng **khóa đếm sai** có thể gây chặn nhầm hàng loạt hoặc bị vượt qua dễ dàng.

### 4.1. Rate limit theo IP

Khóa theo **client IP** thường có sẵn ở edge và hữu ích cho lưu lượng chưa xác thực. Tuy nhiên:

- Nhiều người dùng có thể chung một IP public sau **NAT, CGNAT, proxy doanh nghiệp hoặc VPN**; họ sẽ chia sẻ cùng hạn mức.
- Một người dùng có thể đổi IP khi chuyển mạng, dùng IPv6 privacy address hoặc đi qua nhiều điểm truy cập; hạn mức theo IP có thể bị phân tán.
- Tác nhân phân tán lưu lượng từ nhiều IP hoặc qua botnet có thể gửi ít request/IP nhưng tổng tải vẫn lớn.
- Chặn cả một prefix IPv6 có thể giảm việc xoay địa chỉ trong một số tình huống, đồng thời có nguy cơ ảnh hưởng nhiều thiết bị hợp lệ; lựa chọn độ dài prefix phải dựa trên bối cảnh.

**IP là tín hiệu mạng, không phải danh tính người dùng được xác thực.** Không dùng IP như bảo đảm ai đã thực hiện hành vi.

### 4.2. IP thật qua reverse proxy và X-Forwarded-For

Nếu có nhiều lớp CDN/proxy, địa chỉ TCP nguồn mà WAF nhìn thấy có thể là IP của proxy phía trước. Một số hệ thống nhận client IP qua trường như `X-Forwarded-For`, `Forwarded` hoặc header riêng của CDN.

~~~text
Client 203.0.113.7
    -> Proxy tin cậy 198.51.100.5
    -> WAF / backend

X-Forwarded-For: 203.0.113.7, 198.51.100.5    (minh họa)
~~~

Vấn đề bảo mật: các header dạng này **có thể do client tự gửi** nếu đường đi cho phép. WAF chỉ nên tin thông tin định danh client được thiết lập bởi **proxy đáng tin cậy trong cấu hình rõ ràng**, sau khi lọc/chuẩn hóa chuỗi proxy theo quy tắc của nền tảng; không lấy tùy tiện phần tử đầu tiên của header do Internet cung cấp.

Nếu client có thể tự thay header mà WAF dùng làm counting key, rate limit có thể bị vượt qua bằng cách thay đổi giá trị trường đó. Ngoài header, cần bảo đảm origin không bị truy cập trực tiếp để đi vòng WAF.

### 4.3. Theo account, session, API key hoặc tenant

Đối với dịch vụ đã xác thực, khóa **account ID**, **tenant ID** hoặc **API key ID** thường phản ánh tốt hơn đơn vị được cấp quyền và mức công bằng. Tuy nhiên:

- Chỉ dùng danh tính **đã được hệ thống tin cậy xác thực**. Một header tự khai `X-User-ID` gửi từ client không thể là định danh an toàn.
- Nếu WAF nằm trước hệ thống xác thực và **không xác minh được JWT hoặc token**, có thể phải dùng tín hiệu khác tại WAF rồi bổ sung limit theo user tại API gateway/ứng dụng.
- API key bị đánh cắp vẫn có thể bị dùng để tiêu thụ quota của chủ sở hữu; kết hợp giám sát và khả năng thu hồi key.
- Tenant lớn có thể có nhiều thành viên sử dụng đồng thời; nên xem xét **giới hạn theo tenant và theo user** để tránh một người chiếm toàn bộ năng lực.
- Không ghi raw access token, cookie bí mật hoặc API key vào log/counting key hiển thị; ưu tiên identifier không nhạy cảm hoặc giá trị dẫn xuất an toàn theo cách triển khai.

### 4.4. Khóa kết hợp và chính sách nhiều tầng

Ví dụ kiểm soát đăng nhập có thể phối hợp:

~~~text
Layer A : Per source IP       -> giảm tốc độ thử từ một nguồn
Layer B : Per account         -> giảm thử hàng loạt mật khẩu trên một tài khoản
Layer C : Per endpoint/global -> bảo vệ năng lực chung của hệ thống đăng nhập
Layer D : Risk-based signals  -> giám sát thiết bị, phiên, uy tín nguồn
~~~

Nếu chỉ giới hạn theo account, một cuộc tấn công **password spraying** có thể thử một mật khẩu trên rất nhiều account và tránh ngưỡng từng tài khoản. Nếu chỉ giới hạn theo IP, một nguồn phân tán hoặc người dùng chung NAT có thể gây khó khăn. Nhiều khóa với mục tiêu khác nhau giúp nâng độ bao phủ nhưng cũng cần cân nhắc tránh khóa tài khoản do người khác cố tình làm cạn quota.

### 4.5. Chuẩn hóa đường dẫn và phương thức

WAF có thể dùng path, method, query hoặc nhóm API làm scope. Cần hiểu cách sản phẩm xử lý:

- Đường dẫn viết hoa/thường, dấu `/` cuối, URL encoding, chuỗi `..` và chuẩn hóa URI.
- Tham số query khác nhau có cùng tiêu tốn tài nguyên hay không.
- `GET /api/items` khác `POST /api/items` về ý nghĩa và chi phí.
- Path có ID động như `/api/items/123`: nên gom theo **route template** khi giới hạn một loại thao tác, tránh mỗi ID được tính vào bucket độc lập.
- CDN cache hit không chạm origin; rule rate limit có thể đếm trước/sau cache tùy vị trí, tạo khác biệt giữa request rate nhìn thấy tại WAF và load backend.

## 5. Thiết kế rule: scope, ngưỡng, hành động và thứ tự đánh giá

### 5.1. Một bộ policy minh họa

Giả định một ứng dụng có trang sản phẩm, endpoint đăng nhập, API công khai đã xác thực và endpoint xuất báo cáo. Các ngưỡng dưới đây **chỉ là ví dụ học tập**, cần điều chỉnh sau khi quan sát workload và kiểm thử năng lực.

| Rule | Match | Khóa đếm | Giới hạn minh họa | Hành động khi vượt |
| --- | --- | --- | --- | --- |
| RL-LOGIN-IP | `POST /login` | Client IP đã xác định đáng tin | 20 yêu cầu/60 giây | Log và trả 429 hoặc challenge phù hợp với client |
| RL-LOGIN-ACCOUNT | `POST /login` | Account ID/identifier đã chuẩn hóa và được ứng dụng xử lý an toàn | 8 lần thử/5 phút | Kiểm soát bổ sung tại auth service, tránh lộ tồn tại tài khoản |
| RL-PUBLIC-API | `/api/public/*` | API key ID đã xác thực | Token bucket 60/phút, burst 10 | 429; thông báo thử lại theo policy |
| RL-EXPORT | `POST /reports/export` | Tenant ID đã xác thực | 5 tác vụ/10 phút, kèm concurrency limit | Từ chối hoặc đưa vào queue có kiểm soát |
| RL-SITE-PRESSURE | Các endpoint public đã chọn | IP hoặc nhóm tín hiệu rủi ro | Ngưỡng riêng theo traffic baseline | Thử log-only rồi challenge/block có kiểm chứng |

Trong thực tế, một request có thể khớp **nhiều rule**. Cần biết nền tảng xét rule theo thứ tự nào, có short-circuit ở action nào, có rule miễn trừ hay không, cách đếm được tiến hành trước/sau challenge và liệu toàn bộ rule đều tăng counter hay chỉ rule đầu tiên.

**Không đặt một ngoại lệ `ALLOW` rộng trước mọi lớp bảo vệ** nếu điều đó khiến request được bỏ qua rate limit hoặc các kiểm tra cần thiết khác. Ngược lại, các luồng health check, webhook và truy cập quản trị hợp lệ có thể cần policy chuyên biệt với định danh và giới hạn riêng, thay vì miễn toàn bộ.

### 5.2. Hành động khi vượt ngưỡng

| Hành động | Ý nghĩa | Khi nên cân nhắc |
| --- | --- | --- |
| **Count/log-only** | Đếm và ghi telemetry, không chặn | Giai đoạn tạo baseline, kiểm thử rule mới |
| **HTTP 429 Too Many Requests** | Báo client đang vượt hạn mức | API, client có khả năng retry có điều tiết |
| **Challenge** | Yêu cầu xác minh thêm theo cơ chế WAF | Lưu lượng browser có thể tương tác, kịch bản bot phù hợp |
| **Block/deny** | Chặn request theo điều kiện và thời hạn | Lưu lượng có dấu hiệu rủi ro rõ, sau khi đánh giá false positive |
| **Delay/throttling** | Làm chậm hoặc điều tiết request | Khi nền tảng hỗ trợ an toàn và độ trễ chấp nhận được |
| **Escalation** | Nâng mức xử lý sau vi phạm liên tiếp | Trường hợp muốn tăng bảo vệ theo tín hiệu, có khả năng quan sát |

Với client API, **challenge đòi hỏi JavaScript/cookie của browser có thể phá vỡ tích hợp**. HTTP 429 với cách retry được công bố thường dễ xử lý hơn.

Ví dụ phản hồi HTTP minh họa:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30

{"error":"rate_limited","message":"Please retry later"}
~~~

`Retry-After: 30` là gợi ý client thử lại **sau 30 giây** theo chính sách của server. Header này có thể biểu diễn thời gian dạng giây hoặc một HTTP-date; không nên khẳng định mọi WAF đều thêm nó tự động. Trên client, việc retry nên có **exponential backoff, jitter, giới hạn số lần thử** và khả năng tôn trọng `Retry-After`; tránh nhiều client cùng retry ngay khi cửa sổ vừa mở.

Ngoài 429, một số WAF trả 403, challenge page hoặc một mã khác theo action. Cần thống nhất hành vi với API contract, monitoring và trải nghiệm người dùng.

### 5.3. Thời lượng block và cơ chế hạ mức

Rate limit **không nhất thiết** có nghĩa chặn IP trong một giờ. Có nền tảng chỉ từ chối request vượt quota hiện tại; có nền tảng đặt một hành động block trong một khoảng riêng. Các câu hỏi quan trọng:

- Ngưỡng áp theo cửa sổ thời gian nào và có reset hay hồi token khi nào?
- Khi vượt, request có bị từ chối ngay hay mọi request tiếp theo bị chặn trong một khoảng?
- Việc đếm tiếp sau khi vi phạm có kéo dài block không?
- Có cảnh báo hoặc quy trình xem xét ngoại lệ khi user hợp lệ bị giới hạn?
- Client có nhận được thông tin phù hợp để tự điều tiết không?

Nếu một IP NAT được nhiều người dùng chia sẻ, block dài theo IP có thể làm ảnh hưởng toàn bộ văn phòng. Chọn hành động tương xứng với độ tin cậy của counting key và tính nhạy cảm endpoint.

## 6. Các giới hạn và nguy cơ bypass cần hiểu

### 6.1. Phân tán qua nhiều IP hoặc nhiều edge

Rule `100 request/phút/IP` không ngăn được kẻ tấn công dùng hàng nghìn địa chỉ IP nếu tổng tải vẫn vượt năng lực origin. Cần phối hợp **global limit**, bot/risk signal, cache, xác thực/quota và upstream DDoS mitigation. Các luồng QUIC/HTTP/3 trên UDP/443 cũng cần được bảo vệ tại edge có hỗ trợ protocol tương ứng; chỉ có rule TCP/443 ở firewall L4 không tự biểu diễn đủ hành vi HTTP/3.

### 6.2. Nguồn có thể đi thẳng tới origin

Nếu DNS công khai trỏ qua CDN/WAF nhưng **origin public IP vẫn cho phép client Internet truy cập trực tiếp**, kẻ tấn công có thể bỏ qua rule tại WAF. Cần giới hạn kết nối từ edge đáng tin cậy, sử dụng private origin khi phù hợp, xác thực kết nối edge-to-origin và quản lý cấu hình firewall/ACL đồng bộ.

**Bảo vệ origin** là một phần của kiến trúc, không phải tùy chọn được đảm bảo chỉ vì đã bật WAF.

### 6.3. WAF không biết chi phí thực tế của từng request

Một request `GET /search?q=...` có thể rẻ hoặc rất đắt tùy truy vấn. Nếu WAF chỉ đếm request, kẻ tấn công có thể gửi ít request nhưng gây truy vấn database phức tạp, hoặc tạo hàng nghìn request có chi phí thấp mà không gây rủi ro tương đương. Cần thêm giới hạn ở ứng dụng: **query timeout, concurrency, pagination, complexity budget, cache, queue và quota theo tài nguyên**.

### 6.4. Các loại tấn công không giải quyết bằng request rate đơn lẻ

- **Lỗ hổng logic và phân quyền:** một request duy nhất có thể khai thác quyền truy cập sai (ví dụ truy xuất dữ liệu không được phép). Cần authorization đúng.
- **SQL injection / XSS / command injection:** rate limiting có thể giảm số lần thử nhưng không thay thế validation, query parameterization, output encoding và WAF detection rules.
- **Slow HTTP hoặc giữ kết nối lâu:** request-rate thấp vẫn tiêu thụ kết nối; cần timeout, connection/concurrency control và bảo vệ hạ tầng.
- **Volumetric L3/L4 DDoS:** WAF L7 có thể chưa nhận đủ request để đếm nếu băng thông hoặc edge bị quá tải; cần bảo vệ upstream.
- **Credential stuffing phân tán:** giới hạn IP đơn lẻ có điểm mù; cần signal và control tại dịch vụ xác thực.
- **DNS amplification, tấn công mạng không dây hoặc quản trị cloud:** thuộc các bề mặt khác, cần các control tương ứng như DNS protection, Wi-Fi authentication, segmentation và cloud configuration security.

## 7. Hệ thống phân tán: counter phải được đồng bộ thế nào?

Trong môi trường CDN nhiều PoP hoặc nhiều WAF instance, các request cùng khóa có thể tới nhiều điểm xử lý.

~~~text
Client / IP A
    |----> Edge PoP 1 : nhận 45 request/phút
    |----> Edge PoP 2 : nhận 45 request/phút

Giới hạn mong muốn trên toàn hệ thống: 60 request/phút/IP
~~~

Nếu mỗi edge có counter **cục bộ**, cả hai đều có thể thấy 45 < 60 và cho qua toàn bộ **90 request/phút**. Đó không nhất thiết là lỗi: một số sản phẩm chủ động chọn đếm xấp xỉ hoặc theo từng region để tối ưu độ trễ, chi phí và độ sẵn sàng.

Có ba hướng thiết kế thường gặp:

| Cách tổ chức counter | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| **Counter cục bộ theo instance/PoP** | Latency thấp, ít phụ thuộc mạng giữa vùng | Ngưỡng thực tế có thể bị nhân lên khi lưu lượng phân tán |
| **Counter tập trung / shared data store** | Khả năng thực thi hạn mức tổng nhất quán hơn | Tăng truy cập từ xa, cần atomic updates, khả năng chịu lỗi và scale |
| **Phân bổ quota theo vùng / đồng bộ xấp xỉ** | Cân bằng latency và mức kiểm soát | Phức tạp, có sai lệch/độ trễ khi trao đổi bộ đếm |

Ngoài vấn đề phân tán, cần kiểm tra:

- **Atomicity:** hai request đến đồng thời không được cùng đọc một giá trị cũ rồi cùng được cho phép sai.
- **Timekeeping:** độ lệch đồng hồ và reset cửa sổ không tạo ra hành vi bất thường.
- **Eviction/TTL:** bộ đếm của khóa ít hoạt động được dọn đúng; việc xóa counter không tạo lỗ hổng lớn.
- **Cardinality:** kẻ tấn công tạo vô số key (IP, header, path) có thể gây áp lực bộ nhớ lưu counter.
- **Fail-open/fail-closed:** khi store không sẵn sàng, rule cho đi, chặn hay dùng fallback? Quyết định cần dựa trên rủi ro và mức độ quan trọng của dịch vụ.
- **Policy rollout:** thay đổi cấu hình đồng thời giữa các POP, các rule cũ/mới có thể khác nhau một thời gian.

Không hứa hẹn chính xác tuyệt đối với một rate-limit phân tán nếu nền tảng chỉ bảo đảm **best effort**; nếu quota thanh toán hoặc giới hạn tài nguyên đặc biệt quan trọng, cân nhắc cơ chế kiểm soát ở dịch vụ authoritative bên trong.

## 8. Cách xác định và điều chỉnh ngưỡng theo dữ liệu thật

### 8.1. Tạo baseline lưu lượng hợp lệ

Theo dõi theo endpoint, nhóm client và giờ cao điểm:

- Requests/second và requests/minute; P50/P95/P99 của **rate theo từng key** trong cửa sổ xác định.
- Burst ngắn (ví dụ 1–10 giây), số request song song, thời gian xử lý và tỷ lệ cache hit.
- Phân phối IP chia sẻ NAT, tenant lớn, client mobile dùng mạng thay đổi, bot hợp lệ và tích hợp webhook.
- CPU/memory, DB connections, queue depth, origin error rate và latency khi tải tăng.
- Tỷ lệ request thất bại/đăng nhập sai, hành vi retry và đột biến theo chiến dịch.

**Không lấy P99 của tổng RPS toàn site để đặt trực tiếp ngưỡng per-IP.** Cần thu thập phân phối **per-counting-key** đúng loại sẽ bị limit, đồng thời xem năng lực tổng của hệ thống.

### 8.2. Ví dụ chọn ngưỡng theo mục tiêu

Giả định API sản phẩm có các thông số **minh họa** sau:

| Chỉ số giả định | Kết quả |
| --- | --- |
| Một client thông thường | 5–20 request/phút |
| Một client hợp lệ bận rộn | Tối đa khoảng 45 request/phút trong khoảng quan sát |
| Burst khi vừa tải trang | 8 request trong 2 giây |
| Mức tải origin muốn hạn chế | Không để một client duy trì 100 request/phút kéo dài |

Có thể **đề xuất để thử nghiệm** token bucket trung bình 60 request/phút và burst 10 token, trước tiên chạy ở chế độ đếm/log-only. Ngưỡng này xuất phát từ baseline giả định và **chưa đủ để triển khai production**; còn phải xác minh client dùng chung IP, cơ chế đếm phân tán, hành vi retry và rủi ro quá tải origin.

Sau chạy thử, phân tích:

1. Có bao nhiêu client hợp lệ sẽ vượt ngưỡng và trong hoàn cảnh nào?
2. Lượng request vượt ngưỡng có thật sự liên quan đến nguy cơ quá tải hoặc lạm dụng không?
3. Nếu mở rộng ngưỡng cho một nhóm khách hàng, tài nguyên backend có đủ không?
4. Có nên tách endpoint, tenant tier, user class hoặc những tác vụ đắt tiền thành policy riêng không?
5. Hành động nào giữ được trải nghiệm và an toàn: log-only, 429, challenge hay block?

### 8.3. Điều chỉnh theo chi phí và hành vi của endpoint

Một số nhu cầu phù hợp với policy **nhiều tầng**:

~~~text
Global safety ceiling  : Giữ tổng request tới origin trong giới hạn năng lực
Per-client rate         : Đảm bảo công bằng giữa các người dùng/API key
Per-route stricter rule: Bảo vệ login, OTP, report, search đắt tiền
Concurrency / job queue: Bảo vệ tác vụ chạy lâu và backend giới hạn worker
Anomaly / bot signals  : Phát hiện nguồn phân tán hoặc ngữ cảnh bất thường
~~~

Nếu các lớp hạn chế nằm trên những hệ thống khác nhau, cần định nghĩa thông điệp lỗi, metric và thứ tự xử lý sao cho đội vận hành biết **control nào** đã từ chối request. Ví dụ, một API gateway và WAF có thể cùng trả 429; thiếu `policy_id` hoặc dấu vết tương ứng sẽ làm việc xử lý sự cố khó hơn.

## 9. Quan sát, cảnh báo và điều tra vi phạm rate limit

### 9.1. Log và metric nên chứa gì?

Một sự kiện rate limit hữu ích thường có:

| Trường / metric | Ý nghĩa |
| --- | --- |
| Timestamp, request ID / correlation ID | Ghép sự kiện qua edge, gateway và origin |
| Policy ID, rule version, action | Biết control nào đưa ra quyết định |
| Endpoint group, HTTP method, host | Tách login, API, static content và các vùng có chi phí khác |
| Key type, key identifier đã bảo vệ | Phân biệt IP, user, tenant, API key mà không lộ token bí mật |
| Client IP tin cậy, địa lý/ASN nếu hợp lệ | Phân tích phân bố lưu lượng, cẩn trọng quyền riêng tư |
| Observed count/rate, window, threshold | Xác minh vì sao bị giới hạn; khả năng cung cấp tùy sản phẩm |
| Response status, challenge outcome | Phân biệt từ chối, thử thách, retry và request hợp lệ |
| Origin latency, 5xx, CPU, queue depth | Đánh giá rate limit có giảm áp lực hệ thống không |

Log HTTP có thể chứa path, tham số truy vấn, IP và dữ liệu cá nhân. Chỉ thu thập trường cần thiết, áp dụng chính sách lưu giữ, phân quyền truy cập và che dữ liệu nhạy cảm. Không log raw mật khẩu, bearer token, OTP hoặc cookie phiên.

### 9.2. Các chỉ số có ích khi rollout

- **Match rate:** tỷ lệ request rơi vào traffic selector.
- **Throttle/block rate:** phần trăm bị giới hạn, phân tách theo policy và counting key.
- **Suspected false positives:** lượng khách hợp lệ bị chặn qua ticket, log hoặc hành vi giao dịch.
- **Origin protection:** thay đổi RPS tới origin, CPU, DB connections, queue depth và latency P95/P99.
- **User experience:** tỷ lệ login thành công, checkout completion, error rate của mobile/API client.
- **Attack coverage:** lưu lượng đáng ngờ còn lọt qua, request phân tán theo IP hoặc tenant, dấu hiệu đổi key để vượt giới hạn.
- **Operational drift:** rule hết hạn, ngoại lệ không được rà soát, log bị thiếu hoặc chính sách giữa các vùng không đồng bộ.

Không nên đánh giá hiệu quả chỉ bằng “số request bị chặn tăng”; số chặn tăng cũng có thể do một ngưỡng quá thấp gây hại cho người dùng thật.

### 9.3. Phân biệt 429 của WAF và của backend

Khi ứng dụng báo “Too Many Requests”, hãy xác minh:

1. Request có tới WAF và đã được kiểm tra bởi rule nào?
2. Log WAF cho biết block/throttle hay request đã được forward?
3. Nếu request tới origin, có API gateway, auth provider hoặc dịch vụ ứng dụng nào trả 429 riêng không?
4. Client có retry quá dày, không tuân thủ `Retry-After` hoặc tạo thác retry giữa nhiều tầng không?
5. Limit đang gắn với IP shared NAT hay account/tenant và có chặn nhầm không?

Một HTTP 429 không đủ để kết luận cấu hình WAF sai; cần nối dấu vết request qua các lớp.

## 10. Kiểm thử rate limiting an toàn và có bằng chứng

Kiểm thử phải diễn ra trên hệ thống, tài khoản và lưu lượng **được cấp quyền**, ưu tiên staging và tránh tạo tải ảnh hưởng dịch vụ production. Có thể dùng test harness nhỏ với tốc độ kiểm soát và logging, không cần chạy công cụ bắn tải lớn để xác minh ngưỡng.

### 10.1. Ma trận positive và negative tests

Với một policy minh họa `RL-PUBLIC-API`: API key đã được xác thực, trung bình 60 request/phút và burst 10; hành động 429 khi bucket không đủ token.

| Test | Hành vi | Kỳ vọng |
| --- | --- | --- |
| **P1 – lưu lượng bình thường** | Client hợp lệ gửi dưới ngưỡng đủ lâu | Request được xử lý bình thường |
| **P2 – burst hợp lệ** | Client gửi đợt ngắn không vượt lượng token đang có | Được phép theo chính sách burst |
| **N1 – vượt tốc độ** | Một key gửi nhanh hơn tốc độ refill cho đến hết token | Request tiếp theo bị giới hạn, có policy ID trong log |
| **R1 – phục hồi sau khi giảm tốc** | Dừng gửi đủ để token hồi, rồi gửi lại | Được phép trở lại theo thuật toán |
| **I1 – cách ly key** | Key A vượt hạn mức, key B vẫn trong hạn mức | Key B không bị chặn do counter của A nếu policy dùng per-key |
| **I2 – NAT chung** | Hai người dùng khác nhau có cùng IP public | Chỉ bị chia sẻ quota nếu đó là mục tiêu thiết kế; nếu không, điều chỉnh key |
| **S1 – spoofed header** | Client gửi header tự khai nhận diện IP/user khác | Header không đáng tin không làm đổi counting key |
| **S2 – origin bypass** | Một kết nối không đi qua WAF tới endpoint origin | Origin phải được bảo vệ theo network policy |
| **D1 – nhiều node/PoP** | Cùng một key gửi qua hai điểm edge được cấp quyền | Hiệu quả phù hợp cam kết đồng bộ/xấp xỉ của nền tảng |
| **O1 – observability** | Tạo một sự kiện rate limit trong staging | Log có rule, action, scope và correlation ID cần thiết |

**Kỳ vọng phải đối chiếu cấu hình cụ thể.** Chẳng hạn, token bucket chỉ cho burst 10 khi bucket đã được nạp đủ; nếu vừa tiêu thụ token thì lượng burst còn lại có thể nhỏ hơn. Một WAF dùng sliding window có thể hành xử khác.

### 10.2. Ví dụ pseudocode kiểm tra theo mô hình token bucket

Đoạn dưới đây minh họa **cách tính cục bộ** cho một khóa, không gửi request thật:

~~~text
Tình huống (giả định):
  refill_rate = 1 token/second
  capacity = 10
  tokens_at_t0 = 10

Tại t = 0: gửi 10 request ngay liên tiếp
  => 10 request được chấp nhận, bucket gần như cạn

Ngay sau đó, gửi request thứ 11
  => thiếu token, áp RATE_LIMIT_ACTION

Tại t = 5 giây không gửi thêm request
  => tích lũy xấp xỉ 5 token (nếu chưa đạt capacity)
  => tiếp tục cho tối đa khoảng 5 request liên tiếp
~~~

Các kết quả mô phỏng giả định không thay thế integration test vì hệ thống thật còn có cạnh tranh đồng thời, độ chính xác thời gian, phân tán và cách WAF tính một request.

### 10.3. Rollout từng bước

1. **Chuẩn bị:** xác nhận threat, baseline, endpoint, owner, cấu hình logging, SLO và rollback.
2. **Quan sát:** áp dụng chế độ count/log-only nếu sản phẩm hỗ trợ; thống kê client sẽ bị ảnh hưởng.
3. **Kiểm tra:** chạy positive/negative tests và mô phỏng tình huống NAT/proxy, IPv6, retry hoặc các edge khác nhau.
4. **Kích hoạt giới hạn:** bắt đầu với phạm vi nhỏ và hành động phù hợp; theo dõi số lượt chặn nhầm và sức khỏe origin.
5. **Hiệu chỉnh:** chỉnh key, route group, threshold, burst, action duration và ngoại lệ trên bằng chứng.
6. **Duy trì:** đánh giá lại khi ứng dụng ra endpoint mới, thay đổi traffic pattern, thêm vùng edge hoặc xảy ra sự cố.

## 11. Case study: bảo vệ luồng đăng nhập và API sau WAF

### 11.1. Bối cảnh

Giả sử một hệ thống gồm SPA, mobile client và API backend, có người dùng doanh nghiệp truy cập qua IP NAT chung. Hệ thống phát hiện nhiều lần đăng nhập thất bại, một nhóm client gọi `GET /api/items` quá dày và endpoint `POST /reports/export` khiến queue tăng nhanh.

Một chính sách chung “30 request/phút/IP cho mọi đường dẫn” sẽ dễ làm hỏng trải nghiệm: trình duyệt tải nhiều request để khởi tạo trang, nhiều nhân viên dùng chung IP, còn một request xuất báo cáo có chi phí cao hơn rất nhiều so với yêu cầu metadata.

### 11.2. Tách chính sách theo threat

| Threat / tài sản | Layer và rule đề xuất | Vì sao |
| --- | --- | --- |
| Tự động thử đăng nhập | WAF giới hạn tốc độ `POST /login` theo IP; auth service theo account và tín hiệu bất thường | Tránh lệ thuộc hoàn toàn vào một IP hoặc một account |
| Quá tải API đọc dữ liệu | WAF/API gateway theo API key hoặc tenant đã xác thực, cache khi thích hợp | Công bằng giữa các khách hàng, bảo vệ origin |
| Nhiều export jobs nặng | Ứng dụng/queue giới hạn concurrency và daily quota; WAF chặn burst thô ở edge | Bảo vệ tài nguyên xử lý, không chỉ số request |
| Đi vòng WAF tới origin | Firewall/ACL hoặc private origin chỉ cho edge đã xác thực kết nối | Ngăn bypass chính sách tại CDN/WAF |
| Tài khoản/tích hợp bị lạm dụng | MFA, quyền tối thiểu, secret rotation, log xác thực và phát hiện bất thường | Rate limit chỉ giảm tần suất, không chứng minh tính hợp lệ của hành vi |

### 11.3. Bản mô tả policy có thể kiểm thử

~~~yaml
# Mẫu mô tả policy để thảo luận và review, không phải cú pháp một sản phẩm WAF.
policy_id: RL-API-READ
objective: "Limit sustained API reads per authenticated client"
traffic:
  path_group: "/api/items*"
  methods: ["GET"]
identity:
  key_type: "verified_api_key_id"
  fallback_for_unauthenticated: "separate IP-based abuse policy"
algorithm:
  type: "token_bucket"
  refill_rate: "60 tokens/minute"
  capacity: 10
  request_cost: 1
action:
  on_exceeded: "HTTP 429"
  retry_guidance: "Retry-After when supported"
logging:
  policy_id: true
  request_id: true
  protected_key_identifier: true
  action: true
owner: "API Platform / Security"
review_when:
  - "Client usage pattern changes"
  - "New endpoint or pricing tier"
  - "High false-positive rate or backend saturation"
~~~

**Điểm lưu ý:** WAF chỉ được phép dùng `verified_api_key_id` nếu nó thực sự có khả năng xác thực và trích xuất danh tính đó từ nguồn tin cậy. Nếu xác thực chỉ được thực hiện tại API gateway, hãy đặt rule per-key ở gateway và dùng rule khác ở WAF trước bước xác thực.

### 11.4. Đánh giá tác dụng và rủi ro còn lại

Sau khi thử nghiệm, ghi lại:

- **Trước/ sau:** số request tới origin, số lần vượt ngưỡng, latency P95/P99, lỗi 5xx, độ dài queue và tỷ lệ thành công của người dùng hợp lệ.
- **Coverage:** rule áp cho IPv4/IPv6, browser/mobile/API, các edge đang sử dụng và những endpoint nhạy cảm hay chưa.
- **False positives:** tenant lớn có bị ảnh hưởng, người dùng NAT có chung bucket không, webhook/monitoring có bị chặn không.
- **Residual risk:** tấn công phân tán, tài khoản đã bị chiếm, logic ứng dụng, truy vấn có chi phí cao và traffic đi vòng edge còn cần control bổ sung.
- **Vận hành:** người phê duyệt điều chỉnh ngưỡng, dashboard/cảnh báo, playbook tạm giảm tải và điều kiện rollback.

Chỉ đánh dấu policy hoạt động tốt khi **lưu lượng không hợp lệ bị hạn chế theo mục tiêu** và **người dùng hợp lệ vẫn dùng được dịch vụ với chất lượng chấp nhận được**.

## 12. Những nhầm lẫn cần tránh

1. **“Rate limit 100/phút/IP nghĩa là cả hệ thống tối đa 100/phút.”** Một quy tắc per-IP cho phép nhiều IP có bộ đếm riêng; tổng có thể lớn hơn rất nhiều.
2. **“IP luôn đại diện cho một người dùng.”** NAT, proxy, CGNAT và VPN khiến nhiều người cùng chia sẻ một IP.
3. **“Thêm X-Forwarded-For là xác định được IP thật.”** Header có thể bị giả mạo; chỉ tin chuỗi proxy được cấu hình rõ.
4. **“Tăng ngưỡng là hết false positive.”** Có thể cần đổi counting key, tách endpoint, bổ sung burst hoặc loại traffic không liên quan khỏi scope.
5. **“Chặn được bot nghĩa là ngăn được DDoS.”** Bot phân tán hoặc volumetric L3/L4 có thể vượt phạm vi của HTTP rate limiting.
6. **“Rate limit ngăn được SQL injection hoặc lộ dữ liệu.”** Một request duy nhất vẫn có thể khai thác lỗ hổng; cần bảo mật ứng dụng và phân quyền.
7. **“Đặt rate limit ở WAF là backend không cần kiểm soát gì nữa.”** Quota theo user/tenant, quyền truy cập, concurrency và resource budgets thường phải nằm gần ứng dụng.
8. **“Mọi WAF đồng bộ counter chính xác giữa các PoP.”** Nền tảng phân tán có thể dùng counter cục bộ hoặc xấp xỉ; phải kiểm tra cam kết và thực nghiệm.
9. **“429 luôn do WAF.”** API gateway, auth service hoặc backend cũng có thể phát sinh 429.
10. **“Chặn càng nhiều càng tốt.”** Chặn nhầm người dùng thực có thể gây gián đoạn; cần đo cả coverage lẫn trải nghiệm.
11. **“Challenge phù hợp với mọi client.”** Máy khách API và webhook không nhất thiết hỗ trợ thử thách dành cho trình duyệt.
12. **“Một rule trên HTTP/1.1 bảo vệ mọi giao thức.”** Cần kiểm tra WAF xử lý HTTP/2, HTTP/3/QUIC, long-lived connections và các đường truy cập khác.

## 13. Bài tập vận dụng

### Bài 1 — Chọn counting key

Một ứng dụng nội bộ phục vụ 800 nhân viên truy cập từ trụ sở qua hai IP NAT. Rule đặt **50 request/phút/IP** cho toàn bộ trang web. Sau rollout, nhiều nhân viên thường xuyên bị 429. Nguyên nhân có khả năng cao là gì, và nên đổi chính sách thế nào?

**Gợi ý đáp án:** nhiều người dùng đang chia sẻ bucket theo IP và endpoint có hành vi khác nhau. Cân nhắc phân loại endpoint, dùng danh tính đã xác thực tại đúng layer, giữ IP-based protection như một lớp bổ sung, chọn burst phù hợp và đo lại lưu lượng hợp lệ. Không nên chỉ mở whitelist trọn vẹn hai IP vì sẽ bỏ qua một lớp phòng vệ quan trọng.

### Bài 2 — Hiểu fixed window

Rule cho phép **100 request/phút/key** theo fixed window. Client gửi 100 request cuối phút 12:00 rồi thêm 100 request ngay đầu phút 12:01. Có chắc đã vi phạm rule theo từng cửa sổ chưa?

**Đáp án:** không nhất thiết; mỗi cửa sổ riêng lẻ vẫn có thể chỉ chứa tối đa 100 request. Đây là vấn đề boundary burst. Nếu ứng dụng nhạy với đột biến, xem xét sliding window, token bucket với capacity phù hợp hoặc concurrency limit.

### Bài 3 — API key chưa xác minh

WAF nằm trước API gateway, có thể đọc header `X-Api-Key-Id` nhưng không xác minh chữ ký hoặc quyền của key. Có an toàn khi coi giá trị header là danh tính đã xác thực để rate limit per-customer không?

**Đáp án:** không. Client có thể thay header để tạo khóa đếm tùy ý và phân tán yêu cầu. Nên chỉ dùng định danh đã được thành phần tin cậy xác thực, hoặc đặt per-customer quota tại API gateway/ứng dụng; WAF có thể duy trì rule IP/behavior-based độc lập.

### Bài 4 — WAF và công suất backend

Mỗi yêu cầu export chạy khoảng 45 giây và tiêu tốn một database connection. Chỉ có 6 request/phút nhưng 20 client gọi đồng thời vẫn khiến hệ thống quá tải. Điều gì còn thiếu?

**Đáp án:** request rate không hạn chế đủ số tác vụ **đồng thời**. Cần giới hạn concurrency, queue và timeout/worker budget tại API/backend, kết hợp quota theo tenant và giới hạn burst nếu cần.

### Bài 5 — Tự thiết kế control

Hãy đề xuất một policy cho endpoint `POST /otp/send`, nêu rõ **threat**, **khóa đếm**, **cửa sổ thời gian**, **hành động**, **tín hiệu log**, **test không vượt ngưỡng**, **test vượt ngưỡng** và **rủi ro còn lại**. Chú ý một đối tượng khác có thể cố ý gọi OTP cho số điện thoại của người dùng thật và gây từ chối dịch vụ thông qua quota.

## 14. Ghi nhớ khi triển khai

**Rate limiting tại WAF** chuyển yêu cầu bảo vệ tính sẵn sàng và giảm lạm dụng HTTP thành một cơ chế **đếm theo khóa, áp ngưỡng trong thời gian và thực hiện hành động phù hợp**. Hiệu quả phụ thuộc vào việc chọn đúng scope, thuật toán, burst, danh tính tin cậy và thứ tự áp chính sách, hơn là chỉ chọn một con số requests/phút.

Để thiết kế mạng an toàn, hãy đặt WAF trong kiến trúc nhiều lớp: bảo vệ origin và đường truyền ở edge, dùng firewall/segmentation để hạn chế đường truy cập, xác thực và phân quyền tại ứng dụng, kiểm soát tài nguyên tốn kém ở gateway/backend, rồi kết hợp telemetry với SOC/IDS/IPS và quy trình ứng phó. **Mọi rule cần được kiểm chứng bằng hành vi thật, quan sát chặn nhầm và khả năng chịu tải**, sau đó được rà soát khi hệ thống, người dùng hoặc mô hình đe dọa thay đổi.
