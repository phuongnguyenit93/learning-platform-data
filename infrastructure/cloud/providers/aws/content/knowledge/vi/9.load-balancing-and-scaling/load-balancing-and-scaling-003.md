# Định tuyến theo host, path, header và trọng số

> **Chương:** Cân bằng tải và mở rộng  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá Region/AZ, IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn cách chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Khi một ứng dụng phát triển từ một máy chủ web thành nhiều dịch vụ như frontend, API, dashboard và worker, chỉ phân phối đều request tới các máy chủ là chưa đủ. Ta còn phải quyết định **request nào đến dịch vụ nào**, phiên bản nào nhận lưu lượng thử nghiệm, và xử lý ra sao khi triển khai hoặc khi một nhóm đích không còn khỏe mạnh.

**Application Load Balancer (ALB)** của AWS là bộ cân bằng tải **Layer 7** có khả năng xử lý HTTP/HTTPS, đánh giá **listener rules** dựa trên hostname, URL path, HTTP header và nhiều thuộc tính khác, rồi chuyển tiếp tới một hoặc nhiều **target groups**. Trong một hành động chuyển tiếp, **trọng số (weight)** cho phép chia dần lưu lượng giữa phiên bản ổn định và phiên bản mới.

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa **ALB, listener, listener rule, condition, action, target group và target**.
2. Thiết kế routing theo **host**, **path**, **HTTP header**, cũng như phối hợp các điều kiện trong một rule.
3. Hiểu **priority**, **default rule**, quan hệ **AND/OR** khi so khớp, và các giới hạn wildcard/regex theo khả năng dịch vụ.
4. Cấu hình **weighted target groups** để triển khai canary hoặc blue/green; phân biệt điều phối lưu lượng với **Auto Scaling**.
5. Chẩn đoán lỗi route sai, 404/403/5xx, target unhealthy, sai TLS/Host, header bị thay đổi hoặc trọng số không như mong đợi.
6. Sử dụng AWS CLI để **đọc cấu hình** và thử nghiệm rule trong sandbox, có bước kiểm chứng và dọn tài nguyên.
7. Đề xuất biện pháp bảo mật, giám sát, rollback, nhiều AZ và tối ưu chi phí.

## 1. Bức tranh tổng thể: từ DNS đến ứng dụng

Một tên miền như `api.example.com` có thể được cấu hình DNS trỏ tới ALB. ALB nhận kết nối vào **listener** (ví dụ HTTPS:443), đánh giá các rule và chuyển request tới target group tương ứng. Mỗi target group có thể chứa nhiều instance EC2, địa chỉ IP hoặc Lambda function tùy loại target và hỗ trợ của dịch vụ.

~~~mermaid
flowchart TD
    U[Client / Browser] --> DNS[DNS: api.example.com]
    DNS --> LB[Application Load Balancer]
    LB --> L[HTTPS listener :443]
    L --> R{Listener rules theo priority}
    R -->|Host api.example.com, Path /v1/*| TG1[Target group: api-v1]
    R -->|Host shop.example.com, Path /images/*| TG2[Target group: image-service]
    R -->|Header X-Release: beta| TG3[Target group: api-beta]
    R -->|Không khớp rule| DEF[Default action]
    TG1 --> A1[EC2 / ECS / IP targets]
    TG2 --> A2[EC2 / ECS / IP targets]
    TG3 --> A3[EC2 / ECS / IP targets]
~~~

**VPC/AZ và ALB:** ALB được gắn với các subnet trong những Availability Zone được bật. Workload phía sau có thể được vận hành bằng **EC2 Auto Scaling**, **Amazon ECS** hoặc hệ thống khác, với health checks để ALB quyết định target nào có thể nhận lưu lượng. Routing rule không tự tạo thêm EC2 hay tự bảo đảm phục hồi.

### 1.1. Thành phần và trách nhiệm

| Thành phần | Là gì? | Câu hỏi nó trả lời |
|---|---|---|
| **ALB** | Cân bằng tải Layer 7, nhận HTTP/HTTPS | Lưu lượng client được tiếp nhận ở đâu? |
| **Listener** | Port và protocol nhận kết nối, có default action | Cổng 80 hay 443? Có TLS certificate không? |
| **Listener rule** | Điều kiện, thứ tự ưu tiên, hành động | Request này khớp quy tắc nào? |
| **Condition** | Host/path/header/query/method/IP... | Có phải request cần định tuyến đặc biệt không? |
| **Action** | Forward, redirect, fixed response; có thể có auth tùy ngữ cảnh | Request được chuyển tiếp hay phản hồi thế nào? |
| **Target group** | Nhóm target và health check | Dịch vụ/phiên bản nào nhận request? |
| **Target** | EC2 instance, IP hoặc Lambda theo target type | Workload cụ thể nào xử lý request? |
| **Health check** | Kiểm tra trạng thái target | Target có đủ khỏe để nhận request không? |

Ví dụ cấu hình logic:

~~~text
Listener HTTPS :443
  priority 10 -> Host admin.example.com                -> tg-admin
  priority 20 -> Host api.example.com + Header beta    -> tg-api-beta
  priority 30 -> Host api.example.com + Path /v1/*     -> tg-api-v1
  priority 40 -> Host api.example.com + Path /v2/*     -> tg-api-v2
  default     -> fixed-response 404
~~~

**Số priority càng nhỏ được xét càng sớm.** Đã khớp một listener rule và thực thi action của rule đó thì ALB không tiếp tục tìm một rule ưu tiên thấp hơn để thử lại. Vì thế, thứ tự đặt rule là một phần của thiết kế ứng dụng.

### 1.2. Vì sao tập trung vào ALB?

AWS còn có **Network Load Balancer (NLB)** và **Gateway Load Balancer (GWLB)**, nhưng **routing theo host, URL path và HTTP header là khả năng trọng tâm của ALB**. NLB chủ yếu phục vụ các tình huống Layer 4 và có bộ rule/action khác; không áp hướng dẫn ALB ở bài này cho NLB một cách máy móc.

## 2. Cách ALB đánh giá listener rules

### 2.1. Thứ tự priority và default action

Một listener có **default rule** luôn tồn tại. Mỗi non-default rule có một **priority riêng** trong listener đó và được xét theo thứ tự tăng dần; default rule được xét cuối cùng, không có condition.

~~~mermaid
flowchart TD
    A[Request tới HTTPS listener :443] --> B{Priority 10 khớp?}
    B -->|Có| X[Thực thi action rule 10]
    B -->|Không| C{Priority 20 khớp?}
    C -->|Có| Y[Thực thi action rule 20]
    C -->|Không| D{Priority 30 khớp?}
    D -->|Có| Z[Thực thi action rule 30]
    D -->|Không| E[Default action]
~~~

Quy tắc an toàn:

- **Specific trước, general sau:** `Host=api.example.com` + `Header=X-Release:beta` nên nằm trước rule chỉ có `Host=api.example.com`.
- **Ưu tiên không phải trọng số:** priority 10/20 quyết định **thứ tự xét điều kiện**, còn weight 90/10 quyết định **phân phối request giữa các target groups** trong cùng forward action.
- **Default rule không có condition:** có thể cấu hình fixed-response 404 cho host/path không được khai báo, hoặc chuyển tới một target group mặc định theo chủ đích.
- Với những rule có điều kiện chồng lấn, **rule đầu tiên khớp** sẽ thắng. Không có cơ chế “cộng dồn” tác dụng định tuyến của nhiều rule đã khớp.

### 2.2. Phối hợp điều kiện AND và giá trị OR

ALB hỗ trợ các condition types phổ biến: `host-header`, `path-pattern`, `http-header`, `http-request-method`, `query-string` và `source-ip`.

- Nhiều **condition** khác loại trong cùng một rule được kết hợp theo logic **AND**: request phải đạt **tất cả các condition**.
- Với một condition chứa nhiều **values** để so khớp, một trong các value phù hợp là đủ (**OR**).
- Với nhiều điều kiện `http-header` hoặc `query-string` trong một rule, mỗi condition vẫn phải được đáp ứng.
- AWS có **quota** về số condition, match evaluation và wildcard mỗi rule. Kiểm tra quota hiện hành trước khi tạo các pattern phức tạp.

Ví dụ:

~~~text
Điều kiện A: host-header ∈ { api.example.com, service.example.com }
Điều kiện B: path-pattern ∈ { /v1/*, /legacy/* }
Điều kiện C: X-Channel ∈ { partner, internal }

Rule khớp khi:
    (host = api.example.com OR service.example.com)
AND (path bắt đầu theo /v1/* OR /legacy/*)
AND (header X-Channel = partner OR internal)
~~~

Cách viết này giúp giảm số rule lặp lại, nhưng không nên gom quá nhiều condition nếu người vận hành không còn nhìn ra được luồng request và quyền truy cập.

### 2.3. Hành động của listener rule

Một rule thường có hành động cuối là:

| Action | Hiệu quả | Tình huống |
|---|---|---|
| **forward** | Gửi request tới một hoặc nhiều target groups | Phân dịch vụ, canary/blue-green |
| **redirect** | Trả HTTP 301/302 với địa chỉ khác | Chuyển HTTP sang HTTPS, đổi tên miền |
| **fixed-response** | ALB tự trả status/body theo cấu hình | 404 khi không khớp, 403 cho đường bị cấm |
| **authenticate-cognito** / **authenticate-oidc** | Xác thực theo cơ chế ALB hỗ trợ trước hành động cuối | Ứng dụng cần đăng nhập tại tầng ingress |

Với listener hỗ trợ, một rule có thể có **authentication action** trước hành động `forward`; cuối cùng vẫn cần đúng hành động kết thúc theo quy tắc ALB. AWS còn hỗ trợ **host header rewrite và URL rewrite transforms** trên những listener rules phù hợp: đây là cơ chế riêng, không nên hiểu rằng mọi path routing mặc định sẽ tự xóa hoặc đổi phần path.

## 3. Host-based routing: một ALB, nhiều tên miền

### 3.1. Nguyên tắc so khớp Host

**Host-based routing** chọn target group dựa trên **HTTP Host header**, ví dụ:

~~~text
shop.example.com   -> tg-web-shop
api.example.com    -> tg-api
admin.example.com  -> tg-admin
~~~

Với HTTPS, client thực hiện TLS handshake, ALB chọn chứng chỉ thích hợp theo cấu hình TLS/SNI, sau đó xử lý HTTP request theo listener rules. **Host header dùng để route không đồng nghĩa với chứng chỉ TLS hoặc danh tính người dùng.** Client có thể gửi Host header tùy ý trong nhiều tình huống, nên không dùng điều kiện Host thay một cơ chế xác thực/phân quyền.

### 3.2. Ví dụ JSON condition

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": [
        "api.example.com",
        "service.example.com"
      ]
    }
  }
]
~~~

Với value matching, ALB hỗ trợ wildcard như `*` và `?` theo quy tắc tương ứng. Ví dụ `*.example.com` dùng để khớp các subdomain như `api.example.com`, **không nhất thiết khớp domain gốc** `example.com`. Hostname matching không phân biệt hoa/thường.

Một số quy tắc ALB hiện hành còn hỗ trợ **regular expression matching** cho host/path/header với cấu hình `RegexValues`. Regex mang thêm giới hạn cú pháp và quota; chỉ dùng khi value/pattern thông thường không đủ, và kiểm tra trên request thử nghiệm.

### 3.3. Lựa chọn thiết kế

Ví dụ hệ thống thương mại điện tử:

| Host | Target group | Dịch vụ |
|---|---|---|
| `shop.example.com` | `tg-web` | Frontend người mua |
| `api.example.com` | `tg-api` | Backend API |
| `seller.example.com` | `tg-seller` | Seller portal |
| `admin.example.com` | `tg-admin` | Quản trị nội bộ |

Dù cùng ALB, **admin portal vẫn cần kiểm soát danh tính và mạng**. Một quy tắc Host dành cho `admin.example.com` không ngăn người lạ tự tạo HTTP request với header đó. Có thể áp AWS WAF, ALB authentication, security controls của ứng dụng và thiết kế mạng nội bộ theo nhu cầu.

## 4. Path-based routing: tách dịch vụ bằng URL

### 4.1. Điều kiện path-pattern

Path-based routing xem **đường dẫn trong URL**, không bao gồm query string. Ví dụ:

~~~text
https://app.example.com/api/orders/123  -> tg-api
https://app.example.com/static/logo.svg -> tg-static
https://app.example.com/admin/users     -> tg-admin
https://app.example.com/                -> tg-web
~~~

Ví dụ condition:

~~~json
[
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": [
        "/api/*",
        "/v2/*"
      ]
    }
  }
]
~~~

Các pattern được so trên path của request sau bước normalization theo cơ chế ALB. **Path matching phân biệt hoa/thường** theo quy tắc được AWS công bố; query string không thuộc phần so khớp của `path-pattern`. Nếu cần khớp `?region=us`, hãy dùng condition `query-string` riêng.

### 4.2. Path forwarding không mặc nhiên viết lại URL

Ví dụ rule có `/api/*` và request là:

~~~text
GET https://app.example.com/api/orders/123?include=items
~~~

Nếu chỉ cấu hình condition `path-pattern` với action `forward`, backend thông thường tiếp tục nhận đường dẫn tương ứng **`/api/orders/123`**; ALB **không tự xóa `/api`** chỉ vì đã match. Nếu backend thực sự chỉ có endpoint `/orders/123`, cần:

1. Để backend hiểu prefix `/api`; hoặc
2. Cấu hình **URL rewrite transform** khi listener/dịch vụ hỗ trợ, với pattern và replacement được kiểm thử; hoặc
3. Thiết kế tầng ingress/reverse proxy khác chịu trách nhiệm rewrite.

Tránh suy luận behavior rewrite theo tên action. Thay đổi path có thể ảnh hưởng chữ ký request, cache key, authorization và log/tracing.

### 4.3. Tránh rule bị che khuất

Giả sử hai rule:

~~~text
priority 10: path /api/* -> tg-api-default
priority 20: path /api/internal/* -> tg-api-internal
~~~

Mọi request `/api/internal/users` đã khớp priority 10, nên **không đi tới rule 20**. Phải đảo thứ tự:

~~~text
priority 10: path /api/internal/* -> tg-api-internal
priority 20: path /api/*          -> tg-api-default
~~~

Đây là lỗi thường gặp nhất khi một hệ thống có nhiều microservices hoặc route legacy. Hãy vẽ thứ tự ưu tiên và chạy bộ request mẫu trước khi áp rule mới.

## 5. HTTP header routing: chia luồng theo metadata request

### 5.1. Cách HTTP header condition hoạt động

ALB cho phép so khớp một HTTP header theo tên và giá trị. Ví dụ client gửi:

~~~http
GET /checkout HTTP/1.1
Host: shop.example.com
X-Release: canary
~~~

Một rule có `Host=shop.example.com`, `Path=/checkout*` và `X-Release=canary` có thể định tuyến request đó sang target group mới.

Ví dụ condition:

~~~json
[
  {
    "Field": "http-header",
    "HttpHeaderConfig": {
      "HttpHeaderName": "X-Release",
      "Values": ["canary"]
    }
  }
]
~~~

Tên và giá trị header so khớp theo quy tắc không phân biệt hoa/thường của ALB. Header names, giá trị, wildcard và regex có giới hạn; một số cấu hình bảo mật như `routing.http.drop_invalid_header_fields.enabled` có thể khiến ALB loại bỏ những header không hợp lệ.

### 5.2. Phối hợp Host + Path + Header

Ví dụ điều kiện đầy đủ:

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": ["shop.example.com"]
    }
  },
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": ["/checkout*"]
    }
  },
  {
    "Field": "http-header",
    "HttpHeaderConfig": {
      "HttpHeaderName": "X-Release",
      "Values": ["canary"]
    }
  }
]
~~~

Rule này chỉ khớp khi cả **host, path và header** phù hợp. Nếu thiếu header, request nên rơi xuống một rule có priority thấp hơn để dùng target group ổn định hoặc default action đã định nghĩa.

### 5.3. Header do client gửi không phải bằng chứng xác thực

Đặt `X-Release: canary` qua `curl` rất đơn giản, vì vậy:

- Dùng header routing cho **canary testing, phân chia kênh thử nghiệm, định tuyến theo client capability** nếu hệ thống chấp nhận nguồn header.
- **Không dùng header client tự khai báo để xác thực** khách hàng, quyết định tenant, quyền admin hay chính sách truy cập dữ liệu.
- Nếu một trusted proxy/edge component gắn header, cần bảo đảm client không thể cung cấp hoặc giả mạo cùng header để vượt quy tắc.
- Đối với truy cập nhạy cảm, dùng **IAM/OIDC/Cognito, application authorization, AWS WAF** và các kiểm soát phía backend phù hợp.

Điều kiện header không tự chặn việc gọi thẳng backend qua đường mạng khác. Target nên nằm trong subnet/security group được thiết kế để chỉ nhận những luồng truy cập cho phép.

## 6. Weighted target groups: chia traffic theo tỷ lệ

### 6.1. Trọng số áp dụng ở đâu?

Trong một **`forward` action** có nhiều target groups, ALB có thể chia lưu lượng theo **weight** mỗi nhóm. Trọng số là số nguyên trong phạm vi AWS quy định (thường **0–999** cho mỗi nhóm), và tỷ phần lý thuyết của một nhóm có weight dương là:

~~~text
Traffic share của group i
≈ weight_i / tổng weight của các group được cấu hình
~~~

Ví dụ:

| Target group | Weight | Tỷ phần dự kiến |
|---|---:|---:|
| `tg-stable` | 90 | 90% |
| `tg-canary` | 10 | 10% |
| Tổng | 100 | 100% |

Tỷ lệ quan sát được không nhất thiết đúng 90/10 ở một cửa sổ nhỏ do thống kê, số lượng request, stickiness, lỗi client và hành vi workload. Weight **không giống số target**: một target group có 5 EC2 không tự nhận traffic gấp 5 lần nhóm có 1 EC2.

### 6.2. Ví dụ ForwardConfig

~~~json
[
  {
    "Type": "forward",
    "ForwardConfig": {
      "TargetGroups": [
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-stable/1111111111111111",
          "Weight": 90
        },
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-canary/2222222222222222",
          "Weight": 10
        }
      ],
      "TargetGroupStickinessConfig": {
        "Enabled": false
      }
    }
  }
]
~~~

Tất cả ARN ở trên là **giá trị minh họa**. Trong một forward action, AWS hỗ trợ nhiều target group trong giới hạn dịch vụ; dùng nhóm phù hợp với listener và cân nhắc thuật toán phân phối nội bộ từng group.

**Hai cấp phân phối cần tách:**

1. **Giữa target groups:** dựa trên các weight được cấu hình trong forward action.
2. **Giữa các targets của cùng target group:** theo thuật toán/cấu hình target group và trạng thái health của target.

Một rule có thể vừa dùng `host-header`/`path-pattern` để chọn nhóm ứng dụng, vừa dùng weighted forward để chia lưu lượng giữa hai phiên bản của ứng dụng ấy.

### 6.3. Quy tắc quan trọng: weight không phải failover

**ALB không tự động chuyển trọng số sang target group khác khi một weighted target group trống hoặc toàn unhealthy.** Vì vậy, nếu `tg-canary` có weight 10 và tất cả target của nó không khỏe, không được giả định rằng 100% lưu lượng sẽ tự dồn sang `tg-stable`.

Hướng thiết kế vận hành:

- Có **health check** cho từng target group.
- Theo dõi `HealthyHostCount`, `UnHealthyHostCount`, HTTP 5xx và latency.
- Tạo khả năng **rollback weight về 0 cho canary** hoặc chuyển rule về stable khi điều kiện cảnh báo đạt ngưỡng.
- Kết hợp deployment system/Auto Scaling để thay thế target không khỏe.
- Thử nghiệm cơ chế rollback trong sandbox thay vì coi health check là kế hoạch failover hoàn chỉnh.

Bên trong một target group cũng có hành vi fail-open hoặc ngưỡng sức khỏe theo cấu hình của dịch vụ; không nên suy luận từ đó rằng **weighted group routing có tự động failover giữa groups**.

### 6.4. Target group stickiness

Nếu cần giữ một client ở cùng **target group** giữa các request, có thể bật `TargetGroupStickinessConfig` với thời lượng phù hợp. Khi đó ALB sử dụng cookie theo cơ chế dịch vụ để duy trì lựa chọn group, giúp người dùng không bị chuyển liên tục giữa phiên bản stable/canary.

Phân biệt:

- **Target-group stickiness:** giữ client gắn với **group** trong một weighted forward action.
- **Target stickiness:** giữ client gắn với **một target** trong target group theo khả năng và cấu hình khác.

Stickiness có thể làm phân phối thực tế lệch tỷ lệ weight, gây vấn đề với client không lưu cookie hoặc request API stateless. Nếu ứng dụng cần session, ưu tiên lưu session bên ngoài EC2 (như Redis/DynamoDB phù hợp) để không phụ thuộc một node; chỉ bật stickiness khi có lý do rõ ràng.

## 7. Canary, blue/green và triển khai theo giai đoạn

### 7.1. Canary rollout bằng weight

Giả sử cùng một endpoint API có hai phiên bản:

- **Stable:** `tg-api-v1` chạy phiên bản đã kiểm chứng.
- **Canary:** `tg-api-v2` chạy phiên bản mới.

Chiến lược rollout ví dụ:

| Giai đoạn | Stable | Canary | Tiêu chí đi tiếp |
|---|---:|---:|---|
| Kiểm tra khói | 100 | 0 | Canary đã deploy, health và smoke test đạt |
| Canary nhỏ | 99 | 1 | Error rate/latency ổn định, số request đủ |
| Canary mở rộng | 90 | 10 | 5xx, p95/p99, business metrics đạt |
| Chuyển dần | 50 | 50 | Không có regression, hệ thống đủ capacity |
| Hoàn tất | 0 | 100 | Đạt tiêu chí, giữ khả năng rollback trong cửa sổ kiểm soát |

**Các tỷ lệ chỉ là kế hoạch minh họa.** Đừng tăng trọng số theo thời gian cố định nếu chưa có lượng request đủ để đánh giá lỗi hiếm. Với traffic thấp, 1% có thể cho quá ít request để kết luận.

~~~mermaid
flowchart LR
    U[Clients] --> ALB[ALB listener rule]
    ALB -->|90% dự kiến| ST[Stable target group]
    ALB -->|10% dự kiến| CA[Canary target group]
    ST --> VM1[API v1 targets]
    CA --> VM2[API v2 targets]
    MON[CloudWatch / logs / traces / business KPIs] -. Theo dõi .-> ST
    MON -. Theo dõi .-> CA
    MON --> R{SLO đạt?}
    R -->|Có| INC[Tăng weight canary]
    R -->|Không| RB[Đặt canary weight 0 / rollback]
~~~

### 7.2. Blue/green deployment

Blue/green có hai môi trường/target groups sẵn sàng. Khi xác nhận green tốt, có thể đổi traffic bằng một rule forward hoặc tăng dần weight. Ưu điểm là giữ môi trường blue làm đường rollback tạm thời.

Lưu ý:

- Backend database/schema migration phải **tương thích hai chiều** trong khoảng chuyển đổi; rollback code không sửa được schema phá vỡ tương thích.
- Đừng coi weight 0 là đã **xóa** phiên bản; targets/compute và tài nguyên liên quan vẫn tồn tại, phát sinh chi phí.
- Nếu phải bảo toàn session, áp dụng sticky/group consistency hoặc tách trạng thái theo mô hình ứng dụng.
- Route rule chỉ là một phần của deployment; cần health checks, autoscaling, smoke tests, metrics và rollback.

### 7.3. Khi nào dùng header thay cho weight?

**Header routing** phù hợp để thử phiên bản mới với nhóm kiểm thử đã xác định hoặc request từ một công cụ thử nghiệm:

~~~text
Host api.example.com + Header X-Release: canary -> tg-api-v2
Host api.example.com (không header)             -> tg-api-v1
~~~

**Weighted routing** phù hợp để lấy mẫu một tỷ lệ traffic chung. Có thể kết hợp:

1. Rule priority cao dành cho tester gửi header, chuyển **100% tester** sang canary.
2. Rule priority thấp hơn phân phối traffic còn lại **99/1** giữa stable/canary.
3. Default rule xử lý host/path còn lại.

Phải kiểm soát thứ tự priority để tester không bị rule chung bắt trước. Header do client tự gửi **không phù hợp làm kiểm soát bảo mật**; tester có quyền truy cập dữ liệu thực phải được xác thực ở ứng dụng.

## 8. Thiết kế routing rules có thể kiểm chứng

### 8.1. Ví dụ kiến trúc hoàn chỉnh

Hệ thống bán hàng có ba dịch vụ ở hai AZ:

- `shop.example.com`: frontend.
- `api.example.com`: API stable và canary.
- `admin.example.com`: dashboard quản trị; xác thực độc lập.

Đề xuất thứ tự rule:

| Priority | Điều kiện | Action | Lý do |
|---:|---|---|---|
| 10 | Host `api.example.com` + Header `X-Release: canary` | Forward `tg-api-canary` | Tester/canary chỉ định |
| 20 | Host `api.example.com` + Path `/v2/*` | Forward `tg-api-v2` | Dịch vụ API v2 theo path |
| 30 | Host `api.example.com` + Path `/v1/*` | Forward 90% `tg-api-stable` + 10% `tg-api-canary` | Canary tỷ lệ nhỏ |
| 40 | Host `shop.example.com` + Path `/static/*` | Forward `tg-static` | Tài nguyên tĩnh |
| 50 | Host `shop.example.com` | Forward `tg-web` | Frontend còn lại |
| 60 | Host `admin.example.com` | Authenticate rồi forward `tg-admin` | Dashboard |
| Default | Không điều kiện | Fixed response 404 | Loại host/path chưa khai báo |

**Mẫu này không phải ACL toàn diện.** Cần cấu hình TLS certificate đúng các hostname, security groups, IAM, AWS WAF và authorization ở backend. Có thể dùng CloudFront + S3 thay một target group EC2 chuyên phục vụ static files tùy kiến trúc.

### 8.2. Bảng thử request dự kiến

| Request | Rule đầu tiên khớp | Kết quả |
|---|---|---|
| `Host=api.example.com`, `Path=/v1/orders`, `X-Release=canary` | 10 | `tg-api-canary` |
| `Host=api.example.com`, `Path=/v2/orders`, không header | 20 | `tg-api-v2` |
| `Host=api.example.com`, `Path=/v1/orders`, không header | 30 | Chia stable/canary theo weight |
| `Host=shop.example.com`, `Path=/static/logo.svg` | 40 | `tg-static` |
| `Host=shop.example.com`, `Path=/cart` | 50 | `tg-web` |
| `Host=admin.example.com`, `Path=/settings` | 60 | Đăng nhập hợp lệ rồi tới `tg-admin` |
| `Host=unknown.example.com`, `Path=/anything` | Default | 404 từ ALB |

Nếu muốn định tuyến `/v1` **không có dấu /** ở cuối, bổ sung pattern phù hợp; `/v1/*` không nhất thiết khớp toàn bộ biến thể `/v1`. Kiểm thử chính xác path normalization và pattern trong ứng dụng thực.

### 8.3. Phân biệt routing với URL rewrite

Routing chọn target group; rewrite làm thay đổi host/path trước khi gửi backend nếu được cấu hình. Ví dụ cùng request `/api/v1/orders`:

- **Routing thuần:** backend nhận path tương ứng `/api/v1/orders`.
- **URL rewrite:** có thể cấu hình biến đổi thành `/v1/orders` theo rule transform hỗ trợ.

Khi thêm transform, cập nhật bộ test để xác minh header/path/HTTP status từ backend và log. Không bật rewrite chỉ vì nhóm backend chưa rõ quy ước đường dẫn.

## 9. Thực hành 1 — Đọc cấu hình ALB bằng AWS CLI

**Phần này chỉ đọc**, phù hợp cả khi bạn chưa được cấp quyền thay đổi tài nguyên. Bạn cần AWS CLI v2, profile hợp lệ và quyền `elasticloadbalancing:DescribeLoadBalancers`, `DescribeListeners`, `DescribeRules`, `DescribeTargetGroups`, `DescribeTargetHealth` tương ứng.

### 9.1. Xác minh account và Region

Ví dụ dùng Bash/Linux hoặc AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws configure list --profile "$AWS_PROFILE"
~~~

Nếu đang dùng **AWS CloudShell** dưới phiên Console và không có profile `aws-lab-dev`, bỏ dòng `export AWS_PROFILE` và tham số `--profile` khi cần. Kiểm tra account/role thực tế trước khi tiếp tục.

### 9.2. Liệt kê ALB và listener

~~~bash
REGION=ap-southeast-1

aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --query 'LoadBalancers[].{Name:LoadBalancerName,Type:Type,DNS:DNSName,State:State.Code}' \
  --output table
~~~

Chọn một ALB **được cấp phép để xem** rồi lấy listener:

~~~bash
ALB_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:loadbalancer/app/aws-lab-alb/0123456789abcdef"

aws elbv2 describe-listeners \
  --load-balancer-arn "$ALB_ARN" \
  --region "$REGION" \
  --query 'Listeners[].{Listener:ListenerArn,Protocol:Protocol,Port:Port}' \
  --output table
~~~

Các ARN là **placeholder giả định**, phải thay bằng ARN thật của sandbox. Một lỗi `LoadBalancerNotFound` thường là sai ARN/Region/account hoặc tài nguyên không tồn tại.

### 9.3. Đọc thứ tự listener rules

~~~bash
LISTENER_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/aws-lab-alb/0123456789abcdef/abcdef0123456789"

aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --region "$REGION" \
  --output json
~~~

Ghi lại theo thứ tự:

1. `Priority`: các rule non-default được xét từ số nhỏ tới số lớn.
2. `Conditions`: `Field`, `Values` hoặc `HostHeaderConfig`/`PathPatternConfig`/`HttpHeaderConfig`.
3. `Actions`: `Type`, `TargetGroupArn` hoặc `ForwardConfig.TargetGroups` và `Weight`.
4. `IsDefault`: rule fallback khi không có rule khác khớp.

**Bài tập:** Từ cấu hình trả về, tìm ba request giả định: (a) request khớp host nhưng sai path; (b) khớp host + path nhưng thiếu header; (c) khớp cả ba. Xác định rule và target group đầu tiên mà mỗi request sẽ sử dụng.

### 9.4. Kiểm tra target groups và health

~~~bash
aws elbv2 describe-target-groups \
  --load-balancer-arn "$ALB_ARN" \
  --region "$REGION" \
  --query 'TargetGroups[].{Name:TargetGroupName,Arn:TargetGroupArn,Protocol:Protocol,Port:Port,Type:TargetType}' \
  --output table
~~~

Với một target group cụ thể:

~~~bash
TG_ARN="arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-stable/1111111111111111"

aws elbv2 describe-target-health \
  --target-group-arn "$TG_ARN" \
  --region "$REGION" \
  --query 'TargetHealthDescriptions[].{Id:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason,Description:TargetHealth.Description}' \
  --output table
~~~

Nếu target chưa healthy, chưa nên sử dụng target group đó cho rollout có lưu lượng thật. Kiểm tra **health check path/port/status matcher**, security group và khả năng kết nối từ ALB tới target.

## 10. Thực hành 2 — Tạo rule host/path/header và weight trên sandbox

> **Đây là phần mở rộng có tác động thật**. Chỉ áp dụng trên **ALB và target groups dành riêng cho lab**, có quyền thay đổi, đã xác minh account/Region và biết cách dọn rule. ALB, backend EC2/ECS, log, truyền dữ liệu và các thành phần khác có thể phát sinh phí. Phần này không bắt buộc nếu bạn chỉ có quyền đọc.

### 10.1. Điều kiện đầu vào

Sandbox cần sẵn:

- ALB gắn ít nhất hai AZ phù hợp và có HTTPS listener hoặc HTTP listener dành riêng cho lab.
- `tg-stable` và `tg-canary` có targets khỏe; ứng dụng trả **response có đánh dấu phiên bản** (ví dụ JSON `{"version":"stable"}` hoặc `{"version":"canary"}`) để biết được request đã đi đâu.
- Listener priority dự kiến **chưa bị dùng**; kiểm tra bằng `describe-rules`.
- Security group cho phép đường từ client kiểm thử đến ALB và từ ALB đến backend, trong phạm vi sandbox.
- Quyền `elasticloadbalancing:CreateRule`, `ModifyRule`, `DeleteRule` và các quyền đọc cần thiết.

**Không tạo rule vào listener đang phục vụ production** hoặc listener do người khác sở hữu. Mỗi mục bên dưới có JSON ví dụ; **thay ARN giả định bằng ARN thật** trước khi thực thi.

### 10.2. Tạo rule dành riêng cho tester theo header

Tạo file `conditions-canary.json` chứa:

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": ["api.example.com"]
    }
  },
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": ["/v1/*"]
    }
  },
  {
    "Field": "http-header",
    "HttpHeaderConfig": {
      "HttpHeaderName": "X-Release",
      "Values": ["canary"]
    }
  }
]
~~~

Tạo file `actions-canary.json`:

~~~json
[
  {
    "Type": "forward",
    "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-canary/2222222222222222"
  }
]
~~~

Tạo rule priority 10 **chỉ khi listener sandbox có priority 10 còn trống**:

~~~bash
RULE_CANARY_ARN=$(aws elbv2 create-rule \
  --listener-arn "$LISTENER_ARN" \
  --priority 10 \
  --conditions file://conditions-canary.json \
  --actions file://actions-canary.json \
  --region "$REGION" \
  --query 'Rules[0].RuleArn' \
  --output text)

echo "$RULE_CANARY_ARN"
~~~

Rule trên chỉ khớp khi host, path và header đều đúng. Nếu người kiểm thử không gửi `X-Release: canary`, request không vào rule này và sẽ được xử lý bởi rule tiếp theo/default action.

### 10.3. Tạo weighted rule cho mọi request API v1 còn lại

Tạo file `conditions-v1.json`:

~~~json
[
  {
    "Field": "host-header",
    "HostHeaderConfig": {
      "Values": ["api.example.com"]
    }
  },
  {
    "Field": "path-pattern",
    "PathPatternConfig": {
      "Values": ["/v1/*"]
    }
  }
]
~~~

Tạo file `actions-v1-weighted.json`:

~~~json
[
  {
    "Type": "forward",
    "ForwardConfig": {
      "TargetGroups": [
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-stable/1111111111111111",
          "Weight": 90
        },
        {
          "TargetGroupArn": "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/tg-api-canary/2222222222222222",
          "Weight": 10
        }
      ],
      "TargetGroupStickinessConfig": {
        "Enabled": false
      }
    }
  }
]
~~~

Tạo weighted rule priority 20:

~~~bash
RULE_WEIGHTED_ARN=$(aws elbv2 create-rule \
  --listener-arn "$LISTENER_ARN" \
  --priority 20 \
  --conditions file://conditions-v1.json \
  --actions file://actions-v1-weighted.json \
  --region "$REGION" \
  --query 'Rules[0].RuleArn' \
  --output text)

echo "$RULE_WEIGHTED_ARN"
~~~

Điều cần xác minh:

- Priority 10 và 20 đều hợp lệ/không trùng.
- Header rule được xét trước weighted rule.
- Weighted rule có hai target groups đúng ARN và weight 90/10.
- Target group có healthy targets trong những AZ đã cấu hình.
- Backend xử lý được path `/v1/...`, vì không có URL rewrite trong ví dụ này.

### 10.4. Kiểm thử định tuyến bằng curl

Giả sử `api.example.com` đã trỏ DNS tới ALB lab và chứng chỉ TLS hợp lệ:

~~~bash
curl -i https://api.example.com/v1/status

curl -i \
  -H "X-Release: canary" \
  https://api.example.com/v1/status
~~~

Với request có header, kỳ vọng response đến từ canary (do rule priority 10). Không header, request đi theo **weighted rule priority 20**, nên cần gửi nhiều request và quan sát response/metrics mới đánh giá được phân phối 90/10.

Nếu chưa có DNS riêng, có thể kiểm thử **HTTP listener** được quản trị cho lab bằng cách dùng DNS name của ALB cùng header `Host`; với **HTTPS** cần xem TLS SNI/chứng chỉ/hostname phù hợp. Không dùng `curl -k` làm giải pháp lâu dài để bỏ qua xác thực chứng chỉ; TLS phải được kiểm thử trên hostname hợp lệ khi đưa vào vận hành.

Để xem response backend nào phục vụ, nên đặt header hoặc JSON field như `X-App-Version: stable` / `canary` ở backend thử nghiệm. Header đánh dấu chỉ phục vụ quan sát, không phải cơ chế bảo mật.

### 10.5. Kiểm tra cấu hình sau tạo

~~~bash
aws elbv2 describe-rules \
  --listener-arn "$LISTENER_ARN" \
  --region "$REGION" \
  --query 'Rules[].{Priority:Priority,RuleArn:RuleArn,Conditions:Conditions,Actions:Actions}' \
  --output json
~~~

Nếu priority 10/20 không xuất hiện hoặc JSON khác dự kiến, kiểm tra lỗi AWS CLI, ARN, account và quyền trước khi gửi thêm request. Cần chú ý target group health và default rule để tránh che khuất đường đi của request.

### 10.6. Dọn rule sau lab

Chỉ xóa đúng **rule ARN do bạn vừa tạo**:

~~~bash
aws elbv2 delete-rule \
  --rule-arn "$RULE_CANARY_ARN" \
  --region "$REGION"

aws elbv2 delete-rule \
  --rule-arn "$RULE_WEIGHTED_ARN" \
  --region "$REGION"
~~~

**Không dùng lệnh này nếu biến ARN rỗng hoặc trỏ đến rule của người khác.** Ghi lại ARN trong ghi chú lab trước khi đóng terminal; nếu tạo rule lỗi ở giữa, kiểm tra rule nào thực sự tồn tại rồi mới dọn. Nếu bạn đã tạo ALB, target groups, EC2, ECS service hoặc certificate riêng cho lab, hãy dọn chúng theo quy trình được cấp phép, kiểm tra chi phí EBS, public IPv4, logs và truyền dữ liệu.

## 11. Theo dõi rollout và khả năng phục hồi

### 11.1. Metrics quan trọng

| Lớp | Metrics gợi ý | Diễn giải |
|---|---|---|
| **ALB listener/target group** | `RequestCount`, `RequestCountPerTarget` | Lưu lượng, phân phối giữa các nhóm |
| **Target health** | `HealthyHostCount`, `UnHealthyHostCount` | Canary/stable có đủ target nhận traffic? |
| **HTTP errors** | `HTTPCode_Target_5XX_Count`, `HTTPCode_ELB_5XX_Count` | Phân biệt lỗi backend và load balancer |
| **Latency** | `TargetResponseTime` và p95/p99 ứng dụng | Đánh giá regression của phiên bản mới |
| **Availability** | Target health, health-check failures, connection errors | Cảnh báo khi target group không sẵn sàng |
| **Ứng dụng** | Business conversion, transaction failures, timeout, retry rate | Chỉ số ảnh hưởng người dùng |
| **Chi phí** | ALB usage, LCU, backend compute, cross-AZ transfer, logs | Đánh giá chi phí mỗi request đạt SLO |

CloudWatch có dimension `LoadBalancer` và `TargetGroup` cho nhiều ALB metrics. Khi so sánh stable/canary, lọc theo đúng dimensions. Một số thông số **là metric của target group**, còn log/tracing ở ứng dụng có thể cần thiết để thấy lỗi chi tiết.

### 11.2. Ví dụ tiêu chí rollback

Giả sử canary nhận 10% traffic trong 20 phút. Tổ chức định nghĩa:

- Canary `HealthyHostCount=0` trong thời gian kiểm tra: **dừng rollout, đưa weight về 0**.
- Canary error rate cao hơn baseline một ngưỡng định trước: xem xét rollback theo điều kiện thống kê và tác động người dùng.
- Canary p95 latency vượt SLO: giữ hoặc giảm weight, kiểm tra CPU, DB, connection pool, GC.
- Có lỗi ghi dữ liệu hoặc thay đổi không tương thích: áp quy trình phục hồi ứng dụng/dữ liệu; giảm weight không tự đảo ngược dữ liệu đã ghi.

**Không sao chép một ngưỡng lỗi cố định** cho mọi dịch vụ. Với traffic thấp, cần đủ mẫu; với nghiệp vụ thanh toán, ưu tiên tín hiệu lỗi trọng yếu và ngưỡng bảo vệ nghiêm hơn.

### 11.3. Auto Scaling làm gì trong mô hình này?

**Auto Scaling** tăng/giảm số EC2 theo nhu cầu hoặc chính sách đo tải; **weighted routing** điều chỉnh tỷ lệ request đi tới từng target group. Hai cơ chế nên phối hợp:

~~~text
Weighted routing:
  tg-stable 90% | tg-canary 10%
  -> quyết định tỷ lệ request theo nhóm.

Auto Scaling:
  tg-stable gắn ASG stable
  tg-canary gắn ASG canary
  -> quyết định số instance có thể phục vụ trong từng nhóm.
~~~

Nếu đưa 50% traffic vào canary nhưng chỉ có một target nhỏ, tăng weight có thể gây quá tải. Trước mỗi bước rollout, kiểm tra **canary capacity**, autoscaling warm-up, health checks và giới hạn database/phụ thuộc chung.

### 11.4. Nhiều AZ và failure modes

- Bật ALB trên các AZ phù hợp; target groups nên có targets khỏe ở nhiều AZ khi yêu cầu sẵn sàng cao.
- Health checks chỉ cho biết endpoint kiểm tra đang trả kết quả phù hợp, chưa xác nhận mọi chức năng nghiệp vụ.
- Một dependency chung như RDS, Redis hoặc external API có thể là **single point of failure** dù target groups ở hai AZ.
- Kiểm thử tình huống mất target, thiếu capacity một AZ, canary gặp lỗi và rollback.
- Khi rule chỉ forward tới target group trống/toàn unhealthy, **đừng trông chờ weight tự failover** sang group còn lại.

## 12. Bảo mật và giới hạn của định tuyến Layer 7

### 12.1. TLS, Host header và X-Forwarded-For

ALB có thể kết thúc TLS với chứng chỉ ACM hoặc nguồn chứng chỉ được hỗ trợ. Cần:

1. Có certificate hợp lệ cho tên miền ứng dụng.
2. Cấu hình HTTPS listener và policy TLS đáp ứng yêu cầu bảo mật.
3. Redirect từ HTTP sang HTTPS nếu ứng dụng cần bắt buộc TLS.
4. Kiểm tra backend sử dụng các header do proxy thêm như `X-Forwarded-For`, `X-Forwarded-Proto` và `X-Forwarded-Port` một cách an toàn.
5. Không tin mù quáng vào header client tự gửi khi quyết định danh tính, IP nguồn hay quyền truy cập; cấu hình trusted proxy và xử lý chuỗi IP đúng quy định ứng dụng.

### 12.2. WAF và authorization

**AWS WAF** có thể gắn với ALB theo hỗ trợ của dịch vụ, cho phép lọc request, rate-based rules và các biện pháp bảo vệ trước lớp ứng dụng. Tuy vậy:

- **Routing rule** không thay thế WAF, IAM hoặc application authorization.
- Host/path/header condition chỉ chọn đường đi; nó không cho phép người dùng vượt các bước xác thực ở backend.
- Dashboard admin cần kiểm soát danh tính; nếu cần riêng tư hơn, thiết kế **internal ALB** hoặc giới hạn mạng phù hợp.
- Có thể cần thêm xác thực ở tầng ALB (OIDC/Cognito) và kiểm soát theo role bên trong ứng dụng.

### 12.3. Routing không đảm bảo tenant isolation

Ví dụ frontend gửi header `X-Tenant-ID: company-A`. Nếu ALB dùng header này chuyển request tới ứng dụng A, client vẫn có thể giả mạo header `company-B`. **Tenant isolation cần cơ chế danh tính có thể kiểm chứng và ủy quyền theo tài nguyên**, cùng kiểm tra dữ liệu phía backend. Không dùng routing header làm ranh giới bảo mật cho dữ liệu khách hàng.

## 13. Chi phí và hạn mức khi dùng nhiều rules/target groups

### 13.1. Chi phí

ALB thường tính phí **theo thời gian hoạt động** và mức sử dụng **Load Balancer Capacity Units (LCU)** theo mô hình giá AWS hiện hành. Backend EC2/ECS/Lambda, dữ liệu truyền, CloudWatch logs, WAF, DNS và các thành phần khác có bảng giá riêng.

| Thành phần | Có thể phát sinh chi phí | Cách kiểm soát |
|---|---|---|
| ALB | Thời gian ALB chạy và mức LCU sử dụng | Xóa ALB lab không cần thiết; đo tải và tính giá |
| Target compute | EC2/ECS/Lambda hoặc backend tương ứng | Auto Scaling, right-sizing, lịch chạy phù hợp |
| Logs/metrics | Log lưu S3, CloudWatch metrics/logs, tracing | Retention và tần suất thu thập hợp lý |
| Security | WAF/web ACL rules, request processing và dịch vụ liên quan | Chọn rule đúng nhu cầu, đo chi phí |
| Networking | Data transfer/cross-AZ, NAT hoặc thành phần khác nếu có | Thiết kế VPC/AZ và giám sát lưu lượng |

**Không mặc định weighted routing miễn phí chỉ vì thêm một rule**: việc duy trì thêm nhóm backend có thể tạo chi phí compute, EBS, IP, monitoring và vận hành. Ngược lại, số target groups đơn lẻ không đồng nghĩa có phí target group tách biệt theo giờ.

### 13.2. Quotas

AWS giới hạn các tài nguyên như số rules mỗi ALB, target groups, listeners và số condition/match evaluation theo rule. Nếu đạt quota, AWS CLI có thể trả lỗi quota/limit tương ứng.

Nguyên tắc:

- Không tạo một rule mới cho từng người dùng hoặc từng request; quản lý nhóm lưu lượng có thể dự đoán.
- Đặt conventions cho priority, ví dụ mỗi dịch vụ được cấp một khoảng số để tránh va chạm.
- Giữ các rule có ý nghĩa rõ, dễ rà soát; dọn rule của phiên bản đã ngừng phục vụ.
- Kiểm tra **Service Quotas** và tài liệu AWS hiện hành trước khi cần số rule lớn.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Request `/api/internal/*` vào backend chung | Rule `/api/*` có priority cao hơn | Sắp xếp rule cụ thể trước rule tổng quát |
| Host đúng nhưng 404 từ ALB | Không có path rule khớp, rơi vào fixed-response default | `describe-rules`, kiểm tra Host và path thực tế |
| Header routing không khớp | Header name/value khác dự kiến; proxy loại/sửa header; rule priority sai | Kiểm tra request thực, cấu hình ALB và edge proxy |
| Header điều khiển canary bị client tự giả mạo | Dựa vào header không đáng tin cho quyền truy cập | Chuyển authorization sang identity/backend, kiểm soát edge |
| Weighted 90/10 không thấy chính xác trong 20 request | Kích thước mẫu nhỏ, stickiness và traffic khác nhau | Tăng cửa sổ quan sát, phân tích request count theo target group |
| Canary unhealthy nhưng ALB vẫn có lỗi | Weighted target group không tự failover | Rollback weight, kiểm tra health và capacity |
| Kết nối HTTPS lỗi dù Host rule đúng | SNI/certificate hoặc DNS sai | Kiểm tra certificate, TLS listener, domain thực |
| Backend trả 404 dù ALB đã chọn đúng target | Backend không hiểu prefix `/api` | Xác minh path gốc và URL rewrite nếu sử dụng |
| Target health báo unhealthy | Health check path/status/port sai; SG không cho phép kết nối | `describe-target-health`, network + application logs |
| Không tạo được rule mới | Priority trùng, ARN sai, condition/quota không hợp lệ | Xem error từ `create-rule`, quota và cấu hình hiện hữu |
| Tăng canary weight nhưng latency tăng mạnh | Canary chưa đủ capacity hoặc dependency chung quá tải | ASG/ECS capacity, CPU, DB, connection pool, trace |
| Target group stable có targets khỏe nhưng một số request vẫn lỗi | Canary group nhận traffic nhưng không khỏe | Xem trọng số từng group, health và metric 5xx |
| Dữ liệu không phục hồi khi rollback application | Schema/data migration phá vỡ tương thích | Thiết kế migration backward compatible và backup/restore |
| Hóa đơn cao sau khi kết thúc test | ALB/EC2/EBS/logging còn chạy | Kiểm tra Cost Explorer và tài nguyên theo Region/tag |

### 14.1. Trình tự chẩn đoán ngắn

~~~text
1. Đúng account, Region, ALB, listener, hostname?
2. TLS/DNS/client request có thực sự đến đúng ALB?
3. Rule priority nào khớp trước?
4. Condition host/path/header có đúng request sau proxy/normalization?
5. Action forward/redirect/fixed-response và weight có đúng?
6. Target group có healthy targets và đủ capacity?
7. Lỗi do ALB, backend, IAM/network, WAF hay dependency ứng dụng?
8. Có rollback và dọn tài nguyên sau thử nghiệm không?
~~~

## 15. Tình huống thực tế và bài tập đánh giá

### 15.1. Bài toán

Một nền tảng học trực tuyến chạy trên AWS có:

- `learn.example.com`: frontend học viên.
- `api.example.com`: API nội dung và tiến độ.
- `teacher.example.com`: cổng giáo viên.
- Một đợt phát hành **API v2** chưa sẵn sàng nhận toàn bộ traffic.
- API v1 và v2 chạy trên hai nhóm EC2 Auto Scaling ở hai AZ; state nghiệp vụ lưu ngoài EC2.
- Yêu cầu kiểm soát độ trễ p99, số lỗi 5xx, chi phí và phục hồi khi phiên bản mới gặp sự cố.

Hãy thiết kế listener rules và deployment workflow.

**Một phương án tham khảo:**

| Rule | Priority | Điều kiện | Action |
|---|---:|---|---|
| Test canary | 10 | `Host=api.example.com` + `X-Release=canary` | 100% tới `tg-api-v2` |
| Public API | 20 | `Host=api.example.com` + `Path=/v1/*` | Stable 95%, canary 5% |
| Teacher portal | 30 | `Host=teacher.example.com` | Xác thực phù hợp + `tg-teacher` |
| Student frontend | 40 | `Host=learn.example.com` | `tg-frontend` |
| Default | - | Không khớp | 404 |

Bên cạnh listener rules, cần:

- ALB HTTPS certificate và DNS phù hợp.
- Security groups và IAM roles đúng mức cần thiết.
- Target group health check, Auto Scaling mỗi phiên bản và khả năng thay thế instance.
- Dashboard per target group/phiên bản; điều kiện tiến/tạm dừng/rollback.
- Database migration tương thích khi hai phiên bản cùng chạy.
- AWS WAF/application authorization; header canary chỉ phục vụ chọn phiên bản.
- Cost Explorer/AWS Budgets cho ALB và backend, cùng kế hoạch xóa môi trường thử.

### 15.2. Câu hỏi suy luận

1. Tại sao rule `Host=api.example.com` không nên đứng trước rule `Host=api.example.com` + `X-Release=canary`?
2. Nếu request đúng host nhưng path `/v1` không khớp `/v1/*`, ALB thực hiện gì?
3. Priority 10/20 có liên quan gì đến weight 90/10 không?
4. Với rule có hai điều kiện Host và Header, những điều kiện nào phải đúng để rule khớp?
5. Nếu canary weight 10 nhưng target group canary trống hoặc unhealthy, ALB có tự dồn 10% sang stable không?
6. Header do browser gửi có thể thay thế xác thực của teacher portal không?
7. Khi điều chỉnh canary từ 5% lên 50%, cần đo capacity và SLO nào trước?
8. Khi backend nhận path `/api/users` nhưng chỉ có route `/users`, vấn đề nằm ở đâu?
9. Có thể kết luận thành công từ việc 10 request đầu tiên đi stable và 1 request đi canary không?
10. Làm thế nào vừa đảm bảo rollback code nhanh, vừa xử lý database schema migration?
11. ALB routing và EC2 Auto Scaling giải quyết hai vấn đề khác nhau như thế nào?
12. Khi cần dùng một ALB cho nhiều subdomain, có cần chứng chỉ TLS và DNS phù hợp từng hostname không?

### 15.3. Đáp án gợi ý

1. Rule tổng quát có thể bắt request trước, khiến rule header không bao giờ được xét.
2. ALB thử rule kế tiếp rồi default action nếu không còn rule khớp.
3. Priority quyết định **rule được xét trước**, weight quyết định **tỷ lệ gửi tới target groups trong một action**.
4. Cả Host và Header đều đúng, do rule kết hợp condition theo logic AND.
5. Không; weighted routing không tự failover giữa target groups như vậy.
6. Không; client có thể tự sửa header, authorization cần dựa trên danh tính và quyền được xác minh.
7. Healthy targets, request count, error rate, TargetResponseTime/p95/p99, DB capacity và chỉ số nghiệp vụ.
8. Path routing không tự động strip prefix; cần backend hỗ trợ hoặc URL rewrite transform được cấu hình.
9. Không; mẫu quá nhỏ để đánh giá tỷ lệ và chất lượng.
10. Dùng backward-compatible schema, phased migration, backup/restore và kế hoạch khôi phục.
11. Routing chọn **đích request**, Auto Scaling điều chỉnh **số target có thể phục vụ**.
12. Có; phải xác minh domain, DNS và certificate/SNI cho đường HTTPS.

## 16. Checklist hoàn thành bài học

Trước khi đưa cấu hình routing vào môi trường dùng chung:

- [ ] Đã vẽ sơ đồ ALB, listeners, rule priorities, target groups và AZ.
- [ ] Các condition Host/Path/Header có bộ request test cho cả trường hợp khớp và không khớp.
- [ ] Rule chuyên biệt đứng trước rule tổng quát, không có priority trùng.
- [ ] Path forwarding có tương thích backend; nếu rewrite, đã kiểm thử transform.
- [ ] Hostname, DNS, TLS certificates/SNI và HTTP→HTTPS redirect được kiểm tra.
- [ ] Header client tự gửi không được dùng thay authentication/authorization.
- [ ] Hai target groups của weighted forward có đúng ARN, weights và healthy targets.
- [ ] Có dashboard để so sánh stable/canary theo error rate, latency và business metrics.
- [ ] Có tiêu chí rollback; không phụ thuộc vào weighted target group auto-failover.
- [ ] Canary đủ capacity và Auto Scaling đã được cấu hình theo tải dự kiến.
- [ ] Phương án đa AZ, storage bền vững và database compatibility đã được đánh giá.
- [ ] Quyền IAM, security groups và AWS WAF phù hợp với luồng truy cập.
- [ ] Đã dự trù chi phí ALB/LCU, backend và logs; có hướng dẫn dọn môi trường lab.

**Kết quả mong đợi:** người học có thể phân loại request theo Host/Path/Header, dự đoán listener rule đầu tiên khớp, giải thích weighted forward và thiết kế rollout theo dữ liệu đo được. Từ đó, họ biết triển khai an toàn, giám sát lỗi, phục hồi khi canary gặp sự cố và tránh để tài nguyên thử nghiệm phát sinh chi phí không kiểm soát.

## Tài liệu AWS chính thức

- [Application Load Balancer listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-rules.html)
- [Condition types for listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/rule-condition-types.html)
- [Action types for listener rules](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/rule-action-types.html)
- [Add a listener rule](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/add-rule.html)
- [Target groups for Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html)
- [Health checks for ALB target groups](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html)
- [AWS CLI elbv2 create-rule](https://docs.aws.amazon.com/cli/latest/reference/elbv2/create-rule.html)
- [Monitor Application Load Balancers using CloudWatch](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html)
- [Elastic Load Balancing quotas](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-limits.html)
- [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)
- [EC2 Auto Scaling documentation](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)

> **Lưu ý khi áp dụng:** Tên miền `example.com`, ARN account `111122223333`, target groups và đường dẫn trong bài là ví dụ đào tạo. AWS có thể cập nhật giới hạn, cú pháp và tính năng rule/transform theo Region và phiên bản dịch vụ. Trước khi thay đổi listener production, đối chiếu tài liệu AWS hiện hành, kiểm thử trên sandbox và chuẩn bị phương án rollback đã được duyệt.
