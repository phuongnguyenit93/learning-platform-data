# Chẩn đoán lỗi 4xx, 5xx qua CloudFront, ALB và API Gateway

Khi một API hoặc website trả về HTTP 4xx/5xx, mã trạng thái chỉ cho biết request đã thất bại theo một cách nào đó. Nó chưa chỉ ra tầng nào tạo ra lỗi. Cùng một mã 502 có thể do CloudFront không bắt tay TLS được với origin, Application Load Balancer (ALB) nhận TCP reset từ target, API Gateway không hiểu phản hồi Lambda proxy hoặc chính ứng dụng trả về 502. Một mã 403 có thể đến từ AWS WAF, CloudFront signed URL, quyền truy cập S3, authorizer của API Gateway, listener rule hoặc ứng dụng.

Muốn chẩn đoán chính xác, cần truy vết request theo đúng topology, xác định tầng đầu tiên tạo lỗi và đối chiếu status code với access log, metric, request ID, target health và application log. Không nên tăng timeout, mở security group hoặc vô hiệu hóa WAF chỉ vì thấy 502/504.

Bài học này trình bày cách đọc lỗi qua ba thành phần thường gặp: Amazon CloudFront, Application Load Balancer và Amazon API Gateway. Các thành phần có thể được kết hợp theo nhiều topology khác nhau; không phải mọi request đều đi qua cả ba. Nội dung tập trung vào quy trình chẩn đoán, ví dụ log, nguyên nhân phổ biến, cách xử lý và kiểm thử sau khắc phục.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt lỗi 4xx do client, xác thực, phân quyền, WAF, routing và ứng dụng tạo ra.
- Phân biệt lỗi 5xx do edge, load balancer, integration, target và application tạo ra.
- Nhận diện các topology CloudFront → ALB, CloudFront → API Gateway và API Gateway → VPC Link → ALB/NLB.
- Dùng request ID/correlation ID để nối log giữa CloudFront, ALB, API Gateway và backend.
- Đọc CloudFront standard logs và nhận diện x-edge-result-type, x-edge-detailed-result-type, x-edge-request-id.
- Phân biệt elb_status_code với target_status_code trong ALB access logs.
- Dùng CloudWatch metrics của ALB để xác định lỗi do load balancer hay target.
- Bật và đọc API Gateway access logs, execution logs và integration latency.
- Chẩn đoán các lỗi 400, 401, 403, 404, 429, 500, 502, 503 và 504.
- Kiểm tra DNS, TLS, listener/rule, target health, security group, NACL và timeout budget.
- Xây dựng runbook, alarm, regression test và quy trình rollback.

## 2. Hiểu topology trước khi điều tra

CloudFront, ALB và API Gateway không phải lúc nào cũng nằm trên một đường request cố định. Hãy xem kiến trúc thực tế và xác định origin/integration của từng thành phần trước khi đọc log.

### 2.1 CloudFront → ALB → application

    Browser / Mobile client
             |
          CloudFront
             |
          HTTPS origin
             |
            ALB
             |
       Target group
        /    |     \
      ECS   EC2    EKS ingress
             |
        Application

CloudFront là edge cache/reverse proxy. ALB định tuyến request đến target theo listener rule và target group. 4xx/5xx có thể được tạo bởi CloudFront, AWS WAF, ALB hoặc application.

### 2.2 CloudFront → API Gateway → integration

    Browser / Mobile client
             |
          CloudFront
             |
        API Gateway
             |
      Lambda / HTTP integration
             |
       Application / service

API Gateway xác thực, authorizes, validate request và gọi integration. CloudFront có thể cache response theo cache behavior; với API động, cần kiểm tra cache policy, origin request policy và method được forward.

### 2.3 API Gateway → VPC Link → ALB/NLB → service

    Client / CloudFront
             |
        API Gateway
             |
          VPC Link
             |
          ALB/NLB
             |
       ECS / EKS / EC2
             |
        Application

Với private integration, API Gateway dùng VPC Link để truy cập resource trong VPC. VPC Link V2 hỗ trợ ALB và NLB cho REST APIs; HTTP APIs cũng hỗ trợ ALB, NLB và AWS Cloud Map. VPC Link V1 là loại legacy cho REST API và chỉ hỗ trợ NLB. Trong topology này, API Gateway và ALB có log riêng; lỗi có thể xuất hiện ở integration trước khi request tới target.

### 2.4 Quy tắc đầu tiên

1. Xác định URL mà client gọi và domain mapping.
2. Xác định CloudFront distribution/cache behavior có xử lý path đó không.
3. Xác định CloudFront origin thực tế: ALB, API Gateway, S3 hay custom origin.
4. Nếu có API Gateway, xác định API type (REST, HTTP, WebSocket), stage, route/resource và integration type.
5. Nếu có ALB, xác định listener, rule, target group và target type.
6. Ghi lại request ID, thời điểm UTC, method, path, status và response headers.

Không giả định mọi lỗi nhìn thấy ở browser đều do service gần browser nhất. Edge có thể trả lại một lỗi đã cache từ origin hoặc dùng custom error page để thay response body.

## 3. HTTP 4xx và 5xx nói lên điều gì?

| Nhóm | Ý nghĩa chung | Ví dụ |
|---|---|---|
| 4xx | Request không được xử lý do request, identity, permission, policy hoặc resource | 400, 401, 403, 404, 405, 409, 413, 429 |
| 5xx | Gateway/server/integration không thể hoàn tất request | 500, 502, 503, 504 |

### 3.1 4xx không luôn là lỗi của người dùng

Một 403 có thể do policy sai, IAM role thiếu quyền, WAF false positive, CloudFront signed cookie hết hạn hoặc API Gateway authorizer cấu hình sai. Một 404 có thể do path mapping, stage, listener rule hoặc deployment thiếu route. Vì vậy, không hướng dẫn người dùng thử lại nếu lỗi thực tế nằm ở cấu hình hệ thống.

### 3.2 5xx không luôn là lỗi của application

ALB có thể tạo 502 khi target reset kết nối, CloudFront có thể tạo 502 khi TLS handshake thất bại, API Gateway có thể tạo 502 khi Lambda proxy trả response sai định dạng. 504 có thể do một tầng hết timeout trước khi tầng phía sau kịp trả lời.

### 3.3 Cùng một status có nhiều nguồn

HTTP status là hợp đồng giữa các tầng. Mỗi gateway có thể:

- Tạo response trực tiếp.
- Chuyển tiếp response từ origin/target.
- Ánh xạ lỗi integration thành một status khác.
- Thay body bằng custom error page.
- Cache response lỗi trong một khoảng thời gian.

Hãy tìm trường log chỉ rõ response do tầng nào tạo ra thay vì suy đoán từ status.

## 4. Quy trình chẩn đoán chung

### 4.1 Thu thập bằng chứng

Trước khi thay đổi cấu hình, thu thập:

- Thời điểm UTC và khoảng thời gian lỗi.
- Request method, host, path, query và content type.
- HTTP status, response body và response headers.
- Request/correlation ID từ client và các gateway.
- CloudFront distribution ID/cache behavior.
- ALB ARN, listener, target group và target IP/port nếu có.
- API ID, stage, route/resource và integration.
- Thay đổi gần nhất: deploy, certificate, DNS, WAF rule, security group, timeout, scaling hoặc policy.

Không đưa access token, cookie, API key, dữ liệu cá nhân hoặc body nhạy cảm vào ticket/log chia sẻ.

### 4.2 Khoanh vùng theo tầng

    Client nhận 4xx/5xx
             |
       Kiểm tra response headers
             |
       Có CloudFront không?
          /       \
        Có         Không
        |            |
   CloudFront log   Gateway/ALB log
        |
   Origin request có xảy ra?
       /       \
     Có         Không
     |            |
 Origin logs   WAF/cache/function/
     |         edge configuration
     |
   ALB hoặc API Gateway?
       /              \
     ALB              API Gateway
      |                   |
 ELB vs target        Gateway vs integration
      |                   |
 Target/app logs      Backend/Lambda logs

Sơ đồ là quy trình tư duy; topology thực tế có thể đảo thứ tự hoặc chỉ chứa một số thành phần.

### 4.3 Tái hiện lỗi có kiểm soát

- Dùng cùng method, path, headers và body với request lỗi.
- So sánh request đi qua CloudFront với request gọi origin trực tiếp trong môi trường được phép.
- So sánh theo Region/AZ, tenant, identity, user-agent và payload size.
- Dùng một request ID mới cho mỗi lần thử; giữ correlation ID chung khi cần nối các lần retry.
- Thử một thay đổi mỗi lần và ghi lại kết quả.

Không bypass WAF, authentication hoặc network controls trên production để “thử cho nhanh”. Dùng test environment hoặc một endpoint đã được phê duyệt.

### 4.4 Xác định tầng đầu tiên tạo lỗi

Một request có thể đi qua nhiều gateway. Ví dụ:

- CloudFront log ghi 403, không có origin request và WAF log có BLOCK: lỗi ở WAF/edge.
- CloudFront log ghi 502, ALB không có access log tương ứng: kiểm tra CloudFront-to-origin DNS/TLS/network.
- ALB log có elb_status_code=502, target_status_code=-: ALB tạo lỗi trước khi nhận response hợp lệ từ target.
- ALB log có elb_status_code=500, target_status_code=500: target trả 500 và ALB chuyển tiếp.
- API Gateway log có INTEGRATION_TIMEOUT: lỗi integration/time budget.
- API Gateway có status 502 nhưng không có backend invocation: kiểm tra mapping, permission và đường integration.

Sự vắng mặt của log không phải bằng chứng tuyệt đối request không đến tầng đó: logging có thể chưa bật, log delivery có thể trễ hoặc best-effort. Kết hợp metric, trace và application evidence.

## 5. Chẩn đoán lỗi tại Amazon CloudFront

CloudFront nhận request từ viewer, áp dụng cache behavior, viewer/origin request policies, function association, WAF và các quy tắc phân phối; sau đó có thể trả cache hit hoặc gọi origin. Vì vậy, cần xác định request có đi tới origin hay bị xử lý ngay tại edge.

### 5.1 Những dấu hiệu cần đọc

| Header/log field | Ý nghĩa | Dùng để |
|---|---|---|
| HTTP response status | Mã trả về cho viewer | Bắt đầu phân loại |
| X-Cache | Thường cho biết Hit/Miss/Error from cloudfront | Nhận biết cache/edge error |
| Via | Cho biết response đi qua CloudFront | Xác nhận edge path |
| X-Amz-Cf-Id | Request identifier của CloudFront | Nối response với access log |
| sc-status | Status gửi cho viewer trong standard log | Tìm request lỗi |
| x-edge-result-type | Kết quả xử lý cuối cùng | Hit, Miss, Error, CapacityExceeded... |
| x-edge-response-result-type | Phân loại ngay trước khi trả response | So sánh với result cuối |
| x-edge-detailed-result-type | Chi tiết hơn khi có Error | Phân biệt origin, viewer, internal error |
| x-edge-request-id | ID request, cũng xuất hiện trong X-Amz-Cf-Id | Correlation |
| time-taken / time-to-first-byte | Thời gian xử lý/byte đầu | Phân biệt chậm ở origin hay viewer |

CloudFront standard logging là tùy chọn và có độ trễ phân phối. Log có thể được ghi theo từng edge location; một khoảng thời gian có thể có nhiều file. Không dùng log làm hệ thống accounting tuyệt đối.

### 5.2 CloudFront 400 Bad Request

Nguyên nhân có thể:

- Request header, URI hoặc method không hợp lệ.
- Host header hoặc path không khớp origin behavior.
- Header/query/cookie bị forward sai hoặc vượt giới hạn.
- Origin từ chối request vì Host, content type hoặc request signature.
- AWS WAF hoặc function sửa request không đúng.

Kiểm tra method, Host, URI encoding, content length, header size, query string, cookie forwarding và WAF logs. So sánh một request hợp lệ với request lỗi ở cùng behavior.

### 5.3 CloudFront 401/403

Các nguyên nhân thường gặp:

- CloudFront signed URL/signed cookie hết hạn, sai policy hoặc signature.
- Geo restriction từ chối viewer.
- AWS WAF block request.
- S3 origin access control/origin access identity hoặc bucket policy sai.
- Origin trả AccessDenied, API Gateway authorizer từ chối hoặc application trả 403.
- Origin request policy không forward header/cookie cần thiết cho authorization.

Phân biệt 403 ở edge với 403 từ origin. Kiểm tra WAF sampled requests/logs, CloudFront function/Lambda@Edge, origin logs và quyền truy cập S3/API. Với S3 origin, kiểm tra OAC, bucket policy, object key và KMS key policy.

### 5.4 CloudFront 404 Not Found

Kiểm tra:

- Path pattern/cache behavior có chọn đúng origin không.
- Origin path có thêm/bớt prefix không.
- API base path mapping, stage hoặc route có đúng không.
- Object key có phân biệt chữ hoa/chữ thường không.
- Application deploy có route/resource chưa.
- Error 404 có đang được cache tại edge không.

Nếu origin đã sửa nhưng viewer vẫn nhận 404 cũ, kiểm tra error caching minimum TTL và cache policy. Invalidation chỉ xử lý bản cache; không sửa route hoặc object bị thiếu ở origin.

### 5.5 CloudFront 502 Bad Gateway

502 thường có nghĩa CloudFront không kết nối được origin hoặc không nhận được response hợp lệ. Các nhóm nguyên nhân:

| Nhóm | Dấu hiệu | Kiểm tra |
|---|---|---|
| DNS | NonS3OriginDnsError, origin domain không resolve | DNS record, authoritative NS/SOA, resolver |
| TLS certificate | Certificate expired/self-signed/invalid, hostname mismatch, chain thiếu | SAN/CN, chain, expiry, SNI |
| TLS protocol/cipher | Handshake không thống nhất | Origin TLS policy/protocol/cipher |
| Port/network | Origin không nghe port, firewall chặn | Origin port, security group/NACL/firewall |
| Invalid response | Header/status/response malformed | Web server/application response |
| Edge function | Lambda@Edge/CloudFront Function validation error | Function logs, response schema, read-only headers |
| Origin service | ALB/API Gateway tự trả 502 | Dùng request ID và log tầng origin |

Với custom HTTPS origin, certificate phải khớp origin domain hoặc Host header mà CloudFront dùng khi kết nối. Kiểm tra SNI và Host forwarding; certificate có thể hợp lệ cho viewer domain nhưng không hợp lệ cho origin domain.

Các lệnh kiểm tra từ môi trường có quyền:

    nslookup origin.example.com
    dig origin.example.com A
    openssl s_client -connect origin.example.com:443 -servername origin.example.com
    curl -sv https://origin.example.com/health

Thử DNS/TLS từ public internet khi điều tra custom public origin vì CloudFront cần resolve và kết nối origin theo cấu hình công khai. Với VPC origin, kiểm tra kết nối private và security configuration phù hợp.

### 5.6 CloudFront 503 Service Unavailable

Phân biệt:

- CloudFront capacity/quota: log result type có thể là CapacityExceeded hoặc LimitExceeded.
- Origin trả 503 vì không đủ capacity hoặc maintenance.
- ALB trả 503 vì không có target sẵn sàng.
- API Gateway/backend trả 503 vì integration unavailable.
- WAF custom response có thể dùng status code tùy chỉnh.

Đối chiếu CloudFront result type với origin log, ALB ELB/target metrics và API Gateway 5XX metrics. Nếu lỗi chỉ xuất hiện ở một path/cache behavior, kiểm tra origin mapping; nếu tăng trên mọi path, xem xét edge/origin capacity và service health.

### 5.7 CloudFront 504 Gateway Timeout

CloudFront có thể hết thời gian chờ khi:

- Không thiết lập được kết nối tới origin.
- Origin không trả byte đầu trong origin response timeout.
- Origin bắt đầu response nhưng dừng gửi dữ liệu quá lâu.
- Origin/API Gateway/ALB có timeout riêng ngắn hơn.
- Backend bị nghẽn, dependency chậm hoặc connection pool cạn.

Kiểm tra Origin Connection Timeout, Connection Attempts và Origin Response Timeout. Với GET/HEAD, CloudFront có thể thử kết nối lại theo cấu hình; với DELETE/OPTIONS/PATCH/PUT/POST, hành vi retry khác và client có thể phải gửi lại. Không tăng timeout trước khi kiểm tra latency và capacity của backend.

### 5.8 Error caching và stale response

CloudFront có thể cache một số lỗi origin. Theo tài liệu hiện hành, các status 404, 414, 500, 501, 502, 503 và 504 thuộc nhóm có thể cache. Một số lỗi 400, 403, 405, 412 và 415 chỉ cache khi origin trả Cache-Control max-age hoặc s-maxage. CachingDisabled managed policy không cache các status/custom error page này.

Nếu origin phục hồi nhưng viewer vẫn thấy lỗi:

1. Kiểm tra response header và X-Cache.
2. Kiểm tra Error Caching Minimum TTL.
3. Kiểm tra custom error page và cache behavior của error page.
4. Kiểm tra origin Cache-Control.
5. Chỉ invalidation khi đã xác định response lỗi nằm trong cache và hiểu phạm vi invalidation.

CloudFront có thể tiếp tục phục vụ object stale khi origin trả 5xx nếu object còn trong edge cache và điều kiện stale-serving phù hợp. Điều này giúp tăng availability nhưng có nghĩa viewer có thể nhận nội dung cũ trong thời gian origin lỗi.

## 6. Chẩn đoán lỗi tại Application Load Balancer

ALB có thể tạo response hoặc chuyển tiếp response từ target. Bằng chứng quan trọng nhất trong access log là cặp status:

- elb_status_code: status do load balancer, fixed-response rule hoặc AWS WAF custom response tạo.
- target_status_code: status target trả về; chỉ có khi ALB kết nối được target và target gửi response.

Nếu target_status_code là dấu gạch ngang, không có response HTTP từ target được ghi nhận. Kiểm tra thêm target:port, actions_executed, error_reason, request_processing_time, target_processing_time và response_processing_time.

### 6.1 Bật và đọc ALB access logs

ALB access logs bị tắt mặc định. Có thể lưu vào S3 theo log delivery configuration; AWS cũng cung cấp enhanced logging options qua CloudWatch Logs/Firehose/S3 trong console Integrations. Access logs là best-effort, có thể đến trễ và không nên dùng làm accounting tuyệt đối.

Các trường hữu ích:

| Field | Ý nghĩa |
|---|---|
| type/time | Protocol và thời điểm response |
| client:port | Client trực tiếp hoặc proxy trước ALB |
| target:port | Target đã xử lý request; dấu gạch ngang nếu không dispatch |
| request | Method, URL và protocol |
| request_processing_time | Thời gian ALB nhận/chuẩn bị request |
| target_processing_time | Thời gian ALB chờ target xử lý |
| response_processing_time | Thời gian ALB xử lý response trước khi gửi client |
| elb_status_code | Status do ALB/WAF/fixed response tạo |
| target_status_code | Status từ target |
| actions_executed | forward, redirect, fixed-response, authenticate, waf... |
| error_reason | Lý do lỗi ở các trường hợp được hỗ trợ |
| trace_id | X-Amzn-Trace-Id dùng để nối trace |

### 6.2 Phân biệt lỗi ALB và lỗi target bằng metric

| CloudWatch metric | Ý nghĩa |
|---|---|
| HTTPCode_ELB_4XX_Count | 4xx do ALB tạo |
| HTTPCode_ELB_5XX_Count | 5xx do ALB tạo |
| HTTPCode_Target_4XX_Count | 4xx do target tạo |
| HTTPCode_Target_5XX_Count | 5xx do target tạo |
| HealthyHostCount | Số target healthy |
| UnHealthyHostCount | Số target unhealthy |
| TargetResponseTime | Thời gian phản hồi của target |
| TargetConnectionErrorCount | Lỗi kết nối từ ALB tới target |
| RejectedConnectionCount | Kết nối bị ALB từ chối do capacity/connection limit |

Metric ELB và Target được tách riêng. Nếu HTTPCode_Target_5XX_Count tăng, xem application log và target health. Nếu HTTPCode_ELB_5XX_Count tăng, xem ALB access log, target registration, security group, connection và timeout.

### 6.3 ALB 400 Bad Request

Nguyên nhân có thể:

- Request line/header không hợp lệ hoặc thiếu.
- Content-Length/Transfer-Encoding không hợp lệ.
- Client gửi header quá lớn hoặc URI quá dài.
- HTTP protocol/version không được hỗ trợ.
- Desync mitigation phân loại request là ambiguous/severe.

Kiểm tra request raw, header, body size, protocol và classification_reason trong access log. Nếu chỉ một client/proxy bị lỗi, so sánh request headers do proxy thêm vào.

Nếu payload vượt giới hạn hoặc URI quá dài, ALB có thể trả 413 Payload Too Large hoặc 414 URI Too Long; hãy đọc status thực tế và request size thay vì gom tất cả vào 400.

### 6.4 ALB 401/403

Các nguyên nhân có thể:

- Listener rule dùng authenticate action và session/token không hợp lệ.
- AWS WAF block request (mặc định thường là 403 hoặc custom response).
- Fixed-response action trả 401/403.
- Target application trả 401/403.

Dùng actions_executed và target_status_code để phân biệt. Nếu actions_executed chứa waf và target:port là dấu gạch ngang, kiểm tra WAF logs/rule match. Nếu target_status_code=403, xem application authorization.

### 6.5 ALB 404 Not Found

ALB không cung cấp một routing 404 mặc định cho mọi trường hợp. 404 thường đến từ target/application hoặc fixed-response listener rule. Kiểm tra:

- Host/path condition của listener rule.
- Rule priority và default action.
- Rewrite/redirect transform nếu có.
- Target application route và deployment version.
- Target group/port mapping.

Nếu ALB access log có target_status_code=404, target đã trả 404. Nếu target_status_code không có và action là fixed-response, lỗi do listener rule.

### 6.6 ALB 502 Bad Gateway

Nguyên nhân thường gặp:

- Target gửi TCP RST khi ALB thiết lập kết nối.
- Target đóng kết nối bằng RST/FIN khi ALB còn request đang chờ.
- Response malformed hoặc header không hợp lệ/quá lớn.
- Target deregister trong khi request dài đang xử lý; deregistration delay không đủ.
- TLS handshake giữa ALB và HTTPS target thất bại.
- Lambda target trả response lỗi, timeout hoặc bị throttle.

Kiểm tra:

1. elb_status_code=502 và target_status_code có giá trị hay không.
2. target:port và target group health.
3. Application log có nhận request hay không.
4. Target keep-alive có ngắn hơn ALB idle timeout không.
5. Target response header có vượt giới hạn không.
6. Target group protocol/port/certificate có đúng không.
7. Deregistration delay và deployment drain behavior.

Nếu target_status_code là dấu gạch ngang, ưu tiên điều tra connection/TLS/target reset trước khi sửa business logic.

### 6.7 ALB 503 Service Unavailable

ALB có thể trả 503 khi target group không có registered target hoặc tất cả target đang ở trạng thái unused. Kiểm tra:

- Target group có target đã đăng ký không?
- Target có ở trạng thái healthy/initial/draining/unused?
- Health check path, port, protocol và matcher có đúng không?
- ECS/EKS/Auto Scaling có đủ task/pod/instance không?
- Deployment có deregister hết target trước khi target mới healthy không?
- Listener rule có forward tới đúng target group không?

Xem HealthyHostCount, UnHealthyHostCount, target health reason và deployment events. Nếu target count giảm về zero khi rollout, điều chỉnh deployment minimum healthy percentage, readiness/health check và capacity.

### 6.8 ALB 504 Gateway Timeout

Nguyên nhân thường gặp:

- ALB không kết nối được target trong connection timeout.
- Target đã nhận kết nối nhưng không phản hồi trước idle timeout.
- Network ACL không cho phép return traffic từ target tới ALB trên ephemeral ports 1024–65535.
- Target trả Content-Length lớn hơn body thực tế khiến ALB chờ byte còn thiếu.
- Lambda target không phản hồi trong thời gian cho phép.

Đối chiếu request_processing_time, target_processing_time và response_processing_time. Nếu target_processing_time gần idle timeout, xem database, thread pool, lock, dependency và queue. Nếu không có kết nối target, kiểm tra route, SG, NACL, port và listener protocol.

### 6.9 Kiểm tra target health

Health check là request riêng, không phải bản sao hoàn toàn của request người dùng. Kiểm tra:

- Health check path trả đúng status code matcher.
- Application bind vào 0.0.0.0/private interface thay vì chỉ localhost.
- Security group cho phép traffic từ ALB security group tới target port.
- Startup grace/readiness đủ lâu.
- Health endpoint không phụ thuộc quá nhiều dịch vụ downstream nếu chỉ cần xác nhận process sống.
- Target deregistration delay phù hợp với request dài.

Một target healthy vẫn có thể trả 500 cho một route; health check thành công chỉ chứng minh endpoint health check đáp ứng điều kiện đã cấu hình.

## 7. Chẩn đoán lỗi tại Amazon API Gateway

API Gateway có thể tạo lỗi trước khi gọi integration hoặc chuyển tiếp lỗi từ integration. REST API, HTTP API và WebSocket API có khả năng logging, response type và context variable khác nhau; khi đọc log phải biết API type và stage.

### 7.1 Phân biệt lỗi gateway và integration

| Nhóm | Ví dụ | Hướng điều tra |
|---|---|---|
| Request validation | 400 BAD_REQUEST_BODY/PARAMETERS | Request model, required parameter, validator |
| Authentication/authorization | 401/403 | Authorizer, JWT/Cognito/IAM, resource policy, API key |
| Route/resource | 403 MISSING_AUTHENTICATION_TOKEN hoặc 404 | Method, route, stage, base path mapping |
| Throttling/quota | 429 THROTTLED/QUOTA_EXCEEDED | Account, stage, method, usage plan |
| Integration response | 4xx/5xx từ backend | Integration status và backend log |
| Integration failure | 5xx/504 | Endpoint unavailable, permission, network, response mapping |
| Integration timeout | 504 | Integration latency, timeout setting và backend runtime |
| API configuration | 500 | Integration URI, mapping template, authorizer config, deployment |

Một status code có thể được tùy chỉnh qua GatewayResponse hoặc integration response mapping. Hãy xem response type, gateway log và integration status thay vì chỉ nhìn body trả về.

### 7.2 API Gateway 400 Bad Request

Nguyên nhân thường gặp:

- Request validator từ chối query/path/header parameter.
- Body không khớp JSON schema/model.
- Mapping template hoặc request transformation không xử lý đúng input.

Kiểm tra method/route, request model, required fields, content type, binary media type và mapping template. So sánh payload thực tế với một request hợp lệ.

Với REST API, request quá lớn có thể trả 413 REQUEST_TOO_LARGE; media type không được hỗ trợ có thể trả 415 UNSUPPORTED_MEDIA_TYPE. Hãy phân biệt hai response type này với lỗi validation 400.

### 7.3 API Gateway 401 Unauthorized

Kiểm tra:

- Token có hết hạn, sai issuer/audience hoặc chữ ký không hợp lệ không?
- JWT/Cognito authorizer có cấu hình đúng identity source không?
- Lambda authorizer có trả policy/context hợp lệ không?
- IAM SigV4 request có ký đúng service/Region/path không?
- Custom domain, stage hoặc authorization type có thay đổi không?

Không log raw bearer token. Ghi request ID, authorizer status, error category và principal đã được ẩn danh.

### 7.4 API Gateway 403 Forbidden

REST API Gateway có nhiều response type 403:

| Gateway response type | Nguyên nhân thường gặp |
|---|---|
| ACCESS_DENIED | Authorizer, Cognito/JWT scope hoặc resource policy từ chối |
| INVALID_API_KEY | API key không hợp lệ hoặc không được gửi |
| INVALID_SIGNATURE | AWS Signature không hợp lệ |
| EXPIRED_TOKEN | Token AWS hết hạn |
| MISSING_AUTHENTICATION_TOKEN | Method/resource không tồn tại hoặc request dùng sai path/method |
| WAF_FILTERED | AWS WAF chặn request |

403 không đồng nghĩa token hết hạn. Kiểm tra API Gateway access log, authorizer log, WAF log, resource policy, API key/usage plan và custom domain mapping.

### 7.5 API Gateway 404 và MISSING_AUTHENTICATION_TOKEN

REST API có thể trả 403 MISSING_AUTHENTICATION_TOKEN khi client gọi method hoặc resource không được hỗ trợ. HTTP API thường trả route-not-found theo behavior riêng. Đối chiếu:

- API ID và stage.
- Resource path/route key.
- HTTP method.
- Custom domain API mapping/base path.
- Deployment đã cập nhật stage chưa.
- Path bị CloudFront origin path hoặc API mapping thêm/bớt prefix không.

Không sửa authorizer khi nguyên nhân thực tế là path/method không khớp.

### 7.6 API Gateway 429 Too Many Requests

429 có thể do throttling hoặc quota:

- Account-level throttle quota.
- Stage/method/route throttling.
- Usage plan quota cho API key (REST API).
- Backend hoặc integration tự trả 429.

Đối chiếu API Gateway metrics, usage plan, stage settings, integration logs và backend throttling. Dùng exponential backoff có jitter, tôn trọng Retry-After nếu có và giới hạn concurrency. Không retry liên tục ở client vì có thể làm tình trạng throttling nặng hơn.

### 7.7 API Gateway 500 Internal Server Error

Các response type có thể gồm API_CONFIGURATION_ERROR, AUTHORIZER_CONFIGURATION_ERROR, AUTHORIZER_FAILURE hoặc DEFAULT_5XX. Kiểm tra:

- Integration URI/endpoint có hợp lệ không?
- API deployment có chứa cấu hình mới không?
- Mapping template có lỗi không?
- Authorizer có timeout hoặc exception không?
- IAM permission cho API Gateway invoke Lambda/other integration có đúng không?
- Backend có throw exception hay trả response lỗi không?

Tách log gateway và log integration. Nếu backend không nhận request, điều tra API configuration/permission/network; nếu backend có nhận, dùng request ID để tìm stack trace.

### 7.8 API Gateway 502 Bad Gateway

Với Lambda proxy integration, Lambda phải trả response đúng schema. Ví dụ:

    {
      "statusCode": 200,
      "headers": {
        "Content-Type": "application/json"
      },
      "body": "{\"message\":\"ok\"}",
      "isBase64Encoded": false
    }

Nếu function trả object sai format, body không phải chuỗi theo yêu cầu, JSON không serialize được hoặc function throw exception, API Gateway có thể trả 502. Với HTTP/custom integration, response không hợp lệ hoặc mapping sai cũng có thể tạo 502.

Kiểm tra:

1. Lambda invocation có xảy ra không?
2. Lambda có exception, timeout, throttle hoặc out-of-memory không?
3. Response có statusCode, headers, body và isBase64Encoded đúng format không?
4. Body có serialize đúng và header/content type hợp lệ không?
5. Mapping template có tạo response không hợp lệ không?
6. Với VPC Link, endpoint/target group/listener có healthy và reachable không?

Đừng nhầm HTTP status 502 do Lambda trả có chủ đích với 502 do API Gateway không parse được response. Xem integration status, integration error và Lambda logs.

### 7.9 API Gateway 503 Service Unavailable

503 thường chỉ ra integration/backend không sẵn sàng hoặc quá tải. Kiểm tra:

- Backend capacity, connection pool và deployment/maintenance.
- VPC Link status, subnet/ENI và security group.
- ALB/NLB target health nếu dùng private integration.
- Lambda concurrency/throttling nếu integration là Lambda.
- Service discovery/DNS nếu dùng HTTP integration.
- Integration error và backend response status.

Nếu backend tạm thời unavailable, trả 503 có chủ đích và hướng dẫn client retry với backoff. Nếu 503 do gateway/integration network, sửa connectivity/capacity trước khi retry traffic lớn.

### 7.10 API Gateway 504 Gateway Timeout

504 xuất hiện khi integration request vượt quá maximum integration timeout được cấu hình. Với REST API, mặc định thường là 29 giây. AWS cho phép yêu cầu tăng quota cho Regional và private REST APIs; việc tăng có thể yêu cầu giảm account-level throttle quota. Sau khi tăng quota, phải cập nhật timeout trên integration và redeploy API để cấu hình có hiệu lực.

Với HTTP API hoặc WebSocket API, kiểm tra timeout limit riêng của loại API và integration; không áp dụng con số REST API cho mọi API type.

Quy trình:

1. Xem API Gateway IntegrationLatency/Latency và access log.
2. Kiểm tra integration có được gọi không.
3. Nếu là Lambda, so sánh Lambda Duration và timeout.
4. Nếu là HTTP/VPC Link, đo thời gian connect, time to first byte và backend duration.
5. Kiểm tra ALB target_processing_time, target health và database/dependency latency.
6. Tách công việc hậu xử lý không cần thiết khỏi synchronous request.
7. Nếu nghiệp vụ dài, chuyển sang asynchronous job: trả 202 + job ID, xử lý nền và cung cấp endpoint truy vấn trạng thái.

### 7.11 REST API execution logs và access logs

REST API có execution logging và access logging:

- Execution logs cho biết request execution, mapping và integration errors; bật ERROR hoặc INFO theo nhu cầu.
- Access logs ghi một record có cấu trúc cho mỗi request với các context variable do bạn chọn.
- Data tracing có thể ghi payload nhạy cảm; không nên bật trên production API nếu không có kiểm soát rõ.

HTTP APIs hỗ trợ access logging qua CloudWatch Logs; khả năng execution logging và context fields khác REST API. Dùng đúng tài liệu theo API type.

### 7.12 Access log format khuyến nghị

Ví dụ JSON format cho REST API; các context variable phải đặt dưới dạng chuỗi literal khi cấu hình access log:

    {
      "requestId": "$context.requestId",
      "extendedRequestId": "$context.extendedRequestId",
      "requestTime": "$context.requestTime",
      "httpMethod": "$context.httpMethod",
      "resourcePath": "$context.resourcePath",
      "status": "$context.status",
      "responseLatency": "$context.responseLatency",
      "integrationStatus": "$context.integration.status",
      "integrationLatency": "$context.integration.latency",
      "integrationError": "$context.integration.error",
      "authorizerStatus": "$context.authorizer.status",
      "wafStatus": "$context.waf.status"
    }

Tránh ghi Authorization header, cookie, API key, request body hoặc dữ liệu nhạy cảm vào access log. extendedRequestId do API Gateway tạo; requestId có thể được client cung cấp trong một số trường hợp, nên dùng extendedRequestId làm ID do gateway kiểm soát.

### 7.13 CloudWatch metrics của API Gateway

Các metric quan trọng:

| Metric | Ý nghĩa |
|---|---|
| Count | Tổng request |
| 4XXError | Số lỗi 4xx |
| 5XXError | Số lỗi 5xx |
| Latency | Thời gian từ API Gateway nhận request đến khi trả response |
| IntegrationLatency | Thời gian từ lúc gateway gửi request đến backend đến khi nhận response |

Nếu Latency cao nhưng IntegrationLatency thấp, xem overhead gateway, authorization, mapping hoặc network path. Nếu IntegrationLatency chiếm phần lớn Latency, điều tra backend. Bật detailed metrics theo method/resource/stage nếu cần phân tích sâu; metric chi tiết có thể phát sinh phí.

## 8. Correlation ID và tracing xuyên nhiều tầng

Khi request đi qua nhiều gateway, mỗi dịch vụ có request identifier riêng. Không nên kỳ vọng một ID tự động xuất hiện trong mọi log. Hãy giữ các ID gốc và truyền một correlation ID của ứng dụng qua những header được phép.

### 8.1 Các ID thường gặp

| Thành phần | ID/header | Mục đích |
|---|---|---|
| CloudFront | x-amz-cf-id / x-edge-request-id | Nhận diện request ở edge |
| ALB | X-Amzn-Trace-Id / trace_id trong access log | Nối request với trace |
| API Gateway REST | extendedRequestId / requestId | Tìm access/execution log |
| API Gateway | x-amzn-RequestId hoặc x-amz-apigw-id khi response cung cấp | Hỗ trợ client ghi nhận gateway request |
| AWS X-Ray | Trace ID | Nối segment/subsegment giữa service hỗ trợ tracing |
| Application | X-Correlation-ID do ứng dụng tạo/duy trì | Nối log giữa service và workflow |

Không gộp các ID này thành một giá trị. Ghi từng ID vào structured log để có thể tìm request ở từng tầng.

### 8.2 Propagate correlation ID

Application gateway có thể tạo correlation ID nếu client không gửi. Nếu nhận ID từ client, validate charset/length, giới hạn độ dài và không dùng nó làm identity hoặc authorization token. Ghi thêm request ID của AWS để có thể tra cứu log native.

Ví dụ log application:

    {
      "timestamp": "2026-11-20T08:15:30.123Z",
      "level": "ERROR",
      "service": "orders-api",
      "correlation_id": "req-7f4d3c",
      "cloudfront_request_id": "opaque-edge-id",
      "api_gateway_extended_request_id": "gateway-id",
      "alb_trace_id": "Root=1-...",
      "route": "POST /orders",
      "status": 500,
      "error_code": "DB_POOL_EXHAUSTED"
    }

Đây là ví dụ cấu trúc; không ghi payload, token hoặc PII nếu không cần. Với nhiều service, giữ correlation ID xuyên qua message attributes, workflow input và downstream request.

### 8.3 X-Ray và service map

AWS X-Ray có thể giúp xem segment/subsegment và latency giữa các thành phần được instrument. API Gateway REST API hỗ trợ X-Ray tracing theo cấu hình stage; Lambda, application SDK và một số AWS service có thể tạo segment liên quan.

X-Ray không tự động thay thế access logs. Dùng trace để xem thời gian và dependency; dùng access logs để biết request/status/target; dùng application logs để đọc stack trace và business error. Kiểm tra sampling vì không phải mọi request đều được trace.

## 9. Timeout budget giữa CloudFront, API Gateway, ALB và backend

Nhiều lỗi 504 xuất hiện vì timeout của tầng ngoài ngắn hơn thời gian xử lý hợp lệ của tầng trong. Thiết kế timeout theo request path thực tế.

### 9.1 Nguyên tắc

Với request đồng bộ, timeout của từng bước bên trong nên ngắn hơn deadline của bước gọi nó, có margin cho network, serialization và response transfer. Ví dụ:

    Database/dependency timeout
              <
       Application deadline
              <
       ALB target idle budget
              <
       API Gateway integration timeout
              <
       CloudFront origin response timeout
              <
       Client deadline

Đây là thứ tự minh họa cho một topology cụ thể, không phải cấu hình mặc định cho mọi hệ thống. Nếu một lớp không tồn tại trong topology, bỏ lớp đó khỏi chuỗi. Với streaming, timeout có thể áp dụng theo khoảng im lặng giữa các byte thay vì tổng thời gian toàn request.

### 9.2 Ví dụ request CloudFront → API Gateway → ALB → service

Giả sử service cần tối đa 8 giây để hoàn thành một request:

- Database query deadline: 5 giây.
- Application deadline: 10 giây.
- ALB idle timeout: đủ dài để application hoàn thành và gửi response.
- API Gateway integration timeout: dài hơn thời gian hợp lệ của ALB/backend.
- CloudFront origin response timeout: dài hơn API Gateway timeout và response transfer.
- Client timeout: dài hơn CloudFront timeout.

Các con số là ví dụ sizing, không phải AWS defaults. Đo p95/p99 và đặt margin theo SLA. Với REST API, integration timeout mặc định thường là 29 giây; nếu tăng quota cho Regional/private API, cần xem trade-off account throttle quota và redeploy API.

### 9.3 Khi nào tăng timeout?

Chỉ tăng timeout sau khi xác nhận:

- Backend thực sự cần thời gian dài và có capacity.
- Không có deadlock, connection pool exhaustion hoặc dependency chậm bất thường.
- Client và mọi gateway ở phía ngoài có timeout phù hợp.
- Worker/thread/concurrency đủ để phục vụ request kéo dài.
- Request có thể retry an toàn nếu connection bị cắt.

Nếu công việc mất nhiều phút, thường nên chuyển sang asynchronous pattern: nhận request, tạo job, trả 202 Accepted + job ID, xử lý nền và cung cấp API lấy trạng thái/kết quả.

### 9.4 Retry và side effects

Timeout không chứng minh backend chưa thực hiện hành động. Ví dụ POST /payments có thể đã ghi giao dịch nhưng response bị mất ở CloudFront/API Gateway. Client retry mù có thể tạo giao dịch trùng.

Với POST/PUT có side effect:

- Dùng idempotency key theo business request.
- Lưu kết quả theo key trước khi trả response.
- Retry chỉ khi API contract cho phép.
- Dùng exponential backoff và jitter cho lỗi transient/429/503.
- Không retry lỗi validation/authentication 4xx.
- Giới hạn số lần retry và tổng retry budget.

## 10. Bảng đối chiếu nhanh theo status code

| Status | CloudFront | ALB | API Gateway |
|---|---|---|---|
| 400 | Request/headers/URI hoặc origin trả 400 | Request malformed/headers/content length | Request validation, body/parameter/schema |
| 401 | Origin/authentication response hoặc custom behavior | Authenticate action/target response | Authorizer/token authentication |
| 403 | WAF, geo, signed URL/cookie, S3/OAC hoặc origin | WAF, authenticate/fixed response hoặc target | Authorizer, resource policy, API key/signature, WAF |
| 404 | Object/path/origin route hoặc cached error | Thường target/fixed response/listener route | Resource/route/stage/base path mapping |
| 429 | Origin/WAF/quota behavior | Target hoặc WAF/custom response | Throttle/usage quota hoặc integration |
| 500 | Origin/application/function error | Target response hoặc LB internal/config error | API configuration, authorizer/integration/backend |
| 502 | DNS/TLS/connection/invalid origin response | Target reset/malformed response/TLS | Lambda proxy format, integration response/network |
| 503 | Edge capacity/quota hoặc origin unavailable | Không có target usable | Backend/integration unavailable |
| 504 | Origin connect/read timeout | Target connection/idle timeout | Integration timeout |

Status code chỉ là gợi ý. Luôn kiểm tra log field xác định nguồn response.

## 11. Runbook chẩn đoán theo triệu chứng

### 11.1 Viewer nhận 403 nhưng origin không thấy request

1. Lấy X-Amz-Cf-Id và thời điểm UTC.
2. Tìm CloudFront standard/real-time log theo x-edge-request-id.
3. Xem x-edge-detailed-result-type, x-edge-result-type và sc-status.
4. Kiểm tra AWS WAF sampled requests/logs và geo restriction.
5. Kiểm tra signed URL/cookie, CloudFront Function/Lambda@Edge.
6. Nếu origin là S3, kiểm tra OAC/OAI, bucket policy, object key và KMS.
7. Sửa rule/policy đã xác định, chạy regression test và theo dõi block rate.

### 11.2 CloudFront trả 502, ALB không có log tương ứng

1. Xác minh request có cache miss và CloudFront thực sự gọi origin.
2. Kiểm tra origin domain DNS.
3. Kiểm tra TLS certificate expiry, SAN/CN, chain và SNI.
4. Kiểm tra CloudFront origin protocol/port.
5. Kiểm tra security group/firewall/network ACL và origin reachability.
6. Kiểm tra function association nếu có.
7. Gọi origin trực tiếp trong môi trường được phép để so sánh.

### 11.3 ALB trả 502

1. Tìm access log theo thời gian, path và trace_id.
2. So sánh elb_status_code với target_status_code.
3. Nếu target_status_code là dấu gạch ngang, kiểm tra target reset, SG/NACL, port, TLS và connection.
4. Nếu target_status_code có 5xx, tìm application log.
5. Kiểm tra keep-alive, idle timeout, header size và deregistration delay.
6. Kiểm tra TargetConnectionErrorCount và target health.

### 11.4 ALB trả 503 sau deployment

1. Kiểm tra HealthyHostCount/UnHealthyHostCount theo target group.
2. Xem ECS service events, EKS rollout/pod readiness hoặc Auto Scaling activity.
3. Kiểm tra target group registration/deregistration.
4. Kiểm tra health check path, matcher, port và security group.
5. Xác minh deployment có giữ đủ healthy capacity trong lúc thay phiên bản.
6. Rollback nếu không thể khôi phục target healthy trong SLA.

### 11.5 API Gateway trả 502

1. Tìm access log theo extendedRequestId.
2. Kiểm tra integration.status, integration.integrationStatus và integration.error.
3. Xác minh backend có nhận request không.
4. Nếu Lambda proxy, kiểm tra Lambda log và response format.
5. Nếu VPC Link, kiểm tra VPC Link status, listener, target health và network.
6. Kiểm tra mapping template, content type và binary/base64 handling.

### 11.6 API Gateway trả 504

1. Kiểm tra IntegrationLatency và Latency.
2. Tìm execution log có timeout error (nếu REST API).
3. Dùng extendedRequestId nối với Lambda/ALB/application logs.
4. Xác định integration đã được gọi chưa.
5. So sánh Lambda Duration, ALB target_processing_time và database latency.
6. Tối ưu backend hoặc chuyển công việc dài sang asynchronous processing.
7. Chỉ yêu cầu tăng integration timeout khi đã có bằng chứng và SLA phù hợp.

### 11.7 Tỷ lệ 5xx tăng đột biến

- Xác định bắt đầu từ lúc nào và có trùng deploy/configuration change không.
- Phân tách theo status, API route, cache behavior, target group và AZ.
- Kiểm tra 5XX metric của CloudFront, HTTPCode_ELB_5XX_Count, HTTPCode_Target_5XX_Count và API Gateway 5XXError.
- Kiểm tra HealthyHostCount, CPU/memory, connection pool, throttling và dependency latency.
- Giảm traffic/canary rollback nếu thay đổi mới là nguyên nhân.
- Không scale đồng thời nhiều lớp trước khi biết bottleneck; có thể làm downstream quá tải hơn.

## 12. Case study: API đặt hàng trả 502/504 sau khi triển khai

### 12.1 Kiến trúc

Một ứng dụng thương mại điện tử dùng CloudFront làm public entry point, API Gateway REST API để xác thực và route, VPC Link tới ALB nội bộ, sau đó ALB forward đến ECS service xử lý đơn hàng. Database nằm trong private subnet.

### 12.2 Triệu chứng

- Người dùng thấy 504 ở một số request POST /orders.
- Một số request khác trả 502.
- CloudFront standard logs cho thấy status 504 và x-edge-result-type=Error.
- API Gateway metrics có IntegrationLatency tăng mạnh.
- ALB target group vẫn có HealthyHostCount lớn hơn zero.

### 12.3 Điều tra

1. Dùng x-edge-request-id để tìm CloudFront log và xác nhận request là Miss, được forward tới origin.
2. Dùng API Gateway extendedRequestId để tìm access log; integration status cho thấy timeout.
3. Dùng thời gian và correlation ID để tìm ALB access log.
4. ALB log có target_status_code=200 cho một số request, nhưng target_processing_time tăng gần giới hạn timeout ở các request khác.
5. Application log cho thấy connection pool database cạn sau deployment; mỗi request giữ connection trong khi chờ một query chậm.
6. Một số request đã ghi đơn hàng nhưng response không tới client trước khi gateway timeout.

### 12.4 Root cause và khắc phục

Nguyên nhân chính là connection pool và query latency tăng sau deploy. API Gateway timeout trước khi backend hoàn thành; CloudFront cũng có thể timeout nếu response timeout ngắn hơn hoặc gần với API Gateway integration timeout.

Khắc phục:

- Rollback phiên bản có query regression.
- Tối ưu query và giới hạn concurrency.
- Đặt application/database deadline rõ ràng.
- Giữ ALB/API Gateway/CloudFront timeout theo thứ tự phù hợp với SLA.
- Thêm idempotency key cho POST /orders vì request timeout có thể đã ghi đơn.
- Thêm alarm cho API Gateway IntegrationLatency, ALB TargetResponseTime, target 5xx và database connection pool.

### 12.5 Bài học

HealthyHostCount chỉ cho biết target vượt health check; nó không chứng minh mọi route đều xử lý nhanh. CloudFront 504 cũng không tự chứng minh CloudFront có lỗi. Phải nối request ID qua từng tầng và tìm thành phần đầu tiên vượt thời gian hoặc trả lỗi.

## 13. Lab A: điều tra lỗi origin của CloudFront

### Mục tiêu

Quan sát cách CloudFront ghi nhận lỗi origin và phân biệt lỗi edge/origin trong một distribution thử nghiệm.

### Chuẩn bị

- CloudFront distribution non-production.
- Một custom origin/ALB thử nghiệm có HTTPS.
- Access logging cho distribution.
- Quyền xem DNS, certificate, origin configuration và WAF logs.

### Bước 1: kiểm tra request thành công

1. Gọi URL qua CloudFront bằng curl.
2. Ghi status, X-Cache, Via và X-Amz-Cf-Id.
3. Xác nhận access log có sc-status, x-edge-result-type và x-edge-request-id.
4. So sánh origin log cùng thời điểm.

### Bước 2: tạo lỗi có kiểm soát

Trong môi trường lab, cấu hình origin domain hoặc TLS certificate không khớp để tạo lỗi 502. Không thay đổi distribution production. Ghi lại response header và log detail.

### Bước 3: phân tích

1. Tìm x-edge-request-id.
2. Kiểm tra x-edge-detailed-result-type.
3. Xác minh origin có nhận request không.
4. Dùng nslookup/dig và openssl s_client để kiểm tra DNS/TLS.
5. Khôi phục origin configuration.
6. Gọi lại và xác nhận 2xx.

### Bước 4: kiểm tra error caching

1. Tạo một lỗi 404 ở origin thử nghiệm.
2. Gọi lại cùng object/path.
3. Xem X-Cache và thời gian response.
4. Kiểm tra Error Caching Minimum TTL/cache policy.
5. Sửa object/route và xác minh thời điểm edge thử lại origin.

## 14. Lab B: phân biệt lỗi do ALB và target

### Mục tiêu

Dùng ALB access logs và CloudWatch metrics để xác định status do load balancer hay target tạo.

### Chuẩn bị

- ALB non-production với target group gồm ít nhất một ECS/EC2 test target.
- Bật ALB access logs.
- Bật CloudWatch metrics dashboard.
- Ứng dụng test có thể trả 200, 403, 500 và trì hoãn response.

### Bước 1: tạo response từ target

1. Gọi route trả 500 từ application.
2. Tìm access log tương ứng.
3. Xác nhận elb_status_code=500 và target_status_code=500.
4. Kiểm tra HTTPCode_Target_5XX_Count tăng.

### Bước 2: tạo lỗi do ALB

Trong lab, cấu hình target group không có target usable hoặc tạm thời deregister test target. Gọi request và xác nhận ALB trả 503. Kiểm tra elb_status_code và target_status_code.

### Bước 3: tạo timeout

1. Tạo endpoint test có response delay được kiểm soát.
2. Điều chỉnh timeout trong lab để tạo 504.
3. So sánh target_processing_time với idle timeout.
4. Xem HTTPCode_ELB_504_Count và HTTPCode_Target_5XX_Count.

### Bước 4: khôi phục

Đăng ký target lại, xác minh health check, khôi phục timeout và kiểm tra 2xx. Dọn target, rule và log không cần giữ.

## 15. Lab C: điều tra API Gateway 502/504

### Mục tiêu

Tạo hai lỗi integration phổ biến và tìm nguyên nhân trong API Gateway logs.

### Chuẩn bị

- REST API non-production.
- Lambda proxy integration.
- CloudWatch execution/access logging.
- Lambda CloudWatch logs.

### Bước 1: bật logging

1. Bật execution logging ở mức ERROR hoặc INFO.
2. Bật access logging với requestId, extendedRequestId, status, integrationStatus, integrationLatency và integrationError.
3. Không bật data tracing cho payload nhạy cảm.
4. Gọi endpoint thành công và lưu request ID.

### Bước 2: tạo 502 do response format

Trong Lambda test, trả một object không theo Lambda proxy response schema. Gọi endpoint, lấy extendedRequestId và tìm execution log. Xác nhận Lambda đã được invoke nhưng API Gateway không thể chuyển response hợp lệ.

### Bước 3: tạo 504 do timeout

1. Tạo Lambda test có delay dài hơn integration timeout của lab.
2. Gọi endpoint và ghi lại status/latency.
3. Tìm access log và execution log theo extendedRequestId.
4. So sánh IntegrationLatency với Lambda Duration.
5. Khôi phục timeout và Lambda code.

### Bước 4: kiểm tra 403/429

Thử token/API key không hợp lệ hoặc gửi request vượt throttling quota trong môi trường lab. Xác định gateway response type và phân biệt với response do backend trả.

### Bước 5: dọn lab

Khôi phục code/config, xóa test API/key/usage plan nếu không dùng và đặt retention log phù hợp.

## 16. Truy vấn log mẫu

### 16.1 API Gateway access logs trong CloudWatch Logs Insights

Nếu access log được lưu dạng JSON và có field tương ứng:

    fields @timestamp, extendedRequestId, httpMethod, resourcePath,
           status, integrationStatus, integrationLatency, integrationError
    | filter status >= 500
    | sort @timestamp desc
    | limit 100

Tìm integration timeout:

    fields @timestamp, @message
    | filter @message like /Execution failed due to a timeout/
    | sort @timestamp desc
    | limit 100

### 16.2 ALB metrics

Tạo dashboard theo cùng khoảng thời gian với:

- HTTPCode_ELB_4XX_Count và HTTPCode_ELB_5XX_Count.
- HTTPCode_Target_4XX_Count và HTTPCode_Target_5XX_Count.
- HealthyHostCount và UnHealthyHostCount.
- TargetResponseTime.
- TargetConnectionErrorCount.
- RejectedConnectionCount.

Dùng statistic Sum cho error counters; dùng Minimum/Average/Maximum phù hợp cho target health và latency. Kiểm tra dimensions theo LoadBalancer, TargetGroup và AvailabilityZone.

### 16.3 CloudFront logs

Với standard logs trên S3, lọc theo:

- sc-status thuộc 400–599.
- x-edge-result-type=Error hoặc CapacityExceeded/LimitExceeded.
- x-edge-detailed-result-type để xác định loại lỗi.
- x-edge-request-id để tra một request.
- cache-behavior-path-pattern để biết behavior đã match.
- time-taken và time-to-first-byte để so sánh latency.

Nếu dùng Athena, tạo table theo schema CloudFront log fields thực tế. Cập nhật schema khi AWS bổ sung field; không giả định mọi file log đều có cùng số cột nếu parser chưa xử lý version.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể kết luận nguyên nhân chỉ từ status 502?

**Đáp án:** CloudFront, ALB, API Gateway hoặc application đều có thể tạo 502 với nguyên nhân khác nhau; phải xác định tầng tạo response qua log và request ID.

**Câu 2.** CloudFront, ALB và API Gateway có luôn nằm trên cùng một request path không?

**Đáp án:** Không. Có nhiều topology như CloudFront → ALB, CloudFront → API Gateway hoặc API Gateway → VPC Link → ALB/NLB.

**Câu 3.** Trường CloudFront nào giúp nối response với access log?

**Đáp án:** X-Amz-Cf-Id ở response và x-edge-request-id trong standard logs.

**Câu 4.** x-edge-detailed-result-type dùng để làm gì?

**Đáp án:** Cung cấp chi tiết hơn về lỗi CloudFront, ví dụ lỗi origin, viewer hoặc internal error.

**Câu 5.** CloudFront 502 thường do nguyên nhân nào?

**Đáp án:** DNS, TLS/certificate, port/network, origin response malformed hoặc Lambda@Edge/CloudFront Function validation.

**Câu 6.** Vì sao CloudFront có thể tiếp tục trả 404 sau khi origin đã sửa?

**Đáp án:** Error response có thể đang được cache theo Error Caching Minimum TTL hoặc Cache-Control.

**Câu 7.** elb_status_code và target_status_code khác nhau thế nào?

**Đáp án:** elb_status_code là response do ALB/WAF/fixed-response tạo; target_status_code là status từ target khi target đã gửi response.

**Câu 8.** Metric nào cho biết 5xx do ALB tạo?

**Đáp án:** HTTPCode_ELB_5XX_Count.

**Câu 9.** Metric nào cho biết 5xx do target tạo?

**Đáp án:** HTTPCode_Target_5XX_Count.

**Câu 10.** ALB 503 thường có nghĩa gì?

**Đáp án:** Target group không có registered target hoặc tất cả target ở trạng thái unused/không sẵn sàng.

**Câu 11.** ALB 504 thường do nguyên nhân nào?

**Đáp án:** Không kết nối được target trong connection timeout, target không phản hồi trước idle timeout hoặc network ACL chặn return traffic.

**Câu 12.** API Gateway 403 có luôn là token hết hạn không?

**Đáp án:** Không. Có thể do authorizer, API key, signature, resource policy, WAF hoặc sai method/resource dẫn đến MISSING_AUTHENTICATION_TOKEN.

**Câu 13.** Vì sao Lambda proxy integration có thể trả 502?

**Đáp án:** Lambda trả response không đúng schema proxy, throw exception hoặc response không serialize/parse được.

**Câu 14.** API Gateway 429 thường do gì?

**Đáp án:** Account/stage/method throttling, usage plan quota hoặc backend tự trả 429.

**Câu 15.** IntegrationLatency khác Latency thế nào?

**Đáp án:** IntegrationLatency đo thời gian gateway chờ backend; Latency đo toàn bộ thời gian từ khi gateway nhận request đến khi trả response.

**Câu 16.** REST API integration timeout mặc định thường là bao lâu?

**Đáp án:** Thường là 29 giây; có thể yêu cầu tăng cho Regional/private REST APIs, nhưng có thể ảnh hưởng account throttle quota.

**Câu 17.** Vì sao không nên bật data tracing rộng trên production API?

**Đáp án:** Execution data có thể chứa payload, token hoặc dữ liệu nhạy cảm; logging có thể làm lộ thông tin và tăng chi phí.

**Câu 18.** Vì sao cần idempotency key khi retry POST sau timeout?

**Đáp án:** Backend có thể đã thực hiện side effect nhưng response bị mất; idempotency key ngăn tạo giao dịch hoặc record trùng.

**Câu 19.** Nếu CloudFront 502 nhưng ALB không có access log tương ứng, nên kiểm tra gì trước?

**Đáp án:** CloudFront origin DNS, TLS certificate/SNI, port, network/firewall và edge function trước khi điều tra application.

**Câu 20.** Khi nào nên chuyển API xử lý dài sang asynchronous job?

**Đáp án:** Khi thời gian xử lý vượt timeout đồng bộ hoặc có thể kéo dài không dự đoán được; API nhận job, trả 202 + job ID và xử lý nền.

## 18. Checklist production readiness

- [ ] Topology thực tế và thứ tự các gateway đã được ghi lại.
- [ ] Mỗi API route/path được ánh xạ tới đúng CloudFront behavior, origin, API stage và ALB target group.
- [ ] CloudFront standard/real-time logging được bật theo nhu cầu và retention.
- [ ] ALB access logging hoặc enhanced logging được bật.
- [ ] API Gateway access logging được cấu hình cho đúng API type.
- [ ] REST API execution logging dùng mức phù hợp; data tracing không bật rộng trên production.
- [ ] Response headers/request IDs được giữ lại trong client diagnostics.
- [ ] Correlation ID được validate và propagate xuyên các service.
- [ ] Không ghi token, cookie, API key, PII hoặc payload nhạy cảm không cần thiết.
- [ ] CloudFront origin DNS, TLS, SNI, certificate chain và port được kiểm thử.
- [ ] CloudFront cache/error caching/custom error page được rà soát.
- [ ] ALB listener rules, target group, target health và deregistration delay được kiểm thử.
- [ ] ALB elb_status_code và target_status_code được đưa vào log analysis.
- [ ] ALB ELB/Target 4xx/5xx metrics có dashboard và alarm.
- [ ] API Gateway authorizer, resource policy, API key, WAF và route mapping được kiểm thử.
- [ ] Lambda proxy response format và integration mapping có regression test.
- [ ] VPC Link, security group, NACL, subnet IP và target reachability được xác minh.
- [ ] Timeout budget giữa dependency, application, ALB, API Gateway, CloudFront và client được thống nhất.
- [ ] Retry có backoff/jitter, giới hạn attempts và idempotency cho side effects.
- [ ] 429/503 có backpressure và retry policy phù hợp.
- [ ] 502/503/504 runbook chỉ rõ log, metric, owner và rollback.
- [ ] Có test non-production cho WAF block, malformed response, target unavailable và timeout.
- [ ] Có alarm cho error rate, latency, target health, integration latency và queue/connection saturation.
- [ ] Có kế hoạch rollback khi lỗi tăng sau deployment/configuration change.

## 19. Tài liệu tham khảo chính thức

1. [Troubleshooting error response status codes in CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/troubleshooting-response-errors.html) — tổng quan cách xử lý 4xx/5xx.
2. [How CloudFront processes HTTP 4xx and 5xx status codes](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HTTPStatusCodes.html) — error caching và custom error pages.
3. [CloudFront HTTP 502 Bad Gateway](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/http-502-bad-gateway.html) — DNS, TLS, certificate và origin connection.
4. [CloudFront HTTP 504 Gateway Timeout](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/http-504-gateway-timeout.html) — origin timeout.
5. [CloudFront origin settings](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html) — connection/response timeout.
6. [CloudFront standard logging](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/standard-logging.html) — bật log và các field.
7. [CloudFront standard logs reference](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/standard-logs-reference.html) — sc-status, x-edge-result-type và request ID.
8. [Troubleshoot your Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html) — nguyên nhân ALB 4xx/5xx.
9. [ALB access logs](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html) — elb_status_code, target_status_code và timing fields.
10. [ALB CloudWatch metrics](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html) — ELB/Target error metrics và target health.
11. [Target health checks for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — health status và reason.
12. [Gateway response types for API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/supported-gateway-response-types.html) — response type và default status.
13. [Variables for access logging for API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-variables-for-access-logging.html) — request, integration, authorizer và WAF context.
14. [Configure logging for HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging.html) — HTTP API access logs.
15. [Set up stages for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-stages.html) — execution/access logging và X-Ray.
16. [API Gateway metrics and dimensions](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-metrics-and-dimensions.html) — 4XXError, 5XXError, Latency và IntegrationLatency.
17. [Lambda proxy integrations in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html) — response format và 502 behavior.
18. [Troubleshoot API Gateway HTTP 504 timeout errors](https://repost.aws/knowledge-center/api-gateway-504-errors) — access logs, integration latency và timeout.
19. [Troubleshoot REST API Gateway 5xx errors](https://repost.aws/knowledge-center/api-gateway-5xx-error) — 502/503/504.
20. [Increase the API Gateway integration timeout limit](https://repost.aws/knowledge-center/api-gateway-timeout-limit) — quota và redeploy.
21. [Private integrations for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/private-integration.html) — VPC Link V2 và ALB/NLB targets.
22. [Private integrations for HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html) — ALB, NLB và AWS Cloud Map.

---

**Kết luận:** Chẩn đoán 4xx/5xx cần xác định đúng tầng tạo response. CloudFront logs cho biết edge/cache/origin result; ALB access logs và metrics phân biệt lỗi do load balancer với lỗi từ target; API Gateway access/execution logs cho biết gateway, authorizer và integration đã làm gì. Hãy nối các bằng chứng bằng request ID/correlation ID, kiểm tra timeout theo thứ tự của request path, xử lý nguyên nhân gốc và xác minh bằng regression test trước khi kết thúc incident.
