# AWS WAF web ACL, rule và managed rule group

AWS Web Application Firewall (AWS WAF) bảo vệ ứng dụng web và API bằng cách kiểm tra các yêu cầu HTTP(S) trước khi chúng đến tài nguyên đích. Người vận hành định nghĩa một web access control list (web ACL), sắp xếp các rule theo thứ tự ưu tiên, chọn hành động cho yêu cầu khớp và đặt hành động mặc định cho yêu cầu không khớp rule nào. AWS WAF cung cấp rule tự xây dựng, rule group do nhóm vận hành quản lý và managed rule group do AWS hoặc nhà cung cấp khác duy trì.

Trong kiến trúc AWS, web ACL thường được gắn với Amazon CloudFront, Application Load Balancer (ALB), Amazon API Gateway REST API, AWS AppSync, Amazon Cognito hoặc các tài nguyên được AWS WAF hỗ trợ khác. WAF là lớp bảo vệ ở tầng ứng dụng. Nó bổ sung cho security group, network ACL, AWS Network Firewall, AWS Shield và cơ chế xác thực/ủy quyền của ứng dụng.

Bài học tập trung vào AWS WAF phiên bản hiện hành (WAFv2): cách thiết kế web ACL, chọn rule, triển khai managed rule group, kiểm thử trước khi chặn lưu lượng và vận hành các chính sách bảo vệ an toàn. Trong một số giao diện và tài liệu mới, AWS gọi web ACL là “protection pack (web ACL)”; API và tài nguyên CloudFormation vẫn sử dụng thuật ngữ WebACL.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của web ACL và chọn đúng scope REGIONAL hoặc CLOUDFRONT.
- Mô tả thứ tự đánh giá rule, default action và ý nghĩa của Allow, Block, Count, CAPTCHA, Challenge.
- Chọn statement phù hợp để kiểm tra IP, địa lý, URI, header, body, SQL injection, XSS và lưu lượng vượt ngưỡng.
- Cấu hình AWS Managed Rules và managed rule group của bên thứ ba theo cách có thể kiểm thử và cập nhật.
- Dùng rule override, scope-down statement và label để giảm false positive.
- Ước lượng WCU, hiểu giới hạn body inspection và kiểm soát chi phí.
- Gắn web ACL vào tài nguyên AWS, bật logging/metrics và xử lý lỗi thường gặp.

## 1. AWS WAF đứng ở đâu trong kiến trúc

AWS WAF là dịch vụ tường lửa ứng dụng web. Dịch vụ nhận diện các thuộc tính của HTTP(S) request, đối chiếu chúng với rule và quyết định cho phép, chặn, đếm hoặc yêu cầu client vượt qua thử thách. WAF giúp giảm nguy cơ từ các mẫu tấn công phổ biến như SQL injection, cross-site scripting (XSS), request bất thường, nguồn IP có uy tín xấu, bot tự động và lạm dụng endpoint.

Một luồng đơn giản:

~~~mermaid
flowchart LR
    C["Client / Bot"] --> E["CloudFront hoặc ALB / API Gateway"]
    E --> W["AWS WAF web ACL"]
    W -->|"Allow"| A["Ứng dụng / API"]
    W -->|"Block / Challenge / CAPTCHA"| X["Từ chối hoặc xác minh client"]
    A --> D["Dữ liệu và dịch vụ backend"]
~~~

AWS WAF được tích hợp tại điểm nhận request của tài nguyên được bảo vệ. Vì thế, rule phải phù hợp với vị trí gắn WAF và cấu trúc request mà điểm đó nhìn thấy. Nếu request đi qua CloudFront rồi mới đến ALB, địa chỉ nguồn mà ALB hoặc WAF nhìn thấy có thể là địa chỉ của proxy/CDN, tùy vị trí triển khai và cấu hình forwarded IP.

AWS WAF không thay thế:

- **Security groups và network ACL:** kiểm soát kết nối mạng theo địa chỉ, giao thức và cổng.
- **AWS Network Firewall:** kiểm tra và kiểm soát luồng mạng ở tầng mạng/transport trong VPC.
- **AWS Shield:** cung cấp bảo vệ DDoS; Shield Standard được tích hợp mặc định cho dịch vụ AWS, Shield Advanced bổ sung khả năng và hỗ trợ nâng cao.
- **Xác thực và phân quyền ứng dụng:** xác minh danh tính, quyền truy cập tài nguyên, session và business rules.
- **Kiểm soát bảo mật trong mã nguồn:** validate input, parameterized query, output encoding, secret management và cập nhật dependency.

WAF là lớp phòng thủ bổ sung. Một request vượt qua WAF vẫn phải được ứng dụng xác thực, phân quyền và kiểm tra dữ liệu.

## 2. Web ACL, scope và tài nguyên được bảo vệ

### 2.1. Web ACL là gì?

Web ACL là tài nguyên trung tâm chứa:

- Tên, mô tả, ARN và scope.
- Default action là Allow hoặc Block.
- Danh sách rule với priority, statement, action và visibility configuration.
- Rule group được tham chiếu, bao gồm managed rule group.
- Cấu hình CAPTCHA/Challenge, body inspection, custom response và logging.
- Metrics và cấu hình thu thập sampled requests.

Một web ACL có thể bảo vệ một hoặc nhiều tài nguyên tương thích. Nhiều ứng dụng có thể dùng chung một web ACL khi chính sách bảo vệ tương đồng; ứng dụng có yêu cầu khác nhau thường nên dùng web ACL riêng để tránh rule ngoại lệ của ứng dụng này ảnh hưởng ứng dụng khác.

### 2.2. Regional và CloudFront scope

AWS WAF có hai scope chính:

| Scope | Cách dùng | Region của tài nguyên WAF |
|---|---|---|
| REGIONAL | Bảo vệ tài nguyên regional như ALB, API Gateway REST API, AppSync, Cognito, App Runner, Amplify, Verified Access và Amazon Bedrock AgentCore Gateway. | Cùng Region với tài nguyên được bảo vệ. |
| CLOUDFRONT | Bảo vệ CloudFront distribution ở lớp edge toàn cầu. | Quản lý web ACL và các WAF resource liên quan tại us-east-1 (N. Virginia). |

Scope được chọn khi tạo web ACL và không thể đổi bằng cách chỉnh sửa web ACL hiện tại. Nếu chọn sai scope, thường phải tạo web ACL mới đúng scope rồi chuyển association.

Một số điểm vận hành:

- Web ACL REGIONAL phải ở cùng Region với ALB hoặc API regional.
- Web ACL CLOUDFRONT được quản lý tại us-east-1, dù distribution phục vụ người dùng toàn cầu.
- CloudFront distribution được liên kết qua cấu hình distribution; không dùng quy trình association giống ALB.
- Với ALB, API Gateway REST API và các tài nguyên regional được hỗ trợ, có thể dùng AssociateWebACL.
- ARN của WAF resource phản ánh scope. Với CloudFront, ARN sử dụng segment global; với tài nguyên regional, ARN sử dụng regional.

Không nhầm AWS WAF với AWS WAF Classic. Các tài nguyên mới nên dùng WAFv2 (wafv2 trong API/CLI và AWS::WAFv2::* trong CloudFormation).

### 2.3. Chọn điểm gắn WAF

| Kiến trúc | Điểm gắn WAF thường dùng | Điều cần kiểm tra |
|---|---|---|
| CloudFront → ALB → ECS | Web ACL CLOUDFRONT tại CloudFront; có thể bổ sung WAF regional ở ALB nếu cần chính sách riêng. | Ngăn truy cập trực tiếp ALB bỏ qua lớp edge; xác định nguồn IP thật. |
| Internet → ALB → EC2/ECS | Web ACL REGIONAL gắn ALB. | Security group chỉ nhận traffic cần thiết; body inspection giới hạn 8 KB. |
| API Gateway REST API → Lambda | Web ACL REGIONAL gắn REST API stage. | Kiểm tra stage/association, body inspection và API authentication. |
| AppSync GraphQL API | Web ACL REGIONAL. | Giới hạn body inspection; query depth/complexity vẫn cần kiểm soát ở tầng GraphQL/app. |
| Amazon Cognito user pool | Web ACL REGIONAL. | Có thể dùng rule chuyên biệt cho luồng đăng nhập và bảo vệ tài khoản. |

AWS WAF không gắn trực tiếp với mọi loại endpoint. Trước khi thiết kế, hãy xác minh resource type đang sử dụng có được hỗ trợ trong Region và scope đó hay không.

## 3. Cách AWS WAF đánh giá request

### 3.1. Priority và thứ tự xử lý

AWS WAF đánh giá rule theo priority số tăng dần: priority 0 chạy trước priority 10. Giá trị priority phải duy nhất trong cùng web ACL. Khi một rule tạo ra hành động kết thúc (terminating action), WAF dừng đánh giá các rule còn lại cho request đó.

Ví dụ:

| Priority | Rule | Action | Kết quả |
|---:|---|---|---|
| 0 | Chặn IP trong danh sách deny | Block | Request khớp bị chặn ngay. |
| 10 | AWS Managed Rules CRS | Theo rule trong group | Rule group có thể chặn hoặc tiếp tục. |
| 20 | Giới hạn tốc độ /login | Block khi vượt ngưỡng | Request bị rate limit bị chặn. |
| 30 | Gắn nhãn request nội bộ | Count | Đếm và tiếp tục xử lý. |
| — | Default action | Allow | Áp dụng nếu không có action kết thúc trước đó. |

Không nên sắp xếp rule chỉ theo tên. Hãy sắp xếp theo luồng xử lý mong muốn và hiểu rõ rule nào có thể kết thúc evaluation.

### 3.2. Default action

Default action được áp dụng nếu request không tạo ra terminating action trong quá trình đánh giá.

- **Allow:** phù hợp với website/API công khai cần chặn một số mẫu request đáng ngờ. Request không khớp rule sẽ được chuyển tới tài nguyên.
- **Block:** phù hợp với ứng dụng có danh sách endpoint/client được phép rõ ràng. Cần có rule Allow đủ bao phủ traffic hợp lệ trước khi áp dụng.

Default action chỉ có Allow hoặc Block. Không thể đặt default action là Count. Chọn default action quá rộng có thể tạo lỗ hổng; chọn Block mà thiếu allow rule có thể làm ứng dụng ngừng phục vụ người dùng hợp lệ.

### 3.3. Rule action

| Action | Loại | Hành vi |
|---|---|---|
| Allow | Kết thúc | Cho request đi tiếp tới tài nguyên được bảo vệ và dừng đánh giá rule. |
| Block | Kết thúc | Chặn request; mặc định trả HTTP 403, có thể cấu hình custom response. |
| Count | Không kết thúc | Ghi nhận request khớp rồi tiếp tục đánh giá rule kế tiếp. |
| CAPTCHA | Có điều kiện | Yêu cầu client giải CAPTCHA nếu token chưa hợp lệ/hết hạn; token hợp lệ thì tiếp tục như Count. |
| Challenge | Có điều kiện | Thực hiện thử thách trình duyệt im lặng; token hợp lệ thì tiếp tục như Count. |

CAPTCHA và Challenge phù hợp với trình duyệt truy cập HTTPS. Client API, ứng dụng di động hoặc webhook không có khả năng xử lý token có thể bị ảnh hưởng nếu áp dụng sai. Hai action này có tính phí bổ sung. Không nên dùng CAPTCHA/Challenge thay cho xác thực tài khoản hoặc chống brute force toàn diện.

### 3.4. Rule group action override và rule action override

Có hai mức override cần phân biệt:

- **Override toàn bộ kết quả rule group (OverrideAction: Count):** đưa kết quả của cả rule group về Count trong web ACL để kiểm thử. Các rule bên trong vẫn được đánh giá theo logic của group, nhưng kết quả group không chặn request.
- **Override một hoặc nhiều rule bên trong (RuleActionOverrides):** thay action của các rule được chỉ định, thường chuyển một rule nghi ngờ false positive sang Count trong khi các rule khác vẫn giữ action gốc.

Ví dụ, khi managed rule group chặn nhầm endpoint upload, hãy tìm rule ID cụ thể trong log rồi override riêng rule đó sang Count hoặc điều chỉnh phạm vi áp dụng. Không nên chuyển cả managed rule group sang Count dài hạn chỉ để xử lý một false positive.

## 4. Rule statement: định nghĩa request cần kiểm tra

Statement mô tả điều kiện để một rule khớp request. Có thể kết hợp statement bằng logic AND, OR, NOT và dùng scope-down statement để giới hạn tập request được đánh giá.

### 4.1. Match statement phổ biến

| Statement | Công dụng | Ví dụ |
|---|---|---|
| IPSetReferenceStatement | Khớp địa chỉ IPv4/IPv6 thuộc IP set. | Chặn IP nguồn đã xác định có hành vi tấn công. |
| GeoMatchStatement | Khớp quốc gia/vùng địa lý theo IP. | Đếm request từ khu vực không thuộc thị trường phục vụ. |
| ByteMatchStatement | Tìm chuỗi hoặc byte pattern trong request component. | Khớp URI bắt đầu bằng /admin. |
| RegexPatternSetReferenceStatement | So khớp regex pattern set. | Phát hiện đường dẫn hoặc tham số có định dạng đáng ngờ. |
| SizeConstraintStatement | Kiểm tra kích thước request component. | Phát hiện query string hoặc body vượt kích thước dự kiến. |
| SQLiMatchStatement | Phát hiện pattern SQL injection. | Kiểm tra query string hoặc body. |
| XssMatchStatement | Phát hiện pattern cross-site scripting. | Kiểm tra URI, query, body hoặc header. |
| LabelMatchStatement | Khớp label đã được rule trước gắn vào request. | Chặn hoặc đếm nhóm request được managed rule group phân loại. |
| RateBasedStatement | Đếm và giới hạn tốc độ theo khóa tổng hợp. | Giới hạn request đăng nhập theo IP trong cửa sổ thời gian. |

Request component có thể là URI path, query string, HTTP method, single header, all headers, cookies, body, JSON body và các thuộc tính fingerprint được hỗ trợ. Hãy chọn đúng component thay vì kiểm tra toàn bộ request không cần thiết.

### 4.2. Text transformation

Trước khi so khớp, WAF có thể biến đổi dữ liệu để chuẩn hóa request component. Một số transformation thường gặp gồm:

- LOWERCASE: chuyển chuỗi về chữ thường.
- URL_DECODE: giải mã URL encoding.
- HTML_ENTITY_DECODE: giải mã HTML entities.
- COMPRESS_WHITE_SPACE: chuẩn hóa khoảng trắng.
- CMD_LINE: chuẩn hóa một số ký tự thường gặp trong command line.
- NORMALIZE_PATH và NORMALIZE_PATH_WIN: chuẩn hóa đường dẫn theo quy tắc tương ứng.

Transformation được thực hiện theo thứ tự priority. Một chuỗi có thể thay đổi sau nhiều bước; hãy kiểm thử bằng request thực tế và tránh áp dụng transformation quá rộng làm tăng false positive.

### 4.3. Kết hợp điều kiện

Giả sử cần chặn request vào /admin từ IP không nằm trong mạng quản trị. Có thể dùng AND để kết hợp điều kiện URI path bắt đầu bằng /admin và điều kiện NOT đối với IP set cho phép. Điều kiện logic nên được thiết kế rõ ràng để người vận hành hiểu request nào bị chặn.

Không đưa managed rule group statement vào bên trong AND/OR/NOT. Managed rule group được tham chiếu trực tiếp như một rule trong web ACL. Rule group reference cũng không thể được lồng vào một statement khác.

## 5. Rate-based rule: giới hạn request theo tốc độ

Rate-based rule giúp giảm brute force, credential stuffing, scraping hoặc lạm dụng endpoint. WAF đếm request theo aggregation key và áp dụng action cho request vượt giới hạn.

Các cấu hình chính:

- Limit: ngưỡng request trong cửa sổ đánh giá; giá trị thấp nhất được phép là 10.
- EvaluationWindowSec: cửa sổ 60, 120, 300 hoặc 600 giây; mặc định 300 giây.
- AggregateKeyType: cách tổng hợp, thường là IP, forwarded IP, custom keys hoặc constant.
- ScopeDownStatement: giới hạn request được đưa vào bộ đếm, ví dụ chỉ URI /login.
- Action: Count, Block, CAPTCHA hoặc Challenge; rate-based rule không dùng Allow làm action giới hạn.

Giới hạn tốc độ được áp dụng gần ngưỡng cấu hình nhưng không phải một bộ đếm chính xác tuyệt đối. WAF đánh giá định kỳ và có thể có độ trễ khi lưu lượng tăng/giảm nhanh. Không dùng rate-based rule làm bộ quota nghiệp vụ cần độ chính xác giao dịch.

### 5.1. Ví dụ giới hạn endpoint đăng nhập

Một API có endpoint /login. Ta muốn theo dõi số request theo IP trong 5 phút và block khi vượt 500 request.

~~~yaml
- Name: RateLimitLogin
  Priority: 20
  Statement:
    RateBasedStatement:
      Limit: 500
      EvaluationWindowSec: 300
      AggregateKeyType: IP
      ScopeDownStatement:
        ByteMatchStatement:
          FieldToMatch:
            UriPath: {}
          PositionalConstraint: STARTS_WITH
          SearchString: /login
          TextTransformations:
            - Priority: 0
              Type: NONE
  Action:
    Block: {}
  VisibilityConfig:
    SampledRequestsEnabled: true
    CloudWatchMetricsEnabled: true
    MetricName: RateLimitLogin
~~~

Ví dụ chỉ minh họa cấu trúc rule. Ngưỡng 500 không phải khuyến nghị dùng chung; phải đo lưu lượng bình thường, phân biệt người dùng NAT chung và xác định hành vi của client trước khi chọn ngưỡng.

### 5.2. Chọn aggregation key

- **Source IP:** dùng địa chỉ IP nguồn mà WAF nhận được. Nếu request đi qua proxy hoặc load balancer, địa chỉ này có thể là proxy.
- **Forwarded IP:** đọc địa chỉ từ header được cấu hình, thường là X-Forwarded-For. Chỉ tin header do proxy tin cậy ghi đè; nếu client có thể tự gửi header mà upstream không loại bỏ/ghi lại, kẻ tấn công có thể giả mạo IP.
- **Custom keys:** kết hợp IP, HTTP method, header, cookie, query argument hoặc label namespace theo nhu cầu.
- **Constant:** gom tất cả request phù hợp vào một bộ đếm; phải có scope-down statement để xác định request được đếm.

Request thiếu một thành phần được chọn làm aggregation key có thể không được đưa vào instance tương ứng. Hãy kiểm tra cấu trúc request thực tế và fallback behavior khi dùng forwarded IP.

Mỗi rate-based rule có bộ đếm riêng. Hai rule giống nhau ở hai vị trí khác nhau không chia sẻ trạng thái đếm. Một rate-based rule nằm trong rule group cũng có phạm vi theo instance của group đó.

### 5.3. Rate limit không thay thế bảo vệ đăng nhập

Rate limit theo IP có thể ảnh hưởng người dùng hợp lệ ở văn phòng, trường học hoặc mạng di động dùng chung NAT. Đối với đăng nhập, nên kết hợp:

- Rate-based rule ở WAF để giảm burst traffic.
- Giới hạn theo tài khoản hoặc định danh tại ứng dụng.
- MFA, passwordless hoặc cơ chế xác thực chống credential stuffing.
- Theo dõi thất bại đăng nhập và phát hiện bất thường.
- Backoff, lockout có kiểm soát và quy trình khôi phục tài khoản.

WAF không biết đầy đủ ngữ cảnh tài khoản nghiệp vụ nếu request chưa được ứng dụng xác thực.

## 6. AWS Managed Rules và managed rule group

Managed rule group là tập hợp rule được một nhà cung cấp duy trì. Khi thêm managed rule group vào web ACL, WAF đánh giá các rule bên trong theo cấu hình do nhà cung cấp công bố. Nhóm vận hành có thể cấu hình version, scope-down statement và override action.

Managed rule group thường giúp triển khai lớp bảo vệ ban đầu nhanh hơn việc tự viết hàng chục rule. Tuy nhiên, managed rules không biết mọi đặc thù của ứng dụng. Cần kiểm thử với traffic thực và xem xét false positive trước khi bật Block.

### 6.1. Nhóm AWS Managed Rules phổ biến

| Nhóm | Mục đích | Khi cân nhắc |
|---|---|---|
| AWSManagedRulesCommonRuleSet (Core Rule Set/CRS) | Các mẫu khai thác web phổ biến, request bất thường và một số kiểm tra giao thức. | Lớp baseline cho nhiều website/API. |
| AWSManagedRulesKnownBadInputsRuleSet | Pattern request đã biết là đầu vào xấu. | Bổ sung cho CRS. |
| AWSManagedRulesSQLiRuleSet | Pattern liên quan SQL injection. | Ứng dụng có endpoint truy vấn dữ liệu. |
| AWSManagedRulesAmazonIpReputationList | IP có uy tín xấu theo dữ liệu AWS. | Chặn nguồn có dấu hiệu tấn công đã biết. |
| AWSManagedRulesAnonymousIpList | Nguồn như proxy ẩn danh, VPN hoặc Tor exit node theo danh sách AWS. | Khi chính sách ứng dụng cần đánh giá traffic ẩn danh. |
| Rule group cho Linux, Unix/POSIX, Windows, PHP hoặc WordPress | Pattern khai thác theo nền tảng/ứng dụng. | Chỉ bật khi stack có liên quan. |
| AWSManagedRulesAdminProtectionRuleSet | Bảo vệ các trang quản trị phổ biến. | Ứng dụng có endpoint quản trị phù hợp. |
| Bot Control | Phân loại và kiểm soát bot. | Website/API bị scraping hoặc tự động hóa; có chi phí bổ sung. |
| AWSManagedRulesATPRuleSet (Account Takeover Prevention) | Phát hiện hành vi chiếm đoạt tài khoản trong luồng đăng nhập. | Ứng dụng có nhu cầu bảo vệ đăng nhập và cấu hình tích hợp phù hợp. |
| AWSManagedRulesACFPRuleSet (Account Creation Fraud Prevention) | Phát hiện dấu hiệu gian lận trong luồng tạo tài khoản. | Dịch vụ mở tài khoản công khai có rủi ro abuse. |

Tên và khả năng của managed rule group có thể thay đổi theo thời gian. Hãy kiểm tra danh sách và tài liệu của nhà cung cấp trong Region/scope cần dùng trước khi triển khai. Hầu hết AWS Managed Rules baseline không tính phí riêng, nhưng một số nhóm nâng cao như Bot Control, ATP hoặc ACFP có tính phí bổ sung. Managed rule group từ AWS Marketplace có thể có phí đăng ký của nhà cung cấp.

### 6.2. Thêm managed rule group vào web ACL

Một managed rule group được khai báo bằng ManagedRuleGroupStatement, thường gồm:

- VendorName: AWS hoặc nhà cung cấp managed rule group.
- Name: tên rule group.
- Version: phiên bản nếu nhóm hỗ trợ versioning và muốn pin phiên bản cụ thể.
- ScopeDownStatement: giới hạn tập request được đánh giá.
- RuleActionOverrides: override action của từng rule con nếu cần.

Ví dụ CloudFormation:

~~~yaml
- Name: AWSManagedCommonRules
  Priority: 10
  OverrideAction:
    None: {}
  Statement:
    ManagedRuleGroupStatement:
      VendorName: AWS
      Name: AWSManagedRulesCommonRuleSet
      RuleActionOverrides:
        - Name: SizeRestrictions_BODY
          ActionToUse:
            Count: {}
  VisibilityConfig:
    SampledRequestsEnabled: true
    CloudWatchMetricsEnabled: true
    MetricName: AWSManagedCommonRules
~~~

Rule SizeRestrictions_BODY trong ví dụ được override thành Count để nhóm vận hành quan sát ảnh hưởng tới endpoint upload. Tên rule phải khớp chính xác tên được managed rule group công bố. Hãy kiểm tra log, sampled request và tài liệu của group trước khi áp dụng override.

### 6.3. Rule group versioning

Một số managed rule group cung cấp version:

- **Default version:** nhà cung cấp quản lý version được khuyến nghị. Với AWS Managed Rules có versioning, AWS gửi thông báo SNS trước khi chuyển default sang version tĩnh khác; các IP reputation rule groups là ngoại lệ không cung cấp versioning/SNS update notification.
- **Static version:** chọn một version cụ thể để có thời gian kiểm thử và phê duyệt trước khi nâng cấp. Version có vòng đời và có thể hết hạn.
- **LATEST:** luôn theo version tĩnh mới nhất. Tùy chọn này hiện được hỗ trợ cho AWS WAF Bot Control; thay đổi có thể đến mà không có thông báo trước theo cơ chế version thông thường.

Đừng pin một version rồi quên nâng cấp. Thiết lập quy trình nhận thông báo, thử nghiệm version mới, so sánh false positive và cập nhật trước ngày version cũ hết hạn.

### 6.4. Tuning managed rules

Quy trình an toàn:

1. Tạo web ACL trong môi trường staging hoặc test.
2. Bật managed rule group với Count/override phù hợp để quan sát traffic.
3. Gửi bộ request hợp lệ và request mô phỏng tấn công qua ứng dụng.
4. Bật logging, xem rule ID, label, URI, request component và action.
5. Xác định rule nào tạo false positive; kiểm tra endpoint và payload cụ thể.
6. Chỉ override rule cần thiết sang Count hoặc giới hạn group bằng scope-down statement.
7. Chạy Count trên production traffic trong khoảng thời gian đủ đại diện.
8. Chuyển sang action chặn theo từng nhóm rule; theo dõi metrics và lỗi ứng dụng sau rollout.

Không tạo allow rule rộng ở priority thấp hơn tất cả managed rules chỉ để bỏ qua false positive. Cách đó có thể khiến request độc hại cũng được cho qua và làm các rule bảo vệ phía sau không được đánh giá.

## 7. Scope-down statement và label

### 7.1. Scope-down statement

Scope-down statement thu hẹp tập request mà rule group hoặc rate-based rule đánh giá. Ví dụ:

- Chỉ áp dụng Bot Control cho URI /search và /catalog.
- Chỉ chạy SQLi managed rule group trên endpoint nhận dữ liệu tìm kiếm.
- Chỉ rate limit request có URI bắt đầu bằng /login.
- Chỉ kiểm tra request từ một nhóm quốc gia hoặc có label nhất định.

Scope-down statement là bộ lọc trước khi rule group/rate-based rule xử lý request. Nó không sửa nội dung của rule bên trong managed rule group. Statement được dùng trong scope-down phải là loại có thể lồng theo quy tắc WAF; managed rule group statement không thể được lồng vào scope-down.

### 7.2. Label

Rule có thể gắn label cho request khớp. Rule được đánh giá sau đó có thể dùng LabelMatchStatement để xử lý theo nhãn. Managed rule group cũng có thể phát label để mô tả loại request hoặc rule đã khớp.

Ví dụ về cách dùng label:

1. Managed rule group phát hiện request có dấu hiệu SQL injection nhưng được cấu hình Count để quan sát.
2. Rule sau đó kiểm tra label thuộc namespace của managed rule group.
3. Rule tùy chỉnh có thể block một nhóm label cụ thể, Count nhóm khác hoặc gắn thêm nhãn cho log/metrics.

Label namespace và tên label có phân biệt chữ hoa/chữ thường. Rule dùng label phải chạy sau rule tạo label. Nếu rule trước đã tạo terminating action, rule sau sẽ không được chạy.

## 8. WCU và giới hạn thiết kế

AWS WAF dùng Web ACL Capacity Units (WCU) để biểu diễn mức tài nguyên cần cho rule evaluation. Mỗi statement có chi phí WCU cơ bản; các yếu tố như regex, text transformation, JSON body inspection và logic lồng nhau có thể làm tăng WCU.

Một số giới hạn quan trọng theo tài liệu AWS hiện hành:

| Hạng mục | Giới hạn được công bố |
|---|---:|
| WCU tối đa của một web ACL | 5.000 |
| WCU tối đa của một rule group | 5.000 |
| Số rate-based rule tối đa trong một web ACL | 10 |
| Ngưỡng thấp nhất cho rate-based rule | 10 request |
| Số IP tối đa trong một IP set | 10.000 |
| Số reference statement trong web ACL | 50 |
| Số reference statement trong rule group | 50 |
| Ngưỡng WCU bắt đầu phát sinh chi phí ngoài giá cơ bản | Trên 1.500 WCU |

Các quota được áp dụng theo tài khoản và Region; một số quota cố định, một số có thể gửi yêu cầu tăng. Hãy kiểm tra trang AWS WAF quotas trước khi triển khai quy mô lớn vì quota và giá có thể thay đổi.

### 8.1. Lập ngân sách WCU

- Dùng managed rule group phù hợp với stack; không bật mọi group chỉ vì có sẵn.
- Kiểm tra WCU của managed rule group bằng thông tin provider/DescribeManagedRuleGroup.
- Tính WCU của rule tùy chỉnh và scope-down statement.
- Dùng IP set và regex pattern set để tái sử dụng dữ liệu thay vì tạo nhiều statement trùng lặp.
- Xem lại các text transformation và phạm vi body/JSON inspection.
- Dùng CheckCapacity hoặc công cụ kiểm tra capacity tương ứng trước khi cập nhật web ACL qua API/CLI.
- Theo dõi chi phí WCU, request inspection, managed group nâng cao, CAPTCHA/Challenge và logging.

WCU không phải giới hạn số rule đơn giản. Hai web ACL có cùng số rule có thể tiêu thụ WCU rất khác nhau tùy statement và độ phức tạp.

## 9. Giới hạn body inspection và oversize handling

AWS WAF chỉ kiểm tra phần request body mà dịch vụ nền chuyển tới WAF. Nếu body lớn hơn giới hạn, phần vượt quá không được WAF kiểm tra.

| Tài nguyên | Giới hạn body inspection |
|---|---|
| Application Load Balancer | Cố định 8 KB |
| AWS AppSync | Cố định 8 KB |
| CloudFront | Mặc định 16 KB; có thể tăng theo nấc 16 KB đến 64 KB |
| API Gateway, Cognito, App Runner, Verified Access, Bedrock AgentCore Gateway | Mặc định 16 KB; có thể tăng đến 64 KB theo cấu hình được hỗ trợ |
| AWS Amplify | Dùng giới hạn của CloudFront |

Tăng body inspection limit có thể làm phát sinh phí bổ sung cho phần traffic lớn hơn mức mặc định. AWS WAF không hỗ trợ request body inspection rule cho gRPC traffic. Khi tài nguyên nhận body lớn hơn giới hạn, phần dữ liệu bị cắt không được đưa vào quá trình match.

Với Body hoặc JsonBody, cần chọn OversizeHandling:

- CONTINUE: tiếp tục kiểm tra phần body WAF nhận được.
- MATCH: coi request là khớp statement.
- NO_MATCH: coi request không khớp statement.

Giá trị mặc định là CONTINUE. Nếu rule có action Block và chọn MATCH, request có body vượt giới hạn có thể bị block. Nếu chọn NO_MATCH, request lớn có thể đi qua rule đó mà không được kiểm tra. Hãy chọn dựa trên loại endpoint và cách ứng dụng xử lý payload.

Các request component khác cũng có giới hạn. Khi kiểm tra tất cả headers hoặc cookies, WAF có thể chỉ kiểm tra tối đa 8 KB và 200 thành phần đầu tiên. Kiểm tra một single header có thể áp dụng giới hạn khác. Hãy đọc giới hạn cụ thể cho component đang dùng.

## 10. Tạo web ACL bằng CloudFormation

Dưới đây là ví dụ web ACL regional cho một ALB. Web ACL dùng default Allow, thêm AWS Managed Rules Common Rule Set và rate-based rule cho /login. Rule SizeRestrictions_BODY được chuyển sang Count để có thể quan sát trước khi quyết định chặn payload lớn.

~~~yaml
Parameters:
  ApplicationLoadBalancerArn:
    Type: String
    Description: ARN of the regional Application Load Balancer to protect

Resources:
  ShopWebACL:
    Type: AWS::WAFv2::WebACL
    Properties:
      Name: shop-api-web-acl
      Description: Web ACL for the shop API
      Scope: REGIONAL
      DefaultAction:
        Allow: {}
      VisibilityConfig:
        SampledRequestsEnabled: true
        CloudWatchMetricsEnabled: true
        MetricName: shop-api-web-acl
      Rules:
        - Name: AWSManagedCommonRules
          Priority: 10
          OverrideAction:
            None: {}
          Statement:
            ManagedRuleGroupStatement:
              VendorName: AWS
              Name: AWSManagedRulesCommonRuleSet
              RuleActionOverrides:
                - Name: SizeRestrictions_BODY
                  ActionToUse:
                    Count: {}
          VisibilityConfig:
            SampledRequestsEnabled: true
            CloudWatchMetricsEnabled: true
            MetricName: aws-managed-common-rules
        - Name: RateLimitLogin
          Priority: 20
          Action:
            Block: {}
          Statement:
            RateBasedStatement:
              Limit: 500
              EvaluationWindowSec: 300
              AggregateKeyType: IP
              ScopeDownStatement:
                ByteMatchStatement:
                  FieldToMatch:
                    UriPath: {}
                  PositionalConstraint: STARTS_WITH
                  SearchString: /login
                  TextTransformations:
                    - Priority: 0
                      Type: NONE
          VisibilityConfig:
            SampledRequestsEnabled: true
            CloudWatchMetricsEnabled: true
            MetricName: rate-limit-login

  ShopWebACLAssociation:
    Type: AWS::WAFv2::WebACLAssociation
    Properties:
      WebACLArn: !GetAtt ShopWebACL.Arn
      ResourceArn: !Ref ApplicationLoadBalancerArn
~~~

Trong template thực tế, ApplicationLoadBalancerArn phải được truyền bằng parameter hoặc tham chiếu tới tài nguyên ALB được tạo trong cùng stack. Web ACL và ALB phải nằm cùng Region. Nếu triển khai cho CloudFront, đổi scope sang CLOUDFRONT, triển khai WAF resource ở us-east-1 và gắn ARN vào cấu hình CloudFront distribution; không dùng AWS::WAFv2::WebACLAssociation theo ví dụ ALB.

Trước khi deploy, hãy kiểm tra tên metric, rule name, WCU, quyền CloudFormation execution role và ảnh hưởng của association tới traffic production. Với stack đang tồn tại, thay đổi web ACL có thể tác động trực tiếp tới request đang phục vụ.

## 11. Quản lý bằng AWS CLI

Các lệnh dưới đây minh họa thao tác với web ACL regional ở ap-southeast-1.

Liệt kê web ACL:

~~~bash
aws wafv2 list-web-acls \
  --scope REGIONAL \
  --region ap-southeast-1
~~~

Lấy cấu hình một web ACL:

~~~bash
aws wafv2 get-web-acl \
  --name shop-api-web-acl \
  --scope REGIONAL \
  --id <WEB_ACL_ID> \
  --region ap-southeast-1
~~~

Liệt kê resource được hỗ trợ trong Region:

~~~bash
aws wafv2 list-resources-for-web-acl \
  --web-acl-arn <WEB_ACL_ARN> \
  --resource-type APPLICATION_LOAD_BALANCER \
  --region ap-southeast-1
~~~

Associate web ACL với ALB:

~~~bash
aws wafv2 associate-web-acl \
  --web-acl-arn <WEB_ACL_ARN> \
  --resource-arn <ALB_ARN> \
  --region ap-southeast-1
~~~

Kiểm tra web ACL gắn với một resource:

~~~bash
aws wafv2 get-web-acl-for-resource \
  --resource-arn <ALB_ARN> \
  --region ap-southeast-1
~~~

Disassociate web ACL khỏi ALB:

~~~bash
aws wafv2 disassociate-web-acl \
  --resource-arn <ALB_ARN> \
  --region ap-southeast-1
~~~

Với CloudFront, dùng --scope CLOUDFRONT và --region us-east-1 khi thao tác WAF resource. Việc gắn web ACL được thực hiện trong cấu hình CloudFront distribution. Không chạy lệnh disassociate trên production nếu chưa có kế hoạch thay thế lớp bảo vệ.

Khi cập nhật web ACL bằng API/CLI, GetWebACL trả về LockToken. Dùng token hiện hành cho UpdateWebACL; nếu cấu hình đã được thay đổi bởi một tiến trình khác, token cũ sẽ bị từ chối. Đọc lại web ACL trước khi cập nhật để tránh ghi đè thay đổi của nhóm khác.

## 12. Logging, metrics và visibility

### 12.1. CloudWatch metrics

Mỗi web ACL và rule có thể bật VisibilityConfig:

- CloudWatchMetricsEnabled: gửi metric sang Amazon CloudWatch.
- MetricName: tên metric; chỉ dùng ký tự được hỗ trợ, tránh tên reserved như All và Default_Action.
- SampledRequestsEnabled: bật thu thập mẫu request để xem request khớp rule.

Metrics giúp theo dõi số request Allowed, Blocked, Counted, CAPTCHA và Challenge theo web ACL/rule. Khi một rule được đổi action hoặc priority, so sánh metrics trước và sau thay đổi.

### 12.2. WAF logging

AWS WAF có thể ghi log request tới:

- Amazon CloudWatch Logs.
- Amazon S3.
- Amazon Data Firehose delivery stream.

Tên log destination phải tuân thủ prefix aws-waf-logs- theo loại đích. Log thường chứa action, terminating rule, rule group, labels, thông tin HTTP request và các trường liên quan để điều tra. Bật log filter để giữ các record quan trọng như Block, CAPTCHA, Challenge hoặc request có label cụ thể, đồng thời kiểm soát dung lượng log.

Ví dụ log giúp trả lời:

- Request bị chặn bởi rule nào?
- Managed rule group phát label gì?
- URI, method hoặc header nào khiến request khớp?
- Request có bị rate limit không?
- Thay đổi rule gần đây có làm tăng false positive không?

### 12.3. Bảo vệ dữ liệu nhạy cảm

Request log và sampled request có thể chứa session ID, token, email, query parameter hoặc dữ liệu cá nhân. Hãy:

- Dùng data protection để bảo vệ trường nhạy cảm trong dữ liệu log và sampled request theo khả năng cấu hình.
- Dùng RedactedFields cho URI path, query string, single header và HTTP method trong logging configuration khi phù hợp.
- Lưu ý field redaction của logging không tự áp dụng lên sampled requests.
- Tắt sampling hoặc cấu hình data protection nếu request sample có thể chứa secret/PII.
- Giới hạn IAM quyền đọc log, mã hóa log destination và đặt retention phù hợp.
- Không đưa access token, password hoặc dữ liệu thẻ thanh toán vào URL/query string.

Redaction chỉ tác động tới thành phần request được cấu hình tương ứng. Ví dụ redaction SingleHeader không tự che dữ liệu từ rule dùng Headers để match. Hãy kiểm tra cấu hình logging và sampling riêng.

## 13. Kiểm thử và triển khai an toàn

AWS khuyến nghị kiểm thử và tune web ACL trước khi áp dụng cho traffic production. Một lộ trình thực tế:

1. **Tạo staging:** gắn web ACL vào môi trường thử nghiệm có request tương tự production.
2. **Bật logging và metrics:** bảo đảm có thể xác định rule ID, label, request component và action.
3. **Chạy test case hợp lệ:** đăng nhập, tìm kiếm, upload, API pagination, webhook, mobile client và luồng quản trị.
4. **Chạy test case bảo mật:** payload SQLi/XSS thử nghiệm, URI bất thường, request vượt ngưỡng, IP deny và request body lớn.
5. **Bật Count:** chuyển rule hoặc managed rule group cần đánh giá sang Count trên traffic thật trong thời gian đại diện.
6. **Đọc false positive:** đối chiếu request bị match với nghiệp vụ, không dựa riêng vào tên rule.
7. **Override tối thiểu:** sửa đúng rule, statement hoặc scope-down gây vấn đề.
8. **Chuyển dần sang Block/Challenge:** rollout theo nhóm rule và theo dõi error rate, conversion, API latency và số request bị chặn.
9. **Chuẩn bị rollback:** lưu cấu hình trước thay đổi và quy trình cập nhật web ACL trở lại phiên bản an toàn.
10. **Theo dõi sau rollout:** đặt cảnh báo cho tăng đột biến BlockedRequests, CountedRequests, CAPTCHA/Challenge và lỗi ứng dụng.

Count mode không đảm bảo request sẽ được cho qua trong mọi tình huống nếu một rule khác trước đó đã tạo terminating action. Khi thử nghiệm, hãy kiểm tra toàn bộ thứ tự priority và default action.

## 14. Tích hợp với ứng dụng Java và Spring Boot

AWS WAF nằm trước ứng dụng nên không yêu cầu ứng dụng Java phải gọi WAF SDK cho mỗi request. Nhóm backend chủ yếu phối hợp qua hợp đồng HTTP và vận hành:

- Xác định endpoint công khai, endpoint đăng nhập, upload, search và admin.
- Ghi log ứng dụng có correlation ID để liên kết với WAF log; không ghi secret hoặc PII không cần thiết.
- Định nghĩa ngưỡng rate limit dựa trên hành vi client và tải thực tế.
- Trả mã lỗi ổn định khi WAF Block; ứng dụng có thể nhận 403 trước khi request tới backend.
- Nếu dùng CAPTCHA/Challenge, frontend cần hỗ trợ token/cookie và luồng retry phù hợp.
- Nếu ứng dụng nằm sau CloudFront hoặc ALB, xác định rõ nguồn IP tin cậy và cách proxy ghi forwarded header.

Một ví dụ: Spring Boot có endpoint /api/login, /api/search và /api/files. WAF có thể dùng rate-based rule cho /api/login, managed rule group baseline cho toàn web ACL, scope-down SQLi rule group cho endpoint tìm kiếm và kiểm tra body size phù hợp với endpoint upload. Ứng dụng vẫn phải dùng password hashing, MFA, parameterized SQL, validation và authorization.

## 15. Tình huống thiết kế: bảo vệ cửa hàng trực tuyến

Một cửa hàng trực tuyến triển khai CloudFront trước ALB, backend chạy ECS và dữ liệu ở RDS. Yêu cầu gồm chặn request độc hại, giảm bot scraping, hạn chế brute force đăng nhập và bảo vệ API.

Thiết kế có thể triển khai:

- Web ACL CLOUDFRONT gắn với distribution để lọc traffic ở edge.
- AWS Managed Rules CRS và Known Bad Inputs để làm baseline; bật Count trước khi chuyển các rule sang Block.
- IP reputation managed rule group để xử lý nguồn có dấu hiệu xấu.
- Rate-based rule có scope-down /login và /api/auth, với ngưỡng riêng cho browser/mobile clients.
- Bot Control nếu scraping hoặc automation là rủi ro đáng kể và ngân sách cho phép.
- WAF regional tại ALB khi cần chính sách riêng; security group ALB chỉ nhận traffic từ CloudFront origin-facing prefix list hoặc nguồn được phê duyệt.
- CloudWatch metrics, WAF logs và cảnh báo cho BlockedRequests, rate limit và false positive.
- IAM role và pipeline triển khai web ACL qua CloudFormation, có review thay đổi và rollback.

Không áp dụng cùng một ngưỡng rate limit cho mọi endpoint. /health, static assets, login, search và upload có đặc tính request khác nhau. Đặc biệt, nếu ALB vẫn truy cập trực tiếp từ Internet, người dùng có thể bỏ qua web ACL CloudFront; cần bảo vệ origin bằng network controls và cấu hình truy cập phù hợp.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Request hợp lệ nhận 403 | Managed rule false positive, rule custom quá rộng, thứ tự priority hoặc default Block. | Tìm terminating rule trong WAF log; chuyển đúng rule sang Count để xác minh. |
| Rate limit chặn người dùng chung mạng | Nhiều người dùng chia sẻ một public IP/NAT. | Chọn ngưỡng khác, aggregation key phù hợp hoặc scope-down cụ thể. |
| Rate limit không nhận IP client | WAF thấy IP proxy/CDN hoặc forwarded header không đúng. | Kiểm tra topology và upstream có ghi đè header tin cậy không. |
| SQLi/XSS rule không phát hiện payload lớn | Body vượt giới hạn WAF inspect. | Kiểm tra body size limit và OversizeHandling; cân nhắc tăng limit nếu được hỗ trợ. |
| Managed rule group không được đánh giá | Sai vendor/name/version, sai scope, scope-down loại request hoặc group chưa được thêm vào web ACL. | Kiểm tra cấu hình ManagedRuleGroupStatement, WCU và log. |
| UpdateWebACL bị từ chối | LockToken đã cũ hoặc thiếu quyền. | Gọi GetWebACL, lấy LockToken mới và kiểm tra IAM. |
| CloudFront không nhận web ACL | Dùng nhầm regional scope hoặc Region. | Dùng scope CLOUDFRONT, Region us-east-1, cập nhật distribution config. |
| Không thấy request sample | Sampling bị tắt, request không match rule, hoặc cấu hình data protection. | Kiểm tra VisibilityConfig và log; không dùng sample làm nguồn audit đầy đủ. |
| Log không đến đích | Sai prefix destination, quyền service-linked role, policy S3/KMS hoặc Firehose. | Kiểm tra logging configuration, IAM, bucket/key policy và trạng thái delivery. |
| WCU vượt capacity | Nhiều managed group hoặc statement phức tạp. | Dùng CheckCapacity, rà soát WCU và bỏ rule trùng lặp. |

## 17. Bài thực hành: bảo vệ API regional bằng WAF

Mục tiêu: tạo web ACL regional, thêm managed rule group và rate-based rule, gắn với ALB staging, bật metrics/logging và kiểm thử false positive.

### Bước 1: Xác định scope và tài nguyên

- Chọn Region của ALB, ví dụ ap-southeast-1.
- Xác định ARN ALB, listener, target group và endpoint cần bảo vệ.
- Xác nhận ALB không được truy cập ngoài các nguồn đã phê duyệt.
- Chọn default action phù hợp với mô hình traffic; với API công khai, có thể bắt đầu bằng Allow và thêm rule chặn.

### Bước 2: Tạo web ACL

Tạo web ACL REGIONAL với DefaultAction Allow, bật metrics và sampled requests cho staging. Thêm AWSManagedRulesCommonRuleSet với override Count cho các rule có khả năng ảnh hưởng endpoint upload.

### Bước 3: Thêm rate-based rule

Tạo rule giới hạn /login theo IP. Bắt đầu bằng Count, quan sát traffic giờ cao điểm và traffic NAT chung. Chỉ chuyển sang Block khi ngưỡng đã được kiểm chứng.

### Bước 4: Gắn web ACL vào ALB

Dùng CloudFormation association hoặc aws wafv2 associate-web-acl. Kiểm tra lại bằng get-web-acl-for-resource và xác minh request thực tế đi qua ALB được đánh giá.

### Bước 5: Bật logging và metrics

Gửi log tới CloudWatch Logs hoặc S3/Firehose với destination tuân thủ prefix. Kiểm tra metric cho web ACL và từng rule. Cấu hình data protection/redaction cho trường nhạy cảm.

### Bước 6: Kiểm thử

- Gửi request hợp lệ tới login, search, upload.
- Gửi request thử nghiệm có pattern SQLi/XSS trong môi trường test.
- Gửi nhiều request trong thời gian ngắn để kiểm tra rate rule.
- Xem log để xác định terminating rule, label và action.
- Chuyển rule false positive sang Count, điều chỉnh scope-down hoặc inspection component.
- Lặp lại kiểm thử trước khi bật Block.

### Bước 7: Chuẩn bị vận hành

Lưu template CloudFormation trong repository, yêu cầu review thay đổi, đặt cảnh báo cho tỷ lệ Block tăng cao, ghi lại owner của từng rule và định kỳ rà soát managed rule version. Thực hiện rollback bằng template/configuration đã được phê duyệt nếu traffic hợp lệ bị chặn.

## 18. Những hiểu lầm cần tránh

1. **Có WAF là ứng dụng đã an toàn.** WAF chỉ lọc request theo rule; ứng dụng vẫn phải xác thực, phân quyền và validate dữ liệu.
2. **Managed Rules phù hợp với mọi ứng dụng.** Managed group cần được tune theo endpoint và payload thực tế.
3. **Count nghĩa là request chắc chắn được Allow.** Rule sau hoặc rule trước có thể tạo terminating action; default action vẫn quyết định khi không có terminating action.
4. **Priority lớn chạy trước.** Priority số nhỏ chạy trước.
5. **Rate limit là quota chính xác.** WAF áp dụng gần ngưỡng, không phải bộ đếm giao dịch chính xác.
6. **X-Forwarded-For luôn đáng tin.** Chỉ tin header do proxy tin cậy kiểm soát.
7. **WAF kiểm tra toàn bộ body.** WAF chỉ nhận phần body trong giới hạn của resource.
8. **RedactedFields che dữ liệu trong sampled requests.** Field redaction của logging không áp dụng cho sampling.
9. **Tất cả managed rule group đều miễn phí.** Một số nhóm nâng cao và Marketplace group có phí riêng.
10. **Có thể đổi scope của web ACL sau khi tạo.** Scope cần chọn đúng ngay từ đầu; sai scope thường phải tạo resource mới.
11. **Một web ACL CloudFront nằm trong Region của người dùng.** WAF resource cho CloudFront được quản lý ở us-east-1.
12. **Block rule đầu tiên luôn là rule tốt nhất.** Rule Allow/Block kết thúc evaluation; thứ tự phải phản ánh chính sách.
13. **Tăng WCU chỉ cần tăng quota.** Web ACL có giới hạn cố định 5.000 WCU; trên 1.500 WCU có thể phát sinh phí bổ sung.
14. **WAF thay thế chống brute force ở tầng tài khoản.** Rate limit theo IP cần phối hợp với kiểm soát theo tài khoản và MFA.

## 19. Câu hỏi tự kiểm tra

**1. Web ACL regional bảo vệ ALB ở Region nào?**

Web ACL phải ở cùng Region với ALB. Với CloudFront, WAF resource được quản lý tại us-east-1.

**2. Rule có priority 5 và priority 20, rule nào chạy trước?**

Priority 5 chạy trước vì AWS WAF đánh giá theo số priority tăng dần.

**3. Điều gì xảy ra khi rule Count khớp request?**

WAF ghi nhận request và tiếp tục đánh giá rule kế tiếp.

**4. Vì sao Allow rule đặt đầu danh sách có thể làm rule Block phía sau không chạy?**

Allow là terminating action nên WAF dừng evaluation khi request khớp.

**5. Khi nào dùng OverrideAction Count cho managed rule group?**

Khi cần quan sát tác động của cả group trong giai đoạn kiểm thử mà chưa muốn group chặn request.

**6. Khi nào dùng RuleActionOverrides?**

Khi chỉ một hoặc vài rule con tạo false positive và cần thay action riêng cho các rule đó.

**7. Vì sao rate-based rule theo source IP có thể ảnh hưởng nhiều người dùng?**

Nhiều người dùng có thể chia sẻ một public IP thông qua NAT hoặc proxy.

**8. Khi nào có thể dùng forwarded IP?**

Khi request đi qua proxy tin cậy và proxy kiểm soát header forwarded IP, loại bỏ giá trị client giả mạo.

**9. WAF có kiểm tra toàn bộ body lớn hơn giới hạn inspection không?**

Không. WAF chỉ nhận phần body được tài nguyên chuyển tới trong giới hạn cấu hình.

**10. Scope-down statement có tác dụng gì?**

Nó giới hạn request được đánh giá bởi rate-based rule hoặc managed rule group, ví dụ chỉ endpoint /login.

**11. Managed rule group version tĩnh có lợi ích gì?**

Giúp nhóm vận hành kiểm thử và phê duyệt version trước khi thay đổi rule đang bảo vệ production.

**12. Field redaction trong logging có che sampled requests không?**

Không. Cần dùng data protection cho sampled request hoặc tắt sampling nếu có dữ liệu nhạy cảm.

## 20. Checklist vận hành production

- [ ] Web ACL dùng đúng scope và Region.
- [ ] Chỉ association với resource được phê duyệt.
- [ ] Default action phù hợp với mô hình truy cập.
- [ ] Rule priority và terminating action đã được review.
- [ ] Managed rule group đã chạy Count và tune trên traffic đại diện.
- [ ] Version managed rule có quy trình nhận thông báo/nâng cấp.
- [ ] Rate-based rule có ngưỡng và aggregation key dựa trên dữ liệu thực.
- [ ] Forwarded IP chỉ dùng khi proxy được tin cậy và kiểm soát header.
- [ ] Body inspection limit và oversize handling phù hợp từng endpoint.
- [ ] WCU và chi phí được ước lượng.
- [ ] CloudWatch metrics, WAF logging và cảnh báo hoạt động.
- [ ] Log/sample được bảo vệ khỏi secret và PII.
- [ ] CloudFormation hoặc IaC là nguồn cấu hình có review.
- [ ] Có quy trình rollback và owner cho từng rule.
- [ ] Có lịch rà soát false positive, quota, chi phí và managed rule updates.

## Tài liệu tham khảo

- [Configuring protection in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl.html)
- [Resources that you can protect with AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html)
- [Associating or disassociating protection with an AWS resource](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-associating-aws-resource.html)
- [How AWS WAF handles rule and rule group actions](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-rule-actions.html)
- [Using match rule statements in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statements-match.html)
- [Aggregating rate-based rules in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html)
- [Using managed rule groups in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-using-managed-rule-groups.html)
- [AWS Managed Rules rule groups list](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-list.html)
- [Using versioned managed rule groups](https://docs.aws.amazon.com/waf/latest/developerguide/waf-managed-rule-groups-versioning.html)
- [Overriding rule group actions](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-rule-group-override-options.html)
- [Testing and tuning your AWS WAF protections](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-testing.html)
- [Web ACL capacity units (WCUs)](https://docs.aws.amazon.com/waf/latest/developerguide/aws-waf-capacity-units.html)
- [AWS WAF quotas](https://docs.aws.amazon.com/waf/latest/developerguide/limits.html)
- [Considerations for managing body inspection](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-setting-body-inspection-limit.html)
- [Configuring logging for a protection pack (web ACL)](https://docs.aws.amazon.com/waf/latest/developerguide/logging-management-configure.html)
- [AWS::WAFv2::WebACL CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-wafv2-webacl.html)

