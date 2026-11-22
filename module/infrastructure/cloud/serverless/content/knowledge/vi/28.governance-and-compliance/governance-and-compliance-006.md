# Quản lý quota và yêu cầu tăng hạn mức trước khi mở rộng

Một ứng dụng serverless có thể tự mở rộng số lượng function instance khi traffic tăng, nhưng khả năng scale không phải vô hạn. Mỗi dịch vụ cloud đều có quota, rate limit, concurrency limit, giới hạn kích thước payload hoặc giới hạn tài nguyên theo account, project, subscription, region hay resource. Nếu một mắt xích chạm hạn mức, hệ thống có thể bị throttling, trả lỗi, tăng queue backlog hoặc không triển khai được phiên bản mới dù code vẫn hoạt động bình thường.

Quản lý quota là một phần của capacity planning và governance. Nhóm phát triển cần biết workload sẽ tiêu thụ hạn mức nào, scope của hạn mức, tốc độ tăng trưởng, mức headroom còn lại và thời gian cần để xin tăng quota. Với Java function kích hoạt bởi HTTP, queue hoặc event, cần tính cả concurrency, thời gian thực thi, batch size, downstream request rate, retry và lưu trữ message. Không đợi đến lúc production bị throttling mới bắt đầu tìm quota owner hoặc gửi yêu cầu tăng hạn mức.

## 1. Phân biệt quota, service limit và rate limit

Các thuật ngữ thường được dùng lẫn nhau nhưng có ý nghĩa khác nhau:

- **Quota:** mức sử dụng tối đa được cấp cho một scope trong một khoảng thời gian hoặc tại một thời điểm. Ví dụ số function concurrency trong một region, số resource được tạo trong project hoặc throughput được cấp cho một namespace.
- **Service limit:** giới hạn kỹ thuật của dịch vụ. Có giới hạn là quota có thể yêu cầu tăng; có giới hạn cố định không thể thay đổi theo yêu cầu thông thường.
- **Rate limit/throttle:** giới hạn tốc độ request hoặc operation trong một đơn vị thời gian. Vượt ngưỡng thường nhận lỗi throttling, `429`, `TooManyRequests` hoặc lỗi đặc thù của provider.
- **Resource configuration limit:** giới hạn cấu hình của một resource cụ thể, chẳng hạn timeout, memory, batch size hoặc kích thước request. Một số giới hạn có thể tăng bằng cách đổi cấu hình, một số là hard limit.
- **Capacity:** năng lực thực tế của dịch vụ hoặc dependency tại thời điểm sử dụng. Có quota cao không đồng nghĩa nền tảng luôn có sẵn capacity tức thời ở mọi region.

| Loại hạn mức | Ví dụ | Cách xử lý thường gặp |
|---|---|---|
| Concurrent capacity | Số Lambda execution đồng thời hoặc số Cloud Run instances | Xin tăng quota, giảm concurrency, queue buffer hoặc scale theo giới hạn |
| Request rate | API calls/giây, publish requests/giây | Rate limiter, retry có backoff, quota increase hoặc batching |
| Resource count | Số function, queue, namespace hoặc deployment | Dọn resource cũ, tái sử dụng có kiểm soát hoặc xin tăng quota |
| Throughput | Message/byte mỗi giây, stream capacity | Tăng partition/shard/unit nếu hỗ trợ, phân phối tải |
| Payload/size | Kích thước event, message, deployment package | Giảm payload, dùng object storage reference hoặc thiết kế lại |
| Storage/retention | Dung lượng, số object, retention | Lifecycle, TTL, partitioning hoặc tăng capacity |
| Fixed service limit | Giới hạn cứng theo API/runtime | Thay đổi kiến trúc hoặc chia nhỏ workload; không thể chỉ gửi ticket để bỏ giới hạn |

Quota không phải lúc nào cũng là con số toàn account. Một giới hạn có thể áp dụng riêng theo region, API, model, tier, namespace, partition, function hoặc project. Khi ghi quota vào tài liệu vận hành, luôn ghi rõ tên quota, đơn vị, scope và thời điểm kiểm tra.

## 2. Vì sao quota quan trọng với serverless?

Serverless che giấu phần lớn việc quản lý máy chủ, nhưng không loại bỏ giới hạn của tài nguyên bên dưới. Một HTTP burst có thể làm Lambda tăng concurrency; Lambda lại mở nhiều connection đến database. Một queue có thể nhận message nhanh hơn worker xử lý; backlog tăng cho đến khi chạm retention hoặc storage limit. Một event fan-out có thể tạo nhiều invocation hơn số event đầu vào.

Các triệu chứng thường gặp khi chạm quota:

- HTTP API trả `429 Too Many Requests`, `503`, hoặc lỗi throttling đặc thù.
- Function bị throttled hoặc không scale thêm execution environment.
- Event source mapping giảm tốc độ polling, stream consumer lag tăng hoặc message age tăng.
- Queue, topic, event bus hoặc subscription không tạo được do resource count quota.
- API downstream từ chối request do quota theo client, tenant hoặc region.
- Database throttling, connection exhaustion hoặc partition nóng dù function còn capacity.
- Deployment thất bại khi tạo thêm function, role, network interface hoặc resource khác.
- Chi phí tăng đột ngột vì retry storm, invocation lặp hoặc giữ capacity quá lớn.

Điều quan trọng là phân biệt quota của function với quota của dependency. Tăng Lambda concurrency có thể làm tình hình xấu hơn nếu database chỉ chịu được ít connection hoặc API đối tác có rate limit thấp hơn. Throughput hữu ích của toàn pipeline thường bị giới hạn bởi mắt xích yếu nhất:

\[
Throughput_{system} \leq \min(C_{ingress}, C_{compute}, C_{broker}, C_{database}, C_{external})
\]

Các năng lực trong công thức phải được quy đổi về cùng đơn vị, ví dụ operation/giây. Đây là mô hình capacity planning, không phải công thức billing.

## 3. Hiểu scope và cách quota được áp dụng

Trước khi kiểm tra một hạn mức, xác định quota được áp dụng ở đâu:

- **Organization/tenant:** một số chính sách hoặc resource pool được quản lý ở cấp tổ chức.
- **Account/subscription/project:** quota gắn với phạm vi billing hoặc quản lý chính.
- **Region:** quota có thể độc lập giữa các region; tăng ở region này không tự tăng ở region khác.
- **Resource/service instance:** quota có thể áp dụng riêng cho queue, namespace, database, function hoặc API.
- **Principal/client:** API quota có thể theo API key, service account, user, tenant hoặc consumer.
- **Time window:** rate limit có thể tính theo giây, phút, ngày hoặc rolling window.

Ví dụ, một tổ chức có nhiều AWS account; Lambda concurrency quota được xét theo account và region. Google Cloud quota có thể áp dụng theo project và region hoặc là quota toàn cục cho API. Azure quota thường gắn với subscription, region, SKU hoặc resource provider. Không cộng các con số từ nhiều scope khác nhau để suy ra một quota tổng mà dịch vụ không hỗ trợ.

### Quota kế thừa và quota chia sẻ

Một số quota được chia sẻ bởi nhiều resource hoặc workload trong cùng scope. Ví dụ nhiều Lambda function có thể cùng tiêu thụ concurrency account/region; nhiều ứng dụng có thể cùng gọi một API quota; nhiều queue có thể dùng chung throughput của namespace. Một function nhìn riêng có vẻ còn nhiều headroom nhưng toàn account/project đã gần giới hạn.

Lập inventory quota ở cấp scope thật sự, đồng thời phân bổ budget nội bộ cho từng service/team. Internal allocation không làm tăng quota cloud; nó giúp ngăn một workload chiếm hết tài nguyên chung.

## 4. Các nhóm quota cần kiểm tra cho serverless Java

### Compute và function execution

- Concurrent executions ở account/region hoặc plan.
- Reserved concurrency và provisioned/minimum instances.
- Số function, version, alias, revision hoặc deployment slot.
- Memory, CPU, timeout, ephemeral storage và package/image size.
- Số execution hoặc thời gian chạy theo plan.
- Scale-out rate hoặc số instance tối đa của hosting plan.

### API và ingress

- Request rate, burst capacity và quota theo API/stage/key/tenant.
- Số API, route, deployment, custom domain hoặc gateway resource.
- Payload size, connection count và timeout.
- WAF, authorizer hoặc identity provider rate limit.

### Messaging và event processing

- Queue/topic/subscription count.
- Message publish/delivery/receive throughput.
- Message size, batch size, retention và backlog capacity.
- Concurrent consumers, session/partition count và lock/visibility duration.
- Event bus rule, target, archive, replay hoặc event source mapping count.
- Stream shard/partition, read/write throughput và consumer lag.

### Data và network

- Database read/write capacity, request units, connection count và partition throughput.
- Object count, storage size, API operation rate và retention.
- VPC/VNet address space, subnet IP, network interface và private endpoint count.
- NAT gateway, egress bandwidth, DNS query hoặc connection quota nếu có.
- KMS/key operation rate và secret manager API quota.

### Governance và operations

- Số resource có thể tạo trong account/project/subscription.
- Service control plane API request rate.
- Logging ingestion, metric series, trace volume và retention.
- Build/deployment concurrency, artifact registry storage và API quota.
- Support plan hoặc quyền gửi quota request.

Không phải tất cả nhóm đều cần tăng quota. Trước tiên xác định quota thực sự có nguy cơ chạm dựa trên usage, growth và kiến trúc.

## 5. Capacity planning từ traffic và thời gian xử lý

Với function xử lý request đồng bộ, có thể ước lượng concurrency bằng định luật Little:

\[
C \approx \lambda \times T
\]

Trong đó:

- \(C\): số invocation đồng thời cần thiết.
- \(\lambda\): tốc độ request đến, tính bằng request/giây.
- \(T\): thời gian xử lý trung bình, tính bằng giây.

Ví dụ, peak traffic là 120 request/giây và thời gian xử lý trung bình 0,4 giây:

\[
C \approx 120 \times 0.4 = 48
\]

Nếu dành 30% headroom cho burst và biến động, mục tiêu capacity ban đầu khoảng 63 concurrency. Đây chỉ là ước lượng; cần kiểm tra duration distribution, burst profile, cold start, retries, downstream latency và provider scaling behavior. Với p95/p99, không thay average duration bằng percentile một cách máy móc rồi coi đó là sizing chính xác.

### Tính cả fan-out và downstream calls

Nếu mỗi request tạo 3 message và mỗi message kích hoạt một worker, số invocation downstream có thể lớn hơn nhiều so với số HTTP request. Nếu một worker gọi database 2 lần và external API 1 lần, operation rate downstream phải được tính từ số record thực tế và số call mỗi record.

Ví dụ:

| Thành phần | Tốc độ đầu vào | Số operation mỗi đơn vị | Nhu cầu ước tính |
|---|---:|---:|---:|
| HTTP API | 100 request/s | 1 invocation | 100 invocation/s |
| Queue producer | 100 request/s | 3 message/request | 300 message/s |
| Worker | 300 message/s | 2 DB calls/message | 600 DB calls/s |
| Notification | 300 message/s | 1 external API call/message | 300 API calls/s |

Nếu database chỉ chịu được 400 call/s trong cấu hình hiện tại, tăng worker concurrency không giúp hoàn tất nhanh hơn một cách bền vững. Cần bulk write, cache, giảm số call, giới hạn concurrency hoặc tăng capacity database trước.

### Tính quota theo peak và retry

Không sizing chỉ theo average. Dùng peak dự kiến, burst, growth và retry amplification. Nếu 5% message lỗi và mỗi message được retry tối đa 3 lần, tổng attempt có thể tăng đáng kể so với số message gốc. Một downstream outage có thể khiến hầu hết message retry, tạo tải lớn đúng lúc hệ thống đang yếu.

Thiết kế retry có exponential backoff, jitter, retry budget và DLQ. Capacity plan cần mô phỏng tình huống lỗi chứ không chỉ happy path.

## 6. Tính headroom và thời điểm cần yêu cầu tăng quota

Với quota giới hạn \(Q\) và peak usage dự báo \(P\), mức sử dụng là:

\[
Utilization = \frac{P}{Q} \times 100\%
\]

Headroom tuyệt đối:

\[
Headroom = Q - P
\]

Nếu peak dự báo là 720 và quota là 1.000, utilization là 72% và headroom là 280 đơn vị. Đây chưa phải lý do tự động phải tăng quota; cần xem growth rate, thời gian phê duyệt, burst, DR/failover và mức độ quan trọng của dịch vụ.

Một chính sách vận hành có thể cảnh báo ở 70%, tạo ticket review ở 80% và bắt đầu request trước khi forecast vượt 85–90%. Các ngưỡng chỉ là ví dụ; workload critical hoặc quota request mất nhiều tuần có thể cần ngưỡng thấp hơn.

### Dự báo thời điểm chạm hạn mức

Nếu usage tăng đều với tốc độ \(g\) đơn vị/ngày, thời gian ước tính đến quota:

\[
DaysToLimit \approx \frac{Q - U}{g}
\]

Trong đó \(U\) là usage hiện tại. Công thức không phù hợp nếu traffic theo mùa hoặc tăng theo bậc; khi đó dùng forecast theo campaign, customer onboarding, batch schedule và growth plan.

Đừng chờ đến 100%. Khi chạm quota, request increase có thể chưa được duyệt ngay; service có thể đã bị throttling trong thời gian chờ.

## 7. Quota trong AWS serverless

AWS Service Quotas là điểm bắt đầu để xem quota theo service và gửi yêu cầu tăng đối với quota được hỗ trợ. Một số quota có thể tự điều chỉnh hoặc có quy trình khác; một số service limit là cố định. Kiểm tra quota tại đúng account và region đang chạy workload.

### AWS Lambda

Các hạn mức cần xem xét gồm:

- Account concurrency quota theo region.
- Reserved concurrency phân bổ cho từng function.
- Provisioned Concurrency và capacity đã cấu hình.
- Function memory, timeout, ephemeral storage và deployment package/container limits.
- Số request/invocation, scaling behavior và event source mapping configuration.

Reserved concurrency vừa dành riêng capacity cho function vừa giới hạn mức tối đa function có thể dùng. Nếu đặt quá thấp, function có thể throttled dù account còn concurrency. Nếu đặt quá cao, function có thể chiếm phần lớn concurrency chia sẻ. Provisioned Concurrency chuẩn bị execution environment trước nhưng tiêu thụ capacity và có chi phí riêng theo pricing model.

### API Gateway và ingress

Kiểm tra throttling account/region, API/stage usage plan, route/integration limits và payload size. Throttling API Gateway có thể xảy ra trước khi Lambda được gọi; tăng Lambda concurrency không giải quyết được quota gateway. WAF hoặc authorizer cũng có thể có rate limit riêng.

### SQS, SNS và EventBridge

- SQS: queue count, message size, retention, API request throughput và FIFO throughput/partition behavior.
- SNS: topic/subscription count và publish/delivery throughput theo loại topic/region.
- EventBridge: event bus/rule/target quotas, `PutEvents` throughput, archive/replay và target invocation limits.

SQS có thể hấp thụ burst nhưng backlog vẫn cần storage và retention. Nếu consumer chậm, theo dõi `ApproximateAgeOfOldestMessage`, visible/in-flight messages và DLQ. Đừng coi queue là capacity vô hạn.

### Kinesis, DynamoDB và Step Functions

- Kinesis: shard count, read/write throughput, enhanced fan-out hoặc consumer limits theo cấu hình.
- DynamoDB: on-demand/provisioned throughput, partition-level hot key, table/index limits và account-level quotas.
- Step Functions: state transition throughput, execution start rate, concurrent executions và API-specific quotas theo loại workflow.

Tăng quota account-level không loại bỏ partition hot key hoặc giới hạn transaction của một resource cụ thể. Phải xác định bottleneck ở scope đúng.

### Quy trình request tăng quota AWS

1. Chọn account, region và service trong AWS Service Quotas.
2. Xác định đúng quota name, quota code, current value và adjustable status.
3. Xem usage/CloudWatch metrics và kiểm tra các workload khác dùng chung quota.
4. Chọn **Request quota increase** nếu quota hỗ trợ; nhập giá trị mong muốn và thông tin giải trình.
5. Nếu quota không xuất hiện hoặc cần review đặc biệt, mở AWS Support case theo quy trình của account/support plan.
6. Theo dõi trạng thái request; không coi việc gửi request là đã được cấp quota.
7. Sau khi được duyệt, xác minh quota effective ở đúng region/account và chạy load test có kiểm soát.

Quyền xem và gửi quota request phụ thuộc IAM permission và support plan. Tăng một quota có thể yêu cầu AWS review capacity hoặc thông tin kiến trúc bổ sung.

## 8. Quota trong Azure Functions và dịch vụ liên quan

Azure quota có thể gắn với subscription, region, SKU, resource provider hoặc một resource cụ thể. Phân biệt quota của hosting plan với quota của dịch vụ downstream.

### Azure Functions hosting

Kiểm tra các yếu tố:

- Hosting plan và SKU đang dùng (Consumption, Flex Consumption, Premium, Dedicated hoặc plan phù hợp tại thời điểm triển khai).
- Số instance tối đa và cách scale theo plan/region.
- Memory/CPU, execution duration, storage và networking integration.
- Số Function App, deployment slot và resource provider quota.
- Concurrency của trigger và giới hạn của extension.

Các giới hạn cụ thể khác nhau theo hosting plan, OS, region và runtime. Không áp dụng một con số concurrency hoặc execution time cho mọi Function App. Kiểm tra trang quota/limit của đúng plan và region.

### Service Bus, Event Hubs và Event Grid

- Service Bus: namespace, messaging units/SKU, queue/topic/subscription count, connection và message throughput.
- Event Hubs: throughput units hoặc processing units theo tier, partition count, consumer groups và retention.
- Event Grid: topic/subscription resource limits, publish/delivery throughput và retry behavior.

Nếu Service Bus lock duration hoặc prefetch không phù hợp, message có thể bị giao lại dù quota chưa chạm. Nếu Event Hubs partition không đủ, tăng instance không tạo thêm parallelism hiệu quả.

### API Management, Storage và database

Kiểm tra API Management tier/capacity, rate-limit policy, Storage account throughput/transaction limits, Cosmos DB RU/s và hot partition, SQL connection/resource limits. Một quota tăng ở Function App không tự tăng quota Cosmos DB hoặc API Management.

### Quy trình request tăng quota Azure

1. Mở Azure Portal, chọn đúng subscription và region.
2. Vào trang **Quotas** hoặc quota blade của dịch vụ/plan tương ứng; một số dịch vụ có mục quota riêng.
3. Chọn provider, service, location, SKU và quota cần tăng.
4. Xem current usage, current limit, availability và trạng thái request increase.
5. Gửi request với desired limit, thời gian cần, workload forecast và business justification.
6. Nếu quota không hỗ trợ self-service, tạo Support request cho đúng service/subscription.
7. Theo dõi approval, xác minh limit mới và kiểm tra các dependency quota liên quan.

Một số quota Azure chỉ tăng được qua support, một số không adjustable hoặc phụ thuộc capacity của region/SKU. Có thể cần đăng ký resource provider hoặc chọn region/plan khác trước khi triển khai.

## 9. Quota trong Google Cloud serverless

Google Cloud phân biệt **quotas** và **system limits**. Quota thường có thể quản lý/request increase theo project, region hoặc API; system limit có thể là giới hạn cố định. Quota API/service usage và resource quota không phải lúc nào cũng có cùng scope.

### Cloud Run và Cloud Functions

Kiểm tra:

- Maximum instances/minimum instances và concurrency per instance.
- CPU, memory, request/instance limits và regional capacity.
- Số service/revision/function và deployment resource.
- Cloud Build, Artifact Registry và deployment API quota.
- Ingress/egress, VPC connector hoặc Direct VPC egress limits khi dùng networking.

Cloud Run concurrency là số request có thể xử lý đồng thời trên một instance; maximum instances giới hạn scale-out của service. Tăng concurrency có thể giảm instance count nhưng tăng contention/memory trong một instance. Tăng maximum instances có thể tăng tải database và external APIs. Chọn hai thông số cùng capacity downstream.

### Pub/Sub, Eventarc và API quotas

- Pub/Sub: publish/subscribe throughput, outstanding messages/bytes, ack deadline và subscription count.
- Eventarc: trigger/resource quotas, delivery rate và target invocation capacity.
- API Gateway/Endpoints: request quota và rate limit theo service/API/consumer.
- Cloud Logging/Monitoring: ingestion, metric descriptor/time series và API quota.

Pub/Sub có thể giữ backlog, nhưng message age, retention, storage và subscriber capacity vẫn có giới hạn. Khi subscriber bị throttled, điều chỉnh flow control, ack deadline và concurrency trước khi chỉ tăng publish quota.

### Quy trình request tăng quota Google Cloud

1. Chọn đúng project trong Google Cloud Console.
2. Mở **IAM & Admin → Quotas & System Limits** hoặc trang quota của service/API.
3. Lọc theo service, metric, region/location và quota dimension.
4. Kiểm tra current usage, limit, project và billing status.
5. Chọn quota hỗ trợ chỉnh sửa và gửi request increase với giá trị mong muốn.
6. Nếu không có nút chỉnh hoặc request cần review, dùng support/request flow được hiển thị cho project và service đó.
7. Theo dõi trạng thái, xác minh quota effective và chạy test ở đúng project/region.

Quyền xem/chỉnh quota phụ thuộc IAM role và service. Một số quota cần billing account hoạt động hoặc support entitlement. Không giả định tăng quota ở project thử nghiệm sẽ tự áp dụng sang project production.

## 10. Chuẩn bị hồ sơ yêu cầu tăng quota

Một request tốt giải thích vì sao cần tăng và chứng minh con số đề xuất dựa trên workload. Tránh gửi một câu “cần scale lớn hơn” mà không có số liệu.

Thông tin nên chuẩn bị:

| Thông tin | Nội dung |
|---|---|
| Scope | Account/subscription/project, region, service, resource ID nếu có |
| Quota | Tên chính xác, metric/code, đơn vị và current limit |
| Current usage | Average, peak, burst, utilization và thời điểm đo |
| Desired limit | Giá trị cần tăng và lý do chọn giá trị đó |
| Workload | Request/message rate, concurrency, payload, duration và growth |
| Architecture | Function, queue, database, API, fan-out và dependency limits |
| Evidence | Load test, dashboard, logs, forecast, throttling events |
| Timeline | Ngày cần quota và kế hoạch rollout/campaign |
| Risk controls | Backoff, rate limit, reserved concurrency, queue, DLQ và alarms |
| Contact/owner | Team vận hành, technical owner và escalation contact |

### Cách tính desired limit

Giả sử dự báo peak concurrency 1.200, đã gồm 20% headroom. Nếu hiện tại quota là 1.000, request có thể đề xuất mức phù hợp với forecast và kế hoạch tăng trưởng, chẳng hạn 1.500, thay vì yêu cầu một con số cực lớn không có giải trình. Cần tính cả workload khác dùng chung quota và khả năng failover.

Desired limit không nên chỉ bằng peak đo được hôm nay. Hãy tính thời gian đến lần mở rộng tiếp theo, thời gian provider xét duyệt và độ bất định của forecast. Nhưng cũng không xin quota cao không cần thiết: quota lớn có thể tăng blast radius nếu workload lỗi hoặc bị lạm dụng.

### Mẫu nội dung request

```text
Service / quota:
Account, project or subscription:
Region / location:
Current quota and unit:
Requested quota and unit:
Current peak usage:
Expected peak usage and growth date:
Workload description:
Architecture and dependent services:
Load-test or monitoring evidence:
Throttling/error impact if not increased:
Rate limiting, backoff and backpressure controls:
Deployment/rollout date:
Technical owner and contact:
```

Đính kèm dashboard hoặc test report đã loại bỏ secret và dữ liệu cá nhân. Nếu request liên quan nhiều quota, nêu rõ thứ tự phụ thuộc và quota nào là critical path.

## 11. Kiểm tra quota trước khi mở rộng

Tích hợp quota review vào release planning:

1. Đọc kiến trúc và xác định resource/operation phát sinh khi traffic tăng.
2. Liệt kê quota theo scope, region và owner.
3. Lấy current usage và peak từ telemetry.
4. Tính forecast cho traffic, concurrency, storage, message backlog và downstream calls.
5. Tính headroom sau khi cộng growth, burst, retry và DR requirement.
6. Xác định quota adjustable, fixed limit hoặc resource configuration.
7. Gửi request sớm cho quota cần tăng; ghi ticket ID, owner và due date.
8. Chỉ mở rollout theo từng giai đoạn sau khi quota effective và dependency capacity đã xác minh.

### Release gate

Một release mở rộng traffic nên bị chặn hoặc yêu cầu phê duyệt nếu:

- Forecast peak vượt quota hiện tại hoặc headroom dưới ngưỡng đã đặt.
- Quota request chưa được duyệt và ngày mở rộng đã đến gần.
- Downstream API/database không có capacity tương ứng.
- Region DR chưa có quota/capacity đủ cho failover dự kiến.
- Không có alarm, rate limit hoặc rollback plan.

Đây là governance gate nội bộ; có thể triển khai bằng checklist, change approval hoặc policy-as-code. Không phải mọi thay đổi nhỏ đều cần quy trình phê duyệt nặng, nhưng mở rộng production cần có bằng chứng capacity.

## 12. Theo dõi quota và đặt cảnh báo

Theo dõi cả **quota usage** và **tín hiệu gần chạm quota**. Một số quota có metric chính thức; một số phải tổng hợp từ usage hoặc service metrics. Ghi rõ dữ liệu nào là measured, estimated hoặc manual snapshot.

Các tín hiệu hữu ích:

- Current quota, current usage và utilization percentage.
- Peak/maximum utilization theo cửa sổ 5 phút, 1 giờ và 1 ngày.
- Throttling count, `429`, `TooManyRequests`, `ProvisionedThroughputExceeded` hoặc lỗi tương đương.
- Lambda throttles, concurrent executions và reserved concurrency utilization.
- Queue depth, oldest message age, DLQ depth và retry count.
- Stream iterator age/consumer lag và partition throughput.
- Database throttling, connection saturation và API downstream rate-limit response.
- Resource create failures và deployment failures do quota.

### Ngưỡng cảnh báo gợi ý

| Mức | Ví dụ ngưỡng | Hành động |
|---|---:|---|
| Informational | 60–70% | Ghi nhận xu hướng và kiểm tra forecast |
| Warning | 75–80% | Thông báo owner, review growth và dependency quotas |
| Action required | 85–90% | Mở quota request hoặc kế hoạch giảm tải |
| Critical | Gần 100% hoặc có throttling | Kích hoạt incident/capacity runbook, giới hạn traffic |

Ngưỡng cần điều chỉnh theo volatility và lead time. Với quota có thể mất nhiều tuần để tăng, cảnh báo ở mức thấp hơn. Với quota tự động tăng theo usage, vẫn theo dõi throttling và hard limits.

Không tạo metric dimension cho từng resource ID nếu cardinality quá cao. Dùng dashboard theo service, region, account/project, environment và owner; lưu resource-level detail trong log/inventory.

## 13. Java: xử lý throttling và retry có giới hạn

Khi downstream trả lỗi throttling, Java function không nên retry ngay lập tức liên tục. Retry tức thì có thể làm tăng tải và tạo retry storm. Dùng exponential backoff, jitter, giới hạn attempt/deadline và phân loại lỗi.

Ví dụ helper minh họa:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryPolicy {
    public static Duration delay(int attempt,
                                 Duration base,
                                 Duration maximum) {
        long baseMillis = base.toMillis();
        long maximumMillis = maximum.toMillis();
        if (baseMillis <= 0 || maximumMillis <= 0
                || baseMillis > maximumMillis) {
            throw new IllegalArgumentException("Invalid retry delay bounds");
        }
        int exponent = Math.min(Math.max(attempt - 1, 0), 20);
        long multiplier = 1L << exponent;
        long scaled = baseMillis > maximumMillis / multiplier
                ? maximumMillis : baseMillis * multiplier;
        long capMillis = Math.min(maximumMillis, scaled);
        long jitterMillis = ThreadLocalRandom.current()
                .nextLong(capMillis);
        return Duration.ofMillis(jitterMillis);
    }

    private RetryPolicy() {}
}
```

Đây là full-jitter backoff minh họa; phép nhân được chặn theo `maximumMillis` để tránh overflow. Trong production, cần thêm tổng deadline, tôn trọng `Retry-After` nếu service trả header đó và chỉ retry lỗi tạm thời như throttling/timeout/network reset. Lỗi authorization, validation hoặc resource not found thường không nên retry vô hạn.

### Không giữ Lambda chờ retry quá lâu

Nếu trigger là SQS hoặc stream, thường nên để broker/event source quản lý retry theo policy thay vì sleep trong function nhiều lần. Sleep tiêu thụ execution duration và memory trong khi không làm tăng capacity. Trả partial batch failure hoặc throw theo semantics của trigger, rồi để retry policy/backoff/DLQ xử lý.

Với HTTP synchronous request, retry downstream chỉ trong phần latency budget còn lại. Nếu downstream đang throttle, có thể trả `429` hoặc `503` có `Retry-After` theo API contract, hoặc enqueue công việc để xử lý bất đồng bộ.

### Rate limiter và concurrency limiter

Nếu external API chỉ cho phép một số request/giây, dùng token bucket/leaky bucket hoặc distributed rate limiter để điều tiết. Local limiter trong mỗi Lambda instance không đảm bảo quota toàn hệ thống vì nhiều instance có thể cùng chạy. Với global quota, cần coordinator/distributed limiter hoặc giới hạn tổng concurrency và ước lượng request rate từ concurrency × request rate mỗi invocation.

## 14. Java: bulkhead và backpressure cho downstream

Giới hạn số request đồng thời đến database/API giúp tránh một function scale-out làm cạn dependency. Một semaphore trong JVM chỉ giới hạn mỗi execution environment; nếu cần giới hạn toàn account/service, cần kết hợp event source maximum concurrency, reserved concurrency, queue và giới hạn phía downstream.

Ví dụ local bulkhead đơn giản:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class DownstreamBulkhead {
    private final Semaphore permits = new Semaphore(8);

    public <T> T execute(CallableOperation<T> operation) throws Exception {
        if (!permits.tryAcquire(100, TimeUnit.MILLISECONDS)) {
            throw new DownstreamSaturatedException();
        }
        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }

    @FunctionalInterface
    public interface CallableOperation<T> {
        T call() throws Exception;
    }
}
```

Semaphore trên chỉ bảo vệ một instance. Không nhân bản nó rồi cho rằng tổng concurrency đã được giới hạn ở mức 8. Khi có nhiều Lambda environment, tổng permit có thể lên tới `8 × số environment`. Hãy đặt limit ở event source/function hoặc dùng cơ chế phân phối nếu quota downstream là toàn cục.

### Queue làm bộ đệm

Queue hấp thụ burst khi producer nhanh hơn consumer. Giới hạn consumer concurrency để giữ downstream trong capacity; backlog sẽ được xử lý dần. Cần theo dõi oldest message age và đảm bảo retention đủ cho thời gian phục hồi. Nếu backlog tăng liên tục, queue chỉ trì hoãn sự cố; phải tăng throughput bền vững hoặc giảm ingest rate.

## 15. Khi quota chưa được duyệt

Không mặc định request sẽ được chấp thuận đúng thời hạn. Chuẩn bị các phương án:

- Giảm peak bằng rate limiting, admission control hoặc lịch xử lý phân tán.
- Dùng queue để làm phẳng burst và giới hạn consumer concurrency.
- Batch/bulk operation để giảm số API/database calls.
- Giảm fan-out, loại duplicate và cache dữ liệu phù hợp.
- Chia workload theo account/project/subscription hoặc region nếu kiến trúc và chính sách cho phép.
- Chuyển sang SKU/plan/region có quota phù hợp sau khi đánh giá latency, compliance và cost.
- Giảm scope rollout, bật feature theo tenant hoặc percentage traffic.
- Tạm hoãn campaign/migration không thiết yếu.
- Thiết kế degradation có chủ đích, ví dụ hoãn notification hoặc analytics nhưng giữ giao dịch cốt lõi.

Không chia workload sang nhiều account/project chỉ để né quota mà không có governance. Việc phân tán có thể tăng complexity, chi phí network, audit và rủi ro dữ liệu. Chỉ dùng khi đó là kiến trúc được quản trị và provider cho phép.

## 16. Multi-region và disaster recovery

Quota ở region chính không bảo đảm region dự phòng có cùng mức. Khi thiết kế active-active hoặc active-passive, tính capacity cho từng region:

- Active-active: mỗi region xử lý một phần traffic nhưng phải có headroom khi một region mất.
- Active-passive: region standby có thể cần đủ quota để tiếp nhận toàn bộ peak traffic sau failover.
- Data replication: stream, database, object storage và KMS có quota riêng ở region đích.
- Identity/network: role, private endpoint, IP space và service connection cũng phải sẵn sàng.
- Deployment: function, version, alias, queue, event mapping và API quota cần được chuẩn bị trước.

Chạy DR exercise có kiểm soát để xác minh quota/capacity thật, không chỉ kiểm tra resource đã được tạo. Nếu chỉ failover một phần traffic, ghi rõ tỷ lệ và cách admission control hoạt động.

## 17. Quota as Code và governance

Không phải quota nào cũng có thể khai báo hoặc tăng bằng Infrastructure as Code. Tuy vậy, có thể quản lý phần cấu hình và bằng chứng liên quan:

- Lưu desired concurrency, maximum instances, batch size, rate limit và reserved capacity trong template.
- Lưu quota inventory theo service/scope/region/owner và ngày kiểm tra.
- Dùng CI preflight để kiểm tra quota API hoặc so sánh usage với ngưỡng đã định.
- Tạo change request khi forecast vượt headroom.
- Lưu quota request ID, approval, effective value và evidence.
- Đặt alert và runbook trong monitoring/IaC.
- Rà soát quota định kỳ và sau thay đổi lớn về traffic/architecture.

Ví dụ inventory dạng bảng:

| Service | Scope | Quota | Current limit | Peak forecast | Owner | Status |
|---|---|---|---:|---:|---|---|
| Lambda | account A / region X | Concurrent executions | 1.000 | 1.300 | Platform | Request pending |
| API Gateway | account A / region X | Request rate | 5.000/s | 3.500/s | API team | Healthy |
| SQS | account A / region X | API throughput | Theo loại queue | ước lượng từ load test | Orders | Review |
| Database | cluster orders-prod | Connections | 400 | 520 | Data team | Mitigation needed |

Giá trị trong bảng chỉ minh họa; cần thay bằng quota thực tế của môi trường. Với quota không có một current limit duy nhất, ghi rõ cách đo và metric thay thế.

### CI preflight và rollout gate

Một bước kiểm tra trước release có thể:

1. Đọc environment/region/account/project từ deployment target.
2. Lấy quota/usage từ API provider hoặc inventory được cập nhật.
3. So sánh forecast peak + headroom với current limit.
4. Kiểm tra dependency quotas (database, broker, API, network).
5. Fail hoặc yêu cầu approval nếu không đủ capacity.

Không giả định mọi quota đều có API query thống nhất hoặc trả dữ liệu real-time. Nếu quota được cập nhật thủ công, ghi timestamp và owner để tránh dùng số liệu quá cũ.

## 18. Vai trò và trách nhiệm

Quản lý quota hiệu quả cần phân định owner:

| Vai trò | Trách nhiệm |
|---|---|
| Application team | Dự báo traffic, đo concurrency/throughput, tối ưu code và xử lý throttling |
| Platform/cloud team | Theo dõi quota, gửi request, quản lý account/project/subscription và region capacity |
| Data team | Xác nhận database throughput, connection, partition và storage limits |
| Security/governance | Kiểm tra quyền request, scope, audit, policy và rủi ro khi chia workload |
| SRE/operations | Đặt alert, incident runbook, load test và DR exercise |
| Product/business owner | Cung cấp timeline campaign, growth forecast và mức độ ưu tiên nghiệp vụ |

Mỗi quota quan trọng cần một owner rõ ràng. Tránh tình trạng application team nghĩ cloud team đang xin quota trong khi cloud team không biết ngày launch hoặc forecast peak.

## 19. Quy trình ứng phó khi chạm quota

Khi thấy throttling hoặc lỗi quota trong production:

1. Xác định service, quota name, scope và region gây lỗi.
2. Kiểm tra error code, request ID, metric và thời điểm bắt đầu.
3. Phân biệt quota exhaustion với service outage, IAM denial, network timeout hoặc downstream failure.
4. Giới hạn traffic/concurrency để ngăn retry storm.
5. Giữ message trong queue nếu retention và capacity cho phép; tránh purge hoặc drop dữ liệu.
6. Bật fallback/degradation đã thiết kế và thông báo owner.
7. Gửi quota request hoặc support case nếu adjustable; đồng thời áp dụng mitigation.
8. Sau khi limit tăng, xác minh effective value, load test có kiểm soát và mở traffic dần.
9. Cập nhật capacity model, alert threshold và runbook để tránh lặp lại.

Không tự động retry liên tục lỗi quota. Với HTTP, phản hồi `429`/`503` phù hợp; với message, dùng backoff, visibility/lock timeout và DLQ. Nếu downstream đã quá tải, retry nhanh sẽ làm outage kéo dài.

## 20. Checklist trước khi mở rộng production

### Inventory và forecast

- [ ] Đã liệt kê quota theo account/project/subscription, region, service và resource.
- [ ] Đã phân biệt adjustable quota, fixed service limit, rate limit và configuration limit.
- [ ] Đã đo average, peak, burst, growth và retry amplification.
- [ ] Đã tính concurrency từ arrival rate và duration.
- [ ] Đã tính fan-out, database/API calls, message backlog, storage và network usage.
- [ ] Đã tính headroom và thời gian dự kiến đến quota.

### Request và approval

- [ ] Quota cần tăng có tên, scope, unit và current value chính xác.
- [ ] Desired value dựa trên forecast và headroom có giải trình.
- [ ] Request được gửi đủ sớm theo lead time của provider.
- [ ] Có request ID, owner, due date và trạng thái approval.
- [ ] Quota effective đã được xác minh ở đúng account/project/subscription và region.

### Runtime và dependency

- [ ] Function concurrency không vượt khả năng database/API/broker.
- [ ] Có rate limit, backoff/jitter, retry budget và idempotency.
- [ ] Queue/stream có capacity, retention, DLQ và backpressure phù hợp.
- [ ] Batch size/window và fan-out đã được load test.
- [ ] Multi-region/DR có quota và network/data capacity tương ứng.

### Operations và governance

- [ ] Có dashboard utilization, throttles, queue age, consumer lag và downstream saturation.
- [ ] Alert threshold phù hợp với volatility và quota request lead time.
- [ ] Có rollout gate, canary, rollback và degradation plan.
- [ ] Quota inventory có owner và ngày review.
- [ ] Có runbook xử lý quota exhaustion và post-incident review.

Quản lý quota tốt bắt đầu trước khi mở rộng: hiểu hạn mức theo đúng scope, dự báo peak và retry, kiểm tra mọi dependency, yêu cầu tăng sớm và duy trì headroom. Quota increase giúp mở rộng trần sử dụng nhưng không tự bảo đảm capacity hay khả năng chịu tải của toàn pipeline. Với Java serverless, hãy kết hợp quota planning với rate limiting, queue buffering, concurrency control, idempotent retry, observability và DR testing để tăng traffic mà vẫn giữ được latency, độ tin cậy và chi phí trong giới hạn đã định.
