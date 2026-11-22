# AWS Shield và kiến trúc giảm thiểu DDoS

Một dịch vụ web có thể được thiết kế bảo mật tốt nhưng vẫn không sẵn sàng nếu kẻ tấn công làm cạn băng thông, trạng thái kết nối, năng lực xử lý HTTP hoặc tài nguyên phía sau. Distributed Denial of Service (DDoS) là kiểu tấn công phối hợp từ nhiều nguồn nhằm làm gián đoạn khả năng phục vụ người dùng hợp lệ. Một kiến trúc chống DDoS hiệu quả cần phối hợp khả năng hấp thụ lưu lượng ở biên mạng, phát hiện bất thường, lọc request tại lớp ứng dụng, bảo vệ origin, mở rộng có kiểm soát và quy trình phản ứng sự cố.

AWS Shield là dịch vụ managed DDoS protection. **Shield Standard** được bật tự động cho khách hàng AWS và không tính phí riêng; **Shield Advanced** là gói trả phí bổ sung khả năng giám sát, phát hiện, mitigation, tích hợp AWS WAF, Shield Response Team và một số quyền lợi bảo vệ chi phí. Shield là một lớp trong kiến trúc. Route 53, CloudFront, Global Accelerator, AWS WAF, load balancer, VPC origins, security groups, auto scaling và observability quyết định ứng dụng có giữ được availability trong thực tế hay không.

Bài thuộc chương **Bảo vệ mạng và ứng dụng**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung hướng tới khả năng chọn kiến trúc phù hợp cho website, API và ứng dụng TCP/UDP; cấu hình bảo vệ đúng resource; phân biệt lớp bảo vệ L3/L4/L7; xây dựng health checks, alert và runbook; kiểm soát chi phí và kiểm tra khả năng phục hồi.

> **Nguyên tắc:** Không có một nút bật Shield nào bảo vệ mọi resource trong account. Shield Advanced chỉ giám sát/bảo vệ resource được chỉ định hoặc được áp dụng qua AWS Firewall Manager policy. Cần đưa traffic qua đúng điểm entry, bảo vệ origin để không bị bypass, và kiểm thử rule để tránh chặn nhầm người dùng hợp lệ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích DDoS và phân biệt volumetric, protocol và application-layer attacks.
2. Nhận diện các kiểu tấn công L3, L4 và L7 thường gặp.
3. So sánh AWS Shield Standard và Shield Advanced.
4. Xác định resource types Shield Advanced hỗ trợ và phạm vi bảo vệ.
5. Giải thích vai trò của Route 53, CloudFront, Global Accelerator, AWS WAF và Elastic Load Balancing.
6. Thiết kế kiến trúc DDoS-resilient cho web application, API và TCP/UDP workloads.
7. Bảo vệ origin khỏi truy cập trực tiếp khi CloudFront là public entry point.
8. Sử dụng AWS WAF rate-based rules và Anti-DDoS Managed Rule Group.
9. Hiểu sự thay đổi từ Layer 7 Auto Mitigation sang Anti-DDoS Managed Rule Group trong năm 2026.
10. Cấu hình Route 53 health checks để hỗ trợ Shield Advanced health-based detection.
11. Mô tả vai trò, điều kiện và cách liên hệ Shield Response Team (SRT).
12. Theo dõi DDoS events bằng Shield metrics, CloudWatch, WAF logs và EventBridge.
13. Xây dựng runbook phát hiện, containment, mitigation và recovery.
14. Đánh giá chi phí, DDoS cost protection và giới hạn dịch vụ.
15. Thực hành bảo vệ tài nguyên trong AWS sandbox và kiểm tra false positives.

## 2. DDoS là gì và ảnh hưởng đến ứng dụng

DDoS là tấn công từ nhiều nguồn phân tán. Nguồn tấn công có thể là botnet, máy chủ bị chiếm quyền, proxy hoặc hệ thống tạo traffic tự động. Mục tiêu là khiến một resource hoặc một thành phần phụ thuộc không thể phục vụ request hợp lệ.

Một cuộc DDoS có thể gây:

- Cạn băng thông mạng hoặc năng lực xử lý packet.
- Cạn connection table, socket, thread hoặc worker.
- Tăng CPU, memory, database connections và queue depth.
- Làm tăng latency, HTTP 5xx, timeout và error rate.
- Tạo chi phí bất thường do data transfer, request processing hoặc autoscaling.
- Ảnh hưởng dịch vụ phụ thuộc như DNS, authentication, payment, API và database.

DDoS không nhất thiết làm máy chủ ngừng hoạt động hoàn toàn. Chỉ cần response time tăng vượt SLO hoặc request quan trọng bị timeout, trải nghiệm người dùng và doanh thu đã bị ảnh hưởng.

### 2.1. Ba nhóm tấn công theo lớp OSI

| Nhóm | Lớp | Mục tiêu | Ví dụ |
|---|---|---|---|
| Volumetric/network | L3 | Bão hòa băng thông hoặc năng lực xử lý packet | UDP flood, ICMP flood, reflection/amplification |
| Protocol/transport | L4 | Làm cạn trạng thái kết nối hoặc khai thác protocol | TCP SYN flood, connection flood |
| Application | L7 | Làm cạn năng lực xử lý HTTP/API hoặc backend | HTTP request flood, login/search/API abuse |

### 2.2. Volumetric và reflection/amplification

Kẻ tấn công tạo lượng packet lớn hoặc lợi dụng máy chủ bên thứ ba để khuếch đại traffic về phía nạn nhân. Với reflection/amplification, attacker giả mạo source IP của nạn nhân trong request nhỏ; dịch vụ phản hồi tạo response lớn hơn gửi về nạn nhân. Nạn nhân phải tiếp nhận lượng traffic lớn dù không trực tiếp giao tiếp với attacker.

Phòng vệ cần capacity hấp thụ traffic lớn và lọc ở upstream/edge. Chỉ tăng instance size hoặc Auto Scaling trong VPC thường không giải quyết được bão hòa băng thông trước khi traffic tới origin.

### 2.3. Protocol attacks

TCP SYN flood gửi nhiều SYN và tạo nhiều kết nối chưa hoàn tất handshake, làm cạn trạng thái kết nối ở endpoint hoặc thiết bị trung gian. Connection flood khác ở chỗ nhiều kết nối có thể hoàn tất handshake nhưng giữ tài nguyên lâu. Một số vector khai thác đặc tính protocol, packet fragmentation hoặc state tracking.

Các lớp edge như CloudFront, Route 53 và Global Accelerator có cơ chế mitigation tích hợp; AWS Shield cung cấp phát hiện/mitigation theo resource và lớp mạng được hỗ trợ. Security group và NACL kiểm soát traffic nhưng không thay thế hệ thống DDoS mitigation upstream.

### 2.4. Application-layer attacks

HTTP request flood có thể gửi request hợp lệ về cú pháp nhưng gây chi phí xử lý cao, ví dụ tìm kiếm, đăng nhập, tạo báo cáo, truy vấn database hoặc API không cache được. Attack traffic có thể phân tán qua nhiều IP, dùng user-agent và request pattern giống người dùng thật.

Chỉ giới hạn request theo IP có thể không đủ nếu attacker dùng botnet hoặc NAT/shared IP. Cần kết hợp rate-based rules, managed rule groups, token/challenge, authentication, caching, quota theo user/API key, backend concurrency limit và capacity planning. Cần bảo vệ endpoint tốn kém nhất trước khi request đi tới database.

## 3. AWS Shield Standard và Shield Advanced

### 3.1. Shield Standard

Shield Standard được bật tự động cho mọi AWS customer và không tính thêm phí riêng. Nó bảo vệ trước các DDoS attacks phổ biến ở network và transport layers (L3/L4), gồm SYN/UDP floods, reflection attacks và các vector thường gặp.

Các dịch vụ như Route 53, CloudFront và Global Accelerator có lợi thế từ hệ thống edge/network mitigation phân tán của AWS. Khi ứng dụng đặt entry point tại edge, traffic có thể được hấp thụ/lọc gần nguồn hơn trước khi tới Region.

Shield Standard không yêu cầu subscription hoặc thao tác enable riêng. Tuy vậy, Standard không tự cấu hình AWS WAF rules, application-specific rate limits, origin restrictions, health checks hay runbook cho ứng dụng.

### 3.2. Shield Advanced

Shield Advanced là subscription trả phí dành cho ứng dụng internet-facing cần khả năng bảo vệ, giám sát và phản ứng nâng cao. Các capability chính gồm:

- Always-on flow-based monitoring và phát hiện DDoS event cho protected resources.
- Advanced visibility, metrics và reports về attack/event.
- Mitigation nâng cao cho L3/L4 và hỗ trợ L7 thông qua AWS WAF.
- Tích hợp AWS WAF Web ACL, rules và managed rule groups.
- Health-based detection bằng Route 53 health checks.
- Protection groups để phân nhóm resource và đánh giá event ở cấp nhóm.
- Shield Response Team (SRT) hỗ trợ điều tra/mitigation khi đủ điều kiện support.
- Proactive engagement khi health check gắn với protected resource chuyển unhealthy trong một detected event.
- DDoS cost protection dưới dạng service credits theo điều kiện của chương trình.

Shield Advanced không tự động bảo vệ mọi resource trong account. Phải thêm resource vào Shield Advanced hoặc áp dụng policy phù hợp qua AWS Firewall Manager. Khi kiến trúc có CloudFront phía trước ELB và ELB chỉ nhận traffic từ CloudFront, AWS khuyến nghị chỉ cần enable Shield Advanced protection cho CloudFront thay vì tính phí bảo vệ cả hai resource.

### 3.3. So sánh nhanh

| Khả năng | Shield Standard | Shield Advanced |
|---|---|---|
| Tự động có sẵn | Có | Cần subscription |
| Phí Shield riêng | Không | Có, kèm usage charges |
| L3/L4 common DDoS | Có | Có, nâng cao hơn |
| Advanced event visibility | Cơ bản qua dịch vụ tích hợp | Có |
| Health-based detection | Không | Có |
| Protection groups | Không | Có |
| AWS WAF integration | Dùng WAF riêng theo pricing | Có các quyền lợi WAF nhất định cho protected resources |
| Anti-DDoS Managed Rule Group | Có thể dùng qua AWS WAF theo pricing tương ứng | Có quyền truy cập theo subscription/giới hạn request |
| SRT support | Không | Có, nếu có Business hoặc Enterprise Support |
| Proactive SRT engagement | Không | Có, cần health check và setup |
| DDoS cost protection | Không | Có, subject to terms/eligibility |

### 3.4. Resource types được Shield Advanced hỗ trợ

Shield Advanced hỗ trợ bảo vệ nâng cao cho các loại resource sau:

- Amazon CloudFront distributions.
- Amazon Route 53 hosted zones.
- AWS Global Accelerator standard accelerators.
- Amazon EC2 Elastic IP addresses; EC2 instances được bảo vệ thông qua EIP association.
- Application Load Balancers.
- Classic Load Balancers.
- Network Load Balancers thông qua association với EC2 Elastic IP addresses.

Không thể thêm trực tiếp mọi AWS resource vào Shield Advanced. Ví dụ, Gateway Load Balancer và Global Accelerator custom routing accelerator không nằm trong danh sách resource được bảo vệ. NAT Gateway xử lý outbound traffic; Shield Advanced tập trung bảo vệ DDoS inbound.

Tài liệu Shield Advanced hiện hành nêu hỗ trợ IPv4 và không hỗ trợ IPv6 cho resource protections. Khi thiết kế dual-stack, cần kiểm tra phạm vi protection của từng dịch vụ và không giả định Shield Advanced cover IPv6. Giới hạn số lượng protected resources theo resource type/account cũng cần kiểm tra trong Service Quotas.
Mặc định có thể protect tối đa 1.000 resources cho mỗi resource type trong một AWS account; nếu vượt mức, gửi yêu cầu quota increase qua Service Quotas.



## 4. Vai trò của các dịch vụ trong kiến trúc chống DDoS

Không có dịch vụ nào giải quyết mọi lớp tấn công. Kiến trúc nên đặt đúng chức năng tại từng điểm:

| Dịch vụ | Vai trò trong DDoS resiliency | Lớp/tác động chính |
|---|---|---|
| Amazon Route 53 | DNS authoritative, health checks, routing/failover | DNS/application availability |
| Amazon CloudFront | Global edge entry, cache, absorb traffic, TLS termination | L3/L4 edge + L7 cache/origin shielding |
| AWS Global Accelerator | Anycast static IPs, global edge entry, route traffic tới healthy endpoints | L3/L4/global routing |
| AWS Shield Standard | Automatic common DDoS mitigation | L3/L4 |
| AWS Shield Advanced | Enhanced detection/mitigation, visibility, SRT and cost protection | L3/L4/L7 integration |
| AWS WAF | Inspect HTTP(S), managed rules, rate-based rules, labels, challenge/block | L7 |
| Elastic Load Balancing | Distribute traffic across targets/AZs, health-based routing | Availability/capacity |
| Auto Scaling / ECS / EKS scaling | Add capacity within configured limits | Backend resilience |
| AWS Network Firewall / Security Groups / NACLs | Restrict allowed network paths and protocols | Network access control |
| CloudWatch / CloudTrail / EventBridge | Metrics, audit, alerts and automation | Detection/response |

### 4.1. Route 53

Route 53 phục vụ authoritative DNS và có thể dùng health checks để hỗ trợ routing/failover. DNS query floods được giảm thiểu nhờ hệ thống DNS phân tán và cơ chế của AWS. Health check nên phản ánh trạng thái ứng dụng thực tế, ví dụ endpoint health, response code, latency hoặc composite check từ CloudWatch alarms.

Không nên tạo health check chỉ kiểm tra TCP port mở nếu ứng dụng vẫn lỗi ở tầng nghiệp vụ. Shield Advanced health-based detection sử dụng trạng thái health check để điều chỉnh độ nhạy phát hiện; health check phải liên quan tới resource được bảo vệ.

### 4.2. CloudFront

CloudFront phân phối nội dung từ edge locations, cache object và giữ kết nối tới origin. Cache hit giúp request không đi vào VPC/database, giảm tải origin khi traffic tăng. TLS termination tại edge, kết hợp Shield mitigation, giúp lọc một số vector trước khi tới origin.

Đối với dynamic content, thiết kế cache policy hợp lý: cache static assets lâu, cache API responses khi an toàn, và tránh cache response chứa dữ liệu riêng tư. Cache không thay authorization; không cache dữ liệu theo user nếu cache key không bao gồm các yếu tố cần thiết.

### 4.3. Global Accelerator

Global Accelerator cung cấp static anycast IP và đưa traffic qua AWS global network tới endpoint phù hợp. Nó hữu ích cho TCP/UDP hoặc ứng dụng cần static IP, failover nhanh và định tuyến tới healthy regional endpoints. Với web content, CloudFront thường là lựa chọn edge/cache phù hợp hơn; Global Accelerator bổ sung giá trị cho non-HTTP hoặc yêu cầu network routing.

### 4.4. AWS WAF

AWS WAF là lớp kiểm soát request L7. Web ACL có thể chứa:

- Managed rule groups để phát hiện common exploits, bots và DDoS request patterns.
- Rate-based rules để giới hạn request rate theo IP hoặc aggregation keys.
- IP sets, geo match, header/path/method filters.
- Label matching để xử lý request đã được rule trước gắn nhãn.
- CAPTCHA/Challenge actions cho client/browser phù hợp.
- Logging và sampled requests để phân tích false positives.

WAF không hấp thụ volumetric attack ở upstream như edge DDoS mitigation. WAF xử lý HTTP(S) request sau khi traffic đã tới điểm được associate với Web ACL. Đặt CloudFront hoặc ALB/API Gateway đúng vị trí và bảo vệ origin để tránh attacker bỏ qua WAF.

## 5. Kiến trúc tham chiếu cho web application

Một kiến trúc web resilient phổ biến đặt Route 53 và CloudFront ở edge, AWS WAF kiểm tra request, sau đó CloudFront forward tới origin trong private VPC. Shield Standard cung cấp bảo vệ tự động; Shield Advanced bảo vệ resource được đăng ký rõ ràng và tăng visibility/response.

~~~mermaid
flowchart LR
    U["Users / Internet"] --> DNS["Route 53<br/>DNS + health checks"]
    DNS --> CF["CloudFront<br/>Edge cache + TLS"]
    CF --> WAF["AWS WAF Web ACL<br/>Associated with CloudFront"]
    WAF --> ORIGIN["CloudFront VPC origin"]
    ORIGIN --> ALB["Private ALB"]
    ALB --> APP["ECS / EKS / EC2 targets"]
    APP --> DB["RDS / ElastiCache"]
    SHIELD["Shield Standard / Advanced"] -.-> DNS
    SHIELD -.-> CF
    SHIELD -.-> ALB
    CW["CloudWatch / WAF logs / EventBridge"] -.-> SHIELD
~~~

Các nguyên tắc:

1. **Một entry point công khai:** hướng người dùng qua Route 53 và CloudFront thay vì public nhiều origin.
2. **Cache trước origin:** static content và response có thể cache được nên được phục vụ từ edge.
3. **Web ACL ở đúng resource:** associate Web ACL với CloudFront distribution để kiểm tra request trước khi tới origin.
4. **Origin không public nếu không cần:** CloudFront VPC origins cho phép CloudFront truy cập ALB/NLB/EC2 trong private subnet.
5. **Origin access cho S3:** dùng Origin Access Control (OAC) để chỉ CloudFront distribution được phép đọc private S3 origin.
6. **Scale backend có giới hạn:** Auto Scaling/ECS/EKS capacity limits và database connection limits cần thiết kế theo budget và load test.
7. **Health check và failover:** kiểm tra application health, không chỉ instance status.
8. **Observe từ edge đến database:** theo dõi CloudFront, WAF, ALB, application, queue và database metrics.

### 5.1. Bảo vệ origin khỏi direct access

Nếu attacker biết ALB DNS name hoặc public EC2 address, họ có thể gửi request trực tiếp tới origin và bypass CloudFront/WAF. Các giải pháp:

- Ưu tiên CloudFront VPC origins để giữ ALB/NLB/EC2 origin trong private subnets và giới hạn origin access tới CloudFront.
- Với S3 origin, dùng OAC và bucket policy chỉ cho phép đúng distribution.
- Nếu chưa dùng VPC origins, giới hạn ALB security group theo CloudFront origin-facing managed prefix list hoặc cơ chế xác thực origin phù hợp; kiểm tra cả IPv4/IPv6 và health check paths.
- Có thể dùng custom origin header làm một lớp xác minh bổ sung, nhưng header bí mật không thay thế network restriction và cần rotate.
- Không để origin DNS/endpoint trở thành public bypass path.

CloudFront VPC origins là giải pháp AWS khuyến nghị cho origin trong VPC; hỗ trợ ALB, NLB và EC2 trong private subnets, không cần internet access ở origin. Với S3, OAC vẫn là managed solution được khuyến nghị.

### 5.2. Web ACL và rate-based rules

Rate-based rule đếm request trong khoảng thời gian do AWS WAF hỗ trợ và áp dụng action khi rate vượt ngưỡng. Có thể aggregate theo source IP, forwarded IP hoặc custom keys được hỗ trợ. Dùng scope-down statement để chỉ áp dụng cho path nhạy cảm, ví dụ `/login`, `/search` hoặc `/api/report`.

Ví dụ chính sách ở mức thiết kế:

| Endpoint | Kiểm soát gợi ý | Lý do |
|---|---|---|
| `/login` | Rate limit theo IP + account-level throttle trong ứng dụng | Giảm brute force và login flood |
| `/search` | Rate limit + cache + query complexity limit | Tránh query tốn DB |
| `/api/report` | Authentication + quota theo tenant + queue | Không để request đắt làm cạn worker |
| Static assets | CloudFront cache + WAF baseline | Giảm request về origin |
| Admin endpoint | Authentication mạnh, allowlist khi phù hợp, rate limit | Giảm attack surface |

Rate-based rule là lớp mitigation gần thời gian thực và ngưỡng được đánh giá theo cơ chế của WAF; không nên coi nó là quota chính xác tuyệt đối cho billing hoặc business rate limiting. Với quota theo user/tenant/API key, ứng dụng/API Gateway cần enforce riêng.

### 5.3. Tránh cache poisoning và false positives

- Chỉ cache response phù hợp; kiểm tra query strings, cookies, headers trong cache key.
- Không cache response có PII/private data nếu không có cache isolation đúng.
- Dùng WAF Count mode để quan sát rule mới trước khi Block.
- Xem sampled requests và WAF logs trước khi tăng độ nhạy.
- Có exception hẹp theo URI/headers/client behavior đã xác minh.
- Theo dõi tỷ lệ legitimate traffic bị Challenge/CAPTCHA và conversion/error rate.

## 6. Kiến trúc cho API, TCP và UDP workloads

### 6.1. API workloads

Với API Gateway, AppSync hoặc public ALB, kết hợp WAF Web ACL, authentication, per-client quotas, caching, backend concurrency limits và queue. Shield Advanced chỉ bảo vệ các resource types được hỗ trợ; không giả định mọi API endpoint/service có thể được add trực tiếp vào Shield Advanced. AWS WAF có thể bảo vệ nhiều loại resource hơn Shield Advanced.

Một pattern API:

~~~mermaid
flowchart TD
    CLIENT["Mobile / Web / Partner"] --> EDGE["Route 53 / CloudFront"]
    EDGE --> WAF["AWS WAF Web ACL"]
    WAF --> API["API Gateway / ALB"]
    API --> AUTH["JWT / Cognito / IAM auth"]
    AUTH --> LIMIT["Tenant quota + concurrency limit"]
    LIMIT --> QUEUE["SQS / EventBridge"]
    QUEUE --> WORKER["Lambda / ECS workers"]
    WORKER --> DATA["DynamoDB / RDS"]
    OBS["CloudWatch / WAF logs"] -.-> WAF
    SH["Shield"] -.-> EDGE
~~~

Với API tốn kém, trả nhanh bằng `429 Too Many Requests` khi vượt quota, queue công việc dài, và áp dụng idempotency để retry không tạo side effects lặp. Đừng để request flood chuyển thẳng thành database connection flood.

### 6.2. TCP/UDP workloads

Game servers, DNS, voice/video signaling hoặc custom protocols có thể cần Network Load Balancer, Elastic IP hoặc Global Accelerator. Dùng Shield protection cho đúng resource type được hỗ trợ và kiểm tra association path.

- Dùng Global Accelerator khi cần static anycast IP, health-based endpoint routing và global ingress.
- Dùng NLB cho high-performance TCP/UDP load balancing; Shield Advanced protection cho NLB phụ thuộc EIP association theo resource support.
- Dùng security groups/NACLs để giới hạn protocol/port và source ranges phù hợp.
- Thiết kế connection timeout, idle timeout, retry/backoff và per-client connection limits.
- Theo dõi packets/bytes, new connections, active flows, rejected connections và application health.

Với UDP, application protocol nên xác minh request hợp lệ và giới hạn response amplification. Không phản hồi payload lớn cho request nhỏ chưa được xác thực nếu protocol có thể bị lợi dụng làm reflector.

## 7. Layer 7 DDoS protection và Anti-DDoS Managed Rule Group

Tấn công HTTP request flood có thể tạo request nhìn hợp lệ nhưng gây áp lực lớn lên ứng dụng. AWS WAF xử lý lớp này bằng Web ACL, rate-based rules, managed rule groups và token/challenge. Shield Advanced cung cấp tích hợp và visibility nâng cao cho protected resources.

### 7.1. Thay đổi quan trọng trong năm 2026

Từ ngày **26/03/2026**, AWS WAF Anti-DDoS Managed Rule Group (Anti-DDoS AMR) trở thành giải pháp mặc định cho bảo vệ HTTP request flood và thay thế tính năng Layer 7 Auto Mitigation (L7AM) trong hướng dẫn triển khai mới.

- Shield Advanced customer hiện hữu có thể tiếp tục dùng L7AM legacy cho account cũ hoặc mới.
- Khách hàng Shield Advanced mới được khuyến nghị dùng Anti-DDoS Managed Rule Group.
- Nếu khách hàng mới cần truy cập L7AM legacy, cần liên hệ AWS Support.
- Anti-DDoS AMR có khả năng phát hiện/mitigate trong vài giây theo tài liệu AWS, trong khi L7AM legacy có thể cần vài phút tùy event.
- Không sao chép hướng dẫn L7AM cũ sang kiến trúc mới mà không kiểm tra ngày cập nhật và service availability.

### 7.2. Anti-DDoS Managed Rule Group hoạt động thế nào?

AWS managed rule group có tên `AWSManagedRulesAntiDDoSRuleSet`, do vendor `AWS` cung cấp và sử dụng 50 WCUs. Rule group phát hiện request tham gia hoặc có khả năng tham gia DDoS event, gắn labels và áp dụng soft/hard mitigations.

- **Soft mitigation:** gửi silent browser Challenge cho request có thể xử lý challenge interstitial. Điều này phù hợp với browser GET requests được đánh dấu challengeable.
- **Hard mitigation:** block request có mức nghi ngờ đủ cao.
- Có thể điều chỉnh sensitivity cho challenge và block theo mức low/medium/high suspicion.
- Rule group gắn labels để các rule tiếp theo trong Web ACL có thể áp dụng hành động tùy chỉnh.
- Rule group có thể gắn label cho cả traffic hợp lệ và traffic tấn công khi resource đang trong event; vì vậy cần hiểu label semantics trước khi tạo rule block bổ sung.

Các label thường gặp:

| Label | Ý nghĩa |
|---|---|
| `awswaf:managed:aws:anti-ddos:event-detected` | Resource đang có DDoS event theo baseline; label có thể xuất hiện trên mọi request tới resource trong thời gian event |
| `awswaf:managed:aws:anti-ddos:ddos-request` | Request đến từ nguồn bị nghi tham gia event |
| `...:low-suspicion-ddos-request` | Request có mức nghi ngờ thấp/probable |
| `...:medium-suspicion-ddos-request` | Request có mức nghi ngờ cao hơn |
| `...:high-suspicion-ddos-request` | Request có mức nghi ngờ rất cao |
| `...:challengeable-request` | URI/request có thể xử lý Challenge action theo điều kiện của rule group |

Không block tất cả request chỉ vì có label `event-detected`: label này có thể gắn cho legitimate traffic trong lúc resource đang bị tấn công. Dùng label thể hiện request nghi DDoS, confidence level, token status và challengeability theo thứ tự rule và mục tiêu của ứng dụng.

### 7.3. Triển khai Anti-DDoS AMR

Quy trình tổng quát:

1. Tạo hoặc chọn AWS WAF Web ACL v2 cho CloudFront hoặc resource được hỗ trợ.
2. Xác định resource cần bảo vệ và associate Web ACL.
3. Thêm AWS managed rule group `AWSManagedRulesAntiDDoSRuleSet` với vendor `AWS`.
4. Review sensitivity, challenge behavior, rule action overrides và thứ tự ưu tiên.
5. Xác minh các URI hỗ trợ Challenge; loại trừ URI không thể xử lý browser challenge như API machine-to-machine, webhook hoặc endpoint không tương thích.
6. Bật WAF logging và CloudWatch metrics; theo dõi labels, sampled requests và legitimate traffic.
7. Dùng Count/override behavior trong giai đoạn kiểm thử nếu cần đánh giá tác động; chỉ chuyển sang Block/Challenge khi đã xác minh.
8. Test load/attack simulation trong môi trường được phép và theo AWS testing policy.

Rule group có thể dùng Challenge cho request browser-compatible và Block cho request có mức nghi ngờ cao. API clients không thể thực hiện browser challenge có thể bị ảnh hưởng nếu scope không đúng. Dùng scope-down statement để giới hạn URI/traffic, và kiểm tra labels trước khi tạo custom label-match rules.

### 7.4. Shield Advanced L7 và WAF rate-based rules

Ngay cả khi dùng Anti-DDoS AMR, ứng dụng vẫn cần business-specific controls:

- Rate limit theo source IP cho các endpoint public không yêu cầu identity.
- Quota theo user, tenant, API key hoặc JWT subject trong application/API layer.
- Authentication trước khi chạy operation tốn kém.
- Cache và request coalescing cho read-heavy endpoints.
- Queue, concurrency cap và circuit breaker cho backend.
- Challenge/CAPTCHA cho flows có browser session phù hợp.
- Allowlist hẹp cho partner/webhook đã xác minh; không hardcode allowlist rộng.

Rate-based rules và managed rule groups là lớp phòng vệ; chúng không thay business quota, fraud controls hoặc authorization.

### 7.5. Chi phí và giới hạn WAF

AWS Shield Advanced subscription bao gồm quyền truy cập Layer 7 Anti-DDoS managed rule group và một allowance tối đa 50 tỷ WAF requests mỗi tháng theo payer ID. Request vượt allowance được tính phí theo pricing hiện hành. Phí managed rules và các tính năng WAF ngoài phạm vi được bao gồm vẫn có thể áp dụng.

Shield Advanced bao gồm một số chi phí AWS WAF tiêu chuẩn cho protected resources, gồm phí Web ACL, rule và request ở mức mặc định tối đa 1.500 WCUs/default body size trong allowance. Bot Control, Fraud Control, Web ACL vượt 1.500 WCUs và body inspection vượt default size có thể phát sinh thêm phí. Kiểm tra pricing trước khi bật các managed rule groups hoặc tính năng bổ sung.

## 8. Health-based detection, proactive engagement và Shield Response Team

### 8.1. Route 53 health checks cho Shield Advanced

Shield Advanced có thể dùng Route 53 health checks để hiểu tình trạng ứng dụng và cải thiện độ nhạy phát hiện. Health check có thể liên kết với protected resource, ngoại trừ Route 53 hosted zone. Khi ứng dụng unhealthy, Shield Advanced có thể phát hiện event nhanh hơn và ở ngưỡng thấp hơn; khi healthy, cần nhiều bằng chứng hơn trước khi báo event.

Health check tốt cần:

- Chỉ báo healthy khi ứng dụng hoạt động trong ngưỡng SLO đã định.
- Chỉ báo unhealthy khi người dùng thực sự bị ảnh hưởng.
- Kiểm tra endpoint/response/latency liên quan tới resource.
- Có thể kết hợp CloudWatch metrics, application health và dependency checks.
- Không tạo false unhealthy vì lỗi một dependency không quan trọng.
- Vẫn được duy trì trong suốt thời gian protected resource cần health-based detection.

Shield Advanced không tự quản lý health check. Health check phải đang healthy khi associate; không xóa health check đang dùng bởi Shield Advanced. Health-based detection có thể tăng độ chính xác cho L3/L4 resources như NLB, EIP, Global Accelerator standard accelerator và L7 resources như CloudFront/ALB.

### 8.2. Proactive engagement

Proactive engagement cho phép SRT chủ động liên hệ khi Shield Advanced phát hiện event và Route 53 health check gắn với protected resource chuyển unhealthy. Cần cấu hình health check, contact details và quyền/ủy quyền phù hợp trước khi sự cố xảy ra.

Proactive engagement không có nghĩa AWS sẽ tự động liên hệ mọi khách hàng Shield Standard. Nó là một capability của Shield Advanced có điều kiện; cần giữ contact escalation chính xác và có người trực nhận cuộc gọi/email.

### 8.3. Shield Response Team (SRT)

SRT gồm các security engineers chuyên xử lý DDoS. Họ có thể:

- Phân tích AWS WAF logs để nhận diện attack patterns.
- Hỗ trợ tạo/chỉnh WAF rules với sự chấp thuận trong quá trình engagement.
- Xây dựng custom network mitigations cho infrastructure-layer attacks.
- Phối hợp network traffic engineering để tăng mitigation capacity hoặc điều chỉnh đường traffic.
- Đưa ra architectural recommendations khi cần thay đổi thiết kế.

Để sử dụng SRT, tài khoản cần Shield Advanced và AWS Business Support hoặc Enterprise Support. Không giả định gói Shield Advanced tự động bao gồm mọi mức AWS Support. Khi xảy ra sự cố, mở support case dưới AWS Shield với severity phù hợp support plan; cung cấp protected resource, triệu chứng, user impact, thời gian và thông tin traffic.

### 8.4. Protection groups

Shield Advanced protection groups cho phép nhóm các protected resources để đánh giá event và mitigation theo nhóm. Ví dụ nhóm CloudFront distributions, ALB và EIPs thuộc cùng một ứng dụng hoặc environment. Có thể dùng membership criteria để resource mới được tự động thêm vào group.

Protection group hỗ trợ quan sát và phân tích theo nhóm; nó không tự động biến resource chưa được protect thành resource đã được protect. Vẫn phải khai báo resource protection hoặc áp dụng Firewall Manager policy.

## 9. Bật Shield Advanced và quản lý protection

### 9.1. Chuẩn bị trước khi subscribe

Trước khi bật Shield Advanced, xác định:

- Business-critical applications, RTO/RPO và SLO availability.
- Public entry points: Route 53, CloudFront, Global Accelerator, ALB/NLB, EIPs.
- Account/Region ownership và resource ARNs.
- Web ACL hiện có, WAF capacity units (WCUs), managed rules và request volume.
- Route 53 health checks và escalation contacts.
- Người có quyền quản lý Shield, WAF, Firewall Manager và AWS Support.
- Budget, 1-year subscription commitment và usage-based data transfer out.

Shield Advanced là cam kết theo năm. Kiểm tra pricing, billing owner/payer ID và support plan trước khi subscribe. Subscription không tự động bảo vệ resource; sau khi subscribe vẫn phải thêm protected resources.

### 9.2. Thêm resource vào Shield Advanced

Quy trình Console tổng quát:

1. Mở AWS WAF & Shield Console.
2. Subscribe Shield Advanced và xác nhận điều khoản/billing commitment.
3. Mở **AWS Shield → Protected resources**.
4. Chọn **Add resources to protect**.
5. Chọn Region và resource type; resource global như CloudFront/Route 53 được chọn theo phạm vi tương ứng.
6. Load resources và chọn resource cần bảo vệ.
7. Với resource application layer, associate AWS WAF Web ACL.
8. Cấu hình Route 53 health check nếu dùng health-based detection/proactive engagement.
9. Kiểm tra protection status, metrics, notifications và contact information.
10. Ghi nhận owner, change ticket, resource ARN và ngày review.

Shield Advanced protection chỉ áp dụng cho resource được chọn hoặc được policy của Firewall Manager quản lý. Khi thay origin, distribution, EIP hoặc load balancer, kiểm tra lại protection coverage.

### 9.3. Quản lý nhiều accounts bằng AWS Firewall Manager

AWS Firewall Manager giúp quản lý tập trung Shield Advanced protections và AWS WAF policies trên AWS Organizations. Security administrator có thể tạo policy theo OU/account/resource scope, áp dụng cho resource hiện có và resource mới theo policy configuration.

Thiết kế governance nên:

- Chọn delegated administrator và security account rõ ràng.
- Phân loại account production, development và sandbox.
- Tạo policy cho resource types/Regions được hỗ trợ.
- Quy định Web ACL baseline, managed rule groups và exception process.
- Gửi policy compliance findings tới Security Hub/SNS hoặc workflow tương ứng.
- Theo dõi resource mới chưa được protect và drift sau thay đổi IaC.

Firewall Manager policy không thay thế review của ứng dụng owner. Một Web ACL baseline có thể cần scope-down/exception cho webhook, API clients hoặc endpoint đặc thù.

### 9.4. AWS Shield network security director (preview)

Tại thời điểm 20/11/2026, AWS Shield network security director được mô tả trong AWS FAQ là capability preview, hỗ trợ phân tích topology và cấu hình network security, tìm issue như overly permissive access và một số nguy cơ liên quan DDoS/web threats. Analysis cần được khởi chạy thủ công; preview hiện không hỗ trợ continuous analysis/automated monitoring. Đây là công cụ visibility/remediation về network security, không thay thế Shield Standard/Advanced DDoS protection hoặc AWS WAF.

## 10. Monitoring, metrics và audit

DDoS response cần quan sát đồng thời edge, network, load balancer, application và backend. Chỉ nhìn CPU của EC2 có thể bỏ lỡ attack đang bị edge mitigation hoặc làm cạn database connection.

### 10.1. Metrics nên theo dõi

| Layer | Metrics / signals | Ý nghĩa |
|---|---|---|
| Shield Advanced | DDoS detected, attack bits/packets/requests per second, event status | Xác định resource và loại event |
| CloudFront | Requests, bytes downloaded, 4xx/5xx, origin latency, cache hit ratio | Phân biệt traffic spike, origin failure và cache behavior |
| AWS WAF | Allowed/Blocked/Counted/Challenge requests, rule labels, sampled requests | Tìm request pattern và false positives |
| Route 53 | Health check status, DNS query patterns, failover events | Biết user-facing health và DNS behavior |
| ALB/NLB | RequestCount, target response time, target 5xx, active/rejected connections | Theo dõi ingress và target saturation |
| Application | Request rate, latency percentiles, queue depth, worker concurrency, auth failures | Phân biệt legitimate flash crowd và abusive traffic |
| Database/cache | Connections, CPU, latency, throttles, cache hit/miss | Xác định backend bottleneck |
| Billing | Data transfer out, WAF requests, autoscaling and service usage | Phát hiện cost anomaly |

Tên metric cụ thể thay đổi theo resource type. Dùng Shield console, CloudWatch metrics và service-specific dashboards để chọn đúng namespace/dimensions.

### 10.2. Alert và event routing

Tạo CloudWatch alarms cho:

- Shield DDoS event được phát hiện trên protected resource.
- Route 53 health check chuyển unhealthy.
- WAF Blocked/Challenge/Counted requests tăng đột biến.
- CloudFront/ALB 5xx và origin latency tăng.
- Application error rate, queue age hoặc database connections vượt SLO.
- Data transfer out hoặc usage cost tăng ngoài dự kiến.

Route alarm tới SNS/on-call system hoặc EventBridge incident workflow. Alert nên kèm resource ARN, Region, event time, dashboard link, runbook và người chịu trách nhiệm. Không tạo một alarm chỉ dựa vào request count nếu không có baseline và health context.

### 10.3. WAF logging và phân tích request

WAF logs có thể giúp xác định:

- URI, HTTP method, headers và request characteristics.
- Rule nào match, action Allow/Block/Count/Challenge.
- Labels do managed rule groups gắn.
- Source IP và forwarded IP khi được cấu hình đúng.
- Request pattern theo thời gian và resource.

Bảo vệ WAF logs như security data: giới hạn access, retention, redact/avoid logging sensitive headers/cookies và tránh lưu credentials/token. Không ghi log toàn bộ request body nếu không cần thiết.

### 10.4. CloudTrail và audit thay đổi protection

Dùng CloudTrail để truy vết ai đã:

- Tạo, xóa hoặc cập nhật Shield protection.
- Thay đổi AWS WAF Web ACL/rule/association.
- Thay đổi Route 53 health checks hoặc DNS records.
- Cập nhật CloudFront distribution/origin.
- Thay đổi security groups, NACLs, ALB/NLB và Firewall Manager policies.
- Thay đổi contact/permission cho SRT hoặc security automation.

Dùng CloudTrail trail multi-Region/organization trail và central S3 archive theo yêu cầu audit. Gắn protection changes với change ticket/IaC deployment để phân biệt thay đổi được duyệt và thay đổi bất thường.

## 11. Chi phí và DDoS cost protection

### 11.1. Shield Standard

Shield Standard được bật tự động và không tính phí Shield riêng. Các dịch vụ đi kèm như CloudFront, Route 53, WAF, ELB hoặc data transfer vẫn có pricing riêng theo cách sử dụng.

### 11.2. Shield Advanced

Theo pricing AWS được kiểm tra ngày 20/11/2026:

- Subscription fee là **3.000 USD/tháng cho payer account** khi payer account hoặc ít nhất một linked account subscribe và payer sở hữu các linked accounts/resources theo điều kiện billing.
- Cần cam kết subscription **1 năm**; subscription tự gia hạn theo chu kỳ năm nếu không hủy đúng cửa sổ thông báo.
- Có usage-based fees cho data transfer out từ các protected resources như CloudFront, ELB, EC2 và Global Accelerator.
- Subscription bao gồm một số phí AWS WAF tiêu chuẩn cho protected resources: Web ACL, rules và request fees ở mức default 1.500 WCUs/default body size trong allowance.
- Allowance tối đa 50 tỷ AWS WAF requests mỗi payer ID mỗi calendar month; requests vượt mức tính phí theo pricing table. Requests được Shield Advanced xác định là DDoS không tính vào allowance này.
- Bot Control, Fraud Control, WAF Web ACL trên 1.500 WCUs, body inspection vượt default size và một số managed-rule fees vẫn có thể tính riêng.

Giá theo GB/Region/resource và các phí phụ thuộc traffic có thể thay đổi. Luôn dùng AWS Shield Pricing và AWS Pricing Calculator để estimate trước khi subscribe.

### 11.3. DDoS cost protection

Shield Advanced có cơ chế cost protection cho một số usage spikes do DDoS attack gây ra, ví dụ data transfer out fees của protected resources. Quyền lợi được cấp dưới dạng Shield Advanced service credits, không phải cam kết hoàn lại mọi chi phí phát sinh hoặc tự động bù toàn bộ hóa đơn.

DDoS cost protection phụ thuộc điều kiện eligibility, protected resource, 1-year subscription commitment, quy trình request credit và bằng chứng sự cố. Giữ CloudTrail, Shield event reports, CloudWatch metrics, WAF logs, billing data và incident timeline để hỗ trợ yêu cầu.

### 11.4. Kiểm soát chi phí và tránh overprovision

- Cache nhiều hơn ở CloudFront để giảm origin requests/data processing.
- Chọn đúng protected resources; nếu ALB chỉ nhận traffic từ CloudFront, xem xét protect CloudFront theo pricing guidance.
- Dùng WAF scope-down statements để giới hạn traffic được evaluate bởi managed rule groups khi phù hợp.
- Theo dõi WAF requests, WCUs, Bot/Fraud features và data transfer out.
- Dùng Auto Scaling có min/max, concurrency limits và budget alarms.
- Không scale database vô hạn để hấp thụ traffic không hợp lệ.
- Đánh giá cost protection trong risk model, nhưng không dùng nó làm lý do bỏ qua capacity/caching design.

## 12. Runbook phản ứng khi phát hiện DDoS

Runbook nên được viết và diễn tập trước sự cố. Khi phát hiện traffic bất thường, mục tiêu là giữ availability cho người dùng hợp lệ, xác định lớp bị tấn công, giảm blast radius và giữ bằng chứng phục vụ post-incident review.

### 12.1. Detect và xác nhận impact

1. Xác định protected resource, account, Region và thời điểm bắt đầu event.
2. Kiểm tra Shield Advanced event details/metrics nếu resource đã được protect.
3. So sánh CloudFront, WAF, ALB/NLB, application và database metrics với baseline.
4. Kiểm tra Route 53 health check và user-facing synthetic monitoring.
5. Phân biệt traffic spike hợp lệ (flash crowd, campaign, launch) với attack pattern.
6. Xác định endpoint, URI, source IP/ASN, user-agent, token status, request rate và backend cost.

Không chỉ dựa vào tổng request count. Một flash crowd hợp lệ có thể tăng request nhưng cache hit cao, còn attack có thể tập trung vào một URI tốn DB và gây latency dù tổng request thấp.

### 12.2. Contain và mitigate

Tùy lớp tấn công:

- **L3/L4:** dựa vào Shield/edge mitigation; kiểm tra resource protection, Global Accelerator/CloudFront/Route 53 path, security groups/NACLs và health.
- **L7 HTTP flood:** kiểm tra WAF labels/logs, Anti-DDoS AMR, rate-based rules, scope-down, Challenge/Block sensitivity và cache.
- **Origin overload:** tăng cache, giới hạn direct origin access, giảm concurrency, queue công việc, circuit breaker và tạm vô hiệu endpoint tốn kém theo incident plan.
- **Backend bottleneck:** kiểm tra connection pool, database throttling, queue age và worker saturation; không tăng capacity vô hạn.
- **False positives:** chuyển rule sang Count hoặc giảm sensitivity có kiểm soát; tạo exception hẹp, không mở allowlist rộng.

Nếu dùng Shield Advanced, liên hệ SRT theo support plan khi event ảnh hưởng availability. Cung cấp resource ARN, event time, user impact, metrics, WAF logs và các mitigation đã thử.

### 12.3. Communicate và preserve evidence

- Kích hoạt incident commander và on-call owners.
- Cập nhật trạng thái dịch vụ, phạm vi ảnh hưởng, workaround và thời điểm cập nhật tiếp theo.
- Lưu Shield event report, WAF logs, CloudFront/ALB metrics, application logs, CloudTrail events và billing evidence.
- Ghi lại thay đổi rule/policy, ai phê duyệt, thời gian và kết quả.
- Không xóa logs hoặc tắt audit logging trong lúc xử lý.

### 12.4. Recover và learn

1. Giảm dần mitigation tạm thời sau khi traffic ổn định.
2. Kiểm tra legitimate users có thể hoàn thành các luồng quan trọng.
3. Xác minh origin/backend đã trở về baseline và không còn queue backlog.
4. Kiểm tra cache behavior, WAF false positives và health check.
5. Đánh giá data transfer, WAF usage, autoscaling và cost anomaly.
6. Viết post-incident review: timeline, root cause, control gaps, decision points và action owners.
7. Cập nhật runbook, architecture diagram, WAF rules, capacity plan và escalation contacts.

## 13. Bài thực hành trên AWS sandbox

Các bài lab dưới đây dùng tài nguyên sandbox do người học quản lý. Không tạo DDoS traffic tới public systems, third-party endpoints hoặc production resources. Nếu cần mô phỏng attack traffic, tuân thủ AWS DDoS simulation testing policy và chỉ dùng phương pháp/provider được AWS cho phép.

### 13.1. Lab A — Xây dựng web entry path

1. Tạo một CloudFront distribution trước ứng dụng test.
2. Tạo Route 53 hosted zone/record nếu có domain sandbox.
3. Associate AWS WAF Web ACL với CloudFront.
4. Đặt origin là S3 private bucket dùng OAC hoặc ALB trong VPC.
5. Nếu dùng ALB, thử CloudFront VPC origin để giữ origin trong private subnet.
6. Xác minh request đi qua CloudFront và origin không truy cập trực tiếp từ Internet.
7. Kiểm tra cache hit ratio và origin request count.

### 13.2. Lab B — AWS WAF rate-based rule

1. Tạo Web ACL sandbox và associate với CloudFront hoặc ALB test.
2. Tạo rate-based rule cho path test như `/login-test`.
3. Đặt action Count trước để quan sát.
4. Gửi traffic bình thường từ test client trong giới hạn cho phép.
5. Xem WAF metrics, sampled requests và logs.
6. Chuyển action sang Block/Challenge sau khi xác minh false positives.
7. Thử request tới path khác để xác nhận scope-down chỉ áp dụng đúng endpoint.

### 13.3. Lab C — Anti-DDoS Managed Rule Group

1. Xác nhận account/Region/resource có thể dùng AWS WAF managed rule group.
2. Thêm `AWSManagedRulesAntiDDoSRuleSet` vào Web ACL sandbox.
3. Đọc WCU usage và managed rule configuration.
4. Kiểm tra labels được ghi trong WAF logs/metrics.
5. Xác minh URI nào được challengeable; loại trừ webhook/API client không hỗ trợ browser challenge.
6. Quan sát Count/Challenge/Block actions và kiểm tra legitimate traffic.
7. Ghi lại request volume và pricing implications.

Không cố tạo attack flood để kích hoạt rule group. Dùng sample logs/test cases hoặc AWS-approved simulation theo policy.

### 13.4. Lab D — Shield Advanced protection và health check

1. Chỉ thực hiện nếu có sandbox account và subscription được phê duyệt; kiểm tra cam kết/chi phí trước.
2. Thêm CloudFront distribution hoặc ALB sandbox vào Shield Advanced protected resources.
3. Tạo Route 53 health check phản ánh application health.
4. Associate health check với protection và xác nhận health check đang healthy.
5. Xem Shield metrics/event visibility và cấu hình notifications.
6. Xem cách bật proactive engagement/contact details nếu đủ điều kiện.
7. Xóa protection sau lab theo quy trình subscription/resource policy; không hủy subscription ngoài cửa sổ điều khoản.

### 13.5. Lab E — Origin protection

1. Tạo private S3 bucket hoặc private ALB origin.
2. Nếu S3, dùng OAC và bucket policy chỉ cho phép CloudFront distribution.
3. Nếu VPC origin, đặt ALB/NLB/EC2 trong private subnet và cấu hình CloudFront VPC origin.
4. Thử truy cập origin trực tiếp từ Internet; request phải không thể đi qua public path.
5. Xác minh CloudFront vẫn phục vụ ứng dụng.
6. Kiểm tra security group, bucket policy và CloudFront origin configuration.

### 13.6. Lab F — Monitoring và incident drill

1. Tạo CloudWatch dashboard gồm CloudFront, WAF, ALB và application metrics.
2. Tạo alarm cho WAF blocked requests, origin 5xx và health check unhealthy.
3. Route alarm tới SNS/EventBridge test workflow.
4. Dùng traffic test hợp lệ để tạo baseline và quan sát metrics.
5. Chạy tabletop exercise: giả định HTTP flood vào endpoint search.
6. Thực hiện các bước detect, contain, communicate, recover theo runbook.
7. Ghi lại gap trong dashboard, alert, contact list và escalation process.

## 14. Checklist review DDoS resiliency trước production

### Architecture và entry points

- [ ] Đã inventory tất cả public entry points, origins, DNS records và EIPs?
- [ ] Route 53/CloudFront/Global Accelerator phù hợp protocol và traffic pattern?
- [ ] Static/dynamic content đã cache theo policy an toàn?
- [ ] Origin được bảo vệ khỏi direct access/bypass?
- [ ] CloudFront VPC origins hoặc S3 OAC được dùng khi phù hợp?
- [ ] Backend có Auto Scaling, concurrency limits, queue và circuit breakers?
- [ ] Có multi-AZ/failover và dependency health checks?

### Shield và WAF coverage

- [ ] Shield Standard đã được hiểu là tự động bật và chỉ bảo vệ common L3/L4?
- [ ] Shield Advanced có cần thiết theo business impact/risk/cost?
- [ ] Mọi resource cần Shield Advanced đã được explicitly protected hoặc áp dụng Firewall Manager policy?
- [ ] Resource type/IPv4 support/association path được kiểm tra?
- [ ] WAF Web ACL gắn đúng CloudFront/ALB/API resource?
- [ ] Anti-DDoS Managed Rule Group được cân nhắc theo trạng thái dịch vụ hiện hành?
- [ ] Rate-based rules có scope-down, threshold và false-positive review?
- [ ] API clients/webhooks không tương thích Challenge được xử lý riêng?

### Health, monitoring và response

- [ ] Route 53 health checks phản ánh application health và được duy trì?
- [ ] Proactive engagement/contact details được cấu hình nếu dùng?
- [ ] SRT eligibility và Business/Enterprise Support đã xác nhận?
- [ ] Có CloudWatch dashboard và alarm từ edge tới database?
- [ ] WAF logs/Shield events/CloudTrail được lưu và truy cập có kiểm soát?
- [ ] Có incident commander, on-call contacts và runbook?
- [ ] Đã diễn tập DDoS tabletop và recovery?

### Cost và governance

- [ ] Đã ước tính Shield Advanced 1-year subscription và DTO usage fees?
- [ ] Đã kiểm tra 50B WAF request allowance, WCU và non-standard WAF charges?
- [ ] DDoS cost protection eligibility/credit process được hiểu đúng?
- [ ] Firewall Manager policy cover account/resource lifecycle?
- [ ] Có owner, exception process và lịch review protection coverage?

## 15. Câu hỏi tự đánh giá

1. DDoS khác DoS ở điểm nào?
2. Volumetric, protocol và application-layer attacks khác nhau thế nào?
3. UDP reflection/amplification attack hoạt động ra sao?
4. TCP SYN flood làm cạn loại tài nguyên nào?
5. Vì sao HTTP request flood có thể gây thiệt hại dù request hợp lệ về cú pháp?
6. AWS Shield Standard có cần enable không và có phí Shield riêng không?
7. Shield Standard bảo vệ những lớp nào?
8. Shield Advanced bổ sung những capability nào?
9. Những resource types nào có thể được Shield Advanced protect?
10. Shield Advanced có tự động bảo vệ mọi resource trong account không?
11. Vì sao cần kiểm tra IPv4/IPv6 support?
12. Route 53 giúp tăng DDoS resiliency như thế nào?
13. CloudFront giảm tải origin bằng những cơ chế nào?
14. Global Accelerator phù hợp use case nào so với CloudFront?
15. AWS WAF hoạt động ở layer nào và Web ACL làm gì?
16. Vì sao WAF không thay thế upstream DDoS mitigation?
17. Vì sao phải bảo vệ origin khỏi direct access khi dùng CloudFront?
18. CloudFront VPC origins hỗ trợ origin types nào?
19. OAC dùng để bảo vệ loại origin nào?
20. Rate-based rule khác business quota theo user/tenant như thế nào?
21. Vì sao nên dùng Count trước khi Block?
22. Anti-DDoS Managed Rule Group trở thành default solution từ ngày nào?
23. Tên AWS managed rule group Anti-DDoS là gì và sử dụng bao nhiêu WCUs?
24. Soft mitigation và hard mitigation khác nhau thế nào?
25. Vì sao không block tất cả request có label `event-detected`?
26. Khi nào browser Challenge có thể gây false positives?
27. Health-based detection dùng Route 53 health check để làm gì?
28. Health check nào là điều kiện cho SRT proactive engagement?
29. SRT cần AWS Support plan nào?
30. SRT có thể hỗ trợ những hoạt động nào trong DDoS incident?
31. Protection groups có tự protect resource mới không?
32. AWS Firewall Manager hỗ trợ governance DDoS như thế nào?
33. Shield Advanced có cost protection dưới hình thức nào?
34. Shield Advanced pricing gồm những thành phần nào?
35. Cần theo dõi metrics nào từ CloudFront/WAF/ALB/backend?
36. Runbook DDoS cần những bước detect, contain, communicate và recover nào?

### Định hướng đáp án

- **Attack layers:** L3 bão hòa network; L4 khai thác protocol/connection state; L7 làm cạn application/backend bằng request flood.
- **Shield Standard:** tự động, không phí Shield riêng, tập trung common L3/L4.
- **Shield Advanced:** subscription trả phí, protected resources cụ thể, advanced visibility/mitigation, WAF integration, health-based detection, SRT và cost credits theo điều kiện.
- **Architecture:** Route 53/CloudFront/Global Accelerator làm entry/edge; WAF xử lý L7; origin private/restricted; cache, scale và queue giảm áp lực backend.
- **2026 L7:** Anti-DDoS Managed Rule Group là hướng triển khai mặc định từ 26/03/2026; legacy L7AM vẫn có cho customer hiện hữu.
- **Response:** health checks, metrics, WAF logs, CloudTrail, SRT và runbook giúp phản ứng có kiểm soát.
- **Cost:** 1-year commitment, monthly subscription, data transfer out usage, WAF request/WCU allowances và credit eligibility phải được đánh giá.

## 16. Tình huống thiết kế: bảo vệ website thương mại điện tử

Một website bán hàng có frontend static, API đăng nhập/tìm kiếm/đặt hàng và database RDS. Lưu lượng bình thường tập trung theo giờ; khi flash sale, request tăng đột biến. Hệ thống có nguy cơ bị HTTP flood vào endpoint search/login, đồng thời attacker có thể thử truy cập trực tiếp ALB origin.

### 16.1. Phân tích yêu cầu

- Frontend cần phân phối nhanh và chịu được traffic spike toàn cầu.
- API cần bảo vệ endpoint tốn database và giới hạn theo tenant/user.
- Order/payment cần giữ tính đúng đắn, idempotency và không bị queue flood.
- Origin phải không thể bypass CloudFront/WAF.
- Đội vận hành cần phát hiện nhanh, có SRT escalation và kiểm soát cost.

### 16.2. Kiến trúc đề xuất

1. Route 53 phục vụ DNS và health checks cho application.
2. CloudFront là public entry point; static assets được cache ở edge.
3. AWS WAF Web ACL associate với CloudFront, có baseline managed rules, Anti-DDoS AMR và rate-based rules theo endpoint.
4. CloudFront VPC origin kết nối tới ALB trong private subnet; security groups chỉ cho phép origin traffic hợp lệ.
5. ALB phân phối tới ECS/EKS targets qua nhiều Availability Zones.
6. API authentication và quota theo user/tenant chạy trước operation tốn kém.
7. Search dùng cache/query limits; order/payment dùng idempotency và queue khi xử lý bất đồng bộ.
8. RDS connection pool và worker concurrency có giới hạn; autoscaling có min/max.
9. Shield Standard tự động bảo vệ common L3/L4; nếu business impact yêu cầu, subscribe Shield Advanced và protect CloudFront distribution, Route 53 hosted zone hoặc resource đủ điều kiện.
10. Route 53 health check phản ánh application health; CloudWatch alarms/WAF logs/Shield events route tới on-call.

### 16.3. Quyết định và trade-offs

| Quyết định | Lý do | Trade-off cần quản lý |
|---|---|---|
| CloudFront làm public entry | Hấp thụ traffic ở edge, cache static assets, ẩn origin | Cache policy và invalidation cần chính xác |
| VPC origin cho ALB | Origin nằm private, giảm direct-origin bypass | Cần kiểm tra compatibility và network configuration |
| Anti-DDoS AMR + rate rules | Phát hiện HTTP flood và giới hạn endpoint | Challenge không phù hợp mọi API client; cần test false positives |
| Quota ở application/API | Giới hạn theo user/tenant, bảo vệ business operation | Cần identity và distributed rate-limit state |
| Queue + concurrency caps | Tách request burst khỏi worker/database | Queue backlog cần alarm và dead-letter handling |
| Shield Advanced | Advanced visibility, mitigation, SRT và cost credits | Subscription 1 năm, DTO usage và WAF cost cần budget |

### 16.4. Kịch bản sự cố

Giả sử trong flash sale, request search tăng gấp nhiều lần và ALB target response time tăng:

1. Kiểm tra CloudFront cache hit ratio; nếu thấp, xem cache key và response headers.
2. Kiểm tra WAF logs/Anti-DDoS labels để xác định request patterns và endpoint.
3. Xem Shield event details và Route 53 health check.
4. Tăng rate limit/scope-down cho search sau khi xác nhận legitimate traffic; không block toàn bộ label `event-detected`.
5. Bật cache/query limits hoặc tạm giảm chức năng search tốn kém theo incident plan.
6. Giữ order/payment path hoạt động; dùng queue và idempotency.
7. Liên hệ SRT nếu Shield Advanced event ảnh hưởng availability và support plan đủ điều kiện.
8. Sau sự cố, điều chỉnh cache policy, WAF sensitivity, capacity plan và alert thresholds.

Bài học: một kiến trúc tốt không cố xử lý mọi request bằng cách scale backend. Nó hấp thụ traffic ở edge, chỉ đưa request cần thiết tới origin, giới hạn chi phí xử lý và giữ luồng nghiệp vụ quan trọng hoạt động.

## 17. Tài liệu AWS chính thức

1. [How AWS Shield and Shield Advanced work](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-overview.html) — Khái niệm DDoS, Shield Standard/Advanced và attack classes.
2. [AWS Shield Standard overview](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-standard-summary.html) — Standard protection và edge services.
3. [AWS Shield Advanced capabilities and options](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-summary-capabilities.html) — Advanced features, WAF, health checks, protection groups, SRT và cost protection.
4. [Resources protected by Shield Advanced](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-summary-protected-resources.html) — Resource types và explicit protection requirement.
5. [Building DDoS resilient architectures](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-resiliency.html) — Architecture patterns cho web và TCP/UDP.
6. [Example Shield Advanced web architecture](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-resiliency-example-web.html) — Route 53, CloudFront, WAF, ELB và EC2.
7. [AWS Best Practices for DDoS Resiliency](https://docs.aws.amazon.com/whitepapers/latest/aws-best-practices-ddos-resiliency/welcome.html) — Các best practices toàn diện.
8. [Protecting your origin](https://docs.aws.amazon.com/whitepapers/latest/aws-best-practices-ddos-resiliency/protecting-your-origin-bp1-bp5.html) — CloudFront VPC origins và S3 OAC.
9. [AWS WAF Anti-DDoS Managed Rule Group](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-anti-ddos.html) — Rule group, labels, challenge và block.
10. [Automating application layer DDoS mitigation](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-automatic-app-layer-response.html) — Thay đổi L7AM và Anti-DDoS AMR từ 26/03/2026.
11. [Health-based detection with Shield Advanced](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-health-checks.html) — Route 53 health checks và detection sensitivity.
12. [Shield Response Team support](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-srt-support.html) — SRT capabilities và support-plan requirement.
13. [Setting up Shield Response Team support](https://docs.aws.amazon.com/waf/latest/developerguide/authorize-srt.html) — Quyền và proactive engagement.
14. [AWS Shield Advanced pricing](https://aws.amazon.com/shield/pricing/) — Subscription, data transfer out, WAF request allowance và pricing examples.
15. [AWS Shield FAQs](https://aws.amazon.com/shield/faqs/) — Shield capabilities, cost và network security director preview.
16. [AWS Firewall Manager](https://docs.aws.amazon.com/waf/latest/developerguide/fms-chapter.html) — Quản lý tập trung WAF và Shield policies.
17. [AWS WAF rate-based rules](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html) — Rate-based rules và aggregation.
18. [AWS WAF scope-down statements](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-scope-down-statements.html) — Giới hạn traffic được evaluate và cost.
19. [AWS Shield DDoS testing policy](https://aws.amazon.com/security/ddos-simulation-testing/) — Quy tắc kiểm thử DDoS simulation trên AWS.

> **Ghi nhớ cuối bài:** Shield Standard cung cấp bảo vệ L3/L4 tự động; Shield Advanced bổ sung detection, mitigation, visibility, WAF integration, SRT và cost protection theo điều kiện. Kiến trúc resilient đặt Route 53/CloudFront/Global Accelerator ở entry, AWS WAF tại L7, origin được bảo vệ khỏi bypass, backend có cache/queue/limits và đội vận hành có health checks, metrics, alert cùng runbook. Kiểm tra service changes, resource coverage và pricing trước khi triển khai production.
