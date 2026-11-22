# CloudFront distribution, origin và cache behavior

Khi một ứng dụng web có người dùng tại nhiều khu vực, việc mọi yêu cầu đều đi thẳng về máy chủ gốc (*origin*) có thể làm tăng độ trễ, lưu lượng, chi phí và áp lực lên hệ thống. **Amazon CloudFront** là dịch vụ mạng phân phối nội dung (**CDN – Content Delivery Network**) của AWS. CloudFront tiếp nhận yêu cầu tại các điểm mạng biên (*edge locations*), phục vụ nội dung có thể cache và chuyển những yêu cầu còn lại tới origin theo chính sách của **distribution**.

Ba khái niệm phải phân biệt rõ:

- **Distribution**: cấu hình phân phối nội dung của CloudFront, gồm tên miền, chứng chỉ, origins, cache behaviors, chính sách bảo mật và logging.
- **Origin**: nơi có dữ liệu hoặc ứng dụng gốc, chẳng hạn **Amazon S3**, **Application Load Balancer (ALB)**, một HTTP server hay API endpoint.
- **Cache behavior**: quy tắc khớp đường dẫn yêu cầu, chọn origin và quy định cache, phương thức HTTP, HTTPS và các policy kèm theo.

Bài học thuộc chương **DNS và phân phối nội dung**, mô-đun **CLOUD_PROVIDERS_AWS**. Người học kết nối CloudFront với Region/AZ, IAM, VPC, compute, lưu trữ, cơ sở dữ liệu, tích hợp và serverless để thiết kế ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả luồng **viewer → CloudFront edge → origin** và phân biệt **cache hit/miss**.
2. Tạo mô hình distribution có nhiều origins và nhiều cache behaviors; hiểu **default behavior** và thứ tự **path pattern**.
3. Chọn đúng **S3 bucket origin**, **custom origin**, **origin group** và những giới hạn tương ứng.
4. Phân biệt **cache policy**, **origin request policy**, **response headers policy** và cấu hình TTL.
5. Cấu hình HTTPS, tên miền/Route 53, **Origin Access Control (OAC)**, WAF và giới hạn quyền truy cập.
6. Thiết kế caching cho file tĩnh, API public và API cá nhân hóa mà không vô tình làm lộ dữ liệu giữa người dùng.
7. Kiểm chứng hoạt động bằng AWS CLI, HTTP headers, log/metric; triển khai invalidation và xử lý sự cố thường gặp.

## 2. Kiến trúc hoạt động của CloudFront

~~~mermaid
flowchart LR
    USER["Viewer<br/>Trình duyệt / ứng dụng"] -->|"HTTPS + DNS"| EDGE["CloudFront edge<br/>Distribution"]
    EDGE -->|"Cache hit: trả ngay"| USER
    EDGE -->|"Cache miss / hết TTL"| ORIGIN{"Cache behavior chọn origin"}
    ORIGIN -->|"assets/*"| S3["S3 bucket origin<br/>Ảnh, JS, CSS"]
    ORIGIN -->|"api/*"| ALB["ALB / API origin<br/>Ứng dụng động"]
    S3 --> EDGE
    ALB --> EDGE
~~~

Luồng cơ bản:

1. Người dùng truy cập một tên miền, ví dụ **www.example.com**. DNS đưa người dùng đến CloudFront distribution tương ứng.
2. CloudFront xác định **cache behavior** theo **đường dẫn URL**, ví dụ **/assets/logo.png** hoặc **/api/orders**.
3. CloudFront tạo **cache key** theo cache policy và tìm phản hồi còn hiệu lực tại lớp cache liên quan.
4. Nếu có bản cache phù hợp và còn hợp lệ (**hit**), CloudFront phục vụ phản hồi mà không cần gọi origin.
5. Nếu không có bản cache hợp lệ (**miss**), CloudFront gửi **origin request** theo policy để lấy nội dung; phản hồi có thể được cache tùy loại request và cấu hình TTL.

CloudFront dùng mạng biên toàn cầu nhưng **origin vẫn có vị trí, quota và cơ chế bảo vệ riêng**. CloudFront không thay thế khả năng chịu lỗi của database, ứng dụng, ALB hoặc Region. Khi origin mất khả năng hoạt động, đối với nội dung chưa được cache hoặc request động, ứng dụng vẫn có thể lỗi nếu không có kiến trúc dự phòng tương ứng.

### 2.1. Cache hit, cache miss và cache expiry

| Khái niệm | Giải thích | Tác động |
|---|---|---|
| **Cache hit** | Bản phản hồi phù hợp cache key đã tồn tại, còn dùng được | Giảm độ trễ và tải về origin |
| **Cache miss** | Chưa có bản cache thích hợp hoặc yêu cầu cần truy vấn origin | Tốn request và có thể tốn lưu lượng origin |
| **TTL** | Khoảng thời gian CloudFront xem nội dung cache là hợp lệ theo policy/headers | TTL dài có thể tăng hit ratio nhưng chậm cập nhật nội dung |
| **Cache key** | Tập thuộc tính dùng phân biệt các biến thể của phản hồi | Key quá rộng làm giảm hit; key quá hẹp có thể trả sai biến thể |
| **Invalidation** | Yêu cầu CloudFront loại bỏ bản cache theo đường dẫn | Cho phép lấy nội dung mới trước khi TTL hết, có thể phát sinh chi phí |

**Không nhầm lẫn:** DNS TTL của Route 53 hoặc nhà cung cấp DNS **khác** với CloudFront cache TTL. DNS TTL liên quan thời gian cache bản ghi tên miền; CloudFront TTL điều khiển độ mới của nội dung ở CDN.

## 3. CloudFront distribution: những thành phần chính

Distribution là đối tượng cấp cao dùng để tổ chức các origins, behaviors và cách người dùng truy cập. Một standard distribution điển hình có:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| **Distribution ID** | E123EXAMPLEID | Định danh quản trị qua API/CLI |
| **Distribution domain name** | d111example.cloudfront.net | Tên miền do CloudFront cấp |
| **Alternate domain names** | www.example.com | Tên miền của doanh nghiệp cần cấu hình certificate/DNS |
| **Viewer certificate** | ACM certificate cho www.example.com | TLS giữa người dùng và CloudFront |
| **Origins** | S3 bucket, ALB | Nguồn nội dung/ứng dụng |
| **Default cache behavior** | **\*** | Quy tắc bắt buộc khi request không khớp behavior nào khác |
| **Ordered cache behaviors** | /assets/*, /api/* | Các quy tắc theo đường dẫn với thứ tự xét cụ thể |
| **Security/logging** | AWS WAF, access logs | Bảo vệ, ghi nhận lưu lượng và phân tích sự cố |

Khi tạo hoặc cập nhật distribution, thay đổi cần được **triển khai ra hệ thống CloudFront**; trạng thái cập nhật có thể là **InProgress** trước khi thành **Deployed**. Do đó, cấu hình mới lưu thành công không đồng nghĩa toàn bộ edge đã áp dụng ngay tức thì.

### 3.1. Tên miền riêng, DNS và HTTPS

Để dùng **https://www.example.com**, bạn cần:

1. Thêm **www.example.com** vào **Alternate domain names** của distribution.
2. Gắn certificate hợp lệ, bao phủ tên miền đó. **ACM certificate dùng cho CloudFront viewer phải nằm tại Region us-east-1** (US East – N. Virginia).
3. Tạo DNS record phù hợp. Với **Route 53**, dùng **A/AAAA Alias** trỏ đến CloudFront; DNS nhà cung cấp khác thường dùng CNAME cho subdomain.
4. Kiểm tra **viewer protocol policy** để yêu cầu HTTPS, TLS security policy và HTTP versions được phép.

**Zone apex** như **example.com** không dùng CNAME thông thường theo quy tắc DNS; Route 53 hỗ trợ **Alias A/AAAA** tại apex. Nếu bật IPv6 cho viewer, kiểm tra record AAAA tương ứng. Distribution không bắt buộc phải dùng Route 53; bạn có thể quản trị DNS ở nhà cung cấp khác nếu đáp ứng yêu cầu tên miền.

### 3.2. Viewer protocol và origin protocol là hai chặng khác nhau

~~~mermaid
flowchart LR
    U["Viewer"] -->|"Chặng 1:<br/>HTTPS đến CloudFront"| C["CloudFront"]
    C -->|"Chặng 2:<br/>HTTPS đến custom origin"| O["ALB / custom origin"]
~~~

- **Viewer protocol policy** ở cache behavior có thể cho phép HTTP/HTTPS, **Redirect HTTP to HTTPS**, hoặc chỉ **HTTPS Only**.
- **Origin protocol policy** của **custom origin** quyết định CloudFront kết nối tới origin qua HTTP Only, HTTPS Only hoặc Match Viewer theo khả năng hỗ trợ.
- Với **S3 bucket origin + OAC** cấu hình **Sign requests (recommended)**, CloudFront ký request tới S3 và dùng HTTPS cho đường này theo chế độ tương ứng.

Chỉ bật HTTPS giữa viewer và CloudFront **không đủ** nếu đường CloudFront → custom origin vẫn HTTP và dữ liệu nhạy cảm yêu cầu mã hóa end-to-end. Khi bật HTTPS tới custom origin, certificate của origin phải hợp lệ và khớp tên miền được dùng để kết nối, nếu không có thể xuất hiện **502 Bad Gateway**.

## 4. Origin: nơi lấy dữ liệu gốc

### 4.1. Các loại origin phổ biến

| Loại | Ví dụ | Phù hợp | Điều cần kiểm tra |
|---|---|---|---|
| **S3 bucket origin** | Bucket ảnh, CSS, JS, tài liệu public qua CloudFront | Static assets và nội dung object | **OAC**, bucket policy, KMS, object key, cache headers |
| **Custom origin: ALB** | Java Spring Boot chạy trên EC2/ECS sau ALB | API, SSR/HTML động | HTTPS origin, SG/WAF, target health, timeouts |
| **Custom origin: HTTP server** | Reverse proxy hoặc hệ thống on-prem có endpoint hợp lệ | Di chuyển ứng dụng hoặc hybrid | DNS, Internet/đường riêng phù hợp, TLS và origin capacity |
| **Custom origin: API endpoint** | API Gateway hoặc backend HTTP hỗ trợ | API tĩnh/động | Header **Host**, authorization, stage/path, caching |
| **Origin group** | Primary và secondary origins | Failover khi origin chính lỗi trong phạm vi hỗ trợ | Status codes, HTTP methods và tính tương thích dữ liệu |

Một distribution có thể chứa **nhiều origin**, nhưng **mỗi cache behavior chọn một origin hoặc origin group đích**. CloudFront không tự suy ra rằng đường **/api/** cần ALB còn **/images/** cần S3; người thiết kế phải cấu hình các behavior và origin ID tương ứng.

### 4.2. S3 bucket endpoint so với S3 website endpoint

Đây là khác biệt bảo mật quan trọng:

| Phương án | CloudFront xem như | Bảo vệ truy cập |
|---|---|---|
| **S3 bucket origin thông thường** | S3 origin | Có thể dùng **Origin Access Control (OAC)** với ký request; bucket có thể giữ private |
| **S3 static website endpoint** | **Custom origin** | **Không hỗ trợ OAC/OAI** với endpoint website; phải thiết kế truy cập công khai và hạn chế phù hợp |

Đối với website tĩnh chỉ cần HTML/CSS/JS, lựa chọn thường được khuyến nghị là **S3 bucket private + CloudFront OAC**, thay vì mở public bucket chỉ để CDN đọc. Nếu cần những tính năng website endpoint cụ thể như redirect do S3 website hosting cung cấp, phải nhận biết điểm đánh đổi về quyền truy cập và cân nhắc xử lý redirect/rewrite ở CloudFront/application thay thế.

### 4.3. Origin Access Control (OAC) cho S3 private

**OAC** cho phép CloudFront ký các yêu cầu đến S3 với service principal CloudFront. Bucket policy có thể giới hạn quyền đọc vào **một distribution cụ thể** thông qua condition **AWS:SourceArn**.

Ví dụ bucket policy **chỉ đọc** (account/distribution/bucket giả định; cần thay bằng ARN thật):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontReadWithOAC",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudfront.amazonaws.com"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::web-assets-demo-example/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::111122223333:distribution/E123EXAMPLEID"
        }
      }
    }
  ]
}
~~~

Điều kiện trong ví dụ giúp hạn chế quyền của CloudFront đến đúng distribution. Cần đồng thời:

- Tạo OAC, gắn với **S3 bucket origin**, chọn phương án **Sign requests** phù hợp (khuyến nghị **always**), cập nhật và chờ distribution triển khai.
- Đặt S3 **Block Public Access** thích hợp và xác minh object ownership, bucket policy, object key.
- Nếu object dùng **SSE-KMS** với customer managed key, xác minh **KMS key policy** cho phép CloudFront sử dụng key theo hướng dẫn.
- Không vô tình giữ các bucket policy/public ACL quá rộng sau khi chuyển sang OAC.

**OAC không đồng nghĩa nội dung chỉ người dùng được xác thực mới xem được.** OAC chỉ hạn chế **CloudFront → S3 origin**; nếu viewer không bị kiểm soát, bất kỳ ai biết URL CloudFront vẫn có thể tải nội dung được phân phối. Với nội dung trả phí/riêng tư, cần cơ chế kiểm soát ở lớp viewer như **signed URLs/signed cookies**, ứng dụng xác thực hoặc biện pháp tương ứng.

### 4.4. Custom origin và origin path

Với **ALB**, **API endpoint** hoặc HTTP server, cần cấu hình:

- **Origin domain name** đúng với DNS/certificate.
- **Origin protocol policy** và port/timeout phù hợp.
- **Origin path** nếu cần thêm một prefix cố định vào đường dẫn gửi tới origin.
- Các header cần forward, security group/firewall, network và tính sẵn sàng của dịch vụ gốc.

Ví dụ custom origin có **Origin path = /backend** và viewer request **/api/products** có thể được gửi tới origin với path **/backend/api/products**. Không coi **Origin path** là rewrite bỏ prefix **/api**; nếu backend chỉ nhận **/products**, cần một cơ chế rewrite thích hợp hoặc cấu hình backend tương ứng.

**Bảo vệ origin ALB:** giới hạn đường truy cập trực tiếp đến origin khi có thể, áp dụng TLS, WAF và chính sách network. CloudFront không mặc định ẩn hay đóng các endpoint origin có thể truy cập từ Internet. Với mô hình private origin/VPC origin khi được hỗ trợ, phải kiểm tra yêu cầu và giới hạn kiến trúc cụ thể.

### 4.5. Origin group và failover

Nếu cần dự phòng origin, bạn có thể tạo **origin group** gồm **primary** và **secondary**, rồi gắn group này cho một cache behavior. Khi **cache miss** và primary trả lỗi thuộc danh sách đã cấu hình hoặc gặp lỗi kết nối/timeout tương ứng, CloudFront có thể gửi request sang secondary.

Các HTTP status codes có thể được chọn cho failover theo tài liệu CloudFront bao gồm **400, 403, 404, 416, 429, 500, 502, 503, 504**. **Không nên bật 403/404 làm điều kiện failover một cách mù quáng**: 403 có thể là quyền bị từ chối hợp lệ, còn 404 có thể là object thực sự không tồn tại.

**Ràng buộc quan trọng:** origin failover thông thường chỉ áp dụng cho **GET, HEAD và OPTIONS**, **không áp dụng POST, PUT, PATCH, DELETE**. CloudFront không tự đồng bộ dữ liệu giữa hai origins hoặc đảm bảo consistency. Một hệ thống upload/API ghi dữ liệu cần cơ chế phục hồi backend riêng.

## 5. Cache behavior: chọn đường đi và cách xử lý request

Mỗi standard distribution có **default cache behavior** bắt buộc. Có thể thêm **ordered cache behaviors** với những **path pattern** khác nhau. Một behavior điển hình quy định:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| **Path pattern** | Những đường dẫn URL sẽ khớp behavior | **/assets/\***, **/api/private/\*** |
| **Target origin / origin group** | Nơi nhận origin request khi không dùng cache | S3 assets hoặc ALB API |
| **Viewer protocol policy** | Yêu cầu HTTP/HTTPS | Redirect HTTP to HTTPS |
| **Allowed HTTP methods** | Các method CloudFront chấp nhận và có thể forward | GET/HEAD/OPTIONS hoặc toàn bộ |
| **Cached HTTP methods** | Method có thể được cache | GET/HEAD, có thể gồm OPTIONS |
| **Cache policy** | TTL và cache key | Managed CachingOptimized hoặc custom |
| **Origin request policy** | Giá trị cần gửi origin nhưng không thêm vào cache key | Một số headers, cookies, query strings |
| **Response headers policy** | Header bổ sung/điều chỉnh trên response | CORS, HSTS, security headers |
| **Edge functions** | Tùy biến request/response nếu cần | URL rewrite, kiểm tra yêu cầu đơn giản |

### 5.1. Thứ tự path pattern cực kỳ quan trọng

CloudFront xét **ordered cache behaviors theo thứ tự cấu hình**, và dùng **behavior đầu tiên khớp path**. Nếu không có behavior nào khớp, CloudFront dùng default behavior **\***.

Ví dụ thứ tự hợp lý cho một ứng dụng:

| Thứ tự | Path pattern | Origin | Chính sách gợi ý |
|---|---|---|---|
| 1 | **/api/private/\*** | ALB | Không cache dữ liệu người dùng, forward thông tin xác thực cần thiết |
| 2 | **/api/public/\*** | ALB | Chỉ cache endpoint GET nếu response không cá nhân hóa |
| 3 | **/assets/\*** | S3 | Cache dài, file có version/hash |
| 4 | **/api/\*** | ALB | Cache disabled mặc định cho phần API còn lại |
| Default | **\*** | S3 hoặc web origin | HTML, đường dẫn khác; TTL theo chính sách nội dung |

Ví dụ request **/api/private/profile** sẽ khớp behavior thứ nhất. Nếu đặt **/api/\*** trước **/api/private/\***, request sẽ khớp behavior tổng quát trước và có thể nhận policy sai. CloudFront **không tự ưu tiên path cụ thể hơn** nếu bạn đặt thứ tự ngược.

Path pattern chủ yếu dựa trên **đường dẫn URI**, không dựa trên query string để quyết định behavior. Nếu cần biến thể theo tham số **?language=vi**, hãy cấu hình **cache key/query string policy** phù hợp bên trong behavior.

**Rủi ro bảo mật:** nếu behavior tổng quát cho phép public caching hoặc thiếu yêu cầu viewer authentication, một behavior nhạy cảm bị đặt sau nó có thể bị áp dụng sai. Phải kiểm thử cả path bị chồng lấn.

### 5.2. Allowed methods và cached methods khác nhau

CloudFront có các lựa chọn allowed methods thường gặp:

- **GET, HEAD**.
- **GET, HEAD, OPTIONS**.
- **GET, HEAD, OPTIONS, PUT, PATCH, POST, DELETE**.

Chỉ **GET, HEAD** và nếu bật thêm thì **OPTIONS** mới là các method được cache theo cấu hình. Việc cho phép **POST/PUT/PATCH/DELETE** không có nghĩa CloudFront sẽ cache các kết quả ghi dữ liệu. Với API có phương thức ghi, cần cho phép đúng method, forward body/headers cần thiết và cấu hình kiểm soát quyền ở origin.

**OPTIONS** thường dùng cho CORS preflight. Nếu chọn cache OPTIONS, hãy đảm bảo cache key/response CORS phân biệt các biến thể cần thiết theo **Origin** hoặc những request headers phù hợp; ngược lại có thể trả CORS headers cho sai phía gọi.

## 6. Ba nhóm policy: cache, origin request, response headers

Đây là phần dễ nhầm nhất trong triển khai CloudFront:

| Policy | Điều khiển | Có quyết định cache key? |
|---|---|---|
| **Cache policy** | TTL min/default/max, headers/cookies/query strings đưa vào cache key, compression options | **Có** |
| **Origin request policy** | Headers/cookies/query strings cần gửi tới origin **ngoài** các giá trị đã có trong cache key | **Không** |
| **Response headers policy** | CORS headers, security headers và custom response headers gửi tới viewer | **Không** |

### 6.1. Cache policy quyết định cache key

Cache key xác định khi nào hai request có thể chia sẻ một bản cache:

- **Headers**: ví dụ phân biệt response theo một header cụ thể.
- **Cookies**: chỉ chọn cookie thực sự làm thay đổi nội dung.
- **Query strings**: ví dụ **lang=vi**, **size=small** nếu chúng thay đổi response.
- **Compression support**: CloudFront có thể xử lý/caching biến thể gzip/Brotli theo cấu hình và hỗ trợ.

Nếu thêm **mọi cookie**, **mọi header** hoặc **mọi query string** vào cache key, số lượng biến thể tăng nhanh, làm giảm hit ratio và tăng origin load. Tuy nhiên, **loại bỏ một giá trị có ảnh hưởng tới nội dung khỏi cache key** có thể dẫn đến phản hồi không đúng người hoặc sai ngôn ngữ/định dạng.

**Quy tắc thiết kế:** đưa vào cache key **những thuộc tính làm nội dung phản hồi khác nhau**, và không cache dữ liệu có tính cá nhân nếu chưa chứng minh được tính tách biệt/an toàn của từng biến thể.

### 6.2. Origin request policy quyết định phần thông tin chỉ gửi origin

Cache policy tự động forward những headers/cookies/query strings **đã đưa vào cache key**. Origin request policy bổ sung các trường cần cho backend nhưng **không tạo biến thể cache**.

Ví dụ, backend muốn log header địa lý do CloudFront thêm vào, nhưng trang ảnh giống nhau cho mọi quốc gia. Có thể forward header này tới origin bằng origin request policy mà không đưa nó vào cache key nếu origin thực sự trả cùng một response. Nếu backend thay đổi nội dung theo quốc gia, lại phải tính đến **cache key** hoặc tắt cache cho luồng tương ứng.

**Quan hệ quan trọng:** khi dùng **origin request policy**, behavior phải dùng **cache policy**; hai policy phối hợp, không phải hai bộ lọc độc lập chặn giá trị của nhau.

### 6.3. Response headers policy

Response headers policy có thể thêm/điều chỉnh:

- **CORS**: Access-Control-Allow-Origin, methods/headers và max-age khi được cấu hình.
- **Security headers**: HSTS, X-Content-Type-Options, Content-Security-Policy, Referrer-Policy...
- **Custom headers**: các header do tổ chức quy định.

Các policy này điều khiển header trả về viewer, **không tự sửa dữ liệu object trong origin** và **không thay thế xác thực/ủy quyền**. Một policy CORS cho phép trình duyệt đọc response từ một origin khác theo điều kiện, nhưng không tự trao quyền truy cập API.

### 6.4. Ví dụ tránh nhầm policy

Giả sử **GET /catalog?lang=vi** và **GET /catalog?lang=en** có nội dung khác nhau.

| Cách cấu hình | Hệ quả |
|---|---|
| Không forward **lang** | Origin có thể không biết ngôn ngữ được yêu cầu |
| Chỉ forward **lang** bằng origin request policy | Origin nhận lang trên **cache miss** nhưng bản cache có thể bị dùng chung cho các ngôn ngữ |
| Đưa **lang** vào **cache key** | Các ngôn ngữ có cache entry riêng, và lang tự được forward đến origin |
| Tắt cache | Mỗi yêu cầu đến origin, hữu ích nếu nội dung không cache an toàn |

## 7. TTL và Cache-Control: hiệu năng gắn với độ mới của dữ liệu

### 7.1. Minimum, default và maximum TTL

Cache policy có ba tham số:

| Tham số | Ý nghĩa |
|---|---|
| **Minimum TTL** | Khoảng thời gian tối thiểu CloudFront giữ bản cache trước khi đánh giá lại |
| **Default TTL** | TTL dùng khi origin **không cung cấp** Cache-Control/Expires liên quan |
| **Maximum TTL** | Giới hạn tối đa thời gian lưu cache khi origin khai báo thời hạn lớn |

Origin có thể gửi:

~~~http
Cache-Control: public, max-age=300
~~~

Trong tình huống phù hợp, CloudFront dùng chỉ thị response và giới hạn min/max TTL của cache policy để xác định thời hạn. Nếu origin không có Cache-Control/Expires, **Default TTL** sẽ được dùng. Phải cân nhắc cả **browser cache** và **CloudFront edge cache**; thay đổi edge không nhất thiết xóa bản cache đã lưu tại trình duyệt.

### 7.2. Cảnh báo bảo mật: Minimum TTL lớn hơn 0

**Nếu Minimum TTL > 0, CloudFront có thể cache response trong ít nhất khoảng thời gian đó ngay cả khi origin gửi Cache-Control: no-cache, no-store hoặc private.** Vì vậy, với dữ liệu cá nhân, kết quả xác thực hoặc nội dung không được dùng chung:

1. Ưu tiên **managed cache policy CachingDisabled** hoặc chính sách custom cho phép **TTL min/default/max đều bằng 0** nếu muốn tắt caching ở behavior.
2. Kiểm tra đầy đủ **Authorization, Cookie, session** và biến thể response; chỉ forward đúng giá trị cần thiết.
3. Không chỉ dựa vào header **Cache-Control: private** khi cache policy vẫn có **Minimum TTL > 0**.
4. Kiểm thử hai người dùng độc lập với nội dung khác nhau, kể cả trường hợp cache hit và cache miss.

### 7.3. Chiến lược TTL theo loại tài nguyên

| Tài nguyên | Chiến lược gợi ý | Vì sao |
|---|---|---|
| **/assets/app.ab12cd.js** | TTL dài, tên file có hash/version | Nội dung gần như bất biến; khi phát hành file mới dùng URL khác |
| **/index.html** | TTL ngắn hoặc revalidate thường xuyên | Đảm bảo trình duyệt nhanh biết URL asset mới |
| **/api/public/catalog** | TTL ngắn nếu dữ liệu có thể chia sẻ | Giảm tải API, chấp nhận độ trễ cập nhật có kiểm soát |
| **/api/private/profile** | CachingDisabled | Tránh rủi ro chia sẻ response riêng tư |
| **/api/orders POST** | Forward request, không cache phản hồi ghi dữ liệu theo cache semantics thông thường | Cần kiểm tra auth, idempotency và backend |

**TTL dài không đồng nghĩa “không thể cập nhật”**: có thể đổi tên asset theo phiên bản hoặc invalidation; nhưng nếu URL không đổi, bản cache cũ có thể tiếp tục được phục vụ cho đến khi hết hạn/invalidation.

### 7.4. Cache error responses

CloudFront có thể cache một số phản hồi lỗi như **403/404/5xx** theo cơ chế **error caching** và cấu hình **Error Caching Minimum TTL**. Hậu quả là sau khi sửa bucket policy hay upload object, người dùng vẫn có thể thấy lỗi cũ trong một khoảng thời gian.

Khi gặp hiện tượng này, kiểm tra origin đã trả dữ liệu đúng chưa, chính sách TTL và error caching, sau đó chờ hết hạn hoặc thực hiện invalidation phù hợp. Không kết luận ngay lỗi do DNS khi CloudFront vẫn đang trả bản cache của thông báo lỗi.

## 8. Thiết kế mẫu: S3 assets và API qua ALB

Giả sử một ứng dụng thương mại điện tử có frontend tĩnh và backend Java Spring Boot:

~~~mermaid
flowchart TB
    V["Viewer<br/>shop.example.com"] --> CF["CloudFront distribution<br/>HTTPS / WAF"]
    CF -->|"assets/* → cache dài"| S3["S3 private bucket<br/>OAC"]
    CF -->|"api/public/* → GET cache ngắn"| ALB["ALB"]
    CF -->|"api/private/* → cache disabled"| ALB
    ALB --> ASG["EC2 Auto Scaling Group<br/>Spring Boot"]
    ASG --> DB["RDS / DynamoDB"]
~~~

### 8.1. Bản thiết kế behavior

| Path pattern | Origin | Cache policy | Origin request policy | Allowed methods |
|---|---|---|---|---|
| **/api/private/\*** | ALB | **CachingDisabled** | Forward headers/cookies/query cần cho auth/backend | All methods cần cho API |
| **/api/public/\*** | ALB | Cache ngắn, key theo những query thay đổi nội dung | Chỉ forward metadata phục vụ origin | GET/HEAD (OPTIONS nếu dùng CORS) |
| **/assets/\*** | S3 | **CachingOptimized** hoặc policy tương đương | Thường không cần forward cookie/auth | GET/HEAD |
| **Default \*** | S3 hoặc web origin | TTL theo HTML/SPA và route | Tùy ứng dụng | GET/HEAD |

**Cấu hình ví dụ chỉ minh họa tư duy.** Chính sách CachingOptimized có Minimum TTL lớn hơn 0; không gắn policy đó cho dữ liệu riêng tư chỉ vì thấy “tối ưu hiệu năng”. Với API public nhưng cần **Authorization** hoặc biến thể theo từng người, phải đánh giá lại giả định “public” trước khi cache.

### 8.2. HTML SPA và fallback

Một ứng dụng SPA có route **/products/123** có thể cần trả **index.html** để client-side router xử lý. Nếu origin là S3 private, request tới object không tồn tại đôi khi trả **403** thay vì 404, tùy quyền và kiểu request.

**Không nên áp dụng custom error response 403 → index.html một cách vô điều kiện trên toàn distribution** có API và S3: lỗi “không được phép” của API có thể bị che bằng HTTP 200/HTML, gây sai semantics và cản giám sát bảo mật. Ưu tiên rewrite theo đường dẫn viewer phù hợp, tách behaviors/origins hoặc một chiến lược fallback được kiểm soát và kiểm thử kỹ.

## 9. Tối ưu cache, invalidation và triển khai nội dung

### 9.1. Dùng tên file có version/hash

Với static assets:

~~~text
/assets/app.3f2a1c.js
/assets/styles.a17bb4.css
/images/logo.v5.png
~~~

Các file có tên bất biến có thể đặt TTL dài. Khi phát hành mới, tạo URL mới và cập nhật HTML tham chiếu. Cách này thường an toàn hơn việc ghi đè cùng tên và cố invalidation tất cả nơi đã cache, nhất là vì browser/proxy phía người dùng có cache riêng.

Đối với **index.html**, đặt TTL ngắn hoặc cơ chế revalidate phù hợp. Trình duyệt lấy HTML mới sẽ phát hiện tên assets mới.

### 9.2. Invalidation dùng khi nào?

**Invalidation** yêu cầu CloudFront loại bỏ những đường dẫn cache đã chọn để lần truy cập kế tiếp phải lấy nội dung phù hợp từ origin. Chỉ dùng khi cần:

- Sửa gấp nội dung cùng URL trong khi TTL còn dài.
- Xóa bản nội dung lỗi hoặc nhạy cảm bị cache ngoài dự kiến, đồng thời sửa gốc rễ bảo mật.
- Cập nhật tài nguyên không dùng versioned filename.

Invalidation có giới hạn quota và mô hình phí theo số đường dẫn; nên quản trị theo pipeline phát hành thay vì invalidation toàn bộ distribution sau mọi commit.

### 9.3. CloudFront Functions, Lambda@Edge và Origin Shield

Các tính năng hỗ trợ bổ sung:

- **CloudFront Functions**: logic nhẹ tại edge, chẳng hạn normalize/rewrite URL hoặc xử lý đơn giản ở các giai đoạn viewer được hỗ trợ.
- **Lambda@Edge**: cho phép xử lý phức tạp hơn ở những sự kiện CloudFront được hỗ trợ, gồm một số thao tác với origin request/response.
- **Origin Shield**: lớp cache bổ sung được chọn theo Region để giảm nhiều request lặp tới origin trong kiến trúc phù hợp.

Chúng có **giới hạn, chi phí và hành vi triển khai riêng**, không tự thay thế cache behavior hoặc thiết kế ứng dụng. Một đoạn function rewrite sai có thể làm cache key và định tuyến không còn khớp với dự kiến; cần kiểm thử riêng.

## 10. Bảo mật CloudFront distribution

### 10.1. Chia đường bảo mật thành hai phần

| Chặng | Câu hỏi | Biện pháp |
|---|---|---|
| **Viewer → CloudFront** | Ai được truy cập nội dung? Request có bị tấn công không? | HTTPS, WAF, signed URL/cookie, rate-based rules, auth |
| **CloudFront → origin** | Chỉ CloudFront hay hệ thống được phép mới tiếp cận dữ liệu gốc? | S3 OAC + bucket policy, origin TLS, ALB/network protection |

**AWS WAF** có thể gắn với CloudFront để áp dụng các quy tắc bảo vệ web. **AWS Shield Standard** cung cấp khả năng bảo vệ DDoS theo phạm vi dịch vụ. Các cơ chế này hỗ trợ bảo vệ nhưng không bảo đảm loại bỏ mọi cuộc tấn công, và không sửa được lỗi phân quyền trong ứng dụng hoặc bucket policy.

### 10.2. Signed URLs và signed cookies

Với file giới hạn người xem như video trả phí, báo cáo hoặc nội dung thuê bao, CloudFront hỗ trợ **signed URLs** và **signed cookies** qua thiết lập trusted key groups/khóa ký tương ứng:

- **Signed URL**: phù hợp cấp quyền cho một URL hoặc tài nguyên cụ thể.
- **Signed cookie**: phù hợp cấp quyền cho một nhóm tài nguyên mà client truy cập nhiều URL.

Hạn sử dụng của chữ ký, policy URL/path, quản lý private key và bảo vệ cookies là trách nhiệm của hệ thống cấp quyền. Signed URL/cookie **không thay thế xác thực nghiệp vụ**, và cũng không làm cho S3 origin private nếu bucket policy vẫn cho public access trực tiếp.

### 10.3. Không cache dữ liệu riêng tư bằng cache key chung

Ví dụ nguy hiểm:

1. Người A gửi GET **/api/me** kèm cookie hoặc Authorization.
2. Origin trả dữ liệu cá nhân A.
3. CloudFront cache response với key chỉ có path **/api/me**.
4. Người B gửi GET cùng path và có thể nhận phản hồi của A từ cache.

Vì vậy, với endpoint cá nhân hóa nên dùng **CachingDisabled** và forward thông tin xác thực cần thiết, trừ khi đội kỹ thuật có thiết kế cache phân tách người dùng được chứng minh đúng và có kiểm thử bảo mật. Đưa tất cả cookies vào cache key để “an toàn” không tự giải quyết các vấn đề auth, chi phí và cache cardinality.

### 10.4. Geo restriction không phải data residency

CloudFront có thể hỗ trợ giới hạn quyền viewer theo quốc gia trong những tình huống phù hợp. Nhưng **đặt geo restriction không có nghĩa nội dung được lưu, xử lý hoặc cache chỉ trong quốc gia/Region đó**. Với yêu cầu lưu trú dữ liệu và dữ liệu cá nhân, cần kiểm tra cách hệ thống xử lý thông tin, logs, origin Region, CDN behavior và chính sách pháp lý của tổ chức.

## 11. Kiểm tra distribution bằng AWS CLI và HTTP

Những lệnh dưới đây chỉ kiểm kê tài nguyên hoặc thực hiện invalidation được nêu rõ. Các ID/domain là ví dụ, cần thay bằng tài nguyên do bạn quản lý. API CloudFront quản trị distribution thuộc phạm vi toàn cầu; không nhầm với Region của origin S3/ALB hoặc ACM viewer certificate.

### 11.1. Liệt kê và đọc cấu hình distribution

~~~bash
# Xem những distribution mà tài khoản có quyền liệt kê.
aws cloudfront list-distributions \
  --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status,Enabled:Enabled}' \
  --output table

# Đọc cấu hình đã được lưu của một distribution cụ thể.
aws cloudfront get-distribution-config \
  --id E123EXAMPLEID \
  --query 'DistributionConfig.{Origins:Origins.Items,Default:DefaultCacheBehavior,Ordered:CacheBehaviors.Items}' \
  --output json
~~~

Quan sát **origins**, **TargetOriginId**, **PathPattern**, các **CachePolicyId**, **OriginRequestPolicyId**, **ViewerProtocolPolicy** và **AllowedMethods** thực tế. Nếu behavior không dùng cache policy theo mô hình hiện đại, có thể có cấu hình cache legacy; nên đánh giá trước khi chuyển đổi.

### 11.2. Tạo invalidation có kiểm soát

~~~bash
# Thay ID distribution thật. Lệnh này thay đổi trạng thái cache.
aws cloudfront create-invalidation \
  --distribution-id E123EXAMPLEID \
  --paths "/index.html" "/assets/*"
~~~

Lệnh trả về invalidation ID và trạng thái. Khi cần kiểm tra một invalidation cụ thể:

~~~bash
aws cloudfront get-invalidation \
  --distribution-id E123EXAMPLEID \
  --id I123EXAMPLEID
~~~

Chỉ invalidation những path cần thiết; nên dùng versioned filenames cho assets thường xuyên phát hành. Tùy nhu cầu và chi phí, có thể đợi TTL hết thay vì chủ động invalidation.

### 11.3. Kiểm tra HTTP response

~~~bash
# Gọi từ môi trường được phép kiểm thử; thay domain bằng tên thật.
curl -I "https://www.example.com/assets/app.3f2a1c.js"

# Kiểm tra endpoint public và response headers.
curl -i "https://www.example.com/api/public/catalog?lang=vi"
~~~

Các header hữu ích có thể gồm **Cache-Control**, **Age**, **X-Cache**, **Via**, **Content-Encoding**, **Access-Control-Allow-Origin**, **Strict-Transport-Security** và mã trạng thái. **X-Cache: Hit from cloudfront** có thể cho biết một yêu cầu được phục vụ từ cache; nhưng kết quả phụ thuộc edge, cache key, vị trí và thời điểm. Gọi hai lần liên tiếp không luôn bảo đảm lần hai là hit, đặc biệt khi TTL = 0 hoặc policy tạo biến thể khác nhau.

Đừng thử với dữ liệu cá nhân thật hoặc lưu toàn bộ Authorization/cookies trong log debug công khai.

## 12. Giám sát và điều tra hiệu năng

### 12.1. Metric nên theo dõi

CloudFront công bố các metric/đặc trưng giám sát; nhóm metric có thể gồm:

| Chỉ số | Ý nghĩa | Khi nào cần điều tra |
|---|---|---|
| **Requests** | Số lượng viewer requests | Tăng tải bất thường, cần scale origin |
| **BytesDownloaded / BytesUploaded** | Lưu lượng giữa CloudFront và viewer | Tăng chi phí traffic hoặc payload lớn |
| **4xxErrorRate** | Tỷ lệ lỗi client-side trả tới viewer | Quyền S3, bad request, missing object, WAF/auth |
| **5xxErrorRate** | Tỷ lệ lỗi máy chủ/edge trả tới viewer | Origin lỗi, TLS/timeout, backend quá tải |
| **TotalErrorRate** | Tổng tỷ lệ lỗi theo metric | Quan sát sức khỏe tổng |
| **CacheHitRate** | Tỷ lệ request có thể phục vụ từ cache theo cách tính của metric | Cache key quá nhiều biến thể, TTL không phù hợp |
| **OriginLatency** | Độ trễ khi CloudFront lấy phản hồi từ origin | ALB/backend/database chậm hoặc lỗi mạng |

Một số metric chi tiết như **CacheHitRate/OriginLatency** cần bật tính năng **additional CloudWatch metrics** và có thể tính phí bổ sung; cần kiểm tra cấu hình hiện hành. Metric tổng theo distribution có thể che khuất một path hoặc loại request lỗi; kết hợp access logs và monitoring tại origin.

### 12.2. Standard logs và real-time logs

- **Standard access logs** giúp phân tích request paths, status, user agent, cache result và luồng truy cập theo khả năng ghi log được hỗ trợ.
- **Real-time logs** có thể cung cấp log với độ trễ thấp hơn theo cấu hình sampling/trường dữ liệu, nhưng cần thiết kế pipeline và chi phí riêng.
- **ALB logs, application logs, S3 access logs/CloudTrail, WAF logs** có thể bổ sung bằng chứng phía origin hoặc lớp bảo vệ.

Khi bật logging, kiểm tra **PII, IP address, cookies, query strings và thông tin xác thực** để tránh vô tình lưu dữ liệu nhạy cảm. Phân quyền nơi lưu log, đặt retention và chỉ tập hợp những trường cần thiết.

### 12.3. Quy trình điều tra một URL chậm

1. Xác định đúng **URL, method, query, Host, thời gian và khu vực người dùng**.
2. Xem behavior khớp đầu tiên, origin đích, cache policy và TTL.
3. Kiểm tra **X-Cache, Age, latency**, số request và log để phân biệt hit/miss.
4. Với miss, đo **origin latency**, ALB target health, app performance, database I/O và network.
5. Kiểm tra cache key có chứa cookie/header/query không cần thiết không.
6. Sửa policy/ứng dụng theo nguyên nhân, kiểm thử nhiều edge/users và quan sát chi phí/hiệu năng sau thay đổi.

## 13. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra trước |
|---|---|---|
| **403** với S3 private | Thiếu OAC, sai bucket policy/SourceArn, KMS hoặc object không tồn tại mà không có quyền ListBucket | S3 origin type, OAC signing, policy, KMS, key chính xác |
| **403** trên một đường API | WAF, xác thực backend, behavior sai thứ tự hoặc origin trả Deny | WAF logs, access logs, path pattern, API auth |
| **404** dù asset mới đã upload | Sai path, origin path, object key hoặc lỗi được cache | S3 key, behavior, TTL/error caching, invalidation |
| **502 Bad Gateway** | Origin TLS certificate mismatch, SSL handshake, DNS hoặc origin protocol lỗi | Origin domain, certificate, listener, port, DNS |
| **503/504** | Origin quá tải, connection/response timeout, backend không khỏe | ALB/EC2 metrics, origin timeout, autoscaling, app logs |
| **Sai origin cho /api/private/\*** | Behavior tổng quát **/api/\*** đứng trước | Đổi đúng thứ tự ordered cache behaviors |
| **X-Cache luôn Miss** | Caching disabled, TTL thấp, cache key quá nhiều biến thể, edge khác nhau | Cache policy, query/cookie/header, response Cache-Control |
| **Người B thấy dữ liệu người A** | Cache response cá nhân hóa bằng cache key chung | Tắt cache ngay cho behavior nhạy cảm, rà soát auth và logs |
| **CORS chỉ lỗi với một số người dùng** | OPTIONS/cached response không phân biệt Origin hoặc response headers policy sai | Origin/cors header, OPTIONS caching, cache key, policy |
| **Nội dung cũ vẫn xuất hiện** | Edge TTL, browser cache, stale response hoặc invalidation chưa hoàn tất | Cache-Control, Age, versioned asset, invalidation status |
| **ALB trực tiếp hoạt động nhưng qua CloudFront lỗi** | Origin path, Host header, TLS, allowed methods, origin policy | So sánh request thực tới origin và cấu hình CloudFront |
| **Origin group không failover POST** | Failover chỉ áp dụng GET/HEAD/OPTIONS | Thiết kế backend failover cho API ghi và retry/idempotency |
| **Chi phí tăng sau thêm CDN** | Thêm quá nhiều request variants, log, invalidations, origin shield hoặc WAF charges | Billing, CacheHitRate, request counts, pricing |

## 14. Quy trình triển khai CloudFront an toàn

### Bước 1 — Phân loại nội dung

Chia đường dẫn thành **static immutable assets**, **HTML cần cập nhật**, **API public có thể cache**, **API cá nhân hóa**, **phương thức ghi dữ liệu**, **media/large files**. Ghi rõ yêu cầu auth, TTL chấp nhận, cache key và độ nhạy cảm của từng nhóm.

### Bước 2 — Chọn origins và bảo vệ nguồn gốc

Với static assets, chọn S3 bucket private và **OAC**; với API, chọn ALB/API endpoint có TLS và khả năng mở rộng tương ứng. Nếu origin ở nhiều Region, xác định luồng DR và tính nhất quán dữ liệu; origin group chỉ giải quyết failover trong phạm vi method/status được hỗ trợ.

### Bước 3 — Tạo distribution và domain

Tạo distribution, định nghĩa origins, chứng chỉ/alternate domain, viewer HTTPS và WAF phù hợp. Cấu hình Route 53 Alias hoặc DNS tại nhà cung cấp đang sử dụng. Đợi phân phối cấu hình hoàn tất, sau đó kiểm tra domain/TLS.

### Bước 4 — Thiết kế behaviors và policies

Đưa path nhạy cảm và cụ thể lên trước, path tổng quát phía sau; gắn đúng origin, allowed/cached methods và cache/origin request/response headers policies. Với response private, tắt cache hoặc chứng minh được phân tách người dùng. Kiểm tra **Minimum TTL** trước khi đưa cấu hình lên production.

### Bước 5 — Kiểm thử request an toàn

Thử cache hit/miss, CORS OPTIONS, GET với query, URL khác path, file 404, API 401/403, origin 502/503/504, viewer HTTP redirect, HTTPS tới origin. Thử hai người dùng độc lập để phát hiện rủi ro cache chia sẻ dữ liệu.

### Bước 6 — Tích hợp CI/CD và quan sát vận hành

Dùng tên assets có hash/version, cập nhật HTML sau assets, invalidation có chọn lọc, review cấu hình như code (CloudFormation/Terraform/CDK khi phù hợp). Bật metrics/logging cần thiết, rà soát chi phí và có rollback cho policy/behavior thay đổi sai.

## 15. Thực hành tình huống

### Tình huống A — Website tĩnh S3 có yêu cầu bảo mật

Một nhóm đang lưu các file HTML, CSS, JS trong S3 và muốn phục vụ toàn cầu qua CloudFront. Họ không muốn mở bucket public.

**Câu hỏi:** cần tạo origin nào, cấu hình quyền thế nào?

**Gợi ý:** dùng **S3 bucket origin** với **OAC**, bật ký request, bucket policy chỉ cho phép CloudFront service principal với **AWS:SourceArn** của distribution, giữ Block Public Access và kiểm tra SSE-KMS nếu có. Không chọn S3 website endpoint nếu cần OAC.

### Tình huống B — /api/me bị cache nhầm

API trả profile theo cookie phiên. Đội triển khai dùng cache policy tối ưu cho static assets và gắn nó cho toàn bộ **/api/\***.

**Câu hỏi:** nguy cơ gì, cần sửa nơi nào?

**Gợi ý:** response của người dùng A có thể được dùng cho B nếu cache key không phân biệt phiên. Tạo behavior **/api/private/\*** trước **/api/\***, dùng **CachingDisabled**, forward auth/cookies theo nhu cầu, kiểm tra **Minimum TTL = 0** và test với hai tài khoản. Không chỉ thêm Cookie vào origin request policy rồi giữ cache key chung.

### Tình huống C — Cùng một API nhưng hai ngôn ngữ

**GET /api/public/catalog?lang=vi** và **?lang=en** trả dữ liệu khác nhau. Origin request policy forward toàn bộ query string nhưng cache policy không đưa **lang** vào key.

**Câu hỏi:** vì sao người dùng có thể nhận ngôn ngữ sai?

**Gợi ý:** hai request chia sẻ cùng cache key. Thêm **lang** vào cache policy để tách cache entries, đồng thời kiểm tra các query khác có làm response thay đổi hay không.

### Tình huống D — Thứ tự behaviors bị đảo

Distribution có behavior **/api/\*** trước **/api/private/\***; behavior chung forward tới origin nhưng dùng TTL dương. API cá nhân có security requirements nghiêm ngặt.

**Câu hỏi:** behavior nào được áp dụng, và sửa thế nào?

**Gợi ý:** CloudFront lấy **behavior đầu tiên khớp**, tức **/api/\***. Chuyển **/api/private/\*** lên trước, dùng chính sách cache và xác thực thích hợp, kiểm thử URL với cả query string.

### Tình huống E — Deploy mới nhưng người dùng vẫn thấy JS cũ

CI/CD ghi đè **/assets/app.js**, nhưng CloudFront cache file đó với TTL dài. Nhóm thực hiện invalidation vẫn có người dùng nhìn thấy phiên bản cũ trong browser.

**Câu hỏi:** triển khai dài hạn nên thay đổi gì?

**Gợi ý:** đặt tên file theo hash/version (ví dụ **app.f2c9a1.js**), giữ TTL dài cho assets bất biến, chỉ cache ngắn/revalidate HTML; invalidation chỉ khi thực sự cần. Invalidation edge không buộc mọi browser/proxy phải xóa bản đã cache tại client.

### Tình huống F — Origin primary lỗi khi người dùng gửi POST

Ứng dụng ghi đơn hàng bằng POST và tạo CloudFront origin group gồm ALB primary/secondary, cấu hình failover cho 503.

**Câu hỏi:** CloudFront có tự gửi POST tới secondary không?

**Gợi ý:** không, CloudFront origin failover thường chỉ hỗ trợ **GET, HEAD, OPTIONS**. Với lệnh ghi phải thiết kế chuyển traffic/API backend, dữ liệu đồng bộ, retry idempotent và khả năng khôi phục ứng dụng riêng. Không áp dụng retry POST mù quáng vì có thể tạo đơn trùng.

## 16. Checklist trước khi đưa CloudFront vào production

- [ ] Đã phân loại file tĩnh, HTML, API public, API riêng tư và các method ghi dữ liệu.
- [ ] Đã tạo distribution với origins hợp lệ, chứng chỉ/TLS và DNS/Route 53 phù hợp.
- [ ] Đã dùng **S3 OAC** nếu cần origin private; bucket policy và KMS policy đúng.
- [ ] Đã cấu hình **ordered cache behaviors đúng thứ tự**, default behavior hợp lý.
- [ ] Đã kiểm tra allowed methods, cached methods và CORS OPTIONS.
- [ ] Đã hiểu cache key gồm headers/cookies/query strings nào và origin forward những gì.
- [ ] Đã phân biệt cache policy, origin request policy và response headers policy.
- [ ] Đã kiểm tra min/default/max TTL, **Minimum TTL > 0** và dữ liệu nhạy cảm.
- [ ] Đã kiểm tra HTTPS viewer/origin, certificate, WAF, OAC và signed access nếu cần.
- [ ] Đã có chiến lược versioned assets, invalidation và rollback cho deploy.
- [ ] Đã kiểm thử origin failover đúng HTTP methods và xây DR cho API ghi.
- [ ] Đã bật giám sát lỗi 4xx/5xx, latency, cache hit và logging theo nhu cầu.
- [ ] Đã xác minh geo restriction không bị hiểu nhầm là ràng buộc lưu trú dữ liệu.
- [ ] Đã dự toán request/data transfer, WAF, invalidation, origin shield và logging.

## 17. Ghi nhớ

**CloudFront distribution** tổ chức tên miền, origins, behaviors và chính sách; **origin** cung cấp nội dung gốc; **cache behavior** chọn đường đi và quyết định cách request được xử lý. **Cache policy** xác định TTL và cache key; **origin request policy** gửi thêm dữ liệu đến backend mà không đổi cache key; **response headers policy** bổ sung headers cho viewer. Với **S3 private**, dùng **OAC** và bucket policy giới hạn distribution. Với dữ liệu cá nhân, **không dùng cache key chung** hoặc Minimum TTL dương khi chưa chứng minh được an toàn. Tối ưu hiệu năng phải đi cùng **bảo mật, khả năng phục hồi, giám sát và chi phí**.

### Tài liệu AWS chính thức để đối chiếu khi triển khai

- [CloudFront Developer Guide](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) — tổng quan dịch vụ.
- [CloudFront cache behavior settings](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesCacheBehavior.html) — path pattern, methods, viewer protocol, policy.
- [CloudFront CacheBehavior API](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_CacheBehavior.html) — thứ tự behavior và TargetOriginId.
- [Understand cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cache-key-understand-cache-policy.html) — TTL và cache key.
- [Understand origin request policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/origin-request-understand-origin-request-policy.html) — header, cookie, query string gửi đến origin.
- [Understand cache and origin request policy combination](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-how-origin-request-policies-and-cache-policies-work-together.html) — tương tác giữa hai policy.
- [Response headers policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-response-headers-policies.html) — CORS/security headers.
- [Control how long content is cached](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html) — Cache-Control và TTL.
- [Restrict access to an S3 origin with OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) — OAC, bucket policy, hạn chế website endpoint.
- [Origin failover](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/high_availability_origin_failover.html) — primary/secondary và HTTP methods.
- [Alternate domain names and certificates](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/CNAMEs.html) — DNS, certificate và domain ownership.
- [Route 53 alias to CloudFront](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-to-cloudfront-distribution.html) — DNS định tuyến tới distribution.
- [Invalidate content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html) — phiên bản nội dung và invalidation.
- [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/) — phí request, truyền dữ liệu và tính năng bổ sung theo mô hình giá áp dụng.
