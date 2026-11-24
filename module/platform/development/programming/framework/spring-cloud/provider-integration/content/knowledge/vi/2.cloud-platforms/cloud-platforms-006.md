# Hạn ngạch, giới hạn tốc độ và mô hình tính phí theo mức sử dụng

Một ứng dụng Spring Boot tích hợp dịch vụ managed có thể chạy ổn định lúc thử nghiệm nhưng phát sinh lỗi khi tăng tải: ứng dụng mở quá nhiều kết nối database, API storage trả về lỗi do vượt tốc độ, queue tồn đọng message, hoặc hóa đơn cloud tăng nhanh dù không bổ sung máy chủ. Những hiện tượng này liên quan đến ba cơ chế cần phân biệt: **hạn ngạch (quota)**, **giới hạn tốc độ (rate limit/throttling)** và **tính phí theo mức sử dụng (usage-based pricing)**.

Trong chương **Nền tảng đám mây** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, bài học này cung cấp nền tảng để thực hành tích hợp Spring Boot với AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Khi gọi storage, messaging, database hay secret manager, nhóm phát triển cần biết dịch vụ giới hạn theo tài khoản/project/region ra sao, khi nào được retry, cách giữ an toàn dữ liệu và danh tính, cách đo nhu cầu thực tế và cách tránh chi phí bất ngờ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **quota, hard limit, rate limit, burst, concurrency limit, throughput, capacity** và **budget**.
- Xác định đơn vị áp hạn ngạch: account, subscription, project, region, service, tài nguyên hoặc principal.
- Hiểu các phản hồi như **429, 503, ResourceExhausted, Throttling**, phân loại được lỗi tạm thời với lỗi cấu hình/quyền.
- Thiết kế giới hạn lưu lượng, retry có backoff/jitter, timeout, idempotency và backpressure cho ứng dụng Spring Boot.
- Đọc mô hình tính phí object storage, messaging, database, secret và truyền dữ liệu của AWS/Azure/Google Cloud.
- Lập dự toán, đặt budget/cảnh báo, gắn tag/label phân bổ chi phí và kiểm thử ở tải có kiểm soát.

## 2. Các khái niệm không được đánh đồng

**Quota (hạn ngạch)** là ngưỡng được nhà cung cấp đặt cho một đại lượng sử dụng, chẳng hạn số VM, số instance database, số lần gọi API trong một phút hoặc tổng dung lượng tài nguyên. Quota có thể là mặc định, cố định, có thể yêu cầu nâng hoặc phụ thuộc cấp dịch vụ.

**Service limit/hard limit** là giới hạn kỹ thuật hoặc sản phẩm không nhất thiết có quy trình nâng, chẳng hạn kích thước tối đa của một message, độ dài tên tài nguyên hoặc số thành phần mà một tier cho phép. Một quota có thể chỉnh không có nghĩa mọi giới hạn đều chỉnh được.

**Rate limit** giới hạn tốc độ yêu cầu trong một khoảng thời gian, chẳng hạn request/giây hoặc request/phút. **Throttling** là hành vi làm chậm, từ chối hay hạn chế request khi vượt giới hạn hoặc khi dịch vụ cần bảo vệ năng lực xử lý. Có dịch vụ áp giới hạn tốc độ động, không công bố một con số cố định cho mọi trường hợp.

**Burst capacity** cho phép xử lý một đợt request ngắn lớn hơn tốc độ ổn định trong những điều kiện nhất định; sau đợt đó, request có thể bị hạn chế. **Concurrency limit** đo số tác vụ đang chạy đồng thời, không đo trực tiếp số request/giây.

**Throughput** là lượng công việc thực sự được xử lý mỗi đơn vị thời gian: message/giây, MiB/giây hoặc transactions/giây. Throughput có thể phụ thuộc kích thước dữ liệu, loại operation, mạng, Region, phân vùng dữ liệu và cấu hình tier.

**Budget** là mục tiêu chi tiêu và cơ chế theo dõi/cảnh báo. Trong đa số công cụ quản trị cloud, **budget alert không phải giới hạn cứng tự động dừng mọi chi phí**. Một số sản phẩm có biện pháp giới hạn hoặc tự động hóa riêng, nhưng phải cấu hình và hiểu tác động trước khi dùng.

| Thuật ngữ | Ví dụ | Tác động khi chạm ngưỡng | Cách xử lý thường gặp |
|---|---|---|---|
| Resource quota | Số instance DB tối đa trong Region | Không tạo thêm tài nguyên | Xem scope, giải phóng tài nguyên, xin tăng quota nếu hỗ trợ |
| Rate quota | Số API calls trong một phút | 429 hoặc mã throttling đặc thù | Giảm tải, backoff, cache, batch |
| Concurrency limit | Số kết nối DB, request đồng thời | Chờ pool, bị từ chối, timeout | Pool sizing, giới hạn concurrency, scale có điều kiện |
| Payload/service limit | Kích thước message tối đa | Lỗi validation, request không hợp lệ | Chia payload hoặc lưu ngoài queue, gửi reference |
| Throughput capacity | Dung lượng xử lý message hoặc I/O | Queue backlog, latency cao | Điều chỉnh tier/capacity, batch, worker phù hợp |
| Budget | Cảnh báo chi tiêu tháng | Thông báo hoặc automation được thiết lập | Điều tra usage và chính sách ngăn chi phí |
| Billing minimum/rounding | Đơn vị request, GB-tháng, giờ/giây | Chi phí khác phép nhân giản lược | Đọc bảng giá và cách làm tròn từng SKU |

> **Quota không phải giá tiền, budget không phải quota, và quota không phải cam kết SLA.** Một ứng dụng chưa chạm quota vẫn có thể tốn kém hoặc hoạt động chậm vì nguyên nhân khác.

## 3. Một yêu cầu cloud có thể bị giới hạn ở nhiều lớp

Giả sử Spring Boot nhận HTTP request, truy vấn database rồi gửi event lên queue. Request chịu nhiều ranh giới:

~~~mermaid
flowchart LR
    U["Client traffic"] --> G["API gateway / ingress limit"]
    G --> APP["Spring Boot<br/>threads + connection pool"]
    APP --> SDK["SDK throttling / retry policy"]
    SDK --> SVC["Managed API<br/>rate + capacity"]
    SVC --> Q["Queue / database / storage"]
    Q --> B["Billing meters"]
    MET["Metrics + alerts"] -. "Quan sát" .-> APP
    MET -. "Quan sát" .-> SVC
    MET -. "Theo dõi chi phí" .-> B
~~~

Các ranh giới có thể áp dụng đồng thời: gateway chỉ nhận một số request, pool kết nối ứng dụng chỉ cho phép một số request chờ, SDK giới hạn attempts, dịch vụ đặt quota riêng cho API, còn database có giới hạn connection hoặc tài nguyên CPU/I/O.

### 3.1. Tính tốc độ khác tính đồng thời

Nếu một service nhận trung bình **50 request/giây**, mỗi request giữ connection trong **0,2 giây**, số request đang xử lý trung bình xấp xỉ:

\[
L = \lambda \times W = 50 \times 0{,}2 = 10
\]

Đây là ứng dụng đơn giản của **Little's Law** khi hệ thống ở trạng thái ổn định. Nếu latency tăng lên **2 giây** trong khi tốc độ đến giữ nguyên, số request đồng thời trung bình có thể tăng lên gần **100**. Khi connection pool chỉ có 20 connection, request sẽ bắt đầu xếp hàng hoặc timeout.

Vì thế, tăng số thread hoặc replica không tự giải quyết lỗi quota. Nó có thể tăng **tổng số kết nối** và khiến managed database quá tải.

### 3.2. Burst và token bucket

Một mô hình rate limiter phổ biến là **token bucket**: token được nạp theo tốc độ ổn định, mỗi request tiêu thụ token; bucket giữ số token tối đa để cho phép burst ngắn. Ví dụ limiter của ứng dụng nạp **10 token/giây**, giữ tối đa **30 token**. Sau thời gian rảnh có thể chấp nhận một burst tới 30 request, nhưng không thể duy trì 30 request mỗi giây mãi mãi.

Đây chỉ là **mô hình toán học minh họa**; cloud provider có thể sử dụng cơ chế hoặc nhiều lớp giới hạn khác. Một rate limiter đặt riêng trên **mỗi instance Spring Boot** không kiểm soát tổng tốc độ trên toàn deployment. Với 10 replica, mỗi replica cho 10 request/giây thì tổng tối đa lý thuyết có thể lên đến 100 request/giây. Nếu cần giới hạn toàn hệ thống, phải dùng quota phân bổ theo replica hoặc limiter phối hợp phân tán.

## 4. Phạm vi quota và trách nhiệm quản lý

Hạn ngạch phải được tìm theo **dịch vụ + operation + resource scope + vị trí + loại tier**. Không có một quota chung áp dụng cho mọi API của một cloud.

| Khía cạnh | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Ranh giới quản trị chính | AWS account, Region, dịch vụ; đôi khi theo tài nguyên | Subscription, Region, resource/provider và SKU; đôi khi theo tenant | Project/consumer project, Region/location, API/service; đôi khi theo tài nguyên |
| Công cụ xem quota | Service Quotas, tài liệu dịch vụ, CloudWatch | Azure Quotas, trang Usage + quotas theo dịch vụ, Azure Monitor | Google Cloud Quotas & System Limits, Cloud Monitoring |
| Yêu cầu tăng giới hạn | Tùy quota dịch vụ; có thể yêu cầu nâng qua Service Quotas hoặc hỗ trợ | Tùy loại quota, subscription, Region và cấp hỗ trợ | Tùy metric/quota; có thể yêu cầu điều chỉnh khi được hỗ trợ |
| Theo dõi chi phí | Cost Explorer, Cost and Usage Report, AWS Budgets | Cost Management, budgets, cost analysis | Cloud Billing reports, budgets, billing export |
| Phân bổ chi phí | Account, cost allocation tags, cost categories | Subscription, resource group, tags, billing scopes | Billing account, project, labels, billing export |

**Lưu ý phạm vi:** cùng một doanh nghiệp có thể có nhiều AWS account, Azure subscription hoặc Google Cloud project. Các quota không mặc nhiên được cộng gộp, chia sẻ hay chuyển giữa chúng. Ngược lại, một số quota tổ chức hoặc giới hạn dịch vụ có thể tác động lên nhiều đơn vị bên dưới. Chỉ có tài liệu quota cụ thể mới trả lời được.

Khi tăng quota, cần có kế hoạch **capacity, cost và security**. Quota cao hơn cho phép gọi API hoặc cấp phát tài nguyên nhiều hơn; nó cũng mở ra khả năng phát sinh chi phí lớn hơn hoặc gây tác động rộng hơn nếu ứng dụng có lỗi.

## 5. AWS: quota và billing theo từng dịch vụ

### 5.1. Amazon S3

S3 có cơ chế tự mở rộng cho tải object request, nhưng không nên suy luận rằng **một bucket không bao giờ bị throttling**. Tốc độ phụ thuộc các yếu tố như loại operation, prefix, loại bucket, Region và trạng thái mở rộng. Một số tình huống có thể trả **503 Slow Down**; client nên sử dụng retry policy thích hợp và exponential backoff, quan sát số lần retry.

Chi phí S3 có thể gồm:

- **Lưu trữ** theo GB-tháng, storage class, location, thời gian lưu và quy tắc làm tròn.
- **Request** theo loại operation và nhóm tính phí, như PUT/COPY/POST/LIST hoặc GET/SELECT tùy dịch vụ và storage class.
- **Truy xuất dữ liệu** đối với một số storage class hoặc tính năng.
- **Truyền dữ liệu** qua các region, ra internet và các đường mạng có tính phí.
- **Versioning, replication, lifecycle transition, inventory, analytics**, encryption key/KMS request và các tính năng bổ sung.

Ví dụ bật versioning giúp khôi phục bản ghi đè, nhưng **mọi version được giữ lại có thể tiếp tục tính phí** theo storage class và lifecycle áp dụng. Xóa phiên bản hiện hành không bảo đảm các version cũ không còn chi phí.

### 5.2. Amazon SQS và SNS

SQS có giới hạn theo loại queue, action, message size, throughput và từng tính năng. **Standard** và **FIFO** có đặc điểm throughput và ordering/deduplication khác nhau; một số quota có thể nâng, một số giới hạn do kiến trúc dịch vụ.

Chi phí SQS phụ thuộc **đơn vị request theo bảng giá**, loại queue, lượng message, kích thước message và truyền dữ liệu liên quan. Một lần gọi API có thể được quy đổi thành nhiều đơn vị tính phí theo kích thước hoặc batch; không ước tính chỉ bằng số message thành công nếu ứng dụng liên tục retry hoặc long poll.

SNS tính phí theo loại publish, request/delivery, loại endpoint và các yếu tố khác tùy tier/dịch vụ đích. Một event fan-out tới nhiều subscriber có thể tạo **nhiều đơn vị giao nhận** và chi phí ở dịch vụ nhận.

### 5.3. Amazon RDS, Secrets Manager và các phần phụ trợ

RDS có giới hạn cho số instance, dung lượng, kiểu instance, kết nối và các tham số engine tùy cấu hình. **Maximum connections của database** không phải một con số AWS chung; còn phụ thuộc engine, cấu hình, bộ nhớ và load.

Chi phí RDS có thể gồm thời gian compute, storage provisioned/usage, I/O hoặc throughput theo engine/loại hình, backup vượt phần bao gồm, replication và data transfer. Khi chọn Multi-AZ hay read replica, cần tính tài nguyên bổ sung theo kiến trúc cụ thể.

AWS Secrets Manager có thể tính phí theo secret được quản lý và API calls; rotation còn có thể sử dụng dịch vụ khác. Đọc secret tại mỗi HTTP request gây thêm độ trễ và tăng số lần gọi/chi phí. Cần dùng cache phù hợp với yêu cầu rotation, tuyệt đối không cache bằng cách ghi secret ra log hay file công khai.

**Công cụ AWS nên xem:** Service Quotas để kiểm tra quota hiện hành có thể điều chỉnh; CloudWatch để xem throttles, requests, DB connections và queue metrics; AWS Budgets/Cost Explorer để quan sát chi phí; tài liệu pricing chính thức cho số tiền tại Region, tier và thời điểm thực tế.

## 6. Azure: quota theo subscription, Region và SKU

### 6.1. Azure Blob Storage

Blob Storage có giới hạn ở cấp storage account, throughput, request rate và từng operation/tính năng. Khi bị áp lực tải hoặc chạm giới hạn, tùy API và điều kiện có thể nhận phản hồi **429 Too Many Requests**, **503 Server Busy** hoặc thông tin throttling khác.

Chi phí có thể gồm dung lượng lưu theo tier, giao dịch read/write/list, truy xuất ở tier phù hợp, redundancy như LRS/ZRS/GRS/GZRS, lifecycle, versioning/snapshot, data transfer, private networking và lựa chọn encryption key. **GRS/GZRS là lựa chọn sao chép dữ liệu**, vì vậy cần tính cả chi phí, data location và kỳ vọng khôi phục, không chỉ nhìn đơn giá GB.

### 6.2. Azure Service Bus

Namespace có **tier** như Basic, Standard hoặc Premium với khả năng và mô hình tính phí khác nhau. Các khái niệm như operations, message size, connections, throughput và năng lực **Messaging Units** liên quan đến tier và tính năng.

Tăng số worker Spring Boot không tự tăng năng lực namespace. Nếu nhiều producer phát nhanh hơn consumer xử lý, backlog có thể tăng. Cần điều chỉnh prefetch/concurrency, lock/ack, retry, DLQ và capacity của tier; đánh giá chi phí theo mô hình tính phí hiện hành của SKU.

### 6.3. Azure SQL Database và Key Vault

Azure SQL Database sử dụng tài nguyên tính toán và lưu trữ theo purchasing model, service tier, provisioned/serverless configuration, backup và HA/DR. Một pool JDBC có cấu hình quá lớn có thể gây tắc nghẽn hoặc chạm giới hạn kết nối dù subscription chưa hết quota tạo resource.

Azure Key Vault có giới hạn giao dịch theo loại thao tác, loại vault/khóa và phạm vi thời gian. Các operation không nhất thiết cùng giá và cùng quota. Ví dụ giải mã/crypto operation trên key có thể khác đọc secret. Một số lỗi throttling có thể dùng **Retry-After** theo phản hồi dịch vụ; không retry thiếu giới hạn trên mọi 403.

**Công cụ Azure nên xem:** Azure Quotas hoặc trang usage của dịch vụ, Azure Monitor, Cost Management + Billing và budgets. Không mặc định quota và giá của storage account trong một Region áp dụng cho tất cả Region hoặc tất cả SKU.

## 7. Google Cloud: quotas, system limits và billing theo project

### 7.1. Cloud Storage

Cloud Storage phân biệt **quota có thể điều chỉnh**, **system limits** và giới hạn scaling/performance tùy loại bucket, location và operation. Khi tăng tải đột ngột, cần tính đến hành vi ramp-up, request distribution, retried operations và mức hỗ trợ của dịch vụ.

Chi phí có thể gồm **storage GB-tháng**, Class A/Class B operations theo bảng giá, data retrieval ở storage class phù hợp, network egress và các phí quản lý/replication có liên quan. Bucket regional, dual-region và multi-region khác về data location, cấu hình sao chép và chi phí; đừng dùng project ID để suy ra location hoặc đơn giá.

### 7.2. Pub/Sub

Pub/Sub có quota cho **publish throughput, pull/streaming pull, acknowledge**, các tài nguyên topic/subscription và những giới hạn kỹ thuật khác. Nhiều quota có phạm vi **project và Region**, nhưng phải xem đúng metric trong trang quản trị; quota dành cho một loại request không tương đương throughput toàn hệ thống.

Billing Pub/Sub có thể dựa trên dữ liệu publish/delivery hoặc hạng mục usage tương ứng, retention, snapshot, subscriptions và các tùy chọn khác tùy sản phẩm. Nếu một message có nhiều subscription, lưu lượng giao nhận và chi phí có thể tăng theo số subscriber. Retry và redelivery cũng có thể làm tăng tài nguyên tiêu thụ; hãy kiểm tra đơn vị được tính theo bảng giá hiện hành.

### 7.3. Cloud SQL, Secret Manager và API quota

Cloud SQL có quota về tài nguyên/instance và các giới hạn instance/engine; năng lực xử lý thực tế phụ thuộc CPU, RAM, storage, I/O, connection pool, HA/read replica. Chi phí có thể gồm compute, storage, backup, network và replica theo cấu hình.

Secret Manager phân biệt số lượng version/secret, operation và giới hạn API; từng loại truy cập dữ liệu có thể có cách tính phí khác nhau. Đọc secret liên tục không thay việc thiết kế cache, rotation và bảo vệ payload.

Google Cloud thường hiển thị quota theo **consumer project** hoặc phạm vi chi tiết của API. Nếu client dùng project mặc định khác với project chứa tài nguyên, cần kiểm tra ai đang bị tính quota và billing, cùng các điều kiện IAM, API enablement và organization policy.

**Công cụ GCP nên xem:** Google Cloud Quotas & System Limits, Cloud Monitoring, Cloud Billing reports/budgets và Cloud Billing export để phân tích chi tiết bằng dữ liệu sử dụng thực tế.

## 8. Cách nhận biết throttling và phân loại lỗi

Một HTTP status **không đủ để kết luận** điều kiện nào bị vi phạm. SDK có thể sử dụng gRPC status, mã lỗi riêng, exception wrapper hoặc nhiều lần retry trước khi trả lỗi cuối cùng.

| Tín hiệu | Ý nghĩa có thể có | Cách kiểm tra |
|---|---|---|
| HTTP **429** hoặc gRPC **RESOURCE_EXHAUSTED** | Vượt rate/quota, throttling, hoặc một giới hạn sản phẩm | Provider error code, quota metric, headers, scope/quota name |
| HTTP **503** / **Slow Down** / **Server Busy** | Dịch vụ quá tải hoặc tạm thời hạn chế xử lý | Request metrics, docs error code, latency và Retry-After nếu có |
| HTTP **403** / PermissionDenied | Thiếu IAM/RBAC, policy, token audience, network restriction | Runtime identity, resource scope, policy; không tự động tăng quota |
| HTTP **400** | Payload, yêu cầu hoặc parameter không hợp lệ | Validation, kích thước dữ liệu, service limit, error details |
| HTTP **409** / conflict | Xung đột phiên bản, trạng thái hoặc thao tác cạnh tranh | Preconditions, ETag/generation, idempotency |
| Timeout/connection reset | Mạng hoặc downstream chậm; kết quả có thể chưa biết | Trace/request ID, deadline, server logs và idempotency |

Các bước chẩn đoán cơ bản:

1. Ghi lại **service, action, resource ID, Region, principal, request ID, timestamp**, nhưng không ghi token/secret.
2. Đọc **mã lỗi chi tiết** và quota metric liên quan thay vì chỉ nhìn HTTP status.
3. Xác định **phạm vi quota**: per project, account, region, resource, identity hay request method.
4. Kiểm tra tình trạng retry từ **SDK và ứng dụng**; đôi khi request gốc có một lần nhưng downstream thấy nhiều attempts.
5. Kiểm tra thêm quyền, network, capacity tier và tính đúng đắn nghiệp vụ nếu quota chưa chạm ngưỡng.

**Không retry vô hạn các lỗi 401/403 hay request validation.** Với lỗi tạm thời, retry chỉ an toàn khi xử lý được khả năng request trước đó đã có tác dụng phụ.

## 9. Rate limiting, retry và backpressure trong Spring Boot

### 9.1. Kiểm soát tải theo từng tầng

~~~mermaid
flowchart LR
    API["Incoming requests"] --> RL["Rate limit / admission control"]
    RL --> BH["Bulkhead / concurrency cap"]
    BH --> SDK["Cloud SDK: timeout + bounded retry"]
    SDK --> SV["AWS / Azure / Google service"]
    SV --> MT["Metrics: 429, latency, backlog"]
    MT -. "Điều chỉnh năng lực" .-> RL
    MT -. "Điều chỉnh retry/limit" .-> BH
~~~

Một cách tiếp cận theo thứ tự:

- **Giới hạn request đầu vào** theo tenant/client hoặc toàn dịch vụ để ngăn một khách hàng chiếm hết quota.
- **Giới hạn concurrency** của mỗi downstream bằng semaphore/bulkhead và connection pool.
- Dùng **bounded queue** cho công việc có thể chạy bất đồng bộ; tránh queue vô hạn.
- Dùng **batch API** ở nơi có lợi, nhưng kiểm tra kích thước payload, hạn ngạch per batch, trường hợp thành công một phần và cách tính phí.
- **Retry có exponential backoff + jitter**, tôn trọng Retry-After nếu API hỗ trợ, giới hạn attempts và overall deadline.
- Có **idempotency key** khi retry các lệnh tạo/ghi dữ liệu, cùng logic dedup ở phía ứng dụng.
- Quan sát p95/p99, throttling rate và saturation để tinh chỉnh thay vì chỉ tăng retry count.

### 9.2. Vì sao retry lồng nhau nguy hiểm?

Nếu tầng HTTP retry 3 lần, service layer retry 3 lần và SDK lại retry 3 lần, một yêu cầu nghiệp vụ có thể dẫn đến **tối đa 27 attempts downstream** trong tình huống nhất định. Việc tăng attempts làm tăng tải đúng lúc downstream đang quá tải; nó có thể tăng request billing và gây duplicate side effect.

Dùng cơ chế retry đã có trong AWS SDK, Azure SDK hoặc Google Cloud client library khi phù hợp. Trước khi thêm Spring Retry/Resilience4j bên ngoài, hãy thống nhất lớp chịu trách nhiệm và đo **tổng số attempts**. Retry ngoài còn phải cân nhắc deadline tổng và idempotency.

### 9.3. Ví dụ Spring Boot + AWS SDK v2: giới hạn concurrency khi gửi SQS

Đây là ví dụ minh họa **concurrency cap cục bộ** để bảo vệ resource, không phải rate limiter phân tán hoặc cấu hình quota AWS:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

@Configuration
class CloudClientConfig {
    @Bean
    SqsClient sqsClient(@Value("${app.aws.region}") String region) {
        return SqsClient.builder().region(Region.of(region)).build();
    }
}

@Service
class OrderPublisher {
    private final SqsClient sqs;
    private final String queueUrl;
    private final Semaphore inFlight = new Semaphore(16);

    OrderPublisher(
            SqsClient sqs,
            @Value("${app.messaging.queue-url}") String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    String send(String eventJson) throws InterruptedException {
        if (!inFlight.tryAcquire(250, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Publisher is overloaded");
        }
        try {
            return sqs.sendMessage(SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageBody(eventJson)
                    .build()).messageId();
        } finally {
            inFlight.release();
        }
    }
}
~~~

~~~yaml
app:
  aws:
    region: ap-southeast-1
  messaging:
    queue-url: https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-test
~~~

Các property **app.*** ở đây do ví dụ định nghĩa, không phải property Spring Cloud AWS dùng chung cho mọi phiên bản. Đoạn code giả định dependency AWS SDK v2 SQS, Spring Boot có auto-configuration cơ bản và runtime credential thông qua provider chain/role. Nếu ứng dụng đã dùng Spring Cloud AWS auto-configured client, cần tránh khai báo bean trùng và dùng BOM tương thích với Spring Boot.

Lưu ý quan trọng:

- **16 permits** chỉ giới hạn tối đa 16 lời gọi đang thực hiện **trong một instance**; nó không đảm bảo tối đa 16 request/giây hay giới hạn cho toàn cluster.
- SDK có thể tự retry theo chính sách mặc định; một lần gọi Java có thể phát sinh nhiều API attempts.
- Gửi message xong nhưng phản hồi mất có thể khiến retry tạo message thứ hai. Payload nên mang **eventId/idempotency key** để consumer xử lý lặp an toàn; dùng outbox khi cần bảo đảm publish sau commit DB.
- Trong hệ thống thực, nên phân loại lỗi overload thành response thích hợp, đo metric thời gian chờ permit, xác định timeout toàn luồng, và dùng rate limiter tập trung khi cần ràng buộc toàn deployment.
- Không nhúng AWS access key/secret key trong code hoặc YAML.

Tương tự, với **Spring Cloud Azure** hoặc **Spring Cloud GCP**, đặt giới hạn ở adapter/service layer phía ứng dụng và kết hợp chính sách retry được SDK dịch vụ hỗ trợ. Cấu hình per-operation và thuộc tính starter phải tra theo **phiên bản thư viện sử dụng**.

## 10. Tính phí theo mức sử dụng: hiểu đúng đơn vị đo

Các cloud thường dùng **mô hình nhiều đồng hồ tính phí (billing meters)**. Một resource có thể phát sinh nhiều loại phí cùng lúc.

| Thành phần | Đơn vị tính phí thường gặp | Ví dụ thực tế |
|---|---|---|
| Compute/runtime | vCPU-giây, GB-giây, giờ/giây instance, capacity units | Container chạy liên tục, database provisioned |
| Object storage | GB-tháng theo tier/location | Ảnh, file hóa đơn, bản sao, version |
| Storage operations | Số request/transaction theo loại | PUT, GET, LIST, lifecycle transition |
| Messaging | Số operation, request unit, byte ingress/egress, capacity tier | Publish, pull, send, delivery, retention |
| Managed database | Compute, storage, IOPS/I/O, backup, replica | Primary + read replica, backup dài hạn |
| Secrets/KMS | Secret/version, API operations, cryptographic requests | Đọc secret, decrypt key |
| Network | GB truyền ra internet, giữa Region/AZ, qua gateway/endpoint | Ứng dụng gọi DB khác Region |
| Observability | Ingested logs, retained GB, metric series, tracing | Debug log toàn bộ request, lưu lâu |
| Backup/replication | GB sao chép/lưu, request, traffic | Cross-region backup, secondary database |

**Giá theo đơn vị** thay đổi theo provider, Region, storage class, SKU/tier, thời gian, hợp đồng và free tier. Một số sản phẩm tính phí theo đơn vị tối thiểu, thời gian provisioned dù ít request, hoặc ngưỡng lưu trữ tối thiểu. Khi lập dự toán cần dùng bảng giá **đúng SKU và ngày hiện hành**; không coi ví dụ dưới đây là báo giá.

### 10.1. Công thức lập dự toán đơn giản

~~~text
Tổng phí ước tính
  = Compute
  + Storage chính và bản sao
  + API requests / operations
  + Messaging ingress, delivery, retention
  + Data transfer / networking
  + Backup, KMS, secret, logs
  + Các hạng mục dịch vụ bổ sung
  - Credits / discounts áp dụng
~~~

Ví dụ giả định một tháng **31 ngày**, chỉ chọn bốn thành phần để học phương pháp tính:

| Hạng mục giả định | Usage | Đơn giá giả định | Thành tiền |
|---|---:|---:|---:|
| Object storage | 120 GB-tháng | 0,025 USD/GB-tháng | 3,00 USD |
| API operations | 2.000.000 requests | 0,004 USD/1.000 requests | 8,00 USD |
| Network egress có tính phí | 70 GB | 0,09 USD/GB | 6,30 USD |
| Runtime luôn bật | 744 giờ | 0,05 USD/giờ | 37,20 USD |
| **Tổng giả định** | | | **54,50 USD** |

Đây là **các đơn giá giả định phục vụ minh họa số học**; không khẳng định giá AWS, Azure hay Google Cloud. Bảng chưa tính database, queue, KMS, backup, logs, thuế, free tier, round-up, volume discounts và các khoản khác. Một dự toán production phải tính đúng hạng mục theo billing meter của dịch vụ thực tế.

### 10.2. Tăng traffic không đồng nghĩa tăng chi phí tuyến tính

Một hệ thống có **chi phí cố định theo provisioned capacity** cộng với **chi phí biến đổi theo usage**. Với DB instance chạy cả tháng, giảm nửa số SQL query chưa chắc giảm nửa bill compute. Ngược lại, object storage có thể tăng phí theo dữ liệu tích lũy ngay cả khi traffic giảm.

Khi traffic tăng vượt một ngưỡng, hệ thống có thể cần thêm DB replica, nâng tier messaging hoặc bật thêm network capacity, làm đường chi phí tăng theo **bậc** chứ không liên tục tuyến tính.

## 11. Sáu tình huống gây tăng chi phí âm thầm

1. **Retry storm:** SDK và nhiều lớp ứng dụng cùng retry, nhân số request billable và áp lực quota.
2. **Nhiều bản sao dữ liệu:** versioning, soft delete, backup, snapshot, cross-region replication giữ nhiều dữ liệu hơn dự kiến.
3. **Cross-region hoặc internet egress:** workload và dữ liệu đặt xa nhau, job export và backup tạo traffic lớn.
4. **Log quá nhiều:** ghi request/response body, stack trace hay trace 100% ở tải lớn khiến storage/ingestion tăng; đồng thời có rủi ro lộ dữ liệu.
5. **Provisioned resource quên dọn:** DB, private endpoint, NAT gateway, premium tier, test cluster, IP hoặc disk tiếp tục có phí dù không dùng.
6. **Fan-out/retention:** cùng event phát tới nhiều subscription/queue, giữ message quá lâu, retry hoặc redelivery dồn backlog.

Tối ưu chi phí cần xét **tính đúng đắn và bảo mật**. Ví dụ, giảm backup retention đến mức không thể đáp ứng RPO/RTO hoặc xóa audit log cần thiết có thể tiết kiệm hóa đơn nhưng tạo rủi ro lớn hơn.

## 12. Budget, quota và guardrail trong một quy trình vận hành

### 12.1. Ba lớp kiểm soát

~~~mermaid
flowchart TD
    PLAN["Dự báo tải và chi phí"] --> Q["Quota / service limit<br/>theo service, Region, project"]
    PLAN --> B["Budget + alert theo chi phí"]
    PLAN --> L["Rate / concurrency limit<br/>trong ứng dụng"]
    Q --> OBS["Metrics + billing review"]
    B --> OBS
    L --> OBS
    OBS --> ACT["Điều chỉnh capacity, code, policy và ngân sách"]
~~~

- **Quota** giới hạn một đại lượng kỹ thuật; giúp kiểm soát provisioning hoặc lượng request nhưng không tự thay thế quản lý chi phí.
- **Budget** giúp phát hiện chênh lệch spending; không mặc định chặn provisioned capacity đang chạy hoặc những chi phí được ghi nhận trễ.
- **Application guardrail** như rate limit, bounded queue, timeout và concurrency cap hạn chế việc ứng dụng gây tải quá mức theo quy tắc nghiệp vụ.

### 12.2. Chủ sở hữu và ngân sách

Một triển khai trưởng thành nên xác định:
 
| Kiểm soát | Chủ sở hữu gợi ý | Bằng chứng |
|---|---|---|
| Quota còn dư cho launch | Platform/SRE | Quota metric và kế hoạch capacity |
| Rate limiting theo tenant | Backend team | Load test, metric rejected/accepted |
| Retry có kiểm soát | Backend team | Tổng attempts/request, 429 rate, p95/p99 |
| Budget cho môi trường | FinOps/Platform | Alert thresholds, billing dashboard |
| Tài nguyên gắn cost label | IaC/Platform | Tag/label coverage và cost allocation |
| Dọn môi trường test | QA/Platform | TTL, IaC teardown, danh sách resource còn lại |
| Quy trình ứng phó bất thường | On-call/Operations | Runbook, alert routing, lịch sử incident |

Gắn nhãn **environment**, **team**, **service**, **cost-center** theo khả năng hỗ trợ của dịch vụ. Tuy nhiên, tag/label không tự động chuyển chi phí sang đúng người nếu chức năng cost allocation chưa được bật hoặc đơn vị tính phí nằm ở shared services.

### 12.3. Cần làm gì khi budget vượt ngưỡng?

Khi nhận cảnh báo: kiểm tra tài nguyên/dịch vụ nào tăng bill, so sánh với baseline traffic, tìm spike retries, egress, log ingest, resource mới, backup/replication hoặc thay đổi tier. Không nên tự động xóa production database chỉ vì budget đạt ngưỡng.

Nếu thiết kế automation hạn chế chi tiêu, hãy thử trên môi trường cô lập, phân biệt workload **có thể dừng** và **không thể dừng**, xác định người phê duyệt và hậu quả đối với dữ liệu, availability và billing tiếp tục phát sinh.

## 13. Bài toán capacity planning cho Spring Boot

### 13.1. Database connection pool khi scale ngang

Giả sử Spring Boot có **20 replica**, mỗi replica cấu hình **maximum pool size = 20**. Tổng kết nối ứng dụng tối đa theo cấu hình có thể đạt **400 connection** (20 × 20), chưa tính admin sessions, maintenance, job và dịch vụ khác.

Nếu database chỉ cho phép hoặc chỉ xử lý tốt ít hơn 400 kết nối, scale thêm replica có thể làm lỗi nặng hơn. Phương án là:
 
- Đo số connection hoạt động và thời gian giữ connection thay vì chọn pool theo CPU một cách máy móc.
- Tính tổng pool trong **mọi replica và worker**, dự trù headroom.
- Dùng proxy/pooler được hỗ trợ nếu phù hợp engine và workload, nhưng không xem đó là vô hạn kết nối.
- Giảm transaction quá dài, tối ưu SQL và cache theo tính nhất quán nghiệp vụ.
- Load test dưới đúng giới hạn database và xác minh hành vi autoscale.

### 13.2. Queue backlog khi producer nhanh hơn consumer

Nếu producer trung bình phát **1.000 message/phút** còn consumer xử lý **800 message/phút**, backlog tăng khoảng **200 message/phút** khi điều kiện giữ nguyên. Sau 30 phút, tồn đọng mới có thể lên đến **6.000 message** (chưa tính retry, DLQ và các biến thiên khác).

Muốn giải quyết cần tăng throughput tiêu thụ hợp lý, giảm lượng message, batch thích hợp hoặc tạo backpressure phía producer. **Chỉ tăng retention** giúp message tồn tại lâu hơn nhưng không làm consumer xử lý nhanh hơn.

### 13.3. Tách ba ngưỡng

Khi chuẩn bị tăng tải, thiết lập ba ngưỡng khác nhau:

1. **Ngưỡng nghiệp vụ:** số đơn/phút, latency cho người dùng, tỷ lệ thành công.
2. **Ngưỡng kỹ thuật:** DB connections, API request quota, messaging throughput, pool saturation.
3. **Ngưỡng tài chính:** chi phí dự kiến/ngày/tháng, egress, storage growth và budget alert.

Một hệ thống vượt ngưỡng kỹ thuật trước khi đạt ngưỡng tài chính vẫn cần xử lý. Một hệ thống chưa chạm quota nhưng egress tăng gấp nhiều lần vẫn cần điều tra chi phí.

## 14. Thiết kế kiểm thử tích hợp và hiệu năng có kiểm soát

Trước khi chạy load test trên AWS/Azure/GCP, dùng account/subscription/project test và nguồn dữ liệu cô lập; xác định người sở hữu resource và cách cleanup. Tăng tải dần theo kịch bản được phê duyệt, không tạo burst lớn vào production hoặc cố vượt quota một cách không kiểm soát.

| Kịch bản | Điều cần quan sát | Tiêu chí thành công |
|---|---|---|
| Tải tăng dần tới ngưỡng | Throughput, p95/p99, 429/503, CPU/pool | Không có queue vô hạn hoặc timeout dây chuyền |
| Rate limiter per instance | Accepted/rejected mỗi pod và toàn cụm | Tổng tải tuân theo chính sách đã thiết kế |
| Retry sau 429 | Attempts, backoff, Retry-After, deadline | Không xuất hiện retry storm |
| Publisher mất ACK sau send | Duplicate event, outbox, consumer dedup | Không có side effect nghiệp vụ lặp |
| DB pool gần giới hạn | Acquire latency, timeout, active/idle | Backpressure và khả năng phục hồi có kiểm soát |
| Queue backlog kéo dài | Oldest message age, DLQ, retries | Có alert, scale hoặc giảm producer hợp lý |
| Billing khi tăng load | API request units, egress, logs | Ước tính bám sát billing meter và dự toán |
| Resource ở sai Region/tier | Location, SKU, endpoint, cost | Phát hiện cấu hình trước khi đẩy dữ liệu thật |
| Thiếu IAM role | PermissionDenied/403 | Phân loại lỗi quyền, không retry vô hạn |
| Cleanup sau test | Bucket objects, DB/queue, disks, alerts | Không để lại resource billable ngoài kế hoạch |

**Mock test** có thể kiểm tra retry logic, semaphore và parsing lỗi, nhưng không xác minh quota, pricing hay hành vi network thật. Integration/load test trên cloud phải có ngưỡng an toàn cho số request, thời lượng, ngân sách dự kiến và khả năng dừng.

### 14.1. Các metrics nên có

- **Client/SDK:** requests, attempts, retries, 429/503, timeout, end-to-end deadline exceeded, request latency p50/p95/p99.
- **Application:** active threads, connection-pool saturation, concurrent calls, rejected requests, queue length, circuit breaker state.
- **Messaging:** ingress/egress, send/receive rates, backlog, oldest message age, delivery count, DLQ, message size.
- **Database:** active/max connection, waiting requests, query latency, I/O, CPU, lock waits.
- **Cost:** usage theo service, Region, environment và billing meter; daily spend, forecast, anomaly alerts, log/egress/backup growth.
- **Security:** throttling do policy hay 403 do IAM, audit việc nâng quota, thay đổi role, thay đổi tier hoặc bật replication.

Các metric và log phải loại bỏ token, access key, secret value, payload cá nhân và dữ liệu nhạy cảm. Billing data có thể xuất hiện trễ so với request metrics; vì vậy cảnh báo chi phí nên kết hợp **tín hiệu kỹ thuật thời gian gần thực** và billing report.

## 15. Tình huống chẩn đoán thường gặp

### Tình huống A: AWS S3 trả 503 khi upload tăng đột biến

Một job chạy song song số lượng lớn PUT vào cùng luồng lưu trữ. Kiểm tra request distribution, operation, prefix/loại bucket, throughput, SDK retry và CloudWatch metrics. Giảm tốc độ đột ngột bằng concurrency cap, backoff/jitter, batch/phân phối phù hợp và điều chỉnh tải dần. Đồng thời xem số lần retry có làm tăng request billing hoặc tác vụ trùng không.

### Tình huống B: Azure Service Bus chậm dù tăng worker

Consumer tăng từ 5 lên 30 replica, nhưng namespace ở tier/capacity giới hạn và downstream database chạm maximum connections. Tăng worker làm tăng redelivery, lock expiry hoặc DB timeout. Điều tra namespace metrics, lock duration, prefetch, DB pool tổng, DLQ và đơn vị tính phí. Điều chỉnh cả **producer rate, worker concurrency, tier capacity và DB throughput**.

### Tình huống C: GCP Pub/Sub trả RESOURCE_EXHAUSTED

Publisher tăng message size và throughput, đồng thời SDK retry nhiều attempts. Kiểm tra quota metric chính xác theo project/region và API, IAM, API enablement, backlog, batch settings, publish flow control và error detail. Giảm tốc độ, bật batching/flow control phù hợp hoặc xin tăng quota nếu dịch vụ hỗ trợ và workload đã chứng minh nhu cầu.

### Tình huống D: chi phí database tăng mà traffic không tăng

Một managed database được nâng instance tier để thử hiệu năng và quên hạ xuống; thêm read replica hoặc backup retention kéo dài. Billing có thể tăng dù RPS không đổi. Kiểm tra resource inventory, SKU hiện tại, instance-hours, backup, replica, cross-region transfer và nhãn cost allocation; thêm review sau thử nghiệm.

### Tình huống E: Spring Boot lỗi 403 nhưng nhóm xin tăng quota

403 có thể do thiếu IAM/RBAC, sai service account/managed identity, resource scope hoặc network policy. Tăng quota không giải quyết quyền truy cập. Xác định principal thực tế và permission action trước, đọc error code/trace. Chỉ điều chỉnh quota khi bằng chứng cho thấy chạm đúng hạn ngạch kỹ thuật.

## 16. Những hiểu nhầm phổ biến

| Hiểu nhầm | Điều cần hiểu |
|---|---|
| “Có quota cao nghĩa là chi phí luôn thấp” | Quota chỉ đặt giới hạn kỹ thuật; sử dụng nhiều có thể tính phí nhiều |
| “Đặt budget nghĩa là vượt tiền cloud tự ngắt” | Budget thường là cảnh báo; automation chặn/dừng phải thiết kế riêng |
| “429 nào cũng là hết tổng quota tháng” | Có thể là rate limit theo thời gian, principal, operation hoặc resource |
| “Tăng retry count sẽ giúp vượt giới hạn nhanh hơn” | Retry dồn dập dễ gây throttling nặng hơn và tăng chi phí |
| “Concurrency 16 nghĩa là chỉ 16 request/giây” | Concurrency là số đồng thời, RPS còn phụ thuộc latency |
| “Mỗi pod có limiter là đã có global limit” | Tổng tải nhân với số replica nếu không phối hợp |
| “Không có traffic thì không có phí” | DB provisioned, instance, disk, endpoint, backup hoặc tier vẫn có thể tính phí |
| “Một message chỉ có một đơn vị tính phí” | Kích thước, batch, fan-out, delivery và model định giá có thể thay đổi số đơn vị |
| “Có thể tăng mọi quota nếu trả thêm tiền” | Có hard limits và hạn ngạch không điều chỉnh được |
| “Quota và pricing của mọi region giống nhau” | Region, tier, loại tài nguyên và hợp đồng có thể khác |
| “Mock test đủ chứng minh ứng dụng chịu quota cloud” | Cần kiểm thử cloud cô lập và quan sát metrics thực tế |
| “Tăng connection pool luôn làm database nhanh hơn” | Tổng kết nối và contention có thể làm DB quá tải |

## 17. Checklist trước khi lên production

- **Quota inventory:** liệt kê service, operation, scope, Region, current usage, limit và khả năng tăng; dành headroom cho launch.
- **Traffic model:** ước tính request/giây, burst, message size, concurrency, database connections và số replica.
- **SDK policy:** biết retry mặc định của cloud SDK, đặt overall deadline, backoff/jitter, timeout, max attempts và xử lý Retry-After khi thích hợp.
- **Idempotency:** mọi write/send có thể bị retry phải có cách ngăn side effect nghiệp vụ lặp; consumer xử lý redelivery và DLQ.
- **Backpressure:** giới hạn ingress, concurrency, pool, queue và autoscaling theo năng lực downstream.
- **Pricing model:** lập danh sách billing meters theo Region/SKU, cả request, storage, compute, network, KMS, backup, logs và replication.
- **Budget/alert:** đặt cảnh báo theo môi trường, team và service; xác nhận ai nhận, ai xử lý và hành động nào an toàn.
- **Security:** IAM role, managed identity, service account đúng phạm vi; không log secret; không tự tăng quyền khi nhận 403.
- **Testing:** load test có kiểm soát với lỗi 429/503, timeout, retry, duplicate, DB pool và cleanup; không làm ảnh hưởng production.
- **Review định kỳ:** kiểm tra cost anomaly, drift của tier, tài nguyên không dùng, quota headroom, backup retention và tình trạng label.

## 18. Tổng kết

**Hạn ngạch** xác định giới hạn sử dụng tài nguyên/API, **giới hạn tốc độ** điều chỉnh mức tải và đồng thời, còn **mô hình tính phí** quy đổi usage thành chi phí theo nhiều đơn vị đo. Ba cơ chế có quan hệ với nhau nhưng không thay thế cho nhau. Ứng dụng vẫn có thể bị throttling khi chưa hết quota tổng, hoặc phát sinh hóa đơn lớn khi chưa từng thấy lỗi 429.

Khi tích hợp Spring Boot với AWS, Azure và Google Cloud, nên đi theo chuỗi **xác định quota scope → đo tải thực → giới hạn concurrency/rate → retry an toàn → bảo vệ idempotency → quan sát billing meters → đặt budget và kiểm thử**. Cách làm này giúp hệ thống dùng storage, messaging, database và secret manager ổn định hơn, dễ dự đoán chi phí và tránh biến lỗi tải tạm thời thành sự cố diện rộng.

