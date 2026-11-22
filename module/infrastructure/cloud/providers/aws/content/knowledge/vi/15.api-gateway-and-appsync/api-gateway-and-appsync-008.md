# Private API, VPC Link và backend trong VPC

Một hệ thống Java/Spring Boot chạy trên Amazon ECS hoặc EC2 thường đặt sau **internal Application Load Balancer (ALB)** trong các private subnets. Đội phát triển muốn dùng **Amazon API Gateway** để xử lý authentication, routing, throttling, metrics và versioning, nhưng không muốn backend phải có public IP. Một hệ thống khác lại muốn **chính API endpoint cũng chỉ truy cập được từ mạng nội bộ**. Hai yêu cầu có vẻ giống nhau nhưng dùng **hai cơ chế khác nhau** trong AWS:

- **Private API:** hạn chế **đường client gọi vào API Gateway**. Trong API Gateway, endpoint type **PRIVATE** hiện chỉ có cho **REST API**; client đi qua **Interface VPC Endpoint cho `execute-api`**.
- **Private integration qua VPC Link:** nối **API Gateway tới HTTP/HTTPS backend bên trong VPC**. Một API có VPC Link vẫn có thể là **public API** ở phía client, trừ khi cấu hình endpoint private hoặc biện pháp kiểm soát riêng.
- **AWS AppSync Private API:** cung cấp **GraphQL/Realtime API** riêng tư qua **AppSync Interface VPC Endpoint**; không dùng API Gateway VPC Link để truy cập GraphQL endpoint.

Bài học thuộc chương **API Gateway và AppSync** của mô-đun **CLOUD_PROVIDERS_AWS**. Chủ đề liên hệ với Region/AZ, IAM, VPC, Route 53, ECS/EC2, Lambda, RDS, CloudWatch, phân phối nội dung, khả năng phục hồi và kiểm soát chi phí. Mục tiêu cuối cùng là thiết kế tuyến **client → API → backend** vừa đúng về mạng, vừa đúng về quyền truy cập, sẵn sàng phục vụ và quan sát được khi có lỗi.

> **Ghi nhớ trước tiên:** **Private API** mô tả *ai có thể đi vào API Gateway và đi bằng đường nào*; **VPC Link** mô tả *API Gateway đi tới backend trong VPC bằng đường nào*. Chúng độc lập và **có thể được kết hợp** trong cùng một REST API.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Private REST API**, **REST/HTTP API private integration**, **VPC Link V1/V2**, **AWS AppSync Private API** và **AWS PrivateLink**.
2. Giải thích luồng client → `execute-api` Interface Endpoint → Private REST API → integration → backend.
3. Nêu các điều kiện để API Gateway kết nối **ALB, NLB hoặc AWS Cloud Map** bằng VPC Link V2 và hiểu giới hạn theo loại API.
4. Thiết kế private subnets, Security Groups, routing, NACL, DNS và TLS cho VPC Link và backend trên ECS/EC2.
5. Cấu hình **API resource policy** dùng `aws:SourceVpce`/`aws:SourceVpc`, VPC endpoint policy và method authorization phù hợp.
6. Giải thích VPC Link V2 **immutable subnet/SG**, trạng thái `PENDING`/`AVAILABLE`/`INACTIVE` và chu kỳ không hoạt động 60 ngày.
7. Biết lỗi **stage path prefix**, `Host`/SNI/TLS, target group health, quyền IAM, endpoint private DNS và cross-account connectivity.
8. Phân biệt **AppSync data-plane** `appsync-api` với **control-plane** `appsync` endpoints; hiểu giới hạn thay đổi visibility sau khi tạo.
9. Đọc cấu hình bằng AWS Console/CLI theo cách **chỉ đọc**, tách network troubleshooting khỏi lỗi ứng dụng.
10. Đánh giá rủi ro bảo mật, độ trễ, đa AZ, downtime khi rollout và tổng chi phí API Gateway/PrivateLink/ALB.

## 2. Ba kiến trúc thường gặp

### 2.1. API công khai, backend riêng tư

Ví dụ người dùng Internet gọi `https://api.example.com/orders`, nhưng backend Spring Boot không có Internet-facing load balancer:

~~~mermaid
flowchart LR
    I["Internet client"] --> A["API Gateway HTTP API hoặc REST Regional"]
    A --> V["VPC Link V2"]
    subgraph VPC["Customer VPC"]
      V --> L["Internal ALB / NLB"]
      L --> S["ECS/EC2: Spring Boot"]
      S --> R["RDS private"]
    end
~~~

**Tính chất:** API endpoint có thể được truy cập từ Internet theo authorization được thiết lập. VPC Link chỉ giữ đoạn **API Gateway → ALB/NLB/backend** trong đường private, không biến frontend API thành private API.

### 2.2. Private REST API chỉ cho client nội bộ

Một EC2 trong VPC hoặc client on-prem qua VPN/Direct Connect gọi API; backend có thể là Lambda integration:

~~~mermaid
flowchart LR
    C["EC2/ECS/on-prem client có đường tới VPC"] --> E["Interface VPCE: execute-api"]
    E --> A["API Gateway REST API, EndpointType PRIVATE"]
    A --> L["Lambda integration"]
    L --> D["S3 / RDS / DynamoDB theo VpcConfig"]
~~~

**Tính chất:** Client phải dùng **Interface Endpoint** thích hợp và thỏa resource policy. Không cần VPC Link chỉ vì API endpoint là PRIVATE hoặc backend là Lambda: API Gateway có native Lambda integration. Nếu Lambda code cần gọi RDS private, **Lambda VpcConfig** giải quyết đoạn đó.

### 2.3. Private REST API + backend HTTP riêng tư

Kết hợp hai cơ chế nếu **cả client lẫn backend** đều cần đường riêng tư:

~~~mermaid
flowchart LR
    C["Internal client"] --> E["execute-api Interface Endpoint"]
    E --> R["API Gateway PRIVATE REST API"]
    R --> V["VPC Link V2"]
    subgraph VPC["Backend VPC"]
      V --> ALB["Internal ALB"]
      ALB --> ECS["ECS/EC2 Spring Boot"]
      ECS --> DB["Private database"]
    end
~~~

**Tính chất:** Đường vào được kiểm soát qua endpoint/resource policy, còn đường ra backend qua VPC Link. Hai thành phần có **IAM, routing, SG, DNS và chi phí riêng**.

## 3. Bảng quyết định: thứ gì đang được đặt riêng tư?

| Thành phần/câu hỏi | Private REST API | API có VPC Link | AppSync Private API |
|---|---|---|---|
| Đang bảo vệ đoạn nào? | **Client → API Gateway** | **API Gateway → VPC backend** | **Client → AppSync GraphQL/Realtime** |
| API type | **REST** | **REST hoặc HTTP**; WebSocket có điều kiện riêng | **AWS AppSync GraphQL** |
| Client phải ở VPC/VPN/DX? | Có đường tới **execute-api VPCE** | **Không nhất thiết**; frontend có thể public | Có đường tới **appsync-api VPCE** |
| Tài nguyên chính | Interface VPCE, API resource policy | VPC Link V2, subnets, SG, ALB/NLB/Cloud Map | AppSync private visibility, Interface VPCE |
| Có bắt buộc VPC Link không? | Không | Có với private HTTP/HTTPS integration | Không |
| Có tự bảo mật backend không? | Không | Không tự thay thế SG/auth/TLS | Không; còn phụ thuộc data sources |
| IAM/authorization | Method auth + resource/endpoint policies | Frontend authorizer + backend auth riêng | GraphQL auth + endpoint policy |
| Vị trí lưu dữ liệu | Bất kỳ data source hợp lệ theo integration | Backend ở private VPC topology | AppSync data sources và AWS services phù hợp |

**Sai lầm phổ biến:** Thấy chữ “private integration” và kết luận toàn bộ API là private. Một HTTP API dùng private ALB qua VPC Link vẫn có **regional public invoke endpoint** nếu bạn không hạn chế client theo biện pháp phù hợp.

## 4. Private REST API: `execute-api` Interface Endpoint

### 4.1. Endpoint type PRIVATE là gì?

API Gateway REST API có ba endpoint types thông dụng: **Regional**, **edge-optimized** và **Private**. Private REST API không cho Internet truy cập trực tiếp qua endpoint public theo cách thông thường; client dùng **Interface VPC Endpoint** (AWS PrivateLink) cho service:

~~~text
com.amazonaws.ap-southeast-1.execute-api
~~~

Ví dụ trên dùng Region Singapore. VPCE tạo network interfaces mang private IP trong các subnets đã chọn. VPC endpoint SG phải cho phép **inbound TCP 443** từ clients. VPC/Route 53 Resolver phải phân giải tên phù hợp tới endpoint nếu dùng Private DNS.

Private REST APIs hỗ trợ giao thức TLS 1.2 và IP address type dualstack theo tài liệu hiện hành. Đây là đặc điểm của **private API endpoint**, không phải cam kết rằng mọi backend đằng sau integration chỉ dùng TLS 1.2.

### 4.2. Một VPCE có thể phục vụ nhiều Private REST APIs

Không cần tạo một interface endpoint riêng cho từng REST API. Một VPC endpoint cho `execute-api` có thể sử dụng với **nhiều private APIs** được cho phép trong account/Region phù hợp. Cần:

1. VPC endpoint hoạt động và endpoint SG đúng.
2. Resource policy của mỗi API cho phép **VPC/VPCE**.
3. Endpoint policy phù hợp với API/method/principal.
4. Method authorization (ví dụ `AWS_IAM`) cho phép caller.
5. DNS/private domain association nếu dùng URL tương ứng.

Một network path hợp lệ **không** đồng nghĩa mọi API tự cho phép mọi caller.

### 4.3. On-premises gọi private API

Người dùng ở datacenter có thể đi tới VPCE qua **AWS Direct Connect hoặc VPN**, với private routing/DNS phù hợp. On-prem client **vẫn phải đi qua Interface VPCE** để gọi private REST API. Việc có VPN kết nối VPC không làm API tự có private IP để kết nối TCP trực tiếp ngoài endpoint.

Để phân giải tên từ on-prem, có thể cần Route 53 Resolver inbound endpoint/forwarding configuration, tùy DNS architecture. VPN/DX cần route tới endpoint ENI private IP, Security Group/NACL mở chiều HTTPS cần thiết.

## 5. Resource policy, endpoint policy và method authorization

Để bảo vệ một private REST API, phân quyền nhiều lớp:

| Lớp | Cấu hình | Nó quyết định |
|---|---|---|
| **Client network** | VPC route/DNS đến Interface VPCE, VPCE SG TCP 443 | Có gửi được traffic tới VPCE không? |
| **VPC endpoint policy** | Policy gắn với VPCE `execute-api` | API/principal/action nào được đi qua endpoint? |
| **REST API resource policy** | `aws:SourceVpce`, `aws:SourceVpc`, principal | Endpoint/VPC nào được phép invoke API này? |
| **Method authorization** | `AWS_IAM`, Cognito/Lambda authorizer hoặc cấu hình phù hợp | User/workload nào được phép gọi method? |
| **Backend security** | VPC Link SG, ALB listener, JWT/service auth | Request từ API Gateway có được backend chấp nhận không? |

### 5.1. Resource policy giới hạn đúng VPC endpoint

Ví dụ **chỉ minh họa**, sau khi thay `vpce-0123456789abcdef0` bằng VPCE thật:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PermitInvocationSubjectToVpceRestriction",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": "execute-api:/*"
    },
    {
      "Sid": "DenyRequestsFromOtherEndpoints",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": "execute-api:/*",
      "Condition": {
        "StringNotEquals": {
          "aws:SourceVpce": "vpce-0123456789abcdef0"
        }
      }
    }
  ]
}
~~~

**Ý nghĩa:** Resource policy cho phép nguồn qua **một VPCE cụ thể**, còn các nguồn khác bị explicit deny. Tuy vậy, `Principal: "*"` sẽ không tự xác thực user đã đăng nhập. Trên methods nhạy cảm, vẫn nên bật **AWS_IAM hoặc authorizer** phù hợp, kết hợp endpoint policy với least privilege.

Trong API Gateway, chuỗi `execute-api:/*` là **cú pháp rút gọn** của resource ARN trong API resource policy; API Gateway mở rộng thành ARN cho API hiện tại khi lưu. Nếu dùng IAM caller policy hoặc VPC endpoint policy, thường cần ARN đầy đủ kiểu:

~~~text
arn:aws:execute-api:ap-southeast-1:111122223333:abc123def4/prod/GET/orders
~~~

Cần thay account/API ID/stage/method/path đúng thực tế. Không copy wildcard toàn bộ các APIs vào identity policy của production client nếu không cần.

### 5.2. `SourceVpce`, `SourceVpc` và địa chỉ gốc

- `aws:SourceVpce` giới hạn **VPC endpoint ID** mà request đi qua.
- `aws:SourceVpc` giới hạn **nguồn VPC**.
- `aws:VpcSourceIp` là condition key thích hợp khi muốn dựa vào **IP gốc của caller** đi qua interface endpoint; `aws:SourceIp` không nhất thiết phản ánh IP ban đầu vì VPCE có thể rewrite source IP.

Không dùng `IpAddress aws:SourceIp` của Internet API làm chính sách IP filtering cho private API mà chưa kiểm tra semantics và dualstack. Với architecture nhiều accounts/VPCs, ưu tiên explicit endpoint/VPC IDs và quản trị lifecycle của chúng.

### 5.3. Endpoint policy không thay resource policy

Một VPC endpoint có thể có policy chỉ cho `GET` trên một API. Điều đó giảm scope của đường mạng nhưng **resource policy** vẫn phải cho phép API được invoke từ nguồn đó, và IAM auth method vẫn cần credentials hợp lệ.

Lưu ý kỹ: chính sách VPC endpoint phân loại principal theo thông tin **SigV4/SigV4a signed request** hoặc request không ký; với bearer token/JWT, endpoint có thể không nhìn thấy IAM principal theo cách bạn dự tính. Nếu muốn giới hạn principal IAM ở endpoint policy, cần chọn `AWS_IAM` và kiểm thử ký request đúng.

### 5.4. Ví dụ endpoint policy giới hạn một API

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "execute-api:Invoke",
      "Resource": [
        "arn:aws:execute-api:ap-southeast-1:111122223333:abc123def4/prod/GET/*"
      ]
    }
  ]
}
~~~

Policy này chỉ minh họa VPCE policy theo resource; **không thay thế** API's resource policy và method authorization. Với custom private domain, có thêm domain-name access association và resource policy riêng theo tài liệu hiện hành.

## 6. Private REST API và DNS: cách gọi từ VPC

### 6.1. Private DNS bật

Khi VPCE `execute-api` bật **Private DNS**, client bên trong VPC có thể gọi API theo invoke URL quen thuộc:

~~~text
https://abc123def4.execute-api.ap-southeast-1.amazonaws.com/prod/orders
~~~

nhưng private resolver trả đường tới **private VPCE**. Nếu method dùng `AWS_IAM` thì request **phải ký SigV4**. `curl` không có chữ ký chỉ thích hợp cho API test được phép dùng authorization khác.

**Cảnh báo DNS:** Bật Private DNS cho `execute-api` có thể khiến **default execute-api URL của public APIs** trong cùng VPC bị resolve về private VPCE, làm lỗi khi gọi public APIs đó. Phương án là dùng custom domain của public API, hoặc tắt private DNS và tạo Route 53 private hosted zone/records cho những private APIs cụ thể theo nhu cầu.

### 6.2. Private DNS tắt hoặc dùng endpoint-specific URL

Có những cách gọi private REST API mà không bật Private DNS:

- VPCE DNS hostname kèm HTTP header `Host` hoặc `x-apigw-api-id` để API Gateway nhận diện API cần invoke.
- URL được tạo sau khi **associate VPC endpoint với private API**, dạng:

~~~text
https://abc123def4-vpce0123456789abcdef0.execute-api.ap-southeast-1.amazonaws.com/prod/orders
~~~

Đây là ví dụ hình thức URL; dùng hostname do API Gateway cung cấp thực tế. Association tạo Route 53 alias để client không cần tự đặt Host header trong tình huống đó.

### 6.3. Kiểm tra bằng các tầng riêng biệt

Từ EC2 trong VPC đã được cấp quyền:

~~~bash
# Chỉ đọc: kiểm tra DNS, không gửi request nghiệp vụ.
nslookup abc123def4.execute-api.ap-southeast-1.amazonaws.com

# Nếu method test được phép truy cập không dùng AWS_IAM,
# lệnh GET này gửi một request thật và có thể phát sinh chi phí.
curl -i --connect-timeout 5 \
  https://abc123def4.execute-api.ap-southeast-1.amazonaws.com/prod/health
~~~

Nếu method dùng `AWS_IAM`, phải ký SigV4 bằng AWS SDK/HTTP client phù hợp; một HTTP `403` từ request `curl` không ký **không chứng minh** mạng đã lỗi. Với on-prem client, trước tiên kiểm tra DNS/route tới VPCE IP và security group.

## 7. VPC Link: kênh API Gateway gọi backend private

**VPC Link** là tài nguyên do API Gateway quản lý để thiết lập **private integration** tới các resources trong VPC. Nó không phải API endpoint cho clients và không phải NAT Gateway. VPC Link V2 tạo ENIs trong những subnets được chọn, dùng security groups được cấu hình và đưa lưu lượng tới integration target.

### 7.1. VPC Link V1 và V2

| Đặc điểm | **VPC Link V1 (legacy)** | **VPC Link V2 (khuyến nghị)** |
|---|---|---|
| Quản lý bằng CLI/API | `aws apigateway create-vpc-link` | `aws apigatewayv2 create-vpc-link` |
| REST private integration | Hỗ trợ với **NLB** | Hỗ trợ **ALB và NLB** |
| HTTP API private integration | Không dùng V1 mới | **ALB, NLB và AWS Cloud Map** |
| Cách cấu hình | Target NLB | **Subnet IDs + Security Group IDs** |
| Đường đi | VPC Link đến NLB theo model V1 | API Gateway-managed ENIs trong VPC theo V2 |
| Khuyến nghị triển khai mới | Không tạo V1 mới nếu V2 phù hợp | Ưu tiên V2 và kiểm tra Regional availability |

**Điểm cần cập nhật so với tài liệu cũ:** REST API **không còn bị giới hạn NLB-only** cho private integration. **REST VPC Link V2** hiện cho phép **ALB trực tiếp**, không nhất thiết dựng NLB phía trước ALB. Nhưng **REST private integration không hỗ trợ AWS Cloud Map target**; Cloud Map là khả năng của HTTP API private integration.

### 7.2. Giới hạn vận hành V2

- VPC Link V2 và load balancer/Cloud Map target/API liên quan phải thuộc **cùng AWS account** theo điều kiện private integrations hiện hành.
- **Subnets và security groups của VPC Link V2 là immutable**: đã tạo thì không sửa trực tiếp. Muốn thay, tạo VPC Link V2 mới và cập nhật integrations.
- VPC Link V2 có `PENDING` rồi `AVAILABLE` khi ENIs được cấp. Chỉ deploy/test backend khi sẵn sàng.
- Nếu **không có traffic trong 60 ngày**, link có thể chuyển `INACTIVE` và API Gateway xóa ENIs. Khi có traffic lại, requests phụ thuộc link có thể thất bại trong lúc API Gateway cấp lại ENIs (vài phút). Cần monitoring và runbook cho môi trường ít dùng.
- Cùng một VPC Link có thể tái sử dụng cho nhiều private integrations phù hợp; không cần tạo link mới cho mỗi route nếu security boundaries/traffic giống nhau.

## 8. HTTP API private integration với ALB/NLB/Cloud Map

HTTP API thường phù hợp khi cần routing/proxy đơn giản, JWT/IAM authorization và chi phí request thấp hơn REST APIs cho những tính năng tương đương. HTTP API **không có endpoint type PRIVATE** giống REST; nó vẫn có thể dùng **VPC Link V2** để kết nối một backend private.

### 8.1. Dùng internal ALB

Một lựa chọn phổ biến cho Spring Boot trên ECS:

~~~mermaid
flowchart LR
    C["Web/mobile client"] --> G["API Gateway HTTP API"]
    G --> V["VPC Link V2"]
    V --> A["Internal ALB: HTTPS listener"]
    A --> T["ECS service: orders-api :8080"]
    T --> D["RDS private"]
~~~

ALB phù hợp khi cần HTTP routing theo host/path, health checks, HTTPS listener, target groups và ứng dụng microservices. API Gateway **không tự bảo đảm ALB targets healthy**. Một target group unhealthy có thể làm API Gateway trả lỗi dù VPC Link status là AVAILABLE.

### 8.2. Dùng NLB

NLB là lựa chọn khi backend dùng TCP/TLS listener, throughput/connection behavior phù hợp hoặc kiến trúc đã dùng NLB. API Gateway vẫn xử lý **HTTP API integration**, nên phải chọn listener/protocol đúng; không suy “có NLB TCP listener” là API Gateway có thể đưa bất kỳ giao thức binary tùy ý.

### 8.3. Dùng AWS Cloud Map

HTTP API private integration có thể trỏ tới **AWS Cloud Map service ARN**; API Gateway dùng `DiscoverInstances` để lấy các private IP/port đã đăng ký và định tuyến đến instances healthy trả về.

- Cloud Map records phải có IP và port attributes phù hợp.
- Với ECS service discovery, cần cấu hình **SRV records** theo hướng dẫn hoặc ECS Service Connect phù hợp.
- Không áp dụng mô hình này cho REST private integration vì REST **không hỗ trợ Cloud Map target**.
- Health status trong Cloud Map và health checks ở ứng dụng vẫn phải được thiết kế cẩn thận.

### 8.4. Stage prefix bị chuyển xuống backend

HTTP API private integration có thể chuyển cả phần **stage** của URL xuống backend. Ví dụ client gọi:

~~~text
GET /test/orders/123
~~~

nhưng Spring Boot backend chỉ expose `/orders/123`. Nếu không dùng mapping, backend có thể nhận `/test/orders/123` và trả `404`.

Khắc phục bằng **parameter mapping** để overwrite integration request path thành:

~~~text
$request.path
~~~

Khi tạo route/integration, kiểm tra mapping và test cụ thể các stages `dev`/`test`/`prod`. Không sửa base path trong Spring Boot để chữa lỗi DNS/SG.

### 8.5. HTTPS từ API Gateway tới backend

Private integration dùng **HTTP theo mặc định** trừ khi cấu hình HTTPS phù hợp. Với HTTP API, dùng integration **`tlsConfig`** (secure server name) và HTTPS listener/target. TLS certificate trên backend phải khớp SNI/hostname nếu kiểm tra tên. **Client HTTPS tới API Gateway không đồng nghĩa backend cũng là HTTPS**.

## 9. REST API private integration với VPC Link V2

REST API có các tính năng như resource/method model, request validation, API keys/usage plans, mapping templates và **Private endpoint type**. Với private integration đến HTTP backend:

- Tạo **VPC Link V2** bằng `apigatewayv2` API/CLI.
- Tạo **REST method integration** bằng `apigateway put-integration` hoặc Console, chọn **VPC_LINK** và cung cấp VPC Link V2 ID.
- Khi dùng **V2**, integration target có thể là **ALB hoặc NLB ARN**; `uri` dùng tên host/URL integration (có ý nghĩa với Host header và TLS verification).
- Khi dùng **V1 legacy**, integration target là **NLB** theo model cũ.
- **REST không hỗ trợ Cloud Map private integration target**.
- Khi cập nhật REST integration/resource policy/method, **redeploy REST API vào stage** để cấu hình được phục vụ theo deployment mới.

### 9.1. Các bước qua Console

1. Tạo hoặc chọn REST API đúng account/Region.
2. Tạo **VPC Link V2** với ít nhất hai subnets khi có thể và SG được phép tới load balancer.
3. Đợi VPC Link `AVAILABLE`.
4. Tạo method như `GET /orders`, integration type **VPC Link** và chọn target ALB/NLB tương ứng.
5. Cấu hình HTTP/HTTPS, integration path, TLS hostname và method authorization.
6. Nếu muốn API chỉ dùng mạng private, cấu hình **REST endpoint type PRIVATE** cùng `execute-api` VPCE/resource policy.
7. Deploy/redeploy đến stage `prod`, test URL, CloudWatch và ALB target health.

### 9.2. Khi nào cần cả VPC Link và `execute-api` VPCE?

| Tình huống | Cần `execute-api` Interface VPCE? | Cần VPC Link? |
|---|---|---|
| Internet client → HTTP API → internal ALB | **Không** | **Có** |
| EC2 private → Private REST API → Lambda | **Có** | **Không** |
| EC2 private → Private REST API → internal ALB | **Có** | **Có** |
| EC2 private → Regional REST API → Lambda | Không để dùng Regional endpoint (cần egress phù hợp) | Không |
| ECS trong VPC → AppSync Private GraphQL | Dùng `appsync-api` endpoint, không phải `execute-api` | **Không** |

Cột “cần” xét **mô hình nêu trong tình huống**. Một ứng dụng có thể có mạng WAN/VPN hoặc những integration khác; đừng suy từ bảng rằng VPC Link là cách duy nhất API Gateway gọi mọi AWS backend.

## 10. VPC Link V2: subnet, SG và đường mạng tới ALB

### 10.1. Đường từ link ENI tới target

Một mô hình:

| Thành phần | Vị trí | Network policy |
|---|---|---|
| VPC Link V2 | Private subnets AZ-a/AZ-b | Link ENIs dùng **SG-VPC-LINK** |
| Internal ALB | Private subnets với các target AZ | ALB SG **inbound TCP 443** từ SG-VPC-LINK |
| ECS/EC2 targets | Private subnets | Target SG **inbound TCP 8080** từ ALB SG |
| RDS | Private database subnets | DB SG **inbound TCP 5432** từ target SG |

Hình dung:

~~~text
API Gateway
  → VPC Link ENI (SG-VPC-LINK, outbound 443)
  → Internal ALB listener :443 (ALB SG inbound from SG-VPC-LINK)
  → Spring Boot target :8080 (target SG inbound from ALB SG)
  → RDS :5432 (DB SG inbound from target SG)
~~~

Security Groups là **stateful**, nên return traffic của kết nối được phép thường tự động đi qua. Network ACL là **stateless**, cần mở chiều đi/trả về và ephemeral ports nếu tổ chức có restrictive NACL. Route tables phải cho phép đường tới private endpoints. Không mở ALB SG inbound `0.0.0.0/0` chỉ vì API Gateway không đến được ALB.

### 10.2. Các kiểm tra quan trọng

1. VPC Link subnets có **đủ IP addresses** cho managed ENIs và không chặn VPC link traffic.
2. ALB thuộc account/VPC topology được private integration hỗ trợ; target listener ARN/ALB ARN đúng.
3. SG gắn VPC Link cho phép outbound tới ALB, ALB SG inbound từ link SG.
4. ALB listener/target group healthy; target SG inbound và ứng dụng lắng nghe đúng port.
5. Nếu dùng HTTPS, backend certificate phù hợp và host/SNI verification đúng.
6. Cloud Map targets có IP/port và health theo tài liệu khi dùng HTTP API.
7. Nếu cross-VPC, route tables/NACL/peering/TGW/PrivateLink phải có **đường thực tế và chiều về**.

### 10.3. Same-account và cross-account backend

Tài liệu AWS yêu cầu các tài nguyên trực tiếp của private integration — API, VPC Link và target **load balancer hoặc Cloud Map service** — thuộc **cùng một AWS account**. Nếu backend nghiệp vụ ở account khác, có thể thiết kế **target ALB/NLB trong account API** rồi kết nối sang account backend bằng AWS PrivateLink, VPC peering hoặc Transit Gateway theo mô hình phù hợp.

Không dùng một load balancer ARN của account B làm integration target trực tiếp cho VPC Link ở account A khi điều kiện API không cho phép. Việc có **Transit Gateway route** không tự bỏ hạn chế control plane same-account.

## 11. API Gateway IAM, JWT, resource policy và backend authentication

### 11.1. Client-side auth

Một private backend không có public IP **không bảo đảm API an toàn** nếu public API cho tất cả caller `ANY /admin/*`. Tùy loại API, chọn:

- **REST API:** `AWS_IAM`, Cognito User Pool authorizer, Lambda authorizer và các phương án phù hợp.
- **HTTP API:** JWT authorizer (OIDC/Cognito), Lambda authorizer hoặc `AWS_IAM`.
- **Private REST API:** bổ sung **resource policy giới hạn VPCE/VPC** và VPCE policy.

Nếu method yêu cầu `AWS_IAM`, IAM caller role phải có `execute-api:Invoke` trên đúng execute-api ARN; client ký SigV4. Với JWT authorization, backend vẫn có thể cần kiểm tra application-level claims/roles do yêu cầu nghiệp vụ.

### 11.2. API Gateway → backend không phải IAM identity thông thường

VPC Link cung cấp **kết nối mạng**, không đồng nghĩa API Gateway tự gửi JWT nghiệp vụ hay tự assume IAM role để gọi một HTTP server private. Để backend chỉ tin API Gateway:

- Restrict network source qua **SG-VPC-LINK → ALB SG**, không mở public access trực tiếp vào ALB.
- Dùng **TLS** cho integration nếu yêu cầu; validate hostname/cert.
- Định nghĩa header/identity forwarding một cách có kiểm soát; backend không tin một header `X-User-Id` nếu client có thể giả mạo header đó.
- Với sensitive operations, dùng service authentication/authorizer và cơ chế signed identity/cross-check phù hợp.
- Nếu ALB listener hay backend tự thực hiện OIDC/auth, thiết kế propagation/redirect và timeout tương thích API Gateway.

### 11.3. Policies có thể chặn theo nhiều lớp

Lỗi `403` có thể đến từ:
- VPCE policy.
- API Gateway resource policy `aws:SourceVpce`/`aws:SourceVpc`.
- Method IAM/JWT/Lambda authorizer.
- Backend application authorization nếu response được proxy.
- WAF hoặc guardrails tùy loại API/config.

Vì vậy phải đọc **API Gateway access logs**, execution logs nơi được hỗ trợ, CloudTrail changes, ALB access logs và app logs để phân biệt nguồn phát sinh. Không sửa tất cả IAM policies theo kiểu wildcard.

## 12. DNS, HTTP request path, Host header và TLS

### 12.1. Hai chiều DNS phải đúng

- **Client → Private API:** resolver trong VPC phải đưa hostname `execute-api` (hoặc private custom domain) tới **VPCE IP**.
- **API Gateway → backend qua VPC Link:** integration phải chỉ đúng ALB/NLB/Cloud Map target. ALB listener rule có thể match **Host/path**, nên sai host/path cũng gây `404` dù TCP connect thành công.

Với một custom domain như `api.internal.example.com`, cần TLS certificate, DNS record/association và API mapping phù hợp. Không mặc định Route 53 private hosted zone tự cho phép mọi VPCE truy cập private custom domain: cần domain-name access association và resource policy theo API Gateway feature hiện hành.

### 12.2. HTTPS cả hai đoạn

~~~text
Client --HTTPS--> API Gateway --HTTP hoặc HTTPS theo integration--> Internal ALB --> Backend
~~~

Nếu tổ chức yêu cầu mã hóa end-to-end, cấu hình **HTTPS ở integration** chứ không chỉ ở API Gateway public/private endpoint. Với HTTP API đặt `tlsConfig` secure server name; với REST VPC Link V2 đặt `uri` chứa host HTTPS theo tài liệu AWS.

Không dùng `insecureSkipVerification` hay tắt hostname verification để chữa lỗi kết nối production. Hãy kiểm tra ACM certificate/SNI/TLS listener và DNS host header.

### 12.3. CORS không thay authorization

Nếu browser client được phép gọi một public API, cấu hình **CORS** đúng origin/method/header. CORS là cơ chế browser, không bảo vệ private backend khỏi request do script/curl gửi. Với private API trên intranet, CORS có thể vẫn cần nếu web app khác origin; phải xử lý preflight và authorization phù hợp.

### 12.4. URL path rewriting

- Với HTTP private integration, **stage path prefix** có thể được gửi xuống backend. Dùng parameter mapping `$request.path` khi cần.
- Với REST private integration, kiểm tra integration request paths/mapping templates và đặc điểm của stage; đừng suy backend luôn nhận nguyên URL người dùng nhập.
- Test dấu `/`, path params, query strings, HTTP method và Host header với ALB listener rules.

## 13. AppSync Private API: giải pháp GraphQL khác API Gateway VPC Link

**AWS AppSync** cung cấp GraphQL API và realtime subscriptions. AppSync hỗ trợ **Private GraphQL APIs**, được gọi từ VPC qua **AWS PrivateLink**; không phải API Gateway REST PRIVATE và không dùng VPC Link của API Gateway để đưa GraphQL requests vào AppSync.

### 13.1. Hai loại AppSync Interface Endpoint

| Endpoint service ở `ap-southeast-1` | Vai trò |
|---|---|
| `com.amazonaws.ap-southeast-1.appsync-api` | **Data plane:** GraphQL queries/mutations/subscriptions và Realtime endpoints |
| `com.amazonaws.ap-southeast-1.appsync` | **Control plane:** quản lý GraphQL APIs, schemas, data sources qua CLI/SDK |

Nếu workload chỉ cần **gọi GraphQL API**, endpoint `appsync-api` là điểm trọng tâm. Không tạo `appsync` control-plane endpoint rồi kỳ vọng GraphQL query sẽ chạy qua nó.

### 13.2. Private visibility phải chọn lúc tạo

Với AWS AppSync GraphQL API, `visibility` có các giá trị như `GLOBAL` hoặc `PRIVATE`; **Private API feature phải được bật khi tạo API** và **không thể chuyển qua lại public/private sau khi API đã tạo** theo tài liệu AWS. Cần quyết định phạm vi truy cập trước khi phát hành, và nếu thay đổi kiến trúc, thiết kế migration sang API mới.

VPC interface endpoint cho AppSync Private API cần ở **cùng account và Region với API**, theo hướng dẫn AppSync hiện hành. Hệ thống VPC đó phải có đúng SG inbound 443, private DNS và IAM/endpoint policy nếu hạn chế người dùng.

### 13.3. AppSync Private DNS có caveat giống API Gateway

Bật Private DNS cho `appsync-api` Interface Endpoint có thể khiến clients trong VPC **không gọi được các AppSync public APIs qua URL do AppSync sinh ra**, vì DNS được điều hướng qua endpoint dành cho private APIs. Theo hướng dẫn AWS, có thể dùng **custom domains** cho public AppSync APIs cần tiếp tục được truy cập từ VPC đó.

AppSync Console Query Editor **không tự vào VPC của bạn** chỉ vì bạn đang dùng AWS Console. Trình duyệt cần đường mạng tới private endpoint, ví dụ client VPN/Direct Connect, mới gọi được private API.

### 13.4. AppSync không tự truy cập mọi private HTTP backend

Một AppSync resolver gọi Lambda, DynamoDB hoặc data source được hỗ trợ qua integration của AppSync. Nếu Lambda resolver cần truy cập RDS hoặc một internal ALB, **Lambda function phải có VPC config/SG/route đúng** cho backend đó. Không dùng VPC Link của API Gateway cho AppSync; hai sản phẩm có mô hình integration khác nhau.

**Chọn AppSync** khi API hợp với GraphQL schema/typed resolvers, queries/mutations/subscriptions và data sources tích hợp. **Chọn API Gateway** khi cần REST/HTTP endpoint routing, proxy và policy/authorizers tương ứng.

## 14. AWS Console: quy trình thiết lập hai phía

### 14.1. Tạo Private REST API (inbound private)

1. Đăng nhập đúng AWS account và Region, chọn **API Gateway → REST API → Build**.
2. Chọn endpoint type **Private**, bật các security options phù hợp.
3. Tạo **Interface VPC Endpoint cho execute-api** trong VPC caller, chọn private subnets và SG inbound TCP 443.
4. Tạo **resource policy** của REST API hạn chế `aws:SourceVpce` hoặc `aws:SourceVpc`; không chỉ dựa vào VPCE SG.
5. Cân nhắc **VPC endpoint policy** và method `AWS_IAM`/authorizer.
6. Associate VPCE với API nếu muốn API Gateway cấp alias DNS chuyên biệt; kiểm tra Private DNS và ảnh hưởng đến public default URLs.
7. Tạo methods/integrations, deploy stage. Dùng client trong VPC/VPN/DX để test.
8. Quan sát CloudWatch access logs, CloudTrail changes và chỉ public hóa domain nếu thực sự thuộc thiết kế (không tự đổi endpoint private thành public).

### 14.2. Tạo HTTP API với private ALB integration

1. Chuẩn bị ECS/EC2 backend và **internal ALB listener/healthy target group** trong account mục tiêu.
2. Mở **API Gateway → VPC links** và tạo **VPC Link V2**; chọn VPC, subnets, SG theo thiết kế.
3. Đợi trạng thái `AVAILABLE`; xác nhận ALB SG cho phép inbound từ VPC Link SG.
4. Tạo **HTTP API → Integration → Private resource**, chọn VPC Link + ALB listener (hoặc NLB/Cloud Map).
5. Tạo route như `GET /orders` hoặc `ANY /{proxy+}` theo routing requirements.
6. Cấu hình `tlsConfig` nếu cần HTTPS, kiểm tra stage prefix/`$request.path`.
7. Đặt JWT/IAM authorizer, CORS, throttling, metrics và access logging thích hợp.
8. Deploy theo stage; gửi request qua đúng client auth, kiểm tra ALB health và backend response.

### 14.3. Chọn REST VPC Link V2 thay V1

Khi triển khai REST mới tới ALB/NLB, chọn **VPC Link V2**; V1 NLB-only là legacy. Khi đã có hệ thống REST dùng V1 hoạt động, migration cần kế hoạch đổi integration, redeploy stage, rollback và kiểm tra khác biệt Host/TLS/path; không xóa V1 khi các stages vẫn phụ thuộc nó.

## 15. AWS CLI chỉ đọc: kiểm tra account, APIs, VPC Links và endpoints

Tất cả lệnh trong phần này là **read-only**. Giả định AWS CLI v2 với profile `dev`, Region `ap-southeast-1`. Thay placeholders `abc123def4`, `vpc-EXAMPLE`, `vpce-EXAMPLE` và các ARN bằng giá trị thật nếu có quyền. Chỉ đọc vẫn có thể có API request charges nhỏ theo chính sách dịch vụ.

### 15.1. Danh tính và REST APIs

~~~bash
aws sts get-caller-identity --profile dev --output json

aws apigateway get-rest-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'items[].{Id:id,Name:name,Endpoint:endpointConfiguration.types,VPCEs:endpointConfiguration.vpcEndpointIds}' \
  --output table

aws apigateway get-rest-api \
  --rest-api-id abc123def4 \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Kiểm tra `endpointConfiguration.types` có `PRIVATE` không và resource policy có ràng buộc nguồn VPCE/VPC không. Nếu API là REGIONAL hoặc EDGE, việc tích hợp tới ALB bằng VPC Link **không khiến endpoint types biến thành PRIVATE**.

### 15.2. HTTP APIs và integrations

~~~bash
aws apigatewayv2 get-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Items[].{Id:ApiId,Name:Name,Protocol:ProtocolType,Endpoint:ApiEndpoint}' \
  --output table

aws apigatewayv2 get-integrations \
  --api-id HTTP_API_ID \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws apigatewayv2 get-routes \
  --api-id HTTP_API_ID \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Tìm integration `ConnectionType = VPC_LINK`, `ConnectionId`, `IntegrationType = HTTP_PROXY` và `IntegrationUri` trỏ tới listener ARN hoặc Cloud Map service ARN phù hợp. `HTTP_API_ID` là placeholder; không tự tạo API nếu chưa có quyền.

### 15.3. VPC Links V2 và legacy V1

~~~bash
# VPC links V2: dùng apigatewayv2 CLI
aws apigatewayv2 get-vpc-links \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Items[].{Id:VpcLinkId,Name:Name,Status:VpcLinkStatus,Subnets:SubnetIds,SGs:SecurityGroupIds}' \
  --output json

# VPC links V1 legacy của REST: dùng apigateway CLI
aws apigateway get-vpc-links \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Hai lệnh khác namespace API nên **không được so tên rồi kết luận một VPC Link V2 đã biến mất** khi `get-vpc-links` của V1 không trả kết quả.

### 15.4. Interface endpoints trong VPC

~~~bash
aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values=vpc-EXAMPLE \
  --profile dev \
  --region ap-southeast-1 \
  --query 'VpcEndpoints[].{Id:VpcEndpointId,Service:ServiceName,Type:VpcEndpointType,PrivateDns:PrivateDnsEnabled,State:State,SubnetIds:SubnetIds,SG:Groups[].GroupId}' \
  --output json
~~~

Tìm service names:

~~~text
com.amazonaws.ap-southeast-1.execute-api  # Private REST API ingress
com.amazonaws.ap-southeast-1.appsync-api  # AppSync Private GraphQL data plane
com.amazonaws.ap-southeast-1.appsync      # AppSync management control plane
~~~

Nếu không thấy execute-api endpoint ở đúng VPC caller, client private REST API không có đường vào theo cơ chế này. Nếu có VPCE nhưng SG inbound 443 không cho caller, kết nối có thể timeout.

### 15.5. ALB/NLB và target health

~~~bash
aws elbv2 describe-load-balancers \
  --profile dev \
  --region ap-southeast-1 \
  --query 'LoadBalancers[].{Name:LoadBalancerName,Scheme:Scheme,Type:Type,Arn:LoadBalancerArn,Vpc:VpcId,Dns:DNSName}' \
  --output json

aws elbv2 describe-listeners \
  --load-balancer-arn ALB_OR_NLB_ARN \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws elbv2 describe-target-health \
  --target-group-arn TARGET_GROUP_ARN \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

**VPC Link AVAILABLE chưa đủ:** target groups của ALB/NLB phải có healthy targets, backend routing đúng Host/path, app đang lắng nghe port phù hợp. Không tắt health checks để “cho thông mạng”.

### 15.6. AppSync APIs

~~~bash
aws appsync list-graphql-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'graphqlApis[].{Name:name,Id:apiId,Visibility:visibility,Urls:uris}' \
  --output json
~~~

`visibility` cho biết private/global theo API metadata. Cần kiểm tra cùng account/Region và VPC endpoints `appsync-api` trước khi kỳ vọng gọi GraphQL qua private network.

## 16. Cấu hình VPC Link V2 bằng CLI: chỉ ví dụ có tác động

**Các lệnh phần này tạo/thay đổi tài nguyên AWS thật**, chỉ chạy sau review/approval trong môi trường lab đúng account. Không dùng placeholder literal ở production.

### 16.1. Tạo VPC Link V2

~~~bash
# CÓ TÁC ĐỘNG: tạo managed ENIs/network capacity và có thể phát sinh phí.
aws apigatewayv2 create-vpc-link \
  --name orders-private-vpc-link \
  --subnet-ids subnet-EXAMPLE-A subnet-EXAMPLE-B \
  --security-group-ids sg-EXAMPLE-VPCLINK \
  --profile dev \
  --region ap-southeast-1
~~~

Sau khi API trả `VpcLinkId`, đọc trạng thái bằng `get-vpc-link`/`get-vpc-links` cho tới `AVAILABLE`. Đừng truyền IDs của hai VPC khác nhau; chọn subnets phù hợp AZ/route và SG đúng VPC.

### 16.2. HTTP API integration vào ALB listener

~~~bash
# CÓ TÁC ĐỘNG: tạo integration nhưng chưa có route/deployment đầy đủ.
aws apigatewayv2 create-integration \
  --api-id HTTP_API_ID \
  --integration-type HTTP_PROXY \
  --integration-method GET \
  --connection-type VPC_LINK \
  --connection-id VPC_LINK_V2_ID \
  --integration-uri arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/orders-internal/EXAMPLE_ALB_ID/EXAMPLE_LISTENER_ID \
  --payload-format-version 1.0 \
  --profile dev \
  --region ap-southeast-1
~~~

Đối với HTTP API, `IntegrationUri` khi dùng ALB/NLB là **listener ARN**, không phải DNS name của target group. Để API nhận được traffic, còn phải tạo route, authorizer, stage/deployment (theo cấu hình auto-deploy), access logs và test. Với HTTPS integration, thêm TLS config theo ARN/secure server name thực tế.

### 16.3. REST API integration vào ALB bằng VPC Link V2

~~~bash
# CÓ TÁC ĐỘNG: thay method integration của REST API.
aws apigateway put-integration \
  --rest-api-id REST_API_ID \
  --resource-id RESOURCE_ID \
  --http-method GET \
  --type HTTP_PROXY \
  --integration-http-method GET \
  --connection-type VPC_LINK \
  --connection-id VPC_LINK_V2_ID \
  --integration-target arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:loadbalancer/app/orders-internal/EXAMPLE_ALB_ID \
  --uri https://orders.internal.example.com:443/orders \
  --profile dev \
  --region ap-southeast-1
~~~

Với REST V2, `--integration-target` là **load balancer ARN** và `--uri` xác định hostname/đường dẫn integration, ảnh hưởng Host header/TLS verification. Cần dùng certificate/ALB listener đúng hostname và redeploy REST API stage để thay đổi có hiệu lực. Mẫu này không tạo resource/method/authorizer hoặc deploy stage cho bạn.

### 16.4. Điều không nên làm

Không tự chạy `create-vpc-link` chỉ để thử một `get-vpc-links`. Không xóa VPC Link V1 cũ nếu còn REST integrations phụ thuộc. Không tạo VPC Link V2 mới trong mỗi CI deployment khi có thể tái sử dụng vì làm tăng ENIs, vận hành và chi phí. Với V2 cần thay subnets/SG, thiết kế rollout link mới rồi chuyển traffic an toàn, không thể update chúng in-place.

## 17. Spring Boot backend: health và đường đi HTTP

Giả sử microservice có endpoint:

~~~java
package com.example.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    @GetMapping("/{orderId}")
    public ResponseEntity<String> findOrder(@PathVariable String orderId) {
        // Ví dụ học tập: chưa truy vấn database hoặc xác thực ownership.
        return ResponseEntity.ok("order=" + orderId);
    }
}
~~~

Một request `GET /orders/42` có thể đi theo tuyến:

~~~text
Client HTTPS
  → API Gateway route GET /orders/{orderId}
  → VPC Link V2
  → ALB listener :443 (Host/path rules)
  → ECS task :8080
  → Spring Boot GET /orders/42
~~~

Nếu API stage `test` bị giữ trong path, backend có thể nhận `/test/orders/42` → `404`. Với HTTP API, cấu hình path parameter mapping thích hợp. Nếu backend chỉ lắng nghe `localhost:8080` thay vì interface của container, ALB target có thể không reach được dù task healthy ở cấp container.

### 17.1. Health checks và readiness

- ALB target group health check nên gọi endpoint an toàn, ví dụ `/actuator/health/readiness` nếu đã cấu hình Spring Boot Actuator.
- Health check path/status/port/SG phải đúng, nếu không target ở trạng thái unhealthy.
- API Gateway có thể báo `5xx` khi integration target không khỏe, timeout hoặc không được kết nối; ứng dụng vẫn có thể báo lỗi `500` nếu code throw exception.
- Backend không nên tin request chỉ dựa vào SG; cần kiểm tra authorization/claims nghiệp vụ khi thích hợp.

### 17.2. Timeouts, keep-alive và idempotency

API Gateway và ALB có integration/idle timeouts tùy loại API, Region và cấu hình. Với request xử lý lâu (ví dụ xuất báo cáo Java vài phút), không giữ một HTTP request đồng bộ qua API Gateway nếu vượt limits; thay bằng:

1. `POST /jobs` tạo một job trong SQS/Step Functions.
2. Backend trả `202 Accepted` kèm job ID.
3. Client poll trạng thái hoặc nhận callback/websocket/event khi job hoàn tất.
4. Kết quả lưu S3 và dùng presigned URL theo quyền/hạn dùng phù hợp.

Việc retry từ client/API integration có thể gửi lại request; implement **idempotency keys**, transaction boundaries và duplicate handling cho POST tạo đơn hàng.

## 18. Observability: API Gateway, VPC Link, ALB và application logs

### 18.1. Các lớp đo lường

| Lớp | Nguồn quan sát | Chỉ số nên theo dõi |
|---|---|---|
| API Gateway | Access logs, metrics, tracing khi được hỗ trợ | `Count`, `4XXError`, `5XXError`, `Latency`, `IntegrationLatency` |
| VPC Link V2 | Status API/Console; ENI/Flow Logs | `PENDING/AVAILABLE/INACTIVE`, network rejects/connection errors |
| VPC network | VPC Flow Logs, Reachability Analyzer khi phù hợp | IP/port, ACCEPT/REJECT, route/SG/NACL |
| ALB/NLB | Target health, access logs, CloudWatch | `HealthyHostCount`, `TargetResponseTime`, 5xx, TCP errors |
| Spring Boot | Actuator/Micrometer/structured logs | HTTP status, DB latency, correlation ID, exceptions |
| IAM/control-plane | CloudTrail | Ai sửa API/resource policy/VPC Link/SG/target? |

Một `504 Gateway Timeout` không tự cho biết lỗi tại API Gateway, VPC Link, ALB hay backend. Hãy nối **request ID**, timestamp, route/path, status, integration latency, ALB trace header và application log tương ứng.

### 18.2. Security logging

- Không ghi `Authorization` bearer/JWT hoặc API keys nguyên văn vào access log.
- Mask request bodies, credentials, PII và secrets.
- Giới hạn CloudWatch retention và quyền xem logs.
- CloudTrail dùng để audit control-plane changes, không phải thay application access logs.
- Bật metrics/alarms cho VPC Link `INACTIVE` và backend target health đối với môi trường ít traffic.

## 19. Troubleshooting theo triệu chứng

| Lỗi/triệu chứng | Nhóm nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Private REST API `403` | Resource policy không cho VPCE/VPC, endpoint policy hoặc IAM auth sai | Đọc `SourceVpce`, VPCE policy, method authorization, SigV4 |
| HTTP API public vẫn gọi được backend private | Đây là hành vi **đúng** của private integration | Muốn private frontend phải đổi architecture/chọn Private REST API |
| DNS của private API trả public IP | Private DNS/Resolver/VPCE association sai | VPC DNS attributes, VPCE PrivateDnsEnabled và hostname |
| Client VPC không gọi được public execute-api URL | Bật Private DNS trên execute-api VPCE làm đổi DNS resolution | Dùng public custom domain hoặc split private DNS strategy |
| VPCE TCP 443 timeout | Endpoint SG, subnet/NACL, route hoặc DNS | SG inbound từ client, VPCE ENI IP/route |
| `get-vpc-links` V1 không thấy link V2 | Dùng sai CLI namespace | `apigatewayv2 get-vpc-links` |
| VPC Link V2 ở `PENDING` | ENIs đang tạo, subnet/IP/permissions | Link status, subnet capacity, VPC SG |
| VPC Link V2 `INACTIVE` | 60 ngày không có traffic | Chờ reprovision, theo dõi status; chuẩn bị first-request behavior |
| API Gateway integration `502` | TLS Host mismatch, ALB reset, integration cấu hình sai | Integration URI, secure server name, ALB listeners/cert/logs |
| API Gateway integration `504` | Backend timeout, SG/route/NACL sai, ALB không trả kịp | Integration latency, Flow Logs, ALB target health, backend timeouts |
| Spring Boot trả `404` từ private integration | Stage prefix `/test` hoặc path mapping sai | HTTP API `$request.path` mapping, ALB path rules |
| ALB targets unhealthy | Target SG/port/readiness/TLS sai | Target group status, SG target inbound, health endpoint |
| NLB/ALB 5xx nhưng VPC Link AVAILABLE | Link sống nhưng backend không khỏe | ALB/NLB metrics, target logs, application |
| REST VPC Link V2 không dùng được Cloud Map | REST không hỗ trợ Cloud Map target | Dùng ALB/NLB hoặc HTTP API |
| Không sửa được subnets/SG của VPC Link V2 | V2 immutable | Tạo link mới và đổi integrations |
| VPC Link target khác AWS account | Same-account restriction | Dùng LB cùng account và cross-account PrivateLink/TGW/peering |
| HTTP API backend HTTPS cert mismatch | `tlsConfig`/SNI/cert sai | TLS hostname, listener, ACM/trust chain |
| Private API gọi từ on-prem bị lỗi | Không có route/DNS tới VPCE | VPN/DX routes, Resolver inbound, endpoint SG |
| AppSync private queries không đến endpoint | Thiếu `appsync-api` data-plane endpoint | AppSync visibility, VPCE service name, Private DNS |
| AppSync public API không dùng được từ VPC | Private DNS của `appsync-api` ghi đè default API hostname | Custom domain cho public AppSync hoặc thiết kế DNS khác |
| Chi phí tăng dù backend không public | VPCE/VPC Link/ALB/CloudWatch/egress phí độc lập | Cost Explorer, tài nguyên idle, request volume |

### 19.1. Trình tự điều tra bảy bước

1. **Xác định API type/endpoint:** REST PRIVATE, REST REGIONAL hay HTTP API? AppSync PRIVATE hay GLOBAL?
2. **Xác định đoạn đang lỗi:** client → VPCE/API Gateway hay API Gateway → VPC Link → ALB, hoặc AppSync → resolver/Lambda?
3. **Kiểm tra DNS/TLS:** hostname đúng, VPCE Private DNS có bật và ảnh hưởng public domains không?
4. **Kiểm tra authorization:** API resource policy/VPCE policy/method IAM/JWT có khớp caller?
5. **Kiểm tra VPC Link:** V1 hay V2, `AVAILABLE`/`INACTIVE`, subnets/SG đúng?
6. **Kiểm tra backend:** listener target ARN, SG, NACL, target health, path mapping, TLS, app readiness.
7. **Đối chiếu logs/metrics:** API Gateway access/integration logs, ALB target/flow logs, CloudTrail và Spring Boot logs.

Không giải quyết `403` do resource policy bằng cách mở ALB SG; cũng không giải quyết `504` do backend timeout bằng cách cấp IAM administrator.

## 20. Độ sẵn sàng, bảo mật và chi phí

### 20.1. Khả năng phục hồi theo AZ

- VPC Link V2 chọn subnets ở **nhiều AZ** nếu có thể để tránh single-AZ dependency.
- ALB/NLB cần listener và healthy targets đa AZ; ECS service nên có replicas và target group checks.
- Interface VPC endpoints `execute-api`/`appsync-api` nên có endpoint ENIs ở AZs clients dùng, SG và DNS đúng.
- Với HTTP API/REST, cấu hình retry behavior/idempotency, circuit breakers và backend DB pool theo SLO.
- Nếu backend chạy multi-Region, cần chiến lược DR/Route 53/API custom domain, replication và kiểm thử riêng; một VPC Link không tự kết nối mọi Regions.

### 20.2. Chi phí cần tính riêng

| Hạng mục | Lý do có thể phát sinh phí |
|---|---|
| API Gateway REST/HTTP | Requests, payload, data transfer, caching/other features nếu dùng |
| Interface VPC Endpoint | Endpoint-hours theo AZ, data processing |
| VPC Link | Theo loại link/feature và biểu phí API Gateway/VPC networking hiện hành |
| ALB/NLB | LB-hours, LCU/NLCU, processed traffic |
| ECS/EC2 backend | Task/instance CPU/RAM và storage |
| CloudWatch Logs / tracing | Ingestion, retention, metrics và trace spans |
| Route 53/ACM/private DNS | Hosted zones/queries, cert-related services tùy loại |
| Inter-AZ/cross-account networking | Data transfer và PrivateLink/TGW/NAT nếu topology dùng |

Một **API public + VPC Link** có thể rẻ/đơn giản hơn “Private REST API + interface endpoint + VPC Link” nếu yêu cầu không cần private frontend. Ngược lại, hệ thống nội bộ có yêu cầu data perimeter nghiêm ngặt có thể chấp nhận chi phí/độ phức tạp thêm để chỉ cho phép VPCE. Không chọn theo mỗi giá request, cần tính tổng TCO mạng, security và vận hành.

### 20.3. Quy tắc bảo mật thực tế

1. IAM roles/authorizers tối thiểu; không mở `execute-api:Invoke` cho tất cả principals trừ khi đã có lớp xác thực khác được duyệt.
2. Private REST API dùng **resource policy với `SourceVpce`/`SourceVpc`**, VPCE policy và SG; kiểm tra explicit deny.
3. Private integration dùng **SG VPC Link → ALB SG** và TLS end-to-end khi phù hợp.
4. Không public hóa database/private ALB chỉ để API Gateway hoạt động.
5. Kiểm soát DNS/Route 53/ACM certificates, domain-name access associations.
6. Ghi logs đã loại bỏ tokens/PII, cảnh báo lỗi 5xx/latency và kiểm toán mọi change.
7. Dùng IaC/approval, thay VPC Link V2 bằng link mới khi cần đổi subnet/SG thay vì thao tác trực tiếp không hỗ trợ.

## 21. Bài thực hành chỉ đọc: nhận diện kiến trúc và nguyên nhân lỗi

### 21.1. Bối cảnh

Một hệ thống Spring Boot trên ECS ở private subnets có internal ALB. Client Internet phải gọi API `api.example.com`, nhưng không được truy cập thẳng ALB. Đồng thời, ứng dụng quản trị nội bộ phải có private endpoint dành riêng cho nhân viên qua VPN.

Hãy vẽ hai tuyến:

- **Tuyến khách hàng:** public **HTTP API + VPC Link V2 → internal ALB → ECS**; dùng JWT/IAM authorizer và security controls.
- **Tuyến nội bộ:** **Private REST API → execute-api VPCE → VPC Link V2 → internal ALB → ECS** nếu backend HTTP riêng tư; hoặc native Lambda integration nếu hệ thống quản trị được triển khai bằng Lambda.

Không cần tạo API/VPC Link trong lab, tránh phát sinh chi phí.

### 21.2. Phần A — Đọc API type

~~~bash
aws sts get-caller-identity --profile dev

aws apigateway get-rest-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'items[].{Id:id,Name:name,Endpoint:endpointConfiguration.types}' \
  --output table

aws apigatewayv2 get-apis \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Items[].{Id:ApiId,Name:Name,Type:ProtocolType}' \
  --output table
~~~

Ghi API IDs, REST/HTTP types và trạng thái endpoint. Nếu REST endpoint type không phải PRIVATE, việc có VPC Link có làm API thành private không? **Không.**

### 21.3. Phần B — Đọc VPC Links và endpoints

~~~bash
aws apigatewayv2 get-vpc-links \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws ec2 describe-vpc-endpoints \
  --filters Name=service-name,Values=com.amazonaws.ap-southeast-1.execute-api \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Chỉ ra VPC Link V2 subnets/SG và VPCE `execute-api` subnets/SG. Hai nhóm ENIs này có nhiệm vụ giống nhau không? **Không:** VPC Link thuộc đoạn tới backend; execute-api VPCE thuộc đoạn client vào private REST API.

### 21.4. Phần C — Kiểm tra ALB/Target

~~~bash
aws elbv2 describe-load-balancers \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws elbv2 describe-target-health \
  --target-group-arn TARGET_GROUP_ARN \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Nếu VPC Link `AVAILABLE` mà targets unhealthy, bạn sẽ kiểm tra ALB SG/target SG, listener, readiness hay tạo thêm execute-api VPCE? **Kiểm tra backend first**, vì vấn đề thuộc outbound integration.

### 21.5. Phần D — Phân biệt ba lỗi

| Kết quả | Chẩn đoán nên ưu tiên |
|---|---|
| `403` khi gọi Private REST API từ EC2 | Resource policy `SourceVpce`, VPCE policy, IAM method auth/SigV4 |
| `504` từ API Gateway, ALB không ghi request | VPC Link networking, SG/NACL, target/Host/TLS |
| `404` từ Spring Boot có log path `/test/orders/42` | HTTP API stage-prefix mapping đến backend |

Đưa ra danh sách phép kiểm **chỉ đọc** cho từng lỗi, không mở SG `0.0.0.0/0` hoặc wildcard IAM để thử.

### 21.6. Phần E — AppSync

Nếu phòng phân tích chuyển API quản trị sang GraphQL:

1. Chọn **AppSync Private API khi tạo** và giải thích tại sao không thể bật sau đó cho API đã công bố.
2. Chọn **`appsync-api` Interface Endpoint** cho queries/mutations/subscriptions.
3. Chỉ tạo `appsync` management endpoint nếu CLI/SDK trong VPC cần quản trị API qua đường riêng tư.
4. Nếu AppSync resolver gọi Lambda truy vấn RDS, Lambda cần **VpcConfig** của chính nó; **VPC Link không phải tính năng data source của AppSync**.
5. Kiểm tra ảnh hưởng Private DNS tới AppSync public default URLs trong cùng VPC.

## 22. Câu hỏi tự đánh giá

1. Private REST API và API Gateway private integration bảo vệ hai đoạn mạng nào?
2. HTTP API có endpoint type PRIVATE giống REST không?
3. Một HTTP API sử dụng VPC Link đến internal ALB có thể được gọi từ Internet không?
4. Service name của execute-api Interface VPC Endpoint tại Region Singapore là gì?
5. Private REST API có cần VPC Link nếu integration chỉ gọi Lambda không?
6. API resource policy `aws:SourceVpce` hạn chế điều gì?
7. Vì sao VPCE policy không thay thế method IAM/JWT authorizer?
8. Tại sao bật Private DNS cho `execute-api` có thể làm public execute-api URL trong VPC không dùng được?
9. VPC Link V1 khác V2 ở mục đích, CLI và loại target ra sao?
10. REST API VPC Link V2 hiện có cần đặt NLB trước ALB không?
11. HTTP API private integration hỗ trợ Cloud Map, nhưng REST API có hỗ trợ Cloud Map target không?
12. Tại sao chọn SG inbound TCP 443 của ALB từ SG của VPC Link thay vì `0.0.0.0/0`?
13. Khi VPC Link V2 chuyển `INACTIVE` sau 60 ngày không traffic, chuyện gì xảy ra với ENIs?
14. Có sửa subnets/SG của VPC Link V2 in-place được không?
15. HTTP API stage `test` có thể làm backend nhận path nào khác dự kiến?
16. Cần cấu hình gì để API Gateway → backend dùng HTTPS?
17. Vì sao Backend `404` và Private API `403` phải được chẩn đoán khác nhau?
18. Đường private AppSync GraphQL dùng endpoint service `appsync` hay `appsync-api`?
19. Có thể đổi AppSync API từ GLOBAL sang PRIVATE sau khi API đã tạo không?
20. AppSync resolver gọi Lambda truy vấn RDS cần cấu hình VPC Link hay Lambda VpcConfig?
21. Vì sao cross-account ALB/VPC Link private integration phải tuân thủ same-account constraint của direct target?
22. Những chi phí nào còn phát sinh khi backend không có public IP?

### Định hướng đáp án

- **Private REST API:** inbound qua `execute-api` VPCE, resource policy, endpoint policy và authorizer.
- **VPC Link V2:** outbound private integration tới **ALB/NLB (REST hoặc HTTP)** hoặc **Cloud Map (HTTP)**, tạo ENIs trong VPC; link V2 immutable, có thể INACTIVE sau 60 ngày.
- **AppSync Private API:** GraphQL/Realtime qua `appsync-api` VPCE, visibility phải chọn lúc tạo; khác API Gateway VPC Link.
- **Vận hành:** tách DNS, authentication, network, TLS, backend target health, stage mapping, request logs, chi phí.

## 23. Tài liệu AWS chính thức

1. [Private REST APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-private-apis.html) — Endpoint PRIVATE và Interface VPCE.
2. [Create a private API](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-private-api-create.html) — Resource policy, VPCE association, deployment.
3. [Invoke a private API](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-private-api-test-invoke-url.html) — DNS, invocation và private custom domains.
4. [API Gateway resource policy examples](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-resource-policies-examples.html) — `SourceVpc`, `SourceVpce`, `VpcSourceIp`.
5. [VPC endpoint policies for private APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-vpc-endpoint-policies.html) — Endpoint access controls.
6. [Private integrations for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/private-integration.html) — VPC Link V2 to ALB/NLB và V1 legacy.
7. [Set up VPC links V2](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-vpc-links-v2.html) — Creation, subnet/SG immutability, INACTIVE sau 60 ngày.
8. [Create REST private integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-private-integration.html) — REST `put-integration` và `integration-target`.
9. [HTTP API private integrations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html) — ALB/NLB/Cloud Map, path mapping.
10. [HTTP API to ECS private integration tutorial](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-private-integration.html) — Ví dụ hoàn chỉnh từ ALB/ECS.
11. [Deploy REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-deploy-api.html) — Deployment, stages, update propagation.
12. [AWS CLI apigatewayv2 create-vpc-link](https://docs.aws.amazon.com/cli/latest/reference/apigatewayv2/create-vpc-link.html) — Lệnh tạo V2.
13. [AWS CLI apigatewayv2 create-integration](https://docs.aws.amazon.com/cli/latest/reference/apigatewayv2/create-integration.html) — Lệnh tạo HTTP integration.
14. [AWS CLI apigateway put-integration](https://docs.aws.amazon.com/cli/latest/reference/apigateway/put-integration.html) — REST integration.
15. [AWS AppSync Private APIs](https://docs.aws.amazon.com/appsync/latest/devguide/using-private-apis.html) — GraphQL/Realtime, AppSync endpoints và visibility.
16. [AppSync GraphqlApi API](https://docs.aws.amazon.com/appsync/latest/APIReference/API_GraphqlApi.html) — `visibility` GLOBAL/PRIVATE.
17. [API Gateway Private API and integration best practices whitepaper](https://docs.aws.amazon.com/whitepapers/latest/best-practices-api-gateway-private-apis-integration/best-practices-api-gateway-private-apis-integration.html) — Kiến trúc và security/operations.
18. [VPC Interface endpoints through AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html) — Interface endpoints, SG, Private DNS.
19. [Security groups for VPC](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) — Stateful network policy.
20. [ALB target group health checks](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-health-checks.html) — Health status.
21. [API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/) — Requests và features.
22. [AWS PrivateLink pricing](https://aws.amazon.com/privatelink/pricing/) — VPCE endpoint-hours/data processing.
23. [Elastic Load Balancing pricing](https://aws.amazon.com/elasticloadbalancing/pricing/) — ALB/NLB charges.

> **Ghi nhớ cuối bài:** Để xây API an toàn, hãy vẽ **hai mũi tên riêng**: **client → API** và **API → backend**. Nếu cần giữ *frontend* nội bộ, dùng **Private REST API + execute-api VPCE** (hoặc AppSync Private API khi là GraphQL). Nếu cần giữ *backend* nội bộ, dùng **VPC Link V2 + private ALB/NLB/Cloud Map theo API type**. Khi cần cả hai, kết hợp đúng các cơ chế, kiểm tra IAM/resource policy, SG, DNS, TLS, stage path, target health, logs và chi phí trước khi phát hành.

