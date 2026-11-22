# Nạp log, bảo mật và quan sát OpenSearch domain

## Mục tiêu học tập

Amazon OpenSearch Service cung cấp các domain được quản lý để lưu trữ, tìm kiếm và phân tích dữ liệu. Trong một hệ thống production, tạo domain và gửi document vào index mới chỉ là bước đầu. Nhóm vận hành còn phải đưa log đến đúng nơi, chuẩn hóa dữ liệu, kiểm soát quyền truy cập, bảo vệ dữ liệu khi truyền và lưu trữ, đồng thời quan sát trạng thái cluster để phát hiện sự cố trước khi người dùng bị ảnh hưởng.

Bài học thuộc chương **Phân tích và tìm kiếm** của module CLOUD_PROVIDERS_AWS. Nội dung tập trung vào vòng đời vận hành một OpenSearch domain: thu thập log ứng dụng và log hệ thống, bật log publishing, cấu hình audit và slow logs, thiết kế bảo mật theo nhiều lớp, theo dõi metrics bằng CloudWatch và xử lý các tình huống thường gặp.

Sau bài học, người học có thể:

- Phân biệt log của chính OpenSearch domain với log ứng dụng được nạp vào domain.
- Chọn CloudWatch Logs subscription, Amazon Data Firehose, OpenSearch Ingestion hoặc OpenTelemetry Collector cho từng luồng dữ liệu.
- Chuẩn hóa timestamp, field, index và retention trước khi ingest.
- Bật application/error logs, search slow logs, index slow logs và audit logs.
- Cấu hình CloudWatch Logs resource policy để OpenSearch Service ghi log.
- Giải thích domain access policy, IAM identity policy và fine-grained access control.
- Thiết kế VPC access, security group, HTTPS, node-to-node encryption và encryption at rest.
- Tạo dashboard, CloudWatch alarms và truy vấn CloudWatch Logs Insights.
- Dùng CloudTrail và EventBridge để theo dõi thay đổi cấu hình.
- Chẩn đoán lỗi ingest, authorization, shard, storage, JVM pressure và query latency.

## 1. Bức tranh tổng thể: ingest, secure và observe

Một OpenSearch domain thường nằm ở cuối hoặc gần cuối pipeline dữ liệu. Log có thể đến từ ứng dụng, container, máy chủ, load balancer, hệ điều hành, dịch vụ AWS hoặc chính OpenSearch. Trước khi được index, dữ liệu nên được lọc, chuẩn hóa, bổ sung metadata và loại bỏ thông tin nhạy cảm không cần thiết.

Có hai luồng log cần phân biệt:

- **Log được ingest vào domain:** sự kiện ứng dụng, access log, audit log từ hệ thống khác, log container, log mạng hoặc telemetry. Đây là dữ liệu mà đội vận hành muốn tìm kiếm và phân tích.
- **Log phát sinh từ domain:** lỗi nội bộ OpenSearch, slow logs và audit logs của chính domain. OpenSearch Service có thể publish các loại log này sang Amazon CloudWatch Logs.

Không nên đưa toàn bộ log của domain trở lại chính domain đó theo cách không kiểm soát. Nếu domain đang lỗi do disk hoặc heap pressure, ingest thêm log với tốc độ cao có thể làm tình hình nghiêm trọng hơn. Nên có CloudWatch Logs hoặc S3 làm nơi quan sát và lưu trữ độc lập.

~~~mermaid
flowchart LR
    A[Applications / ECS / EKS / EC2] --> B[CloudWatch Logs / OTel]
    C[ALB / VPC / AWS services] --> B
    B --> D[Subscription / Firehose / OpenSearch Ingestion]
    D --> E[Parse, filter, enrich, normalize]
    E --> F[OpenSearch domain]
    F --> G[OpenSearch Dashboards / Search]
    F --> H[CloudWatch metrics]
    F --> I[Domain error, slow, audit logs]
    I --> J[CloudWatch Logs]
    H --> K[CloudWatch alarms / dashboards]
    J --> K
    L[CloudTrail / EventBridge] --> K
~~~

Một kiến trúc tốt giữ được ba đặc tính: dữ liệu đi vào theo pipeline có thể quan sát, quyền truy cập có thể giải thích, và khi domain gặp sự cố vẫn còn một kênh log độc lập để điều tra.

## 2. Phân loại log và telemetry

Log là bản ghi sự kiện có timestamp. Metrics là chuỗi số đo theo thời gian. Trace mô tả hành trình của một request qua nhiều service. Ba tín hiệu bổ sung cho nhau:

| Tín hiệu | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Logs | Điều gì đã xảy ra? | HTTP 500, lỗi parse JSON, user đăng nhập thất bại |
| Metrics | Mức độ và xu hướng ra sao? | Request rate, p95 latency, JVM memory pressure |
| Traces | Request đi qua thành phần nào và mất thời gian ở đâu? | Checkout gọi inventory, payment và fulfillment |

Log ứng dụng thường cần các field như timestamp, severity, service, environment, request ID, trace ID, host/container, message và error stack. Tránh chỉ ghi một chuỗi text tự do vì việc lọc theo service, status code hoặc trace ID sẽ khó hơn.

Đối với log bảo mật, cần xác định rõ dữ liệu nào được phép ghi. Password, access token, session cookie, private key, dữ liệu thanh toán và thông tin cá nhân không nên xuất hiện nguyên vẹn trong message hoặc request body. Hãy redaction tại nguồn hoặc processor trước khi dữ liệu đi vào OpenSearch.

## 3. Chọn đường ingest log phù hợp

Không có một pipeline duy nhất phù hợp cho mọi nguồn log.

| Nguồn dữ liệu | Cách ingest thường dùng | Khi nào phù hợp |
|---|---|---|
| CloudWatch Logs | Subscription filter tới Lambda, Kinesis Data Streams hoặc Data Firehose | Log đã tập trung trong CloudWatch |
| Ứng dụng trên EC2/ECS/EKS | Fluent Bit, OpenTelemetry Collector hoặc agent phù hợp | Cần thu thập log từ file, stdout hoặc telemetry |
| Log và trace theo OpenTelemetry | OTel Collector → OpenSearch Ingestion | Muốn chuẩn hóa telemetry theo OTLP |
| Streaming event | Amazon Data Firehose hoặc Kinesis Data Streams kết hợp consumer | Lưu lượng liên tục, cần buffering và retry |
| Batch file | S3, Lambda hoặc pipeline ingest theo lịch | Dữ liệu lịch sử, archive hoặc backfill |
| AWS service có tích hợp sẵn | Tích hợp trực tiếp của dịch vụ hoặc Data Firehose | Muốn giảm thành phần tự quản lý |

Amazon OpenSearch Ingestion là data collector serverless được quản lý, xây dựng trên Data Prepper. Pipeline có thể nhận log, metrics và traces, sau đó filter, enrich, transform, normalize và chuyển đến OpenSearch domain hoặc OpenSearch Serverless collection. Dịch vụ tự quản lý hạ tầng pipeline và mở rộng trong giới hạn capacity đã cấu hình.

Data Firehose phù hợp với luồng streaming có buffering, retry và delivery destination được hỗ trợ. CloudWatch Logs subscription phù hợp khi log đã nằm trong CloudWatch Logs và cần chuyển tiếp gần thời gian thực. OTel Collector phù hợp khi ứng dụng đã phát telemetry theo chuẩn OpenTelemetry.

### 3.1. Khi nào nên dùng CloudWatch Logs subscription?

Nếu ứng dụng đã ghi log vào CloudWatch Logs, subscription filter có thể chuyển sự kiện gần thời gian thực đến một destination được hỗ trợ. Destination có thể là Lambda, Kinesis Data Streams hoặc Amazon Data Firehose tùy kiến trúc.

Subscription filter có thể lọc theo pattern để giảm lượng dữ liệu. Ví dụ chỉ chuyển log có ERROR hoặc log từ một service cụ thể. Subscription delivery có ngữ nghĩa at-least-once; duplicate event có thể xuất hiện. Pipeline downstream nên có event ID, request ID hoặc khóa idempotency để phát hiện bản ghi trùng khi cần.

Subscription filter hỗ trợ log group thuộc Standard log class. Nếu log group đang dùng Infrequent Access, cần kiểm tra giới hạn hiện hành trước khi thiết kế subscription.

### 3.2. Khi nào nên dùng OpenSearch Ingestion?

Dùng OpenSearch Ingestion khi cần một pipeline được quản lý để xử lý dữ liệu trước khi index. Data Prepper có thể:

- Parse JSON, Grok hoặc định dạng log khác.
- Chuyển đổi tên field và timestamp.
- Bổ sung metadata từ source hoặc enrichment processor.
- Lọc event không cần thiết.
- Chia route theo loại dữ liệu.
- Chuyển log và trace đến OpenSearch.
- Xuất metrics theo pipeline observability phù hợp.

Pipeline có thể kết nối VPC để tăng kiểm soát mạng. IAM principal gửi dữ liệu cần quyền ingest trên pipeline ARN, thường là action osis:Ingest. Nếu pipeline xuất metrics sang Amazon Managed Service for Prometheus, principal còn cần aps:RemoteWrite trên workspace tương ứng.

Ví dụ pipeline Data Prepper đơn giản nhận OTLP logs, chuẩn hóa timestamp và ghi vào domain:

~~~yaml
version: "2"
checkout-logs:
  source:
    otlp:
      logs_path: "/checkout/v1/logs"
  processor:
    - copy_values:
        entries:
          - from_key: "time"
            to_key: "@timestamp"
  sink:
    - opensearch:
        hosts:
          - "https://orders-search.example.ap-southeast-1.es.amazonaws.com"
        index_type: log-analytics-plain
        aws:
          serverless: false
          region: ap-southeast-1
          sts_role_arn: "arn:aws:iam::123456789012:role/osis-to-orders-search"
~~~

Đây là cấu hình minh họa. Thay endpoint và role ARN bằng giá trị của môi trường. Pipeline role cần được phép assume và ghi vào domain; nếu domain dùng FGAC, ánh xạ role đó sang OpenSearch role có quyền ghi vào index pattern do pipeline tạo.

OTel Collector có thể export logs đến pipeline bằng SigV4:

~~~yaml
extensions:
  sigv4auth:
    region: ap-southeast-1
    service: osis

exporters:
  otlphttp/osis-logs:
    logs_endpoint: "https://pipeline-endpoint/v1/logs"
    auth:
      authenticator: sigv4auth

service:
  extensions: [sigv4auth]
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/osis-logs]
~~~

Không nên dùng pipeline chỉ để chuyển nguyên payload không chuẩn hóa nếu có thể sửa định dạng tại nguồn. Chuẩn hóa sớm giúp index mapping nhất quán và giảm chi phí lưu trữ.

## 4. Chuẩn hóa log trước khi index

Một event log có thể dùng cấu trúc JSON như sau:

~~~json
{
  "@timestamp": "2026-11-20T06:30:12.456Z",
  "severity": "ERROR",
  "service": "checkout",
  "environment": "production",
  "host": "checkout-7d9c8",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-7f9a21",
  "http": {
    "method": "POST",
    "route": "/orders",
    "status_code": 500
  },
  "message": "Unable to reserve inventory",
  "error": {
    "type": "InventoryTimeout",
    "message": "Inventory service did not respond before deadline"
  }
}
~~~

Các nguyên tắc quan trọng:

- Dùng UTC và định dạng timestamp nhất quán.
- Tách severity, service, environment, status code và trace ID thành field riêng.
- Dùng keyword cho field dùng để filter/group và numeric/date cho field cần range query.
- Không tạo một field mới cho mỗi request hoặc mỗi user nếu không cần thiết.
- Giữ mapping ổn định bằng index template.
- Chọn index naming convention theo service và thời gian.
- Đặt retention theo giá trị điều tra, yêu cầu pháp lý và chi phí.
- Xử lý payload lớn hoặc stack trace dài bằng chiến lược phù hợp, tránh một document quá lớn.

Nếu timestamp không được parse đúng, OpenSearch có thể index event theo thời gian ingest hoặc coi timestamp là text. Dashboard theo time range khi đó sẽ cho kết quả sai hoặc bỏ sót dữ liệu.

## 5. Index template, rollover và retention

Với log có tốc độ ingest liên tục, không nên tạo một index vĩnh viễn duy nhất cho mọi dữ liệu. Có thể dùng index theo ngày hoặc data stream/rollover phù hợp phiên bản OpenSearch và loại workload.

Ví dụ index template cho log của checkout:

~~~json
{
  "index_patterns": ["logs-checkout-*"],
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "severity": { "type": "keyword" },
        "service": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "trace_id": { "type": "keyword" },
        "request_id": { "type": "keyword" },
        "message": { "type": "text" },
        "http": {
          "properties": {
            "status_code": { "type": "integer" },
            "method": { "type": "keyword" }
          }
        }
      }
    }
  }
}
~~~

Số primary shard ở ví dụ chỉ mang tính minh họa. Chọn shard count dựa trên kích thước index, ingest rate, query pattern và số data node. AWS đưa ra khoảng tham khảo 10–30 GiB cho shard của search workload và 30–50 GiB cho shard của log workload; 50 GiB nên được xem là mức trần cần lập kế hoạch tăng trưởng. Thông thường nên có ít nhất một replica để tăng redundancy và read capacity. Quá nhiều shard làm tăng overhead heap và cluster state; quá ít shard có thể làm một shard quá lớn hoặc giảm khả năng song song hóa.

Index State Management (ISM) có thể tự động rollover, chuyển index sang warm/cold tier nếu kiến trúc hỗ trợ, read-only hoặc delete sau thời hạn. Chính sách retention cần được thống nhất với chủ dữ liệu và yêu cầu audit. Đừng giữ mọi log vô thời hạn chỉ vì storage đang còn trống.

## 6. Ba lớp bảo mật của OpenSearch domain

Bảo mật OpenSearch Service có ba lớp chính:

1. **Network:** quyết định request có thể đến endpoint hay không.
2. **Domain access policy:** quyết định principal được gọi URI hoặc API nào trên domain.
3. **Fine-grained access control (FGAC):** xác thực user và quyết định quyền ở cluster, index, document và field level.

Ngoài ba lớp này, IAM identity policy kiểm soát quyền quản trị domain và AWS API; encryption bảo vệ dữ liệu khi truyền hoặc lưu trữ; CloudTrail và audit logs cung cấp bằng chứng vận hành.

Một request phải vượt qua các lớp kiểm soát liên quan. Nếu security group chặn, request không đến domain. Nếu domain access policy từ chối, request bị chặn ở rìa domain. Nếu request được phép đến OpenSearch, FGAC tiếp tục kiểm tra danh tính và role mapping.

~~~mermaid
flowchart TD
    A[Client request] --> B{Network / VPC / SG}
    B -->|Deny| X[Không tới domain]
    B -->|Allow| C{Domain access policy}
    C -->|Deny| Y[Edge policy rejects]
    C -->|Allow| D{FGAC authentication}
    D -->|Fail| Z[Authentication denied]
    D -->|Success| E{Cluster / Index / Document / Field permission}
    E -->|Deny| F[Authorization denied]
    E -->|Allow| G[OpenSearch operation]
~~~

Không dùng một lớp duy nhất làm toàn bộ chiến lược bảo mật. Ví dụ VPC security group chỉ giới hạn nguồn mạng; nó không phân biệt analyst được đọc index nào hay ingest role được ghi index nào.

## 7. VPC domain hay public domain?

Khi tạo domain, chọn VPC access hoặc public endpoint. Hai mô hình có đặc điểm khác nhau:

| Tiêu chí | VPC domain | Public domain |
|---|---|---|
| Kết nối | Client phải có đường mạng vào VPC | Client có internet route đến endpoint |
| Kiểm soát network | Security group, route, NACL, VPN/TGW/proxy | Public network và access policy |
| IP-based domain policy | Không dùng được; security group xử lý IP/network | Có thể dùng |
| Thay đổi loại endpoint | Không thể chuyển trực tiếp sang public | Không thể chuyển trực tiếp sang VPC |
| Phù hợp | Production nội bộ, workload private | Use case cần endpoint public có kiểm soát |

Domain VPC không thể được truy cập trực tiếp từ máy bên ngoài VPC. Máy quản trị cần VPN, Transit Gateway, managed network hoặc proxy có route phù hợp.

Một domain được tạo với VPC access không thể chuyển sang public endpoint bằng cách sửa cấu hình. Chiều ngược lại cũng vậy. Nếu cần đổi mô hình, phải tạo domain mới, migrate dữ liệu và chuyển client sang endpoint mới.

Security group của domain nên chỉ nhận HTTPS từ security group hoặc CIDR của các workload cần truy cập. Không mở inbound toàn internet chỉ để tiện kiểm tra OpenSearch Dashboards.

## 8. Domain access policy và IAM identity policy

Domain access policy là resource-based policy gắn với domain. Nó kiểm soát quyền gọi các subresource của OpenSearch, ví dụ index và HTTP API. Resource ARN thường có dạng:

~~~text
arn:aws:es:ap-southeast-1:123456789012:domain/orders-search/*
~~~

Ví dụ chỉ cho phép role của ứng dụng gọi HTTP API trên domain:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCheckoutService",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/checkout-search-role"
      },
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut"
      ],
      "Resource": "arn:aws:es:ap-southeast-1:123456789012:domain/orders-search/*"
    }
  ]
}
~~~

Đây là ví dụ theo domain resource policy. Phải điều chỉnh HTTP methods theo API thực tế. Không cấp es:ESHttp* cho mọi principal nếu ứng dụng chỉ cần đọc hoặc index một nhóm dữ liệu.

Nếu domain access policy chứa IAM user hoặc role, client phải ký request bằng AWS Signature Version 4. Điều này có thể xung đột với FGAC dùng internal user database và HTTP Basic Authentication, vì client không thể đồng thời ký cùng request bằng username/password và IAM credentials. Khi dùng internal user database, một cấu hình thường gặp là domain access policy không yêu cầu IAM principal, giới hạn network bằng VPC/security group và để FGAC xác thực, phân quyền user. Khi dùng IAM master user, client dùng SigV4 và role mapping tương ứng. Chọn một mô hình nhất quán cho ứng dụng và Dashboards.

IAM identity policy thường kiểm soát configuration API như DescribeDomain, UpdateDomainConfig, CreateDomain và DeleteDomain. Nó cũng có thể cấp quyền HTTP API cho principal. Phân biệt quyền quản trị domain với quyền truy cập dữ liệu.

Trong domain access policy, resource ARN có dấu /* ở cuối để chỉ subresource. Quyền gọi configuration API dùng domain ARN phù hợp, không phải subresource ARN.

Nếu policy có Principal là dấu sao, domain có thể nhận anonymous request theo điều kiện áp dụng. Không dùng open access policy cho public domain production. Với VPC domain, security group vẫn kiểm soát network; tuy nhiên policy mở không có principal có thể chấp nhận unsigned HTTP request từ nguồn mà security group cho phép. Hãy bật FGAC và giới hạn role thay vì coi VPC là quyền truy cập dữ liệu.

## 9. Fine-grained access control

FGAC cung cấp quyền ở nhiều cấp:

- **Cluster-level:** quản lý cluster API, health, index template hoặc chức năng toàn cluster.
- **Index-level:** đọc, ghi, tạo index, quản lý alias và mapping.
- **Document-level security (DLS):** chỉ cho user xem document thỏa query.
- **Field-level security (FLS):** chỉ hiển thị hoặc loại trừ field nhất định.
- **Field masking:** che giá trị của field nhạy cảm theo cấu hình.

FGAC dùng OpenSearch roles, users và mappings. OpenSearch role khác IAM role. IAM role đại diện danh tính AWS; FGAC role chứa quyền bên trong cluster. Một IAM role có thể được ánh xạ sang một hoặc nhiều FGAC roles.

FGAC cần được xem là quyết định kiến trúc ngay từ đầu: sau khi bật, không thể tắt trực tiếp. Nếu thay đổi mô hình bảo mật lớn, cần lập kế hoạch migration sang domain mới.

Ví dụ:

- Role ingest chỉ được ghi vào logs-checkout-*.
- Role analyst chỉ được search trên logs-*.
- Role security-auditor chỉ đọc audit index.
- Role support chỉ được xem document của tenant được giao.
- Role pii-restricted bị ẩn các field email hoặc phone.

FGAC yêu cầu domain bật HTTPS, encryption at rest và node-to-node encryption. Sau khi bật FGAC, không thể tắt trực tiếp. Khi thiết kế domain mới, nên xác định trước master user, authentication method và role mapping.

## 10. Master user và quản lý danh tính

Master user có quyền cao trên OpenSearch cluster. Có thể chọn:

- IAM principal làm master user.
- Internal user database với username/password.

Master user có quyền truy cập rộng, vì vậy chỉ dùng để quản trị role, user, mapping và cấu hình bảo mật. Ứng dụng ingest hoặc dashboard không nên dùng master credential.

Có thể dùng SAML authentication cho OpenSearch Dashboards để tích hợp identity provider. Với IAM master user, nếu muốn đăng nhập Dashboards bằng giao diện web, cần cấu hình phương thức đăng nhập phù hợp như SAML hoặc Amazon Cognito theo kiến trúc được hỗ trợ. Nếu chỉ đặt IAM master user mà không cấu hình cơ chế sign-in phù hợp, trang đăng nhập Dashboards có thể không hoạt động như mong đợi.

Role mapping là bước bắt buộc. Tạo role nhưng không map user/backend role sẽ khiến request bị từ chối. Khi dùng SAML, có thể ánh xạ group attribute từ identity provider sang FGAC role.

## 11. HTTPS, node-to-node encryption và encryption at rest

Ba cấu hình encryption có mục đích khác nhau:

| Cấu hình | Bảo vệ điều gì | Vai trò |
|---|---|---|
| Require HTTPS | Client đến domain endpoint | Mã hóa request/response giữa client và domain |
| Node-to-node encryption | Giao tiếp giữa OpenSearch nodes | TLS 1.2 cho lưu chuyển dữ liệu nội bộ |
| Encryption at rest | Dữ liệu trên storage | AWS KMS và AES-256 |

Node-to-node encryption bảo vệ traffic khi OpenSearch phân phối và replicate dữ liệu giữa các node. Nếu client gửi dữ liệu qua HTTPS, dữ liệu tiếp tục được bảo vệ khi cluster xử lý và phân phối. Node-to-node encryption là điều kiện bắt buộc của FGAC.

Khi bật node-to-node encryption, không thể tắt trực tiếp. Nếu cần thay đổi, thường phải tạo domain mới, snapshot/migrate dữ liệu và chuyển ứng dụng.

Encryption at rest dùng AWS KMS. Có thể dùng AWS owned key hoặc customer managed key. Nếu dùng customer managed key, cần bảo đảm key policy và trạng thái key cho phép OpenSearch Service sử dụng. Key bị disabled hoặc inaccessible có thể làm domain phát sinh lỗi KMS và ảnh hưởng hoạt động.

Lưu ý: encryption at rest của domain không tự mã hóa CloudWatch Logs log group. Nếu cần mã hóa log publishing, cấu hình KMS encryption riêng cho log group. Manual snapshot repository trên S3 cũng có cơ chế encryption riêng ở bucket.

## 12. Bật log publishing cho domain

OpenSearch Service có bốn loại log chính có thể publish đến CloudWatch Logs:

| Log type trong cấu hình | Nội dung | Dùng để |
|---|---|---|
| ES_APPLICATION_LOGS | Error/application logs của OpenSearch | Lỗi query, indexing, script, snapshot và vận hành |
| SEARCH_SLOW_LOGS | Search request hoặc search slow logs | Tìm truy vấn chậm |
| INDEX_SLOW_LOGS | Shard indexing slow logs | Tìm index operation chậm |
| AUDIT_LOGS | User activity và security events | Điều tra authentication, authorization và compliance |

Các log này bị tắt mặc định. Nếu bật, CloudWatch Logs tính phí theo mức sử dụng. Nên tạo log group riêng cho từng loại log để quản lý retention, access và truy vấn dễ hơn.

Để bật log publishing bằng console:

1. Mở Amazon OpenSearch Service.
2. Chọn domain.
3. Mở tab Logs.
4. Chọn log type cần publish và bật Enable.
5. Chọn hoặc tạo CloudWatch log group.
6. Cấp resource policy cho service principal của OpenSearch.
7. Chờ domain quay lại trạng thái Active rồi kiểm tra log stream.

Khi bật log publishing, domain có thể chuyển sang Processing. Thời gian cập nhật phụ thuộc cấu hình và có thể kéo dài. Không coi việc bật checkbox là bằng chứng log đã được ghi; cần kiểm tra resource policy, log group và threshold.

## 13. CloudWatch Logs resource policy cho OpenSearch

OpenSearch Service cần quyền tạo log stream và ghi log events. Resource policy trên CloudWatch Logs cho phép service principal es.amazonaws.com ghi vào log group.

Ví dụ policy giới hạn theo account và domain:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOpenSearchDomainLogDelivery",
      "Effect": "Allow",
      "Principal": {
        "Service": "es.amazonaws.com"
      },
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/*:*",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:es:ap-southeast-1:123456789012:domain/orders-search"
        }
      }
    }
  ]
}
~~~

Điều kiện SourceAccount và SourceArn giúp giảm nguy cơ confused deputy. Hãy dùng ARN đúng account, Region, domain và log group. Các condition này được hỗ trợ với service software phù hợp; nếu domain quá cũ, kiểm tra khả năng tương thích trước khi áp dụng.

CloudWatch Logs giới hạn số resource policies theo Region. Nếu nhiều domain publish log, có thể dùng một policy được quản trị tập trung bao phủ các log group cần thiết thay vì tạo policy riêng vượt quota.

Ví dụ tạo resource policy bằng AWS CLI:

~~~bash
aws logs put-resource-policy \
  --policy-name opensearch-domain-logs \
  --policy-document file://opensearch-logs-policy.json
~~~

Không cấp quyền logs:PutLogEvents cho principal rộng hơn phạm vi log group cần thiết. Đặt retention cho từng log group và giới hạn ai có thể đọc audit log.

## 14. Bật log publishing bằng AWS CLI

Tạo log group trước:

~~~bash
aws logs create-log-group \
  --log-group-name /aws/opensearch/orders-search/application
~~~

Sau khi đã cấu hình resource policy, bật các loại log bằng update-domain-config:

~~~bash
aws opensearch update-domain-config \
  --domain-name orders-search \
  --log-publishing-options '{
    "ES_APPLICATION_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/application",
      "Enabled": true
    },
    "SEARCH_SLOW_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/search-slow",
      "Enabled": true
    },
    "INDEX_SLOW_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/index-slow",
      "Enabled": true
    },
    "AUDIT_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/audit",
      "Enabled": true
    }
  }'
~~~

Lệnh trên là ví dụ cho shell có hỗ trợ single-quoted JSON. Với PowerShell hoặc môi trường CI khác, điều chỉnh cách quoting hoặc lưu JSON vào file và truyền tham số file phù hợp.

Kiểm tra cấu hình:

~~~bash
aws opensearch describe-domain-config \
  --domain-name orders-search
~~~

Tìm phần LogPublishingOptions và xác minh đúng ARN, đúng loại log và Enabled=true. Sau đó mở CloudWatch Logs và kiểm tra log stream mới.

## 15. Error/application logs

ES_APPLICATION_LOGS là loại log dùng để quan sát lỗi nội bộ của OpenSearch. Khi bật, dịch vụ publish các dòng WARN, ERROR và FATAL; một số exception từ DEBUG cũng có thể xuất hiện.

Những tình huống thường hữu ích:

- Painless script compilation error.
- Query không hợp lệ hoặc lỗi shard.
- Mapping/parsing exception khi index document.
- Snapshot failure.
- Index State Management migration failure.
- Rejected execution hoặc lỗi tài nguyên.

Không phải mọi lỗi đều xuất hiện trong error logs. Nếu client nhận HTTP 4xx hoặc 5xx, cần đối chiếu response body, application log, audit log và metric cùng thời điểm. Không kết luận rằng không có log nghĩa là không có lỗi.

## 16. Search slow logs và index slow logs

Slow logs giúp xác định thao tác tốn thời gian. Có hai phạm vi thường gặp:

- Search request slow log đo tổng thời gian xử lý request tìm kiếm; hỗ trợ ở OpenSearch 2.13 trở lên theo tài liệu dịch vụ.
- Shard slow log ghi nhận thời gian search hoặc indexing ở cấp shard/index.

Chỉ bật log publishing chưa đủ. Với shard slow logs, cần cấu hình threshold ở index settings để OpenSearch biết thao tác nào được xem là chậm.

Ví dụ đặt threshold cho index log:

~~~http
PUT logs-checkout-*/_settings
{
  "index.search.slowlog.threshold.query.info": "1s",
  "index.search.slowlog.threshold.query.warn": "3s",
  "index.indexing.slowlog.threshold.index.info": "1s",
  "index.indexing.slowlog.threshold.index.warn": "3s"
}
~~~

Các giá trị chỉ là điểm bắt đầu. Hãy chọn threshold theo SLO, loại query, volume và latency bình thường. Threshold quá thấp sẽ tạo quá nhiều log và tăng chi phí; threshold quá cao có thể bỏ sót query ảnh hưởng người dùng.

Khi test, có thể tạm đặt threshold thấp trong môi trường non-production để xác nhận log xuất hiện. Sau đó tăng về mức phù hợp. Không để threshold thử nghiệm ở production lâu hơn cần thiết.

## 17. Audit logs và theo dõi hoạt động người dùng

Audit logs theo dõi hoạt động trên cluster như authentication success/failure, request đến OpenSearch, thay đổi index và truy vấn tìm kiếm. Audit logs yêu cầu domain bật FGAC.

Để bật audit logs cần hai bước:

1. Bật AUDIT_LOGS publishing trong cấu hình domain và cấp CloudWatch Logs resource policy.
2. Trong OpenSearch Dashboards, bật audit logging và cấu hình layer/category phù hợp.

User thực hiện cấu hình audit cần được map vào role security_manager để truy cập Security REST API.

Các category thường gặp:

| Category | Ý nghĩa |
|---|---|
| FAILED_LOGIN | Authentication thất bại |
| AUTHENTICATED | Authentication thành công |
| MISSING_PRIVILEGES | User thiếu quyền thực hiện request |
| GRANTED_PRIVILEGES | Request được cấp quyền |
| INDEX_EVENT | Thao tác quản trị index |
| COMPLIANCE_DOC_READ | Đọc document theo compliance audit |
| COMPLIANCE_DOC_WRITE | Ghi document theo compliance audit |

Không bật mọi category một cách máy móc. GRANTED_PRIVILEGES và AUTHENTICATED có thể ghi cho mọi request hợp lệ, làm log volume tăng mạnh. AWS khuyến nghị loại trừ hai category này trong nhiều cấu hình mặc định và chỉ bật khi có nhu cầu điều tra cụ thể.

Audit settings cũng có thể cho phép ghi request body. Điều này hữu ích khi điều tra nhưng có thể làm lộ dữ liệu nhạy cảm. Cấu hình exclude sensitive headers, ignore users/requests và compliance logging theo yêu cầu bảo mật.

Audit log message có giới hạn kích thước; nội dung vượt quá giới hạn có thể bị cắt. Một số cross-cluster search request bị từ chối bởi destination domain access policy không xuất hiện trong audit log của domain đích. Dùng thêm CloudTrail, source domain logs và client logs khi điều tra cross-cluster search.

## 18. Ví dụ cấu hình audit logs

Sau khi đã bật publishing ở domain, có thể cấu hình audit logs qua OpenSearch Dashboards hoặc Security REST API.

Ví dụ cấu hình tối giản, giữ lại các category cần điều tra và loại các event quá phổ biến:

~~~json
{
  "enabled": true,
  "audit": {
    "enable_rest": true,
    "disabled_rest_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "enable_transport": true,
    "disabled_transport_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "resolve_bulk_requests": true,
    "log_request_body": false,
    "resolve_indices": true,
    "exclude_sensitive_headers": true,
    "ignore_users": [
      "kibanaserver"
    ],
    "ignore_requests": [
      "/_cluster/health"
    ]
  }
}
~~~

Ví dụ REST request:

~~~http
PUT _plugins/_security/api/audit/config
Content-Type: application/json

{
  "enabled": true,
  "audit": {
    "enable_rest": true,
    "disabled_rest_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "enable_transport": true,
    "disabled_transport_categories": [
      "GRANTED_PRIVILEGES",
      "AUTHENTICATED"
    ],
    "log_request_body": false,
    "exclude_sensitive_headers": true
  }
}
~~~

Cấu hình thực tế phải giữ các category phù hợp với chính sách compliance. Nếu cần chứng minh ai đọc hoặc ghi document nào, xem xét compliance logging và chi phí phát sinh. Hãy thử nghiệm trước trên domain test vì audit settings ảnh hưởng đến lượng log và quyền riêng tư.

## 19. Quan sát domain bằng CloudWatch metrics

Amazon OpenSearch Service publish metrics trong namespace AWS/ES. Phần lớn metrics được gửi mỗi 60 giây. Một số EBS metrics có chu kỳ cập nhật dài hơn. Metrics tích lũy như rejected task có thể reset khi node restart, replacement hoặc blue/green deployment.

Metrics giúp quan sát ba nhóm:

- **Cluster health:** trạng thái shard, node và khả năng nhận write.
- **Resource pressure:** CPU, JVM heap, storage, queue và rejected requests.
- **Workload performance:** search rate, indexing rate, latency và request volume.

Các dimension phổ biến gồm ClientId và DomainName cho metric cấp domain, thêm NodeId cho metric cấp node. Một số metric shard có thêm ShardRole. Khi tạo alarm, chọn đúng dimension và statistic; nhầm dimension sẽ khiến alarm ở trạng thái Insufficient Data.

Metrics được dịch vụ lưu trữ trong khoảng thời gian giới hạn trước khi loại bỏ. Dashboard và alarm CloudWatch có thể phát sinh phí riêng, dù một số metrics của OpenSearch Service được publish không tính thêm phí metric.

## 20. Metrics quan trọng và cách diễn giải

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| ClusterStatus.red | Có primary shard hoặc replica không được allocate | Cluster có nguy cơ mất dữ liệu hoặc không phục vụ một phần index |
| ClusterStatus.yellow | Replica shard chưa allocate | Redundancy suy giảm |
| FreeStorageSpace | Dung lượng trống của data node | Disk gần đầy, nguy cơ write block |
| JVMMemoryPressure | Phần trăm Java heap đang dùng | Heap cao kéo dài, GC pressure, write block |
| CPUUtilization | CPU của node | Query/index workload vượt capacity |
| Nodes | Số node đang hoạt động | Node không reachable hoặc cluster thiếu node |
| ClusterIndexWritesBlocked | Cluster đang chặn write hay không | Storage/heap pressure hoặc trạng thái cluster |
| SearchLatency | Tổng thời gian xử lý search theo node trong khoảng metric | Query chậm hoặc tải tăng |
| IndexingLatency | Thời gian indexing | Ingest chậm hoặc write pressure |
| SearchRate | Số search request | Thay đổi traffic hoặc query pattern |
| IndexingRate | Số operation index | Tốc độ ingest và burst |
| ThreadpoolSearchQueue | Số task search đang chờ | Search worker bị nghẽn |
| ThreadpoolWriteQueue | Số task write đang chờ | Ingest vượt khả năng xử lý |
| ThreadpoolSearchRejected | Search task bị từ chối | Search queue quá tải |
| ThreadpoolWriteRejected | Write task bị từ chối | Write queue quá tải |
| AutomatedSnapshotFailure | Automated snapshot thất bại | Snapshot/recovery cần điều tra |

FreeStorageSpace được CloudWatch hiển thị theo MiB. Statistic Minimum giúp phát hiện node có disk trống ít nhất. Statistic Sum cho biết tổng dung lượng trống của cluster nhưng phải giữ period một phút để có giá trị chính xác theo hướng dẫn AWS.

SysMemoryUtilization cao không đồng nghĩa ngay với vấn đề heap. OpenSearch dùng filesystem cache; JVMMemoryPressure thường là chỉ số hữu ích hơn để theo dõi áp lực heap Java.

Với OpenSearch version 7.1 trở lên, ThreadpoolWriteRejected không còn là chỉ số duy nhất cho write rejection do write queue mặc định đã thay đổi. Theo dõi thêm CoordinatingWriteRejected, PrimaryWriteRejected và ReplicaWriteRejected nếu workload dùng version tương ứng.

## 21. CloudWatch alarms khuyến nghị

Một số ngưỡng khởi đầu từ hướng dẫn AWS:

| Alarm | Điều kiện tham khảo | Phản ứng |
|---|---|---|
| ClusterStatus.red | Maximum >= 1 trong 1 phút | Kiểm tra shard allocation, node và disk |
| ClusterStatus.yellow | Maximum >= 1 trong 1 phút, lặp lại nhiều kỳ | Kiểm tra replica allocation và node availability |
| FreeStorageSpace | Minimum <= 20 GiB hoặc 25% dung lượng node | Tăng EBS/storage hoặc node; kiểm tra retention |
| ClusterIndexWritesBlocked | Maximum >= 1 | Kiểm tra storage, heap và write block |
| Nodes | Minimum nhỏ hơn số node mong đợi | Điều tra node failure |
| AutomatedSnapshotFailure | Maximum >= 1 | Kiểm tra cluster health và snapshot status |
| CPUUtilization | Cao kéo dài, ví dụ 80% trong 15 phút | Tăng instance size hoặc node count |
| JVMMemoryPressure | Maximum >= 95% lặp lại | Kiểm tra heap, shard, query và scaling |
| MasterJVMMemoryPressure | Cao kéo dài | Kiểm tra dedicated master capacity |

Không sao chép ngưỡng mẫu mà không xét workload. Ví dụ FreeStorageSpace cần được quy đổi theo dung lượng mỗi node, số node và replica. Một cluster lớn có tổng disk trống cao nhưng một node đã gần đầy vẫn có thể gặp sự cố.

Alarm nên có action rõ ràng: gửi SNS, tạo incident, hoặc kích hoạt EventBridge workflow. Tránh tự động scale hoặc xóa index dựa trên một metric duy nhất mà không có guardrail.

## 22. Tạo CloudWatch alarm cho JVM memory pressure

Ví dụ AWS CLI tạo alarm cho JVMMemoryPressure:

~~~bash
aws cloudwatch put-metric-alarm \
  --alarm-name orders-search-jvm-pressure \
  --namespace AWS/ES \
  --metric-name JVMMemoryPressure \
  --dimensions Name=ClientId,Value=123456789012 Name=DomainName,Value=orders-search \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 3 \
  --datapoints-to-alarm 3 \
  --threshold 90 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data missing \
  --alarm-actions arn:aws:sns:ap-southeast-1:123456789012:platform-alerts
~~~

Threshold 90% là giá trị ví dụ để minh họa cách tạo alarm. Đối chiếu khuyến nghị theo metric, workload và runbook. Nếu dùng node-level metric, bổ sung NodeId dimension và xác định có cần alarm riêng cho từng node hay không.

Alarm cho cluster red nên dùng statistic Maximum và phản ứng nhanh. Alarm cho yellow có thể cần nhiều evaluation periods để tránh cảnh báo thoáng qua trong lúc shard relocation. Dùng composite alarm nếu cần kết hợp cluster status, storage và node count.

## 23. Dùng CloudWatch Logs Insights để điều tra

Khi log đã được publish, CloudWatch Logs Insights có thể lọc lỗi theo thời gian, severity, domain hoặc exception.

Ví dụ tìm ERROR/FATAL trong log group application:

~~~text
fields @timestamp, @message
| filter @message like /ERROR|FATAL/
| sort @timestamp desc
| limit 100
~~~

Tìm log slow query có thời gian vượt ngưỡng nếu log format chứa took:

~~~text
fields @timestamp, @message
| filter @message like /took/
| sort @timestamp desc
| limit 100
~~~

Tìm failed login từ audit logs:

~~~text
fields @timestamp, @message
| filter @message like /FAILED_LOGIN/
| sort @timestamp desc
| limit 100
~~~

Log format có thể thay đổi theo version và cấu hình. Nếu log được parse thành JSON fields, dùng field đó để filter thay vì regex chuỗi. Truy vấn rộng trên log group lớn có thể tốn thời gian và chi phí scan; luôn giới hạn time range và log group.

## 24. CloudTrail và EventBridge cho hoạt động domain

CloudTrail ghi nhận các configuration API calls tới OpenSearch Service, ví dụ:

- CreateDomain và DeleteDomain.
- UpdateDomainConfig.
- AddTags và RemoveTags.
- Thay đổi access policy hoặc security configuration.
- Các thao tác quản trị domain khác được hỗ trợ trong CloudTrail.

CloudTrail trả lời ai đã gọi AWS API, từ account nào, source IP nào và vào thời điểm nào. Nó không thay thế audit logs của OpenSearch cho từng request tìm kiếm hoặc thao tác document.

Amazon EventBridge nhận near-real-time service events mô tả thay đổi trạng thái domain. Có thể tạo rule để phát hiện domain chuyển sang Processing, cấu hình update, lỗi hoặc sự kiện dịch vụ. Từ đó gửi SNS, tạo incident hoặc kích hoạt workflow phản ứng.

Kết hợp ba nguồn:

| Nguồn | Phạm vi |
|---|---|
| CloudTrail | Ai thay đổi cấu hình AWS domain/API |
| OpenSearch audit logs | Ai đăng nhập và thực hiện thao tác trong cluster |
| CloudWatch metrics/logs | Cluster và workload vận hành như thế nào |

Khi điều tra, đồng bộ timestamp UTC và giữ domain name, request ID, principal ARN, trace ID để liên kết sự kiện giữa các nguồn.

## 25. Quan sát ứng dụng bằng OpenTelemetry

Nếu cần quan sát cả logs, traces và metrics của ứng dụng, có thể dùng OpenTelemetry Collector làm điểm thu thập telemetry. Collector nhận OTLP từ SDK hoặc auto-instrumentation, sau đó gửi logs/traces đến OpenSearch Ingestion bằng SigV4. Metrics có thể được gửi sang Amazon Managed Service for Prometheus bằng Prometheus Remote Write.

Luồng mẫu:

~~~mermaid
flowchart LR
    A[Application SDK / Agent] --> B[OpenTelemetry Collector]
    B -->|OTLP logs and traces| C[OpenSearch Ingestion]
    C --> D[OpenSearch domain]
    B -->|Prometheus Remote Write| E[Amazon Managed Service for Prometheus]
    D --> F[OpenSearch UI]
    E --> F
~~~

IAM principal gửi telemetry cần osis:Ingest trên pipeline ARN. Nếu gửi metrics sang AMP, cần aps:RemoteWrite trên workspace. OpenSearch Ingestion xử lý, enrich và route telemetry trước khi index.

OpenSearch Service hiện có trải nghiệm observability mới trong OpenSearch UI workspace. Các tính năng Application Monitoring, service map và correlation logs/traces/metrics được tài liệu hóa cho OpenSearch UI; chúng không đồng nghĩa với mọi plugin trong giao diện OpenSearch Dashboards truyền thống. Kiểm tra loại workspace và feature availability trước khi thiết kế dashboard.

## 26. Bảo vệ log và dữ liệu nhạy cảm

Log thường chứa nhiều dữ liệu có thể nhận dạng người dùng hoặc tiết lộ kiến trúc nội bộ. Trước khi ingest, cần xác định:

- Field nào là dữ liệu cá nhân hoặc bí mật.
- Ai được đọc index tương ứng.
- Ai có quyền export hoặc snapshot.
- Log được giữ bao lâu.
- Log group và S3 archive được mã hóa bằng key nào.
- Có cần field masking hoặc document-level security không.
- Ai được phép thay đổi audit settings hoặc retention.

Không ghi access token, password, session cookie hoặc private key vào log. Không dùng audit log request body cho mọi request nếu payload có thể chứa thông tin cá nhân. Dùng data minimization và redaction ở source/processor.

Với dữ liệu nhiều tenant, có thể tách index theo tenant hoặc dùng DLS để giới hạn document theo tenant ID. DLS/FLS cần được kiểm thử cả với bulk, alias, aggregation và dashboard. Một policy sai có thể để lộ dữ liệu qua query khác dù giao diện chỉ hiển thị một số field.

## 27. Quản trị retention và chi phí quan sát

Chi phí vận hành OpenSearch domain không chỉ là compute và storage. Log publishing, CloudWatch Logs ingestion/storage, dashboards, alarms, Data Firehose, OpenSearch Ingestion và snapshot đều có thể phát sinh chi phí.

Một số biện pháp:

- Tách application, search slow, index slow và audit logs.
- Đặt retention ngắn hơn cho log debug/slow logs nếu không có yêu cầu lưu dài.
- Archive audit logs cần giữ lâu sang S3 theo chính sách.
- Dùng filter ở CloudWatch Logs subscription để giảm log volume.
- Redact và drop field không cần thiết trước khi index.
- Chọn threshold slow logs hợp lý.
- Dùng ISM để rollover và xóa index hết hạn.
- Theo dõi ingest bytes, index size, shard count và storage growth.
- Dừng hoặc scale pipeline không cần hoạt động liên tục khi use case cho phép.
- Kiểm soát cardinality của field và số lượng index.

Không đặt retention ngắn hơn yêu cầu điều tra hoặc compliance. Nếu audit log cần lưu 1 năm, hãy thiết kế archive riêng và kiểm thử khả năng truy xuất thay vì giữ toàn bộ dữ liệu trong hot storage.

## 28. Case study: quan sát domain tìm kiếm đơn hàng

Một nền tảng thương mại điện tử có OpenSearch domain phục vụ tìm kiếm đơn hàng và tra cứu lịch sử. Ứng dụng checkout chạy trên ECS, API gateway và load balancer tạo access log, còn nhóm bảo mật cần theo dõi truy cập index.

Thiết kế:

1. Domain nằm trong VPC, security group chỉ nhận HTTPS từ ECS service và mạng quản trị.
2. Require HTTPS, node-to-node encryption và encryption at rest được bật.
3. FGAC dùng IAM master role và role mapping riêng cho ingest, analyst và security auditor.
4. ECS gửi structured application logs đến CloudWatch Logs.
5. Subscription filter chuyển log phù hợp vào Data Firehose hoặc OpenSearch Ingestion.
6. Pipeline chuẩn hóa timestamp, service, environment, trace ID và status code.
7. Index template đặt mapping rõ ràng; ISM rollover và xóa log theo retention.
8. Domain publish application logs, search slow logs, index slow logs và audit logs vào các log group riêng.
9. CloudWatch alarms theo dõi red/yellow, storage, CPU, JVM pressure, node count và write block.
10. CloudTrail và EventBridge phát hiện thay đổi domain configuration.
11. Analyst chỉ đọc index logs-*; ingest role chỉ ghi index theo service; security auditor đọc audit log và security events.
12. Runbook liên kết CloudWatch metrics, slow logs, audit logs và application trace để xác định nguyên nhân.

Nếu search latency tăng nhưng CPU bình thường, nhóm kiểm tra slow logs và shard distribution. Nếu write block xuất hiện cùng lúc FreeStorageSpace thấp, nhóm xem ISM retention, tăng EBS hoặc data node capacity. Nếu có nhiều FAILED_LOGIN hoặc MISSING_PRIVILEGES, nhóm đối chiếu principal, role mapping và source network.

## 29. Troubleshooting theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Domain timeout | VPC route, SG, NACL, DNS | Xác nhận client có đường mạng đến VPC domain |
| HTTP 403 | Domain access policy, IAM signature, FGAC role mapping | Xác định lớp nào từ chối request |
| Log group không có stream | CloudWatch resource policy, log publishing option | Kiểm tra es.amazonaws.com, ARN và Enabled |
| Slow logs không xuất hiện | Threshold và log publishing | Cấu hình index slowlog threshold và thử lại |
| Audit logs không bật | FGAC, security_manager, resource policy | Hoàn thành cả domain publishing và Dashboards configuration |
| ClusterStatus.red | Unassigned primary shard, node, disk | Kiểm tra allocation explain, node health và storage |
| ClusterStatus.yellow | Replica shard chưa allocate | Kiểm tra replica, AZ và node availability |
| FreeStorageSpace thấp | Disk per node, index growth, retention | Rollover, delete expired index hoặc tăng storage |
| JVMMemoryPressure cao | Heap, shard count, query, aggregation | Giảm shard/fielddata, tối ưu query, scale |
| ClusterIndexWritesBlocked | Disk hoặc heap protection | Xác định nguyên nhân write block trước khi retry |
| Search queue tăng | Search concurrency, slow query | Tối ưu query, shard và scale |
| Write rejection tăng | Ingest burst, indexing pressure | Buffer, backoff, batch size và scale |
| Audit log volume tăng mạnh | GRANTED_PRIVILEGES/AUTHENTICATED categories | Điều chỉnh categories và filters |
| Ingest bị trùng | At-least-once delivery/retry | Dùng event ID hoặc idempotent processing |
| Field mapping conflict | Cùng field có nhiều type | Chuẩn hóa schema, template và version field |

### 29.1. Lỗi 403 không phải lúc nào cũng là IAM

Có thể chia lỗi thành ba trường hợp:

- IAM request signing hoặc identity policy không cho phép.
- Domain access policy không cho phép principal hoặc HTTP method.
- FGAC xác thực user nhưng user không có quyền trên cluster/index/document/field.

Hãy kiểm tra response, request signer, principal ARN và role mapping. Đừng cấp es:* cho toàn bộ domain để sửa nhanh một lỗi 403.

### 29.2. Storage và JVM pressure

Khi FreeStorageSpace gần 0, OpenSearch Service có thể block writes và trả ClusterBlockException. Khi heap pressure cao kéo dài, cơ chế bảo vệ có thể chặn write để tránh cluster chuyển sang red. Kiểm tra shard count, fielddata, query aggregation, mapping explosion, queue và node sizing.

Không xóa index mới nhất hoặc index đang được ứng dụng sử dụng chỉ để giải phóng disk. Xác định index hết retention, snapshot/recovery requirement và owner trước khi xóa.

### 29.3. Không thấy audit log dù đã bật

Audit logging gồm hai phần: publish AUDIT_LOGS sang CloudWatch và bật/configure audit logging bên trong OpenSearch. Kiểm tra cả hai. Ngoài ra, user cấu hình cần security_manager role; log group cần resource policy cho OpenSearch Service; domain phải dùng FGAC.

## 30. Lab: bật log publishing và tạo alarm

Thực hiện trên domain test hoặc môi trường đã được phê duyệt. Không thay đổi domain production chỉ để thử nghiệm.

### Bước 1: Kiểm tra domain

~~~bash
aws opensearch describe-domain \
  --domain-name orders-search
~~~

Ghi lại domain ARN, endpoint, VPC options, encryption options và trạng thái.

### Bước 2: Tạo log groups

~~~bash
aws logs create-log-group \
  --log-group-name /aws/opensearch/orders-search/application

aws logs create-log-group \
  --log-group-name /aws/opensearch/orders-search/search-slow
~~~

Tạo resource policy cho service principal OpenSearch theo mẫu ở phần trên.

### Bước 3: Bật application logs và slow logs

~~~bash
aws opensearch update-domain-config \
  --domain-name orders-search \
  --log-publishing-options '{
    "ES_APPLICATION_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/application",
      "Enabled": true
    },
    "SEARCH_SLOW_LOGS": {
      "CloudWatchLogsLogGroupArn": "arn:aws:logs:ap-southeast-1:123456789012:log-group:/aws/opensearch/orders-search/search-slow",
      "Enabled": true
    }
  }'
~~~

Chờ domain về Active. Cấu hình threshold cho index test.

### Bước 4: Tạo một truy vấn test và kiểm tra log

~~~http
PUT logs-lab-000001/_settings
{
  "index.search.slowlog.threshold.query.info": "1ms",
  "index.search.slowlog.threshold.query.warn": "2ms"
}
~~~

Chạy search query trên index test, sau đó mở CloudWatch Logs để kiểm tra log stream. Threshold thấp chỉ dùng trong lab và phải được trả về mức phù hợp sau khi xác minh.

### Bước 5: Tạo alarm

Dùng lệnh put-metric-alarm ở phần CloudWatch để theo dõi JVMMemoryPressure. Có thể tạo thêm alarm cho ClusterStatus.red và FreeStorageSpace.

### Bước 6: Kiểm tra và dọn dẹp

- Xác minh log stream nhận được event.
- Xác minh metric có data point.
- Xác minh alarm chuyển state đúng khi điều kiện xảy ra trong môi trường test.
- Khôi phục slow log threshold về mức vận hành phù hợp.
- Xóa alarm, log group và test index nếu không còn cần.
- Không xóa domain hoặc dữ liệu ngoài phạm vi lab.

## 31. Checklist production readiness

### Ingestion

- [ ] Đã phân loại domain logs và application logs.
- [ ] Đã chọn pipeline ingest phù hợp nguồn dữ liệu.
- [ ] Log có timestamp UTC và schema nhất quán.
- [ ] Đã filter/redact secret và dữ liệu cá nhân trước khi index.
- [ ] Có xử lý retry, duplicate và backpressure.
- [ ] Index template và retention policy đã được kiểm thử.
- [ ] Shard count dựa trên kích thước index và query pattern.

### Security

- [ ] Domain nằm trong VPC nếu workload phù hợp với private access.
- [ ] Security group chỉ cho phép client đã xác định.
- [ ] Require HTTPS được bật.
- [ ] Node-to-node encryption được bật.
- [ ] Encryption at rest dùng KMS key được quản lý.
- [ ] FGAC được bật và role mapping đã kiểm thử.
- [ ] Master user chỉ dùng cho quản trị.
- [ ] Domain access policy và IAM identity policy tuân theo least privilege.
- [ ] CloudWatch log groups có resource policy, encryption và retention.
- [ ] Audit logs không ghi credential hoặc payload nhạy cảm ngoài chủ đích.

### Observability

- [ ] Application/error logs đã được publish.
- [ ] Search slow và index slow logs đã có threshold.
- [ ] Audit logs đã bật cả publishing lẫn cấu hình bên trong OpenSearch.
- [ ] CloudWatch alarms theo dõi cluster health, disk, JVM, CPU và write block.
- [ ] Có dashboard theo domain, node và workload.
- [ ] CloudTrail theo dõi configuration API.
- [ ] EventBridge có rule cho domain events quan trọng.
- [ ] Runbook liên kết metric, log và trace theo timestamp/request ID.

### Cost and operations

- [ ] Log group retention phù hợp yêu cầu lưu trữ.
- [ ] Ingest pipeline capacity và cost được theo dõi.
- [ ] Có kế hoạch rollover và delete index cũ.
- [ ] Có owner cho từng index/log source.
- [ ] Có quy trình thay đổi policy, role mapping và KMS key.
- [ ] Có kiểm thử snapshot/restore và khả năng phục hồi domain.
- [ ] Có kế hoạch điều tra khi CloudWatch hoặc OpenSearch không nhận log.

## 32. Bài tập tự kiểm tra

### Câu 1

Sự khác nhau giữa log được ingest vào OpenSearch domain và log phát sinh từ domain là gì?

**Đáp án:** Log được ingest là dữ liệu từ ứng dụng/hệ thống mà tổ chức muốn tìm kiếm. Log phát sinh từ domain là error logs, slow logs và audit logs của chính OpenSearch Service.

### Câu 2

Bốn loại log publishing phổ biến của OpenSearch Service là gì?

**Đáp án:** ES_APPLICATION_LOGS, SEARCH_SLOW_LOGS, INDEX_SLOW_LOGS và AUDIT_LOGS.

### Câu 3

Bật INDEX_SLOW_LOGS publishing đã đủ để nhận slow log chưa?

**Đáp án:** Chưa. Cần cấu hình threshold ở index settings để OpenSearch quyết định thao tác nào được ghi.

### Câu 4

Vì sao audit logs cần fine-grained access control?

**Đáp án:** Audit logs của OpenSearch Service chỉ khả dụng khi domain bật FGAC; việc cấu hình audit cần role security_manager.

### Câu 5

Domain access policy và IAM identity policy khác nhau thế nào?

**Đáp án:** Domain access policy là resource-based policy kiểm soát request đến subresource của domain; IAM identity policy gắn với user/role và thường kiểm soát AWS configuration API cùng quyền HTTP API được cấp.

### Câu 6

VPC domain có thể dùng IP-based domain access policy không?

**Đáp án:** Không. Với VPC domain, security group thực hiện kiểm soát nguồn mạng theo IP/CIDR.

### Câu 7

Có thể đổi domain từ VPC endpoint sang public endpoint trực tiếp không?

**Đáp án:** Không. Cần tạo domain mới và migrate dữ liệu.

### Câu 8

FGAC yêu cầu những cấu hình encryption nào?

**Đáp án:** HTTPS cho mọi traffic, encryption at rest và node-to-node encryption.

### Câu 9

Node-to-node encryption bảo vệ luồng nào?

**Đáp án:** Bảo vệ giao tiếp nội bộ giữa OpenSearch nodes bằng TLS 1.2.

### Câu 10

CloudTrail thay thế audit logs của OpenSearch được không?

**Đáp án:** Không. CloudTrail theo dõi AWS configuration API; audit logs theo dõi hoạt động authentication/authorization và request trong cluster.

### Câu 11

Metric nào phản ánh áp lực Java heap?

**Đáp án:** JVMMemoryPressure; cần phân biệt với SysMemoryUtilization.

### Câu 12

FreeStorageSpace được CloudWatch hiển thị theo đơn vị nào?

**Đáp án:** MiB. Console OpenSearch có thể hiển thị theo GiB.

### Câu 13

ClusterIndexWritesBlocked có giá trị 1 nghĩa là gì?

**Đáp án:** Cluster đang block incoming write requests.

### Câu 14

Tại sao không nên bật GRANTED_PRIVILEGES và AUTHENTICATED audit categories cho mọi request?

**Đáp án:** Chúng có thể ghi cho mọi request hợp lệ, làm log volume và chi phí tăng mạnh.

### Câu 15

CloudWatch Logs subscription có thể tạo duplicate event không?

**Đáp án:** Có. Subscription có ngữ nghĩa at-least-once, do đó downstream nên hỗ trợ phát hiện hoặc xử lý duplicate.

### Câu 16

OpenSearch Ingestion dựa trên công nghệ nào?

**Đáp án:** Data Prepper, một data collector có khả năng filter, enrich, transform, normalize và aggregate dữ liệu.

### Câu 17

Nếu log group không có log stream sau khi bật publishing, cần kiểm tra gì?

**Đáp án:** Kiểm tra CloudWatch Logs resource policy, principal es.amazonaws.com, ARN log group, domain log publishing option và trạng thái domain.

### Câu 18

Tại sao cần tách log group cho application, slow và audit logs?

**Đáp án:** Để quản lý quyền đọc, retention, encryption, truy vấn và chi phí theo mục đích của từng loại log.

### Câu 19

Một cluster yellow luôn có nghĩa là primary data đã mất không?

**Đáp án:** Không. Yellow thường nghĩa là có replica shard chưa được allocate; primary shard vẫn có thể hoạt động. Tuy nhiên redundancy đã suy giảm và cần điều tra.

### Câu 20

Khi JVMMemoryPressure cao kéo dài, những nguyên nhân nào cần kiểm tra?

**Đáp án:** Shard count, fielddata, mapping explosion, aggregation, wildcard query, time range rộng, concurrency và instance capacity.

## 33. Tài liệu tham khảo chính thức

- [Monitoring OpenSearch logs with Amazon CloudWatch Logs](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/createdomain-configure-slow-logs.html)
- [Monitoring audit logs in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/audit-logs.html)
- [Monitoring Amazon OpenSearch Service domains](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/monitoring.html)
- [Monitoring OpenSearch cluster metrics with Amazon CloudWatch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/managedomains-cloudwatchmetrics.html)
- [Recommended CloudWatch alarms for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/cloudwatch-alarms.html)
- [Identity and Access Management in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ac.html)
- [Fine-grained access control in Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/fgac.html)
- [Launching OpenSearch Service domains within a VPC](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/vpc.html)
- [Node-to-node encryption for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ntn.html)
- [Encryption of data at rest for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/encryption-at-rest.html)
- [Operational best practices for Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/bp.html)
- [Overview of Amazon OpenSearch Ingestion](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ingestion.html)
- [Ingesting application telemetry](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/observability-ingestion.html)
- [Monitoring pipeline logs](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/monitoring-pipeline-logs.html)
- [Loading streaming data from Amazon CloudWatch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/integrations-cloudwatch.html)
- [Loading streaming data into Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/integrations.html)
- [Real-time processing of log data with CloudWatch Logs subscriptions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html)
- [Log Amazon OpenSearch Service API calls with CloudTrail](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/monitoring-cloudtrail.html)
- [AWS CloudFormation OpenSearch Service domain resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-opensearchservice-domain.html)

Các tên metric, tính năng, giới hạn, engine version và cách cấu hình có thể thay đổi theo OpenSearch version, service software và Region. Trước khi triển khai, đối chiếu tài liệu hiện hành và thử nghiệm trên domain non-production.

