# Rate-based rule và giảm thiểu bot, lạm dụng API

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, bảo vệ mạng và ứng dụng cần kiểm soát cả lưu lượng độc hại lẫn cách ứng dụng xử lý các yêu cầu hợp lệ nhưng quá dày đặc. AWS WAF cung cấp Web ACL, rule và rule group để kiểm tra HTTP request trước khi request tới ứng dụng. Rate-based rule giúp phát hiện nhóm request vượt ngưỡng trong một khoảng thời gian và áp dụng hành động như Block, CAPTCHA hoặc Challenge. Khi kết hợp với AWS Managed Rules, Bot Control, API Gateway, CloudFront, Application Load Balancer và cơ chế xác thực của ứng dụng, tổ chức có thể giảm scraping, credential stuffing, brute force, spam và lạm dụng endpoint.

Sau bài học, người học có thể:

- Giải thích cách AWS WAF rate-based rule đếm request và áp dụng rate limit.
- Chọn evaluation window, threshold, aggregation key và scope-down statement phù hợp.
- Xử lý đúng địa chỉ IP khi request đi qua proxy hoặc load balancer.
- Phân biệt hành động Count, Block, CAPTCHA và Challenge.
- Kết hợp rate-based rule với Bot Control và Fraud Control cho các luồng đăng nhập, đăng ký.
- Thiết kế lớp bảo vệ API bằng AWS WAF, API Gateway và logic giới hạn theo danh tính.
- Theo dõi false positive, phân tích WAF logs và điều chỉnh rule an toàn.

## 1. Nhận diện bot và lạm dụng API

Bot là chương trình gửi request tự động. Bot không phải lúc nào cũng xấu: crawler của công cụ tìm kiếm, monitor tình trạng dịch vụ hoặc tích hợp đối tác có thể là lưu lượng hợp lệ. Rủi ro xuất hiện khi bot hoặc người dùng tự động hóa gửi request với mục đích vượt quyền, thu thập dữ liệu trái phép, tạo tài khoản giả, thử mật khẩu hoặc tiêu thụ tài nguyên quá mức.

Các kiểu lạm dụng phổ biến:

| Kiểu tấn công hoặc lạm dụng | Dấu hiệu | Tác động |
|---|---|---|
| Brute force đăng nhập | Nhiều lần thử mật khẩu trên một tài khoản hoặc từ một nguồn | Chiếm tài khoản, tăng tải xác thực |
| Credential stuffing | Thử tập username/password bị lộ trên nhiều tài khoản | Account takeover, gian lận |
| Scraping | Thu thập giá, tồn kho, nội dung hoặc danh mục với tốc độ cao | Mất lợi thế dữ liệu, tăng tải |
| Account creation fraud | Tạo nhiều tài khoản để nhận ưu đãi hoặc spam | Gian lận khuyến mại, dữ liệu giả |
| API enumeration | Gọi liên tục nhiều ID hoặc tham số để dò tài nguyên | Rò rỉ dữ liệu, tải backend |
| Inventory hoarding | Tự động giữ chỗ hoặc thêm hàng vào giỏ với số lượng lớn | Làm sai lệch tồn kho và trải nghiệm mua hàng |
| Layer 7 flood | Gửi nhiều request HTTP có vẻ hợp lệ tới endpoint đắt đỏ | Cạn CPU, connection hoặc database |
| Abuse theo tenant | Một tenant hoặc API client tiêu thụ phần lớn quota dùng chung | Ảnh hưởng khách hàng khác |

Không nên kết luận một request là độc hại chỉ vì nó đến từ bot hoặc có tần suất cao. Crawler hợp lệ có thể truy cập nhiều trang; một công ty có hàng trăm nhân viên sau NAT có thể dùng chung một IP; một ứng dụng di động có thể gửi nhiều request hợp lệ trong thời gian ngắn. Quy tắc cần xét endpoint, danh tính, loại hành động, hành vi, token và tác động tới hệ thống.

## 2. AWS WAF đứng ở đâu trong kiến trúc?

AWS WAF kiểm tra request HTTP(S) tại lớp ứng dụng. Có thể gắn Web ACL vào các tài nguyên được hỗ trợ như:

- Amazon CloudFront distribution.
- Application Load Balancer.
- Amazon API Gateway REST API.
- AWS AppSync GraphQL API.
- Amazon Cognito user pool.
- AWS App Runner, AWS Amplify và một số dịch vụ khác theo danh sách hỗ trợ hiện hành.

Với tài nguyên regional, Web ACL phải được tạo trong cùng Region với tài nguyên. Với CloudFront, Web ACL có scope CLOUDFRONT và được quản lý trong Region us-east-1 (N. Virginia). Mỗi tài nguyên chỉ có thể gắn với một Web ACL tại một thời điểm; một Web ACL có thể được liên kết với nhiều tài nguyên tương thích trong giới hạn dịch vụ.

Sơ đồ luồng cơ bản:

~~~mermaid
flowchart LR
    C[Client hoặc bot] --> E[CloudFront hoặc ALB]
    E --> W[AWS WAF Web ACL]
    W -->|Request hợp lệ| A[API Gateway hoặc ứng dụng]
    W -->|Block / Challenge / CAPTCHA| R[Phản hồi tại lớp bảo vệ]
    A --> B[Service và database]
    W --> L[WAF logs và CloudWatch metrics]
    A --> M[Application metrics và audit logs]
~~~

AWS WAF xử lý ở lớp HTTP và có thể chặn request trước khi backend nhận request. Nó không thay thế bảo vệ mạng ở lớp thấp hơn, xác thực người dùng, kiểm soát quyền truy cập dữ liệu hoặc giới hạn tài nguyên bên trong ứng dụng. Với DDoS, cần xem xét AWS Shield và các biện pháp bảo vệ phù hợp ở lớp mạng, transport và ứng dụng.

## 3. Rate-based rule hoạt động như thế nào?

Rate-based rule theo dõi số request phù hợp với điều kiện của rule trong một evaluation window. AWS WAF gom request thành các nhóm theo aggregation key. Mỗi nhóm được gọi là một aggregation instance. Khi số request của một instance vượt threshold, rule áp dụng action cho các request tiếp theo thuộc instance đó và vẫn thỏa scope-down statement.

Ví dụ, nếu aggregation key là địa chỉ IP, mỗi IP có bộ đếm riêng:

| IP | Số request trong cửa sổ | Threshold | Kết quả |
|---|---:|---:|---|
| 198.51.100.10 | 420 | 1.000 | Chưa vượt ngưỡng |
| 198.51.100.20 | 1.450 | 1.000 | Request tiếp theo có thể bị áp dụng action |
| 203.0.113.8 | 85 | 1.000 | Chưa vượt ngưỡng |

Threshold là ngưỡng theo evaluation window của từng aggregation instance, không phải tổng số request của toàn Web ACL. Nếu rule giới hạn theo IP, 1.000 request từ một IP và 1.000 request từ một IP khác được đếm riêng. Nếu rule kết hợp IP với HTTP method, mỗi cặp IP và method là một instance khác nhau.

Một rule có thể có scope-down statement để chỉ tính một nhóm request, chẳng hạn request POST tới endpoint đăng nhập. Khi đó, request GET trang chủ hoặc request tới endpoint khác không đi vào bộ đếm của rule này.

Rate-based rule không phải bộ đếm giao dịch chính xác để lập hóa đơn hoặc thực thi quota nghiệp vụ. AWS WAF ước lượng tốc độ request và áp dụng rate limit gần ngưỡng cấu hình; không bảo đảm đúng chính xác con số. Cần xem rule như cơ chế bảo vệ khả dụng và giảm lưu lượng bất thường.

## 4. Evaluation window và threshold

AWS WAF hỗ trợ các evaluation window sau:

| Giá trị | Thời gian nhìn lại | Khi nào cân nhắc |
|---:|---|---|
| 60 giây | 1 phút | Phản ứng nhanh với endpoint nhạy cảm |
| 120 giây | 2 phút | Cân bằng phản ứng và biến động ngắn hạn |
| 300 giây | 5 phút | Mặc định, phù hợp nhiều trường hợp |
| 600 giây | 10 phút | Nhận diện hành vi kéo dài hơn |

Giá trị mặc định là 300 giây. Evaluation window là khoảng thời gian WAF nhìn ngược lại mỗi khi ước lượng tốc độ; nó không quy định WAF chỉ kiểm tra một lần sau mỗi cửa sổ. WAF kiểm tra thường xuyên với lịch đánh giá riêng.

Giới hạn thấp nhất được phép cấu hình là 10 request trong evaluation window. Threshold phải được lựa chọn dựa trên traffic bình thường của endpoint, loại client và mục tiêu bảo vệ. Ví dụ, endpoint login thường có ngưỡng thấp hơn endpoint đọc danh mục công khai; endpoint export báo cáo hoặc tìm kiếm đắt đỏ có thể cần giới hạn chặt hơn.

Rate-based rule có một số đặc điểm vận hành quan trọng:

- WAF áp dụng giới hạn gần threshold, nhưng không bảo đảm giới hạn chính xác.
- Có thể có độ trễ vài phút trước khi WAF nhận diện và bắt đầu rate limit; khi traffic giảm, rule cũng cần thời gian để ngừng áp dụng action. Độ trễ giảm rate thường dưới 30 giây theo tài liệu AWS.
- Khi thay đổi threshold, evaluation window, aggregation settings, forwarded IP hoặc scope-down của rule đang chạy, bộ đếm có thể bị reset và hoạt động rate limiting có thể gián đoạn tới khoảng một phút.
- Mỗi instance của rate-based rule có bộ theo dõi riêng. Hai rule có cấu hình giống nhau trong hai Web ACL khác nhau không chia sẻ counter.
- Nếu một rule group có rate-based rule được dùng ở nhiều nơi, mỗi lần sử dụng tạo một instance theo dõi riêng.

Không dùng rate-based rule làm giới hạn duy nhất cho quota của khách hàng, số giao dịch thanh toán hoặc giới hạn tài nguyên chính xác. Các yêu cầu này nên được thực thi trong ứng dụng hoặc lớp API sau khi xác thực danh tính.

## 5. Chọn aggregation key

Aggregation key quyết định request nào được đếm chung. Mặc định, rate-based rule gom theo source IP. AWS WAF hỗ trợ nhiều lựa chọn khác, bao gồm IP address, forwarded IP, ASN, header, cookie, query argument, query string, URI path, HTTP method, label namespace và JA3/JA4 fingerprint. Có thể kết hợp nhiều custom keys để tạo aggregation instance chi tiết hơn.

| Key | Ví dụ sử dụng | Điểm cần cân nhắc |
|---|---|---|
| Source IP | Giới hạn request theo nguồn mạng | Nguồn có thể là proxy hoặc NAT |
| Forwarded IP | Lấy IP client từ header do proxy tin cậy ghi vào | Chỉ an toàn khi header được kiểm soát |
| HTTP method | Tách GET và POST | Một client có thể tạo nhiều instance |
| URI path | Giới hạn riêng endpoint login hoặc search | Cần cân nhắc path động và nhiều biến thể |
| Header hoặc cookie | Phân nhóm theo client/session identifier | Không tin giá trị do client tự khai nếu không được xác thực |
| Query argument | Giới hạn theo loại truy vấn | Giá trị có thể tạo cardinality cao |
| Label namespace | Giới hạn nhóm request đã được rule khác gắn nhãn | Rule tạo label phải chạy trước |
| JA3/JA4 fingerprint | Phát hiện nhóm client có TLS fingerprint tương tự | Fingerprint không phải danh tính người dùng |
| ASN | Gom theo nhà mạng hoặc hệ thống tự trị | Có thể gom nhiều người dùng hợp lệ vào một nhóm |

Tất cả thành phần được khai báo trong custom aggregation key phải có mặt trong request thì request mới được đánh giá và rate limit. Ví dụ, nếu rule dùng IP + header X-Client-Type, request thiếu header đó sẽ không được tính vào rule. Vì vậy, hãy kiểm tra tính ổn định của key trên traffic thật.

### 5.1. Forwarded IP và proxy

Nếu request đi qua reverse proxy hoặc load balancer, source IP mà WAF nhìn thấy có thể là địa chỉ của proxy cuối cùng. Có thể dùng forwarded IP trong header để lấy địa chỉ client, ví dụ X-Forwarded-For.

Chỉ sử dụng forwarded IP khi kiến trúc proxy đáng tin cậy. Proxy cần xóa hoặc ghi đè header do client gửi vào, sau đó thiết lập giá trị client IP theo một quy tắc đã được kiểm chứng. Nếu ứng dụng tin trực tiếp một header tùy ý do client tự gửi, attacker có thể đổi header để né rate limit.

Với forwarded IP, WAF dùng địa chỉ đầu tiên trong header cho rate-based rule. Nếu header tồn tại nhưng IP không hợp lệ, cấu hình fallback behavior thành MATCH hoặc NO_MATCH. MATCH đưa request có IP lỗi vào cùng nhóm giá trị lỗi; NO_MATCH bỏ qua request đối với rule. Nếu header không tồn tại, statement dùng header được đánh giá là No match; trường hợp này không kích hoạt fallback. Hãy kiểm tra rõ hành vi này để tránh tạo lỗ hổng do thiếu header.

## 6. Scope-down statement và thứ tự rule

Scope-down statement thu hẹp tập request mà rate-based rule theo dõi. Các request không khớp scope-down sẽ không được tính và không bị rate limit bởi rule đó.

Một số ví dụ:

- Chỉ giới hạn POST tới /api/login.
- Chỉ giới hạn request tới /api/search có query phức tạp.
- Chỉ giới hạn traffic có label bot đáng ngờ.
- Chỉ áp dụng rate limit cho một nhóm quốc gia hoặc một loại nội dung.
- Chỉ giới hạn request có header hoặc path phù hợp với endpoint cần bảo vệ.

Có thể dùng các statement như Byte match, Regex pattern set, IP set, Geo match, Label match, AND/OR/NOT trong scope-down. Hãy kiểm tra WCU và độ phức tạp của rule khi kết hợp nhiều điều kiện.

AWS WAF đánh giá rule theo thứ tự priority tăng dần. Rule có priority nhỏ hơn được đánh giá trước. Nếu muốn rate limit request dựa trên label của managed rule group hoặc Bot Control, rule tạo label phải chạy trước rate-based rule. Nếu rule trước đó dùng Block hoặc Allow kết thúc quá trình đánh giá, rate-based rule phía sau sẽ không được chạy cho request đó. Trong trường hợp cần quan sát label trước khi quyết định, có thể cấu hình override action của rule group thành Count trong giai đoạn kiểm thử.

Rate-based statement không thể lồng bên trong statement khác. Có thể đặt trực tiếp trong Web ACL hoặc rule group và thêm scope-down bên trong rate-based statement.

## 7. Action: Count, Block, CAPTCHA và Challenge

Rate-based rule hỗ trợ các action như Block, Count, CAPTCHA và Challenge; không dùng Allow làm action cho rate-based rule.

| Action | Hành vi | Khi nên dùng |
|---|---|---|
| Count | Đếm và có thể gắn label/header cho request vượt ngưỡng, rồi tiếp tục đánh giá Web ACL | Quan sát và tuning trước khi chặn |
| Block | Chặn request vượt ngưỡng | API hoặc endpoint mà request quá mức cần bị từ chối |
| CAPTCHA | Yêu cầu client giải CAPTCHA khi thiếu token hợp lệ | Luồng trình duyệt có thể tương tác |
| Challenge | Thực hiện browser challenge để xác minh client | Phân biệt browser thực với công cụ tự động |

Điểm quan trọng: action Count không giới hạn tốc độ. Nó chỉ ghi nhận request vượt ngưỡng và tiếp tục đánh giá các rule phía sau. Nếu mục tiêu là ngăn request vượt ngưỡng tới backend, cần chọn action có tác dụng chặn hoặc challenge phù hợp.

Với CAPTCHA hoặc Challenge, WAF xử lý request dựa trên trạng thái token. Request vượt ngưỡng nhưng có token hợp lệ, chưa hết hạn có thể tiếp tục; request vượt ngưỡng mà thiếu token hợp lệ sẽ bị challenge hoặc CAPTCHA. Vì vậy, CAPTCHA/Challenge không phải cơ chế throttle tất cả request đã vượt ngưỡng.

Với API machine-to-machine, CAPTCHA hoặc browser challenge thường không phù hợp vì client không thể tương tác. Có thể dùng Block hoặc custom response cho client API, đồng thời thiết kế retry/backoff ở phía client. Với trình duyệt, Challenge hoặc CAPTCHA có thể giảm bot nhưng cần kiểm thử token, SDK tích hợp và trải nghiệm người dùng.

## 8. Kết hợp AWS WAF Bot Control và Fraud Control

Rate-based rule phát hiện request có tần suất cao theo key đã chọn. Nó không tự xác định mọi loại bot hoặc hành vi gian lận. AWS WAF có các managed rule group chuyên biệt để bổ sung tín hiệu nhận diện.

### 8.1. Bot Control

AWS WAF Bot Control có hai cấp bảo vệ chính:

- **Common:** nhận diện nhiều bot tự khai báo danh tính như crawler, công cụ scraping và automated browser. Rule group gắn label cho traffic được nhận diện và có thể chặn các bot không xác minh được theo chính sách.
- **Targeted:** bao gồm Common và thêm cơ chế nhận diện bot tinh vi hơn, chẳng hạn browser interrogation, fingerprinting, behavioral heuristics, rate limiting, CAPTCHA và browser challenge nền.

Bot Control gắn label theo loại bot và kết quả kiểm tra. Có thể dùng label để tạo rule riêng: cho phép crawler đã xác minh, giới hạn crawler không rõ nguồn, hoặc chặn nhóm bot scraping không được phép. Hãy xác định rõ bot nào có ích cho sản phẩm; không nên chặn mọi crawler vì có thể ảnh hưởng tìm kiếm, giám sát hoặc đối tác hợp lệ.

Targeted protection có thể cần tích hợp AWS WAF application integration SDK để thu thập token và tín hiệu phiên. Tính năng này có chi phí bổ sung; nên kiểm tra giá, phạm vi endpoint và yêu cầu tích hợp trước khi bật.

### 8.2. Fraud Control cho login và signup

AWS WAF Fraud Control có hai managed rule group chuyên biệt:

- **Account Takeover Prevention (ATP):** kiểm tra request tới endpoint đăng nhập, phát hiện hành vi đăng nhập bất thường, thử credential bị lộ và credential stuffing. Với CloudFront, ATP còn có thể kiểm tra response của ứng dụng để theo dõi tỷ lệ login thành công/thất bại.
- **Account Creation Fraud Prevention (ACFP):** kiểm tra endpoint đăng ký tài khoản, phát hiện tạo tài khoản hàng loạt và hành vi đáng ngờ dựa trên IP, session, thông tin tài khoản và token.

ATP và ACFP không thay thế xác thực trong ứng dụng. Chúng bổ sung tín hiệu và hành động quản lý rủi ro tại lớp WAF. Cả hai có yêu cầu cấu hình endpoint và application integration; có chi phí bổ sung. Theo tài liệu AWS hiện hành, ATP/ACFP không khả dụng cho Amazon Cognito user pools. Một số khả năng response inspection chỉ áp dụng khi Web ACL bảo vệ CloudFront.

## 9. Thiết kế lớp bảo vệ API

API cần nhiều lớp kiểm soát vì một request có thể hợp lệ về cú pháp nhưng vẫn lạm dụng nghiệp vụ.

| Lớp | Cơ chế | Mục tiêu |
|---|---|---|
| Edge | CloudFront, AWS WAF, Shield | Chặn request độc hại trước khi tới origin |
| HTTP/API gateway | AWS WAF trên API Gateway REST API, throttling ở API Gateway | Giảm request burst và bảo vệ stage/method |
| Authentication | IAM, Cognito, Lambda authorizer hoặc cơ chế xác thực phù hợp | Xác định client hoặc người dùng |
| Application | Quota theo user, tenant, API key đã xác thực, token bucket và idempotency | Bảo vệ logic nghiệp vụ và tài nguyên dùng chung |
| Data/service | Connection pool, queue, circuit breaker, database limits | Ngăn request hợp lệ làm cạn tài nguyên phía sau |
| Observability | WAF logs, API metrics, application traces và audit logs | Phát hiện, điều tra và điều chỉnh |

AWS WAF có thể gắn vào API Gateway REST API và đánh giá trước các access control khác như resource policy, IAM policy, Lambda authorizer hoặc Cognito authorizer. Vì vậy, WAF phù hợp để chặn request theo đặc điểm HTTP trước khi API Gateway xử lý xác thực.

API Gateway throttling dùng token bucket và có thể cấu hình ở cấp account/Region, API, stage, method hoặc usage plan tùy loại API. Các mức throttling và quota của usage plan là best-effort target, không phải hard limit; client đôi khi vẫn có thể vượt quota. API key trong usage plan dùng để nhận diện client cho mục đích quản lý usage, không được dùng làm cơ chế authentication hoặc authorization. Hãy dùng IAM, Cognito hoặc Lambda authorizer để xác thực và phân quyền.

Rate limit theo IP không thể thay thế quota theo người dùng. Nhiều người dùng có thể chia sẻ một NAT IP; một botnet có thể phân tán request qua nhiều IP. Với giới hạn theo tài khoản, tenant hoặc subscription, ứng dụng cần áp dụng quota sau khi đã xác thực principal. Nếu WAF dùng custom header để phân nhóm, header đó phải được tạo hoặc xác minh bởi một thành phần tin cậy; không tin header định danh do client tùy ý gửi.

## 10. Tuning threshold và tránh false positive

Threshold quá thấp có thể chặn người dùng hợp lệ. Threshold quá cao khiến rule phản ứng muộn. Hãy dựa trên traffic bình thường và hậu quả khi endpoint bị lạm dụng.

Quy trình tuning:

1. Thu thập baseline theo endpoint, method, thời gian trong ngày, client type và source network.
2. Xác định endpoint nhạy cảm như login, signup, password reset, search, checkout hoặc export.
3. Chọn evaluation window và aggregation key.
4. Thêm scope-down để chỉ tính request đúng endpoint và method.
5. Bật Count trong giai đoạn quan sát.
6. So sánh số request vượt ngưỡng với logs, metrics và hành vi người dùng hợp lệ.
7. Điều chỉnh threshold, key, scope-down và ngoại lệ cho crawler/monitor hợp lệ.
8. Chuyển sang Block, CAPTCHA hoặc Challenge theo loại client.
9. Theo dõi false positive, tỷ lệ 403/429, login success rate, backend latency và request volume sau khi triển khai.

Những tình huống cần cân nhắc:

- **NAT hoặc proxy doanh nghiệp:** nhiều người dùng hợp lệ có thể dùng chung IP. Threshold theo IP cần đủ cao hoặc kết hợp thêm key khác.
- **Mobile carrier NAT:** lượng lớn thiết bị có thể dùng chung địa chỉ egress.
- **Crawler tốt:** xác minh danh tính bot và chỉ miễn trừ bot thực sự cần thiết.
- **Health check:** scope-down hoặc allowlist rõ ràng cho health check có xác thực, không mở rộng ngoại lệ quá mức.
- **Endpoint động:** URI chứa ID có thể tạo nhiều aggregation instance; cân nhắc chuẩn hóa path hoặc giới hạn theo label/HTTP method.
- **Traffic theo chiến dịch:** flash sale hoặc sự kiện truyền thông làm baseline thay đổi. Cần quy trình tăng threshold có thời hạn và giám sát.

Không đổi nhiều thuộc tính của rate-based rule cùng lúc trên production vì thay đổi cấu hình có thể reset counter. Dùng staging hoặc Count để xác nhận trước khi chuyển action.

## 11. Ví dụ cấu hình rate limit cho endpoint đăng nhập

Giả sử một API đăng nhập chạy sau Application Load Balancer trong Region ap-southeast-1. Mục tiêu là theo dõi request tới POST /api/login và chặn một IP có hơn khoảng 1.000 request trong cửa sổ 5 phút.

Ví dụ fragment CloudFormation cho AWS::WAFv2::WebACL:

~~~yaml
Resources:
  ApiWebAcl:
    Type: AWS::WAFv2::WebACL
    Properties:
      Name: ApiRateProtection
      Scope: REGIONAL
      DefaultAction:
        Allow: {}
      VisibilityConfig:
        CloudWatchMetricsEnabled: true
        MetricName: ApiRateProtection
        SampledRequestsEnabled: true
      Rules:
        - Name: LimitLoginBySourceIp
          Priority: 10
          Action:
            Block: {}
          Statement:
            RateBasedStatement:
              Limit: 1000
              EvaluationWindowSec: 300
              AggregateKeyType: IP
              ScopeDownStatement:
                AndStatement:
                  Statements:
                    - ByteMatchStatement:
                        FieldToMatch:
                          UriPath: {}
                        PositionalConstraint: EXACTLY
                        SearchString: /api/login
                        TextTransformations:
                          - Priority: 0
                            Type: NONE
                    - ByteMatchStatement:
                        FieldToMatch:
                          Method: {}
                        PositionalConstraint: EXACTLY
                        SearchString: POST
                        TextTransformations:
                          - Priority: 0
                            Type: NONE
          VisibilityConfig:
            CloudWatchMetricsEnabled: true
            MetricName: LimitLoginBySourceIp
            SampledRequestsEnabled: true
~~~

Đây là ví dụ cấu hình rule trong một Web ACL regional. Sau khi tạo, cần tạo Web ACL association với ALB hoặc API Gateway REST API tương ứng. Với CloudFront, dùng scope CLOUDFRONT và tạo Web ACL trong us-east-1.

Cách đọc cấu hình:

- Limit 1000 là ngưỡng ví dụ cho mỗi aggregation instance trong evaluation window.
- EvaluationWindowSec 300 tương ứng 5 phút.
- AggregateKeyType IP gom request theo source IP.
- ScopeDownStatement chỉ đưa request đúng path và method vào bộ đếm.
- Action Block chặn request thuộc instance đã vượt ngưỡng.
- VisibilityConfig bật CloudWatch metrics và sampled requests để theo dõi.

Trong giai đoạn triển khai đầu tiên, nên đổi Action thành Count để quan sát. Sau khi xác nhận không chặn nhầm traffic hợp lệ, chuyển sang Block hoặc action phù hợp. Threshold 1.000 không phải khuyến nghị chung cho mọi API; cần đo traffic thực tế và điều chỉnh.

## 12. Ví dụ: kết hợp label và rate-based rule

Một managed rule group hoặc Bot Control có thể gắn label cho request nghi là bot. Sau đó, rate-based rule dùng label namespace làm scope-down hoặc aggregation key để giới hạn nhóm traffic đó.

Luồng thiết kế:

~~~mermaid
flowchart TD
    A[Request vào Web ACL] --> B[Bot Control hoặc managed rule group]
    B --> C{Có label bot?}
    C -- Không --> D[Tiếp tục các rule khác]
    C -- Có --> E[Rate-based rule khớp label]
    E --> F{Vượt threshold?}
    F -- Không --> G[Cho tiếp tục đánh giá]
    F -- Có --> H[Block hoặc Challenge]
~~~

Để thiết kế đúng:

1. Đặt rule group tạo label trước rate-based rule.
2. Nếu cần rate rule đánh giá request đã được gắn label, bảo đảm rule trước đó không kết thúc request bằng Allow hoặc Block.
3. Có thể override một số rule của managed rule group sang Count trong giai đoạn tuning để label được tạo mà request tiếp tục được đánh giá.
4. Dùng label namespace phù hợp để phân biệt loại bot hoặc nhóm hành vi.
5. Đặt action và threshold theo tác động của từng nhóm; không nhất thiết chặn tất cả bot.

Một rate-based rule chỉ thực hiện action hoặc áp dụng label khi request đang bị rate limit. Do đó, label từ rate-based rule không phải là dấu hiệu cho mọi request khớp scope-down; nó phản ánh request đang vượt ngưỡng theo aggregation instance.

## 13. Logging và giám sát

Bật visibility cho từng rule và Web ACL để tạo CloudWatch metrics. Đặt metric name dễ nhận diện theo endpoint và mục tiêu bảo vệ. Theo dõi:

- AllowedRequests, BlockedRequests, CountedRequests, CaptchaRequests và ChallengeRequests.
- Request count theo từng rule, Web ACL và resource.
- Tỷ lệ request bị chặn theo endpoint và method.
- Tỷ lệ 4xx/5xx, latency, CPU, database connections và queue depth của backend.
- Login success/failure, password reset, signup success và số tài khoản mới.
- Tỷ lệ người dùng hợp lệ gặp CAPTCHA/Challenge hoặc nhận response bị từ chối.

Có thể bật sampled requests để xem một mẫu request được WAF kiểm tra. Sampled requests hữu ích khi tuning nhưng không thay thế log đầy đủ và có thể chứa thông tin nhạy cảm.

AWS WAF hỗ trợ ghi log tới các đích được hỗ trợ như Amazon Data Firehose, Amazon CloudWatch Logs và Amazon S3 theo cấu hình dịch vụ hiện hành. Khi bật logging, cần:

- Chọn đúng Web ACL và destination.
- Dùng logging filter để giảm log không cần thiết.
- Redact header hoặc trường chứa token, cookie, credential và dữ liệu nhạy cảm.
- Hạn chế IAM access vào log destination.
- Mã hóa dữ liệu và đặt retention phù hợp.
- Không coi sampled request hoặc log đã redact là bản ghi đầy đủ cho mọi yêu cầu điều tra.

Khi phát hiện spike, hãy đối chiếu WAF log với CloudFront/ALB access log, API Gateway execution/access log và application log. Phân tích source IP, URI, method, user agent, label, token status, response code và thời gian. Dữ liệu từ nhiều lớp giúp phân biệt bot, NAT, client lỗi và đợt tăng traffic hợp lệ.

## 14. Quy trình phản ứng khi bị lạm dụng API

Một playbook phản ứng có thể triển khai theo các bước:

1. **Xác nhận tín hiệu:** xem metric nào tăng, endpoint nào bị tác động và thời điểm bắt đầu.
2. **Phân loại:** xác định brute force, scraping, credential stuffing, request flood hay traffic hợp lệ tăng đột biến.
3. **Giảm tác động:** bật rule đã được kiểm thử, điều chỉnh threshold có kiểm soát hoặc thêm scope-down cho endpoint bị lạm dụng.
4. **Bảo vệ người dùng:** không chặn diện rộng nếu có NAT hoặc khách hàng lớn bị ảnh hưởng; dùng CAPTCHA/Challenge với browser traffic khi phù hợp.
5. **Bảo vệ backend:** bật throttling ở API Gateway, giới hạn concurrency ở service, dùng queue hoặc circuit breaker khi cần.
6. **Bảo vệ tài khoản:** yêu cầu xác thực bổ sung, khóa tạm thời theo chính sách, kiểm tra credential compromise và thông báo người dùng theo quy trình.
7. **Theo dõi phục hồi:** quan sát blocked/count metrics, latency, error rate và tỷ lệ thành công nghiệp vụ.
8. **Điều tra và cải tiến:** lưu log, xác định nguồn, cập nhật runbook và bổ sung test cho tình huống vừa xảy ra.

Nếu một rule đang gây false positive, chuyển action sang Count có thể giúp khôi phục traffic trong lúc phân tích, nhưng phải cân nhắc rủi ro nếu cuộc tấn công vẫn đang diễn ra. Thay đổi cấu hình cần người chịu trách nhiệm, thời điểm, lý do và phương án quay lại.

## 15. Chi phí và giới hạn cần tính

AWS WAF tính phí theo Web ACL, rule và số request được kiểm tra; một số managed rule group như Bot Control và Fraud Control có chi phí bổ sung. Custom aggregation key tiêu thụ WCU cao hơn key IP cơ bản. Rate-based rule có WCU cơ bản và thêm WCU cho từng custom aggregation key; scope-down statement cũng cộng WCU theo statement được dùng.

Các yếu tố cần tính:

- Số Web ACL và tài nguyên được bảo vệ.
- Số rule và WCU trong mỗi Web ACL.
- Request volume và số request được kiểm tra bởi managed rule group.
- Chi phí Bot Control, ATP, ACFP và các tính năng intelligent threat mitigation.
- Chi phí CloudWatch metrics, log delivery, Firehose, S3 storage và truy vấn log.
- Lưu lượng giữa CloudFront, ALB, API Gateway và backend.

Dùng scope-down để chỉ đưa request cần kiểm tra vào managed rule group có thể giúp kiểm soát chi phí và giảm phạm vi phân tích. Tuy nhiên, đừng thu hẹp scope quá mức khiến endpoint dễ bị lạm dụng bị bỏ qua. Hãy đo traffic, xác định rủi ro và cân bằng chi phí với mức bảo vệ.

## 16. Thực hành đề xuất

Một cửa hàng trực tuyến có các endpoint:

- GET /products: đọc danh mục sản phẩm.
- GET /search: tìm kiếm và lọc sản phẩm.
- POST /api/login: đăng nhập.
- POST /api/signup: đăng ký tài khoản.
- POST /api/checkout: tạo đơn hàng.

Nhóm vận hành phát hiện traffic tăng mạnh từ nhiều IP khác nhau. Database bắt đầu quá tải; login và signup có tỷ lệ thất bại tăng, trong khi danh mục sản phẩm bị scraping.

Hãy xây dựng phương án theo từng lớp:

| Endpoint | Kiểm soát đề xuất | Lý do |
|---|---|---|
| /products | Bot Control, rate rule theo bot label hoặc fingerprint | Giảm scraping nhưng giữ crawler hợp lệ |
| /search | Rate-based rule theo IP + path hoặc fingerprint | Hạn chế request tìm kiếm lặp lại |
| /api/login | Rate-based rule theo IP, ATP và giới hạn theo tài khoản ở backend | Giảm brute force và credential stuffing |
| /api/signup | ACFP, Challenge/CAPTCHA và giới hạn nghiệp vụ | Giảm tạo tài khoản giả |
| /api/checkout | Xác thực, idempotency key, quota theo user/tenant và bảo vệ backend | Tránh đặt hàng lặp và giữ tài nguyên |

Các bước thực hành:

1. Tạo Web ACL phù hợp với scope của CloudFront hoặc ALB.
2. Bật logging và metrics; xác định baseline traffic.
3. Tạo rate-based rule cho POST /api/login ở Count mode.
4. Dùng scope-down để loại request ngoài endpoint cần kiểm soát.
5. Kiểm tra tác động của NAT và client hợp lệ.
6. Bật Bot Control ở mức phù hợp và đánh giá labels.
7. Cân nhắc ATP cho login và ACFP cho signup nếu kiến trúc, endpoint và ngân sách đáp ứng yêu cầu.
8. Chuyển rule sang action phù hợp sau khi tuning.
9. Bổ sung quota theo user/tenant sau khi ứng dụng xác thực.
10. Kiểm thử load, false positive, response code và khả năng phục hồi của backend.

Kết quả mong đợi là hệ thống có thể hạn chế bot và request lạm dụng mà không làm gián đoạn khách hàng hợp lệ, đồng thời cung cấp đủ log để điều tra và cải tiến.

## Kết luận

AWS WAF rate-based rule là công cụ kiểm soát tốc độ request ở lớp HTTP. Hiệu quả của rule phụ thuộc vào evaluation window, threshold, aggregation key, scope-down và action được chọn. Bot Control và Fraud Control bổ sung khả năng nhận diện bot, credential stuffing và gian lận đăng ký; CloudFront, ALB, API Gateway và ứng dụng tạo thành nhiều lớp bảo vệ.

Rate limit theo IP không thay thế xác thực và quota nghiệp vụ. Hãy kết hợp WAF với API Gateway throttling, xác thực danh tính, giới hạn theo user hoặc tenant, bảo vệ backend và giám sát liên tục. Tuning ở Count mode, kiểm tra false positive, bảo vệ forwarded IP và ghi log an toàn giúp triển khai rate limiting bền vững.

## Tài liệu tham khảo

- [Using rate-based rule statements in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html)
- [Rate-based rule high-level settings](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-high-level-settings.html)
- [Rate-based rule caveats](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-caveats.html)
- [Aggregating rate-based rules](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html)
- [Rate-based rule aggregation instances and counts](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-instances.html)
- [Applying rate limiting to requests](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-request-limiting.html)
- [Using scope-down statements](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-scope-down-statements.html)
- [Using forwarded IP addresses](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-forwarded-ip-address.html)
- [AWS WAF Bot Control](https://docs.aws.amazon.com/waf/latest/developerguide/waf-bot-control.html)
- [AWS WAF Fraud Control account takeover prevention](https://docs.aws.amazon.com/waf/latest/developerguide/waf-atp.html)
- [AWS WAF Fraud Control account creation fraud prevention](https://docs.aws.amazon.com/waf/latest/developerguide/waf-acfp.html)
- [Resources that you can protect with AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html)
- [Protecting API Gateway REST APIs with AWS WAF](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html)
- [Usage plans and API keys for REST APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html)
- [AWS WAF logging](https://docs.aws.amazon.com/waf/latest/developerguide/logging.html)
- [AWS WAF pricing](https://aws.amazon.com/waf/pricing/)

